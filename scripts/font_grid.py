#!/usr/bin/env python3
"""
How badly does a face fight the pixel grid?

This exists because of a defect the user found by eye: intra-word letter gaps in
the demo come out 1-4 px where the design asks for a fraction, and at heading
size adjacent letters fuse. `advtext.backends.imgui_draw.snap_px` rounds every
glyph origin to a whole pixel, so the gap a reader sees is the designed gap plus
a rounding error, and the error is a property of *the face at that size*.

A face's advance in pixels is

    advance_px = advance_units * size_px / units_per_em

so an advance lands exactly on the grid when `advance_units` is a multiple of
`units_per_em / size_px`. Roboto is 2048 upm, so at 16 px it wants multiples of
128, and its advances are not: `a` is 1114 units, 8.703 px. Inconsolata is
1000 upm and every advance is 500 units, exactly 8.000 px at 16 px -- it cannot
fight the grid at this size, which makes it the control rather than the winner.

Two metrics, because they answer different questions.

**Per-advance** is the one an earlier measurement in this project used: the mean
distance from each letter's advance to the nearest whole (and half) pixel. It is
a property of the face alone and it is easy to check by hand.

**Per-origin** is the one that matches the complaint. Letters inside a word
accumulate: the origin of the fifth letter is the sum of four advances plus any
kerns, and it is *that* sum which gets rounded. So this walks the real words of
a real document, accumulates real advances, and reports how far each glyph
origin is displaced by snapping -- and, more to the point, the spread of the
errors applied to the gaps *within* a word, because an even set of wrong gaps
reads better than an uneven set of nearly-right ones.

Neither number says a face looks better. They say how much rounding it invites.
The looking is the user's, per `.concerns/lead--visual-standard.md`.

Usage:

    .venv/bin/python scripts/font_grid.py                    # the default table
    .venv/bin/python scripts/font_grid.py --size 16 --size 20
    .venv/bin/python scripts/font_grid.py --sweep            # size sweep per face
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont

# The body size the demo sets. `advtext.style.BODY_SIZE_PX`.
DEFAULT_SIZE_PX = 16.0

# The faces to compare. The first is what ships; the rest are what is installed
# on this machine and is a plausible text face. A path that does not exist is
# reported and skipped rather than raising, because this list is machine
# specific and the script is meant to survive being run elsewhere.
CANDIDATES: tuple[tuple[str, str], ...] = (
    ("Roboto (shipped)", "@bundle:Roboto/Roboto-Regular.ttf"),
    ("Inconsolata (shipped, mono)", "@bundle:Inconsolata-Medium.ttf"),
    ("DroidSans (bundled)", "@bundle:DroidSans.ttf"),
    ("DejaVu Serif", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("Liberation Serif", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
    ("Liberation Sans", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ("Noto Serif", "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"),
    ("Noto Sans", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    ("Nimbus Roman (Times)", "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf"),
    ("Nimbus Sans (Helvetica)", "/usr/share/fonts/opentype/urw-base35/NimbusSans-Regular.otf"),
    ("C059 (Century Schoolbook)", "/usr/share/fonts/opentype/urw-base35/C059-Roman.otf"),
    ("P052 (Palatino)", "/usr/share/fonts/opentype/urw-base35/P052-Roman.otf"),
    ("URW Bookman", "/usr/share/fonts/opentype/urw-base35/URWBookman-Light.otf"),
    ("Latin Modern Math", "@bundle:latex/latinmodern-math.otf"),
)

# a-z A-Z, the set the earlier measurement in this project used, so its numbers
# and these are comparable.
ALPHABET = tuple(chr(c) for c in range(ord("a"), ord("z") + 1)) + tuple(
    chr(c) for c in range(ord("A"), ord("Z") + 1)
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'’]*")


def bundle_directory() -> Path:
    """Where imgui_bundle keeps the fonts this project ships."""
    import imgui_bundle

    return Path(imgui_bundle.__file__).parent / "assets" / "fonts"


def resolve(spec: str) -> Path:
    """A candidate's path, expanding the `@bundle:` prefix."""
    if spec.startswith("@bundle:"):
        return bundle_directory() / spec[len("@bundle:") :]
    return Path(spec)


@dataclass(frozen=True)
class Metrics:
    """One face's advances and kerns, in font units, with the em they measure in."""

    name: str
    path: Path
    upm: int
    advances: dict[str, int]
    kerns: dict[tuple[str, str], int]

    def px(self, letter: str, size_px: float) -> float:
        return self.advances[letter] * size_px / self.upm

    def kern_px(self, left: str, right: str, size_px: float) -> float:
        return self.kerns.get((left, right), 0) * size_px / self.upm

    @property
    def grid_unit(self) -> float:
        """
        Font units per pixel at 16 px -- the multiple an advance must be to land
        on the grid. Reported because it explains every row that follows.
        """
        return self.upm / DEFAULT_SIZE_PX


def _pair_kerns(font: TTFont, letters: Mapping[str, str]) -> dict[tuple[str, str], int]:
    """
    GPOS x-advance kerns between the letters we measure, both subtable formats.

    This matters more than it looks. The whole finding below is that some faces
    put every *advance* on a whole number of pixels at 18 px -- but a kern is an
    independent number, and if kerns are off the grid then a kerned pair throws
    the rest of its word off it too. So the kern has to be in the walk, or the
    "pixel perfect" claim is measured against a pipeline nobody ships.
    """
    if "GPOS" not in font:
        return {}
    glyph_to_letter = {glyph: letter for letter, glyph in letters.items()}
    kerns: dict[tuple[str, str], int] = {}
    gdef = font.get("GDEF")
    for lookup in font["GPOS"].table.LookupList.Lookup:
        if lookup.LookupType != 2:
            continue
        for sub in lookup.SubTable:
            fmt = getattr(sub, "Format", None)
            coverage = getattr(sub, "Coverage", None)
            if fmt == 1 and getattr(sub, "PairSet", None) and coverage is not None:
                for first, pair_set in zip(coverage.glyphs, sub.PairSet, strict=False):
                    left = glyph_to_letter.get(first)
                    if left is None:
                        continue
                    for record in pair_set.PairValueRecord:
                        right = glyph_to_letter.get(record.SecondGlyph)
                        value = getattr(record.Value1, "XAdvance", 0) or 0
                        if right is not None and value:
                            kerns[(left, right)] = value
            elif fmt == 2 and getattr(sub, "Class1Record", None) and coverage is not None:
                class1 = sub.ClassDef1.classDefs
                class2 = sub.ClassDef2.classDefs
                covered = set(coverage.glyphs)
                for left_glyph, left in glyph_to_letter.items():
                    if left_glyph not in covered:
                        continue
                    row = sub.Class1Record[class1.get(left_glyph, 0)]
                    for right_glyph, right in glyph_to_letter.items():
                        record = row.Class2Record[class2.get(right_glyph, 0)]
                        value = getattr(record.Value1, "XAdvance", 0) or 0
                        if value:
                            kerns.setdefault((left, right), value)
    del gdef
    return kerns


def read_metrics(name: str, path: Path) -> Metrics | None:
    """Advances and kerns for `ALPHABET`, or None if the file or coverage is missing."""
    if not path.is_file():
        return None
    font = TTFont(path, lazy=True)
    try:
        upm = int(font["head"].unitsPerEm)
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        advances: dict[str, int] = {}
        glyphs: dict[str, str] = {}
        for letter in ALPHABET:
            glyph = cmap.get(ord(letter))
            if glyph is None or glyph not in hmtx.metrics:
                continue
            advances[letter] = int(hmtx[glyph][0])
            glyphs[letter] = glyph
        if len(advances) < len(ALPHABET) // 2:
            return None
        try:
            kerns = _pair_kerns(font, glyphs)
        except (AttributeError, KeyError, IndexError):
            # A malformed or unusual GPOS is reported as "no kerns" rather than
            # crashing the whole table, because this list is machine specific.
            print(f"  (could not read GPOS kerns for {name})", file=sys.stderr)
            kerns = {}
        return Metrics(name=name, path=path, upm=upm, advances=advances, kerns=kerns)
    finally:
        font.close()


def distance_to_grid(value: float, step: float) -> float:
    """How far `value` sits from the nearest multiple of `step`."""
    scaled = value / step
    return abs(scaled - round(scaled)) * step


@dataclass(frozen=True)
class AdvanceReport:
    """The per-advance metric: a property of the face, independent of any text."""

    whole: float
    half: float
    on_grid: int
    total: int


def measure_advances(metrics: Metrics, size_px: float) -> AdvanceReport:
    whole: list[float] = []
    half: list[float] = []
    on_grid = 0
    for letter in metrics.advances:
        value = metrics.px(letter, size_px)
        d_whole = distance_to_grid(value, 1.0)
        whole.append(d_whole)
        half.append(distance_to_grid(value, 0.5))
        # A tenth of a thousandth of a pixel is float noise, not a design.
        if d_whole < 1e-4:
            on_grid += 1
    return AdvanceReport(
        whole=statistics.fmean(whole),
        half=statistics.fmean(half),
        on_grid=on_grid,
        total=len(whole),
    )


@dataclass(frozen=True)
class OriginReport:
    """
    The per-origin metric: what snapping actually does to the words of a text.

    `displacement_*` is how far a glyph is moved from where layout put it.
    `gap_error_sd` is the standard deviation of the error applied to the gaps
    *inside* a word, which is the quantity the reader's complaint is written in:
    an evenly-wrong set of gaps reads better than an unevenly-near-right one.
    """

    words: int
    glyphs: int
    displacement_mean: float
    displacement_max: float
    gap_error_sd: float


def measure_origins(
    metrics: Metrics,
    size_px: float,
    words: Sequence[str],
    *,
    step: float = 1.0,
    kerning: bool = True,
) -> OriginReport:
    """
    Walk each word, accumulate advances and kerns, and snap each origin to `step`.

    `kerning` is a parameter rather than always-on because the two settings
    answer different questions, and the difference between them turned out to be
    the most important number this script produces. With it off you measure the
    face's *advance* design against the grid. With it on you measure what the
    renderer actually places, because `advtext` applies GPOS kerns.
    """
    displacements: list[float] = []
    gap_errors: list[float] = []
    counted_words = 0
    for word in words:
        letters = [c for c in word if c in metrics.advances]
        if len(letters) < 2:
            continue
        counted_words += 1
        pen = 0.0
        errors: list[float] = []
        for index, letter in enumerate(letters):
            if kerning and index:
                pen += metrics.kern_px(letters[index - 1], letter, size_px)
            snapped = round(pen / step) * step
            error = snapped - pen
            displacements.append(abs(error))
            errors.append(error)
            pen += metrics.px(letter, size_px)
        # The gap between two letters is stretched or squeezed by the difference
        # of their two origin errors, so that difference is the visible quantity.
        gap_errors.extend(b - a for a, b in zip(errors, errors[1:], strict=False))
    if not displacements:
        return OriginReport(0, 0, 0.0, 0.0, 0.0)
    return OriginReport(
        words=counted_words,
        glyphs=len(displacements),
        displacement_mean=statistics.fmean(displacements),
        displacement_max=max(displacements),
        gap_error_sd=statistics.pstdev(gap_errors) if len(gap_errors) > 1 else 0.0,
    )


def kern_report(metrics: Metrics, size_px: float, words: Sequence[str]) -> tuple[int, int, int]:
    """
    How many adjacent letter pairs in the corpus are kerned, and how many of
    those kerns land on a whole pixel.

    This is the size of the exception to the on-grid finding. A face whose
    advances are all whole pixels still leaves its *kerned* pairs off the grid,
    and the only honest way to say how much that costs is to count the pairs a
    real document actually contains.
    """
    pairs = 0
    kerned = 0
    on_grid = 0
    for word in words:
        letters = [c for c in word if c in metrics.advances]
        for left, right in zip(letters, letters[1:], strict=False):
            pairs += 1
            value = metrics.kerns.get((left, right), 0)
            if value:
                kerned += 1
                if distance_to_grid(value * size_px / metrics.upm, 1.0) < 1e-4:
                    on_grid += 1
    return pairs, kerned, on_grid


def corpus_words(paths: Iterable[Path]) -> tuple[str, ...]:
    """Every word of the demo documents, so the corpus is the real one."""
    words: list[str] = []
    for path in paths:
        if path.is_file():
            words.extend(_WORD.findall(path.read_text(encoding="utf-8")))
    return tuple(words)


def load_all() -> list[Metrics]:
    faces: list[Metrics] = []
    for name, spec in CANDIDATES:
        path = resolve(spec)
        found = read_metrics(name, path)
        if found is None:
            print(f"  (skipped {name}: {path} is missing or lacks the alphabet)", file=sys.stderr)
            continue
        faces.append(found)
    return faces


def table(faces: Sequence[Metrics], size_px: float, words: Sequence[str]) -> None:
    print(f"\n### At {size_px:g} px body size, {len(words)} words of demo/ prose\n")
    header = (
        f"{'face':<28} {'upm':>5} {'units/px':>9} "
        f"{'adv->whole':>11} {'adv->half':>10} {'on grid':>8} "
        f"{'orig disp':>10} {'max':>6} {'gap sd':>7}"
    )
    print(header)
    print("-" * len(header))
    for face in faces:
        adv = measure_advances(face, size_px)
        org = measure_origins(face, size_px, words)
        print(
            f"{face.name:<28} {face.upm:>5} {face.upm / size_px:>9.1f} "
            f"{adv.whole:>11.3f} {adv.half:>10.3f} {adv.on_grid:>4}/{adv.total:<3} "
            f"{org.displacement_mean:>10.3f} {org.displacement_max:>6.3f} "
            f"{org.gap_error_sd:>7.3f}"
        )
    print(
        "\nadv->whole / adv->half: mean px from an advance to the nearest whole "
        "/ half pixel.\norig disp: mean px a glyph origin moves when snapped to "
        "a whole pixel, over real words.\ngap sd: sd of the error applied to "
        "gaps inside a word. Lower is more even, not better."
    )


def sweep(faces: Sequence[Metrics], words: Sequence[str], sizes: Sequence[float]) -> None:
    """
    The same faces across a ladder of sizes.

    Worth having because grid alignment is not a property of a face -- it is a
    property of a face *at a size*. A face that is poor at 16 px may be exact at
    some other size, and the demo is free to choose its body size.
    """
    print("\n### Mean origin displacement (px) when snapped to a whole pixel\n")
    header = f"{'face':<28} " + " ".join(f"{s:>6g}" for s in sizes)
    print(header)
    print("-" * len(header))
    for face in faces:
        cells = []
        for size in sizes:
            cells.append(f"{measure_origins(face, size, words).displacement_mean:>6.3f}")
        print(f"{face.name:<28} " + " ".join(cells))


def half_pixel_gain(faces: Sequence[Metrics], size_px: float, words: Sequence[str]) -> None:
    """
    What the decided half-pixel quantisation buys, per face.

    The user chose half-pixel offsets after looking at a rendered A/B. This is
    the arithmetic underneath that choice, and it is reported per face because
    the gain is not the same for all of them -- a face already near the grid has
    less to gain, and a mono face at an exact size has nothing to gain at all.
    """
    print(f"\n### What quantising to 1/2 px instead of 1 px does, at {size_px:g} px\n")
    header = (
        f"{'face':<28} {'1/1 disp':>9} {'1/2 disp':>9} {'change':>8} "
        f"{'1/1 gap sd':>11} {'1/2 gap sd':>11}"
    )
    print(header)
    print("-" * len(header))
    for face in faces:
        whole = measure_origins(face, size_px, words, step=1.0)
        half = measure_origins(face, size_px, words, step=0.5)
        change = (
            (half.displacement_mean - whole.displacement_mean) / whole.displacement_mean * 100.0
            if whole.displacement_mean
            else 0.0
        )
        print(
            f"{face.name:<28} {whole.displacement_mean:>9.3f} {half.displacement_mean:>9.3f} "
            f"{change:>7.1f}% {whole.gap_error_sd:>11.3f} {half.gap_error_sd:>11.3f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--size",
        type=float,
        action="append",
        default=None,
        help="body size in px; repeatable. Defaults to 16.",
    )
    parser.add_argument("--sweep", action="store_true", help="also print a size ladder")
    args = parser.parse_args(argv)

    sizes = args.size or [DEFAULT_SIZE_PX]
    root = Path(__file__).resolve().parent.parent
    words = corpus_words((root / "demo" / "sample.md", root / "demo" / "columns.md"))
    if not words:
        print("no demo prose found; falling back to the alphabet", file=sys.stderr)
        words = ALPHABET

    faces = load_all()
    if not faces:
        print("no candidate face could be read", file=sys.stderr)
        return 1

    for size in sizes:
        table(faces, size, words)
    half_pixel_gain(faces, sizes[0], words)
    if args.sweep:
        sweep(faces, words, (12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 20.0, 24.0, 32.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Render the font/grid comparison, instead of asserting it from font tables.

`scripts/font_grid.py` measures advances and kerns and concludes that Liberation
Serif at 18 px puts glyph origins on whole pixels where Roboto at 16 px does
not. That is arithmetic. It produces no pixels, and this project has a written
record of the lead getting four visual calls wrong -- see
`.concerns/lead--visual-standard.md`. So this script rasterises the same cases
through the same machinery the demo uses and lets the difference be looked at.

**What is faithful here, and what is not.** The glyph bitmaps are ImGui's: a
real `ImFontAtlas`, baked by stb_truetype at `floor(size + 0.5)`, read back out
of the atlas texture. The origins are computed the way `advtext` computes them
-- fontTools advances plus GPOS kerns -- and snapped the way
`advtext.backends.imgui_draw._RigidSpan.pen` snaps them: the span anchor to a
whole pixel, each glyph's offset within the span to the quantum under test.
What is *not* faithful is the compositing: this blits the baked alpha directly
rather than going through `ImDrawList` and a GPU. That is deliberate, because it
removes the renderer's bilinear filter from the picture and shows what the
snapping alone does. A full-app screenshot is `make shot`'s job.

The claim under test that matters most is the one nobody has observed: that
on-grid origins make **every instance of a letter identical**, while off-grid
origins make instances differ. The user has previously spotted two instances of
`p` rendering differently. `--report` byte-compares them.

    .venv/bin/python scripts/render_grid_compare.py
    .venv/bin/python scripts/render_grid_compare.py --zoom 8 --report
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from font_grid import Metrics, read_metrics, resolve  # noqa: E402

# The phrases the user has actually complained about, so the comparison is
# against the defect rather than against a pangram nobody has looked at.
# "difference" is the heading case where `iffe` fused into one 31 px ink run;
# "counting" and "people" are the two words they named from a 1:1 screenshot.
SAMPLES: tuple[str, ...] = (
    "counting the spaces",
    "people of difference",
    "minimum illicit",
)

# (label, path spec, size). Inconsolata is the control: 1000 upm, every advance
# exactly 500 units, so at 16 px it is exactly on the grid by construction. If
# the harness cannot show it as perfect, the harness is wrong.
CASES: tuple[tuple[str, str, float], ...] = (
    ("Roboto 16px (ships today)", "@bundle:Roboto/Roboto-Regular.ttf", 16.0),
    ("Roboto 18px", "@bundle:Roboto/Roboto-Regular.ttf", 18.0),
    (
        "Liberation Serif 18px",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        18.0,
    ),
    (
        "Nimbus Roman 18px",
        "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf",
        18.0,
    ),
    ("Inconsolata 16px (control)", "@bundle:Inconsolata-Medium.ttf", 16.0),
)


@dataclass(frozen=True)
class Baked:
    """One face baked at one size: the atlas alpha plus a glyph lookup."""

    alpha: np.ndarray
    glyphs: dict[str, tuple[np.ndarray, float, float]]
    ascent: float
    descent: float
    size: float


def bake(path: Path, size_px: float, letters: str) -> Baked:
    """
    Bake a face through a real ImGui atlas and read the glyph rasters back.

    A window needs a display; a frame does not, and neither does an atlas --
    `create_context` allocates plain memory and `ImFontAtlas` bakes on the CPU
    through stb_truetype. `docs/status.md` section 2 records that this is how the
    whole ImGui backend is testable here.
    """
    from imgui_bundle import imgui

    imgui.create_context()
    atlas = imgui.get_io().fonts
    atlas.clear()
    font = atlas.add_font_from_file_ttf(str(path), size_px)
    baked = font.get_font_baked(size_px)

    # Touch every glyph first: the 1.92 atlas is dynamic, so a glyph is only in
    # the texture once something has asked for it.
    for letter in sorted(set(letters)):
        baked.find_glyph(ord(letter))

    tex = atlas.tex_data
    pixels = tex.get_pixels_array()
    array = np.asarray(pixels, dtype=np.uint8).reshape(tex.height, tex.width, tex.bytes_per_pixel)
    # RGBA32 with the coverage in alpha; the colour channels are white.
    alpha = array[:, :, 3] if tex.bytes_per_pixel == 4 else array[:, :, 0]

    glyphs: dict[str, tuple[np.ndarray, float, float]] = {}
    for letter in sorted(set(letters)):
        glyph = baked.find_glyph(ord(letter))
        if glyph is None or not glyph.is_visible():
            continue
        u0 = int(round(glyph.u0 * tex.width))
        u1 = int(round(glyph.u1 * tex.width))
        v0 = int(round(glyph.v0 * tex.height))
        v1 = int(round(glyph.v1 * tex.height))
        glyphs[letter] = (alpha[v0:v1, u0:u1].copy(), float(glyph.x0), float(glyph.y0))
    return Baked(
        alpha=alpha,
        glyphs=glyphs,
        ascent=float(baked.ascent),
        descent=float(baked.descent),
        size=float(baked.size),
    )


def snap(value: float, quantum: float) -> float:
    """`imgui_draw.snap_px` generalised to a quantum. Pascal rounding, as there."""
    import math

    return math.floor(value / quantum + 0.5) * quantum


def origins(metrics: Metrics, text: str, size_px: float, quantum: float) -> list[float]:
    """
    Where each glyph lands, by `_RigidSpan.pen`'s rule.

    The span anchor is a whole pixel and every offset inside the span is snapped
    to `quantum`. A space closes the span -- it is glue -- so the next word opens
    a new anchor on a whole pixel, which is the behaviour the user asked to keep
    when they rejected a trial that put word-leading glyphs on a coin flip.
    """
    places: list[float] = []
    anchor = 0.0
    pen = 0.0
    previous = ""
    for index, letter in enumerate(text):
        if letter == " ":
            # Close the span: advance by a word space and re-anchor whole.
            pen += metrics.px(" ", size_px) if " " in metrics.advances else size_px * 0.25
            anchor = float(round(anchor + pen))
            pen = 0.0
            previous = ""
            places.append(float("nan"))
            continue
        if previous and index:
            pen += metrics.kern_px(previous, letter, size_px)
        places.append(anchor + snap(pen, quantum))
        pen += metrics.px(letter, size_px)
        previous = letter
    return places


def draw(baked: Baked, metrics: Metrics, text: str, size_px: float, quantum: float) -> np.ndarray:
    """Composite one line of text into an alpha canvas at snapped origins."""
    places = origins(metrics, text, size_px, quantum)
    finite = [p for p in places if p == p]
    width = int(max(finite) + size_px * 2) if finite else int(size_px)
    height = int(round(baked.ascent - baked.descent)) + 4
    canvas = np.zeros((height, width), dtype=np.uint16)
    # The top-left of the line box, NOT the baseline. `ImFontGlyph.y0` is an
    # offset from the pen position, and `add_text` takes a top-left corner --
    # `_RigidSpan` sets `top=snap_px(baseline.y - baked.ascent)` for exactly that
    # reason. Adding the ascent here as well put every glyph a full ascent below
    # the canvas, every blit failed its bounds check, and the canvas came out
    # empty while the identity report cheerfully compared blank crops and
    # declared them identical. See `_assert_has_ink`.
    top = 2.0
    for letter, place in zip(text, places, strict=False):
        if place != place or letter not in baked.glyphs:
            continue
        bitmap, x0, y0 = baked.glyphs[letter]
        # The x offset is fractional under a fractional quantum; the bitmap is
        # not. Placing it at the floor and carrying no phase is exactly what
        # ImGui does after `IM_TRUNC`, and is why the half-pixel variant needs
        # `ImDrawListFlags_TextNoPixelSnap` to mean anything on a GPU. Here the
        # fraction is resolved by a two-tap horizontal blend, which is what the
        # bilinear filter would do.
        x = place + x0
        y = top + y0
        left = int(np.floor(x))
        frac = x - left
        rows, cols = bitmap.shape
        row0 = int(round(y))
        if row0 < 0 or row0 + rows > height:
            continue
        for shift, weight in ((0, 1.0 - frac), (1, frac)):
            if weight <= 0.0:
                continue
            lo = left + shift
            if lo < 0 or lo + cols > width:
                continue
            canvas[row0 : row0 + rows, lo : lo + cols] += (
                bitmap.astype(np.float64) * weight
            ).astype(np.uint16)
    return np.clip(canvas, 0, 255).astype(np.uint8)


def _assert_has_ink(canvas: np.ndarray, label: str, text: str) -> None:
    """
    Refuse to report on a blank canvas.

    This exists because the first version of this script rendered NOTHING -- a
    sign error put every glyph an ascent below the canvas, every blit failed its
    bounds check, and `instance_identity` compared blank crops and reported that
    every letter rendered identically in every case. The conclusion it produced
    was the one the lead was hoping for, which is the worst way for a fixture to
    fail.

    `docs/status.md` section 5 catalogues five families of tests in this project
    that could not fail. The house rule it derives is "attack the fixture, not
    the assertion", and this is that rule applied to the fixture that caught the
    lead out.
    """
    ink = int(canvas.sum())
    if ink == 0:
        raise AssertionError(
            f"{label}: rendered {text!r} and got a blank canvas. Every number "
            "derived from this image would be an artefact of the bug, not a "
            "measurement of the font."
        )


def instance_identity(
    canvas: np.ndarray, metrics: Metrics, text: str, size_px: float, quantum: float, baked: Baked
) -> dict[str, tuple[int, int]]:
    """
    For each letter appearing more than once, how many DISTINCT rasters it got.

    This is the claim the lead could not support from font tables: that on-grid
    origins make every instance of a letter identical.

    Each instance is rasterised ALONE, at the position the full line gave it,
    and the isolated strips are compared. Cropping the finished line instead
    compares the letter *plus whatever its neighbours put in the window*, so
    `e` in "people" and `e` in "difference" come out different for reasons that
    have nothing to do with the grid. That version reported the on-grid control
    (Inconsolata at 16 px, every advance exactly 8.000 px) as rendering five
    distinct `i`s, which is arithmetically impossible and is how the bug was
    caught.

    `canvas` is taken only for its width, so the strips line up with the image
    the reader is looking at.
    """
    places = origins(metrics, text, size_px, quantum)
    width = canvas.shape[1]
    seen: dict[str, list[bytes]] = {}
    for letter, place in zip(text, places, strict=False):
        if place != place or letter not in baked.glyphs:
            continue
        bitmap, x0, _ = baked.glyphs[letter]
        rows, cols = bitmap.shape
        x = place + x0
        left = int(np.floor(x))
        frac = x - left
        if left < 0 or left + cols + 1 > width:
            continue
        # One glyph, alone, at its own subpixel phase -- the same two-tap blend
        # `draw` uses, so the strip is what this instance contributes to the
        # line and nothing else.
        strip = np.zeros((rows, cols + 2), dtype=np.float64)
        strip[:, 0:cols] += bitmap * (1.0 - frac)
        strip[:, 1 : cols + 1] += bitmap * frac
        seen.setdefault(letter, []).append(np.clip(strip, 0, 255).astype(np.uint8).tobytes())
    return {
        letter: (len(set(crops)), len(crops)) for letter, crops in seen.items() if len(crops) > 1
    }


def magnify(image: np.ndarray, zoom: int) -> np.ndarray:
    """Nearest-neighbour, so a pixel stays a pixel. `numpy.repeat`, per the house method."""
    return np.repeat(np.repeat(image, zoom, axis=0), zoom, axis=1)


def write_png(path: Path, image: np.ndarray, note: str) -> None:
    """
    Ink on paper, not white on black -- the demo sets dark ink on a light page,
    and a reader judging letter fit on inverted text is judging a different
    thing. `visual_diff.encode_png` is the project's encoder; a second one here
    would be a second thing to be wrong.

    The `tEXt` note is what stops these from becoming another set of unlabelled
    PNGs of unknown provenance, which `.concerns/lead--visual-standard.md`
    records as a defect this project has already shipped once.
    """
    from visual_diff import encode_png

    ink = 255 - image
    rgb = np.repeat(ink[:, :, None], 3, axis=2)
    path.write_bytes(encode_png(rgb, {"advtext-grid-case": note}))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zoom", type=int, default=6)
    parser.add_argument("--out", type=Path, default=Path("artifacts/gridfont"))
    parser.add_argument("--report", action="store_true", help="print the identity table")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    letters = "".join(sorted(set("".join(SAMPLES))))

    rows: list[tuple[str, np.ndarray]] = []
    report: list[str] = []
    for label, spec, size in CASES:
        path = resolve(spec)
        metrics = read_metrics(label, path)
        if metrics is None:
            print(f"skipped {label}: {path} missing", file=sys.stderr)
            continue
        baked = bake(path, size, letters + " ")
        for quantum, quantum_name in ((1.0, "whole"), (0.5, "half")):
            panels = []
            for sample in SAMPLES:
                canvas = draw(baked, metrics, sample, size, quantum)
                _assert_has_ink(canvas, f"{label} [{quantum_name}]", sample)
                panels.append(canvas)
                if args.report:
                    identity = instance_identity(canvas, metrics, sample, size, quantum, baked)
                    for letter, (distinct, total) in sorted(identity.items()):
                        if distinct > 1:
                            report.append(
                                f"{label:<28} {quantum_name:<5} {sample[:20]:<21} "
                                f"'{letter}' {distinct} distinct of {total}"
                            )
            width = max(p.shape[1] for p in panels)
            stack = np.zeros((sum(p.shape[0] + 2 for p in panels), width), dtype=np.uint8)
            y = 0
            for panel in panels:
                stack[y : y + panel.shape[0], : panel.shape[1]] = panel
                y += panel.shape[0] + 2
            rows.append((f"{label} [{quantum_name}-pixel]", stack))

    if not rows:
        print("nothing rendered", file=sys.stderr)
        return 1

    for (
        label,
        image,
    ) in rows:
        slug = label.lower().replace(" ", "-").replace("(", "").replace(")", "")
        slug = slug.replace("[", "").replace("]", "")
        write_png(args.out / f"{slug}.png", magnify(image, args.zoom), label)

    order = " | ".join(label for label, _ in rows)
    width = max(image.shape[1] for _, image in rows)
    gap = 6
    sheet = np.zeros((sum(image.shape[0] + gap for _, image in rows), width), dtype=np.uint8)
    y = 0
    for _, image in rows:
        sheet[y : y + image.shape[0], : image.shape[1]] = image
        y += image.shape[0] + gap
    write_png(args.out / f"all-cases-{args.zoom}x.png", magnify(sheet, args.zoom), order)
    write_png(args.out / "all-cases-1x.png", sheet, order)

    print(f"wrote {len(rows) + 2} files to {args.out}")
    print("\norder of the stacked sheet, top to bottom:")
    for label, _ in rows:
        print(f"  {label}")
    if report:
        print("\n### letters whose instances did NOT render identically\n")
        for line in report:
            print("  " + line)
    elif args.report:
        print("\nevery repeated letter rendered identically in every case")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ----------------------------------------------------------------------------
# Page mode
# ----------------------------------------------------------------------------
#
# Word crops answer "which glyph pair moved". They do not answer "does this read
# better as a page", and that is the question a face change actually turns on.
# So this sets real prose at a real measure and lets it be looked at at 1:1.


def wrap_justified(
    metrics: Metrics, words: Sequence[str], size_px: float, measure_px: float
) -> list[tuple[list[str], float]]:
    """
    Greedy first-fit lines, each returned with the interword space it needs.

    **This is NOT `advtext`'s line breaker** and must not be read as a sample of
    it. `advtext.linebreak` runs Knuth's total-fit pass and picks the breaking
    with the fewest demerits over the whole paragraph; this fills each line and
    hopes, which is the greedy control `tests/test_linebreak.py` exists to prove
    is worse. It is used here because the quantity under test is letter fit
    *inside* a word, which is a function of the characters and their kerns and
    is identical whichever breaker chose the breaks.

    The space returned is the justified one: the slack shared out over the gaps,
    which is what makes the right edge straight and what makes a page look like
    a page rather than like a ragged sample.
    """
    natural = metrics.px(" ", size_px) if " " in metrics.advances else size_px * 0.25
    lines: list[tuple[list[str], float]] = []
    current: list[str] = []
    ink = 0.0
    for word in words:
        width = sum(metrics.px(c, size_px) for c in word if c in metrics.advances)
        if current and ink + natural * len(current) + width > measure_px:
            gaps = len(current) - 1
            space = (measure_px - ink) / gaps if gaps else natural
            lines.append((current, space))
            current, ink = [word], width
        else:
            current.append(word)
            ink += width
    if current:
        lines.append((current, natural))
    return lines


def draw_page(
    baked: Baked,
    metrics: Metrics,
    words: Sequence[str],
    size_px: float,
    measure_px: float,
    quantum: float,
    leading: float,
) -> np.ndarray:
    """A block of set prose, each word its own rigid span on a whole-pixel anchor."""
    lines = wrap_justified(metrics, words, size_px, measure_px)
    height = int(len(lines) * leading + size_px * 2)
    width = int(measure_px + size_px)
    canvas = np.zeros((height, width), dtype=np.uint16)

    for row, (line, space) in enumerate(lines):
        x = 0.0
        y = size_px * 0.5 + row * leading
        for word in line:
            # A word is one rigid span: its anchor is snapped WHOLE, and every
            # glyph inside it is placed by an offset snapped to `quantum`. This
            # is `_RigidSpan`'s rule, and the whole anchor is what the user
            # insisted on after seeing a trial that fuzzed word-leading glyphs.
            anchor = float(np.floor(x + 0.5))
            pen = 0.0
            previous = ""
            for letter in word:
                if letter not in baked.glyphs:
                    if letter in metrics.advances:
                        pen += metrics.px(letter, size_px)
                    previous = letter
                    continue
                if previous:
                    pen += metrics.kern_px(previous, letter, size_px)
                place = anchor + snap(pen, quantum)
                bitmap, x0, y0 = baked.glyphs[letter]
                gx = place + x0
                left = int(np.floor(gx))
                frac = gx - left
                top = int(round(y + y0))
                rows, cols = bitmap.shape
                if left < 0 or left + cols + 1 > width or top < 0 or top + rows > height:
                    pen += metrics.px(letter, size_px)
                    previous = letter
                    continue
                for shift, weight in ((0, 1.0 - frac), (1, frac)):
                    if weight > 0.0:
                        canvas[top : top + rows, left + shift : left + shift + cols] += (
                            bitmap.astype(np.float64) * weight
                        ).astype(np.uint16)
                pen += metrics.px(letter, size_px)
                previous = letter
            x = anchor + pen + space
    return np.clip(canvas, 0, 255).astype(np.uint8)

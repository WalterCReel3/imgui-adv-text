"""
Measure the disagreement between ImGui's glyph advances and fontTools'.

`docs/decisions.md` section 4 records this as a known, unverified risk and says a
verify script "must measure the disagreement when a display exists; until it
runs, the per-glyph decision is a hedge and not a measurement". This is that
script.

**No display is required, and that is the first thing this script established.**
An ImGui *window* cannot be opened in this environment, but nothing here opens
one. `imgui.create_context()` allocates plain memory, `ImFontAtlas` bakes glyphs
on the CPU through stb_truetype, and `ImFontBaked.get_char_advance` reads the
result out of a vector. A GPU is needed to *upload* an atlas texture, not to
build one. So the measurement `docs/decisions.md` deferred to "when a display
exists" is available now, and the hedge can be replaced by a number.

**What the numbers say.** ImGui's advances are integers -- it quantises every
advance to a whole pixel, which `docs/decisions.md` predicted. But the
disagreement is not rounding. At a nominal 16px, Roboto's advances come back
about 15% *smaller* than fontTools' for the same nominal size, and the error is
systematic rather than random, so it accumulates instead of cancelling: over a
44-character line it reaches 42px, which is wider than two characters.

The cause is that "size" names two different lengths. `advtext.fontlib` scales a
face by `size / unitsPerEm`, so a size of 16 makes the *em* 16px. ImGui bakes
through stb_truetype, which scales by pixel *height* -- roughly
`size / (hhea.ascender - hhea.descender)`. For Roboto those denominators are 2048
and 2400, and 2048/2400 is 0.853. `advtext.fontlib` already reads vertical
metrics from `hhea` specifically so it would agree with ImGui; matching the table
was necessary and was not sufficient, because the denominator is the other half.

**The correction, stated as what was measured rather than as a mechanism.**
Asking ImGui for `metrics.ascent + metrics.descent` pixels instead of `size`
pixels collapses the drift:

    face    nominal   requested   worst drift over 44 chars
    prose     16.0       16.0                42.3750 px
    prose     16.0       18.7500              1.0312 px
    prose     32.0       32.0               100.7500 px
    prose     32.0       37.5000              3.2500 px

`ascent + descent` is the right expression to reach for because `fontlib` stores
both from `hhea` and stores `descent` as a positive number, so their sum is
exactly `(ascender - descender)` scaled into pixels -- the denominator ImGui
uses, expressed in the units the caller already has. No new font API is needed.

**Deliberately out of scope: deriving ImGui's exact per-glyph rounding rule.**
The residual after correction is about 1px per 44 characters and it is not
explained by any single rule this script tried -- neither `round` nor `ceil` of
the scaled advance reproduces every glyph, and ImGui additionally quantises the
*requested* size to an integer before baking, so asking for 18.75 bakes at 19.
Reverse-engineering that belongs in ImGui's source, not here. This script
measures the disagreement and checks that a correction shrinks it; it does not
claim to model it. Treat the residual as the floor that per-glyph positioning
exists to absorb, which is the conclusion `docs/decisions.md` already reached by
a different route.

The module splits into a pure half and an ImGui half on purpose. Everything that
does arithmetic on two advance tables is pure, importable without ImGui, and
covered by `tests/test_verify_advances.py`. The ImGui half is the smallest shell
that can produce the second table.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advtext import fontlib
from advtext.fontmetrics import Face, FontMetrics

__all__ = [
    "DEFAULT_SAMPLE",
    "DEFAULT_SIZES_PX",
    "Disagreement",
    "Drift",
    "accumulated_drift",
    "compare_advances",
    "format_report",
    "imgui_advances",
    "main",
    "uniform_ratio",
]

Advances = Mapping[int, float]
"""
One face at one size: codepoint to horizontal advance in device pixels.

A plain mapping rather than a class because both producers already have one and
neither should have to learn a type to be compared.
"""

DEFAULT_SAMPLE = "The quick brown fox jumps over the lazy dog."
"""
The string drift is accumulated over.

A pangram, so every letter contributes, and long enough that a systematic
per-glyph error has somewhere to accumulate. Drift is the number that matters
and a one-word sample cannot show it.
"""

DEFAULT_SIZES_PX: tuple[float, ...] = (16.0, 32.0)
"""
Body size and a heading size. The disagreement scales with size, so one sample
cannot distinguish a fixed offset from a proportional one.
"""


@dataclass(frozen=True, slots=True)
class Disagreement:
    """
    One codepoint whose two advances differ.
    """

    codepoint: int
    ours_px: float
    theirs_px: float

    @property
    def delta_px(self) -> float:
        """
        Theirs minus ours. Negative means ImGui advances less than we laid out.
        """
        return self.theirs_px - self.ours_px


@dataclass(frozen=True, slots=True)
class Drift:
    """
    Accumulated disagreement along a string.

    `worst_px` is the headline and `final_px` is not. The visible error at a
    glyph is the sum of every delta before it, so what a reader sees is the
    largest that running sum ever gets -- which a total can hide, because
    opposite-signed deltas cancel in a total and do not cancel on screen.
    """

    worst_px: float
    final_px: float
    compared: int
    skipped: int


def compare_advances(
    ours: Advances, theirs: Advances, *, tolerance_px: float = 0.0
) -> tuple[Disagreement, ...]:
    """
    Codepoints present in both tables whose advances differ by more than `tolerance_px`.

    Codepoints missing from either side are not disagreements -- they are a
    coverage question, which is a different question, and reporting them here
    would bury the arithmetic under glyphs one side simply does not have.
    Ordered by codepoint so two runs diff cleanly.
    """
    shared = sorted(set(ours) & set(theirs))
    return tuple(
        Disagreement(codepoint=cp, ours_px=ours[cp], theirs_px=theirs[cp])
        for cp in shared
        if abs(theirs[cp] - ours[cp]) > tolerance_px
    )


def accumulated_drift(text: str, ours: Advances, theirs: Advances) -> Drift:
    """
    How far apart the two tables walk across `text`.

    A character absent from either table is skipped rather than guessed at, and
    counted: a drift figure computed over half the string is not comparable with
    one computed over all of it, and `skipped` is what lets a reader tell.
    """
    running = 0.0
    worst = 0.0
    compared = 0
    skipped = 0
    for character in text:
        codepoint = ord(character)
        if codepoint not in ours or codepoint not in theirs:
            skipped += 1
            continue
        running += theirs[codepoint] - ours[codepoint]
        worst = max(worst, abs(running))
        compared += 1
    return Drift(worst_px=worst, final_px=running, compared=compared, skipped=skipped)


def uniform_ratio(
    ours: Advances, theirs: Advances, *, relative_tolerance: float = 1e-3
) -> float | None:
    """
    The single constant `theirs / ours` explaining every pair, or `None`.

    A constant ratio is a different diagnosis from scattered rounding: it means
    the two sides disagree about a *unit*, not about a decimal place. It is worth
    separating because `docs/decisions.md` section 5 names exactly one such
    hazard -- if ImGui treated its coordinates as points rather than pixels the
    whole layer would be wrong by 96/72, and a ratio near 1.333 is that bug
    announcing itself.

    Pairs whose `ours` is zero are skipped: a zero-width glyph carries no ratio.
    """
    ratios = [theirs[cp] / ours[cp] for cp in sorted(set(ours) & set(theirs)) if ours[cp] != 0.0]
    if not ratios:
        return None
    mean = statistics.fmean(ratios)
    if mean == 0.0:
        return None
    if any(abs(ratio - mean) > abs(mean) * relative_tolerance for ratio in ratios):
        return None
    return mean


def format_report(
    label: str, drift: Drift, disagreements: tuple[Disagreement, ...], ratio: float | None
) -> str:
    """
    One human-readable block per face and size.
    """
    lines = [
        f"{label}",
        f"  glyphs compared        {drift.compared} ({drift.skipped} skipped)",
        f"  disagreeing glyphs     {len(disagreements)}",
        f"  worst accumulated drift {drift.worst_px:.4f} px",
        f"  drift at end of sample  {drift.final_px:.4f} px",
    ]
    if ratio is not None and ratio == 1.0:
        lines.append("  uniform ratio           1.0 -- the two tables agree exactly")
    elif ratio is not None:
        lines.append(f"  uniform ratio detected  {ratio:.6f} -- a unit disagreement, not rounding")
    if disagreements:
        worst = max(disagreements, key=lambda d: abs(d.delta_px))
        lines.append(
            f"  worst single glyph      U+{worst.codepoint:04X} "
            f"ours={worst.ours_px:.4f} imgui={worst.theirs_px:.4f} "
            f"delta={worst.delta_px:+.4f} px"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------------
# The ImGui half. Needs imgui-bundle but not a display, and not a window.
# --------------------------------------------------------------------------------


def imgui_advances(face: Face, size_px: float, codepoints: Iterable[int]) -> dict[int, float]:
    """
    ImGui's own advance for each codepoint, in device pixels.

    Imports ImGui locally so the pure half of this module stays importable, and
    its tests collectable, in an environment with no imgui-bundle at all.

    Creating a context and baking a font opens nothing and draws nothing. The
    context is deliberately not destroyed: this is a one-shot script, and
    `ImFontBaked` pointers are documented as valid only for the current frame, so
    releasing the atlas underneath the values we just read buys nothing.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    font = imgui.get_io().fonts.add_font_from_file_ttf(str(fontlib.font_file(face)), size_px)
    baked = font.get_font_baked(size_px)
    return {cp: baked.get_char_advance(cp) for cp in codepoints}


def _our_advances(metrics: FontMetrics, codepoints: Iterable[int]) -> dict[int, float]:
    """
    The advances the layout core actually used, for the codepoints the face has.
    """
    return {cp: metrics.advance(cp) for cp in codepoints if metrics.has(cp)}


def main(argv: list[str] | None = None) -> int:
    """
    Report the disagreement for each face at each size, naive and corrected.
    """
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.strip().splitlines()[0])
    parser.add_argument("--sample", default=DEFAULT_SAMPLE, help="string drift is measured over")
    parser.add_argument(
        "--size",
        type=float,
        action="append",
        dest="sizes",
        help="a device-pixel size to test; repeatable. Defaults to 16 and 32.",
    )
    parser.add_argument(
        "--tolerance-px",
        type=float,
        default=0.0,
        help="advances closer than this are not counted as disagreeing",
    )
    args = parser.parse_args(argv)
    sizes: tuple[float, ...] = tuple(args.sizes) if args.sizes else DEFAULT_SIZES_PX
    sample: str = args.sample
    codepoints = sorted({ord(character) for character in sample})

    print(f"sample: {sample!r} ({len(sample)} characters)")
    for face in Face:
        for size in sizes:
            metrics = fontlib.metrics(face, size)
            ours = _our_advances(metrics, codepoints)
            if not ours:
                print(f"\n{face.value} at {size:g}px: face covers none of the sample")
                continue
            corrected = metrics.ascent + metrics.descent
            for label, requested in (("naive", size), ("corrected", corrected)):
                theirs = imgui_advances(face, requested, ours)
                print()
                print(
                    format_report(
                        f"{face.value} at {size:g}px, {label} "
                        f"(requested {requested:.4f}px of ImGui)",
                        accumulated_drift(sample, ours, theirs),
                        compare_advances(ours, theirs, tolerance_px=args.tolerance_px),
                        uniform_ratio(ours, theirs),
                    )
                )
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

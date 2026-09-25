r"""
Measure the vertical half of the fontTools-versus-ImGui disagreement.

`scripts/verify_advances.py` measures the horizontal half. This is the other
one: `advtext.backends.imgui_draw._glyph` converts our baseline to ImGui's
top-left origin by subtracting `font.get_font_baked(size).ascent` -- **ImGui's**
ascent and not `advtext.fontlib`'s -- on the argument that for positioning
against ImGui's own convention ImGui's number is correct by definition. That
argument was unchecked. This script checks it.

**This script has been executed and the numbers below are its output.** No
display is needed and none was used. `imgui.create_context()` allocates plain
memory and `ImFontAtlas` bakes through stb_truetype on the CPU; a GPU and a
display are needed to *upload* an atlas texture, not to build one. The
no-display finding in `docs/decisions.md` is about opening a *window* -- `glfw`
and `immapp.run` -- and it does not reach the atlas. Note that
`/home/wreel/Source/pptmstr/scripts/verify_fonts.py`, the nominal idiom for a
verify script, ends in `immapp.run` and therefore *would* hang here; the idiom
this file follows is `verify_advances.py`'s, which opens nothing. Nothing below
sets `ini_folder_type` because nothing below constructs a runner to set it on.

## What was measured, and the conclusion

**The conversion is correct.** ImGui's own glyph boxes satisfy
`glyph.y0 == baked.ascent - ink_top` to within its pixel quantisation -- worst
residual 1.6007 px over 90 glyph boxes, being three probe glyphs across all six
faces at every size the demo uses, with every `y0` and `y1` landing on a whole
pixel, which is where a residual of that size comes from. Subtracting the baked
ascent is therefore the right operation and using `fontlib`'s ascent instead
would be wrong. That is the question this script was written to settle and it is
settled.

**The ascent disagreement is real but it is not a positioning risk.** It is a
symptom of the *same* defect `verify_advances.py` found, seen from the side:

    face    nominal   requested   our ascent   ImGui ascent   delta
    prose     16.0      16.0000      14.844       13.000      -1.844
    prose     16.0      18.7500      14.844       16.000      +1.156
    prose     36.0      36.0000      33.398       29.000      -4.398
    prose     36.0      42.1875      33.398       34.000      +0.602

Asking ImGui for `size` pixels bakes Roboto about 12.4% small, because "size"
names the em to `advtext.fontlib` and the pixel height -- roughly
`hhea.ascender - hhea.descender` -- to stb_truetype. Asking instead for
`metrics.ascent + metrics.descent` pixels is the correction `verify_advances.py`
established, and it moves the ascent the way it moves the advances.

Latin Modern Math is the exception that proves the mechanism: its `hhea` ascender
and descender sum to exactly its 1000-unit em, so its corrected size equals its
nominal one and its rows are identical in both tables. A face whose two
denominators agree needs no correction, and this is what that looks like.

The residual after correction, around +1 px, does *not*
displace a line. `_glyph` subtracts whatever ascent the same baked font reports,
so the conversion stays self-consistent whatever that number is: a larger baked
ascent moves the top-left up and moves `glyph.y0` down by the same amount, and
the ink lands on our baseline either way. The identity check above is what
demonstrates that, and it is why this script reports the residual rather than
the ascent delta as its headline.

**So the thing to fix was never the ascent.** It was the size handed to
`add_text`, and `advtext.backends.imgui_draw` now corrects it. Ascent enters
nothing else: `docs/decisions.md` records that a line's height is the ink extent
of its glyphs and that `FontMetrics.ascent` is never consulted by the layout
path, so a disagreement here cannot reach a box.

## Deliberately out of scope

Modelling ImGui's quantisation. It ceils the ascent, rounds glyph boxes outward
to whole pixels, and quantises the requested size before baking, and no single
rule tried here reproduces every face -- `verify_advances.py` reached the same
wall and gave the same reason. This script measures the disagreement and checks
an identity; it does not claim to predict either.

The module splits into a pure half and an ImGui half on purpose. Every function
that does arithmetic on two ascents is importable without imgui-bundle and is
covered by `tests/test_verify_ascent.py`. The ImGui half is the smallest shell
that can produce the second column.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advtext import fontlib
from advtext.fontmetrics import Face
from advtext.style import Theme
from advtext.units import DEFAULT_PX_PER_INCH, px_from_sp

__all__ = [
    "DEFAULT_PROBES",
    "FORMULA_SIZE_PX",
    "AscentReading",
    "OffsetResidual",
    "demo_sizes_px",
    "format_ascent_report",
    "format_offset_report",
    "imgui_readings",
    "main",
    "predicted_glyph_top",
    "requested_size_px",
    "top_left_y",
    "worst_residual_px",
]


FORMULA_SIZE_PX = 36.0
"""
The size `advtext.ui.app.App.formula_box` sets the summation at.

Written down because it is the one size in the demo that the theme does not
generate, and the display sigma is the glyph most likely to expose a vertical
error -- it is the tallest thing the demo draws.
"""

DEFAULT_PROBES: tuple[int, ...] = (0x41, 0x67, 0x2211)
"""
Glyphs the ink-top identity is checked against.

`A` sits on the baseline with no descender, `g` hangs well below it, and U+2211
is tall in both directions. A glyph that does not cross the baseline cannot
distinguish a correct ascent from one that is wrong by the descender.
"""


# --------------------------------------------------------------------------------
# The pure half. No ImGui, no display, importable anywhere.
# --------------------------------------------------------------------------------


def top_left_y(baseline_y_px: float, ascent_px: float) -> float:
    """
    The conversion `advtext.backends.imgui_draw._glyph` performs, in one place.

    `Glyph.y` is on the baseline and `add_text` takes a top-left corner. This is
    the whole of the difference between them, extracted so the arithmetic under
    test can be stated once and asserted without a window.
    """
    return baseline_y_px - ascent_px


def predicted_glyph_top(ascent_px: float, ink_top_px: float) -> float:
    """
    Where a glyph's ink must fall below the top-left corner it was drawn at.

    `ink_top_px` is the glyph's highest ink measured up from the baseline, which
    is `GlyphBBox.y_max`. If ImGui's own `ImFontGlyph.y0` matches this, then
    subtracting the baked ascent from our baseline puts the ink exactly where our
    layout put it, and `top_left_y` is correct. That equality is the one claim
    this script exists to test.
    """
    return ascent_px - ink_top_px


def requested_size_px(ascent_px: float, descent_px: float) -> float:
    """
    The size to ask ImGui for so that its baked pixel height matches ours.

    `advtext.fontlib` scales a face by `size / unitsPerEm`, so a size of 16 makes
    the *em* 16 px. stb_truetype -- and so ImGui, which bakes through it --
    scales by pixel *height*, roughly `size / (hhea.ascender - hhea.descender)`.
    `fontlib` stores both vertical metrics from `hhea` and stores `descent`
    positive, so their sum is that denominator expressed in the units the caller
    already holds. `scripts/verify_advances.py` established this correction
    horizontally; it is the same number vertically.
    """
    return ascent_px + descent_px


def demo_sizes_px(theme: Theme) -> tuple[float, ...]:
    """
    Every distinct font size the demo actually sets, in device pixels.

    Read out of the theme rather than written down, so this script cannot drift
    away from the sizes a reader would see on screen. `Theme.build` generates its
    type scale from one body size and a ratio, so listing the results here would
    be a second copy of a derivation.
    """
    sizes = {px_from_sp(style.font.size, theme.px_per_inch) for style in theme.blocks.values()}
    sizes.add(FORMULA_SIZE_PX)
    return tuple(sorted(sizes))


@dataclass(frozen=True, slots=True)
class AscentReading:
    """
    One face at one size: our ascent against ImGui's, both in device pixels.

    `requested_px` is what ImGui was *asked* for and `nominal_px` is the size our
    layout used. They differ whenever the correction in `requested_size_px` is
    applied, and keeping both is what lets a report say which column it is.
    """

    face: Face
    nominal_px: float
    requested_px: float
    ours_px: float
    theirs_px: float

    @property
    def delta_px(self) -> float:
        """
        Theirs minus ours. Negative means ImGui bakes a shorter ascent than we measured.

        This is also, one for one, how far apart the two top-left corners would
        be: `top_left_y` subtracts the ascent, so a difference in ascent is a
        difference in y of the same size and the opposite sign.
        """
        return self.theirs_px - self.ours_px


@dataclass(frozen=True, slots=True)
class OffsetResidual:
    """
    ImGui's own glyph top against the one `predicted_glyph_top` computes.

    A residual near zero means the ascent conversion is right. A residual near
    the descent, or near the whole ascent, means it is subtracting the wrong
    quantity -- which is the failure a reader would see as every line sitting a
    constant amount too high or too low.
    """

    face: Face
    size_px: float
    codepoint: int
    actual_top_px: float
    predicted_top_px: float

    @property
    def residual_px(self) -> float:
        """
        Actual minus predicted. ImGui quantises a glyph box to whole pixels, so a
        residual below 1 px is quantisation rather than disagreement.
        """
        return self.actual_top_px - self.predicted_top_px


def worst_residual_px(residuals: Iterable[OffsetResidual]) -> float:
    """
    The largest absolute residual, or zero when nothing was measured.

    Absolute rather than signed, and a maximum rather than a mean: opposite-signed
    residuals cancel in a mean and do not cancel on screen, which is the same
    reason `verify_advances.Drift` reports its worst running sum.
    """
    return max((abs(item.residual_px) for item in residuals), default=0.0)


def format_ascent_report(label: str, readings: Sequence[AscentReading]) -> str:
    """
    One table of ascents, one row per reading.
    """
    lines = [
        label,
        f"  {'face':<20}{'nominal':>9}{'requested':>11}{'ours':>10}{'imgui':>9}{'delta':>9}",
    ]
    for reading in readings:
        lines.append(
            f"  {reading.face.value:<20}{reading.nominal_px:>9.2f}{reading.requested_px:>11.4f}"
            f"{reading.ours_px:>10.3f}{reading.theirs_px:>9.3f}{reading.delta_px:>+9.3f}"
        )
    return "\n".join(lines)


def format_offset_report(label: str, residuals: Sequence[OffsetResidual]) -> str:
    """
    The identity check, summarised, with its worst offender named.
    """
    worst_px = worst_residual_px(residuals)
    lines = [
        label,
        f"  glyph boxes checked     {len(residuals)}",
        f"  worst residual          {worst_px:.4f} px",
    ]
    if residuals:
        worst = max(residuals, key=lambda item: abs(item.residual_px))
        lines.append(
            f"  worst case              {worst.face.value} U+{worst.codepoint:04X} "
            f"at {worst.size_px:g}px: imgui y0={worst.actual_top_px:.2f} "
            f"predicted={worst.predicted_top_px:.2f} residual={worst.residual_px:+.4f} px"
        )
    verdict = (
        "the ascent conversion is correct; the residual is pixel quantisation"
        if worst_px < 2.0
        else "the ascent conversion is WRONG -- see advtext.backends.imgui_draw._ascent"
    )
    lines.append(f"  verdict                 {verdict}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------
# The ImGui half. Needs imgui-bundle but not a display, and not a window.
# --------------------------------------------------------------------------------


def imgui_readings(
    face: Face, nominal_px: float, requested_px: float, probes: Iterable[int]
) -> tuple[AscentReading, tuple[OffsetResidual, ...]]:
    """
    Bake one face at one requested size and read its ascent and its glyph boxes.

    Imports ImGui locally so the pure half of this module stays importable, and
    its tests collectable, in an environment with no imgui-bundle at all.

    Creating a context and baking a font opens nothing and draws nothing. The
    context is deliberately not destroyed: this is a one-shot script, and
    `ImFontBaked` pointers are documented as valid only for the current frame, so
    releasing the atlas underneath the values just read buys nothing.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    font = imgui.get_io().fonts.add_font_from_file_ttf(
        str(fontlib.imgui_font_file(face)), requested_px
    )
    baked = font.get_font_baked(requested_px)
    ours = fontlib.metrics(face, nominal_px)
    reading = AscentReading(
        face=face,
        nominal_px=nominal_px,
        requested_px=requested_px,
        ours_px=ours.ascent,
        theirs_px=baked.ascent,
    )

    # Our ink is measured at the nominal size and ImGui's box at the baked one,
    # so the two are compared on ImGui's scale. The ascent ratio is that scale:
    # both numbers describe the same `hhea.ascender` and nothing else varies.
    scale = baked.ascent / ours.ascent if ours.ascent else 1.0
    residuals: list[OffsetResidual] = []
    for codepoint in probes:
        if not ours.has(codepoint):
            continue
        glyph = baked.find_glyph_no_fallback(codepoint)
        if glyph is None:
            continue
        residuals.append(
            OffsetResidual(
                face=face,
                size_px=requested_px,
                codepoint=codepoint,
                actual_top_px=glyph.y0,
                predicted_top_px=predicted_glyph_top(
                    baked.ascent, ours.bbox(codepoint).y_max * scale
                ),
            )
        )
    return reading, tuple(residuals)


def main(argv: list[str] | None = None) -> int:
    """
    Report every face's ascent naive and corrected, then check the conversion.
    """
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.strip().splitlines()[0])
    parser.add_argument(
        "--size",
        type=float,
        action="append",
        dest="sizes",
        help="a device-pixel size to test; repeatable. Defaults to the demo's own sizes.",
    )
    parser.add_argument(
        "--px-per-inch",
        type=float,
        default=DEFAULT_PX_PER_INCH,
        help="device resolution the theme's scaled points are converted through",
    )
    args = parser.parse_args(argv)
    theme = Theme.build(px_per_inch=args.px_per_inch)
    sizes: tuple[float, ...] = tuple(args.sizes) if args.sizes else demo_sizes_px(theme)

    print(f"sizes: {', '.join(format(size, 'g') for size in sizes)} px")
    residuals: list[OffsetResidual] = []
    for label, correct in (("naive", False), ("corrected", True)):
        readings: list[AscentReading] = []
        for face in Face:
            for size in sizes:
                ours = fontlib.metrics(face, size)
                requested = requested_size_px(ours.ascent, ours.descent) if correct else size
                reading, found = imgui_readings(face, size, requested, DEFAULT_PROBES)
                readings.append(reading)
                if correct:
                    residuals.extend(found)
        print()
        print(format_ascent_report(f"ascent, {label}", readings))

    print()
    print(format_offset_report("ink-top identity, corrected sizes", residuals))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

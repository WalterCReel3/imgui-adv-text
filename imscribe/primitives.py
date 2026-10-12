r"""
The two vocabularies a theme is written in: lengths in scaled points, and faces by role.

Everything here was `imscribe.units`' or `imscribe.fontmetrics`' until
2026-10-11 and **both import it back**: `imscribe.units.sp_from_px` is this
module's `sp_from_px`, `imscribe.fontmetrics.Face` is this module's `Face`,
the same objects, and no caller of either had to change
(`tests/test_typeset_closure.py` holds the identities).

It is its own module because of what else those two hold. `imscribe.units` is
also TeX's glue orders and the running-rule sentinel, and
`imscribe.fontmetrics` is the metrics protocols of the Python layout core:
they are part of the reference core, which is kept for the SVG litmus
renderer and for nothing else. `imscribe.theme` needs a length and a face to
say what a heading looks like, and so does everything that sets text through
imtypeset. Taking them from here is what lets all of that load **no** module
of the reference core, at import or when a theme is built.

This module imports nothing of imscribe, and must not.

## Lengths

**Integer scaled points.** A scaled point is 2^-16 pt, so a dimension is a
plain `int` and one printer's point is `UNITY` = 65536 of them.
`imscribe.units` has the argument for integers over floats (a length is exact
while it is packed and is rounded once); what matters here is that the
conversions below are the only way in and out, and that each rounds once, on
the way in.

A point is 1/72.27 inch by definition and a pixel is whatever the display
says, so the two are related only through a resolution. That resolution is an
explicit parameter with a named default rather than a module-level global: a
hidden global DPI is a value that two call sites disagree about and neither
mentions.

## Faces

Named by role, not by file: a theme asks for `Face.PROSE_BOLD`, not for
Roboto-Bold.ttf. Which file a role is set from is `imscribe.fontlib`'s table
for the reference core and the host's registration for the library
(`imscribe.typesetter.load_fonts`).
"""

from __future__ import annotations

import enum
from typing import Final, TypeAlias

__all__ = [
    "BP_PER_INCH",
    "DEFAULT_PX_PER_INCH",
    "PT_PER_INCH",
    "UNITY",
    "Face",
    "Scaled",
    "pt_from_sp",
    "px_from_sp",
    "round_to_px",
    "sp_from_bp",
    "sp_from_pt",
    "sp_from_px",
]

Scaled: TypeAlias = int
"""
A length in scaled points (2^-16 pt).

An alias rather than a `NewType`, and that is a trade rather than an oversight.
`NewType` would catch a raw int reaching a dimension parameter, but layout is
almost entirely arithmetic *on* dimensions, and `a + b` over two `NewType` ints
is an `int` again -- every sum, difference and glue accumulation would need a
re-wrap. The wrapper noise would be dense enough to hide the thing it is meant
to make visible. The name is documentation and the unit discipline is held by
the conversions below being the only way in and out.
"""

UNITY: Final = 1 << 16
"""Scaled points in one printer's point. TeX's `@d unity == '200000` (§101)."""

PT_PER_INCH: Final = 72.27
"""Printer's points per inch. This is the definition of TeX's `pt`."""

BP_PER_INCH: Final = 72.0
"""
Big points per inch. `bp` is what PostScript, PDF and most digital type call a
"point"; it is 1.00375 TeX points, and confusing the two is a 0.4% error that
looks like a font bug rather than a unit bug.
"""

DEFAULT_PX_PER_INCH: Final = 96.0
"""
Assumed display resolution, in pixels per inch.

96 is the CSS reference pixel and what ImGui's unscaled coordinates behave like
at 100% UI scale. It is an assumption about the device, not a fact about the
document, which is why every conversion takes it as an argument and this is only
the default.
"""


def sp_from_pt(points: float) -> Scaled:
    """
    Convert printer's points to scaled points, rounding once.
    """
    return round(points * UNITY)


def pt_from_sp(length: Scaled) -> float:
    """
    Convert scaled points to printer's points. Exact for every `Scaled`.
    """
    return length / UNITY


def sp_from_bp(big_points: float) -> Scaled:
    """
    Convert big points (1/72 inch, the PostScript point) to scaled points.
    """
    return round(big_points * (PT_PER_INCH / BP_PER_INCH) * UNITY)


def sp_from_px(pixels: float, px_per_inch: float = DEFAULT_PX_PER_INCH) -> Scaled:
    """
    Convert device pixels to scaled points at a given display resolution.
    """
    return round(pixels * (PT_PER_INCH / px_per_inch) * UNITY)


def px_from_sp(length: Scaled, px_per_inch: float = DEFAULT_PX_PER_INCH) -> float:
    """
    Convert scaled points to device pixels, **without** rounding.

    Deliberately fractional. Rounding a position to the pixel grid is ship-out's
    job and must happen once, at the end, on an absolute coordinate -- see
    `round_to_px`. Rounding here instead would round every intermediate length
    and put the error back where the scaled-point representation exists to keep
    it out of.
    """
    return length * (px_per_inch / PT_PER_INCH) / UNITY


def round_to_px(length: Scaled, px_per_inch: float = DEFAULT_PX_PER_INCH) -> int:
    """
    Snap an absolute ship-out coordinate to the pixel grid.

    The single rounding step. Apply it to a final absolute position, never to a
    width that another position will be computed from: rounding widths and then
    summing them accumulates error along a line, while rounding the sums does
    not.

    **This is not §625's glue rounding and must not be used for it.** That one is
    sp to sp, inside the layout core, and has to be Pascal's `round` -- half away
    from zero -- because the algorithm takes differences of successive rounded
    totals and a 1sp divergence shifts every glue node after it. This one is sp
    to device pixels, happens once, and uses Python's `round`, which is
    half-to-even; `round_to_px` of exactly 2.5px is 2 and of 3.5px is 4. Pixels
    are a device grid and no later arithmetic depends on the tie-break, so
    half-to-even is fine here and wrong there (correction C3 in
    `docs/tex-notes.md`).
    """
    return round(px_from_sp(length, px_per_inch))


class Face(enum.Enum):
    """
    The typographic roles this project renders, named by role rather than by family.

    `CODE_BOLD` is the one role with no file behind it in the fonts imgui-bundle
    ships: the bundle has a single Inconsolata weight. It exists so that a host
    with a bold monospace of its own has a role to register it under
    (`imscribe.fontlib.register_font`); until one is registered `imscribe.fontlib`
    backs it with `PROSE_BOLD`'s file, which is what bold inside code was set in
    before this member existed. So iterating `Face` now visits a role that may
    share a file with another -- a caller that wants one entry per *file* asks
    `imscribe.fontlib.backing_face`.
    """

    PROSE = "prose"
    PROSE_BOLD = "prose-bold"
    PROSE_ITALIC = "prose-italic"
    PROSE_BOLD_ITALIC = "prose-bold-italic"
    CODE = "code"
    CODE_BOLD = "code-bold"
    MATH = "math"

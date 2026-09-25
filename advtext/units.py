r"""
Dimensions, in TeX's scaled points, as Python integers.

**The decision: integer scaled points, everywhere, with exactly two documented
exceptions.** A scaled point is 2^-16 pt, so a dimension is a plain `int` and
one printer's point is `UNITY` = 65536 of them.

The alternative was floats, and it is worse here for a specific reason rather
than a stylistic one. TeX's rounding discipline is that a length is *exact*
while it is being packed and gets rounded exactly once, at ship-out
(`docs/tex-notes.md` §2.5): the glue renderer accumulates the total natural
stretch seen so far, multiplies by the glue ratio once, rounds once, and takes a
difference against the previous rounded total. That is what stops per-glue
rounding error from walking along a line. You cannot express "rounded exactly
once" in a system whose intermediate values are already approximate -- with
floats every addition rounds, the discipline becomes unstateable, and the error
it exists to prevent comes back in a form nobody can point at. Integers make the
whole pipeline reproducible bit-for-bit, which also makes a golden-artifact test
meaningful instead of approximate.

The two exceptions, both deliberate:

- **`glue_set` is a float.** It is a *ratio*, not a length (`docs/tex-notes.md`
  §1.2: `glue_ratio = real`). TeX itself stores it as a real. Multiplying a
  scaled stretch by it is where the one rounding happens.
- **The conversions below take and return `float` at the boundary**, because the
  outside world speaks points and pixels. They round on the way in, once.

Pixels. There is no printer here; the output device is a pixel grid, and a font
size arrives as "16 px". A point is 1/72.27 inch by definition and a pixel is
whatever the display says, so the two are related only through a resolution.
That resolution is an explicit parameter with a named default rather than a
module-level global: a hidden global DPI is a value that two call sites disagree
about and neither mentions.

Out of scope: `mu` (math units, which scale with the current math style), `em`
and `ex` relative units, and TeX's `xn_over_d` fixed-point multiply. The first
two belong with the code that knows a style and a font; the third is an overflow
dodge for 32-bit arithmetic that Python's unbounded ints make unnecessary.
"""

from __future__ import annotations

import enum
from typing import Final, TypeAlias

__all__ = [
    "BP_PER_INCH",
    "DEFAULT_PX_PER_INCH",
    "MAX_DIMEN",
    "PT_PER_INCH",
    "RUNNING",
    "UNITY",
    "GlueOrder",
    "Scaled",
    "px_from_sp",
    "round_to_px",
    "sp_from_bp",
    "sp_from_pt",
    "sp_from_px",
    "pt_from_sp",
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

MAX_DIMEN: Final = (1 << 30) - 1
"""
The largest representable dimension, TeX's `@d max_dimen == '7777777777` (§421).
About 16384 pt. Kept as a limit even though Python integers do not overflow,
because a length past it means a computation went wrong rather than that a very
long line is wanted.
"""

RUNNING: Final = -(1 << 30)
r"""
The "running dimension" sentinel for rules, TeX's `@d null_flag == -'10000000000`
(§138). A running width, height or depth is resolved against the enclosing box
at ship-out, which is how `\hrule` spans whatever it is put in. It is a
*sentinel and not a length*: never add it to anything.
"""


class GlueOrder(enum.IntEnum):
    """
    The four orders of infinity a glue component can have (§150).

    An `IntEnum` because in the source this is an ordinal type,
    `@!glue_ord = normal..filll`, and the comparison between two orders is
    load-bearing: the rule in §646 is that the highest order of infinity with a
    nonzero coefficient is used *as if no other orders were present*. A plain
    `Enum` would make that comparison an explicit lookup for no gain, since the
    ordering is the semantics here rather than an accident of declaration.

    `NORMAL` is finite glue. It is the only order whose amounts are lengths in
    the ordinary sense; the other three are coefficients that dominate every
    lower order completely, so a `fil` amount and a `NORMAL` amount must never
    be added together. `advtext.nodes.GlueTotal` is the type that enforces that.
    """

    NORMAL = 0
    FIL = 1
    FILL = 2
    FILLL = 3


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

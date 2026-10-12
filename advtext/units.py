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

**Where the lengths themselves are defined.** `Scaled`, `UNITY`, the three
resolutions and the six conversions are `advtext.primitives`' since
2026-10-11 and are imported here: the same objects under either path. They
moved so that a theme, and everything that sets its text through imtypeset,
can name a length without loading this module, which with `GlueOrder`,
`MAX_DIMEN` and `RUNNING` is part of the reference layout core. Everything
this docstring says about them is still the decision.
"""

from __future__ import annotations

import enum
from typing import Final

from advtext.primitives import (
    BP_PER_INCH,
    DEFAULT_PX_PER_INCH,
    PT_PER_INCH,
    UNITY,
    Scaled,
    pt_from_sp,
    px_from_sp,
    round_to_px,
    sp_from_bp,
    sp_from_pt,
    sp_from_px,
)

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

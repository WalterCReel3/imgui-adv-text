"""
`badness(t, s)` -- how bad it is to stretch or shrink by `t` when `s` is available.

One function, transcribed from §108 of `tex.web` without simplification, and
that fidelity is the whole point of the module. §108 says outright that "all
implementations of TeX should use precisely this method", and the reason is not
sentiment: the integer approximation's exact output values are what the fitness
class thresholds are calibrated against. §817 names the four classes; the
thresholds themselves are applied in `try_break`, and they are not symmetric.
Stretching (§852) is a three-way ladder -- `b > 99` very loose, `b > 12` loose,
otherwise decent. Shrinking (§853) is two-way -- `b > 12` tight, otherwise
decent, with no "very tight" class at all. Those numbers are not round by
accident: this function returns exactly 12 when the stretch used is half of what
is available and exactly 100 when it is all of it. Substituting the textbook
`100 * (t / s) ** 3` moves a handful of values across those edges, which changes
which breakpoints win, which changes where the lines break. The "cleaner"
version is a different algorithm wearing the same name.

Two properties from §108 worth knowing because tests here pin them:

- `badness(t+1, s) >= badness(t, s) >= badness(t, s+1)` -- monotone, provably.
- It can produce at most 1095 distinct values. `tests/test_badness.py` counts
  them, which is a direct check of the transcription against the source's own
  arithmetic claim rather than against a restatement of it.

Out of scope: `last_badness` reporting, the `\\hbadness`/`\\vbadness` diagnostic
gates (§660, §674), and the sentinels callers layer on top of this one --
`awful_bad`, `deplorable`, and `try_break`'s `inf_bad + 1` for a line that
cannot shrink enough. Those belong with the code that packs and breaks; this
module answers one question and returns a value in `[0, INF_BAD]`.
"""

from __future__ import annotations

from typing import Final

from advtext.units import Scaled

__all__ = ["INF_BAD", "badness"]

INF_BAD: Final = 10000
"""
Infinitely bad. TeX's `@d inf_bad = 10000` (§108).

§108 treats any badness of 2^13 or more as infinite. The largest value this
function actually returns short of the ceiling is 8189, so the finite range and
the sentinel do not meet; §828 relies on `badness` never exceeding 10000.
"""

_ALPHA: Final = 297
"""
The multiplier in the approximation `r ~ alpha * t / s`, chosen so that
`alpha**3` is close to `100 * 2**18`: 297**3 = 26198073 = 99.94 * 2**18. `r` is
therefore roughly the cube root of the wanted badness, scaled.
"""

_MAX_T_FOR_DIRECT_MULTIPLY: Final = 7230584
"""
Largest `t` for which `t * 297` still fits in a signed 32-bit word:
7230584 * 297 = 2147483448 < 2**31. Above it the source divides before it
multiplies, losing precision to keep the product representable.

Python integers do not overflow, so this branch is not needed for correctness of
the arithmetic -- it is needed for *agreement*. The two paths round differently,
and dropping the branch would make this function disagree with TeX on exactly
the large-`t` inputs a stretched line produces.
"""

_MIN_S_FOR_SCALED_DIVIDE: Final = 1663497
"""
Below this, a `t` too large to multiply cannot be scaled down usefully either,
so the source sets `r := t`. That is guaranteed to exceed `_MAX_R` and yield
`INF_BAD`, which is the right answer: a huge shortfall against a tiny
stretchability is infinitely bad.
"""

_MAX_R: Final = 1290
"""
Guard on the `r * r * r` multiply: 1290**3 < 2**31 < 1291**3. Past it the result
would be infinitely bad anyway, so the guard and the semantics coincide.
"""

_ROUNDING_ADDEND: Final = 1 << 17
"""Half of `_SCALE`. The source writes it as the octal constant `@'400000`."""

_SCALE: Final = 1 << 18
"""
The divisor, `@'1000000` in the source. The final line computes `r**3 / 2**18`
rounded to nearest, which recovers the intended `100 * (t/s)**3`.
"""


def badness(t: Scaled, s: Scaled) -> int:
    """
    The badness of making a total `t` out of amounts summing to `s` (§108).

    `t` is the amount that has to be made up and must not be negative; a caller
    measuring shrink negates its shortfall first, as §853 does. `s` is the
    available stretchability or shrinkability; zero or negative `s` is
    infinitely bad unless nothing has to be made up at all.

    Every division below has non-negative operands, which is what lets Python's
    floor `//` stand in for Pascal's `div`. The two disagree on negative
    operands, so the guard on `t` is load-bearing rather than defensive: without
    it a negative `t` would floor the wrong way and return a plausible number.
    """
    if t < 0:
        raise ValueError(
            f"badness is defined for t >= 0; callers negate a shortfall first, got {t}"
        )
    if t == 0:
        return 0
    if s <= 0:
        return INF_BAD

    r: int
    if t <= _MAX_T_FOR_DIRECT_MULTIPLY:
        r = (t * _ALPHA) // s
    elif s >= _MIN_S_FOR_SCALED_DIVIDE:
        r = t // (s // _ALPHA)
    else:
        r = t

    if r > _MAX_R:
        return INF_BAD
    return (r * r * r + _ROUNDING_ADDEND) // _SCALE

r"""
The vocabulary of a math list, and the style algebra that governs it.

A formula here is a flat sequence of **atoms**: a nucleus with an optional
superscript and subscript, classified by what it *is* rather than by how it
looks. `advtext.math.mlist` turns that sequence into the boxes, kerns and glue
`hpack` can measure. This module holds only the types and the arithmetic over
styles -- nothing here measures anything or touches a font.

**Styles are TeX's integers, backwards on purpose.** §688 encodes display, text,
script and scriptscript as 0, 2, 4, 6 and adds 1 for the cramped variant, which
"gives a numerical order that is backwards from the convention of Appendix G";
a *smaller* style has a *larger* numerical value. Every transition in §702 is
integer arithmetic over that encoding, and keeping it lets those five one-liners
be transcribed rather than reinvented as a lookup table. `cur_style < TEXT`
means "display", `cur_style < SCRIPT` means "display or text", and an odd style
is a cramped one -- three tests that appear all over `mlist.py`.

**Atom class is not the same thing as atom type.** Thirteen types exist, and
only the first eight -- Ord, Op, Bin, Rel, Open, Close, Punct, Inner -- index
the inter-atom spacing table. §761 maps the rest onto one of the eight for
spacing: Over, Under, Vcenter, Radical and Accent all space as Ord, and a
fraction spaces as Inner. `spacing_class` is that map, and it is the only thing
the spacing table is ever indexed by.

**A field is a tagged union, not an optional pile.** §681's `math_type` is one
of empty, `math_char`, `sub_box` and `sub_mlist`, and `Field` is exactly that
set with `None` for empty. The alternative -- an atom carrying a codepoint *and*
a box *and* a sublist, three of which are always `None` -- makes "which one is
set" a runtime question in a module whose whole job is to branch on it.

Deliberately out of scope: `\mathchoice` (`docs/decisions.md`), delimiters and
the `left_noad`/`right_noad` pair that `var_delimiter` serves, and `\halign`.
Radical and Accent atoms are *declared* here because they are part of the
vocabulary and the spacing map needs them, and `mlist.py` raises on them rather
than pretending -- both need a delimiter or accent chain walk that nothing in
this project implements.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

from advtext.nodes import Box
from advtext.units import Scaled

__all__ = [
    "Atom",
    "AtomType",
    "Field",
    "Fraction",
    "Limits",
    "MathChar",
    "MathItem",
    "MathSize",
    "Style",
    "SubBox",
    "SubList",
    "bin_",
    "close_",
    "cramped_style",
    "denom_style",
    "frac",
    "group",
    "inner",
    "num_style",
    "op",
    "open_",
    "ord_",
    "punct",
    "rel",
    "size_for",
    "sub_style",
    "sup_style",
    "text",
]


class Style(enum.IntEnum):
    """
    The eight math styles, in §688's encoding: even is uncramped, odd is cramped.

    An `IntEnum` because the transitions in §702 are integer arithmetic on these
    values and the comparisons are load-bearing, not incidental. Larger is
    smaller: `SCRIPT_SCRIPT` (6) is the tiniest.
    """

    DISPLAY = 0
    DISPLAY_CRAMPED = 1
    TEXT = 2
    TEXT_CRAMPED = 3
    SCRIPT = 4
    SCRIPT_CRAMPED = 5
    SCRIPT_SCRIPT = 6
    SCRIPT_SCRIPT_CRAMPED = 7


class MathSize(enum.IntEnum):
    """
    The three font sizes a formula is set from (§699), in TeX's size codes.

    Three sizes rather than a continuous scale because that is what a math font
    is designed for: the script faces are not the text face shrunk, they are
    drawn with heavier strokes so they survive being small.
    """

    TEXT = 0
    SCRIPT = 16
    SCRIPT_SCRIPT = 32


def cramped_style(style: Style) -> Style:
    """
    §702: `cramped_style(#) == 2*(# div 2)+cramped`. Cramp without resizing.
    """
    return Style(2 * (style // 2) + 1)


def sup_style(style: Style) -> Style:
    """
    §702: `sup_style(#) == 2*(# div 4)+script_style+(# mod 2)`. Smaller, cramp kept.
    """
    return Style(2 * (style // 4) + Style.SCRIPT + (style % 2))


def sub_style(style: Style) -> Style:
    """
    §702: `sub_style(#) == 2*(# div 4)+script_style+cramped`. Smaller and cramped.

    A subscript is always cramped and a superscript is not, which is why
    `x^{y^z}` stacks higher than `x_{y_z}` drops.
    """
    return Style(2 * (style // 4) + Style.SCRIPT + 1)


def num_style(style: Style) -> Style:
    """
    §702: `num_style(#) == #+2-2*(# div 6)`. Smaller unless already scriptscript.
    """
    return Style(style + 2 - 2 * (style // 6))


def denom_style(style: Style) -> Style:
    """
    §702: `denom_style(#) == 2*(# div 2)+cramped+2-2*(# div 6)`. Smaller and cramped.
    """
    return Style(2 * (style // 2) + 1 + 2 - 2 * (style // 6))


def size_for(style: Style) -> MathSize:
    """
    §703: display and text both set from the text face; script and below shrink.
    """
    if style < Style.SCRIPT:
        return MathSize.TEXT
    return MathSize(16 * ((style - Style.TEXT) // 2))


def is_display(style: Style) -> bool:
    """
    §749's `cur_style<text_style`: display or cramped display.
    """
    return style < Style.TEXT


def is_cramped(style: Style) -> bool:
    """
    §688's `odd(cur_style)`: something sits above, so scripts must not rise.
    """
    return bool(style % 2)


class AtomType(enum.Enum):
    """
    What an atom is, which decides how much air goes either side of it.

    The first eight are §682's `ord_noad..inner_noad` and index the spacing
    table directly. The rest space as something else; see `spacing_class`.
    """

    ORD = enum.auto()
    OP = enum.auto()
    BIN = enum.auto()
    REL = enum.auto()
    OPEN = enum.auto()
    CLOSE = enum.auto()
    PUNCT = enum.auto()
    INNER = enum.auto()
    OVER = enum.auto()
    UNDER = enum.auto()
    VCENTER = enum.auto()
    RADICAL = enum.auto()
    ACCENT = enum.auto()

    @property
    def spacing_class(self) -> int:
        """
        The row or column this atom uses in §764's table, 0..7.
        """
        return _SPACING_CLASS[self]


# §761: Over, Under, Vcenter, Radical and Accent are all spaced as Ord. The
# eight that index the table map to themselves, in the source's order.
_SPACING_CLASS: dict[AtomType, int] = {
    AtomType.ORD: 0,
    AtomType.OP: 1,
    AtomType.BIN: 2,
    AtomType.REL: 3,
    AtomType.OPEN: 4,
    AtomType.CLOSE: 5,
    AtomType.PUNCT: 6,
    AtomType.INNER: 7,
    AtomType.OVER: 0,
    AtomType.UNDER: 0,
    AtomType.VCENTER: 0,
    AtomType.RADICAL: 0,
    AtomType.ACCENT: 0,
}


class Limits(enum.Enum):
    """
    Where a big operator's scripts go (§682's `op_noad` subtypes).

    `DEFAULT` is the one that carries information: §749's first line turns it
    into `LIMITS` in display style and leaves it alone otherwise, which is why
    a summation stacks its bounds in a display and sets them to the right
    inline. `LIMITS` and `NO_LIMITS` are the explicit overrides.
    """

    DEFAULT = enum.auto()
    LIMITS = enum.auto()
    NO_LIMITS = enum.auto()


@dataclass(frozen=True, slots=True)
class MathChar:
    """
    §681's `math_char`: one glyph from the math face.

    The codepoint may be a synthetic one minted by `advtext.fontlib` for a glyph
    the font does not encode -- that is how the display-size summation is named.
    """

    codepoint: int


@dataclass(frozen=True, slots=True)
class SubBox:
    """
    §681's `sub_box`: material already packed, to be used as it stands.
    """

    box: Box


@dataclass(frozen=True, slots=True)
class SubList:
    """
    §681's `sub_mlist`: a nested formula, to be converted at the inherited style.
    """

    items: tuple[MathItem, ...]


Field: TypeAlias = MathChar | SubBox | SubList | None
"""
One of an atom's three slots. `None` is §681's `empty`.
"""


@dataclass(frozen=True, slots=True)
class Atom:
    """
    A nucleus with optional scripts, classified (§681, §682).
    """

    kind: AtomType
    nucleus: Field = None
    sup: Field = None
    sub: Field = None
    limits: Limits = Limits.DEFAULT


@dataclass(frozen=True, slots=True)
class Fraction:
    r"""
    §683's `fraction_noad`, which reuses an atom's fields under other names.

    `thickness` of `None` is the source's `default_code`, meaning "use
    `default_rule_thickness`"; a thickness of exactly zero is `\atop`, a stacked
    pair with no rule between them, and §744 and §745 both branch on that.

    No delimiter fields. `\atopwithdelims` needs `var_delimiter`, which needs a
    delimiter chain walk this project does not implement.
    """

    numerator: Field = None
    denominator: Field = None
    thickness: Scaled | None = None


MathItem: TypeAlias = Atom | Fraction
"""
Anything that can appear in a math list. A union, so `match` over it is total.
"""


# --------------------------------------------------------------------------------
# A builder, so a formula reads as a formula
#
# There is no LaTeX parser here and there should not be: a parser would be the
# thing being demonstrated instead of the typesetting. These functions exist so
# that the sigma litmus test can be written out and still be read back.
# --------------------------------------------------------------------------------

Buildable: TypeAlias = "Field | MathItem | str | Sequence[MathItem]"
"""
Anything `group` will accept where a field is wanted.
"""


def _as_field(value: Buildable) -> Field:
    """
    Coerce the convenient forms into the one the algorithm consumes.

    A bare string becomes ordinary atoms, one per character, because that is
    what a string in a formula means; anything needing other classes says so.
    """
    match value:
        case None | MathChar() | SubBox() | SubList():
            return value
        case str():
            return SubList(text(value))
        case Atom() | Fraction():
            return SubList((value,))
        case _:
            return SubList(tuple(value))


def group(*parts: Buildable) -> SubList:
    """
    Gather several pieces into one field, flattening strings into atoms.
    """
    items: list[MathItem] = []
    for part in parts:
        field = _as_field(part)
        match field:
            case SubList(inner_items):
                items.extend(inner_items)
            case MathChar() | SubBox():
                items.append(Atom(AtomType.ORD, field))
            case None:
                continue
    return SubList(tuple(items))


def text(value: str) -> tuple[Atom, ...]:
    """
    Every character of a string as an ordinary atom.
    """
    return tuple(Atom(AtomType.ORD, MathChar(ord(character))) for character in value)


def _atom(
    kind: AtomType,
    nucleus: str | Field,
    sup: Buildable = None,
    sub: Buildable = None,
    limits: Limits = Limits.DEFAULT,
) -> Atom:
    """
    One atom, with strings coerced. A one-character string is a single glyph.
    """
    if isinstance(nucleus, str):
        nucleus = MathChar(ord(nucleus)) if len(nucleus) == 1 else SubList(text(nucleus))
    return Atom(kind, nucleus, _as_field(sup), _as_field(sub), limits)


def ord_(nucleus: str | Field, *, sup: Buildable = None, sub: Buildable = None) -> Atom:
    """
    An ordinary atom: a variable, a digit, a letter.
    """
    return _atom(AtomType.ORD, nucleus, sup, sub)


def op(
    nucleus: str | Field,
    *,
    sup: Buildable = None,
    sub: Buildable = None,
    limits: Limits = Limits.DEFAULT,
) -> Atom:
    r"""
    A large operator: `\sum`, `\int`, `\prod`.

    Leave `limits` at `DEFAULT` to get TeX's behaviour -- stacked in display
    style, set to the right inline -- which is what the litmus test exercises.
    """
    return _atom(AtomType.OP, nucleus, sup, sub, limits)


def bin_(nucleus: str | Field) -> Atom:
    """
    A binary operator. It becomes ordinary where there is nothing to bind (§727).
    """
    return _atom(AtomType.BIN, nucleus)


def rel(nucleus: str | Field) -> Atom:
    """
    A relation: the widest spacing in the table.
    """
    return _atom(AtomType.REL, nucleus)


def open_(nucleus: str | Field) -> Atom:
    """
    An opening delimiter, spaced tight against what follows.
    """
    return _atom(AtomType.OPEN, nucleus)


def close_(nucleus: str | Field) -> Atom:
    """
    A closing delimiter, spaced like an ordinary atom on its right.
    """
    return _atom(AtomType.CLOSE, nucleus)


def punct(nucleus: str | Field) -> Atom:
    """
    Punctuation: a thin space after, never before.
    """
    return _atom(AtomType.PUNCT, nucleus)


def inner(nucleus: Buildable, *, sup: Buildable = None, sub: Buildable = None) -> Atom:
    """
    A self-contained subformula, spaced as a unit.
    """
    return Atom(AtomType.INNER, _as_field(nucleus), _as_field(sup), _as_field(sub))


def frac(
    numerator: Buildable, denominator: Buildable, *, thickness: Scaled | None = None
) -> Fraction:
    """
    A fraction. `thickness=0` is `\\atop`: stacked, with no rule between.
    """
    return Fraction(_as_field(numerator), _as_field(denominator), thickness)

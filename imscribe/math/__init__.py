"""
Math typesetting: a formula as atoms, converted into boxes `hpack` can measure.

Two modules and one seam. `imscribe.math.atoms` holds the vocabulary -- atom
classes, the four styles and their cramped variants, the style transitions, and
a small builder so a formula can be written out and read back. `imscribe.math.
mlist` is the algorithm, TeX's `mlist_to_hlist` (§726-§767).

The names re-exported here are the ones a caller needs to build and convert a
formula. Everything else is an implementation detail of the conversion and is
reachable through the submodules if it is really wanted.

A radical and a `\\left`...`\\right` pair are sized from the glyphs the font's
variant chain holds and from nothing else. A radicand taller than the tallest
surd, or content the tallest delimiter covers less than three quarters of,
raises `DelimiterTooSmallError` rather than being set with a sign that does
not reach; so does prose holding a character its face lacks
(`MissingGlyphError`). Every refusal of that kind is a `MathLayoutError`, which
is the one type a caller with a fallback needs to catch.

Out of scope, and each for a reason stated where it bites: delimiters built
from pieces, accents, `\\mathchoice`, and any parsing at all. A LaTeX parser
would become the thing being demonstrated instead of the typesetting.
"""

from __future__ import annotations

from imscribe.math.atoms import (
    MED_SPACE,
    NEGATIVE_THIN_SPACE,
    QQUAD,
    QUAD,
    THICK_SPACE,
    THIN_SPACE,
    Atom,
    AtomType,
    Field,
    Fraction,
    Limits,
    MathChar,
    MathItem,
    MathSize,
    MathText,
    MuGlue,
    Style,
    SubBox,
    SubList,
    bin_,
    close_,
    cramped_style,
    delimited,
    denom_style,
    frac,
    group,
    inner,
    num_style,
    op,
    open_,
    ord_,
    prose_text,
    punct,
    radical,
    rel,
    size_for,
    space,
    sub_style,
    sup_style,
    text,
)
from imscribe.math.mlist import (
    DelimiterTooSmallError,
    MathFonts,
    MathLayoutError,
    MathResolver,
    MissingGlyphError,
    TextFaceUnavailableError,
    math_fonts,
    mlist_to_hlist,
)

__all__ = [
    "MED_SPACE",
    "NEGATIVE_THIN_SPACE",
    "QQUAD",
    "QUAD",
    "THICK_SPACE",
    "THIN_SPACE",
    "Atom",
    "AtomType",
    "DelimiterTooSmallError",
    "Field",
    "Fraction",
    "Limits",
    "MathChar",
    "MathFonts",
    "MathItem",
    "MathLayoutError",
    "MathResolver",
    "MathSize",
    "MathText",
    "MissingGlyphError",
    "MuGlue",
    "Style",
    "SubBox",
    "SubList",
    "TextFaceUnavailableError",
    "bin_",
    "close_",
    "cramped_style",
    "delimited",
    "denom_style",
    "frac",
    "group",
    "inner",
    "math_fonts",
    "mlist_to_hlist",
    "num_style",
    "op",
    "open_",
    "ord_",
    "prose_text",
    "punct",
    "radical",
    "rel",
    "size_for",
    "space",
    "sub_style",
    "sup_style",
    "text",
]

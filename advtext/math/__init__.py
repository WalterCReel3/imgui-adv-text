"""
Math typesetting: a formula as atoms, converted into boxes `hpack` can measure.

Two modules and one seam. `advtext.math.atoms` holds the vocabulary -- atom
classes, the four styles and their cramped variants, the style transitions, and
a small builder so a formula can be written out and read back. `advtext.math.
mlist` is the algorithm, TeX's `mlist_to_hlist` (§726-§767).

The names re-exported here are the ones a caller needs to build and convert a
formula. Everything else is an implementation detail of the conversion and is
reachable through the submodules if it is really wanted.

Out of scope, and each for a reason stated where it bites: delimiters and
therefore radicals, accents, `\\mathchoice`, and any parsing at all. A LaTeX
parser would become the thing being demonstrated instead of the typesetting.
"""

from __future__ import annotations

from advtext.math.atoms import (
    Atom,
    AtomType,
    Field,
    Fraction,
    Limits,
    MathChar,
    MathItem,
    MathSize,
    Style,
    SubBox,
    SubList,
    bin_,
    close_,
    cramped_style,
    denom_style,
    frac,
    group,
    inner,
    num_style,
    op,
    open_,
    ord_,
    punct,
    rel,
    size_for,
    sub_style,
    sup_style,
    text,
)
from advtext.math.mlist import MathFonts, MathResolver, math_fonts, mlist_to_hlist

__all__ = [
    "Atom",
    "AtomType",
    "Field",
    "Fraction",
    "Limits",
    "MathChar",
    "MathFonts",
    "MathItem",
    "MathResolver",
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
    "math_fonts",
    "mlist_to_hlist",
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

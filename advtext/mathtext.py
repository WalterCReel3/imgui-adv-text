r"""
A `$...$` subset, turned into the atom vocabulary `advtext.math` already has.

**This is an extension that sits on top of the engine, and the direction of the
import is the whole of that statement.** This module imports `advtext.math`;
nothing in `advtext.math`, `advtext.markdown` or the layout below them imports
this. The engine stays parser-free: `advtext.math.atoms` still says a formula is
built, not parsed, and the Formula gallery (`advtext.ui.formulas`) is still
written out by hand. What changed is the user's decision (2026-10-07,
`.concerns/lead--demo-tasks.md`): inline math from a subset, "just enough to be
useful without having to dive into a parser". So this is a tokenizer and a
recursive descent over a fixed table, and it is deliberately not TeX's mouth:
no macros, no catcodes, no state.

    result = parse(r"e^{i\pi} + 1 = 0", display=False)
    if isinstance(result, Formula):
        box = set_formula(result, formula_fonts(size))
    else:
        result.reason, result.position, result.kind   # set the source as code

    typeset(source, size, display=False)   # both steps; a font failure is a Refusal too

## The contract: a formula, or a refusal, and never a guess

`parse` is **total**: it returns a `Formula` or a `Refusal` for every string and
raises for none (`tests/test_mathtext.py` fuzzes that). Anything outside the
subset is a `Refusal` carrying a reason a person can read and the offset of the
offending character. There is no best-effort path, because a formula that sets
with a piece silently missing reads as a different formula, and the caller's
fallback -- the source in the code face -- is honest where a guess is not.

**A `Formula` can be set, with one exception that is not the parser's to
know.** `mlist_to_hlist` raises on Accent atoms and this module never emits
one, and nesting is capped (`MAX_DEPTH`) so neither this parser's recursion nor
the engine's can run out of stack on hostile input. The exception is height: a
`\left`...`\right` or a `\sqrt` is sized from the font's chain of ready-made
variants, the tallest about three em, and content taller than that is refused
by the engine when the list is converted
(`advtext.math.mlist.DelimiterTooSmallError`) -- always for a radical, and for
a `\left` pair once the tallest delimiter covers less than three quarters of
the content. Whether that happens depends on
the style and the font, so `parse` cannot say; `set_formula` raises it and
`typeset` returns it as a `Refusal` of kind `LAYOUT`.

## What the engine builds, and so what is in the subset

Read out of `advtext/math/mlist.py` on 2026-10-07, not out of its docstring:

- **Scripts** (`^`, `_`, nested, both at once): `_make_scripts`, §756-§759.
  In. `'` is a prime in the superscript.
- **`\frac`**: `_make_fraction`, §743-§747. In.
- **Big operators and limits**: `_make_op`, one variant step in display
  style (§749). In, with `\limits` and `\nolimits`.
- **Atom classes and spacing**: §727 and §764's table. In; the class of every
  symbol is in the tables below.
- **`\overline`, `\underline`**: `_make_over`, `_make_under` (§734, §735). In.
- **`\left...\right`**: `_make_left_right` over the variant chain, with no
  extensible half. In, for the delimiters `sized_delimiters()` lists -- each
  has a chain of eight in Latin Modern Math -- and `.` for none. `\middle`
  and `\big` and its family are not built and are refused. `\binom` is in:
  a fraction with no bar between a fitted pair of parentheses.
- **`\sqrt`**: `_make_radical`. In. It takes no degree, so `\sqrt[3]{x}` and
  `\root` are refused.
- **Explicit spaces**: a `SPACE` atom holding glue in math units. `\,` `\:`
  (`\>`) `\;` `\!` `\quad` `\qquad` and amsmath's long names for the first
  four are in, and so are `\ ` and `~`, as six mu (`_SPACES` says what that
  is and is not). `\hspace` and the phantoms are refused.
- **`\text{}`**: a `MathText` field, set in a prose face at the size of the
  style it lands in. In, with `\textrm`, `\textit`, `\textbf`; the argument
  is plain words. `\mbox` and `\hbox` stay at text size in TeX whatever the
  style, which this does not do, so they are refused and the reason says to
  write `\text`. `\mathrm{}` and `\operatorname{}` are something else: the
  math face's own upright letters as atoms.
- **Accents** (`\hat`, `\vec`, ...): `ACCENT`, on which `mlist_to_hlist`
  raises. Refused.
- **`\displaystyle`, `\dfrac`, `\tfrac`**: a math list has no style-change
  item. Refused.

**Matrices are left out for now** (the user's decision), and so is everything
that needs alignment: `\begin{...}`, `&`, `\\`. They are refusals with their own
kinds, so a host can say which thing it was.

Fixed-size parentheses and brackets are ordinary Open and Close atoms, exactly
as the gallery's `cauchy` uses them, and do not grow; `\left(` is how a source
asks for one that does.

## Four choices a reader comparing this with LaTeX should know about

**A fraction is wrapped in an Inner atom**, as the gallery writes
`inner(frac(...))`. LaTeX's `\frac` is `{... \over ...}`, an Ord. The engine
omits `\nulldelimiterspace` either side of a fraction (`_make_fraction` says
so), and the thin space an Inner takes from its neighbours stands in for it;
an Ord fraction would touch the letters beside it. It also keeps every `\frac`
here identical to the hand-built gallery entries.

**Integrals keep their bounds beside them** (`Limits.NO_LIMITS`), sums and
products take the engine's default (stacked in display, beside inline). That is
LaTeX's own split -- `\int` is `\intop\nolimits` -- and `\limits` / `\nolimits`
override either.

**Variables are math italic, digits and capital Greek upright**, the convention
`advtext.ui.formulas.italic` documents, including its trap: the italic `h` is
`U+210E` because `U+1D455` does not exist. The table is repeated here rather
than imported because `advtext.ui.formulas` imports `advtext.markdown`, and
markdown is the one module that will import this; the tests pin the two equal.

**`\dots` is `\ldots`.** amsmath chooses between baseline and centred dots by
what follows; that is state, so it is not done.

## The second pass: four things the engine grew

Radicals, sized delimiters, spaces and text in math were refusals in the first
version of this module, because the engine built none of them. The lead's
decision D1 (`.concerns/lead--demo-review0-findings.md`) had task C-mathengine
add them to `advtext.math`, and this module now emits the engine's own atoms
for them: `RADICAL`, an Inner of `LEFT`...`RIGHT`, `SPACE`, and an Ord holding
`MathText`. The kinds `RADICAL`, `DELIMITER`, `SPACING` and `TEXT` remain for
what is still refused in each family (a degree, `\big`, `\hspace`, `\mbox`).

A first draft had set spaces by folding a space glyph of the math face into
the atom before it. It was withdrawn for D1 and is not used: the engine's
`SPACE` atom is glue in math units, transparent to the class of its
neighbours, which a wrapped glyph only imitated. The draft's acceptance test
-- a space adds its own width and nothing else, for every pair of classes --
is in `tests/test_mathtext.py` against the real thing; the draft itself stays
in `.concerns/C-mathtext-scripts/` as a record.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from advtext.fontmetrics import Face, MathFontMetrics
from advtext.math.atoms import (
    MED_SPACE,
    NEGATIVE_THIN_SPACE,
    QQUAD,
    QUAD,
    THICK_SPACE,
    THIN_SPACE,
    Atom,
    AtomType,
    Fraction,
    Limits,
    MathChar,
    MathItem,
    MathText,
    MuGlue,
    Style,
    SubList,
)
from advtext.math.mlist import (
    SURD,
    DelimiterTooSmallError,
    MathFonts,
    MathLayoutError,
    MathResolver,
    MissingGlyphError,
    TextFaceUnavailableError,
    math_fonts,
    mlist_to_hlist,
)
from advtext.nodes import Box
from advtext.pack import hpack
from advtext.units import Scaled

if TYPE_CHECKING:
    from advtext.markdown import MathBuilder, MathRefused
    from advtext.style import MetricsResolver

__all__ = [
    "MAX_DEPTH",
    "Formula",
    "MathResult",
    "Refusal",
    "RefusalKind",
    "Typeset",
    "formula_fonts",
    "markdown_math",
    "parse",
    "refused_commands",
    "set_formula",
    "sized_delimiters",
    "supported_commands",
    "typeset",
]


MAX_DEPTH: Final = 24
"""
How deeply braces, scripts and fraction arguments may nest before `parse` refuses.

Two recursions are bounded by it: this parser's, and `mlist_to_hlist`'s over the
nested lists it is handed. Four levels already reach the scriptscript floor, so
nothing legible is lost; the number is a stack guard, not a typographic limit.
"""


class RefusalKind(enum.Enum):
    r"""
    Why a source was not turned into a formula. One per class of reason.

    Kinds rather than only prose so a host can branch -- "matrices are not
    supported yet" is a different message to a reader than "this is not math".

    Two kinds are `typeset`'s alone, because `parse` has no font: `FONT`, and
    `LAYOUT` -- a source that is in the subset and that the engine would not
    set with the fonts in hand, which in practice means that what is inside a
    `\left`...`\right` or under a `\sqrt` is taller than the largest delimiter
    the math face has.
    """

    EMPTY = "empty"
    SYNTAX = "syntax"
    NESTING = "nesting"
    UNKNOWN_COMMAND = "unknown-command"
    CHARACTER = "character"
    MACRO = "macro"
    ENVIRONMENT = "environment"
    MATRIX = "matrix"
    ALIGNMENT = "alignment"
    INFIX = "infix"
    DELIMITER = "delimiter"
    RADICAL = "radical"
    ACCENT = "accent"
    STYLE = "style"
    SPACING = "spacing"
    TEXT = "text"
    FONT = "font"
    LAYOUT = "layout"


@dataclass(frozen=True, slots=True)
class Formula:
    r"""
    A source the subset covers, as a math list.

    `items` is what `advtext.math.mlist_to_hlist` consumes and nothing else: the
    same `Atom` and `Fraction` values the gallery builds by hand. `source` is
    the string between the dollars, kept because a copy of a selected formula
    returns it. `display` is carried, not baked in: the atoms are the same in
    both styles and only `style` differs.
    """

    source: str
    display: bool
    items: tuple[MathItem, ...]

    @property
    def style(self) -> Style:
        """
        `Style.DISPLAY` for `$$...$$`, `Style.TEXT` for `$...$`.
        """
        return Style.DISPLAY if self.display else Style.TEXT


@dataclass(frozen=True, slots=True)
class Refusal:
    """
    A source outside the subset: why, and where.

    `position` is an offset into `source` (0 <= position <= len(source)), the
    start of the command or character that could not be taken. `reason` is one
    sentence for a person. The caller sets `source` as code.
    """

    source: str
    display: bool
    kind: RefusalKind
    reason: str
    position: int


MathResult = Formula | Refusal
"""
What `parse` returns. A union, so `match` or `isinstance` over it is total.
"""


def parse(source: str, *, display: bool = False) -> MathResult:
    r"""
    Turn the text between the dollars into a math list, or say why not.

    Total and linear: one left-to-right pass, no backtracking, no exception for
    any input. `display` only chooses the style the result is set at.
    """
    parser = _Parser(source)
    try:
        items = parser.formula()
    except _Refused as refused:
        position = min(max(refused.position, 0), len(source))
        return Refusal(source, display, refused.kind, refused.reason, position)
    return Formula(source, display, items)


def formula_fonts(
    size: Scaled,
    resolve: MathResolver | None = None,
    *,
    text: MetricsResolver | None = None,
) -> MathFonts:
    r"""
    The math face at the three sizes a formula at `size` needs, and the prose faces.

    `resolve` defaults to the real font, imported lazily for the reason
    `advtext.ui.formulas.fontlib_math_metrics` gives. `advtext.fontlib` caches
    the faces by size, so this is three dictionary builds; a caller setting many
    formulae at one size should still keep the result, because `MathFonts.measure`
    is a fresh closure each time and a layout cache keyed on it would miss.

    `text` resolves the prose face a `\text{...}` is set in. It defaults to
    `advtext.style.fontlib_metrics`, imported lazily like the math face;
    without one the engine raises `TextFaceUnavailableError` for any formula
    holding prose.
    """
    if text is None:
        from advtext.style import fontlib_metrics

        text = fontlib_metrics
    return math_fonts(size, _real_math_metrics if resolve is None else resolve, text=text)


def _real_math_metrics(size: Scaled) -> MathFontMetrics:
    from advtext import fontlib

    return fontlib.math_metrics(float(size))


def set_formula(formula: Formula, fonts: MathFonts) -> Box:
    r"""
    One formula as a packed hbox at its natural width, on its baseline.

    `box.height` and `box.depth` are the formula's own, so a line holding it is
    as tall as it needs to be. The box must be shipped with `fonts.measure`
    (or a measure that resolves the same math keys), as the gallery's are.

    **Raises `advtext.math.mlist.MathLayoutError`** for a formula the fonts in
    hand cannot set: content taller than the largest variant of a `\left`,
    `\right` or `\sqrt` (`DelimiterTooSmallError`), or prose with no prose
    face to set it in (`TextFaceUnavailableError`). `typeset` turns both into
    refusals; a caller of this function catches that one type.
    """
    return hpack(
        mlist_to_hlist(formula.items, formula.style, fonts),
        measure=fonts.measure,
    ).box


@dataclass(frozen=True, slots=True)
class Typeset:
    """
    A formula that was parsed and set: the box, and what it has to be shipped with.
    """

    formula: Formula
    box: Box
    fonts: MathFonts


def typeset(
    source: str,
    size: Scaled,
    *,
    display: bool = False,
    resolve: MathResolver | None = None,
    fonts: MathFonts | None = None,
) -> Typeset | Refusal:
    r"""
    `parse`, `formula_fonts` and `set_formula` as one call that cannot raise.

    The two-step route can, in three ways, and each lands here as a
    `Refusal`, so a caller has one fallback -- the source as code:

    - **The engine will not set it** (`advtext.math.mlist.MathLayoutError`):
      kind `LAYOUT`, position 0. In practice, a radicand taller than the
      tallest radical sign the math face has, or content between `\left` and
      `\right` that the tallest delimiter covers less than three quarters of,
      since neither is assembled from pieces; the reason says which and by
      how much. Prose with no prose face to set it in is an exception, and is
      a `FONT` matter.
    - **A word in `\text{}` has a character its face lacks**
      (`advtext.math.mlist.MissingGlyphError`): kind `FONT`, at the position
      of the character, which the reason names. A formula with a hole where
      a word should be is not set.
    - **Anything else**: kind `FONT`. The math face may be missing
      (`advtext.fontlib.MissingFontError`), a host may have registered a face
      with no `MATH` table, and `resolve` is injected and may do anything.

    Pass `fonts` to reuse one `MathFonts` across the formulae of a document;
    `size` and `resolve` are then not consulted.

    Bare `Exception` in the last catch, deliberately, for the reason
    `advtext.ui.specimen` gives for the same catch: the resolver is the
    caller's code. It is the only such catch in this module, and `parse`
    itself needs none.
    """
    result = parse(source, display=display)
    if isinstance(result, Refusal):
        return result
    try:
        used = formula_fonts(size, resolve) if fonts is None else fonts
        box = set_formula(result, used)
    except MissingGlyphError as failure:
        character = failure.character
        reason = (
            f"the {failure.face.value} face has no glyph for {character!r} "
            f"(U+{ord(character):04X}), so its words cannot be set"
        )
        return Refusal(source, display, RefusalKind.FONT, reason, max(source.find(character), 0))
    except TextFaceUnavailableError as failure:
        reason = f"there is no prose face to set its words in: {failure}"
        return Refusal(source, display, RefusalKind.FONT, " ".join(reason.split()), 0)
    except MathLayoutError as failure:
        return Refusal(source, display, RefusalKind.LAYOUT, _layout_reason(failure), 0)
    except Exception as failure:
        reason = f"the math face could not set it: {type(failure).__name__}: {failure}"
        return Refusal(source, display, RefusalKind.FONT, " ".join(reason.split()), 0)
    return Typeset(result, box, used)


def _layout_reason(failure: MathLayoutError) -> str:
    """
    One sentence for a person, out of what the engine raised.

    The engine's own message is in scaled points and names a codepoint; a
    reader wants the delimiter and a proportion.
    """
    if isinstance(failure, DelimiterTooSmallError) and failure.largest > 0:
        if failure.codepoint == SURD:
            what, which = "what is under the root", "radical sign"
        else:
            what, which = "what is between the delimiters", chr(failure.codepoint)
        times = failure.needed / failure.largest
        return (
            f"{what} needs a {which} {times:.2f} times as tall as the largest the math "
            "face has, and one is not assembled from pieces here"
        )
    return " ".join(f"the math engine will not set it: {failure}".split())


def markdown_math(resolve: MathResolver | None = None, *, remember: int = 2048) -> MathBuilder:
    r"""
    This module as the `math=` argument of `build_document` and `StreamDocument`.

        build_document(source, theme, resolve, math=markdown_math())
        StreamDocument(theme, resolve, math=markdown_math())

    `advtext.markdown` finds the dollars and does not know what a formula is;
    it calls what it is given with the source, display or not, and the size of
    the text around it. This is that callable: `typeset`, with a refusal
    turned into the `advtext.markdown.MathRefused` the converter sets as code.
    The dependency runs one way -- this module imports markdown, lazily, and
    markdown imports neither this nor any other formula parser.

    **It remembers.** A stream converts its last block again every time text
    arrives, and a formula in that block would be parsed and set again each
    time; so the last `remember` distinct `(source, display, size)` results
    are kept, and the three math faces for each size. Boxes are immutable, so
    handing the same one out twice is safe. Keep one builder for the life of a
    view and it is also what makes an unchanged paragraph an unchanged value
    to the layout caches. When the limit is reached everything is forgotten
    at once, which is crude and costs one re-set of what is on screen.

    **The math face has to be loaded.** `advtext.ui.fonts.load_fonts` leaves
    `Face.MATH` out by default (`TEXT_FACES`) and loads it on first use, which
    draws the first frame of the first formula in whatever face is bound and
    then stalls for about a second (measured by review 0, not here). A host
    that turns math on should ask for `ALL_FACES` up front.

    `resolve` is `formula_fonts`'s: leave it out for the real font. Whatever
    it is, the document's own measure must be able to resolve the math font
    keys in the boxes; `advtext.style.fontlib_metrics` does.
    """
    from advtext.markdown import MathRefused

    faces: dict[Scaled, MathFonts] = {}
    built: dict[tuple[str, bool, Scaled], Box | MathRefused] = {}

    def build(source: str, display: bool, size: Scaled) -> Box | MathRefused:
        key = (source, display, size)
        found = built.get(key)
        if found is None:
            if len(built) >= remember:
                built.clear()
            result = typeset(source, size, display=display, resolve=resolve, fonts=faces.get(size))
            if isinstance(result, Refusal):
                found = MathRefused(result.reason, result.position)
            else:
                faces[size] = result.fonts
                found = result.box
            built[key] = found
        return found

    return build


# --------------------------------------------------------------------------------
# The tables. A command is in exactly one of them.
# --------------------------------------------------------------------------------


def _char(kind: AtomType, codepoint: int, limits: Limits = Limits.DEFAULT) -> Atom:
    return Atom(kind, MathChar(codepoint), limits=limits)


def _upright(text: str) -> SubList:
    """
    A run of characters as ordinary atoms, in the math face's upright forms.
    """
    return SubList(tuple(Atom(AtomType.ORD, MathChar(ord(character))) for character in text))


_ITALIC_RANGES: Final = (
    (ord("a"), ord("z"), 0x1D44E),
    (ord("A"), ord("Z"), 0x1D434),
    (0x03B1, 0x03C9, 0x1D6FC),
)

_ITALIC_EXCEPTIONS: Final = {
    ord("h"): 0x210E,
    0x2202: 0x1D715,
    0x03F5: 0x1D716,
    0x03D1: 0x1D717,
    0x03F0: 0x1D718,
    0x03D5: 0x1D719,
    0x03F1: 0x1D71A,
    0x03D6: 0x1D71B,
}
"""
`advtext.ui.formulas._ITALIC_EXCEPTIONS`, plus the six variant Greek letters,
whose italic forms sit after the block rather than inside it.
"""


def _italic(codepoint: int) -> int:
    if codepoint in _ITALIC_EXCEPTIONS:
        return _ITALIC_EXCEPTIONS[codepoint]
    for first, last, target in _ITALIC_RANGES:
        if first <= codepoint <= last:
            return target + codepoint - first
    return codepoint


def _table(kind: AtomType, entries: dict[str, int]) -> dict[str, Atom]:
    return {name: _char(kind, codepoint) for name, codepoint in entries.items()}


# unicode-math's assignment: \epsilon and \phi are the lunate and the stroked
# forms, \varepsilon and \varphi the ones inside the Greek block.
_GREEK_LOWER: Final = {
    "alpha": 0x03B1,
    "beta": 0x03B2,
    "gamma": 0x03B3,
    "delta": 0x03B4,
    "epsilon": 0x03F5,
    "varepsilon": 0x03B5,
    "zeta": 0x03B6,
    "eta": 0x03B7,
    "theta": 0x03B8,
    "vartheta": 0x03D1,
    "iota": 0x03B9,
    "kappa": 0x03BA,
    "varkappa": 0x03F0,
    "lambda": 0x03BB,
    "mu": 0x03BC,
    "nu": 0x03BD,
    "xi": 0x03BE,
    "pi": 0x03C0,
    "varpi": 0x03D6,
    "rho": 0x03C1,
    "varrho": 0x03F1,
    "sigma": 0x03C3,
    "varsigma": 0x03C2,
    "tau": 0x03C4,
    "upsilon": 0x03C5,
    "phi": 0x03D5,
    "varphi": 0x03C6,
    "chi": 0x03C7,
    "psi": 0x03C8,
    "omega": 0x03C9,
}

_GREEK_UPPER: Final = {
    "Gamma": 0x0393,
    "Delta": 0x0394,
    "Theta": 0x0398,
    "Lambda": 0x039B,
    "Xi": 0x039E,
    "Pi": 0x03A0,
    "Sigma": 0x03A3,
    "Upsilon": 0x03A5,
    "Phi": 0x03A6,
    "Psi": 0x03A8,
    "Omega": 0x03A9,
}

_ORDS: Final = {
    "infty": 0x221E,
    "partial": 0x1D715,
    "nabla": 0x2207,
    "hbar": 0x210F,
    "ell": 0x2113,
    "forall": 0x2200,
    "exists": 0x2203,
    "emptyset": 0x2205,
    "Re": 0x211C,
    "Im": 0x2111,
    "aleph": 0x2135,
    "neg": 0x00AC,
    "lnot": 0x00AC,
    "angle": 0x2220,
    "prime": 0x2032,
    "top": 0x22A4,
    "bot": 0x22A5,
    "imath": 0x1D6A4,
    "jmath": 0x1D6A5,
    "vdots": 0x22EE,
    "vert": 0x007C,
    "Vert": 0x2016,
    "|": 0x2016,
    "backslash": 0x005C,
    "%": 0x0025,
    "#": 0x0023,
    "&": 0x0026,
    "_": 0x005F,
    "$": 0x0024,
}

_BINS: Final = {
    "pm": 0x00B1,
    "mp": 0x2213,
    "times": 0x00D7,
    "div": 0x00F7,
    "cdot": 0x22C5,
    "ast": 0x2217,
    "star": 0x22C6,
    "circ": 0x2218,
    "bullet": 0x2219,
    "cap": 0x2229,
    "cup": 0x222A,
    "wedge": 0x2227,
    "land": 0x2227,
    "vee": 0x2228,
    "lor": 0x2228,
    "setminus": 0x2216,
    "oplus": 0x2295,
    "ominus": 0x2296,
    "otimes": 0x2297,
    "odot": 0x2299,
}

_RELS: Final = {
    "le": 0x2264,
    "leq": 0x2264,
    "ge": 0x2265,
    "geq": 0x2265,
    "ne": 0x2260,
    "neq": 0x2260,
    "equiv": 0x2261,
    "approx": 0x2248,
    "sim": 0x223C,
    "simeq": 0x2243,
    "cong": 0x2245,
    "propto": 0x221D,
    "ll": 0x226A,
    "gg": 0x226B,
    "in": 0x2208,
    "notin": 0x2209,
    "ni": 0x220B,
    "subset": 0x2282,
    "supset": 0x2283,
    "subseteq": 0x2286,
    "supseteq": 0x2287,
    "to": 0x2192,
    "rightarrow": 0x2192,
    "gets": 0x2190,
    "leftarrow": 0x2190,
    "leftrightarrow": 0x2194,
    "Rightarrow": 0x21D2,
    "Leftarrow": 0x21D0,
    "Leftrightarrow": 0x21D4,
    "longrightarrow": 0x27F6,
    "implies": 0x27F9,
    "iff": 0x27FA,
    "mapsto": 0x21A6,
    "uparrow": 0x2191,
    "downarrow": 0x2193,
    "mid": 0x2223,
    "parallel": 0x2225,
    "perp": 0x27C2,
    "vdash": 0x22A2,
    "models": 0x22A8,
}

_OPENS: Final = {
    "{": 0x007B,
    "lbrace": 0x007B,
    "langle": 0x27E8,
    "lfloor": 0x230A,
    "lceil": 0x2308,
    "lvert": 0x007C,
    "lVert": 0x2016,
}

_CLOSES: Final = {
    "}": 0x007D,
    "rbrace": 0x007D,
    "rangle": 0x27E9,
    "rfloor": 0x230B,
    "rceil": 0x2309,
    "rvert": 0x007C,
    "rVert": 0x2016,
}

_PUNCTS: Final = {"colon": 0x003A}

# \mathinner in plain TeX: dots are spaced as a unit from what they separate.
_INNERS: Final = {"ldots": 0x2026, "dots": 0x2026, "cdots": 0x22EF, "ddots": 0x22F1}

# The engine's default: stacked in display style, beside the operator inline.
_BIG_OPS: Final = {
    "sum": 0x2211,
    "prod": 0x220F,
    "coprod": 0x2210,
    "bigcup": 0x22C3,
    "bigcap": 0x22C2,
    "bigvee": 0x22C1,
    "bigwedge": 0x22C0,
    "bigoplus": 0x2A01,
    "bigotimes": 0x2A02,
}

# LaTeX's \int is \intop\nolimits: the bounds stay beside it in every style.
_INTEGRALS: Final = {"int": 0x222B, "iint": 0x222C, "iiint": 0x222D, "oint": 0x222E}

# Operator names. The first group takes limits in display the way \lim does.
_FUNCTIONS_WITH_LIMITS: Final = ("lim", "max", "min", "sup", "inf", "det", "gcd", "Pr")
_FUNCTIONS: Final = (
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "arcsin",
    "arccos",
    "arctan",
    "sinh",
    "cosh",
    "tanh",
    "log",
    "ln",
    "lg",
    "exp",
    "arg",
    "deg",
    "dim",
    "ker",
    "hom",
)


def _build_symbols() -> dict[str, Atom]:
    symbols: dict[str, Atom] = {}
    for name, codepoint in _GREEK_LOWER.items():
        symbols[name] = _char(AtomType.ORD, _italic(codepoint))
    symbols.update(_table(AtomType.ORD, _GREEK_UPPER))
    symbols.update(_table(AtomType.ORD, _ORDS))
    symbols.update(_table(AtomType.BIN, _BINS))
    symbols.update(_table(AtomType.REL, _RELS))
    symbols.update(_table(AtomType.OPEN, _OPENS))
    symbols.update(_table(AtomType.CLOSE, _CLOSES))
    symbols.update(_table(AtomType.PUNCT, _PUNCTS))
    symbols.update(_table(AtomType.INNER, _INNERS))
    symbols.update(_table(AtomType.OP, _BIG_OPS))
    for name, codepoint in _INTEGRALS.items():
        symbols[name] = _char(AtomType.OP, codepoint, Limits.NO_LIMITS)
    for name in _FUNCTIONS_WITH_LIMITS:
        symbols[name] = Atom(AtomType.OP, _upright(name))
    for name in _FUNCTIONS:
        symbols[name] = Atom(AtomType.OP, _upright(name), limits=Limits.NO_LIMITS)
    return symbols


_SYMBOLS: Final = _build_symbols()
"""
Every command that is one atom, by name without the backslash.
"""

# TeX's own math codes for the characters of plain ASCII. `-` and `*` are set as
# the minus sign and the asterisk operator, which is what a math font means by
# them; `:` is a relation (`\colon` is the punctuation); `!` and `?` are Close.
_CHARACTERS: Final = {
    "+": _char(AtomType.BIN, 0x002B),
    "-": _char(AtomType.BIN, 0x2212),
    "*": _char(AtomType.BIN, 0x2217),
    "=": _char(AtomType.REL, 0x003D),
    "<": _char(AtomType.REL, 0x003C),
    ">": _char(AtomType.REL, 0x003E),
    ":": _char(AtomType.REL, 0x003A),
    "(": _char(AtomType.OPEN, 0x0028),
    "[": _char(AtomType.OPEN, 0x005B),
    ")": _char(AtomType.CLOSE, 0x0029),
    "]": _char(AtomType.CLOSE, 0x005D),
    "!": _char(AtomType.CLOSE, 0x0021),
    "?": _char(AtomType.CLOSE, 0x003F),
    ",": _char(AtomType.PUNCT, 0x002C),
    ";": _char(AtomType.PUNCT, 0x003B),
    ".": _char(AtomType.ORD, 0x002E),
    "/": _char(AtomType.ORD, 0x002F),
    "|": _char(AtomType.ORD, 0x007C),
    "@": _char(AtomType.ORD, 0x0040),
}


def _build_unicode() -> dict[str, Atom]:
    """
    A symbol typed as itself rather than by name: `π`, `∑`, `≤`.

    Taken only where a command already produces that glyph, so the class is the
    command's and nothing reaches the math face that the coverage test did not
    check. A Greek letter typed directly is the variable, so it is found by its
    upright codepoint and set italic like the command.
    """
    by_character: dict[str, Atom] = {}
    for name, codepoint in _GREEK_LOWER.items():
        by_character.setdefault(chr(codepoint), _SYMBOLS[name])
    by_character.setdefault(chr(0x2202), _SYMBOLS["partial"])
    for atom in _SYMBOLS.values():
        if isinstance(atom.nucleus, MathChar) and atom.nucleus.codepoint > 0x7F:
            by_character.setdefault(chr(atom.nucleus.codepoint), atom)
    by_character.setdefault(chr(0x2212), _CHARACTERS["-"])
    return by_character


_UNICODE: Final = _build_unicode()

_TEXT_COMMANDS: Final = ("mathrm", "operatorname")

_BLACKBOARD_HOLES: Final = {
    "C": 0x2102,
    "H": 0x210D,
    "N": 0x2115,
    "P": 0x2119,
    "Q": 0x211A,
    "R": 0x211D,
    "Z": 0x2124,
}
_SCRIPT_HOLES: Final = {
    "B": 0x212C,
    "E": 0x2130,
    "F": 0x2131,
    "H": 0x210B,
    "I": 0x2110,
    "L": 0x2112,
    "M": 0x2133,
    "R": 0x211B,
}


def _alphabet(command: str, character: str) -> int | None:
    r"""
    One letter in `\mathbb`, `\mathbf` or `\mathcal`, or `None` if it has no form.

    Unicode's mathematical alphanumerics, with the holes the Letterlike Symbols
    block had already filled. `\mathbb` and `\mathcal` are capitals only, which
    is what the commands mean in LaTeX; `\mathbf` takes letters and digits.
    """
    if not character.isascii():
        return None
    upper = "A" <= character <= "Z"
    offset = ord(character) - ord("A")
    if command == "mathbb":
        if not upper:
            return None
        return _BLACKBOARD_HOLES.get(character, 0x1D538 + offset)
    if command == "mathcal":
        if not upper:
            return None
        return _SCRIPT_HOLES.get(character, 0x1D49C + offset)
    if upper:
        return 0x1D400 + offset
    if "a" <= character <= "z":
        return 0x1D41A + ord(character) - ord("a")
    if "0" <= character <= "9":
        return 0x1D7CE + ord(character) - ord("0")
    return None


_ALPHABET_COMMANDS: Final = ("mathbb", "mathbf", "mathcal")
_STRUCTURES: Final = (
    *("frac", "overline", "underline", "limits", "nolimits"),
    *("sqrt", "left", "right", "binom"),
)

_SPACES: Final[dict[str, Atom]] = {
    ",": THIN_SPACE,
    "thinspace": THIN_SPACE,
    ":": MED_SPACE,
    ">": MED_SPACE,
    "medspace": MED_SPACE,
    ";": THICK_SPACE,
    "thickspace": THICK_SPACE,
    "!": NEGATIVE_THIN_SPACE,
    "negthinspace": NEGATIVE_THIN_SPACE,
    "quad": QUAD,
    "qquad": QQUAD,
    " ": Atom(AtomType.SPACE, MuGlue(6, stretch=3, shrink=2)),
}
r"""
The explicit spaces, as the engine's own `SPACE` atoms: plain TeX's three
muskips and the macros built on them, with amsmath's long names for the same.

`\quad` is eighteen math units of the style it lands in, which is plain TeX's
one em everywhere but in a script (`advtext.math.atoms.QUAD` has the detail).

`\ ` (and `~`, which is the same space with a break forbidden, and nothing in
a formula breaks here) is six math units, stretching three and shrinking two.
In TeX it is the *text* font's interword glue (`app_space`), which is not a
number of mu; six is what that glue comes to in plain TeX's own text font
(cmr10: 3.33pt plus 1.67pt minus 1.11pt against a ten-point quad of eighteen
mu), and is exact for nothing else. It also shrinks in a script, where TeX's
does not. That is the engine's existing `SPACE` item and no new rule
(review 2, item 10); the alternative -- the prose face's own space as an
Ord -- has the right width in one face and the wrong class in all of them.
"""

_PROSE: Final[dict[str, Face]] = {
    "text": Face.PROSE,
    "textrm": Face.PROSE,
    "textnormal": Face.PROSE,
    "textit": Face.PROSE_ITALIC,
    "textbf": Face.PROSE_BOLD,
}
r"""
The commands that set words inside a formula, and the prose face each one uses.
"""

_DELIMITER_CHARACTERS: Final[dict[str, int | None]] = {
    "(": 0x0028,
    ")": 0x0029,
    "[": 0x005B,
    "]": 0x005D,
    "|": 0x007C,
    "/": 0x002F,
    "<": 0x27E8,
    ">": 0x27E9,
    ".": None,
}
_DELIMITER_COMMANDS: Final[dict[str, int]] = {
    "{": 0x007B,
    "lbrace": 0x007B,
    "}": 0x007D,
    "rbrace": 0x007D,
    "lbrack": 0x005B,
    "rbrack": 0x005D,
    "|": 0x2016,
    "Vert": 0x2016,
    "vert": 0x007C,
    "langle": 0x27E8,
    "rangle": 0x27E9,
    "lfloor": 0x230A,
    "rfloor": 0x230B,
    "lceil": 0x2308,
    "rceil": 0x2309,
    "backslash": 0x005C,
}
r"""
What may follow `\left` and `\right`: a character or a command, to a codepoint.

`.` is the null delimiter (`None`). Every codepoint here has a chain of
vertical variants in Latin Modern Math -- eight sizes each, the largest about
three em (`tests/test_mathtext.py` reads the font and holds that). A delimiter
with no chain could only ever be set at its one size, so the arrows (two sizes)
and everything else are not in the tables and are refused after a `\left`.
"""

_NEVER: Final[tuple[tuple[RefusalKind, str, tuple[str, ...]], ...]] = (
    (
        RefusalKind.DELIMITER,
        "needs a brace that stretches sideways, which the math engine does not build",
        ("overbrace", "underbrace"),
    ),
    (
        RefusalKind.DELIMITER,
        r"asks for a delimiter of a named size; only \left and \right size one, to its content",
        (
            *("big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr"),
            *("biggl", "biggr", "Biggl", "Biggr", "bigm", "Bigm", "biggm", "Biggm"),
        ),
    ),
    (
        RefusalKind.DELIMITER,
        r"puts a delimiter between a \left and its \right, which the math engine does not build",
        ("middle",),
    ),
    (
        RefusalKind.STYLE,
        r"is a binomial at a named style, which a math list cannot say; write \binom",
        ("dbinom", "tbinom"),
    ),
    (
        RefusalKind.RADICAL,
        "places a degree over the radical sign, which the math engine's radical does not take",
        ("root",),
    ),
    (
        RefusalKind.SPACING,
        r"is a space the math engine has no item for; it has \, \: \; \! \quad and \qquad",
        (
            *("space", "enspace", "hspace", "mspace", "kern", "mkern", "hskip", "mskip"),
            *("phantom", "hphantom", "vphantom"),
        ),
    ),
    (
        RefusalKind.TEXT,
        r"sets a box at the text size whatever the style around it; write \text{...}",
        ("mbox", "hbox"),
    ),
    (
        RefusalKind.ACCENT,
        "is an accent, which the math engine does not build",
        (
            *("hat", "widehat", "bar", "vec", "tilde", "widetilde", "dot", "ddot"),
            *("acute", "grave", "breve", "check", "overrightarrow", "overleftarrow"),
        ),
    ),
    (
        RefusalKind.STYLE,
        "changes the style or the font of what follows it, which a math list cannot say",
        (
            *("displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle"),
            *("dfrac", "tfrac", "cfrac", "rm", "bf", "it", "cal", "boldsymbol", "bm"),
            *("mathit", "mathsf", "mathtt", "mathfrak", "mathscr", "color", "textcolor"),
        ),
    ),
    (
        RefusalKind.INFIX,
        r"is an infix fraction; write \frac{..}{..}",
        ("over", "atop", "choose", "above", "brace", "brack"),
    ),
    (
        RefusalKind.MACRO,
        "defines a macro, and there are none here",
        (
            *("def", "newcommand", "renewcommand", "let", "gdef", "edef"),
            *("DeclareMathOperator", "providecommand"),
        ),
    ),
    (
        RefusalKind.ENVIRONMENT,
        "opens or closes an environment, and there are none here",
        ("begin", "end"),
    ),
    (
        RefusalKind.MATRIX,
        "is a matrix, and matrices are left out for now",
        ("matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "array", "cases", "substack"),
    ),
    (
        RefusalKind.ALIGNMENT,
        "breaks a line or a column, and nothing here is aligned",
        ("\\", "cr", "newline", "hline", "tag", "label", "nonumber", "notag"),
    ),
)


def _refusals() -> dict[str, tuple[RefusalKind, str]]:
    table: dict[str, tuple[RefusalKind, str]] = {}
    for kind, reason, names in _NEVER:
        for name in names:
            table[name] = (kind, reason)
    return table


_REFUSED: Final = _refusals()

_MATRIX_ENVIRONMENTS: Final = frozenset(
    {"matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "array"}
)


def supported_commands() -> tuple[str, ...]:
    r"""
    Every command name `parse` accepts, without the backslash, sorted.

    One-character names are control symbols: `"{"` is `\{`. For a page that
    lists the subset and for the test that checks each one against the font.
    """
    return tuple(
        sorted({*_SYMBOLS, *_TEXT_COMMANDS, *_ALPHABET_COMMANDS, *_STRUCTURES, *_SPACES, *_PROSE})
    )


def sized_delimiters() -> dict[str, int | None]:
    r"""
    What may follow `\left` or `\right`, as it is written, to the codepoint sized.

    A key is a bare character (`"("`, `"<"`) or a command with its backslash
    (`"\\{"`, `"\\langle"`). `"."` maps to `None`: the null delimiter, which
    sets nothing and still closes the pair.
    """
    table: dict[str, int | None] = dict(_DELIMITER_CHARACTERS)
    table.update({"\\" + name: codepoint for name, codepoint in _DELIMITER_COMMANDS.items()})
    return table


def refused_commands() -> dict[str, RefusalKind]:
    """
    Every command `parse` recognises in order to refuse it, and the kind it gives.

    A command in neither this nor `supported_commands` is `UNKNOWN_COMMAND`.
    """
    return {name: kind for name, (kind, _) in sorted(_REFUSED.items())}


# --------------------------------------------------------------------------------
# The parser
# --------------------------------------------------------------------------------


class _Refused(Exception):
    """
    Raised inside the descent and caught by `parse`, and nowhere else.
    """

    def __init__(self, kind: RefusalKind, reason: str, position: int) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.position = position


class _Parser:
    """
    One pass over one source. Scannerless: `index` is the only state but depth.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.index = 0
        self.depth = 0

    # ---- entry --------------------------------------------------------------

    def formula(self) -> tuple[MathItem, ...]:
        items = self.items(opened_at=None)
        if not items:
            raise _Refused(RefusalKind.EMPTY, "there is nothing between the dollars", 0)
        return items

    # ---- scanning -----------------------------------------------------------

    def skip_blanks(self) -> None:
        source, index = self.source, self.index
        while index < len(source) and source[index].isspace():
            index += 1
        self.index = index

    def peek(self) -> str:
        """
        The next non-blank character, or `""` at the end. Consumes the blanks.
        """
        self.skip_blanks()
        return self.source[self.index] if self.index < len(self.source) else ""

    def command_name(self) -> str:
        r"""
        Read `\name` or `\x` at `index`, which is on the backslash.
        """
        source = self.source
        start = self.index + 1
        if start >= len(source):
            raise _Refused(RefusalKind.SYNTAX, "a backslash with nothing after it", self.index)
        end = start
        while end < len(source) and source[end].isascii() and source[end].isalpha():
            end += 1
        if end == start:
            end = start + 1
        self.index = end
        return source[start:end]

    def enter(self, position: int) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise _Refused(
                RefusalKind.NESTING, f"nested more than {MAX_DEPTH} levels deep", position
            )

    # ---- lists --------------------------------------------------------------

    def items(self, opened_at: int | None, left_at: int | None = None) -> tuple[MathItem, ...]:
        r"""
        A list of atoms up to the end, or up to the `}` matching `opened_at`,
        or -- when `left_at` is the position of a `\left` -- up to its `\right`.

        The `}` is consumed; the `\right` is not, because its delimiter follows
        it and `left_right` reads the two together.
        """
        out: list[MathItem] = []
        while True:
            character = self.peek()
            position = self.index
            if not character:
                if left_at is not None:
                    raise _Refused(RefusalKind.SYNTAX, r"a \left with no \right after it", left_at)
                if opened_at is not None:
                    raise _Refused(RefusalKind.SYNTAX, "a { that is never closed", opened_at)
                break
            if character == "}":
                if left_at is not None:
                    raise _Refused(
                        RefusalKind.SYNTAX, r"a } between a \left and its \right", position
                    )
                if opened_at is None:
                    raise _Refused(RefusalKind.SYNTAX, "a } with no { before it", position)
                self.index += 1
                break
            if character == "\\" and self.at_command("right", position):
                if left_at is None:
                    raise _Refused(
                        RefusalKind.SYNTAX, r"a \right with no \left before it", position
                    )
                break
            if character in "^_'":
                # TeX's rule: a script with nothing to hang on hangs on nothing.
                out.append(self.scripts(Atom(AtomType.ORD)))
                continue
            parsed = self.atom()
            # A space is glue, not a noad: a script after one hangs on nothing
            # (the branch above, next time round), not on the space.
            out.append(parsed if parsed.kind is AtomType.SPACE else self.scripts(parsed))
        return tuple(out)

    def at_command(self, name: str, position: int) -> bool:
        r"""
        Whether the command at `position` is exactly `\name`, and not `\namesake`.
        """
        end = position + 1 + len(name)
        if not self.source.startswith(name, position + 1):
            return False
        following = self.source[end : end + 1]
        return not (following.isascii() and following.isalpha())

    def group(self) -> tuple[MathItem, ...]:
        """
        `{ ... }` at `index`, which is on the brace.
        """
        opened_at = self.index
        self.enter(opened_at)
        self.index += 1
        items = self.items(opened_at)
        self.depth -= 1
        return items

    def argument(self, of: str, position: int) -> SubList:
        """
        What a script or a command takes: a braced group, or exactly one atom.
        """
        character = self.peek()
        if character == "{":
            return SubList(self.group())
        if not character or character in "}^_'":
            raise _Refused(RefusalKind.SYNTAX, f"{of} has nothing after it", position)
        self.enter(self.index)
        parsed = self.atom()
        self.depth -= 1
        return SubList((parsed,))

    def braced_text(self, of: str, position: int) -> str:
        """
        The raw characters of `{...}` after a letters command: plain ASCII only.
        """
        if self.peek() != "{":
            raise _Refused(RefusalKind.SYNTAX, f"{of} needs a braced argument", position)
        start = self.index + 1
        end = self.source.find("}", start)
        if end < 0:
            raise _Refused(RefusalKind.SYNTAX, "a { that is never closed", self.index)
        for offset in range(start, end):
            character = self.source[offset]
            if character in "{\\$" or not (character.isspace() or " " <= character <= "~"):
                raise _Refused(
                    RefusalKind.CHARACTER,
                    f"{of} takes plain ASCII only, with no commands or braces inside",
                    offset,
                )
        self.index = end + 1
        return "".join(" " if c.isspace() else c for c in self.source[start:end])

    # ---- atoms --------------------------------------------------------------

    def atom(self) -> Atom:
        """
        One atom without its scripts. `index` is on a non-blank that is not `}`.
        """
        position = self.index
        character = self.source[position]
        if character == "{":
            items = self.group()
            if len(items) == 1:
                only = items[0]
                if (
                    isinstance(only, Atom)
                    and only.kind is AtomType.ORD
                    and only.sup is None
                    and only.sub is None
                ):
                    # §1186: a group holding one bare ordinary atom is that atom.
                    return only
            return Atom(AtomType.ORD, SubList(items))
        if character == "\\":
            return self.command(position)
        self.index += 1
        if character.isascii() and character.isalpha():
            return _char(AtomType.ORD, _italic(ord(character)))
        if character.isascii() and character.isdigit():
            return _char(AtomType.ORD, ord(character))
        found = _CHARACTERS.get(character) or _UNICODE.get(character)
        if found is not None:
            return found
        if character == "~":
            return _SPACES[" "]
        if character == "&":
            raise _Refused(
                RefusalKind.ALIGNMENT, "& separates columns, and nothing here is aligned", position
            )
        if character == "#":
            raise _Refused(
                RefusalKind.MACRO, "# is a macro parameter, and there are none here", position
            )
        if character == "$":
            raise _Refused(RefusalKind.SYNTAX, "a $ inside a formula", position)
        if character == "%":
            raise _Refused(
                RefusalKind.SYNTAX, r"% starts a comment; write \% for the sign", position
            )
        raise _Refused(
            RefusalKind.CHARACTER,
            f"the character {character!r} (U+{ord(character):04X}) is not in the subset",
            position,
        )

    def command(self, position: int) -> Atom:
        name = self.command_name()
        if name.isspace():
            name = " "
        shown = "backslash-space" if name == " " else "\\" + name
        symbol = _SYMBOLS.get(name)
        if symbol is not None:
            return symbol
        if name == "frac":
            numerator = self.argument(shown, position)
            denominator = self.argument(shown, position)
            return Atom(AtomType.INNER, SubList((Fraction(numerator, denominator),)))
        if name == "overline":
            return Atom(AtomType.OVER, self.argument(shown, position))
        if name == "underline":
            return Atom(AtomType.UNDER, self.argument(shown, position))
        space = _SPACES.get(name)
        if space is not None:
            return space
        if name == "sqrt":
            if self.peek() == "[":
                kind, reason = _REFUSED["root"]
                raise _Refused(kind, f"\\sqrt[n] {reason}", position)
            return Atom(AtomType.RADICAL, self.argument(shown, position))
        if name == "binom":
            return self.binomial(shown, position)
        if name == "left":
            return self.left_right(position)
        if name == "right":
            raise _Refused(RefusalKind.SYNTAX, r"a \right with no \left before it", position)
        face = _PROSE.get(name)
        if face is not None:
            return Atom(AtomType.ORD, MathText(self.prose(shown, position), face))
        if name in _TEXT_COMMANDS:
            letters = _upright(self.braced_text(shown, position).replace(" ", ""))
            if name == "mathrm":
                return Atom(AtomType.ORD, letters)
            return Atom(AtomType.OP, letters, limits=Limits.NO_LIMITS)
        if name in _ALPHABET_COMMANDS:
            return self.alphabet(name, shown, position)
        if name in ("limits", "nolimits"):
            raise _Refused(RefusalKind.SYNTAX, f"{shown} must follow an operator", position)
        if name == "begin":
            self.refuse_environment(position)
        refused = _REFUSED.get(name)
        if refused is not None:
            raise _Refused(refused[0], f"{shown} {refused[1]}", position)
        raise _Refused(RefusalKind.UNKNOWN_COMMAND, f"{shown} is not in the subset", position)

    def left_right(self, position: int) -> Atom:
        r"""
        `\left<d> ... \right<d>` with `index` just past `\left`: one Inner atom.

        What TeX builds (`math_left_right`) and what
        `advtext.math.atoms.delimited` builds by hand: an Inner whose nucleus
        is `LEFT, body..., RIGHT`, so the pair spaces as Inner outside, as Open
        and Close inside, and scripts hang off the whole of it. The delimiters
        are not sized here -- that needs the body set, and so a style, and it
        is the engine's to do when the list is converted.
        """
        self.enter(position)
        opening = self.delimiter(r"\left", position)
        body = self.items(None, left_at=position)
        closed_at = self.index
        self.command_name()
        closing = self.delimiter(r"\right", closed_at)
        self.depth -= 1
        return Atom(
            AtomType.INNER,
            SubList((Atom(AtomType.LEFT, opening), *body, Atom(AtomType.RIGHT, closing))),
        )

    def binomial(self, shown: str, position: int) -> Atom:
        r"""
        `\binom{n}{k}`: one over the other with no bar, between parentheses that fit.

        Both halves exist in the engine already: `Fraction(thickness=0)` is
        `\atop` (§745), and `LEFT`/`RIGHT` size a pair to the list they stand
        in. So this is `{\left( {n \atop k} \right)}`, an Ord as amsmath's is.
        It is not quite TeX's: `\atopwithdelims` takes its delimiters at a
        size the font states for the style (`delim1`, `delim2`, §748) and
        `make_left_right` fits them to the content, so the parentheses here
        can come out a variant smaller or larger than LaTeX's. `\dbinom` and
        `\tbinom` name a style, which a math list cannot say, and are refused.
        """
        self.enter(position)
        upper = self.argument(shown, position)
        lower = self.argument(shown, position)
        self.depth -= 1
        return Atom(
            AtomType.ORD,
            SubList(
                (
                    Atom(AtomType.LEFT, MathChar(0x0028)),
                    Fraction(upper, lower, thickness=0),
                    Atom(AtomType.RIGHT, MathChar(0x0029)),
                )
            ),
        )

    def delimiter(self, of: str, position: int) -> MathChar | None:
        r"""
        The delimiter after a `\left` or `\right`: a math character, or `None` for `.`.
        """
        character = self.peek()
        here = self.index
        if not character:
            raise _Refused(RefusalKind.SYNTAX, f"{of} has no delimiter after it", position)
        if character == "\\":
            name = self.command_name()
            codepoint = _DELIMITER_COMMANDS.get(name)
            if codepoint is None:
                raise _Refused(
                    RefusalKind.DELIMITER,
                    f"\\{name} is not a delimiter {of} can size",
                    here,
                )
            return MathChar(codepoint)
        if character not in _DELIMITER_CHARACTERS:
            raise _Refused(
                RefusalKind.DELIMITER, f"{character!r} is not a delimiter {of} can size", here
            )
        self.index += 1
        found = _DELIMITER_CHARACTERS[character]
        return None if found is None else MathChar(found)

    def prose(self, of: str, position: int) -> str:
        r"""
        The words of `\text{...}`: anything printable, with no markup inside.

        Blanks are kept, a run of them as one space, because `\text{ if }` is
        how a formula asks for the air around a word. A brace, a backslash or
        a dollar inside would be a group, a command or math within the text;
        none of that is done, so each is refused rather than set as itself.
        """
        if self.peek() != "{":
            raise _Refused(RefusalKind.SYNTAX, f"{of} needs a braced argument", position)
        start = self.index + 1
        end = self.source.find("}", start)
        if end < 0:
            raise _Refused(RefusalKind.SYNTAX, "a { that is never closed", self.index)
        out: list[str] = []
        for offset in range(start, end):
            character = self.source[offset]
            if character.isspace():
                if not out or out[-1] != " ":
                    out.append(" ")
            elif character in "{\\$":
                raise _Refused(
                    RefusalKind.TEXT,
                    f"{of} takes plain words only, with no commands, braces or math inside",
                    offset,
                )
            elif not character.isprintable():
                raise _Refused(
                    RefusalKind.CHARACTER,
                    f"the character U+{ord(character):04X} in {of} cannot be printed",
                    offset,
                )
            else:
                out.append(character)
        self.index = end + 1
        return "".join(out)

    def alphabet(self, name: str, shown: str, position: int) -> Atom:
        start = self.index
        text = self.braced_text(shown, position)
        codepoints: list[int] = []
        for character in text.replace(" ", ""):
            codepoint = _alphabet(name, character)
            if codepoint is None:
                raise _Refused(
                    RefusalKind.CHARACTER, f"{shown} has no form of {character!r}", start
                )
            codepoints.append(codepoint)
        if len(codepoints) == 1:
            return _char(AtomType.ORD, codepoints[0])
        return Atom(
            AtomType.ORD, SubList(tuple(_char(AtomType.ORD, codepoint) for codepoint in codepoints))
        )

    def refuse_environment(self, position: int) -> None:
        r"""
        `\begin{...}`: a matrix if it names one, an environment otherwise.
        """
        rest = self.source[self.index :].lstrip()
        if rest.startswith("{"):
            name = rest[1 : rest.find("}")] if "}" in rest else ""
            if name.rstrip("*") in _MATRIX_ENVIRONMENTS or name in ("cases", "substack"):
                kind, reason = _REFUSED["matrix"]
                raise _Refused(kind, f"\\begin{{{name}}} {reason}", position)

    # ---- scripts ------------------------------------------------------------

    def scripts(self, base: Atom) -> Atom:
        r"""
        `base` with whatever `^`, `_`, `'`, `\limits` and `\nolimits` follow it.
        """
        sup: list[MathItem] | None = None
        sub: tuple[MathItem, ...] | None = None
        primed = False
        limits = base.limits
        while True:
            character = self.peek()
            here = self.index
            if character == "'":
                if sup is not None and not primed:
                    raise _Refused(RefusalKind.SYNTAX, "a prime after a superscript", here)
                self.index += 1
                sup = [] if sup is None else sup
                sup.append(_SYMBOLS["prime"])
                primed = True
            elif character == "^":
                if sup is not None and not primed:
                    raise _Refused(RefusalKind.SYNTAX, "a second superscript on one atom", here)
                self.index += 1
                sup = [] if sup is None else sup
                sup.extend(self.argument("^", here).items)
                primed = False
            elif character == "_":
                if sub is not None:
                    raise _Refused(RefusalKind.SYNTAX, "a second subscript on one atom", here)
                self.index += 1
                sub = self.argument("_", here).items
            elif character == "\\" and self.source.startswith(("\\limits", "\\nolimits"), here):
                name = self.command_name()
                if name not in ("limits", "nolimits"):
                    self.index = here
                    break
                if base.kind is not AtomType.OP:
                    raise _Refused(RefusalKind.SYNTAX, f"\\{name} must follow an operator", here)
                limits = Limits.LIMITS if name == "limits" else Limits.NO_LIMITS
            else:
                break
        if sup is None and sub is None and limits is base.limits:
            return base
        return replace(
            base,
            sup=base.sup if sup is None else SubList(tuple(sup)),
            sub=base.sub if sub is None else SubList(sub),
            limits=limits,
        )

r"""
`mlist_to_hlist`: a math list becomes horizontal material `hpack` can measure.

This is TeX's §726-§767, and the sigma litmus test lives here. Two passes, for
the reason §726 gives: the first pass translates each atom into boxes and
records how tall the tallest of them came out, and only then does the second
pass know enough to put the right amount of air between them. Neither pass can
be folded into the other because a `Bin` does not know whether it is binary
until its neighbours have been seen.

**`make_op` and the display-size operator.** §749 enlarges a big operator by
following the font's variant chain **exactly one step** -- no size-fitting
search, unlike `var_delimiter` at §708 -- and only in display style. Latin
Modern Math carries a real chain for U+2211, so the display sigma here is a
different glyph drawn by a type designer rather than the body glyph scaled up.
That distinction is the whole point of the test (`docs/decisions.md`), and it
is why `imscribe.fontlib` mints a codepoint for `summation.v1`: the font leaves
it unencoded and a `CharNode` can carry nothing else.

OpenType states the same rule differently -- "the first variant at least
`DisplayOperatorMinHeight` tall" -- and for this font the two agree, which
`tests/test_fontmetrics.py` pins. We follow TeX's, because the rest of this
module is TeX's.

**The operator is centred on the math axis, not on the baseline.** §749's
`shift_amount := half(height - depth) - axis_height` puts the glyph's vertical
middle on the axis, which is where `-` and `=` sit. `AxisHeight` is real font
data (250/1000 em here), not a fraction of the em anybody chose.

**The spacing table is transcribed, not derived.** §764's 64-character string is
below, verbatim, checked against `tex.web:15064`. It is the single largest
contributor to whether a formula reads as set rather than typed: `a+b` with Bin
spacing looks right and with Ord spacing looks like a variable name.

**Script sizes come from the font.** `ScriptPercentScaleDown` (70) and
`ScriptScriptPercentScaleDown` (50) are in Latin Modern Math's `MATH` table.
`docs/tex-notes.md` §10 notes that the 0.7/0.5 magnifications are `plain.tex`
defaults and are **not in `tex.web`** at all -- the source only provides the
mechanism, `fam_fnt(f+size)`. Taking them from the font is strictly better than
taking them from a convention.

**Delimiters are chosen, never built.** `var_delimiter` (`tex.web:13906`) does
two things: it walks a character's chain of ever-larger variants for the first
one tall enough, and failing that it *assembles* one from a top, a bottom and
as many repeats of a middle piece as it takes. Only the first half is here.
`_delimiter_box` walks the font's vertical variant chain -- for Latin Modern
Math, eight parentheses up to 2.99 em and five surds up to 3 em. When the last
entry is still too short TeX returns the largest it found ("if no variant is
large enough, it returns the largest available", `tex.web:13895`). Here a
`\left`/`\right` delimiter does the same while the largest covers three
quarters of the content (`LARGEST_VARIANT_MUST_COVER`, which is this project's
number and not TeX's), and below that -- and for a radical always -- it raises
`DelimiterTooSmallError`. That refusal is the one place this module departs
from the source on purpose, because a caller can turn a refusal into something
honest and cannot do anything with a formula that is quietly wrong. Glyph
assembly stays out of scope, as `docs/decisions.md` has it.

That one function serves `make_radical` (`tex.web:14476`) and
`make_left_right` (`tex.web:15017`).

**A surd is hung from its ink, not from its baseline.** `make_radical` assumes
a TFM convention: the surd's *height* is the thickness of the rule that joins
it and everything else is depth, so `shift_amount := -(height(x)+clr)` puts the
glyph's top stroke level with the rule. An OpenType surd is an ordinary outline
and four of Latin Modern Math's five straddle the axis instead. So the rule
thickness comes from the font's `RadicalRuleThickness`, and the glyph is
shifted by whatever puts the top of its ink where TeX's arithmetic puts the top
of the rule -- which is the same position, reached without the convention.
XeTeX does the equivalent by rewriting the box's height and depth.

**Three numbers here are plain.tex's and are scaled to the em.**
`\delimiterfactor` (901) is a ratio. `\delimitershortfall` (5pt) and
`\nulldelimiterspace` (1.2pt) are lengths chosen for ten-point type, and are
kept as that *proportion* -- half a quad and 0.12 of one -- rather than as
absolute lengths, so that whether a delimiter is big enough does not depend on
the pixel size a host happens to set the formula at. That is a choice, and it
is a different one from `SCRIPT_SPACE` below, which predates it and is absolute.

Deliberately out of scope, each because it needs machinery this project does not
have and `docs/decisions.md` rules out:

- **Extensible delimiters**, as above, and with them `\atopwithdelims`. §748
  wraps a fraction in delimiters and we stop before it; with TeX's own null
  delimiter that step contributes two empty boxes of `\nulldelimiterspace`, so
  the omission is a missing space and not a missing structure.
- **A radical's degree.** `\root 3 \of x` is a plain.tex macro over boxes.
- **Accents**, which walk a width-fitting chain (§740).
- **`\mathchoice`**, `\middle`, and `\nonscript`.
- **Penalties after Bin and Rel atoms** (§766's `bin_op_penalty`,
  `rel_penalty`). They exist so a *line breaker* can cut an inline formula, and
  nothing in this project produces inline math -- `imscribe.markdown` emits no
  `MathOn`/`MathOff` -- so they would be nodes with no reader.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TypeAlias

from imscribe.fontmetrics import Face, FontMetrics, MathFontMetrics, MathParams
from imscribe.math.atoms import (
    MED_MU,
    THICK_MU,
    THIN_MU,
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
    cramped_style,
    denom_style,
    is_cramped,
    is_display,
    num_style,
    size_for,
    sub_style,
    sup_style,
)
from imscribe.nodes import Box, BoxKind, CharNode, FontKey, Glue, GlueSpec, Kern, Node, Rule
from imscribe.pack import CharMeasure, PackMode, hpack, vpack
from imscribe.style import MetricsResolver, char_measure, font_key, interword_glue
from imscribe.units import RUNNING, UNITY, GlueOrder, Scaled, sp_from_pt

__all__ = [
    "DELIMITER_FACTOR",
    "MATH_SPACING",
    "SURD",
    "DelimiterTooSmallError",
    "MathFonts",
    "MathLayoutError",
    "MathResolver",
    "TextFaceUnavailableError",
    "math_fonts",
    "mlist_to_hlist",
]

MATH_SPACING = "0234000122*4000133**3**344*0400400*000000234000111*1111112341011"
r"""
§764's `math_spacing`, verbatim, checked character by character against
`tex.web:15064`. Indexed `8*row + column` with row and column the *spacing
class* of the left and right atom (§765's magic offset reduces to exactly that).

    0  no space
    1  conditional thin  (\nonscript\mskip\thinmuskip)
    2  thin              (\mskip\thinmuskip)
    3  conditional medium
    4  conditional thick
    *  impossible

"Conditional" means the space is dropped in script and scriptscript styles.
An impossible entry is one the Bin-to-Ord conversion of §727 makes unreachable,
so reaching one is a bug in that conversion rather than in the formula.
"""


# plain.tex's \thinmuskip, \medmuskip and \thickmuskip. They are macro-package
# values and not in tex.web; `imscribe.math.atoms` holds them, because an explicit
# `\,` and the table's thin space must be the same three math units.
THIN_MU_SKIP = THIN_MU
MED_MU_SKIP = MED_MU
THICK_MU_SKIP = THICK_MU

# \scriptspace, plain.tex's 0.5pt. §756 adds it to the width of every script box
# so a following glyph does not touch the script that precedes it.
SCRIPT_SPACE = sp_from_pt(0.5)

# §726 starts the first pass with `r_type := op_noad`, which is what makes a
# leading Bin become Ord: there is nothing to its left to bind.
_FIRST_PASS_INITIAL = AtomType.OP

# §727: a Bin in any of these contexts is not binary.
_BIN_BECOMES_ORD_AFTER = frozenset(
    {AtomType.BIN, AtomType.OP, AtomType.REL, AtomType.OPEN, AtomType.PUNCT}
)

# §727, the other direction: one of these following a Bin demotes that Bin.
_DEMOTES_A_PRECEDING_BIN = frozenset({AtomType.REL, AtomType.CLOSE, AtomType.PUNCT})

_NOT_IMPLEMENTED = {
    AtomType.ACCENT: "an accent walks a width-fitting chain (§740), which this project has not",
}

SURD = 0x221A
r"""
U+221A SQUARE ROOT, the one delimiter a radical is built from.

TeX's `radical_noad` carries its delimiter in a field (`left_delimiter`,
`tex.web:13483`) because `\radical` takes it as an argument; every radical
anybody writes passes the same one, so it is a constant here.
"""

DELIMITER_FACTOR = 901
r"""
plain.tex's `\delimiterfactor`: a delimiter must cover this many thousandths of
twice the content's greater reach from the axis (`tex.web:15025`).
"""

DELIMITER_SHORTFALL = sp_from_pt(5.0)
r"""
plain.tex's `\delimitershortfall`: 5pt, **absolute**, as TeX has it
(`tex.web:15026`, `delta2:=delta1+delta1-delimiter_shortfall`; the parameter is
a dimension, `tex.web:5312`). However tall the content, the delimiter may fall
short of it by at most this.

It was half a math quad here until review 2 (item 9) measured that an
em-relative shortfall never decides: at half a quad, `2*delta1 - shortfall`
exceeds 90.1% of `2*delta1` only once `delta1` passes 2.5 quads, and the
largest ready-made parenthesis is 1.5 quads from the axis. As a length it does
what the source means it to: at a small size it is generous, at a large one it
is strict. The value is plain.tex's and is not in `tex.web`.
"""

LARGEST_VARIANT_MUST_COVER = (3, 4)
r"""
How much of the content the largest variant of a `\left`/`\right` delimiter
must cover to be used when no variant satisfies TeX's rule: three quarters.

**This number is the lead's, not TeX's** (`.concerns/lead--demo-review2-findings.md`,
item 9, amending D1). TeX with no extensible recipe returns the largest variant
however short it falls (`tex.web:13895`); the first version of this module
refused anything the rule did not accept, and C-mathtext2 measured ordinary
formulas -- a fraction with stacked limits between `\left(` and `\right)` --
refused for being 3 to 5 percent too tall. So the largest variant is used, as
TeX would, while it reaches three quarters of twice the content's greater reach
from the axis, and below that the formula is refused. A numerator and a
denominator so that integer arithmetic states the boundary exactly.

A radical does not get this: see `_make_radical`.
"""

_NULL_DELIMITER_SPACE_QUADS = 0.12
r"""
plain.tex's `\nulldelimiterspace` of 1.2pt, likewise: the width of `\left.`.
"""


class MathLayoutError(ValueError):
    """
    A formula this module will not set, as opposed to one it set wrongly.

    The base of everything `mlist_to_hlist` raises about its *input* when the
    input is well formed and merely beyond what the fonts in hand can do. A
    caller with somewhere else to put the source -- inline code, say -- catches
    this one type. `NotImplementedError` (an accent) and `AssertionError` (a
    broken invariant) are not under it and are not that kind of news.
    """


class DelimiterTooSmallError(MathLayoutError):
    """
    No variant of a delimiter is tall enough for what it has to cover.

    `needed` and `largest` are height plus depth in scaled points, `codepoint`
    is the delimiter as the formula named it. Raised instead of returning the
    largest variant, which is what TeX does when it has no extensible recipe
    to fall back on and which sets a delimiter that visibly does not reach.
    """

    def __init__(self, codepoint: int, needed: Scaled, largest: Scaled) -> None:
        super().__init__(
            f"U+{codepoint:04X} has no variant {needed} sp tall (the largest is {largest} sp), "
            "and delimiters are not assembled from pieces here"
        )
        self.codepoint = codepoint
        self.needed = needed
        self.largest = largest


class TextFaceUnavailableError(MathLayoutError):
    """
    A formula holds prose and the fonts it was given cannot measure prose.

    `math_fonts` was called without `text`, or `text` did not know the face.
    """


class MissingGlyphError(MathLayoutError):
    r"""
    Prose in a formula holds a character the face it is to be set in does not have.

    `character` is the first such character and `face` the prose face asked.
    Raised rather than set: a `CharNode` for a glyph the face lacks measures as
    nothing and draws as nothing, so `v = \text{...}` came out as a formula
    with a hole after the equals sign (review 2, item 5). A formula is one
    face's work at one size and is not patched from another face the way a
    paragraph's characters are (`imscribe.markdown`); the caller's fallback --
    the source, as code -- is.
    """

    def __init__(self, character: str, face: Face) -> None:
        super().__init__(
            f"{face.value} has no glyph for {character!r} (U+{ord(character):04X}), "
            "and a formula is not patched from another face"
        )
        self.character = character
        self.face = face


_HANDLED_BY_THE_FIRST_PASS = frozenset({AtomType.LEFT, AtomType.RIGHT, AtomType.SPACE})

MathResolver: TypeAlias = Callable[[Scaled], MathFontMetrics]
"""
The math face at a size in scaled points.

Injected rather than imported so the tests can drive the whole algorithm from a
fake with round numbers and still check `make_op` against the real font where
that is the claim being made.
"""


@dataclass(frozen=True, slots=True)
class MathFonts:
    """
    The math face at all three sizes a formula needs, and how to measure it.

    Three faces rather than one scaled three ways because that is what §699's
    `fam_fnt(f+size)` names and what a math font is drawn for; the script faces
    have heavier strokes so they survive being small.
    """

    sizes: dict[MathSize, Scaled]
    faces: dict[MathSize, MathFontMetrics]
    keys: dict[MathSize, FontKey]
    measure: CharMeasure
    text: MetricsResolver | None = None
    """
    How a prose face is resolved for a `MathText`, or `None` if it cannot be.

    `measure` consults it for every font key that is not one of the three math
    keys, so a box holding prose packs through the same `measure` as the rest
    of the formula and nobody has to know which characters were which.
    """

    def face(self, style: Style) -> MathFontMetrics:
        """
        The face this style is set from (§703).
        """
        return self.faces[size_for(style)]

    def params(self, style: Style) -> MathParams:
        """
        TeX's σ and ξ parameters at this style's size.
        """
        return self.face(style).math

    def key(self, style: Style) -> FontKey:
        """
        What a `CharNode` set at this style carries.
        """
        return self.keys[size_for(style)]

    def mu(self, style: Style) -> Scaled:
        """
        §703's `cur_mu`: one math unit is a eighteenth of the math quad.
        """
        return round(self.params(style).math_quad / 18)


def math_fonts(
    base_size: Scaled, resolve: MathResolver, *, text: MetricsResolver | None = None
) -> MathFonts:
    """
    Build the three sizes from one, using the font's own script percentages.

    `text` resolves every font key that is not a math key -- which is to say
    the prose faces a `MathText` is set in. Without it a formula holding prose
    raises `TextFaceUnavailableError` rather than the `KeyError` from inside
    `hpack` that used to be the only symptom, and a formula holding none is
    unaffected. `imscribe.style.fontlib_metrics` is the production value; it is
    not the default because this module is driven by fakes in the tests and a
    default that opens font files would be a default nobody asked for.
    """
    text_face = resolve(base_size)
    scales = text_face.math
    sizes = {
        MathSize.TEXT: base_size,
        MathSize.SCRIPT: round(base_size * scales.script_scale),
        MathSize.SCRIPT_SCRIPT: round(base_size * scales.script_script_scale),
    }
    faces = {size: (text_face if size is MathSize.TEXT else resolve(sizes[size])) for size in sizes}
    keys = {size: font_key(Face.MATH, sizes[size]) for size in sizes}
    by_key: dict[FontKey, FontMetrics] = {keys[size]: faces[size] for size in sizes}

    def metrics_for(key: FontKey) -> FontMetrics:
        found = by_key.get(key)
        if found is not None:
            return found
        if text is None:
            raise TextFaceUnavailableError(
                f"{key!r} is not a math font and these MathFonts were built without `text`"
            )
        return text(key)

    return MathFonts(
        sizes=sizes,
        faces=faces,
        keys=keys,
        measure=char_measure(metrics_for),
        text=text,
    )


def _half(value: Scaled) -> Scaled:
    """
    TeX's `half(x)`, which rounds an odd value *away* from zero on the low side.
    """
    return (value + 1) // 2 if value % 2 else value // 2


@dataclass(frozen=True, slots=True)
class _Translated:
    """
    One atom after the first pass: what it spaces as, and what it became.

    `kind` is `None` for a node that is not a noad -- an explicit space -- which
    the second pass links in without consulting the table (`tex.web:15000`).
    """

    kind: AtomType | None
    nodes: tuple[Node, ...]


def mlist_to_hlist(
    items: Sequence[MathItem],
    style: Style,
    fonts: MathFonts,
) -> list[Node]:
    """
    Convert a math list into horizontal material at one style (§726).

    The result is unpacked: a caller `hpack`s it, with `fonts.measure`.
    """
    return _second_pass(_first_pass(items, style, fonts), style, fonts)


# --------------------------------------------------------------------------------
# First pass: every atom becomes boxes
# --------------------------------------------------------------------------------


_BOUNDARY_SPACES_AS = {AtomType.LEFT: AtomType.OPEN, AtomType.RIGHT: AtomType.CLOSE}


def _spacing_type(item: MathItem) -> AtomType:
    """
    What this item spaces as before §727's conversions are applied.

    A boundary is `Open` or `Close` from the start. TeX keeps `left_noad` and
    `right_noad` apart until the second pass, but lists them beside `open_noad`
    and `close_noad` in both of §727's tests (`tex.web:14335`, 14339), so
    nothing in the first pass can tell the difference.
    """
    if not isinstance(item, Atom):
        return AtomType.INNER
    return _BOUNDARY_SPACES_AS.get(item.kind, item.kind)


def _first_pass(items: Sequence[MathItem], style: Style, fonts: MathFonts) -> list[_Translated]:
    """
    Translate each atom, settling whether each `Bin` is really binary (§727).

    `last` is TeX's `r`, "the most recent noad preceding `q`" (`tex.web:14287`):
    an explicit space is a node and not a noad, so it neither becomes `r` nor
    changes `r_type`, and a `Bin` binds straight through it.
    """
    out: list[_Translated] = []
    previous = _FIRST_PASS_INITIAL
    last: int | None = None
    boundaries: list[tuple[int, Atom]] = []
    for item in items:
        if isinstance(item, Atom) and item.kind is AtomType.SPACE:
            out.append(_Translated(None, (_math_space(item, style, fonts),)))
            continue
        kind = _spacing_type(item)
        if kind is AtomType.BIN and previous in _BIN_BECOMES_ORD_AFTER:
            kind = AtomType.ORD
        elif (
            kind in _DEMOTES_A_PRECEDING_BIN and last is not None and out[last].kind is AtomType.BIN
        ):
            out[last] = replace(out[last], kind=AtomType.ORD)
        last = len(out)
        if isinstance(item, Atom) and item.kind in _BOUNDARY_SPACES_AS:
            # Sized below, once the height and depth of the whole list are known.
            boundaries.append((last, item))
            out.append(_Translated(kind, ()))
        else:
            out.append(_Translated(kind, tuple(_translate(item, style, fonts))))
        previous = kind
    # §727 again, at the end: a list ending in a Bin has nothing for it to bind.
    if last is not None and out[last].kind is AtomType.BIN:
        out[last] = replace(out[last], kind=AtomType.ORD)
    if boundaries:
        _size_boundaries(out, boundaries, style, fonts)
    return out


def _size_boundaries(
    out: list[_Translated], boundaries: Sequence[tuple[int, Atom]], style: Style, fonts: MathFonts
) -> None:
    """
    Give each `LEFT` and `RIGHT` its delimiter, sized to the list it stands in.

    TeX does this in the second pass, "since `max_h` and `max_d` are now known"
    (`tex.web:14965`); every atom has been translated by the time this runs, so
    it is the same moment. `max_h` and `max_d` are §727's `check_dimensions`
    (`tex.web:14315`): each *noad's* hlist, packed, and nothing else -- an
    explicit space contributes no height, and the boundaries themselves have no
    hlist yet. Both delimiters are sized from the same two numbers at the same
    style, "so they will have consistent sizes" (`tex.web:15012`).

    The extra `hpack` per atom is paid only by a list that holds a boundary.
    """
    skip = {index for index, _ in boundaries}
    max_h: Scaled = 0
    max_d: Scaled = 0
    for index, translated in enumerate(out):
        if translated.kind is None or index in skip:
            continue
        packed = hpack(list(translated.nodes), measure=fonts.measure).box
        max_h = max(max_h, packed.height)
        max_d = max(max_d, packed.depth)
    for index, atom in boundaries:
        box = _make_left_right(atom, style, max_d, max_h, fonts)
        out[index] = replace(out[index], nodes=(box,))


def _math_space(atom: Atom, style: Style, fonts: MathFonts) -> Glue:
    """
    An explicit space as glue, its math units scaled by `cur_mu` (§716).

    `tex.web:14363`: "Convert math glue to ordinary glue", through `math_glue`
    at 14098. TeX has a kern form as well (`math_kern`, 14120) for `\\mkern`;
    one form is enough here, since a spec with no stretch or shrink sets
    exactly as a kern would in a box that is packed to its natural width.
    """
    if not isinstance(atom.nucleus, MuGlue):
        raise TypeError(f"a SPACE atom carries a MuGlue, not {atom.nucleus!r}")
    return Glue(_from_mu(atom.nucleus, fonts.mu(style)))


def _translate(item: MathItem, style: Style, fonts: MathFonts) -> list[Node]:
    """
    One atom's `new_hlist`: its nucleus, with scripts attached if it has any.
    """
    if isinstance(item, Fraction):
        return _make_fraction(item, style, fonts)

    reason = _NOT_IMPLEMENTED.get(item.kind)
    if reason is not None:
        raise NotImplementedError(f"{item.kind.name} atoms are not supported: {reason}")

    if item.kind in _HANDLED_BY_THE_FIRST_PASS:
        raise AssertionError(f"{item.kind.name} is placed by the first pass, not translated")

    if item.kind is AtomType.OP:
        nodes, delta, finished = _make_op(item, style, fonts)
        if finished:
            return nodes
    elif item.kind is AtomType.RADICAL:
        nodes, delta = _make_radical(item, style, fonts), 0
    elif item.kind is AtomType.OVER:
        nodes, delta = _make_over(item, style, fonts), 0
    elif item.kind is AtomType.UNDER:
        nodes, delta = _make_under(item, style, fonts), 0
    elif item.kind is AtomType.VCENTER:
        nodes, delta = _make_vcenter(item, style, fonts), 0
    else:
        nodes, delta = _translate_nucleus(item.nucleus, style, fonts)

    if item.sup is None and item.sub is None:
        return nodes
    return _make_scripts(nodes, item, delta, style, fonts)


def _translate_nucleus(field: Field, style: Style, fonts: MathFonts) -> tuple[list[Node], Scaled]:
    """
    A nucleus as nodes, and TeX's `delta` -- the italic correction (§755).

    A math character is followed by a kern of its italic correction, which is
    what leans a script off the end of an integral sign.
    """
    match field:
        case None:
            return [], 0
        case MathChar(codepoint):
            face = fonts.face(style)
            delta = round(face.italic_correction(codepoint))
            nodes: list[Node] = [CharNode(fonts.key(style), codepoint)]
            if delta:
                nodes.append(Kern(width=delta))
            return nodes, delta
        case SubBox(box):
            return [box], 0
        case SubList(items):
            return mlist_to_hlist(items, style, fonts), 0
        case MathText():
            return [_text_box(field, style, fonts)], 0
        case MuGlue():
            raise TypeError("a MuGlue is the nucleus of a SPACE atom and of nothing else")


def _clean_box(field: Field, style: Style, fonts: MathFonts) -> Box:
    """
    §720's `clean_box`: a field, converted at a given style and packed into one box.

    The "simplify a trivial box" step (§721) drops the italic-correction kern
    after a lone character **without narrowing the box**. That is not a tidy-up:
    the width still includes the correction, and only the kern node goes, so a
    later `rebox` can put the glyph back where it belongs.
    """
    already: Box | None = None
    nodes: list[Node] = []
    match field:
        case None:
            nodes = []
        case MathChar():
            nodes, _ = _translate_nucleus(field, style, fonts)
        case SubBox(box):
            if box.shift_amount == 0:
                already = box
            nodes = [box]
        case SubList(items):
            nodes = mlist_to_hlist(items, style, fonts)
        case MathText():
            already = _text_box(field, style, fonts)
        case MuGlue():
            raise TypeError("a MuGlue is the nucleus of a SPACE atom and of nothing else")
    if already is not None:
        return already

    packed = hpack(nodes, measure=fonts.measure).box
    contents = packed.contents
    if len(contents) == 2 and isinstance(contents[0], CharNode) and isinstance(contents[1], Kern):
        packed = replace(packed, contents=(contents[0],))
    return packed


def _text_box(field: MathText, style: Style, fonts: MathFonts) -> Box:
    r"""
    Prose inside a formula, packed at the size of the style it landed in.

    What `\text{...}` gives (amsmath's, which follows the style; plain TeX's
    `\hbox` would stay at text size in a subscript). Set the way
    `imscribe.markdown` sets a run of prose -- the face's own pair kerning, and
    an interword glue for each space -- except that every space is kept,
    leading and trailing ones too, because here they are the request.

    The glue keeps its stretch and shrink, which do nothing: the box is packed
    to its natural width and so is everything it is ever put in.

    Raises `MissingGlyphError` for a character the face has no glyph for.
    """
    if fonts.text is None:
        raise TextFaceUnavailableError(
            f"{field.text!r} is prose, and these MathFonts were built without `text`"
        )
    key = font_key(field.face, fonts.sizes[size_for(style)])
    try:
        metrics = fonts.text(key)
    except MathLayoutError:
        raise
    except Exception as error:
        raise TextFaceUnavailableError(f"{field.face.value} did not resolve: {error}") from error
    space = round(metrics.space_width)
    nodes: list[Node] = []
    characters = field.text
    for index, character in enumerate(characters):
        if character.isspace():
            nodes.append(Glue(interword_glue(space)))
            continue
        if not metrics.has(ord(character)):
            raise MissingGlyphError(character, field.face)
        nodes.append(CharNode(key, ord(character)))
        following = characters[index + 1 : index + 2]
        if following and not following.isspace():
            kern = round(metrics.kern(ord(character), ord(following)))
            if kern:
                nodes.append(Kern(width=kern))
    return hpack(nodes, measure=fonts.measure).box


# --------------------------------------------------------------------------------
# var_delimiter, and the two things that call it
# --------------------------------------------------------------------------------


def _delimiter_box(
    codepoint: int,
    style: Style,
    needed: Scaled,
    fonts: MathFonts,
    *,
    at_least: Scaled | None = None,
) -> tuple[Box, MathSize]:
    """
    The smallest variant of a delimiter whose height plus depth is `needed` or more.

    Returned with the size of the font it was found in, which is not always
    the style's: see the outer loop below. A caller that draws something to
    meet the glyph -- a radical's rule -- needs that font's numbers.

    `at_least` is what the largest variant must reach to be used when none
    reaches `needed`. Left out, it is `needed`: nothing short is ever returned.

    `var_delimiter`'s search (`tex.web:13941-13968`) without its extensible
    half. Two loops, as there: the outer one runs from the font of the current
    size up to the text font (`z:=z+s+16; repeat z:=z-16 ... until z<16`), so a
    delimiter in a subscript is tried at script size first and borrows a larger
    font only if it must; the inner one follows the variant chain
    (`list_tag`). The first character tall enough wins.

    The box is `char_box`'s (`tex.web:13980`): the one character, with its
    italic correction in the width. Unshifted -- the two callers shift it by
    different rules.

    Raises `DelimiterTooSmallError` when the largest it saw is under
    `at_least`, where TeX would settle for it; the module docstring says why.
    """
    floor = needed if at_least is None else min(at_least, needed)
    largest: Scaled = 0
    fallback: tuple[Box, MathSize] | None = None
    size = size_for(style)
    while True:
        face = fonts.faces[size]
        key = fonts.keys[size]
        chain = face.vertical_variants(codepoint)
        for candidate in [variant.codepoint for variant in chain] or [codepoint]:
            node = CharNode(key, candidate)
            dimens = fonts.measure(node)
            extent = dimens.height + dimens.depth
            if extent < needed and extent <= largest:
                continue
            box = Box(
                kind=BoxKind.HLIST,
                contents=(node,),
                width=dimens.width + round(face.italic_correction(candidate)),
                height=dimens.height,
                depth=dimens.depth,
            )
            if extent >= needed:
                return box, size
            # `tex.web:13954`: "if hd>w then begin f:=g; c:=y; w:=hd" -- the
            # largest so far is remembered in case nothing is large enough.
            largest = extent
            fallback = (box, size)
        if size is MathSize.TEXT:
            if fallback is not None and largest >= floor:
                return fallback
            raise DelimiterTooSmallError(codepoint, needed, largest)
        size = MathSize(size - 16)


def _make_left_right(
    atom: Atom, style: Style, max_d: Scaled, max_h: Scaled, fonts: MathFonts
) -> Box:
    r"""
    `make_left_right` (`tex.web:15017-15030`): one delimiter of a `\left`/`\right`.

    `delta1` is the content's greater reach from the *axis*, up or down, so the
    delimiter is symmetric about the axis even when the content is not. It must
    then cover `delimiter_factor` thousandths of twice that, and may not fall
    short of twice that by more than `delimiter_shortfall` (`tex.web:15025`
    and 15026, both as written: 901 and an absolute 5pt). The division by 500
    before the multiplication is the source's, kept: it is how TeX avoids
    overflow and it costs under a hundredth of a point.

    The smallest variant satisfying both is taken. When none does, the largest
    is -- TeX's own answer for a font with no extensible recipe
    (`tex.web:13895`) -- provided it covers `LARGEST_VARIANT_MUST_COVER` of
    twice `delta1`, and the formula is refused only below that. That fraction
    is not TeX's; the constant's docstring says whose it is and why.

    The box comes back centred on the axis, which is `var_delimiter`'s last act
    (`tex.web:13932`) and is applied to the null delimiter too.
    """
    params = fonts.params(style)
    axis = round(params.axis_height)
    delta2 = max_d + axis
    delta1 = max_h + max_d - delta2
    if delta2 > delta1:
        delta1 = delta2
    delta = (delta1 // 500) * DELIMITER_FACTOR
    delta2 = delta1 + delta1 - DELIMITER_SHORTFALL
    if delta < delta2:
        delta = delta2
    # Not TeX's: what the largest variant must reach when none reaches `delta`.
    numerator, denominator = LARGEST_VARIANT_MUST_COVER
    covering = -((-2 * delta1 * numerator) // denominator)

    match atom.nucleus:
        case None:
            box = Box(
                kind=BoxKind.HLIST,
                width=round(params.math_quad * _NULL_DELIMITER_SPACE_QUADS),
            )
        case MathChar(codepoint):
            box, _ = _delimiter_box(codepoint, style, delta, fonts, at_least=covering)
        case _:
            raise TypeError(f"a delimiter is one math character or None, not {atom.nucleus!r}")
    return replace(box, shift_amount=_half(box.height - box.depth) - axis)


def _make_radical(atom: Atom, style: Style, fonts: MathFonts) -> list[Node]:
    """
    `make_radical` (`tex.web:14476-14490`): a surd, a rule, and the radicand under it.

    The radicand is set **cramped**, so a superscript inside does not rise into
    the rule. The clearance between it and the rule is larger in display style
    -- TeX computes `default_rule_thickness + |math_x_height|/4` there and
    `default_rule_thickness * 5/4` elsewhere, and the font states both results.
    The surd is then the smallest variant covering radicand, clearance and
    rule, and whatever it has to spare is split: "the symbol will be placed so
    that the actual clearance is `clr` plus half the excess" (`tex.web:14472`).

    The glyph hangs from the top of its ink; see the module docstring. In TeX's
    terms `depth(y)` is the surd's height plus depth less the rule thickness.

    The result is one box, as it is in the source (`hpack(y,natural)`), so
    scripts hang off the whole radical.

    **A radical is refused when no surd covers it**, and does not take the
    largest-variant allowance a `\\left` pair has: a parenthesis that stops
    short still reads as a parenthesis, and a surd that does not reach its
    rule is a broken sign (the lead's decision, review 2 item 9).
    """
    params = fonts.params(style)
    radicand = _clean_box(atom.nucleus, cramped_style(style), fonts)
    thickness = round(params.radical_rule_thickness)
    if is_display(style):
        clearance = round(params.radical_display_style_vertical_gap)
    else:
        clearance = round(params.radical_vertical_gap)

    covered = radicand.height + radicand.depth + clearance
    surd, found_at = _delimiter_box(SURD, style, covered + thickness, fonts)
    # `tex.web:14489`: `overbar(x,clr,height(y))` -- the rule is as thick as the
    # surd *that was found* says, not as the current size's rule. They differ
    # when a radical in a script outgrows the script font's chain and borrows a
    # text-size surd, whose stroke is the text font's: review 2 suspected the
    # rule then kept the script face's thickness and stepped at the join, and
    # it did (measured in `tests/test_mathlist.py`).
    thickness = round(fonts.faces[found_at].math.radical_rule_thickness)
    excess = (surd.height + surd.depth - thickness) - covered
    if excess > 0:
        clearance += _half(excess)
    top = radicand.height + clearance + thickness
    surd = replace(surd, shift_amount=surd.height - top)
    return [hpack([surd, _overbar(radicand, clearance, thickness)], measure=fonts.measure).box]


# \hss: no natural width, infinitely stretchable and infinitely shrinkable, so
# a pair of them centres whatever sits between them at any target width.
_HSS = Glue(
    GlueSpec(
        width=0,
        stretch=UNITY,
        stretch_order=GlueOrder.FIL,
        shrink=UNITY,
        shrink_order=GlueOrder.FIL,
    )
)


def _rebox(box: Box, width: Scaled, fonts: MathFonts) -> Box:
    """
    §715's `rebox`: re-centre a box in a new width, using `\\hss` either side.

    A vlist is wrapped rather than unwrapped -- §715 hpacks it first, so its
    contents become the single box itself and the centring applies to the whole
    thing. The single-character case gets an explicit kern first, because
    `clean_box` folded an italic correction into the width and centring the
    glyph without compensating would push it half a correction to the left.
    """
    if box.width == width or not box.contents:
        return replace(box, width=width)
    contents: list[Node] = [box] if box.kind is BoxKind.VLIST else list(box.contents)
    first = contents[0]
    if len(contents) == 1 and isinstance(first, CharNode):
        advance = fonts.measure(first).width
        if advance != box.width:
            contents.append(Kern(width=box.width - advance))
    return hpack([_HSS, *contents, _HSS], width, PackMode.EXACTLY, measure=fonts.measure).box


# --------------------------------------------------------------------------------
# make_op: the sigma path
# --------------------------------------------------------------------------------


def _make_op(atom: Atom, style: Style, fonts: MathFonts) -> tuple[list[Node], Scaled, bool]:
    """
    §749: enlarge, centre on the axis, and stack the limits if they belong there.

    Returns the material, the sub/superscript offset `delta`, and whether the
    limits were stacked -- in which case the caller must **not** call
    `make_scripts`, because they are already in the box (§733).
    """
    limits = atom.limits
    if limits is Limits.DEFAULT and is_display(style):
        limits = Limits.LIMITS

    face = fonts.face(style)
    nucleus = atom.nucleus
    delta = 0

    if isinstance(nucleus, MathChar):
        codepoint = nucleus.codepoint
        if is_display(style):
            chain = face.vertical_variants(codepoint)
            if len(chain) > 1:
                # Exactly one step (§749). Not a search: `var_delimiter` walks the
                # chain looking for a fit and `make_op` does not.
                codepoint = chain[1].codepoint
        delta = round(face.italic_correction(codepoint))
        box = _clean_box(MathChar(codepoint), style, fonts)
        if atom.sub is not None and limits is not Limits.LIMITS:
            # §749 removes the italic correction when a subscript sits to the
            # right of the operator rather than beneath it.
            box = replace(box, width=box.width - delta)
        shift = _half(box.height - box.depth) - round(face.math.axis_height)
        nucleus = SubBox(replace(box, shift_amount=shift))

    if limits is Limits.LIMITS:
        return [_stack_limits(atom, nucleus, delta, style, fonts)], delta, True

    nodes, _ = _translate_nucleus(nucleus, style, fonts)
    return nodes, delta, False


def _stack_limits(atom: Atom, nucleus: Field, delta: Scaled, style: Style, fonts: MathFonts) -> Box:
    """
    §750 and §751: the upper limit, the operator and the lower limit in a vlist.

    Built by hand rather than by `vpack`, exactly as the source does, because
    the height and depth are *stated*: the vlist's baseline has to stay the
    operator's own, already-axis-centred baseline, and a `vpack` would put it on
    the last box instead. The `big_op_spacing5` kerns are padding that counts
    towards the height and depth, so interline glue sees the formula's full
    extent.
    """
    params = fonts.params(style)
    upper = _clean_box(atom.sup, sup_style(style), fonts)
    middle = _clean_box(nucleus, style, fonts)
    lower = _clean_box(atom.sub, sub_style(style), fonts)

    width = max(upper.width, middle.width, lower.width)
    upper = replace(_rebox(upper, width, fonts), shift_amount=_half(delta))
    middle = _rebox(middle, width, fonts)
    lower = replace(_rebox(lower, width, fonts), shift_amount=-_half(delta))

    padding = round(params.big_op_spacing5)
    height = middle.height
    depth = middle.depth
    contents: list[Node] = []

    if atom.sup is not None:
        # §751: a minimum baseline distance, floored by a minimum gap.
        rise = max(round(params.big_op_spacing3) - upper.depth, round(params.big_op_spacing1))
        contents.extend([Kern(width=padding), upper, Kern(width=rise)])
        height += padding + upper.height + upper.depth + rise

    contents.append(middle)

    if atom.sub is not None:
        drop = max(round(params.big_op_spacing4) - lower.height, round(params.big_op_spacing2))
        contents.extend([Kern(width=drop), lower, Kern(width=padding)])
        depth += padding + lower.height + lower.depth + drop

    return Box(
        kind=BoxKind.VLIST,
        contents=tuple(contents),
        width=width,
        height=height,
        depth=depth,
    )


# --------------------------------------------------------------------------------
# Scripts, fractions, and the bar-and-rule atoms
# --------------------------------------------------------------------------------


def _make_scripts(
    nodes: list[Node], atom: Atom, delta: Scaled, style: Style, fonts: MathFonts
) -> list[Node]:
    """
    §756-§759: attach a subscript, a superscript, or both.

    The two clamps are the ones that keep scripts legible and they are easy to
    misremember: the top of a lone subscript may not rise above **four fifths**
    of the x-height (§757), and the bottom of a superscript may not fall below
    **one quarter** of it (§758). When both are present they must be at least
    `4 * default_rule_thickness` apart, and if they are not the subscript drops
    and then both rise together (§759).
    """
    params = fonts.params(style)
    x_height = abs(round(params.math_x_height))
    smaller = Style.SCRIPT if style < Style.SCRIPT else Style.SCRIPT_SCRIPT
    smaller_params = fonts.params(smaller)

    if isinstance(atom.nucleus, MathChar) and nodes and isinstance(nodes[0], CharNode):
        # §756: a bare character has no box to measure, so the shifts start at
        # zero and the clamps below do all the work. `tex.web:14889` asks
        # `is_char_node(p)` of the nucleus's *translation*, and a nucleus that
        # is a list has been packed into a box by then (`sub_mlist`,
        # `tex.web:14848-14851`), so only a nucleus that is one character can
        # take this branch. This used to ask whether the first node was a
        # character, which a group beginning with a letter also is: `{x^2}^3`
        # hung its 3 where a bare `x^3` would and set as x-superscript-23
        # (review 2, item 1). A group's nodes are not packed here as the source
        # packs them; the box measured below is the same box either way.
        shift_up: Scaled = 0
        shift_down: Scaled = 0
    else:
        enclosing = hpack(nodes, measure=fonts.measure).box
        shift_up = enclosing.height - round(smaller_params.sup_drop)
        shift_down = enclosing.depth + round(smaller_params.sub_drop)

    if atom.sup is None:
        script = _widen(_clean_box(atom.sub, sub_style(style), fonts))
        shift_down = max(shift_down, round(params.sub1), script.height - (x_height * 4) // 5)
        attached: Box = replace(script, shift_amount=shift_down)
    else:
        upper = _widen(_clean_box(atom.sup, sup_style(style), fonts))
        if is_cramped(style):
            clearance = round(params.sup3)
        elif is_display(style):
            clearance = round(params.sup1)
        else:
            clearance = round(params.sup2)
        shift_up = max(shift_up, clearance, upper.depth + x_height // 4)

        if atom.sub is None:
            attached = replace(upper, shift_amount=-shift_up)
        else:
            lower = _widen(_clean_box(atom.sub, sub_style(style), fonts))
            shift_down = max(shift_down, round(params.sub2))
            gap = 4 * round(params.default_rule_thickness) - (
                (shift_up - upper.depth) - (lower.height - shift_down)
            )
            if gap > 0:
                shift_down += gap
                lift = (x_height * 4) // 5 - (shift_up - upper.depth)
                if lift > 0:
                    shift_up += lift
                    shift_down -= lift
            # The superscript sits `delta` to the right of the subscript, which
            # is what makes an integral's bounds lean with the glyph.
            upper = replace(upper, shift_amount=delta)
            separation = Kern(width=(shift_up - upper.depth) - (lower.height - shift_down))
            stacked = vpack([upper, separation, lower]).box
            attached = replace(stacked, shift_amount=shift_down)

    return [*nodes, attached]


def _widen(box: Box) -> Box:
    """
    §756's `width(x) := width(x) + script_space`.
    """
    return replace(box, width=box.width + SCRIPT_SPACE)


def _make_fraction(fraction: Fraction, style: Style, fonts: MathFonts) -> list[Node]:
    """
    §743-§747: numerator over denominator, with the rule centred on the axis.

    The three shift pairs are the ones §744 selects between: display takes
    `num1`/`denom1`, non-display with a rule takes `num2`/`denom2`, and `\\atop`
    -- a thickness of zero -- takes `num3`/`denom2`, sitting slightly higher
    because there is no rule to clear.

    No delimiters: §748 wraps the result with `var_delimiter`, which this project
    does not implement. With TeX's own null delimiter that step adds two empty
    boxes, so what is missing is `\\nulldelimiterspace` either side.
    """
    params = fonts.params(style)
    rule_thickness = round(params.default_rule_thickness)
    thickness = rule_thickness if fraction.thickness is None else fraction.thickness

    numerator = _clean_box(fraction.numerator, num_style(style), fonts)
    denominator = _clean_box(fraction.denominator, denom_style(style), fonts)
    if numerator.width < denominator.width:
        numerator = _rebox(numerator, denominator.width, fonts)
    else:
        denominator = _rebox(denominator, numerator.width, fonts)

    if is_display(style):
        shift_up = round(params.num1)
        shift_down = round(params.denom1)
    else:
        shift_down = round(params.denom2)
        shift_up = round(params.num2) if thickness else round(params.num3)

    axis = round(params.axis_height)
    contents: list[Node]
    if thickness == 0:
        # §745. The gap between the two boxes must reach `clr`; any deficiency is
        # split evenly so the pair stays centred on where it was.
        clearance = 7 * rule_thickness if is_display(style) else 3 * rule_thickness
        short = _half(
            clearance - ((shift_up - numerator.depth) - (denominator.height - shift_down))
        )
        if short > 0:
            shift_up += short
            shift_down += short
        contents = [
            numerator,
            Kern(width=(shift_up - numerator.depth) - (denominator.height - shift_down)),
            denominator,
        ]
    else:
        # §746. The rule straddles the axis, so its edges are at `axis ± half`.
        clearance = 3 * thickness if is_display(style) else thickness
        half = _half(thickness)
        above = clearance - ((shift_up - numerator.depth) - (axis + half))
        below = clearance - ((axis - half) - (denominator.height - shift_down))
        if above > 0:
            shift_up += above
        if below > 0:
            shift_down += below
        contents = [
            numerator,
            Kern(width=(shift_up - numerator.depth) - (axis + half)),
            # §704's `fraction_rule`: height is the thickness, depth zero, width
            # running so it spans whatever box encloses it.
            Rule(width=RUNNING, height=thickness, depth=0),
            Kern(width=(axis - half) - (denominator.height - shift_down)),
            denominator,
        ]

    return [
        Box(
            kind=BoxKind.VLIST,
            contents=tuple(contents),
            width=numerator.width,
            height=shift_up + numerator.height,
            depth=denominator.depth + shift_down,
        )
    ]


def _overbar(box: Box, gap: Scaled, thickness: Scaled) -> Box:
    """
    §705's `overbar`: a rule above a box, with a gap under it and air above it.
    """
    return vpack(
        [
            Kern(width=thickness),
            Rule(width=RUNNING, height=thickness, depth=0),
            Kern(width=gap),
            box,
        ]
    ).box


def _make_over(atom: Atom, style: Style, fonts: MathFonts) -> list[Node]:
    """
    §734: a bar over the nucleus, three rule thicknesses clear of it.
    """
    thickness = round(fonts.params(style).default_rule_thickness)
    inner_box = _clean_box(atom.nucleus, cramped_style(style), fonts)
    return [_overbar(inner_box, 3 * thickness, thickness)]


def _make_under(atom: Atom, style: Style, fonts: MathFonts) -> list[Node]:
    """
    §735: a bar under the nucleus, with the original baseline preserved.

    The height of the result is the nucleus's own height, not the vlist's, which
    is what stops an underlined term pushing the line above it up.
    """
    thickness = round(fonts.params(style).default_rule_thickness)
    inner_box = _clean_box(atom.nucleus, style, fonts)
    stacked = vpack(
        [
            inner_box,
            Kern(width=3 * thickness),
            Rule(width=RUNNING, height=thickness, depth=0),
        ]
    ).box
    total = stacked.height + stacked.depth
    return [replace(stacked, height=inner_box.height, depth=total - inner_box.height)]


def _make_vcenter(atom: Atom, style: Style, fonts: MathFonts) -> list[Node]:
    """
    §736: re-hang a box so its vertical middle is on the axis.
    """
    axis = round(fonts.params(style).axis_height)
    box = _clean_box(atom.nucleus, style, fonts)
    total = box.height + box.depth
    height = axis + _half(total)
    return [replace(box, height=height, depth=total - height)]


# --------------------------------------------------------------------------------
# Second pass: the spacing
# --------------------------------------------------------------------------------


def _second_pass(translated: Sequence[_Translated], style: Style, fonts: MathFonts) -> list[Node]:
    """
    §766: walk the translated atoms and put the table's glue between them.
    """
    out: list[Node] = []
    previous: AtomType | None = None
    for item in translated:
        if item.kind is None:
            # A node, not a noad: linked in as it stands, and `r_type` is left
            # alone, so the atoms either side still space against each other.
            out.extend(item.nodes)
            continue
        if previous is not None:
            spec = _inter_atom_glue(previous, item.kind, style, fonts)
            if spec is not None:
                out.append(Glue(spec))
        out.extend(item.nodes)
        previous = item.kind
    return out


def _inter_atom_glue(
    left: AtomType, right: AtomType, style: Style, fonts: MathFonts
) -> GlueSpec | None:
    """
    The space between two adjacent atoms, or `None` for none at all.
    """
    code = MATH_SPACING[8 * left.spacing_class + right.spacing_class]
    if code == "*":
        raise AssertionError(
            f"{left.name} followed by {right.name} is an impossible pair (§764); "
            "the Bin-to-Ord conversion of §727 should have prevented it"
        )
    if code == "0":
        return None
    # A conditional space is suppressed in script styles, where there is no room
    # for it and the formula is being read as one unit anyway.
    conditional = code in "134"
    if conditional and style >= Style.SCRIPT:
        return None
    mu_glue = {"1": THIN_MU_SKIP, "2": THIN_MU_SKIP, "3": MED_MU_SKIP, "4": THICK_MU_SKIP}[code]
    return _from_mu(mu_glue, fonts.mu(style))


def _from_mu(mu_glue: MuGlue, mu: Scaled) -> GlueSpec:
    """
    §716's `math_glue`: scale a spec expressed in math units into real lengths.
    """
    return GlueSpec(
        width=mu_glue.width * mu,
        stretch=mu_glue.stretch * mu,
        shrink=mu_glue.shrink * mu,
    )

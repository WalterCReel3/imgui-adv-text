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
is why `advtext.fontlib` mints a codepoint for `summation.v1`: the font leaves
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

Deliberately out of scope, each because it needs machinery this project does not
have and `docs/decisions.md` rules out:

- **Delimiters.** No `var_delimiter`, so no `\left`/`\right`, no radical, and no
  `\atopwithdelims`. §748 wraps a fraction in delimiters and we stop before it;
  with TeX's own null delimiter that step contributes two empty boxes of
  `\nulldelimiterspace`, so the omission is a missing space and not a missing
  structure.
- **Accents**, which walk a width-fitting chain (§740).
- **`\mathchoice`**, and the `left_noad`/`right_noad` pair.
- **Penalties after Bin and Rel atoms** (§766's `bin_op_penalty`,
  `rel_penalty`). They exist so a *line breaker* can cut an inline formula, and
  nothing in this project produces inline math -- `advtext.markdown` emits no
  `MathOn`/`MathOff` -- so they would be nodes with no reader.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TypeAlias

from advtext.fontmetrics import Face, MathFontMetrics, MathParams
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
    cramped_style,
    denom_style,
    is_cramped,
    is_display,
    num_style,
    size_for,
    sub_style,
    sup_style,
)
from advtext.nodes import Box, BoxKind, CharNode, FontKey, Glue, GlueSpec, Kern, Node, Rule
from advtext.pack import CharMeasure, PackMode, hpack, vpack
from advtext.style import char_measure, font_key
from advtext.units import RUNNING, UNITY, GlueOrder, Scaled, sp_from_pt

__all__ = [
    "MATH_SPACING",
    "MathFonts",
    "MathResolver",
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


@dataclass(frozen=True, slots=True)
class _MuGlue:
    """
    A glue spec in math units, before it is scaled by `cur_mu`.
    """

    width: int
    stretch: int = 0
    shrink: int = 0


# plain.tex's \thinmuskip, \medmuskip and \thickmuskip. They are macro-package
# values and not in tex.web, which defines only the three glue parameters and
# leaves them zero; these are the ones every LaTeX document has been set with
# since 1984, so they are the ones a reader will recognise the output of.
THIN_MU_SKIP = _MuGlue(3)
MED_MU_SKIP = _MuGlue(4, stretch=2, shrink=4)
THICK_MU_SKIP = _MuGlue(5, stretch=5)

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
    AtomType.RADICAL: "a radical needs var_delimiter (§708), which this project has not",
    AtomType.ACCENT: "an accent walks a width-fitting chain (§740), which this project has not",
}


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


def math_fonts(base_size: Scaled, resolve: MathResolver) -> MathFonts:
    """
    Build the three sizes from one, using the font's own script percentages.
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
    by_key = {keys[size]: faces[size] for size in sizes}
    return MathFonts(
        sizes=sizes,
        faces=faces,
        keys=keys,
        measure=char_measure(lambda key: by_key[key]),
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
    """

    kind: AtomType
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


def _spacing_type(item: MathItem) -> AtomType:
    """
    What this item spaces as before §727's conversions are applied.
    """
    return item.kind if isinstance(item, Atom) else AtomType.INNER


def _first_pass(items: Sequence[MathItem], style: Style, fonts: MathFonts) -> list[_Translated]:
    """
    Translate each atom, settling whether each `Bin` is really binary (§727).
    """
    out: list[_Translated] = []
    previous = _FIRST_PASS_INITIAL
    for item in items:
        kind = _spacing_type(item)
        if kind is AtomType.BIN and previous in _BIN_BECOMES_ORD_AFTER:
            kind = AtomType.ORD
        elif kind in _DEMOTES_A_PRECEDING_BIN and out and out[-1].kind is AtomType.BIN:
            out[-1] = replace(out[-1], kind=AtomType.ORD)
        out.append(_Translated(kind, tuple(_translate(item, style, fonts))))
        previous = kind
    # §727 again, at the end: a list ending in a Bin has nothing for it to bind.
    if out and out[-1].kind is AtomType.BIN:
        out[-1] = replace(out[-1], kind=AtomType.ORD)
    return out


def _translate(item: MathItem, style: Style, fonts: MathFonts) -> list[Node]:
    """
    One atom's `new_hlist`: its nucleus, with scripts attached if it has any.
    """
    if isinstance(item, Fraction):
        return _make_fraction(item, style, fonts)

    reason = _NOT_IMPLEMENTED.get(item.kind)
    if reason is not None:
        raise NotImplementedError(f"{item.kind.name} atoms are not supported: {reason}")

    if item.kind is AtomType.OP:
        nodes, delta, finished = _make_op(item, style, fonts)
        if finished:
            return nodes
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
    if already is not None:
        return already

    packed = hpack(nodes, measure=fonts.measure).box
    contents = packed.contents
    if len(contents) == 2 and isinstance(contents[0], CharNode) and isinstance(contents[1], Kern):
        packed = replace(packed, contents=(contents[0],))
    return packed


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

    if nodes and isinstance(nodes[0], CharNode):
        # §756: a bare character has no box to measure, so the shifts start at
        # zero and the clamps below do all the work.
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


def _from_mu(mu_glue: _MuGlue, mu: Scaled) -> GlueSpec:
    """
    §716's `math_glue`: scale a spec expressed in math units into real lengths.
    """
    return GlueSpec(
        width=mu_glue.width * mu,
        stretch=mu_glue.stretch * mu,
        shrink=mu_glue.shrink * mu,
    )

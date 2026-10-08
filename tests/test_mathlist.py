"""
Math list conversion: the spacing table and the style algebra on a fake font,
`make_op` on the real one.

The split is deliberate and it is the whole argument for the metrics Protocol.
Spacing and styles are *arithmetic*, and a fake with round numbers lets a test
say "the medium space is exactly 40" instead of "the medium space is positive".
`make_op` selecting a display-size operator is not arithmetic -- it is a claim
about what is in `latinmodern-math.otf` -- and a fake would let it pass
vacuously, so those tests open the real font and skip where it is absent.

`FakeMathMetrics` is built at a size of 180 so that one math unit is exactly 10
(`cur_mu` is the math quad over 18, §703). Every spacing number below follows
from that: a thin space is 3 mu, medium is 4, thick is 5.

The second half of the file is the four things the second build added: sized
delimiters, radicals, explicit spaces and prose in a formula. `ChainedFake` is a
fake that *does* have a variant chain, at a size of 18,000 so that
`make_left_right`'s `div 500` has something to divide. The first fake's reason
for having none still holds for what it is used for -- a fabricated chain says
nothing about which summation Latin Modern Math carries -- but which link of a
chain `var_delimiter` stops at is arithmetic, and round numbers are the way to
state a boundary exactly. The real font then answers the questions that are
about the font: that the parentheses and surds are there, in order, and that a
surd hung by this code meets its rule.

Deliberately not here: anything that draws. No display exists.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from advtext import fontlib
from advtext.fontmetrics import Face, GlyphBBox, GlyphVariant, MathParams
from advtext.math import (
    MED_SPACE,
    NEGATIVE_THIN_SPACE,
    QQUAD,
    QUAD,
    THICK_SPACE,
    THIN_SPACE,
    Atom,
    AtomType,
    DelimiterTooSmallError,
    Limits,
    MathChar,
    MathLayoutError,
    MathSize,
    MathText,
    MissingGlyphError,
    MuGlue,
    Style,
    SubBox,
    SubList,
    TextFaceUnavailableError,
    bin_,
    close_,
    cramped_style,
    delimited,
    denom_style,
    frac,
    group,
    inner,
    math_fonts,
    mlist_to_hlist,
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
)
from advtext.math import mlist as mlist_module
from advtext.math.mlist import (
    DELIMITER_FACTOR,
    DELIMITER_SHORTFALL,
    LARGEST_VARIANT_MUST_COVER,
    MATH_SPACING,
    SURD,
    MathFonts,
)
from advtext.nodes import Box, BoxKind, CharNode, Glue, Kern, Node, Rule
from advtext.pack import hpack
from advtext.style import font_key, fontlib_metrics, parse_font_key
from advtext.units import sp_from_pt, sp_from_px

# One math unit comes out at exactly 10 at this size, so thin/medium/thick are
# 30, 40 and 50 and every assertion below can be checked by hand.
FAKE_SIZE = 180
MU = FAKE_SIZE // 18

# Fractions of the em the fake reports, chosen to divide evenly at 180.
AXIS = FAKE_SIZE // 4  # 45
X_HEIGHT = FAKE_SIZE // 2  # 90
RULE_THICKNESS = FAKE_SIZE // 20  # 9


def fake_params(size: int) -> MathParams:
    """
    TeX's math parameters as round fractions of the em, so shifts are checkable.
    """
    return MathParams(
        math_x_height=size // 2,
        math_quad=size,
        num1=size * 7 // 10,
        num2=size * 4 // 10,
        num3=size * 45 // 100,
        denom1=size * 7 // 10,
        denom2=size * 35 // 100,
        sup1=size * 4 // 10,
        sup2=size * 36 // 100,
        sup3=size * 29 // 100,
        sub1=size * 15 // 100,
        sub2=size * 25 // 100,
        sup_drop=size * 25 // 100,
        sub_drop=size * 20 // 100,
        delim1=size * 24 // 10,
        delim2=size,
        axis_height=size // 4,
        default_rule_thickness=size // 20,
        big_op_spacing1=size // 5,
        big_op_spacing2=size // 6,
        big_op_spacing3=size // 9,
        big_op_spacing4=size * 6 // 10,
        big_op_spacing5=size // 10,
        # TeX's own formulas (make_radical, tex.web:14480-14483) over the two
        # numbers above: 9, 9 + 9 // 4 = 11 and 9 + 90 // 4 = 31 at size 180.
        radical_rule_thickness=size // 20,
        radical_vertical_gap=size // 20 + (size // 20) // 4,
        radical_display_style_vertical_gap=size // 20 + (size // 2) // 4,
        script_scale=0.7,
        script_script_scale=0.5,
        display_operator_min_height=size * 13 // 10,
    )


@dataclass(frozen=True, slots=True)
class FakeMathMetrics:
    """
    A `MathFontMetrics` with no font behind it and no variant chain.

    No chain on purpose: the chain is the one thing a fake must not fabricate,
    because asserting against a fabricated one would prove nothing about the
    litmus test. The real-font tests below cover it.
    """

    size: float
    face: Face = Face.MATH

    @property
    def ascent(self) -> float:
        return self.size * 0.8

    @property
    def descent(self) -> float:
        return self.size * 0.2

    @property
    def x_height(self) -> float:
        return self.size / 2

    @property
    def em(self) -> float:
        return self.size

    @property
    def space_width(self) -> float:
        return self.size / 3

    @property
    def math(self) -> MathParams:
        return fake_params(int(self.size))

    def has(self, codepoint: int) -> bool:
        return True

    def advance(self, codepoint: int) -> float:
        return self.size / 2

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(0.0, 0.0, self.size * 0.45, self.size * 0.4)

    def kern(self, codepoint: int, following: int) -> float:
        return 0.0

    def italic_correction(self, codepoint: int) -> float:
        return 0.0

    def vertical_variants(self, codepoint: int) -> tuple[GlyphVariant, ...]:
        return ()


@pytest.fixture
def fake() -> MathFonts:
    return math_fonts(FAKE_SIZE, lambda size: FakeMathMetrics(float(size)))


@pytest.fixture
def real(bundled_fonts: Path) -> MathFonts:
    # 32 px so the script sizes stay well clear of rounding noise.
    return math_fonts(
        sp_from_px(32.0), lambda size: fontlib.math_metrics(float(size)), text=fontlib_metrics
    )


def glue_widths(nodes: list[Node]) -> list[int]:
    return [n.spec.width for n in nodes if isinstance(n, Glue)]


def codepoints(box: Box) -> list[int]:
    """
    Every glyph in a packed box, in reading order, however deeply nested.
    """
    found: list[int] = []
    for node in box.contents:
        if isinstance(node, CharNode):
            found.append(node.codepoint)
        elif isinstance(node, Box):
            found.extend(codepoints(node))
    return found


def only_box(nodes: list[Node]) -> Box:
    boxes = [n for n in nodes if isinstance(n, Box)]
    assert len(boxes) == 1
    return boxes[0]


# -- the spacing table ---------------------------------------------------


def test_the_spacing_table_is_the_sources_sixty_four_characters() -> None:
    # tex.web:15064. Transcribed rather than derived, so this is the guard that
    # it stayed transcribed.
    assert len(MATH_SPACING) == 64
    assert MATH_SPACING == (
        "02340001" "22*40001" "33**3**3" "44*04004" "00*00000" "02340001" "11*11111" "12341011"
    )


def test_a_binary_operator_between_two_ordinaries_gets_medium_space(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), bin_("+"), ord_("b")], Style.TEXT, fake)
    assert glue_widths(nodes) == [4 * MU, 4 * MU]


def test_a_relation_gets_thick_space_on_both_sides(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), rel("="), ord_("b")], Style.TEXT, fake)
    assert glue_widths(nodes) == [5 * MU, 5 * MU]


def test_two_ordinaries_get_no_space_at_all(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), ord_("b")], Style.TEXT, fake)
    assert glue_widths(nodes) == []


def test_an_operator_is_followed_by_a_thin_space_that_survives_script_style(
    fake: MathFonts,
) -> None:
    # Op-Ord is entry "2", the one unconditional space in the table: it is not
    # dropped in script styles the way medium and thick are. It does get
    # smaller, because section 703 computes cur_mu from the math quad of the
    # *current size* -- a math unit at script size is 126/18 = 7, not 10. That
    # is the space shrinking with the type rather than being suppressed.
    formula = [op("f", limits=Limits.NO_LIMITS), ord_("x")]
    script_mu = fake.sizes[MathSize.SCRIPT] // 18
    assert glue_widths(mlist_to_hlist(formula, Style.TEXT, fake)) == [3 * MU]
    assert glue_widths(mlist_to_hlist(formula, Style.SCRIPT, fake)) == [3 * script_mu]
    assert script_mu < MU


def test_conditional_spaces_vanish_in_script_style(fake: MathFonts) -> None:
    formula = [ord_("a"), bin_("+"), ord_("b"), rel("="), ord_("c")]
    assert glue_widths(mlist_to_hlist(formula, Style.TEXT, fake)) != []
    assert glue_widths(mlist_to_hlist(formula, Style.SCRIPT, fake)) == []


def test_medium_space_is_stretchable_and_shrinkable_the_way_plain_tex_sets_it(
    fake: MathFonts,
) -> None:
    nodes = mlist_to_hlist([ord_("a"), bin_("+"), ord_("b")], Style.TEXT, fake)
    spec = next(n for n in nodes if isinstance(n, Glue)).spec
    # \medmuskip is 4mu plus 2mu minus 4mu.
    assert (spec.width, spec.stretch, spec.shrink) == (4 * MU, 2 * MU, 4 * MU)


# -- the Bin-to-Ord conversion -------------------------------------------


def test_a_leading_binary_operator_is_demoted_because_it_binds_nothing(
    fake: MathFonts,
) -> None:
    # Section 726 starts the pass with r_type = op_noad precisely so this works:
    # the minus in "-x" is a sign, not a subtraction, and takes no space.
    nodes = mlist_to_hlist([bin_("-"), ord_("x")], Style.TEXT, fake)
    assert glue_widths(nodes) == []


def test_a_binary_operator_before_a_relation_is_demoted(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), bin_("+"), rel("=")], Style.TEXT, fake)
    # a..+ becomes Ord-Ord (nothing); +..= becomes Ord-Rel (thick).
    assert glue_widths(nodes) == [5 * MU]


def test_a_trailing_binary_operator_is_demoted(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), bin_("+")], Style.TEXT, fake)
    assert glue_widths(nodes) == []


def test_no_ordered_pair_of_atoms_can_reach_an_impossible_table_entry(
    fake: MathFonts,
) -> None:
    # The table has eleven "*" entries and section 727's conversion is the only
    # thing that keeps them unreachable. If the conversion is ever weakened this
    # raises, which is the point.
    builders = {
        AtomType.ORD: ord_,
        AtomType.OP: op,
        AtomType.BIN: bin_,
        AtomType.REL: rel,
        AtomType.OPEN: open_,
        AtomType.CLOSE: close_,
        AtomType.PUNCT: punct,
        AtomType.INNER: inner,
    }
    for left in builders.values():
        for right in builders.values():
            mlist_to_hlist([left("a"), right("b")], Style.TEXT, fake)


# -- the style algebra ---------------------------------------------------


def test_a_superscript_of_a_display_atom_is_set_in_script_style() -> None:
    assert sup_style(Style.DISPLAY) is Style.SCRIPT
    assert sub_style(Style.DISPLAY) is Style.SCRIPT_CRAMPED


def test_a_subscript_is_always_cramped_and_a_superscript_keeps_what_it_inherited() -> None:
    # Which is why x^{y^z} climbs and x_{y_z} does not keep dropping.
    assert sub_style(Style.TEXT) is Style.SCRIPT_CRAMPED
    assert sup_style(Style.TEXT) is Style.SCRIPT
    assert sup_style(Style.TEXT_CRAMPED) is Style.SCRIPT_CRAMPED


def test_a_script_of_a_script_is_scriptscript_and_stops_there() -> None:
    assert sup_style(Style.SCRIPT) is Style.SCRIPT_SCRIPT
    assert sup_style(Style.SCRIPT_SCRIPT) is Style.SCRIPT_SCRIPT
    assert sub_style(Style.SCRIPT_SCRIPT) is Style.SCRIPT_SCRIPT_CRAMPED
    assert num_style(Style.SCRIPT_SCRIPT) is Style.SCRIPT_SCRIPT


def test_a_fractions_denominator_is_cramped_and_its_numerator_is_not() -> None:
    assert num_style(Style.DISPLAY) is Style.TEXT
    assert denom_style(Style.DISPLAY) is Style.TEXT_CRAMPED


def test_cramping_does_not_change_the_size() -> None:
    for style in Style:
        assert size_for(cramped_style(style)) is size_for(style)


def test_display_and_text_share_a_size_and_the_scripts_do_not() -> None:
    assert size_for(Style.DISPLAY) is MathSize.TEXT
    assert size_for(Style.TEXT_CRAMPED) is MathSize.TEXT
    assert size_for(Style.SCRIPT) is MathSize.SCRIPT
    assert size_for(Style.SCRIPT_SCRIPT_CRAMPED) is MathSize.SCRIPT_SCRIPT


def test_the_script_sizes_come_from_the_fonts_own_percentages(fake: MathFonts) -> None:
    # Not plain.tex's 0.7/0.5 convention, which docs/tex-notes.md section 10
    # records as absent from tex.web: these are MathConstants fields.
    assert fake.sizes[MathSize.TEXT] == FAKE_SIZE
    assert fake.sizes[MathSize.SCRIPT] == round(FAKE_SIZE * 0.7)
    assert fake.sizes[MathSize.SCRIPT_SCRIPT] == round(FAKE_SIZE * 0.5)


def test_a_script_is_set_from_the_smaller_face(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("x", sup="2")], Style.TEXT, fake)
    box = hpack(nodes, measure=fake.measure).box
    fonts = {n.font for n in box.contents if isinstance(n, CharNode)}
    nested = only_box(list(box.contents))
    assert fonts == {fake.key(Style.TEXT)}
    assert {n.font for n in nested.contents if isinstance(n, CharNode)} == {fake.key(Style.SCRIPT)}


# -- scripts -------------------------------------------------------------


def test_a_lone_subscript_is_pushed_down_to_clear_four_fifths_of_the_x_height(
    fake: MathFonts,
) -> None:
    # Section 757. The clamp is 4/5, not 1/5; the research brief said 1/5 and was
    # wrong, and tex.web:14913 settles it.
    nodes = mlist_to_hlist([ord_("x", sub="i")], Style.TEXT, fake)
    script = only_box(nodes)
    params = fake.params(Style.TEXT)
    floor = max(round(params.sub1), script.height - (X_HEIGHT * 4) // 5)
    assert script.shift_amount == floor


def script_shifts(nodes: list[Node]) -> list[int]:
    """
    How far each shifted box at the top level of a list was raised (positive up).
    """
    return [-node.shift_amount for node in nodes if isinstance(node, Box) and node.shift_amount]


RAISED_GROUP = group(ord_("x", sup="2"))


@pytest.mark.parametrize(
    "nucleus",
    [
        # {x^2}^3: the reported case.
        RAISED_GROUP,
        # {(a+b)}^2 and \mathrm{ab}^2: a list that merely begins with a character.
        group(open_("("), "a", bin_("+"), "b", close_(")")),
        group("a", "b"),
    ],
)
def test_a_script_on_a_group_is_placed_from_the_groups_box_and_not_as_on_a_letter(
    fake: MathFonts, nucleus: SubList
) -> None:
    # tex.web:14889: `if is_char_node(p)` -- and p, for a nucleus that is a
    # list, is the hbox `sub_mlist` packed (14848-14851), never a character.
    # The test used to be "is the first node a character", which a group
    # beginning with a letter also is, so {x^2}^3 set as x-superscript-23.
    inner_nodes = mlist_to_hlist(nucleus.items, Style.TEXT, fake)
    enclosing = hpack(inner_nodes, measure=fake.measure).box
    from_the_box = enclosing.height - round(fake.params(Style.SCRIPT).sup_drop)
    on_a_letter = script_shifts(mlist_to_hlist([ord_("x", sup="3")], Style.TEXT, fake))[-1]

    nodes = mlist_to_hlist([ord_(nucleus, sup="3")], Style.TEXT, fake)
    # §758's clamps still apply; a flat group is as low as a letter, and only
    # one with something raised inside it is told apart (the first case).
    assert script_shifts(nodes)[-1] == max(from_the_box, on_a_letter)
    if nucleus is RAISED_GROUP:
        assert from_the_box > on_a_letter, "the fake must tell the two branches apart"


def test_a_subscript_on_a_group_drops_by_the_groups_depth(fake: MathFonts) -> None:
    # {a_i}_j: the outer j clears the inner i, which a bare a_j would not.
    nucleus = group(ord_("a", sub="i"))
    enclosing = hpack(mlist_to_hlist(nucleus.items, Style.TEXT, fake), measure=fake.measure).box
    expected = enclosing.depth + round(fake.params(Style.SCRIPT).sub_drop)
    bare = only_box(mlist_to_hlist([ord_("a", sub="j")], Style.TEXT, fake)).shift_amount
    assert expected > bare
    nodes = mlist_to_hlist([ord_(nucleus, sub="j")], Style.TEXT, fake)
    assert [n for n in nodes if isinstance(n, Box)][-1].shift_amount == expected


def test_a_single_character_nucleus_still_takes_the_bare_letter_branch(fake: MathFonts) -> None:
    # The other side of the same line of the source: nothing moved for x^2.
    params = fake.params(Style.TEXT)
    script = only_box(mlist_to_hlist([ord_("x", sup="2")], Style.TEXT, fake))
    assert -script.shift_amount == max(round(params.sup2), script.depth + X_HEIGHT // 4)


def test_a_lone_superscript_is_shifted_up_not_down(fake: MathFonts) -> None:
    # shift_amount is positive down, so a raised script is negative.
    script = only_box(mlist_to_hlist([ord_("x", sup="2")], Style.TEXT, fake))
    assert script.shift_amount < 0


def test_two_scripts_are_kept_four_rule_thicknesses_apart(fake: MathFonts) -> None:
    # Section 759: if they would be closer, the subscript drops and then both
    # rise together. The separating kern is the gap itself.
    nodes = mlist_to_hlist([ord_("x", sup="2", sub="i")], Style.TEXT, fake)
    stacked = only_box(nodes)
    assert stacked.kind is BoxKind.VLIST
    kerns = [n for n in stacked.contents if isinstance(n, Kern)]
    assert len(kerns) == 1
    assert kerns[0].width >= 4 * RULE_THICKNESS


def test_a_cramped_superscript_uses_the_lower_of_the_three_shifts(fake: MathFonts) -> None:
    params = fake.params(Style.TEXT)
    upright = only_box(mlist_to_hlist([ord_("x", sup="2")], Style.TEXT, fake))
    cramped = only_box(mlist_to_hlist([ord_("x", sup="2")], Style.TEXT_CRAMPED, fake))
    assert round(params.sup3) < round(params.sup2)
    assert -cramped.shift_amount <= -upright.shift_amount


# -- make_op, against the real font --------------------------------------


def test_display_style_selects_a_genuinely_different_summation_glyph(
    real: MathFonts, bundled_fonts: Path
) -> None:
    # The litmus test's central claim. Not the body glyph scaled up: a different
    # glyph, drawn larger, selected by following the font's own variant chain
    # exactly one step (section 749).
    display = hpack(mlist_to_hlist([op("∑")], Style.DISPLAY, real), measure=real.measure).box
    text = hpack(mlist_to_hlist([op("∑")], Style.TEXT, real), measure=real.measure).box
    display_glyphs = [fontlib.glyph_name(Face.MATH, c) for c in codepoints(display)]
    text_glyphs = [fontlib.glyph_name(Face.MATH, c) for c in codepoints(text)]
    assert display_glyphs == ["summation.v1"]
    assert text_glyphs == ["summation"]


def test_the_display_operator_is_taller_than_the_text_one_at_the_same_size(
    real: MathFonts, bundled_fonts: Path
) -> None:
    display = hpack(mlist_to_hlist([op("∑")], Style.DISPLAY, real), measure=real.measure).box
    text = hpack(mlist_to_hlist([op("∑")], Style.TEXT, real), measure=real.measure).box
    assert display.height + display.depth > text.height + text.depth
    # Both are set from the same face at the same size, so the difference is the
    # glyph and nothing else.
    assert real.key(Style.DISPLAY) == real.key(Style.TEXT)


def test_the_operator_is_centred_on_the_math_axis_and_not_on_the_baseline(
    real: MathFonts, bundled_fonts: Path
) -> None:
    # Section 749: shift_amount = half(height - depth) - axis_height, which puts
    # the glyph's vertical middle on the axis where the minus sign sits.
    nodes = mlist_to_hlist([op("∑", limits=Limits.NO_LIMITS)], Style.TEXT, real)
    box = hpack(nodes, measure=real.measure).box
    axis = round(real.params(Style.TEXT).axis_height)
    middle = (box.depth - box.height) // 2
    assert abs(middle + axis) <= 1


def test_limits_are_stacked_in_display_style_and_set_to_the_right_inline(
    real: MathFonts, bundled_fonts: Path
) -> None:
    formula = [op("∑", sup="n", sub=group("i", rel("="), "1"))]
    display = mlist_to_hlist(formula, Style.DISPLAY, real)
    text = mlist_to_hlist(formula, Style.TEXT, real)
    # Stacked: one vlist holding the upper limit, the operator and the lower one.
    stacked = only_box(display)
    assert stacked.kind is BoxKind.VLIST
    # Inline: the nucleus, then a separate box of scripts beside it.
    assert len([n for n in text if isinstance(n, Box)]) == 2


def test_the_upper_limit_is_above_the_operator_and_the_lower_below(
    real: MathFonts, bundled_fonts: Path
) -> None:
    stacked = only_box(mlist_to_hlist([op("∑", sup="n", sub="i")], Style.DISPLAY, real))
    boxes = [n for n in stacked.contents if isinstance(n, Box)]
    assert len(boxes) == 3
    upper, middle, lower = boxes
    assert codepoints(upper) == [ord("n")]
    assert [fontlib.glyph_name(Face.MATH, c) for c in codepoints(middle)] == ["summation.v1"]
    assert codepoints(lower) == [ord("i")]


def test_nolimits_keeps_the_bounds_beside_the_operator_even_in_display_style(
    real: MathFonts, bundled_fonts: Path
) -> None:
    formula = [op("∑", sup="n", sub="i", limits=Limits.NO_LIMITS)]
    nodes = mlist_to_hlist(formula, Style.DISPLAY, real)
    assert len([n for n in nodes if isinstance(n, Box)]) == 2


def test_the_stacked_limits_are_all_as_wide_as_the_widest_of_them(
    real: MathFonts, bundled_fonts: Path
) -> None:
    # Section 750 reboxes all three to the common width, which is what centres
    # the bounds under and over the operator rather than left-aligning them.
    stacked = only_box(
        mlist_to_hlist(
            [
                op("∑", sup="n", sub="i"),
            ],
            Style.DISPLAY,
            real,
        )
    )
    boxes = [n for n in stacked.contents if isinstance(n, Box)]
    assert {b.width for b in boxes} == {stacked.width}


# -- fractions -----------------------------------------------------------


def rule_top_above_baseline(vlist: Box) -> int:
    """
    How far the fraction bar's top sits above the vlist's baseline.

    Walks down from the top of the box: the numerator, then the kern, then the
    rule. Written out rather than asserted against a formula so that a change in
    how the vlist is assembled is caught rather than cancelled out.
    """
    above = vlist.height
    for node in vlist.contents:
        if isinstance(node, Rule):
            return above
        if isinstance(node, Box):
            above -= node.height + node.depth
        elif isinstance(node, Kern):
            above -= node.width
    raise AssertionError("no rule in this fraction")


def test_the_fraction_bar_is_centred_on_the_math_axis(fake: MathFonts) -> None:
    vlist = only_box(mlist_to_hlist([frac("x", "y")], Style.TEXT, fake))
    assert vlist.kind is BoxKind.VLIST
    half = (RULE_THICKNESS + 1) // 2
    assert rule_top_above_baseline(vlist) == AXIS + half


def test_the_fraction_rule_thickness_comes_from_the_font(fake: MathFonts) -> None:
    vlist = only_box(mlist_to_hlist([frac("x", "y")], Style.TEXT, fake))
    rule = next(n for n in vlist.contents if isinstance(n, Rule))
    assert rule.height == RULE_THICKNESS
    assert rule.depth == 0


def test_an_atop_fraction_has_no_rule_at_all(fake: MathFonts) -> None:
    vlist = only_box(mlist_to_hlist([frac("x", "y", thickness=0)], Style.TEXT, fake))
    assert not [n for n in vlist.contents if isinstance(n, Rule)]
    assert len([n for n in vlist.contents if isinstance(n, Box)]) == 2


def test_a_display_fraction_sets_its_numerator_higher_than_a_text_one(
    fake: MathFonts,
) -> None:
    # Section 744: display takes num1/denom1, non-display num2/denom2, and num1
    # is the larger shift.
    display = only_box(mlist_to_hlist([frac("x", "y")], Style.DISPLAY, fake))
    text = only_box(mlist_to_hlist([frac("x", "y")], Style.TEXT, fake))
    assert display.height > text.height
    assert display.depth > text.depth


def test_a_fraction_spaces_as_an_inner_atom(fake: MathFonts) -> None:
    # Section 761 maps fraction_noad onto inner_noad for spacing, so an
    # ordinary atom beside one gets the conditional thin space, not nothing.
    nodes = mlist_to_hlist([ord_("a"), frac("x", "y")], Style.TEXT, fake)
    assert glue_widths(nodes) == [3 * MU]


def test_numerator_and_denominator_are_reboxed_to_a_common_width(
    fake: MathFonts,
) -> None:
    vlist = only_box(mlist_to_hlist([frac("xyz", "y")], Style.TEXT, fake))
    boxes = [n for n in vlist.contents if isinstance(n, Box)]
    assert len({b.width for b in boxes}) == 1


# -- what is not implemented, and says so --------------------------------


def test_an_accent_reports_what_is_missing_rather_than_rendering_something_wrong(
    fake: MathFonts,
) -> None:
    # This test named a radical until the second build gave the engine one. An
    # accent is what is left: it needs a width-fitting chain, which nothing reads.
    accent = Atom(AtomType.ACCENT, MathChar(ord("x")))
    with pytest.raises(NotImplementedError, match="width-fitting chain"):
        mlist_to_hlist([accent], Style.TEXT, fake)


def test_not_implemented_is_not_the_refusal_a_caller_with_a_fallback_catches(
    fake: MathFonts,
) -> None:
    # `MathLayoutError` means "well formed, and beyond these fonts"; an accent is
    # "this module has no code for that", and the two must not be one except clause.
    assert not issubclass(NotImplementedError, MathLayoutError)
    assert issubclass(DelimiterTooSmallError, MathLayoutError)
    assert issubclass(TextFaceUnavailableError, MathLayoutError)


# -- the builder ---------------------------------------------------------


def test_the_builder_produces_the_atoms_it_reads_as() -> None:
    formula = op("∑", sup="n", sub=group("i", rel("="), "1"))
    assert formula.kind is AtomType.OP
    assert formula.nucleus == MathChar(0x2211)
    assert formula.limits is Limits.DEFAULT
    sub = formula.sub
    assert isinstance(sub, SubList)
    assert [item.kind for item in sub.items] == [AtomType.ORD, AtomType.REL, AtomType.ORD]


def test_a_multi_character_nucleus_becomes_a_sublist_of_ordinaries() -> None:
    atom = ord_("sin")
    assert isinstance(atom.nucleus, SubList)
    assert len(atom.nucleus.items) == 3


def test_replacing_a_style_does_not_disturb_the_atoms(fake: MathFonts) -> None:
    # Frozen dataclasses throughout, so the same formula can be converted twice
    # at different styles and give two independent results.
    formula = [op("∑", sup="n", sub="i")]
    first = mlist_to_hlist(formula, Style.DISPLAY, fake)
    second = mlist_to_hlist(formula, Style.DISPLAY, fake)
    assert replace(only_box(first), contents=()) == replace(only_box(second), contents=())


# ========================================================================
# The second build: sized delimiters, radicals, explicit spaces, prose
# ========================================================================

# Large enough that `delta1 div 500` (tex.web:15025) is not simply zero, and a
# multiple of 18 so one math unit is exactly 1000.
BIG = 18_000
BIG_AXIS = BIG // 4  # 4500
BIG_RULE = BIG // 20  # 900
BIG_GAP = BIG_RULE + BIG_RULE // 4  # 1125, text style
BIG_DISPLAY_GAP = BIG_RULE + (BIG // 2) // 4  # 3150
# \delimitershortfall for the fabricated chain. The real one is 5pt, absolute
# (327,680 sp), which is eighteen of this fake's quads and would never decide;
# the `tall` fixture sets this in its place so the boundary is a round number.
BIG_SHORTFALL = BIG // 2

# (height, depth) of each link of every fabricated chain, in ems. Each is
# centred on the axis at a quarter em, as a font's delimiters are. The last is
# 5.05 em, not 5 or 6, so that exactly one content height separates "the factor
# rule would accept this" from "the shortfall rule does not"; see the refusal test.
CHAIN_SHAPES = ((0.75, 0.25), (1.25, 0.75), (1.75, 1.25), (2.775, 2.275))
EXTENTS = (18_000, 36_000, 54_000, 90_900)

CHAINS: dict[int, tuple[int, ...]] = {
    ord("("): (ord("("), 0xE001, 0xE002, 0xE003),
    ord(")"): (ord(")"), 0xE011, 0xE012, 0xE013),
    SURD: (SURD, 0xE021, 0xE022, 0xE023),
}
SHAPE_OF: dict[int, tuple[float, float]] = {
    codepoint: shape
    for chain in CHAINS.values()
    for codepoint, shape in zip(chain, CHAIN_SHAPES, strict=True)
}
# One delimiter with no chain at all and nothing below the baseline, so that
# "centred on the axis" is a shift that is not zero.
SHAPE_OF[ord("[")] = (1.0, 0.0)


@dataclass(frozen=True, slots=True)
class ChainedFake(FakeMathMetrics):
    """
    `FakeMathMetrics` with a variant chain for two parentheses and the surd.
    """

    def bbox(self, codepoint: int) -> GlyphBBox:
        shape = SHAPE_OF.get(codepoint)
        if shape is None:
            return FakeMathMetrics.bbox(self, codepoint)
        return GlyphBBox(0.0, -shape[1] * self.size, self.size * 0.45, shape[0] * self.size)

    def vertical_variants(self, codepoint: int) -> tuple[GlyphVariant, ...]:
        return tuple(
            GlyphVariant(f"v{index}", link, sum(CHAIN_SHAPES[index]) * self.size)
            for index, link in enumerate(CHAINS.get(codepoint, ()))
        )


@pytest.fixture
def tall(monkeypatch: pytest.MonkeyPatch) -> MathFonts:
    monkeypatch.setattr(mlist_module, "DELIMITER_SHORTFALL", BIG_SHORTFALL)
    return math_fonts(BIG, lambda size: ChainedFake(float(size)))


def a_box(height: int, depth: int = 0) -> Atom:
    """
    An ordinary atom that is exactly this tall, so a boundary can be stated.
    """
    return ord_(SubBox(Box(kind=BoxKind.HLIST, width=1000, height=height, depth=depth)))


def delimiter_boxes(nodes: list[Node]) -> list[Box]:
    """
    The boxes in a list that hold one chained character and nothing else.
    """
    found = []
    for node in nodes:
        if (
            isinstance(node, Box)
            and len(node.contents) == 1
            and isinstance(node.contents[0], CharNode)
            and node.contents[0].codepoint in SHAPE_OF
        ):
            found.append(node)
    return found


def link_of(box: Box) -> int:
    """
    Which link of its chain a delimiter box holds, 0 for the base character.
    """
    char = box.contents[0]
    assert isinstance(char, CharNode)
    for chain in CHAINS.values():
        if char.codepoint in chain:
            return chain.index(char.codepoint)
    raise AssertionError(f"U+{char.codepoint:04X} is in no chain")


# -- make_left_right -----------------------------------------------------


def test_the_fabricated_chain_is_what_the_arithmetic_below_assumes(tall: MathFonts) -> None:
    # The fixture check for everything in this half of the file.
    key = tall.keys[MathSize.TEXT]
    for chain in CHAINS.values():
        extents = []
        for link in chain:
            dimens = tall.measure(CharNode(key, link))
            extents.append(dimens.height + dimens.depth)
        assert tuple(extents) == EXTENTS
    assert tall.mu(Style.TEXT) == 1000
    assert round(tall.params(Style.TEXT).axis_height) == BIG_AXIS
    assert DELIMITER_FACTOR == 901


@pytest.mark.parametrize(
    ("height", "depth", "link"),
    [
        # delta1 = 9999 from the axis: (9999 div 500) * 901 = 17119, and the base
        # character is 18000. The division comes first, as in the source; taken
        # the other way round this is 18018 and the base character is not enough.
        (BIG_AXIS + 9_999, 0, 0),
        # delta1 = 10000: 20 * 901 = 18020, twenty more than the base has.
        (BIG_AXIS + 10_000, 0, 1),
        # The same reach, downward: delta2 = depth + axis is the larger.
        (0, 10_000 - BIG_AXIS, 1),
        (BIG_AXIS + 19_500, 0, 1),
        (BIG_AXIS + 20_000, 0, 2),
        # delta1 = 49950: the factor asks for 89199 and the shortfall rule for
        # 2 * 49950 - 9000 = 90900, which is the last link exactly.
        (BIG_AXIS + 49_950, 0, 3),
    ],
)
def test_a_pair_takes_the_smallest_variant_the_factor_and_shortfall_rules_allow(
    tall: MathFonts, height: int, depth: int, link: int
) -> None:
    nodes = mlist_to_hlist([delimited("(", a_box(height, depth), ")")], Style.TEXT, tall)
    left, right = delimiter_boxes(nodes)
    assert (link_of(left), link_of(right)) == (link, link)


def test_the_shortfall_is_five_points_and_not_a_share_of_the_quad() -> None:
    # tex.web:15026 subtracts a dimension, and plain.tex sets it to 5pt. It was
    # half a quad here, which review 2 (item 9) showed never decides anything.
    assert DELIMITER_SHORTFALL == sp_from_pt(5.0)
    assert LARGEST_VARIANT_MUST_COVER == (3, 4)


def test_the_shortfall_rule_decides_which_real_parenthesis_a_tall_box_takes(
    real: MathFonts,
) -> None:
    # The claim review 2 found false of the em-relative rule: somewhere within
    # reach of the real chain, the shortfall asks for more than the factor does
    # and a larger parenthesis is taken because of it.
    params = real.params(Style.TEXT)
    axis = round(params.axis_height)
    key = real.key(Style.TEXT)
    chain = [v.codepoint for v in real.face(Style.TEXT).vertical_variants(ord("("))]
    decided = 0
    for reach in range(real.sizes[MathSize.TEXT] // 2, real.sizes[MathSize.TEXT] * 3 // 2, 4096):
        by_factor = (reach // 500) * DELIMITER_FACTOR
        by_shortfall = 2 * reach - DELIMITER_SHORTFALL
        if by_shortfall <= by_factor:
            continue
        nodes = mlist_to_hlist([delimited("(", a_box(axis + reach), ")")], Style.TEXT, real)
        taken = codepoints(hpack(nodes, measure=real.measure).box)[0]
        dimens = real.measure(CharNode(key, taken))
        extent = dimens.height + dimens.depth
        if taken != chain[-1]:
            assert extent >= by_shortfall
        smaller = chain[chain.index(taken) - 1]
        below = real.measure(CharNode(key, smaller))
        decided += by_factor <= below.height + below.depth < by_shortfall
    assert decided > 0


def test_content_past_the_last_variant_takes_the_largest_while_it_covers_three_quarters(
    tall: MathFonts,
) -> None:
    # delta1 = 50000. The shortfall rule wants 91000 and the last link is 90900:
    # no variant satisfies TeX's rule. TeX returns the largest (tex.web:13895),
    # and so does this while the largest covers three quarters of 2 * delta1.
    # It used to be refused, which is what refused ordinary fractions in
    # \left( \right) for being a few percent too tall (review 2, item 9).
    for reach in (50_000, 60_600):
        nodes = mlist_to_hlist([delimited("(", a_box(BIG_AXIS + reach), ")")], Style.TEXT, tall)
        left, right = delimiter_boxes(nodes)
        assert (link_of(left), link_of(right)) == (3, 3)
    # 60600 is the boundary exactly: three quarters of 121200 is 90900.
    assert 4 * EXTENTS[-1] == 3 * 2 * 60_600


def test_content_the_largest_variant_covers_under_three_quarters_of_is_refused(
    tall: MathFonts,
) -> None:
    # One scaled point of reach past the boundary above.
    formula = [delimited("(", a_box(BIG_AXIS + 60_601), ")")]
    with pytest.raises(DelimiterTooSmallError) as refused:
        mlist_to_hlist(formula, Style.TEXT, tall)
    assert refused.value.codepoint == ord("(")
    assert refused.value.needed == 2 * 60_601 - BIG_SHORTFALL
    assert refused.value.largest == EXTENTS[-1]


def test_the_largest_variant_is_never_taken_when_a_smaller_one_satisfies_the_rule(
    tall: MathFonts,
) -> None:
    # The allowance is a fallback and not a preference: the table above still
    # holds row for row with it in place (the fixture is the same).
    nodes = mlist_to_hlist([delimited("(", a_box(BIG_AXIS + 10_000), ")")], Style.TEXT, tall)
    assert [link_of(box) for box in delimiter_boxes(nodes)] == [1, 1]


def test_a_delimiter_is_centred_on_the_axis_whatever_its_own_baseline(tall: MathFonts) -> None:
    # "[" in this fake stands wholly above its baseline and has no chain, so the
    # shift that centres it is real: half of 18000, less the axis.
    nodes = mlist_to_hlist([delimited("[", "x", None)], Style.TEXT, tall)
    (bracket,) = delimiter_boxes(nodes)
    above_axis = (bracket.height - bracket.shift_amount) - BIG_AXIS
    below_axis = (bracket.depth + bracket.shift_amount) + BIG_AXIS
    assert bracket.shift_amount == BIG // 2 - BIG_AXIS
    assert above_axis == below_axis == BIG // 2


def test_a_null_delimiter_is_an_empty_box_of_the_null_delimiter_space(tall: MathFonts) -> None:
    nodes = mlist_to_hlist([delimited(None, "x", ")")], Style.TEXT, tall)
    null = nodes[0]
    assert isinstance(null, Box) and null.contents == ()
    # plain.tex's 1.2pt at ten point: 0.12 of the quad.
    assert null.width == BIG * 12 // 100
    assert (null.height, null.depth) == (0, 0)
    assert len(delimiter_boxes(nodes)) == 1


def test_a_left_right_group_is_one_inner_atom_holding_its_boundaries() -> None:
    atom = delimited("(", group("x", bin_("+"), "y"), ")")
    assert atom.kind is AtomType.INNER
    assert isinstance(atom.nucleus, SubList)
    kinds = [item.kind for item in atom.nucleus.items if isinstance(item, Atom)]
    assert kinds == [AtomType.LEFT, AtomType.ORD, AtomType.BIN, AtomType.ORD, AtomType.RIGHT]
    assert AtomType.LEFT.spacing_class == AtomType.OPEN.spacing_class
    assert AtomType.RIGHT.spacing_class == AtomType.CLOSE.spacing_class


def test_the_group_spaces_as_inner_outside_and_as_open_and_close_inside(tall: MathFonts) -> None:
    # Outside: Ord-Inner and Inner-Ord are both a conditional thin space. Inside:
    # a Bin after the left boundary and a Bin before the right one are both
    # demoted (tex.web:14335, 14339), so nothing at all is asked for in there.
    inside = group(bin_("-"), ord_("x"), bin_("+"))
    nodes = mlist_to_hlist([ord_("a"), delimited("(", inside, ")"), ord_("b")], Style.TEXT, tall)
    assert glue_widths(nodes) == [3_000, 3_000]
    # And it is not that the table is off in there: a Bin with something to bind
    # keeps its medium spaces between the same two boundaries.
    bound = mlist_to_hlist(
        [delimited("(", group(ord_("x"), bin_("+"), ord_("y")), ")")], Style.TEXT, tall
    )
    assert glue_widths(bound) == [4_000, 4_000]


def test_the_groups_conditional_space_vanishes_in_script_style(tall: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), delimited("(", "x", ")")], Style.SCRIPT, tall)
    assert glue_widths(nodes) == []


def test_a_script_on_a_group_hangs_from_the_delimiters_not_from_what_is_inside(
    tall: MathFonts,
) -> None:
    bare = only_box(mlist_to_hlist([ord_("x", sup="2")], Style.TEXT, tall))
    nodes = mlist_to_hlist([delimited("(", "x", ")", sup="2")], Style.TEXT, tall)
    script = nodes[-1]
    assert isinstance(script, Box) and script not in delimiter_boxes(nodes)
    # Section 756: the shift starts from the height of the whole nucleus, and the
    # nucleus now includes a parenthesis three quarters of an em tall.
    assert -script.shift_amount > -bare.shift_amount


def test_a_boundary_outside_any_group_is_sized_to_the_list_it_stands_in(tall: MathFonts) -> None:
    # Nothing requires the Inner wrapper; `\left` alone in a list measures that list.
    lone = [Atom(AtomType.LEFT, MathChar(ord("("))), a_box(BIG_AXIS + 10_000)]
    (left,) = delimiter_boxes(mlist_to_hlist(lone, Style.TEXT, tall))
    assert link_of(left) == 1


def test_the_real_parentheses_around_a_display_fraction_are_the_smallest_that_cover(
    real: MathFonts,
) -> None:
    fraction = frac(group("a", bin_("+"), "b"), "c")
    content = hpack(mlist_to_hlist([fraction], Style.DISPLAY, real), measure=real.measure).box
    params = real.params(Style.DISPLAY)
    axis = round(params.axis_height)
    reach = max(content.height - axis, content.depth + axis)
    needed = max((reach // 500) * 901, 2 * reach - DELIMITER_SHORTFALL)

    nodes = mlist_to_hlist([delimited("(", fraction, ")")], Style.DISPLAY, real)
    packed = hpack(nodes, measure=real.measure).box
    chars = codepoints(packed)
    face = real.face(Style.DISPLAY)
    key = real.key(Style.DISPLAY)
    for delimiter, set_as in ((ord("("), chars[0]), (ord(")"), chars[-1])):
        chain = [variant.codepoint for variant in face.vertical_variants(delimiter)]
        extents = []
        for link in chain:
            dimens = real.measure(CharNode(key, link))
            extents.append(dimens.height + dimens.depth)
        index = chain.index(set_as)
        assert index > 0, "a display fraction should not fit the body parenthesis"
        assert extents[index] >= needed > extents[index - 1]


def test_the_real_parentheses_around_one_letter_are_the_body_ones(real: MathFonts) -> None:
    nodes = mlist_to_hlist([delimited("(", "x", ")")], Style.TEXT, real)
    assert codepoints(hpack(nodes, measure=real.measure).box) == [ord("("), ord("x"), ord(")")]


def test_the_real_font_refuses_content_taller_than_its_largest_parenthesis(
    real: MathFonts,
) -> None:
    em = real.sizes[MathSize.TEXT]
    with pytest.raises(DelimiterTooSmallError) as refused:
        mlist_to_hlist([delimited("(", a_box(4 * em), ")")], Style.DISPLAY, real)
    # 2.99 em is the last of Latin Modern Math's eight; nothing is assembled.
    assert 2.9 * em < refused.value.largest < 3.0 * em
    assert refused.value.needed > refused.value.largest


# -- make_radical --------------------------------------------------------


def radical_parts(nodes: list[Node]) -> tuple[Box, Box, Box]:
    """
    A translated radical as (the whole box, the surd's box, the vlist under the rule).
    """
    whole = only_box(nodes)
    surd, bar = whole.contents
    assert isinstance(surd, Box) and isinstance(bar, Box)
    assert bar.kind is BoxKind.VLIST
    return whole, surd, bar


def clearance_of(bar: Box) -> int:
    """
    The kern between the rule and the radicand: `clr`, as it was finally set.
    """
    above, rule, gap, radicand = bar.contents
    assert isinstance(above, Kern) and isinstance(rule, Rule) and isinstance(gap, Kern)
    assert isinstance(radicand, Box)
    # tex.web:13883's `overbar`: a kern of the rule's thickness above the rule.
    assert above.width == rule.height
    return gap.width


@pytest.mark.parametrize(
    ("style", "gap"),
    [(Style.TEXT, BIG_GAP), (Style.DISPLAY, BIG_DISPLAY_GAP)],
)
def test_the_clearance_under_the_rule_is_larger_in_display_style(
    tall: MathFonts, style: Style, gap: int
) -> None:
    # A radicand that leaves the base surd nothing to spare, so the clearance is
    # the minimum and not the minimum plus half an excess.
    radicand = a_box(EXTENTS[0] - BIG_RULE - gap)
    _, surd, bar = radical_parts(mlist_to_hlist([radical(radicand)], style, tall))
    assert link_of(surd) == 0
    assert clearance_of(bar) == gap
    assert BIG_DISPLAY_GAP > BIG_GAP


def test_a_surd_with_height_to_spare_gives_half_of_it_to_the_clearance(tall: MathFonts) -> None:
    # tex.web:14486. The radicand is 7200 tall; the base surd covers 18000 less
    # the 900 of the rule, so 17100 - (7200 + 1125) = 8775 is spare, and half of
    # an odd number rounds up.
    _, surd, bar = radical_parts(mlist_to_hlist([radical("x")], Style.TEXT, tall))
    assert link_of(surd) == 0
    assert clearance_of(bar) == BIG_GAP + 4_388


@pytest.mark.parametrize("style", [Style.TEXT, Style.DISPLAY])
@pytest.mark.parametrize("height", [0, 7_200, 20_000, 40_000, 80_000])
def test_the_top_of_the_surds_ink_is_the_top_of_the_rule(
    tall: MathFonts, style: Style, height: int
) -> None:
    whole, surd, bar = radical_parts(mlist_to_hlist([radical(a_box(height))], style, tall))
    rule_top = bar.height - BIG_RULE
    assert surd.height - surd.shift_amount == rule_top
    assert rule_top == height + clearance_of(bar) + BIG_RULE
    # The surd reaches at least to the bottom of the radicand.
    assert surd.depth + surd.shift_amount >= 0
    assert whole.height == bar.height
    assert bar.shift_amount == 0


@pytest.mark.parametrize(
    ("height", "link"),
    [
        (EXTENTS[0] - BIG_RULE - BIG_GAP, 0),
        (EXTENTS[0] - BIG_RULE - BIG_GAP + 1, 1),
        (EXTENTS[1] - BIG_RULE - BIG_GAP, 1),
        (EXTENTS[1] - BIG_RULE - BIG_GAP + 1, 2),
        (EXTENTS[3] - BIG_RULE - BIG_GAP, 3),
    ],
)
def test_the_surd_is_the_first_variant_covering_radicand_clearance_and_rule(
    tall: MathFonts, height: int, link: int
) -> None:
    _, surd, _ = radical_parts(mlist_to_hlist([radical(a_box(height))], Style.TEXT, tall))
    assert link_of(surd) == link


def test_a_radicand_one_scaled_point_too_tall_for_the_last_surd_is_refused(
    tall: MathFonts,
) -> None:
    height = EXTENTS[3] - BIG_RULE - BIG_GAP + 1
    with pytest.raises(DelimiterTooSmallError) as refused:
        mlist_to_hlist([radical(a_box(height))], Style.TEXT, tall)
    assert refused.value.codepoint == SURD
    assert refused.value.needed == EXTENTS[3] + 1
    assert refused.value.largest == EXTENTS[3]


def test_the_radicand_is_set_cramped(tall: MathFonts) -> None:
    # make_radical's first line (tex.web:14479). The observable is a superscript:
    # sup3 against sup2, 29% of the em against 36%.
    def script_shift(box: Box) -> int:
        scripts = [n for n in box.contents if isinstance(n, Box)]
        assert len(scripts) == 1
        return scripts[0].shift_amount

    squared = ord_("x", sup="2")
    _, _, bar = radical_parts(mlist_to_hlist([radical(squared)], Style.TEXT, tall))
    radicand = bar.contents[-1]
    assert isinstance(radicand, Box)
    cramped = hpack(mlist_to_hlist([squared], Style.TEXT_CRAMPED, tall), measure=tall.measure).box
    open_air = hpack(mlist_to_hlist([squared], Style.TEXT, tall), measure=tall.measure).box
    assert script_shift(radicand) == script_shift(cramped)
    assert script_shift(cramped) != script_shift(open_air)
    assert -script_shift(radicand) < -script_shift(open_air)


def test_a_radical_spaces_as_an_ordinary_atom_and_takes_scripts_as_one_box(
    tall: MathFonts,
) -> None:
    assert glue_widths(mlist_to_hlist([ord_("a"), radical("x"), ord_("b")], Style.TEXT, tall)) == []
    spaced = mlist_to_hlist([ord_("a"), bin_("+"), radical("x")], Style.TEXT, tall)
    assert glue_widths(spaced) == [4_000, 4_000]
    whole, script = mlist_to_hlist([radical("x", sup="2")], Style.TEXT, tall)
    assert isinstance(whole, Box) and isinstance(script, Box)
    assert script.shift_amount < 0


def test_a_delimiter_in_a_script_borrows_a_larger_font_only_when_it_must(
    tall: MathFonts,
) -> None:
    # var_delimiter's outer loop (tex.web:13948): the font of the current size
    # first, then the larger ones. The script face is 0.7 of 18000.
    script_size = tall.sizes[MathSize.SCRIPT]
    assert script_size == 12_600
    largest_in_script = round(CHAIN_SHAPES[-1][0] * script_size) + round(
        CHAIN_SHAPES[-1][1] * script_size
    )
    assert largest_in_script == 63_630

    _, small, _ = radical_parts(mlist_to_hlist([radical(a_box(1_000))], Style.SCRIPT, tall))
    char = small.contents[0]
    assert isinstance(char, CharNode) and char.font == tall.keys[MathSize.SCRIPT]

    _, large, _ = radical_parts(mlist_to_hlist([radical(a_box(68_000))], Style.SCRIPT, tall))
    char = large.contents[0]
    assert isinstance(char, CharNode)
    assert char.font == tall.keys[MathSize.TEXT]
    assert link_of(large) == 3


def test_a_borrowed_surds_rule_is_as_thick_as_the_font_it_was_borrowed_from(
    tall: MathFonts,
) -> None:
    # tex.web:14489: `overbar(x,clr,height(y))` -- the thickness is the surd's
    # own. A radical in a script that outgrows the script chain takes a
    # text-size surd, whose stroke is the text font's 900 and not the script
    # font's 630; the rule used to stay at 630 and step at the join (review 2,
    # item 9, the reviewer's suspicion: confirmed by this test failing first).
    script_rule = round(tall.params(Style.SCRIPT).radical_rule_thickness)
    text_rule = round(tall.params(Style.TEXT).radical_rule_thickness)
    assert (script_rule, text_rule) == (630, 900)

    def rule_of(bar: Box) -> int:
        (rule,) = [node for node in bar.contents if isinstance(node, Rule)]
        return rule.height + rule.depth

    _, small, bar = radical_parts(mlist_to_hlist([radical(a_box(1_000))], Style.SCRIPT, tall))
    assert rule_of(bar) == script_rule
    _, large, bar = radical_parts(mlist_to_hlist([radical(a_box(68_000))], Style.SCRIPT, tall))
    assert rule_of(bar) == text_rule
    # And the surd still hangs so that its ink top is the top of the rule.
    assert large.height - large.shift_amount == bar.height - text_rule


@pytest.mark.parametrize("link", [0, 1, 2, 3, 4])
def test_every_real_surd_meets_its_rule_and_covers_its_radicand(real: MathFonts, link: int) -> None:
    # The claim that needs the font: Latin Modern Math's base surd keeps TeX's
    # height-is-the-rule convention and its four larger ones do not, and one piece
    # of arithmetic has to hang all five correctly.
    face = real.face(Style.TEXT)
    key = real.key(Style.TEXT)
    params = real.params(Style.TEXT)
    chain = face.vertical_variants(SURD)
    assert len(chain) == 5
    dimens = real.measure(CharNode(key, chain[link].codepoint))
    thickness = round(params.radical_rule_thickness)
    gap = round(params.radical_vertical_gap)
    # The tallest radicand this link still covers.
    height = dimens.height + dimens.depth - thickness - gap

    whole, surd, bar = radical_parts(mlist_to_hlist([radical(a_box(height))], Style.TEXT, real))
    char = surd.contents[0]
    assert isinstance(char, CharNode) and char.codepoint == chain[link].codepoint
    assert clearance_of(bar) == gap
    assert surd.height - surd.shift_amount == bar.height - thickness
    assert surd.depth + surd.shift_amount == 0
    assert codepoints(whole) == [chain[link].codepoint]


def test_the_real_font_refuses_a_radicand_taller_than_its_largest_surd(real: MathFonts) -> None:
    em = real.sizes[MathSize.TEXT]
    with pytest.raises(DelimiterTooSmallError) as refused:
        mlist_to_hlist([radical(a_box(3 * em))], Style.TEXT, real)
    assert refused.value.codepoint == SURD
    assert 2.99 * em < refused.value.largest <= 3.0 * em


# -- explicit spaces -----------------------------------------------------


def test_the_named_spaces_are_plain_texs_in_math_units(fake: MathFonts) -> None:
    def spec(atom: Atom) -> tuple[int, int, int]:
        (glue,) = mlist_to_hlist([atom], Style.TEXT, fake)
        assert isinstance(glue, Glue)
        return glue.spec.width, glue.spec.stretch, glue.spec.shrink

    assert spec(THIN_SPACE) == (3 * MU, 0, 0)
    assert spec(MED_SPACE) == (4 * MU, 2 * MU, 4 * MU)
    assert spec(THICK_SPACE) == (5 * MU, 5 * MU, 0)
    assert spec(NEGATIVE_THIN_SPACE) == (-3 * MU, 0, 0)
    assert spec(QUAD) == (18 * MU, 0, 0)
    assert spec(QQUAD) == (36 * MU, 0, 0)
    assert spec(space(7, stretch=1, shrink=2)) == (7 * MU, MU, 2 * MU)


def test_a_space_adds_itself_and_leaves_the_table_alone(fake: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("a"), THIN_SPACE, ord_("b")], Style.TEXT, fake)
    assert glue_widths(nodes) == [3 * MU]
    # In reading order: the explicit space, then what the table puts before "+".
    nodes = mlist_to_hlist([ord_("a"), THIN_SPACE, bin_("+"), ord_("b")], Style.TEXT, fake)
    assert glue_widths(nodes) == [3 * MU, 4 * MU, 4 * MU]


def test_a_space_is_not_something_for_a_binary_operator_to_bind(fake: MathFonts) -> None:
    # A node, not a noad: it never becomes `r` (tex.web:14287), so the three
    # demotions of section 727 all see straight through it.
    leading = mlist_to_hlist([THIN_SPACE, bin_("+"), ord_("b")], Style.TEXT, fake)
    assert glue_widths(leading) == [3 * MU]
    trailing = mlist_to_hlist([ord_("a"), bin_("+"), QUAD], Style.TEXT, fake)
    assert glue_widths(trailing) == [18 * MU]
    before_a_relation = mlist_to_hlist(
        [ord_("a"), bin_("+"), THIN_SPACE, rel("="), ord_("b")], Style.TEXT, fake
    )
    assert glue_widths(before_a_relation) == [3 * MU, 5 * MU, 5 * MU]
    # The control: with something on both sides the same "+" is binary.
    bound = mlist_to_hlist(
        [ord_("a"), THIN_SPACE, bin_("+"), THIN_SPACE, ord_("b")], Style.TEXT, fake
    )
    assert glue_widths(bound) == [3 * MU, 4 * MU, 3 * MU, 4 * MU]


def test_a_space_in_a_script_is_measured_in_the_scripts_math_units(fake: MathFonts) -> None:
    # Unconditional, so it survives script style; eighteen to *that* size's quad.
    script_mu = fake.mu(Style.SCRIPT)
    assert script_mu == 7 != MU
    nodes = mlist_to_hlist([ord_("x", sub=group("i", THIN_SPACE, "j"))], Style.TEXT, fake)
    script = only_box(nodes)
    assert glue_widths(list(script.contents)) == [3 * script_mu]


def test_a_bare_mu_glue_in_a_group_becomes_a_space_and_not_an_ordinary_atom() -> None:
    items = group("a", MuGlue(3), "b").items
    assert [item.kind for item in items if isinstance(item, Atom)] == [
        AtomType.ORD,
        AtomType.SPACE,
        AtomType.ORD,
    ]


def test_a_space_has_no_spacing_class_and_a_malformed_one_is_a_type_error(
    fake: MathFonts,
) -> None:
    with pytest.raises(ValueError, match="not a noad"):
        _ = AtomType.SPACE.spacing_class
    with pytest.raises(TypeError, match="MuGlue"):
        mlist_to_hlist([Atom(AtomType.SPACE, MathChar(ord("x")))], Style.TEXT, fake)
    with pytest.raises(TypeError, match="MuGlue"):
        mlist_to_hlist([Atom(AtomType.ORD, MuGlue(3))], Style.TEXT, fake)


# -- prose in a formula --------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeProse:
    """
    A prose `FontMetrics` with round numbers and exactly one kerned pair.
    """

    face: Face
    size: float

    @property
    def ascent(self) -> float:
        return self.size * 0.8

    @property
    def descent(self) -> float:
        return self.size * 0.2

    @property
    def x_height(self) -> float:
        return self.size / 2

    @property
    def em(self) -> float:
        return self.size

    @property
    def space_width(self) -> float:
        return self.size / 4

    def has(self, codepoint: int) -> bool:
        return True

    def advance(self, codepoint: int) -> float:
        return self.size / 2

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(0.0, -self.size * 0.2, self.size * 0.45, self.size * 0.7)

    def kern(self, codepoint: int, following: int) -> float:
        return -self.size / 10 if (codepoint, following) == (ord("A"), ord("V")) else 0.0


def fake_prose(key: str) -> FakeProse:
    spec = parse_font_key(key)
    return FakeProse(spec.face, float(spec.size))


@pytest.fixture
def worded() -> MathFonts:
    return math_fonts(FAKE_SIZE, lambda size: FakeMathMetrics(float(size)), text=fake_prose)


def test_prose_is_one_box_of_prose_face_characters_at_the_styles_size(worded: MathFonts) -> None:
    box = only_box(mlist_to_hlist([prose_text("if x")], Style.TEXT, worded))
    chars = [n for n in box.contents if isinstance(n, CharNode)]
    assert [chr(c.codepoint) for c in chars] == ["i", "f", "x"]
    assert {c.font for c in chars} == {font_key(Face.PROSE, FAKE_SIZE)}
    # Three advances of half an em and one space of a quarter.
    assert box.width == 3 * 90 + 45
    assert (box.height, box.depth) == (126, 36)


def test_prose_keeps_every_space_it_was_given_and_kerns_as_its_face_kerns(
    worded: MathFonts,
) -> None:
    padded = only_box(mlist_to_hlist([prose_text(" a ")], Style.TEXT, worded))
    assert [type(n) for n in padded.contents] == [Glue, CharNode, Glue]
    kerned = only_box(mlist_to_hlist([prose_text("AV")], Style.TEXT, worded))
    assert [type(n) for n in kerned.contents] == [CharNode, Kern, CharNode]
    kern = kerned.contents[1]
    assert isinstance(kern, Kern) and kern.width == -18
    assert kerned.width == 2 * 90 - 18


def test_prose_in_a_script_is_set_at_the_script_size(worded: MathFonts) -> None:
    nodes = mlist_to_hlist([ord_("x", sub=prose_text("max"))], Style.TEXT, worded)
    script = only_box(nodes)
    script_key = font_key(Face.PROSE, worded.sizes[MathSize.SCRIPT])
    assert script_key != font_key(Face.PROSE, FAKE_SIZE)
    assert [key for key in char_keys(script)] == [script_key] * 3


def char_keys(box: Box) -> list[str]:
    keys: list[str] = []
    for node in box.contents:
        if isinstance(node, CharNode):
            keys.append(node.font)
        elif isinstance(node, Box):
            keys.extend(char_keys(node))
    return keys


def test_prose_can_be_set_in_any_face_the_resolver_knows(worded: MathFonts) -> None:
    box = only_box(mlist_to_hlist([prose_text("b", face=Face.PROSE_BOLD)], Style.TEXT, worded))
    assert char_keys(box) == [font_key(Face.PROSE_BOLD, FAKE_SIZE)]


def test_prose_is_an_ordinary_atom_to_the_spacing_table(worded: MathFonts) -> None:
    nodes = mlist_to_hlist([prose_text("a"), bin_("+"), prose_text("b")], Style.TEXT, worded)
    assert glue_widths(nodes) == [4 * MU, 4 * MU]


def test_prose_packs_where_a_field_is_cleaned_into_a_box_too(worded: MathFonts) -> None:
    # The other route into a field: `_clean_box`, for a numerator.
    fraction = frac(MathText("ab"), MathText("c"))
    vlist = only_box(mlist_to_hlist([fraction], Style.TEXT, worded))
    assert len(char_keys(vlist)) == 3


def test_prose_with_a_character_its_face_lacks_is_refused_and_names_it() -> None:
    # Review 2, item 5: it used to set, with nothing where the word should be.
    @dataclass(frozen=True, slots=True)
    class Latin(FakeProse):
        def has(self, codepoint: int) -> bool:
            return codepoint < 0x250

    def resolve(key: str) -> Latin:
        spec = parse_font_key(key)
        return Latin(spec.face, float(spec.size))

    fonts = math_fonts(FAKE_SIZE, lambda size: FakeMathMetrics(float(size)), text=resolve)
    assert mlist_to_hlist([prose_text("speed")], Style.TEXT, fonts)
    with pytest.raises(MissingGlyphError) as refused:
        mlist_to_hlist([ord_("v"), rel("="), prose_text("ok 速度")], Style.TEXT, fonts)
    assert refused.value.character == "速"
    assert refused.value.face is Face.PROSE
    assert "U+901F" in str(refused.value)
    assert issubclass(MissingGlyphError, MathLayoutError)


def test_fonts_built_without_text_refuse_prose_and_say_so(fake: MathFonts) -> None:
    # This was a KeyError from inside hpack. It is now a refusal with a name, at
    # the atom and at the measure both.
    with pytest.raises(TextFaceUnavailableError, match="without `text`"):
        mlist_to_hlist([prose_text("if")], Style.TEXT, fake)
    with pytest.raises(TextFaceUnavailableError):
        fake.measure(CharNode(font_key(Face.PROSE, FAKE_SIZE), ord("i")))
    # And the three math keys are untouched by any of it.
    assert fake.measure(CharNode(fake.keys[MathSize.TEXT], ord("x"))).width == FAKE_SIZE // 2


def test_a_prose_face_that_does_not_resolve_is_the_same_refusal() -> None:
    def broken(key: str) -> FakeProse:
        raise fontlib.MissingFontError(f"no file for {key}")

    fonts = math_fonts(FAKE_SIZE, lambda size: FakeMathMetrics(float(size)), text=broken)
    with pytest.raises(TextFaceUnavailableError, match="did not resolve"):
        mlist_to_hlist([prose_text("if")], Style.TEXT, fonts)


def test_real_prose_beside_real_math_packs_through_the_one_measure(real: MathFonts) -> None:
    size = real.sizes[MathSize.TEXT]
    prose = fontlib.metrics(Face.PROSE, float(size))
    nodes = mlist_to_hlist([ord_("x"), rel("="), prose_text("fit")], Style.TEXT, real)
    packed = hpack(nodes, measure=real.measure).box
    word = nodes[-1]
    assert isinstance(word, Box)
    advances = sum(round(prose.advance(ord(c))) for c in "fit")
    kerns = round(prose.kern(ord("f"), ord("i"))) + round(prose.kern(ord("i"), ord("t")))
    assert word.width == advances + kerns
    assert [parse_font_key(key).face for key in char_keys(packed)] == [
        Face.MATH,
        Face.MATH,
        Face.PROSE,
        Face.PROSE,
        Face.PROSE,
    ]

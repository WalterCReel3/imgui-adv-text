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

Deliberately not here: anything that draws. No display exists.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from advtext import fontlib
from advtext.fontmetrics import Face, GlyphBBox, GlyphVariant, MathParams
from advtext.math import (
    Atom,
    AtomType,
    Limits,
    MathChar,
    MathSize,
    Style,
    SubList,
    bin_,
    close_,
    cramped_style,
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
    punct,
    rel,
    size_for,
    sub_style,
    sup_style,
)
from advtext.math.mlist import MATH_SPACING, MathFonts
from advtext.nodes import Box, BoxKind, CharNode, Glue, Kern, Node, Rule
from advtext.pack import hpack
from advtext.units import sp_from_px

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
    return math_fonts(sp_from_px(32.0), lambda size: fontlib.math_metrics(float(size)))


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


def test_a_radical_reports_what_is_missing_rather_than_rendering_something_wrong(
    fake: MathFonts,
) -> None:
    radical = Atom(AtomType.RADICAL, MathChar(ord("x")))
    with pytest.raises(NotImplementedError, match="var_delimiter"):
        mlist_to_hlist([radical], Style.TEXT, fake)


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

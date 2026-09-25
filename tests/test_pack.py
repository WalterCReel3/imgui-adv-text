r"""
Claims about `hpack`, `vpack` and interline glue, with the arithmetic pinned.

The glue setting is the part of this system that everything else trusts, and it
fails quietly: a wrong `glue_set` does not raise, it just puts the words in
slightly the wrong places. So the numbers here are exact rather than
approximate, and several of them are the specific values §660 and §817 are
calibrated against -- badness exactly 100 when the whole of the available
stretch is used, which is the edge between "loose" and "underfull".

`_stretch_given_to` restates §2.5's matching-order rule so that "finite glue
gets nothing when `fil` glue is present" can be asserted as a consequence rather
than as a field value. The real renderer belongs to the ship-out task and does
one more thing this helper does not (it accumulates and rounds once across the
line); if the two ever disagree about *which* glue is set, that is worth
knowing.
"""

from __future__ import annotations

import itertools

import pytest

from advtext.nodes import (
    Box,
    BoxKind,
    CharNode,
    Disc,
    Glue,
    GlueSign,
    GlueSpec,
    Kern,
    MathOff,
    MathOn,
    Node,
    Penalty,
    Rule,
)
from advtext.pack import (
    IGNORE_DEPTH,
    OVERFULL_BADNESS,
    CharDimens,
    InterlineSkip,
    PackFitness,
    PackMode,
    append_to_vlist,
    hpack,
    interline_glue,
    vpack,
)
from advtext.units import MAX_DIMEN, RUNNING, GlueOrder, Scaled, sp_from_pt

PT = sp_from_pt(1.0)


def _stretch_given_to(glue: Glue, box: Box) -> float:
    """
    What §2.5 would add to this glue node's natural width inside this box.

    Glue whose order does not match the box's renders at exactly its natural
    width, which is the whole content of the order hierarchy at draw time.
    """
    if box.glue_sign is GlueSign.STRETCHING and glue.spec.stretch_order is box.glue_order:
        return box.glue_set * glue.spec.stretch
    if box.glue_sign is GlueSign.SHRINKING and glue.spec.shrink_order is box.glue_order:
        return -box.glue_set * glue.spec.shrink
    return 0.0


def _text(width: Scaled, height: Scaled = 0, depth: Scaled = 0) -> Box:
    """
    A stand-in for a packed word: a box with dimensions and no contents to measure.
    """
    return Box(kind=BoxKind.HLIST, width=width, height=height, depth=depth)


# --------------------------------------------------------------------------
# hpack: natural size
# --------------------------------------------------------------------------


def test_packing_at_natural_size_sums_widths_and_takes_the_largest_height_and_depth() -> None:
    result = hpack(
        [
            _text(10 * PT, height=7 * PT, depth=0),
            Glue(GlueSpec(width=4 * PT)),
            _text(20 * PT, height=5 * PT, depth=3 * PT),
        ]
    )
    assert result.box.width == 34 * PT
    assert result.box.height == 7 * PT
    assert result.box.depth == 3 * PT
    assert result.natural == 34 * PT


def test_packing_at_natural_size_leaves_the_glue_unset() -> None:
    result = hpack([Glue(GlueSpec(width=4 * PT, stretch=2 * PT))])
    assert result.fitness is PackFitness.EXACT
    assert result.excess == 0
    assert result.box.glue_sign is GlueSign.NORMAL
    assert result.box.glue_set == 0.0
    assert result.badness == 0


def test_kerns_and_math_nodes_add_their_width_without_affecting_height_or_depth() -> None:
    result = hpack([_text(10 * PT, height=7 * PT), Kern(width=2 * PT), MathOn(width=PT), MathOff()])
    assert result.box.width == 13 * PT
    assert result.box.height == 7 * PT


def test_penalties_and_discretionaries_occupy_no_width_at_all() -> None:
    result = hpack([_text(10 * PT), Penalty(50), Disc(pre_break=(_text(99 * PT),))])
    assert result.box.width == 10 * PT


def test_a_box_shifted_down_gives_up_height_and_gains_depth_in_its_container() -> None:
    # §653. Positive shift is downward, and this is the only place the sign of
    # shift_amount is observable from outside.
    shifted = Box(kind=BoxKind.HLIST, width=PT, height=8 * PT, depth=3 * PT, shift_amount=2 * PT)
    result = hpack([shifted])
    assert result.box.height == 6 * PT
    assert result.box.depth == 5 * PT


def test_a_rule_ignores_its_shift_and_its_running_height_loses_the_maximum() -> None:
    result = hpack([_text(PT, height=4 * PT, depth=PT), Rule(width=10 * PT)])
    assert result.box.width == 11 * PT
    assert result.box.height == 4 * PT
    assert result.box.depth == PT


# --------------------------------------------------------------------------
# hpack: stretching
# --------------------------------------------------------------------------


def test_stretch_is_shared_in_proportion_to_each_nodes_stretch_component() -> None:
    thin = Glue(GlueSpec(width=4 * PT, stretch=PT))
    thick = Glue(GlueSpec(width=4 * PT, stretch=3 * PT))
    result = hpack([_text(10 * PT), thin, thick], 30 * PT, PackMode.EXACTLY)

    assert result.excess == 12 * PT
    assert result.box.glue_sign is GlueSign.STRETCHING
    assert result.box.glue_order is GlueOrder.NORMAL
    assert result.box.glue_set == pytest.approx(3.0)
    assert _stretch_given_to(thin, result.box) == pytest.approx(3 * PT)
    assert _stretch_given_to(thick, result.box) == pytest.approx(9 * PT)
    # The parts add up to the whole, which is the property that matters.
    assert _stretch_given_to(thin, result.box) + _stretch_given_to(thick, result.box) == (
        pytest.approx(result.excess)
    )


def test_a_single_fil_glue_absorbs_every_bit_of_stretch_and_finite_glue_gets_none() -> None:
    finite = Glue(GlueSpec(width=4 * PT, stretch=2 * PT))
    infinite = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    result = hpack([finite, infinite], 24 * PT, PackMode.EXACTLY)

    assert result.box.glue_order is GlueOrder.FIL
    assert result.fitness is PackFitness.INFINITE_GLUE
    assert result.badness == 0
    assert _stretch_given_to(finite, result.box) == 0.0
    assert _stretch_given_to(infinite, result.box) == pytest.approx(result.excess)


def test_two_fil_glues_split_the_stretch_evenly_which_is_how_centring_works() -> None:
    left = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    right = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    result = hpack([left, _text(10 * PT), right], 30 * PT, PackMode.EXACTLY)

    assert result.excess == 20 * PT
    assert _stretch_given_to(left, result.box) == pytest.approx(10 * PT)
    assert _stretch_given_to(right, result.box) == pytest.approx(10 * PT)


def test_a_higher_order_of_infinity_takes_everything_from_a_lower_one() -> None:
    fil = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    fill = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FILL))
    result = hpack([fil, fill], 20 * PT, PackMode.EXACTLY)

    assert result.box.glue_order is GlueOrder.FILL
    assert _stretch_given_to(fil, result.box) == 0.0
    assert _stretch_given_to(fill, result.box) == pytest.approx(20 * PT)


def test_a_box_stretched_within_its_glue_is_loose_rather_than_underfull() -> None:
    # Badness is exactly 100 when the whole of the available stretch is used,
    # and §660 reports "Underfull" only above 100. So using all of it is the
    # last case that is merely loose.
    result = hpack([Glue(GlueSpec(width=10 * PT, stretch=5 * PT))], 15 * PT, PackMode.EXACTLY)
    assert result.fitness is PackFitness.LOOSE
    assert result.badness == 100
    assert result.box.glue_set == pytest.approx(1.0)


def test_a_box_stretched_past_its_glue_is_underfull() -> None:
    result = hpack([Glue(GlueSpec(width=10 * PT, stretch=5 * PT))], 25 * PT, PackMode.EXACTLY)
    assert result.fitness is PackFitness.UNDERFULL
    assert result.badness == 2698
    assert result.box.glue_set == pytest.approx(3.0)


def test_a_box_with_no_stretch_at_all_is_underfull_and_its_contents_simply_do_not_fill_it() -> None:
    result = hpack([_text(10 * PT)], 30 * PT, PackMode.EXACTLY)
    assert result.fitness is PackFitness.UNDERFULL
    assert result.badness == 10000
    # §659: nothing to stretch, so the sign reverts to normal and the glue
    # ratio is zero rather than infinite.
    assert result.box.glue_sign is GlueSign.NORMAL
    assert result.box.glue_set == 0.0
    assert result.box.width == 30 * PT


# --------------------------------------------------------------------------
# hpack: shrinking
# --------------------------------------------------------------------------


def test_shrink_is_shared_in_proportion_and_reported_as_tight() -> None:
    thin = Glue(GlueSpec(width=6 * PT, shrink=PT))
    thick = Glue(GlueSpec(width=6 * PT, shrink=3 * PT))
    result = hpack([thin, thick], 10 * PT, PackMode.EXACTLY)

    assert result.excess == -2 * PT
    assert result.box.glue_sign is GlueSign.SHRINKING
    assert result.fitness is PackFitness.TIGHT
    assert result.box.glue_set == pytest.approx(0.5)
    assert _stretch_given_to(thin, result.box) == pytest.approx(-0.5 * PT)
    assert _stretch_given_to(thick, result.box) == pytest.approx(-1.5 * PT)


def test_shrink_is_bounded_so_a_box_squeezed_past_its_glue_is_reported_overfull() -> None:
    # §666: the overflow is not distributed. The glue shrinks as far as it can,
    # the ratio is clamped to exactly one, and the box sticks out.
    result = hpack([Glue(GlueSpec(width=20 * PT, shrink=2 * PT))], 10 * PT, PackMode.EXACTLY)

    assert result.fitness is PackFitness.OVERFULL
    assert result.overfull_by == 8 * PT
    assert result.badness == OVERFULL_BADNESS
    assert result.box.glue_set == 1.0
    assert result.box.glue_sign is GlueSign.SHRINKING
    # The box still claims the width it was asked for; the contents exceed it.
    assert result.box.width == 10 * PT


def test_using_exactly_all_the_available_shrink_is_tight_and_not_yet_overfull() -> None:
    result = hpack([Glue(GlueSpec(width=20 * PT, shrink=2 * PT))], 18 * PT, PackMode.EXACTLY)
    assert result.fitness is PackFitness.TIGHT
    assert result.overfull_by == 0
    assert result.box.glue_set == pytest.approx(1.0)
    assert result.badness == 100


def test_infinite_shrink_is_never_overfull_because_it_is_unbounded() -> None:
    result = hpack(
        [Glue(GlueSpec(width=20 * PT, shrink=1, shrink_order=GlueOrder.FIL))],
        PT,
        PackMode.EXACTLY,
    )
    assert result.fitness is PackFitness.INFINITE_GLUE
    assert result.overfull_by == 0
    assert result.box.glue_order is GlueOrder.FIL


# --------------------------------------------------------------------------
# hpack: modes, empty lists, and the errors
# --------------------------------------------------------------------------


def test_additional_mode_adds_the_target_to_the_natural_size() -> None:
    nodes: list[Node] = [_text(10 * PT), Glue(GlueSpec(width=2 * PT, stretch=PT))]
    natural = hpack(nodes)
    wider = hpack(nodes, 5 * PT, PackMode.ADDITIONAL)
    assert natural.box.width == 12 * PT
    assert wider.box.width == 17 * PT
    assert wider.excess == 5 * PT


def test_an_empty_box_packed_to_a_target_is_a_spacer_rather_than_a_defect() -> None:
    # Every diagnostic in §660-§667 is guarded by `list_ptr(r) <> null`, because
    # `\hbox to 1in{}` is something a person writes on purpose.
    result = hpack([], 72 * PT, PackMode.EXACTLY)
    assert result.fitness is PackFitness.EMPTY
    assert result.badness == 0
    assert result.box.width == 72 * PT


def test_packing_a_character_without_a_way_to_measure_it_fails_loudly() -> None:
    with pytest.raises(ValueError, match="no `measure`"):
        hpack([CharNode("prose-16", ord("a"))])


def test_a_measured_character_contributes_its_advance_and_its_ink_extents() -> None:
    def measure(char: CharNode) -> CharDimens:
        return CharDimens(width=5 * PT, height=7 * PT, depth=2 * PT)

    result = hpack([CharNode("prose-16", ord("g"))] * 3, measure=measure)
    assert result.box.width == 15 * PT
    assert result.box.height == 7 * PT
    assert result.box.depth == 2 * PT


def test_a_running_width_in_a_horizontal_list_is_rejected_rather_than_silently_negative() -> None:
    # RUNNING is -2**30. Adding it to a width would produce a box 16384pt short
    # and no error at all, which is the worst available outcome.
    with pytest.raises(ValueError, match="never running inside an hlist"):
        hpack([Rule()])


# --------------------------------------------------------------------------
# vpack
# --------------------------------------------------------------------------


def test_heights_and_depths_chain_down_a_vertical_list_rather_than_taking_a_maximum() -> None:
    # §670: each box contributes the previous item's depth plus its own height,
    # and the last item's depth becomes the box's depth.
    result = vpack(
        [
            _text(PT, height=10 * PT, depth=2 * PT),
            _text(PT, height=8 * PT, depth=3 * PT),
        ]
    )
    assert result.box.height == 10 * PT + 2 * PT + 8 * PT
    assert result.box.depth == 3 * PT


def test_a_vertical_lists_width_is_the_widest_item_shifted_right_by_its_shift_amount() -> None:
    result = vpack(
        [
            _text(30 * PT),
            Box(kind=BoxKind.HLIST, width=20 * PT, shift_amount=15 * PT),
        ]
    )
    assert result.box.width == 35 * PT


def test_glue_in_a_vertical_list_closes_off_the_running_depth_before_adding_its_width() -> None:
    # §671: `x := x + d; d := 0` before the glue's own width is counted, so a
    # box's depth is paid for once and does not overlap the glue below it.
    result = vpack(
        [
            _text(PT, height=10 * PT, depth=4 * PT),
            Glue(GlueSpec(width=6 * PT)),
            _text(PT, height=8 * PT, depth=PT),
        ]
    )
    assert result.box.height == 10 * PT + 4 * PT + 6 * PT + 8 * PT
    assert result.box.depth == PT


def test_depth_past_the_limit_becomes_height_so_the_reference_point_moves_down() -> None:
    # §668. The excess is converted, not discarded: the box keeps its total
    # extent and the baseline moves.
    result = vpack([_text(PT, height=10 * PT, depth=9 * PT)], max_depth=2 * PT)
    assert result.box.depth == 2 * PT
    assert result.box.height == 17 * PT
    assert result.box.height + result.box.depth == 19 * PT


def test_plain_vpack_does_not_clamp_the_depth() -> None:
    result = vpack([_text(PT, height=10 * PT, depth=9 * PT)])
    assert result.box.depth == 9 * PT
    assert result.box.height == 10 * PT
    assert MAX_DIMEN > 9 * PT


def test_vertical_glue_sets_exactly_as_horizontal_glue_does() -> None:
    top = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    bottom = Glue(GlueSpec(stretch=1, stretch_order=GlueOrder.FIL))
    result = vpack([top, _text(PT, height=10 * PT), bottom], 30 * PT, PackMode.EXACTLY)

    assert result.box.kind is BoxKind.VLIST
    assert result.box.glue_order is GlueOrder.FIL
    assert _stretch_given_to(top, result.box) == pytest.approx(10 * PT)
    assert _stretch_given_to(bottom, result.box) == pytest.approx(10 * PT)


def test_an_overfull_vertical_box_is_reported_just_like_a_horizontal_one() -> None:
    result = vpack(
        [_text(PT, height=20 * PT), Glue(GlueSpec(width=10 * PT, shrink=2 * PT))],
        25 * PT,
        PackMode.EXACTLY,
    )
    assert result.fitness is PackFitness.OVERFULL
    assert result.overfull_by == 3 * PT
    assert result.badness == OVERFULL_BADNESS


def test_a_character_in_a_vertical_list_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="cannot appear in a vertical list"):
        vpack([CharNode("prose-16", ord("a"))])


def test_a_running_height_in_a_vertical_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="never running inside a vlist"):
        vpack([Rule(width=10 * PT)])


def test_a_rule_with_a_running_width_still_packs_into_a_vertical_list() -> None:
    # The invariant runs the other way here: a horizontal rule's *width* is the
    # one that gets resolved against the enclosing box, and it must lose the
    # maximum rather than win it.
    result = vpack([_text(20 * PT, height=PT), Rule(width=RUNNING, height=PT, depth=0)])
    assert result.box.width == 20 * PT
    assert result.box.height == 2 * PT


# --------------------------------------------------------------------------
# interline glue (§679)
# --------------------------------------------------------------------------

BASELINE = GlueSpec(width=12 * PT, stretch=2 * PT, shrink=PT)
LINESKIP = GlueSpec(width=PT, stretch=PT // 2)
SKIP = InterlineSkip(baselineskip=BASELINE, lineskip=LINESKIP, lineskiplimit=0)


def test_no_interline_glue_goes_above_the_first_box_in_a_vertical_list() -> None:
    assert interline_glue(IGNORE_DEPTH, _text(PT, height=7 * PT), SKIP) is None


def test_a_prev_depth_below_the_sentinel_also_suppresses_the_glue() -> None:
    assert interline_glue(IGNORE_DEPTH - PT, _text(PT, height=7 * PT), SKIP) is None


def test_the_ignore_depth_sentinel_is_exactly_minus_one_thousand_points() -> None:
    assert IGNORE_DEPTH == -1000 * PT
    assert IGNORE_DEPTH == -65_536_000


def test_interline_glue_makes_the_baseline_to_baseline_distance_the_baselineskip() -> None:
    glue = interline_glue(2 * PT, _text(PT, height=7 * PT), SKIP)
    assert glue is not None
    # 12pt wanted, minus 2pt already below the previous baseline, minus 7pt
    # above this one.
    assert glue.spec.width == 3 * PT


def test_the_baselineskip_copy_keeps_its_stretch_and_shrink_and_only_its_width_changes() -> None:
    # `new_skip_param` copies the spec and overwrites `width` alone. Building a
    # fresh GlueSpec(width=d) instead would make every interline gap rigid, and
    # a stretched vertical list would then have nowhere to put the stretch --
    # which is visible only as slightly wrong rhythm, never as an error.
    glue = interline_glue(2 * PT, _text(PT, height=7 * PT), SKIP)
    assert glue is not None
    assert glue.spec.stretch == BASELINE.stretch
    assert glue.spec.shrink == BASELINE.shrink
    assert glue.spec.stretch_order is BASELINE.stretch_order
    # And the parameter itself is untouched, so the next line computes the same.
    assert BASELINE.width == 12 * PT


def test_a_tall_line_falls_back_to_lineskip_when_the_gap_would_be_below_the_limit() -> None:
    # 12 - 2 - 11 = -1pt: the boxes would collide, so TeX gives up on constant
    # baselines and guarantees a minimum visual gap instead.
    glue = interline_glue(2 * PT, _text(PT, height=11 * PT), SKIP)
    assert glue is not None
    assert glue.spec == LINESKIP


def test_the_lineskip_fallback_uses_the_parameter_as_it_is_stretch_included() -> None:
    glue = interline_glue(2 * PT, _text(PT, height=20 * PT), SKIP)
    assert glue is not None
    assert glue.spec.width == LINESKIP.width
    assert glue.spec.stretch == LINESKIP.stretch


def test_lineskiplimit_moves_the_boundary_without_touching_the_calculation() -> None:
    generous = InterlineSkip(baselineskip=BASELINE, lineskip=LINESKIP, lineskiplimit=4 * PT)
    # The gap is 3pt, which is fine against a limit of 0 and not against 4pt.
    assert interline_glue(2 * PT, _text(PT, height=7 * PT), SKIP) == Glue(
        GlueSpec(width=3 * PT, stretch=2 * PT, shrink=PT)
    )
    assert interline_glue(2 * PT, _text(PT, height=7 * PT), generous) == Glue(LINESKIP)


def test_a_gap_exactly_at_the_lineskiplimit_still_uses_baselineskip() -> None:
    # The source tests `d < line_skip_limit`, so equality keeps the constant
    # baselines. An off-by-one here would show up as a rhythm that breaks on
    # exactly one line in a page.
    limit = 3 * PT
    skip = InterlineSkip(baselineskip=BASELINE, lineskip=LINESKIP, lineskiplimit=limit)
    glue = interline_glue(2 * PT, _text(PT, height=7 * PT), skip)
    assert glue is not None
    assert glue.spec.width == limit
    assert glue.spec.stretch == BASELINE.stretch


def test_appending_boxes_interleaves_the_glue_and_reports_the_new_prev_depth() -> None:
    first = _text(PT, height=7 * PT, depth=2 * PT)
    second = _text(PT, height=7 * PT, depth=PT)
    vlist: list[Node] = []

    prev_depth = append_to_vlist(vlist, first, IGNORE_DEPTH, SKIP)
    assert vlist == [first]
    assert prev_depth == 2 * PT

    prev_depth = append_to_vlist(vlist, second, prev_depth, SKIP)
    assert vlist == [first, Glue(GlueSpec(width=3 * PT, stretch=2 * PT, shrink=PT)), second]
    assert prev_depth == PT


def test_a_rule_gets_no_interline_glue_above_it_and_suppresses_the_glue_below_it() -> None:
    # tex.web 20515-20522: a rule reaches a vertical list by tail_append, not by
    # append_to_vlist, and the same line sets `prev_depth := ignore_depth`.
    # "Note that baselineskip calculations are disabled after a rule in vertical
    # mode." So a rule is insulated on both sides and the document supplies its
    # own spacing -- this is the markdown `---` between two paragraphs.
    above = _text(PT, height=7 * PT, depth=2 * PT)
    rule = Rule(width=100 * PT, height=PT // 2, depth=0)
    below = _text(PT, height=7 * PT, depth=2 * PT)
    vlist: list[Node] = []

    prev_depth = append_to_vlist(vlist, above, IGNORE_DEPTH, SKIP)
    prev_depth = append_to_vlist(vlist, rule, prev_depth, SKIP)
    assert prev_depth == IGNORE_DEPTH
    prev_depth = append_to_vlist(vlist, below, prev_depth, SKIP)

    assert vlist == [above, rule, below]
    assert not any(isinstance(node, Glue) for node in vlist)


def test_a_box_after_a_rule_would_otherwise_have_received_a_baselineskip_gap() -> None:
    # The same box *does* get glue when what precedes it is a box rather than a
    # rule, which is what makes the previous test a claim about rules and not
    # about these particular dimensions.
    rule = Rule(width=100 * PT, height=PT // 2, depth=0)
    spacer = _text(PT, height=PT, depth=2 * PT)
    box = _text(PT, height=7 * PT, depth=2 * PT)

    after_rule: list[Node] = []
    prev_depth = append_to_vlist(after_rule, rule, IGNORE_DEPTH, SKIP)
    append_to_vlist(after_rule, box, prev_depth, SKIP)

    after_box: list[Node] = []
    prev_depth = append_to_vlist(after_box, spacer, IGNORE_DEPTH, SKIP)
    append_to_vlist(after_box, box, prev_depth, SKIP)

    assert after_rule == [rule, box]
    assert after_box == [spacer, Glue(GlueSpec(width=3 * PT, stretch=2 * PT, shrink=PT)), box]


def test_a_vertical_list_built_with_interline_glue_has_evenly_spaced_baselines() -> None:
    # The point of the whole rule: whatever the heights and depths, consecutive
    # baselines sit exactly `\baselineskip` apart until a line is too tall.
    boxes = [
        _text(PT, height=7 * PT, depth=2 * PT),
        _text(PT, height=5 * PT, depth=0),
        _text(PT, height=9 * PT, depth=PT),
    ]
    vlist: list[Node] = []
    prev_depth = IGNORE_DEPTH
    for box in boxes:
        prev_depth = append_to_vlist(vlist, box, prev_depth, SKIP)

    baselines: list[Scaled] = []
    pen: Scaled = 0
    for node in vlist:
        if isinstance(node, Glue):
            pen += node.spec.width
        else:
            assert isinstance(node, Box)
            pen += node.height
            baselines.append(pen)
            pen += node.depth

    assert [b - a for a, b in itertools.pairwise(baselines)] == [12 * PT, 12 * PT]

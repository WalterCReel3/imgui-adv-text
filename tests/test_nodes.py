"""
Claims about the node vocabulary, concentrated on the two things it can get wrong.

The types themselves are dataclasses and mostly need no defending. Two
properties do:

- **Orders of infinity must not combine.** The §646 worked example is here as a
  test because it is the case that a plausible wrong implementation fails and
  every simpler case passes.
- **Height and depth must not be swapped**, and the baseline convention has to
  survive being carried through a box.

The discardability partition is tested too, since §148 makes it load-bearing for
line breaking and we lost the type-code ordering that enforced it in the source.
"""

from __future__ import annotations

import dataclasses

import pytest

from imscribe.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    BoxKind,
    CharNode,
    Disc,
    Glue,
    GlueSpec,
    GlueTotal,
    Kern,
    KernKind,
    MathOff,
    MathOn,
    Penalty,
    Rule,
    is_discardable,
    permits_break_at_following_glue,
)
from imscribe.units import RUNNING, GlueOrder, sp_from_pt

PT = sp_from_pt(1.0)


def test_finite_stretch_does_not_add_to_infinite_stretch() -> None:
    total = GlueTotal.of(10 * PT) + GlueTotal.of(1, GlueOrder.FIL)
    assert total[GlueOrder.NORMAL] == 10 * PT
    assert total[GlueOrder.FIL] == 1
    assert total.dominant_order is GlueOrder.FIL
    assert total.dominant == 1


def test_a_lower_order_of_infinity_survives_a_higher_one_cancelling_itself() -> None:
    # §646's own example: 3pt, 8fill, 5fil, 6pt, -3fil, -8fill total to
    # "essentially 2fil". A GlueTotal that folded each addition into the
    # highest order present would lose the 5fil at the second step and report
    # nothing at all here, which is the defect this type exists to prevent.
    total = (
        GlueTotal.of(3 * PT)
        + GlueTotal.of(8, GlueOrder.FILL)
        + GlueTotal.of(5, GlueOrder.FIL)
        + GlueTotal.of(6 * PT)
        + GlueTotal.of(-3, GlueOrder.FIL)
        + GlueTotal.of(-8, GlueOrder.FILL)
    )
    assert total.dominant_order is GlueOrder.FIL
    assert total.dominant == 2
    assert total[GlueOrder.NORMAL] == 9 * PT
    assert total[GlueOrder.FILL] == 0


def test_the_highest_nonzero_order_wins_regardless_of_how_small_its_amount_is() -> None:
    total = GlueTotal.of(100 * PT) + GlueTotal.of(1, GlueOrder.FILLL)
    assert total.dominant_order is GlueOrder.FILLL
    assert total.dominant == 1


def test_a_total_that_cancels_at_every_order_reports_normal_order_and_zero() -> None:
    total = GlueTotal.of(5, GlueOrder.FILL) + GlueTotal.of(-5, GlueOrder.FILL)
    assert total.dominant_order is GlueOrder.NORMAL
    assert total.dominant == 0


def test_an_empty_glue_total_is_the_identity_for_addition() -> None:
    populated = GlueTotal.of(7 * PT) + GlueTotal.of(2, GlueOrder.FIL)
    assert GlueTotal() + populated == populated
    assert populated + GlueTotal() == populated


def test_glue_totals_add_associatively_so_accumulation_order_cannot_change_the_answer() -> None:
    a = GlueTotal.of(3 * PT)
    b = GlueTotal.of(8, GlueOrder.FILL)
    c = GlueTotal.of(5, GlueOrder.FIL)
    assert (a + b) + c == a + (b + c)


def test_a_box_round_trips_its_width_height_and_depth_without_swapping_them() -> None:
    box = Box(
        kind=BoxKind.HLIST,
        width=100 * PT,
        height=7 * PT,
        depth=2 * PT,
    )
    assert box.width == 100 * PT
    assert box.height == 7 * PT
    assert box.depth == 2 * PT


def test_height_is_above_the_baseline_and_depth_below_it_so_they_are_not_interchangeable() -> None:
    # The convention, spelled as arithmetic: at baseline y in a downward-growing
    # coordinate system the box spans y - height to y + depth (§1.3). A glyph
    # with a descender has depth and one without has none, and a box that
    # confused the two would place them identically.
    baseline = 50 * PT
    parenthesis = Box(kind=BoxKind.HLIST, height=8 * PT, depth=3 * PT)
    ex = Box(kind=BoxKind.HLIST, height=5 * PT, depth=0)

    assert baseline - parenthesis.height == 42 * PT
    assert baseline + parenthesis.depth == 53 * PT
    assert baseline + ex.depth == baseline
    assert parenthesis.height + parenthesis.depth > ex.height + ex.depth


def test_a_positive_shift_amount_lowers_a_box_in_an_hlist() -> None:
    # §653: a shifted box contributes height - s and depth + s to its enclosing
    # box, so a positive shift takes away from the height and adds to the depth.
    shift = 2 * PT
    box = Box(kind=BoxKind.HLIST, height=8 * PT, depth=3 * PT, shift_amount=shift)
    assert box.height - box.shift_amount == 6 * PT
    assert box.depth + box.shift_amount == 5 * PT


def test_a_new_box_is_unset_with_natural_glue() -> None:
    box = Box(kind=BoxKind.VLIST)
    assert box.contents == ()
    assert box.glue_set == 0.0
    assert box.glue_order is GlueOrder.NORMAL
    assert (box.width, box.height, box.depth, box.shift_amount) == (0, 0, 0, 0)


def test_a_rules_dimensions_start_running_so_they_are_resolved_by_the_enclosing_box() -> None:
    assert Rule().is_running
    assert Rule(width=RUNNING, height=PT // 2, depth=0).is_running
    assert not Rule(width=100 * PT, height=PT // 2, depth=0).is_running


def test_glue_kern_penalty_and_math_are_discarded_after_a_break_and_the_rest_are_not() -> None:
    # §148's partition. The source encodes it as a comparison on type codes; we
    # have an unordered union, so this test is what holds the two in agreement.
    discarded = [
        Glue(GlueSpec(width=4 * PT)),
        Kern(width=PT),
        Kern(width=PT, kind=KernKind.EXPLICIT),
        Penalty(50),
        MathOn(),
        MathOff(),
    ]
    kept = [
        CharNode("roboto-regular-16", ord("a")),
        Box(kind=BoxKind.HLIST),
        Box(kind=BoxKind.VLIST),
        Rule(),
        Disc(),
    ]
    assert all(is_discardable(node) for node in discarded)
    assert not any(is_discardable(node) for node in kept)


def test_a_font_kern_permits_a_break_at_the_glue_after_it_and_an_explicit_kern_does_not() -> None:
    # §868's third branch: `(type(prev_p)=kern_node) and (subtype(prev_p)<>explicit)`.
    # A kern is discardable, so this is the case that proves the breakpoint rule
    # is not the negation of `is_discardable` -- both kerns below are discarded
    # after a break and only one of them offers a break at the glue that follows.
    font_kern = Kern(width=-PT // 20, kind=KernKind.NORMAL)
    explicit_kern = Kern(width=3 * PT, kind=KernKind.EXPLICIT)

    assert permits_break_at_following_glue(font_kern)
    assert not permits_break_at_following_glue(explicit_kern)
    assert is_discardable(font_kern) and is_discardable(explicit_kern)


def test_the_break_at_glue_rule_admits_exactly_section_868s_three_branches() -> None:
    # Branches one and two -- `is_char_node(prev_p)`, then `precedes_break`,
    # which is `type(p) < math_node` and so covers boxes, rules and
    # discretionaries. Glue, penalties and math nodes fail all three: a math
    # node is `type = math_node` and the break it offers is taken at the node
    # itself by §866, never at the glue after it.
    permitted = [
        CharNode("roboto-regular-16", ord("a")),
        Box(kind=BoxKind.HLIST),
        Box(kind=BoxKind.VLIST),
        Rule(),
        Disc(),
        Kern(width=PT, kind=KernKind.NORMAL),
        Kern(width=PT, kind=KernKind.ACCENT),
    ]
    refused = [
        Glue(GlueSpec(width=4 * PT)),
        Kern(width=PT, kind=KernKind.EXPLICIT),
        Penalty(50),
        MathOn(),
        MathOff(),
    ]
    assert all(permits_break_at_following_glue(node) for node in permitted)
    assert not any(permits_break_at_following_glue(node) for node in refused)


def test_an_infinite_penalty_forbids_a_break_and_an_eject_penalty_forces_one() -> None:
    assert Penalty(INF_PENALTY).forbids_break
    assert Penalty(INF_PENALTY + 1).forbids_break
    assert not Penalty(INF_PENALTY - 1).forbids_break

    assert Penalty(EJECT_PENALTY).forces_break
    assert Penalty(EJECT_PENALTY - 1).forces_break
    assert not Penalty(EJECT_PENALTY + 1).forces_break


def test_an_ordinary_penalty_neither_forbids_nor_forces_a_break() -> None:
    for value in (-9999, -100, 0, 100, 9999):
        penalty = Penalty(value)
        assert not penalty.forbids_break
        assert not penalty.forces_break


def test_the_penalty_sentinels_share_inf_bads_magnitude_as_the_source_defines_them() -> None:
    # §157: inf_penalty = inf_bad, eject_penalty = -inf_penalty. They are
    # compared against badness in the demerits formula, so the magnitudes match
    # on purpose rather than by coincidence.
    assert INF_PENALTY == 10000
    assert EJECT_PENALTY == -10000


def test_a_glue_spec_is_shareable_between_glue_nodes_because_it_is_a_value() -> None:
    baseline_skip = GlueSpec(width=12 * PT, stretch=PT, shrink=PT)
    first, second = Glue(baseline_skip), Glue(baseline_skip)
    assert first == second
    assert first.spec is second.spec


def test_nodes_are_frozen_so_a_packed_list_cannot_be_mutated_behind_a_boxs_back() -> None:
    box = Box(kind=BoxKind.HLIST, width=10 * PT)
    with pytest.raises(dataclasses.FrozenInstanceError):
        box.width = 20 * PT  # type: ignore[misc]

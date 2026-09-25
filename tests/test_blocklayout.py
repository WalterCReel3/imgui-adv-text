r"""
Claims about block layout, and about the argument it is making.

Two of these carry the thesis and the rest support it:

- `test_a_centred_item_stays_centred_at_every_width` -- nothing recomputes a
  centre. Two spacers of equal weight always receive equal shares, so the centre
  is a consequence of the glue rather than a rule applied to it.
- `test_a_fil_spacer_takes_the_whole_surplus_and_a_finite_one_takes_nothing` --
  the priority tier flexbox has no way to express. The finite spacer here has a
  thousand times the weight of anything else in the row and still gets exactly
  its natural size.

Sizes are whole points so an expected position is arithmetic. Positions are read
back through `place`, which goes through `hpack`, `vpack` and `ship` -- the same
code a paragraph goes through -- so these are tests of the real pipeline and not
of a parallel one.
"""

from __future__ import annotations

from advtext.blocklayout import (
    Column,
    Leaf,
    Row,
    Separator,
    centre,
    flex,
    gap,
    layout,
    leaves,
    left,
    measure,
    place,
    right,
    space_around,
    space_between,
    space_evenly,
    spacer,
)
from advtext.pack import PackFitness
from advtext.shipout import Point
from advtext.units import GlueOrder, Scaled, sp_from_pt

PT = sp_from_pt(1.0)

_HEIGHT: Scaled = 10 * PT


def _leaf(points: float, name: str = "") -> Leaf:
    """
    A block `points` wide and a fixed ten points tall, so widths are the variable.
    """
    return Leaf(width=round(points * PT), height=_HEIGHT, name=name)


def _xs(row: Row | Column, width: Scaled | None = None) -> list[Scaled]:
    """
    The left edge of every leaf, in tree order.
    """
    return [rect.x for rect in place(row, width=width)]


# --------------------------------------------------------------------------
# The two that carry the argument
# --------------------------------------------------------------------------


def test_a_centred_item_stays_centred_at_every_width() -> None:
    # Nothing recomputes the centre when the container resizes. Two spacers of
    # equal weight split whatever surplus exists into equal shares, so "centred"
    # is what the glue does rather than a rule someone applies.
    item = _leaf(20)
    for points in (30, 50, 100, 200, 301, 999):
        width = round(points * PT)
        (rect,) = place(Row(centre([item])), width=width)
        before = rect.x
        after = width - (rect.x + rect.width)
        assert abs(before - after) <= 1, f"not centred at {points}pt"
        assert rect.width == item.width


def test_centring_is_exact_to_within_one_scaled_point_when_the_surplus_is_odd() -> None:
    # An odd surplus cannot be halved into two integers, and §625 resolves the
    # tie away from zero, so the left share is one scaled point larger. That is
    # 1/65536 of a point -- worth pinning as a known, bounded asymmetry rather
    # than leaving someone to discover it as a suspicious off-by-one.
    (rect,) = place(Row(centre([_leaf(20)])), width=100 * PT + 1)
    before = rect.x
    after = (100 * PT + 1) - (rect.x + rect.width)
    assert before - after == 1


def test_a_fil_spacer_takes_the_whole_surplus_and_a_finite_one_takes_nothing() -> None:
    # The priority tier. The finite spacer has a weight of a thousand and the
    # infinite one a weight of one, and the finite one still gets exactly zero:
    # §646 uses the highest order present "as if no other orders were present".
    # Flexbox has one proportional pool and cannot say this at all.
    row = Row((_leaf(10, "a"), flex(1000), _leaf(10, "b"), spacer(), _leaf(10, "c")))
    a, b, c = _xs(row, 100 * PT)

    assert a == 0
    assert b == 10 * PT, "the finite spacer grew, so the order hierarchy is not being applied"
    assert c == 90 * PT


def test_a_higher_order_spacer_beats_a_lower_order_one_by_the_same_rule() -> None:
    # And it is a hierarchy rather than a single special case: fill beats fil
    # exactly as fil beats finite, with no code anywhere distinguishing them.
    row = Row(
        (
            _leaf(10),
            spacer(order=GlueOrder.FIL),
            _leaf(10),
            spacer(order=GlueOrder.FILL),
            _leaf(10),
        )
    )
    a, b, c = _xs(row, 100 * PT)
    assert (a, b, c) == (0, 10 * PT, 90 * PT)


# --------------------------------------------------------------------------
# Proportional division
# --------------------------------------------------------------------------


def test_two_flexes_split_the_surplus_in_the_ratio_of_their_weights() -> None:
    row = Row((_leaf(10), flex(1), _leaf(10), flex(2), _leaf(10)))
    for points in (60, 100, 200, 400):
        width = round(points * PT)
        a, b, c = _xs(row, width)
        surplus = width - 30 * PT
        first_gap = b - (a + 10 * PT)
        second_gap = c - (b + 10 * PT)

        assert first_gap + second_gap == surplus
        assert abs(2 * first_gap - second_gap) <= 2, f"ratio drifted at {points}pt"


def test_the_ratio_split_holds_even_when_the_surplus_does_not_divide_evenly() -> None:
    # Three weights against a surplus of one scaled point. §625's accumulate-
    # and-difference gives the whole point to one of them rather than giving a
    # third to each and losing it to rounding -- the shares still sum to the
    # surplus exactly, which is what stops a row from failing to fill its box.
    row = Row((_leaf(10), flex(1), _leaf(10), flex(1), _leaf(10), flex(1), _leaf(10)))
    width = 40 * PT + 1
    a, b, c, d = _xs(row, width)
    gaps = [b - (a + 10 * PT), c - (b + 10 * PT), d - (c + 10 * PT)]

    assert sum(gaps) == 1
    assert layout(row, width=width).width == width


def test_equal_weights_give_equal_shares() -> None:
    row = Row((_leaf(10), flex(), _leaf(10), flex(), _leaf(10)))
    a, b, c = _xs(row, 100 * PT)
    assert b - (a + 10 * PT) == c - (b + 10 * PT) == 35 * PT


# --------------------------------------------------------------------------
# The six alignments, which are six placements and not six flags
# --------------------------------------------------------------------------


def test_left_alignment_puts_the_surplus_after_the_last_child() -> None:
    assert _xs(Row(left([_leaf(10), _leaf(10)])), 100 * PT) == [0, 10 * PT]


def test_right_alignment_puts_the_surplus_before_the_first_child() -> None:
    assert _xs(Row(right([_leaf(10), _leaf(10)])), 100 * PT) == [80 * PT, 90 * PT]


def test_space_between_puts_nothing_at_the_ends_and_an_equal_share_in_each_gap() -> None:
    a, b, c = _xs(Row(space_between([_leaf(10), _leaf(10), _leaf(10)])), 100 * PT)
    assert a == 0
    assert c + 10 * PT == 100 * PT
    assert b - (a + 10 * PT) == c - (b + 10 * PT) == 35 * PT


def test_space_around_gives_each_child_equal_space_on_both_sides() -> None:
    # CSS specifies this as a behaviour and needs a paragraph to do it. Here it
    # is a weight of 2 in the interior against 1 at the ends, and the observable
    # consequence -- each child's centre sits at (2k+1)/2n of the width -- falls
    # out rather than being arranged.
    width = 120 * PT
    rects = place(Row(space_around([_leaf(10), _leaf(10), _leaf(10)])), width=width)
    centres = [rect.x + rect.width // 2 for rect in rects]
    assert centres == [width // 6, width // 2, 5 * width // 6]


def test_space_evenly_makes_every_gap_equal_including_the_ends() -> None:
    a, b, c = _xs(Row(space_evenly([_leaf(10), _leaf(10), _leaf(10)])), 100 * PT)
    ends = a
    assert ends == 17 * PT + PT // 2
    assert b - (a + 10 * PT) == c - (b + 10 * PT) == ends
    assert 100 * PT - (c + 10 * PT) == ends


def test_an_alignment_helper_of_one_child_still_behaves() -> None:
    # The degenerate cases, because a layout built from a list comprehension will
    # hit them and a crash at zero or one child is the least useful kind.
    assert space_between(()) == ()
    assert space_around(()) == ()
    assert space_evenly(()) == ()
    assert len(space_between([_leaf(10)])) == 1
    assert _xs(Row(space_between([_leaf(10)])), 100 * PT) == [0]


# --------------------------------------------------------------------------
# Gaps, separators, and what happens under compression
# --------------------------------------------------------------------------


def test_a_gap_keeps_its_natural_size_when_there_is_nothing_to_distribute() -> None:
    row = Row((_leaf(10), gap(5 * PT), _leaf(10)))
    a, b = _xs(row)
    assert b - a == 15 * PT
    assert layout(row).width == 25 * PT


def test_a_gap_with_shrink_closes_under_compression_and_a_separator_does_not() -> None:
    # The distinction that makes a kern worth having in a system with no line
    # breaking: it is rigid when everything else gives. A gutter declared with
    # `Separator` survives a squeeze that closes every `Gap` in the row.
    row = Row(
        (
            _leaf(10, "a"),
            gap(10 * PT, shrink=10 * PT),
            _leaf(10, "b"),
            Separator(10 * PT),
            _leaf(10, "c"),
        )
    )
    assert layout(row).width == 50 * PT

    a, b, c = _xs(row, 40 * PT)
    assert b - (a + 10 * PT) == 0, "the shrinkable gap did not close"
    assert c - (b + 10 * PT) == 10 * PT, "the separator shrank, and a kern never shrinks"


def test_a_row_squeezed_past_its_shrink_reports_overfull_rather_than_lying() -> None:
    # `advtext.pack` returns the diagnostic instead of printing it, so a layout
    # debugger -- or a test -- can say "this toolbar is 5pt overfull at 35pt"
    # rather than discovering it visually.
    row = Row((_leaf(10), gap(10 * PT, shrink=10 * PT), _leaf(10), _leaf(10)))
    result = measure(row, width=25 * PT)
    assert result.fitness is PackFitness.OVERFULL
    assert result.overfull_by == 5 * PT


def test_a_row_with_no_stretch_at_all_is_simply_underfull() -> None:
    row = Row((_leaf(10), _leaf(10)))
    result = measure(row, width=100 * PT)
    assert result.fitness is PackFitness.UNDERFULL
    assert result.box.width == 100 * PT


# --------------------------------------------------------------------------
# The toolbar, and the limit of what it can honestly claim
# --------------------------------------------------------------------------


def _toolbar(left_width: float, right_width: float) -> Row:
    """
    Fixed controls at each end, a title between two spacers.
    """
    return Row(
        (
            _leaf(left_width, "left controls"),
            spacer(),
            _leaf(30, "title"),
            spacer(),
            _leaf(right_width, "right controls"),
        )
    )


def test_a_symmetric_toolbar_centres_its_title_and_keeps_it_centred() -> None:
    toolbar = _toolbar(20, 20)
    for points in (120, 240, 500):
        width = round(points * PT)
        _, title, _ = place(toolbar, width=width)
        assert abs((title.x + title.width // 2) - width // 2) <= 1


def test_an_asymmetric_toolbar_centres_its_title_in_the_surplus_and_not_in_the_bar() -> None:
    # The honest limit, and it is the same limit flexbox has. Two equal spacers
    # split the space *left over*, so the title is centred between the flanks
    # rather than in the container whenever the flanks differ. Centring it in the
    # container needs the shorter flank padded to match, which is a decision for
    # whoever is designing the toolbar and not something glue can infer.
    width = 200 * PT
    _, title, _ = place(_toolbar(20, 60), width=width)
    centre_of_title = title.x + title.width // 2
    centre_of_bar = width // 2
    centre_of_surplus = (20 * PT + (width - 60 * PT)) // 2

    assert centre_of_title != centre_of_bar
    assert abs(centre_of_title - centre_of_surplus) <= 1


def test_the_toolbars_ends_stay_pinned_to_the_edges_at_any_width() -> None:
    toolbar = _toolbar(20, 20)
    for points in (120, 240, 500):
        width = round(points * PT)
        first, _, last = place(toolbar, width=width)
        assert first.x == 0
        assert last.x + last.width == width


# --------------------------------------------------------------------------
# Columns, nesting and the propagation rule
# --------------------------------------------------------------------------


def test_a_column_stacks_its_children_and_hands_its_width_down_to_each_row() -> None:
    column = Column((Row(centre([_leaf(20)])), Row(centre([_leaf(30)]))), width=100 * PT)
    box = layout(column)
    assert box.width == 100 * PT
    assert box.height == 2 * _HEIGHT

    rects = place(column, origin=Point(0, box.height))
    assert [rect.y for rect in rects] == [0, _HEIGHT]
    for rect in rects:
        assert abs((rect.x + rect.width // 2) - 50 * PT) <= 1


def test_a_nested_row_is_packed_at_its_natural_size_unless_it_is_given_a_width() -> None:
    # The propagation rule, asserted as the limitation it is. A row cannot know
    # how wide its children should be because its siblings consume the space, so
    # a nested row that says nothing gets its natural size -- and stating a width
    # is how you override that.
    natural = Row((_leaf(10), spacer(), _leaf(10)))
    assert layout(natural).width == 20 * PT

    outer = Row((natural, spacer()))
    assert _xs(outer, 100 * PT) == [0, 10 * PT]

    stated = Row((_leaf(10), spacer(), _leaf(10)), width=60 * PT)
    assert _xs(Row((stated, spacer())), 100 * PT) == [0, 50 * PT]


def test_a_column_inside_a_column_inherits_the_width_through_both_levels() -> None:
    inner = Column((Row(right([_leaf(10)])),))
    outer = Column((inner,), width=100 * PT)
    (rect,) = place(outer, origin=Point(0, layout(outer).height))
    assert rect.x + rect.width == 100 * PT


def test_a_column_respects_a_height_target_by_stretching_the_glue_between_rows() -> None:
    column = Column(
        (Row((_leaf(10),)), spacer(), Row((_leaf(10),))),
        height=100 * PT,
        width=50 * PT,
    )
    box = layout(column)
    assert box.height == 100 * PT

    first, second = place(column, origin=Point(0, box.height))
    assert first.y == 0
    assert second.y == 100 * PT - _HEIGHT


def test_a_columns_depth_comes_from_its_last_child_the_way_a_page_does() -> None:
    # `vpack` chains height and depth instead of summing bounding boxes, which is
    # what stops two blocks with descenders overlapping. It is the same rule that
    # gives paragraphs their vertical rhythm, applied to buttons.
    deep = Leaf(width=10 * PT, height=8 * PT, depth=4 * PT)
    column = Column((deep, deep))
    box = layout(column)
    assert box.height == 8 * PT + 4 * PT + 8 * PT
    assert box.depth == 4 * PT


# --------------------------------------------------------------------------
# The seams to the rest of the tree
# --------------------------------------------------------------------------


def test_leaves_come_back_in_the_order_place_emits_rectangles_for_them() -> None:
    column = Column(
        (
            Row((_leaf(10, "one"), spacer(), _leaf(10, "two"))),
            Row(centre([_leaf(10, "three")])),
        ),
        width=100 * PT,
    )
    found = leaves(column)
    rects = place(column, origin=Point(0, layout(column).height))

    assert [leaf.name for leaf in found] == ["one", "two", "three"]
    assert len(rects) == len(found)
    assert all(rect.width == leaf.width for rect, leaf in zip(rects, found, strict=True))


def test_a_leaf_becomes_a_rect_whose_top_is_its_height_above_the_baseline() -> None:
    # The sign convention, which is the same one everywhere else in this project:
    # `height` extends up from the baseline and `depth` down, so a rect's top is
    # `y - height` and it is `height + depth` tall.
    leaf = Leaf(width=10 * PT, height=8 * PT, depth=4 * PT)
    (rect,) = place(Row((leaf,)), origin=Point(0, 20 * PT))
    assert rect.y == 20 * PT - 8 * PT
    assert rect.height == 12 * PT


def test_a_leaf_with_no_height_draws_nothing_because_an_empty_rule_is_not_output() -> None:
    # §624 declines to output an empty rule, so a zero-area leaf occupies its
    # width and produces no rectangle. Worth pinning so it reads as the source's
    # behaviour rather than as a lost block.
    row = Row((Leaf(width=10 * PT, height=0), _leaf(10)))
    rects = place(row)
    assert len(rects) == 1
    assert rects[0].x == 10 * PT


def test_a_row_reports_the_same_width_through_layout_and_through_its_rects() -> None:
    # `layout` and `place` must not be two implementations. They are not -- the
    # second calls the first -- and this is what would notice if somebody made
    # them two.
    row = Row((_leaf(10), gap(5 * PT), _leaf(10), spacer(), _leaf(10)))
    width = 200 * PT
    box = layout(row, width=width)
    rects = place(row, width=width)

    assert box.width == width
    assert rects[-1].x + rects[-1].width == width


def test_an_empty_row_and_an_empty_column_are_boxes_of_no_size() -> None:
    assert layout(Row(())).width == 0
    assert layout(Column(())).height == 0
    assert place(Row(())) == []


def test_a_layout_with_only_spacers_packs_without_a_leaf_to_hang_on() -> None:
    # A row of pure glue is a legitimate spacer strip, and it must not need a
    # leaf to be well defined. `hpack` judges it INFINITE_GLUE rather than
    # underfull, because glue at an infinite order always reaches the target.
    result = measure(Row((spacer(), spacer())), width=100 * PT)
    assert result.fitness is PackFitness.INFINITE_GLUE
    assert result.box.width == 100 * PT
    assert place(Row((spacer(), spacer())), width=100 * PT) == []

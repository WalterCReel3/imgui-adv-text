r"""
`advtext.columns`: does the splitter cut where TeX cuts, and does it lose anything?

Two fixtures, and the split between them is the point.

**A synthetic stack of lines with known heights.** Every breakpoint's height is
an exact multiple of a 14 pt baseline, so "cut after the fifth line" is an index
this file can compute rather than a number it has to read off the implementation.
It is built through `advtext.pack.append_to_vlist`, so the glue between the lines
is real §679 interline glue and not a hand-written stand-in -- and the lines are
8 pt over 2 pt against a 14 pt `\baselineskip`, which leaves **4 pt of interline
glue between every pair**. That number is load-bearing twice over, and `INTERLINE`
says why at length:

- It must not be zero, or the hazard this module exists to handle -- leftover
  interline glue at the top of a column -- is invisible to every test here. A
  composed document from `advtext.ui` has **zero-width** interline glue between
  body lines, because `advtext.style`'s strut makes height plus depth equal
  `\baselineskip` exactly, so splitting the real document would have been the
  weaker fixture rather than the stronger one.
- It must not equal the `\splittopskip` head gap either, and at the 12 pt
  baseline this file was first written with it did. Both came to 2 pt, so the
  head a correct splitter produces and the head a splitter that discarded
  nothing would produce were the same number, and the discard test was green for
  both. The meta-test pins both conditions.

**`demo/sample.md`, composed for real.** Heterogeneous material -- headings,
kerns between blocks, a rule, a table, a barred block quote -- which is where
conservation has something to say. The measure comes from a fake font with round
numbers, as in `tests/test_compose.py`, because what is being tested is which
nodes end up in which column and not how wide a glyph is.

The load-bearing assertion in this file is **conservation**: concatenate the
columns and you get the single-column sequence of boxes and rules back, by
object identity, with nothing dropped and nothing repeated. It is stated over
boxes and rules rather than over every node on purpose, because discarding glue
at the cut is the *correct* behaviour and an assertion over all nodes would
forbid it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from advtext.columns import (
    AWFUL_BAD,
    DEPLORABLE,
    SPLIT_TOP_SKIP,
    ColumnSplit,
    compose_into_columns,
    prune_top,
    split_into_columns,
    vert_break,
    vsplit,
)
from advtext.fontmetrics import Face, FontMetrics, GlyphBBox
from advtext.markdown import build_document
from advtext.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    BoxKind,
    CharNode,
    FontKey,
    Glue,
    GlueSpec,
    Kern,
    KernKind,
    Node,
    Penalty,
    Rule,
    permits_break_at_following_glue,
)
from advtext.pack import IGNORE_DEPTH, InterlineSkip, PackFitness, append_to_vlist
from advtext.style import Theme, char_measure, parse_font_key
from advtext.ui import compose_blocks
from advtext.units import GlueOrder, sp_from_pt, sp_from_px

# -- the synthetic stack -------------------------------------------------

BASELINE = sp_from_pt(14.0)
LINE_HEIGHT = sp_from_pt(8.0)
LINE_DEPTH = sp_from_pt(2.0)
INTERLINE = BASELINE - LINE_DEPTH - LINE_HEIGHT
"""
The gap §679 puts between two of these lines: 14 - 2 - 8 = 4 pt.

Named because several tests below assert against it, one asserts it is nonzero,
and one asserts it differs from the `\\splittopskip` gap.

**The 14 pt `\\baselineskip` is not a round number by accident.** At 12 pt the
interline glue comes to 2 pt and the head gap `\\splittopskip - height` comes to
10 - 8 = 2 pt as well, so the correct head of column two and the head a splitter
that discarded nothing would produce are *the same number* and the discard test
below is vacuous. That is not a hypothetical -- it is what this file did on its
first run, and the assertion that caught it (`head_gap != INTERLINE`) is still
there.
"""
HEAD_GAP = max(0, SPLIT_TOP_SKIP.width - LINE_HEIGHT)
"""
What §969 puts above the first line of a column of these: 10 - 8 = 2 pt.
"""

SKIP = InterlineSkip(
    baselineskip=GlueSpec(width=BASELINE),
    lineskip=GlueSpec(width=sp_from_pt(1.0)),
    lineskiplimit=0,
)


def stack(count: int) -> tuple[list[Node], list[Box]]:
    """
    `count` uniform lines with real interline glue, and the boxes on their own.

    Each box gets a distinct width so a failure prints something a reader can
    locate. The tests compare by identity, not by value, so two boxes that
    happened to be equal would not hide a duplicated one.
    """
    vlist: list[Node] = []
    boxes: list[Box] = []
    prev_depth = IGNORE_DEPTH
    for index in range(count):
        box = Box(
            kind=BoxKind.HLIST,
            width=sp_from_pt(100.0 + index),
            height=LINE_HEIGHT,
            depth=LINE_DEPTH,
        )
        boxes.append(box)
        prev_depth = append_to_vlist(vlist, box, prev_depth, SKIP)
    return vlist, boxes


def height_of(lines: int) -> int:
    """
    The natural height of a fragment of `lines` of the synthetic stack.

    The first line contributes its height, every later one a full baseline. The
    last line's *depth* is not in it, because `vpack` reports depth separately
    and `vert_break` measures the same way.
    """
    return LINE_HEIGHT + (lines - 1) * BASELINE


def column_for(lines: int) -> int:
    """
    The column height that holds exactly `lines` of the synthetic stack.

    `height_of` plus the `\\splittopskip` glue that `split_into_columns` puts
    above the first line of every column, including the first. Forgetting that
    term is the reason a column asked for four lines held three.
    """
    return HEAD_GAP + height_of(lines)


def glue_index_after(lines: int) -> int:
    """
    Where in the synthetic stack the glue following line `lines` sits.

    The list runs box, glue, box, glue, ... so line *k* is at `2(k-1)` and the
    glue after it at `2k - 1`.
    """
    return 2 * lines - 1


def boxes_and_rules(nodes: Sequence[Node]) -> list[Box | Rule]:
    """
    Just the material that carries ink, in order.
    """
    return [node for node in nodes if isinstance(node, Box | Rule)]


def carried(split: ColumnSplit) -> list[Box | Rule]:
    """
    Every box and rule the split accounted for: the columns, then the overflow.
    """
    material: list[Box | Rule] = []
    for column in split.columns:
        material.extend(boxes_and_rules(column.contents))
    material.extend(boxes_and_rules(split.overflow))
    return material


def head_gap(column: Box) -> int:
    """
    How far the top of a column's first line sits below the top of the column.
    """
    if not column.contents:
        return 0
    first = column.contents[0]
    return first.spec.width if isinstance(first, Glue) else 0


def first_baseline(column: Box) -> int:
    """
    How far a column's first baseline sits below the top of the column.
    """
    ink = boxes_and_rules(column.contents)
    return head_gap(column) + (ink[0].height if ink else 0)


# -- the meta-test the fixture needs -------------------------------------


def test_the_synthetic_stack_really_does_carry_nonzero_interline_glue() -> None:
    """
    Without this the discard tests below would pass for a splitter that discards nothing.

    `docs/status.md` section 5: attack the fixture, not the assertion. A composed
    document's body lines sit on a strut that fills `\\baselineskip` exactly, so
    the glue between them is zero wide and "the glue at the cut was discarded" is
    unfalsifiable against real prose. This fixture is deliberately built so it is
    not.
    """
    vlist, boxes = stack(4)
    assert INTERLINE == sp_from_pt(4.0) != 0
    # And distinct from the head gap, or "the glue at the cut was discarded and
    # replaced" would be indistinguishable from "it was left alone".
    assert INTERLINE != HEAD_GAP
    assert (
        vlist
        == [boxes[0], Glue(GlueSpec(width=INTERLINE))]
        + [node for box in boxes[1:] for node in (box, Glue(GlueSpec(width=INTERLINE)))][:-1]
    )


# -- vert_break: where the cut goes --------------------------------------


def test_the_cut_goes_after_the_last_line_that_still_fits() -> None:
    vlist, _ = stack(20)
    assert vert_break(vlist, height_of(5)) == glue_index_after(5)


def test_one_scaled_point_less_room_costs_the_column_a_whole_line() -> None:
    """
    The discriminating control for the test above.

    An off-by-one splitter that rounded, or that compared against the height
    including the last line's depth, would give the same answer for both goals.
    """
    vlist, _ = stack(20)
    assert vert_break(vlist, height_of(5) - 1) == glue_index_after(4)
    assert vert_break(vlist, height_of(5) + 1) == glue_index_after(5)


def test_a_list_that_fits_entirely_is_not_cut_at_all() -> None:
    vlist, _ = stack(6)
    assert vert_break(vlist, height_of(6)) == len(vlist)
    assert vert_break(vlist, height_of(600)) == len(vlist)


def test_an_initial_glue_node_is_never_the_cut(tmp_path: Path) -> None:
    r"""
    §970: "an initial glue node is not a legal breakpoint".

    A list whose first node is a tall glue has no legal breakpoint anywhere, so
    it comes back whole however far past the goal it runs -- rather than being
    cut at index zero into an empty column, which is what a splitter that tested
    only "is this glue" would do.
    """
    tall = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    leading = Glue(GlueSpec(width=sp_from_pt(100.0)))
    assert vert_break([leading, tall], sp_from_pt(1.0)) == 2

    # The paired control: the same glue, one box later, is a breakpoint.
    assert vert_break([tall, leading, tall], sp_from_pt(1.0)) == 1


def test_an_explicit_kern_before_glue_is_a_cut_in_a_vertical_list() -> None:
    r"""
    §973 admits **any** kern followed by glue; §868's horizontal rule admits only
    a non-explicit one, and refuses a break at the kern itself entirely.

    So this is the case where reusing `advtext.nodes.permits_break_at_following_glue`
    -- the obvious thing to reach for -- gives the wrong answer. It returns
    `False` for an explicit kern, and the glue that follows the kern is not a
    breakpoint either, because its predecessor is the kern and a kern is not
    `precedes_break`. Under the wrong predicate this list has no legal break at
    all and comes back whole; under §973 it is cut at the kern.

    `advtext.ui` emits exactly this shape: `_stacked` puts an explicit-width
    `Kern` between two blocks, and interline glue follows it.
    """
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    gap = Kern(width=sp_from_pt(100.0), kind=KernKind.EXPLICIT)
    vlist: list[Node] = [line, gap, Glue(GlueSpec()), line]

    assert vert_break(vlist, LINE_HEIGHT) == 1

    # The paired control: the very same kern, with no glue after it, is not a
    # breakpoint -- so the test above is about the rule and not about kerns.
    assert vert_break([line, gap, line], LINE_HEIGHT) == 3


def test_a_forced_penalty_cuts_the_column_short_of_what_would_fit() -> None:
    """
    §974: `pi <= eject_penalty` wins outright and stops the scan.

    The goal leaves room for all twenty lines, so a splitter that only counts
    heights takes the whole list. The forced break is three lines in.
    """
    vlist, _ = stack(20)
    forced = vlist[: glue_index_after(3)] + [Penalty(EJECT_PENALTY)] + vlist[glue_index_after(3) :]

    assert vert_break(forced, height_of(100)) == glue_index_after(3)

    # The control: the same list with an ordinary penalty there is not cut.
    ordinary = vlist[: glue_index_after(3)] + [Penalty(0)] + vlist[glue_index_after(3) :]
    assert vert_break(ordinary, height_of(100)) == len(ordinary)


def test_an_infinite_penalty_forbids_the_only_cut_the_list_has() -> None:
    """
    §974 skips a node whose penalty is `inf_penalty` or more before it is ever costed.

    The penalty sits where the column would fit exactly, and the glue after it is
    not a breakpoint because its predecessor is a penalty. So forbidding it
    leaves the list with nowhere to break, which is the visible difference.
    """
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    forbidden: list[Node] = [line, Penalty(INF_PENALTY), Glue(GlueSpec()), line]
    permitted: list[Node] = [line, Penalty(0), Glue(GlueSpec()), line]

    assert vert_break(forbidden, LINE_HEIGHT) == 4
    assert vert_break(permitted, LINE_HEIGHT) == 1


def test_a_forced_break_is_taken_even_where_the_column_is_hopelessly_underfull() -> None:
    """
    §974's `if pi <= eject_penalty then b := pi`, which is not the `b + pi` beside it.

    This clause is nearly unobservable and it took an ablation to find that out,
    so the shape of the list is worth explaining rather than apologising for.
    `b := pi` and `b := b + pi` agree whenever `b` is finite -- both come out
    around -10000 and both beat every non-forced break -- so they can only
    disagree where the forced break's own badness is already **infinite**, which
    `b := b + pi` turns into `deplorable` (100000) and `b := pi` turns into
    -10000. For that to change the answer the scan must have found a *cheaper*
    break earlier, and badness only grows as a column empties, so the height has
    to come back down in between. A negative vertical kern is how it does --
    ordinary TeX, and the only shape in which the clause has a consequence.

    Here: the break at index 3 costs nothing (0.1 pt short against 1 pt of
    stretch), the kern then drops 10 pt off the running height, and the forced
    penalty sits 10.1 pt short of the goal, which against 1 pt of stretch is
    infinitely bad. §974 takes it anyway. `b := b + pi` scores it 100000, keeps
    the earlier break and ignores the `\\eject`.
    """
    tall = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(19.9), depth=0)
    empty = Box(kind=BoxKind.HLIST, width=0, height=0, depth=0)
    vlist: list[Node] = [
        tall,
        Glue(GlueSpec(width=0, stretch=sp_from_pt(1.0))),
        empty,
        Glue(GlueSpec()),
        Kern(width=-sp_from_pt(10.0)),
        Penalty(EJECT_PENALTY),
        tall,
    ]

    assert vert_break(vlist, sp_from_pt(20.0)) == 5

    # The control, which is what makes the index above mean something: with an
    # ordinary penalty there instead, the cheap break at index 3 does win.
    ordinary = list(vlist)
    ordinary[5] = Penalty(0)
    assert vert_break(ordinary, sp_from_pt(20.0)) == 3


def test_infinite_vertical_stretch_makes_every_underfull_break_equally_good() -> None:
    """
    §975: any nonzero `active_height[3..5]` and the badness of an underfull column is 0.

    Nothing `advtext.ui` composes contains vertical `fil` -- `advtext.style`
    builds interline glue and block spacing rigid -- so this guards a
    transcription rather than a live path, and it is here because an ablation
    found it was the one clause in the module no test could see.

    Same shape as the forced-break test above and for the same reason: with
    `<=` breaking ties toward the later candidate, both readings pick the last
    break unless the height comes back down in between. It does, at the kern.
    After it the column is 10 pt short; §975 charges nothing for that because a
    `fil` is present, and the later break wins. Without the clause the 10 pt
    shortfall against 1 pt of finite stretch is infinitely bad, scores
    `deplorable`, and the earlier break keeps the column.
    """
    tall = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(19.9), depth=0)
    empty = Box(kind=BoxKind.HLIST, width=0, height=0, depth=0)
    vlist: list[Node] = [
        tall,
        Glue(GlueSpec(width=0, stretch=sp_from_pt(1.0))),
        empty,
        Glue(GlueSpec(width=0, stretch=sp_from_pt(1.0), stretch_order=GlueOrder.FIL)),
        empty,
        Glue(GlueSpec()),
        Kern(width=-sp_from_pt(10.0)),
        Penalty(0),
        tall,
    ]

    assert vert_break(vlist, sp_from_pt(20.0)) == 7

    # The control: the same list with that one glue finite instead of infinite.
    finite = list(vlist)
    finite[3] = Glue(GlueSpec(width=0, stretch=sp_from_pt(1.0)))
    assert vert_break(finite, sp_from_pt(20.0)) == 5


def test_splitmaxdepth_charges_a_deep_line_for_the_depth_it_cannot_keep() -> None:
    """
    §972's `not_found` clamp: depth past `\\splitmaxdepth` becomes height.

    Three lines 8 pt over 20 pt deep. Unclamped, two of them fit in 40 pt because
    only the *last* line's depth hangs below the box. Clamped to 4 pt, each
    line's extra 16 pt is charged to the running height instead and only one
    fits. A splitter that dropped the clamp would put two lines in a column that
    `vpack` then packs 16 pt too tall.
    """
    deep = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(8.0), depth=sp_from_pt(20.0))
    last = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(8.0), depth=0)
    vlist: list[Node] = [deep, Glue(GlueSpec()), deep, Glue(GlueSpec()), last]

    assert vert_break(vlist, sp_from_pt(40.0)) == 3
    assert vert_break(vlist, sp_from_pt(40.0), sp_from_pt(4.0)) == 1


def test_glue_after_a_font_kern_is_a_breakpoint_horizontally_and_not_vertically() -> None:
    """
    §973's glue rule is `precedes_break(prev_p)`; §868's has a third branch it does not.

    `advtext.nodes.permits_break_at_following_glue` implements §868 and returns
    `True` for a non-explicit kern before glue. §973 returns `False` -- the break
    a kern offers in a vertical list is *at the kern*, taken one node earlier.

    The two therefore disagree only on which side of a zero-width kern the cut
    falls, because §974 breaks ties toward the later candidate and any kern with
    width of its own pushes the glue past the goal where it loses anyway. That is
    a small consequence and this test says so rather than dressing it up; what it
    protects is the predicate, and the predicate is what a future reader will be
    tempted to replace with the one that is already written.
    """
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=0)
    font_kern = Kern(width=0, kind=KernKind.NORMAL)
    vlist: list[Node] = [line, font_kern, Glue(GlueSpec()), line]

    # The kern, not the glue after it.
    assert vert_break(vlist, LINE_HEIGHT) == 1
    # And the §868 predicate really would have said otherwise about that glue.
    assert permits_break_at_following_glue(font_kern)


def test_a_character_in_a_vertical_list_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="vertbreak"):
        vert_break([CharNode(font="x-16", codepoint=0x41)], sp_from_pt(10.0))


def test_the_two_cost_sentinels_keep_the_ordering_the_source_relies_on() -> None:
    """
    §974: deplorable is "more than inf_bad, but less than awful_bad".

    A hopeless break must still beat an impossible one, or a list with no good
    break in it runs off the bottom of the column instead of being cut.
    """
    assert DEPLORABLE > INF_PENALTY
    assert DEPLORABLE < AWFUL_BAD


# -- prune_top: the head of the next column ------------------------------


def test_prune_top_drops_the_discardables_and_sizes_splittopskip_from_the_first_line() -> None:
    tall = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(4.0), depth=0)
    fragment: list[Node] = [
        Glue(GlueSpec(width=sp_from_pt(7.0))),
        Kern(width=sp_from_pt(3.0)),
        Penalty(150),
        tall,
        Glue(GlueSpec(width=sp_from_pt(9.0))),
    ]

    pruned = prune_top(fragment, GlueSpec(width=sp_from_pt(10.0)))

    # 10pt of \splittopskip less the 4pt line that follows it: the baseline
    # lands at 10pt, which is the whole point of the parameter.
    assert pruned == [Glue(GlueSpec(width=sp_from_pt(6.0))), tall, fragment[-1]]


def test_splittopskip_is_floored_at_zero_rather_than_pulling_a_tall_line_upward() -> None:
    tall = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(40.0), depth=0)
    pruned = prune_top(
        [Glue(GlueSpec(width=sp_from_pt(7.0))), tall], GlueSpec(width=sp_from_pt(10.0))
    )
    assert pruned == [Glue(GlueSpec(width=0)), tall]


def test_a_fragment_of_nothing_but_discardables_prunes_to_nothing() -> None:
    assert prune_top([Glue(GlueSpec(width=sp_from_pt(7.0))), Penalty(3)]) == []
    assert prune_top([]) == []


# -- the discard at the cut, which is what a naive splitter gets wrong ----


def test_the_interline_glue_at_the_cut_does_not_reappear_at_the_top_of_column_two() -> None:
    """
    The case where naive and correct disagree, stated as a number.

    A splitter that cut the list and used the tail as-is would put the 2 pt
    interline glue that separated line 5 from line 6 at the head of column 2,
    and column 2's text would start 2 pt lower than column 1's. What is there
    instead is `\\splittopskip` glue sized from the line that follows it.
    """
    vlist, boxes = stack(20)

    # The fixture check that makes the assertion mean something: the node at the
    # cut really is a 2pt glue, so keeping it would be visible.
    cut = vert_break(vlist, height_of(5))
    assert vlist[cut] == Glue(GlueSpec(width=INTERLINE))

    split = split_into_columns(vlist, height=column_for(5), count=2)
    second = split.columns[1]

    assert head_gap(second) == HEAD_GAP
    assert head_gap(second) != INTERLINE
    assert boxes_and_rules(second.contents)[0] is boxes[5]


def test_every_column_of_uniform_lines_starts_at_the_same_first_baseline() -> None:
    """
    The `\\splittopskip` hazard, stated the way a screenshot would catch it.

    Column 1's head comes from §1001's `\\topskip` and columns 2 and 3's from
    §969's `\\splittopskip`; they are the same computation, so with uniform lines
    the three agree exactly. Dropping either one makes this red.
    """
    vlist, _ = stack(30)
    split = split_into_columns(vlist, height=column_for(6), count=3)

    baselines = {first_baseline(column) for column in split.columns}
    assert baselines == {SPLIT_TOP_SKIP.width}


# -- conservation --------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 3, 4, 7])
def test_the_columns_concatenate_back_into_the_single_column_reading_order(count: int) -> None:
    """
    The load-bearing property: nothing dropped, nothing duplicated, order kept.

    By identity rather than equality, because the synthetic stack's lines differ
    only in width and an equality comparison would accept a column that repeated
    one line in place of another of the same size.
    """
    vlist, boxes = stack(23)
    split = split_into_columns(vlist, height=column_for(4), count=count)
    got = carried(split)

    assert len(got) == len(boxes)
    assert all(a is b for a, b in zip(got, boxes, strict=True))


def test_a_column_holds_a_contiguous_run_rather_than_a_scattering() -> None:
    """
    Conservation alone would be satisfied by a splitter that interleaved columns.

    Text has to continue from the foot of one column to the head of the next, so
    each column's boxes must be a contiguous slice of the original in order --
    this is the assertion that says the columns are *columns* and not two
    alternating halves of the document.
    """
    vlist, boxes = stack(23)
    split = split_into_columns(vlist, height=column_for(4), count=3)

    start = 0
    for column in split.columns:
        ink = boxes_and_rules(column.contents)
        assert ink == boxes[start : start + len(ink)]
        assert all(a is b for a, b in zip(ink, boxes[start:], strict=False))
        start += len(ink)
    assert boxes_and_rules(split.overflow) == boxes[start:]


def test_material_that_does_not_fit_comes_back_as_overflow_rather_than_disappearing() -> None:
    vlist, boxes = stack(23)
    split = split_into_columns(vlist, height=column_for(4), count=2)

    assert not split.fits
    assert len(boxes_and_rules(split.overflow)) == len(boxes) - 8
    assert carried(split) == boxes


def test_more_columns_than_material_come_back_empty_and_still_the_right_height() -> None:
    vlist, boxes = stack(3)
    split = split_into_columns(vlist, height=column_for(10), count=4)

    assert split.fits
    assert len(split.columns) == 4
    assert boxes_and_rules(split.columns[0].contents) == boxes
    assert all(column.contents == () for column in split.columns[1:])
    assert {column.height for column in split.columns} == {column_for(10)}


def test_every_column_is_packed_exactly_to_the_column_height() -> None:
    vlist, _ = stack(23)
    split = split_into_columns(vlist, height=column_for(4), count=3)
    assert {column.height for column in split.columns} == {column_for(4)}


def test_a_line_taller_than_the_column_overflows_the_column_rather_than_being_dropped() -> None:
    """
    §977 packs `exactly`, so an unbreakable box taller than the goal sticks out.

    Reported rather than silently truncated: `PackResult.overfull_by` is the
    number, and the box is still in the column.
    """
    giant = Box(kind=BoxKind.HLIST, width=0, height=sp_from_pt(80.0), depth=0)
    split = split_into_columns([giant], height=sp_from_pt(30.0), count=1)

    assert split.results[0].fitness is PackFitness.UNDERFULL or split.fits
    assert boxes_and_rules(split.columns[0].contents) == [giant]
    assert split.results[0].natural == sp_from_pt(80.0)


def test_a_rule_survives_the_split_and_is_counted_where_it_sits() -> None:
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    rule = Rule(width=sp_from_pt(100.0), height=sp_from_pt(1.0), depth=0)
    vlist: list[Node] = [line, Glue(GlueSpec(width=INTERLINE)), rule, Glue(GlueSpec()), line]

    split = split_into_columns(vlist, height=column_for(1), count=3)
    assert carried(split) == [line, rule, line]


def test_a_running_rule_dimension_is_refused_rather_than_measured_as_minus_16384pt() -> None:
    with pytest.raises(ValueError, match="running"):
        vert_break([Rule(width=sp_from_pt(10.0))], sp_from_pt(10.0))


# -- the arguments ------------------------------------------------------


@pytest.mark.parametrize("count", [0, -1])
def test_a_column_count_below_one_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="column count"):
        split_into_columns(stack(3)[0], height=column_for(2), count=count)


@pytest.mark.parametrize("height", [0, -sp_from_pt(1.0)])
def test_a_column_height_that_is_not_positive_is_refused(height: int) -> None:
    with pytest.raises(ValueError, match="column height"):
        split_into_columns(stack(3)[0], height=height, count=2)


def test_material_that_opens_with_a_penalty_makes_progress_instead_of_spinning() -> None:
    """
    `vert_break` can return zero -- a penalty at index zero is a legal break.

    `prune_top` is what stops that from being an infinite loop: it removes every
    leading discardable, so a column that consumed nothing still shortens the
    remainder. Two columns and a finite return is the assertion.
    """
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    split = split_into_columns([Penalty(EJECT_PENALTY), line], height=column_for(1), count=2)
    assert carried(split) == [line]


def test_vsplit_leaves_its_own_input_head_alone() -> None:  # §977 does not prune the box it splits
    """
    `vsplit` is §977 exactly; the `\\topskip` on the first column is
    `split_into_columns`'s addition and is cited as §1001 there rather than
    smuggled into this routine.
    """
    line = Box(kind=BoxKind.HLIST, width=0, height=LINE_HEIGHT, depth=LINE_DEPTH)
    lead = Glue(GlueSpec(width=sp_from_pt(5.0)))
    column, rest = vsplit([lead, line], sp_from_pt(100.0))
    assert column.box.contents == (lead, line)
    assert rest == []


# -- a real document -----------------------------------------------------

GLYPH = sp_from_px(10.0)
SPACE = sp_from_px(8.0)
MEASURE = sp_from_px(340.0)
SAMPLE = Path(__file__).resolve().parent.parent / "demo" / "sample.md"


@dataclass(frozen=True, slots=True)
class FakeMetrics:
    """
    Round numbers and no font behind them, as in `tests/test_compose.py`.

    Which column a box lands in does not depend on how wide a glyph is, so a real
    font here would only make the suite depend on a font directory.
    """

    face: Face
    size: float

    @property
    def ascent(self) -> float:
        return 0.8 * GLYPH

    @property
    def descent(self) -> float:
        return 0.2 * GLYPH

    @property
    def x_height(self) -> float:
        return 0.5 * GLYPH

    @property
    def em(self) -> float:
        return self.size

    @property
    def space_width(self) -> float:
        return float(SPACE)

    def has(self, codepoint: int) -> bool:
        return True

    def advance(self, codepoint: int) -> float:
        return float(SPACE if codepoint == 0x20 else GLYPH)

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(0.0, -0.2 * GLYPH, 0.9 * GLYPH, 0.7 * GLYPH)

    def kern(self, codepoint: int, following: int) -> float:
        return 0.0


def fake_resolve(key: FontKey) -> FontMetrics:
    spec = parse_font_key(key)
    return FakeMetrics(face=spec.face, size=float(spec.size))


@pytest.fixture
def sample_material() -> tuple[Theme, tuple[Node, ...]]:
    """
    `demo/sample.md` as a single-column vertical list: the sequence to conserve.
    """
    theme = Theme.build()
    document = build_document(SAMPLE.read_text(encoding="utf-8"), theme, fake_resolve)
    box = compose_blocks(document.blocks, theme, MEASURE, char_measure(fake_resolve))
    return theme, box.contents


def test_the_sample_document_is_heterogeneous_enough_for_the_test_below_to_mean_something(
    sample_material: tuple[Theme, tuple[Node, ...]],
) -> None:
    """
    Conservation over a list of uniform boxes would be a weaker claim.

    The sample has kerns between blocks and more than a page of lines at this
    measure, which is what makes the split cross block boundaries.
    """
    _, material = sample_material
    assert any(isinstance(node, Kern) for node in material)
    assert len(boxes_and_rules(material)) > 40


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_a_real_document_is_conserved_across_any_column_count(
    sample_material: tuple[Theme, tuple[Node, ...]], count: int
) -> None:
    theme, material = sample_material
    expected = boxes_and_rules(material)

    split = split_into_columns(material, height=sp_from_px(700.0), count=count)
    got = carried(split)

    assert len(got) == len(expected)
    assert all(a is b for a, b in zip(got, expected, strict=True))


def test_compose_into_columns_agrees_with_composing_and_splitting_by_hand() -> None:
    """
    The convenience is the two halves and nothing else -- no second layout pass.
    """
    theme = Theme.build()
    measure = char_measure(fake_resolve)
    document = build_document(SAMPLE.read_text(encoding="utf-8"), theme, fake_resolve)
    material = compose_blocks(document.blocks, theme, MEASURE, measure).contents

    by_hand = split_into_columns(material, height=sp_from_px(700.0), count=3)
    end_to_end = compose_into_columns(
        document.blocks,
        theme,
        measure,
        column_width=MEASURE,
        column_height=sp_from_px(700.0),
        count=3,
    )

    assert end_to_end.columns == by_hand.columns
    assert end_to_end.overflow == by_hand.overflow


def test_narrowing_the_measure_for_more_columns_puts_fewer_lines_in_each() -> None:
    """
    The demo's actual gesture: the same page split two ways.

    Three columns of a third of the width hold more lines in total than two of a
    half, because the text is broken to a narrower measure -- so this is a check
    that the column count is reaching the line breaker and not only the splitter.
    """
    theme = Theme.build()
    measure = char_measure(fake_resolve)
    document = build_document(SAMPLE.read_text(encoding="utf-8"), theme, fake_resolve)
    page = sp_from_px(1000.0)

    counts = {}
    for count in (2, 3):
        split = compose_into_columns(
            document.blocks,
            theme,
            measure,
            column_width=page // count,
            column_height=sp_from_px(700.0),
            count=count,
        )
        counts[count] = len(boxes_and_rules(split.columns[0].contents))

    assert counts[3] > counts[2] >= 1

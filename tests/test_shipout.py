r"""
Claims about ship-out, built on hand-made boxes so every position is computable.

Nothing here opens a font. `_measure` gives every character a round advance, so
an expected x is a sum a reader can do in their head, and a test that fails names
a number rather than a discrepancy. That is the point of `hpack` and `ship` both
taking an injected `CharMeasure`: the arithmetic is checkable because the inputs
were chosen.

The load-bearing test in this file is
`test_the_set_glue_accumulates_so_the_last_glyph_lands_exactly_on_the_right_margin`,
together with `test_glue_is_rounded_by_the_pascal_rule_at_an_exact_half`. Between
them they are the entire justification for §625's accumulate-multiply-round-
difference dance, which looks like something to simplify until you see what
simplifying it costs. Both fail under the obvious implementation -- round each
glue node's share independently, with Python's `round` -- and the first fails by
a whole scaled point on the right margin of every justified line.

The sign conventions get their own tests for the same reason they get their own
paragraph in `advtext.nodes`: height and depth are measured from the baseline,
`shift_amount` is positive downward in an hlist and rightward in a vlist, and
each of those is a one-character change that produces plausible output.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from advtext.nodes import (
    Box,
    BoxKind,
    CharNode,
    Disc,
    Glue,
    GlueSpec,
    Kern,
    KernKind,
    MathOff,
    MathOn,
    Node,
    Penalty,
    Rule,
)
from advtext.pack import (
    CharDimens,
    InterlineSkip,
    PackMode,
    append_to_vlist,
    hpack,
    vpack,
)
from advtext.shipout import (
    DrawCmd,
    Glyph,
    Line,
    Point,
    RuleRect,
    SetGlue,
    pascal_round,
    ship,
)
from advtext.units import RUNNING, GlueOrder, Scaled, sp_from_pt

PT = sp_from_pt(1.0)

# Every character is this wide, so an expected x is a count of characters.
_ADVANCE: Scaled = 10 * PT
_ASCENT: Scaled = 7 * PT
_DESCENT: Scaled = 2 * PT

FONT = "prose@786432"


def _measure(node: CharNode) -> CharDimens:
    """
    A fake metrics lookup with round numbers, so positions are arithmetic.
    """
    return CharDimens(width=_ADVANCE, height=_ASCENT, depth=_DESCENT)


# Every character is the same width here too, because the horizontal arithmetic
# is what most of this file checks -- but the *ink* differs per codepoint, which
# is the only way to tell a line's own height from the extent of the glyphs on
# it. `_measure` above cannot: under it `acem` and `gjpqy` are the same shape.
_INK_X_HEIGHT: Scaled = 4 * PT
_INK_ASCENDER: Scaled = 7 * PT
_INK_DESCENDER: Scaled = 2 * PT

_DESCENDS = frozenset("gjpqy")
_REACHES_UP = frozenset("bdfhijklt")


def _ink_measure(node: CharNode) -> CharDimens:
    """
    Height and depth per codepoint, so an ink extent is visible as a number.
    """
    character = chr(node.codepoint)
    return CharDimens(
        width=_ADVANCE,
        height=_INK_ASCENDER if character in _REACHES_UP else _INK_X_HEIGHT,
        depth=_INK_DESCENDER if character in _DESCENDS else 0,
    )


def _chars(text: str, font: str = FONT) -> list[Node]:
    return [CharNode(font, ord(character)) for character in text]


def _glyphs(cmds: Sequence[DrawCmd]) -> list[Glyph]:
    return [cmd for cmd in cmds if isinstance(cmd, Glyph)]


def _lines(cmds: Sequence[DrawCmd]) -> list[Line]:
    return [cmd for cmd in cmds if isinstance(cmd, Line)]


def _rules(cmds: Sequence[DrawCmd]) -> list[RuleRect]:
    return [cmd for cmd in cmds if isinstance(cmd, RuleRect)]


def _glues(cmds: Sequence[DrawCmd]) -> list[SetGlue]:
    return [cmd for cmd in cmds if isinstance(cmd, SetGlue)]


# --------------------------------------------------------------------------
# Horizontal placement
# --------------------------------------------------------------------------


def test_glyph_x_positions_in_a_natural_hbox_are_the_running_sum_of_advances() -> None:
    box = hpack(_chars("abcd"), measure=_measure).box
    glyphs = _glyphs(ship(box, measure=_measure))

    assert [glyph.codepoint for glyph in glyphs] == [ord(c) for c in "abcd"]
    assert [glyph.x for glyph in glyphs] == [0, _ADVANCE, 2 * _ADVANCE, 3 * _ADVANCE]
    assert all(glyph.y == 0 for glyph in glyphs)


def test_the_origin_is_the_boxs_reference_point_and_every_position_is_absolute() -> None:
    # The reference point is on the baseline at the left edge, so a glyph shipped
    # at origin (100pt, 50pt) sits with its baseline at y = 50pt -- not with its
    # top there. A backend that reads `y` as a top edge draws a whole ascent low.
    box = hpack(_chars("ab"), measure=_measure).box
    glyphs = _glyphs(ship(box, Point(100 * PT, 50 * PT), measure=_measure))

    assert [glyph.x for glyph in glyphs] == [100 * PT, 100 * PT + _ADVANCE]
    assert [glyph.y for glyph in glyphs] == [50 * PT, 50 * PT]


def test_kerns_and_math_nodes_move_the_pen_without_drawing_anything() -> None:
    nodes: list[Node] = [
        *_chars("a"),
        Kern(width=3 * PT, kind=KernKind.NORMAL),
        MathOn(width=PT),
        *_chars("b"),
        MathOff(width=PT),
        Penalty(50),
        Disc(),
        *_chars("c"),
    ]
    glyphs = _glyphs(ship(hpack(nodes, measure=_measure).box, measure=_measure))

    assert [glyph.x for glyph in glyphs] == [
        0,
        _ADVANCE + 4 * PT,
        2 * _ADVANCE + 5 * PT,
    ]


def test_a_character_without_a_measure_is_refused_rather_than_placed_at_zero_width() -> None:
    box = hpack(_chars("ab"), measure=_measure).box
    with pytest.raises(ValueError, match="no `measure`"):
        ship(box)


# --------------------------------------------------------------------------
# §625: the glue rounding discipline, which is the reason this module is hard
# --------------------------------------------------------------------------


def test_the_set_glue_accumulates_so_the_last_glyph_lands_exactly_on_the_right_margin() -> None:
    # Three glues, one scaled point of excess between them. Each one's own share
    # is a third of a scaled point, so rounding each independently gives every
    # one of them zero and the line comes up a whole scaled point short -- a
    # right margin that wavers, which reads as a line-breaker bug.
    #
    # §625 rounds the running total instead: 1/3 -> 0, 2/3 -> 1, 3/3 -> 1. The
    # widths are the differences 0, 1, 0, which sum to exactly the excess.
    nodes: list[Node] = [
        *_chars("a"),
        Glue(GlueSpec(width=4 * PT, stretch=PT)),
        *_chars("b"),
        Glue(GlueSpec(width=4 * PT, stretch=PT)),
        *_chars("c"),
        Glue(GlueSpec(width=4 * PT, stretch=PT)),
        *_chars("d"),
    ]
    natural = 4 * _ADVANCE + 12 * PT
    result = hpack(nodes, natural + 1, PackMode.EXACTLY, measure=_measure)
    assert result.excess == 1
    assert result.box.glue_set == pytest.approx(1 / (3 * PT))

    cmds = ship(result.box, measure=_measure)
    widths = [glue.width for glue in _glues(cmds)]
    assert widths == [4 * PT, 4 * PT + 1, 4 * PT]
    assert sum(widths) == 12 * PT + 1

    last = _glyphs(cmds)[-1]
    assert last.x + _ADVANCE == result.box.width

    # And the same claim stated as the failure it prevents: dividing the excess
    # up node by node loses it entirely.
    independent = [round(result.box.glue_set * PT) for _ in widths]
    assert independent == [0, 0, 0]


def test_glue_is_rounded_by_the_pascal_rule_at_an_exact_half() -> None:
    # `glue_set` is a ratio of integers and `cur_glue` an integer sum of scaled
    # points, so the product lands on an exact half routinely. Here the ratio is
    # 1/2 and the first glue's running total is 5, giving exactly 2.5.
    #
    # Pascal's `round` is half away from zero and gives 3; Python's ties to even
    # and gives 2. The totals agree at the end either way -- both reach 5 -- so
    # this is invisible on the right margin and visible as the *word in the
    # middle of the line* sitting one scaled point off. Correction C3.
    nodes: list[Node] = [
        *_chars("a"),
        Glue(GlueSpec(width=4 * PT, stretch=5)),
        *_chars("b"),
        Glue(GlueSpec(width=4 * PT, stretch=5)),
        *_chars("c"),
    ]
    natural = 3 * _ADVANCE + 8 * PT
    result = hpack(nodes, natural + 5, PackMode.EXACTLY, measure=_measure)
    assert result.box.glue_set == 0.5

    widths = [glue.width for glue in _glues(ship(result.box, measure=_measure))]
    assert widths == [4 * PT + 3, 4 * PT + 2]
    assert sum(widths) == 8 * PT + 5

    # Python's rounding would have split the same five scaled points 2 then 3.
    assert round(0.5 * 5) == 2
    assert pascal_round(0.5 * 5) == 3


def test_pascal_round_goes_away_from_zero_on_every_tie_including_negative_ones() -> None:
    assert pascal_round(2.5) == 3
    assert pascal_round(3.5) == 4
    assert pascal_round(-2.5) == -3
    assert pascal_round(-0.5) == -1
    assert pascal_round(0.5) == 1

    # Away from ties it is ordinary rounding, and it agrees with Python there.
    for value in (0.0, 0.4, 0.6, -0.4, -0.6, 12.3, -12.3, 1000.49):
        assert pascal_round(value) == round(value)


def test_shrinking_takes_the_glue_ratio_negatively_even_though_it_is_stored_positive() -> None:
    # §664 stores `glue_set` as a positive ratio for shrink as well as stretch
    # and puts the direction in `glue_sign` alone, so `cur_glue` has to *fall*.
    # A renderer that added instead would widen an overfull line rather than
    # squeezing it, and the text would run off the right edge with no diagnostic.
    nodes: list[Node] = [
        *_chars("a"),
        Glue(GlueSpec(width=4 * PT, shrink=2 * PT)),
        *_chars("b"),
    ]
    natural = 2 * _ADVANCE + 4 * PT
    result = hpack(nodes, natural - PT, PackMode.EXACTLY, measure=_measure)
    assert result.box.glue_set == 0.5

    (glue,) = _glues(ship(result.box, measure=_measure))
    assert glue.width == 3 * PT
    assert glue.natural == 4 * PT
    assert _glyphs(ship(result.box, measure=_measure))[-1].x == _ADVANCE + 3 * PT


def test_glue_at_an_order_the_box_was_not_set_at_renders_at_its_natural_width() -> None:
    # §646: the highest order with a nonzero coefficient is used "as if no other
    # orders were present". The fil glue absorbs the whole excess; the finite
    # glue beside it gets nothing at all, not a proportional share.
    nodes: list[Node] = [
        *_chars("a"),
        Glue(GlueSpec(width=4 * PT, stretch=2 * PT)),
        *_chars("b"),
        Glue(GlueSpec(width=0, stretch=PT, stretch_order=GlueOrder.FIL)),
    ]
    natural = 2 * _ADVANCE + 4 * PT
    result = hpack(nodes, natural + 30 * PT, PackMode.EXACTLY, measure=_measure)
    assert result.box.glue_order is GlueOrder.FIL

    finite, infinite = _glues(ship(result.box, measure=_measure))
    assert finite.width == 4 * PT
    assert infinite.width == 30 * PT


def test_glue_in_an_unset_box_renders_at_its_natural_width() -> None:
    box = hpack(
        [*_chars("a"), Glue(GlueSpec(width=4 * PT, stretch=2 * PT)), *_chars("b")],
        measure=_measure,
    ).box
    (glue,) = _glues(ship(box, measure=_measure))
    assert glue.width == glue.natural == 4 * PT


# --------------------------------------------------------------------------
# Nesting, shifting and vertical placement
# --------------------------------------------------------------------------


def test_nested_boxes_compose_their_origins() -> None:
    inner = hpack(_chars("xy"), measure=_measure).box
    outer = hpack([*_chars("a"), inner, *_chars("b")], measure=_measure).box
    glyphs = _glyphs(ship(outer, Point(5 * PT, 0), measure=_measure))

    assert [glyph.codepoint for glyph in glyphs] == [ord(c) for c in "axyb"]
    assert [glyph.x for glyph in glyphs] == [
        5 * PT,
        5 * PT + _ADVANCE,
        5 * PT + 2 * _ADVANCE,
        5 * PT + 3 * _ADVANCE,
    ]


def test_the_pen_resumes_at_the_sub_boxs_declared_width_not_where_the_recursion_stopped() -> None:
    # §621: `cur_h := edge + width(p)`. A box packed wider than its contents --
    # any justified line, and every `\hbox to` -- would otherwise leave the pen
    # short by the difference and overlap whatever follows it.
    inner = hpack(_chars("x"), 20 * PT, PackMode.ADDITIONAL, measure=_measure).box
    assert inner.width == _ADVANCE + 20 * PT

    outer = hpack([inner, *_chars("b")], measure=_measure).box
    glyphs = _glyphs(ship(outer, measure=_measure))
    assert [glyph.x for glyph in glyphs] == [0, _ADVANCE + 20 * PT]


def test_shift_amount_moves_a_box_down_in_an_hlist_because_positive_is_down() -> None:
    inner = hpack(_chars("x"), measure=_measure).box
    raised = Box(
        kind=inner.kind,
        contents=inner.contents,
        width=inner.width,
        height=inner.height,
        depth=inner.depth,
        shift_amount=3 * PT,
    )
    outer = hpack([*_chars("a"), raised], measure=_measure).box
    glyphs = _glyphs(ship(outer, measure=_measure))

    assert glyphs[0].y == 0
    assert glyphs[1].y == 3 * PT


def test_shift_amount_moves_a_box_right_in_a_vlist() -> None:
    line = hpack(_chars("x"), measure=_measure).box
    shifted = Box(
        kind=line.kind,
        contents=line.contents,
        width=line.width,
        height=line.height,
        depth=line.depth,
        shift_amount=6 * PT,
    )
    page = vpack([line, shifted]).box
    glyphs = _glyphs(ship(page, Point(0, page.height), measure=_measure))

    assert [glyph.x for glyph in glyphs] == [0, 6 * PT]


def test_a_vlist_steps_down_by_each_lines_height_then_its_depth() -> None:
    # A vbox is entered at its reference point and immediately moves up by its
    # own height to the top edge; each item then costs height + depth. Passing
    # `Point(0, page.height)` therefore puts the top edge at y = 0, which is the
    # call a document renderer makes and the one worth pinning.
    first = hpack(_chars("a"), measure=_measure).box
    second = hpack(_chars("b"), measure=_measure).box
    page = vpack([first, Glue(GlueSpec(width=5 * PT)), second]).box

    lines = _lines(ship(page, Point(0, page.height), measure=_measure))
    assert [line.y for line in lines] == [
        _ASCENT,
        _ASCENT + _DESCENT + 5 * PT + _ASCENT,
    ]
    assert page.height == 2 * _ASCENT + _DESCENT + 5 * PT
    assert page.depth == _DESCENT


def test_a_vertical_kern_and_a_vertical_glue_both_move_the_pen_down() -> None:
    first = hpack(_chars("a"), measure=_measure).box
    second = hpack(_chars("b"), measure=_measure).box
    page = vpack([first, Kern(width=9 * PT), second]).box

    lines = _lines(ship(page, Point(0, page.height), measure=_measure))
    assert lines[1].y - lines[0].y == _DESCENT + 9 * PT + _ASCENT


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def test_a_rule_in_an_hlist_is_a_rect_spanning_its_height_above_and_depth_below() -> None:
    nodes: list[Node] = [*_chars("a"), Rule(width=8 * PT, height=2 * PT, depth=PT)]
    box = hpack(nodes, measure=_measure).box
    (rect,) = _rules(ship(box, Point(0, 40 * PT), measure=_measure))

    assert rect.x == _ADVANCE
    assert rect.width == 8 * PT
    assert rect.y == 40 * PT - 2 * PT
    assert rect.height == 3 * PT


def test_a_running_rule_in_an_hlist_takes_the_enclosing_boxs_height_and_depth() -> None:
    # This is how a table cell's border, or a block quote's left bar, fills the
    # box it is in without anyone measuring the box first.
    nodes: list[Node] = [*_chars("a"), Rule(width=PT, height=RUNNING, depth=RUNNING)]
    box = hpack(nodes, measure=_measure).box
    assert box.height == _ASCENT and box.depth == _DESCENT

    (rect,) = _rules(ship(box, Point(0, 40 * PT), measure=_measure))
    assert rect.y == 40 * PT - _ASCENT
    assert rect.height == _ASCENT + _DESCENT


def test_a_running_rule_in_a_vlist_takes_the_enclosing_boxs_width() -> None:
    # The markdown thematic break: a full-column `---` that nothing had to
    # measure the column to emit.
    line = hpack(_chars("abc"), measure=_measure).box
    page = vpack([line, Rule(width=RUNNING, height=PT, depth=0)]).box
    assert page.width == 3 * _ADVANCE

    (rect,) = _rules(ship(page, Point(0, page.height), measure=_measure))
    assert rect.x == 0
    assert rect.width == 3 * _ADVANCE
    assert rect.height == PT
    assert rect.y == _ASCENT + _DESCENT


def test_a_rule_with_no_thickness_occupies_space_and_draws_nothing() -> None:
    # §624 declines to output an empty rule but still advances past it, which is
    # how `\hrule height 0pt` is a spacer rather than a no-op.
    box = hpack([Rule(width=8 * PT, height=0, depth=0), *_chars("a")], measure=_measure).box
    cmds = ship(box, measure=_measure)

    assert _rules(cmds) == []
    assert _glyphs(cmds)[0].x == 8 * PT


def test_a_rule_whose_width_is_still_running_in_an_hlist_is_refused() -> None:
    # §138's invariant. Left unchecked it is catastrophic rather than wrong: the
    # sentinel is -2^30, so the pen would jump 16384pt to the left.
    box = Box(
        kind=BoxKind.HLIST,
        contents=(Rule(width=RUNNING, height=PT, depth=0),),
        width=PT,
        height=PT,
    )
    with pytest.raises(ValueError, match="never running inside an hlist"):
        ship(box)


def test_a_character_in_a_vertical_list_is_refused() -> None:
    box = Box(kind=BoxKind.VLIST, contents=(CharNode(FONT, ord("a")),))
    with pytest.raises(ValueError, match="cannot appear in a vertical list"):
        ship(box, measure=_measure)


# --------------------------------------------------------------------------
# Reading order: the contract with advtext.selection
# --------------------------------------------------------------------------


def test_reading_order_indices_are_dense_and_strictly_increasing_across_a_nested_tree() -> None:
    first = hpack(
        [*_chars("ab"), Glue(GlueSpec(width=4 * PT)), *_chars("cd")], measure=_measure
    ).box
    nested = hpack([*_chars("ef")], measure=_measure).box
    second = hpack([*_chars("g"), nested, *_chars("h")], measure=_measure).box
    page = vpack([first, Glue(GlueSpec(width=5 * PT)), second]).box

    cmds = ship(page, Point(0, page.height), measure=_measure)
    indexed = [cmd for cmd in cmds if isinstance(cmd, (Glyph, SetGlue))]

    assert [cmd.index for cmd in indexed] == list(range(len(indexed)))
    # The interword glue takes an index of its own, and the nested box's material
    # sits in reading order *between* the glyphs either side of it rather than
    # after them -- which is the property a range selection depends on and the
    # one a depth-last traversal would break.
    assert [chr(cmd.codepoint) if isinstance(cmd, Glyph) else " " for cmd in indexed] == list(
        "ab cdgefh"
    )


def test_vertical_glue_takes_no_index_because_it_is_not_a_character() -> None:
    line = hpack(_chars("a"), measure=_measure).box
    page = vpack([line, Glue(GlueSpec(width=5 * PT)), line]).box

    cmds = ship(page, Point(0, page.height), measure=_measure)
    assert _glues(cmds) == []
    assert [cmd.index for cmd in _glyphs(cmds)] == [0, 1]


def test_each_line_command_brackets_exactly_the_material_on_that_line() -> None:
    first = hpack([*_chars("ab"), Glue(GlueSpec(width=4 * PT)), *_chars("c")], measure=_measure).box
    second = hpack(_chars("de"), measure=_measure).box
    page = vpack([first, second]).box

    cmds = ship(page, Point(0, page.height), measure=_measure)
    lines = _lines(cmds)

    assert [(line.start, line.end) for line in lines] == [(0, 4), (4, 6)]
    for line in lines:
        covered = [
            cmd
            for cmd in cmds
            if isinstance(cmd, (Glyph, SetGlue)) and line.start <= cmd.index < line.end
        ]
        assert all(cmd.y == line.y for cmd in covered)


def test_a_line_command_precedes_the_material_it_covers() -> None:
    # A backend or a selection pass can then walk the list once and always know
    # which line it is inside.
    line = hpack(_chars("ab"), measure=_measure).box
    page = vpack([line, line]).box

    cmds = ship(page, Point(0, page.height), measure=_measure)
    assert isinstance(cmds[0], Line)
    assert isinstance(cmds[3], Line)
    assert [type(cmd).__name__ for cmd in cmds] == [
        "Line",
        "Glyph",
        "Glyph",
        "Line",
        "Glyph",
        "Glyph",
    ]


def test_a_line_reports_its_boxs_height_and_depth_and_not_the_ink_of_its_glyphs() -> None:
    # A line of lowercase letters and a line with a descender must highlight to
    # the same height, which they can only do if `Line` passes the box's own
    # dimensions through. Flooring those is the *document* layer's job --
    # `advtext.style.Strut`, applied by `advtext.ui`, and
    # `tests/test_selection.py` pins the end of it -- so what is checked here is
    # ship-out's half of the bargain: report what the box says even when the
    # glyphs on it say something smaller.
    #
    # `_ink_measure` and not `_measure`, because under a measure that gives every
    # character the same extent the box's height *is* the ink and this test
    # cannot fail. The two boxes below start out genuinely different shapes.
    shallow = hpack(_chars("acem"), measure=_ink_measure).box
    deep = hpack(_chars("gjpqy"), measure=_ink_measure).box
    assert (shallow.height, shallow.depth) == (_INK_X_HEIGHT, 0)
    assert (deep.height, deep.depth) == (_INK_ASCENDER, _INK_DESCENDER)

    strut_height, strut_depth = 9 * PT, 3 * PT
    strutted = [
        Box(
            kind=box.kind,
            contents=box.contents,
            width=box.width,
            height=strut_height,
            depth=strut_depth,
        )
        for box in (shallow, deep)
    ]
    page = vpack(strutted).box
    first, second = _lines(ship(page, Point(0, page.height), measure=_ink_measure))

    assert (first.height, first.depth) == (strut_height, strut_depth)
    assert (second.height, second.depth) == (strut_height, strut_depth)
    # The line spans [y - height, y + depth), so the first one's top edge is the
    # top of the page and the last one's bottom edge is the bottom of it.
    assert first.y - first.height == 0
    assert second.y + second.depth == page.height + page.depth


def test_set_glue_carries_the_lines_full_height_so_a_selection_spans_the_space() -> None:
    # `_ink_measure` again: the space between "a" and "y" must take the whole
    # line's band and not the extent of either neighbour, and only a measure
    # where those three differ can tell.
    box = hpack(
        [*_chars("a"), Glue(GlueSpec(width=4 * PT)), *_chars("y")], measure=_ink_measure
    ).box
    (glue,) = _glues(ship(box, measure=_ink_measure))

    assert glue.height == box.height == _INK_X_HEIGHT
    assert glue.depth == box.depth == _INK_DESCENDER
    # The glue's rect runs from the end of "a" to the start of "y", so a caret
    # dropped anywhere in the space has a rect to land in.
    assert glue.x == _ADVANCE
    assert glue.x + glue.width == _ADVANCE + 4 * PT
    assert _glyphs(ship(box, measure=_ink_measure))[1].x == glue.x + glue.width


def test_a_bare_hbox_ships_as_one_line_without_being_wrapped_in_a_vbox() -> None:
    box = hpack(_chars("ab"), measure=_measure).box
    (line,) = _lines(ship(box, measure=_measure))

    assert (line.start, line.end) == (0, 2)
    assert line.width == box.width
    assert line.y == 0


def test_a_nested_hbox_inside_an_hbox_is_not_a_line_of_its_own() -> None:
    # A list marker, a formula or a link is part of the line that contains it.
    # One `Line` per visual line is what makes selection rects come out right.
    inner = hpack(_chars("xy"), measure=_measure).box
    outer = hpack([*_chars("a"), inner], measure=_measure).box
    page = vpack([outer]).box

    assert len(_lines(ship(page, Point(0, page.height), measure=_measure))) == 1


# --------------------------------------------------------------------------
# A small document end to end
# --------------------------------------------------------------------------


def test_two_lines_with_interline_glue_sit_one_baselineskip_apart() -> None:
    # §679's whole purpose: a constant baseline-to-baseline distance. Shipping is
    # where that becomes an observable pair of y coordinates rather than a glue
    # node nobody has measured.
    skip = InterlineSkip(
        baselineskip=GlueSpec(width=14 * PT),
        lineskip=GlueSpec(width=PT),
        lineskiplimit=0,
    )
    first = hpack(_chars("ab"), measure=_measure).box
    second = hpack(_chars("cd"), measure=_measure).box

    vlist: list[Node] = []
    prev_depth = append_to_vlist(vlist, first, -65_536_000, skip)
    append_to_vlist(vlist, second, prev_depth, skip)
    page = vpack(vlist).box

    first_line, second_line = _lines(ship(page, Point(0, page.height), measure=_measure))
    assert second_line.y - first_line.y == 14 * PT

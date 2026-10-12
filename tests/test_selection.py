r"""
Claims about the selection model, over hand-built commands with round positions.

Every coordinate here is a multiple of ten, so an expected boundary is a count of
characters and a failure names a number. The commands are constructed directly
rather than shipped from a real layout for most of these: the point of a test
about hit testing is that the geometry was *chosen*, and going through `hpack`
and `ship` would make every expected value depend on the packing as well. One
test at the end does run the real pipeline, because a model that only ever meets
hand-made input is a model that agrees with the test helper.

The tests that carry the most weight are the ones about cases that are wrong in
almost every hand-rolled selection:

- a **backwards drag**, which breaks when rect-building assumes `start <= end`;
- a click **past the right margin**, which lands on the next line when the hit
  test searches by distance instead of choosing the line first;
- **serialization across a wrap**, which freezes this column's width into the
  clipboard when a layout break is treated as a newline.
"""

from __future__ import annotations

from imscribe.markdown import TextBlock
from imscribe.nodes import CharNode, Glue, GlueSpec, Node
from imscribe.pack import CharDimens, PackMode, hpack, vpack
from imscribe.selection import (
    Granularity,
    Rect,
    Selection,
    SelectionModel,
)
from imscribe.shipout import Atom, DrawCmd, Glyph, Line, Point, RuleRect, SetGlue, ship
from imscribe.style import BlockKind, Theme
from imscribe.ui import compose_blocks
from imscribe.units import Scaled, sp_from_px

FONT = "prose@786432"

_ADV: Scaled = 10
_HEIGHT: Scaled = 8
_DEPTH: Scaled = 2
_LEADING: Scaled = 20


def _line(
    text: str,
    *,
    start: int = 0,
    x: Scaled = 0,
    y: Scaled = _HEIGHT,
    width: Scaled | None = None,
) -> list[DrawCmd]:
    """
    A visual line of `text`, one cell of `_ADV` per character, spaces as glue.

    `width` defaults to the natural width; passing a wider one is how a justified
    line whose last glyph stops short of the right margin is expressed.
    """
    cmds: list[DrawCmd] = []
    pen = x
    for offset, character in enumerate(text):
        if character == " ":
            cmds.append(
                SetGlue(
                    x=pen,
                    y=y,
                    width=_ADV,
                    natural=_ADV,
                    height=_HEIGHT,
                    depth=_DEPTH,
                    index=start + offset,
                )
            )
        else:
            cmds.append(
                Glyph(font=FONT, codepoint=ord(character), x=pen, y=y, index=start + offset)
            )
        pen += _ADV
    header = Line(
        x=x,
        y=y,
        width=pen - x if width is None else width,
        height=_HEIGHT,
        depth=_DEPTH,
        start=start,
        end=start + len(text),
    )
    return [header, *cmds]


def _document(*texts: str) -> SelectionModel:
    """
    Stacked lines, `_LEADING` apart, numbered continuously in reading order.
    """
    cmds: list[DrawCmd] = []
    start = 0
    for row, text in enumerate(texts):
        cmds.extend(_line(text, start=start, y=_HEIGHT + row * _LEADING))
        start += len(text)
    return SelectionModel.from_commands(cmds)


def _at(column: float, row: int = 0) -> Point:
    """
    A point `column` cells across and inside row `row`'s band.
    """
    return Point(x=round(column * _ADV), y=_HEIGHT + row * _LEADING)


# --------------------------------------------------------------------------
# Hit testing
# --------------------------------------------------------------------------


def test_a_click_left_of_a_glyphs_midpoint_gives_the_boundary_before_it() -> None:
    model = _document("abcd")
    # Glyph 2 occupies [20, 30); its midpoint is 25.
    assert model.hit(Point(20, _HEIGHT)) == 2
    assert model.hit(Point(24, _HEIGHT)) == 2


def test_a_click_right_of_a_glyphs_midpoint_gives_the_boundary_after_it() -> None:
    model = _document("abcd")
    assert model.hit(Point(25, _HEIGHT)) == 3
    assert model.hit(Point(29, _HEIGHT)) == 3


def test_the_midpoint_itself_falls_to_the_right_which_is_what_a_reader_expects() -> None:
    # Exactly on the midpoint is a tie and has to go somewhere. Rightward matches
    # every text system: the caret lands after the character you clicked the
    # middle of, so clicking "the middle of the m" puts the caret past the m.
    model = _document("abcd")
    assert model.hit(Point(15, _HEIGHT)) == 2


def test_a_click_left_of_the_line_lands_at_the_line_start() -> None:
    model = _document("abcd")
    assert model.hit(Point(-500, _HEIGHT)) == 0


def test_a_click_past_the_right_edge_of_a_line_lands_at_that_lines_end() -> None:
    # The one that goes wrong when the hit test looks for the nearest glyph in a
    # straight line: the first glyph of the line below is closer in that metric
    # than the last glyph of this one, and the caret jumps a line.
    model = _document("abcd", "efgh")
    assert model.hit(Point(5_000, _HEIGHT)) == 4

    # That boundary is also the start of the next line, and it is the *same
    # number* rather than an ambiguity to resolve -- the glue at the break was
    # discarded before ship-out saw it, so there is one boundary here and not
    # two. It is benign because rects come from the items a range covers:
    # selecting up to it highlights on the first line and not on the second.
    assert model.hit(Point(-5_000, _HEIGHT + _LEADING)) == 4
    assert len(model.rects(model.select(0, 4))) == 1


def test_a_click_past_the_right_margin_of_a_justified_line_still_lands_at_the_line_end() -> None:
    # A justified line's last glyph stops short of the margin only when the line
    # was set loose; the margin is the line's width, not the last glyph's edge.
    cmds = _line("ab", width=100 * _ADV)
    model = SelectionModel.from_commands(cmds)
    assert model.hit(Point(900, _HEIGHT)) == 2


def test_a_click_above_the_document_lands_on_the_first_line_and_below_it_on_the_last() -> None:
    # A drag that leaves the document extends the selection to the end rather
    # than stopping, which is what holding the mouse button and moving off the
    # window does everywhere.
    model = _document("abcd", "efgh", "ijkl")
    assert model.hit(Point(0, -10_000)) == 0
    assert model.hit(Point(10_000, 10_000)) == 12


def test_a_click_in_the_gap_between_two_lines_belongs_to_the_nearer_line() -> None:
    # Vertical glue takes no reading index, so there is nothing in the gap to
    # select; the click has to resolve to a line and the nearer one is it.
    model = _document("abcd", "efgh")
    gap_top = _HEIGHT + _DEPTH
    gap_bottom = _HEIGHT + _LEADING - _HEIGHT
    assert model.hit(Point(0, gap_top)) == 0
    assert model.hit(Point(0, gap_bottom - 1)) == 4


def test_an_interword_space_is_pointable_because_ship_out_gives_it_an_index() -> None:
    model = _document("ab cd")
    # The space is item 2, occupying [20, 30).
    assert model.hit(Point(21, _HEIGHT)) == 2
    assert model.hit(Point(28, _HEIGHT)) == 3


def test_an_empty_document_hit_tests_to_the_only_boundary_it_has() -> None:
    model = SelectionModel.from_commands([])
    assert model.length == 0
    assert model.hit(Point(50, 50)) == 0
    assert model.rects(model.select(0, 0)) == []


def test_a_rule_is_not_pointable_because_a_thematic_break_is_not_a_character() -> None:
    cmds: list[DrawCmd] = [*_line("ab"), RuleRect(x=0, y=20, width=200, height=2)]
    model = SelectionModel.from_commands(cmds)
    assert model.length == 2
    assert model.text(model.select(0, 2)) == "ab"


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------


def test_a_backwards_drag_produces_the_same_range_as_the_forwards_one() -> None:
    # The case that is always broken. Rect-building assumes start <= end and
    # produces nothing when it is not, so dragging right-to-left highlights
    # nothing at all and only ever gets noticed by a user.
    model = _document("abcdefgh")
    forwards = model.select(2, 6)
    backwards = model.select(6, 2)

    assert forwards == backwards == Selection(2, 6)
    assert model.rects(forwards) == model.rects(backwards)
    assert model.text(forwards) == model.text(backwards) == "cdef"


def test_a_backwards_drag_across_three_lines_produces_the_same_rects_as_forwards() -> None:
    model = _document("abcd", "efgh", "ijkl")
    down = model.select_at(_at(1, 0), _at(3, 2), Granularity.CHARACTER)
    up = model.select_at(_at(3, 2), _at(1, 0), Granularity.CHARACTER)
    assert down == up
    assert model.rects(down) == model.rects(up)


def test_a_range_off_the_end_is_clamped_rather_than_raising_three_frames_later() -> None:
    model = _document("abcd")
    assert model.select(-50, 900) == Selection(0, 4)


def test_a_plain_click_selects_nothing() -> None:
    model = _document("abcd")
    boundary = model.hit(_at(2))
    selection = model.select(boundary, boundary)
    assert selection.is_empty
    assert model.rects(selection) == []
    assert model.text(selection) == ""


# --------------------------------------------------------------------------
# Rects
# --------------------------------------------------------------------------

# A fake font whose glyphs have real, *unequal* vertical extents, in the scaled
# points the theme works in so that a strut sized from a 16 px body dominates
# them. Three classes and no more: an x-height letter, one that reaches above it,
# and one that hangs below the baseline.
_INK_ADVANCE: Scaled = sp_from_px(10.0)
_INK_X_HEIGHT: Scaled = sp_from_px(8.0)
_INK_ASCENDER: Scaled = sp_from_px(12.0)
_INK_DESCENDER: Scaled = sp_from_px(4.0)
_INK_MEASURE_WIDTH: Scaled = sp_from_px(300.0)

_DESCENDS = frozenset("gjpqy")
_REACHES_UP = frozenset("bdfhijklt")


def _ink_measure(node: CharNode) -> CharDimens:
    """
    Height and depth per codepoint, which is what makes an ink extent visible.
    """
    character = chr(node.codepoint)
    return CharDimens(
        width=_INK_ADVANCE,
        height=_INK_ASCENDER if character in _REACHES_UP else _INK_X_HEIGHT,
        depth=_INK_DESCENDER if character in _DESCENDS else 0,
    )


def _ink_nodes(text: str) -> list[Node]:
    return [CharNode(FONT, ord(character)) for character in text]


def test_a_selection_within_one_line_yields_exactly_one_rect() -> None:
    model = _document("abcdefgh")
    (rect,) = model.rects(model.select(2, 5))
    assert rect == Rect(x=20, y=0, width=30, height=_HEIGHT + _DEPTH)


def test_a_selection_spanning_three_lines_yields_three_rects_and_the_middle_one_is_full() -> None:
    model = _document("abcd", "efgh", "ijkl")
    first, middle, last = model.rects(model.select(2, 10))

    # The first starts mid-way and runs to its own right edge; the last starts at
    # its own left edge and stops mid-way; only the middle is the whole line.
    assert (first.x, first.width) == (20, 20)
    assert (middle.x, middle.width) == (0, 40)
    assert (last.x, last.width) == (0, 20)
    assert [rect.y for rect in (first, middle, last)] == [0, _LEADING, 2 * _LEADING]


def test_every_rect_is_full_line_height_rather_than_the_ink_of_its_glyphs() -> None:
    # A line of lowercase letters and a line with a descender must highlight to
    # the same height. A selection whose height flickers with whether a line
    # happens to contain a "g" reads as broken even though each rect is
    # individually defensible.
    #
    # The one test in this file that runs the *document* layer, and it has to.
    # Every other test here hands `SelectionModel` a `Line` whose height and
    # depth were chosen, which cannot distinguish a full line height from an ink
    # extent however different the letters look -- `_document("acem", "gjpqy")`
    # is geometrically identical to `_document("aaaa", "aaaaa")`. What makes the
    # claim true is `imscribe.style.Strut`, applied by `imscribe.ui`, so that is
    # what this goes through. The ink below is per codepoint and really does
    # differ between the two lines; the test below this one is the guard on that.
    theme = Theme.build()
    style = theme.style(BlockKind.PARAGRAPH)
    blocks = (
        TextBlock(kind=BlockKind.PARAGRAPH, style=style, material=tuple(_ink_nodes("acem"))),
        TextBlock(kind=BlockKind.PARAGRAPH, style=style, material=tuple(_ink_nodes("gjpqy"))),
    )
    box = compose_blocks(blocks, theme, _INK_MEASURE_WIDTH, _ink_measure)
    model = SelectionModel.from_commands(ship(box, Point(0, box.height), measure=_ink_measure))

    rects = model.rects(model.select(0, model.length))
    assert len(rects) == 2
    assert {rect.height for rect in rects} == {style.strut.total}


def test_the_ink_fixture_gives_the_two_lines_genuinely_different_extents() -> None:
    # The test above is only a test of the strut while the two lines it uses
    # have genuinely different ink, and a fixture that quietly went uniform
    # would leave it passing and covering nothing. That happened here once
    # already, which is why this is asserted rather than assumed.
    shallow = hpack(_ink_nodes("acem"), measure=_ink_measure).box
    deep = hpack(_ink_nodes("gjpqy"), measure=_ink_measure).box
    assert shallow.depth == 0
    assert deep.depth > shallow.depth
    assert deep.height > shallow.height
    assert shallow.height + shallow.depth != deep.height + deep.depth


def test_a_lines_rect_reaches_its_right_margin_when_the_selection_runs_past_its_end() -> None:
    # The right edge of the last item on a line is the line's right edge, not the
    # glyph's advance, so a justified line highlights to the margin rather than
    # leaving a notch where the stretched glue was.
    cmds = [*_line("ab", start=0, width=100), *_line("cd", start=2, y=_HEIGHT + _LEADING)]
    model = SelectionModel.from_commands(cmds)
    first, _ = model.rects(model.select(0, 4))
    assert first.x + first.width == 100


def test_a_selection_that_touches_no_items_on_a_line_draws_nothing_there() -> None:
    model = _document("abcd", "efgh", "ijkl")
    rects = model.rects(model.select(0, 2))
    assert len(rects) == 1
    assert rects[0].y == 0


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def test_a_layout_line_break_serialises_as_a_space_and_not_as_a_newline() -> None:
    # The documented decision. A paragraph wrapped into three lines is one
    # paragraph; copying it must not freeze this column's width into the
    # clipboard, because the wrap points show up as ragged hard breaks anywhere
    # the text is pasted at a different measure.
    model = _document("the quick", "brown fox", "jumps")
    assert model.text(model.select(0, model.length)) == "the quick brown fox jumps"
    assert "\n" not in model.text(model.select(0, model.length))


def test_a_break_named_in_hard_breaks_serialises_as_a_newline_because_it_is_content() -> None:
    # Every line of a fenced code block is a line in the source and joining them
    # with spaces destroys the program. Nothing in the command stream can tell
    # those from a wrap, so the layer that put the newlines there says where
    # they are.
    model = _document("def f():", "    return 1")
    text = model.text(model.select(0, model.length), hard_breaks={8})
    assert text == "def f():\n    return 1"


def test_a_hard_break_drops_the_space_the_parfillskip_would_have_left_dangling() -> None:
    # A paragraph ends with `\parfillskip`, which is an interword space sitting
    # at the end of its last line and would otherwise serialise as a trailing
    # space before every newline.
    model = _document("one ", "two")
    assert model.text(model.select(0, model.length), hard_breaks={4}) == "one\ntwo"


def test_a_wrap_after_a_space_does_not_add_a_second_one() -> None:
    model = _document("one ", "two")
    assert model.text(model.select(0, model.length)) == "one two"


def test_serialising_a_partial_range_takes_exactly_the_items_it_covers() -> None:
    model = _document("abcd", "efgh")
    assert model.text(model.select(2, 6)) == "cd ef"
    assert model.text(model.select(3, 4)) == "d"
    assert model.text(model.select(4, 4)) == ""


def test_an_interword_space_serialises_as_a_space_wherever_it_came_from() -> None:
    model = _document("ab cd")
    assert model.text(model.select(0, 5)) == "ab cd"
    assert model.text(model.select(2, 3)) == " "


# --------------------------------------------------------------------------
# Granularity
# --------------------------------------------------------------------------


def test_word_granularity_stops_at_punctuation() -> None:
    model = _document("foo.bar")
    assert model.word_at(_at(1)) == Selection(0, 3)
    assert model.text(model.word_at(_at(1))) == "foo"
    assert model.word_at(_at(4.5)) == Selection(4, 7)


def test_double_clicking_punctuation_selects_the_run_of_punctuation() -> None:
    # "Stops at punctuation" from the other side: a run of punctuation is its own
    # unit, which is what an editor does and is what makes the rule symmetric
    # rather than a special case for letters.
    model = _document("a--b")
    assert model.word_at(_at(1.5)) == Selection(1, 3)
    assert model.text(model.word_at(_at(1.5))) == "--"


def test_double_clicking_a_space_selects_the_run_of_spaces() -> None:
    model = _document("a  b")
    assert model.word_at(_at(1.5)) == Selection(1, 3)


def test_word_granularity_keeps_digits_and_underscores_inside_a_word() -> None:
    # `__init__` and `utf8` are one word each. This is the rule pptmstr's inline
    # parser also had to get right, for the same reason: technical prose is full
    # of identifiers and breaking them at the underscore reads as a bug.
    model = _document("a __init__ b")
    assert model.text(model.word_at(_at(5))) == "__init__"


def test_word_granularity_excludes_the_apostrophe_and_says_so() -> None:
    # A deliberate choice rather than an oversight: including apostrophes and
    # hyphens would make "don't" one word and also make `foo-bar` one word, and
    # this layer cannot tell prose from code to apply different rules.
    model = _document("don't")
    assert model.text(model.word_at(_at(1))) == "don"


def test_a_double_click_past_the_end_of_a_line_takes_the_last_word_on_it() -> None:
    model = _document("alpha beta", "gamma")
    assert model.text(model.word_at(Point(5_000, _HEIGHT))) == "beta"


def test_line_granularity_takes_the_whole_visual_line_and_nothing_below_it() -> None:
    model = _document("abcd", "efgh")
    assert model.line_at(_at(1, 1)) == Selection(4, 8)
    assert model.text(model.line_at(_at(1, 1))) == "efgh"
    assert len(model.rects(model.line_at(_at(1, 1)))) == 1


def test_a_word_granularity_drag_never_cuts_a_word_in_half() -> None:
    # Granularity is state, not a one-shot gesture: a drag that began as a double
    # click keeps snapping to whole words as it extends, in both directions.
    model = _document("alpha beta gamma")
    forwards = model.select_at(_at(1), _at(12), Granularity.WORD)
    backwards = model.select_at(_at(12), _at(1), Granularity.WORD)

    assert forwards == backwards == Selection(0, 16)
    assert model.text(forwards) == "alpha beta gamma"


def test_a_line_granularity_drag_covers_every_line_it_touches_whole() -> None:
    model = _document("abcd", "efgh", "ijkl")
    selection = model.select_at(_at(2, 2), _at(2, 0), Granularity.LINE)
    assert selection == Selection(0, 12)
    assert len(model.rects(selection)) == 3


# --------------------------------------------------------------------------
# Nested lines, which a table produces
# --------------------------------------------------------------------------


def test_an_item_belongs_to_the_innermost_line_containing_it() -> None:
    # A vbox inside an hbox -- a table cell -- puts lines inside a line. The
    # container is not a fragment: pointing at it means pointing at one of the
    # lines inside it, and treating it as a fragment of its own would give every
    # item on those lines two possible rects.
    outer = Line(x=0, y=8, width=80, height=8, depth=2, start=0, end=4)
    inner_first = Line(x=0, y=8, width=40, height=8, depth=2, start=0, end=2)
    inner_second = Line(x=40, y=28, width=40, height=8, depth=2, start=2, end=4)
    cmds: list[DrawCmd] = [
        outer,
        inner_first,
        Glyph(FONT, ord("a"), 0, 8, 0),
        Glyph(FONT, ord("b"), 10, 8, 1),
        inner_second,
        Glyph(FONT, ord("c"), 40, 28, 2),
        Glyph(FONT, ord("d"), 50, 28, 3),
    ]
    model = SelectionModel.from_commands(cmds)

    assert [fragment.line for fragment in model.fragments] == [inner_first, inner_second]

    # "c" occupies [40, 50) on the second inner line; 44 is left of its midpoint.
    assert model.hit(Point(44, 28)) == 2
    # Two rects and not three: the container contributes none of its own.
    assert len(model.rects(model.select(0, 4))) == 2


# --------------------------------------------------------------------------
# Against the real pipeline, so the model does not only agree with the helper
# --------------------------------------------------------------------------


def _measure(node: CharNode) -> CharDimens:
    return CharDimens(width=_ADV, height=_HEIGHT, depth=_DEPTH)


def _nodes(text: str) -> list[Node]:
    return [CharNode(FONT, ord(character)) for character in text]


def test_selection_works_on_commands_the_real_ship_out_produced() -> None:
    # Everything above builds commands by hand so the geometry is chosen. This
    # one goes through `hpack`, `vpack` and `ship`, including a line whose glue
    # was stretched, to check the model against the thing it will actually be
    # handed rather than only against the helper at the top of this file.
    first_nodes: list[Node] = [
        *_nodes("ab"),
        Glue(GlueSpec(width=_ADV, stretch=_ADV)),
        *_nodes("cd"),
    ]
    first = hpack(first_nodes, 60, PackMode.EXACTLY, measure=_measure).box
    second = hpack(_nodes("ef"), measure=_measure).box
    page = vpack([first, Glue(GlueSpec(width=_ADV)), second]).box

    model = SelectionModel.from_commands(ship(page, Point(0, page.height), measure=_measure))

    assert model.length == 7
    assert model.text(model.select(0, model.length)) == "ab cd ef"
    assert model.text(model.select(0, 5)) == "ab cd"

    # The glue was stretched from 10 to 20, so "c" starts at 40 rather than 30
    # and the hit test has to read the shipped positions rather than assume a
    # uniform cell. 41 is inside "c", left of its midpoint at 45.
    assert model.hit(Point(41, first.height)) == 3
    (rect,) = model.rects(model.select(0, 2))
    assert rect.width == 2 * _ADV

    # The stretched space is one item and its cell is the whole stretched width.
    (space,) = model.rects(model.select(2, 3))
    assert space.x == 2 * _ADV
    assert space.width == 2 * _ADV


def test_a_selection_across_the_real_line_break_joins_with_a_space() -> None:
    first = hpack(_nodes("ab"), measure=_measure).box
    second = hpack(_nodes("cd"), measure=_measure).box
    page = vpack([first, second]).box

    model = SelectionModel.from_commands(ship(page, Point(0, page.height), measure=_measure))
    assert model.text(model.select(0, 4)) == "ab cd"
    assert model.text(model.select(0, 4), hard_breaks={2}) == "ab\ncd"


# --------------------------------------------------------------------------
# Fill, separators, and lines side by side (2026-10-07)
#
# Three things the tests above could not exercise, because they need a kind of
# item or a kind of geometry `_line` does not build: glue with no natural
# width, a break that is content in the middle of a line, and two lines that
# share a vertical band. Each is built by hand here so the expected answer can
# be read off the fixture; the same rules are checked against real tables and
# documents in `tests/test_units_layout.py` and `tests/test_bare_view.py`.
# --------------------------------------------------------------------------


def _fill(index: int, x: Scaled, *, width: Scaled = 0, y: Scaled = _HEIGHT) -> SetGlue:
    """
    Glue with no natural width, as a `\\rightskip`, a `\\parfillskip` or an `\\hss` ships.
    """
    return SetGlue(x=x, y=y, width=width, natural=0, height=_HEIGHT, depth=_DEPTH, index=index)


def _cells(*texts: str, y: Scaled = _HEIGHT, start: int = 0) -> tuple[list[DrawCmd], list[int]]:
    """
    One line holding several cells, each `fill text fill`, as an unwrapped table row ships.

    Returns the commands and the index each cell begins at.
    """
    cmds: list[DrawCmd] = []
    begins: list[int] = []
    index, pen = start, 0
    for text in texts:
        begins.append(index)
        cmds.append(_fill(index, pen, y=y))
        index += 1
        for character in text:
            cmds.append(Glyph(font=FONT, codepoint=ord(character), x=pen, y=y, index=index))
            index += 1
            pen += _ADV
        cmds.append(_fill(index, pen, width=3 * _ADV, y=y))
        index += 1
        pen += 3 * _ADV
    header = Line(x=0, y=y, width=pen, height=_HEIGHT, depth=_DEPTH, start=start, end=index)
    return [header, *cmds], begins


def test_fill_at_the_ends_of_a_line_is_not_a_space_and_fill_between_words_is_one() -> None:
    cmds, _ = _cells("ab", "cd")
    model = SelectionModel.from_commands(cmds)
    # fill a b fill | fill c d fill: nothing before "ab", nothing after "cd",
    # and the two fills between them are one space, not two.
    assert model.text(Selection(0, model.length)) == "ab cd"
    # A selection of nothing but fill is no text at all.
    assert model.text(Selection(3, 5)) == ""


def test_a_separator_inside_a_line_replaces_the_fill_around_it() -> None:
    cmds, begins = _cells("ab", "cd", "ef")
    model = SelectionModel.from_commands(cmds)
    everything = Selection(0, model.length)
    tabs = {begins[1]: "\t", begins[2]: "\t"}
    assert model.text(everything, separators=tabs) == "ab\tcd\tef"
    # Starting at a cell's own first index, its separator is not between two
    # selected things and is not written.
    assert model.text(Selection(begins[1], model.length), separators=tabs) == "cd\tef"
    # Any string will do, and one given for an index the selection does not
    # reach changes nothing.
    assert model.text(everything, separators={begins[1]: "\n\n", 999: "!"}) == "ab\n\ncd ef"


def test_a_separator_with_no_selected_character_after_it_is_not_written() -> None:
    # A selection that ends on the fill a cell (or a list item, ahead of its
    # marker) begins with has crossed that item's separator and reached none
    # of its text. Measured before this was pinned: "ab\t", and through
    # `imscribe.ui.units` a copy ending at a nested list item's marker ended
    # with that item's newline and its indent.
    cmds, begins = _cells("ab", "cd", "ef")
    model = SelectionModel.from_commands(cmds)
    tabs = {begins[1]: "\t", begins[2]: "\t"}
    assert model.text(Selection(0, begins[1] + 1), separators=tabs) == "ab"
    assert model.text(Selection(0, begins[1] + 2), separators=tabs) == "ab\tc"
    assert model.text(Selection(0, begins[1] + 1)) == "ab"


def test_a_separator_at_the_start_of_a_line_takes_the_place_of_the_wrap() -> None:
    model = _document("ab", "cd", "ef")
    everything = Selection(0, model.length)
    assert model.text(everything) == "ab cd ef"
    assert model.text(everything, separators={2: "\n"}) == "ab\ncd ef"
    assert model.text(everything, separators={2: "\n\n", 4: "\t"}) == "ab\n\ncd\tef"
    # `hard_breaks` is the same thing with the separator fixed at a newline,
    # and a separator given for the same boundary wins over it.
    assert model.text(everything, hard_breaks={2, 4}) == "ab\ncd\nef"
    assert model.text(everything, hard_breaks={2}, separators={2: "\t"}) == "ab\tcd ef"
    # A space as a separator is a wrap: it is not doubled after a space.
    spaced = _document("ab ", "cd")
    assert spaced.text(Selection(0, spaced.length), separators={3: " "}) == "ab cd"


def test_a_line_that_holds_only_a_rule_is_not_a_line_of_text() -> None:
    first = _line("ab", start=0, y=_HEIGHT)
    rule_line = Line(x=0, y=_HEIGHT + _LEADING, width=40, height=1, depth=0, start=2, end=2)
    rule = RuleRect(x=0, y=_HEIGHT + _LEADING - 1, width=40, height=1)
    blank = Line(
        x=0, y=_HEIGHT + 2 * _LEADING, width=0, height=_HEIGHT, depth=_DEPTH, start=2, end=2
    )
    last = _line("cd", start=2, y=_HEIGHT + 3 * _LEADING)

    ruled = SelectionModel.from_commands([*first, rule_line, rule, *last])
    assert [len(fragment.items) for fragment in ruled.fragments] == [2, 2]
    assert ruled.text(Selection(0, 4)) == "ab cd"

    # A blank line of text -- no rule in it -- is still a line, and still copies
    # as a break of its own.
    blanked = SelectionModel.from_commands([*first, blank, *last])
    assert [len(fragment.items) for fragment in blanked.fragments] == [2, 0, 2]
    assert blanked.text(Selection(0, 4)) == "ab\ncd"


def test_a_highlight_does_not_cover_fill_at_either_end_of_what_is_selected() -> None:
    cmds, begins = _cells("ab", "cd")
    model = SelectionModel.from_commands(cmds)
    # Everything: from the left of "a" to the right of "d", fill between them
    # included, but not the fill before "a" nor the 3-cell fill after "d".
    (whole,) = model.rects(Selection(0, model.length))
    assert (whole.x, whole.width) == (0, 2 * _ADV + 3 * _ADV + 2 * _ADV)
    # The second cell alone: its two letters, and none of the blank beside them.
    (second,) = model.rects(Selection(begins[1], model.length))
    assert (second.x, second.width) == (5 * _ADV, 2 * _ADV)
    # Only fill selected: nothing to highlight.
    assert model.rects(Selection(3, 5)) == []


def _side_by_side() -> tuple[SelectionModel, list[DrawCmd]]:
    """
    A row of two cells as a wrapped table row ships: a container line, then a stack of lines a cell.

    The left cell has one line, `ab`, at x 0. The right cell has three, `cd`,
    `ef`, `gh`, at x 100. So the left cell's column is empty beside the right
    cell's second and third lines.
    """
    row = Line(
        x=0, y=_HEIGHT, width=200, height=_HEIGHT, depth=_DEPTH + 2 * _LEADING, start=0, end=8
    )
    left = _line("ab", start=0, x=0, y=_HEIGHT)
    right = [
        cmd
        for number, text in enumerate(("cd", "ef", "gh"))
        for cmd in _line(text, start=2 + 2 * number, x=100, y=_HEIGHT + number * _LEADING)
    ]
    below = _line("zz", start=8, x=0, y=_HEIGHT + 4 * _LEADING, width=200)
    cmds = [row, *left, *right, *below]
    return SelectionModel.from_commands(cmds), cmds


def test_a_point_under_a_short_cell_belongs_to_that_cell_not_to_its_taller_neighbour() -> None:
    model, _ = _side_by_side()
    by_text = {model.text(Selection(f.start, f.end)): f for f in model.fragments}
    assert sorted(by_text) == ["ab", "cd", "ef", "gh", "zz"]
    assert by_text["ab"].outer is not None and by_text["zz"].outer is None
    assert by_text["ab"].reach == by_text["gh"].reach

    third_row_y = _HEIGHT + 2 * _LEADING
    # Level with the right cell's third line, under the left cell's only one.
    assert model.fragment_at(Point(5, third_row_y)) is by_text["ab"]
    # The same height in the right cell is that cell's third line.
    assert model.fragment_at(Point(105, third_row_y)) is by_text["gh"]
    # Between the two cells, where no line's extent reaches: the line whose
    # band holds the point, nearest in x -- as before.
    assert model.fragment_at(Point(70, third_row_y)) is by_text["gh"]
    assert model.fragment_at(Point(70, _HEIGHT)) is by_text["cd"]
    assert model.fragment_at(Point(30, _HEIGHT)) is by_text["ab"]
    # Below the row, in the next line's band: that line, wherever x is.
    assert model.fragment_at(Point(105, _HEIGHT + 4 * _LEADING)) is by_text["zz"]
    # And a drag from the short cell down its empty column stays in it.
    assert (
        model.text(
            model.select_at(Point(0, _HEIGHT), Point(15, third_row_y), Granularity.CHARACTER)
        )
        == "ab"
    )


def test_an_atom_of_no_width_is_an_item_and_not_fill() -> None:
    """
    Review 2, item 8. An `Atom` is a `SetGlue` by subclass, and glue of no
    natural width is fill: positioning, skipped by the highlight and by a
    copy. A formula that happens to be zero wide (`${}$`) is not that.
    """
    cmds: list[DrawCmd] = [
        Line(x=0, y=100, width=30, height=8, depth=2, start=0, end=4),
        Glyph(font="f@1", codepoint=ord("a"), x=0, y=100, index=0),
        Atom(x=10, y=100, width=0, natural=0, height=8, depth=2, index=1),
        SetGlue(x=10, y=100, width=10, natural=0, height=8, depth=2, index=2),
        Glyph(font="f@1", codepoint=ord("b"), x=20, y=100, index=3),
    ]
    model = SelectionModel.from_commands(cmds)
    assert model.text(Selection(0, 4), atoms={1: "${}$"}) == "a${}$ b"
    # Selected alone it is highlighted (a rectangle of no width, on its line)
    # and copied; the real fill beside it is neither.
    assert model.text(Selection(1, 2), atoms={1: "${}$"}) == "${}$"
    assert len(model.rects(Selection(1, 2))) == 1
    assert model.rects(Selection(2, 3)) == []

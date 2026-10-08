r"""
`StreamView`: a document drawn while it is still arriving.

`advtext.ui.stream_view` promises four things beyond what `BareView` does, and
each is a claim about work done or about what stays still, so each is tested
by counting or by comparing positions, never by timing and never by looking:

1. per change, only the live tail is shipped and indexed; and however many
   pieces arrive between two frames there is one parse and one layout;
2. the pane follows the end until the reader scrolls away, and not after;
3. a table being written does not rescale the rows already on screen;
4. a selection keeps meaning the same text while text arrives, or is cut back
   to the settled part -- it is never left meaning other words.

The scrolling tests run real ImGui frames with no display, in the idiom of
`tests/test_bare_view.py`. The layout tests need no frame at all:
`StreamView.sync()` and `layout_for` are the per-frame work without the frame.

**One test here is a measurement kept as a tripwire**, and its docstring says
so: `test_the_origin_imgui_hands_a_view_is_a_whole_number_of_pixels`. The
plan's vertical snapping hazard is real for a fractional origin. ImGui does
not produce one by itself, which is what that test measures; a host can, with
a fractional cursor position, and the view snaps its origin so that it does
not matter (`test_a_fractional_cursor_position_sets_the_same_lines_as_a_whole_one`).

Nothing here opens a window.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import advtext.stream as stream_module
import advtext.ui.bare_view as bare_module
import advtext.ui.units as units_module
from advtext.backends.imgui_draw import draw
from advtext.markdown import TableBlock, TextBlock, build_document
from advtext.selection import Selection, SelectionModel
from advtext.shipout import Glyph, Line, Point, ship
from advtext.stream import CommitPolicy, StreamDocument
from advtext.style import Align, Theme, char_measure, fontlib_metrics
from advtext.ui import SizedTable, table_columns, table_natural_widths
from advtext.ui.bare_view import BareView
from advtext.ui.stream_view import StreamView
from advtext.ui.units import CODE_PIECE_LINES, TABLE_PIECE_ROWS, layout_units
from advtext.units import Scaled, px_from_sp, sp_from_px

ROOT = Path(__file__).resolve().parent.parent

WIDTH = sp_from_px(500.0)


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure(bundled_fonts: Any) -> Any:
    return char_measure(fontlib_metrics)


def pieces_of(source: str) -> list[str]:
    """
    `source` a word at a time, each with the white space after it.
    """
    return re.findall(r"\S+\s*|\s+", source)


def streamed(
    source: str,
    theme: Theme,
    measure: Any,
    *,
    policy: CommitPolicy = CommitPolicy.KEEP_STREAMED,
    close: bool = False,
    **kwargs: Any,
) -> StreamView:
    """
    A view whose stream has received all of `source`, a word at a time, laid out each time.
    """
    stream = StreamDocument(theme, fontlib_metrics, policy=policy)
    view = StreamView(stream, measure, **kwargs)
    for piece in pieces_of(source):
        stream.append(piece)
        view.sync()
        view.layout_for(WIDTH)
    if close:
        stream.close()
        view.sync()
        view.layout_for(WIDTH)
    return view


# -- 1. what is redone --------------------------------------------------------


class _Counter:
    def __init__(self, real: Any) -> None:
        self.real = real
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return self.real(*args, **kwargs)


def test_each_append_ships_and_indexes_the_live_tail_and_nothing_settled(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    shipped = _Counter(ship)
    monkeypatch.setattr(units_module, "ship", shipped)
    indexed = _Counter(SelectionModel.from_commands)
    monkeypatch.setattr(units_module.SelectionModel, "from_commands", indexed)

    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    steps = 0
    worst_ship = worst_index = 0
    several_live = 0
    for piece in pieces_of(source):
        stream.append(piece)
        ships, indexes = shipped.calls, indexed.calls
        assert view.sync()
        layout = view.layout_for(WIDTH)
        # Touch what a frame touches: draw everything, hit-test in the tail.
        assert layout.cmds or not layout.placed
        layout.model.hit(Point(0, layout.height - 1))
        steps += 1
        # One unit, the one being written, however long the document is by
        # now **and however many blocks are live**. The bound here was the
        # number of live blocks, which a view that re-shipped every item of a
        # list being written on each word would have met. A word changes one
        # block; the stream hands the other live blocks back as the objects
        # they were, and their units are found by identity.
        assert shipped.calls - ships <= 1
        assert indexed.calls - indexes <= 1
        several_live += len(stream.live) >= 3
        worst_ship = max(worst_ship, shipped.calls - ships)
        worst_index = max(worst_index, indexed.calls - indexes)

    final = view.layout_for(WIDTH)
    assert steps > 400 and len(final.placed) > 15
    # The document has a list and a quote, so the tail was three blocks or
    # more at many steps (112 of 440 when this was written): the bound of
    # one was tested where it differs from the number of live blocks.
    assert several_live > 50
    # The whole replay shipped about one unit a step. Re-shipping the document
    # each step -- what `DocumentView` did before units -- would be the sum of
    # the unit counts along the way, several thousand.
    assert shipped.calls <= steps + len(final.placed)
    assert worst_ship >= 1 and worst_index >= 1
    assert view.relayouts == steps


def test_a_settled_block_keeps_its_shipped_unit_for_good(theme: Theme, measure: Any) -> None:
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    held: dict[int, Any] = {}
    for piece in pieces_of(source):
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        settled = len(stream.committed)
        for unit in layout.placed:
            if unit.block_start + len(unit.blocks) > settled:
                continue
            before = held.setdefault(unit.block_start, unit.unit.cmds)
            # The same tuple object, at the same place, as when it first settled.
            assert before is unit.unit.cmds
    assert len(held) > 10


def test_pieces_that_arrive_between_two_frames_cost_one_parse_and_one_layout(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    pieces = pieces_of(source)
    # The stream tokenises once per parse it runs. (It called `build_document`
    # when this was written; it now resumes a walk of its own, and `_tokens`
    # is the call each parse makes exactly once.)
    parsed = _Counter(stream_module._tokens)
    monkeypatch.setattr(stream_module, "_tokens", parsed)
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)

    for burst in (pieces[:60], pieces[60:61], pieces[61:200]):
        for piece in burst:
            stream.append(piece)
        parses, layouts = parsed.calls, view.relayouts
        assert stream.pending
        view.sync()
        view.layout_for(WIDTH)
        # One read of the stream: at most its two parses (boundary, then tail).
        assert 1 <= parsed.calls - parses <= 2
        assert view.relayouts == layouts + 1
        # And a frame on which nothing arrived does neither.
        for _ in range(3):
            assert not view.sync()
            view.layout_for(WIDTH)
        assert parsed.calls - parses <= 2
        assert view.relayouts == layouts + 1


@pytest.mark.parametrize("policy", list(CommitPolicy))
def test_a_finished_stream_is_laid_out_as_its_document_would_be_from_scratch(
    theme: Theme, measure: Any, policy: CommitPolicy
) -> None:
    # Everything incremental above is worth nothing if the result differs from
    # laying the same blocks out cold.
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    view = streamed(source, theme, measure, policy=policy, close=True)
    layout = view.layout_for(WIDTH)
    cold = layout_units(view._layout_blocks(WIDTH), theme, WIDTH, measure)
    assert layout.cmds == cold.cmds
    assert layout.height == cold.height and layout.length == cold.length
    # Under RESET with no table held, that is exactly the plain document.
    if policy is CommitPolicy.RESET:
        assert view._layout_blocks(WIDTH) == view.stream.blocks
        plain = build_document(source, theme, fontlib_metrics, references=False)
        assert view.stream.blocks == plain.blocks


# -- commit policy ------------------------------------------------------------

PARAGRAPH = (
    "This paragraph is long enough to be set on several lines at the width the test "
    "uses, so that whether its settled lines move when it commits is a thing that "
    "can be seen in the positions of its glyphs and not only argued about.\n"
    "\n"
    "Next block starts here.\n"
)


def _first_block_glyphs(view: StreamView) -> list[tuple[int, Scaled, Scaled]]:
    layout = view.layout_for(WIDTH)
    return [(c.codepoint, c.x, c.y) for c in layout.placed[0].cmds if isinstance(c, Glyph)]


def test_keeping_streamed_breaks_moves_nothing_when_a_block_commits(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.KEEP_STREAMED)
    view = StreamView(stream, measure)
    live: list[tuple[int, Scaled, Scaled]] = []
    for piece in pieces_of(PARAGRAPH):
        was_live = not stream.committed
        stream.append(piece)
        view.sync()
        glyphs = _first_block_glyphs(view)
        if was_live and not stream.committed:
            live = glyphs
    assert len(stream.committed) == 1 and len(live) > 150
    # Committed, the paragraph's every glyph is where it was while it streamed.
    assert _first_block_glyphs(view) == live
    block = stream.committed[0]
    assert isinstance(block, TextBlock) and block.style.align is Align.LEFT


def test_resetting_on_commit_sets_the_block_again_once_and_justified(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    view = StreamView(stream, measure)
    live: list[tuple[int, Scaled, Scaled]] = []
    for piece in pieces_of(PARAGRAPH):
        stream.append(piece)
        view.sync()
        if not stream.committed:
            live = _first_block_glyphs(view)
    block = stream.committed[0]
    assert isinstance(block, TextBlock) and block.style.align is Align.JUSTIFY
    reset = _first_block_glyphs(view)
    # The same characters, set differently: that is the one jump RESET makes.
    assert [codepoint for codepoint, _, _ in reset] == [codepoint for codepoint, _, _ in live]
    assert reset != live
    # And it is the document's own layout of that paragraph.
    plain = build_document(PARAGRAPH, theme, fontlib_metrics, references=False)
    cold = layout_units(plain.blocks[:1], theme, WIDTH, measure)
    assert [(c.codepoint, c.x, c.y) for c in cold.cmds if isinstance(c, Glyph)] == reset


# -- 3. tables ------------------------------------------------------------------

TABLE = (
    "| key | value |\n"
    "|-----|-------|\n"
    "| a | short |\n"
    "| bb | a much longer cell of text |\n"
    "| a much longer first cell | x |\n"
    "\n"
    "After the table.\n"
)


def _table_widths(view: StreamView) -> tuple[Scaled, ...] | None:
    blocks = view._layout_blocks(WIDTH)
    tables = [block for block in blocks if isinstance(block, TableBlock)]
    if not tables:
        return None
    return table_columns(tables[0], view.theme, WIDTH, view.measure)


def test_a_running_maximum_of_apportioned_widths_would_overflow_the_pane(
    theme: Theme, measure: Any
) -> None:
    # The rule the plan's notes proposed, shown not to work, with its numbers.
    # Apportioned widths fill the measure at every step, so once two columns
    # have each been the wide one their maxima sum to more than the measure.
    stream = StreamDocument(theme, fontlib_metrics)
    highest: list[Scaled] = []
    for piece in pieces_of(TABLE):
        stream.append(piece)
        for block in stream.blocks:
            if isinstance(block, TableBlock) and block.rows:
                widths = table_columns(block, theme, WIDTH, measure)
                assert sum(widths) == WIDTH
                highest = [max(a, b) for a, b in zip(highest or widths, widths, strict=True)]
    assert sum(highest) > WIDTH
    assert px_from_sp(sum(highest) - WIDTH) > 100.0


def test_a_live_tables_columns_never_narrow_and_its_first_column_never_moves(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    held_steps: list[tuple[Scaled, ...]] = []
    plain_steps: list[tuple[Scaled, ...]] = []
    natural_steps: list[tuple[Scaled, ...]] = []
    first_glyph_x: set[Scaled] = set()
    plain_first_x: set[Scaled] = set()
    second_column_x: list[Scaled] = []
    plain_second_column_x: list[Scaled] = []
    for piece in pieces_of(TABLE):
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        live = [b for b in stream.live if isinstance(b, TableBlock)]
        if not live or not live[0].rows:
            continue
        widths = _table_widths(view)
        assert widths is not None
        held_steps.append(widths)
        plain_steps.append(table_columns(live[0], theme, WIDTH, measure))
        natural_steps.append(table_natural_widths(live[0], theme, measure))
        unit = next(u for u in layout.placed if isinstance(u.blocks[0], TableBlock))
        glyphs = [c for c in unit.cmds if isinstance(c, Glyph)]
        first_glyph_x.add(glyphs[0].x)
        # "value", the header of the second column: the fourth glyph on.
        assert "".join(chr(c.codepoint) for c in glyphs[:4]) == "keyv"
        second_column_x.append(glyphs[3].x)
        # The control is the same blocks laid out with nothing held: what a
        # `BareView` over the stream's document does, by the same function.
        default = layout_units(stream.blocks, theme, WIDTH, measure)
        plain_unit = next(u for u in default.placed if isinstance(u.blocks[0], TableBlock))
        plain_glyphs = [c for c in plain_unit.cmds if isinstance(c, Glyph)]
        plain_first_x.add(plain_glyphs[0].x)
        plain_second_column_x.append(plain_glyphs[3].x)
    assert len(held_steps) > 10

    # Held: no column ever narrows, the table never exceeds the measure, and
    # the widths are exactly the widest cell each column has had.
    for before, after in zip(held_steps, held_steps[1:], strict=False):
        assert all(b <= a for b, a in zip(before, after, strict=True))
    assert all(sum(widths) <= WIDTH for widths in held_steps)
    running: tuple[Scaled, ...] = natural_steps[0]
    for held, natural in zip(held_steps, natural_steps, strict=True):
        running = tuple(max(a, b) for a, b in zip(running, natural, strict=True))
        assert held == running
    assert len(first_glyph_x) == 1
    changes = sum(a != b for a, b in zip(held_steps, held_steps[1:], strict=False))
    # The second column starts where the first ends, so it moves only to the
    # right, and only when the first column grows.
    assert all(b >= a for a, b in zip(second_column_x, second_column_x[1:], strict=False))

    # The control, the default apportioning over the same steps: columns do
    # narrow, and the widths change at more steps than the held ones do.
    narrowed = sum(
        any(a < b for a, b in zip(after, before, strict=True))
        for before, after in zip(plain_steps, plain_steps[1:], strict=False)
    )
    assert narrowed >= 1
    plain_changes = sum(a != b for a, b in zip(plain_steps, plain_steps[1:], strict=False))
    assert plain_changes >= changes
    # And on the page: with nothing held, the second column's first glyph
    # moves left at some step -- the jitter -- where the held one never did.
    assert plain_first_x == first_glyph_x
    assert any(
        b < a for a, b in zip(plain_second_column_x, plain_second_column_x[1:], strict=False)
    )


@pytest.mark.parametrize("policy", list(CommitPolicy))
def test_at_commit_a_table_is_apportioned_once_or_keeps_what_it_had(
    theme: Theme, measure: Any, policy: CommitPolicy
) -> None:
    view = streamed(TABLE, theme, measure, policy=policy)
    stream = view.stream
    assert isinstance(stream.committed[0], TableBlock), "the table should have committed"
    table = stream.committed[0]
    natural = table_natural_widths(table, theme, measure)
    widths = _table_widths(view)
    laid_out = view._layout_blocks(WIDTH)[0]
    if policy is CommitPolicy.RESET:
        # Apportioned once, normally: it fills the measure, as a table in a
        # finished document does.
        assert not isinstance(laid_out, SizedTable)
        assert widths == table_columns(table, theme, WIDTH, measure)
        assert widths is not None and sum(widths) == WIDTH
    else:
        # The widths it streamed at: each column its widest cell.
        assert isinstance(laid_out, SizedTable)
        assert widths == natural
        assert widths is not None and sum(widths) < WIDTH
        # And the same object frame after frame, so its unit is found by identity.
        assert view._layout_blocks(WIDTH)[0] is laid_out


def test_a_live_table_too_wide_to_hold_is_wrapped_to_the_measure(
    theme: Theme, measure: Any
) -> None:
    wide = "| key | value |\n|---|---|\n" "| one | " + "word " * 40 + "|\n"
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append(wide)
    view.sync()
    layout = view.layout_for(WIDTH)
    (table,) = [block for block in stream.blocks if isinstance(block, TableBlock)]
    assert sum(table_natural_widths(table, theme, measure)) > WIDTH
    laid_out = view._layout_blocks(WIDTH)[-1]
    # Handed to the default apportioning, as before -- but as the widths that
    # apportioning gives, stated (AF-livetable: the plain table had every
    # cell measured and broken again for each row that arrived). So this was
    # `not isinstance(laid_out, SizedTable)`, and is now that the widths are
    # the plain table's and the commands are the plain table's.
    assert isinstance(laid_out, SizedTable)
    assert laid_out.column_widths == table_columns(table, theme, WIDTH, measure)
    assert sum(laid_out.column_widths) == WIDTH
    assert layout.cmds == layout_units((table,), theme, WIDTH, measure).cmds
    # Wrapped: far more lines than its two rows.
    assert sum(isinstance(cmd, Line) for cmd in layout.cmds) > 6


# -- 4. the selection ---------------------------------------------------------

SETTLED = (
    "Settled paragraph the reader selects words in.\n"
    "\n"
    "Live paragraph that keeps\n"
    "growing while they do, with enough words to wrap\n"
    "onto more than one line at the width the test lays it out to,\n"
    "and then some more of them so that it certainly does.\n"
)
"""
A paragraph that settles early and one that stays live for a long time.

The second is written over several source lines on purpose. A block commits
when the first *line* of the next block ends, so a live paragraph on one long
line would leave the first uncommitted until the very last character.
"""


def test_a_selection_in_settled_text_is_untouched_by_what_arrives_after_it(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    pieces = pieces_of(SETTLED)
    chosen: Selection | None = None
    later = 0
    for piece in pieces:
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        if chosen is None and stream.committed:
            view.select(Selection(8, 17))
            chosen = view.selection
            assert view.selected_text() == "paragraph"
        elif chosen is not None:
            later += 1
            assert view.selection == chosen
            assert view.selected_text() == "paragraph"
            assert layout is view.layout
    assert chosen is not None and later > 20


def test_a_selection_reaching_into_the_live_tail_survives_more_text_and_a_rebreak(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    pieces = pieces_of(SETTLED)
    words = 0
    later = 0
    selected = ""
    for piece in pieces:
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        if stream.committed and stream.live:
            words += 1
        if words == 6 and not selected:
            # From the middle of the settled paragraph to the end of what the
            # live one holds so far.
            last_glyph = max(
                unit.base + cmd.index
                for unit in layout.placed[-1:]
                for cmd in unit.unit.cmds
                if isinstance(cmd, Glyph)
            )
            view.select(Selection(8, last_glyph + 1))
            selected = view.selected_text()
            assert selected.startswith("paragraph the reader") and "Live paragraph" in selected
        elif selected:
            later += 1
            assert view.selected_text() == selected, piece
    assert selected and later > 15
    # The tail went on to wrap, so the indices under the selection were
    # renumbered at least once; the words were not.
    final = view.layout_for(WIDTH)
    assert sum(isinstance(c, Line) for c in final.placed[-1].cmds) >= 2
    # And it survives the tail committing.
    stream.close()
    view.sync()
    view.layout_for(WIDTH)
    assert view.selected_text() == selected


def test_when_markup_closes_under_a_selection_it_is_cut_back_to_the_settled_text(
    theme: Theme, measure: Any
) -> None:
    # `**bold` is two asterisks and four letters until the closing `**`
    # arrives; then the asterisks are gone and every glyph after them has
    # moved up by two. A selection ending in that paragraph no longer names
    # the characters it did.
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Settled words here.\n\nLive with **bold")
    view.sync()
    layout = view.layout_for(WIDTH)
    live = layout.placed[-1]
    assert "**bold" in layout.model.text(Selection(live.base, layout.length))

    view.select(Selection(8, layout.length))
    assert view.selected_text().startswith("words here.")
    whole_tail = Selection(live.base + 2, layout.length)

    stream.append(" text** and on.\n")
    view.sync()
    after = view.layout_for(WIDTH)
    assert "**" not in after.model.text(Selection(0, after.length))
    # Cut back to the end of the settled paragraph: the part that is still
    # exactly what was selected.
    assert view.selected_text() == "words here."

    # A selection that was wholly in the live text has nothing settled to
    # fall back to, and goes.
    stream2 = StreamDocument(theme, fontlib_metrics)
    view2 = StreamView(stream2, measure)
    stream2.append("Settled words here.\n\nLive with **bold")
    view2.sync()
    view2.layout_for(WIDTH)
    view2.select(whole_tail)
    assert not view2.selection.is_empty
    stream2.append(" text** and on.\n")
    view2.sync()
    view2.layout_for(WIDTH)
    assert view2.selection.is_empty


def test_a_selection_in_a_block_that_is_reset_on_commit_keeps_its_words(
    theme: Theme, measure: Any
) -> None:
    # The plan's notes had this selection cleared. The block's characters are
    # the same before and after it is set again, so it is carried instead.
    stream = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    view = StreamView(stream, measure)
    pieces = pieces_of(PARAGRAPH)
    for piece in pieces[:-5]:
        stream.append(piece)
    view.sync()
    layout = view.layout_for(WIDTH)
    assert not stream.committed
    view.select(Selection(5, 60))
    selected = view.selected_text()
    assert len(selected) > 40
    for piece in pieces[-5:]:
        stream.append(piece)
    view.sync()
    view.layout_for(WIDTH)
    assert len(stream.committed) == 1
    # The same words. A space at the very edge of a selection is not carried:
    # its ends are restated as glyphs, which is what does not move.
    assert view.selected_text() == selected.strip()
    assert layout is not view.layout


# -- 2. following the tail ----------------------------------------------------


def frame(
    view: BareView,
    *,
    wheel: float | None = None,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    before: Callable[[Any], None] | None = None,
    window: tuple[float, float] = (20.0, 20.0),
    width_px: float | None = None,
) -> tuple[float, float]:
    """
    One frame of the view in a scrolling child, with no display. Returns (scroll_y, scroll_max_y).

    `before` runs inside the child ahead of the view, where a host's own
    widgets and cursor moves would be; `window` is where the host put the
    window this frame.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1200.0, 800.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    if left is not None:
        io.add_mouse_button_event(0, left)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(*window))
        imgui.set_next_window_size(imgui.ImVec2(700.0, 400.0))
        imgui.begin("##advtext-stream-test", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##advtext-stream-child")
        if before is not None:
            before(imgui)
        scroll = (float(imgui.get_scroll_y()), float(imgui.get_scroll_max_y()))
        view.draw(fonts=lambda face: None, width_px=width_px)
        imgui.end_child()
        imgui.end()
    finally:
        imgui.render()
    return scroll


def fed(view: StreamView, words: int, start: int = 0) -> None:
    """
    Append `words` words, ten a frame: a fast stream, and a suite that stays quick.
    """
    for number in range(start, start + words):
        view.stream.append(f"word{number} ")
        if number % 40 == 39:
            view.stream.append("\n\n")
        if number % 10 == 9:
            frame(view)
    frame(view)


def test_the_pane_follows_the_end_while_the_reader_is_at_the_bottom(
    theme: Theme, measure: Any
) -> None:
    view = StreamView(StreamDocument(theme, fontlib_metrics), measure)
    frame(view, mouse=(300.0, 200.0))
    assert view.following
    fed(view, 600)
    frame(view)
    scroll, limit = frame(view)
    assert limit > 400.0, "the document must have outgrown the window"
    assert scroll == limit
    assert view.following


def test_scrolling_up_releases_the_pane_and_scrolling_back_down_takes_it_again(
    theme: Theme, measure: Any
) -> None:
    view = StreamView(StreamDocument(theme, fontlib_metrics), measure)
    frame(view, mouse=(300.0, 200.0))
    fed(view, 600)
    frame(view)

    # The reader wheels up.
    frame(view, wheel=3.0)
    scroll, limit = frame(view)
    assert scroll < limit - 50.0
    assert not view.following
    parked = scroll
    # Text keeps arriving and the pane stays where the reader left it.
    fed(view, 200, start=600)
    scroll, limit_now = frame(view)
    assert scroll == parked
    assert limit_now > limit
    assert not view.following

    # Back to the bottom by the wheel: following again, with nothing pressed.
    for _ in range(40):
        frame(view, wheel=-5.0)
    scroll, limit = frame(view)
    assert scroll == limit and view.following
    fed(view, 100, start=800)
    frame(view)
    scroll, limit = frame(view)
    assert scroll == limit


def test_follow_tail_goes_to_the_end_from_anywhere_and_follow_off_never_scrolls(
    theme: Theme, measure: Any
) -> None:
    view = StreamView(StreamDocument(theme, fontlib_metrics), measure)
    frame(view, mouse=(300.0, 200.0))
    fed(view, 600)
    frame(view)
    frame(view, wheel=6.0)
    scroll, limit = frame(view)
    assert scroll < limit and not view.following
    view.follow_tail()
    frame(view)
    scroll, limit = frame(view)
    assert scroll == limit and view.following

    still = StreamView(StreamDocument(theme, fontlib_metrics), measure, follow=False)
    frame(still)
    fed(still, 600)
    scroll, limit = frame(still)
    assert limit > 400.0 and scroll == 0.0
    assert not still.following


# -- the snapping hazard ------------------------------------------------------


class _Tops:
    """
    A draw list that keeps the y every glyph was placed at.
    """

    def __init__(self) -> None:
        self.flags = 0
        self.ys: list[float] = []

    def add_text(self, *args: Any) -> None:
        position = args[2] if len(args) == 5 else args[0]
        self.ys.append(float(position.y))

    def add_rect_filled(self, *args: Any) -> None:
        pass


class _Face:
    def is_glyph_in_font(self, codepoint: int) -> bool:
        return True

    def get_font_baked(self, size: float) -> Any:
        class Baked:
            pass

        baked = Baked()
        baked.size = float(int(size + 0.5))  # type: ignore[attr-defined]
        baked.ascent = baked.size * 0.75  # type: ignore[attr-defined]
        return baked


def _line_gaps(cmds: Any, origin_y: float) -> list[float]:
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    recorded = _Tops()
    draw(recorded, cmds, imgui.ImVec2(0.0, origin_y), fonts=lambda face: _Face())  # type: ignore[arg-type, return-value]
    tops: list[float] = []
    for y in recorded.ys:
        if not tops or y != tops[-1]:
            tops.append(y)
    return [b - a for a, b in zip(tops, tops[1:], strict=False)]


def test_the_gaps_between_lines_do_not_depend_on_a_whole_pixel_scroll(
    theme: Theme, measure: Any
) -> None:
    """
    The plan's snapping hazard, measured: real for a fractional origin, absent for a whole one.

    Each line's top is snapped to a pixel on its own and the body leading is
    21.6 px, so consecutive lines are 21 or 22 px apart in a fixed pattern.
    Moving the origin by a whole number of pixels moves every line by that
    number and the pattern is untouched: settled lines do not shimmer as the
    pane scrolls. Moving it by a fraction re-rounds every line and the
    pattern changes -- which is the hazard, and is why the next test exists.
    """
    text = " ".join(f"word{number}" for number in range(400)) + "\n"
    document = build_document(text, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, WIDTH, measure)
    base = _line_gaps(layout.cmds, 100.0)
    assert len(base) > 40
    assert set(base) == {21.0, 22.0}
    for whole in (101.0, 137.0, 63.0, -412.0):
        assert _line_gaps(layout.cmds, whole) == base
    differing = {
        fraction: sum(
            a != b for a, b in zip(base, _line_gaps(layout.cmds, 100.0 + fraction), strict=True)
        )
        for fraction in (0.25, 0.5, 0.75)
    }
    assert all(count > 10 for count in differing.values()), differing


def test_the_origin_imgui_hands_a_view_is_a_whole_number_of_pixels(
    theme: Theme, measure: Any
) -> None:
    """
    A measurement of ImGui kept as a tripwire: its own scroll and window positions are whole.

    What is recorded is **the cursor ImGui hands the view**, read in the
    child just before `draw` -- not `view.origin`, which the view now snaps
    and would be whole whatever ImGui did. Four things are tried, and each
    is done here rather than described: streaming with the tail followed;
    wheeling by fractions of a notch; a scroll position set by hand to a
    fraction of a pixel; and the window itself placed at (10.5, 20.25). In
    ImGui 1.92 the cursor is whole after every one.

    Nothing depends on this any more: `BareView._cursor_origin` snaps, and
    `test_a_fractional_cursor_position_sets_the_same_lines_as_a_whole_one`
    is the test of that. If this goes red, ImGui has started producing
    fractional positions by itself; the view copes, and the sentence in
    `_cursor_origin` that says it does not is what needs changing.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    view = StreamView(StreamDocument(theme, fontlib_metrics), measure)
    cursors: list[tuple[float, float]] = []
    scrolls: list[float] = []

    def record(imgui: Any) -> None:
        at = imgui.get_cursor_screen_pos()
        cursors.append((float(at.x), float(at.y)))

    def seen(**kwargs: Any) -> None:
        scrolls.append(frame(view, before=record, **kwargs)[0])

    frame(view, mouse=(300.0, 200.0))
    for number in range(400):
        view.stream.append(f"word{number} ")
        if number % 5 == 4:
            seen()
    assert view.following and scrolls[-1] > 100.0
    followed = len({y for _, y in cursors})
    for notch in (0.3, -0.7, 1.0, -0.33, 2.5):
        seen(wheel=notch)
        seen()

    # A fractional scroll set by hand. The view must not be following, or
    # its own request for the end of the pane replaces this one.
    view.follow = False
    asked: list[float] = []

    def scroll_to(value: float) -> Callable[[Any], None]:
        def hook(imgui: Any) -> None:
            imgui.set_scroll_y(value)
            asked.append(value)
            record(imgui)

        return hook

    for value in (123.4, 77.5, 200.75):
        frame(view, before=scroll_to(value))
        seen()
        assert abs(scrolls[-1] - value) < 1.0, "the scroll set by hand must have been applied"
    assert len(asked) == 3

    # The window itself at a fractional position.
    before_move = cursors[-1]
    for _ in range(3):
        seen(window=(10.5, 20.25))
    assert cursors[-1][0] != before_move[0], "the window must have moved"

    assert followed > 10, "the origin never moved while following; nothing was measured"
    assert all(x == float(int(x)) and y == float(int(y)) for x, y in cursors), cursors
    assert all(value == float(int(value)) for value in scrolls)
    # Which ImGui this was measured in, compared as numbers: "1.100" sorts
    # before "1.92" as a string.
    version = tuple(int(part) for part in imgui.get_version().split(".")[:2])
    assert version >= (1, 92), version


def test_a_column_does_not_narrow_when_markup_closing_makes_its_cell_narrower(
    theme: Theme, measure: Any
) -> None:
    # A column's natural width grows as text arrives -- except when markup
    # closes: `**wide wide wide` is three words and two asterisks until the
    # closing pair arrives and the asterisks vanish. The held width is the
    # widest the column has *been*, so the column stays put; the natural width
    # on its own would have pulled it in.
    source = "| key | value |\n|---|---|\n| **wide wide wide** | x |\n| a | b |\n"
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    held: list[Scaled] = []
    natural: list[Scaled] = []
    for piece in re.findall(r"\S\S?|\s+", source):
        stream.append(piece)
        view.sync()
        view.layout_for(WIDTH)
        tables = [block for block in stream.live if isinstance(block, TableBlock)]
        if not tables or not tables[0].rows:
            continue
        widths = _table_widths(view)
        assert widths is not None
        held.append(widths[0])
        natural.append(table_natural_widths(tables[0], theme, measure)[0])
    assert len(held) > 8
    assert any(
        b < a for a, b in zip(natural, natural[1:], strict=False)
    ), "the cell never got narrower; the fixture shows nothing"
    assert all(b >= a for a, b in zip(held, held[1:], strict=False))


# -- 6. a long code fence that is still open ----------------------------------
#
# One live block however long it gets. As one unit it was composed and shipped
# whole for every line appended; `StreamView` lays it out in pieces
# (`advtext.ui.units`, "A long code block in pieces"), and the oracle for what
# that must not change is the same blocks laid out with every block whole.


def code_line(number: int) -> str:
    return f"value_{number} = compute({number})  # {'x' * (number % 5 + 1)}\n"


def fence_view(theme: Theme, measure: Any, lines: int) -> StreamView:
    """
    A view whose stream is a paragraph and then an open fence of `lines` lines, a line a layout.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Before the code.\n\n```python\n")
    for number in range(lines):
        stream.append(code_line(number))
        view.sync()
        view.layout_for(WIDTH)
    return view


def test_a_line_added_to_an_open_fence_ships_one_piece_whatever_the_fences_length(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines_shipped: list[int] = []

    def counting(*args: Any, **kwargs: Any) -> Any:
        cmds = ship(*args, **kwargs)
        lines_shipped.append(sum(1 for cmd in cmds if isinstance(cmd, Line)))
        return cmds

    monkeypatch.setattr(units_module, "ship", counting)
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Before the code.\n\n```python\n")
    view.sync()
    view.layout_for(WIDTH)
    per_step: list[int] = []
    whole: list[int] = []
    for number in range(10 * CODE_PIECE_LINES + 3):
        # A line arrives in three pieces, as tokens do, and each is laid out.
        text = code_line(number)
        for piece in (text[:4], text[4:11], text[11:]):
            lines_shipped.clear()
            stream.append(piece)
            view.sync()
            view.layout_for(WIDTH)
            assert len(lines_shipped) <= 1, "one unit shipped per append: the last piece"
            per_step.append(sum(lines_shipped))
            whole.append(number + 1)
    # What an append costs is the last piece, and that never exceeds a piece
    # (a line begun but not ended is a line of the block too, hence the one).
    assert max(per_step) <= CODE_PIECE_LINES + 1
    # Laid out whole it would have been the fence's length each time; here it
    # is half a piece on average, and the replay as a whole ships less than a
    # fifth of the lines.
    assert sum(per_step) * 5 < sum(whole)
    code = view.layout_for(WIDTH).units_of_block(1)
    assert len(code) == 11 and [unit.part for unit in code] == list(range(11))


@pytest.mark.parametrize(
    "lines", [CODE_PIECE_LINES, CODE_PIECE_LINES + 1, 3 * CODE_PIECE_LINES, 100, 173]
)
def test_an_open_fence_in_pieces_is_what_the_fence_laid_out_whole_is(
    theme: Theme, measure: Any, lines: int
) -> None:
    view = fence_view(theme, measure, lines)
    layout = view.layout_for(WIDTH)
    blocks = view.stream.document.blocks
    whole = layout_units(blocks, theme, WIDTH, measure)
    assert len(whole.placed) == 2
    assert len(layout.placed) == 1 + -(-lines // CODE_PIECE_LINES)

    # Drawn output and selection indices: the same commands.
    assert layout.cmds == whole.cmds
    assert (layout.height, layout.length) == (whole.height, whole.length)
    # Copy text, hard line breaks included.
    everything = Selection(0, layout.length)
    copied = layout.model.copy_text(everything)
    assert copied == whole.model.copy_text(everything)
    body = "".join(code_line(number) for number in range(lines))
    assert copied == "Before the code.\n\n" + body.rstrip("\n")
    assert view.block_text(1) == body.rstrip("\n")
    # A selection that starts and ends inside the fence, across pieces.
    own = layout.indices_of_block(1)
    inside = Selection(own.start + 7, own.stop - 9)
    assert layout.model.copy_text(inside) == whole.model.copy_text(inside)
    assert layout.model.rects(inside) == whole.model.rects(inside)

    # One block to a hit test, at every line of it; one block to a selection.
    for y in range(0, layout.height, sp_from_px(3.0)):
        assert layout.block_at(Point(0, y)) == whole.block_at(Point(0, y))
    assert {layout.block_at(Point(0, unit.y + 1)) for unit in layout.units_of_block(1)} == {1}
    view.select(everything)
    assert view.selected_blocks() == (0, 1)
    # The source map is the document's and names the fence once.
    source = view.stream.source
    assert view.block_source(1, source) == "```python\n" + body
    assert view.selected_source(source) == source


def test_a_fence_keeps_its_pieces_when_it_closes_and_nothing_settled_is_rebuilt(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = fence_view(theme, measure, 3 * CODE_PIECE_LINES + 5)
    before = view.layout_for(WIDTH).units_of_block(1)
    shipped = _Counter(ship)
    monkeypatch.setattr(units_module, "ship", shipped)
    view.stream.append("```\n\nAnd a paragraph after it.\n\nAnother.\n")
    assert view.sync()
    layout = view.layout_for(WIDTH)
    assert len(view.stream.committed) >= 2, "the fence must have committed"
    after = layout.units_of_block(1)
    assert len(after) == len(before) == 4
    # The same placed units, not merely equal ones: nothing moved, nothing
    # was shipped for the fence, and its commands are the tuples they were.
    assert all(new is old for new, old in zip(after, before, strict=True))
    assert shipped.calls == 2, "the two paragraphs after the fence, and no piece of it"
    assert layout.cmds == layout_units(view.stream.document.blocks, theme, WIDTH, measure).cmds


def test_a_selection_in_an_open_fence_survives_the_fence_growing(
    theme: Theme, measure: Any
) -> None:
    view = fence_view(theme, measure, 2 * CODE_PIECE_LINES + 3)
    layout = view.layout_for(WIDTH)
    code = layout.units_of_block(1)
    # From the first piece into the live one.
    selection = Selection(code[0].base + 4, code[2].base + 10)
    view.select(selection)
    text = layout.model.copy_text(selection)
    for number in range(2 * CODE_PIECE_LINES + 3, 4 * CODE_PIECE_LINES + 1):
        view.stream.append(code_line(number))
        view.sync()
        layout = view.layout_for(WIDTH)
        assert view.selection == selection
        assert layout.model.copy_text(view.selection) == text


def test_colour_spans_on_a_fence_in_pieces_colour_what_they_colour_on_the_whole_block(
    theme: Theme, measure: Any
) -> None:
    # Syntax colouring is what a host does to exactly these blocks. The spans
    # are in the block's coordinates; each piece is mapped from its own zero.
    from advtext.backends.imgui_draw import Palette
    from advtext.markdown import CodeBlock
    from advtext.spans import ColourSpan, code_position
    from advtext.ui import Viewport

    lines = 3 * CODE_PIECE_LINES + 5
    view = fence_view(theme, measure, lines)
    document = view.stream.document
    block = document.blocks[1]
    assert isinstance(block, CodeBlock)
    keyword, comment, found = 0xFF0000C1, 0xFF00C100, 0x40C10000
    spans = [
        ColourSpan(code_position(block, n, 0), code_position(block, n, 5), ink=keyword)
        for n in range(0, lines, 3)
    ]
    # One span across two piece boundaries, and a mark across one.
    spans.append(
        ColourSpan(
            code_position(block, CODE_PIECE_LINES - 2, 8),
            code_position(block, 2 * CODE_PIECE_LINES + 1, 4),
            ink=comment,
        )
    )
    spans.append(
        ColourSpan(
            code_position(block, 2 * CODE_PIECE_LINES - 1, 2),
            code_position(block, 2 * CODE_PIECE_LINES, 9),
            mark=found,
        )
    )
    whole_view = BareView(document=document, theme=theme, measure=measure)
    palette = Palette()

    def decorated(some: BareView) -> tuple[dict[int, int], list[Any], int]:
        some.set_colours(1, spans)
        layout = some.layout_for(WIDTH)
        visible = list(layout.visible_units(Viewport(0, layout.height)))
        inks, fills = some._decorate(visible, palette)
        by_index = {index: ink for start, end, ink in inks for index in range(start, end)}
        assert sum(end - start for start, end, _ in inks) == len(by_index), "ink ranges overlap"
        assert inks == sorted(inks)
        return by_index, sorted(fills, key=repr), len(layout.placed)

    pieced_inks, pieced_fills, pieced_units = decorated(view)
    whole_inks, whole_fills, whole_units = decorated(whole_view)
    assert (pieced_units, whole_units) == (5, 2)
    assert pieced_inks == whole_inks and len(set(whole_inks.values())) == 2
    assert pieced_fills == whole_fills and len(whole_fills) == 2
    assert view.unmapped_blocks == 0
    # A frame on which nothing changed cuts no spans again: each piece is
    # handed the tuple it was handed before.
    layout = view.layout_for(WIDTH)
    visible = list(layout.visible_units(Viewport(0, layout.height)))
    first = [view._spans_for(unit, 1, view._pieced) for unit in layout.units_of_block(1)]
    view._decorate(visible, palette)
    again = [view._spans_for(unit, 1, view._pieced) for unit in layout.units_of_block(1)]
    assert all(a is b for a, b in zip(first, again, strict=True))


def test_the_cost_of_a_line_does_not_grow_with_the_length_of_the_fence(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The scaling, as counts: the lines composed and shipped for a line appended early and late.

    Two windows of one open fence, each two whole pieces long, so both see
    every size of last piece the same number of times. In pieces, what a new
    line costs is the last piece wherever in the fence it is, and the two
    windows ship **the same number of lines**. Laid out whole -- the control,
    the same view with pieces turned off -- every line ships the fence so
    far, and the late window ships about six times the early one (the fence
    is 48 and 304 lines long at the windows' middles).

    This was a ratio of two median times with a bound of three, and its
    control asserted a *lower* bound on a ratio of times: both true on a
    quiet machine and neither a fact about the code on a busy one (review 5,
    item 5). A unit is composed and shipped in one step
    (`advtext.ui.units.UnitCache._unit`), so the lines shipped are the lines
    composed, and those two are where the time went. The clock is still
    there, below, for whoever asks for it.
    """
    early, late = _fence_lines_shipped(theme, measure, StreamView, monkeypatch)
    assert early == late == 2 * sum(range(1, CODE_PIECE_LINES + 1)), (early, late)

    class Whole(StreamView):
        _CODE_LINES = 0

    early, late = _fence_lines_shipped(theme, measure, Whole, monkeypatch)
    # Lines 33 to 64 and 289 to 320 of the fence, each laid out whole.
    assert (early, late) == (sum(range(33, 65)), sum(range(289, 321)))
    assert late > 6 * early


def _fence_lines_shipped(
    theme: Theme, measure: Any, kind: type[StreamView], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int]:
    """
    Code lines shipped while lines 32-64, and then 288-320, of one open fence arrive.

    The paragraph before the fence is settled and ships nothing; every `Line`
    counted is a line of the code block.
    """
    shipped = [0]

    def counting(*args: Any, **kwargs: Any) -> Any:
        cmds = ship(*args, **kwargs)
        shipped[0] += sum(1 for cmd in cmds if isinstance(cmd, Line))
        return cmds

    monkeypatch.setattr(units_module, "ship", counting)
    stream = StreamDocument(theme, fontlib_metrics)
    view = kind(stream, measure)
    stream.append("Before the code.\n\n```python\n")
    view.sync()
    view.layout_for(WIDTH)
    per_line: list[int] = []
    for number in range(320):
        shipped[0] = 0
        stream.append(f"v{number} = {number}\n")
        view.sync()
        view.layout_for(WIDTH)
        per_line.append(shipped[0])
    assert 32 % CODE_PIECE_LINES == 0
    return sum(per_line[32:64]), sum(per_line[288:320])


@pytest.mark.skipif(
    os.environ.get("ADVTEXT_SLOW") != "1",
    reason="a ratio of two clock readings, which a loaded machine can fail either way; "
    "the count test above holds the claim. Set ADVTEXT_SLOW=1 to run it.",
)
def test_on_a_clock_a_line_costs_the_same_late_in_a_fence_as_early_and_whole_it_does_not(
    theme: Theme, measure: Any
) -> None:
    """
    The same claim in seconds, and its control, for a run that wants to see milliseconds.

    Per appended line -- the stream's parse, the view's sync and the layout --
    as a median over each of the two windows. In pieces the ratio is about
    one; laid out whole it is about six. Three is the bound on both sides.
    Run with `ADVTEXT_SLOW=1` when this was written: it passed.
    """
    early, late = _fence_line_costs(theme, measure, StreamView)
    assert late < 3.0 * early, (early, late)

    class Whole(StreamView):
        _CODE_LINES = 0

    early, late = _fence_line_costs(theme, measure, Whole)
    assert late > 3.0 * early, (early, late)


def _fence_line_costs(theme: Theme, measure: Any, kind: type[StreamView]) -> tuple[float, float]:
    """
    Median seconds per appended line, for lines 32-64 and 288-320 of one open fence.

    Short enough that the control, which lays the fence out whole 320 times,
    takes a couple of seconds.
    """
    import statistics
    import time

    stream = StreamDocument(theme, fontlib_metrics)
    view = kind(stream, measure)
    stream.append("Before the code.\n\n```python\n")
    costs: list[float] = []
    for number in range(320):
        began = time.perf_counter()
        stream.append(f"v{number} = {number}\n")
        view.sync()
        view.layout_for(WIDTH)
        costs.append(time.perf_counter() - began)
    assert 32 % CODE_PIECE_LINES == 0
    return statistics.median(costs[32:64]), statistics.median(costs[288:320])


def test_a_fence_in_pieces_is_drawn_and_pointed_at_in_real_frames(
    theme: Theme, measure: Any
) -> None:
    # Real ImGui frames, no display: the view draws several units for one
    # block, follows the tail as the fence grows, and a mouse over any piece
    # is over the one block.
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Before the code.\n\n```python\n")
    frame(view)
    for number in range(5 * CODE_PIECE_LINES + 2):
        stream.append(code_line(number))
        if number % 7 == 0:
            frame(view)
    frame(view)
    scroll, most = frame(view)
    assert most > 0 and scroll == most and view.following
    layout = view.layout
    assert layout is not None and len(layout.units_of_block(1)) == 6
    origin = view.origin
    assert origin is not None
    over: set[int | None] = set()
    for unit in layout.units_of_block(1)[-2:]:
        y = origin[1] + px_from_sp(unit.y, view.px_per_inch) + 3.0
        frame(view, mouse=(origin[0] + 40.0, y))
        over.add(view.block_under_mouse())
        assert view.under_mouse().block == 1
    assert over == {1}


# -- review 4 -------------------------------------------------------------------

LATE_ROW = (
    "| k | v |\n|---|---|\n| a | b |\n",
    "| alpha beta gamma delta | epsilon zeta eta theta |\n\nAfter the table.\n",
)
"""
A table in two bursts: its first row, then a much wider row together with the block after it.

The second burst is what review 4's first snippet found: the table's last row
and its commit arrive in one sync, so there is no layout at which the table is
live *and* has its last row.
"""


def _arrived(theme: Theme, measure: Any, bursts: list[str]) -> StreamView:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    for burst in bursts:
        stream.append(burst)
        view.sync()
        view.layout_for(WIDTH)
    return view


def _table_glyphs(view: StreamView) -> list[tuple[int, Scaled, Scaled]]:
    unit = view.layout_for(WIDTH).placed[0]
    assert isinstance(unit.blocks[0], TableBlock)
    return [(c.codepoint, c.x, c.y) for c in unit.cmds if isinstance(c, Glyph)]


def test_a_table_whose_last_row_arrives_with_its_commit_is_measured_at_the_commit(
    theme: Theme, measure: Any
) -> None:
    # Review 4, item 1, measured before the fix: columns of 25 and 25 px and
    # ten lines, where the same table fed a word at a time gets 188 and 168
    # px and three. The held widths were refreshed only at a layout that saw
    # the table live, and at commit the previous layout's went to `_kept` for
    # good -- here the widths of `| a | b |`.
    view = _arrived(theme, measure, list(LATE_ROW))
    table = view.stream.committed[0]
    assert isinstance(table, TableBlock) and len(table.rows) == 2
    natural = table_natural_widths(table, theme, measure)
    assert sum(natural) < WIDTH, "fixture: the table must fit at its natural widths"
    assert _table_widths(view) == natural
    lines = [cmd for cmd in view.layout_for(WIDTH).placed[0].cmds if isinstance(cmd, Line)]
    assert len(view.layout_for(WIDTH).placed[0].model.fragments) == 3, lines


def test_under_keep_streamed_a_committed_table_is_set_the_same_however_it_arrived(
    theme: Theme, measure: Any
) -> None:
    # The same document ended in different layouts depending on how the
    # stream happened to be cut: a word at a time the table was held at its
    # natural widths, and in one burst it was never live at a layout, so it
    # was never held and got the default apportioning, filling the measure.
    # Now a table that commits under KEEP_STREAMED is measured at its commit
    # whether or not it was ever seen live.
    source = "".join(LATE_ROW)
    arrivals = {
        "a word at a time": pieces_of(source),
        "two bursts": list(LATE_ROW),
        "one burst": [source],
        "a character at a time": list(source),
    }
    glyphs = {
        name: _table_glyphs(_arrived(theme, measure, bursts)) for name, bursts in arrivals.items()
    }
    assert len(glyphs["one burst"]) > 40
    for name, found in glyphs.items():
        assert found == glyphs["a word at a time"], name
    # A view made over a stream that had already finished is the same again.
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append(source)
    stream.close()
    late = StreamView(stream, measure)
    assert _table_glyphs(late) == glyphs["a word at a time"]
    # Under RESET none of this applies: apportioned once, to the measure.
    reset = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    reset.append(source)
    view = StreamView(reset, measure)
    widths = _table_widths(view)
    assert widths is not None and sum(widths) == WIDTH


def test_a_live_table_with_an_empty_column_and_no_cell_padding_is_laid_out_not_raised(
    theme: Theme, measure: Any
) -> None:
    # Review 4, item 6. A column whose every cell is empty has a natural
    # width of zero when the theme pads cells by nothing, and `with_columns`
    # refuses a width under one scaled point: `ValueError` out of `draw`,
    # every frame, for a table the plain path lays out.
    bare = replace(theme, cell_padding=0)
    source = "| a |  |\n|---|---|\n| b |  |\n"
    plain = build_document(source, bare, fontlib_metrics)
    assert table_natural_widths(plain.blocks[0], bare, measure)[1] == 0  # type: ignore[arg-type]
    assert len(layout_units(plain.blocks, bare, WIDTH, measure).placed) == 1, "the control"

    stream = StreamDocument(bare, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append(source)
    view.sync()
    layout = view.layout_for(WIDTH)
    assert [chr(c.codepoint) for c in layout.cmds if isinstance(c, Glyph)] == ["a", "b"]
    first_x = [c.x for c in layout.cmds if isinstance(c, Glyph)]
    # Held, like any live table: the first column at its natural width and
    # the empty one at a single scaled point, not handed back to the default
    # apportioning (which would give the empty column half the pane).
    laid_out = view._layout_blocks(WIDTH)[0]
    assert isinstance(laid_out, SizedTable)
    natural = table_natural_widths(plain.blocks[0], bare, measure)  # type: ignore[arg-type]
    assert _table_widths(view) == (natural[0], 1)
    frame(view)

    # The empty column then gets text: held like any other, and the first
    # column's glyphs are where they were.
    stream.append("| c | words |\n")
    view.sync()
    layout = view.layout_for(WIDTH)
    glyphs = [c for c in layout.cmds if isinstance(c, Glyph)]
    assert "".join(chr(c.codepoint) for c in glyphs) == "abcwords"
    assert [c.x for c in glyphs[:2]] == first_x
    # And it commits, under the default policy, without raising either.
    stream.append("\nAfter.\n")
    view.sync()
    view.layout_for(WIDTH)
    assert isinstance(stream.committed[0], TableBlock)
    frame(view)


def test_a_drag_in_a_block_that_is_set_again_at_commit_keeps_its_anchor_on_the_same_words(
    theme: Theme, measure: Any
) -> None:
    # Review 4, item 4, in the case it was found in: a drag in progress in
    # the live paragraph when it commits under RESET. The paragraph is set
    # again, justified; the anchor was a point, the point was now other
    # words, and the selection's fixed end moved from "thing" to "that".
    stream = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    view = StreamView(stream, measure, follow=False)
    pieces = pieces_of(PARAGRAPH)
    stream.append("".join(pieces[:-5]))
    frame(view, mouse=(1190.0, 790.0), left=False, width_px=420.0)
    frame(view, mouse=(1190.0, 790.0), width_px=420.0)
    assert view.origin is not None
    press = (view.origin[0] + 200.0, view.origin[1] + 50.0)
    drag = (press[0] + 100.0, press[1])
    frame(view, mouse=press, width_px=420.0)
    frame(view, mouse=press, left=True, width_px=420.0)
    frame(view, mouse=drag, width_px=420.0)
    frame(view, mouse=drag, width_px=420.0)
    before = view.selected_text()
    live = _first_block_glyphs_at(view)
    assert len(before.strip()) > 8 and view._dragging and not stream.committed

    stream.append("".join(pieces[-5:]))
    frame(view, mouse=drag, width_px=420.0)
    assert len(stream.committed) == 1
    assert _first_block_glyphs_at(view) != live, "fixture: the commit must move the glyphs"
    assert view._dragging
    # The moving end is wherever the mouse is; pull it below everything, so
    # the selection runs from the anchor to the end of the text.
    below = (drag[0], drag[1] + 300.0)
    frame(view, mouse=below, width_px=420.0)
    frame(view, mouse=below, width_px=420.0)
    after = view.selected_text()
    assert after.startswith(before.strip()[:8]), (before, after)
    assert after.endswith("Next block starts here.")
    frame(view, left=False, width_px=420.0)
    assert not view._dragging


def _first_block_glyphs_at(view: StreamView) -> list[tuple[int, Scaled, Scaled]]:
    layout = view.layout
    assert layout is not None
    return [(c.codepoint, c.x, c.y) for c in layout.placed[0].cmds if isinstance(c, Glyph)]


def test_a_block_that_changes_and_commits_in_one_sync_cuts_the_selection_back_not_away(
    theme: Theme, measure: Any
) -> None:
    # Read by review 4, not run by it; run here, and real. The clamp looked
    # for where the live tail began using the number of blocks committed
    # *now*. When the block under the selection's end both changed its text
    # and committed between two layouts, that put the boundary after the
    # changed block, nothing could be carried, and the whole selection was
    # cleared -- where the docstring says it is cut back to the text that is
    # still what it was, as it is when the same block changes without
    # committing (`test_when_markup_closes_under_a_selection...`).
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Settled words here.\n\nLive with **bold")
    view.sync()
    layout = view.layout_for(WIDTH)
    view.select(Selection(8, layout.length))
    assert view.selected_text().startswith("words here.") and "**bold" in view.selected_text()

    stream.append(" text** and on.\n\nA third block.\n")
    view.sync()
    after = view.layout_for(WIDTH)
    assert len(stream.committed) == 2, "the block must have committed in the same sync"
    assert "**" not in after.model.text(Selection(0, after.length))
    assert view.selected_text() == "words here."


def test_the_selection_can_be_read_between_a_sync_and_the_layout_that_follows_it(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append("Settled words here.\n\nLive words")
    view.sync()
    view.layout_for(WIDTH)
    view.select(Selection(8, 13))
    assert view.selected_text() == "words"
    stream.append(" and more of them")
    assert view.sync() and view.layout is None
    assert view.selected_text() == "words"
    assert view.selected_blocks() == (0,)
    view.layout_for(WIDTH)
    assert view.selected_text() == "words"


def test_a_fractional_cursor_position_sets_the_same_lines_as_a_whole_one(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The view snaps its origin, so a host's fractional cursor does not re-round the lines.

    ImGui's own positions are whole (the tripwire below), but a host's
    `set_cursor_pos` is not ImGui's own: measured before the view snapped,
    a cursor moved by (0.5, 0.25) reached the backend as an origin of
    (28.5, -1509.75). The origin the backend is handed is recorded here, and
    the line gaps it gives are computed the way the backend computes them.
    """
    text = " ".join(f"word{number}" for number in range(400)) + "\n"
    document = build_document(text, theme, fontlib_metrics)
    view = BareView(document=document, theme=theme, measure=measure)
    handed: list[tuple[float, float]] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **given: Any) -> Any:
        handed.append((float(origin.x), float(origin.y)))
        return real(draw_list, runs, origin, **given)

    monkeypatch.setattr(bare_module, "draw_runs", spy)

    def nudged(dx: float, dy: float) -> Callable[[Any], None]:
        def move(imgui: Any) -> None:
            at = imgui.get_cursor_screen_pos()
            imgui.set_cursor_screen_pos(imgui.ImVec2(at.x + dx, at.y + dy))

        return move

    frame(view)
    frame(view, before=nudged(0.0, 0.0))
    whole = handed[-1]
    layout = view.layout
    assert layout is not None
    base = _line_gaps(layout.cmds, whole[1])
    assert len(base) > 30 and set(base) == {21.0, 22.0}
    for dx, dy in ((0.25, 0.25), (0.5, 0.75), (0.75, 0.5), (0.3, 0.4), (-0.25, -0.4)):
        frame(view, before=nudged(dx, dy))
        x, y = handed[-1]
        assert (x, y) == (float(int(x)), float(int(y))), "the origin handed on is whole"
        assert abs(x - (whole[0] + dx)) <= 0.5 and abs(y - (whole[1] + dy)) <= 0.5
        assert view.origin == (x, y), "and it is the one hit testing uses"
        assert _line_gaps(layout.cmds, y) == base
        # The control: the same cursor, not snapped, re-rounds the lines.
        if dy in (0.25, 0.75, 0.5):
            unsnapped = _line_gaps(layout.cmds, whole[1] + dy)
            assert sum(a != b for a, b in zip(base, unsnapped, strict=True)) > 10


def test_on_the_demo_stream_a_set_line_moves_only_for_a_cause_read_off_the_layouts(
    theme: Theme, measure: Any
) -> None:
    """
    `demo/stream.md` a word at a time, kept as streamed: which set lines move, and why.

    A stronger form of a test in `tests/test_example_stream.py`, whose
    "cause" is whether the piece that arrived contains an asterisk, a
    backtick or a bar -- true of most pieces of that document whether or not
    they moved anything. Here the cause is read from the two layouts:

    - **never** a line of a block that had committed by the earlier layout;
    - *text*: the characters of the line's block, up to the end of the
      line, are not what the block now begins with -- markup that closed;
    - *table*: the block is a table, whose columns widen as cells arrive;
    - *pushed*: the line is intact, glyph for glyph and x for x, on another
      baseline, and a line above it in the live tail moved for one of the
      first two causes or was the one being written.

    The line being written -- the last of the document -- is not a set line.
    Anything else is unexplained and fails. First-fit breaking is why there
    is nothing else: a line that is full does not change when words are
    added after it.
    """
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    earlier: tuple[Any, ...] = ()
    settled_earlier = 0
    was_table: set[int] = set()
    causes: dict[str, int] = {"text": 0, "table": 0, "pushed": 0}
    compared = 0
    committed_lines: tuple[Any, ...] = ()
    for piece in pieces_of(source):
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        # Only the blocks that were live at the earlier layout are asked for.
        now = view.set_lines(settled_earlier)
        present = set(now)
        assert all(line.block >= settled_earlier for line in now)
        text_now: dict[int, list[int]] = {}
        for line in now:
            text_now.setdefault(line.block, []).extend(code for code, _ in line.glyphs)
        intact = {(line.block, line.glyphs) for line in now}
        tables = {
            number
            for number, block in enumerate(stream.blocks)
            if number >= settled_earlier and isinstance(block, TableBlock)
        }
        text_before: dict[int, list[int]] = {}
        disturbed = False
        for position, line in enumerate(earlier):
            so_far = text_before.setdefault(line.block, [])
            so_far.extend(code for code, _ in line.glyphs)
            if position == len(earlier) - 1:
                break  # the line being written
            compared += 1
            if line in present:
                continue
            if line.block in tables or line.block in was_table:
                causes["table"] += 1
                disturbed = True
            elif text_now.get(line.block, [])[: len(so_far)] != so_far:
                causes["text"] += 1
                disturbed = True
            elif (line.block, line.glyphs) in intact and disturbed:
                causes["pushed"] += 1
            else:
                raise AssertionError(
                    f"a set line of block {line.block} moved with no cause, at {piece!r}: "
                    f"{''.join(chr(code) for code, _ in line.glyphs)!r}"
                )
        # A block that had committed by the earlier layout: its lines are
        # where they were. All of them, asked the whole-document way.
        assert view.set_lines(0, settled_earlier) == committed_lines
        settled_earlier = len(stream.committed)
        committed_lines = view.set_lines(0, settled_earlier)
        was_table = tables
        earlier = view.set_lines(settled_earlier)
        assert layout is view.layout
    assert compared > 1000
    assert causes["text"] >= 1 and causes["table"] >= 1, causes


@pytest.mark.parametrize("policy", list(CommitPolicy))
def test_the_lines_of_a_block_that_had_committed_by_the_last_layout_are_where_they_were(
    theme: Theme, measure: Any, policy: CommitPolicy
) -> None:
    # What `BareView.set_lines` tells a caller it may rely on to ask for the
    # tail only: under either policy, once a layout has been built with a
    # block committed, that block's lines do not move at this width. (Under
    # RESET a block is set again *at* its commit, which is before the first
    # layout that has it committed.) Asked the whole-document way, every step.
    source = (ROOT / "demo" / "stream.md").read_text(encoding="utf-8")
    stream = StreamDocument(theme, fontlib_metrics, policy=policy)
    view = StreamView(stream, measure)
    settled = 0
    held: tuple[Any, ...] = ()
    for piece in pieces_of(source):
        stream.append(piece)
        view.sync()
        view.layout_for(WIDTH)
        assert view.set_lines(0, settled) == held
        settled = len(stream.committed)
        held = view.set_lines(0, settled)
    assert settled > 15 and len(held) > 40


def test_set_lines_of_a_fence_in_pieces_are_the_fences_lines_and_index_nothing(
    theme: Theme, measure: Any
) -> None:
    lines = 3 * CODE_PIECE_LINES + 5
    view = fence_view(theme, measure, lines)
    layout = view.layout_for(WIDTH)
    assert len(layout.units_of_block(1)) == 4
    found = view.set_lines(1)
    assert not any(unit._placement._model is not None for unit in layout.placed)
    assert [line.block for line in found] == [1] * lines
    assert ["".join(chr(code) for code, _ in line.glyphs) for line in found] == [
        code_line(number).rstrip("\n") for number in range(lines)
    ]
    baselines = [line.baseline for line in found]
    assert baselines == sorted(baselines) and len(set(baselines)) == lines
    whole = layout_units(view.stream.document.blocks, theme, WIDTH, measure)
    assert baselines == [
        fragment.line.y for fragment in whole.placed[1].model.fragments if fragment.items
    ]
    assert view.set_lines() == view.set_lines(0, 1) + found


def test_a_drag_begun_on_the_white_beside_settled_text_survives_every_token(
    theme: Theme, measure: Any
) -> None:
    # Review 5, item 1, as a streaming host meets it: the button goes down
    # right of a committed paragraph's last line and text keeps arriving in
    # a list item below. The caret has the paragraph's fill before it and the
    # item's indent after it -- glue on both sides -- and each piece is a
    # relayout: the first one used to end the drag with the button still down.
    # (With a *paragraph* below, the caret is beside that paragraph's first
    # glyph and was always carried; the fixture needs the list.)
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure, follow=False)
    stream.append("Settled.\n\n- the live\n  item")
    frame(view, mouse=(1190.0, 790.0), left=False, width_px=420.0)
    frame(view, mouse=(1190.0, 790.0), width_px=420.0)
    assert view.origin is not None and len(stream.committed) == 1
    press = (view.origin[0] + 380.0, view.origin[1] + 8.0)
    frame(view, mouse=press, width_px=420.0)
    frame(view, mouse=press, left=True, width_px=420.0)
    assert view._dragging and view.selection.is_empty
    for piece in (" gains", " a", " few", " words", " while", " the", " button", " is", " down."):
        before = view.relayouts
        stream.append(piece)
        frame(view, mouse=press, width_px=420.0)
        assert view.relayouts == before + 1, "fixture: each piece must be a relayout"
        assert view._dragging, f"the drag ended when {piece!r} arrived"
    below = (press[0], press[1] + 300.0)
    frame(view, mouse=below, width_px=420.0)
    frame(view, mouse=below, width_px=420.0)
    assert (
        view.selected_text()
        .strip()
        .endswith("the live item gains a few words while the button is down.")
    )
    assert "Settled" not in view.selected_text()
    frame(view, left=False, width_px=420.0)
    assert not view._dragging


# -- AF-livetable: a long live table is laid out in pieces ------------------------

TABLE_OPENS = "Before the table.\n\n| name | value | note |\n|:--|--:|---|\n"


def steady_row(number: int) -> str:
    """
    A row whose cells are as wide as every other row's: no column's widest cell changes.
    """
    return f"| item {100 + number} | {1000 + number * 7} | a few words about row {100 + number} |\n"


def varied_row(number: int) -> str:
    """
    A row as a model writes them: lengths vary, some cells are empty, some hold a link.
    """
    name = "" if number % 11 == 5 else f"item {number}"
    value = f"{number * 37 % 1000}.{number % 100:02d}"
    words = ("a note", "a longer note about this row", "ok", "see [the docs](https://e.x/%d)", "")
    note = words[number % 5] % number if "%d" in words[number % 5] else words[number % 5]
    if number in (7, 8, 16, 23):
        note = "one of the long ones, with enough words in the cell that it will wrap when narrow"
    return f"| {name} | {value} | {note} |\n"


class _WholeTables(StreamView):
    """
    The control: the same view with tables laid out whole, as they were before pieces.
    """

    _TABLE_ROWS = 0


def _everything(view: StreamView) -> Selection:
    assert view.layout is not None
    return Selection(0, view.layout.length)


@pytest.mark.parametrize(
    ("width_px", "policy"),
    [
        (560.0, CommitPolicy.KEEP_STREAMED),
        (300.0, CommitPolicy.KEEP_STREAMED),
        (170.0, CommitPolicy.KEEP_STREAMED),
        (300.0, CommitPolicy.RESET),
    ],
)
def test_a_table_laid_out_in_pieces_as_it_streams_is_the_table_laid_out_whole(
    theme: Theme, measure: Any, width_px: float, policy: CommitPolicy
) -> None:
    """
    The gate: at every layout of a table arriving a word at a time, pieces and whole agree.

    Two views over one stream, laid out after every piece: `StreamView`, which
    cuts a long table into pieces, and the same view with the cut turned off.
    Compared: the commands (so every position and every index), the text a
    copy gives, and the block under a sweep of points. At 560 px the table
    is held at its natural widths; at 300 it does not fit and is wrapped to
    the measure; at 170 the longest words do not fit either. Then the table
    commits and the comparison is made again -- and against a layout of the
    committed document from nothing. The policy only matters at the commit,
    so `RESET` is run at one width.
    """
    width = sp_from_px(width_px)
    stream = StreamDocument(theme, fontlib_metrics, policy=policy)
    pieced, whole = StreamView(stream, measure), _WholeTables(stream, measure)
    stream.append(TABLE_OPENS)
    compared = widened = 0
    widths: tuple[Scaled, ...] | None = None
    for number in range(21):
        for piece in pieces_of(varied_row(number)):
            stream.append(piece)
            pieced.sync()
            whole.sync()
            mine, theirs = pieced.layout_for(width), whole.layout_for(width)
            assert mine.cmds == theirs.cmds, (number, piece)
            assert (mine.height, mine.length) == (theirs.height, theirs.length)
            compared += 1
            table = pieced._layout_blocks(width)[1]
            now = table.column_widths if isinstance(table, SizedTable) else None
            widened += now != widths
            widths = now
        if number % 6 == 5:
            assert pieced.selected_text() == whole.selected_text() == ""
            copied = pieced.layout_for(width).model.copy_text(_everything(pieced))
            assert copied == whole.layout_for(width).model.copy_text(_everything(whole))
            for y in range(0, mine.height, sp_from_px(9.0)):
                assert mine.block_at(Point(0, y)) == theirs.block_at(Point(0, y))
    assert compared > 100 and 1 < widened < compared
    in_pieces = -(-21 // TABLE_PIECE_ROWS)
    assert in_pieces >= 3 and len(pieced.layout_for(width).units_of_block(1)) == in_pieces
    assert len(whole.layout_for(width).units_of_block(1)) == 1

    stream.append("\nAfter the table.\n\nAnd more.\n")
    pieced.sync()
    whole.sync()
    mine, theirs = pieced.layout_for(width), whole.layout_for(width)
    assert isinstance(stream.committed[1], TableBlock) and len(stream.committed[1].rows) == 21
    assert len(mine.units_of_block(1)) == in_pieces
    assert mine.cmds == theirs.cmds
    assert mine.model.copy_text(_everything(pieced)) == theirs.model.copy_text(_everything(whole))
    # From nothing, with no cache and no pieces: the blocks the view lays out.
    assert mine.cmds == layout_units(pieced._layout_blocks(width), theme, width, measure).cmds
    if policy is CommitPolicy.RESET:
        # Apportioned once, normally: the plain document's layout.
        assert mine.cmds == layout_units(stream.blocks, theme, width, measure).cmds


def _table_work(
    theme: Theme,
    measure: Any,
    kind: type[StreamView],
    monkeypatch: pytest.MonkeyPatch,
    width: Scaled,
    windows: tuple[range, range],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """
    For each window of appended rows: lines shipped, cells measured, cells broken for a floor.

    One row an append, each laid out. The three counts are where the time of
    a table's layout goes: composing and shipping rows (one `ship` per unit;
    its `Line`s are counted), `hpack` of each cell for its natural width,
    and a line break of each cell for its longest word when the table does
    not fit.
    """
    import advtext.ui as ui_module

    counts = [0, 0, 0]
    real_natural, real_longest = ui_module._natural_widths, ui_module._longest_word

    def shipping(*args: Any, **kwargs: Any) -> Any:
        cmds = ship(*args, **kwargs)
        counts[0] += sum(1 for cmd in cmds if isinstance(cmd, Line))
        return cmds

    def measuring(rows: Any, *args: Any, **kwargs: Any) -> Any:
        counts[1] += sum(len(row) for row in rows)
        return real_natural(rows, *args, **kwargs)

    def flooring(*args: Any, **kwargs: Any) -> Any:
        counts[2] += 1
        return real_longest(*args, **kwargs)

    monkeypatch.setattr(units_module, "ship", shipping)
    monkeypatch.setattr(ui_module, "_natural_widths", measuring)
    monkeypatch.setattr(ui_module, "_longest_word", flooring)
    stream = StreamDocument(theme, fontlib_metrics)
    view = kind(stream, measure)
    stream.append(TABLE_OPENS)
    view.sync()
    view.layout_for(width)
    per_row: list[tuple[int, int, int]] = []
    for number in range(windows[1].stop):
        counts[:] = [0, 0, 0]
        stream.append(steady_row(number))
        view.sync()
        view.layout_for(width)
        per_row.append((counts[0], counts[1], counts[2]))
    early, late = (
        tuple(sum(row[k] for row in per_row[window.start : window.stop]) for k in range(3))
        for window in windows
    )
    return early, late  # type: ignore[return-value]


@pytest.mark.parametrize("width_px", [560.0, 260.0])
def test_the_cost_of_a_row_does_not_grow_with_the_length_of_the_table(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch, width_px: float
) -> None:
    """
    The scaling, as counts: the work done for a row appended early in a table and late.

    Two windows of one live table, each a whole number of pieces long: rows
    16-32 and rows 80-96. In pieces, with rows that change no column's width, the
    work for a row is the last piece wherever in the table it is, and the
    two windows do **exactly the same**: lines shipped, cells measured, cells
    broken. Whole -- the control, the cut turned off -- every row ships and
    measures the table so far, and the late window does more than three
    times the early one (the table is 24 and 88 rows long at the windows'
    middles). At 260 px the table does not fit and is wrapped, which is
    where the third count is not zero.

    Counts and not a clock (review 5, item 5). What the counts leave out is
    in `advtext.ui.units` and `TableMeasure`: a pointer or two per row, per
    layout.
    """
    width = sp_from_px(width_px)
    windows = (range(16, 32), range(80, 96))
    assert all(w.start % TABLE_PIECE_ROWS == 0 == len(w) % TABLE_PIECE_ROWS for w in windows)
    early, late = _table_work(theme, measure, StreamView, monkeypatch, width, windows)
    assert early == late, (early, late)
    assert early[0] > 0 and early[1] > 0 and (early[2] > 0) == (width_px < 300.0)
    whole_early, whole_late = _table_work(theme, measure, _WholeTables, monkeypatch, width, windows)
    assert all(b > 3 * a for a, b in zip(whole_early[:2], whole_late[:2], strict=True))
    assert whole_early[0] > 3 * early[0]


def test_a_table_keeps_its_pieces_when_it_commits_and_nothing_of_it_is_set_again(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append(TABLE_OPENS)
    for number in range(29):
        stream.append(varied_row(number))
        view.sync()
        view.layout_for(WIDTH)
    before = view.layout_for(WIDTH).units_of_block(1)
    shipped = _Counter(ship)
    monkeypatch.setattr(units_module, "ship", shipped)
    stream.append("\n")
    assert view.sync()
    layout = view.layout_for(WIDTH)
    assert len(stream.committed) == 2, "the table commits on the blank line under it"
    after = layout.units_of_block(1)
    assert len(after) == len(before) == -(-29 // TABLE_PIECE_ROWS)
    assert all(new is old for new, old in zip(after, before, strict=True))
    assert shipped.calls == 0
    # And it stays that way while the text after it arrives.
    for piece in pieces_of("A sentence after the table, a word at a time.\n\nMore.\n"):
        stream.append(piece)
        view.sync()
        layout = view.layout_for(WIDTH)
        assert all(new is old for new, old in zip(layout.units_of_block(1), before, strict=True))


def _links_of(view: StreamView, width: Scaled) -> list[tuple[str, int, int, tuple[Any, ...]]]:
    from advtext.backends.imgui_draw import Palette
    from advtext.ui import Viewport

    layout = view.layout_for(width)
    view._decorate(list(layout.visible_units(Viewport(0, layout.height))), Palette())
    return [(link.target, link.block, link.number, link.rects) for link in view.visible_links]


def test_the_links_in_a_table_in_pieces_are_the_whole_tables_links_by_number_and_place(
    theme: Theme, measure: Any
) -> None:
    # A link is known by its block and its number among the block's links
    # (`advtext.spans.LinkArea`). A piece maps its own cells from zero, so
    # without `PlacedUnit.skipped` the first link of every piece was number
    # 0 of block 1, and a press on one released on another was a click.
    stream = StreamDocument(theme, fontlib_metrics)
    followed: list[str] = []
    pieced = StreamView(stream, measure, on_link=followed.append)
    whole = _WholeTables(stream, measure, on_link=followed.append)
    stream.append(TABLE_OPENS + "".join(varied_row(number) for number in range(29)))
    pieced.sync()
    whole.sync()
    mine, theirs = _links_of(pieced, WIDTH), _links_of(whole, WIDTH)
    assert mine == theirs
    assert len(mine) == 4 and [number for _, _, number, _ in mine] == list(range(4))
    # Each the first link of its piece: each would have been number 0.
    assert [target.rsplit("/", 1)[1] for target, _, _, _ in mine] == ["3", "13", "18", "28"]
    assert pieced.unmapped_blocks == whole.unmapped_blocks == 0
    in_pieces = {
        unit.part for unit in pieced.layout_for(WIDTH).units_of_block(1) if unit.unit.blocks
    }
    assert in_pieces == set(range(-(-29 // TABLE_PIECE_ROWS)))


def test_a_press_on_a_link_in_one_piece_released_on_a_link_in_another_follows_neither(
    theme: Theme, measure: Any
) -> None:
    # In real frames. Pieces of two rows, so that both links are on screen:
    # each is the first link of its piece.
    class Small(StreamView):
        _TABLE_ROWS = 2

    stream = StreamDocument(theme, fontlib_metrics)
    followed: list[str] = []
    view = Small(stream, measure, on_link=followed.append, follow=False)
    rows = (
        "| a | [one](https://e.x/1) |\n| b | x |\n| c | y |\n"
        "| d | [two](https://e.x/2) |\n| e | z |\n"
    )
    stream.append("| k | v |\n|---|---|\n" + rows)
    frame(view, mouse=(1190.0, 790.0), left=False, width_px=560.0)
    frame(view, mouse=(1190.0, 790.0), width_px=560.0)
    assert view.origin is not None and view.layout is not None
    links = {link.target: link for link in view.visible_links}
    first, second = links["https://e.x/1"], links["https://e.x/2"]
    assert (first.number, second.number) == (0, 1)
    units = view.layout.units_of_block(0)
    assert len(units) == 3 and first.rects[0].y < units[1].y <= second.rects[0].y

    def on(link: Any) -> tuple[float, float]:
        rect = link.rects[0]
        assert view.origin is not None
        return (
            view.origin[0] + px_from_sp(rect.x + rect.width // 2),
            view.origin[1] + px_from_sp(rect.y + rect.height // 2),
        )

    def click(down: Any, up: Any) -> None:
        frame(view, mouse=on(down), width_px=560.0)
        frame(view, mouse=on(down), left=True, width_px=560.0)
        frame(view, mouse=on(up), width_px=560.0)
        frame(view, mouse=on(up), left=False, width_px=560.0)
        frame(view, mouse=on(up), width_px=560.0)

    click(first, second)
    assert followed == []
    # The control, or the line above could be a click that never works.
    click(second, second)
    assert followed == ["https://e.x/2"]
    click(first, first)
    assert followed == ["https://e.x/2", "https://e.x/1"]


def test_a_selection_in_a_live_table_survives_rows_arriving_and_reads_the_same(
    theme: Theme, measure: Any
) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append(TABLE_OPENS + "".join(steady_row(number) for number in range(11)))
    view.sync()
    layout = view.layout_for(WIDTH)
    pieces = layout.units_of_block(1)
    assert len(pieces) == -(-11 // TABLE_PIECE_ROWS) >= 2
    view.select(Selection(pieces[0].base + 4, pieces[1].base + 9))
    selected = view.selected_text()
    assert "\n" in selected and "\t" in selected
    for number in range(11, 30):
        stream.append(steady_row(number))
        view.sync()
        view.layout_for(WIDTH)
        assert view.selected_text() == selected
    # A row wider than any before moves every column: the same words still.
    stream.append(
        "| a much longer name than any | 1 | and a much longer note than any before it |\n"
    )
    view.sync()
    view.layout_for(WIDTH)
    assert view.selected_text() == selected


def test_colour_spans_set_on_a_table_in_pieces_are_ignored_as_on_a_whole_one(
    theme: Theme, measure: Any
) -> None:
    # `set_colours` on a table is kept and not applied. In pieces that used
    # to be an assertion in `_spans_for`, which knew only code pieces.
    stream = StreamDocument(theme, fontlib_metrics)
    view = StreamView(stream, measure)
    stream.append(TABLE_OPENS + "".join(steady_row(number) for number in range(20)))
    view.sync()
    from advtext.spans import ColourSpan

    view.set_colours(1, [ColourSpan(0, 5, ink=0xFF0000FF)])
    frame(view)
    frame(view)
    assert view.unmapped_blocks == 0 and len(view.layout.units_of_block(1)) > 2  # type: ignore[union-attr]

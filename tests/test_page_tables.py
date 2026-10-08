"""
The Tables page: its width arithmetic, its board with no ImGui, the page in
frames with a mouse, and the real app in a window.

**Four levels, stated so nobody reads more into a green run than is there.**

1. `dragged`, `fitted` and `floors_of`: integers in, integers out.
2. `Board` with no ImGui at all: `settle`, `drag`, `reset`, `observe` against
   the view's own layout. "One unit re-shipped" is asserted here, by identity
   of every other unit.
3. The page through `App.gui` in frames of a real `ImGuiContext` with no
   backend, mouse events queued before `new_frame`: a handle hovered, pressed,
   moved and released; a press on text; a selection carried through a drag;
   and the one gesture a mouse cannot make, a press on the frame of arrival.
4. The real app in a real window (`tests/conftest.py::window`), the same
   gesture injected, the page's own report read back as counts.

**Nothing here judges how a table looks** at any width. Nobody has dragged a
column with a hand.
"""

from __future__ import annotations

import math
import random
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from advtext.markdown import ColumnAlign, TableBlock, TextBlock, build_document
from advtext.pack import hpack
from advtext.selection import Selection
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import SizedTable, pages, table_columns, with_columns
from advtext.ui.app import App, parse_tab_request
from advtext.ui.pages import PageContext
from advtext.ui.pages import tables as page
from advtext.ui.pages.tables import Board, dragged, fitted, floors_of, readouts
from advtext.units import UNITY, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

DENSITY = 96.0
SIZE = (1300.0, 800.0)

SMALL = (
    "A paragraph above the table, long enough to have words to select in it.\n\n"
    "| Key | Value |\n"
    "| --- | --- |\n"
    "| one | alpha bravo charlie delta echo foxtrot golf hotel india juliet |\n"
    "| two | kilo lima mike |\n\n"
    "A paragraph below the table.\n"
)


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure() -> Any:
    return char_measure(fontlib_metrics)


def _px(value: float) -> Scaled:
    return sp_from_px(value, DENSITY)


def _board(theme: Theme, measure: Any, text: str | None = SMALL, width_px: float = 720.0) -> Board:
    """
    A board settled and laid out at `width_px`, its first layout already observed.
    """
    board = Board(theme=theme, measure=measure, text=text)
    _lay_out(board, width_px)
    return board


def _lay_out(board: Board, width_px: float | None = None) -> int | None:
    """
    What a frame does without a frame: settle, lay out, observe.
    """
    if width_px is not None:
        board.settle(_px(width_px))
    assert board.width is not None
    board.view.layout_for(board.width)
    return board.observe()


# ----------------------------------------------------------------------
# 1. Arithmetic
# ----------------------------------------------------------------------


def test_an_inner_edge_moves_the_boundary_and_keeps_the_pair_as_wide_as_it_was() -> None:
    widths, floors = (100, 200, 300), (40, 50, 60)
    assert dragged(widths, floors, 0, 130.0, 1000) == (130, 170, 300)
    assert dragged(widths, floors, 1, 250.0, 1000) == (100, 150, 350)
    # Nothing moved: the same tuple, so the caller can tell.
    assert dragged(widths, floors, 0, 100.0, 1000) == widths


def test_an_inner_edge_stops_at_either_columns_floor() -> None:
    widths, floors = (100, 200, 300), (40, 50, 60)
    assert dragged(widths, floors, 0, -5000.0, 1000) == (40, 260, 300)
    assert dragged(widths, floors, 0, 5000.0, 1000) == (250, 50, 300)
    assert dragged(widths, floors, 1, 5000.0, 1000) == (100, 440, 60)


def test_the_last_edge_resizes_the_last_column_between_its_floor_and_the_measure() -> None:
    widths, floors = (100, 200, 300), (40, 50, 60)
    assert dragged(widths, floors, 2, 450.0, 1000) == (100, 200, 150)
    assert dragged(widths, floors, 2, 0.0, 1000) == (100, 200, 60)
    assert dragged(widths, floors, 2, 5000.0, 1000) == (100, 200, 700)
    # A measure the other columns already fill: the last stays at its floor.
    assert dragged(widths, floors, 2, 5000.0, 250) == (100, 200, 60)


@pytest.mark.parametrize("x", [math.nan, math.inf, -math.inf])
def test_a_position_that_is_not_a_number_moves_nothing(x: float) -> None:
    widths = (100, 200, 300)
    for edge in range(3):
        assert dragged(widths, (40, 50, 60), edge, x, 1000) == widths


def test_an_edge_that_does_not_exist_moves_nothing() -> None:
    widths = (100, 200)
    assert dragged(widths, (10, 10), 2, 50.0, 1000) == widths
    assert dragged(widths, (10, 10), -1, 50.0, 1000) == widths
    assert dragged((), (), 0, 50.0, 1000) == ()


def test_a_pair_already_narrower_than_its_two_floors_is_left_alone() -> None:
    assert dragged((30, 30, 300), (40, 50, 60), 0, 35.0, 1000) == (30, 30, 300)


def test_whatever_a_pointer_asks_for_the_widths_stay_whole_and_at_or_above_the_floors() -> None:
    """
    Two thousand drags from one seed, each from the result of the last.
    """
    rng = random.Random(20261007)
    for _ in range(40):
        count = rng.randint(1, 6)
        floors = tuple(rng.randint(1, 400) for _ in range(count))
        widths = tuple(floor + rng.randint(0, 900) for floor in floors)
        available = rng.randint(1, 4000)
        for _ in range(50):
            edge = rng.randrange(count)
            x = rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-1e300, 1e300), 0.5, -0.0])
            after = dragged(widths, floors, edge, x, available)
            assert len(after) == count
            assert all(type(width) is int for width in after)
            assert all(width >= floor for width, floor in zip(after, floors, strict=True))
            if edge < count - 1:
                assert sum(after) == sum(widths)
            else:
                assert after[:-1] == widths[:-1]
                assert after[-1] <= max(floors[-1], available - sum(widths[:-1]))
            widths = after


def test_fitted_leaves_widths_that_fit_and_squeezes_those_that_do_not() -> None:
    floors = (40, 50, 60)
    assert fitted((100, 200, 300), floors, 600) == (100, 200, 300)
    assert fitted((100, 200, 300), floors, 9000) == (100, 200, 300)

    squeezed = fitted((100, 200, 300), floors, 375)
    assert sum(squeezed) == 375
    assert all(width >= floor for width, floor in zip(squeezed, floors, strict=True))
    # 225 of slack over 60 + 150 + 240 of room: 30, 75, 120.
    assert squeezed == (70, 125, 180)

    assert fitted((100, 200, 300), floors, 150) == floors
    assert fitted((100, 200, 300), floors, 100) == floors
    # A width under its floor is raised to it, whatever the measure.
    assert fitted((10, 200, 300), floors, 9000) == (40, 200, 300)


def test_fitted_sums_to_the_measure_exactly_whenever_it_squeezes() -> None:
    rng = random.Random(7)
    for _ in range(500):
        count = rng.randint(1, 6)
        floors = tuple(rng.randint(1, 300) for _ in range(count))
        widths = tuple(floor + rng.randint(0, 900) for floor in floors)
        available = rng.randint(1, 3000)
        out = fitted(widths, floors, available)
        assert all(width >= floor for width, floor in zip(out, floors, strict=True))
        if sum(widths) <= available:
            assert out == widths
        elif sum(floors) < available:
            assert sum(out) == available
        else:
            assert out == floors


def test_a_columns_floor_is_its_longest_word_and_the_padding(theme: Theme, measure: Any) -> None:
    """
    The oracle is the word set on its own, not the breaker `floors_of` asks.
    """
    source = (
        "| a | b |\n| --- | --- |\n"
        "| one two incomprehensibilities three | xx |\n"
        "| four | yy zzzzzzzzzzzzzzzzzzzzzzzz y |\n"
    )
    table = build_document(source, theme, fontlib_metrics).blocks[0]
    assert isinstance(table, TableBlock)

    def alone(word: str) -> Scaled:
        block = build_document(word + "\n", theme, fontlib_metrics).blocks[0]
        assert isinstance(block, TextBlock)
        return hpack(block.material, measure=measure).box.width + 2 * theme.cell_padding

    expected = (alone("incomprehensibilities"), alone("zzzzzzzzzzzzzzzzzzzzzzzz"))
    assert floors_of(table, theme, measure) == expected
    # The same for the table once it has widths of its own.
    sized = with_columns(table, widths=(50 * UNITY, 60 * UNITY))
    assert floors_of(sized, theme, measure) == expected


# ----------------------------------------------------------------------
# 2. The board
# ----------------------------------------------------------------------


def test_the_demo_document_has_the_five_cases_the_page_says_it_has(
    theme: Theme, measure: Any
) -> None:
    """
    Counted from the converted document, at the measure the page opens at.
    """
    text = pages.demo_text("tables.md")
    assert text is not None, "demo/tables.md is missing"
    board = _board(theme, measure, text=None, width_px=page.DEFAULT_PANE_PX)
    assert len(board.tables) == 5
    blocks = [board.block(table) for table in board.tables]
    width = board.width
    assert width is not None

    fits = [sum(board.natural(table)) <= width for table in board.tables]
    assert fits[0], "the short-cell table should fit and be scaled up"
    assert not fits[1] and not fits[3]
    # Too wide for the whole body too, so no setting of the slider un-squeezes it.
    assert sum(board.natural(board.tables[3])) > _px(1068.0)
    assert sum(board.floors(board.tables[3])) < width

    aligns = set(blocks[2].aligns)
    assert {ColumnAlign.CENTER, ColumnAlign.RIGHT} <= aligns

    links = [cell.links for row in blocks[4].rows for cell in row if cell.links]
    assert len(links) >= 3
    assert all(len(block.header) >= 2 for block in blocks)


def _as_set(board: Board, table: int, theme: Theme, measure: Any) -> tuple[Scaled, ...]:
    """
    What compose will set the view's own block to, asked of the library.
    """
    shown = board.view.document.blocks[table]
    assert isinstance(shown, TableBlock) and board.width is not None
    return table_columns(shown, theme, board.width, measure)


def test_the_boards_columns_are_the_ones_the_view_is_set_to(theme: Theme, measure: Any) -> None:
    board = _board(theme, measure, text=None)
    assert board.width is not None
    for table in board.tables:
        assert board.columns(table) == _as_set(board, table, theme, measure)
    first = board.tables[1]
    assert board.drag(first, 0, sum(board.columns(first)[:1]) + _px(40.0))
    _lay_out(board)
    for table in board.tables:
        assert board.columns(table) == _as_set(board, table, theme, measure)
    assert isinstance(board.view.document.blocks[first], SizedTable)


def test_a_drag_re_ships_the_one_table_and_no_other_unit(theme: Theme, measure: Any) -> None:
    board = _board(theme, measure, text=None)
    before = board.view.layout
    assert before is not None and board.relayouts == 0
    table = board.tables[1]
    grip = next(g for g in board.grips() if g.table == table and g.edge == 1)

    assert board.drag(table, 1, grip.x - _px(120.0))
    assert _lay_out(board) == 1
    after = board.view.layout
    assert after is not None and after is not before
    assert (board.reshipped, board.units, board.relayouts) == (1, len(after.placed), 1)
    changed = [
        new.block_start
        for old, new in zip(before.placed, after.placed, strict=True)
        if old.unit is not new.unit
    ]
    assert changed == [table]


def test_a_narrower_column_wraps_its_cells_onto_more_lines(theme: Theme, measure: Any) -> None:
    board = _board(theme, measure)
    (table,) = board.tables
    layout = board.view.layout
    assert layout is not None
    (unit,) = layout.units_of_block(table)
    below_was = layout.units_of_block(table + 1)[0].y
    lines = len(board.view.set_lines(table, table + 1))
    assert lines == 3  # header and two rows, nothing wrapped at 720 px

    grip = board.grips()[-1]
    assert (grip.table, grip.edge) == (table, 1)
    assert board.drag(table, 1, 0.0)
    _lay_out(board)
    layout = board.view.layout
    assert layout is not None
    (narrow,) = layout.units_of_block(table)
    assert board.columns(table)[1] == board.floors(table)[1]
    assert len(board.view.set_lines(table, table + 1)) > lines + 5
    assert narrow.height > unit.height
    # The paragraph under the table moved down by exactly what the table grew.
    (below,) = layout.units_of_block(table + 1)
    assert below.y - below_was == narrow.height - unit.height


def test_the_handles_sit_on_the_column_edges_of_the_table_as_laid_out(
    theme: Theme, measure: Any
) -> None:
    board = _board(theme, measure, text=None)
    layout = board.view.layout
    assert layout is not None
    grips = board.grips()
    assert len(grips) == sum(len(board.columns(table)) for table in board.tables)
    for table in board.tables:
        own = [grip for grip in grips if grip.table == table]
        assert [grip.edge for grip in own] == list(range(len(own)))
        units = layout.units_of_block(table)
        assert {(grip.top, grip.bottom) for grip in own} == {(units[0].y, units[-1].bottom)}
        xs = [grip.x for grip in own]
        assert xs == sorted(xs)
        assert xs[-1] == sum(board.columns(table)) + board.block(table).left_indent
    # Between a settle at a new measure and the layout for it, nothing to grab.
    board.settle(_px(500.0))
    assert board.grips() == ()


def test_nothing_a_pointer_can_ask_for_reaches_compose_as_an_invalid_width(
    theme: Theme, measure: Any
) -> None:
    """
    `with_columns` raises on a width under one unit or not finite; none may arrive.
    """
    board = _board(theme, measure, text=None, width_px=300.0)
    wild = [-1e300, -1e9, -1.0, 0.0, 0.4, 1e9, 1e300, math.inf, -math.inf, math.nan]
    for grip in board.grips():
        for x in wild:
            board.drag(grip.table, grip.edge, x)
            _lay_out(board)
            widths = board.columns(grip.table)
            floors = board.floors(grip.table)
            assert all(type(width) is int and width >= 1 for width in widths)
            assert all(width >= floor for width, floor in zip(widths, floors, strict=True))
    assert not board.drag(999, 0, 10.0), "a block that is not a table"
    assert not board.drag(board.tables[0], 99, 10.0), "an edge that does not exist"


def test_no_drag_before_the_first_layout_and_none_on_a_document_with_no_table(
    theme: Theme, measure: Any
) -> None:
    fresh = Board(theme=theme, measure=measure, text=SMALL)
    assert not fresh.drag(fresh.tables[0], 0, 100.0)
    assert fresh.columns(fresh.tables[0]) == () and fresh.grips() == ()
    assert len(readouts(fresh)) == 4

    bare = _board(theme, measure, text="Only a paragraph.\n")
    assert bare.tables == () and bare.focus is None and bare.grips() == ()
    assert readouts(bare)[0] == "no table in this document"
    assert not bare.reset()


def test_reset_puts_back_the_very_blocks_the_document_was_converted_to(
    theme: Theme, measure: Any
) -> None:
    board = _board(theme, measure, text=None)
    automatic = {table: board.columns(table) for table in board.tables}
    for table in board.tables[:3]:
        assert board.drag(table, 1, -_px(2000.0))
    _lay_out(board)
    assert len(board.chosen) == 3

    assert board.reset()
    assert _lay_out(board) == 3, "the three tables that had been dragged, and nothing else"
    assert board.chosen == {}
    assert all(
        shown is source
        for shown, source in zip(board.view.document.blocks, board.source.blocks, strict=True)
    )
    assert {table: board.columns(table) for table in board.tables} == automatic
    assert not board.reset()


def test_chosen_widths_are_squeezed_by_a_narrow_measure_and_come_back(
    theme: Theme, measure: Any
) -> None:
    board = _board(theme, measure, width_px=720.0)
    (table,) = board.tables
    assert board.drag(table, 1, _px(600.0))
    _lay_out(board)
    wide = board.columns(table)
    assert sum(wide) == _px(600.0)

    assert _lay_out(board, 300.0) is None, "a new measure is not a drag and is not counted"
    narrow = board.columns(table)
    assert sum(narrow) == _px(300.0) < sum(wide)
    assert all(w >= f for w, f in zip(narrow, board.floors(table), strict=True))
    assert board.view.document.blocks[table] == with_columns(board.block(table), widths=narrow)

    _lay_out(board, 720.0)
    assert board.columns(table) == wide


def test_the_floors_option_sets_every_column_of_every_table_to_its_floor(
    theme: Theme, measure: Any
) -> None:
    board = _board(theme, measure, text=None)
    board.to_floors()
    assert _lay_out(board) == len(board.tables)
    for table in board.tables:
        assert board.columns(table) == board.floors(table)


def test_the_readouts_are_four_lines_of_counts_and_sizes(theme: Theme, measure: Any) -> None:
    board = _board(theme, measure)
    (table,) = board.tables
    lines = readouts(board)
    assert len(lines) == 4
    assert lines[0].startswith("table 1 of 1  ·  automatic  ·  720 px wide in a 720 px measure")
    assert "0 of 2 columns under natural width, 0 at the floor" in lines[0]
    assert lines[2] == "last drag: none yet"
    assert "clicked: 0" in lines[3]

    board.drag(table, 1, 0.0)
    _lay_out(board)
    lines = readouts(board)
    assert (
        "dragged" in lines[0] and "1 of 2 columns under natural width, 1 at the floor" in lines[0]
    )
    shown = [tuple(int(n) for n in part.split("/")) for part in lines[1].split(":  ")[1].split("·")]
    expected = [
        tuple(round(px_from_sp(value, DENSITY)) for value in column)
        for column in zip(
            board.columns(table), board.natural(table), board.floors(table), strict=True
        )
    ]
    assert shown == expected
    assert lines[2].startswith("last drag: 1 of 3 units re-shipped")

    # Change and cost, never quality (docs/visual-review.md).
    banned = ("better", "worse", "good", "bad", "clean", "nice", "crisp", "ugly", "correct")
    for line in lines:
        assert not any(word in line.lower().split() for word in banned)


def test_without_a_demo_directory_the_page_shows_its_built_in_table(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    board = Board(theme=theme, measure=measure)
    assert len(board.tables) == 1
    _lay_out(board, 400.0)
    assert len(board.grips()) == 2


# ----------------------------------------------------------------------
# 3. The page, in frames
# ----------------------------------------------------------------------


def test_the_page_is_discovered_where_the_sidebar_order_puts_it() -> None:
    found = pages.require()
    spec = found.find("tables")
    assert spec is page.PAGE
    assert (spec.name, spec.group, spec.order) == ("Tables", "Embedding", 120)
    assert spec.shot_specs() == ("tables", "tables:floors")
    for request in spec.shot_specs():
        assert parse_tab_request(request, found).tab == "tables"


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


def test_the_launch_options_set_the_measure_and_the_opening_state() -> None:
    plain = page.TablesPage(_context("tables"))
    assert plain.pane_px == page.DEFAULT_PANE_PX and not plain._to_floors
    made = page.TablesPage(_context("tables:floors,500"))
    assert made.pane_px == 500.0 and made._to_floors
    assert page.TablesPage(_context("tables:5")).pane_px == page.MIN_PANE_PX
    assert page.TablesPage(_context("tables:99999")).pane_px == page.MAX_PANE_PX
    assert page.TablesPage(_context("document:3")).pane_px == page.DEFAULT_PANE_PX


def _frame(
    app: App, *, mouse: tuple[float, float] | None = None, button: bool | None = None
) -> None:
    """
    One frame of `App.gui` in a full-size window of a context with no backend.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##advtext-tables-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
    finally:
        imgui.render()


@pytest.fixture
def shown() -> Any:
    """
    The page in the shell after three frames, pointer off the window; released afterwards.
    """
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="tables")
    _frame(app, mouse=(-1.0e6, -1.0e6), button=False)
    _frame(app)
    _frame(app)
    made = app.page("tables")
    assert isinstance(made, page.TablesPage)
    yield app, made
    _frame(app, mouse=(-1.0e6, -1.0e6), button=False)
    _frame(app)


def _on_screen(made: page.TablesPage, table: int, edge: int) -> tuple[float, float]:
    """
    A point on a handle: on its column edge, a little below the table's top.
    """
    board = made.board
    origin = board.view.origin
    assert origin is not None
    grip = next(g for g in board.grips() if (g.table, g.edge) == (table, edge))
    x = origin[0] + px_from_sp(grip.x, DENSITY)
    y = origin[1] + px_from_sp(grip.top, DENSITY) + 12.0
    assert 0.0 < y < SIZE[1] - 20.0, "the handle is not in the window"
    return x, y


def test_the_page_opens_at_its_measure_with_every_table_automatic(shown: Any) -> None:
    _, made = shown
    board = made.board
    assert made.frames == 3 and board.chosen == {} and made.held is None
    assert board.width == _px(page.DEFAULT_PANE_PX)
    assert board.view.layout is not None and board.view.layout.width == board.width
    assert made.stats is not None and made.stats.glyphs > 0
    assert board.reshipped is None and board.relayouts == 0
    assert len(board.grips()) == 17
    # The handles left the cursor where the view had: nothing added to the content.
    assert made.cursor_drift == 0.0


def test_a_handle_hovered_pressed_and_moved_drags_its_column_and_selects_nothing(
    shown: Any,
) -> None:
    app, made = shown
    board = made.board
    table = board.tables[0]
    before = board.columns(table)
    x, y = _on_screen(made, table, 0)

    _frame(app, mouse=(x + 2.0, y))  # the frame of hovering a mouse always has
    assert made.held is None and board.chosen == {}
    _frame(app, button=True)
    assert made.held == (table, 0)
    assert board.chosen == {}, "a press alone moves nothing"
    assert board.view.selection.is_empty

    _frame(app, mouse=(x + 2.0 - 100.0, y))
    assert made.held == (table, 0)
    moved = board.columns(table)
    # The edge kept its 2 px offset from the pointer: 100 px, to the scaled point's rounding.
    assert abs((before[0] - moved[0]) - _px(100.0)) <= 1
    assert sum(moved) == sum(before)
    assert board.reshipped == 1 and board.relayouts == 1
    # The layout the frame drew is the one with the new widths: no frame of lag.
    assert board.view.layout is not None
    assert board.view.document.blocks[table] == with_columns(board.block(table), widths=moved)
    assert board.grips()[0].x == moved[0]

    _frame(app, mouse=(x + 2.0 - 130.0, y))
    assert board.relayouts == 2 and board.reshipped == 1
    _frame(app, button=False)
    _frame(app)
    assert made.held is None
    assert board.view.selection.is_empty
    assert abs((before[0] - board.columns(table)[0]) - _px(130.0)) <= 1

    # With the button up, moving the pointer moves nothing.
    settled = board.columns(table)
    _frame(app, mouse=(x + 300.0, y))
    _frame(app)
    assert board.columns(table) == settled and board.relayouts == 2


def test_a_handle_dragged_past_everything_stops_at_the_floors(shown: Any) -> None:
    app, made = shown
    board = made.board
    table = board.tables[0]
    x, y = _on_screen(made, table, 0)
    total = sum(board.columns(table))
    _frame(app, mouse=(x, y))
    _frame(app, button=True)
    _frame(app, mouse=(-50000.0, y))
    assert board.columns(table)[0] == board.floors(table)[0]
    _frame(app, mouse=(50000.0, y))
    assert board.columns(table)[1] == board.floors(table)[1]
    assert sum(board.columns(table)) == total
    _frame(app, button=False)


def test_a_press_on_text_selects_as_it_always_did_and_drags_no_column(shown: Any) -> None:
    app, made = shown
    board = made.board
    origin = board.view.origin
    assert origin is not None
    # The first block is the heading; press inside its line and drag right.
    layout = board.view.layout
    assert layout is not None
    y = origin[1] + px_from_sp(layout.placed[0].y + layout.placed[0].height // 2, DENSITY)
    _frame(app, mouse=(origin[0] + 20.0, y))
    _frame(app, button=True)
    _frame(app, mouse=(origin[0] + 200.0, y))
    _frame(app, button=False)
    _frame(app)
    assert not board.view.selection.is_empty
    assert board.view.selected_text() in "Tables you can pull about"
    assert board.chosen == {} and made.held is None and board.relayouts == 0


def test_a_selection_made_before_a_drag_is_still_there_after_it(shown: Any) -> None:
    app, made = shown
    board = made.board
    table = board.tables[0]
    layout = board.view.layout
    assert layout is not None
    # Everything from the heading down to and including the first table.
    stop = layout.units_of_block(table)[-1].index_range.stop
    board.view.select(Selection(0, stop))
    text = board.view.selected_text()
    assert "flush right" in text

    x, y = _on_screen(made, table, 0)
    _frame(app, mouse=(x, y))
    _frame(app, button=True)
    _frame(app, mouse=(x - 60.0, y))
    _frame(app, button=False)
    _frame(app)
    assert table in board.chosen
    assert board.view.selected_text() == text


def test_a_press_on_the_frame_the_pointer_arrives_is_the_handles(shown: Any) -> None:
    """
    The gesture the handles used to lose, and no longer do.

    A mouse hovers for a frame before it can press. An injected event need
    not: move and press queued together reach the page on one frame. While the
    handles were submitted *after* the view, the view saw no item under the
    pointer on that frame, took the press as a selection, and its own button
    kept the handle from being clicked. They are submitted before it now
    (`BareView.next_origin`, `layout_for`), so the handle is ImGui's hovered
    item by the time the view looks: the column moves and nothing is selected.
    """
    app, made = shown
    board = made.board
    table = board.tables[0]
    before = board.columns(table)
    x, y = _on_screen(made, table, 0)
    _frame(app, mouse=(x, y), button=True)
    assert made.held == (table, 0)
    _frame(app, mouse=(x - 80.0, y))
    _frame(app, mouse=(x - 80.0, y))
    after = board.columns(table)
    assert table in board.chosen and after[0] < before[0]
    assert board.view.selection.is_empty and not board.view.owns_selection
    _frame(app, button=False)
    _frame(app)
    assert made.held is None


LINKED = (
    "| Name | Where |\n"
    "| --- | --- |\n"
    "| The parser, described at some length so that the cell has words to wrap"
    " | [the project](https://example.org/parser) |\n"
)


def test_a_link_in_a_cell_is_hovered_and_clicked_before_and_after_its_table_is_dragged(
    theme: Theme, measure: Any
) -> None:
    """
    The page's `draw` on its own in a window, over a document that is one table with a link.

    A press on a link is the link's (the view's rule) and a press on a handle
    is the handle's (this page's): neither selects, and dragging the table
    does not lose the link.
    """
    pytest.importorskip("imgui_bundle")
    made = page.TablesPage(PageContext.build())
    made.board = Board(theme=theme, measure=measure, text=LINKED)
    board = made.board

    class _Shell:
        def gui(self) -> None:
            made.draw()

    shell: Any = _Shell()
    _frame(shell, mouse=(-1.0e6, -1.0e6), button=False)
    _frame(shell)
    _frame(shell)

    def on_the_link() -> tuple[float, float]:
        origin = board.view.origin
        assert origin is not None
        (link,) = board.view.visible_links
        rect = link.rects[0]
        return (
            origin[0] + px_from_sp(rect.x + rect.width // 2, DENSITY),
            origin[1] + px_from_sp(rect.y + rect.height // 2, DENSITY),
        )

    def click(point: tuple[float, float]) -> None:
        _frame(shell, mouse=point)
        assert board.view.hovered_link == "https://example.org/parser"
        assert "link under the pointer: https://example.org/parser" in readouts(board)[3]
        _frame(shell, button=True)
        _frame(shell, button=False)
        _frame(shell)

    click(on_the_link())
    assert board.followed == ["https://example.org/parser"]
    assert board.view.selection.is_empty and board.chosen == {}

    (table,) = board.tables
    x, y = _on_screen(made, table, 0)
    _frame(shell, mouse=(x, y))
    assert board.view.hovered_link is None
    _frame(shell, button=True)
    _frame(shell, mouse=(x - 150.0, y))
    _frame(shell, button=False)
    _frame(shell)
    assert table in board.chosen and board.followed == ["https://example.org/parser"]

    # The pointer comes straight off the handle. For that one frame the view
    # still counts the handle as the item under the mouse -- ImGui's hovered
    # ID is this frame's or, while nothing is hovered yet, the last frame's --
    # so the link is not hovered until the frame after. This edge is the
    # view's and submitting the handles before it does not remove it.
    _frame(shell, mouse=on_the_link())
    assert board.view.hovered_link is None
    click(on_the_link())
    assert board.followed == ["https://example.org/parser"] * 2
    assert "clicked: 2" in readouts(board)[3]
    assert board.view.selection.is_empty
    _frame(shell, mouse=(-1.0e6, -1.0e6), button=False)


def test_the_floors_option_opens_the_page_with_every_table_at_its_floors() -> None:
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="tables:floors,600")
    _frame(app, mouse=(-1.0e6, -1.0e6), button=False)
    _frame(app)
    made = app.page("tables")
    assert isinstance(made, page.TablesPage)
    board = made.board
    assert board.width == _px(600.0)
    assert set(board.chosen) == set(board.tables)
    for table in board.tables:
        assert board.columns(table) == board.floors(table)
    # The opening state is the first layout, not a drag.
    assert board.reshipped is None


# ----------------------------------------------------------------------
# 4. The real app in a real window
# ----------------------------------------------------------------------

GESTURE = """
from imgui_bundle import hello_imgui, imgui

from advtext.ui import app as advtext_app
from advtext.units import px_from_sp

state = {"frames": 0, "step": 0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        # No operator will wake an idling app.
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    state["frames"] += 1
    made = self.page("tables")
    board = made.board
    io = imgui.get_io()
    if state["frames"] < 6 or board.view.origin is None:
        return
    table = board.tables[0]
    if state["step"] == 0:
        grip = next(g for g in board.grips() if (g.table, g.edge) == (table, 0))
        origin = board.view.origin
        state["x"] = origin[0] + px_from_sp(grip.x, board.px_per_inch)
        state["y"] = origin[1] + px_from_sp(grip.top, board.px_per_inch) + 12.0
        state["before"] = board.columns(table)
        io.add_mouse_pos_event(state["x"], state["y"])
    elif state["step"] == 2:
        io.add_mouse_button_event(0, True)
    elif 4 <= state["step"] < 14:
        io.add_mouse_pos_event(state["x"] - 12.0 * (state["step"] - 3), state["y"])
    elif state["step"] == 14:
        state["held"] = made.held
        io.add_mouse_button_event(0, False)
    elif state["step"] >= 17:
        moved = state["before"][0] - board.columns(table)[0]
        print(
            f"gesture held={int(state['held'] == (table, 0))} "
            f"released={int(made.held is None)} "
            f"moved_px={px_from_sp(moved, board.px_per_inch):.1f} "
            f"sum_kept={int(sum(board.columns(table)) == sum(state['before']))}"
        )
        for line in made.report():
            print(line)
        hello_imgui.get_runner_params().app_shall_exit = True
    state["step"] += 1


advtext_app.App.gui = watched_gui
advtext_app.run(tab="tables")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_a_column_is_dragged_in_a_real_window(window: Window) -> None:
    """
    The real app on `--tab tables`: hover a handle, press, ten moves of 12 px, release.

    Counts only: the handle was held and let go, the column narrowed by the
    120 px the pointer travelled, the table kept its width, each move's
    relayout re-shipped one unit, no text was selected, glyphs were drawn and
    none was missing.
    """
    script = window.out / "tables_page_gesture.py"
    script.write_text(textwrap.dedent(GESTURE), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if "=" in line]
    assert len(lines) == 7, done.stdout
    gesture, total = _fields(lines[0]), _fields(lines[1])
    assert gesture["held"] == "1" and gesture["released"] == "1", done.stdout
    assert abs(float(gesture["moved_px"]) - 120.0) < 0.5, done.stdout
    assert gesture["sum_kept"] == "1"
    assert total["tables"] == "5" and total["dragged"] == "1"
    assert total["reshipped"] == "1" and total["relayouts"] == "10", done.stdout
    assert total["selected"] == "0"
    assert int(total["glyphs"]) > 0 and total["missing"] == "0"
    tables = [_fields(line) for line in lines[2:]]
    assert [entry["state"] for entry in tables] == ["dragged"] + ["automatic"] * 4
    assert all(entry["under_floor"] == "0" for entry in tables)

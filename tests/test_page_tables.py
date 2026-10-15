"""
The Tables page: its width arithmetic, what it says without the imtypeset
library, the page in frames with a mouse when the library draws, and the real
app in a window.

**Four levels, stated so nobody reads more into a green run than is there.**

1. `dragged` and `fitted`: integers in, integers out.
2. Without the library, in this process (where it is never ready): the page
   draws one line saying why and nothing else, its launch options are read
   all the same, the readout lines are checked over a stand-in board, and a
   fresh interpreter shows that opening the page imports no old view.
3. With the library (skipped with the reason when `IMTYPESET_LIBRARY` is not
   set): ONE child process with the library loaded and its fonts given,
   driving the page in frames of a real `ImGuiContext` with no backend, mouse
   events queued before `new_frame`: a handle hovered, pressed, moved and
   released; a press on text; a selection carried through a drag; the one
   gesture a mouse cannot make, a press on the frame of arrival; and the
   library failing mid-run.
4. The real app in a real window (`tests/conftest.py::window`), with and
   without the library; with it, the same gesture injected and the page's own
   report read back as counts.

**The old board is gone and its answers are data.** Until T5-FB-C the page
had a second board over the Python layout core, and the library's columns
were compared with it live. `OLD_BOARD` below is what that board answered for
`demo/tables.md` at the page's opening measure, written down once
(`.concerns/T5-FB-C-scripts/freeze_tables.py`).

**Nothing here judges how a table looks** at any width. Nobody has dragged a
column with a hand.
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import test_typeset_closure as closure

from imscribe import typesetter
from imscribe.ui import pages
from imscribe.ui.app import App, parse_tab_request
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import tables as page
from imscribe.ui.pages import typeset as typeset_page
from imscribe.ui.pages.tables import dragged, fitted, readouts
from imscribe.ui.typeset_view import TypesetUnavailable
from imscribe.units import Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

DENSITY = 96.0
SIZE = (1300.0, 800.0)
_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)

OLD_BOARD: dict[str, Any] = {
    "width_sp": 35522150,
    "tables": [4, 7, 10, 13, 16],
    "handles": 17,
    "columns": [
        [314.66232179457245, 405.33767009781036],
        [77.9609220955272, 359.6631041796389, 282.3759656172167],
        [68.61401498936281, 348.97357565379826, 128.67554775062268, 173.73685349859903],
        [
            84.39058689419885,
            148.59373378476548,
            183.2882347122769,
            155.96976020911168,
            147.7576762920299,
        ],
        [125.49215263724575, 370.7110299268369, 223.79680932830016],
    ],
    "natural": [
        [110.12497486638648, 141.85936446009757],
        [77.9609220955272, 958.6793867073994, 748.60903691236],
        [44.31246594800748, 225.374896222499, 83.10153655562475, 112.20309905562475],
        [
            84.39058689419885,
            381.999914059257,
            579.281146222499,
            451.7264157521275,
            420.4139668301163,
        ],
        [125.49215263724575, 529.6717509534559, 223.79680932830016],
    ],
    "floors": [
        [79.75779304171856, 69.67183608343711],
        [77.9609220955272, 104.04679554535078, 83.42180770677668],
        [44.31246594800748, 92.2577727726754, 83.10153655562475, 78.89060229867165],
        [
            84.39058689419885,
            97.3515049359174,
            96.35155196009757,
            91.03903574486303,
            87.89840831257784,
        ],
        [125.49215263724575, 123.66402682648403, 223.79680932830016],
    ],
    "available": [35522150, 35522150, 35522150, 35522150, 35522150],
    "readouts": [
        "table 1 of 5  ·  automatic  ·  720 px wide in a 720 px measure"
        "  ·  0 of 2 columns under natural width, 0 at the floor",
        "width / natural / floor, px:  315 / 110 / 80  ·  405 / 142 / 70",
    ],
}
"""
What the old core's board answered for `demo/tables.md` at 720 px, 96 px an inch.

Pixels for `columns`, `natural` and `floors` (a list a table), scaled points
for `width_sp` and `available`, and its first two readout lines.
"""


def _px(value: float) -> Scaled:
    return sp_from_px(value, DENSITY)


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


# ----------------------------------------------------------------------
# 2. Without the library
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


def _frame(draw: Any) -> int:
    """
    One frame of a context with no backend, `draw()` in a full-size window.

    Returns the vertices `draw` added to the window's draw list.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.add_mouse_pos_event(-1.0e6, -1.0e6)
    added = 0
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##imscribe-tables-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            vertices = imgui.get_window_draw_list().vtx_buffer
            before = vertices.size()
            draw()
            added = vertices.size() - before
        finally:
            imgui.end()
    finally:
        imgui.render()
    return added


@pytest.fixture
def unasked(monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    `imscribe.typesetter` as at import, and a `module()` that fails the test if asked.
    """
    typesetter._forget()
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("the page asked for the library"))
    yield
    typesetter._forget()


@pytest.mark.parametrize("spec", ["tables", "tables:floors,600"])
def test_without_the_library_the_page_is_one_line_saying_why(
    spec: str, monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    Through the app's shell. No board, no controls, no pane: the sentence and nothing else.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    for _ in range(3):
        _frame(app.gui)
    assert app.page_errors == {}, app.page_errors
    made = app.page("tables")
    assert isinstance(made, page.TablesPage)
    assert made.board is None and made.renderer == "none" and made.whole is None
    assert made.reason == typesetter.SWITCHED_OFF_REASON and made.frames == 3
    assert made.report() == [f"frames=3 renderer=none reason={typesetter.SWITCHED_OFF_REASON!r}"]

    # The page's own frame: exactly the vertices of its sentence.
    sentence = f"{typeset_page.NOT_DRAWING}: {made.reason}"

    def only_the_sentence() -> None:
        imgui.text_wrapped(sentence)

    assert _frame(made.draw) == _frame(only_the_sentence) > 0


CLOSURE = r"""
import json
import sys

from imgui_bundle import imgui

from imscribe.ui.pages import PageContext
from imscribe.ui.pages import tables as page

at_import = sorted(name for name in sys.modules if name.startswith("imscribe"))
context = PageContext.build(request_page="tables", request_options=("floors",))
before = set(sys.modules)
made = page.TablesPage(context)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
for _ in range(3):
    io.delta_time = 1.0 / 60.0
    imgui.new_frame()
    imgui.begin("x")
    made.draw()
    imgui.end()
    imgui.render()
print(json.dumps({
    "at_import": at_import,
    "report": made.report(),
    "added": sorted(name for name in set(sys.modules) - before if name.startswith("imscribe")),
    "loaded": sorted(name for name in sys.modules if name.startswith("imscribe")),
    "imtypeset": "imtypeset" in sys.modules,
}))
"""


def test_without_the_library_importing_and_drawing_the_page_load_no_old_view(
    tmp_path: Path,
) -> None:
    """
    A fresh interpreter, the library's variables removed. Importing the page
    loads nothing of the old core (two leaves until T5-B2) and three frames of it add no
    `imscribe` module to what a `PageContext` loaded: no `imscribe.markdown`, no
    `BareView`, no compositor, no draw backend.
    """
    pytest.importorskip("imgui_bundle")
    script = tmp_path / "closure.py"
    script.write_text(textwrap.dedent(CLOSURE), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-P", str(script)],
        cwd=str(_ROOT),
        env={**env, "PYTHONPATH": str(_ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert got["report"] == [f"frames=3 renderer=none reason={typesetter.SWITCHED_OFF_REASON!r}"]
    assert got["imtypeset"] is False and got["added"] == []
    assert set(got["at_import"]) & closure.OLD_CORE == set()
    assert set(got["loaded"]) & closure.REFERENCE_CORE == set()
    loaded = set(got["loaded"])
    for gone in (
        "imscribe.markdown",
        "imscribe.linebreak",
        "imscribe.shipout",
        "imscribe.selection",
        "imscribe.ui.composition",
        "imscribe.ui.bare_view",
        "imscribe.backends.imgui_draw",
    ):
        assert gone not in loaded


class _View:
    hovered_link: str | None = None


class _StandIn:
    """
    The members `readouts` reads of a board, with one two-column table at block 3.
    """

    px_per_inch = DENSITY
    tables: tuple[int, ...] = (3,)
    focus: int | None = 3
    width: Scaled | None = _px(720.0)
    rows_set: int | None = None
    cells_measured: int | None = None
    relayouts = 0

    def __init__(self) -> None:
        self.view = _View()
        self.followed: list[str] = []
        self.chosen: dict[int, tuple[Scaled, ...]] = {}
        self.widths = (_px(300.0), _px(420.0))

    def columns(self, table: int) -> tuple[Scaled, ...]:
        return self.widths

    def natural(self, table: int) -> tuple[Scaled, ...]:
        return (_px(110.0), _px(500.0))

    def floors(self, table: int) -> tuple[Scaled, ...]:
        return (_px(80.0), _px(70.0))

    def available(self, table: int) -> Scaled:
        return _px(720.0)


def test_the_readouts_are_four_lines_of_counts_and_sizes() -> None:
    board: Any = _StandIn()
    lines = readouts(board)
    assert lines == (
        "table 1 of 1  ·  automatic  ·  720 px wide in a 720 px measure"
        "  ·  1 of 2 columns under natural width, 0 at the floor",
        "width / natural / floor, px:  300 / 110 / 80  ·  420 / 500 / 70",
        "last drag: none yet",
        "link under the pointer: none  ·  clicked: 0, last: none yet",
    )

    board.widths = (_px(650.0), _px(70.0))
    board.chosen[3] = board.widths
    board.rows_set, board.cells_measured, board.relayouts = 5, 0, 2
    board.view.hovered_link = "https://example.org/a"
    board.followed.append("https://example.org/b")
    lines = readouts(board)
    assert len(lines) == 4
    assert lines[0].startswith("table 1 of 1  ·  dragged  ·  720 px wide")
    assert "1 of 2 columns under natural width, 1 at the floor" in lines[0]
    assert lines[1].endswith("650 / 110 / 80  ·  70 / 500 / 70")
    assert lines[2] == (
        "last drag: 5 table rows set again, 0 cells measured again (the library's own counts)"
        "  ·  layouts caused by dragging so far: 2"
    )
    assert lines[3] == (
        "link under the pointer: https://example.org/a"
        "  ·  clicked: 1, last: https://example.org/b"
    )

    # Change and cost, never quality (docs/visual-review.md).
    banned = ("better", "worse", "good", "bad", "clean", "nice", "crisp", "ugly", "correct")
    for line in lines:
        assert not any(word in line.lower().split() for word in banned)


def test_the_readouts_stay_four_lines_with_no_table_and_before_a_layout() -> None:
    board: Any = _StandIn()
    board.width = None
    assert readouts(board)[:2] == ("not laid out yet", "")
    board.width, board.widths = _px(720.0), ()
    assert readouts(board)[:2] == ("not laid out yet", "")
    board.focus, board.tables = None, ()
    lines = readouts(board)
    assert lines[:2] == ("no table in this document", "") and len(lines) == 4


class _Board(_StandIn):
    """
    A board whose view fails where `fail` says, as the views report a library switched off.
    """

    def __init__(self, fail: str, error: type[Exception] = TypesetUnavailable) -> None:
        super().__init__()
        self.fail = fail
        self.error = error
        self.calls: list[str] = []

    def _maybe(self, name: str) -> None:
        self.calls.append(name)
        if self.fail == name:
            raise self.error("imtypeset failed and is switched off: Error: no")

    def columns(self, table: int) -> tuple[Scaled, ...]:
        self._maybe("columns")
        return self.widths

    def settle(self, width: Scaled) -> None:
        self._maybe("settle")


@pytest.mark.parametrize("where", ["columns", "settle"])
def test_a_library_that_fails_anywhere_in_the_frame_leaves_the_page_alive_saying_why(
    where: str, unasked: None
) -> None:
    """
    `columns` is asked by the readouts, outside the pane; `settle` is the
    first thing inside it. Either way `TypesetUnavailable` does not leave
    `draw`, the pane (if begun) is ended, and the next frame is the one line.
    """
    made = page.TablesPage(_context("tables"))
    board: Any = _Board(where)
    made.board = board
    made.held = (3, 0)
    assert made.renderer == "TypesetView"
    _frame(made.draw)  # would raise "Missing EndChild" if the pane were left open
    assert made.board is None and made.renderer == "none" and made.held is None
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    calls = len(board.calls)
    _frame(made.draw)
    assert len(board.calls) == calls and made.frames == 2
    assert made.report() == [f"frames=2 renderer=none reason={made.reason!r}"]


def test_an_exception_that_is_not_typeset_unavailable_propagates(unasked: None) -> None:
    made = page.TablesPage(_context("tables"))
    board: Any = _Board("settle", ZeroDivisionError)
    made.board = board
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    _frame(draw)
    assert len(raised) == 1 and made.board is board and made.renderer == "TypesetView"


# ----------------------------------------------------------------------
# 3. With the library: the page over `TypesetView`, in frames with no backend
# ----------------------------------------------------------------------
#
# Everything above runs in this process, where the library is never ready.
# What follows is ONE child process with the library loaded and its fonts
# given, driving the page through real ImGui frames with mouse events queued;
# each test reads its part of the report. Skipped, with the reason, when
# `IMTYPESET_LIBRARY` is not set.

_TYPESET = r"""
import json, sys

from imgui_bundle import imgui

from imscribe import typesetter
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import tables as page
from imscribe.ui.typeset_view import TypesetUnavailable
from imscribe.primitives import px_from_sp, sp_from_px

SIZE = (1300.0, 800.0)
OFF = (-1.0e6, -1.0e6)
def loaded():
    return sorted(name for name in sys.modules if name.split(".")[0] == "imscribe")

report = {"module": typesetter.module() is not None, "loaded_at_import": loaded()}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(*SIZE)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
ts = typesetter.module()
calls = []

class Counting:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)
    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            calls.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)
        return call

ts._lib = Counting(ts._lib)

def frame(made, *, mouse=None, button=None):
    # One frame of the page in a full-size window of a context with no backend.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##imscribe-tables-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            calls.clear()
            made.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return list(calls)

def context(options=(), count=None):
    # What `--tab tables:floors,600` makes of itself, without the app (which loads everything).
    return PageContext.build(request_page="tables", request_options=options, request_count=count)

def on_screen(made, table, edge):
    board = made.board
    origin = board.view.origin
    grip = next(g for g in board.grips() if (g.table, g.edge) == (table, edge))
    return (origin[0] + px_from_sp(grip.x, board.px_per_inch),
            origin[1] + px_from_sp(grip.top, board.px_per_inch) + 12.0)

def px(values, board):
    return [px_from_sp(value, board.px_per_inch) for value in values]

def edges(board, table):
    count = board.view.table_geometry(table).column_count
    return [board.view.table_column(table, n) for n in range(count)]

def park(made):
    frame(made, mouse=OFF, button=False)
    frame(made)

# 1. The page as it opens.
made = page.TablesPage(context())
first = frame(made, mouse=OFF, button=False)
frame(made)
steady = [frame(made) for _ in range(3)]
board = made.board
report["loaded_after_five_frames"] = loaded()
width_px = px_from_sp(board.width, board.px_per_inch)
report["opening"] = {
    "renderer": made.renderer, "board": type(board).__name__, "reason": made.reason,
    "frames": made.frames, "chosen": dict(board.chosen), "held": made.held,
    "width_px": width_px, "width_sp": board.width, "tables": list(board.tables),
    "grips": len(board.grips()),
    "drift": made.cursor_drift, "whole": made.whole,
    "rows_set": board.rows_set, "relayouts": board.relayouts,
    "first_calls": first, "steady_calls": steady,
    "readouts": list(page.readouts(board)),
    "report": made.report(),
    "columns": [px(board.columns(t), board) for t in board.tables],
    "natural": [px(board.natural(t), board) for t in board.tables],
    "floors": [px(board.floors(t), board) for t in board.tables],
    "available": [board.available(t) for t in board.tables],
    "under_floor": [sum(w < f for w, f in zip(board.columns(t), board.floors(t)))
                    for t in board.tables],
    "grip_tops": [[g.table, g.edge, px_from_sp(g.x, board.px_per_inch)]
                  for g in board.grips() if g.table == board.tables[0]],
    "first_table_edges": [e.max for e in edges(board, board.tables[0])],
}

# 2. A handle hovered, pressed and moved.
table = board.tables[0]
before = board.columns(table)
x, y = on_screen(made, table, 0)
frame(made, mouse=(x + 2.0, y))
hovered = {"held": made.held, "chosen": dict(board.chosen)}
frame(made, button=True)
pressed = {"held": made.held, "chosen": dict(board.chosen), "selection": board.view.selection}
drag_calls = frame(made, mouse=(x + 2.0 - 100.0, y))
moved = board.columns(table)
geometry = board.view.table_geometry(table)
gesture = {
    "hovered": hovered, "pressed": pressed, "held": made.held,
    "moved_sp": before[0] - moved[0], "hundred_sp": sp_from_px(100.0, board.px_per_inch),
    "sums": [sum(before), sum(moved)], "relayouts": board.relayouts,
    "rows_set": board.rows_set, "cells_measured": board.cells_measured,
    "stated": geometry.stated, "calls": drag_calls,
    "edges_px": [[e.min, e.max] for e in edges(board, table)], "moved_px": px(moved, board),
    "grip_x": [board.grips()[0].x, moved[0]],
    "others_stated": [board.view.table_geometry(t).stated for t in board.tables[1:]],
}
after_drag = frame(made)
frame(made, mouse=(x + 2.0 - 130.0, y))
gesture["second"] = [board.relayouts, before[0] - board.columns(table)[0],
                     sp_from_px(130.0, board.px_per_inch)]
frame(made, button=False)
frame(made)
gesture["released"] = [made.held, board.view.selection]
settled = board.columns(table)
frame(made, mouse=(x + 300.0, y))
frame(made)
gesture["button_up"] = [board.columns(table) == settled, board.relayouts]
gesture["frame_after_a_drag"] = after_drag
gesture["readouts"] = list(page.readouts(board))
gesture["report"] = made.report()
report["gesture"] = gesture

# 3. Past everything: the floors. Then reset.
x, y = on_screen(made, table, 0)
total = sum(board.columns(table))
frame(made, mouse=(x, y))
frame(made, button=True)
frame(made, mouse=(-50000.0, y))
low = [board.columns(table)[0], board.floors(table)[0], sum(board.columns(table))]
frame(made, mouse=(50000.0, y))
high = [board.columns(table)[1], board.floors(table)[1], sum(board.columns(table))]
frame(made, button=False)
park(made)
report["floors"] = {"total": total, "low": low, "high": high,
                    "edges_px": [e.max - e.min for e in edges(board, table)],
                    "floor_px": px(board.floors(table), board)}
reset = board.reset()
frame(made)
frame(made)
report["reset"] = {"changed": reset, "chosen": dict(board.chosen),
                   "stated": board.view.table_geometry(table).stated,
                   "back": board.columns(table) == before, "again": board.reset(),
                   "rows_set": board.rows_set}

# 4. A press on text selects and drags no column; the selection outlives a drag.
relayouts = board.relayouts
rect = board.view.block_rect(1)
frame(made, mouse=(rect[0] + 40.0, rect[1] + 30.0))
frame(made, button=True)
frame(made, mouse=(rect[0] + 200.0, rect[1] + 30.0))
frame(made, button=False)
frame(made)
selection = board.view.selection
x, y = on_screen(made, table, 0)
frame(made, mouse=(x, y))
frame(made, button=True)
frame(made, mouse=(x - 60.0, y))
frame(made, button=False)
park(made)
report["text"] = {"selection": selection, "text": board.view.selected_text(),
                  "relayouts": [relayouts, board.relayouts],
                  "after_a_drag": board.view.selection}
board.reset()
park(made)

# 5. A narrow measure squeezes chosen widths, and they come back.
x, y = on_screen(made, table, 0)
frame(made, mouse=(x, y))
frame(made, button=True)
frame(made, mouse=(x + 80.0, y))
frame(made, button=False)
park(made)
chosen = board.columns(table)
counted = board.relayouts
made.pane_px = 300.0
frame(made)
frame(made)
narrow = {"columns": board.columns(table), "available": board.available(table),
          "floors": board.floors(table), "wish": board.chosen[table],
          "edges_px": [e.max - e.min for e in edges(board, table)],
          "relayouts": board.relayouts - counted}
made.pane_px = page.DEFAULT_PANE_PX
frame(made)
frame(made)
report["squeezed"] = {"chosen": chosen, "narrow": narrow, "back": board.columns(table) == chosen}
board.reset()
park(made)

# 6. A link in a cell, before and after its table is dragged.
LINKED = (
    "Before.\n\n"
    "| Rule | Where |\n| --- | --- |\n"
    "| hpack | [the packer](https://example.org/pack) and some more words to wrap |\n"
    "| vpack | [the stacker](https://example.org/stack) |\n\nAfter.\n"
)
linked = page.TablesPage(context())
linked.board = page.TypesetBoard(theme=linked.context.theme,
                                 px_per_inch=linked.context.px_per_inch, text=LINKED)
park(linked)
frame(linked)
board2 = linked.board
def link_point(number):
    row = board2.view.links[number]
    doc = board2.view.native_document
    x0, y0, _, y1 = doc.caret_rect((row.block, row.start + 2))
    x1 = doc.caret_rect((row.block, row.start + 3))[0]
    ox, oy = board2.view.origin
    return (ox + (x0 + x1) / 2.0, oy + (y0 + y1) / 2.0)
def click(point):
    frame(linked, mouse=point)
    frame(linked)
    hovered = board2.view.hovered_link
    frame(linked, button=True)
    frame(linked, button=False)
    frame(linked)
    return hovered
links = {"targets": [row.target for row in board2.view.links]}
links["first"] = [click(link_point(0)), list(board2.followed)]
t2 = board2.tables[0]
x, y = on_screen(linked, t2, 0)
frame(linked, mouse=(x, y))
frame(linked, button=True)
frame(linked, mouse=(x + 90.0, y))
frame(linked, button=False)
park(linked)
links["dragged"] = t2 in board2.chosen
links["second"] = [click(link_point(1)), list(board2.followed)]
links["readout"] = page.readouts(board2)[3]
links["selection"] = board2.view.selection
report["links"] = links
park(linked)

# 7. The floors option: the opening state is not a drag.
opened = page.TablesPage(context(("floors",), 600))
park(opened)
frame(opened)
board3 = opened.board
report["option"] = {
    "width_px": px_from_sp(board3.width, board3.px_per_inch),
    "chosen": sorted(board3.chosen) == list(board3.tables),
    "at_floors": [board3.columns(t) == board3.floors(t) for t in board3.tables],
    "edges_at_floors": [
        max(
            abs((e.max - e.min) - f)
            for e, f in zip(edges(board3, t), px(board3.floors(t), board3))
        )
        for t in board3.tables
    ],
    "rows_set": board3.rows_set, "relayouts": board3.relayouts,
    "wrapped": [any(board3.view.table_row(t, r).wrapped
                    for r in range(board3.view.table_geometry(t).row_count))
                for t in board3.tables],
}

# 8. The library fails mid-run: the page stays alive and says why from the next frame.
def failed(where, error=TypesetUnavailable):
    failing = page.TablesPage(context())
    park(failing)
    target = failing.board.view
    def broken(*args, **kwargs):
        raise error("imtypeset failed and is switched off: Error: no")
    setattr(target, where, broken)
    raised = []
    real_draw = failing.draw
    def guarded():
        try:
            real_draw()
        except ZeroDivisionError as exc:
            raised.append(type(exc).__name__)
    failing.draw = guarded
    frame(failing)              # `frame` ends the window: a pane left open would assert
    fallen = {"renderer": failing.renderer, "board": type(failing.board).__name__,
              "reason": failing.reason, "whole": failing.whole, "held": failing.held,
              "raised": raised}
    if not raised:
        fallen["later_calls"] = [frame(failing), frame(failing)]
        fallen["later"] = [failing.renderer, failing.frames, failing.report()]
    return fallen
# `draw` is the view's own; `layout_for` is the page's first call inside the pane;
# `block_under_mouse` is asked by the handles.
report["fallen"] = {where: failed(where) for where in ("draw", "layout_for", "block_under_mouse")}
report["not_caught"] = failed("draw", ZeroDivisionError)

# 9. A press on the frame the pointer arrives is the handle's.
arriving = page.TablesPage(context())
park(arriving)
frame(arriving)
board4 = arriving.board
t4 = board4.tables[0]
before4 = board4.columns(t4)
x, y = on_screen(arriving, t4, 0)
frame(arriving, mouse=(x, y), button=True)
arrival = {"held": arriving.held}
frame(arriving, mouse=(x - 80.0, y))
frame(arriving, mouse=(x - 80.0, y))
arrival["chosen"] = t4 in board4.chosen
arrival["narrower"] = board4.columns(t4)[0] < before4[0]
arrival["selection"] = board4.view.selection
frame(arriving, button=False)
frame(arriving)
arrival["released"] = arriving.held
report["arrival"] = arrival
park(arriving)

# 10. No demo directory: the built-in table. And a document with no table in it.
found = page.demo_text
page.demo_text = lambda name: None
try:
    builtin = page.TablesPage(context(count=400))
finally:
    page.demo_text = found
park(builtin)
frame(builtin)
report["builtin"] = {"tables": len(builtin.board.tables), "grips": len(builtin.board.grips()),
                     "text": builtin.board.view.texts[0]}
bare = page.TablesPage(context())
bare.board = page.TypesetBoard(theme=bare.context.theme, px_per_inch=bare.context.px_per_inch,
                               text="Only a paragraph, and no table.\n")
before_layout = [bare.board.drag(0, 0, 100.0), list(bare.board.grips())]
park(bare)
frame(bare)
report["no_table"] = {"tables": list(bare.board.tables), "focus": bare.board.focus,
                      "before_layout": before_layout,
                      "drag": bare.board.drag(0, 0, 100.0), "grips": len(bare.board.grips()),
                      "reset": bare.board.reset(), "readouts": list(page.readouts(bare.board)),
                      "whole": bare.whole}
report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    done = subprocess.run(
        [sys.executable, "-B", "-c", _TYPESET],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    (line,) = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    got: dict[str, Any] = json.loads(line[len("REPORT ") :])
    # In the child: this is the process that draws.
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got["reason"]
    assert got["trouble"] == "" and got["module_at_end"] is True
    return got


_FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]
_LAYOUT_FOR = ["LayoutDocument", "GetDocumentSize"]


def test_with_the_library_the_page_opens_on_a_typeset_board_and_the_same_columns(
    typeset: dict[str, Any],
) -> None:
    """
    The library's widths, natural widths and floors for all five tables at
    the page's 720 px are the old board's (`OLD_BOARD`, frozen) to a
    ten-thousandth of a pixel, so the first two readout lines are the text
    the old board gave, there are as many handles (17), and no automatic
    column reads as under its floor.
    """
    opening = typeset["opening"]
    assert (opening["renderer"], opening["board"], opening["reason"]) == (
        "TypesetView",
        "TypesetBoard",
        "",
    )
    assert opening["chosen"] == {} and opening["held"] is None
    assert opening["whole"] is True
    assert opening["rows_set"] is None and opening["relayouts"] == 0
    assert opening["width_px"] == pytest.approx(page.DEFAULT_PANE_PX, abs=0.001)
    assert opening["width_sp"] == OLD_BOARD["width_sp"]
    assert opening["tables"] == OLD_BOARD["tables"] == [4, 7, 10, 13, 16]
    assert opening["grips"] == OLD_BOARD["handles"] == 17
    assert opening["drift"] == 0.0
    for what in ("columns", "natural", "floors"):
        assert len(opening[what]) == len(OLD_BOARD[what]) == 5
        for ours, theirs in zip(opening[what], OLD_BOARD[what], strict=True):
            assert ours == pytest.approx(theirs, abs=0.0001), what
    assert opening["available"] == OLD_BOARD["available"]
    assert opening["under_floor"] == [0] * 5
    assert opening["readouts"][:2] == OLD_BOARD["readouts"]
    assert opening["readouts"][2] == "last drag: none yet"
    assert len(opening["readouts"]) == 4
    # A handle is on the column's edge as the library laid the table out.
    for (_, _, x), edge in zip(opening["grip_tops"], opening["first_table_edges"], strict=True):
        assert x == pytest.approx(edge, abs=0.001)
    total = dict(part.split("=", 1) for part in opening["report"][0].split() if "=" in part)
    assert total["renderer"] == "TypesetView" and total["tables"] == "5"
    assert int(total["vertices"]) > 1000 and total["whole"] == "1"
    assert len(opening["report"]) == 6


def test_with_the_library_a_frame_of_the_page_is_five_calls_and_the_handles_ask_once(
    typeset: dict[str, Any],
) -> None:
    """
    A steady frame: the layout before the handles (`layout_for`: two calls)
    and the view's own three. The handles' geometry is asked on the first
    frame (a call a table and a call a column, the natural widths and the
    floors with them) and again only when the measure, the document's height
    or the chosen widths change. On a frame a column is dragged: the
    library's counters before, one `SetDocumentTableColumns`, the layout
    again, where each table is (a call each: the rows below the dragged
    table moved), the draw, and the counters after.
    """
    opening = typeset["opening"]
    assert opening["steady_calls"] == [[*_LAYOUT_FOR, *_FRAME]] * 3
    first = opening["first_calls"]
    assert first[:6] == [
        "GetCurrentContext",
        "CreateDocument",
        "SetDocumentBlocks",
        "SetDocumentOptions",
        *_LAYOUT_FOR,
    ]
    assert first[-3:] == _FRAME
    asked = first[6:-3]
    assert set(asked) == {"GetDocumentTableGeometry", "GetDocumentTableColumn"}
    gesture = typeset["gesture"]
    assert gesture["calls"] == [
        *_LAYOUT_FOR,
        "GetDocumentStats",
        "SetDocumentTableColumns",
        *_LAYOUT_FOR,
        *["GetDocumentTableGeometry"] * 5,
        *_FRAME,
        "GetDocumentStats",
    ]
    # The pointer held still on the handle: nothing is stated and nothing asked.
    assert gesture["frame_after_a_drag"] == [*_LAYOUT_FOR, *_FRAME]


def test_with_the_library_importing_the_page_and_opening_it_load_no_old_view(
    typeset: dict[str, Any],
) -> None:
    """
    What is in `sys.modules` of the old core (`tests/test_typeset_closure.py`'s
    list) at two moments of the child. Importing the page: nothing (two
    leaves until T5-B2). After five frames drawn through the library:
    nothing either. Until 2026-10-12 it was `fontlib` and the `fontmetrics`
    it imports, because `typesetter.load_fonts` read the font files from
    it; the table of files is `imscribe.fontfiles`' now (`Theme.build`
    loaded `nodes`, `pack` and `badness` until T5-B2). **No line breaker, no
    ship-out, no selection model, no compositor, no node, no draw backend.**
    """
    core = closure.REFERENCE_CORE
    assert set(typeset["loaded_at_import"]) & core == set()
    opened = set(typeset["loaded_after_five_frames"])
    assert opened & core == set()
    assert "imscribe.markdown" not in opened and "imscribe.ui.typeset_view" in opened


def test_with_the_library_a_handle_hovered_pressed_and_moved_states_the_columns(
    typeset: dict[str, Any],
) -> None:
    gesture = typeset["gesture"]
    assert gesture["hovered"] == {"held": None, "chosen": {}}
    # A press alone moves nothing and selects nothing.
    assert gesture["pressed"] == {"held": [4, 0], "chosen": {}, "selection": None}
    assert gesture["held"] == [4, 0]
    # The edge kept its 2 px offset from the pointer: 100 px, to the scaled point's rounding.
    assert abs(gesture["moved_sp"] - gesture["hundred_sp"]) <= 1
    before, after = gesture["sums"]
    assert before == after
    assert gesture["relayouts"] == 1
    # The library's own account of the drag: the dragged table's five rows
    # set again, and not one cell measured again.
    assert gesture["rows_set"] == 5 and gesture["cells_measured"] == 0
    # The layout the frame drew is the one with the new widths: no frame of lag.
    assert gesture["stated"] is True and gesture["others_stated"] == [False] * 4
    (first_min, first_max), (second_min, second_max) = gesture["edges_px"]
    assert first_min == 0.0 and first_max == second_min
    assert [first_max - first_min, second_max - second_min] == pytest.approx(
        gesture["moved_px"], abs=0.001
    )
    assert gesture["grip_x"][0] == gesture["grip_x"][1]
    relayouts, moved, wanted = gesture["second"]
    assert relayouts == 2 and abs(moved - wanted) <= 1
    assert gesture["released"] == [None, None]
    # With the button up, moving the pointer moves nothing.
    assert gesture["button_up"] == [True, 2]
    assert gesture["readouts"][0].startswith("table 1 of 5  ·  dragged")
    assert gesture["readouts"][2] == (
        "last drag: 5 table rows set again, 0 cells measured again (the library's own counts)"
        "  ·  layouts caused by dragging so far: 2"
    )


def test_with_the_library_a_drag_stops_at_the_floors_and_reset_gives_the_table_back(
    typeset: dict[str, Any],
) -> None:
    floors = typeset["floors"]
    column, floor, total = floors["low"]
    assert column == floor and total == floors["total"]
    column, floor, total = floors["high"]
    assert column == floor and total == floors["total"]
    # As the library has it: the second column is its floor wide, to the pixel's fraction.
    assert floors["edges_px"][1] == pytest.approx(floors["floor_px"][1], abs=0.001)
    reset = typeset["reset"]
    assert reset["changed"] is True and reset["chosen"] == {} and reset["again"] is False
    # Fitted by the library again, to the very widths it had before any drag.
    assert reset["stated"] is False and reset["back"] is True


def test_with_the_library_a_press_on_text_selects_and_the_selection_outlives_a_drag(
    typeset: dict[str, Any],
) -> None:
    text = typeset["text"]
    (block, start), (same, end) = text["selection"]
    assert block == same == 1 and end > start and len(text["text"]) == end - start
    # The press on the text dragged nothing; the drag after it was one.
    before, after = text["relayouts"]
    assert after == before + 1
    assert text["after_a_drag"] == text["selection"]


def test_with_the_library_chosen_widths_are_squeezed_by_a_narrow_measure_and_come_back(
    typeset: dict[str, Any],
) -> None:
    """
    The library uses stated widths as given, so the squeeze is the page's
    (`fitted`), and the widths the library is given are the squeezed ones.
    """
    squeezed = typeset["squeezed"]
    narrow = squeezed["narrow"]
    assert narrow["wish"] == squeezed["chosen"] and sum(narrow["wish"]) > narrow["available"]
    assert sum(narrow["columns"]) == narrow["available"]
    assert all(
        width >= floor for width, floor in zip(narrow["columns"], narrow["floors"], strict=True)
    )
    assert narrow["columns"] == list(fitted(narrow["wish"], narrow["floors"], narrow["available"]))
    assert narrow["edges_px"] == pytest.approx(
        [px_from_sp(width, DENSITY) for width in narrow["columns"]], abs=0.001
    )
    # A change of measure is not a drag.
    assert narrow["relayouts"] == 0
    assert squeezed["back"] is True


def test_with_the_library_a_link_in_a_cell_is_clicked_before_and_after_its_table_is_dragged(
    typeset: dict[str, Any],
) -> None:
    links = typeset["links"]
    pack, stack = links["targets"]
    assert links["first"] == [pack, [pack]]
    assert links["dragged"] is True
    assert links["second"] == [stack, [pack, stack]]
    assert "clicked: 2" in links["readout"] and links["selection"] is None


def test_with_the_library_the_floors_option_opens_every_table_at_its_floors(
    typeset: dict[str, Any],
) -> None:
    option = typeset["option"]
    assert option["width_px"] == pytest.approx(600.0, abs=0.001)
    assert option["chosen"] is True and option["at_floors"] == [True] * 5
    assert max(option["edges_at_floors"]) < 0.001
    assert option["wrapped"] == [True] * 5
    # The opening state is the first layout, not a drag.
    assert option["rows_set"] is None and option["relayouts"] == 0


def test_with_the_library_a_view_that_fails_mid_run_leaves_the_page_alive_saying_why(
    typeset: dict[str, Any],
) -> None:
    """
    A view call raising `TypesetUnavailable` -- the draw, the layout before
    it, or the question the handles ask -- does not leave `draw`: the board
    is dropped, and every frame after it is the one line, with not one call
    of the library's.
    """
    reason = "imtypeset failed and is switched off: Error: no"
    assert sorted(typeset["fallen"]) == ["block_under_mouse", "draw", "layout_for"]
    for where, fallen in typeset["fallen"].items():
        assert (fallen["renderer"], fallen["board"], fallen["raised"]) == (
            "none",
            "NoneType",
            [],
        ), where
        assert fallen["reason"] == reason
        assert fallen["whole"] is None and fallen["held"] is None
        assert fallen["later_calls"] == [[], []]
        assert fallen["later"] == ["none", 5, [f"frames=5 renderer=none reason={reason!r}"]]


def test_with_the_library_an_exception_that_is_not_typeset_unavailable_propagates(
    typeset: dict[str, Any],
) -> None:
    kept = typeset["not_caught"]
    assert kept["raised"] == ["ZeroDivisionError"]
    assert (kept["renderer"], kept["board"], kept["reason"]) == ("TypesetView", "TypesetBoard", "")


def test_with_the_library_a_press_on_the_frame_the_pointer_arrives_is_the_handles(
    typeset: dict[str, Any],
) -> None:
    """
    A mouse hovers for a frame before it can press. An injected event need
    not: move and press queued together reach the page on one frame. The
    handles are submitted before the view draws, so the handle is ImGui's
    hovered item by the time the view judges the press: the column moves and
    nothing is selected.
    """
    arrival = typeset["arrival"]
    assert arrival["held"] == [4, 0]
    assert arrival["chosen"] is True and arrival["narrower"] is True
    assert arrival["selection"] is None and arrival["released"] is None


def test_with_the_library_and_no_demo_directory_the_page_shows_its_built_in_table(
    typeset: dict[str, Any],
) -> None:
    builtin = typeset["builtin"]
    assert (builtin["tables"], builtin["grips"]) == (1, 2)
    assert builtin["text"] == "No demo/ directory was found, so this is the only table."


def test_with_the_library_a_document_with_no_table_has_no_handle_and_no_drag(
    typeset: dict[str, Any],
) -> None:
    none = typeset["no_table"]
    assert none["tables"] == [] and none["focus"] is None and none["grips"] == 0
    assert none["before_layout"] == [False, []]
    assert none["drag"] is False and none["reset"] is False and none["whole"] is True
    assert none["readouts"][:3] == ["no table in this document", "", "last drag: none yet"]


# ----------------------------------------------------------------------
# 4. The real app in a real window
# ----------------------------------------------------------------------

GESTURE = """
import sys

from imgui_bundle import hello_imgui, imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app
from imscribe.primitives import px_from_sp

WANT_LIBRARY = sys.argv[1] == "with"
state = {"frames": 0, "step": 0}
real_gui = imscribe_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        # No operator will wake an idling app.
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    state["frames"] += 1
    made = self.page("tables")
    board = made.board
    io = imgui.get_io()
    if state["frames"] < 6:
        return
    if not WANT_LIBRARY:
        if state["frames"] == 12:
            print(
                f"alive=1 board={type(board).__name__} errors={len(self.page_errors)} "
                f"current={self.current} imported={int('imtypeset' in sys.modules)}"
            )
            for line in made.report():
                print(line)
            hello_imgui.get_runner_params().app_shall_exit = True
        return
    if board.view.origin is None:
        return
    table = board.tables[0]
    if state["step"] == 0:
        if WANT_LIBRARY:
            # In the child, not in the test: this is the process that draws.
            assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
            assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
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
            f"sum_kept={int(sum(board.columns(table)) == sum(state['before']))} "
            f"renderer={made.renderer} imported={int('imtypeset' in sys.modules)}"
        )
        for line in made.report():
            print(line)
        hello_imgui.get_runner_params().app_shall_exit = True
    state["step"] += 1


imscribe_app.App.gui = watched_gui
imscribe_app.run(tab="tables")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def _gesture(window: Window, how: str, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    script = window.out / "tables_page_gesture.py"
    script.write_text(textwrap.dedent(GESTURE), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if "=" in line]
    assert len(lines) == (7 if how == "with" else 2), done.stdout
    print(how, window.where, done.stdout)  # shown by pytest when the test fails
    return [_fields(line) for line in lines]


def test_in_a_real_window_without_the_library_the_page_says_why_not_and_stays_alive(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app on `--tab tables`, the library's variables removed: twelve
    frames, no board, no error page, the library not imported, and the
    page's report is its reason.
    """
    alive, total = _gesture(window, "without", monkeypatch)
    assert alive == {
        "alive": "1",
        "board": "NoneType",
        "errors": "0",
        "current": "Tables",
        "imported": "0",
    }
    assert total["renderer"] == "none" and total["frames"] == "12"
    # The reason as the readout quotes it, cut at its first blank; until
    # 2026-10-14 it began 'IMTYPESET_LIBRARY (P43).
    assert total["reason"] == repr(typesetter.SWITCHED_OFF_REASON).split()[0]


def test_a_column_is_dragged_in_a_real_window_with_the_library(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The same gesture with the library drawing: a `TypesetBoard`, in the child.

    The child asserts `typesetter.module()` and `ready()` before the gesture,
    so this cannot pass through the "why not" line. Hover a handle, press,
    ten moves of 12 px, release. Counts only: held, let go, 120 px, the table
    as wide as it was, one table dragged, nothing selected, no column under
    its floor, and the library's own account: each of the ten moves
    stated the columns once and a draw followed (`relayouts`), the last of
    them set table rows again and measured no cell again, and vertices
    reached the draw list. (That the page's module loads nothing of the old
    core is measured where imports are, further up; the app around it does.)
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    gesture, total, *tables = _gesture(window, "with", monkeypatch)
    assert gesture["renderer"] == "TypesetView" == total["renderer"]
    assert gesture["imported"] == "1"
    assert gesture["held"] == "1" and gesture["released"] == "1"
    assert abs(float(gesture["moved_px"]) - 120.0) < 0.5
    assert gesture["sum_kept"] == "1"
    assert total["tables"] == "5" and total["dragged"] == "1"
    assert total["relayouts"] == "10" and total["selected"] == "0"
    assert 0 < int(total["rows_set"]) <= 5 and total["cells_measured"] == "0"
    assert int(total["vertices"]) > 1000 and total["whole"] == "1"
    assert [entry["state"] for entry in tables] == ["dragged"] + ["automatic"] * 4
    assert all(entry["under_floor"] == "0" for entry in tables)

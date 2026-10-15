r"""
The Columns page: `imscribe.ui.pages.columns`, drawn through
`TypesetView.set_columns` and through nothing else (tranche 5, T5-COLUMNS).

**Four levels, so nobody reads more into a green run than is there.**

1. No ImGui: the two pieces of arithmetic, the state the controls move, and
   what importing the page loads.
2. Frames of a real `ImGuiContext` with no backend, in this process. The
   library is never ready here (nothing called `typesetter.load_fonts()`),
   so this is the ONE LINE that says why not, and the page must not ask for
   the library to find that out. A view that raises is stood in for.
3. With the library, real frames, no window (`child`; skipped with the
   reason when `IMTYPESET_LIBRARY` is not set): a child process loads the
   library's fonts into an atlas nobody renders and drives the page.
4. The real app in a real window (`tests/conftest.py::window`), with the
   library (asserting IN THE CHILD that `typesetter.module()` is not `None`
   and `typesetter.ready()`) and without it.

**Nothing here judges how the page looks.** Columns, calls and vertices are
counted and rectangles compared. `tests/test_columns.py` is the old core's
own and is not this page's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from imscribe import typesetter
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import columns as page
from imscribe.ui.pages.columns import ColumnsPage, pages_of, sheet_width
from imscribe.ui.typeset_view import TypesetUnavailable

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from conftest import Window

ROOT = Path(__file__).resolve().parent.parent
VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
SIZE = (1300.0, 800.0)
NEEDS_LIBRARY = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)
_FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]
_PAGE_FRAME = [*_FRAME, "GetDocumentColumnCount", "GetDocumentStats"]
"""A frame of the page: the view's three calls, then the page's two readouts."""


def _context(count: int | None = None, *options: str, **fields: Any) -> PageContext:
    return PageContext.build(
        request_page="Columns", request_count=count, request_options=options, **fields
    )


# ----------------------------------------------------------------------
# 1. No ImGui
# ----------------------------------------------------------------------

# The old layout core and what stands on it, as `tests/test_typeset_closure.py`
# lists it, with `imscribe.units` and `imscribe.fontmetrics`, which were the
# floor of `imscribe.theme` until T5-B2 and are not loaded any more.
OLD = (
    "imscribe.units",
    "imscribe.fontmetrics",
    "imscribe.badness",
    "imscribe.nodes",
    "imscribe.pack",
    "imscribe.linebreak",
    "imscribe.shipout",
    "imscribe.selection",
    "imscribe.fontlib",
    "imscribe.math",
    "imscribe.mathtext",
    "imscribe.spans",
    "imscribe.columns",
    "imscribe.blocklayout",
    "imscribe.backends",
    "imscribe.markdown",
    "imscribe.style",
    "imscribe.stream",
    "imscribe.ui.bare_view",
    "imscribe.ui.document_view",
    "imscribe.ui.stream_view",
    "imscribe.ui.units",
    "imscribe.ui.composition",
    "imscribe.ui.app",
)

_CLOSURE = r"""
import importlib, json, sys
before = set(sys.modules)
if sys.argv[1] == "from":
    from imscribe.ui.pages import columns
else:
    columns = importlib.import_module("imscribe.ui.pages.columns")
at_import = sorted(m for m in set(sys.modules) - before if m.split(".")[0] == "imscribe")
from imscribe.ui.pages import PageContext
made = columns.PAGE.factory(PageContext.build(request_page="Columns", request_count=3))
lines = made.lines()
built = sorted(m for m in set(sys.modules) - before if m.split(".")[0] == "imscribe")
print(json.dumps({"import": at_import, "built": built, "lines": list(lines),
                  "imgui": "imgui_bundle" in sys.modules, "imtypeset": "imtypeset" in sys.modules}))
"""


def _old(loaded: list[str]) -> list[str]:
    return sorted(
        module
        for module in loaded
        if any(module == one or module.startswith(one + ".") for one in OLD)
    )


@pytest.mark.parametrize("form", ["import", "from"])
def test_importing_and_building_the_page_loads_none_of_the_old_core(form: str) -> None:
    """
    A fresh interpreter with the library's variables removed: the import,
    in both spellings, and then the page BUILT from a context. Neither
    loads `imscribe.columns`, the old views, the old draw backend, the app or
    any other module of the old core; nor Dear ImGui, nor imtypeset. A page
    built with no library holds the one line.

    Building a `Theme` loaded `imscribe.nodes`, `imscribe.pack` and
    `imscribe.badness` until T5-B2 (the theme's interline glue was the old
    core's class) and those three were allowed after the build. A style's
    leading is a number now and nothing is allowed at either moment.
    """
    env = {key: value for key, value in os.environ.items() if key not in VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CLOSURE, form],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    assert done.returncode == 0, done.stderr
    told = json.loads(done.stdout.strip().splitlines()[-1])
    assert _old(told["import"]) == [], (form, _old(told["import"]))
    assert "imscribe.ui.pages.columns" in told["import"]
    assert "imscribe.ui.typeset_view" in told["import"]
    assert _old(told["built"]) == [], (form, _old(told["built"]))
    assert told["imgui"] is False and told["imtypeset"] is False
    assert len(told["lines"]) == 1 and told["lines"][0].startswith(page.NOT_DRAWING)


def test_the_sheet_is_the_pane_up_to_a_widest_column_each() -> None:
    """
    `count` columns of at most `TEXT_WIDTH_PX` and the gutters between
    them, or the pane when that is narrower; never narrower than a view can
    be laid out at.
    """
    assert sheet_width(2000.0, 1, 20.0) == page.TEXT_WIDTH_PX
    assert sheet_width(2000.0, 3, 20.0) == 3 * page.TEXT_WIDTH_PX + 40.0
    assert sheet_width(900.0, 3, 20.0) == 900.0
    assert sheet_width(900.0, 1, 20.0) == page.TEXT_WIDTH_PX
    assert sheet_width(0.0, 2, 20.0) > 0.0
    assert sheet_width(-50.0, 2, 20.0) == sheet_width(0.0, 2, 20.0)


@pytest.mark.parametrize(
    ("columns", "count", "pages"),
    [(1, 1, 1), (12, 3, 4), (13, 3, 5), (2, 3, 1), (0, 3, 1), (7, 1, 7), (9, 2, 5)],
)
def test_pages_are_the_columns_in_groups_of_the_count(columns: int, count: int, pages: int) -> None:
    assert pages_of(columns, count) == pages


def test_the_launch_names_the_count_and_the_fill() -> None:
    """
    `--tab columns:3` is three columns, `columns:5` adds a button for five,
    `columns:3,balance` opens balanced, and no count is `DEFAULT_COUNT`. A
    count given to ANOTHER page is not this page's.
    """
    assert page.PAGE.name == "Columns" and page.PAGE.shots == ("1", "2", "3")
    assert page.PAGE.accepts("balance") and page.PAGE.accepts("3")
    plain = ColumnsPage(_context())
    assert (plain.count, plain.counts, plain.balance) == (page.DEFAULT_COUNT, (1, 2, 3), False)
    three = ColumnsPage(_context(3))
    assert (three.count, three.counts) == (3, (1, 2, 3))
    five = ColumnsPage(_context(5))
    assert (five.count, five.counts) == (5, (1, 2, 3, 5))
    assert ColumnsPage(_context(3, "balance")).balance is True
    other = PageContext.build(request_page="Document", request_count=3, request_options=())
    assert ColumnsPage(other).count == page.DEFAULT_COUNT


def test_a_count_the_library_would_refuse_is_refused_where_the_launch_is_parsed() -> None:
    """
    B1 (T5-R #5). `--tab columns:4097` was a valid request (any integer of 1
    or more is), the page was built with it, and `TypesetView.set_columns`
    raised `ValueError` inside the page's `draw` on the first frame with the
    library: the app's traceback page, and `PageError` after the window
    closed. The count is now held to the page's own limit
    (`PageSpec.max_count`, the view's `MAX_COLUMNS`) by
    `imscribe.ui.app.parse_tab_request`, before a window opens, in the words
    every other refused option gets. The same integer is still another
    page's to read as it likes (`stress:5000` is a number of paragraphs).
    """
    from imscribe.ui.app import parse_tab_request
    from imscribe.ui.typeset_view import MAX_COLUMNS

    assert page.PAGE.max_count == MAX_COLUMNS
    assert parse_tab_request(f"columns:{MAX_COLUMNS}").columns == MAX_COLUMNS
    with pytest.raises(ValueError, match=f"at most {MAX_COLUMNS}") as refused:
        parse_tab_request(f"columns:{MAX_COLUMNS + 1}")
    assert "Columns" in str(refused.value) and str(MAX_COLUMNS + 1) in str(refused.value)
    with pytest.raises(ValueError, match="at most"):
        parse_tab_request(f"columns:balance,{MAX_COLUMNS + 1},debug")
    assert not page.PAGE.accepts(str(MAX_COLUMNS + 1)) and page.PAGE.accepts(str(MAX_COLUMNS))
    # Another page's integer is not held to this page's limit.
    assert parse_tab_request(f"stress:{MAX_COLUMNS + 1}").columns == MAX_COLUMNS + 1
    # And what the limit is there to prevent: the view refuses the count at the call.
    view = object.__new__(page.TypesetView)
    with pytest.raises(ValueError, match="count is"):
        view.set_columns(MAX_COLUMNS + 1, height=300.0)


def test_the_text_is_the_launch_s_columns_source_then_its_source_then_the_demo_file() -> None:
    assert ColumnsPage(_context(), "given\n").text == "given\n"
    assert ColumnsPage(_context(columns_source="c\n", source="s\n")).text == "c\n"
    assert ColumnsPage(_context(source="s\n")).text == "s\n"
    assert ColumnsPage(_context()).text == (ROOT / "demo" / "columns.md").read_text("utf-8")


def test_the_controls_move_state_that_needs_no_library() -> None:
    """
    `pick`, `set_balance`, `turn` and `columns_wanted`: what each control
    does, with no view and no ImGui. A turn is held to the pages there are;
    a new count or another fill goes back to the first page; balance with
    one column is the uncut document.
    """
    made = ColumnsPage(_context(3))
    assert made.columns_wanted(480.0) == {"count": 3, "height": 480.0}
    assert made.columns_wanted(3.0) == {"count": 3, "height": page.MIN_HEIGHT_PX}
    made.columns = 11  # what the library would have said
    assert made.pages == 4
    assert [made.turn(1), made.turn(1), made.turn(1), made.turn(1)] == [1, 2, 3, 3]
    assert [made.turn(-1), made.turn(-9)] == [2, 0]
    made.turn(2)
    made.pick(2)
    assert (made.count, made._turn_to, made.pages) == (2, 0, 6)
    made.pick(7)
    assert made.counts == (1, 2, 3, 7)
    for bad in (0, -1, 2.0, True, "3"):
        with pytest.raises(ValueError, match="column count"):
            made.pick(bad)  # type: ignore[arg-type]
    assert made.count == 7
    made.turn(1)
    made.set_balance(True)
    assert (made.balance, made._turn_to, made.pages) == (True, 0, 1)
    assert made.columns_wanted(480.0) == {"count": 7, "balance": True}
    made.pick(1)
    assert made.columns_wanted(480.0) is None


# ----------------------------------------------------------------------
# 2. Frames with no backend: the one line
# ----------------------------------------------------------------------


@pytest.fixture
def unasked(monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    `imscribe.typesetter` as at import, and a `module()` that fails the test if asked.
    """
    typesetter._forget()
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("the page asked for the library"))
    yield
    typesetter._forget()


def _frame(draw: Any) -> dict[str, Any]:
    """
    One frame of a context with no backend, `draw()` in a full-size window.

    The vertex count, and the names of the windows that drew anything.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.add_mouse_pos_event(-1.0e6, -1.0e6)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##imscribe-page-columns-test", None, imgui.WindowFlags_.no_title_bar.value)
        before = imgui.get_window_draw_list().vtx_buffer.size()
        try:
            # What `draw` raises leaves here as itself: the window is ended first.
            draw()
            own = imgui.get_window_draw_list().vtx_buffer.size() - before
        finally:
            imgui.end()
    finally:
        imgui.render()
    data = imgui.get_draw_data()
    return {"vertices": int(data.total_vtx_count), "own": int(own), "lists": len(data.cmd_lists)}


def test_without_the_library_the_page_is_one_line_that_says_why(
    unasked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Not ready: `draw` puts text in the page's own window and nothing else.
    No control and no column pane is reached (each fails the test if it
    is), no child window draws (one draw list), no view is built, and the
    library is never asked for. The line is `NOT_DRAWING` and `why_not()`.
    """
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    made = ColumnsPage(_context(3))
    monkeypatch.setattr(made, "_controls", lambda imgui: pytest.fail("controls were drawn"))
    monkeypatch.setattr(made, "_draw_columns", lambda imgui: pytest.fail("a pane was drawn"))
    first = _frame(made.draw)
    second = _frame(made.draw)
    assert made.view is None and made.frames == 2
    assert made.reason == typesetter.SWITCHED_OFF_REASON
    assert made.lines() == (page.NOT_DRAWING + made.reason,)
    assert first["own"] > 0 and first["own"] == second["own"]
    assert first["lists"] == 1
    assert made.report()[0].startswith("frames=2 renderer=none count=3 ")


def test_the_line_is_wrapped_to_the_window(unasked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A long reason takes more than one line of the window and still fits
    inside it: the item the page leaves is no wider than the window.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    monkeypatch.setattr(page, "why_not", lambda: "a reason that goes on " * 40)
    made = ColumnsPage(_context())
    seen: dict[str, float] = {}

    def draw() -> None:
        made.draw()
        size = imgui.get_item_rect_size()
        seen["width"], seen["height"] = size.x, size.y
        seen["line"] = imgui.get_text_line_height()

    _frame(draw)
    assert 0.0 < seen["width"] <= SIZE[0]
    assert seen["height"] > 2.0 * seen["line"]


class _Raising:
    """
    Stands in for the page's view: its `draw` raises what it was given.
    """

    columns = None

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.debug = False

    def default_gutter(self) -> float:
        return 20.0

    def set_columns(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def draw(self, **kwargs: Any) -> bool:
        raise self.error


def test_a_view_that_becomes_unavailable_is_the_same_line_from_that_frame_on(
    unasked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    `TypesetUnavailable` out of the view's draw does not leave the page: the
    frame ends with ImGui's stacks whole (the next `new_frame` would raise
    otherwise), the line with the reason is drawn in that frame, the view is
    dropped, and every later frame is the line alone, whatever `why_not`
    says afterwards.
    """
    monkeypatch.setattr(page, "why_not", lambda: "")
    made = ColumnsPage(_context(2))
    made.view = _Raising(TypesetUnavailable("imtypeset failed and is switched off: boom"))  # type: ignore[assignment]
    _frame(made.draw)
    assert made.view is None
    assert made.reason == "imtypeset failed and is switched off: boom"
    monkeypatch.setattr(made, "_controls", lambda imgui: pytest.fail("controls were drawn"))
    monkeypatch.setattr(made, "_draw_columns", lambda imgui: pytest.fail("a pane was drawn"))
    after = _frame(made.draw)
    assert after["own"] > 0 and after["lists"] == 1
    assert made.lines() == (page.NOT_DRAWING + made.reason,)


def test_any_other_exception_out_of_the_view_is_a_bug_and_leaves_the_page(
    unasked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page, "why_not", lambda: "")
    made = ColumnsPage(_context(2))
    made.view = _Raising(RuntimeError("a bug"))  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="a bug"):
        _frame(made.draw)
    assert made.reason == ""


# ----------------------------------------------------------------------
# 3. With the library, no window
# ----------------------------------------------------------------------

CHILD_PRELUDE = r"""
import json, math, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import columns as page
from imscribe.ui.pages.columns import ColumnsPage

SIZE = (1300.0, 800.0)
report = {"module": typesetter.module() is not None,
          "load_start": ["%.2f" % x for x in __import__("os").getloadavg()]}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(*SIZE)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
io.add_mouse_pos_event(-1.0e6, -1.0e6)
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


def frame(made, count=1):
    # `count` frames of the page in a window filling the display; the last frame's calls.
    for _ in range(count):
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(*SIZE))
            imgui.begin("##imscribe-page-child", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                calls.clear()
                made.draw()
                got = list(calls)
            finally:
                imgui.end()
        finally:
            imgui.render()
    return got


def fields(made):
    line = made.report()[0]
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def context(count=None, *options):
    return PageContext.build(request_page="Columns", request_count=count, request_options=options)


def ranges(view):
    found, k = [], 0
    while True:
        one = view.column(k)
        if not one.exists:
            return found
        found.append([list(one.start), list(one.end), list(one.min), list(one.max)])
        k += 1
"""

CHILD_EPILOGUE = r"""
report["trouble"] = typesetter.trouble()
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


def child(body: str) -> dict[str, Any]:
    """
    Run `body` in a child that has the library's fonts in an ImGui context with no window.

    Skips when `IMTYPESET_LIBRARY` is not set; fails when it is set and the
    library is not in use, so a green run is never the one line's.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(NEEDS_LIBRARY)
    done = subprocess.run(
        [sys.executable, "-B", "-c", CHILD_PRELUDE + textwrap.dedent(body) + CHILD_EPILOGUE],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-6000:]
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    assert report["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert report["load_fonts"] is True and report["ready"] is True, report.get("reason", "")
    return report


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    return child(r"""
        counts = {}
        for count in (1, 2, 3):
            made = ColumnsPage(context(count))
            first = frame(made)
            heights = [made.view.columns.height]
            second = frame(made)
            heights.append(made.view.columns.height)
            steady = [frame(made) for _ in range(3)]
            view = made.view
            counts[str(count)] = {
                "first": first, "second": second, "heights": heights,
                "steady": steady, "fields": fields(made),
                "lines": list(made.lines()),
                "columns": list(view.columns), "column_width": view.column_width,
                "width": view.width, "height": view.height, "vertices": made.vertices,
                "origin": list(view.origin),
            }
            view.close()
        report["counts"] = counts

        # Three columns a page: every page reached, the last one whole; then the columns themselves.
        made = ColumnsPage(context(3))
        frame(made, 3)
        view = made.view
        pitch = 3 * (view.column_width + view.columns.gutter)
        start = view.origin[0]
        turned = []
        for _ in range(12):
            asked = made.turn(1)
            frame(made, 3)
            turned.append([asked, made.page, start - view.origin[0], made.pages, made.columns,
                           made.settled])
        last_lines = list(made.lines())
        found = ranges(view)
        frame(made, 2)
        end = [len(view.texts) - 1, len(view.texts[-1])]
        view.select_all()
        everything = view.selected_text() == view.separator.join(t for t in view.texts if t)
        view.clear_selection()
        back = [made.turn(-1), frame(made, 3), made.page, start - view.origin[0]]
        made.pick(2)
        picked = [frame(made), frame(made, 3), made.page, start - view.origin[0],
                  list(view.columns), fields(made)]
        report["pages"] = {"pitch": pitch, "turned": turned, "ranges": found, "end": end,
                           "everything": everything, "back": back, "picked": picked,
                           "last_lines": last_lines, "sheet": view.column_width * 2
                           + view.columns.gutter}

        # Balanced, which is new; and one balanced column, which is the uncut document.
        made.pick(3)
        made.set_balance(True)
        balanced_first = frame(made)
        balanced = [frame(made, 3), fields(made), list(made.lines()), list(view.columns),
                    ranges(view), view.height, made.turn(1)]
        made.pick(1)
        uncut = [frame(made), frame(made, 2), view.columns, fields(made), list(made.lines())]
        made.set_balance(False)
        again = [frame(made), frame(made, 2), list(view.columns), fields(made)]
        report["balanced"] = {"first": balanced_first, "balanced": balanced, "uncut": uncut,
                              "again": again}

        # The overlay checkbox reaches the view; a launch that names balance opens balanced.
        made.context.debug = True
        frame(made)
        report["debug"] = view.debug
        opened = ColumnsPage(context(2, "balance"))
        frame(opened, 2)
        report["opened"] = [list(opened.view.columns), fields(opened)]
        opened.view.close()

        # The library switched off under the page: the one line, and the page lives.
        typesetter.disable("switched off by the test")
        off = [frame(made), frame(made)]
        report["off"] = {"calls": off, "view": made.view is None, "reason": made.reason,
                         "lines": list(made.lines()), "fields": fields(made)}
        """)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_with_the_library_the_page_draws_the_document_in_that_many_columns(
    typeset: dict[str, Any], count: int
) -> None:
    """
    `--tab columns:N`: the view is told `count=N` and the pane's height,
    one column is `(sheet - gutters) / N` wide with the sheet held to N
    columns of `TEXT_WIDTH_PX`, the document makes more columns than N
    (`demo/columns.md` overflows one page at every count), and text reaches
    the draw list.

    **A frame of the page is five calls**: the view's three, then
    `GetDocumentColumnCount` and `GetDocumentStats` for the readout. The
    first frame also makes the document and tells it the columns; the
    second tells it again when the pane's height moved (a child window
    knows its height, less its scrollbar, from its second frame on), and
    no frame after that does.
    """
    told = typeset["counts"][str(count)]
    assert told["first"] == [
        "GetCurrentContext",
        "CreateDocument",
        "SetDocumentBlocks",
        "SetDocumentOptions",
        "SetDocumentColumns",
        *_PAGE_FRAME,
    ]
    settled = told["heights"][0] == told["heights"][1]
    assert told["second"] == (_PAGE_FRAME if settled else ["SetDocumentColumns", *_PAGE_FRAME])
    assert told["steady"] == [_PAGE_FRAME] * 3
    asked, height, gutter, balance = told["columns"]
    assert height == told["heights"][1]
    assert (asked, balance) == (count, False)
    assert gutter == pytest.approx(21.6, abs=0.001)
    sheet = min(SIZE[0], count * page.TEXT_WIDTH_PX + (count - 1) * gutter)
    assert told["column_width"] <= page.TEXT_WIDTH_PX + 0.001
    assert told["column_width"] * count + gutter * (count - 1) <= sheet + 0.001
    # The pane is most of the window's height, and a column is as tall as the pane.
    assert 500.0 < height < SIZE[1] and told["height"] == height
    fields = told["fields"]
    assert fields["renderer"] == "TypesetView" and fields["count"] == str(count)
    assert int(fields["columns"]) > count and int(fields["pages"]) > 1
    assert fields["page"] == "0" and fields["balance"] == "0"
    assert told["vertices"] > 1000
    assert told["lines"][0].startswith("renderer: TypesetView in columns (imtypeset)")
    assert f"{count} columns a page" in told["lines"][1]
    assert told["lines"][2] == page.DEFECTS_NOTE


def test_pages_of_three_columns_are_the_page_moved_left_by_whole_pages(
    typeset: dict[str, Any],
) -> None:
    """
    `Next page` moves the document left by `count * (column width +
    gutter)` under the pane's clip rectangle, a page at a time, to the last
    page and no further; the last page is reached WHOLE though it holds
    fewer than three columns (the page extends the pane's content for it).
    Once the last column has been reached the count is exact and the page
    stops saying "about".
    """
    told = typeset["pages"]
    pitch = told["pitch"]
    turned = told["turned"]
    pages = turned[-1][3]
    assert pages == -(-len(told["ranges"]) // 3) and pages >= 3
    assert len(told["ranges"]) % 3 != 0, "the last page is meant to be part empty"
    for step, (asked, shown, moved, _pages, _columns, _settled) in enumerate(turned, start=1):
        assert asked == shown
        assert moved == pytest.approx(shown * pitch, abs=1.0), step
    assert turned[0][1] == 1
    assert [one[1] for one in turned[-3:]] == [pages - 1] * 3
    assert turned[-1][4] == len(told["ranges"]) and turned[-1][5] is True
    assert "about" not in " ".join(told["last_lines"])
    assert f"page {pages} of {pages}" in told["last_lines"][1]
    asked, _calls, shown, moved = told["back"]
    assert asked == shown == pages - 2 and moved == pytest.approx(shown * pitch, abs=1.0)


def test_the_page_s_columns_hold_the_document_once_and_copy_as_uncut(
    typeset: dict[str, Any],
) -> None:
    told = typeset["pages"]
    starts = [tuple(one[0]) for one in told["ranges"]]
    ends = [tuple(one[1]) for one in told["ranges"]]
    assert starts[0] == (0, 0) and starts[1:] == ends[:-1] and ends[-1] == tuple(told["end"])
    assert told["everything"] is True


def test_another_count_tells_the_library_once_and_starts_at_the_first_page(
    typeset: dict[str, Any],
) -> None:
    first, steady, shown, moved, columns, fields = typeset["pages"]["picked"]
    assert first == ["SetDocumentColumns", *_PAGE_FRAME] and steady == _PAGE_FRAME
    assert (shown, columns[0], fields["count"]) == (0, 2, "2")
    # The sheet is narrower at two columns and is centred: the document's left edge moved right.
    assert moved < 0.0 or typeset["pages"]["sheet"] >= SIZE[0] - 40.0


def test_balance_is_offered_said_to_be_new_and_one_column_of_it_is_uncut(
    typeset: dict[str, Any],
) -> None:
    """
    The checkbox maps to `set_columns(count, balance=True)`: exactly `count`
    columns of one height, one page, no page to turn to, and a caption that
    says it is new and not the reference's. With one column the view is
    shown uncut. Unticked, the columns are filled in order again.
    """
    told = typeset["balanced"]
    assert told["first"] == ["SetDocumentColumns", *_PAGE_FRAME]
    steady, fields, lines, columns, ranges, height, turned = told["balanced"]
    assert steady == _PAGE_FRAME
    assert columns[0] == 3 and columns[3] is True and columns[1] == 0.0
    assert len(ranges) == 3 and len({one[3][1] for one in ranges}) == 1
    assert (fields["columns"], fields["pages"], fields["balance"]) == ("3", "1", "1")
    assert fields["settled"] == "1" and turned == 0
    assert height == pytest.approx(ranges[0][3][1], abs=1.0)
    assert lines[1] == page.BALANCE_NOTE and "not the reference's" in lines[1]
    first, steady, columns, fields, lines = told["uncut"]
    assert first == ["SetDocumentColumns", *_PAGE_FRAME] and steady == _PAGE_FRAME
    assert columns is None and (fields["columns"], fields["pages"]) == ("1", "1")
    assert "uncut" in lines[0] and lines[1] == page.BALANCE_NOTE
    first, steady, columns, fields = told["again"]
    assert first == ["SetDocumentColumns", *_PAGE_FRAME] and steady == _PAGE_FRAME
    assert columns[0] == 1 and columns[1] > 500.0 and columns[3] is False
    assert int(fields["columns"]) > 1
    assert typeset["debug"] is True
    opened, fields = typeset["opened"]
    assert opened[0] == 2 and opened[3] is True and fields["balance"] == "1"


def test_the_library_switched_off_under_the_page_is_the_one_line_and_no_traceback(
    typeset: dict[str, Any],
) -> None:
    """
    `typesetter.disable` between two frames: the next frame asks the
    library nothing, draws the line with the reason, drops the view, and
    does not raise.
    """
    told = typeset["off"]
    assert told["calls"] == [[], []]
    assert told["view"] is True
    assert "switched off by the test" in told["reason"]
    assert told["lines"] == [page.NOT_DRAWING + told["reason"]]
    assert told["fields"]["renderer"] == "none"


# ----------------------------------------------------------------------
# 4. The real app in a real window
# ----------------------------------------------------------------------

WINDOWED = r"""
import json
import sys

from imgui_bundle import hello_imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app

TAB, WANT_LIBRARY = sys.argv[1], sys.argv[2] == "with"
report = {"frames": 0, "seen": []}
real_gui = imscribe_app.App.gui


def watched_gui(self):
    if report["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    report["frames"] += 1
    made = self._views.get(self.current)
    if report["frames"] < 4:
        return
    if report["frames"] == 4:
        report["current"] = self.current
        report["page_errors"] = sorted(getattr(self, "page_errors", {}))
        report["ready"] = typesetter.ready()
        report["reason"] = made.reason
        if WANT_LIBRARY:
            assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
            assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
    report["seen"].append(made.report()[0])
    report["lines"] = list(made.lines())
    report["view"] = made.view is not None
    if made.view is not None and made.view.columns is not None:
        report["columns"] = list(made.view.columns)
        report["column_width"] = made.view.column_width
        report["width"] = made.view.width
    if report["frames"] == 8 and made.view is not None:
        made.turn(1)
    if report["frames"] >= 16:
        report["trouble"] = typesetter.trouble()
        hello_imgui.get_runner_params().app_shall_exit = True


imscribe_app.App.gui = watched_gui
imscribe_app.run(tab=TAB)
report["imported"] = "imtypeset" in sys.modules
OLD = ("imscribe.columns", "imscribe.ui.document_view")
report["old"] = sorted(m for m in sys.modules if m in OLD)
print("REPORT " + json.dumps(report))
"""


def _windowed(window: Window, monkeypatch: pytest.MonkeyPatch, how: str) -> dict[str, Any]:
    if how == "with" and not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(NEEDS_LIBRARY)
    script = window.out / f"page_columns_{how}.py"
    script.write_text(WINDOWED, encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), "columns:3", how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    print(how, window.where, json.dumps(report))  # shown by pytest when the test fails
    assert report["imported"] is (how == "with")
    assert report["ready"] is (how == "with")
    assert report["current"] == "Columns" and report["page_errors"] == []
    return report


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_in_a_real_window_with_the_library_the_page_is_drawn_in_three_columns(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app, `--tab columns:3`, the library loaded and ready IN THE
    CHILD: the view is in three columns filled in order, vertices reach the
    draw list on every frame watched, the document makes more than three
    columns, and `Next page` shows the second page.
    """
    report = _windowed(window, monkeypatch, "with")
    assert report["view"] is True and report["reason"] == "" and report["trouble"] == ""
    assert report["columns"][0] == 3 and report["columns"][3] is False
    assert report["columns"][1] > 200.0
    seen = [_fields(line) for line in report["seen"]]
    assert all(one["renderer"] == "TypesetView" and one["count"] == "3" for one in seen)
    assert all(int(one["vertices"]) > 1000 for one in seen)
    assert int(seen[-1]["columns"]) > 3 and int(seen[-1]["pages"]) > 1
    assert seen[0]["page"] == "0" and seen[-1]["page"] == "1"
    assert report["width"] > 3 * report["column_width"]
    assert report["lines"][0].startswith("renderer: TypesetView in columns")


def test_in_a_real_window_without_the_library_the_page_is_the_one_line(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The same launch with the two variables removed: no view, the one line
    naming the variable, and nothing of imtypeset imported. Not a traceback
    page: the app reports no page error.
    """
    report = _windowed(window, monkeypatch, "without")
    assert report["view"] is False
    assert report["reason"] == typesetter.SWITCHED_OFF_REASON
    assert report["lines"] == [page.NOT_DRAWING + report["reason"]]
    assert all(_fields(line)["renderer"] == "none" for line in report["seen"])
    assert report["old"] == [], "the page, or the app on its way to it, loaded an old module"

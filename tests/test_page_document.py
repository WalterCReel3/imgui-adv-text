r"""
The Document page, and the helpers the other three pages of its task
(`find`, `themes`, `inspector`) drive the library with.

**Four levels, so nobody reads more into a green run than is there.**

1. No ImGui: the sheet arithmetic, and what importing each of the pages loads.
2. Frames of a real `ImGuiContext` with no backend, in this process. The
   library is never ready here (nothing called `typesetter.load_fonts()`), so
   the page is ONE LINE saying why, and must not ask for the library to find
   that out. A fake view shows what this process can see of the rest: the
   sheet worked out, a view that fails mid-run leaving the page alive.
3. With the library, real frames, no window (`typeset_child`; skipped with
   the reason when `IMTYPESET_LIBRARY` is not set): a child process loads the
   library's fonts into an atlas nobody renders and drives the page through
   the app's own `gui`.
4. The real app in a real window: with the library (`windowed_typeset`,
   asserting IN THE CHILD that `typesetter.module()` is not `None` and
   `typesetter.ready()`, at the fourth frame and again at the end), and
   without it (the one line, and no traceback page).

**There is no other renderer to fall back to**, so a green run of levels 3
and 4 is the library's or nobody's; the helpers still assert it at both ends
of a child, because a library switched off half way leaves pages that draw
one line and raise nothing.

**Nothing here judges how the page looks.** Vertices are counted and
rectangles compared.

`typeset_child`, `windowed_typeset`, `unasked` and `says_only_why_not` are
imported by `tests/test_page_find.py`, `tests/test_page_themes.py` and
`tests/test_page_inspector.py`.
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
from imscribe.ui.app import App
from imscribe.ui.pages import document as page
from imscribe.ui.pages.document import DocumentPage, Sheet, sheet_for
from imscribe.ui.pages.typeset import not_drawing, say_why_not
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


# ----------------------------------------------------------------------
# Helpers, shared with the other three pages' tests
# ----------------------------------------------------------------------

CHILD_PRELUDE = r"""
import json, sys, time
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.ui.app import App, parse_tab_request
from imscribe.ui.pages import PageContext

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


def frame(draw, count=1):
    # `count` frames of `draw()` in a window filling the display; the last frame's vertices.
    for _ in range(count):
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(*SIZE))
            imgui.begin("##imscribe-page-child", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                draw()
            finally:
                imgui.end()
        finally:
            imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def mouse(x, y):
    io.add_mouse_pos_event(float(x), float(y))


def click(button=0):
    io.add_mouse_button_event(button, True)


def release(button=0):
    io.add_mouse_button_event(button, False)


def fields(line):
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def context(spec):
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


def switch_off(why):
    # The one way a body may lose the library. What it was just before is
    # recorded, so that the parent can tell a switch the test made from a
    # library that failed on its own.
    report["before_switch_off"] = [typesetter.module() is not None, typesetter.ready()]
    report["switched_off"] = why
    typesetter.disable(why)


def only_the_line(draw, reason):
    # [vertices of `draw()`, vertices of the one "why not" line]: equal when the page is that
    # line. The line is drawn twice first: a window's first frame is not its second.
    from imscribe.ui.pages.typeset import say_why_not
    alone = lambda: say_why_not(reason)
    frame(alone, 2)
    return [frame(draw), frame(alone)]
"""

CHILD_EPILOGUE = r"""
report["trouble"] = typesetter.trouble()
report["module_after"] = typesetter.module() is not None
report["ready_after"] = typesetter.ready()
report["reason_after"] = typesetter.reason()
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


def typeset_child(body: str) -> dict[str, Any]:
    """
    Run `body` in a child that has the library's fonts in an ImGui context with no window.

    The child has `report` (a dict it fills), `frame(draw, count)`, `mouse`,
    `click`, `release`, `fields`, `context(spec)`, `switch_off(why)` and
    `only_the_line(draw, reason)`. Skips when `IMTYPESET_LIBRARY` is not set;
    fails when it is set and the library is not in use.

    **Asserted before the body and after it**: the library is imported and
    its fonts are loaded when the body starts, and still are when it ends. A
    body that ends with the library off must have switched it off itself,
    through `switch_off`, with the library in use at that moment; a library
    that failed on its own part way (after which every page draws one line
    and raises nothing) fails the test here.
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
    why = report.get("switched_off")
    if why is None:
        assert report["module_after"] is True and report["ready_after"] is True, (
            "the library was lost during the body: " + report["reason_after"]
        )
    else:
        assert report["before_switch_off"] == [True, True], "lost before the test switched it off"
        assert report["ready_after"] is False and report["reason_after"] == why
    return report


WINDOWED_PRELUDE = r"""
import json
import sys

from imgui_bundle import hello_imgui, imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app

TAB, WANT_LIBRARY = sys.argv[1], sys.argv[2] == "with"
report = {"frames": 0}
real_gui = imscribe_app.App.gui


def finish():
    report["trouble"] = typesetter.trouble()
    report["ready_end"] = typesetter.ready()
    if WANT_LIBRARY:
        report["module_end"] = typesetter.module() is not None
    report["page_errors"] = sorted(imscribe_app_errors())
    hello_imgui.get_runner_params().app_shall_exit = True


APPS = []


def imscribe_app_errors():
    return APPS[-1].page_errors if APPS else {}


def watched_gui(self):
    if report["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    APPS.append(self)
    report["frames"] += 1
    made = self._views.get(self.current)
    if report["frames"] == 4:
        report["current"] = self.current
        report["ready"] = typesetter.ready()
        report["reason"] = made.reason
        if WANT_LIBRARY:
            assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
            assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
    if report["frames"] >= 4:
        watch(self, made, report["frames"])
"""

WINDOWED_EPILOGUE = r"""
imscribe_app.App.gui = watched_gui
imscribe_app.run(tab=TAB)
report["imported"] = "imtypeset" in sys.modules
print("REPORT " + json.dumps(report))
"""


def windowed_typeset(
    window: Window, monkeypatch: pytest.MonkeyPatch, tab: str, body: str, how: str = "with"
) -> dict[str, Any]:
    """
    The real app on `tab` in a real window; `body` defines `watch(app, made, frame)`.

    `watch` is called after each frame from the fourth on, fills `report`
    and calls `finish()` when it has seen enough. With `how="with"` the test
    is skipped unless `IMTYPESET_LIBRARY` is set, the CHILD asserts that the
    library is imported and ready before anything else is looked at, and it
    is asserted again here as of `finish()`. With `how="without"` the two
    variables are removed for the child, which must then never import the
    library. Either way no page may have reached the app's traceback page.
    """
    if how == "with" and not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(NEEDS_LIBRARY)
    script = window.out / f"page_{tab.split(':')[0]}_{how}.py"
    script.write_text(
        WINDOWED_PRELUDE + textwrap.dedent(body) + WINDOWED_EPILOGUE, encoding="utf-8"
    )
    with monkeypatch.context() as patch:
        if how == "without":
            for name in VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), tab, how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    print(how, window.where, json.dumps(report))  # shown by pytest when the test fails
    assert report["imported"] is (how == "with")
    assert report["ready"] is (how == "with")
    assert report["ready_end"] is (how == "with"), report.get("trouble", "")
    assert report.get("module_end", True) is True, "the library was lost while the window ran"
    assert report["page_errors"] == [], "a page reached the app's traceback page"
    return report


@pytest.fixture
def unasked(monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    `imscribe.typesetter` as at import, and a `module()` that fails the test if asked.
    """
    typesetter._forget()
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("the page asked for the library"))
    yield
    typesetter._forget()


def _frame(draw: Any) -> int:
    """
    One frame of a context with no backend, `draw()` in a full-size window; the vertex count.
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
        imgui.begin("##imscribe-page-document-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def says_only_why_not(draw: Any, reason: str) -> int:
    """
    Assert that a frame of `draw()` is the one "why not" line and NOTHING else.

    Counted, not read: the frame has exactly the vertices of a frame holding
    only `say_why_not(reason)`, in the same window. A control, a caption, a
    pane's border or a second line would each add some. Returns the count.
    """
    assert reason, "a page that draws nothing must say why"

    def alone() -> None:
        say_why_not(reason)

    # A window's first frame in a context is not its second (measured: six
    # vertices apart), so the line is drawn until two frames of it agree, and
    # once more after the page's, so the page's frame stands between two equals.
    _frame(alone)
    line = _frame(alone)
    drawn = _frame(draw)
    assert line > 0, "the line itself draws nothing here, so equality would prove nothing"
    assert _frame(alone) == line, "the reference frame is not steady"
    assert drawn == line, not_drawing(reason)
    return line


# ----------------------------------------------------------------------
# 1. No ImGui
# ----------------------------------------------------------------------

# The old layout core, as `tests/test_typeset_closure.py` lists it, plus the
# modules that stand on it. `imscribe.units` and `imscribe.fontmetrics` are on
# that file's list and were the floor of everything until T5-B2 (arithmetic,
# and the `Face` enum); both are `imscribe.primitives`' now, which is what a
# page loads instead, and neither old module may be loaded.
OLD = (
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
FLOOR = {"imscribe.primitives", "imscribe.theme"}
WAS_THE_FLOOR = {"imscribe.units", "imscribe.fontmetrics"}

_CLOSURE = r"""
import importlib, json, sys
before = set(sys.modules)
if sys.argv[2] == "from":
    package, _, name = sys.argv[1].rpartition(".")
    exec(f"from {package} import {name}")
else:
    importlib.import_module(sys.argv[1])
print(json.dumps(sorted(m for m in set(sys.modules) - before if m.split(".")[0] == "imscribe")))
"""


@pytest.mark.parametrize("form", ["import", "from"])
@pytest.mark.parametrize("name", ["document", "find", "themes", "inspector", "_syntax"])
def test_importing_a_moved_page_loads_none_of_the_old_core(name: str, form: str) -> None:
    """
    A fresh interpreter, the one import, and what of imscribe it then holds.

    Import time; `test_a_page_built_and_drawn_without_the_library_loads_no_old_view`
    is the same question after the page has been made and drawn.
    """
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CLOSURE, f"imscribe.ui.pages.{name}", form],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    assert done.returncode == 0, done.stderr
    loaded = set(json.loads(done.stdout.strip().splitlines()[-1]))
    old = sorted(
        module
        for module in loaded
        if any(module == one or module.startswith(one + ".") for one in OLD)
    )
    assert old == [], (name, form, old)
    assert f"imscribe.ui.pages.{name}" in loaded
    assert FLOOR <= loaded, "the floor moved: say so in tests/test_typeset_closure.py too"
    assert not WAS_THE_FLOOR & loaded, sorted(WAS_THE_FLOOR & loaded)


_DRAWN = r"""
import importlib, json, sys
from imgui_bundle import imgui
from imscribe.ui.pages import PageContext

context = PageContext.build()
module = importlib.import_module(sys.argv[1])
before = set(sys.modules)
made = module.PAGE.factory(context)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
for _ in range(2):
    imgui.new_frame()
    imgui.begin("##imscribe-page-drawn")
    made.draw()
    imgui.end()
    imgui.render()
print(json.dumps({
    "loaded": sorted(m for m in set(sys.modules) - before if m.split(".")[0] == "imscribe"),
    "renderer": made.renderer, "reason": made.reason,
    "imtypeset": "imtypeset" in sys.modules,
}))
"""

# What `Theme.at_pixel_height` loads to measure a face: `imscribe.style` (its
# resolver's home, with the modules that module imports) and
# `imscribe.fontlib`. The Themes page makes its theme that way
# (`.concerns/lead--tranche-5.md`, decision 5); the others load none of it.
# (`imscribe.units` and `imscribe.fontmetrics` come with it too and are not on
# `OLD`; `tests/test_typeset_closure.py` states the whole set.)
MEASURING = {
    "imscribe.style",
    "imscribe.fontlib",
    "imscribe.nodes",
    "imscribe.pack",
    "imscribe.badness",
}


@pytest.mark.parametrize("name", ["document", "find", "themes", "inspector"])
def test_a_page_built_and_drawn_without_the_library_loads_no_old_view(name: str) -> None:
    """
    A fresh interpreter with the library's variables removed: the page is made
    from `PageContext.build()`, drawn for two frames, and what of imscribe was
    loaded BY THAT is listed. Nothing of the old core or the old views, with
    one named exception: the Themes page measures a face to make its theme.
    """
    pytest.importorskip("imgui_bundle")
    environment = {k: v for k, v in os.environ.items() if k not in VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _DRAWN, f"imscribe.ui.pages.{name}"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**environment, "PYTHONPATH": str(ROOT)},
        cwd=str(ROOT),
    )
    assert done.returncode == 0, done.stderr[-4000:]
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert got["renderer"] == "none" and got["reason"] and got["imtypeset"] is False
    old = {
        module
        for module in got["loaded"]
        if any(module == one or module.startswith(one + ".") for one in OLD)
    }
    allowed = MEASURING if name == "themes" else set()
    assert old == allowed, (name, sorted(old ^ allowed))
    if name == "themes":
        assert "imscribe.fontlib" in got["loaded"], "the named exception is no longer taken: say so"


# `imscribe.ui.document_view.page_for`'s answers, frozen on 2026-10-11 before
# the old page body was removed (`.concerns/T5-FB-A-scripts/sheet_rows.py`
# printed them): `(available, alphabet, leading)` in pixels to the old page's
# `(offset, width, margin, head)`, converted from scaled points and rounded
# to four places. `sheet_for` restated that function and is now the only
# statement of the rule; these rows are what holds it to the old one. They
# cover no alphabet at all, a region narrower than the ideal sheet (the
# margin at its floor of three leadings, and at the canon's sixth when that
# is smaller), exactly the ideal sheet, and a region wider than it (centred).
OLD_SHEETS = (
    ((80.0, 0.0, 14.0), (0.0, 80.0, 13.3333, 14.0)),
    ((1068.0, 0.0, 21.6), (0.0, 1068.0, 178.0, 21.6)),
    ((80.0, 120.0, 21.6), (0.0, 80.0, 13.3333, 21.6)),
    ((300.0, 120.0, 14.0), (0.0, 300.0, 42.0, 14.0)),
    ((300.0, 120.0, 21.6), (0.0, 300.0, 50.0, 21.6)),
    ((467.0, 120.0, 14.0), (31.0, 405.0, 67.5, 14.0)),
    ((1900.0, 120.0, 21.6), (747.5, 405.0, 67.5, 21.6)),
    ((300.0, 207.55, 14.0), (0.0, 300.0, 42.0, 14.0)),
    ((467.0, 207.55, 14.0), (0.0, 467.0, 42.0, 14.0)),
    ((467.0, 207.55, 21.6), (0.0, 467.0, 64.8, 21.6)),
    ((700.5, 207.55, 21.6), (0.0094, 700.4812, 116.7469, 21.6)),
    ((1068.0, 207.55, 14.0), (183.7594, 700.4812, 116.7469, 14.0)),
    ((1900.0, 207.55, 21.6), (599.7594, 700.4812, 116.7469, 21.6)),
    ((700.5, 333.3, 14.0), (0.0, 700.5, 42.0, 14.0)),
    ((1068.0, 333.3, 21.6), (0.0, 1068.0, 159.0375, 21.6)),
    ((1900.0, 333.3, 14.0), (387.5563, 1124.8875, 187.4813, 14.0)),
)

OLD_ALPHABET_PX = 207.5547
"""
`abc...z` in the stock theme's body face as the old `DocumentView` added it up
(`imscribe.ui.document_view.alphabet_length`, 207.55465750181614 px), frozen on
2026-10-11. The page now asks the library, which says 208.0.
"""


def test_the_sheet_is_the_old_pages_arithmetic_in_pixels() -> None:
    """
    `sheet_for` against the old page's `page_for`, whose answers are `OLD_SHEETS`.

    The old function rounded to whole scaled points (1/65536 pt) and the rows
    are rounded to four places, hence the bound.
    """
    for (available, alphabet, leading), (offset, width, margin, head) in OLD_SHEETS:
        new = sheet_for(available, alphabet_px=alphabet, leading_px=leading)
        where = (available, alphabet, leading)
        assert new.offset == pytest.approx(offset, abs=1e-3), where
        assert new.width == pytest.approx(width, abs=1e-3), where
        assert new.margin == pytest.approx(margin, abs=1e-3), where
        assert new.head == pytest.approx(head, abs=1e-3), where
        assert new.measure == pytest.approx(width - 2.0 * margin, abs=2e-3), where


def test_a_sheet_never_has_no_width_and_is_centred() -> None:
    wide = sheet_for(1068.0, alphabet_px=207.55, leading_px=21.6)
    assert wide.measure == pytest.approx(207.55 * page.MEASURE_ALPHABETS)
    assert wide.offset == pytest.approx((1068.0 - wide.width) / 2.0) and wide.offset > 0.0
    unmeasured = sheet_for(500.0, alphabet_px=0.0, leading_px=21.6)
    assert (unmeasured.offset, unmeasured.width) == (0.0, 500.0) and unmeasured.margin > 0.0
    assert isinstance(unmeasured, Sheet)


# ----------------------------------------------------------------------
# 2. Frames with no backend: one line saying why, the library never asked for
# ----------------------------------------------------------------------

SMALL = "# t\n\nSome words to set.\n"


@pytest.mark.parametrize("variable", ["unset", "set"])
def test_without_the_library_the_page_is_one_line_saying_why(
    variable: str, monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    `set` is `make test TYPESET=1`'s case in this process: the variable is
    there, no fonts were loaded, and the page must not import the library to
    find that out.
    """
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    if variable == "set":
        monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, "/somewhere/lib.so")
    app = App(source=SMALL, columns_source="x\n", open_tab="document")
    for _ in range(2):
        _frame(app.gui)
    assert app.page_errors == {}, app.page_errors
    made = app._views["Document"]
    assert isinstance(made, DocumentPage)
    assert made.source == SMALL, "the markdown the launch named, through the context"
    assert made.typeset is None and made.renderer == "none" and made.sheet is None
    assert made.frames == 2 and made.vertices == 0
    says_only_why_not(made.draw, made.reason)
    assert made.report()[0].startswith("frames=3 renderer=none blocks=0 measure=0 ")


def test_the_page_needs_no_app_and_has_a_document_without_the_demo_file(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    from imscribe.ui.pages import PageContext

    assert DocumentPage(PageContext.build()).source.startswith("# ")
    assert DocumentPage(PageContext.build(source=SMALL)).source == SMALL
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    assert DocumentPage(PageContext.build()).source == page.FALLBACK


class _Failing:
    """
    A `TypesetView` whose library fails at the second frame's draw, as the view reports it.
    """

    height = 40.0
    texts = ("x",)

    def __init__(self, error: Exception | None = None) -> None:
        self.draws = 0
        self.debug = False
        self.error = error or TypesetUnavailable("imtypeset failed and is switched off: Error: no")

    def layout_for(self, width_px: float) -> float:
        return self.height

    def draw(self, **kwargs: Any) -> bool:
        from imgui_bundle import imgui

        self.draws += 1
        if self.draws > 1:
            raise self.error
        imgui.dummy(imgui.ImVec2(kwargs["width_px"], self.height))
        return False


def _on_a_fake_view(error: Exception | None = None) -> tuple[App, DocumentPage, _Failing]:
    app = App(source=SMALL, columns_source="x\n", open_tab="document")
    made = app.page("document")
    assert isinstance(made, DocumentPage)
    failing = _Failing(error)
    made.typeset = failing  # type: ignore[assignment]
    made.reason = ""
    made._alphabet = 207.55
    return app, made, failing


def test_a_typeset_view_that_fails_mid_run_leaves_the_page_alive_and_saying_why(
    unasked: None,
) -> None:
    """
    `TypesetUnavailable` out of a draw does not leave the page: nothing reaches
    the app's traceback page, and from the next frame on the page is the one line.

    Also what this process can see of the drawing path without the library:
    the sheet is worked out, the view is given its measure, and a `draw` that
    answers false is said in a line.
    """
    app, made, failing = _on_a_fake_view()
    _frame(app.gui)
    assert (made.renderer, failing.draws, made.whole) == ("TypesetView", 1, False)
    sheet = made.sheet
    assert sheet is not None and sheet.measure == pytest.approx(207.55 * page.MEASURE_ALPHABETS)
    assert made.vertices > 4, "the sheet's fill and the line saying something was not set"

    _frame(app.gui)
    assert failing.draws == 2 and made.typeset is None and made.sheet is None
    assert made.renderer == "none" and app.page_errors == {}
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    _frame(app.gui)
    assert failing.draws == 2 and made.frames == 3 and app.page_errors == {}
    says_only_why_not(made.draw, made.reason)
    assert "renderer=none" in made.report()[0]


def test_an_exception_that_is_not_the_librarys_is_a_bug_and_propagates(unasked: None) -> None:
    app, made, failing = _on_a_fake_view(ZeroDivisionError("a bug in the page"))
    _frame(made.draw)
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    _frame(draw)  # the frame still closes: the page's child window was ended on the way out
    assert len(raised) == 1 and made.typeset is failing and made.renderer == "TypesetView"


# ----------------------------------------------------------------------
# 3. With the library, real frames, no window
# ----------------------------------------------------------------------

_TYPESET = r"""
SOURCE = open("demo/sample.md", encoding="utf-8").read()  # the child runs in the repository
app = App(source=SOURCE, columns_source="x\n", open_tab="document")
first = frame(app.gui)
made = app._views["Document"]
view = made.typeset
report["renderer"] = made.renderer
report["reason"] = made.reason
report["source_is_the_apps"] = made.source == SOURCE
frame(app.gui, 3)
report["vertices"] = made.vertices
report["whole"] = made.whole
sheet = made.sheet
report["sheet"] = list(sheet)
report["measure"] = sheet.measure
report["origin"] = list(view.origin)
report["height"] = view.height
report["blocks"] = len(view.texts)
report["edits"] = dict(view.edits)

# The alphabet the library measured, and the width this page was given.
report["alphabet"] = made.alphabet_px()
report["leading"] = made.leading_px()
report["available"] = sheet.offset * 2.0 + sheet.width

# Every line of the first paragraph the library set, against the measure.
lines = view.set_lines(1, 2)
report["line_rights"] = [line.right for line in lines]
report["line_lefts"] = [line.left for line in lines]

# The debug overlay is the shared flag, and is something on the draw list.
plain = made.vertices
made.context.debug = True
frame(app.gui, 2)
report["debug_vertices"] = made.vertices
report["view_debug"] = view.debug
made.context.debug = False
frame(app.gui, 2)
report["plain_again"] = made.vertices == plain

# A selection is the view's, and a copy is the library's.
view.select_all()
frame(app.gui)
report["selected"] = len(view.selected_text())
report["texts"] = sum(len(text) for text in view.texts)
view.clear_selection()

# A real drag over the first paragraph selects text in it, and a click elsewhere drops it.
first = view.set_lines(1, 2)[0]
x, y = view.origin
start = (x + first.left + 20.0, y + (first.top + first.bottom) / 2)
mouse(*start)
frame(app.gui, 2)
click()
frame(app.gui)
mouse(start[0] + 150.0, start[1])
frame(app.gui, 2)
dragging = view.selection
release()
frame(app.gui)
report["dragged"] = [dragging, view.selection, view.selected_text(), view.texts[1][:60],
                     view.owns_selection]
mouse(-1.0e6, -1.0e6)
frame(app.gui)
view.clear_selection()

# The library switched off under the page: it stays alive, and is one line saying why.
switch_off("switched off by the test")
frame(app.gui)
report["after"] = [made.renderer, made.reason, made.typeset is None, made.sheet is None,
                   dict(app.page_errors)]
frame(app.gui, 2)
report["later"] = [made.renderer, dict(app.page_errors), only_the_line(made.draw, made.reason)]
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    return typeset_child(_TYPESET)


def test_with_the_library_the_page_draws_the_source_through_the_typeset_view(
    typeset: dict[str, Any],
) -> None:
    assert typeset["renderer"] == "TypesetView" and typeset["reason"] == ""
    assert typeset["source_is_the_apps"] is True
    assert typeset["vertices"] > 1000 and typeset["whole"] is True
    assert typeset["blocks"] > 10
    # One document, made once; nothing the page does edits it.
    assert typeset["edits"] == {"set": 1, "replace": 0, "append": 0}


def test_the_sheet_is_the_old_pages_to_within_a_pixel(typeset: dict[str, Any]) -> None:
    """
    The alphabet is the library's measurement where the old page added one up
    from its own metrics (`OLD_ALPHABET_PX`, frozen); the rest is arithmetic,
    held to the old page's by `OLD_SHEETS`.

    Measured, not asserted equal. A pixel is the bound a reader could see.
    """
    offset, width, margin, head = typeset["sheet"]
    old = sheet_for(
        typeset["available"], alphabet_px=OLD_ALPHABET_PX, leading_px=typeset["leading"]
    )
    assert typeset["alphabet"] == pytest.approx(OLD_ALPHABET_PX, abs=1.0)
    assert typeset["measure"] == pytest.approx(old.measure, abs=2.5)
    assert margin == pytest.approx(old.margin, abs=1.0) and head == pytest.approx(old.head)
    assert offset == pytest.approx(old.offset, abs=2.0)
    assert head == pytest.approx(typeset["leading"])


def test_the_text_is_set_to_the_measure_a_margin_in(typeset: dict[str, Any]) -> None:
    offset, width, margin, head = typeset["sheet"]
    measure = typeset["measure"]
    rights, lefts = typeset["line_rights"], typeset["line_lefts"]
    assert len(rights) > 2, "the sample's first paragraph is several lines at this measure"
    assert max(rights) <= measure + 0.5 and min(lefts) >= -0.5
    # Justified: every line but the last ends at the measure.
    assert all(right == pytest.approx(measure, abs=1.0) for right in rights[:-1]), rights
    # The origin is the sheet's text corner, snapped to a whole pixel.
    x, y = typeset["origin"]
    assert x == int(x) and y == int(y)
    assert typeset["height"] > 1000.0


def test_the_debug_checkbox_and_the_selection_reach_the_typeset_view(
    typeset: dict[str, Any],
) -> None:
    assert typeset["view_debug"] is True
    assert typeset["debug_vertices"] > typeset["vertices"]
    assert typeset["plain_again"] is True
    # Everything selected copies every block's text and a separator between them.
    assert typeset["selected"] >= typeset["texts"] > 1000


def test_a_drag_on_the_sheet_selects_text_of_the_typeset_view(typeset: dict[str, Any]) -> None:
    """
    Injected mouse events through the app's own frame: a press on the first
    paragraph's first line, 150 px along it, a release.
    """
    dragging, selection, text, paragraph, owns = typeset["dragged"]
    assert dragging is not None and selection == dragging
    (first, start), (last, end) = selection
    assert first == last == 1 and end > start
    assert text == paragraph[start:end] and len(text) > 5
    assert owns is True


def test_the_library_switched_off_under_the_page_leaves_one_line_and_no_traceback(
    typeset: dict[str, Any],
) -> None:
    renderer, reason, dropped, no_sheet, errors = typeset["after"]
    assert (renderer, dropped, no_sheet, errors) == ("none", True, True, {})
    assert "switched off by the test" in reason
    renderer, errors, (drawn, line) = typeset["later"]
    assert (renderer, errors) == ("none", {})
    assert drawn == line > 0, "the page is the one line and nothing else"


# ----------------------------------------------------------------------
# 4. The real app in a real window, with the library and without it
# ----------------------------------------------------------------------

_WATCH = r"""
def watch(app, made, frame):
    if frame == 8:
        report["renderer"] = made.renderer
        report["vertices"] = made.vertices
        report["whole"] = made.whole
        report["sheet"] = None if made.sheet is None else list(made.sheet)
        report["text"] = made.report()
        finish()
"""


def test_in_a_real_window_with_the_library_the_document_is_drawn_by_the_typeset_view(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = windowed_typeset(window, monkeypatch, "document", _WATCH)
    assert report["current"] == "Document" and report["reason"] == ""
    assert report["renderer"] == "TypesetView" and report["trouble"] == ""
    assert report["vertices"] > 1000 and report["whole"] is True
    assert report["sheet"] is not None


WATCH_WITHOUT = r"""
def watch(app, made, frame):
    if frame == 8:
        report["renderer"] = made.renderer
        report["typeset"] = made.typeset is None
        report["text"] = made.report()
        finish()
"""
"""What the four pages' "without the library, in a real window" tests watch."""


def test_in_a_real_window_without_the_library_the_page_says_why_and_stays_up(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The plain gate's window: the app runs, the page is selected, it has no
    view and a reason, the library was never imported and nothing reached the
    traceback page (`windowed_typeset` asserts the last two).
    """
    report = windowed_typeset(window, monkeypatch, "document", WATCH_WITHOUT, how="without")
    assert report["current"] == "Document" and report["reason"]
    assert report["renderer"] == "none" and report["typeset"] is True
    assert "renderer=none" in report["text"][0] and "vertices=0" in report["text"][0]

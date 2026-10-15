r"""
The Typeset page: that it draws through the imtypeset library or says in one
line why not, and that a needle produces marks when the library is drawing.

Experimental (branch `experimental/imtypeset-adoption`, task IT-PAGE; the
fallback to `BareView` was removed in T5-FB-C).

**Three levels, so nobody reads more into a green run than is there.**

1. No ImGui: `why_not`, the find box's counts, the caption lines.
2. Frames of a real `ImGuiContext` with no backend, in this process. Here the
   library is never ready (nothing called `typesetter.load_fonts()`), with or
   without `IMTYPESET_LIBRARY`, so these are the "says why not" path: the
   page loads, draws its one line, and does not ask for the library
   (`typesetter.module` is replaced by a function that fails the test). The
   page's wiring to a view is driven with a stand-in view. A fresh interpreter
   checks that building and drawing the page imports no old view.
3. The real app in a real window (`tests/conftest.py::window`), twice: with
   the variables removed, and -- skipped with the reason when
   `IMTYPESET_LIBRARY` is not set -- with them. The second asserts IN THE
   CHILD that `typesetter.module()` is not `None` and `typesetter.ready()`, so
   it cannot pass through the "why not" line.

**Nothing here judges how the page looks.** The window tests count vertices on
the pane's draw list and compare two counts.
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
from imscribe.ui.pages import PageContext, discover
from imscribe.ui.pages import typeset as page
from imscribe.ui.pages.typeset import TypesetPage
from imscribe.ui.typeset_view import TypesetUnavailable

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from conftest import Window

_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
SIZE = (1300.0, 800.0)
SOURCE = (
    "# A heading\n\nSome glue, then [a link](https://example.org) and more Glue.\n\n"
    "| a | b |\n| --- | --- |\n| glue | 2 |\n\nA last paragraph with glue in it.\n"
)


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
        imgui.begin("##imscribe-page-typeset-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


# ----------------------------------------------------------------------
# 1. No ImGui
# ----------------------------------------------------------------------


def test_the_page_is_discovered_under_its_own_heading() -> None:
    spec = discover().find("typeset")
    assert spec is page.PAGE
    assert (spec.group, spec.order, spec.shot_specs()) == ("Experimental", 510, ("typeset",))


def test_why_not_is_the_typesetters_reason_when_that_is_true(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    assert page.why_not() == typesetter.reason() == typesetter.SWITCHED_OFF_REASON


def test_why_not_does_not_say_the_variable_is_unset_when_it_is_set(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    Nobody asked `module()`, so `reason()` still holds its first sentence; the page does not.
    """
    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, "/somewhere/lib.so")
    assert typesetter.reason() == typesetter.SWITCHED_OFF_REASON
    assert page.why_not() == page.FONTS_NOT_LOADED
    typesetter.note("load_fonts was called with no Dear ImGui context")
    assert page.why_not() == "load_fonts was called with no Dear ImGui context"
    monkeypatch.delenv(typesetter.LIBRARY_VARIABLE)
    typesetter.disable("Error: add_font refused")
    assert page.why_not() == "Error: add_font refused"


def test_the_find_box_counts_without_the_library_and_the_page_says_one_line(unasked: None) -> None:
    made = TypesetPage(PageContext.build(), SOURCE)
    assert made.typeset is None and made.renderer == "none"
    assert made.finder.needle == page.DEFAULT_NEEDLE
    # Two in prose, case ignored; the one in the table cell; and one more.
    assert [(m.block, made.texts[m.block][m.start : m.end]) for m in made.finder.matches] == [
        (1, "glue"),
        (1, "Glue"),
        (2, "glue"),
        (3, "glue"),
    ]
    # A table is one block, its cells a tab and its rows a newline apart.
    assert made.table_count == 1 and made.texts[2] == "a\tb\nglue\t2"
    assert made.marks == 0
    assert made.reason == page.why_not() != ""
    assert made.lines() == (f"{page.NOT_DRAWING}: {made.reason}",)

    # The find state is the page's own and moves without a view.
    made.step(-1)
    assert made.finder.status() == "4 of 4"
    made.type("zzqq")
    assert made.finder.matches == ()
    assert made.lines() == (f"{page.NOT_DRAWING}: {made.reason}",)
    assert "found=0" in made.report()[0] and "renderer=none" in made.report()[0]


def test_the_one_line_has_no_dangling_colon_without_a_reason() -> None:
    assert page.not_drawing("") == page.NOT_DRAWING
    assert page.not_drawing("x is not set") == f"{page.NOT_DRAWING}: x is not set"


# ----------------------------------------------------------------------
# 2. Frames with no backend: the "why not" line, the library never asked for
# ----------------------------------------------------------------------


@pytest.mark.parametrize("variable", ["unset", "set"])
def test_the_page_loads_and_says_why_not_without_the_library(
    variable: str, monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    Through the app's shell, as every page-enumerating test builds it.

    `set` is `make test TYPESET=1`'s case in this process: the variable is
    there, no fonts were loaded, and the page must not import the library to
    find that out.
    """
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    if variable == "set":
        monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, "/somewhere/lib.so")
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="typeset")
    counts = [_frame(app.gui) for _ in range(3)]
    assert app.page_errors == {}, app.page_errors
    made = app._views["Typeset"]
    assert isinstance(made, TypesetPage)
    assert made.typeset is None and made.renderer == "none"
    assert made.frames == 3 and made.vertices == 0, (made.vertices, counts)
    expected = typesetter.SWITCHED_OFF_REASON if variable == "unset" else page.FONTS_NOT_LOADED
    assert made.reason == expected
    assert made.lines() == (f"{page.NOT_DRAWING}: {expected}",)
    # The state that needs no drawing is there all the same.
    assert len(made.texts) > 10 and len(made.finder.matches) > 0


def _text_vertices(text: str, wrap_px: float) -> int:
    """
    Four vertices a glyph that has ink, as `imgui.text_wrapped` would add them at this width.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    count = 0

    def inked() -> None:
        nonlocal count
        draw_list = imgui.get_window_draw_list()
        before = draw_list.vtx_buffer.size()
        imgui.push_text_wrap_pos(imgui.get_cursor_pos().x + wrap_px)
        imgui.text_unformatted(text)
        imgui.pop_text_wrap_pos()
        count = draw_list.vtx_buffer.size() - before

    _frame(inked)
    return count


def test_without_the_library_the_frame_is_the_one_line_and_nothing_else(unasked: None) -> None:
    """
    The page's whole frame adds the vertices of its sentence and no other: no
    search row, no pane, no document.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    made = TypesetPage(PageContext.build(), SOURCE)
    added: list[int] = []
    items: list[int] = []

    def draw() -> None:
        draw_list = imgui.get_window_draw_list()
        before = draw_list.vtx_buffer.size()
        cursor = imgui.get_cursor_pos().y
        made.draw()
        added.append(draw_list.vtx_buffer.size() - before)
        items.append(round((imgui.get_cursor_pos().y - cursor) / imgui.get_text_line_height()))

    for _ in range(2):
        _frame(draw)
    sentence = made.lines()[0]
    assert added[0] == added[1] == _text_vertices(sentence, SIZE[0]) > 0
    # One item high: a line or two of wrapped text, not a pane.
    assert 1 <= items[1] <= 2, items
    assert made.frames == 2 and made.vertices == 0


CLOSURE = r"""
import json
import sys

from imgui_bundle import imgui

from imscribe.ui.pages import PageContext
from imscribe.ui.pages import typeset as page

context = PageContext.build()
before = set(sys.modules)
made = page.TypesetPage(context)
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
    "line": list(made.lines()),
    "frames": made.frames,
    "added": sorted(name for name in set(sys.modules) - before if name.startswith("imscribe")),
    "old": sorted(name for name in sys.modules if name in sys.argv[1:]),
    "imtypeset": "imtypeset" in sys.modules,
}))
"""

OLD_VIEWS = (
    "imscribe.markdown",
    "imscribe.mathtext",
    "imscribe.ui.bare_view",
    "imscribe.ui.document_view",
    "imscribe.ui.composition",
    "imscribe.backends.imgui_draw",
    "imscribe.shipout",
    "imscribe.linebreak",
)
"""What the fallback this page used to have pulled in the first time it drew."""


def test_building_and_drawing_the_page_imports_no_old_view(tmp_path: Path) -> None:
    """
    In a fresh interpreter, without the library's variables: three frames of
    the page add no `imscribe` module at all to what importing it and building
    a `PageContext` loaded, and none of the old views is loaded.
    """
    pytest.importorskip("imgui_bundle")
    script = tmp_path / "closure.py"
    script.write_text(textwrap.dedent(CLOSURE), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in _VARIABLES}
    root = Path(__file__).resolve().parent.parent
    done = subprocess.run(
        [sys.executable, "-P", str(script), *OLD_VIEWS],
        cwd=root,
        env={**env, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["frames"] == 3 and report["imtypeset"] is False
    assert report["line"] == [f"{page.NOT_DRAWING}: {typesetter.SWITCHED_OFF_REASON}"]
    assert report["added"] == [] and report["old"] == [], report


class _Failing:
    """
    A `TypesetView` whose library fails on the `fail_at`-th draw, as `TypesetView.draw` reports it.
    """

    scrolled = False

    def __init__(self, fail_at: int = 2, error: type[Exception] = TypesetUnavailable) -> None:
        self.draws = 0
        self.fail_at = fail_at
        self.error = error
        self.marks: list[Any] = []
        self.scrolls: list[Any] = []

    def set_marks(self, marks: Any = None) -> None:
        self.marks.append(marks)

    def scroll_to(self, *args: Any, **kwargs: Any) -> None:
        self.scrolls.append((args, kwargs))

    def draw(self, **kwargs: Any) -> bool:
        from imgui_bundle import imgui

        self.draws += 1
        if self.draws >= self.fail_at:
            raise self.error("imtypeset failed and is switched off: Error: no")
        imgui.dummy(imgui.ImVec2(kwargs["width_px"], 10.0))
        return True


def test_a_typeset_view_that_fails_mid_run_leaves_the_page_alive_saying_why(unasked: None) -> None:
    """
    `TypesetUnavailable` does not leave `draw`; the next frame is the one line.

    Also the wiring this process can see without the library: the marks are
    handed over once per finder revision, as plain tuples.
    """
    made = TypesetPage(PageContext.build(), SOURCE)
    failing = _Failing()
    made.typeset = failing  # type: ignore[assignment]
    assert made.renderer == "TypesetView"
    assert made.marks == 4 and made.lines()[0].startswith("renderer: TypesetView")
    assert made.lines()[1].startswith("4 found, 4 marked")
    assert made.lines()[1].endswith("table cells are searched, formula source is not")
    assert made.lines()[2].startswith("1 table(s) in this document, set by the library")

    _frame(made.draw)
    assert (made.renderer, made.vertices) == ("TypesetView", 0)
    assert failing.marks == [made.finder.marks()]
    assert all(isinstance(mark, tuple) for mark in failing.marks[0])

    _frame(made.draw)  # raises inside; the page catches it
    assert failing.draws == 2 and made.typeset is None and made.renderer == "none"
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    assert made.lines() == (f"{page.NOT_DRAWING}: {made.reason}",) and made.marks == 0
    _frame(made.draw)
    assert failing.draws == 2 and made.frames == 3 and made.vertices == 0


def test_an_exception_that_is_not_typeset_unavailable_propagates(unasked: None) -> None:
    made = TypesetPage(PageContext.build(), SOURCE)
    failing = _Failing(fail_at=1, error=ZeroDivisionError)
    made.typeset = failing  # type: ignore[assignment]
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    # `draw` closed its pane on the way out, or ending the frame would assert.
    _frame(draw)
    assert len(raised) == 1 and made.typeset is failing and made.renderer == "TypesetView"


def test_typing_and_stepping_hand_the_view_new_marks_and_the_matchs_place(unasked: None) -> None:
    """
    Next and previous are `scroll_to(block, offset)` of the current match, once;
    a new needle is new marks, once.
    """
    made = TypesetPage(PageContext.build(), SOURCE)
    view = _Failing(fail_at=10**9)
    made.typeset = view  # type: ignore[assignment]
    _frame(made.draw)
    assert view.scrolls == [] and len(view.marks) == 1

    made.step(-1)  # wraps to the last match
    last = made.finder.matches[-1]
    _frame(made.draw)
    _frame(made.draw)
    assert view.scrolls == [((last.block, last.start), {"align": page.SHOW_AT})]
    assert len(view.marks) == 2  # the current match moved, so the marks did

    made.type("link")
    _frame(made.draw)
    _frame(made.draw)
    assert len(view.marks) == 3 and len(view.marks[-1]) == len(made.finder.matches) == 1
    assert len(view.scrolls) == 2

    made.type("zzqq")  # nothing to show: no scroll, and the marks are emptied
    _frame(made.draw)
    assert len(view.scrolls) == 2 and len(view.marks[-1]) == 0


# ----------------------------------------------------------------------
# 3. The real app in a real window
# ----------------------------------------------------------------------

WINDOWED = r"""
import json
import sys

from imgui_bundle import hello_imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app

WANT_LIBRARY = sys.argv[1] == "with"
report = {"frames": 0}
real_gui = imscribe_app.App.gui


def snapshot(made):
    view = made.typeset
    return {
        "renderer": made.renderer,
        "vertices": made.vertices,
        "marks": made.marks,
        "found": len(made.finder.matches),
        "scrolls": made.scrolls,
        "aligned": made.aligned,
        "lines": list(made.lines()),
        "edits": None if view is None else dict(view.edits),
        "tables": None if view is None else len(view.tables),
        "in_tables": None if view is None else sum(
            match.block in view.tables for match in made.finder.matches
        ),
    }


def watched_gui(self):
    real_gui(self)
    report["frames"] += 1
    frame = report["frames"]
    made = self._views.get("Typeset")
    if frame == 6:
        report["current"] = self.current
        report["ready"] = typesetter.ready()
        report["reason"] = made.reason
        if WANT_LIBRARY:
            assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
            assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
        report["needle"] = snapshot(made)
        made.finder.search("")          # not `type`: nothing may scroll between the two counts
    elif frame == 10:
        report["empty"] = snapshot(made)
        made.type("glue")
        made.step(-1)                   # the last match, far down the sample
    elif frame == 18:
        report["stepped"] = snapshot(made)
        report["trouble"] = typesetter.trouble()
        report["text"] = made.report()
        hello_imgui.get_runner_params().app_shall_exit = True


imscribe_app_errors = {}


def watched_gui_outer(self):
    watched_gui(self)
    imscribe_app_errors.update(self.page_errors)


imscribe_app.App.gui = watched_gui_outer
imscribe_app.run(tab="typeset")
report["imported"] = "imtypeset" in sys.modules
report["survived"] = "Typeset" not in imscribe_app_errors
print(json.dumps(report))
"""


def _run(window: Window, how: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    script = window.out / "page_typeset.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    report: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    print(how, window.where, json.dumps(report))  # shown by pytest when the test fails
    return report


def test_in_a_real_window_without_the_library_the_page_says_why_not_and_draws_no_document(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _run(window, "without", monkeypatch)
    assert report["current"] == "Typeset" and report["imported"] is False
    assert report["survived"] is True
    assert report["ready"] is False and report["reason"] == typesetter.SWITCHED_OFF_REASON
    for moment in ("needle", "empty", "stepped"):
        assert report[moment]["renderer"] == "none", report[moment]
        assert report[moment]["vertices"] == 0 and report[moment]["marks"] == 0
        assert report[moment]["lines"] == [
            f"imtypeset is not drawing: {typesetter.SWITCHED_OFF_REASON}"
        ]
        assert report[moment]["scrolls"] == 0
    # The find state needs no drawing.
    assert report["needle"]["found"] > 0 and report["empty"]["found"] == 0
    assert "renderer=none" in report["text"][0]


def test_in_a_real_window_with_the_library_the_typeset_path_draws_and_a_needle_makes_marks(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    report = _run(window, "with", monkeypatch)
    assert report["current"] == "Typeset" and report["imported"] is True
    assert report["survived"] is True
    assert report["ready"] is True and report["reason"] == "" and report["trouble"] == ""
    needle, empty, stepped = report["needle"], report["empty"], report["stepped"]
    for moment in (needle, empty, stepped):
        assert moment["renderer"] == "TypesetView", moment
        assert moment["aligned"] is True
        assert moment["vertices"] > 1000
        # One document, made once, and never edited by a search.
        assert moment["edits"] == {"set": 1, "replace": 0, "append": 0}
        assert moment["lines"][0] == "renderer: TypesetView (imtypeset, one retained document)"

    # The needle: as many marks as matches, and they are vertices on the pane's
    # draw list -- the same frame at the same scroll with no needle has fewer.
    assert needle["found"] > 0 and needle["marks"] == needle["found"]
    assert (empty["found"], empty["marks"]) == (0, 0)
    assert needle["scrolls"] == empty["scrolls"] == 0
    assert needle["vertices"] > empty["vertices"], (needle["vertices"], empty["vertices"])

    # The sample has a table, the library sets it, and the page says so. A
    # match in one of its cells is among the matches and is marked.
    assert needle["tables"] > 0
    assert needle["lines"][2].startswith(
        f"{needle['tables']} table(s) in this document, set by the library"
    )
    assert needle["in_tables"] > 0

    # Previous from the first match wraps to the last, which is not on the first screen.
    assert stepped["marks"] == stepped["found"] == needle["found"]
    assert stepped["scrolls"] >= 1

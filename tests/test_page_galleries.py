r"""
The Specimen, Formula and Math pages: one section of imtypeset's demo each,
or one line saying why not while the library is not ready.

Four layers, cheapest first:

1. **What the page modules are**: their sidebar entries, and an import that
   loads none of the old layout core (a fresh interpreter each, both ways of
   writing the import).
2. **Without the library**, in this process: each page is one wrapped line
   with the reason, nobody asked `typesetter.module()`, and building and
   drawing it imports nothing.
3. **With a stand-in for the library**, in this process (the real one is kept
   out of it: `advtext/typesetter.py`): the section is called once a frame,
   inside the page's child, at the theme's body size; the counts are the
   differences of `stats()`; the ways the page gives the section up.
4. **The real app in a real window** (`tests/conftest.py::window`), once with
   the library and once without, visiting the three pages in one run.

**Nothing here judges how a page looks.** The window tests count: vertices on
the child's draw list, the library's own figures, calls of the section.

The pages' old bodies (`_old_specimen.py`, `_old_formula.py`,
`_old_mathtext.py`) and `tests/test_page_math.py` were deleted in tranche 5
(T5-FB-C). `tests/test_specimen.py` and `tests/test_formulas.py` test
`advtext/ui/specimen.py` and `formulas.py`, which no page draws any more.
"""

from __future__ import annotations

import enum
import json
import os
import subprocess
import sys
import textwrap
import types
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext import typesetter
from advtext.ui.app import App, parse_tab_request
from advtext.ui.pages import PageContext, discover
from advtext.ui.pages import formula as formula_page
from advtext.ui.pages import mathtext as math_page
from advtext.ui.pages import specimen as specimen_page
from advtext.ui.pages import typeset as typeset_page
from advtext.ui.pages.specimen import STAT_NAMES, SectionPage, why_not
from advtext.ui.typeset_view import TypesetUnavailable
from tests.test_typeset_closure import OLD_CORE, THEME, _loaded_by

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from conftest import Window

_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
SIZE = (1300.0, 800.0)
TINY = "# t\n\nOne short paragraph.\n"

PAGES = {
    "Specimen": (specimen_page, specimen_page.SpecimenPage, "Specimen"),
    "Formula": (formula_page, formula_page.FormulaPage, "Formulas"),
    "Math": (math_page, math_page.MathPage, "Math"),
}
"""
Page name -> its module, its class, the `DemoSection` member.
"""

_ROOT = Path(__file__).resolve().parent.parent
ZERO = {key: 0 for key, _ in STAT_NAMES}


# ----------------------------------------------------------------------
# 1. What the page modules are
# ----------------------------------------------------------------------


def test_the_three_pages_are_listed_where_they_were_and_math_has_one_shot() -> None:
    """
    Name and sidebar place did not move. The Math page lost its `done` option
    and the second photograph with its old body (the section has no such
    state to open in), so `math:done` is refused like any unknown word.
    """
    found = {page.name: page for page in discover().pages}
    listed = {
        name: (
            found[name].order,
            found[name].group,
            found[name].label,
            found[name].options,
            found[name].shot_specs(),
        )
        for name in PAGES
    }
    assert listed == {
        "Specimen": (30, "Typesetting", "Specimen", (), ("specimen",)),
        "Formula": (40, "Typesetting", "Formula", (), ("formula",)),
        "Math": (60, "Typesetting", "Math in text", (), ("math",)),
    }
    for name, (module, cls, section) in PAGES.items():
        assert found[name] is module.PAGE and module.PAGE.factory is cls
        assert issubclass(cls, SectionPage) and cls.SECTION == section
        assert cls.__module__ == module.__name__
        assert not hasattr(cls, "OLD")
    assert not math_page.PAGE.accepts("done") and math_page.PAGE.accepts("debug")
    with pytest.raises(ValueError, match="done"):
        parse_tab_request("math:done", discover())


def test_the_old_bodies_are_gone_and_the_scan_finds_nothing_in_their_place() -> None:
    import importlib.util

    for old in ("_old_specimen", "_old_formula", "_old_mathtext"):
        assert importlib.util.find_spec(f"advtext.ui.pages.{old}") is None
    found = discover()
    assert not [name for name in found.modules.values() if "._old_" in name]
    assert not [failure for failure in found.failures if "_old_" in failure.module]


@pytest.mark.parametrize("form", ["import", "from"])
@pytest.mark.parametrize("name", sorted(PAGES))
def test_importing_a_page_loads_no_old_core(name: str, form: str) -> None:
    """
    A fresh interpreter, one import: none of the old core (two leaves a
    `Theme` needed until T5-B2), and not the library.
    """
    module = PAGES[name][0].__name__
    loaded = _loaded_by(module, form)
    assert module in loaded
    assert (loaded & OLD_CORE) == THEME, sorted(loaded & OLD_CORE)
    assert not {item for item in loaded if "._old_" in item}
    assert not loaded & {"advtext.style", "advtext.markdown", "advtext.stream"}


# ----------------------------------------------------------------------
# Frames with no backend
# ----------------------------------------------------------------------


def _imgui() -> Any:
    return pytest.importorskip("imgui_bundle").imgui


def _frame(draw: Any) -> int:
    """
    One frame of a context with no backend, `draw()` in a full-size window; the vertex count.
    """
    imgui = _imgui()
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
        imgui.begin("##advtext-page-galleries-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


# ----------------------------------------------------------------------
# 2. Without the library
# ----------------------------------------------------------------------


@pytest.fixture
def unasked(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    `advtext.typesetter` as at import, and a `module()` that fails the test if asked.
    """
    typesetter._forget()
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("the page asked for the library"))
    yield
    typesetter._forget()


def _added_by(draw: Any) -> int:
    """
    The vertices `draw` adds to the test window's own draw list in one frame.
    """
    imgui = _imgui()
    added = [0]

    def counted() -> None:
        vertices = imgui.get_window_draw_list().vtx_buffer
        before = vertices.size()
        draw()
        added[0] = vertices.size() - before

    _frame(counted)
    return added[0]


@pytest.mark.parametrize("name", sorted(PAGES))
def test_without_the_library_the_page_is_one_line_saying_why(
    name: str, unasked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Through the app's shell, three frames: no error page, no section, the
    reason. And the page's own frame is its sentence and nothing else: no
    caption, no separator, no child window.
    """
    imgui = _imgui()
    for variable in _VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    _module, cls, section = PAGES[name]
    app = App(source=TINY, columns_source=TINY, open_tab=name.lower())
    for _ in range(3):
        _frame(app.gui)
    assert app.page_errors == {}
    page = app.page(name)
    assert type(page) is cls and page.renderer == "none" and page.frames == 3
    assert page.reason == "IMTYPESET_LIBRARY is not set" and page.title == ""
    assert page.counts == ZERO
    sentence = f"{typeset_page.NOT_DRAWING}: IMTYPESET_LIBRARY is not set"
    assert page.line() == sentence
    assert page.report() == [
        f"frames=3 renderer=none section={section} size={page.size_px:.2f} "
        "paragraphs=0 vertices=0 layouts=0 reason='IMTYPESET_LIBRARY is not set'"
    ]
    assert _added_by(page.draw) == _added_by(lambda: imgui.text_wrapped(sentence)) > 0


def test_the_reason_does_not_say_the_variable_is_unset_when_it_is_set(
    unasked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, "/somewhere/libimtypeset_bundle.so")
    assert why_not() == specimen_page.FONTS_NOT_LOADED == typeset_page.FONTS_NOT_LOADED
    assert why_not is typeset_page.why_not, "one rule, in one place"
    page = math_page.MathPage(_context("math"))
    assert page.renderer == "none" and page.reason == specimen_page.FONTS_NOT_LOADED


def test_every_page_is_built_from_a_bare_context_with_no_app(unasked: None) -> None:
    """
    The old Specimen and Formula bodies drew material cached on `App` and
    raised "no app" without one. Nothing of a page needs the app now.
    """
    for _module, cls, _section in PAGES.values():
        page = cls(PageContext.build())
        assert page.renderer == "none" and page.reason


CLOSURE = r"""
import json
import sys

from imgui_bundle import imgui

from advtext.ui.pages import PageContext
from advtext.ui.pages import formula, mathtext, specimen

context = PageContext.build()
before = set(sys.modules)
made = [specimen.SpecimenPage(context), formula.FormulaPage(context), mathtext.MathPage(context)]
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
for _ in range(3):
    io.delta_time = 1.0 / 60.0
    imgui.new_frame()
    imgui.begin("x")
    for page in made:
        page.draw()
    imgui.end()
    imgui.render()
print(json.dumps({
    "added": sorted(name for name in set(sys.modules) - before if name.startswith("advtext")),
    "loaded": sorted(name for name in sys.modules if name.startswith("advtext")),
    "lines": [page.line() for page in made],
    "frames": [page.frames for page in made],
    "imtypeset": "imtypeset" in sys.modules,
}))
"""


def test_without_the_library_building_and_drawing_the_pages_import_nothing(
    tmp_path: Path,
) -> None:
    """
    A fresh interpreter, the library's variables removed: three frames of the
    three pages add no `advtext` module to what a `PageContext` loaded. In
    particular none of what the old bodies stood on.
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
    assert got["added"] == [] and got["imtypeset"] is False and got["frames"] == [3, 3, 3]
    assert got["lines"] == [f"{typeset_page.NOT_DRAWING}: IMTYPESET_LIBRARY is not set"] * 3
    loaded = set(got["loaded"])
    for gone in (
        "advtext.backends.imgui_draw",
        "advtext.markdown",
        "advtext.mathtext",
        "advtext.shipout",
        "advtext.stream",
        "advtext.ui.bare_view",
        "advtext.ui.document_view",
        "advtext.ui.formulas",
        "advtext.ui.specimen",
        "advtext.ui.stream_view",
    ):
        assert gone not in loaded


# ----------------------------------------------------------------------
# 3. With a stand-in for the library
# ----------------------------------------------------------------------

_FAKE = "advtext_test_fake_imtypeset"


class _Library(types.ModuleType):
    """
    What the page uses of imtypeset: `stats()`, and `<name>.demo` beside it.

    The section costs 3 paragraphs, 120 vertices and 1 layout each call, and
    records where it was called: ImGui's font size and the current window.
    """

    def __init__(self, titles: dict[str, str]) -> None:
        super().__init__(_FAKE)
        self.ready = True
        self.calls: list[tuple[int, float, str]] = []
        self.totals = {"DrawCalls": 10, "VerticesEmitted": 1000, "Layouts": 5, "TextBuilds": 7}
        self.raises: Exception | None = None

        class DemoSection(enum.IntEnum):
            Specimen = 2
            Math = 3
            Formulas = 4

        self.demo = types.ModuleType(f"{_FAKE}.demo")
        self.demo.DemoSection = DemoSection  # type: ignore[attr-defined]
        self.demo.section_name = lambda section: titles.get(  # type: ignore[attr-defined]
            DemoSection(section).name, ""
        )
        self.demo.show_demo_section = self._show  # type: ignore[attr-defined]

    def stats(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(**self.totals)

    def _show(self, section: int) -> None:
        imgui = _imgui()
        window = imgui.internal.get_current_window()
        self.calls.append((int(section), float(imgui.get_font_size()), str(window.name)))
        imgui.text_unformatted("the stand-in section")
        if self.raises is not None:
            raise self.raises
        self.totals["DrawCalls"] += 3
        self.totals["VerticesEmitted"] += 120
        self.totals["Layouts"] += 1


TITLES = {"Specimen": "Specimen", "Formulas": "Formula gallery", "Math": "Math"}


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Library]:
    """
    `typesetter.ready()` and `module()` answering for a stand-in library.
    """
    typesetter._forget()
    fake = _Library(dict(TITLES))
    monkeypatch.setitem(sys.modules, _FAKE, fake)
    monkeypatch.setitem(sys.modules, f"{_FAKE}.demo", fake.demo)
    monkeypatch.setattr(typesetter, "ready", lambda: fake.ready)
    monkeypatch.setattr(typesetter, "module", lambda: fake if fake.ready else None)
    yield fake
    typesetter._forget()


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_section_is_called_once_a_frame_in_the_child_at_the_body_size(
    name: str, library: _Library
) -> None:
    """
    No app: the page is built from a bare context.
    """
    imgui = _imgui()
    _module, cls, section = PAGES[name]
    page = cls(PageContext.build())
    assert page.renderer == "section" and page.reason == ""
    assert page.title == TITLES[section]
    assert page.counts == {"paragraphs": 0, "vertices": 0, "layouts": 0}

    sizes: list[float] = []

    def draw() -> None:
        sizes.append(float(imgui.get_font_size()))
        page.draw()
        sizes.append(float(imgui.get_font_size()))

    vertices = [_frame(draw) for _ in range(3)]
    assert page.renderer == "section" and page.frames == 3 and len(library.calls) == 3
    wanted = getattr(library.demo.DemoSection, section)
    for called, size, window in library.calls:
        assert called == wanted
        assert size == pytest.approx(page.size_px) and size != sizes[0]
        assert cls.CHILD in window, window
    # The size is pushed around the call and popped after it.
    assert len(set(sizes)) == 1
    assert page.counts == {"paragraphs": 3, "vertices": 120, "layouts": 1}
    assert vertices[-1] > 0
    assert f"section {TITLES[section]!r} at {page.size_px:.0f} px" in page.line()
    assert "3 paragraphs, 120 vertices, 1 layouts" in page.line()
    assert page.report() == [
        f"frames=3 renderer=section section={section} size={page.size_px:.2f} "
        "paragraphs=3 vertices=120 layouts=1"
    ]


def test_the_size_is_the_themes_body_size_in_pixels(library: _Library) -> None:
    from advtext.theme import BlockKind
    from advtext.units import px_from_sp

    context = PageContext.build(px_per_inch=144.0)
    page = specimen_page.SpecimenPage(context)
    body = context.theme.style(BlockKind.PARAGRAPH).font.size
    assert page.size_px == pytest.approx(px_from_sp(body, 144.0), abs=1e-3) and page.size_px > 0.0
    assert specimen_page.SpecimenPage(PageContext.build()).size_px == 16.0
    assert page.size_px == pytest.approx(
        1.5 * specimen_page.SpecimenPage(PageContext.build()).size_px
    )


def test_a_library_without_the_section_leaves_the_one_line(library: _Library) -> None:
    """
    A library built without its demo gives no section a title.
    """
    library.demo.section_name = lambda section: ""  # type: ignore[attr-defined]
    page = math_page.MathPage(_context("math"))
    assert page.renderer == "none"
    assert page.reason == "the loaded imtypeset library has no demo section Math"
    assert page.line() == f"{typeset_page.NOT_DRAWING}: {page.reason}"
    _frame(page.draw)
    assert library.calls == [] and page.frames == 1


def test_a_library_whose_demo_does_not_import_leaves_the_one_line(
    library: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, f"{_FAKE}.demo", None)
    page = math_page.MathPage(_context("math"))
    assert page.renderer == "none"
    assert page.reason.startswith("imtypeset's demo is not usable: ")
    _frame(page.draw)
    assert library.calls == []


def test_a_library_switched_off_later_makes_the_page_the_one_line_for_good(
    library: _Library,
) -> None:
    page = math_page.MathPage(_context("math"))
    _frame(page.draw)
    assert page.renderer == "section" and len(library.calls) == 1
    assert page.counts == {"paragraphs": 3, "vertices": 120, "layouts": 1}
    library.ready = False
    typesetter._reason = "switched off by a test"
    try:
        _frame(page.draw)
        _frame(page.draw)
    finally:
        typesetter._forget()
    assert page.renderer == "none" and len(library.calls) == 1
    assert page.reason == "switched off by a test" and page.title == ""
    assert page.counts == ZERO
    assert page.line() == f"{typeset_page.NOT_DRAWING}: switched off by a test"
    library.ready = True
    _frame(page.draw)
    assert page.renderer == "none" and len(library.calls) == 1, "the choice is not made twice"


def test_typeset_unavailable_out_of_the_section_is_caught_and_shown_from_the_next_frame(
    library: _Library,
) -> None:
    """
    Through the app's shell: the page stays alive (no entry in `page_errors`),
    the child was ended and the font popped (the frame closes), and the next
    frames are the one line with the exception's sentence.
    """
    library.raises = TypesetUnavailable("imtypeset failed and is switched off: Error: no")
    app = App(source=TINY, columns_source=TINY, open_tab="formula")
    _frame(app.gui)
    assert app.page_errors == {}
    page = app.page("formula")
    assert isinstance(page, SectionPage)
    assert page.renderer == "none" and len(library.calls) == 1
    assert page.reason == "imtypeset failed and is switched off: Error: no"
    library.raises = None
    _frame(app.gui)
    _frame(app.gui)
    assert app.page_errors == {} and len(library.calls) == 1 and page.frames == 3
    assert page.line() == f"{typeset_page.NOT_DRAWING}: {page.reason}"


def test_an_exception_out_of_the_section_reaches_the_apps_page_error(
    library: _Library, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Not caught by the page: the app shows the traceback in its place, and the
    frame still ends, the child closed and the font popped by the page.
    """
    library.raises = ValueError("the section failed")
    app = App(source=TINY, columns_source=TINY, open_tab="specimen")
    assert _frame(app.gui) > 0
    assert "the section failed" in app.page_errors["Specimen"]
    assert "the section failed" in capsys.readouterr().err
    page = app.page("specimen")
    assert page.renderer == "section" and len(library.calls) == 1  # type: ignore[attr-defined]
    assert _frame(app.gui) > 0
    assert len(library.calls) == 1, "a page that raised is not drawn again until Retry"


# ----------------------------------------------------------------------
# 4. The real app in a real window
# ----------------------------------------------------------------------

WINDOWED = r"""
import json
import sys

from imgui_bundle import hello_imgui, imgui

from advtext import typesetter
from advtext.ui import app as advtext_app

WANT_LIBRARY = sys.argv[1] == "with"
ORDER = ("Specimen", "Formula", "Math")
STAY = 8
report = {"frames": 0, "pages": {}}
seen = {"calls": 0, "child": 0, "size": 0.0, "window": ""}
real_gui = advtext_app.App.gui


def watch(demo):
    real = demo.show_demo_section

    def shown(section):
        before = imgui.get_window_draw_list().vtx_buffer.size()
        seen["size"] = imgui.get_font_size()
        seen["window"] = imgui.internal.get_current_window().name
        real(section)
        seen["calls"] += 1
        seen["child"] = imgui.get_window_draw_list().vtx_buffer.size() - before

    demo.show_demo_section = shown


def watched_gui(self):
    if report["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
        report["ui_size"] = imgui.get_font_size()
    real_gui(self)
    report["frames"] += 1
    frame = report["frames"]
    at, step = divmod(frame - 1, STAY)
    name = ORDER[at]
    made = self._views.get(name)
    if step == 0 and WANT_LIBRARY:
        assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
        assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
        if at == 0:
            watch(made._demo)
        report["stats_" + name] = typesetter.module().stats().DrawCalls
    if step == STAY - 1:
        entry = {
            "current": self.current,
            "renderer": made.renderer,
            "reason": made.reason,
            "title": made.title,
            "size": made.size_px,
            "frames": made.frames,
            "counts": dict(made.counts),
            "report": made.report(),
            "line": made.line(),
            "seen": dict(seen),
        }
        if WANT_LIBRARY:
            error = typesetter.module().last_error()
            entry["last_error"] = int(error.code)
        report["pages"][name] = entry
        seen.update(calls=0, child=0, size=0.0, window="")
        if at + 1 < len(ORDER):
            self.select(ORDER[at + 1])
        else:
            report["ready"] = typesetter.ready()
            report["trouble"] = typesetter.trouble()
            report["errors"] = sorted(self.page_errors)
            hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="specimen")
report["imported"] = "imtypeset" in sys.modules
report["old_loaded"] = sorted(
    name for name in sys.modules
    if "._old_" in name or name in ("advtext.ui.specimen", "advtext.ui.formulas")
)
report["old_core_loaded"] = sorted(
    name for name in sys.modules
    if name in ("advtext.mathtext", "advtext.ui.stream_view")
)
print(json.dumps(report))
"""

STAY = 8
"""Frames each page is shown for in the window run; `WINDOWED` has the same number."""


def _run(window: Window, how: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    script = window.out / "page_galleries.py"
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


def test_in_a_real_window_without_the_library_the_three_pages_say_why_not(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The app survives all three pages for eight frames each with no library:
    no error page, no section called, the reason in each page's line.
    (`report["old_loaded"]` is printed and not asserted: what the app itself
    still imports is T5-APP's.)
    """
    report = _run(window, "without", monkeypatch)
    assert report["imported"] is False and report["errors"] == []
    for name, (_module, _cls, section) in PAGES.items():
        entry = report["pages"][name]
        assert entry["current"] == name and entry["frames"] == STAY
        assert entry["renderer"] == "none" and entry["title"] == ""
        assert entry["reason"] == "IMTYPESET_LIBRARY is not set"
        assert entry["line"] == "imtypeset is not drawing: IMTYPESET_LIBRARY is not set"
        assert entry["counts"] == ZERO and entry["seen"]["calls"] == 0
        assert entry["report"] == [
            f"frames={STAY} renderer=none section={section} size={entry['size']:.2f} "
            "paragraphs=0 vertices=0 layouts=0 reason='IMTYPESET_LIBRARY is not set'"
        ]


def test_in_a_real_window_with_the_library_each_page_draws_its_section(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Counts only. Each section, shown for eight frames as it opens: it was
    called once a frame in the page's child at the page's size; it put
    vertices on that child's draw list; the library says it drew paragraphs
    and emitted vertices in the last frame; and no page raised. Nobody
    looked at the window.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    report = _run(window, "with", monkeypatch)
    assert report["imported"] is True and report["ready"] is True
    assert report["errors"] == [] and report["trouble"] == ""
    titles = {"Specimen": "Specimen", "Formula": "Formula gallery", "Math": "Math"}
    for name, (_module, cls, section) in PAGES.items():
        entry = report["pages"][name]
        assert entry["current"] == name and entry["frames"] == STAY
        assert entry["renderer"] == "section" and entry["reason"] == ""
        assert entry["title"] == titles[name]
        seen, counts = entry["seen"], entry["counts"]
        # Once a frame. The first frame's call is counted for the first page
        # only from the frame after the watch was put in.
        assert seen["calls"] == (STAY - 1 if name == "Specimen" else STAY), seen
        assert cls.CHILD in seen["window"]
        assert seen["size"] == pytest.approx(entry["size"]) and entry["size"] > 0.0
        assert seen["child"] > 0, f"{name}: nothing on the child's draw list"
        assert counts["paragraphs"] > 0 and counts["vertices"] > 0, counts
        assert entry["report"] == [
            f"frames={STAY} renderer=section section={section} size={entry['size']:.2f} "
            f"paragraphs={counts['paragraphs']} vertices={counts['vertices']} "
            f"layouts={counts['layouts']}"
        ]

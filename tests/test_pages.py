"""
The demo's pages: the scan that finds them, the contract they are held to, and
the shell that lists and draws them.

**What is and is not a real frame here.** The scan, the `PageSpec` rules, the
request grammar and `sidebar_rows` are pure and are tested as such. `App.gui` is
then driven through frames of a real `ImGuiContext` with no backend -- the idiom
`tests/test_document_view.py::_page_frame` established -- which makes ImGui's
own layout, hover resolution and click handling the thing under test, without a
window. The last test opens the real app in a real window (on the session's
display, or an Xvfb; `tests/conftest.py::window`) and shows every discovered
page for a few frames each. That one is the "each page is run once in a window"
check for every page, including pages added after this file was written: it
asks the scan what there is.

**The scan's failure cases use a package built for the purpose** under
`tmp_path`, because the real package must have none: `test_every_module_in_the_
real_package_is_a_page` is the test that goes red when somebody's page module
does not import.
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext.ui import app as app_module
from advtext.ui import pages
from advtext.ui.app import App, TabRequest, parse_tab_request, sidebar_rows
from advtext.ui.pages import Discovery, Failure, PageContext, PageSpec

if TYPE_CHECKING:
    from conftest import Window

TINY = "# t\n\nOne short paragraph.\n"
ORIGINAL = ("Document", "Columns", "Specimen", "Formula")


class _Recorder:
    """
    A page that draws one line and remembers what it was handed and when.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.frames = 0
        self.available: tuple[float, float] | None = None
        self.cursor: tuple[float, float] | None = None

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        avail = imgui.get_content_region_avail()
        self.available = (avail.x, avail.y)
        cursor = imgui.get_cursor_screen_pos()
        self.cursor = (cursor.x, cursor.y)
        imgui.text_unformatted("recorder")


def _spec(name: str, order: int, **fields: Any) -> PageSpec:
    return PageSpec(name=name, order=order, factory=_Recorder, **fields)


# ----------------------------------------------------------------------
# The real package
# ----------------------------------------------------------------------


def test_every_module_in_the_real_package_is_a_page() -> None:
    """
    The red test for a page module that does not import, has no `PAGE`, or takes
    a name another page has. `require` raises with every reason at once, so the
    failure message is the list of what to fix.
    """
    found = pages.require()
    assert found.failures == ()


def test_the_original_pages_come_first_in_their_old_order() -> None:
    """
    Document, Columns, Specimen, Formula: the tab bar's order, and still the
    head of the list however many pages are added after them, because the
    page that opens when nothing is asked for is the first one.

    There were five. Blocks showed the old core's `hpack` and `vpack` at
    three widths and was deleted with tranche 5 (`.concerns/lead--tranche-5.md`,
    decision 3): boxes are imtypeset's, and it exposes none.
    """
    names = [page.name for page in pages.discover().pages]
    assert tuple(names[:4]) == ORIGINAL
    assert pages.discover().find("blocks") is None


SIDEBAR = (
    ("Typesetting", "Document", "Document", 10),
    ("Typesetting", "Columns", "Columns", 20),
    ("Typesetting", "Specimen", "Specimen", 30),
    ("Typesetting", "Formula", "Formula", 40),
    ("Typesetting", "Math", "Math in text", 60),
    ("Embedding", "Themes", "Themes", 110),
    ("Embedding", "Tables", "Tables", 120),
    ("Embedding", "Find", "Find", 130),
    ("Embedding", "Inspector", "Inspector", 140),
    ("Streaming", "Stream", "Stream", 210),
    ("Streaming", "Chat", "Chat", 220),
    ("Diff", "Diff", "Diff", 310),
    ("Performance", "Stress", "Stress", 410),
    ("Experimental", "Typeset", "Typeset", 510),
)
"""
The whole sidebar: group, name, label and order of every page, top to bottom.

`.concerns/lead--demo-page-order.md` written out. A literal on purpose: the
pages are discovered and each states its own place, so nothing else would
notice two of them claiming one number, or one drifting into another group's
range -- which three had done within a day of the scan existing (Stream at
110, Themes at 210, Stress at 210 under a group of its own). Adding a page
means adding its row here.
"""


def test_the_sidebar_is_exactly_the_agreed_list() -> None:
    found = pages.discover().pages
    assert tuple((page.group, page.name, page.label, page.order) for page in found) == SIDEBAR
    orders = [page.order for page in found]
    assert len(set(orders)) == len(orders), "two pages share an order"
    # A group is one run of rows: its heading is drawn once.
    headings = [row.text for row in sidebar_rows(pages.discover()) if row.kind == "heading"]
    assert headings == [
        "Typesetting",
        "Embedding",
        "Streaming",
        "Diff",
        "Performance",
        "Experimental",
    ]


def test_page_names_are_unique_without_regard_to_case() -> None:
    names = [page.name.lower() for page in pages.discover().pages]
    assert len(set(names)) == len(names), names


def test_tab_names_is_a_view_of_the_scan_and_not_a_copy() -> None:
    """
    `advtext.ui.app.TAB_NAMES` was a literal tuple; `scripts/visual_diff.py` and
    several tests import it. It is computed from the scan now, so swapping the
    scan must change it.
    """
    assert tuple(app_module.TAB_NAMES) == tuple(page.name for page in pages.discover().pages)
    assert app_module.page_names() == tuple(app_module.TAB_NAMES)
    with pytest.raises(AttributeError):
        _ = app_module.NO_SUCH_NAME


# ----------------------------------------------------------------------
# The scan, on a package made to break it
# ----------------------------------------------------------------------


@pytest.fixture
def fake_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """
    A package with one good page, and one module for each way of not being one.

    `_helper.py` raises on import: the scan must never import it, and the only
    way to show that is for importing it to be noticeable.
    """
    name = "advtext_fake_pages_for_test"
    root = tmp_path / name
    root.mkdir()
    header = (
        "from advtext.ui.pages import PageSpec\n\n\n"
        "class P:\n    def __init__(self, c): pass\n    def draw(self): pass\n\n\n"
    )
    files = {
        "__init__.py": "",
        "good.py": header + 'PAGE = PageSpec(name="Good", order=20, factory=P)\n',
        "early.py": header
        + 'PAGE = PageSpec(name="Early", order=10, factory=P, shots=("", "2"))\n',
        "broken.py": "import a_module_that_does_not_exist_anywhere\n",
        "empty.py": "X = 1\n",
        "wrongtype.py": 'PAGE = "not a spec"\n',
        "twin.py": header + 'PAGE = PageSpec(name="GOOD", order=5, factory=P)\n',
        "spaced.py": header + 'PAGE = PageSpec(name="Two Words", order=1, factory=P)\n',
        "_helper.py": 'raise RuntimeError("a private module was imported by the scan")\n',
    }
    for filename, body in files.items():
        (root / filename).write_text(body, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield name
    finally:
        for loaded in [key for key in sys.modules if key.split(".")[0] == name]:
            del sys.modules[loaded]


def test_the_scan_keeps_the_good_pages_in_order(fake_package: str) -> None:
    found = pages.discover(fake_package)
    assert [page.name for page in found.pages] == ["Early", "Good"]
    assert found.shot_specs() == ("early", "early:2", "good")


def test_every_way_of_not_being_a_page_is_reported_by_name(fake_package: str) -> None:
    """
    Five modules, five failures, each naming its module and its own reason.

    A scan that swallowed any of these would show a demo with a page missing
    and nothing saying so -- the stale-list defect, reintroduced by the
    mechanism that replaced the list.
    """
    found = pages.discover(fake_package)
    reasons = {failure.module.rpartition(".")[2]: failure.reason for failure in found.failures}
    assert set(reasons) == {"broken", "empty", "wrongtype", "twin", "spaced"}
    assert "ModuleNotFoundError" in reasons["broken"]
    assert "a_module_that_does_not_exist_anywhere" in reasons["broken"]
    assert reasons["empty"] == "defines no PAGE"
    assert "not a PageSpec" in reasons["wrongtype"]
    assert "already taken" in reasons["twin"] and f"{fake_package}.good" in reasons["twin"]
    assert "one word" in reasons["spaced"]


def test_a_module_with_a_leading_underscore_is_never_imported(fake_package: str) -> None:
    found = pages.discover(fake_package)
    assert f"{fake_package}._helper" not in sys.modules
    assert all("_helper" not in failure.module for failure in found.failures)


def test_require_raises_naming_every_failure_at_once(fake_package: str) -> None:
    with pytest.raises(pages.PageLoadError) as caught:
        pages.require(fake_package)
    message = str(caught.value)
    for module in ("broken", "empty", "wrongtype", "twin", "spaced"):
        assert f"{fake_package}.{module}" in message


def test_a_module_fixed_on_disk_is_found_by_the_next_scan(fake_package: str) -> None:
    """
    The scan is not cached, and a module that failed to import is not in
    `sys.modules`, so the next scan tries it again.
    """
    assert pages.discover(fake_package).find("Mended") is None
    root = Path(sys.modules[fake_package].__path__[0])
    (root / "broken.py").write_text(
        "from advtext.ui.pages import PageSpec\n"
        'PAGE = PageSpec(name="Mended", order=1, factory=lambda context: None)\n',
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    assert pages.discover(fake_package).find("mended") is not None


# ----------------------------------------------------------------------
# PageSpec and PageContext
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Two Words", "", "3d", "a:b", "a,b", "tab\tbed"])
def test_a_name_tab_could_not_address_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="one word"):
        _spec(name, 1)


@pytest.mark.parametrize("word", ["debug", "Wide", "3", "two words", ""])
def test_an_option_word_that_would_be_ambiguous_is_refused(word: str) -> None:
    """
    `debug` and integers already mean something on every page, and the request
    grammar compares words exactly, so an upper-case word could never match.
    """
    with pytest.raises(ValueError, match="option"):
        _spec("Page", 1, options=(word,))


def test_a_shot_may_only_carry_words_the_page_accepts() -> None:
    assert _spec(
        "Page", 1, options=("wide",), shots=("", "wide", "3,debug", "wide,2")
    ).shot_specs() == (
        "page",
        "page:wide",
        "page:3,debug",
        "page:wide,2",
    )
    with pytest.raises(ValueError, match="'narrow'"):
        _spec("Page", 1, options=("wide",), shots=("narrow",))


def test_the_label_is_the_title_when_there_is_one() -> None:
    assert _spec("Math", 1, title="Math in text").label == "Math in text"
    assert _spec("Math", 1).label == "Math"


def test_a_context_from_the_defaults_needs_no_app_and_no_window() -> None:
    """
    `PageContext.build()` is what a page's own test builds its page from.
    """
    context = PageContext.build()
    assert context.debug is False
    assert context.source is None and context.columns_source is None
    from advtext.fontmetrics import Face

    assert context.fonts(Face.PROSE) is None
    assert context.theme is not None
    assert context.metrics is pages.face_metrics
    assert PageContext.build(debug=True, px_per_inch=120.0).px_per_inch == 120.0
    assert PageContext.build(source="# s\n").source == "# s\n"
    # What the context carried for the old views is gone, as a field and as a keyword.
    for gone in ("measure", "app", "require_app"):
        assert not hasattr(context, gone), f"PageContext.{gone} is back"
    with pytest.raises(TypeError):
        PageContext.build(measure=None)
    for helper in ("draw_at", "paint_sheet", "plate", "claim", "available_width"):
        assert not hasattr(pages, helper), f"advtext.ui.pages.{helper} is back"


def test_the_contexts_one_measurement_is_the_font_files_own() -> None:
    """
    `PageContext.metrics` is what `Theme.at_pixel_height` is handed, and it
    answers what `advtext.style.fontlib_metrics` answers: asked for the body
    face at a size, it gives that face's em, ascent and descent.
    """
    from advtext.fontmetrics import Face
    from advtext.style import fontlib_metrics
    from advtext.theme import Theme, font_key
    from advtext.units import sp_from_px

    key = font_key(Face.PROSE, sp_from_px(16.0))
    mine, theirs = pages.face_metrics(key), fontlib_metrics(key)
    assert (mine.em, mine.ascent, mine.descent) == (theirs.em, theirs.ascent, theirs.descent)
    assert mine.em > 0 and mine.ascent > 0
    context = PageContext.build()
    sized = Theme.at_pixel_height(18.0, metrics=context.metrics)
    assert sized == Theme.at_pixel_height(18.0)


def test_a_page_reads_only_the_options_addressed_to_it() -> None:
    context = PageContext.build(request_page="tables", request_options=("wide",), request_count=4)
    assert context.options_for("Tables") == ("wide",)
    assert context.count_for("TABLES") == 4
    assert context.options_for("Stream") == ()
    assert context.count_for("Stream") is None


# ----------------------------------------------------------------------
# The request grammar, for a page with words of its own
# ----------------------------------------------------------------------

FAKE = Discovery(
    (
        _spec("Alpha", 10, group="One", caption="first"),
        _spec("Beta", 20, group="One", options=("wide", "dark"), title="Beta page"),
        _spec("Gamma", 30, group="Two"),
    )
)


def test_a_pages_own_option_words_are_parsed_and_kept_in_order() -> None:
    assert parse_tab_request("beta:dark,3,wide,debug", FAKE) == TabRequest(
        tab="beta", columns=3, debug=True, options=("dark", "wide")
    )


def test_a_word_is_only_an_option_on_the_page_that_declares_it() -> None:
    """
    `wide` is Beta's. On Alpha it is a misspelling like any other, and the
    refusal names it; on Beta a word that is nobody's is refused and the message
    lists the ones Beta does take.
    """
    with pytest.raises(ValueError, match="'wide' is not a tab option"):
        parse_tab_request("alpha:wide", FAKE)
    with pytest.raises(ValueError) as caught:
        parse_tab_request("beta:tall", FAKE)
    assert "'tall' is not a tab option" in str(caught.value)
    assert "'wide'" in str(caught.value) and "'dark'" in str(caught.value)


def test_an_unknown_name_is_refused_with_the_scans_names_and_its_failures() -> None:
    broken = Discovery(FAKE.pages, (Failure("pkg.delta", "ImportError: no"),))
    with pytest.raises(ValueError) as caught:
        parse_tab_request("delta", broken)
    message = str(caught.value)
    assert "'delta' is not a tab" in message
    assert "Alpha, Beta, Gamma" in message
    assert "pkg.delta" in message and "ImportError: no" in message


# ----------------------------------------------------------------------
# The sidebar, as rows
# ----------------------------------------------------------------------


def test_the_sidebar_lists_pages_under_their_group_headings() -> None:
    rows = sidebar_rows(FAKE)
    assert [(row.kind, row.text) for row in rows] == [
        ("heading", "One"),
        ("page", "Alpha"),
        ("page", "Beta page"),
        ("heading", "Two"),
        ("page", "Gamma"),
    ]
    assert rows[1].detail == "first"
    assert rows[2].page is FAKE.pages[1]


def test_a_module_that_failed_is_listed_with_its_reason() -> None:
    rows = sidebar_rows(Discovery(FAKE.pages, (Failure("pkg.delta", "ImportError: no"),)))
    assert [(row.kind, row.text, row.detail) for row in rows[-2:]] == [
        ("heading", "failed to load", ""),
        ("failure", "delta", "ImportError: no"),
    ]


def test_pages_with_no_group_get_no_heading() -> None:
    rows = sidebar_rows(Discovery((_spec("Solo", 1), _spec("Duo", 2))))
    assert [row.kind for row in rows] == ["page", "page"]


# ----------------------------------------------------------------------
# The shell, through real ImGui frames
# ----------------------------------------------------------------------

SIZE = (1300.0, 800.0)


def _frame(
    app: App, *, mouse: tuple[float, float] | None = None, button: bool | None = None
) -> int:
    """
    One frame of `App.gui` in a full-size window of a context with no backend.

    Returns the frame's vertex count, which is the cheapest evidence that
    something was drawn.
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
        # No title bar, as hello_imgui's full-screen window has none, so the
        # body starts at the window's padding.
        imgui.begin("##advtext-pages-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            app.gui()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def _release(app: App) -> None:
    """
    Leave the pointer up and off the window for whichever test runs next.
    """
    _frame(app, mouse=(-1.0e6, -1.0e6), button=False)


def _fake_app(found: Discovery = FAKE, open_tab: str | None = None) -> App:
    """
    A real `App` whose scan is replaced, so the shell is tested on pages that record.
    """
    app = App(source=TINY, columns_source=TINY)
    app.discovery = found
    app.current = found.pages[0].name if found.pages else None
    app._views.clear()
    if open_tab is not None:
        request = parse_tab_request(open_tab, found)
        app.open_tab = request.tab
        app.context.request_page = request.tab
        app.context.request_options = request.options
    return app


def test_the_first_page_in_order_is_the_one_that_opens() -> None:
    app = App(source=TINY, columns_source=TINY)
    assert app.current == "Document"
    assert app._views == {}, "a page was built before any frame asked for it"


def test_only_the_page_that_is_showing_is_built_and_drawn() -> None:
    """
    Lazy, and kept: the factory runs on the first frame a page is shown, once.
    """
    app = _fake_app()
    _frame(app)
    _frame(app)
    assert list(app._views) == ["Alpha"]
    alpha = app._views["Alpha"]
    assert isinstance(alpha, _Recorder) and alpha.frames == 2
    assert alpha.context is app.context

    app.select("gamma")
    _frame(app)
    assert list(app._views) == ["Alpha", "Gamma"]
    assert alpha.frames == 2, "a page that is not showing was drawn"
    app.select("ALPHA")
    _frame(app)
    assert app._views["Alpha"] is alpha, "the page object was rebuilt; its state would be lost"
    assert alpha.frames == 3


def test_open_tab_selects_once_and_then_lets_go() -> None:
    """
    Held, `open_tab` would re-select every frame and the list could never be
    clicked away from.
    """
    app = _fake_app(open_tab="beta:wide")
    assert app.current == "Alpha"
    _frame(app)
    assert (app.current, app.open_tab) == ("Beta", None)
    beta = app._views["Beta"]
    assert isinstance(beta, _Recorder)
    assert beta.context.options_for("Beta") == ("wide",)
    app.select("Alpha")
    _frame(app)
    assert app.current == "Alpha"


def test_selecting_a_name_that_is_no_page_is_an_error() -> None:
    app = _fake_app()
    with pytest.raises(KeyError):
        app.select("delta")
    with pytest.raises(KeyError):
        app.page("delta")


def test_a_page_is_handed_the_window_less_the_sidebar() -> None:
    """
    The body starts one sidebar and one item spacing in from the window's
    padding, at the window's top, and is offered everything to the right.

    Stated against the live style and not as literals: this context has ImGui's
    default style, the real app has `apply_style`'s. With `apply_style`'s
    16 px padding and 12 px spacing the same arithmetic is 1300 - 32 - 188 - 12
    = 1068 px, the body width the tab bar gave at 1100; that figure was measured
    in a real window and is recorded in `advtext.ui.app.WINDOW_SIZE`.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    app = _fake_app()
    _frame(app)
    page = app._views["Alpha"]
    assert isinstance(page, _Recorder) and page.available and page.cursor
    style = imgui.get_style()
    left = style.window_padding.x + app_module.SIDEBAR_WIDTH_PX + style.item_spacing.x
    assert page.cursor[0] == pytest.approx(left)
    assert page.cursor[1] == pytest.approx(style.window_padding.y)
    assert page.available[0] == pytest.approx(SIZE[0] - left - style.window_padding.x)
    assert page.available[1] == pytest.approx(SIZE[1] - 2 * style.window_padding.y)


def test_a_click_on_a_row_of_the_sidebar_shows_that_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A press and release on a row, resolved by ImGui's own hover and click logic.

    Where the rows are is read from ImGui, by recording each selectable's item
    rectangle as the app submits it; nothing here assumes a row height.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    rects: dict[str, tuple[float, float, float, float]] = {}
    real = imgui.selectable

    def recording(label: str, *args: Any, **kwargs: Any) -> Any:
        result = real(label, *args, **kwargs)
        low, high = imgui.get_item_rect_min(), imgui.get_item_rect_max()
        rects[label.partition("##")[0]] = (low.x, low.y, high.x, high.y)
        return result

    monkeypatch.setattr(imgui, "selectable", recording)
    app = _fake_app()
    try:
        _frame(app)
        assert set(rects) == {"Alpha", "Beta page", "Gamma"}
        # The rows are inside the sidebar and one above the other.
        # A selectable's rectangle reaches half an item spacing past the
        # content it sits in, which the sidebar's clip rectangle then cuts.
        style = imgui.get_style()
        limit = style.window_padding.x + app_module.SIDEBAR_WIDTH_PX + style.item_spacing.x / 2
        for x0, _, x1, _ in rects.values():
            assert x1 <= limit
            assert x1 > x0
        assert rects["Alpha"][1] < rects["Beta page"][1] < rects["Gamma"][1]

        x0, y0, x1, y1 = rects["Gamma"]
        point = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        _frame(app, mouse=point)
        _frame(app, button=True)
        _frame(app, button=False)
        _frame(app)
        assert app.current == "Gamma"
        gamma = app._views["Gamma"]
        assert isinstance(gamma, _Recorder) and gamma.frames >= 1
    finally:
        _release(app)


def test_a_failed_module_is_drawn_in_the_list_and_the_rest_still_works() -> None:
    app = _fake_app(Discovery(FAKE.pages, (Failure("pkg.delta", "ImportError: no"),)))
    with_failure = _frame(app)
    without = _frame(_fake_app())
    assert with_failure > without, "the failure rows added nothing to the frame"
    assert app.current == "Alpha" and isinstance(app._views["Alpha"], _Recorder)


def test_an_app_with_no_pages_says_so_instead_of_crashing() -> None:
    app = _fake_app(Discovery(()))
    assert app.current is None
    assert _frame(app) > 0


def _said(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """
    Every string a page hands `imgui.text_wrapped` from here on, in order.

    `advtext.ui.pages.typeset.say_why_not` draws its line with that call.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    said: list[str] = []
    real = imgui.text_wrapped

    def recording(text: str) -> None:
        said.append(text)
        real(text)

    monkeypatch.setattr(imgui, "text_wrapped", recording)
    return said


@pytest.mark.parametrize("name", [row[1] for row in SIDEBAR])
def test_each_page_without_the_library_says_why_not_in_one_line_through_the_shell(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Every page, shown for three frames in a process where imtypeset is not loaded.

    The pytest process never loads the library, with `TYPESET=1` or without
    (the tests that need it open a window in a child), so this is the same
    statement on both gates: the page object comes from its own module, it
    raises nothing, and each frame it draws exactly one wrapped line, which
    begins `NOT_DRAWING` and carries `why_not()`'s reason. It draws that and
    no old view: `advtext.ui.bare_view`, `document_view`, `stream_view`,
    `diff_view` and the old draw backend are not loaded by showing it
    (`tests/test_typeset_closure.py` has the same statement per module, in a
    fresh interpreter, for import time).

    This replaces `test_each_original_page_draws_frames_through_the_shell`,
    which showed the five original pages and asked only that vertices were
    added -- true then of text set by the old core, and true now of one line.
    """
    from advtext import typesetter
    from advtext.ui.pages.typeset import NOT_DRAWING, not_drawing, why_not

    assert not typesetter.ready(), "the library is loaded in the pytest process"
    said = _said(monkeypatch)
    app = App(source=TINY, columns_source=TINY, open_tab=name.lower())
    empty = _fake_app(Discovery(()))
    baseline = _frame(empty)
    said.clear()
    counts = []
    for _ in range(3):
        before = len(said)
        counts.append(_frame(app))
        assert said[before:] == [not_drawing(why_not())], f"{name} said {said[before:]}"
    assert said[0].startswith(NOT_DRAWING) and len(said[0]) > len(NOT_DRAWING)
    assert app.page_errors == {}, app.page_errors
    assert app.current == name
    page = app._views[name]
    assert type(page).__module__.startswith("advtext.ui.pages.")
    assert list(app._views) == [name]
    assert counts[-1] > baseline, f"{name} drew nothing: {counts} against {baseline}"


OLD_VIEWS = (
    "advtext.ui.bare_view",
    "advtext.ui.document_view",
    "advtext.ui.stream_view",
    "advtext.ui.diff_view",
    "advtext.ui.specimen",
    "advtext.ui.formulas",
    "advtext.ui.composition",
    "advtext.backends.imgui_draw",
    "advtext.shipout",
    "advtext.linebreak",
    "advtext.columns",
    "advtext.blocklayout",
)
"""
The old views, the old draw backend, and the parts of the old core only they
reach. What a page without the library must not load by being shown.
"""

SHOWN = """
import json
import sys

from imgui_bundle import imgui

from advtext.ui import app as advtext_app

OLD = {old!r}
names = list(advtext_app.page_names())
report = {{"after_import": sorted(m for m in sys.modules if m in OLD), "pages": {{}}}}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
app = advtext_app.App(source="# t\\n\\nOne short paragraph.\\n")
report["after_app"] = sorted(m for m in sys.modules if m in OLD)
for name in names:
    app.select(name)
    for _ in range(3):
        io.delta_time = 1.0 / 60.0
        imgui.new_frame()
        imgui.set_next_window_size(imgui.ImVec2(1300.0, 800.0))
        imgui.begin("##shown", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
        imgui.render()
    report["pages"][name] = sorted(m for m in sys.modules if m in OLD)
report["errors"] = sorted(app.page_errors)
print(json.dumps(report))
"""


def test_showing_every_page_without_the_library_loads_no_old_view() -> None:
    """
    A fresh interpreter with no library: import the app, build it, show every
    page for three headless frames. None of `OLD_VIEWS` is in `sys.modules`
    at any point, and no page raised.

    In a child because `sys.modules` of the pytest process holds whatever
    earlier tests imported. The library's two variables are removed from the
    child's environment, so the statement is the plain gate's on both gates.
    """
    import json
    import os
    import subprocess

    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("IMTYPESET_")
    }
    done = subprocess.run(
        [sys.executable, "-c", SHOWN.format(old=OLD_VIEWS)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        env=environment,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["errors"] == []
    assert report["after_import"] == [] and report["after_app"] == []
    assert set(report["pages"]) == {row[1] for row in SIDEBAR}
    loaded = {name: found for name, found in report["pages"].items() if found}
    assert loaded == {}, f"showing a page loaded an old view: {loaded}"


def test_the_debug_overlay_is_one_flag_shared_by_every_page() -> None:
    """
    `--tab columns:debug` turns the overlay on for every page: the flag is
    `PageContext.debug`, one object, and each page is built from that context.

    This used to end by reading the flag back off the app's `DocumentView`
    after a frame of the Document page. The app holds no view now; what a
    page does with the flag is its own test's subject.
    """
    found = Discovery((_spec("Columns", 10), _spec("Document", 20)))
    app = _fake_app(found, open_tab="columns:debug")
    app.context.debug = parse_tab_request("columns:debug", found).debug
    assert app.context.debug is True
    _frame(app)
    app.select("Document")
    _frame(app)
    seen = [app._views[name].context for name in ("Columns", "Document")]  # type: ignore[attr-defined]
    assert seen[0] is seen[1] is app.context and seen[1].debug is True
    assert App(source=TINY, open_tab="document:debug").context.debug is True


# ----------------------------------------------------------------------
# A page that raises
# ----------------------------------------------------------------------


class _Raiser:
    """
    A page whose `draw` raises partway through a frame, with ImGui's stacks left open.
    """

    fail = True
    built = 0

    def __init__(self, context: PageContext) -> None:
        type(self).built += 1
        self.frames = 0

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        if not type(self).fail:
            imgui.text_unformatted("recovered")
            return
        imgui.begin_child("##raiser-child", imgui.ImVec2(200.0, 100.0))
        imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(1.0, 0.0, 0.0, 1.0))
        imgui.push_id("left-open")
        imgui.begin_group()
        raise RuntimeError("the page fell over")


class _BadFactory:
    def __init__(self, context: PageContext) -> None:
        raise ValueError("the page could not be built")

    def draw(self) -> None:  # pragma: no cover - never built
        raise AssertionError


def _raising_app(capsys: pytest.CaptureFixture[str]) -> App:
    _Raiser.fail, _Raiser.built = True, 0
    found = Discovery(
        (
            PageSpec(name="Alpha", order=10, factory=_Recorder),
            PageSpec(name="Boom", order=20, factory=_Raiser),
            PageSpec(name="Unbuilt", order=30, factory=_BadFactory),
        )
    )
    return _fake_app(found)


def test_a_page_that_raises_is_shown_its_traceback_and_the_app_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    The exception is caught per page, ImGui's open stacks are closed, and the
    frame ends. Before this the first frame of such a page raised out of
    `App.gui` and took the app with it.
    """
    app = _raising_app(capsys)
    _frame(app)
    assert app.page_errors == {}
    app.select("Boom")
    for _ in range(3):
        assert _frame(app) > 0
    error = app.page_errors["Boom"]
    assert "RuntimeError: the page fell over" in error and "Traceback" in error
    assert "in draw" in error
    # Reported once where a terminal would show it, not once a frame.
    assert capsys.readouterr().err.count("advtext: page 'Boom' raised") == 1
    # The page is not drawn again while its error stands.
    boom = app._views["Boom"]
    assert isinstance(boom, _Raiser) and boom.frames == 1
    # The body shows the error: more than the sidebar alone draws.
    sidebar_only = _frame(_fake_app(Discovery(())))
    assert _frame(app) > sidebar_only

    # The rest of the app is as it was.
    app.select("Alpha")
    _frame(app)
    alpha = app._views["Alpha"]
    assert isinstance(alpha, _Recorder) and alpha.frames == 2
    assert list(app.page_errors) == ["Boom"]


def test_a_factory_that_raises_is_caught_the_same_way(capsys: pytest.CaptureFixture[str]) -> None:
    app = _raising_app(capsys)
    app.select("Unbuilt")
    assert _frame(app) > 0
    assert _frame(app) > 0
    assert "ValueError: the page could not be built" in app.page_errors["Unbuilt"]
    assert "Unbuilt" not in app._views


def test_retrying_a_failed_page_builds_it_again(capsys: pytest.CaptureFixture[str]) -> None:
    app = _raising_app(capsys)
    app.select("Boom")
    _frame(app)
    assert "Boom" in app.page_errors and _Raiser.built == 1
    _Raiser.fail = False
    _frame(app)
    assert "Boom" in app.page_errors, "a failed page came back without being asked to"
    app.retry("Boom")
    _frame(app)
    assert app.page_errors == {}
    assert _Raiser.built == 2, "the page object that failed was kept"
    boom = app._views["Boom"]
    assert isinstance(boom, _Raiser) and boom.frames == 1


def test_a_run_that_caught_a_page_error_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Caught for the window, not for the process: `run` raises once the window
    has closed, so a screenshot or a tour of a broken page exits non-zero with
    the page's traceback instead of photographing an error message.
    """
    from imgui_bundle import immapp

    def fake_run(params: Any, *rest: Any) -> None:
        params.callbacks.show_gui.__self__.page_errors["Boom"] = "Traceback ...\nRuntimeError: x\n"

    monkeypatch.setattr(immapp, "run", fake_run)
    with pytest.raises(app_module.PageError, match="Boom") as caught:
        app_module.run(TINY, columns_source=TINY)
    assert "RuntimeError: x" in str(caught.value)

    monkeypatch.setattr(immapp, "run", lambda params, *rest: None)
    app_module.run(TINY, columns_source=TINY)


# ----------------------------------------------------------------------
# Ink against what is behind it, on every page
# ----------------------------------------------------------------------

MINIMUM_CONTRAST = 4.5
"""
The least luminance contrast (WCAG 2 relative-luminance ratio, 1 to 21) between
a run of text and the surface behind it. 4.5 is that standard's floor for body
text. **A statement of contrast and not of looks**: it catches ink that cannot
be told from its ground -- the Stream page drew (17, 17, 17) on (14, 14, 16),
a ratio of 1.02 -- and says nothing about whether a page that passes is good.
"""


def _channels(colour: int) -> tuple[int, int, int]:
    return (colour & 0xFF, (colour >> 8) & 0xFF, (colour >> 16) & 0xFF)


def _luminance(colour: int) -> float:
    def linear(value: int) -> float:
        scaled = value / 255.0
        return scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4

    red, green, blue = _channels(colour)
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast(one: int, other: int) -> float:
    high, low = sorted((_luminance(one), _luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def frame_inks(imgui: Any) -> list[tuple[int, int | None, int]]:
    """
    Every distinct `(ink, surface behind it, glyphs)` of the frame that was just rendered.

    Read from Dear ImGui's draw data, so it sees text whoever drew it: ImGui's
    own widgets, and the imtypeset library writing into the same draw lists.
    Four consecutive vertices of one colour on two x and two y are a quad. One
    whose corners share a texture coordinate is a filled rectangle (the atlas's
    white pixel); one whose corners span two u and two v is a glyph. A glyph's
    surface is the last opaque rectangle, in draw order, that contains the
    glyph's centre; both are cut to the clip rectangle of the draw command
    they belong to, so a rectangle scrolled out of a pane is not a surface and
    a glyph outside its pane is not judged.

    Not seen: a glyph in a translucent ink, anything that is not an
    axis-aligned quad (rounded fills, lines), and what a glyph's own shape
    covers. It is the colours asked for, not pixels.

    Self-contained (it imports nothing and reads no global) because the tour
    below writes its source into the script it runs in a window.
    """
    fills: list[tuple[float, float, float, float, int]] = []
    pairs: dict[tuple[int, int | None], int] = {}
    for draw_list in imgui.get_draw_data().cmd_lists:
        vertices = draw_list.vtx_buffer
        indices = draw_list.idx_buffer
        spans = []
        for command in draw_list.cmd_buffer:
            if not command.elem_count:
                continue
            used = [
                int(indices[at])
                for at in range(command.idx_offset, command.idx_offset + command.elem_count)
            ]
            clip = command.clip_rect
            spans.append(
                (
                    command.vtx_offset + min(used),
                    command.vtx_offset + max(used),
                    (clip.x, clip.y, clip.z, clip.w),
                )
            )
        for low, high, (left, top, right, bottom) in spans:
            first = low
            while first + 3 <= high:
                quad = [vertices[first + corner] for corner in range(4)]
                colour = int(quad[0].col)
                xs = sorted({vertex.pos.x for vertex in quad})
                ys = sorted({vertex.pos.y for vertex in quad})
                if len(xs) != 2 or len(ys) != 2 or any(int(v.col) != colour for v in quad[1:]):
                    first += 1
                    continue
                first += 4
                if (colour >> 24) != 0xFF:
                    continue
                us = {vertex.uv.x for vertex in quad}
                vs = {vertex.uv.y for vertex in quad}
                if len(us) == 1 and len(vs) == 1:
                    cut = (max(xs[0], left), max(ys[0], top), min(xs[1], right), min(ys[1], bottom))
                    if cut[0] < cut[2] and cut[1] < cut[3]:
                        fills.append((*cut, colour))
                elif len(us) == 2 and len(vs) == 2:
                    x, y = (xs[0] + xs[1]) / 2.0, (ys[0] + ys[1]) / 2.0
                    if not (left <= x < right and top <= y < bottom):
                        continue
                    surface = None
                    for x0, y0, x1, y1, fill in reversed(fills):
                        if x0 <= x < x1 and y0 <= y < y1:
                            surface = fill
                            break
                    pairs[(colour, surface)] = pairs.get((colour, surface), 0) + 1
    return [(ink, surface, count) for (ink, surface), count in pairs.items()]


def _judge(name: str, found: list[tuple[int, int | None, int]]) -> None:
    """
    Every ink of a frame against `MINIMUM_CONTRAST`, with the page's name in the message.
    """
    assert found, f"{name} drew no text in a frame"
    for ink, surface, count in found:
        assert surface is not None, f"{name} drew {count} glyph(s) over no opaque surface"
        ratio = contrast(ink, surface)
        assert ratio >= MINIMUM_CONTRAST, (
            f"{name}: {count} glyph(s) in ink {_channels(ink)} on {_channels(surface)} "
            f"are a contrast of {ratio:.2f}"
        )


def _inks_headless(name: str) -> list[tuple[int, int | None, int]]:
    """
    `frame_inks` of the page's fourth frame, in a context of its own with the app's real style.

    `apply_style` because the surround a pane sits on is a style colour, and
    the default style's is another.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    before = imgui.get_current_context()
    own = imgui.create_context()
    imgui.set_current_context(own)
    try:
        app_module.apply_style()
        app = App(open_tab=name.lower())
        for _ in range(4):
            _frame(app)
        found = frame_inks(imgui)
        assert app.page_errors == {}, app.page_errors
    finally:
        imgui.destroy_context(own)
        if before is not None:
            imgui.set_current_context(before)
    return found


@pytest.mark.parametrize("name", [row[1] for row in SIDEBAR])
def test_every_page_draws_ink_that_contrasts_with_what_is_behind_it(name: str) -> None:
    """
    One headless frame of each discovered page with the app's style: every
    glyph in it is in an ink at least `MINIMUM_CONTRAST` from the opaque
    surface under the glyph's centre.

    **What this frame holds.** The pytest process has no imtypeset, so the
    page's body is its one line saying so, drawn by Dear ImGui in the style's
    text colour, beside the sidebar. That line and the chrome are what is
    judged here, on both gates. The page's own text is judged by
    `test_every_page_in_a_real_window_draws_ink_that_contrasts`, from the
    same reading of a frame of the real app with the library.

    **How this differs from the test it replaces.** That one wrapped the old
    draw backend's `draw_runs` and judged the base ink of each run it was
    handed. No page hands that backend anything now. This reads the frame's
    vertices instead, which sees every glyph in its final colour (syntax
    inks, links and marks included, which the old test did not see) and
    does not see what the old one did not either: how a pixel came out.
    """
    _judge(name, _inks_headless(name))


def test_the_reading_of_a_frame_tells_ink_from_surface_and_respects_clipping() -> None:
    """
    `frame_inks` on a frame made for it: the pairs it must find, and the two it must not.

    A light sheet with dark text on it and light text on the ground beside
    it; then, in a pane, a sheet painted under a clip rectangle that shows
    only its left end, light text over the part that is clipped away, and
    red text past the pane's right edge. With the clip rectangles ignored the
    light text is credited with a sheet that is not on screen under it and
    the red text is judged though nobody can see it: either adds a pair, and
    `.concerns/T5-APP-scripts/ablate_reading.py` is that run, red.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    before = imgui.get_current_context()
    own = imgui.create_context()
    imgui.set_current_context(own)
    dark, light, ground = 0xFF101010, 0xFFF0F0F0, 0xFF202020
    try:
        io = imgui.get_io()
        io.display_size = imgui.ImVec2(600.0, 400.0)
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
        for _ in range(2):
            io.delta_time = 1.0 / 60.0
            imgui.new_frame()
            imgui.push_style_color(imgui.Col_.window_bg, imgui.color_convert_u32_to_float4(ground))
            imgui.push_style_color(imgui.Col_.child_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.0))
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(600.0, 400.0))
            imgui.begin("##reading", None, imgui.WindowFlags_.no_title_bar.value)
            draw_list = imgui.get_window_draw_list()
            draw_list.add_rect_filled(imgui.ImVec2(20.0, 20.0), imgui.ImVec2(300.0, 60.0), light)
            draw_list.add_text(imgui.ImVec2(30.0, 30.0), dark, "on the sheet")
            draw_list.add_text(imgui.ImVec2(30.0, 80.0), light, "on the ground")
            imgui.set_cursor_screen_pos(imgui.ImVec2(20.0, 120.0))
            imgui.begin_child("##pane", imgui.ImVec2(300.0, 40.0))
            inner = imgui.get_window_draw_list()
            # A sheet of which only x < 100 is shown: past that it is no surface.
            inner.push_clip_rect(imgui.ImVec2(20.0, 120.0), imgui.ImVec2(100.0, 160.0), True)
            inner.add_rect_filled(imgui.ImVec2(20.0, 120.0), imgui.ImVec2(320.0, 160.0), light)
            inner.pop_clip_rect()
            inner.add_text(imgui.ImVec2(200.0, 130.0), light, "in the pane")
            # Text past the pane's right edge: emitted, clipped away, not judged.
            inner.add_text(imgui.ImVec2(400.0, 130.0), 0xFF0000FF, "out of the pane")
            imgui.end_child()
            imgui.end()
            imgui.pop_style_color(2)
            imgui.render()
        found = {(ink, surface) for ink, surface, _ in frame_inks(imgui)}
    finally:
        imgui.destroy_context(own)
        if before is not None:
            imgui.set_current_context(before)
    assert found == {(dark, light), (light, ground)}


def test_the_contrast_measure_is_the_standard_one() -> None:
    white, black = 0xFFFFFFFF, 0xFF000000
    assert contrast(white, black) == pytest.approx(21.0)
    assert contrast(black, black) == 1.0
    # The pair C-page-find measured on the Stream page.
    assert contrast(0xFF111111, 0xFF100E0E) == pytest.approx(1.02, abs=0.01)


# ----------------------------------------------------------------------
# Every discovered page, in a real window
# ----------------------------------------------------------------------

TOUR = """
from __future__ import annotations

import json
import sys

from imgui_bundle import hello_imgui, imgui, immapp

from advtext import typesetter
from advtext.ui import app as advtext_app
from advtext.ui.pages.typeset import NOT_DRAWING

{frame_inks}

# Each page is shown five frames. The fourth is the one that is judged. On
# the fifth the library's draw calls are answered and draw nothing, so that
# frame is everything on the page that is NOT the library's text: the
# sidebar, the controls, the captions.
FRAMES_EACH = 5
JUDGED, GROUND = 3, 4
names = list(advtext_app.page_names())
state = {{"frame": 0, "showing": None}}
report = {{"toured": [], "inks": {{}}, "ground": {{}}, "silenced": {{}}, "said": {{}},
          "ready": {{}}, "finished": []}}
real_gui = advtext_app.App.gui
real_run = immapp.run
real_wrapped = imgui.text_wrapped


def wrapped(text):
    if text.startswith(NOT_DRAWING) and state["showing"] is not None:
        report["said"].setdefault(state["showing"], text)
    real_wrapped(text)


class Silent:
    # In front of the package's ctypes library: a draw call answers "done" and draws nothing.
    def __init__(self, real, hushed):
        self._real, self._hushed = real, hushed

    def __getattr__(self, name):
        if name.startswith("ImTypeset_Draw") or name == "ImTypeset_ShowDemoSection":
            self._hushed.append(name)
            return lambda *args: 1
        return getattr(self._real, name)


def touring_gui(self):
    index = state["frame"] // FRAMES_EACH
    if index >= len(names):
        state["showing"] = None
        hello_imgui.get_runner_params().app_shall_exit = True
        return real_gui(self)
    name = names[index]
    if self.current != name:
        self.select(name)
    state["showing"] = name
    if state["frame"] % FRAMES_EACH == 0:
        # A page that plays a replay against the clock (Stream) is fed all of
        # it at once: four frames at its own rate were EIGHT glyphs of its own
        # text (measured 2026-10-11), which is no reading of the page.
        session = getattr(self.page(name), "session", None)
        if session is not None:
            session.finish()
            report["finished"].append(name)
    ground = state["frame"] % FRAMES_EACH == GROUND and typesetter.ready()
    if not ground:
        real_gui(self)
    else:
        # `_lib` is a private name of a package this tree does not own, in
        # each of its modules that draws. If it moves, nothing is hushed and
        # the test says so; it does not pass.
        hushed = []
        modules = [m for n, m in sys.modules.items()
                   if (n == "imtypeset" or n.startswith("imtypeset.")) and hasattr(m, "_lib")]
        real = [m._lib for m in modules]
        for module in modules:
            module._lib = Silent(module._lib, hushed)
        try:
            real_gui(self)
        finally:
            for module, was in zip(modules, real):
                module._lib = was
        report["silenced"][name] = sorted(set(hushed))
    if name not in report["toured"]:
        report["toured"].append(name)


def after_swap():
    # The frame is rendered and the next has not begun: its draw data stands.
    name = state["showing"]
    if name is None:
        return
    if state["frame"] % FRAMES_EACH == JUDGED:
        report["inks"][name] = frame_inks(imgui)
        report["ready"][name] = typesetter.ready()
    elif state["frame"] % FRAMES_EACH == GROUND:
        report["ground"][name] = frame_inks(imgui)
    state["frame"] += 1


def run_with_reader(params, *rest):
    params.callbacks.after_swap = after_swap
    params.fps_idling.enable_idling = False
    report["fonts_callback"] = params.callbacks.load_additional_fonts.__name__
    watched = params.callbacks.before_exit

    def before_exit():
        report["fonts"] = [font.get_debug_name() for font in imgui.get_io().fonts.fonts]
        report["own_faces"] = sorted(face.name for face in advtext_app._FACES)
        report["reason"] = typesetter.reason()
        report["trouble"] = typesetter.trouble()
        watched()

    params.callbacks.before_exit = before_exit
    return real_run(params, *rest)


imgui.text_wrapped = wrapped
immapp.run = run_with_reader
advtext_app.App.gui = touring_gui
advtext_app.run()
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def tour(window: Window) -> dict[str, Any]:
    """
    The real `run` -- real fonts, real `immapp.run`, a real GL context -- with
    `App.gui` wrapped so that each discovered page is selected in turn and
    shown for five frames before the app is asked to exit. The fourth is read
    as it is; on the fifth the library's draw calls are answered without
    drawing and the frame is read again (`ground`: the page less the
    library's text). Once for the module; what comes back is what the child
    printed.

    The child's environment is this process's: with `make test TYPESET=1` it
    has the library and the pages draw through it, without it they do not.
    The tests below say which they require.
    """
    import inspect
    import json

    script = window.out / "tour_pages.py"
    source = textwrap.dedent(TOUR).format(frame_inks=inspect.getsource(frame_inks))
    script.write_text(source, encoding="utf-8")
    done = window.run([str(script)], timeout=600.0)
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    report: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return report


def _library_asked_for() -> bool:
    import os

    from advtext import typesetter

    return bool(os.environ.get(typesetter.LIBRARY_VARIABLE))


def test_every_discovered_page_runs_in_a_real_window(tour: dict[str, Any]) -> None:
    """
    Every page's factory and `draw` survive real frames with the real atlas:
    a page that raises ends the run non-zero with its traceback, which is the
    fixture's assertion message. It says nothing about how any page looks.

    **And each page drew what the environment implies.** With the library
    asked for (`make test TYPESET=1`) it is ready on every page's last frame
    and NO page said `NOT_DRAWING`: each drew through the typeset layer, in
    an atlas that holds the library's fonts and none of the app's. Without
    it, EVERY page said `NOT_DRAWING` with the same reason, and the atlas
    holds the one UI font. Until tranche 5 a page without the library drew
    the old view instead, and this test could not tell which had drawn.
    """
    from advtext.fontmetrics import Face

    names = list(app_module.page_names())
    assert tour["toured"] == names
    assert set(tour["inks"]) == set(names) == set(tour["ground"])
    assert tour["finished"] == ["Stream"], "which pages the tour fed whole changed"
    assert tour["fonts_callback"] == "_load_fonts_for_run"
    if _library_asked_for():
        assert tour["said"] == {}, f"with the library, a page is not drawing: {tour['said']}"
        assert tour["ready"] == dict.fromkeys(names, True), (tour["reason"], tour["trouble"])
        assert tour["reason"] == "" and tour["trouble"] == ""
        assert tour["own_faces"] == []
        assert len(tour["fonts"]) == len(Face)
    else:
        assert set(tour["said"]) == set(names)
        assert len(set(tour["said"].values())) == 1, tour["said"]
        assert "IMTYPESET_LIBRARY is not set" in tour["said"][names[0]]
        assert tour["ready"] == dict.fromkeys(names, False)
        assert tour["own_faces"] == [app_module.UI_FACE]
        assert len(tour["fonts"]) == 1


OWN_TEXT_GLYPHS = 200
"""
The least glyphs of a page's OWN text (set by the library) the judged frame
must hold: three lines of prose or so. A floor and not a measurement: on
2026-10-11, on an Xvfb, the least any page had was about three times this
(`.concerns/T5-FINAL--builder--result.md` has the fourteen counts, and
`.concerns/T5-FINAL-scripts/tour_counts.py` prints them).
"""


@pytest.mark.parametrize("name", [row[1] for row in SIDEBAR])
def test_every_page_in_a_real_window_draws_ink_that_contrasts(
    name: str, tour: dict[str, Any]
) -> None:
    """
    The contrast statement, on the fourth frame of each page of the real app.

    With the library this is the page's own text as imtypeset drew it, every
    glyph in its final ink against the surface under it: the sheet, a code
    ground, a table's header, a diff row's fill. Without it, the one line
    and the chrome, as in the headless test above but with a real atlas.
    `frame_inks` says what a reading of a frame cannot see.
    """
    found = [(ink, surface, count) for ink, surface, count in tour["inks"][name]]
    _judge(name, found)
    if _library_asked_for():
        glyphs = sum(count for _, _, count in found)
        line_only = len("imtypeset is not drawing: IMTYPESET_LIBRARY is not set")
        chrome = sum(len(row[2]) for row in SIDEBAR) + 64
        assert glyphs > chrome + line_only, f"{name} drew {glyphs} glyphs: no more than the chrome"
        # B4 (T5-R #4). The bound above is met by a page's captions and
        # controls alone: it does not show that any glyph of the LIBRARY's
        # was among those judged. The fifth frame is the same page with the
        # library's draw calls answered and nothing drawn; what the judged
        # frame has more than that is the page's own text, and there must
        # be some. A page whose text was all in a translucent ink, or was
        # drawn and not read as glyphs, has none and fails here.
        silenced = tour["silenced"].get(name)
        assert silenced, f"{name}: no draw call of the library's was made on the fifth frame"
        ground = sum(count for _, _, count in tour["ground"][name])
        own = glyphs - ground
        assert own >= OWN_TEXT_GLYPHS, (
            f"{name}: {glyphs} glyphs judged, {ground} of them with the library drawing "
            f"nothing: {own} of the page's own text were judged, under {OWN_TEXT_GLYPHS}"
        )


# ----------------------------------------------------------------------
# Review 3, item 11: what else a page that raises can leave open
# ----------------------------------------------------------------------


class _LeavesOpen:
    """
    A page that raises with one more kind of thing open. `clip` is the one
    nobody had tried: a draw list's clip rectangle, pushed and never popped
    (what `DiffView` and `BareView` do around their text, in a `try`).
    """

    kind = "clip"

    def __init__(self, context: PageContext) -> None:
        self.frames = 0

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        kind = type(self).kind
        if kind == "clip":
            draw_list = imgui.get_window_draw_list()
            draw_list.push_clip_rect(imgui.ImVec2(10.0, 10.0), imgui.ImVec2(60.0, 60.0), True)
            draw_list.push_clip_rect(imgui.ImVec2(20.0, 20.0), imgui.ImVec2(40.0, 40.0), True)
        elif kind == "clip-in-child":
            imgui.begin_child("##leaves-open", imgui.ImVec2(200.0, 100.0))
            imgui.get_window_draw_list().push_clip_rect(
                imgui.ImVec2(10.0, 10.0), imgui.ImVec2(60.0, 60.0), True
            )
        elif kind == "window-clip":
            imgui.push_clip_rect(imgui.ImVec2(10.0, 10.0), imgui.ImVec2(60.0, 60.0), True)
        elif kind == "table":
            imgui.begin_table("t", 2)
            imgui.table_next_row()
            imgui.table_next_column()
        elif kind == "tab":
            imgui.begin_tab_bar("tb")
            imgui.begin_tab_item("x")
        elif kind == "tooltip":
            imgui.begin_tooltip()
        elif kind == "disabled":
            imgui.begin_disabled()
        elif kind == "window":
            imgui.begin("##a-second-window")
        raise RuntimeError(f"left open: {kind}")


@pytest.mark.parametrize(
    "kind",
    ["clip", "clip-in-child", "window-clip", "table", "tab", "tooltip", "disabled", "window"],
)
def test_a_page_that_raises_with_this_left_open_does_not_take_the_next_frames(
    kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Headless frames, counts only. The frame the page raises in ends, the
    next three end, the error page is what is drawn (its Retry button is an
    item: more vertices than the sidebar alone), and another page drawn
    afterwards draws -- so nothing the page left open is still clipping or
    disabling what comes after it.
    """
    _LeavesOpen.kind = kind
    found = Discovery(
        (
            PageSpec(name="Alpha", order=10, factory=_Recorder),
            PageSpec(name="Open", order=20, factory=_LeavesOpen),
        )
    )
    app = _fake_app(found)
    alone = _frame(app)
    app.select("Open")
    counts = [_frame(app) for _ in range(4)]
    assert f"RuntimeError: left open: {kind}" in app.page_errors["Open"]
    assert capsys.readouterr().err.count("advtext: page 'Open' raised") == 1
    page = app._views["Open"]
    assert isinstance(page, _LeavesOpen) and page.frames == 1
    sidebar_only = _frame(_fake_app(Discovery(())))
    assert min(counts) > sidebar_only, (counts, sidebar_only)
    assert counts[1] == counts[2] == counts[3]  # the error page, the same each frame
    app.select("Alpha")
    assert _frame(app) == alone  # and the page after it is drawn as it was before

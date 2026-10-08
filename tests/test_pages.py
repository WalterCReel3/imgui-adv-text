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
ORIGINAL = ("Document", "Columns", "Specimen", "Formula", "Blocks")


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


def test_the_five_original_pages_come_first_in_their_old_order() -> None:
    """
    Document, Columns, Specimen, Formula, Blocks: the tab bar's order, and still
    the head of the list however many pages are added after them, because the
    page that opens when nothing is asked for is the first one.
    """
    names = [page.name for page in pages.discover().pages]
    assert tuple(names[:5]) == ORIGINAL


SIDEBAR = (
    ("Typesetting", "Document", "Document", 10),
    ("Typesetting", "Columns", "Columns", 20),
    ("Typesetting", "Specimen", "Specimen", 30),
    ("Typesetting", "Formula", "Formula", 40),
    ("Typesetting", "Blocks", "Blocks", 50),
    ("Typesetting", "Math", "Math in text", 60),
    ("Embedding", "Themes", "Themes", 110),
    ("Embedding", "Tables", "Tables", 120),
    ("Embedding", "Find", "Find", 130),
    ("Embedding", "Inspector", "Inspector", 140),
    ("Streaming", "Stream", "Stream", 210),
    ("Streaming", "Chat", "Chat", 220),
    ("Diff", "Diff", "Diff", 310),
    ("Performance", "Stress", "Stress", 410),
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
    assert headings == ["Typesetting", "Embedding", "Streaming", "Diff", "Performance"]


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
    assert context.app is None
    assert context.debug is False
    from advtext.fontmetrics import Face

    assert context.fonts(Face.PROSE) is None
    assert context.measure is not None and context.theme is not None
    with pytest.raises(RuntimeError, match="no app"):
        context.require_app()
    assert PageContext.build(debug=True, px_per_inch=120.0).px_per_inch == 120.0


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
        app.gui()
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


@pytest.mark.parametrize("name", ORIGINAL)
def test_each_original_page_draws_frames_through_the_shell(name: str) -> None:
    """
    The five pages that used to be tabs, each shown for three frames.

    `fonts` is the app's own lookup, which answers `None` for every face here
    because no atlas was loaded; the draw goes through all the same. The page
    object comes from its module, and showing it adds vertices to a frame that
    without it holds only the sidebar.
    """
    app = App(source=TINY, columns_source=TINY, open_tab=name.lower())
    empty = _fake_app(Discovery(()))
    baseline = _frame(empty)
    counts = [_frame(app) for _ in range(3)]
    assert app.current == name
    page = app._views[name]
    assert type(page).__module__ == f"advtext.ui.pages.{name.lower()}"
    assert list(app._views) == [name]
    assert counts[-1] > baseline, f"{name} drew nothing: {counts} against {baseline}"


def test_the_debug_overlay_is_one_flag_shared_by_every_page() -> None:
    """
    `--tab columns:debug` turns the overlay on, and the Document page shows it
    too: the checkbox on each page writes `PageContext.debug`, and the Document
    page copies that into its view before drawing.
    """
    app = App(source=TINY, columns_source=TINY, open_tab="columns:debug")
    assert app.context.debug is True
    _frame(app)
    app.view.debug = False
    app.select("Document")
    _frame(app)
    assert app.view.debug is True


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


def _surface_behind(imgui: Any, x: float, y: float) -> int | None:
    """
    The colour of the last opaque rectangle drawn under a point, in this window or one above it.

    Read from ImGui's own vertex buffers at the moment text is about to be
    drawn: four consecutive vertices of one opaque colour on two x and two y
    is a filled rectangle -- a window's background, a sheet a page painted, a
    ground a pane pushed -- and the latest one containing the point is what
    the text will sit on. Windows are walked outward, child to parent.
    """
    window = imgui.internal.get_current_window()
    while window is not None:
        buffer = window.draw_list.vtx_buffer
        for first in range(buffer.size() - 4, -1, -1):
            quad = [buffer[first + corner] for corner in range(4)]
            colour = int(quad[0].col)
            if (colour >> 24) != 0xFF or any(int(vertex.col) != colour for vertex in quad):
                continue
            xs = sorted({vertex.pos.x for vertex in quad})
            ys = sorted({vertex.pos.y for vertex in quad})
            if len(xs) == 2 and len(ys) == 2 and xs[0] <= x < xs[1] and ys[0] <= y < ys[1]:
                return colour
        window = window.parent_window
    return None


def _inks_and_surfaces(name: str, monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int | None]]:
    """
    Every `(ink, surface behind it)` the page handed the backend in its fourth frame.

    In a context of its own with the app's real style (`apply_style`): the
    surround a pane sits on is a style colour, and the default style's is
    another. Every route to the backend ends in `draw_runs`, which is wrapped
    where each caller looks it up.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    import advtext.backends.imgui_draw as backend
    import advtext.ui.bare_view as bare_view
    import advtext.ui.diff_view as diff_view

    seen: list[tuple[int, int | None]] = []
    real = backend.draw_runs

    def watching(draw_list: Any, runs: Any, origin: Any, **rest: Any) -> Any:
        runs = list(runs)
        surface = _surface_behind(imgui, origin.x + 4.0, origin.y + 4.0)
        seen.extend((ink, surface) for _, ink in runs)
        return real(draw_list, runs, origin, **rest)

    for module in (backend, bare_view, diff_view):
        monkeypatch.setattr(module, "draw_runs", watching)

    before = imgui.get_current_context()
    own = imgui.create_context()
    imgui.set_current_context(own)
    try:
        app_module.apply_style()
        app = App(open_tab=name.lower())
        for _ in range(4):
            seen.clear()
            _frame(app)
        assert app.page_errors == {}, app.page_errors
    finally:
        imgui.destroy_context(own)
        if before is not None:
            imgui.set_current_context(before)
    return list(seen)


@pytest.mark.parametrize("name", [row[1] for row in SIDEBAR])
def test_every_page_draws_ink_that_contrasts_with_what_is_behind_it(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    One headless frame of each discovered page: every run of text it hands the
    backend is in an ink at least `MINIMUM_CONTRAST` from the opaque surface
    under the text's origin.

    **What it does not see.** Colour spans (syntax inks, links, find marks)
    and a diff's row inks and row fills are passed beside the runs and are
    not judged here; nor is anything ImGui draws itself. And it is the colour
    asked for, not a pixel: no glyph is rasterised in these frames.
    """
    pairs = _inks_and_surfaces(name, monkeypatch)
    assert pairs, f"{name} handed the backend no text in a frame"
    for ink, surface in pairs:
        assert surface is not None, f"{name} drew text over no opaque surface"
        ratio = contrast(ink, surface)
        assert (
            ratio >= MINIMUM_CONTRAST
        ), f"{name}: ink {_channels(ink)} on {_channels(surface)} is a contrast of {ratio:.2f}"


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
import sys

from imgui_bundle import hello_imgui, imgui

from advtext.ui import app as advtext_app

FRAMES_EACH = 4
names = list(advtext_app.page_names())
state = {"frame": 0, "shown": []}
real_gui = advtext_app.App.gui


def touring_gui(self):
    index = state["frame"] // FRAMES_EACH
    if index >= len(names):
        hello_imgui.get_runner_params().app_shall_exit = True
        return real_gui(self)
    name = names[index]
    if self.current != name:
        self.select(name)
    real_gui(self)
    if name not in state["shown"]:
        state["shown"].append(name)
    state["frame"] += 1


advtext_app.App.gui = touring_gui
advtext_app.run()
print("faces loaded:", sum(1 for font in advtext_app._FACES.values() if font is not None))
print("toured:", ",".join(state["shown"]))
"""


def test_every_discovered_page_runs_in_a_real_window(window: Window) -> None:
    """
    The real `run` -- real fonts, real `immapp.run`, a real GL context -- with
    `App.gui` wrapped so that each discovered page is selected in turn and
    shown for four frames before the app is asked to exit.

    What this establishes is that every page's factory and `draw` survive real
    frames with the real atlas: a page that raises ends the run non-zero with
    its traceback, which is the assertion's message. It says nothing about how
    any page looks.
    """
    script = window.out / "tour_pages.py"
    script.write_text(textwrap.dedent(TOUR), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    expected = ",".join(app_module.page_names())
    assert f"toured: {expected}" in done.stdout, done.stdout
    assert "faces loaded: 0" not in done.stdout, "no face reached the atlas"


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

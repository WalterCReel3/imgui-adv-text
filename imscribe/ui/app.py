r"""
The demo application: a sidebar of pages, one window, and a theme that stays out of the way.

**The pages are discovered.** The navigation is a list down the left of the
window, and what it lists is whatever `imscribe.ui.pages.discover` finds: one
module per page under `imscribe/ui/pages/`, each exposing a `PAGE`.
`imscribe.ui.pages`' docstring is the contract. What is here is the shell: the
sidebar, the request grammar (`parse_tab_request`), the chrome
(`apply_style`), the fonts and `run`. The words "tab" and `--tab` survive in
the grammar and in `TAB_NAMES` because scripts, Makefile targets and people's
fingers already use them; they mean "page".

**The app sets no text of its own.** Until 2026-10-11 `App` built a
`DocumentView`, a font specimen and a formula gallery out of imscribe's own
layout core whichever renderer drew, held the column geometry of the Columns
page, and loaded six faces into the atlas for the old ImGui draw backend.
All of that is gone from this module (`.concerns/T5-APP--builder--result.md`
lists the members and who called them). Every page draws through the typeset
layer (`imscribe.typesetter`, the imtypeset library) and keeps its own state;
when the library is not loaded a page says so in one line
(`imscribe.ui.pages.typeset.why_not`). Importing this module loads what
`imscribe.theme` loads and nothing else of the old core
(`tests/test_typeset_closure.py` holds the set).

## What a screenshot can ask for

`App.open_tab` and the grammar `parse_tab_request` implements were built when
nothing could click the navigation, and are still how `scripts/shot.py`
selects a page and its state.

## The theme

`apply_style` is the whole of it: a neutral dark chrome. It is restrained on
purpose: the text is the thing being shown, so there is no accent on anything
that is not interactive and no rounding on the sidebar's rows.

Set once from hello_imgui's `setup_imgui_style` callback rather than per
frame: `ImGuiStyle` is global mutable state that persists across frames,
unlike almost everything else in immediate mode.

## Fonts

**With the library, every font in the atlas is the library's.**
`imscribe.typesetter.load_fonts` adds one font per role (a copy of each file
with its character map rewritten for typesetting), and the app adds none of
its own: the other team's answer (f) in
`../imtypeset/docs/advtext-swap-status.md` is that a face is shared by the
host using the library's `ImFont`, found through
`imtypeset.font_atlas_index(role)`. So the UI font -- the sidebar, the
captions, every widget -- is the library's font for `UI_FACE`, and
`PageContext.fonts` answers the library's font for any role a page wants to
push. `_use_library_ui_font` makes that font ImGui's default by name
(`io.font_default`) instead of relying on it being first in the atlas.

**Without the library, one UI font**, loaded by `load_fonts` through
`imscribe.ui.fonts.load_faces`, so that the one line each page then draws can
be read. That call still reaches `imscribe.fontlib` (through
`imscribe.ui.fonts`), imported when it runs and not before;
`imscribe.typesetter.load_fonts` finds its files in `imscribe.fontfiles`
and reaches nothing of the old core.

Deliberately out of scope: docking, persistence beyond the ini file, and any
editing.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from imscribe.primitives import DEFAULT_PX_PER_INCH
from imscribe.theme import Theme
from imscribe.ui.pages import (
    DEMO_DIR,
    SHARED_OPTION,
    Discovery,
    Failure,
    PageContext,
    PageSpec,
    PageView,
    caption,
    demo_text,
    discover,
    is_count,
    split_options,
)
from imscribe.ui.palette import rgba

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

    from imscribe.primitives import Face

__all__ = [
    "DEFAULT_MARKDOWN",
    "DEMO_DIR",
    "SIDEBAR_WIDTH_PX",
    "UI_FACE",
    "UI_FONT_PX",
    "WINDOW_SIZE",
    "App",
    "Failure",
    "PageError",
    "SidebarRow",
    "TabRequest",
    "apply_style",
    "demo_text",
    "load_fonts",
    "not_drawing_at_exit",
    "page_names",
    "parse_tab_request",
    "run",
    "sidebar_rows",
]

WINDOW_TITLE = "imscribe"

SIDEBAR_WIDTH_PX: Final = 188.0
"""
The width of the navigation list, in pixels.

Fixed rather than proportional: the list is chrome, and chrome that grew with the
window would take width from the page when there is most of it to give. Wide
enough for a two-word label at the default face with the row padding
`apply_style` sets.
"""

WINDOW_SIZE: Final = (1300, 800)
"""
The window `run` opens, in pixels, and what `scripts/shot.py` photographs by default.

**1300 and not the 1100 it was, so that the page body is the width it was.** The
sidebar costs `SIDEBAR_WIDTH_PX` plus one `item_spacing.x` (12 px, `apply_style`)
between it and the body: 200 px. Under the tab bar the body was the window less
its padding, 1100 - 2 x 16 = 1068 px; at 1300 it is 1068 px again, so every page
sets the sheet it set before. The height is unchanged at 800, which makes the
body *taller* than it was by the tab bar's row, since nothing sits above a page
now.
"""


def _clip_depth(draw_list: Any) -> int | None:
    """
    How many clip rectangles are pushed on a draw list, or `None` if this
    binding does not expose the stack (`ImDrawList::_ClipRectStack`).
    """
    stack = getattr(draw_list, "_clip_rect_stack", None)
    try:
        return len(stack) if stack is not None else None
    except TypeError:
        return None


class PageError(RuntimeError):
    """
    Raised by `run` after the window has closed, if a page raised while it was open.

    The exception was caught for the window's sake (`App._draw_page`) and is
    not swallowed for the process's: a screenshot, a tour or a probe of a
    broken page exits non-zero, and the message is every failed page's
    traceback.
    """

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = dict(errors)
        names = ", ".join(self.errors)
        super().__init__(
            f"page(s) raised while drawing: {names}\n\n" + "\n".join(self.errors.values())
        )


def page_names() -> tuple[str, ...]:
    """
    The name of every discovered page, in sidebar order.

    What `--tab` accepts, case-insensitively. Read by scanning
    `imscribe.ui.pages`, so there is no list here to keep.
    """
    return tuple(page.name for page in discover().pages)


def __getattr__(name: str) -> object:
    """
    `TAB_NAMES`, computed when asked for.

    It was a literal tuple of five names, "the single copy of this list", after
    three hand-kept copies had drifted (`Makefile`, `scripts/run_demo.py`,
    `scripts/shot.py`; `tests/test_shot_all.py` has the account). The pages are
    now discovered, so the single copy is the directory listing and this is a
    view of it: `scripts/visual_diff.py` and the tests that import the name keep
    working and now see a page the day its module lands. A module attribute
    cannot be computed at import here -- the page modules import this one --
    hence the hook, and hence its absence from `__all__`, which may only name
    what the module defines statically. New code should call `page_names()`.
    """
    if name == "TAB_NAMES":
        return page_names()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Used when neither a source nor `demo/sample.md` is available. Short on purpose:
# `demo/` is not shipped inside the wheel, so this is what an installed copy of
# the package shows, and it should say what the project is rather than be long.
DEFAULT_MARKDOWN = """\
# imscribe

Markdown, streams and diffs as selectable text in a Dear ImGui pane. The text is
set by the **imtypeset** library on *TeX's model*: boxes, glue, kerns and
penalties, lines broken over badness and demerits, every glyph at a position the
typesetter worked out. `imscribe` reads the markdown, describes it to the
library, and is the view a host calls `draw()` on.

Because every glyph position is computed by the typesetter rather than inside a
widget, hit testing is arithmetic over data it already has. That is why this
text is selectable and ImGui's own is not.

- Drag to select, and drag backwards too.
- Double click for a word, triple click for a line.
- Ctrl+C copies the selection.

> Selection is the point. It is a gap in ImGui only because the widget owns the
> layout.
"""

# `DEMO_DIR` and `demo_text` live in `imscribe.ui.pages` now, where a page can
# reach them without importing this module; they are re-exported above.


# ----------------------------------------------------------------------
# What a screenshot can ask for
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TabRequest:
    """
    A page to open on the first frame, and the state to open it in.

    Every field is `None`-or-default-meaning-"leave it alone", so a request can
    name a page without disturbing the column count and vice versa.

    `options` are the words that are the named page's own (`PageSpec.options`),
    in the order given. `debug` and the integer are not among them: every page
    accepts those two and they keep the fields they always had.
    """

    tab: str | None = None
    columns: int | None = None
    debug: bool = False
    options: tuple[str, ...] = ()


def _check_tab_name(spec: str, name: str, found: Discovery) -> PageSpec | None:
    """
    The page `name` addresses, refusing a name that is no page and naming the ones that are.

    An empty name is allowed and means "leave the page alone": `parse_tab_request`
    maps it to `TabRequest(tab=None)`, and `:debug` with no name in front of it
    is a legitimate way to ask for the overlay on whatever opens.
    """
    if not name:
        return None
    page = found.find(name)
    if page is not None:
        return page
    broken = ""
    if found.failures:
        broken = (
            " (Not loaded, and so not among them: "
            + "; ".join(f"{failure.module} -- {failure.reason}" for failure in found.failures)
            + ".)"
        )
    raise ValueError(
        f"{spec!r}: {name!r} is not a tab. "
        f"The tabs are {', '.join(page.name for page in found.pages)} -- case does not "
        f"matter.{broken} "
        "Refused rather than ignored because an unmatched name opens the first "
        "page, which is a photograph of the wrong thing under a filename that "
        "claims otherwise."
    )


def parse_tab_request(spec: str | None, found: Discovery | None = None) -> TabRequest:
    """
    Parse `NAME[:OPTION[,OPTION...]]`, the grammar a screenshot addresses a page with.

    Built when nothing could click a control, so that a page whose interesting
    states are only reachable by clicking could still be photographed in them:

        document            the Document page, as it opens
        document:debug      ... with the debug overlay on
        columns:3           the Columns page, at three columns
        columns:3,debug     ... and the overlay

    An option is an integer of 1 or more (the column count; any page may read it
    through `PageContext.count_for`, and a page may cap it with
    `PageSpec.max_count`), the word `debug`, or one of the words the
    named page declares in `PageSpec.options`. Anything else raises `ValueError`
    **before the window opens**: a misspelt option that silently did nothing
    would produce a photograph of the default state under a filename claiming
    otherwise, and a wrong picture is worse than a refusal.

    **The name is held to the same standard, and it was not always.** A name
    that is not a discovered page raises here, case-insensitively as `App.gui`
    matches it. Before this, an unknown name simply never matched, ImGui opened
    the first tab, and `--tab colums` produced an image byte-identical to
    `--tab document` at exit 0 -- the exact failure the paragraph above refuses
    for options, going unrefused for the thing the option is attached to.

    `found` is a scan the caller already has; without it the pages are scanned
    here, which imports every page module.
    """
    if spec is None:
        return TabRequest()
    if found is None:
        found = discover()
    name, separator, rest = spec.partition(":")
    page = _check_tab_name(spec, name, found)
    if not separator:
        return TabRequest(tab=name or None)

    columns: int | None = None
    debug = False
    words: list[str] = []
    for option in split_options(rest) or ("",):
        if option == SHARED_OPTION:
            debug = True
        elif is_count(option):
            columns = int(option)
            if page is not None and page.max_count is not None and columns > page.max_count:
                raise ValueError(
                    f"{spec!r}: {option!r} is more than {page.name} takes, which is at most "
                    f"{page.max_count}. Refused here rather than on the first frame, where "
                    "the page would raise it from inside its draw."
                )
        elif page is not None and option in page.options:
            words.append(option)
        else:
            own = (
                f" {page.name} also takes {', '.join(repr(word) for word in page.options)}."
                if page is not None and page.options
                else ""
            )
            raise ValueError(
                f"{spec!r}: {option!r} is not a tab option. "
                "Options are 'debug' or a column count of 1 or more, "
                f"comma separated, after a colon -- for instance 'columns:3,debug'.{own}"
            )
    return TabRequest(tab=name or None, columns=columns, debug=debug, options=tuple(words))


@dataclass(frozen=True, slots=True)
class SidebarRow:
    """
    One line of the navigation list: a group heading, a page, or a module that failed.

    A value and not a draw call so the list can be checked without a frame:
    `sidebar_rows` is pure, and `App._sidebar` draws exactly what it returns.
    """

    kind: str
    """`"heading"`, `"page"` or `"failure"`."""
    text: str
    page: PageSpec | None = None
    detail: str = ""


def sidebar_rows(found: Discovery) -> tuple[SidebarRow, ...]:
    """
    The navigation list for a scan, top to bottom.

    Pages are in `Discovery.pages`' order, which is `(order, name)`. A heading
    is emitted whenever the group changes from one page to the next, so pages
    of one group that are not adjacent in that order get the heading twice --
    which is visible, and is how a page whose `order` strays into another
    group's range gets noticed. Modules that could not be loaded come last,
    under their own heading, with the reason as the row's detail.
    """
    rows: list[SidebarRow] = []
    group: str | None = None
    for page in found.pages:
        if page.group != group:
            group = page.group
            if group:
                rows.append(SidebarRow("heading", group))
        rows.append(SidebarRow("page", page.label, page, page.caption))
    if found.failures:
        rows.append(SidebarRow("heading", "failed to load"))
        for failure in found.failures:
            rows.append(
                SidebarRow("failure", failure.module.rpartition(".")[2], None, failure.reason)
            )
    return tuple(rows)


@dataclass(slots=True)
class App:
    """
    The shell: what the sidebar lists, which page is showing, and what a page is built from.

    `discovery` is what the sidebar lists, `current` the page that is
    showing, `context` what every page is built from, and the page objects
    themselves are built on first showing and kept. A page keeps its state on
    its own object. What the launch named is handed to the pages through
    `context`: the two markdown sources, and the integer and the option words
    of `--tab` (`PageContext.count_for`, `options_for`). The Columns page's
    count was a field here; it is that page's own now.
    """

    theme: Theme = field(default_factory=Theme.build)
    px_per_inch: float = DEFAULT_PX_PER_INCH
    source: str = DEFAULT_MARKDOWN
    columns_source: str | None = None
    """
    The markdown the Columns page flows, or `None` to flow `source`.

    A second document because the two pages want different prose: columns
    need sustained paragraphs. `run` fills this from `demo/columns.md`.
    """
    open_tab: str | None = None
    """
    A page to select on the first frame, in `parse_tab_request`'s grammar.

    Exists so a screenshot can name the page it wants, and the state it wants
    it in, without clicking for either. After construction it holds the bare
    name; the first frame moves it into `current` and clears it.
    """
    discovery: Discovery = field(init=False)
    """
    What `imscribe.ui.pages.discover` found when this app was built. Scanned
    once: the sidebar is drawn from it every frame.
    """
    context: PageContext = field(init=False)
    current: str | None = field(default=None, init=False)
    """
    The name of the page that is showing; the first in sidebar order until
    `open_tab` or a click says otherwise. `None` only if no page was found.
    """
    page_errors: dict[str, str] = field(default_factory=dict, init=False)
    """
    The traceback of each page whose factory or `draw` raised, by page name.

    A page in here is not built or drawn; its body shows the traceback and a
    button that calls `retry`. Empty in a healthy app, which is what a test
    or `run` checks.
    """
    _views: dict[str, PageView] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.discovery = discover()
        request = parse_tab_request(self.open_tab, self.discovery)
        self.open_tab = request.tab
        self.context = PageContext(
            theme=self.theme,
            px_per_inch=self.px_per_inch,
            fonts=_face_font,
            debug=request.debug,
            request_page=request.tab,
            request_options=request.options,
            request_count=request.columns,
            source=self.source,
            columns_source=self.columns_source,
        )
        if self.discovery.pages:
            self.current = self.discovery.pages[0].name

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def page(self, name: str) -> PageView:
        """
        The page object for `name` (any case), built on first request and kept.

        Lazy because a factory may parse a document or lay one out, and a demo
        with a dozen pages should not pay for eleven it has not shown. Kept for
        the app's lifetime, which is what makes the object a place for a page
        to hold its state.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        made = self._views.get(spec.name)
        if made is None:
            made = self._views[spec.name] = spec.factory(self.context)
        return made

    def select(self, name: str) -> None:
        """
        Show page `name` (any case) from the next `gui` on. `KeyError` if it is no page.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        self.current = spec.name

    def retry(self, name: str) -> None:
        """
        Forget that page `name` failed, and the page object that did: the next frame builds it anew.

        The object is dropped because an exception partway through a `draw`
        or a constructor leaves no promise about its state.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        self.page_errors.pop(spec.name, None)
        self._views.pop(spec.name, None)

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    def gui(self) -> None:
        """
        One frame: the navigation list, and beside it whichever page is showing.

        The list is a child window of fixed width; the page is drawn after a
        `same_line`, inside a group and **not** inside a second child. A group
        only moves the left edge: the page's own header row is still drawn on
        the window's background and its own scrolling child is still a direct
        child of the window, exactly as under the tab bar, which is what keeps
        the five original pages' pixels where they were. A wrapping child would
        have put the header on the darker child background and nested every
        page's scroll one level down.

        `open_tab` selects a page once, on the first frame, and is then cleared;
        held, it would re-select every frame and the list could never be
        clicked away from.

        **An exception out of a page's factory or its `draw` is caught, per
        page** (`_draw_page`): the body shows the traceback, the list still
        works, and every other page is as it was. It used to end the app. The
        reason given then -- a screenshot run must not photograph a blank
        body -- is kept another way: `run` raises `PageError` once the window
        has closed if anything is in `page_errors`, so `scripts/shot.py` and
        the window tests still fail, with the page's own traceback.
        """
        from imgui_bundle import imgui

        if self.open_tab is not None:
            self.select(self.open_tab)
            self.open_tab = None
        self._sidebar()
        imgui.same_line()
        imgui.begin_group()
        if self.current is None:
            caption("no pages were found in imscribe.ui.pages")
        else:
            self._draw_page(self.current)
        imgui.end_group()

    def _draw_page(self, name: str) -> None:
        """
        Build and draw page `name`, or show why it could not be.

        **ImGui's stacks are put back after an exception.** A `draw` that
        raises between a `begin_child` and its `end_child` (or a push and its
        pop) leaves the frame unbalanced, and ImGui then asserts at the
        window's `End` -- through imgui-bundle, a second exception, out of
        the frame. So the state is stored before the page runs
        (`error_recovery_store_state`) and restored if it raises, with
        ImGui's own reporting of what it had to close switched off for the
        length of that call: the traceback is the report. Measured in
        headless frames with a child, a style colour, an id and a group left
        open (`tests/test_pages.py`), and with a table, a tab bar, a tooltip,
        a disabled block and a second window.

        **A clip rectangle left pushed on this window's draw list is popped
        here**, because ImGui's recovery does not do it (review 3, item 11,
        measured: no assertion and no exception, on that frame or the next
        -- but everything drawn in the window after the page on the frame it
        raised, the traceback included, was clipped to the rectangle the
        page left: 58 vertices where the frames after it had 1,338). The
        depth is read from the draw list's own stack (`_clip_depth`); where
        a binding does not show it, nothing is popped and that one frame is
        clipped as before.

        `Exception` and not `BaseException`: Ctrl+C and `SystemExit` still
        end the app. The traceback goes to stderr once, when it happens.
        """
        from imgui_bundle import imgui

        error = self.page_errors.get(name)
        if error is None:
            state = imgui.internal.ErrorRecoveryState()
            imgui.internal.error_recovery_store_state(state)
            draw_list = imgui.get_window_draw_list()
            clips = _clip_depth(draw_list)
            try:
                self.page(name).draw()
            except Exception:
                error = self.page_errors[name] = traceback.format_exc()
                print(f"imscribe: page {name!r} raised:\n{error}", file=sys.stderr)
                io = imgui.get_io()
                reporting = (
                    io.config_error_recovery_enable_assert,
                    io.config_error_recovery_enable_debug_log,
                    io.config_error_recovery_enable_tooltip,
                )
                io.config_error_recovery_enable_assert = False
                io.config_error_recovery_enable_debug_log = False
                io.config_error_recovery_enable_tooltip = False
                try:
                    imgui.internal.error_recovery_try_to_recover_state(state)
                finally:
                    (
                        io.config_error_recovery_enable_assert,
                        io.config_error_recovery_enable_debug_log,
                        io.config_error_recovery_enable_tooltip,
                    ) = reporting
                # The one stack ImGui's recovery does not look at: this
                # window's clip rectangles. `imgui.pop_clip_rect` and not the
                # draw list's own: it also puts the window's clip rectangle
                # back, which is what items and text are culled against, and
                # which `imgui.push_clip_rect` (as against the draw list's)
                # had changed.
                while clips is not None and (_clip_depth(draw_list) or 0) > clips:
                    imgui.pop_clip_rect()
        if error is not None:
            caption(f"{name} raised an exception and is not being drawn")
            imgui.same_line()
            if imgui.small_button(f"Retry##imscribe-page-retry-{name}"):
                self.retry(name)
            imgui.begin_child(f"##imscribe-page-error-{name}")
            imgui.text_unformatted(error)
            imgui.end_child()

    def _sidebar(self) -> None:
        """
        Draw `sidebar_rows` and take a click on one of them.

        The child's background is pushed to transparent, so the list sits on
        the window's own colour: `child_bg` is the dark surround a page sheet
        lies on, and the list is chrome, not a surround.
        """
        from imgui_bundle import imgui

        imgui.push_style_color(imgui.Col_.child_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.0))
        visible = imgui.begin_child("##imscribe-sidebar", imgui.ImVec2(SIDEBAR_WIDTH_PX, 0.0))
        imgui.pop_style_color()
        if visible:
            for index, row in enumerate(sidebar_rows(self.discovery)):
                if row.kind == "heading":
                    if index:
                        imgui.spacing()
                    caption(row.text.upper())
                elif row.page is not None:
                    label = f"{row.text}##imscribe-page-{row.page.name}"
                    if imgui.selectable(label, row.page.name == self.current)[0]:
                        self.current = row.page.name
                    if row.detail:
                        imgui.set_item_tooltip(row.detail)
                else:
                    imgui.text_colored(imgui.ImVec4(0.9, 0.6, 0.2, 1.0), row.text)
                    imgui.set_item_tooltip(row.detail)
        imgui.end_child()


# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------


def _vec4(colour: int, alpha: float = 1.0) -> imgui.ImVec4:
    """
    One of this module's packed `IM_COL32` colours as ImGui's float vector.

    `rgba` packs alpha, blue, green, red with the low byte first -- the byte order
    is `IM_COL32`'s and is not RGBA despite the name -- so the shifts here are
    that order read back. Taking the colours from one place and converting is what
    keeps the chrome and the page from drifting apart.
    """
    from imgui_bundle import imgui

    return imgui.ImVec4(
        (colour & 0xFF) / 255.0,
        ((colour >> 8) & 0xFF) / 255.0,
        ((colour >> 16) & 0xFF) / 255.0,
        alpha,
    )


# The chrome. Neutral greys with one desaturated accent, because the page is the
# only saturated thing on screen and anything else competing with it is a
# regression. `SURROUND` is darker than `CHROME` so the sheet sits on the darkest
# surface in the window and reads as lit.
CHROME = rgba(0x1A, 0x1A, 0x1D)
SURROUND = rgba(0x0E, 0x0E, 0x10)
RAISED = rgba(0x26, 0x26, 0x2B)
HOVER = rgba(0x32, 0x32, 0x38)
LINE = rgba(0x38, 0x38, 0x3F)
LABEL = rgba(0xE4, 0xE4, 0xE6)
MUTED = rgba(0x8C, 0x8C, 0x96)
ACCENT = rgba(0x9F, 0xB4, 0xCC)


def apply_style() -> None:
    """
    Push the demo's chrome into `ImGuiStyle`. Needs a live context.

    A hello_imgui `setup_imgui_style` callback rather than something `run` calls
    directly, and set once rather than per frame: `ImGuiStyle` is global mutable
    state that persists across frames, unlike almost everything else in immediate
    mode, and a per-frame push would be a pair of calls to keep balanced for no
    gain.

    Restrained deliberately. Square corners everywhere the eye might otherwise
    read a widget as a card, no borders except the hairline under a tab bar, and
    the accent only on things that respond to a mouse. `docs/imgui-risks.md`'s
    argument that the text is what is being demonstrated applies to the chrome
    too: the most useful thing this function does is stop the default theme's blue
    from being the brightest object in a photograph of a page of type.

    The shell has no tab bar any more -- its navigation is a list of
    selectables, coloured by the three `header` entries below -- but the tab
    colours are kept for a page that wants tabs of its own inside its body.
    """
    from imgui_bundle import imgui

    style = imgui.get_style()
    style.window_rounding = 0.0
    style.child_rounding = 0.0
    style.frame_rounding = 3.0
    style.grab_rounding = 3.0
    style.tab_rounding = 0.0
    style.scrollbar_rounding = 0.0
    style.window_border_size = 0.0
    style.child_border_size = 0.0
    style.frame_border_size = 0.0
    style.tab_bar_border_size = 1.0
    style.tab_bar_overline_size = 2.0
    style.window_padding = imgui.ImVec2(16, 12)
    style.frame_padding = imgui.ImVec2(10, 6)
    style.item_spacing = imgui.ImVec2(12, 8)
    style.scrollbar_size = 12.0
    style.grab_min_size = 10.0

    colour = imgui.Col_
    put = style.set_color_
    put(colour.text, _vec4(LABEL))
    put(colour.text_disabled, _vec4(MUTED))
    put(colour.window_bg, _vec4(CHROME))
    # The scrolling children are the surround the page sits on, so they are the
    # darkest surface here and not a lighter "panel" -- see `Palette`, which makes
    # the same argument from the other side.
    put(colour.child_bg, _vec4(SURROUND))
    put(colour.popup_bg, _vec4(RAISED))
    put(colour.border, _vec4(LINE))
    put(colour.border_shadow, imgui.ImVec4(0, 0, 0, 0))
    put(colour.frame_bg, _vec4(RAISED))
    put(colour.frame_bg_hovered, _vec4(HOVER))
    put(colour.frame_bg_active, _vec4(HOVER))
    put(colour.check_mark, _vec4(ACCENT))
    put(colour.button, _vec4(RAISED))
    put(colour.button_hovered, _vec4(HOVER))
    put(colour.button_active, _vec4(ACCENT, 0.45))
    put(colour.header, _vec4(RAISED))
    put(colour.header_hovered, _vec4(HOVER))
    put(colour.header_active, _vec4(HOVER))
    put(colour.separator, _vec4(LINE))
    put(colour.scrollbar_bg, _vec4(SURROUND))
    put(colour.scrollbar_grab, _vec4(RAISED))
    put(colour.scrollbar_grab_hovered, _vec4(HOVER))
    put(colour.scrollbar_grab_active, _vec4(ACCENT, 0.6))
    put(colour.tab, _vec4(CHROME))
    put(colour.tab_hovered, _vec4(HOVER))
    put(colour.tab_selected, _vec4(RAISED))
    put(colour.tab_selected_overline, _vec4(ACCENT))
    put(colour.tab_dimmed, _vec4(CHROME))
    put(colour.tab_dimmed_selected, _vec4(RAISED))
    put(colour.tab_dimmed_selected_overline, _vec4(ACCENT, 0.4))


# ----------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------

UI_FACE: Final = "PROSE"
"""
The role whose font the app's own text is drawn in, by the name of its `Face` member.

The running-text face. It is the file the app's UI font was before the
library's fonts were shared (`Roboto-Regular`, as `imscribe.fontlib` resolves
`Face.PROSE`), so the chrome is set in the same file with and without the
library. By name, as `imscribe.description.FACE_ROLES` keys its roles, so
this module does not import the enum to say it.
"""

UI_FONT_PX: Final = 16.0
"""
The pixel height the app's own text is drawn at, with the library and without.

Without the library it is the size `load_fonts` loads the one font at
(`imscribe.ui.fonts.DEFAULT_LOAD_PX`, the same number;
`tests/test_app_typeset.py` holds them equal). With it, the library's fonts
carry no size of their own, and Dear ImGui's `style.font_size_base` would
stay at its default of 20 (measured in the window, 2026-10-11), so
`_use_library_ui_font` sets it to this.
"""

_FACES: dict[Face, imgui.ImFont | None] = {}
"""
The fonts the app itself put in the atlas: `UI_FACE`'s when the library is not
drawing, and nothing when it is.
"""


def load_fonts() -> None:
    """
    Put the one UI font in the atlas: `UI_FACE`, from the path `imscribe.fontlib` resolves.

    What `run` loads when the library is not drawing, so that the sidebar and
    the one line each page then draws can be read. A thin caller of
    `imscribe.ui.fonts.load_faces`; it never asks for the library, because it
    is a public name that a test calls in the pytest process
    (`tests/test_fonts_setup.py`).

    Until 2026-10-11 this loaded every face, mathematics included, for the
    old ImGui draw backend. No page draws through that backend any more.

    A face that fails to load is left absent rather than fatal: ImGui then
    draws in its built-in font.

    **The dict is cleared first.** It is a module global, and a second `run`
    in one process would otherwise keep an `ImFont` belonging to the atlas
    the first run destroyed.
    """
    from imgui_bundle import hello_imgui

    from imscribe.primitives import Face
    from imscribe.ui.fonts import load_faces

    _FACES.clear()
    params = hello_imgui.FontLoadingParams()
    # The file lives in the imgui-bundle wheel, not in an assets folder of ours,
    # so it is loaded by absolute path rather than through the asset system.
    params.inside_assets = False
    loaded = load_faces(
        (Face[UI_FACE],),
        loader=lambda path: hello_imgui.load_font(str(path), UI_FONT_PX, params),
    )
    _FACES.update(loaded.fonts)


def _library_font(role_name: str) -> imgui.ImFont | None:
    """
    The library's `ImFont` for a role (by `Face` member name), or `None`.

    `imtypeset.font_atlas_index` is asked every time: its answer moves when a
    font is added to or removed from the atlas. `None` when the library is
    not ready, when the role has no font, and when the index is not in the
    atlas this binding shows.
    """
    from imscribe import typesetter

    if not typesetter.ready():
        return None
    from imgui_bundle import imgui

    from imscribe.description import FACE_ROLES

    index = typesetter.module().font_atlas_index(FACE_ROLES[role_name])
    if index is None:
        return None
    fonts = imgui.get_io().fonts.fonts
    return fonts[index] if 0 <= index < len(fonts) else None


def _use_library_ui_font() -> bool:
    """
    Make the library's font for `UI_FACE` Dear ImGui's default. False if there is none.

    Set by name (`io.font_default`) and not left to the order the library
    adds its roles in: `Fonts[0]` is whichever font was added first, and
    that is the library's business. The size is `UI_FONT_PX`, which says why.
    """
    from imgui_bundle import imgui

    font = _library_font(UI_FACE)
    if font is None:
        return False
    imgui.get_io().font_default = font
    imgui.get_style().font_size_base = UI_FONT_PX
    return True


def _use_own_ui_font() -> bool:
    """
    Make the font `load_fonts` loaded Dear ImGui's default, at `UI_FONT_PX`. False if it is absent.

    Needed only when something else is in the atlas before it; see
    `_load_fonts_for_run`. With the app's font alone in the atlas it is
    `Fonts[0]` and the default without being named.
    """
    from imgui_bundle import imgui

    font = next((font for face, font in _FACES.items() if face.name == UI_FACE), None)
    if font is None:
        return False
    imgui.get_io().font_default = font
    imgui.get_style().font_size_base = UI_FONT_PX
    return True


def _load_fonts_for_run() -> None:
    """
    `run`'s font callback: the library's fonts and none of the app's, or one UI font without it.

    When `imscribe.typesetter.module()` answers the library, its fonts are
    loaded (`typesetter.load_fonts`, which destroys a context left from an
    earlier Dear ImGui context first) and the role `UI_FACE` becomes the
    default font; the app adds no copy of any face. When there is no library
    -- no `IMTYPESET_LIBRARY`, or it refused -- or its fonts did not load,
    this is `load_fonts`: one font. A failure in the library does not raise:
    `typesetter.reason()` keeps the sentence and each page shows it. Fonts
    that loaded with none for `UI_FACE` among them are a third case with no
    refusal behind it; it is recorded with `typesetter.note`, which is what
    the pages then show (`imscribe.ui.pages.typeset.why_not`).

    After a failed load the library's context is destroyed
    (`typesetter.unload`) and the app's font is loaded and then NAMED the
    default (`_use_own_ui_font`). Named, because the fonts the library added
    before it failed are still in the atlas afterwards: measured in the
    window on 2026-10-11 with a load that was made to report failure, seven
    of the library's fonts and then the app's one, `Fonts[0]` the library's,
    and the chrome drawn in it at Dear ImGui's default 20 px until this
    function said otherwise.

    **Not inside `load_fonts`**, which a test calls in the pytest process:
    there, with the variable set, it would import the library into that
    process and give it a context on whatever Dear ImGui context another
    test left current.
    """
    from imscribe import typesetter

    _FACES.clear()
    if typesetter.module() is None:
        load_fonts()
        return
    loaded = typesetter.load_fonts()
    if loaded and _use_library_ui_font():
        return
    typesetter.unload()
    if loaded:
        # The fonts DID load, and none of them is the one the app draws its
        # own text in. Said, because after the unload nothing else says it:
        # `reason()` is empty (the library was never refused) and each page
        # would fall back on "load_fonts() has not succeeded", of a call that
        # returned True.
        typesetter.note(
            f"the library loaded its fonts but has none for the role {UI_FACE}, which "
            "the app draws its own text in, so the app unloaded the library"
        )
    load_fonts()
    _use_own_ui_font()


def _unload_typesetter() -> None:
    """
    `run`'s `before_exit`: imtypeset's context goes before the Dear ImGui context does.

    Its fonts are in that context's atlas (`imscribe.typesetter.load_fonts`
    says whose job this is). Does nothing when the library is not in use.
    """
    from imscribe import typesetter
    from imscribe.ui.pages.typeset import why_not

    global _NOT_DRAWING_AT_EXIT
    # Before the unload: afterwards `ready()` is false for a library that
    # drew to the last frame as for one that never drew.
    _NOT_DRAWING_AT_EXIT = why_not()
    typesetter.unload()


_NOT_DRAWING_AT_EXIT = ""


def not_drawing_at_exit() -> str:
    """
    Why the library was not drawing when the last `run`'s window closed; empty if it was.

    The sentence every page was showing in place of its content
    (`imscribe.ui.pages.typeset.why_not`), read in `before_exit` before the
    library is unloaded. Empty while a run is going and before any has
    ended. With no `IMTYPESET_LIBRARY` it says that the variable is not set,
    which is no failure: whether the library was ASKED FOR is the caller's to
    read from the environment, as `scripts/shot.py` and `scripts/run_demo.py`
    do. A page that never drew is covered as one that did: the state is the
    process's (`typesetter.disable` is for the whole run), not a page's.
    """
    return _NOT_DRAWING_AT_EXIT


def _face_font(face: Face) -> imgui.ImFont | None:
    """
    The `ImFont` for a role, or `None`: `PageContext.fonts`.

    The app's own font when it loaded one for the role (without the
    library, `UI_FACE` only); otherwise the library's font for the role.
    """
    own = _FACES.get(face)
    if own is not None:
        return own
    return _library_font(face.name)


# ----------------------------------------------------------------------


def run(
    source: str | None = None,
    *,
    ini_folder: str | None = None,
    tab: str | None = None,
    columns_source: str | None = None,
) -> None:
    """
    Open the demo window. Needs a display.

    On this machine's `DISPLAY=:1` a window opens in about 0.4 s. Whether that
    display is reachable is a fact about the session and not about this
    function: from the sandbox of 2026-10-06 it was not, and the window was
    opened on an Xvfb in a user namespace instead (`scripts/mouse_probe.py`,
    `xvfb_command`). Without a reachable display this does not hang: GLFW
    aborts in about 0.6 s with
    `IM_ASSERT( glfwInitSuccess )`, and `scripts/run_demo.py` turns that into
    something readable. `make shot` photographs any page without a terminal
    attached to a display, and `make shot-headless` is the Xvfb fallback for a
    machine that has none.

    `source` and `columns_source` both default to the files in `demo/`, falling
    back to `DEFAULT_MARKDOWN` when this is not a checkout -- `demo/` is not
    inside the package and is absent from an installed wheel.

    `tab` selects a page on the first frame in `parse_tab_request`'s grammar, which
    is how a screenshot reaches a state without clicking for it. (This used to
    say "a state no click in this environment can produce";
    `scripts/mouse_probe.py` posts clicks into this app now, though it does not
    click the navigation list.)

    `ini_folder_type` is set to the app's own user-config folder rather than the
    default current folder, so running this does not scatter `.ini` files across
    whatever directory it was launched from. pptmstr's app does this and its
    verify scripts do not, which is why that tree has stray ini files in it.
    """
    from imgui_bundle import hello_imgui, immapp

    global _NOT_DRAWING_AT_EXIT
    _NOT_DRAWING_AT_EXIT = ""
    app = App(
        source=source or demo_text("sample.md") or DEFAULT_MARKDOWN,
        columns_source=columns_source or demo_text("columns.md"),
        open_tab=tab,
    )

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = WINDOW_SIZE
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.provide_full_screen_window
    )
    params.ini_folder_type = hello_imgui.IniFolderType.app_user_config_folder
    if ini_folder is not None:
        params.ini_folder_type = hello_imgui.IniFolderType.absolute_path
        params.ini_filename = str(Path(ini_folder) / "imscribe.ini")
    params.callbacks.load_additional_fonts = _load_fonts_for_run
    params.callbacks.before_exit = _unload_typesetter
    params.callbacks.setup_imgui_style = apply_style
    params.callbacks.show_gui = app.gui
    immapp.run(params)
    if app.page_errors:
        raise PageError(app.page_errors)

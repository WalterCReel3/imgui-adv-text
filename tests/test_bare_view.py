r"""
`BareView`: the embeddable view, in real ImGui frames with no display.

`advtext.ui.bare_view.BareView` makes promises a pure test cannot reach, because
they are about what ImGui does with the items the view submits: that over the
text there is *no* item for a host's hover and context menus to be blocked by,
that a left press nevertheless begins a selection, and that the press does not
also drag the host's window. So almost everything here runs frames, in the idiom
`tests/test_document_view.py` established: a window needs a display and a frame
does not; mouse events queued before `new_frame` are delivered; `begin`,
`begin_child`, `is_item_hovered` and popups all answer from them.

`fonts=lambda face: None` throughout, so the process-global font atlas is never
touched. Glyphs are then counted as `missing` rather than drawn, which is
enough: these tests are about geometry, items and selection, and
`tests/test_imgui_draw.py` is where glyphs are drawn.

**What these frames are not.** No pixels, no swap chain, no window manager, no
real pointer. `scripts/mouse_probe.py` drives the same shared mouse code in a
real window through `DocumentView`. `BareView.draw` itself was driven in a real
window once, by a throwaway script under Xvfb, and the module docstring of
`advtext.ui.bare_view` records what that run read back; no test here repeats it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import advtext.ui.bare_view as bare_module
from advtext.backends.imgui_draw import DARK_PALETTE, Palette
from advtext.markdown import CodeBlock, TextBlock, build_document
from advtext.selection import Selection
from advtext.shipout import Glyph, Point
from advtext.spans import ColourSpan, code_position, find_spans
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView, Pointed, block_kind
from advtext.ui.document_view import DocumentView
from advtext.units import px_from_sp, sp_from_px

SOURCE = (
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky "
    "xray yankee zulu.\n"
    "\n"
    "```\nfenced code\n```\n"
    "\n"
    "Second paragraph, below the code, with different words in it entirely.\n"
)
"""
A paragraph of distinct words, a code block, a second paragraph.

Distinct words so that a selection says where it started; three blocks so that
"which block is under the mouse" has more than one answer.
"""

ROOT = Path(__file__).resolve().parent.parent

WINDOW = (40.0, 30.0)
"""
Where the test window starts. Not the origin, so a window that moved is visible.
"""


class Seen:
    """
    What one frame observed, read straight after `BareView.draw` returned.
    """

    cursor: Any = None
    after: Any = None
    available: float = 0.0
    item_hovered: bool = False
    any_hovered: bool = False
    any_active: bool = False
    window_pos: tuple[float, float] = (0.0, 0.0)
    context_item: bool = False
    context_window: bool = False
    host_clicked: bool = False
    vertices: int = 0
    glyphs: int = 0
    rules: int = 0
    colours: list[int] = []
    cursor_kind: Any = None
    scroll_y: float = 0.0
    scroll_max: float = 0.0


def frame(
    *views: BareView,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    right: bool | None = None,
    before: Callable[[Any, Seen], None] | None = None,
    after: Callable[[Any, Seen], None] | None = None,
    menu: str = "",
    child_width: float = 0.0,
    width_px: float | None = None,
    palette: Any = None,
    ctrl_c: bool | None = None,
    wheel: float | None = None,
    skip_draw: bool = False,
    focus: bool | None = None,
) -> Seen:
    """
    One frame: a movable window, a child, each view drawn in turn, and what was seen.

    The window is placed once (`first_use_ever`), so a drag that ImGui took for
    a window move really moves it and `Seen.window_pos` shows that. `before`
    and `after` run inside the child either side of the views, which is where
    a host's own widgets would be submitted. `menu` is which context menu the
    host offers: `"item"` for one attached to the view's rectangle, `"window"`
    for the window's own, asked not to open over an item. One at a time,
    because two popups opened by one click replace each other.
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
    if left is not None:
        io.add_mouse_button_event(0, left)
    if right is not None:
        io.add_mouse_button_event(1, right)
    if ctrl_c is not None:
        io.add_key_event(imgui.Key.mod_ctrl, ctrl_c)
        io.add_key_event(imgui.Key.c, ctrl_c)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    if focus is not None:
        io.add_focus_event(focus)

    seen = Seen()
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(*WINDOW), imgui.Cond_.first_use_ever.value)
        imgui.set_next_window_size(imgui.ImVec2(900.0, 700.0), imgui.Cond_.first_use_ever.value)
        imgui.begin("##advtext-bare-test")
        position = imgui.get_window_pos()
        seen.window_pos = (float(position.x), float(position.y))
        imgui.begin_child("##advtext-bare-child", imgui.ImVec2(child_width, 0.0))
        if before is not None:
            before(imgui, seen)
        seen.cursor = imgui.get_cursor_screen_pos()
        seen.available = float(imgui.get_content_region_avail().x)
        start = imgui.get_window_draw_list().vtx_buffer.size()
        seen.scroll_y = float(imgui.get_scroll_y())
        seen.scroll_max = float(imgui.get_scroll_max_y())
        for view in () if skip_draw else views:
            stats = view.draw(fonts=lambda face: None, width_px=width_px, palette=palette)
            seen.glyphs += stats.glyphs
            seen.rules += stats.rules
        buffer = imgui.get_window_draw_list().vtx_buffer
        seen.vertices = buffer.size() - start
        seen.colours = [int(buffer[index].col) for index in range(start, buffer.size(), 4)]
        seen.item_hovered = bool(imgui.is_item_hovered())
        seen.cursor_kind = imgui.get_mouse_cursor()
        seen.any_hovered = bool(imgui.internal.get_hovered_id() != 0)
        seen.any_active = bool(imgui.is_any_item_active())
        seen.after = imgui.get_cursor_screen_pos()
        if menu == "item" and imgui.begin_popup_context_item("##host-item-menu"):
            seen.context_item = True
            imgui.end_popup()
        over_nothing = (
            imgui.PopupFlags_.mouse_button_right.value | imgui.PopupFlags_.no_open_over_items.value
        )
        if menu == "window" and imgui.begin_popup_context_window(
            "##host-window-menu", over_nothing
        ):
            seen.context_window = True
            imgui.end_popup()
        if after is not None:
            after(imgui, seen)
        imgui.end_child()
        imgui.end()
    finally:
        imgui.render()
    return seen


def close_popups() -> None:
    """
    A frame that dismisses any popup a test opened, so the next test starts clean.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    io = imgui.get_io()
    io.add_mouse_button_event(0, False)
    io.add_mouse_button_event(1, False)
    imgui.new_frame()
    imgui.close_current_popup()
    try:
        imgui.begin("##advtext-bare-test")
        imgui.set_window_pos(imgui.ImVec2(*WINDOW))
        if imgui.begin_popup("##host-item-menu"):
            imgui.close_current_popup()
            imgui.end_popup()
        if imgui.begin_popup("##host-window-menu"):
            imgui.close_current_popup()
            imgui.end_popup()
        imgui.end()
    finally:
        imgui.render()


@pytest.fixture
def view(bundled_fonts: Any) -> BareView:
    theme = Theme.build()
    made = BareView(
        document=build_document(SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    # Two settling frames with the mouse parked off the window: the first sizes
    # the child, and hover needs a position that was current at submission.
    frame(made, mouse=(1190.0, 790.0), left=False, right=False)
    frame(made, mouse=(1190.0, 790.0))
    yield made
    close_popups()


def over_text(view: BareView, dx: float = 2.0, dy: float = 6.0) -> tuple[float, float]:
    """
    A screen position `dx`, `dy` pixels into the document as it was last drawn.
    """
    assert view.origin is not None
    return (view.origin[0] + dx, view.origin[1] + dy)


# -- the pane ---------------------------------------------------------------


def test_the_measure_is_the_pane_and_not_a_page(view: BareView) -> None:
    seen = frame(view)
    layout = view.layout
    assert layout is not None
    # The whole content region, where `DocumentView` would cap it at 2.25
    # alphabets and centre a sheet.
    assert layout.width == sp_from_px(seen.available)
    assert seen.available > 700.0
    assert view.origin == (float(seen.cursor.x), float(seen.cursor.y))

    page = DocumentView(document=view.document, theme=view.theme, measure=view.measure)
    assert page.page(sp_from_px(seen.available)).measure < layout.width


def test_a_narrower_pane_is_a_narrower_measure_and_a_floor_stops_it_at_zero(
    view: BareView,
) -> None:
    wide = view.layout
    seen = frame(view, child_width=300.0)
    narrow = view.layout
    assert wide is not None and narrow is not None
    assert narrow.width == sp_from_px(seen.available) < wide.width
    assert narrow.height > wide.height

    frame(view, width_px=1.0)
    assert view.layout is not None and view.layout.width == sp_from_px(MIN_WIDTH_PX)


def test_a_width_the_host_passes_is_the_measure(view: BareView) -> None:
    frame(view, width_px=412.0)
    assert view.layout is not None and view.layout.width == sp_from_px(412.0)


def test_nothing_is_painted_behind_the_text(view: BareView, bundled_fonts: Any) -> None:
    # Every vertex is a glyph's: at most four a glyph (a space is a glyph with
    # no quad), and this document has no rule. With no font given the backend
    # sets the glyphs in ImGui's default face, which is fine here -- the count
    # is the point. The page view, in the same harness, sets the same glyphs
    # and has exactly one quad more: its sheet. That is the control.
    bare = frame(view)
    assert bare.glyphs > 100 and bare.rules == 0
    assert 0 < bare.vertices <= 4 * bare.glyphs and bare.vertices % 4 == 0
    page = DocumentView(document=view.document, theme=view.theme, measure=view.measure)
    sheet = frame(page)
    assert sheet.glyphs == bare.glyphs
    assert sheet.vertices == bare.vertices + 4


def test_the_view_claims_its_height_whether_or_not_a_drag_is_in_progress(
    view: BareView,
) -> None:
    idle = frame(view)
    layout = view.layout
    assert layout is not None
    height = px_from_sp(layout.height)
    # The document's height and then ImGui's own spacing after an item.
    assert height <= idle.after.y - idle.cursor.y <= height + 8.0

    frame(view, mouse=over_text(view))
    dragging = frame(view, mouse=over_text(view), left=True)
    assert view._dragging
    # The dummy and the button advance the cursor identically.
    assert dragging.after.y - dragging.cursor.y == pytest.approx(idle.after.y - idle.cursor.y)
    frame(view, left=False)


def test_only_what_the_window_shows_is_handed_to_the_backend(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme = Theme.build()
    tall = BareView(
        document=build_document(SOURCE * 30, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    handed: list[int] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        handed.append(sum(len(cmds) for cmds, _ in runs))
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    frame(tall, mouse=(1190.0, 790.0))
    frame(tall)
    layout = tall.layout
    assert layout is not None
    assert px_from_sp(layout.height) > 3 * 700.0, "the document must be taller than the window"
    assert 0 < handed[-1] < len(layout.cmds) // 3


# -- the mouse: what is left for the caller ---------------------------------


def test_over_the_text_there_is_no_item_and_the_host_can_ask_what_is_there(
    view: BareView,
) -> None:
    frame(view, mouse=over_text(view))
    seen = frame(view, mouse=over_text(view))
    # No interactive item: nothing hovered, nothing active, nothing swallowed.
    assert not seen.any_hovered
    assert not seen.any_active
    # And yet the host can tell the mouse is over the document, and which block.
    assert seen.item_hovered
    assert view.block_under_mouse() == 0

    # Off the document the same question answers no.
    away = frame(view, mouse=(1190.0, 790.0))
    away = frame(view, mouse=(1190.0, 790.0))
    assert not away.item_hovered


def test_the_block_under_a_point_and_its_verbatim_source(view: BareView) -> None:
    frame(view)
    layout = view.layout
    assert layout is not None and view.origin is not None
    x = view.origin[0] + 5.0
    blocks = []
    for unit in layout.placed:
        middle = view.origin[1] + px_from_sp((unit.y + unit.bottom) // 2)
        blocks.append(view.block_at(x, middle))
    assert blocks == [0, 1, 2]
    assert view.block_at(x, view.origin[1] - 5.0) is None

    code = view.source_of(1)
    assert code is not None
    assert code.span.of(SOURCE) == "```\nfenced code\n```\n"
    first = view.source_of(0)
    assert first is not None and first.span.of(SOURCE).startswith("Alpha bravo")
    assert view.source_of(99) is None


def test_a_right_click_on_the_text_opens_a_menu_the_host_attached_to_the_view(
    view: BareView,
) -> None:
    where = over_text(view, dx=60.0)
    seen = Seen()
    for right in (None, True, False, None):
        seen = frame(view, mouse=where, right=right, menu="item")
    # `begin_popup_context_item` with an explicit ID, straight after `draw`.
    assert seen.context_item
    assert view.selection.is_empty and not view._dragging


def test_the_windows_own_context_menu_opens_over_the_text(view: BareView) -> None:
    # Asked with `no_open_over_items`: this menu opens only where the mouse is
    # over no item. It opens over the bare view's text...
    where = over_text(view, dx=60.0)
    seen = Seen()
    for right in (None, True, False, None):
        seen = frame(view, mouse=where, right=right, menu="window")
    assert seen.context_window
    assert view.selection.is_empty
    close_popups()

    # ...and not over the page view's, whose button is an item. Same harness,
    # same gesture: the control that shows the flag is doing something.
    page = DocumentView(document=view.document, theme=view.theme, measure=view.measure)
    frame(page, mouse=(1190.0, 790.0))
    frame(page, mouse=(1190.0, 790.0))
    assert page.origin is not None
    on_page = (page.origin[0] + 60.0, page.origin[1] + 6.0)
    for right in (None, True, False, None):
        seen = frame(page, mouse=on_page, right=right, menu="window")
    assert seen.any_hovered
    assert not seen.context_window


# -- the mouse: selection ---------------------------------------------------


def test_a_press_and_drag_on_the_text_selects_it(view: BareView) -> None:
    start = over_text(view)
    frame(view, mouse=start)
    pressed = frame(view, mouse=start, left=True)
    assert view._dragging
    # The drag owns an item for as long as it lasts...
    assert pressed.any_active
    end = over_text(view, dx=140.0)
    frame(view, mouse=end)
    released = frame(view, mouse=end, left=False)
    assert not view._dragging
    assert view.selected_text().startswith("Alpha bravo"), view.selected_text()
    # ...and no longer. (ImGui reports the previous frame's hovered item for
    # one frame more, which is why this looks two frames on.)
    frame(view, mouse=end)
    after = frame(view, mouse=end)
    assert not after.any_active and not after.any_hovered
    assert released.window_pos == WINDOW


def test_a_drag_on_the_text_does_not_move_the_hosts_window(view: BareView) -> None:
    # The reason there is an item at all. ImGui drags a window by any press
    # that lands on no item, so the control comes first: a press on the bare
    # window background, below the document, moves the window.
    assert view.origin is not None and view.layout is not None
    empty = (view.origin[0] + 200.0, view.origin[1] + px_from_sp(view.layout.height) + 120.0)
    frame(view, mouse=empty)
    frame(view, mouse=empty, left=True)
    frame(view, mouse=(empty[0] + 50.0, empty[1] + 30.0))
    moved = frame(view, mouse=(empty[0] + 50.0, empty[1] + 30.0), left=False)
    moved = frame(view)
    assert moved.window_pos != WINDOW, "the harness cannot detect a window drag"
    assert view.selection.is_empty

    # The same gesture begun on the text selects, and the window stays put.
    home = moved.window_pos
    start = over_text(view)
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    frame(view, mouse=(start[0] + 150.0, start[1] + 30.0))
    frame(view, mouse=(start[0] + 150.0, start[1] + 30.0), left=False)
    still = frame(view)
    assert still.window_pos == home
    assert not view.selection.is_empty
    close_popups()


def test_a_double_click_selects_a_word(view: BareView) -> None:
    where = over_text(view, dx=20.0)
    frame(view, mouse=where)
    for down in (True, False, True, False):
        frame(view, mouse=where, left=down)
    assert view.selected_text() == "Alpha"


def test_an_item_the_host_drew_over_the_text_keeps_its_click(view: BareView) -> None:
    where = over_text(view, dx=30.0, dy=8.0)
    assert view.origin is not None
    corner = view.origin

    def host_button(imgui: Any, seen: Seen) -> None:
        # Submitted before the view, over its first line, without moving the
        # cursor the view will be drawn at.
        home = imgui.get_cursor_screen_pos()
        imgui.set_cursor_screen_pos(imgui.ImVec2(corner[0], corner[1]))
        if imgui.button("host", imgui.ImVec2(120.0, 18.0)):
            seen.host_clicked = True
        imgui.set_cursor_screen_pos(home)

    frame(view, mouse=where, before=host_button)
    frame(view, mouse=where, left=True, before=host_button)
    assert not view._dragging
    released = frame(view, mouse=where, left=False, before=host_button)
    assert released.host_clicked
    assert view.selection.is_empty


def test_an_overlay_the_host_draws_after_the_view_keeps_its_click_too(view: BareView) -> None:
    # Submitted *after* `draw`, so it does not exist yet when the press is
    # judged on the frame it happens. It was hovered on the frame before,
    # though, and that is what the view asks about.
    where = over_text(view, dx=30.0, dy=8.0)
    assert view.origin is not None
    corner = view.origin

    def overlay(imgui: Any, seen: Seen) -> None:
        imgui.set_cursor_screen_pos(imgui.ImVec2(corner[0], corner[1]))
        if imgui.button("overlay", imgui.ImVec2(120.0, 18.0)):
            seen.host_clicked = True

    frame(view, mouse=where, after=overlay)
    frame(view, mouse=where, after=overlay)
    frame(view, mouse=where, left=True, after=overlay)
    assert not view._dragging
    released = frame(view, mouse=where, left=False, after=overlay)
    assert released.host_clicked
    assert view.selection.is_empty


def test_two_views_in_one_window_select_independently(bundled_fonts: Any) -> None:
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    first = BareView(
        document=build_document("First view words here.\n", theme, fontlib_metrics),
        theme=theme,
        measure=measure,
    )
    second = BareView(
        document=build_document("Second view other text.\n", theme, fontlib_metrics),
        theme=theme,
        measure=measure,
    )
    frame(first, second, mouse=(1190.0, 790.0), left=False)
    frame(first, second, mouse=(1190.0, 790.0))
    assert first.origin is not None and second.origin is not None
    assert second.origin[1] > first.origin[1]
    start = (second.origin[0] + 2.0, second.origin[1] + 6.0)
    frame(first, second, mouse=start)
    frame(first, second, mouse=start, left=True)
    frame(first, second, mouse=(start[0] + 90.0, start[1]))
    frame(first, second, mouse=(start[0] + 90.0, start[1]), left=False)
    assert second.selected_text().startswith("Second")
    assert first.selection.is_empty and not first._dragging
    close_popups()


# -- shared with the page view ----------------------------------------------


def test_the_page_view_is_the_bare_view_with_a_page_on_it() -> None:
    # "Share code, do not fork it": the layout, the selection, the mouse and
    # the copy are one implementation, inherited.
    assert issubclass(DocumentView, BareView)
    for shared in (
        "layout_for",
        "selected_text",
        "viewport_in",
        "_handle_mouse",
        "_handle_copy",
        "_paint",
        "_document_point",
    ):
        assert getattr(DocumentView, shared) is getattr(BareView, shared), shared
    assert DocumentView.draw is not BareView.draw
    assert DocumentView._pressed is not BareView._pressed


def test_changing_one_block_and_invalidating_reships_one_block(view: BareView) -> None:
    frame(view)
    shipped = view._units.stats().misses
    theme = view.theme
    edited = SOURCE.replace("Second paragraph", "Another paragraph")
    view.document = build_document(edited, theme, fontlib_metrics)
    view.invalidate()
    assert view.layout is None
    frame(view)
    assert view._units.stats().misses == shipped + 1
    assert view.layout is not None and len(view.layout.placed) == 3


# -- ink ---------------------------------------------------------------------

INKED = (
    "# A heading\n"
    "\n"
    "Body text in a paragraph.\n"
    "\n"
    "More body text in a second paragraph.\n"
    "\n"
    "```\ncode here\n```\n"
    "\n"
    "> A quoted line.\n"
    "\n"
    "---\n"
    "\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n"
)
"""
One block of each role a palette can ink, and two paragraphs in a row.
"""

HEADING, BODY, CODE, QUOTE, TABLE, RULE_INK, PAGE = (
    0xFF0000F1,
    0xFF0000F2,
    0xFF0000F3,
    0xFF0000F4,
    0xFF0000F5,
    0xFF0000F6,
    0xFF0000F7,
)


@pytest.fixture
def inked(bundled_fonts: Any) -> BareView:
    theme = Theme.build()
    made = BareView(
        document=build_document(INKED, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(made, mouse=(1190.0, 790.0), left=False, right=False)
    frame(made, mouse=(1190.0, 790.0))
    return made


def role_palette() -> Palette:
    return Palette(page=PAGE, ink=BODY, rule=RULE_INK).with_roles(
        {
            BlockKind.HEADING_1: HEADING,
            BlockKind.CODE: CODE,
            BlockKind.QUOTE: QUOTE,
            BlockKind.TABLE: TABLE,
        }
    )


def test_block_kind_reads_the_role_off_every_block_type(inked: BareView) -> None:
    kinds = [block_kind(block) for block in inked.document.blocks]
    assert kinds == [
        BlockKind.HEADING_1,
        BlockKind.PARAGRAPH,
        BlockKind.PARAGRAPH,
        BlockKind.CODE,
        BlockKind.QUOTE,
        BlockKind.RULE,
        BlockKind.TABLE,
    ]


def test_with_no_role_inks_the_view_hands_over_one_run_as_it_always_did(
    inked: BareView, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        seen.append((list(runs), kwargs["palette"]))
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    frame(inked)
    runs, palette = seen[-1]
    layout = inked.layout
    assert layout is not None
    # One run, the default ink, and every command the layout has (the window
    # is taller than this document, so nothing is culled).
    assert palette == Palette()
    assert len(runs) == 1
    assert runs[0] == (layout.cmds, Palette().ink)


def test_each_block_is_handed_over_in_its_roles_ink(
    inked: BareView, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        seen.append(list(runs))
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    frame(inked, palette=role_palette())
    runs = seen[-1]
    layout = inked.layout
    assert layout is not None
    # Heading, the two paragraphs joined into one run, code, quote, the rule
    # (no glyphs; it falls to the body ink and is one run of its own between
    # two differently inked neighbours), table.
    assert [ink for _, ink in runs] == [HEADING, BODY, CODE, QUOTE, BODY, TABLE]
    assert len(runs) < len(layout.placed)
    # Nothing lost, nothing reordered: the runs are the layout's commands.
    assert tuple(cmd for cmds, _ in runs for cmd in cmds) == layout.cmds
    # And each run is exactly its units' commands.
    assert runs[0][0] == layout.placed[0].cmds
    assert runs[1][0] == layout.placed[1].cmds + layout.placed[2].cmds
    assert runs[2][0] == layout.placed[3].cmds


def test_the_role_inks_reach_the_draw_list_and_nothing_else_does(inked: BareView) -> None:
    # End to end, in a real frame: the colour of every quad the view added is
    # one the palette named. No page colour either -- the bare view paints none.
    seen = frame(inked, palette=role_palette())
    drawn = set(seen.colours)
    assert drawn == {HEADING, BODY, CODE, QUOTE, TABLE, RULE_INK}
    assert PAGE not in drawn

    # The same palette through the page view inks the same roles, and paints
    # its sheet in the palette's page colour, which here is not a light one.
    page = DocumentView(document=inked.document, theme=inked.theme, measure=inked.measure)
    sheet = frame(page, palette=role_palette())
    assert set(sheet.colours) == drawn | {PAGE}
    assert sheet.colours[0] == PAGE


def test_a_dark_palette_draws_in_its_own_colours_only(inked: BareView) -> None:
    seen = frame(inked, palette=DARK_PALETTE)
    assert set(seen.colours) == {DARK_PALETTE.ink, DARK_PALETTE.rule}
    # A selection is highlighted in the palette's colour too.
    start = over_text(inked)
    frame(inked, mouse=start, palette=DARK_PALETTE)
    frame(inked, mouse=start, left=True, palette=DARK_PALETTE)
    frame(inked, mouse=(start[0] + 120.0, start[1]), palette=DARK_PALETTE)
    selecting = frame(inked, mouse=(start[0] + 120.0, start[1]), left=False, palette=DARK_PALETTE)
    assert not inked.selection.is_empty
    assert set(selecting.colours) == {DARK_PALETTE.ink, DARK_PALETTE.rule, DARK_PALETTE.highlight}
    assert selecting.colours[0] == DARK_PALETTE.highlight
    close_popups()


def test_each_block_of_a_quote_is_drawn_in_its_own_roles_ink(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A quote is one unit: one command list, one bar. Its run is in the ink of
    # its first block, and each later block that wants another ink gets it by
    # index. So a heading inside a quote is the heading's colour and the
    # paragraph under it the quote's -- neither takes the other's. (Until
    # review 3 the whole unit took its first block's ink, and the docstring
    # said the opposite of what the test pinned.)
    theme = Theme.build()
    view = BareView(
        document=build_document(
            "> # Quoted heading\n>\n> And a quoted paragraph under it.\n", theme, fontlib_metrics
        ),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    assert [block_kind(block) for block in view.document.blocks] == [
        BlockKind.HEADING_1,
        BlockKind.QUOTE,
    ]
    seen: list[Any] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        seen.append((list(runs), kwargs["inks"]))
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    drawn = frame(view, palette=role_palette())
    layout = view.layout
    assert layout is not None and len(layout.placed) == 1
    runs, inks = seen[-1]
    assert [ink for _, ink in runs] == [HEADING]
    (unit,) = layout.placed
    paragraph = unit.indices_of(1)
    assert inks == [(paragraph.start, paragraph.stop, QUOTE)]
    assert layout.model.text(Selection(paragraph.start, paragraph.stop)).startswith("And a quoted")
    # Both colours are really on the glyphs.
    assert {HEADING, QUOTE} <= set(drawn.colours)


def test_a_link_inside_a_quoted_paragraph_shows_over_that_paragraphs_role_ink(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme = Theme.build()
    view = BareView(
        document=build_document(
            "> First quoted paragraph.\n>\n"
            "> # A heading with [a link](https://example.com/q) in it\n",
            theme,
            fontlib_metrics,
        ),
        theme=theme,
        measure=char_measure(fontlib_metrics),
        on_link=lambda target: None,
    )
    seen: list[Any] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["inks"])
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    palette = role_palette()
    frame(view, palette=palette)
    layout = view.layout
    assert layout is not None
    inks = seen[-1]
    # Sorted, non-overlapping, and the heading's ink is cut around the link's.
    assert inks == sorted(inks)
    assert all(a[1] <= b[0] for a, b in zip(inks, inks[1:], strict=False))
    by_colour = {
        colour: " ".join(
            layout.model.text(Selection(start, end)).strip()
            for start, end, ink in inks
            if ink == colour
        )
        for colour in (HEADING, palette.link)
    }
    assert by_colour[palette.link] == "a link"
    assert by_colour[HEADING] == "A heading with in it"


# -- links -------------------------------------------------------------------

LINKED = (
    "Words before [the first link](https://example.com/one) and words after it, "
    "then enough more words that the paragraph wraps and [a second link whose "
    "text is long enough to break across a line](https://example.com/two) at the "
    "width this test lays it out to, and a tail.\n"
    "\n"
    "```\ndef f(x):\n    return x\n```\n"
    "\n"
    "> A quoted paragraph first.\n"
    ">\n"
    "> Then one with [a quoted link](https://example.com/three) in it.\n"
)
"""
Two links in a paragraph (one made to break), a code block, and a link inside a quote.
"""

LINK_WIDTH = 420.0
"""
A pane narrow enough that the second link is set across two lines.
"""


@pytest.fixture
def linked(bundled_fonts: Any) -> tuple[BareView, list[str]]:
    theme = Theme.build()
    followed: list[str] = []
    made = BareView(
        document=build_document(LINKED, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
        on_link=followed.append,
    )
    frame(made, mouse=(1190.0, 790.0), left=False, right=False, child_width=LINK_WIDTH)
    frame(made, mouse=(1190.0, 790.0), child_width=LINK_WIDTH)
    return made, followed


def on_link(view: BareView, target: str, line: int = 0) -> tuple[float, float]:
    """
    A screen position in the middle of one line of the link with this target.
    """
    (link,) = [area for area in view.visible_links if area.target == target]
    rect = link.rects[line]
    assert view.origin is not None
    return (
        view.origin[0] + px_from_sp(rect.x + rect.width // 2),
        view.origin[1] + px_from_sp(rect.y + rect.height // 2),
    )


def lframe(view: BareView, **kwargs: Any) -> Seen:
    return frame(view, child_width=LINK_WIDTH, **kwargs)


def test_every_link_on_screen_is_found_including_one_inside_a_quote(
    linked: tuple[BareView, list[str]],
) -> None:
    view, _ = linked
    assert [link.target for link in view.visible_links] == [
        "https://example.com/one",
        "https://example.com/two",
        "https://example.com/three",
    ]
    # The second was set across a line: one link, two rectangles.
    assert [len(link.rects) for link in view.visible_links] == [1, 2, 1]
    # Block numbers are the document's: the paragraph, and the quote's second
    # paragraph, which shares its unit's commands with the first.
    assert [link.block for link in view.visible_links] == [0, 0, 3]
    assert view.unmapped_blocks == 0


def test_hovering_a_link_reports_its_target_and_asks_for_the_hand(
    linked: tuple[BareView, list[str]],
) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    view, followed = linked
    where = on_link(view, "https://example.com/one")
    lframe(view, mouse=where)
    seen = lframe(view, mouse=where)
    assert view.hovered_link == "https://example.com/one"
    assert seen.cursor_kind == imgui.MouseCursor_.hand
    # Still no item: hovering a link is geometry, like everything else here.
    assert not seen.any_hovered and not seen.any_active

    beside = over_text(view)
    lframe(view, mouse=beside)
    seen = lframe(view, mouse=beside)
    assert view.hovered_link is None
    assert seen.cursor_kind != imgui.MouseCursor_.hand
    assert followed == []

    view.hand_cursor = False
    lframe(view, mouse=where)
    seen = lframe(view, mouse=where)
    assert view.hovered_link == "https://example.com/one"
    assert seen.cursor_kind != imgui.MouseCursor_.hand


def test_a_click_on_a_link_follows_it_and_selects_nothing(
    linked: tuple[BareView, list[str]],
) -> None:
    view, followed = linked
    where = on_link(view, "https://example.com/one")
    lframe(view, mouse=where)
    home = lframe(view, mouse=where).window_pos
    pressed = lframe(view, mouse=where, left=True)
    # The press is the link's: no selection drag began, and the view holds an
    # item so that the press does not drag the window either.
    assert not view._dragging and view.selection.is_empty
    assert pressed.any_active
    assert followed == []
    lframe(view, mouse=where, left=False)
    assert followed == ["https://example.com/one"]
    assert view.selection.is_empty
    lframe(view, mouse=where)
    after = lframe(view, mouse=where)
    assert not after.any_active
    assert after.window_pos == home
    assert followed == ["https://example.com/one"], "followed once, not once a frame"


def test_a_link_broken_across_two_lines_is_one_link_to_click(
    linked: tuple[BareView, list[str]],
) -> None:
    view, followed = linked
    upper = on_link(view, "https://example.com/two", line=0)
    lower = on_link(view, "https://example.com/two", line=1)
    assert lower[1] > upper[1]
    lframe(view, mouse=upper)
    lframe(view, mouse=upper, left=True)
    lframe(view, mouse=lower)
    lframe(view, mouse=lower, left=False)
    assert followed == ["https://example.com/two"]
    assert view.selection.is_empty and not view._dragging


def test_a_press_on_a_link_released_elsewhere_follows_nothing(
    linked: tuple[BareView, list[str]],
) -> None:
    view, followed = linked
    where = on_link(view, "https://example.com/one")
    other = on_link(view, "https://example.com/two")
    plain = over_text(view)
    for release_at in (plain, other):
        lframe(view, mouse=where)
        lframe(view, mouse=where, left=True)
        lframe(view, mouse=release_at)
        lframe(view, mouse=release_at, left=False)
        lframe(view, mouse=release_at)
    assert followed == []
    assert view.selection.is_empty
    assert view._link_down is None


def test_with_no_callback_a_link_is_plain_text_and_a_press_on_it_selects(
    linked: tuple[BareView, list[str]],
) -> None:
    view, followed = linked
    where = on_link(view, "https://example.com/one")
    view.on_link = None
    lframe(view, mouse=where)
    lframe(view, mouse=where)
    assert view.hovered_link is None
    lframe(view, mouse=where, left=True)
    assert view._dragging
    lframe(view, mouse=(where[0] + 60.0, where[1]))
    lframe(view, mouse=(where[0] + 60.0, where[1]), left=False)
    assert not view.selection.is_empty
    assert followed == []
    close_popups()


def _handed(view: BareView, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> dict[str, Any]:
    """
    One frame, returning the keyword arguments the view gave the backend.
    """
    seen: list[dict[str, Any]] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **given: Any) -> Any:
        seen.append({**given, "runs": list(runs)})
        return real(draw_list, runs, origin, **given)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    lframe(view, **kwargs)
    monkeypatch.setattr(bare_module, "draw_runs", real)
    return seen[-1]


def _text_in(view: BareView, start: int, end: int) -> str:
    assert view.layout is not None
    return view.layout.model.text(view.layout.model.select(start, end))


def test_a_live_link_is_drawn_in_the_link_ink_with_an_underline_on_each_line(
    linked: tuple[BareView, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = linked
    palette = Palette(link=0xFF0000C1)
    given = _handed(view, monkeypatch, palette=palette)
    inks = given["inks"]
    assert {colour for _, _, colour in inks} == {palette.link}
    inked = " ".join(_text_in(view, start, end) for start, end, _ in inks)
    assert inked == (
        "the first link a second link whose text is long enough to break across a line "
        "a quoted link"
    )
    # One underline per line of each link: 1 + 2 + 1.
    assert [colour for _, colour in given["fills"]] == [palette.link] * 4
    rects = [rect for link in view.visible_links for rect in link.rects]
    for (under, _), rect in zip(given["fills"], rects, strict=True):
        assert (under.x, under.width) == (rect.x, rect.width)
        assert rect.y < under.y < rect.y + rect.height
        assert 0 < under.height < rect.height // 8


def test_links_are_styled_when_live_unless_the_host_says_otherwise(
    linked: tuple[BareView, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = linked
    assert _handed(view, monkeypatch)["inks"]
    view.on_link = None
    plain = _handed(view, monkeypatch)
    assert plain["inks"] == [] and plain["fills"] == []
    # Where the links are does not depend on whether they are drawn.
    assert len(view.visible_links) == 3
    view.style_links = True
    assert _handed(view, monkeypatch)["inks"]
    view.on_link = lambda target: None
    view.style_links = False
    assert _handed(view, monkeypatch)["inks"] == []

    # The demo's page view has no callback, so it draws links as it always did.
    page = DocumentView(document=view.document, theme=view.theme, measure=view.measure)
    frame(page, mouse=(1190.0, 790.0))
    given = _handed(page, monkeypatch)
    assert given["inks"] == [] and given["fills"] == []


# -- colour finer than a block -------------------------------------------------


def test_syntax_colours_and_find_marks_reach_the_backend_on_the_right_words(
    linked: tuple[BareView, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = linked
    view.on_link = None
    keyword, hit = 0xFF0000D1, 0xFF0000D2
    code = view.document.blocks[1]
    paragraph = view.document.blocks[0]
    assert isinstance(code, CodeBlock) and isinstance(paragraph, TextBlock)
    view.set_colours(
        1,
        [
            ColourSpan(code_position(code, 0, 0), code_position(code, 0, 3), ink=keyword),
            ColourSpan(code_position(code, 1, 4), code_position(code, 1, 10), ink=keyword),
        ],
    )
    view.set_colours(0, find_spans(paragraph, "words", mark=hit))
    given = _handed(view, monkeypatch)
    assert [_text_in(view, start, end) for start, end, _ in given["inks"]] == ["def", "return"]
    assert {colour for _, _, colour in given["inks"]} == {keyword}
    assert [colour for _, colour in given["fills"]] == [hit] * 2
    assert view.unmapped_blocks == 0

    # And they are really drawn: the colours are among the frame's vertices.
    seen = lframe(view)
    assert {keyword, hit} <= set(seen.colours)

    view.set_colours(1, [])
    given = _handed(view, monkeypatch)
    assert given["inks"] == [] and len(given["fills"]) == 2
    view.clear_colours()
    given = _handed(view, monkeypatch)
    assert given["inks"] == [] and given["fills"] == []


def test_a_units_decoration_is_built_once_and_kept_until_something_changes(
    linked: tuple[BareView, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _ = linked
    calls: list[int] = []
    real = bare_module.decorate

    def counted(block: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs["number"])
        return real(block, *args, **kwargs)

    monkeypatch.setattr(bare_module, "decorate", counted)
    for _ in range(5):
        lframe(view)
    assert calls == [], "the fixture's settling frames already built these"

    paragraph = view.document.blocks[0]
    assert isinstance(paragraph, TextBlock)
    view.set_colours(0, find_spans(paragraph, "words", mark=0xFF0000D2))
    for _ in range(5):
        lframe(view)
    # The paragraph's unit, once. The quote's unit was not touched.
    assert calls == [0]

    # A different palette's link ink is a different decoration for both units.
    for _ in range(3):
        lframe(view, palette=Palette(link=0xFF0000C2))
    assert sorted(calls[1:]) == [0, 3]


def test_a_link_in_a_table_cell_is_live_wrapped_or_not(bundled_fonts: Any) -> None:
    theme = Theme.build()
    followed: list[str] = []
    view = BareView(
        document=build_document(
            "| what | where |\n|---|---|\n"
            "| a cell with enough words in it that it has to wrap, and "
            "[a link to follow](https://example.com/cell) inside "
            "| [second](https://example.com/b) |\n",
            theme,
            fontlib_metrics,
        ),
        theme=theme,
        measure=char_measure(fontlib_metrics),
        on_link=followed.append,
    )
    for width in (LINK_WIDTH, 0.0):
        frame(view, mouse=(1190.0, 790.0), left=False, child_width=width)
        frame(view, mouse=(1190.0, 790.0), child_width=width)
        assert [link.target for link in view.visible_links] == [
            "https://example.com/cell",
            "https://example.com/b",
        ]
        assert view.unmapped_blocks == 0
        where = on_link(view, "https://example.com/cell")
        frame(view, mouse=where, child_width=width)
        frame(view, mouse=where, child_width=width)
        assert view.hovered_link == "https://example.com/cell"
        frame(view, mouse=where, left=True, child_width=width)
        frame(view, mouse=where, left=False, child_width=width)
    assert followed == ["https://example.com/cell"] * 2
    assert view.selection.is_empty


# -- copy ----------------------------------------------------------------------

COPY_SOURCE = (
    "A paragraph first.\n"
    "\n"
    "```\nline one\nline two\n\nline four\n```\n"
    "\n"
    "- an item with [a link](https://example.com/item) in it\n"
    "- another item\n"
)


def copy_view(source: str = COPY_SOURCE, **kwargs: Any) -> BareView:
    theme = Theme.build()
    made = BareView(
        document=build_document(source, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
        **kwargs,
    )
    return made


def pressed_ctrl_c(*views: BareView, **kwargs: Any) -> str:
    """
    Ctrl+C down for a frame and up for a frame; what the clipboard holds afterwards.

    The clipboard is ImGui's own in-memory one, seeded with a sentinel so a
    copy that did not happen cannot pass on what an earlier test left there.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    imgui.set_clipboard_text("SENTINEL")
    frame(*views, ctrl_c=True, **kwargs)
    frame(*views, ctrl_c=False, **kwargs)
    return str(imgui.get_clipboard_text())


def test_ctrl_c_over_a_code_block_keeps_its_lines(bundled_fonts: Any) -> None:
    # Phase 6, defect 1. Written first and run against the tree as found: the
    # clipboard held 'line one line two\nline four'.
    view = copy_view("```\nline one\nline two\n\nline four\n```\n")
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    view.select_all()
    assert pressed_ctrl_c(view) == "line one\nline two\n\nline four"


def test_ctrl_c_gives_back_a_character_no_face_could_set(bundled_fonts: Any) -> None:
    # A character none of the faces has is drawn as U+FFFD
    # (`advtext.markdown.ReplacedChar`); the clipboard and `selected_text`
    # get the character the source had. Before C-facade both got U+FFFD.
    view = copy_view("Speed is \u901f\u5ea6 here.\n\n```\nv = \u901f\n```\n")
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    view.select_all()
    assert pressed_ctrl_c(view) == "Speed is \u901f\u5ea6 here.\n\nv = \u901f"
    assert view.selected_text() == "Speed is \u901f\u5ea6 here.\n\nv = \u901f"


def test_ctrl_c_copies_the_document_as_it_reads_not_as_it_wrapped(bundled_fonts: Any) -> None:
    view = copy_view()
    for width in (0.0, 260.0):
        frame(view, mouse=(1190.0, 790.0), left=False, child_width=width)
        frame(view, child_width=width)
        view.select_all()
        assert pressed_ctrl_c(view, child_width=width) == (
            "A paragraph first.\n"
            "\n"
            "line one\nline two\n\nline four\n"
            "\n"
            "\u2022 an item with a link in it\n"
            "\u2022 another item"
        )
        assert view.selected_text() == pressed_ctrl_c(view, child_width=width)


def test_one_keypress_copies_from_one_view_and_it_is_the_one_last_selected_in(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phase 6, defect 2. Written first and run against the tree as found: two
    # views with a selection each made two clipboard writes on one keypress,
    # ['First', 'Second'], and the second silently won.
    imgui = pytest.importorskip("imgui_bundle").imgui
    first, second = copy_view("First view words.\n"), copy_view("Second view words.\n")
    frame(first, second, mouse=(1190.0, 790.0), left=False)
    frame(first, second)
    writes: list[str] = []
    real = imgui.set_clipboard_text
    monkeypatch.setattr(
        imgui, "set_clipboard_text", lambda text: (writes.append(text), real(text))[1]
    )

    first.select(Selection(0, 5))
    second.select(Selection(0, 6))
    frame(first, second)
    # Selecting in the second took the selection from the first.
    assert second.owns_selection and not first.owns_selection
    assert first.selection.is_empty and not second.selection.is_empty
    assert pressed_ctrl_c(first, second) == "Second"
    assert writes == ["SENTINEL", "Second"]

    # And back again, by a real press in the first view.
    assert first.origin is not None
    where = (first.origin[0] + 2.0, first.origin[1] + 6.0)
    frame(first, second, mouse=where)
    frame(first, second, mouse=where, left=True)
    frame(first, second, mouse=(where[0] + 70.0, where[1]))
    frame(first, second, mouse=(where[0] + 70.0, where[1]), left=False)
    assert first.owns_selection and not second.owns_selection
    assert second.selection.is_empty
    assert pressed_ctrl_c(first, second).startswith("First")
    close_popups()


def test_a_view_that_owns_nothing_copies_nothing(bundled_fonts: Any) -> None:
    view = copy_view()
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    assert not view.owns_selection
    assert pressed_ctrl_c(view) == "SENTINEL"
    # A selection that is there but was never made current -- put in place
    # behind the view's back, as a test or a restore might -- is not copied:
    # the keypress belongs to whichever view was last selected in.
    view._selection = Selection(0, 11)
    assert view.selected_text() == "A paragraph"
    assert pressed_ctrl_c(view) == "SENTINEL"
    view.select(Selection(0, 11))
    assert pressed_ctrl_c(view) == "A paragraph"
    # An empty selection is not copied either, owned or not.
    view.select(Selection(3, 3))
    assert pressed_ctrl_c(view) == "SENTINEL"


def test_ctrl_c_is_left_to_a_text_input_that_is_being_typed_in(bundled_fonts: Any) -> None:
    view = copy_view()
    box: list[tuple[float, float]] = []

    def host_input(imgui: Any, seen: Seen) -> None:
        where = imgui.get_cursor_screen_pos()
        box.append((float(where.x) + 20.0, float(where.y) + 8.0))
        imgui.set_next_item_width(200.0)
        imgui.input_text("##host-input", "typed text")

    frame(view, mouse=(1190.0, 790.0), left=False, before=host_input)
    frame(view, before=host_input)
    view.select_all()
    assert pressed_ctrl_c(view, before=host_input).startswith("A paragraph first.")

    # Click into the host's input: it is active, and the keypress is its own.
    imgui = pytest.importorskip("imgui_bundle").imgui
    frame(view, mouse=box[-1], before=host_input)
    frame(view, mouse=box[-1], left=True, before=host_input)
    frame(view, mouse=box[-1], left=False, before=host_input)
    frame(view, before=host_input)
    assert imgui.get_io().want_text_input
    assert view.owns_selection and not view.selection.is_empty
    copied = pressed_ctrl_c(view, before=host_input)
    assert not copied.startswith("A paragraph first."), copied

    # Leave the input, and the view answers again.
    frame(view, mouse=(1190.0, 790.0), before=host_input)
    frame(view, mouse=(1190.0, 790.0), left=True, before=host_input)
    frame(view, mouse=(1190.0, 790.0), left=False, before=host_input)
    frame(view, before=host_input)
    assert not imgui.get_io().want_text_input
    assert pressed_ctrl_c(view, before=host_input).startswith("A paragraph first.")
    close_popups()


# -- the host's hooks ----------------------------------------------------------


def test_the_host_can_make_a_copy_mean_the_markdown(bundled_fonts: Any) -> None:
    view = copy_view(copy_as=lambda v: v.selected_source(COPY_SOURCE))
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    view.select_all()
    assert pressed_ctrl_c(view) == COPY_SOURCE
    # `selected_text` is still the rendered text; `copy_as` is what Ctrl+C writes.
    assert view.selected_text().startswith("A paragraph first.\n\nline one")


def test_copy_as_markdown_is_the_source_of_every_block_the_selection_touches(
    bundled_fonts: Any,
) -> None:
    view = copy_view()
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    layout = view.layout
    assert layout is not None

    # Two words of the paragraph: its whole source line.
    view.select(Selection(2, 9))
    assert view.selected_blocks() == (0,)
    assert view.selected_source(COPY_SOURCE) == "A paragraph first.\n"

    # From inside the code block into the first list item: both blocks whole,
    # with one blank line where the source has one between them.
    code, item = layout.placed[1], layout.placed[2]
    view.select(Selection(code.base + 3, item.base + 4))
    assert view.selected_blocks() == (1, 2)
    assert view.selected_source(COPY_SOURCE) == (
        "```\nline one\nline two\n\nline four\n```\n"
        "\n"
        "- an item with [a link](https://example.com/item) in it\n"
    )
    # Two adjacent list items are adjacent source lines: nothing between them.
    view.select(Selection(item.base, layout.length))
    assert view.selected_source(COPY_SOURCE) == (
        "- an item with [a link](https://example.com/item) in it\n- another item\n"
    )
    view.clear_selection()
    assert view.selected_blocks() == () and view.selected_source(COPY_SOURCE) == ""


def test_a_block_can_be_had_as_text_and_as_source_for_a_menu_item(bundled_fonts: Any) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    view = copy_view()
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    assert view.block_text(1) == "line one\nline two\n\nline four"
    assert view.block_text(2) == "\u2022 an item with a link in it"
    assert view.block_text(99) == ""
    assert view.block_source(1, COPY_SOURCE) == "```\nline one\nline two\n\nline four\n```\n"
    assert view.block_source(2, COPY_SOURCE) == (
        "- an item with [a link](https://example.com/item) in it\n"
    )
    # The whole list, for an item of it.
    assert view.block_source(2, COPY_SOURCE, top=True) == (
        "- an item with [a link](https://example.com/item) in it\n- another item\n"
    )
    assert view.block_source(99, COPY_SOURCE) is None

    # `copy` writes whatever the host's menu item says, and by default the selection.
    imgui.set_clipboard_text("SENTINEL")
    view.copy(view.block_source(1, COPY_SOURCE))
    assert imgui.get_clipboard_text().startswith("```\nline one")
    view.select(Selection(0, 11))
    view.copy()
    assert imgui.get_clipboard_text() == "A paragraph"


def test_the_view_says_what_is_under_a_point_and_opens_nothing(bundled_fonts: Any) -> None:
    # No `on_link`: the link is not live, and is still reported -- a "copy link
    # address" item does not need the view to follow links.
    view = copy_view()
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    layout = view.layout
    assert layout is not None and view.origin is not None
    assert view.hovered_link is None

    (link,) = view.visible_links
    rect = link.rects[0]
    on_the_link = (
        view.origin[0] + px_from_sp(rect.x + rect.width // 2),
        view.origin[1] + px_from_sp(rect.y + rect.height // 2),
    )
    pointed = view.pointed(*on_the_link)
    assert (pointed.block, pointed.link, pointed.selected) == (
        2,
        "https://example.com/item",
        False,
    )
    code = layout.placed[1]
    first_glyph = next(cmd for cmd in code.cmds if isinstance(cmd, Glyph))
    in_the_code = (
        view.origin[0] + px_from_sp(first_glyph.x) + 3.0,
        view.origin[1] + px_from_sp(code.y) + 6.0,
    )
    assert view.pointed(*in_the_code) == Pointed(block=1, link=None, selected=False)
    assert view.pointed(view.origin[0] + 5.0, view.origin[1] - 50.0) == Pointed(None, None, False)

    # On selected text, the menu is about the selection.
    view.select(Selection(code.base, code.base + code.unit.count))
    assert view.pointed(*in_the_code).selected
    assert not view.pointed(*on_the_link).selected

    # `under_mouse` is `pointed` at the mouse, and a right click there selects
    # nothing and leaves the selection alone.
    frame(view, mouse=in_the_code)
    frame(view, mouse=in_the_code, right=True, menu="item")
    frame(view, mouse=in_the_code, right=False, menu="item")
    opened = frame(view, mouse=in_the_code, menu="item")
    assert opened.context_item
    assert view.under_mouse() == Pointed(block=1, link=None, selected=True)
    assert view.selection == Selection(code.base, code.base + code.unit.count)
    close_popups()


# -- review 3: drags, relayouts, highlights -------------------------------------


def test_a_drag_whose_release_frame_was_not_drawn_ends_all_the_same(view: BareView) -> None:
    # The view sees `is_mouse_released` only on a frame it is drawn. Hidden on
    # that one frame, it used to go on selecting with no button held, and kept
    # its drag button submitted. Confirmed before the fix with the reviewer's
    # snippet: dragging True, selection still changing, an item hovered.
    start = over_text(view)
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    frame(view, mouse=(start[0] + 40.0, start[1]))
    assert view._dragging
    held = view.selection
    frame(view, left=False, skip_draw=True)

    frame(view, mouse=(start[0] + 200.0, start[1]))
    after = frame(view, mouse=(start[0] + 200.0, start[1]))
    assert not view._dragging
    assert view.selection == held, "the mouse's wandering after the release is not the drag"
    frame(view, mouse=(start[0] + 200.0, start[1]))
    settled = frame(view, mouse=(start[0] + 200.0, start[1]))
    assert not after.any_active and not settled.any_hovered


def test_a_drag_ends_when_the_application_loses_focus_under_it(view: BareView) -> None:
    start = over_text(view)
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    frame(view, mouse=(start[0] + 40.0, start[1]))
    frame(view, focus=False)
    frame(view)
    frame(view, focus=True)
    held = view.selection
    frame(view, mouse=(start[0] + 200.0, start[1]))
    frame(view, mouse=(start[0] + 200.0, start[1]))
    assert not view._dragging and view.selection == held
    close_popups()


def test_a_selection_means_the_same_words_after_the_pane_is_resized(bundled_fonts: Any) -> None:
    # Review 3, item 3. The reading order is renumbered when lines re-break,
    # so the same two integers used to select other words after a resize.
    theme = Theme.build()
    source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    view = BareView(
        document=build_document(source, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    wide = view.layout_for(sp_from_px(500.0))
    # A stretch from the middle of one block to the middle of a later one.
    first, last = wide.placed[10], wide.placed[14]
    view.select(Selection(first.base + 9, last.base + 20))
    before = view.selected_text()
    assert len(before) > 200
    kept = view.selection

    narrow = view.layout_for(sp_from_px(400.0))
    assert narrow.length != wide.length, "nothing was renumbered; the fixture shows nothing"
    assert view.selection != kept
    assert view.selected_text() == before
    # And back, and at a third width: the words never change.
    for width in (500.0, 333.0, 900.0):
        view.layout_for(sp_from_px(width))
        assert view.selected_text() == before


def test_a_selection_in_a_block_that_was_replaced_is_dropped_not_reinterpreted(
    bundled_fonts: Any,
) -> None:
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    view = BareView(
        document=build_document("One two three.\n\nFour five six.\n", theme, fontlib_metrics),
        theme=theme,
        measure=measure,
    )
    width = sp_from_px(500.0)
    layout = view.layout_for(width)
    second = layout.placed[1]
    view.select(Selection(second.base, second.base + 4))
    assert view.selected_text() == "Four"

    # The first block changes: the selection is in the second, whose text is
    # the same, so it survives the renumbering.
    view.document = build_document(
        "One two three and more.\n\nFour five six.\n", theme, fontlib_metrics
    )
    view.invalidate()
    view.layout_for(width)
    assert view.selected_text() == "Four"

    # The second block changes under it: gone, rather than now meaning "Nine".
    view.document = build_document(
        "One two three and more.\n\nNine five six.\n", theme, fontlib_metrics
    )
    view.invalidate()
    view.layout_for(width)
    assert view.selection.is_empty


def test_only_the_visible_part_of_a_long_selection_is_turned_into_rectangles(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review 3, item 4: 1460 rectangles a frame for 24 on screen. The highlight
    # is now built from the units the window shows.
    theme = Theme.build()
    tall = BareView(
        document=build_document(SOURCE * 40, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(tall, mouse=(1190.0, 790.0), left=False)
    frame(tall)
    tall.select_all()
    handed: list[int] = []
    real = bare_module.draw_runs

    def spy(draw_list: Any, runs: Any, origin: Any, **kwargs: Any) -> Any:
        handed.append(len(kwargs["highlights"]))
        return real(draw_list, runs, origin, **kwargs)

    monkeypatch.setattr(bare_module, "draw_runs", spy)
    frame(tall)
    layout = tall.layout
    assert layout is not None
    everything = len(layout.model.rects(tall.selection))
    assert 0 < handed[-1] < everything // 4
    # And the units far below were never indexed to find that out. (The line
    # above indexed them all, so a fresh view is asked.)
    fresh = BareView(document=tall.document, theme=theme, measure=tall.measure)
    frame(fresh)
    fresh.select_all()
    frame(fresh)
    assert fresh.layout is not None
    indexed = [unit._placement._model is not None for unit in fresh.layout.placed]
    assert any(indexed) and not all(indexed)
    assert sum(indexed) < len(indexed) // 3


def test_a_document_that_becomes_empty_under_a_drag_does_not_assert(view: BareView) -> None:
    # `invisible_button` with no height is an assertion inside ImGui.
    start = over_text(view)
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    assert view._dragging
    view.document = build_document("", view.theme, fontlib_metrics)
    view.invalidate()
    frame(view, mouse=start)
    frame(view, mouse=start, left=False)
    assert view.layout is not None and view.layout.height == 0
    assert not view._dragging and view.selection.is_empty


def test_hit_testing_follows_the_document_when_the_pane_is_scrolled(
    bundled_fonts: Any,
) -> None:
    # Every other test here hit-tests at scroll zero. Scrolled, the origin the
    # view records is above the window, and a click must still land on the
    # line that is under the mouse and not the one that used to be.
    theme = Theme.build()
    tall = BareView(
        document=build_document(SOURCE * 30, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(tall, mouse=(400.0, 300.0), left=False)
    frame(tall, mouse=(400.0, 300.0))
    for _ in range(4):
        frame(tall, mouse=(400.0, 300.0), wheel=-5.0)
    scrolled = frame(tall, mouse=(400.0, 300.0))
    assert scrolled.scroll_y > 300.0, "the wheel did not scroll the child"
    assert tall.origin is not None and tall.layout is not None
    assert tall.origin[1] < 0.0

    # A line of prose that is on screen now, found from the layout, and the
    # screen position of its middle.
    origin_y = tall.origin[1]
    expected = next(
        fragment
        for fragment in tall.layout.model.fragments
        if len(fragment.items) > 20
        and 250.0 < origin_y + px_from_sp((fragment.top + fragment.bottom) // 2) < 450.0
    )
    where = (
        tall.origin[0] + px_from_sp(expected.line.x) + 60.0,
        origin_y + px_from_sp((expected.top + expected.bottom) // 2),
    )
    point = tall.document_point(*where)
    assert point is not None
    assert expected.top <= point.y < expected.bottom
    frame(tall, mouse=where)
    for down in (True, False, True, False, True, False):
        frame(tall, mouse=where, left=down)
    # A triple click: the visual line under the mouse.
    assert tall.selection == Selection(expected.start, expected.end)
    assert tall.block_under_mouse() == tall.layout.block_at(point)
    close_popups()


# -- review 4: drags across frames not drawn and across relayouts ---------------

WRAPPING = (
    "| key | value |\n"
    "|---|---|\n"
    "| one | several words in a cell that wrap when the pane is narrow |\n"
    "| two | and a second row of the same kind of words as the first |\n"
    "\n"
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky "
    "xray yankee zulu.\n"
)
"""
A table whose cells wrap at a narrow measure, and a paragraph of distinct words below it.

**The table is what renumbers the reading order.** Every line a wrapped cell
gains is a line with glue of its own, and each of those takes an index, so the
paragraph below starts at a different index at each width. Measured on
`demo/sample.md` between 500 and 400 px, its table is the *only* unit whose
index count changes -- which is why a selection in its first paragraphs shows
nothing, and why review 4's second snippet printed `same=True`.
"""


def wrapping_view() -> BareView:
    theme = Theme.build()
    made = BareView(
        document=build_document(WRAPPING, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(made, mouse=(1190.0, 790.0), left=False, right=False, width_px=500.0)
    frame(made, mouse=(1190.0, 790.0), width_px=500.0)
    return made


def in_the_paragraph(view: BareView, dx: float, line: int = 0) -> tuple[float, float]:
    """
    A screen position `dx` pixels along line `line` of the last unit, as last drawn.
    """
    assert view.origin is not None and view.layout is not None
    paragraph = view.layout.placed[-1]
    return (
        view.origin[0] + dx,
        view.origin[1] + px_from_sp(paragraph.y) + 6.0 + 21.6 * line,
    )


@pytest.mark.parametrize("release_drawn", [True, False])
def test_a_drag_that_missed_its_release_means_the_same_words_after_a_relayout(
    bundled_fonts: Any, release_drawn: bool
) -> None:
    # Review 4, item 2. The lead's run of the reviewer's snippet did not show
    # it, for the reason `WRAPPING` gives; with a fixture whose indices move,
    # it did: the view was not drawn on the release frame, so it still thought
    # it was dragging at the next layout, a drag was never carried, and the
    # old integers were left to name other words. `release_drawn=True` is the
    # control and passed before the fix.
    view = wrapping_view()
    start = in_the_paragraph(view, 2.0)
    frame(view, mouse=start, width_px=500.0)
    frame(view, mouse=start, left=True, width_px=500.0)
    end = (start[0] + 150.0, start[1])
    frame(view, mouse=end, width_px=500.0)
    frame(view, mouse=end, width_px=500.0)
    before = view.selected_text()
    assert before.startswith("Alpha bravo") and view._dragging
    kept, wide = view.selection, view.layout
    assert wide is not None

    frame(view, left=False, skip_draw=not release_drawn, width_px=500.0)
    frame(view, width_px=300.0)
    frame(view, width_px=300.0)
    narrow = view.layout
    assert narrow is not None and narrow.length != wide.length, "nothing was renumbered"
    assert narrow.placed[-1].base != wide.placed[-1].base
    assert not view._dragging
    assert view.selected_text() == before
    assert view.selection != kept, "the words are the same because the integers are not"
    close_popups()


def test_a_press_made_while_the_view_was_not_drawn_does_not_resume_the_old_drag(
    view: BareView,
) -> None:
    # Review 4, item 3. The release *and* the next press both happen on frames
    # the view is not drawn (its tab is away): it comes back with the button
    # down and used to take that for its own drag, still in progress, and
    # extend the selection from the old anchor to wherever the mouse now was.
    start = over_text(view)
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    frame(view, mouse=(start[0] + 40.0, start[1]))
    frame(view, mouse=(start[0] + 40.0, start[1]))
    held = view.selection
    assert view._dragging and view.selected_text() == "Alpha"

    frame(view, left=False, skip_draw=True)
    frame(view, mouse=(1100.0, 20.0), left=True, skip_draw=True)
    elsewhere = (start[0] + 300.0, start[1] + 40.0)
    back = frame(view, mouse=elsewhere)
    assert not view._dragging
    assert not back.any_active, "no drag, so no drag button"
    frame(view, mouse=elsewhere)
    assert view.selection == held and view.selected_text() == "Alpha"
    frame(view, left=False)
    close_popups()


def test_a_link_held_down_is_let_go_when_the_view_is_not_drawn_for_a_frame(
    linked: tuple[BareView, list[str]],
) -> None:
    # The same gap for a link: pressed, then the release and a new press both
    # unseen. Coming back with the button down and letting go on the link is
    # not a click on it -- the press that is being released was made elsewhere.
    view, followed = linked
    where = on_link(view, "https://example.com/one")
    lframe(view, mouse=where)
    lframe(view, mouse=where, left=True)
    assert view._link_down is not None
    lframe(view, left=False, skip_draw=True)
    lframe(view, mouse=(1100.0, 20.0), left=True, skip_draw=True)
    lframe(view, mouse=where)
    assert view._link_down is None
    lframe(view, mouse=where, left=False)
    lframe(view, mouse=where)
    assert followed == []
    close_popups()


def test_a_drags_anchor_is_the_text_it_was_put_down_on_not_the_place(
    bundled_fonts: Any,
) -> None:
    # Review 4, item 4. The anchor was a point of the document, and a point
    # is other words once the lines under it re-break. A drag in progress
    # when the pane is resized (or, in a stream, when its block is set again)
    # then moved its *fixed* end. Forwards: the selection must still begin
    # with the words it began with. The moving end is under the mouse and
    # says whatever is under the mouse now; that is not the claim.
    view = wrapping_view()
    press = in_the_paragraph(view, 200.0, line=1)
    frame(view, mouse=press, width_px=500.0)
    frame(view, mouse=press, left=True, width_px=500.0)
    drag = (press[0] + 100.0, press[1])
    frame(view, mouse=drag, width_px=500.0)
    frame(view, mouse=drag, width_px=500.0)
    before = view.selected_text()
    assert len(before) > 8 and view._dragging

    frame(view, mouse=drag, width_px=300.0)
    # Now pull the moving end far below the document: everything from the
    # anchor to the end of the text.
    below = (drag[0], drag[1] + 600.0)
    frame(view, mouse=below, width_px=300.0)
    frame(view, mouse=below, width_px=300.0)
    assert view._dragging
    after = view.selected_text()
    assert after.startswith(before.strip()[:8]), (before, after)
    assert after.endswith("zulu.")
    frame(view, left=False, width_px=300.0)

    # Backwards: pressed at the same spot and dragged up and to the left,
    # the anchor is the selection's end, and that is what must not change.
    view = wrapping_view()
    press = in_the_paragraph(view, 300.0, line=1)
    frame(view, mouse=press, width_px=500.0)
    frame(view, mouse=press, left=True, width_px=500.0)
    drag = (press[0] - 100.0, press[1])
    frame(view, mouse=drag, width_px=500.0)
    frame(view, mouse=drag, width_px=500.0)
    before = view.selected_text()
    assert len(before) > 8
    above = in_the_paragraph(view, 2.0, line=0)
    frame(view, mouse=above, width_px=300.0)
    above = in_the_paragraph(view, 2.0, line=0)
    frame(view, mouse=above, width_px=300.0)
    frame(view, mouse=above, width_px=300.0)
    after = view.selected_text()
    assert after.startswith("Alpha bravo")
    assert after.endswith(before.strip()[-8:]), (before, after)
    frame(view, left=False, width_px=300.0)
    close_popups()


def test_a_double_click_drag_keeps_its_first_word_through_a_relayout(
    bundled_fonts: Any,
) -> None:
    # The anchor of a word drag is the word, whole, and it is carried as a
    # selection of that word is.
    view = wrapping_view()
    press = in_the_paragraph(view, 200.0, line=1)
    frame(view, mouse=press, width_px=500.0)
    for down in (True, False, True):
        frame(view, mouse=press, left=down, width_px=500.0)
    word = view.selected_text()
    assert word.isalpha() and view._dragging
    below = (press[0], press[1] + 600.0)
    frame(view, mouse=below, width_px=300.0)
    frame(view, mouse=below, width_px=300.0)
    after = view.selected_text()
    # A word drag ends on a whole word too, here one of the last line's.
    assert after.startswith(word + " ") and len(after) > len(word) + 20
    assert after.split()[-1] in ("xray", "yankee", "zulu.")
    frame(view, left=False, width_px=300.0)
    close_popups()


def test_asking_what_is_under_a_point_indexes_the_unit_there_and_no_other(
    bundled_fonts: Any,
) -> None:
    # Review 4, item 8. `pointed` asked the whole selection for its
    # rectangles to learn whether one point was in any of them, which built
    # the selection index of every unit under a select-all: 5 to 740 units in
    # one call on twenty copies of the demo document. It is offered for a
    # per-frame tooltip.
    theme = Theme.build()
    tall = BareView(
        document=build_document(SOURCE * 40, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(tall, mouse=(1190.0, 790.0), left=False)
    frame(tall)
    tall.select_all()
    frame(tall)
    frame(tall)
    layout = tall.layout
    assert layout is not None and tall.origin is not None and len(layout.placed) > 70

    def indexed() -> int:
        return sum(unit._placement._model is not None for unit in layout.placed)

    before = indexed()
    assert 0 < before < 40
    on_text = (tall.origin[0] + 50.0, tall.origin[1] + 30.0)
    assert tall.pointed(*on_text).selected
    assert indexed() == before
    # A unit nobody has scrolled to: it is indexed to answer, and it alone.
    far = layout.placed[70]
    assert far._placement._model is None
    down_there = (tall.origin[0] + 50.0, tall.origin[1] + px_from_sp(far.y) + 8.0)
    assert tall.pointed(*down_there).selected
    assert indexed() == before + 1
    # In the gap between two blocks nothing is selected, as before.
    gap = (tall.origin[0] + 50.0, tall.origin[1] + px_from_sp(layout.placed[0].bottom) + 2.0)
    assert tall.pointed(*gap) == Pointed(block=None, link=None, selected=False)
    # And the answer is the one the whole selection's rectangles give.
    tall.select(Selection(layout.placed[1].base, layout.placed[2].base + 6))
    for dx, dy in ((50.0, 50.0), (10.0, 8.0), (300.0, 30.0), (20.0, 130.0), (200.0, 160.0)):
        point = tall.document_point(tall.origin[0] + dx, tall.origin[1] + dy)
        assert point is not None
        slow = any(
            rect.x <= point.x < rect.x + rect.width and rect.y <= point.y < rect.y + rect.height
            for rect in layout.model.rects(tall.selection)
        )
        assert tall.pointed(tall.origin[0] + dx, tall.origin[1] + dy).selected == slow


def test_the_selection_can_be_read_after_an_invalidate_and_before_the_next_layout(
    view: BareView,
) -> None:
    # A host's "Copy" menu item can run between its own `invalidate()` and
    # the next `draw`. The selection is still there, in the layout it was
    # made in, and used to read as the empty string.
    imgui = pytest.importorskip("imgui_bundle").imgui
    view.select(Selection(6, 19))
    assert view.selected_text() == "bravo charlie"
    view.invalidate()
    assert view.layout is None
    assert view.selected_text() == "bravo charlie"
    assert view.selected_blocks() == (0,)
    imgui.set_clipboard_text("")
    view.copy()
    assert imgui.get_clipboard_text() == "bravo charlie"
    frame(view)
    assert view.selected_text() == "bravo charlie"


# -- review 4: where the lines are, for a caller that counts them ----------------

LINES_SOURCE = (
    "# A heading\n"
    "\n"
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky.\n"
    "\n"
    "> A quoted paragraph.\n"
    ">\n"
    "> And a second one in the same quote.\n"
    "\n"
    "```\ncode one\n\ncode three\n```\n"
    "\n"
    "| key | value |\n|---|---|\n| one | several words in a cell that wrap when narrow |\n"
    "\n"
    "---\n"
    "\n"
    "- an item\n"
)


def _lines_from_fragments(layout: Any) -> list[tuple[int, tuple[tuple[int, int], ...]]]:
    """
    Each line that holds a glyph, as the selection index has it: baseline, then glyphs.

    The whole-document, index-every-unit way of asking, which is what
    `examples/stream_replay.py` did and what `set_lines` is checked against.
    """
    return [
        (fragment.line.y, glyphs)
        for fragment in layout.model.fragments
        if (
            glyphs := tuple(
                (item.codepoint, item.x) for item in fragment.items if isinstance(item, Glyph)
            )
        )
    ]


@pytest.mark.parametrize("width", [500.0, 260.0])
def test_set_lines_are_the_lines_a_click_lands_on_found_without_indexing_anything(
    bundled_fonts: Any, width: float
) -> None:
    theme = Theme.build()
    view = BareView(
        document=build_document(LINES_SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    assert view.set_lines() == (), "nothing before the first layout"
    layout = view.layout_for(sp_from_px(width))
    lines = view.set_lines()
    assert not any(unit._placement._model is not None for unit in layout.placed)
    assert not any(unit._placement._cmds is not None for unit in layout.placed[1:])
    assert [(line.baseline, line.glyphs) for line in lines] == _lines_from_fragments(layout)
    assert len(lines) >= 10

    # Each line names the block it is a line of, the paragraphs of a quote
    # separately, and a rule has no line.
    kinds = [type(block).__name__ for block in view.document.blocks]
    assert kinds.count("RuleBlock") == 1
    rule = kinds.index("RuleBlock")
    assert sorted({line.block for line in lines}) == [
        number for number in range(len(kinds)) if number != rule
    ]
    for line in lines:
        point = Point(0, line.baseline - 1)
        assert layout.block_at(point) == line.block

    # From a block on: the tail of the same answer, and the units before it
    # are not walked. A range is half-open.
    for first in range(len(kinds) + 2):
        assert view.set_lines(first) == tuple(line for line in lines if line.block >= first)
    assert view.set_lines(2, 4) == tuple(line for line in lines if 2 <= line.block < 4)
    assert view.set_lines(3, 3) == ()


# -- review 5: a drag put down on fill ------------------------------------------

FILL_BEFORE = "First paragraph, short.\n\n- item one\n- item two\n\n  - nested item\n\nLast"
FILL_AFTER = FILL_BEFORE + " paragraph grows a little."


def _two_layouts(before: str, after: str, width_px: float = 500.0) -> tuple[Any, Any]:
    """
    `before` laid out, then `after` laid out over it the way a view does after an edit.
    """
    from advtext.ui.units import UnitCache, layout_units

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    width = sp_from_px(width_px)
    cache = UnitCache()
    old = layout_units(
        build_document(before, theme, fontlib_metrics).blocks, theme, width, measure, units=cache
    )
    new = layout_units(
        build_document(after, theme, fontlib_metrics).blocks,
        theme,
        width,
        measure,
        units=cache,
        previous=old,
    )
    return old, new


def test_a_caret_anywhere_on_a_block_that_did_not_change_is_carried_to_the_same_place(
    bundled_fonts: Any,
) -> None:
    # Review 5, item 1, measured with its snippet A: a caret was carried only
    # by a glyph next to it, so a press right of a paragraph's last line or in
    # a list's gutter -- glue on both sides -- had its drag ended by the next
    # relayout, 198 of 500 press positions on blocks that had not changed. In
    # a stream a relayout is every frame text arrives.
    from advtext.selection import Granularity

    old, new = _two_layouts(FILL_BEFORE, FILL_AFTER)
    unchanged = old.placed[:-1]
    assert len(unchanged) == 4
    assert all(o.unit.cmds is n.unit.cmds for o, n in zip(unchanged, new.placed, strict=False))
    assert old.placed[-1].unit.cmds is not new.placed[-1].unit.cmds
    lost: list[tuple[int, int]] = []
    presses = 0
    on_fill = 0
    for unit, twin in zip(unchanged, new.placed, strict=False):
        for px in range(0, 500, 4):
            point = Point(sp_from_px(float(px)), unit.y + unit.height // 2)
            anchor = old.model.select_at(point, point, Granularity.CHARACTER)
            assert anchor.is_empty
            presses += 1
            glyph_beside = any(
                isinstance(cmd, Glyph) and unit.base + cmd.index in (anchor.start - 1, anchor.start)
                for cmd in unit.unit.cmds
            )
            on_fill += not glyph_beside
            carried = bare_module._carried_anchor(anchor, old, new)
            # Nothing above the edit was renumbered here, so "the same place"
            # is the same integers, and a press there in the new layout is it.
            if carried != new.model.select_at(point, point, Granularity.CHARACTER):
                lost.append((unit.block_start, px))
            assert twin.base == unit.base
    assert on_fill > 100, "the fixture has to press on fill for this to say anything"
    assert lost == [], f"{len(lost)} of {presses} presses lost their anchor"


def test_a_caret_on_fill_is_carried_when_the_units_above_it_were_renumbered(
    bundled_fonts: Any,
) -> None:
    # The unchanged block sits *below* a block that re-broke into another
    # number of items, so its indices all moved: the caret moves with them.
    from advtext.selection import Granularity

    old, new = _two_layouts(
        "Top.\n\nSecond block, short.\n",
        "Top " + "and more words " * 12 + ".\n\nSecond block, short.\n",
    )
    below, twin = old.placed[-1], new.placed[-1]
    assert below.unit.cmds is twin.unit.cmds and below.base != twin.base
    point = Point(sp_from_px(450.0), below.y + below.height // 2)
    anchor = old.model.select_at(point, point, Granularity.CHARACTER)
    carried = bare_module._carried_anchor(anchor, old, new)
    assert carried is not None and carried.is_empty
    assert carried.start - twin.base == anchor.start - below.base
    there = Point(point.x, twin.y + twin.height // 2)
    assert carried == new.model.select_at(there, there, Granularity.CHARACTER)


def test_a_caret_on_fill_of_a_block_that_re_broke_stays_after_the_same_glyph(
    bundled_fonts: Any,
) -> None:
    # Same text, other lines (a pane resized, a stream's block set again):
    # the caret is restated as "after this many of the unit's glyphs".
    from advtext.selection import Granularity
    from advtext.ui.units import UnitCache, layout_units

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    blocks = build_document(WRAPPING, theme, fontlib_metrics).blocks
    cache = UnitCache()
    old = layout_units(blocks, theme, sp_from_px(500.0), measure, units=cache)
    new = layout_units(blocks, theme, sp_from_px(300.0), measure, units=cache, previous=old)
    paragraph, twin = old.placed[-1], new.placed[-1]
    # Far right of the paragraph's last line: parfillskip, nothing else.
    point = Point(sp_from_px(495.0), paragraph.bottom - sp_from_px(4.0))
    anchor = old.model.select_at(point, point, Granularity.CHARACTER)
    glyphs = [cmd for cmd in paragraph.unit.cmds if isinstance(cmd, Glyph)]
    before = sum(1 for glyph in glyphs if paragraph.base + glyph.index < anchor.start)
    assert before == len(glyphs), "the press was meant to land after the last glyph"
    assert not any(paragraph.base + g.index in (anchor.start - 1, anchor.start) for g in glyphs)
    carried = bare_module._carried_anchor(anchor, old, new)
    assert carried is not None and carried.is_empty
    theirs = [cmd for cmd in twin.unit.cmds if isinstance(cmd, Glyph)]
    assert carried.start == twin.base + theirs[-1].index + 1


def test_a_caret_on_fill_of_a_block_whose_text_changed_is_not_carried(
    bundled_fonts: Any,
) -> None:
    # The rule for a relayout is unchanged: the same text, or nothing. A
    # caret after the last glyph of a paragraph that now reads differently
    # *before* the caret has no text to say where it was.
    from advtext.selection import Granularity

    old, new = _two_layouts("Top.\n\nSecond block, short.\n", "Top.\n\nAnother thing, short.\n")
    below = old.placed[-1]
    point = Point(sp_from_px(450.0), below.y + below.height // 2)
    anchor = old.model.select_at(point, point, Granularity.CHARACTER)
    assert bare_module._carried_anchor(anchor, old, new) is None
    # ...and one whose block is gone altogether.
    old, new = _two_layouts("Top.\n\nSecond block, short.\n", "Top.\n")
    assert bare_module._carried_anchor(anchor, old, new) is None


def test_a_drag_begun_right_of_a_short_line_goes_on_while_another_block_grows(
    bundled_fonts: Any,
) -> None:
    # The same thing in real frames, as a streaming host meets it: the button
    # is down on the white right of a settled paragraph while the last block
    # gains words. Before the fix the first relayout ended the drag.
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    view = BareView(
        document=build_document(FILL_BEFORE, theme, fontlib_metrics), theme=theme, measure=measure
    )
    frame(view, mouse=(1190.0, 790.0), left=False, right=False, width_px=500.0)
    frame(view, mouse=(1190.0, 790.0), width_px=500.0)
    assert view.origin is not None and view.layout is not None
    first = view.layout.placed[0]
    press = (view.origin[0] + 420.0, view.origin[1] + px_from_sp(first.y + first.height // 2))
    frame(view, mouse=press, width_px=500.0)
    frame(view, mouse=press, left=True, width_px=500.0)
    assert view._dragging and view.selection.is_empty
    text = FILL_BEFORE
    for word in (" paragraph", " grows", " a", " little."):
        text += word
        view.document = build_document(text, theme, fontlib_metrics)
        view.invalidate()
        frame(view, mouse=press, width_px=500.0)
        assert view._dragging, f"the drag ended when {word!r} arrived"
    below = (press[0], press[1] + 600.0)
    frame(view, mouse=below, width_px=500.0)
    frame(view, mouse=below, width_px=500.0)
    assert view._dragging
    assert view.selected_text().split("\n")[-1] == "Last paragraph grows a little."
    assert "item one" in view.selected_text() and "First" not in view.selected_text()
    frame(view, left=False, width_px=500.0)
    close_popups()


# -- review 5: asking what is under the mouse must not cost the draw anything ---


def test_asking_what_is_under_the_mouse_each_frame_leaves_a_long_units_slice_alone(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review 5, item 2 (its snippet B, which nobody had run: it reproduced,
    # 871 commands moved per frame against 0). A unit too long to move whole
    # keeps the one slice of itself the window last showed. `pointed` asked
    # "is this point on selected text" through `visible_units`, which cut the
    # unit to a band one scaled point tall and overwrote that slice, so with
    # a non-empty selection anywhere a host calling `under_mouse()` per frame
    # (a tooltip) made the next draw move the visible slice again, every frame.
    import advtext.ui.units as units_module

    theme = Theme.build()
    lines = "".join(
        f"value_{n} = compute({n}, other=[x for x in range({n})])\n" for n in range(600)
    )
    view = BareView(
        document=build_document(
            f"Intro paragraph here.\n\n```\n{lines}```\n", theme, fontlib_metrics
        ),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    frame(view, mouse=(1190.0, 790.0), left=False)
    frame(view)
    assert view.origin is not None and view.layout is not None
    over_code = (view.origin[0] + 60.0, view.origin[1] + 300.0)
    view.select(Selection(0, 5))
    moved = [0]
    real = units_module.moved

    def counting(cmds: Any, dy: Any, di: Any) -> Any:
        out = real(cmds, dy, di)
        moved[0] += len(out)
        return out

    monkeypatch.setattr(units_module, "moved", counting)
    frame(view, mouse=over_code)
    frame(view, mouse=over_code)
    big = view.layout.placed[1]
    assert len(big.unit.cmds) > units_module.MOVE_WHOLE_BELOW
    assert big._placement._cmds is None, "fixture: the unit must be drawn by its slice"
    moved[0] = 0
    frame(view, mouse=over_code)
    assert moved[0] == 0, "control: a frame on which nothing changed moves nothing"
    for _ in range(3):
        pointed = view.under_mouse()
        assert pointed == Pointed(block=1, link=None, selected=False)
        frame(view, mouse=over_code)
    assert moved[0] == 0
    # And the answer is still right where the point *is* on selected text.
    on_intro = (view.origin[0] + 4.0, view.origin[1] + 8.0)
    assert view.pointed(*on_intro) == Pointed(block=0, link=None, selected=True)
    close_popups()

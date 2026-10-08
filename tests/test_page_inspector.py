"""
The Inspector page: its facts held to the view's own answers, its reuse count
held to the units a layout really carried over, and the page in frames and in
a window.

Three levels:

1. `Reuse` and `facts_of` over a real `BareView` laid
   out at a width, with no ImGui.
2. The page through `App.gui` in frames of a real `ImGuiContext` with no
   backend: a hover, the outline, a right click and the two menu items, the
   slider's effect.
3. The real app in a real window (`tests/conftest.py::window`): counts the
   page prints, read back here.

**Nothing here judges how the outline or the panel looks.**
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext.markdown import CodeBlock, build_document
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui.app import App
from advtext.ui.bare_view import BareView, Pointed
from advtext.ui.pages import PageContext, discover
from advtext.ui.pages import inspector as page
from advtext.ui.pages.inspector import (
    InspectorPage,
    Reuse,
    facts_of,
    panel_lines,
    readouts,
)
from advtext.units import px_from_sp, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

SAMPLE = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(encoding="utf-8")
WIDTH = sp_from_px(520.0)


@pytest.fixture
def view(bundled_fonts: Any) -> BareView:
    theme = Theme.build()
    return BareView(
        document=build_document(SAMPLE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )


# ----------------------------------------------------------------------
# 1. No ImGui
# ----------------------------------------------------------------------


def test_the_first_layout_is_all_built_and_the_same_layout_is_not_a_relayout(
    view: BareView,
) -> None:
    reuse = Reuse()
    assert not reuse.observe(None) and reuse.relayouts == 0
    layout = view.layout_for(WIDTH)
    assert reuse.observe(layout)
    units = len(layout.placed)
    assert (reuse.relayouts, reuse.last_units, reuse.last_built, reuse.last_reused) == (
        1,
        units,
        units,
        0,
    )
    assert not reuse.observe(view.layout_for(WIDTH))  # the same object: nothing happened
    assert reuse.relayouts == 1
    assert not any(reuse.was_reused(placed) for placed in layout.placed)


def test_a_new_width_builds_every_unit_and_an_edit_builds_one(view: BareView) -> None:
    """
    Held to the view's own cache: what the page calls built is, relayout by
    relayout, exactly the units `UnitCache` shipped (`misses`), read from the
    private counter here and nowhere in the page.
    """
    reuse = Reuse()
    cache = view._units

    def built_by(make: Any) -> tuple[Any, int]:
        before = cache.stats().misses
        layout = make()
        reuse.observe(layout)
        return layout, cache.stats().misses - before

    first, shipped = built_by(lambda: view.layout_for(WIDTH))
    assert reuse.last_built == shipped == len(first.placed)
    second, shipped = built_by(lambda: view.layout_for(sp_from_px(400.0)))
    assert reuse.last_built == shipped > len(second.placed) // 2

    # Back to the first width: the view's cache keeps two passes.
    third, shipped = built_by(lambda: view.layout_for(WIDTH))
    assert reuse.last_built == shipped == 0
    assert all(reuse.was_reused(placed) for placed in third.placed)
    assert not any(reuse.was_reused(placed) for placed in first.placed)  # another layout's

    # One block replaced: one unit built, the rest carried over.
    blocks = list(view.document.blocks)
    target = next(i for i, b in enumerate(blocks) if isinstance(b, CodeBlock))
    other = build_document("```\nsomething else\n```\n", view.theme, fontlib_metrics).blocks[0]
    blocks[target] = other
    view.document = type(view.document)(blocks=tuple(blocks))
    view.invalidate()
    fourth, shipped = built_by(lambda: view.layout_for(WIDTH))
    assert reuse.relayouts == 4
    assert reuse.last_built == shipped == 1 and reuse.last_reused == len(fourth.placed) - 1
    built = [p for p in fourth.placed if not reuse.was_reused(p)]
    assert [p.block_range.start for p in built] == [target]


def test_a_document_parsed_again_is_reported_reused(view: BareView) -> None:
    """
    The defect the page's old count had: every `Unit` of a re-parsed document
    is a new object, and comparing objects called all of them built.
    """
    reuse = Reuse()
    first = view.layout_for(WIDTH)
    reuse.observe(first)
    view.document = build_document(SAMPLE, view.theme, fontlib_metrics)
    view.invalidate()
    again = view.layout_for(WIDTH)
    assert again is not first
    assert any(a.unit is not b.unit for a, b in zip(first.placed, again.placed, strict=True))
    reuse.observe(again)
    assert reuse.last_built == 0 and reuse.last_reused == len(again.placed)


def test_a_long_sweep_of_widths_and_back_is_counted_as_the_cache_did_it(view: BareView) -> None:
    """
    The other one: the page remembered eight layouts and called anything older
    built, whatever the view's cache had done. Now the two cannot differ.
    """
    reuse = Reuse()
    reuse.observe(view.layout_for(WIDTH))
    for step in range(12):
        reuse.observe(view.layout_for(sp_from_px(300.0 + step)))
    before = view._units.stats().misses
    back = view.layout_for(WIDTH)
    reuse.observe(back)
    assert reuse.last_built == view._units.stats().misses - before
    assert reuse.total_built == view._units.stats().misses


def test_a_blocks_rectangle_is_its_own_extent_in_its_unit(view: BareView) -> None:
    layout = view.layout_for(WIDTH)
    for number in range(len(view.document.blocks)):
        reuse = Reuse()
        reuse.observe(layout)
        facts = facts_of(view, SAMPLE, number, reuse)
        assert facts is not None
        x, y, width, height = facts.rect
        assert x == 0.0 and abs(width - 520.0) < 0.01 and height >= 0.0
        unit = layout.unit_of_block(number)
        assert unit is not None
        assert px_from_sp(unit.y) - 0.01 <= y and y + height <= px_from_sp(unit.bottom) + 0.01
    assert view.block_rect(10**6) is None


def test_a_paragraph_inside_a_quote_is_outlined_on_its_own(bundled_fonts: Any) -> None:
    """A quote of two paragraphs is one unit; each paragraph has its own extent in it."""
    theme = Theme.build()
    source = "Before.\n\n> First quoted paragraph.\n>\n> Second quoted paragraph.\n\nAfter.\n"
    view = BareView(
        document=build_document(source, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    layout = view.layout_for(WIDTH)
    reuse = Reuse()
    reuse.observe(layout)
    shared = next(p for p in layout.placed if len(p.block_range) > 1)
    first, second = shared.block_range[0], shared.block_range[1]
    upper = facts_of(view, source, first, reuse)
    facts = facts_of(view, source, second, reuse)
    assert upper is not None and facts is not None
    a, b = upper.rect, facts.rect
    assert a[1] + a[3] <= b[1] + 0.01 and a[3] < px_from_sp(shared.height)
    assert facts is not None and facts.unit_blocks == (first, second + 1)
    assert facts.source is not None and "Second quoted" in facts.source
    assert any("shared by blocks" in line for line in panel_lines(facts))


def test_the_facts_are_the_views_own_answers(view: BareView) -> None:
    reuse = Reuse()
    assert facts_of(view, SAMPLE, 0, reuse) is None  # nothing laid out yet
    layout = view.layout_for(WIDTH)
    reuse.observe(layout)
    kinds = set()
    for number, block in enumerate(view.document.blocks):
        facts = facts_of(view, SAMPLE, number, reuse)
        assert facts is not None and facts.block == number
        own = layout.indices_of_block(number)
        assert facts.indices == (own.start, own.stop)
        assert facts.lines == len(view.set_lines(number, number + 1))
        assert facts.source == view.block_source(number, SAMPLE)
        where = view.source_of(number)
        assert where is not None
        assert facts.source_lines == (where.span.line_start, where.span.line_end)
        assert facts.source is not None and facts.source in SAMPLE
        placed = layout.placed[facts.unit]
        assert number in placed.block_range
        assert facts.unit_blocks == (placed.block_range.start, placed.block_range.stop)
        assert facts.unit_count == 1 and not facts.reused
        assert facts.build_ms == placed.unit.build_seconds * 1000.0 > 0.0
        rect = view.block_rect(number)
        assert rect is not None
        assert facts.rect == tuple(
            px_from_sp(value) for value in (rect.x, rect.y, rect.width, rect.height)
        )
        assert panel_lines(facts)[0] == f"block {number}: {facts.kind}"
        kinds.add(facts.kind)
        del block
    assert {BlockKind.HEADING_1.name, BlockKind.PARAGRAPH.name, BlockKind.CODE.name} <= kinds
    assert BlockKind.TABLE.name in kinds and BlockKind.QUOTE.name in kinds
    assert facts_of(view, SAMPLE, len(view.document.blocks), reuse) is None


def test_the_readout_is_counts() -> None:
    reuse = Reuse(relayouts=3, last_units=40, last_reused=39, last_built=1)
    reuse.total_reused, reuse.total_built = 39, 81
    (line,) = readouts(reuse, 519.6)
    assert "measure 520 px" in line and "relayouts 3" in line
    assert "40 units, 39 reused, 1 built" in line and "39 reused, 81 built" in line


def test_the_page_is_discovered_under_one_word() -> None:
    found = discover().find("inspector")
    assert found is page.PAGE and found.factory is InspectorPage
    assert found.order == 140 and found.group == "Embedding"


# ----------------------------------------------------------------------
# 2. Frames, no display
# ----------------------------------------------------------------------

SIZE = (1300.0, 800.0)
OFF = (5.0, 795.0)


def _imgui() -> Any:
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    return imgui


def _frame(
    app: App,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    right: bool | None = None,
) -> None:
    imgui = _imgui()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    if right is not None:
        io.add_mouse_button_event(1, right)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##advtext-inspector-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
    finally:
        imgui.render()


@pytest.fixture
def shown(bundled_fonts: Any) -> tuple[App, InspectorPage]:
    app = App(source=SAMPLE, open_tab="inspector")
    _frame(app, mouse=OFF, left=False, right=False)
    _frame(app, mouse=OFF)
    made = app.page("inspector")
    assert isinstance(made, InspectorPage)
    yield app, made
    # Close any popup a test left open, so the next test starts clean.
    imgui = _imgui()
    imgui.get_io().add_mouse_button_event(1, False)
    _frame(app, mouse=OFF, left=True)
    _frame(app, mouse=OFF, left=False)


def over(made: InspectorPage, block: int, dx: float = 30.0) -> tuple[float, float]:
    """A screen point inside block `block` as the page last drew it."""
    rect = made.view.block_rect(block)
    assert rect is not None
    screen = made.view.to_screen(rect)
    assert screen is not None
    return (screen[0] + dx, (screen[1] + screen[3]) / 2)


def test_the_page_opens_with_one_relayout_and_nothing_pointed_at(
    shown: tuple[App, InspectorPage],
) -> None:
    _, made = shown
    layout = made.view.layout
    assert layout is not None and made.reuse.relayouts == 1
    assert made.reuse.last_built == len(layout.placed) and made.reuse.last_reused == 0
    assert made.hovered is None and made.block is None and made.facts is None
    assert made.outlined is None and made.menus_opened == 0
    assert made.stats is not None and made.stats.glyphs > 300
    assert abs(px_from_sp(layout.width) - 520.0) < 0.01


def test_hovering_a_block_fills_the_panel_and_outlines_it(
    shown: tuple[App, InspectorPage],
) -> None:
    app, made = shown
    layout = made.view.layout
    assert layout is not None
    target = 0  # the title: near the top, and its source is not its text
    point = over(made, target)
    _frame(app, mouse=point)
    _frame(app, mouse=point)
    assert made.hovered == target == made.block
    facts = made.facts
    assert facts is not None and facts.block == target and facts.kind == "HEADING_1"
    assert facts.source == made.view.block_source(target, SAMPLE)
    assert facts.source is not None and facts.source.startswith("# ")
    assert facts.build_ms > 0.0
    assert not facts.reused  # the page's first layout built everything
    # The outline is the block's rectangle, where the view put the document.
    origin = made.view.origin
    assert origin is not None and made.outlined is not None
    x0, y0, x1, y1 = made.outlined
    assert y0 <= point[1] <= y1 and x0 <= point[0] <= x1
    assert abs((y1 - y0) - (facts.rect[3] + 2.0)) < 0.01
    assert abs(y0 - (origin[1] + facts.rect[1] - 1.0)) < 0.01

    # The mouse leaves: the panel keeps the block, the outline goes.
    _frame(app, mouse=OFF)
    _frame(app, mouse=OFF)
    assert made.hovered is None and made.block == target and made.outlined is None
    assert made.facts is facts  # and nothing was worked out again


def test_the_facts_are_not_worked_out_again_on_a_frame_where_nothing_changed(
    shown: tuple[App, InspectorPage], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, made = shown
    calls: list[int] = []
    real = page.facts_of

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(page, "facts_of", counted)
    point = over(made, 2)
    for _ in range(6):
        _frame(app, mouse=point)
    assert made.block == 2 and len(calls) == 1
    other = over(made, 4)
    _frame(app, mouse=other)
    _frame(app, mouse=other)
    assert made.block == 4 and len(calls) == 2


def test_the_slider_relays_out_and_the_counts_say_what_was_reused(
    shown: tuple[App, InspectorPage],
) -> None:
    app, made = shown
    units = made.reuse.last_units
    point = over(made, 2)
    _frame(app, mouse=point)
    _frame(app, mouse=point)
    made.set_width(400.0)
    _frame(app, mouse=point)
    layout = made.view.layout
    assert layout is not None and abs(px_from_sp(layout.width) - 400.0) < 0.01
    assert made.reuse.relayouts == 2 and made.reuse.last_units == units
    assert made.reuse.last_built > units // 2  # a new measure re-breaks the text
    assert made.facts is not None and not made.facts.reused
    built_at_400 = made.reuse.last_built
    made.set_width(520.0)
    _frame(app, mouse=point)
    assert made.reuse.relayouts == 3
    assert made.reuse.last_reused == units and made.reuse.last_built == 0
    assert made.facts is not None and made.facts.reused
    made.set_width(400.0)
    _frame(app, mouse=point)
    assert made.reuse.last_reused == units
    assert made.reuse.total_built == units + built_at_400
    # A measure wider than the pane is held to the pane.
    made.set_width(5000.0)
    _frame(app, mouse=OFF)
    layout = made.view.layout
    assert layout is not None
    assert abs(px_from_sp(layout.width) - made.max_width_px) < 0.01 < made.max_width_px


def test_a_right_click_opens_the_pages_menu_and_both_items_copy(
    shown: tuple[App, InspectorPage],
) -> None:
    app, made = shown
    imgui = _imgui()
    imgui.set_clipboard_text("sentinel")
    target = 0
    point = over(made, target)
    _frame(app, mouse=point)
    _frame(app, mouse=point)
    # Idle, over the text: the view has no item, so nothing blocks the menu.
    assert made.menus_opened == 0
    _frame(app, mouse=point, right=True)
    _frame(app, mouse=point, right=False)
    _frame(app, mouse=point)
    assert made.menus_opened == 1
    assert made.menu == Pointed(block=target, link=None, selected=False)
    assert made.view.selection.is_empty  # a right click selected nothing

    # What the two items do, called as the menu calls them.
    text = made.copy_text(made.menu)
    assert text == made.view.block_text(target) and not text.startswith("#")
    assert imgui.get_clipboard_text() == text and made.copied == ("text", text)
    markdown = made.copy_markdown(made.menu)
    assert markdown == made.view.block_source(target, SAMPLE) and markdown.startswith("# ")
    assert imgui.get_clipboard_text() == markdown and made.copied == ("markdown", markdown)


def test_a_right_click_on_the_selection_makes_the_menu_about_the_selection(
    shown: tuple[App, InspectorPage],
) -> None:
    app, made = shown
    imgui = _imgui()
    made.view.select_all()
    _frame(app, mouse=OFF)
    point = over(made, 2)
    _frame(app, mouse=point)
    _frame(app, mouse=point, right=True)
    _frame(app, mouse=point, right=False)
    assert made.menu is not None and made.menu.selected and made.menus_opened == 1
    assert made.copy_text(made.menu) == made.view.selected_text()
    assert made.copy_markdown(made.menu) == made.view.selected_source(SAMPLE)
    assert imgui.get_clipboard_text() == made.view.selected_source(SAMPLE)
    assert len(made.view.selected_text()) > 1000  # still everything: the click kept it


def test_a_menu_item_clicked_in_the_popup_copies(shown: tuple[App, InspectorPage]) -> None:
    """The real `menu_item`, clicked: found through the popup window ImGui made."""
    app, made = shown
    imgui = _imgui()
    imgui.set_clipboard_text("sentinel")
    point = over(made, 2)
    _frame(app, mouse=point)
    _frame(app, mouse=point, right=True)
    _frame(app, mouse=point, right=False)
    _frame(app, mouse=point)
    assert made.menus_opened == 1
    # The popup opens at the mouse; its first item is a few pixels in.
    first = (point[0] + 20.0, point[1] + 16.0)
    _frame(app, mouse=first)
    _frame(app, mouse=first, left=True)
    _frame(app, mouse=first, left=False)
    _frame(app, mouse=first)
    assert made.copied is not None and made.copied[0] == "text"
    assert made.copied[1] == made.view.block_text(2) == imgui.get_clipboard_text()


def test_the_report_is_one_line_of_counts(shown: tuple[App, InspectorPage]) -> None:
    app, made = shown
    point = over(made, 3)
    _frame(app, mouse=point)
    _frame(app, mouse=point)
    (line,) = made.report()
    got = dict(part.split("=", 1) for part in line.split())
    assert got["hovered"] == got["block"] == "3" and got["outlined"] == "1"
    assert got["relayouts"] == "1" and got["missing"] == "0" and int(got["glyphs"]) > 300
    assert got["blocks"] == str(len(made.view.document.blocks))


def test_without_the_demo_file_the_page_still_has_a_document(
    bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = InspectorPage(PageContext.build())
    assert made.source == page.FALLBACK and len(made.view.document.blocks) >= 5


# ----------------------------------------------------------------------
# 3. A real window
# ----------------------------------------------------------------------

WINDOWED = """
from imgui_bundle import hello_imgui, imgui

from advtext.ui import app as advtext_app

state = {"frames": 0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    made = self.page("inspector")
    frame = state["frames"]
    io = imgui.get_io()
    if frame >= 4 and made.view.origin is not None:
        block = 2 + (frame // 6) % 4
        left, top, right, bottom = made.view.to_screen(made.view.block_rect(block))
        io.add_mouse_pos_event(left + 40.0, (top + bottom) / 2)
    if frame == 20:
        made.set_width(380.0)
    if frame == 30:
        made.set_width(520.0)
    real_gui(self)
    state["frames"] += 1
    if frame in (16, 24, 34):
        print(made.report()[0])
    if frame == 36:
        hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="inspector")
"""


def test_the_page_runs_in_a_real_window_hovering_and_relaying_out(window: Window) -> None:
    """
    The real app on `--tab inspector`: the mouse walked over four blocks, the
    measure changed and changed back. Counts only: a block was hovered and
    outlined, glyphs were drawn with none missing, the first relayout built
    units and the return to the first measure built none.
    """
    script = window.out / "inspector_page.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
    assert len(lines) == 3, done.stdout
    first, narrow, back = (dict(part.split("=", 1) for part in line.split()) for line in lines)
    for got in (first, narrow, back):
        assert int(got["glyphs"]) > 300 and got["missing"] == "0", done.stdout
        assert got["outlined"] == "1" and int(got["hovered"]) >= 2, done.stdout
        assert got["kind"] != "-" and int(got["lines"]) >= 1, done.stdout
    assert (first["relayouts"], narrow["relayouts"], back["relayouts"]) == ("1", "2", "3")
    assert first["width"] == "520" and narrow["width"] == "380" and back["width"] == "520"
    assert int(narrow["last_built"]) > int(narrow["last_reused"])
    assert back["last_built"] == "0" and back["last_reused"] == first["units"]

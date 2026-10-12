"""
The Inspector page: its facts held to the view's own answers, and the page in
frames and in a window.

Four levels:

1. No ImGui: the panel's lines and the counts line, as text.
2. Frames of a real `ImGuiContext` with no backend, in this process. The
   library is never ready here, so the page is ONE LINE saying why. A fake
   view -- four rows of known height that answers what a `TypesetView`
   answers -- shows what this process can see of the rest: the hover, the
   facts worked out once per change, the outline, the right click and both
   copies through the real popup, the measure, and a view that fails mid-run
   leaving the page alive.
3. With the library, real frames, no window (`test_page_document.typeset_child`;
   skipped with the reason when `IMTYPESET_LIBRARY` is not set): the same
   walk over the real view.
4. The real app in a real window: with the library (asserting in the child
   that it is imported and ready) and without it (the one line, no traceback
   page).

**Nothing here judges how the outline or the panel looks.**
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from test_page_document import (
    VARIABLES,
    WATCH_WITHOUT,
    says_only_why_not,
    typeset_child,
    unasked,
    windowed_typeset,
)

from advtext.ui.pages import PageContext, discover
from advtext.ui.pages import inspector as page
from advtext.ui.pages.inspector import InspectorPage, Target
from advtext.ui.typeset_view import TypesetUnavailable

if TYPE_CHECKING:
    from conftest import Window

assert unasked  # the fixture, imported: `typesetter.module()` fails the test if asked

SIZE = (1300.0, 800.0)
OFF = (5.0, 795.0)


# ----------------------------------------------------------------------
# 1. No ImGui
# ----------------------------------------------------------------------


def test_the_page_is_discovered_under_one_word() -> None:
    found = discover().find("inspector")
    assert found is page.PAGE and found.factory is InspectorPage
    assert found.order == 140 and found.group == "Embedding"


def test_the_panel_and_the_counts_line_are_counts() -> None:
    facts = page.TypesetFacts(
        block=3,
        kind="PARAGRAPH",
        source="Some *words*.\n",
        source_lines=(6, 7),
        characters=11,
        lines=2,
        rect=(0.0, 120.0, 520.0, 61.2),
    )
    assert page.typeset_panel_lines(facts) == (
        "block 3: PARAGRAPH",
        "source lines: 7 to 7",
        "characters: 11",
        "lines set: 2",
        "rectangle: y 120, height 61 px (its full extent)",
    )
    # No line names the renderer: there is one.
    (line,) = page.typeset_readouts(None, None, 520.0, 0)
    assert line == "measure 520 px   edits of the document 0   nothing drawn yet"
    stats = SimpleNamespace(blocks=37, blocks_laid_out=12, blocks_deferred=25)
    (line,) = page.typeset_readouts(None, stats, 399.6, 2)
    assert line == (
        "measure 400 px   edits of the document 2   "
        "blocks 37   laid out so far 12   not reached yet 25"
    )


def test_without_the_demo_file_the_page_still_has_a_document(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = InspectorPage(PageContext.build())
    assert made.source == page.FALLBACK and made.typeset is None and made.view is None


# ----------------------------------------------------------------------
# 2. Frames, no display: one line saying why; the rest over a fake view
# ----------------------------------------------------------------------


def _imgui() -> Any:
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    return imgui


def _frame(
    made: InspectorPage,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    right: bool | None = None,
    draw: Any = None,
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
        try:
            (made.draw if draw is None else draw)()
        finally:
            imgui.end()
    finally:
        imgui.render()


def test_without_the_library_the_page_is_one_line_saying_why(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    `set` is `make test TYPESET=1`'s case in this process: the variable is
    there, no fonts were loaded, and the page must not import the library to
    find that out. No slider, no panel: the line and nothing else.
    """
    for variable in ("unset", "set"):
        for name in VARIABLES:
            monkeypatch.delenv(name, raising=False)
        if variable == "set":
            monkeypatch.setenv(VARIABLES[0], "/somewhere/lib.so")
        made = InspectorPage(PageContext.build())
        assert made.typeset is None and made.view is None
        assert made.renderer == "none" and made.reason
        assert made.lines() == (f"imtypeset is not drawing: {made.reason}",)
        says_only_why_not(made.draw, made.reason)
        assert made.hovered is None and made.facts is None and made.outlined is None
        assert made.report()[0].startswith("frames=1 renderer=none blocks=0 width=520 edits=0 ")
        # The menu's two actions with no view: nothing copied, nothing raised.
        assert made.copy_text(Target(0)) == "" == made.copy_markdown(Target(0, True))
        assert made.copied is None and made.target_under_mouse() == Target(None, False)


class _FakeTypeset:
    """
    What the page reads of a `TypesetView`: four rows `ROW` px tall, one block each.

    `fail` names the call that raises (`"draw"`, `"stats"`, `"block_rect"` or
    `"copy"`) and `fail_at` the draw from which it does.
    """

    ROW = 40.0
    revision = 0
    texts = ("The title", "A paragraph to point at.", "code = 1", "The last one")

    def __init__(
        self, fail_at: int = 10**9, fail: str = "draw", error: Exception | None = None
    ) -> None:
        self.fail_at = fail_at
        self.fail = fail
        self.error = error or TypesetUnavailable("imtypeset failed and is switched off: Error: no")
        self.draws = 0
        self.debug = False
        self.origin: tuple[float, float] | None = None
        self.width = 0.0
        self.selection: Any = None
        self.copies: list[str] = []
        self.rect_calls = 0

    @property
    def height(self) -> float:
        return self.ROW * len(self.texts)

    def _maybe(self, call: str) -> None:
        if self.fail == call and self.draws >= self.fail_at:
            raise self.error

    def draw(self, **kwargs: Any) -> bool:
        imgui = _imgui()
        self.draws += 1
        self._maybe("draw")
        at = imgui.get_cursor_screen_pos()
        self.origin = (float(at.x), float(at.y))
        self.width = float(kwargs["width_px"])
        imgui.dummy(imgui.ImVec2(self.width, self.height))
        return True

    @property
    def stats(self) -> Any:
        self._maybe("stats")
        return SimpleNamespace(
            blocks=len(self.texts),
            blocks_laid_out=len(self.texts),
            blocks_deferred=0,
            whole=True,
            vertices=0,
        )

    def block_under_mouse(self) -> int | None:
        assert self.origin is not None
        mouse = _imgui().get_mouse_pos()
        row = int((mouse.y - self.origin[1]) // self.ROW)
        inside = self.origin[0] <= mouse.x < self.origin[0] + self.width
        return row if inside and 0 <= row < len(self.texts) else None

    @property
    def under_mouse(self) -> Any:
        block = self.block_under_mouse()
        if block is None:
            return None
        return SimpleNamespace(in_block=True, position=(block, 2))

    def block_rect(self, block: int) -> tuple[float, float, float, float]:
        self._maybe("block_rect")
        self.rect_calls += 1
        assert self.origin is not None
        x, y = self.origin
        return (x, y + block * self.ROW, x + self.width, y + (block + 1) * self.ROW)

    def source_of(self, block: int) -> Any:
        return SimpleNamespace(span=SimpleNamespace(line_start=2 * block, line_end=2 * block + 1))

    def block_source(self, block: int, source: str | None = None) -> str:
        return f"source of {block}\n"

    def block_text(self, block: int) -> str:
        return self.texts[block]

    def block_role(self, block: int) -> str:
        return "HEADING_1" if block == 0 else "PARAGRAPH"

    def set_lines(self, first: int, stop: int) -> tuple[object, ...]:
        return (object(),) * (first + 1)

    def selected_text(self) -> str:
        return "the selection, as text"

    def selected_source(self, source: str | None = None) -> str:
        return "the selection, as markdown"

    def copy(self, text: str) -> None:
        self._maybe("copy")
        self.copies.append(text)
        _imgui().set_clipboard_text(text)


def _on_a_fake_view(**failing: Any) -> tuple[InspectorPage, _FakeTypeset]:
    """
    The page as it is built with the library, over the fake, after two frames.
    """
    made = InspectorPage(PageContext.build())
    fake = _FakeTypeset(**failing)
    made.typeset, made.reason = fake, ""  # type: ignore[assignment]
    _frame(made, mouse=OFF, left=False, right=False)
    if fake.fail_at > 1:
        _frame(made, mouse=OFF)
    return made, fake


def over(fake: _FakeTypeset, block: int, dx: float = 30.0) -> tuple[float, float]:
    """A screen point inside row `block` of the fake as it was last drawn."""
    assert fake.origin is not None
    return (fake.origin[0] + dx, fake.origin[1] + (block + 0.5) * fake.ROW)


@pytest.fixture
def shown(unasked: None) -> Any:
    made, fake = _on_a_fake_view()
    yield made, fake
    # Close any popup a test left open, so the next test starts clean.
    _imgui().get_io().add_mouse_button_event(1, False)
    _frame(made, mouse=OFF, left=True)
    _frame(made, mouse=OFF, left=False)


def test_the_page_opens_with_nothing_pointed_at(shown: tuple[InspectorPage, _FakeTypeset]) -> None:
    made, fake = shown
    assert made.renderer == "TypesetView" and made.view is fake and fake.draws == 2
    assert made.hovered is None and made.block is None and made.facts is None
    assert made.outlined is None and made.menus_opened == 0
    assert fake.width == 520.0, "the view is given the measure the slider is on"
    assert made.lines() == (
        "measure 520 px   edits of the document 0   "
        "blocks 4   laid out so far 4   not reached yet 0",
    )


def test_hovering_a_block_fills_the_panel_and_outlines_it(
    shown: tuple[InspectorPage, _FakeTypeset],
) -> None:
    made, fake = shown
    point = over(fake, 0)
    _frame(made, mouse=point)
    _frame(made, mouse=point)
    assert made.hovered == 0 == made.block
    facts = made.facts
    assert facts is not None and facts.block == 0 and facts.kind == "HEADING_1"
    # The facts are the view's own answers.
    assert facts.source == fake.block_source(0) and facts.source_lines == (0, 1)
    assert facts.characters == len(fake.texts[0]) and facts.lines == 1
    assert facts.rect == (0.0, 0.0, 520.0, fake.ROW)
    # The outline is the block's rectangle, where the view put it: 3 px and 1 px out.
    left, top, right, bottom = fake.block_rect(0)
    assert made.outlined == (left - 3.0, top - 1.0, right + 3.0, bottom + 1.0)

    # The mouse leaves: the panel keeps the block, the outline goes.
    _frame(made, mouse=OFF)
    _frame(made, mouse=OFF)
    assert made.hovered is None and made.block == 0 and made.outlined is None
    assert made.facts is facts  # and nothing was worked out again


def test_the_facts_are_not_worked_out_again_on_a_frame_where_nothing_changed(
    shown: tuple[InspectorPage, _FakeTypeset], monkeypatch: pytest.MonkeyPatch
) -> None:
    made, fake = shown
    calls: list[int] = []
    real = page.typeset_facts_of

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(page, "typeset_facts_of", counted)
    point = over(fake, 2)
    for _ in range(6):
        _frame(made, mouse=point)
    assert made.block == 2 and len(calls) == 1
    other = over(fake, 3)
    _frame(made, mouse=other)
    _frame(made, mouse=other)
    assert made.block == 3 and len(calls) == 2
    # An edit of the document is a change too: the facts are worked out again.
    fake.revision = 1  # type: ignore[misc]
    _frame(made, mouse=other)
    assert len(calls) == 3 and made.edits == 1


def test_the_slider_gives_the_view_the_measure_and_the_facts_follow(
    shown: tuple[InspectorPage, _FakeTypeset],
) -> None:
    made, fake = shown
    point = over(fake, 1)
    _frame(made, mouse=point)
    _frame(made, mouse=point)
    wide = made.facts
    assert wide is not None and wide.rect[2] == 520.0
    made.set_width(400.0)
    _frame(made, mouse=point)
    assert fake.width == 400.0
    narrow = made.facts
    assert narrow is not None and narrow is not wide and narrow.rect[2] == 400.0
    assert made.lines()[0].startswith("measure 400 px")
    # A measure wider than the pane is held to the pane.
    made.set_width(5000.0)
    _frame(made, mouse=OFF)
    assert fake.width == made.max_width_px and 520.0 < made.max_width_px < SIZE[0]
    made.set_width(1.0)
    assert made.width_px >= 80.0, "and one narrower than a view can be set to is held too"


def test_a_right_click_opens_the_pages_menu_and_both_items_copy(
    shown: tuple[InspectorPage, _FakeTypeset],
) -> None:
    made, fake = shown
    imgui = _imgui()
    imgui.set_clipboard_text("sentinel")
    point = over(fake, 0)
    _frame(made, mouse=point)
    _frame(made, mouse=point)
    assert made.menus_opened == 0
    _frame(made, mouse=point, right=True)
    _frame(made, mouse=point, right=False)
    _frame(made, mouse=point)
    assert made.menus_opened == 1
    assert made.menu == Target(block=0, selected=False)

    # What the two items do, called as the menu calls them.
    text = made.copy_text(made.menu)
    assert text == fake.texts[0]
    assert imgui.get_clipboard_text() == text and made.copied == ("text", text)
    markdown = made.copy_markdown(made.menu)
    assert markdown == fake.block_source(0)
    assert imgui.get_clipboard_text() == markdown and made.copied == ("markdown", markdown)


def test_a_right_click_on_the_selection_makes_the_menu_about_the_selection(
    shown: tuple[InspectorPage, _FakeTypeset],
) -> None:
    made, fake = shown
    fake.selection = ((1, 0), (2, 5))
    for block, selected in ((2, True), (3, False), (0, False)):
        point = over(fake, block)
        _frame(made, mouse=point)
        _frame(made, mouse=point, right=True)
        _frame(made, mouse=point, right=False)
        assert made.menu == Target(block, selected)
        _frame(made, mouse=OFF, left=True)  # close the popup
        _frame(made, mouse=OFF, left=False)
    assert made.menus_opened == 3
    assert made.copy_text(Target(2, True)) == fake.selected_text()
    assert made.copy_markdown(Target(2, True)) == fake.selected_source()
    assert _imgui().get_clipboard_text() == fake.selected_source()


def test_a_menu_item_clicked_in_the_popup_copies(
    shown: tuple[InspectorPage, _FakeTypeset],
) -> None:
    """The real `menu_item`, clicked: found through the popup window ImGui made."""
    made, fake = shown
    imgui = _imgui()
    imgui.set_clipboard_text("sentinel")
    point = over(fake, 2)
    _frame(made, mouse=point)
    _frame(made, mouse=point, right=True)
    _frame(made, mouse=point, right=False)
    _frame(made, mouse=point)
    assert made.menus_opened == 1
    # The popup opens at the mouse; its first item is a few pixels in.
    first = (point[0] + 20.0, point[1] + 16.0)
    _frame(made, mouse=first)
    _frame(made, mouse=first, left=True)
    _frame(made, mouse=first, left=False)
    _frame(made, mouse=first)
    assert made.copied == ("text", fake.texts[2])
    assert fake.copies == [fake.texts[2]] and imgui.get_clipboard_text() == fake.texts[2]


def test_the_report_is_one_line_of_counts(shown: tuple[InspectorPage, _FakeTypeset]) -> None:
    made, fake = shown
    point = over(fake, 3)
    _frame(made, mouse=point)
    _frame(made, mouse=point)
    (line,) = made.report()
    got = dict(part.split("=", 1) for part in line.split())
    assert got["renderer"] == "TypesetView" and got["blocks"] == "4" and got["width"] == "520"
    assert got["hovered"] == got["block"] == "3" and got["outlined"] == "1"
    assert got["kind"] == "PARAGRAPH" and got["lines"] == "4" and got["edits"] == "0"
    assert got["laid_out"] == "4" and got["deferred"] == "0" and got["whole"] == "1"


@pytest.mark.parametrize("call", ["draw", "stats", "block_rect", "copy"])
def test_a_typeset_view_that_fails_mid_run_leaves_the_page_alive_and_saying_why(
    call: str, unasked: None
) -> None:
    """
    `TypesetUnavailable` out of ANY view call of a frame -- the draw, the
    counts, the facts and the outline, a copy from the real popup -- does not
    leave `draw` (so it cannot reach the app's traceback page), and from the
    next frame on the page is the one line. What was pointed at goes with the
    view: block numbers were its document's.
    """
    made, fake = _on_a_fake_view()
    point = over(fake, 2)
    if call == "copy":
        # Open the real popup and click its first item on the frame that fails.
        _frame(made, mouse=point)
        _frame(made, mouse=point, right=True)
        _frame(made, mouse=point, right=False)
        _frame(made, mouse=point)
        item = (point[0] + 20.0, point[1] + 16.0)
        _frame(made, mouse=item)
        _frame(made, mouse=item, left=True)
        fake.fail, fake.fail_at = call, fake.draws + 1
        _frame(made, mouse=item, left=False)
    else:
        fake.fail, fake.fail_at = call, fake.draws + 1
        _frame(made, mouse=point)
    assert made.typeset is None and made.view is None and made.renderer == "none"
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    assert made.block is None and made.hovered is None and made.facts is None
    assert made.menu is None and made.outlined is None and made.view_stats is None
    assert fake.copies == []
    _frame(made, mouse=OFF, left=False, right=False)
    draws = fake.draws
    says_only_why_not(made.draw, made.reason)
    assert fake.draws == draws and "renderer=none" in made.report()[0]


def test_an_exception_that_is_not_the_librarys_is_a_bug_and_propagates(unasked: None) -> None:
    made, fake = _on_a_fake_view()
    fake.fail, fake.fail_at, fake.error = "block_rect", fake.draws + 1, ZeroDivisionError("a bug")
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    _frame(made, mouse=over(fake, 1), draw=draw)  # the frame still closes: the pane was ended
    assert len(raised) == 1 and made.typeset is fake and made.renderer == "TypesetView"


# ----------------------------------------------------------------------
# 3. With the library, real frames, no window
# ----------------------------------------------------------------------

_TYPESET = r"""
import dataclasses
from advtext.ui.pages import inspector as page

SAMPLE = open("demo/sample.md", encoding="utf-8").read()
OFF = (5.0, 795.0)
app = App(source=SAMPLE, open_tab="inspector")


def step(at=None, left=None, right=None, count=1):
    if at is not None:
        mouse(*at)
    if left is not None:
        io.add_mouse_button_event(0, left)
    if right is not None:
        io.add_mouse_button_event(1, right)
    frame(app.gui, count)


def over(block, dx=30.0):
    left, top, right, bottom = view.block_rect(block)
    return (left + dx, (top + bottom) / 2)


step(OFF, False, False)
step(OFF)
made = app._views["Inspector"]
view = made.typeset
report["renderer"] = made.renderer
report["open"] = [made.hovered, made.block, made.facts is None, made.outlined, made.menus_opened]
report["lines"] = list(made.lines())
report["stats"] = made.view_stats._asdict()
report["blocks"] = len(view.texts)

# Hover the title: the facts are the view's own answers, and the outline is its rectangle.
calls = []
real = page.typeset_facts_of
page.typeset_facts_of = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
point = over(0)
step(point, count=2)
facts = made.facts
rect = view.block_rect(0)
report["hover"] = {
    "hovered": made.hovered, "block": made.block, "facts": dataclasses.asdict(facts),
    "kind": view.block_role(0), "source": view.block_source(0),
    "lines": len(view.set_lines(0, 1)), "characters": len(view.texts[0]),
    "outlined": list(made.outlined), "rect": list(rect), "origin": list(view.origin),
    "point": list(point), "panel": list(page.typeset_panel_lines(facts)),
}
step(OFF, count=2)
report["left"] = [made.hovered, made.block, made.outlined, made.facts is facts]

# Six frames over one block work the facts out once; another block, once more.
calls.clear()
point = over(2)
step(point, count=6)
first = len(calls)
other = over(4)
step(other, count=2)
report["facts_calls"] = [first, len(calls), made.block]

# The measure: a narrower one sets a paragraph on more lines, and is laid out again.
point = over(3)
step(point, count=2)
wide = [made.facts.lines, made.view_stats.blocks_laid_out]
made.set_width(400.0)
step(over(3), count=2)
step(over(3), count=2)
narrow = [made.facts.lines, made.view_stats.blocks_laid_out, made.hovered,
          max(line.right for line in view.set_lines(3, 4))]
made.set_width(520.0)
step(over(3), count=2)
step(over(3), count=2)
report["measure"] = {"wide": wide, "narrow": narrow,
                     "back": [made.facts.lines, made.view_stats.blocks_laid_out],
                     "edits": dict(view.edits), "page_edits": made.edits}
made.set_width(5000.0)
step(OFF, count=2)
report["held"] = [made.max_width_px, max(line.right for line in view.set_lines(3, 4))]
made.set_width(520.0)
step(OFF, count=2)

# A right click opens the page's menu; both items copy.
imgui.set_clipboard_text("sentinel")
point = over(0)
step(point, count=2)
before = made.menus_opened
step(point, right=True)
step(point, right=False)
step(point)
menu = made.menu
text = made.copy_text(menu)
clip_text = imgui.get_clipboard_text()
markdown = made.copy_markdown(menu)
report["menu"] = {
    "opened": [before, made.menus_opened], "target": list(menu), "selection": view.selection,
    "text": text, "block_text": view.block_text(0), "clip_text": clip_text,
    "markdown": markdown, "block_source": view.block_source(0),
    "clip_markdown": imgui.get_clipboard_text(), "copied": list(made.copied),
}
step(OFF, left=True)
step(OFF, left=False)

# A right click on the selection makes the menu about the selection.
view.select_all()
step(OFF)
point = over(2)
step(point)
step(point, right=True)
step(point, right=False)
menu = made.menu
report["selected"] = {
    "target": list(menu), "text": made.copy_text(menu) == view.selected_text(),
    "markdown": made.copy_markdown(menu) == view.selected_source(),
    "clip": imgui.get_clipboard_text() == view.selected_source(),
    "length": len(view.selected_text()), "source_length": len(view.selected_source()),
    "whole_source": len(SAMPLE),
}
step(OFF, left=True)
step(OFF, left=False)
view.clear_selection()

# The real menu item, clicked in the popup ImGui made.
imgui.set_clipboard_text("sentinel")
point = over(2)
step(point)
step(point, right=True)
step(point, right=False)
step(point)
item = (point[0] + 20.0, point[1] + 16.0)
step(item)
step(item, left=True)
step(item, left=False)
step(item)
report["clicked"] = [list(made.copied), view.block_text(2), imgui.get_clipboard_text()]
step(OFF, left=True)
step(OFF, left=False)

point = over(3)
step(point, count=2)
report["report"] = fields(made.report()[0])

# The debug overlay is the shared flag.
made.context.debug = True
step(OFF, count=2)
report["debug"] = view.debug
made.context.debug = False

# The library switched off under the page, a block hovered: it stays alive, what
# was pointed at goes, and it is one line saying why.
point = over(3)
step(point, count=2)
pointed = [made.hovered, made.block, made.facts is not None, made.outlined is not None]
switch_off("switched off by the test")
step(point)
report["after"] = [made.renderer, made.reason, made.typeset is None, made.view is None,
                   pointed, [made.hovered, made.block, made.facts, made.outlined, made.menu],
                   dict(app.page_errors)]
step(OFF, count=2)
report["later"] = [made.renderer, dict(app.page_errors), list(made.lines()), made.reason,
                   only_the_line(made.draw, made.reason)]
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    return typeset_child(_TYPESET)


def test_with_the_library_the_page_opens_on_the_typeset_view_with_nothing_pointed_at(
    typeset: dict[str, Any],
) -> None:
    assert typeset["renderer"] == "TypesetView"
    assert typeset["open"] == [None, None, True, None, 0]
    # One line, and it does not name the renderer: there is one.
    (line,) = typeset["lines"]
    assert line.startswith("measure 520 px   edits of the document 0   blocks ")
    stats = typeset["stats"]
    assert stats["whole"] is True and stats["vertices"] > 1000
    assert stats["blocks"] == typeset["blocks"] > 10
    # The library lays out what the window shows: fewer than all, more than none.
    assert 0 < stats["blocks_laid_out"] < stats["blocks"]
    assert stats["blocks_deferred"] == stats["blocks"] - stats["blocks_laid_out"]


def test_with_the_library_hovering_a_block_fills_the_panel_and_outlines_it(
    typeset: dict[str, Any],
) -> None:
    hover = typeset["hover"]
    facts = hover["facts"]
    assert hover["hovered"] == hover["block"] == facts["block"] == 0
    # The facts are the view's own answers.
    assert facts["kind"] == hover["kind"] == "HEADING_1"
    assert facts["source"] == hover["source"] and facts["source"].startswith("# ")
    assert facts["source_lines"] == [0, 1]
    assert facts["lines"] == hover["lines"] >= 1 and facts["characters"] == hover["characters"] > 0
    assert hover["panel"][0] == "block 0: HEADING_1" and hover["panel"][1] == "source lines: 1 to 1"
    # The outline is the block's full extent on screen, 3 px and 1 px out.
    left, top, right, bottom = hover["rect"]
    assert hover["outlined"] == [left - 3.0, top - 1.0, right + 3.0, bottom + 1.0]
    x, y = hover["point"]
    assert left <= x <= right and top <= y <= bottom
    # And the facts' rectangle is that one, from the document's corner.
    ox, oy = hover["origin"]
    fx, fy, width, height = facts["rect"]
    assert [ox + fx, oy + fy, ox + fx + width, oy + fy + height] == pytest.approx(hover["rect"])
    # The mouse leaves: the panel keeps the block, the outline goes, nothing is worked out again.
    assert typeset["left"] == [None, 0, None, True]
    assert typeset["facts_calls"] == [1, 2, 4]


def test_with_the_library_the_measure_slider_sets_the_text_again(
    typeset: dict[str, Any],
) -> None:
    """
    What replaces "relayouts, reused, built": the library's counter of blocks
    laid out goes up when the measure changes (it lays out again what the
    window shows) and in BOTH directions. Nothing is carried over.
    """
    measure = typeset["measure"]
    wide_lines, wide_laid = measure["wide"]
    narrow_lines, narrow_laid, hovered, right = measure["narrow"]
    back_lines, back_laid = measure["back"]
    assert narrow_lines > wide_lines == back_lines > 1 and hovered == 3
    assert right == pytest.approx(400.0, abs=1.0), "a justified line ends at the measure"
    assert narrow_laid > wide_laid and back_laid > narrow_laid
    # A new measure is a layout, not an edit: the document was handed over once.
    assert measure["edits"] == {"set": 1, "replace": 0, "append": 0} and measure["page_edits"] == 0
    # A measure wider than the pane is held to the pane.
    max_width, widest = typeset["held"]
    assert 520.0 < max_width and widest == pytest.approx(max_width, abs=1.0)


def test_with_the_library_a_right_click_opens_the_menu_and_both_items_copy(
    typeset: dict[str, Any],
) -> None:
    menu = typeset["menu"]
    assert menu["opened"] == [0, 1] and menu["target"] == [0, False]
    assert menu["selection"] is None, "a right click selected nothing"
    assert menu["text"] == menu["block_text"] == menu["clip_text"]
    assert not menu["text"].startswith("#")
    assert menu["markdown"] == menu["block_source"] == menu["clip_markdown"]
    assert menu["markdown"].startswith("# ") and menu["copied"] == ["markdown", menu["markdown"]]

    selected = typeset["selected"]
    assert selected["target"] == [2, True]
    assert selected["text"] and selected["markdown"] and selected["clip"]
    assert selected["length"] > 1000
    # Everything selected: every block's source, so nearly the whole file.
    assert selected["source_length"] > 0.9 * selected["whole_source"]

    copied, block_text, clipboard = typeset["clicked"]
    assert copied == ["text", block_text] and clipboard == block_text


def test_with_the_library_the_report_and_the_switch_off(typeset: dict[str, Any]) -> None:
    got = typeset["report"]
    assert got["renderer"] == "TypesetView" and got["hovered"] == got["block"] == "3"
    assert got["outlined"] == "1" and got["kind"] != "-" and int(got["lines"]) >= 1
    assert got["blocks"] == str(typeset["blocks"]) and got["whole"] == "1"
    assert got["edits"] == "0" and int(got["vertices"]) > 1000
    assert typeset["debug"] is True
    renderer, reason, dropped, no_view, pointed, after, errors = typeset["after"]
    assert (renderer, dropped, no_view, errors) == ("none", True, True, {})
    assert "switched off by the test" in reason
    assert pointed == [3, 3, True, True] and after == [None, None, None, None, None]
    renderer, errors, lines, reason, (drawn, line) = typeset["later"]
    assert (renderer, errors) == ("none", {})
    assert lines == [f"imtypeset is not drawing: {reason}"]
    assert drawn == line > 0, "the page is the one line and nothing else"


# ----------------------------------------------------------------------
# 4. The real app in a real window, with the library and without it
# ----------------------------------------------------------------------

_WATCH = r"""
def watch(app, made, frame):
    view = made.typeset
    if view is not None and view.origin is not None:
        block = 2 + (frame // 6) % 4
        left, top, right, bottom = view.block_rect(block)
        imgui.get_io().add_mouse_pos_event(left + 40.0, (top + bottom) / 2)
    if frame == 20:
        made.set_width(380.0)
    if frame == 30:
        made.set_width(520.0)
    if frame in (16, 26, 36):
        report.setdefault("text", []).append(made.report()[0])
    if frame == 36:
        report["renderer"] = made.renderer
        finish()
"""


def test_in_a_real_window_with_the_library_the_typeset_path_hovers_and_sets_again(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = windowed_typeset(window, monkeypatch, "inspector", _WATCH)
    assert report["current"] == "Inspector" and report["reason"] == ""
    assert report["renderer"] == "TypesetView" and report["trouble"] == ""
    first, narrow, back = (
        dict(part.split("=", 1) for part in line.split()) for line in report["text"]
    )
    for got in (first, narrow, back):
        assert got["renderer"] == "TypesetView" and got["whole"] == "1", report["text"]
        assert int(got["vertices"]) > 1000, report["text"]
        assert got["outlined"] == "1" and int(got["hovered"]) >= 2, report["text"]
        assert got["kind"] != "-" and int(got["lines"]) >= 1, report["text"]
    assert (first["width"], narrow["width"], back["width"]) == ("520", "380", "520")
    assert int(first["laid_out"]) < int(narrow["laid_out"]) < int(back["laid_out"])


def test_in_a_real_window_without_the_library_the_page_says_why_and_stays_up(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The plain gate's window: no view and a reason, the library never imported,
    nothing on the traceback page.
    """
    report = windowed_typeset(window, monkeypatch, "inspector", WATCH_WITHOUT, how="without")
    assert report["current"] == "Inspector" and report["reason"]
    assert report["renderer"] == "none" and report["typeset"] is True
    got = dict(part.split("=", 1) for part in report["text"][0].split())
    assert got["renderer"] == "none" and got["blocks"] == "0" and got["outlined"] == "0"

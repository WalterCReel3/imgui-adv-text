r"""
The Inspector page: point at a block and read what the view knows about it.

A document on the left, and on the right, for the block under the pointer:
its role, the markdown it came from, how long its text is, how many lines the
library set it on and where it is. The hovered block is outlined. A right
click opens a menu with *Copy as text* and *Copy as markdown*. A slider
changes the measure, so that the text is set again.

**Everything here goes through the view's public surface, and that is the
point of the page.** The view draws no outline and opens no menu. It says
which block is under the mouse (`block_under_mouse`), what the library hit
there (`under_mouse`), where the block's source is (`block_source`,
`source_of`), what a copy of it would be (`block_text`, `selected_text`,
`selected_source`), and where it sits (`block_rect`, `origin`); the page
draws the rectangle and owns the popup (`begin_popup_context_item` with an ID
of the page's, straight after `draw`).

Nothing here judges how the outline or the panel looks.

## What draws

An `advtext.ui.typeset_view.TypesetView` fed the markdown SOURCE. There is no
other renderer. The view is made once, when the page is built, if
`advtext.typesetter.ready()` (the app's font callback loaded the library's
fonts). When it is not, the page draws ONE wrapped line saying why
(`advtext.ui.pages.typeset.why_not`, drawn by that module's `say_why_not`) and
nothing else: no slider, no panel. A view call that raises
`TypesetUnavailable` anywhere in a frame -- the draw, the menu's copies, the
facts, the outline -- has drawn no text: the page drops the view and what was
pointed at, keeps the sentence, and is that one line from the next frame on.
The exception does not leave `draw`, so the app's traceback page is not
reached; any other exception is a bug and is not caught.

`InspectorPage.renderer` is `"TypesetView"` while there is a view and
`"none"` when there is not; `reason` is then why.

Nothing of the old layout core or the old views is imported by this module,
at import or later.

## The panel and the counts line

The panel is `TypesetFacts`, read from the view's source map and from the
library:

| the panel says | from |
|---|---|
| role | `block_role` |
| source, source lines | `block_source`, `source_of` |
| characters: the length of the block's text | `block_text` |
| lines the library set | `len(set_lines(n, n + 1))` |
| rectangle: the block's FULL extent, space above and below included | `block_rect` |

There are no layout units on this side, nothing is carried over from one
layout to the next by this side, and the library times nothing, so the panel
says nothing about any of the three.

The counts line is the view's own (`typeset_readouts`): edits of the
document, blocks in it, blocks the library has laid out so far (a counter
that only goes up: a new measure lays out again what the window shows) and
blocks it has not reached. One more call into the library a frame, for that.
The outline is the block's full extent, its own spacing included. The menu's
target is the library's hit under the right click: "on the selection" is the
hit's position lying inside the selected range, which at a line's end or
between two lines is the nearest caret and not the glyph under the point.
*Copy as markdown* of a selection is `TypesetView.selected_source`, which
takes every block between the first and the last selected, a rule included.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

from advtext import typesetter
from advtext.ui.ownership import MIN_WIDTH_PX
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.palette import DARK_PALETTE, rgba
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView

__all__ = [
    "PAGE",
    "InspectorPage",
    "Target",
    "TypesetFacts",
    "typeset_facts_of",
    "typeset_panel_lines",
    "typeset_readouts",
]

FALLBACK = (
    "# Inspector\n\nA paragraph to point at, with enough words in it to be set on "
    "more than one line at any measure this page offers.\n\n"
    "> A quote, which is one unit\n>\n> of two paragraphs.\n\n"
    "```\ncode = 1\n```\n\n- an item\n- another\n"
)
"""What the page shows when `demo/sample.md` is not there (an installed wheel)."""

PANEL_WIDTH_PX = 372.0
DEFAULT_WIDTH_PX = 520.0
OUTLINE = rgba(0xF5, 0x9E, 0x0B)
"""The outline of the hovered block. The page's colour: the view draws no outline."""

MENU_ID = "##advtext-inspector-menu"


class Target(NamedTuple):
    """
    What a context menu is about: a block, and whether the click was on the selection.

    What is under the mouse is the library's hit; these are the two things
    the menu reads of it.
    """

    block: int | None
    selected: bool = False


@dataclass(frozen=True, slots=True)
class TypesetFacts:
    """What the panel says about one block. The module docstring has the map."""

    block: int
    kind: str
    source: str | None
    source_lines: tuple[int, int] | None
    """`[first, stop)` lines of the markdown, zero-based."""
    characters: int
    """The length of the block's text as the library holds it."""
    lines: int
    """Lines the library set the block on at the last layout."""
    rect: tuple[float, ...]
    """`(x, y, width, height)` in pixels from the document's top-left: the block's full extent."""


def typeset_facts_of(view: Any, block: int) -> TypesetFacts | None:
    """
    The facts for block `block` of a `TypesetView` as last drawn, or `None`.

    Two calls into the library for the block (its rectangle and its
    geometry) and one for each of its lines; the page asks when the block or
    the layout changed, not every frame.
    """
    if not 0 <= block < len(view.texts) or view.origin is None:
        return None
    rect = view.block_rect(block)
    if rect is None:
        return None
    where = view.source_of(block)
    x, y = view.origin
    return TypesetFacts(
        block=block,
        kind=view.block_role(block) or "RULE",
        source=view.block_source(block),
        source_lines=None if where is None else (where.span.line_start, where.span.line_end),
        characters=len(view.block_text(block)),
        lines=len(view.set_lines(block, block + 1)),
        rect=(rect[0] - x, rect[1] - y, rect[2] - rect[0], rect[3] - rect[1]),
    )


def typeset_panel_lines(facts: TypesetFacts) -> tuple[str, ...]:
    """The panel's lines for one block, above its source."""
    lines = "(not recorded)"
    if facts.source_lines is not None:
        lines = f"{facts.source_lines[0] + 1} to {facts.source_lines[1]}"
    return (
        f"block {facts.block}: {facts.kind}",
        f"source lines: {lines}",
        f"characters: {facts.characters}",
        f"lines set: {facts.lines}",
        f"rectangle: y {facts.rect[1]:.0f}, height {facts.rect[3]:.0f} px (its full extent)",
    )


def typeset_readouts(view: Any, stats: Any, width_px: float, edits: int) -> tuple[str, ...]:
    """
    The counts line under the controls: the view's own account.

    `stats` is the view's `ViewStats` as of the last frame, or `None`.
    """
    counted = (
        "nothing drawn yet"
        if stats is None
        else f"blocks {stats.blocks}   laid out so far {stats.blocks_laid_out}   "
        f"not reached yet {stats.blocks_deferred}"
    )
    return (f"measure {width_px:.0f} px   edits of the document {edits}   {counted}",)


def _why_not() -> str:
    """
    Why imtypeset is not drawing, as one sentence; empty when `typesetter.ready()`.

    `advtext.ui.pages.typeset.why_not`, which never asks `typesetter.module()`
    (a page is built in the pytest process by every page-enumerating test,
    and the library is kept out of that process). Imported when it is needed,
    so that importing this page imports no other page.
    """
    if typesetter.ready():
        return ""
    from advtext.ui.pages.typeset import why_not

    return why_not()


def _not_drawing(reason: str) -> str:
    """
    The one line a page shows instead of its content: `advtext.ui.pages.typeset.not_drawing`.
    """
    from advtext.ui.pages.typeset import not_drawing

    return not_drawing(reason)


def _say_why_not(reason: str) -> None:
    """
    The whole of a frame without the library: one wrapped line, `say_why_not`'s.
    """
    from advtext.ui.pages.typeset import say_why_not

    say_why_not(reason)


class InspectorPage:
    """
    The page: a view, the facts for the block last pointed at, and the menu.

    `typeset` is the `TypesetView`, or `None` when the library is not drawing
    (`reason` says why, and the page is that one line). `view` is the same
    object under the name the copies use.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        text = demo_text("sample.md")
        self.source = FALLBACK if text is None else text
        self.typeset: TypesetView | None = None
        self.reason = _why_not()
        """Why nothing is drawn, when nothing is; empty while the view draws."""
        if not self.reason:
            try:
                self.typeset = TypesetView(self.source, theme=context.theme, palette=DARK_PALETTE)
            except TypesetUnavailable as exc:
                self.reason = str(exc)
        self._revision = 0 if self.typeset is None else self.typeset.revision
        self.width_px = DEFAULT_WIDTH_PX
        self.max_width_px = DEFAULT_WIDTH_PX
        self.frames = 0
        self.view_stats: Any = None
        """The view's `ViewStats` as of the last frame, or `None`."""
        self.hovered: int | None = None
        """The block under the pointer on the last frame, or `None`."""
        self.block: int | None = None
        """The block the panel is about: the last one hovered. It stays when the mouse leaves."""
        self.facts: TypesetFacts | None = None
        self.menu: Target | None = None
        """What the open context menu is about: what was under the right click."""
        self.menus_opened = 0
        self.copied: tuple[str, str] | None = None
        """The last copy made from the menu: `("text" | "markdown", what was copied)`."""
        self.outlined: tuple[float, float, float, float] | None = None
        """The outline drawn on the last frame, as screen `(x0, y0, x1, y1)`, or `None`."""
        self._facts_for: tuple[object, ...] | None = None

    @property
    def view(self) -> TypesetView | None:
        """The view in use, or `None` when the library is not drawing."""
        return self.typeset

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.typeset is not None else "none"

    # -- what the controls and the menu do --------------------------------

    def set_width(self, width_px: float) -> None:
        """What the slider does: the next frame lays the document out at this measure."""
        self.width_px = max(MIN_WIDTH_PX, float(width_px))

    def copy_text(self, target: Target) -> str:
        """
        *Copy as text*: the selection if the click was on it, else the block as it reads.

        Nothing is copied, and the answer is empty, with no view.
        """
        view = self.typeset
        if view is None:
            return ""
        if target.selected:
            text = view.selected_text()
        else:
            text = "" if target.block is None else view.block_text(target.block)
        view.copy(text)
        self.copied = ("text", text)
        return str(text)

    def copy_markdown(self, target: Target) -> str:
        """
        *Copy as markdown*: the source of the selected blocks, else of the block.

        Nothing is copied, and the answer is empty, with no view.
        """
        view = self.typeset
        if view is None:
            return ""
        if target.selected:
            text = view.selected_source(self.source)
        else:
            found = None if target.block is None else view.block_source(target.block, self.source)
            text = "" if found is None else found
        view.copy(text)
        self.copied = ("markdown", text)
        return str(text)

    def target_under_mouse(self) -> Target:
        """
        What the view has under the mouse, as the menu wants it.

        The library's hit at the last draw. `selected` is whether the hit's
        position lies inside the selected range.
        """
        view = self.typeset
        hit = None if view is None else view.under_mouse
        if view is None or hit is None or not hit.in_block:
            return Target(None, False)
        place = (int(hit.position[0]), int(hit.position[1]))
        selection = view.selection
        return Target(place[0], selection is not None and selection[0] <= place < selection[1])

    @property
    def edits(self) -> int:
        """How many times the view's document changed since the page opened; 0 with no view."""
        return 0 if self.typeset is None else self.typeset.revision - self._revision

    def lines(self) -> tuple[str, ...]:
        """The counts line under the controls; the one "why not" line when nothing draws."""
        if self.typeset is None:
            return (_not_drawing(self.reason),)
        return typeset_readouts(self.typeset, self.view_stats, self.width_px, self.edits)

    def report(self) -> list[str]:
        """What an unattended run prints: counts."""
        facts = self.facts
        counted = self.view_stats
        view = self.typeset
        return [
            f"frames={self.frames} renderer={self.renderer} "
            f"blocks={0 if view is None else len(view.texts)} width={self.width_px:.0f} "
            f"edits={self.edits} "
            f"laid_out={0 if counted is None else counted.blocks_laid_out} "
            f"deferred={0 if counted is None else counted.blocks_deferred} "
            f"hovered={-1 if self.hovered is None else self.hovered} "
            f"block={-1 if self.block is None else self.block} "
            f"kind={'-' if facts is None else facts.kind} "
            f"lines={0 if facts is None else facts.lines} "
            f"outlined={int(self.outlined is not None)} menus={self.menus_opened} "
            f"whole={1 if counted is None else int(counted.whole)} "
            f"vertices={0 if counted is None else counted.vertices}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        view = self.typeset
        if view is None:
            _say_why_not(self.reason)
            return
        try:
            self._frame(imgui, view)
        except TypesetUnavailable as exc:
            # Whatever raised drew no text: what was drawn before it is this
            # frame, and the page is the one line from the next. Block numbers
            # were the view's, so what was pointed at goes with it.
            self.typeset = None
            self.view_stats = None
            self.reason = str(exc)
            self.block = self.hovered = self.facts = self.menu = self._facts_for = None
            self.outlined = None

    def _frame(self, imgui: Any, view: TypesetView) -> None:
        """
        The frame through imtypeset. `TypesetUnavailable` is the caller's to catch.

        Every pair opened here is closed on the way out of an exception, so
        the caller's handler leaves ImGui's stacks as it found them.
        """
        self._controls(imgui)
        for line in self.lines():
            caption(line)
        imgui.separator()

        available = imgui.get_content_region_avail()
        spacing = imgui.get_style().item_spacing.x
        text_width = max(MIN_WIDTH_PX + 40.0, available.x - PANEL_WIDTH_PX - spacing)
        # Always a scrollbar, so the pane's width does not depend on the
        # document's height at the measure the slider is on.
        imgui.begin_child(
            "##advtext-inspector-text",
            imgui.ImVec2(text_width, 0.0),
            imgui.ChildFlags_.borders.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        try:
            self.max_width_px = max(MIN_WIDTH_PX, imgui.get_content_region_avail().x)
            width_px = min(self.width_px, self.max_width_px)
            view.debug = self.context.debug
            view.draw(palette=DARK_PALETTE, width_px=width_px)
            # One more call into the library a frame, for the counts line.
            self.view_stats = view.stats
            over = bool(imgui.is_item_hovered())
            self.hovered = view.block_under_mouse() if over else None
            if self.hovered is not None:
                self.block = self.hovered
            if over and imgui.is_mouse_clicked(imgui.MouseButton_.right):
                self.menu = self.target_under_mouse()
            self._menu(imgui)
            self._refresh(width_px)
            self._outline(imgui)
        finally:
            imgui.end_child()

        imgui.same_line()
        imgui.begin_child("##advtext-inspector-panel", imgui.ImVec2(0.0, 0.0))
        try:
            self._panel(imgui)
        finally:
            imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        imgui.set_next_item_width(320.0)
        changed, value = imgui.slider_float(
            "measure (px)",
            self.width_px,
            MIN_WIDTH_PX,
            max(self.max_width_px, MIN_WIDTH_PX + 1.0),
            "%.0f",
        )
        if changed:
            self.set_width(float(round(value)))
        imgui.same_line()
        debug_toggle(self.context)

    def _menu(self, imgui: Any) -> None:
        """The host's menu. The view opened nothing; this is attached to its rectangle."""
        if not imgui.begin_popup_context_item(MENU_ID):
            return
        # A copy asks the view, which may find the library gone: what was
        # clicked is noted here and carried out after the popup is closed, so
        # that no ImGui pair is open when it raises.
        chosen = ""
        try:
            if imgui.is_window_appearing():
                self.menus_opened += 1
            target = self.menu if self.menu is not None else Target(None, False)
            about = "selection" if target.selected else "block"
            if imgui.menu_item(f"Copy {about} as text", "", False, target.block is not None)[0]:
                chosen = "text"
            if imgui.menu_item(f"Copy {about} as markdown", "", False, target.block is not None)[0]:
                chosen = "markdown"
        finally:
            imgui.end_popup()
        if chosen == "text":
            self.copy_text(target)
        elif chosen == "markdown":
            self.copy_markdown(target)

    def _refresh(self, width_px: float = 0.0) -> None:
        """Work the facts out again when the block or the layout changed, not every frame."""
        view = self.typeset
        if view is None:
            return
        block = self.block
        # There is no layout object to compare. A block's facts change with
        # the measure, with an edit, and with the document's height (a block
        # above it was laid out for the first time and moved it).
        layout: object = None if view.origin is None else (width_px, view.revision, view.height)
        key = (block, layout)
        if self._facts_for is not None and self._facts_for == key:
            return
        self._facts_for = key
        self.facts = None
        if block is None or layout is None:
            return
        self.facts = typeset_facts_of(view, block)

    def _outline(self, imgui: Any) -> None:
        self.outlined = None
        view = self.typeset
        if self.facts is None or self.hovered is None or view is None:
            return
        # One call into the library on a frame a block is hovered: its full
        # extent on screen, as of this frame's draw.
        screen = view.block_rect(self.hovered)
        if screen is None:
            return
        box = (screen[0] - 3.0, screen[1] - 1.0, screen[2] + 3.0, screen[3] + 1.0)
        imgui.get_window_draw_list().add_rect(
            imgui.ImVec2(box[0], box[1]), imgui.ImVec2(box[2], box[3]), OUTLINE
        )
        self.outlined = box

    def _panel(self, imgui: Any) -> None:
        facts = self.facts
        if facts is None:
            caption("Point at a block. Right-click it for the copy menu.")
            return
        for line in typeset_panel_lines(facts):
            imgui.text_wrapped(line)
        imgui.separator()
        caption("markdown source, verbatim:")
        imgui.push_text_wrap_pos(0.0)
        imgui.text_unformatted("(none recorded)" if facts.source is None else facts.source)
        imgui.pop_text_wrap_pos()


PAGE = PageSpec(
    name="Inspector",
    order=140,
    factory=InspectorPage,
    group="Embedding",
    caption="Point at a block: its source, role, lines and rectangle, and a copy menu.",
)

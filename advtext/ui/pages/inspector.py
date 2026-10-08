r"""
The Inspector page: point at a block and read what the library knows about it.

A document on the left in a `BareView`, and on the right, for the block under
the pointer: its role, the markdown it came from, the reading-order indices and
lines it owns, the layout unit it is part of, whether that unit was built for
the last relayout or carried over, and what building it costs. The hovered
block is outlined. A right click opens a menu with *Copy as text* and *Copy as
markdown*. A slider changes the measure, so that relayouts happen and what each
one reused can be counted.

**Everything here goes through the view's public surface, and that is the
point of the page**: it is the host a `BareView` was designed for. The view
draws no outline and opens no menu. It says which block is under the mouse
(`block_under_mouse`), whether the point is on the selection (`under_mouse`),
where the block's source is (`block_source`, `source_of`), what a copy of it
would be (`block_text`, `selected_text`, `selected_source`), and where its unit
sits (`layout`, `origin`); the page draws the rectangle and owns the popup
(`begin_popup_context_item` with an ID of the page's, straight after `draw`).

## Two readouts that are the view's own account

Both used to be worked out here, because the view kept no per-layout account
of its caches and no timings; both substitutes were wrong in ways their
labels had to apologise for, and both are now read from the library.

- **Reused or built** (`Reuse`) is `UnitLayout.stats`: the positions of the
  units `layout_units` composed and shipped for this layout, and by
  subtraction the ones it found. The page's old count compared `Unit` objects
  with the last eight layouts it had seen, which over-reported builds twice
  over: a unit found by value after a re-parse is a new object around the old
  commands, and a unit the view's cache still held from further back than the
  page's window was counted as built.
- **Build time** is `Unit.build_seconds`: what composing and shipping the
  unit took when the view's cache built it -- one wall-clock sample, carried
  with the unit for as long as it is reused. The page used to compose and
  ship the unit a second time itself to have a number.

Nothing here judges how the outline or the panel looks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats, rgba
from advtext.markdown import build_document
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView, Pointed, block_kind
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.units import PlacedUnit, UnitLayout
from advtext.units import px_from_sp

__all__ = [
    "PAGE",
    "BlockFacts",
    "InspectorPage",
    "Reuse",
    "facts_of",
    "readouts",
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


@dataclass(slots=True)
class Reuse:
    """
    A running tally of what each relayout built and what it found.

    `observe(layout)` once a frame. A layout that is a new object is a
    relayout, and its `stats` (`advtext.ui.units.LayoutStats`) say which of
    its units were composed and shipped for it; the rest were found in the
    view's cache. Nothing is worked out here: this adds the layouts up.
    """

    relayouts: int = 0
    last_units: int = 0
    last_reused: int = 0
    last_built: int = 0
    total_reused: int = 0
    total_built: int = 0
    _last: UnitLayout | None = field(default=None, init=False)

    def observe(self, layout: UnitLayout | None) -> bool:
        """Take note of the view's layout; true if it was a new one."""
        if layout is None or layout is self._last:
            return False
        self._last = layout
        stats = layout.stats
        self.relayouts += 1
        self.last_units = stats.units
        self.last_built = len(stats.built)
        self.last_reused = stats.reused
        self.total_built += self.last_built
        self.total_reused += self.last_reused
        return True

    def was_reused(self, unit: PlacedUnit) -> bool:
        """Whether `unit`, of the layout last observed, was found and not built for it."""
        layout = self._last
        if layout is None:
            return False
        position = layout.position_of(unit)
        return position is not None and not layout.stats.was_built(position)


@dataclass(frozen=True, slots=True)
class BlockFacts:
    """What the panel says about one block."""

    block: int
    kind: str
    source: str | None
    source_lines: tuple[int, int] | None
    """`[first, stop)` lines of the markdown, zero-based, if the document records them."""
    indices: tuple[int, int]
    """`[start, stop)` of the block's reading-order indices in the layout."""
    lines: int
    """Set lines that hold at least one glyph."""
    unit: int
    """Index of its (first) unit in `layout.placed`."""
    unit_blocks: tuple[int, int]
    """`[first, stop)` of the blocks that unit sets: more than one for a quote."""
    unit_count: int
    """How many units set the block: more than one only when it is laid out in pieces."""
    reused: bool
    build_ms: float
    """What the view's cache spent building the block's unit(s), whenever it built them."""
    rect: tuple[float, ...]
    """`(x, y, width, height)` in pixels from the document's top-left: `BareView.block_rect`."""


def facts_of(view: BareView, source: str, block: int, reuse: Reuse) -> BlockFacts | None:
    """The facts for block `block` of `view` as last laid out, or `None`."""
    layout = view.layout
    if layout is None or not 0 <= block < len(view.document.blocks):
        return None
    units = layout.units_of_block(block)
    rect = view.block_rect(block)
    first_at = layout.position_of(units[0]) if units else None
    if not units or rect is None or first_at is None:
        return None
    first = units[0]
    ppi = view.px_per_inch
    where = view.source_of(block)
    own = layout.indices_of_block(block)
    return BlockFacts(
        block=block,
        kind=block_kind(view.document.blocks[block]).name,
        source=view.block_source(block, source),
        source_lines=None if where is None else (where.span.line_start, where.span.line_end),
        indices=(own.start, own.stop),
        lines=len(view.set_lines(block, block + 1)),
        unit=first_at,
        unit_blocks=(first.block_range.start, first.block_range.stop),
        unit_count=len(units),
        reused=all(reuse.was_reused(unit) for unit in units),
        build_ms=sum(unit.unit.build_seconds for unit in units) * 1000.0,
        rect=(
            px_from_sp(rect.x, ppi),
            px_from_sp(rect.y, ppi),
            px_from_sp(rect.width, ppi),
            px_from_sp(rect.height, ppi),
        ),
    )


def readouts(reuse: Reuse, width_px: float) -> tuple[str, ...]:
    """The counts line under the controls."""
    return (
        f"measure {width_px:.0f} px   relayouts {reuse.relayouts}   "
        f"last: {reuse.last_units} units, {reuse.last_reused} reused, {reuse.last_built} built   "
        f"all: {reuse.total_reused} reused, {reuse.total_built} built",
    )


def panel_lines(facts: BlockFacts) -> tuple[str, ...]:
    """The panel's lines for one block, above its source."""
    lines = "(not recorded)"
    if facts.source_lines is not None:
        lines = f"{facts.source_lines[0] + 1} to {facts.source_lines[1]}"
    unit = f"unit {facts.unit}"
    if facts.unit_count > 1:
        unit += f" and {facts.unit_count - 1} more (laid out in pieces)"
    if facts.unit_blocks[1] - facts.unit_blocks[0] > 1:
        unit += f", shared by blocks {facts.unit_blocks[0]} to {facts.unit_blocks[1] - 1}"
    start, stop = facts.indices
    state = "carried over" if facts.reused else "built"
    return (
        f"block {facts.block}: {facts.kind}",
        f"source lines: {lines}",
        f"indices: {start} to {stop} ({stop - start})",
        f"lines set: {facts.lines}",
        unit,
        f"at the last relayout: {state} (the layout's own stats)",
        f"compose + ship when built: {facts.build_ms:.2f} ms (one sample, the view's)",
        f"rectangle: y {facts.rect[1]:.0f}, height {facts.rect[3]:.0f} px",
    )


class InspectorPage:
    """The page: a `BareView`, the facts for the block last pointed at, and the menu."""

    def __init__(self, context: PageContext) -> None:
        self.context = context
        text = demo_text("sample.md")
        self.source = FALLBACK if text is None else text
        self.view = BareView(
            document=build_document(self.source, context.theme, context.metrics),
            theme=context.theme,
            measure=context.measure,
            px_per_inch=context.px_per_inch,
        )
        self.reuse = Reuse()
        self.width_px = DEFAULT_WIDTH_PX
        self.max_width_px = DEFAULT_WIDTH_PX
        self.frames = 0
        self.stats: DrawStats | None = None
        self.hovered: int | None = None
        """The block under the pointer on the last frame, or `None`."""
        self.block: int | None = None
        """The block the panel is about: the last one hovered. It stays when the mouse leaves."""
        self.facts: BlockFacts | None = None
        self.menu: Pointed | None = None
        """What the open context menu is about: what was under the right click."""
        self.menus_opened = 0
        self.copied: tuple[str, str] | None = None
        """The last copy made from the menu: `("text" | "markdown", what was copied)`."""
        self.outlined: tuple[float, float, float, float] | None = None
        """The outline drawn on the last frame, as screen `(x0, y0, x1, y1)`, or `None`."""
        self._facts_for: tuple[object, ...] | None = None

    # -- what the controls and the menu do --------------------------------

    def set_width(self, width_px: float) -> None:
        """What the slider does: the next frame lays the document out at this measure."""
        self.width_px = max(MIN_WIDTH_PX, float(width_px))

    def copy_text(self, target: Pointed) -> str:
        """*Copy as text*: the selection if the click was on it, else the block as it reads."""
        if target.selected:
            text = self.view.selected_text()
        else:
            text = "" if target.block is None else self.view.block_text(target.block)
        self.view.copy(text)
        self.copied = ("text", text)
        return text

    def copy_markdown(self, target: Pointed) -> str:
        """*Copy as markdown*: the source of the selected blocks, else of the block."""
        if target.selected:
            text = self.view.selected_source(self.source)
        else:
            found = (
                None if target.block is None else self.view.block_source(target.block, self.source)
            )
            text = "" if found is None else found
        self.view.copy(text)
        self.copied = ("markdown", text)
        return text

    def report(self) -> list[str]:
        """What an unattended run prints: counts."""
        reuse, stats, facts = self.reuse, self.stats, self.facts
        layout = self.view.layout
        return [
            f"frames={self.frames} blocks={len(self.view.document.blocks)} "
            f"units={0 if layout is None else len(layout.placed)} "
            f"width={self.width_px:.0f} relayouts={reuse.relayouts} "
            f"last_reused={reuse.last_reused} last_built={reuse.last_built} "
            f"reused={reuse.total_reused} built={reuse.total_built} "
            f"hovered={-1 if self.hovered is None else self.hovered} "
            f"block={-1 if self.block is None else self.block} "
            f"kind={'-' if facts is None else facts.kind} "
            f"lines={0 if facts is None else facts.lines} "
            f"outlined={int(self.outlined is not None)} menus={self.menus_opened} "
            f"glyphs={0 if stats is None else stats.glyphs} "
            f"missing={0 if stats is None else stats.missing}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        self._controls(imgui)
        for line in readouts(self.reuse, self.width_px):
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
        self.max_width_px = max(MIN_WIDTH_PX, imgui.get_content_region_avail().x)
        width_px = min(self.width_px, self.max_width_px)
        view = self.view
        view.debug = self.context.debug
        self.stats = view.draw(fonts=self.context.fonts, palette=DARK_PALETTE, width_px=width_px)
        over = bool(imgui.is_item_hovered())
        self.reuse.observe(view.layout)
        self.hovered = view.block_under_mouse() if over else None
        if self.hovered is not None:
            self.block = self.hovered
        if over and imgui.is_mouse_clicked(imgui.MouseButton_.right):
            self.menu = view.under_mouse()
        self._menu(imgui)
        self._refresh()
        self._outline(imgui)
        imgui.end_child()

        imgui.same_line()
        imgui.begin_child("##advtext-inspector-panel", imgui.ImVec2(0.0, 0.0))
        self._panel(imgui)
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
        if imgui.is_window_appearing():
            self.menus_opened += 1
        target = self.menu if self.menu is not None else Pointed(None, None, False)
        about = "selection" if target.selected else "block"
        if imgui.menu_item(f"Copy {about} as text", "", False, target.block is not None)[0]:
            self.copy_text(target)
        if imgui.menu_item(f"Copy {about} as markdown", "", False, target.block is not None)[0]:
            self.copy_markdown(target)
        imgui.end_popup()

    def _refresh(self) -> None:
        """Work the facts out again when the block or the layout changed, not every frame."""
        view, block = self.view, self.block
        layout = view.layout
        key = (block, layout)
        if self._facts_for is not None and all(
            a is b or a == b for a, b in zip(self._facts_for, key, strict=True)
        ):
            return
        self._facts_for = key
        self.facts = None
        if block is None or layout is None:
            return
        self.facts = facts_of(view, self.source, block, self.reuse)

    def _outline(self, imgui: Any) -> None:
        self.outlined = None
        rect = None if self.hovered is None else self.view.block_rect(self.hovered)
        screen = None if rect is None else self.view.to_screen(rect)
        if self.facts is None or screen is None:
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
        for line in panel_lines(facts):
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
    caption="Point at a block: its source, role, indices, unit, and what a relayout reused.",
)

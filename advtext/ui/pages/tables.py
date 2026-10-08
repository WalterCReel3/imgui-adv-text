r"""
The Tables page: drag a column's edge and its cells are broken again, live.

A document with five tables in it is drawn by one `advtext.ui.bare_view.BareView`.
Every column of every table has a handle on its right edge. Dragging one sets
the table's column widths through `advtext.ui.with_columns`, which is the hook
the library has for exactly this, and the view lays out again. Above the pane
are readouts: each column's width against its natural width and its
longest-word floor, and how many of the document's units the last drag
re-shipped.

## What a drag does

- **A handle between two columns moves their boundary.** The two share the
  width they had between them, so the table stays as wide as it was.
- **The handle on the table's right edge resizes the last column**, and the
  table with it, up to the measure.
- **No column goes below its floor** -- the widest stretch of any of its cells
  that no line break can divide, padding included. Below that a word would run
  into the next column, and the library's own default never goes there either.
- **Reset to automatic** drops every width that was chosen and the library
  apportions the columns again.

Widths are clamped here, in `dragged` and `fitted`, before `with_columns` is
called: it raises on a width under one scaled point or one that is not finite,
and a mouse can ask for either. A table that was dragged keeps the widths that
were chosen while they fit; when the measure becomes too narrow for them they
are squeezed toward the floors for as long as it stays narrow (`fitted`), and
come back when it widens.

## How the drag coexists with the view's selection drag

`BareView` submits no item while idle and begins a selection on a left press
over its rectangle unless *an item of the host's is under the mouse*
(`advtext.ui.bare_view`, "Where the mouse goes"). So each handle is an
`invisible_button` this page submits **before** `view.draw()`, in the frame's
own geometry: `view.layout_for(width)` for the layout the draw is about to
use, `view.next_origin()` for where it is about to put it, and
`advtext.ui.table_columns` for the edges.

- a press on a handle is the handle's: the handle is already ImGui's hovered
  item when the view judges the press, on the very frame the pointer arrives;
- while the handle is held it is ImGui's active item, so the view's window is
  not "hovered" and the view begins nothing and follows no link;
- a press anywhere else on the text begins a selection as it always does;
- a selection made before a drag is carried across each relayout by the view
  (`advtext.ui.units.carry_selection`), so it is still there afterwards.

The handles used to be submitted *after* the view, from the origin and layout
of the frame before, because the view had no way to say where it was about to
draw. That had two single-frame edges. One is gone: a press arriving on the
same frame the pointer first reached a handle went to the view as a
selection, since the handle did not exist yet when the view looked. The other
is the view's and remains: on the frame the pointer *leaves* a handle, ImGui
still reports the handle as the hovered item (its hovered ID is this frame's
or, until something is hovered, the last frame's), so a link is not hovered
and a press would not select until the frame after. Both are pinned by
`tests/test_page_tables.py`.

A held handle is applied before the view lays out, from the mouse position
and `next_origin()`, so the table follows the pointer on the frame it moves.

## Where the numbers come from

Everything is asked through public names: the longest-word floors are
`advtext.ui.table_column_limits(...).floor`, and "re-shipped" is
`UnitLayout.stats.built`, the layout's own account of the units it composed
and shipped. (Both were roundabout before the library said them: floors by
asking `table_columns` at a one-point measure, and re-shipping by comparing
unit objects position by position.)

## The readouts report change and cost, never quality

A count of units re-shipped is a fact about what the caches did. Whether a
table reads well at the widths somebody dragged it to is what the page exists
to let a person judge (`docs/visual-review.md`).

## What has been run

`tests/test_page_tables.py`: the arithmetic on its own; the board with no
ImGui; the page in frames of a real ImGui context with no backend, with mouse
events queued (hover, press, move, release on a handle, and a press on text);
and the real app in a window with the same gesture injected, reporting counts.
Nobody has dragged a column with a hand.

Options (`--tab tables:...`): `floors` opens with every column of every table
at its floor; an integer is the pane's measure in pixels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats, rgba
from advtext.markdown import Document, TableBlock, build_document
from advtext.pack import CharMeasure
from advtext.style import MetricsResolver, Theme, fontlib_metrics
from advtext.ui import table_column_limits, table_columns, table_natural_widths, with_columns
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.units import UnitLayout
from advtext.units import DEFAULT_PX_PER_INCH, UNITY, Scaled, px_from_sp, sp_from_px

__all__ = [
    "DEFAULT_PANE_PX",
    "FALLBACK",
    "GRIP_PX",
    "PAGE",
    "Board",
    "Grip",
    "TablesPage",
    "dragged",
    "fitted",
    "floors_of",
    "readouts",
]

DEFAULT_PANE_PX: Final = 720.0
"""
The measure the page opens at, in pixels, where the window has that much.

Narrower than the 1068 px body on purpose: at this width one of the demo's
tables fits and is scaled up, and one does not and is squeezed, so both of the
library's regimes are on the page as it opens. A starting point for the slider
and not a claim about what a pane should be.
"""

MIN_PANE_PX: Final = 240.0
MAX_PANE_PX: Final = 1600.0

GRIP_PX: Final = 8.0
"""
How wide a handle is, centred on its column edge.

The stock theme's cell padding is half the body size on each side of a column
edge -- 16 px of blank between two cells' text at the demo's size -- so a
handle this wide lies inside the padding and takes no press from a glyph.
"""

GRIP_LINE: Final = rgba(0x9F, 0xB4, 0xCC)
"""
The line drawn on a handle that is hovered or held. This page's chrome, not a palette role.
"""

FLOORS_OPTION: Final = "floors"

FALLBACK: Final = (
    "No `demo/` directory was found, so this is the only table.\n\n"
    "| Column | What dragging its edge does |\n"
    "| --- | --- |\n"
    "| First | The boundary moves and both columns are broken again at their new widths. |\n"
    "| Second | The right edge resizes this column and the table with it. |\n"
)


# ----------------------------------------------------------------------
# Arithmetic: no ImGui, no layout
# ----------------------------------------------------------------------


def floors_of(block: TableBlock, theme: Theme, measure: CharMeasure) -> tuple[Scaled, ...]:
    """
    Each column's longest unbreakable stretch, padding included: the narrowest it can be set.

    `advtext.ui.table_column_limits(...).floor`: the widths `table_columns`
    squeezes a too-wide table towards and never below, whatever widths the
    block itself carries. Never under one scaled point, which is the least
    `with_columns` takes.
    """
    return tuple(max(1, floor) for floor in table_column_limits(block, theme, measure).floor)


def dragged(
    widths: Sequence[Scaled],
    floors: Sequence[Scaled],
    edge: int,
    x: float,
    available: Scaled,
) -> tuple[Scaled, ...]:
    """
    `widths` after the right edge of column `edge` is dragged to `x`.

    `x` is measured from the table's left edge, in scaled points, and may be
    anything a mouse can produce: negative, far past the pane, not finite.
    What comes back is always a set of widths `with_columns` accepts.

    An edge between two columns moves the boundary: the two keep the width
    they had between them and neither goes under its floor. The last edge
    resizes the last column alone, between its floor and what is left of
    `available` -- or stays at the floor when not even that fits.

    Returned unchanged when there is nothing to do: no such edge, an `x` that
    is not a number, or a pair of columns already too narrow for both floors.
    """
    current = tuple(widths)
    if not 0 <= edge < len(current) or not math.isfinite(x):
        return current
    left = sum(current[:edge])
    # Clamped as a float first: `round` of 1e300 is an integer of three
    # hundred digits, which is a width nobody asked for the arithmetic of.
    low = floors[edge]
    if edge < len(current) - 1:
        pair = current[edge] + current[edge + 1]
        high = pair - floors[edge + 1]
        if high < low:
            return current
        chosen = round(min(max(x - left, low), high))
        return (*current[:edge], chosen, pair - chosen, *current[edge + 2 :])
    high = max(low, available - left)
    return (*current[:edge], round(min(max(x - left, low), high)))


def fitted(
    widths: Sequence[Scaled], floors: Sequence[Scaled], available: Scaled
) -> tuple[Scaled, ...]:
    """
    Chosen `widths`, squeezed to `available` if they are wider than it.

    As given when they fit. Otherwise every column keeps its floor and what is
    left of `available` is shared in proportion to how far each was above its
    floor, the last column taking the rounding remainder so the sum is exact
    -- the rule `advtext.ui` applies to its own default, restated because that
    function is private. When the floors alone exceed `available` they are
    what comes back and the table is wider than the measure.
    """
    current = tuple(max(width, floor) for width, floor in zip(widths, floors, strict=True))
    if sum(current) <= available:
        return current
    slack = available - sum(floors)
    give = [width - floor for width, floor in zip(current, floors, strict=True)]
    total = sum(give)
    if slack <= 0 or total <= 0:
        return tuple(floors)
    out = [floor + slack * room // total for floor, room in zip(floors, give, strict=True)]
    out[-1] += available - sum(out)
    return tuple(out)


# ----------------------------------------------------------------------
# The board: a document, its view, and the widths somebody chose
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Grip:
    """
    One handle: which table, which column's right edge, and where it is in the document.

    `table` indexes `Document.blocks`. `x`, `top` and `bottom` are document
    scaled points; `view.origin` plus these in pixels is where it is on screen.
    """

    table: int
    edge: int
    x: Scaled
    top: Scaled
    bottom: Scaled


@dataclass
class Board:
    """
    A document with tables in it, the view that draws it, and the column widths chosen so far.

    Everything the page does except the ImGui calls: `settle` is told the
    measure a frame is about to lay out at, `drag` and `reset` are the
    gestures, `grips` says where the handles are, `observe` counts what a
    relayout re-shipped. None of it needs a window.
    """

    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver = fontlib_metrics
    px_per_inch: float = DEFAULT_PX_PER_INCH
    text: str | None = None
    """The markdown to show in place of `demo/tables.md`. For a test, or a host's own."""

    source: Document = field(init=False)
    """The document as converted, every table automatic. Never changed."""
    view: BareView = field(init=False)
    tables: tuple[int, ...] = field(init=False)
    """Which of the document's blocks are tables, in order."""
    chosen: dict[int, tuple[Scaled, ...]] = field(default_factory=dict, init=False)
    """The widths a drag asked for, by block number. A table not in here is automatic."""
    focus: int | None = field(default=None, init=False)
    """The table the readouts are about: the one last pointed at or dragged."""
    width: Scaled | None = field(default=None, init=False)
    """The measure of the last `settle`, or `None` before the first."""
    followed: list[str] = field(default_factory=list, init=False)
    """Every link target clicked, in order."""
    reshipped: int | None = field(default=None, init=False)
    """How many units the latest drag's (or reset's) relayout shipped again; `None` before any."""
    units: int = field(default=0, init=False)
    """How many units that layout had."""
    relayouts: int = field(default=0, init=False)
    """How many layouts drags and resets have caused."""
    _floors: dict[int, tuple[Scaled, ...]] = field(default_factory=dict, init=False)
    _natural: dict[int, tuple[Scaled, ...]] = field(default_factory=dict, init=False)
    _automatic: dict[int, tuple[Scaled, tuple[Scaled, ...]]] = field(
        default_factory=dict, init=False
    )
    _seen: UnitLayout | None = field(default=None, init=False)
    _pending: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        found = demo_text("tables.md") if self.text is None else self.text
        self.source = build_document(FALLBACK if found is None else found, self.theme, self.metrics)
        self.tables = tuple(
            number
            for number, block in enumerate(self.source.blocks)
            if isinstance(block, TableBlock)
        )
        self.focus = self.tables[0] if self.tables else None
        self.view = BareView(
            self.source,
            self.theme,
            self.measure,
            px_per_inch=self.px_per_inch,
            on_link=self.followed.append,
        )

    # -- what a table's columns are ------------------------------------

    def block(self, table: int) -> TableBlock:
        """
        The table at block number `table`, as converted. `KeyError` if that block is not a table.
        """
        if table not in self.tables:
            raise KeyError(f"block {table} is not a table")
        found = self.source.blocks[table]
        assert isinstance(found, TableBlock)
        return found

    def floors(self, table: int) -> tuple[Scaled, ...]:
        """
        `floors_of` this table, measured once.
        """
        if table not in self._floors:
            self._floors[table] = floors_of(self.block(table), self.theme, self.measure)
        return self._floors[table]

    def natural(self, table: int) -> tuple[Scaled, ...]:
        """
        Each column's widest cell set on one line, padding included, measured once.
        """
        if table not in self._natural:
            self._natural[table] = table_natural_widths(self.block(table), self.theme, self.measure)
        return self._natural[table]

    def available(self, table: int) -> Scaled:
        """
        The width the table has at the current measure: the measure less the table's indent.
        """
        width = UNITY if self.width is None else self.width
        return max(width - self.block(table).left_indent, UNITY)

    def columns(self, table: int) -> tuple[Scaled, ...]:
        """
        The widths this table's columns are set to at the current measure.

        The chosen ones, squeezed if the measure has become too narrow for
        them; otherwise the library's own, asked of `table_columns` once for
        each measure. Empty before the first `settle`.
        """
        if self.width is None:
            return ()
        wish = self.chosen.get(table)
        if wish is not None:
            return fitted(wish, self.floors(table), self.available(table))
        kept = self._automatic.get(table)
        if kept is None or kept[0] != self.width:
            kept = (
                self.width,
                table_columns(self.block(table), self.theme, self.width, self.measure),
            )
            self._automatic[table] = kept
        return kept[1]

    # -- the gestures ---------------------------------------------------

    def settle(self, width: Scaled) -> None:
        """
        Tell the board the measure the next layout is at. Call before the view draws.

        A change of measure with widths chosen sets those tables again, since
        what fitted before may not now.
        """
        if width == self.width:
            return
        self.width = width
        if self.chosen:
            self._apply()

    def drag(self, table: int, edge: int, x: float) -> bool:
        """
        Drag the right edge of column `edge` of `table` to document x `x`. True if anything moved.

        `x` is in the document's scaled points, as `Grip.x` is. Nothing
        before the first `settle`: there is no measure to drag within.
        """
        if self.width is None or table not in self.tables:
            return False
        before = self.columns(table)
        after = dragged(
            before,
            self.floors(table),
            edge,
            x - self.block(table).left_indent,
            self.available(table),
        )
        self.focus = table
        if after == before:
            return False
        self.chosen[table] = after
        self._apply()
        return True

    def to_floors(self) -> None:
        """
        Set every column of every table to its floor: the most wrapping there can be.
        """
        for table in self.tables:
            self.chosen[table] = self.floors(table)
        self._apply()

    def reset(self) -> bool:
        """
        Back to automatic: forget every chosen width. True if there was one.
        """
        if not self.chosen:
            return False
        self.chosen.clear()
        self._apply()
        return True

    def _apply(self) -> None:
        """
        Put the chosen widths into the view's document and ask it to lay out again.

        Each chosen table is replaced by `with_columns` of the table as
        converted; every other block is the object it was, which is what lets
        the view's caches find it.
        """
        blocks = list(self.source.blocks)
        if self.width is not None:
            for table in self.chosen:
                blocks[table] = with_columns(self.block(table), widths=self.columns(table))
        self.view.document = replace(self.source, blocks=tuple(blocks))
        self.view.invalidate()
        self._pending = True

    # -- where the handles are, and what a relayout cost -----------------

    def grips(self) -> tuple[Grip, ...]:
        """
        Every handle of the view's current layout, top to bottom and left to right.

        Empty before the view has laid out, and while its layout is at a
        measure other than the board's (the frame between a `settle` and the
        draw that follows it).
        """
        layout = self.view.layout
        if layout is None or layout.width != self.width:
            return ()
        out: list[Grip] = []
        for table in self.tables:
            units = layout.units_of_block(table)
            if not units:
                continue
            x = self.block(table).left_indent
            for edge, width in enumerate(self.columns(table)):
                x += width
                out.append(Grip(table, edge, x, units[0].y, units[-1].bottom))
        return tuple(out)

    def observe(self) -> int | None:
        """
        Count the units the latest layout shipped again, if a drag or a reset caused it.

        Call after the view has drawn. The count is the layout's own
        (`UnitLayout.stats.built`): the units it composed and shipped. A
        layout at a new measure is not counted -- every unit is new and none
        because of a drag -- and neither is one nothing here asked for.
        Returns the count, or `None` when nothing was counted.
        """
        layout = self.view.layout
        if layout is None or layout is self._seen:
            return None
        before, self._seen = self._seen, layout
        pending, self._pending = self._pending, False
        if before is None or before.width != layout.width or not pending:
            return None
        changed = len(layout.stats.built)
        self.reshipped = changed
        self.units = len(layout.placed)
        self.relayouts += 1
        return changed


def readouts(board: Board) -> tuple[str, ...]:
    """
    The four readout lines, top to bottom. Always four, so the pane below does not move.

    Widths in pixels at the board's density. Counts and sizes; no judgement.
    """
    table = board.focus
    if table is None or board.width is None:
        about = "no table in this document" if table is None else "not laid out yet"
        return (about, "", _last_drag(board), _links(board))
    density = board.px_per_inch
    widths = board.columns(table)
    natural = board.natural(table)
    floors = board.floors(table)
    under = sum(1 for width, wide in zip(widths, natural, strict=True) if width < wide)
    at_floor = sum(1 for width, floor in zip(widths, floors, strict=True) if width <= floor)
    state = "dragged" if table in board.chosen else "automatic"
    head = (
        f"table {board.tables.index(table) + 1} of {len(board.tables)}  ·  {state}"
        f"  ·  {px_from_sp(sum(widths), density):.0f} px wide in a "
        f"{px_from_sp(board.available(table), density):.0f} px measure"
        f"  ·  {under} of {len(widths)} columns under natural width, {at_floor} at the floor"
    )
    columns = "width / natural / floor, px:  " + "  ·  ".join(
        f"{px_from_sp(width, density):.0f} / {px_from_sp(wide, density):.0f}"
        f" / {px_from_sp(floor, density):.0f}"
        for width, wide, floor in zip(widths, natural, floors, strict=True)
    )
    return (head, columns, _last_drag(board), _links(board))


def _last_drag(board: Board) -> str:
    if board.reshipped is None:
        return "last drag: none yet"
    return (
        f"last drag: {board.reshipped} of {board.units} units re-shipped"
        f"  ·  layouts caused by dragging so far: {board.relayouts}"
    )


def _links(board: Board) -> str:
    hovered = board.view.hovered_link
    last = board.followed[-1] if board.followed else "none yet"
    return (
        f"link under the pointer: {hovered or 'none'}"
        f"  ·  clicked: {len(board.followed)}, last: {last}"
    )


def report(board: Board, frames: int, stats: DrawStats | None) -> list[str]:
    """
    What an unattended run prints: one line of totals and one a table. Counts, not judgements.
    """
    selection = board.view.selection
    lines = [
        f"frames={frames} tables={len(board.tables)} dragged={len(board.chosen)} "
        f"reshipped={-1 if board.reshipped is None else board.reshipped} units={board.units} "
        f"relayouts={board.relayouts} selected={selection.end - selection.start} "
        f"glyphs={0 if stats is None else stats.glyphs} "
        f"missing={0 if stats is None else stats.missing}"
    ]
    for table in board.tables:
        widths = board.columns(table)
        floors = board.floors(table)
        lines.append(
            f"table={table} columns={len(widths)} "
            f"width_sp={sum(widths)} "
            f"under_floor={sum(1 for w, f in zip(widths, floors, strict=True) if w < f)} "
            f"state={'dragged' if table in board.chosen else 'automatic'}"
        )
    return lines


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


class TablesPage:
    """
    The page: a `Board`, the frame that draws it, and the handles over the view.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.board = Board(
            theme=context.theme,
            measure=context.measure,
            metrics=context.metrics,
            px_per_inch=context.px_per_inch,
        )
        asked = context.count_for(PAGE.name)
        self.pane_px = (
            DEFAULT_PANE_PX if asked is None else min(max(float(asked), MIN_PANE_PX), MAX_PANE_PX)
        )
        self._to_floors = FLOORS_OPTION in context.options_for(PAGE.name)
        self.held: tuple[int, int] | None = None
        """The handle being dragged as of the last frame: `(table, edge)`."""
        self._grab = 0.0
        self.cursor_drift = 0.0
        """How far the handles left ImGui's cursor from where the view had left it. Zero."""
        self.stats: DrawStats | None = None
        self.frames = 0

    def report(self) -> list[str]:
        """
        `report` of this page's board, with the frames it has drawn.
        """
        return report(self.board, self.frames, self.stats)

    def draw(self) -> None:
        from imgui_bundle import imgui

        board = self.board
        self.frames += 1
        self._controls(imgui)
        for line in readouts(board):
            caption(line)
        imgui.separator()

        # A vertical scrollbar that is always there: a row that grows as its
        # column narrows can push the document past the window, and a
        # scrollbar appearing would change the measure under the drag.
        imgui.begin_child(
            "##advtext-tables",
            imgui.ImVec2(0.0, 0.0),
            imgui.ChildFlags_.borders.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        width_px = max(min(imgui.get_content_region_avail().x, self.pane_px), MIN_WIDTH_PX)
        board.settle(sp_from_px(width_px, board.px_per_inch))
        if self._to_floors:
            self._to_floors = False
            board.to_floors()
        # This frame's geometry, before the view draws: where it will put the
        # document, and the layout it will put there.
        origin = board.view.next_origin()
        self._follow(imgui, origin)
        board.view.layout_for(sp_from_px(width_px, board.px_per_inch))
        self._handles(imgui, origin)
        board.view.debug = self.context.debug
        self.stats = board.view.draw(
            fonts=self.context.fonts, palette=DARK_PALETTE, width_px=width_px
        )
        board.observe()
        imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        if imgui.button("Reset to automatic"):
            self.board.reset()
        imgui.same_line()
        imgui.set_next_item_width(260.0)
        changed, pane = imgui.slider_float(
            "measure, px", self.pane_px, MIN_PANE_PX, MAX_PANE_PX, "%.0f"
        )
        if changed:
            self.pane_px = min(max(float(pane), MIN_PANE_PX), MAX_PANE_PX)
        imgui.same_line()
        debug_toggle(self.context)

    def _follow(self, imgui: Any, origin: tuple[float, float]) -> None:
        """
        Move the held handle to the pointer, before the view lays out.

        `origin` is where the view is about to draw (`next_origin`). A handle
        whose button is no longer down is let go here; ImGui lets go of the
        item itself.
        """
        if self.held is None:
            return
        if not imgui.is_mouse_down(imgui.MouseButton_.left):
            self.held = None
            return
        table, edge = self.held
        x_px = imgui.get_mouse_pos().x - self._grab - origin[0]
        if math.isfinite(x_px):
            self.board.drag(table, edge, sp_from_px(x_px, self.board.px_per_inch))

    def _handles(self, imgui: Any, origin: tuple[float, float]) -> None:
        """
        One invisible button a column edge, where the view is about to draw. Call inside its child.

        Submitted before the view, so that each is an item by the time the
        view judges a press (the module docstring). `origin` is
        `view.next_origin()` and the view has been laid out for this frame.
        The cursor is put back afterwards, to where the view starts
        (`cursor_drift` is the check): the buttons are inside the rectangle
        the view is about to claim and add nothing to the child's content.
        """
        board = self.board
        density = board.px_per_inch
        pointed = board.view.block_under_mouse()
        if pointed in board.tables and self.held is None:
            board.focus = pointed

        after = imgui.get_cursor_screen_pos()
        mouse_x = imgui.get_mouse_pos().x
        held: tuple[int, int] | None = None
        for grip in board.grips():
            x = origin[0] + px_from_sp(grip.x, density)
            top = origin[1] + px_from_sp(grip.top, density)
            height = px_from_sp(grip.bottom - grip.top, density)
            if height < 1.0:
                continue
            imgui.set_cursor_screen_pos(imgui.ImVec2(x - GRIP_PX / 2.0, top))
            imgui.invisible_button(
                f"##advtext-tables-grip-{grip.table}-{grip.edge}", imgui.ImVec2(GRIP_PX, height)
            )
            if imgui.is_item_activated():
                # Where on the handle it was taken, so the edge does not jump
                # to the pointer on the first frame of the drag.
                self._grab = mouse_x - x
            active = imgui.is_item_active()
            if active:
                held = (grip.table, grip.edge)
            if active or imgui.is_item_hovered():
                board.focus = grip.table
                imgui.set_mouse_cursor(imgui.MouseCursor_.resize_ew)
                imgui.get_window_draw_list().add_line(
                    imgui.ImVec2(x, top), imgui.ImVec2(x, top + height), GRIP_LINE, 2.0
                )
        # Back to where the view starts. It submits its own item next, which
        # is what ImGui asks of anyone who moves the cursor.
        imgui.set_cursor_screen_pos(after)
        self.cursor_drift = imgui.get_cursor_screen_pos().y - after.y
        self.held = held


PAGE = PageSpec(
    name="Tables",
    order=120,
    factory=TablesPage,
    group="Embedding",
    caption="drag a column edge and the cells re-wrap",
    options=(FLOORS_OPTION,),
    shots=("", FLOORS_OPTION),
)

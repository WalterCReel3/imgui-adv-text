r"""
The Tables page: drag a column's edge and its cells are broken again, live.

A document with five tables in it is drawn by one view. Every column of every
table has a handle on its right edge. Dragging one states the table's column
widths, and the table is set again at them. Above the pane are readouts: each
column's width against its natural width and its longest-word floor, and what
the last drag cost.

## What draws: the imtypeset library, or nothing

Chosen once, when the page is built, as `imscribe.ui.pages.typeset` chooses
(`why_not`): with `imscribe.typesetter.ready()` the page is a `TypesetBoard`
over an `imscribe.ui.typeset_view.TypesetView`, where a table is a block of
the library's document (imtypeset commit `be40444`) and a drag is
`TypesetView.set_table_columns`. Otherwise `TablesPage.board` is `None` and
the page draws one wrapped line saying why (`pages.typeset.say_why_not`) and
nothing else. A view call that raises `TypesetUnavailable` anywhere in the
frame (the controls and the readouts ask the view too) has drawn no text: the
page drops the board, keeps the sentence, and is that one line from the next
frame on. Any other exception is a bug and leaves `draw`.

**Nothing of the old core's views or layout is imported here**, at import or
later. `imscribe.primitives` is: scaled points are the board's unit.

## Where the numbers come from

- A column's natural width and its floor are the library's
  (`TypesetView.table_column`: `natural`, `floor`), its width and the
  handles' places are the table's geometry as laid out (`table_geometry`,
  `table_column`, `table_row`), all asked once after a layout and kept until
  the document's height, the measure or the chosen widths change.
- **What a drag costs** is read from the library's own counters
  (`imtypeset.DocumentStats`: `TableRowsSet`, `TableCellsMeasured`): the third
  readout line is how many table rows the last drag's layout set again and
  how many cells it measured again. Counts.
- **A stated width is used as given by the library**, so squeezing chosen
  widths into a measure that became too narrow is this page's (`fitted`).
- **The handles are placed from the layout as it stands before the draw**
  (`TypesetView.layout_for`, then the geometry). The library lays a block out
  when the window first reaches it, so on a frame where blocks above a table
  are laid out for the first time (the first frame, a scroll into new text) a
  handle can be where the table was a frame ago; the next frame has it right.
- The debug overlay is the library's own (line boxes); `report()` has no
  glyph or missing-glyph count (the library reports neither); a table is
  never split into pieces of rows.
- **A defect of the library at `be40444` that shows**
  (`../imtypeset/docs/advtext-swap-status.md`): the rule under a header takes
  a whole line of height. (Another is gone at `7a7bc36`: a point on the blank
  part of a cell answered the next cell. This page never read it: the focus
  is the table under the pointer, and the block of a hit was right.)

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

Widths are clamped here, in `dragged` and `fitted`, before
`set_table_columns` is called: a mouse can ask for a width under one scaled
point or one that is not finite. A table that was dragged keeps the widths
that were chosen while they fit; when the measure becomes too narrow for them
they are squeezed toward the floors for as long as it stays narrow (`fitted`),
and come back when it widens.

## How the drag coexists with the view's selection drag

The view begins a selection on a left press over its rectangle unless *an
item of the host's is under the mouse*. So each handle is an
`invisible_button` this page submits **before** `view.draw()`, in the frame's
own geometry: `layout_for(width)` for the layout the draw is about to use,
the cursor snapped to a whole pixel for where it is about to put it, and the
table's geometry for the edges.

- a press on a handle is the handle's: the handle is already ImGui's hovered
  item when the view judges the press, on the very frame the pointer arrives;
- while the handle is held it is ImGui's active item, so the view's window is
  not "hovered" and the view begins nothing and follows no link;
- a press anywhere else on the text begins a selection as it always does;
- a selection made before a drag is still there afterwards.

A held handle is applied before the view draws, from the mouse position and
that origin, so the table follows the pointer on the frame it moves.

## The readouts report change and cost, never quality

A count of rows set again is a fact about what the library did. Whether a
table reads well at the widths somebody dragged it to is what the page exists
to let a person judge (`docs/visual-review.md`).

## What has been run

`tests/test_page_tables.py`: the arithmetic on its own; the page without the
library (its one line, its launch options); with the library, the page in
frames of a real ImGui context with no backend, with mouse events queued
(hover, press, move, release on a handle, and a press on text); and the real
app in a window with the same gesture injected, reporting counts. Nobody has
dragged a column with a hand.

Options (`--tab tables:...`): `floors` opens with every column of every table
at its floor; an integer is the pane's measure in pixels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from imscribe.primitives import DEFAULT_PX_PER_INCH, UNITY, Scaled, px_from_sp, sp_from_px
from imscribe.ui.ownership import MIN_WIDTH_PX
from imscribe.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from imscribe.ui.pages.typeset import say_why_not, why_not
from imscribe.ui.palette import DARK_PALETTE, rgba
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imscribe.theme import Theme

__all__ = [
    "DEFAULT_PANE_PX",
    "FALLBACK",
    "GRIP_PX",
    "PAGE",
    "Grip",
    "TablesPage",
    "TypesetBoard",
    "dragged",
    "fitted",
    "readouts",
    "typeset_report",
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

_ROUNDING_SP: Final = 8
"""
How far under its floor a width the library answered may be and still be "at the floor".

In scaled points: 8 is about a ten-thousandth of a pixel. The library answers
single-precision pixels (an edge near 700 px is good to about 6e-5 px).
"""

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
    What comes back is always whole widths at or above the floors.

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
    floor, the last column taking the rounding remainder so the sum is
    exact. When the floors alone exceed `available` they are
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

    `table` is the block's number in the view. `x`, `top` and `bottom` are
    document scaled points; the view's origin plus these in pixels is where it
    is on screen.
    """

    table: int
    edge: int
    x: Scaled
    top: Scaled
    bottom: Scaled


@dataclass
class TypesetBoard:
    """
    A document with tables in it over a `TypesetView`, and the column widths chosen so far.

    Everything the page does except the ImGui calls: `settle` is told the
    measure a frame is about to lay out at, `drag` and `reset` are the
    gestures, `grips` says where the handles are, `observe` counts what a
    drag made the library set again. The tables are the imtypeset library's
    blocks: a column's natural width and floor are
    `TypesetView.table_column`'s, its width and the handles' places are the
    table's geometry as laid out, and a drag is
    `TypesetView.set_table_columns`. Everything is kept in scaled points at
    the board's density (`dragged` and `fitted` are whole-number arithmetic);
    a pixel the library answers is converted once.

    **Nothing is known before the library has the document**, which is the
    first `lay_out` (the page calls it each frame before the handles): until
    then `columns`, `natural`, `floors` and `grips` are empty and a drag
    moves nothing. Raises `TypesetUnavailable` as the view does.
    """

    theme: Theme
    px_per_inch: float = DEFAULT_PX_PER_INCH
    text: str | None = None
    """The markdown to show in place of `demo/tables.md`. For a test, or a host's own."""

    view: TypesetView = field(init=False)
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
    rows_set: int | None = field(default=None, init=False)
    """How many table rows the latest drag's (or reset's) layout set again; `None` before any."""
    cells_measured: int | None = field(default=None, init=False)
    """How many cells that layout measured again. The library says none, for a drag."""
    relayouts: int = field(default=0, init=False)
    """How many times a drag or a reset has stated columns and a draw followed."""
    _limits: dict[int, tuple[tuple[Scaled, ...], tuple[Scaled, ...]]] = field(
        default_factory=dict, init=False
    )
    _lefts: dict[int, Scaled] = field(default_factory=dict, init=False)
    _automatic: dict[int, tuple[Scaled, tuple[Scaled, ...]]] = field(
        default_factory=dict, init=False
    )
    _stated: set[int] = field(default_factory=set, init=False)
    _laid: Scaled | None = field(default=None, init=False)
    _epoch: int = field(default=0, init=False)
    _grips: tuple[tuple[object, ...], tuple[Grip, ...]] | None = field(default=None, init=False)
    _drawn: bool = field(default=False, init=False)
    _pending: tuple[int, int] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        found = demo_text("tables.md") if self.text is None else self.text
        self.view = TypesetView(
            FALLBACK if found is None else found,
            theme=self.theme,
            palette=DARK_PALETTE,
            on_link=self.followed.append,
        )
        self.tables = tuple(self.view.tables)
        self.focus = self.tables[0] if self.tables else None

    # -- what a table's columns are ------------------------------------

    def _sp(self, pixels: float) -> Scaled:
        return sp_from_px(pixels, self.px_per_inch)

    def _known(self, table: int) -> tuple[tuple[Scaled, ...], tuple[Scaled, ...]]:
        """
        (natural widths, floors) of a table's columns, asked of the library once.

        Empty while the library has no document. A floor is rounded UP to a
        scaled point and is never under one: a column stated a fraction of a
        scaled point under its longest word would be under it.
        """
        if table not in self.tables:
            raise KeyError(f"block {table} is not a table")
        found = self._limits.get(table)
        if found is None:
            geometry = self.view.table_geometry(table)
            if geometry is None:
                return ((), ())
            columns = [self.view.table_column(table, n) for n in range(geometry.column_count)]
            floors: list[Scaled] = []
            for column in columns:
                floor = self._sp(column.floor)
                if px_from_sp(floor, self.px_per_inch) < column.floor:
                    floor += 1
                floors.append(max(1, floor))
            found = (tuple(self._sp(column.natural) for column in columns), tuple(floors))
            self._limits[table] = found
            self._lefts[table] = self._sp(geometry.min[0])
        return found

    def floors(self, table: int) -> tuple[Scaled, ...]:
        """
        Each column's longest unbreakable stretch, padding included: the library's `floor`.
        """
        return self._known(table)[1]

    def natural(self, table: int) -> tuple[Scaled, ...]:
        """
        Each column's widest cell set on one line, padding included: the library's `natural`.
        """
        return self._known(table)[0]

    def available(self, table: int) -> Scaled:
        """
        The width the table has at the current measure: the measure less the table's indent.
        """
        self._known(table)
        width = UNITY if self.width is None else self.width
        return max(width - self._lefts.get(table, 0), UNITY)

    def columns(self, table: int) -> tuple[Scaled, ...]:
        """
        The widths this table's columns are set to at the current measure.

        The chosen ones, squeezed if the measure has become too narrow for
        them; otherwise the library's own, read from the table as laid out,
        once for each measure. Empty before the first `lay_out`, and for an
        automatic table while the layout is at another measure than the
        board's.
        """
        if self.width is None or not self.floors(table):
            return ()
        wish = self.chosen.get(table)
        if wish is not None:
            return fitted(wish, self.floors(table), self.available(table))
        kept = self._automatic.get(table)
        if kept is None or kept[0] != self.width:
            geometry = None if self._laid != self.width else self.view.table_geometry(table)
            if geometry is None:
                return ()
            edges = [self.view.table_column(table, n) for n in range(geometry.column_count)]
            widths = [self._sp(edge.max - edge.min) for edge in edges]
            # A column the library squeezed to its floor is AT its floor: the
            # two are single-precision pixels, and the floor was rounded up,
            # so the difference of a few scaled points is rounding and not a
            # column under its longest word.
            floors = self.floors(table)
            widths = [
                floor if 0 < floor - width <= _ROUNDING_SP else width
                for width, floor in zip(widths, floors, strict=True)
            ]
            kept = (self.width, tuple(widths))
            self._automatic[table] = kept
        return kept[1]

    # -- the gestures ---------------------------------------------------

    def settle(self, width: Scaled) -> None:
        """
        Tell the board the measure the next layout is at. Call before `lay_out`.

        A change of measure with widths chosen states those tables again,
        since what fitted before may not now. That is not counted as a drag.
        """
        if width == self.width:
            return
        self.width = width
        if self.chosen:
            self._apply(counted=False)

    def lay_out(self, width_px: float) -> float:
        """
        Lay the document out for this frame, `width_px` wide: `TypesetView.layout_for`.

        After it the library has the document, and the columns and the
        handles are the ones of this measure. Returns the height, an
        estimate until every block has been in view.
        """
        height = self.view.layout_for(width_px)
        self._laid = self.width
        return height

    def drag(self, table: int, edge: int, x: float) -> bool:
        """
        Drag the right edge of column `edge` of `table` to document x `x`. True if anything moved.

        `x` is in the document's scaled points, as `Grip.x` is. Nothing
        before the first `settle` and `lay_out`.
        """
        if self.width is None or table not in self.tables:
            return False
        before = self.columns(table)
        if not before:
            return False
        after = dragged(
            before,
            self.floors(table),
            edge,
            x - self._lefts.get(table, 0),
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

        Nothing for a table the library has not been asked about yet (before
        the first `lay_out`).
        """
        for table in self.tables:
            floors = self.floors(table)
            if floors:
                self.chosen[table] = floors
        self._apply()

    def reset(self) -> bool:
        """
        Back to automatic: forget every chosen width. True if there was one.
        """
        if not self.chosen:
            return False
        self.chosen.clear()
        self._automatic.clear()
        self._apply()
        return True

    def _apply(self, counted: bool = True) -> None:
        """
        State the chosen widths in the view: one `set_table_columns` a table that changed.

        A table that is no longer chosen gets back the columns it was
        described with. The widths go over in pixels with each column's own
        alignment kept. `counted` says a drag or a reset caused this, for
        `observe`; a change of measure did not.
        """
        if counted and self._drawn and self._pending is None:
            self._pending = self._counters()
        for table in self.tables:
            if table in self.chosen and self.width is not None:
                widths = [px_from_sp(width, self.px_per_inch) for width in self.columns(table)]
                self.view.set_table_columns(table, widths)
                self._stated.add(table)
            elif table in self._stated:
                self.view.set_table_columns(table, None)
                self._stated.discard(table)
        self._epoch += 1

    def _counters(self) -> tuple[int, int]:
        """(table rows set, table cells measured) so far, by the library's own count."""
        doc = self.view.native_document
        if doc is None:
            return (0, 0)
        stats = doc.stats()
        return (int(stats.TableRowsSet), int(stats.TableCellsMeasured))

    # -- where the handles are, and what a relayout cost -----------------

    def grips(self) -> tuple[Grip, ...]:
        """
        Every handle of the layout as it stands, top to bottom and left to right.

        Empty before the first `lay_out`, and while the layout is at a
        measure other than the board's. A handle's x is the table's left
        edge and its columns' widths (`columns`); its top and bottom are the
        table's as the library laid it out, asked once (a call a table) and
        kept until the measure, the document's height or the chosen widths
        change.
        """
        if self.width is None or self._laid != self.width:
            return ()
        key = (self.width, self.view.height, self._epoch, self.view.revision)
        if self._grips is not None and self._grips[0] == key:
            return self._grips[1]
        out: list[Grip] = []
        for table in self.tables:
            widths = self.columns(table)
            geometry = self.view.table_geometry(table)
            if not widths or geometry is None or geometry.row_count == 0:
                continue
            top, bottom = self._sp(geometry.min[1]), self._sp(geometry.max[1])
            x = self._lefts.get(table, 0)
            for edge, width in enumerate(widths):
                x += width
                out.append(Grip(table, edge, x, top, bottom))
        self._grips = (key, tuple(out))
        return self._grips[1]

    def observe(self) -> int | None:
        """
        Count what the latest draw set again, if a drag or a reset caused it.

        Call after the view has drawn. The counts are the library's own
        (`DocumentStats.TableRowsSet`, `TableCellsMeasured`), taken before the
        columns were stated and after the draw that followed. A layout at a
        new measure is not counted, and neither is the opening state.
        Returns the rows set again, or `None` when nothing was counted.
        """
        self._drawn = True
        before, self._pending = self._pending, None
        if before is None:
            return None
        rows, cells = self._counters()
        self.rows_set, self.cells_measured = rows - before[0], cells - before[1]
        self.relayouts += 1
        return self.rows_set


def readouts(board: TypesetBoard) -> tuple[str, ...]:
    """
    The four readout lines, top to bottom. Always four, so the pane below does not move.

    Widths in pixels at the board's density. Counts and sizes; no judgement.
    """
    table = board.focus
    widths = () if table is None or board.width is None else board.columns(table)
    if table is None or not widths:
        about = "no table in this document" if table is None else "not laid out yet"
        return (about, "", _last_drag(board), _links(board))
    density = board.px_per_inch
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


def _last_drag(board: TypesetBoard) -> str:
    if board.rows_set is None:
        return "last drag: none yet"
    return (
        f"last drag: {board.rows_set} table rows set again, "
        f"{board.cells_measured} cells measured again (the library's own counts)"
        f"  ·  layouts caused by dragging so far: {board.relayouts}"
    )


def _links(board: TypesetBoard) -> str:
    hovered = board.view.hovered_link
    last = board.followed[-1] if board.followed else "none yet"
    return (
        f"link under the pointer: {hovered or 'none'}"
        f"  ·  clicked: {len(board.followed)}, last: {last}"
    )


def _table_lines(board: TypesetBoard) -> list[str]:
    lines: list[str] = []
    for table in board.tables:
        widths = board.columns(table)
        floors = board.floors(table)
        lines.append(
            f"table={table} columns={len(widths)} "
            f"width_sp={sum(widths)} "
            f"under_floor={sum(1 for w, f in zip(widths, floors, strict=False) if w < f)} "
            f"state={'dragged' if table in board.chosen else 'automatic'}"
        )
    return lines


def typeset_report(board: TypesetBoard, frames: int, whole: bool | None) -> list[str]:
    """
    What an unattended run prints: one line of totals and one a table. Counts, not judgements.

    `selected` is the characters a copy of the selection gives. There is no
    count of glyphs and none of glyphs missing (the library reports neither):
    `vertices` is what the last draw added to the draw list and `whole`
    whether the library set everything in view as asked.
    """
    view = board.view
    stats = view.stats
    lines = [
        f"frames={frames} renderer=TypesetView tables={len(board.tables)} "
        f"dragged={len(board.chosen)} "
        f"rows_set={-1 if board.rows_set is None else board.rows_set} "
        f"cells_measured={-1 if board.cells_measured is None else board.cells_measured} "
        f"relayouts={board.relayouts} "
        f"selected={len(view.selected_text()) if view.selection is not None else 0} "
        f"vertices={stats.vertices} whole={-1 if whole is None else int(whole)}"
    ]
    return lines + _table_lines(board)


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


class TablesPage:
    """
    The page: a board, the frame that draws it, and the handles over the view.

    `board` is a `TypesetBoard` while the imtypeset library draws and `None`
    when it does not; `reason` then says why, and is the one line the page
    draws. `renderer` is `"TypesetView"` or `"none"`.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.reason = why_not()
        self.board: TypesetBoard | None = None
        if not self.reason:
            try:
                self.board = TypesetBoard(theme=context.theme, px_per_inch=context.px_per_inch)
            except TypesetUnavailable as exc:
                self.reason = str(exc)
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
        self.whole: bool | None = None
        """What `TypesetView.draw` answered last; `None` before the first and with no board."""
        self.frames = 0

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.board is not None else "none"

    def report(self) -> list[str]:
        """
        `typeset_report` of this page's board with the frames it has drawn, or why there is none.
        """
        if self.board is None:
            return [f"frames={self.frames} renderer=none reason={self.reason!r}"]
        return typeset_report(self.board, self.frames, self.whole)

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        board = self.board
        if board is None:
            say_why_not(self.reason)
            return
        try:
            self._frame(imgui, board)
        except TypesetUnavailable as exc:
            # The library was switched off under the view. Whatever of the
            # controls this frame had submitted stays; the page is the one
            # line from the next frame on.
            self.reason = str(exc) or "imtypeset is not ready"
            self.board = None
            self.held, self.whole = None, None

    def _frame(self, imgui: Any, board: TypesetBoard) -> None:
        """
        The controls, the readouts and the pane. Every call of the view's is in here.
        """
        self._controls(imgui, board)
        for line in readouts(board):
            caption(line)
        imgui.separator()

        # A vertical scrollbar that is always there: a row that grows as its
        # column narrows can push the document past the window, and a
        # scrollbar appearing would change the measure under the drag.
        imgui.begin_child(
            "##imscribe-tables",
            imgui.ImVec2(0.0, 0.0),
            imgui.ChildFlags_.borders.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        try:
            width_px = max(min(imgui.get_content_region_avail().x, self.pane_px), MIN_WIDTH_PX)
            self._draw_typeset(imgui, board, width_px)
        finally:
            imgui.end_child()

    def _draw_typeset(self, imgui: Any, board: TypesetBoard, width_px: float) -> None:
        """
        One frame through `TypesetView`: lay out, follow the held handle, the handles, the draw.
        """
        board.settle(sp_from_px(width_px, board.px_per_inch))
        # Where the view is about to draw: its `draw` snaps the cursor to a whole pixel.
        cursor = imgui.get_cursor_screen_pos()
        origin = (math.floor(cursor.x + 0.5), math.floor(cursor.y + 0.5))
        board.lay_out(width_px)
        again = False
        if self._to_floors:
            self._to_floors = False
            board.to_floors()
            again = True
        if self._follow(imgui, board, origin) or again:
            # The columns moved: the rows below them are other heights now.
            board.lay_out(width_px)
        self._handles(imgui, board, origin)
        board.view.debug = self.context.debug
        self.whole = board.view.draw(palette=DARK_PALETTE, width_px=width_px)
        board.observe()

    def _controls(self, imgui: Any, board: TypesetBoard) -> None:
        if imgui.button("Reset to automatic"):
            board.reset()
        imgui.same_line()
        imgui.set_next_item_width(260.0)
        changed, pane = imgui.slider_float(
            "measure, px", self.pane_px, MIN_PANE_PX, MAX_PANE_PX, "%.0f"
        )
        if changed:
            self.pane_px = min(max(float(pane), MIN_PANE_PX), MAX_PANE_PX)
        imgui.same_line()
        debug_toggle(self.context)

    def _follow(self, imgui: Any, board: TypesetBoard, origin: tuple[float, float]) -> bool:
        """
        Move the held handle to the pointer, before the view draws. True if a column moved.

        `origin` is where the view is about to draw. A handle
        whose button is no longer down is let go here; ImGui lets go of the
        item itself.
        """
        if self.held is None:
            return False
        if not imgui.is_mouse_down(imgui.MouseButton_.left):
            self.held = None
            return False
        table, edge = self.held
        x_px = imgui.get_mouse_pos().x - self._grab - origin[0]
        if not math.isfinite(x_px):
            return False
        return board.drag(table, edge, sp_from_px(x_px, board.px_per_inch))

    def _handles(self, imgui: Any, board: TypesetBoard, origin: tuple[float, float]) -> None:
        """
        One invisible button a column edge, where the view is about to draw. Call inside its child.

        Submitted before the view, so that each is an item by the time the
        view judges a press (the module docstring). `origin` is where the
        view is about to draw and the view has been laid out for this frame.
        The cursor is put back afterwards, to where the view starts
        (`cursor_drift` is the check): the buttons are inside the rectangle
        the view is about to claim and add nothing to the child's content.
        """
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
                f"##imscribe-tables-grip-{grip.table}-{grip.edge}", imgui.ImVec2(GRIP_PX, height)
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

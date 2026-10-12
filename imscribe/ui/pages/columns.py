r"""
The Columns page: one document shown in 1, 2 or 3 newspaper columns by imtypeset.

The page draws through `imscribe.ui.typeset_view.TypesetView.set_columns` and
through nothing else. The cutting is the library's ("Columns" in
`../imtypeset/include/imtypeset.h`, commit `0b21807`): text continues from
the foot of one column to the head of the next, and the column count is a
control rather than a constant, because the *reflow* is the demonstration.
Until tranche 5 this page cut the old core's vertical list with
`imscribe.columns` and drew each piece with the old ImGui backend; none of
that is imported here, and there is no fallback to it.

## When the library is not loaded

`imscribe.typesetter.ready()` false: the page draws ONE wrapped line,
`NOT_DRAWING` and `imscribe.ui.pages.typeset.why_not()`, and nothing else: no
controls, no view, no old view. A `TypesetUnavailable` out of a draw (the
library failed and was switched off) is shown the same way, in that frame
and every one after, for as long as the page object lives; any other
exception is a bug and leaves the page.

**The page asks `ready()` and never `typesetter.module()`** before it is
ready (`imscribe/ui/pages/typeset.py` has why): it is built in the pytest
process by every page-enumerating test, where the library is kept out.

## The controls, and what each is in the library's terms

- **1 / 2 / 3** (and the launch's own count, `--tab columns:5`): `count`,
  how many columns stand across the sheet. One column is
  `(sheet - gutter * (count - 1)) / count` wide, and the document is laid
  out at that width.
- **balance** off (as the page opens): `set_columns(count, height=h)`,
  columns **filled in order**, the old core's fill. `h` is the visible
  height of the pane, so a column is as tall as the window and the reader
  sees a whole page of `count` columns at once. The document makes as many
  columns as it needs; those past `count` are the old `ColumnSplit.overflow`
  and stand further right in the same pane, which scrolls SIDEWAYS. **Pages
  of `count` columns** are that scroll in steps: page `p` is the page moved
  left by `p * count * (column width + gutter)` under the pane's clip
  rectangle (`Previous page` / `Next page`, and the scrollbar).
- **balance** on: `set_columns(count, balance=True)`, exactly `count`
  columns of one height, the least that holds the document; the pane
  scrolls down. **This is new and is not the reference's**: `imscribe.columns`
  never balanced (its docstring: "Balance: not done"). With one column
  there is nothing to balance and the document is shown uncut.
- **debug overlay**: the library's own overlay, as on every page.

The sheet is the pane's width, held to `count` columns of at most
`TEXT_WIDTH_PX` each (the widest the Find and Typeset pages set text) and
centred.

## What the old page showed that this one does not

- *Sheets stacked down a scroll, a paper colour behind each, a hairline in
  each gutter.* Gone: the view paints no page, and one document is drawn
  once (so that a selection can run through every column). Pages are side
  by side and reached by scrolling sideways.
- *The sheet arithmetic of `imscribe.ui.app.column_page`* (margins from the
  alphabet's length, a sheet that grows with the count). Replaced by the
  width rule above, in pixels.
- *"N node(s) past 24 pages are not shown".* There is no cap: columns are
  cut when they are reached, so nothing is dropped and nothing is counted
  as dropped.

What it shows instead (`lines()`): how many columns there are and whether
that is still the library's estimate, one column's width and height, the
gutter, and which page of how many.

## What the library's columns do that a reader of this page will meet

This page was written against imtypeset commit `0b21807`, the first with
columns, and its list of that commit's known defects. **The library pinned
now is `7a7bc36`**, where the other team's document
(`../imtypeset/docs/advtext-swap-status.md`, "Known defects in columns at
`0b21807`: fixed in `7a7bc36`") strikes most of that list out. What that
document says is STILL so at `7a7bc36`, on this page's document
(`demo/columns.md`: headings and paragraphs, no table and no hosted block):

- **Columns do not share a first baseline**: a column that starts with a
  heading has its first baseline lower than its neighbours'.
- **A cut can leave one line of a paragraph alone** at the head or the foot
  of a column: the line breaker hands over no club or widow penalties.

And what is the design and not a defect: **how many columns there are is an
estimate** until the last has been reached, so "page 1 of 6" can become "of
5" as the reader scrolls. The page says "about" while any block is not yet
laid out.

Said fixed there in `7a7bc36`, none of them met by this document and none
measured from this page: a table cut between its header and the rule under
it; a column ending after a heading that is followed by an empty block;
`overfull` under balance; overflow the library's own `DocumentView` could
not scroll to. The one fix that WAS measured in this tree is the view's (a
caret asked for before the columns are cut that far:
`imscribe/ui/typeset_view.py`, "Columns").

Nobody has looked at this page. `tests/test_page_columns.py` counts columns,
calls and vertices; `report()` prints counts.
"""

from __future__ import annotations

import math
from typing import Any, Final

from imscribe.ui.ownership import MIN_WIDTH_PX
from imscribe.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from imscribe.ui.pages.typeset import why_not
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import MAX_COLUMNS, TypesetUnavailable, TypesetView

__all__ = [
    "COLUMN_COUNTS",
    "DEFAULT_COUNT",
    "FALLBACK",
    "NOT_DRAWING",
    "PAGE",
    "TEXT_WIDTH_PX",
    "ColumnsPage",
    "pages_of",
    "sheet_width",
]

COLUMN_COUNTS: Final = (1, 2, 3)
"""The column counts the page offers as buttons. `--tab columns:5` adds its own."""

DEFAULT_COUNT: Final = 2
"""How many columns the page opens with when the launch names none."""

TEXT_WIDTH_PX: Final = 600.0
"""The widest one column is set, as the Find and Typeset pages' text is."""

MIN_HEIGHT_PX: Final = 80.0
"""The shortest a column is made, in a pane with next to no height."""

NOT_DRAWING: Final = "imtypeset is not drawing: "
"""What the one line starts with when the library is not ready."""

BALANCE_NOTE: Final = (
    "balanced: the least height at which this many columns hold the document  ·  "
    "new, not the reference's (imscribe.columns never balanced)"
)

DEFECTS_NOTE: Final = (
    "known in the library as pinned (7a7bc36): columns do not share a first baseline, "
    "and a cut can leave one line of a paragraph alone"
)

FALLBACK: Final = (
    "No `demo/columns.md` was found, so this paragraph, said a few times over, is the "
    "whole document. It is long enough to be cut into columns.\n\n"
) * 12


def sheet_width(available: float, count: int, gutter: float) -> float:
    """
    How wide `count` columns are drawn across a pane `available` pixels wide.

    All of the pane, up to `count` columns of `TEXT_WIDTH_PX` and the
    gutters between them; never less than a view can be laid out at.
    """
    widest = count * TEXT_WIDTH_PX + gutter * (count - 1)
    return max(min(float(available), widest), MIN_WIDTH_PX)


def pages_of(columns: int, count: int) -> int:
    """
    How many pages of `count` columns `columns` columns make: the last may be part empty.
    """
    return max(math.ceil(max(columns, 1) / max(count, 1)), 1)


class ColumnsPage:
    """
    One document in columns, a count, a fill, and which page of them is in view.

    `reason` is why the library is not drawing, or `""`. The state the
    controls move (`count`, `balance`, the page asked for) needs no library
    and is what the tests without one read.
    """

    def __init__(self, context: PageContext, text: str | None = None) -> None:
        self.context = context
        if text is None:
            text = getattr(context, "columns_source", None)
        if text is None:
            text = getattr(context, "source", None)
        if text is None:
            text = demo_text("columns.md")
        if text is None:
            text = FALLBACK
        self.text = text
        """The markdown on show."""
        asked = context.count_for(PAGE.name)
        self.count = asked if asked is not None else DEFAULT_COUNT
        """How many columns stand across the sheet."""
        self.counts: tuple[int, ...] = tuple(sorted({*COLUMN_COUNTS, self.count}))
        """The counts offered as buttons."""
        self.balance = "balance" in context.options_for(PAGE.name)
        """Whether the columns are balanced (new) and not filled in order."""
        self.view: TypesetView | None = None
        self._failure = ""
        self.reason = why_not()
        self.frames = 0
        self.vertices = 0
        """Vertices the view added to the pane's draw list in the last frame."""
        self.columns = 1
        """How many columns the library said there were at the last frame."""
        self.settled = False
        """Whether that is exact: every block has been laid out."""
        self.page = 0
        """The page in view at the last frame, from 0: read off the pane's scroll."""
        self.height_px = 0.0
        """How tall a column was made at the last frame (in order), or the page (balanced)."""
        self._turn_to: int | None = None

    # -- what the controls do: no library, no ImGui -----------------------

    def pick(self, count: int) -> None:
        """
        What a count button does: that many columns across the sheet, from the first page.
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError(f"a column count is an integer of 1 or more, not {count!r}")
        if count != self.count:
            self.count = count
            self.counts = tuple(sorted({*self.counts, count}))
            self._turn_to = 0

    def set_balance(self, balance: bool) -> None:
        """
        What the balance checkbox does. Either way the reader is back at the first page.
        """
        if bool(balance) != self.balance:
            self.balance = bool(balance)
            self._turn_to = 0

    @property
    def pages(self) -> int:
        """
        How many pages of `count` columns there are: 1 when balanced or uncut.
        """
        return 1 if self.balance else pages_of(self.columns, self.count)

    def turn(self, delta: int) -> int:
        """
        What Previous page (`-1`) and Next page (`+1`) do; the page asked for, from 0.

        Held to the pages there are. Carried out by the next `draw`, which
        scrolls the pane sideways by whole pages.
        """
        base = self.page if self._turn_to is None else self._turn_to
        self._turn_to = min(max(base + int(delta), 0), self.pages - 1)
        return self._turn_to

    def columns_wanted(self, height_px: float) -> dict[str, Any] | None:
        """
        What `TypesetView.set_columns` is given for the controls as they stand; `None` is uncut.

        `height_px` is the pane's visible height. Balanced: `count` columns
        of one height, or uncut for a count of one. In order: columns
        `height_px` tall.
        """
        if self.balance:
            return {"count": self.count, "balance": True} if self.count >= 2 else None
        return {"count": self.count, "height": max(float(height_px), MIN_HEIGHT_PX)}

    def lines(self) -> tuple[str, ...]:
        """
        The captions under the controls: what the column geometry gives, and what to know.
        """
        if self.reason:
            return (NOT_DRAWING + self.reason,)
        view = self.view
        if view is None or view.columns is None:
            fill = "uncut: one balanced column is the whole document"
            return (f"renderer: TypesetView  ·  {fill}", BALANCE_NOTE)
        about = "" if self.settled else "about "
        shape = (
            f"{about}{self.columns} columns of {view.column_width:.0f} px, "
            f"{self.height_px:.0f} px tall, gutter {view.columns.gutter:.1f} px"
        )
        if self.balance:
            return (
                f"renderer: TypesetView in columns (imtypeset)  ·  {shape}",
                BALANCE_NOTE,
                DEFECTS_NOTE,
            )
        where = f"page {self.page + 1} of {about}{self.pages}, {self.count} columns a page"
        return (
            f"renderer: TypesetView in columns (imtypeset)  ·  {shape}",
            f"filled in order: text continues from the foot of one column to the head of "
            f"the next  ·  {where}",
            DEFECTS_NOTE,
        )

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts.
        """
        view = self.view
        width = 0.0 if view is None else view.column_width
        return [
            f"frames={self.frames} renderer={'none' if self.reason else 'TypesetView'} "
            f"count={self.count} balance={int(self.balance)} columns={self.columns} "
            f"settled={int(self.settled)} pages={self.pages} page={self.page} "
            f"column_width={width:.3f} height={self.height_px:.3f} vertices={self.vertices}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        # A failure under the page stays said, whatever is ready afterwards:
        # `imscribe.ui.app.App.retry` builds the page anew.
        self.reason = self._failure or why_not()
        if self.reason:
            # The one line, and nothing else: no controls, no view.
            self.view = None
            imgui.text_wrapped(NOT_DRAWING + self.reason)
            return
        self._controls(imgui)
        for line in self.lines():
            caption(line)
        imgui.separator()
        try:
            self._draw_columns(imgui)
        except TypesetUnavailable as exc:
            # The library failed under the page and is switched off: the
            # same line, from this frame on. Nothing else is caught.
            self.view = None
            self.reason = self._failure = why_not() or str(exc)
            imgui.text_wrapped(NOT_DRAWING + self.reason)

    def _controls(self, imgui: Any) -> None:
        debug_toggle(self.context)
        for count in self.counts:
            imgui.same_line()
            if imgui.radio_button(f"{count}##columns", self.count == count):
                self.pick(count)
        imgui.same_line()
        caption("columns")
        imgui.same_line()
        changed, balance = imgui.checkbox("balance (new)", self.balance)
        if changed:
            self.set_balance(balance)
        if not self.balance:
            imgui.same_line()
            if imgui.button("Previous page"):
                self.turn(-1)
            imgui.same_line()
            if imgui.button("Next page"):
                self.turn(1)

    def _draw_columns(self, imgui: Any) -> None:
        """
        The sheet: a child as wide as `count` columns, the view in it, and the pane's scroll.

        In order the child scrolls sideways and its scrollbar is always
        there, so that a column's height does not depend on whether the
        document overflows the first page.
        """
        view = self.view
        if view is None:
            view = self.view = TypesetView(
                self.text, theme=self.context.theme, palette=DARK_PALETTE, math=True
            )
        view.debug = self.context.debug
        gutter = view.default_gutter() if view.columns is None else view.columns.gutter
        available = imgui.get_content_region_avail()
        width = sheet_width(available.x, self.count, gutter)
        # Centred in the pane, on a whole pixel.
        imgui.set_cursor_pos_x(
            imgui.get_cursor_pos_x() + math.floor(max(available.x - width, 0.0) / 2.0)
        )
        flags = 0 if self.balance else imgui.WindowFlags_.always_horizontal_scrollbar.value
        imgui.begin_child("##imscribe-columns", imgui.ImVec2(width, 0.0), 0, flags)
        try:
            inside = imgui.get_content_region_avail()
            wanted = self.columns_wanted(math.floor(inside.y))
            if wanted is None:
                view.set_columns(None)
            else:
                view.set_columns(**wanted)
            # What `count` columns stand across: the pane, less its scrollbar.
            across = max(inside.x, MIN_WIDTH_PX)
            vertices = imgui.get_window_draw_list().vtx_buffer
            before = vertices.size()
            view.draw(palette=DARK_PALETTE, width_px=across)
            self.vertices = vertices.size() - before
            self.columns = view.column_count()
            self.settled = view.stats.blocks_deferred == 0
            self.height_px = view.height
            if self.balance or view.columns is None:
                self.page, self._turn_to = 0, None
                return
            # A page is `count` columns and the gutter after them.
            pitch = self.count * (view.column_width + view.columns.gutter)
            # So that the last page can be scrolled to whole, though it may
            # hold fewer columns than `count`.
            short = self.pages * pitch - view.columns.gutter - view.width
            if short > 0.5:
                imgui.same_line(0.0, 0.0)
                imgui.dummy(imgui.ImVec2(short, 1.0))
            if self._turn_to is not None:
                self._turn_to = min(self._turn_to, self.pages - 1)
                imgui.set_scroll_x(self._turn_to * pitch)
                self.page, self._turn_to = self._turn_to, None
            else:
                self.page = min(
                    max(math.floor(imgui.get_scroll_x() / pitch + 0.5), 0), self.pages - 1
                )
        finally:
            imgui.end_child()


PAGE = PageSpec(
    name="Columns",
    order=20,
    factory=ColumnsPage,
    group="Typesetting",
    caption="the same material flowed into one, two or three columns",
    options=("balance",),
    shots=("1", "2", "3"),
    # `TypesetView.set_columns` refuses more: said to the launch, not to a frame.
    max_count=MAX_COLUMNS,
)

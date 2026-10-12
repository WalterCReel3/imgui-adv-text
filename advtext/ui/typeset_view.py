r"""
The embeddable view again, over ONE retained `imtypeset.Document`.

**Experimental** (branch `experimental/imtypeset-adoption`, step A2 of
`../imtypeset/docs/advtext-rework-plan.md` section 6.3). Of the facade:
`TypesetView`, `TypesetUnavailable`, `SetLine`, `HostFor` and `Hosted`; the
rest is reached from here. It is not a name of `advtext.ui`.

`TypesetView` has the shape of `advtext.ui.bare_view.BareView`: a `draw()`
called inside the host's own (usually scrolling child) window, at the cursor,
as wide as the pane, which leaves one item as ImGui's last item. What is
different is who sets the text. `BareView` breaks, ships and draws every block
in Python; this hands the blocks to the library once per edit and then, each
frame, makes a fixed number of calls whatever the document's length.

## What goes in: markdown source, and no old-core object on the way

    view = TypesetView(source, theme=theme, math=True)     # a str of markdown

A string is read by `advtext.typeset_markdown.parse_markdown` (text and runs
straight from the parser's tokens: no node, no font metrics) and described by
its `MarkdownConverter`. The view keeps the string and the source map.
`parse_markdown`'s blocks, or a `MarkdownDocument`, may be handed over
instead. Nothing else is taken: until tranche 5 the node material of
`advtext.markdown` was too, walked by `advtext.typesetter.Converter`, and that
path is deleted with the converter.

`tests/test_typeset_view.py` holds what the view describes equal, on every
markdown file under `demo/`, to what that old path described (frozen in
`tests/data/material_descriptions.json`): texts, block shapes, styles, links,
tables. What differs, and is meant to (`.concerns/SW-2--builder--result.md`):
which run a white-space character is in.

## When it can be used, and what happens when it cannot

- The constructor raises `TypesetUnavailable` naming
  `advtext.typesetter.reason()` when `typesetter.module()` is `None`.
- `draw()` raises `TypesetUnavailable` when `typesetter.ready()` is false (the
  fonts were never given: `typesetter.load_fonts()` belongs in the host's
  `load_additional_fonts`), and when the library fails mid-draw, in which case
  it has also called `typesetter.disable(why)`.
- **Only the library's own failure switches it off** (`library_failed`): an
  exception the `imtypeset` package defines. Anything else raised under a
  call into the library -- a slip in this module's Python, a `TypeError` or
  `ValueError` for an argument the package refused -- leaves as itself with
  the library still in use. It is a bug and is not to be caught as "the
  library is unavailable". Until 2026-10-11 (T5-FINAL) every exception was
  taken for the library's and switched it off for the process;
  `TypesetDiffView` already sorted them, and the three views now share the
  one rule.

There is no other renderer to draw with instead (the old views are deleted);
**this class never silently draws nothing.** `draw()` opens no window, pushes
no ID and no style, so an exception out of it leaves ImGui's stacks as the
host had them, and the host can say so at the same cursor in the same frame:

    try:
        typeset_view.draw(palette=palette)
    except TypesetUnavailable as exc:
        imgui.text_wrapped(str(exc))

## Calls into the library, per frame

`layout`, `draw`, `size`: three, in that order (the size is stale until the
draw has laid out what the window shows). The draw names no draw list
(`Document.draw(None, pos)` is the current window's), so
`typesetter.window_draw_list()` is not used. Then one `block_geometry` for
each hosted block in view: **3 + hosted blocks in view**, which does not grow
with the document; a table is the library's own block and costs no call of
its own. Two more while any ink is set (`set_colours`). Then one more, at
most:

- a `hit_test` while the mouse is over the text and no drag is on (the link
  under it, in a table cell too, and `under_mouse`);
- or a `select_range` on each frame of a drag.

Not per frame: the frame of a press makes both (five in all); a waiting
`scroll_to` adds one `block_geometry` or `caret_rect`; a copy is one
`range_text`; an edit is one `replace_blocks`; a change of the palette's rule
ink is one `set_options` and of its role inks one `set_blocks`
(`set_palette` has each part's cost); a hosted block whose widget changed
height is one `set_block_extent`; and on a frame where that happened, or the
document's height changed, one `block_geometry` for every hosted block of
the document. Reading `stats` is one call, `span_rects` one, `set_lines` one
a block and one a line, `table_geometry`, `table_column` and `table_row` one
each, `set_table_columns` one. `tests/test_typeset_view.py` and
`tests/test_typeset_hosts.py` count them.

**In columns** (`set_columns`) a frame is the same three. The draw after the
columns changed makes one `set_columns` first. Hosted blocks cost otherwise:
two `column` calls, then a `block_geometry` and a `column_pos` for each hosted
block in the columns the window shows ("Columns" below). `column_count`,
`column` and `column_pos` are one call each when a host asks, and a
`scroll_to` a position asks `column_count` before its `caret_rect`.

## What is `BareView`'s, kept

- **No item while idle.** The rectangle is claimed with `imgui.dummy`; an
  `invisible_button` is there only from a press on the text until the release,
  so the press does not drag the host's window. A press begins a selection only
  in the hovered window, inside the view, with no item of the host's under the
  mouse (`BareView`'s module docstring has the reasons).
- **A drag is anchored to text.** The fixed end is the range the press
  selected (a caret, a word for a double click, a line for a triple), kept as
  `(block, offset)` positions, which keep their meaning at another width.
- **A view not drawn for a frame has stopped dragging**, and stopped holding a
  link down.
- **One selection is current across every view in the process**
  (`advtext.ui.bare_view.SELECTION_OWNERSHIP`, the same counter): only the
  owner answers Ctrl+C and Ctrl+A, and never while ImGui has a text input
  active. `copy_as` replaces what Ctrl+C writes; NUL goes to the clipboard as
  `CLIPBOARD_NUL`.
- **Links.** With `on_link`, a press and a release on the same link call it,
  a press on a link begins no selection, and the hand cursor is asked for.
  Links are drawn in the palette's `link` ink when live (`style_links`
  overrides).
- **`scroll_to`** is callable from anywhere and carried out by the next
  `draw`; `scrolled` says whether that draw moved the pane.
- The origin is snapped to a whole pixel and the width floored at
  `MIN_WIDTH_PX`.

## What is different, and what has no counterpart

- **`fonts=` is accepted and ignored.** The library draws from the faces
  `typesetter.load_fonts()` gave it (its own copies in the atlas).
- **`draw` returns a `bool`**, the library's "everything in view was set as
  asked", not a `DrawStats`: the library counts no glyphs and reports none
  missing, so a `DrawStats` could only be made up. `stats` (a `ViewStats`) is
  what a page that printed `stats.glyphs` reads instead: the vertices the
  frame added, what was in view, and the library's own counters for the
  document. *Decided in tranche 3; every caller that only tests the bool is
  served as before.*
- **The selection is `((block, offset), (block, offset))`** into the described
  texts (`texts`), or `None`; not `advtext.selection.Selection` integers.
- **`hovered_link` answers with or without `on_link`**: the hit test is made
  either way.
- **Colour.** `Palette.ink`, `highlight` and `rule` (rules and quote bars)
  apply and may change between frames. `Palette.roles` (an ink per block
  kind) applies: the ink is in the block's style as the library holds it, so
  changing the roles hands the document over again and parses nothing.
  `Palette.link` is in the runs, so changing it describes the document again.
  `set_palette` says what each costs and the tests count it. `page` is not
  applied: the view paints no page (a host that wants a sheet draws one and
  gives `draw` the measure as `width_px`). A link is coloured and not
  underlined. `set_colours` lays inks over ranges of a block (syntax
  colour), as marks, beside `set_marks`.
- **Copy** is the library's: within a block the text as written, a blank line
  (`separator`) between blocks, and **nothing, and no separator, for a block
  with no text**: a rule. No list marker. So copying everything gives
  `separator.join(text for text in view.texts if text)`, formulas as their
  source without dollars. A table gives its cells (next item).
- **Tables are the library's** ("Tables" below): selected, copied, searched
  and marked cell by cell.
- **The height is an estimate** until every block has been in view once: the
  library lays a block out when the window first reaches it. `scroll_to`
  therefore goes on correcting itself for a few frames (`_SCROLL_FRAMES`).
- **Of `BareView`'s members, built here to what a demo page reads**
  (tranche 3): `host_for` / `hosted` (next section); the source map
  (`source`, `source_of`, `block_source`, `selected_blocks`,
  `selected_source`, `block_text`); `block_under_mouse`; `set_colours` /
  `clear_colours`; `span_rects`; `set_lines` (lines as text ranges and
  rectangles, not glyphs); `layout_for` (pixels in, the height out); `debug`
  (the library's own overlay); `stats`; `set_theme`.
- **Not built, and why**: `relayouts` and `layout` / `layout_stats` (there is
  no layout object on this side; `revision`, `edits` and
  `stats.blocks_laid_out` are the counts there are); `viewport_in` and
  `visible_links` (the library culls; `stats.blocks_drawn` counts);
  `to_screen` and `document_point` (every rectangle here is already pixels,
  from `origin`); `measure`, `px_per_inch`, `invalidate`, `next_origin`,
  `unmapped_blocks`, `pointed` (no counterpart is needed or possible); a
  `page()` (the Document page's sheet is `draw(width_px=measure)` at a cursor
  a margin in: what is lost is the measure worked out from the alphabet's
  length, which the host now states in pixels).

## Tables

A table is ONE block of the library's document (`KIND_TABLE`; imtypeset
commit `be40444`): `advtext.description` has its shape and both converters
make it. The view draws nothing of it and asks nothing about it in a frame.
`tables` lists the table blocks' numbers; `texts[n]` of a table is its cells'
texts, a tab between the cells of a row and a newline between rows, and
positions index that as they index any block's text.

- **Selection and copy** are the library's and work in cells: a drag from one
  cell into another takes everything between the two in reading order,
  whatever the mouse crossed, and a copy gives each cell's text with a tab
  between the cells of a row and a newline between rows.
- **Links in cells** are tags in the cells' runs: `hovered_link`, `on_link`
  and `links` (ranges of the block's text) serve them as anywhere else.
- **Marks and inks** (`set_marks`, `set_colours`) draw in cells;
  `advtext.typeset_find` searches each cell.
- **The rule and the padding** are the theme's (`Theme.table_rule_thickness`,
  `Theme.cell_padding`) and the rule's ink is `Palette.rule`, handed over as
  document options. `Palette.roles`' TABLE ink is the block style's.
- **Columns a host states**: `set_table_columns(block, columns)` (a drag of a
  column's edge), read back with `table_geometry`, `table_column` (edges,
  `natural`, `floor`) and `table_row`. A `SizedTable` (old core) or a
  `MarkdownTable` with `widths` / `shares` states them in the description.

**What the library's rule reproduces of the old core's, measured** (2026-10-11,
`demo/tables.md`, 684 px, five tables, `.concerns/T4-TABLES-scripts/compare_tables.py`):
every column's width, natural width and floor, and every row's height, equal
`advtext.ui.table_columns` / `table_column_limits` / `_table_boxes` to within
0.001 px, fitted, scaled up and squeezed alike.

**What differs**, each measured or read where it says:

- *The rule under a header takes a whole line of height* (21.6 px at the
  stock sizes) whatever its thickness, where the old core's took its
  thickness (0.96 px): a table with a header is 20.64 px taller. Measured.
- *A cell has no hard break*: a newline in a cell is white space.
- *A copy* is tab- and newline-joined cells from the cell the range starts
  in to the cell it ends in; the old core padded a short row with tabs and
  dropped a tab with no text on one side (`../imtypeset/docs/divergences.md`).
- *No table is split*: the old view cut a long table into pieces of rows
  with the header repeated (`advtext.ui.units`); here it is one block, laid
  out whole the first time any of it is looked at.
- *Defects the other team listed at `be40444`* and that showed here: a caret
  rectangle in a wrapped row is the row's height; a table held (a stream's)
  keeps its old widths after a change of font size. (A third is gone at the
  library pinned now, `7a7bc36`: a point on a cell's blank part answered the
  NEXT cell. `tests/test_typeset_view.py` holds that it answers its own. The
  other team says the caret is fixed in the same commit; that has not been
  measured here.)

## Columns

    view.set_columns(3, height=500.0)       # filled in order, 500 px tall
    view.set_columns(3, balance=True)       # three of one height
    view.set_columns(None)                  # uncut again

The library shows ONE document in columns (imtypeset commit `0b21807`;
"Columns" in its `imtypeset.h` is the specification): the column it is laid
out in is cut, as TeX's `\vsplit` cuts, between two lines, between two rows
of a table and between two blocks, not after a heading, and the pieces
stand side by side. Nothing of the description changes and every position,
range and mark means what it meant, so the selection, the marks, the inks,
the find index and `texts` are untouched by `set_columns`, and
`selected_text` is the uncut document's to the character.

- **The width `draw` is given is what `count` columns stand across**, so
  the document is laid out `(width - gutter * (count - 1)) / count` wide
  (`column_width`). The gutter is one line of the theme's paragraph style
  unless stated.
- **Filled in order** (`height=`): as many columns as the document needs,
  each that tall; those past `count` stand further right, and
  `column(count).exists` is the old `split_into_columns`' "overflow". The
  view claims the whole PAGE (`width`, `height`): in a child window with a
  horizontal scrollbar the columns past the pane are scrolled to, and a
  host that wants pages of `count` columns shows page `p` by scrolling to
  `p * count * (column_width + gutter)`. Lazy: a column is cut, and its
  blocks laid out, when a draw, a hit test or a question first reaches it;
  column `k` costs every column before it, once.
- **Balanced** (`balance=True`, two or more): exactly `count` columns of
  the least height that holds the document. **New, and not the old core's**
  (`advtext.columns` never balanced). Every block is laid out to find the
  height, and it is searched for again after any edit: `TypesetStreamView`
  refuses it.
- **On the page**: the mouse, the selection, `span_rects`, `under_mouse`,
  `width` and `height` speak of the page; a drag from one column into a
  later one selects in reading order, a point in a gutter is the column's
  on its left, a point below a column's last line is that line.
- **Of the uncut column**: `block_rect`, `set_lines`, `table_geometry`,
  `table_column`, `table_row`. `column_pos` takes a corner of theirs to the
  page; a rectangle of theirs may be cut in two. The view does that itself
  for the two things it places: a hosted widget (never cut; handed a
  rectangle one column wide) and `scroll_to`, which in columns also scrolls
  SIDEWAYS, to the left edge of the column holding the block or the caret.
- **Arguments are checked at the call** (`set_columns`, `column`,
  `column_pos`): a malformed one is a `TypeError` or `ValueError` there and
  never the library's refusal inside `draw`, which would switch it off.

**Defects the other team lists at `0b21807`** (`advtext-swap-status.md`,
"Known defects in columns") that reach a host of this view:

- *A caret or range rectangle asked for before the columns are cut that
  far can name the wrong column.* Reproduced at `0b21807` (2026-10-11,
  `demo/columns.md`, a caret in block 20 of a document nothing had drawn:
  420 px too far right and 160 px too high). **Fixed in `7a7bc36`**, the
  library pinned now: measured the same day, the caret is the same with and
  without `column_count` asked first, and `scroll_to` no longer asks it
  (`tests/test_typeset_view.py` holds the calls of that frame). The rest of
  this list is as it was read at `0b21807` and has not been measured again.
- *`column_pos` of an uncut point whose block has not been laid out* is
  the place of an ESTIMATE (reproduced, same document: one column too far
  right). After the call the blocks before it are laid out and the next
  answer is right, which is why `scroll_to` a block settles on its second
  look.
- *Filled in order, an overfull column* (something taller than a column
  that cannot be cut: a hosted block, a quote, a wrapped table row) reaches
  past the column's foot; the view claims the page's height and does not
  clip, so it is drawn over whatever the host puts below. `column(k).overfull`
  says so.
- *A table can be cut between its header row and the rule under it*; *an
  empty block between a heading and its text lets a column end after the
  heading*; *columns do not share a first baseline*, and a cut can leave one
  line of a paragraph at the head or foot of a column. None is hidden here.
- *Under balance `overfull` can be true for columns that fit.*

## A block the host draws: `host_for`

`host_for` is a callable, `(view, number, block) -> Hosted | None`
(`HostFor`, `Hosted`). It is asked about each block once per block object,
when the block is described; a block it answers for is given to the library
as a Host block holding the widget's `text`, and the view hands the widget
its rectangle at each draw. **A block it answered for is asked about again
when where that block came from changed and the block did not**: its span of
the source (`source_of`) or, in a stream view, its having committed. The last
line of a fence can arrive that way (its newline together with the closing
fence), and a widget that reads the source would otherwise never be shown
it. The block and everything after it are then described again, as for any
edit there. `advtext.ui.typeset_hosts` has the contract in
full and `TypesetDiffFences`, which draws a fenced `diff` with a
`TypesetDiffView`. What the host's code raises (`host_for`, a widget's
`height_for` or `draw`) leaves the view as itself and never switches the
library off.

## Edits

`set_document` takes a markdown string or blocks ("What goes in"). It does not
raise for a library that has been switched off since the view drew
(`typesetter.disable`, by this view or another): the blocks are described and
kept, nothing is edited, and the next `draw` raises `TypesetUnavailable`.
Blocks are compared from the front, **by identity and then by value** (they
are frozen values, and a string is parsed into new ones every time): the
blocks before the first one that differs are kept
as they are in the library, and the rest are described again and handed over
in ONE `replace_blocks`. So a string that changed at its end is an edit of its
last blocks. Giving the same string, or the same blocks, again does nothing. `revision`
counts the edits; `edits` counts them by kind. `_edit` is the one place an edit
reaches the library, for a subclass that can do better for a tail that only
grew (`append_text`).

An edit drops marks that were handed over already packed (they hold byte
offsets into the texts as they were), repacks marks handed over as plain
`imtypeset.Mark`s, drops the inks (`set_colours`) of the blocks it replaced,
and drops a selection that reaches a replaced block.

## What has and has not been run

`tests/test_typeset_view.py` drives this in a real window (the `window`
fixture: this machine's display, or Xvfb with software GL) through
`hello_imgui`, with mouse and key events queued through `io.add_*_event`;
the members of tranche 3 and the host protocol are driven through real ImGui
frames with no window (`tests/test_typeset_hosts.py` too).
**Not run anywhere**: a real pointer, a window manager, a host with several
panes, an ImGui context destroyed without `typesetter.unload()` first. Nobody
has looked at what it draws; the tests say that vertices reach the draw list.
"""

from __future__ import annotations

import ctypes
import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, NamedTuple, NoReturn, Protocol

from advtext import typesetter
from advtext.description import (
    KIND_HOST,
    BlockDescription,
    ColumnDescription,
    Description,
    LinkRow,
    StyleDescription,
)
from advtext.markdown_rules import BlockSource
from advtext.typeset_markdown import (
    MarkdownCode,
    MarkdownConverter,
    MarkdownTable,
    MarkdownText,
    parse_markdown,
)
from advtext.ui.ownership import (
    MIN_WIDTH_PX,
    SELECTION_OWNERSHIP,
    clipboard_text,
    scroll_for,
)
from advtext.ui.palette import Palette

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

    from advtext.style import Theme

__all__ = [
    "MAX_COLUMNS",
    "HostFor",
    "Hosted",
    "Position",
    "Range",
    "SetLine",
    "TypesetUnavailable",
    "TypesetView",
    "ViewColumns",
    "ViewStats",
    "library_failed",
    "raise_failed",
]

Position = tuple[int, int]
"""A place in the document: a block's number and an index into that block's `str`."""

Range = tuple[Position, Position]
"""Two positions, the earlier first."""

# What a block the host draws is given before its widget has been asked how
# tall it is, which is at a draw: a widget may need the fonts to answer.
_HOST_GUESS_PX = 16.0


class Hosted(Protocol):
    """
    Something a host draws in a block's place: a height, a `draw`, and the text a copy gives.

    What `HostFor` answers with. `height_for(width_px)` is asked at every
    draw, with the width of the rectangle the block has; `draw` is called with
    ImGui's cursor at that rectangle's top-left corner, only while the
    rectangle meets the window, and may submit items of its own. `text` is
    what a selection that takes the block copies for it (its last newline is
    left off) and what `TypesetView.block_text` answers. A widget that has a
    `handle_keys()` is called through it on a frame it is NOT drawn, so that
    one that owns the selection still answers Ctrl+C.
    """

    @property
    def text(self) -> str: ...

    def height_for(self, width_px: float) -> float: ...

    def draw(self, *, palette: Palette | None = None, width_px: float | None = None) -> object: ...


HostFor = Callable[["TypesetView", int, object], "Hosted | None"]
"""
`(view, number, block) -> Hosted | None`: asked about a block, what draws it, or `None`.

Asked once per block *object* (a block that is kept is not asked about again,
unless it is hosted and its place in the source changed: the module
docstring), after the block has been described: `view.texts[number]`, `view.source_of(number)`
and `view.hosted(number)` (the widget that stood there before, if any) answer
for it during the call. `advtext.ui.typeset_hosts.TypesetDiffFences` is one.
"""


class SetLine(NamedTuple):
    """
    One line of a block as the library set it: `TypesetView.set_lines`.

    `start` and `end` index the block's text (`texts[block]`). The rectangle
    and the baseline are pixels from the document's top-left corner (`origin`
    on screen). Hashable: two layouts' lines can be compared as sets, and a
    line that kept its characters and moved is another line.
    """

    block: int
    line: int
    start: int
    end: int
    left: float
    top: float
    right: float
    bottom: float
    baseline: float


class ViewStats(NamedTuple):
    """
    What the last `draw` did, and the library's own counters: `TypesetView.stats`.

    `whole` is what `draw` returned. `vertices` is how many vertices the
    frame added to the window's draw list between the start of the view's
    `draw` and its end, a hosted widget's own child windows not. `hosts` is
    how many hosted blocks were in view. **`tables` and `cells` are always
    0**: they counted what the table stopgap drew, the library draws tables
    inside its one draw call and reports no count, and the fields stay only
    so that the tuple's shape did not move in the tranche that removed the
    stopgap. The rest is `imtypeset.Document.stats()`: `blocks` in the document,
    `blocks_deferred` not yet laid out (their height is an estimate),
    and two counters that only go up, `blocks_laid_out` and `blocks_drawn`.
    There is no count of glyphs and none of glyphs missing: the library
    reports neither, and `whole` is false when something in view was not set
    as asked.
    """

    whole: bool = True
    vertices: int = 0
    tables: int = 0
    cells: int = 0
    hosts: int = 0
    blocks: int = 0
    blocks_deferred: int = 0
    blocks_laid_out: int = 0
    blocks_drawn: int = 0


class ViewColumns(NamedTuple):
    """
    How a view shows its document in columns: `TypesetView.columns`.

    `count` columns stand across the width a `draw` is given, `gutter`
    pixels apart (already resolved: never `None`). `height` above zero fills
    them in order, each that tall, as many as the document needs; `balance`
    makes `count` columns of one height, the least that holds the document.
    """

    count: int  # type: ignore[assignment]  # the field, not `tuple.count`
    height: float
    gutter: float
    balance: bool


MAX_COLUMNS = 4096
"""The most columns `set_columns` takes: the library's own limit on `Columns.count`."""


class _Host(NamedTuple):
    block: object
    hosted: Hosted


class _Inks(NamedTuple):
    """One block's inks as the library takes them, sorted by where each starts."""

    starts: list[int]
    longest: int
    packed: Any


# How far outside the clip rectangle the inks handed to a draw reach.
_INK_SLACK_PX = 32.0


# How many draws a `scroll_to` is looked at again. A block's place is an
# estimate until the blocks above it in the window have been laid out, which
# the draw after the scroll does; the request is dropped as soon as a draw
# finds nothing left to move.
_SCROLL_FRAMES = 4


class TypesetUnavailable(RuntimeError):
    """
    imtypeset cannot draw this, now or any more, and there is nothing else to draw it with.

    The message is `advtext.typesetter.reason()`, or says that the fonts were
    never loaded.
    """


def library_failed(exc: BaseException) -> bool:
    """
    Whether `exc` is the library's own failure and not an error of this side's Python.

    The library's own: an `imtypeset.Error`, or anything else the package
    defines, or a subclass of one. Not the library's: an error of a view's
    own code, of the model or of a host's callback, and the built-in
    `TypeError` / `ValueError` the package raises for an argument it refuses
    (a closed document, a malformed block): each of those is a mistake on
    this side of the call and is raised as it is.
    """
    return any(
        kind.__module__ == "imtypeset" or kind.__module__.startswith("imtypeset.")
        for kind in type(exc).__mro__
    )


def raise_failed(exc: Exception) -> NoReturn:
    """
    Raise what a call into the library raised, as what a host should see of it.

    The ONE rule of `TypesetView`, `TypesetStreamView` and `TypesetDiffView`
    (each `_failed` is this): a `TypesetUnavailable` is passed on; the
    library's own failure (`library_failed`) switches the library off for the
    run (`typesetter.disable`) and becomes `TypesetUnavailable`; anything else
    is raised as itself and switches nothing off.
    """
    if isinstance(exc, TypesetUnavailable) or not library_failed(exc):
        raise exc
    why = f"{type(exc).__name__}: {exc}"
    typesetter.disable(why)
    raise TypesetUnavailable(f"imtypeset failed and is switched off: {why}") from exc


class TypesetView:
    """
    A selectable view of one document, set and drawn by imtypeset.

    The module docstring has the contract. Mutable, as `BareView` is: it holds
    the library's `Document`, the description it was made from, and a few
    pieces of interaction state.
    """

    def __init__(
        self,
        document: object = None,
        *,
        theme: Theme | None = None,
        palette: Palette | None = None,
        on_link: Callable[[str], None] | None = None,
        hand_cursor: bool = True,
        copy_as: Callable[[TypesetView], str] | None = None,
        style_links: bool | None = None,
        separator: str = "\n\n",
        math: object = None,
        references: bool = True,
        host_for: HostFor | None = None,
    ) -> None:
        """
        `document` is what `set_document` takes; `None` is an empty view.

        `theme` is the one a markdown string is read with, and the one blocks
        given ready-made were built with (it is what their sizes are read
        against). `math` and `references` are used only to read a markdown
        string: anything true for `math` turns `$...$` and `$$` on (a
        `MathBuilder` is accepted for that and is not called), and
        `references` is `parse_markdown`'s. `palette` may also be given to
        each `draw`, as `BareView` takes it. `host_for` is asked which blocks
        a widget of the host's draws ("A block the host draws" in the module
        docstring). Raises `TypesetUnavailable` when the library is not in use.
        """
        if typesetter.module() is None:
            raise TypesetUnavailable(f"imtypeset is not in use: {typesetter.reason()}")
        if theme is None:
            from advtext.theme import Theme as _Theme

            theme = _Theme.build()
        self.theme = theme
        self.on_link = on_link
        self.hand_cursor = hand_cursor
        self.copy_as = copy_as
        self.style_links = style_links
        self.separator = separator
        self.math = math
        self.references = references
        self.host_for = host_for
        self.debug = False
        """Whether the library draws its own overlay (line boxes) with the text."""
        self.revision = 0
        """How many times the described document has changed."""
        self.edits: dict[str, int] = {"set": 0, "replace": 0, "append": 0}
        """Edits made in the library, by the call that made them."""

        self._palette = palette if palette is not None else Palette()
        self._source: str | None = None
        self._sources: tuple[BlockSource, ...] = ()
        self._given: Any = None  # a document handed over that answers `source_of`
        self._blocks: tuple[object, ...] = ()
        self._converter: MarkdownConverter = self._new_converter()
        self._described: list[BlockDescription] = []
        self._texts: list[str] = []
        self._links: list[LinkRow] = []
        self._tables: list[int] = []
        # The style table the LIBRARY has is the view's, not the converter's:
        # a converter's style with a role's ink laid over it (`Palette.roles`).
        # `_converted[n]` is block n's index in the converter's table, which
        # is what a change of the roles is worked out from again.
        self._converted: list[int] = []
        self._styles: list[StyleDescription] = []
        self._style_index: dict[tuple[int, int], int] = {}
        # Columns a host stated (`set_table_columns`): each such table's
        # columns as the converter described them, to go back to.
        self._described_columns: dict[int, tuple[ColumnDescription, ...]] = {}
        # Where each hosted block was (left, top, bottom from the document's
        # corner) when `_rects_key` was what it is.
        self._rects: dict[int, tuple[float, float, float]] = {}
        self._rects_key: tuple[float, float, int] | None = None
        self._host_epoch = 0
        # The blocks a widget of the host's draws, the height each has given
        # the library, and where the ones the last draw showed were.
        self._hosts: dict[int, _Host] = {}
        # Where each hosted block came from when `host_for` answered for it
        # (`_asked_as`): a kept block is asked about again when this moved.
        self._host_asked: dict[int, object] = {}
        self._host_heights: dict[int, float] = {}
        self._hosts_shown: dict[int, tuple[float, float, float, float]] = {}
        self._doc: Any = None
        self._style: Any = None
        self._rule: int | None = None  # the rule ink the document's options hold
        # How the document is shown in columns (`set_columns`), what of that
        # the library's document has been told, and what the last layout made
        # of it: one column's width, and the page's.
        self._columns: ViewColumns | None = None
        self._columns_told: ViewColumns | None = None
        self._column_width = 0.0
        self._width = 0.0

        self._selection: Range | None = None
        self._all_selected = False
        self._anchor: Range = ((0, 0), (0, 0))
        self._granularity = 0
        self._dragging = False
        self._drawn_frame = -(2**31)
        self._owned = 0
        self._origin: tuple[float, float] | None = None
        self._height = 0.0
        self._whole = True
        self._vertices = 0
        self._hit: Any = None
        self._hot: tuple[int, int] | None = None  # (block, tag) of the link under the mouse
        self._link_down: tuple[int, int] | None = None
        self._scroll: tuple[int, int | None, float, float | None, bool, int] | None = None
        self._scrolled = False
        self._marks: Any = None
        self._packed: Any = None
        # Inks a host laid over ranges of blocks (`set_colours`), and what is
        # handed to the library's draw: those and the marks, packed together.
        self._colours: dict[int, tuple[tuple[int, int, int], ...]] = {}
        self._inked: dict[int, _Inks] = {}  # each block's inks, packed, made at a draw
        self._drawn_marks: Any = None
        self._drawn_for: tuple[int, int, int, int] | None = None
        if document is not None:
            self.set_document(document)

    # ------------------------------------------------------------------
    # The document
    # ------------------------------------------------------------------

    def set_document(self, document: object) -> bool:
        """
        Show `document`: markdown source, or blocks already made.

        **A string is read by `advtext.typeset_markdown.parse_markdown`** with
        the view's `theme`, `math` and `references`: text and runs, no node
        material and no font asked anything. The view keeps the string and
        where each block came from in it (`source`, `source_of`).

        Anything else is its `blocks` if it has that attribute, or a sequence
        of blocks: what `parse_markdown` or an
        `advtext.typeset_markdown.MarkdownStream` made. A `sources`
        attribute as long as the blocks, or a `source_of`, is kept for the
        source map.

        Describes again only what changed, and returns whether anything did.
        A string equal to the last one given is nothing. Blocks are compared
        from the front, by identity and then by value (they are frozen
        values, so an edit to the end of a long source re-describes its last
        blocks and not the document); those after the first different one
        are described and replaced in one edit.
        """
        if isinstance(document, str):
            if document == self._source:
                return False
            parsed = parse_markdown(
                document, self.theme, references=self.references, math=bool(self.math)
            )
            # Before the blocks: a `host_for` asked about them reads `source`.
            self._source = document
            self._given = None
            return self._set_blocks(parsed.blocks, parsed.sources)
        blocks = getattr(document, "blocks", document)
        if not isinstance(blocks, Sequence):
            raise TypeError(
                "set_document takes a markdown str, a Document, or a sequence of blocks"
            )
        sources = getattr(document, "sources", ())
        if not isinstance(sources, Sequence) or len(sources) != len(blocks):
            sources = ()
        held = (self._source, self._given, self._sources)
        self._source = None
        self._given = document if callable(getattr(document, "source_of", None)) else None
        changed = self._set_blocks(blocks, sources)
        if not changed:
            # The same blocks again: what is known about their source stands.
            self._source, self._given, self._sources = held
        return changed

    def _new_converter(self) -> MarkdownConverter:
        return MarkdownConverter(self.theme, link_color=self._link_color())

    def _forget(self) -> None:
        """
        Nothing is described any more: a new converter, and the library's document closed.

        The hosted widgets are kept, so that a `host_for` asked again about
        the same blocks finds the widget it made (`hosted`).
        """
        self._converter = self._new_converter()
        self._blocks = ()
        self._described, self._texts, self._links, self._tables = [], [], [], []
        self._converted, self._styles, self._style_index = [], [], {}
        self._described_columns = {}
        # A new converter numbers styles from zero, so the library's document
        # is made again and not edited.
        self.close()

    def _kept(self, blocks: Sequence[object]) -> int:
        """
        How many leading blocks of `blocks` are the ones on show: the first that changed.

        By identity, and by value too: `parse_markdown`'s blocks are frozen
        values, and a string read again makes new ones that are equal.
        """
        old = self._blocks
        first = 0
        limit = min(len(old), len(blocks))
        while first < limit and (old[first] is blocks[first] or old[first] == blocks[first]):
            first += 1
        # A hosted block that is what it was, from somewhere else in the
        # source: its widget is shown what arrived ("A block the host draws").
        for at in self._hosts:
            if at >= first:
                break
            if self._asked_as(at) != self._host_asked.get(at):
                return at
        return first

    def _asked_as(self, block: int) -> object:
        """
        What a hosted block's widget may have read beside the block: its span of the source.

        Compared with what it was when `host_for` last answered for the
        block. `None` with no source map, which never differs.
        """
        where = self.source_of(block)
        return None if where is None else (where.span.start, where.span.end)

    def _set_blocks(self, given: Sequence[object], sources: Sequence[BlockSource] = ()) -> bool:
        blocks = tuple(given)
        # Before `_kept`, which asks where the hosted blocks come from now.
        self._sources = tuple(sources)
        first = self._kept(blocks)
        old = self._blocks
        if first == len(old) == len(blocks):
            return False
        # A block that is what it was is the object it was: `host_for` is
        # asked once per object, and a stream's selection rule reads identity.
        blocks = old[:first] + blocks[first:]
        known = len(self._styles)
        described = self._converter.describe(blocks[first:], base=first)
        removed = len(old) - first
        self._blocks = blocks
        self._described[first:] = described.blocks
        self._texts[first:] = described.texts
        self._converted[first:] = [block.style for block in described.blocks]
        self._links = [row for row in self._links if row.block < first] + described.links
        self._tables = [at for at in self._tables if at < first] + described.tables
        self._described_columns = {
            at: columns for at, columns in self._described_columns.items() if at < first
        }
        self._ask_hosts(first)
        self._describe_more(first)
        self._ink_blocks(first)
        self.revision += 1
        if self._all_selected:
            self._selection = self._everything()
        elif self._selection is not None and self._selection[1][0] >= first:
            self._selection = None
            self._dragging = False
        if self._dragging and self._anchor[1][0] >= first:
            self._dragging = False
        if self._link_down is not None and self._link_down[0] >= first:
            self._link_down = None
        self._hit = None
        self._hot = None
        self._colours = {at: spans for at, spans in self._colours.items() if at < first}
        self._inked = {at: inks for at, inks in self._inked.items() if at < first}
        self._drawn_marks = None
        # Packed marks hold byte offsets into the texts as they were.
        if self._packed is not None and self._packed is self._marks:
            self._marks = None
        self._packed = None
        if self._doc is not None and not self._doc.closed:
            if typesetter.module() is None:
                # Switched off since this view drew (`typesetter.disable`, by
                # any view): there is nothing to edit with, and that is the
                # next `draw`'s to say. The library's document is behind the
                # description from here on, so it is not kept.
                self._doc = None
                return True
            try:
                self._edit(
                    first,
                    removed,
                    described._replace(
                        blocks=self._described[first:],
                        styles=list(self._styles),
                        texts=self._texts[first:],
                    ),
                    self._styles[known:],
                )
            except Exception as exc:  # noqa: BLE001 -- see `_failed`
                self._failed(exc)
        return True

    def _ask_hosts(self, first: int) -> None:
        """
        Ask `host_for` about each block from `first` on, and describe the ones it takes as Host.

        While it is asked, `hosted(n)` still answers the widget that stood
        at `n` before this edit, and `texts[n]` is the block's own text. What
        `host_for` raises is the host's and leaves here as itself; the
        library's document is then closed, since it no longer matches what
        is described, and the next draw makes it again.
        """
        hosts = {at: host for at, host in self._hosts.items() if at < first}
        asked = {at: was for at, was in self._host_asked.items() if at < first}
        self._host_heights = {at: h for at, h in self._host_heights.items() if at < first}
        if self.host_for is None:
            self._hosts, self._host_asked = hosts, asked
            return
        try:
            for at in range(first, len(self._blocks)):
                block = self._blocks[at]
                hosted = self.host_for(self, at, block)
                if hosted is None:
                    continue
                hosts[at] = _Host(block, hosted)
                asked[at] = self._asked_as(at)
                was = self._described[at]
                text = str(hosted.text).removesuffix("\n")
                self._described[at] = BlockDescription(
                    kind=KIND_HOST,
                    text=text,
                    style=was.style,
                    left_indent=was.left_indent,
                    extent=_HOST_GUESS_PX,
                )
                self._texts[at] = text
        except BaseException:
            self.close()
            raise
        finally:
            self._hosts, self._host_asked = hosts, asked
            taken = {at for at in hosts if at >= first}
            if taken:
                self._links = [row for row in self._links if row.block not in taken]
                self._tables = [at for at in self._tables if at not in taken]

    def _ink_blocks(self, first: int) -> None:
        """
        Give each block from `first` on its style in the view's table: the converter's, in its ink.

        The ink is its role's in `Palette.roles`, or 0 (the document's) when
        the palette names none for it.
        """
        roles = {kind.name: int(colour) for kind, colour in self._palette.roles}
        for at in range(first, len(self._described)):
            ink = roles.get(_role_of(self._blocks[at]), 0) if roles else 0
            key = (self._converted[at], ink)
            found = self._style_index.get(key)
            if found is None:
                found = self._style_index[key] = len(self._styles)
                self._styles.append(self._converter.styles[key[0]]._replace(Color=ink))
            if self._described[at].style != found:
                self._described[at] = self._described[at]._replace(style=found)

    def _describe_more(self, first: int) -> None:
        """
        A subclass's say in the descriptions of the blocks from `first` on, before they are inked.

        Nothing here. `TypesetStreamView` flags the tables it holds.
        """

    def _drop_heights(self) -> None:
        """Every hosted block gives the library its height again at the next draw."""
        self._host_heights = {}
        self._host_epoch += 1

    def _edit(
        self,
        first: int,
        removed: int,
        described: Description,
        fresh: Sequence[StyleDescription],
    ) -> None:
        """
        Make one edit in the library: blocks `[first, first + removed)` become `described.blocks`.

        `fresh` are the styles this describe added, which is what
        `replace_blocks` wants (it appends them to the document's). Called
        only while the library's document exists; the view's own record
        (`texts`, `links`) is already what it will be. A subclass that sees a
        tail that only grew makes `append_text` of it here and counts it in
        `edits["append"]`.
        """
        whole = self._doc.replace_blocks(
            first, removed, described.blocks, typesetter.block_styles(fresh)
        )
        self.edits["replace"] += 1
        self._cut(whole)

    def _cut(self, whole: bool) -> None:
        """
        Say so when an edit was applied in part: the library cut what was wrong in it.
        """
        if whole is not True:
            typesetter.note(f"an edit was cut: {self._doc.edit_error.message}")

    def _document(self) -> Any:
        """
        The library's document, made from the description if there is none.

        There is none before the first draw, after `close`, and after
        `typesetter.unload()` closed it.
        """
        if not typesetter.ready():
            why = typesetter.reason() or "typesetter.load_fonts() has not succeeded"
            raise TypesetUnavailable(f"imtypeset cannot draw: {why}")
        if self._doc is None or self._doc.closed:
            ts = typesetter.module()
            # A new document has the guessed heights.
            self._drop_heights()
            try:
                self._doc = ts.Document()
                whole = self._doc.set_blocks(self._described, typesetter.block_styles(self._styles))
                self.edits["set"] += 1
                self._cut(whole)
            except Exception as exc:  # noqa: BLE001 -- see `_failed`
                self._failed(exc)
            self._rule = None
            self._columns_told = None  # a new document is shown uncut
        return self._doc

    def _failed(self, exc: Exception) -> NoReturn:
        """
        What was raised while the library was in use, sorted by whose it is (`raise_failed`).

        The library's own failure switches it off for the run and the caller
        is told it cannot be drawn; anything else -- a slip in this module --
        is raised as it is, and the library stays in use.
        """
        raise_failed(exc)

    def close(self) -> None:
        """
        Release the library's document. The view can still be drawn: it is made again.
        """
        if self._doc is not None:
            self._doc.close()
        self._doc = None
        self._drop_heights()

    @property
    def blocks(self) -> tuple[object, ...]:
        """The advtext blocks on show."""
        return self._blocks

    @property
    def texts(self) -> Sequence[str]:
        """
        Each block's text as the library holds it; `""` for a rule.

        A table's is its cells' texts, a tab between the cells of a row and
        a newline between rows: what a copy of all of it gives. What
        positions index, in a table as anywhere, and what a find searches
        (`advtext.typeset_find`, cell by cell). Not a copy: do not change it.
        """
        return self._texts

    @property
    def links(self) -> Sequence[LinkRow]:
        """
        Every link: its block, its range in that block's text, its tag and its target.

        A link in a table cell too, as a range of the table's text.
        """
        return self._links

    @property
    def tables(self) -> Sequence[int]:
        """The numbers of the blocks that are tables (`KIND_TABLE`), ascending."""
        return self._tables

    def table_geometry(self, block: int) -> Any:
        """
        A table as the library last laid it out: `imtypeset.TableGeometry`, or `None`.

        `row_count`, `column_count`, `cell_count`, and `min` / `max` in
        pixels from the document's corner (`origin` on screen): from the
        table's left edge to the right edge of its last column, first row's
        top to last row's bottom. `stated` says the columns are stated or
        held and not fitted to the width. One call, which lays the table out
        at the width of the last layout. `None` for a block that is no
        table, and before the first `draw` or `layout_for`.
        """
        return self._of_table(block, lambda doc: doc.table_geometry(block))

    def table_column(self, block: int, column: int) -> Any:
        """
        One column of a table: `imtypeset.TableColumnGeometry`, or `None` as `table_geometry`.

        `min` and `max` are its edges, x from the document's left edge, the
        padding inside them. `natural` and `floor` are what its cells want
        whatever the width: the widest of them on one line, and the widest
        piece of any that cannot be broken, each with the padding: what a
        drag handle is held between. All zero for a column that is not there.
        """
        return self._of_table(block, lambda doc: doc.table_column(block, column))

    def table_row(self, block: int, row: int) -> Any:
        """
        One row of a table: `imtypeset.TableRowGeometry`, or `None` as `table_geometry`.

        `min` and `max` are its top and bottom, y from the document's top
        (the rule under a header lies between two rows); `wrapped` says a
        cell of it was broken into lines.
        """
        return self._of_table(block, lambda doc: doc.table_row(block, row))

    def _of_table(self, block: int, ask: Callable[[Any], Any]) -> Any:
        doc = self.native_document
        if doc is None or typesetter.module() is None or block not in self._tables:
            return None
        try:
            return ask(doc)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def set_table_columns(self, block: int, columns: Sequence[object] | None) -> bool:
        """
        State a table's columns: what a drag of a column's edge does each frame.

        `columns` are `advtext.description.ColumnDescription`s, or tuples in
        its order `(align, width, share)`: `width` in pixels with the cell
        padding in it, read when EVERY column states one above zero (the
        table is then exactly those widths, whatever the pane's), else
        `share` when every column states one, else the library fits the
        table. They replace the table's columns, alignments included. **A
        bare number is a width for a column that keeps the alignment it was
        described with** (left, for a column the table did not describe):
        `set_table_columns(block, [120.0, 80.0])` is a drag.
        `None` puts back the columns the table was described with.

        Kept in the description, so they survive the document being handed
        to the library again (a palette's roles, a closed document), and
        **dropped when an edit replaces the block**. One call into the
        library when its document exists: rows are set again only if a
        width or an alignment changed, and no cell is measured again. True
        when the columns are other than they were. Raises `ValueError` for a
        block that is no table.

        Raises `TypeError`, and leaves the table as it was, for a column
        that is none of those: `(1, "wide")`, say. It is refused here, as
        `set_marks` refuses a mark, because the library's own refusal of it
        could only be taken for a failure of the library and switch the
        library off.
        """
        if block not in self._tables:
            raise ValueError(f"block {block} is not a table")
        was = self._described[block]
        if columns is None:
            stated = self._described_columns.pop(block, was.columns)
        else:
            described = self._described_columns.get(block, was.columns)
            made: list[ColumnDescription] = []
            for at, one in enumerate(columns):
                column: Any = None
                if isinstance(one, ColumnDescription):
                    column = one
                elif isinstance(one, (int, float)):
                    align = (
                        described[at].align if at < len(described) else ColumnDescription().align
                    )
                    column = ColumnDescription(align, width=float(one))
                else:
                    try:
                        column = ColumnDescription(*one)  # type: ignore[misc]
                    except TypeError:
                        column = None
                if not _is_column(column):
                    raise TypeError(
                        f"set_table_columns: column {at} is {one!r}; a column is a width in "
                        "pixels, or (align, width, share) with an integer and two numbers, "
                        "which is an advtext.description.ColumnDescription"
                    )
                made.append(column)
            stated = tuple(made)
            self._described_columns.setdefault(block, was.columns)
        if stated == was.columns:
            return False
        self._described[block] = was._replace(columns=stated)
        doc = self.native_document
        if doc is not None and typesetter.module() is not None:
            try:
                doc.set_table_columns(block, stated)
            except Exception as exc:  # noqa: BLE001 -- see `_failed`
                self._failed(exc)
        return True

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def set_columns(
        self,
        count: int | None = None,
        *,
        height: float = 0.0,
        gutter: float | None = None,
        balance: bool = False,
    ) -> bool:
        """
        Show the document in columns from the next `draw` on; `set_columns(None)` shows it uncut.

        `count` columns stand across the width `draw` is given, so one
        column is `(width - gutter * (count - 1)) / count` wide, and that is
        the width the document is laid out at. Then ONE of two fills
        ("Columns" in the module docstring):

        - `height` (pixels, above zero): **in order**. Every column is that
          tall and takes what fits; there are as many as the document needs,
          and those past `count` stand further right (`column(count).exists`
          says there are any). Lazy: a column is cut when something reaches it.
        - `balance=True`, with a `count` of two or more: `count` columns of
          one height, the least that holds the document. Everything is laid
          out to find it, and again after any edit.

        `gutter` is the space between two columns in pixels; `None` is one
        line of the theme's paragraph style and 0 is none.

        Nothing is asked of the library here: the next `draw` (or
        `layout_for`) tells it, in one call, and only when what is said
        changed. Nothing is described or laid out again for it, and the
        selection, the marks and the inks stand: positions mean what they
        meant. True when the columns are other than they were.

        Raises `TypeError` or `ValueError` here, and changes nothing, for
        an argument the library could not be handed: a `count` that is not
        an integer from 1 to `MAX_COLUMNS`, a `height` or `gutter` that is
        not a finite number of zero or more (finite as the C `float` the
        library takes, and not one that becomes zero there), neither a
        `height` nor `balance`, both of them, `balance` with fewer than two
        columns, or any of `height`, `gutter` and `balance` with no `count`
        (until tranche 5 that was taken, and showed the document uncut).
        """
        wanted: ViewColumns | None = None
        if count is None:
            given = [
                name
                for name, stated in (
                    ("height", not _is_default(height, 0.0)),
                    ("gutter", gutter is not None),
                    ("balance", not _is_default(balance, False)),
                )
                if stated
            ]
            if given:
                raise ValueError(
                    f"set_columns: {' and '.join(given)} given with no count; say how many "
                    "columns, or set_columns(None) alone to show the document uncut"
                )
        else:
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError(f"set_columns: count is {count!r}; it is an integer, or None")
            if not 1 <= count <= MAX_COLUMNS:
                raise ValueError(f"set_columns: count is {count}; it is from 1 to {MAX_COLUMNS}")
            if not isinstance(balance, bool):
                raise TypeError(f"set_columns: balance is {balance!r}; it is True or False")
            height = _length(height, "height")
            if gutter is None:
                gutter = self.default_gutter()
            else:
                gutter = _length(gutter, "gutter")
            if balance and height > 0.0:
                raise ValueError(
                    "set_columns: a height fills the columns in order and balance finds "
                    "their height itself; give one of the two"
                )
            if balance and count < 2:
                raise ValueError("set_columns: balance wants a count of two or more")
            if not balance and height <= 0.0:
                raise ValueError(
                    "set_columns: give a height above zero (columns filled in order) or "
                    "balance=True; set_columns(None) shows the document uncut"
                )
            self._refuse_columns(count, height, gutter, balance)
            wanted = ViewColumns(count, height, gutter, balance)
        if wanted == self._columns:
            return False
        self._columns = wanted
        # Where the hosted blocks are is another question now.
        self._rects_key = None
        self._drawn_marks = None
        return True

    def _refuse_columns(self, count: int, height: float, gutter: float, balance: bool) -> None:
        """
        A subclass's say, after the arguments were found well formed: raise to refuse them.

        Nothing here. `TypesetStreamView` refuses `balance`.
        """

    def default_gutter(self) -> float:
        """
        The gutter `set_columns` uses when none is stated, in pixels.

        One line of the theme's paragraph style, which is the library's own
        default (its style's em times its line height). No call.
        """
        from advtext.theme import BlockKind

        line = self.theme.style(BlockKind.PARAGRAPH).leading
        return float(self._converter.px(line))

    @property
    def columns(self) -> ViewColumns | None:
        """How the document is shown in columns (`set_columns`), or `None` when it is uncut."""
        return self._columns

    @property
    def column_width(self) -> float:
        """
        The width the last `draw` or `layout_for` laid the document out at, in pixels.

        One column's, when the document is shown in columns; the pane's
        otherwise. 0 before the first.
        """
        return self._column_width

    @property
    def width(self) -> float:
        """
        How wide the rectangle the last `draw` claimed was, in pixels.

        The width it was given, uncut. In columns the page's: every column
        there is and the gutters between them, which is more than it was
        given when columns filled in order run past `count`, and an
        estimate until the last column has been reached.
        """
        return self._width

    def column_count(self) -> int:
        """
        How many columns there are: 1 for a document shown uncut, and before the first `draw`.

        Balanced, `count`. In order, the columns cut so far and the
        library's estimate of the rest, exact once the last column has been
        reached. One call, which reads what the library's document was last
        told: columns set since the last `draw` are counted after the next.
        """
        doc = self.native_document
        if doc is None or typesetter.module() is None:
            return 1
        try:
            return int(doc.column_count())
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def column(self, index: int) -> Any:
        """
        Column `index` on the page: `imtypeset.ColumnGeometry`, or `None` before the first `draw`.

        `min` and `max` are its rectangle and `content_min` / `content_max`
        what its lines occupy, in pixels from the document's corner (`origin`
        on screen); it holds the positions `[start, end)`; `uncut_top` is
        where its first line is in the uncut column; `overfull` says it
        holds something taller than a column that cannot be cut; `exists`
        is false, and the rest zero, for a column that is not there. A
        document shown uncut has column 0, which is all of it.

        One call, and **it cuts every column up to `index`**, laying out
        what they hold: asking for a late column of a long document costs
        the document. Raises `TypeError` for an `index` that is no integer.
        """
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError(f"column: index is {index!r}; it is an integer")
        doc = self.native_document
        if doc is None or typesetter.module() is None:
            return None
        try:
            return doc.column(index)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def column_pos(self, point: tuple[float, float]) -> tuple[float, float]:
        """
        Where a point of the UNCUT column is on the page, both in pixels from the document's corner.

        `block_rect`, `set_lines`, `table_geometry`, `table_column` and
        `table_row` go on answering for the uncut column in a document shown
        in columns (`block_rect` at `origin`, the rest from the corner); this
        takes a corner of theirs to where it is drawn. A point, not a
        rectangle: a block may be cut, and the foot of a column's last line
        maps to the head of the next column. The same point back for a
        document shown uncut, and before the first `draw`. One call, which
        cuts the columns up to the one that shows the point.

        Raises `TypeError` for anything but two finite numbers.
        """
        try:
            pair: tuple[Any, ...] = tuple(point)
        except TypeError:
            pair = ()
        if len(pair) != 2 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in pair
        ):
            raise TypeError(f"column_pos: the point is {point!r}; it is (x, y), two finite numbers")
        given = (float(pair[0]), float(pair[1]))
        doc = self.native_document
        if doc is None or typesetter.module() is None:
            return given
        try:
            px, py = doc.column_pos(given)
            return (float(px), float(py))
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def _column_px(self, width_px: float) -> float:
        """One column's width when `width_px` is what the columns stand across."""
        columns = self._columns
        if columns is None:
            return width_px
        across = (width_px - columns.gutter * (columns.count - 1)) / columns.count
        return max(across, MIN_WIDTH_PX)

    @property
    def hosts(self) -> Sequence[int]:
        """The numbers of the blocks a widget of the host's draws (`host_for`), ascending."""
        return sorted(self._hosts)

    def hosted(self, block: int) -> Hosted | None:
        """
        The widget standing for block `block`, or `None` if the view sets that block itself.

        For a host that wants to reach it (switch a diff to side by side), and
        for a `host_for` that wants the widget it made last time.
        """
        host = self._hosts.get(block)
        return None if host is None else host.hosted

    @property
    def hosts_drawn(self) -> int:
        """How many hosted widgets the last `draw` drew: the ones whose rectangle met the window."""
        return len(self._hosts_shown)

    @property
    def converter(self) -> Any:
        """
        The converter the description was made with; its `link_target(tag)` reads a hit.

        An `advtext.typeset_markdown.MarkdownConverter`. Its `styles` are
        NOT the library's: the view lays the palette's role inks over them.
        """
        return self._converter

    # ------------------------------------------------------------------
    # The source map
    # ------------------------------------------------------------------

    @property
    def source(self) -> str | None:
        """The markdown the view was given as a string, or `None` when it was given blocks."""
        return self._source

    def source_of(self, block: int) -> BlockSource | None:
        """
        Where block `block` came from in the markdown, or `None` if there is no record.

        A record exists when the view was given a string, or something with
        `sources` (a `MarkdownDocument`) or a `source_of` (an
        `advtext.markdown.Document`). Whole source lines, at two grains
        (`advtext.markdown_rules.BlockSource`).
        """
        if 0 <= block < len(self._sources):
            return self._sources[block]
        if self._given is not None and 0 <= block < len(self._blocks):
            found: BlockSource | None = self._given.source_of(block)
            return found
        return None

    def block_source(
        self, block: int, source: str | None = None, *, top: bool = False
    ) -> str | None:
        """
        One block's markdown, cut verbatim from the source, or `None` if it has no record.

        `source` is the string the blocks were read from; left out, it is the
        one the view holds (`source`), and the answer is `None` when it holds
        none. `top=True` gives the whole top-level block the block is part of
        (the whole list for one of its items).
        """
        where = self.source_of(block)
        text = self.source if source is None else source
        if where is None or text is None:
            return None
        return (where.top if top else where.span).of(text)

    def block_text(self, block: int) -> str:
        """
        One block's text as the library holds it (`texts[block]`); `""` for a number out of range.

        A code block's lines newline-joined, a table's cells with tabs and
        newlines between them, a hosted block as its widget's `text`. No
        list marker.
        """
        return self._texts[block] if 0 <= block < len(self._texts) else ""

    def block_role(self, block: int) -> str:
        """
        The name of the `BlockKind` block `block` plays (`"HEADING_2"`, `"CODE"`, `"TABLE"`).

        What `Palette.roles` is keyed by, for a page that says what a block
        is. `""` for a rule and for a number out of range.
        """
        return _role_of(self._blocks[block]) if 0 <= block < len(self._blocks) else ""

    def selected_blocks(self) -> tuple[int, ...]:
        """
        The numbers of the blocks the selection touches, in order; empty with no selection.

        The block the selection starts in, when it takes at least one
        character of it; the one it ends in, likewise; and EVERY block
        between the two, a rule or a hosted block with no text included
        (`BareView.selected_blocks` leaves out a block that holds no
        character).
        """
        if self._selection is None:
            return ()
        (first, start), (last, end) = self._selection
        if first == last:
            return (first,)
        chosen = list(range(first + 1, last))
        if start < len(self._texts[first]) or not self._texts[first]:
            chosen.insert(0, first)
        if end > 0:
            chosen.append(last)
        return tuple(chosen)

    def selected_source(self, source: str | None = None) -> str:
        """
        The verbatim markdown of every block the selection touches: "copy as markdown".

        **Whole blocks, not the selected characters**, as in `BareView`:
        nothing maps a character of the text back to an offset in the
        markdown. Each block's own source lines once, in order; lines next to
        each other in the source stay so, and one blank line stands for a
        gap. `source` as in `block_source`. `""` with no selection, no
        source, or no record.
        """
        text = self.source if source is None else source
        if text is None:
            return ""
        spans = []
        for block in self.selected_blocks():
            where = self.source_of(block)
            if where is not None and where.span not in spans:
                spans.append(where.span)
        spans.sort(key=lambda span: span.line_start)
        pieces: list[str] = []
        previous_end: int | None = None
        for span in spans:
            if previous_end is not None and span.line_start < previous_end:
                continue
            if pieces and previous_end is not None and span.line_start > previous_end:
                if not pieces[-1].endswith("\n"):
                    pieces.append("\n")
                pieces.append("\n")
            pieces.append(span.of(text))
            previous_end = span.line_end
        return "".join(pieces)

    @property
    def native_document(self) -> Any:
        """
        The `imtypeset.Document`, or `None` before the first draw and after `close`.
        """
        return None if self._doc is None or self._doc.closed else self._doc

    # ------------------------------------------------------------------
    # Colour
    # ------------------------------------------------------------------

    @property
    def palette(self) -> Palette:
        """The palette in use: the constructor's, or the last one given to `draw`."""
        return self._palette

    def set_palette(self, palette: Palette) -> None:
        """
        Draw with `palette` from now on. What each part of it costs to change:

        - `ink`, `highlight`, `rule`: nothing is described and nothing edited.
          A different ink or highlight is a new style for the document's
          layout call; an equal palette, another object or the same, does
          nothing at all.
        - `roles` (an ink per block kind): the inks are in the block styles
          the library holds, so the document is **given to the library again**
          (one `set_blocks`: its blocks are laid out again as the window
          reaches them, and every hosted block gives its height again). Nothing is
          parsed and no block is described again; `texts`, `links`,
          `revision`, the selection and the marks are untouched.
        - `link`, when links are styled: it is in the runs, so every block
          is described again (not parsed again) and the library is given a
          new document; what `links` and `texts` hold is replaced by equal
          values. Marks handed over packed go, as at any edit.
        """
        old = self._palette
        old_link = self._link_color()
        self._palette = palette
        if (palette.ink, palette.highlight) != (old.ink, old.highlight):
            self._style = None
        if self._link_color() != old_link:
            self._redescribe()
        elif palette.roles != old.roles:
            self._recolour()

    def set_theme(self, theme: Theme, document: object = None) -> bool:
        """
        Read and set with `theme` from now on, without making another view.

        A view holding markdown source reads it again with the theme (the
        blocks name the theme's styles); one holding blocks is given
        `document`, the same content built with the new theme, or, with none,
        describes the blocks it has against the new theme's sizes. One new
        library document either way. The selection and the inks
        (`set_colours`) are kept when the texts came out the same, which a
        theme alone does not change; marks handed over packed go, as at any
        edit. The faces are
        whatever `typesetter.load_fonts()` registered: a theme that names
        other font FILES is not served here.
        """
        self.theme = theme
        self._style = None
        if document is not None:
            self._forget()
            self._source = None
            self.set_document(document)
            return True
        self._redescribe(read=True)
        return True

    def _target(self, tag: int) -> str | None:
        found: str | None = self._converter.link_target(tag)
        return found

    def _link_color(self) -> int:
        styled = self.style_links if self.style_links is not None else self.on_link is not None
        return int(self._palette.link) if styled else 0

    def _redescribe(self, read: bool = False) -> None:
        """
        Describe everything again with a new converter: the link ink or the theme changed.

        `read` reads the markdown again too, when the view holds it: a block
        names its theme's styles, so another theme is another parse. Another
        link ink is not: the blocks say where the links are, not their colour.
        """
        blocks, sources, source, given = self._blocks, self._sources, self._source, self._given
        texts, colours = list(self._texts), self._colours
        selection, dragging = self._selection, self._dragging
        self._forget()
        if read and source is not None:
            parsed = parse_markdown(
                source, self.theme, references=self.references, math=bool(self.math)
            )
            blocks, sources = parsed.blocks, parsed.sources
        self._set_blocks(blocks, sources)
        self._source, self._given = source, given
        if self._texts == texts:
            # The same characters: what named ranges of them still does.
            self._colours = colours
            self._selection, self._dragging = selection, dragging

    def _recolour(self) -> None:
        """
        The role inks changed: the same blocks with other styles, handed over whole.
        """
        self._styles, self._style_index = [], {}
        self._ink_blocks(0)
        if self._doc is None or self._doc.closed:
            return
        if typesetter.module() is None:
            self._doc = None
            return
        try:
            whole = self._doc.set_blocks(self._described, typesetter.block_styles(self._styles))
            self.edits["set"] += 1
            self._cut(whole)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        # The heights the hosted blocks gave went with the blocks.
        self._drop_heights()

    # ------------------------------------------------------------------
    # Selection and copy
    # ------------------------------------------------------------------

    @property
    def selection(self) -> Range | None:
        """
        What is selected, as `((block, offset), (block, offset))` into `texts`; `None` if nothing.
        """
        return self._selection

    def _everything(self) -> Range | None:
        if not self._texts:
            return None
        last = len(self._texts) - 1
        return ((0, 0), (last, len(self._texts[last])))

    def select(self, selection: Range | None) -> None:
        """
        Select a range of text, or nothing; the view takes the selection as a press would.
        """
        if selection is not None:
            start, end = sorted((tuple(selection[0]), tuple(selection[1])))
            selection = None if start == end else ((start[0], start[1]), (end[0], end[1]))
        self._selection = selection
        self._all_selected = False
        self._dragging = False
        if selection is not None:
            self._own()

    def select_all(self) -> None:
        """
        Select everything, and go on selecting everything as the document grows.
        """
        self._selection = self._everything()
        self._all_selected = True
        self._dragging = False
        self._own()

    def clear_selection(self) -> None:
        """Select nothing."""
        self._selection = None
        self._all_selected = False
        self._dragging = False

    @property
    def owns_selection(self) -> bool:
        """Whether this view's selection is the current one in the process."""
        return SELECTION_OWNERSHIP.holds(self._owned)

    def _own(self) -> None:
        self._owned = SELECTION_OWNERSHIP.take()

    def selected_text(self) -> str:
        """
        The selection as the library copies it; `""` when nothing is selected.

        The module docstring says what a copy gives. One call into the
        library. Needs `typesetter.ready()`.
        """
        if self._selection is None:
            return ""
        doc = self._document()
        try:
            return str(doc.range_text(self._selection, self.separator))
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def copy(self, text: str | None = None) -> None:
        """
        Put `text` on the clipboard, or what Ctrl+C would when it is `None`.
        """
        from imgui_bundle import imgui

        imgui.set_clipboard_text(clipboard_text(self._copied() if text is None else text))

    def _copied(self) -> str:
        return self.copy_as(self) if self.copy_as is not None else self.selected_text()

    # ------------------------------------------------------------------
    # Marks
    # ------------------------------------------------------------------

    def set_marks(self, marks: object = None) -> None:
        """
        Draw `marks` with the text from now on; `None` or an empty sequence for none.

        Either what `imtypeset.Document.pack_marks` returned (and
        `advtext.typeset_find` makes), which is drawn as it is and **dropped
        at the next edit** -- it holds byte offsets into the texts as they
        were, so compare `revision` and hand over new ones -- or a sequence of
        `imtypeset.Mark` (or tuples in its field order), with positions into
        `texts`, which the view packs once and packs again after an edit. A
        mark naming a block that is not there is left out.

        Raises `TypeError`, and leaves the marks as they were, when one of a
        sequence has another shape (`advtext.typeset_find.Finder.matches` for
        its `marks()`, say). It is refused here because `draw` could only
        take it for a failure of the library and switch the library off.
        """
        if marks is not None and not _is_packed(marks):
            given: list[Any] = list(marks)  # type: ignore[call-overload]
            for number, mark in enumerate(given):
                if not _is_mark(mark):
                    raise TypeError(
                        f"set_marks: mark {number} is {mark!r}; a mark is (((block, offset), "
                        "(block, offset)), color[, place, thickness, offset]), which is what "
                        "advtext.typeset_find.Finder.marks() makes"
                    )
            marks = given
        self._marks = marks or None
        self._packed = self._marks if _is_packed(self._marks) else None
        self._drawn_marks = None

    def set_colours(self, block: int, spans: Iterable[object]) -> None:
        """
        Ink ranges of block `block`'s text: syntax colours for a code block, say.

        `spans` are `(start, end, colour)`, or objects with `start`, `end`
        and `ink` or `colour`: half-open ranges of `texts[block]` and an
        ImGui packed colour. They replace what the block had; an empty
        sequence takes them off. Drawn as `imtypeset.Mark`s in the ink's
        place, under the host's own marks, so nothing is laid out again.

        **What they cost.** Packing a block's, once, at the next draw. Then
        the library reads every mark it is handed at every draw (measured
        2026-10-11: 1,881 inks on a 600-line code block took a frame from 48
        to 2,515 microseconds), so the view hands over only the inks of the
        text the window shows: while any ink is set a frame makes **two more
        calls** (a hit test at the top of the clip rectangle and one at the
        bottom) and the library reads the inks between the two.

        **Kept for a block that an edit leaves alone and dropped for one it
        replaces**, so after a change colour the blocks from the first that
        changed. On a hosted block they draw nothing; in a table they ink
        the cells, by offsets into the table's text.
        """
        taken: list[tuple[int, int, int]] = []
        for span in spans:
            if isinstance(span, Sequence):
                start, end, colour = span[0], span[1], span[2]
            else:
                start, end = span.start, span.end  # type: ignore[attr-defined]
                colour = getattr(span, "ink", None)
                if colour is None:
                    colour = span.colour  # type: ignore[attr-defined]
            if end > start:
                taken.append((int(start), int(end), int(colour)))
        if taken:
            self._colours[int(block)] = tuple(sorted(taken))
        else:
            self._colours.pop(int(block), None)
        self._inked.pop(int(block), None)
        self._drawn_marks = None

    def clear_colours(self) -> None:
        """Take off every ink `set_colours` laid on."""
        if self._colours:
            self._colours, self._inked = {}, {}
            self._drawn_marks = None

    def _marks_for(
        self,
        doc: Any,
        clip: tuple[float, float, float] | None = None,
        across: tuple[float, float] | None = None,
    ) -> Any:
        """
        What the draw is handed: the host's marks, and the inks of the text in view.

        `clip` is the window's clip rectangle from the document's corner, as
        (top, bottom, width); with none, every ink is handed over. With no
        inks this asks the library nothing and packs once per change.

        `across` is for a document shown in columns: the clip rectangle's
        left and right edges from the document's corner (`_ink_edges`). The
        text in view then lies, in reading order, between the head of the
        column at its left edge and the foot of the column at its right.
        """
        count = len(self._texts)
        if self._marks is not None and self._packed is None:
            kept = []
            for mark in self._marks:
                (b0, o0), (b1, o1) = mark[0]
                if 0 <= b0 < count and 0 <= b1 < count:
                    clipped = (
                        (b0, min(max(o0, 0), len(self._texts[b0]))),
                        (b1, min(max(o1, 0), len(self._texts[b1]))),
                    )
                    kept.append((clipped, *mark[1:]))
            self._packed = doc.pack_marks(kept)
        if not self._colours:
            return self._packed if self._packed is not None else ()
        if clip is None:
            shown = (0, 0, count, 0)
        else:
            # A little more than the clip: a line whose box is just outside
            # it can still have ink inside it.
            left, right = across if across is not None else (0.0, clip[2])
            top = doc.hit_test((left, clip[0] - _INK_SLACK_PX)).position
            bottom = doc.hit_test((right, clip[1] + _INK_SLACK_PX)).position
            shown = (int(top[0]), int(top[1]), int(bottom[0]), int(bottom[1]))
        if self._drawn_marks is not None and shown == self._drawn_for:
            return self._drawn_marks
        parts: list[tuple[Any, int, int]] = []
        place = int(typesetter.module().MarkPlace.Ink)
        for at in sorted(self._colours):
            if at < shown[0] or at > shown[2] or at >= count or at in self._hosts:
                continue
            inks = self._inked.get(at)
            if inks is None:
                length = len(self._texts[at])
                spans = [
                    (max(start, 0), min(end, length), colour)
                    for start, end, colour in self._colours[at]
                    if min(end, length) > max(start, 0)
                ]
                inks = self._inked[at] = _Inks(
                    [span[0] for span in spans],
                    max((span[1] - span[0] for span in spans), default=0),
                    doc.pack_marks(
                        [(((at, start), (at, end)), colour, place) for start, end, colour in spans]
                    ),
                )
            # Sorted by where they start; none is longer than `longest`, so
            # none that starts before `first` reaches the first character shown.
            first = bisect_left(inks.starts, shown[1] - inks.longest) if at == shown[0] else 0
            stop = bisect_right(inks.starts, shown[3]) if at == shown[2] else len(inks.starts)
            if stop > first:
                parts.append((inks.packed, first, stop - first))
        if self._packed is not None and self._packed.count:
            parts.append((self._packed, 0, int(self._packed.count)))
        self._drawn_marks = _joined(parts) if parts else ()
        self._drawn_for = shown
        return self._drawn_marks

    # ------------------------------------------------------------------
    # Where things are
    # ------------------------------------------------------------------

    @property
    def origin(self) -> tuple[float, float] | None:
        """Where the document's top-left corner was on screen at the last `draw`, in pixels."""
        return self._origin

    @property
    def height(self) -> float:
        """
        The document's height at the last `draw`, in pixels.

        An estimate until every block has been in view once.
        """
        return self._height

    @property
    def hovered_link(self) -> str | None:
        """
        The target of the link under the mouse at the last `draw`, or `None`.

        `None` when the mouse is elsewhere, during a drag, and when something
        of the host's is in front of the text.
        """
        return None if self._hot is None else self._target(self._hot[1])

    @property
    def under_mouse(self) -> Any:
        """
        The `imtypeset.DocumentHit` under the mouse at the last `draw`, or `None`.

        `position.block` is the block (when `in_block`), for a host's menu or
        tooltip. `None` when the mouse is not over the view or a drag is on.
        """
        return self._hit

    def block_under_mouse(self) -> int | None:
        """
        The number of the block under the mouse at the last `draw`, or `None`.

        `None` when the mouse is not over the view, is between blocks or over
        a hosted widget, and during a drag. Read from `under_mouse`: no call.
        """
        hit = self._hit
        return int(hit.position.block) if hit is not None and hit.in_block else None

    @property
    def stats(self) -> ViewStats:
        """
        What the last `draw` did, with the library's counters for the document.

        One call into the library (`Document.stats`) at each read, and none
        when it is not read: it is not part of a frame's calls.
        """
        mine = ViewStats(self._whole, self._vertices, 0, 0, len(self._hosts_shown))
        doc = self.native_document
        if doc is None or typesetter.module() is None:
            return mine
        try:
            counted = doc.stats()
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        return mine._replace(
            blocks=int(counted.Blocks),
            blocks_deferred=int(counted.BlocksDeferred),
            blocks_laid_out=int(counted.BlocksLaidOut),
            blocks_drawn=int(counted.BlocksDrawn),
        )

    def set_lines(self, first_block: int = 0, stop_block: int | None = None) -> tuple[SetLine, ...]:
        """
        Each line of blocks `[first_block, stop_block)` as the library set it at the last layout.

        In reading order. Empty before the first draw. **It lays out every
        block asked about** (a call a block and a call a line), so ask for
        the blocks that could have changed and not for a long document; a
        hosted block has no lines, and a table answers what the library
        counts as its lines (`table_row` is what says where its rows are).
        """
        doc = self.native_document
        if doc is None or typesetter.module() is None:
            return ()
        stop = len(self._texts) if stop_block is None else min(stop_block, len(self._texts))
        lines: list[SetLine] = []
        try:
            for block in range(max(first_block, 0), stop):
                geometry = doc.block_geometry(block)
                x, y = geometry.full_min
                for number in range(int(geometry.line_count)):
                    line = doc.block_line(block, number)
                    lines.append(
                        SetLine(
                            block,
                            number,
                            int(line.text_start),
                            int(line.text_end),
                            x + line.min[0],
                            y + line.min[1],
                            x + line.max[0],
                            y + line.max[1],
                            y + line.baseline,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        return tuple(lines)

    def span_rects(
        self, block: int, start: int, end: int
    ) -> list[tuple[float, float, float, float]]:
        """
        One (left, top, right, bottom) per line a range of block `block`'s text touches.

        Pixels from the document's top-left corner (`origin` on screen), by
        `imtypeset.Document.range_rects`: one call, which lays the block out.
        Empty before the first draw and for a block that is not there.
        """
        doc = self.native_document
        if doc is None or typesetter.module() is None or not 0 <= block < len(self._texts):
            return []
        try:
            return [tuple(rect) for rect in doc.range_rects(((block, start), (block, end)))]
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def block_rect(self, block: int) -> tuple[float, float, float, float] | None:
        """
        Where block `block` is on screen, as (left, top, right, bottom) pixels; `None` if unknown.

        Its full extent, the space above and below it included, at the origin
        of the last `draw`. One call into the library, which lays the block
        out; the blocks above it may still be estimates.
        """
        if self._origin is None or not 0 <= block < len(self._texts):
            return None
        doc = self._document()
        try:
            geometry = doc.block_geometry(block)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        x, y = self._origin
        return (
            x + geometry.full_min[0],
            y + geometry.full_min[1],
            x + geometry.full_max[0],
            y + geometry.full_max[1],
        )

    def scroll_to(
        self,
        block: int,
        offset: int | None = None,
        *,
        margin_px: float = 24.0,
        align: float | None = None,
        always: bool = False,
    ) -> None:
        """
        Ask for a block, or the line holding `offset` in it, to be brought into view.

        Callable from anywhere: the request is kept and the next `draw`
        carries it out in the window it is drawn in, by
        `advtext.ui.bare_view.scroll_for`'s rule (`margin_px`, `align` and
        `always` are its). ImGui applies a scroll at the start of the frame
        after. The latest request is the one held, and it is looked at again
        on each of the next few draws (one library call each), because a
        block's place is an estimate until what is above it in the window has
        been laid out; a reader who scrolls in those frames is brought back.
        """
        self._scroll = (int(block), offset, float(margin_px), align, always, _SCROLL_FRAMES)

    @property
    def scrolled(self) -> bool:
        """Whether the last `draw` moved the pane for a `scroll_to`."""
        return self._scrolled

    def _carry_out_scroll(self, doc: Any, origin_x: float, origin_y: float) -> bool:
        request = self._scroll
        if request is None:
            return False
        from imgui_bundle import imgui

        block, offset, margin, align, always, left = request
        # Looked at again by the next draws whether or not this one moves
        # anything: what this draw lays out can move the block.
        self._scroll = (block, offset, margin, align, always, left - 1) if left > 1 else None
        if not 0 <= block < len(self._texts):
            self._scroll = None
            return False
        columns = self._columns
        if offset is None:
            geometry = doc.block_geometry(block)
            left, top, bottom = geometry.min[0], geometry.min[1], geometry.max[1]
            if columns is not None:
                # The block's corner on the page. As tall as the block is in
                # the uncut column: one cut in two is wherever its head is.
                left, head = doc.column_pos((left, top))
                top, bottom = head, head + (bottom - top)
        else:
            left, top, _, bottom = doc.caret_rect((block, offset))
        moved = False
        if columns is not None:
            if columns.height > 0.0:
                bottom = min(bottom, max(columns.height, top))
            moved = self._scroll_to_column(left, origin_x)
        scroll = float(imgui.get_scroll_y())
        # The place in the window's scrolled content.
        base = origin_y - imgui.get_window_pos().y + scroll
        target = scroll_for(
            base + top,
            base + bottom,
            scroll,
            float(imgui.get_window_size().y),
            margin=margin,
            align=align,
            always=always,
        )
        if target is not None:
            # As far as the window scrolled at its last frame; if the content
            # has grown since, the next look goes the rest of the way.
            target = min(target, float(imgui.get_scroll_max_y()))
        if target is None or abs(target - scroll) < 0.5:
            return moved
        imgui.set_scroll_y(target)
        return True

    def _scroll_to_column(self, left: float, origin_x: float) -> bool:
        """
        Bring the column holding page x `left` into view sideways, if it is not all in view.

        Its left edge is put where the page's is in a window not scrolled.
        A window that cannot scroll sideways is not moved: columns past the
        pane are then the host's to show (pages: "Columns").
        """
        from imgui_bundle import imgui

        columns = self._columns
        if columns is None or self._column_width <= 0.0:
            return False
        pitch = self._column_width + columns.gutter
        edge = math.floor(max(left, 0.0) / pitch + 1e-6) * pitch
        scroll = float(imgui.get_scroll_x())
        # The column's left edge in the window's scrolled content.
        at = origin_x - imgui.get_window_pos().x + scroll + edge
        if at >= scroll and at + self._column_width <= scroll + float(imgui.get_window_size().x):
            return False
        target = min(max(edge, 0.0), float(imgui.get_scroll_max_x()))
        if abs(target - scroll) < 0.5:
            return False
        imgui.set_scroll_x(target)
        return True

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def layout_for(self, width_px: float) -> float:
        """
        Lay the document out `width_px` wide, as `draw` is about to, and return its height.

        In columns `width_px` is what the columns stand across, as it is for
        `draw`, and the height is the page's.

        For a host that wants the layout before the draw: to time it apart,
        or to ask where something is (`block_rect`, `span_rects`) at the
        width the frame will use. What it costs is the hosted blocks' heights;
        text is laid out by the library when the window reaches it,
        which is in `draw`, so **the height is an estimate** until then and
        the time measured here is not "the layout". `draw` makes its own
        layout call afterwards all the same (the library answers it at once
        when nothing changed). Raises `TypesetUnavailable` as `draw` does.
        """
        doc = self._document()
        width_px = self._column_px(max(float(width_px), MIN_WIDTH_PX))
        wanted = self._host_wants(width_px)
        try:
            self._lay_out(doc, width_px, wanted)
            return float(doc.size()[1])
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    def _host_wants(self, width_px: float) -> dict[int, float]:
        """
        How tall each hosted widget says it is at this width. The host's code: outside `_failed`.
        """
        return {
            at: max(
                float(host.hosted.height_for(max(width_px - self._described[at].left_indent, 1.0))),
                0.0,
            )
            for at, host in self._hosts.items()
        }

    def _lay_out(self, doc: Any, width_px: float, wanted: dict[int, float]) -> None:
        """Tell the library what changed and lay out `width_px` wide: ONE column's width."""
        if self._style is None:
            self._style = typesetter.base_style(self.theme, int(self._palette.ink))
            self._style.SelectionColor = int(self._palette.highlight)
        if self._rule != self._palette.rule:
            self._rule = int(self._palette.rule)
            # A table's padding and its header rule are the theme's; the
            # rule's ink is the palette's, as a Rule block's is. Below one
            # scaled point the library is told "none" (zero would be its
            # own default).
            to_px = self._converter.px
            padding = to_px(self.theme.cell_padding)
            thickness = to_px(self.theme.table_rule_thickness)
            doc.set_options(
                typesetter.module().DocumentOptions(
                    QuoteBarColor=self._rule,
                    RuleColor=self._rule,
                    TableCellPadding=padding if padding > 0.0 else -1.0,
                    TableRuleThickness=thickness if thickness > 0.0 else -1.0,
                    TableRuleColor=self._rule,
                )
            )
        if self._columns != self._columns_told:
            columns = self._columns
            native = None
            if columns is not None:
                ts = typesetter.module()
                native = ts.Columns(
                    count=columns.count,
                    height=columns.height,
                    # The library reads 0 as its own default and below zero as none.
                    gutter=columns.gutter if columns.gutter > 0.0 else -1.0,
                    flags=ts.ColumnFlags.Balance if columns.balance else ts.ColumnFlags.None_,
                )
            doc.set_columns(native)
            self._columns_told = columns
        doc.layout(width_px, self._style)
        self._column_width = width_px
        for at, height in wanted.items():
            if self._host_heights.get(at) != height:
                doc.set_block_extent(at, height)
                self._host_heights[at] = height
                self._host_epoch += 1

    def draw(
        self,
        *,
        fonts: object = None,
        palette: Palette | None = None,
        width_px: float | None = None,
    ) -> bool:
        """
        Draw the document at the cursor, as wide as the pane, and handle the mouse and the keys.

        Call inside any window; a scrolling child is the usual one. The item
        this leaves as ImGui's last item is the view's whole rectangle.
        `fonts` is ignored (see the module docstring). False when something
        in view could not be set as asked (a face with no font, a formula the
        library refused); `stats` has more. Raises `TypesetUnavailable` when
        the library cannot draw; nothing has been drawn or claimed then.
        What a hosted widget raises leaves here as itself.
        """
        from imgui_bundle import imgui

        if palette is not None and palette is not self._palette and palette != self._palette:
            self.set_palette(palette)
        doc = self._document()
        self._begin_frame()
        if width_px is None:
            width_px = imgui.get_content_region_avail().x
        width_px = max(float(width_px), MIN_WIDTH_PX)
        cursor = imgui.get_cursor_screen_pos()
        x, y = math.floor(cursor.x + 0.5), math.floor(cursor.y + 0.5)
        native = imgui.get_window_draw_list()
        vertices = native.vtx_buffer.size()
        # What the document is laid out at: one column's width in columns.
        column_px = self._column_px(width_px)
        wanted = self._host_wants(column_px) if self._hosts else {}
        try:
            self._lay_out(doc, column_px, wanted)
            self._scrolled = self._carry_out_scroll(doc, x, y)
            # No draw list named: the current window's (`Document.draw(None, pos)`).
            marks = self._marks_for(
                doc,
                (
                    (native.get_clip_rect_min().y - y, native.get_clip_rect_max().y - y, width_px)
                    if self._colours
                    else None
                ),
                self._ink_edges(native, x) if self._colours else None,
            )
            whole = doc.draw(
                None, (x, y), selection=self._selection, marks=marks, debug=bool(self.debug)
            )
            # After the draw: it is the draw that lays out what the window shows.
            size = doc.size()
            self._height = float(size[1])
            # In columns the rectangle is the page's: every column and gutter.
            self._width = width_px if self._columns is None else float(size[0])
            self._origin = (x, y)
            if not self._hosts:
                self._hosts_shown = {}
            elif self._columns is None:
                self._hosts_shown = self._find_hosts(doc, y, width_px)
            else:
                self._hosts_shown = self._find_hosts_in_columns(doc, native, x, y)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        # The host's own code runs out here (a hosted widget's `draw`, and
        # below `copy_as` and `on_link`): what one of them raises is the
        # host's, and is no reason to switch the library off.
        if self._hosts:
            self._draw_hosts(x, y, width_px)
        self._whole = bool(whole)
        self._vertices = int(native.vtx_buffer.size() - vertices)
        try:
            followed = self._handle_mouse(
                doc, imgui.ImVec2(x, y), imgui.ImVec2(self._width, self._height)
            )
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        self._handle_keys()
        if followed is not None and self.on_link is not None:
            self.on_link(followed)
        return bool(whole)

    def _ink_edges(self, native: Any, x: float) -> tuple[float, float] | None:
        """
        In columns, the clip rectangle's left and right edges from the document's corner.

        A little outside it, as the inks' window is above and below, and
        never the PAGE's edges: a point in a column further right than the
        window shows would cut every column up to it, and so lay out the
        document. `None` for a document shown uncut.
        """
        if self._columns is None:
            return None
        left = max(native.get_clip_rect_min().x - x - _INK_SLACK_PX, 0.0)
        right = max(native.get_clip_rect_max().x - x + _INK_SLACK_PX, left)
        return (left, right)

    def _find_hosts_in_columns(
        self, doc: Any, native: Any, x: float, y: float
    ) -> dict[int, tuple[float, float, float, float]]:
        """
        Each hosted block in view on a page of columns: (left, top, right, bottom) from its corner.

        The library answers for a block in the uncut column, and
        `column_pos` takes its corner to the page; a hosted block is never
        cut. Asked only of the hosted blocks the columns under the clip
        rectangle hold, so that a widget far down the document does not cut
        every column before it: two `column` calls, then a `block_geometry`
        and a `column_pos` for each of those blocks.
        """
        columns = self._columns
        assert columns is not None
        column_px = self._column_width
        pitch = column_px + columns.gutter
        clip_min, clip_max = native.get_clip_rect_min(), native.get_clip_rect_max()
        first = max(math.floor((clip_min.x - x) / pitch), 0)
        last = math.floor((clip_max.x - x) / pitch)
        if last < first:
            return {}
        head = doc.column(first)
        if not head.exists:
            return {}
        foot = head if last == first else doc.column(last)
        # A column past the last one there is: everything to the end.
        stop = int(foot.end[0]) if foot.exists else len(self._texts)
        shown: dict[int, tuple[float, float, float, float]] = {}
        for at in self._hosts:
            if at < int(head.start[0]) or at > stop:
                continue
            left, top, bottom = _block_rect(doc, at)
            page_x, page_y = doc.column_pos((left, top))
            right = max(page_x - left + column_px, page_x + 1.0)
            rect = (float(page_x), float(page_y), float(right), float(page_y + bottom - top))
            if y + rect[3] < clip_min.y or y + rect[1] > clip_max.y:
                continue
            if x + rect[2] < clip_min.x or x + rect[0] > clip_max.x:
                continue
            shown[at] = rect
        return shown

    def _find_hosts(
        self, doc: Any, y: float, width_px: float
    ) -> dict[int, tuple[float, float, float, float]]:
        """
        Each hosted block in view, as (left, top, right, bottom) from the document's corner.

        Where every hosted block is, is asked of the library once (a call
        each) and kept until the document's height, the width or a hosted
        block's height changes; from then on only one the clip rectangle
        reaches is asked again.
        """
        from imgui_bundle import imgui

        key = (self._height, width_px, self._host_epoch)
        asked = key != self._rects_key
        if asked:
            self._rects = {at: _block_rect(doc, at) for at in self._hosts}
            self._rects_key = key
        native = imgui.get_window_draw_list()
        clip_top, clip_bottom = native.get_clip_rect_min().y, native.get_clip_rect_max().y
        shown: dict[int, tuple[float, float, float, float]] = {}
        for at in self._hosts:
            left, top, bottom = self._rects[at]
            if y + bottom < clip_top or y + top > clip_bottom:
                continue
            if not asked:
                left, top, bottom = self._rects[at] = _block_rect(doc, at)
            shown[at] = (left, top, max(width_px, left + 1.0), bottom)
        return shown

    def _draw_hosts(self, x: float, y: float, width_px: float) -> None:
        """
        Hand each hosted widget in view its rectangle; give the others their keys.

        The cursor is put back afterwards: the view claims its whole
        rectangle itself, with the item that follows.
        """
        from imgui_bundle import imgui

        cursor = imgui.get_cursor_screen_pos()
        try:
            for at, host in self._hosts.items():
                rect = self._hosts_shown.get(at)
                if rect is None:
                    keys = getattr(host.hosted, "handle_keys", None)
                    if callable(keys):
                        keys()
                    continue
                imgui.set_cursor_screen_pos(imgui.ImVec2(x + rect[0], y + rect[1]))
                host.hosted.draw(palette=self._palette, width_px=rect[2] - rect[0])
        finally:
            imgui.set_cursor_screen_pos(cursor)

    def _in_host(self, local: tuple[float, float]) -> bool:
        """Whether a point from the document's corner is on a hosted widget the last draw showed."""
        return any(
            left <= local[0] < right and top <= local[1] < bottom
            for left, top, right, bottom in self._hosts_shown.values()
        )

    def _begin_frame(self) -> None:
        """
        End a drag or a held link this view did not see through the previous frame.
        """
        from imgui_bundle import imgui

        frame = int(imgui.get_frame_count())
        if frame - self._drawn_frame > 1:
            self._dragging = False
            self._link_down = None
        self._drawn_frame = frame

    def _button_id(self) -> str:
        return f"##advtext-typeset-{id(self):x}"

    def _item_in_front(self) -> bool:
        """
        Whether an item other than this view's own drag button is under the mouse.

        `BareView._item_in_front` has the reasoning.
        """
        from imgui_bundle import imgui

        hovered_id = getattr(getattr(imgui, "internal", None), "get_hovered_id", None)
        if hovered_id is None:
            return bool(imgui.is_any_item_hovered())
        hovered = hovered_id()
        return bool(hovered != 0 and hovered != imgui.get_id(self._button_id()))

    def _handle_mouse(self, doc: Any, origin: imgui.ImVec2, size: imgui.ImVec2) -> str | None:
        """
        The link under the mouse, a press, a drag, a release; and the item that claims the space.

        Returns the target of a link that was clicked on this frame, for `draw` to follow.
        """
        from imgui_bundle import imgui

        left = imgui.MouseButton_.left
        mouse = imgui.get_mouse_pos()
        local = (mouse.x - origin.x, mouse.y - origin.y)
        down = imgui.is_mouse_down(left)

        # Another view began a selection since this one last did.
        if self._owned and not self.owns_selection:
            self._selection = None
            self._all_selected = False
            self._dragging = False
            self._owned = 0
        # The button is up and did not come up on this frame: the release was
        # on a frame this view was not drawn.
        if self._dragging and not down and not imgui.is_mouse_released(left):
            self._dragging = False

        # While this view's own button is the active item ImGui counts the
        # window's hover as blocked; that is the view blocking itself.
        held = self._dragging or self._link_down is not None
        flags = imgui.HoveredFlags_.allow_when_blocked_by_active_item.value if held else 0
        over = (
            size.y > 0.0
            and imgui.is_window_hovered(flags)
            and not self._item_in_front()
            and imgui.is_mouse_hovering_rect(
                origin, imgui.ImVec2(origin.x + size.x, origin.y + size.y)
            )
            # The mouse over a hosted widget is the widget's: no hit test, no
            # press, no link of this view's.
            and not (self._hosts_shown and self._in_host(local))
        )
        self._hit = None
        self._hot = None
        if over and not self._dragging:
            hit = self._hit = doc.hit_test(local)
            if hit.tag and hit.inside and self._target(hit.tag) is not None:
                self._hot = (int(hit.position.block), int(hit.tag))

        clicked = over and imgui.is_mouse_clicked(left)
        live = self._hot is not None and self.on_link is not None
        if clicked and live:
            self._link_down = self._hot
        press = clicked and not live

        # An item only for the length of a drag or a held link. Both branches
        # advance the cursor by the same size.
        if (press or self._dragging or self._link_down is not None) and size.y > 0.0:
            imgui.invisible_button(self._button_id(), size)
        else:
            imgui.dummy(size)

        if press:
            self._own()
            clicks = int(imgui.get_mouse_clicked_count(left))
            self._granularity = min(max(clicks, 1), 3) - 1  # character, word, line
            picked = doc.select_range(local, local, self._granularity)
            self._anchor = (_position(picked.start), _position(picked.end))
            self._dragging = True
            self._all_selected = False
            self._selection = None if self._anchor[0] == self._anchor[1] else self._anchor
        elif self._dragging:
            under = doc.select_range(local, local, self._granularity)
            start = min(self._anchor[0], _position(under.start))
            end = max(self._anchor[1], _position(under.end))
            self._selection = None if start == end else (start, end)
            if not down:
                self._dragging = False

        if live and self.hand_cursor:
            imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
        if self._link_down is not None and not clicked:
            if imgui.is_mouse_released(left):
                pressed, self._link_down = self._link_down, None
                if self._hot == pressed:
                    return self._target(pressed[1])
            elif not down:
                self._link_down = None
        return None

    def _handle_keys(self) -> None:
        """
        Ctrl+A and Ctrl+C, when this view owns the selection and no text input is active.
        """
        from imgui_bundle import imgui

        if not self.owns_selection:
            return
        io = imgui.get_io()
        if io.want_text_input or not io.key_ctrl:
            return
        if imgui.is_key_pressed(imgui.Key.a, False):
            self._selection = self._everything()
            self._all_selected = True
            self._dragging = False
        if self._selection is not None and imgui.is_key_pressed(imgui.Key.c, False):
            imgui.set_clipboard_text(clipboard_text(self._copied()))


def _position(position: Any) -> Position:
    return (int(position[0]), int(position[1]))


def _length(value: object, name: str) -> float:
    """
    A length in pixels handed to `set_columns`: a finite number of zero or more, as a float.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"set_columns: {name} is {value!r}; it is a number of pixels")
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"set_columns: {name} is {value!r}; it is finite and zero or more")
    # The library takes a C `float`: a number too large for one arrives as
    # infinity, and one too small as zero, which means something else there
    # (no height is "not filled in order"; no gutter is none).
    narrowed = ctypes.c_float(value).value
    if not math.isfinite(narrowed) or (value > 0.0 and narrowed == 0.0):
        raise ValueError(
            f"set_columns: {name} is {value!r}, which the library's single-precision "
            f"float holds as {narrowed!r}; give a number of pixels it can hold"
        )
    return float(value)


def _is_default(value: object, default: object) -> bool:
    """Whether an argument of `set_columns` was left as it is declared: the same type and value."""
    return type(value) is type(default) and value == default


def _block_rect(doc: Any, block: int) -> tuple[float, float, float]:
    """
    (left, top, bottom) of a hosted block from the document's corner, without its spacing.
    """
    geometry = doc.block_geometry(block)
    return (float(geometry.min[0]), float(geometry.min[1]), float(geometry.max[1]))


def _is_mark(mark: Any) -> bool:
    """
    Whether `mark` has the fields of an `imtypeset.Mark`, in its order and of its types.
    """
    try:
        (b0, o0), (b1, o1) = mark[0]
        return (
            2 <= len(mark) <= 5
            and all(isinstance(value, int) for value in (b0, o0, b1, o1, *mark[1:3]))
            and all(isinstance(value, (int, float)) for value in mark[3:])
        )
    except (TypeError, ValueError, LookupError):
        return False


def _is_column(column: Any) -> bool:
    """
    Whether `column` is a `ColumnDescription` of the types the library packs: an integer, two reals.
    """
    return (
        isinstance(column, ColumnDescription)
        and isinstance(column.align, int)
        and isinstance(column.width, (int, float))
        and isinstance(column.share, (int, float))
    )


def _is_packed(marks: object) -> bool:
    """
    Whether `marks` is what `imtypeset.Document.pack_marks` returned and not a sequence of marks.
    """
    return hasattr(marks, "array") and hasattr(marks, "count") and not isinstance(marks, Sequence)


def _role_of(block: object) -> str:
    """
    The name of the `BlockKind` a block plays, which is what `Palette.roles` is keyed by.

    A text block says so itself (`kind`); a code block and a table are each
    one kind and are known by their class (`MarkdownCode`, `MarkdownTable`).
    `""` for a rule and for anything else: a rule's colour is `Palette.rule`.
    """
    if isinstance(block, MarkdownText):
        return block.kind.name
    if isinstance(block, MarkdownCode):
        return "CODE"
    if isinstance(block, MarkdownTable):
        return "TABLE"
    return ""


def _joined(parts: Sequence[tuple[Any, int, int]]) -> Any:
    """
    Stretches of results of `imtypeset.Document.pack_marks` as one, in the order given.

    Each part is (a packed result, the first mark to take, how many). The
    library's draw takes one array. A packed result is an array of the
    library's mark struct and a count, and is made again here from the
    parts: that is the shape of a private class of a package this tree does
    not own (`imtypeset._Marks(array, count)`), and
    `tests/test_typeset_view.py` draws through it so that a change there is a
    red test and not a wrong colour.
    """
    packed = parts[0][0]
    kind = packed.array._type_
    size = ctypes.sizeof(kind)
    count = sum(part[2] for part in parts)
    array = (kind * max(count, 1))()
    at = 0
    for source, first, taken in parts:
        ctypes.memmove(
            ctypes.byref(array, size * at), ctypes.byref(source.array, size * first), size * taken
        )
        at += taken
    return type(packed)(array, count)

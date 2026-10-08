r"""
Per-unit layout: each independent run of blocks shipped once, and stacked by offset.

`advtext.ui.compose` returns one box for a whole document, and until this module
existed `DocumentView.layout_for` shipped that box and indexed the result every
time anything changed. Composition already had a per-block cache
(`advtext.ui.LayoutCache`); ship-out, the culling index and the selection index
had none, so a one-word edit to one paragraph re-walked every box in the
document and rebuilt every `Line`, `Glyph` and `Fragment` in it. This module is
the missing half: the **shipped** form of each unit is kept, and a document is
a list of units with a y offset and an index base each.

It imports no ImGui. Everything here is arithmetic over shipped commands, which
is why it sits beside `compose` and is tested with no window.

## The unit is a run, not a block

`advtext.ui.block_runs` has the argument: consecutive quoted blocks share one
bar, so they are one box and one unit. Everything else is a unit of one block.
A unit therefore covers a *range* of the document's blocks, and
`PlacedUnit.block_start` says where it begins.

## Why stacking is exact, and what "exact" was checked against

Between two runs `compose_blocks` puts a kern and restarts `prev_depth`, so no
interline glue depends on both sides of a run boundary. Vertical positions in
ship-out are sums of integer scaled points, so a unit shipped with its top at
zero and then moved down by the sum of everything above it lands every command
on the same integer the whole-document ship gave it. Reading-order indices are
dense, so a unit's indices moved up by the count of items above it are the
whole-document indices.

That is an argument, and the house rule is that an argument is not evidence.
`tests/test_units_layout.py` asserts `UnitLayout.cmds == ship(compose(...))`
command for command on `demo/sample.md` and on a document with one of every
block kind, at several measures; and that every `UnitModel` query agrees with
the flat `SelectionModel` over a grid of points and a sweep of ranges.

## Local commands, placed lazily

`advtext.shipout.ship` takes an origin but no index base, and its commands are
frozen. Moving a unit therefore means rebuilding each of its commands, which
costs about what shipping it did. So a `Unit` holds commands in **its own
coordinates** -- top at y = 0, first item at index 0 -- and a `PlacedUnit`
derives the moved copy only when something asks for it: the draw call for a
unit that is on screen, hit testing for the unit under the mouse, `rects` and
`text` for the units a selection covers. A unit that is off screen and
unselected is never moved at all. The first unit of a document needs no move
and hands back its local commands unchanged.

The moved copies are memoised on a `_Placement`, and `layout_units` reuses the
placement from the previous layout whenever the unit, its offset and its index
base are all unchanged. So an edit that leaves a block's height and item count
alone re-derives nothing below it, and one that changes its height re-derives
the units below it one at a time as they scroll into view.

## The selection index is built per unit, and only when touched

`UnitModel` answers every query `advtext.selection.SelectionModel` answers --
it is the same code, `advtext.selection.FragmentQueries` -- but it finds
fragments by bisecting to a unit first. `fragment_at` builds the fragments of
the unit under the point; `rects` and `text` build those of the units the range
covers. A document nobody has clicked on has no selection index at all.

## What a copy reads as, which only this layer can say

Shipped commands do not distinguish a line the breaker wrapped from a line the
author ended, and `advtext.selection` therefore takes the difference as data:
a mapping from a reading-order boundary to the separator that belongs before
it. The blocks are where that data is, so it is built here, per unit, and
`UnitModel.copy_text` is `text` with it passed:

- between two blocks, `BLOCK_BREAK` (a blank line) -- but between two blocks
  inside one list, at any nesting, `LINE_BREAK`, and then `LIST_INDENT` for
  each list the block is inside beyond the first (`UnitModel._leads` has the
  rule and how the depth is read);
- between two lines of a code block, and at a markdown hard break,
  `LINE_BREAK`;
- between two rows of a table `LINE_BREAK`, between two cells `CELL_BREAK`; an
  empty cell still gets its tab;
- between a list marker and the item's text, one space -- the gap is a kern,
  which has no index, so nothing else would put one there.

A line the breaker wrapped, including a wrapped line of a table cell, still
joins with a space. `tests/test_units_layout.py` pins whole documents as the
exact string a copy gives.

## A long code block in pieces

A unit is normally a whole block. That is the wrong unit for one thing: a code
block that is still being written. Its unit misses on every appended line, and
composing and shipping it is linear in its length -- measured through
`advtext.ui.stream_view` at 13 ms a line when the fence is 100 lines long, 102
ms at 600 and 477 ms at 2000, for a line that changed nothing above itself.

A code block's lines are independent of each other: no line break is chosen,
and the only thing joining two lines is §679's interline glue, which depends
on the depth of the one and the height of the other and nothing else. So
`layout_units(..., code_lines=n)` lays a code block of more than `n` lines out
as **pieces** of `n` lines, each a unit of its own, stacked with exactly the
interline glue the whole block would have put between those two lines
(`_piece_gap`). A piece whose lines have not changed is found in the cache
like any other unit, so a line appended to a long fence composes and ships
the last piece -- at most `n` lines -- whatever the block's length.

What stays true, and `tests/test_units_layout.py` asserts each against the
whole-block layout of the same document: the commands and their indices; the
answer to every selection query; the text a copy gives, line breaks included;
`block_at` naming one block for every y the block covers. What changes is the
*shape* of the layout, for a caller that walks `placed`:

- a block in pieces is several consecutive `PlacedUnit`s with one
  `block_start`, numbered by `part`; `blocks` of each is a `CodeBlock`
  holding that piece's lines, not the document's block;
- `unit_of_block` gives the first piece; `units_of_block` and
  `indices_of_block` give all of the block.

It is off by default (`code_lines=0`), so nothing that lays out a settled
document changes shape; the streaming view asks for it.

## A long table in pieces

The same, for the other block a model writes a row at a time. A table of
thirty rows was composed, shipped and indexed whole for every row appended:
5.7 ms a row at 30 rows and 42 ms at 200, measured through
`advtext.ui.stream_view`.

A table is not as easy to cut as a code block, because its column widths are
a property of every row. But **once the widths are given, a row depends on
nothing but itself**: `advtext.ui._table_boxes` sets each row to the widths
and joins two rows with §679's interline glue, as it joins two lines. So
`layout_units(..., table_rows=n)` settles the widths first -- the table's own
if it is a `SizedTable` that states them, else what `table_columns` gives for
the whole table at this measure -- and lays a table of more than `n` rows out
as pieces of `n` rows, each a `SizedTable` at those widths and a unit of its
own. The first piece has the header and the rule under it; the rest have no
header. A row added to a long table then composes and ships the last piece.

**When the widths change, every piece is laid out again.** That is not a
shortcoming of the cut: a column that got wider moves every cell to its
right in every row. It happens when a cell arrives that is the widest its
column has had, and `.concerns/AF-livetable--builder--result.md` has how often
that was on a table of realistic shape.

What stays true is what stays true of a code block in pieces, asserted in
`tests/test_units_layout.py` against the same table laid out whole, with
wrapped rows on both sides of a cut: commands and indices, every selection
query, copy text with its tabs and newlines, `block_at`, and the links in
its cells (`PlacedUnit.skipped` is how a link keeps its number). A table is
not cut if a row has another number of cells than the table has widths, or
a width is under one scaled point: a `SizedTable` cannot say either.

## What a unit cannot do

- **It does not make a resize cheaper.** A unit is keyed by the width it was
  broken to, for the reason `LayoutCache` gives at length. Every unit misses on
  every width change.
- **Units are assumed to be stacked top to bottom without overlap** for the
  *nearest-line* half of `fragment_at` (a point in the gap between two units
  belongs to the nearer of its two neighbours). Culling makes no such
  assumption: it bounds each unit by its own ink and is exact for any geometry.
- **Inside a quote, a block's items are found by where they sit, not by
  construction.** `Unit.spans` gives each block of a run its index range, and
  for a run of several blocks that is read back off the shipped commands by
  comparing each item's baseline with the blocks' vertical extents
  (`ComposedRun.extents`). It is checked against laying each block out alone,
  but it rests on one paragraph of a quote ending above where the next begins.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import accumulate, chain
from time import perf_counter
from typing import assert_never

from advtext.linebreak import LineBreakParams
from advtext.markdown import (
    Block,
    CodeBlock,
    FormulaSpan,
    RuleBlock,
    TableBlock,
    TextBlock,
)
from advtext.nodes import EJECT_PENALTY, Box, CharNode, Kern, Node, Penalty
from advtext.pack import CharMeasure, InterlineSkip, interline_glue, vpack
from advtext.selection import (
    Boundary,
    Fragment,
    FragmentQueries,
    Rect,
    Selection,
    SelectionModel,
    fragment_nearest,
)
from advtext.shipout import Atom, DrawCmd, Glyph, Line, Point, RuleRect, SetGlue, ship
from advtext.spans import (
    SpanMap,
    SpanMapError,
    index_count,
    map_code_block,
    map_table,
    map_text_block,
    replaced_within,
)
from advtext.style import BlockKind, Theme
from advtext.ui import (
    CacheStats,
    CommandIndex,
    ComposedRun,
    HostBlock,
    LayoutCache,
    RunComposer,
    SizedTable,
    Viewport,
    block_runs,
    prev_depth_after,
    run_gap,
    table_columns,
)
from advtext.units import Scaled

__all__ = [
    "BLOCK_BREAK",
    "CELL_BREAK",
    "CODE_PIECE_LINES",
    "LINE_BREAK",
    "LIST_INDENT",
    "TABLE_PIECE_ROWS",
    "LayoutStats",
    "PlacedUnit",
    "Unit",
    "UnitCache",
    "UnitLayout",
    "UnitModel",
    "carry_caret",
    "carry_selection",
    "layout_units",
    "moved",
    "ship_unit",
]


BLOCK_BREAK = "\n\n"
"""
What a copy puts between two blocks: a blank line, as between two paragraphs of plain text.
"""

LINE_BREAK = "\n"
"""
What a copy puts where a line end is content: between code lines, list items and
table rows, and at a hard break.
"""

CELL_BREAK = "\t"
"""
What a copy puts between two cells of a table row, so that it pastes into a spreadsheet as cells.
"""

LIST_INDENT = "  "
"""
What a copy puts at the head of a line for each list it is inside beyond the first.
"""

_LIST_ITEMS = frozenset({BlockKind.BULLET_ITEM, BlockKind.ORDERED_ITEM})

CODE_PIECE_LINES = 16
"""
How many lines a piece of a long code block holds, for a caller that wants pieces at all.

`layout_units` does not default to it -- pieces are asked for, by
`advtext.ui.stream_view` -- but this is the size it was measured at. It is
the most a line appended to an open fence can cost to lay out: the last piece
is composed and shipped again, and that is at most this many lines. Measured
with 75-character lines on a busy machine, a line costs about 0.2 ms to
compose and ship, so 0.2 to 3.5 ms an append as the piece fills, and the mean
over a whole piece was 2.9 ms at 100 lines, 3.2 at 600 and 3.4 at 2000 with
the parse and the visible commands included.

Smaller makes an append cheaper and a long block more units. Each unit costs
a layout a few microseconds whether or not it changed, which is the part that
still grows with the block: at 16 a 2000-line block is 125 units. Sixteen,
twenty-four and thirty-two were tried at those three lengths and sixteen was
the cheapest at each (3.4, 5.7 and 8.0 ms at 2000 lines).
"""

TABLE_PIECE_ROWS = 4
"""
How many rows a piece of a long table holds, for a caller that wants pieces at all.

As `CODE_PIECE_LINES` is for a code block, and smaller because a row costs
more than a line: a cell packed for each column, and a line break for each
one that wraps. It is the most a row appended to a long table can cost to
lay out.

Measured through `advtext.ui.stream_view` on a three-column table of rows
of one width, a row an append, mean over rows 129 to 192 with the parse and
the visible commands included
(`.concerns/AF-livetable-scripts/measure.py.txt`, `pieces`):

    rows a piece    held at natural widths    wrapped to a 260 px measure
          4               1.10 ms                     2.49 ms
          8               1.46 ms                     3.65 ms
         16               2.29 ms                     6.08 ms
         32               4.03 ms                    11.40 ms
      (whole)            32.89 ms                    97.16 ms

Four was the cheapest at both, at a length where its forty-eight units are
each costing a layout their few microseconds. Smaller was not tried: at two
the last piece saves a row and the unit count doubles.
"""

MOVE_WHOLE_BELOW = 4000
"""
How many commands a unit may have and still be moved into place whole when part of it shows.

Below this the whole unit is moved once and kept, which makes every later
frame free. Above it only the visible slice is moved, and moved again when
the window does. Four thousand commands is a paragraph of some four thousand
characters or a code block of about eighty lines; moving that many costs a
few milliseconds, once.
"""


@dataclass(frozen=True, slots=True)
class Unit:
    """
    One run of blocks, composed, shipped and indexed for culling, in its own coordinates.

    **Local coordinates**: the top of the unit is y = 0 and its first pointable
    item is index 0. Nothing in a `Unit` knows where in a document it sits,
    which is what lets one be reused when the blocks above it change -- and
    lets two equal runs in one document share a single `Unit`.

    `count` is how many reading-order indices the unit consumes: its glyphs and
    its horizontal glue. `ink` is `(min top, max bottom, max top, min bottom)`
    over its commands' extents, which is what culling needs to decide "none of
    it", "all of it" or "look at each command" without looking at any command.
    """

    blocks: tuple[Block, ...]
    """The run this unit sets: one block, or a run of consecutive quoted ones."""
    box: Box
    """The run's vbox, as `advtext.ui.RunComposer.compose` returned it."""
    extents: tuple[tuple[Scaled, Scaled], ...]
    """`(top, bottom)` of each block in `blocks`, measured down from the unit's top."""
    cmds: tuple[DrawCmd, ...]
    """The shipped commands, in local coordinates."""
    index: CommandIndex
    """The vertical extent of every command in `cmds`, local."""
    count: int
    """How many reading-order indices this unit consumes."""
    ink: tuple[Scaled, Scaled, Scaled, Scaled]
    """`(min top, max bottom, max top, min bottom)` over `index`; zeros when empty."""
    lines: int
    """How many `Line` commands it shipped. Zero means nothing here can be pointed at."""
    spans: tuple[tuple[int, int], ...]
    """`[start, end)` of each block's reading-order indices, local. Tiles `[0, count)`."""
    build_seconds: float = field(default=0.0, compare=False)
    """
    What composing and shipping this unit took, in seconds, when a `UnitCache` built it.

    One wall-clock sample of one build (`time.perf_counter` either side of
    `RunComposer.compose` and `ship_unit`), kept with the unit for as long as
    it is reused -- so it is what the unit cost *when it was built*, not what
    the layout that reused it paid. Zero for a unit built by `ship_unit`
    directly. Not part of the unit's value: two units are equal whatever they
    cost.
    """

    @property
    def height(self) -> Scaled:
        """
        The unit's full vertical extent: what the next unit is stacked below.
        """
        return self.box.height + self.box.depth


def ship_unit(composed: ComposedRun, measure: CharMeasure) -> Unit:
    """
    Ship one composed run with its top at zero, and index it for culling.

    This is the whole per-unit cost that the cache exists to avoid repeating:
    one `ship` and one `CommandIndex.of`. `UnitCache.misses` counts calls to
    it, so "only the changed block was re-shipped" is a number a test reads
    rather than a claim.

    `count` is read off the `Line` commands rather than by counting items: a
    top-level run is a vbox of lines, so every indexed item is inside some
    line, and the largest `end` is one past the last index ship-out assigned.
    """
    box = composed.box
    cmds = tuple(ship(box, Point(0, box.height), measure=measure))
    index = CommandIndex.of(cmds)
    ends = [cmd.end for cmd in cmds if isinstance(cmd, Line)]
    ink = (
        (min(index.tops), max(index.bottoms), max(index.tops), min(index.bottoms))
        if cmds
        else (0, 0, 0, 0)
    )
    count = max(ends, default=0)
    return Unit(
        blocks=composed.blocks,
        box=box,
        extents=composed.extents,
        cmds=cmds,
        index=index,
        count=count,
        ink=ink,
        lines=len(ends),
        spans=_spans(cmds, composed.extents, count),
    )


def _spans(
    cmds: tuple[DrawCmd, ...], extents: tuple[tuple[Scaled, Scaled], ...], count: int
) -> tuple[tuple[int, int], ...]:
    """
    Which reading-order indices each block of a run owns, as local `[start, end)`.

    A run of one owns all of them and nothing is looked at. For a quote, the
    blocks are stacked top to bottom and reading order runs the same way, so
    the ranges are contiguous and only the boundaries need finding: an item
    belongs to the first block whose bottom edge is at or below its baseline.
    A baseline is never below its own line's bottom, and the next paragraph's
    first baseline is below the previous paragraph's bottom by at least its
    own line height, so the comparison cannot put an item in the wrong block
    unless a paragraph's first line has no height at all.

    A block that set nothing gets an empty range at the position it would
    have had, so the ranges always tile `[0, count)`.
    """
    if len(extents) == 1:
        return ((0, count),)
    bottoms = [bottom for _, bottom in extents]
    starts = [count] * len(extents)
    for cmd in cmds:
        if isinstance(cmd, Glyph | SetGlue):
            block = min(bisect_left(bottoms, cmd.y), len(extents) - 1)
            starts[block] = min(starts[block], cmd.index)
    # An empty block starts where the next non-empty one does.
    for block in range(len(starts) - 2, -1, -1):
        starts[block] = min(starts[block], starts[block + 1])
    starts[0] = 0
    return tuple(zip(starts, [*starts[1:], count], strict=True))


def _separators_within(unit: Unit) -> dict[int, str]:
    """
    Where, inside one unit, a break is content: local index to separator.

    One rule per block type, and each reads the structure from where
    composition left it rather than guessing from geometry:

    - **Between the blocks of a quote**, a blank line, at each later block's
      first index (`Unit.spans`).
    - **A list item's marker** is `\\hss`, the marker's glyphs, then a kern.
      The kern has no index, so the space between "1." and the text has to be
      said: one space before the item's first own index.
    - **A hard break** is a forced penalty in the material. The item that
      follows it is found through `advtext.spans`, which is the only thing
      that knows which shipped index a material node became. A block with no
      forced break is not mapped at all.
    - **A code block** is one line per source line, so every `Line` after the
      first begins with a newline. A blank source line needs nothing here:
      `advtext.selection` writes one for any empty line.
    - **A table** is walked as boxes -- rows, then cells -- because a row that
      did not wrap is a single line and has no command per cell. Separators
      at one index are concatenated, which is what makes an empty cell keep
      its tab: its start is also the next cell's.
    """
    separators: dict[int, str] = {}

    def add(index: int, text: str) -> None:
        separators[index] = separators.get(index, "") + text

    for position, block in enumerate(unit.blocks):
        start, stop = unit.spans[position]
        if position:
            separators[start] = BLOCK_BREAK
        match block:
            case TextBlock():
                if block.marker:
                    gap = start + 1 + index_count(block.marker)
                    if gap < stop:
                        separators[gap] = " "
                for index in _after_hard_breaks(unit, block, start, stop):
                    separators[index] = LINE_BREAK
            case CodeBlock():
                for cmd in unit.cmds:
                    if isinstance(cmd, Line) and cmd.start > start:
                        separators[cmd.start] = LINE_BREAK
            case TableBlock():
                cursor = start
                rows = [
                    node
                    for node in unit.box.contents
                    if isinstance(node, Box) and any(isinstance(c, Box) for c in node.contents)
                ]
                for row_number, row in enumerate(rows):
                    if row_number:
                        add(cursor, LINE_BREAK)
                    cells = [child for child in row.contents if isinstance(child, Box)]
                    for cell_number, cell in enumerate(cells):
                        if cell_number:
                            add(cursor, CELL_BREAK)
                        cursor += index_count(cell)
            case _:
                pass
    return separators


def _atoms_within(unit: Unit) -> dict[int, str]:
    """
    What each inline formula in a unit copies as: local index to `$source$`.

    A formula is one shipped item (`advtext.shipout.Atom`) and the commands do
    not say what it was built from; the block does (`TextBlock.formulas`,
    `TableCell.formulas`, in material indices), and `advtext.spans` is what
    turns a material index into a shipped one. A unit with no formula is not
    mapped at all. A block that cannot be mapped gives nothing, and its
    formulae then copy as nothing: as with a hard break, wrong, and far better
    than an exception out of a copy.
    """
    atoms: dict[int, str] = {}

    def name(formulas: tuple[FormulaSpan, ...], mapped: SpanMap) -> None:
        for formula in formulas:
            index = mapped.shipped_index(formula.index)
            if index is not None:
                atoms[index] = formula.text

    for position, block in enumerate(unit.blocks):
        start, stop = unit.spans[position]
        try:
            match block:
                case TextBlock() if block.formulas:
                    if len(unit.blocks) == 1:
                        name(block.formulas, map_text_block(block, unit.cmds))
                    else:
                        name(
                            block.formulas,
                            map_text_block(block, unit.cmds, start=start, stop=stop),
                        )
                case TableBlock() if any(
                    cell.formulas for row in (block.header, *block.rows) for cell in row
                ):
                    for cell, mapped in map_table(block, unit.box, base=start):
                        name(cell.formulas, mapped)
                case _:
                    pass
        except SpanMapError:
            continue
    return atoms


def _originals_within(unit: Unit) -> dict[int, str]:
    """
    What each replaced character in a unit copies as: local index to the character.

    A character no face of the theme has is set as U+FFFD, and the glyph
    shipped for it is U+FFFD; the node keeps what was written
    (`advtext.markdown.ReplacedChar`), and `advtext.spans` turns the node's
    place in the material into a shipped index, as for a formula
    (`_atoms_within`). A block with no such node -- nearly every block --
    costs one pass over its material and is not mapped. A block that cannot
    be mapped gives nothing and its replaced characters then copy as the
    U+FFFD that is drawn: wrong, and far better than an exception out of a
    copy.

    Not looked into: a list marker (this tree's are a bullet and digits) and
    the inside of a formula box, which copies as its source whatever it holds.
    """
    originals: dict[int, str] = {}

    def name(replaced: dict[int, str], mapped: SpanMap) -> None:
        for material_index, character in replaced.items():
            index = mapped.shipped_index(material_index)
            if index is not None:
                originals[index] = character

    for position, block in enumerate(unit.blocks):
        start, stop = unit.spans[position]
        try:
            match block:
                case TextBlock():
                    replaced = replaced_within(block.material)
                    if not replaced:
                        continue
                    if len(unit.blocks) == 1:
                        name(replaced, map_text_block(block, unit.cmds))
                    else:
                        name(replaced, map_text_block(block, unit.cmds, start=start, stop=stop))
                case CodeBlock():
                    replaced = replaced_within(tuple(chain.from_iterable(block.lines)))
                    if replaced:
                        name(replaced, map_code_block(block, base=start))
                case TableBlock():
                    cells = {
                        id(cell): found
                        for row in (block.header, *block.rows)
                        for cell in row
                        if (found := replaced_within(cell.material))
                    }
                    if not cells:
                        continue
                    for cell, mapped in map_table(block, unit.box, base=start):
                        if id(cell) in cells:
                            name(cells[id(cell)], mapped)
                case _:
                    pass
        except SpanMapError:
            continue
    return originals


def _list_depth(block: Block, quoted: int, list_indent: Scaled, quote_indent: Scaled) -> int | None:
    """
    How many lists a block is inside, or None for a block that is in no list.

    Derived from what the block already carries. `advtext.markdown` sets
    `left_indent` to the style's own indent plus one `Theme.list_indent` for
    each open list and one `Theme.quote_indent` for each open quote, all
    integers, so with the quotes taken off what is left is a whole number of
    list indents. (A rule is the exception in having no style indent added.)
    `quoted` is the block's quote depth: its own for a text block, the
    caller's best reading for any other, which does not carry one.

    Zero is a block that is a list item by its marker or its kind and has no
    list's indent -- one built by hand with `advtext.markdown.text_block`,
    which infers no indent, or any block when `list_indent` is zero. It is an
    item of a list one deep in everything but name, and is treated as one.

    Not measured: a theme whose `quote_indent` is a whole multiple of its
    `list_indent`. There a fence one quote deeper than `quoted` has the indent
    of a fence in a list and is read as one. The built theme's are 1.5 and
    1.9 em.
    """
    own = 0 if isinstance(block, RuleBlock) else block.style.left_indent
    inside = block.left_indent - own - quoted * quote_indent
    levels, rest = divmod(inside, list_indent) if list_indent > 0 else (0, 0)
    if rest == 0 and levels > 0:
        return levels
    if isinstance(block, TextBlock) and (block.marker or block.kind in _LIST_ITEMS):
        return 0
    return None


def _numbered(block: TextBlock) -> bool:
    """
    Whether a list item's marker is a number rather than a bullet.
    """
    return any(
        isinstance(node, CharNode) and chr(node.codepoint).isdigit() for node in block.marker
    )


def _after_hard_breaks(unit: Unit, block: TextBlock, start: int, stop: int) -> list[int]:
    """
    The local index of the first item after each forced break in a text block.

    A forced break is a penalty at or below `EJECT_PENALTY` that is not the
    material's last node. Most blocks have none and return at once. One that
    cannot be mapped (`SpanMapError`) returns nothing, and its hard breaks then
    copy as spaces -- wrong, and far better than an exception out of a copy.
    """
    material = block.material
    forced = [
        index
        for index, node in enumerate(material[:-1])
        if isinstance(node, Penalty) and node.value <= EJECT_PENALTY
    ]
    if not forced:
        return []
    try:
        if len(unit.blocks) == 1:
            mapped = map_text_block(block, unit.cmds)
        else:
            mapped = map_text_block(block, unit.cmds, start=start, stop=stop)
    except SpanMapError:
        return []
    after: list[int] = []
    for index in forced:
        for later in range(index + 1, len(material)):
            local = mapped.shipped[later]
            if local is not None:
                after.append(mapped.base + local)
                break
    return after


def moved(cmds: Iterable[DrawCmd], dy: Scaled, di: int) -> tuple[DrawCmd, ...]:
    """
    `cmds`, moved down by `dy` and with every reading-order index raised by `di`.

    Constructed field by field rather than with `dataclasses.replace`, because
    this is the one loop here that runs per command and `replace` measures
    about three times slower on these four types. The price is that this
    function knows every field of every command, so a field added to one of
    them in `advtext.shipout` would be silently dropped here.
    `tests/test_units_layout.py::test_moving_a_command_knows_every_field_it_has`
    pins the field lists so that it is a failure instead.
    """
    out: list[DrawCmd] = []
    for cmd in cmds:
        match cmd:
            case Glyph():
                out.append(
                    Glyph(
                        font=cmd.font,
                        codepoint=cmd.codepoint,
                        x=cmd.x,
                        y=cmd.y + dy,
                        index=cmd.index + di,
                    )
                )
            case SetGlue():
                # An `Atom` is a `SetGlue` with no field of its own, and has
                # to come out the other side still an atom.
                out.append(
                    (Atom if isinstance(cmd, Atom) else SetGlue)(
                        x=cmd.x,
                        y=cmd.y + dy,
                        width=cmd.width,
                        natural=cmd.natural,
                        height=cmd.height,
                        depth=cmd.depth,
                        index=cmd.index + di,
                    )
                )
            case Line():
                out.append(
                    Line(
                        x=cmd.x,
                        y=cmd.y + dy,
                        width=cmd.width,
                        height=cmd.height,
                        depth=cmd.depth,
                        start=cmd.start + di,
                        end=cmd.end + di,
                    )
                )
            case RuleRect():
                out.append(RuleRect(x=cmd.x, y=cmd.y + dy, width=cmd.width, height=cmd.height))
            case _ as unreachable:
                assert_never(unreachable)
    return tuple(out)


class _Placement:
    """
    One unit's commands at one offset and index base, derived on demand and kept.

    The only mutable thing in this module besides the cache, and the reason is
    the module docstring's: moving a unit costs about what shipping it did, so
    it is done when first asked for and never for a unit nobody looks at. A
    plain class with two memo slots rather than a frozen dataclass because that
    is what it is.

    Shared between successive `UnitLayout`s by `layout_units`, which is what
    makes "nothing below the edit moved" cost nothing.
    """

    __slots__ = (
        "_atoms",
        "_cmds",
        "_model",
        "_originals",
        "_separators",
        "_slice",
        "base",
        "source",
        "y",
    )

    def __init__(self, source: tuple[DrawCmd, ...], y: Scaled, base: int) -> None:
        self.source = source
        self.y = y
        self.base = base
        self._cmds: tuple[DrawCmd, ...] | None = None
        self._model: SelectionModel | None = None
        self._separators: dict[int, str] | None = None
        self._atoms: dict[int, str] | None = None
        self._originals: dict[int, str] | None = None
        # The last partial view of a long unit: the local viewport it was cut
        # to, and the commands moved for it.
        self._slice: tuple[Scaled, Scaled, tuple[DrawCmd, ...]] | None = None

    def matches(self, source: tuple[DrawCmd, ...], y: Scaled, base: int) -> bool:
        """
        Whether this is the placement of exactly these commands at exactly this spot.

        The commands are compared by identity. A `Unit` re-found by value keeps
        the tuple it shipped, so identity is both sufficient and free.
        """
        return self.source is source and self.y == y and self.base == base

    @property
    def cmds(self) -> tuple[DrawCmd, ...]:
        if self._cmds is None:
            if self.y == 0 and self.base == 0:
                self._cmds = self.source
            else:
                self._cmds = moved(self.source, self.y, self.base)
        return self._cmds

    @property
    def model(self) -> SelectionModel:
        if self._model is None:
            self._model = SelectionModel.from_commands(self.cmds)
        return self._model


@dataclass(frozen=True, slots=True)
class PlacedUnit:
    """
    A unit in a document: which blocks it is, where it sits, and which indices it owns.

    This is the public per-block structure. Colour by role reads `blocks` and
    draws `cmds`; hit testing reads `y`, `height` and `block_at`; source copy
    maps `block_range` to source lines; a streaming view replaces the last one
    and leaves the rest alone.

    `cmds` and `model` are in **document** coordinates and are derived on first
    use (see the module docstring). `unit.cmds` is the same material in the
    unit's own coordinates and costs nothing.
    """

    unit: Unit
    block_start: int
    """Index into the document's `blocks` of the first block this unit sets."""
    y: Scaled
    """The unit's top edge, in document scaled points."""
    base: int
    """The reading-order index of the unit's first item."""
    _placement: _Placement = field(repr=False, compare=False)
    part: int | None = None
    """
    Which piece of its block this unit is, from zero; `None` when it is the whole block.

    Set only for a code block or a table laid out in pieces (the module
    docstring). Every piece of one block has that block's `block_start`.
    """
    skipped: int = 0
    """
    How much of the block comes before this piece, in the units its decoration counts in.

    For a piece of a code block, the block's material indices before the
    piece's first: a host's colour spans count in those. For a piece of a
    table, the links in the rows before it: a link is known by its number
    among its block's links. Zero for a whole block.
    """

    @property
    def blocks(self) -> tuple[Block, ...]:
        """
        The blocks this unit sets. More than one only for a block quote.

        For a piece of a code block this is a `CodeBlock` of the piece's own
        lines, and for a piece of a table a `SizedTable` of its own rows;
        neither is an element of the document's `blocks`, and `block_start`
        says which of those it is a piece of.
        """
        return self.unit.blocks

    @property
    def block_range(self) -> range:
        """
        Which of the document's blocks these are, as indices into `Document.blocks`.
        """
        return range(self.block_start, self.block_start + len(self.unit.blocks))

    @property
    def height(self) -> Scaled:
        """
        The unit's full vertical extent.
        """
        return self.unit.height

    @property
    def bottom(self) -> Scaled:
        """
        One past the unit's last row: `y + height`. The gap below it is not included.
        """
        return self.y + self.unit.height

    @property
    def index_range(self) -> range:
        """
        The reading-order indices this unit owns: `[base, base + count)`.
        """
        return range(self.base, self.base + self.unit.count)

    @property
    def cmds(self) -> tuple[DrawCmd, ...]:
        """
        The unit's shipped commands in document coordinates.
        """
        return self._placement.cmds

    @property
    def model(self) -> SelectionModel:
        """
        A selection index over this unit alone, in document coordinates and indices.
        """
        return self._placement.model

    @property
    def separators(self) -> Mapping[int, str]:
        """
        What a copy writes inside this unit where a break is content, by document index.

        Everything the module docstring lists except the separator *before*
        the unit, which depends on its neighbour and is `UnitLayout`'s. Built
        on first use and kept with the placement.
        """
        placement = self._placement
        if placement._separators is None:
            local = _separators_within(self.unit)
            placement._separators = {self.base + index: text for index, text in local.items()}
        return placement._separators

    @property
    def atoms(self) -> Mapping[int, str]:
        """
        What each inline formula in this unit copies as, by document index.

        Empty for a unit with no formula in it, which is nearly all of them.
        Built on first use and kept with the placement, as `separators` is.
        """
        placement = self._placement
        if placement._atoms is None:
            local = _atoms_within(self.unit)
            placement._atoms = {self.base + index: text for index, text in local.items()}
        return placement._atoms

    @property
    def originals(self) -> Mapping[int, str]:
        """
        What each replaced character in this unit copies as, by document index.

        Empty unless a character no face has was set here as U+FFFD
        (`advtext.markdown.ReplacedChar`). Built on first use and kept with
        the placement, as `atoms` is.
        """
        placement = self._placement
        if placement._originals is None:
            local = _originals_within(self.unit)
            placement._originals = {self.base + index: text for index, text in local.items()}
        return placement._originals

    def block_at(self, y: Scaled) -> int | None:
        """
        Which document block a document-space `y` falls in, or `None` for none.

        `None` between two paragraphs of a quote as well as outside the unit:
        the space between blocks belongs to neither, and a caller that wants
        the nearest one can ask for it knowing that it is asking.
        """
        local = y - self.y
        for offset, (top, bottom) in enumerate(self.unit.extents):
            if top <= local < bottom:
                return self.block_start + offset
        return None

    def indices_of(self, block: int) -> range:
        """
        The reading-order indices document block `block` owns, in document indices.

        `block` is an index into `Document.blocks` and must be one of
        `block_range`. For a unit of one block this is `index_range`; for a
        quote it is that paragraph's share of it. For a piece of a code block
        it is the piece's share: `UnitLayout.indices_of_block` has the block's.
        """
        start, end = self.unit.spans[block - self.block_start]
        return range(self.base + start, self.base + end)

    def visible(self, viewport: Viewport) -> tuple[DrawCmd, ...]:
        """
        This unit's commands that meet `viewport`, in document coordinates.

        Three answers, and the first two look at no command: none of the unit's
        ink meets the viewport; all of it does, so every command is kept; or the
        viewport's edge runs through the unit and each command is tested the way
        `CommandIndex.visible` tests it.
        """
        top, bottom = viewport.top - self.y, viewport.bottom - self.y
        ink_top, ink_bottom, last_top, first_bottom = self.unit.ink
        if not (ink_bottom > top and ink_top < bottom):
            return ()
        if first_bottom > top and last_top < bottom:
            return self.cmds
        index = self.unit.index
        placement = self._placement
        if placement._cmds is None and len(self.unit.cmds) > MOVE_WHOLE_BELOW:
            # A long unit of which a window shows a slice: move the slice, not
            # the unit. Moving all of it costs about what shipping it did, and
            # a six-hundred-line code block still being written would pay
            # that every frame for the few dozen lines on screen.
            if placement._slice is not None and placement._slice[:2] == (top, bottom):
                return placement._slice[2]
            kept = [
                cmd
                for cmd, cmd_top, cmd_bottom in zip(
                    self.unit.cmds, index.tops, index.bottoms, strict=True
                )
                if cmd_bottom > top and cmd_top < bottom
            ]
            sliced = moved(kept, self.y, self.base)
            placement._slice = (top, bottom, sliced)
            return sliced
        return tuple(
            cmd
            for cmd, cmd_top, cmd_bottom in zip(self.cmds, index.tops, index.bottoms, strict=True)
            if cmd_bottom > top and cmd_top < bottom
        )


@dataclass(frozen=True, eq=False)
class UnitModel(FragmentQueries):
    """
    `SelectionModel`'s queries over a stack of units, touching only the units a query needs.

    Every rule -- midpoint splitting, word classes, wrap-versus-hard-break
    serialisation -- is inherited from `advtext.selection.FragmentQueries`
    unchanged. What is here is the two lookups, and both begin by bisecting to
    a unit.

    Not slotted, so that `fragments` can be a `cached_property`: it is the
    whole document's fragments, it exists for callers that want the flat view
    (`scripts/mouse_probe.py`, tests), and no query in this class reads it.
    """

    placed: tuple[PlacedUnit, ...]
    length: int
    list_indent: Scaled = 0
    """`Theme.list_indent` of the theme the blocks were built with; zero reads no nesting."""
    quote_indent: Scaled = 0
    """`Theme.quote_indent` of the same theme."""

    @cached_property
    def _ends(self) -> tuple[int, ...]:
        return tuple(unit.base + unit.unit.count for unit in self.placed)

    @cached_property
    def _reach(self) -> tuple[tuple[Scaled, ...], tuple[Scaled, ...]]:
        return _reach(self.placed)

    @cached_property
    def fragments(self) -> tuple[Fragment, ...]:
        """
        Every fragment in the document, in reading order. Builds every unit's index.
        """
        return tuple(chain.from_iterable(unit.model.fragments for unit in self.placed))

    @cached_property
    def _leads(self) -> tuple[tuple[tuple[str | None, str], ...], ...]:
        """
        For each unit, for each of its blocks: the separator before it, and its indent.

        **The rule for a list.** Every block inside one outermost list -- an
        item at any depth, a later paragraph of an item, a fence, a quote or a
        table inside one -- begins a new line: `LINE_BREAK`, never a blank
        line. Everything else gets `BLOCK_BREAK`, the first block of a list
        included. The indent is two spaces for each list the block is inside
        beyond the first; it is part of the separator before the block, and
        `separators_within` puts it after every newline inside the block too.

        A list ends at the first block that is in no list, at a block quoted
        less deeply than the list began, and at an outermost item of the
        other sort or the other quote depth: a bulleted list followed by a
        numbered one is two lists, as it was before nesting was read. The
        sort is read off the marker (`_numbered`), not the kind, because
        inside a quote every text block's kind is `QUOTE`.

        **How deep a block is, is derived, not stored** (`_list_depth`): a
        block's `left_indent` is a sum of the theme's `list_indent` and
        `quote_indent`, and the theme's two lengths are passed in. A block
        that is not text carries no quote depth, so it is taken to be quoted
        as deeply as the list that is open, and never opens one.

        A later piece of a code block begins with a line of that block, and
        gets what `_separators_within` gives a line of a whole one: a newline
        if anything of the block comes before it in the reading order, and
        **nothing** if not -- blank lines carry no index, so a piece that
        follows only blank lines begins at the block's own first index, where
        the separator before the block already is and must stay.
        """
        leads: list[tuple[tuple[str | None, str], ...]] = []
        # The outermost open list: how deeply it is quoted, and whether it is
        # numbered -- None until one of its own items has said.
        top: tuple[int, bool | None] | None = None
        opened = 0
        indent = ""
        for unit in self.placed:
            if unit.part:
                leads.append(((LINE_BREAK + indent if unit.base > opened else None, indent),))
                continue
            opened = unit.base
            entry: list[tuple[str | None, str]] = []
            for block in unit.blocks:
                text = block if isinstance(block, TextBlock) else None
                quoted = text.quote_depth if text else top[0] if top else 0
                depth = _list_depth(block, quoted, self.list_indent, self.quote_indent)
                if depth is None or (text is None and top is None):
                    top = None
                    indent = ""
                    entry.append((BLOCK_BREAK, indent))
                    continue
                sort = _numbered(text) if text and text.marker and depth <= 1 else None
                fresh = (
                    top is None
                    or quoted < top[0]
                    or (sort is not None and (quoted != top[0] or top[1] not in (None, sort)))
                )
                if fresh or top is None:
                    top = (quoted, sort)
                elif top[1] is None:
                    top = (top[0], sort)
                indent = LIST_INDENT * max(depth - 1, 0)
                entry.append(((BLOCK_BREAK if fresh else LINE_BREAK) + indent, indent))
            leads.append(tuple(entry))
        return tuple(leads)

    def separators_within(self, start: Boundary, end: Boundary) -> dict[int, str]:
        """
        The content separators of every unit a range touches, as one mapping.

        What `copy_text` passes to `text`. Public for a caller that wants the
        structure without the text -- a host building its own serialisation.

        A unit's own separators (`PlacedUnit.separators`) know nothing of
        lists, which are a matter of what came before the unit. So two things
        are rewritten here from `_leads`: the blank line a quote puts before
        each of its later blocks becomes that block's own separator, and a
        newline inside a block that is indented is followed by the indent.

        **A hosted block is written into the separator after it.** An
        `advtext.ui.HostBlock` holds no item, so no index is its own, and a
        mapping keyed by index has one place for it: in front of the next
        item, between that block's own separator and the next block's. So a
        selection that has text before the widget and text after it copies
        `Hosted.text` in between, on its own lines, and one that stops at
        either edge of the widget does not, because `text` writes a separator
        only between two pieces of selected text. Nothing else about the
        widget is in the reading order.

        That leaves out a hosted block with no text on one side of it at all
        -- the first or the last thing in a document -- which no separator
        can carry. `copy_text` adds those itself (`edge_hosts`).
        """
        merged: dict[int, str] = {}
        # What the hosted blocks passed over since the last unit with any
        # text in it copy as, each behind its own separator.
        hosted = ""
        for position in range(bisect_left(self._ends, start), len(self.placed)):
            unit = self.placed[position]
            if unit.base > end:
                break
            leads = self._leads[position]
            lead, indent = leads[0]
            stand_in = unit.unit.blocks[0]
            if isinstance(stand_in, HostBlock):
                body = _hosted_text(stand_in)
                if body:
                    if indent:
                        body = body.replace(LINE_BREAK, LINE_BREAK + indent)
                    hosted += (lead if position and lead is not None else "") + body
                continue
            if position and lead is not None:
                merged[unit.base] = hosted + lead
            if unit.unit.count:
                hosted = ""
            if len(leads) == 1 and not indent:
                merged.update(unit.separators)
                continue
            starts = [unit.base + first for first, _ in unit.unit.spans]
            for index, text in unit.separators.items():
                block = bisect_right(starts, index) - 1
                lead, indent = leads[block]
                if block and index == starts[block] and lead is not None:
                    text = lead + text.removeprefix(BLOCK_BREAK)
                elif indent:
                    text = text.replace(LINE_BREAK, LINE_BREAK + indent)
                merged[index] = text
        return merged

    def copy_text(self, selection: Selection, *, everything: bool = False) -> str:
        """
        The selected text as the document's structure says it reads: what a copy should give.

        `text` with the separators only this layer knows -- blank lines
        between blocks, newlines between code lines and table rows, tabs
        between cells (the module docstring has the list). `text` itself is
        inherited unchanged and, given no separators, still treats every break
        as a wrap, exactly as the flat `SelectionModel` over the same commands
        does; that is what the equality tests against the flat model compare,
        and what a caller with separators of its own starts from.

        **Hosted blocks at an edge of the document are copied only when the
        caller says `everything=True`.** A hosted block that has no text
        before it, or none after it, cannot be "between two pieces of
        selected text" (`separators_within`), and a reply that ends in a
        diff is the usual shape of one: a copy of the whole document used to
        leave the diff out, and a document that was only a diff copied as
        nothing (review 2, item 2). With `everything`, the text of the
        leading hosted blocks comes before the selection's own and that of
        the trailing ones after, each behind the separator its place in the
        document gives it. **Nothing is inferred from the range** (it was,
        from `covers_everything`, until review 3, item 4): a hosted block
        has no index, so the boundary after the last character is also the
        boundary after the diff below it, and a selection of the one
        sentence above a diff runs from the first boundary to the last
        without anybody having pointed at the diff. The caller knows
        whether its user asked for everything -- `BareView` does, from the
        select-all gesture -- and this does not.
        """
        body = self.text(
            selection,
            separators=self.separators_within(selection.start, selection.end),
            atoms=self.atoms_within(selection.start, selection.end),
            originals=self.originals_within(selection.start, selection.end),
        )
        if not everything:
            return body
        leading, trailing = self.edge_hosts()
        if not leading and not trailing:
            return body
        out = ""
        first_text = leading[-1] + 1 if leading else 0
        pieces: list[tuple[int, str]] = [
            (position, self._host_text(position)) for position in leading
        ]
        pieces.append((first_text, body))
        pieces += [(position, self._host_text(position)) for position in trailing]
        for position, text in pieces:
            if not text:
                continue
            if out:
                lead = self._leads[position][0][0] if position < len(self._leads) else None
                out += BLOCK_BREAK if lead is None else lead
            out += text
        return out

    def covers_everything(self, selection: Selection) -> bool:
        """
        Whether a selection runs from the document's first boundary to its
        last. A fact about the range, and no longer what decides whether the
        hosted blocks at the edges are copied: see `copy_text`.
        """
        return selection.start <= 0 and selection.end >= self.length

    def edge_hosts(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """
        The hosted units with no text before them, and those with none after,
        as positions in `placed`. A document with no text at all has every
        hosted unit in the first and none in the second. Units that hold
        nothing and are not hosted (a rule) are passed over.
        """
        placed = self.placed
        leading: list[int] = []
        first = 0
        while first < len(placed) and not placed[first].unit.count:
            if isinstance(placed[first].unit.blocks[0], HostBlock):
                leading.append(first)
            first += 1
        trailing: list[int] = []
        last = len(placed) - 1
        while last >= first and not placed[last].unit.count:
            if isinstance(placed[last].unit.blocks[0], HostBlock):
                trailing.append(last)
            last -= 1
        return tuple(leading), tuple(reversed(trailing))

    def _host_text(self, position: int) -> str:
        """What the hosted unit at `position` copies as, indented as its place asks."""
        stand_in = self.placed[position].unit.blocks[0]
        assert isinstance(stand_in, HostBlock)
        body = _hosted_text(stand_in)
        indent = self._leads[position][0][1]
        return body.replace(LINE_BREAK, LINE_BREAK + indent) if body and indent else body

    def atoms_within(self, start: Boundary, end: Boundary) -> dict[int, str]:
        """
        What every inline formula in a range copies as: its source, dollars included.

        What `copy_text` passes to `text` as `atoms`, and public for the same
        reason `separators_within` is.
        """
        merged: dict[int, str] = {}
        for position in range(bisect_left(self._ends, start), len(self.placed)):
            unit = self.placed[position]
            if unit.base > end:
                break
            merged.update(unit.atoms)
        return merged

    def originals_within(self, start: Boundary, end: Boundary) -> dict[int, str]:
        """
        What every replaced character in a range copies as: the character written.

        A character no face of the theme has is drawn as U+FFFD and must not
        be copied as one. What `copy_text` passes to `text` as `originals`,
        and public for the same reason `atoms_within` is.
        """
        merged: dict[int, str] = {}
        for position in range(bisect_left(self._ends, start), len(self.placed)):
            unit = self.placed[position]
            if unit.base > end:
                break
            merged.update(unit.originals)
        return merged

    def fragments_within(self, start: Boundary, end: Boundary) -> Iterator[Fragment]:
        """
        The fragments of the units whose index range meets `[start, end]`.

        Closed at both ends, which is what the base class asks for: a unit
        ending exactly at `start` may hold the blank line `text()` wants to
        know about.
        """
        for position in range(bisect_left(self._ends, start), len(self.placed)):
            unit = self.placed[position]
            if unit.base > end:
                break
            if unit.unit.lines:
                yield from unit.model.fragments

    def fragment_at(self, point: Point) -> Fragment | None:
        """
        The line a point belongs to: the one whose band contains it, else the nearest.

        The same answer the flat model gives, found without building it, by
        handing `advtext.selection.fragment_nearest` only the fragments that
        can win. A line whose band contains `point.y` is in a unit whose ink
        spans it; failing that the nearest line is in one of those units or in
        the first pointable unit on either side of them -- which is where
        "units are stacked top to bottom" is assumed.
        """
        placed = self.placed
        low, high = _spanning(self._reach, point.y)
        # "Pointable" is "has a fragment", which is narrower than "shipped a
        # line": a thematic break ships a line that holds a rule and nothing
        # to point at, and stepping onto it would hide the paragraph beyond.
        above = next((p for p in range(low - 1, -1, -1) if _fragments_of(placed[p])), None)
        below = next((p for p in range(high, len(placed)) if _fragments_of(placed[p])), None)
        near = [above] if above is not None else []
        near.extend(range(low, high))
        if below is not None:
            near.append(below)
        return fragment_nearest(
            (fragment for position in near for fragment in _fragments_of(placed[position])),
            point,
        )


def _hosted_text(block: HostBlock) -> str:
    """
    What a selection across a hosted block copies for it: `Hosted.text`, less its last newline.

    Asked when a copy is made and not when the layout is, so a widget whose
    text grows without its height changing is not laid out again for it.
    """
    host = block.host
    if host is None:
        return ""
    return str(host.text).removesuffix(LINE_BREAK)


def _fragments_of(unit: PlacedUnit) -> tuple[Fragment, ...]:
    """
    A unit's fragments, without building an index for a unit that has no lines.
    """
    return unit.model.fragments if unit.unit.lines else ()


def _reach(placed: tuple[PlacedUnit, ...]) -> tuple[tuple[Scaled, ...], tuple[Scaled, ...]]:
    """
    Two monotone arrays that bound where a y can possibly be inside a unit's ink.

    `bottoms[i]` is the lowest ink bottom among units `0..i` taken as a running
    **maximum**, and `tops[i]` the highest ink top among units `i..` taken as a
    running **minimum**. Both are monotone whatever the geometry, so both can
    be bisected, and a unit outside the slice they give provably has no ink at
    that y. That is what lets culling be exact without assuming the units are
    in order: the arrays narrow the search and each unit inside it is still
    tested against its own ink.
    """
    bottoms = tuple(accumulate((unit.y + unit.unit.ink[1] for unit in placed), max))
    tops = tuple(accumulate((unit.y + unit.unit.ink[0] for unit in reversed(placed)), min))
    return bottoms, tops[::-1]


def _spanning(
    reach: tuple[tuple[Scaled, ...], tuple[Scaled, ...]], top: Scaled, bottom: Scaled | None = None
) -> tuple[int, int]:
    """
    The slice of units that can have ink in `[top, bottom)`; for a point, `bottom` is omitted.

    Everything before `low` has all its ink at or above `top`; everything from
    `high` on has all its ink at or below `bottom`.
    """
    bottoms, tops = reach
    low = bisect_right(bottoms, top)
    high = bisect_right(tops, top) if bottom is None else bisect_left(tops, bottom)
    return low, max(low, high)


@dataclass(frozen=True, slots=True)
class LayoutStats:
    """
    What building one `UnitLayout` did: which units were built, which found, and the time.

    Stated by the library because a host cannot work it out from outside. A
    unit found *by value* -- the same blocks parsed again -- is re-homed as a
    new `Unit` object around the commands it already had, so comparing unit
    objects between two layouts reports a rebuild that did not happen; and the
    cache keeps more than one pass, so comparing with the previous layout
    alone bills every return to a width. Two demo pages measured both.

    These are the counts of the one `layout_units` call that made the layout.
    A layout a view answers from its cache has the stats of when it was
    built; `advtext.ui.bare_view.BareView.layout_stats` is the last build's.

    The times are single wall-clock samples and include whatever else the
    machine was doing. They say which unit was expensive; they are not a
    benchmark.
    """

    units: int = 0
    """How many units the layout has."""
    built: tuple[int, ...] = ()
    """Positions in `UnitLayout.placed` of the units built for this layout, ascending."""
    blocks_broken: int = 0
    """
    How many blocks were set again (line-broken, or a table or code block composed).

    Every block of every built unit, less the blocks of a multi-block unit
    whose boxes the `LayoutCache` still had: one paragraph of a quote changing
    rebuilds the quote's unit and breaks that paragraph alone.
    """
    seconds: float = 0.0
    """The whole `layout_units` call, in seconds."""
    build_seconds: float = 0.0
    """The part of `seconds` spent composing and shipping the built units."""

    @property
    def reused(self) -> int:
        """
        How many units were found, by identity or by value, and not built.
        """
        return self.units - len(self.built)

    def was_built(self, position: int) -> bool:
        """
        Whether the unit at `position` in `UnitLayout.placed` was built for this layout.
        """
        at = bisect_left(self.built, position)
        return at < len(self.built) and self.built[at] == position


@dataclass(frozen=True, eq=False)
class UnitLayout:
    """
    A document laid out to one width, as a stack of placed units.

    What `DocumentView` used to keep as a box, a `CommandIndex` and a
    `SelectionModel` for the whole document. It answers the same questions --
    `cmds`, `visible`, `model`, `height` -- and none of them is stored: each is
    assembled from the units, and the ones that would touch every unit
    (`cmds`, `box`, `model.fragments`) are computed only if asked for.

    Compared by identity, like the `Layout` it replaces was in practice: two
    layouts are "the same" when one was returned from the cache.
    """

    width: Scaled
    """The measure every unit was broken to."""
    placed: tuple[PlacedUnit, ...]
    """The units, top to bottom, in document order."""
    height: Scaled
    """The document's full extent: the bottom of its last unit."""
    length: int
    """How many reading-order items the document has."""
    list_indent: Scaled = 0
    """The theme's `list_indent`: what `model` reads a block's list depth from."""
    quote_indent: Scaled = 0
    """The theme's `quote_indent`, for the same."""
    stats: LayoutStats = LayoutStats()
    """What building this layout did: units built and found, blocks broken, the time."""

    @cached_property
    def model(self) -> UnitModel:
        """
        The selection queries over the whole document. Cheap: it indexes nothing yet.
        """
        return UnitModel(
            placed=self.placed,
            length=self.length,
            list_indent=self.list_indent,
            quote_indent=self.quote_indent,
        )

    @cached_property
    def _reach(self) -> tuple[tuple[Scaled, ...], tuple[Scaled, ...]]:
        return _reach(self.placed)

    @cached_property
    def _tops(self) -> tuple[Scaled, ...]:
        return tuple(unit.y for unit in self.placed)

    @cached_property
    def _block_starts(self) -> tuple[int, ...]:
        return tuple(unit.block_start for unit in self.placed)

    @cached_property
    def cmds(self) -> tuple[DrawCmd, ...]:
        """
        Every command in the document, in document coordinates.

        Equal, command for command, to shipping `compose`'s box at
        `Point(0, box.height)`. **It moves every unit**, so it is for a caller
        that genuinely wants the whole list -- an SVG export, a test, a probe.
        The draw path uses `visible`, which moves only what is on screen.
        """
        return tuple(chain.from_iterable(unit.cmds for unit in self.placed))

    @cached_property
    def box(self) -> Box:
        """
        The whole document as one vbox, for a caller that wants a box.

        Assembled from the units' boxes and the gaps between them. It ships to
        the same commands as `advtext.ui.compose`'s box and has the same width,
        height and depth, but it is **not** the same tree: each unit is a vbox
        of its own inside it, where `compose` returns one flat vertical list.
        """
        nodes: list[Node] = []
        pen: Scaled = 0
        for unit in self.placed:
            if unit.y != pen:
                nodes.append(Kern(width=unit.y - pen))
            nodes.append(unit.unit.box)
            pen = unit.bottom
        return vpack(nodes).box

    def visible(self, viewport: Viewport) -> tuple[DrawCmd, ...]:
        """
        The commands whose extent meets `viewport`, in reading order.

        Exactly `CommandIndex.of(self.cmds).visible(viewport)`, and
        `tests/test_units_layout.py` asserts that over a sweep of viewports.
        The difference is what it costs: the old path compared every command
        in the document on every frame, and this compares only the commands of
        a unit the viewport's edge passes through.
        """
        return tuple(chain.from_iterable(cmds for _, cmds in self.visible_units(viewport)))

    def visible_units(self, viewport: Viewport) -> Iterator[tuple[PlacedUnit, tuple[DrawCmd, ...]]]:
        """
        Each unit that meets `viewport`, with the commands of it that do.

        `visible` with the seams left in: the same commands in the same order,
        but still grouped by the unit they belong to, which is what a caller
        needs to treat one block differently from the next -- drawing each in
        its own ink, say. A unit with nothing on screen is not yielded.
        """
        low, high = _spanning(self._reach, viewport.top, viewport.bottom)
        for unit in self.placed[low:high]:
            cmds = unit.visible(viewport)
            if cmds:
                yield unit, cmds

    def visible_rects(self, selection: Selection, viewport: Viewport) -> list[Rect]:
        """
        The highlight rectangles of `selection` that meet `viewport`, and only those.

        `model.rects(selection)` builds a rectangle for every line the
        selection covers and a caller then throws away the ones off screen:
        measured on twenty copies of `demo/sample.md` with everything
        selected, 1460 rectangles a frame for 24 on screen, 5 ms a frame and
        217 ms the first time, because building them indexes every unit. This
        asks only the units the viewport meets, so the cost is the window's
        and a unit nobody has scrolled to is never indexed for a highlight.

        **It asks no unit for its commands.** Which units meet the viewport is
        read from their ink extents, the test `PlacedUnit.visible` makes
        before it looks at a command. Going through `visible_units` instead
        cut each unit to this viewport, and a long unit keeps exactly one
        such cut (`_Placement._slice`): `BareView.pointed` asks this about a
        band one scaled point tall, so a host calling `under_mouse()` every
        frame overwrote the window's slice and the next draw moved it again
        -- 871 commands a frame on a six-hundred-line code block where an
        unchanged frame moves none (review 5, item 2;
        `tests/test_bare_view.py`). A unit whose ink meets the viewport but
        none of whose commands does is asked for its rectangles where it
        used to be skipped; they are filtered by the viewport just below,
        so the answer is the same.
        """
        if selection.is_empty:
            return []
        rects: list[Rect] = []
        low, high = _spanning(self._reach, viewport.top, viewport.bottom)
        for unit in self.placed[low:high]:
            ink_top, ink_bottom, _, _ = unit.unit.ink
            if not (ink_bottom > viewport.top - unit.y and ink_top < viewport.bottom - unit.y):
                continue
            if not unit.unit.lines or unit.base >= selection.end:
                continue
            if unit.base + unit.unit.count <= selection.start:
                continue
            rects.extend(
                rect
                for rect in unit.model.rects(selection)
                if viewport.covers(rect.y, rect.y + rect.height)
            )
        return rects

    def unit_at(self, point: Point) -> PlacedUnit | None:
        """
        The unit whose box contains `point.y`, or `None` in a gap or outside the document.

        By `y` alone, on purpose: a point in the margin beside a paragraph is
        beside *that paragraph*, and a caller opening a context menu there
        wants it. A caller that cares about `x` has the unit's `cmds`.

        This is the box's extent and not the ink's, and assumes the units are
        stacked top to bottom, which `layout_units` guarantees for
        non-negative block spacing.
        """
        # The *last* unit whose top is at or above the point. A zero-height
        # unit shares its top with the unit after it, and of the two it is the
        # later one that can contain anything.
        position = bisect_right(self._tops, point.y) - 1
        if position < 0:
            return None
        unit = self.placed[position]
        return unit if unit.y <= point.y < unit.bottom else None

    def block_at(self, point: Point) -> int | None:
        """
        The index into `Document.blocks` of the block under a point, or `None`.

        The point-to-block hit test. Inside a block quote it resolves to the
        paragraph, not the quote. A code block laid out in pieces is one
        block here: every y from its first line's top to its last line's
        bottom names it, including any interline glue between two pieces,
        which belongs to no unit.
        """
        position = bisect_right(self._tops, point.y) - 1
        if position < 0:
            return None
        unit = self.placed[position]
        if unit.y <= point.y < unit.bottom:
            return unit.block_at(point.y)
        below = position + 1
        if below < len(self.placed) and self.placed[below].part and point.y >= unit.bottom:
            return unit.block_start
        return None

    def unit_of(self, boundary: Boundary) -> PlacedUnit | None:
        """
        The unit that owns reading-order item `boundary`, or `None` past the end.
        """
        if not 0 <= boundary < self.length:
            return None
        position = bisect_right(self.model._ends, boundary)
        return self.placed[position]

    def unit_of_block(self, block: int) -> PlacedUnit | None:
        """
        The unit that sets `Document.blocks[block]`, or `None` if there is no such block.

        The *first* such unit, for a code block laid out in pieces:
        `units_of_block` has them all.
        """
        for unit in self.placed:
            if block in unit.block_range:
                return unit
        return None

    def units_of_block(self, block: int) -> tuple[PlacedUnit, ...]:
        """
        Every unit that sets part of `Document.blocks[block]`, top to bottom.

        One unit, except for a code block laid out in pieces. Empty if there
        is no such block.
        """
        # Units are in block order and a unit's blocks end where the next
        # one's begin, so the units of a block are found by bisection: every
        # piece of a block has its `block_start`, and a block inside a quote
        # run has the run's, which is the last one at or before it.
        starts = self._block_starts
        high = bisect_right(starts, block)
        if high == 0 or block not in self.placed[high - 1].block_range:
            return ()
        low = bisect_left(starts, starts[high - 1], 0, high)
        return self.placed[low:high]

    def position_of(self, unit: PlacedUnit) -> int | None:
        """
        Where `unit` is in `placed`, or `None` if it is not one of this layout's units.

        By identity, found by bisection on its top edge: a host that was
        handed a `PlacedUnit` (`unit_at`, `units_of_block`) and wants its
        entry in `stats`, or its neighbours, does not have to search for it.
        """
        tops = self._tops
        position = bisect_left(tops, unit.y)
        while position < len(tops) and tops[position] == unit.y:
            if self.placed[position] is unit:
                return position
            position += 1
        return None

    def indices_of_block(self, block: int) -> range:
        """
        The reading-order indices `Document.blocks[block]` owns, however many units set it.

        `PlacedUnit.indices_of` for a block that is one unit or part of one;
        for a code block in pieces, from its first piece's first index to its
        last piece's last. An empty range at zero if there is no such block.
        """
        units = self.units_of_block(block)
        if not units:
            return range(0)
        return range(units[0].indices_of(block).start, units[-1].indices_of(block).stop)


def _glyphs(unit: PlacedUnit) -> list[Glyph]:
    """
    A unit's glyphs in reading order, in its own (local) indices.
    """
    return [cmd for cmd in unit.unit.cmds if isinstance(cmd, Glyph)]


def _same_text(old: list[Glyph], new: list[Glyph], count: int) -> bool:
    """
    Whether two units set the same first `count` characters.

    Codepoints only: a word that became bold when its markup closed is the
    same text in another face, and a selection of it is still a selection of it.
    """
    if len(old) < count or len(new) < count:
        return False
    return all(old[k].codepoint == new[k].codepoint for k in range(count))


def carry_selection(selection: Selection, old: UnitLayout, new: UnitLayout) -> Selection | None:
    """
    `selection`, made against `old`, as the same text in `new` -- or `None` if it is not there.

    **A selection is boundaries in the reading order, and the reading order is
    not stable.** Every line carries glue that takes an index -- a
    `\\rightskip`, a `\\parfillskip`, a cell's `\\hss` -- so a paragraph
    that re-breaks into a different number of lines has a different number of
    items, and every index after it moves. Measured on `demo/sample.md`: 5286
    items at 500 px and 5295 at 400 px, and the same pair of integers selects
    different words. So a selection kept as integers across a relayout can
    come to mean other text without anything having gone wrong.

    The rule this implements: **after a relayout a selection denotes the same
    text or it is gone.** What is stable is the glyphs -- nothing here
    hyphenates, so a block sets the same characters in the same order however
    it breaks -- so each end of the selection is restated as "the n-th glyph
    of the unit that begins at this block", and looked up again in `new`.

    It carries only if the text is demonstrably the same:

    - the selection covers at least one glyph;
    - the unit at each end exists in `new`, beginning at the same block, and
      sets the same characters up to the selection's edge in it (the whole
      unit, for the first of several);
    - every unit strictly between them is in `new` at the same block with the
      same characters.

    "The unit that begins at this block" is, for a code block laid out in
    pieces, the piece with the same number: a piece holds the same lines for
    as long as the block has them.

    Anything else is `None` and the caller decides -- clear it, or keep the
    part that did carry (`advtext.ui.stream_view` clamps to the settled text).
    A unit shipped once and merely moved is recognised by identity and costs
    nothing to check; a re-broken one costs a walk of its glyphs.
    """
    start = max(0, min(selection.start, old.length))
    end = max(0, min(selection.end, old.length))
    if start >= end:
        return selection
    first, last = old.unit_of(start), old.unit_of(end - 1)
    if first is None or last is None:
        return None
    # A piece of a code block is "the unit that begins at this block" only
    # together with which piece it is.
    by_block = {(unit.block_start, unit.part or 0): unit for unit in new.placed}

    def twin(unit: PlacedUnit) -> PlacedUnit | None:
        found = by_block.get((unit.block_start, unit.part or 0))
        if found is None or len(found.blocks) != len(unit.blocks):
            return None
        return found

    new_first, new_last = twin(first), twin(last)
    if new_first is None or new_last is None:
        return None

    first_glyphs, last_glyphs = _glyphs(first), _glyphs(last)
    # Glyphs of the first unit before the selection, and of the last unit
    # through its end.
    skipped = sum(1 for glyph in first_glyphs if first.base + glyph.index < start)
    taken = sum(1 for glyph in last_glyphs if last.base + glyph.index < end)
    if first is last and taken <= skipped:
        return None

    positions = [(unit.block_start, unit.part or 0) for unit in old.placed]
    low = positions.index((first.block_start, first.part or 0))
    high = positions.index((last.block_start, last.part or 0))
    for unit in old.placed[low : high + 1]:
        other = twin(unit)
        if other is None:
            return None
        if other.unit.cmds is unit.unit.cmds:
            continue
        mine = first_glyphs if unit is first else last_glyphs if unit is last else _glyphs(unit)
        theirs = _glyphs(other)
        needed = taken if unit is last else len(mine)
        if unit is not last and len(theirs) != len(mine):
            return None
        if not _same_text(mine, theirs, needed):
            return None

    new_first_glyphs = _glyphs(new_first)
    new_last_glyphs = new_first_glyphs if new_last is new_first else _glyphs(new_last)
    if skipped >= len(new_first_glyphs):
        # The selection began after the first unit's last glyph: on fill.
        if first is last:
            return None
        new_start = new_first.base + new_first.unit.count
    else:
        new_start = new_first.base + new_first_glyphs[skipped].index
    if taken == 0:
        new_end = new_last.base
    else:
        new_end = new_last.base + new_last_glyphs[taken - 1].index + 1
    if new_start >= new_end:
        return None
    return Selection(new_start, new_end)


def carry_caret(at: Boundary, old: UnitLayout, new: UnitLayout) -> Boundary | None:
    """
    A caret at boundary `at` of `old`, as the same place in `new` -- or `None` if it is gone.

    `carry_selection` cannot do this: a caret selects nothing, and it hands an
    empty selection back as it was given. A caret is the fixed end of a drag
    (`advtext.ui.bare_view`), and it is carried by the same rule a selection
    is -- **the same text or nothing** -- in the first of these that applies:

    1. **A unit beside the caret was not re-shipped** (`new` holds the very
       commands, by identity): the caret keeps its offset in that unit,
       wherever the unit's indices now begin. This is every press on a block
       that did not change, including the ones with glue on both sides -- the
       white right of a paragraph's last line, a list's gutter, a table
       cell's fill -- and it reads no glyph. The unit holding the item before
       the caret is asked first and then the one holding the item after; they
       differ only for a caret between two units.
    2. **The item before the caret is a glyph**, and the unit still sets the
       same characters up to and including it: the caret stays after that
       glyph. Else **the item after it is a glyph**, likewise: it stays
       before that one.
    3. **The caret is on fill in a unit that was set again**: it is restated
       as "after this many of the unit's glyphs" and stays after the last
       glyph before it, if the unit still sets the same characters that far;
       failing that (it was before the unit's first glyph), before the first
       glyph after it.

    Until review 5 only the second existed, and its snippet A measured what
    that cost: 198 of 500 press positions on four blocks that had not changed
    lost their drag at the next relayout, which in a stream is the next
    frame text arrives on.

    "The same characters" is `carry_selection`'s test: codepoints, and only
    as far as the caret, so a caret in a paragraph that is still being
    written is carried while words arrive after it. A unit's twin is the unit
    of `new` that begins at the same block (and is the same piece of it).

    Under the third rule a caret that sat after a line's fill comes back in
    front of it: the same place in the text, on the other side of glue. A
    selection dragged down from there can begin with the space the line
    break stood for where it did not before. Nothing measures that; it is
    the price of saying where a caret is by a glyph.
    """
    at = max(0, min(at, old.length))
    by_block = {(unit.block_start, unit.part or 0): unit for unit in new.placed}

    def twin(unit: PlacedUnit) -> PlacedUnit | None:
        found = by_block.get((unit.block_start, unit.part or 0))
        if found is None or len(found.blocks) != len(unit.blocks):
            return None
        return found

    before = old.unit_of(at - 1) if at > 0 else None
    after = old.unit_of(at)
    beside = [unit for unit in (before, after) if unit is not None]
    if before is after:
        beside = beside[:1]
    pairs = [(unit, other) for unit in beside if (other := twin(unit)) is not None]
    for unit, other in pairs:
        if other.unit.cmds is unit.unit.cmds:
            return other.base + (at - unit.base)

    def restated(want: Callable[[PlacedUnit, list[Glyph], int], int | None]) -> Boundary | None:
        # `want` names a glyph of the old unit by its position among the
        # unit's glyphs; the answer is a boundary beside that glyph in `new`.
        for unit, other in pairs:
            mine = _glyphs(unit)
            count = sum(1 for glyph in mine if unit.base + glyph.index < at)
            chosen = want(unit, mine, count)
            if chosen is None:
                continue
            theirs = _glyphs(other)
            if not _same_text(mine, theirs, chosen + 1):
                continue
            # After the glyph if it comes before the caret, before it if not.
            return other.base + theirs[chosen].index + (1 if chosen < count else 0)
        return None

    def adjacent_before(unit: PlacedUnit, mine: list[Glyph], count: int) -> int | None:
        return count - 1 if count and unit.base + mine[count - 1].index == at - 1 else None

    def adjacent_after(unit: PlacedUnit, mine: list[Glyph], count: int) -> int | None:
        return count if count < len(mine) and unit.base + mine[count].index == at else None

    def last_before(unit: PlacedUnit, mine: list[Glyph], count: int) -> int | None:
        return count - 1 if count else None

    def first_after(unit: PlacedUnit, mine: list[Glyph], count: int) -> int | None:
        return count if count < len(mine) else None

    for want in (adjacent_before, adjacent_after, last_before, first_after):
        found = restated(want)
        if found is not None:
            return found
    return None


_Shape = tuple[tuple[object, ...], ...]
"""
A cheap stand-in for a run's value: enough to tell most different runs apart at a glance.
"""


def _shape(run: tuple[Block, ...]) -> _Shape:
    """
    What kind of blocks a run holds, how big each is, and a few of its nodes.

    **Never the whole value.** A unit used to be stored under the run itself,
    which hashes every node of every block: three or four such hashes per
    layout for a block that had changed and could not hit, and for a
    six-hundred-line code fence still being written that was more than
    shipping it. A shape costs the same for a block of any size. Two runs of
    one shape are then compared for real, and that comparison stops at the
    first thing that differs -- for a block that grew, its length.
    """
    shapes: list[tuple[object, ...]] = []
    for block in run:
        match block:
            case TextBlock():
                material = block.material
                shapes.append((TextBlock, len(material), material[:3], material[-3:]))
            case CodeBlock():
                lines = block.lines
                shapes.append(
                    (
                        CodeBlock,
                        len(lines),
                        len(lines[-1]) if lines else 0,
                        lines[0][:3] if lines else (),
                    )
                )
            case TableBlock():
                shapes.append((TableBlock, len(block.rows), len(block.header)))
            case _:
                shapes.append((type(block),))
    return tuple(shapes)


@dataclass(slots=True)
class _Shelf:
    """
    One pass key's units: every one by shape and value, and the last pass's by identity.

    `by_shape` is the store. A run is looked up under its `_shape` and then
    compared, by value, with the few units that share it, which is what makes
    the cache unable to go stale: a run that is equal is the same layout,
    whoever built the objects. `by_id` is how a pass over an unchanged
    document avoids even that. It maps `id(run[0])` to the unit, and it is
    sound because the unit holds the run: an object whose `id` is in this dict
    is alive, so the `id` cannot have been reused.

    `by_id` is rebuilt every pass and so doubles as "what the last pass used".
    """

    by_shape: dict[_Shape, list[Unit]] = field(default_factory=dict)
    by_id: dict[int, Unit] = field(default_factory=dict)

    def __len__(self) -> int:
        return sum(len(units) for units in self.by_shape.values())

    def find(self, run: tuple[Block, ...]) -> Unit | None:
        """
        The stored unit whose run equals `run`, or `None`.
        """
        for unit in self.by_shape.get(_shape(run), ()):
            if unit.blocks == run:
                return unit
        return None

    def store(self, unit: Unit, replacing: Unit | None = None) -> None:
        """
        Keep `unit` under its run's shape, in place of `replacing` if that is given.
        """
        units = self.by_shape.setdefault(_shape(unit.blocks), [])
        if replacing is not None:
            for position, held in enumerate(units):
                if held is replacing:
                    units[position] = unit
                    return
        units.append(unit)

    def retire(self) -> dict[int, Unit]:
        """
        Drop what the last pass did not use, and hand its identity map to the next.

        A walk of the stored units and nothing else: no block is hashed or
        compared to find out that it was not used.
        """
        used = self.by_id
        if len(used) != len(self):
            live = {id(unit) for unit in used.values()}
            self.by_shape = {
                shape: kept
                for shape, units in self.by_shape.items()
                if (kept := [unit for unit in units if id(unit) in live])
            }
        self.by_id = {}
        return used


@dataclass(frozen=True, slots=True)
class _Piece:
    """
    One piece of a code block or a table: its lines or rows as a block of their own.
    """

    block: CodeBlock | SizedTable
    material: int
    """
    What the next piece's `skipped` grows by: the nodes in a code piece's lines, the links
    in a table piece's cells.
    """


def _pieces(block: CodeBlock, size: int, before: tuple[_Piece, ...]) -> tuple[_Piece, ...]:
    """
    `block` as pieces of `size` lines, reusing each of `before` that still holds the same lines.

    **The same object, where the lines are the same**, and that is the point:
    `UnitCache` finds a unit by the identity of its block before it looks at
    anything else, so a piece handed back as the object it was last time costs
    one dict lookup, and a piece rebuilt costs a shape, a search and a
    comparison. With sixty pieces of similar code the second is what a layout
    would mostly be doing.

    "The same lines" is decided by value, so this cannot hand back a piece
    for lines that differ. It is cheap because `advtext.stream` keeps the
    line tuples it has already converted: equal lines are the same objects,
    and comparing a tuple of them compares pointers.
    """
    lines = block.lines
    out: list[_Piece] = []
    for number, first in enumerate(range(0, len(lines), size)):
        chunk = lines[first : first + size]
        held = before[number] if number < len(before) else None
        if (
            held is not None
            and isinstance(held.block, CodeBlock)
            and held.block.lines == chunk
            and (held.block.style is block.style or held.block.style == block.style)
            and held.block.language == block.language
            and held.block.left_indent == block.left_indent
        ):
            out.append(held)
        else:
            out.append(_Piece(replace(block, lines=chunk), sum(map(len, chunk))))
    return tuple(out)


def _table_pieces(
    block: TableBlock, widths: tuple[Scaled, ...], size: int, before: tuple[_Piece, ...]
) -> tuple[_Piece, ...] | None:
    """
    `block` as pieces of `size` rows at the column widths `widths`, reusing what it can of `before`.

    The first piece is the header and the first `size` rows; each later one
    is rows alone. Every piece is a `SizedTable` at the whole table's widths,
    which is what makes it set its rows as the whole table would.

    A piece of `before` is handed back, the same object, when it holds the
    same rows at the same widths with the same header, alignments, style and
    indent -- decided by value, as `_pieces` decides, and cheap for the same
    reason: `advtext.stream` keeps the rows it has converted, so equal rows
    are the same objects and comparing a tuple of them compares pointers.

    `None` if the table cannot be cut: a row (or the header) with another
    number of cells than there are widths, which a `SizedTable` refuses, or a
    width under one scaled point, likewise. markdown-it pads and trims every
    row to its header, so neither happens to a table that was parsed; a table
    built by hand can do both, and is laid out whole.
    """
    columns = len(widths)
    if not columns or any(type(width) is not int or width < 1 for width in widths):
        return None
    rows = block.rows
    out: list[_Piece] = []
    for number, first in enumerate(range(0, len(rows), size)):
        chunk = rows[first : first + size]
        header = () if number else block.header
        held = before[number] if number < len(before) else None
        if (
            held is not None
            and isinstance(held.block, SizedTable)
            and held.block.rows == chunk
            and held.block.column_widths == widths
            and held.block.header == header
            and held.block.aligns == block.aligns
            and (held.block.style is block.style or held.block.style == block.style)
            and held.block.left_indent == block.left_indent
        ):
            out.append(held)
            continue
        if any(len(row) != columns for row in chunk) or (header and len(header) != columns):
            return None
        piece = SizedTable(
            style=block.style,
            header=header,
            rows=chunk,
            aligns=block.aligns,
            left_indent=block.left_indent,
            column_widths=widths,
        )
        links = sum(len(cell.links) for row in (header, *chunk) for cell in row)
        out.append(_Piece(piece, links))
    return tuple(out)


def _piece_gap(
    above: Unit, below: Unit, skip: InterlineSkip, known: dict[tuple[Scaled, Scaled], Scaled]
) -> Scaled:
    """
    The space between two consecutive pieces of one block: §679's interline glue.

    What `advtext.pack.append_to_vlist` puts between the last line of `above`
    and the first of `below` when they are lines of one vertical list -- the
    same function, asked the same question. It reads the depth of the one and
    the height of the other and nothing else, which is why a block can be cut
    between any two lines and stacked back exactly. The glue is at its natural
    width for the reason `advtext.ui._extent` gives: nothing packs these lists
    to a target.

    `known` remembers the answer by the two numbers it depends on, for one
    block's pieces. Every line of a code block is set on one strut, so there
    are one or two distinct pairs in a block of any length, and asking the
    rule afresh for each of a hundred boundaries -- it builds a glue each
    time -- was the largest per-piece cost of a layout when profiled.
    """
    last, first = above.box.contents[-1], below.box.contents[0]
    assert isinstance(last, Box) and isinstance(first, Box), "a piece is a stack of lines or rows"
    # A table row whose cells wrapped is resumed from its last line's depth,
    # not its own (`advtext.ui.prev_depth_after`); for anything else, and so
    # for every line of code, the two are one number.
    depth = prev_depth_after(last)
    pair = (depth, first.height)
    gap = known.get(pair)
    if gap is None:
        glue = interline_glue(depth, first, skip)
        gap = 0 if glue is None else glue.spec.width
        known[pair] = gap
    return gap


@dataclass(slots=True)
class UnitCache:
    """
    Shipped units, kept between two layouts of a document.

    The analogue of `advtext.ui.LayoutCache` one stage later, and it sits *in
    front* of it: a run found here is not looked up there, because a unit
    already holds the box. A layout of an unchanged document therefore composes
    nothing, ships nothing, indexes nothing and hashes nothing -- and a block
    that *did* change is never hashed either (`_shape`), so finding out that
    it missed costs the same for a block of any size.

    `misses` is the number of units shipped and indexed over the cache's life,
    and `hits` the number answered without doing either. Those two are the
    figures to read before believing any claim about what an edit costs.

    Keyed by the same pass key as `LayoutCache` and bounded the same way:
    `resident_passes` distinct (width, context) keys are kept, least recently
    used evicted, and within one key a unit survives for as long as every pass
    at that key uses it.

    **A unit is keyed by the width, so a resize misses on every unit.** Read
    `LayoutCache` before trying to change that.
    """

    resident_passes: int = 2
    shelves: dict[Hashable, _Shelf] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    # What the most recent miss took to compose and ship, in seconds: how
    # `layout_units` learns a build's time without timing every lookup.
    last_build_seconds: float = 0.0
    # The pieces the last layout cut each long code block into, by the block's
    # number and the piece size. Not per width: a piece is lines, and the
    # same lines at any measure.
    pieces: dict[tuple[int, int], tuple[_Piece, ...]] = field(default_factory=dict)
    # The column widths the last layout worked out for each long table that
    # did not state its own, by block number: the table (held, so that it is
    # the identity that is compared), the pass key, and the widths. A settled
    # table is the same object from layout to layout and is measured once.
    columns: dict[int, tuple[TableBlock, Hashable, tuple[Scaled, ...]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.resident_passes < 1:
            raise ValueError(f"resident_passes must be at least 1, got {self.resident_passes}")

    def stats(self) -> CacheStats:
        """
        Lifetime hits and misses, and how many units are resident.
        """
        return CacheStats(
            hits=self.hits,
            misses=self.misses,
            entries=sum(len(shelf) for shelf in self.shelves.values()),
        )

    def clear(self) -> None:
        """
        Drop everything, including the counters.
        """
        self.shelves = {}
        self.pieces = {}
        self.columns = {}
        self.hits = 0
        self.misses = 0

    def _begin(self, key: Hashable) -> tuple[_Shelf, dict[int, Unit]]:
        shelf = self.shelves.pop(key, None)
        if shelf is None:
            shelf = _Shelf()
        previous = shelf.retire()
        self.shelves[key] = shelf
        while len(self.shelves) > self.resident_passes:
            del self.shelves[next(iter(self.shelves))]
        return shelf, previous

    def _unit(
        self,
        shelf: _Shelf,
        previous: dict[int, Unit],
        run: tuple[Block, ...],
        composer: RunComposer,
    ) -> Unit:
        """
        The unit for `run`: by identity if it can be, by value if not, else built.
        """
        found = previous.get(id(run[0]))
        if (
            found is not None
            and len(found.blocks) == len(run)
            and all(mine is theirs for mine, theirs in zip(found.blocks, run, strict=True))
        ):
            self.hits += 1
            shelf.by_id[id(run[0])] = found
            return found

        held = shelf.find(run)
        if held is not None:
            # Equal blocks, different objects: a re-parsed document. Re-home
            # the unit on the new objects so the next pass finds it by
            # identity, and so the old document is not kept alive by it.
            self.hits += 1
            found = replace(held, blocks=run)
            shelf.store(found, replacing=held)
        else:
            self.misses += 1
            began = perf_counter()
            found = ship_unit(composer.compose(run), composer.measure)
            self.last_build_seconds = perf_counter() - began
            found = replace(found, build_seconds=self.last_build_seconds)
            shelf.store(found)
        shelf.by_id[id(run[0])] = found
        return found


def layout_units(
    blocks: tuple[Block, ...],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams | None = None,
    *,
    units: UnitCache | None = None,
    cache: LayoutCache | None = None,
    previous: UnitLayout | None = None,
    code_lines: int = 0,
    table_rows: int = 0,
) -> UnitLayout:
    """
    Lay a document out to a width as a stack of units, reusing whatever has not changed.

    The per-unit counterpart of `advtext.ui.compose` followed by `ship`,
    `CommandIndex.of` and `SelectionModel.from_commands`, and the result is
    interchangeable with theirs: same commands, same indices, same answers.

    Three things are reused and each is optional:

    - `units` keeps shipped units. With it, a run that has not changed is not
      composed, shipped or indexed again. Without it every call ships
      everything, which is correct and is what a one-shot caller wants.
    - `cache` is the `LayoutCache` underneath, consulted only for a run that
      `units` could not answer. It earns its place when a unit is rebuilt but
      a block inside it need not be re-broken.
    - `previous` is the last `UnitLayout` for this document. A unit that is
      the same and sits at the same offset and index base takes its placement
      -- the moved commands and the selection index, if they were ever built
      -- from there.

    Cost when nothing changed: a loop over the units and no hashing. Cost when
    one block changed: that block's composition, ship and index, plus -- only
    if its height or item count changed -- the lazy re-placement of the units
    below it as they are looked at.

    `code_lines`, when positive, lays a code block of more than that many
    lines out as pieces of that many, each a unit (the module docstring has
    what that buys and what it changes for a caller that walks `placed`).
    The commands, indices and every query's answer are the whole block's.
    Zero, the default, never cuts a block.

    `table_rows` is the same for a table of more than that many rows: pieces
    of that many rows, each set to the column widths of the whole table.
    """
    began = perf_counter()
    composer = RunComposer(theme=theme, width=width, measure=measure, params=params, cache=cache)
    store = UnitCache() if units is None else units
    found_before = cache.hits if cache is not None else 0
    built: list[int] = []
    built_blocks = 0
    build_seconds = 0.0

    def fetch(run: tuple[Block, ...]) -> Unit:
        """
        The unit for `run`, noting it as built if the cache had to build it.

        Called immediately before `place`, so the position noted is the one
        the unit is about to take.
        """
        nonlocal built_blocks, build_seconds
        misses = store.misses
        unit = store._unit(shelf, known, run, composer)
        if store.misses != misses:
            built.append(len(placed))
            built_blocks += len(run)
            build_seconds += store.last_build_seconds
        return unit

    shelf, known = store._begin(composer.key)
    earlier = previous.placed if previous is not None else ()
    cut_before: dict[tuple[int, int], tuple[_Piece, ...]] = store.pieces
    cut_now: dict[tuple[int, int], tuple[_Piece, ...]] = {}
    sized_before = store.columns
    sized_now: dict[int, tuple[TableBlock, Hashable, tuple[Scaled, ...]]] = {}

    placed: list[PlacedUnit] = []
    y: Scaled = 0
    base = 0

    def place(unit: Unit, start: int, part: int | None, skipped: int) -> None:
        nonlocal y, base
        position = len(placed)
        placement: _Placement | None = None
        if position < len(earlier):
            before = earlier[position]
            if before._placement.matches(unit.cmds, y, base):
                placement = before._placement
                if (
                    before.unit is unit
                    and before.block_start == start
                    and before.part == part
                    and before.skipped == skipped
                ):
                    # The same unit in the same place saying the same things:
                    # the same (frozen) object will do. A long code block in
                    # pieces is a hundred of these per layout.
                    placed.append(before)
                    y += unit.height
                    base += unit.count
                    return
        if placement is None:
            placement = _Placement(unit.cmds, y, base)
        placed.append(
            PlacedUnit(
                unit=unit,
                block_start=start,
                y=y,
                base=base,
                _placement=placement,
                part=part,
                skipped=skipped,
            )
        )
        y += unit.height
        base += unit.count

    start = 0
    above: tuple[Block, ...] | None = None
    for run in block_runs(blocks):
        if above is not None:
            y += run_gap(above, run)
        block = run[0]
        pieces: tuple[_Piece, ...] | None = None
        key = (start, 0)
        if code_lines > 0 and isinstance(block, CodeBlock) and len(block.lines) > code_lines:
            key = (start, code_lines)
            pieces = _pieces(block, code_lines, cut_before.get(key, ()))
        elif table_rows > 0 and isinstance(block, TableBlock) and len(block.rows) > table_rows:
            key = (start, table_rows)
            if isinstance(block, SizedTable) and block.column_widths:
                widths = block.column_widths
            else:
                # The whole table's widths at this measure, worked out once
                # for as long as it is this table and this pass key.
                sized = sized_before.get(start)
                if sized is not None and sized[0] is block and sized[1] == composer.key:
                    widths = sized[2]
                else:
                    widths = table_columns(block, theme, width, measure, composer.context.params)
                sized_now[start] = (block, composer.key, widths)
            pieces = _table_pieces(block, widths, table_rows, cut_before.get(key, ()))
        if pieces is not None:
            cut_now[key] = pieces
            skipped = 0
            upper: Unit | None = None
            gaps: dict[tuple[Scaled, Scaled], Scaled] = {}
            for part, piece in enumerate(pieces):
                unit = fetch((piece.block,))
                if upper is not None:
                    y += _piece_gap(upper, unit, block.style.interline, gaps)
                place(unit, start, part, skipped)
                skipped += piece.material
                upper = unit
        else:
            place(fetch(run), start, None, 0)
        start += len(run)
        above = run
    store.pieces = cut_now
    store.columns = sized_now
    return UnitLayout(
        width=width,
        placed=tuple(placed),
        height=y,
        length=base,
        list_indent=theme.list_indent,
        quote_indent=theme.quote_indent,
        stats=LayoutStats(
            units=len(placed),
            built=tuple(built),
            blocks_broken=built_blocks - ((cache.hits - found_before) if cache is not None else 0),
            seconds=perf_counter() - began,
            build_seconds=build_seconds,
        ),
    )

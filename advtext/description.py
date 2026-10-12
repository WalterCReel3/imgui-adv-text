"""
A document as imtypeset takes one: the description types, in one place, with nothing behind them.

**Experimental** (branch `experimental/imtypeset-adoption`). Of the facade:
`Description` and `BlockDescription`; the rest is reached from here.

Two things make a description. `advtext.typesetter.Converter` walks blocks
that hold node material, and `advtext.typeset_markdown.MarkdownConverter`
reads blocks that hold text and runs already. Both give the tuples defined
here, and a view and `advtext.typeset_find` read them. A description is one
thing whoever made it, and `tests/test_description.py` holds the two modules'
names to be these very objects.

**A table is a block** (`KIND_TABLE`): `BlockDescription.rows` are its rows of
`CellDescription`s (text and runs, the runs indexing the CELL's text) and
`BlockDescription.columns` one `ColumnDescription` a column (alignment, and a
width or a share when the host states one). `BLOCK_TABLE_HEADER` says the
first row is a header. The block's `text` is `table_text` of the cells, which
is what the library makes of the rows itself, what a copy of the whole table
gives, and what a position in the block indexes; `cell_spans` says where each
cell lies in it.

**This module imports the standard library and nothing else**: not the old
layout core, not `advtext.style`, not imtypeset. That is why the two tables
an enum would key are keyed by NAME here (`FACE_ROLES`, `ALIGNS`), and
`face_role` / `align_code` take a member of whatever enum and read its name:
`Face` lives in `advtext.primitives` and `Align` in `advtext.theme`, and a
module that every part of the new layer imports must not decide where those
live or load what they sit beside.

The tuples are in the field order of `imtypeset.Block` and `imtypeset.Run`,
with the header's enumerators (`../imtypeset/include/imtypeset.h`) as the
integers below, so a description is built, compared and searched without the
library, and `imtypeset.Document` takes the tuples as they are.
`tests/test_typeset.py` compares each integer with the loaded package's own
when there is one.

Offsets are indices into a block's `str` (codepoints). The Python package
converts to the library's byte offsets itself.
"""

from __future__ import annotations

import collections
from collections.abc import Iterable, Sequence
from typing import Any, Final, NamedTuple

__all__ = [
    "ALIGNS",
    "BLOCK_FIXED_LINE_HEIGHT",
    "BLOCK_HARD_BREAKS",
    "BLOCK_MATH",
    "BLOCK_TABLE_HEADER",
    "BLOCK_TABLE_HELD",
    "BlockDescription",
    "CellDescription",
    "ColumnDescription",
    "Description",
    "FACE_DEFAULT",
    "FACE_ROLES",
    "KIND_CODE",
    "KIND_HEADING",
    "KIND_HOST",
    "KIND_LIST_ITEM",
    "KIND_PARAGRAPH",
    "KIND_RULE",
    "KIND_TABLE",
    "LinkRow",
    "MISFIT_BLOCK",
    "RUN_DISPLAY_FORMULA",
    "RUN_FORMULA",
    "RUN_NO_BREAK",
    "RunDescription",
    "StyleDescription",
    "UNKNOWN_BLOCK_EXTENT_PX",
    "align_code",
    "cell_spans",
    "column_aligns",
    "face_role",
    "table_text",
    "with_tags",
]

# ---------------------------------------------------------------------------
# The header's enumerators, as integers
# ---------------------------------------------------------------------------

KIND_PARAGRAPH, KIND_HEADING, KIND_LIST_ITEM, KIND_CODE, KIND_RULE, KIND_HOST = 0, 1, 2, 3, 4, 5
KIND_TABLE: Final = 6

FACE_DEFAULT: Final = 0

FACE_ROLES: Final[dict[str, int]] = {
    "PROSE": 1,
    "PROSE_BOLD": 2,
    "PROSE_ITALIC": 3,
    "PROSE_BOLD_ITALIC": 4,
    "CODE": 5,
    "CODE_BOLD": 6,
    "MATH": 7,
}
"""
Which imtypeset role each advtext face is registered under, by the NAME of the `Face` member.

Both are roles *a font file is registered under*, so the table is by name,
and a theme's own mapping of document roles onto faces
(`advtext.style.Faces`) has already been applied by the time a face is
looked up here. `advtext.typesetter.FACE_ROLE` is this table keyed by the
members themselves.
"""

ALIGNS: Final[dict[str, int]] = {"JUSTIFY": 0, "LEFT": 1, "CENTER": 2, "RIGHT": 3}
"""
imtypeset's alignment for each `advtext.style.Align`, by the NAME of the member.
"""

RUN_NO_BREAK, RUN_FORMULA, RUN_DISPLAY_FORMULA = 1, 2, 4
# `ImTypesetBlockFlags_`. Bit 1 names nothing in the header.
BLOCK_HARD_BREAKS: Final = 1 << 0
BLOCK_MATH: Final = 1 << 2
BLOCK_FIXED_LINE_HEIGHT: Final = 1 << 3
BLOCK_TABLE_HEADER: Final = 1 << 4
"""A table's first row is a header: the library draws its rule under that row."""
BLOCK_TABLE_HELD: Final = 1 << 5
"""
A table's columns are held while it grows: each as wide as the widest cell it has had.

What a view over a stream sets on a table still being written
(`advtext.ui.typeset_stream_view`); `../imtypeset/include/imtypeset.h`, "A
TABLE THAT GROWS", has the rule.
"""


def face_role(face: Any) -> int:
    """
    The imtypeset role of a `Face` member (anything with that member's `name`).

    Raises `KeyError` for a name that is not one of the seven.
    """
    return FACE_ROLES[face.name]


def align_code(align: Any) -> int:
    """
    imtypeset's alignment for an `Align` member (anything with that member's `name`).
    """
    return ALIGNS[align.name]


def column_aligns(aligns: Iterable[Any]) -> tuple[int, ...]:
    """
    A table's column alignments (`advtext.markdown_rules.ColumnAlign`) as `ALIGNS`' integers.

    By name again: `LEFT` and `CENTER` are themselves, and anything else is
    `RIGHT`, which is the one other alignment a column has. Never justified.
    """
    return tuple(
        ALIGNS[align.name] if align.name in ("LEFT", "CENTER") else ALIGNS["RIGHT"]
        for align in aligns
    )


# The height of the Host block that stands for a block neither converter knows.
UNKNOWN_BLOCK_EXTENT_PX: Final = 16.0

MISFIT_BLOCK: Final = "block type {name}"
"""
`MISFIT_BLOCK.format(name=type(block).__name__)`: a block a converter does not know.
"""


# ---------------------------------------------------------------------------
# The tuples
# ---------------------------------------------------------------------------


class RunDescription(NamedTuple):
    """
    A stretch of a block's text set differently: `imtypeset.Run`, field for field.

    `start` and `end` index the block's `str`. Within a block the runs are in
    ascending order and do not overlap, which the library requires.
    """

    start: int
    end: int
    face: int = FACE_DEFAULT
    scale: float = 0.0
    color: int = 0
    flags: int = 0
    tag: int = 0


class CellDescription(NamedTuple):
    """
    One table cell: `imtypeset.Cell`, field for field. `runs` index the cell's own `text`.

    The runs carry what a paragraph's do: faces, formulas, and a link's tag
    and ink. The library sets a newline in a cell as white space: a cell has
    no hard breaks.
    """

    text: str = ""
    runs: tuple[RunDescription, ...] = ()


class ColumnDescription(NamedTuple):
    """
    One column of a table: `imtypeset.TableColumn`, field for field.

    `align` is one of `ALIGNS`' integers (left, centre or right; the library
    reads justified as left). `width` is the column's width in pixels, cell
    padding included, and is read only when EVERY column of the table states
    one above zero: the table is then exactly those widths. Otherwise `share`
    is read, when every column states one: its part of the width, in any
    unit. With neither the library fits the table.
    """

    align: int = 1
    width: float = 0.0
    share: float = 0.0


class BlockDescription(NamedTuple):
    """
    One block: `imtypeset.Block`, field for field, so the library takes it as it is.

    `rows` and `columns` are a `KIND_TABLE` block's alone (the module
    docstring); its `text` is `table_text` of the rows and its `runs` are
    empty, each cell having its own.
    """

    kind: int = KIND_PARAGRAPH
    text: str = ""
    runs: tuple[RunDescription, ...] = ()
    marker: str = ""
    style: int = 0
    left_indent: float = 0.0
    quote_depth: int = 0
    container: int = 0
    item: int = 0
    extent: float = 0.0
    flags: int = 0
    level: int = 0
    rows: tuple[tuple[CellDescription, ...], ...] = ()
    columns: tuple[ColumnDescription, ...] = ()


class StyleDescription(NamedTuple):
    """
    A block's style: the fields of `imtypeset.BlockStyle` a converter sets, by their names there.

    `Scale` is a multiple of the document style's size
    (`advtext.typesetter.base_style`), lengths are pixels.
    `advtext.typesetter.block_styles` makes the library's struct from it.
    """

    Face: int = FACE_DEFAULT
    Scale: float = 0.0
    LineHeight: float = 0.0
    Align: int = 0
    FirstLineIndent: float = 0.0
    SpaceAbove: float = 0.0
    SpaceBelow: float = 0.0
    Color: int = 0
    MarkerGap: float = 0.0


class LinkRow(NamedTuple):
    """
    One link: which block, which range of that block's `str`, and where it goes.

    `tag` is what `imtypeset.Document.hit_test` answers for a point on it, and
    the converter's `link_target(tag)` is `target`.
    """

    block: int
    start: int
    end: int
    tag: int
    target: str


class Description(NamedTuple):
    """
    What a converter's `describe` makes of a run of blocks.

    `blocks[i]` describes the i-th block given, one for one, and `texts[i]` is
    its text, which is what a position indexes: empty for a rule, and for a
    table `table_text` of its cells.
    `styles` is a copy of the converter's WHOLE style table so far, not this
    call's share: a block's `style` indexes it. A first `set_blocks` is given
    all of it and a `replace_blocks` only what the call added. `tables` are
    the document indices of the table blocks. `links` hold a table's links
    too, as ranges of the block's text. `misfits` counts what a description
    could not say and `kinds` what was walked.
    """

    blocks: list[BlockDescription]
    styles: list[StyleDescription]
    links: list[LinkRow]
    tables: list[int]
    texts: list[str]
    misfits: collections.Counter[str]
    kinds: collections.Counter[str]


# ---------------------------------------------------------------------------
# What both converters do the same way
# ---------------------------------------------------------------------------


def table_text(rows: Iterable[Iterable[str]]) -> str:
    """
    A table's text: a tab between the cells of a row, a newline between rows.

    `rows` are the cells' texts, the header row first when there is one; a
    row with no cell is a row of one empty cell. This is the string
    `imtypeset.Document` makes of `Block.rows` (its `_table_rows`), so it is
    what a table block's positions index and what a copy of the whole table
    gives. `tests/test_typeset.py` holds it against the library's own.
    """
    return "\n".join("\t".join(row) for row in rows)


def cell_spans(rows: Iterable[Sequence[CellDescription]]) -> list[list[tuple[int, int]]]:
    """
    Where each cell of a table lies in `table_text` of it: `[start, end)` per cell, per row.

    A cell's run or a match at offset `n` of the cell's text is at `start +
    n` of the block's. A row with no cell has one empty span, as the library
    gives it one empty cell.
    """
    out: list[list[tuple[int, int]]] = []
    at = 0
    for number, row in enumerate(rows):
        if number:
            at += 1
        spans: list[tuple[int, int]] = []
        for column, cell in enumerate(row):
            if column:
                at += 1
            spans.append((at, at + len(cell.text)))
            at += len(cell.text)
        out.append(spans or [(at, at)])
    return out


def with_tags(
    runs: Sequence[RunDescription], tagged: Sequence[tuple[int, int, int]], color: int
) -> list[RunDescription]:
    """
    `runs` with each link's tag laid over them, still ascending and not overlapping.

    `tagged` is `(start, end, tag)` per link. The library takes one run for a
    character, so a link over bold text is not two runs: the styled run is
    cut at the link's edges and the pieces inside carry the tag. Where two
    links claim a character (markdown does not nest them) the earlier one
    keeps it. A link's edge never falls inside a formula as either converter
    writes one; were it to, the formula's run is kept whole and takes the tag
    of the link at its start.

    `color` is given to tagged text only, and not to a formula, whose ink is
    the builder's.
    """
    links: list[tuple[int, int, int]] = []
    reached = 0
    for start, end, tag in sorted(tagged):
        start = max(start, reached)
        if end > start:
            links.append((start, end, tag))
            reached = end

    def tag_at(position: int) -> int:
        for start, end, tag in links:
            if start <= position < end:
                return tag
        return 0

    formula = RUN_FORMULA | RUN_DISPLAY_FORMULA
    out: list[RunDescription] = []
    covered = 0
    edges = sorted({edge for start, end, _ in links for edge in (start, end)})

    def plain(start: int, end: int) -> None:
        # Tagged text between two styled runs: a run that changes nothing but the tag.
        cuts = [start, *(edge for edge in edges if start < edge < end), end]
        for left, right in zip(cuts, cuts[1:], strict=False):
            tag = tag_at(left)
            if tag:
                out.append(RunDescription(left, right, color=color, tag=tag))

    for run in runs:
        if run.start > covered:
            plain(covered, run.start)
        if run.flags & formula:
            out.append(run._replace(tag=tag_at(run.start)))
        else:
            cuts = [run.start, *(edge for edge in edges if run.start < edge < run.end), run.end]
            for left, right in zip(cuts, cuts[1:], strict=False):
                tag = tag_at(left)
                out.append(
                    run._replace(start=left, end=right, color=color if tag else run.color, tag=tag)
                )
        covered = max(covered, run.end)
    if links and links[-1][1] > covered:
        plain(covered, links[-1][1])
    return out

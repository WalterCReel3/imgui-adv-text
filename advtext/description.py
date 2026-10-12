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

**A host makes one too** (pptmstr's P8): `description_of(blocks, styles,
links)` fills in what is read off the blocks, and `check_description` holds
any description to the shape, raising `TypeError` or `ValueError` that names
the block. `advtext.ui.typeset_view.TypesetView.set_document` takes a
`Description` and runs the check where it is handed over, so a host's slip
is told at its own call and not by the library in the middle of a draw.

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

**What the package can pack, and the check holds a description to it**
(2026-10-12, after a review found values that passed the check and raised
`struct.error` or `OverflowError` in the middle of a draw): the package
writes a block, a run and a column as C structs, so an integer field is at
most `INT_MAX`, a real one at most `FLOAT_MAX` either side of zero, and a
colour is 32 bits. `check_description` and `check_runs` refuse anything
else, and a view runs them where a document is handed over.

**Text that cannot be encoded.** A Python `str` can hold what UTF-8 cannot:
a surrogate code point (U+D800 to U+DFFF), which is what
`bytes.decode(errors="surrogateescape")` makes of each undecodable byte and
so what tool output and file names read that way carry. The package encodes
a block's text and raises `UnicodeEncodeError` on one. `encodable(text)` is
the text with each replaced by `REPLACEMENT` (U+FFFD), one character for
one, so every offset still names what it named; `settled(block)` does that
to a whole block. **The views do it to everything they hand the library**
(`advtext.ui.typeset_view`), so a host does nothing. `check_description`
PASSES such text, since a view can show it; a host that hands a description
straight to `imtypeset.Document` calls `settled` on its blocks first.
"""

from __future__ import annotations

import collections
import re
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
    "FLOAT_MAX",
    "INT_MAX",
    "KIND_CODE",
    "KIND_HEADING",
    "KIND_HOST",
    "KIND_LIST_ITEM",
    "KIND_PARAGRAPH",
    "KIND_RULE",
    "KIND_TABLE",
    "LinkRow",
    "MISFIT_BLOCK",
    "REPLACEMENT",
    "RUN_DISPLAY_FORMULA",
    "RUN_FORMULA",
    "RUN_NO_BREAK",
    "RunDescription",
    "StyleDescription",
    "UNKNOWN_BLOCK_EXTENT_PX",
    "align_code",
    "cell_spans",
    "check_description",
    "check_runs",
    "column_aligns",
    "description_of",
    "encodable",
    "face_role",
    "settled",
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


def description_of(
    blocks: Iterable[BlockDescription],
    styles: Iterable[StyleDescription],
    links: Iterable[LinkRow] = (),
) -> Description:
    """
    A `Description` of blocks a HOST described, with what can be read off them filled in.

    For a host that has its own segmenter and hands a view its description
    (`advtext.ui.typeset_view.TypesetView.set_document`). `blocks[i].style`
    indexes `styles`, so there is at least one style; `StyleDescription()`
    is the document's own text. `links` say where each tagged run goes: a
    run's `tag` is a number of the host's own, above zero, and one `LinkRow`
    names its block, its range and its target. `tables` and `texts` are read
    off the blocks, and nothing misfits. Checked (`check_description`):
    raises `TypeError` or `ValueError` for something a view could not show.
    """
    held = list(blocks)
    made = Description(
        held,
        list(styles),
        list(links),
        [at for at, block in enumerate(held) if getattr(block, "kind", None) == KIND_TABLE],
        [getattr(block, "text", "") for block in held],
        collections.Counter(),
        collections.Counter(),
    )
    check_description(made)
    return made


INT_MAX: Final = 2**31 - 1
"""The most an integer field of a block, a run or a mark holds: the package packs a C `int`."""

FLOAT_MAX: Final = 3.4028234663852886e38
"""The most a real field holds, either side of zero: the package packs a C `float`."""

REPLACEMENT: Final = "\ufffd"
"""What stands for a character that cannot be encoded (`encodable`): U+FFFD."""

_SURROGATE: Final = re.compile("[\ud800-\udfff]")


def encodable(text: str) -> str:
    """
    `text` as the library can be handed it: each surrogate code point is `REPLACEMENT`.

    One character for one, so an offset into the one is an offset into the
    other. The same object when there is nothing to replace, which for ASCII
    is known without reading it. The module docstring says where such text
    comes from.
    """
    if text.isascii() or _SURROGATE.search(text) is None:
        return text
    return _SURROGATE.sub(REPLACEMENT, text)


def _settled_runs(runs: Any) -> Any:
    return runs if type(runs) is tuple else tuple(runs)


def settled(block: BlockDescription) -> BlockDescription:
    """
    `block` as a view keeps it: nothing in it a host still holds, and all of it encodable.

    `runs`, `rows`, each row, each cell's `runs` and `columns` are tuples
    (a list a host goes on appending to would otherwise change a block
    after it was checked), and `text`, `marker` and each cell's text are
    `encodable`. **The same object when it already is**, which is the usual
    case and costs a few comparisons. For a block `check_description` or a
    converter has passed; it checks nothing itself.
    """
    text, marker = encodable(block.text), encodable(block.marker)
    runs, columns = _settled_runs(block.runs), _settled_runs(block.columns)
    rows = block.rows
    if rows or type(rows) is not tuple:
        made = []
        same = type(rows) is tuple
        for row in rows:
            cells = []
            kept = type(row) is tuple
            for cell in row:
                cell_text, cell_runs = encodable(cell.text), _settled_runs(cell.runs)
                if cell_text is not cell.text or cell_runs is not cell.runs:
                    cell, kept = CellDescription(cell_text, cell_runs), False
                cells.append(cell)
            same = same and kept
            made.append(row if kept else tuple(cells))
        if not same:
            rows = tuple(made)
    if (
        text is block.text
        and marker is block.marker
        and runs is block.runs
        and columns is block.columns
        and rows is block.rows
    ):
        return block
    return block._replace(text=text, marker=marker, runs=runs, rows=rows, columns=columns)


def _brief(value: object) -> str:
    """`repr(value)`, cut where it would bury the message: an integer of 400 digits has one."""
    try:
        said = repr(value)
    except ValueError:  # an int past the interpreter's limit for digits
        return f"<{type(value).__name__} too long to print>"
    return said if len(said) <= 80 else f"{said[:60]}... ({len(said)} characters)"


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _real(value: object) -> bool:
    """A finite number a C `float` holds, and no `bool`: what a real field is given."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and -FLOAT_MAX <= value <= FLOAT_MAX
    )


def check_runs(runs: object, length: int, where: str) -> None:
    """
    Raise for runs the library could not be handed: `where` names what holds them.

    `runs` is a tuple or list of `RunDescription`s over a text of `length`
    characters: integers `0 <= start <= end <= length`, ascending and not
    overlapping (the library takes one run for a character), a face that is
    0 or one of `FACE_ROLES`' seven, a `scale` that is a finite number of
    zero or more (at most `FLOAT_MAX`), a `color` that is a packed colour
    of 32 bits, and integers of zero to `INT_MAX` for `flags` and `tag`.
    `TypeError` for a wrong type, `ValueError` for a wrong value.
    """
    if not isinstance(runs, (tuple, list)):
        raise TypeError(
            f"{where}: runs is a {type(runs).__name__}; it is a tuple of RunDescription"
        )
    reached = 0
    for number, run in enumerate(runs):
        here = f"{where}: run {number}"
        if not isinstance(run, RunDescription):
            raise TypeError(f"{here} is a {type(run).__name__}; it is a RunDescription")
        for name in ("start", "end", "face", "color", "flags", "tag"):
            if not _whole(getattr(run, name)):
                raise TypeError(f"{here}: {name} is {getattr(run, name)!r}; it is an integer")
        if not _real(run.scale):
            raise TypeError(
                f"{here}: scale is {_brief(run.scale)}; it is a finite number of at most "
                f"{FLOAT_MAX:.3g}"
            )
        if not 0 <= run.start <= run.end <= length:
            raise ValueError(f"{here} is [{run.start}, {run.end}) of a text of {length} characters")
        if run.start < reached:
            raise ValueError(
                f"{here} starts at {run.start}, before the run before it ends ({reached}): "
                "runs are ascending and do not overlap"
            )
        reached = run.end
        if not 0 <= run.face <= max(FACE_ROLES.values()):
            raise ValueError(f"{here}: face is {run.face}; it is 0 or one of FACE_ROLES")
        if run.scale < 0.0 or not 0 <= run.color <= 0xFFFFFFFF or run.flags < 0 or run.tag < 0:
            raise ValueError(f"{here}: scale, color, flags and tag are zero or more: {run!r}")
        if run.flags > INT_MAX or run.tag > INT_MAX:
            raise ValueError(f"{here}: flags and tag are at most {INT_MAX}: {run!r}")


def _check_block(block: object, at: int, styles: int) -> None:
    where = f"block {at}"
    if not isinstance(block, BlockDescription):
        raise TypeError(f"{where} is a {type(block).__name__}; it is a BlockDescription")
    for name in ("kind", "style", "quote_depth", "container", "item", "flags", "level"):
        if not _whole(getattr(block, name)):
            raise TypeError(f"{where}: {name} is {getattr(block, name)!r}; it is an integer")
    for name in ("text", "marker"):
        if not isinstance(getattr(block, name), str):
            raise TypeError(f"{where}: {name} is {getattr(block, name)!r}; it is a str")
    for name in ("left_indent", "extent"):
        value = getattr(block, name)
        if not _real(value):
            raise TypeError(
                f"{where}: {name} is {_brief(value)}; it is a finite number of pixels, at most "
                f"{FLOAT_MAX:.3g}"
            )
        if value < 0.0:
            raise ValueError(f"{where}: {name} is {value!r}; it is zero or more")
    if not KIND_PARAGRAPH <= block.kind <= KIND_TABLE:
        raise ValueError(f"{where}: kind is {block.kind}; it is one of the seven KIND_ integers")
    if not 0 <= block.style < styles:
        raise ValueError(
            f"{where}: style is {block.style} and the description has {styles} style(s); "
            "a block's style indexes Description.styles"
        )
    if min(block.quote_depth, block.container, block.item, block.flags, block.level) < 0:
        raise ValueError(f"{where}: quote_depth, container, item, flags and level are zero or more")
    if max(block.quote_depth, block.container, block.item, block.flags, block.level) > INT_MAX:
        raise ValueError(
            f"{where}: quote_depth, container, item, flags and level are at most {INT_MAX}"
        )
    check_runs(block.runs, len(block.text), where)
    for name in ("rows", "columns"):
        if not isinstance(getattr(block, name), (tuple, list)):
            raise TypeError(f"{where}: {name} is a {type(getattr(block, name)).__name__}")
    if block.kind != KIND_TABLE:
        if block.rows or block.columns:
            raise ValueError(f"{where}: rows and columns are a KIND_TABLE block's")
        return
    for number, row in enumerate(block.rows):
        if not isinstance(row, (tuple, list)):
            raise TypeError(
                f"{where}: row {number} is a {type(row).__name__}; it is a tuple of "
                "CellDescription"
            )
        for across, cell in enumerate(row):
            here = f"{where}: row {number}, cell {across}"
            if not isinstance(cell, CellDescription):
                raise TypeError(f"{here} is a {type(cell).__name__}; it is a CellDescription")
            if not isinstance(cell.text, str):
                raise TypeError(f"{here}: text is {cell.text!r}; it is a str")
            check_runs(cell.runs, len(cell.text), here)
    if block.text != table_text([cell.text for cell in row] for row in block.rows):
        raise ValueError(
            f"{where}: a table's text is table_text of its cells (a tab between the cells of "
            "a row, a newline between rows), which is what its positions index"
        )
    for number, column in enumerate(block.columns):
        here = f"{where}: column {number}"
        if not isinstance(column, ColumnDescription):
            raise TypeError(f"{here} is a {type(column).__name__}; it is a ColumnDescription")
        if not _whole(column.align) or not _real(column.width) or not _real(column.share):
            raise TypeError(
                f"{here} is {_brief(column)}; it is an integer and two finite numbers of at "
                f"most {FLOAT_MAX:.3g}"
            )
        if column.align not in ALIGNS.values() or column.width < 0.0 or column.share < 0.0:
            raise ValueError(f"{here} is {column!r}; an ALIGNS integer, a width and a share >= 0")


def check_description(description: object) -> None:
    """
    Raise for a `Description` a view could not show as it is given; `None` for one it can.

    What a host that describes its own blocks is told AT THE CALL that hands
    them over, and not by the library in the middle of a draw. `TypeError`
    for a wrong type and `ValueError` for a wrong value, each naming the
    block (and the run, the cell or the column) by number:

    - every block is a `BlockDescription` of the types its fields name, a
      `kind` that is one of the seven, a `style` that indexes `styles`,
      lengths that are finite and zero or more, integers of zero to
      `INT_MAX`, runs as `check_runs` has them, and `rows` / `columns` only
      on a `KIND_TABLE` block, whose `text` is `table_text` of its cells;
    - every style is a `StyleDescription` of numbers a C `float` holds
      (the library's struct takes a larger one as infinity, silently);
    - **not checked: whether the text can be encoded.** A surrogate code
      point passes; a view sets it as U+FFFD (`encodable`, and the module
      docstring);
    - every link is a `LinkRow` naming a block there is, a range of its text,
      a tag above zero and a `str` target;
    - `texts` are the blocks' texts and `tables` the table blocks' numbers
      (`description_of` fills both in);
    - `misfits` is empty: a block a converter did not know is an empty Host
      block there, and a view does not show a gap nobody asked for.

    This module's own check, with no library: it holds a description to the
    shape, not to what the library would make of it.
    """
    if not isinstance(description, Description):
        raise TypeError(f"{type(description).__name__} is not an advtext.description.Description")
    for name in ("blocks", "styles", "links", "tables", "texts"):
        if not isinstance(getattr(description, name), (tuple, list)):
            raise TypeError(
                f"Description.{name} is a {type(getattr(description, name)).__name__}; "
                "it is a list"
            )
    if description.misfits:
        raise ValueError(
            "the description holds blocks its converter did not know, each an empty Host "
            f"block: {dict(description.misfits)}"
        )
    for number, style in enumerate(description.styles):
        if not isinstance(style, StyleDescription):
            raise TypeError(f"style {number} is a {type(style).__name__}; it is a StyleDescription")
        if not _whole(style.Face) or not _whole(style.Align) or not _whole(style.Color):
            raise TypeError(f"style {number}: Face, Align and Color are integers: {style!r}")
        for name in ("Scale", "LineHeight", "FirstLineIndent", "SpaceAbove", "SpaceBelow"):
            if not _real(getattr(style, name)):
                raise TypeError(
                    f"style {number}: {name} is {_brief(getattr(style, name))}; it is a finite "
                    f"number of at most {FLOAT_MAX:.3g}"
                )
        if not _real(style.MarkerGap):
            raise TypeError(
                f"style {number}: MarkerGap is {_brief(style.MarkerGap)}; a finite number of "
                f"at most {FLOAT_MAX:.3g}"
            )
        if (
            not 0 <= style.Face <= max(FACE_ROLES.values())
            or style.Align not in ALIGNS.values()
            or not 0 <= style.Color <= 0xFFFFFFFF
            or style.Scale < 0.0
            or style.LineHeight < 0.0
        ):
            raise ValueError(
                f"style {number}: a Face that is 0 or one of FACE_ROLES, an ALIGNS integer, "
                f"a packed colour, and a Scale and a LineHeight of zero or more: {style!r}"
            )
    for at, block in enumerate(description.blocks):
        _check_block(block, at, len(description.styles))
    blocks = description.blocks
    if list(description.texts) != [block.text for block in blocks]:
        raise ValueError("Description.texts are not the blocks' texts, one for one")
    if list(description.tables) != [at for at, b in enumerate(blocks) if b.kind == KIND_TABLE]:
        raise ValueError("Description.tables are not the numbers of the KIND_TABLE blocks")
    for number, row in enumerate(description.links):
        here = f"link {number}"
        if not isinstance(row, LinkRow):
            raise TypeError(f"{here} is a {type(row).__name__}; it is a LinkRow")
        if not all(_whole(value) for value in row[:4]) or not isinstance(row.target, str):
            raise TypeError(f"{here} is {row!r}; four integers and a str")
        if not 0 <= row.block < len(blocks):
            raise ValueError(f"{here} names block {row.block} of {len(blocks)}")
        if not 0 <= row.start <= row.end <= len(blocks[row.block].text) or row.tag < 1:
            raise ValueError(f"{here} is {row!r}: a range of its block's text and a tag above zero")
        if row.tag > INT_MAX:
            raise ValueError(f"{here}: tag is {row.tag}; a run's tag is at most {INT_MAX}")


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

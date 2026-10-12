r"""
Markdown straight to what imtypeset takes: text and runs, and no node on the way.

**Experimental** (branch `experimental/imtypeset-adoption`, step A6 of
`../imtypeset/docs/advtext-rework-plan.md` section 6.3, "skip the material").
Of the facade: `parse_markdown`, `MarkdownDocument`, `MarkdownStream` and
`MarkdownConverter`; the rest is reached from here.

The path that exists beside it goes the long way round. `imscribe.markdown`
turns the source into *nodes* -- a `CharNode` per character, glue between
words, kerns it measured, a formula as a box the old math core built -- and
`imscribe.typesetter.Converter` then walks those nodes back into a string and
runs, dropping the kerns and the boxes again. This module reads the same
tokens from the same parser (`imscribe.markdown_rules`) and writes the string
and the runs directly. It needs no font metrics, so it takes no resolver.

    document = parse_markdown(source, theme, math=True)    # blocks of text and runs
    converter = MarkdownConverter(theme)
    described = converter.describe(document.blocks)        # what a Document is given

or `describe_markdown(source, theme)` for both at once.

## Two steps, and why

`parse_markdown` gives `MarkdownBlock`s: the four shapes `imscribe.markdown`
has (`MarkdownText`, `MarkdownCode`, `MarkdownRule`, `MarkdownTable`) with a
`str` and runs where those have material. They are frozen values that name a
`BlockStyle` and a URL, not a style *index* or a link *tag*.

`MarkdownConverter` gives the `Description`, and has the surface of
`imscribe.typesetter.Converter` -- `describe(blocks, base)`, `styles`,
`targets`, `link_target(tag)`, `px`, `theme`, `link_color` -- because the
index and the tag belong to a table that outlives one call: a stream
describes its changed tail again and again and the blocks already in the
library's document go on naming styles by number. A view that holds blocks
and a converter can be given these blocks and this converter instead.

## What it is held equal to

`tests/test_typeset_markdown.py` compares, for every `demo/**/*.md`, a corpus
of awkward sources and generated ones, all seven fields of this module's
`Description` with `Converter(theme).describe(build_document(source,
...).blocks)`. With `converter_spaces=True` (below) they are equal but for
three things, each of which the test names and counts rather than skips:

1. **No kern is counted.** `kinds["kerns dropped ..."]` is the number of kern
   nodes the old path made and threw away. Nothing here makes one.
2. **A character its face lacks.** `imscribe.markdown._stand_in` asks the font
   and sets such a character from another face (a run in that face comes out
   of the old path) or as U+FFFD (a misfit is counted there). This module has
   no font to ask: the character is described in the face it was written in,
   and what is drawn for it is the library's to decide.
3. **A formula the old math core refuses.** There the source is set as code,
   dollars and all. Here every closed formula is a Formula run and the
   library is what accepts or refuses it. `refuses=` puts the old decision
   back for a caller that wants it (the test does, to show the rest equal).

## The space after a run

There is a fourth difference, and it is the default. In the material a space
is glue, and glue has no face: `Converter` begins a run at the first
*character* set differently and ends it at the next, so the space after a
code span is inside the code run and a space that opens one is outside it.
imtypeset sets a space in the face of the run it is in. Measured on
2026-10-11 with the default theme (`.concerns/SW-2-scripts/run_space_probe.py`):
the space after `` `ab` `` in a paragraph is 8.0 px wide through `Converter`'s
runs, and 3.961 px when the run ends before it, which is the width of the
glue the old core set there.

So here a space is in the face of the text it was written in, which is the
face whose space the old core measured for its glue: the space after a code
span is the paragraph's, a space inside one is the code face's.
`converter_spaces=True` gives `Converter`'s runs instead, exactly, and is
what the equality above is shown with. The test holds the default two ways:
against `converter_spaces=True` (nothing differs but where runs meet white
space) and against the material's glue widths (every space of every demo is
in a face whose space is that wide; `Converter`'s runs fail that).

## Formulas: who says no

With `math=True` the two math rules are on (`imscribe.markdown` describes
them) and what they find becomes a run flagged `RUN_FORMULA` or
`RUN_DISPLAY_FORMULA` over the formula's SOURCE, no dollars. Three things are
never offered as a formula, here as there: a `$$` block whose closing line
has not been read (`$$` and its source so far, in the code face), an empty
formula, and one `refuses(source, display, size)` answers true for (its
source with its dollars, in the code face).

## Tables

A table is described as `imscribe.typesetter.Converter` describes one: ONE
block of `KIND_TABLE`, which the library sets (imtypeset commit `be40444`).
Its cells are on the `MarkdownTable` (text, runs, link ranges, per cell) and
go into `BlockDescription.rows` with the converter's link tags laid over the
runs; `BlockDescription.columns` has one `ColumnDescription` a column for the
alignment, and `BLOCK_TABLE_HEADER` is set when there is a header row. The
block's text is `table_text` of the cells, and a cell's links are rows of
`Description.links` as ranges of that text. A `MarkdownTable` may state its
columns (`widths`, scaled points with the padding in, or `shares`): what a
host that lets a column be dragged hands over. A test holds the two
converters equal on every table under `demo/`.

## A stream

`MarkdownStream` is `imscribe.stream.StreamDocument`'s commit rule: text
through `append`, the tail parsed up to its last complete line to decide
which top-level blocks are settled, every top-level block before the last
committed, and the rest -- unfinished line included -- parsed again for the
live blocks. `blocks`, `committed`, `live`, `revision`, `source`, `sources`,
`closed`, `pending`, `theme`.

And three of its shortcuts, so that a long block being written is not read
from its top at every read: a list or a quote is read from the line its last
child starts on (`_resume_point`), a top-level fence a line at a time and a
top-level table a row at a time. Measured on 2026-10-11, a line a piece, mean
cost of a read over the last tenth of the pieces
(`.concerns/T3-A2-scripts/stream_cost_long.py`, same run, load about 3):

    fence of 600 lines   StreamDocument 0.10 ms   MarkdownStream 0.07 ms   (before: 3.6)
    list of 300 items    StreamDocument 0.50 ms   MarkdownStream 0.24 ms   (before: 21)
    table of 200 rows    StreamDocument 0.35 ms   MarkdownStream 0.20 ms   (before: 16)

and the same at the first tenth as at the last. What it does NOT have: a
fence inside a list item or a quote is read whole while it is open (1.0 ms a
read by its 300th line, against `StreamDocument`'s 0.08).

## What a host may ask of the reading

`ReaderOptions`, as `reader=` to `parse_markdown`, `describe_markdown` and
`MarkdownStream` (2026-10-12; pptmstr's requests P7, P27 and P32). Six switches,
all off by default, and all off is the reading there has always been: raw
HTML set as the characters written (`html_as_text`), an image read as an
exclamation mark and a link (`images_as_text`), the stars of a glob kept
(`keep_glob_stars`), a link followed by its destination, inside the link
(`show_link_destinations`), a fence's info string set in front of its
code (`show_fence_info`; "A fence's info string" below), and a backslash
escape set with its backslash (`backslashes_as_written`). The class says what
each does exactly. The first three and the last choose the PARSER
(`imscribe.markdown_rules._reader_parser`, one object per combination, never
a rule switched on a shared one); the other two are `_Reader`'s (and, for a
fence a stream follows line by line, `MarkdownStream`'s). A stream and a
settled parse given equal options go through the same parser and the same
reader, and `tests/test_reader_options.py` holds a stream to one parse of
what it has after every piece under each option.
**No host needs `markdown_rules._parser`**, and one that changes that shared
object changes the reading of everything else in its process.

## The size of a code span

`Theme.inline_code_scale` and `Theme.inline_code_step` (2026-10-12; pptmstr's
P11), which at their defaults say nothing. Otherwise every run in the code
role (a code span, and a formula shown as its source) carries
`RunDescription.scale = Theme.inline_code_run_scale(kind)`, which the library
reads as a multiple of the size of the block the run is in (measured:
`tests/test_reader_options.py`). Nothing else writes a scale, and on a
monospace base nothing does.

## Tabs

A tab in a fenced or an indented block is handed to the library as a tab
(2026-10-12; pptmstr's P29). Until then it was expanded here to spaces, to
the next multiple of `imscribe.markdown_rules.TAB_WIDTH` columns counted from
the start of its line, so a Makefile recipe copied out of a view had spaces
where its author wrote a tab. The library's own rule for a code block is the
same stop ("tabs to the next multiple of four columns"), and by measurement
(`tests/test_host_requests_2.py`; `.concerns/N-HOST2-scripts/p29_tabs.py`)
the two put every character of sixteen awkward lines at the same place to
0.00001 px, at seven em sizes and two pixel heights, under each code
overflow, with characters the code face lacks and a combining mark before
the tab: the screen is what it was, `MarkdownCode.text` and a view's `texts`
hold the tab, and a copy gives it back. What was frozen of the old core has
the spaces, and `tests/material_frozen.with_the_old_tabs` is the one stated
difference. `imscribe.ui.typeset_diff_view` never expanded a tab.

## A fence's info string

`ReaderOptions.show_fence_info` (2026-10-12; pptmstr's P27) sets it as a
block of its own in front of the code, a `MarkdownText` of kind
`BlockKind.CODE`; the class says exactly what. It is not the code's first
line, which is what pptmstr did meanwhile, for three reasons, the first
measured: the library reads no run on a code block (its header: "no runs";
a coloured run on one changes no vertex, `tests/test_host_requests_2.py`),
so a first line could be told from the code only by a mark a host lays over
it; a copy of the code would begin with a line that is not code; and
`MarkdownCode.text`, which a host's syntax colouring and
`imscribe.ui.typeset_hosts.TypesetDiffFences` read, would not be the code. A
text block is selected, copied and inked like any other. A settled parse
and a stream make the two blocks through one function (`_fence_info`), and
the test holds a stream to one parse of what it has after every piece.

## The space after a list

`Theme.space_after_list` (2026-10-12; pptmstr's P26), read here by
`_Reader._end_list`: the last item of an outermost list takes it as its
space below. `None`, the default, is the item's own, as ever: the gap after
a list is then the gap between two of its items, which is also what the old
core set (the frozen descriptions give a list's last item its items' style).

## What this module imports

`imscribe.description` (the standard library only) for the description types
and the enumerators, which are the very objects `imscribe.typesetter` has;
`imscribe.markdown_rules` (markdown-it only); `imscribe.theme` for `Theme`,
`BlockStyle`, `BlockKind`, `Emphasis` and `Align`; and `imscribe.primitives` for
one conversion, which `imscribe.theme` imports too and which imports nothing.
So importing this module loads those four modules of imscribe and no other,
and `tests/test_typeset_markdown.py` says so by name. Not loaded: `style`,
`nodes`, `pack`, `badness`, `markdown`, `shipout`, `fontlib`, `math`,
`units`, `fontmetrics`, `typesetter`. (Building a `Theme` loads none of them
either, since 2026-10-11: `imscribe.theme` says how.)
"""

from __future__ import annotations

import collections
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any, NamedTuple

from imscribe.description import (
    BLOCK_HARD_BREAKS,
    BLOCK_TABLE_HEADER,
    FACE_DEFAULT,
    KIND_CODE,
    KIND_HEADING,
    KIND_HOST,
    KIND_LIST_ITEM,
    KIND_PARAGRAPH,
    KIND_RULE,
    KIND_TABLE,
    MISFIT_BLOCK,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    RUN_NO_BREAK,
    UNKNOWN_BLOCK_EXTENT_PX,
    BlockDescription,
    CellDescription,
    ColumnDescription,
    Description,
    LinkRow,
    RunDescription,
    StyleDescription,
    align_code,
    cell_spans,
    column_aligns,
    face_role,
    table_text,
    with_tags,
)
from imscribe.markdown_rules import (
    _BULLET,
    _COLUMN_ALIGNS,
    BlockSource,
    ColumnAlign,
    SourceSpan,
    _line_starts,
    _parse,
    _reader_parser,
    _span,
)
from imscribe.primitives import Scaled, px_from_sp
from imscribe.theme import Align, BlockKind, BlockStyle, Emphasis, Theme

__all__ = [
    "BLOCK_HARD_BREAKS",
    "BLOCK_TABLE_HEADER",
    "BlockDescription",
    "CellDescription",
    "ColumnDescription",
    "Description",
    "FACE_DEFAULT",
    "FormulaRange",
    "KIND_CODE",
    "KIND_HEADING",
    "KIND_HOST",
    "KIND_LIST_ITEM",
    "KIND_PARAGRAPH",
    "KIND_RULE",
    "KIND_TABLE",
    "LinkRange",
    "LinkRow",
    "MarkdownBlock",
    "MarkdownCell",
    "MarkdownCode",
    "MarkdownConverter",
    "MarkdownDocument",
    "MarkdownRule",
    "MarkdownStream",
    "MarkdownTable",
    "MarkdownText",
    "RUN_DISPLAY_FORMULA",
    "RUN_FORMULA",
    "RUN_NO_BREAK",
    "ReaderOptions",
    "Refuses",
    "RunDescription",
    "StyleDescription",
    "describe_markdown",
    "parse_markdown",
    "reader_options",
    "table_text",
    "text_as_set",
]

# The description's types and integers are `imscribe.description`'s, imported
# above and re-exported: the same objects `imscribe.typesetter` has.
_with_tags = with_tags


# ---------------------------------------------------------------------------
# Blocks: what a parse gives
# ---------------------------------------------------------------------------


class LinkRange(NamedTuple):
    """
    A link's range in its block's (or cell's) `str`, and its URL.
    """

    start: int
    end: int
    target: str


class FormulaRange(NamedTuple):
    r"""
    One `$...$` of a block: where it is in the text, its source, and what became of it.

    `state` is `"set"` for a Formula run (the range is the source, no
    dollars), `"refused"` for one `refuses` turned down and `"unclosed"` for a
    `$$` block still being written (the range is then what is shown in the
    code face, dollars included).
    """

    start: int
    end: int
    source: str
    display: bool = False
    state: str = "set"


@dataclass(frozen=True, slots=True)
class MarkdownText:
    """
    A heading, a paragraph, a list item, quoted text or a display formula.

    `runs` carry faces and formulas and no tag: `links` are beside them, and
    a converter lays its tags over the runs. `left_indent` is absolute, in
    scaled points, as `imscribe.markdown.TextBlock.left_indent` is.
    """

    kind: BlockKind
    style: BlockStyle
    text: str
    runs: tuple[RunDescription, ...] = ()
    links: tuple[LinkRange, ...] = ()
    marker: str = ""
    left_indent: Scaled = 0
    quote_depth: int = 0
    hard_breaks: bool = False
    formulas: tuple[FormulaRange, ...] = ()


@dataclass(frozen=True, slots=True)
class MarkdownCode:
    r"""
    A fenced or indented block: its lines joined by `\n`, blank end dropped.

    **A tab is a tab** (since 2026-10-12; pptmstr's P29). The library sets
    one to the next multiple of four columns counted from the start of its
    line, which is where `str.expandtabs(TAB_WIDTH)` put the spaces this
    text held before, and a copy gives the tab back. "Tabs" in the module
    docstring has the measurement.
    """

    style: BlockStyle
    text: str
    language: str = ""
    left_indent: Scaled = 0


@dataclass(frozen=True, slots=True)
class MarkdownRule:
    """
    A thematic break.
    """

    style: BlockStyle
    thickness: Scaled
    left_indent: Scaled = 0


@dataclass(frozen=True, slots=True)
class MarkdownCell:
    """
    One table cell: its text, its runs, its links and its formulas.
    """

    text: str
    runs: tuple[RunDescription, ...] = ()
    links: tuple[LinkRange, ...] = ()
    header: bool = False
    hard_breaks: bool = False
    formulas: tuple[FormulaRange, ...] = ()


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    """
    A table, as rows of cells and one alignment per column.

    `widths` and `shares` are for a host that states the columns itself (a
    drag of a column's edge): `dataclasses.replace(table, widths=...)`. One
    entry a column or none at all. `widths` are scaled points, cell padding
    included, and the table is then exactly as wide as they sum to; `shares`
    are parts of the width in any unit. The parser sets neither.
    """

    style: BlockStyle
    header: tuple[MarkdownCell, ...]
    rows: tuple[tuple[MarkdownCell, ...], ...]
    aligns: tuple[ColumnAlign, ...]
    left_indent: Scaled = 0
    widths: tuple[Scaled, ...] = ()
    shares: tuple[float, ...] = ()


MarkdownBlock = MarkdownText | MarkdownCode | MarkdownRule | MarkdownTable
"""
Anything `parse_markdown` produces.
"""


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """
    A whole source, read: its blocks, and where each came from (`sources[i]` for `blocks[i]`).
    """

    blocks: tuple[MarkdownBlock, ...]
    sources: tuple[BlockSource, ...] = ()


Refuses = Callable[[str, bool, Scaled], bool]
"""
`(source, display, size) -> bool`: whether a formula is to be shown as its source instead.

`size` is the size of the text the formula sits in, in scaled points, as an
`imscribe.markdown.MathBuilder` is given it.
"""


# ---------------------------------------------------------------------------
# What a host may ask of the reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReaderOptions:
    """
    How markdown is READ, where a host wants something other than CommonMark's reading.

    For `parse_markdown`, `describe_markdown` and `MarkdownStream`, as
    `reader=`. **One object for a settled document and for a stream**: two
    calls given equal options read with the same parser object
    (`imscribe.markdown_rules._reader_parser`) and the same reader, so what a
    stream ends as is what one parse of its whole source gives, option for
    option (`tests/test_reader_options.py` holds it after every piece). A
    frozen value: it compares and hashes by its fields.

    **Every field is off by default, and all off is the reading there has
    always been**: the same parser objects, the same blocks.

    These exist for a host whose reader is approving text somebody else
    wrote (pptmstr's request P7). A CommonMark reader shows less than was
    written in four ways, and each field puts one of them back:

    `html_as_text`
        Raw HTML is set as the characters written. Off, a block of HTML is
        dropped whole, a tag in a line is dropped with nothing in its place
        (`List<String>` reads `List`), and an unclosed `<!--` takes every
        line after it to the end of the document. On, the two rules that
        read raw HTML are not run, so `<div>` and `<!-- note` are the text
        of a paragraph and `<String>` is seven characters of its line. An
        autolink (`<https://example.org>`) is not raw HTML and is a link
        either way; an entity (`&amp;`) is still one character.

    `images_as_text`
        `![alt](address)` is not dropped. Off, an image and its description
        are left out (this library draws no image). On, the image rule is
        not run, and what is left is what markdown reads when nothing claims
        the `!`: an exclamation mark and then a LINK whose text is the
        description and whose target is the image's address. The address is
        on screen only with `show_link_destinations` as well, as any link's
        is; the characters `[`, `]`, `(` and `)` are not set.

    `keep_glob_stars`
        The stars of `**/*.py`, `src/*`, `/* note */` and `2*3*4` are set,
        and `**bold**` is still bold. The rule, what tells the two apart
        (the character on each side of a run of stars) and what it gets
        wrong in each direction are `imscribe.markdown_rules._written_stars`'s
        docstring; in one line, a run of stars is text when a `/` touches
        it, when `.` and a non-space follow it, or when a letter or digit is
        on both sides of it.

    `show_link_destinations`
        A link is followed by where it goes: its text, a space, and the
        destination in parentheses, `text (https://example.org/x)`, or with
        a title `text (https://example.org/x "the title")`. **The link's
        range covers all of it**, the parenthesis included, so the
        destination takes the link's tag, its ink and its click
        (`MarkdownText.links`, then `Description.links` and `Run.tag`). The
        destination is the one that would be followed: markdown-it's
        normalised form (percent-encoded, a host name in punycode), so a
        text that only looks like its destination does not hide it. It is
        left unsaid in one case, when the link's text already IS the
        destination, character for character, give or take a scheme the
        reader supplied (`mailto:`, `http://`, `https://`) and one closing
        `/`: most autolinks, and a bare address written as its own text. A
        link with a title is always followed by both. In a table cell the
        same.

    `show_fence_info`
        A fence's info string is set (2026-10-12; pptmstr's P27). Off, the
        words after the backticks are `MarkdownCode.language` and are drawn
        nowhere: of ```` ```python IMPORTANT also delete tests ```` a reader
        sees the code and nothing else. On, a fence that has an info string
        is TWO blocks: first a `MarkdownText` of kind `BlockKind.CODE`
        holding the whole info string, language included, each run of white
        space in it one space; then the `MarkdownCode`, whose `language` and
        `text` are what they are with the option off. Nothing else makes a
        `MarkdownText` of that kind, so that is how a host knows the block
        (`TypesetView.block_role` answers `"CODE"` for both), and it is an
        ordinary text block: it wraps, it is selected and copied as its own
        block, and `TypesetView.set_colours` inks it. It is in the code
        face at the code block's indent, with the code's space above it and
        none between it and its code (two styles, `space_below=0` and
        `space_above=0`, beside the theme's one). Both blocks have the
        fence's place in the source. A fence with no info string, and an
        indented code block, are one block as ever. "A fence's info string"
        in the module docstring says why it is a block and not a line of
        the code.

    `backslashes_as_written`
        A backslash escape is set with its backslash (2026-10-12; pptmstr's
        P32). Off, CommonMark's reading: `C:\\_work\\*.log` is set as
        `C:_work*.log`, `foo\\.py` as `foo.py`, `\\\\server` as `\\server`.
        On, a backslash before one of the 32 ASCII punctuation characters is
        set and so is the character, which still marks nothing:
        `\\*not emphasis\\*` is those sixteen characters, upright. So a path
        or a pattern reads as it was written, and a writer who escaped a
        star on purpose sees their backslash. **A backslash that ends a line
        is set and the line still ends there** (a hard break, as in
        CommonMark, with the backslash before it). `\\$` with math on is
        `\\$` and opens no formula. `\\|` in a table cell is `\\|`, in a code
        span in a cell too. NOT reached, because the backslash is read
        before any inline text is: a link's destination and title
        (`[a](C:\\_x)` still goes to, and with `show_link_destinations`
        shows, `C:_x`) and a link reference definition. Unchanged, having
        never been escapes: a backslash in a code span, a fenced or indented
        block, an autolink, a formula's source, a fence's info string.
        `imscribe.markdown_rules._written_backslashes` has the rule and why
        the escape rule is replaced and not switched off.

    Not here, because pptmstr's old seam did it outside the parser and a
    host still can: breaking a long unbreakable word.

    **A host that wants one character taken literally needs no escape at
    all** if it makes the block itself: the `text` of a `MarkdownText`, a
    `MarkdownCode` or a `MarkdownCell` handed to a view is never read as
    markdown, so every character of it is set (white space apart: a text
    block's is the library's, `text_as_set`). An escape is needed only inside
    a string the host hands over to be READ as markdown, and there
    CommonMark's own backslash still works under `backslashes_as_written`:
    the character is literal, and its backslash shows.
    """

    html_as_text: bool = False
    images_as_text: bool = False
    keep_glob_stars: bool = False
    show_link_destinations: bool = False
    show_fence_info: bool = False
    backslashes_as_written: bool = False

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, bool):
                raise TypeError(
                    f"ReaderOptions.{field.name} is True or False, not {type(value).__name__}"
                )


_AS_COMMONMARK = ReaderOptions()


def reader_options(reader: object) -> ReaderOptions:
    """
    `reader` as given to `parse_markdown` or `MarkdownStream`, checked: `None` is the default.

    Raises `TypeError`, naming the type, for anything that is neither `None`
    nor a `ReaderOptions`. Public so that something which keeps a host's
    `reader=` for a parse it makes later (a view) can refuse a mistake at
    the host's call and not at that parse.
    """
    if reader is None:
        return _AS_COMMONMARK
    if not isinstance(reader, ReaderOptions):
        raise TypeError(f"reader is a ReaderOptions or None, not {type(reader).__name__}")
    return reader


def _names_itself(said: str, target: str) -> bool:
    """
    Whether a link's text is its own destination, character for character.

    pptmstr's rule (`_names_itself` in its old seam). The two may differ in a
    scheme the reader supplied and in one closing `/`, and in nothing else.
    markdown-it's own normalising is deliberately not asked: it is what turns
    `https://аpple.com` written with a Cyrillic `а` into the `xn--` host the
    link goes to, and a text that only NORMALISES to its destination is a
    lookalike of it, which is the link whose destination most needs showing.
    """
    said = said.strip().removesuffix("/")
    goes = target.removesuffix("/")
    return bool(said) and goes in (said, f"mailto:{said}", f"http://{said}", f"https://{said}")


# ---------------------------------------------------------------------------
# Inline content to text and runs
# ---------------------------------------------------------------------------


class _Run:
    r"""
    One block's (or cell's) text under construction.

    This is `imscribe.markdown._Converter._append_text` and
    `imscribe.typesetter.Converter._text_of` run together with the nodes left
    out, so every rule here is one of theirs and is named where it is applied.
    What the nodes were needed for, and how it is done without them:

    - `any` is "the node list is not empty": white space before the first
      node of a block is dropped, and after it is a space.
    - `glues` is how many interword glue nodes the list ends with, which is
      what a hard break's `\unskip` removes (`imscribe.markdown._unskip`). In
      `parts` each of those is its own `" "`, so removing them is a slice.
    - `eject` is a forced break that is so far the last node. In a block set
      centred or ragged left a hard break is that one penalty and no fill
      (`imscribe.markdown._fill_and_break`), and the old converter reads it as
      a newline only when something follows it. So the newline is written
      when the next node arrives, and positions noted in between (`late`) are
      moved past it then.
    """

    __slots__ = (
        "any",
        "base",
        "converter_spaces",
        "eject",
        "formulas",
        "glues",
        "hard",
        "late",
        "links",
        "opened",
        "parts",
        "pos",
        "run_font",
        "run_scale",
        "run_start",
        "runs",
    )

    def __init__(self, base: int, converter_spaces: bool = False) -> None:
        self.base = base
        self.converter_spaces = converter_spaces
        self.parts: list[str] = []
        self.pos = 0
        self.any = False
        self.glues = 0
        self.eject = False
        self.hard = False
        self.runs: list[RunDescription] = []
        self.run_start = 0
        # The open run's face and its scale. A scale of 0.0 is "the block's
        # size", and is what every run has unless the theme sizes its code
        # spans (`Theme.inline_code_run_scale`).
        self.run_font = base
        self.run_scale = 0.0
        # A link is [start, end, target] while the run is being built: a hard
        # break may still move either end.
        self.links: list[list[Any]] = []
        self.opened: list[list[Any]] = []
        self.late: list[tuple[list[Any], int]] = []
        self.formulas: list[FormulaRange] = []

    def _node(self) -> None:
        """
        A node is about to follow: a forced break that was last is last no longer.
        """
        if self.eject:
            self.eject = False
            if not self.parts or self.parts[-1] != "\n":
                self._newline()
                for entry, index in self.late:
                    entry[index] += 1
            self.late.clear()
        self.any = True

    def _newline(self) -> None:
        """
        A hard break's newline. It has no face: a run ends before it and another begins after.

        With `converter_spaces` the open run goes on over it, as over a space.
        """
        if not self.converter_spaces:
            self._close(self.pos)
        self.parts.append("\n")
        self.pos += 1
        self.hard = True
        if not self.converter_spaces:
            self._open(self.pos, self.base, 0.0)

    def _open(self, start: int, font: int, scale: float) -> None:
        self.run_start, self.run_font, self.run_scale = start, font, scale

    def _close(self, end: int) -> None:
        if (self.run_font != self.base or self.run_scale) and end > self.run_start:
            self.runs.append(RunDescription(self.run_start, end, self.run_font, self.run_scale))

    def space(self, font: int, scale: float = 0.0) -> None:
        """
        A run of white space: one space, or nothing at the very start of the block.

        `font` is the face of the text the space was written in, and the
        space is set in it, at that text's `scale`: a run begins or ends at
        a space as it does at a letter. With `converter_spaces` a space has
        no face, as glue has none in the material, and whatever run is open
        goes on over it.
        """
        if not self.any:
            return
        self._node()
        if (font != self.run_font or scale != self.run_scale) and not self.converter_spaces:
            self._close(self.pos)
            self._open(self.pos, font, scale)
        self.parts.append(" ")
        self.pos += 1
        self.glues += 1

    def text(self, text: str, font: int, scale: float = 0.0) -> None:
        """
        Characters in the face `font` at `scale`, every run of white space in them one space.

        `str.split` and `str.isspace` agree on what white space is, which is
        what makes this `_append_text`'s loop: it cuts on `isspace`.
        """
        if not text:
            return
        words = text.split()
        if not words:
            self.space(font, scale)
            return
        if text[0].isspace():
            self.space(font, scale)
        self._node()
        if font != self.run_font or scale != self.run_scale:
            self._close(self.pos)
            self._open(self.pos, font, scale)
        joined = " ".join(words)
        self.parts.append(joined)
        self.pos += len(joined)
        self.glues = 0
        if text[-1].isspace():
            self.space(font, scale)

    def after_white_space(self) -> bool:
        """
        Whether what is written next begins a line or follows a space: no space is wanted first.

        True at the very start, after an interword space, and after a hard
        break, whether its newline is written yet or not.
        """
        return (
            not self.any
            or self.glues > 0
            or self.eject
            or (bool(self.parts) and self.parts[-1] == "\n")
        )

    def formula(self, source: str, display: bool) -> None:
        """
        A formula the library is to set: its source, under a run that says so.
        """
        self._node()
        self._close(self.pos)
        end = self.pos + len(source)
        self.runs.append(
            RunDescription(self.pos, end, flags=RUN_DISPLAY_FORMULA if display else RUN_FORMULA)
        )
        self.formulas.append(FormulaRange(self.pos, end, source, display))
        self.parts.append(source)
        self.pos = end
        self._open(end, self.base, 0.0)
        self.glues = 0

    def link_open(self, target: str) -> None:
        entry = [self.pos, self.pos, target]
        if self.eject:
            self.late.append((entry, 0))
        self.opened.append(entry)

    def link_close(self) -> None:
        if not self.opened:
            return
        entry = self.opened.pop()
        entry[1] = self.pos
        if self.eject:
            self.late.append((entry, 1))
        self.links.append(entry)

    def hard_break(self, align: Align) -> None:
        r"""
        A markdown hard break: `\unskip`, then the forced break.
        """
        if self.glues:
            del self.parts[-self.glues :]
            self.pos -= self.glues
            self.glues = 0
            end = self.pos
            for entry in self.links:
                if entry[1] > end:
                    entry[0], entry[1] = min(entry[0], end), end
            for entry in self.opened:
                entry[0] = min(entry[0], end)
            # A run that a removed space began, or ended on, ends here.
            while self.runs and self.runs[-1].end > end:
                last = self.runs.pop()
                if last.start < end:
                    self.runs.append(last._replace(end=end))
            if self.run_start >= end:
                # The open run held nothing but a removed space.
                self._open(end, self.base, 0.0)
        self._node()
        if align in (Align.RIGHT, Align.CENTER):
            # The penalty alone. A newline only if a node follows: `_node`.
            self.eject = True
        elif not self.parts or self.parts[-1] != "\n":
            # The fill glue, which the old converter reads as the newline
            # wherever it stands; the penalty after it then adds nothing.
            self._newline()

    def finish(self) -> tuple[str, tuple[RunDescription, ...], tuple[LinkRange, ...]]:
        """
        The text, the runs, and the links that cover at least one character.
        """
        self._close(self.pos)
        links = tuple(
            LinkRange(start, end, target)
            for start, end, target in sorted(self.links, key=lambda entry: entry[0])
            if end > start
        )
        return "".join(self.parts), tuple(self.runs), links


@dataclass(slots=True)
class _List:
    kind: BlockKind
    number: int = 1


class _Nesting(NamedTuple):
    """
    What a `_Reader` carries from one token to the next, between two blocks.

    `imscribe.markdown._WalkState` with a marker that is a `str`: which lists
    are open and what number each has reached, how deep the quotes go, the
    indent those add up to, and the marker an item is still waiting to hand
    to a paragraph. A reader given this back emits, for the tokens that
    follow, what the reader it was taken from would have.
    """

    lists: tuple[tuple[BlockKind, int], ...]
    quote_depth: int
    indent: Scaled
    marker: str


class _Reader:
    """
    One pass over one source's tokens: `imscribe.markdown._Converter`, writing text.

    The walk, the nesting state and the source map are that class's, line for
    line where the nodes are not involved.
    """

    def __init__(
        self,
        theme: Theme,
        refuses: Refuses | None,
        converter_spaces: bool = False,
        reader: ReaderOptions = _AS_COMMONMARK,
    ) -> None:
        self._theme = theme
        self._refuses = refuses
        self._converter_spaces = converter_spaces
        self._destinations = reader.show_link_destinations
        self._fence_info = reader.show_fence_info
        self._list_end: Scaled | None = theme.space_after_list
        self._blocks: list[MarkdownBlock] = []
        self._sources: list[BlockSource] = []
        self._lists: list[_List] = []
        self._quote_depth = 0
        self._indent: Scaled = 0
        self._marker = ""
        self._heading: BlockKind | None = None
        self._heading_span: SourceSpan | None = None
        self._next = 0
        self._roles: dict[tuple[BlockKind, Emphasis], tuple[int, float]] = {}
        self._marked: tuple[int, _Nesting | None] = (0, None)

    def _role(self, kind: BlockKind, emphasis: Emphasis) -> tuple[int, float]:
        """
        The face a run of `emphasis` in a `kind` block is set in, and its scale.

        The scale is 0.0, "the block's size", for everything but text in the
        code role (a code span, and a formula shown as its source), which
        takes the theme's (`Theme.inline_code_run_scale`: 0.0 unless the
        theme says otherwise, and always on a monospace base).
        """
        key = (kind, emphasis)
        found = self._roles.get(key)
        if found is None:
            scale = self._theme.inline_code_run_scale(kind) if emphasis.code else 0.0
            found = self._roles[key] = (face_role(self._theme.face_for(kind, emphasis)), scale)
        return found

    # -- inline -----------------------------------------------------------

    def _inline(self, kind: BlockKind, tokens: Any, style: BlockStyle) -> _Run:
        run = _Run(face_role(style.font.face), self._converter_spaces)
        emphasis = _PLAIN
        stack: list[Emphasis] = []
        # With `show_link_destinations`: each open link's target, its title,
        # and the text read inside it so far.
        shown: list[tuple[str, str, list[str]]] = []
        for token in tokens or ():
            match token.type:
                case "text":
                    run.text(str(token.content), *self._role(kind, emphasis))
                    for entry in shown:
                        entry[2].append(str(token.content))
                case "code_inline":
                    run.text(str(token.content), *self._role(kind, _CODE))
                    for entry in shown:
                        entry[2].append(str(token.content))
                case "strong_open":
                    stack.append(emphasis)
                    emphasis = emphasis.with_(bold=True)
                case "em_open":
                    stack.append(emphasis)
                    emphasis = emphasis.with_(italic=True)
                case "strong_close" | "em_close":
                    emphasis = stack.pop() if stack else _PLAIN
                case "link_open":
                    target = str(token.attrs.get("href", ""))
                    run.link_open(target)
                    if self._destinations:
                        shown.append((target, str(token.attrs.get("title") or ""), []))
                case "link_close":
                    if shown:
                        # Before the link is closed, so that its range, and
                        # with it the tag and the click, covers the destination.
                        target, title, said = shown.pop()
                        if title or not _names_itself("".join(said), target):
                            font, scale = self._role(kind, emphasis)
                            if not run.after_white_space():
                                run.space(font, scale)
                            run.text(
                                f'({target} "{title}")' if title else f"({target})", font, scale
                            )
                    run.link_close()
                case "softbreak":
                    run.space(*self._role(kind, emphasis))
                case "hardbreak":
                    run.hard_break(style.align)
                case "math_inline":
                    self._formula(run, kind, str(token.content), token.markup == "$$")
                case _:
                    # Images, raw HTML: dropped with their text, as there.
                    # (A parser built for `ReaderOptions.html_as_text` or
                    # `images_as_text` makes no such token.)
                    continue
        return run

    def _formula(self, run: _Run, kind: BlockKind, source: str, display: bool) -> None:
        """
        A closed formula: a Formula run, or its source with its dollars in the code face.
        """
        refused = not source
        if not refused and self._refuses is not None:
            refused = bool(self._refuses(source, display, self._theme.style(kind).font.size))
        if not refused:
            run.formula(source, display)
            return
        marker = "$$" if display else "$"
        # Before the range is opened: in a block set centred or ragged left a
        # hard break's newline is written when the next node arrives (`_Run`),
        # and read first, `run.pos` is one short of where the dollar will be.
        run._node()
        start = run.pos
        run.text(f"{marker}{source}{marker}", *self._role(kind, _CODE))
        run.formulas.append(FormulaRange(start, run.pos, source, display, "refused"))

    # -- blocks -----------------------------------------------------------

    def _paragraph_kind(self) -> BlockKind:
        if self._quote_depth:
            return BlockKind.QUOTE
        if self._lists:
            return self._lists[-1].kind
        return BlockKind.PARAGRAPH

    def _take_marker(self) -> str:
        marker, self._marker = self._marker, ""
        return marker

    def _text(self, kind: BlockKind, style: BlockStyle, run: _Run) -> None:
        text, runs, links = run.finish()
        self._blocks.append(
            MarkdownText(
                kind=kind,
                style=style,
                text=text,
                runs=runs,
                links=links,
                marker=self._take_marker(),
                left_indent=self._indent + style.left_indent,
                quote_depth=self._quote_depth,
                hard_breaks=run.hard,
                formulas=tuple(run.formulas),
            )
        )

    def _display_math(self, source: str, closed: bool) -> None:
        kind = self._paragraph_kind()
        style = replace(self._theme.style(kind), align=Align.CENTER, first_line_indent=0)
        run = _Run(face_role(style.font.face), self._converter_spaces)
        source = " ".join(source.split())
        if closed:
            self._formula(run, kind, source, True)
        else:
            run.text(f"$${source}", *self._role(kind, _CODE))
            run.formulas.append(FormulaRange(0, run.pos, source, True, "unclosed"))
        self._text(kind, style, run)

    def _code(self, source: str, language: str) -> None:
        style = self._theme.style(BlockKind.CODE)
        indent = self._indent + style.left_indent
        lines = source.split("\n")
        while lines and not lines[-1]:
            lines.pop()
        if self._fence_info and language:
            self._blocks.append(_fence_info(style, language, indent))
            style = _under_info(style)
        self._blocks.append(
            MarkdownCode(style=style, text="\n".join(lines), language=language, left_indent=indent)
        )

    def _end_list(self) -> None:
        """
        The outermost list has closed: its last item takes the theme's space after a list.

        Only with `Theme.space_after_list`, and only when what the list ends
        on is a list item's text (a fence or a table that ends an item keeps
        its own space, and text quoted inside a list is a quote's).
        """
        if self._list_end is None or not self._blocks:
            return
        last = self._blocks[-1]
        if (
            isinstance(last, MarkdownText)
            and last.kind in (BlockKind.BULLET_ITEM, BlockKind.ORDERED_ITEM)
            and last.style.space_below != self._list_end
        ):
            self._blocks[-1] = replace(last, style=replace(last.style, space_below=self._list_end))

    def _table(self, tokens: list[Any], start: int) -> int:
        style = self._theme.style(BlockKind.TABLE)
        header: list[MarkdownCell] = []
        rows: list[tuple[MarkdownCell, ...]] = []
        aligns: list[ColumnAlign] = []
        row: list[MarkdownCell] = []
        in_header = False
        is_header_cell = False
        index = start + 1
        while index < len(tokens) and tokens[index].type != "table_close":
            token = tokens[index]
            match token.type:
                case "thead_open":
                    in_header = True
                case "thead_close":
                    in_header = False
                case "tr_open":
                    row = []
                case "tr_close":
                    if in_header:
                        header = row
                    else:
                        rows.append(tuple(row))
                case "th_open" | "td_open":
                    is_header_cell = token.type == "th_open"
                    if in_header:
                        aligns.append(
                            _COLUMN_ALIGNS.get(str(token.attrs.get("style", "")), ColumnAlign.LEFT)
                        )
                case "inline":
                    run = self._inline(BlockKind.TABLE, token.children, style)
                    text, runs, links = run.finish()
                    row.append(
                        MarkdownCell(
                            text=text,
                            runs=runs,
                            links=links,
                            header=is_header_cell,
                            hard_breaks=run.hard,
                            formulas=tuple(run.formulas),
                        )
                    )
            index += 1
        self._blocks.append(
            MarkdownTable(
                style=style,
                header=tuple(header),
                rows=tuple(rows),
                aligns=tuple(aligns),
                left_indent=self._indent + style.left_indent,
            )
        )
        return index + 1

    # -- the walk ---------------------------------------------------------

    def read(
        self,
        tokens: list[Any],
        source: str,
        lines: list[int] | None = None,
        *,
        first: int = 0,
        top: SourceSpan | None = None,
        mark: int = -1,
    ) -> MarkdownDocument:
        """
        `tokens` as blocks, with where each came from.

        `first`, `top` and `mark` are `imscribe.markdown._Converter._walk`'s,
        for a stream that picks a walk up part of the way through a list or
        a quote: the tokens before `first` are taken as handled, by a reader
        whose nesting was put back with `_restore`, and `top` is the
        top-level block the walk is then inside. `mark` is a token index at
        which to note how many blocks have been emitted and what the nesting
        is (`_marked`), so that a later walk can be picked up there in turn.
        """
        if lines is None:
            lines = _line_starts(source)
        index = first
        while index < len(tokens):
            if index == mark:
                self._marked = (len(self._blocks), self._snapshot())
            token = tokens[index]
            if token.level == 0 and token.map:
                top = _span(token.map, lines, source)
            emitted = len(self._blocks)
            own = _span(token.map, lines, source) if token.map else top
            if token.type == "heading_open":
                self._heading_span = own if token.map else None
            elif token.type == "inline" and self._heading_span is not None:
                own = self._heading_span
            self._handle(tokens, index)
            if own is not None:
                for _ in range(len(self._blocks) - emitted):
                    self._sources.append(BlockSource(span=own, top=top or own))
            index = self._next
        if mark == len(tokens):
            self._marked = (len(self._blocks), self._snapshot())
        return MarkdownDocument(blocks=tuple(self._blocks), sources=tuple(self._sources))

    def _snapshot(self) -> _Nesting:
        return _Nesting(
            lists=tuple((state.kind, state.number) for state in self._lists),
            quote_depth=self._quote_depth,
            indent=self._indent,
            marker=self._marker,
        )

    def _restore(self, state: _Nesting) -> None:
        self._lists = [_List(kind, number) for kind, number in state.lists]
        self._quote_depth = state.quote_depth
        self._indent = state.indent
        self._marker = state.marker

    def _handle(self, tokens: list[Any], index: int) -> None:
        token = tokens[index]
        self._next = index + 1
        theme = self._theme
        match token.type:
            case "heading_open":
                self._heading = _HEADING_KINDS.get(str(token.tag), BlockKind.HEADING_3)
            case "heading_close":
                self._heading = None
                self._heading_span = None
            case "inline":
                kind = self._heading or self._paragraph_kind()
                style = theme.style(kind)
                self._text(kind, style, self._inline(kind, token.children, style))
            case "bullet_list_open":
                self._lists.append(_List(BlockKind.BULLET_ITEM))
                self._indent += theme.list_indent
            case "ordered_list_open":
                self._lists.append(_List(BlockKind.ORDERED_ITEM, int(token.attrs.get("start", 1))))
                self._indent += theme.list_indent
            case "bullet_list_close" | "ordered_list_close":
                if self._lists:
                    self._lists.pop()
                    self._indent -= theme.list_indent
                    if not self._lists:
                        self._end_list()
            case "list_item_open":
                self._marker = self._next_marker()
            case "list_item_close":
                self._marker = ""
            case "blockquote_open":
                self._quote_depth += 1
                self._indent += theme.quote_indent
            case "blockquote_close":
                self._quote_depth -= 1
                self._indent -= theme.quote_indent
            case "fence" | "code_block":
                self._code(str(token.content), str(token.info).strip())
            case "math_block":
                self._display_math(str(token.content), bool((token.meta or {}).get("closed", True)))
            case "hr":
                self._blocks.append(
                    MarkdownRule(
                        style=theme.style(BlockKind.RULE),
                        thickness=theme.rule_thickness,
                        left_indent=self._indent,
                    )
                )
            case "table_open":
                self._next = self._table(tokens, index)

    def _next_marker(self) -> str:
        if not self._lists:
            return _BULLET
        state = self._lists[-1]
        if state.kind is BlockKind.BULLET_ITEM:
            return _BULLET
        text = f"{state.number}."
        state.number += 1
        return text


_PLAIN = Emphasis()
_CODE = Emphasis(code=True)

_HEADING_KINDS = {f"h{level}": BlockKind[f"HEADING_{level}"] for level in range(1, 7)}


def _fence_info(style: BlockStyle, info: str, indent: Scaled) -> MarkdownText:
    """
    The block `ReaderOptions.show_fence_info` puts before a fence: its info string, as text.

    `style` is the code block's own, as the theme has it, and `indent` the
    code block's. The one place this block is made, for a settled parse and
    for a stream's fence alike.
    """
    return MarkdownText(
        kind=BlockKind.CODE,
        style=replace(style, space_below=0),
        text=" ".join(info.split()),
        left_indent=indent,
    )


def _under_info(style: BlockStyle) -> BlockStyle:
    """
    The style of a code block that follows its info string: no space between the two.
    """
    return replace(style, space_above=0)


def parse_markdown(
    source: str,
    theme: Theme,
    *,
    references: bool = True,
    math: bool = False,
    more_may_follow: bool = False,
    refuses: Refuses | None = None,
    converter_spaces: bool = False,
    reader: ReaderOptions | None = None,
) -> MarkdownDocument:
    """
    Markdown source as blocks of text and runs, with where each came from.

    `references` and `more_may_follow` are `imscribe.markdown.build_document`'s,
    and so is the parser. `math=True` is what a builder is there: it turns on
    `$...$` and `$$`. `refuses` is asked about each closed formula; the module
    docstring has what is done with the answer. It is not called with math
    off. `converter_spaces=True` gives the runs `imscribe.typesetter.Converter`
    gives ("The space after a run" in the module docstring).

    `reader` is a `ReaderOptions`: what of the source a CommonMark reader
    would hide and this host wants set. `None` is `ReaderOptions()`, the
    reading there has always been. Anything else is a `TypeError` here.
    """
    options = reader_options(reader)
    tokens = _parse(_parser_for(references, math, options), source, more_may_follow and math)
    return _Reader(theme, refuses if math else None, converter_spaces, options).read(tokens, source)


def _parser_for(references: bool, math: bool, reader: ReaderOptions) -> Any:
    """
    The parser for the two switches and a host's reader options: one object per combination.

    `show_link_destinations` and `show_fence_info` are not a parser's
    business (`_Reader` writes what they show), so two options that differ
    only in those share a parser.
    """
    return _reader_parser(
        references,
        math,
        not reader.html_as_text,
        not reader.images_as_text,
        reader.keep_glob_stars,
        reader.backslashes_as_written,
    )


# ---------------------------------------------------------------------------
# White space, as the library will set it
# ---------------------------------------------------------------------------

# Anything in a text block's `str` that the library will not set as written:
# white space at either end, two white-space characters together, or one that
# is not a plain space (a newline is looked at apart: `text_as_set`).
_NOT_AS_SET = re.compile(r"\A\s|\s\Z|\s\s|[^\S \n]")
_WHITE_SPACE = re.compile(r"\s+")
_LINE_END = re.compile(r"\r\n|\r|\n")
_OPAQUE = RUN_FORMULA | RUN_DISPLAY_FORMULA


def text_as_set(block: MarkdownText) -> MarkdownText:
    r"""
    `block` with its white space written as the library sets it; `block` itself if it is already.

    imtypeset sets a text block's white space by one rule whatever it is
    handed (its header, at `SetParagraphText`: "runs of white space are one
    space wherever they fall, across runs too, and white space at either end
    is dropped"), and no flag keeps it. So `a   b` handed over is drawn and
    copied as `a b`, and a description that still said `a   b` has
    `Description.texts`, and a view's `texts`, disagree with the screen
    (pptmstr's P28). `imscribe.ui.typeset_view.TypesetView` describes the
    blocks it is HANDED AS BLOCKS through this ("White space in a text
    block" there); `MarkdownConverter` does not call it, and what
    `parse_markdown` and a stream write is described as it always was.

    The rule, measured against the library (`tests/test_host_requests_2.py`
    holds it, character by character, for everything `str.isspace` is true
    of): a run of white space is one space; at either end of the text it is
    nothing; and in a block with `hard_breaks` a run that holds line ends
    (`\r\n`, `\r` or `\n`, each once) is that many `\n` and no space, because
    the library ends the line at each. A run flagged as a formula is its
    source and is left exactly as written. Runs, links and formulas keep the
    characters they covered; one left covering nothing is dropped.
    """
    text = block.text
    if not _NOT_AS_SET.search(text) and (block.hard_breaks or "\n" not in text):
        return block
    opaque = [(run.start, run.end) for run in block.runs if run.flags & _OPAQUE]
    parts: list[str] = []
    # `moved[i]` is where offset `i` of the text is in the new one.
    moved = [0] * (len(text) + 1)
    out = 0
    at = 0

    def keep(end: int) -> None:
        nonlocal out, at
        parts.append(text[at:end])
        for index in range(at, end):
            moved[index] = out + index - at
        out += end - at
        at = end

    def plain(end: int) -> None:
        nonlocal out, at
        for match in _WHITE_SPACE.finditer(text, at, end):
            keep(match.start())
            written = " "
            if match.start() == 0 or match.end() == len(text):
                written = ""
            elif block.hard_breaks:
                written = "\n" * len(_LINE_END.findall(match.group())) or " "
            parts.append(written)
            for index in range(match.start(), match.end()):
                moved[index] = out + min(index - match.start(), len(written))
            out += len(written)
            at = match.end()
        keep(end)

    for start, end in opaque:
        if at <= start <= end <= len(text):
            plain(start)
            keep(end)
    plain(len(text))
    moved[len(text)] = out
    written_text = "".join(parts)
    if written_text == text:
        return block

    def clip(offset: int) -> int:
        return moved[min(max(offset, 0), len(text))]

    return replace(
        block,
        text=written_text,
        runs=tuple(
            run._replace(start=clip(run.start), end=clip(run.end))
            for run in block.runs
            if clip(run.end) > clip(run.start)
        ),
        links=tuple(
            LinkRange(clip(start), clip(end), target)
            for start, end, target in block.links
            if clip(end) > clip(start)
        ),
        formulas=tuple(
            formula._replace(start=clip(formula.start), end=clip(formula.end))
            for formula in block.formulas
            if clip(formula.end) > clip(formula.start)
        ),
    )


# ---------------------------------------------------------------------------
# Blocks to a description
# ---------------------------------------------------------------------------


class MarkdownConverter:
    """
    `MarkdownBlock`s to block descriptions, for one theme.

    The same object `imscribe.typesetter.Converter` is, over blocks that
    already hold their text: a style table and a link table that outlive a
    call, for the reasons given there. `Description.styles[n:]` are the
    styles a call added, where `n` was `len(converter.styles)` before it; a
    tag is 1 + the index of its URL in `targets`.
    """

    def __init__(self, theme: Theme, *, link_color: int = 0) -> None:
        self.theme = theme
        self.link_color = link_color
        self.body: Scaled = theme.style(BlockKind.PARAGRAPH).font.size
        self.styles: list[StyleDescription] = []
        self.targets: list[str] = []
        self._style_index: dict[BlockStyle, int] = {}
        self._tags: dict[str, int] = {}

    def px(self, length: Scaled) -> float:
        """
        A scaled-point length in the theme's pixels, unrounded.
        """
        return px_from_sp(length, self.theme.px_per_inch)

    def link_target(self, tag: int) -> str | None:
        """
        The URL a run's tag stands for, or `None` for 0 and for a number no link was given.
        """
        if 1 <= tag <= len(self.targets):
            return self.targets[tag - 1]
        return None

    def style(self, style: BlockStyle) -> int:
        """
        The index of `style` in `styles`, added if this is the first block set in it.
        """
        found = self._style_index.get(style)
        if found is None:
            found = self._style_index[style] = len(self.styles)
            size = style.font.size
            self.styles.append(
                StyleDescription(
                    Face=face_role(style.font.face),
                    Scale=size / self.body,
                    LineHeight=style.leading / size,
                    Align=align_code(style.align),
                    FirstLineIndent=self.px(style.first_line_indent),
                    SpaceAbove=self.px(style.space_above),
                    SpaceBelow=self.px(style.space_below),
                    MarkerGap=self.px(self.theme.marker_gap),
                )
            )
        return found

    def _tag(self, target: str) -> int:
        tag = self._tags.get(target)
        if tag is None:
            self.targets.append(target)
            tag = self._tags[target] = len(self.targets)
        return tag

    def describe(self, blocks: Sequence[object], base: int = 0) -> Description:
        """
        `blocks` as descriptions; `base` is the index the first will have in the document.

        One description for each block given. Anything that is not a
        `MarkdownBlock` becomes an empty Host block and a misfit, naming the
        paragraph style (added to the table if no block has used it).
        """
        out: list[BlockDescription] = []
        links: list[LinkRow] = []
        tables: list[int] = []
        misfits: collections.Counter[str] = collections.Counter()
        kinds: collections.Counter[str] = collections.Counter()
        for block in blocks:
            at = base + len(out)
            if isinstance(block, MarkdownText):
                out.append(self._text(block, at, links, kinds))
            elif isinstance(block, MarkdownCode):
                kinds["CodeBlock"] += 1
                kinds["code lines"] += block.text.count("\n") + 1 if block.text else 0
                if block.language:
                    kinds[
                        "code blocks naming a language "
                        "(kept by the host; imscribe does not draw it)"
                    ] += 1
                out.append(
                    BlockDescription(
                        kind=KIND_CODE,
                        text=block.text,
                        style=self.style(block.style),
                        left_indent=self.px(block.left_indent),
                    )
                )
            elif isinstance(block, MarkdownRule):
                kinds["RuleBlock"] += 1
                out.append(
                    BlockDescription(
                        kind=KIND_RULE,
                        style=self.style(block.style),
                        left_indent=self.px(block.left_indent),
                        extent=max(1.0, self.px(block.thickness)),
                    )
                )
            elif isinstance(block, MarkdownTable):
                tables.append(at)
                out.append(self._table(block, at, links, kinds))
            else:
                misfits[MISFIT_BLOCK.format(name=type(block).__name__)] += 1
                out.append(
                    BlockDescription(
                        kind=KIND_HOST,
                        style=self.style(self.theme.style(BlockKind.PARAGRAPH)),
                        extent=UNKNOWN_BLOCK_EXTENT_PX,
                    )
                )
        texts = [block.text for block in out]
        return Description(out, list(self.styles), links, tables, texts, misfits, kinds)

    def _table(
        self,
        block: MarkdownTable,
        at: int,
        links: list[LinkRow],
        kinds: collections.Counter[str],
    ) -> BlockDescription:
        """
        A table as one block: its cells with the link tags laid over their runs, and its columns.
        """
        kinds["TableBlock"] += 1
        given = [block.header, *block.rows] if block.header else list(block.rows)
        rows: list[tuple[CellDescription, ...]] = []
        for row in given:
            cells: list[CellDescription] = []
            for one in row:
                kinds["table cells"] += 1
                if one.hard_breaks:
                    kinds["table cells with a hard break (white space to the library)"] += 1
                for formula in one.formulas:
                    if formula.state == "set":
                        kinds["formulas set (an explicit Formula run)"] += 1
                    elif formula.state == "unclosed":
                        kinds["display formulas not closed yet (source so far)"] += 1
                    else:
                        kinds[
                            "formulas refused by imscribe's builder "
                            "(their source, in the code face)"
                        ] += 1
                runs: Sequence[RunDescription] = one.runs
                if one.links:
                    tagged = [(start, end, self._tag(target)) for start, end, target in one.links]
                    runs = with_tags(runs, tagged, self.link_color)
                cells.append(CellDescription(one.text, tuple(runs)))
            rows.append(tuple(cells))
        for spans, row in zip(cell_spans(rows), given, strict=True):
            for (base, _), one in zip(spans, row, strict=False):
                for start, end, target in one.links:
                    links.append(LinkRow(at, base + start, base + end, self._tag(target), target))
                    kinds["links (Run.tag into a host table)"] += 1
        aligns = column_aligns(block.aligns)
        columns: tuple[ColumnDescription, ...]
        if block.widths and len(block.widths) == len(aligns):
            columns = tuple(
                ColumnDescription(align, width=self.px(width))
                for align, width in zip(aligns, block.widths, strict=True)
            )
        elif block.shares and len(block.shares) == len(aligns):
            columns = tuple(
                ColumnDescription(align, share=float(share))
                for align, share in zip(aligns, block.shares, strict=True)
            )
        else:
            columns = tuple(ColumnDescription(align) for align in aligns)
        return BlockDescription(
            kind=KIND_TABLE,
            text=table_text([cell.text for cell in row] for row in rows),
            style=self.style(block.style),
            left_indent=self.px(block.left_indent),
            flags=BLOCK_TABLE_HEADER if block.header else 0,
            rows=tuple(rows),
            columns=columns,
        )

    def _text(
        self,
        block: MarkdownText,
        at: int,
        links: list[LinkRow],
        kinds: collections.Counter[str],
    ) -> BlockDescription:
        name = block.kind.name
        kinds[f"TextBlock {name}"] += 1
        for formula in block.formulas:
            if formula.state == "set":
                kinds["formulas set (an explicit Formula run)"] += 1
            elif formula.state == "unclosed":
                kinds["display formulas not closed yet (source so far)"] += 1
            else:
                kinds[
                    "formulas refused by imscribe's builder " "(their source, in the code face)"
                ] += 1
        if block.style.first_line_indent:
            kinds["first-line indent boxes (to BlockStyle.FirstLineIndent)"] += 1
        runs: Sequence[RunDescription] = block.runs
        if block.links:
            tagged: list[tuple[int, int, int]] = []
            for start, end, target in block.links:
                tag = self._tag(target)
                links.append(LinkRow(at, start, end, tag, target))
                tagged.append((start, end, tag))
                kinds["links (Run.tag into a host table)"] += 1
            runs = with_tags(runs, tagged, self.link_color)
        if block.marker:
            kinds["list markers"] += 1
        if name.startswith("HEADING"):
            kind, level = KIND_HEADING, int(name[-1])
        elif name.endswith("_ITEM"):
            kind, level = KIND_LIST_ITEM, 0
        else:
            kind, level = KIND_PARAGRAPH, 0
        if block.quote_depth > 1:
            kinds["blocks quoted more than one deep"] += 1
        if block.style.left_indent:
            kinds["blocks whose style has a left indent of its own"] += 1
        return BlockDescription(
            kind=kind,
            text=block.text,
            runs=tuple(runs),
            marker=block.marker,
            style=self.style(block.style),
            left_indent=self.px(block.left_indent),
            quote_depth=block.quote_depth,
            flags=BLOCK_HARD_BREAKS if block.hard_breaks else 0,
            level=level,
        )


def describe_markdown(
    source: str,
    theme: Theme,
    *,
    link_color: int = 0,
    references: bool = True,
    math: bool = False,
    more_may_follow: bool = False,
    refuses: Refuses | None = None,
    converter_spaces: bool = False,
    reader: ReaderOptions | None = None,
) -> Description:
    """
    `MarkdownConverter(theme).describe(parse_markdown(source, theme, ...).blocks)`.

    For a document described once. The converter is dropped, so there is no
    `link_target`: read `Description.links`.
    """
    document = parse_markdown(
        source,
        theme,
        references=references,
        math=math,
        more_may_follow=more_may_follow,
        refuses=refuses,
        converter_spaces=converter_spaces,
        reader=reader,
    )
    return MarkdownConverter(theme, link_color=link_color).describe(document.blocks)


# ---------------------------------------------------------------------------
# Where a long list or quote can be re-read from: `imscribe.markdown`'s, copied
# ---------------------------------------------------------------------------
#
# Everything from here to the next rule is `imscribe.markdown`'s `_Resume`,
# `_opens`, `_resume_point`, `_opener` and `_step_over` and the four constants
# they read, COPIED BY LINE RANGE, not retyped, docstrings and all. They read
# tokens and strings and make no node, but they live in a module that imports
# the layout core, which this one must not load; `imscribe.markdown` was not
# this task's file to cut them out of (T3-A2; the lead was told). The right
# home is `imscribe.markdown_rules`, with both modules importing them, and
# until then `tests/test_typeset_markdown.py` holds the source of each
# function here equal to the source of the one there, so neither can drift.
# When `imscribe.markdown` goes with the old core, these are the survivors.


@dataclass(frozen=True, slots=True)
class _Resume:
    r"""
    A line inside an unfinished container from which its source can be parsed alone.

    For `imscribe.stream`, and the whole of what lets it stop re-reading a long
    list every time the list grows. `_resume_point` has the argument; this is
    what it returns.

    `line` is a line of the source the tokens came from. `opener` is one line
    of markdown, newline included, that puts a parser where the real one was at
    the start of that line: the same quotes and list items open, at the same
    columns, with a thematic break as the only thing in the innermost. So
    `opener + source_from_line` parses to the containers, the break, and then
    exactly what the whole source has from `line` on. `shape` is the type and
    markup of each token the opener must produce, break last, which is what a
    caller checks before believing that (`_opens`). `mark` is the index, among
    the tokens `_resume_point` was given, of the first one that the lines from
    `line` on produce: the blocks emitted before it are settled, and the
    converter's state there is the state to resume with.
    """

    line: int
    opener: str
    shape: tuple[tuple[str, str], ...]
    mark: int


_CONTAINER_OPENS = frozenset(
    {"bullet_list_open", "ordered_list_open", "list_item_open", "blockquote_open"}
)
_CONTAINER_CLOSES = frozenset(
    {"bullet_list_close", "ordered_list_close", "list_item_close", "blockquote_close"}
)

_ITEM_OPENER = re.compile(r"( {0,3})(\d{1,9}[.)]|[-+*])( *)")
_QUOTE_OPENER = re.compile(r" {0,3}> ?")


def _opens(tokens: list[Any], shape: tuple[tuple[str, str], ...]) -> bool:
    """
    Whether `tokens` begin with exactly the containers and the break an opener is for.

    The check that an opener was read as what it was written to be. When this
    is false the caller parses the whole source instead, which is always
    right.

    **No source is known that makes it false.** The rule that could take an
    opener for something else is the table rule, which runs before every other
    and claims a first line whose second looks like a delimiter row; but it
    also needs a pipe in that first line (`markdown_it/rules_block/table.py`,
    `if "|" not in lineText`), and no opener has one. The fuzz runs recorded
    in `.concerns/AF-streamcost--builder--result.md` refused none. It stays
    because it is six comparisons and what it guards against is silent: tokens
    converted from the wrong nesting.
    """
    count = len(shape)
    if len(tokens) < count:
        return False
    for level, (kind, markup) in enumerate(shape[:-1]):
        token = tokens[level]
        if token.type != kind or token.markup != markup or token.level != level:
            return False
    last = tokens[count - 1]
    return bool(
        last.type == "hr" and last.level == count - 1 and last.map and list(last.map) == [0, 1]
    )


def _resume_point(
    tokens: list[Any], source: str, starts: list[int], skip: int = 0
) -> _Resume | None:
    r"""
    The latest line of `source` from which its unfinished first block can be re-read alone.

    `source` must end at a line end, and `tokens` are its tokens. `skip` is how
    many of them at the front are an opener's, when `source` itself began with
    one. `None` when the source's first top-level block is not a list or a
    quote that everything after it is still inside, or when no opener could be
    written for where it has got to.

    **What this is for.** `imscribe.stream` commits a top-level block when the
    next one starts, and until then re-parses it whole on every read. A list is
    one top-level block however long, and so is a block quote (measured before
    this existed, mean cost of a four-character piece near the end: 43 ms for a
    list of 300 items, 16 ms for a quote of 150 paragraphs). What has been
    converted of such a block cannot be *committed* early, because its `top`
    span is still growing; but it need not be parsed or converted again.

    **The line.** The last block-level token that is a direct child of its
    container -- a paragraph, a heading, a fence, a table, a rule, a raw HTML
    block -- starts on some line. Everything emitted before that line is
    settled by the same argument the stream's own boundary rests on, applied
    inside the container: block structure is decided line by line, a finished
    line cannot be taken back, and a later line can extend, convert or split
    only the block being written. So the source is re-read from that line.
    When the last such token is a fence that has met its closing line, the
    line is the one *after* the closing line: nothing reaches back into a
    closed fence, and without this every piece of the line after a long code
    block inside a list item would re-read the whole of it.

    **The opener.** Re-reading from a line in the middle of a container needs
    the container open. The lines themselves cannot do it: the second paragraph
    of a list item, read alone, is an indented paragraph or a code block (the
    construct `docs/adoption-plan.md` rules a blank-line scanner out with). So
    one line is written in front that opens the same containers at the same
    columns, each list item by its own marker and padding, each quote by `> `,
    with a thematic break as the innermost's content: a break because it is a
    whole block in three characters that nothing after it can continue,
    extend or attach to. markdown-it itself treats the columns a marker covers
    as spaces once the item is open (`StateBlock.getLines`: "patched tShift
    masked characters to look like spaces"), so a later line of the item sees
    the same thing above it either way. Where the line to resume at starts a
    *new item* of a list, the list is opened with a marker padded by four
    spaces: a sibling item may be indented up to three columns, and an opener
    padded by one would take such a line as its own content (found by reading
    the list rule, not by a failing test).

    **What is inferred and what is checked.** That the opener leaves the parser
    in the state the real source did is an argument from reading
    `markdown_it/rules_block/list.py`, `blockquote.py` and `state_block.py` in
    the installed 4.2.0, not a theorem. Two things stand behind it. A caller
    verifies with `_opens` that the opener was read as the containers it names
    before using anything that follows, and falls back to the whole parse when
    not. And the result is compared with one parse of the whole source: from
    every line of sixteen nested sources in `tests/test_markdown.py`, and after
    every piece of the stream's corpus in `tests/test_stream.py`. **That
    comparison, run over generated documents, found two mistakes in the first
    version** (an inner item's indent written where the outer marker's padding
    absorbed it, in `_opener`; and the unfinished line under a quoted fence,
    in `_leading_fence`), so it can fail, and a construct it has not been
    shown is untested rather than safe.
    Tabs are not reasoned about at all: an opening line with a tab in it gets
    no opener, and the block is re-parsed whole as before.
    """
    stack: list[int] = []
    leaf = -1
    chain: tuple[int, ...] = ()
    for index, token in enumerate(tokens):
        kind = token.type
        if kind in _CONTAINER_OPENS:
            stack.append(index)
        elif kind in _CONTAINER_CLOSES:
            stack.pop()
        elif index >= skip and token.nesting >= 0 and token.map and token.level == len(stack):
            leaf = index
            chain = tuple(stack)
    if leaf < 0 or not chain or chain[0] != 0 or int(tokens[0].map[0]) != 0:
        return None
    token = tokens[leaf]
    begin, end = int(token.map[0]), int(token.map[1])
    if token.type == "fence" and end - begin > str(token.content).count("\n") + 1:
        line, mark, spine = end, leaf + 1, chain
    else:
        line = begin
        depth = 0
        while depth < len(chain) and int(tokens[chain[depth]].map[0]) < line:
            depth += 1
        mark = chain[depth] if depth < len(chain) else leaf
        spine = chain[:depth]
    if not spine:
        return None
    written = _opener(tokens, spine, source, starts)
    if written is None:
        return None
    opener, shape = written
    return _Resume(line=line, opener=opener, shape=shape, mark=mark)


def _opener(
    tokens: list[Any], spine: tuple[int, ...], source: str, starts: list[int]
) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    """
    One line that opens the containers `spine` indexes, and the tokens it should give.

    Each list item's marker, indent and padding are read off the line the item
    opens on, after stepping over what the containers outside it put on that
    line: the same text when they open on that line too, their continuation --
    an item's width in spaces, a quote's `>` -- when they opened earlier. A
    list at the end of the spine with no item is one about to take a new item
    (`_resume_point` says why it is padded by four). `None` whenever a line is
    not laid out the way this expects, tabs included.
    """
    pieces: list[str] = []
    shape: list[tuple[str, str]] = []
    widths: list[int | None] = []
    at_line, at = -1, 0
    marker = ""
    index = 0
    while index < len(spine):
        token = tokens[spine[index]]
        if token.type == "blockquote_open":
            line = int(token.map[0])
            text = source[starts[line] : starts[line + 1]].rstrip("\n")
            position = at if line == at_line else _step_over(text, widths)
            found = None if position is None else _QUOTE_OPENER.match(text, position)
            if found is None or "\t" in text:
                return None
            pieces.append("> ")
            shape.append(("blockquote_open", ">"))
            widths.append(None)
            at_line, at = line, found.end()
            index += 1
            continue
        marker = str(token.markup)
        ordered = token.type == "ordered_list_open"
        shape.append((str(token.type), marker))
        shape.append(("list_item_open", marker))
        if index + 1 == len(spine):
            pieces.append(("1" + marker if ordered else marker) + "    ")
            break
        item = tokens[spine[index + 1]]
        line = int(item.map[0])
        text = source[starts[line] : starts[line + 1]].rstrip("\n")
        position = at if line == at_line else _step_over(text, widths)
        found = None if position is None else _ITEM_OPENER.match(text, position)
        if found is None or "\t" in text or found[2][-1] != marker:
            return None
        if found[2][0].isdigit() != ordered:
            return None
        gap = len(found[3])
        # markdown-it's own rule for where an item's content starts: after the
        # spaces that follow the marker, unless the line ends there or there
        # are more than four, and then after one.
        padding = 1 if found.end() == len(text) or gap > 4 else gap
        if not padding:
            return None
        width = len(found[1]) + len(found[2]) + padding
        indent = found[1]
        if indent and widths and widths[-1] is not None:
            # This item is indented inside another item, on a line of its own.
            # Written straight after that item's marker the indent would be
            # read as more of *its* padding and move its content column
            # (measured: `-` then a nested ` 2.` came back as an outer item
            # one column wider, and a later line indented for the real one
            # fell out of it). Only the column this item's content starts at
            # matters to what follows, so the indent goes after the marker
            # instead -- when that still leaves four spaces or fewer.
            padding += len(indent)
            indent = ""
            if padding > 4:
                return None
        pieces.append(indent + found[2] + " " * padding)
        widths.append(width)
        at_line, at = line, min(found.start() + width, len(text))
        index += 2
    rule = "---" if marker == "*" else "***"
    shape.append(("hr", rule))
    return "".join(pieces) + rule + "\n", tuple(shape)


def _step_over(text: str, widths: list[int | None]) -> int | None:
    """
    Where in `text` the content of containers opened on earlier lines begins.

    `widths` has one entry per container, outermost first: the columns a list
    item's content is indented by, or `None` for a quote. `None` when the line
    does not carry one of them.
    """
    position = 0
    for width in widths:
        if width is None:
            found = _QUOTE_OPENER.match(text, position)
            if found is None:
                return None
            position = found.end()
        else:
            if text[position : position + width] != " " * width:
                return None
            position += width
    return position


# ---------------------------------------------------------------------------
# A source that arrives a piece at a time
# ---------------------------------------------------------------------------


_FENCE_OPENER = re.compile(r" {0,3}(?:```|~~~)")
"""
What a tail must start with to be worth asking the parser whether it opens a fence.

A filter and nothing more, as in `imscribe.stream`: it lets through lines that
are not openers and the parser is what says no to those.
"""

_TABLE_DELIMITER = re.compile(r"[ \t|:-]*-[ \t|:-]*\n")
"""
What a tail's second line must look like to be worth asking whether it is a table's.
"""


@dataclass(frozen=True, slots=True)
class _Kept:
    """
    The settled children of the list or quote being written, in one theme.

    `blocks` are the blocks emitted before the line reading resumes at, and
    `state` is the reader's nesting at that line.
    """

    blocks: tuple[MarkdownBlock, ...]
    state: _Nesting


@dataclass(frozen=True, slots=True)
class _Restart:
    """
    Where in the tail a read resumes, when the tail is one long list or quote.

    `imscribe.stream._Restart`. `resume` is `_resume_point`'s answer, and
    `line` and `offset` are its line in the tail's coordinates. `spans` are
    the own spans of the kept blocks in the WHOLE source's coordinates (they
    are final). `commit` and `live` are the kept blocks in the stream's two
    themes, and the same object when those are one theme.

    Valid for as long as the tail starts where it did: `_advance` discards it.
    """

    resume: _Resume
    line: int
    offset: int
    spans: tuple[SourceSpan, ...]
    commit: _Kept
    live: _Kept


@dataclass(frozen=True, slots=True)
class _Parsed:
    """
    One reading of the tail: blocks kept from earlier readings, then fresh ones.

    `kept` and `spans` are parallel and all belong to the top-level block
    `top`; `fresh` and `sources` are parallel and are what the parse itself
    produced. `top` and `sources` are in the tail's coordinates and `spans`
    in the whole source's. With nothing kept, `top` is `None`.
    """

    kept: tuple[MarkdownBlock, ...]
    spans: tuple[SourceSpan, ...]
    top: SourceSpan | None
    fresh: tuple[MarkdownBlock, ...]
    sources: tuple[BlockSource, ...]

    @property
    def blocks(self) -> tuple[MarkdownBlock, ...]:
        return self.kept + self.fresh if self.kept else self.fresh


class _Fence(NamedTuple):
    """
    What `MarkdownStream._fence_at` found: a fence's lines, its info string, whether it ended.
    """

    lines: list[str]
    language: str
    closed: bool


@dataclass(slots=True)
class _LiveFence:
    """
    A top-level fence still being written, and the lines of it already read.

    `imscribe.stream._LiveFence`, at top level only. The tail is this fence
    and nothing else while one of these exists. `prefix` is the opener and
    the first content line as they stand in the tail, sent to the parser in
    front of every new piece. `lines` is every complete content line, tabs
    expanded, blank ones at the end included. `starts` is the offset in the
    tail at which each complete line begins, and last the offset at which
    the next will. `live` and `commit` are the fence with no text in each of
    the stream's two themes, and `live_info` and `commit_info` the block that
    goes before each under `ReaderOptions.show_fence_info` (`None` without it,
    and for a fence that has no info string).
    """

    prefix: str
    lines: list[str]
    starts: list[int]
    live: MarkdownCode
    commit: MarkdownCode
    live_info: MarkdownText | None = None
    commit_info: MarkdownText | None = None


@dataclass(slots=True)
class _LiveTable:
    """
    A top-level table still being written, and the rows of it already read.

    `imscribe.stream._LiveTable`. `prefix` is its header row and its delimiter
    row as they stand in the tail. `rows` is every row whose line has ended,
    in the live theme, and `commit_rows` the same in the theme a block
    commits with: one list when the themes are one. (There the rows are
    shared whatever the themes, because a cell's nodes do not depend on its
    block's alignment; here a cell's TEXT does, at a hard break.) `starts`
    is as in `_LiveFence`. `live` and `commit` are the table with no rows.
    """

    prefix: str
    rows: list[tuple[MarkdownCell, ...]]
    commit_rows: list[tuple[MarkdownCell, ...]]
    starts: list[int]
    live: MarkdownTable
    commit: MarkdownTable


def _content_lines(content: str) -> list[str]:
    r"""
    A fence's content as its lines, blank lines at the end kept.

    One entry for every line, whether or not the last ends in a newline;
    none for the empty string. A tab stays a tab (`MarkdownCode`), and the
    library counts its stop from the start of its own line, so lines read a
    few at a time and put end to end are the lines read together.
    """
    pieces = content.split("\n")
    if not pieces[-1]:
        pieces.pop()
    return pieces


def _filled(
    template: MarkdownCode, lines: list[str], info: MarkdownText | None = None
) -> tuple[MarkdownBlock, ...]:
    """
    `template` with `lines` as its text, less the blank ones at their end, after `info` if any.
    """
    count = len(lines)
    while count and not lines[count - 1]:
        count -= 1
    code = replace(template, text="\n".join(lines[:count]))
    return (code,) if info is None else (info, code)


def _read_tokens(
    tokens: list[Any],
    source: str,
    starts: list[int],
    theme: Theme,
    refuses: Refuses | None,
    converter_spaces: bool,
    *,
    first: int = 0,
    state: _Nesting | None = None,
    mark: int = -1,
    options: ReaderOptions = _AS_COMMONMARK,
) -> tuple[MarkdownDocument, int, _Nesting | None]:
    """
    `tokens` as blocks, optionally from part of the way in, noting the nesting at `mark`.

    `imscribe.markdown._convert`. With `state`, the tokens before `first` are
    an opener's (`_Resume.opener`) and are not read: the walk begins at
    `first` in the nesting `state` records, inside the top-level block the
    first token opens. Returns the document, and how many of its blocks had
    been emitted when the walk reached token `mark`, with the nesting there
    (zero and `None` when it never did).
    """
    reader = _Reader(theme, refuses, converter_spaces, options)
    top: SourceSpan | None = None
    if state is not None:
        reader._restore(state)
        top = _span(tokens[0].map, starts, source)
    document = reader.read(tokens, source, starts, first=first, top=top, mark=mark)
    count, marked = reader._marked
    return document, count, marked


class MarkdownStream:
    r"""
    A document that arrives a piece at a time, as `MarkdownBlock`s.

    `imscribe.stream.StreamDocument`'s contract for a view that reads
    `revision` and `blocks`, and its commit rule, which that module's
    docstring argues and its tests hold: **the tail is parsed up to its last
    newline, every top-level block before the last one is committed, and the
    tail then begins on the last one's first line.** An unfinished line is
    only ever part of the live tail. Link reference definitions are not read
    (`references=False`), for the reason given there, and line ends are
    normalised as text is appended.

    What holds at every read, and `tests/test_typeset_markdown.py` checks
    after every piece: `blocks` equal `parse_markdown(source, theme,
    references=False, math=..., more_may_follow=not closed).blocks`, and a
    committed block is the same object from then on. A block of the live
    tail is kept as the same object too while it compares equal, so a view
    that looks for the first block that `is not` the one it had finds the
    first one that changed.

    `live_theme` is the theme the tail is built with while it is being
    written, for a host that wants what `imscribe.stream.live_theme` gives (a
    justified theme set ragged until a block is finished); a block is built
    with `theme` when it commits. Left out, both are `theme`, and nothing
    about a block changes when it commits.

    **A long block being written is not read from its top at every read.**
    Three of `StreamDocument`'s shortcuts are here, each the same
    construction and each asking the parser, not a reading of the text done
    here, what a line is:

    - a **list or a quote** keeps the children that are finished and reads
      from the line its last child starts on, behind one line that re-opens
      the containers (`_resume_point`, `_Restart`). Nothing commits on the
      strength of it;
    - a **top-level fence** is read a line at a time once its first two
      lines have ended, and commits the moment its closing line ends
      (`_LiveFence`);
    - a **top-level table** is read a row at a time once its header and
      delimiter rows have ended, and commits when a complete line arrives
      that is not a row of it (`_LiveTable`).

    So a fence or a table followed this way commits one line EARLIER than
    the rule above says; `blocks` is the same either way, and `committed` /
    `live` is where it shows. What `StreamDocument` has and this does not: a
    fence INSIDE a list item or a quote is not followed a line at a time. It
    is its container's last child and is read whole, with that child, while
    it is open (once it has closed, reading resumes after it). A table
    inside a container likewise, as there.

    `append` may be called from another thread, as there; everything else is
    the reader's.
    """

    def __init__(
        self,
        theme: Theme,
        *,
        math: bool = False,
        refuses: Refuses | None = None,
        live_theme: Theme | None = None,
        converter_spaces: bool = False,
        reader: ReaderOptions | None = None,
    ) -> None:
        self._theme = theme
        self._live_theme = theme if live_theme is None else live_theme
        self._math = math
        # A host's reader options, checked here, and the one parser every
        # read of this stream goes through: the parser `parse_markdown` is
        # handed for the same options with `references=False`.
        self._reader = reader_options(reader)
        self._parser = _parser_for(False, math, self._reader)
        self._refuses = refuses if math else None
        self._converter_spaces = converter_spaces
        self._head: list[str] = []
        self._head_chars = 0
        self._head_lines = 0
        self._tail = ""
        self._pending: list[str] = []
        self._held = ""
        self._lock = threading.Lock()
        # How much of the tail the last commit decision had read. Whole lines.
        self._examined = 0
        # At most one of these three is set. `_fence` and `_table`: the tail is
        # that one block, followed a line at a time. `_restart`: the tail is
        # one list or quote, and only its end is read again.
        self._fence: _LiveFence | None = None
        self._table: _LiveTable | None = None
        self._restart: _Restart | None = None
        self._committed: tuple[MarkdownBlock, ...] = ()
        self._committed_sources: tuple[BlockSource, ...] = ()
        self._live: tuple[MarkdownBlock, ...] = ()
        # The live blocks' sources are built when first asked for, from
        # `_live_parsed`: see `sources`.
        self._live_sources: tuple[BlockSource, ...] | None = ()
        self._live_parsed: _Parsed | None = None
        self._revision = 0
        self._stale = False
        self._closed = False

    # -- writing ----------------------------------------------------------

    def append(self, text: str) -> None:
        r"""
        Take the next piece of source: any size, cut anywhere. Parsed at the next read.

        `\r\n` and a lone `\r` become `\n`, including a `\r\n` cut between
        two pieces. Raises `ValueError` once the stream is closed.
        """
        with self._lock:
            if self._closed:
                raise ValueError("append() on a closed MarkdownStream")
            if not text:
                return
            text = self._held + text
            self._held = ""
            if text.endswith("\r"):
                text, self._held = text[:-1], "\r"
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text:
                self._pending.append(text)
                self._stale = True

    def close(self) -> None:
        """
        The source has ended: everything commits, the unfinished last line included.
        """
        with self._lock:
            if self._closed:
                return
            if self._held:
                self._pending.append("\n")
                self._held = ""
            self._closed = True
            self._stale = True

    # -- reading ----------------------------------------------------------

    @property
    def theme(self) -> Theme:
        """The host's theme, as given."""
        return self._theme

    @property
    def live_theme(self) -> Theme:
        """
        The theme the unfinished tail is built with: `theme` itself unless one was given.

        When it is not `theme`, a block is built again as it commits (what
        `imscribe.stream.CommitPolicy.RESET` is there), and a view that holds
        a live table's columns lets them go at that moment.
        """
        return self._live_theme

    @property
    def reader(self) -> ReaderOptions:
        """The reader options this stream reads with: `ReaderOptions()` unless some were given."""
        return self._reader

    @property
    def closed(self) -> bool:
        """Whether `close` has been called."""
        return self._closed

    @property
    def source(self) -> str:
        r"""Everything appended so far, line ends normalised to `\n`: what `sources` index."""
        with self._lock:
            pending = "".join(self._pending)
        return "".join(self._head) + self._tail + pending

    @property
    def committed(self) -> tuple[MarkdownBlock, ...]:
        """The blocks that will not change. Append-only: a longer tuple, same start."""
        self._settle()
        return self._committed

    @property
    def live(self) -> tuple[MarkdownBlock, ...]:
        """The blocks of the unfinished tail. Empty after `close`."""
        self._settle()
        return self._live

    @property
    def blocks(self) -> tuple[MarkdownBlock, ...]:
        """`committed` followed by `live`."""
        self._settle()
        return self._committed + self._live

    @property
    def sources(self) -> tuple[BlockSource, ...]:
        """
        Where each of `blocks` came from, as spans into `source`.

        The live blocks' part is built on the first read after a change and
        not before: while a long list is being written every one of its
        blocks has a `top` that ends where the text so far ends, so each
        read that asks is one new `BlockSource` per live block, and a caller
        that reads only `blocks` does not pay that.
        """
        self._settle()
        live = self._live_sources
        if live is None:
            parsed = self._live_parsed
            assert parsed is not None
            live = self._live_sources = self._sources_of(parsed)
        return self._committed_sources + live

    @property
    def revision(self) -> int:
        """A counter that goes up whenever `blocks` may have changed. Reading it parses."""
        self._settle()
        return self._revision

    @property
    def pending(self) -> bool:
        """Whether text has been appended that no read has parsed yet. Parses nothing."""
        return self._stale

    # -- the ways this class reaches the parser ----------------------------

    def _tokens_of(self, source: str) -> list[Any]:
        # Until the stream is closed more may follow, and with math on a
        # closing dollar that is the last character so far closes nothing yet
        # (`imscribe.markdown_rules`). Only the unfinished last line of the
        # tail can end in one: every other slice parsed here ends at a line end.
        return _parse(self._parser, source, self._math and not self._closed)

    def _blocks_of(
        self,
        tokens: list[Any],
        source: str,
        starts: list[int],
        theme: Theme,
        *,
        first: int = 0,
        state: _Nesting | None = None,
        mark: int = -1,
    ) -> tuple[MarkdownDocument, int, _Nesting | None]:
        return _read_tokens(
            tokens,
            source,
            starts,
            theme,
            self._refuses,
            self._converter_spaces,
            first=first,
            state=state,
            mark=mark,
            options=self._reader,
        )

    def _fence_at(self, source: str) -> _Fence | None:
        r"""
        The fenced block `source` begins with, if its first line opens one at top level.

        `imscribe.markdown._leading_fence` without a container, and its
        docstring has the reasons for each step: the parser answers, not a
        reading of backticks; a fence token's line range ends after the
        closing line when there is one, so a range one line longer than
        opener plus content is a closed fence; and an unfinished last line
        is given its newline first, or dropped when it is only spaces and
        tabs, because markdown-it's line scanner never records such a line.
        """
        unfinished = source[source.rfind("\n") + 1 :]
        if unfinished:
            source = source + "\n" if unfinished.strip(" \t") else source[: -len(unfinished)]
        tokens = _parse(self._parser, source)
        if not tokens:
            return None
        token = tokens[0]
        if token.type != "fence" or not token.map or token.map[0] != 0 or token.level != 0:
            return None
        lines = _content_lines(str(token.content))
        return _Fence(
            lines=lines,
            language=str(token.info).strip(),
            closed=int(token.map[1]) - int(token.map[0]) > len(lines) + 1,
        )

    def _table_of(self, text: str, theme: Theme) -> tuple[MarkdownTable, int, int] | None:
        """
        The table `text` begins with: the block, the line it ends before, and how many blocks.

        `None` unless the first thing the parser finds is a table that starts
        on the first line. The line is markdown-it's own (`token.map`); the
        count is of every block `text` reads as, so one means the table is
        all there is.
        """
        tokens = self._tokens_of(text)
        if not tokens or tokens[0].type != "table_open" or not tokens[0].map:
            return None
        if int(tokens[0].map[0]) != 0:
            return None
        document, _, _ = self._blocks_of(tokens, text, _line_starts(text), theme)
        if not document.blocks or not isinstance(document.blocks[0], MarkdownTable):
            return None
        return document.blocks[0], int(tokens[0].map[1]), len(document.blocks)

    # -- the parse --------------------------------------------------------

    def _read(self, upto: int, *, committing: bool) -> _Parsed:
        """
        Parse the tail's first `upto` characters, re-reading as little of it as is known safe.

        `imscribe.stream.StreamDocument._read`. `committing` says which of the
        two parses of `_settle` this is: the one over complete lines, in the
        theme a block commits with, or the one over everything, in the live
        theme. Only the first may move the point reading resumes from
        (`_resume_point` needs complete lines), and it reads for both themes
        when it does, so that the second finds its kept blocks waiting.

        With no `_restart`, or one whose opener the parser did not read as
        the containers it was written for, this is one parse of the whole
        tail: the slow answer, and the one every other is held equal to.
        """
        theme = self._theme if committing else self._live_theme
        learn = committing and not self._closed
        restart = self._restart
        if restart is not None:
            parsed = self._read_resumed(restart, upto, theme, committing, learn)
            if parsed is not None:
                return parsed
            if learn:
                self._restart = None
        source = self._tail[:upto]
        tokens = self._tokens_of(source)
        starts = _line_starts(source)
        point = _resume_point(tokens, source, starts) if learn else None
        mark = point.mark if point is not None else -1
        document, count, state = self._blocks_of(tokens, source, starts, theme, mark=mark)
        if point is not None and state is not None:
            kept = _Kept(document.blocks[:count], state)
            live = kept
            if self._live_theme is not theme:
                other, _, other_state = self._blocks_of(
                    tokens, source, starts, self._live_theme, mark=mark
                )
                assert other_state is not None
                live = _Kept(other.blocks[:count], other_state)
            self._restart = _Restart(
                resume=point,
                line=point.line,
                offset=starts[point.line],
                spans=tuple(
                    entry.span.shifted(self._head_lines, self._head_chars)
                    for entry in document.sources[:count]
                ),
                commit=kept,
                live=live,
            )
        return _Parsed((), (), None, document.blocks, document.sources)

    def _read_resumed(
        self, restart: _Restart, upto: int, theme: Theme, committing: bool, learn: bool
    ) -> _Parsed | None:
        """
        `_read` by parsing an opener and the tail from `restart` on. `None` if that failed.

        The opener is one line, so every line of what is parsed is one line
        further down than it is in the tail, less the lines before the
        restart; characters likewise. The container's own span runs from the
        tail's first line -- a restart is only ever made in the tail's first
        block -- to wherever this parse says the container now ends.
        """
        opener = restart.resume.opener
        shape = restart.resume.shape
        source = opener + self._tail[restart.offset : upto]
        tokens = self._tokens_of(source)
        if not _opens(tokens, shape):
            return None
        starts = _line_starts(source)
        skip = len(shape)
        point = _resume_point(tokens, source, starts, skip) if learn else None
        mark = point.mark if point is not None else -1
        kept = restart.commit if committing else restart.live
        document, count, state = self._blocks_of(
            tokens, source, starts, theme, first=skip, state=kept.state, mark=mark
        )
        lines = restart.line - 1
        characters = restart.offset - len(opener)
        inside = _span(tokens[0].map, starts, source)
        top = SourceSpan(
            line_start=0,
            line_end=inside.line_end + lines,
            start=0,
            end=inside.end + characters,
        )
        sources = tuple(
            BlockSource(
                span=entry.span.shifted(lines, characters),
                top=top if entry.top.line_start == 0 else entry.top.shifted(lines, characters),
            )
            for entry in document.sources
        )
        if point is not None and state is not None:
            commit = _Kept(kept.blocks + document.blocks[:count], state)
            live = commit
            if restart.live is not restart.commit:
                other, _, other_state = self._blocks_of(
                    tokens,
                    source,
                    starts,
                    self._live_theme,
                    first=skip,
                    state=restart.live.state,
                    mark=mark,
                )
                assert other_state is not None
                live = _Kept(restart.live.blocks + other.blocks[:count], other_state)
            self._restart = _Restart(
                resume=point,
                line=point.line + lines,
                offset=starts[point.line] + characters,
                spans=restart.spans
                + tuple(
                    entry.span.shifted(self._head_lines, self._head_chars)
                    for entry in sources[:count]
                ),
                commit=commit,
                live=live,
            )
        return _Parsed(kept.blocks, restart.spans, top, document.blocks, sources)

    def _settle(self) -> None:
        """
        Run the deferred parse: commit what is settled, rebuild the live tail.

        `imscribe.stream.StreamDocument._settle`. Two parses of the tail at
        most. The first reads it up to its last newline and decides the
        boundary; it is skipped when no line has ended since it was last
        run. The second builds the live blocks from whatever is left,
        unfinished line included, and is skipped when the first one already
        read exactly that text with the same theme.

        Neither runs while the tail is an open fence or a table being
        followed, which read only what is new. The loop is for the one that
        ends: its commit leaves a tail that has not been looked at, and that
        goes round again.
        """
        with self._lock:
            if not self._stale:
                return
            self._stale = False
            pending, self._pending = self._pending, []
        if pending:
            self._tail += "".join(pending)
        if self._closed:
            self._fence = None
            self._table = None
        was = self._live
        before_commit = len(self._committed)

        may_enter = True
        while True:
            if self._fence is not None:
                before = len(self._tail)
                if self._grow_fence():
                    break
                # Left the fence. If it committed, the tail is shorter and what
                # remains may open another; if it did not, something disagreed
                # with the parser and trying again now would only loop.
                may_enter = len(self._tail) < before
            elif self._table is not None:
                before = len(self._tail)
                if self._grow_table():
                    break
                may_enter = len(self._tail) < before

            decided: _Parsed | None = None
            complete = len(self._tail) if self._closed else self._tail.rfind("\n") + 1
            if self._closed or complete > self._examined:
                decided = self._read(complete, committing=True)
                self._examined = complete
                if self._commit(decided):
                    decided = None

            if self._closed:
                self._live, self._live_sources, self._live_parsed = (), (), None
            elif may_enter and (self._enter_fence() or self._enter_table()):
                continue
            elif (
                decided is not None
                and complete == len(self._tail)
                and self._theme is self._live_theme
            ):
                self._show(decided)
            else:
                self._show(self._read(len(self._tail), committing=False))
            break
        self._keep_identity(was, before_commit)
        self._revision += 1

    def _keep_identity(self, was: tuple[MarkdownBlock, ...], before_commit: int) -> None:
        """
        A block that is what it was is the object it was, committed or not.

        `was` are the live blocks of the last read and `before_commit` how
        many blocks were committed then; what follows those, committed in
        this read or live now, is compared with `was` from the front and
        takes its objects for as long as the two are equal.

        A long list's kept children come back as the same objects read after
        read, so nearly every comparison is `is`. Where a kept child was
        equal and not the same -- the first read after reading resumed there
        has blocks from another parse -- the restart is given the object the
        view already holds, so that it is `is` from then on.
        """
        fresh = [*self._committed[before_commit:], *self._live]
        first_swap = -1
        same = 0
        for old in was[: len(fresh)]:
            block = fresh[same]
            if block is not old:
                if block != old:
                    break
                fresh[same] = old
                if first_swap < 0:
                    first_swap = same
            same += 1
        if first_swap < 0:
            return
        cut = len(self._committed) - before_commit
        if cut:
            self._committed = self._committed[:before_commit] + tuple(fresh[:cut])
        self._live = tuple(fresh[cut:])
        restart = self._restart
        if restart is None or cut:
            return
        kept = len(restart.live.blocks)
        if first_swap < kept <= same:
            held = _Kept(self._live[:kept], restart.live.state)
            self._restart = replace(
                restart,
                live=held,
                commit=held if restart.commit is restart.live else restart.commit,
            )

    def _commit(self, parsed: _Parsed) -> bool:
        """
        Commit every top-level block of `parsed` but the last. True if the tail moved.

        All of them when the stream is closed. `parsed` is the tail's
        complete lines, so its spans count from the tail's start and are
        shifted into the whole source's coordinates on the way out.

        The tail moves to the last top-level block's first line even when
        there is no block before it to commit: blank lines, or a raw HTML
        block, which emits nothing.
        """
        sources = parsed.sources
        if self._closed:
            cut = len(parsed.kept) + len(parsed.fresh)
            start, lines = len(self._tail), self._tail.count("\n")
        else:
            if not (parsed.kept or parsed.fresh) or len(sources) != len(parsed.fresh):
                # No source map, no boundary: refusing to commit is the answer
                # that cannot be wrong. (A reader records a source for every
                # block it emits.)
                return False
            last = sources[-1].top if sources else parsed.top
            assert last is not None
            if last == parsed.top:
                # Still inside the container the kept blocks belong to.
                cut = 0
            else:
                cut = len(parsed.kept) + next(
                    index for index, source in enumerate(sources) if source.top == last
                )
            start, lines = last.start, last.line_start
        if not cut and not start and not self._closed:
            return False
        if cut:
            self._committed += parsed.blocks[:cut]
            self._committed_sources += self._sources_of(parsed)[:cut]
        self._advance(start, lines)
        return True

    def _advance(self, characters: int, lines: int) -> None:
        """
        Move the start of the tail forward: that much source is settled.
        """
        self._head.append(self._tail[:characters])
        self._tail = self._tail[characters:]
        self._head_chars += characters
        self._head_lines += lines
        self._examined = max(0, self._examined - characters)
        self._restart = None

    # -- a fence being written ---------------------------------------------

    def _enter_fence(self) -> bool:
        """
        Start following the tail as an open fence, if its first two lines are one.

        Two *complete* lines, parsed on their own, being a top-level fence
        that has not closed. That is enough to know every later line belongs
        to it until one closes it; `imscribe.stream` says why it takes two
        (`~~~a|b` over `-|-` is a table).
        """
        tail = self._tail
        first = tail.find("\n") + 1
        second = tail.find("\n", first) + 1 if first else 0
        if not second or not _FENCE_OPENER.match(tail):
            return False
        prefix = tail[:second]
        found = self._fence_at(prefix)
        if found is None or found.closed or len(found.lines) != 1:
            return False
        live = self._live_theme.style(BlockKind.CODE)
        commit = self._theme.style(BlockKind.CODE)
        # As `_Reader._code` makes the two blocks, in each theme.
        shown = self._reader.show_fence_info and bool(found.language)
        self._fence = _LiveFence(
            prefix=prefix,
            lines=found.lines,
            starts=[0, first, second],
            live=MarkdownCode(
                style=_under_info(live) if shown else live,
                text="",
                language=found.language,
                left_indent=live.left_indent,
            ),
            commit=MarkdownCode(
                style=_under_info(commit) if shown else commit,
                text="",
                language=found.language,
                left_indent=commit.left_indent,
            ),
            live_info=_fence_info(live, found.language, live.left_indent) if shown else None,
            commit_info=(
                _fence_info(commit, found.language, commit.left_indent) if shown else None
            ),
        )
        return True

    def _grow_fence(self) -> bool:
        """
        Read what is new of the fence. True if it is still open and has been shown.

        False when the fence is over, and then `_fence` is `None`. Either a
        new line closed it -- it is committed here, with the lines up to its
        closing one, and the tail now starts after that -- or the parser did
        not find the fence this object says is there, which no source is
        known to cause and which is answered by forgetting the fence and
        parsing the tail whole.
        """
        fence = self._fence
        assert fence is not None
        tail = self._tail
        starts = fence.starts
        read = starts[-1]
        complete = tail.rfind("\n") + 1
        if complete > read:
            chunk = tail[read:complete]
            found = self._fence_at(fence.prefix + chunk)
            if found is None or not (found.closed or len(found.lines) == chunk.count("\n") + 1):
                self._fence = None
                return False
            position = chunk.find("\n")
            while position != -1:
                starts.append(read + position + 1)
                position = chunk.find("\n", position + 1)
            fence.lines.extend(found.lines[1:])
            if found.closed:
                # The opener, the content lines, and the line that closed it.
                through = len(fence.lines) + 2
                span = _span((0, through), starts, tail)
                settled = _filled(fence.commit, fence.lines, fence.commit_info)
                self._committed += settled
                self._committed_sources += (self._shifted(BlockSource(span=span, top=span)),) * len(
                    settled
                )
                self._advance(starts[through], through)
                self._examined = 0
                self._fence = None
                return False
        self._examined = complete

        lines = fence.lines
        unfinished = tail[complete:]
        if unfinished:
            # The line still being typed is content -- unless, as it stands, it
            # would close the fence, in which case the parser returns no line
            # for it. Either way it is asked again when more of it arrives.
            found = self._fence_at(fence.prefix + unfinished)
            if found is None:
                self._fence = None
                return False
            lines = lines + found.lines[1:]
            starts.append(len(tail))
        span = _span((0, len(starts) - 1), starts, tail)
        if unfinished:
            starts.pop()
        self._live = _filled(fence.live, lines, fence.live_info)
        self._live_sources = (self._shifted(BlockSource(span=span, top=span)),) * len(self._live)
        self._live_parsed = None
        return True

    # -- a table being written ---------------------------------------------

    def _enter_table(self) -> bool:
        """
        Start following the tail as a table, if its first two lines are a header and a delimiter.

        Two *complete* lines that, parsed on their own, are a table of no
        rows and nothing else. Complete, because a delimiter row still being
        typed can stop being one (`|---|x`). At top level only.
        """
        tail = self._tail
        first = tail.find("\n") + 1
        second = tail.find("\n", first) + 1 if first else 0
        if not second or not _TABLE_DELIMITER.fullmatch(tail, first, second):
            return False
        prefix = tail[:second]
        found = self._table_of(prefix, self._live_theme)
        if found is None or found[0].rows or found[1] != 2 or found[2] != 1:
            return False
        commit = found[0]
        rows: list[tuple[MarkdownCell, ...]] = []
        commit_rows = rows
        if self._theme is not self._live_theme:
            other = self._table_of(prefix, self._theme)
            if other is None or other[0].rows:
                return False
            commit = other[0]
            commit_rows = []
        self._table = _LiveTable(
            prefix=prefix,
            rows=rows,
            commit_rows=commit_rows,
            starts=[0, first, second],
            live=found[0],
            commit=commit,
        )
        return True

    def _grow_table(self) -> bool:
        """
        Read what is new of the table. True if it is still the tail and has been shown.

        `imscribe.stream.StreamDocument._grow_table`, whose docstring has the
        claim this rests on and what in markdown-it it was read from: whether
        a line is a row of an open table, and what its cells are, depends on
        that line and on the table's header and delimiter rows, and on no
        other row. So each new complete line is parsed under the header and
        delimiter alone and the rows it gives are added to the ones kept.

        The table commits when a complete line arrives that is not a row of
        it, with the rows before that line, and the tail then starts on that
        line. A line still being typed is asked about the same way, as it
        stands; if the answer is anything more than the table, the tail is
        parsed whole for this one read and the table is kept.

        False when the table is over, and then `_table` is `None`.
        """
        table = self._table
        assert table is not None
        tail = self._tail
        starts = table.starts
        read = starts[-1]
        complete = tail.rfind("\n") + 1
        two = table.commit_rows is not table.rows
        if complete > read:
            chunk = tail[read:complete]
            count = chunk.count("\n")
            found = self._table_of(table.prefix + chunk, self._live_theme)
            if found is None:
                self._table = None
                return False
            block, end, _ = found
            fresh = end - 2
            if not 0 <= fresh <= count or len(block.rows) != fresh:
                self._table = None
                return False
            if two:
                other = self._table_of(table.prefix + chunk, self._theme)
                if other is None or other[1] != end or len(other[0].rows) != fresh:
                    self._table = None
                    return False
                table.commit_rows.extend(other[0].rows)
            table.rows.extend(block.rows)
            position = chunk.find("\n")
            for _ in range(fresh):
                starts.append(read + position + 1)
                position = chunk.find("\n", position + 1)
            if fresh < count:
                # A complete line that is not a row: the table is over.
                through = len(starts) - 1
                span = _span((0, through), starts, tail)
                self._committed += (replace(table.commit, rows=tuple(table.commit_rows)),)
                self._committed_sources += (self._shifted(BlockSource(span=span, top=span)),)
                self._advance(starts[through], through)
                self._examined = 0
                self._table = None
                return False
        self._examined = complete

        rows = table.rows
        lines = len(starts) - 1
        unfinished = tail[complete:]
        if unfinished:
            found = self._table_of(table.prefix + unfinished, self._live_theme)
            if found is None:
                self._table = None
                return False
            block, end, blocks = found
            if blocks != 1 or end not in (2, 3) or len(block.rows) != end - 2:
                self._show(self._read(len(tail), committing=False))
                return True
            if block.rows:
                rows = [*rows, *block.rows]
                lines += 1
        starts.append(len(tail))
        span = _span((0, lines), starts, tail)
        starts.pop()
        self._live = (replace(table.live, rows=tuple(rows)),)
        self._live_sources = (self._shifted(BlockSource(span=span, top=span)),)
        self._live_parsed = None
        return True

    # -- what a read leaves -------------------------------------------------

    def _show(self, parsed: _Parsed) -> None:
        self._live = parsed.blocks
        self._live_sources = None
        self._live_parsed = parsed

    def _sources_of(self, parsed: _Parsed) -> tuple[BlockSource, ...]:
        """
        `parsed`'s sources, kept blocks first, in the whole source's coordinates.
        """
        fresh = tuple(self._shifted(source) for source in parsed.sources)
        if parsed.top is None:
            return fresh
        top = parsed.top.shifted(self._head_lines, self._head_chars)
        return tuple(BlockSource(span=span, top=top) for span in parsed.spans) + fresh

    def _shifted(self, source: BlockSource) -> BlockSource:
        return BlockSource(
            span=source.span.shifted(self._head_lines, self._head_chars),
            top=source.top.shifted(self._head_lines, self._head_chars),
        )

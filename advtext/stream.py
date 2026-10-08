r"""
A document that arrives a piece at a time: settled blocks, and a tail still being written.

`advtext.markdown.build_document` is handed a whole file. A host showing a
model's answer is handed a few characters at a time and must show what it has.
Re-parsing everything on every token is correct and is what this module exists
to avoid: `StreamDocument` takes text through `append`, decides which top-level
blocks can no longer change, **commits** those -- builds them once, never again
-- and re-parses only the source after them, the **live tail**.

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("Some *text* that")
    stream.append(" keeps arriving.\n\nA second")
    stream.committed      # blocks that will never be revised
    stream.live           # blocks of the unfinished tail, rebuilt as it grows
    stream.close()        # the source has ended: everything commits

This module performs no layout and imports none. It produces the same frozen
`Block`s `build_document` does, so everything downstream -- `compose_blocks`,
the per-block units, the views -- takes them unchanged, and composition's
by-value caches hit on every committed block because a committed block is the
same object from then on.

## Where the commit boundary is, and why it is not a scanner

The parser decides, not a hand-written reading of blank lines and fences. The
tail is parsed with markdown-it, each block comes back with the span of the
top-level markdown block it belongs to (`advtext.markdown.BlockSource.top`),
and **every top-level block before the last one is committed**. The tail then
begins at the last one's first line.

`docs/adoption-plan.md` rules the scanner out with one construct, and
`demo/stream.md` contains it so that a demo cannot hide it: a numbered item
followed by an indented fence. Parsed from the item's own first line the fence
is inside the item; parsed from the fence's line alone -- which is where a
"blank line, then something new" scanner would cut -- it is a top-level code
block with the wrong indent and no number. Cutting only at boundaries the parser
itself reports cannot make that mistake.

Source before the tail's last top-level block that emitted nothing -- blank
lines, a raw HTML block -- is dropped from the tail at the same time, whether
or not a block is committed with it, so the tail always begins on the first
line of the block still being written.

**The boundary is decided on complete lines only.** The reviewer predicted the
failure this prevents and it reproduces: the source `para`, newline, `#` parses
as a paragraph and an empty heading, so the paragraph would commit; when the
next characters make the line `#tag` it is one two-line paragraph and the
committed block is wrong. The same happens with a fence opener that turns out to
have a backtick in its info string, a `<p` that becomes `<path>`, and a table
whose delimiter row is half typed (all four are in `tests/test_stream.py`). An
unfinished line can still become anything; a finished one cannot. So the commit
decision parses the tail *up to its last newline*, and the unfinished line is
only ever part of the live tail, which is re-parsed anyway.

**What that rests on, and how much of it was checked.** Two claims:

1. *Once a line has ended, nothing that arrives later changes any top-level
   block but the last.* A later line can extend the last block (a lazy
   continuation line, another list item), convert it (a setext underline turns a
   paragraph into a heading) or split it (a delimiter row turns the end of a
   paragraph into a table). None of those reaches the block before it.
2. *Parsing from the first line of a top-level block gives the blocks the whole
   source gives from there on.* Top-level block structure does not depend on
   what came before the block.

Both are false of CommonMark as specified, for one construct: a link reference
definition, which may come last and changes every earlier `[name]`. That rule is
switched off here (`build_document(..., references=False)`), and the cost is
stated below. With it off, neither claim is proved in this module. They are
**tested**: `tests/test_stream.py` feeds several documents through in pieces of
one character, of a "token", of a line and of random sizes, and after every
piece asserts that the stream's blocks are exactly the blocks of one parse of
everything received so far, and that no committed block has changed. A construct
that broke either claim would fail there. A construct nobody thought to put in
those documents is not covered by anything.

A top-level block that emits nothing this project renders -- a raw HTML block --
is invisible to the boundary, which is found from emitted blocks. The block
before it is then committed one block later than it could have been. That is
late, not wrong.

## What differs from `build_document`

- **Link reference definitions are not read.** `[name]: https://example.org` is
  set as a paragraph of that text and `[name]` is not a link. On a source with
  no definitions the closed stream's blocks equal `build_document`'s, which is
  the other half of what the property test asserts.
- **Line ends are normalised.** `\r\n` and a lone `\r` become `\n` as text is
  appended, with a `\r` at the end of one piece held until the next shows
  whether a `\n` follows. `StreamDocument.source` and every `SourceSpan` are in
  that normalised text. markdown-it does the same to a source it is given, so
  the blocks are the same; only the offsets are in different coordinates from
  the host's raw bytes, and only for a source that had carriage returns.

## The live tail is set ragged, and what happens to it at commit

A block is re-broken every time it grows, so the lines already above the one
being written must not move. Justified setting cannot promise that: the
optimiser chooses every break of a paragraph together, and adding a word can
move an earlier one (measured by A7-stable on the 635-node paragraph of
`demo/sample.md`: 0 to 4 of 101 word-steps moved a settled line, depending on
the measure). Composition breaks any block that is not justified **first-fit at
natural spacing** (`advtext.ui._text_boxes`), which fills each line and never
looks back: a line, once left, is the same line for every longer text.

So the blocks of the live tail are built with `live_theme(theme)`: the host's
theme with every justified block style made ragged right, and nothing else
touched. A theme that is ragged, centred or ragged left already is its own live
theme. This module only puts the alignment on the block's style, as data;
`advtext.ui` is what acts on it.

**What first-fit does not protect is the text changing under it.** The claim is
about appending *words*. A source prefix is not a word prefix: an unclosed `**`
is set as two asterisks until its partner arrives and then the whole run is
bold, with other widths; a `[text](` is literal until the `)`. When that
happens every line after the opening mark can move, in any setting. Nothing here
hides it and a count of moved lines must not assume zero for such text.

`CommitPolicy` is what a block becomes when it commits:

- `KEEP_STREAMED` (the default): the block as it was last shown. Its lines are
  the lines the reader watched arrive.
- `RESET`: the block rebuilt with the host's own theme, so a justified theme's
  paragraph is re-set justified at the moment it is finished. One change of
  line breaks per block, at commit.

Which of those is the better thing to look at is not something this module has
an opinion about. The default is the one that changes nothing on screen. For a
theme that is not justified the two are the same.

## What a caller gets to know

`revision` goes up whenever the blocks may have changed, and `committed` is a
tuple that only ever grows at its end, so a view keeps everything it has built
for `committed[:n]` and rebuilds for `live` alone. Parsing is deferred: `append`
only stores the text, and the parse runs when the blocks are next read. However
many pieces arrive between two reads, they cost one parse of the tail.

## A long list or quote is not re-read from its top

A list is one top-level block however many items it has, and so is a block
quote, so "re-parse the tail" used to mean the whole of it for every read while
it was being written. Measured then, in four-character pieces, mean cost of a
piece over the first tenth of the source and over the last: a list of 300
one-line items, 2.1 ms and 43 ms; a quote of 150 paragraphs, 0.8 ms and 17 ms;
a fence of 600 lines *inside a list item*, 1.1 ms and 23 ms. About a quarter of
that was markdown-it and the rest was turning its tokens into blocks.

Such a block still cannot **commit** a child early: every block of a list
carries the span of the whole list (`BlockSource.top`), and that grows until the
list ends. What it can do is stop parsing and converting the children that are
finished. So the stream keeps them (`_Restart`) and reads the tail **from the
line its last child starts on**, with one line in front that re-opens the
containers that child is inside -- `advtext.markdown._resume_point` has the
construction and the argument for it. The same three sources now cost 0.25,
0.20 and 0.09 ms a piece at either end (`.concerns/AF-streamcost--builder--result.md`
has the script and the runs).

What that rests on is a fourth claim beside the two above, and it is the first
of them over again one level down: *once a line has ended, nothing that arrives
later changes any child of an open container but the last*. Like them it is
argued, not proved, and held by the property test, here on sources that nest
lists, quotes and fences. Two things bound the damage if it is wrong somewhere.
The opener line is checked on every read to have been parsed as the containers
it was written for, and if it ever is not the tail is parsed whole, as before
(no source is known that does it; `advtext.markdown._opens`). And nothing is
committed on the strength of it: commits are still decided by top-level blocks
alone, so a wrong resumption shows wrong live blocks until the container ends,
and cannot put a block into `committed` that a whole parse would not.

**What is still linear, and how much.** The kept blocks are one tuple, extended
by a copy when a child finishes and concatenated with the fresh ones on every
read: one pointer per block. `sources` builds a `BlockSource` per live block
when it is read, because each one's `top` ends where the text now ends; that is
about 0.4 microseconds a block, paid only by a caller that asks. A list item's
or quote's *last child* is still re-read whole while it grows, so one enormous
paragraph inside an item costs what one enormous paragraph costs anywhere. An
unclosed raw HTML block is not a container and is not resumed (below).

## A fence being written is the exception: it is converted a line at a time

A long code block is the commonest long block in a model's answer, and parsed
whole on every read it cost 32 ms a piece by its 600th line and rising (review
3, item 5, measured; 0.07 ms now, the same at the 60th line as at the 600th).
A top-level fence is also the one block whose continuation is simple enough to
follow without re-reading it: every line after the opener is content until one
line closes it. So once the tail's first two complete lines
parse as an open fence, the stream stops re-parsing the tail and keeps the lines
it has already converted (`_LiveFence`). Each read then hands the parser the
opener, the first content line and **only the lines that have arrived since**,
plus once more with the unfinished line, and appends what comes back. The cost
of a read no longer depends on how long the fence is, bar the copy of one
pointer per line that building the block's tuple takes.

Three things about how, because each is where it could have been wrong:

- **The parser still decides everything.** Whether a line closes the fence is
  asked of markdown-it on the short text, not read off the backticks here, and
  so is the stripping of a fence's indent from each line
  (`advtext.markdown._leading_fence`).
- **Why the first content line is always sent along.** An opener followed
  directly by a later content line can be something else: `~~~a|b` over `-|-`
  is a table, whose rule runs before the fence's. With the fence's real second
  line in between, the first two lines are the two that already parsed as a
  fence, and no rule that runs before the fence rule reads further than that.
- **Two lines are waited for before any of this starts**, for the same reason:
  with only the opener complete, the next line can still make it a table.

**A fence followed this way commits the moment its closing line ends**, not a
line later as every other block does. The complete-lines rule exists because an
unfinished line can still become anything; a finished closing line cannot, and
nothing that follows a closed fence reaches back into it. Committing there is
what keeps the reads *after* a long fence cheap too: the alternative is the
whole fence parsed again for every piece of the line that follows it.

This rests on a third claim beside the two above -- *an open top-level fence is
extended by every later line until one closes it, and by nothing after that* --
which is tested the same way and proved no more than they are. An empty fence is
not followed, nor one whose closing line arrives before its first content line
has ended; those are short.

**A fence inside a list item or a quote is followed the same way, and never
commits there.** It starts where reading resumes, so the parser is handed the
opener line, the fence's first two lines and what is new. Three things differ.
A line can end it without closing it, by not being indented far enough or by
lacking the quote's `>`: then the parser returns fewer lines than it was given
and the fence is forgotten. The unfinished line is sent exactly as it stands,
because inside a quote an unended `>` is the quote's line and not the fence's.
While such a line is still being typed the fence is kept, and what the line
has become so far is read from the opener, the fence's first two lines and
the line itself (`_show_past_nested_fence`): forgetting the fence there, as
this did until review 5, read the whole of it again for every piece of the
line under it -- `2. the next step`, usually.
And when the fence closes nothing commits -- its list has not ended -- so it
joins the kept children of its container and reading resumes on the line after
its closing line (`_keep_nested_fence`), again without the fence being read a
second time. A nested fence that was never followed -- an empty one, one whose
containers could not be given an opener -- is read whole once more when it
closes and then resumed after in the same way.

## A table being written is read a row at a time

The other block a model writes a line at a time, and it had the fence's
problem: a table is one top-level block until something follows it, so every
piece of every row parsed and converted all of it again. Measured through a
view, a row an append, the parse alone: 1.0, 3.2, 5.5 and 21 ms a row at 10,
30, 50 and 200 rows; 0.3 ms at each now
(`.concerns/AF-livetable--builder--result.md`).

Once the tail's first two complete lines parse as a table's header and
delimiter rows and nothing else, the stream keeps the rows it has converted
(`_LiveTable`) and hands the parser those two lines and **only the lines that
have arrived since**. Three things about it, as for the fence:

- **The parser still decides everything**: whether a line is a row, how it
  splits into cells, what ends the table. `_grow_table` has the claim this
  rests on -- a row depends on its own line and on the header and delimiter,
  and on no other row -- and what in markdown-it it was read from.
- **A followed table commits when a complete line arrives that is not a row
  of it**, which is nearly always the blank line under it, and not a line
  later. Waiting for the next block's first line to end, as every other
  block does, is the whole table read again for every piece of that line.
- **The rows are the same objects from one read to the next**, and in the
  committed block. A view that lays a long table out in pieces finds the
  pieces it has already set by the identity of their rows
  (`advtext.ui.units`), which is the other half of what makes a row cheap.

At top level only. A table inside a list item or a quote is its container's
last child and is read whole with it while it grows, as one long paragraph
there is. On `close` a followed table is parsed whole once, like everything
else that is still live.

An unclosed raw HTML block of the kinds that do not end at a blank line
(`<!--`, `<pre>`, `<script>`) swallows the rest of the source, in a stream as
in a whole parse: nothing after it is a block, so nothing after it is shown and
nothing more commits until `close`, while the tail grows and is re-parsed
(measured: 1.6 ms a piece by 600 swallowed lines, from 0.16; it is cheaper
than a list because nothing in it is converted). That is what the source means, and the
stream agrees with the whole parse about it at every step. A host that does not
want a stray `<!--` to hide the rest of an answer has to escape it before
appending.

Deliberately out of scope: layout, held table column widths while a table is
live, selection across a re-break, coalescing to a frame, scrolling. Those are
the view's.
"""

from __future__ import annotations

import enum
import re
import threading
from dataclasses import dataclass, replace
from itertools import repeat
from typing import Any

from advtext.markdown import (
    Block,
    BlockSource,
    CodeBlock,
    Document,
    MathBuilder,
    SourceSpan,
    TableBlock,
    TableCell,
    _convert,
    _Fence,
    _leading_fence,
    _line_starts,
    _opens,
    _Resume,
    _resume_point,
    _span,
    _tokens,
    _WalkState,
    code_block,
)
from advtext.nodes import Node
from advtext.style import Align, MetricsResolver, Theme

__all__ = [
    "CommitPolicy",
    "StreamDocument",
    "live_theme",
]


class CommitPolicy(enum.Enum):
    """
    What a block of the live tail becomes at the moment it is committed.

    The module docstring has the two members at length. In one line each:
    `KEEP_STREAMED` commits the ragged block the reader was already looking at;
    `RESET` commits the block as the host's theme sets it.
    """

    KEEP_STREAMED = enum.auto()
    RESET = enum.auto()


def live_theme(theme: Theme) -> Theme:
    """
    `theme` with every justified block style made ragged right; itself if none is.

    The theme the live tail's blocks are built with. Only `Align.JUSTIFY` is
    replaced, because it is the only alignment whose line breaks depend on text
    that has not arrived yet; `LEFT`, `CENTER` and `RIGHT` are all broken
    first-fit by composition and differ only in where a finished line is put.

    Nothing but `BlockStyle.align` differs between a block built with this
    theme and the same source built with `theme` -- material, links, marker and
    indent are equal -- which `tests/test_stream.py` asserts, since `RESET`
    relies on it to mean "re-set" and not "rebuild as something else".

    Returns the same object when there is nothing to change, so a caller can
    ask `live_theme(theme) is theme`.
    """
    if all(style.align is not Align.JUSTIFY for style in theme.blocks.values()):
        return theme
    return replace(
        theme,
        blocks={
            kind: replace(style, align=Align.LEFT) if style.align is Align.JUSTIFY else style
            for kind, style in theme.blocks.items()
        },
    )


_FENCE_MARK = re.compile(r"```|~~~")
"""
The same filter for a fence inside a list or quote, where anything may precede it.
"""

_FENCE_OPENER = re.compile(r" {0,3}(?:```|~~~)")
"""
What a line must start with to be worth asking the parser whether it opens a fence.

A filter and nothing more: it lets through lines that are not openers (a
backtick fence with a backtick in its info string, a table's header row) and
`advtext.markdown._leading_fence` is what says no to those.
"""


_TABLE_DELIMITER = re.compile(r"[ \t|:-]*-[ \t|:-]*\n")
"""
What a tail's second line must look like to be worth asking the parser whether it is a table's.

A filter and nothing more, as `_FENCE_OPENER` is: a delimiter row is dashes,
colons, pipes and blanks with at least one dash. Whether the two lines *are* a
table -- the column counts agree, the first is not something else -- is the
parser's to say.
"""


@dataclass(slots=True)
class _LiveTable:
    """
    A top-level table still being written, and the rows of it already converted.

    The tail is this table and nothing else for as long as one of these
    exists. `prefix` is its header row and its delimiter row as they stand in
    the tail, sent to the parser in front of every new piece. `rows` is every
    row whose line has ended, converted. `starts` is the offset in the tail at
    which each complete line begins, and last the offset at which the next
    will, as in `_LiveFence`.

    `live` and `commit` are the table with no rows in each of the stream's two
    themes; the block shown and the block committed are these with the rows
    put in. The rows are shared between the two for the reason a fence's
    lines are: a theme and its live theme differ in a block style's alignment
    and in nothing a cell is made of (`live_theme`).
    """

    prefix: str
    rows: list[tuple[TableCell, ...]]
    starts: list[int]
    live: TableBlock
    commit: TableBlock


@dataclass(slots=True)
class _LiveFence:
    """
    A top-level fence still being written, and what has been converted of it.

    The tail is this fence and nothing else for as long as one of these exists.
    `prefix` is the opener and the first content line as they stand in the
    tail, sent to the parser in front of every new piece (the module docstring
    says why both). `lines` is every complete content line, converted, blank
    ones at the end included: a `CodeBlock` drops trailing blank lines, and
    text may still arrive after these. `starts` is the offset in the tail at
    which each complete line begins, and last the offset at which the next
    will, so `starts[-1]` is also how much of the tail has been read.

    `live` and `commit` are the fence as an empty `CodeBlock` in each of the
    stream's two themes; the block shown and the block committed are these with
    the lines put in.

    **Inside a list or a quote** the fence is not the tail but its end, and
    `base` is the restart it begins at: the tail from `base.offset` on is this
    fence and nothing else, `prefix` has the restart's opener line in front of
    the fence's two, and `starts` still holds offsets in the tail. Such a
    fence is only ever shown. It cannot commit before its container does, so
    when it closes it becomes one of the container's kept blocks
    (`StreamDocument._keep_nested_fence`).
    """

    prefix: str
    lines: list[tuple[Node, ...]]
    starts: list[int]
    live: CodeBlock
    commit: CodeBlock
    base: _Restart | None = None


@dataclass(frozen=True, slots=True)
class _Kept:
    """
    The settled children of the container being written, in one theme.

    `blocks` are the blocks emitted before the line parsing resumes at, and
    `state` is the converter's nesting state at that line, which is what makes
    the next block come out numbered and indented as if the walk had never
    stopped.
    """

    blocks: tuple[Block, ...]
    state: _WalkState


@dataclass(frozen=True, slots=True)
class _Restart:
    """
    Where in the tail a read resumes, when the tail is one long list or quote.

    `resume` is `advtext.markdown._resume_point`'s answer, and `line` and
    `offset` are its line in the tail's coordinates. `spans` are the own spans
    of the kept blocks, in the **whole source's** coordinates -- they are
    final, and the tail cannot move while this object lives, so they are moved
    once and not on every read. Their `top` is not stored because it is the
    container's whole span, which grows with every piece.
    `commit` and `live` are the kept blocks in the stream's two themes, and the
    same object when those are one theme.

    Valid for as long as the tail starts where it did: text is only ever added
    after `offset`, and `StreamDocument._advance` discards this.
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

    A `Document` in two pieces, so that a read which re-parsed only the end of
    a long container does not have to rebuild a `BlockSource` for every block
    before it in order to say what it found. `kept` and `spans` are parallel
    and all belong to the top-level block `top`; `fresh` and `sources` are
    parallel and are whatever the parse itself produced. `top` and `sources`
    are in the tail's coordinates and `spans` in the whole source's
    (`_Restart`). With nothing kept, `top` is `None` and this is a `Document`
    by another name.
    """

    kept: tuple[Block, ...]
    spans: tuple[SourceSpan, ...]
    top: SourceSpan | None
    fresh: tuple[Block, ...]
    sources: tuple[BlockSource, ...]

    @property
    def blocks(self) -> tuple[Block, ...]:
        return self.kept + self.fresh if self.kept else self.fresh


class StreamDocument:
    """
    Markdown received in pieces: blocks that are settled, and a tail that is not.

    Construct it with the theme and resolver a `build_document` call would take
    (and its `math`, if formulas are wanted: off by default, as there),
    `append` text as it arrives, and `close` when the source has ended. Read
    `committed` and `live`, or `document` for the two together as an ordinary
    `Document` with its source map.

    **The invariant, held by `tests/test_stream.py` after every piece:**
    `committed` only grows, and a block in it is never replaced, removed or
    reordered. `blocks` -- committed then live -- equals, block for block, one
    parse of `source` with reference definitions off, except for the alignment
    carried on a style: live blocks have the live theme's, committed ones the
    policy's. With `math`, that one parse is a parse *told what the stream
    knows*: `build_document(source, ..., references=False, math=math,
    more_may_follow=not closed)`. While the stream is open, an inline formula
    whose closing dollar is the last character received is still text (the
    character after it decides whether it closed anything: `$PATH=$` then
    `HOME`); `close()` is the end of the input, and then it is a formula.

    **Threads: `append` may be called from any thread; nothing else may.** A
    host usually receives its text on a network thread, so `append` takes a
    lock around the buffer of pieces not yet parsed, and the parse takes the
    whole buffer under the same lock; a piece is in one read or the next and
    cannot fall between (it could, before the lock: measured, a thread
    appending 1,500 pieces while another read `revision` lost a piece in 3
    trials of 30). Every read, and `close`, belong to one thread -- the one
    that draws. Pieces appended from *two* threads at once arrive in an order
    nobody chose, and a `\r\n` split between them is two line ends; one
    producer is what is meant.

    `append` after `close` raises `ValueError`, from any thread. A producer
    that is cancelled -- the user stops a reply, the host closes the stream --
    may well have one more token on its way, and that token lands here: stop
    the producer before closing, or catch the error where it appends.
    """

    __slots__ = (
        "_closed",
        "_commit_theme",
        "_committed",
        "_committed_sources",
        "_document",
        "_examined",
        "_fence",
        "_head",
        "_head_chars",
        "_head_lines",
        "_held",
        "_live",
        "_live_parsed",
        "_live_sources",
        "_live_theme",
        "_lock",
        "_math",
        "_pending",
        "_policy",
        "_resolve",
        "_restart",
        "_revision",
        "_stale",
        "_table",
        "_tail",
        "_theme",
    )

    def __init__(
        self,
        theme: Theme,
        resolve: MetricsResolver,
        *,
        policy: CommitPolicy = CommitPolicy.KEEP_STREAMED,
        math: MathBuilder | None = None,
    ) -> None:
        self._theme = theme
        self._resolve = resolve
        self._policy = policy
        # `$...$` and `$$`, and what sets them: `advtext.markdown` has the
        # rules. None, the default, and a dollar is text. Every parse and every
        # conversion below goes through the three methods that pass this on.
        self._math = math
        self._live_theme = live_theme(theme)
        self._commit_theme = theme if policy is CommitPolicy.RESET else self._live_theme
        # The source, in three parts: what committed blocks came from (kept
        # only so `source` can be asked for), the uncommitted tail, and pieces
        # appended since the tail was last parsed.
        self._head: list[str] = []
        self._head_chars = 0
        self._head_lines = 0
        self._tail = ""
        self._pending: list[str] = []
        # A carriage return that ended a piece, until the next piece says
        # whether it was half of a `\r\n`.
        self._held = ""
        # Guards `_pending`, `_held`, `_stale` and the reading of `_closed` in
        # `append`: the only state a thread other than the reader's touches.
        self._lock = threading.Lock()
        # How much of the tail the last commit decision had read. Whole lines.
        self._examined = 0
        # Set while the tail is one open top-level fence being followed line by
        # line instead of re-parsed; see `_LiveFence`.
        self._fence: _LiveFence | None = None
        # Set while the tail is one top-level table being followed row by row
        # instead of re-parsed; see `_LiveTable`. Never set together with
        # `_fence`: each is "the tail is this one block".
        self._table: _LiveTable | None = None
        # Set while the tail is one list or quote whose earlier children are
        # kept and only its end is re-parsed; see `_Restart`.
        self._restart: _Restart | None = None
        self._committed: tuple[Block, ...] = ()
        self._committed_sources: tuple[BlockSource, ...] = ()
        self._live: tuple[Block, ...] = ()
        # The live blocks' sources are built when first asked for, from
        # `_live_parsed`: see `sources`.
        self._live_sources: tuple[BlockSource, ...] | None = ()
        self._live_parsed: _Parsed | None = None
        self._document: Document | None = None
        self._revision = 0
        self._stale = False
        self._closed = False

    # -- the three ways this class reaches the parser ------------------------
    #
    # Each is the function of `advtext.markdown` it names with this stream's
    # `math` passed on, and nothing else. They exist so that no call below can
    # forget to: a table followed row by row, a fence followed line by line
    # and a list re-read from a resume point all ask the parser what the next
    # line is, and with math on a `$$` line is a block's start to the parser
    # that reads the whole source. A follower asking a parser that did not
    # know that would disagree with it.

    def _tokens_of(self, source: str) -> list[Any]:
        # With math off the call is the one this class always made, argument
        # for argument: tests count parses by standing in for `_tokens`.
        if self._math is None:
            return _tokens(source)
        # Until the stream is closed more may follow, and a closing dollar
        # that is the last character so far closes nothing yet
        # (`advtext.markdown._math_inline`; review 3, item 3). Only a text
        # that ends in a dollar is affected, and only the unfinished last
        # line of the tail can end in one: every other slice parsed here
        # ends at a line end.
        return _tokens(source, True, not self._closed)

    def _blocks_of(
        self,
        tokens: list[Any],
        source: str,
        starts: list[int],
        theme: Theme,
        resolve: MetricsResolver,
        *,
        first: int = 0,
        state: _WalkState | None = None,
        mark: int = -1,
    ) -> tuple[Document, int, _WalkState | None]:
        return _convert(
            tokens,
            source,
            starts,
            theme,
            resolve,
            first=first,
            state=state,
            mark=mark,
            math=self._math,
        )

    def _fence_at(
        self,
        source: str,
        theme: Theme,
        shape: tuple[tuple[str, str], ...] = (),
        *,
        verbatim: bool = False,
    ) -> _Fence | None:
        # `resolve` so that a character the code face lacks is stood in for
        # here as `build_document` stands in for it (`markdown._stand_in`).
        if self._math is None:
            return _leading_fence(source, theme, shape, verbatim=verbatim, resolve=self._resolve)
        return _leading_fence(
            source, theme, shape, verbatim=verbatim, math=True, resolve=self._resolve
        )

    # -- writing ----------------------------------------------------------

    def append(self, text: str) -> None:
        r"""
        Take the next piece of source. Any size, cut anywhere.

        Stores the text and returns; the parse happens when the blocks are next
        read (see the module docstring). `\r\n` and a lone `\r` become `\n`,
        including a `\r\n` cut between two pieces.

        Raises `ValueError` once the stream is closed: a block committed by
        `close` was committed on the promise that nothing follows it.

        The one method that may be called from a thread other than the
        reader's; the class docstring has what that does and does not cover.
        """
        with self._lock:
            if self._closed:
                raise ValueError("append() on a closed StreamDocument")
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
        The source has ended: commit everything, the unfinished last line included.

        After this `live` is empty and `append` raises. Closing twice is
        harmless.
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
        """
        The host's theme, as given.
        """
        return self._theme

    @property
    def live_theme(self) -> Theme:
        """
        The theme the live tail's blocks are built with: `live_theme(self.theme)`.
        """
        return self._live_theme

    @property
    def policy(self) -> CommitPolicy:
        """
        What a block becomes when it commits. Fixed for the life of the stream.
        """
        return self._policy

    @property
    def closed(self) -> bool:
        """
        Whether `close` has been called.
        """
        return self._closed

    @property
    def source(self) -> str:
        r"""
        Everything appended so far, with line ends normalised to `\n`.

        The text every `SourceSpan` in `sources` indexes. A `\r` that ended the
        last piece is not in it yet.
        """
        with self._lock:
            pending = "".join(self._pending)
        return "".join(self._head) + self._tail + pending

    @property
    def committed(self) -> tuple[Block, ...]:
        """
        The blocks that will not change. Append-only: a longer tuple, same start.
        """
        self._settle()
        return self._committed

    @property
    def live(self) -> tuple[Block, ...]:
        """
        The blocks of the unfinished tail, ragged. Replaced whenever the tail grows.

        Usually one block; a list or a quote being written is as many as it has
        items or paragraphs, because the whole top-level block is unfinished.
        Empty before any text, between a commit and the next text, and after
        `close`.
        """
        self._settle()
        return self._live

    @property
    def blocks(self) -> tuple[Block, ...]:
        """
        `committed` followed by `live`.
        """
        self._settle()
        return self._committed + self._live

    @property
    def sources(self) -> tuple[BlockSource, ...]:
        """
        Where each of `blocks` came from, as spans into `source`. Parallel to `blocks`.

        The live blocks' part is built on the first read after a change and not
        before. While a long list or quote is being written every one of its
        blocks has a `top` that ends where the text so far ends, so each read
        that asks is one new `BlockSource` per live block; a caller that reads
        only `blocks` does not pay that.
        """
        self._settle()
        live = self._live_sources
        if live is None:
            parsed = self._live_parsed
            assert parsed is not None
            live = self._live_sources = self._sources_of(parsed)
        return self._committed_sources + live

    @property
    def document(self) -> Document:
        """
        `blocks` and `sources` as a `Document`. The same object until `revision` changes.
        """
        self._settle()
        if self._document is None:
            self._document = Document(blocks=self.blocks, sources=self.sources)
        return self._document

    @property
    def revision(self) -> int:
        """
        A counter that goes up whenever `blocks` may have changed.

        Reading it runs the deferred parse, so `revision` before and after a
        frame's appends is how a view asks "is there anything to lay out".
        """
        self._settle()
        return self._revision

    @property
    def pending(self) -> bool:
        """
        Whether text has been appended that no read has parsed yet. Parses nothing.
        """
        return self._stale

    # -- the parse --------------------------------------------------------

    def _read(self, upto: int, *, committing: bool) -> _Parsed:
        """
        Parse the tail's first `upto` characters, re-reading as little of it as is known safe.

        `committing` says which of the two parses of `_settle` this is: the
        one over complete lines, in the theme a block commits with, or the one
        over everything, in the live theme. Only the first may move the point
        reading resumes from (`advtext.markdown._resume_point` needs complete
        lines), and it converts for both themes when it does, so that the
        second finds its kept blocks waiting.

        With no `_restart`, or one whose opener the parser did not read as the
        containers it was written for, this is one parse of the whole tail: the
        slow answer, and the one every other is held equal to by the tests.
        """
        theme = self._commit_theme if committing else self._live_theme
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
        document, count, state = self._blocks_of(
            tokens, source, starts, theme, self._resolve, mark=mark
        )
        if point is not None and state is not None:
            kept = _Kept(document.blocks[:count], state)
            live = kept
            if self._live_theme is not theme:
                other, _, other_state = self._blocks_of(
                    tokens, source, starts, self._live_theme, self._resolve, mark=mark
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
        further down than it is in the tail, less the lines before the restart;
        characters likewise. The container's own span runs from the tail's
        first line -- a restart is only ever made in the tail's first block --
        to wherever this parse says the container now ends.
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
            tokens, source, starts, theme, self._resolve, first=skip, state=kept.state, mark=mark
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
                    self._resolve,
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

        Two parses of the tail at most. The first reads it up to its last
        newline and decides the boundary; it is skipped when no line has ended
        since it was last run. The second builds the live blocks from whatever
        is left, unfinished line included, and is skipped when the first one
        already read exactly that text with the same theme.

        Neither runs while the tail is an open fence being followed
        (`_grow_fence`), which reads only what is new. The loop is for the
        fence that ends: its commit leaves a tail that has not been looked at,
        and that goes round again -- to the two parses, or into another fence
        if one piece brought two.
        """
        with self._lock:
            if not self._stale:
                return
            self._stale = False
            # Taken, not copied and then cleared: a piece appended from
            # another thread is in the list this read takes or in the new
            # one, and there is no moment at which it is in neither.
            pending, self._pending = self._pending, []
        if pending:
            self._tail += "".join(pending)
        if self._closed:
            self._fence = None
            self._table = None

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
                and self._commit_theme is self._live_theme
            ):
                self._show(decided)
            else:
                self._show(self._read(len(self._tail), committing=False))
            break
        self._document = None
        self._revision += 1

    def _commit(self, parsed: _Parsed) -> bool:
        """
        Commit every top-level block of `parsed` but the last. True if the tail moved.

        All of them when the stream is closed. `parsed` is the tail's complete
        lines, so its spans count from the tail's start and are shifted into
        the whole source's coordinates on the way out.

        The tail moves to the last top-level block's first line even when there
        is no block before it to commit: blank lines, or a raw HTML block,
        which emits nothing. They are as settled as a block would be, and a
        tail that begins on its block's first line is what `_enter_fence`
        looks for.
        """
        blocks, sources = parsed.blocks, parsed.sources
        if self._closed:
            cut, start, lines = len(blocks), len(self._tail), self._tail.count("\n")
        else:
            if not blocks or len(sources) != len(parsed.fresh):
                # No source map, no boundary. Unreachable through
                # `advtext.markdown`, which records a source for every block;
                # refusing to commit is the answer that cannot be wrong.
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
            self._committed += blocks[:cut]
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

        Two *complete* lines, parsed on their own, being a top-level fence that
        has not closed. That is enough to know every later line belongs to it
        until one closes it; the module docstring says why it takes two.
        """
        tail = self._tail
        first = tail.find("\n") + 1
        second = tail.find("\n", first) + 1 if first else 0
        if not second or not _FENCE_OPENER.match(tail):
            return self._enter_nested_fence()
        prefix = tail[:second]
        found = self._fence_at(prefix, self._live_theme)
        if found is None or found.closed or len(found.lines) != 1:
            return False
        self._fence = _LiveFence(
            prefix=prefix,
            lines=found.lines,
            starts=[0, first, second],
            live=code_block("", self._live_theme, self._resolve, language=found.language),
            commit=code_block("", self._commit_theme, self._resolve, language=found.language),
        )
        return True

    def _enter_nested_fence(self) -> bool:
        """
        Start following a fence inside the list or quote being written, if it ends in one.

        The same two-line test as `_enter_fence`, made where reading resumes
        (`_restart`) instead of at the start of the tail, with the restart's
        opener line in front so that the parser reads the fence inside its
        containers. The block shown is taken from an ordinary conversion of
        those lines, so its indent is the one the containers give it.
        """
        restart = self._restart
        if restart is None:
            return False
        tail = self._tail
        begin = restart.offset
        first = tail.find("\n", begin) + 1
        second = tail.find("\n", first) + 1 if first else 0
        if not second or not _FENCE_MARK.search(tail, begin, first):
            return False
        resume = restart.resume
        prefix = resume.opener + tail[begin:second]
        found = self._fence_at(prefix, self._live_theme, resume.shape)
        if found is None or found.closed or len(found.lines) != 1:
            return False
        document, _, _ = self._blocks_of(
            self._tokens_of(prefix),
            prefix,
            _line_starts(prefix),
            self._live_theme,
            self._resolve,
            first=len(resume.shape),
            state=restart.live.state,
        )
        if len(document.blocks) != 1 or not isinstance(document.blocks[0], CodeBlock):
            return False
        shown = replace(document.blocks[0], lines=())
        self._fence = _LiveFence(
            prefix=prefix,
            lines=found.lines,
            starts=[begin, first, second],
            live=shown,
            commit=shown,
            base=restart,
        )
        return True

    def _grow_fence(self) -> bool:
        """
        Read what is new of the fence. True if it is still open and has been shown.

        False when the fence is over, and then `_fence` is `None`. Either a
        new line closed it -- it is committed here, with the lines up to its
        closing one, and the tail now starts after that -- or the parser did
        not find the fence this object says is there, which no source is known
        to cause and which is answered by forgetting the fence and parsing the
        tail whole.
        """
        fence = self._fence
        assert fence is not None
        base = fence.base
        shape = base.resume.shape if base is not None else ()
        tail = self._tail
        starts = fence.starts
        read = starts[-1]
        complete = tail.rfind("\n") + 1
        if complete > read:
            chunk = tail[read:complete]
            found = self._fence_at(fence.prefix + chunk, self._live_theme, shape)
            if found is None or not (found.closed or len(found.lines) == chunk.count("\n") + 1):
                # Not a fence, or an open one that does not hold every line it
                # was given -- inside a container, a line that is not indented
                # far enough ends the item and the fence with it.
                self._fence = None
                return False
            fresh = found.lines[1:]
            position = chunk.find("\n")
            while position != -1:
                starts.append(read + position + 1)
                position = chunk.find("\n", position + 1)
            fence.lines.extend(fresh)
            if found.closed:
                # The opener, the content lines, and the line that closed it.
                through = len(fence.lines) + 2
                if base is not None:
                    # Nothing commits: the container is still open. The fence
                    # becomes one of its kept children instead.
                    self._keep_nested_fence(fence, base, through)
                    self._fence = None
                    return False
                span = _span((0, through), starts, tail)
                self._committed += (_filled(fence.commit, fence.lines),)
                self._committed_sources += (self._shifted(BlockSource(span=span, top=span)),)
                self._advance(starts[through], through)
                self._examined = 0
                self._fence = None
                return False
        self._examined = complete

        lines = fence.lines
        unfinished = tail[complete:]
        if base is not None:
            return self._show_nested_fence(fence, base, unfinished)
        if unfinished:
            # The line still being typed is content -- unless, as it stands, it
            # would close the fence, in which case the parser returns no line
            # for it. Either way it is asked again when more of it arrives.
            found = self._fence_at(fence.prefix + unfinished, self._live_theme)
            if found is None:
                self._fence = None
                return False
            lines = lines + found.lines[1:]
            starts.append(len(tail))
        span = _span((0, len(starts) - 1), starts, tail)
        if unfinished:
            starts.pop()
        self._live = (_filled(fence.live, lines),)
        self._live_sources = (self._shifted(BlockSource(span=span, top=span)),)
        self._live_parsed = None
        return True

    def _keep_nested_fence(self, fence: _LiveFence, base: _Restart, through: int) -> None:
        """
        A followed fence inside a container has closed: resume after it from now on.

        `through` is how many of the fence's lines there are, closing line
        included. The restart is moved past them and the fence joins the kept
        blocks, without reading it again: what the converter's state is after
        a fence, and what opener re-opens its containers, do not depend on how
        many lines it had, so both are taken from the fence's first content
        line and its closing line parsed alone, and the lines already
        converted are put into the block that parse gives.

        If any of that is not as expected the restart is left where it was, at
        the fence's first line, and the ordinary read that follows parses the
        fence whole once and finds the same place itself. Slower, not wrong.
        """
        tail = self._tail
        starts = fence.starts
        resume = base.resume
        short = fence.prefix + tail[starts[through - 1] : starts[through]]
        tokens = self._tokens_of(short)
        if not _opens(tokens, resume.shape):
            return
        marks = _line_starts(short)
        skip = len(resume.shape)
        point = _resume_point(tokens, short, marks, skip)
        # Line 4 of opener, fence line, content line, closing line: the line
        # after a fence that is closed and is the last block there is.
        if point is None or point.line != 4:
            return
        held = [(base.commit, self._commit_theme)]
        if base.live is not base.commit:
            held.append((base.live, self._live_theme))
        kept: list[_Kept] = []
        for before, theme in held:
            document, count, state = self._blocks_of(
                tokens,
                short,
                marks,
                theme,
                self._resolve,
                first=skip,
                state=before.state,
                mark=point.mark,
            )
            block = document.blocks[0] if document.blocks else None
            if state is None or count != 1 or not isinstance(block, CodeBlock):
                return
            filled = _filled(replace(block, lines=()), fence.lines)
            kept.append(_Kept((*before.blocks, filled), state))
        span = _span((0, through), starts, tail).shifted(0, self._head_chars)
        span = SourceSpan(
            line_start=span.line_start + base.line + self._head_lines,
            line_end=span.line_end + base.line + self._head_lines,
            start=span.start,
            end=span.end,
        )
        self._restart = _Restart(
            resume=point,
            line=base.line + through,
            offset=starts[through],
            spans=(*base.spans, span),
            commit=kept[0],
            live=kept[-1],
        )

    def _show_nested_fence(self, fence: _LiveFence, base: _Restart, unfinished: str) -> bool:
        """
        `_grow_fence`'s last step for a fence inside a container: show it, or give up.

        At top level an unfinished line is the fence's or closes it. Inside a
        container it may be neither -- a line not indented far enough has left
        the list item, and is a block of its own -- and it may belong to the
        container without belonging to the fence (`_leading_fence` has the
        measured case). So the parser is handed the text as it stands and
        three things are read off its answer: that the fence is still the last
        block, where its range ends, and where its container's does. Anything
        but "still the last block" forgets the fence, and the ordinary read
        shows whatever the text now is.
        """
        tail = self._tail
        starts = fence.starts
        lines = fence.lines
        through = fenced = len(starts) - 1
        if unfinished:
            found = self._fence_at(
                fence.prefix + unfinished, self._live_theme, base.resume.shape, verbatim=True
            )
            if found is None or not found.last:
                if found is not None and self._show_past_nested_fence(fence, base, found):
                    return True
                self._fence = None
                return False
            lines = lines + found.lines[1:]
            # The prefix is the opener line, the fence's opening line and its
            # first content line; the unfinished line is the one after those.
            fenced += found.end > 3
            through += found.outer_end > 3
            starts.append(len(tail))
        span = _span((0, fenced), starts, tail)
        outer = _span((0, through), starts, tail)
        if unfinished:
            starts.pop()
        # The fence's lines are counted from the restart; the container it is
        # in runs from the tail's first line.
        span = SourceSpan(
            line_start=span.line_start + base.line,
            line_end=span.line_end + base.line,
            start=span.start,
            end=span.end,
        )
        top = SourceSpan(line_start=0, line_end=outer.line_end + base.line, start=0, end=outer.end)
        block = _filled(fence.live, lines)
        self._show(_Parsed(base.live.blocks, base.spans, top, (block,), (BlockSource(span, top),)))
        return True

    def _show_past_nested_fence(self, fence: _LiveFence, base: _Restart, found: _Fence) -> bool:
        """
        Show a followed fence and, after it, the unfinished line that has left it.

        `found` is the parser's reading of the opener line, the fence's first
        two lines and the unfinished line, exactly as it stands, in which the
        fence is not the last block: the line being typed is not indented far
        enough, or lacks the quote's `>`, and is a block of its own -- the
        next list item, as a rule. That used to forget the fence, and the read
        that followed parsed its container from the fence's first line: once
        per piece of the line, the whole fence each time (review 5, item 3:
        7339 characters for one character under a fence of 3616).

        Instead the fence is kept and those same four lines are converted. The
        first block they give is the fence with one line, and what is shown in
        its place is the fence with every line it has; the blocks after it are
        shown as they are. **That rests on a claim like the one `_grow_fence`
        makes for complete lines**: what the parser makes of a line that ends
        an open fence without closing it -- which containers it also ends,
        what it begins -- does not depend on how many lines the fence had
        before it. markdown-it's block rules look at the line in hand and the
        indents of the containers open, and the fence's rule has stopped; no
        source is known that says otherwise, and `tests/test_stream.py` holds
        the result equal to a whole parse after every character of eighteen
        such lines, the review's battery besides.

        Spans are the one thing the short text cannot give directly. Its lines
        are the opener (0), the fence's opening line (1), its first content
        line (2) and the unfinished line (3); in the tail the fence has all
        its complete lines between 2 and 3. So a line number is moved to the
        tail's through `fence.starts`, and each span cut again from the tail
        by `_span`, which drops blank lines at a span's end the way the whole
        parse does -- a fence may have any number of those before the line
        that leaves it.

        False, having shown nothing, if the short parse is not that picture:
        the fence closed or grown, a block that begins before the unfinished
        line. The caller then forgets the fence and reads the long way, which
        is always right.

        The fence is not forgotten here. The line may be typed for many more
        pieces and each is answered by this; when it ends, `_grow_fence` is
        handed a line the fence does not hold and forgets it as before.
        """
        if found.closed or len(found.lines) != 1 or found.end != 3:
            return False
        tail = self._tail
        resume = base.resume
        short = fence.prefix + tail[fence.starts[-1] :]
        tokens = self._tokens_of(short)
        if not _opens(tokens, resume.shape):
            return False
        marks = _line_starts(short)
        document, _, _ = self._blocks_of(
            tokens,
            short,
            marks,
            self._live_theme,
            self._resolve,
            first=len(resume.shape),
            state=base.live.state,
        )
        blocks, sources = document.blocks, document.sources
        # One block, when the line is so far an item with nothing in it (`2.`).
        if not blocks or len(sources) != len(blocks) or not isinstance(blocks[0], CodeBlock):
            return False
        # Offsets in the tail of each complete line of the fence, of the
        # unfinished line, and of the end of the text.
        edges = [*fence.starts, len(tail)]
        count = len(fence.starts) - 1
        line = {1: 0, 2: 1, 3: count, 4: count + 1}

        def placed(span: SourceSpan, begin: int) -> SourceSpan | None:
            # `span` of the short text as a span of the tail, if it starts on
            # short line `begin`. Line numbers count from the tail's start.
            if span.line_start != begin or span.line_end not in line or span.line_end <= begin:
                return None
            if begin == 0:
                # The container, which starts where the tail does and not
                # where reading resumed.
                cut = _span((0, line[span.line_end]), edges, tail)
                return SourceSpan(0, cut.line_end + base.line, 0, cut.end)
            cut = _span((line[begin], line[span.line_end]), edges, tail)
            return SourceSpan(
                cut.line_start + base.line, cut.line_end + base.line, cut.start, cut.end
            )

        top = placed(sources[0].top, 0)
        own = placed(sources[0].span, 1)
        if top is None or own is None or sources[0].span.line_end != 3:
            return False
        fresh: list[BlockSource] = [BlockSource(own, top)]
        for source in sources[1:]:
            span = placed(source.span, 3)
            outer = top if source.top.line_start == 0 else placed(source.top, 3)
            if span is None or outer is None:
                return False
            fresh.append(BlockSource(span, outer))
        shown = (_filled(fence.live, fence.lines), *blocks[1:])
        self._show(_Parsed(base.live.blocks, base.spans, top, shown, tuple(fresh)))
        return True

    # -- a table being written ---------------------------------------------

    def _table_of(self, text: str, theme: Theme) -> tuple[TableBlock, int, int] | None:
        """
        The table `text` begins with: the block, the line it ends before, and how many blocks.

        `None` unless the first thing the parser finds is a table that starts
        on the first line. The line is markdown-it's own (`token.map`), not a
        `SourceSpan`'s, which has had blank lines trimmed from it; the count
        is of every block `text` converts to, so one means the table is all
        there is.
        """
        tokens = self._tokens_of(text)
        if not tokens or tokens[0].type != "table_open" or not tokens[0].map:
            return None
        if int(tokens[0].map[0]) != 0:
            return None
        document, _, _ = self._blocks_of(tokens, text, _line_starts(text), theme, self._resolve)
        if not document.blocks or not isinstance(document.blocks[0], TableBlock):
            return None
        return document.blocks[0], int(tokens[0].map[1]), len(document.blocks)

    def _enter_table(self) -> bool:
        """
        Start following the tail as a table, if its first two lines are a header and a delimiter.

        Two *complete* lines that, parsed on their own, are a table of no
        rows and nothing else. Complete, because a delimiter row still being
        typed can stop being one (`|---|x`). At top level only: a table
        inside a list item or a quote is its container's last child and is
        read with it (`_read_resumed`), whole, as before.
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
        if self._commit_theme is not self._live_theme:
            other = self._table_of(prefix, self._commit_theme)
            if other is None or other[0].rows:
                return False
            commit = other[0]
        self._table = _LiveTable(
            prefix=prefix, rows=[], starts=[0, first, second], live=found[0], commit=commit
        )
        return True

    def _grow_table(self) -> bool:
        """
        Read what is new of the table. True if it is still the tail and has been shown.

        **Each new complete line is parsed under the header and delimiter
        alone**, not under the rows before it, and the rows it gives are
        added to the ones kept. That rests on a claim of the same kind as the
        fence's: *whether a line is a row of an open table, and what its
        cells are, depends on that line and on the table's header and
        delimiter rows, and on no other row*. markdown-it's table rule
        (`rules_block/table.py`) goes down the lines one at a time and for
        each asks whether it is blank, whether it is indented four columns,
        and whether another block could start on it -- all questions about
        the line -- then splits it into the header's number of cells. It was
        read for this; it is not a documented interface, and
        `tests/test_stream.py` holds the result equal to a whole parse after
        every piece of every table it has.

        **The table commits when a complete line arrives that is not a row of
        it** -- a blank line, almost always -- with the rows before that
        line, and the tail then starts on that line. The ordinary rule would
        wait for the first line of the *next block* to end, and read the
        whole table again for every piece of it. The claim for committing
        there is the first one over again: the line is complete, so what it
        is cannot change, and a table that a line has ended is not re-opened
        by anything after it.

        A line still being typed is asked about the same way, as it stands.
        If the answer is the table and nothing else it is shown, with that
        line as its last row when the parser makes it one. If it is anything
        more -- the line has become a heading, a fence, a list item, which
        end a table without a blank line -- the tail is parsed whole for this
        one read and the table is kept: that is the slow answer and the right
        one, for a shape nothing was measured writing.

        False when the table is over, and then `_table` is `None`: committed
        as above, or forgotten because the parser did not find the table
        this object says is there, which no source is known to cause and
        which is answered by parsing the tail whole.
        """
        table = self._table
        assert table is not None
        tail = self._tail
        starts = table.starts
        read = starts[-1]
        complete = tail.rfind("\n") + 1
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
            table.rows.extend(block.rows)
            position = chunk.find("\n")
            for _ in range(fresh):
                starts.append(read + position + 1)
                position = chunk.find("\n", position + 1)
            if fresh < count:
                # A complete line that is not a row: the table is over.
                through = len(starts) - 1
                span = _span((0, through), starts, tail)
                self._committed += (replace(table.commit, rows=tuple(table.rows)),)
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
        kept = tuple(map(BlockSource, parsed.spans, repeat(top)))
        return kept + fresh

    def _shifted(self, source: BlockSource) -> BlockSource:
        return BlockSource(
            span=source.span.shifted(self._head_lines, self._head_chars),
            top=source.top.shifted(self._head_lines, self._head_chars),
        )


def _filled(template: CodeBlock, lines: list[tuple[Node, ...]]) -> CodeBlock:
    """
    `template` with `lines` as its lines, less the blank ones at their end.

    The trimming `advtext.markdown` does when it builds a `CodeBlock` from
    source, done here to lines that were kept untrimmed while the fence grew.
    """
    count = len(lines)
    while count and not lines[count - 1]:
        count -= 1
    return replace(template, lines=tuple(lines[:count]))

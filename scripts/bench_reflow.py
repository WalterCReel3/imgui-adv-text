r"""
Time a reflow, so every claim about layout performance in this project is measured.

A **reflow** is what happens between two frames when the window changes width:
`compose` breaks every paragraph to the new measure, `ship` flattens the packed
box into absolute draw commands, and `SelectionModel.from_commands` indexes
those commands for hit testing. Those three are the whole of it, and this script
times them separately because they have very different shapes -- one is a line
breaker and the other two are linear walks.

**Markdown parsing is not part of a reflow and is not in the reflow tables.** For
a document that is handed over whole it happens exactly once, when the file is
opened. Timing it into a reflow total would inflate the denominator and flatter
every later optimisation by making it look like a smaller fraction of a bigger
number. It is reported on its own lines above the tables, as context, and never
added in.

**Two parse figures are printed and they differ by more than an order of
magnitude.** This docstring used to say that building the document "costs
roughly as much as several reflows". That was the *first* parse in a process,
which pays for opening and reading the font files `fontlib_metrics` resolves:
measured 2026-10-06 on the 37-block sample, 361ms and 611ms on two runs. A
second parse of the same source, with the metrics already resident, measured
11.0-11.6ms -- a tenth of one cold reflow, not several. The header prints both,
labelled, because a host that streams re-parses many times and pays the second
figure, not the first.

**A streamed document is the one case where parsing *is* per-change work**, and
table 6 exists for it: there the parse is inside the total, because a host that
is handed text a word at a time has to re-parse to find out what the word did.

Run it with:

    python scripts/bench_reflow.py --widths 300,420,800 --repeat 5

**Best of N, not the mean.** A Python process under a shared machine has a noise
floor that is one-sided: nothing makes a run faster than the work it does, so the
minimum is the closest estimate of the real cost available and the mean measures
the machine's other tenants. Compare minima between two runs of this script and
the comparison is about the code.

## What the tables say

1. **Cold reflow** -- no cache anywhere, which is what the tree did before
   `LayoutCache` existed. This is the number to compare across revisions.
2. **Warm cache at an unchanged width** -- one `LayoutCache`, composed twice at
   the same measure. This is a theme-independent redraw, a selection change, or
   any re-render that did not resize: the second pass should cost almost nothing.
3. **Resize drag** -- one `LayoutCache` carried across a run of *consecutive*
   widths one point apart, so every frame is a width the cache has never seen.
   That is what a drag is, and best-of-N over repeats of the same width would
   quietly measure a cache hit instead. **This table is expected to show no
   win**, because a text block broken to 300pt tells you nothing about the same
   block at 301pt. It is here so that the absence is measured rather than
   assumed, and the hit count beside it says exactly how much did survive; see
   `advtext.ui.LayoutCache`.
4. **Composition by block** -- each block composed alone, heaviest first. The
   cost of breaking a paragraph grows far faster than its length, so one
   paragraph of `demo/sample.md` is a third of the document's total and an
   average per block would hide that. This is the table to read before optimising
   the breaker, and the one that says what viewport culling would be worth.
5. **One block edited** -- the case `DocumentView`'s own per-width cache cannot
   express, because `invalidate` drops the whole layout and a re-compose then
   re-breaks every block to recover from a change to one. The edit lands on the
   sample's *most expensive* paragraph, so this is the pessimistic end.
6. **Streaming** -- what one appended word costs when the document arrives a
   word at a time and the host does the only thing the library offers today:
   re-parse everything received so far, compose it through a `LayoutCache`,
   ship it, and index it. All four phases are in the total. Table 5 is not this
   number: `_after_an_edit` starts its clock after `build_document` returns and
   stops it when `compose` does, so it leaves out the parse, the ship and the
   index. See `time_stream_append`. **This row is the baseline a streaming view
   has to beat, not a streaming implementation**; nothing here is incremental
   except what `LayoutCache` already was. A word is a run of non-space and the
   space after it, and `demo/sample.md` is 963 words by that rule.

   One run of table 6 at 420pt, `--repeat 5`, on a machine other agents were
   loading at the time (so read ratios, not absolutes; the counts are exact and
   `tests/test_bench_numbers.py` re-derives them):

       | words   | blocks | tail nodes | parse   | compose | ship   | index  | total   |
       | 241/963 |      7 |         52 |  2.57ms |  1.14ms | 1.80ms | 0.57ms |  6.08ms |
       | 482/963 |     12 |        288 |  5.18ms |  5.14ms | 3.42ms | 1.06ms | 14.81ms |
       | 722/963 |     29 |          1 |  8.17ms |  2.15ms | 5.30ms | 1.63ms | 17.25ms |
       | 963/963 |     37 |        635 | 11.13ms | 37.19ms | 7.31ms | 2.23ms | 57.87ms |

   Parse, ship and index grow with what has already arrived whichever block
   the word lands in: at the last word they are 20.7ms of the 57.9ms, and at
   word 722, where the tail block is a single node, they are 15.1ms of 17.3ms.
   Compose is the one column that follows the tail block and not the document.

   **The streaming view, against that baseline** (added 2026-10-07). The same
   appended word through `advtext.stream.StreamDocument` and
   `advtext.ui.stream_view.StreamView`: the stream re-parses its unfinished
   tail and not the document, and the view composes, ships and indexes the
   live unit and finds the rest (`time_stream_view_append`). `frame` is what
   the next frame then does that it did not do before -- move the visible
   units into place and index the one under the mouse. One run at 420pt,
   `--repeat 5`, same loaded machine, a 768px window following the tail:

       | words   | units | parse  | layout | frame  | total  |
       | 241/963 |     7 | 0.30ms | 0.61ms | 0.13ms | 1.03ms |
       | 482/963 |    12 | 0.58ms | 2.55ms | 0.43ms | 3.55ms |
       | 722/963 |    29 | 1.90ms | 0.51ms | 0.12ms | 2.53ms |
       | 963/963 |    37 | 1.31ms | 5.96ms | 0.82ms | 8.09ms |

   The baseline table printed in the same run read 5.83, 14.28, 16.85 and
   55.33ms for the same four words, so that is the pair to compare; the
   figures quoted above it are an earlier run. Every one of these layouts
   shipped exactly one unit. The last row is the 635-node paragraph being
   broken again, which is still most of its cost and is now a first-fit break
   (the live tail is ragged), not the 36ms total-fit break the baseline row
   paid. The parse column does not fall to nothing: the stream re-parses its
   whole unfinished top-level block, and at word 722 that block is a list.

   **What this table does not show, because the sample has no long code
   block:** a fenced block still open is one live unit, and it is composed and
   shipped whole on every appended line. Measured separately on 2026-10-07 (a
   throwaway script; 560px): 61.8ms a line at 600 lines, about 11ms at 100,
   of which compose is a third and ship the rest. The stream's own parse of
   an open fence is flat (0.2ms). Making that cost independent of the fence's
   length needs a code block to be several units, which it is not.

   **Later on 2026-10-07 it became several units**, in a `StreamView` only
   (`advtext.ui.units.layout_units(..., code_lines=16)`). Its builder's figures,
   same shape of script on a busier machine with longer lines: 106.8ms a line
   at 600 lines before and 1.9ms after, 492ms and 4.2ms at 2000
   (`.concerns/AF-codeunits--builder--result.md`). Not shown by this table
   either: a table that is still streaming. A row per append, three columns,
   560px, 2026-10-07, it was linear: 6.4ms at 20 rows, 16.9ms at 50, 31.7ms at
   100, parse and layout together, about a third of it parse. Later the same
   day a top-level live table was followed row by row in the stream and laid
   out as pieces of four rows in a `StreamView`
   (`layout_units(..., table_rows=4)`); its builder's figures for the same
   script are 0.83 to 1.21ms a row from 10 to 200 rows
   (`.concerns/AF-livetable--builder--result.md`). A table inside a list item
   or a quote is not followed and was not measured.

7. **Ragged right against justified** -- printed only with `--ragged`, because
   it is slow, and it is slow because of what it found. The sample's heaviest
   paragraph composed alone, once with the default theme's `Align.JUSTIFY` and
   once with `Align.LEFT`, which `advtext.ui` implements as a `\rightskip` of
   infinitely stretchable glue. Measured 2026-10-06, single runs on a loaded
   machine, the same 635 nodes both ways:

       | width | justified | ragged    |
       | 300pt |   26.91ms | 2201.71ms |
       | 420pt |   39.54ms | 3303.91ms |
       | 800pt |   27.71ms | 8679.98ms |

   The whole 37-block sample, every block set ragged, was timed once by a
   throwaway script this table replaces and not by this one: 7.2s, 12.0s and
   28.2s to compose at the three widths, against 0.13s, 0.12s and 0.12s
   justified. Ragged gets worse as the measure widens.

   **Composition no longer takes that path by default.** Since 2026-10-06 a
   block that is not justified is broken first-fit at natural spacing
   (`advtext.ui._text_boxes`), so the `ragged` column above is now what
   `ComposeParams(ragged_total_fit=True)` costs -- the old path, kept
   reachable -- and the table prints a third column for what a ragged block
   costs today. One run, 2026-10-07, at 300 / 420 / 800pt: justified 26.58 /
   33.97 / 24.34ms, ragged total-fit 1976.89 / 2920.45 / 7572.08ms, ragged
   first-fit 4.58 / 5.14 / 7.40ms.

   That is a measurement. The explanation is an inference from reading
   `advtext/linebreak.py` and has not been tested: under an infinitely
   stretchable `\rightskip` no line short of the measure is ever infeasible, so
   every legal breakpoint stays active under every line number it can be
   reached at, and the module's docstring records that `easy_line` (the merge
   of active nodes that differ only in line number) and delta nodes were left
   out as "free at paragraph sizes". They were measured against justified
   setting. Headings are `Align.LEFT` too and do not show this because they are
   one line long.

Deliberately out of scope: timing the ImGui backend, which needs a font atlas
and belongs in `scripts/verify_advances.py`'s idiom rather than here; and
per-function profiling, which `python -m cProfile` already does better.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advtext.markdown import Block, Document, TextBlock, build_document
from advtext.nodes import Box
from advtext.pack import CharMeasure
from advtext.selection import SelectionModel
from advtext.shipout import DrawCmd, Line, Point, ship
from advtext.stream import StreamDocument
from advtext.style import Align, Theme, char_measure, fontlib_metrics
from advtext.ui import (
    PROSE_BREAKING_TOTAL_FIT_RAGGED,
    CacheStats,
    CommandIndex,
    LayoutCache,
    Viewport,
    compose,
    compose_blocks,
)
from advtext.ui.stream_view import StreamView
from advtext.units import Scaled, sp_from_pt, sp_from_px

__all__ = [
    "DEFAULT_STREAM_AT",
    "StreamTiming",
    "ViewTiming",
    "Timing",
    "main",
    "ragged",
    "time_ragged_block",
    "time_reflow",
    "time_stream_append",
    "word_ends",
]

DEFAULT_WIDTHS = "300,420,800"
"""
Three measures: narrow enough to break badly, the litmus measure, and wide.

`scripts/render_litmus.py` sets its artifacts at 420pt, so the middle column is
directly comparable with everything in `docs/litmus.md`.
"""

DEFAULT_STREAM_AT = "0.25,0.5,0.75,1.0"
"""
How far into the source the streaming table samples, as fractions of its words.

Four points and not every word: one row costs a whole-document compose per
repeat to put the cache back, so timing every append of the sample (the module
docstring has its word count) would take minutes to say what four rows say. The
cost of an append depends on how much has already arrived (parse, ship and index
are linear in it) and on which block the word lands in (compose re-breaks that
one block), and the rows print both so neither is averaged away.

`1.0` is the last word of the source, which for `demo/sample.md` lands in the
document's heaviest paragraph -- the same pessimistic end `_after_an_edit` times,
so the two tables can be read against each other.
"""

_WORD = re.compile(r"\S+\s*")
"""
A word and the whitespace after it: the unit the streaming table appends.

The trailing whitespace travels with the word so that the last prefix is the
whole source, byte for byte, and so that a blank line arrives with the word
before it rather than as an append of its own that changes no glyph.
"""

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Timing:
    """
    One width's reflow, split into its three phases. Milliseconds.

    `total` is the sum of the three and not a separately measured wall clock:
    the three are timed independently so that each is a best-of-N in its own
    right, and a best-of-N of the sum would be a different and less useful
    number.
    """

    width_pt: float
    compose_ms: float
    ship_ms: float
    index_ms: float

    @property
    def total_ms(self) -> float:
        """
        The whole reflow, against a 16.7ms budget at 60fps.
        """
        return self.compose_ms + self.ship_ms + self.index_ms


def _best(repeat: int, work: Callable[[], T]) -> tuple[float, T]:
    """
    Milliseconds for the fastest of `repeat` runs, and the last result.

    The result is returned so the caller can feed one phase's output into the
    next without a fourth untimed run producing it.
    """
    best = float("inf")
    result = work()
    for _ in range(repeat):
        start = time.perf_counter()
        result = work()
        best = min(best, time.perf_counter() - start)
    return best * 1000.0, result


def time_reflow(
    document: Document,
    theme: Theme,
    width: Scaled,
    repeat: int,
    measure: CharMeasure,
    cache: LayoutCache | None = None,
) -> Timing:
    """
    Time one reflow at one width, best of `repeat`.

    `cache` is passed straight through to `compose`, so the same function times
    the cold and the warm case and the two are comparable by construction.

    `measure` is a parameter and not built here **because `LayoutCache` keys it
    by identity**: a fresh `char_measure` closure per call would miss on every
    lookup and the warm table would read as a cache that does not work. It is
    the same constraint a real UI is under, which is why it is not hidden.

    Note that a warm run repeated `repeat` times measures the *cache hit*: the
    first call fills it and every later one reads it. That is the intended
    measurement -- the cold number is the one taken with `cache=None`.
    """

    def do_compose() -> Box:
        return compose(document, theme, width, measure, cache=cache)

    compose_ms, box = _best(repeat, do_compose)

    def do_ship() -> list[DrawCmd]:
        return ship(box, Point(0, box.height), measure=measure)

    ship_ms, cmds = _best(repeat, do_ship)

    def do_index() -> SelectionModel:
        return SelectionModel.from_commands(cmds)

    index_ms, _ = _best(repeat, do_index)
    return Timing(
        width_pt=width / 65536.0,
        compose_ms=compose_ms,
        ship_ms=ship_ms,
        index_ms=index_ms,
    )


@dataclass(frozen=True, slots=True)
class StreamTiming:
    """
    What one appended word costs a host that re-does the whole document. Milliseconds.

    `words` and `blocks` describe the document *after* the append. `tail` and
    `tail_nodes` name the last block, which is the one the word landed in and
    the only one `compose` had to break again -- `misses` says whether that is
    what happened. `hits` and `misses` are the timed `compose` call's own, not
    the cache's lifetime totals: the pass that warmed the cache is subtracted.

    `index_ms` is **both** indexes `DocumentView.layout_for` builds after a
    ship -- `CommandIndex.of` for culling and `SelectionModel.from_commands` for
    hit testing -- because a view pays for both on every change. `Timing.index_ms`
    in the reflow tables is the selection model alone, so the two columns are
    not the same quantity and are labelled differently in the output.
    """

    width_pt: float
    words: int
    blocks: int
    tail: str
    tail_nodes: int
    parse_ms: float
    compose_ms: float
    ship_ms: float
    index_ms: float
    hits: int
    misses: int

    @property
    def total_ms(self) -> float:
        """
        Parse, compose, ship and index: everything between a word and a frame.

        A sum of four independent best-of-N figures and not a measured wall
        clock, for the reason `Timing.total_ms` gives.
        """
        return self.parse_ms + self.compose_ms + self.ship_ms + self.index_ms


def word_ends(source: str) -> list[int]:
    """
    The offset just past each word of `source`, whitespace included.

    `source[: word_ends(source)[k]]` is the document after `k + 1` words have
    arrived. Offsets rather than the prefixes themselves, because the prefixes
    of a long source are quadratic in its length and nothing needs them all at
    once.

    **A prefix is cut wherever a word ends, with no regard for markdown**, and
    that is the point: a fence may be open, a `**` unclosed, a table half a row
    long. That is what a stream looks like, and `tests/test_bench_numbers.py`
    checks that every prefix of the sample still builds.
    """
    return [match.end() for match in _WORD.finditer(source)]


def time_stream_append(
    source: str,
    theme: Theme,
    width: Scaled,
    repeat: int,
    measure: CharMeasure,
    word: int,
) -> StreamTiming:
    """
    Time appending word number `word` (1-based) of `source`, best of `repeat`.

    The state before the append is the first `word - 1` words, already parsed
    and composed through a `LayoutCache` -- what a host holds after the previous
    frame. The append is then the four things a host with only today's
    whole-document API must do:

    1. **parse** -- `build_document` over everything received so far. There is no
       incremental parser, so this is linear in the document and not in the word.
    2. **compose** -- through the cache, so every block the word did not touch is
       a hit and only the last block is broken again.
    3. **ship** -- the whole packed box, because `ship` has no notion of a block.
    4. **index** -- `CommandIndex.of` and `SelectionModel.from_commands` over the
       whole command list, for the same reason.

    Each phase is its own best-of-N, as in `time_reflow`.

    **The compose repeat rebuilds its state every time, and has to.** After one
    timed `compose` the cache holds the new last block, so a second timed call
    would be all hits and best-of-N would report the cost of a redraw. So each
    repeat starts a fresh cache, warms it with the previous prefix (untimed),
    and re-parses the new prefix so that no block is reused by identity -- the
    cache keys blocks by value, the discipline `_after_an_edit` records.

    `measure` is shared across the warm-up and the timed call for the reason
    `time_reflow` gives: the cache keys it by identity.
    """
    ends = word_ends(source)
    if not 1 <= word <= len(ends):
        raise ValueError(f"word must be in 1..{len(ends)}, got {word}")
    before = source[: ends[word - 2]] if word >= 2 else ""
    after = source[: ends[word - 1]]

    def do_parse() -> Document:
        return build_document(after, theme, fontlib_metrics)

    parse_ms, document = _best(repeat, do_parse)

    previous = build_document(before, theme, fontlib_metrics)
    best = float("inf")
    hits = misses = 0
    box = compose(document, theme, width, measure)
    for _ in range(repeat):
        cache = LayoutCache()
        compose(previous, theme, width, measure, cache=cache)
        warmed = cache.stats()
        fresh = build_document(after, theme, fontlib_metrics)
        start = time.perf_counter()
        box = compose(fresh, theme, width, measure, cache=cache)
        best = min(best, time.perf_counter() - start)
        done = cache.stats()
        hits, misses = done.hits - warmed.hits, done.misses - warmed.misses

    def do_ship() -> tuple[DrawCmd, ...]:
        return tuple(ship(box, Point(0, box.height), measure=measure))

    ship_ms, cmds = _best(repeat, do_ship)

    def do_index() -> tuple[CommandIndex, SelectionModel]:
        return CommandIndex.of(cmds), SelectionModel.from_commands(cmds)

    index_ms, _ = _best(repeat, do_index)

    tail = document.blocks[-1] if document.blocks else None
    return StreamTiming(
        width_pt=width / 65536.0,
        words=word,
        blocks=len(document.blocks),
        tail=type(tail).__name__ if tail is not None else "-",
        tail_nodes=len(tail.material) if isinstance(tail, TextBlock) else 0,
        parse_ms=parse_ms,
        compose_ms=best * 1000.0,
        ship_ms=ship_ms,
        index_ms=index_ms,
        hits=hits,
        misses=misses,
    )


def ragged(theme: Theme) -> Theme:
    """
    `theme` with every block `Align.LEFT`: ragged right, nothing else changed.

    The faces and sizes are the theme's own, so a difference in compose cost
    between a document built with `theme` and one built with this is a
    difference between justified and ragged setting and not between two fonts.
    Alignment is carried on each block at `build_document` time, so the document
    has to be built with the theme it will be composed with.
    """
    return replace(
        theme,
        blocks={kind: replace(style, align=Align.LEFT) for kind, style in theme.blocks.items()},
    )


def time_ragged_block(
    source: str, theme: Theme, width: Scaled, repeat: int, measure: CharMeasure
) -> tuple[int, float, float]:
    """
    The heaviest text block of `source`, composed alone justified and then ragged.

    Returns its node count and the two best-of-`repeat` times in milliseconds.
    "Heaviest" is by node count under `theme`, the stand-in for cost that
    `tests/test_bench_numbers.py` uses for the same block; the ragged document's
    block at the same index is the same text, and the function refuses to
    compare them if it has a different number of nodes.

    One block and not the document, because the ragged document takes tens of
    seconds per pass and the block shows the same ratio.
    """
    loose = ragged(theme)
    justified = build_document(source, theme, fontlib_metrics).blocks
    unjustified = build_document(source, loose, fontlib_metrics).blocks
    index, block = max(
        ((i, b) for i, b in enumerate(justified) if isinstance(b, TextBlock)),
        key=lambda pair: len(pair[1].material),
    )
    other = unjustified[index]
    if not isinstance(other, TextBlock) or len(other.material) != len(block.material):
        raise ValueError(f"block {index} is not the same text under the ragged theme")
    justified_ms, _ = _best(repeat, lambda: compose_blocks((block,), theme, width, measure))
    # The total-fit breaker, asked for by name: composition's default for a
    # ragged block has been first-fit since 2026-10-06, and without this the
    # column would silently time a different algorithm from the one it reports.
    ragged_ms, _ = _best(
        repeat,
        lambda: compose_blocks((other,), loose, width, measure, PROSE_BREAKING_TOTAL_FIT_RAGGED),
    )
    return len(block.material), justified_ms, ragged_ms


def time_ragged_first_fit(
    source: str, theme: Theme, width: Scaled, repeat: int, measure: CharMeasure
) -> float:
    """
    The same heaviest block, ragged, as composition breaks it by default: first-fit.

    Milliseconds, best of `repeat`. The companion of `time_ragged_block`, whose
    ragged column is the total-fit breaker.
    """
    loose = ragged(theme)
    blocks = build_document(source, loose, fontlib_metrics).blocks
    block = max((b for b in blocks if isinstance(b, TextBlock)), key=lambda b: len(b.material))
    best, _ = _best(repeat, lambda: compose_blocks((block,), loose, width, measure))
    return best


@dataclass(frozen=True, slots=True)
class ViewTiming:
    """
    What one appended word costs through `StreamDocument` and `StreamView`. Milliseconds.

    `parse_ms` is the stream's deferred parse (its unfinished tail, not the
    document). `layout_ms` is `StreamView.sync` and `layout_for`: compose,
    ship and culling index of the live unit, and finding the rest. `frame_ms`
    is the work the next frame does for the first time: moving the visible
    units into place and indexing the tail unit for a hit test. `shipped` is
    how many units the timed layout shipped, which is the claim in a number.
    """

    width_pt: float
    words: int
    units: int
    shipped: int
    parse_ms: float
    layout_ms: float
    frame_ms: float

    @property
    def total_ms(self) -> float:
        return self.parse_ms + self.layout_ms + self.frame_ms


WINDOW_PX = 768.0
"""
The height of the pane the streaming view's `frame` column culls to.
"""


def time_stream_view_append(
    source: str,
    theme: Theme,
    width: Scaled,
    repeat: int,
    measure: CharMeasure,
    word: int,
) -> ViewTiming:
    """
    Time appending word number `word` (1-based) through the streaming view, best of `repeat`.

    The state before the append is a `StreamDocument` that has received the
    first `word - 1` words and a `StreamView` that has laid them out and drawn
    a frame's worth -- what a host holds after the previous frame. Each repeat
    rebuilds that state, because the append is not repeatable on a stream that
    has already taken it. The prefix is appended in one piece: the stream's
    blocks depend on the text and not on how it was cut, which
    `tests/test_stream.py` checks piece by piece.

    The three phases are timed in the order a frame runs them and each is its
    own best-of-N, as in `time_stream_append`.
    """
    ends = word_ends(source)
    if not 1 <= word <= len(ends):
        raise ValueError(f"word must be in 1..{len(ends)}, got {word}")
    before = source[: ends[word - 2]] if word >= 2 else ""
    piece = source[len(before) : ends[word - 1]]
    window = sp_from_px(WINDOW_PX)

    def touch(view: StreamView) -> None:
        layout = view.layout_for(width)
        layout.visible(Viewport(max(0, layout.height - window), layout.height))
        if layout.height:
            layout.model.hit(Point(0, layout.height - 1))

    parse = lay = frame = float("inf")
    units = shipped = 0
    for _ in range(repeat):
        stream = StreamDocument(theme, fontlib_metrics)
        view = StreamView(stream, measure)
        if before:
            stream.append(before)
        view.sync()
        touch(view)
        misses = view._units.stats().misses

        stream.append(piece)
        start = time.perf_counter()
        _ = stream.revision
        parsed = time.perf_counter()
        view.sync()
        layout = view.layout_for(width)
        laid = time.perf_counter()
        touch(view)
        done = time.perf_counter()

        parse = min(parse, parsed - start)
        lay = min(lay, laid - parsed)
        frame = min(frame, done - laid)
        units = len(layout.placed)
        shipped = view._units.stats().misses - misses
    return ViewTiming(
        width_pt=width / 65536.0,
        words=word,
        units=units,
        shipped=shipped,
        parse_ms=parse * 1000.0,
        layout_ms=lay * 1000.0,
        frame_ms=frame * 1000.0,
    )


def _stream_words(count: int, fractions: list[float]) -> list[int]:
    """
    Which 1-based word numbers a list of fractions of a `count`-word source names.

    Clamped to `1..count` and de-duplicated in order, so `0.0` means the first
    word rather than an append of nothing and a short source does not time one
    word four times.
    """
    words: list[int] = []
    for fraction in fractions:
        word = min(count, max(1, round(count * fraction)))
        if word not in words:
            words.append(word)
    return words


def _table(title: str, rows: list[Timing], note: str = "") -> str:
    """
    One markdown table, so the output can be pasted into a write-up unchanged.
    """
    lines = [f"### {title}", ""]
    if note:
        lines += [note, ""]
    lines += [
        "| width | compose | ship | selection index | total |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.width_pt:.0f}pt | {row.compose_ms:.2f}ms | {row.ship_ms:.2f}ms "
            f"| {row.index_ms:.2f}ms | {row.total_ms:.2f}ms |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """
    Parse the sample once, then time a reflow at every requested width.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--widths",
        default=DEFAULT_WIDTHS,
        help=f"comma-separated measures in points (default {DEFAULT_WIDTHS})",
    )
    parser.add_argument("--repeat", type=int, default=5, help="runs per phase; the best is kept")
    parser.add_argument(
        "--stream-at",
        default=DEFAULT_STREAM_AT,
        help=(
            "comma-separated fractions of the source's words at which the streaming "
            f"table times one append (default {DEFAULT_STREAM_AT}); empty to skip it"
        ),
    )
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parent.parent / "demo" / "sample.md"
    )
    parser.add_argument(
        "--ragged",
        action="store_true",
        help="also time the heaviest block set ragged right (slow: seconds per run)",
    )
    args = parser.parse_args(argv)

    widths = [sp_from_pt(float(part)) for part in args.widths.split(",") if part.strip()]
    if not widths:
        parser.error("--widths named no widths")

    theme = Theme.build()
    # One measure for the whole run, held the way a UI holds it: it memoises per
    # glyph, and LayoutCache keys it by identity.
    measure = char_measure(fontlib_metrics)
    source = args.source.read_text(encoding="utf-8")

    start = time.perf_counter()
    document = build_document(source, theme, fontlib_metrics)
    parse_ms = (time.perf_counter() - start) * 1000.0
    # The first parse paid for opening the font files; this one did not. It is
    # the figure a host that re-parses pays, and the streaming table's parse
    # column should agree with it at the last row.
    reparse_ms, _ = _best(args.repeat, lambda: build_document(source, theme, fontlib_metrics))

    print(f"source:     {args.source}")
    print(f"blocks:     {len(document.blocks)}")
    print(f"repeat:     best of {args.repeat}")
    print(
        f"parse:      {parse_ms:.1f}ms  (first in this process: font files opened. Once, on open)"
    )
    print(
        f"re-parse:   {reparse_ms:.1f}ms  (metrics resident. NOT part of a reflow; see Streaming)"
    )
    print("budget:     16.67ms per frame at 60fps")
    print()

    cold = [time_reflow(document, theme, width, args.repeat, measure) for width in widths]
    print(_table("Cold reflow, no cache", cold))

    warm: list[Timing] = []
    for width in widths:
        cache = LayoutCache()
        compose(document, theme, width, measure, cache=cache)
        warm.append(time_reflow(document, theme, width, args.repeat, measure, cache=cache))
    print(
        _table(
            "Re-render at an unchanged width, warm cache",
            warm,
            "A redraw that did not resize: a selection change, a scroll, an invalidation.",
        )
    )

    print("### Resize drag, one cache across consecutive widths\n")
    print("Every frame is a width never seen before, which is what a drag is.\n")
    print("| width | compose, best frame | cache hits | cache misses |")
    print("|---|---|---|---|")
    for width in widths:
        best, stats = _drag(document, theme, width, args.repeat, measure)
        print(f"| {width / 65536.0:.0f}pt | {best:.2f}ms | {stats.hits} | {stats.misses} |")
    print()

    print(f"### Composition by block, at {widths[0] / 65536.0:.0f}pt\n")
    print(
        "Where the time actually is. The cost of breaking a paragraph grows much\n"
        "faster than its length, so a document's total is dominated by its longest\n"
        "few blocks and an average per block is a misleading number.\n"
    )
    print("| block | kind | nodes | lines | compose |")
    print("|---|---|---|---|---|")
    for row in _by_block(document, theme, widths[0], args.repeat, measure)[:5]:
        index, kind, nodes, count, ms = row
        print(f"| {index} | {kind} | {nodes} | {count} | {ms:.2f}ms |")
    print()

    print("### One block edited, same width\n")
    print(
        "The case DocumentView's own per-width cache cannot express: it drops the\n"
        "whole layout on invalidate, so an edit to one paragraph re-breaks all of\n"
        "them. Compare against the cold table's compose column.\n"
    )
    print("| width | compose after the edit | cache hits | cache misses |")
    print("|---|---|---|---|")
    for width in widths:
        best, stats = _after_an_edit(source, theme, width, args.repeat, measure)
        print(f"| {width / 65536.0:.0f}pt | {best:.2f}ms | {stats.hits} | {stats.misses} |")
    print()

    fractions = [float(part) for part in args.stream_at.split(",") if part.strip()]
    if fractions:
        count = len(word_ends(source))
        print("### Streaming: one appended word, whole document re-done\n")
        print(
            "What a word costs a host that is handed text a piece at a time and has\n"
            "only the whole-document API: re-parse everything so far, compose through\n"
            "a warm LayoutCache, ship, and build both indexes. The parse is in the\n"
            "total here. `index` is CommandIndex + SelectionModel, which is more than\n"
            "the `selection index` column above. `tail` is the block the word landed in.\n"
        )
        print(
            "| width | words | blocks | tail | parse | compose | hits/misses "
            "| ship | index | total | % budget |"
        )
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for width in widths:
            for word in _stream_words(count, fractions):
                at = time_stream_append(source, theme, width, args.repeat, measure, word)
                print(
                    f"| {at.width_pt:.0f}pt | {at.words}/{count} | {at.blocks} "
                    f"| {at.tail} {at.tail_nodes} | {at.parse_ms:.2f}ms "
                    f"| {at.compose_ms:.2f}ms | {at.hits}/{at.misses} | {at.ship_ms:.2f}ms "
                    f"| {at.index_ms:.2f}ms | {at.total_ms:.2f}ms "
                    f"| {at.total_ms / (1000.0 / 60.0) * 100:.0f}% |"
                )
        print()

        print("### Streaming: the same appended word through StreamDocument and StreamView\n")
        print(
            "The stream parses its unfinished tail; the view composes, ships and\n"
            "indexes the live unit and finds the rest. `shipped` is how many units\n"
            "the timed layout shipped. `frame` is what the next frame does for the\n"
            f"first time in a {WINDOW_PX:.0f}px window that follows the tail.\n"
        )
        print("| width | words | units | shipped | parse | layout | frame | total | % budget |")
        print("|---|---|---|---|---|---|---|---|---|")
        for width in widths:
            for word in _stream_words(count, fractions):
                seen = time_stream_view_append(source, theme, width, args.repeat, measure, word)
                print(
                    f"| {seen.width_pt:.0f}pt | {seen.words}/{count} | {seen.units} "
                    f"| {seen.shipped} | {seen.parse_ms:.2f}ms | {seen.layout_ms:.2f}ms "
                    f"| {seen.frame_ms:.2f}ms | {seen.total_ms:.2f}ms "
                    f"| {seen.total_ms / (1000.0 / 60.0) * 100:.0f}% |"
                )
        print()

    if args.ragged:
        print("### Ragged right against justified, the heaviest block alone\n")
        print(
            "The same paragraph composed with Align.JUSTIFY, with Align.LEFT through\n"
            "the total-fit breaker (asked for by name; best of 1 whatever --repeat\n"
            "says, because that run is seconds long), and with Align.LEFT as\n"
            "composition breaks it by default, first-fit.\n"
        )
        print("| width | nodes | justified | ragged, total-fit | ratio | ragged, first-fit |")
        print("|---|---|---|---|---|---|")
        for width in widths:
            nodes, justified_ms, ragged_ms = time_ragged_block(source, theme, width, 1, measure)
            first_fit_ms = time_ragged_first_fit(source, theme, width, args.repeat, measure)
            print(
                f"| {width / 65536.0:.0f}pt | {nodes} | {justified_ms:.2f}ms "
                f"| {ragged_ms:.2f}ms | {ragged_ms / justified_ms:.0f}x | {first_fit_ms:.2f}ms |"
            )
        print()
    return 0


def _drag(
    document: Document,
    theme: Theme,
    width: Scaled,
    frames: int,
    measure: CharMeasure,
) -> tuple[float, CacheStats]:
    """
    Compose `frames` consecutive widths one point apart through one cache.

    Returns the fastest frame and what the cache had done by the end. The fastest
    frame is the fair comparison against the cold table's `compose` column, and
    the hit count is the honest account of how much a cache can carry across a
    width change at all.
    """
    cache = LayoutCache()
    step = sp_from_pt(1.0)
    best = float("inf")
    for frame in range(frames):
        start = time.perf_counter()
        compose(document, theme, width + frame * step, measure, cache=cache)
        best = min(best, time.perf_counter() - start)
    return best * 1000.0, cache.stats()


def _by_block(
    document: Document,
    theme: Theme,
    width: Scaled,
    repeat: int,
    measure: CharMeasure,
) -> list[tuple[int, str, int, int, float]]:
    """
    Every block's own composition cost, heaviest first.

    Measured by composing each block **alone**, through a one-block document, so
    the number is the block's own cost rather than a share of a profile. The
    stacking that joins them is a fraction of a millisecond and is not here.
    """
    rows: list[tuple[int, str, int, int, float]] = []
    for index, block in enumerate(document.blocks):
        one: tuple[Block, ...] = (block,)

        def just_this(blocks: tuple[Block, ...] = one) -> Box:
            return compose_blocks(blocks, theme, width, measure)

        nodes = len(block.material) if isinstance(block, TextBlock) else 0
        ms, _ = _best(repeat, just_this)
        rows.append((index, type(block).__name__, nodes, _lines_in(one, theme, width, measure), ms))
    return sorted(rows, key=lambda row: row[4], reverse=True)


def _lines_in(blocks: tuple[Block, ...], theme: Theme, width: Scaled, measure: CharMeasure) -> int:
    """
    How many lines one block occupies, for the table's sake.
    """
    box = compose_blocks(blocks, theme, width, measure)
    return sum(
        1 for cmd in ship(box, Point(0, box.height), measure=measure) if isinstance(cmd, Line)
    )


def _after_an_edit(
    source: str,
    theme: Theme,
    width: Scaled,
    repeat: int,
    measure: CharMeasure,
) -> tuple[float, CacheStats]:
    """
    Compose the document, edit one paragraph, and time composing it again.

    The edit is a word appended to the **last** paragraph of the source, so it
    changes exactly one `TextBlock` and leaves every other block equal to the one
    the cache already holds. Every repeat re-parses so the blocks are rebuilt
    rather than reused by identity -- the cache keys blocks by value, and an
    edit that produced the same objects would prove nothing.

    **This is the pessimistic end of the range for `demo/sample.md`**, and
    deliberately so rather than by accident: the last paragraph is the document's
    single most expensive block, 31.9ms of 97.7ms at 420pt. The per-block table
    above shows the spread. Editing a typical paragraph costs a few milliseconds.

    The *structural* claim -- that the edit lands on the heaviest block -- is what
    makes this the pessimistic end, and `tests/test_bench_numbers.py` re-derives
    it rather than leaving it asserted here. The two milliseconds are a loaded
    machine's best-of-N and move about 10% between runs; the 84.4ms this line
    carried before was not noise but the sample growing under it, which is the
    failure the test exists to catch.
    """
    cache = LayoutCache()
    compose(build_document(source, theme, fontlib_metrics), theme, width, measure, cache=cache)
    best = float("inf")
    for frame in range(repeat):
        edited = build_document(f"{source.rstrip()} word{frame}.\n", theme, fontlib_metrics)
        start = time.perf_counter()
        compose(edited, theme, width, measure, cache=cache)
        best = min(best, time.perf_counter() - start)
        # Re-fill from the unedited document, so the next repeat starts from the
        # same cache state rather than from the previous edit's.
        compose(build_document(source, theme, fontlib_metrics), theme, width, measure, cache=cache)
    return best * 1000.0, cache.stats()


if __name__ == "__main__":
    raise SystemExit(main())

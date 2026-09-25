r"""
Time a reflow, so every claim about layout performance in this project is measured.

A **reflow** is what happens between two frames when the window changes width:
`compose` breaks every paragraph to the new measure, `ship` flattens the packed
box into absolute draw commands, and `SelectionModel.from_commands` indexes
those commands for hit testing. Those three are the whole of it, and this script
times them separately because they have very different shapes -- one is a line
breaker and the other two are linear walks.

**Markdown parsing is not part of a reflow and is not in the table.** Building
the document from source costs roughly as much as several reflows, and it
happens exactly once, when the file is opened. Timing it into a reflow total
would inflate the denominator and flatter every later optimisation by making it
look like a smaller fraction of a bigger number. It is reported on its own line
above the table, as context, and never added in.

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

Deliberately out of scope: timing the ImGui backend, which needs a font atlas
and belongs in `scripts/verify_advances.py`'s idiom rather than here; and
per-function profiling, which `python -m cProfile` already does better.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advtext.markdown import Block, Document, TextBlock, build_document
from advtext.nodes import Box
from advtext.pack import CharMeasure
from advtext.selection import SelectionModel
from advtext.shipout import DrawCmd, Line, Point, ship
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import CacheStats, LayoutCache, compose, compose_blocks
from advtext.units import Scaled, sp_from_pt

__all__ = ["Timing", "main", "time_reflow"]

DEFAULT_WIDTHS = "300,420,800"
"""
Three measures: narrow enough to break badly, the litmus measure, and wide.

`scripts/render_litmus.py` sets its artifacts at 420pt, so the middle column is
directly comparable with everything in `docs/litmus.md`.
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
        "--source", type=Path, default=Path(__file__).resolve().parent.parent / "demo" / "sample.md"
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

    print(f"source:     {args.source}")
    print(f"blocks:     {len(document.blocks)}")
    print(f"repeat:     best of {args.repeat}")
    print(f"parse:      {parse_ms:.1f}ms  (once, on open -- NOT part of a reflow)")
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

r"""
Composition: the one piece of the UI package that does not touch ImGui.

**This was `advtext/ui/__init__.py` until 2026-10-10** and every name here is
still reached as `advtext.ui.<name>`: the package forwards to this module the
first time one is asked for (see its docstring for how, and for why
`Viewport` and `Hosted` are defined there and imported here). It moved so that
importing a module under `advtext.ui.` that sets its text some other way
(`advtext.ui.typeset_view`) no longer loads the line breaker. The module is
`composition` and not `compose` because `advtext.ui.compose` is the function.

`compose` turns a parsed markdown `Document` into a single packed vertical box:
it breaks every paragraph, hangs every list marker, sizes every table column and
stacks the lot with interline glue. That is the last step of the pipeline before
ship-out, and **it imports no ImGui**, which is why it lives here
rather than in `document_view.py`. `scripts/render_litmus.py` has
to do exactly the same work to produce an SVG with no display attached, and two
implementations of "lay out a document" would drift.

The ImGui-dependent modules are `advtext.ui.document_view` and
`advtext.ui.app`. Importing this module does not import either, so a headless
caller can `from advtext.ui import compose` safely.

**This is the only module that knows a document has a width.** Everything above
it produced material with no page in mind and everything below it consumes
absolute coordinates. That is the seam worth keeping: it is what makes
relayout-on-resize a single call rather than a traversal.

## What composition decides, and why it is not in `advtext.style`

Three things need a width and are therefore here rather than in the theme:

- **Ragged setting.** `BlockStyle.align` is data. A block that is not justified
  is set by handing `break_paragraph` a `\rightskip` of `0pt plus 1fil`, because
  only the breaker can add glue to the end of every line. Headings and code are
  ragged; body text, list items and quotes are justified. **A block that is not
  justified is also broken first-fit, at natural spacing**, where a justified
  one goes through the total-fit optimiser -- `_text_boxes` has the measured
  reasons, and `ComposeParams` is how to ask for the old behaviour.
- **The hanging marker.** A list item is broken to `width - left_indent` with
  `ParShape`'s indent, and the first line is then re-packed with the marker in a
  box exactly `left_indent` wide, right-aligned against a `marker_gap`. That
  keeps the item's text aligned whatever the marker's width, which a fixed
  marker offset does not once the list reaches item 10.
- **Table column widths, and wrapping inside a cell.** Every cell is packed at
  its natural size and the widest per column wins. A table that fits the
  measure is then spread to fill it; one that does not has its columns
  narrowed, never below their longest word, and a cell wider than its column
  is **broken as a paragraph** at the column's width. `_table_boxes` has the
  rules and `with_columns` is how a caller supplies widths of its own.
  `advtext.markdown` deliberately stops before all of this because it is
  `hpack` arithmetic and doing it there would make the converter measure.

**Every line of text is set on a strut**, which is the one thing this module
does that is not in the list above and is the reason a selection highlight has a
straight bottom edge. `advtext.style.Strut` carries the argument; what belongs
here is where it is *not* applied. A thematic break and a table's header rule
are lines in the vertical list and are not lines of text -- they have no
baseline of their own, and giving a one-pixel rule a full line's height and
depth would put a line's worth of air around it and move it off the rhythm the
block gap already set.

**A block quote is barred, and the bar is the one thing here that needs two
passes.** A rule down the left of a quote has to be exactly as tall as the
quote, and the quote's height is not known until its paragraphs have been broken
and packed. So a run of consecutive quoted blocks is stacked into a vbox of its
own and the rule is built from that vbox's dimensions -- `_barred`. Everything
else in this module is a single pass and this is why it could not be.

**Space between blocks is a kern, not interline glue.** Inside a block, §679's
`append_to_vlist` rule keeps a constant baseline-to-baseline rhythm. Between two
blocks the rhythm is deliberately broken -- that is what the space is *for* --
so the block gap is an explicit kern and the next block starts a fresh
`prev_depth`. Leaving both in would add a `\baselineskip`-derived gap on top of
the requested one and every heading would sit a line lower than asked.

**Viewport culling lives here too, and it is the same seam seen from the other
side.** `CommandIndex` and `Viewport` say which shipped draw commands are on
screen. They are here rather than in `advtext.ui.document_view` because deciding
what is visible is arithmetic over absolute coordinates and needs no frame, and
because `advtext.ui.document_view` cannot be executed in this environment while
everything in this file can. What is left there is reading a scroll offset out
of ImGui. Read `CommandIndex` before assuming culling could have been done
earlier in the pipeline: it could not, and the docstring says why.

**Composition is expensive and `LayoutCache` is only half a remedy.** Breaking
`demo/sample.md`'s 23 blocks takes ~85ms against a 16.7ms frame budget, and ~82%
of that is the line breaker re-packing trial lines. A cache of per-block line
boxes makes a re-render at an unchanged width nearly free and does **nothing**
for a resize drag, because a paragraph's breaking is a function of the width it
was broken to. That type's docstring has the measurements; the remaining cost is
`advtext.linebreak`'s to pay, not this module's.

Deliberately out of scope: colour and link decoration (the node model carries
neither; `TextBlock.links` is what a backend draws them from), nested tables,
and any notion of a page. `docs/decisions.md` puts page breaking out of scope,
so a document is one continuous vertical list however long it gets.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields, replace
from typing import TypeAlias

from advtext.linebreak import LineBreakParams, LineSpec, ParShape, break_paragraph
from advtext.markdown import (
    Block,
    CodeBlock,
    ColumnAlign,
    Document,
    RuleBlock,
    TableBlock,
    TableCell,
    TextBlock,
)
from advtext.nodes import Box, Glue, GlueSpec, Kern, Node, Rule
from advtext.pack import (
    IGNORE_DEPTH,
    CharMeasure,
    PackMode,
    append_to_vlist,
    hpack,
    vpack,
)
from advtext.selection import Rect
from advtext.shipout import DrawCmd, Line, RuleRect
from advtext.style import Align, Theme
from advtext.ui import Hosted, Viewport
from advtext.units import UNITY, GlueOrder, Scaled

__all__ = [
    "HSS",
    "PROSE_BREAKING",
    "PROSE_BREAKING_BOUNDED",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED",
    "RAGGED_RIGHT",
    "CacheStats",
    "ColumnLimits",
    "CommandIndex",
    "ComposeParams",
    "ComposedRun",
    "HostBlock",
    "Hosted",
    "LayoutCache",
    "RunComposer",
    "SizedTable",
    "TableMeasure",
    "Viewport",
    "block_runs",
    "compose",
    "compose_blocks",
    "prev_depth_after",
    "run_gap",
    "table_column_limits",
    "table_columns",
    "table_natural_widths",
    "visible_rects",
    "with_columns",
]

HSS = GlueSpec(
    width=0,
    stretch=UNITY,
    stretch_order=GlueOrder.FIL,
    shrink=UNITY,
    shrink_order=GlueOrder.FIL,
)
r"""
`\hss`: no natural width, infinitely stretchable and shrinkable.

One of these pushes material to one side of a box and a pair of them centres it,
at any width, without an alignment flag anywhere. `advtext.blocklayout` makes the
same point at length.
"""

RAGGED_RIGHT = GlueSpec(stretch=UNITY, stretch_order=GlueOrder.FIL)
r"""
The `\rightskip` that turns justified setting into ragged-right setting.

Infinite stretch at the end of every line means the line breaker stops charging
badness for a short line, so it breaks where the words fall rather than
stretching the spaces to reach the margin.
"""

PROSE_BREAKING = LineBreakParams(tolerance=1000, emergency_stretch=20 * UNITY)
r"""
Breaking parameters for prose **in a project with no hyphenator**.

`advtext.linebreak.LineBreakParams` defaults to `plain.tex`'s numbers, and that
is right for a module whose job is to transcribe TeX. It is wrong here, and the
difference is measured rather than assumed: at `\tolerance=200`, composing
`demo/sample.md` at a 420pt measure produces **seven overfull lines, the worst by
181pt** -- text sitting in and past the margin. (This said *five* until T6
rewrote the document beneath it; the 181pt still reproduces exactly.) For several
paragraphs of ordinary English prose *no* breaking exists in which every line's
badness stays under 200, because without hyphenation nothing can cut inside a
word, and §854's last-resort escape then forces a break wherever the scan is
standing.

`\tolerance=1000` with 20pt of `\emergencystretch` removes **every** overfull
line from that document, which is what a plain TeX user does when hyphenation is
off. `docs/litmus.md` has both columns.

## What this value costs, which was not known when it was chosen

**`\emergencystretch` is scored but not packed, so `tolerance` bounds nothing.**
§828 (`tex.web` line 16335) describes the third pass -- *"we add
`emergency_stretch` to the background stretchability"* -- and §863 performs it,
`background[2] := background[2] + emergency_stretch` at `tex.web` line 17018.
The breaker therefore *scores* candidate lines against stretchability that does
not exist, and `advtext.linebreak._assemble` packs the winner **without** it,
deliberately and correctly (its docstring says why). A line admitted as "badness
under 1000" can then be set at any `glue_set` at all.

Measured over `demo/columns.md` and `demo/sample.md` at 26 measures from 260px
to 760px, this setting produces lines whose badness -- computed back from the
`glue_set` the packer actually set -- reaches **`INF_BAD`, 10000: ten times the
1000 declared here**, at a worst `glue_set` of 11.26. The interword space on
that line is 6.6 times its natural width. Those are the lines a reader points at.

`tests/test_compose.py::test_prose_breaking_does_not_bound_how_loose_a_line_can_be`
asserts that, as a recorded fact rather than as a desired property.

## The alternative, and exactly what it costs

`LineBreakParams(tolerance=6000)` -- same looseness admitted, no emergency
stretch. The bound then holds exactly, because the line the breaker scored is
the line the packer emits: worst badness over the same sweep is **5893** and
worst `glue_set` **3.90**. 6000 is the smallest tolerance that adds no overfull
line at either measure this project sets by rule (`scripts/render_litmus.py`'s
420pt and `document_view.page_for`'s 2.25 alphabets); at 5900, `demo/sample.md`
gains one at 420pt.

**It is not shipped because it is not free.** Over the same sweep it turns 24
overfull lines into 105, and one of the new ones is in `demo/columns.md` at the
399.5px measure the three-column tab currently sets --
`tests/test_demo_content.py` asserts that document ships no glyph past a column
edge, and it would stop being true. The band is narrow: columns.md gains an
overfull line at 400, 405, 410, 435 and 440px and none at 390, 395, 415-430 or
445-480, so a three-column measure at the project's own 2.00-alphabet floor
would likely make the swap free. `tests/test_compose.py` pins both the bound the
alternative restores and the overfull line it costs, so the change is one line
and the evidence for it cannot rot.

Raising the tolerance further does not escape the trade: at `tolerance=8189`,
the largest value `advtext.badness.badness` can return below `INF_BAD`, the
sweep still gains 56 overfull lines. `line_penalty` and `adj_demerits` move
nothing measurable at 0, 100 and 100000.

## What would actually fix it

Not a parameter. Measured, not guessed: a discretionary at every position legal
under `\lefthyphenmin=2`/`\righthyphenmin=3` -- an upper bound, since real Liang
patterns find fewer -- takes `demo/columns.md` at the 468.75px measure from a
worst `glue_set` of 3.04 to **1.10** with plain TeX's own `\tolerance=200` and no
emergency stretch, and no overfull line. Hyphenation does not improve this
trade, it dissolves it. `docs/decisions.md` scopes it out at ~1000 lines for
§915-§916's ligature reconstruction and that cost is real.

The cheap fraction is honouring the hyphens an author already typed, which needs
no patterns at all and which `advtext.nodes.Disc` already describes: a `Disc`
after every hyphen between two letters takes the sweep from 24 overfull lines to
**2**, adding none anywhere. Nothing generates those today.

It lives here rather than in `advtext.linebreak` because "this project has no
hyphenator" is a fact about the document layer, not about the algorithm. Pass
`params=` to override it; `LineBreakParams()` gets plain TeX's behaviour back.
"""


@dataclass(frozen=True, slots=True)
class ComposeParams(LineBreakParams):
    r"""
    `LineBreakParams`, plus the one breaking choice that is composition's and not TeX's.

    Composition breaks a block that is **not justified** with the first-fit
    breaker and at natural spacing (`_text_boxes` says why, with figures). That
    is a decision about which algorithm a block gets, made per block from its
    alignment, so it cannot be a field of the parameters one algorithm reads --
    and it must be in the cache key, which the `params` object already is.
    Hence a subclass, passed wherever `params` is.

    `ragged_total_fit=True` puts non-justified blocks back through the
    total-fit optimiser with their glue as emitted, which is exactly what
    every block got before first-fit existed. It is here so the old result
    stays reachable -- for a comparison, or for a short ragged block where the
    optimiser's choice is wanted and its cost does not matter. Expect that
    cost: 78 to 339 times the justified one on a 635-node paragraph, and one
    word per line ahead of a word wider than the measure
    (`tests/test_stream_stability.py` pins the latter).

    It does not touch justified blocks, which are total-fit either way, nor
    table cells, which are always first-fit.
    """

    ragged_total_fit: bool = False


PROSE_BREAKING_TOTAL_FIT_RAGGED = ComposeParams(
    tolerance=PROSE_BREAKING.tolerance,
    emergency_stretch=PROSE_BREAKING.emergency_stretch,
    ragged_total_fit=True,
)
r"""
`PROSE_BREAKING`, with non-justified blocks sent through the total-fit breaker as before.

The parameters composition used for *every* block until 2026-10-06. See
`ComposeParams`.
"""

PROSE_BREAKING_BOUNDED = LineBreakParams(tolerance=6000)
r"""
`PROSE_BREAKING` with the `\emergencystretch` taken out, for a caller who wants the bound.

Everything about the choice is in `PROSE_BREAKING`'s docstring, including why
this is not the default. In one line: this one honours its own `tolerance` --
every line that is neither overfull nor a paragraph's last has
`badness <= 6000`, measured worst 5893 -- and it buys that by putting a handful
of lines into the margin at measures below the project's two-alphabet floor.

Exported rather than left as a literal in the tests so that the two settings sit
next to each other and a reader comparing them does not have to trust a number
copied into a test file.
"""


@dataclass(frozen=True, slots=True)
class _Context:
    """
    The part of a block's cache key that is the same for every block in one pass.

    Built once at the top of `compose_blocks` rather than per block. `theme` is
    `_theme_key`'s tuple and not a `Theme`, because a `Theme` cannot be hashed.
    """

    params: LineBreakParams
    measure: CharMeasure
    theme: tuple[object, ...]


_PassKey: TypeAlias = tuple[Scaled, _Context]
"""
What identifies one composition pass: the measure, and the context every block shares.

Everything a `_BlockKey` carries except the block itself. Two passes with equal
pass keys can share cache entries; two with different ones provably cannot,
because the width or the context differs inside every key either would look up.
That is what makes the pass key the right unit to hold a generation against --
see `LayoutCache`, "Residency is per pass key".
"""


_BlockKey: TypeAlias = tuple[Block, Scaled, _Context]
"""
What one block's line boxes depend on, in full: the block, the width, the context.

`_block_boxes` is a pure function of exactly the block, the theme, the width, the
measure and the params, so a key carrying all five cannot go stale -- and a key
that drops one silently returns another document's layout. `tests/test_compose.py`
has a test that fails for each of the five if it is dropped.
"""


@dataclass(frozen=True, slots=True)
class CacheStats:
    """
    What a `LayoutCache` did, for a benchmark or a debug overlay to print.

    `hits` and `misses` are lifetime totals; `entries` is what is resident now,
    which is bounded by `LayoutCache.resident_passes` generations and so says
    nothing about how long the cache has been alive.

    `entries` counts distinct cached results, not dict slots: one generation
    holds one entry per block it composed, and a block cached at two measures is
    two entries because it is two layouts.
    """

    hits: int
    misses: int
    entries: int


@dataclass(slots=True)
class _Generation:
    """
    One pass key's cache entries, and which of them the pass now running has used.

    `used` is how the retention rule is enforced without keeping two copies of
    everything: `begin` throws away exactly the entries that the *previous* pass
    at this key did not touch. An entry therefore survives for as long as every
    pass at its own pass key uses it, and the pass that skips it is the pass that
    drops it.

    The invariant that makes that sound is `used <= entries.keys()` at all times:
    `LayoutCache.boxes` only ever adds a key to `used` in the same breath as
    putting it in `entries`, and `begin` narrows `entries` to `used` before
    emptying `used`. So an edit that changes one paragraph leaves the old
    paragraph's entry resident for exactly one further pass and then gone.
    """

    entries: dict[_BlockKey, tuple[Box, ...]] = field(default_factory=dict)
    used: set[_BlockKey] = field(default_factory=set)

    def begin(self) -> None:
        """
        Retire what the last pass at this key did not use, and start counting again.

        The length test is not a micro-optimisation dressed up as a guard. The
        rebuild costs two more hashes of a `_BlockKey` per block -- one to read
        the old dict and one to write the new -- and hashing a `_BlockKey` walks
        the whole of a `TextBlock`'s material tuple: one sweep of
        `demo/sample.md`'s 37 keys measures **1.08ms**, which is most of a warm
        pass on its own. Skipping the rebuild on the pass that retires nothing --
        which is every pass over a document that has not changed, the warm case
        this cache exists for -- measures **1.0ms of a 3.8ms warm pass**.

        It is exact rather than approximate because `used` is a subset of
        `entries.keys()` by construction, so equal sizes mean equal sets.
        """
        if len(self.used) != len(self.entries):
            self.entries = {key: self.entries[key] for key in self.used}
        self.used = set()


@dataclass(slots=True)
class LayoutCache:
    """
    Per-block line boxes, kept between two calls to `compose`.

    **Two vintages of measurement are quoted below and they do not agree.** The
    figures in "Residency is per pass key" and in `_Generation.begin` were taken
    against `demo/sample.md` at **37 blocks**. Everything else here -- 84.4ms,
    1.8ms, 90.9ms, 8.3ms, the 0.11ms-of-84.3ms by-kind table, 34.7ms, 0.48ms --
    predates that document and was taken when it had **23**. Those older figures
    are stale in magnitude; what they are cited *for* -- that a warm pass is two
    orders cheaper than a cold one, that cost is superlinear in paragraph length,
    that the by-kind spread does not justify a per-kind key -- is unaffected, and
    re-deriving them is `T12-final-gate`'s, not this change's.

    **Be clear about what this does and does not buy, because the obvious
    expectation is the wrong one.** A block's cache key contains the width it was
    broken to, so *every text block misses on every width change*. A live resize
    drag gets **nothing** from this cache, and that is not a shortcoming to be
    engineered around: a paragraph broken to 300pt tells you nothing whatsoever
    about the same paragraph at 301pt, and a cache that answered otherwise would
    be returning a wrong layout. `scripts/bench_reflow.py` measures the drag over
    consecutive one-point widths and reports **zero hits**, which is the result
    and not a bug in the benchmark.

    What it buys is the **re-render at an unchanged width**: on `demo/sample.md`
    at 420pt, composition goes from 84.4ms to 1.8ms and the whole reflow
    including ship-out and the selection index from 90.9ms to 8.3ms.

    **That headline is measured against no cache at all, and the tree already
    has a coarser one.** `advtext.ui.document_view.DocumentView.layout_for`
    keeps the whole `Layout` -- box, commands and selection index -- for the last
    width it composed, and returns it untouched when the width has not changed.
    For a scroll or a selection change in the real widget that costs nothing at
    all, which beats 1.8ms. So the case this type uniquely serves is the one that
    cache cannot express: **a document whose blocks have only partly changed.**
    `DocumentView.invalidate` throws the whole layout away, and a re-compose then
    re-breaks 23 blocks to recover from an edit to one. Through this cache it
    re-breaks the one. `scripts/bench_reflow.py`'s last table measures it at
    **34.7ms against 84.4ms** at 420pt -- and that is the *worst* case rather
    than a typical one, because the block it edits is the sample's single most
    expensive paragraph at 31.9ms on its own. Editing a typical paragraph costs
    a few milliseconds. The by-block table has the spread, and it is the number
    to read before optimising anything here: composition cost per paragraph is
    strongly superlinear in its length, so 635 nodes cost 31.9ms where 427 cost
    11.4ms, and the document's total is dominated by its longest few blocks.

    **Since `advtext.ui.units` (2026-10-06) `DocumentView` no longer works that
    way**, and the paragraph above describes what this cache was built against
    rather than what calls it now. Nothing keeps one whole `Layout` any more and
    `DocumentView` has no `layout_for` of its own: the method is
    `advtext.ui.bare_view.BareView.layout_for` (and `StreamView.layout_for`),
    and what calls this cache is `advtext.ui.units.layout_units` beneath them.
    `layout_for` keeps the *shipped* form of each
    run of blocks in a `UnitCache` that sits in front of this one, so a run that
    has not changed is not looked up here at all and this cache records neither
    a hit nor a miss for it. This cache is then the second line: it answers when
    a unit has to be rebuilt but a block inside it need not be re-broken.

    The second beneficiary is any caller that is not a `DocumentView` at all --
    `scripts/render_litmus.py`, a second view of the same document, a test.

    ## The width is in the key for every block, including the ones that ignore it

    A fenced code block is not line-broken, so its layout really is independent
    of the measure and could be keyed without the width and hit during a drag.
    Measured, that is worth **0.11ms of 84.3ms** on `demo/sample.md` -- 20 text
    blocks cost 83.6ms, the table 0.57ms, the code block 0.11ms and the rule
    0.006ms. It is not taken. A per-kind exemption from the key would be a place
    for a future width dependence to hide, and 0.13% does not buy that risk.
    Note that a `RuleBlock` is **not** in this category despite looking like it:
    `_rule_box` draws the rule to the full measure.

    ## Residency is per pass key, and that is the fix for two consumers

    Entries are grouped by `_PassKey` -- the measure plus the context -- and each
    group retains for itself: **an entry survives for as long as every pass *at
    its own pass key* uses it, and one such pass that does not use it drops it.**
    `_Generation` implements that in one method.

    The five words "at its own pass key" are the whole of a fix, and this is what
    they repair. The scheme before them held one `current` generation and one
    `previous`, rotated on every `compose_blocks` regardless of what was being
    composed. Two consumers at two measures sharing one cache -- a Document tab
    at the page width and a Columns tab at a column width, or one routine
    composing at the 2-column then the 3-column measure -- therefore evicted each
    other outright: each pass's rotation discarded the generation the *other*
    consumer was about to read.

    Measured, alternating 420pt and 205pt over eight passes on `demo/sample.md`
    as it stood at 37 blocks, with one `char_measure` hoisted across the run:
    **0 hits and 296 misses**, every pass a full reflow, 161ms at 420pt and 300ms
    at 205pt against a 16.7ms frame budget. Grouped by pass key the same eight
    passes are **222 hits and 74 misses** -- the two filling passes miss and the
    six after them are pure cache -- at 2.8ms and 3.2ms.
    `tests/test_compose.py::test_two_consumers_at_two_measures_do_not_evict_each_other`
    pins the counts and
    `::test_two_consumers_at_two_measures_still_get_each_others_layout_right`
    pins that the layouts they get are each other's and not each other's.

    The single-consumer warm pass got **faster**, 3.8ms to 2.7ms, which is a
    consequence rather than an aim: the old scheme hashed a `_BlockKey` three
    times per warm lookup -- miss in `current`, hit in `previous`, promote into
    `current` -- and this one hashes twice. Residency for a single consumer also
    halves, from two copies of the key set to one.

    Nothing about the single-consumer *behaviour* changes, and two of those
    behaviours are pinned on purpose. A resize drag still gets **zero** hits,
    because a paragraph broken to 300pt says nothing about the same paragraph at
    301pt and every consecutive width is a new pass key. And residency is still
    **two documents' worth** whatever the drag does, because the number of
    resident pass keys is bounded.

    ## `resident_passes`, which is the capacity that was always there

    The old scheme had no number to tune, but it did have a capacity: exactly one
    distinct pass key could be resident, and a second one evicted the first. The
    number is now written down. Two is the default because two is what the bound
    already was in the workload it was chosen for -- a drag retains the last two
    widths and no more, which is what
    `tests/test_compose.py::test_a_cache_keeps_two_generations_and_no_more`
    measured before this change and still measures unaltered after it.

    Two is also exactly enough for the case above: one document tab and one
    columns tab, or two column counts. **A caller that cycles three measures
    wants `LayoutCache(resident_passes=3)`** -- a columns view with a 1/2/3
    control is the obvious one, and at two it will miss every time the count
    returns to the least recently used of the three. Eviction is by least recent
    use and not by age, so the measures a caller keeps coming back to are the
    ones that stay.

    The bound is what stops a leak under exactly the workload the cache cannot
    accelerate: keyed on the width, an unbounded cache dragged across 500 pixels
    retains 500 broken copies of every paragraph in the document.

    ## The measure is keyed by identity

    `CharMeasure` is a closure over a font resolver and has no meaningful
    equality, so two distinct measure objects are two keys even if they would
    return the same numbers. That direction of error is a wasted reflow and the
    other direction is a wrong document, so identity is the conservative choice.
    A caller that rebuilds its measure every frame gets no hits and should hoist
    it; `advtext.style.char_measure` memoises per glyph and is meant to be held.

    **The block, by contrast, is keyed by value**, and that costs 0.48ms of the
    1.8ms a warm pass takes -- hashing a `TextBlock` walks its whole material
    tuple. Keying blocks by `id` would recover most of it and is deliberately not
    done: the remaining 1.3ms is the stacking that no per-block cache can remove,
    the total is already inside the frame budget, and value equality is the
    property that makes "this cache cannot go stale" a thing one can read off the
    key rather than an argument about object lifetimes.
    """

    resident_passes: int = 2
    generations: dict[_PassKey, _Generation] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        """
        Refuse a capacity below one, which would be a cache that cannot hit.

        Zero is not "no cache". It is a cache that does all the work of one and
        answers nothing, and the only symptom is a frame rate.
        """
        if self.resident_passes < 1:
            raise ValueError(f"resident_passes must be at least 1, got {self.resident_passes}")

    def stats(self) -> CacheStats:
        """
        Lifetime hits and misses, and how many entries are resident.
        """
        return CacheStats(
            hits=self.hits,
            misses=self.misses,
            entries=sum(len(generation.entries) for generation in self.generations.values()),
        )

    def clear(self) -> None:
        """
        Drop everything, including the counters.

        Nothing in composition needs this -- the key is complete, so a changed
        theme or a changed font simply misses. It exists for a caller that has
        replaced the whole document and wants the memory back now.
        """
        self.generations = {}
        self.hits = 0
        self.misses = 0

    def begin_pass(self, key: _PassKey) -> _Generation:
        """
        Open a pass at `key` and hand back the generation it caches into.

        Called once per `compose_blocks`. Retiring what the last pass *at this
        key* did not use is what bounds one generation; evicting the least
        recently used pass key is what bounds their number. Re-inserting the
        generation is what makes `generations` an LRU ordering rather than an
        insertion one -- a `dict` preserves insertion order, so a `pop` and a
        re-add move an entry to the most-recent end, and the `del` therefore
        takes the least recently *used* pass key rather than the oldest one.

        Returned rather than stashed on `self`, so a `_Memo` names the generation
        it writes into and there is no "which pass am I in" state on the cache to
        get out of step with the recursion.
        """
        generation = self.generations.pop(key, None)
        if generation is None:
            generation = _Generation()
        generation.begin()
        self.generations[key] = generation
        while len(self.generations) > self.resident_passes:
            del self.generations[next(iter(self.generations))]
        return generation

    def boxes(
        self,
        generation: _Generation,
        key: _BlockKey,
        build: Callable[[], tuple[Box, ...]],
    ) -> tuple[Box, ...]:
        """
        `build()`'s result for `key`, computed at most once per pass at its key.

        `generation` comes from `begin_pass`; the counters live here rather than
        there because they are the cache's lifetime totals and not one pass's.

        `key` still carries the width and the context even though `generation`
        already implies both. The redundancy is deliberate: "this cache cannot
        return another width's layout" stays readable off the key alone, instead
        of becoming a property of the bucketing being correct.
        """
        found = generation.entries.get(key)
        if found is not None:
            self.hits += 1
            generation.used.add(key)
            return found
        self.misses += 1
        built = build()
        generation.entries[key] = built
        generation.used.add(key)
        return built


def _theme_key(theme: Theme) -> tuple[object, ...]:
    """
    A hashable stand-in for a `Theme`, which is not itself hashable.

    `Theme.blocks` is a `dict`, so the frozen dataclass has a `__hash__` that
    raises -- check that before assuming a frozen dataclass can be a dict key.
    The dict becomes a `frozenset` of its items, which is hashable, caches its
    hash, and needs no ordering over `BlockKind`.

    **Derived from `dataclasses.fields` rather than listed**, so that a field
    added to `Theme` joins the key without anyone remembering to come here. A
    forgotten field would be a cache that returns a layout from the old theme,
    which is the failure mode this whole type exists to make impossible.
    `tests/test_compose.py::test_the_theme_cache_key_covers_every_field_of_theme`
    pins the count.
    """
    return tuple(_hashable(getattr(theme, spec.name)) for spec in fields(theme))


def _hashable(value: object) -> object:
    """
    `value`, or a hashable equivalent of it if it is a mapping.
    """
    if isinstance(value, dict):
        return frozenset(value.items())
    return value


@dataclass(frozen=True, slots=True)
class _Memo:
    """
    A cache plus the part of the key that is constant for a whole composition.

    The theme and the params are the same for every block in one pass, so the
    context tuple is built once at the top rather than per block. It travels with
    the cache because the two are only ever used together.

    `generation` is the one `LayoutCache.begin_pass` opened for this pass, carried
    here rather than left as "the active one" on the cache -- a cache with a
    current-pass field can fall out of step with the memo being passed down the
    recursion, and one without cannot.
    """

    cache: LayoutCache
    generation: _Generation
    context: _Context


@dataclass(frozen=True, slots=True)
class CommandIndex:
    """
    A shipped command list with the vertical extent of every command beside it.

    **This is the whole of viewport culling, and it is bookkeeping rather than
    algorithm** -- but only because it culls *drawing* and not *breaking*. Asking
    which blocks are visible before laying them out is circular, since a block's
    height is not known until it has been broken and the blocks above it decide
    where it starts. By the time a command list exists every one of those
    questions is already answered and each command carries an absolute
    coordinate, so selecting the visible ones is a comparison per command.

    ## Why this is the cost worth cutting

    Measured on `demo/sample.md` at 420pt in a real headless ImGui frame:
    `advtext.backends.imgui_draw.draw` takes **21ms** for the document's 4,226
    commands, against a 16.7ms frame budget -- so the widget misses 60fps while
    doing nothing at all, because `DocumentView` caches the layout and then
    redraws every glyph in the document on every frame regardless. Culling to a
    768px viewport leaves 1,952 commands and **8-10ms**, depending on where the
    scroll is. Building this index costs 0.33ms once per layout and a cull costs
    0.16ms per frame.

    **And the culled cost does not grow with the document**, which is the whole
    return. Concatenated copies of the same sample, one 768px window, same frame:

    | document | commands | unculled | culled |
    |---|---|---|---|
    | 1,842px | 4,226 | 20.7ms | 9.4ms |
    | 3,725px | 8,452 | 41.3ms | 9.4ms |
    | 7,490px | 16,904 | 82.1ms | 9.3ms |

    A frame becomes a function of the window rather than of the file.

    **Re-run that table with `python scripts/bench_draw.py --copies 1,2,4`.** It
    reproduces these figures to within noise and it also answers the question
    they raise: 20 of the 21ms is our own per-glyph Python, not ImGui's drawing
    work, which is about 1ms. So culling is the right lever and batching runs of
    glyphs into one `add_text` is not -- see that script's docstring for the
    decomposition.

    Ship-out and the selection index are the other candidates and they are not
    worth culling: together they are 6.5ms, they run only when the width changes,
    and the composition on that same frame is 84ms. Culling them would be 7% of a
    frame that is already five times over budget.

    **Who calls this now (2026-10-07).** The section above is the argument the
    type was built on, and two things in it have moved since. No view keeps
    one `CommandIndex` over a whole document: `advtext.ui.units` builds one
    per unit when the unit is shipped, and `UnitLayout.visible(viewport)` is
    the cull a view calls, asserted in `tests/test_units_layout.py` to return
    exactly `CommandIndex.of(layout.cmds).visible(viewport)`. So "ship-out and
    the selection index ... run only when the width changes" describes the
    whole-document path; under units they run per unit that changed. And the
    milliseconds are of the backend before its per-glyph memo:
    `scripts/bench_draw.py` prints current ones (one run on 2026-10-07, quiet
    machine: 13.7 ms full, 5.1 ms culled, the culled figure the same at one,
    two and four copies).

    ## A command's extent is its line's, and that is exact rather than generous

    A `Line` is emitted before the material it covers and spans
    `[y - height, y + depth)`. A `Glyph` carries a baseline and no ink bounds, so
    it takes the extent of the innermost `Line` it sits in -- which is not an
    approximation: `hpack` computes a line's height and depth as the maximum over
    its contents' ink, and `advtext.style.Strut` only ever raises them, so a
    glyph's ink is inside its line's extent by construction. A `RuleRect` uses its
    own `[y, y + height)`, which matters for the bar down a block quote: the bar
    is one rule spanning every line of the quote and its own extent is the tight
    one.

    ## Selection is untouched, deliberately

    Culling happens **after** ship-out and after `SelectionModel.from_commands`,
    on a copy of the list. The model still indexes the whole document, reading
    order is still dense over it, and `text()` over a selection running off the
    bottom of the window still serialises the off-screen half. Nothing about
    `advtext.selection` had to change and nothing about it may: a selection that
    copied only what was on screen is precisely the failure this project exists
    to beat.
    """

    cmds: tuple[DrawCmd, ...]
    tops: tuple[Scaled, ...]
    bottoms: tuple[Scaled, ...]

    @classmethod
    def of(cls, cmds: Sequence[DrawCmd]) -> CommandIndex:
        """
        Index a shipped command list, in one forward pass.

        The pass is forward and stateful for the same reason `SelectionModel`'s
        is: a `Line` precedes the commands it covers, so one sweep always knows
        which line it is inside.
        """
        tops: list[Scaled] = []
        bottoms: list[Scaled] = []
        line_top: Scaled = 0
        line_bottom: Scaled = 0
        for cmd in cmds:
            match cmd:
                case Line():
                    line_top, line_bottom = cmd.y - cmd.height, cmd.y + cmd.depth
                    tops.append(line_top)
                    bottoms.append(line_bottom)
                case RuleRect():
                    tops.append(cmd.y)
                    bottoms.append(cmd.y + cmd.height)
                case _:
                    tops.append(line_top)
                    bottoms.append(line_bottom)
        return cls(cmds=tuple(cmds), tops=tuple(tops), bottoms=tuple(bottoms))

    def visible(self, viewport: Viewport) -> tuple[DrawCmd, ...]:
        """
        The commands whose extent meets `viewport`, in reading order.

        Order is preserved and **a kept `Glyph` always keeps the `Line` that
        introduced it**, which is not a special case here but a consequence of
        the extents: a glyph is given its line's extent exactly, so the two are
        visible or culled together, and the header precedes the glyph in the
        original list. The result is therefore a legal command list in its own
        right and a backend cannot tell it from a short document.
        `tests/test_document_view.py` asserts that rather than leaving it as an
        argument, because the debug overlay's line boxes would go missing from
        under their own glyphs if it stopped being true.
        """
        top, bottom = viewport.top, viewport.bottom
        return tuple(
            cmd
            for cmd, cmd_top, cmd_bottom in zip(self.cmds, self.tops, self.bottoms, strict=True)
            if cmd_bottom > top and cmd_top < bottom
        )


def visible_rects(rects: Sequence[Rect], viewport: Viewport) -> tuple[Rect, ...]:
    """
    The highlight rects that meet `viewport`.

    A `Rect` is top-anchored and carries its own height, so this needs no index.
    Separate from `CommandIndex.visible` because highlights are rebuilt whenever
    the selection changes and the command list is not.
    """
    return tuple(rect for rect in rects if viewport.covers(rect.y, rect.y + rect.height))


def compose(
    document: Document,
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams | None = None,
    *,
    cache: LayoutCache | None = None,
) -> Box:
    """
    Lay a whole document out to a width, returning one packed vertical box.

    `width` is the measure, in scaled points. The result's reference point is on
    the baseline of its first line, which is what `advtext.shipout.ship` expects;
    pass `Point(0, box.height)` as the origin to put its top-left at zero.

    `params` defaults to `PROSE_BREAKING`, which is **not** `LineBreakParams()`
    -- see that constant for the measurement behind the difference. A caller
    that wants plain TeX's tolerance passes `LineBreakParams()` explicitly and
    should expect overfull lines on unhyphenated English.

    Expensive: this runs the line breaker over every paragraph, which is ~85ms
    on `demo/sample.md` against a 16.7ms frame budget. Pass a `LayoutCache` and
    hold it across frames, and a re-render at an **unchanged** width becomes a
    lookup per block. A re-render at a *changed* width still costs the full
    reflow and no cache can alter that; `LayoutCache` says why at length.
    """
    return compose_blocks(document.blocks, theme, width, measure, params, cache=cache)


def compose_blocks(
    blocks: tuple[Block, ...],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams | None = None,
    *,
    cache: LayoutCache | None = None,
) -> Box:
    """
    `compose`, over a bare sequence of blocks, for a caller rendering a fragment.
    """
    params = PROSE_BREAKING if params is None else params
    memo: _Memo | None = None
    if cache is not None:
        context = _Context(params, measure, _theme_key(theme))
        memo = _Memo(cache, cache.begin_pass((width, context)), context)
    return vpack(_stacked(blocks, theme, width, measure, params, depth=0, memo=memo)).box


def block_runs(blocks: tuple[Block, ...]) -> list[tuple[Block, ...]]:
    """
    A document's blocks as the units that can be laid out independently of each other.

    **The unit is a run, not a block, and the difference is the block quote.**
    Consecutive quoted blocks are stacked into one box so that a single bar can
    run down the left of all of them (`_barred`), and that bar's height is a
    property of the whole run. Everything else is a run of one. So this is the
    finest partition for which "lay this out without looking at its neighbours"
    is true, and it is the one `compose_blocks` itself stacks -- `_runs` at
    depth zero, exposed rather than re-derived, so the two cannot disagree.

    What sits *between* two runs is `run_gap` and belongs to neither.
    """
    return _runs(blocks, 0)


def run_gap(above: tuple[Block, ...], below: tuple[Block, ...]) -> Scaled:
    """
    The vertical space `compose_blocks` puts between two adjacent runs.

    The lower block's `space_above` added to the upper one's `space_below`,
    which is the kern `_stacked` inserts. No interline glue joins it: a run
    starts a fresh `prev_depth`, which is the property that makes stacking
    separately composed runs by offset **exact in scaled points** rather than
    approximately right. `tests/test_units_layout.py` asserts the equality
    against `compose` on the demo document instead of leaving it as this
    argument.
    """
    return above[-1].style.space_below + below[0].style.space_above


@dataclass(frozen=True, slots=True)
class ComposedRun:
    """
    One run of blocks, composed on its own: its box, and where each block sits in it.

    `box` is a vbox holding exactly the line boxes `compose_blocks` would have
    put in the document's vertical list for these blocks, with the same
    interline glue between them. Its reference point is on its last line's
    baseline, as any vbox's is; `box.height + box.depth` is its full extent.

    `extents` has one `(top, bottom)` per block of the run, measured down from
    the top of `box`. For a run of one that is the whole box. For a quoted run
    it is what lets a point be resolved to *one paragraph of the quote* rather
    than to the quote, which is what a block-level hit test has to answer.
    The space between two blocks of a run belongs to neither.
    """

    blocks: tuple[Block, ...]
    box: Box
    extents: tuple[tuple[Scaled, Scaled], ...]


@dataclass(slots=True)
class RunComposer:
    """
    One composition pass, taken a run at a time instead of a document at a time.

    `compose_blocks` breaks every block and returns one box. A caller that keeps
    the *shipped* form of each run -- `advtext.ui.units` -- must be able to ask
    for one run without paying for the others, and must be able to do it
    through the same `LayoutCache` and the same `_stacked` that the whole-document
    path uses, or the two would be two implementations of "lay out a block".
    This is that entry point and it adds no layout code of its own.

    `key` is the `LayoutCache` pass key for this pass: the measure plus the
    params, the `CharMeasure` (by identity) and the theme. A cache of anything
    derived from a composed run is keyed by exactly this and the run, for the
    reason `_BlockKey` gives.

    **The `LayoutCache` pass is opened lazily, on the first run of several
    blocks actually composed.** A pass in which every run was answered from a
    later cache never touches the `LayoutCache` at all, and so does not retire
    anything from it; and a run of one block is composed without it (`compose`
    says why).
    """

    theme: Theme
    width: Scaled
    measure: CharMeasure
    params: LineBreakParams | None = None
    cache: LayoutCache | None = None
    _context: _Context | None = field(default=None, init=False)
    _memo: _Memo | None = field(default=None, init=False)

    @property
    def context(self) -> _Context:
        """
        What every block of this pass shares, built once.
        """
        if self._context is None:
            params = PROSE_BREAKING if self.params is None else self.params
            self._context = _Context(params, self.measure, _theme_key(self.theme))
        return self._context

    @property
    def key(self) -> _PassKey:
        """
        What identifies this pass: the measure and the shared context.
        """
        return (self.width, self.context)

    def compose(self, run: tuple[Block, ...]) -> ComposedRun:
        """
        Compose one run from `block_runs`, through the cache if there is one.
        """
        context = self.context
        # Only a run of several blocks goes through the `LayoutCache`. A run
        # of one is asked for here because its unit missed, which means the
        # block changed, which means its line boxes are not in the cache
        # either -- and finding that out hashes the block twice, which for a
        # long code block costs more than composing it. A quote is different:
        # one paragraph of it changing rebuilds the unit, and the others'
        # boxes are worth finding.
        memo: _Memo | None = None
        if self.cache is not None and len(run) > 1:
            if self._memo is None:
                self._memo = _Memo(self.cache, self.cache.begin_pass(self.key), context)
            memo = self._memo
        extents: list[tuple[Scaled, Scaled]] = []
        vlist = _stacked(
            run,
            self.theme,
            self.width,
            self.measure,
            context.params,
            depth=0,
            memo=memo,
            extents=extents,
        )
        return ComposedRun(blocks=run, box=vpack(vlist).box, extents=tuple(extents))


def _extent(node: Node) -> Scaled:
    """
    How far one item of a naturally-set vertical list moves the pen down.

    Only what `_stacked` puts in a vertical list: boxes, the block-gap kern and
    interline glue. The glue is at its natural width because nothing here packs
    a vertical list to a target, so `vpack` sets no glue and ship-out advances
    by exactly `spec.width`.
    """
    match node:
        case Box():
            return node.height + node.depth
        case Kern():
            return node.width
        case Glue():
            return node.spec.width
        case _:
            return 0


def _stacked(
    blocks: tuple[Block, ...],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
    depth: int,
    memo: _Memo | None,
    extents: list[tuple[Scaled, Scaled]] | None = None,
) -> list[Node]:
    """
    Stack blocks into a vertical list, barring each run quoted deeper than `depth`.

    `depth` is the quote nesting this call is *inside*, so the top-level call
    passes zero and every run of blocks at depth 1 or more becomes one barred
    box; `_barred` then calls back in at depth 1 and a doubly-quoted run inside
    it gets its own bar. That recursion is the whole of the nesting support and
    it is why the run-gathering takes a depth rather than asking "is this
    quoted".

    `extents`, when given, receives one `(top, bottom)` per block in `blocks`,
    in order, measured down from the top of the list being built. It is
    bookkeeping beside the stacking and changes nothing about it: the same
    nodes are appended whether or not anyone asked where they landed.
    """
    vlist: list[Node] = []
    prev_depth: Scaled = IGNORE_DEPTH
    space_below: Scaled = 0
    pen: Scaled = 0
    counted = 0

    for run in _runs(blocks, depth):
        style = run[0].style
        if vlist:
            gap = space_below + style.space_above
            if gap:
                vlist.append(Kern(width=gap))
            # A fresh rhythm: the kern is the gap, and interline glue on top of
            # it would add a second one.
            prev_depth = IGNORE_DEPTH
        if extents is not None:
            pen += sum(_extent(node) for node in vlist[counted:])
            counted = len(vlist)
        boxes: tuple[Box, ...]
        if _quote_depth(run[0]) > depth:
            inner: list[tuple[Scaled, Scaled]] | None = None if extents is None else []
            boxes = (_barred(run, theme, width, measure, params, depth + 1, memo, inner),)
            if extents is not None and inner is not None:
                # The barred box is an hbox exactly as tall as the vbox inside
                # it, so the inner list's top is this box's top.
                extents.extend((pen + top, pen + bottom) for top, bottom in inner)
        else:
            boxes = _cached_block_boxes(run[0], theme, width, measure, params, memo)
        for box in boxes:
            prev_depth = append_to_vlist(vlist, box, prev_depth, style.interline)
            if isinstance(box, _WrappedRow):
                # `\prevdepth` after a `\vtop`: see `_WrappedRow`.
                prev_depth = box.resumed_depth
        if extents is not None:
            top = pen
            pen += sum(_extent(node) for node in vlist[counted:])
            counted = len(vlist)
            if _quote_depth(run[0]) <= depth:
                extents.append((top, pen))
        space_below = run[-1].style.space_below

    return vlist


def _quote_depth(block: Block) -> int:
    """
    How many block quotes enclose this block.

    Only a `TextBlock` records it. A fenced code block, a table or a thematic
    break inside a quote therefore reads as depth zero here, which means it
    **interrupts the bar**: the quote comes out as two barred runs with an
    unbarred block between them. That is a real limitation and the alternative is
    a `quote_depth` field on four dataclasses in `advtext.markdown`, which is the
    fix if anyone writes that document.
    """
    return block.quote_depth if isinstance(block, TextBlock) else 0


def _runs(blocks: tuple[Block, ...], depth: int) -> list[tuple[Block, ...]]:
    """
    `blocks`, with each consecutive run quoted deeper than `depth` gathered into one.

    Everything else comes back as a run of one, so the caller has a single loop
    rather than a loop and a special case.
    """
    runs: list[tuple[Block, ...]] = []
    pending: list[Block] = []
    for block in blocks:
        if _quote_depth(block) > depth:
            pending.append(block)
            continue
        if pending:
            runs.append(tuple(pending))
            pending = []
        runs.append((block,))
    if pending:
        runs.append(tuple(pending))
    return runs


def _barred(
    run: tuple[Block, ...],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
    depth: int,
    memo: _Memo | None,
    extents: list[tuple[Scaled, Scaled]] | None = None,
) -> Box:
    """
    One block quote: its blocks stacked, with a rule down the left of the lot.

    The second pass the bar needs. A rule beside a quote has to be exactly as
    tall as the quote, and how tall the quote is not known until its paragraphs
    have been broken and packed -- so the run is stacked into a vbox first, and
    the rule is then built from that vbox's own height and depth. `Theme` has
    carried `quote_rule_thickness` since it was written and nothing drew it,
    because the first pass is where everything else in this module happens.

    The rule is placed with a **negative kern** afterwards, which is how TeX puts
    two things in the same horizontal space (`\\kern-\\wd0`). The alternative
    would be shifting the vbox right by the bar's width, and that would move the
    text: the quote's lines already carry their own indent from `ParShape`, so
    the vbox has to sit at x = 0 and the rule has to be the thing that moves.
    """
    inner = vpack(_stacked(run, theme, width, measure, params, depth, memo, extents)).box
    indents = [block.left_indent for block in run if isinstance(block, TextBlock)]
    bar_x = max(0, min(indents, default=theme.quote_indent) - theme.quote_indent)
    thickness = theme.quote_rule_thickness
    return hpack(
        [
            Kern(width=bar_x),
            Rule(width=thickness, height=inner.height, depth=inner.depth),
            Kern(width=-(bar_x + thickness)),
            inner,
        ],
        measure=measure,
    ).box


def _cached_block_boxes(
    block: Block,
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
    memo: _Memo | None,
) -> tuple[Box, ...]:
    """
    `_block_boxes`, through the cache when there is one.

    The only place composition consults a `LayoutCache`. One block's line boxes
    are the unit because that is the largest thing whose inputs are all in the
    key -- a whole document's box additionally depends on the interline glue
    between one block and the next, which is not a property of either.
    """
    if memo is None:
        return _block_boxes(block, theme, width, measure, params)
    return memo.cache.boxes(
        memo.generation,
        (block, width, memo.context),
        lambda: _block_boxes(block, theme, width, measure, params),
    )


def _block_boxes(
    block: Block, theme: Theme, width: Scaled, measure: CharMeasure, params: LineBreakParams
) -> tuple[Box, ...]:
    """
    One block as the line boxes it occupies, top to bottom.

    Every box that is a line of *text* comes back set on the block's strut; the
    rule blocks do not. The module docstring says why.

    A tuple rather than a list because a `LayoutCache` hands the same result to
    every caller that asks for it, and a mutable sequence shared between two
    frames is a defect waiting for the first caller that edits one in place.
    """
    strut = block.style.strut
    match block:
        case TextBlock():
            return tuple(
                strut.applied_to(box) for box in _text_boxes(block, theme, width, measure, params)
            )
        case HostBlock():
            return (_host_box(block),)
        case CodeBlock():
            return tuple(
                strut.applied_to(
                    replace(hpack(line, measure=measure).box, shift_amount=block.left_indent)
                )
                for line in block.lines
            )
        case RuleBlock():
            return (_rule_box(block, width, measure),)
        case TableBlock():
            return tuple(_table_boxes(block, theme, width, measure, params))


def _skips(align: Align, params: LineBreakParams) -> LineBreakParams:
    r"""
    The `\leftskip`/`\rightskip` pair that produces one alignment (§886, §887).

    Justification is the *absence* of the trick: with no `\rightskip` the surplus
    has nowhere to go but the interword glue. Every other alignment is a
    placement of infinitely stretchable glue, which is why there is no alignment
    branch anywhere below this function.

    **Ragged left and centred take the `\parfillskip` away as well.** It is
    `fil` glue at the right-hand end of the last line, and a left skip is `fil`
    glue too, so on the last line the two share the slack in proportion to
    their stretch: the line ended `slack / 65537` short of the margin ragged
    left (measured by A7-stream at about 0.003 pt on a 305 pt measure) and was
    off centre by half that centred. With no `\parfillskip` the last line has
    exactly the glue every other line has. `_cell_params` already did this for
    table cells and `advtext.markdown._fill_and_break` does it for the line
    before a hard break. Justified and ragged-right keep the default: there
    the `\parfillskip` is the only thing that lets a last line be short.
    """
    match align:
        case Align.JUSTIFY:
            return replace(params, left_skip=GlueSpec(), right_skip=GlueSpec())
        case Align.LEFT:
            return replace(params, left_skip=GlueSpec(), right_skip=RAGGED_RIGHT)
        case Align.RIGHT:
            return replace(
                params, left_skip=RAGGED_RIGHT, right_skip=GlueSpec(), par_fill_skip=GlueSpec()
            )
        case Align.CENTER:
            return replace(
                params, left_skip=RAGGED_RIGHT, right_skip=RAGGED_RIGHT, par_fill_skip=GlueSpec()
            )


def _shape(block: TextBlock, width: Scaled) -> ParShape:
    """
    The per-line widths for one block, including any first-line indent.

    `BlockStyle.first_line_indent` is zero in the default theme, so this is a
    `ParShape.uniform` in practice -- but the field exists, and a shape is the
    only place it can be honoured. Dropping it here would make it silently
    inert, which is worse than not having it.
    """
    indent = block.left_indent
    available = max(width - indent, UNITY)
    first = block.style.first_line_indent
    if not first:
        return ParShape.uniform(available, indent)
    return ParShape(
        (
            LineSpec(max(available - first, UNITY), indent + first),
            LineSpec(available, indent),
        )
    )


def _text_boxes(
    block: TextBlock, theme: Theme, width: Scaled, measure: CharMeasure, params: LineBreakParams
) -> list[Box]:
    r"""
    Break one text block into lines, hanging its marker on the first of them.

    **A justified block goes through the total-fit optimiser; any other
    alignment is broken first-fit, with its interword shrink removed.** Two
    measured reasons, neither of them taste:

    - Ragged setting is a `\rightskip` of `fil`, under which every line that
      fits costs the optimiser the same. Its active list then grows with the
      paragraph, and the 635-node paragraph of `demo/sample.md` takes 2.5 to
      9.3 *seconds* ragged against about 30 ms justified
      (`.concerns/A7-greedy--builder--result.md`). First-fit takes 5 to 9 ms.
    - Ahead of a word wider than the measure the optimiser's last-resort break
      comes from the chain with the most lines, which sets every earlier word
      on a line of its own (`tests/test_stream_stability.py`).

    **The shrink is removed so that a line is fitted at its natural width.**
    First-fit asks `hpack` whether a line fits, and `hpack` will compress the
    interword spaces to make it fit. In ragged text that produces a line set
    tighter than its neighbours for no reason a reader can see -- the right
    edge is not being reached for -- so the material is handed over with
    nothing to compress and "fits" means "is no wider than the measure".
    The stretch is left alone; it is never used, because the `fil` in the skip
    outranks it.

    With the shrink removed first-fit and total-fit choose **the same breaks**
    on every block of the demo document at 300, 420 and 800 pt (measured by
    A7-greedy: 0 of 34 blocks differ). What differs from what this function
    did before is therefore exactly the lines the optimiser used to set
    compressed; `.concerns/A5-tables--builder--result.md` counts them.

    `ComposeParams(ragged_total_fit=True)` restores the old path unchanged.
    """
    align = block.style.align
    material = block.material
    line_params = _skips(align, params)
    if align is not Align.JUSTIFY and not (
        isinstance(params, ComposeParams) and params.ragged_total_fit
    ):
        material = _unshrinkable(material)
        line_params = replace(line_params, first_fit=True)
    broken = break_paragraph(
        material,
        _shape(block, width),
        line_params,
        measure=measure,
    )
    lines = list(broken.boxes)
    if block.marker and lines:
        lines[0] = _hang_marker(lines[0], block.marker, block.left_indent, theme, measure)
    return lines


def _unshrinkable(material: tuple[Node, ...]) -> tuple[Node, ...]:
    """
    `material` with every glue's shrink removed, so nothing in it can be set tight.

    What makes a first-fit line "fit" mean "no wider than the measure at its
    natural spacing". Glue with no shrink is passed through as the same
    object, and each distinct spec is rewritten once, because a paragraph has
    hundreds of interword glues and two or three distinct specs.
    """
    rewritten: dict[GlueSpec, GlueSpec] = {}
    out: list[Node] = []
    for node in material:
        if isinstance(node, Glue) and node.spec.shrink:
            spec = rewritten.get(node.spec)
            if spec is None:
                spec = replace(node.spec, shrink=0, shrink_order=GlueOrder.NORMAL)
                rewritten[node.spec] = spec
            out.append(replace(node, spec=spec))
        else:
            out.append(node)
    return tuple(out)


def _hang_marker(
    line: Box,
    marker: tuple[Node, ...],
    indent: Scaled,
    theme: Theme,
    measure: CharMeasure,
) -> Box:
    """
    Put a list marker in the margin the first line gave up.

    The marker sits in a box exactly `indent` wide, pushed right by `\\hss` and
    held off the text by `marker_gap`, so "1." and "10." both end at the same
    place and every item's text starts at the same x. The line's own
    `shift_amount` is dropped, because the marker box now supplies that offset.
    """
    # Stretch only, no shrink. A marker wider than the gutter -- "10." in a list
    # whose indent was sized for "1." -- would otherwise shrink an \hss to a
    # *negative* width and hang the digit off the left edge of the document. With
    # stretch alone the box simply overfulls: the marker starts at the item's own
    # left edge and eats into the gap, which is the right thing to lose.
    marker_box = hpack(
        [
            Glue(GlueSpec(stretch=UNITY, stretch_order=GlueOrder.FIL)),
            *marker,
            Kern(width=theme.marker_gap),
        ],
        indent,
        PackMode.EXACTLY,
        measure=measure,
    ).box
    return hpack([marker_box, replace(line, shift_amount=0)], measure=measure).box


def _rule_box(block: RuleBlock, width: Scaled, measure: CharMeasure) -> Box:
    """
    A thematic break as a box, rather than as a bare `Rule` in the vertical list.

    §679 suppresses interline glue on both sides of a vertical-list rule, which
    is right for a `\\hrule` written by hand and wrong here: the block gap either
    side is already an explicit kern, and a bare rule would additionally lose the
    rhythm it does not need to lose. Wrapping it in an hbox keeps it an ordinary
    item.
    """
    return hpack(
        [
            Kern(width=block.left_indent),
            Rule(width=width - block.left_indent, height=block.thickness, depth=0),
        ],
        measure=measure,
    ).box


@dataclass(frozen=True, slots=True)
class HostBlock(CodeBlock):
    """
    A rectangle the layout reserves and something else draws in: a block that sets no text.

    What `advtext.ui.bare_view.BareView` lays out in the place of a block a
    host has claimed (`BareView.host_for`): as tall as `height`, as wide as
    the measure, holding no glyph and no reading-order index. The unit it
    becomes has no commands, so nothing is drawn, culled, indexed or selected
    for it; the view finds it by block number and hands its rectangle to
    `host`. It never appears in a `Document`: `document.blocks[n]` is still
    the block the markdown made, which is what hit testing, the source map and
    `set_colours` go on naming.

    **A subclass of `CodeBlock` with no lines, for the reason `SizedTable` is a
    subclass**: everything in this package that asks what a block *is* --
    `advtext.ui.bare_view.block_kind`, the separators a copy writes, the list
    a block belongs to, the unit cache's shape -- has an answer for a code
    block already, and for an empty one the answer is "nothing here", which
    is right. Only composition needs to know the difference (`_block_boxes`),
    and it has to: a code block of no lines has no height. It is also what
    the diff this was built for *is*: a fenced block, set some other way.
    (A fence is never part of a quote's run -- `_quote_depth` -- so a
    `HostBlock` is always a unit by itself.)

    `height` is in scaled points. `host` is compared like any field, which
    for an ordinary object means by identity: two host blocks are the same
    layout when they are the same height standing for the same widget.
    """

    height: Scaled = 0
    host: Hosted | None = None


def _host_box(block: HostBlock) -> Box:
    """
    A box `block.height` tall with nothing in it.

    A vbox holding one kern, not an empty hbox: ship-out gives an hbox a
    `Line` whether or not anything is on it, and an empty `Line` copies as a
    newline and takes a caret. A vbox of one kern ships nothing at all.
    """
    return vpack([Kern(width=max(block.height, 0))]).box


@dataclass(frozen=True, slots=True)
class SizedTable(TableBlock):
    """
    A table whose column widths the caller chose: the resize hook.

    A host that lets a user drag a column border, or a streaming view that
    must not let a live table's columns jitter, has widths of its own and
    needs the table set to them. `with_columns` builds one of these from the
    `TableBlock` the converter produced, and it goes into the document's
    `blocks` in the original's place; `table_columns` reports the widths a
    table would get, which is where a drag starts from.

    **A subclass, so that the widths are part of the block.** Composition
    caches by block value (`LayoutCache`, `advtext.ui.units.UnitCache`), and a
    table at two sets of widths is two layouts. Carrying the widths in the
    block makes that true with no change to any key; passing them beside the
    document would have made every cache in the tree responsible for
    remembering them. The field belongs on `TableBlock` itself and is here
    only because `advtext.markdown` had other writers when this was built --
    `isinstance(block, TableBlock)` holds, so nothing that reads a table needs
    to know.

    Exactly one of the two is set. Widths are absolute scaled points and
    **include the cell padding**, as the default apportioning's do; they are
    used as given, so the table is as wide as they sum to, whatever the
    measure. Fractions are shares of the measure and always fill it.

    **Checked on construction, by every route** -- `with_columns`, a direct
    call, `dataclasses.replace`. One entry per column; a width a whole number
    of scaled points and at least one; a fraction finite, positive, and still
    positive as a share of the total. A table that failed any of these used to
    construct and then fail (or silently lose a column) at the compose a frame
    later: two widths for three columns raised `IndexError` in `_table_boxes`.
    With neither set this is a plain table and is laid out as one.
    """

    column_widths: tuple[Scaled, ...] = ()
    column_fractions: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.column_widths and self.column_fractions:
            raise ValueError(
                "a sized table has exactly one of `column_widths` and `column_fractions`; "
                "both were given"
            )
        chosen = self.column_widths or self.column_fractions
        if not chosen:
            return
        columns = max((len(row) for row in _table_rows(self)), default=0)
        if len(chosen) != columns:
            raise ValueError(f"the table has {columns} columns and {len(chosen)} widths were given")
        for width in self.column_widths:
            if type(width) is not int or width < 1:
                raise ValueError(
                    f"a column width is a whole number of scaled points, at least 1; got {width!r}"
                )
        if self.column_fractions:
            _checked_fractions(self.column_fractions)


def _checked_fractions(fractions: Sequence[object]) -> tuple[float, ...]:
    """
    `fractions` as floats, or `ValueError` if they are not shares of anything.

    Each must be a finite positive number, and so must each one's share of the
    total: three entries of 1e308 are each finite and sum to infinity, and
    1e-320 beside 1e300 is positive and is zero once divided. Both would reach
    `_column_widths` as a NaN or a zero and neither is a width.
    """
    out: list[float] = []
    for entry in fractions:
        if isinstance(entry, bool) or not isinstance(entry, int | float):
            raise ValueError(f"a column fraction is a number, got {entry!r}")
        share = _as_float(entry)
        if not math.isfinite(share) or share <= 0:
            raise ValueError(f"a column fraction must be positive and finite, got {entry!r}")
        out.append(share)
    total = sum(out)
    if not math.isfinite(total) or any(entry / total <= 0 for entry in out):
        raise ValueError(
            f"every column fraction must be a positive share of their total, got {tuple(out)}"
        )
    return tuple(out)


def _as_float(entry: int | float) -> float:
    """
    `entry` as a float, an integer too large for one reading as infinity.

    `float(10**400)` raises `OverflowError`, which is not the error a caller
    validating its own input is told to expect.
    """
    try:
        return float(entry)
    except OverflowError:
        return math.inf


def _checked_widths(widths: Sequence[object]) -> tuple[Scaled, ...]:
    """
    `widths` rounded to whole scaled points, or `ValueError` if one is not a width.

    Rounded and not truncated, because a host dragging a border has a float
    and the nearest unit is what it means. Refused when the result is less
    than one unit: `int(0.4)` was accepted as a width of 0, and a caller
    passing 0.4 has almost certainly passed points or a fraction where scaled
    points were wanted.
    """
    out: list[Scaled] = []
    for entry in widths:
        if isinstance(entry, bool) or not isinstance(entry, int | float):
            raise ValueError(f"a column width is a number of scaled points, got {entry!r}")
        if not math.isfinite(_as_float(entry)) or round(entry) < 1:
            raise ValueError(
                f"a column width must be at least 1 scaled point and finite, got {entry!r}"
            )
        out.append(round(entry))
    return tuple(out)


def _table_rows(block: TableBlock) -> list[tuple[TableCell, ...]]:
    """
    Every row of a table, the header first if there is one.
    """
    return [block.header, *block.rows] if block.header else list(block.rows)


def with_columns(
    block: TableBlock,
    *,
    widths: Sequence[Scaled] | None = None,
    fractions: Sequence[float] | None = None,
) -> SizedTable:
    """
    `block`, with its column widths fixed by the caller instead of apportioned.

    Give `widths` (scaled points, padding included) or `fractions` (shares of
    the measure, in any unit: they are normalised), one entry per column.
    Cells are wrapped to whatever results, exactly as they are under the
    default apportioning. Passing a `SizedTable` replaces its widths.

    Widths that are not whole scaled points are rounded to them.

    Refuses, here at the call: the wrong number of columns; a width under one
    scaled point; a fraction that is not positive; anything not finite or not
    a number. The alternative is the compose that would otherwise discover it
    a frame later with the host's drag handler no longer on the stack -- or
    not discover it, and set a column to no width. `SizedTable` checks the
    same things for a caller that builds one directly.
    """
    if (widths is None) == (fractions is None):
        raise ValueError("give exactly one of `widths` and `fractions`")
    chosen = tuple(widths if widths is not None else fractions or ())
    columns = max((len(row) for row in _table_rows(block)), default=0)
    if len(chosen) != columns:
        raise ValueError(f"the table has {columns} columns and {len(chosen)} widths were given")
    return SizedTable(
        style=block.style,
        header=block.header,
        rows=block.rows,
        aligns=block.aligns,
        left_indent=block.left_indent,
        column_widths=_checked_widths(chosen) if widths is not None else (),
        column_fractions=_checked_fractions(chosen) if fractions is not None else (),
    )


def table_columns(
    block: TableBlock,
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams | None = None,
) -> tuple[Scaled, ...]:
    """
    The column widths `compose` sets this table to at this measure, padding included.

    The same function composition calls, so the answer cannot drift from the
    layout. For a `SizedTable` it is what the caller asked for; otherwise it is
    the default apportioning. A host starts a column drag from these, and a
    streaming view keeps a running maximum of them.
    """
    params = PROSE_BREAKING if params is None else params
    rows = _table_rows(block)
    if not rows:
        return ()
    natural = _natural_widths(rows, theme.cell_padding, measure)
    return tuple(_column_widths(block, rows, natural, theme, width, measure, params))


def table_natural_widths(
    block: TableBlock, theme: Theme, measure: CharMeasure
) -> tuple[Scaled, ...]:
    """
    Each column's widest cell set on one line, padding included: what the table wants.

    Independent of any measure, which is why it is separate from
    `table_columns`: that one answers "what will compose set this to *here*",
    and scales a table that fits up to the measure. This is the number that
    only ever **grows** while a table is being written -- a cell gains text, a
    row is added, and no column's widest cell gets narrower -- so it is what a
    streaming view holds a live table's columns to (`advtext.ui.stream_view`),
    where the apportioned widths move every column each time one of them
    grows.
    """
    rows = _table_rows(block)
    if not rows:
        return ()
    natural = _natural_widths(rows, theme.cell_padding, measure)
    columns = max(len(row) for row in rows)
    widest = [0] * columns
    for sizes in natural:
        for index, size in enumerate(sizes):
            widest[index] = max(widest[index], size)
    return tuple(widest)


@dataclass(frozen=True, slots=True)
class ColumnLimits:
    """
    How narrow and how wide each column of a table is worth making, padding included.

    `floor[i]` is column `i`'s longest unbreakable stretch: narrower than
    that and a word sticks out of its cell. `natural[i]` is its widest cell
    set on one line: wider than that and nothing in it changes. Both are
    independent of any measure, and `floor[i] <= natural[i]`.
    """

    floor: tuple[Scaled, ...]
    natural: tuple[Scaled, ...]


def table_column_limits(
    block: TableBlock,
    theme: Theme,
    measure: CharMeasure,
    params: LineBreakParams | None = None,
) -> ColumnLimits:
    """
    Each column's longest-word floor and its natural width, in one call.

    What a host needs before it lets anyone drag a column edge: the range a
    width can sensibly be clamped to before it is handed to `with_columns`.
    `natural` is `table_natural_widths`. `floor` is the number `table_columns`
    squeezes a too-wide table down towards and never below (`_squeezed`), and
    it is worked out by the same function (`_longest_word`, the line
    breaker's own answer to "where may this cell wrap"), so the two cannot
    disagree: `floor == table_columns(block, theme, one_point, measure)` for a
    table that is not a `SizedTable`, which is how the demo's Tables page
    obtained it before this existed and what `tests/test_viewapi.py` holds.

    Any widths a `SizedTable` carries are ignored: these are limits of the
    content. Costs one `hpack` and one first-fit line break a cell, every
    call; a host dragging a column should ask once per table and keep the
    answer. Empty for a table with no rows.
    """
    params = PROSE_BREAKING if params is None else params
    rows = _table_rows(block)
    if not rows:
        return ColumnLimits((), ())
    padding = theme.cell_padding
    columns = max(len(row) for row in rows)
    natural = [0] * columns
    floor = [0] * columns
    for row, sizes in zip(rows, _natural_widths(rows, padding, measure), strict=True):
        for index, cell in enumerate(row):
            natural[index] = max(natural[index], sizes[index])
            floor[index] = max(
                floor[index], _longest_word(cell.material, params, measure) + 2 * padding
            )
    return ColumnLimits(floor=tuple(floor), natural=tuple(natural))


@dataclass(slots=True)
class TableMeasure:
    """
    A table's column measurements, kept from one layout to the next while it gains rows.

    `table_natural_widths` and `table_columns` measure every cell of every
    row each time they are asked: one `hpack` a cell, and for a table too
    wide for the measure a line break a cell as well (`_longest_word`). For a
    table that is being written that is the whole table measured again for
    every row that arrives -- 5 ms of a 25 ms layout at 55 rows of three
    columns when it was profiled, and it grows with the table.

    One of these, kept by whoever lays the table out repeatedly
    (`advtext.ui.stream_view` keeps one per live table), measures a row
    **once**. It remembers the rows it has measured *by identity*, in order:
    a row that is the object it was last time is not measured again, and from
    the first row that is not, everything is. So it cannot answer for a row
    it has not seen, whatever was done to the table in between -- a row
    replaced, rows removed, another table altogether. `advtext.stream` hands
    back the rows it has already converted as the objects they were, which
    is what makes this pay; a caller that rebuilds its rows each time gets
    the right answer at the old price.

    `natural` is `table_natural_widths` and `columns` is `table_columns`, to
    the scaled point: `tests/test_tables.py` holds them equal through a table
    growing, its last row changing under it and its rows being cut back.

    What is still proportional to the table, per call: one pointer comparison
    a row, to find where the rows stop being the ones measured.
    """

    _rows: list[tuple[TableCell, ...]] = field(default_factory=list)
    # Each measured row's cell widths, and the column maxima over the rows up
    # to and including it. A list per row so that a changed last row costs
    # that row and not the table.
    _natural: list[list[Scaled]] = field(default_factory=list)
    _widest: list[list[Scaled]] = field(default_factory=list)
    # The same for each cell's longest unbreakable stretch. Shorter than
    # `_rows` until a table that does not fit asks: a line break a cell is
    # not paid for by a table that never needs it.
    _narrowest: list[list[Scaled]] = field(default_factory=list)
    # What the numbers were measured with; anything else starts again.
    _with: tuple[Scaled, CharMeasure] | None = None
    _breaking: LineBreakParams | None = None

    def _taken(self, block: TableBlock, padding: Scaled, measure: CharMeasure) -> int:
        """
        Measure whatever rows of `block` are new, and return how many it has.
        """
        rows = _table_rows(block)
        if self._with is None or self._with[0] != padding or self._with[1] is not measure:
            self._rows, self._natural, self._widest, self._narrowest = [], [], [], []
            self._with = (padding, measure)
        known = self._rows
        same = 0
        limit = min(len(known), len(rows))
        while same < limit and known[same] is rows[same]:
            same += 1
        del known[same:], self._natural[same:], self._widest[same:], self._narrowest[same:]
        for row in rows[same:]:
            sizes = _natural_widths([row], padding, measure)[0]
            known.append(row)
            self._natural.append(sizes)
            self._widest.append(_column_maxima(self._widest[-1] if self._widest else [], sizes))
        return len(rows)

    def natural(self, block: TableBlock, theme: Theme, measure: CharMeasure) -> tuple[Scaled, ...]:
        """
        `table_natural_widths(block, theme, measure)`, measuring only the rows that are new.
        """
        if not self._taken(block, theme.cell_padding, measure):
            return ()
        return tuple(self._widest[-1])

    def columns(
        self,
        block: TableBlock,
        theme: Theme,
        width: Scaled,
        measure: CharMeasure,
        params: LineBreakParams | None = None,
    ) -> tuple[Scaled, ...]:
        """
        `table_columns(block, theme, width, measure, params)`, measuring only the rows that are new.

        The three regimes are `_column_widths`'s, in its words and by its
        functions; what differs is where the column maxima come from.
        """
        params = PROSE_BREAKING if params is None else params
        padding = theme.cell_padding
        if not self._taken(block, padding, measure):
            return ()
        if isinstance(block, SizedTable) and (block.column_widths or block.column_fractions):
            rows = _table_rows(block)
            return tuple(_column_widths(block, rows, self._natural, theme, width, measure, params))
        widest = list(self._widest[-1])
        available = max(width - block.left_indent, UNITY)
        if sum(widest) <= available:
            return tuple(_apportioned(widest, available))
        if self._breaking is not params and self._breaking != params:
            del self._narrowest[:]
            self._breaking = params
        for row in self._rows[len(self._narrowest) :]:
            floors = [_longest_word(cell.material, params, measure) + 2 * padding for cell in row]
            self._narrowest.append(
                _column_maxima(self._narrowest[-1] if self._narrowest else [], floors)
            )
        narrowest = self._narrowest[-1] + [0] * (len(widest) - len(self._narrowest[-1]))
        return tuple(_squeezed(widest, narrowest, available))


def _column_maxima(so_far: list[Scaled], sizes: list[Scaled]) -> list[Scaled]:
    """
    Column by column, the larger of two rows of widths; a column only one has keeps its own.
    """
    if len(so_far) == len(sizes):
        return [max(pair) for pair in zip(so_far, sizes, strict=True)]
    long, short = (so_far, sizes) if len(so_far) > len(sizes) else (sizes, so_far)
    return [
        max(size, short[index]) if index < len(short) else size for index, size in enumerate(long)
    ]


def prev_depth_after(box: Box) -> Scaled:
    r"""
    The `\prevdepth` a vertical list goes on from after `box`: what the next interline glue reads.

    A box's own depth, except after a table row whose cells wrapped
    (`_WrappedRow`), where it is the depth of the row's last line. `_stacked`
    applies exactly this as it appends a block's boxes; it is public for
    `advtext.ui.units`, which lays a long table out in pieces and has to put
    between two pieces the glue `_stacked` would have put between those two
    rows.
    """
    return box.resumed_depth if isinstance(box, _WrappedRow) else box.depth


def _natural_widths(
    rows: list[tuple[TableCell, ...]], padding: Scaled, measure: CharMeasure
) -> list[list[Scaled]]:
    """
    Every cell's width set on one line, padding included, row by row.
    """
    return [
        [hpack(cell.material, measure=measure).box.width + 2 * padding for cell in row]
        for row in rows
    ]


def _column_widths(
    block: TableBlock,
    rows: list[tuple[TableCell, ...]],
    natural: list[list[Scaled]],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
) -> list[Scaled]:
    """
    One width per column: the caller's if it gave any, else apportioned to the measure.

    Three regimes for the default, and the first is unchanged from before
    cells could wrap:

    - **The table fits.** Columns are scaled *up* in proportion to fill the
      measure (`_apportioned`). No cell is narrower than its content, so none
      wraps, and the table is set exactly as it always was.
    - **It does not fit, but would if its cells wrapped.** Every column keeps
      at least its longest unbreakable word (`_squeezed`), and what is left of
      the measure is shared in proportion to how much each column *could*
      give up. The table is exactly as wide as the measure.
    - **Not even the longest words fit.** Each column gets its longest word
      and the table is wider than the measure. This is the overfull case that
      remains, and it is the same one a paragraph has with a word wider than
      its line.

    Before wrapping existed the second and third regimes were one: every
    column was scaled *down* in proportion and its cells ran into the next
    column. Scaling a column of one-word labels down by the same factor as a
    column of sentences is what made that inevitable, and is why the squeeze
    is not proportional to natural width.
    """
    columns = max(len(row) for row in rows)
    available = max(width - block.left_indent, UNITY)
    if isinstance(block, SizedTable):
        if block.column_widths:
            return list(block.column_widths)
        if block.column_fractions:
            return _shared(block.column_fractions, available)

    widest = [0] * columns
    for sizes in natural:
        for index, size in enumerate(sizes):
            widest[index] = max(widest[index], size)
    if sum(widest) <= available:
        return _apportioned(widest, available)

    padding = theme.cell_padding
    narrowest = [0] * columns
    for row in rows:
        for index, cell in enumerate(row):
            floor = _longest_word(cell.material, params, measure) + 2 * padding
            narrowest[index] = max(narrowest[index], floor)
    return _squeezed(widest, narrowest, available)


def _shared(fractions: tuple[float, ...], available: Scaled) -> list[Scaled]:
    """
    `available` divided in the proportions of `fractions`, every column at least one unit.

    Rounded shares, with the last column taking the rounding remainder as it
    does in `_apportioned`, so the widths sum to `available` exactly. Two
    things that rule alone gets wrong for a very small share, and neither can
    be refused when the fractions are given because the measure is not known
    then: the share rounds to zero, and the remainder -- which can be negative
    -- lands on a last column that is itself a rounding away from zero. So
    each share is floored at one scaled point, and whatever that or the
    remainder would take from the last column below one is taken from the
    widest instead. `available` is at least a point (65536 units), so the
    widest column always has it to give.
    """
    total = sum(fractions)
    shares = [max(1, round(available * share / total)) for share in fractions]
    shares[-1] += available - sum(shares)
    if shares[-1] < 1:
        widest = max(range(len(shares)), key=shares.__getitem__)
        shares[widest] -= 1 - shares[-1]
        shares[-1] = 1
    return shares


def _longest_word(
    material: tuple[Node, ...], params: LineBreakParams, measure: CharMeasure
) -> Scaled:
    """
    The width of the widest stretch of a cell that no line break can divide.

    Asked of the line breaker rather than worked out here: the cell is broken
    first-fit at a width nothing fits in, which puts every unbreakable stretch
    on a line of its own, and each line is then measured at its natural width.
    So "where may a cell wrap" has one answer, the breaker's, and this cannot
    disagree with the wrapping it sizes columns for.
    """
    if not material:
        return 0
    broken = break_paragraph(
        material,
        ParShape.uniform(UNITY),
        replace(params, first_fit=True, left_skip=GlueSpec(), right_skip=GlueSpec()),
        measure=measure,
    )
    return max(
        (hpack(line.contents, measure=measure).box.width for line in broken.boxes), default=0
    )


def _squeezed(widest: list[Scaled], narrowest: list[Scaled], available: Scaled) -> list[Scaled]:
    """
    Column widths for a table too wide for `available`: floors first, then the slack.

    Each column starts at `narrowest`, its longest word, and the measure left
    over is shared in proportion to `widest - narrowest` -- how much room the
    column's content would use if it had it. A column whose widest cell is one
    word has nothing to gain and gets nothing, which is what keeps a column of
    labels from being wrapped to make room for a column of prose.

    The last column takes the rounding remainder, as in `_apportioned`, so the
    widths sum to `available` exactly and the header rule lands on the margin.
    When the floors alone exceed `available` they are returned as they are and
    the table is wider than the measure.
    """
    slack = available - sum(narrowest)
    if slack <= 0:
        return list(narrowest)
    give = [wide - narrow for wide, narrow in zip(widest, narrowest, strict=True)]
    total = sum(give)
    if total <= 0:
        return list(narrowest)
    widths = [narrow + slack * room // total for narrow, room in zip(narrowest, give, strict=True)]
    widths[-1] += available - sum(widths)
    return widths


def _table_boxes(
    block: TableBlock,
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
) -> list[Box]:
    """
    Size a table's columns, then set every row to them.

    Natural widths first, widest per column wins, then every cell is set to its
    column's width with its column's alignment. Two passes because a column's
    width is a property of the whole column and no cell can know it alone.
    `_column_widths` decides the widths and says how.

    **A cell wider than its column is broken as a paragraph at the column's
    width**, ragged on the side its alignment leaves free, and its row is as
    tall as its tallest cell. `\\halign`'s real problem -- a width that depends
    on a breaking that depends on the width -- does not arise, because the
    widths are fixed from the cells' natural and longest-word widths *before*
    anything is broken, and the breaking then only decides heights.

    **A row in which every cell fits is set exactly as it was before cells
    could wrap**: one hbox, each cell packed to its column's width. So a table
    that fits the measure produces the same boxes it always did, and
    `tests/test_tables.py` asserts that on the demo document's table rather
    than leaving it as this sentence. A row with a wrapped cell is built
    differently for every cell in it -- see `_wrapped_row` for why -- and comes
    back as a `_WrappedRow`, which is how the row after it stays on the
    baseline grid.

    **What still overfulls**: a column narrower than its longest word, which
    happens when a caller's `with_columns` says so or when the longest words
    alone exceed the measure. The word is set whole and runs into the next
    column, as an over-wide word in a paragraph runs into the margin.
    """
    rows = _table_rows(block)
    if not rows:
        return []

    columns = max(len(row) for row in rows)
    padding = theme.cell_padding
    natural = _natural_widths(rows, padding, measure)
    widths = _column_widths(block, rows, natural, theme, width, measure, params)

    aligns = tuple(block.aligns) + (ColumnAlign.LEFT,) * (columns - len(block.aligns))
    strut = block.style.strut
    boxes: list[Box] = []
    for row, row_natural in zip(rows, natural, strict=True):
        fits = all(cell <= widths[index] for index, cell in enumerate(row_natural))
        if fits:
            set_row = _table_row(row, widths, aligns, block.left_indent, padding, measure)
        else:
            set_row = _wrapped_row(row, widths, aligns, block, padding, measure, params)
        # The strut goes on the row and not on each cell: a cell is a sub-box of
        # the row's hlist, so flooring the row floors every cell in it, and one
        # strut per row is what keeps a row of digits the same height as a row
        # with a descender in it.
        boxes.append(strut.applied_to(set_row))
        if block.header and row is rows[0] and theme.table_rule_thickness:
            boxes.append(
                hpack(
                    [
                        Kern(width=block.left_indent),
                        Rule(
                            width=sum(widths),
                            height=theme.table_rule_thickness,
                            depth=0,
                        ),
                    ],
                    measure=measure,
                ).box
            )
    return boxes


def _apportioned(natural: list[Scaled], available: Scaled) -> list[Scaled]:
    """
    Column widths scaled to fill exactly `available`, keeping their proportions.

    In proportion rather than equally, and in both directions rather than only
    downward. Proportion, because a column of one-word labels beside a column of
    sentences should stay narrow -- sharing the surplus equally would give the
    labels column as much new space as the prose one and leave the table looking
    like it was set by a spreadsheet. Both directions, because a table that stops
    short of the margin the prose beside it reaches reads as a table that failed
    rather than as a narrow one.

    The last column takes the rounding remainder, so the widths sum to
    `available` **exactly** and the header rule drawn at `sum(widths)` lands on
    the margin rather than a scaled point inside it. Spreading the remainder
    would put a sub-pixel difference in every column instead of one place.
    """
    total = sum(natural)
    if total <= 0 or not natural:
        return natural
    scaled = [column * available // total for column in natural]
    scaled[-1] += available - sum(scaled)
    return scaled


def _table_row(
    row: tuple[TableCell, ...],
    widths: list[Scaled],
    aligns: tuple[ColumnAlign, ...],
    indent: Scaled,
    padding: Scaled,
    measure: CharMeasure,
) -> Box:
    """
    One row, every cell packed to its column's width.
    """
    cells: list[Node] = [Kern(width=indent)]
    for index, width in enumerate(widths):
        material: tuple[Node, ...] = row[index].material if index < len(row) else ()
        cells.append(
            hpack(
                [Kern(width=padding), *_aligned(material, aligns[index]), Kern(width=padding)],
                width,
                PackMode.EXACTLY,
                measure=measure,
            ).box
        )
    return hpack(cells, measure=measure).box


def _wrapped_row(
    row: tuple[TableCell, ...],
    widths: list[Scaled],
    aligns: tuple[ColumnAlign, ...],
    block: TableBlock,
    padding: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
) -> _WrappedRow:
    """
    One row in which at least one cell is wider than its column: every cell a stack of lines.

    Each cell is broken to its column's width and becomes a vbox whose
    reference point is its **first** line's baseline (`_cell_lines`), so the
    cells of a row hang from a common first baseline and the row is as deep as
    its longest cell.

    **Every cell of the row is built this way, including the ones that fit**,
    and the reason is reading order rather than layout. Ship-out makes a line
    of each hbox in a vertical list, and `advtext.selection` gives an item to
    the innermost line containing it. Were the short cells left as plain
    sub-boxes of the row, their glyphs would belong to the row's own line and
    the wrapped cell's to lines nested inside it, and the row's line -- which
    starts first -- would serialise *around* the wrapped cell: first column,
    third column, then the second. With every cell a stack of its own lines
    the row is only a container, and a copy reads each cell whole, left to
    right, a row at a time.

    The row records how far below its reference point its *lowest* baseline
    is -- the last line of whichever cell wrapped furthest -- because that is
    the baseline the next row steps from (`_WrappedRow`).
    """
    cells: list[Node] = [Kern(width=block.left_indent)]
    lowest: Scaled = 0
    for index, width in enumerate(widths):
        material: tuple[Node, ...] = row[index].material if index < len(row) else ()
        cell, below = _cell_lines(material, aligns[index], width, block, padding, measure, params)
        cells.append(cell)
        lowest = max(lowest, below)
    packed = hpack(cells, measure=measure).box
    return _WrappedRow(
        kind=packed.kind,
        contents=packed.contents,
        width=packed.width,
        height=packed.height,
        depth=packed.depth,
        shift_amount=packed.shift_amount,
        glue_set=packed.glue_set,
        glue_sign=packed.glue_sign,
        glue_order=packed.glue_order,
        last_baseline=lowest,
    )


@dataclass(frozen=True, slots=True)
class _WrappedRow(Box):
    r"""
    A table row whose cells are `\vtop`s, and the `\prevdepth` to resume from after it.

    **The defect this exists for, measured (review 2, item 1):** the row after
    a wrapped row sat 1.074 leadings below the wrapped row's last baseline,
    and a wrapped header put the first body row 1.369 leadings below the
    header's last baseline where an unwrapped header gives 2. The cause is
    §679 doing what it says. A row of `\vtop` cells has its reference point
    on its *first* baseline and is as deep as all the lines below it; the
    interline glue for the next box is `\baselineskip - prev_depth - height`,
    which for a depth of two leadings is far below `\lineskiplimit`, so the
    glue is `\lineskip` instead and the next row lands that far off the grid.
    (0.074 is exactly this theme's `\lineskip` over its `\baselineskip`; the
    header's 1.369 is the same `\lineskip` above the rule and a whole leading
    below it.)

    **The fix is the one TeX's own users apply**: assign `\prevdepth` after
    the `\vtop`, to the depth of its last line. The row's box is unchanged --
    it is honestly as deep as its lines, which is what the space below the
    table, the selection bands and the culling extents all need -- and only
    the depth the *interline rule* is given differs: `resumed_depth`, how far
    the row extends below its lowest baseline. `_stacked` substitutes it after
    appending the row, so the next row (or the header rule) is glued as though
    it followed the wrapped cell's last line, which it does.

    Nothing else reads the field. It is a subclass of `Box` rather than a
    value beside it because the boxes of a block travel as a tuple through
    `LayoutCache`, and the resumed depth has to be cached with the row it
    belongs to; `isinstance(row, Box)` holds, the contents are the shape
    `advtext.spans` and `advtext.ui.units` walk, and `dataclasses.replace`
    (the strut, a shift) keeps the class and the field.

    A row in which nothing wrapped to a second line -- one over-wide word --
    has `last_baseline` zero and resumes from its own depth, as a plain row.
    """

    last_baseline: Scaled = 0

    @property
    def resumed_depth(self) -> Scaled:
        """
        How far the row extends below its lowest baseline: the last line's depth.

        Taken from the row's depth as it stands, so a strut applied to the row
        afterwards is included.
        """
        return self.depth - self.last_baseline


def _cell_lines(
    material: tuple[Node, ...],
    align: ColumnAlign,
    width: Scaled,
    block: TableBlock,
    padding: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
) -> tuple[Box, Scaled]:
    r"""
    One cell broken to its column, as a `\vtop`: lines stacked below a first baseline.

    Returns the box and how far its last baseline is below its first, which
    is zero for a cell of one line and is what `_wrapped_row` needs to say
    where the row's lowest baseline is.

    Broken **first-fit** (`LineBreakParams.first_fit`). The cell is ragged, and
    ragged setting through the total-fit breaker is the case
    `.concerns/A0-bench--builder-2--ragged-compose-is-100x-slower.md` measured
    at 80 to 300 times the justified cost; first-fit is linear and, for ragged
    text, chooses the breaks a reader expects -- each line as full as it goes.

    At natural spacing, for the reason `_text_boxes` gives: the interword
    shrink is removed first, so a line fits when it is no wider than the cell
    and is never compressed to fit. That also makes this agree with
    `_table_boxes`' own test for whether a row needs wrapping at all, which
    compares natural widths.

    The column's alignment is where the infinitely stretchable glue goes, as
    in `_aligned`: on the right for a left-aligned column, on the left for a
    right-aligned one, on both sides to centre. A right-aligned or centred
    cell is also given no `\parfillskip`, because the paragraph-end glue is
    infinitely stretchable too and would pull its last line off the alignment
    the other lines have.

    Every line is set on the block's strut and the lines are joined by the
    block's interline glue, so a wrapped cell has the leading its table's
    rows have. The vbox `vpack` returns has its reference point on the *last*
    baseline; moving height into depth puts it on the first, which is all a
    `\vtop` is, and ship-out finds the top of a vbox from its height alone.

    An empty cell is one empty line: the breaker returns a line holding the
    `\parfillskip` for a paragraph with nothing in it, never no lines
    (`tests/test_tables.py::test_an_empty_cell_is_still_one_line_of_its_column`),
    so there is no case here for a cell without a line.
    """
    inner = max(width - 2 * padding, UNITY)
    broken = break_paragraph(
        _unshrinkable(material),
        ParShape.uniform(inner),
        _cell_params(align, params),
        measure=measure,
    )
    lines = broken.boxes
    strut = block.style.strut
    vlist: list[Node] = []
    prev_depth: Scaled = IGNORE_DEPTH
    for line in lines:
        set_line = strut.applied_to(replace(line, shift_amount=padding))
        prev_depth = append_to_vlist(vlist, set_line, prev_depth, block.style.interline)
    stacked = vpack(vlist).box
    first = strut.applied_to(lines[0]).height
    below = stacked.height - first
    return replace(stacked, width=width, height=first, depth=below + stacked.depth), below


def _cell_params(align: ColumnAlign, params: LineBreakParams) -> LineBreakParams:
    r"""
    The breaking parameters for a wrapped cell in a column of this alignment.
    """
    first_fit = replace(params, first_fit=True)
    match align:
        case ColumnAlign.LEFT:
            return replace(first_fit, left_skip=GlueSpec(), right_skip=RAGGED_RIGHT)
        case ColumnAlign.RIGHT:
            return replace(
                first_fit,
                left_skip=RAGGED_RIGHT,
                right_skip=GlueSpec(),
                par_fill_skip=GlueSpec(),
            )
        case ColumnAlign.CENTER:
            return replace(
                first_fit,
                left_skip=RAGGED_RIGHT,
                right_skip=RAGGED_RIGHT,
                par_fill_skip=GlueSpec(),
            )


def _aligned(material: tuple[Node, ...], align: ColumnAlign) -> list[Node]:
    """
    A cell's material with the `\\hss` that places it in its column.

    Three alignments, no alignment enumeration: each one is where the infinitely
    stretchable glue goes. That is `advtext.blocklayout`'s whole argument, applied
    to the one place in this document that needs it.
    """
    match align:
        case ColumnAlign.LEFT:
            return [*material, Glue(HSS)]
        case ColumnAlign.RIGHT:
            return [Glue(HSS), *material]
        case ColumnAlign.CENTER:
            return [Glue(HSS), *material, Glue(HSS)]

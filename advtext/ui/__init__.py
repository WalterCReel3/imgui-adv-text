r"""
The UI package, and the one piece of it that does not touch ImGui.

`compose` turns a parsed markdown `Document` into a single packed vertical box:
it breaks every paragraph, hangs every list marker, sizes every table column and
stacks the lot with interline glue. That is the last step of the pipeline before
ship-out, and **it imports no ImGui**, which is why it lives in this
`__init__.py` rather than in `document_view.py`. `scripts/render_litmus.py` has
to do exactly the same work to produce an SVG with no display attached, and two
implementations of "lay out a document" would drift.

The ImGui-dependent modules are `advtext.ui.document_view` and
`advtext.ui.app`. Importing this package does not import either, so a headless
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
  ragged; body text, list items and quotes are justified.
- **The hanging marker.** A list item is broken to `width - left_indent` with
  `ParShape`'s indent, and the first line is then re-packed with the marker in a
  box exactly `left_indent` wide, right-aligned against a `marker_gap`. That
  keeps the item's text aligned whatever the marker's width, which a fixed
  marker offset does not once the list reaches item 10.
- **Table column widths.** Every cell is packed at its natural size, the widest
  per column wins, and every cell is then re-packed to that width with its
  column's alignment. `advtext.markdown` deliberately stops before this because
  it is `hpack` arithmetic and doing it there would make the converter measure.

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
from advtext.units import DEFAULT_PX_PER_INCH, UNITY, GlueOrder, Scaled, sp_from_px

__all__ = [
    "HSS",
    "PROSE_BREAKING",
    "PROSE_BREAKING_BOUNDED",
    "RAGGED_RIGHT",
    "CacheStats",
    "CommandIndex",
    "LayoutCache",
    "Viewport",
    "compose",
    "compose_blocks",
    "visible_rects",
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
class Viewport:
    """
    The band of a document that is on screen, in **document** scaled points.

    Document coordinates and not screen ones: everything below `compose` works in
    the document's own space, where zero is the top of the first line and y grows
    downward, and converting once at the edge is what keeps the culling arithmetic
    testable with no window anywhere near it.

    Half-open, `[top, bottom)`, like every other range in this project.
    """

    top: Scaled
    bottom: Scaled

    @classmethod
    def of_pixels(
        cls,
        top_px: float,
        height_px: float,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        overscan_px: float = 0.0,
    ) -> Viewport:
        """
        A viewport from a scroll offset and a visible height, both in pixels.

        `overscan_px` widens the band at both ends. Zero is correct for a static
        frame -- `CommandIndex` bounds a glyph by its line box, and `hpack` takes
        the line's height as a maximum over its contents' *ink*, so nothing a line
        contains can extend past the extent the index gives it. It exists for a
        caller that wants material ready before a scroll reaches it, which is a
        different question from correctness and is the caller's to answer.
        """
        return cls(
            top=sp_from_px(top_px - overscan_px, px_per_inch),
            bottom=sp_from_px(top_px + height_px + overscan_px, px_per_inch),
        )

    def covers(self, top: Scaled, bottom: Scaled) -> bool:
        """
        Whether `[top, bottom)` overlaps this viewport at all.
        """
        return bottom > self.top and top < self.bottom


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


def _stacked(
    blocks: tuple[Block, ...],
    theme: Theme,
    width: Scaled,
    measure: CharMeasure,
    params: LineBreakParams,
    depth: int,
    memo: _Memo | None,
) -> list[Node]:
    """
    Stack blocks into a vertical list, barring each run quoted deeper than `depth`.

    `depth` is the quote nesting this call is *inside*, so the top-level call
    passes zero and every run of blocks at depth 1 or more becomes one barred
    box; `_barred` then calls back in at depth 1 and a doubly-quoted run inside
    it gets its own bar. That recursion is the whole of the nesting support and
    it is why the run-gathering takes a depth rather than asking "is this
    quoted".
    """
    vlist: list[Node] = []
    prev_depth: Scaled = IGNORE_DEPTH
    space_below: Scaled = 0

    for run in _runs(blocks, depth):
        style = run[0].style
        if vlist:
            gap = space_below + style.space_above
            if gap:
                vlist.append(Kern(width=gap))
            # A fresh rhythm: the kern is the gap, and interline glue on top of
            # it would add a second one.
            prev_depth = IGNORE_DEPTH
        boxes: tuple[Box, ...]
        if _quote_depth(run[0]) > depth:
            boxes = (_barred(run, theme, width, measure, params, depth + 1, memo),)
        else:
            boxes = _cached_block_boxes(run[0], theme, width, measure, params, memo)
        for box in boxes:
            prev_depth = append_to_vlist(vlist, box, prev_depth, style.interline)
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
    inner = vpack(_stacked(run, theme, width, measure, params, depth, memo)).box
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
            return tuple(_table_boxes(block, theme, width, measure))


def _skips(align: Align, params: LineBreakParams) -> LineBreakParams:
    r"""
    The `\leftskip`/`\rightskip` pair that produces one alignment (§886, §887).

    Justification is the *absence* of the trick: with no `\rightskip` the surplus
    has nowhere to go but the interword glue. Every other alignment is a
    placement of infinitely stretchable glue, which is why there is no alignment
    branch anywhere below this function.
    """
    match align:
        case Align.JUSTIFY:
            return replace(params, left_skip=GlueSpec(), right_skip=GlueSpec())
        case Align.LEFT:
            return replace(params, left_skip=GlueSpec(), right_skip=RAGGED_RIGHT)
        case Align.RIGHT:
            return replace(params, left_skip=RAGGED_RIGHT, right_skip=GlueSpec())
        case Align.CENTER:
            return replace(params, left_skip=RAGGED_RIGHT, right_skip=RAGGED_RIGHT)


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
    """
    Break one text block into lines, hanging its marker on the first of them.
    """
    broken = break_paragraph(
        block.material,
        _shape(block, width),
        _skips(block.style.align, params),
        measure=measure,
    )
    lines = list(broken.boxes)
    if block.marker and lines:
        lines[0] = _hang_marker(lines[0], block.marker, block.left_indent, theme, measure)
    return lines


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


def _table_boxes(block: TableBlock, theme: Theme, width: Scaled, measure: CharMeasure) -> list[Box]:
    """
    Size a table's columns, then set every row to them.

    Natural widths first, widest per column wins, then every cell is re-packed to
    that width with its column's alignment. Two passes because a column's width
    is a property of the whole column and no cell can know it alone.

    **The columns are then scaled to the measure in both directions**, by
    `_apportioned`. Scaling only downward was the earlier behaviour and it left
    the table stopping short of the margin the prose beside it runs to, which
    reads as a table that failed to lay out rather than as a narrow one.

    Cells do not wrap -- breaking text inside a cell means running the breaker
    against a width that depends on the breaking, which is `\\halign`'s real
    problem and out of scope (`docs/decisions.md`). So **a column squeezed below
    its natural width still overfulls visibly**, and widening the table does not
    change that: it makes it rarer, because the squeeze now only happens when the
    whole table is wider than the measure rather than whenever one column is
    greedy. That case remains, and it is the one to reach for `\\halign` over.
    """
    rows = [block.header, *block.rows] if block.header else list(block.rows)
    if not rows:
        return []

    columns = max(len(row) for row in rows)
    padding = theme.cell_padding
    natural = [0] * columns
    for row in rows:
        for index, cell in enumerate(row):
            packed = hpack(cell.material, measure=measure).box
            natural[index] = max(natural[index], packed.width + 2 * padding)

    widths = _apportioned(natural, max(width - block.left_indent, UNITY))

    aligns = tuple(block.aligns) + (ColumnAlign.LEFT,) * (columns - len(block.aligns))
    strut = block.style.strut
    boxes: list[Box] = []
    for row in rows:
        # The strut goes on the row and not on each cell: a cell is a sub-box of
        # the row's hlist, so flooring the row floors every cell in it, and one
        # strut per row is what keeps a row of digits the same height as a row
        # with a descender in it.
        boxes.append(
            strut.applied_to(_table_row(row, widths, aligns, block.left_indent, padding, measure))
        )
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

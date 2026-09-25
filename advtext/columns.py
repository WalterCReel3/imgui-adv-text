r"""
`\vsplit`: cutting one composed vertical list into newspaper columns.

`advtext.ui.compose` produces a single vertical box for a whole document, and
that is the right shape for a continuous scroll. Newspaper setting wants the
opposite: the same material cut into N pieces of a fixed height, read foot of
one column to head of the next. This module is the cut, and nothing else -- it
takes a vertical list, returns N boxes, and never asks where on a screen they
go.

**The algorithm is TeX's, not a height accumulator.** §970-§976 is `vert_break`,
the cost function that chooses *where* to cut; §968-§969 is `prune_page_top`,
which cleans the head of the fragment that is left; §977 is `vsplit`, which is
the two of them plus a `vpackage`. `docs/tex-notes.md` §6.2-§6.4 transcribes all
three and this module implements them as transcribed.

Three things a hand-rolled splitter gets wrong, and they are the reason this is
not thirty lines:

- **The glue at the head of column 2 has to go.** Cut a vertical list between
  two lines and the interline glue that separated them is now the first thing in
  the next column. Every column but the first then starts one `\baselineskip`
  lower than it should, and because the gap varies with the height of whichever
  line happened to land there, the columns do not even start at a *consistently*
  wrong place. `prune_top` is §969's answer: discard every glue, kern and
  penalty before the first box, then insert `\splittopskip` glue sized
  `\splittopskip - height(first box)`, floored at zero. That puts the first
  baseline of every column exactly `\splittopskip` from its top, which is the
  property `tests/test_columns.py` asserts by comparing columns rather than by
  comparing one column against a number.

- **A breakpoint in a vertical list is not a breakpoint in a horizontal one.**
  §973's glue rule is `precedes_break(prev_p)` and nothing else, where §868's --
  the rule `advtext.nodes.permits_break_at_following_glue` implements -- also
  admits a non-explicit kern before the glue. Worse, the two differ in the
  opposite direction on kerns themselves: in a vlist **every** kern followed by
  glue is a legal break, explicit or not, where in an hlist only an explicit one
  is. Reusing the horizontal predicate here is wrong twice over, so this module
  spells §973 out.

- **A penalty is a real instruction.** `EJECT_PENALTY` forces the cut where it
  sits and `INF_PENALTY` forbids one. A splitter that only counts heights
  silently ignores both. Nothing in `advtext.ui` emits vertical penalties today,
  so this costs nothing at present and is the difference between implementing
  §974 and approximating it.

**Balance: not done, and here is the price.** Columns are filled in order --
each one takes as much as `vert_break` says fits, and the last one is as short
as it turns out to be. TeX's `\balance` is not a separate algorithm but the same
cost function run against a *searched* column height: bisect on the height until
the shortest column is within tolerance of the tallest, which is `count`
`vert_break` scans per probe and roughly ten probes, so an order of magnitude
more work than one unbalanced split. **Measured, so that the next person does
not have to guess whether that is affordable:** a three-way split of
`demo/sample.md`'s 193 composed nodes at a 262 pt measure costs **0.53 ms**,
best of five, against **277 ms** to compose the same document at that measure in
the same process. Balance would therefore cost a few milliseconds on a path that
already costs a quarter of a second, and it was left out for scope, not for
cost. The visible consequence is a short final column, which is what a newspaper
page looks like anyway.

**Nothing here stretches, and that is a property of the material rather than of
this module.** `advtext.style` builds interline glue and block spacing rigid
(`_leading`, and "Block spacing does not stretch" in its docstring), so a
composed document contains no vertical stretch at all. §977 packs each column
`exactly` to the column height, and with no stretch available a short column
simply sits at the top of its measure with `GlueSign.NORMAL` -- it is not spread
out. A caller who supplies stretchable vertical material *will* see it
stretched, because that is what `exactly` means.

**What the material gives this module to work with, which is less than it looks
like.** A splitter can only cut where a breakpoint is legal, and a composed
document supplies fewer of those than it has lines:

- **A block boundary is not a breakpoint.** `advtext.ui._stacked` puts
  `Kern(width=gap)` between two block runs and then sets
  `prev_depth = IGNORE_DEPTH`, so no interline glue follows it. The sequence is
  `Box, Kern, Box`, and §973 admits a kern only when *glue* follows it. So every
  run of consecutive one-line blocks -- a list of short items, a heading and the
  line under it -- is one indivisible atom.
- **A block quote is one box however long it is.** `_barred` returns a single
  `hpack`, so a quote cannot be divided and a quote taller than the column will
  overflow it.
- **There are no vertical penalties at all**, so there is no widow or orphan
  control for §974 to consume. The clause is implemented and the material never
  exercises it.

**Measured rather than feared**, because the first three of those read like a
crisis and are not one. On `demo/sample.md` at a 262 pt measure: 193 nodes, 97
boxes and rules, 22 kerns, and **74 legal breakpoints** -- exactly 96 minus the
22 kerns, which confirms the mechanism. The longest unbreakable span is
**195.9 pt, 37% of a 527 pt column**, and three columns come out filled to 524,
513 and 520 pt of 527. So atomicity costs this document **under 3% of a column**,
and it would start to hurt at a column height near the 196 pt atom rather than at
this one.

If it ever does hurt, the fix is one line and it is **not in this file**:
`_stacked` emitting `Glue(GlueSpec(width=gap))` instead of `Kern(width=gap)`
would make every block boundary legal, taking the sample from 74 breakpoints to
96. `advtext.style` justifies the rigid choice on the grounds that "page breaking
is out of scope... so stretch on block spacing would be a parameter with no
reader", and this module is that reader, so the justification has expired. It was
left alone because substituting it changed the split of this document **not at
all** -- same three fills, same overflow -- and a change with no measured effect
is not worth the churn.

Deliberately absent:

- **Marks.** §977 tracks `split_first_mark` and `split_bot_mark` across the cut.
  `advtext.nodes` has no `Mark` node (its docstring says why), so there is
  nothing to track.
- **Inserts and the page builder** (§980-§1007). `\vsplit` is the whole of what
  a column needs; the page builder additionally schedules output routines and
  floats, and neither exists here.
- **Column rules and gutters.** Where the columns are placed, and what is drawn
  between them, is the caller's -- this module returns boxes with no notion of a
  horizontal position. `advtext.blocklayout.Row` already composes boxes
  side by side and is the natural consumer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final, assert_never

from advtext.badness import INF_BAD, badness
from advtext.linebreak import LineBreakParams
from advtext.markdown import Block
from advtext.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    CharNode,
    Disc,
    Glue,
    GlueSpec,
    GlueTotal,
    Kern,
    MathOff,
    MathOn,
    Node,
    Penalty,
    Rule,
    is_discardable,
)
from advtext.pack import CharMeasure, PackMode, PackResult, vpack
from advtext.style import Theme
from advtext.ui import LayoutCache, compose_blocks
from advtext.units import MAX_DIMEN, RUNNING, UNITY, GlueOrder, Scaled

__all__ = [
    "AWFUL_BAD",
    "DEPLORABLE",
    "SPLIT_TOP_SKIP",
    "ColumnSplit",
    "compose_into_columns",
    "prune_top",
    "split_into_columns",
    "vert_break",
    "vsplit",
]

AWFUL_BAD: Final = (1 << 30) - 1
r"""
The cost of a break that cannot be taken at all. TeX's `@d awful_bad == @'7777777777`.

Numerically equal to `advtext.units.MAX_DIMEN`, and the two are **not** the same
constant: one is the largest representable length and this is a sentinel cost
chosen to exceed every real one. They are kept apart because a cost is compared
against `DEPLORABLE` and `INF_BAD` and a length is not.
"""

DEPLORABLE: Final = 100_000
r"""
The cost §974 gives a break whose badness is already infinite. `@d deplorable == 100000`.

"More than `inf_bad`, but less than `awful_bad`" -- so a break that is merely
hopeless still beats one that is impossible, and a list with no good break in it
still gets cut somewhere rather than running off the bottom.
"""

SPLIT_TOP_SKIP: Final = GlueSpec(width=10 * UNITY)
r"""
`\splittopskip`: how far the first baseline of a column sits from its top.

10 pt, which is `plain.tex`'s value. Rigid on purpose -- §969 overwrites the
width and keeps everything else, so stretch here would let the first baseline of
a stretched column drift, and the whole point of the parameter is that it does
not.
"""


def _precedes_break(node: Node) -> bool:
    """
    §148's `precedes_break`: whether a glue node immediately after `node` may be cut at.

    §973's glue arm is `if precedes_break(prev_p) then pi:=0`, and §148 defines
    `precedes_break(p) == (type(p) < math_node)`. Over this project's node
    vocabulary that partition is exactly the complement of
    `advtext.nodes.is_discardable`, so this is one call and a citation rather
    than a second hard-coded tuple that could drift from the first.

    Not `advtext.nodes.permits_break_at_following_glue`. That is §868, the
    *horizontal* rule, and it has a third branch admitting a non-explicit kern
    before the glue which §973 does not have. The module docstring has the rest.
    """
    return not is_discardable(node)


def _break_badness(cur_height: Scaled, goal: Scaled, stretch: GlueTotal, shrink: Scaled) -> int:
    """
    §975: how bad it is to end a column here.

    Any nonzero *infinite* stretch makes an underfull column cost nothing at all
    -- `active_height[3..5] <> 0` in the source -- because infinite glue always
    reaches the target exactly. Overfull past the available shrink is
    `AWFUL_BAD`, which §974 reads as "stop scanning".
    """
    if cur_height < goal:
        if stretch.dominant_order is not GlueOrder.NORMAL:
            return 0
        return badness(goal - cur_height, stretch[GlueOrder.NORMAL])
    if cur_height - goal > shrink:
        return AWFUL_BAD
    return badness(cur_height - goal, shrink)


def vert_break(nodes: Sequence[Node], goal: Scaled, max_depth: Scaled = MAX_DIMEN) -> int:
    """
    The index in `nodes` at which to cut for a column of height `goal` (§970-§976).

    `len(nodes)` means "take the whole list": either it fits, or no legal
    breakpoint exists anywhere in it.

    `max_depth` is `\\splitmaxdepth`. Depth beyond it is added to the running
    height during the scan (§972's `not_found` clamp), so a column whose last
    line has a deep descender is measured the way `vpack` will pack it.

    **Ties go to the later breakpoint.** §974's test is `b <= least_cost`, not
    `<`, and the `<=` is doing real work here. A composed document from
    `advtext.ui` has no vertical stretch at all, so every underfull break scores
    the same `DEPLORABLE`; under `<` the first one would win and every column
    would hold one line. Under `<=` the last one wins, which is the fullest
    column that still fits.

    Raises on a node that cannot appear in a proper vertical list -- §973's
    `confusion("vertbreak")`.
    """
    least_cost = AWFUL_BAD
    best_place = len(nodes)
    cur_height: Scaled = 0
    prev_dp: Scaled = 0
    stretch = GlueTotal()
    shrink: Scaled = 0

    for index in range(len(nodes) + 1):
        # `None` is §973's `goto not_found` / `goto update_heights`: this node is
        # not a legal breakpoint, so §974 is skipped for it.
        penalty_here: int | None = None
        node: Node | None = None

        if index == len(nodes):
            # §972: "if p = null then pi := eject_penalty". The end of the list
            # is always a forced break, which is what makes the scan terminate.
            penalty_here = EJECT_PENALTY
        else:
            node = nodes[index]
            match node:
                case Box():
                    cur_height += prev_dp + node.height
                    prev_dp = node.depth
                case Rule():
                    if node.height == RUNNING or node.depth == RUNNING:
                        raise ValueError(
                            "a rule's height and depth are never running inside a vlist "
                            "(tex.web §138); resolve them before splitting"
                        )
                    cur_height += prev_dp + node.height
                    prev_dp = node.depth
                case Glue():
                    # §970: "an initial glue node is not a legal breakpoint" --
                    # the source arranges it by initialising `prev_p := p`, so
                    # the first node is tested against itself and glue is not
                    # `precedes_break`. Index zero is the same statement.
                    if index > 0 and _precedes_break(nodes[index - 1]):
                        penalty_here = 0
                case Kern():
                    # §973: any kern, explicit or not, provided glue follows. A
                    # kern at the very end counts as followed by a penalty node,
                    # i.e. not a breakpoint.
                    following = nodes[index + 1] if index + 1 < len(nodes) else None
                    if isinstance(following, Glue):
                        penalty_here = 0
                case Penalty():
                    penalty_here = node.value
                case CharNode() | Disc() | MathOn() | MathOff():
                    raise ValueError(
                        f"{type(node).__name__} cannot appear in a vertical list being split "
                        '(tex.web §973 calls this confusion("vertbreak"))'
                    )
                case _ as unreachable:
                    assert_never(unreachable)

        if penalty_here is not None and penalty_here < INF_PENALTY:
            cost = _break_badness(cur_height, goal, stretch, shrink)
            if cost < AWFUL_BAD:
                if penalty_here <= EJECT_PENALTY:
                    cost = penalty_here
                elif cost < INF_BAD:
                    cost = cost + penalty_here
                else:
                    cost = DEPLORABLE
            if cost <= least_cost:
                best_place = index
                least_cost = cost
            if cost == AWFUL_BAD or penalty_here <= EJECT_PENALTY:
                return best_place

        # §976. Reached from both glue arms -- the legal one falls through §974
        # and the illegal one jumps straight here.
        if isinstance(node, Glue):
            spec = node.spec
            stretch = stretch + GlueTotal.of(spec.stretch, spec.stretch_order)
            # §976 reports infinite shrink in a box being split as an error and
            # continues with the order forced to `normal`. There is no terminal
            # here, so it is coerced silently and the citation is the record.
            shrink += spec.shrink
            cur_height += prev_dp + spec.width
            prev_dp = 0
        elif isinstance(node, Kern):
            cur_height += prev_dp + node.width
            prev_dp = 0

        # §972's `not_found`: "the maximum depth d might be negative, so
        # cur_height and prev_dp might need to be corrected even after a glue or
        # kern node."
        if prev_dp > max_depth:
            cur_height += prev_dp - max_depth
            prev_dp = max_depth

    return best_place  # pragma: no cover - the p=null arm above always returns


def prune_top(nodes: Sequence[Node], split_top_skip: GlueSpec = SPLIT_TOP_SKIP) -> list[Node]:
    """
    The head of a fragment, cleaned for the top of a column (§968, §969).

    Every glue, kern and penalty before the first box or rule is discarded, and
    `\\splittopskip` glue is inserted in their place with its width reduced by
    the height of that first box and floored at zero. The result is that the
    first baseline sits `max(\\splittopskip, height of first line)` below the top
    of the column -- the same distance in every column, which is the whole
    reason the routine exists.

    An empty list, or one holding nothing but discardables, prunes to nothing.
    """
    for index, node in enumerate(nodes):
        match node:
            case Box() | Rule():
                if isinstance(node, Rule) and node.height == RUNNING:
                    raise ValueError(
                        "a rule's height is never running inside a vlist (tex.web §138); "
                        "resolve it before splitting"
                    )
                gap = max(0, split_top_skip.width - node.height)
                return [Glue(replace(split_top_skip, width=gap)), *nodes[index:]]
            case Glue() | Kern() | Penalty():
                continue
            case CharNode() | Disc() | MathOn() | MathOff():
                raise ValueError(
                    f"{type(node).__name__} cannot appear at the head of a split-off vertical "
                    'list (tex.web §968 calls this confusion("pruning"))'
                )
            case _ as unreachable:
                assert_never(unreachable)
    return []


def vsplit(
    nodes: Sequence[Node],
    height: Scaled,
    *,
    split_top_skip: GlueSpec = SPLIT_TOP_SKIP,
    split_max_depth: Scaled = MAX_DIMEN,
) -> tuple[PackResult, list[Node]]:
    """
    One column off the front of `nodes`, and what is left (§977).

    The column is packed `exactly` to `height` -- §977's
    `vpackage(p, h, exactly, split_max_depth)` -- so every column is the same
    size whatever it holds. The remainder comes back pruned by `prune_top` and
    is ready to be the head of the next column or to be `vsplit` again.

    The `PackResult` rather than the bare box, because a column that did not fit
    is a real outcome a caller may want to report: `fitness` is `OVERFULL` and
    `overfull_by` says by how much. That happens when no legal breakpoint exists
    early enough -- a single unbreakable box taller than the column, for
    instance -- and it is information, not a failure.
    """
    place = vert_break(nodes, height, split_max_depth)
    column = vpack(nodes[:place], height, PackMode.EXACTLY, max_depth=split_max_depth)
    return column, prune_top(nodes[place:], split_top_skip)


@dataclass(frozen=True, slots=True)
class ColumnSplit:
    """
    What `split_into_columns` produced: the columns, and anything that did not fit.

    `results` rather than bare boxes because `PackResult.fitness` is how a caller
    finds out that a column overflowed, and `overflow` rather than silently
    truncating because "the document is longer than the page" is the caller's
    decision to make -- a demo might shrink the type, a printer might add a page.
    """

    results: tuple[PackResult, ...]
    overflow: tuple[Node, ...]

    @property
    def columns(self) -> tuple[Box, ...]:
        """
        The packed column boxes, left to right.
        """
        return tuple(result.box for result in self.results)

    @property
    def fits(self) -> bool:
        """
        Whether the whole document landed in the columns it was given.
        """
        return not self.overflow


def split_into_columns(
    nodes: Sequence[Node],
    *,
    height: Scaled,
    count: int,
    split_top_skip: GlueSpec = SPLIT_TOP_SKIP,
    split_max_depth: Scaled = MAX_DIMEN,
) -> ColumnSplit:
    """
    Flow one vertical list into `count` columns of `height`, in reading order.

    Repeated `vsplit`. Column *k* holds the material that follows column *k-1*'s
    last line, which is what makes the text continue from the foot of one column
    to the head of the next; `tests/test_columns.py` pins that as conservation
    -- concatenate the columns' boxes and you get the single-column sequence,
    with nothing dropped and nothing repeated.

    Columns past the end of the material come back empty and packed to `height`,
    so `len(result.columns)` is always `count` and a caller laying out a row does
    not have to special-case a document that ran out early.

    **The first column's head is pruned too**, which `vsplit` on its own does not
    do and §977 does not ask for. This is §1001's `\\topskip`, the page builder's
    mirror of `prune_page_top` -- the same computation, applied because the top
    of a *page* needs the treatment the top of a *fragment* gets. It is a no-op
    on material from `advtext.ui.compose_blocks`, which begins with a box; it
    earns its place the moment a caller hands over a fragment that begins with
    glue, where without it column one alone would start with a stray gap. TeX
    keeps `\\topskip` and `\\splittopskip` as two parameters and they are
    collapsed to one here, because every column in this routine is a column of
    the same document and two numbers that have to agree are worse than one.

    **What `\\splittopskip` levels is the top of the ink, not the baseline**, and
    the difference is worth being clear about because the baseline is the number
    a reader of this code will measure. §969 makes the head glue
    `max(0, split_top_skip - height of the first line)`, so the first baseline
    lands at `max(split_top_skip, that height)` and the *top* of that line lands
    at `max(0, split_top_skip - that height)`. With a `\\splittopskip` smaller
    than every line -- the 10 pt `plain.tex` default is smaller than this
    project's 12.2 pt body line -- every column's first line is flush with the
    top of its column and the baselines differ by exactly as much as the lines
    do. Measured on `demo/sample.md` at a 340 px measure over four columns: tops
    all at 0.00 pt, baselines 20.29, 12.20, 12.20, 12.20, because column one
    starts on a heading. That is TeX's intended behaviour and it is the one that
    looks right; a reviewer comparing *baselines* across columns and finding them
    unequal has found the heading, not a defect.

    The loop cannot spin: `vert_break` only ever returns zero at a node that is
    itself discardable -- glue at index zero is excluded by §970, and a box is
    never a breakpoint -- and `prune_top` removes every leading discardable, so
    a column that consumed nothing still shortens the remainder.
    """
    if count < 1:
        raise ValueError(f"a column count must be at least 1, got {count}")
    if height <= 0:
        raise ValueError(f"a column height must be positive, got {height}")

    results: list[PackResult] = []
    rest: Sequence[Node] = prune_top(nodes, split_top_skip)
    for _ in range(count):
        column, rest = vsplit(
            rest, height, split_top_skip=split_top_skip, split_max_depth=split_max_depth
        )
        results.append(column)
    return ColumnSplit(tuple(results), tuple(rest))


def compose_into_columns(
    blocks: tuple[Block, ...],
    theme: Theme,
    measure: CharMeasure,
    *,
    column_width: Scaled,
    column_height: Scaled,
    count: int,
    params: LineBreakParams | None = None,
    cache: LayoutCache | None = None,
    split_top_skip: GlueSpec = SPLIT_TOP_SKIP,
    split_max_depth: Scaled = MAX_DIMEN,
) -> ColumnSplit:
    """
    Compose `blocks` at `column_width` and flow the result into `count` columns.

    The convenience that joins the two halves. `advtext.ui.compose_blocks`
    already returns the vertical list as `Box.contents` -- `vpack` stores the
    nodes it was handed, unmodified -- so no new seam into `advtext.ui` was
    needed to get at the pre-packed material, and none was cut.

    **`column_width` is the width of one column, not of the page.** A caller
    with a page width and a gutter subtracts the gutters and divides; doing it
    here would mean this module owning a gutter it does not draw.

    Composition is the expensive half -- `docs/status.md` section 4 measures
    82.9 ms for `demo/sample.md` -- and it depends on `column_width` and not on
    `count`. A caller changing only the column count over a fixed page therefore
    *does* pay it again, because narrowing the page into more columns changes the
    measure and `LayoutCache` correctly misses on every text block at a new
    width. Pass a `cache` anyway: it earns its place when the count returns to
    one already seen.
    """
    material = compose_blocks(blocks, theme, column_width, measure, params, cache=cache).contents
    return split_into_columns(
        material,
        height=column_height,
        count=count,
        split_top_skip=split_top_skip,
        split_max_depth=split_max_depth,
    )

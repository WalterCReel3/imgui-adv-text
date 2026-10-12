r"""
`hpack` and `vpack`: measuring a list into a box, and setting its glue.

This is the middle of the system. Above it there is only vocabulary; below it
there is only drawing. `hpack` walks a horizontal list, adds up natural widths,
takes the maximum height and depth, and works out how far the glue has to
stretch or shrink to reach a target. `vpack` does the same down the page.
`interline_glue` is §679, the rule that makes stacked boxes look like set prose.

**The glue setting lives on the box, not in the glue.** `hpack` records three
things -- `glue_set`, `glue_sign`, `glue_order` -- and leaves every `Glue` node
in the list holding its original, unmodified spec. Ship-out multiplies the two
back together. That separation is what lets one node list be packed to two
different widths without being copied, and it is why a `Box` can be immutable
and still describe a setting: the setting is a property of *this packing*, not
of the glue. A design that wrote resolved widths into the glue nodes would have
to deep-copy the list per column and would make the second packing depend on
whether the first had happened.

**The order hierarchy decides everything.** If any `fil` stretch is present,
finite stretch contributes nothing at all -- not proportionally less, nothing
(§646, §658). The cascade picks the highest order with a nonzero total and
divides only by that.

That rule is applied **once, after the whole list has been walked**, and it must
not be applied while accumulating. Folding each glue node into the highest order
seen so far loses information: §646's own example -- 3pt, 8fill, 5fil, 6pt,
-3fil, -8fill, which comes to "essentially 2fil" -- collapses to nothing at all
if the `fil` term is discarded the moment a `fill` term appears, because the
`fill` terms then cancel and take the answer with them. `imscribe.nodes.GlueTotal`
keeps the four orders apart for exactly this reason, and `_set_glue` asks
`dominant_order` at the end and nowhere else.

**Diagnostics come back with the box.** TeX sets a global `last_badness` and
prints to a terminal (§660, §666). There is no terminal here and a global would
be shared mutable state across two backends and a test suite, so `hpack` returns
a `PackResult` carrying the box, the badness, the fitness and the overflow. The
box is `result.box`; nothing else changed.

**Fonts are injected, not imported.** A `CharNode` names a face and a codepoint
and carries no metrics, so packing a list containing characters needs a way to
measure them. That arrives as a `CharMeasure` callable rather than as an import
of `imscribe.fontmetrics`, which keeps this module free of any knowledge that
fonts have files, sizes or tables -- and keeps it testable with round numbers. A
list of boxes, glue and kerns needs no measure at all and packing one without
supplying it is normal. pptmstr injects measurement into layout the same way
(`pptmstr/ui/span_layout.py`); the difference is that here layout does not know
what is on the other end of the callable.

Deliberately out of scope:

- **Kerning and ligature building.** TeX inserts kern nodes into the list
  *before* `hpack` ever sees it; `hpack` only adds up what is there. Whichever
  task turns text into nodes owns that, and it is the right place for it --
  a kern is a node the line breaker has to be able to see.
- **`\hbadness`, `\vbadness`, `\hfuzz`, `\vfuzz` and `\overfullrule`.** Those
  gate *reporting* (§660, §666), and `PackResult` reports unconditionally and
  lets the caller decide. `\vbadness` in particular does not enter any cost
  function -- see `docs/decisions.md`.
- **`\vadjust`, inserts and marks**, which `hpack` moves to an adjustment list
  (§655). No page breaking here, so there is nothing to adjust into.
- **Leaders.** A glue subtype we do not use; it is the one place `hpack` looks
  at a glue node's height.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Final, TypeAlias, assert_never

from imscribe.badness import badness
from imscribe.nodes import (
    Box,
    BoxKind,
    CharNode,
    Disc,
    Glue,
    GlueSign,
    GlueSpec,
    GlueTotal,
    Kern,
    MathOff,
    MathOn,
    Node,
    Penalty,
    Rule,
)
from imscribe.units import MAX_DIMEN, RUNNING, GlueOrder, Scaled

__all__ = [
    "IGNORE_DEPTH",
    "OVERFULL_BADNESS",
    "CharDimens",
    "CharMeasure",
    "InterlineSkip",
    "PackFitness",
    "PackMode",
    "PackResult",
    "append_to_vlist",
    "hpack",
    "interline_glue",
    "vpack",
]

OVERFULL_BADNESS: Final = 1_000_000
"""
The badness TeX assigns an overfull box (§666): `last_badness := 1000000`.

Not a badness in the §108 sense -- that function never exceeds 10000 -- but a
sentinel chosen to dominate every real one. It means "the box does not fit and
the overflow was not distributed", and the length it overflowed by is in
`PackResult.overfull_by`.
"""

IGNORE_DEPTH: Final = -65_536_000
"""
The `prev_depth` that suppresses interline glue. TeX's `@d ignore_depth` (§212).

Exactly -1000 pt (65536000 / 65536 = 1000), and used as a sentinel rather than
as a length: a vertical list starts at this value so that the first box in it
gets no leading glue above it. Any real depth is greater, so the test in §679 is
a plain comparison rather than an optional.
"""


class PackMode(enum.Enum):
    """
    Whether the target is the final size or an amount added to the natural one.

    TeX's `@d exactly=0` and `@d additional=1` (§644). Its `natural` is not a
    third mode -- it is `additional` with a target of zero, which is why that is
    the default here and `hpack(nodes)` packs at natural size.
    """

    EXACTLY = enum.auto()
    ADDITIONAL = enum.auto()


class PackFitness(enum.Enum):
    r"""
    How well the contents met the target, in TeX's own categories.

    The four middle members are the words `hpack` prints (§660, §666, §667).
    The thresholds are not arbitrary: badness is exactly 100 when the whole of
    the available stretch is used (`imscribe.badness`), so `UNDERFULL` means
    "stretched past what the glue offered" and `LOOSE` means "stretched, but
    within it".

    `INFINITE_GLUE` and `EMPTY` exist because TeX declines to judge those two
    cases at all, and that silence is deliberate rather than an oversight. Glue
    set at an infinite order always reaches the target exactly, so there is no
    badness to compute; and `\hbox to 1in{}` is a spacer somebody wrote on
    purpose, which is why every diagnostic in §660-§667 is guarded by
    `list_ptr(r) <> null`.
    """

    EXACT = enum.auto()
    LOOSE = enum.auto()
    UNDERFULL = enum.auto()
    TIGHT = enum.auto()
    OVERFULL = enum.auto()
    INFINITE_GLUE = enum.auto()
    EMPTY = enum.auto()


@dataclass(frozen=True, slots=True)
class CharDimens:
    """
    What packing needs to know about one glyph: its advance, and its ink extents.

    `height` and `depth` are measured from the baseline, upward and downward
    respectively, like everything else in this project.
    """

    width: Scaled
    height: Scaled = 0
    depth: Scaled = 0


CharMeasure: TypeAlias = Callable[[CharNode], CharDimens]
"""
How a caller tells `hpack` how wide a character is.

A bare callable rather than a Protocol because there is exactly one operation.
The adapter over `imscribe.fontmetrics` belongs to whichever task builds node
lists out of text -- it is the layer that knows what size a face was asked for,
and therefore the layer that owns the one rounding from the metrics layer's
floats into scaled points.
"""


@dataclass(frozen=True, slots=True)
class PackResult:
    """
    A packed box, and what packing it was like.

    `natural` is the size the contents came to on their own and `excess` is
    `target - natural`, TeX's `x` after §657's `x := w - x`: positive means the
    glue had to stretch, negative that it had to shrink. Both are along the
    packing axis -- width for `hpack`, height for `vpack` -- which is why they
    are named for neither.

    `badness` is TeX's `last_badness`: 0 when there was nothing to make up or
    when no finite judgement applies, and `OVERFULL_BADNESS` when the box does
    not fit. `overfull_by` is the length §666 prints as "pt too wide", and is
    zero unless `fitness` is `OVERFULL`.
    """

    box: Box
    fitness: PackFitness
    natural: Scaled
    excess: Scaled
    badness: int = 0
    overfull_by: Scaled = 0


@dataclass(frozen=True, slots=True)
class InterlineSkip:
    """
    The three parameters §679 consults, gathered so they travel together.

    They are a unit because the rule is meaningless with only some of them, and
    because the markdown builder needs to vary them per block: a heading wants
    more leading than a paragraph, and passing three loose lengths around is how
    two of them end up from different blocks.
    """

    baselineskip: GlueSpec
    lineskip: GlueSpec
    lineskiplimit: Scaled = 0


def _accumulate_glue(
    spec: GlueSpec, stretch: GlueTotal, shrink: GlueTotal
) -> tuple[GlueTotal, GlueTotal]:
    """
    Add one glue spec's stretch and shrink into the running per-order totals (§656).
    """
    return (
        stretch + GlueTotal.of(spec.stretch, spec.stretch_order),
        shrink + GlueTotal.of(spec.shrink, spec.shrink_order),
    )


def _set_glue(
    natural: Scaled,
    target: Scaled,
    stretch: GlueTotal,
    shrink: GlueTotal,
    is_empty: bool,
) -> tuple[float, GlueSign, GlueOrder, PackFitness, int, Scaled]:
    """
    §657-§667: decide the glue ratio, sign and order, and judge the result.

    Shared verbatim between `hpack` and `vpack` because §672-§678 are §657-§667
    with `height` substituted for `width` -- the source says so and the two
    really are character-for-character the same apart from the parameter names.
    Keeping one copy is what stops them drifting apart, which is a defect that
    would show up only in vertical lists and only when they were stretched.
    """
    excess = target - natural

    if excess == 0:
        return 0.0, GlueSign.NORMAL, GlueOrder.NORMAL, PackFitness.EXACT, 0, 0

    if excess > 0:
        order = stretch.dominant_order
        available = stretch[order]
        if available == 0:
            # Only reachable at NORMAL order: the cascade picks an infinite
            # order only when its total is nonzero. Nothing to stretch, so the
            # contents simply do not fill the box (§659).
            sign, ratio = GlueSign.NORMAL, 0.0
        else:
            sign, ratio = GlueSign.STRETCHING, excess / available
        if is_empty:
            return ratio, sign, order, PackFitness.EMPTY, 0, 0
        if order is not GlueOrder.NORMAL:
            return ratio, sign, order, PackFitness.INFINITE_GLUE, 0, 0
        how_bad = badness(excess, stretch[GlueOrder.NORMAL])
        fitness = PackFitness.UNDERFULL if how_bad > 100 else PackFitness.LOOSE
        return ratio, sign, order, fitness, how_bad, 0

    wanted = -excess
    order = shrink.dominant_order
    available = shrink[order]
    if available == 0:
        sign, ratio = GlueSign.NORMAL, 0.0
    else:
        sign, ratio = GlueSign.SHRINKING, wanted / available

    if is_empty:
        return ratio, sign, order, PackFitness.EMPTY, 0, 0
    if order is not GlueOrder.NORMAL:
        return ratio, sign, order, PackFitness.INFINITE_GLUE, 0, 0

    if available < wanted:
        # §666: the overflow is not distributed. The glue shrinks as far as it
        # can and the box sticks out by the difference, which is the behaviour
        # the black overfull rule in a proof copy is marking.
        return (
            1.0,
            GlueSign.SHRINKING,
            order,
            PackFitness.OVERFULL,
            OVERFULL_BADNESS,
            wanted - available,
        )
    return ratio, sign, order, PackFitness.TIGHT, badness(wanted, available), 0


def hpack(
    nodes: Sequence[Node],
    target: Scaled = 0,
    mode: PackMode = PackMode.ADDITIONAL,
    *,
    measure: CharMeasure | None = None,
) -> PackResult:
    """
    Package a horizontal list into an hbox (§649-§667).

    Widths add along the list; heights and depths take the maximum, each
    measured from the baseline. A box shifted down by `s` contributes
    `height - s` and `depth + s` to its container (§653), which is the one place
    the sign convention is visible and is unambiguous: positive shifts down.

    `measure` is required only if the list contains a `CharNode`.
    """
    width: Scaled = 0
    height: Scaled = 0
    depth: Scaled = 0
    stretch = GlueTotal()
    shrink = GlueTotal()

    for node in nodes:
        match node:
            case CharNode():
                if measure is None:
                    raise ValueError(
                        "hpack was given a CharNode but no `measure`; a character has no "
                        "dimensions of its own, so packing one needs a way to look them up"
                    )
                dimens = measure(node)
                width += dimens.width
                height = max(height, dimens.height)
                depth = max(depth, dimens.depth)
            case Box():
                width += node.width
                shift = node.shift_amount
                height = max(height, node.height - shift)
                depth = max(depth, node.depth + shift)
            case Rule():
                if node.width == RUNNING:
                    raise ValueError(
                        "a rule's width is never running inside an hlist (tex.web §138); "
                        "resolve it before packing, or the box comes out 16384pt short"
                    )
                width += node.width
                # A running height or depth loses the maximum on its own, being
                # hugely negative, which is exactly how §653 handles it.
                height = max(height, node.height)
                depth = max(depth, node.depth)
            case Glue():
                width += node.spec.width
                stretch, shrink = _accumulate_glue(node.spec, stretch, shrink)
            case Kern() | MathOn() | MathOff():
                width += node.width
            case Penalty() | Disc():
                # §651: `othercases do_nothing`. A discretionary contributes
                # nothing; the nodes it would replace follow it in the list and
                # are measured in their own right.
                pass
            case _ as unreachable:
                assert_never(unreachable)

    final_width = target if mode is PackMode.EXACTLY else width + target
    ratio, sign, order, fitness, how_bad, over = _set_glue(
        width, final_width, stretch, shrink, not nodes
    )
    box = Box(
        kind=BoxKind.HLIST,
        contents=tuple(nodes),
        width=final_width,
        height=height,
        depth=depth,
        glue_set=ratio,
        glue_sign=sign,
        glue_order=order,
    )
    return PackResult(
        box=box,
        fitness=fitness,
        natural=width,
        excess=final_width - width,
        badness=how_bad,
        overfull_by=over,
    )


def vpack(
    nodes: Sequence[Node],
    target: Scaled = 0,
    mode: PackMode = PackMode.ADDITIONAL,
    *,
    max_depth: Scaled = MAX_DIMEN,
) -> PackResult:
    """
    Package a vertical list into a vbox (§668-§678).

    Heights and depths chain rather than taking a maximum: each box contributes
    the previous item's depth plus its own height, and the running depth is the
    last item's, which becomes the box's (§670). Widths take the maximum, with a
    box's `shift_amount` moving it right.

    `max_depth` is `vpackage`'s fourth parameter. Depth past it is **converted
    into height**, not discarded: the reference point moves down (§668). Plain
    `vpack` passes `max_dimen`, which is the default here.

    A `CharNode` in a vertical list is TeX's `confusion("vpack")` and a
    programming error rather than an input error, so it raises.
    """
    width: Scaled = 0
    height: Scaled = 0
    depth: Scaled = 0
    stretch = GlueTotal()
    shrink = GlueTotal()

    for node in nodes:
        match node:
            case CharNode():
                raise ValueError(
                    "a character cannot appear in a vertical list (tex.web §669 calls this "
                    'confusion("vpack")); pack it into an hbox first'
                )
            case Box():
                height += depth + node.height
                depth = node.depth
                width = max(width, node.width + node.shift_amount)
            case Rule():
                if node.height == RUNNING or node.depth == RUNNING:
                    raise ValueError(
                        "a rule's height and depth are never running inside a vlist "
                        "(tex.web §138); resolve them before packing"
                    )
                height += depth + node.height
                depth = node.depth
                # A running width loses the maximum on its own (§670).
                width = max(width, node.width)
            case Glue():
                height += depth + node.spec.width
                depth = 0
                stretch, shrink = _accumulate_glue(node.spec, stretch, shrink)
            case Kern():
                height += depth + node.width
                depth = 0
            case Penalty() | Disc() | MathOn() | MathOff():
                # §669: `othercases do_nothing`. These do not occur in a proper
                # vertical list, and where they do they occupy no space.
                pass
            case _ as unreachable:
                assert_never(unreachable)

    if depth > max_depth:
        height += depth - max_depth
        depth = max_depth

    final_height = target if mode is PackMode.EXACTLY else height + target
    ratio, sign, order, fitness, how_bad, over = _set_glue(
        height, final_height, stretch, shrink, not nodes
    )
    box = Box(
        kind=BoxKind.VLIST,
        contents=tuple(nodes),
        width=width,
        height=final_height,
        depth=depth,
        glue_set=ratio,
        glue_sign=sign,
        glue_order=order,
    )
    return PackResult(
        box=box,
        fitness=fitness,
        natural=height,
        excess=final_height - height,
        badness=how_bad,
        overfull_by=over,
    )


def interline_glue(prev_depth: Scaled, box: Box, skip: InterlineSkip) -> Glue | None:
    r"""
    The glue that goes above `box` in a vertical list, or `None` (§679).

    TeX aims for a constant *baseline-to-baseline* distance. The gap it needs is
    `\baselineskip` minus the previous box's depth minus this box's height, and
    that is the whole calculation. When the answer falls below `\lineskiplimit`
    -- which happens when a tall line follows a deep one, and can be negative,
    meaning the two would collide -- TeX gives up on constant baselines and uses
    `\lineskip` instead, which guarantees a minimum *visual* gap rather than a
    constant rhythm.

    Two details that are easy to get wrong and only show up as slightly wrong
    rhythm in a stretched vertical list:

    - The `\lineskip` branch uses the spec **as it is**, stretch and shrink
      included (`new_param_glue` shares the spec).
    - The `\baselineskip` branch is a **fresh copy with only the width
      replaced** (`new_skip_param`, then `width(temp_ptr) := d`). Its stretch
      and shrink survive. A version that built `GlueSpec(width=d)` from nothing
      would silently make every interline gap rigid, and vertical justification
      would then have nowhere to go.

    `None` means no glue at all: `prev_depth` is still `IGNORE_DEPTH`, so this
    is the first box in the list and nothing goes above it.
    """
    if prev_depth <= IGNORE_DEPTH:
        return None
    deficiency = skip.baselineskip.width - prev_depth - box.height
    if deficiency < skip.lineskiplimit:
        return Glue(skip.lineskip)
    return Glue(replace(skip.baselineskip, width=deficiency))


def append_to_vlist(
    vlist: list[Node], item: Box | Rule, prev_depth: Scaled, skip: InterlineSkip
) -> Scaled:
    r"""
    Append `item` to `vlist` with its interline glue, and return the new `prev_depth`.

    The imperative half of §679, kept separate from `interline_glue` so the rule
    can be tested without a list and used without one -- the markdown builder
    interleaves penalties between boxes and needs to drive the two steps itself.

    `prev_depth` is threaded through the return value rather than held in a
    module global as TeX holds it in `aux.sc`, because two vertical lists being
    built at once is normal here and a global would silently join them. Start a
    fresh list at `IGNORE_DEPTH` so the first box gets no glue above it.

    **A `Rule` suppresses interline glue on both sides of itself**, and that is
    why this takes a `Box | Rule` rather than a `Box`. A rule reaches a vertical
    list by `tail_append(scan_rule_spec)` rather than through this routine, so
    no glue goes above it, and the very same line sets
    `prev_depth := ignore_depth`, so none goes below it either. The source says
    why in as many words: "Note that baselineskip calculations are disabled
    after a rule in vertical mode."

    A document that wants space around a rule states it with explicit glue, and
    that is the right way round -- a thematic break is a deliberate
    interruption of the vertical rhythm rather than a participant in it. Leaving
    the two cases to the caller would mean every rule that anyone forgot about
    got a stray `\baselineskip`-derived gap underneath, with nothing raising and
    nothing looking wrong except the spacing.
    """
    if isinstance(item, Rule):
        vlist.append(item)
        return IGNORE_DEPTH
    glue = interline_glue(prev_depth, item, skip)
    if glue is not None:
        vlist.append(glue)
    vlist.append(item)
    return item.depth

r"""
UI block layout on TeX's box and glue machinery, as a demonstration rather than a toolkit.

**The claim.** Glue is a more expressive layout primitive than flexbox, and has
been since 1982. A glue spec carries a natural size, a stretch, a shrink **and an
order of infinity**, and the order is the part flexbox has no equivalent of. It
lets a layout say "absorb the surplus *here*, and if there is a higher-order
absorber anywhere in this row, take nothing at all" -- an absolute priority
between growers rather than a single proportional pool.

The second half of the claim is smaller and lands harder: **glue is an item in
the list rather than a property of the container.** CSS needs
`justify-content: flex-start | flex-end | center | space-between | space-around |
space-evenly` because the model cannot express space as a thing you put
somewhere. Here those six are six placements of the same primitive, and this
module implements them as six four-line functions over `spacer()` rather than as
a branch in the packer. That is the difference, and it is why `Row` has no
`align` field: an alignment enum here would be a worse spelling of a list.

**What this genuinely buys over flexbox**

- **Priority tiers.** `fil` beats finite absolutely and `fill` beats `fil`. There
  is no way to write that in flexbox; you reach for a second layout pass or a
  media query. `test_a_fil_spacer_takes_everything_and_the_finite_one_takes_nothing`
  is the demonstration.
- **Alignment is not an enumeration.** See above.
- **Baseline alignment by construction.** A row packs on a common baseline and
  has no other mode, which is the opposite of the usual framing: flexbox offers
  `align-items: baseline` as one option among five, and it is the *only* thing an
  hbox does. This is a real strength for text-bearing UI -- a label beside a
  button beside an icon line up on their baselines without anybody asking.
- **Shrink is a separate budget from stretch**, with its own order hierarchy, and
  a `Separator` (a kern) is rigid under compression where a `Gap` is not.

**What it does not buy, stated plainly because overselling a stretch goal is
worse than scoping it**

- **No percentage bases.** `width: 50%` is unexpressible. Proportional division
  works on *surplus* (`flex(1)` against `flex(2)`), not on the container.
- **No wrapping.** `flex-wrap` has no analogue. The paragraph line breaker next
  door does exactly this for text and nothing here reuses it for blocks.
- **No cross-axis alignment modes.** `align-items: center | stretch | flex-start
  | flex-end` do not exist; everything sits on the baseline. `Box.shift_amount`
  is the mechanism that would implement them and nothing here computes one.
- **No content-based sizing.** A `Leaf` is *given* its size. In a real toolkit a
  button's width comes from measuring its label, which means a measurement pass
  before packing. That pass is the single biggest missing piece.
- **No constraint propagation through a row.** A `Column` knows its children's
  width and passes it down; a `Row` does not know its children's widths, because
  its siblings consume them. So a nested `Row` is packed at its natural size
  unless it is given an explicit `width`. That asymmetry is not a shortcut -- it
  is true of the geometry, and flexbox resolves it only by running a second pass
  over resolved flex bases, which this deliberately does not do.

**Where this stops being honest to call a UI system.** It is a layout *model*.
There is no event routing, no focus, no hit testing of widgets, no invalidation,
no incremental relayout, no clipping or scrolling and no z-order. To make it real
you would need, roughly in order: a measurement pass so leaves can size
themselves from content; an identity on each leaf so a relayout can be diffed
against the previous one instead of rebuilt; dirty-marking so a changed leaf
repacks one row rather than the tree; and an input layer. `advtext.selection`
already shows that hit testing over shipped output is arithmetic, so the input
layer is the least of them.

**It reimplements nothing.** Every dimension here comes out of `advtext.pack`,
every coordinate out of `advtext.shipout`, and a `Leaf` is a `Rule` -- which is
apt rather than a trick, since a UI block *is* a filled rectangle. That means the
SVG backend renders a block layout with no code of its own, and it means a bug in
this module cannot be a bug in the geometry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeAlias, assert_never

from advtext.nodes import Box, Glue, GlueSpec, Kern, KernKind, Node, Rule
from advtext.pack import PackMode, PackResult, hpack, vpack
from advtext.shipout import ORIGIN, Point, RuleRect, ship
from advtext.units import GlueOrder, Scaled

__all__ = [
    "Block",
    "Column",
    "Gap",
    "Leaf",
    "Row",
    "Separator",
    "Spacer",
    "centre",
    "flex",
    "gap",
    "layout",
    "leaves",
    "left",
    "measure",
    "place",
    "right",
    "space_around",
    "space_between",
    "space_evenly",
    "spacer",
]


@dataclass(frozen=True, slots=True)
class Leaf:
    """
    A block of fixed size: a button, an icon, a label whose text has been measured.

    Becomes a `Rule`, which is what makes it visible to `advtext.shipout` and
    therefore to both backends without this module knowing either exists.

    `height` and `depth` are measured from the baseline like everything else in
    this project, and that is the mechanism behind the baseline alignment a row
    gets for free: a leaf with `depth=0` sits entirely above the line, and one
    standing in for a text label gives its descender as depth so that it lines up
    with its neighbours rather than with their bounding boxes.

    `name` is for the reader and for a test's error message. It is not an
    identity: nothing here diffs one layout against another, and giving it a
    field that looked like a key would suggest otherwise.
    """

    width: Scaled
    height: Scaled
    depth: Scaled = 0
    name: str = ""


@dataclass(frozen=True, slots=True)
class Spacer:
    """
    Space that absorbs surplus: `weight` units of stretch at `order`.

    Two idioms, and the difference between them is the whole argument:

    - `spacer()` is `fil` order. It takes the entire surplus and leaves nothing
      for any finite stretch in the same row, however large that finite stretch
      is. This is "push to the edge" and it is not expressible in flexbox.
    - `flex(n)` is finite order. Several of them split the surplus in proportion
      to their weights, which is `flex-grow: n`.

    Mixing them is the point rather than a mistake: a row with `flex(1)` padding
    and a `spacer()` gives the spacer everything, and the padding keeps its
    natural size exactly. §646's rule -- the highest order with a nonzero
    coefficient is used "as if no other orders were present" -- is doing that,
    and no special case anywhere implements it.

    A spacer has no shrink. It can grow a row but never rescue an overfull one,
    which is correct: an absorber of surplus is not a source of it.
    """

    weight: int = 1
    order: GlueOrder = GlueOrder.FIL


@dataclass(frozen=True, slots=True)
class Gap:
    """
    A fixed space that may be given stretch and shrink of its own.

    The everyday `gap` between two items. `shrink` is what lets a row survive
    being packed narrower than its contents: the gaps close first, down to
    `shrink`, and only then does the row go overfull. That is a minimum-size
    budget expressed as a length rather than as a `min-width` on a neighbour.
    """

    size: Scaled
    stretch: Scaled = 0
    shrink: Scaled = 0
    order: GlueOrder = GlueOrder.NORMAL


@dataclass(frozen=True, slots=True)
class Separator:
    """
    A rigid space: a kern, which never stretches and never shrinks.

    Distinguishable from `Gap(size)` only under compression, and that is exactly
    when you want it. Pack a row narrower than its contents and every `Gap` with
    shrink closes up while every `Separator` keeps its size, so the gutter you
    declared inviolable stays inviolable and the row goes overfull instead.

    It is also the right *word*. `Kern` in the source means "rigid space that is
    not a place to break", and the moment anything here wraps, that second half
    starts mattering too.
    """

    size: Scaled


@dataclass(frozen=True, slots=True)
class Row:
    """
    Children laid left to right on a common baseline, packed to `width`.

    `width` is the row's target. Left as `None` the row is packed at its natural
    size, which is what a nested row gets unless it is told otherwise -- see the
    module docstring on why a row cannot propagate a width to its children and a
    column can.

    There is deliberately **no alignment field**. `left`, `right`, `centre`,
    `space_between`, `space_around` and `space_evenly` are functions that put
    spacers into the child list, and they are in this module so that the
    mechanism is visible rather than hidden behind an enum.
    """

    children: tuple[Block, ...] = ()
    width: Scaled | None = None


@dataclass(frozen=True, slots=True)
class Column:
    """
    Children stacked top to bottom, packed to `height`.

    `width` is the width handed *down* to any child row that does not state one
    of its own. A column genuinely knows this and a row genuinely does not, which
    is why the propagation goes one way only.

    Note what `vpack` does that a naive stacker does not: each child contributes
    the previous child's depth plus its own height, so two leaves with descenders
    do not overlap and the column's own depth is the last child's. That is the
    same rule that gives paragraphs their vertical rhythm, applied to buttons.
    """

    children: tuple[Block, ...] = ()
    height: Scaled | None = None
    width: Scaled | None = None


Block: TypeAlias = Leaf | Spacer | Gap | Separator | Row | Column
"""
Anything that can be a child of a row or a column.
"""


# --------------------------------------------------------------------------
# Constructors, so a layout reads like layout
# --------------------------------------------------------------------------


def spacer(weight: int = 1, order: GlueOrder = GlueOrder.FIL) -> Spacer:
    """
    Infinite-order space: takes the whole surplus, beating any finite stretch.
    """
    return Spacer(weight=weight, order=order)


def flex(weight: int = 1) -> Spacer:
    """
    Finite-order space: `flex-grow`, splitting surplus in proportion to weights.
    """
    return Spacer(weight=weight, order=GlueOrder.NORMAL)


def gap(size: Scaled, *, stretch: Scaled = 0, shrink: Scaled = 0) -> Gap:
    """
    A fixed space, optionally able to give a little in either direction.
    """
    return Gap(size=size, stretch=stretch, shrink=shrink)


# --------------------------------------------------------------------------
# The six alignments, each a placement rather than a flag
# --------------------------------------------------------------------------


def left(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: flex-start` -- all the surplus after the last child.
    """
    return (*children, spacer())


def right(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: flex-end` -- all the surplus before the first child.
    """
    return (spacer(), *children)


def centre(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: center` -- equal spacers either side split the surplus evenly.

    It stays centred at every width because the two spacers have equal weight and
    therefore always receive equal shares, whatever the surplus turns out to be.
    Nothing recomputes a centre; the centre is a consequence.
    """
    return (spacer(), *children, spacer())


def space_between(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: space-between` -- a spacer in every gap and none at the ends.
    """
    items = tuple(children)
    if len(items) < 2:
        return items
    placed: list[Block] = [items[0]]
    for child in items[1:]:
        placed.append(spacer())
        placed.append(child)
    return tuple(placed)


def space_around(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: space-around` -- each child gets equal space on both sides.

    So the interior gaps are twice the end gaps, which CSS specifies as a
    behaviour and this expresses as a weight of 2 against a weight of 1. The
    third alignment that needs a paragraph of prose in the CSS spec is a number
    here.
    """
    items = tuple(children)
    if not items:
        return ()
    placed: list[Block] = [spacer(1)]
    for index, child in enumerate(items):
        if index:
            placed.append(spacer(2))
        placed.append(child)
    placed.append(spacer(1))
    return tuple(placed)


def space_evenly(children: Iterable[Block]) -> tuple[Block, ...]:
    """
    `justify-content: space-evenly` -- every gap equal, ends included.
    """
    items = tuple(children)
    if not items:
        return ()
    placed: list[Block] = [spacer()]
    for child in items:
        placed.append(child)
        placed.append(spacer())
    return tuple(placed)


# --------------------------------------------------------------------------
# Building nodes, and packing them
# --------------------------------------------------------------------------


def _to_node(block: Block, *, inherited_width: Scaled | None) -> Node:
    """
    One block as one layout node. Nothing here measures or positions anything.
    """
    match block:
        case Leaf():
            return Rule(width=block.width, height=block.height, depth=block.depth)
        case Spacer():
            return Glue(GlueSpec(width=0, stretch=block.weight, stretch_order=block.order))
        case Gap():
            return Glue(
                GlueSpec(
                    width=block.size,
                    stretch=block.stretch,
                    stretch_order=block.order,
                    shrink=block.shrink,
                    shrink_order=block.order,
                )
            )
        case Separator():
            return Kern(width=block.size, kind=KernKind.EXPLICIT)
        case Row():
            return _pack(block, inherited_width=inherited_width).box
        case Column():
            return _pack(block, inherited_width=inherited_width).box
        case _ as unreachable:
            assert_never(unreachable)


def _pack(block: Row | Column, *, inherited_width: Scaled | None) -> PackResult:
    """
    Pack one container, passing a known width down through a column only.

    A column knows how wide its children are because it stacks them; a row does
    not, because its siblings consume the space. So the width descends through
    columns and stops at every row that did not state one. The module docstring
    argues that this asymmetry is a property of the geometry rather than a
    shortcut.
    """
    match block:
        case Row():
            target = block.width if block.width is not None else inherited_width
            nodes = [_to_node(child, inherited_width=None) for child in block.children]
            if target is None:
                return hpack(nodes)
            return hpack(nodes, target, PackMode.EXACTLY)
        case Column():
            below = block.width if block.width is not None else inherited_width
            nodes = [_to_node(child, inherited_width=below) for child in block.children]
            if block.height is None:
                return vpack(nodes)
            return vpack(nodes, block.height, PackMode.EXACTLY)
        case _ as unreachable:
            assert_never(unreachable)


def measure(block: Row | Column, *, width: Scaled | None = None) -> PackResult:
    """
    Pack a layout and report how it went: the box, and whether it fitted.

    The full `PackResult`, not just the box, because "this toolbar is 12pt
    overfull at 200pt" is the thing a layout debugger wants and the thing a test
    should be able to assert. `advtext.pack` returns it unconditionally rather
    than printing to a terminal as TeX does, so it costs nothing to pass on.
    """
    return _pack(block, inherited_width=width)


def layout(block: Row | Column, *, width: Scaled | None = None) -> Box:
    """
    Pack a layout to a width and return the box.
    """
    return measure(block, width=width).box


def place(
    block: Row | Column,
    *,
    width: Scaled | None = None,
    origin: Point = ORIGIN,
) -> list[RuleRect]:
    """
    Pack a layout and return one rectangle per leaf, in tree order.

    Tree order is `leaves()`'s order, so the two zip. A leaf is a `Rule` and
    ship-out turns a rule into a `RuleRect`, which means this goes through the
    same coordinate walk that sets a paragraph -- and it means the SVG backend
    renders a block layout with no code of its own, since a `RuleRect` is a
    `DrawCmd` like any other.

    **A zero-area leaf produces no rectangle**, because §624 declines to output
    an empty rule. Give a leaf a height if you want to see it.
    """
    box = layout(block, width=width)
    return [cmd for cmd in ship(box, origin) if isinstance(cmd, RuleRect)]


def leaves(block: Block) -> tuple[Leaf, ...]:
    """
    Every leaf in the tree, in the order `place` emits rectangles for them.

    Exists so a caller can say which rectangle is which without this module
    inventing an identity for a leaf that nothing else would honour.
    """
    found: list[Leaf] = []
    _collect(block, found)
    return tuple(found)


def _collect(block: Block, found: list[Leaf]) -> None:
    match block:
        case Leaf():
            found.append(block)
        case Row() | Column():
            for child in block.children:
                _collect(child, found)
        case Spacer() | Gap() | Separator():
            pass
        case _ as unreachable:
            assert_never(unreachable)

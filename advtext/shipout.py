r"""
Ship-out: flattening a packed box tree into absolute-positioned draw commands.

This module is the boundary of the system. Above it everything is a tree in
layout coordinates and nothing knows where anything will actually appear; below
it everything is a flat list that a backend blits without understanding. It
imports no ImGui, no fontTools and no backend, and the two backends that consume
its output share no code with each other -- which is the property that proves the
geometry really was separated from the drawing rather than merely described as
separate.

It is TeX's `hlist_out`/`vlist_out` pair (§619-§640) with the DVI stripped out.
What is left when you remove the file format is exactly the recursive coordinate
walk, and that walk is the whole of this module.

**Coordinates are absolute integer scaled points, x right and y down.** Down,
because that is TeX's own convention -- `cur_v` grows downward through a page --
and because every device this project targets agrees with it. The `origin`
argument is the root box's *reference point*: on its baseline, at its left edge.
So `ship(page, Point(0, page.height))` puts the top-left corner of the page at
the coordinate origin, and that is the call a document renderer makes.

**Nothing here rounds to pixels, and that is the discipline rather than an
omission.** `docs/decisions.md` requires the pixel rounding to happen exactly
once, on a final absolute coordinate. The coordinates in these commands *are*
final and absolute, so a backend applies `advtext.units.round_to_px` to each one
as it draws and the requirement is met with nothing left to accumulate. Rounding
here would only mean rounding the same numbers one step earlier and losing the
bit-for-bit reproducibility that makes a golden artifact worth diffing.

**The one subtle algorithm is §625's glue rendering, and it is subtle on
purpose.** TeX does not compute each set glue node's width on its own. It carries
a running total of the natural stretch seen so far, multiplies that total by the
box's glue ratio, rounds *the total* once, and takes the difference against the
previously rounded total. The individual widths are differences of rounded sums
rather than rounded individually, which means the error never accumulates: after
the last glue node on a line the accumulated set glue is exactly the excess the
box was packed to absorb, so the last word lands exactly on the right margin.
Round each node independently instead and a justified paragraph acquires a
right edge that wavers by a scaled point or two per line -- which looks like a
bug in the line breaker, where nobody will find it.
`tests/test_shipout.py` pins a case that fails under independent rounding.

**Reading order, which is a contract with `advtext.selection`.**

Every command that a reader can point at carries an `index: int`. Indices start
at 0, increase strictly, and are assigned in the order material is traversed,
which is document reading order. Two node kinds take an index:

- a `CharNode`, which becomes a `Glyph`;
- a `Glue` node **in a horizontal list**, which becomes a `SetGlue` and is the
  interword space a reader expects to be able to select across.

- an **atom box** in a horizontal list (`is_atom`: an hbox whose contents open
  with a `MathOn` and close with a `MathOff`), which becomes one `Atom` and
  takes **one** index however much is inside it. This is an inline formula.
  The glyphs inside are shipped after the `Atom` and carry *its* index, so a
  colour over that index tints the whole formula; glue inside takes no index
  and emits nothing; and no `Line` is emitted for the hboxes of a vlist inside
  it, so a fraction's numerator is not a line of the paragraph. Measured
  before this existed (`.concerns/demo-review0-snippets/S12.py.txt`): a
  stacked box inside a line shipped a `Line` of its own, the glyph after it
  on the outer line was then culled with the inner line's band while still on
  screen, and a copy of `A`, the box's `B`, `C` came out `AC B`.

Everything else takes none. Vertical glue is not a character, and a click
between two lines belongs to a line rather than to the gap; `Line` commands are
what answer that. A `Kern`, a `Penalty` and a discretionary are invisible and
unpointable.

Two consequences worth stating plainly, because they are the ones a caller gets
wrong:

- **An index is a position in the shipped sequence, not an offset into the
  markdown source.** Line breaking discards the glue at each chosen break before
  ship-out ever sees it, so the indices are dense over what was actually set and
  there is no correspondence to source offsets. Anything wanting to map back to
  source has to carry its own spans, as `advtext.markdown.LinkSpan` does -- and
  those spans are in *material* indices, which are not these either.
  `advtext.spans` is the map between the two.
- **What a `SetGlue` means as *text* is the selection task's decision, not
  this module's.** Most of them are interword spaces; a paragraph's
  `\parfillskip` is one too and serialises as a trailing space unless somebody
  decides otherwise. The geometry is here; the semantics are not.

**No colour.** `advtext.style` and `advtext.markdown` both settled that colour is
presentation and belongs to the backend, and the node model carries none, so a
colour field here would have exactly one value forever and would be a second
place to look for something that is not there. A backend that wants to tint a
link reads `advtext.markdown.LinkSpan`, turns its material range into ranges of
these indices with `advtext.spans.map_text_block`, and draws from those -- the
same mechanism selection highlighting uses. (This paragraph used to say a
backend "matches it against these indices" as though that were a lookup. It is
not: a `LinkSpan` counts kerns, penalties and the glue the breaker discarded,
and these indices count the `\rightskip` it added, so until `advtext.spans`
existed nothing in the tree could do the matching and nothing did.)

**No size either.** A `FontKey` *is* a face at a size -- `advtext.style.font_key`
encodes both and `parse_font_key` decodes them -- so a separate `size` field
would let a command name one size in its key and a different one beside it.

Deliberately out of scope:

- **Leaders** (§626-§629, §635-§637). A glue subtype this project does not use;
  they are the one thing that makes ship-out output a *loop* rather than a walk.
- **The DVI machinery**: `push`/`pop`, `prune_movements`, `synch_h`/`synch_v`,
  `dvi_f` font switching, `max_push`. All of it exists to make the byte stream
  short and none of it affects a single coordinate.
- **Whatsits, `\special`, inserts and marks.** No page builder, nothing to say.
- **`\shipout`'s page origin offset** -- TeX's one-inch `\hoffset`/`\voffset`
  margin. A caller places the page by choosing `origin`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final, TypeAlias, assert_never

from advtext.nodes import (
    Box,
    BoxKind,
    CharNode,
    Disc,
    FontKey,
    Glue,
    GlueSign,
    Kern,
    MathOff,
    MathOn,
    Penalty,
    Rule,
)
from advtext.pack import CharMeasure
from advtext.units import RUNNING, Scaled

__all__ = [
    "BILLION",
    "ORIGIN",
    "Atom",
    "DrawCmd",
    "Glyph",
    "Line",
    "Point",
    "RuleRect",
    "SetGlue",
    "atom_box",
    "is_atom",
    "pascal_round",
    "ship",
]

BILLION: Final = 1_000_000_000.0
"""
The `vet_glue` clamp (§625): `@d billion == float_constant(1000000000)`.

A guard on a `real` multiplication, not a design choice -- it stops a wildly
stretched infinite-order glue from producing a product that overflows a `scaled`
when rounded. It fires only on input that was already nonsense, and it is kept
because a port that drops it fails differently from TeX on exactly the inputs
nobody has a test for.
"""


def pascal_round(value: float) -> int:
    """
    Pascal's `round`: to nearest, ties **away from zero**.

    §625 rounds the accumulated glue product with Pascal's `round`, which is not
    Python's. Python's builtin rounds ties to even, so `round(2.5)` is 2 where
    Pascal gives 3, and `round(-0.5)` is 0 where Pascal gives -1. That looks like
    a rounding nicety and is not: `glue_set` is a ratio of two integers and
    `cur_glue` is an integer sum of scaled points, so the product lands on an
    exact half routinely rather than rarely. And because §625 takes *differences*
    of successive rounded totals, one tie resolved the other way shifts every
    glue node after it by a scaled point.

    Distinct from `advtext.units.round_to_px`, which is a different operation in
    different units -- scaled points to device pixels, once, on a final absolute
    coordinate -- and correctly uses Python's rounding. See correction C3 in
    `docs/tex-notes.md`.
    """
    if value >= 0.0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


@dataclass(frozen=True, slots=True)
class Point:
    """
    An absolute position in scaled points, x rightward and y downward.
    """

    x: Scaled = 0
    y: Scaled = 0


@dataclass(frozen=True, slots=True)
class Glyph:
    """
    One character, placed.

    `x` is the left edge of the glyph's advance and `y` is **on the baseline**,
    not at the top of the glyph. A backend that treats `y` as a top edge draws
    every line roughly one ascent too low, which is the single most common way
    to get this wrong and does not look like a sign error when it happens.

    `font` is the whole identity of the face and its size; `advtext.style`
    encodes it and `advtext.style.parse_font_key` is the only decoder.
    """

    font: FontKey
    codepoint: int
    x: Scaled
    y: Scaled
    index: int


@dataclass(frozen=True, slots=True)
class RuleRect:
    """
    A filled rectangle: fraction bars, underlines, table borders, thematic breaks.

    Unlike everything else here this is an ordinary top-left rectangle, because
    a rule has no baseline of its own and §624 resolves it to a device rectangle
    before drawing. `y` is the top edge and `height` extends downward from it, so
    the rule covers `[y, y + height)`.

    Nothing about it is pointable, so it carries no index: a horizontal rule
    between two paragraphs is not a character and selecting "across" it selects
    the paragraphs on either side.
    """

    x: Scaled
    y: Scaled
    width: Scaled
    height: Scaled


@dataclass(frozen=True, slots=True)
class SetGlue:
    """
    A horizontal glue node, at the width this particular packing gave it.

    `width` is the *set* width -- natural plus whatever §625 handed this node --
    and `natural` is what the spec asked for. The difference is what makes a
    debug overlay legible: it is precisely the amount this space was stretched or
    squeezed to justify the line, and it is the only place in a rendered document
    where the line breaker's decision is visible as a number.

    `y` and `height`/`depth` are the enclosing line's, not the glue's, so the
    rect a selection or an overlay draws for it is full line height and lines up
    with the glyphs either side.
    """

    x: Scaled
    y: Scaled
    width: Scaled
    natural: Scaled
    height: Scaled
    depth: Scaled
    index: int


@dataclass(frozen=True, slots=True)
class Atom(SetGlue):
    """
    A box that is one pointable item: an inline formula, placed.

    The rectangle a reader points at, with nothing in it to draw; the glyphs
    and rules of the formula follow as ordinary commands, the glyphs carrying
    this command's `index`. `width` and `natural` are both the box's width.
    `y`, `height` and `depth` are the enclosing line's, as a `SetGlue`'s are,
    so a highlight over it is as tall as the highlight over the words beside
    it.

    **A subclass of `SetGlue`, and that is a deliberate economy.** It adds no
    field. What it adds is a type a consumer can ask about: `advtext.selection`
    makes it one item that is neither a character nor a space, and
    `advtext.spans` anchors on it. A consumer that does not ask -- a backend's
    `match` -- takes it for a set glue, which draws nothing outside a debug
    overlay, and that is the right thing for it to do. A fifth member of
    `DrawCmd` would have been a type error in every backend's `assert_never`
    for a command none of them draws.

    What it copies as is not here: ship-out has the box and not the source it
    was built from. `advtext.selection.FragmentQueries.text` takes that as
    data (`atoms`), from the layer that has the block.
    """


def is_atom(box: Box) -> bool:
    """
    Whether a box ships as one pointable item: an hbox bracketed by math nodes.

    `MathOn` first and `MathOff` last, *inside* the box. TeX puts the pair
    around an inline formula in the paragraph's own list (§147); there the
    line breaker prunes a `MathOn` that starts a line (§879, and
    `advtext.linebreak` follows it), so a bracket in the list does not survive
    to ship-out and one inside the box does. Nothing else in this tree builds
    a box of this shape.
    """
    contents = box.contents
    return (
        box.kind is BoxKind.HLIST
        and len(contents) >= 2
        and isinstance(contents[0], MathOn)
        and isinstance(contents[-1], MathOff)
    )


def atom_box(box: Box) -> Box:
    """
    `box` wrapped so that it ships as one item, with the same three dimensions.

    The wrapper is an hbox at the box's natural size, so it measures and packs
    exactly as the box did; the line breaker cannot cut inside a box, so it
    also breaks as a unit.
    """
    return Box(
        kind=BoxKind.HLIST,
        contents=(MathOn(), box, MathOff()),
        width=box.width,
        height=box.height + max(0, -box.shift_amount),
        depth=box.depth + max(0, box.shift_amount),
    )


@dataclass(frozen=True, slots=True)
class Line:
    """
    An hbox that was an item of a vertical list: one line of set material.

    Emitted *before* the commands it covers, so a single forward pass can keep
    track of which line it is in. `start` and `end` are the half-open range of
    indices the line contains; a line with no pointable material has
    `start == end`.

    This is what makes selection rects coherent. A multi-line selection is not
    one rectangle, and each fragment wants the full line height rather than the
    ink extent of whatever glyphs happen to be in it -- otherwise a line of
    lowercase text gets a visibly shorter highlight than the line above it.
    `y` is the baseline, so the fragment spans `[y - height, y + depth)`.

    **`height` and `depth` are the box's, and making them a full line height is
    somebody else's job.** `hpack` takes the maximum over the *ink* of the
    glyphs, so an hbox of `xxx` has x-height and zero depth, faithfully to TeX;
    what puts a floor under that is `advtext.style.Strut`, applied per line by
    `advtext.ui`. Recomputing anything here from the glyphs would undo it.

    A bare hlist handed straight to `ship` counts as one line, because a caller
    shipping a single line should not have to wrap it in a vbox to be told where
    it is.
    """

    x: Scaled
    y: Scaled
    width: Scaled
    height: Scaled
    depth: Scaled
    start: int
    end: int


DrawCmd: TypeAlias = Glyph | RuleRect | SetGlue | Line
"""
Anything ship-out emits.

A union of frozen dataclasses rather than a base class, so a backend's `match`
plus `assert_never` turns a forgotten variant into a type error at a named line
rather than a silently undrawn thing.
"""


class _Shipper:
    """
    The recursive walk, with the state §619 declares as locals of `hlist_out`.

    A class rather than threaded arguments because `cmds` and the reading index
    are genuinely shared across the whole recursion, while `cur_glue`/`cur_g` are
    genuinely per-box -- TeX declares the latter inside `hlist_out` and gets a
    fresh pair per invocation for free. Passing six accumulators through two
    mutually recursive functions would obscure which of them reset and which do
    not, and that distinction is the bug this arrangement cannot have.
    """

    __slots__ = ("cmds", "in_atom", "index", "measure")

    def __init__(self, measure: CharMeasure | None) -> None:
        self.cmds: list[DrawCmd] = []
        self.index = 0
        self.measure = measure
        # True while walking the inside of an atom box: nothing in there takes
        # an index of its own or is a line. See `Atom`.
        self.in_atom = False

    def _advance_of(self, node: CharNode) -> Scaled:
        """
        The width `hlist_out` moves by after setting one character (§620).
        """
        if self.measure is None:
            raise ValueError(
                "ship was given a CharNode but no `measure`; a character carries no "
                "dimensions of its own, so placing one needs a way to look its advance up"
            )
        return self.measure(node).width

    def line_out(self, box: Box, left_edge: Scaled, base_line: Scaled) -> None:
        """
        Ship an hbox as a line, bracketing it with the `Line` command that covers it.

        The `Line` goes into the list before its contents so that one forward
        pass always knows which line it is inside, which means its index range is
        not known when it is appended and is patched in afterwards. That is the
        only mutation in this module, it is confined to a slot this call owns,
        and the alternative -- shipping the contents into a scratch list and
        splicing -- allocates a list per line to avoid one assignment.
        """
        slot = len(self.cmds)
        start = self.index
        header = Line(
            x=left_edge,
            y=base_line,
            width=box.width,
            height=box.height,
            depth=box.depth,
            start=start,
            end=start,
        )
        self.cmds.append(header)
        self.hlist_out(box, left_edge, base_line)
        self.cmds[slot] = replace(header, end=self.index)

    def hlist_out(self, box: Box, left_edge: Scaled, base_line: Scaled) -> None:
        """
        §619-§625: walk a horizontal list left to right, holding `cur_v = base_line`.
        """
        cur_h = left_edge
        cur_glue = 0.0
        cur_g: Scaled = 0

        for node in box.contents:
            match node:
                case CharNode():
                    self.cmds.append(
                        Glyph(
                            font=node.font,
                            codepoint=node.codepoint,
                            x=cur_h,
                            y=base_line,
                            index=self.index,
                        )
                    )
                    if not self.in_atom:
                        self.index += 1
                    cur_h += self._advance_of(node)

                case Box() if not self.in_atom and is_atom(node):
                    # One item, then its ink. The index moves on only after
                    # the inside has been walked, so every glyph in there
                    # carries the atom's.
                    self.cmds.append(
                        Atom(
                            x=cur_h,
                            y=base_line,
                            width=node.width,
                            natural=node.width,
                            height=box.height,
                            depth=box.depth,
                            index=self.index,
                        )
                    )
                    self.in_atom = True
                    self.hlist_out(node, cur_h, base_line + node.shift_amount)
                    self.in_atom = False
                    self.index += 1
                    cur_h += node.width

                case Box():
                    # §621: the sub-box is shifted *down* by shift_amount, and
                    # cur_h afterwards is the edge plus the box's own width --
                    # never wherever the recursion happened to leave it. An hbox
                    # inside an hbox is not a line: a list marker or a formula is
                    # part of the line that contains it.
                    self.descend(node, cur_h, base_line + node.shift_amount, as_line=False)
                    cur_h += node.width

                case Rule():
                    # §624's fin_rule: a running height or depth takes the
                    # enclosing box's, and the two together are the thickness.
                    if node.width == RUNNING:
                        raise ValueError(
                            "a rule's width is never running inside an hlist (tex.web §138); "
                            "resolve it before shipping"
                        )
                    height = box.height if node.height == RUNNING else node.height
                    depth = box.depth if node.depth == RUNNING else node.depth
                    thickness = height + depth
                    if thickness > 0 and node.width > 0:
                        self.cmds.append(
                            RuleRect(
                                x=cur_h,
                                y=base_line - height,
                                width=node.width,
                                height=thickness,
                            )
                        )
                    cur_h += node.width

                case Glue():
                    set_width, cur_glue, cur_g = _set_glue_width(node, box, cur_glue, cur_g)
                    if not self.in_atom:
                        self.cmds.append(
                            SetGlue(
                                x=cur_h,
                                y=base_line,
                                width=set_width,
                                natural=node.spec.width,
                                height=box.height,
                                depth=box.depth,
                                index=self.index,
                            )
                        )
                        self.index += 1
                    cur_h += set_width

                case Kern() | MathOn() | MathOff():
                    # §622: `kern_node,math_node: cur_h := cur_h + width(p)`.
                    cur_h += node.width

                case Penalty() | Disc():
                    # §622's `othercases do_nothing`. A penalty has no extent, and
                    # a discretionary that survived line breaking was not taken.
                    pass

                case _ as unreachable:
                    assert_never(unreachable)

    def vlist_out(self, box: Box, left_edge: Scaled, reference: Scaled) -> None:
        """
        §629-§634: walk a vertical list downward, holding `cur_h = left_edge`.

        Entered at the box's reference point and stepping immediately to its top
        edge, which is what `cur_v := cur_v - height(this_box)` (§630) does. Every
        item then advances `cur_v` by its own height to reach its baseline and by
        its depth afterwards.
        """
        cur_v = reference - box.height
        cur_glue = 0.0
        cur_g: Scaled = 0

        for node in box.contents:
            match node:
                case CharNode():
                    raise ValueError(
                        "a character cannot appear in a vertical list (tex.web §630 calls "
                        'this confusion("vlistout")); pack it into an hbox first'
                    )

                case Box():
                    # §632: down to this item's baseline, recurse, then down by
                    # its depth. `shift_amount` moves the box *right* here. An
                    # hbox that is an item of a vertical list is exactly what a
                    # line is -- `line_break` hpacks each line and appends it --
                    # so this is where a `Line` command comes from.
                    cur_v += node.height
                    self.descend(
                        node, left_edge + node.shift_amount, cur_v, as_line=not self.in_atom
                    )
                    cur_v += node.depth

                case Rule():
                    # §633: a running width takes the enclosing box's, and cur_v
                    # advances past the rule before it is drawn -- so the rule
                    # hangs above the new cur_v, not below it.
                    if node.height == RUNNING or node.depth == RUNNING:
                        raise ValueError(
                            "a rule's height and depth are never running inside a vlist "
                            "(tex.web §138); resolve them before shipping"
                        )
                    width = box.width if node.width == RUNNING else node.width
                    thickness = node.height + node.depth
                    cur_v += thickness
                    if thickness > 0 and width > 0:
                        self.cmds.append(
                            RuleRect(
                                x=left_edge,
                                y=cur_v - thickness,
                                width=width,
                                height=thickness,
                            )
                        )

                case Glue():
                    # §634 is §625 with `rule_ht` for `rule_wd`. Vertical glue is
                    # not pointable, so it takes no index and emits no command --
                    # a click between two lines belongs to a line.
                    set_height, cur_glue, cur_g = _set_glue_width(node, box, cur_glue, cur_g)
                    cur_v += set_height

                case Kern():
                    # §631: `kern_node: cur_v := cur_v + width(p)`.
                    cur_v += node.width

                case Penalty() | Disc() | MathOn() | MathOff():
                    # §631's `othercases do_nothing`. None of these belongs in a
                    # proper vertical list, and where one does it has no extent.
                    pass

                case _ as unreachable:
                    assert_never(unreachable)

    def descend(self, box: Box, x: Scaled, y: Scaled, *, as_line: bool) -> None:
        """
        Recurse into a sub-box. `as_line` says whether an hbox here is a line.
        """
        match box.kind:
            case BoxKind.HLIST:
                if as_line:
                    self.line_out(box, x, y)
                else:
                    self.hlist_out(box, x, y)
            case BoxKind.VLIST:
                self.vlist_out(box, x, y)
            case _ as unreachable:
                assert_never(unreachable)


def _set_glue_width(
    node: Glue, box: Box, cur_glue: float, cur_g: Scaled
) -> tuple[Scaled, float, Scaled]:
    """
    §625: the set width of one glue node, and the running state it leaves behind.

    Transcribed rather than simplified. The width is `width(g) - cur_g` computed
    *before* the accumulator moves and `+ cur_g` after it, so each node gets the
    difference between two rounded totals rather than its own rounded share. The
    asymmetry is the source's: `cur_glue` grows on stretch and shrinks on
    shrink, because §664 stores `glue_set` as a positive ratio in both directions
    and the sign lives in `glue_sign` alone.

    Glue whose order does not match the box's contributes nothing and renders at
    exactly its natural width (§646's "as if no other orders were present").
    """
    spec = node.spec
    width = spec.width - cur_g

    if box.glue_sign is GlueSign.STRETCHING:
        if spec.stretch_order is box.glue_order:
            cur_glue += spec.stretch
            cur_g = pascal_round(_vet_glue(box.glue_set * cur_glue))
    elif box.glue_sign is GlueSign.SHRINKING:
        if spec.shrink_order is box.glue_order:
            cur_glue -= spec.shrink
            cur_g = pascal_round(_vet_glue(box.glue_set * cur_glue))

    return width + cur_g, cur_glue, cur_g


def _vet_glue(product: float) -> float:
    """
    §625's `vet_glue`: clamp a glue product to +/- one billion before rounding.
    """
    return max(-BILLION, min(BILLION, product))


ORIGIN: Final = Point()
"""
The default placement: the root box's reference point at the coordinate origin.
"""


def ship(
    box: Box,
    origin: Point = ORIGIN,
    *,
    measure: CharMeasure | None = None,
) -> list[DrawCmd]:
    """
    Flatten a packed box into absolute-positioned draw commands.

    `origin` is `box`'s reference point: on its baseline, at its left edge. To
    put the top-left corner of a page at the coordinate origin, pass
    `Point(0, box.height)`.

    `measure` is the same `CharMeasure` `advtext.pack.hpack` takes and must be
    the *same* one, resolved against the same metrics. A `CharNode` carries no
    advance, so ship-out has to look it up again, and a ship-out measuring
    differently from the packing that produced the box would lay glyphs out
    inside a line whose width was computed from other numbers. It is required
    only if the tree contains a character.

    The commands come back in reading order, with each `Line` immediately
    preceding the material it covers.
    """
    shipper = _Shipper(measure)
    shipper.descend(box, origin.x, origin.y, as_line=True)
    return shipper.cmds

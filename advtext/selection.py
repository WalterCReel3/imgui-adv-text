r"""
Selection: turning shipped draw commands back into carets, ranges, rects and text.

`docs/decisions.md` calls selection the point of the project, and this module is
where that claim is cashed. pptmstr records that ImGui text is not selectable and
calls it "a real gap in ImGui, not a workaround failing"
(`pptmstr/ui/transcript_pane.py:14-16`), then works around it by copying whole
blocks from a context menu (`rich_pane.py:417-421`). The gap is real *for a
widget*, because a widget owns its layout and never tells you where a glyph
landed. We computed every glyph position ourselves, so hit testing here is
arithmetic over data we already have, and this module needs no font, no metrics
and no ImGui to do it.

**It needs no metrics because of how the commands are shaped, which is worth
knowing before you reach for one.** A `Glyph` carries no advance, so the right
edge of a glyph is not on the glyph -- it is the `x` of the next item on the same
line, and for the last item it is the line's right edge. That is exact rather
than approximate, and it is *better* than asking a font: it absorbs any kern
between a pair into the left glyph's cell, so there is no sliver between two
kerned letters where a click belongs to neither.

**Boundaries, not glyphs.** A caret sits between characters, so a position is an
integer in `[0, n]`: boundary `b` is immediately before item `b`, and boundary
`n` is past the end. Clicking the left half of a glyph gives the boundary before
it and the right half the boundary after it, which is what every text system does
and what a reader's hand already expects.

Boundaries index the reading order `advtext.shipout` assigns. Two kinds of thing
take an index there: a glyph, and a *horizontal* glue node -- the interword space.
Vertical glue does not, so the gap between two lines belongs to a line rather than
to itself.

**Why there is no caret affinity, which is the thing this design gets for free.**
Indices are dense, so the boundary at the end of line `k` and the boundary at the
start of line `k+1` are the *same number*: the glue at the break was discarded
before ship-out ever saw it. In an editor that ambiguity is the "affinity"
problem and it needs a flag on every caret. It never becomes visible here because
rects are derived from the *items a range covers* rather than from its endpoints:
a range ending at that boundary covers the last item of line `k` and none of line
`k+1`, so it draws one rect on line `k` and nothing below. Hit testing still
chooses the line by `y` first and only then clamps `x` inside it, so a click past
the right margin of line `k` lands at line `k`'s end -- which is the same integer
as line `k+1`'s start, and means the same selection either way. (`x` does choose
between lines that share a vertical band -- the lines of two wrapped table cells
in one row -- and `fragment_nearest` says exactly when.)

**Nested lines are handled rather than assumed away.** An hbox inside a vlist is
a line, and a vbox inside an hbox -- a table cell, a `\vcenter` -- puts lines
inside a line. `advtext.shipout` emits both, so the ranges nest. Each item is
assigned to the *innermost* line containing it, which is the one a reader would
point at, and only those innermost lines become selectable fragments.

**The serialization decision, which is a real judgement call.**

A paragraph broken into five lines is one paragraph. Copying it must not produce
five hard-wrapped lines with this column's width frozen into them -- paste that
into an editor at a different width and it is visibly broken. So **a line break
introduced by layout serialises as a single space, never as a newline.**

But some line breaks *are* content. Every line of a fenced code block is a
separate line in the source, and joining them with spaces destroys the program.
Nothing in the shipped command stream distinguishes the two cases: ship-out sees
boxes in a vertical list and has no idea which of them a line breaker produced
and which a source newline did.

Rather than guess -- a vertical-gap threshold or an indent heuristic would be a
parallel scheme invented here and wrong somewhere -- `text()` takes the structural
breaks as data. `separators` maps a boundary to what belongs before the item
there -- a newline, a blank line, a tab -- and everything not in it is a wrap and
joins with a space. (`hard_breaks`, the first form of this, is the same with the
separator fixed at one newline; a set could not say "a blank line here" or "a
tab here", which is what a paragraph boundary and a table cell need.) The layer
that built the document knows which is which, because it is the layer that put
the source newlines there: `advtext.ui.units.UnitModel.copy_text` builds the
mapping from the blocks. The default is empty, which means "everything is a
wrap", which is the right default for prose and the wrong one for code.

**An inline formula is one item.** `advtext.shipout` ships an atom box as one
`Atom` followed by its ink, the glyphs carrying the atom's index. Here the
`Atom` is the item and the glyphs after it that repeat its index are not: a
caret cannot land inside a formula because there is no boundary there, a
double click takes the formula alone, and its highlight is the atom's own
rectangle at the line's height. What it copies as is data, like a structural
break: `text()` takes `atoms`, a mapping from the item's index to its text
(`$...$` source, from `advtext.ui.units`), and an atom nobody named copies as
nothing -- the glyphs of a formula are math-italic and private-use codepoints,
which are not what anybody typed.

Deliberately out of scope, with reasons:

- **A caret rectangle.** That is the one place the affinity ambiguity above would
  become visible, and answering it needs a flag on a boundary that nothing else
  in this module needs. If a blinking caret is wanted, it needs designing rather
  than deriving.
- **Editing.** No insertion, deletion or reflow. This is a read-only document.
- **Bidi selection.** Left to right only, per `docs/decisions.md`. A visual range
  and a logical range are the same thing here and are not in general.
- **Rule and image content.** A `RuleRect` carries no index because a thematic
  break is not a character; selecting across one selects the paragraphs either
  side and does not put anything in the clipboard for the rule itself.
- **Accessibility trees, IME composition, drag-and-drop.** A widget system's
  problems, not a layout model's.
"""

from __future__ import annotations

import enum
from bisect import bisect_left, bisect_right
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

from advtext.shipout import Atom, DrawCmd, Glyph, Line, Point, RuleRect, SetGlue
from advtext.units import Scaled

__all__ = [
    "Boundary",
    "Fragment",
    "FragmentQueries",
    "Granularity",
    "Item",
    "Rect",
    "Selection",
    "SelectionModel",
    "fragment_nearest",
]

Boundary: TypeAlias = int
"""
A caret position: an integer in `[0, n]`, immediately before item `b`.

A plain `int` because it is an index into the reading order and every operation
on it is index arithmetic. See the module docstring on why it carries no
affinity.
"""

Item: TypeAlias = Glyph | SetGlue
"""
The shipped commands a reader can point at: a glyph, an interword space, and an
`advtext.shipout.Atom` -- an inline formula, which is a `SetGlue` by type.
"""


class Granularity(enum.Enum):
    """
    How much a single gesture selects: one click, a double click, a triple click.

    An enum rather than three functions because a UI holds the current
    granularity as *state* -- a drag that began as a double click keeps selecting
    whole words as it extends -- and that state wants a name.
    """

    CHARACTER = enum.auto()
    WORD = enum.auto()
    LINE = enum.auto()


class _Class(enum.Enum):
    """
    What kind of run a word-granularity selection expands over.

    Three classes rather than two because double-clicking a space should select
    the run of spaces and double-clicking punctuation the run of punctuation,
    which is what an editor does and what "stops at punctuation" means from the
    other side.
    """

    WORD = enum.auto()
    SPACE = enum.auto()
    OTHER = enum.auto()
    ATOM = enum.auto()


def _classify(item: Item) -> _Class:
    """
    Which run `item` belongs to for word granularity.

    Word characters are alphanumerics and the underscore. Apostrophes and hyphens
    are deliberately *not* word characters: including them would make "don't" one
    word and "well-known" one word, which is a defensible choice, but it also
    makes `foo-bar` and `a--b` one word, and the rule has to be the same in code
    and in prose because this layer cannot tell them apart.
    """
    if isinstance(item, Atom):
        # A formula is its own kind of run: a double click takes it and not
        # the spaces or the brackets beside it.
        return _Class.ATOM
    if isinstance(item, SetGlue):
        return _Class.SPACE
    character = chr(item.codepoint)
    if character.isalnum() or character == "_":
        return _Class.WORD
    if character.isspace():
        return _Class.SPACE
    return _Class.OTHER


@dataclass(frozen=True, slots=True)
class Rect:
    """
    A highlight rectangle, top-left anchored, in the same scaled points ship-out uses.

    Not baseline-anchored, unlike a `Glyph`: a highlight is a device rectangle and
    has no baseline of its own. `y` is the top edge and the rect covers
    `[y, y + height)`.
    """

    x: Scaled
    y: Scaled
    width: Scaled
    height: Scaled


@dataclass(frozen=True, slots=True)
class Selection:
    """
    A half-open range of reading-order items, `[start, end)`, always normalised.

    Half-open because it is a range of *items* rather than of boundaries, and
    because that makes "the selection covers nothing" expressible as
    `start == end` without a separate flag. Normalised on construction through
    `SelectionModel.select`, which is what makes a backwards drag work -- the case
    that is broken in every hand-rolled selection, because the code that builds
    the rects quietly assumes `start <= end` and produces nothing when it is not.
    """

    start: Boundary
    end: Boundary

    @property
    def is_empty(self) -> bool:
        """
        Whether this selects nothing, which is what a plain click produces.
        """
        return self.start >= self.end

    def covers(self, index: int) -> bool:
        """
        Whether item `index` is inside the selection.
        """
        return self.start <= index < self.end


@dataclass(frozen=True, slots=True)
class Fragment:
    """
    One visual line, with the pointable items on it and where each one ends.

    `edges` has one more entry than `items`: `edges[k]` is the left edge of item
    `k` and `edges[-1]` is the line's right edge, so the cell of item `k` is
    `[edges[k], edges[k + 1])` and every x query is a lookup rather than a
    measurement. See the module docstring on why that is exact and a font is not
    needed.

    **`indices` is not `range(start, end)` and assuming it is was a real defect.**
    A line's index range is dense, but a line that *encloses another line* owns
    only the items outside the nested one, so its own run has a hole in it. That
    shape is not exotic -- it is every stacked-limits operator
    (`advtext.math.mlist._stack_limits` returns a vlist, and ship-out gives a
    vlist child its own `Line`), so the sigma litmus test produces one. Deriving
    an offset as `index - start` then walks off the end of `edges`. Every lookup
    here goes through `indices` instead, which is the items' own reading order
    and is correct whether or not there is a hole.
    """

    line: Line
    items: tuple[Item, ...]
    edges: tuple[Scaled, ...]
    indices: tuple[Boundary, ...]
    outer: Line | None = None
    """
    The outermost line this one is nested in, or `None` for a line that stands alone.

    A table row whose cells wrapped is one line holding a stack of lines per
    cell, so every line of every cell of that row has the row as its `outer`.
    It is what tells hit testing that two lines at different heights are side
    by side in one row rather than one above the other: see `fragment_nearest`.
    """

    def offset_of(self, boundary: Boundary) -> int | None:
        """
        Which of this line's own items `boundary` addresses, or `None` for a hole.
        """
        position = bisect_left(self.indices, boundary)
        if position < len(self.indices) and self.indices[position] == boundary:
            return position
        return None

    def owned_range(self, first: Boundary, last: Boundary) -> tuple[int, int] | None:
        """
        The offsets of the owned items inside `[first, last]`, or `None` for none.

        The items a fragment owns inside a range are always a contiguous run of
        offsets even when their indices are not contiguous, because a selection
        is itself a range -- so this is two bisections and not a scan.
        """
        low = bisect_left(self.indices, first)
        high = bisect_right(self.indices, last) - 1
        return (low, high) if low <= high else None

    @property
    def start(self) -> Boundary:
        """
        The boundary at the very start of this line.
        """
        return self.line.start

    @property
    def end(self) -> Boundary:
        """
        The boundary just past the last item on this line.
        """
        return self.line.end

    @property
    def reach(self) -> tuple[Scaled, Scaled]:
        """
        The vertical band of the row this line is part of: its `outer` line's, or its own.
        """
        line = self.line if self.outer is None else self.outer
        return line.y - line.height, line.y + line.depth

    @property
    def top(self) -> Scaled:
        """
        The top edge of the full-height band this line occupies.
        """
        return self.line.y - self.line.height

    @property
    def bottom(self) -> Scaled:
        """
        The bottom edge of the band: one past the last row the line covers.
        """
        return self.line.y + self.line.depth

    def rect_for(self, first: int, last: int) -> Rect:
        """
        The highlight covering items `first` through `last` inclusive, full line height.

        Full line height on purpose. Deriving it from the glyphs' own extents
        would make a line of lowercase letters highlight shorter than the line
        above it, and a selection whose height flickers with whether a line
        happens to contain a descender reads as broken even though every
        rectangle in it is defensible.

        `first` and `last` are reading-order indices and are clamped to what this
        line actually owns; a caller that passes a range this line owns nothing in
        gets a `ValueError` rather than a rectangle for the wrong items.
        """
        span = self.owned_range(first, last)
        if span is None:
            raise ValueError(f"line [{self.start}, {self.end}) owns nothing in [{first}, {last}]")
        low, high = span
        left = self.edges[low]
        right = self.edges[high + 1]
        return Rect(x=left, y=self.top, width=right - left, height=self.bottom - self.top)


def _fragments(cmds: Sequence[DrawCmd]) -> tuple[Fragment, ...]:
    """
    Group shipped commands into visual lines, innermost line wins.

    `advtext.shipout` emits each `Line` before the material it covers and nests
    them where boxes nest, so one forward pass with a stack assigns every item to
    the innermost line containing it. A line that turned out to contain only
    other lines is a container -- a table row, a `\\vcenter` -- and is not a
    fragment: pointing at it means pointing at one of the lines inside it.

    **Nor is a line that holds a rule and nothing else.** A thematic break and
    the line under a table's header are each an hbox in the vertical list, so
    ship-out gives each a `Line`, and with no item on it such a line used to
    pass for a blank line of text: copying across one put a newline in the
    clipboard that no source line stood for. A blank line of *text* -- the
    empty line in a fenced code block -- has no rule in it, and stays.
    """
    stack: list[Line] = []
    owned: dict[int, list[Item]] = {}
    order: list[Line] = []
    has_child: set[int] = set()
    ruled: set[int] = set()
    outer: dict[int, Line] = {}
    # The index of the atom whose ink is being passed over, if any: the glyphs
    # of a formula repeat their atom's index and are not items themselves.
    atom = -1

    for cmd in cmds:
        match cmd:
            case Line():
                while stack and cmd.start >= stack[-1].end:
                    stack.pop()
                if stack:
                    has_child.add(id(stack[-1]))
                    outer[id(cmd)] = stack[0]
                stack.append(cmd)
                owned.setdefault(id(cmd), [])
                order.append(cmd)
            case Glyph() | SetGlue():
                if cmd.index == atom and isinstance(cmd, Glyph):
                    continue
                if isinstance(cmd, Atom):
                    atom = cmd.index
                while stack and cmd.index >= stack[-1].end:
                    stack.pop()
                if stack:
                    owned[id(stack[-1])].append(cmd)
            case RuleRect():
                # A rule carries no index and cannot be pointed at; it marks
                # the line it sits in as not being a line of text. A fraction
                # bar is a rule too, but the line it is on holds the formula's
                # atom, so that line has an item and stays a line of text.
                if stack:
                    ruled.add(id(stack[-1]))

    fragments: list[Fragment] = []
    for line in order:
        items = owned[id(line)]
        if not items and (id(line) in has_child or id(line) in ruled):
            continue
        fragments.append(
            Fragment(
                line=line,
                items=tuple(items),
                edges=_edges(line, items),
                indices=tuple(item.index for item in items),
                outer=outer.get(id(line)),
            ),
        )
    fragments.sort(key=lambda fragment: fragment.start)
    return tuple(fragments)


def fragment_nearest(fragments: Iterable[Fragment], point: Point) -> Fragment | None:
    """
    The line a point belongs to, out of `fragments`: `y` decides first, then `x`.

    Choosing the line by `y` *before* looking at `x` is what makes a click past
    the right margin land at the end of that line rather than on whichever line
    happens to have a glyph nearest in a straight line. A point above the first
    line belongs to the first line and one below the last to the last, because
    a drag that leaves the document should extend the selection rather than
    stop.

    **`x` is consulted only to choose between lines that `y` cannot separate**,
    and until table cells could wrap there were none that mattered. A wrapped
    cell is a stack of lines beside its neighbour's stack, and that makes two
    things true that are false of a paragraph. Two lines can share a vertical
    band; and a point can be level with one cell's fifth line while sitting
    under another cell's only one. So the rule has three steps, and for lines
    stacked in one column -- every paragraph -- the first two never fire:

    1. **The point is inside a row, over a line of it.** Take the lines whose
       *row* (`Fragment.reach`) contains `y` and whose own horizontal extent
       contains `x`: those are the lines of the cell under the point. The one
       whose band contains `y` wins, else the nearest of them in `y`. A click
       below a short cell's last line, level with its neighbour's later lines,
       is a click in the short cell.
    2. **Some line's band contains `y`** but none has `x` in it -- the padding
       between two cells, or the margin beside any line. The nearest of those
       in `x` wins.
    3. **No band contains `y`.** The nearest line in `y` wins, and `x` breaks a
       tie.

    Ties go to the earlier line in reading order, which is what the scan this
    replaces did. A line that stands alone is its own row, so step 1 chooses
    among lines whose band contains `y` and whose extent contains `x` -- at
    most one in a column of text -- and the answer is the one it always was;
    `tests/test_selection.py`'s older tests did not change.

    `fragments` must be in reading order and must include every line whose row
    contains `point.y`, or the nearest line if none does. Passing all of them
    always satisfies that.
    """

    def beside(fragment: Fragment) -> Scaled:
        left = fragment.line.x
        return max(left - point.x, point.x - (left + fragment.line.width), 0)

    def away(fragment: Fragment) -> Scaled:
        return max(fragment.top - point.y, point.y - fragment.bottom, 0)

    under: Fragment | None = None
    under_by: Scaled = 0
    inside: Fragment | None = None
    inside_by: Scaled = 0
    nearest: Fragment | None = None
    nearest_by: tuple[Scaled, Scaled] = (0, 0)
    for fragment in fragments:
        aside = beside(fragment)
        contains = fragment.top <= point.y < fragment.bottom
        if aside == 0:
            top, bottom = fragment.reach
            if top <= point.y < bottom:
                distance = 0 if contains else away(fragment)
                if under is None or distance < under_by:
                    under, under_by = fragment, distance
        if contains:
            if inside is None or aside < inside_by:
                inside, inside_by = fragment, aside
        elif inside is None and under is None:
            far = (max(fragment.top - point.y, point.y - fragment.bottom), aside)
            if nearest is None or far < nearest_by:
                nearest, nearest_by = fragment, far
    if under is not None:
        return under
    return inside if inside is not None else nearest


def _edges(line: Line, items: Sequence[Item]) -> tuple[Scaled, ...]:
    """
    The left edge of every item on a line, plus the line's right edge.

    An item's right edge is the next item's left edge, so a kern between two
    glyphs belongs to the cell of the glyph before it and no click falls in a gap.
    """
    return (*(item.x for item in items), line.x + line.width)


class FragmentQueries:
    """
    Every selection query, written against two lookups a subclass supplies.

    **Why this is a base class and `SelectionModel` is no longer the whole of
    it.** `SelectionModel` holds one flat tuple of fragments and scans it on
    every call: `fragment_at`, `rects` and `text` are each linear in the
    *document*. That is right for one shipped command list and it is the wrong
    shape for a document laid out as independent units, where a query should
    touch the unit under the mouse or the units a selection covers and nothing
    else. `advtext.ui.units.UnitModel` is that second shape. Rather than write
    hit testing, word expansion, rect derivation and serialisation twice --
    and have the two drift on exactly the cases this module's docstring spends
    its length on -- everything that is a *rule* lives here once, and the two
    models differ only in how they find fragments:

    - `fragment_at(point)`: the line a point belongs to.
    - `fragments_within(start, end)`: every fragment that could contribute to
      the range `[start, end]`, in reading order. It may return more than that
      (the flat model returns all of them); the rules below filter exactly.
    - `length`: how many items the reading order has.

    Nothing here was changed in the move. `tests/test_selection.py` passes
    unedited, which is the evidence for that sentence rather than the sentence
    itself.
    """

    __slots__ = ()

    length: int

    def fragment_at(self, point: Point) -> Fragment | None:
        """
        The line a point belongs to: the one whose band contains it, else the nearest.
        """
        raise NotImplementedError

    def fragments_within(self, start: Boundary, end: Boundary) -> Iterable[Fragment]:
        """
        Fragments that may own or border an item in `[start, end]`, in reading order.

        A superset is allowed and the bounds are *closed* at both ends: `text()`
        asks about a blank line sitting exactly on a boundary, which owns no
        item at all.
        """
        raise NotImplementedError

    # ----------------------------------------------------------------
    # Hit testing
    # ----------------------------------------------------------------

    def hit(self, point: Point) -> Boundary:
        """
        The nearest character boundary to a point.

        Left of a glyph's midpoint gives the boundary before it and right of it
        the boundary after; left of the line gives the line's start and past its
        right edge gives the line's end.
        """
        fragment = self.fragment_at(point)
        if fragment is None:
            return 0
        return self._boundary_in(fragment, point.x)

    def _offset_in(self, fragment: Fragment, x: Scaled) -> int:
        """
        Which of a line's own items sits under `x`, clamped into the line.

        Separate from `_boundary_in` because a double click wants the *item* and
        a caret wants the boundary, and going from one to the other through an
        index is what broke on a line with a nested line in it.
        """
        if x < fragment.edges[0]:
            return 0
        for offset in range(len(fragment.items)):
            if x < fragment.edges[offset + 1]:
                return offset
        return len(fragment.items) - 1

    def _boundary_in(self, fragment: Fragment, x: Scaled) -> Boundary:
        """
        Clamp an x to a boundary inside one line, splitting each item at its midpoint.

        The midpoint test is written as `2 * x < left + right` rather than as a
        division so that it is exact at every coordinate, including the odd sums a
        justified line produces and the negative ones a negative origin does.
        """
        if not fragment.items:
            return fragment.start
        if x < fragment.edges[0]:
            return fragment.indices[0]
        for offset in range(len(fragment.items)):
            left = fragment.edges[offset]
            right = fragment.edges[offset + 1]
            if x < right:
                return fragment.indices[offset] + (0 if 2 * x < left + right else 1)
        return fragment.indices[-1] + 1

    # ----------------------------------------------------------------
    # Ranges
    # ----------------------------------------------------------------

    def select(self, anchor: Boundary, active: Boundary) -> Selection:
        """
        The range between two boundaries, in either order.

        `anchor` is where the drag started and `active` where the pointer is now,
        and swapping them has to give the same range -- the backwards drag. Both
        are clamped into the document, so a drag that ran off the end is a
        selection to the end rather than an index error three frames later.
        """
        low, high = sorted((self._clamp(anchor), self._clamp(active)))
        return Selection(start=low, end=high)

    def select_at(self, anchor: Point, active: Point, granularity: Granularity) -> Selection:
        """
        The range a drag between two points selects at a given granularity.

        At `WORD` and `LINE` the range is the union of the units under each end,
        so a word-granularity drag never cuts a word in half however it is
        extended -- which is the behaviour of a double-click-and-drag everywhere
        and the reason granularity is state rather than a one-shot gesture.
        """
        match granularity:
            case Granularity.CHARACTER:
                return self.select(self.hit(anchor), self.hit(active))
            case Granularity.WORD:
                return self._union(self.word_at(anchor), self.word_at(active))
            case Granularity.LINE:
                return self._union(self.line_at(anchor), self.line_at(active))

    def word_at(self, point: Point) -> Selection:
        """
        The run of like characters under a point: a double click.

        Word characters expand over word characters, spaces over spaces and
        punctuation over punctuation, so "stops at punctuation" holds from both
        sides. A click past the end of a line takes the last unit on that line
        rather than nothing, which is what a double click past the end of a line
        does in an editor.
        """
        fragment = self.fragment_at(point)
        if fragment is None or not fragment.items:
            return (
                Selection(0, 0) if fragment is None else Selection(fragment.start, fragment.start)
            )

        offset = self._offset_in(fragment, point.x)
        wanted = _classify(fragment.items[offset])
        first = offset
        while first > 0 and _classify(fragment.items[first - 1]) is wanted:
            first -= 1
        last = offset
        while last + 1 < len(fragment.items) and _classify(fragment.items[last + 1]) is wanted:
            last += 1
        return Selection(fragment.indices[first], fragment.indices[last] + 1)

    def line_at(self, point: Point) -> Selection:
        """
        The whole visual line under a point: a triple click.

        The *visual* line, not the logical paragraph. A triple click selects what
        the reader is pointing at, and combined with `text()`'s wrap handling it
        copies as one run without the wrap frozen in.
        """
        fragment = self.fragment_at(point)
        if fragment is None:
            return Selection(0, 0)
        return Selection(fragment.start, fragment.end)

    def _union(self, first: Selection, second: Selection) -> Selection:
        """
        The smallest range containing both, which is what extending a drag means.
        """
        return Selection(min(first.start, second.start), max(first.end, second.end))

    def _clamp(self, boundary: Boundary) -> Boundary:
        return max(0, min(self.length, boundary))

    # ----------------------------------------------------------------
    # Drawing and copying
    # ----------------------------------------------------------------

    def rects(self, selection: Selection) -> list[Rect]:
        """
        One rect per line fragment the selection touches.

        A multi-line selection is not one rectangle, and it is not one rectangle
        per line either unless you clip: the first line starts mid-way, the last
        ends mid-way, and every line between them runs from its own left edge to
        its own right edge. An empty selection produces no rects -- a caret is not
        this module's to draw, for the reason the module docstring gives.

        **Fill at the ends of a line is not highlighted.** Glue with no natural
        width is not a space anybody typed: it is the `\\rightskip` that makes
        a line ragged, the `\\parfillskip` after a paragraph's last word, the
        `\\hss` that centres a table cell. Each takes a reading-order index, so
        a selection covers it, and highlighting it painted a bar from the last
        word to the margin on a ragged line and a bar of blank column *before*
        the text of a right-aligned cell. A rectangle now runs from the first
        thing of the selection that is not fill to the last; fill between two
        words -- there is none in what this tree sets -- would still be
        covered.

        **A blank line inside the selection gets no rectangle, and that is a
        decision rather than an oversight.** An empty line owns no items, so it
        has no material to highlight, and its line box has zero width -- there is
        nothing to derive a width *from*. This module has no font and no page
        margin, and inventing either to paint a sliver would be inventing a
        number. A UI that wants a blank selected line to show should extend the
        previous line's rect to its own right margin, because the margin is a
        fact the UI has and the model does not. `text()` is the other half of
        this and does *not* skip the blank line: a line break is representable
        without a width, so there it is emitted.
        """
        if selection.is_empty:
            return []
        rects: list[Rect] = []
        for fragment in self.fragments_within(selection.start, selection.end):
            span = fragment.owned_range(
                max(selection.start, fragment.start), min(selection.end, fragment.end) - 1
            )
            if span is None:
                continue
            low, high = span
            # Fill at either end of the selected stretch is not text and is
            # not highlighted: see the docstring.
            while low <= high and _is_fill(fragment.items[low]):
                low += 1
            while high >= low and _is_fill(fragment.items[high]):
                high -= 1
            if low <= high:
                rects.append(fragment.rect_for(fragment.indices[low], fragment.indices[high]))
        return rects

    def text(
        self,
        selection: Selection,
        *,
        hard_breaks: Collection[int] = (),
        separators: Mapping[int, str] | None = None,
        atoms: Mapping[int, str] | None = None,
        originals: Mapping[int, str] | None = None,
    ) -> str:
        """
        The selected text, for the clipboard.

        **A line break introduced by layout becomes a single space.** A paragraph
        wrapped into five lines is one paragraph; copying it must not freeze this
        column's width into the clipboard, because pasting that anywhere else
        shows the wrap points as ragged hard breaks. The module docstring argues
        this at length.

        **What is content arrives as data.** Nothing in the shipped command
        stream distinguishes a wrap from the end of a paragraph, a code line
        or a table cell, so the layer that built the document says where those
        are. `separators` maps a boundary to the text that belongs *before the
        item at that boundary*: `"\\n"` at the start of each code line,
        `"\\n\\n"` at the start of each block, `"\\t"` at the start of
        each cell after a row's first, `" "` between a list marker and its
        text. It is consulted at every item, not only at the start of a line,
        because a table row that did not wrap is one line holding all its
        cells. `advtext.ui.units.UnitModel` builds the mapping from the
        document's blocks and passes it for you; this flat model has no blocks
        and so, given none, treats every break as a wrap. `hard_breaks` is the
        older, narrower form -- a set of boundaries that each mean `"\\n"` --
        and still works.

        A separator is written only *between* two pieces of selected text: one
        that falls at the very start of the selection is not content of it,
        and neither is one that no selected character follows -- a selection
        that ends on the fill a list item or a table cell begins with.

        **Glue with no natural width is not a space, but it can stand for
        one.** The `\\rightskip` of a ragged line, a `\\parfillskip`, the
        `\\hss` either side of a table cell and the fill before a hard break
        each take a reading-order index and none of them is a space anybody
        typed. At the start or the end of a line, or next to a separator, such
        fill is written as nothing. *Between* two characters on one line -- the
        `\\hss` between two cells of a row, when nobody has said the cells are
        cells -- any amount of it is one space, so that text with no
        separators at all still does not run two words together. Before this a
        copied table came out with two and three spaces between cells and one
        after the last.

        **A blank line does not need a separator and is handled here.** An
        empty line is a `Line` whose `start` equals its `end`, so it is
        self-describing in the command stream in a way a wrap is not, and a
        mapping keyed by boundary could not express it anyway -- all three
        boundaries around it are the same integer. So an empty line strictly
        inside the selection contributes a break of its own. That is the case
        `docs/decisions.md` names: a blank line inside a fenced code block must
        survive a copy. (A line holding only a rule is not a blank line and is
        not a fragment at all; see `_fragments`.)

        **An atom copies as what `atoms` says it is.** An inline formula is one
        item (`advtext.shipout.Atom`) and its text is its source, which the
        commands do not carry: `atoms` maps the item's index to it, dollars
        included. One that is not in the mapping is written as nothing.

        **A glyph copies as what `originals` says was written, where it says
        so.** A character no face has is drawn as U+FFFD
        (`advtext.markdown.ReplacedChar`) and the command for it carries only
        what was drawn: `originals` maps the glyph's index to the character
        the source had. A glyph that is not in the mapping is its own
        codepoint, which is every glyph of nearly every document.

        Joining is tidied rather than mechanical: a wrap adds a space only if
        the text does not already end with white space, and any other
        separator drops the spaces that would have been left dangling before
        it.
        """
        if selection.is_empty:
            return ""
        breaks = frozenset(hard_breaks)
        given: Mapping[int, str] = separators if separators is not None else {}
        named: Mapping[int, str] = atoms if atoms is not None else {}
        written_as: Mapping[int, str] = originals if originals is not None else {}
        pieces: list[str] = []
        # How many of `pieces` there were when the last character was written.
        written = 0

        for fragment in self.fragments_within(selection.start, selection.end):
            if not fragment.items:
                # A blank line. Strictly inside, so a selection that merely ends
                # on one does not pick up a trailing newline.
                if pieces and selection.start < fragment.start < selection.end:
                    _separate(pieces, "\n")
                continue
            span = fragment.owned_range(
                max(selection.start, fragment.start), min(selection.end, fragment.end) - 1
            )
            if span is None:
                continue
            low, high = span
            opening = True
            # Fill seen since the last character, not yet written: it becomes
            # one space if a character follows it on this line, and nothing if
            # a separator or the end of the line does.
            filled = False
            for offset in range(low, high + 1):
                index = fragment.indices[offset]
                item = fragment.items[offset]
                separator = given.get(index)
                if separator is None and index in breaks and index == fragment.start:
                    separator = "\n"
                if separator is None and opening:
                    # The first item of this line's share and nothing said what
                    # precedes it: a wrap.
                    separator = " " if pieces else None
                opening = False
                if separator is not None:
                    if pieces:
                        _separate(pieces, separator)
                    filled = False
                if _is_fill(item):
                    filled = separator is None
                    continue
                if filled:
                    if pieces:
                        _separate(pieces, " ")
                    filled = False
                if isinstance(item, Atom):
                    rendered = named.get(index, "")
                elif index in written_as and isinstance(item, Glyph):
                    rendered = written_as[index]
                else:
                    rendered = _render_item(item)
                if not rendered:
                    # An atom nobody named: there is nothing to write for it.
                    continue
                pieces.append(rendered)
                written = len(pieces)

        # A separator with no character after it is not between two things.
        return "".join(pieces[:written])


@dataclass(frozen=True, slots=True)
class SelectionModel(FragmentQueries):
    """
    A shipped document, indexed once so hit testing is a lookup per frame.

    Built from the `DrawCmd` list `advtext.shipout.ship` returns and holding no
    reference to the box tree, no font and no backend. A UI rebuilds it when the
    layout changes and queries it on every mouse event; the indexing is linear in
    the document and each query after that is linear in one line.
    """

    fragments: tuple[Fragment, ...]
    length: int

    @classmethod
    def from_commands(cls, cmds: Sequence[DrawCmd]) -> SelectionModel:
        """
        Index a shipped command list for hit testing.
        """
        fragments = _fragments(cmds)
        length = max((fragment.end for fragment in fragments), default=0)
        return cls(fragments=fragments, length=length)

    def fragment_at(self, point: Point) -> Fragment | None:
        """
        The line a point belongs to: the one whose band contains it, else the nearest.

        `fragment_nearest` is the rule, shared with every other model so that
        they cannot answer differently.
        """
        return fragment_nearest(self.fragments, point)

    def fragments_within(self, start: Boundary, end: Boundary) -> Iterable[Fragment]:
        """
        Every fragment, whatever the range: the flat model has no index to narrow by.

        Which is the cost `advtext.ui.units.UnitModel` exists to avoid, and is
        exactly what this class did before the lookup had a name.
        """
        return self.fragments


def _is_fill(item: Item) -> bool:
    """
    Whether an item is glue with no natural width: positioning, not a typed space.

    An `Atom` is a `SetGlue` by subclass (so the backends draw nothing for it)
    and is never fill, whatever its width: it is a formula, and one of no
    width -- `${}$`, or `$\\!\\,$` -- is still something the author wrote. It
    used to be taken for fill and dropped from the highlight and from a copy
    (review 2, item 8).
    """
    return isinstance(item, SetGlue) and not isinstance(item, Atom) and item.natural == 0


def _render_item(item: Item) -> str:
    """
    One selected item that is not fill, as text: its character, or a space for a space.
    """
    return " " if isinstance(item, SetGlue) else chr(item.codepoint)


_TRAILING_SPACE: Final = " "


def _separate(pieces: list[str], separator: str) -> None:
    """
    Put a separator after the text so far, in place.

    A single space is a wrap, and adds nothing after white space: the break is
    already there, and a space after a newline would put a stray one at the
    head of the next line. Anything else is content, and takes the place of
    whatever spaces were left dangling before it.
    """
    if separator == _TRAILING_SPACE:
        if not pieces[-1].endswith((_TRAILING_SPACE, "\n", "\t")):
            pieces.append(_TRAILING_SPACE)
        return
    while pieces and not pieces[-1].rstrip(_TRAILING_SPACE):
        pieces.pop()
    if not pieces:
        # Nothing but spaces came before it, so it is not between two things.
        return
    pieces[-1] = pieces[-1].rstrip(_TRAILING_SPACE)
    pieces.append(separator)

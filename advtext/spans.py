r"""
Spans: from a position in a block's material to a position in what was shipped.

Two index spaces meet here and nothing else in the tree connects them.

- **Material indices.** `advtext.markdown.LinkSpan` says "nodes 14 to 31 of this
  block's `material` tuple". That tuple is the breaker's *input*: characters,
  interword glue, font kerns, penalties.
- **Shipped indices.** `advtext.shipout` numbers what a reader can point at -- a
  `Glyph` per character and a `SetGlue` per horizontal glue node -- densely, in
  reading order, over the breaker's *output*. Selection, hit testing and
  highlight rects all live in this space.

They differ in both directions. Material holds things that take no shipped index
(kerns, penalties) and things that never reach ship-out at all (the glue a line
broke at, and the discardable run pruned from the start of the next line). The
shipped sequence holds things that were never in the material: `\rightskip` on
the end of every line, `\leftskip` on the front of every line of a centred or
flush-right block, `\parfillskip` on the last, and a list item's marker box
ahead of its first.

`advtext.shipout`'s docstring used to say a backend "reads `LinkSpan` and
matches it against these indices" and no code did. This is that code. A link's
underline, a per-run colour, a find-in-document highlight and a hover test are
all the same question -- *which shipped items are material `[start, end)`?* --
and `SpanMap.runs` answers it as one index range per line, which is the shape
`advtext.selection.SelectionModel.rects` already turns into rectangles.

**How the two are matched, and why not the obvious way.**

The obvious way is to have the breaker report where it cut. `Paragraph` does
not carry its breakpoints, and the line boxes travel from `advtext.ui`'s
`LayoutCache` as bare `Box` tuples with the `Paragraph` already dropped, so that
route means changing `advtext.linebreak`, the cache's value type and every
caller between them. It is the better design if those files are ever open for
another reason. This module instead recovers the correspondence from the two
sequences, and is exact for the reason below rather than approximately right.

*Characters are anchors.* Nothing in this tree hyphenates -- no `Disc` is ever
produced -- so the breaker neither drops nor invents a character. After the
marker prefix is stepped over, the k-th shipped glyph **is** the k-th `CharNode`
of the material. Every anchor is checked against the glyph it is paired with
(same font key, same codepoint) and a mismatch raises `SpanMapError`, so a map
that comes back at all has had every character verified. A non-empty `Box` in
the material is an anchor the same way, covering as many indices as
`index_count` says it ships -- which for an atom box (`advtext.shipout.is_atom`,
an inline formula) is exactly one, whatever is inside it.

*Glue is settled between anchors, by counting.* `linebreak._line_nodes` builds
every line as one **contiguous slice** of the material with insertions only at
its two ends. So between two anchors:

- on the **same line**, the shipped glue is exactly the material glue, 1:1;
- across a **line break**, the earlier line keeps the first few material glues
  of the gap and then ends with one inserted `\rightskip`; the later line opens
  with `\leftskip` if the block has one and then keeps the last few. Whatever
  is in neither is what the breaker discarded, and maps to nothing;
- before the **first anchor of the block** every material glue survives (there
  is no pruning at a paragraph's start), so anything shipped in excess is the
  inserted lead -- which is how this module learns whether there is a
  `\leftskip` without being handed the `LineBreakParams`;
- after the **last anchor** on the paragraph's last line every remaining
  material glue survives too, except one that is the material's final node,
  which §816 (`linebreak._prepare`) replaces with a penalty.

A line with no anchor on it -- the blank line between two hard breaks -- has
nothing to count against, so its glue is left unmapped. That is correct in every
case this tree produces (such a line holds only inserted glue) and is the stated
limit in any other.

**The result is local to one block.** `SpanMap.base` is the shipped index of the
block's first item, so the same map serves a block shipped alone (phase 2 of
`docs/adoption-plan.md` ships each top-level block separately; base 0 within
its unit) and a block inside a larger shipment. For the second case the caller
needs to know where the block starts, and `index_count` over the line boxes of
the blocks before it is that number.

**What is mapped.**

- `TextBlock`: paragraphs, headings, list items (marker stepped over and
  checked), quotes (the bar's enclosing `Line` is seen through), every
  alignment, hard breaks, a first-line indent box.
- `CodeBlock`: trivially -- one glyph per character, nothing inserted, nothing
  discarded. Material coordinates are a flat index over the lines' nodes;
  `code_position` converts a line and column.
- Bare material against bare lines (`map_material`), with `paragraph=False` for
  a list that was `hpack`ed rather than broken. A table cell today is one.

**What is not, and what happens instead.**

- **Table cells are mapped from the table's box, not from its commands.**
  `map_table` walks the rows and cells of the vbox composition produced and
  maps each cell with `map_material`, wrapped or not. It needs the box, which
  a per-block unit keeps; a caller holding only shipped commands for a table
  cannot map its cells.
- **A taken discretionary.** A hyphen is a character the material does not
  contain. Any `Disc` in the material raises `SpanMapError` rather than
  guessing.
- **A box in the material with glue and no glyph** cannot be located among the
  gap's own glue and raises.
- **Source offsets.** These are material indices, not offsets into the markdown.
  `material_text` gives the block's rendered text with a material index per
  character, which is enough for "highlight every match of this string" and for
  a host that colours by offset into text *it* supplied (a code block's
  source). Markdown-source offsets would need the converter to keep them, and
  it does not.
- **Geometry.** A `ShippedRun` is an index range, not a rectangle. `span_rects`
  hands the ranges to a `SelectionModel` for full-line-height rects -- the same
  mechanism selection highlighting uses, which is what `advtext.shipout`
  promised. An underline wants the baseline as well; that is the `Line.y` of
  the fragment the run falls in, and it is the drawing code's to read.

**Decoration, added by the task this module was a spike for.** `decorate` takes
a block, its map and a `SelectionModel` and returns what a backend draws beside
the glyphs: ink ranges over shipped indices, mark rectangles, underlines, and
one `LinkArea` per link with its rectangles. `ColourSpan` is how a host says
"this stretch of this block, in this colour", in material coordinates;
`colour_text` and `find_spans` say it in text coordinates. It is still only
arithmetic -- the colours are integers nobody here interprets.

No URL handling and no ImGui here: this is index arithmetic over
`advtext.nodes` and `advtext.shipout`, importable without a backend.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

from advtext.markdown import (
    CodeBlock,
    LinkSpan,
    ReplacedChar,
    TableBlock,
    TableCell,
    TextBlock,
)
from advtext.nodes import EJECT_PENALTY, Box, BoxKind, CharNode, Disc, Glue, Node, Penalty
from advtext.selection import Rect, Selection, SelectionModel
from advtext.shipout import Atom, DrawCmd, Glyph, Line, SetGlue, is_atom
from advtext.units import Scaled

__all__ = [
    "ColourSpan",
    "Decoration",
    "FindIndex",
    "LinkArea",
    "MaterialText",
    "ShippedRun",
    "SpanMap",
    "SpanMapError",
    "TextMatch",
    "code_position",
    "colour_text",
    "decorate",
    "find_spans",
    "index_count",
    "map_code_block",
    "map_material",
    "map_table",
    "map_text_block",
    "map_text_boxes",
    "material_text",
    "span_rects",
]

_Sig: TypeAlias = tuple[object, ...]
"""
What one shipped item looks like from either side: `("g", font, codepoint)` for a
glyph, `("s", natural_width)` for a set glue. Enough to tell a character from the
one that should have been there, and deliberately no more -- positions differ
between a box and the commands shipped from it, and identity does not survive
`LayoutCache`, which hands back boxes built from an *equal* block's nodes.
"""

_NO_SIG: Final[_Sig] = ("",)

_GLYPH: Final = "g"
_SPACE: Final = "s"
_ATOM: Final = "a"
"""
An atom box (`advtext.shipout.is_atom`): an inline formula, which ships as one
item whatever is inside it. Its signature is `("a", width)`.
"""


class SpanMapError(ValueError):
    """
    The material and the shipped lines do not describe the same block.

    Raised rather than returning a best effort, because the consumer draws an
    underline or opens a URL from the answer and a map that is silently off by
    one puts both on the wrong word. Causes, in the order they have been seen:
    the commands were shipped from a different block or a different slice of a
    larger shipment; the block was composed by something that prepends more than
    `advtext.ui._hang_marker` does; the material holds a discretionary.
    """


@dataclass(frozen=True, slots=True)
class ShippedRun:
    """
    One line's worth of a span: shipped items `[start, end)`, all on line `line`.

    `start` and `end` are absolute shipped indices (the map's `base` is already
    added), so `Selection(run.start, run.end)` is directly usable against the
    `SelectionModel` built from the same commands. `line` counts the block's own
    lines from zero. A link broken across a line break is two runs with the same
    target; treating them as one link is the caller's, and trivially so, since
    both came from one `runs` call.
    """

    line: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SpanMap:
    """
    One block's material, matched to what was shipped for it.

    `shipped[i]` is the **local** shipped index of material node `i` -- add
    `base` for the absolute one, or use `shipped_index` -- and `None` when the
    node took no index (a kern, a penalty) or never reached ship-out (the glue
    at a break). `extent[i]` is how many consecutive indices it covers: one for
    a character or a glue, more for a box, zero where `shipped[i]` is `None`.

    `lines[j]` is the local half-open index range of the block's j-th line,
    including whatever was inserted on it; `count` is the total, so the next
    block in the same shipment starts at `base + count`.
    """

    base: int
    count: int
    shipped: tuple[int | None, ...]
    extent: tuple[int, ...]
    lines: tuple[tuple[int, int], ...]

    def shipped_index(self, material_index: int) -> int | None:
        """
        The absolute shipped index of one material node, or `None` if it has none.
        """
        local = self.shipped[material_index]
        return None if local is None else self.base + local

    def material_index(self, shipped_index: int) -> int | None:
        """
        Which material node an absolute shipped index came from, or `None`.

        `None` for anything inserted at compose time -- a marker, a line's
        `\\rightskip` -- and for an index outside the block. Linear in the block;
        a caller asking per glyph per frame should build its own table from
        `shipped` once.
        """
        local = shipped_index - self.base
        for index, start in enumerate(self.shipped):
            if start is not None and start <= local < start + self.extent[index]:
                return index
        return None

    def line_of(self, shipped_index: int) -> int | None:
        """
        Which of the block's lines an absolute shipped index is on.
        """
        local = shipped_index - self.base
        for number, (start, end) in enumerate(self.lines):
            if start <= local < end:
                return number
        return None

    def runs(self, start: int, end: int) -> tuple[ShippedRun, ...]:
        """
        The shipped items of material `[start, end)`, one range per line.

        Each run begins and ends on an item of the span itself: it does not
        reach back over a marker or forward into the `\\rightskip`, so an
        underline drawn from it stops at the last letter and not at the margin.
        Discarded material contributes nothing, which is why a span that is
        contiguous in the material comes back as two runs when it straddles a
        break. A span that covers only discarded or indexless nodes is `()`.

        Runs are also split wherever the indices are not consecutive. With the
        line structure this module assumes that never happens inside a line, and
        splitting anyway means a wrong assumption shows up as an extra run
        rather than as a rect over something that was not in the span.
        """
        low, high = max(start, 0), min(end, len(self.shipped))
        indices: list[int] = []
        for index in range(low, high):
            first = self.shipped[index]
            if first is not None:
                indices.extend(range(first, first + self.extent[index]))
        indices.sort()

        runs: list[ShippedRun] = []
        line = 0
        for local in indices:
            while line < len(self.lines) and local >= self.lines[line][1]:
                line += 1
            previous = runs[-1] if runs else None
            if previous is not None and previous.line == line and previous.end == self.base + local:
                runs[-1] = ShippedRun(line, previous.start, previous.end + 1)
            else:
                runs.append(ShippedRun(line, self.base + local, self.base + local + 1))
        return tuple(runs)

    def link_runs(self, link: LinkSpan) -> tuple[ShippedRun, ...]:
        """
        `runs` for one `LinkSpan` of the block this map was built from.
        """
        return self.runs(link.start, link.end)


def span_rects(model: SelectionModel, runs: Iterable[ShippedRun]) -> list[Rect]:
    """
    Full-line-height rectangles for some runs, from the selection model.

    `model` must be built from the same commands the runs index into. This is
    the mechanism selection highlighting already uses, reused rather than
    reimplemented, so a link's hover target and a selection over the same words
    are the same rectangles to the scaled point.
    """
    rects: list[Rect] = []
    for run in runs:
        rects.extend(model.rects(Selection(run.start, run.end)))
    return rects


# ---------------------------------------------------------------------------
# What ships
# ---------------------------------------------------------------------------


def _signatures(node: Node, *, horizontal: bool, out: list[_Sig]) -> None:
    """
    Append the signature of every index `node` takes when shipped, in order.

    The rule is `advtext.shipout`'s and is repeated here rather than imported
    because ship-out exposes it only as a side effect of placing things:
    a `CharNode` takes one, a `Glue` **in a horizontal list** takes one, a box is
    walked. `tests/test_spans.py` holds this against the real `ship` so the two
    cannot drift apart unnoticed.
    """
    match node:
        case CharNode():
            out.append((_GLYPH, node.font, node.codepoint))
        case Glue():
            if horizontal:
                out.append((_SPACE, node.spec.width))
        case Box():
            if horizontal and is_atom(node):
                # One index for the whole box, as ship-out gives it; what is
                # inside takes none. Only in a horizontal list: an atom box
                # that is an item of a vertical list is shipped as a line.
                out.append((_ATOM, node.width))
                return
            inner = node.kind is BoxKind.HLIST
            for child in node.contents:
                _signatures(child, horizontal=inner, out=out)
        case _:
            pass


def index_count(nodes: Node | Iterable[Node]) -> int:
    """
    How many reading-order indices these nodes take when shipped.

    Given the line boxes of a block, this is how far the block advances the
    index -- so the base of block *n* inside a larger shipment is the sum over
    the boxes of blocks `0..n-1`. Interline glue and the kerns between blocks
    sit in a vertical list and take none, so they do not need to be passed.

    A bare sequence is counted as the items of a vertical list: boxes are
    walked, loose glue is not counted.
    """
    out: list[_Sig] = []
    if isinstance(nodes, Iterable):
        for node in nodes:
            _signatures(node, horizontal=False, out=out)
    else:
        _signatures(nodes, horizontal=False, out=out)
    return len(out)


def _line_signatures(boxes: Sequence[Box]) -> list[list[_Sig]]:
    """
    One list of signatures per line box.
    """
    lines: list[list[_Sig]] = []
    for box in boxes:
        out: list[_Sig] = []
        _signatures(box, horizontal=False, out=out)
        lines.append(out)
    return lines


@dataclass(slots=True)
class _LineNode:
    """
    A `Line` command and the lines nested inside it, while grouping commands.
    """

    start: int
    end: int
    own: int
    children: list[_LineNode]


def _paragraph_lines(roots: list[_LineNode]) -> list[_LineNode]:
    """
    The lines that are lines of the paragraph, seen through any wrapper.

    A `Line` is emitted for every hbox that is an item of a vertical list, and
    two shapes in this tree nest them. A block quote is one hbox holding the bar
    and a vbox of the real lines, so an outer `Line` spans the whole quote and
    owns no item itself: it is seen through. A line holding a stacked formula
    has `Line`s *inside* it, and it does own items (at the least its
    `\\rightskip`): it is kept, with the nested items counted as its own.
    """
    found: list[_LineNode] = []
    for node in roots:
        if node.own == 0 and node.children:
            found.extend(_paragraph_lines(node.children))
        else:
            found.append(node)
    return found


def _command_lines(
    cmds: Sequence[DrawCmd], start: int | None, stop: int | None
) -> tuple[int, list[list[_Sig]]]:
    """
    Group shipped commands into paragraph lines of signatures, and find the base.

    `start` and `stop` restrict the commands to one block's index range when
    several blocks were shipped together; a `Line` is kept only if it lies
    inside the range, which drops an enclosing wrapper shared with neighbours.
    """
    low = start if start is not None else 0
    items: dict[int, _Sig] = {}
    roots: list[_LineNode] = []
    stack: list[_LineNode] = []

    def inside(index: int) -> bool:
        return index >= low and (stop is None or index < stop)

    for cmd in cmds:
        match cmd:
            case Line():
                if cmd.start < low or (stop is not None and cmd.end > stop):
                    continue
                while stack and not (stack[-1].start <= cmd.start and cmd.end <= stack[-1].end):
                    stack.pop()
                node = _LineNode(cmd.start, cmd.end, 0, [])
                (stack[-1].children if stack else roots).append(node)
                if cmd.start < cmd.end:
                    stack.append(node)
            case Glyph():
                # A glyph that repeats an atom's index is that formula's ink,
                # not an item: the atom was recorded when it was met.
                if inside(cmd.index) and items.get(cmd.index, _NO_SIG)[0] != _ATOM:
                    items[cmd.index] = (_GLYPH, cmd.font, cmd.codepoint)
                    _count_own(stack, cmd.index)
            case Atom():
                if inside(cmd.index):
                    items[cmd.index] = (_ATOM, cmd.width)
                    _count_own(stack, cmd.index)
            case SetGlue():
                if inside(cmd.index):
                    items[cmd.index] = (_SPACE, cmd.natural)
                    _count_own(stack, cmd.index)
            case _:
                pass

    lines = _paragraph_lines(roots)
    if not items:
        return low, [[] for _ in lines]
    base = min(items)
    covered = sum(node.end - node.start for node in lines)
    if covered != len(items) or any(index not in items for index in range(base, base + covered)):
        raise SpanMapError(
            "the shipped commands are not a whole number of lines: "
            f"{len(items)} pointable items but the lines found cover {covered}. "
            "Pass the commands of one block, or its index range as start/stop."
        )
    return base, [[items[index] for index in range(node.start, node.end)] for node in lines]


def _count_own(stack: list[_LineNode], index: int) -> None:
    """
    Credit one item to the innermost open line that contains it.
    """
    while stack and not (stack[-1].start <= index < stack[-1].end):
        stack.pop()
    if stack:
        stack[-1].own += 1


# ---------------------------------------------------------------------------
# The alignment
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Anchor:
    """
    A material node that is certain to be shipped, and what it ships as.
    """

    index: int
    sigs: tuple[_Sig, ...]
    first_glyph: int


def _anchors(material: Sequence[Node]) -> tuple[list[_Anchor], list[list[int]]]:
    """
    Split material into anchors and the glue between them.

    `gaps[k]` is the material indices of the glue before anchor `k`, in order,
    and `gaps[-1]` is the glue after the last anchor; there is always one more
    gap than there are anchors.
    """
    anchors: list[_Anchor] = []
    gaps: list[list[int]] = [[]]
    for index, node in enumerate(material):
        match node:
            case CharNode():
                anchors.append(_Anchor(index, ((_GLYPH, node.font, node.codepoint),), 0))
                gaps.append([])
            case Glue():
                gaps[-1].append(index)
            case Box():
                sigs: list[_Sig] = []
                # Material is a horizontal list, which is what makes an atom
                # box in it one item; any other box is walked by its own kind.
                _signatures(node, horizontal=True, out=sigs)
                if not sigs:
                    continue
                first = next((k for k, sig in enumerate(sigs) if sig[0] in (_GLYPH, _ATOM)), None)
                if first is None:
                    raise SpanMapError(
                        f"material[{index}] is a box that ships glue and no glyph, so it "
                        "cannot be told apart from the glue around it"
                    )
                anchors.append(_Anchor(index, tuple(sigs), first))
                gaps.append([])
            case Disc():
                raise SpanMapError(
                    f"material[{index}] is a discretionary; a taken break would ship "
                    "characters the material does not contain, and this map does not guess"
                )
            case _:
                pass
    return anchors, gaps


def map_material(
    material: Sequence[Node],
    lines: Sequence[Box],
    *,
    prefix: int = 0,
    paragraph: bool = True,
    base: int = 0,
) -> SpanMap:
    """
    Match a horizontal list against the line boxes it was set into.

    `lines` are the boxes in order, as `advtext.linebreak.break_paragraph`
    returned them or as `advtext.ui` decorated them. `prefix` is the number of
    indices on the first line that precede anything from `material` -- a hung
    marker. `paragraph=False` says the list was packed as it stood rather than
    broken, so its final glue was not replaced by §816's penalty; a table cell
    today is that case, with its `\\hss` showing up as an unmapped lead or tail.

    Raises `SpanMapError` if the two cannot be the same material.
    """
    return _align(material, _line_signatures(lines), prefix, paragraph, base)


def _align(
    material: Sequence[Node],
    lines: list[list[_Sig]],
    prefix: int,
    paragraph: bool,
    base: int,
) -> SpanMap:
    """
    The module docstring's algorithm. Everything else here is an adapter for it.
    """
    anchors, gaps = _anchors(material)

    bounds: list[tuple[int, int]] = []
    flat: list[_Sig] = []
    for line in lines:
        bounds.append((len(flat), len(flat) + len(line)))
        flat.extend(line)
    count = len(flat)
    if prefix > (bounds[0][1] if bounds else 0):
        raise SpanMapError(
            f"a prefix of {prefix} indices does not fit on the first line, which ships "
            f"{bounds[0][1] if bounds else 0}"
        )

    line_at = [number for number, (low, high) in enumerate(bounds) for _ in range(low, high)]
    shipped: list[int | None] = [None] * len(material)
    extent = [0] * len(material)

    # Pass one: place every anchor. `between[k]` is the shipped glue found in
    # the gap before anchor k, and `between[-1]` what follows the last anchor.
    between: list[list[int]] = []
    anchor_lines: list[int] = []
    cursor = prefix
    for anchor in anchors:
        gap: list[int] = []
        while cursor < count and flat[cursor][0] == _SPACE:
            gap.append(cursor)
            cursor += 1
        # A box that opens with glue reclaims that glue from the gap.
        start = cursor - anchor.first_glyph
        if anchor.first_glyph > len(gap):
            raise SpanMapError(
                f"material[{anchor.index}] cannot start {anchor.first_glyph} items before "
                f"shipped index {cursor}"
            )
        if anchor.first_glyph:
            del gap[-anchor.first_glyph :]
        stop = start + len(anchor.sigs)
        if tuple(flat[start:stop]) != anchor.sigs:
            got = flat[cursor] if cursor < count else "the end of the block"
            raise SpanMapError(
                f"material[{anchor.index}] should have shipped as "
                f"{anchor.sigs[anchor.first_glyph]} at local index {cursor}, and what is "
                f"there is {got}"
            )
        if line_at[start] != line_at[stop - 1]:
            raise SpanMapError(f"material[{anchor.index}] is one box shipped across two lines")
        shipped[anchor.index] = start
        extent[anchor.index] = stop - start
        anchor_lines.append(line_at[start])
        between.append(gap)
        cursor = stop
    tail = list(range(cursor, count))
    stray = next((index for index in tail if flat[index][0] == _GLYPH), None)
    if stray is not None:
        raise SpanMapError(
            f"shipped local index {stray} is a glyph {flat[stray]} that no material node "
            "accounts for"
        )
    between.append(tail)

    def on(indices: list[int], line: int) -> list[int]:
        return [index for index in indices if line_at[index] == line]

    def pair(material_glue: list[int], shipped_glue: list[int]) -> None:
        for index, local in zip(material_glue, shipped_glue, strict=True):
            shipped[index] = local
            extent[index] = 1

    if not anchors:
        return SpanMap(base, count, tuple(shipped), tuple(extent), tuple(bounds))

    # The lead: how many inserted glues open every line (`\leftskip`, or a
    # cell's `\hss`). Exact when the block's first line carries an anchor,
    # because nothing is pruned from a paragraph's start; otherwise the smallest
    # lead any anchored line shows, which is exact unless every one of them
    # also kept material glue at its head.
    leading = [len(on(between[k], anchor_lines[k])) for k in range(len(anchors))]
    first_on_line = [
        k for k in range(len(anchors)) if k == 0 or anchor_lines[k - 1] != anchor_lines[k]
    ]
    if anchor_lines[0] == 0:
        lead = leading[0] - len(gaps[0])
        if lead < 0:
            raise SpanMapError(
                f"the block opens with {len(gaps[0])} material glue nodes and only "
                f"{leading[0]} were shipped ahead of its first character"
            )
    else:
        lead = min(leading[k] for k in first_on_line)

    last_line = len(bounds) - 1
    for k in range(len(anchors) + 1):
        glue, found = gaps[k], between[k]
        before = anchor_lines[k - 1] if k > 0 else None
        after = anchor_lines[k] if k < len(anchors) else None

        if before is not None and before == after:
            if len(glue) != len(found):
                raise SpanMapError(
                    f"{len(glue)} material glue nodes sit between two anchors on line "
                    f"{before} and {len(found)} were shipped there"
                )
            pair(glue, found)
            continue

        kept = 0
        if before is not None:
            trailing = on(found, before)
            if after is None and before == last_line:
                # The paragraph's last line runs to the end of the material, so
                # every glue left survives -- bar a final one, which §816 swaps
                # for a penalty before the breaker ever sees it.
                dropped = paragraph and bool(material) and isinstance(material[-1], Glue)
                kept = len(glue) - (1 if dropped and glue else 0)
            else:
                # Every broken line ends with exactly one inserted \rightskip.
                kept = len(trailing) - 1
            if not 0 <= kept <= min(len(glue), len(trailing)):
                raise SpanMapError(
                    f"line {before} ends with {len(trailing)} shipped glue nodes, which "
                    f"cannot hold {kept} of the {len(glue)} in the material there"
                )
            pair(glue[:kept], trailing[:kept])

        if after is not None:
            opening = on(found, after)
            survivors = len(glue) if before is None and after == 0 else len(opening) - lead
            if not 0 <= survivors <= min(len(glue) - kept, len(opening)):
                raise SpanMapError(
                    f"line {after} opens with {len(opening)} shipped glue nodes, of which "
                    f"{lead} are inserted, and the material has {len(glue) - kept} to give"
                )
            if survivors:
                pair(glue[-survivors:], opening[-survivors:])

    return SpanMap(base, count, tuple(shipped), tuple(extent), tuple(bounds))


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _marker_prefix(block: TextBlock, lines: list[list[_Sig]]) -> int:
    """
    How many indices a hung marker puts ahead of the first line, checked.

    `advtext.ui._hang_marker` packs `[\\hss, *marker, kern]` into a box and sets
    it in front of the first line, so the prefix is the marker's own indices
    plus one for the `\\hss`. That is knowledge of another module's layout, and
    it is why the marker's glyphs are compared here: if the hanging ever changes
    shape this raises instead of shifting every link in every list item.
    """
    if not block.marker or not lines:
        return 0
    expected: list[_Sig] = []
    for node in block.marker:
        _signatures(node, horizontal=True, out=expected)
    prefix = 1 + len(expected)
    got = lines[0][1:prefix]
    if lines[0][:1] != [(_SPACE, 0)] or got != expected:
        raise SpanMapError(
            "the block has a marker and its first line does not open with one: expected "
            f"{expected} after a zero-width glue, found {lines[0][:prefix]}"
        )
    return prefix


def map_text_boxes(block: TextBlock, boxes: Sequence[Box], *, base: int = 0) -> SpanMap:
    """
    Map a text block against its own line boxes.

    `boxes` is what `advtext.ui` produced for this block and nothing else: one
    box per line, the first with the marker already hung on it. `base` is where
    the block starts in whatever was shipped; see `index_count`.
    """
    lines = _line_signatures(boxes)
    return _align(block.material, lines, _marker_prefix(block, lines), True, base)


def map_text_block(
    block: TextBlock,
    cmds: Sequence[DrawCmd],
    *,
    start: int | None = None,
    stop: int | None = None,
) -> SpanMap:
    """
    Map a text block against the commands shipped for it.

    With `start` and `stop` left out, `cmds` must be the commands of this block
    alone -- which is what shipping each top-level block separately gives. For a
    block inside a larger shipment (a paragraph of a block quote shares its
    quote's commands) pass the block's absolute index range; `index_count` over
    the line boxes of the blocks before it gives `start`, and over its own gives
    the length.

    The map's `base` is the block's first shipped index as found in `cmds`, so
    `runs` come back in the commands' own index space with nothing to add.
    """
    base, lines = _command_lines(cmds, start, stop)
    return _align(block.material, lines, _marker_prefix(block, lines), True, base)


def map_code_block(block: CodeBlock, *, base: int = 0) -> SpanMap:
    """
    Map a code block, whose material coordinates are a flat index over its lines.

    No commands are needed. A code line is `hpack`ed as it stands and holds
    nothing but characters -- its spaces are `CharNode`s, per
    `advtext.markdown.CodeBlock` -- so nothing is inserted, nothing is discarded
    and the flat index *is* the local shipped index. An empty source line is an
    empty range in `lines`. `code_position` converts a line and a column.
    """
    shipped: list[int | None] = []
    extent: list[int] = []
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for line in block.lines:
        opened = cursor
        for node in line:
            if isinstance(node, CharNode):
                shipped.append(cursor)
                extent.append(1)
                cursor += 1
            else:
                shipped.append(None)
                extent.append(0)
        bounds.append((opened, cursor))
    return SpanMap(base, cursor, tuple(shipped), tuple(extent), tuple(bounds))


def map_table(block: TableBlock, box: Box, *, base: int = 0) -> list[tuple[TableCell, SpanMap]]:
    """
    Map every cell of a table against the box the table was set into.

    `box` is the vbox `advtext.ui` composed for this table alone -- its rows,
    the rule under its header and the interline glue between them -- which is
    what a per-block unit keeps (`advtext.ui.units.Unit.box`). `base` is the
    table's first shipped index. The result has one entry per cell that has
    material, header first, row by row and left to right, which is the order
    the cells' indices ascend in.

    Two row shapes, and they are the two `advtext.ui._table_boxes` builds:

    - a row whose cells all fit is one hbox with a sub-box per cell, the cell's
      material packed as it stands between its padding (`map_material` with
      `paragraph=False`);
    - a row with a wrapped cell has every cell as a stack of line boxes, each
      cell broken like a paragraph (`paragraph=True`).

    Which shape a cell has is read off its box -- a vbox is a stack of lines --
    and not recomputed from widths, so this cannot disagree with composition
    about whether a row wrapped. A row box that does not hold one sub-box per
    column raises `SpanMapError`.
    """
    rows = [block.header, *block.rows] if block.header else list(block.rows)
    row_boxes = [
        node
        for node in box.contents
        if isinstance(node, Box) and any(isinstance(child, Box) for child in node.contents)
    ]
    if len(row_boxes) != len(rows):
        raise SpanMapError(
            f"the table has {len(rows)} rows and its box holds {len(row_boxes)} row boxes"
        )
    mapped: list[tuple[TableCell, SpanMap]] = []
    cursor = base
    for row, row_box in zip(rows, row_boxes, strict=True):
        cell_boxes = [child for child in row_box.contents if isinstance(child, Box)]
        if len(cell_boxes) < len(row):
            raise SpanMapError(
                f"a row of {len(row)} cells was set into {len(cell_boxes)} cell boxes"
            )
        for position, cell_box in enumerate(cell_boxes):
            if position < len(row) and row[position].material:
                cell = row[position]
                if cell_box.kind is BoxKind.VLIST:
                    lines = [child for child in cell_box.contents if isinstance(child, Box)]
                    span_map = map_material(cell.material, lines, base=cursor)
                else:
                    span_map = map_material(cell.material, [cell_box], paragraph=False, base=cursor)
                mapped.append((cell, span_map))
            cursor += index_count(cell_box)
    return mapped


def code_position(block: CodeBlock, line: int, column: int) -> int:
    """
    The flat material index of `column` on `line` of a code block.

    Columns count the block's nodes, which are characters **after tab
    expansion** (`advtext.markdown.TAB_WIDTH`); a host colouring from its own
    tokeniser has to expand tabs the same way or use `material_text`, which
    returns the expanded text. `column` may equal the line's length, for the end
    of a half-open range.
    """
    if not 0 <= line < len(block.lines) or not 0 <= column <= len(block.lines[line]):
        raise IndexError(f"no column {column} on line {line} of this code block")
    return sum(len(earlier) for earlier in block.lines[:line]) + column


# ---------------------------------------------------------------------------
# Text coordinates
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MaterialText:
    """
    A block's characters as a string, and the material index behind each one.

    `indices[k]` is the material index of `text[k]`, or `None` for a character
    that stands for no node (the newline between two code lines). So a match of
    a search string at `text[a:b]` is material `span(a, b)`.
    """

    text: str
    indices: tuple[int | None, ...]

    def span(self, start: int, end: int) -> tuple[int, int] | None:
        """
        The half-open material range behind `text[start:end]`, or `None`.

        `None` when the slice holds no character that came from a node. The
        range runs from the first such character to the last, so anything
        between them that has no character of its own -- a kern, a penalty --
        is inside it, which is what a highlight wants.
        """
        behind = [index for index in self.indices[start:end] if index is not None]
        if not behind:
            return None
        return behind[0], behind[-1] + 1


def material_text(block: TextBlock | CodeBlock) -> MaterialText:
    """
    The text a block sets, with a material index for every character.

    For a `TextBlock`: each `CharNode` is its character -- the one that was
    written, where no face had it and U+FFFD was set
    (`advtext.markdown.ReplacedChar`), so a search for what the source says
    finds it -- and each glue is a space, except glue of zero natural width,
    which is a newline -- in material from `advtext.markdown` the only such
    glue is the fill before a hard break.
    That last rule is a reading of what this tree's converter emits and not a
    property of glue; material built some other way may disagree with it.
    Characters inside a box are not included.

    A forced break with no fill before it is a newline too. That is what a
    hard break is in a block set centred or ragged left
    (`advtext.markdown._fill_and_break` leaves the fill out there), and
    without this the two words either side of one ran together in the text:
    measured, `one two`, a hard break, `three four` in a ragged-left block read
    `one twothree four`, so a search found `twothree` and not `two three`.

    For a `CodeBlock`: the lines joined with newlines, which is the source after
    tab expansion and with trailing blank lines dropped. Indices are the flat
    ones `map_code_block` uses.
    """
    text: list[str] = []
    indices: list[int | None] = []
    match block:
        case TextBlock():
            return _prose_text(block.material)
        case CodeBlock():
            flat = 0
            for number, line in enumerate(block.lines):
                if number:
                    text.append("\n")
                    indices.append(None)
                for node in line:
                    if isinstance(node, CharNode):
                        text.append(_written(node))
                        indices.append(flat)
                    flat += 1
    return MaterialText("".join(text), tuple(indices))


def _written(node: CharNode) -> str:
    """
    The character a node stands for: its own, or the one it replaced.
    """
    return chr(node.original if isinstance(node, ReplacedChar) else node.codepoint)


def replaced_within(material: Sequence[Node]) -> dict[int, str]:
    """
    Material index to the character written, for each node set as a stand-in.

    Empty for nearly every block, and found by one pass that allocates
    nothing when it is. What `advtext.ui.units` maps to shipped indices so
    that a copy returns the character and not the U+FFFD drawn for it.
    """
    return {
        index: chr(node.original)
        for index, node in enumerate(material)
        if isinstance(node, ReplacedChar)
    }


def _prose_text(material: Sequence[Node]) -> MaterialText:
    """
    `material_text` for a paragraph's material, which is also what a table cell holds.
    """
    text: list[str] = []
    indices: list[int | None] = []
    for index, node in enumerate(material):
        if isinstance(node, CharNode):
            text.append(_written(node))
            indices.append(index)
        elif isinstance(node, Glue):
            text.append(" " if node.spec.width else "\n")
            indices.append(index)
        elif isinstance(node, Penalty) and node.value <= EJECT_PENALTY:
            if not text or text[-1] != "\n":
                text.append("\n")
                indices.append(index)
    return MaterialText("".join(text), tuple(indices))


# ---------------------------------------------------------------------------
# Decoration: colour and links, worked out beside the nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ColourSpan:
    """
    A colour for part of one block: an ink for its glyphs, a mark behind them, or both.

    `start` and `end` are **material** indices of the block, half-open -- the
    same coordinates a `LinkSpan` uses. For a code block they are the flat
    indices `code_position` returns, so a tokeniser's `(line, column, length)`
    is `ColourSpan(code_position(b, line, column), code_position(b, line,
    column + length), ink=...)`. For a match in a block's text, `colour_text`
    and `find_spans` convert from offsets into `material_text(block).text`.

    `ink` recolours the glyphs: syntax highlighting. `mark` fills the full line
    height behind them: a find-in-document hit. Neither changes a single
    position -- this is applied when the commands are drawn, and the node model
    and `advtext.shipout.Glyph` stay colourless, as `advtext.markdown` says
    they must.
    """

    start: int
    end: int
    ink: int | None = None
    mark: int | None = None


def colour_text(
    block: TextBlock | CodeBlock,
    start: int,
    end: int,
    *,
    ink: int | None = None,
    mark: int | None = None,
) -> ColourSpan | None:
    """
    A `ColourSpan` for `material_text(block).text[start:end]`, or `None` for nothing.

    Text coordinates in, material coordinates out. `None` when the slice holds
    no character that came from a node -- a slice of nothing but the newline
    between two code lines.
    """
    behind = material_text(block).span(start, end)
    return None if behind is None else ColourSpan(behind[0], behind[1], ink=ink, mark=mark)


def find_spans(
    block: TextBlock | CodeBlock,
    needle: str,
    *,
    ink: int | None = None,
    mark: int | None = None,
    ignore_case: bool = False,
) -> list[ColourSpan]:
    """
    One `ColourSpan` for every occurrence of `needle` in the block's text.

    Find-in-document for one block: non-overlapping matches, left to right, in
    the text `material_text` gives -- which has a space wherever the block has
    an interword glue, so a phrase is found whether or not it was set across a
    line break. An empty needle matches nothing.

    **In a text block a space in the needle also matches a hard break**, and
    the reverse: the two are one character each in the text, a reader sees two
    words on two lines either way, and a search for them should not depend on
    whether the author forced the break (it did: `two three` was not found
    across one). In a code block it does not -- there a line end is content,
    and `a b` is a different thing from `a` at the end of one line and `b` at
    the start of the next.
    """
    if not needle:
        return []
    text = material_text(block)
    haystack, wanted = (
        (text.text.casefold(), needle.casefold()) if ignore_case else (text.text, needle)
    )
    if len(haystack) != len(text.text):
        # Case folding changed a length (a sharp s); offsets would be wrong.
        haystack, wanted = text.text, needle
    if isinstance(block, TextBlock):
        # One character for one character, so every offset still stands.
        haystack, wanted = haystack.replace("\n", " "), wanted.replace("\n", " ")
    spans: list[ColourSpan] = []
    position = haystack.find(wanted)
    while position != -1:
        behind = text.span(position, position + len(wanted))
        if behind is not None:
            spans.append(ColourSpan(behind[0], behind[1], ink=ink, mark=mark))
        position = haystack.find(wanted, position + len(wanted))
    return spans


@dataclass(frozen=True, slots=True)
class TextMatch:
    """
    One occurrence `FindIndex.find` found: material `[start, end)` of a block, or of a cell.

    `block` indexes the blocks the index was built from. With `cell` `None`
    the range is in the block's own material coordinates -- a `ColourSpan`'s,
    so `ColourSpan(match.start, match.end, mark=...)` marks it. For a match
    in a table, `cell` is `(row, column)` and the range is in *that cell's*
    material; `row` counts the header as row zero when the table has one,
    which is the order `map_table` walks.
    """

    block: int
    start: int
    end: int
    cell: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class _Searchable:
    """
    One searchable stretch: a block's text or a cell's, as it stands and case-folded.
    """

    block: int
    cell: tuple[int, int] | None
    text: MaterialText
    plain: str
    folded: str | None
    prose: bool


@dataclass(frozen=True, slots=True)
class FindIndex:
    """
    The text of every block of a document, built once, for find-in-document.

    `find_spans` rebuilds a block's text on every call, which is the whole
    cost of a search (measured by the demo's Find page: 11.5 to 25 ms a
    needle over 740 blocks whatever the match count, against 17 ms to build
    this once). A host with a search box builds one of these when the
    document changes and calls `find` per keystroke.

    **Table cells are in it**, each as its own stretch of text: a match never
    runs from one cell into the next. Text inside a box -- an inline formula
    -- is not, as in `material_text`. A rule and a block the host draws have
    no text here.

    Frozen: it describes the blocks it was built from, and a document that
    changed wants a new one. For a stream that is the whole document again on
    each change; nothing here is incremental.
    """

    entries: tuple[_Searchable, ...]

    @classmethod
    def of(cls, blocks: Sequence[object]) -> FindIndex:
        """
        Index `blocks` (a `Document.blocks`), in order.
        """
        entries: list[_Searchable] = []

        def add(block: int, cell: tuple[int, int] | None, text: MaterialText, prose: bool) -> None:
            # In prose a hard break and a space are one character each and a
            # reader sees two words either way (`find_spans`); one character
            # for one character, so every offset still stands.
            plain = text.text.replace("\n", " ") if prose else text.text
            folded = plain.casefold()
            entries.append(
                _Searchable(
                    block, cell, text, plain, folded if len(folded) == len(plain) else None, prose
                )
            )

        for number, block in enumerate(blocks):
            match block:
                case TextBlock():
                    add(number, None, material_text(block), True)
                case CodeBlock():
                    add(number, None, material_text(block), False)
                case TableBlock():
                    rows = [block.header, *block.rows] if block.header else list(block.rows)
                    for row_number, row in enumerate(rows):
                        for column, cell in enumerate(row):
                            if cell.material:
                                add(number, (row_number, column), _prose_text(cell.material), True)
                case _:
                    pass
        return cls(tuple(entries))

    def find(self, needle: str, *, ignore_case: bool = False) -> tuple[TextMatch, ...]:
        """
        Every non-overlapping occurrence of `needle`, in reading order.

        Block by block, a table's cells row by row and left to right, and
        left to right within each. In a text or code block the matches are
        exactly `find_spans`' for that block, with its rules: a space in the
        needle matches a hard break in prose and not in code, and a stretch
        whose case-folded form has another length (a sharp s) is searched as
        it stands. An empty needle finds nothing.
        """
        if not needle:
            return ()
        folded = needle.casefold()
        spaced, spaced_folded = needle.replace("\n", " "), folded.replace("\n", " ")
        matches: list[TextMatch] = []
        for entry in self.entries:
            if ignore_case and entry.folded is not None:
                haystack, wanted = entry.folded, spaced_folded if entry.prose else folded
            else:
                haystack, wanted = entry.plain, spaced if entry.prose else needle
            position = haystack.find(wanted)
            while position != -1:
                behind = entry.text.span(position, position + len(wanted))
                if behind is not None:
                    matches.append(TextMatch(entry.block, behind[0], behind[1], entry.cell))
                position = haystack.find(wanted, position + len(wanted))
        return tuple(matches)


@dataclass(frozen=True, slots=True)
class LinkArea:
    """
    One link as it was set: where it is, in indices and in rectangles.

    `runs` has one entry per line the link's text landed on and `rects` the
    full-line-height rectangle of each, in the coordinates of the commands the
    map was built from. **A link broken across lines is one `LinkArea` with
    several rects**, so hovering either half is hovering the link and a press
    on one half released on the other is still a click on it.

    `block` and `number` are the caller's name for the block and the position
    of the link in that block's `links`; together they identify the link
    across frames without comparing URLs, two of which may be equal.
    """

    target: str
    block: int
    number: int
    runs: tuple[ShippedRun, ...]
    rects: tuple[Rect, ...]

    def contains(self, x: Scaled, y: Scaled) -> bool:
        """
        Whether a point is on this link's text, on any of its lines.
        """
        return any(
            rect.x <= x < rect.x + rect.width and rect.y <= y < rect.y + rect.height
            for rect in self.rects
        )


@dataclass(frozen=True, slots=True)
class Decoration:
    """
    Everything to draw over and under one block's glyphs that the glyphs do not carry.

    - `inks`: `(start, end, colour)` over **shipped** indices, half-open,
      sorted and non-overlapping. A glyph whose index falls in one is drawn in
      that colour instead of its block's ink.
    - `marks`: filled rectangles behind the text, full line height.
    - `underlines`: thin filled rectangles under link text.
    - `links`: the hover and click targets.

    All in the coordinates and indices of the commands and the
    `SelectionModel` it was built from, so a decoration built from a placed
    unit is in document space and can be handed to the draw call as it is.
    """

    inks: tuple[tuple[int, int, int], ...] = ()
    marks: tuple[tuple[Rect, int], ...] = ()
    underlines: tuple[tuple[Rect, int], ...] = ()
    links: tuple[LinkArea, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.inks or self.marks or self.underlines or self.links)


def _run_rects(model: SelectionModel, runs: Iterable[ShippedRun]) -> Iterator[tuple[Rect, Scaled]]:
    """
    Each run's full-line-height rect and the baseline of the line it is on.

    `span_rects` with the baseline kept, which is the one thing an underline
    needs that a highlight does not. Through the same `Fragment.rect_for` the
    selection highlight uses, so a link's rect and a selection over the same
    words agree to the scaled point.
    """
    for run in runs:
        for fragment in model.fragments_within(run.start, run.end):
            owned = fragment.owned_range(
                max(run.start, fragment.start), min(run.end, fragment.end) - 1
            )
            if owned is not None:
                low, high = owned
                rect = fragment.rect_for(fragment.indices[low], fragment.indices[high])
                yield rect, fragment.line.y


def decorate(
    spans: SpanMap,
    model: SelectionModel,
    *,
    links: Sequence[LinkSpan] = (),
    number: int = 0,
    first_link: int = 0,
    colours: Sequence[ColourSpan] = (),
    link_ink: int | None = None,
    underline: tuple[Scaled, Scaled] = (0, 0),
) -> Decoration:
    """
    One block's colour spans and links, turned into things a backend can draw.

    `spans` is the `SpanMap` of some material -- a text block's, a code
    block's, one table cell's -- and `model` a `SelectionModel` over the same
    commands; both must be in the same index space, and whatever space that
    is, the result is in it too. `links` are that material's own (`TextBlock.
    links`, `TableCell.links`). `number` is the caller's name for the block
    and ends up on each `LinkArea`, whose own `number` counts from
    `first_link` -- so the cells of one table can share a block number and
    still give every link a different name.

    `colours` are the host's, in material coordinates. Where two inks overlap
    the **later one in the sequence wins**, and any of them wins over the link
    ink: a find hit inside a link shows the hit.

    `link_ink` styles the block's links -- their glyphs in that ink, and an
    underline `underline[0]` below the baseline and `underline[1]` thick, in
    the same colour. `None` leaves links unstyled, but their `LinkArea`s are
    still returned: where a link *is* does not depend on whether it is drawn.
    A zero thickness draws no underline.

    A link or a span that covers only material the breaker discarded has no
    runs, and contributes nothing rather than a zero-width rectangle.
    """
    painted: dict[int, int] = {}
    marks: list[tuple[Rect, int]] = []
    underlines: list[tuple[Rect, int]] = []
    areas: list[LinkArea] = []

    offset, thickness = underline
    for position, link in enumerate(links, start=first_link):
        runs = spans.link_runs(link)
        if not runs:
            continue
        rects: list[Rect] = []
        for rect, baseline in _run_rects(model, runs):
            rects.append(rect)
            if link_ink is not None and thickness > 0:
                underlines.append(
                    (
                        Rect(x=rect.x, y=baseline + offset, width=rect.width, height=thickness),
                        link_ink,
                    )
                )
        if link_ink is not None:
            for run in runs:
                for index in range(run.start, run.end):
                    painted[index] = link_ink
        areas.append(LinkArea(link.target, number, position, runs, tuple(rects)))

    for colour in colours:
        runs = spans.runs(colour.start, colour.end)
        if colour.ink is not None:
            for run in runs:
                for index in range(run.start, run.end):
                    painted[index] = colour.ink
        if colour.mark is not None:
            marks.extend((rect, colour.mark) for rect, _ in _run_rects(model, runs))

    inks: list[tuple[int, int, int]] = []
    for index in sorted(painted):
        ink = painted[index]
        if inks and inks[-1][1] == index and inks[-1][2] == ink:
            inks[-1] = (inks[-1][0], index + 1, ink)
        else:
            inks.append((index, index + 1, ink))
    return Decoration(tuple(inks), tuple(marks), tuple(underlines), tuple(areas))

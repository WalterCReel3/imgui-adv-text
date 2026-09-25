r"""
Markdown source in, node lists out.

This module is the front door: it turns a document into the horizontal material
`advtext.linebreak` cuts into lines and `advtext.pack` measures, plus the
vertical structure around it. **It performs no layout.** Nothing here knows how
wide the page is, where a line ends, or where anything lands. It knows what a
run of text is set in and what glue sits between two words, and it stops there.

**Why this is not pptmstr's segmenter.** `pptmstr/ui/blocks.py` hand-writes its
own block parser and uses markdown-it-py only for `parseInline`, because its
tokens arrive from a model a few characters at a time and it must re-render a
half-finished document every frame. A streaming segmenter is the right answer to
that problem and the wrong one to ours: we are handed a whole file. So the
library's block parser is used as well as its inline one, and the cursor
machinery is not copied. pptmstr's `_asterisk_only_emphasis` override *is*
copied, for the reason given at `pptmstr/ui/inline.py:50-74`: CommonMark's
intraword rule protects `foo_bar_baz` but not `__init__`, whose underscore runs
sit at word boundaries and legitimately open a delimiter run. A typography demo
about a Python project that renders `__init__` in bold has a bug in it.

## What comes out

A `Document` of `Block`s, a tagged union of four shapes rather than one with
optional fields, so `match` plus `assert_never` makes a forgotten kind a type
error:

- `TextBlock` -- material for the line breaker, plus the indent it hangs at and
  the marker that sits in the margin. Headings, paragraphs, list items and
  quoted text are all this shape; they differ only in their `BlockStyle`.
- `CodeBlock` -- one node list per source line, already split. A fenced block's
  line endings are content, so it is never line-broken and a long line overflows
  rather than wrapping somewhere the author did not choose.
- `RuleBlock` -- a thematic break.
- `TableBlock` -- cells of horizontal material, with a column alignment each.

**What a consumer still has to do, stated plainly because nothing else says it.**
Two pieces of arithmetic are deliberately left outside this module, both because
they are layout:

1. **Ragged setting.** `BlockStyle.align` is data, not an instruction that has
   been carried out. A block whose align is not `JUSTIFY` is set by giving the
   line breaker a `\rightskip` of `0pt plus 1fil` (and a matching `\leftskip`
   for centred material). Only the breaker can add glue to every line, so only
   the breaker can do it.
2. **Table column widths.** `hpack` each cell to its natural size, take the
   maximum per column, then re-`hpack` every cell in that column to it. That is
   three lines at the call site and it is `hpack` arithmetic, which is why it is
   not here -- this module would have to import a packer and measure, and then
   it would be doing layout.

## Where breaks are legal, and how that shapes what is emitted

`docs/tex-notes.md` §5: a break at glue is legal only when the node before it is
non-discardable. Three consequences are visible in the code below.

- **A run of whitespace collapses to one `Glue`.** Two glue nodes in a row would
  offer a breakpoint between them that leaves a space at the start of the next
  line, and the second would be discarded after the break anyway.
- **Intra-word positions are not decorated with penalties.** A word is a run of
  `CharNode`s and `NORMAL` kerns, and §5 already makes every position in it
  illegal: there is no glue, and a break at a kern needs the kern to be
  `EXPLICIT` *and* followed by glue. Emitting `INF_PENALTY` between every pair of
  letters would be a node per character that changes nothing.
- **An `INF_PENALTY` is emitted where a break would otherwise be legal and is
  not wanted**, which in this document is the space inside an inline code span.
  `advtext.selection` treating `os.path join` as two lines is the kind of wrong
  that survives review because it looks deliberate.

**A `TextBlock`'s material does *not* end with §816's paragraph terminator, and
that is deliberate.** `advtext.linebreak` supplies it: §816 lives in `line_break`
in the source, not in the code that builds the horizontal list, and
`_prepare` there replaces a trailing glue with `INF_PENALTY` and appends
`\parfillskip` before breaking anything. Appending one here as well leaves the
breaker a parfillskip *after* the forced break it already took, which comes out
as a second line holding one glue and nothing else -- a blank line after every
block, and a pointable item that serialises as a stray space. A markdown **hard
break** does still emit those three nodes, because that one is mid-paragraph and
nothing else would produce it.

Deliberately out of scope: images, raw HTML blocks and inline HTML, footnotes,
task lists, nested tables, and colour. The first three are dropped silently
because rendering them is a different project; `docs/decisions.md` sets the
boundary. Links keep their target in a `LinkSpan` rather than a node field,
because the node model has no place for one and adding a colour to `CharNode`
would put presentation in the layout core.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline.emphasis import tokenize as _emphasis_tokenize
from markdown_it.rules_inline.state_inline import StateInline

from advtext.fontmetrics import FontMetrics
from advtext.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    BoxKind,
    CharNode,
    Glue,
    GlueSpec,
    Kern,
    KernKind,
    Node,
    Penalty,
)
from advtext.style import (
    NEUTRAL_SPACE_FACTOR,
    BlockKind,
    BlockStyle,
    Emphasis,
    FontSpec,
    MetricsResolver,
    Theme,
    interword_glue,
    space_factor_after,
)
from advtext.units import UNITY, GlueOrder, Scaled

__all__ = [
    "Block",
    "CodeBlock",
    "ColumnAlign",
    "Document",
    "LinkSpan",
    "RuleBlock",
    "TableBlock",
    "TableCell",
    "TextBlock",
    "build_document",
]

# TeX's \parfillskip: no natural width, and enough stretch to swallow whatever is
# left of the last line. The coefficient is 1 fil; its magnitude is irrelevant as
# long as it is the only infinite stretch in the list, and one point's worth is
# what plain TeX writes.
PARFILLSKIP = GlueSpec(width=0, stretch=UNITY, stretch_order=GlueOrder.FIL)

# A fenced block is not wrapped, so a tab has to become a definite number of
# columns somewhere. Four, because that is what the code in this project's own
# documents uses.
TAB_WIDTH = 4

# Levels below three are set as level three rather than dropped: the litmus
# document needs three, and a level-five heading that renders as body text reads
# as a parser failure.
_HEADING_KINDS = {
    "h1": BlockKind.HEADING_1,
    "h2": BlockKind.HEADING_2,
    "h3": BlockKind.HEADING_3,
}

_BULLET = "•"


class ColumnAlign(enum.Enum):
    """
    A table column's alignment, as the source's `:---:` markers set it.
    """

    LEFT = enum.auto()
    CENTER = enum.auto()
    RIGHT = enum.auto()


_COLUMN_ALIGNS = {
    "text-align:left": ColumnAlign.LEFT,
    "text-align:center": ColumnAlign.CENTER,
    "text-align:right": ColumnAlign.RIGHT,
}


@dataclass(frozen=True, slots=True)
class LinkSpan:
    """
    A link's destination, and the half-open range of material it covers.

    Indices are into the owning block's `material` tuple. Kept beside the nodes
    rather than inside them because `advtext.nodes` is the layout core and a URL
    is not a typographic property -- and because a link's underline or colour is
    the backend's to draw, from this.
    """

    target: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TextBlock:
    """
    Horizontal material for the line breaker, and where it hangs.

    `left_indent` is absolute and already includes every enclosing list and
    quote; it is not added to `style.left_indent` by the caller. `marker` is the
    bullet or number, to be packed naturally and set ending `Theme.marker_gap`
    to the left of `left_indent`, so the text of every item lines up whatever
    the marker's width.
    """

    kind: BlockKind
    style: BlockStyle
    material: tuple[Node, ...]
    links: tuple[LinkSpan, ...] = ()
    marker: tuple[Node, ...] = ()
    left_indent: Scaled = 0
    quote_depth: int = 0


@dataclass(frozen=True, slots=True)
class CodeBlock:
    """
    A fenced or indented block, one node list per source line.

    Already split, and never line-broken: see the module docstring. Spaces
    inside are `CharNode`s of U+0020 rather than glue, which is the one place in
    this document where that is the right answer -- indentation is content, and
    glue would let it stretch.
    """

    style: BlockStyle
    lines: tuple[tuple[Node, ...], ...]
    language: str = ""
    left_indent: Scaled = 0


@dataclass(frozen=True, slots=True)
class RuleBlock:
    """
    A thematic break: a rule as wide as the measure.
    """

    style: BlockStyle
    thickness: Scaled
    left_indent: Scaled = 0


@dataclass(frozen=True, slots=True)
class TableCell:
    """
    One cell's horizontal material, to be packed to its column's width.
    """

    material: tuple[Node, ...]
    links: tuple[LinkSpan, ...] = ()
    header: bool = False


@dataclass(frozen=True, slots=True)
class TableBlock:
    """
    A table, as rows of cells and one alignment per column.

    Column widths are not here; the module docstring says why and what to do.
    `header` is a row like any other and is separated only so a renderer can rule
    under it without counting.
    """

    style: BlockStyle
    header: tuple[TableCell, ...]
    rows: tuple[tuple[TableCell, ...], ...]
    aligns: tuple[ColumnAlign, ...]
    left_indent: Scaled = 0


Block = TextBlock | CodeBlock | RuleBlock | TableBlock
"""
Anything `build_document` produces. A union, so `match` over it is exhaustive.
"""


@dataclass(frozen=True, slots=True)
class Document:
    """
    A whole markdown file, converted.
    """

    blocks: tuple[Block, ...]


def _asterisk_only_emphasis(state: StateInline, silent: bool) -> bool:
    """
    Suppress underscore emphasis, keeping `*`.

    pptmstr's reasoning at `pptmstr/ui/inline.py:50-74` applies unchanged:
    CommonMark's intraword rule already protects `foo_bar_baz`, and does not
    protect `__init__`, because each of its underscore runs sits at a word
    boundary and so may legally flank. The cost is that `_italic_` no longer
    italicises, which is the trade this document wants.
    """
    if state.src[state.pos] == "_":
        return False
    return _emphasis_tokenize(state, silent)


def _build_parser() -> MarkdownIt:
    """
    CommonMark, plus tables, minus underscore emphasis.

    Tables are not CommonMark and have to be enabled explicitly; the litmus test
    requires one (`docs/decisions.md`).
    """
    parser = MarkdownIt("commonmark").enable("table")
    parser.inline.ruler.at("emphasis", _asterisk_only_emphasis)
    return parser


_PARSER = _build_parser()


@dataclass(slots=True)
class _Run:
    """
    Material under construction, with the link spans found so far.

    Mutable on purpose: this is the imperative shell around a pile of immutable
    nodes, and threading an accumulator through twenty append sites would buy
    nothing that the frozen nodes do not already give.
    """

    nodes: list[Node] = field(default_factory=list)
    links: list[LinkSpan] = field(default_factory=list)
    space_factor: int = NEUTRAL_SPACE_FACTOR


class _Converter:
    """
    One pass over one document's token stream.

    Holds the nesting state a flat open/close token stream forces: which lists
    are open and what number each is up to, how deep the quotes go, and the
    marker a list item is waiting to hand to its first paragraph.
    """

    def __init__(self, theme: Theme, resolve: MetricsResolver) -> None:
        self._theme = theme
        self._resolve = resolve
        self._blocks: list[Block] = []
        self._lists: list[_ListState] = []
        self._quote_depth = 0
        self._indent: Scaled = 0
        self._pending_marker: tuple[Node, ...] = ()
        self._heading: BlockKind | None = None

    # -- text to nodes ----------------------------------------------------

    def _metrics_for(self, font: FontSpec) -> FontMetrics:
        return self._resolve(font.key)

    def _append_text(self, run: _Run, text: str, font: FontSpec, breakable: bool) -> None:
        """
        Append one styled run of text as characters, kerns and interword glue.

        `breakable` is false inside an inline code span, where the space still
        gets its natural width but is preceded by an `INF_PENALTY` so the line
        breaker cannot cut a command in half.
        """
        metrics = self._metrics_for(font)
        space_width = round(metrics.space_width)
        index = 0
        length = len(text)
        while index < length:
            character = text[index]
            if character.isspace():
                while index < length and text[index].isspace():
                    index += 1
                if not run.nodes:
                    # Leading space at the start of a block: a break here would be
                    # illegal anyway and the space itself would be discarded.
                    continue
                if not breakable:
                    run.nodes.append(Penalty(INF_PENALTY))
                run.nodes.append(
                    # The theme decides how much of §1044 a sentence space gets;
                    # see `advtext.style.Spacing`. Passing it here rather than
                    # letting `interword_glue` default is what makes the choice
                    # a property of the document being built.
                    Glue(interword_glue(space_width, run.space_factor, self._theme.spacing))
                )
                continue
            run.nodes.append(CharNode(font.key, ord(character)))
            run.space_factor = space_factor_after(character, run.space_factor)
            following = text[index + 1] if index + 1 < length else ""
            if following and not following.isspace():
                kern = round(metrics.kern(ord(character), ord(following)))
                if kern:
                    run.nodes.append(Kern(width=kern, kind=KernKind.NORMAL))
            index += 1

    def _inline(self, kind: BlockKind, tokens: Any) -> _Run:
        """
        One `inline` token's children, flattened into material.

        markdown-it emits emphasis as open/close markers around a flat run of
        text tokens rather than as a tree, so an explicit stack is all that is
        needed and there is no recursion here.
        """
        run = _Run()
        emphasis = Emphasis()
        stack: list[Emphasis] = []
        link_starts: list[tuple[str, int]] = []
        for token in tokens or ():
            match token.type:
                case "text":
                    self._append_text(
                        run, str(token.content), self._theme.font_for(kind, emphasis), True
                    )
                case "code_inline":
                    font = self._theme.font_for(kind, Emphasis(code=True))
                    self._append_text(run, str(token.content), font, False)
                case "strong_open":
                    stack.append(emphasis)
                    emphasis = emphasis.with_(bold=True)
                case "em_open":
                    stack.append(emphasis)
                    emphasis = emphasis.with_(italic=True)
                case "strong_close" | "em_close":
                    emphasis = stack.pop() if stack else Emphasis()
                case "link_open":
                    link_starts.append((str(token.attrs.get("href", "")), len(run.nodes)))
                case "link_close":
                    if link_starts:
                        target, start = link_starts.pop()
                        run.links.append(LinkSpan(target, start, len(run.nodes)))
                case "softbreak":
                    # A source newline inside a paragraph is a space, per
                    # CommonMark. Treating it as a line break would show the
                    # author's wrapping on top of ours.
                    self._append_text(run, " ", self._theme.font_for(kind, emphasis), True)
                case "hardbreak":
                    run.nodes.extend(_fill_and_break())
                case _:
                    # Images, raw HTML and anything else this project does not
                    # render. Dropping the token drops its text with it, which is
                    # the honest outcome for material we cannot set.
                    continue
        return run

    # -- blocks -----------------------------------------------------------

    def _emit_text(self, kind: BlockKind, run: _Run) -> None:
        style = self._theme.style(kind)
        material: list[Node] = []
        if style.first_line_indent:
            material.append(Box(BoxKind.HLIST, width=style.first_line_indent))
        offset = len(material)
        material.extend(run.nodes)
        self._blocks.append(
            TextBlock(
                kind=kind,
                style=style,
                material=tuple(material),
                links=tuple(
                    LinkSpan(link.target, link.start + offset, link.end + offset)
                    for link in run.links
                ),
                marker=self._take_marker(),
                left_indent=self._indent + style.left_indent,
                quote_depth=self._quote_depth,
            )
        )

    def _take_marker(self) -> tuple[Node, ...]:
        marker = self._pending_marker
        self._pending_marker = ()
        return marker

    def _paragraph_kind(self) -> BlockKind:
        """
        What an ordinary paragraph is, given what encloses it.

        A quote wins over a list item: the quote is what a reader sees, and the
        item's indent has already been applied to `self._indent`.
        """
        if self._quote_depth:
            return BlockKind.QUOTE
        if self._lists:
            return self._lists[-1].kind
        return BlockKind.PARAGRAPH

    def _marker_material(self, text: str) -> tuple[Node, ...]:
        run = _Run()
        kind = self._lists[-1].kind if self._lists else BlockKind.PARAGRAPH
        self._append_text(run, text, self._theme.font_for(kind, Emphasis()), False)
        return tuple(run.nodes)

    def _code(self, source: str, language: str) -> None:
        style = self._theme.style(BlockKind.CODE)
        font = style.font
        lines: list[tuple[Node, ...]] = []
        for raw in source.expandtabs(TAB_WIDTH).split("\n"):
            lines.append(tuple(CharNode(font.key, ord(ch)) for ch in raw))
        while lines and not lines[-1]:
            lines.pop()
        self._blocks.append(
            CodeBlock(
                style=style,
                lines=tuple(lines),
                language=language,
                left_indent=self._indent + style.left_indent,
            )
        )

    def _table(self, tokens: list[Any], start: int) -> int:
        """
        Consume one table, returning the index just past its `table_close`.
        """
        style = self._theme.style(BlockKind.TABLE)
        header: list[TableCell] = []
        rows: list[tuple[TableCell, ...]] = []
        aligns: list[ColumnAlign] = []
        row: list[TableCell] = []
        in_header = False
        is_header_cell = False
        index = start + 1
        while index < len(tokens) and tokens[index].type != "table_close":
            token = tokens[index]
            match token.type:
                case "thead_open":
                    in_header = True
                case "thead_close":
                    in_header = False
                case "tr_open":
                    row = []
                case "tr_close":
                    if in_header:
                        header = row
                    else:
                        rows.append(tuple(row))
                case "th_open" | "td_open":
                    is_header_cell = token.type == "th_open"
                    if in_header:
                        aligns.append(
                            _COLUMN_ALIGNS.get(str(token.attrs.get("style", "")), ColumnAlign.LEFT)
                        )
                case "inline":
                    run = self._inline(BlockKind.TABLE, token.children)
                    row.append(
                        TableCell(
                            material=tuple(run.nodes),
                            links=tuple(run.links),
                            header=is_header_cell,
                        )
                    )
            index += 1
        self._blocks.append(
            TableBlock(
                style=style,
                header=tuple(header),
                rows=tuple(rows),
                aligns=tuple(aligns),
                left_indent=self._indent + style.left_indent,
            )
        )
        return index + 1

    # -- the walk ---------------------------------------------------------

    def convert(self, source: str) -> Document:
        """
        Walk the token stream once, emitting a block wherever one closes.
        """
        tokens = list(_PARSER.parse(source))
        index = 0
        while index < len(tokens):
            token = tokens[index]
            match token.type:
                case "heading_open":
                    self._heading = _HEADING_KINDS.get(str(token.tag), BlockKind.HEADING_3)
                case "heading_close":
                    self._heading = None
                case "inline":
                    kind = self._heading or self._paragraph_kind()
                    self._emit_text(kind, self._inline(kind, token.children))
                case "bullet_list_open":
                    self._lists.append(_ListState(BlockKind.BULLET_ITEM))
                    self._indent += self._theme.list_indent
                case "ordered_list_open":
                    self._lists.append(
                        _ListState(BlockKind.ORDERED_ITEM, int(token.attrs.get("start", 1)))
                    )
                    self._indent += self._theme.list_indent
                case "bullet_list_close" | "ordered_list_close":
                    if self._lists:
                        self._lists.pop()
                        self._indent -= self._theme.list_indent
                case "list_item_open":
                    self._pending_marker = self._marker_material(self._next_marker())
                case "blockquote_open":
                    self._quote_depth += 1
                    self._indent += self._theme.quote_indent
                case "blockquote_close":
                    self._quote_depth -= 1
                    self._indent -= self._theme.quote_indent
                case "fence" | "code_block":
                    self._code(str(token.content), str(token.info).strip())
                case "hr":
                    self._blocks.append(
                        RuleBlock(
                            style=self._theme.style(BlockKind.RULE),
                            thickness=self._theme.rule_thickness,
                            left_indent=self._indent,
                        )
                    )
                case "table_open":
                    index = self._table(tokens, index)
                    continue
            index += 1
        return Document(blocks=tuple(self._blocks))

    def _next_marker(self) -> str:
        if not self._lists:
            return _BULLET
        state = self._lists[-1]
        if state.kind is BlockKind.BULLET_ITEM:
            return _BULLET
        text = f"{state.number}."
        state.number += 1
        return text


@dataclass(slots=True)
class _ListState:
    """
    One open list: what its items are, and what number the next one gets.
    """

    kind: BlockKind
    number: int = 1


def _fill_and_break() -> tuple[Node, ...]:
    r"""
    §816's paragraph terminator: fill the rest of the line, then cut it.

    The `INF_PENALTY` stops the breaker cutting before `\parfillskip`, whose
    infinite stretch then absorbs whatever the last line does not use, and the
    `EJECT_PENALTY` forces the break. Without the infinite glue the breaker
    charges the last line for being short and justifies it to the right margin.

    A markdown hard break wants exactly the same three nodes: the only
    difference is that the paragraph carries on afterwards, which the breaker
    does not need to be told.
    """
    return (Penalty(INF_PENALTY), Glue(PARFILLSKIP), Penalty(EJECT_PENALTY))


def build_document(source: str, theme: Theme, resolve: MetricsResolver) -> Document:
    """
    Convert markdown source into blocks of unpacked material.

    `resolve` is how a `FontKey` becomes measurable; `advtext.style` supplies
    `fontlib_metrics` for real fonts and tests supply a fake with round numbers.
    """
    return _Converter(theme, resolve).convert(source)

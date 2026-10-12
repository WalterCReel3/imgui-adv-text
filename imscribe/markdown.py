r"""
Markdown source in, node lists out.

This module is the front door: it turns a document into the horizontal material
`imscribe.linebreak` cuts into lines and `imscribe.pack` measures, plus the
vertical structure around it. **It performs no layout.** Nothing here knows how
wide the page is, where a line ends, or where anything lands. It knows what a
run of text is set in and what glue sits between two words, and it stops there.

**Why this is not pptmstr's segmenter.** `pptmstr/ui/blocks.py` hand-writes its
own block parser and uses markdown-it-py only for `parseInline`, because its
tokens arrive from a model a few characters at a time and it must re-render a
half-finished document every frame. `build_document` has the other problem: it
is handed a whole file. So the library's block parser is used as well as its
inline one, and the cursor machinery is not copied.

**This paragraph used to go further, and that part is withdrawn.** It read "a
streaming segmenter is the right answer to that problem and the wrong one to
ours", and "ours" was true of a demo that opens a file. It is not true of a host
that receives its text a token at a time, and `docs/adoption-plan.md` makes
pptmstr such a host (`docs/decisions.md`, "Adoption"). What still holds is
narrower: *this function* takes a complete source and is not incremental, and
that is not a defect in it. A streaming segmenter belongs **beside**
`build_document`, as a caller that decides which top-level blocks are settled
and hands their source here, rather than as a second block parser. That caller
is `imscribe.stream.StreamDocument`. Nothing in this module streams; what it
gives that caller is `build_document(..., references=False)`, a parse in which
a link reference definition is ordinary text, because a definition is the one
construct in CommonMark by which a later line changes a block that had already
ended.

pptmstr's `_asterisk_only_emphasis` override *is*
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

## Blocks without markdown

`build_document` is not the only way to get a block. A host has text that is
not markdown and must not be parsed as it -- a log line with asterisks in it, a
tool's output, a user's message quoted verbatim -- and until `text_block` and
`code_block` existed its only route to a `TextBlock` was to escape the text and
hope, or to copy `_Converter._append_text`. Both constructors take plain text, a
theme and a resolver and return the same frozen block the converter would have
made, **by running the converter's own methods on it**: the kerning, the
whitespace collapse, the space factor and the tab expansion are one
implementation, and `tests/test_markdown.py` holds the constructors equal to
`build_document` on text where the two should agree.

They return one block each. A host stacks them in a `Document` itself, or beside
blocks that did come from markdown; a `Document` is only a tuple.

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
  `imscribe.selection` treating `os.path join` as two lines is the kind of wrong
  that survives review because it looks deliberate.

**A `TextBlock`'s material does *not* end with §816's paragraph terminator, and
that is deliberate.** `imscribe.linebreak` supplies it: §816 lives in `line_break`
in the source, not in the code that builds the horizontal list, and
`_prepare` there replaces a trailing glue with `INF_PENALTY` and appends
`\parfillskip` before breaking anything. Appending one here as well leaves the
breaker a parfillskip *after* the forced break it already took, which comes out
as a second line holding one glue and nothing else -- a blank line after every
block, and a pointable item that serialises as a stray space. A markdown **hard
break** does still emit those three nodes, because that one is mid-paragraph and
nothing else would produce it -- in a block set justified or ragged right. In a
block set centred or ragged left the fill is left out and only the forced break
is emitted; `_fill_and_break` has the measurement that made that necessary.

## Math, when a caller turns it on

Off by default, and when off nothing below applies: a dollar is a dollar.
`build_document(..., math=builder)` (and `imscribe.stream.StreamDocument`'s
`math=`) switch on two rules and hand what they find to `builder`, a
`MathBuilder`: source, display or not, and the size of the text around it, in;
a packed `Box` or a `MathRefused` out. **The builder is passed in and this
module imports no formula parser** -- `imscribe.mathtext.markdown_math()` is
the one this tree ships, and a host may pass any other.

- **`$...$` inline**, with pandoc's guards so that prices are not math: no
  white space after the opening dollar, none before the closing one, and the
  closing dollar not followed by a digit. Two more, a heuristic of this
  project's so that shell text is not math either: the opening dollar is not
  preceded by a letter or digit and the closing one is not followed by a
  letter, a digit, `{` or `(` (`_math_inline` says what that gives up:
  `$n$th`). `\$` is a literal dollar (the
  ordinary backslash escape, which runs first). A dollar inside a code span or
  a fence is never looked at. `$$...$$` in the middle of a line is the same
  thing set in display style.
- **`$$` as a block**, with a fence's semantics and for a fence's reason
  (`.concerns/lead--demo-review0-findings.md`, D2): a line that is `$$` and
  nothing else opens a display formula that runs to the next such line or to
  the end of the input, and a line that is `$$ ... $$` is one on its own. No
  rule here looks ahead for a closer, because a rule that did would let a
  later line turn an earlier, finished paragraph into part of a formula, and a
  streaming caller has already shown that paragraph as settled. **A block
  whose closing line has not arrived is not typeset**: it is its source so
  far in the code face, opening dollars and all, with no closing dollars
  invented, and its `FormulaSpan` is `unclosed`. A formula read a few
  characters at a time otherwise went from refused to set and back as each
  prefix happened to parse or not (review 2, item 3: three changes of state
  on one sum).

A formula the builder set is **one node**: an atom box
(`imscribe.shipout.atom_box`), on the baseline, which the line breaker cannot
cut and which ships as a single pointable item. A display formula is a
`TextBlock` of the enclosing kind holding that one box, centred. A formula
the builder refused is its source, dollars included, in the code face. Either
way it is recorded in the block's `formulas` (a table cell's, for a cell):
where it is in the material, its source, and the refusal's reason if there was
one. `imscribe.ui.units` reads that to copy a selected formula as its source.

Deliberately out of scope: images, raw HTML blocks and inline HTML, footnotes,
task lists, nested tables, and colour. The first three are dropped silently
because rendering them is a different project; `docs/decisions.md` sets the
boundary. Links keep their target in a `LinkSpan` rather than a node field,
because the node model has no place for one and adding a colour to `CharNode`
would put presentation in the layout core.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, TypeAlias

from markdown_it import MarkdownIt

from imscribe.fontmetrics import Face, FontMetrics

# How markdown is read -- the parser, its rules, the source map -- lives in
# `imscribe.markdown_rules`, which imports nothing of imscribe, so that a reader
# which makes no nodes can share it. Every name that moved there is imported
# back under its own name: `imscribe.markdown.X` is the same object it was.
from imscribe.markdown_rules import _BULLET as _BULLET
from imscribe.markdown_rules import _COLUMN_ALIGNS as _COLUMN_ALIGNS
from imscribe.markdown_rules import _END_IS_OPEN as _END_IS_OPEN
from imscribe.markdown_rules import _MORE_MAY_FOLLOW as _MORE_MAY_FOLLOW
from imscribe.markdown_rules import _PARSER as _PARSER
from imscribe.markdown_rules import _PARSER_WITHOUT_REFERENCES as _PARSER_WITHOUT_REFERENCES
from imscribe.markdown_rules import TAB_WIDTH as TAB_WIDTH
from imscribe.markdown_rules import BlockSource as BlockSource
from imscribe.markdown_rules import ColumnAlign as ColumnAlign
from imscribe.markdown_rules import SourceSpan as SourceSpan
from imscribe.markdown_rules import _asterisk_only_emphasis as _asterisk_only_emphasis
from imscribe.markdown_rules import _build_parser as _build_parser
from imscribe.markdown_rules import _inline_knowing_the_end as _inline_knowing_the_end
from imscribe.markdown_rules import _line_starts as _line_starts
from imscribe.markdown_rules import _math_block as _math_block
from imscribe.markdown_rules import _math_inline as _math_inline
from imscribe.markdown_rules import _parse as _parse
from imscribe.markdown_rules import _parser as _parser
from imscribe.markdown_rules import _span as _span
from imscribe.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    BoxKind,
    CharNode,
    FontKey,
    Glue,
    GlueSpec,
    Kern,
    KernKind,
    Node,
    Penalty,
)
from imscribe.shipout import atom_box
from imscribe.style import (
    NEUTRAL_SPACE_FACTOR,
    Align,
    BlockKind,
    BlockStyle,
    Emphasis,
    FontSpec,
    MetricsResolver,
    Theme,
    font_key,
    interword_glue,
    parse_font_key,
    space_factor_after,
)
from imscribe.units import UNITY, GlueOrder, Scaled

__all__ = [
    "Block",
    "BlockSource",
    "CodeBlock",
    "ColumnAlign",
    "Document",
    "FormulaSpan",
    "LinkSpan",
    "MathBuilder",
    "MathRefused",
    "REPLACEMENT_CHARACTER",
    "ReplacedChar",
    "RuleBlock",
    "SourceSpan",
    "TableBlock",
    "TableCell",
    "TextBlock",
    "build_document",
    "code_block",
    "formula_spans",
    "replaced_characters",
    "text_block",
]

# TeX's \parfillskip: no natural width, and enough stretch to swallow whatever is
# left of the last line. The coefficient is 1 fil; its magnitude is irrelevant as
# long as it is the only infinite stretch in the list, and one point's worth is
# what plain TeX writes.
PARFILLSKIP = GlueSpec(width=0, stretch=UNITY, stretch_order=GlueOrder.FIL)

# All six levels CommonMark has. Levels four to six used to be set as level
# three; `imscribe.style`'s docstring says what they are set as now and why. The
# fallback in `convert` is still level three and is unreachable: markdown-it
# emits no heading tag outside this table.
_HEADING_KINDS = {
    "h1": BlockKind.HEADING_1,
    "h2": BlockKind.HEADING_2,
    "h3": BlockKind.HEADING_3,
    "h4": BlockKind.HEADING_4,
    "h5": BlockKind.HEADING_5,
    "h6": BlockKind.HEADING_6,
}

REPLACEMENT_CHARACTER = 0xFFFD
"""
U+FFFD, set in place of a character no face of the theme has a glyph for.

See `_stand_in`. `replaced_characters` counts them in a block.
"""


@dataclass(frozen=True, slots=True)
class ReplacedChar(CharNode):
    """
    A `CharNode` that stands for a character no face of the theme has.

    `font` and `codepoint` are what is *set* -- U+FFFD in the prose face, or
    `?` (`_stand_in`) -- and `original` is the codepoint that was *written*.
    Everything that measures, breaks, packs or ships sees an ordinary
    `CharNode`, which is what it is. What reads a document as text asks for
    `original`: `imscribe.spans.material_text` (and so find), and a copy,
    through `imscribe.ui.units.UnitModel.originals_within`.

    **Why on the node and not beside the block.** C-hostfix sketched a
    per-block map from node index to character. A stream cuts a code block
    and a table into pieces (`imscribe.stream`), a view cuts a table by rows,
    and each cut would have to re-base such a map or drop it; a node carries
    its original through every one of them untouched, and two blocks compare
    equal exactly when they would copy the same.
    """

    original: int = 0


def _char_node(theme: Theme, resolve: MetricsResolver, key: FontKey, codepoint: int) -> CharNode:
    """
    The node for a character its own face lacks: borrowed, replaced, or left.

    `_stand_in` decides; this only remembers what was written when what is
    set is another character.
    """
    font, shown = _stand_in(theme, resolve, key, codepoint)
    if shown == codepoint:
        return CharNode(font, shown)
    return ReplacedChar(font, shown, codepoint)


# General categories that are never stood in for: controls and format
# characters draw nothing by design (a zero-width joiner, a soft hyphen, a
# variation selector), and a combining mark the face lacks has no base to be
# replaced on.
_DRAWN_AS_NOTHING_ON_PURPOSE = frozenset({"Cc", "Cf", "Mn", "Me"})


def _stand_in(
    theme: Theme, resolve: MetricsResolver, key: FontKey, codepoint: int
) -> tuple[FontKey, int]:
    """
    What to set for a character the face of `key` has no glyph for.

    Called only for such a character, so text a face covers pays one `has`
    per character and is otherwise untouched: its material is the material it
    always was, node for node (`tests/test_markdown.py` holds that for
    `demo/sample.md`).

    **Why.** A `CharNode` for a glyph its face lacks measures as nothing and
    draws as nothing. The code face shipped here has no Greek and the prose
    face has no arrows, so `π` in inline code and `→` in a paragraph were
    gaps (C-page-math measured it; review 2, item 5b).

    **The rule** (the lead's decision): the same character in the first of
    the theme's other faces that has it, at the same size -- the prose face
    (`Faces.regular`), then the math face, then the code face. If none has
    it, `REPLACEMENT_CHARACTER` in the prose face, or `?` if that face has no
    U+FFFD either, so the reader sees that something was there.

    Consequences a host should know, none of them hidden:

    - A character borrowed from the prose or math face in a code span or a
      code block has that face's advance, not the code face's, and moves the
      columns after it on its line.
    - Borrowing from the math face makes a document with no formula in it
      need `Face.MATH` loaded (`imscribe.ui.fonts`: `ALL_FACES`).
    - A borrowed character is the character still, and copies as itself. A
      *replaced* one is U+FFFD on the page and **still copies, and is found,
      as the character that was written**: its node is a `ReplacedChar`,
      which keeps it.
    - No kern is set after a character that was stood in for.

    White space, controls, format characters and combining marks are left as
    they were (`_DRAWN_AS_NOTHING_ON_PURPOSE`). A resolver that does not know
    a face -- a test's fake, a host with no math face -- is skipped, not an
    error: bare `Exception`, because the resolver is the caller's code.
    """
    character = chr(codepoint)
    if character.isspace() or unicodedata.category(character) in _DRAWN_AS_NOTHING_ON_PURPOSE:
        return key, codepoint
    try:
        bound = parse_font_key(key)
    except ValueError:
        return key, codepoint
    prose: tuple[FontKey, FontMetrics] | None = None
    for face in dict.fromkeys((theme.faces.regular, Face.MATH, theme.faces.code)):
        other = key if face is bound.face else font_key(face, bound.size)
        try:
            metrics = resolve(other)
        except Exception:
            continue
        if face is theme.faces.regular:
            prose = (other, metrics)
        if face is not bound.face and metrics.has(codepoint):
            return other, codepoint
    if prose is not None:
        for stand in (REPLACEMENT_CHARACTER, ord("?")):
            if prose[1].has(stand):
                return prose[0], stand
    return key, codepoint


@dataclass(frozen=True, slots=True)
class LinkSpan:
    """
    A link's destination, and the half-open range of material it covers.

    Indices are into the owning block's `material` tuple. Kept beside the nodes
    rather than inside them because `imscribe.nodes` is the layout core and a URL
    is not a typographic property -- and because a link's underline or colour is
    the backend's to draw, from this.
    """

    target: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class FormulaSpan:
    """
    One `$...$` of a block: where it is in the material, and what it was.

    `start` and `end` are a half-open range of the owning block's (or table
    cell's) `material`, as a `LinkSpan`'s are. A formula that was set is one
    node there, an atom box, so its range is one wide. One the builder refused
    is its source in the code face, and the range covers those characters;
    `refusal` is then the builder's reason and `position` the offset into
    `source` it pointed at. `refusal` is empty for a formula that was set,
    which is how to tell the two apart.

    In the block and not beside it, unlike a source span: it is content. Two
    paragraphs that differ in a formula's source differ in their boxes.
    """

    source: str
    start: int
    end: int
    display: bool = False
    refusal: str = ""
    position: int = 0
    unclosed: bool = False
    """
    A `$$` block whose closing line has not been read: source so far, not a formula.

    Never set and never offered to the builder; `refusal` then says only
    that. A host listing what was refused skips these, or says "still being
    written" -- nothing is wrong with the source yet.
    """

    @property
    def text(self) -> str:
        """
        The formula as it was written, dollars included: what a copy of it gives.

        An unclosed block has no closing dollars, here as on the page.
        """
        marker = "$$" if self.display else "$"
        return f"{marker}{self.source}" if self.unclosed else f"{marker}{self.source}{marker}"

    @property
    def index(self) -> int:
        """
        The material index of the formula's box. Meaningful when it was set.
        """
        return self.start


_UNCLOSED = "the display block has not been closed yet"


@dataclass(frozen=True, slots=True)
class MathRefused:
    """
    A `MathBuilder`'s other answer: this source is not a formula it can set.

    `reason` is one sentence for a person and `position` an offset into the
    source. The converter sets the source as code and keeps both on the
    block's `FormulaSpan`.
    """

    reason: str
    position: int = 0


MathBuilder: TypeAlias = Callable[[str, bool, Scaled], "Box | MathRefused"]
"""
What turns a formula's source into a box: `(source, display, size) -> Box | MathRefused`.

`source` is the text between the dollars. `display` is true for `$$`. `size`
is the size of the text the formula sits in, in scaled points -- a heading's
formula is asked for at the heading's size. The box comes back at its natural
width with its reference point on the baseline, and whoever later measures and
ships the document must be able to resolve the font keys inside it
(`imscribe.style.fontlib_metrics` resolves the math face's). Called once for
every formula every time its block is converted, which for the last block of
a stream is every time text arrives: a builder should remember what it built.
It must not raise.
"""


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
    formulas: tuple[FormulaSpan, ...] = ()


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
    formulas: tuple[FormulaSpan, ...] = ()


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

    `sources` runs parallel to `blocks` -- `sources[i]` is where `blocks[i]`
    came from -- and is empty for a document assembled by hand from
    `text_block` and `code_block`, which has no markdown source to point into.

    **Beside the blocks, not in them, and that is deliberate.** Composition
    caches by block *value* (`imscribe.ui.LayoutCache`,
    `imscribe.ui.units.UnitCache`). A source position inside the block would
    make two identical paragraphs different keys, and would make every block
    below an inserted line a cache miss although nothing about its layout had
    changed. Kept here, an edit moves the spans and re-breaks nothing.
    """

    blocks: tuple[Block, ...]
    sources: tuple[BlockSource, ...] = ()

    def source_of(self, block: int) -> BlockSource | None:
        """
        Where `blocks[block]` came from, or `None` if this document records no sources.
        """
        if 0 <= block < len(self.sources):
            return self.sources[block]
        return None


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
    formulas: list[FormulaSpan] = field(default_factory=list)


class _Converter:
    """
    One pass over one document's token stream.

    Holds the nesting state a flat open/close token stream forces: which lists
    are open and what number each is up to, how deep the quotes go, and the
    marker a list item is waiting to hand to its first paragraph.
    """

    def __init__(
        self,
        theme: Theme,
        resolve: MetricsResolver,
        parser: MarkdownIt = _PARSER,
        math: MathBuilder | None = None,
    ) -> None:
        self._theme = theme
        self._resolve = resolve
        self._parser = parser
        self._math = math
        self._blocks: list[Block] = []
        self._sources: list[BlockSource] = []
        self._lists: list[_ListState] = []
        self._quote_depth = 0
        self._indent: Scaled = 0
        self._pending_marker: tuple[Node, ...] = ()
        self._heading: BlockKind | None = None
        self._heading_span: SourceSpan | None = None
        self._next = 0
        self._marked: tuple[int, _WalkState | None] = (0, None)

    # -- text to nodes ----------------------------------------------------

    def _metrics_for(self, font: FontSpec) -> FontMetrics:
        return self._resolve(font.key)

    def _append_text(self, run: _Run, text: str, font: FontSpec, breakable: bool) -> None:
        """
        Append one styled run of text as characters, kerns and interword glue.

        `breakable` is false inside an inline code span, where the space still
        gets its natural width but is preceded by an `INF_PENALTY` so the line
        breaker cannot cut a command in half.

        A character the face has no glyph for is set from another face of the
        theme, or as U+FFFD: `_stand_in` has the rule.
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
                    # see `imscribe.style.Spacing`. Passing it here rather than
                    # letting `interword_glue` default is what makes the choice
                    # a property of the document being built.
                    Glue(interword_glue(space_width, run.space_factor, self._theme.spacing))
                )
                continue
            codepoint = ord(character)
            if metrics.has(codepoint):
                run.nodes.append(CharNode(font.key, codepoint))
                covered = True
            else:
                run.nodes.append(_char_node(self._theme, self._resolve, font.key, codepoint))
                covered = False
            run.space_factor = space_factor_after(character, run.space_factor)
            following = text[index + 1] if index + 1 < length else ""
            if covered and following and not following.isspace():
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
                    _unskip(run, link_starts)
                    run.nodes.extend(_fill_and_break(self._theme.style(kind).align))
                case "math_inline":
                    self._formula(
                        run, kind, emphasis, str(token.content), token.markup == "$$", False
                    )
                case _:
                    # Images, raw HTML and anything else this project does not
                    # render. Dropping the token drops its text with it, which is
                    # the honest outcome for material we cannot set.
                    continue
        return run

    def _formula(
        self,
        run: _Run,
        kind: BlockKind,
        emphasis: Emphasis,
        source: str,
        display: bool,
        breakable: bool,
    ) -> None:
        """
        One formula into a run: the builder's box as a single node, or its source as code.

        The box goes in as an atom (`imscribe.shipout.atom_box`): one node the
        breaker cannot cut, one item when shipped. After it the space factor
        is neutral again, as it is after any box in TeX (§1076), so a formula
        that ends a sentence is followed by an ordinary space and not by
        whatever the last character before the formula would have earned.

        A refusal sets the source with its dollars in the code face -- the
        reader sees what was written and that it was meant as math -- and the
        span records why. `breakable` is for a display formula, whose source
        may be long and is a block of its own; an inline one is kept whole
        as an inline code span is.
        """
        start = len(run.nodes)
        font = self._theme.font_for(kind, emphasis)
        built = (
            self._math(source, display, font.size)
            if self._math is not None
            else MathRefused("no formula builder was given")
        )
        if isinstance(built, MathRefused):
            span = FormulaSpan(source, start, start, display)
            code = self._theme.font_for(kind, Emphasis(code=True))
            self._append_text(run, span.text, code, breakable)
            run.formulas.append(
                replace(span, end=len(run.nodes), refusal=built.reason, position=built.position)
            )
            return
        run.nodes.append(atom_box(built))
        run.space_factor = NEUTRAL_SPACE_FACTOR
        run.formulas.append(FormulaSpan(source, start, start + 1, display))

    def _display_math(self, source: str, closed: bool = True) -> None:
        """
        A `$$` block: one centred block holding the formula and nothing else.

        **Only a closed block is handed to the builder.** One whose closing
        `$$` line has not been read is set as what there is of it -- `$$` and
        the source so far, in the code face, nothing after it -- and recorded
        as a span that is `unclosed`. The builder is not asked, so a prefix
        that happens to be a formula (`\\sum_{k=0}` on the way to
        `\\sum_{k=0}^{\\infty}`) is not shown set and then unset again, and
        no reason is recorded for a refusal nobody made. In a whole file an
        unclosed block runs to the end and stays source, which is what a
        reader of the file sees too: a `$$` that was never closed.

        The block is of whatever kind a paragraph here would be, so it takes
        that kind's spacing, indent and quote bar; only its alignment and its
        first-line indent are its own. Centring is the block's `align` and is
        done where every other alignment is, in composition, so this stays
        material and no layout. A formula wider than the measure is not
        scaled or broken: it overhangs, like a long line of code.
        """
        kind = self._paragraph_kind()
        style = replace(self._theme.style(kind), align=Align.CENTER, first_line_indent=0)
        run = _Run()
        source = " ".join(source.split())
        if closed:
            self._formula(run, kind, Emphasis(), source, True, True)
        else:
            code = self._theme.font_for(kind, Emphasis(code=True))
            self._append_text(run, f"$${source}", code, True)
            run.formulas.append(
                FormulaSpan(source, 0, len(run.nodes), True, _UNCLOSED, unclosed=True)
            )
        self._blocks.append(
            TextBlock(
                kind=kind,
                style=style,
                material=tuple(run.nodes),
                marker=self._take_marker(),
                left_indent=self._indent + style.left_indent,
                quote_depth=self._quote_depth,
                formulas=tuple(run.formulas),
            )
        )

    # -- blocks -----------------------------------------------------------

    def _emit_text(self, kind: BlockKind, run: _Run) -> None:
        self._blocks.append(self._text_block(kind, run))

    def _text_block(self, kind: BlockKind, run: _Run) -> TextBlock:
        """
        A finished run as a block, taking the pending marker and the nesting state.

        Separate from `_emit_text` so that `text_block` below can have the block
        without a document to put it in. This is the only place a `TextBlock` is
        constructed.
        """
        style = self._theme.style(kind)
        material: list[Node] = []
        if style.first_line_indent:
            material.append(Box(BoxKind.HLIST, width=style.first_line_indent))
        offset = len(material)
        material.extend(run.nodes)
        return TextBlock(
            kind=kind,
            style=style,
            material=tuple(material),
            links=tuple(
                LinkSpan(link.target, link.start + offset, link.end + offset) for link in run.links
            ),
            marker=self._take_marker(),
            left_indent=self._indent + style.left_indent,
            quote_depth=self._quote_depth,
            formulas=tuple(
                replace(span, start=span.start + offset, end=span.end + offset)
                for span in run.formulas
            ),
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

    def _marker_material(self, text: str, kind: BlockKind | None = None) -> tuple[Node, ...]:
        """
        A list marker's nodes, in the face of the item it hangs beside.

        `kind` is for `text_block`, which has no open list to ask; the walk
        leaves it out and gets the innermost open list's kind, as it always did.
        """
        run = _Run()
        if kind is None:
            kind = self._lists[-1].kind if self._lists else BlockKind.PARAGRAPH
        self._append_text(run, text, self._theme.font_for(kind, Emphasis()), False)
        return tuple(run.nodes)

    def _code(self, source: str, language: str) -> None:
        self._blocks.append(self._code_block(source, language))

    def _code_block(self, source: str, language: str) -> CodeBlock:
        """
        Source text as a block of unbroken lines. The only place a `CodeBlock` is made.
        """
        style = self._theme.style(BlockKind.CODE)
        lines = _code_lines(source, style.font.key, self._theme, self._resolve)
        while lines and not lines[-1]:
            lines.pop()
        return CodeBlock(
            style=style,
            lines=tuple(lines),
            language=language,
            left_indent=self._indent + style.left_indent,
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
                            formulas=tuple(run.formulas),
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

    def convert(self, source: str, more_may_follow: bool = False) -> Document:
        """
        Walk the token stream once, emitting a block wherever one closes.
        """
        tokens = _parse(self._parser, source, more_may_follow)
        return self._walk(tokens, source, _line_starts(source))

    def _walk(
        self,
        tokens: list[Any],
        source: str,
        lines: list[int],
        *,
        first: int = 0,
        top: SourceSpan | None = None,
        mark: int = -1,
    ) -> Document:
        """
        `convert`, from token `first` on, for a caller that already has the tokens.

        `first` and `top` are for a walk picked up part of the way through a
        document (`_convert`): the tokens before `first` are taken as handled,
        by a converter whose state was put back with `_restore`, and `top` is
        the top-level block the walk is then inside. `mark` is a token index
        at which to note how many blocks have been emitted and what the
        nesting state is, in `_marked`, so that a later walk can be picked up
        there in turn.
        """
        index = first
        while index < len(tokens):
            if index == mark:
                self._marked = (len(self._blocks), self._snapshot())
            token = tokens[index]
            # The source map, kept beside the walk rather than inside it: a
            # token at nesting level zero that carries a line range opens a
            # top-level block, and whatever blocks are emitted while handling
            # one token came from that token's own lines. Every emitting token
            # (`inline`, `fence`, `code_block`, `hr`, `table_open`) has a map.
            if token.level == 0 and token.map:
                top = _span(token.map, lines, source)
            emitted = len(self._blocks)
            own = _span(token.map, lines, source) if token.map else top
            if token.type == "heading_open":
                # A heading's text is an `inline` token mapped to the text's
                # lines only. A setext heading has an underline as well, and
                # `heading_open` is the one token whose range includes it
                # (review 3, item 6: the span of `Title`, `=====` was `Title`).
                self._heading_span = own if token.map else None
            elif token.type == "inline" and self._heading_span is not None:
                own = self._heading_span
            self._handle(tokens, index)
            if own is not None:
                for _ in range(len(self._blocks) - emitted):
                    self._sources.append(BlockSource(span=own, top=top or own))
            index = self._next
        if mark == len(tokens):
            self._marked = (len(self._blocks), self._snapshot())
        return Document(blocks=tuple(self._blocks), sources=tuple(self._sources))

    def _snapshot(self) -> _WalkState:
        return _WalkState(
            lists=tuple((state.kind, state.number) for state in self._lists),
            quote_depth=self._quote_depth,
            indent=self._indent,
            pending_marker=self._pending_marker,
        )

    def _restore(self, state: _WalkState) -> None:
        self._lists = [_ListState(kind, number) for kind, number in state.lists]
        self._quote_depth = state.quote_depth
        self._indent = state.indent
        self._pending_marker = state.pending_marker

    def _handle(self, tokens: list[Any], index: int) -> None:
        """
        One token of the walk. Sets `_next` to the index to continue from.
        """
        token = tokens[index]
        self._next = index + 1
        match token.type:
            case "heading_open":
                self._heading = _HEADING_KINDS.get(str(token.tag), BlockKind.HEADING_3)
            case "heading_close":
                self._heading = None
                self._heading_span = None
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
            case "list_item_close":
                # An item that emitted no text block -- an empty one, or one
                # holding only a fence -- still has its marker waiting. Left
                # there it was taken by the next paragraph in the document,
                # outside the list (review 3, item 1, measured: `- a`, `-`, a
                # blank line and `para` set `para` with a bullet). The item is
                # over; nothing after it is what the marker was for.
                self._pending_marker = ()
            case "blockquote_open":
                self._quote_depth += 1
                self._indent += self._theme.quote_indent
            case "blockquote_close":
                self._quote_depth -= 1
                self._indent -= self._theme.quote_indent
            case "fence" | "code_block":
                self._code(str(token.content), str(token.info).strip())
            case "math_block":
                self._display_math(str(token.content), bool((token.meta or {}).get("closed", True)))
            case "hr":
                self._blocks.append(
                    RuleBlock(
                        style=self._theme.style(BlockKind.RULE),
                        thickness=self._theme.rule_thickness,
                        left_indent=self._indent,
                    )
                )
            case "table_open":
                self._next = self._table(tokens, index)

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


def _unskip(run: _Run, link_starts: list[tuple[str, int]]) -> None:
    r"""
    TeX's `\unskip`: drop the interword glue a run ends with, before a forced break.

    **The defect this closes was measured, not supposed.** A backslash hard
    break keeps the space the author typed before it -- `aaa bbb \` and a
    newline -- so the run ended `b, Glue, INF_PENALTY, fil Glue, EJECT_PENALTY`.
    That trailing glue follows a character and is therefore a legal breakpoint
    (`docs/tex-notes.md` section 5). Whenever the words fitted the line but the
    words *plus that space* did not, the breaker's only feasible move was to
    break at the space, and the forced break then ended a line with nothing on
    it. With this module's test metrics, where `aaa bbb` is 68 wide and a space
    is 8, that happened at a measure of 68 or 69 justified and from 68 to 73
    ragged, where there is no shrink to hide it: three lines, the middle one
    empty. `tests/test_markdown.py` rebuilds the old material and shows it.

    plain TeX's `\\` and LaTeX's `\newline` both `\unskip` first, for this
    reason. The two-space form of a markdown hard break never had the problem,
    because markdown-it strips those spaces from the text before the break; the
    paragraph's own end never had it either, because `imscribe.linebreak._prepare`
    removes a trailing glue before appending `\parfillskip`, which is section
    816's own unskip.

    A glue that came from inside an unbreakable code span is preceded by an
    `INF_PENALTY`, and that goes with it: it guarded a space that is no longer
    there, and `_fill_and_break` begins with one of its own.

    Link spans are indices into the same list, so one that ended on a removed
    node is pulled back to the new end, and a link *opened* after the removed
    glue starts there. Without that a link's range would run on into the three
    break nodes that are about to be appended.
    """
    nodes = run.nodes
    while nodes and isinstance(nodes[-1], Glue):
        nodes.pop()
        if nodes and isinstance(nodes[-1], Penalty) and nodes[-1].value >= INF_PENALTY:
            nodes.pop()
    end = len(nodes)
    run.links[:] = [
        link if link.end <= end else LinkSpan(link.target, min(link.start, end), end)
        for link in run.links
    ]
    link_starts[:] = [(target, min(start, end)) for target, start in link_starts]


def _fill_and_break(align: Align) -> tuple[Node, ...]:
    r"""
    §816's paragraph terminator: fill the rest of the line, then cut it.

    The `INF_PENALTY` stops the breaker cutting before `\parfillskip`, whose
    infinite stretch then absorbs whatever the last line does not use, and the
    `EJECT_PENALTY` forces the break. Without the infinite glue the breaker
    charges the last line for being short and justifies it to the right margin.

    A markdown hard break wants exactly the same three nodes: the only
    difference is that the paragraph carries on afterwards, which the breaker
    does not need to be told.

    **Except in a block set ragged left or centred, where the fill is left out
    and the forced break stands alone.** Measured before this took an argument
    (review 2, item 3): `aaa`, a hard break, `bbb`, a hard break, `ccc`, set
    `Align.RIGHT` at 225.8 pt with the real fonts, put the first glyphs of the
    three lines at 103.1, 102.8 and 206.9 pt. Only the last line was at the
    right margin. Those alignments are a `\leftskip` of `1fil` on every line
    (`imscribe.ui._skips`), and the fill here is `1fil` too, so the two shared
    the slack equally and the line sat halfway. `PARFILLSKIP`'s comment said
    its magnitude does not matter "as long as it is the only infinite stretch
    in the list"; in these two alignments it is not the only one.

    Plain TeX's own answer is the same omission: `\raggedleft` and `\centering`
    set `\parfillskip` to zero, because the skips already dispose of the slack
    and a second infinite glue can only take some of it away from them. With no
    fill the line before a hard break is `\leftskip`, the words, `\rightskip`,
    and is placed exactly as every other line of the block is.

    A justified block needs the fill, and a ragged-right one is indifferent to
    it (the fill and its `\rightskip` are both at the right-hand end). Both
    keep it, so that the two differ in nothing but their style: that is what
    lets `imscribe.stream` set a block ragged while it is being written and
    justified once it is finished without building its material twice over in
    two shapes.
    """
    if align in (Align.RIGHT, Align.CENTER):
        return (Penalty(EJECT_PENALTY),)
    return (Penalty(INF_PENALTY), Glue(PARFILLSKIP), Penalty(EJECT_PENALTY))


def _newlines(text: str) -> str:
    r"""
    `text` with `\r\n` and a lone `\r` each turned into `\n`.

    What markdown-it does to a source before it reads it, done for the two
    constructors that never go near markdown-it. Without it `code_block` set a
    carriage return as a *character* at the end of every line of a file with
    Windows line ends (measured: `"a\r\nb\r\n"` gave lines of code points
    `[97, 13]` and `[98, 13]`), and a host cannot be expected to know that it
    had to strip them first.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


_NO_EMPHASIS = Emphasis()
"""
The default emphasis of `text_block`, named so the signature builds no instance.
"""


def text_block(
    text: str,
    theme: Theme,
    resolve: MetricsResolver,
    *,
    kind: BlockKind = BlockKind.PARAGRAPH,
    emphasis: Emphasis = _NO_EMPHASIS,
    hard_breaks: bool = False,
    marker: str = "",
    indent: Scaled = 0,
    quote_depth: int = 0,
) -> TextBlock:
    r"""
    Plain text as one block of breakable material, with no markdown read out of it.

    `text` is set exactly as written: an asterisk is an asterisk and a backtick
    is a backtick. (Line ends are the one thing read out of it: `\r\n` and a
    lone `\r` are newlines, as they are to markdown.) `kind` chooses the
    `BlockStyle` -- any kind whose block is text, so a heading is
    `kind=BlockKind.HEADING_2` -- and `emphasis` the face within it, through
    `Theme.font_for` as the converter does it. One emphasis for the whole
    block: text with runs in several faces is what markdown is for.

    **Newlines.** By default every run of whitespace, newlines included, is one
    interword space -- CommonMark's rule for a paragraph, and the right one for
    text that was wrapped by whoever produced it. With `hard_breaks=True` each
    newline ends the line there, with the same nodes a markdown hard break
    emits, and the text carries on below; whitespace either side of the
    newline is dropped, and so are newlines at the very start and end. A blank
    line in the middle sets a blank line. This is still **one block**: a host
    that wants paragraph spacing between two paragraphs makes two blocks.

    `marker` is hung in the margin as a list marker is ("•", "3.", or anything
    else), set in the same face the converter would use for `kind`. `indent` is
    what encloses the block -- one `theme.list_indent` per list level, one
    `theme.quote_indent` per quote -- and the style's own `left_indent` is added
    to it, as it is for a block that came from markdown. `quote_depth` is how
    many quote bars a renderer draws beside it. None of the three is inferred
    from `kind`: a `BULLET_ITEM` with no marker and no indent is a paragraph in
    a list item's spacing, which is occasionally what is wanted.

    `resolve` must be the resolver the block will be measured with later, for
    the reason `build_document` gives: the kerns are computed here and baked in.
    """
    if kind in (BlockKind.CODE, BlockKind.RULE, BlockKind.TABLE):
        raise ValueError(
            f"{kind.name} is not a kind of text block; use code_block for code, "
            "and build_document for a rule or a table"
        )
    converter = _Converter(theme, resolve)
    converter._indent = indent
    converter._quote_depth = quote_depth
    if marker:
        converter._pending_marker = converter._marker_material(marker, kind)
    font = theme.font_for(kind, emphasis)
    run = _Run()
    text = _newlines(text)
    if hard_breaks:
        # Stripped first so a trailing newline does not become a forced break
        # with nothing after it: the line breaker appends its own terminator and
        # the two together would set an empty last line.
        for number, line in enumerate(text.strip().split("\n")):
            if number:
                run.nodes.extend(_fill_and_break(theme.style(kind).align))
            converter._append_text(run, line.strip(), font, True)
    else:
        converter._append_text(run, text.strip(), font, True)
    return converter._text_block(kind, run)


def code_block(
    source: str,
    theme: Theme,
    resolve: MetricsResolver,
    *,
    language: str = "",
    indent: Scaled = 0,
) -> CodeBlock:
    """
    Source text as a block of lines that are never broken, as a fenced block is.

    For anything whose line endings and spacing are content: code, a diff, a
    table drawn in characters, a tool's output. One line of `source` is one line
    of the block, whether it ends in `\n`, `\r\n` or a lone `\r`; a tab advances
    to the next multiple of `TAB_WIDTH` columns;
    trailing blank lines are dropped and interior ones kept. That is the fenced
    block's own treatment because it is the fenced block's own code.

    `language` is carried on the block and not interpreted -- nothing in this
    project highlights -- and is where a host that does would look. `indent` is
    what encloses the block, as for `text_block`; the code style's own indent is
    added to it.

    `resolve` is unused today, because a code line's nodes are characters with
    no kerns and no glue and so need no measurement to build. It is in the
    signature so the two constructors are called the same way and so that
    kerning code, should a face ever want it, is not a breaking change.
    """
    converter = _Converter(theme, resolve)
    converter._indent = indent
    return converter._code_block(_newlines(source), language)


def _code_lines(
    source: str,
    key: FontKey,
    theme: Theme | None = None,
    resolve: MetricsResolver | None = None,
) -> list[tuple[Node, ...]]:
    r"""
    Code as one tuple of characters per source line, blank lines at the end kept.

    One entry for every line of `source`, whether or not its last line ends in
    a newline; none for the empty string. A tab advances to the next multiple of
    `TAB_WIDTH` columns, counted from the start of its own line, so converting
    lines one at a time gives what converting them together does. That, and
    keeping the trailing blank lines `CodeBlock` drops, is what lets
    `imscribe.stream` convert a fence that is still being written a few lines at
    a time and put the pieces end to end.

    With `theme` and `resolve`, a character the code face has no glyph for is
    set from another face or as U+FFFD (`_stand_in`), one character at a time
    and so the same whichever way the lines were cut. Without them -- a
    caller that has no resolver -- every character is the code face's, as it
    was before that rule existed.
    """
    pieces = source.expandtabs(TAB_WIDTH).split("\n")
    if not pieces[-1]:
        pieces.pop()
    if theme is None or resolve is None:
        return [tuple(CharNode(key, ord(character)) for character in piece) for piece in pieces]
    metrics = resolve(key)
    chosen: dict[str, CharNode] = {}
    lines: list[tuple[Node, ...]] = []
    for piece in pieces:
        line: list[Node] = []
        for character in piece:
            node = chosen.get(character)
            if node is None:
                codepoint = ord(character)
                if metrics.has(codepoint):
                    node = CharNode(key, codepoint)
                else:
                    node = _char_node(theme, resolve, key, codepoint)
                chosen[character] = node
            line.append(node)
        lines.append(tuple(line))
    return lines


@dataclass(frozen=True, slots=True)
class _Fence:
    """
    What `_leading_fence` found: a fence's lines, its info string, and whether it ended.
    """

    lines: list[tuple[Node, ...]]
    language: str
    closed: bool
    end: int = 0
    outer_end: int = 0
    last: bool = True


def _leading_fence(
    source: str,
    theme: Theme,
    shape: tuple[tuple[str, str], ...] = (),
    *,
    verbatim: bool = False,
    math: bool = False,
    resolve: MetricsResolver | None = None,
) -> _Fence | None:
    r"""
    The fenced block `source` begins with, if its first line opens one at top level.

    With `shape`, `source` begins instead with an opener line (`_Resume`) for
    the containers a fence is inside, and the fence asked about is the one its
    *second* line opens: the first block after the opener's thematic break,
    whatever list items or quotes that second line itself opens on the way.
    `None` if the opener was not read as `shape`.

    `verbatim` leaves an unfinished last line as it is instead of ending or
    dropping it, and the caller reads three more things off the result: `end`
    and `outer_end`, the line the fence's range and its outermost container's
    range stop at, and `last`, whether the fence is the last block there is.
    That is for a fence inside a container, where the paragraph below about an
    unfinished line is not true. Measured: `> ~~~`, `> `, and an unended `>`
    give a fence of lines 0 to 2 inside a quote of lines 0 to 3 -- the last
    line is the quote's and not the fence's -- while the same three lines with
    a newline at the end give a fence of 0 to 3. And an unfinished line that
    is not indented far enough is not in the fence or the container at all.
    So there the parser is asked about the text exactly as it stands.

    For `imscribe.stream`, which asks two things `build_document` cannot answer
    because a `CodeBlock` does not record them: whether the fence has met its
    closing line, and how many lines it has *including* blank ones at its end
    (a block drops those, and a fence still being written may yet put text
    after them). `None` when the first top-level block is anything else.

    The parser answers, not a reading of backticks done here: which line closes
    a fence depends on its indent, its length, its character and what trails
    it, and a first line that looks like an opener can be a table's header row
    (the table rule runs first: `~~~a|b` over `-|-` is a table). markdown-it
    records neither fact directly. A fence token's line range ends after the
    closing line when there is one and after the last content line when there
    is not (`markdown_it/rules_block/fence.py`: `state.line = nextLine + (1 if
    haveEndMarker else 0)`), so a range one line longer than opener plus content
    is a closed fence. That reading of the rule was checked against the
    installed markdown-it-py and is pinned by `tests/test_markdown.py`; it is
    not part of the library's documented interface.

    **An unfinished last line is given its newline first, or left off.** With
    every line ended, the count of content lines is the count of newlines in
    the content, which is what the comparison above needs; without that, a
    fence whose unfinished last line is empty once its indent is stripped
    counts one line short and reads as closed. A last line with something on
    it is the same line to the block parser with a newline or without. One of
    only spaces and tabs is not, and this was found by the stream's property
    test rather than expected: markdown-it's line scanner
    (`StateBlock.__init__`) records a line when it meets a newline or the last
    character, but skips leading whitespace before it looks, so an unended line
    that is all whitespace is never recorded and is no line at all. It is
    dropped here to match.

    Read with reference definitions off, as the stream reads everything, and
    with the math rules on when `math` is, so that this is the parser the rest
    of the stream is reading with. **No source is known for which that changes
    the answer here**: a `$$` line inside a fence is a line of code to both
    parsers, and no fence opener is a math opener. A test that swapped the
    plain parser back in passed the whole math corpus
    (`tests/test_mathinline.py`), three sources written to catch it included.
    It is passed anyway because the lines *after* a fence in a container do
    read differently in the two (a `$$` line is a lazy continuation to one
    and the end of the quote to the other), and `outer_end` and `last` are
    read off those.

    `resolve` is the document's resolver, for the one thing here that needs a
    font: a character the code face lacks is stood in for (`_code_lines`),
    and a stream's lines must be the lines `build_document` makes.
    """
    unfinished = source[source.rfind("\n") + 1 :]
    if unfinished and not verbatim:
        source = source + "\n" if unfinished.strip(" \t") else source[: -len(unfinished)]
    tokens = _parse(_parser(False, math), source)
    index = 0
    if shape:
        if not _opens(tokens, shape):
            return None
        index = len(shape)
        # Between the break and the fence: the opener's own item closing when
        # the fence's line starts a new one, and whatever that line opens. Not
        # the outermost container closing, though -- a fence after that is in
        # some other top-level block, and not the one being resumed.
        while index < len(tokens) and (
            tokens[index].type in _CONTAINER_OPENS
            or (tokens[index].type in _CONTAINER_CLOSES and tokens[index].level > 0)
        ):
            index += 1
    if index >= len(tokens):
        return None
    token = tokens[index]
    if token.type != "fence" or not token.map or token.map[0] != (1 if shape else 0):
        return None
    if not shape and token.level != 0:
        return None
    lines = _code_lines(str(token.content), theme.style(BlockKind.CODE).font.key, theme, resolve)
    return _Fence(
        lines=lines,
        language=str(token.info).strip(),
        closed=int(token.map[1]) - int(token.map[0]) > len(lines) + 1,
        end=int(token.map[1]),
        outer_end=int(tokens[0].map[1]) if tokens[0].map else 0,
        last=all(later.type in _CONTAINER_CLOSES for later in tokens[index + 1 :]),
    )


@dataclass(frozen=True, slots=True)
class _WalkState:
    """
    Everything `_Converter` carries from one token to the next, between two blocks.

    Which lists are open and what number each has reached, how deep the quotes
    go, the indent those add up to, and the marker an item is still waiting to
    hand to a paragraph. A converter given this back (`_Converter._restore`)
    emits, for the tokens that follow, what the converter it was taken from
    would have. The heading state is not here because a snapshot is only ever
    taken between blocks, where there is none.
    """

    lists: tuple[tuple[BlockKind, int], ...]
    quote_depth: int
    indent: Scaled
    pending_marker: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class _Resume:
    r"""
    A line inside an unfinished container from which its source can be parsed alone.

    For `imscribe.stream`, and the whole of what lets it stop re-reading a long
    list every time the list grows. `_resume_point` has the argument; this is
    what it returns.

    `line` is a line of the source the tokens came from. `opener` is one line
    of markdown, newline included, that puts a parser where the real one was at
    the start of that line: the same quotes and list items open, at the same
    columns, with a thematic break as the only thing in the innermost. So
    `opener + source_from_line` parses to the containers, the break, and then
    exactly what the whole source has from `line` on. `shape` is the type and
    markup of each token the opener must produce, break last, which is what a
    caller checks before believing that (`_opens`). `mark` is the index, among
    the tokens `_resume_point` was given, of the first one that the lines from
    `line` on produce: the blocks emitted before it are settled, and the
    converter's state there is the state to resume with.
    """

    line: int
    opener: str
    shape: tuple[tuple[str, str], ...]
    mark: int


_CONTAINER_OPENS = frozenset(
    {"bullet_list_open", "ordered_list_open", "list_item_open", "blockquote_open"}
)
_CONTAINER_CLOSES = frozenset(
    {"bullet_list_close", "ordered_list_close", "list_item_close", "blockquote_close"}
)

_ITEM_OPENER = re.compile(r"( {0,3})(\d{1,9}[.)]|[-+*])( *)")
_QUOTE_OPENER = re.compile(r" {0,3}> ?")


def _tokens(source: str, math: bool = False, more_may_follow: bool = False) -> list[Any]:
    """
    markdown-it's tokens for `source`, reference definitions off, unconverted.

    Split from conversion for `imscribe.stream`, which reads the tokens for
    where a parse can be resumed and may convert the one list twice, once in
    each of its two themes. `more_may_follow` is `build_document`'s.
    """
    return _parse(_parser(False, math), source, more_may_follow)


def _convert(
    tokens: list[Any],
    source: str,
    starts: list[int],
    theme: Theme,
    resolve: MetricsResolver,
    *,
    first: int = 0,
    state: _WalkState | None = None,
    mark: int = -1,
    math: MathBuilder | None = None,
) -> tuple[Document, int, _WalkState | None]:
    """
    `tokens` as blocks, optionally from part of the way in, noting the state at `mark`.

    With `state`, the tokens before `first` are an opener's (`_Resume.opener`)
    and are not converted: the walk begins at `first` in the nesting `state`
    records, inside the top-level block the first token opens. Spans are in
    `source`'s own lines and characters; a caller that parsed an opener and a
    suffix moves them itself.

    Returns the document, and how many of its blocks had been emitted when the
    walk reached token `mark`, with the state it was in there (zero and `None`
    when it never did).
    """
    converter = _Converter(theme, resolve, _parser(False, math is not None), math)
    top: SourceSpan | None = None
    if state is not None:
        converter._restore(state)
        top = _span(tokens[0].map, starts, source)
    document = converter._walk(tokens, source, starts, first=first, top=top, mark=mark)
    count, marked = converter._marked
    return document, count, marked


def _opens(tokens: list[Any], shape: tuple[tuple[str, str], ...]) -> bool:
    """
    Whether `tokens` begin with exactly the containers and the break an opener is for.

    The check that an opener was read as what it was written to be. When this
    is false the caller parses the whole source instead, which is always
    right.

    **No source is known that makes it false.** The rule that could take an
    opener for something else is the table rule, which runs before every other
    and claims a first line whose second looks like a delimiter row; but it
    also needs a pipe in that first line (`markdown_it/rules_block/table.py`,
    `if "|" not in lineText`), and no opener has one. The fuzz runs recorded
    in `.concerns/AF-streamcost--builder--result.md` refused none. It stays
    because it is six comparisons and what it guards against is silent: tokens
    converted from the wrong nesting.
    """
    count = len(shape)
    if len(tokens) < count:
        return False
    for level, (kind, markup) in enumerate(shape[:-1]):
        token = tokens[level]
        if token.type != kind or token.markup != markup or token.level != level:
            return False
    last = tokens[count - 1]
    return bool(
        last.type == "hr" and last.level == count - 1 and last.map and list(last.map) == [0, 1]
    )


def _resume_point(
    tokens: list[Any], source: str, starts: list[int], skip: int = 0
) -> _Resume | None:
    r"""
    The latest line of `source` from which its unfinished first block can be re-read alone.

    `source` must end at a line end, and `tokens` are its tokens. `skip` is how
    many of them at the front are an opener's, when `source` itself began with
    one. `None` when the source's first top-level block is not a list or a
    quote that everything after it is still inside, or when no opener could be
    written for where it has got to.

    **What this is for.** `imscribe.stream` commits a top-level block when the
    next one starts, and until then re-parses it whole on every read. A list is
    one top-level block however long, and so is a block quote (measured before
    this existed, mean cost of a four-character piece near the end: 43 ms for a
    list of 300 items, 16 ms for a quote of 150 paragraphs). What has been
    converted of such a block cannot be *committed* early, because its `top`
    span is still growing; but it need not be parsed or converted again.

    **The line.** The last block-level token that is a direct child of its
    container -- a paragraph, a heading, a fence, a table, a rule, a raw HTML
    block -- starts on some line. Everything emitted before that line is
    settled by the same argument the stream's own boundary rests on, applied
    inside the container: block structure is decided line by line, a finished
    line cannot be taken back, and a later line can extend, convert or split
    only the block being written. So the source is re-read from that line.
    When the last such token is a fence that has met its closing line, the
    line is the one *after* the closing line: nothing reaches back into a
    closed fence, and without this every piece of the line after a long code
    block inside a list item would re-read the whole of it.

    **The opener.** Re-reading from a line in the middle of a container needs
    the container open. The lines themselves cannot do it: the second paragraph
    of a list item, read alone, is an indented paragraph or a code block (the
    construct `docs/adoption-plan.md` rules a blank-line scanner out with). So
    one line is written in front that opens the same containers at the same
    columns, each list item by its own marker and padding, each quote by `> `,
    with a thematic break as the innermost's content: a break because it is a
    whole block in three characters that nothing after it can continue,
    extend or attach to. markdown-it itself treats the columns a marker covers
    as spaces once the item is open (`StateBlock.getLines`: "patched tShift
    masked characters to look like spaces"), so a later line of the item sees
    the same thing above it either way. Where the line to resume at starts a
    *new item* of a list, the list is opened with a marker padded by four
    spaces: a sibling item may be indented up to three columns, and an opener
    padded by one would take such a line as its own content (found by reading
    the list rule, not by a failing test).

    **What is inferred and what is checked.** That the opener leaves the parser
    in the state the real source did is an argument from reading
    `markdown_it/rules_block/list.py`, `blockquote.py` and `state_block.py` in
    the installed 4.2.0, not a theorem. Two things stand behind it. A caller
    verifies with `_opens` that the opener was read as the containers it names
    before using anything that follows, and falls back to the whole parse when
    not. And the result is compared with one parse of the whole source: from
    every line of sixteen nested sources in `tests/test_markdown.py`, and after
    every piece of the stream's corpus in `tests/test_stream.py`. **That
    comparison, run over generated documents, found two mistakes in the first
    version** (an inner item's indent written where the outer marker's padding
    absorbed it, in `_opener`; and the unfinished line under a quoted fence,
    in `_leading_fence`), so it can fail, and a construct it has not been
    shown is untested rather than safe.
    Tabs are not reasoned about at all: an opening line with a tab in it gets
    no opener, and the block is re-parsed whole as before.
    """
    stack: list[int] = []
    leaf = -1
    chain: tuple[int, ...] = ()
    for index, token in enumerate(tokens):
        kind = token.type
        if kind in _CONTAINER_OPENS:
            stack.append(index)
        elif kind in _CONTAINER_CLOSES:
            stack.pop()
        elif index >= skip and token.nesting >= 0 and token.map and token.level == len(stack):
            leaf = index
            chain = tuple(stack)
    if leaf < 0 or not chain or chain[0] != 0 or int(tokens[0].map[0]) != 0:
        return None
    token = tokens[leaf]
    begin, end = int(token.map[0]), int(token.map[1])
    if token.type == "fence" and end - begin > str(token.content).count("\n") + 1:
        line, mark, spine = end, leaf + 1, chain
    else:
        line = begin
        depth = 0
        while depth < len(chain) and int(tokens[chain[depth]].map[0]) < line:
            depth += 1
        mark = chain[depth] if depth < len(chain) else leaf
        spine = chain[:depth]
    if not spine:
        return None
    written = _opener(tokens, spine, source, starts)
    if written is None:
        return None
    opener, shape = written
    return _Resume(line=line, opener=opener, shape=shape, mark=mark)


def _opener(
    tokens: list[Any], spine: tuple[int, ...], source: str, starts: list[int]
) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    """
    One line that opens the containers `spine` indexes, and the tokens it should give.

    Each list item's marker, indent and padding are read off the line the item
    opens on, after stepping over what the containers outside it put on that
    line: the same text when they open on that line too, their continuation --
    an item's width in spaces, a quote's `>` -- when they opened earlier. A
    list at the end of the spine with no item is one about to take a new item
    (`_resume_point` says why it is padded by four). `None` whenever a line is
    not laid out the way this expects, tabs included.
    """
    pieces: list[str] = []
    shape: list[tuple[str, str]] = []
    widths: list[int | None] = []
    at_line, at = -1, 0
    marker = ""
    index = 0
    while index < len(spine):
        token = tokens[spine[index]]
        if token.type == "blockquote_open":
            line = int(token.map[0])
            text = source[starts[line] : starts[line + 1]].rstrip("\n")
            position = at if line == at_line else _step_over(text, widths)
            found = None if position is None else _QUOTE_OPENER.match(text, position)
            if found is None or "\t" in text:
                return None
            pieces.append("> ")
            shape.append(("blockquote_open", ">"))
            widths.append(None)
            at_line, at = line, found.end()
            index += 1
            continue
        marker = str(token.markup)
        ordered = token.type == "ordered_list_open"
        shape.append((str(token.type), marker))
        shape.append(("list_item_open", marker))
        if index + 1 == len(spine):
            pieces.append(("1" + marker if ordered else marker) + "    ")
            break
        item = tokens[spine[index + 1]]
        line = int(item.map[0])
        text = source[starts[line] : starts[line + 1]].rstrip("\n")
        position = at if line == at_line else _step_over(text, widths)
        found = None if position is None else _ITEM_OPENER.match(text, position)
        if found is None or "\t" in text or found[2][-1] != marker:
            return None
        if found[2][0].isdigit() != ordered:
            return None
        gap = len(found[3])
        # markdown-it's own rule for where an item's content starts: after the
        # spaces that follow the marker, unless the line ends there or there
        # are more than four, and then after one.
        padding = 1 if found.end() == len(text) or gap > 4 else gap
        if not padding:
            return None
        width = len(found[1]) + len(found[2]) + padding
        indent = found[1]
        if indent and widths and widths[-1] is not None:
            # This item is indented inside another item, on a line of its own.
            # Written straight after that item's marker the indent would be
            # read as more of *its* padding and move its content column
            # (measured: `-` then a nested ` 2.` came back as an outer item
            # one column wider, and a later line indented for the real one
            # fell out of it). Only the column this item's content starts at
            # matters to what follows, so the indent goes after the marker
            # instead -- when that still leaves four spaces or fewer.
            padding += len(indent)
            indent = ""
            if padding > 4:
                return None
        pieces.append(indent + found[2] + " " * padding)
        widths.append(width)
        at_line, at = line, min(found.start() + width, len(text))
        index += 2
    rule = "---" if marker == "*" else "***"
    shape.append(("hr", rule))
    return "".join(pieces) + rule + "\n", tuple(shape)


def _step_over(text: str, widths: list[int | None]) -> int | None:
    """
    Where in `text` the content of containers opened on earlier lines begins.

    `widths` has one entry per container, outermost first: the columns a list
    item's content is indented by, or `None` for a quote. `None` when the line
    does not carry one of them.
    """
    position = 0
    for width in widths:
        if width is None:
            found = _QUOTE_OPENER.match(text, position)
            if found is None:
                return None
            position = found.end()
        else:
            if text[position : position + width] != " " * width:
                return None
            position += width
    return position


def replaced_characters(block: Block) -> int:
    """
    How many characters of a block no face of the theme could set.

    For a host that wants to say so ("3 characters could not be shown").
    Counted from the material -- its `ReplacedChar` nodes -- rather than
    recorded beside it, so it is right for any slice of a block: a stream and
    a view both cut code blocks and tables into pieces. A U+FFFD that was in
    the source to begin with is not counted (it was set as written), and a
    character set as `?` because the prose face has no U+FFFD is. Until
    `ReplacedChar` existed this counted U+FFFD codepoints and had both of
    those the other way round. Formula boxes are not looked into.
    """

    def count(nodes: tuple[Node, ...]) -> int:
        return sum(1 for node in nodes if isinstance(node, ReplacedChar))

    match block:
        case TextBlock():
            return count(block.material) + count(block.marker)
        case CodeBlock():
            return sum(count(line) for line in block.lines)
        case TableBlock():
            return sum(count(cell.material) for row in (block.header, *block.rows) for cell in row)
        case _:
            return 0


def formula_spans(block: Block) -> tuple[FormulaSpan, ...]:
    """
    Every formula of a block, set or refused: a text block's own, a table's cell by cell.

    For a caller that wants to list what a document's math came to -- which
    sources were refused, and why -- without knowing which block shapes can
    hold a formula. A table's are in reading order, header first; their
    `start` and `end` index the *cell's* material, so they locate nothing
    without the cell and are for reading `source` and `refusal` from.
    """
    match block:
        case TextBlock():
            return block.formulas
        case TableBlock():
            return tuple(
                span
                for row in (block.header, *block.rows)
                for cell in row
                for span in cell.formulas
            )
        case _:
            return ()


def build_document(
    source: str,
    theme: Theme,
    resolve: MetricsResolver,
    *,
    references: bool = True,
    math: MathBuilder | None = None,
    more_may_follow: bool = False,
) -> Document:
    """
    Convert markdown source into blocks of unpacked material.

    The result also records where each block came from (`Document.sources`),
    as line and character ranges into `source`.

    `resolve` is how a `FontKey` becomes measurable; `imscribe.style` supplies
    `fontlib_metrics` for real fonts and tests supply a fake with round numbers.

    `references=False` reads the source with link reference definitions
    switched off: `[name]: https://example.org` is then a paragraph of that
    text, and `[name]` elsewhere is not a link. It exists for a caller that is
    given its source a piece at a time (`imscribe.stream`). A definition may
    come anywhere, including last, and turns every earlier `[name]` in the
    document into a link, so with definitions on, no block of an unfinished
    document is ever settled. It is the only such construct in what this parser
    accepts, which is a statement `tests/test_stream.py` tests rather than one
    read out of the CommonMark specification.

    `math` turns on `$...$` and `$$` and is what sets them; the module
    docstring has the rules. Left out, a dollar is text, and nothing about the
    result differs from what this function returned before it had the
    argument.

    `more_may_follow=True` says `source` is a text still being received. It
    changes one thing, and only with `math` on: an inline formula whose
    closing dollar is the **last character of the source** is not a formula
    yet -- it is text, dollars and all -- because whether that dollar closes
    anything depends on the character after it (`_math_inline`). The default
    reads the end of the input as a valid follower, which is right for a
    document that is whole. `imscribe.stream.StreamDocument` parses its live
    tail with this on until it is closed, so "the stream equals one parse of
    its source" is a statement about `build_document(stream.source,
    references=False, math=..., more_may_follow=not stream.closed)`.
    """
    converter = _Converter(theme, resolve, _parser(references, math is not None), math)
    return converter.convert(source, more_may_follow and math is not None)

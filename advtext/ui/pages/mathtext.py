r"""
The Math page: `$...$` and `$$` in running text, set by the math extension.

Three panes, each an ordinary view over an ordinary document converted with
`math=advtext.mathtext.markdown_math()` -- one builder for the whole page, kept,
because it remembers what it has set:

- **The text** (left) is `demo/math.md`: prose with formulas in it, each chosen
  as the witness to one thing -- a tall inline fraction and what it does to its
  line's gaps, scripts on the baseline, one source inline and as a `$$` display,
  a formula at a line break (the *measure* slider re-breaks the page so it can
  be watched moving whole), formulas in a heading, a list item, a quotation and
  a table cell, a link straight after a formula, and prices that stay text.
- **The source box** (top right) is markdown a visitor types; the paragraph
  under it is re-set on every edit, and every formula the builder refused is
  listed with its reason.
- **The stream** (bottom right) is a short reply fed to an
  `advtext.stream.StreamDocument` a few characters at a time. It opens stopped
  *inside* its first formula, so the unclosed `$` is on screen as text; *Step*
  feeds one piece.

## Two sections of the text are generated, so they cannot go stale

`demo/math.md` holds two placeholders. `{{reference}}` becomes a table of
*what | source | result* in which the source cell and the formula are made from
one string, and `{{refusals}}` a list of sources with the reason the parser gave
**when the page was built** -- not a reason copied into a file.

Which side a source lands on is likewise asked, not written down: every
candidate (`REFERENCE`, `REFUSED`) is put through `advtext.mathtext.typeset` at
the body size and goes to the table if it sets and to the list if it does not.
That is how the four constructs of the extension's second pass (radicals,
sized delimiters, spaces, words in a formula) got from the list to the table:
they were candidates of their own while they were refused, and moved by
themselves the moment the parser took them. They are rows of `REFERENCE` now.
The tests pin that `REFERENCE` sets and `REFUSED` does not, and show a source
changing sides when the answer changes.

**What is still out**, and listed with its reason: **matrices, left out for
now** by the user's decision, with everything else that needs alignment;
accents; a root taller than the largest radical sign the math face carries;
and content so much taller than the largest delimiter that the delimiter
would cover under three quarters of it, since neither sign is assembled from
pieces. (Content a little taller than the largest delimiter is set with the
largest: the stacked-limits fraction that used to head this list sets now.)
The first item of `REFUSED` is a `\left(`...`\right)` around a continued
fraction five deep, which parses and which the engine will not set for that
reason -- a refusal of kind `layout`, found by `typeset` and not by the
parser.

## What the readouts are

Counts: formulas set and refused in each pane (from
`advtext.markdown.formula_spans`), atoms in each layout
(`advtext.shipout.Atom` commands, one per set formula), glyphs drawn and glyphs missing
(`DrawStats`). The line under the header is `BareView.selected_text()` of
whichever pane owns the selection, which is what Ctrl+C would copy: a selected
formula appears there as its source between dollars. For the stream, the
number of dollar signs standing in the text as characters, outside any formula
span -- which is one while a `$` is unclosed and zero once it closes.

**None of it is a measure of quality** (`docs/visual-review.md`). Nobody has
judged how these formulas look in their lines.

## What the slider costs

A new measure re-breaks all of the text: about 110 ms for its 44 blocks,
measured headless, against 90 to 190 ms for `demo/sample.md` re-broken the same
way, so it is the price of a justified re-break and not of the formulas. The
slider moves in whole pixels, and a measure already visited is a cache hit.

## Limits this page shows rather than hides

- Find does not search inside a formula (`advtext.spans.material_text` leaves
  boxes out); the text says so.
- A `|` cannot be written in a formula in a table cell (the table rule splits
  the row first), so no row of the reference table has one.
- A character the face it is set in has no glyph for is taken from another
  of the theme's faces that has it (`advtext.markdown`, since C-mathfix), so
  a refused source with a Greek letter in it no longer shows a gap in the
  code face. The source box still counts glyphs nothing could draw
  (`DrawStats.missing`).
- The source box catches whatever `build_document` raises for typed input and
  shows it, keeping the last paragraph that did convert.

Options (`--tab math:...`): `done` opens with the stream fed to its end.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats
from advtext.markdown import (
    Block,
    Document,
    FormulaSpan,
    MathBuilder,
    TextBlock,
    build_document,
    formula_spans,
)
from advtext.mathtext import Refusal, RefusalKind, markdown_math, typeset
from advtext.nodes import CharNode
from advtext.pack import CharMeasure
from advtext.shipout import Atom
from advtext.stream import StreamDocument
from advtext.style import BlockKind, MetricsResolver, Theme
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.stream_view import StreamView
from advtext.units import DEFAULT_PX_PER_INCH, Scaled

__all__ = [
    "EDITOR_TEXT",
    "FALLBACK",
    "PAGE",
    "REFERENCE",
    "REFUSED",
    "STREAM_SOURCE",
    "Editor",
    "MathPage",
    "Replay",
    "Sorted",
    "Tally",
    "Verdict",
    "compose",
    "loose_dollars",
    "pieces",
    "reference_markdown",
    "refusals_markdown",
    "selection_line",
    "sort_out",
    "tally",
    "verdict",
]

# ----------------------------------------------------------------------
# The candidates: every source the two generated sections are made from
# ----------------------------------------------------------------------

REFERENCE: Final[tuple[tuple[str, str], ...]] = (
    ("superscript", r"x^2"),
    ("subscript", r"x_i"),
    ("both scripts", r"x_i^2"),
    ("a braced script", r"x^{a+b}"),
    ("a script on a script", r"e^{x^2}"),
    ("primes", r"f'(x) + g''(x)"),
    ("fraction", r"\frac{a}{b}"),
    ("fraction in a fraction", r"\frac{1}{1 + \frac{1}{x}}"),
    ("Greek, lower case", r"\alpha \beta \gamma \pi \omega"),
    ("Greek, capitals", r"\Gamma \Delta \Sigma \Omega"),
    ("sum with limits", r"\sum_{i=1}^{n} a_i"),
    ("product with limits", r"\prod_{k=1}^{n} k"),
    ("integral with bounds", r"\int_a^b f(x) dx"),
    ("limits beside, on request", r"\sum\nolimits_{i=1}^{n} a_i"),
    ("limits stacked, on request", r"\int\limits_a^b f"),
    ("relations", r"a \le b \ne c \approx d"),
    ("membership", r"x \in A \subset B"),
    ("arrows", r"a \to b \Rightarrow c"),
    ("binary operators", r"a + b - c \times d \cdot e \pm f"),
    ("fixed-size delimiters", r"(a + b)[c]\{d\}"),
    ("delimiters sized to their content", r"\left( \frac{a}{b} \right)"),
    ("brackets, sized", r"\left[ \frac{a}{b} \right]"),
    ("angle brackets, sized", r"\left\langle \frac{a}{b} \right\rangle"),
    ("a brace on one side only", r"\left\{ \frac{x}{2} \right."),
    ("a sized pair with scripts", r"\left. \frac{x^2}{2} \right\rbrack_0^1"),
    ("a square root", r"\sqrt{x^2 + y^2}"),
    ("a root over a fraction", r"\sqrt{\frac{a}{b}}"),
    ("explicit spaces", r"a \, b \; c \quad d"),
    ("a thin space before the differential", r"\int_0^1 f(x) \, dx"),
    ("a negative thin space", r"\int\!\!\int f"),
    ("words inside a formula", r"x = 1 \text{ if } y > 0"),
    ("words in a subscript", r"v_{\text{max}} \le c"),
    ("overline and underline", r"\overline{x + y} \underline{z}"),
    ("named functions", r"\sin x + \log y"),
    ("a limit", r"\lim_{n \to \infty} a_n"),
    ("an operator name", r"\operatorname{rank} A"),
    ("upright letters", r"\mathrm{d}x"),
    ("alphabets", r"\mathbb{R} \mathcal{L} \mathbf{v}"),
    ("dots on the baseline", r"a_1, \ldots, a_n"),
    ("dots on the axis", r"a_1 + \cdots + a_n"),
    ("ordinary symbols", r"\infty \partial \nabla \forall \exists"),
    ("symbols typed as themselves", "∞ ≤ ∑"),
)
"""
`(what it shows, source)`, one row for each construct of the subset. All set.

Every character of every source here, and in the two lists below, is one the
code face has a glyph for, because the page shows each source in that face. The
last row was `π ≤ ∑` until a walk of the page in a window counted one glyph
missing: Inconsolata has no `π` (nor `α`, `β`), and a character the bound face
lacks is counted and not drawn -- there is no fallback face. `tests/test_page_math.py`
holds the candidates to the code face's coverage.
"""

REFUSED: Final[tuple[tuple[str, str], ...]] = (
    (
        "content far taller than the largest parenthesis",
        r"\left( 1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{x}}}}} \right)",
    ),
    ("roots nested past the largest radical sign", r"\sqrt{\sqrt{\sqrt{\sqrt{\sqrt{\sqrt{x}}}}}}"),
    ("a root with a degree", r"\sqrt[3]{x}"),
    ("a delimiter of a named size", r"\big( x \big)"),
    ("a brace that stretches sideways", r"\overbrace{a + b}"),
    ("a matrix", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"),
    ("cases", r"\begin{cases} a \\ b \end{cases}"),
    ("an environment", r"\begin{align} a &= b \end{align}"),
    ("a column separator", r"a & b"),
    ("a macro definition", r"\newcommand{\R}{\mathbb{R}}"),
    ("a plain TeX definition", r"\def\half{\frac{1}{2}}"),
    ("an accent", r"\hat{x}"),
    ("a change of style", r"\displaystyle\sum_i a_i"),
    ("an infix fraction", r"a \over b"),
    ("a command nobody listed", r"\frobnicate{x}"),
    ("a script with nothing in it", r"x^"),
    ("a brace left open", r"\frac{a}{b"),
)
"""
`(what it is, source)` for sources outside the subset for good, or for now (matrices).

The first two are in the subset and are refused by the engine, not the parser:
what stands between the delimiters, or under the root, is taller than the
largest ready-made sign the math face has.
"""

EDITOR_TEXT: Final = (
    "Type markdown here. This sum is set in its line:\n"
    "$\\sum_{k=0}^{\\infty} \\frac{x^k}{k!} = e^x$\n"
    "and this accent is refused and stays as typed:\n"
    "$\\hat{x}$ and $5 is a price."
)
"""
What the source box holds as the page opens: one formula that sets, one that does not, one price.

In short lines, because ImGui's multi-line box does not wrap and a line break
inside a markdown paragraph is a space.
"""

STREAM_SOURCE: Final = (
    "The roots are $x = \\frac{-b \\pm \\sqrt{d}}{2a}$, where $d = b^2 - 4ac$ is the "
    "discriminant. Until a closing dollar sign has arrived the source is shown as "
    "text, and the words before it do not move when it closes.\n\n"
    "$$\n\\sum_{k=0}^{\\infty} \\frac{x^k}{k!} = e^x\n$$\n\n"
    "A display block is open from its first line, like a code fence.\n"
)

PIECE: Final = 3
"""
Characters in one piece of the stream. Small enough to stop inside a formula.
"""

PIECES_PER_SECOND: Final = 12.0

FALLBACK: Final = (
    "# Math in text\n\n"
    "No `demo/math.md` was found, so this is the whole text. A formula in a line: "
    "$e^{i\\pi} + 1 = 0$, a taller one, $\\frac{a}{b}$, and a price, $5 and $10.\n\n"
    "$$\n\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}\n$$\n\n"
    "{{reference}}\n\n{{refusals}}\n"
)

REFERENCE_MARK: Final = "{{reference}}"
REFUSALS_MARK: Final = "{{refusals}}"

TEXT_PANE_PX: Final = 600.0
"""
The text pane's outer width. The measure inside it is the slider's, never more than this holds.
"""

MEASURE_PX: Final = (160.0, 548.0)
"""
The slider's range. The top is what `TEXT_PANE_PX` holds beside padding and a scrollbar.

The bottom is under the width of the widest inline formula in `demo/math.md`
(218 px at the stock theme, measured), so the overhang its text describes can
be reached; `tests/test_page_math.py` holds the inequality.
"""

DEFAULT_MEASURE_PX: Final = 520.0
INPUT_HEIGHT_PX: Final = 84.0
RESULT_HEIGHT_PX: Final = 190.0
SELECTION_SHOWN: Final = 110
"""
How many characters of a selection's copy the header line shows before it is cut.
"""

DOLLAR: Final = 0x24


# ----------------------------------------------------------------------
# Sorting the candidates: asked of the extension, not written down
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Verdict:
    """
    What the extension made of one source: it set, or it was refused and why.

    `kind` is `None` for a source that set; then `reason` is empty.
    """

    what: str
    source: str
    kind: RefusalKind | None = None
    reason: str = ""
    position: int = 0

    @property
    def sets(self) -> bool:
        return self.kind is None


def verdict(what: str, source: str, size: Scaled) -> Verdict:
    """
    Put one source through `advtext.mathtext.typeset` at `size` and report.

    `typeset` and not `parse`: a source the parser takes and the engine cannot
    set -- no math face, content taller than the font's largest delimiter --
    is a refusal in a document, so it is one here.
    """
    result = typeset(source, size)
    if isinstance(result, Refusal):
        return Verdict(what, source, result.kind, result.reason, result.position)
    return Verdict(what, source)


@dataclass(frozen=True, slots=True)
class Sorted:
    """
    Every candidate, on the side the extension put it: `sets` for the table, `refused` for the list.
    """

    sets: tuple[Verdict, ...]
    refused: tuple[Verdict, ...]


def sort_out(
    size: Scaled,
    candidates: Iterable[tuple[str, str]] | None = None,
) -> Sorted:
    """
    `REFERENCE` and then `REFUSED` (or `candidates`), each on the side it was put.
    """
    if candidates is None:
        candidates = (*REFERENCE, *REFUSED)
    verdicts = [verdict(what, source, size) for what, source in candidates]
    return Sorted(
        tuple(item for item in verdicts if item.sets),
        tuple(item for item in verdicts if not item.sets),
    )


_PUNCTUATION: Final = re.compile(r"([!-/:-@\[-`{-~])")


def _escaped(text: str) -> str:
    """
    `text` with every ASCII punctuation mark backslashed, so markdown reads it as itself.

    A reason quotes the command it is about (`\\frac{..}{..}`), and unescaped
    that is markup, or a formula.
    """
    return _PUNCTUATION.sub(r"\\\1", text)


def reference_markdown(sets: Sequence[Verdict]) -> str:
    """
    The table of *what | source | result*: the source cell and the formula are one string.

    A source with a `|` or a backtick in it cannot be written in a cell and is
    left out; `tests/test_page_math.py` holds that none of the candidates has one.
    """
    rows = ["| what | source | result |", "|---|---|---|"]
    for item in sets:
        if "|" in item.source or "`" in item.source:
            continue
        rows.append(f"| {_escaped(item.what)} | `{item.source}` | ${item.source}$ |")
    return "\n".join(rows)


def refusals_markdown(refused: Sequence[Verdict]) -> str:
    """
    One list item for each refused source: the source between dollars, then why.

    The dollars are the point: the converter is handed the formula, refuses
    it, and sets it as typed in the code face. Nothing here writes code spans.
    """
    items = []
    for item in refused:
        kind = "" if item.kind is None else item.kind.value
        items.append(
            f"- ${item.source}$ — {_escaped(item.what)} ({_escaped(kind)}): "
            f"{_escaped(item.reason)}."
        )
    return "\n".join(items)


def compose(text: str, found: Sorted) -> str:
    """
    `text` with its two placeholders replaced; a section with no placeholder is appended.
    """
    for mark, section in (
        (REFERENCE_MARK, reference_markdown(found.sets)),
        (REFUSALS_MARK, refusals_markdown(found.refused)),
    ):
        if mark in text:
            text = text.replace(mark, section)
        else:
            text = f"{text.rstrip()}\n\n{section}\n"
    return text


# ----------------------------------------------------------------------
# Counting what a document's math came to
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tally:
    """
    The formulas of some blocks: how many set, and the ones that were refused.
    """

    sets: int = 0
    refused: tuple[FormulaSpan, ...] = ()
    unclosed: int = 0
    """
    Display blocks whose closing `$$` has not arrived. Shown as source until it
    does; neither set nor refused, because nobody has been asked yet.
    """

    @property
    def total(self) -> int:
        return self.sets + len(self.refused) + self.unclosed


def tally(blocks: Iterable[Block]) -> Tally:
    """
    Every formula of `blocks`, table cells included, split by whether it set.
    """
    sets = 0
    unclosed = 0
    refused: list[FormulaSpan] = []
    for block in blocks:
        for span in formula_spans(block):
            if span.unclosed:
                unclosed += 1
            elif span.refusal:
                refused.append(span)
            else:
                sets += 1
    return Tally(sets, tuple(refused), unclosed)


def loose_dollars(blocks: Iterable[Block]) -> int:
    """
    Dollar signs set as characters of the text, outside every formula span.

    A refused formula keeps its dollars inside its span and is not counted; a
    price is, and so is the opening `$` of a formula whose end has not arrived.
    Text blocks only.
    """
    count = 0
    for block in blocks:
        if not isinstance(block, TextBlock):
            continue
        spans = [range(span.start, span.end) for span in block.formulas]
        for index, node in enumerate(block.material):
            if (
                isinstance(node, CharNode)
                and node.codepoint == DOLLAR
                and not any(index in span for span in spans)
            ):
                count += 1
    return count


def atoms_in(view: BareView) -> int:
    """
    Atoms in a view's current layout: one for each formula that was set and shipped.

    Counted from the shipped commands (`advtext.shipout.Atom`).
    `PlacedUnit.atoms` is not this number: it names what every formula span of
    a block would copy as, a refused one included (measured: 66 entries for
    this page's 50 set formulas and 16 refusals), and only the entries that
    land on an `Atom` are ever used.
    """
    layout = view.layout
    if layout is None:
        return 0
    return sum(1 for unit in layout.placed for cmd in unit.cmds if isinstance(cmd, Atom))


# ----------------------------------------------------------------------
# The source box
# ----------------------------------------------------------------------


@dataclass(slots=True)
class Editor:
    """
    Markdown somebody types, and the view of what it converts to. No ImGui.
    """

    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver
    math: MathBuilder
    px_per_inch: float = DEFAULT_PX_PER_INCH
    text: str = EDITOR_TEXT
    error: str = ""
    """What the last edit raised, or empty. The view then still shows the edit before it."""
    edits: int = 0
    view: BareView = field(init=False)

    def __post_init__(self) -> None:
        self.view = BareView(
            document=self._convert(self.text),
            theme=self.theme,
            measure=self.measure,
            px_per_inch=self.px_per_inch,
        )

    def _convert(self, text: str) -> Document:
        return build_document(text, self.theme, self.metrics, math=self.math)

    def set_text(self, text: str) -> None:
        """
        What an edit of the box does: convert, and hand the view the new document.

        Whatever the conversion raises is kept in `error` and shown; the box is
        a visitor's free text, and a traceback on the way to a frame ends the
        app (`advtext.ui.pages`, "an exception in `draw` is not caught").
        """
        self.text = text
        self.edits += 1
        try:
            document = self._convert(text)
        except Exception as failure:  # typed input; see the docstring
            self.error = f"{type(failure).__name__}: {failure}"
            return
        self.error = ""
        self.view.document = document
        self.view.invalidate()

    @property
    def tally(self) -> Tally:
        return tally(self.view.document.blocks)

    def lines(self) -> tuple[str, ...]:
        """
        The readout under the paragraph: counts, then each refusal with its reason.
        """
        found = self.tally
        out = [
            f"{found.sets} set  ·  {len(found.refused)} refused  ·  "
            f"{loose_dollars(self.view.document.blocks)} dollar signs left as text"
        ]
        if self.error:
            out.append(f"not converted: {self.error}")
        for span in found.refused:
            out.append(f"{span.text}  refused at character {span.position}: {span.refusal}")
        return tuple(out)


# ----------------------------------------------------------------------
# The stream
# ----------------------------------------------------------------------


def pieces(source: str, size: int = PIECE) -> tuple[str, ...]:
    """
    `source` cut into pieces of `size` characters, the last one shorter.
    """
    size = max(size, 1)
    return tuple(source[start : start + size] for start in range(0, len(source), size))


def opening_pieces(source: str, size: int = PIECE) -> int:
    """
    How many pieces to feed so the stream stops a little way inside its first formula.

    Eight characters past the first dollar sign, or everything if there is none.
    """
    first = source.find("$")
    if first == -1:
        return len(pieces(source, size))
    return min((first + 8) // max(size, 1), len(pieces(source, size)))


@dataclass(slots=True)
class Replay:
    """
    `source` fed to a stream with math on, a piece at a time. No ImGui.
    """

    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver
    math: MathBuilder
    px_per_inch: float = DEFAULT_PX_PER_INCH
    source: str = STREAM_SOURCE
    parts: tuple[str, ...] = field(init=False)
    fed: int = field(default=0, init=False)
    stream: StreamDocument = field(init=False)
    view: StreamView = field(init=False)

    def __post_init__(self) -> None:
        self.parts = pieces(self.source)
        self.restart(opening_pieces(self.source))

    def restart(self, feed: int = 0) -> None:
        """
        Begin again from nothing, then feed `feed` pieces.
        """
        self.stream = StreamDocument(self.theme, self.metrics, math=self.math)
        self.view = StreamView(self.stream, self.measure, px_per_inch=self.px_per_inch)
        self.fed = 0
        self.step(feed)

    @property
    def done(self) -> bool:
        return self.fed >= len(self.parts)

    def step(self, count: int = 1) -> int:
        """
        Feed up to `count` more pieces; close the stream after the last. Returns how many.
        """
        taken = self.parts[self.fed : self.fed + max(count, 0)]
        for piece in taken:
            self.stream.append(piece)
        self.fed += len(taken)
        if self.done and not self.stream.closed:
            self.stream.close()
        return len(taken)

    def finish(self) -> int:
        return self.step(len(self.parts) - self.fed)

    @property
    def tally(self) -> Tally:
        return tally(self.stream.blocks)

    def line(self) -> str:
        """
        The stream's readout: how far it is, and what its dollars have come to so far.
        """
        found = self.tally
        return (
            f"{self.fed} of {len(self.parts)} pieces  ·  {found.sets} set  ·  "
            f"{len(found.refused)} refused so far  ·  "
            f"{loose_dollars(self.stream.blocks)} dollar signs standing as text"
        )


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


def selection_line(views: Sequence[BareView]) -> str:
    """
    What Ctrl+C would copy now: the selected text of whichever view owns the selection.
    """
    for view in views:
        if view.owns_selection:
            text = view.selected_text()
            if text:
                shown = text if len(text) <= SELECTION_SHOWN else text[:SELECTION_SHOWN] + "…"
                return f"selection copies ({len(text)} characters): {shown!r}"
    return "select across a formula in any pane: this line shows what Ctrl+C would copy"


class MathPage:
    """
    The page: the text, the source box and the stream, sharing one math builder.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        theme, metrics = context.theme, context.metrics
        self.math: MathBuilder = markdown_math()
        self.size: Scaled = theme.style(BlockKind.PARAGRAPH).font.size
        self.sorted = sort_out(self.size)
        text = demo_text("math.md")
        self.from_file = text is not None
        self.source = compose(FALLBACK if text is None else text, self.sorted)
        self.text = BareView(
            document=build_document(self.source, theme, metrics, math=self.math),
            theme=theme,
            measure=context.measure,
            px_per_inch=context.px_per_inch,
        )
        self.editor = Editor(theme, context.measure, metrics, self.math, context.px_per_inch)
        self.replay = Replay(theme, context.measure, metrics, self.math, context.px_per_inch)
        if "done" in context.options_for(PAGE.name):
            self.replay.finish()
        self.measure_px = DEFAULT_MEASURE_PX
        self.playing = False
        self.frames = 0
        self.stats: dict[str, DrawStats] = {}
        self._due = 0.0

    # -- what the controls do --------------------------------------------

    def set_measure(self, width_px: float) -> None:
        """
        What the slider does: the text is re-broken at `width_px` on the next frame.
        """
        low, high = MEASURE_PX
        self.measure_px = float(round(min(max(width_px, low), high)))

    def type(self, text: str) -> None:
        """
        What an edit of the source box does.
        """
        self.editor.set_text(text)

    def restart(self) -> None:
        self.replay.restart()
        self.playing = False
        self._due = 0.0

    def play(self, on: bool = True) -> None:
        """
        Start or stop feeding the stream by the clock. Starting a finished one restarts it.
        """
        if on and self.replay.done:
            self.replay.restart()
        self.playing = on
        self._due = 0.0

    def advance(self, seconds: float) -> int:
        """
        Feed what `seconds` of playing is worth, and stop playing at the end. Returns pieces fed.
        """
        if not self.playing:
            return 0
        self._due += max(seconds, 0.0) * PIECES_PER_SECOND
        count = int(self._due)
        self._due -= count
        fed = self.replay.step(count)
        if self.replay.done:
            self.playing = False
        return fed

    @property
    def views(self) -> tuple[BareView, BareView, BareView]:
        return (self.text, self.editor.view, self.replay.view)

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts, one line a pane and one for the page.
        """
        lines = []
        total = DrawStats()
        panes = (
            ("text", self.text, tally(self.text.document.blocks)),
            ("editor", self.editor.view, self.editor.tally),
            ("stream", self.replay.view, self.replay.tally),
        )
        for name, view, found in panes:
            stats = self.stats.get(name, DrawStats())
            total = DrawStats(
                total.glyphs + stats.glyphs,
                total.missing + stats.missing,
                total.rules + stats.rules,
            )
            lines.append(
                f"pane={name} blocks={len(view.document.blocks)} set={found.sets} "
                f"refused={len(found.refused)} atoms={atoms_in(view)} "
                f"loose={loose_dollars(view.document.blocks)} glyphs={stats.glyphs} "
                f"missing={stats.missing} rules={stats.rules}"
            )
        lines.append(
            f"frames={self.frames} from_file={int(self.from_file)} "
            f"measure={self.measure_px:.0f} table={len(self.sorted.sets)} "
            f"listed={len(self.sorted.refused)} fed={self.replay.fed} "
            f"pieces={len(self.replay.parts)} edits={self.editor.edits} "
            f"glyphs={total.glyphs} missing={total.missing} rules={total.rules}"
        )
        return lines

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        if self.playing:
            self.advance(imgui.get_io().delta_time)
        self._header(imgui)
        imgui.separator()

        padded = imgui.ChildFlags_.borders.value | imgui.ChildFlags_.always_use_window_padding.value
        scrolls = imgui.WindowFlags_.always_vertical_scrollbar.value
        debug = self.context.debug
        fonts = self.context.fonts

        imgui.begin_child("##advtext-math-text", imgui.ImVec2(TEXT_PANE_PX, 0.0), padded, scrolls)
        self.text.debug = debug
        self.stats["text"] = self.text.draw(
            fonts=fonts, palette=DARK_PALETTE, width_px=max(self.measure_px, MIN_WIDTH_PX)
        )
        imgui.end_child()

        imgui.same_line()
        imgui.begin_group()
        self._source_box(imgui, padded, scrolls)
        self._stream(imgui, padded, scrolls)
        imgui.end_group()

    def _header(self, imgui: Any) -> None:
        caption("markdown with $...$ and $$, set by the math extension; a refusal stays as typed")
        imgui.same_line()
        debug_toggle(self.context)
        imgui.same_line()
        imgui.set_next_item_width(220.0)
        changed, value = imgui.slider_float(
            "measure", self.measure_px, MEASURE_PX[0], MEASURE_PX[1], "%.0f px"
        )
        if changed:
            self.set_measure(value)
        caption(selection_line(self.views))

    def _source_box(self, imgui: Any, padded: int, scrolls: int) -> None:
        editor = self.editor
        caption("type markdown; the paragraph under the box is set again on every edit")
        changed, text = imgui.input_text_multiline(
            "##advtext-math-source",
            editor.text,
            imgui.ImVec2(max(imgui.get_content_region_avail().x, MIN_WIDTH_PX), INPUT_HEIGHT_PX),
        )
        if changed and text != editor.text:
            self.type(text)
        imgui.begin_child(
            "##advtext-math-result", imgui.ImVec2(0.0, RESULT_HEIGHT_PX), padded, scrolls
        )
        editor.view.debug = self.context.debug
        stats = editor.view.draw(fonts=self.context.fonts, palette=DARK_PALETTE)
        self.stats["editor"] = stats
        imgui.push_text_wrap_pos(0.0)
        for line in editor.lines():
            caption(line)
        if stats.missing:
            # Typed text can ask a face for a character it does not have (the
            # code face has no Greek), and nothing is drawn in its place.
            caption(f"{stats.missing} glyphs not drawn: the face they are set in has none")
        imgui.pop_text_wrap_pos()
        imgui.end_child()

    def _stream(self, imgui: Any, padded: int, scrolls: int) -> None:
        replay = self.replay
        if imgui.button("Restart"):
            self.restart()
        imgui.same_line()
        if imgui.button("Step"):
            self.playing = False
            replay.step()
        imgui.same_line()
        if imgui.button("Pause" if self.playing else "Play"):
            self.play(not self.playing)
        imgui.same_line()
        if imgui.button("Finish"):
            self.playing = False
            replay.finish()
        caption(f"stream: {replay.line()}")
        height = max(imgui.get_content_region_avail().y, 80.0)
        imgui.begin_child("##advtext-math-stream", imgui.ImVec2(0.0, height), padded, scrolls)
        replay.view.debug = self.context.debug
        self.stats["stream"] = replay.view.draw(fonts=self.context.fonts, palette=DARK_PALETTE)
        imgui.end_child()


PAGE = PageSpec(
    name="Math",
    order=60,
    factory=MathPage,
    group="Typesetting",
    title="Math in text",
    caption="inline and display formulas from a $...$ subset, in running text and in a stream",
    options=("done",),
    shots=("", "done"),
)

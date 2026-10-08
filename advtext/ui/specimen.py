r"""
A font specimen: the six faces this project sets, arranged so they can be compared.

The material for a specimen tab, as boxes and numbers. Nothing here draws, nothing
here imports ImGui -- not even deferred, as `advtext.ui.document_view` has to --
because a specimen is arithmetic over font metrics and the result is a packed
`advtext.nodes.Box` that `advtext.shipout.ship` turns into commands for whichever
backend is asking. `scripts/render_litmus.py` and an ImGui tab are the two intended
consumers and they share every line below.

**What has been executed, and what has not.** Every number this module produces is
measured from the real font files by `tests/test_specimen.py`, which runs with no
display. Whether the result *looks* good is not asserted anywhere and is not
claimed here.

## Three sections, and why each one earns its space

1. **The six faces**, one line each, at one size, labelled in a measured gutter.
   Side by side rather than one at a time: `advtext.ui.app.App.formula_box` makes
   the argument and it is the same argument -- a reader compares two things faster
   than they compare a picture with a memory. The four Roboto faces share an
   x-height, an ascent and a descent to the font unit, so what separates them here
   is **set width**: at 24 px the pangram comes out 473.44 px regular, 480.56 px
   bold, 464.26 px italic and 471.20 px bold italic. Inconsolata (516.00 px) and
   Latin Modern Math (479.42 px) separate on x-height as well -- 0.457 and 0.431 of
   the em against Roboto's 0.528 -- which is the measurement `advtext.style`'s
   docstring uses to argue that code is set at the body size rather than smaller.

2. **A size ladder**, one face at six sizes. The sizes are not hand-picked: they
   are `advtext.style`'s own modular scale, 1.25 per step from a 16 px body,
   extended two steps downward. A ladder of round numbers would demonstrate that
   text can be big or small; this one demonstrates the scale the document is
   actually set on.

3. **Kerning**, which is the section that shows metrics rather than shapes.

## Why kerning is the metric demonstration, and not something else

The brief for this module asked for something a naive renderer gets wrong, and
there were three candidates: justification landing exactly on the margin, the
display-size summation being a different glyph, and `GPOS` kerning. The first two
are already demonstrated elsewhere in this tree -- `tests/test_litmus.py` owns the
margin and the Formula tab owns the summation -- and neither is a property of a
*face*, which is what a specimen is about. Kerning is:

- **It is per-face data and it varies.** Of the six faces, only the four Roboto
  ones carry a `kern` feature. Inconsolata is monospaced and Latin Modern Math
  spaces through its `MATH` table, so both genuinely have none, and a specimen
  that showed a kern for them would be showing a bug. `advtext.fontlib`'s
  `_read_kern_feature` comment records the same fact.
- **The widget underneath cannot do it at all.** ImGui exposes no kerning, so this
  is not "we do it better", it is "this cannot be got from the layer we replaced".
- **It is falsifiable to the scaled point.** Each pair is set twice, once with the
  font's `GPOS` value applied and once with it dropped, and the difference between
  the two boxes is *exactly* that value. `tests/test_specimen.py` asserts the
  equality rather than an inequality.

**`rt` is in the pair list on purpose.** Its Roboto kern is **positive** (+24/1000
em), so the naive setting is too *tight* rather than too loose. A demonstration
made only of `AV`, `To` and `Wa` would leave a reader with the wrong rule --
"kerning pulls letters together" -- and the one counterexample costs a row.

## What this module does not do

**Rows are set at their natural width and are never line-broken.** A specimen line
that wrapped would stop being a specimen: the reader is comparing set widths, and a
row that wrapped would compare a fragment. So `width` below is the measure for the
*prose* in each section -- the heading and the note, which go through
`advtext.markdown` and `advtext.ui.compose_blocks` like any other document -- and
it is not a constraint on the rows. `Specimen.box.width` is therefore the greater
of `width` and the widest row, and is what a caller sizing a scroll region should
use: when it comes back larger than the `width` that was asked for, a row did not
fit. At the default sizes the widest row is the monospace one at **590 px**
including the gutter, so that happens below about 590 px of measure. It clips
rather than reflowing, and the remedy is a smaller `specimen_px`.

Also out of scope: colour (the node model carries none), glyph-set tables, and any
notion of which faces ImGui managed to load -- `advtext.ui.app.load_fonts` treats a
missing face as non-fatal and reports through `DrawStats.missing`, and this module
takes the same posture one layer up: a face whose metrics cannot be resolved is
listed in `Specimen.absent` and its rows are simply not built.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from advtext.fontmetrics import Face, FontMetrics
from advtext.markdown import build_document
from advtext.nodes import Box, CharNode, Glue, GlueSpec, Kern, Node
from advtext.pack import (
    IGNORE_DEPTH,
    CharMeasure,
    InterlineSkip,
    PackMode,
    append_to_vlist,
    hpack,
    vpack,
)
from advtext.style import (
    BODY_SIZE_PX,
    TYPE_SCALE_RATIO,
    BlockKind,
    MetricsResolver,
    Strut,
    Theme,
    char_measure,
    font_key,
    interword_glue,
)
from advtext.ui import compose_blocks
from advtext.units import UNITY, GlueOrder, Scaled, px_from_sp, sp_from_px

__all__ = [
    "FACE_LABELS",
    "KERN_FACE",
    "KERN_PAIRS",
    "KERN_PX",
    "LABEL_PX",
    "LADDER_STEPS",
    "LADDER_TEXT",
    "PANGRAM",
    "SPECIMEN_PX",
    "KernPair",
    "Specimen",
    "SpecimenRow",
    "SpecimenSection",
    "build_specimen",
    "ladder_sizes_px",
]

PANGRAM = "The quick brown fox jumps over the lazy dog"
"""
The line every face is set in.

A pangram rather than a pretty phrase because the comparison is of *shapes*, and a
line missing half the alphabet hides half the differences. This one is also long
enough for the set widths to **separate**, which is not automatic: at 24 px the six
faces land between 464.26 px and 516.00 px with the closest two 1.14 px apart,
where "Sphinx of black quartz, judge my vow." puts the regular face and the bold
italic **0.11 px** apart -- a tenth of a pixel, close enough that a face resolving
to the wrong file would still look like a plausible row. Measured, both of them;
`tests/test_specimen.py` pins the separation this one gets.
"""

LADDER_TEXT = "Hamburgefonstiv"
"""
The size ladder's line: the type designer's own string, for its mix of round,
straight, ascending and descending forms in fifteen characters.
"""

FACE_LABELS: dict[Face, str] = {
    Face.PROSE: "Regular",
    Face.PROSE_BOLD: "Bold",
    Face.PROSE_ITALIC: "Italic",
    Face.PROSE_BOLD_ITALIC: "Bold Italic",
    Face.CODE: "Mono",
    Face.MATH: "Math",
}
"""
What each role is called in the gutter.

The role names rather than the family names: `advtext.fontmetrics.Face`'s whole
point is that layout asks for a role, and a specimen labelled "Roboto-Bold.ttf"
would document `advtext.fontlib`'s table instead of this project's model.
"""

KERN_PAIRS: tuple[tuple[str, str], ...] = (
    ("A", "V"),
    ("T", "o"),
    ("W", "a"),
    ("Y", "o"),
    ("P", "."),
    ("L", "T"),
    ("r", "t"),
)
"""
The pairs set twice in the kerning section.

Six that Roboto kerns negatively and one -- `rt` -- that it kerns **positively**.
The module docstring says why the last one is not optional.
"""

KERN_FACE = Face.PROSE
"""
The face the kerning section is set in.

One of the four that actually carry a `kern` feature. Setting this demonstration in
the code or math face would produce two identical columns and read as a broken
demonstration rather than as a fact about those faces.
"""

SPECIMEN_PX = 24.0
"""
The size the six faces are compared at.

Large enough that a stroke-weight difference is visible and small enough that the
widest row (the monospace one) stays inside about 600 px including the gutter.
"""

LADDER_STEPS = 6
"""
How many rungs the size ladder has, counting down from the theme's h1.
"""

KERN_PX = 44.0
"""
The size the kerned pairs are set at.

Deliberately much larger than the body: Roboto's `AV` kern is 42/1000 em, which is
1.0 px at the body size and would be invisible. At 44 px it is 1.8 px, which is the
difference between two columns a reader can actually see.
"""

LABEL_PX = 12.0
"""
The size of the gutter labels, which are set in `Face.CODE` at every row.

One face and one size for every label in the document, so the gutter is not part of
the comparison. The monospace row is therefore labelled in its own face at a
different size; there is no face that labelling it in would avoid that, and a
caption that looks like a caption is worth more than the avoidance.
"""

_FILL = GlueSpec(stretch=UNITY, stretch_order=GlueOrder.FIL)
r"""
`\hfil`: stretch only, no shrink.

Numerically the same spec as `advtext.ui.RAGGED_RIGHT`, and not imported from there
because that constant is a `\rightskip` and reading one in a label box would look
like a mistake. Stretch without shrink for the reason `advtext.ui._hang_marker`
gives: a label wider than the gutter then overfulls into the gap rather than being
pushed off the left edge of the page by a negatively-shrunk glue.
"""

# The rhythm every specimen row is set on, as a multiple of its own size. Rows vary
# in size within the ladder, so the leading is per row rather than per section and
# §679 sees a baselineskip that has grown with the type.
_LEADING_RATIO = 1.5


def ladder_sizes_px(base_px: float = BODY_SIZE_PX, steps: int = LADDER_STEPS) -> tuple[float, ...]:
    """
    The size ladder, ascending: `advtext.style`'s modular scale around the body size.

    Two steps below the body and the rest above, so the body size itself is on the
    ladder and the top rung is the theme's own h1. Generated from
    `TYPE_SCALE_RATIO` rather than listed, for the reason `advtext.style.Theme.build`
    generates the type scale rather than listing it: a changed ratio should move the
    specimen with the document.
    """
    return tuple(base_px * TYPE_SCALE_RATIO ** (step - 2) for step in range(steps))


@dataclass(frozen=True, slots=True)
class KernPair:
    """
    One kerned pair, measured both ways, in scaled points.

    `kern` is the font's own `GPOS` value at this size, rounded once on the way in
    exactly as `advtext.markdown` rounds it. The invariant worth knowing is
    `kerned == unkerned + kern`, exactly -- it is what makes the two columns in the
    specimen a measurement rather than an impression, and `tests/test_specimen.py`
    asserts the equality.
    """

    left: str
    right: str
    kern: Scaled
    kerned: Scaled
    unkerned: Scaled


@dataclass(frozen=True, slots=True)
class SpecimenRow:
    """
    One line of a specimen: a label in the gutter and one or two samples beside it.

    `set_width` is the width of the sample alone, with the gutter excluded, because
    that is the number being compared down a column. `box.width` includes the
    gutter and is what the row occupies.

    `label_width` is the label's own set width, excluding the gap that separates it
    from the sample. It is here so that "the gutter was measured and every label
    fits it" is a property a test can check without reaching into the builder.

    `pair` is present only on a kerning row and carries the numbers behind it.
    """

    label: str
    face: Face
    size: Scaled
    box: Box
    set_width: Scaled
    label_width: Scaled
    pair: KernPair | None = None


@dataclass(frozen=True, slots=True)
class SpecimenSection:
    """
    A heading, a note and a run of rows, packed into one vertical box.

    The heading and the note are ordinary markdown, composed by
    `advtext.ui.compose_blocks` at the caller's measure. The rows are not: they are
    packed at their natural width and never broken, which the module docstring
    argues for.

    `note` is that composed prose on its own, and it comes back empty when the faces
    it needs are missing -- see `_prose`. It is exposed separately so that "the rows
    survived and the caption did not" is observable rather than a claim.

    `header` is a column heading over the rows, and is `None` for a section whose
    columns need no naming. It is not a `SpecimenRow` because it is not a specimen:
    "every row in this section carries a `KernPair`" should stay a true sentence.
    """

    title: str
    rows: tuple[SpecimenRow, ...]
    box: Box
    note: Box
    header: Box | None = None


@dataclass(frozen=True, slots=True)
class Specimen:
    """
    The whole specimen document, ready to ship.

    `box`'s reference point is the baseline of its first line, like every other box
    in this project, so `ship(specimen.box, Point(0, specimen.box.height))` puts its
    top-left at the origin.

    `absent` lists the faces whose metrics could not be resolved. It is empty in
    every environment that has the bundled fonts; it exists so that a font swap
    degrades to a shorter specimen rather than to a traceback, matching
    `advtext.ui.app.load_fonts`.
    """

    sections: tuple[SpecimenSection, ...]
    box: Box
    gutter: Scaled
    absent: tuple[Face, ...]


@dataclass(slots=True)
class _Stack:
    """
    A vertical list under construction, with §679's `prev_depth` threaded through it.

    The same two moves `advtext.ui._stacked` makes, and made the same way: a box
    joins with its interline glue, and an explicit gap is a kern that also resets
    `prev_depth` to `IGNORE_DEPTH`. Leaving `prev_depth` alone across a kern would
    add a `\\baselineskip`-derived gap on top of the requested one, which is the
    defect that docstring warns about.
    """

    vlist: list[Node] = field(default_factory=list)
    prev_depth: Scaled = IGNORE_DEPTH

    def gap(self, amount: Scaled) -> None:
        """
        Break the rhythm by `amount`, or by nothing at the very top of the list.
        """
        if self.vlist and amount:
            self.vlist.append(Kern(width=amount))
        self.prev_depth = IGNORE_DEPTH

    def add(self, box: Box, skip: InterlineSkip) -> None:
        """
        Append one box on `skip`'s rhythm.
        """
        self.prev_depth = append_to_vlist(self.vlist, box, self.prev_depth, skip)

    def packed(self) -> Box:
        """
        The list as a vbox at its natural height.
        """
        return vpack(self.vlist).box


def _skip(size: Scaled) -> InterlineSkip:
    """
    The interline triple for a row set at `size`.

    Looser than `advtext.style`'s prose leading (1.5 against 1.35) because specimen
    rows are compared to each other rather than read as a paragraph, and the extra
    air is what stops a 31 px rung of the ladder from crowding the 25 px one.
    """
    return InterlineSkip(
        baselineskip=GlueSpec(width=round(size * _LEADING_RATIO)),
        lineskip=GlueSpec(width=round(size * 0.2)),
        lineskiplimit=0,
    )


def _set(
    text: str,
    face: Face,
    size: Scaled,
    metrics: FontMetrics,
    measure: CharMeasure,
    *,
    kerned: bool = True,
) -> Box:
    """
    One run of text in one face at one size, as an hbox at its natural width.

    A condensed `advtext.markdown._Converter._append_text`: characters, the `GPOS`
    kern between adjacent pairs, and interword glue for a space. The space factor is
    not tracked, because a specimen line is not a sentence and §1034's wide space
    after a period would add a variable this comparison does not want.

    `kerned=False` drops the kern nodes and nothing else, which is precisely the
    setting a renderer that measures glyph by glyph produces. That it differs from
    the kerned setting by exactly the sum of the kerns is the whole demonstration.
    """
    key = font_key(face, size)
    space = round(metrics.space_width)
    nodes: list[Node] = []
    for index, character in enumerate(text):
        if character == " ":
            nodes.append(Glue(interword_glue(space)))
            continue
        nodes.append(CharNode(key, ord(character)))
        following = text[index + 1 : index + 2]
        if kerned and following and following != " ":
            amount = round(metrics.kern(ord(character), ord(following)))
            if amount:
                nodes.append(Kern(width=amount))
    return hpack(nodes, measure=measure).box


def _fixed(box: Box, width: Scaled, measure: CharMeasure) -> Box:
    """
    `box` left-aligned in a column exactly `width` wide.

    The column is what makes two samples comparable: both start at the same x, so
    the eye reads the difference off their right-hand ends rather than having to
    hold one of them in memory.
    """
    return hpack([box, Glue(_FILL)], width, PackMode.EXACTLY, measure=measure).box


def _row(label: Box, gutter: Scaled, gap: Scaled, samples: list[Node], measure: CharMeasure) -> Box:
    """
    A label right-aligned in a gutter exactly `gutter` wide, then the samples.

    Right-aligned for the reason `advtext.ui._hang_marker` right-aligns a list
    marker: labels of different lengths then all end at the same x, one gap to the
    left of the column every row's sample starts at.

    **The gap is a kern inside the gutter box and not space after it**, exactly as
    `_hang_marker` puts `marker_gap` inside the marker box. Written the other way
    round the gutter is the label's column and the widest label ends flush against
    the sample it names -- which is what this did until a screenshot showed "Bold
    Italic" touching its own pangram.
    """
    gutter_box = hpack(
        [Glue(_FILL), label, Kern(width=gap)], gutter, PackMode.EXACTLY, measure=measure
    ).box
    return hpack([gutter_box, *samples], measure=measure).box


def _prose(
    source: str, theme: Theme, width: Scaled, resolve: MetricsResolver, measure: CharMeasure
) -> Box:
    """
    A chunk of markdown, composed to `width`.

    Through `advtext.markdown.build_document` and `advtext.ui.compose_blocks` rather
    than built by hand, so a section heading in the specimen is set with the same
    face, size, leading and breaking as a heading anywhere else in the document. The
    alternative -- hand-packing the prose too -- would be a second, drifting
    implementation of the thing this project exists to do once.

    **Returns an empty box rather than raising when a face is missing.** The note
    is prose, so it reaches for the regular, bold, italic and code faces whatever
    the section is about, and `build_document` resolves each one as it converts. A
    specimen whose rows survive a font swap and whose captions do not is the right
    way round: the rows are the specimen.
    """
    try:
        document = build_document(source, theme, resolve)
    except Exception:
        return vpack([]).box
    return compose_blocks(document.blocks, theme, width, measure)


def _px_label(size_px: float) -> str:
    """
    A size as it appears in the gutter: `16 px`, `10.2 px`.
    """
    return f"{round(size_px, 1):g} px"


def _kern_label(kern: Scaled, px_per_inch: float) -> str:
    """
    A kern as it appears in the gutter, in pixels and signed.

    Signed because the sign is the point: `rt` is the row that stops a reader
    concluding that kerning only ever tightens.
    """
    return f"{px_from_sp(kern, px_per_inch):+.2f} px"


class _Labels:
    """
    Every gutter label in the specimen, packed once, and the gutter they all fit.

    **The gutter is measured rather than picked**, which is the same argument
    `advtext.style`'s docstring makes about `WIDEST_MARKER_EM`: a round number holds
    "Bold" and not "Bold Italic", and the label then eats its own gap and touches
    the sample it labels. Packing every label before any row is built is what makes
    one number right for all of them.
    """

    __slots__ = ("_boxes", "_measure", "_metrics", "_size", "gap", "gutter")

    def __init__(
        self,
        texts: list[str],
        theme: Theme,
        resolve: MetricsResolver,
        measure: CharMeasure,
    ) -> None:
        self._size = sp_from_px(LABEL_PX, theme.px_per_inch)
        try:
            self._metrics: FontMetrics | None = resolve(font_key(Face.CODE, self._size))
        except Exception:
            # The label face is `Face.CODE`, which is also one of the six being
            # shown, so this is reachable by the same font swap that empties a row.
            # An unlabelled specimen is a poor specimen and a raised exception in a
            # frame callback takes the window with it.
            self._metrics = None
        self._measure = measure
        self._boxes = {text: self.caption(text) for text in texts}
        self.gap = theme.marker_gap
        widest = max((box.width for box in self._boxes.values()), default=0)
        self.gutter = widest + self.gap if self._boxes else 0

    def caption(self, text: str) -> Box:
        """
        Any text at the label size and in the label face, packed naturally.

        A caption is **not** a gutter label and must not widen the gutter: the
        column headings in the kerning section sit over the samples rather than in
        the margin, and letting them into the measurement would push every specimen
        line right by the width of the word "unkerned".
        """
        if self._metrics is None:
            return hpack([]).box
        return _set(text, Face.CODE, self._size, self._metrics, self._measure)

    def box(self, text: str) -> Box:
        """
        The packed label, which was measured before the gutter was decided.
        """
        return self._boxes[text]

    def natural(self, text: str) -> Scaled:
        """
        The label's own width, excluding the gap. `natural + gap <= gutter`, always.
        """
        return self._boxes[text].width


_FACES_NOTE = """\
## The six faces

Every role this engine sets, at one size, on one grid. Roboto supplies four *real*
faces, so **bold** is a drawn bold and *italic* is a drawn italic rather than a
smear or a slant; the four share an x-height, an ascent and a descent to the font
unit, so what separates them here is set width. Inconsolata sets `code` and Latin
Modern Math sets formulae, and both have a smaller x-height than Roboto at the same
em -- 0.457 and 0.431 against 0.528 -- which is the measurement behind the decision
to set code at the body size instead of shrinking it.
"""

_LADDER_NOTE = """\
## A size ladder

Not round numbers: the document's own modular scale, a major third of 1.25 per step
from a 16 px body, extended two steps down. The top rung is the size a level-one
heading is set at, and the third rung is the size this note is set at.
"""

_KERN_NOTE = """\
## Kerning, which the widget underneath cannot do

Each pair is set twice. On the left with the font's own `GPOS` kern applied, on the
right with it dropped -- which is what a renderer that measures one glyph at a time
produces, and what Dear ImGui produces, because it exposes no kerning at all. The
difference between the two columns is exactly the value in the gutter. Read `rt`
last: its kern is *positive*, so the unkerned setting there is too tight rather than
too loose, and kerning is not simply a matter of pulling letters together.
"""


@dataclass(frozen=True, slots=True)
class _Build:
    """
    Everything a section builder needs that is the same for every section.

    Gathered into one record rather than passed as six parameters, the way
    `advtext.ui._Context` gathers the part of a cache key that is constant for a
    whole composition. `metrics` is keyed at the *specimen* size only; a section
    setting text at another size resolves its own, because a metrics object is
    bound to one face at one size.
    """

    theme: Theme
    width: Scaled
    resolve: MetricsResolver
    measure: CharMeasure
    labels: _Labels
    metrics: dict[Face, FontMetrics]

    def at(self, face: Face, size: Scaled) -> FontMetrics | None:
        """
        This face at this size, or `None` if it does not resolve.
        """
        if face not in self.metrics:
            return None
        try:
            return self.resolve(font_key(face, size))
        except Exception:
            return None

    def row(
        self,
        label: str,
        face: Face,
        size: Scaled,
        samples: list[Node],
        set_width: Scaled,
        pair: KernPair | None = None,
    ) -> SpecimenRow:
        """
        One row, on the strut its own size asks for.

        The strut is what makes a column of rows tile: `Strut.filling` fills the
        row's baseline-to-baseline distance exactly, so §679's interline glue comes
        out at zero and a row of `acem` occupies the same band as a row of `gjpqy`.
        `advtext.style.Strut` carries the argument at length.
        """
        strut = Strut.filling(round(size * _LEADING_RATIO))
        box = _row(
            self.labels.box(label), self.labels.gutter, self.labels.gap, samples, self.measure
        )
        return SpecimenRow(
            label=label,
            face=face,
            size=size,
            box=strut.applied_to(box),
            set_width=set_width,
            label_width=self.labels.natural(label),
            pair=pair,
        )

    def section(
        self,
        title: str,
        note: str,
        rows: list[SpecimenRow],
        header: Box | None = None,
    ) -> SpecimenSection:
        """
        A composed heading and note, an optional column heading, then the rows.
        """
        stack = _Stack()
        prose = _prose(note, self.theme, self.width, self.resolve, self.measure)
        stack.add(prose, _skip(prose.height))
        stack.gap(self.theme.marker_gap)
        if header is not None:
            stack.add(header, _skip(sp_from_px(LABEL_PX, self.theme.px_per_inch)))
            stack.gap(self.theme.marker_gap)
        for row in rows:
            stack.add(row.box, _skip(row.size))
        return SpecimenSection(
            title=title,
            rows=tuple(rows),
            box=stack.packed(),
            note=prose,
            header=header,
        )


def build_specimen(
    theme: Theme,
    width: Scaled,
    resolve: MetricsResolver,
    *,
    measure: CharMeasure | None = None,
    specimen_px: float = SPECIMEN_PX,
) -> Specimen:
    """
    Build the whole specimen: three sections, packed, ready for `advtext.shipout`.

    `width` is the measure the *prose* is broken to and not a bound on the rows; see
    the module docstring. `resolve` is the `advtext.style.MetricsResolver` every
    length comes from -- pass `advtext.style.fontlib_metrics` for the real fonts.

    `measure` defaults to `char_measure(resolve)`. Pass the one the caller will
    later hand `advtext.shipout.ship` and `advtext.backends.imgui_draw.draw`:
    `docs/status.md` §4 records that handing those a *different* metrics than the
    packing used is an unenforced contract whose only symptom is text at the wrong
    size, everywhere, with nothing raised.

    A face whose metrics cannot be resolved is skipped and named in
    `Specimen.absent` rather than raising, for the reason `load_fonts` does the
    same: a font swap should cost a row, not the tab.

    **Expensive: 68 ms at a 760 pt measure, best of three, against a 16.7 ms frame
    budget.** 62 ms of that is the three section notes going through
    `break_paragraph`, which is the same superlinear cost `docs/status.md` §4
    measures on `demo/sample.md` and is not this module's to fix. The rows are
    cheap because nothing about them is line-broken. Nothing here depends on the
    window except the measure the notes break to, so a caller should build once and
    rebuild only when that changes -- `advtext.ui.document_view.DocumentView` keeps
    a layout per width for exactly this reason.
    """
    specimen_size = sp_from_px(specimen_px, theme.px_per_inch)
    kern_size = sp_from_px(KERN_PX, theme.px_per_inch)
    ladder = ladder_sizes_px(BODY_SIZE_PX)

    metrics: dict[Face, FontMetrics] = {}
    absent: list[Face] = []
    # The roles this tab labels, not every `Face`: `Face.CODE_BOLD` has no file
    # of its own in the bundle and is backed by the bold prose file, so a row
    # for it would be a second "Bold" under another name -- the near-tie
    # `test_the_six_faces_come_out_six_distinguishable_widths` exists to refuse.
    for face in FACE_LABELS:
        try:
            metrics[face] = resolve(font_key(face, specimen_size))
        # Bare `Exception` and not `MissingFontError`: `resolve` is injected and a
        # caller's resolver may fail in its own way. `load_fonts` catches the same
        # breadth for the same reason -- a font swap costs a row, not the tab.
        except Exception:
            absent.append(face)

    resolved = char_measure(resolve) if measure is None else measure
    build = _Build(
        theme=theme,
        width=width,
        resolve=resolve,
        measure=resolved,
        labels=_Labels(
            [
                *(FACE_LABELS[face] for face in metrics),
                *(_px_label(size_px) for size_px in ladder),
                *_kern_labels(resolve, kern_size, theme),
            ],
            theme,
            resolve,
            resolved,
        ),
        metrics=metrics,
    )

    sections = [
        _faces_section(build, specimen_size),
        _ladder_section(build, ladder),
    ]
    kerning = _kerning_section(build, kern_size)
    if kerning is not None:
        sections.append(kerning)

    # The gap between two sections is the one the theme already puts above a
    # level-two heading, because that is what the next section opens with. Naming a
    # number here would put the specimen on a rhythm of its own.
    stack = _Stack()
    section_gap = theme.style(BlockKind.HEADING_2).space_above
    for index, section in enumerate(sections):
        if index:
            stack.gap(section_gap)
        stack.add(section.box, _skip(section.box.height))
    return Specimen(
        sections=tuple(sections),
        box=stack.packed(),
        gutter=build.labels.gutter,
        absent=tuple(absent),
    )


def _kern_labels(resolve: MetricsResolver, size: Scaled, theme: Theme) -> list[str]:
    """
    The gutter text for every kerning row, needed before the gutter can be sized.

    Resolved at the kerning section's own size and not at the specimen size: a kern
    is a fraction of the em, so the pixel figure in the gutter is only right for the
    size the pair is actually set at. Empty when the kerning face does not resolve,
    which is the same condition that drops the section entirely.
    """
    try:
        metrics = resolve(font_key(KERN_FACE, size))
    except Exception:
        return []
    return [
        _kern_label(round(metrics.kern(ord(left), ord(right))), theme.px_per_inch)
        for left, right in KERN_PAIRS
    ]


def _faces_section(build: _Build, size: Scaled) -> SpecimenSection:
    """
    One pangram per face, at one size, in `advtext.fontmetrics.Face`'s own order.
    """
    rows: list[SpecimenRow] = []
    for face, label in FACE_LABELS.items():
        metrics = build.at(face, size)
        if metrics is None:
            continue
        sample = _set(PANGRAM, face, size, metrics, build.measure)
        rows.append(build.row(label, face, size, [sample], sample.width))
    return build.section("The six faces", _FACES_NOTE, rows)


def _ladder_section(build: _Build, ladder: tuple[float, ...]) -> SpecimenSection:
    """
    One face up the modular scale, largest last so the ladder reads as a ladder.
    """
    rows: list[SpecimenRow] = []
    for size_px in ladder:
        size = sp_from_px(size_px, build.theme.px_per_inch)
        metrics = build.at(Face.PROSE, size)
        if metrics is None:
            continue
        label = _px_label(size_px)
        sample = _set(LADDER_TEXT, Face.PROSE, size, metrics, build.measure)
        rows.append(build.row(label, Face.PROSE, size, [sample], sample.width))
    return build.section("A size ladder", _LADDER_NOTE, rows)


def _kerning_section(build: _Build, size: Scaled) -> SpecimenSection | None:
    """
    Each pair set kerned and unkerned, in two columns of one measured width.

    `None` when the kerning face is absent. A section whose two columns were
    identical would read as a broken demonstration rather than as a missing font,
    and there is no honest fallback: of the six faces only the four Roboto ones
    carry a `kern` feature at all.
    """
    metrics = build.at(KERN_FACE, size)
    if metrics is None:
        return None

    measured: list[tuple[KernPair, Box, Box]] = []
    for left, right in KERN_PAIRS:
        kerned = _set(left + right, KERN_FACE, size, metrics, build.measure)
        plain = _set(left + right, KERN_FACE, size, metrics, build.measure, kerned=False)
        pair = KernPair(
            left=left,
            right=right,
            kern=round(metrics.kern(ord(left), ord(right))),
            kerned=kerned.width,
            unkerned=plain.width,
        )
        measured.append((pair, kerned, plain))

    # One column width for both settings and every pair, so the two columns line up
    # down the page and the difference is read off their right-hand ends. Sized from
    # the widest setting actually measured rather than from a round number, for the
    # reason the gutter is: a column that fits `AV` does not fit `Wa`.
    column = max(max(pair.kerned, pair.unkerned) for pair, _, _ in measured) + round(size * 0.4)
    # The gutter is left empty on the header row. A word there would sit one
    # `marker_gap` from the word over the first column, in the same face at the same
    # size, and the two read as one word -- "kernkerned", seen in a screenshot
    # before this comment was written. What the gutter holds is said in the note.
    header = _row(
        build.labels.caption(""),
        build.labels.gutter,
        build.labels.gap,
        [
            _fixed(build.labels.caption("kerned"), column, build.measure),
            build.labels.caption("not kerned"),
        ],
        build.measure,
    )
    rows = [
        build.row(
            _kern_label(pair.kern, build.theme.px_per_inch),
            KERN_FACE,
            size,
            [_fixed(kerned, column, build.measure), plain],
            kerned.width,
            pair,
        )
        for pair, kerned, plain in measured
    ]
    return build.section("Kerning, which the widget underneath cannot do", _KERN_NOTE, rows, header)

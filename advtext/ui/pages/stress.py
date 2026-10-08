r"""
The Stress page: several documents on screen at once, and what a frame of them costs.

A host does not show one document. It shows a transcript beside a diff beside a
log, several of them still being written, and what it can afford is whatever all
of them cost together in one frame. This page puts 1 to 16 panes in a grid, each
with a view of its own over `demo/sample.md`, and times the library's part of
every frame.

## The controls

- **panes** -- how many, 1 to 16, in a grid as near square as it goes.
- **length** -- the document is `demo/sample.md` once, five times or twenty
  times over. Longer documents are what culling is for: a pane shows the same
  screenful whatever the length.
- **all streaming** -- each pane becomes a `StreamView` whose document arrives
  a few characters at a time and starts again when it is finished, so there is
  always a block still being written in every pane. Otherwise each pane is a
  `BareView` over a finished document.
- **select all in every pane** -- every pane draws a whole-document selection.
  A selection belongs to one view at a time (`BareView.owns_selection`), so
  the page selects each pane again just before drawing it.

## The readout, and exactly what is in it

Timed with `time.perf_counter` around two calls per pane per frame:

- **layout** is `view.layout_for(width)`, and for a streaming pane the
  `view.sync()` before it, which is where what arrived is parsed. On a frame
  where nothing changed this is a cache hit and costs microseconds.
- **draw** is `view.draw(...)` after that: culling to the pane's window,
  building and submitting the draw-list calls, the selection highlight, hit
  testing and the copy shortcut.

Each is shown as a **rolling median** over the last `WINDOW` frames, per pane
and summed over panes. A median, so one slow frame -- a first layout, a
garbage collection -- does not sit in the figure for a second.

**Three figures, because the sum alone was misread** (review 2 measured a
streaming view at about 2 ms a frame whether 1 or 16 of them ran, where this
page's totals for 1, 4 and 16 panes read as though a view got dearer in
company):

- **the total** is the sum over panes: what the library costs this frame.
  It grows with the pane count because every view is laid out and drawn and
  nothing is shared between views.
- **per view** is that total over the number of panes. This is the figure to
  compare across pane counts -- with one caution the page states beside it:
  the panes share the window, so more panes means a narrower measure in each
  (`pane measure`), and a narrower measure is more lines.
- **per piece of text** is, for each frame in which a streaming pane took
  text, that pane's layout and draw over the number of pieces it took. A
  frame is not a piece: at 40 pieces a second and 60 frames a second a pane
  takes a piece on two frames of three, and a frame that runs long takes
  more pieces at once, so cost per frame rises with frame time while cost
  per piece falls. Both are shown, with the pieces a frame.

**The streaming panes are staggered.** Each starts at another place in the
document (pane `i` of sixteen starts `i` sixteenths in, fed in one go before
anything is timed; its first layout is one cold sample the median forgets)
and takes its pieces on other frames (a fraction of a piece of head start).
Started together on one clock they all reached the same long table on the
same frame, and the page measured that one event once per pane.

**Not included**: ImGui's own work on what was submitted (tessellation, the
render, the buffer swap); the grid's child windows; this page's own readout;
feeding the streams; and the second culling pass the page runs to count units,
below. So the figure is the library's cost inside the frame and is less than
the frame.

- **glyphs** -- `DrawStats.glyphs`, the glyphs submitted this frame, all panes.
- **units drawn / culled** -- a document is laid out as units, one per block
  or per piece of a long block. Drawn is how many met the pane's window this
  frame; culled is the rest. Counted by asking the layout again
  (`UnitLayout.visible_units`) after the draw and outside the timing.

## The reference line

pptmstr shows several panes at once and treats about 1.7 ms a frame as too much
for a block that is still being written. The readout shows the summed median
beside that figure, and their ratio. **It does not say whether the figure is
met, and it is not this page's to say**: the number here is from this machine,
this renderer and this window, and 1.7 ms is another project's line for another
workload.

## Caches are per view, and that is in the numbers

Each `BareView` (and so each `StreamView`) owns its `LayoutCache` and its
`UnitCache`; nothing in the library shares them between views. Sixteen panes
over the same text therefore lay it out sixteen times, and the first frame after
a change of pane count, length or width costs sixteen cold layouts -- seen as a
jump in the layout figure that the median then forgets. The steady figure is
unaffected: an unchanged document is a hit in its own view's cache. What *is*
shared is below the views: font metrics and the glyph measure, which are
process-wide, and the parsed `Document`, which this page builds once per length
and hands to every finished pane, since a `Document` is immutable. Streaming
panes each parse their own.

## What has been run

`tests/test_page_stress.py` checks the arithmetic and that the counters count
what they say, in frames of an ImGui context with no backend, and runs the page
in a real window at 1, 4 and 16 panes. Those window figures come from a
software rasteriser on a virtual display and are labelled so wherever they are
written down.

Options (`--tab stress:...`): an integer is the number of panes; `streaming`,
`selected`, `x5` and `x20` are the toggles.
"""

from __future__ import annotations

import math
import re
import statistics
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats
from advtext.markdown import Document, build_document
from advtext.pack import CharMeasure
from advtext.stream import StreamDocument
from advtext.style import MetricsResolver, Theme, fontlib_metrics
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView
from advtext.ui.pages import PageContext, PageSpec, caption, demo_text
from advtext.ui.stream_view import StreamView
from advtext.units import DEFAULT_PX_PER_INCH, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from advtext.backends.imgui_draw import FaceFont

__all__ = [
    "LENGTHS",
    "MAX_PANES",
    "PAGE",
    "REFERENCE_MS",
    "WINDOW",
    "Pane",
    "Rolling",
    "Stress",
    "StressPage",
    "grid_shape",
    "readouts",
    "repeated",
]

MAX_PANES: Final = 16
LENGTHS: Final = (1, 5, 20)
"""
How many copies of the source a pane's document is. The three the length control offers.
"""

WINDOW: Final = 60
"""
Frames in the rolling median: about a second at a display's refresh rate.
"""

REFERENCE_MS: Final = 1.7
"""
The per-frame figure pptmstr treats as too much for a block still being written.

Shown beside the measured total as a line to read against. Another project's
number for another workload; nothing here asserts it is met or missed.
"""

STREAM_TOKENS_PER_SECOND: Final = 40.0
"""
How fast each streaming pane's text arrives. Roughly a hosted model; not a claim.
"""

FALLBACK: Final = (
    "# Stress\n\nNo `demo/` directory was found, so every pane holds this paragraph "
    "instead of the sample document. It is long enough to break onto a few lines.\n"
)


def repeated(source: str, copies: int) -> str:
    """
    `source` `copies` times over, as one markdown document with a blank line between copies.
    """
    return "\n\n".join([source.rstrip("\n")] * max(1, copies)) + "\n"


def grid_shape(panes: int) -> tuple[int, int]:
    """
    `(columns, rows)` for `panes` panes: as near square as it goes, wider than tall.

    The smallest number of columns whose square holds them, and only as many
    rows as are used: 4 is 2 x 2, 5 is 3 x 2, 16 is 4 x 4.
    """
    panes = max(1, panes)
    columns = math.ceil(math.sqrt(panes))
    return columns, math.ceil(panes / columns)


class Rolling:
    """
    The last `size` samples of one quantity, and their median.

    Seconds in, milliseconds out. Zero before the first sample rather than an
    error, because a readout is drawn before anything has been timed.
    """

    def __init__(self, size: int = WINDOW) -> None:
        self.samples: deque[float] = deque(maxlen=size)

    def add(self, seconds: float) -> None:
        self.samples.append(seconds)

    def clear(self) -> None:
        self.samples.clear()

    @property
    def median_ms(self) -> float:
        return statistics.median(self.samples) * 1000.0 if self.samples else 0.0

    @property
    def last_ms(self) -> float:
        return self.samples[-1] * 1000.0 if self.samples else 0.0

    @property
    def worst_ms(self) -> float:
        return max(self.samples) * 1000.0 if self.samples else 0.0


@dataclass
class Pane:
    """
    One pane: a view, the stream behind it if it has one, and what its frames cost.
    """

    view: BareView
    stream: StreamDocument | None = None
    pieces: list[str] = field(default_factory=list)
    fed: int = 0
    laps: int = 0
    """How many times a streaming pane has finished its document and started it again."""
    took: int = 0
    """How many pieces the last `Stress.feed` gave this pane."""
    layout: Rolling = field(default_factory=Rolling)
    draw: Rolling = field(default_factory=Rolling)
    per_piece: Rolling = field(default_factory=Rolling)
    """Layout plus draw over the pieces taken, for the frames in which any were."""
    taken: deque[int] = field(default_factory=lambda: deque(maxlen=WINDOW))
    """Pieces taken on each of the last `WINDOW` frames."""
    width_px: float = 0.0
    """The measure this pane was last laid out to, in pixels."""
    glyphs: int = 0
    units_total: int = 0
    units_drawn: int = 0
    _owed: float = 0.0

    @property
    def units_culled(self) -> int:
        return self.units_total - self.units_drawn

    def sample(self, layout_seconds: float, draw_seconds: float) -> None:
        """
        One frame's two times, and -- if the pane took text this frame -- their sum per piece.
        """
        self.layout.add(layout_seconds)
        self.draw.add(draw_seconds)
        self.taken.append(self.took)
        if self.took > 0:
            self.per_piece.add((layout_seconds + draw_seconds) / self.took)


def _pieces(source: str) -> list[str]:
    """
    `source` in pieces of at most four visible characters, each with the white space before it.
    """
    return re.findall(r"\s*\S{1,4}|\s+", source)


@dataclass
class Stress:
    """
    The page's state and its per-frame work, with nothing that needs a window in the logic.

    `configure` rebuilds the panes when a control changes; `feed` moves the
    streaming panes' clocks; `frame` is one pane's timed layout and draw.
    """

    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver = fontlib_metrics
    px_per_inch: float = DEFAULT_PX_PER_INCH
    source: str | None = None
    """The text of one copy. `demo/sample.md` when `None`."""
    timer: Callable[[], float] = time.perf_counter

    count: int = 4
    length: int = 1
    streaming: bool = False
    select_all: bool = False

    panes: list[Pane] = field(default_factory=list, init=False)
    _built: tuple[int, bool] | None = field(default=None, init=False)
    _documents: dict[int, Document] = field(default_factory=dict, init=False)
    _texts: dict[int, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.source is None:
            found = demo_text("sample.md")
            self.source = FALLBACK if found is None else found
        self.configure()

    # -- material ------------------------------------------------------

    def text(self, length: int) -> str:
        """
        The markdown of a pane's document at `length` copies. Built once per length.
        """
        if length not in self._texts:
            assert self.source is not None
            self._texts[length] = repeated(self.source, length)
        return self._texts[length]

    def document(self, length: int) -> Document:
        """
        The parsed document at `length` copies, built once and shared by every finished pane.

        Shared because a `Document` is immutable and parsing twenty copies
        sixteen times over is a second of nothing to look at. The views do not
        share anything derived from it: each lays it out in its own caches.
        """
        if length not in self._documents:
            self._documents[length] = build_document(self.text(length), self.theme, self.metrics)
        return self._documents[length]

    # -- panes ---------------------------------------------------------

    def configure(self) -> None:
        """
        Make the panes match the controls. Does nothing if they already do.

        A change of length or of streaming rebuilds every pane, since every
        pane's document is different. A change of count alone keeps the panes
        there are -- with their warm caches and their medians -- and adds or
        drops at the end.
        """
        self.count = max(1, min(MAX_PANES, self.count))
        if self.length not in LENGTHS:
            self.length = LENGTHS[0]
        kind = (self.length, self.streaming)
        if kind != self._built:
            self.panes = []
            self._built = kind
        del self.panes[self.count :]
        while len(self.panes) < self.count:
            self.panes.append(self._pane(len(self.panes)))

    def _pane(self, index: int = 0, *, restart: bool = False) -> Pane:
        """
        Pane `index`. A streaming one is staggered against the others unless it is a restart.

        Staggered in place -- it is given the first `index` sixteenths of its
        document at once, here, before anything is timed -- and in time: a
        fraction of a piece of head start, so that it takes its pieces on
        other frames than its neighbours. A pane starting its document again
        starts at the beginning: it is out of step with the rest already.
        """
        if not self.streaming:
            view = BareView(
                document=self.document(self.length),
                theme=self.theme,
                measure=self.measure,
                px_per_inch=self.px_per_inch,
            )
            return Pane(view=view)
        stream = StreamDocument(self.theme, self.metrics)
        pieces = _pieces(self.text(self.length))
        pane = Pane(
            view=StreamView(stream, self.measure, px_per_inch=self.px_per_inch),
            stream=stream,
            pieces=pieces,
        )
        if not restart:
            pane.fed = index * len(pieces) // MAX_PANES
            if pane.fed:
                stream.append("".join(pieces[: pane.fed]))
            # Sevenths of the pane count, so that neighbours are far apart in
            # phase: 0, 7/16, 14/16, 5/16, ... and no two of sixteen coincide.
            pane._owed = (index * 7 % MAX_PANES) / MAX_PANES
        return pane

    def feed(self, seconds: float) -> int:
        """
        Give every streaming pane the pieces `seconds` allow. Returns how many, all panes.

        A pane that has had its whole document is started again from nothing
        on the next call -- a new stream and a new view -- so that there is
        always something still being written. That restart is a cold layout
        and shows in the figures as one.
        """
        total = 0
        for index, pane in enumerate(self.panes):
            if pane.stream is None:
                continue
            if pane.fed >= len(pane.pieces):
                fresh = self._pane(index, restart=True)
                fresh.laps = pane.laps + 1
                fresh.layout, fresh.draw = pane.layout, pane.draw
                fresh.per_piece, fresh.taken = pane.per_piece, pane.taken
                self.panes[index] = pane = fresh
            assert pane.stream is not None
            pane._owed += max(0.0, seconds) * STREAM_TOKENS_PER_SECOND
            count = min(int(pane._owed + 1e-6), len(pane.pieces) - pane.fed)
            pane._owed -= count
            for piece in pane.pieces[pane.fed : pane.fed + count]:
                pane.stream.append(piece)
            pane.fed += count
            pane.took = count
            total += count
        return total

    # -- one pane, one frame -------------------------------------------

    def frame(self, pane: Pane, fonts: FaceFont, imgui: Any) -> DrawStats:
        """
        One pane's frame inside its child window: timed layout, timed draw, then the counts.

        The layout is asked for first, at the width `draw` is about to choose,
        so that `draw`'s own request for it is a hit and the two times do not
        overlap.
        """
        view = pane.view
        if self.select_all:
            # Before the draw and outside the timing: ownership of the
            # selection passes to this pane for the length of its own draw.
            view.select_all()
        width_px = max(imgui.get_content_region_avail().x, MIN_WIDTH_PX)

        began = self.timer()
        if isinstance(view, StreamView):
            view.sync()
        layout = view.layout_for(sp_from_px(width_px, self.px_per_inch))
        laid = self.timer()
        stats = view.draw(fonts=fonts, palette=DARK_PALETTE, width_px=width_px)
        drawn = self.timer()

        pane.sample(laid - began, drawn - laid)
        pane.width_px = width_px
        pane.glyphs = stats.glyphs

        # Counted after the fact, from the same three numbers the view culled
        # with. This is a second culling pass and it is not in the times above.
        origin = view.origin
        pane.units_total = len(layout.placed)
        if origin is None:
            pane.units_drawn = 0
        else:
            viewport = view.viewport_in(
                origin[1], imgui.get_window_pos().y, imgui.get_window_size().y
            )
            pane.units_drawn = sum(1 for _ in layout.visible_units(viewport))
        return stats

    # -- totals --------------------------------------------------------

    @property
    def layout_ms(self) -> float:
        """The sum over panes of each pane's median layout time."""
        return sum(pane.layout.median_ms for pane in self.panes)

    @property
    def draw_ms(self) -> float:
        """The sum over panes of each pane's median draw time."""
        return sum(pane.draw.median_ms for pane in self.panes)

    @property
    def total_ms(self) -> float:
        return self.layout_ms + self.draw_ms

    @property
    def per_view_ms(self) -> float:
        """The total over the number of panes: what one view costs a frame, on average."""
        return self.total_ms / len(self.panes) if self.panes else 0.0

    @property
    def per_piece_ms(self) -> float | None:
        """
        The median, over the panes that took any text, of each one's median cost per piece.

        `None` when no pane has taken a piece in its window: nothing is streaming.
        """
        medians = [pane.per_piece.median_ms for pane in self.panes if pane.per_piece.samples]
        return statistics.median(medians) if medians else None

    @property
    def pieces_per_frame(self) -> float:
        """Pieces taken per view per frame, over the panes' windows. Zero when none were."""
        frames = sum(len(pane.taken) for pane in self.panes)
        return sum(sum(pane.taken) for pane in self.panes) / frames if frames else 0.0

    @property
    def pane_px(self) -> float:
        """The measure the panes were last laid out to: the first pane's, in pixels."""
        return self.panes[0].width_px if self.panes else 0.0

    @property
    def glyphs(self) -> int:
        return sum(pane.glyphs for pane in self.panes)

    @property
    def units_drawn(self) -> int:
        return sum(pane.units_drawn for pane in self.panes)

    @property
    def units_culled(self) -> int:
        return sum(pane.units_culled for pane in self.panes)

    def forget(self) -> None:
        """
        Empty every median, so the next figures are of the frames from now on.
        """
        for pane in self.panes:
            pane.layout.clear()
            pane.draw.clear()
            pane.per_piece.clear()
            pane.taken.clear()


def readouts(stress: Stress) -> tuple[str, ...]:
    """
    The page's readout lines: totals, the reference line, what is left out, and per view.

    Numbers and what they are of. The ratio to the reference is arithmetic; no
    line says whether it is met.
    """
    total = stress.total_ms
    per_view = stress.per_view_ms
    per_piece = stress.per_piece_ms
    piece = (
        "per piece of text: none taken"
        if per_piece is None
        else f"per piece of text {per_piece:.2f} ms, at {stress.pieces_per_frame:.2f} "
        "pieces a view a frame"
    )
    kind = "StreamView, text arriving" if stress.streaming else "BareView, finished"
    return (
        f"{len(stress.panes)} panes ({kind})  ·  document x{stress.length}"
        f"  ·  median of the last {WINDOW} frames, summed over panes:"
        f"  layout {stress.layout_ms:.2f} ms  +  draw {stress.draw_ms:.2f} ms"
        f"  =  {total:.2f} ms",
        f"reference line {REFERENCE_MS:.1f} ms a frame (pptmstr's figure for a live block)"
        f"  ·  this total is {total / REFERENCE_MS:.2f} x that",
        f"glyphs submitted {stress.glyphs}  ·  units drawn {stress.units_drawn}"
        f", culled {stress.units_culled}",
        "timed: the views' layout_for and draw calls.  not timed: ImGui's render, "
        "the child windows, this readout.  each pane has its own layout caches.",
        f"per view {per_view:.2f} ms a frame ({per_view / REFERENCE_MS:.2f} x the reference line)"
        f"  ·  {piece}  ·  pane measure {stress.pane_px:.0f} px",
        "the total rises with the pane count because every view is laid out and drawn "
        "and nothing is shared between views; per view is the figure to set beside "
        "another pane count, at another pane measure.  a frame is not a piece of text: "
        "a longer frame takes more pieces.  streaming panes are staggered in place and in time.",
    )


def report(stress: Stress) -> str:
    """
    One line of figures for an unattended run. Counts and milliseconds, no judgement.
    """
    samples = min((len(pane.draw.samples) for pane in stress.panes), default=0)
    return (
        f"panes={len(stress.panes)} streaming={int(stress.streaming)} length={stress.length} "
        f"samples={samples} layout_ms={stress.layout_ms:.3f} draw_ms={stress.draw_ms:.3f} "
        f"total_ms={stress.total_ms:.3f} glyphs={stress.glyphs} "
        f"units_drawn={stress.units_drawn} units_culled={stress.units_culled} "
        f"per_view_ms={stress.per_view_ms:.3f} "
        f"per_piece_ms={-1.0 if stress.per_piece_ms is None else stress.per_piece_ms:.3f} "
        f"pieces_per_frame={stress.pieces_per_frame:.3f} pane_px={stress.pane_px:.0f}"
    )


class StressPage:
    """
    The page: a `Stress` and the frame that draws its grid.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        words = context.options_for(PAGE.name)
        count = context.count_for(PAGE.name)
        self.stress = Stress(
            theme=context.theme,
            measure=context.measure,
            metrics=context.metrics,
            px_per_inch=context.px_per_inch,
            count=4 if count is None else count,
            length=20 if "x20" in words else 5 if "x5" in words else 1,
            streaming="streaming" in words,
            select_all="selected" in words,
        )

    def draw(self) -> None:
        from imgui_bundle import imgui

        stress = self.stress
        self._controls(imgui)
        stress.configure()
        for line in readouts(stress):
            caption(line)
        imgui.separator()

        stress.feed(imgui.get_io().delta_time)
        columns, rows = grid_shape(len(stress.panes))
        spacing = imgui.get_style().item_spacing
        available = imgui.get_content_region_avail()
        width = max((available.x - spacing.x * (columns - 1)) / columns, 1.0)
        height = max((available.y - spacing.y * (rows - 1)) / rows, 1.0)
        for index, pane in enumerate(stress.panes):
            if index % columns:
                imgui.same_line()
            imgui.begin_child(
                f"##advtext-stress-{index}",
                imgui.ImVec2(width, height),
                imgui.ChildFlags_.borders.value,
                imgui.WindowFlags_.always_vertical_scrollbar.value,
            )
            pane.view.debug = self.context.debug
            stress.frame(pane, self.context.fonts, imgui)
            imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        stress = self.stress
        imgui.set_next_item_width(200.0)
        changed, count = imgui.slider_int("panes", stress.count, 1, MAX_PANES)
        if changed:
            stress.count = count
        for length in LENGTHS:
            imgui.same_line()
            if imgui.radio_button(f"x{length}", stress.length == length):
                stress.length = length
        imgui.same_line()
        _, stress.streaming = imgui.checkbox("all streaming", stress.streaming)
        imgui.same_line()
        was = stress.select_all
        _, stress.select_all = imgui.checkbox("select all in every pane", stress.select_all)
        if was and not stress.select_all:
            for pane in stress.panes:
                pane.view.clear_selection()


PAGE = PageSpec(
    name="Stress",
    order=410,
    factory=StressPage,
    group="Performance",
    caption="1 to 16 panes at once, with the library's per-frame cost",
    options=("streaming", "selected", "x5", "x20"),
    shots=("4", "16,streaming"),
)

r"""
The Stream page: one source replayed as tokens into two views at once, with
counters for what moved and what it cost.

A model writes an answer a few characters at a time and a host has to show it
while it is being written. This page replays a markdown file that way through
`advtext.stream.StreamDocument` and `advtext.ui.stream_view.StreamView`, twice
over, in two panes fed the same pieces on the same clock:

- **`KEEP_STREAMED`** on the left: a finished block stays broken the way it was
  while it streamed.
- **`RESET`** on the right: a finished block is set again as the theme sets it
  (justified, here), once, at the moment it is finished.

Everything else on the page is there to let somebody see the difference between
those two and what either costs: a rate slider, pause, single step, restart, a
picker of sources chosen to be hard, a bar in the margin beside whatever is
still unfinished, and readouts.

## The readouts, and what they do and do not say

**They report change and cost. None of them is a measure of quality**
(`docs/visual-review.md`, rule 1). A count of zero settled lines moved is a
fact about positions; it does not say the text reads well, and a count above
zero does not say it reads badly -- `RESET` moves lines on purpose.

- **Settled lines moved.** After each layout, the lines now set are compared
  with the lines of the layout before. A line is its block, its baseline and
  each glyph's codepoint and x. Every line of the earlier layout but its last
  -- the one still being written -- is looked for unchanged in the new one;
  each that is missing counts. The lines are asked of the view through
  `StreamView.set_lines`, and only for the blocks that had not committed as of
  the layout before, so the cost of counting does not grow with the document.
  **A change of width is not a move**: a layout at a new width starts the
  comparison over and counts nothing.
- **Cost of an append, in three parts.** *parse* is `StreamView.sync`, the one
  place a frame parses what arrived. *layout* is `StreamView.layout_for` at the
  pane's width. *draw* is the rest of `StreamView.draw` on that frame: culling,
  the draw calls, hit testing. A frame may take in several pieces, so each
  figure is per layout, shown as the latest, the mean over the replay and the
  largest. Frames on which nothing arrived are not counted. These are
  wall-clock times of this process on this machine at this moment.
- **Blocks, committed and live.** How many blocks the stream will not touch
  again, and how many it still may.

## The mark beside the unfinished end

A bar in the pane's left padding runs from the top of the first live block to
the bottom of the last. Where it starts is the commit boundary. It is drawn by
this page from public facts -- `stream.committed`, `view.layout.placed`,
`view.origin` -- and is not part of the view.

## The sources

`demo/stream.md` and five files under `demo/stream/`, each one case:
numbered steps with fences and indented paragraphs under the numbers; a
thirty-row table; a six-hundred-line code block; an address too wide for any
pane in the middle of a paragraph, with reference-style links, which a stream
shows as typed, by design; and plain prose. An installed wheel has no `demo/`
and gets one built-in paragraph.

## What has been run

`tests/test_page_stream.py` drives whole replays with a clock advanced by
hand, holds the counter to what first-fit predicts, runs the page in ImGui
frames with no backend, and runs it in a real window at a rate slow enough
that the stream spans many layouts. Nobody has watched it. Whether either
policy is comfortable to read at any rate is what the page exists to let a
person judge.

The logic here is the precedent `examples/stream_replay.py` set, restated
rather than imported: an example is not part of the package.

Options (`--tab stream:...`): a source key (`steps`, `table`, `code`, `links`,
`prose`) picks the source; `done` feeds the whole source on the first frame;
an integer is the tokens per second.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats, rgba
from advtext.pack import CharMeasure
from advtext.stream import CommitPolicy, StreamDocument
from advtext.style import MetricsResolver, Theme, fontlib_metrics
from advtext.ui.bare_view import MIN_WIDTH_PX, SetLine
from advtext.ui.pages import PageContext, PageSpec, caption, demo_text
from advtext.ui.stream_view import StreamView
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from advtext.backends.imgui_draw import FaceFont

__all__ = [
    "DEFAULT_TOKENS_PER_SECOND",
    "FALLBACK",
    "MAX_TOKENS_PER_SECOND",
    "PAGE",
    "SOURCES",
    "Cost",
    "Lane",
    "Session",
    "Source",
    "StreamPage",
    "changed_lines",
    "live_span",
    "readouts",
    "tokens",
]

DEFAULT_TOKENS_PER_SECOND: Final = 40.0
"""
Roughly what a hosted model produces. A starting point for the slider and not a claim.
"""

MAX_TOKENS_PER_SECOND: Final = 2000.0

LIVE_MARK: Final = rgba(0xD9, 0x8E, 0x2B)
"""
The bar beside the unfinished blocks. Not a palette role: it is this page's own chrome.
"""

FALLBACK: Final = (
    "No `demo/` directory was found, so this is the only source: one paragraph, "
    "long enough to break onto a few lines, fed a few characters at a time. A "
    "checkout has six sources to pick from.\n"
)


@dataclass(frozen=True, slots=True)
class Source:
    """
    One entry of the source picker: its option word, its label, and its file under `demo/`.
    """

    key: str
    label: str
    path: str

    def text(self) -> str:
        """
        The file's text, or `FALLBACK` where there is no `demo/` to read.
        """
        found = demo_text(self.path)
        return FALLBACK if found is None else found


SOURCES: Final = (
    Source("mixed", "mixed answer", "stream.md"),
    Source("steps", "numbered steps", "stream/steps.md"),
    Source("table", "30-row table", "stream/table.md"),
    Source("code", "600-line code block", "stream/code.md"),
    Source("links", "wide URL, reference links", "stream/links.md"),
    Source("prose", "plain prose", "stream/prose.md"),
)
"""
The picker, in order. The first is what the page opens on.
"""


def tokens(source: str) -> list[str]:
    """
    `source` cut into pieces of at most four visible characters, as a model's tokens are.

    Each piece carries the white space in front of it, so the pieces
    concatenate back to exactly `source` and a paragraph break arrives with
    the first characters of the paragraph after it. The cut is arbitrary and
    is meant to be: a stream does not break where markdown would like, and
    `**` is as likely to arrive split in two as whole.
    """
    return re.findall(r"\s*\S{1,4}|\s+", source)


def changed_lines(before: list[SetLine], after: list[SetLine]) -> list[SetLine]:
    """
    The settled lines of `before` that are not in `after` exactly as they were.

    "Settled" is every line but the last, which is the one being written.
    "As they were" is the same glyphs at the same x on the same baseline: a
    line that kept its words and shifted by a scaled point has moved.
    """
    present = set(after)
    return [line for line in before[:-1] if line not in present]


def live_span(view: StreamView) -> tuple[Scaled, Scaled] | None:
    """
    From the top of the first unfinished block to the bottom of the last, in document units.

    `None` when the view has no layout or nothing is unfinished. Read from the
    end of the layout backwards and stopped at the first settled unit, so it
    costs the live units and not the document.

    As of the view's last `sync`: `stream.committed` is read here, so call
    this after drawing and before appending more, as `Lane.observe` is.
    """
    layout = view.layout
    if layout is None:
        return None
    settled = len(view.stream.committed)
    top: Scaled | None = None
    bottom: Scaled = 0
    for unit in reversed(layout.placed):
        blocks = unit.block_range
        if blocks.stop <= settled:
            break
        if top is None:
            bottom = unit.bottom
        top = unit.y
    return None if top is None else (top, bottom)


@dataclass(slots=True)
class Cost:
    """
    One part of an append's cost over a replay: the latest, the sum, the largest, and how many.

    Seconds in, milliseconds out; `mean_ms` is zero before the first sample
    rather than an error, because a readout is drawn before anything arrives.
    """

    last: float = 0.0
    total: float = 0.0
    worst: float = 0.0
    count: int = 0

    def add(self, seconds: float) -> None:
        self.last = seconds
        self.total += seconds
        self.worst = max(self.worst, seconds)
        self.count += 1

    @property
    def last_ms(self) -> float:
        return self.last * 1000.0

    @property
    def mean_ms(self) -> float:
        return self.total * 1000.0 / self.count if self.count else 0.0

    @property
    def worst_ms(self) -> float:
        return self.worst * 1000.0


@dataclass
class Lane:
    """
    One policy's half of the page: a stream, the view over it, and what was counted.

    All of it runs without a window. `take` appends, `lay_out` is the timed
    parse and layout a frame does, `observe` counts the lines that layout
    moved; `Session.tick` calls the three in order and `StreamPage` calls them
    around a real `draw`.
    """

    policy: CommitPolicy
    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver = fontlib_metrics
    px_per_inch: float = DEFAULT_PX_PER_INCH
    timer: Callable[[], float] = time.perf_counter

    stream: StreamDocument = field(init=False)
    view: StreamView = field(init=False)
    moved: int = field(default=0, init=False)
    """Settled lines that moved, in total, since the replay began."""
    moves: list[tuple[int, int]] = field(default_factory=list, init=False)
    """`(pieces taken so far, lines moved)` for each layout in which any did."""
    changed: list[SetLine] = field(default_factory=list, init=False)
    """The lines the latest counted layout moved, as they were before it."""
    taken: int = field(default=0, init=False)
    parse: Cost = field(default_factory=Cost, init=False)
    layout: Cost = field(default_factory=Cost, init=False)
    draw: Cost = field(default_factory=Cost, init=False)
    stats: DrawStats | None = field(default=None, init=False)
    _lines: list[SetLine] = field(default_factory=list, init=False)
    _seen: Any = field(default=None, init=False)
    _settled: int = field(default=0, init=False)
    _fresh: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.restart()

    def restart(self) -> None:
        """
        Begin again from nothing: a new stream, a new view, every count at zero.
        """
        self.stream = StreamDocument(self.theme, self.metrics, policy=self.policy)
        self.view = StreamView(self.stream, self.measure, px_per_inch=self.px_per_inch)
        self.moved = 0
        self.moves = []
        self.changed = []
        self.taken = 0
        self.parse = Cost()
        self.layout = Cost()
        self.draw = Cost()
        self.stats = None
        self._lines = []
        self._seen = None
        self._settled = 0
        self._fresh = False

    def take(self, pieces: list[str], *, close: bool = False) -> None:
        """
        Append `pieces` to the stream, and close it if that was the last of them.
        """
        for piece in pieces:
            self.stream.append(piece)
        self.taken += len(pieces)
        if close and not self.stream.closed:
            self.stream.close()

    def lay_out(self, width: Scaled) -> bool:
        """
        Parse what arrived and lay out at `width`, timing each. True if anything had arrived.

        A frame on which nothing arrived adds no sample: its parse is a
        comparison of two integers and its layout is a cache hit, and averaging
        those in would make an append look cheaper the longer the page idled.
        A layout forced by a change of width alone is not an append either.
        """
        began = self.timer()
        self._fresh = self.view.sync()
        parsed = self.timer()
        self.view.layout_for(width)
        laid = self.timer()
        if self._fresh:
            self.parse.add(parsed - began)
            self.layout.add(laid - parsed)
        return self._fresh

    def observe(self) -> int:
        """
        Count the settled lines the latest layout moved. Call after the view has laid out.

        Does nothing, and returns zero, if the view's layout is the one already
        counted. A layout at a different width from the last one counted also
        counts nothing -- every line moved, and none of them because of the
        stream -- and becomes what the next layout is compared with.

        Only the blocks that were not yet committed at the last layout are
        asked for; the module docstring says why that is all that can have
        moved. Call this before appending anything more: it reads
        `stream.committed` as the number of blocks the layout had settled.
        """
        layout = self.view.layout
        if layout is None or layout is self._seen:
            return 0
        resized = self._seen is not None and layout.width != self._seen.width
        lines = list(self.view.set_lines(0 if resized else self._settled))
        self.changed = [] if self._seen is None or resized else changed_lines(self._lines, lines)
        moved = len(self.changed)
        if moved:
            self.moved += moved
            self.moves.append((self.taken, moved))
        self._settled = len(self.stream.committed)
        self._lines = [line for line in lines if line.block >= self._settled]
        self._seen = layout
        return moved

    def show(self, fonts: FaceFont, imgui: Any) -> DrawStats:
        """
        This lane's view in the current window, with the live mark. One frame.

        Call inside a child window that scrolls. The layout is done first and
        timed on its own, at the width `draw` is about to choose, so the time
        `draw` then takes is drawing and not laying out.
        """
        width_px = max(imgui.get_content_region_avail().x, MIN_WIDTH_PX)
        fresh = self.lay_out(sp_from_px(width_px, self.px_per_inch))
        began = self.timer()
        stats = self.view.draw(fonts=fonts, palette=DARK_PALETTE, width_px=width_px)
        if fresh:
            self.draw.add(self.timer() - began)
        self.stats = stats
        self.observe()

        span = live_span(self.view)
        origin = self.view.origin
        if span is not None and origin is not None:
            top = origin[1] + px_from_sp(span[0], self.px_per_inch)
            bottom = origin[1] + px_from_sp(span[1], self.px_per_inch)
            imgui.get_window_draw_list().add_rect_filled(
                imgui.ImVec2(origin[0] - 8.0, top),
                imgui.ImVec2(origin[0] - 5.0, bottom),
                LIVE_MARK,
            )
        return stats

    def describe(self) -> tuple[str, str]:
        """
        This lane's two readout lines: counts, then cost. Change and cost, no judgement.
        """
        committed = len(self.stream.committed)
        live = len(self.stream.blocks) - committed
        layouts = self.view.relayouts
        counts = (
            f"{self.policy.name}  ·  blocks: {committed} committed, {live} live"
            f"  ·  settled lines moved: {self.moved} (in {len(self.moves)} of {layouts} layouts)"
        )
        cost = (
            "ms per layout, last / mean / max"
            f"  ·  parse {_three(self.parse)}"
            f"  ·  layout {_three(self.layout)}"
            f"  ·  draw {_three(self.draw)}"
        )
        return counts, cost


def _three(cost: Cost) -> str:
    return f"{cost.last_ms:.2f} / {cost.mean_ms:.2f} / {cost.worst_ms:.2f}"


@dataclass
class Session:
    """
    One replay of one source into every lane: the pieces, the clock, and the controls.

    `advance(seconds)` is what a frame's worth of time does; `step`, `pause`
    and `restart` are the buttons; `choose` is the picker. None of it needs a
    window, and the time is always passed in, so a test advances the clock by
    hand and a whole replay runs in a loop (`tick`).

    Both lanes are handed the same pieces in the same call, so at every moment
    they hold the same text and differ only in policy.
    """

    theme: Theme
    measure: CharMeasure
    metrics: MetricsResolver = fontlib_metrics
    px_per_inch: float = DEFAULT_PX_PER_INCH
    source: Source = SOURCES[0]
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    paused: bool = False
    timer: Callable[[], float] = time.perf_counter
    text: str | None = None
    """The text to replay in place of `source`'s file. For a test, or a host's own text."""

    pieces: list[str] = field(init=False)
    fed: int = field(default=0, init=False)
    lanes: tuple[Lane, ...] = field(init=False)
    _owed: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.lanes = tuple(
            Lane(policy, self.theme, self.measure, self.metrics, self.px_per_inch, self.timer)
            for policy in (CommitPolicy.KEEP_STREAMED, CommitPolicy.RESET)
        )
        self.pieces = tokens(self.source.text() if self.text is None else self.text)

    def lane(self, policy: CommitPolicy) -> Lane:
        """
        The lane running under `policy`.
        """
        for lane in self.lanes:
            if lane.policy is policy:
                return lane
        raise KeyError(policy)

    @property
    def done(self) -> bool:
        """
        Whether every piece has been fed and the streams closed.
        """
        return self.fed >= len(self.pieces) and all(lane.stream.closed for lane in self.lanes)

    def restart(self) -> None:
        """
        Begin the same source again from nothing. The rate and the pause are left as they are.
        """
        for lane in self.lanes:
            lane.restart()
        self.fed = 0
        self._owed = 0.0

    def choose(self, source: Source, text: str | None = None) -> None:
        """
        Replay `source` instead, from the beginning.
        """
        self.source = source
        self.text = text
        self.pieces = tokens(source.text() if text is None else text)
        self.restart()

    def _feed(self, count: int) -> int:
        count = max(0, min(count, len(self.pieces) - self.fed))
        pieces = self.pieces[self.fed : self.fed + count]
        self.fed += count
        last = self.fed >= len(self.pieces)
        for lane in self.lanes:
            lane.take(pieces, close=last)
        if last:
            self._owed = 0.0
        return count

    def advance(self, seconds: float) -> int:
        """
        Feed the pieces that `seconds` of the clock allow. Returns how many.

        Nothing while paused. A fraction of a piece is carried to the next
        call, so the rate holds over a second whatever the frame time is. When
        the last piece has gone the streams are closed, which commits whatever
        was still live.
        """
        if self.paused or self.done:
            return 0
        self._owed += max(0.0, seconds) * max(0.0, self.tokens_per_second)
        # A hair over, so that sixty sixtieths of a second at forty a second
        # is forty pieces and not thirty-nine and a rounding error.
        count = int(self._owed + 1e-6)
        fed = self._feed(count)
        if self.fed < len(self.pieces):
            self._owed -= fed
        return fed

    def step(self, count: int = 1) -> int:
        """
        Pause, and feed exactly `count` pieces whatever the clock says. Returns how many went.
        """
        self.paused = True
        self._owed = 0.0
        return self._feed(count)

    def finish(self) -> int:
        """
        Feed everything that is left at once, and close. The pause is left as it is.
        """
        return self._feed(len(self.pieces) - self.fed)

    def tick(self, seconds: float, width: Scaled) -> int:
        """
        One frame without a frame: feed, lay out every lane at `width`, count. Returns pieces fed.
        """
        fed = self.advance(seconds)
        self.settle(width)
        return fed

    def settle(self, width: Scaled) -> None:
        """
        Lay out every lane at `width` and count what moved, without feeding anything.
        """
        for lane in self.lanes:
            lane.lay_out(width)
            lane.observe()

    def progress(self) -> str:
        """
        One line: how far through the source, how fast, and whether the clock is running.
        """
        if self.done:
            state = "finished"
        elif self.paused:
            state = "paused"
        else:
            state = "running"
        return (
            f"{self.source.label}  ·  piece {self.fed} of {len(self.pieces)}"
            f"  ·  {self.tokens_per_second:.0f} tokens/s  ·  {state}"
        )


def readouts(session: Session) -> tuple[str, ...]:
    """
    Every readout line of the page, top to bottom: progress, then two lines a lane.
    """
    lines = [session.progress()]
    for lane in session.lanes:
        lines.extend(lane.describe())
    return tuple(lines)


def report(session: Session, frames: int) -> list[str]:
    """
    What an unattended run prints: one line of totals and one a lane. Counts, not judgements.
    """
    lines = [
        f"frames={frames} fed={session.fed} pieces={len(session.pieces)} "
        f"done={int(session.done)} source={session.source.key}"
    ]
    for lane in session.lanes:
        stats = lane.stats
        lines.append(
            f"{lane.policy.name} layouts={lane.view.relayouts} moved={lane.moved} "
            f"layouts_that_moved={len(lane.moves)} samples={lane.layout.count} "
            f"blocks={len(lane.stream.blocks)} committed={len(lane.stream.committed)} "
            f"glyphs={0 if stats is None else stats.glyphs} "
            f"missing={0 if stats is None else stats.missing}"
        )
    return lines


class StreamPage:
    """
    The page: a `Session` and the frame that draws it.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        words = context.options_for(PAGE.name)
        source = next((entry for entry in SOURCES if entry.key in words), SOURCES[0])
        rate = context.count_for(PAGE.name)
        self.session = Session(
            theme=context.theme,
            measure=context.measure,
            metrics=context.metrics,
            px_per_inch=context.px_per_inch,
            source=source,
            tokens_per_second=DEFAULT_TOKENS_PER_SECOND if rate is None else float(rate),
        )
        if "done" in words:
            self.session.finish()
        self.frames = 0

    def report(self) -> list[str]:
        """
        `report` of this page's session, with the frames it has drawn.
        """
        return report(self.session, self.frames)

    def draw(self) -> None:
        from imgui_bundle import imgui

        session = self.session
        self.frames += 1
        self._controls(imgui)
        for line in readouts(session):
            caption(line)
        imgui.separator()

        session.advance(imgui.get_io().delta_time)
        spacing = imgui.get_style().item_spacing.x
        width = max((imgui.get_content_region_avail().x - spacing) / len(session.lanes), 1.0)
        for index, lane in enumerate(session.lanes):
            if index:
                imgui.same_line()
            # A vertical scrollbar that is always there, so the pane's width --
            # and with it every line break -- does not change on the frame the
            # text first outgrows it. That would be counted as a resize, and
            # correctly, but it would be this page's doing and not the stream's.
            imgui.begin_child(
                f"##advtext-stream-{lane.policy.name}",
                imgui.ImVec2(width, 0.0),
                imgui.ChildFlags_.borders.value,
                imgui.WindowFlags_.always_vertical_scrollbar.value,
            )
            lane.view.debug = self.context.debug
            lane.show(self.context.fonts, imgui)
            imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        session = self.session
        imgui.set_next_item_width(200.0)
        if imgui.begin_combo("##advtext-stream-source", session.source.label):
            for entry in SOURCES:
                if imgui.selectable(entry.label, entry is session.source)[0]:
                    session.choose(entry)
            imgui.end_combo()
        imgui.same_line()
        imgui.set_next_item_width(220.0)
        changed, rate = imgui.slider_float(
            "tokens/s", session.tokens_per_second, 0.0, MAX_TOKENS_PER_SECOND
        )
        if changed:
            session.tokens_per_second = rate
        imgui.same_line()
        if imgui.button("Resume" if session.paused else "Pause"):
            session.paused = not session.paused
        imgui.same_line()
        if imgui.button("Step"):
            session.step()
        imgui.same_line()
        if imgui.button("Restart"):
            session.restart()


PAGE = PageSpec(
    name="Stream",
    order=210,
    factory=StreamPage,
    group="Streaming",
    caption="one source replayed as tokens under both commit policies, with counters",
    options=("done", *(entry.key for entry in SOURCES)),
    shots=("400", "table,done"),
)

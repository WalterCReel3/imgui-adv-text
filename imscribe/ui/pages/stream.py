r"""
The Stream page: one source replayed as tokens into two views at once, with
counters for what moved and what it cost.

A model writes an answer a few characters at a time and a host has to show it
while it is being written. This page replays a markdown file that way through
`imscribe.typeset_markdown.MarkdownStream` under
`imscribe.ui.typeset_stream_view.TypesetStreamView`, twice over, in two panes
fed the same pieces on the same clock:

- **`KEEP_STREAMED`** on the left: a finished block stays as it was read while
  it streamed, ragged.
- **`RESET`** on the right: a finished block is read again as the theme sets
  it (justified, here), once, at the moment it is finished.

Everything else on the page is there to let somebody see the difference between
those two and what either costs: a rate slider, pause, single step, restart, a
picker of sources chosen to be hard, a bar in the margin beside whatever is
still unfinished, and readouts.

## When the library is not drawing

There is no other renderer. While `imscribe.typesetter.ready()` is false the
page draws ONE wrapped line and nothing else
(`imscribe.ui.pages.typeset.say_why_not`: that imtypeset is not drawing, and
why), and the clock does not run. The `Session` is still there: the pieces,
the clock and the controls need no library and are tested without one. A
lane's view is made by its first `show`, which is the first frame the library
could draw.

A call that raises `TypesetUnavailable` (the library failed and was switched
off) ends that frame's drawing; the page keeps the sentence and from the next
frame on draws the one line, for good. The exception does not leave `draw`, so
the app's traceback page is not reached. Any other exception is a bug and is
not caught.

**The page asks `ready()` and never `typesetter.module()`**: a page is built
in the pytest process by every page-enumerating test, and the library is kept
out of that process (`imscribe/ui/pages/typeset.py` has this at length).

## The two policies, on a `MarkdownStream`

A `MarkdownStream` has no commit policy by name; it has what one is made of, a
theme for the tail and a theme for a commit:

- `KEEP_STREAMED` is `MarkdownStream(ragged(theme))`: one theme, ragged, so a
  block is described the same before and after it commits and nothing is
  handed to the library for the commit.
- `RESET` is `MarkdownStream(theme, live_theme=ragged(theme))`: the block is
  described again in the page's theme when it commits, which reaches the
  library as one `replace_blocks`.

## The readouts, and what they do and do not say

**They report change and cost. None of them is a measure of quality**
(`docs/visual-review.md`, rule 1). A count of zero settled lines moved is a
fact about positions; it does not say the text reads well, and a count above
zero does not say it reads badly -- `RESET` moves lines on purpose.

- **Settled lines moved.** After each draw that followed a change, the lines
  now set are compared with the lines of the draw before. A line is a
  `SetLine`: its block, its number, its text range, its rectangle and its
  baseline, in pixels (not glyph positions). Every line of the earlier draw
  but its last -- the one still being written -- is looked for unchanged in
  the new one; each that is missing counts. The lines are asked of the view
  through `TypesetStreamView.set_lines`, and only for the blocks that had not
  committed as of the draw before. **A change of width is not a move**: a
  draw at a new width starts the comparison over and counts nothing. **No
  count without a draw**: the library's document exists from the first draw
  on, so `Session.tick` with no window feeds and parses and counts no lines.
- **Edits.** `replace_blocks`, `append_text` and the first `set_blocks`, as
  `TypesetStreamView.edits` counts them: at most one a frame.
- **Cost of an append, in two parts.** *parse and edit* is
  `TypesetStreamView.sync` (the parse, the description and the one edit in
  the library). *layout and draw* is the view's `draw` on that frame: the
  library lays out what changed and is in view and draws it in one call, and
  no host can time the two apart. A frame may take in several pieces, so each
  figure is per frame that took text, shown as the latest, the mean over the
  replay and the largest. Frames on which nothing arrived are not counted.
  These are wall-clock times of this process on this machine at this moment.
- **Blocks, committed and live.** How many blocks the stream will not touch
  again, and how many it still may.

There is no count of glyphs and none of glyphs missing: `report` prints the
vertices of the last frame and whether the library set everything as asked.

**What this page does not assert.** How the library breaks a ragged paragraph
is the library's: the counter reports what `set_lines` answered before and
after and the page claims nothing about what it should be. A table's columns
are held while it is written but move when a wider cell arrives (the view
says so).

## The mark beside the unfinished end

A bar in the pane's left padding runs from the top of the first live block to
the bottom of the last. Where it starts is the commit boundary. It is drawn by
this page from public facts -- `stream.committed`, `view.block_rect`,
`view.origin` -- and is not part of the view. Two calls into the library a
lane a frame while anything is live.

## The sources

`demo/stream.md` and five files under `demo/stream/`, each one case:
numbered steps with fences and indented paragraphs under the numbers; a
thirty-row table; a six-hundred-line code block; an address too wide for any
pane in the middle of a paragraph, with reference-style links, which a stream
shows as typed, by design; and plain prose. An installed wheel has no `demo/`
and gets one built-in paragraph.

## What has been run

`tests/test_page_stream.py`: the clock and the controls with no library and no
ImGui; the one line the page draws without the library; and, in children that
load the library, the page in ImGui frames with no backend and in a real
window at a rate slow enough that the stream spans many edits. Nobody has
watched it. Whether either policy is comfortable to read at any rate is what
the page exists to let a person judge.

Options (`--tab stream:...`): a source key (`steps`, `table`, `code`, `links`,
`prose`) picks the source; `done` feeds the whole source on the first frame;
an integer is the tokens per second.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final

from imscribe import typesetter
from imscribe.theme import Align
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.ownership import MIN_WIDTH_PX
from imscribe.ui.pages import PageContext, PageSpec, caption, demo_text
from imscribe.ui.pages.typeset import say_why_not, why_not
from imscribe.ui.palette import DARK_PALETTE, rgba
from imscribe.ui.typeset_stream_view import TypesetStreamView, TypesetUnavailable

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imscribe.theme import Theme

__all__ = [
    "DEFAULT_TOKENS_PER_SECOND",
    "FALLBACK",
    "MAX_TOKENS_PER_SECOND",
    "PAGE",
    "POLICIES",
    "SOURCES",
    "Cost",
    "Lane",
    "Session",
    "Source",
    "StreamPage",
    "changed_lines",
    "ragged",
    "readouts",
    "report",
    "tokens",
]

POLICIES: Final = ("KEEP_STREAMED", "RESET")
"""
The two panes, left to right: the two commit policies, by name.
"""

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


def changed_lines(before: list[Any], after: list[Any]) -> list[Any]:
    """
    The settled lines of `before` that are not in `after` exactly as they were.

    "Settled" is every line but the last, which is the one being written.
    "As they were" is the same glyphs at the same x on the same baseline: a
    line that kept its words and shifted by a scaled point has moved.
    """
    present = set(after)
    return [line for line in before[:-1] if line not in present]


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


def _three(cost: Cost) -> str:
    return f"{cost.last_ms:.2f} / {cost.mean_ms:.2f} / {cost.worst_ms:.2f}"


def ragged(theme: Theme) -> Theme:
    """
    `theme` with every justified block style made ragged right; itself if none is.

    The theme a `MarkdownStream`'s tail is read with. Only `BlockStyle.align`
    differs.
    """
    if all(style.align is not Align.JUSTIFY for style in theme.blocks.values()):
        return theme
    return replace(
        theme,
        blocks={
            kind: replace(style, align=Align.LEFT) if style.align is Align.JUSTIFY else style
            for kind, style in theme.blocks.items()
        },
    )


@dataclass
class Lane:
    """
    One policy's half of the page: a stream, the view over it, and what was counted.

    `name` is one of `POLICIES`; the module docstring says what stream each
    is. The stream needs no library and `take` needs no window. The view is
    made by the first `show` (`TypesetUnavailable` when the library is not in
    use) and is `None` until then, and after a `restart`: `sync`, `observe`
    and the live mark do nothing, and count nothing, without one.
    """

    name: str
    theme: Theme
    timer: Callable[[], float] = time.perf_counter

    stream: MarkdownStream = field(init=False)
    view: TypesetStreamView | None = field(default=None, init=False)
    """The view over `stream`: made by the first `show`, closed and dropped by `restart`."""
    moved: int = field(default=0, init=False)
    """Settled lines that moved, in total, since the replay began."""
    moves: list[tuple[int, int]] = field(default_factory=list, init=False)
    """`(pieces taken so far, lines moved)` for each counted draw in which any did."""
    changed: list[Any] = field(default_factory=list, init=False)
    """The lines the latest counted draw moved, as they were before it."""
    taken: int = field(default=0, init=False)
    parse: Cost = field(default_factory=Cost, init=False)
    """`sync`: the parse, the description and the one edit in the library."""
    draw: Cost = field(default_factory=Cost, init=False)
    """The view's `draw` on a frame that took text: the library's layout and its draw."""
    vertices: int = field(default=0, init=False)
    """Vertices the last `show` added to the pane's draw list, the live mark not included."""
    whole: bool = field(default=True, init=False)
    """What the last `draw` returned: whether everything in view was set as asked."""
    width_px: float = field(default=0.0, init=False)
    _lines: list[Any] = field(default_factory=list, init=False)
    _seen: tuple[int, float] | None = field(default=None, init=False)
    _settled: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.name not in POLICIES:
            raise ValueError(f"{self.name!r} is not one of {POLICIES}")
        self.restart()

    def restart(self) -> None:
        """
        Begin again from nothing: a new stream, no view, every count at zero.

        The view there was gives its document back to the library first,
        which is a library call and may raise `TypesetUnavailable`.
        """
        if self.view is not None:
            self.view.close()
        self.view = None
        live = ragged(self.theme)
        if self.name == "RESET":
            self.stream = MarkdownStream(self.theme, live_theme=live)
        else:
            self.stream = MarkdownStream(live)
        self.moved = 0
        self.moves = []
        self.changed = []
        self.taken = 0
        self.parse = Cost()
        self.draw = Cost()
        self.vertices = 0
        self.whole = True
        self._lines = []
        self._seen = None
        self._settled = 0

    @property
    def edits(self) -> dict[str, int]:
        """
        Edits the view has made in the library, by kind; all zero while there is no view.
        """
        if self.view is None:
            return {"set": 0, "replace": 0, "append": 0}
        return dict(self.view.edits)

    def take(self, pieces: list[str], *, close: bool = False) -> None:
        """
        Append `pieces` to the stream, and close it if that was the last of them.
        """
        for piece in pieces:
            self.stream.append(piece)
        self.taken += len(pieces)
        if close and not self.stream.closed:
            self.stream.close()

    def sync(self, *, make: bool = False) -> bool:
        """
        Take in what arrived (`TypesetStreamView.sync`) and time it. True if a block changed.

        Without a view: nothing, and False, unless `make`, which is how `show`
        asks for the view to be made here. Making it reads the stream, so that
        is the first sync and is timed as one. A frame on which nothing
        arrived adds no sample: its parse is a comparison of two integers, and
        averaging those in would make an append look cheaper the longer the
        page idled.
        """
        began = self.timer()
        if self.view is None:
            if not make:
                return False
            self.view = TypesetStreamView(self.stream, palette=DARK_PALETTE)
            fresh = bool(self.view.blocks)
        else:
            fresh = self.view.sync()
        if fresh:
            self.parse.add(self.timer() - began)
        return fresh

    def observe(self) -> int:
        """
        Count the settled lines the latest draw moved. Call after `view.draw`.

        Nothing before the first draw, nothing when neither the blocks nor the
        width changed since the last count, and nothing for a change of width
        (which becomes what the next draw is compared with). Only the blocks
        not committed at the last count are asked for: `set_lines` is a call a
        block and a call a line.
        """
        view = self.view
        if view is None or view.origin is None:
            return 0
        key = (view.revision, self.width_px)
        if key == self._seen:
            return 0
        resized = self._seen is not None and self._seen[1] != self.width_px
        lines = list(view.set_lines(0 if resized else self._settled))
        self.changed = [] if self._seen is None or resized else changed_lines(self._lines, lines)
        moved = len(self.changed)
        if moved:
            self.moved += moved
            self.moves.append((self.taken, moved))
        self._settled = len(self.stream.committed)
        self._lines = [line for line in lines if line.block >= self._settled]
        self._seen = key
        return moved

    def live_span(self) -> tuple[float, float] | None:
        """
        From the top of the first unfinished block to the bottom of the last, in screen pixels.

        `None` before the first draw and when nothing is unfinished. Two calls
        into the library (`TypesetView.block_rect`).
        """
        view = self.view
        if view is None:
            return None
        settled = len(self.stream.committed)
        last = len(view.blocks) - 1
        if settled > last:
            return None
        top, bottom = view.block_rect(settled), view.block_rect(last)
        if top is None or bottom is None:
            return None
        return top[1], bottom[3]

    def show(self, imgui: Any, *, debug: bool = False) -> bool:
        """
        This lane's view in the current window, with the live mark. One frame.

        Call inside a child window that scrolls. Makes the view if there is
        none. Raises `TypesetUnavailable`, having drawn nothing, when the
        library cannot draw.
        """
        width_px = max(imgui.get_content_region_avail().x, MIN_WIDTH_PX)
        fresh = self.sync(make=True)
        view = self.view
        assert view is not None
        view.debug = debug
        buffer = imgui.get_window_draw_list().vtx_buffer
        before = buffer.size()
        began = self.timer()
        self.whole = view.draw(palette=DARK_PALETTE, width_px=width_px)
        if fresh:
            self.draw.add(self.timer() - began)
        self.vertices = buffer.size() - before
        self.width_px = width_px
        self.observe()

        span = self.live_span()
        origin = view.origin
        if span is not None and origin is not None:
            imgui.get_window_draw_list().add_rect_filled(
                imgui.ImVec2(origin[0] - 8.0, span[0]),
                imgui.ImVec2(origin[0] - 5.0, span[1]),
                LIVE_MARK,
            )
        return self.whole

    def describe(self) -> tuple[str, str]:
        """
        This lane's two readout lines: counts, then cost. Change and cost, no judgement.
        """
        committed = len(self.stream.committed)
        live = len(self.stream.blocks) - committed
        edits = sum(self.edits.values())
        counts = (
            f"{self.name}  ·  blocks: {committed} committed, {live} live"
            f"  ·  settled lines moved: {self.moved} (in {len(self.moves)} of {edits} edits)"
        )
        cost = (
            "ms per frame that took text, last / mean / max"
            f"  ·  parse and edit {_three(self.parse)}"
            f"  ·  layout and draw {_three(self.draw)}"
        )
        return counts, cost

    def summary(self) -> str:
        """
        This lane's line of `report`: counts.
        """
        edits = self.edits
        return (
            f"{self.name} edits={sum(edits.values())} set={edits['set']} "
            f"append={edits['append']} replace={edits['replace']} moved={self.moved} "
            f"layouts_that_moved={len(self.moves)} samples={self.parse.count} "
            f"blocks={len(self.stream.blocks)} committed={len(self.stream.committed)} "
            f"vertices={self.vertices} whole={int(self.whole)}"
        )


@dataclass
class Session:
    """
    One replay of one source into every lane: the pieces, the clock, and the controls.

    `advance(seconds)` is what a frame's worth of time does; `step`, `pause`
    and `restart` are the buttons; `choose` is the picker. None of it needs a
    window or the library, and the time is always passed in, so a test
    advances the clock by hand and a whole replay is fed in a loop (`tick`).

    Both lanes are handed the same pieces in the same call, so at every moment
    they hold the same text and differ only in policy.
    """

    theme: Theme
    source: Source = SOURCES[0]
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    paused: bool = False
    timer: Callable[[], float] = time.perf_counter
    text: str | None = None
    """The text to replay in place of `source`'s file. For a test, or a host's own text."""

    pieces: list[str] = field(init=False)
    fed: int = field(default=0, init=False)
    lanes: tuple[Lane, ...] = field(init=False)
    """A `Lane` for each of `POLICIES`, in that order."""
    _owed: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.lanes = tuple(Lane(name, self.theme, self.timer) for name in POLICIES)
        self.pieces = tokens(self.source.text() if self.text is None else self.text)

    def lane(self, name: str) -> Lane:
        """
        The lane running under the policy `name`, one of `POLICIES`.
        """
        for lane in self.lanes:
            if lane.name == name:
                return lane
        raise KeyError(name)

    @property
    def done(self) -> bool:
        """
        Whether every piece has been fed and the streams closed.
        """
        return self.fed >= len(self.pieces) and all(lane.stream.closed for lane in self.lanes)

    def restart(self) -> None:
        """
        Begin the same source again from nothing. The rate and the pause are left as they are.

        May raise `TypesetUnavailable`: a lane with a view closes it.
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

    def tick(self, seconds: float) -> int:
        """
        One frame without a frame: feed, and `settle`. Returns pieces fed.
        """
        fed = self.advance(seconds)
        self.settle()
        return fed

    def settle(self) -> None:
        """
        Every lane that has a view takes in what arrived and counts what its last draw moved.

        No view is made here, so with no window (and with no library) this
        feeds nothing to anything and counts nothing: a count needs a draw.
        """
        for lane in self.lanes:
            lane.sync()
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
    lines.extend(lane.summary() for lane in session.lanes)
    return lines


RENDERER_LINE: Final = (
    "renderer: TypesetStreamView (imtypeset) over MarkdownStream  ·  "
    "KEEP_STREAMED reads everything ragged; RESET reads a block again in the "
    "page's theme when it commits"
)
"""The first caption while the library draws."""


class StreamPage:
    """
    The page: a `Session` and the frame that draws it, or the one line that says why not.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        words = context.options_for(PAGE.name)
        source = next((entry for entry in SOURCES if entry.key in words), SOURCES[0])
        rate = context.count_for(PAGE.name)
        self.session = Session(
            theme=context.theme,
            source=source,
            tokens_per_second=DEFAULT_TOKENS_PER_SECOND if rate is None else float(rate),
        )
        if "done" in words:
            self.session.finish()
        self.frames = 0
        self.failed = ""
        """What a `TypesetUnavailable` out of a frame said; empty until one was raised."""
        self._released = False

    @property
    def reason(self) -> str:
        """
        Why imtypeset is not drawing this page; empty while it is.

        What a frame raised, for good once one has; otherwise `why_not()`, read
        at each asking, so a page built before the library's fonts were loaded
        draws once they are.
        """
        return self.failed or why_not()

    @property
    def renderer(self) -> str:
        """`"TypesetStreamView"` while the library draws the panes, `"none"` when nothing does."""
        return "none" if self.reason else "TypesetStreamView"

    def report(self) -> list[str]:
        """
        `report` of this page's session, with the frames it has drawn and the renderer.
        """
        lines = report(self.session, self.frames)
        lines[0] += f" renderer={self.renderer}"
        return lines

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        reason = self.reason
        if reason:
            self._release()
            say_why_not(reason)
            return
        self._released = False
        try:
            self._frame(imgui)
        except TypesetUnavailable as exc:
            # The library was switched off under this frame. What it had drawn
            # of the frame stays; from the next one on the page is the one line.
            self.failed = str(exc) or typesetter.reason() or "imtypeset raised TypesetUnavailable"
            self._release()

    def _release(self) -> None:
        """
        Give back what the page's views hold in the library, once, when the page gives up.

        Called when a frame or a call raised `TypesetUnavailable` and on the
        first frame that finds the library not drawing. The views are closed
        and KEPT, with everything else the page knows: `report()` reads them,
        and a closed view makes its document again if it is ever drawn. Until
        2026-10-11 only the Diff page let go of anything.
        """
        if self._released:
            return
        self._released = True
        for lane in self.session.lanes:
            if lane.view is not None:
                lane.view.close()

    def _frame(self, imgui: Any) -> None:
        """
        The controls, the readouts and both panes. `TypesetUnavailable` may leave it.

        Every `begin_child` here is ended on the way out, so the exception
        leaves ImGui's stack as it found it.
        """
        session = self.session
        self._controls(imgui)
        caption(RENDERER_LINE)
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
                f"##imscribe-stream-{lane.name}",
                imgui.ImVec2(width, 0.0),
                imgui.ChildFlags_.borders.value,
                imgui.WindowFlags_.always_vertical_scrollbar.value,
            )
            try:
                lane.show(imgui, debug=self.context.debug)
            finally:
                imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        session = self.session
        imgui.set_next_item_width(200.0)
        if imgui.begin_combo("##imscribe-stream-source", session.source.label):
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

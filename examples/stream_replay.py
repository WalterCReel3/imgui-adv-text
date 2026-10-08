r"""
Stream replay: a document fed to the renderer a few characters at a time.

A model writes an answer token by token and a host has to show it while it is
being written. This example replays `demo/stream.md` through
`advtext.StreamDocument` and `advtext.StreamView` at a rate you choose, and
counts one thing while it does: **how many lines that had already been set
moved.**

    python examples/stream_replay.py

Three controls, and they are the three things worth turning:

- **Tokens per second.** How fast pieces arrive. The view lays out at most once
  a frame whatever the rate, so at 2000 a second it is doing the same work per
  frame as at 20, on more text.
- **Commit policy.** `KEEP_STREAMED` leaves a finished paragraph broken the way
  it was while it streamed, ragged. `RESET` sets it again, justified, when it
  is finished: one visible change per paragraph. Switching restarts the replay.
- **Restart.**

## The counter, and what it does and does not say

After every layout the lines now set are compared with the lines of the
layout before. A line is its glyphs and where each one is. Every line of the
earlier layout **except its last** -- the last is the one still being written
-- is looked for, unchanged, in the new one; each that is not there is counted
as moved (`moved_lines`).

The lines come from `StreamView.set_lines`, and only for the blocks that could
have changed: those not yet committed at the layout before. A block that had
committed by then keeps its lines for as long as the width does, so asking for
it again would be work per layout that grows with the document -- in the
demo whose point is that only the unfinished end is redone.

**A change of width is not the stream moving anything.** A resize sets every
line again; a layout at a new width starts the comparison over and counts
nothing.

**It reports change, not quality** (`docs/visual-review.md`). A count of zero
means no settled line changed, which is a fact about positions. It does not
mean the result reads well, and a count above zero does not mean it reads
badly: `RESET` moves lines on purpose.

What the count is expected to be, and `tests/test_example_stream.py` holds it
to this:

- **Plain prose, `KEEP_STREAMED`: zero.** The live tail is broken first-fit at
  natural spacing, and a first-fit line depends only on the text up to its own
  end, so text arriving after it cannot change it.
- **Markup that closes late: not zero.** `**bold` is two asterisks and four
  letters until the closing pair arrives; then the asterisks are gone, the
  face is bold, and every width after them is different. `demo/stream.md`'s
  second paragraph does this on purpose. First-fit cannot protect a line whose
  own characters change.
- **A table: not zero.** A column widens when a longer cell arrives and the
  columns to its right move with it. The view holds each column at the widest
  it has been, so no column ever *narrows*, which is the part that can be held.
- **`RESET`: not zero, and only at commits.** Every line of a paragraph that
  is set again counts.

## What has been run, and what has not

`tests/test_example_stream.py` drives a whole replay with a clock it advances
by hand, checks the counter against the list above, runs `show` in real ImGui
frames with no display, and runs `main` in a real window wherever an Xvfb can
be started in a user namespace. **Nobody has watched it.** Whether a stream
at forty tokens a second is comfortable to read is exactly the question this
example exists to let somebody answer by looking, and nothing here answers it.

Everything used is importable from the package root; this file imports nothing
else of the library.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from advtext import (
    CommitPolicy,
    DrawStats,
    LoadedFaces,
    MetricsResolver,
    Scaled,
    StreamDocument,
    StreamView,
    Theme,
    char_measure,
    fontlib_metrics,
    load_faces,
    sp_from_px,
)

SOURCE = Path(__file__).resolve().parent.parent / "demo" / "stream.md"
"""
The document replayed by default: written to be every kind of unfinished block for a while.
"""

WINDOW_TITLE = "advtext: stream replay"

DEFAULT_TOKENS_PER_SECOND = 40.0
"""
Roughly what a hosted model produces. A starting point for the slider and not a claim.
"""

MAX_TOKENS_PER_SECOND = 2000.0

Line = Any
"""
One set line as the counter sees it: anything hashable that is equal to itself unmoved.

In a replay it is what `StreamView.set_lines` returns -- a block number, a
baseline, and each glyph's codepoint and x.
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


def lines_of(view: StreamView, first_block: int = 0) -> list[Line]:
    """
    Every line of the view's current layout that holds a glyph, from `first_block` on.

    Top to bottom, as the counter compares them. Empty when the view has no
    current layout. This is `view.set_lines(first_block)` and nothing more;
    it is a function here so that the one place the example asks the library
    where lines are is easy to find.
    """
    return list(view.set_lines(first_block))


def changed_lines(before: list[Line], after: list[Line]) -> list[Line]:
    """
    The settled lines of `before` that are not in `after` exactly as they were.

    "Settled" is every line but the last, which is the one being written.
    "As they were" is the same glyphs at the same x on the same baseline: a
    line that kept its words and shifted by a scaled point has moved.
    """
    present = set(after)
    return [line for line in before[:-1] if line not in present]


def moved_lines(before: list[Line], after: list[Line]) -> int:
    """
    How many settled lines of `before` are not in `after` exactly as they were.

    A count of change. See the module docstring for what it is not.
    """
    return len(changed_lines(before, after))


@dataclass
class Replay:
    """
    One replay: the pieces, how far through them it is, the view, and the counter.

    All the logic the window drives is here, and none of it needs a window:
    `tick(seconds, width)` is one frame's worth -- feed what the clock allows,
    lay out, count -- with the time passed in, so a test advances the clock by
    hand and a whole replay runs in a loop.
    """

    source: str
    theme: Theme
    metrics: MetricsResolver = fontlib_metrics
    policy: CommitPolicy = CommitPolicy.KEEP_STREAMED
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND

    pieces: list[str] = field(init=False)
    stream: StreamDocument = field(init=False)
    view: StreamView = field(init=False)
    fed: int = field(default=0, init=False)
    moved: int = field(default=0, init=False)
    """Settled lines that moved, in total, since the replay began."""
    moves: list[tuple[int, int]] = field(default_factory=list, init=False)
    """`(pieces fed so far, lines moved)` for each layout in which any did."""
    stats: DrawStats | None = field(default=None, init=False)
    _measure: Any = field(default=None, init=False)
    _owed: float = field(default=0.0, init=False)
    changed: list[Line] = field(default_factory=list, init=False)
    """The lines the latest counted layout moved, as they were before it."""
    _lines: list[Line] = field(default_factory=list, init=False)
    _seen: Any = field(default=None, init=False)
    _settled: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.pieces = tokens(self.source)
        # One measure for the life of the replay: the layout caches key it by
        # identity, and a new one per restart would miss on everything.
        self._measure = char_measure(self.metrics)
        self.restart()

    def restart(self, policy: CommitPolicy | None = None) -> None:
        """
        Begin again from nothing, under `policy` if one is given.
        """
        if policy is not None:
            self.policy = policy
        self.stream = StreamDocument(self.theme, self.metrics, policy=self.policy)
        self.view = StreamView(self.stream, self._measure)
        self.fed = 0
        self.moved = 0
        self.moves = []
        self.stats = None
        self._owed = 0.0
        self.changed = []
        self._lines = []
        self._seen = None
        self._settled = 0

    @property
    def done(self) -> bool:
        """
        Whether every piece has been fed and the stream closed.
        """
        return self.fed >= len(self.pieces) and self.stream.closed

    def advance(self, seconds: float) -> int:
        """
        Feed the pieces that `seconds` of the clock allow. Returns how many.

        A fraction of a piece is carried to the next call, so the rate holds
        over a second whatever the frame time is. When the last piece has gone
        the stream is closed, which commits whatever was still live.
        """
        if self.done:
            return 0
        self._owed += max(0.0, seconds) * max(0.0, self.tokens_per_second)
        # A hair over, so that sixty sixtieths of a second at forty a second
        # is forty pieces and not thirty-nine and a rounding error.
        count = min(int(self._owed + 1e-6), len(self.pieces) - self.fed)
        self._owed -= count
        for piece in self.pieces[self.fed : self.fed + count]:
            self.stream.append(piece)
        self.fed += count
        if self.fed >= len(self.pieces) and not self.stream.closed:
            self.stream.close()
            self._owed = 0.0
        return count

    def observe(self) -> int:
        """
        Count the settled lines the latest layout moved. Call after the view has laid out.

        Does nothing, and returns zero, if the view's layout is the one already
        counted: a frame on which no text arrived moves nothing by definition.
        A layout at a different width from the last one counted also counts
        nothing -- every line moved, and none of them because of the stream --
        and becomes what the next layout is compared with.

        Only the blocks that were not yet committed at the last layout are
        asked for (`_settled`); the module docstring says why that is all that
        can have moved. Call this before appending anything more: it reads
        `stream.committed` as the number of blocks the layout had settled.
        """
        layout = self.view.layout
        if layout is None or layout is self._seen:
            return 0
        resized = self._seen is not None and layout.width != self._seen.width
        lines = lines_of(self.view, 0 if resized else self._settled)
        self.changed = [] if self._seen is None or resized else changed_lines(self._lines, lines)
        moved = len(self.changed)
        if moved:
            self.moved += moved
            self.moves.append((self.fed, moved))
        self._settled = len(self.stream.committed)
        self._lines = [line for line in lines if line.block >= self._settled]
        self._seen = layout
        return moved

    def tick(self, seconds: float, width: Scaled) -> int:
        """
        One frame without a frame: feed, lay out at `width`, count. Returns lines moved.
        """
        self.advance(seconds)
        self.view.sync()
        self.view.layout_for(width)
        return self.observe()

    def status(self) -> str:
        """
        One line for the window: how far, how fast, and what has moved.
        """
        layouts = self.view.relayouts
        tail = "following the end" if self.view.following else "scrolled away from the end"
        return (
            f"{self.fed} of {len(self.pieces)} pieces at {self.tokens_per_second:.0f}/s"
            f"  |  {self.policy.name}"
            f"  |  settled lines moved: {self.moved} (in {len(self.moves)} of {layouts} layouts)"
            f"  |  {tail}"
        )


def replay(
    source: str | None = None,
    *,
    theme: Theme | None = None,
    policy: CommitPolicy = CommitPolicy.KEEP_STREAMED,
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND,
) -> Replay:
    """
    A `Replay` of `source`, or of `demo/stream.md`, in the default theme unless one is given.
    """
    text = SOURCE.read_text(encoding="utf-8") if source is None else source
    return Replay(
        source=text,
        theme=Theme.build() if theme is None else theme,
        policy=policy,
        tokens_per_second=tokens_per_second,
    )


def show(playing: Replay, fonts: Any, imgui: Any, seconds: float) -> DrawStats:
    """
    The controls, the status line and the document, in the current window. One frame.

    `seconds` is the time since the last frame; the caller reads it from
    ImGui (`get_io().delta_time`) and a test passes what it likes. `imgui` is
    passed in so that this module imports no ImGui until `main` runs.

    The document's child window has a vertical scrollbar that is always there,
    so the pane's width -- and with it every line break -- does not change on
    the frame the text first outgrows it.
    """
    changed, rate = imgui.slider_float(
        "tokens per second", playing.tokens_per_second, 0.0, MAX_TOKENS_PER_SECOND
    )
    if changed:
        playing.tokens_per_second = rate
    for policy in CommitPolicy:
        imgui.same_line()
        if (
            imgui.radio_button(policy.name, playing.policy is policy)
            and policy is not playing.policy
        ):
            playing.restart(policy)
    imgui.same_line()
    if imgui.button("Restart"):
        playing.restart()
    imgui.text_unformatted(playing.status())

    playing.advance(seconds)
    imgui.begin_child(
        "##advtext-stream-replay",
        imgui.ImVec2(0.0, 0.0),
        imgui.ChildFlags_.borders.value,
        imgui.WindowFlags_.always_vertical_scrollbar.value,
    )
    stats: DrawStats = playing.view.draw(fonts=fonts)
    imgui.end_child()
    playing.observe()
    playing.stats = stats
    return stats


def report(playing: Replay, frames: int) -> list[str]:
    """
    What `main` prints when it was asked to stop by itself. Counts, not judgements.
    """
    stats = playing.stats
    return [
        f"frames={frames} fed={playing.fed} pieces={len(playing.pieces)} "
        f"done={int(playing.done)} policy={playing.policy.name}",
        f"layouts={playing.view.relayouts} moved={playing.moved} "
        f"layouts_that_moved={len(playing.moves)} following={int(playing.view.following)}",
        f"glyphs={0 if stats is None else stats.glyphs} "
        f"missing={0 if stats is None else stats.missing} "
        f"blocks={len(playing.stream.blocks)} committed={len(playing.stream.committed)}",
    ]


def main(argv: list[str] | None = None) -> int:
    """
    Open a window and replay the document in it. Needs a display.

    `--frames N` closes the window after N frames and prints `report`; with
    `--tps` high enough the whole document is fed in that time, which is how
    this is run unattended.
    """
    parser = argparse.ArgumentParser(description="Replay a markdown document as a token stream.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--tps", type=float, default=DEFAULT_TOKENS_PER_SECOND)
    parser.add_argument(
        "--policy", choices=[policy.name for policy in CommitPolicy], default="KEEP_STREAMED"
    )
    parser.add_argument("--source", type=Path, default=SOURCE, help="the markdown to replay")
    args = parser.parse_args(argv)

    from imgui_bundle import hello_imgui, imgui, immapp

    playing = replay(
        args.source.read_text(encoding="utf-8"),
        policy=CommitPolicy[args.policy],
        tokens_per_second=args.tps,
    )
    loaded: list[LoadedFaces] = []
    frames = 0

    def load_fonts() -> None:
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        loaded.append(load_faces())

    def gui() -> None:
        nonlocal frames
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.work_pos)
        imgui.set_next_window_size(viewport.work_size)
        flags = (
            imgui.WindowFlags_.no_decoration.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_saved_settings.value
        )
        if imgui.begin(WINDOW_TITLE, None, flags):
            show(playing, loaded[-1], imgui, imgui.get_io().delta_time)
        imgui.end()
        frames += 1
        if args.frames and frames >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (900, 760)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    # An example should not leave an .ini beside wherever it was launched from.
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    immapp.run(params)

    if args.frames:
        print("\n".join(report(playing, frames)))
    return 0


def page_width(pixels: float = 560.0) -> Scaled:
    """
    A measure in the library's units, for a caller ticking a replay with no pane to ask.
    """
    return sp_from_px(pixels)


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

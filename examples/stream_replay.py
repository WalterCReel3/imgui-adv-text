r"""
Stream replay: a document fed to the renderer a few characters at a time.

A model writes an answer token by token and a host has to show it while it is
being written. This example replays `demo/stream.md` through an
`imscribe.typeset_markdown.MarkdownStream` under an
`imscribe.ui.typeset_stream_view.TypesetStreamView`, drawn by the imtypeset
library, at a rate you choose, and counts one thing while it does: **how many
lines that had already been set moved.**

    python examples/stream_replay.py

(With imscribe installed, imtypeset is too and nothing is set in the
environment; `examples/typeset_minimal.py` says what a developer building
imtypeset from source does instead.)

Three controls, and they are the three things worth turning:

- **Tokens per second.** How fast pieces arrive. The view makes at most one
  edit in the library a frame whatever the rate, so at 2000 a second it is
  doing the same work per frame as at 20, on more text.
- **Commit policy.** `KEEP_STREAMED` reads the whole stream in the ragged
  theme, so a finished paragraph stays as it was while it streamed. `RESET`
  reads the tail ragged and a block again in the theme, justified, when it is
  finished (`MarkdownStream(theme, live_theme=...)`): one visible change per
  paragraph. Switching restarts the replay.
- **Restart.**

## Without the library

There is no other renderer, so the example does not open a window it could
draw nothing in. `main` asks for the library before it makes a window; when
it is not in use it prints why to standard error and returns `NO_LIBRARY`
(1). The library's fonts are loaded from the window's font callback, so one
failure can only be known with the window open: fonts that do not load, or a
draw that raises `TypesetUnavailable`, close the window at once and `main`
prints the reason and returns the same 1.

`Replay` itself needs no library until it is shown: the pieces and the clock
are plain Python, and the view is made by the first `show`, which raises
`TypesetUnavailable` when imtypeset is not in use.

## The counter, and what it does and does not say

After every draw that followed a change, the lines now set are compared with
the lines of the draw before. A line is what `TypesetStreamView.set_lines`
answers: a block, a line number, a text range, a rectangle and a baseline, in
pixels. Every line of the earlier draw **except its last** -- the last is the
one still being written -- is looked for, unchanged, in the new one; each
that is not there is counted as moved (`moved_lines`).

Only the blocks that could have changed are asked for: those not yet committed
at the draw before. Asking for a committed block again would be work per draw
that grows with the document -- in the demo whose point is that only the
unfinished end is redone.

**A change of width is not the stream moving anything.** A resize sets every
line again; a draw at a new width starts the comparison over and counts
nothing.

**Nothing is counted without a draw.** The library's document exists from the
first draw on, so `tick` with no window feeds and parses and counts no lines.

**It reports change, not quality** (`docs/visual-review.md`). A count of zero
means no settled line changed, which is a fact about positions. It does not
mean the result reads well, and a count above zero does not mean it reads
badly: `RESET` moves lines on purpose. How the library breaks a ragged line
is the library's, and this example asserts nothing about what the count
should be under `KEEP_STREAMED`; markup that closes late (`**bold` is two
asterisks and four letters until the closing pair arrives) and a table whose
column widens both move lines, and `demo/stream.md` does both on purpose.

## What has been run, and what has not

`tests/test_example_stream.py` drives the clock by hand with no library, and,
in children that load the library, runs `show` in real ImGui frames with no
display and `main` in a real window wherever an Xvfb can be started in a user
namespace. **Nobody has watched it.** Whether a stream at forty tokens a
second is comfortable to read is exactly the question this example exists to
let somebody answer by looking, and nothing here answers it.

Everything is imported from the package root: the theme and its alignment,
the stream, the view, and the module `typesetter`.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from imscribe import (
    Align,
    MarkdownStream,
    Theme,
    TypesetStreamView,
    TypesetUnavailable,
    typesetter,
)

SOURCE = Path(__file__).resolve().parent.parent / "demo" / "stream.md"
"""
The document replayed by default: written to be every kind of unfinished block for a while.
"""

WINDOW_TITLE = "imscribe: stream replay"

DEFAULT_TOKENS_PER_SECOND = 40.0
"""
Roughly what a hosted model produces. A starting point for the slider and not a claim.
"""

MAX_TOKENS_PER_SECOND = 2000.0

POLICIES = ("KEEP_STREAMED", "RESET")
"""
The two commit policies, by name.
"""

NO_LIBRARY = 1
"""
What `main` returns when imtypeset cannot draw, after saying why on standard error.

The status the other examples of the typeset layer return for it
(`examples/diff_minimal.py`, `examples/typeset_minimal.py`). It is also what
an uncaught exception exits with, so a caller that must tell the two apart
reads standard error: one line beginning `imtypeset is not drawing: `.
"""

Line = Any
"""
One set line as the counter sees it: anything hashable that is equal to itself unmoved.

In a replay it is what `TypesetStreamView.set_lines` returns -- a block number,
a line number, a text range, a rectangle and a baseline.
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


def ragged(theme: Theme) -> Theme:
    """
    `theme` with every justified block style made ragged right; itself if none is.

    The theme a stream's unfinished tail is read with.
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


def lines_of(view: Any, first_block: int = 0) -> list[Line]:
    """
    Every line the library has set of the view's blocks from `first_block` on.

    Top to bottom, as the counter compares them. Empty before the view's
    first draw. This is `view.set_lines(first_block)` and nothing more; it is
    a function here so that the one place the example asks the library where
    lines are is easy to find.
    """
    return list(view.set_lines(first_block))


def changed_lines(before: list[Line], after: list[Line]) -> list[Line]:
    """
    The settled lines of `before` that are not in `after` exactly as they were.

    "Settled" is every line but the last, which is the one being written.
    "As they were" is equal in every field: a line that kept its characters
    and shifted by a pixel has moved.
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

    The pieces and the clock need no window and no library: `advance(seconds)`
    feeds what the clock allows, with the time passed in, so a test advances
    the clock by hand. The view is made by the first `show`.
    """

    source: str
    theme: Theme
    policy: str = "KEEP_STREAMED"
    """One of `POLICIES`."""
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND

    pieces: list[str] = field(init=False)
    stream: MarkdownStream = field(init=False)
    view: TypesetStreamView | None = field(default=None, init=False)
    """The view over `stream`: made by the first `show`, closed and dropped by `restart`."""
    fed: int = field(default=0, init=False)
    moved: int = field(default=0, init=False)
    """Settled lines that moved, in total, since the replay began."""
    moves: list[tuple[int, int]] = field(default_factory=list, init=False)
    """`(pieces fed so far, lines moved)` for each counted draw in which any did."""
    whole: bool = field(default=True, init=False)
    """What the last draw returned: whether everything in view was set as asked."""
    changed: list[Line] = field(default_factory=list, init=False)
    """The lines the latest counted draw moved, as they were before it."""
    width_px: float = field(default=0.0, init=False)
    """The width the last draw was made at."""
    _owed: float = field(default=0.0, init=False)
    _lines: list[Line] = field(default_factory=list, init=False)
    _seen: tuple[int, float] | None = field(default=None, init=False)
    _settled: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.pieces = tokens(self.source)
        self.restart()

    def restart(self, policy: str | None = None) -> None:
        """
        Begin again from nothing, under `policy` if one is given.

        A view there was gives its document back to the library first.
        """
        if policy is not None:
            self.policy = policy
        if self.policy not in POLICIES:
            raise ValueError(f"{self.policy!r} is not one of {POLICIES}")
        if self.view is not None:
            self.view.close()
        self.view = None
        live = ragged(self.theme)
        if self.policy == "RESET":
            self.stream = MarkdownStream(self.theme, live_theme=live)
        else:
            self.stream = MarkdownStream(live)
        self.fed = 0
        self.moved = 0
        self.moves = []
        self.whole = True
        self.changed = []
        self.width_px = 0.0
        self._owed = 0.0
        self._lines = []
        self._seen = None
        self._settled = 0

    @property
    def done(self) -> bool:
        """
        Whether every piece has been fed and the stream closed.
        """
        return self.fed >= len(self.pieces) and self.stream.closed

    @property
    def edits(self) -> dict[str, int]:
        """
        Edits the view has made in the library, by kind; all zero while there is no view.
        """
        if self.view is None:
            return {"set": 0, "replace": 0, "append": 0}
        return dict(self.view.edits)

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
        Count the settled lines the latest draw moved. Call after the view has drawn.

        Does nothing, and returns zero, before the first draw and when neither
        the blocks nor the width changed since the last count: a frame on
        which no text arrived moves nothing by definition. A draw at a
        different width from the last one counted also counts nothing --
        every line moved, and none of them because of the stream -- and
        becomes what the next draw is compared with.

        Only the blocks that were not yet committed at the last count are
        asked for (`_settled`); the module docstring says why that is all that
        can have moved.
        """
        view = self.view
        if view is None or view.origin is None:
            return 0
        key = (view.revision, self.width_px)
        if key == self._seen:
            return 0
        resized = self._seen is not None and key[1] != self._seen[1]
        lines = lines_of(view, 0 if resized else self._settled)
        self.changed = [] if self._seen is None or resized else changed_lines(self._lines, lines)
        moved = len(self.changed)
        if moved:
            self.moved += moved
            self.moves.append((self.fed, moved))
        self._settled = len(self.stream.committed)
        self._lines = [line for line in lines if line.block >= self._settled]
        self._seen = key
        return moved

    def tick(self, seconds: float) -> int:
        """
        One frame without a frame: feed, and take in what arrived. Returns lines moved.

        There is no layout without a draw, so this counts nothing new: zero,
        unless a draw since the last count is still to be counted. Without a
        view it only feeds.
        """
        self.advance(seconds)
        if self.view is None:
            return 0
        self.view.sync()
        return self.observe()

    def status(self) -> str:
        """
        One line for the window: how far, how fast, and what has moved.
        """
        following = self.view is None or self.view.following
        tail = "following the end" if following else "scrolled away from the end"
        return (
            f"{self.fed} of {len(self.pieces)} pieces at {self.tokens_per_second:.0f}/s"
            f"  |  {self.policy}"
            f"  |  settled lines moved: {self.moved} "
            f"(in {len(self.moves)} of {sum(self.edits.values())} edits)"
            f"  |  {tail}"
        )


def replay(
    source: str | None = None,
    *,
    theme: Theme | None = None,
    policy: str = "KEEP_STREAMED",
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


def show(playing: Replay, imgui: Any, seconds: float) -> bool:
    """
    The controls, the status line and the document, in the current window. One frame.

    Returns what the view's `draw` did: whether everything in view was set as
    asked. Raises `TypesetUnavailable` when imtypeset cannot draw; the
    document's child window has been ended by then, so the caller's frame can
    go on (or stop, as `main`'s does).

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
    for name in POLICIES:
        imgui.same_line()
        if imgui.radio_button(name, playing.policy == name) and name != playing.policy:
            playing.restart(name)
    imgui.same_line()
    if imgui.button("Restart"):
        playing.restart()
    imgui.text_unformatted(playing.status())

    playing.advance(seconds)
    imgui.begin_child(
        "##imscribe-stream-replay",
        imgui.ImVec2(0.0, 0.0),
        imgui.ChildFlags_.borders.value,
        imgui.WindowFlags_.always_vertical_scrollbar.value,
    )
    try:
        if playing.view is None:
            playing.view = TypesetStreamView(playing.stream)
        width_px = imgui.get_content_region_avail().x
        playing.whole = playing.view.draw(width_px=width_px)
        playing.width_px = width_px
    finally:
        imgui.end_child()
    playing.observe()
    return playing.whole


def report(playing: Replay, frames: int) -> list[str]:
    """
    What `main` prints when it was asked to stop by itself. Counts, not judgements.

    Asks the view for its counters, which is a call into the library: make it
    while the library's context is still there.
    """
    edits = playing.edits
    view = playing.view
    return [
        f"frames={frames} fed={playing.fed} pieces={len(playing.pieces)} "
        f"done={int(playing.done)} policy={playing.policy} "
        f"renderer=TypesetStreamView ready={int(typesetter.ready())}",
        f"edits={sum(edits.values())} appends={edits['append']} "
        f"replaces={edits['replace']} moved={playing.moved} "
        f"draws_that_moved={len(playing.moves)} "
        f"following={int(view is not None and view.following)}",
        f"vertices={0 if view is None else view.stats.vertices} whole={int(playing.whole)} "
        f"blocks={len(playing.stream.blocks)} committed={len(playing.stream.committed)}",
    ]


def main(argv: list[str] | None = None) -> int:
    """
    Open a window and replay the document in it. Needs a display and the imtypeset library.

    `--frames N` closes the window after N frames and prints `report`; with
    `--tps` high enough the whole document is fed in that time, which is how
    this is run unattended.

    Returns `NO_LIBRARY`, having said why on standard error, when imtypeset
    cannot draw: with no window opened when the library is not in use at all.
    """
    parser = argparse.ArgumentParser(description="Replay a markdown document as a token stream.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--tps", type=float, default=DEFAULT_TOKENS_PER_SECOND)
    parser.add_argument("--policy", choices=list(POLICIES), default="KEEP_STREAMED")
    parser.add_argument("--source", type=Path, default=SOURCE, help="the markdown to replay")
    args = parser.parse_args(argv)

    if typesetter.module() is None:
        print(f"imtypeset is not drawing: {typesetter.reason()}", file=sys.stderr)
        return NO_LIBRARY

    from imgui_bundle import hello_imgui, imgui, immapp

    playing = replay(
        args.source.read_text(encoding="utf-8"), policy=args.policy, tokens_per_second=args.tps
    )
    frames = 0
    report_lines: list[str] = []
    failed: list[str] = []

    def load_fonts() -> None:
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        # Last, so `Fonts[0]` stays the window's own.
        if not typesetter.load_fonts():
            failed.append(typesetter.trouble() or typesetter.reason() or "its fonts did not load")

    def gui() -> None:
        nonlocal frames
        if failed:
            hello_imgui.get_runner_params().app_shall_exit = True
            return
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.work_pos)
        imgui.set_next_window_size(viewport.work_size)
        flags = (
            imgui.WindowFlags_.no_decoration.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_saved_settings.value
        )
        try:
            if imgui.begin(WINDOW_TITLE, None, flags):
                show(playing, imgui, imgui.get_io().delta_time)
        except TypesetUnavailable as exc:
            failed.append(str(exc) or typesetter.reason())
            hello_imgui.get_runner_params().app_shall_exit = True
        finally:
            imgui.end()
        frames += 1
        if not failed and args.frames and frames >= args.frames:
            # Made here, while the library's context is still there to be asked.
            report_lines[:] = report(playing, frames)
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
    # imtypeset's context goes before the Dear ImGui context does.
    params.callbacks.before_exit = typesetter.unload
    immapp.run(params)

    if failed:
        print(f"imtypeset is not drawing: {failed[0]}", file=sys.stderr)
        return NO_LIBRARY
    if args.frames:
        print("\n".join(report_lines))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

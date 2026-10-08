r"""
A chat transcript: several finished messages and one still being written.

This is the pane a host for a language model actually has -- pptmstr's
transcript in miniature. A column of messages, most of them finished, the last
one arriving a few characters at a time; one scrollbar for the lot; text that
can be selected across a message and copied; the end kept in sight while the
reader is at the end.

    python examples/chat_transcript.py

Everything is set in **one monospace face, ragged right**, because that is
what such a host looks like and it is the hardest case for a layout library
written around justified proportional type. The theme is one call:

    Theme.at_pixel_height(15.0, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)

(`bold=Face.CODE` because the bundled files have no bold monospace: without it
the bold role would be set in the proportional bold. A host that registers one
with `register_font` leaves the argument out.)

## How it is put together

- **A finished message is a `BareView`** over a document built once. It lays
  out when the pane's width changes and at no other time; text arriving in
  another message costs it nothing.
- **The message being written is a `StreamView`** over a `StreamDocument`.
  Pieces are appended as they arrive, the view is drawn once a frame, and it
  lays out only what changed.
- **All of them are drawn into one scrolling child window**, one after the
  other, each under a line naming who wrote it. The views paint no background
  and claim only their own height, so stacking them is just drawing them.
- **The streaming view is last, and it is the one that scrolls the pane**: it
  keeps the end in sight while the reader is at the bottom and lets go when
  they scroll up, as `StreamView` does anywhere.
- **One selection across the whole transcript.** Selecting in one message
  drops the selection in another, and Ctrl+C copies from the one last selected
  in -- as the document reads, so a code block keeps its lines.

When the streaming message finishes it stays a `StreamView` over a closed
stream, which is a finished document like any other. A host with a long
history would swap it for a `BareView`; this example does not need to.

**Every message is read with link reference definitions off**
(`build_document(..., references=False)`), finished ones included. A stream
has to be: a `[1]: url` line may arrive last and would turn every earlier `[1]`
into a link after it had been shown as text. Built with the default, a
finished message would make those links, and the same reply would read one
way while it arrived and another once it was swapped for a finished view. One
setting, so a message is the same message before and after.

## What has been run, and what has not

`tests/test_example_stream.py` checks the theme is what it says (one face,
ragged), that the finished messages are not laid out again while the last one
streams, runs `show` in real ImGui frames with no display, and runs `main` in a
real window wherever an Xvfb can be started in a user namespace. **Nobody has
looked at it**, and how monospace ragged text set by this library *reads* next
to a terminal is the judgement this example was written to make possible, not
one it makes.

Everything used is importable from the package root.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from typing import Any

from advtext import (
    DARK_PALETTE,
    Align,
    BareView,
    DrawStats,
    Face,
    Faces,
    LoadedFaces,
    MetricsResolver,
    Palette,
    StreamDocument,
    StreamView,
    Theme,
    build_document,
    char_measure,
    fontlib_metrics,
    load_faces,
)

WINDOW_TITLE = "advtext: chat transcript"

BODY_PX = 15.0

DEFAULT_TOKENS_PER_SECOND = 40.0

BACKGROUND = 0xFF1E1E1E
"""
The pane's own colour, as ImGui packs one (alpha, blue, green, red): the views paint none.
"""

FINISHED: tuple[tuple[str, str], ...] = (
    (
        "you",
        "How do I keep a list's markers lined up when the numbers reach two digits?\n",
    ),
    (
        "assistant",
        "Hang the marker in the margin and right-align it against the text:\n"
        "\n"
        "1. Break the item to the measure less the indent.\n"
        "2. Pack the marker into a box exactly as wide as the indent, with "
        "stretchable glue on its **left**.\n"
        "3. Put that box in front of the first line.\n"
        "\n"
        "Then `9.` and `10.` end at the same place, and every item's text starts "
        "at the same x whatever its number.\n",
    ),
    (
        "you",
        "And for a code block inside a step?\n",
    ),
)
"""
The conversation so far: who, and the markdown they wrote.
"""

STREAMING = (
    "assistant",
    "A fence indented under its item belongs to the item, so it keeps the item's "
    "indent:\n"
    "\n"
    "1. Create the environment.\n"
    "\n"
    "   ```sh\n"
    "   python -m venv .venv\n"
    "   .venv/bin/pip install -e .\n"
    "   ```\n"
    "\n"
    "2. Run the checks, which is where a renderer that scans for blank lines goes "
    "wrong: read from its own first line, the fence above is not *inside* a step "
    "at all.\n"
    "\n"
    "| piece | arrives as |\n"
    "|-------|------------|\n"
    "| a paragraph | words |\n"
    "| a fence | whole lines |\n"
    "\n"
    "That is the whole of it.\n",
)
"""
The message still being written when the window opens.
"""


def transcript_theme(pixel_height: float = BODY_PX) -> Theme:
    """
    One monospace face at a pixel height, ragged right: what a terminal-like host sets.
    """
    return Theme.at_pixel_height(pixel_height, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)


def tokens(source: str) -> list[str]:
    """
    `source` in pieces of at most four visible characters, each with the white space before it.
    """
    return re.findall(r"\s*\S{1,4}|\s+", source)


@dataclass
class Message:
    """
    One message of the transcript: who wrote it, and the view that draws it.
    """

    role: str
    view: BareView
    stats: DrawStats | None = None


@dataclass
class Transcript:
    """
    The finished messages, the one being written, and the clock that feeds it.

    `advance(seconds)` is the whole of what happens between two frames: the
    pieces the clock allows are appended to the last message's stream. Nothing
    is laid out here; each view does that when it is drawn, or when a test
    asks it to.
    """

    theme: Theme = field(default_factory=transcript_theme)
    metrics: MetricsResolver = fontlib_metrics
    palette: Palette = DARK_PALETTE
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    finished: tuple[tuple[str, str], ...] = FINISHED
    streaming: tuple[str, str] = STREAMING

    messages: list[Message] = field(init=False)
    stream: StreamDocument = field(init=False)
    pieces: list[str] = field(init=False)
    fed: int = field(default=0, init=False)
    _owed: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        # One measure for every view: the faces are the same, and a view's
        # caches key the measure by identity.
        measure = char_measure(self.metrics)
        self.messages = [
            Message(
                role,
                BareView(
                    # Definitions off, as a stream reads: see the module docstring.
                    document=build_document(text, self.theme, self.metrics, references=False),
                    theme=self.theme,
                    measure=measure,
                ),
            )
            for role, text in self.finished
        ]
        role, text = self.streaming
        self.stream = StreamDocument(self.theme, self.metrics)
        self.pieces = tokens(text)
        self.messages.append(Message(role, StreamView(self.stream, measure)))

    @property
    def live(self) -> StreamView:
        """
        The view of the message being written: the last one.
        """
        view = self.messages[-1].view
        assert isinstance(view, StreamView)
        return view

    @property
    def done(self) -> bool:
        """
        Whether the last message has been fed in full and its stream closed.
        """
        return self.fed >= len(self.pieces) and self.stream.closed

    def advance(self, seconds: float) -> int:
        """
        Append the pieces `seconds` of the clock allow to the message being written.
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

    def status(self) -> str:
        """
        One line for the window: how much of the last message has arrived.
        """
        state = "finished" if self.done else f"writing, {self.fed} of {len(self.pieces)} pieces"
        tail = "following the end" if self.live.following else "scrolled away from the end"
        return f"{len(self.messages)} messages  |  last one {state}  |  {tail}"


def show(transcript: Transcript, fonts: Any, imgui: Any, seconds: float) -> tuple[DrawStats, ...]:
    """
    The status line and the transcript, in the current window. One frame.

    One child window holds every message, so one scrollbar scrolls the
    conversation. Three things about it are the host's side of the bargain, as
    in `examples/theme_gallery.py`: its background, pushed here because the
    views paint none; a scrollbar that is always there, so the width the
    messages are broken to does not change when the conversation first
    outgrows the pane; and a border, which is what gives a child its padding.

    `seconds` is the time since the last frame, and `imgui` is passed in so
    that this module imports no ImGui until `main` runs.
    """
    imgui.text_unformatted(transcript.status())
    transcript.advance(seconds)
    imgui.push_style_color(imgui.Col_.child_bg, BACKGROUND)
    imgui.begin_child(
        "##advtext-chat-transcript",
        imgui.ImVec2(0.0, 0.0),
        imgui.ChildFlags_.borders.value,
        imgui.WindowFlags_.always_vertical_scrollbar.value,
    )
    for message in transcript.messages:
        imgui.text_disabled(message.role)
        message.stats = message.view.draw(fonts=fonts, palette=transcript.palette)
        imgui.spacing()
    imgui.end_child()
    imgui.pop_style_color()
    return tuple(message.stats for message in transcript.messages if message.stats is not None)


def report(transcript: Transcript, frames: int) -> list[str]:
    """
    What `main` prints when it was asked to stop by itself: a line a message, then a total.
    """
    lines = []
    for number, message in enumerate(transcript.messages):
        stats = message.stats
        lines.append(
            f"message={number} role={message.role} "
            f"glyphs={0 if stats is None else stats.glyphs} "
            f"missing={0 if stats is None else stats.missing} "
            f"blocks={len(message.view.document.blocks)}"
        )
    lines.append(
        f"frames={frames} messages={len(transcript.messages)} fed={transcript.fed} "
        f"done={int(transcript.done)} following={int(transcript.live.following)}"
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the transcript in it. Needs a display.

    `--frames N` closes the window after N frames and prints `report`.
    """
    parser = argparse.ArgumentParser(description="A chat transcript with one message streaming.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--tps", type=float, default=DEFAULT_TOKENS_PER_SECOND)
    args = parser.parse_args(argv)

    from imgui_bundle import hello_imgui, imgui, immapp

    transcript = Transcript(tokens_per_second=args.tps)
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
            show(transcript, loaded[-1], imgui, imgui.get_io().delta_time)
        imgui.end()
        frames += 1
        if args.frames and frames >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (760, 620)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    # An example should not leave an .ini beside wherever it was launched from.
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    immapp.run(params)

    if args.frames:
        print("\n".join(report(transcript, frames)))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

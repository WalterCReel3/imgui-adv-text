r"""
A chat transcript: several finished messages and one still being written.

This is the pane a host for a language model actually has -- pptmstr's
transcript in miniature. A column of messages, most of them finished, the last
one arriving a few characters at a time; one scrollbar for the lot; text that
can be selected across a message and copied; the end kept in sight while the
reader is at the end. It is drawn by the imtypeset library:

    IMTYPESET_LIBRARY=... python examples/chat_transcript.py

(`examples/typeset_minimal.py` has the whole command line; `make typeset-lib`
builds the library.)

Everything is set in **one monospace face, ragged right**, because that is
what such a host looks like and it is the hardest case for a layout library
written around justified proportional type. The theme is one call:

    Theme.at_pixel_height(15.0, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)

(`bold=Face.CODE` because the bundled files have no bold monospace: without it
the bold role would be set in the proportional bold.) That call measures the
face to turn a pixel height into a size, and measuring a face is still
`advtext.fontlib_metrics`, the one thing here that is not the typeset
layer's: imtypeset has no metrics query yet.

## How it is put together

- **A finished message is an `advtext.ui.typeset_view.TypesetView`** given its
  markdown as a string. The library holds one document for it and lays it
  out when the pane's width changes and at no other time; text arriving in
  another message costs it nothing.
- **The message being written is an
  `advtext.ui.typeset_stream_view.TypesetStreamView`** over an
  `advtext.typeset_markdown.MarkdownStream`. Pieces are appended as they
  arrive, the view is drawn once a frame, and it hands the library at most
  one edit for what changed.
- **All of them are drawn into one scrolling child window**, one after the
  other, each under a line naming who wrote it. The views paint no background
  and claim only their own height, so stacking them is just drawing them.
- **The streaming view is last, and it is the one that scrolls the pane**: it
  keeps the end in sight while the reader is at the bottom and lets go when
  they scroll up.
- **One selection across the whole transcript.** Selecting in one message
  drops the selection in another, and Ctrl+C copies from the one last selected
  in -- as the document reads, so a code block keeps its lines.

When the streaming message finishes it stays a view over a closed stream,
which is a finished document like any other.

**Every message is read with link reference definitions off**
(`TypesetView(..., references=False)`), finished ones included. A stream has
to be: a `[1]: url` line may arrive last and would turn every earlier `[1]`
into a link after it had been shown as text. Built with the default, a
finished message would make those links, and the same reply would read one
way while it arrived and another once it was swapped for a finished view. One
setting, so a message is the same message before and after.

## Without the library

There is no other renderer, so the example does not open a window it could
draw nothing in. `main` asks for the library before it makes a window; when
it is not in use it prints why to standard error and returns `NO_LIBRARY`
(1). Fonts that do not load, or a draw that raises `TypesetUnavailable`, can
only happen with the window open: it is closed at once and `main` prints the
reason and returns the same 1.

A `Transcript` itself needs no library until it is shown: the messages' text
and the clock are plain Python, and the views are made by the first `show`
(`open`), which raises `TypesetUnavailable` when imtypeset is not in use.

## What has been run, and what has not

`tests/test_example_stream.py` checks the theme is what it says (one face,
ragged) and drives the clock with no library, and, in children that load the
library, that the finished messages are not handed to the library again while
the last one streams, `show` in real ImGui frames with no display, and `main`
in a real window wherever an Xvfb can be started in a user namespace.
**Nobody has looked at it**, and how monospace ragged text set this way
*reads* next to a terminal is the judgement this example was written to make
possible, not one it makes.

Everything is imported from the package root: the theme, the faces and the
palette, the stream, the two views, and the module `typesetter`.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from advtext import (
    DARK_PALETTE,
    Align,
    Face,
    Faces,
    MarkdownStream,
    Palette,
    Theme,
    TypesetStreamView,
    TypesetUnavailable,
    TypesetView,
    typesetter,
)

WINDOW_TITLE = "advtext: chat transcript"

BODY_PX = 15.0

DEFAULT_TOKENS_PER_SECOND = 40.0

NO_LIBRARY = 1
"""
What `main` returns when imtypeset cannot draw, after saying why on standard error.

The status the other examples of the typeset layer return for it
(`examples/diff_minimal.py`, `examples/typeset_minimal.py`). It is also what
an uncaught exception exits with, so a caller that must tell the two apart
reads standard error: one line beginning `imtypeset is not drawing: `.
"""

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

    Measures the face (`advtext.fontlib_metrics`, asked by
    `Theme.at_pixel_height`) to turn the pixel height into a size.
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
    One message of the transcript: who wrote it, what they wrote, and the view that draws it.
    """

    role: str
    markdown: str
    """The message's text; for the one being written, what it will be when it has all arrived."""
    view: Any = None
    """A `TypesetView` (the last one a `TypesetStreamView`); `None` until `Transcript.open`."""
    whole: bool = True
    """Whether the library's last draw set everything in view as asked."""
    vertices: int = 0
    """Vertices the view's last draw added to the pane's draw list."""


@dataclass
class Transcript:
    """
    The finished messages, the one being written, and the clock that feeds it.

    `advance(seconds)` is the whole of what happens between two frames: the
    pieces the clock allows are appended to the last message's stream. Nothing
    is laid out here, and nothing here needs the library: the views are made
    by `open`, which the first `show` calls.
    """

    theme: Theme = field(default_factory=transcript_theme)
    palette: Palette = DARK_PALETTE
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    finished: tuple[tuple[str, str], ...] = FINISHED
    streaming: tuple[str, str] = STREAMING

    messages: list[Message] = field(init=False)
    stream: MarkdownStream = field(init=False)
    """The stream the last message arrives through, read in `theme` throughout."""
    pieces: list[str] = field(init=False)
    fed: int = field(default=0, init=False)
    _owed: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.pieces = tokens(self.streaming[1])
        self.stream = MarkdownStream(self.theme)
        self.messages = [Message(role, text) for role, text in (*self.finished, self.streaming)]

    def open(self) -> None:
        """
        Make the view of every message that has none. Raises `TypesetUnavailable`.

        A finished message's view is given its markdown with definitions off,
        as a stream reads (the module docstring has why); the last message's
        is over the stream.
        """
        last = len(self.messages) - 1
        for number, message in enumerate(self.messages):
            if message.view is not None:
                continue
            if number == last:
                message.view = TypesetStreamView(self.stream, palette=self.palette)
            else:
                message.view = TypesetView(
                    message.markdown, theme=self.theme, palette=self.palette, references=False
                )

    @property
    def live(self) -> Any:
        """
        The view of the message being written: the last one. `None` before `open`.
        """
        return self.messages[-1].view

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
        following = self.live is None or self.live.following
        tail = "following the end" if following else "scrolled away from the end"
        return f"{len(self.messages)} messages  |  last one {state}  |  {tail}"


def show(transcript: Transcript, imgui: Any, seconds: float) -> tuple[bool, ...]:
    """
    The status line and the transcript, in the current window. One frame.

    Returns what each message's draw did: whether everything in view was set
    as asked. Raises `TypesetUnavailable` when imtypeset cannot draw; the
    child window has been ended and the colour popped by then, so the
    caller's frame can go on (or stop, as `main`'s does).

    One child window holds every message, so one scrollbar scrolls the
    conversation. Three things about it are the host's side of the bargain:
    its background, pushed here because the views paint none; a scrollbar
    that is always there, so the width the messages are broken to does not
    change when the conversation first outgrows the pane; and a border, which
    is what gives a child its padding.

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
    try:
        transcript.open()
        for message in transcript.messages:
            imgui.text_disabled(message.role)
            buffer = imgui.get_window_draw_list().vtx_buffer
            before = buffer.size()
            message.whole = message.view.draw(palette=transcript.palette)
            message.vertices = buffer.size() - before
            imgui.spacing()
    finally:
        imgui.end_child()
        imgui.pop_style_color()
    return tuple(message.whole for message in transcript.messages)


def report(transcript: Transcript, frames: int) -> list[str]:
    """
    What `main` prints when it was asked to stop by itself: a line a message, then a total.
    """
    lines = []
    for number, message in enumerate(transcript.messages):
        blocks = 0 if message.view is None else len(message.view.blocks)
        lines.append(
            f"message={number} role={message.role} vertices={message.vertices} "
            f"whole={int(message.whole)} blocks={blocks}"
        )
    live = transcript.live
    lines.append(
        f"frames={frames} messages={len(transcript.messages)} fed={transcript.fed} "
        f"done={int(transcript.done)} following={int(live is not None and live.following)} "
        f"renderer=TypesetView ready={int(typesetter.ready())}"
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the transcript in it. Needs a display and the imtypeset library.

    `--frames N` closes the window after N frames and prints `report`.

    Returns `NO_LIBRARY`, having said why on standard error, when imtypeset
    cannot draw: with no window opened when the library is not in use at all.
    """
    parser = argparse.ArgumentParser(description="A chat transcript with one message streaming.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--tps", type=float, default=DEFAULT_TOKENS_PER_SECOND)
    args = parser.parse_args(argv)

    if typesetter.module() is None:
        print(f"imtypeset is not drawing: {typesetter.reason()}", file=sys.stderr)
        return NO_LIBRARY

    from imgui_bundle import hello_imgui, imgui, immapp

    transcript = Transcript(tokens_per_second=args.tps)
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
                show(transcript, imgui, imgui.get_io().delta_time)
        except TypesetUnavailable as exc:
            failed.append(str(exc) or typesetter.reason())
            hello_imgui.get_runner_params().app_shall_exit = True
        finally:
            imgui.end()
        frames += 1
        if not failed and args.frames and frames >= args.frames:
            report_lines[:] = report(transcript, frames)
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

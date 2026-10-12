#!/usr/bin/env python3
r"""
Play a mouse into the real demo and check what it selected and what it copied.

The Document page's view turns a pointer position into a range of the document
and a keypress into clipboard text. For most of this project's life that path
had run sixty times a second with `is_mouse_clicked` false and no further.
This script is the instrument that retired that sentence, and it says below
exactly how far it retires it.

## What it does

It runs **the real app** -- `imscribe.ui.app.run`, through the real
`immapp.run`, with the real fonts, sidebar, scrolling child window and GLFW
clipboard -- and before each frame posts input events to ImGui's own queue
(`io.add_mouse_pos_event`, `add_mouse_button_event`, `add_mouse_wheel_event`,
`add_key_event`). The positions are not guessed.
`imscribe.ui.typeset_view.TypesetView._handle_mouse` is wrapped for the length
of the run so that the screen origin the view itself used on the last frame
can be read back; the wrapper calls the real method and changes nothing.

Eight gestures:

1. a drag over the first two words of a line, left to right;
2. the same drag right to left, which must select the same thing;
3. a drag from the first line of a paragraph to its third;
4. a double click on a word;
5. a triple click on a line;
6. Ctrl+C, read back from the clipboard, which is seeded with a sentinel first
   so that a copy that never happened cannot pass on stale contents;
7. a wheel scroll past a whole window height, then a drag on a line that was
   below the fold before it -- the check that the hit-test origin follows the
   scroll;
8. a drag that starts on a visible line and ends on a line below the bottom of
   the window, then Ctrl+C: culling what is drawn does not cull what is copied.

Lines are found **by content** and a missing one is a loud failure, per
`.concerns/lead--visual-standard.md`: a target that silently lands somewhere
else is how a crop of whitespace got reviewed twice.

## What it aims with, what it expects, and its limit

What it aims with is the view's public surface: `origin`, `set_lines()` (each
line as a range of its block's text and a rectangle) and `span_rects()` (where
one character is). What it expects is a slice of `TypesetView.texts`, which is
the description handed to the library and not anything the library answered,
and for the paragraph drag that slice must also occur verbatim in the markdown.
What it never calls to build an expectation is `hit_test`, `select_range` or
`selected_text`. **Its limit**: where a character is on screen is asked of the
same library that then hit-tests the click (`range_rects` going out,
`select_range` coming back), so a defect the two share is not seen; what is
seen is the view's part, which is the origin it subtracts, the scroll, the
press and drag state, the click counter, the ownership of the selection and
the copy.

## It needs the imtypeset library, and says so when there is none

The Document page draws a `TypesetView` when the library is loaded and its
fonts are in the atlas (`imscribe.typesetter.ready()`), and one line saying why
not otherwise. Until tranche 5 (2026-10-11) it drew imscribe's own
`DocumentView` then, and this script had a second gesture script for that
view, with expectations built from the old core's shipped glyphs
(`imscribe.selection`, `imscribe.shipout`). That half is gone with the fallback
it probed. With no library there is nothing to play a mouse at: the run stops
before the first gesture, prints the page's own sentence, and exits 2
(`make typeset-lib`, then `IMTYPESET_LIBRARY=... IMTYPESET_PYTHON=...`, or
`make ... TYPESET=1`). With the library asked for and a view that still does
not draw, the exit is 1: that is a failure, not an absence.

## What it does not do, stated so nobody reads more into a green run

**The events enter at ImGui's input queue, not at the X server.** No pointer
moved on any screen; `xdotool` is not installed here and nothing else in this
environment synthesises an X event. So GLFW's cursor and button callbacks, and
the window manager's part in focus and capture, are still unexercised. What is
exercised is everything from `ImGuiIO` inward, in a real window: hover
resolution against the real sidebar and child window, the invisible button, the
click counter on real frame times, scrolling, the selection, and
`glfwSetClipboardString` / `glfwGetClipboardString` behind
`imgui.set_clipboard_text`.

**It asserts change, not appearance.** `--shot` writes the last frame so the
highlight can be looked at; this script makes no claim about how it looks.

## Three ways to run it

    python scripts/mouse_probe.py              # a window on $DISPLAY
    python scripts/mouse_probe.py --xvfb       # start an Xvfb in a user namespace first
    python scripts/mouse_probe.py --no-window  # a real ImGui context and no backend at all

`--xvfb` is how it was run where it was written. `DISPLAY=:1` is set in that
sandbox and is unreachable from it -- `socket(AF_UNIX)` is refused outright with
`EPERM`, so GLFW cannot connect and aborts with `IM_ASSERT( glfwInitSuccess )`.
What does work there, measured on 2026-10-06, is the chain `scripts/shot.sh`
documents, with one change: `unshare -rm`, a tmpfs over `/tmp`, and
`Xvfb :99 -listen tcp -nolisten unix`, reached as `DISPLAY=127.0.0.1:99` with
Mesa's software rasteriser. `-nolisten unix` is the change; with AF_UNIX
refused there is no unix socket to listen on. The app opens in that server in
about two seconds.

`--no-window` drives the same script through `App.gui()` inside frames of a
bare `imgui.create_context()`. There is no runner there to call the app's
font callback, so this mode calls it itself (`imscribe.ui.app.
_load_fonts_for_run`, which loads the library's fonts into the bare context's
atlas) and unloads the library afterwards. It is lower fidelity in the ways
one would expect: nothing rasterises a glyph, the clipboard is ImGui's
in-memory one rather than the platform's, and `delta_time` is fixed.

Exit status: 0 when every check passed, 1 when one did not, 2 when the probe
could not run at all (no display, no `unshare`, no imtypeset library).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Run from anywhere without an install, matching scripts/shot.py.
if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(ROOT))

OPENING = "This document is the first"
"""
How the line the first six gestures aim at begins, in `demo/sample.md`.

The first paragraph, because it is plain prose with no inline markup: its
shipped characters are the source's characters, which is what lets the
paragraph drag be checked against the markdown file rather than against the
layout. `--opening` names another for a different `--source`.
"""

SENTINEL = "mouse-probe: nothing has been copied yet"
"""
What the clipboard holds before each copy, so stale contents cannot pass.
"""

XVFB_DISPLAY_NUMBER = 99

SETTLE_FRAMES = 24
"""
Idle frames before the first gesture: 0.4 s at the bare context's sixty a second.
"""

MAX_FRAMES = 2000
"""
A runaway bound. The whole script is about ninety frames; a probe still going at
two thousand is one whose generator is waiting on something that will not come.
"""


class ProbeError(RuntimeError):
    """
    The probe could not set up a gesture: a target was not where the script needs it.

    Distinct from a failed check. A check that fails says the view selected the
    wrong thing; this says the probe never got to ask.
    """


# ----------------------------------------------------------------------
# Events. Plain data, so a test can read a gesture without an ImGui context.


@dataclass(frozen=True, slots=True)
class Move:
    """The pointer, in screen pixels."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Button:
    """The left button going down or coming up."""

    down: bool


@dataclass(frozen=True, slots=True)
class Wheel:
    """Vertical wheel travel in ImGui's units; negative scrolls the document up."""

    dy: float


@dataclass(frozen=True, slots=True)
class Key:
    """A key going down or coming up. `name` is `"ctrl"` or `"c"`."""

    name: str
    down: bool


Event = Move | Button | Wheel | Key


def post(io: Any, event: Event, imgui: Any) -> None:
    """
    Queue one event on ImGui's input queue.

    The `add_*_event` family and nothing else: writing `io.mouse_pos` or
    `io.mouse_down` directly bypasses the queue that a real backend feeds, and
    the queue is where ImGui's own ordering rules live (a press and a release
    posted together are spread over two frames; a position is applied before
    the button that follows it).
    """
    match event:
        case Move(x, y):
            io.add_mouse_pos_event(x, y)
        case Button(down):
            io.add_mouse_button_event(0, down)
        case Wheel(dy):
            io.add_mouse_wheel_event(0.0, dy)
        case Key(name, down):
            io.add_key_event({"ctrl": imgui.Key.mod_ctrl, "c": imgui.Key.c}[name], down)


# ----------------------------------------------------------------------
# What the view did on its last frame, read back rather than recomputed.


@dataclass(slots=True)
class SeenTypeset:
    """
    The last frame's `TypesetView` and where it put the document, in pixels.

    Filled in by `watch`. There is no layout
    object to hold: the view answers `set_lines` and `span_rects` in pixels from
    the document's corner, and `origin` is where that corner was on screen.
    """

    view: Any = None
    origin: tuple[float, float] = (0.0, 0.0)
    window_top: float = 0.0
    window_height: float = 0.0
    frames: int = 0

    def lines(self) -> list[Any]:
        """
        Every line of every block that is neither a table nor a hosted widget.

        `TypesetView.set_lines`, which lays out each block it is asked about:
        after this the document's height is no longer an estimate, so a line's
        place does not move under a later gesture. A table's lines sit side by
        side and a hosted block has none, and the probe aims only where "the
        line at this y" has one answer.
        """
        if self.view is None:
            raise ProbeError("no TypesetView has drawn a frame, so there are no lines to aim at")
        skipped = {*self.view.tables, *self.view.hosts}
        return [line for line in self.view.set_lines() if line.block not in skipped]

    def text(self, line: Any) -> str:
        """The characters of one line: its range of the block's described text."""
        whole: str = self.view.texts[line.block]
        return whole[line.start : line.end]

    def on_screen(self, line: Any, *, inset_px: float = 4.0) -> bool:
        """Whether a line's whole band is inside the child window."""
        return (
            self.origin[1] + line.top >= self.window_top + inset_px
            and self.origin[1] + line.bottom <= self.window_top + self.window_height - inset_px
        )

    def point(self, line: Any, offset: int, fraction: float) -> Move:
        """
        The screen position `fraction` of the way across character `offset` of a line.

        The character's rectangle is
        `span_rects` of that one character, and a character with no rectangle
        of its own, or with one of no width, is a loud failure rather than a
        guess at where it might be.
        """
        at = line.start + offset
        rects = self.view.span_rects(line.block, at, at + 1)
        if len(rects) != 1 or not rects[0][2] > rects[0][0]:
            raise ProbeError(
                f"character {offset} of the line {self.text(line)!r} "
                f"has no one rectangle: {rects!r}"
            )
        left, top, right, bottom = rects[0]
        return Move(
            self.origin[0] + left + fraction * (right - left),
            self.origin[1] + (top + bottom) / 2.0,
        )

    def line_copy(self, line: Any) -> str:
        """
        What copying one whole line should put on the clipboard.

        The line's characters without the white space it was broken at. That
        is the library's stated rule and not something this file found out by
        asking it: "a copy does not end in the space a line was broken at"
        (`../imtypeset/docs/advtext-swap-status.md`, "Answers"). A line that ends where its block's
        text ends was not broken and loses nothing.
        """
        text = self.text(line)
        broken = line.end < len(self.view.texts[line.block])
        return text.rstrip() if broken else text

    def copies_as_itself(self, line: Any) -> bool:
        """
        Whether copying this whole line gives `line_copy` of it.

        False where the text a copy gives is not the text described (the
        library's own account of a range), so gestures 7 and 8 do not aim there.
        """
        document = self.view.native_document
        copied = document.range_text(
            ((line.block, line.start), (line.block, line.end)), self.view.separator
        )
        return bool(copied == self.line_copy(line))


@dataclass(slots=True)
class Seen:
    """
    What the run saw: the `TypesetView` that drew, and that one did.

    `renderer` is the class whose `_handle_mouse` was called last, `""` when
    none was: the Document page then drew its one line and no view.
    """

    typeset: SeenTypeset = field(default_factory=SeenTypeset)
    renderer: str = ""


@contextlib.contextmanager
def watch(seen: Seen) -> Iterator[None]:
    """
    Record every `TypesetView._handle_mouse` call into `seen.typeset`, changing nothing.

    The wrapper calls the real method with the real arguments; it exists because
    the origin the view hit-tests against is computed inside `draw` from ImGui's
    cursor and is not otherwise observable. Reading it here rather than
    re-deriving it is the point: a probe that recomputed the origin would aim at
    where it thinks the text is, and the defect worth finding is the view and
    the pixels disagreeing about that.

    Patched on the class and restored on exit, including when the run raises.
    """
    from imgui_bundle import imgui

    from imscribe.ui.typeset_view import TypesetView

    real_typeset = TypesetView._handle_mouse

    def spy_typeset(self: Any, doc: Any, origin: Any, size: Any) -> Any:
        typeset = seen.typeset
        typeset.view = self
        typeset.origin = (float(origin.x), float(origin.y))
        typeset.window_top = float(imgui.get_window_pos().y)
        typeset.window_height = float(imgui.get_window_size().y)
        typeset.frames += 1
        seen.renderer = "TypesetView"
        return real_typeset(self, doc, origin, size)

    TypesetView._handle_mouse = spy_typeset  # type: ignore[method-assign]
    try:
        yield
    finally:
        TypesetView._handle_mouse = real_typeset  # type: ignore[method-assign]


# ----------------------------------------------------------------------
# Aiming.


def first_words_end(text: str, count: int = 2) -> int:
    """
    How many characters the first `count` space-separated words of `text` span.
    """
    spans = [match.end() for match in re.finditer(r"\S+", text)]
    if not spans:
        raise ProbeError("the targeted line has no words on it")
    return spans[min(count, len(spans)) - 1]


def squeeze(text: str) -> str:
    """Runs of whitespace as one space, for comparing prose against its source."""
    return " ".join(text.split())


# ----------------------------------------------------------------------
# Results


@dataclass(frozen=True, slots=True)
class Check:
    """One expectation and what was found."""

    name: str
    expected: object
    actual: object

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


def report(checks: Sequence[Check]) -> str:
    """
    One line a check, with both values on a failure.
    """
    lines = []
    for check in checks:
        lines.append(f"{'PASS' if check.ok else 'FAIL'}  {check.name}")
        if not check.ok:
            lines.append(f"        expected {check.expected!r}")
            lines.append(f"        actual   {check.actual!r}")
    failed = sum(1 for check in checks if not check.ok)
    lines.append(f"{len(checks) - failed} of {len(checks)} checks passed")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# The gestures. A generator: each `yield` is one frame's events, and the code
# after it runs before the next frame, once the view has seen them.

Frames = Iterator[list[Event]]


def _play(*events: Event) -> Frames:
    """
    One event a frame, then one frame with none.

    One a frame because that is what a hand does and because hover is resolved
    from the position that was current when the item was submitted: a press
    posted with its own move is a press on wherever the pointer was before. The
    trailing empty frame means the caller reads state the view has finished
    updating whether the host drains the queue before or after its callback.
    """
    for event in events:
        yield [event]
    yield []


def _copy(imgui: Any) -> Frames:
    """Seed the clipboard with the sentinel, then press and release Ctrl+C."""
    imgui.set_clipboard_text(SENTINEL)
    yield from _play(Key("ctrl", True), Key("c", True), Key("c", False), Key("ctrl", False))


class NotDrawing(ProbeError):
    """
    No `TypesetView` drew a frame, so there was nothing to play a mouse at.

    The message is the Document page's own sentence
    (`imscribe.ui.pages.typeset.why_not`). `main` exits 2 on this when the
    library was never asked for, and 1 when it was: the first is an absence,
    the second a failure.
    """


def script(
    seen: Seen,
    imgui: Any,
    checks: list[Check],
    *,
    source: str,
    opening: str = OPENING,
) -> Frames:
    """
    The settling frames, then the eight gestures of `script_for_typeset`.

    `source` is the markdown the app was given, used once: the paragraph drag's
    expected text must occur in it verbatim, which is the one expectation here
    that does not come from the view at all.
    """
    # Settling. The first frame sizes the child window and the second gives it
    # its scrollbar, which narrows the content region; the layout is not the one
    # the rest of the run will use until then. Longer than that needs, because
    # a context reused from an earlier run may hold a recent click, and a press
    # near it inside ImGui's 0.3 s double-click time would count as its second.
    for _ in range(SETTLE_FRAMES):
        yield []
    if seen.renderer != "TypesetView":
        from imscribe.ui.pages.typeset import not_drawing, why_not

        raise NotDrawing(
            "the Document page drew no TypesetView in "
            f"{SETTLE_FRAMES} frames; it says: {not_drawing(why_not())}"
        )
    yield from script_for_typeset(seen.typeset, imgui, checks, source=source, opening=opening)


def _typeset_range(line: Any, begin: int, end: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Characters `[begin, end)` of a line, as a `TypesetView` states a selection."""
    return ((line.block, line.start + begin), (line.block, line.start + end))


def _drag_first_words_typeset(
    seen: SeenTypeset, line: Any, label: str, checks: list[Check]
) -> Frames:
    """Drag over the first two words of a line, forwards, and check it."""
    text = seen.text(line)
    count = first_words_end(text)
    yield from _play(
        seen.point(line, 0, 0.25),
        Button(True),
        seen.point(line, count - 1, 0.75),
        Button(False),
    )
    checks.append(Check(f"{label}: range", _typeset_range(line, 0, count), seen.view.selection))
    checks.append(Check(f"{label}: text", text[:count], seen.view.selected_text()))


def _prose(seen: SeenTypeset, line: Any, words: int) -> bool:
    """Whether a line begins with a character and holds `words` words or more."""
    text = seen.text(line)
    return bool(text) and not text[0].isspace() and len(re.findall(r"\S+", text)) >= words


def script_for_typeset(
    seen: SeenTypeset,
    imgui: Any,
    checks: list[Check],
    *,
    source: str,
    opening: str = OPENING,
) -> Frames:
    """
    The eight gestures, played at a `TypesetView`.

    Entered from `script` after its settling frames. Eighteen checks. The module
    docstring says what the expectations are built from and what they cannot see.
    """
    view = seen.view
    lines = seen.lines()
    found = [at for at, line in enumerate(lines) if seen.text(line).startswith(opening)]
    if not found:
        present = [seen.text(line)[:40] for line in lines[:6]]
        raise ProbeError(f"no line starts with {opening!r}; the first lines are {present!r}")
    at = found[0]
    if at + 2 >= len(lines) or len({line.block for line in lines[at : at + 3]}) != 1:
        raise ProbeError(f"the paragraph starting {opening!r} must run to at least three lines")
    first, second, third = lines[at : at + 3]
    if not all(seen.on_screen(line) for line in (first, second, third)):
        raise ProbeError(f"the paragraph starting {opening!r} is not on screen at the start")
    whole: str = view.texts[first.block]

    # 1. A drag, left to right.
    yield from _drag_first_words_typeset(
        seen, first, "1 drag over two words, left to right", checks
    )

    # 2. The same drag backwards.
    text = seen.text(first)
    count = first_words_end(text)
    yield from _play(
        seen.point(first, count - 1, 0.75),
        Button(True),
        seen.point(first, 0, 0.25),
        Button(False),
    )
    checks.append(
        Check(
            "2 the same drag, right to left: range",
            _typeset_range(first, 0, count),
            view.selection,
        )
    )
    checks.append(Check("2 the same drag, right to left: text", text[:count], view.selected_text()))

    # 3. Across lines: from the second word of the first line to the end of the
    #    first word of the third. Within a block a copy is the text as written,
    #    so the expectation is that stretch of the described text, whatever
    #    white space the description has where the lines were broken.
    start = first_words_end(text, 1) + 1
    stop = first_words_end(seen.text(third), 1)
    expected = whole[first.start + start : third.start + stop]
    checks.append(
        Check(
            "3 the expected paragraph text occurs verbatim in the markdown source",
            True,
            squeeze(expected) in squeeze(source),
        )
    )
    yield from _play(
        seen.point(first, start, 0.25),
        Button(True),
        seen.point(third, stop - 1, 0.75),
        Button(False),
    )
    checks.append(
        Check(
            "3 drag across three lines: range",
            ((first.block, first.start + start), (third.block, third.start + stop)),
            view.selection,
        )
    )
    checks.append(Check("3 drag across three lines: text", expected, view.selected_text()))

    # 4. A double click, on the second word of the second line that is three
    #    letters or more and has white space or the line's end on both sides:
    #    a word nobody's rule for a word boundary could cut differently.
    second_text = seen.text(second)
    words = [match for match in re.finditer(r"(?<!\S)\w{3,}(?!\S)", second_text)]
    if len(words) < 2:
        raise ProbeError(f"the line {second_text!r} needs two words of three letters or more")
    word = words[1]
    on_word = seen.point(second, (word.start() + word.end() - 1) // 2, 0.5)
    yield from _play(on_word, Button(True), Button(False), Button(True), Button(False))
    checks.append(
        Check(
            "4 double click: range",
            _typeset_range(second, word.start(), word.end()),
            view.selection,
        )
    )
    checks.append(Check("4 double click: text", word.group(), view.selected_text()))

    # 5. A triple click, on the third line, on the character nearest its
    #    middle that is not white space. The range is the whole of the line's
    #    range of the text, the white space it was broken at included; the
    #    copy is without that white space (`SeenTypeset.line_copy`).
    third_text = seen.text(third)
    middle = len(third_text) // 2
    while middle < len(third_text) - 1 and third_text[middle].isspace():
        middle += 1
    yield from _play(
        seen.point(third, middle, 0.5),
        Button(True),
        Button(False),
        Button(True),
        Button(False),
        Button(True),
        Button(False),
    )
    checks.append(
        Check("5 triple click: range", _typeset_range(third, 0, len(third_text)), view.selection)
    )
    checks.append(Check("5 triple click: text", seen.line_copy(third), view.selected_text()))

    # 6. Copy it.
    yield from _copy(imgui)
    checks.append(
        Check(
            "6 ctrl+C: the clipboard holds the line",
            seen.line_copy(third),
            imgui.get_clipboard_text(),
        )
    )

    # 7. Scroll by more than a window, then drag on a line that was below the
    #    fold. `fold` is in the document's own pixels, which a scroll leaves alone.
    origin_before = seen.origin[1]
    height = seen.window_height
    fold = seen.window_top + height - origin_before
    yield from _play(Move(seen.origin[0] + 40.0, seen.window_top + height / 2.0))
    for _ in range(80):
        if origin_before - seen.origin[1] > height:
            break
        yield [Wheel(-3.0)]
    yield []
    yield []
    scrolled = origin_before - seen.origin[1]
    checks.append(
        Check("7 the wheel scrolled the document by more than a window", True, scrolled > height)
    )

    lines = seen.lines()
    below = [
        line
        for line in lines
        if line.top > fold
        and seen.on_screen(line)
        and _prose(seen, line, 3)
        and seen.copies_as_itself(line)
    ]
    if not below:
        raise ProbeError("after scrolling, no line that began below the fold is on screen")
    press = below[0]
    yield from _drag_first_words_typeset(
        seen, press, "7 drag on a line that was below the fold before the scroll", checks
    )

    # 8. Press on that line's second word (not its first: `script` says why)
    #    and release on a line beneath the window's bottom edge, which the
    #    library has not drawn.
    press_text = seen.text(press)
    begin = first_words_end(press_text, 1) + 1
    bottom = seen.window_top + seen.window_height
    beyond = [
        line
        for line in lines
        if seen.origin[1] + line.top > bottom + 100.0
        and _prose(seen, line, 1)
        and line.end - line.start >= 4
        and seen.copies_as_itself(line)
    ]
    if not beyond:
        raise ProbeError(
            "no line lies more than 100 px below the window; the document is too short"
        )
    release = beyond[0]
    stop = first_words_end(seen.text(release), 1)
    yield from _play(
        seen.point(press, begin, 0.25),
        Button(True),
        seen.point(release, stop - 1, 0.75),
        Button(False),
    )
    wanted = ((press.block, press.start + begin), (release.block, release.start + stop))
    checks.append(Check("8 drag past the bottom of the window: range", wanted, view.selection))
    selected = view.selected_text()
    # What a copy across blocks gives, restated from the view's contract and
    # not asked of it: each block's text, the first from the press and the
    # last to the release, the separator between, and nothing (no separator
    # either) for a block with no text.
    texts = view.texts
    if press.block == release.block:
        parts = [texts[press.block][press.start + begin : release.start + stop]]
    else:
        parts = [
            texts[press.block][press.start + begin :],
            *texts[press.block + 1 : release.block],
            texts[release.block][: release.start + stop],
        ]
    checks.append(
        Check(
            "8 drag past the bottom of the window: text runs from the pressed line to the unseen",
            view.separator.join(part for part in parts if part),
            selected,
        )
    )
    yield from _copy(imgui)
    checks.append(
        Check(
            "8 ctrl+C: the clipboard holds all of it, the undrawn part included",
            selected,
            imgui.get_clipboard_text(),
        )
    )


# ----------------------------------------------------------------------
# Driving it


@dataclass(slots=True)
class Driver:
    """
    Feeds the script to a frame loop, one `yield` a frame.

    The same object drives a real window and a bare context, which is what makes
    the headless test a test of this script and not of a second one like it.
    An exception inside the script is held rather than raised: in a window it
    would otherwise unwind through a C++ callback, and the run has to end and
    restore `immapp.run` before anything is reported.
    """

    frames_of: Frames
    done: bool = False
    error: BaseException | None = None
    frames: int = 0
    posted: list[Event] = field(default_factory=list)

    def before_frame(self, io: Any, imgui: Any) -> None:
        if self.done:
            return
        self.frames += 1
        try:
            if self.frames > MAX_FRAMES:
                raise ProbeError(f"still running after {MAX_FRAMES} frames")
            events = next(self.frames_of)
        except StopIteration:
            self.done = True
            return
        except Exception as error:  # noqa: BLE001 - held and reported by the caller
            self.error = error
            self.done = True
            return
        for event in events:
            post(io, event, imgui)
            self.posted.append(event)


@dataclass(frozen=True, slots=True)
class Outcome:
    """What a run produced: the checks, how it ended, and how long it took."""

    mode: str
    checks: tuple[Check, ...]
    error: BaseException | None
    frames: int
    seconds: float
    renderer: str = ""
    """`TypesetView`, the view the gestures were played at; `""` if none drew."""

    @property
    def passed(self) -> bool:
        return self.error is None and bool(self.checks) and all(check.ok for check in self.checks)


def run_without_a_window(source: str, *, opening: str = OPENING) -> Outcome:
    """
    The script, through `App.gui()`, in frames of a context with no backend.

    A real `ImGuiContext`: the event queue, hover resolution, the sidebar, the
    child window and its scrolling are ImGui's own. Not real: there is no
    platform backend, so the clipboard is ImGui's in-memory one, the time step
    is a constant sixtieth of a second, and nothing rasterises a glyph.

    **A context of its own, made here and destroyed here**, with the app's own
    font callback run in it (`imscribe.ui.app._load_fonts_for_run`): the
    library's fonts go into this context's atlas and the library is unloaded
    before the context is destroyed, as `run` does through hello_imgui. The
    context that was current is put back. Without the library the callback
    loads the app's one UI font through hello_imgui, which has no runner here;
    that is skipped, the page draws its one line, and the outcome carries
    `NotDrawing`.
    """
    from imgui_bundle import imgui

    from imscribe import typesetter
    from imscribe.ui import app as imscribe_app

    before = imgui.get_current_context()
    own = imgui.create_context()
    imgui.set_current_context(own)
    seen = Seen()
    checks: list[Check] = []
    began = time.perf_counter()
    try:
        io = imgui.get_io()
        size = imgui.ImVec2(1100.0, 800.0)
        io.display_size = size
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
        if typesetter.module() is not None:
            imscribe_app._load_fonts_for_run()

        app = imscribe_app.App(source=source)
        driver = Driver(script(seen, imgui, checks, source=source, opening=opening))
        with watch(seen):
            while not driver.done:
                driver.before_frame(io, imgui)
                imgui.new_frame()
                try:
                    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
                    imgui.set_next_window_size(size)
                    imgui.begin("##imscribe-mouse-probe")
                    app.gui()
                    imgui.end()
                finally:
                    imgui.render()
    finally:
        typesetter.unload()
        imgui.destroy_context(own)
        if before is not None:
            imgui.set_current_context(before)
    return Outcome(
        "no window",
        tuple(checks),
        driver.error,
        driver.frames,
        time.perf_counter() - began,
        seen.renderer,
    )


def install(runner: Any, driver: Driver, request_exit: Callable[[], None]) -> None:
    """
    Chain the driver onto a runner's callbacks without losing the app's own.

    `pre_new_frame` is where the events go, so they are in the queue when
    `ImGui::NewFrame` drains it. `after_swap` asks the app to exit once the
    script has finished, which is one frame after its last `yield` -- so the
    last frame presented, and the one `--shot` grabs, shows the final selection.

    Idling is switched off for the reason `scripts/shot.py` gives: with no real
    input arriving hello_imgui drops to its idle rate, and a double click then
    takes longer than ImGui's double-click time and is two single clicks.
    """
    from imgui_bundle import imgui

    user_before = runner.callbacks.pre_new_frame
    user_after = runner.callbacks.after_swap

    def pre_new_frame() -> None:
        if user_before is not None:
            user_before()
        driver.before_frame(imgui.get_io(), imgui)

    def after_swap() -> None:
        if user_after is not None:
            user_after()
        if driver.done:
            request_exit()

    runner.callbacks.pre_new_frame = pre_new_frame
    runner.callbacks.after_swap = after_swap
    runner.fps_idling.enable_idling = False


def run_in_a_window(
    source: str | None, *, opening: str = OPENING, shot: Path | None = None
) -> Outcome:
    """
    The script, in the real app, in a real window on `$DISPLAY`.

    `immapp.run` is replaced for the length of the call by a wrapper that
    installs the driver and delegates to the real one, which is how
    `scripts/shot.py` gets in and for the same reason: every font, callback and
    draw call is then the app's own. The ini file goes to a temporary folder, so
    a geometry remembered from somebody's interactive session cannot move the
    window and the run leaves nothing behind.
    """
    from imgui_bundle import hello_imgui, imgui, immapp

    from imscribe.ui import app as imscribe_app

    text = source or imscribe_app.demo_text("sample.md") or imscribe_app.DEFAULT_MARKDOWN
    seen = Seen()
    checks: list[Check] = []
    driver = Driver(script(seen, imgui, checks, source=text, opening=opening))
    real_run = immapp.run

    def patched_run(runner: Any, *rest: Any) -> Any:
        runner.app_window_params.restore_previous_geometry = False
        install(
            runner,
            driver,
            lambda: setattr(hello_imgui.get_runner_params(), "app_shall_exit", True),
        )
        return real_run(runner, *rest)

    began = time.perf_counter()
    immapp.run = patched_run  # type: ignore[assignment]
    try:
        with watch(seen), tempfile.TemporaryDirectory(prefix="imscribe-mouse-probe-") as folder:
            imscribe_app.run(text, ini_folder=folder)
    finally:
        immapp.run = real_run
    seconds = time.perf_counter() - began

    if shot is not None:
        _write_shot(shot)
    return Outcome("window", tuple(checks), driver.error, driver.frames, seconds, seen.renderer)


def _write_shot(out: Path) -> None:
    """
    Write the exited app's last frame, with `scripts/shot.py`'s own grab.

    Loaded by path, because `scripts/` is not a package and must stay off
    `sys.path` (`tests/test_shot.py` says why). Its `_grab` is used rather than
    copied so there is one account of the buffer's orientation, not two.
    """
    spec = importlib.util.spec_from_file_location(
        "_shot_for_mouse_probe", ROOT / "scripts" / "shot.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ProbeError("scripts/shot.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    width, height = module._grab(out)
    print(f"wrote {out} ({width}x{height})")


# ----------------------------------------------------------------------
# A display where there is none


def xvfb_command(inner: Sequence[str], *, display: int = XVFB_DISPLAY_NUMBER) -> list[str]:
    """
    The `unshare` invocation that starts an Xvfb and runs `inner` against it.

    `scripts/shot.sh` documents each link and they are the same here -- a user
    and mount namespace, a tmpfs over `/tmp` for the server's lock file, TCP
    rather than a unix socket, Mesa's software rasteriser -- with one addition,
    `-nolisten unix`. In the sandbox this was written in `socket(AF_UNIX)` is
    refused with `EPERM`, so there is no unix socket to listen on or connect to
    and the display must be named with a host, `127.0.0.1:N`, which Xlib reads
    as TCP port `6000 + N`.

    The tmpfs shadows `$TMPDIR` along with the rest of `/tmp`, so `TMPDIR` is
    reset inside; the inner command's temporary ini folder lands there and
    vanishes with the namespace. Pure, so the shell it builds is testable.
    """
    shell = f"""
mount -t tmpfs tmpfs /tmp
mkdir -p /tmp/.X11-unix /tmp/cache
Xvfb :{display} -screen 0 1400x1000x24 -listen tcp -nolisten unix >/tmp/xvfb.log 2>&1 &
XVFB=$!
trap 'kill $XVFB 2>/dev/null || true' EXIT
export DISPLAY=127.0.0.1:{display} TMPDIR=/tmp
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
export XDG_CACHE_HOME=/tmp/cache XDG_CONFIG_HOME=/tmp/cache
STATUS=0
{shlex.join(inner)} || STATUS=$?
kill -0 $XVFB 2>/dev/null || {{ echo "Xvfb is not running:"; cat /tmp/xvfb.log; }}
exit $STATUS
"""
    return ["unshare", "-rm", "sh", "-e", "-c", shell]


def wait_for_tcp_display(display: str, *, timeout: float = 10.0) -> bool:
    """
    Whether a `host:N` display accepts a TCP connection within `timeout` seconds.

    Only for a display named with a host, which is what `--xvfb` sets; the
    server is started in the background a moment before this process and a
    fixed sleep would be either too long or, under load, too short. A display
    without a host (`:1`) is not probed and is reported reachable: guessing at
    unix sockets, abstract sockets and Wayland is the pre-flight
    `scripts/run_demo.py` argues against, and GLFW's own failure is caught by
    the caller instead.
    """
    host, _, rest = display.rpartition(":")
    if not host:
        return True
    try:
        port = 6000 + int(rest.split(".")[0])
    except ValueError:
        return True
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)


NO_LIBRARY = """\
There is nothing to play a mouse at: {reason}

The Document page draws its text through the imtypeset library and draws one
line without it. Build the pinned library and run with it:

  make typeset-lib
  IMTYPESET_LIBRARY=<the library it built, in build/imtypeset-bundle> \\
  IMTYPESET_PYTHON=build/imtypeset-bundle/pysnap python scripts/mouse_probe.py --xvfb

`make typeset-lib` ends by saying where it installed the pair; the library's
file name is the build's and differs by platform.
"""

NO_DISPLAY = """\
No window could be opened ({reason}).

  python scripts/mouse_probe.py --xvfb        start an Xvfb in a user namespace and use that
  python scripts/mouse_probe.py --no-window   a real ImGui context with no backend: lower fidelity
"""


def main(argv: list[str] | None = None) -> int:
    """
    Parse the arguments, run the probe one of three ways, print the report.
    """
    parser = argparse.ArgumentParser(description="Play a mouse into the imscribe demo.")
    parser.add_argument("--source", type=Path, default=None, help="a markdown file to display")
    parser.add_argument("--opening", default=OPENING, help="how the targeted paragraph begins")
    parser.add_argument(
        "--shot", type=Path, default=None, help="write the last frame here (window only)"
    )
    how = parser.add_mutually_exclusive_group()
    how.add_argument("--xvfb", action="store_true", help="start an Xvfb in a user namespace first")
    how.add_argument("--no-window", action="store_true", help="a bare ImGui context, no backend")
    args = parser.parse_args(argv)

    if args.xvfb:
        missing = [tool for tool in ("unshare", "Xvfb") if shutil.which(tool) is None]
        if missing:
            print(f"--xvfb needs {' and '.join(missing)} on PATH", file=sys.stderr)
            return 2
        inner = [sys.executable, str(Path(__file__).resolve()), "--opening", args.opening]
        if args.source is not None:
            inner += ["--source", str(args.source.resolve())]
        if args.shot is not None:
            inner += ["--shot", str(args.shot.resolve())]
        return subprocess.call(xvfb_command(inner), cwd=ROOT)

    text = args.source.read_text(encoding="utf-8") if args.source else None

    if args.no_window:
        from imscribe.ui import app as imscribe_app

        outcome = run_without_a_window(
            text or imscribe_app.demo_text("sample.md") or imscribe_app.DEFAULT_MARKDOWN,
            opening=args.opening,
        )
    else:
        display = os.environ.get("DISPLAY")
        if not display:
            print(NO_DISPLAY.format(reason="DISPLAY is not set"), file=sys.stderr)
            return 2
        if not wait_for_tcp_display(display):
            print(NO_DISPLAY.format(reason=f"nothing answers at {display}"), file=sys.stderr)
            return 2
        try:
            outcome = run_in_a_window(text, opening=args.opening, shot=args.shot)
        except RuntimeError as error:
            if "glfwInitSuccess" not in str(error):
                raise
            reason = f"DISPLAY={display} is set but GLFW could not connect to it"
            print(NO_DISPLAY.format(reason=reason), file=sys.stderr)
            return 2

    print(
        f"mouse probe, {outcome.mode}: {outcome.frames} frames in {outcome.seconds:.2f}s, "
        f"renderer {outcome.renderer or 'none'}"
    )
    print(report(outcome.checks))
    if outcome.error is not None:
        print(f"the probe stopped early: {type(outcome.error).__name__}: {outcome.error}")
    if isinstance(outcome.error, NotDrawing) and not os.environ.get("IMTYPESET_LIBRARY"):
        print(NO_LIBRARY.format(reason=outcome.error), file=sys.stderr)
        return 2
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

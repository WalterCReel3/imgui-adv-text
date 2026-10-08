#!/usr/bin/env python3
r"""
Play a mouse into the real demo and check what it selected and what it copied.

`advtext.ui.document_view` turns a pointer position into a range of the
document and a keypress into clipboard text. For most of this project's life
that path had run sixty times a second with `is_mouse_clicked` false and no
further, and `README.md` said so: *no mouse click has ever reached a real
frame*. This script is the instrument that retires that sentence, and it says
below exactly how far it retires it.

## What it does

It runs **the real app** -- `advtext.ui.app.run`, through the real
`immapp.run`, with the real fonts, sidebar, scrolling child window and GLFW
clipboard -- and before each frame posts input events to ImGui's own queue
(`io.add_mouse_pos_event`, `add_mouse_button_event`, `add_mouse_wheel_event`,
`add_key_event`). The positions are not guessed. `DocumentView._handle_mouse` is
wrapped for the length of the run so that the layout and the screen origin the
view itself used on the last frame can be read back; the wrapper calls the real
method and changes nothing. A glyph's screen position is then that origin plus
the glyph's own shipped coordinates, which is the arithmetic the view claims to
be doing in the other direction.

Eight gestures, each with an expectation built **without** calling
`SelectionModel.select_at`, `hit`, `word_at`, `line_at` or `text` -- those are
the code under test, and an expectation computed by them would be the view
agreeing with itself:

1. a drag over the first two words of a line, left to right;
2. the same drag right to left, which must select the same thing;
3. a drag from the first line of a paragraph to its third;
4. a double click on a word;
5. a triple click on a line;
6. Ctrl+C, read back from the clipboard, which is seeded with a sentinel first
   so that a copy that never happened cannot pass on stale contents;
7. a wheel scroll past a whole window height, then a drag on a line that was
   below the fold before it -- the check that the hit-test origin follows the
   scroll, which nothing headless reaches;
8. a drag that starts on a visible line and ends on a line below the bottom of
   the window, then Ctrl+C -- the claim `tests/test_document_view.py` exists to
   defend, that culling what is drawn does not cull what is copied.

Expected text is the characters of the shipped glyphs on the targeted lines,
joined by this file's own rule, and for the paragraph drag it is additionally
required to occur verbatim in the markdown source. Lines are found **by
content** (`find_line`) and a missing one is a loud failure, per
`.concerns/lead--visual-standard.md`: a target that silently lands somewhere
else is how a crop of whitespace got reviewed twice.

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
bare `imgui.create_context()`, the idiom `tests/test_imgui_draw.py`
established. It is what `tests/test_mouse_probe.py` runs, so the gesture script
itself is covered wherever the suite runs. It is lower fidelity in the ways one
would expect: no font atlas of ours (`draw` falls back to the bound face at the
right positions), ImGui's in-memory clipboard rather than the platform's, and a
fixed `delta_time`.

Exit status: 0 when every check passed, 1 when one did not, 2 when the probe
could not run at all (no display, no `unshare`).
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

from advtext.selection import Fragment, Selection, SelectionModel  # noqa: E402
from advtext.shipout import SetGlue  # noqa: E402
from advtext.units import px_from_sp, sp_from_px  # noqa: E402

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
class Seen:
    """
    The last frame's `DocumentView`, its layout, and where it put the document.

    Filled in by `watch`. `origin` is the screen position of the document's own
    (0, 0) -- the text block's corner -- and `window_top` / `window_height` are
    the scrolling child window's rectangle, so a line can be asked whether it is
    on screen.
    """

    view: Any = None
    layout: Any = None
    origin: tuple[float, float] = (0.0, 0.0)
    window_top: float = 0.0
    window_height: float = 0.0
    frames: int = 0

    @property
    def model(self) -> SelectionModel:
        if self.layout is None:
            raise ProbeError(
                "the Document page has not drawn a frame, so there is no layout to aim at"
            )
        model: SelectionModel = self.layout.model
        return model

    @property
    def px_per_inch(self) -> float:
        value: float = self.view.px_per_inch
        return value

    def screen_y(self, y_sp: int) -> float:
        """Where a document y, in scaled points, is on screen right now."""
        return self.origin[1] + px_from_sp(y_sp, self.px_per_inch)

    def on_screen(self, fragment: Fragment, *, inset_px: float = 4.0) -> bool:
        """Whether a line's whole band is inside the child window."""
        top = self.screen_y(fragment.top)
        bottom = self.screen_y(fragment.bottom)
        return (
            top >= self.window_top + inset_px
            and bottom <= self.window_top + self.window_height - inset_px
        )


@contextlib.contextmanager
def watch(seen: Seen) -> Iterator[None]:
    """
    Record every `DocumentView._handle_mouse` call into `seen`, changing nothing.

    The wrapper calls the real method with the real arguments; it exists because
    the origin the view hit-tests against is computed inside `draw` from ImGui's
    cursor and is not otherwise observable. Reading it here rather than
    re-deriving it is the point: a probe that recomputed the origin would aim at
    where it thinks the text is, and the defect worth finding is the view and
    the pixels disagreeing about that.

    Patched on the class and restored on exit, including when the run raises.
    """
    from imgui_bundle import imgui

    from advtext.ui.document_view import DocumentView

    real = DocumentView._handle_mouse

    def spy(self: Any, layout: Any, origin: Any) -> None:
        seen.view = self
        seen.layout = layout
        seen.origin = (float(origin.x), float(origin.y))
        seen.window_top = float(imgui.get_window_pos().y)
        seen.window_height = float(imgui.get_window_size().y)
        seen.frames += 1
        real(self, layout, origin)

    DocumentView._handle_mouse = spy  # type: ignore[method-assign]
    try:
        yield
    finally:
        DocumentView._handle_mouse = real  # type: ignore[method-assign]


# ----------------------------------------------------------------------
# Aiming. Pure: fragments in, pixels out.


def line_text(fragment: Fragment) -> str:
    """
    The characters on one visual line, an interword glue as one space.

    Written here rather than borrowed from `advtext.selection._render`, which is
    part of what a copy is checked against.
    """
    return "".join(
        " " if isinstance(item, SetGlue) else chr(item.codepoint) for item in fragment.items
    )


def line_copy(fragment: Fragment) -> str:
    """
    What copying one whole visual line should put on the clipboard.

    `line_text` with the fill left out: glue of no natural width is the
    `\\rightskip` or `\\parfillskip` at the end of the line, which takes a
    reading-order index and is not a space anybody typed. `line_text` keeps it,
    because the probe aims by item offset and needs one character an item;
    since 2026-10-07 a copy does not (`advtext.selection.FragmentQueries.text`).
    Restated here from the shipped commands rather than imported, for the
    reason `line_text` is.
    """
    return "".join(
        ("" if item.natural == 0 else " ") if isinstance(item, SetGlue) else chr(item.codepoint)
        for item in fragment.items
    )


def find_line(model: SelectionModel, opening: str) -> int:
    """
    The position in `model.fragments` of the first line that starts with `opening`.

    By content, and loud when absent. The message quotes the lines that *are*
    there, because the usual cause is a different `--source` and the fix is to
    read what it says.
    """
    for at, fragment in enumerate(model.fragments):
        if line_text(fragment).startswith(opening):
            return at
    present = [line_text(fragment)[:40] for fragment in model.fragments[:6]]
    raise ProbeError(f"no line starts with {opening!r}; the first lines are {present!r}")


def alone_in_its_band(model: SelectionModel, at: int) -> bool:
    """
    Whether no other line with anything on it shares this line's vertical band.

    Where two lines sit side by side, "the line at this y" is a question with
    more than one answer, and the probe aims only where it has one so that no
    expectation depends on which of them the view would pick. Measured on
    2026-10-06: a table row ships as *one* line today, so nothing in
    `demo/sample.md` is side by side and this rejects nothing there. It is here
    for the shapes that are -- a stacked-limits operator is a line inside a
    line -- and for table cells once they wrap into lines of their own.
    """
    line = model.fragments[at]
    for other_at, other in enumerate(model.fragments):
        if other_at == at or not other.items:
            continue
        if other.top < line.bottom and line.top < other.bottom:
            return False
    return True


def copies_as_itself(model: SelectionModel, fragment: Fragment) -> bool:
    """
    Whether copying this whole line gives its own characters and nothing else.

    True of a line of a paragraph. False of a table row, which ships as one
    line and copies with a tab between its cells, and of anything else whose
    copy carries a separator the glyphs do not. Gestures 7 and 8 build their
    expected text from the line's glyphs, so they aim only at lines for which
    that is what a copy returns.

    **Found by a failure, 2026-10-07.** Those two gestures pick "the first line
    below the fold", so which line they get depends on the height of the
    window. At the 1100x800 the app opened at, it was a line of prose every
    time and nothing here said it had to be. When the tab bar became a sidebar
    the page body grew by the tab bar's 36 px, the first line below the fold
    became the header row of `demo/sample.md`'s table, and the probe reported
    `'Module\tOwns'` against an expected `'Module Owns'` -- a correct copy,
    and a wrong expectation.
    """
    copy = getattr(model, "copy_text", model.text)
    return bool(copy(Selection(fragment.start, fragment.end)) == line_copy(fragment))


def cell_point(seen: Seen, fragment: Fragment, offset: int, fraction: float) -> Move:
    """
    The screen position `fraction` of the way across item `offset` of a line.

    A quarter of the way in is left of the item's midpoint, so the caret lands
    before it; three quarters is right of it, so the caret lands after. The
    probe uses only those two and the centre, never an edge, so that no
    expectation depends on how a tie at a boundary is resolved.
    """
    left = fragment.edges[offset]
    right = fragment.edges[offset + 1]
    x_px = px_from_sp(left, seen.px_per_inch) + fraction * px_from_sp(
        right - left, seen.px_per_inch
    )
    y_sp = (fragment.top + fragment.bottom) // 2
    return Move(seen.origin[0] + x_px, seen.screen_y(y_sp))


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


def _drag_first_words(seen: Seen, at: int, label: str, checks: list[Check]) -> Frames:
    """Drag over the first two words of line `at`, forwards, and check it."""
    line = seen.model.fragments[at]
    text = line_text(line)
    count = first_words_end(text)
    yield from _play(
        cell_point(seen, line, 0, 0.25),
        Button(True),
        cell_point(seen, line, count - 1, 0.75),
        Button(False),
    )
    checks.append(
        Check(
            f"{label}: range",
            Selection(line.indices[0], line.indices[count - 1] + 1),
            seen.view.selection,
        )
    )
    checks.append(Check(f"{label}: text", text[:count], seen.view.selected_text()))


def script(
    seen: Seen,
    imgui: Any,
    checks: list[Check],
    *,
    source: str,
    opening: str = OPENING,
) -> Frames:
    """
    The eight gestures in the module docstring, in order.

    `source` is the markdown the app was given, used once: the paragraph drag's
    expected text must occur in it verbatim, which is the one expectation here
    that does not come from the layout at all.
    """
    # Settling. The first frame sizes the child window and the second gives it
    # its scrollbar, which narrows the content region; the layout is not the one
    # the rest of the run will use until then. Longer than that needs, because
    # a context reused from an earlier run may hold a recent click, and a press
    # near it inside ImGui's 0.3 s double-click time would count as its second.
    for _ in range(SETTLE_FRAMES):
        yield []
    if seen.frames == 0:
        raise ProbeError("the Document page never drew: DocumentView._handle_mouse was not called")

    model = seen.model
    at = find_line(model, opening)
    if at + 2 >= len(model.fragments) or not all(
        model.fragments[at + step].items and alone_in_its_band(model, at + step)
        for step in range(3)
    ):
        raise ProbeError(f"the paragraph starting {opening!r} must run to at least three lines")
    first, second, third = (model.fragments[at + step] for step in range(3))
    if not all(seen.on_screen(line) for line in (first, second, third)):
        raise ProbeError(f"the paragraph starting {opening!r} is not on screen at the start")

    # 1. A drag, left to right.
    yield from _drag_first_words(seen, at, "1 drag over two words, left to right", checks)

    # 2. The same drag backwards. The range is normalised, so it must be equal,
    #    and a hand-rolled selection that assumes start <= end selects nothing.
    text = line_text(first)
    count = first_words_end(text)
    yield from _play(
        cell_point(seen, first, count - 1, 0.75),
        Button(True),
        cell_point(seen, first, 0, 0.25),
        Button(False),
    )
    checks.append(
        Check(
            "2 the same drag, right to left: range",
            Selection(first.indices[0], first.indices[count - 1] + 1),
            seen.view.selection,
        )
    )
    checks.append(
        Check("2 the same drag, right to left: text", text[:count], seen.view.selected_text())
    )

    # 3. Across lines: from the second word of the first line to the end of the
    #    first word of the third. A wrap copies as one space.
    start = first_words_end(text, 1) + 1
    third_text = line_text(third)
    stop = first_words_end(third_text, 1)
    expected = " ".join([text[start:].rstrip(), line_text(second).strip(), third_text[:stop]])
    checks.append(
        Check(
            "3 the expected paragraph text occurs verbatim in the markdown source",
            True,
            squeeze(expected) in squeeze(source),
        )
    )
    yield from _play(
        cell_point(seen, first, start, 0.25),
        Button(True),
        cell_point(seen, third, stop - 1, 0.75),
        Button(False),
    )
    checks.append(
        Check(
            "3 drag across three lines: range",
            Selection(first.indices[start], third.indices[stop - 1] + 1),
            seen.view.selection,
        )
    )
    checks.append(Check("3 drag across three lines: text", expected, seen.view.selected_text()))

    # 4. A double click, on the second word of three letters or more on the
    #    second line. `\w` is the selection module's own definition of a word
    #    character -- alphanumerics and the underscore -- restated, not imported.
    second_text = line_text(second)
    words = [match for match in re.finditer(r"\w+", second_text) if len(match.group()) >= 3]
    if len(words) < 2:
        raise ProbeError(f"the line {second_text!r} needs two words of three letters or more")
    word = words[1]
    on_word = cell_point(seen, second, (word.start() + word.end() - 1) // 2, 0.5)
    yield from _play(on_word, Button(True), Button(False), Button(True), Button(False))
    checks.append(
        Check(
            "4 double click: range",
            Selection(second.indices[word.start()], second.indices[word.end() - 1] + 1),
            seen.view.selection,
        )
    )
    checks.append(Check("4 double click: text", word.group(), seen.view.selected_text()))

    # 5. A triple click, on the third line. A line away from the double click
    #    above, which is further than ImGui's double-click distance, so this is
    #    a new click sequence and not clicks three to five of the last one.
    on_line = cell_point(seen, third, len(third.items) // 2, 0.5)
    yield from _play(
        on_line,
        Button(True),
        Button(False),
        Button(True),
        Button(False),
        Button(True),
        Button(False),
    )
    checks.append(
        Check("5 triple click: range", Selection(third.start, third.end), seen.view.selection)
    )
    checks.append(Check("5 triple click: text", line_copy(third), seen.view.selected_text()))

    # 6. Copy it.
    yield from _copy(imgui)
    checks.append(
        Check(
            "6 ctrl+C: the clipboard holds the line", line_copy(third), imgui.get_clipboard_text()
        )
    )

    # 7. Scroll by more than a window, then drag on a line that was below the
    #    fold. The pointer is parked over the document first: the wheel goes to
    #    the window under it.
    origin_before = seen.origin[1]
    height = seen.window_height
    fold = sp_from_px(seen.window_top + height - origin_before, seen.px_per_inch)
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

    model = seen.model
    below = [
        index
        for index, line in enumerate(model.fragments)
        if line.top > fold
        and seen.on_screen(line)
        and len(re.findall(r"\S+", line_text(line))) >= 3
        and alone_in_its_band(model, index)
        and copies_as_itself(model, line)
    ]
    if not below:
        raise ProbeError("after scrolling, no line that began below the fold is on screen")
    yield from _drag_first_words(
        seen, below[0], "7 drag on a line that was below the fold before the scroll", checks
    )

    # 8. Press on that line and release on one beneath the window's bottom edge.
    #    Nothing auto-scrolls; the line it ends on is not drawn. It must still be
    #    selected and it must still be copied.
    #
    #    The press is on the line's *second* word. Gesture 7 pressed on its
    #    first a few frames ago, and a second press at the same point inside
    #    the double-click time is a double click: the drag would then run at
    #    word granularity and, ending as it does on a word boundary, select
    #    exactly what a character drag selects. It did, in the first version of
    #    this script, and passed for the wrong reason.
    press = model.fragments[below[0]]
    press_text = line_text(press)
    begin = first_words_end(press_text, 1) + 1
    bottom = seen.window_top + seen.window_height
    beyond = [
        index
        for index, line in enumerate(model.fragments)
        if seen.screen_y(line.top) > bottom + 100.0
        and len(line.items) >= 4
        and alone_in_its_band(model, index)
        and copies_as_itself(model, line)
    ]
    if not beyond:
        raise ProbeError(
            "no line lies more than 100 px below the window; the document is too short"
        )
    release = model.fragments[beyond[0]]
    release_text = line_text(release)
    stop = first_words_end(release_text, 1)
    yield from _play(
        cell_point(seen, press, begin, 0.25),
        Button(True),
        cell_point(seen, release, stop - 1, 0.75),
        Button(False),
    )
    wanted = Selection(press.indices[begin], release.indices[stop - 1] + 1)
    checks.append(Check("8 drag past the bottom of the window: range", wanted, seen.view.selection))
    selected = seen.view.selected_text()
    checks.append(
        Check(
            "8 drag past the bottom of the window: text runs from the pressed line to the unseen",
            (True, True),
            (
                selected.startswith(press_text[begin:].rstrip()),
                # White space removed from both sides: a line that opens
                # with a list marker reads ` 1.markdown` item by item (fill,
                # marker, a kern with no index, text) and `1. markdown` in a
                # copy, which knows the marker from the text. The characters
                # and their order are what this checks.
                "".join(selected.split()).endswith("".join(release_text[:stop].split())),
            ),
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

    @property
    def passed(self) -> bool:
        return self.error is None and bool(self.checks) and all(check.ok for check in self.checks)


def run_without_a_window(source: str, *, opening: str = OPENING) -> Outcome:
    """
    The script, through `App.gui()`, in frames of a context with no backend.

    A real `ImGuiContext`: the event queue, hover resolution, the sidebar, the
    child window and its scrolling are ImGui's own. Not real: there is no
    platform backend, so the clipboard is ImGui's in-memory one, the time step
    is a constant sixtieth of a second, and no font of ours is in the atlas.

    The context is created if there is none and otherwise reused, as every
    headless test in this tree does; the pointer is left released and off the
    window so a later test in the same process inherits nothing.
    """
    from imgui_bundle import imgui

    from advtext.ui.app import App

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    size = imgui.ImVec2(1100.0, 800.0)
    io.display_size = size
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    # A window name no earlier run in this context used. The child window's
    # scroll position is ImGui's state, keyed by the window's id, and gesture 7
    # leaves it scrolled: a second run under the same name would start a screen
    # and a half down and find its first paragraph off screen.
    name = f"##advtext-mouse-probe-{imgui.get_frame_count()}"
    app = App(source=source)
    seen = Seen()
    checks: list[Check] = []
    driver = Driver(script(seen, imgui, checks, source=source, opening=opening))
    began = time.perf_counter()
    with watch(seen):
        while not driver.done:
            driver.before_frame(io, imgui)
            imgui.new_frame()
            try:
                imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
                imgui.set_next_window_size(size)
                imgui.begin(name)
                app.gui()
                imgui.end()
            finally:
                imgui.render()
        # Leave nothing held for whoever uses the context next.
        io.add_mouse_button_event(0, False)
        io.add_mouse_pos_event(-1.0e6, -1.0e6)
        imgui.new_frame()
        imgui.render()
    return Outcome(
        "no window", tuple(checks), driver.error, driver.frames, time.perf_counter() - began
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

    from advtext.ui import app as advtext_app

    text = source or advtext_app.demo_text("sample.md") or advtext_app.DEFAULT_MARKDOWN
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
        with watch(seen), tempfile.TemporaryDirectory(prefix="advtext-mouse-probe-") as folder:
            advtext_app.run(text, ini_folder=folder)
    finally:
        immapp.run = real_run
    seconds = time.perf_counter() - began

    if shot is not None:
        _write_shot(shot)
    return Outcome("window", tuple(checks), driver.error, driver.frames, seconds)


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


NO_DISPLAY = """\
No window could be opened ({reason}).

  python scripts/mouse_probe.py --xvfb        start an Xvfb in a user namespace and use that
  python scripts/mouse_probe.py --no-window   a real ImGui context with no backend: lower fidelity
"""


def main(argv: list[str] | None = None) -> int:
    """
    Parse the arguments, run the probe one of three ways, print the report.
    """
    parser = argparse.ArgumentParser(description="Play a mouse into the advtext demo.")
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
        from advtext.ui import app as advtext_app

        outcome = run_without_a_window(
            text or advtext_app.demo_text("sample.md") or advtext_app.DEFAULT_MARKDOWN,
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

    print(f"mouse probe, {outcome.mode}: {outcome.frames} frames in {outcome.seconds:.2f}s")
    print(report(outcome.checks))
    if outcome.error is not None:
        print(f"the probe stopped early: {type(outcome.error).__name__}: {outcome.error}")
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

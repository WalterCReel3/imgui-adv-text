#!/usr/bin/env python3
"""
Run the real demo for N frames, photograph the window, write a PNG, exit.

Exists so the UI can be looked at without a human in the loop. For an
immediate-mode UI that is the only way to check that a change did what it
claimed: nothing in `tests/` composites a pixel, so a tab that lays out
perfectly and draws in the background colour passes the whole suite.

**This runs the real app, not a copy of it.** `advtext.ui.app.run` builds the
`RunnerParams` and calls `immapp.run`; this script replaces `immapp.run` with a
wrapper that adjusts the window size, counts frames, and asks the app to exit,
then delegates to the real one. Every font, callback and draw call is the same
as `make run`. A screenshot script that rebuilt the params itself would
photograph a second app that merely resembles the first.

Two things were believed here for most of this project's life and were false in
the session this script was written in; both are load-bearing for it:

  * *"No display is reachable."*  In that session `DISPLAY=:1` was live,
    `AF_UNIX` connected to `/tmp/.X11-unix/X1`, and a real window opened in well
    under a second with no Xvfb. That is a fact about a session: in the
    sandboxed session of 2026-10-06 `DISPLAY=:1` was set and unreachable
    (`socket(AF_UNIX)` raised `PermissionError`) and this script died in GLFW
    until it was run on an Xvfb in a user namespace over TCP -- the shell
    `scripts/mouse_probe.py::xvfb_command` builds, with which one shot took
    about 6s. `scripts/shot.sh` (`make shot-headless`) is the older fallback of
    the same kind; it sleeps 22s per tab and photographs the X root window with
    `xwd`, and was not run in that session.
  * *"`hello_imgui.final_app_window_screenshot()` needs numpy and cv2, neither
    of which is installed."*  It needs numpy only, numpy is a dev dependency in
    `pyproject.toml`, and cv2 is not involved. Without numpy the call raises
    `TypeError: could not export nanobind::ndarray: No module named 'numpy'` --
    the same nanobind failure mode already documented at
    `advtext/ui/document_view.py:306-312` for `ImFont.find_glyph`, where a
    missing optional module turns a binding into a type error rather than an
    import error.

"final" in `final_app_window_screenshot` means *the last frame of the app that
has exited*, so the grab happens after `immapp.run` returns, not inside the
frame callback. That is the one structural difference from pptmstr's
`scripts/screenshot.py`, which grabs mid-frame with `glReadPixels`. PyOpenGL is
not installed here, and the hello_imgui call is the better path anyway: it needs
no GL binding and **its rows come out top-first already**. pptmstr reverses its
rows because GL's origin is bottom-left; doing the same here would ship every
specimen sheet upside down. See `_grab` for how that was checked.

PNG is written by hand via zlib rather than pulling in Pillow. The encoder is
twenty lines and this is a dev script, so a dependency here would be paid for by
everyone who installs the project. numpy is already paid for -- the screenshot
call will not return without it.

Usage:

    python scripts/shot.py --tab document --width 1400 --out artifacts/doc.png

`make shot` wraps it, `make shot-all` loops it over the pages, and both pass
`ARGS` through.

**`--list` is where `make shot-all` gets its list.** It prints one `--tab`
request per line -- every state every discovered page asks to be photographed
in (`advtext.ui.pages.PageSpec.shots`) -- and opens no window. The Makefile used
to carry that list and it went stale; this script used to refuse to carry one for
that reason. Neither carries one now: the pages are found by scanning
`advtext/ui/pages/`, and a module there that cannot be loaded makes `--list`
exit 1 naming it, so `make shot-all` stops instead of photographing what is
left and reporting nothing missing.

**A library that was asked for and is not drawing is a failed shot** (exit 3,
`NOT_DRAWN_STATUS`, no PNG, the reason on stderr; since 2026-10-11). With
`IMTYPESET_LIBRARY` unset the shot of each page's one line is taken as before
and `NO_LIBRARY` says what it is.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Run from anywhere without an install, matching scripts/run_demo.py. After
# `make bootstrap` this is redundant and harmless.
if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(ROOT))


NO_DISPLAY = """\
No DISPLAY is set, so there is nowhere to open a window.

  make shot-headless    start an Xvfb in a user namespace and photograph that
  make svg              render the same layouts with no GPU and no display

--force skips this check, for a machine that can open a window without DISPLAY
set. It is not a way to get a window without one: GLFW aborts in about half a
second with IM_ASSERT( glfwInitSuccess ).
"""


NO_LIBRARY = """\
IMTYPESET_LIBRARY is not set, so no page of the demo will draw its text: every
page sets its text through the imtypeset library and shows one line without it.

  make typeset-lib          build the pinned library (once)
  make shot TYPESET=1       the same command, with it
"""


def library_note(environ: Mapping[str, str]) -> str | None:
    """
    What to tell someone about to open the demo with no library asked for, or `None`.

    A note and not a refusal: the window still opens, each page says the
    same thing in one line, and that is a legitimate thing to want to look
    at. It is here because since 2026-10-11 no page falls back to advtext's
    own layout, so an unadorned `make shot` shows no text at all, and a
    batch of one-line pages should not be the first anyone hears of it.
    Only the variable is read: whether the library then loads is the app's to
    say, on each page.
    """
    return None if environ.get("IMTYPESET_LIBRARY") else NO_LIBRARY


NOT_DRAWN = """\
IMTYPESET_LIBRARY is set ({library}) and imtypeset was not drawing when the
window closed: {reason}

Every page then draws that sentence in one line in place of its text.
"""


NOT_DRAWN_STATUS = 3
"""
The exit status of a shot whose library was asked for and was not drawing.

Not 0, which is a photograph of the page; not 2, which is "no display"; not
1, which is what a page that raised ends with (`advtext.ui.app.PageError`).
"""


def not_drawn(environ: Mapping[str, str], reason: str) -> str | None:
    """
    What to fail with when the library was ASKED FOR and was not drawing at exit, or `None`.

    `reason` is `advtext.ui.app.not_drawing_at_exit()`: the sentence the
    pages were showing when the window closed, empty when the library drew.
    With `IMTYPESET_LIBRARY` unset this is `None` whatever the reason: a shot
    of the one line is then what was asked for, and `library_note` has said
    so. With it set and a reason, the shot is refused: until 2026-10-11 a
    library that was refused at import, lost its fonts or failed in the
    middle of the run still ended in a PNG and exit 0, a photograph of a
    sentence under a filename that names a page.
    """
    library = environ.get("IMTYPESET_LIBRARY")
    if not library or not reason:
        return None
    return NOT_DRAWN.format(library=library, reason=reason)


# ----------------------------------------------------------------------
# The PNG encoder. Pure, and tested without a display.


def encode_png(width: int, height: int, rgb_rows: list[bytes]) -> bytes:
    """
    Minimal truecolour 8-bit PNG, filter type 0 on every row.

    `rgb_rows` is top row first, three bytes per pixel, which is PNG's own
    order -- the caller is responsible for having got the orientation right,
    because nothing downstream can tell an upside-down photograph from a right
    way up one.
    """
    if len(rgb_rows) != height:
        raise ValueError(f"expected {height} rows, got {len(rgb_rows)}")
    if any(len(row) != width * 3 for row in rgb_rows):
        raise ValueError(f"every row must be {width * 3} bytes for a width of {width}")

    raw = b"".join(b"\x00" + row for row in rgb_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def write_png(path: Path, width: int, height: int, rgb_rows: list[bytes]) -> None:
    """Encode and write, creating the output directory if it is absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(width, height, rgb_rows))


# ----------------------------------------------------------------------
# The runner patch. Pure in the sense that matters: it touches only the object
# handed to it, so a stub drives it in a test with no display.


def install_frame_limit(runner: Any, frames: int, request_exit: Callable[[], None]) -> None:
    """
    Make `runner` exit after `frames` frames, without losing its own callback.

    The app may already have an `after_swap` -- today it does not, but a
    screenshot harness that silently dropped one would be a trap for whoever
    adds the first. So the existing callback is called first and this one
    chains onto it.

    `request_exit` fires on exactly the `frames`-th frame rather than on every
    frame from there on. `app_shall_exit` is a latch and re-setting it is
    harmless, but "called once, at frame N" is a claim a test can falsify and
    "called at least once, some time after N" is not.

    Idling is switched off for the same reason pptmstr's screenshot script
    switches it off (`scripts/screenshot.py:77-79`): hello_imgui drops to
    `fps_idle` when no input arrives, a screenshot run has no operator to wake
    it, and the frame count would then take wall-clock time proportional to the
    idle rate.
    """
    user_after = runner.callbacks.after_swap
    seen = {"n": 0}

    def after_swap() -> None:
        if user_after is not None:
            user_after()
        seen["n"] += 1
        if seen["n"] == frames:
            request_exit()

    runner.callbacks.after_swap = after_swap
    runner.fps_idling.enable_idling = False


def apply_window_size(runner: Any, width: int, height: int) -> None:
    """
    Force the window to the requested size, overriding any remembered geometry.

    `restore_previous_geometry` is cleared as well as the size being set.
    `advtext.ui.app.run` points `ini_folder_type` at the app's user-config
    folder, so a previous interactive run really can have left a geometry there;
    without this a shot asked for at 1400px would silently come back at whatever
    width the last human happened to leave the window, and column layouts are
    shot at more than one width precisely to compare them.
    """
    runner.app_window_params.window_geometry.size = [width, height]
    runner.app_window_params.restore_previous_geometry = False


def size_warning(requested: tuple[int, int], captured: tuple[int, int], scale: float) -> str | None:
    """
    Complain when the photograph is not the size that was asked for, or `None`.

    **This fires in practice and it matters.** The window manager clamps to the
    monitor: on this machine's 1920x1080 display, `--width 2400` and `--width
    3000` both come back 1920 wide, silently. The whole point of the width flag
    is comparing one layout at two measures, so two "different" widths that
    were both clamped to the same one produce two identical images and the
    reader concludes the layout does not reflow. That is a wrong conclusion
    drawn from a correct engine, which is worse than a crash.

    A HiDPI framebuffer is the innocent explanation for the same mismatch --
    the buffer is the window size times `scale` -- so it is distinguished here
    rather than lumped in. Returning the message instead of printing it keeps
    this testable with no display.
    """
    if captured == (round(requested[0] * scale), round(requested[1] * scale)):
        return None
    if captured == requested:  # pragma: no cover - scale 1.0 takes the branch above
        return None
    detail = (
        f"framebuffer scale is {scale}, so {requested[0]}x{requested[1]} was expected "
        f"to capture as {round(requested[0] * scale)}x{round(requested[1] * scale)}"
        if scale != 1.0
        else "the window manager clamps to the monitor, so a width wider than the "
        "screen comes back as the screen's width"
    )
    return (
        f"warning: asked for {requested[0]}x{requested[1]} but captured "
        f"{captured[0]}x{captured[1]} -- {detail}. Two shots requested at "
        "different widths above that limit are the same image."
    )


# ----------------------------------------------------------------------


def _grab(out: Path) -> tuple[int, int]:
    """
    Read back the exited app's last frame and write it.

    The buffer is `(H, W, 3)` or `(H, W, 4)` uint8 with **row 0 at the top**,
    which is PNG's order, so unlike a `glReadPixels` grab it is not reversed
    here. That was checked rather than assumed: the first shot taken with this
    script was read as an image, and the tab bar was at the top of it with the
    document below. A row reversal is invisible to every assertion a test can
    cheaply make -- the image is still valid, still the right size, still not
    blank -- so it is checked by looking.

    Returns the pixel dimensions actually captured, which on a HiDPI display are
    the window size times `final_app_window_screenshot_framebuffer_scale()`
    rather than the window size.
    """
    from imgui_bundle import hello_imgui

    # Without numpy this raises TypeError, not ImportError: nanobind cannot
    # export its ndarray and reports that as a type error naming the missing
    # module. Same shape of failure as advtext/ui/document_view.py:306-312.
    try:
        buffer = hello_imgui.final_app_window_screenshot()
    except TypeError as error:
        if "numpy" not in str(error):
            raise
        raise SystemExit(
            "the screenshot needs numpy, which is not installed in this "
            f"interpreter ({sys.executable}).\n"
            "  pip install numpy      # or: make bootstrap, which installs .[dev]\n"
            f"nanobind reported it as a TypeError rather than an ImportError: {error}"
        ) from error

    import numpy as np

    array = np.ascontiguousarray(buffer)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise SystemExit(f"unexpected screenshot shape {array.shape!r}; wanted (H, W, 3|4)")
    height, width = int(array.shape[0]), int(array.shape[1])
    rgb = np.ascontiguousarray(array[:, :, :3])

    write_png(out, width, height, [rgb[y].tobytes() for y in range(height)])
    return width, height


def list_shots() -> int:
    """
    Print every `--tab` request `make shot-all` photographs; 1 if a page is broken.

    The requests come from `advtext.ui.pages.discover`, which is what the app's
    sidebar is drawn from, so the list cannot name a page the app lacks or lack
    one it has. Imports no ImGui and opens nothing.

    **A module that fails to load is an error here and not a shorter list.**
    Nothing is printed to stdout in that case, so a caller that captures the
    output and ignores the status gets an empty list rather than a plausible
    partial one.
    """
    from advtext.ui.pages import discover

    found = discover()
    if found.failures:
        print(
            "not every module under advtext/ui/pages/ could be loaded as a page, so the "
            "list would be short:",
            file=sys.stderr,
        )
        for failure in found.failures:
            print(f"  {failure.module}: {failure.reason}", file=sys.stderr)
        return 1
    for spec in found.shot_specs():
        print(spec)
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Parse the arguments, run the real app for N frames, write the PNG.
    """
    parser = argparse.ArgumentParser(description="Screenshot the advtext ImGui demo.")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "shot.png")
    parser.add_argument(
        "--tab",
        default=None,
        help=(
            "page to select on the first frame, by name, case-insensitively, "
            "with options after a colon (columns:3,debug). Passed straight "
            "through to advtext.ui.app.run, with no list of names here -- a "
            "copy of the list would go stale the first time a page was added. "
            "--list prints the requests make shot-all uses."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help=(
            "print every --tab request `make shot-all` photographs, one per "
            "line, and exit without opening a window. Exits 1 if a module "
            "under advtext/ui/pages/ could not be loaded as a page."
        ),
    )
    parser.add_argument("--source", type=Path, default=None, help="a markdown file to display")
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="window width in pixels; the app's own (advtext.ui.app.WINDOW_SIZE) if omitted",
    )
    parser.add_argument("--height", type=int, default=None, help="window height, likewise")
    parser.add_argument(
        "--frames",
        type=int,
        default=30,
        help=(
            "frames to run before grabbing. The font atlas bakes during the "
            "first frame and the document composes on the first draw, so a "
            "one-frame shot can catch a half-built view."
        ),
    )
    parser.add_argument("--force", action="store_true", help="run even with no DISPLAY set")
    args = parser.parse_args(argv)

    if args.frames < 1:
        parser.error("--frames must be at least 1")
    if args.list:
        return list_shots()
    if not os.environ.get("DISPLAY") and not args.force:
        print(NO_DISPLAY, file=sys.stderr)
        return 2

    note = library_note(os.environ)
    if note is not None:
        print(note, file=sys.stderr)

    from imgui_bundle import hello_imgui, immapp

    from advtext.ui import app as advtext_app

    # The app's own size when none is asked for, so an unadorned shot is a
    # photograph of what `make run` opens. That size is 1300 wide since the
    # sidebar replaced the tab bar; the body of a page is as wide as it was.
    width = args.width if args.width is not None else advtext_app.WINDOW_SIZE[0]
    height = args.height if args.height is not None else advtext_app.WINDOW_SIZE[1]

    real_run = immapp.run

    def patched_run(runner: Any, *rest: Any) -> Any:
        apply_window_size(runner, width, height)
        install_frame_limit(
            runner,
            args.frames,
            lambda: setattr(hello_imgui.get_runner_params(), "app_shall_exit", True),
        )
        return real_run(runner, *rest)

    immapp.run = patched_run  # type: ignore[assignment]
    try:
        text = args.source.read_text(encoding="utf-8") if args.source else None
        advtext_app.run(text, tab=args.tab)
    finally:
        # No `type: ignore` needed on the way back: `real_run` still carries
        # immapp.run's own overloaded type, and mypy calls the ignore redundant
        # here even though it is required on the assignment above.
        immapp.run = real_run

    failure = not_drawn(os.environ, advtext_app.not_drawing_at_exit())
    if failure is not None:
        print(failure + "No PNG was written.", file=sys.stderr)
        return NOT_DRAWN_STATUS

    captured = _grab(args.out)
    warning = size_warning(
        (width, height),
        captured,
        hello_imgui.final_app_window_screenshot_framebuffer_scale(),
    )
    if warning is not None:
        print(warning, file=sys.stderr)
    print(f"wrote {args.out} ({captured[0]}x{captured[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

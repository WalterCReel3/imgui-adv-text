#!/usr/bin/env python3
r"""
Launch the ImGui demo, and refuse to hang when there is nowhere to open a window.

**A display is reachable here and this script has been run.** An earlier version
of this docstring opened "this cannot run in the development sandbox" and closed
"**Never executed.** Nothing downstream of the guard has been run", on the
grounds that the host display was unreachable and Xvfb could not create its lock
file under `/tmp`. Both were re-measured and are false in this environment:
`DISPLAY=:1` is live, `AF_UNIX` connects to `/tmp/.X11-unix/X1`, and a real
window opens in about 0.4s with no Xvfb and no software rasteriser. The
`Makefile` header records the same correction at length.

**The guard is still the whole point of this script**, because a machine without
a display is a real machine and not a historical one. An ImGui window does not
fail cleanly there -- it can hang until killed, `timeout` then reports 143, and
143 tells a reader nothing. So this refuses without a `DISPLAY` and says what to
do instead, and `--force` is there for the person who knows better than it does.

Seeing the UI without sitting in front of a window:

    make shot                one PNG of one tab through the real app, ~2.3s
    make shot-headless       the same via an Xvfb in a user namespace, ~22s a tab
    make svg                 the layouts alone: no GPU, no X server, no window

Usage:

    python scripts/run_demo.py [MARKDOWN_FILE] [--tab SPEC] [--force]

With no file it shows `demo/sample.md`, falling back to
`advtext.ui.app.DEFAULT_MARKDOWN` outside a checkout, where `demo/` is genuinely
absent. `--tab` takes `advtext.ui.app.parse_tab_request`'s grammar, so
`--tab columns:3,debug` opens the Columns tab at three columns with the debug
overlay on -- there are five tabs now, and this argument used to accept three.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Run from anywhere without an install. `make bootstrap` does an editable
# install and makes this redundant, but the script predates the venv and the
# import it shims is three frames deep inside main(), so without it the failure
# is a bare ModuleNotFoundError long after the argument parsing has succeeded.
if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BLOCKED = """\
No DISPLAY is set, so there is nowhere to open a window.

What works with no display at all:
  make shot-headless   Xvfb in a user namespace, then photograph every tab
  make svg             render the same layouts to artifacts/, no GPU and no X

What to try once a display is reachable:
  make run
  make run ARGS="--source demo/sample.md"
  make run ARGS="--tab columns:3"
  make shot ARGS="--tab columns:3 --out artifacts/columns-3.png"
  python scripts/verify_advances.py   (measures the ImGui/fontTools disagreement)

--force skips this check. It is not a way to get a window without a display:
GLFW fails in about half a second with IM_ASSERT( glfwInitSuccess ). It is there
so a machine that can open a window without DISPLAY set -- Wayland, or a remote
runner that sets things up later -- is not refused by this script's guess.
"""


def main(argv: list[str] | None = None) -> int:
    """
    Parse the arguments, refuse to hang, and otherwise open the window.
    """
    parser = argparse.ArgumentParser(description="Run the advtext ImGui demo.")
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="a markdown file to display; omit for demo/sample.md",
    )
    # The same file, spelled as a flag. Not decoration: `BLOCKED` above and the
    # `run` recipe in the Makefile both advertise
    # `make run ARGS="--source demo/sample.md"`, and until now that failed with
    # `unrecognized arguments: --source`. `scripts/shot.py` spells it this way,
    # so the two scripts now take the same flag for the same thing.
    #
    # A separate `dest` rather than aliasing onto the positional's, which looks
    # like it would work and does not: with both actions writing `source`, the
    # optional nargs="?" positional still fires and writes its own `None` over
    # the flag's value, so `--source x` parses to `source=None`. Measured, not
    # assumed -- see the test of exactly this in tests/test_run_demo.py.
    parser.add_argument(
        "--source",
        dest="source_flag",
        type=Path,
        default=None,
        metavar="MARKDOWN_FILE",
        help="the same thing as the positional argument, spelled as a flag",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="try to open the window even with no DISPLAY set",
    )
    # No list of tab names here. This argument carried
    # `choices=("document", "formula", "blocks")` until the demo grew Columns
    # and Specimen tabs, at which point `make run ARGS="--tab columns"` was
    # refused outright -- the two tabs most worth looking at were the two it
    # could not reach, and the colon grammar was rejected by argparse before it
    # ever got to the parser that understands it. `scripts/shot.py` declines to
    # keep a copy of the list for the same reason: "a copy of the tab list would
    # go stale the first time a tab was added". It did.
    parser.add_argument(
        "--tab",
        default=None,
        metavar="SPEC",
        help=(
            "tab to open on the first frame, in advtext.ui.app.parse_tab_request's "
            "grammar NAME[:OPTION,...] -- for instance 'document', 'columns:3' or "
            "'columns:3,debug'. Names are matched case-insensitively"
        ),
    )
    args = parser.parse_args(argv)

    if args.source is not None and args.source_flag is not None:
        parser.error("give the markdown file once, as a positional or as --source, not both")
    source: Path | None = args.source_flag if args.source_flag is not None else args.source

    # The DISPLAY guard runs before anything is imported from `advtext`, and the
    # ordering is deliberate rather than incidental: importing `advtext.ui.app`
    # costs about 0.13s, the refusal path is measured at 0.03s in `README.md`
    # and `docs/status.md`, and a guard whose job is to be faster and clearer
    # than a hang should not pay a package import to say "there is no display".
    # The cost is that a bad `--tab` behind an unset DISPLAY reports the display
    # first; the display is the larger fact of the two.
    if not os.environ.get("DISPLAY") and not args.force:
        print(BLOCKED, file=sys.stderr)
        return 2

    from advtext.ui.app import parse_tab_request, run

    # `App.__post_init__` parses this too, so the window would not open on a bad
    # spec either way -- but it would raise a `ValueError` traceback from three
    # frames down. Parsing it here, where the result is thrown away, turns that
    # into the exit-2-and-a-sentence every other refusal in this script gives.
    try:
        parse_tab_request(args.tab)
    except ValueError as error:
        print(f"run_demo.py: error: {error}", file=sys.stderr)
        return 2

    text = source.read_text(encoding="utf-8") if source else None
    try:
        run(text, tab=args.tab)
    except RuntimeError as error:
        # hello_imgui reports a failed `glfwInit` as an `IM_ASSERT` naming a C++
        # source line, which says nothing a caller can act on. The interesting
        # detail is on the line *above* it, which GLFW writes straight to stderr
        # and is gone by the time this runs. Translated here rather than
        # pre-flighted: probing the display first would have to guess at unix
        # sockets, abstract sockets, TCP displays and Wayland, and would refuse
        # to start on a machine that works. Failing and explaining is honest.
        if "glfwInitSuccess" not in str(error):
            raise
        print(_no_window(os.environ.get("DISPLAY")), file=sys.stderr)
        return 2
    return 0


def _no_window(display: str | None) -> str:
    """
    What to say when GLFW could not initialise, given what DISPLAY claimed.

    Cause 3 used to read "Install xvfb, then uncomment the XVFB_RUN block at the
    top of the Makefile." There is no such block: the Makefile's display
    handling has been rewritten twice since, and `make shot-headless` -- which
    runs `scripts/shot.sh`, an Xvfb inside a user namespace -- is what replaced
    it. The instruction pointed at nothing, which is worse than no instruction,
    because a reader who goes looking assumes they are reading the wrong file.

    Cause 1's `AF_UNIX` probe is *not* stale and was checked separately rather
    than assumed to fall with the Makefile block. It does not fire here -- unix
    sockets work in this sandbox and `DISPLAY=:1` is reached over one -- but it
    is still the diagnostic that separates a blocked socket from an absent
    server on the machines where it does.
    """
    where = f"DISPLAY={display}" if display else "no DISPLAY set"
    return f"""\
GLFW could not initialise, so no window can be opened ({where}).

The layout engine is unaffected -- it needs no GPU and no display:
  make svg     render the same document and formula to artifacts/

Three things that cause this, in the order worth checking:

1. A sandbox or container that blocks the X socket. The give-away is that
   creating a unix socket fails outright rather than the connection being
   refused:
       python3 -c "import socket; socket.socket(socket.AF_UNIX)"
   If that raises PermissionError, nothing on this machine can reach any X
   server and DISPLAY is a red herring.

2. DISPLAY naming a server that is not running, or one this user may not
   connect to. Check with `xdpyinfo -display "$DISPLAY"`, and note that
   XAUTHORITY must be readable too.

3. A headless machine with no X server at all. Nothing here needs fixing on
   such a machine -- photograph the demo instead of opening it:
       make shot-headless   install xvfb, then this runs one inside a user
                            namespace and grabs every tab (~22s a tab)
       make svg             the layouts alone, with no X server involved
"""


if __name__ == "__main__":
    raise SystemExit(main())

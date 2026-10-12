"""
Shared fixtures. There are two, and a guard, and each earns its place.

**`bundled_fonts`.** Every metrics test needs the directory imgui-bundle ships
its fonts in. That path is long, environment-derived, and wrong to write down:
it lives inside whichever site-packages the interpreter happens to be. (When
this was written the project ran on an interpreter borrowed from a sibling
project's virtualenv under another directory; it now runs on its own `./.venv`
and the argument is unchanged -- a test that hard-codes the path encodes one
machine's layout into the suite.) So the fixture resolves the directory the way
production code must: import `imgui_bundle` and walk from its `__file__`. That
also makes the fixture a standing check that the two agree -- if
`imscribe.fontlib` ever resolves fonts some other way, the tests stop exercising
the path production uses.

Skipping rather than failing when the directory is absent is deliberate. A
missing font directory is a statement about the environment, not about the code
under test, and a red suite that means "wrong machine" trains people to ignore
red suites.

**`window`.** Three tests photograph the real app in a real window
(`tests/test_shot.py`, two in `tests/test_visual_diff.py`). They used to be
gated on `DISPLAY` being *set* and went red wherever it was set and
unreachable, which is every sandboxed session this tree has been built in:
`DISPLAY=:1` names a unix socket and `socket(AF_UNIX)` is refused there. They
were red at the start of the adoption session for that reason and no other. The
fixture decides where a window can open by **asking**, in this order:

1. the session's own `DISPLAY` accepts a connection: run on it, unchanged;
2. else `Xvfb` is installed and `unshare -rm` can make a user namespace: run on
   an Xvfb over TCP inside one, which is the recipe
   `scripts/mouse_probe.py::xvfb_command` builds and
   `tests/test_mouse_probe.py` / `tests/test_examples.py` already use;
3. else skip, naming which of the three probes failed.

That reverses a position `tests/test_shot.py` used to argue -- that a
set-but-broken `DISPLAY` should go red and not be pre-flighted. The argument
was that a pre-flight means guessing at transports. The probe here guesses at
two (the unix socket by path and by abstract name, and TCP) and a wrong "no"
costs nothing but a slower window: the test still runs, on Xvfb. A wrong "yes"
goes red in GLFW exactly as before.

Not here, deliberately: an in-process ImGui *window* fixture. Nothing in this
suite opens a window in the test process -- see `docs/decisions.md`; the
`window` fixture runs a subprocess.

**The frame guard (`_no_frame_left_open`, autouse).** Some tests do run Dear
ImGui frames in the pytest process, with no window: a context made by a
module's own fixture, `new_frame`, a `begin`, the code under test, `end`,
`render`. The context is process-wide. A test that raises between `begin` and
`end` leaves it mid-frame, and then EVERY later test that starts a frame fails
in `new_frame` ("Forgot to call Render() or EndFrame() at the end of the
previous frame?"), in files that have nothing to do with the one that broke.
Three builders met that cascade in phase A of tranche 5 (one stale test, 134
reds: `.concerns/T5-FB-C--builder--result.md`). After each test the guard
looks; if a frame is open it closes it with Dear ImGui's own error recovery
(every window, ID and style the test left pushed is popped, then `end_frame`)
and warns, naming the test. This project turns warnings into errors
(`filterwarnings = ["error"]`), so the warning is an ERROR at the teardown of
the test that left the frame open, beside its own failure if it had one: the
blame lands on that test and on no other. A test that imports no Dear ImGui
costs one dictionary lookup. `tests/test_conftest_guard.py` runs the cascade
with and without it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PROBE = _ROOT / "scripts" / "mouse_probe.py"

XVFB_DISPLAY = 94
"""
The TCP display the `window` fixture's Xvfb listens on (port 6094).

The servers started by different test files share a network namespace, so each
has its own number: 99 is the probe's, 95 and 93 `tests/test_example_stream.py`'s.
(97 and 96 were `tests/test_examples.py`'s and `tests/test_example_gallery.py`'s for the
two old-API examples, deleted in tranche 5.) **Every window run on this machine that
goes through this fixture shares the one number**: two test runs at the same moment
collide on the port and one of them fails with "Xvfb is not running" (measured
2026-10-11: a second windowed process started during a whole-suite run turned two
unrelated window tests red, and they passed alone).
"""


@pytest.fixture(scope="session")
def bundled_fonts() -> Path:
    """
    The directory imgui-bundle ships Roboto, Inconsolata and Latin Modern Math in.
    """
    try:
        import imgui_bundle
    except ImportError as exc:  # pragma: no cover - environment, not logic
        pytest.skip(f"imgui-bundle is not importable, so its bundled fonts are unreachable: {exc}")

    fonts = Path(imgui_bundle.__file__).parent / "assets" / "fonts"
    if not fonts.is_dir():
        pytest.skip(f"imgui-bundle is installed but ships no font directory at {fonts}")
    return fonts


def close_open_imgui_frame() -> bool:
    """
    End the Dear ImGui frame the current context was left in, if it was. True if there was one.

    Nothing is imported to find out: a process that has not imported
    `imgui_bundle` has no frame open. With a context that is mid-frame
    (`WithinFrameScope`), Dear ImGui's own recovery unwinds what was left
    pushed since `NewFrame` (windows, child windows, IDs, style colours and
    variables, fonts, groups: `ErrorRecoveryTryToRecoverState` with the state
    the context stored at `NewFrame`) and the frame is then ended. The
    recovery reports each thing it pops as an error, which this wheel turns
    into a Python exception; that is switched off for the call and put back.
    """
    if "imgui_bundle" not in sys.modules:
        return False
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        return False
    context = imgui.get_current_context()
    if not context.within_frame_scope:
        return False
    io = imgui.get_io()
    asserts = io.config_error_recovery_enable_assert
    io.config_error_recovery_enable_assert = False
    try:
        imgui.internal.error_recovery_try_to_recover_state(context.stack_sizes_in_new_frame)
        imgui.end_frame()
    finally:
        io.config_error_recovery_enable_assert = asserts
    return True


@pytest.fixture(autouse=True)
def _no_frame_left_open(request: pytest.FixtureRequest) -> Iterator[None]:
    """
    After every test: a Dear ImGui frame it left open is closed, and said. See the module docstring.
    """
    yield
    if close_open_imgui_frame():
        warnings.warn(
            f"{request.node.nodeid} left a Dear ImGui frame open (it raised between begin and "
            "end, or never ended its frame); tests/conftest.py closed it so that the tests "
            "after it can run frames",
            stacklevel=1,
        )


def display_is_reachable(display: str, *, timeout: float = 0.5) -> bool:
    """
    Whether an X display accepts a connection, asked by connecting.

    `host:N` is TCP port `6000 + N`. `:N` (and `unix:N`) is the unix socket
    `/tmp/.X11-unix/XN`, which Xlib tries by abstract name first and by path
    second, so both are tried. Anything that cannot be parsed is reported
    unreachable: the caller's fallback is another window, not a skip.

    Nothing is sent. An X server that accepts and then refuses the client (no
    authority) reads as reachable here, and the shot then fails in GLFW, red.
    """
    host, _, rest = display.rpartition(":")
    try:
        number = int(rest.split(".")[0])
    except ValueError:
        return False
    if host and host != "unix":
        try:
            with socket.create_connection((host, 6000 + number), timeout=timeout):
                return True
        except OSError:
            return False
    for address in (f"\0/tmp/.X11-unix/X{number}", f"/tmp/.X11-unix/X{number}"):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(address)
                return True
        except OSError:
            continue
    return False


def _namespaces_work() -> bool:
    """
    Whether `unshare -rm` works here, asked by doing it.
    """
    if shutil.which("unshare") is None:
        return False
    try:
        done = subprocess.run(
            ["unshare", "-rm", "true"], capture_output=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def _wait_for_free_display(number: int, *, timeout: float = 15.0) -> bool:
    """
    Wait until nothing accepts a connection on the TCP display `number`. True if it is free.

    Every Xvfb this fixture starts listens on the same port, and one is still
    there for a moment after the run that started it has returned (it is
    killed with its namespace, not waited for). A run begun in that moment
    died with "server already running" and its test went red, in whichever
    file was next: three window tests in one whole-suite run on 2026-10-11,
    and one that calls `run` three times in a row failed two times in three
    ALONE. So the port is asked first. After `timeout` the run goes ahead
    anyway and fails as it did, saying so itself: another session's server on
    the same number is not this fixture's to wait out.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection(("127.0.0.1", 6000 + number), timeout=0.5):
                pass
        except OSError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


@dataclass(frozen=True)
class Window:
    """
    Somewhere a script can open a real window, and a directory it can write to.

    `where` is `"display"` (the session's own `DISPLAY`) or `"xvfb"`. `out` is
    under the repository's ignored `artifacts/` and not under pytest's
    `tmp_path`, because the Xvfb recipe mounts a tmpfs over `/tmp` inside its
    namespace and a file written to `$TMPDIR` there vanishes with it.
    """

    where: str
    out: Path

    def run(
        self, argv: Sequence[str], *, timeout: float = 180.0
    ) -> subprocess.CompletedProcess[str]:
        """
        Run `python argv...` where the window can open; never raises on a non-zero exit.
        """
        env = {**os.environ, "PYTHONPATH": str(_ROOT)}
        if self.where == "display":
            return subprocess.run(
                [sys.executable, *argv],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
                cwd=str(_ROOT),
            )
        spec = importlib.util.spec_from_file_location("_mouse_probe_for_conftest", _PROBE)
        assert spec is not None and spec.loader is not None
        probe = importlib.util.module_from_spec(spec)
        # `dataclasses` looks a class's module up in `sys.modules` while the
        # module body runs, so the module is registered for the load and
        # removed again: `scripts/` stays off `sys.path` and out of the way.
        sys.modules[spec.name] = probe
        try:
            spec.loader.exec_module(probe)
        finally:
            sys.modules.pop(spec.name, None)
        # The server starts in the background a moment before the inner
        # command, so the inner command waits for it to accept a connection.
        inner = textwrap.dedent(f"""
            import os, runpy, sys
            sys.path.insert(0, {str(_PROBE.parent)!r})
            from mouse_probe import wait_for_tcp_display
            if not wait_for_tcp_display(os.environ["DISPLAY"], timeout=30.0):
                raise SystemExit("the Xvfb never accepted a connection")
            sys.path.pop(0)
            sys.argv = {[str(a) for a in argv]!r}
            runpy.run_path(sys.argv[0], run_name="__main__")
            """)
        command = probe.xvfb_command([sys.executable, "-c", inner], display=XVFB_DISPLAY)
        _wait_for_free_display(XVFB_DISPLAY)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
            cwd=str(_ROOT),
        )


@pytest.fixture(scope="session")
def window() -> Iterator[Window]:
    """
    Where a real window can open on this machine, or a skip that says why none can.

    See the module docstring for the order of the probes and for why this is a
    probe at all.
    """
    display = os.environ.get("DISPLAY", "")
    if display and display_is_reachable(display):
        where = "display"
    elif shutil.which("Xvfb") is None:
        pytest.skip(
            f"DISPLAY={display or '(unset)'} accepts no connection and Xvfb is not "
            "installed, so there is nowhere to open a window"
        )
    elif not _namespaces_work():
        pytest.skip(
            f"DISPLAY={display or '(unset)'} accepts no connection and `unshare -rm` "
            "cannot make a user namespace here, which the Xvfb recipe needs"
        )
    else:
        where = "xvfb"
    # A unique directory, not one named for the pid: inside a sandbox every
    # session's pytest can be pid 3, and two runs sharing a name delete each
    # other's PNGs at teardown (measured by C-page-tables, 2026-10-07).
    (_ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-window-", dir=_ROOT / "artifacts"))
    try:
        yield Window(where, out)
    finally:
        shutil.rmtree(out, ignore_errors=True)

"""
Shared fixtures. There are two, a guard, and which imtypeset the session runs with.

**Which imtypeset (`TYPESET`, set when this file is imported).** About fifty
test files decide "the library is here" the same way, each for itself: by
`IMTYPESET_LIBRARY` being set, which is what `make ... TYPESET=1` does; and
they make a child that has no library by taking that variable and
`IMTYPESET_PYTHON` out of its environment. Both were the whole truth while the
library could only be built beside the tree. Since 2026-10-13 imtypeset is a
dependency, installed in the virtualenv, and found with nothing set
(`imscribe/typesetter.py`, route 2): the first rule would skip every
with-library test in the normal install, and the second would no longer make a
child without one. So, for the length of the session and for every process it
starts:

- `IMSCRIBE_NO_TYPESET=1` is put in the environment: imscribe does not LOOK
  for an installed imtypeset (`typesetter.DISABLE_VARIABLE`). A child with the
  two variables taken out is then a child without the library, as it always
  was.
- Where `IMTYPESET_LIBRARY` is not set, an imtypeset distribution is
  installed, and the caller did not set `IMSCRIBE_NO_TYPESET` itself,
  `IMTYPESET_LIBRARY` is set to the installed library's own path. Every
  file's test for the variable is then true, and what loads in a child that
  keeps it is the installed package with its own library (an installed
  imtypeset reads no variable; `typesetter.pairing()` says route
  `distribution` and names the variable under `ignored_environment`).

- **An installed imtypeset is hidden from a test that names another
  library, or stand-ins of its own** (`tests/data/not_installed`). An
  installed imtypeset reads no variable and comes before any directory
  `IMTYPESET_PYTHON` names, so a test that names a library that is not there
  and expects a refusal would be handed a working one. In this process, and
  in every child that has that directory on its `PYTHONPATH` (`Window.run`
  puts it there), the installed package is invisible unless
  `IMTYPESET_LIBRARY` names the library inside it.

Which gives three runs, and the line pytest prints at the top says which one
this is:

    make check                          the installed wheel, when there is one;
                                        without one, the no-library run
    IMSCRIBE_NO_TYPESET=1 make check    the no-library run, wheel or no wheel
    make check TYPESET=1                the library `make typeset-lib` built
                                        -- ONLY in a virtualenv with no
                                        imtypeset installed. With one, the
                                        installed library is what loads
                                        (measured 2026-10-13) and the header
                                        says so.

What this costs: inside this suite the route with NO variable at all, which
is the one a user gets, is run only by the tests that ask for it by taking
`IMSCRIBE_NO_TYPESET` out of a child's environment
(`tests/test_typesetter_pairing.py`).

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
fixture decides where a window can open by **asking**, in this order
(`choose_window`):

1. `Xvfb` is installed and `unshare -rm` can make a user namespace: run on an
   Xvfb of the fixture's own, over TCP inside one, which is the recipe
   `scripts/mouse_probe.py::xvfb_command` builds and
   `tests/test_mouse_probe.py` / `tests/test_examples.py` already use;
2. else the session's own `DISPLAY` accepts a connection: run on it;
3. else skip, naming which of the three probes failed.

**Until 2026-10-13 the first two were the other way round**, and a reachable
`DISPLAY` won. Where that display is a person's desktop its pointer is real:
a test that puts the mouse somewhere and reads what is under it then meets a
second pointer. Measured that day on `DISPLAY=:1` while two sessions worked:
four tests of `tests/test_typeset_view.py` failed in four runs of four on it
and the file passed with `DISPLAY` unset; seven window tests that failed in a
whole-suite run on it passed alone on the fixture's Xvfb. A server nobody
else can reach is the better default wherever one can be started.
`IMSCRIBE_TEST_DISPLAY=1` asks for the session's own display when it is
reachable (CI sets it: `xvfb-run` gives each job a display of its own).

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

_LIBRARY_VARIABLE = "IMTYPESET_LIBRARY"
_DISABLE_VARIABLE = "IMSCRIBE_NO_TYPESET"
HIDE_INSTALLED = _ROOT / "tests" / "data" / "not_installed"
"""On a child's `PYTHONPATH`, the module docstring's last rule holds in the child too."""
_HIDE_VARIABLE = "IMSCRIBE_TEST_NO_INSTALLED_IMTYPESET"


def _hide_installed_typeset() -> None:
    """
    The rule of `tests/data/not_installed/sitecustomize.py`, in this process and its children.
    """
    os.environ[_HIDE_VARIABLE] = "1"
    spec = importlib.util.spec_from_file_location(
        "_not_installed_for_tests", HIDE_INSTALLED / "sitecustomize.py"
    )
    assert spec is not None and spec.loader is not None
    hider = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hider)
    hider.hide()


def installed_typeset_library() -> Path | None:
    """
    The shared library inside an installed imtypeset distribution, or `None`.

    Found without importing the package (an import is the library's gate and
    maps the library into this process): the distribution by its metadata, the
    package by its spec, and the library as the file the package's own
    `_attestation.json` names, or the one `libimtypeset_bundle.*` beside it.
    A source directory of imtypeset on the path is not an installed one.
    """
    from importlib import metadata

    try:
        metadata.distribution("imtypeset")
        spec = importlib.util.find_spec("imtypeset")
    except Exception:  # noqa: BLE001 -- not installed, or not readable: there is none
        return None
    if spec is None or not spec.origin:
        return None
    package = Path(spec.origin).parent
    try:
        import json

        named = json.loads((package / "_attestation.json").read_text(encoding="utf-8"))
        file = named["library"]["file"]
        if isinstance(file, str) and (package / file).is_file():
            return package / file
    except (OSError, ValueError, KeyError, TypeError):
        pass
    found = sorted(package.glob("libimtypeset_bundle.*"))
    libraries = [path for path in found if path.suffix in (".so", ".dylib")]
    return libraries[0] if len(libraries) == 1 else None


def _choose_typeset() -> str:
    """
    Settle which imtypeset this session runs with; the sentence for pytest's header.

    The module docstring has the rule. Writes `os.environ`, once, at import of
    this file, which is before any test module is imported.
    """
    # The reading `imscribe.typesetter._not_looking` makes: blanks alone are nothing.
    asked_without = (os.environ.get(_DISABLE_VARIABLE) or "").strip() not in ("", "0")
    named = os.environ.get(_LIBRARY_VARIABLE) or ""
    installed = installed_typeset_library()
    os.environ[_DISABLE_VARIABLE] = "1"
    if installed is not None:
        _hide_installed_typeset()
    if named and installed is not None:
        return (
            f"imtypeset: {_LIBRARY_VARIABLE}={named} is set AND a distribution is installed: "
            f"the INSTALLED library is what loads ({installed}); the one named is ignored by it"
        )
    if named:
        return f"imtypeset: the library {_LIBRARY_VARIABLE} names ({named})"
    if asked_without:
        return f"imtypeset: none ({_DISABLE_VARIABLE} was set): the no-library run"
    if installed is not None:
        os.environ[_LIBRARY_VARIABLE] = str(installed)
        return f"imtypeset: the installed distribution ({installed})"
    return "imtypeset: none (not installed, and no library named): the no-library run"


TYPESET = _choose_typeset()
"""Which imtypeset the session runs with, as pytest's header says it."""


def pytest_report_header() -> str:
    return TYPESET


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
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(_ROOT), str(HIDE_INSTALLED)])}
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


DISPLAY_VARIABLE = "IMSCRIBE_TEST_DISPLAY"
"""Set (not empty, not 0): the `window` fixture runs on the session's `DISPLAY` when it answers."""


def choose_window(*, asked: bool, reachable: bool, xvfb: bool) -> str | None:
    """
    `"display"`, `"xvfb"`, or `None` for nowhere: the order of the module docstring.

    `asked` is `DISPLAY_VARIABLE`; `reachable` is whether the session's
    `DISPLAY` accepts a connection; `xvfb` is whether an Xvfb can be started
    in a user namespace.
    """
    if asked and reachable:
        return "display"
    if xvfb:
        return "xvfb"
    return "display" if reachable else None


@pytest.fixture(scope="session")
def window() -> Iterator[Window]:
    """
    Where a real window can open on this machine, or a skip that says why none can.

    See the module docstring for the order of the probes and for why this is a
    probe at all.
    """
    display = os.environ.get("DISPLAY", "")
    asked = (os.environ.get(DISPLAY_VARIABLE) or "0").strip() != "0"
    reachable = bool(display) and display_is_reachable(display)
    installed = shutil.which("Xvfb") is not None
    where = choose_window(asked=asked, reachable=reachable, xvfb=installed and _namespaces_work())
    if where is None and not installed:
        pytest.skip(
            f"DISPLAY={display or '(unset)'} accepts no connection and Xvfb is not "
            "installed, so there is nowhere to open a window"
        )
    if where is None:
        pytest.skip(
            f"DISPLAY={display or '(unset)'} accepts no connection and `unshare -rm` "
            "cannot make a user namespace here, which the Xvfb recipe needs"
        )
    assert where is not None
    # A unique directory, not one named for the pid: inside a sandbox every
    # session's pytest can be pid 3, and two runs sharing a name delete each
    # other's PNGs at teardown (measured by C-page-tables, 2026-10-07).
    (_ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-window-", dir=_ROOT / "artifacts"))
    try:
        yield Window(where, out)
    finally:
        shutil.rmtree(out, ignore_errors=True)

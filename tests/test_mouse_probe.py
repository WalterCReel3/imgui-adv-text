r"""
Tests for `scripts/mouse_probe.py`: the aiming arithmetic, the gesture script, and one real window.

Three levels of fidelity, and each test says which it is at.

**Pure.** `SeenTypeset`'s arithmetic over a stand-in view, `first_words_end`,
`report` and `xvfb_command` take data and return data. No ImGui.

**A real ImGui context with no backend.** `--no-window` plays the whole
eight-gesture script through `App.gui()` in frames of a bare
`imgui.create_context()`. The event queue, hover resolution, the sidebar, the
scrolling child and the click counter are ImGui's own. The clipboard is
ImGui's in-memory one and the time step is a constant.

**A real window.** `test_the_probe_passes_in_a_real_window_on_an_xvfb` runs the
script with `--xvfb` in a subprocess: the real app, through the real
`immapp.run`, GLFW and an OpenGL context, on an Xvfb started in a user
namespace. The events still enter at ImGui's input queue rather than at the X
server -- nothing here can move an X pointer -- and the script's docstring
says what that leaves unexercised.

**The view probed is `TypesetView`, and every run of the gestures is in a child
process.** The Document page draws through the imtypeset library or draws one
line saying why not; the library is never loaded into the pytest process; so
the gestures are played in children, which have the library when the suite
runs with it (`make test TYPESET=1` sets `IMTYPESET_LIBRARY`) and skip, with
the reason, when it does not. What the plain run holds instead is the other
half of the contract: with no library the probe plays nothing, says the
page's own sentence, and exits 2.

**What left this file with tranche 5 (2026-10-11).** Until then the probe had a
second gesture script for imscribe's own `DocumentView`, which the Document
page fell back to without the library, and this file ran that script in the
pytest process: five pure tests of its aiming over `imscribe.selection`
(`line_text`, `find_line`, `alone_in_its_band`, `cell_point`, `Seen.on_screen`)
and five runs of it through `App.gui()`. The fallback is removed and so is
that half of the probe; its five pure tests went with it, and the five runs
are restated below against `TypesetView`, in children.

**On the skips.** The window tests skip only when `unshare -rm` cannot make a
namespace or `Xvfb` is not installed, which is a statement about the machine;
the with-library tests skip when the library was not asked for.

**These tests can fail, and three of them exist to show it.** An instrument
that reports eighteen passes out of eighteen is worth nothing until it has been
seen to report a failure. `test_a_view_that_hit_tests_from_the_wrong_origin_
fails_the_probe` (bare context, and again in a real window) shifts the view's
own idea of where the pointer is by one line, and
`test_a_view_that_never_copies_fails_on_the_sentinel` removes the copy. Each
must turn the report red, in the checks one would expect.

Loaded by path rather than imported, for the reason `tests/test_shot.py` gives:
`scripts/` stays off `sys.path`.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from conftest import HIDE_INSTALLED

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "mouse_probe.py"
_SAMPLE = _ROOT / "demo" / "sample.md"
_LIBRARY = "IMTYPESET_LIBRARY"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.

    Registered in `sys.modules` for the length of the load because the script
    defines slotted dataclasses, and `dataclasses` looks the defining module up
    by name while it builds them.
    """
    name = "_mouse_probe_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def probe() -> ModuleType:
    """The script, loaded once."""
    return _load()


# -- pure ----------------------------------------------------------------


class _Line:
    """A line as `TypesetView.set_lines` gives one: a range of a block's text and a band."""

    def __init__(self, block: int, start: int, end: int, top: float, bottom: float) -> None:
        self.block, self.start, self.end, self.top, self.bottom = block, start, end, top, bottom


class _View:
    """Just enough of a `TypesetView` for `SeenTypeset`'s arithmetic."""

    texts = ["Alpha bravo charlie delta", "A table", "Echo"]
    tables = {1: object()}
    hosts: dict[int, object] = {}
    separator = "\n\n"

    def __init__(self) -> None:
        self.rects: dict[tuple[int, int, int], list[tuple[float, float, float, float]]] = {}

    def set_lines(self) -> list[_Line]:
        return [
            _Line(0, 0, 12, 0.0, 20.0),
            _Line(0, 12, 25, 20.0, 40.0),
            _Line(1, 0, 7, 50.0, 70.0),
            _Line(2, 0, 4, 80.0, 100.0),
        ]

    def span_rects(
        self, block: int, start: int, end: int
    ) -> list[tuple[float, float, float, float]]:
        return self.rects.get((block, start, end), [])


def test_the_lines_aimed_at_leave_out_tables_and_read_their_text_from_the_description(
    probe: ModuleType,
) -> None:
    """
    A line's text is its range of the block's DESCRIBED text, which is what the
    probe expects a copy to hold; a table's block is not aimed at.
    """
    seen = probe.SeenTypeset(view=_View())
    lines = seen.lines()
    assert [line.block for line in lines] == [0, 0, 2]
    assert [seen.text(line) for line in lines] == ["Alpha bravo ", "charlie delta", "Echo"]
    with pytest.raises(probe.ProbeError, match="no TypesetView has drawn"):
        probe.SeenTypeset().lines()


def test_a_point_is_the_origin_plus_the_characters_own_rectangle(probe: ModuleType) -> None:
    """
    A quarter of the way into a character is left of its midpoint, three quarters right.

    And the whole thing moves with the origin, by exactly the origin: that is
    the property a scroll relies on. A character with no rectangle of its
    own, or one of no width, is a loud failure and not a guess.
    """
    view = _View()
    second = view.set_lines()[1]
    view.rects[(0, 14, 15)] = [(30.0, 20.0, 38.0, 40.0)]
    seen = probe.SeenTypeset(view=view, origin=(300.0, 120.0))
    quarter, three = seen.point(second, 2, 0.25), seen.point(second, 2, 0.75)
    assert (quarter.x, three.x) == (300.0 + 32.0, 300.0 + 36.0)
    assert quarter.y == three.y == 120.0 + 30.0
    moved = probe.SeenTypeset(view=view, origin=(300.0, 120.0 - 500.0))
    assert moved.point(second, 2, 0.25).y == quarter.y - 500.0

    with pytest.raises(probe.ProbeError, match="has no one rectangle"):
        seen.point(second, 3, 0.5)
    view.rects[(0, 15, 16)] = [(40.0, 20.0, 40.0, 40.0)]
    with pytest.raises(probe.ProbeError, match="has no one rectangle"):
        seen.point(second, 3, 0.5)
    view.rects[(0, 16, 17)] = [(40.0, 20.0, 44.0, 40.0), (0.0, 40.0, 4.0, 60.0)]
    with pytest.raises(probe.ProbeError, match="has no one rectangle"):
        seen.point(second, 4, 0.5)


def test_on_screen_wants_the_whole_band_inside_the_window(probe: ModuleType) -> None:
    """
    A line cut by the window's edge is not a target.
    """
    first, *_, last = _View().set_lines()
    seen = probe.SeenTypeset(
        view=_View(), origin=(0.0, 100.0), window_top=100.0, window_height=40.0
    )
    assert seen.on_screen(first) is False  # its top is inside the 4 px inset
    seen.window_top = 90.0
    assert seen.on_screen(first) is True
    assert seen.on_screen(last) is False


def test_a_copied_line_loses_the_space_it_was_broken_at_and_an_unbroken_one_nothing(
    probe: ModuleType,
) -> None:
    """
    The copy rule the probe expects, stated by the other team and restated here as data.
    """
    seen = probe.SeenTypeset(view=_View())
    broken, last, _ = seen.lines()
    assert seen.text(broken) == "Alpha bravo " and seen.line_copy(broken) == "Alpha bravo"
    assert seen.line_copy(last) == "charlie delta"


def test_first_words_end_counts_characters_through_the_nth_word(probe: ModuleType) -> None:
    assert probe.first_words_end("Alpha bravo charlie") == len("Alpha bravo")
    assert probe.first_words_end("Alpha bravo charlie", 1) == len("Alpha")
    assert probe.first_words_end("Alpha", 2) == len("Alpha")
    with pytest.raises(probe.ProbeError):
        probe.first_words_end("   ")


def test_the_report_shows_both_values_for_a_failure_and_counts(probe: ModuleType) -> None:
    """
    A red check prints what was wanted and what was found; a green one, one line.
    """
    text = probe.report([probe.Check("a", 1, 1), probe.Check("b", "want", "got")])
    assert "PASS  a" in text
    assert "FAIL  b" in text
    assert "'want'" in text and "'got'" in text
    assert text.endswith("1 of 2 checks passed")


def test_an_outcome_with_no_checks_or_with_an_error_has_not_passed(probe: ModuleType) -> None:
    """
    Nothing checked is not a pass, and neither is a run that stopped early.

    The first is the vacuous case: a script that raised before its first check
    would otherwise report zero failures.
    """
    green = (probe.Check("a", 1, 1),)
    assert probe.Outcome("m", green, None, 1, 0.0).passed is True
    assert probe.Outcome("m", (), None, 1, 0.0).passed is False
    assert probe.Outcome("m", green, probe.ProbeError("x"), 1, 0.0).passed is False
    assert probe.Outcome("m", (*green, probe.Check("b", 1, 2)), None, 1, 0.0).passed is False


def test_the_xvfb_command_names_a_tcp_display_and_never_a_unix_socket(probe: ModuleType) -> None:
    """
    The shell `--xvfb` runs: the links that were measured to matter, and the quoting.

    `-nolisten unix` and a host in `DISPLAY` are the two that differ from what a
    reader would write from memory, and both are there because `socket(AF_UNIX)`
    is refused in the sandbox this was built in.
    """
    command = probe.xvfb_command(["python", "a script.py", "--opening", "it's"], display=42)
    assert command[:5] == ["unshare", "-rm", "sh", "-e", "-c"]
    shell = command[5]
    assert "mount -t tmpfs tmpfs /tmp" in shell
    assert "Xvfb :42 " in shell and "-listen tcp" in shell and "-nolisten unix" in shell
    assert "-nolisten local" in shell
    assert "DISPLAY=127.0.0.1:42" in shell
    assert "LIBGL_ALWAYS_SOFTWARE=1" in shell
    assert "python 'a script.py' --opening 'it'\"'\"'s'" in shell


def test_a_tcp_display_is_probed_and_a_local_one_is_not(probe: ModuleType) -> None:
    """
    `host:N` is TCP port 6000 + N and is connected to; `:N` is left to GLFW.
    """
    assert probe.wait_for_tcp_display(":1", timeout=0.0) is True
    assert probe.wait_for_tcp_display("127.0.0.1:nonsense", timeout=0.0) is True

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert probe.wait_for_tcp_display(f"127.0.0.1:{port - 6000}.0", timeout=2.0) is True
    # Closed now, so the same port refuses.
    assert probe.wait_for_tcp_display(f"127.0.0.1:{port - 6000}", timeout=0.0) is False


# -- events, against the real IO object ----------------------------------


def test_post_goes_through_imguis_event_queue_and_the_next_frame_sees_it(
    probe: ModuleType,
) -> None:
    """
    Each event type reaches the real `ImGuiIO` through `add_*_event`.

    A real context rather than a recording stub, for the reason
    `tests/test_shot.py` drives a real `RunnerParams`: a stub with the method
    names copied out of the script would keep passing after imgui-bundle renamed
    one. Read back after `new_frame`, which is where the queue is drained.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1100.0, 800.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    def frame(*events: Any) -> None:
        for event in events:
            probe.post(io, event, imgui)
        imgui.new_frame()

    try:
        frame(probe.Move(123.0, 45.0))
        assert (imgui.get_mouse_pos().x, imgui.get_mouse_pos().y) == (123.0, 45.0)
        imgui.render()
        frame(probe.Button(True))
        assert imgui.is_mouse_clicked(imgui.MouseButton_.left)
        imgui.render()
        frame(probe.Button(False))
        assert imgui.is_mouse_released(imgui.MouseButton_.left)
        imgui.render()
        frame(probe.Wheel(-3.0))
        assert io.mouse_wheel == -3.0
        imgui.render()
        frame(probe.Key("ctrl", True))
        assert io.key_ctrl
        imgui.render()
        frame(probe.Key("c", True))
        assert imgui.is_key_pressed(imgui.Key.c, False)
        imgui.render()
        frame(probe.Key("c", False), probe.Key("ctrl", False))
        imgui.render()
        frame(probe.Move(-1.0e6, -1.0e6))
        assert not io.key_ctrl
    finally:
        imgui.render()


# -- the whole script, in a real context with no backend, in a child -------


_CHILD = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_mouse_probe_child", sys.argv[1])
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
SAMPLE = open(sys.argv[2], encoding="utf-8").read()
"""


def _child(body: str, *, library: bool) -> subprocess.CompletedProcess[str]:
    """
    Run `_CHILD` and then `body` in a fresh interpreter, with or without the library's variables.

    The script is loaded there as `probe` and `demo/sample.md` read as `SAMPLE`.
    """
    environment = {**os.environ, "PYTHONPATH": str(_ROOT)}
    if not library:
        environment = {k: v for k, v in environment.items() if not k.startswith("IMTYPESET_")}
    return subprocess.run(
        [sys.executable, "-c", _CHILD + body, str(_SCRIPT), str(_SAMPLE)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=_ROOT,
        env=environment,
    )


def _needs_the_library() -> None:
    if not os.environ.get(_LIBRARY):
        pytest.skip(
            f"{_LIBRARY} is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )


def test_without_the_library_the_probe_plays_nothing_says_why_and_exits_2() -> None:
    """
    The plain gate's statement, and it is run on both gates with the variables removed.

    No gesture is played at a page that draws one line: zero checks, the
    page's own sentence, the way to get a library, and the exit status that
    means "could not run", not the one that means a check failed.
    """
    done = _child('raise SystemExit(probe.main(["--no-window"]))', library=False)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "renderer none" in done.stdout and "0 of 0 checks passed" in done.stdout
    assert "the probe stopped early: NotDrawing" in done.stdout
    assert "imtypeset is not drawing: IMTYPESET_LIBRARY is not set" in done.stdout
    assert "make typeset-lib" in done.stderr
    assert "FAIL" not in done.stdout


def test_a_library_that_was_asked_for_and_does_not_draw_is_a_failure_and_not_an_absence(
    tmp_path: Path,
) -> None:
    """
    Exit 1, not 2: the variable names a library that is not there, so the
    page draws its line with that reason and the probe has failed.
    """
    environment = {
        **{k: v for k, v in os.environ.items() if not k.startswith("IMTYPESET_")},
        # The second directory: an installed imtypeset reads no variable and
        # would draw; it is hidden from a child that names another library
        # (`tests/conftest.py`, "An installed imtypeset is hidden").
        "PYTHONPATH": os.pathsep.join([str(_ROOT), str(HIDE_INSTALLED)]),
        _LIBRARY: str(tmp_path / "absent.so"),
    }
    done = subprocess.run(
        [sys.executable, str(_SCRIPT), "--no-window"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=_ROOT,
        env=environment,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the probe stopped early: NotDrawing" in done.stdout
    assert "IMTYPESET_LIBRARY is not set" not in done.stdout


def test_every_gesture_passes_against_the_demo_document_with_no_window() -> None:
    """
    Fidelity: a real ImGui context, `App.gui()`, no backend, `demo/sample.md`, the library.

    All eight gestures, by number, so a script that returned early after the
    third would not pass on the strength of the first three; and the events
    posted include a wheel and a key, so the scroll and the copy were played
    and not skipped.
    """
    _needs_the_library()
    done = _child(
        """
outcome = probe.run_without_a_window(SAMPLE)
print(probe.report(outcome.checks))
assert outcome.error is None, outcome.error
assert outcome.passed
numbers = {check.name.split()[0] for check in outcome.checks}
assert numbers == {"1", "2", "3", "4", "5", "6", "7", "8"}, numbers
assert len(outcome.checks) == 18
assert outcome.renderer == "TypesetView"
print("CHILD OK")
""",
        library=True,
    )
    assert done.returncode == 0 and "CHILD OK" in done.stdout, done.stdout + done.stderr


def test_the_script_can_be_run_twice_in_one_process() -> None:
    """
    A second run inherits nothing of the first: not its scroll, its clicks or its library context.

    Each run makes and destroys its own Dear ImGui context and unloads the
    library before the context goes, so the second run's `load_fonts` meets
    no context left from the first.
    """
    _needs_the_library()
    done = _child(
        """
from imgui_bundle import imgui
assert probe.run_without_a_window(SAMPLE).passed
assert imgui.get_current_context() is None
again = probe.run_without_a_window(SAMPLE)
print(probe.report(again.checks))
assert again.passed and len(again.checks) == 18
print("CHILD OK")
""",
        library=True,
    )
    assert done.returncode == 0 and "CHILD OK" in done.stdout, done.stdout + done.stderr


_LOW = """
from imgui_bundle import imgui
from imscribe.ui.typeset_view import TypesetView

LOW = 22.0
real_mouse = TypesetView._handle_mouse

def low_mouse(self, doc, origin, size):
    # The text is where it was; the view believes its corner is a line higher.
    return real_mouse(self, doc, imgui.ImVec2(origin.x, origin.y - LOW), size)

TypesetView._handle_mouse = low_mouse
"""

_LOW_FAILS = (
    "1 drag over two words, left to right: range",
    "1 drag over two words, left to right: text",
    "4 double click: text",
    "5 triple click: text",
)


def test_a_view_that_hit_tests_from_the_wrong_origin_fails_the_probe() -> None:
    """
    The instrument detects the defect it was built for.

    `TypesetView._handle_mouse` is handed an origin one line higher than the
    one the text was drawn from, which is what a head applied to the glyphs
    and not to the mouse does. The text is drawn where it was; every click
    lands a line down. The probe must say so on the very first gesture, and
    it must still finish.
    """
    _needs_the_library()
    done = _child(_LOW + 'raise SystemExit(probe.main(["--no-window"]))', library=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "renderer TypesetView\n" in done.stdout, done.stdout
    for name in _LOW_FAILS:
        assert f"FAIL  {name}" in done.stdout, done.stdout
    assert "of 18 checks passed" in done.stdout


def test_a_view_that_never_copies_fails_on_the_sentinel() -> None:
    """
    A copy that did not happen cannot pass on what the clipboard already held.

    Gesture 5 selects a line and gesture 6 copies it; the clipboard is seeded
    with a sentinel before each copy. With the view's key handling removed
    the sentinel is what comes back, and only the two copy checks fail.
    """
    _needs_the_library()
    done = _child(
        """
from imscribe.ui.typeset_view import TypesetView
TypesetView._handle_keys = lambda self: None
outcome = probe.run_without_a_window(SAMPLE)
failed = {check.name: check.actual for check in outcome.checks if not check.ok}
print(failed)
assert set(failed) == {
    "6 ctrl+C: the clipboard holds the line",
    "8 ctrl+C: the clipboard holds all of it, the undrawn part included",
}, failed
assert set(failed.values()) == {probe.SENTINEL}
assert len(outcome.checks) == 18
print("CHILD OK")
""",
        library=True,
    )
    assert done.returncode == 0 and "CHILD OK" in done.stdout, done.stdout + done.stderr


def test_a_document_without_the_opening_line_stops_early_and_does_not_pass() -> None:
    """
    A missing target is an error with no checks, and that is not a pass.

    And the watcher is taken off the class again: `TypesetView._handle_mouse`
    is the real method after a run that ended in an error.
    """
    _needs_the_library()
    done = _child(
        """
from imscribe.ui.typeset_view import TypesetView
before = TypesetView._handle_mouse
PROSE = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima.\\n"
outcome = probe.run_without_a_window(PROSE)
assert isinstance(outcome.error, probe.ProbeError), outcome.error
assert not isinstance(outcome.error, probe.NotDrawing), outcome.error
assert "no line starts with" in str(outcome.error), outcome.error
assert outcome.checks == () and not outcome.passed
assert outcome.renderer == "TypesetView"
assert TypesetView._handle_mouse is before
print("CHILD OK")
""",
        library=True,
    )
    assert done.returncode == 0 and "CHILD OK" in done.stdout, done.stdout + done.stderr


# -- the real window -----------------------------------------------------


def _can_make_a_namespace() -> bool:
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


def _needs_an_xvfb() -> None:
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which --xvfb needs")


def _abstract_x_sockets() -> str:
    try:
        return Path("/proc/net/unix").read_text(encoding="ascii", errors="replace")
    except OSError:
        return ""


def _an_unused_display() -> int:
    """
    A display number with no lock file, no abstract socket and a free TCP port.
    """
    taken = _abstract_x_sockets()
    for number in range(170, 260):
        if Path(f"/tmp/.X{number}-lock").exists() or f"@/tmp/.X11-unix/X{number}\n" in taken:
            continue
        with socket.socket() as trial:
            try:
                trial.bind(("127.0.0.1", 6000 + number))
            except OSError:
                continue
        return number
    pytest.skip("no display number between 170 and 259 is free")


def test_the_xvfb_starts_where_the_host_already_has_a_server_on_that_display(
    probe: ModuleType,
) -> None:
    """
    `xvfb_command`'s server survives a host server on the same display number.

    GitHub run 38497533497: under `xvfb-run -a` (which takes `:99`) the probe's
    own `Xvfb :99` died with "Cannot establish any listening sockets", because
    the abstract socket `@/tmp/.X11-unix/X99` lives in the network namespace
    `unshare -rm` shares with the host. `-nolisten local` is what stops that.
    Here the host server is started as `xvfb-run` starts one (no TCP), and the
    inner command passes only if the namespace's server answers on TCP.
    """
    _needs_an_xvfb()
    number = _an_unused_display()
    host = subprocess.Popen(
        ["Xvfb", f":{number}", "-screen", "0", "64x64x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if f"@/tmp/.X11-unix/X{number}\n" in _abstract_x_sockets():
                break
            if host.poll() is not None:
                pytest.skip(f"the host Xvfb on :{number} did not start")
            time.sleep(0.1)
        else:
            pytest.skip(f"the host Xvfb on :{number} never bound its abstract socket")
        inner = (
            "import sys; sys.path.insert(0, sys.argv[1]); import mouse_probe; "
            "import os; sys.exit(0 if mouse_probe.wait_for_tcp_display("
            "os.environ['DISPLAY'], timeout=20.0) else 'no answer')"
        )
        done = subprocess.run(
            probe.xvfb_command([sys.executable, "-c", inner, str(_SCRIPT.parent)], display=number),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=_ROOT,
        )
    finally:
        host.terminate()
        host.wait(timeout=10)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Xvfb is not running" not in done.stdout, done.stdout


def test_the_probe_passes_in_a_real_window_on_an_xvfb() -> None:
    """
    Fidelity: the real app in a real GLFW window with an OpenGL context, on Xvfb.

    A subprocess, because `immapp.run` owns a process's one GLFW lifetime and
    because the server lives in a namespace this process is not in. The
    assertion is on the script's own report and exit status. About four seconds.

    With the library: eighteen of eighteen, at a `TypesetView`. Without it the
    same command is the real app drawing its one line in a real window, and
    the probe must say so and exit 2; a green "0 of 0" there, or a pass at a
    view that is not on screen, is what this refuses.
    """
    _needs_an_xvfb()

    done = subprocess.run(
        [sys.executable, str(_SCRIPT), "--xvfb"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=_ROOT,
    )
    assert "mouse probe, window:" in done.stdout, done.stdout + done.stderr
    assert "FAIL" not in done.stdout
    if os.environ.get(_LIBRARY):
        assert done.returncode == 0, done.stdout + done.stderr
        assert "renderer TypesetView\n" in done.stdout, done.stdout
        assert "18 of 18 checks passed" in done.stdout
    else:
        assert done.returncode == 2, done.stdout + done.stderr
        assert "renderer none\n" in done.stdout, done.stdout
        assert "0 of 0 checks passed" in done.stdout
        assert "imtypeset is not drawing: IMTYPESET_LIBRARY is not set" in done.stdout


def test_a_view_that_hit_tests_from_the_wrong_origin_fails_the_probe_in_a_real_window(
    probe: ModuleType,
) -> None:
    """
    The window probe detects the defect it was built for.

    `test_a_view_that_hit_tests_from_the_wrong_origin_fails_the_probe`, in the
    real app. The run must still finish and still name the view.
    """
    _needs_the_library()
    _needs_an_xvfb()

    code = _CHILD + _LOW + "raise SystemExit(probe.main([]))"
    done = subprocess.run(
        probe.xvfb_command([sys.executable, "-c", code, str(_SCRIPT), str(_SAMPLE)]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "renderer TypesetView\n" in done.stdout, done.stdout
    for name in _LOW_FAILS:
        assert f"FAIL  {name}" in done.stdout, done.stdout
    assert "of 18 checks passed" in done.stdout

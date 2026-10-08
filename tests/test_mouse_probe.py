r"""
Tests for `scripts/mouse_probe.py`: the aiming arithmetic, the gesture script, and one real window.

Three levels of fidelity, and each test says which it is at.

**Pure.** `cell_point`, `find_line`, `alone_in_its_band`, `first_words_end`,
`report` and `xvfb_command` take data and return data. No ImGui.

**A real ImGui context with no backend.** `run_without_a_window` plays the whole
eight-gesture script through `App.gui()` in frames of a bare
`imgui.create_context()` -- the idiom `tests/test_imgui_draw.py` established and
`tests/test_document_view.py::_page_frame` already uses for one press and one
drag. The event queue, hover resolution, the tab bar, the scrolling child and
the click counter are ImGui's own. The clipboard is ImGui's in-memory one, the
time step is a constant, and no font of ours is in the atlas. This runs
everywhere the suite does.

**A real window.** `test_the_probe_passes_in_a_real_window_on_an_xvfb` runs the
script with `--xvfb` in a subprocess: the real app, through the real
`immapp.run`, GLFW and an OpenGL context, on an Xvfb started in a user
namespace. It was green where it was written, on 2026-10-06, in a sandbox whose
own `DISPLAY=:1` is unreachable. The events still enter at ImGui's input queue
rather than at the X server -- nothing here can move an X pointer -- and the
script's docstring says what that leaves unexercised.

**On the one skip.** `docs/status.md` values a suite with none, so the gate is a
capability probe and not a guess: the window test skips only when `unshare -rm`
cannot make a namespace or `Xvfb` is not installed, which is a statement about
the machine. Where both exist a probe that cannot open its window is red.

**These tests can fail, and two of them exist to show it.** An instrument that
reports eighteen passes out of eighteen is worth nothing until it has been seen
to report a failure, and this project has had five families of vacuous tests.
`test_a_view_that_hit_tests_from_the_wrong_origin_fails_the_probe` shifts the
view's own idea of where the pointer is by one margin -- the half-applied-origin
defect `tests/test_document_view.py` describes -- and
`test_a_view_that_never_copies_fails_on_the_sentinel` removes the copy. Both
must turn the report red, in the checks one would expect.

Loaded by path rather than imported, for the reason `tests/test_shot.py` gives:
`scripts/` stays off `sys.path`.
"""

from __future__ import annotations

import importlib.util
import shutil
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from advtext.markdown import build_document
from advtext.selection import SelectionModel
from advtext.shipout import Point, ship
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import compose
from advtext.units import px_from_sp, sp_from_px

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "mouse_probe.py"
_SAMPLE = _ROOT / "demo" / "sample.md"


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


def _model(source: str, width_px: float = 467.0) -> SelectionModel:
    """
    A selection model over real markdown, built the way `DocumentView.layout_for` does.
    """
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    box = compose(
        build_document(source, theme, fontlib_metrics), theme, sp_from_px(width_px), measure
    )
    return SelectionModel.from_commands(tuple(ship(box, Point(0, box.height), measure=measure)))


class _View:
    """Just enough of a `DocumentView` for `Seen`'s arithmetic."""

    px_per_inch = 96.0


PROSE = (
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky "
    "xray yankee zulu.\n"
)

TABLE = "Lead paragraph here.\n\n| one | two |\n|---|---|\n| left cell | right cell |\n"


# -- pure ----------------------------------------------------------------


def test_line_text_is_the_lines_characters_with_one_space_a_glue(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    The probe's own rendering of a line agrees with the source it was set from.

    It is the basis of every expected string, so it is pinned against the
    markdown rather than against `SelectionModel.text`, which is what the probe
    exists to check.
    """
    model = _model(PROSE)
    joined = " ".join(probe.line_text(line).strip() for line in model.fragments)
    assert joined == PROSE.strip()
    assert len(model.fragments) >= 3, "the fixture must wrap"


def test_find_line_finds_by_content_and_is_loud_when_the_line_is_absent(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    A target is located by what it says, and a missing one names what is there.
    """
    model = _model("First paragraph.\n\nSecond paragraph here.\n")
    assert probe.line_text(model.fragments[probe.find_line(model, "Second")]).startswith("Second")
    with pytest.raises(probe.ProbeError, match="First paragraph"):
        probe.find_line(model, "Third")


def test_two_lines_side_by_side_are_not_alone_in_their_band_and_a_stacked_one_is(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    The probe refuses to aim where "the line at this y" has two answers.

    A table row was the case this was written for and it is **not** one: a row
    ships as a single line today (`'left cell right cell '`, checked below), so
    the side-by-side case is built by hand, from a real line set a second time
    further right.
    """
    table = _model(TABLE)
    assert [probe.line_text(line).strip() for line in table.fragments if line.items] == [
        "Lead paragraph here.",
        "one two",
        "left cell right cell",
    ]
    assert all(probe.alone_in_its_band(table, at) for at in range(len(table.fragments)))

    prose = _model(PROSE)
    first, second = prose.fragments[0], prose.fragments[1]
    beside = replace(second, line=replace(second.line, x=second.line.x + sp_from_px(600.0)))
    model = SelectionModel(fragments=(first, second, beside), length=prose.length)
    assert probe.alone_in_its_band(model, 0) is True
    assert probe.alone_in_its_band(model, 1) is False
    assert probe.alone_in_its_band(model, 2) is False


def test_cell_point_is_the_origin_plus_the_cells_own_coordinates(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    A quarter of the way into a cell is left of its midpoint, three quarters right.

    And the whole thing moves with the origin, by exactly the origin: that is
    the property a scroll relies on.
    """
    model = _model(PROSE)
    line = model.fragments[1]
    seen = probe.Seen(view=_View(), origin=(300.0, 120.0))
    left = 300.0 + px_from_sp(line.edges[2])
    right = 300.0 + px_from_sp(line.edges[3])
    quarter = probe.cell_point(seen, line, 2, 0.25)
    three = probe.cell_point(seen, line, 2, 0.75)
    assert left < quarter.x < (left + right) / 2 < three.x < right
    assert 120.0 + px_from_sp(line.top) < quarter.y < 120.0 + px_from_sp(line.bottom)

    moved = probe.Seen(view=_View(), origin=(300.0, 120.0 - 500.0))
    assert probe.cell_point(moved, line, 2, 0.25).y == pytest.approx(quarter.y - 500.0)


def test_on_screen_wants_the_whole_band_inside_the_window(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    A line cut by the window's edge is not a target.
    """
    model = _model(PROSE)
    first, last = model.fragments[0], model.fragments[-1]
    seen = probe.Seen(view=_View(), origin=(0.0, 100.0), window_top=100.0, window_height=40.0)
    assert seen.on_screen(first) is False  # its top is inside the 4 px inset
    seen.window_top = 90.0
    assert seen.on_screen(first) is True
    assert seen.on_screen(last) is False


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


# -- the whole script, in a real context with no backend ------------------


def test_every_gesture_passes_against_the_demo_document_with_no_window(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    Fidelity: a real ImGui context, `App.gui()`, no backend, `demo/sample.md`.

    All eight gestures, by number, so a script that returned early after the
    third would not pass on the strength of the first three; and the events
    posted include a wheel and a key, so the scroll and the copy were played and
    not skipped.
    """
    outcome = probe.run_without_a_window(_SAMPLE.read_text(encoding="utf-8"))
    assert outcome.error is None
    assert outcome.passed, probe.report(outcome.checks)
    numbers = {check.name.split()[0] for check in outcome.checks}
    assert numbers == {"1", "2", "3", "4", "5", "6", "7", "8"}
    assert len(outcome.checks) == 18


def test_the_script_can_be_run_twice_in_one_context(probe: ModuleType, bundled_fonts: Any) -> None:
    """
    A second run does not inherit the first one's scroll position or its clicks.

    Both were real: the child window's scroll is ImGui state keyed by window id,
    and a press near the last run's final click inside the double-click time
    would be counted as its second click.
    """
    source = _SAMPLE.read_text(encoding="utf-8")
    assert probe.run_without_a_window(source).passed
    again = probe.run_without_a_window(source)
    assert again.passed, probe.report(again.checks)


def test_a_view_that_hit_tests_from_the_wrong_origin_fails_the_probe(
    probe: ModuleType, bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The instrument detects the defect it was built for.

    `DocumentView._document_point` is made to report the pointer one line lower
    than it is, which is what a head applied to the glyphs and not to the mouse
    does. The text is drawn where it was; every click lands a line down. The
    probe must say so on the very first gesture, and it must still finish.
    """
    from advtext.ui.document_view import DocumentView

    real = DocumentView._document_point

    def one_line_low(self: Any, origin: Any) -> Point:
        point = real(self, origin)
        return Point(point.x, point.y + sp_from_px(22.0))

    monkeypatch.setattr(DocumentView, "_document_point", one_line_low)
    outcome = probe.run_without_a_window(_SAMPLE.read_text(encoding="utf-8"))
    assert not outcome.passed
    failed = {check.name for check in outcome.checks if not check.ok}
    assert "1 drag over two words, left to right: range" in failed
    assert "1 drag over two words, left to right: text" in failed
    assert "4 double click: text" in failed
    assert "5 triple click: text" in failed


def test_a_view_that_never_copies_fails_on_the_sentinel(
    probe: ModuleType, bundled_fonts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A copy that did not happen cannot pass on what the clipboard already held.

    Gesture 5 selects a line and gesture 6 copies it; in a second run in one
    process the clipboard would still hold a selection from the first, which is
    why it is seeded with a sentinel before each copy. With `_handle_copy`
    removed the sentinel is what comes back, and only the two copy checks fail.
    """
    from advtext.ui.document_view import DocumentView

    monkeypatch.setattr(DocumentView, "_handle_copy", lambda self, layout: None)
    outcome = probe.run_without_a_window(_SAMPLE.read_text(encoding="utf-8"))
    failed = {check.name: check.actual for check in outcome.checks if not check.ok}
    assert set(failed) == {
        "6 ctrl+C: the clipboard holds the line",
        "8 ctrl+C: the clipboard holds all of it, the undrawn part included",
    }
    assert set(failed.values()) == {probe.SENTINEL}


def test_a_document_without_the_opening_line_stops_early_and_does_not_pass(
    probe: ModuleType, bundled_fonts: Any
) -> None:
    """
    A missing target is an error with no checks, and that is not a pass.

    And the watcher is taken off the class again: `DocumentView._handle_mouse`
    is the real method after a run that ended in an error.
    """
    from advtext.ui.document_view import DocumentView

    before = DocumentView._handle_mouse
    outcome = probe.run_without_a_window(PROSE)
    assert isinstance(outcome.error, probe.ProbeError)
    assert "no line starts with" in str(outcome.error)
    assert outcome.checks == ()
    assert not outcome.passed
    assert DocumentView._handle_mouse is before


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


def test_the_probe_passes_in_a_real_window_on_an_xvfb(tmp_path: Path) -> None:
    """
    Fidelity: the real app in a real GLFW window with an OpenGL context, on Xvfb.

    A subprocess, because `immapp.run` owns a process's one GLFW lifetime and
    because the server lives in a namespace this process is not in. The
    assertion is on the script's own report and exit status. About four seconds.

    The shot is written under the repository rather than `tmp_path`: the
    namespace mounts a tmpfs over `/tmp`, so a path there would be written into
    the tmpfs and vanish with it.
    """
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which --xvfb needs")

    done = subprocess.run(
        [sys.executable, str(_SCRIPT), "--xvfb"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=_ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "mouse probe, window:" in done.stdout
    assert "18 of 18 checks passed" in done.stdout
    assert "FAIL" not in done.stdout

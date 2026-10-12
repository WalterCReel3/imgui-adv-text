"""
The frame guard of `tests/conftest.py`: one test that leaves a Dear ImGui frame open is one red.

Run as pytest runs it, in a child, on two throwaway tests that share a
context: the first raises between `begin` and `end`, the second runs a clean
frame. Without the guard the second fails in `new_frame`, and so would every
frame test after it in a real run; with it the second passes and the first
is the only test blamed.

The function the guard calls is also driven directly, in a child of its own
with a context of its own, so that what it unwinds is stated.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

_TWO_TESTS = """
import pytest
from imgui_bundle import imgui


@pytest.fixture(scope="module")
def context():
    made = imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(800.0, 600.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    yield made
    imgui.destroy_context(made)


def test_one_raises_between_begin_and_end(context):
    imgui.new_frame()
    imgui.begin("host")
    imgui.begin_child("child")
    imgui.push_id("left pushed")
    raise KeyError("the code under test fell over")


def test_two_runs_a_clean_frame(context):
    imgui.new_frame()
    imgui.begin("host")
    imgui.text("words")
    imgui.end()
    imgui.render()
"""


def _run(directory: Path, *more: str) -> subprocess.CompletedProcess[str]:
    (directory / "test_two.py").write_text(_TWO_TESTS, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *more, str(directory)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=str(directory),
        env={**os.environ, "PYTHONPATH": str(_ROOT / "tests")},
    )


def test_without_the_guard_the_test_after_a_broken_frame_fails_too(tmp_path: Path) -> None:
    """
    The control: the cascade is real. (No `conftest.py` reaches the directory.)
    """
    pytest.importorskip("imgui_bundle")
    done = _run(tmp_path)
    assert "2 failed" in done.stdout, done.stdout + done.stderr
    assert "Forgot to call Render() or EndFrame()" in done.stdout


def test_with_the_guard_only_the_test_that_left_the_frame_open_is_red(tmp_path: Path) -> None:
    """
    `tests/conftest.py` loaded as a plugin, as it is for every test under `tests/`.

    The broken test fails for its own reason and is the one the guard's
    warning names (an error at its teardown, warnings being errors here);
    the test after it runs its frame and passes.
    """
    pytest.importorskip("imgui_bundle")
    done = _run(tmp_path, "-p", "conftest", "-W", "error")
    out = done.stdout
    assert "1 failed, 1 passed, 1 error" in out, out + done.stderr
    assert "KeyError" in out and "Forgot to call Render()" not in out
    assert "test_one_raises_between_begin_and_end left a Dear ImGui frame open" in out


_DIRECT = """
import json, sys
sys.path.insert(0, sys.argv[1])
import conftest

before_import = conftest.close_open_imgui_frame()
from imgui_bundle import imgui
no_context = conftest.close_open_imgui_frame()
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(800.0, 600.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
io.set_ini_filename("")
context = imgui.get_current_context()
between_frames = conftest.close_open_imgui_frame()
imgui.new_frame()
imgui.begin("host")
imgui.begin_child("child")
imgui.push_id("x")
imgui.push_style_color(imgui.Col_.text.value, 0xFF0000FF)
def state():
    windows, colours = context.current_window_stack.size(), context.color_stack.size()
    return [context.within_frame_scope, windows, colours]
open_ = state()
asserts = io.config_error_recovery_enable_assert
closed = conftest.close_open_imgui_frame()
after = state()
again = conftest.close_open_imgui_frame()
imgui.new_frame(); imgui.begin("host"); imgui.end(); imgui.render()
print("REPORT " + json.dumps({"before_import": before_import, "no_context": no_context,
                  "between_frames": between_frames, "open": open_, "closed": closed,
                  "after": after, "again": again,
                  "asserts_put_back": io.config_error_recovery_enable_assert == asserts,
                  "clean_frame_ran": context.frame_count_ended == context.frame_count}))
"""


def test_the_guard_s_function_unwinds_what_was_pushed_and_ends_the_frame() -> None:
    pytest.importorskip("imgui_bundle")
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_DIRECT), str(_ROOT / "tests")],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    # Dear ImGui writes what it popped to standard output itself, around this line.
    (line,) = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    told = json.loads(line[len("REPORT ") :])
    assert "Missing EndChild()" in done.stdout and "Missing End()" in done.stdout
    # Nothing to do before Dear ImGui is imported, with no context, or between frames.
    assert told["before_import"] is False and told["no_context"] is False
    assert told["between_frames"] is False
    # Mid-frame: the implicit window, the host and its child; one colour pushed.
    assert told["open"] == [True, 3, 1]
    assert told["closed"] is True and told["after"] == [False, 0, 0]
    assert told["again"] is False
    assert told["asserts_put_back"] is True and told["clean_frame_ran"] is True


# ----------------------------------------------------------------------
# A3 (T5-R): the frame helpers of the page tests
# ----------------------------------------------------------------------

_PAGE_HELPER = """
import pytest
from imgui_bundle import imgui


@pytest.fixture(scope="module")
def context():
    made = imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(800.0, 600.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    yield made
    imgui.destroy_context(made)


def _frame(draw):
    # The shape ten helpers of the page tests had until T5-FINAL: the window
    # is ended only when `draw` returns, and the frame is rendered either way.
    imgui.new_frame()
    try:
        imgui.begin("host")
        draw()
        imgui.end()
    finally:
        imgui.render()


def _slip():
    raise KeyError("the page fell over")


def test_one_draw_raises_in_the_helper(context):
    _frame(_slip)


def test_two_runs_a_clean_frame(context):
    _frame(lambda: imgui.text("words"))
"""


def _run_helper(directory: Path, *more: str) -> subprocess.CompletedProcess[str]:
    (directory / "test_helper.py").write_text(_PAGE_HELPER, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *more, str(directory)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=str(directory),
        env={**os.environ, "PYTHONPATH": str(_ROOT / "tests")},
    )


def test_a_helper_that_renders_with_its_window_open_leaves_the_frame_open(tmp_path: Path) -> None:
    """
    The control for A3, with no `conftest.py`: `render()` in the helper's
    `finally` meets a window nobody ended, Dear ImGui's "Missing End()" is
    raised OUT OF `render` (so that, and not the page's `KeyError`, is what
    the test fails with), the frame is never ended, and the next test's
    `new_frame` fails. "Rendered in a finally" is not "the frame was closed".
    """
    pytest.importorskip("imgui_bundle")
    done = _run_helper(tmp_path)
    assert "2 failed" in done.stdout, done.stdout + done.stderr
    assert "Missing End()" in done.stdout
    assert "Forgot to call Render() or EndFrame()" in done.stdout


def test_the_guard_covers_a_helper_that_renders_with_its_window_open(tmp_path: Path) -> None:
    """
    The same two tests under `tests/conftest.py`: the frame the first left
    open (by a `render` that raised) is closed, the second passes, and the
    first is the one blamed. That is the in-process half of A3: the guard
    T5-B1 added covers the page tests' helpers too, whatever their shape.
    """
    pytest.importorskip("imgui_bundle")
    done = _run_helper(tmp_path, "-p", "conftest", "-W", "error")
    out = done.stdout
    assert "1 failed, 1 passed, 1 error" in out, out + done.stderr
    assert "Forgot to call Render()" not in out
    assert "test_one_draw_raises_in_the_helper left a Dear ImGui frame open" in out


def _frames_rendered_with_the_window_open() -> list[str]:
    """
    Every frame under `tests/` that is rendered in a `finally` and ends its window outside one.

    Read from the source, in test functions and in the child scripts kept as
    strings alike: from each `imgui.new_frame()` to the `imgui.render()` that
    follows it, when that `render` is in a `finally:`, the last `imgui.end()`
    before it must be in a `finally:` too (the nearest line above it that is
    indented less is `finally:`). A frame with no `finally` at all is not
    listed: what its `draw` raises leaves as itself and ends the script.
    """
    found: list[str] = []
    for path in sorted((_ROOT / "tests").glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue  # the control above is that shape on purpose
        lines = path.read_text(encoding="utf-8").split("\n")
        for start, line in enumerate(lines):
            if not re.search(r"\bimgui\.new_frame\(\)", line) or line.lstrip().startswith("#"):
                continue
            stop = next(
                (
                    n
                    for n in range(start + 1, min(start + 80, len(lines)))
                    if re.search(r"\bimgui\.render\(\)", lines[n])
                ),
                None,
            )
            if stop is None or lines[stop - 1].strip() != "finally:":
                continue
            ends = [n for n in range(start, stop) if lines[n].strip() == "imgui.end()"]
            if not ends:
                continue
            end = ends[-1]
            indent = len(lines[end]) - len(lines[end].lstrip())
            above = next(
                lines[n].strip()
                for n in range(end - 1, start, -1)
                if lines[n].strip() and len(lines[n]) - len(lines[n].lstrip()) < indent
            )
            if above != "finally:":
                found.append(f"{path.name}:{end + 1}")
    return found


def test_no_frame_helper_renders_a_frame_whose_window_it_did_not_end() -> None:
    """
    A3, the other half: the helpers themselves, in-process and in child scripts.

    A child script has no `conftest.py` behind it, so a helper there that
    catches what `draw` raised, or is called again after it, met a context
    stuck mid-frame; and in either place the failure a reader saw was Dear
    ImGui's "Missing End()" and not the exception the page raised. Each now
    ends its window in an inner `finally`, so what `draw` raises leaves the
    helper as itself with the frame closed. (A `draw` that leaves a CHILD
    window of its own open is still Dear ImGui's complaint: only the guard
    covers that, and only in-process.)
    """
    assert _frames_rendered_with_the_window_open() == []

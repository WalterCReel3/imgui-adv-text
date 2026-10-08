"""
The build stands on this project's own environment, and says so when it cannot.

Three claims, each of which was false or unchecked before the adoption work
(`docs/adoption-plan.md`, phase 0):

1.  Nothing in the build reaches into a sibling project. The `Makefile` used to
    fall back to `/home/wreel/Source/pptmstr/.venv/bin/python` when `./.venv`
    was absent, and `scripts/shot.sh` did the same. pptmstr is meant to depend
    on advtext, which it cannot do while advtext's build depends on it.
2.  Without `./.venv` a target fails, quickly, with a line that names `make
    bootstrap` -- rather than with `make: .venv/bin/python: No such file`.
3.  `pyproject.toml`'s imgui-bundle floor is a version that has the draw-list
    flag the backend sets, and the installed bundle satisfies it.

The `make` runs are real runs of the real `Makefile` with `VENV` pointed at a
directory that does not exist, which is the only way to reach the no-venv
branch from a suite that is itself running inside the venv. Nothing is created
there: the guard refuses before any recipe starts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MAKEFILE = _ROOT / "Makefile"
_PYPROJECT = _ROOT / "pyproject.toml"

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-C", str(_ROOT), "--no-print-directory", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _uncommented(text: str) -> str:
    """
    The lines that do something. A comment may still *mention* the sibling
    project -- the Makefile's header explains what was removed and why -- and
    that is history rather than a dependency.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("path", [_MAKEFILE, _ROOT / "scripts" / "shot.sh"], ids=lambda p: p.name)
def test_no_build_file_reaches_into_the_sibling_project(path: Path) -> None:
    live = _uncommented(path.read_text(encoding="utf-8"))
    assert "pptmstr" not in live, f"{path.name} still names pptmstr outside a comment"
    assert "BORROWED" not in live, f"{path.name} still has the borrowed-interpreter fallback"


@needs_make
@pytest.mark.parametrize(
    "target", ["test", "lint", "format", "typecheck", "svg", "run", "shot", "shot-all", "check"]
)
def test_without_a_venv_a_target_stops_and_points_at_bootstrap(target: str, tmp_path: Path) -> None:
    """
    `format` is in the list and safe to be: the guard is a prerequisite, so the
    recipe that would rewrite the tree is never reached. If the guard were
    missing, `$(BIN)black` would be a path under `tmp_path` that does not exist
    and the run would fail without the message, which is the assertion below.
    """
    absent = tmp_path / "no-such-venv"
    result = _make(target, f"VENV={absent}")
    assert result.returncode != 0, f"`make {target}` succeeded with no venv"
    assert (
        "make bootstrap" in result.stderr
    ), f"`make {target}` failed without saying how to fix it:\n{result.stderr}"
    assert not absent.exists(), "the guard created something where the venv should be"


@needs_make
def test_an_overridden_interpreter_is_not_held_to_the_venv_guard(tmp_path: Path) -> None:
    """
    `tests/test_shot_all.py` reads the `shot-all` recipe with an overridden
    `PY` (a stub that answers `--list` and echoes the rest, since the sidebar
    build made the page list come from `$(PY)` itself; it was `PY=echo`
    before). That must keep working where there is no `./.venv`, or the guard
    has turned a statement about the default interpreter into one about every
    interpreter. `PY=echo` is still what this test passes: with it `--list`
    prints its own arguments, which is a non-empty list, so the recipe runs.
    """
    result = _make("-s", "shot-all", "PY=echo", f"VENV={tmp_path / 'no-such-venv'}")
    assert result.returncode == 0, result.stderr
    assert "scripts/shot.py" in result.stdout


@needs_make
def test_venv_info_reports_the_absence_rather_than_another_interpreter(tmp_path: Path) -> None:
    result = _make("venv-info", f"VENV={tmp_path / 'no-such-venv'}")
    assert result.returncode == 0, result.stderr
    assert "make bootstrap" in result.stdout
    assert "pptmstr" not in result.stdout


def _floor() -> tuple[int, ...]:
    text = _PYPROJECT.read_text(encoding="utf-8")
    found = re.search(r'^\s*"imgui-bundle>=([0-9.]+)"', text, re.MULTILINE)
    assert found, "pyproject.toml no longer states an imgui-bundle floor this test can read"
    return tuple(int(part) for part in found.group(1).split("."))


def test_the_imgui_floor_is_a_release_that_has_the_flag_the_backend_sets() -> None:
    """
    What this measures and what it does not.

    Measured: the installed imgui-bundle has `ImDrawListFlags_.text_no_pixel_snap`
    and is at or above the declared floor. Not measured: that the release
    *below* the floor lacks it -- that half comes from the two changelogs and is
    written up beside the floor in `pyproject.toml`. So a floor set too high
    passes here; a floor set below 1.92.900 fails on the last assertion, which
    is the changelog finding written down as a number so that lowering it is a
    deliberate act.

    It also goes red on the first imgui-bundle that renames the flag, which
    upstream is discussing for 1.93. That is the intended alarm: the fix then is
    in `advtext/backends/imgui_draw.py`, not here.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    assert hasattr(imgui.ImDrawListFlags_, "text_no_pixel_snap"), (
        "the installed imgui-bundle has no ImDrawListFlags_.text_no_pixel_snap; "
        "advtext.backends.imgui_draw.draw would raise on its first call"
    )
    floor = _floor()
    installed = tuple(int(part) for part in metadata.version("imgui-bundle").split(".")[:3])
    assert installed >= floor, f"installed imgui-bundle {installed} is below the floor {floor}"
    assert floor >= (1, 92, 900), (
        f"the floor {floor} is below 1.92.900, the first release on Dear ImGui 1.92.9, "
        "which is where the flag was added"
    )

"""
The build stands on this project's own environment, and says so when it cannot.

Three claims, each of which was false or unchecked before the adoption work
(`docs/adoption-plan.md`, phase 0):

1.  Nothing in the build reaches into a sibling project. The `Makefile` used to
    fall back to `/home/wreel/Source/pptmstr/.venv/bin/python` when `./.venv`
    was absent, and `scripts/shot.sh` did the same. pptmstr is meant to depend
    on imscribe, which it cannot do while imscribe's build depends on it.
2.  Without `./.venv` a target fails, quickly, with a line that names `make
    bootstrap` -- rather than with `make: .venv/bin/python: No such file`.
3.  `pyproject.toml` pins imgui-bundle to exactly one version, and it is the
    installed one.

The `make` runs are real runs of the real `Makefile` with `VENV` pointed at a
directory that does not exist, which is the only way to reach the no-venv
branch from a suite that is itself running inside the venv. Nothing is created
there: the guard refuses before any recipe starts.
"""

from __future__ import annotations

import os
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


# What an outer `make test TYPESET=1` leaves in the environment of the suite it
# runs. A sub-make started here would inherit the opt-in through any of them,
# and these tests are about what the Makefile does when told, not when it
# overhears.
_INHERITED = (
    "MAKEFLAGS",
    "MFLAGS",
    "MAKELEVEL",
    "TYPESET",
    "IMTYPESET_LIBRARY",
    "IMTYPESET_PYTHON",
    "IMTYPESET_COMMIT",
    "IMTYPESET_REF",
    "IMTYPESET_REPO",
    "IMTYPESET_CACHE",
    "IMTYPESET_HEADERS",
    "IMTYPESET_HEADER_CACHE",
    "IMTYPESET_BUNDLE_HEADERS",
)


def _make(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean = {name: value for name, value in os.environ.items() if name not in _INHERITED}
    return subprocess.run(
        ["make", "-C", str(_ROOT), "--no-print-directory", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**clean, **(env or {})},
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
    "target",
    [
        "test",
        "lint",
        "format",
        "typecheck",
        "svg",
        "run",
        "shot",
        "shot-all",
        "check",
        "typeset-lib",
    ],
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


# ---------------------------------------------------------------------------
# imtypeset is opt-in (experimental): `TYPESET=1`, or IMTYPESET_LIBRARY given
# ---------------------------------------------------------------------------

_OPT_IN_TARGETS = ["test", "run", "shot", "shot-all"]


def _recipe(target: str, *args: str, env: dict[str, str] | None = None) -> str:
    """
    What `make <target>` would run, with `echo` as the interpreter and nothing run.
    """
    result = _make("-n", target, "PY=echo", "SHOT_TABS=document", *args, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _a_library(tmp_path: Path) -> Path:
    library = tmp_path / "bundle" / "libimtypeset_bundle.so"
    library.parent.mkdir()
    library.write_bytes(b"not a library; the recipe is only printed")
    return library


@needs_make
@pytest.mark.parametrize("target", _OPT_IN_TARGETS)
def test_without_the_opt_in_no_recipe_mentions_imtypeset(target: str) -> None:
    """
    The default is imscribe as it was: neither variable reaches any command.
    `TYPESET=0` is the default said aloud.
    """
    plain = _recipe(target)
    assert "IMTYPESET" not in plain, plain
    assert _recipe(target, "TYPESET=0") == plain
    assert _recipe(target, "TYPESET=") == plain


@needs_make
def test_the_default_test_recipe_is_what_it_was() -> None:
    assert _recipe("test").strip() == "echo -m pytest -q"


@needs_make
@pytest.mark.parametrize("target", _OPT_IN_TARGETS)
def test_typeset_1_puts_both_variables_in_front_and_changes_nothing_else(
    target: str, tmp_path: Path
) -> None:
    """
    Two assignments before the command, and the command as it was -- which is
    why `tests/test_shot_all.py` can read the shot-all recipe in either run.
    `IMTYPESET_PYTHON` and not `PYTHONPATH`: `imscribe/typesetter.py` says why.
    """
    library = _a_library(tmp_path)
    opted = _recipe(target, "TYPESET=1", f"IMTYPESET_BUNDLE={library.parent}", "IMTYPESET_ROOT=/it")
    prefix = f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON=/it/python "
    assert prefix in opted, opted
    assert opted.replace(prefix, "") == _recipe(target)


@needs_make
def test_a_library_named_in_the_environment_is_the_opt_in_too(tmp_path: Path) -> None:
    library = _a_library(tmp_path)
    opted = _recipe("test", "IMTYPESET_ROOT=/it", env={"IMTYPESET_LIBRARY": str(library)})
    assert opted.strip() == (
        f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON=/it/python echo -m pytest -q"
    )


@needs_make
@pytest.mark.parametrize("target", _OPT_IN_TARGETS)
def test_asking_for_a_library_that_is_not_built_stops_and_says_how_to_build_it(
    target: str, tmp_path: Path
) -> None:
    """
    Not a suite that runs and quietly skips everything that was asked for.
    """
    result = _make(target, "PY=echo", "TYPESET=1", f"IMTYPESET_BUNDLE={tmp_path / 'absent'}")
    assert result.returncode != 0, f"`make {target} TYPESET=1` ran with no library"
    assert "make typeset-lib" in result.stderr, result.stderr
    assert not (tmp_path / "absent").exists()


@needs_make
def test_typeset_lib_builds_from_the_named_checkout_for_this_interpreter(tmp_path: Path) -> None:
    """
    Read, not run: the build takes half a minute and a compiler. What is held
    is where it reads from, where it writes, and which interpreter it is for.
    """
    checkout = tmp_path / "imtypeset"
    script = checkout / "python" / "host" / "build_bundle_library.sh"
    script.parent.mkdir(parents=True)
    script.write_text("exit 0\n", encoding="utf-8")
    out = tmp_path / "out"
    result = _make(
        "-n",
        "typeset-lib",
        "PY=/some/python",
        f"IMTYPESET_ROOT={checkout}",
        f"IMTYPESET_BUNDLE={out}",
    )
    assert result.returncode == 0, result.stderr
    assert f"IMTYPESET_BUNDLE_OUT={out}.building sh {script}" in result.stdout
    assert '"/some/python"' in result.stdout
    assert not out.exists() and not Path(f"{out}.building").exists(), "-n wrote something"
    missing = _make("typeset-lib", "PY=echo", f"IMTYPESET_ROOT={tmp_path / 'nowhere'}")
    assert missing.returncode != 0 and "IMTYPESET_ROOT" in missing.stderr


# ---------------------------------------------------------------------------
# The library and the package that calls it travel together
#
# 2026-10-10: the sibling checkout's package began calling a function the
# library built that afternoon did not export, and every with-library test
# failed at import. `make typeset-lib` now leaves a copy of the package beside
# the library, and the opt-in prefers that copy.
# ---------------------------------------------------------------------------


def _a_snapshot(library: Path) -> Path:
    snapshot = library.parent / "pysnap"
    (snapshot / "imtypeset").mkdir(parents=True)
    (snapshot / "imtypeset" / "__init__.py").write_text("", encoding="utf-8")
    return snapshot


@needs_make
@pytest.mark.parametrize("target", _OPT_IN_TARGETS)
def test_typeset_1_prefers_the_package_snapshot_beside_the_library(
    target: str, tmp_path: Path
) -> None:
    library = _a_library(tmp_path)
    snapshot = _a_snapshot(library)
    opted = _recipe(target, "TYPESET=1", f"IMTYPESET_BUNDLE={library.parent}", "IMTYPESET_ROOT=/it")
    prefix = f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON={snapshot} "
    assert prefix in opted, opted
    assert "/it/python" not in opted
    assert opted.replace(prefix, "") == _recipe(target)


@needs_make
def test_the_snapshot_is_the_one_beside_the_library_that_was_named(tmp_path: Path) -> None:
    """
    Beside IMTYPESET_LIBRARY, wherever that is -- not beside the default
    bundle, which may hold a different build. And an empty `pysnap` (no
    package in it) is not a snapshot.
    """
    library = _a_library(tmp_path)
    snapshot = _a_snapshot(library)
    elsewhere = tmp_path / "other"
    (elsewhere / "pysnap").mkdir(parents=True)
    other = elsewhere / "libimtypeset_bundle.so"
    other.write_bytes(b"")
    named = _recipe("test", "IMTYPESET_ROOT=/it", env={"IMTYPESET_LIBRARY": str(library)})
    assert named.strip() == (
        f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON={snapshot} echo -m pytest -q"
    )
    bare = _recipe(
        "test",
        "IMTYPESET_ROOT=/it",
        f"IMTYPESET_BUNDLE={library.parent}",
        env={"IMTYPESET_LIBRARY": str(other)},
    )
    assert (
        bare.strip() == f"IMTYPESET_LIBRARY={other} IMTYPESET_PYTHON=/it/python echo -m pytest -q"
    )


@needs_make
@pytest.mark.parametrize("how", ["command line", "environment"])
def test_a_caller_s_own_package_directory_wins_over_both_defaults(how: str, tmp_path: Path) -> None:
    library = _a_library(tmp_path)
    args = ["TYPESET=1", f"IMTYPESET_BUNDLE={library.parent}", "IMTYPESET_ROOT=/it"]
    mine = {"IMTYPESET_PYTHON": "/mine/python"}
    expected = f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON=/mine/python echo -m pytest -q"
    for with_snapshot in (False, True):
        if with_snapshot:
            _a_snapshot(library)
        if how == "command line":
            opted = _recipe("test", *args, "IMTYPESET_PYTHON=/mine/python")
        else:
            opted = _recipe("test", *args, env=mine)
        assert opted.strip() == expected, (with_snapshot, opted)


_BUILD_OK = """\
set -eu
mkdir -p "$IMTYPESET_BUNDLE_OUT/obj"
echo "$2" > "$IMTYPESET_BUNDLE_OUT/obj/python"
echo new > "$IMTYPESET_BUNDLE_OUT/libimtypeset_bundle.so"
echo stamp > "$IMTYPESET_BUNDLE_OUT/libimtypeset_bundle.so.gate"
"""


def _a_checkout(tmp_path: Path, build: str, package: str = "LOADED = True\n") -> Path:
    """
    A stand-in for the sibling checkout: a build script that takes a moment
    instead of a compiler, and a package with a `__pycache__` in it.
    """
    checkout = tmp_path / "imtypeset"
    script = checkout / "python" / "host" / "build_bundle_library.sh"
    script.parent.mkdir(parents=True)
    script.write_text(build, encoding="utf-8")
    package_dir = checkout / "python" / "imtypeset"
    (package_dir / "__pycache__").mkdir(parents=True)
    (package_dir / "__pycache__" / "__init__.cpython-311.pyc").write_bytes(b"stale")
    (package_dir / "__init__.py").write_text(package, encoding="utf-8")
    (package_dir / "_capi.py").write_text("# declarations\n", encoding="utf-8")
    return checkout


def _an_installed_pair(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    (bundle / "pysnap" / "imtypeset").mkdir(parents=True)
    (bundle / "pysnap" / "imtypeset" / "__init__.py").write_text("# old\n", encoding="utf-8")
    (bundle / "libimtypeset_bundle.so").write_text("old\n", encoding="utf-8")
    (bundle / "BUILT-FROM").write_text("old\n", encoding="utf-8")
    return bundle


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _build(checkout: Path, bundle: Path | str, *more: str) -> subprocess.CompletedProcess[str]:
    import sys

    return _make(
        "typeset-lib",
        f"PY={sys.executable}",
        f"IMTYPESET_ROOT={checkout}",
        f"IMTYPESET_BUNDLE={bundle}",
        *more,
    )


@needs_make
def test_typeset_lib_leaves_the_library_its_package_and_where_they_came_from(
    tmp_path: Path,
) -> None:
    """
    Run, with a stand-in build script: the recipe around the build is what is
    held here, and it is the part this tree owns.
    """
    import sys

    checkout = _a_checkout(tmp_path, _BUILD_OK)
    bundle = _an_installed_pair(tmp_path)
    (bundle / "left-over").write_text("from the build before\n", encoding="utf-8")
    result = _build(checkout, bundle)
    assert result.returncode == 0, result.stderr
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "new\n"
    snapshot = bundle / "pysnap" / "imtypeset"
    assert (snapshot / "__init__.py").read_text(encoding="utf-8") == "LOADED = True\n"
    assert sorted(path.name for path in snapshot.iterdir()) == ["__init__.py", "_capi.py"]
    assert not list(bundle.rglob("__pycache__")), "the snapshot carries bytecode"
    # Whole, not merged: nothing of the build before survives a successful one.
    assert not (bundle / "left-over").exists()
    # Nothing here removes `<library>.gate` (imtypeset's T3): what a script
    # from before 03b5cd4 wrote while staging is that package's to find stale.
    assert (bundle / "libimtypeset_bundle.so.gate").read_text(encoding="utf-8") == "stamp\n"
    # ... and a script that writes no LIBRARY file gets none made for it.
    assert not (bundle / "LIBRARY").exists()
    assert (bundle / "obj" / "python").read_text(encoding="utf-8").strip() == sys.executable
    built_from = (bundle / "BUILT-FROM").read_text(encoding="utf-8")
    assert f"imtypeset: {checkout}\n" in built_from
    assert re.search(r"^commit: \S", built_from, re.MULTILINE), built_from
    assert re.search(r"^uncommitted paths: \S", built_from, re.MULTILINE), built_from
    assert re.search(r"^date: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", built_from, re.MULTILINE)
    assert built_from in result.stdout, "the target does not say what it built from"
    assert result.stdout.splitlines()[-1].startswith(
        f"use it with: IMTYPESET_LIBRARY={bundle}/libimtypeset_bundle.so "
        f"IMTYPESET_PYTHON={bundle}/pysnap "
    )
    assert not Path(f"{bundle}.building").exists()
    assert not Path(f"{bundle}.previous").exists()
    # And the opt-in now finds the copy rather than the checkout.
    opted = _recipe("test", "TYPESET=1", f"IMTYPESET_BUNDLE={bundle}", f"IMTYPESET_ROOT={checkout}")
    assert f"IMTYPESET_PYTHON={bundle / 'pysnap'} " in opted, opted


@needs_make
def test_typeset_lib_builds_where_there_was_no_bundle(tmp_path: Path) -> None:
    checkout = _a_checkout(tmp_path, _BUILD_OK)
    bundle = tmp_path / "build" / "bundle"
    result = _build(checkout, bundle)
    assert result.returncode == 0, result.stderr
    assert (bundle / "libimtypeset_bundle.so").exists()
    assert (bundle / "pysnap" / "imtypeset" / "__init__.py").exists()


@needs_make
@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_built_from_names_the_commit_and_counts_what_was_not_committed(tmp_path: Path) -> None:
    checkout = _a_checkout(tmp_path, _BUILD_OK)

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(checkout), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return done.stdout.strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "--no-gpg-sign", "-m", "a checkout")
    (checkout / "one").write_text("", encoding="utf-8")
    (checkout / "two").write_text("", encoding="utf-8")
    result = _build(checkout, tmp_path / "bundle")
    assert result.returncode == 0, result.stderr
    built_from = (tmp_path / "bundle" / "BUILT-FROM").read_text(encoding="utf-8")
    assert f"commit: {git('rev-parse', 'HEAD')}\n" in built_from, built_from
    assert "uncommitted paths: 2\n" in built_from, built_from


@needs_make
@pytest.mark.parametrize(
    ("build", "package"),
    [
        # The compiler fails after writing half of what it writes.
        (_BUILD_OK + "exit 1\n", "LOADED = True\n"),
        # The build succeeds and the package of that moment does not load
        # against it: the failure of 2026-10-10, caught before it is installed.
        (_BUILD_OK, "raise ImportError('undefined symbol: ImTypeset_Something')\n"),
    ],
    ids=["the build fails", "the pair does not load"],
)
def test_a_failed_typeset_lib_leaves_the_installed_pair_as_it_was(
    build: str, package: str, tmp_path: Path
) -> None:
    checkout = _a_checkout(tmp_path, build, package)
    bundle = _an_installed_pair(tmp_path)
    before = _tree(bundle)
    result = _build(checkout, bundle)
    assert result.returncode != 0, result.stdout
    assert _tree(bundle) == before
    assert not Path(f"{bundle}.previous").exists()


# ---------------------------------------------------------------------------
# Tranche 3 (T3-D): a named commit, and the three ways the recipe above failed
# late or paired wrongly. Each of the four was first seen to fail against the
# Makefile as SW-0 left it.
# ---------------------------------------------------------------------------

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout.strip()


def _commit_all(where: Path, message: str) -> str:
    if not (where / ".git").exists():
        _git(where, "init", "-q")
    _git(where, "add", "-A")
    _git(where, "commit", "-q", "--no-gpg-sign", "-m", message)
    return _git(where, "rev-parse", "HEAD")


def _field(built_from: str, name: str) -> str:
    found = re.search(rf"^{re.escape(name)}: (.*)$", built_from, re.MULTILINE)
    assert found, f"no `{name}:` line in\n{built_from}"
    return found.group(1)


@needs_make
@needs_git
def test_built_from_never_describes_a_repository_that_merely_encloses_the_checkout(
    tmp_path: Path,
) -> None:
    """
    2026-10-11: an extract of imtypeset lay inside imscribe's repository, and
    BUILT-FROM gave imscribe's HEAD and imscribe's uncommitted paths as
    imtypeset's.
    """
    outer = tmp_path / "outer"
    outer.mkdir()
    checkout = _a_checkout(outer, _BUILD_OK)
    (outer / "theirs").write_text("", encoding="utf-8")
    enclosing = _commit_all(outer, "the repository around it")
    result = _build(checkout, tmp_path / "bundle")
    assert result.returncode == 0, result.stderr
    built_from = (tmp_path / "bundle" / "BUILT-FROM").read_text(encoding="utf-8")
    assert enclosing not in built_from, built_from
    assert "not a git checkout" in _field(built_from, "commit")
    assert _field(built_from, "uncommitted paths") == "unknown"


@needs_make
@needs_git
def test_typeset_lib_builds_a_named_commit_and_not_the_working_tree(tmp_path: Path) -> None:
    """
    The commit's script, sources and package, taken out of the checkout's
    object store; the working tree, which has moved on in every one of those,
    is neither read nor written.
    """
    checkout = _a_checkout(tmp_path, _BUILD_OK, "COMMITTED = 1\n")
    (checkout / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    first = _commit_all(checkout, "the commit to build from")
    _git(checkout, "tag", "named")
    script = checkout / "python" / "host" / "build_bundle_library.sh"
    package = checkout / "python" / "imtypeset" / "__init__.py"
    package.write_text("COMMITTED = 2\n", encoding="utf-8")
    script.write_text(_BUILD_OK.replace("echo new", "echo second"), encoding="utf-8")
    second = _commit_all(checkout, "a later commit")
    # ... and a working tree that would fail the build and the import alike.
    package.write_text("raise ImportError('the working tree was read')\n", encoding="utf-8")
    script.write_text("exit 1\n", encoding="utf-8")
    (checkout / "untracked").write_text("", encoding="utf-8")
    before = _tree(checkout)

    bundle = tmp_path / "bundle"
    result = _build(checkout, bundle, "IMTYPESET_COMMIT=named")
    assert result.returncode == 0, result.stderr
    assert _tree(checkout) == before, "the build wrote in the checkout"
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "new\n"
    snapshot = bundle / "pysnap" / "imtypeset" / "__init__.py"
    assert snapshot.read_text(encoding="utf-8") == "COMMITTED = 1\n"
    built_from = (bundle / "BUILT-FROM").read_text(encoding="utf-8")
    assert _field(built_from, "imtypeset") == str(checkout)
    assert _field(built_from, "commit") == first, "the full hash, resolved from the name"
    assert _field(built_from, "uncommitted paths") == "0 (an archive of a commit)"
    assert _field(built_from, "by") == "make typeset-lib IMTYPESET_COMMIT=named"
    assert built_from in result.stdout
    # The extract is installed with the pair, is the commit, and is not a checkout.
    extract = bundle / "src"
    assert (extract / "python" / "imtypeset" / "__init__.py").read_text() == "COMMITTED = 1\n"
    assert not (extract / ".git").exists() and not (extract / "untracked").exists()
    assert not Path(f"{extract}.tar").exists()

    # An abbreviated hash of the later commit replaces all three.
    result = _build(checkout, bundle, f"IMTYPESET_COMMIT={second[:10]}")
    assert result.returncode == 0, result.stderr
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "second\n"
    assert snapshot.read_text(encoding="utf-8") == "COMMITTED = 2\n"
    assert _field((bundle / "BUILT-FROM").read_text(encoding="utf-8"), "commit") == second
    assert (extract / "python" / "imtypeset" / "__init__.py").read_text() == "COMMITTED = 2\n"
    assert _tree(checkout) == before


@needs_make
@needs_git
def test_the_extract_s_neighbours_are_named_from_the_checkout(tmp_path: Path) -> None:
    """
    The build script finds the Dear ImGui Bundle checkout and a Dear ImGui
    clone beside its own checkout by default. An extract in the bundle has
    neither beside it, so both are handed over, from IMTYPESET_ROOT.
    """
    build = (
        _BUILD_OK + 'echo "$1|$IMTYPESET_IMGUI_CLONE" > "$IMTYPESET_BUNDLE_OUT/obj/neighbours"\n'
    )
    checkout = _a_checkout(tmp_path, build)
    _commit_all(checkout, "a checkout")
    bundle = tmp_path / "bundle"
    result = _build(checkout, bundle, "IMTYPESET_COMMIT=HEAD")
    assert result.returncode == 0, result.stderr
    neighbours = (bundle / "obj" / "neighbours").read_text(encoding="utf-8").strip()
    assert neighbours == f"{checkout}/../imgui_bundle|{checkout}/../imgui"


@needs_make
@needs_git
@pytest.mark.parametrize("what", ["no such commit", "not a repository", "inside another's"])
def test_a_commit_that_cannot_be_taken_stops_before_anything_is_touched(
    what: str, tmp_path: Path
) -> None:
    outer = tmp_path / "outer"
    outer.mkdir()
    checkout = _a_checkout(outer, _BUILD_OK)
    if what == "no such commit":
        _commit_all(checkout, "a checkout")
    elif what == "inside another's":
        # HEAD resolves here -- in the repository around the checkout. That is
        # not a commit of imtypeset, and building it would say that it was.
        _commit_all(outer, "the repository around it")
    bundle = _an_installed_pair(tmp_path)
    before = _tree(bundle)
    commit = "no-such-rev" if what == "no such commit" else "HEAD"
    result = _build(checkout, bundle, f"IMTYPESET_COMMIT={commit}")
    assert result.returncode != 0, result.stdout
    assert "IMTYPESET_COMMIT" in result.stderr, result.stderr
    assert _tree(bundle) == before
    assert not Path(f"{bundle}.building").exists()


# ---------------------------------------------------------------------------
# From a repository by URL, at a named ref (IMTYPESET_REF)
#
# The default IMTYPESET_REPO is GitHub, which the sessions that wrote this
# cannot reach, so every test here hands the recipe a `file://` URL of a
# repository it has just made. What that does and does not show about the real
# remote is listed in `.concerns/L1-PKG--builder--result.md`.
# ---------------------------------------------------------------------------


def _a_remote(tmp_path: Path) -> tuple[Path, str, str]:
    """
    A repository to fetch from: two commits that build differently, the first
    tagged twice (`named`, and `annotated` with a tag object), and a working
    tree that has moved on to something that builds nothing.
    """
    remote = _a_checkout(tmp_path, _BUILD_OK, "COMMITTED = 1\n")
    (remote / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    first = _commit_all(remote, "the commit to build from")
    _git(remote, "tag", "named")
    _git(remote, "tag", "-a", "-m", "a release", "annotated")
    script = remote / "python" / "host" / "build_bundle_library.sh"
    package = remote / "python" / "imtypeset" / "__init__.py"
    package.write_text("COMMITTED = 2\n", encoding="utf-8")
    script.write_text(_BUILD_OK.replace("echo new", "echo second"), encoding="utf-8")
    second = _commit_all(remote, "a later commit")
    package.write_text("raise ImportError('the working tree was read')\n", encoding="utf-8")
    script.write_text("exit 1\n", encoding="utf-8")
    return remote, first, second


def _fetch_and_build(
    tmp_path: Path, url: str, ref: str, *more: str
) -> subprocess.CompletedProcess[str]:
    """
    `make typeset-lib IMTYPESET_REF=...` with no checkout of imtypeset to fall back on.
    """
    import sys

    return _make(
        "typeset-lib",
        f"PY={sys.executable}",
        f"IMTYPESET_ROOT={tmp_path / 'no-sibling-checkout'}",
        f"IMTYPESET_BUNDLE={tmp_path / 'bundle'}",
        f"IMTYPESET_CACHE={tmp_path / 'cache'}",
        f"IMTYPESET_REPO={url}",
        f"IMTYPESET_REF={ref}",
        *more,
    )


@needs_make
def test_without_a_ref_the_build_fetches_nothing_and_names_no_repository(tmp_path: Path) -> None:
    """
    `IMTYPESET_REPO` has a default, and a default must not be an opt-in: with
    no ref the recipe is the sibling checkout's, as it was.
    """
    checkout = _a_checkout(tmp_path, _BUILD_OK)
    for more in ((), ("IMTYPESET_COMMIT=HEAD",), ("IMTYPESET_REF=",)):
        result = _make("-n", "typeset-lib", "PY=echo", f"IMTYPESET_ROOT={checkout}", *more)
        assert result.returncode == 0, result.stderr
        for word in ("fetch", "github.com", "imtypeset-cache", "refs/typeset-lib"):
            assert word not in result.stdout, (more, word)
    assert _make("-n", "typeset-lib", "PY=echo", f"IMTYPESET_ROOT={checkout}").stdout == (
        _make("-n", "typeset-lib", "PY=echo", f"IMTYPESET_ROOT={checkout}", "IMTYPESET_REF=").stdout
    )


@needs_make
def test_the_default_repository_is_imtypeset_on_github() -> None:
    """
    Read, not run: nothing here reaches GitHub. What is held is the URL the
    fetch would be given and that it cannot stop at a prompt.
    """
    result = _make("-n", "typeset-lib", "PY=echo", "IMTYPESET_REF=v0.0.0")
    assert result.returncode == 0, result.stderr
    fetch = [line for line in result.stdout.splitlines() if " fetch " in line]
    assert len(fetch) == 1, result.stdout
    assert fetch[0].startswith("GIT_TERMINAL_PROMPT=0 git --git-dir="), fetch[0]
    asked = '"https://github.com/WalterCReel3/imtypeset.git" "v0.0.0"'
    command = fetch[0].split(" || ")[0]
    assert command.endswith(f" fetch --quiet --depth 1 --no-tags {asked}"), fetch[0]
    assert f'--git-dir="{_ROOT}/build/imtypeset-cache"' in fetch[0]


@needs_make
@needs_git
@pytest.mark.parametrize("ref", ["named", "annotated", "hash", "main"])
def test_typeset_lib_fetches_a_ref_from_a_url_and_builds_that_commit(
    ref: str, tmp_path: Path
) -> None:
    """
    A tag, a tag object, a full hash and a branch, each resolved to the hash
    that BUILT-FROM then names; the remote's working tree is not what is
    built, the remote is not written to, and no sibling checkout is read.
    """
    remote, first, second = _a_remote(tmp_path)
    if ref == "main":
        _git(remote, "branch", "-M", "main")
    before = _tree(remote)
    url = f"file://{remote}"
    given = first if ref == "hash" else ref
    expected = second if ref == "main" else first

    result = _fetch_and_build(tmp_path, url, given)
    assert result.returncode == 0, result.stderr
    assert _tree(remote) == before, "the build wrote in the repository it fetched from"
    bundle = tmp_path / "bundle"
    built = "second\n" if ref == "main" else "new\n"
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == built
    snapshot = (bundle / "pysnap" / "imtypeset" / "__init__.py").read_text(encoding="utf-8")
    assert snapshot == ("COMMITTED = 2\n" if ref == "main" else "COMMITTED = 1\n")
    built_from = (bundle / "BUILT-FROM").read_text(encoding="utf-8")
    assert _field(built_from, "imtypeset") == url
    assert _field(built_from, "ref") == given
    assert _field(built_from, "commit") == expected, "the full hash the ref resolved to"
    assert _field(built_from, "uncommitted paths") == "0 (an archive of a commit)"
    assert _field(built_from, "by") == f"make typeset-lib IMTYPESET_REF={given}"
    assert _field(built_from, "library cksum")
    assert built_from in result.stdout
    extract = bundle / "src"
    assert (extract / "python" / "imtypeset" / "__init__.py").read_text() == snapshot
    assert not (extract / ".git").exists() and not Path(f"{extract}.tar").exists()
    assert not (tmp_path / "no-sibling-checkout").exists()
    cache = tmp_path / "cache"
    assert (cache / "HEAD").is_file(), "the cache is a bare repository"
    kept = _git(cache, "for-each-ref", "--format=%(objectname)", "refs/typeset-lib").split()
    assert kept == [expected], "the cache does not keep what was asked for under a ref of its own"


@needs_make
@needs_git
def test_a_second_ref_is_fetched_into_the_same_cache_and_replaces_the_pair(tmp_path: Path) -> None:
    remote, first, second = _a_remote(tmp_path)
    url = f"file://{remote}"
    assert _fetch_and_build(tmp_path, url, "named").returncode == 0
    result = _fetch_and_build(tmp_path, url, second)
    assert result.returncode == 0, result.stderr
    bundle = tmp_path / "bundle"
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "second\n"
    assert _field((bundle / "BUILT-FROM").read_text(encoding="utf-8"), "commit") == second
    # ... and back, from what the cache already holds plus one more fetch.
    result = _fetch_and_build(tmp_path, url, "named")
    assert result.returncode == 0, result.stderr
    assert _field((bundle / "BUILT-FROM").read_text(encoding="utf-8"), "commit") == first


@needs_make
@needs_git
def test_with_a_ref_the_neighbours_are_looked_for_beside_this_repository(tmp_path: Path) -> None:
    """
    With a sibling imtypeset the Dear ImGui Bundle checkout and the Dear ImGui
    clone are looked for beside IT. A machine that fetches imtypeset has no
    such sibling, and a path through a directory that does not exist resolves
    to nothing; so both are looked for beside this repository, or where the
    caller says.
    """
    build = (
        _BUILD_OK + 'echo "$1|$IMTYPESET_IMGUI_CLONE" > "$IMTYPESET_BUNDLE_OUT/obj/neighbours"\n'
    )
    remote = _a_checkout(tmp_path, build)
    _commit_all(remote, "a repository")
    _git(remote, "tag", "named")
    url = f"file://{remote}"
    result = _fetch_and_build(tmp_path, url, "named")
    assert result.returncode == 0, result.stderr
    neighbours = tmp_path / "bundle" / "obj" / "neighbours"
    beside = _ROOT.parent
    assert neighbours.read_text(encoding="utf-8").strip() == f"{beside}/imgui_bundle|{beside}/imgui"
    result = _fetch_and_build(
        tmp_path, url, "named", "IMGUI_BUNDLE_CHECKOUT=/a/bundle", "IMTYPESET_IMGUI_CLONE=/a/clone"
    )
    assert result.returncode == 0, result.stderr
    assert neighbours.read_text(encoding="utf-8").strip() == "/a/bundle|/a/clone"


@needs_make
@needs_git
@pytest.mark.parametrize(
    "what",
    [
        "no such ref",
        "an abbreviated hash",
        "no repository there",
        "a ref that is no commit",
        "a commit as well",
        "no build script",
    ],
)
def test_a_ref_that_cannot_be_fetched_stops_before_anything_is_touched(
    what: str, tmp_path: Path
) -> None:
    """
    No repository at the URL is what no network looks like from here: the
    fetch fails. In every case the installed pair is byte for byte what it
    was, nothing is left staged, and the line says which variable to change.

    The pair that is installed was itself fetched, so the cache already holds
    a commit when the fetch fails: what was fetched LAST time must not be
    what gets built this time.
    """
    remote, first, second = _a_remote(tmp_path)
    url, ref, more = f"file://{remote}", "named", ()
    if what == "no such ref":
        ref = "v9.9.9"
    elif what == "an abbreviated hash":
        ref = first[:10]
    elif what == "no repository there":
        url = f"file://{tmp_path / 'nowhere'}"
    elif what == "a ref that is no commit":
        blob = _git(remote, "rev-parse", "named:python/imtypeset/_capi.py")
        _git(remote, "tag", "a-file", blob)
        ref = "a-file"
    elif what == "a commit as well":
        more = ("IMTYPESET_COMMIT=HEAD",)
    else:
        bare = tmp_path / "elsewhere"
        bare.mkdir()
        (bare / "README").write_text("not imtypeset\n", encoding="utf-8")
        _commit_all(bare, "another project")
        _git(bare, "tag", "named")
        url = f"file://{bare}"
    if what == "a commit as well":
        bundle = _an_installed_pair(tmp_path)
    else:
        bundle = tmp_path / "bundle"
        assert _fetch_and_build(tmp_path, f"file://{remote}", second).returncode == 0
    before = _tree(bundle)
    result = _fetch_and_build(tmp_path, url, ref, *more)
    assert result.returncode != 0, result.stdout
    assert ref in result.stderr and url in result.stderr, result.stderr
    if what in ("no such ref", "an abbreviated hash", "no repository there"):
        assert "could not be fetched" in result.stderr and "IMTYPESET_COMMIT" in result.stderr
        assert "untouched" in result.stderr
    elif what == "a ref that is no commit":
        assert "is not a commit" in result.stderr, result.stderr
    elif what == "a commit as well":
        assert "name two sources" in result.stderr, result.stderr
        assert not (tmp_path / "cache").exists(), "it fetched before refusing"
    else:
        assert "has no python/host/build_bundle_library.sh" in result.stderr, result.stderr
    assert _tree(bundle) == before
    if what != "no build script":
        assert not Path(f"{bundle}.building").exists()


@needs_make
@pytest.mark.parametrize("given", ["{}/", "{}//", "build/../{}/"], ids=["slash", "two", "dots"])
def test_a_bundle_directory_given_with_a_trailing_slash_is_the_same_directory(
    given: str, tmp_path: Path
) -> None:
    """
    `IMTYPESET_BUNDLE=dir/` staged in `dir/.building`, inside the bundle, and
    the build failed at the last rename after doing all the work.
    """
    checkout = _a_checkout(tmp_path, _BUILD_OK)
    bundle = _an_installed_pair(tmp_path)
    spelled = f"{tmp_path}/{given.format('bundle')}" if "build" in given else given.format(bundle)
    result = _build(checkout, spelled)
    assert result.returncode == 0, result.stderr
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "new\n"
    assert sorted(path.name for path in bundle.iterdir() if path.name.startswith(".")) == []
    assert not Path(f"{bundle}.building").exists() and not Path(f"{bundle}.previous").exists()
    opted = _recipe("test", "TYPESET=1", f"IMTYPESET_BUNDLE={spelled}", "IMTYPESET_ROOT=/it")
    assert opted.strip() == (
        f"IMTYPESET_LIBRARY={bundle}/libimtypeset_bundle.so "
        f"IMTYPESET_PYTHON={bundle}/pysnap echo -m pytest -q"
    )


def _an_interpreter_that_reports(tmp_path: Path) -> Path:
    """
    `$(PY)` for a run that goes all the way: the real interpreter for the
    build's import of the pair (`-P -B -c ...`), and for everything else --
    `-m pytest`, a script -- a line saying which pair it would have been
    handed, without running a suite or opening a window inside one.
    """
    import sys

    stub = tmp_path / "python-stub"
    stub.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "-P" ]; then exec "{sys.executable}" "$@"; fi\n'
        'echo "suite: $IMTYPESET_LIBRARY $IMTYPESET_PYTHON"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _suite(tmp_path: Path, bundle: Path, *more: str) -> subprocess.CompletedProcess[str]:
    """`make ... TYPESET=1` on `bundle`, with the interpreter that reports."""
    stub = tmp_path / "python-stub"
    if not stub.exists():
        _an_interpreter_that_reports(tmp_path)
    return _make(
        *more,
        f"PY={stub}",
        "TYPESET=1",
        f"IMTYPESET_BUNDLE={bundle}",
        f"IMTYPESET_ROOT={tmp_path / 'imtypeset'}",
    )


@needs_make
@pytest.mark.parametrize("before", ["no bundle", "a library and no snapshot"])
def test_building_and_testing_in_one_invocation_uses_the_pair_just_built(
    before: str, tmp_path: Path
) -> None:
    """
    `make typeset-lib test TYPESET=1`. Which package goes with the library is
    settled when the Makefile is read, before the build; with no snapshot yet
    the suite got the new library and the checkout's live package.
    """
    _a_checkout(tmp_path, _BUILD_OK)
    bundle = tmp_path / "bundle"
    if before != "no bundle":
        bundle.mkdir()
        (bundle / "libimtypeset_bundle.so").write_text("old\n", encoding="utf-8")
    result = _suite(tmp_path, bundle, "typeset-lib", "test")
    assert result.returncode == 0, result.stderr
    assert (bundle / "libimtypeset_bundle.so").read_text(encoding="utf-8") == "new\n"
    assert result.stdout.splitlines()[-1] == (
        f"suite: {bundle}/libimtypeset_bundle.so {bundle}/pysnap"
    )


@needs_make
def test_a_library_replaced_under_its_snapshot_is_refused_and_a_built_pair_never_is(
    tmp_path: Path,
) -> None:
    """
    Both directions, on one bundle: the pair as `make typeset-lib` left it
    runs, the same directory after something else wrote the library does not,
    and building again runs again.
    """
    checkout = _a_checkout(tmp_path, _BUILD_OK)
    bundle = tmp_path / "bundle"
    assert _build(checkout, bundle).returncode == 0
    library = bundle / "libimtypeset_bundle.so"
    built_from = (bundle / "BUILT-FROM").read_text(encoding="utf-8")
    assert re.fullmatch(r"\d+ \d+", _field(built_from, "library cksum")), built_from
    report = f"suite: {library} {bundle}/pysnap"

    for target in _OPT_IN_TARGETS:
        good = _suite(tmp_path, bundle, target, "SHOT_TABS=document")
        assert good.returncode == 0, (target, good.stderr)
    assert _suite(tmp_path, bundle, "test").stdout.splitlines()[-1] == report
    # What the first import leaves beside the library does not make it stale,
    # and neither does a new modification time on the same bytes.
    (bundle / "libimtypeset_bundle.so.gate").write_text("stamp\n", encoding="utf-8")
    library.write_bytes(library.read_bytes())
    assert _suite(tmp_path, bundle, "test").stdout.splitlines()[-1] == report

    # The build script run by hand into the same directory: a new library,
    # the old snapshot, the old BUILT-FROM.
    library.write_text("built by hand\n", encoding="utf-8")
    for target in _OPT_IN_TARGETS:
        stale = _suite(tmp_path, bundle, target, "SHOT_TABS=document")
        assert stale.returncode != 0, f"`make {target} TYPESET=1` ran a stale pair"
        assert "suite:" not in stale.stdout
        assert "make typeset-lib" in stale.stderr and str(library) in stale.stderr, stale.stderr
    # Named through the environment instead of TYPESET=1: the same answer.
    named = _make("test", "PY=echo", env={"IMTYPESET_LIBRARY": str(library)})
    assert named.returncode != 0 and "make typeset-lib" in named.stderr

    # The ways out: say which package yourself ...
    mine = _suite(tmp_path, bundle, "test", "IMTYPESET_PYTHON=/mine/python")
    assert mine.stdout.splitlines()[-1] == f"suite: {library} /mine/python", mine.stderr
    # ... or build, which a stale pair must not stand in the way of, alone or
    # with the suite behind it.
    again = _suite(tmp_path, bundle, "typeset-lib", "test")
    assert again.returncode == 0, again.stderr
    assert again.stdout.splitlines()[-1] == report
    assert _suite(tmp_path, bundle, "test").stdout.splitlines()[-1] == report


@needs_make
@pytest.mark.parametrize(
    "case", ["no BUILT-FROM", "BUILT-FROM from before the checksum", "no snapshot", "an empty line"]
)
def test_a_pair_the_check_cannot_judge_is_not_called_stale(case: str, tmp_path: Path) -> None:
    """
    Every doubt goes to running: the bundles built before the checksum existed
    (the shared one among them) and a library with no snapshot are as they were.
    """
    _a_checkout(tmp_path, _BUILD_OK)
    bundle = _an_installed_pair(tmp_path)
    package = f"{bundle}/pysnap"
    if case == "no BUILT-FROM":
        (bundle / "BUILT-FROM").unlink()
    elif case == "no snapshot":
        shutil.rmtree(bundle / "pysnap")
        (bundle / "BUILT-FROM").write_text("library cksum: 1 1\n", encoding="utf-8")
        package = f"{tmp_path}/imtypeset/python"
    elif case == "an empty line":
        (bundle / "BUILT-FROM").write_text("library cksum: \n", encoding="utf-8")
    result = _suite(tmp_path, bundle, "test")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f"suite: {bundle}/libimtypeset_bundle.so {package}"


# ---------------------------------------------------------------------------
# Tranche N (N-IMT): the build script of imtypeset 03b5cd4 and later. It says
# the library's name in <out>/LIBRARY (the name differs by platform), writes
# <library>.attestation.json and no .gate, and must be TOLD which headers.
# `_BUILD_OK` above stays what a script from before that commit does, and
# every test above is that shape still working.
# ---------------------------------------------------------------------------

_NEW_NAME = "libimtypeset_bundle.dylib"

_BUILD_NEW = f"""\
set -eu
mkdir -p "$IMTYPESET_BUNDLE_OUT/obj"
told="${{IMTYPESET_BUNDLE_HEADERS-unset}}|${{IMTYPESET_HEADER_CACHE-unset}}"
echo "$told" > "$IMTYPESET_BUNDLE_OUT/obj/told"
echo new > "$IMTYPESET_BUNDLE_OUT/{_NEW_NAME}"
echo "$IMTYPESET_BUNDLE_OUT/{_NEW_NAME}" > "$IMTYPESET_BUNDLE_OUT/LIBRARY"
echo '{{"schema": 1}}' > "$IMTYPESET_BUNDLE_OUT/{_NEW_NAME}.attestation.json"
"""


@needs_make
def test_the_librarys_name_is_read_from_the_file_the_build_script_writes(tmp_path: Path) -> None:
    """
    imtypeset's T2 and T3, run with a stand-in script that names its library
    as the macOS branch of the real one does. Everything that used to spell
    `libimtypeset_bundle.so` goes through LIBRARY: what is imported before
    the pair is installed, the checksum, the opt-in's default, the stale-pair
    check. The attestation is carried beside the library as it was written.
    """
    checkout = _a_checkout(tmp_path, _BUILD_NEW)
    bundle = _an_installed_pair(tmp_path)
    result = _build(checkout, bundle)
    assert result.returncode == 0, result.stderr
    library = bundle / _NEW_NAME
    assert library.read_text(encoding="utf-8") == "new\n"
    assert not (bundle / "libimtypeset_bundle.so").exists(), "the pair before was merged into"
    # LIBRARY named the staging directory when the script wrote it.
    assert (bundle / "LIBRARY").read_text(encoding="utf-8") == f"{library}\n"
    attestation = bundle / f"{_NEW_NAME}.attestation.json"
    assert attestation.read_text(encoding="utf-8") == '{"schema": 1}\n'
    assert not list(bundle.glob("*.gate")), "something here wrote a gate stamp"
    assert f"import {bundle}.building/{_NEW_NAME} with " in result.stdout
    # The last line is the two variables an example is run with, by the name the build gave.
    assert result.stdout.splitlines()[-1].startswith(
        f"use it with: IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON={bundle}/pysnap "
    )
    built_from = (bundle / "BUILT-FROM").read_text(encoding="utf-8")
    checksum = (
        subprocess.run(["cksum"], input=library.read_bytes(), capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    assert _field(built_from, "library cksum") == checksum

    report = f"suite: {library} {bundle}/pysnap"
    assert _suite(tmp_path, bundle, "test").stdout.splitlines()[-1] == report
    opted = _recipe("test", "TYPESET=1", f"IMTYPESET_BUNDLE={bundle}", f"IMTYPESET_ROOT={checkout}")
    assert opted.strip() == (
        f"IMTYPESET_LIBRARY={library} IMTYPESET_PYTHON={bundle}/pysnap echo -m pytest -q"
    )
    # Only the NAME is taken from the file: a bundle that was copied names its own library.
    copy = tmp_path / "copied"
    shutil.copytree(bundle, copy)
    assert _suite(tmp_path, copy, "test").stdout.splitlines()[-1] == (
        f"suite: {copy}/{_NEW_NAME} {copy}/pysnap"
    )
    # The stale-pair check reads the library LIBRARY names ...
    library.write_text("built by hand\n", encoding="utf-8")
    stale = _suite(tmp_path, bundle, "test")
    assert stale.returncode != 0 and str(library) in stale.stderr, stale.stderr
    # ... and building again in one invocation uses the name the pair has.
    again = _suite(tmp_path, bundle, "typeset-lib", "test")
    assert again.returncode == 0, again.stderr
    assert again.stdout.splitlines()[-1] == report


@needs_make
@pytest.mark.parametrize("left", ["nothing", "another name"])
def test_a_library_file_that_names_what_the_script_did_not_leave_installs_nothing(
    left: str, tmp_path: Path
) -> None:
    build = _BUILD_NEW + f'rm "$IMTYPESET_BUNDLE_OUT/{_NEW_NAME}"\n'
    if left == "another name":
        build += 'echo new > "$IMTYPESET_BUNDLE_OUT/libimtypeset_bundle.so"\n'
    checkout = _a_checkout(tmp_path, build)
    bundle = _an_installed_pair(tmp_path)
    before = _tree(bundle)
    result = _build(checkout, bundle)
    assert result.returncode != 0, result.stdout
    assert f"left no library at {bundle}.building/{_NEW_NAME}" in result.stderr, result.stderr
    assert _tree(bundle) == before


@needs_make
def test_a_pair_built_without_an_attestation_is_installed_and_the_build_says_what_it_costs(
    tmp_path: Path,
) -> None:
    """
    The real script can be stopped before its gate step. The pair loads (the
    package probes it in a child at every import), so it is not refused; the
    line is so that nobody runs a suite that way without knowing.
    """
    build = _BUILD_NEW + f'rm "$IMTYPESET_BUNDLE_OUT/{_NEW_NAME}.attestation.json"\n'
    result = _build(_a_checkout(tmp_path, build), tmp_path / "bundle")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bundle" / _NEW_NAME).exists()
    assert f"no {_NEW_NAME}.attestation.json" in result.stderr, result.stderr
    # A script from before 03b5cd4 never wrote one, and is told nothing.
    old = _build(_a_checkout(tmp_path / "old", _BUILD_OK), tmp_path / "old-bundle")
    assert old.returncode == 0 and "attestation" not in old.stderr, old.stderr


@needs_make
@pytest.mark.parametrize(
    ("given", "told"),
    [
        ((), "unset"),
        (("IMTYPESET_HEADERS=",), "unset"),
        (("IMTYPESET_HEADERS=stand-in",), "stand-in"),
    ],
    ids=["default", "empty", "stand-in"],
)
def test_the_headers_choice_is_handed_to_the_script_only_when_one_is_made(
    given: tuple[str, ...], told: str, tmp_path: Path
) -> None:
    """
    imtypeset's T1. By default the script chooses, which from 03b5cd4 on is to
    fetch the wheel's own headers; `IMTYPESET_HEADERS=stand-in` is the choice
    without network, said under the script's own name for it. What it fetches
    is kept under this repository's build/ whichever tree the script runs
    from, or where the caller says.
    """
    checkout = _a_checkout(tmp_path, _BUILD_NEW)
    bundle = tmp_path / "bundle"
    result = _build(checkout, bundle, *given)
    assert result.returncode == 0, result.stderr
    said = (bundle / "obj" / "told").read_text(encoding="utf-8").strip()
    assert said == f"{told}|{_ROOT}/build/imtypeset-headers"
    result = _build(checkout, bundle, *given, f"IMTYPESET_HEADER_CACHE={tmp_path}/kept")
    assert result.returncode == 0, result.stderr
    said = (bundle / "obj" / "told").read_text(encoding="utf-8").strip()
    assert said == f"{told}|{tmp_path}/kept"


@needs_make
def test_the_headers_choice_is_in_the_recipe_as_the_scripts_own_variable(tmp_path: Path) -> None:
    """
    Read, not run: with no choice the word is not in the recipe at all, so a
    caller's own IMTYPESET_BUNDLE_HEADERS in the environment still reaches the
    script, as it did.
    """
    checkout = _a_checkout(tmp_path, _BUILD_NEW)
    plain = _make("-n", "typeset-lib", "PY=echo", f"IMTYPESET_ROOT={checkout}")
    assert plain.returncode == 0, plain.stderr
    assert "IMTYPESET_BUNDLE_HEADERS" not in plain.stdout
    asked = _make(
        "-n", "typeset-lib", "PY=echo", f"IMTYPESET_ROOT={checkout}", "IMTYPESET_HEADERS=stand-in"
    )
    assert "IMTYPESET_BUNDLE_HEADERS=stand-in IMTYPESET_HEADER_CACHE=" in asked.stdout
    assert asked.stdout.replace("IMTYPESET_BUNDLE_HEADERS=stand-in ", "") == plain.stdout


def _pin() -> str:
    text = _PYPROJECT.read_text(encoding="utf-8")
    found = re.findall(r'^\s*"imgui-bundle\s*([^"]*)"', text, re.MULTILINE)
    assert len(found) == 1, f"pyproject.toml names imgui-bundle {len(found)} times"
    exact = re.fullmatch(r"==\s*([0-9]+(?:\.[0-9]+)*)", found[0])
    assert exact, (
        f"pyproject.toml asks for imgui-bundle{found[0]}: it must be `==` one version. "
        "The imtypeset library is linked against one wheel binary and refuses any other "
        "at import, so a range here promises what the pairing cannot keep."
    )
    return exact.group(1)


def test_imgui_bundle_is_pinned_to_exactly_the_version_that_is_installed() -> None:
    """
    What this measures and what it does not.

    Measured: the pin is one exact version (no range, no wildcard) and the
    installed imgui-bundle IS that version. The pin replaced a floor
    (`>=1.92.900`) on 2026-10-11, and the reason is the sidecar: a library
    built by `make typeset-lib` is for the wheel it was linked against.
    Bumping the pin is therefore three acts, and this test is red until the
    first two are done: change the pin, install it (`make bootstrap`), and
    then rebuild the library and run `make check TYPESET=1`, which nothing
    here can check for you.

    Not measured: that an environment holding ANOTHER version is corrected
    by `pip install -e .[dev]`. By pip's rules it is -- an installed version
    that does not satisfy `==` is replaced -- but no index is reachable where
    this was written.

    Until that date this test also held the floor to a release that has
    `ImDrawListFlags_.text_no_pixel_snap`, the flag imscribe's own draw
    backend set. That backend was deleted in tranche 5 and nothing in imscribe
    names the flag now, so it is no longer asserted; the pin is still not
    allowed below 1.92.900, the release every measurement was taken on.
    """
    pin = _pin()
    assert tuple(int(part) for part in pin.split(".")) >= (
        1,
        92,
        900,
    ), f"the pin {pin} is below 1.92.900, the release every measurement here was taken on"
    pytest.importorskip("imgui_bundle")
    installed = metadata.version("imgui-bundle")
    assert installed == pin, (
        f"imgui-bundle {installed} is installed and pyproject.toml pins {pin}: "
        "run `make bootstrap`, then `make typeset-lib` for the new wheel"
    )

"""
The version a host can read, and `make dist`: a wheel and an sdist of a commit.

pptmstr's P31 asks for a name it can require. What imscribe can give alone is
a version that says something, and two files with hashes built from a commit
by one target. This file holds both.

**What is NOT tested here, and could not be by the session that wrote it
(2026-10-12): the real builder.** `./.venv` had neither `build` nor
`hatchling` and no index was reachable, so `python -m build` has never run on
this tree. Every test of `scripts/make_dist.py` below hands it a STAND-IN
builder: a small script that writes a zip and a `tar.gz` from the export it
is given, with the commit's time on every member, which is what hatchling is
expected to do under `SOURCE_DATE_EPOCH`. So these tests hold the script's
own promises -- the commit and not the working tree, two builds compared,
contents checked, nothing installed on a refusal, the hashes, the strings --
and say nothing about whether hatchling's output is reproducible or what it
puts in the wheel. `test_what_pyproject_says_the_wheel_and_the_sdist_hold`
reads the configuration hatchling would read, and that is all it does.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import imscribe
from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "make_dist.py"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def _script() -> ModuleType:
    """`scripts/make_dist.py` as a module, without putting `scripts/` on `sys.path`."""
    spec = importlib.util.spec_from_file_location("_make_dist_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The version
# ---------------------------------------------------------------------------


def _pyproject() -> dict[str, Any]:
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_the_version_is_one_string_in_the_two_places_it_is_written() -> None:
    stated = _pyproject()["project"]["version"]
    assert imscribe.__version__ == stated
    # PEP 440, the shape a requirement can name: release digits, then at most a
    # pre-release, a post-release and a development number.
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?", stated), stated
    assert "__version__" not in imscribe.__all__
    assert "__version__" in dir(imscribe)


def test_the_script_reads_the_two_versions_the_way_this_file_does() -> None:
    """The regular expressions in the script, against the real files and not only a fixture."""
    assert _script().declared_version(_ROOT) == (imscribe.__version__, imscribe.__version__)
    assert _script().pins(_ROOT) == ["imgui-bundle==1.92.900"]


def test_a_child_asked_for_the_pairing_says_which_imscribe_answered() -> None:
    """`python -m imscribe.typesetter`, with nothing to find: the version is there all the same."""
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("IMTYPESET_")
    }
    done = subprocess.run(
        [sys.executable, "-B", "-m", "imscribe.typesetter"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**environment, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    answer = json.loads(done.stdout.strip().splitlines()[-1])
    assert answer["imscribe_version"] == imscribe.__version__
    assert done.returncode == typesetter.EXIT_CODES[typesetter.Kind(answer["kind"])]


def test_a_verdict_nobody_could_be_asked_for_still_names_this_imscribe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    answer = typesetter.verdict()
    assert answer["kind"] == typesetter.Kind.UNCHECKED.value
    assert answer["imscribe_version"] == imscribe.__version__
    assert set(answer) == set(typesetter._PAIRING_KEYS)
    assert typesetter._PAIRING_KEYS[0] == "imscribe_version"


# ---------------------------------------------------------------------------
# What pyproject.toml says is built. Read, not built.
# ---------------------------------------------------------------------------


def test_what_pyproject_says_the_wheel_and_the_sdist_hold() -> None:
    project = _pyproject()
    assert project["build-system"]["build-backend"] == "hatchling.build"
    targets = project["tool"]["hatch"]["build"]["targets"]
    assert targets["wheel"] == {"packages": ["imscribe"]}
    assert (_ROOT / "imscribe" / "py.typed").is_file()
    included = set(targets["sdist"]["include"])
    script = _script()
    for needed in script.SDIST_ONLY:
        assert "/" + needed.rstrip("/") in included, needed
    assert "/imscribe" in included
    # The two tools `make dist` runs are what the dev extra installs.
    dev = " ".join(project["project"]["optional-dependencies"]["dev"])
    for tool in script.TOOLS:
        assert re.search(rf"\b{tool}>=", dev), tool


# ---------------------------------------------------------------------------
# The script, against a stand-in builder
# ---------------------------------------------------------------------------

_STANDIN = r'''
"""A stand-in for `python -m build`: a zip and a tar.gz of the source it is given."""
import gzip, io, os, re, sys, tarfile, time, zipfile
from pathlib import Path

out = Path(sys.argv[sys.argv.index("--outdir") + 1])
source = Path(sys.argv[-1])
fault = os.environ.get("STANDIN_FAULT", "")
epoch = int(os.environ["SOURCE_DATE_EPOCH"])
stated = (source / "pyproject.toml").read_text()
version = re.search(r'^version\s*=\s*"([^"]+)"', stated, re.M).group(1)
stamp = time.gmtime(epoch)[:6]

def files(*tops):
    found = []
    for top in tops:
        path = source / top
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.is_file()))
    return found

info_dir = f"imscribe-{version}.dist-info"
metadata = f"Metadata-Version: 2.1\nName: imscribe\nVersion: {version}\n"
if fault == "path":
    metadata += f"Built-In: {source}\n"
wheel_tops = ["imscribe"] + (["tests"] if fault == "tests" else [])
with zipfile.ZipFile(out / f"imscribe-{version}-py3-none-any.whl", "w") as wheel:
    for path in files(*wheel_tops):
        name = path.relative_to(source).as_posix()
        if fault == "untyped" and name.endswith("py.typed"):
            continue
        wheel.writestr(zipfile.ZipInfo(name, stamp), path.read_bytes())
    wheel.writestr(zipfile.ZipInfo(f"{info_dir}/METADATA", stamp), metadata)
    wheel.writestr(zipfile.ZipInfo(f"{info_dir}/WHEEL", stamp), "Wheel-Version: 1.0\n")

top = f"imscribe-{version}"
sdist_tops = ["imscribe", "tests", "docs", "demo", "README.md", "pyproject.toml",
              "HANDOFF-imtypeset.md", "HANDOFF-pptmstr.md"]
if fault != "bare":
    sdist_tops.append("examples")
raw = io.BytesIO()
with tarfile.open(fileobj=raw, mode="w") as sdist:
    def add(name, data):
        member = tarfile.TarInfo(f"{top}/{name}")
        member.size, member.mtime, member.mode = len(data), epoch, 0o644
        sdist.addfile(member, io.BytesIO(data))
    for path in files(*sdist_tops):
        add(path.relative_to(source).as_posix(), path.read_bytes())
    add("PKG-INFO", metadata.encode())
header_time = int.from_bytes(os.urandom(3), "big") if fault == "clock" else epoch
with open(out / f"{top}.tar.gz", "wb") as handle:
    with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=header_time) as packed:
        packed.write(raw.getvalue())
'''


def _git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout.strip()


_TREE = {
    "pyproject.toml": (
        '[project]\nname = "imscribe"\nversion = "9.8.7.dev6"\n'
        'dependencies = [\n    "imgui-bundle==1.92.900",\n    "fonttools>=4.50",\n]\n'
    ),
    "imscribe/__init__.py": '"""committed"""\n__version__ = "9.8.7.dev6"\n',
    "imscribe/py.typed": "",
    "imscribe/ui/view.py": "X = 1\n",
    "tests/test_it.py": "def test_it():\n    pass\n",
    "examples/minimal.py": "import imscribe\n",
    "demo/sample.md": "# sample\n",
    "docs/status.md": "status\n",
    "README.md": "readme\n",
    "HANDOFF-imtypeset.md": "to imtypeset\n",
    "HANDOFF-pptmstr.md": "to pptmstr\n",
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A committed miniature of this repository, and the stand-in builder beside it."""
    root = tmp_path / "repo"
    for name, text in _TREE.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-gpg-sign", "-m", "a tree")
    (tmp_path / "standin.py").write_text(_STANDIN, encoding="utf-8")
    return root


def _run(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str = "",
    rev: str = "HEAD",
) -> tuple[int, str, Path, Path]:
    """`make()` with the stand-in: the exit code, what was said, the out and stage directories."""
    script = _script()
    monkeypatch.setenv("STANDIN_FAULT", fault)
    out, stage = project.parent / "dist", project.parent / "stage"
    said: list[str] = []
    builder = [sys.executable, "-P", "-B", str(project.parent / "standin.py")]
    try:
        code = script.make(project, out, stage, rev, builder, said.append)
    except script.Stop as stop:
        return stop.code, str(stop), out, stage
    return code, "\n".join(said), out, stage


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@needs_git
def test_it_builds_the_commit_and_not_the_working_tree(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = _git(project, "rev-parse", "HEAD")
    epoch = int(_git(project, "log", "-1", "--format=%ct"))
    # Two things the commit does not have: an edit, and a file nobody added.
    (project / "imscribe" / "__init__.py").write_text(
        '"""edited"""\n__version__ = "0.0.0"\n', encoding="utf-8"
    )
    (project / "imscribe" / "stray.py").write_text("STRAY = 1\n", encoding="utf-8")

    code, said, out, _ = _run(project, monkeypatch)
    assert code == 0, said

    wheel = out / "imscribe-9.8.7.dev6-py3-none-any.whl"
    sdist = out / "imscribe-9.8.7.dev6.tar.gz"
    assert sorted(path.name for path in out.iterdir()) == sorted(
        [wheel.name, sdist.name, wheel.name + ".sha256", sdist.name + ".sha256", "BUILT-FROM"]
    )
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert archive.read("imscribe/__init__.py").decode().startswith('"""committed"""')
        # A zip keeps a time to two seconds, so the commit's own second may be the one before.
        written = archive.getinfo("imscribe/__init__.py").date_time
        assert written == tuple(time.gmtime(epoch - epoch % 2)[:6])
    assert "imscribe/stray.py" not in names and "imscribe/py.typed" in names
    assert all(name.startswith(("imscribe/", "imscribe-9.8.7.dev6.dist-info/")) for name in names)
    with tarfile.open(sdist) as archive:
        inside = archive.getnames()
    for carried in ("examples/minimal.py", "HANDOFF-pptmstr.md", "HANDOFF-imtypeset.md"):
        assert f"imscribe-9.8.7.dev6/{carried}" in inside
    assert "2 path(s) of the working tree" in said and "NOT in what is built" in said

    # The hashes: beside each file in the form `sha256sum -c` reads, and in the record.
    record = (out / "BUILT-FROM").read_text(encoding="utf-8")
    for built in (wheel, sdist):
        assert (out / f"{built.name}.sha256").read_text() == f"{_sha(built)}  {built.name}\n"
        assert f"sha256: {_sha(built)}  {built.name}" in record
    assert f"commit: {commit}" in record and f"source date epoch: {epoch}" in record
    assert "version: 9.8.7.dev6" in record
    assert "uncommitted paths at the time, none of them built: 2" in record

    # The strings a host copies.
    repository = _script().REPOSITORY
    assert f"imscribe @ git+{repository}.git@{commit}" in said
    assert (
        f"imscribe @ {repository}/releases/download/v9.8.7.dev6/{wheel.name}#sha256={_sha(wheel)}"
        in said
    )
    assert f"imscribe==9.8.7.dev6 --hash=sha256:{_sha(wheel)} --hash=sha256:{_sha(sdist)}" in said
    assert "    imgui-bundle==1.92.900\n" in said + "\n" and "fonttools" not in said
    assert "development version" in said
    # Said of both lines that nothing was published.
    assert "Nothing below has been published or pushed" in said


@needs_git
def test_the_two_builds_are_made_from_two_exports_and_are_the_same_bytes(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, said, out, stage = _run(project, monkeypatch)
    assert code == 0, said
    assert "two builds from two exports: the same bytes" in said
    for name in ("imscribe-9.8.7.dev6-py3-none-any.whl", "imscribe-9.8.7.dev6.tar.gz"):
        first, second = stage / "out-first" / name, stage / "out-second" / name
        assert _sha(first) == _sha(second) == _sha(out / name)
    exports = sorted(path.name for path in stage.iterdir() if path.name.startswith("export-"))
    assert exports == ["export-first", "export-second"]
    assert not (stage / "export-first" / "imscribe-src" / ".git").exists()


@needs_git
@pytest.mark.parametrize(
    ("fault", "named"),
    [
        # The export's path written into a member: the two exports have two names.
        ("path", ("imscribe-9.8.7.dev6.dist-info/METADATA", "PKG-INFO", "sha256")),
        # A clock in the gzip header and every member equal.
        ("clock", ("imscribe-9.8.7.dev6.tar.gz", "every member is equal", "container")),
    ],
)
def test_two_builds_that_differ_are_said_and_nothing_is_installed(
    project: Path, monkeypatch: pytest.MonkeyPatch, fault: str, named: tuple[str, ...]
) -> None:
    out = project.parent / "dist"
    out.mkdir()
    (out / "imscribe-0.0.1-py3-none-any.whl").write_text("the build before", encoding="utf-8")

    code, said, _, stage = _run(project, monkeypatch, fault)
    assert code == _script().EXIT_REFUSED
    assert "two builds of one commit differ" in said
    for word in named:
        assert word in said, said
    if fault == "clock":
        assert "whl" not in said.split("Both are under")[0], "the wheel did not differ"
    assert [path.name for path in out.iterdir()] == ["imscribe-0.0.1-py3-none-any.whl"]
    assert (stage / "out-first").is_dir() and (stage / "out-second").is_dir()


@needs_git
@pytest.mark.parametrize(
    ("fault", "named"),
    [
        ("tests", "1 member(s) outside imscribe/ and imscribe-9.8.7.dev6.dist-info/: tests/"),
        ("untyped", "the wheel has no imscribe/py.typed"),
        ("bare", "the sdist has no examples/"),
    ],
)
def test_a_build_that_is_not_what_pyproject_describes_is_not_installed(
    project: Path, monkeypatch: pytest.MonkeyPatch, fault: str, named: str
) -> None:
    code, said, out, _ = _run(project, monkeypatch, fault)
    assert code == _script().EXIT_REFUSED
    assert named in said, said
    assert not out.exists()


@needs_git
def test_a_commit_whose_two_versions_disagree_is_not_installed(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "imscribe" / "__init__.py").write_text('__version__ = "9.8.7"\n', encoding="utf-8")
    _git(project, "commit", "-q", "--no-gpg-sign", "-am", "one of the two")
    code, said, out, _ = _run(project, monkeypatch)
    assert code == _script().EXIT_REFUSED
    assert "pyproject.toml states version '9.8.7.dev6' and imscribe/__init__.py '9.8.7'" in said
    assert not out.exists()


@needs_git
def test_a_build_replaces_the_files_of_the_build_before_and_nothing_else(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = project.parent / "dist"
    out.mkdir()
    for name in ("imscribe-0.0.1-py3-none-any.whl", "imscribe-0.0.1.tar.gz.sha256", "BUILT-FROM"):
        (out / name).write_text("before", encoding="utf-8")
    (out / "somebody-elses.whl").write_text("kept", encoding="utf-8")
    code, said, _, _ = _run(project, monkeypatch)
    assert code == 0, said
    left = {path.name for path in out.iterdir()}
    assert "somebody-elses.whl" in left
    assert not {name for name in left if "0.0.1" in name}
    assert "commit: " in (out / "BUILT-FROM").read_text(encoding="utf-8")


@needs_git
def test_another_commit_can_be_named_and_one_that_does_not_exist_is_refused(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _git(project, "rev-parse", "HEAD")
    (project / "imscribe" / "ui" / "view.py").write_text("X = 2\n", encoding="utf-8")
    _git(project, "commit", "-q", "--no-gpg-sign", "-am", "a second")

    code, said, out, _ = _run(project, monkeypatch, rev=first)
    assert code == 0, said
    with zipfile.ZipFile(out / "imscribe-9.8.7.dev6-py3-none-any.whl") as archive:
        assert archive.read("imscribe/ui/view.py") == b"X = 1\n"
    assert f"@{first}" in said

    shutil.rmtree(out)
    code, said, out, stage = _run(project, monkeypatch, rev="no-such-rev")
    assert code == _script().EXIT_CANNOT_START
    assert "'no-such-rev' names no commit" in said
    assert not out.exists()


@needs_git
def test_a_directory_that_is_not_the_top_of_a_checkout_is_refused(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inside a checkout is not enough: an sdist unpacked under a repository is not it."""
    script = _script()
    for where in (project / "imscribe", project.parent):
        with pytest.raises(script.Stop) as stopped:
            script.make(where, project.parent / "dist", project.parent / "stage", "HEAD", ["true"])
        assert stopped.value.code == script.EXIT_CANNOT_START
        assert "is not the top of a git checkout" in str(stopped.value)
    assert not (project.parent / "dist").exists() and not (project.parent / "stage").exists()


def test_a_directory_that_only_has_the_name_is_not_the_tool() -> None:
    """
    This repository has a `build/`. `find_spec("build")` answers with it when the working
    directory is on the path, and that is not `python -m build`.
    """
    script = _script()

    class Spec:
        def __init__(self, origin: str | None) -> None:
            self.origin = origin

    found = {"build": Spec(None), "hatchling": Spec("/site/hatchling/__init__.py")}
    assert script.missing_tools(found.get) == ["build"]
    assert script.missing_tools(lambda name: None) == ["build", "hatchling"]
    assert script.missing_tools(lambda name: Spec("/site/x.py")) == []
    assert "-P" in script.default_builder() and "--no-isolation" in script.default_builder()


@needs_git
def test_without_the_tools_it_stops_before_anything_is_written(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    monkeypatch.setattr(script, "missing_tools", lambda: ["build", "hatchling"])
    out, stage = project.parent / "dist", project.parent / "stage"
    with pytest.raises(script.Stop) as stopped:
        script.make(project, out, stage)
    assert stopped.value.code == script.EXIT_CANNOT_START
    assert "has no build and no hatchling" in str(stopped.value)
    assert "make bootstrap" in str(stopped.value)
    assert not out.exists() and not stage.exists()


@needs_git
def test_the_command_line_answers_with_the_exit_code_and_one_sentence(project: Path) -> None:
    """The script as `make dist` runs it, with `--builder` naming the stand-in."""
    standin = f"{sys.executable} -P -B {project.parent / 'standin.py'}"
    arguments = [
        sys.executable,
        "-P",
        str(_SCRIPT),
        "--root",
        str(project),
        "--out",
        str(project.parent / "dist"),
        "--stage",
        str(project.parent / "stage"),
        "--builder",
        standin,
    ]
    environment = {name: value for name, value in os.environ.items() if name != "STANDIN_FAULT"}
    good = subprocess.run(
        arguments, capture_output=True, text=True, timeout=120, check=False, env=environment
    )
    assert good.returncode == 0, good.stderr
    assert "imscribe @ git+" in good.stdout
    bad = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**environment, "STANDIN_FAULT": "tests"},
    )
    assert bad.returncode == 3
    assert bad.stderr.startswith("make dist: what was built is not what pyproject.toml describes")


# ---------------------------------------------------------------------------
# The Makefile's target
# ---------------------------------------------------------------------------

_INHERITED = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES", "DIST_DIR", "DIST_REV", "ARGS")


@needs_make
def test_the_dist_target_hands_the_script_the_commit_and_the_directory() -> None:
    clean = {name: value for name, value in os.environ.items() if name not in _INHERITED}

    def recipe(*args: str) -> str:
        done = subprocess.run(
            [
                "make",
                "-C",
                str(_ROOT),
                "--no-print-directory",
                "-n",
                "dist",
                "PY=python-stub",
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=clean,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert recipe() == 'python-stub -P scripts/make_dist.py --out "dist" --rev "HEAD"'
    assert (
        recipe("DIST_DIR=/tmp/else", "DIST_REV=v0.2.0", "ARGS=--stage /tmp/s")
        == 'python-stub -P scripts/make_dist.py --out "/tmp/else" --rev "v0.2.0" --stage /tmp/s'
    )

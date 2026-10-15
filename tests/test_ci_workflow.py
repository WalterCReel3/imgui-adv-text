"""
The CI workflow says what the Makefile can do, and names the pair in one place.

`.github/workflows/ci.yml` was written in a session that could not reach
GitHub, so it has never run. These tests hold it to everything that can be
checked from inside a checkout:

1.  It reads as YAML -- in a subset (below), because `./.venv` has no YAML
    parser and a dev dependency added for one test file is not worth it.
2.  Its triggers and its jobs are the ones the gate is described by: since
    2026-10-13 two on a push (the suite with the library switched off, and
    with the imtypeset wheel `make bootstrap` installs) and one started by
    hand (the pair built from source).
3.  Every `make <target>` it runs is a target of the `Makefile`, and every
    `NAME=value` it hands to `make` is a variable the `Makefile` assigns.
4.  The imtypeset ref is in ONE place, `imtypeset.ref`, as a full commit hash;
    the workflow reads it from there and repeats it nowhere, and it is the ref
    `HANDOFF-imtypeset.md` names.
5.  Every `run:` is a command a person can paste into a shell: no workflow
    expression inside one.
6.  The macOS file cannot start by itself.
7.  `release.yml` can send files to PyPI for a pushed tag `v*` and for
    nothing else, to TestPyPI only for a run started by hand that asks, and
    does neither before the build job passed (2026-10-13).

**The YAML subset.** `read_yaml` below is not a YAML parser. It reads block
mappings, block sequences, plain and quoted scalars on one line, and literal
blocks (`|`), with comments on lines of their own, and it REFUSES everything
else by raising -- flow collections, anchors, tags, folded blocks, tabs, a
comment after a value, a plain scalar holding `: ` or ` #`. Within that subset
a real parser reads the same structure (checked once against PyYAML 6.0 under
the system interpreter, 2026-10-11, by
`.concerns/L1-CI-scripts/crosscheck_yaml.py`; when `yaml` is importable here
`test_the_reader_agrees_with_a_real_parser_when_there_is_one` checks it on
every run, and when it is not that test passes having compared nothing).
Scalars stay strings: `on` is a key named "on" here, where PyYAML makes it
`True`; `if: false` is the string "false".

**What this cannot see**, which is most of what could be wrong with a workflow:
whether an action exists at the version named, whether a package name is right
for the runner's Ubuntu, whether a window opens there, whether the suite
passes there. The list of what was not run, and what would show each
assumption wrong, is in `.concerns/L1-CI--builder--result.md` and, shorter, in
the header of `ci.yml`.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_CI = _WORKFLOWS / "ci.yml"
_MACOS = _WORKFLOWS / "macos.yml"
_RELEASE = _WORKFLOWS / "release.yml"
_PYPROJECT = _ROOT / "pyproject.toml"
_MAKEFILE = _ROOT / "Makefile"
_REF = _ROOT / "imtypeset.ref"
_HANDOFF = _ROOT / "HANDOFF-imtypeset.md"

IMTYPESET_URL = "github.com/WalterCReel3/imtypeset"

# The one action that is not GitHub's own, named by a commit and not a tag: it
# is handed the right to publish. v1.14.2 (read from GitHub's API on
# 2026-10-13; the commit imtypeset's wheels.yml names).
PUBLISH_ACTION = "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"


# ---------------------------------------------------------------------------
# the reader


class NotInTheSubset(ValueError):
    """A line `read_yaml` will not guess at."""


_KEY = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.-]*):(?: (.*))?$")


def _scalar(text: str, where: str) -> str | None:
    """
    One scalar from the rest of a line. `None` for an empty value.
    """
    if text == "":
        return None
    if text[0] == '"':
        if len(text) < 2 or text[-1] != '"' or '"' in text[1:-1] or "\\" in text:
            raise NotInTheSubset(f"{where}: a double-quoted scalar with an escape or a tail")
        return text[1:-1]
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'" or "'" in text[1:-1]:
            raise NotInTheSubset(f"{where}: a single-quoted scalar with a quote inside or a tail")
        return text[1:-1]
    if text[0] in "[{&*!|>%@`,?#-" and not re.match(r"-[^ ]", text):
        raise NotInTheSubset(f"{where}: {text[0]!r} starts something this reader does not read")
    if ": " in text or text.endswith(":") or " #" in text:
        raise NotInTheSubset(f"{where}: a plain scalar holding ': ' or ' #'; quote it")
    return text


def read_yaml(text: str) -> Any:
    """
    The mapping/sequence/string structure of `text`, or `NotInTheSubset`.
    """
    if "\t" in text:
        raise NotInTheSubset("a tab")
    lines: list[tuple[int, str, int]] = []  # indent, content, line number
    raw = text.split("\n")
    for number, line in enumerate(raw, start=1):
        if line != line.rstrip():
            raise NotInTheSubset(f"line {number}: trailing white space")
        lines.append((len(line) - len(line.lstrip(" ")), line.strip(), number))

    position = 0

    def skip() -> None:
        nonlocal position
        while position < len(lines) and (
            lines[position][1] == "" or lines[position][1].startswith("#")
        ):
            position += 1

    def literal(parent: int) -> str:
        """
        The lines of a `|` block: everything indented deeper than `parent`.
        """
        nonlocal position
        body: list[tuple[int, str]] = []
        while position < len(lines):
            indent, content, _ = lines[position]
            if content != "" and indent <= parent:
                break
            body.append((indent, content))
            position += 1
        while body and body[-1][1] == "":
            body.pop()
        if not body:
            raise NotInTheSubset("an empty literal block")
        base = min(indent for indent, content in body if content != "")
        return "".join(
            (" " * (indent - base) + content if content else "") + "\n" for indent, content in body
        )

    def value(rest: str | None, indent: int, where: str) -> Any:
        """
        What follows `key:` -- on the line, as a literal block, or nested.
        """
        if rest == "|":
            return literal(indent)
        if rest is not None and rest != "":
            return _scalar(rest, where)
        skip()
        if position < len(lines) and lines[position][0] > indent:
            return block(lines[position][0])
        return None

    def block(indent: int) -> Any:
        nonlocal position
        skip()
        if lines[position][1].startswith("- ") or lines[position][1] == "-":
            return sequence(indent)
        return mapping(indent, {})

    def mapping(indent: int, into: dict[str, Any]) -> dict[str, Any]:
        nonlocal position
        while True:
            skip()
            if position >= len(lines) or lines[position][0] < indent:
                return into
            at, content, number = lines[position]
            where = f"line {number}"
            if at != indent:
                raise NotInTheSubset(f"{where}: indented {at}, in a mapping at {indent}")
            found = _KEY.match(content)
            if found is None:
                raise NotInTheSubset(f"{where}: not `key: value`: {content!r}")
            key, rest = found.group(1), found.group(2)
            if key in into:
                raise NotInTheSubset(f"{where}: the key {key!r} twice in one mapping")
            position += 1
            into[key] = value(rest, indent, where)

    def sequence(indent: int) -> list[Any]:
        nonlocal position
        items: list[Any] = []
        while True:
            skip()
            if position >= len(lines) or lines[position][0] < indent:
                return items
            at, content, number = lines[position]
            where = f"line {number}"
            if at != indent or not content.startswith("- "):
                raise NotInTheSubset(f"{where}: not an item of the sequence at {indent}")
            inner = content[2:]
            if inner != inner.lstrip(" "):
                raise NotInTheSubset(f"{where}: more than one space after '-'")
            found = _KEY.match(inner)
            if found is None or inner[0] in "\"'":
                position += 1
                items.append(_scalar(inner, where))
                continue
            # `- key: value` opens a mapping whose keys sit two columns in.
            lines[position] = (indent + 2, inner, number)
            items.append(mapping(indent + 2, {}))

    skip()
    if position >= len(lines):
        raise NotInTheSubset("nothing but comments")
    if lines[position][0] != 0:
        raise NotInTheSubset(f"line {lines[position][2]}: the document starts indented")
    document = mapping(0, {})
    skip()
    if position != len(lines):
        raise NotInTheSubset(f"line {lines[position][2]}: not read")
    return document


# ---------------------------------------------------------------------------
# what the tests ask of a workflow


def _workflow(path: Path) -> dict[str, Any]:
    document = read_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list) and steps and all(isinstance(step, dict) for step in steps)
    return steps


def _runs(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in _steps(job) if "run" in step]


def _commands(run: str) -> list[list[str]]:
    """
    A `run:` as shell words, one list per simple command.

    Rough on purpose: a backslash-newline joins two lines, and `;`, `&&`, `||`,
    `|`, `{`, `}` and a newline end a command. Enough to find the word `make`
    at the head of a command, or after `xvfb-run ...`, and its arguments.
    """
    joined = run.replace("\\\n", " ")
    commands: list[list[str]] = []
    for line in joined.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        current: list[str] = []
        for word in lexer:
            if word in {";", "&&", "||", "|", "{", "}", "&"}:
                if current:
                    commands.append(current)
                current = []
            else:
                current.append(word)
        if current:
            commands.append(current)
    return commands


def _make_calls(run: str) -> list[tuple[list[str], dict[str, str]]]:
    """
    Each `make` in a `run:`: its goals, and its `NAME=value` arguments.
    """
    calls: list[tuple[list[str], dict[str, str]]] = []
    for command in _commands(run):
        if "make" not in command or command[0] not in {"make", "xvfb-run"}:
            continue
        arguments = command[command.index("make") + 1 :]
        goals = [word for word in arguments if "=" not in word and not word.startswith("-")]
        variables = dict(word.split("=", 1) for word in arguments if "=" in word)
        calls.append((goals, variables))
    return calls


def _makefile_targets() -> set[str]:
    targets: set[str] = set()
    for line in _MAKEFILE.read_text(encoding="utf-8").splitlines():
        found = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*:(?!=)", line)
        if found is not None:
            targets.add(found.group(1))
    return targets


def _makefile_variables() -> set[str]:
    """
    Every name the Makefile assigns, at any indentation, behind `override` or not.
    """
    return set(
        re.findall(
            r"^[ ]*(?:override\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\?=|:=|\+=|=)",
            _MAKEFILE.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )


def _all_make_calls(workflow: dict[str, Any]) -> list[tuple[str, list[str], dict[str, str]]]:
    found = []
    for name, job in workflow["jobs"].items():
        for run in _runs(job):
            for goals, variables in _make_calls(run):
                found.append((name, goals, variables))
    return found


def _ref_lines() -> list[str]:
    text = _REF.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


# ---------------------------------------------------------------------------
# the reader itself


def test_the_reader_reads_the_shapes_the_workflows_use() -> None:
    text = (
        "# a comment\n"
        "name: CI\n"
        "\n"
        "on:\n"
        "  push:\n"
        "    branches:\n"
        "      - main\n"
        '      - "experimental/**"\n'
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  one:\n"
        "    if: steps.cache.outputs.cache-hit != 'true'\n"
        "    steps:\n"
        '      - name: "a: b"\n'
        "        run: |\n"
        "          first \\\n"
        "            second\n"
        "\n"
        "          third\n"
        "\n"
        "      - uses: actions/checkout@v4\n"
    )
    assert read_yaml(text) == {
        "name": "CI",
        "on": {"push": {"branches": ["main", "experimental/**"]}, "workflow_dispatch": None},
        "jobs": {
            "one": {
                "if": "steps.cache.outputs.cache-hit != 'true'",
                "steps": [
                    {"name": "a: b", "run": "first \\\n  second\n\nthird\n"},
                    {"uses": "actions/checkout@v4"},
                ],
            }
        },
    }


@pytest.mark.parametrize(
    "text",
    [
        "a: [1, 2]\n",
        "a: {b: c}\n",
        "a: &anchor b\n",
        "a: *alias\n",
        "a: !tag b\n",
        "a: >\n  folded\n",
        "a: |-\n  stripped\n",
        "a: b # a comment after a value\n",
        "a: b: c\n",
        "a: 'it''s'\n",
        'a: "an \\n escape"\n',
        "a:\tb\n",
        "a: b \n",
        "a: b\na: c\n",
        "a:\n  b: c\n   d: e\n",
        "  a: b\n",
        "a:\n  - b\n  c: d\n",
        "- a\n",
        "# only a comment\n",
    ],
)
def test_the_reader_refuses_what_it_would_have_to_guess_at(text: str) -> None:
    with pytest.raises(NotInTheSubset):
        read_yaml(text)


@pytest.mark.parametrize("path", [_CI, _MACOS, _RELEASE], ids=lambda p: p.name)
def test_the_reader_agrees_with_a_real_parser_when_there_is_one(path: Path) -> None:
    """
    With PyYAML importable, its reading and this file's are the same structure.

    `./.venv` has none (2026-10-11), and then this compares nothing and passes:
    a skip would change the gate's count for a check that cannot run there.
    PyYAML reads the bare key `on` as `True` and `false`/numbers as their
    values; both sides are brought to strings before comparing.
    """
    ours = _workflow(path)
    if importlib.util.find_spec("yaml") is None:
        return
    import yaml  # type: ignore[import-untyped,unused-ignore]

    def strings(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                ("on" if key is True else str(key)): strings(item) for key, item in node.items()
            }
        if isinstance(node, list):
            return [strings(item) for item in node]
        if isinstance(node, bool):
            return "true" if node else "false"
        return node if node is None else str(node)

    assert strings(yaml.safe_load(path.read_text(encoding="utf-8"))) == ours


# ---------------------------------------------------------------------------
# ci.yml


def test_the_workflow_runs_on_pushes_and_pull_requests_to_main_and_experimental() -> None:
    """
    And by hand (`workflow_dispatch`, added 2026-10-13; until then the two
    events below were the whole set): that is what starts the `sidecar` job,
    and nothing else does.
    """
    workflow = _workflow(_CI)
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"] is None
    for event in ("push", "pull_request"):
        assert workflow["on"][event] == {"branches": ["main", "experimental/**"]}, event
    by_hand = {name for name, job in workflow["jobs"].items() if "if" in job}
    assert by_hand == {"sidecar"}
    assert workflow["jobs"]["sidecar"]["if"] == "github.event_name == 'workflow_dispatch'"


SUPPORTED_PYTHONS = ["3.11", "3.12", "3.13", "3.14"]
"""The CPythons imtypeset 0.4.3 has wheels for (cp311 to cp314); the gates run on each."""

_MATRIX_PYTHON = "${{ matrix.python }}"


def _setup_pythons(job: dict[str, Any]) -> list[str]:
    return [
        step["with"]["python-version"]
        for step in _steps(job)
        if step.get("uses", "").startswith("actions/setup-python@")
    ]


def _assert_runs_once_per_supported_python(job: dict[str, Any], name: str) -> None:
    """
    A matrix over every supported CPython, no leg cancelling the others, the
    version in the job's name, and a step after `make bootstrap` that is red
    unless ./.venv is the version the leg asked for.
    """
    assert job["strategy"] == {
        "fail-fast": "false",
        "matrix": {"python": SUPPORTED_PYTHONS},
    }, name
    assert _setup_pythons(job) == [_MATRIX_PYTHON], name
    assert _MATRIX_PYTHON in job["name"], name
    names = [step.get("name") for step in _steps(job)]
    check = next(
        step for step in _steps(job) if step.get("name") == "The venv is the matrix's Python"
    )
    assert names.index("make bootstrap") + 1 == names.index(check["name"]), name
    assert check["env"] == {"WANT": _MATRIX_PYTHON}, name
    assert "sys.version_info[:2]" in check["run"] and 'os.environ["WANT"]' in check["run"], name


def test_the_workflow_has_the_two_gates_on_ubuntu_over_every_supported_python() -> None:
    """
    Three jobs since 2026-10-13 (two until then: `plain` and a `typeset` that
    built the pair from source). imtypeset became a dependency, so the gate
    with the library is the one `make bootstrap` leaves, and building from
    source moved to `sidecar`.

    The two gates run on CPython 3.11 to 3.14 since 2026-10-14 (task R2-CI;
    3.11 alone until then). `sidecar` stays on 3.11: its cache key names
    `.venv/lib/python3.11`.
    """
    workflow = _workflow(_CI)
    assert set(workflow["jobs"]) == {"plain", "typeset", "sidecar"}
    for name, job in workflow["jobs"].items():
        assert job["runs-on"].startswith("ubuntu-"), name
        if name == "sidecar":
            assert "strategy" not in job
            assert _setup_pythons(job) == ["3.11"], name
        else:
            _assert_runs_once_per_supported_python(job, name)
        # A job with no limit holds a runner for six hours when a window hangs.
        assert int(job["timeout-minutes"]) <= 60, name


def test_the_venv_check_reads_the_version_the_way_the_matrix_writes_it() -> None:
    """
    The step's one-liner, run here: green for this interpreter's own version
    and red for another, so a leg cannot pass on the wrong Python.
    """
    step = next(
        s
        for s in _steps(_workflow(_CI)["jobs"]["plain"])
        if s.get("name") == "The venv is the matrix's Python"
    )
    words = shlex.split(step["run"].strip())
    assert words[:3] == [".venv/bin/python", "-P", "-c"]
    here = f"{sys.version_info[0]}.{sys.version_info[1]}"
    for want, code in ((here, 0), ("2.7", 1)):
        done = subprocess.run(
            [sys.executable, "-P", "-c", words[3]],
            env={**os.environ, "WANT": want},
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == code, (want, done.stderr)


def test_every_upload_in_a_matrix_job_is_named_per_leg() -> None:
    """
    `actions/upload-artifact@v4` refuses a second artifact of one name in a
    run, so an upload in a job that runs four times names the leg.
    """
    for path in (_CI, _MACOS):
        for name, job in _workflow(path)["jobs"].items():
            if "strategy" not in job:
                continue
            for step in _steps(job):
                if step.get("uses", "").startswith("actions/upload-artifact@"):
                    assert _MATRIX_PYTHON in step["with"]["name"], (path.name, name)


def test_the_plain_job_is_bootstrap_then_check_and_never_meets_imtypeset() -> None:
    """
    `make check` with no library must pass where the library is not used.

    Until 2026-10-13 this job had NO imtypeset anywhere and a step, "No
    imtypeset anywhere", that failed if a distribution was installed
    (`find_spec("imtypeset")`); its docstring said: "When imtypeset becomes a
    declared dependency of imscribe, that step goes red and the job's meaning
    has to be decided again". It became one, and this is the decision: `make
    bootstrap` installs the wheel in every job, and the plain job is the
    suite with `IMSCRIBE_NO_TYPESET=1`, which is what imscribe is on a
    platform with no wheel. The job still builds nothing, opts into nothing
    and names no library, and a step before the gate holds that the switch
    is honoured: the command line answers `not-installed` (exit 3).
    """
    plain = _workflow(_CI)["jobs"]["plain"]
    goals = [goals for run in _runs(plain) for goals, _ in _make_calls(run)]
    variables = [variables for run in _runs(plain) for _, variables in _make_calls(run)]
    assert goals == [["bootstrap"], ["check"]]
    assert variables == [{}, {}]
    text = "\n".join(_runs(plain))
    assert "typeset-lib" not in text and "TYPESET=" not in text
    guard = next(step for step in _steps(plain) if step.get("name", "").startswith("No library"))
    for needle in (
        "test ! -e ../imtypeset",
        "IMTYPESET_LIBRARY",
        "IMTYPESET_PYTHON",
        ".venv/bin/python -P -m imscribe.typesetter || code=$?",
        'test "$code" = 3',
    ):
        assert needle in guard["run"], needle
    assert typesetter.EXIT_CODES[typesetter.Kind.NOT_INSTALLED] == 3
    gate = next(step for step in _steps(plain) if step.get("name") == "make check")
    for step in (guard, gate):
        assert step["env"] == {typesetter.DISABLE_VARIABLE: "1"}, step["name"]
    names = [step.get("name") for step in _steps(plain)]
    assert names.index(guard["name"]) < names.index("make check")


def test_the_typeset_job_runs_the_gate_with_the_wheel_bootstrap_installed() -> None:
    """
    The with-library gate since 2026-10-13: nothing is built and nothing is
    set. Before the gate a step asks imscribe which imtypeset it found, with
    no variable in the environment, and is red unless it loads (exit 0).
    """
    typeset = _workflow(_CI)["jobs"]["typeset"]
    assert "if" not in typeset
    calls = [call for run in _runs(typeset) for call in _make_calls(run)]
    assert [goals for goals, _ in calls] == [["bootstrap"], ["shot"], ["check"]]
    assert set(calls[1][1]) == {"ARGS"} and calls[2][1] == {}
    text = "\n".join(_runs(typeset))
    assert "typeset-lib" not in text and "TYPESET=" not in text and "imtypeset.ref" not in text
    assert all(typesetter.DISABLE_VARIABLE not in step.get("env", {}) for step in _steps(typeset))
    asked = next(
        s for s in _steps(typeset) if s["name"].startswith("Which imtypeset pip installed")
    )
    assert asked["run"].rstrip().endswith("\n.venv/bin/python -P -m imscribe.typesetter")
    names = [step["name"] for step in _steps(typeset)]
    assert names.index("make bootstrap") < names.index(asked["name"]) < names.index("make check")


def test_the_dependency_the_workflows_wait_for_is_the_one_pyproject_names() -> None:
    """
    Both pins are exact and the imtypeset line is built for the imgui-bundle
    beside it: its fourth number is that version written as one number.
    """
    text = _PYPROJECT.read_text(encoding="utf-8")
    bundle = re.search(r'^\s*"imgui-bundle==(\d+)\.(\d+)\.(\d+)",$', text, flags=re.MULTILINE)
    library = re.search(r'^\s*"imtypeset==(\d+\.\d+\.\d+)\.(\d+); ([^"]+)",$', text, re.MULTILINE)
    assert bundle is not None and library is not None
    assert library.group(2) == "".join(bundle.groups()), "the two pins do not name one imgui-bundle"
    major, minor = (int(part) for part in library.group(1).split(".")[:2])
    assert (major, minor) >= typesetter.MINIMUM
    # The marker, as imtypeset's docs/releasing.md (section 5) gives it.
    assert library.group(3) == (
        "python_version >= '3.11' and python_version < '3.15' and "
        "((sys_platform == 'linux' and platform_machine == 'x86_64') or "
        "(sys_platform == 'darwin' and platform_machine == 'arm64'))"
    )
    pinned = f"imtypeset {library.group(1)}.{library.group(2)}"
    for path in (_CI, _MACOS):
        # Both files say which published file every job waits on. (For a few
        # hours on 2026-10-13 the sentence was "RED UNTIL ... IS ON PyPI":
        # the pin was written before imtypeset's first upload.)
        assert f"EVERY JOB NEEDS {pinned} FROM PyPI" in path.read_text("utf-8"), path.name


def test_the_sidecar_job_builds_the_pair_from_the_ref_and_runs_the_gate_with_it() -> None:
    """
    Until 2026-10-13 this was the `typeset` job and ran on every push. The
    same steps, in the job that is started by hand, with one more first: the
    installed imtypeset is taken out, because an installed one reads no
    variable and would be what `TYPESET=1` loads.
    """
    typeset = _workflow(_CI)["jobs"]["sidecar"]
    removal = next(s for s in _steps(typeset) if s["name"].startswith("Take the installed"))
    assert ".venv/bin/python -m pip uninstall -y imtypeset" in removal["run"]
    names = [step["name"] for step in _steps(typeset)]
    assert names.index("make bootstrap") < names.index(removal["name"])
    assert names.index(removal["name"]) < names.index("make check TYPESET=1")
    calls = [call for run in _runs(typeset) for call in _make_calls(run)]
    goals = [goals for goals, _ in calls]
    assert goals == [["bootstrap"], ["typeset-lib"], ["shot"], ["check"]]
    build, shot, check = calls[1][1], calls[2][1], calls[3][1]
    assert build["IMTYPESET_REF"] == "$PAIR_REF"
    assert set(build) == {"IMTYPESET_REF", "IMGUI_BUNDLE_CHECKOUT", "IMTYPESET_IMGUI_CLONE"}
    # imtypeset's T1: the runner has network, so the build is left to fetch the
    # wheel's own headers. Nothing in the workflow chooses, by either name.
    live = "\n".join(
        line
        for line in _CI.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "IMTYPESET_HEADERS" not in live and "IMTYPESET_BUNDLE_HEADERS" not in live
    assert "stand-in" not in live
    # imtypeset's T2: the library's file name is the build's; no step spells it.
    assert "libimtypeset_bundle" not in live
    assert shot["TYPESET"] == "1" and check == {"TYPESET": "1"}
    # A pair restored from the cache is held to the ref too, before the gate.
    which = next(s for s in _steps(typeset) if s["name"].startswith("Which pair the gate runs"))
    assert 'grep -qx "ref: $PAIR_REF" build/imtypeset-bundle/BUILT-FROM' in which["run"]
    assert which["env"]["PAIR_REF"] == "${{ steps.pair.outputs.ref }}"


def test_every_make_target_the_workflows_name_is_a_target_of_the_makefile() -> None:
    targets = _makefile_targets()
    assert {"bootstrap", "check", "typeset-lib", "shot"} <= targets  # the reading works at all
    calls = _all_make_calls(_workflow(_CI)) + _all_make_calls(_workflow(_MACOS))
    assert len(calls) >= 10
    for job, goals, _ in calls:
        assert goals, f"{job}: a `make` with no goal runs `help`"
        assert set(goals) <= targets, f"{job}: {sorted(set(goals) - targets)} is no target"


def test_no_make_is_missed_by_the_reading() -> None:
    """
    Every command holding the word `make` is `make ...`, `xvfb-run ... make ...`
    (both read as calls), or the package install that names the package.
    """
    for path in (_CI, _MACOS):
        workflow = _workflow(path)
        for name, job in workflow["jobs"].items():
            for run in _runs(job):
                holding = [command for command in _commands(run) if "make" in command]
                installs = [command for command in holding if command[:2] == ["sudo", "apt-get"]]
                assert len(holding) - len(installs) == len(_make_calls(run)), (path.name, name, run)
                assert all(command.count("make") == 1 for command in holding), (path.name, name)


def test_every_variable_handed_to_make_is_one_the_makefile_assigns() -> None:
    """
    A name the Makefile never assigns is accepted by `make` without a word and
    changes nothing, which is how a workflow would go on building the wrong
    thing. (`IMTYPESET_REF` came with `IMTYPESET_REPO` on 2026-10-11; against
    the Makefile of the commit before, 1eeb09e, this test and the next are
    red -- `.concerns/L1-CI-scripts/red_before_pkg.py` shows it.)

    `ARGS` is read by recipes and never assigned, so it is checked by use.
    """
    makefile = _MAKEFILE.read_text(encoding="utf-8")
    assigned = _makefile_variables()
    assert {"IMTYPESET_BUNDLE", "IMGUI_BUNDLE_CHECKOUT", "TYPESET"} <= assigned
    for job, _, variables in _all_make_calls(_workflow(_CI)):
        for name in variables:
            if name == "ARGS":
                assert "$(ARGS)" in makefile
                continue
            assert (
                name in assigned
            ), f"{job}: make is handed {name}=, which the Makefile never assigns"


def test_the_makefile_has_the_two_names_the_workflow_relies_on() -> None:
    """
    The workflow passes `IMTYPESET_REF` and relies on the DEFAULT of
    `IMTYPESET_REPO` being imtypeset on GitHub: there is no sibling checkout
    on a runner.
    """
    makefile = _MAKEFILE.read_text(encoding="utf-8")
    assert {"IMTYPESET_REPO", "IMTYPESET_REF"} <= _makefile_variables()
    default = re.search(r"^IMTYPESET_REPO\s*\?=\s*(\S+)", makefile, flags=re.MULTILINE)
    assert default is not None, "IMTYPESET_REPO has no `?=` default"
    assert IMTYPESET_URL in default.group(1), default.group(1)


def test_a_run_step_is_a_command_a_person_can_paste() -> None:
    """
    No workflow expression inside a `run:`; values arrive through `env:`.
    """
    for path in (_CI, _MACOS, _RELEASE):
        for name, job in _workflow(path)["jobs"].items():
            for run in _runs(job):
                assert "${{" not in run, (path.name, name, run)


def test_a_step_either_runs_or_uses_an_action_at_a_named_major_version() -> None:
    """
    In ci.yml and macos.yml, which publish nothing. In release.yml every
    action is named by a commit (2026-10-13; until then it named major
    versions too, which this test held it to): a tag can be moved, and that
    workflow is handed the right to publish.
    """
    for path in (_CI, _MACOS, _RELEASE):
        for name, job in _workflow(path)["jobs"].items():
            for step in _steps(job):
                assert ("run" in step) != ("uses" in step), (path.name, name, step)
                assert "name" in step, (path.name, name, step)
                if "uses" in step and path == _RELEASE:
                    assert re.fullmatch(r"[a-z-]+/[a-z-]+@[0-9a-f]{40}", step["uses"]), step
                elif "uses" in step:
                    assert re.fullmatch(r"actions/[a-z-]+(/[a-z-]+)?@v\d+", step["uses"]), step


def test_the_release_names_one_commit_for_each_action_and_says_which_version_it_is() -> None:
    """
    One action, one commit, wherever it is used in the file; and one of the
    two lines above each `uses` (the step's name may come between) says the
    version the commit was read as, because a hash alone tells a reader
    nothing.
    """
    lines = _RELEASE.read_text(encoding="utf-8").splitlines()
    commits: dict[str, set[str]] = {}
    for at, line in enumerate(lines):
        found = re.fullmatch(r"\s+uses: (\S+)@(\S+)", line)
        if found is None:
            continue
        commits.setdefault(found.group(1), set()).add(found.group(2))
        above = lines[at - 2 : at]
        assert any(re.fullmatch(r"\s+# v\d+\.\d+\.\d+", one) for one in above), above
    assert set(commits) == {
        "actions/checkout",
        "actions/setup-python",
        "actions/upload-artifact",
        "actions/download-artifact",
        "pypa/gh-action-pypi-publish",
    }
    assert all(len(found) == 1 for found in commits.values()), commits


def test_the_checkout_leaves_no_token_in_the_repository_the_build_fetches_from() -> None:
    """
    `make typeset-lib` fetches another repository with whatever git finds
    configured; imscribe's own token is not left where it would be sent along.
    """
    for name, job in _workflow(_CI)["jobs"].items():
        checkouts = [s for s in _steps(job) if s.get("uses", "").startswith("actions/checkout@")]
        assert len(checkouts) == 1, name
        assert checkouts[0]["with"]["persist-credentials"] == "false", name
    assert _workflow(_CI)["permissions"] == {"contents": "read"}


def test_window_tests_cannot_skip_unnoticed() -> None:
    """
    Every job runs the gate under a display, and stops before it if `unshare -rm`
    does not work: two test files start their own Xvfb in a user namespace and
    skip without one (tests/test_mouse_probe.py, tests/test_example_stream.py).
    """
    workflow = _workflow(_CI)
    assert workflow["env"]["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert workflow["env"]["GALLIUM_DRIVER"] == "llvmpipe"
    assert workflow["env"]["PYTEST_ADDOPTS"] == "-rs"  # the log names every skip and why
    # The display `xvfb-run` gives a job is the one the window tests use.
    assert workflow["env"]["IMSCRIBE_TEST_DISPLAY"] == "1"
    for name, job in workflow["jobs"].items():
        runs = _runs(job)
        gate = next(run for run in runs if re.search(r"\bmake check\b", run))
        assert gate.startswith("xvfb-run "), name
        before = runs[: runs.index(gate)]
        assert any(run.rstrip().endswith("\nunshare -rm true") for run in before), name


def test_the_window_fixture_prefers_its_own_xvfb_unless_the_display_is_asked_for() -> None:
    """
    `tests/conftest.py::choose_window`, the order the `window` fixture goes
    by since 2026-10-13 (a reachable `DISPLAY` used to win): its own Xvfb
    where one can be started, the session's display where it cannot (a Mac
    has no Xvfb) or where `IMSCRIBE_TEST_DISPLAY` asks, which the workflow
    does.
    """
    from conftest import DISPLAY_VARIABLE, choose_window

    assert DISPLAY_VARIABLE == "IMSCRIBE_TEST_DISPLAY"
    assert choose_window(asked=False, reachable=True, xvfb=True) == "xvfb"
    assert choose_window(asked=True, reachable=True, xvfb=True) == "display"
    assert choose_window(asked=True, reachable=False, xvfb=True) == "xvfb"
    assert choose_window(asked=False, reachable=True, xvfb=False) == "display"
    assert choose_window(asked=False, reachable=False, xvfb=True) == "xvfb"
    for asked in (False, True):
        assert choose_window(asked=asked, reachable=False, xvfb=False) is None


# ---------------------------------------------------------------------------
# the ref


def test_the_ref_file_holds_one_full_commit_hash() -> None:
    lines = _ref_lines()
    assert len(lines) == 1, lines
    assert re.fullmatch(r"[0-9a-f]{40}", lines[0]), lines[0]
    assert "HANDOFF-imtypeset.md" in _REF.read_text(encoding="utf-8")


def test_the_ref_is_the_one_the_handoff_names() -> None:
    """
    The handoff file is the channel to the imtypeset team and names the ref
    imscribe builds against by its short hash; the two move together.
    """
    handoff = _HANDOFF.read_text(encoding="utf-8")
    assert f"`{_ref_lines()[0][:7]}`" in handoff


def test_the_workflow_reads_the_ref_from_the_file_and_repeats_it_nowhere() -> None:
    ref = _ref_lines()[0]
    text = _CI.read_text(encoding="utf-8")
    assert ref not in text and ref[:7] not in text
    typeset = _workflow(_CI)["jobs"]["sidecar"]
    pair = next(step for step in _steps(typeset) if step.get("id") == "pair")
    assert "imtypeset.ref" in pair["run"] and 'echo "ref=$ref"' in pair["run"]
    build = next(step for step in _steps(typeset) if "make typeset-lib" in step.get("run", ""))
    assert build["env"]["PAIR_REF"] == "${{ steps.pair.outputs.ref }}"


def test_the_workflows_way_of_reading_the_ref_file_reads_the_ref() -> None:
    """
    The `sed` in the workflow is "the first line that is neither blank nor a
    comment"; said again in Python and held to the same answer.
    """
    typeset = _workflow(_CI)["jobs"]["sidecar"]
    pair = next(step for step in _steps(typeset) if step.get("id") == "pair")
    assert "sed -n '/^[^#[:space:]]/{p;q;}' imtypeset.ref" in pair["run"]
    first = next(
        line for line in _REF.read_text(encoding="utf-8").splitlines() if re.match(r"[^#\s]", line)
    )
    assert first == _ref_lines()[0]


def test_the_cache_of_the_built_pair_is_keyed_on_the_ref_and_on_the_wheel() -> None:
    typeset = _workflow(_CI)["jobs"]["sidecar"]
    restore = next(step for step in _steps(typeset) if step.get("id") == "cache")
    assert restore["uses"].startswith("actions/cache/restore@")
    assert restore["with"]["path"] == "build/imtypeset-bundle"
    key = restore["with"]["key"]
    for part in (
        "steps.pair.outputs.ref",
        "steps.pair.outputs.wheel",
        "_imgui_bundle*.so",
        "hashFiles('Makefile')",
        "runner.os",
        "runner.arch",
    ):
        assert part in key, part
    built = [s for s in _steps(typeset) if s.get("if") == "steps.cache.outputs.cache-hit != 'true'"]
    assert [("make typeset-lib" in s.get("run", "")) for s in built] == [False, True, False]
    assert built[2]["uses"].startswith("actions/cache/save@")
    assert built[2]["with"]["path"] == restore["with"]["path"]


# ---------------------------------------------------------------------------
# macos.yml


def test_the_macos_workflow_cannot_start_by_itself_and_says_what_it_waits_on() -> None:
    """
    Until 2026-10-13 its one job was switched off (`if: false`) and waited on
    H1 of HANDOFF-imtypeset.md. imtypeset answered H1 yes (a wheel for macOS
    arm64, its probe green on GitHub's runners), so the job is on: it still
    starts only by hand, it says it has never run, and it is the gate with no
    window (`make check`; the window tests skip there).
    """
    workflow = _workflow(_MACOS)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"] is None
    assert set(workflow["jobs"]) == {"check-macos"}
    for name, job in workflow["jobs"].items():
        assert "if" not in job, name
        assert job["runs-on"] == "macos-14", name  # arm64: where imtypeset has a wheel
        _assert_runs_once_per_supported_python(job, name)
        calls = [call for run in _runs(job) for call in _make_calls(run)]
        assert calls == [(["bootstrap"], {}), (["check"], {})], name
        assert ".venv/bin/python -P -m imscribe.typesetter" in "\n".join(_runs(job)), name
        assert "xvfb" not in "\n".join(_runs(job)) and "unshare" not in "\n".join(_runs(job))
    assert "never run" in workflow["name"]
    text = _MACOS.read_text(encoding="utf-8")
    assert "NEVER RUN" in text
    assert "H1 of HANDOFF-imtypeset.md" in text and "L1-MAC" in text


# ---------------------------------------------------------------------------
# release.yml


def _release() -> dict[str, Any]:
    return _workflow(_RELEASE)


def test_the_release_starts_for_a_pushed_tag_or_by_hand_and_for_no_branch() -> None:
    on = _release()["on"]
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": ["v*"]}, "a branch push must not start a release"
    assert on["workflow_dispatch"]["inputs"]["testpypi"]["default"] == "false"
    assert on["workflow_dispatch"]["inputs"]["testpypi"]["type"] == "boolean"
    # Nothing is granted to the workflow as a whole but reading the repository.
    assert _release()["permissions"] == {"contents": "read"}


def test_only_the_two_publishing_jobs_can_publish_and_each_only_for_its_own_event() -> None:
    """
    PyPI: a PUSHED tag `v...`, nothing else. TestPyPI: a run started by hand
    with the input set, nothing else. Each after the build job, each in its
    own environment, each with `id-token: write` and no other write.
    """
    jobs = _release()["jobs"]
    assert set(jobs) == {"build", "publish-pypi", "publish-testpypi"}
    uploads = {
        name: [step for step in _steps(job) if step.get("uses") == PUBLISH_ACTION]
        for name, job in jobs.items()
    }
    assert {name: len(steps) for name, steps in uploads.items()} == {
        "build": 0,
        "publish-pypi": 1,
        "publish-testpypi": 1,
    }
    assert "permissions" not in jobs["build"] and "environment" not in jobs["build"]
    assert "if" not in jobs["build"]

    pypi = jobs["publish-pypi"]
    assert pypi["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
    assert pypi["environment"] == {"name": "pypi", "url": "https://pypi.org/project/imscribe/"}
    assert "repository-url" not in uploads["publish-pypi"][0]["with"]

    rehearsal = jobs["publish-testpypi"]
    assert rehearsal["if"] == (
        "github.event_name == 'workflow_dispatch' && github.event.inputs.testpypi == 'true'"
    )
    assert rehearsal["environment"]["name"] == "testpypi"
    assert uploads["publish-testpypi"][0]["with"]["repository-url"] == (
        "https://test.pypi.org/legacy/"
    )

    for name in ("publish-pypi", "publish-testpypi"):
        job = jobs[name]
        assert job["needs"] == "build", name
        assert job["permissions"] == {"contents": "read", "id-token": "write"}, name
        assert job["runs-on"].startswith("ubuntu-"), "the publishing action runs on Linux only"
        assert uploads[name][0]["with"]["packages-dir"] == "upload", name
        # No token anywhere: Trusted Publishing is the run's own identity.
        assert "password" not in uploads[name][0]["with"], name
    text = _RELEASE.read_text(encoding="utf-8")
    assert "secrets." not in text and "PYPI_API_TOKEN" not in text


def test_the_release_builds_with_the_script_make_dist_runs_and_uploads_two_files() -> None:
    build = _release()["jobs"]["build"]
    names = [step["name"] for step in _steps(build)]
    runs = {step["name"]: step["run"] for step in _steps(build) if "run" in step}
    # What `make dist` runs, with the runner's interpreter (the Makefile's
    # recipe names ./.venv, which a runner does not have).
    recipe = _MAKEFILE.read_text(encoding="utf-8")
    assert "$(PY) -P scripts/make_dist.py --out" in recipe
    built = next(name for name in names if name.startswith("Build the commit twice"))
    assert runs[built] == "python -P scripts/make_dist.py --out dist --rev HEAD"
    # Only the wheel and the sdist: dist/ also holds .sha256 files and
    # BUILT-FROM, which an upload of the directory would stop on.
    files = next(name for name in names if name.startswith("The two files"))
    assert "cp dist/*.whl dist/*.tar.gz upload/" in runs[files]
    assert "python -m twine check --strict upload/*" in runs[files]
    kept = next(step for step in _steps(build) if step.get("uses", "").startswith("actions/upload"))
    assert kept["with"] == {"name": "dist", "path": "upload", "if-no-files-found": "error"}
    # The wheel is installed with its dependencies and asked for its library
    # BEFORE anything is kept for a publishing job.
    installed = next(name for name in names if name.startswith("Install the wheel"))
    assert runs[installed].rstrip().endswith("bin/python -P -m imscribe.typesetter")
    assert names.index(built) < names.index(files) < names.index(installed)
    assert names.index(installed) < names.index(kept["name"])
    # The system libraries imgui-bundle's extension loads are installed before
    # the wheel is asked for its library, and they are the ones the job that
    # runs the suite on the installed wheel installs (ci.yml, `typeset`).
    system = next(name for name in names if name.startswith("System libraries"))
    assert names.index(system) < names.index(installed)
    theirs = _apt_packages(_workflow(_CI)["jobs"]["typeset"])
    assert {"libx11-6", "libxext6", "libgl1"} <= theirs
    assert _apt_packages(build) == {package for package in theirs if package.startswith("lib")}
    for name in ("publish-pypi", "publish-testpypi"):
        fetched = _steps(_release()["jobs"][name])[0]
        assert fetched["uses"].startswith("actions/download-artifact@")
        assert fetched["with"] == {"name": "dist", "path": "upload"}, name


def _apt_packages(job: dict[str, Any]) -> set[str]:
    """What a job's `sudo apt-get install` commands name."""
    packages: set[str] = set()
    for run in _runs(job):
        for command in _commands(run):
            if command[:3] == ["sudo", "apt-get", "install"]:
                packages |= {word for word in command[3:] if not word.startswith("-")}
    return packages


def test_the_release_says_what_a_second_run_of_one_version_does() -> None:
    """
    `skip-existing` finishes an upload that stopped partway; it also lets a
    run for a version the index already holds go green having sent nothing.
    The file says so where the owner reads before pushing a tag.
    """
    jobs = _release()["jobs"]
    for name in ("publish-pypi", "publish-testpypi"):
        upload = next(step for step in _steps(jobs[name]) if step.get("uses") == PUBLISH_ACTION)
        assert upload["with"]["skip-existing"] == "true", name
    said = " ".join(
        line.lstrip("# ")
        for line in _RELEASE.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    )
    assert "GOES GREEN HAVING UPLOADED NOTHING" in said
    assert "`skip-existing: true`" in said


def test_a_tag_that_is_not_the_version_is_refused_before_anything_is_built() -> None:
    """
    The step's `sed` is said again in Python against the real pyproject.toml,
    and its comparison is run in a shell for the right tag and two wrong ones.
    """
    import subprocess

    build = _release()["jobs"]["build"]
    names = [step["name"] for step in _steps(build)]
    step = next(step for step in _steps(build) if step["name"] == "The tag is the version")
    assert step["if"] == "github.event_name == 'push'"
    assert step["env"] == {"RELEASE_TAG": "${{ github.ref_name }}"}
    assert names.index(step["name"]) < names.index(
        next(name for name in names if name.startswith("Build the commit twice"))
    )
    stated = re.search(r'^version = "(.*)"$', _PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    assert stated is not None

    def run(tag: str) -> int:
        done = subprocess.run(
            ["sh", "-e", "-c", step["run"]],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(_ROOT),
            env={"PATH": "/usr/bin:/bin", "RELEASE_TAG": tag},
        )
        if done.returncode == 0:
            assert f"pyproject.toml says {stated.group(1)}; the tag is {tag}" in done.stdout
        return done.returncode

    assert run(f"v{stated.group(1)}") == 0
    assert run(stated.group(1)) != 0, "a tag without the v"
    assert run(f"v{stated.group(1)}.post1") != 0
    assert run("v") != 0

"""
The CI workflow says what the Makefile can do, and names the pair in one place.

`.github/workflows/ci.yml` was written in a session that could not reach
GitHub, so it has never run. These tests hold it to everything that can be
checked from inside a checkout:

1.  It reads as YAML -- in a subset (below), because `./.venv` has no YAML
    parser and a dev dependency added for one test file is not worth it.
2.  Its triggers and its two jobs are the ones the gate is described by.
3.  Every `make <target>` it runs is a target of the `Makefile`, and every
    `NAME=value` it hands to `make` is a variable the `Makefile` assigns.
4.  The imtypeset ref is in ONE place, `imtypeset.ref`, as a full commit hash;
    the workflow reads it from there and repeats it nowhere, and it is the ref
    `HANDOFF-imtypeset.md` names.
5.  Every `run:` is a command a person can paste into a shell: no workflow
    expression inside one.
6.  The macOS file cannot start by itself.

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
import re
import shlex
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = _ROOT / ".github" / "workflows"
_CI = _WORKFLOWS / "ci.yml"
_MACOS = _WORKFLOWS / "macos.yml"
_MAKEFILE = _ROOT / "Makefile"
_REF = _ROOT / "imtypeset.ref"
_HANDOFF = _ROOT / "HANDOFF-imtypeset.md"

IMTYPESET_URL = "github.com/WalterCReel3/imtypeset"


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


@pytest.mark.parametrize("path", [_CI, _MACOS], ids=lambda p: p.name)
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
    workflow = _workflow(_CI)
    assert set(workflow["on"]) == {"push", "pull_request"}
    for event in ("push", "pull_request"):
        assert workflow["on"][event] == {"branches": ["main", "experimental/**"]}, event


def test_the_workflow_has_the_two_gates_on_ubuntu_with_python_3_11() -> None:
    workflow = _workflow(_CI)
    assert set(workflow["jobs"]) == {"plain", "typeset"}
    for name, job in workflow["jobs"].items():
        assert job["runs-on"].startswith("ubuntu-"), name
        pythons = [
            step["with"]["python-version"]
            for step in _steps(job)
            if step.get("uses", "").startswith("actions/setup-python@")
        ]
        assert pythons == ["3.11"], name
        # A job with no limit holds a runner for six hours when a window hangs.
        assert int(job["timeout-minutes"]) <= 60, name


def test_the_plain_job_is_bootstrap_then_check_and_never_meets_imtypeset() -> None:
    """
    `make check` with no library must pass with no imtypeset anywhere.

    So the plain job builds nothing of it, opts into nothing, and has a step
    that fails if a checkout, a built pair, either variable or an installed
    distribution is there after all. (When imtypeset becomes a declared
    dependency of advtext, that step goes red and the job's meaning has to be
    decided again; that is what it is for.)
    """
    plain = _workflow(_CI)["jobs"]["plain"]
    goals = [goals for run in _runs(plain) for goals, _ in _make_calls(run)]
    variables = [variables for run in _runs(plain) for _, variables in _make_calls(run)]
    assert goals == [["bootstrap"], ["check"]]
    assert variables == [{}, {}]
    text = "\n".join(_runs(plain))
    assert "typeset-lib" not in text and "TYPESET=" not in text
    guard = next(
        step["run"] for step in _steps(plain) if step.get("name") == "No imtypeset anywhere"
    )
    for needle in (
        "test ! -e ../imtypeset",
        "IMTYPESET_LIBRARY",
        "IMTYPESET_PYTHON",
        'find_spec("imtypeset")',
    ):
        assert needle in guard, needle
    names = [step.get("name") for step in _steps(plain)]
    assert names.index("No imtypeset anywhere") < names.index("make check")


def test_the_typeset_job_builds_the_pair_from_the_ref_and_runs_the_gate_with_it() -> None:
    typeset = _workflow(_CI)["jobs"]["typeset"]
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
    assert len(calls) >= 8
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
    for path in (_CI, _MACOS):
        for name, job in _workflow(path)["jobs"].items():
            for run in _runs(job):
                assert "${{" not in run, (path.name, name, run)


def test_a_step_either_runs_or_uses_an_action_at_a_named_major_version() -> None:
    for path in (_CI, _MACOS):
        for name, job in _workflow(path)["jobs"].items():
            for step in _steps(job):
                assert ("run" in step) != ("uses" in step), (path.name, name, step)
                assert "name" in step, (path.name, name, step)
                if "uses" in step:
                    assert re.fullmatch(r"actions/[a-z-]+(/[a-z-]+)?@v\d+", step["uses"]), step


def test_the_checkout_leaves_no_token_in_the_repository_the_build_fetches_from() -> None:
    """
    `make typeset-lib` fetches another repository with whatever git finds
    configured; advtext's own token is not left where it would be sent along.
    """
    for name, job in _workflow(_CI)["jobs"].items():
        checkouts = [s for s in _steps(job) if s.get("uses", "").startswith("actions/checkout@")]
        assert len(checkouts) == 1, name
        assert checkouts[0]["with"]["persist-credentials"] == "false", name
    assert _workflow(_CI)["permissions"] == {"contents": "read"}


def test_window_tests_cannot_skip_unnoticed() -> None:
    """
    Both jobs run the gate under a display, and stop before it if `unshare -rm`
    does not work: two test files start their own Xvfb in a user namespace and
    skip without one (tests/test_mouse_probe.py, tests/test_example_stream.py).
    """
    workflow = _workflow(_CI)
    assert workflow["env"]["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert workflow["env"]["GALLIUM_DRIVER"] == "llvmpipe"
    assert workflow["env"]["PYTEST_ADDOPTS"] == "-rs"  # the log names every skip and why
    for name, job in workflow["jobs"].items():
        runs = _runs(job)
        gate = next(run for run in runs if re.search(r"\bmake check\b", run))
        assert gate.startswith("xvfb-run "), name
        before = runs[: runs.index(gate)]
        assert any(run.rstrip().endswith("\nunshare -rm true") for run in before), name


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
    advtext builds against by its short hash; the two move together.
    """
    handoff = _HANDOFF.read_text(encoding="utf-8")
    assert f"`{_ref_lines()[0][:7]}`" in handoff


def test_the_workflow_reads_the_ref_from_the_file_and_repeats_it_nowhere() -> None:
    ref = _ref_lines()[0]
    text = _CI.read_text(encoding="utf-8")
    assert ref not in text and ref[:7] not in text
    typeset = _workflow(_CI)["jobs"]["typeset"]
    pair = next(step for step in _steps(typeset) if step.get("id") == "pair")
    assert "imtypeset.ref" in pair["run"] and 'echo "ref=$ref"' in pair["run"]
    build = next(step for step in _steps(typeset) if "make typeset-lib" in step.get("run", ""))
    assert build["env"]["PAIR_REF"] == "${{ steps.pair.outputs.ref }}"


def test_the_workflows_way_of_reading_the_ref_file_reads_the_ref() -> None:
    """
    The `sed` in the workflow is "the first line that is neither blank nor a
    comment"; said again in Python and held to the same answer.
    """
    typeset = _workflow(_CI)["jobs"]["typeset"]
    pair = next(step for step in _steps(typeset) if step.get("id") == "pair")
    assert "sed -n '/^[^#[:space:]]/{p;q;}' imtypeset.ref" in pair["run"]
    first = next(
        line for line in _REF.read_text(encoding="utf-8").splitlines() if re.match(r"[^#\s]", line)
    )
    assert first == _ref_lines()[0]


def test_the_cache_of_the_built_pair_is_keyed_on_the_ref_and_on_the_wheel() -> None:
    typeset = _workflow(_CI)["jobs"]["typeset"]
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
    workflow = _workflow(_MACOS)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["jobs"]
    for name, job in workflow["jobs"].items():
        assert job["if"] == "false", name
        assert job["runs-on"].startswith("macos-"), name
    text = _MACOS.read_text(encoding="utf-8")
    assert "H1 of HANDOFF-imtypeset.md" in text and "L1-MAC" in text

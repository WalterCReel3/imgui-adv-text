"""
`imscribe.typesetter`: which imtypeset is found, by which route, and what `pairing()` says.

The order under test (`imscribe/typesetter.py`, "Loading, gated"):

1.  `IMTYPESET_LIBRARY` set: the environment route, as it always was.
2.  otherwise an installed `imtypeset` DISTRIBUTION -- one `importlib.metadata`
    finds -- imported with no variable set.
3.  otherwise nothing, and `reason()` is the sentence it always was.

**A distribution exists since 2026-10-13** (imtypeset 0.4.1.192900, a
dependency in `pyproject.toml`), and where it is installed the last section
here loads it with no variable set, as a user's process does. The routing is
still tested with stand-ins the tests build in a temporary directory, in
children from which an imtypeset in site-packages is HIDDEN
(`tests/data/not_installed/sitecustomize.py`; `_without`): it would be found
before or instead of every stand-in. What they stand in for is this contract,
which is the whole of what imscribe assumes:

    With IMTYPESET_LIBRARY unset, `importlib.metadata.distribution("imtypeset")`
    finds the distribution, `import imtypeset` succeeds or raises ImportError
    with a sentence, and `imtypeset.host_info()` then names the library the
    distribution carries.

Two stand-ins:

- **a package of two functions** and a `dist-info`, with no library at all.
  It runs in both gates and holds the routing: who is asked, in what order,
  what is remembered, what `pairing()` reports from `host_info()`. Since
  `module()` holds what it imports to `typesetter.REQUIRED`, the stand-in
  also has every name of that list, as a name and nothing more (`standin`
  writes them from the list itself; `tests/test_typesetter_kinds.py` is
  where one that LACKS a name is tried).
- **the pinned pair, wrapped** (with the library `make typeset-lib` builds
  only -- a library and a package directory that holds none; skipped, with
  the reason, without it and where the session's library is an installed
  distribution): a package named `imtypeset` that carries a library
  inside its own directory, names it to the real package's loader for the
  length of the import, and is otherwise the real package. That one goes the
  whole way -- the import gate, a context, fonts -- with neither variable in
  the environment.

Every routing test runs in a fresh interpreter: an `imtypeset` in
`sys.modules` is exactly the state these tests are about, and the pytest
process must not be left in it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

import imscribe
from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
# On every child's path: an imtypeset in site-packages is hidden from the
# child while `_HIDDEN` is in its environment, unless the child was handed the
# installed library by name (`tests/data/not_installed/sitecustomize.py`).
# `tests/conftest.py` hides it from this process by the same rule.
_HIDE = _ROOT / "tests" / "data" / "not_installed"
_HIDDEN = "IMSCRIBE_TEST_NO_INSTALLED_IMTYPESET"
_KEYS = {
    "imscribe_version",
    "route",
    "reason",
    "kind",
    "library",
    "package",
    "distribution",
    "imtypeset_version",
    "imgui_version",
    "wheel_version",
    "built_for",
    "headers",
    "accepted_by",
    "imtypeset_kind",
    "imtypeset_route",
    "ignored_environment",
    "named_by",
}

_REPORT = """
import json, sys
from imscribe import typesetter
before = sorted(n for n in sys.modules if n.split(".")[0] == "imtypeset")
first = typesetter.pairing()
loaded = typesetter.module()
print(json.dumps({
    "before": before,
    "pairing": first,
    "again": typesetter.pairing(),
    "module": loaded is not None,
    "reason": typesetter.reason(),
    "trouble": typesetter.trouble(),
    "imtypeset": sorted(n for n in sys.modules if n.split(".")[0] == "imtypeset"),
    "imgui": "imgui_bundle" in sys.modules,
    "path": [p for p in sys.path if p.endswith("appended")],
}))
"""


def _child(code: str, env: dict[str, str], *path: Path) -> dict[str, Any]:
    """
    Run `code` in a fresh interpreter with `path` importable, and read the JSON it prints last.
    """
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**env, "PYTHONPATH": os.pathsep.join([str(_ROOT), str(_HIDE), *map(str, path)])},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return report


def _without() -> dict[str, str]:
    """
    An environment in which imscribe finds what the TEST puts there and nothing else.

    Neither variable; not `IMSCRIBE_NO_TYPESET` (`tests/conftest.py` sets it
    for the session, and these children are to LOOK); and an imtypeset in
    site-packages hidden, so that "nothing installed" is true in a
    virtualenv that has one.
    """
    dropped = (*_VARIABLES, typesetter.DISABLE_VARIABLE)
    return {
        **{name: value for name, value in os.environ.items() if name not in dropped},
        _HIDDEN: "1",
    }


def _as_a_user() -> dict[str, str]:
    """
    The environment of a process nobody prepared: no variable of either project, nothing hidden.
    """
    dropped = (*_VARIABLES, typesetter.DISABLE_VARIABLE, _HIDDEN)
    return {name: value for name, value in os.environ.items() if name not in dropped}


_TWO_FUNCTIONS = """
import os
LOADED_WITH = os.environ.get("IMTYPESET_LIBRARY")
def version():
    return "0.9.0"
def host_info():
    return {
        "host": "imgui_bundle",
        "library": os.path.join(os.path.dirname(__file__), "libimtypeset_bundle.so"),
        "imgui_version": "1.92.9",
        "imtypeset_version": "0.9.0",
        "bundle": {
            "headers": "fork:0123abc",
            "wheel_version": "1.92.900",
            "accepted_by": "imgui-check+probe",
        },
    }
"""


def _metadata(site: Path, version: str = "0.9.0", requires: str = "imgui-bundle==1.92.900") -> None:
    info = site / f"imtypeset-{version}.dist-info"
    info.mkdir(parents=True)
    lines = ["Metadata-Version: 2.1", "Name: imtypeset", f"Version: {version}"]
    lines += [f"Requires-Dist: {requires}"] if requires else []
    (info / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")


def standin(source: str = _TWO_FUNCTIONS, without: tuple[str, ...] = (), **fields: Any) -> str:
    """
    The source of a package that has every name of `typesetter.REQUIRED`, and then `source`.

    The names are written from the list, so the stand-in cannot fall behind
    it: a function for a name of the package, a class holding its names for
    an owner, a tuple type in imscribe's field order where the library reads
    by position. `without` leaves names out, spelled as `typesetter.missing`
    spells them (`"stats"`, `"Document.pack_marks"`); `fields` gives a tuple
    type other fields (`Block=("text", "kind")`). `source` comes last and so
    wins: what a test says of `host_info` is what the package answers.
    """
    lines = ["import collections"]
    owners = set(typesetter.REQUIRED) - {""}
    for name in typesetter.REQUIRED[""]:
        if name in without:
            continue
        if name in typesetter._IN_ORDER:
            given = tuple(fields.get(name, typesetter._IN_ORDER[name]))
            made = f"collections.namedtuple({name!r}, {given!r}, defaults=(0,) * {len(given)})"
            lines.append(f"{name} = {made}")
        elif name in owners:
            lines.append(f"class {name}:")
            lines += [
                f"    {member} = 0"
                for member in typesetter.REQUIRED[name]
                if f"{name}.{member}" not in without
            ] or ["    pass"]
        else:
            lines.append(f"def {name}(*args, **kwargs):\n    return None")
    return "\n".join(lines) + "\n" + source


def _a_package(site: Path, source: str = _TWO_FUNCTIONS, without: tuple[str, ...] = ()) -> None:
    (site / "imtypeset").mkdir(parents=True)
    (site / "imtypeset" / "__init__.py").write_text(standin(source, without), encoding="utf-8")
    if "demo" not in without:
        (site / "imtypeset" / "demo.py").write_text("", encoding="utf-8")


def _a_distribution(
    tmp_path: Path, source: str = _TWO_FUNCTIONS, without: tuple[str, ...] = ()
) -> Path:
    """
    What `pip install imtypeset` is asked to leave in a site directory: a
    package, and the metadata that says it was installed.
    """
    site = tmp_path / "site"
    _a_package(site, source, without)
    _metadata(site)
    return site


# ---------------------------------------------------------------------------
# Route 3: nothing
# ---------------------------------------------------------------------------


def test_with_nothing_to_find_the_pairing_is_all_none_and_nothing_is_imported() -> None:
    report = _child(_REPORT, _without())
    assert report["module"] is False
    assert report["reason"] == typesetter.ABSENT_REASON
    assert set(report["pairing"]) == _KEYS
    assert report["pairing"].pop("route") == typesetter.ROUTE_NONE
    assert report["pairing"].pop("reason") == typesetter.ABSENT_REASON
    assert report["pairing"].pop("kind") == typesetter.Kind.NOT_INSTALLED.value
    # The one key that is about imscribe and not about what was found.
    assert report["pairing"].pop("imscribe_version") == imscribe.__version__
    assert set(report["pairing"].values()) == {None}, report["pairing"]
    assert report["imtypeset"] == [] and report["imgui"] is False
    assert report["trouble"] == ""


def test_a_package_on_the_path_that_is_not_installed_is_not_a_distribution(tmp_path: Path) -> None:
    """
    A source directory of imtypeset on `sys.path` -- which is what the
    environment route leaves behind in a process, and what a developer's
    PYTHONPATH may hold -- is importable and carries no library. Without
    metadata it is not asked: not imported, and the sentence is the old one.
    """
    source = tmp_path / "checkout" / "python"
    (source / "imtypeset").mkdir(parents=True)
    (source / "imtypeset" / "__init__.py").write_text(
        "raise ImportError('imtypeset: IMTYPESET_LIBRARY is not set. It names ...')\n",
        encoding="utf-8",
    )
    report = _child(_REPORT, _without(), source)
    assert report["module"] is False
    assert report["reason"] == typesetter.ABSENT_REASON
    assert report["imtypeset"] == [], "a package that is not a distribution was imported"
    assert report["pairing"]["route"] == typesetter.ROUTE_NONE
    assert report["pairing"]["distribution"] is None


# ---------------------------------------------------------------------------
# Route 2: an installed distribution
# ---------------------------------------------------------------------------


def test_an_installed_distribution_is_loaded_with_no_variable_set(tmp_path: Path) -> None:
    site = _a_distribution(tmp_path)
    report = _child(_REPORT, _without(), site)
    assert report["before"] == [], "importing imscribe.typesetter imported imtypeset"
    assert report["module"] is True and report["reason"] == ""
    assert report["imtypeset"] == ["imtypeset"]
    assert report["path"] == [], "sys.path was touched on the distribution route"
    assert report["pairing"] == {
        "imscribe_version": imscribe.__version__,
        "route": typesetter.ROUTE_DISTRIBUTION,
        "reason": "",
        "kind": typesetter.Kind.READY.value,
        "library": str(site / "imtypeset" / "libimtypeset_bundle.so"),
        "package": str(site / "imtypeset"),
        "distribution": "imtypeset 0.9.0",
        "imtypeset_version": "0.9.0",
        "imgui_version": "1.92.9",
        "wheel_version": "1.92.900",
        "built_for": "imgui-bundle==1.92.900",
        "headers": "fork:0123abc",
        "accepted_by": "imgui-check+probe",
        "imtypeset_kind": None,
        "imtypeset_route": None,
        "ignored_environment": None,
        "named_by": None,
    }
    assert report["again"] == report["pairing"]
    assert set(report["pairing"]) == _KEYS and report["trouble"] == ""


def test_a_distribution_that_refuses_is_a_sentence_that_names_it(tmp_path: Path) -> None:
    """
    The contract's other half: what does not load raises ImportError with a
    sentence. The sentence reaches `reason()` with which thing refused in
    front of it, because "IMTYPESET_LIBRARY is not set" from an installed
    package would send the reader to the wrong fix.
    """
    refusal = "imtypeset: built for imgui_bundle 1.92.900, and 1.93.0 is installed"
    site = _a_distribution(tmp_path, f"raise ImportError({refusal!r})\n")
    report = _child(_REPORT, _without(), site)
    assert report["module"] is False
    assert report["reason"] == f"the installed imtypeset 0.9.0 did not load: ImportError: {refusal}"
    assert report["pairing"]["route"] == typesetter.ROUTE_NONE
    assert report["pairing"]["reason"] == report["reason"]
    assert report["pairing"]["kind"] == typesetter.Kind.REFUSED.value
    assert report["pairing"]["distribution"] == "imtypeset 0.9.0"
    assert report["pairing"]["library"] is None and report["pairing"]["built_for"] is None
    assert report["pairing"]["imtypeset_kind"] is None, "a refusal that carries no kind has none"


# -- imtypeset's own word for a refusal (its commit 03b5cd4 on: `ImportError.kind`) --

_SENTENCE = (
    "imtypeset 0.3.0 was built for imgui-bundle 1.92.900, and this application has "
    "imgui-bundle 1.93.0. The two are updated together."
)
_DETAIL = "'/site/imgui_bundle/_imgui_bundle.so' is not sha256 0123 nor elf-load:4567"

# What `imtypeset._bundle.refusal` makes: a plain ImportError whose first line
# is a sentence, with the paths on the lines after it and three attributes.
_REFUSES = """
error = ImportError("imtypeset: " + {sentence!r} + "\\n" + {detail!r}, name="imtypeset")
error.kind, error.sentence, error.detail = {kind!r}, {sentence!r}, {detail!r}
raise error
"""


@pytest.mark.parametrize(
    ("theirs", "ours"),
    [
        ("bundle-mismatch", typesetter.Kind.REFUSED),
        ("damaged", typesetter.Kind.REFUSED),
        ("package-mismatch", typesetter.Kind.REFUSED),
        ("layout", typesetter.Kind.REFUSED),
        ("unchecked", typesetter.Kind.REFUSED),
        ("a-word-of-a-later-release", typesetter.Kind.REFUSED),
        ("wrong-platform", typesetter.Kind.UNSUPPORTED),
        ("no-library", typesetter.Kind.NOT_INSTALLED),
    ],
)
def test_a_refusal_that_carries_a_kind_is_carried_and_decides_imscribes_kind(
    theirs: str, ours: typesetter.Kind, tmp_path: Path
) -> None:
    """
    imtypeset's T4 and its answer to H26. The word is `pairing()["imtypeset_kind"]`
    as it was given; imscribe's own kind is `unsupported` for a package built
    for another system, `not-installed` for one that carries no library, and
    `refused` for every other word, one it has never heard included. The
    reason is the sentence alone: the line of paths is for a log.
    """
    source = _REFUSES.format(kind=theirs, sentence=_SENTENCE, detail=_DETAIL)
    site = _a_distribution(tmp_path, source)
    code = (
        _REPORT
        + "print(json.dumps([typesetter.kind().value, typesetter.EXIT_CODES[typesetter.kind()]]))"
    )
    assert _child(code, _without(), site) == [ours.value, typesetter.EXIT_CODES[ours]]
    report = _child(_REPORT, _without(), site)
    assert report["module"] is False
    assert report["pairing"]["imtypeset_kind"] == theirs
    assert report["pairing"]["kind"] == ours.value
    assert report["reason"] == (
        f"the installed imtypeset 0.9.0 did not load: ImportError: imtypeset: {_SENTENCE}"
    )
    assert "\n" not in report["reason"] and _DETAIL not in report["reason"]
    assert report["pairing"]["route"] == typesetter.ROUTE_NONE
    assert report["again"] == report["pairing"]


def test_a_named_library_refused_with_a_kind_says_the_sentence_and_the_word(tmp_path: Path) -> None:
    """
    The same by the environment route, where nothing is put in front of the
    sentence; and the paths are logged, once, with the word.
    """
    source = _REFUSES.format(kind="damaged", sentence=_SENTENCE, detail=_DETAIL)
    package = tmp_path / "appended"
    _a_package(package, source)
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(tmp_path / "a-library")
    env[typesetter.PACKAGE_VARIABLE] = str(package)
    result = subprocess.run(
        [sys.executable, "-B", "-c", _REPORT],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**env, "PYTHONPATH": os.pathsep.join([str(_ROOT), str(_HIDE)])},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reason"] == f"ImportError: imtypeset: {_SENTENCE}"
    assert report["pairing"]["kind"] == typesetter.Kind.REFUSED.value
    assert report["pairing"]["imtypeset_kind"] == "damaged"
    assert result.stderr.count(f"imtypeset says of that refusal (damaged): {_DETAIL}") == 1


# -- known by its attestation, with no metadata (imtypeset's T5: a frozen application) --
#
# The stand-in says it is imtypeset 0.4.1. Until 2026-10-13 it said 0.3.0 (the
# version that first carried an attestation); a library of that version is
# now refused for its age (`typesetter.MINIMUM`), which is tested at the end
# of this file and is not what these tests are about.

_INSTALLED = """
import os
def host_info():
    return {
        "library": os.path.join(os.path.dirname(__file__), "the-library"),
        "route": "installed",
        "imgui_version": "1.92.9",
        "imtypeset_version": "0.4.1",
        "bundle": {
            "headers": "fork:0123abc",
            "wheel_version": "1.92.900",
            "accepted_by": "imgui-check+probe",
            "built_for": {"wheel_version": "1.92.900"},
        },
    }
"""


@pytest.mark.parametrize(
    ("attestation", "distribution"),
    [
        ('{"schema": 1, "distribution_version": "0.3.0.192900"}', "imtypeset 0.3.0.192900"),
        ('{"schema": 1, "distribution_version": ""}', "imtypeset"),
        ("not json at all", "imtypeset"),
    ],
    ids=["a version", "no version", "unreadable"],
)
def test_a_package_that_carries_an_attestation_is_a_distribution_without_metadata(
    attestation: str, distribution: str, tmp_path: Path
) -> None:
    """
    What a freezer leaves of an installed imtypeset: the package, the library
    and `_attestation.json` inside it, and no `dist-info`. It is loaded with
    no variable set; what the metadata would have said comes from the file
    and from the library's own record. A file imscribe cannot read still marks
    the package: whether it is damaged is the package's gate to say.
    """
    site = tmp_path / "site"
    _a_package(site, _INSTALLED)
    (site / "imtypeset" / "_attestation.json").write_text(attestation, encoding="utf-8")
    report = _child(_REPORT, _without(), site)
    assert report["before"] == [], "looking for the attestation imported imtypeset"
    assert report["module"] is True and report["reason"] == ""
    assert report["path"] == [] and report["trouble"] == ""
    assert report["pairing"] == {
        "imscribe_version": imscribe.__version__,
        "route": typesetter.ROUTE_DISTRIBUTION,
        "reason": "",
        "kind": typesetter.Kind.READY.value,
        "library": str(site / "imtypeset" / "the-library"),
        "package": str(site / "imtypeset"),
        "distribution": distribution,
        "imtypeset_version": "0.4.1",
        "imgui_version": "1.92.9",
        "wheel_version": "1.92.900",
        "built_for": "imgui-bundle==1.92.900",
        "headers": "fork:0123abc",
        "accepted_by": "imgui-check+probe",
        "imtypeset_kind": None,
        "imtypeset_route": "installed",
        "ignored_environment": None,
        "named_by": None,
    }
    assert report["again"] == report["pairing"]


def test_metadata_is_what_built_for_and_the_version_are_read_from_when_there_is_some(
    tmp_path: Path,
) -> None:
    """
    With both, as `pip install` leaves them, nothing changes: the metadata's
    version and its `Requires-Dist`, not the attestation's.
    """
    site = _a_distribution(tmp_path, _INSTALLED)
    (site / "imtypeset" / "_attestation.json").write_text(
        '{"schema": 1, "distribution_version": "9.9.9"}', encoding="utf-8"
    )
    info = site / "imtypeset-0.9.0.dist-info" / "METADATA"
    info.write_text(
        info.read_text(encoding="utf-8").replace("==1.92.900", "==1.92.801"), encoding="utf-8"
    )
    report = _child(_REPORT, _without(), site)
    assert report["pairing"]["distribution"] == "imtypeset 0.9.0"
    assert report["pairing"]["built_for"] == "imgui-bundle==1.92.801"
    assert report["pairing"]["imtypeset_route"] == "installed"


@pytest.mark.parametrize(
    ("requires", "expected"),
    [
        ("imgui_bundle ==1.92.900 ; python_version >= '3.11'", "imgui_bundle ==1.92.900"),
        ("fonttools>=4", None),
        ("", None),
    ],
    ids=["spelled otherwise", "another requirement", "none"],
)
def test_built_for_is_what_the_distribution_declares_and_none_when_it_declares_nothing(
    requires: str, expected: str | None, tmp_path: Path
) -> None:
    site = tmp_path / "site"
    _a_package(site)
    _metadata(site, requires=requires)
    report = _child(_REPORT, _without(), site)
    assert report["pairing"]["route"] == typesetter.ROUTE_DISTRIBUTION
    assert report["pairing"]["built_for"] == expected


def test_a_package_that_cannot_answer_is_a_trouble_and_not_an_exception(tmp_path: Path) -> None:
    site = _a_distribution(tmp_path, "def host_info():\n    raise KeyError('bundle')\n")
    report = _child(_REPORT, _without(), site)
    assert report["module"] is True
    assert report["pairing"]["route"] == typesetter.ROUTE_DISTRIBUTION
    assert report["pairing"]["package"] == str(site / "imtypeset")
    assert report["pairing"]["library"] is None and report["pairing"]["headers"] is None
    assert report["trouble"] == "pairing: KeyError: 'bundle'"


# ---------------------------------------------------------------------------
# Route 1 wins
# ---------------------------------------------------------------------------


def test_the_variable_wins_over_an_installed_distribution(tmp_path: Path) -> None:
    """
    The development override. What is held: the route is the environment's,
    the package's directory is appended as before, and `built_for` -- a claim
    of the distribution about ITS library -- is not made about another one.

    What this also shows and does not fix: with both an installed package and
    `IMTYPESET_PYTHON`, the INSTALLED package is the one imported (the
    directory goes on the end of `sys.path`, as it always has), and it is
    handed the variable's library. `pairing()["package"]` is where that can
    be seen.
    """
    site = _a_distribution(tmp_path)
    appended = tmp_path / "appended"
    (appended / "imtypeset").mkdir(parents=True)
    (appended / "imtypeset" / "__init__.py").write_text("OTHER = True\n", encoding="utf-8")
    library = tmp_path / "dev" / "libimtypeset_bundle.so"
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(library)
    env[typesetter.PACKAGE_VARIABLE] = str(appended)
    report = _child(_REPORT + "print(json.dumps(sys.modules['imtypeset'].LOADED_WITH))", env, site)
    assert report == str(library), "the installed package was not handed the variable"
    report = _child(_REPORT, env, site)
    assert report["module"] is True
    assert report["path"] == [str(appended)]
    assert report["pairing"]["route"] == typesetter.ROUTE_ENVIRONMENT
    assert report["pairing"]["built_for"] is None
    assert report["pairing"]["distribution"] == "imtypeset 0.9.0"
    assert report["pairing"]["package"] == str(site / "imtypeset")


def test_an_installed_package_that_ignores_the_variables_is_not_reported_as_the_environment(
    tmp_path: Path,
) -> None:
    """
    imtypeset's T8, from its v0.3.0 on: a package directory that holds a
    library or an attestation reads neither variable, and says which were set
    (`host_info()["ignored_environment"]`). The route is then the
    distribution's, whatever the environment asked for, the names are in
    `pairing()["ignored_environment"]`, and nothing is remembered as a pair
    the environment named: the variables chose nothing.
    """
    ignoring = _INSTALLED.replace(
        '"route": "installed",',
        '"route": "installed",\n'
        '        "ignored_environment": ["IMTYPESET_LIBRARY", "IMTYPESET_PYTHON"],',
    )
    site = _a_distribution(tmp_path, ignoring)
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(tmp_path / "dev" / "another-library")
    env[typesetter.PACKAGE_VARIABLE] = str(tmp_path / "appended")
    report = _child(
        _REPORT + "print(json.dumps([typesetter.pairing(), typesetter._pair]))", env, site
    )
    found, remembered = report
    assert found["kind"] == typesetter.Kind.READY.value
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["imtypeset_route"] == "installed"
    assert found["ignored_environment"] == "IMTYPESET_LIBRARY, IMTYPESET_PYTHON"
    assert found["library"] == str(site / "imtypeset" / "the-library")
    assert found["named_by"] is None and remembered is None
    assert found["built_for"] == "imgui-bundle==1.92.900", "it IS the distribution's library"


# ---------------------------------------------------------------------------
# The pair the environment named, remembered (pptmstr's P33)
# ---------------------------------------------------------------------------

# A package that answers the library it was imported with, so that a test can
# see which value of the variable an import met.
_NAMED = """
import os
LOADED_WITH = os.environ.get("IMTYPESET_LIBRARY")
def host_info():
    return {"library": LOADED_WITH, "route": "IMTYPESET_LIBRARY", "ignored_environment": []}
"""

# pptmstr's sequence: the variables are set for the first `module()` and then
# taken out of the process, so that what it launches does not inherit them.
_REMOVED = """
import json, os, sys
from imscribe import typesetter
first = typesetter.module()
report = {"first": typesetter.pairing()}
for name in ("IMTYPESET_LIBRARY", "IMTYPESET_PYTHON"):
    del os.environ[name]
def state():
    return {
        "module": typesetter.module() is not None,
        "same": typesetter.module() is first,
        "pairing": typesetter.pairing(),
        "trouble": typesetter.trouble(),
        "environment": sorted(n for n in os.environ if n.startswith("IMTYPESET_")),
        "with": getattr(sys.modules.get("imtypeset"), "LOADED_WITH", None),
    }
"""


def _named(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    """
    An environment that names a stand-in pair: (the environment, the library, the directory).
    """
    appended = tmp_path / "appended"
    _a_package(appended, _NAMED)
    library = tmp_path / "dev" / "libimtypeset_bundle.so"
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(library)
    env[typesetter.PACKAGE_VARIABLE] = str(appended)
    return env, library, appended


def test_a_reset_after_the_variables_were_removed_finds_the_pair_the_first_load_found(
    tmp_path: Path,
) -> None:
    """
    P33 as pptmstr wrote it: it sets the two variables for its own process,
    asks `module()` once, and removes them; a "try again" (`reset()`) then
    found no library, because the variables were asked again. The pair the
    first load found is remembered, the next `module()` uses it, and
    `pairing()["named_by"]` says that it is remembered and not the
    environment's. The variables are not put back.
    """
    env, library, appended = _named(tmp_path)
    code = _REMOVED + (
        "typesetter.reset()\n"
        "report['reset'] = state()\n"
        "typesetter.disable('a draw raised')\n"
        "typesetter.reset()\n"
        "report['disabled'] = state()\n"
        "print(json.dumps(report))\n"
    )
    report = _child(code, env)
    first = report["first"]
    assert first["kind"] == typesetter.Kind.READY.value, first["reason"]
    assert first["route"] == typesetter.ROUTE_ENVIRONMENT and first["named_by"] == "environment"
    assert first["library"] == str(library) and first["package"] == str(appended / "imtypeset")
    for step in ("reset", "disabled"):
        after = report[step]
        assert after["module"] is True and after["same"] is True, after["pairing"]["reason"]
        assert after["pairing"] == {**first, "named_by": "remembered"}
        assert after["environment"] == [], "the variables were put back into the process"
        assert after["trouble"] == ""


def test_the_remembered_pair_is_handed_to_an_import_that_has_to_happen_again(
    tmp_path: Path,
) -> None:
    """
    Where the package is no longer in `sys.modules`, the import is a real one
    and the package reads the variable: it is given the remembered library
    for the length of the import and no longer. `forget_pair()` is how a host
    takes the memory back; the next `module()` after a `reset()` then asks
    the environment alone, as it did before there was a memory.
    """
    env, library, _ = _named(tmp_path)
    code = _REMOVED + (
        "del sys.modules['imtypeset']\n"
        "typesetter.reset()\n"
        "report['again'] = state()\n"
        "typesetter.forget_pair()\n"
        "report['kept'] = state()\n"
        "typesetter.reset()\n"
        "report['forgotten'] = state()\n"
        "print(json.dumps(report))\n"
    )
    report = _child(code, env)
    again = report["again"]
    assert again["module"] is True and again["same"] is False
    assert again["with"] == str(library), "the import did not meet the remembered library"
    assert again["pairing"]["named_by"] == "remembered" and again["environment"] == []
    # Forgetting changes nothing that is loaded: only what the next attempt is given.
    assert report["kept"]["module"] is True
    assert report["kept"]["pairing"] == again["pairing"]
    forgotten = report["forgotten"]
    assert forgotten["module"] is False
    assert forgotten["pairing"]["reason"] == typesetter.ABSENT_REASON
    assert forgotten["pairing"]["kind"] == typesetter.Kind.NOT_INSTALLED.value
    # As `route` does, it goes on describing the package that is in the process.
    assert forgotten["pairing"]["route"] == typesetter.ROUTE_ENVIRONMENT
    assert forgotten["pairing"]["named_by"] == "remembered"


def test_an_environment_that_names_another_library_wins_over_the_remembered_pair(
    tmp_path: Path,
) -> None:
    """
    Decided: where `IMTYPESET_LIBRARY` is set, it is what is asked, and the
    memory is not consulted. What it cannot do is replace a library that is
    already in the process: Python unloads neither, so the package that was
    imported answers again, `pairing()["library"]` is still its library, and
    `trouble()` says that the one named was not loaded. With the package out
    of `sys.modules` the import is a real one and meets the new value; that
    pair is then the one remembered.
    """
    env, library, _ = _named(tmp_path)
    other = tmp_path / "other" / "libimtypeset_bundle.so"
    code = _REMOVED + (
        f"os.environ['IMTYPESET_LIBRARY'] = {str(other)!r}\n"
        "typesetter.reset()\n"
        "report['held'] = state()\n"
        "del sys.modules['imtypeset']\n"
        "typesetter.reset()\n"
        "report['imported'] = state()\n"
        "del os.environ['IMTYPESET_LIBRARY']\n"
        "typesetter.reset()\n"
        "report['afterwards'] = state()\n"
        "print(json.dumps(report))\n"
    )
    report = _child(code, env)
    held = report["held"]
    assert held["module"] is True and held["same"] is True
    assert held["pairing"]["named_by"] == "environment"
    assert held["pairing"]["library"] == str(library), "a process holds one library"
    assert str(other) in held["trouble"] and str(library) in held["trouble"]
    imported = report["imported"]
    assert imported["with"] == str(other) and imported["pairing"]["library"] == str(other)
    assert imported["pairing"]["named_by"] == "environment"
    afterwards = report["afterwards"]
    assert afterwards["pairing"]["library"] == str(other)
    assert afterwards["pairing"]["named_by"] == "remembered"


def test_a_verdict_with_no_arguments_asks_about_the_remembered_pair(tmp_path: Path) -> None:
    """
    `verdict()` is what a NEW process would say, and a new process started
    after the variables were removed would find nothing. So with no library
    given and none in the environment, the child is handed the remembered
    pair explicitly. A library given, an empty string included, is asked as
    given; and a library the environment names is the environment's, as it
    was.
    """
    env, library, appended = _named(tmp_path)
    other = tmp_path / "other" / "libimtypeset_bundle.so"
    code = _REMOVED + (
        "report['remembered'] = typesetter.verdict(timeout=120)\n"
        "report['none'] = typesetter.verdict('', timeout=120)\n"
        f"os.environ['IMTYPESET_LIBRARY'] = {str(other)!r}\n"
        f"os.environ['IMTYPESET_PYTHON'] = {str(appended)!r}\n"
        "report['environment'] = typesetter.verdict(timeout=120)\n"
        "del os.environ['IMTYPESET_LIBRARY'], os.environ['IMTYPESET_PYTHON']\n"
        "typesetter.forget_pair()\n"
        "report['forgotten'] = typesetter.verdict(timeout=120)\n"
        "report['state'] = state()\n"
        "print(json.dumps(report))\n"
    )
    report = _child(code, env)
    remembered = report["remembered"]
    assert remembered["kind"] == typesetter.Kind.READY.value, remembered["reason"]
    assert remembered["library"] == str(library)
    assert remembered["package"] == str(appended / "imtypeset")
    assert remembered["named_by"] == "environment", "the child was given it as variables"
    assert report["none"]["kind"] == typesetter.Kind.NOT_INSTALLED.value
    assert report["environment"]["library"] == str(other)
    assert report["forgotten"]["kind"] == typesetter.Kind.NOT_INSTALLED.value
    assert report["state"]["environment"] == [], "a verdict changed this process's environment"


def test_forget_pair_is_refused_nothing_and_a_pair_is_not_remembered_from_a_refusal(
    tmp_path: Path,
) -> None:
    """
    Only a load that was accepted is remembered: a refused import leaves no
    pair to come back to, and `forget_pair()` with nothing remembered is
    nothing.
    """
    source = _REFUSES.format(kind="damaged", sentence=_SENTENCE, detail=_DETAIL)
    package = tmp_path / "appended"
    _a_package(package, source)
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(tmp_path / "a-library")
    env[typesetter.PACKAGE_VARIABLE] = str(package)
    code = (
        "import json, os\n"
        "from imscribe import typesetter\n"
        "typesetter.forget_pair()\n"
        "report = {'first': typesetter.pairing(), 'pair': typesetter._pair}\n"
        "for name in ('IMTYPESET_LIBRARY', 'IMTYPESET_PYTHON'):\n"
        "    del os.environ[name]\n"
        "typesetter.reset()\n"
        "report['after'] = typesetter.pairing()\n"
        "print(json.dumps(report))\n"
    )
    report = _child(code, env)
    assert report["first"]["kind"] == typesetter.Kind.REFUSED.value and report["pair"] is None
    assert report["first"]["named_by"] is None
    assert report["after"]["kind"] == typesetter.Kind.NOT_INSTALLED.value
    assert report["after"]["reason"] == typesetter.ABSENT_REASON


# ---------------------------------------------------------------------------
# In this process: what is remembered
# ---------------------------------------------------------------------------


def test_the_distribution_is_looked_for_once_and_the_variable_still_works_later(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    A view asks `module()` every frame. With nothing installed that must not
    be a walk over `sys.path` every frame; and a variable set later in the
    same process must still be seen, as before.
    """
    asked: list[str] = []

    def distribution(name: str) -> Any:
        asked.append(name)
        raise metadata.PackageNotFoundError(name)

    for name in (*_VARIABLES, typesetter.DISABLE_VARIABLE):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(metadata, "distribution", distribution)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "imtypeset" not in p])
    monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
    typesetter._forget()
    try:
        for _ in range(3):
            assert typesetter.module() is None
            assert typesetter.reason() == typesetter.ABSENT_REASON
        assert typesetter.pairing()["route"] == typesetter.ROUTE_NONE
        assert asked == ["imtypeset"]
        monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "absent.so"))
        assert typesetter.module() is None
        assert typesetter.reason() != typesetter.ABSENT_REASON
        assert "the installed" not in typesetter.reason()
        assert asked == ["imtypeset"]
        # `_forget` is back to the state at import: it looks again.
        typesetter._forget()
        monkeypatch.delenv(typesetter.LIBRARY_VARIABLE)
        assert typesetter.module() is None
        assert asked == ["imtypeset", "imtypeset"]
    finally:
        typesetter._forget()
    assert typesetter.reason() == typesetter.ABSENT_REASON


# ---------------------------------------------------------------------------
# With the library: the pinned pair, as the environment gives it and as a
# distribution would
# ---------------------------------------------------------------------------

_REAL = """
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter
report = {"pairing": typesetter.pairing(), "module": typesetter.module() is not None}
context = imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures
imgui.get_io().set_ini_filename(None)
report["fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
report["after"] = typesetter.pairing()
typesetter.unload()
imgui.destroy_context(context)
print(json.dumps(report))
"""

# A package that carries a library: it names the one in its own directory to
# the real package's loader for the length of the import, and is the real
# package from then on (`__path__` is the real package's directory, so its
# submodules are the real ones). `{real}` is that directory.
_WRAPPED = """
import os as _os
_here = _os.path.dirname(_os.path.abspath(__file__))
_real = {real!r}
__path__ = [_real]
_os.environ["IMTYPESET_LIBRARY"] = _os.path.join(_here, "libimtypeset_bundle.so")
try:
    with open(_os.path.join(_real, "__init__.py"), encoding="utf-8") as _handle:
        exec(compile(_handle.read(), _os.path.join(_real, "__init__.py"), "exec"))
finally:
    del _os.environ["IMTYPESET_LIBRARY"]
"""


def _installed() -> Path | None:
    """The installed distribution's library when THAT is the session's imtypeset, else `None`."""
    from conftest import installed_typeset_library

    return installed_typeset_library()


def _the_pair() -> tuple[Path, Path]:
    """
    The library and the package directory this run loads; skips when there is none.

    Two shapes since 2026-10-13. **An installed distribution**
    (`tests/conftest.py` names its library in `IMTYPESET_LIBRARY` for the
    session): the library is inside the package directory, and it is what
    loads whatever the variables say. **A sidecar** (`make test TYPESET=1`
    in a virtualenv with no imtypeset installed): the library the variable
    names, and the package directory `IMTYPESET_PYTHON` names, which holds no
    library. `_the_sidecar` is for a test that is about the second alone.
    """
    library = os.environ.get(typesetter.LIBRARY_VARIABLE)
    if not library:
        pytest.skip(
            "no imtypeset in this run: install the wheel, or `make test TYPESET=1` (after "
            "`make typeset-lib`), to load the pinned pair"
        )
    installed = _installed()
    if installed is not None:
        return installed, installed.parent
    package = os.environ.get(typesetter.PACKAGE_VARIABLE)
    assert package, "IMTYPESET_LIBRARY is set and IMTYPESET_PYTHON is not"
    assert (Path(package) / "imtypeset" / "__init__.py").is_file(), package
    return Path(library), Path(package) / "imtypeset"


def _the_sidecar() -> tuple[Path, Path]:
    """
    `_the_pair`, for a test of the ENVIRONMENT route against the real library; skips otherwise.

    An installed imtypeset reads neither variable and is found before any
    directory `IMTYPESET_PYTHON` names, so where one is installed there is no
    environment route to the real library to test.
    """
    pair = _the_pair()
    if _installed() is not None:
        pytest.skip(
            "this run's imtypeset is an installed distribution, which reads no variable: the "
            "environment route against the real library runs with `make test TYPESET=1` in a "
            "virtualenv that has no imtypeset installed"
        )
    return pair


def _held(pairing: dict[str, Any], library: Path) -> None:
    assert set(pairing) == _KEYS
    assert pairing["reason"] == "" and pairing["kind"] == typesetter.Kind.READY.value
    assert pairing["library"] == str(library)
    assert pairing["wheel_version"] == metadata.version("imgui-bundle")
    assert pairing["headers"].startswith(("fork:", "stand-in:")), pairing["headers"]
    assert pairing["accepted_by"] in ("imgui-check+probe", "probe")
    assert pairing["imtypeset_version"] and pairing["imgui_version"]


def test_the_pinned_pair_by_the_environment_reports_itself() -> None:
    library, package = _the_sidecar()
    report = _child(_REAL, dict(os.environ))
    assert report["module"] is True, report["pairing"]["reason"]
    _held(report["pairing"], library)
    assert report["pairing"]["route"] == typesetter.ROUTE_ENVIRONMENT
    assert report["pairing"]["package"] == str(package)
    assert report["pairing"]["distribution"] is None and report["pairing"]["built_for"] is None
    assert report["fonts"] is True and report["ready"] is True, report["reason"]
    assert report["after"] == report["pairing"]


def test_the_pinned_pair_as_a_distribution_loads_and_draws_with_no_variable_set(
    tmp_path: Path,
) -> None:
    """
    The whole of route 2 against the real library: neither variable in the
    environment, the import gate run against the installed wheel, a context,
    and every face added.
    """
    library, real = _the_sidecar()
    wheel = metadata.version("imgui-bundle")
    site = tmp_path / "site"
    (site / "imtypeset").mkdir(parents=True)
    (site / "imtypeset" / "__init__.py").write_text(_WRAPPED.format(real=str(real)), "utf-8")
    carried = site / "imtypeset" / "libimtypeset_bundle.so"
    carried.symlink_to(library)
    _metadata(site, version="0.0.0+standin", requires=f"imgui-bundle=={wheel}")

    report = _child(_REAL, _without(), site)
    assert report["module"] is True, report["pairing"]["reason"]
    _held(report["pairing"], carried)
    assert report["pairing"]["route"] == typesetter.ROUTE_DISTRIBUTION
    assert report["pairing"]["package"] == str(site / "imtypeset")
    assert report["pairing"]["distribution"] == "imtypeset 0.0.0+standin"
    assert report["pairing"]["built_for"] == f"imgui-bundle=={wheel}"
    assert report["fonts"] is True and report["ready"] is True, report["reason"]
    assert report["after"] == report["pairing"]


# ---------------------------------------------------------------------------
# The pair this run was given, in whichever of the two shapes it has: built
# from imtypeset before 03b5cd4 (`<library>.gate`, refusals without a kind,
# no `route`) or from it on (`<library>.attestation.json`, kinds, a route)
# ---------------------------------------------------------------------------

_GATED = """
import json
from imscribe import typesetter
answer = {"pairing": typesetter.pairing()}
package = typesetter.module()
if package is not None:
    answer["checked_in"] = (package.host_info().get("bundle") or {}).get("checked_in")
print(json.dumps(answer))
"""


def _says_kinds(package: Path) -> bool:
    """Whether the package given is one whose refusals carry a kind (03b5cd4 on)."""
    return "def refusal(" in (package / "_bundle.py").read_text(encoding="utf-8")


def test_a_pair_that_carries_an_attestation_is_accepted_by_it_and_not_by_a_child() -> None:
    """
    imtypeset's T3: `make typeset-lib` leaves `<library>.attestation.json`
    beside the library it installs, and the import then checks content
    against it in this process. Without the file every import of the pair
    starts a child interpreter, which works and is never noticed. A pair from
    before 03b5cd4 has no such file and says nothing of a route; then this
    holds only that.
    """
    library, package = _the_sidecar()
    report = _child(_GATED, dict(os.environ))
    assert report["pairing"]["kind"] == typesetter.Kind.READY.value, report["pairing"]["reason"]
    if _says_kinds(package):
        attestation = Path(f"{library}.attestation.json")
        assert attestation.is_file(), f"the pair was installed without {attestation.name}"
        assert report["checked_in"] == "attestation"
        assert report["pairing"]["imtypeset_route"] == "IMTYPESET_LIBRARY"
    else:
        assert not Path(f"{library}.attestation.json").exists()
        assert report["pairing"]["imtypeset_route"] is None
    assert report["pairing"]["imtypeset_kind"] is None


def test_a_real_refusal_carries_the_packages_own_word_when_it_has_one(tmp_path: Path) -> None:
    """
    The package this run was given, handed a file that is no library. From
    03b5cd4 on its refusal is `not-a-library` and its first line a sentence;
    before, there is no word and the reason is the whole message. Either way
    imscribe's kind is `refused`.
    """
    _, package = _the_sidecar()
    impostor = tmp_path / "not-a-library.so"
    impostor.write_bytes(b"\x7fELF and then nothing a loader would take")
    env = dict(os.environ)
    env[typesetter.LIBRARY_VARIABLE] = str(impostor)
    report = _child(_GATED, env)
    assert report["pairing"]["kind"] == typesetter.Kind.REFUSED.value
    assert report["pairing"]["route"] == typesetter.ROUTE_NONE
    if _says_kinds(package):
        assert report["pairing"]["imtypeset_kind"] == "not-a-library"
        assert "\n" not in report["pairing"]["reason"]
        assert str(impostor) not in report["pairing"]["reason"], "the sentence names no path"
    else:
        assert report["pairing"]["imtypeset_kind"] is None


def _as_a_wheel(tmp_path: Path, library: Path, real: Path) -> tuple[Path, Path]:
    """
    The pair given, laid out as imtypeset's wheel lays it out: (the site directory, the library).

    The package's modules, the library and the attestation in ONE directory,
    and no `dist-info`. Skips with a pair from before 03b5cd4, whose package
    looks for a library nowhere but in the variable.
    """
    attestation = Path(f"{library}.attestation.json")
    if not _says_kinds(real) or not attestation.is_file():
        pytest.skip(
            "the pair given is from before imtypeset 03b5cd4: its package carries no library "
            "and finds none without IMTYPESET_LIBRARY"
        )
    site = tmp_path / "site"
    (site / "imtypeset").mkdir(parents=True)
    for module in real.glob("*.py"):
        (site / "imtypeset" / module.name).write_bytes(module.read_bytes())
    carried = site / "imtypeset" / library.name
    carried.symlink_to(library)
    (site / "imtypeset" / "_attestation.json").write_bytes(attestation.read_bytes())
    return site, carried


def _ignores_the_environment(package: Path) -> bool:
    """Whether the package given is one that reads no variable once installed (v0.3.0 on)."""
    return "def ignored_environment(" in (package / "_bundle.py").read_text(encoding="utf-8")


def test_the_staged_package_is_a_directory_with_no_library_in_it() -> None:
    """
    imtypeset's T8: from its v0.3.0 on the environment route works only with
    a package directory that holds neither a library nor `_attestation.json`
    (a checkout's `python/`); one that holds either is an installed
    distribution and reads no variable. `make typeset-lib` puts the library
    BESIDE `pysnap`, not in the package, and this holds it to that.
    """
    library, package = _the_sidecar()
    if package.parent.name != "pysnap":
        pytest.skip(f"the package given is not one `make typeset-lib` staged: {package}")
    assert library.parent == package.parent.parent, "the library is not beside pysnap"
    held = sorted(entry.name for entry in package.iterdir() if entry.suffix != ".py")
    assert [name for name in held if name != "__pycache__"] == [], held
    assert not (package / "_attestation.json").exists()


def test_an_installed_imtypeset_with_the_variables_set_says_which_of_the_two_it_loaded(
    tmp_path: Path,
) -> None:
    """
    imtypeset's T8 against the real package: the pair laid out as a wheel and
    importable, AND both variables naming the staged pair. From v0.3.0 the
    installed package reads neither: the route is the distribution's, the
    library is the one it carries, and `ignored_environment` names both
    variables. At 03b5cd4 the variable still won inside an installed
    package: the route is the environment's and the library the one named.
    """
    library, real = _the_sidecar()
    site, carried = _as_a_wheel(tmp_path, library, real)
    report = _child(_REAL, dict(os.environ), site)
    found = report["pairing"]
    assert found["kind"] == typesetter.Kind.READY.value, found["reason"]
    assert found["package"] == str(site / "imtypeset"), "the installed package comes first"
    assert report["fonts"] is True and report["ready"] is True, report["reason"]
    if _ignores_the_environment(real):
        assert found["route"] == typesetter.ROUTE_DISTRIBUTION
        assert found["imtypeset_route"] == "installed"
        assert found["library"] == str(carried)
        assert found["ignored_environment"] == "IMTYPESET_LIBRARY, IMTYPESET_PYTHON"
        assert found["named_by"] is None
        assert found["built_for"] == f"imgui-bundle=={metadata.version('imgui-bundle')}"
    else:
        assert found["route"] == typesetter.ROUTE_ENVIRONMENT
        assert found["imtypeset_route"] == "IMTYPESET_LIBRARY"
        assert found["library"] == str(library)
        assert found["ignored_environment"] is None
        assert found["named_by"] == "environment"


def test_a_library_without_its_attestation_is_probed_in_a_child_and_accepted(
    tmp_path: Path,
) -> None:
    """
    imtypeset's T9 (and T3): a library the variable names that has no
    `<library>.attestation.json` beside it is probed in a child interpreter
    (from v0.3.0, before the importing process loads it) and accepted;
    `route` is still `IMTYPESET_LIBRARY` for a sidecar. What `make
    typeset-lib` installs carries the attestation so that this is not paid
    at every import; this is the pair without it.
    """
    library, real = _the_sidecar()
    if not _says_kinds(real):
        pytest.skip("the pair given is from before imtypeset 03b5cd4: it has no attestation")
    bare = tmp_path / "bare" / library.name
    bare.parent.mkdir()
    bare.symlink_to(library)
    env = dict(os.environ)
    env[typesetter.LIBRARY_VARIABLE] = str(bare)
    report = _child(_GATED, env)
    assert report["pairing"]["kind"] == typesetter.Kind.READY.value, report["pairing"]["reason"]
    assert report["checked_in"] == "child"
    assert report["pairing"]["library"] == str(bare)
    assert report["pairing"]["imtypeset_route"] == "IMTYPESET_LIBRARY"
    assert report["pairing"]["named_by"] == "environment"


_REAL_REMOVED = """
import json, os, subprocess, sys
from imgui_bundle import imgui
from imscribe import typesetter
report = {"first": typesetter.pairing()}
for name in ("IMTYPESET_LIBRARY", "IMTYPESET_PYTHON"):
    del os.environ[name]
typesetter.reset()
report["again"] = typesetter.pairing()
context = imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures
imgui.get_io().set_ini_filename(None)
report["fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["verdict"] = typesetter.verdict(timeout=120)
report["inherited"] = subprocess.run(
    [sys.executable, "-c", "import os; print(sorted(n for n in os.environ if 'IMTYPESET' in n))"],
    capture_output=True, text=True, check=True,
).stdout.strip()
typesetter.forget_pair()
report["forgotten"] = typesetter.verdict(timeout=120)
typesetter.unload()
imgui.destroy_context(context)
print(json.dumps(report))
"""


def test_the_real_pair_is_come_back_to_after_the_variables_were_removed() -> None:
    """
    P33 against the library: pptmstr's sequence, then fonts, then a verdict
    with no arguments. The second attempt is the package that is already in
    the process; the child of `verdict()` is a new process, is handed the
    remembered pair, and says of it what this process said the first time.
    What this process launches inherits neither variable.
    """
    library, package = _the_sidecar()
    report = _child(_REAL_REMOVED, dict(os.environ))
    first = report["first"]
    _held(first, library)
    assert first["route"] == typesetter.ROUTE_ENVIRONMENT and first["named_by"] == "environment"
    assert report["again"] == {**first, "named_by": "remembered"}
    assert report["fonts"] is True and report["ready"] is True
    assert report["verdict"] == first
    assert report["inherited"] == "[]"
    assert report["forgotten"]["kind"] == typesetter.Kind.NOT_INSTALLED.value
    assert report["again"]["package"] == str(package)


def test_the_pair_laid_out_as_a_wheel_lays_it_out_is_found_by_its_attestation_alone(
    tmp_path: Path,
) -> None:
    """
    Route 2 with nothing standing in for the package: its modules, the library
    and the attestation in ONE directory, as imtypeset's wheel has them, no
    `dist-info`, and neither variable set. The package finds the library
    beside itself (`route: installed`), holds it to the attestation without
    starting a child, and the fonts load.

    Only with a pair from imtypeset 03b5cd4 on: before it the package looks
    for a library nowhere but in the variable, and
    `test_the_pinned_pair_as_a_distribution_loads_and_draws_with_no_variable_set`
    is the test of this route.
    """
    library, real = _the_sidecar()
    site, carried = _as_a_wheel(tmp_path, library, real)
    asked = _REAL.replace(
        "print(json.dumps(report))",
        'report["checked_in"] = typesetter.module().host_info()["bundle"]["checked_in"]\n'
        "print(json.dumps(report))",
    )
    report = _child(asked, _without(), site)
    assert report["module"] is True, report["pairing"]["reason"]
    assert report["checked_in"] == "attestation"
    assert report["fonts"] is True and report["ready"] is True, report["reason"]
    found = report["pairing"]
    assert found["kind"] == typesetter.Kind.READY.value, found["reason"]
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["imtypeset_route"] == "installed"
    assert found["library"] == str(carried) and found["package"] == str(site / "imtypeset")
    assert found["distribution"] == "imtypeset", "a development build's attestation has no version"
    assert found["built_for"] == f"imgui-bundle=={metadata.version('imgui-bundle')}"


# ---------------------------------------------------------------------------
# The installed wheel: route 2 as a user's process takes it (2026-10-13)
# ---------------------------------------------------------------------------


def _the_installed() -> Path:
    library = _installed()
    if library is None:
        pytest.skip("no imtypeset distribution is installed in this interpreter")
    return library


def test_the_installed_wheel_loads_and_draws_with_nothing_set() -> None:
    """
    What `pip install imscribe` gives where imtypeset has a wheel: no
    variable of either project in the environment, nothing hidden, and
    `module()` finds the distribution by its metadata, imports it, and its
    own gate accepts the library it carries against the imgui-bundle that is
    running. Then a context and every face.
    """
    library = _the_installed()
    report = _child(_REAL, _as_a_user())
    assert report["module"] is True, report["pairing"]["reason"]
    found = report["pairing"]
    _held(found, library)
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["imtypeset_route"] == "installed"
    assert found["package"] == str(library.parent)
    assert found["distribution"] == f"imtypeset {metadata.version('imtypeset')}"
    assert found["built_for"] == f"imgui-bundle=={metadata.version('imgui-bundle')}"
    assert found["ignored_environment"] is None and found["named_by"] is None
    if "standin" not in metadata.version("imtypeset"):
        assert found["headers"].startswith("fork:"), "a release wheel is built on the real headers"
    major, minor = (int(part) for part in found["imtypeset_version"].split(".")[:2])
    assert (major, minor) >= typesetter.MINIMUM
    assert report["fonts"] is True and report["ready"] is True, report["reason"]
    assert report["after"] == found


def test_the_installed_wheel_is_what_loads_when_the_variables_name_something_else(
    tmp_path: Path,
) -> None:
    """
    Measured 2026-10-13, and why `make test TYPESET=1` is the developer's
    route only in a virtualenv with no imtypeset installed: with the wheel
    installed and both variables naming another pair, the installed package
    is the one imported, it reads neither variable, and `pairing()` says so.
    """
    library = _the_installed()
    env = _as_a_user()
    env[typesetter.LIBRARY_VARIABLE] = str(tmp_path / "dev" / "libimtypeset_bundle.so")
    env[typesetter.PACKAGE_VARIABLE] = str(tmp_path / "dev" / "python")
    found = _child(_GATED, env)["pairing"]
    assert found["kind"] == typesetter.Kind.READY.value, found["reason"]
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["library"] == str(library)
    assert found["ignored_environment"] == "IMTYPESET_LIBRARY, IMTYPESET_PYTHON"
    assert found["named_by"] is None


# ---------------------------------------------------------------------------
# IMSCRIBE_NO_TYPESET, and the floor on the library's version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "looked"),
    [
        ("1", False),
        ("yes", False),
        (" 1 ", False),
        ("0", True),
        ("", True),
        (" 0 ", True),
        ("   ", True),
        ("\t", True),
    ],
)
def test_the_switch_stops_the_looking_and_nothing_else(
    tmp_path: Path, value: str, looked: bool
) -> None:
    """
    With `IMSCRIBE_NO_TYPESET` set to anything but nothing or 0, an installed
    distribution is not looked for: nothing is imported, the sentence names
    the switch (`SWITCHED_OFF_REASON`; until 2026-10-14 it was the one for
    nothing found), and `distribution` is not said.

    Blanks around the value are not part of it, so a value of blanks alone is
    nothing (2026-10-13: it counted as set until then, while a blank-padded 0
    did not; the two rows of blanks were red).
    """
    site = _a_distribution(tmp_path)
    env = _without()
    env[typesetter.DISABLE_VARIABLE] = value
    report = _child(_REPORT, env, site)
    assert report["module"] is looked
    found = report["pairing"]
    if looked:
        assert found["route"] == typesetter.ROUTE_DISTRIBUTION
        assert found["distribution"] == "imtypeset 0.9.0"
    else:
        assert report["imtypeset"] == [], "it was imported although it was not to be looked for"
        assert found["kind"] == typesetter.Kind.NOT_INSTALLED.value
        assert found["reason"] == typesetter.SWITCHED_OFF_REASON
        assert found["route"] == typesetter.ROUTE_NONE and found["distribution"] is None


def test_a_library_that_is_named_is_loaded_under_the_switch(tmp_path: Path) -> None:
    """
    The switch is about what imscribe looks for by itself. A library the
    environment names is an explicit request and is honoured: this is the
    state every with-library test of this suite runs in (`tests/conftest.py`).
    """
    env, library, appended = _named(tmp_path)
    env[typesetter.DISABLE_VARIABLE] = "1"
    found = _child(_REPORT, env)["pairing"]
    assert found["kind"] == typesetter.Kind.READY.value, found["reason"]
    assert found["route"] == typesetter.ROUTE_ENVIRONMENT
    assert found["library"] == str(library)


def _versioned(version: str) -> str:
    return _TWO_FUNCTIONS.replace('"0.9.0"', repr(version))


@pytest.mark.parametrize("version", ["0.3.0", "0.3.9", "0.0.1"])
def test_a_library_older_than_the_floor_is_refused_before_anything_is_drawn(
    tmp_path: Path, version: str
) -> None:
    """
    imtypeset 0.4 sets code on the device's grid by default and 0.3 did not
    (its changelog); this imscribe's views are written to 0.4. A 0.3 library
    that happened to have every name would draw text in other places, so it
    is refused at the gate, in the sentence form of a package that lacks
    names.
    """
    site = _a_distribution(tmp_path, _versioned(version))
    report = _child(_REPORT, _without(), site)
    assert report["module"] is False
    found = report["pairing"]
    assert found["kind"] == typesetter.Kind.REFUSED.value
    assert found["reason"] == (
        f"the imtypeset at {site / 'imtypeset'} is {version} and this imscribe needs 0.4 or "
        "later; the two were not installed together"
    )
    # Which imtypeset was refused is still said.
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["imtypeset_version"] == version


@pytest.mark.parametrize("version", ["0.4.0", "0.4.1", "0.5.0", "1.0.0", "0.10.0"])
def test_a_library_at_or_above_the_floor_is_not_refused_for_its_version(
    tmp_path: Path, version: str
) -> None:
    site = _a_distribution(tmp_path, _versioned(version))
    report = _child(_REPORT, _without(), site)
    assert report["module"] is True, report["reason"]


def test_a_package_that_cannot_say_its_version_is_held_to_its_names_alone(tmp_path: Path) -> None:
    silent = _TWO_FUNCTIONS.replace('"imtypeset_version": "0.9.0",', "")
    assert silent != _TWO_FUNCTIONS
    site = _a_distribution(tmp_path, silent)
    report = _child(_REPORT, _without(), site)
    assert report["module"] is True, report["reason"]
    assert typesetter.MINIMUM == (0, 4)

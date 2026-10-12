"""
`advtext.typesetter`: which imtypeset is found, by which route, and what `pairing()` says.

The order under test (`advtext/typesetter.py`, "Loading, gated"):

1.  `IMTYPESET_LIBRARY` set: the environment route, as it always was.
2.  otherwise an installed `imtypeset` DISTRIBUTION -- one `importlib.metadata`
    finds -- imported with no variable set.
3.  otherwise nothing, and `reason()` is the sentence it always was.

**No such distribution exists** (2026-10-11; HANDOFF-imtypeset.md, request
H3). So route 2 is tested with stand-ins the tests build in a temporary
directory, and what they stand in for is this contract, which is the whole of
what advtext assumes:

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
- **the pinned pair, wrapped** (with the library only; skipped, with the
  reason, without it): a package named `imtypeset` that carries a library
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

from advtext import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_KEYS = {
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
}

_REPORT = """
import json, sys
from advtext import typesetter
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
        env={**env, "PYTHONPATH": os.pathsep.join([str(_ROOT), *map(str, path)])},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return report


def _without() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name not in _VARIABLES}


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
    an owner, a tuple type in advtext's field order where the library reads
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
    assert report["reason"] == "IMTYPESET_LIBRARY is not set"
    assert set(report["pairing"]) == _KEYS
    assert report["pairing"].pop("route") == typesetter.ROUTE_NONE
    assert report["pairing"].pop("reason") == "IMTYPESET_LIBRARY is not set"
    assert report["pairing"].pop("kind") == typesetter.Kind.NOT_INSTALLED.value
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
    assert report["reason"] == "IMTYPESET_LIBRARY is not set"
    assert report["imtypeset"] == [], "a package that is not a distribution was imported"
    assert report["pairing"]["route"] == typesetter.ROUTE_NONE
    assert report["pairing"]["distribution"] is None


# ---------------------------------------------------------------------------
# Route 2: an installed distribution
# ---------------------------------------------------------------------------


def test_an_installed_distribution_is_loaded_with_no_variable_set(tmp_path: Path) -> None:
    site = _a_distribution(tmp_path)
    report = _child(_REPORT, _without(), site)
    assert report["before"] == [], "importing advtext.typesetter imported imtypeset"
    assert report["module"] is True and report["reason"] == ""
    assert report["imtypeset"] == ["imtypeset"]
    assert report["path"] == [], "sys.path was touched on the distribution route"
    assert report["pairing"] == {
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
def test_a_refusal_that_carries_a_kind_is_carried_and_decides_advtexts_kind(
    theirs: str, ours: typesetter.Kind, tmp_path: Path
) -> None:
    """
    imtypeset's T4 and its answer to H26. The word is `pairing()["imtypeset_kind"]`
    as it was given; advtext's own kind is `unsupported` for a package built
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
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reason"] == f"ImportError: imtypeset: {_SENTENCE}"
    assert report["pairing"]["kind"] == typesetter.Kind.REFUSED.value
    assert report["pairing"]["imtypeset_kind"] == "damaged"
    assert result.stderr.count(f"imtypeset says of that refusal (damaged): {_DETAIL}") == 1


# -- known by its attestation, with no metadata (imtypeset's T5: a frozen application) --

_INSTALLED = """
import os
def host_info():
    return {
        "library": os.path.join(os.path.dirname(__file__), "the-library"),
        "route": "installed",
        "imgui_version": "1.92.9",
        "imtypeset_version": "0.3.0",
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
    and from the library's own record. A file advtext cannot read still marks
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
        "route": typesetter.ROUTE_DISTRIBUTION,
        "reason": "",
        "kind": typesetter.Kind.READY.value,
        "library": str(site / "imtypeset" / "the-library"),
        "package": str(site / "imtypeset"),
        "distribution": distribution,
        "imtypeset_version": "0.3.0",
        "imgui_version": "1.92.9",
        "wheel_version": "1.92.900",
        "built_for": "imgui-bundle==1.92.900",
        "headers": "fork:0123abc",
        "accepted_by": "imgui-check+probe",
        "imtypeset_kind": None,
        "imtypeset_route": "installed",
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

    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(metadata, "distribution", distribution)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "imtypeset" not in p])
    monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
    typesetter._forget()
    try:
        for _ in range(3):
            assert typesetter.module() is None
            assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"
        assert typesetter.pairing()["route"] == typesetter.ROUTE_NONE
        assert asked == ["imtypeset"]
        monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "absent.so"))
        assert typesetter.module() is None
        assert typesetter.reason() != "IMTYPESET_LIBRARY is not set"
        assert "the installed" not in typesetter.reason()
        assert asked == ["imtypeset"]
        # `_forget` is back to the state at import: it looks again.
        typesetter._forget()
        monkeypatch.delenv(typesetter.LIBRARY_VARIABLE)
        assert typesetter.module() is None
        assert asked == ["imtypeset", "imtypeset"]
    finally:
        typesetter._forget()
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"


# ---------------------------------------------------------------------------
# With the library: the pinned pair, as the environment gives it and as a
# distribution would
# ---------------------------------------------------------------------------

_REAL = """
import json, sys
from imgui_bundle import imgui
from advtext import typesetter
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


def _the_pair() -> tuple[Path, Path]:
    """
    The library and the package directory this run was given; skips without them.
    """
    library = os.environ.get(typesetter.LIBRARY_VARIABLE)
    if not library:
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "to load the pinned pair by both routes"
        )
    package = os.environ.get(typesetter.PACKAGE_VARIABLE)
    assert package, "IMTYPESET_LIBRARY is set and IMTYPESET_PYTHON is not"
    assert (Path(package) / "imtypeset" / "__init__.py").is_file(), package
    return Path(library), Path(package) / "imtypeset"


def _held(pairing: dict[str, Any], library: Path) -> None:
    assert set(pairing) == _KEYS
    assert pairing["reason"] == "" and pairing["kind"] == typesetter.Kind.READY.value
    assert pairing["library"] == str(library)
    assert pairing["wheel_version"] == metadata.version("imgui-bundle")
    assert pairing["headers"].startswith(("fork:", "stand-in:")), pairing["headers"]
    assert pairing["accepted_by"] in ("imgui-check+probe", "probe")
    assert pairing["imtypeset_version"] and pairing["imgui_version"]


def test_the_pinned_pair_by_the_environment_reports_itself() -> None:
    library, package = _the_pair()
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
    library, real = _the_pair()
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
from advtext import typesetter
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
    library, package = _the_pair()
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
    advtext's kind is `refused`.
    """
    _, package = _the_pair()
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
    library, real = _the_pair()
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

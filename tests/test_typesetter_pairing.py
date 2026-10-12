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

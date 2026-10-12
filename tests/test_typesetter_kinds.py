"""
`advtext.typesetter`: the kind beside the sentence, the way back, the names check, a verdict
from a child, the `ImFont` of a face, and `load_fonts()` after start-up.

What pptmstr, the first host, asked for as P1, P18, P3, P2, P14 and P17
(`HANDOFF-pptmstr.md`, "Answers to pptmstr"). Four layers, cheapest first:

1.  **This process, a stand-in package** (`gate`): the kinds, `reset`,
    `unsupported`, and what `missing` says of a package that lacks a name.
    The stand-in is `test_typesetter_pairing.standin`, written from
    `typesetter.REQUIRED`, so it has exactly the names the gate asks for.
2.  **advtext's own sources, read**: every name of imtypeset that a module of
    advtext uses is on `typesetter.REQUIRED`. This is the test that fails
    when advtext starts calling something the gate does not ask for.
3.  **A fresh interpreter**: `verdict()` and `python -m advtext.typesetter`,
    with a stand-in distribution in both gates and the pinned pair with the
    library.
4.  **The pinned pair** (skipped, with the reason, without it): `font`, the
    way back with real fonts, and -- in a real window -- `load_fonts()` called
    again long after start-up with a view open, which is what the promise in
    its docstring is a record of.

The state of `advtext.typesetter` is the process's. Everything here that
touches it puts back exactly what it found (`gate`), because other files'
tests in the same pytest process may have the real library loaded.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import signal
import subprocess
import sys
import types
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
import test_typesetter_pairing as pairing
from conftest import Window

from advtext import typesetter
from advtext.primitives import Face
from advtext.typesetter import Kind

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_STATE = (
    "_ts",
    "_package",
    "_tried",
    "_route",
    "_installed",
    "_reason",
    "_why",
    "_unsupported",
    "_disabled",
    "_ready",
    "_home",
    "_trouble",
)


def _package(without: tuple[str, ...] = (), **fields: Any) -> types.ModuleType:
    """
    A stand-in imtypeset as a module object, for `sys.modules`.
    """
    made = types.ModuleType("imtypeset")
    made.__file__ = "/somewhere/site/imtypeset/__init__.py"
    exec(pairing.standin(without=without, **fields), made.__dict__)  # noqa: S102
    if "demo" not in without:
        made.demo = types.ModuleType("imtypeset.demo")  # type: ignore[attr-defined]
    return made


class Gate:
    """
    The typesetter with nothing to find, and ways to give it something.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.imports = 0
        self.installed: str | None = None

    def name_a_library(self, where: str = "/somewhere/libimtypeset_bundle.so") -> None:
        self.monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, where)

    def offer(self, package: types.ModuleType | None) -> None:
        """
        What `import imtypeset` finds from now on; `None` for nothing.
        """
        if package is None:
            self.monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
        else:
            self.monkeypatch.setitem(sys.modules, "imtypeset", package)


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> Iterator[Gate]:
    made = Gate(monkeypatch)
    kept = {name: getattr(typesetter, name) for name in _STATE}
    logged = set(typesetter._logged)
    real = typesetter.importlib.import_module

    def counted(name: str) -> Any:
        if name == "imtypeset":
            made.imports += 1
        return real(name)

    def distribution(name: str) -> Any:
        if made.installed is None:
            raise metadata.PackageNotFoundError(name)
        return types.SimpleNamespace(version=made.installed)

    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(metadata, "distribution", distribution)
    monkeypatch.setattr(metadata, "requires", lambda name: [])
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "imtypeset" not in p])
    monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
    monkeypatch.setattr(typesetter.importlib, "import_module", counted)
    typesetter._forget()
    try:
        yield made
    finally:
        for name, value in kept.items():
            setattr(typesetter, name, value)
        typesetter._logged.clear()
        typesetter._logged.update(logged)


# ---------------------------------------------------------------------------
# P1: the kind beside the sentence
# ---------------------------------------------------------------------------


def test_the_kinds_are_these_six_and_their_values_are_strings() -> None:
    assert {member.name: member.value for member in Kind} == {
        "READY": "ready",
        "NOT_INSTALLED": "not-installed",
        "REFUSED": "refused",
        "FAILED": "failed",
        "UNSUPPORTED": "unsupported",
        "UNCHECKED": "unchecked",
    }
    assert set(typesetter.EXIT_CODES) == set(Kind)
    codes = list(typesetter.EXIT_CODES.values())
    assert typesetter.EXIT_CODES[Kind.READY] == 0
    assert len(set(codes)) == len(codes), "two kinds exit with the same number"
    assert not {1, 2} & set(codes), "1 and 2 are the interpreter's own"


def test_nothing_to_find_is_not_installed_and_the_sentence_is_the_old_one(gate: Gate) -> None:
    assert typesetter.kind() is Kind.NOT_INSTALLED
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"
    assert typesetter.pairing()["kind"] == "not-installed"
    assert gate.imports == 0, "something was imported to find that out"


def test_a_library_that_is_named_and_does_not_load_is_refused(gate: Gate) -> None:
    gate.name_a_library()
    assert typesetter.kind() is Kind.REFUSED
    assert typesetter.reason().startswith("ModuleNotFoundError: ")
    assert typesetter.pairing()["kind"] == "refused"
    assert typesetter.pairing()["route"] == typesetter.ROUTE_NONE


def test_an_installed_distribution_that_does_not_load_is_refused_and_named(gate: Gate) -> None:
    gate.installed = "0.9.0"
    assert typesetter.kind() is Kind.REFUSED
    assert typesetter.reason().startswith(
        "the installed imtypeset 0.9.0 did not load: ModuleNotFoundError: "
    )


def test_a_package_that_answers_is_ready_and_ready_says_nothing_of_fonts(gate: Gate) -> None:
    gate.name_a_library()
    gate.offer(_package())
    assert typesetter.kind() is Kind.READY
    assert typesetter.reason() == ""
    assert typesetter.pairing()["kind"] == "ready"
    assert typesetter.module() is not None and not typesetter.ready()


def test_a_disable_is_failed_whatever_it_was_before(gate: Gate) -> None:
    gate.name_a_library()
    gate.offer(_package())
    assert typesetter.kind() is Kind.READY
    typesetter.disable("Error: the font was refused")
    assert typesetter.kind() is Kind.FAILED
    assert typesetter.reason() == "Error: the font was refused"
    pairing_now = typesetter.pairing()
    assert pairing_now["kind"] == "failed"
    assert pairing_now["route"] == typesetter.ROUTE_ENVIRONMENT, "the package is still what is here"


def test_kind_is_ready_exactly_when_module_answers(
    gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Other files' tests stand a library in by setting `_ts` directly. The kind
    follows `module()` and cannot contradict it.
    """
    assert typesetter.kind() is Kind.NOT_INSTALLED
    monkeypatch.setattr(typesetter, "_ts", object())
    assert typesetter.kind() is Kind.READY


# -- unsupported: only a host can say it ----------------------------------


def test_unsupported_is_the_hosts_to_say_and_only_when_nothing_is_found(gate: Gate) -> None:
    typesetter.unsupported("pptmstr ships no typesetting library for Intel Macs")
    assert typesetter.kind() is Kind.UNSUPPORTED
    assert typesetter.reason() == "pptmstr ships no typesetting library for Intel Macs"
    assert typesetter.pairing()["kind"] == "unsupported"
    assert gate.imports == 0
    # It is the host's statement and not a refusal: the way back keeps it.
    typesetter.reset()
    assert typesetter.kind() is Kind.UNSUPPORTED
    # Taken back.
    typesetter.unsupported("")
    assert typesetter.kind() is Kind.NOT_INSTALLED
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"


def test_what_is_found_is_the_evidence_and_the_hosts_sentence_is_not_used(gate: Gate) -> None:
    typesetter.unsupported("no library here")
    gate.name_a_library()
    assert typesetter.kind() is Kind.REFUSED, "a named library that does not load is a fault"
    assert "no library here" not in typesetter.reason()
    typesetter.reset()
    gate.offer(_package())
    assert typesetter.kind() is Kind.READY


def test_unsupported_said_after_the_first_question_is_heard_at_once(gate: Gate) -> None:
    assert typesetter.kind() is Kind.NOT_INSTALLED
    typesetter.unsupported("no library here")
    assert typesetter.reason() == "no library here"
    assert typesetter.kind() is Kind.UNSUPPORTED


@pytest.mark.parametrize("given", [None, 3, b"no", ["no"]], ids=repr)
def test_unsupported_takes_a_sentence_and_nothing_else(gate: Gate, given: Any) -> None:
    with pytest.raises(TypeError, match="unsupported\\(\\) takes a sentence, not "):
        typesetter.unsupported(given)
    assert typesetter.kind() is Kind.NOT_INSTALLED


# ---------------------------------------------------------------------------
# P18: the way back
# ---------------------------------------------------------------------------


def test_reset_after_a_disable_asks_again_and_fonts_are_to_be_loaded_again(
    gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    pptmstr: "One provoked failure switches the library off for the rest of a
    test process; only the private `_forget()` undoes it."
    """
    gate.name_a_library()
    package = _package()
    gate.offer(package)
    assert typesetter.module() is package and gate.imports == 1
    monkeypatch.setattr(typesetter, "_ready", True)
    typesetter.disable("a view's draw raised")
    assert typesetter.module() is None and gate.imports == 1, "a disable is remembered"

    typesetter.reset()
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set", "as before the first question"
    assert typesetter.module() is package and gate.imports == 2, "the next module() asked again"
    assert typesetter.kind() is Kind.READY and typesetter.reason() == ""
    assert not typesetter.ready(), "ready() is false until load_fonts() is called again"


def test_reset_after_a_refusal_imports_again(gate: Gate) -> None:
    gate.name_a_library()
    assert typesetter.module() is None and typesetter.kind() is Kind.REFUSED
    gate.offer(_package())
    assert typesetter.module() is None and gate.imports == 1, "a refusal is remembered"
    typesetter.reset()
    assert typesetter.module() is not None and gate.imports == 2
    assert typesetter.kind() is Kind.READY


def test_reset_finds_a_distribution_installed_since(gate: Gate) -> None:
    assert typesetter.module() is None
    gate.installed = "1.0.0"
    gate.offer(_package())
    assert typesetter.module() is None, "the distribution is looked for once"
    typesetter.reset()
    assert typesetter.module() is not None
    found = typesetter.pairing()
    assert found["route"] == typesetter.ROUTE_DISTRIBUTION
    assert found["distribution"] == "imtypeset 1.0.0"


def test_what_reset_keeps_and_what_it_lets_be_said_again(
    gate: Gate, caplog: pytest.LogCaptureFixture
) -> None:
    gate.name_a_library()
    gate.offer(_package())
    assert typesetter.module() is not None
    typesetter.note("no font file for code-bold; set in the document's face")
    with caplog.at_level(logging.WARNING, logger="advtext.typesetter"):
        typesetter.disable("the same failure")
        typesetter.disable("the same failure")
        assert [r.getMessage() for r in caplog.records].count(
            "imtypeset is switched off for this run: the same failure"
        ) == 1, "once per distinct message"
        typesetter.reset()
        assert typesetter.trouble() == "no font file for code-bold; set in the document's face"
        assert typesetter._package is not None, "unload() must still reach the context"
        typesetter.disable("the same failure")
        assert [r.getMessage() for r in caplog.records].count(
            "imtypeset is switched off for this run: the same failure"
        ) == 2, "after a reset the same failure is said again"


def test_forget_is_still_the_state_at_import(gate: Gate) -> None:
    gate.name_a_library()
    gate.offer(_package())
    typesetter.unsupported("no library here")
    assert typesetter.module() is not None
    typesetter.note("something got over")
    typesetter._forget()
    assert typesetter._package is None and typesetter.trouble() == ""
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"
    assert typesetter._why is Kind.NOT_INSTALLED


# ---------------------------------------------------------------------------
# P3: the imtypeset that was found has the names this advtext calls
# ---------------------------------------------------------------------------


def test_a_package_with_every_name_lacks_nothing() -> None:
    assert typesetter.missing(_package()) == []


@pytest.mark.parametrize(
    ("without", "expected"),
    [
        (("stats",), ["stats"]),
        (("Document.pack_marks",), ["Document.pack_marks"]),
        (("DocumentOptions.CodeOverflow",), ["DocumentOptions.CodeOverflow"]),
        (("CodeOverflow.Grow",), ["CodeOverflow.Grow"]),
        # An owner that is absent is said once, not once per name it would hold.
        (("Document",), ["Document"]),
        # The package's demo is not asked for (2026-10-12, the lead's decision
        # D1 of PH-FIX): only the Specimen page draws it, and says so itself.
        (("demo",), []),
    ],
    ids=lambda value: value[0] if isinstance(value, tuple) else None,
)
def test_missing_names_what_is_not_there(without: tuple[str, ...], expected: list[str]) -> None:
    assert typesetter.missing(_package(without)) == expected


def test_a_tuple_the_library_reads_by_position_must_begin_with_advtexts_fields() -> None:
    ours = typesetter.BlockDescription._fields
    assert typesetter.missing(_package(Block=(*ours, "later"))) == [], "more fields after are fine"
    swapped = (ours[1], ours[0], *ours[2:])
    assert typesetter.missing(_package(Block=swapped)) == [f"Block.{ours[0]}"]
    assert typesetter.missing(_package(Run=typesetter.RunDescription._fields[:-1])) == [
        f"Run.{typesetter.RunDescription._fields[-1]}"
    ]


def test_missing_never_raises_whatever_it_is_handed() -> None:
    class Raises:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError(name)

    assert len(typesetter.missing(Raises())) >= len(typesetter.REQUIRED[""])
    assert typesetter.missing(None)


def test_a_package_that_lacks_a_name_is_refused_with_a_sentence_that_names_it(gate: Gate) -> None:
    """
    New advtext beside an old imtypeset: it must fall back at the gate, where
    a view turns it into `TypesetUnavailable`, and not raise AttributeError
    inside a draw.
    """
    gate.name_a_library()
    gate.offer(_package(("Document.pack_marks",)))
    assert typesetter.module() is None
    assert typesetter.kind() is Kind.REFUSED
    assert typesetter.reason() == (
        "the imtypeset at /somewhere/site/imtypeset lacks 1 name this advtext calls: "
        "Document.pack_marks; the two were not installed together"
    )
    found = typesetter.pairing()
    assert found["kind"] == "refused"
    # Which package was refused is what a bug report needs.
    assert found["route"] == typesetter.ROUTE_ENVIRONMENT
    assert found["package"] == "/somewhere/site/imtypeset"
    with pytest.raises(RuntimeError, match="imtypeset is not in use: the imtypeset at "):
        typesetter.block_styles([])
    assert typesetter.module() is None and gate.imports == 1, "the refusal is remembered"


def test_the_sentence_names_five_and_counts_the_rest(gate: Gate) -> None:
    gate.name_a_library()
    without = ("stats", "add_font", "Document.draw", "Document.layout", "Style.EmSize", "Face.Code")
    gate.offer(_package((*without, "MarkPlace.Ink")))
    assert typesetter.module() is None
    reason = typesetter.reason()
    assert " lacks 7 names this advtext calls: " in reason and reason.count(",") == 4
    assert " and 2 more; " in reason


# -- the list against advtext's own sources --------------------------------

_SOURCES = sorted((_ROOT / "advtext").rglob("*.py"))
# How a module of advtext comes by the package: a name bound from one of
# these calls, or the call itself with an attribute taken straight off it.
_GATE_CALLS = {"typesetter.module", "module", "_must", "self._ready"}
_GATE_VALUES = {"_ts", "_package", "importlib.import_module('imtypeset')"}
# What a library document is called where one is used. A receiver spelled
# another way is not seen by `test_every_document_method...`; the test after
# it is the net under this one, and needs the pinned package to read.
_DOCUMENT = re.compile(
    r"^(doc|document|tiny|scratch|extra|gutter|code|self\._doc|self\._docs\[.+\])$"
)
# Used, and not on the list because the gate cannot ask for it: `missing`
# reads the CLASS, and making a document to read an instance needs a context.
_ON_AN_INSTANCE = {
    "edit_error": "set in Document.__init__ (what a cut edit said); read after an edit",
}
_DOCUMENT_FILES = (
    "typeset_view.py",
    "typeset_stream_view.py",
    "typeset_diff_view.py",
    "typeset_find.py",
)


def _listed() -> set[str]:
    listed = set(typesetter.REQUIRED[""])
    for owner, names in typesetter.REQUIRED.items():
        listed |= {f"{owner}.{name}" for name in names if owner}
    for owner, names in typesetter._IN_ORDER.items():
        listed |= {f"{owner}.{name}" for name in names}
    return listed


def _package_uses(path: Path) -> dict[str, int]:
    """
    Every name of the package `path` uses, as `missing` spells it, with a line it is on.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            value = node.value
            from_gate = isinstance(value, ast.Call) and ast.unparse(value.func) in _GATE_CALLS
            if from_gate or ast.unparse(value) in _GATE_VALUES:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                bound |= {target.id for target in targets if isinstance(target, ast.Name)}

    def is_package(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in bound
        return ast.unparse(node) == "typesetter.module()"

    uses: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and not node.attr.startswith("_"):
            if is_package(node.value):
                uses.setdefault(node.attr, node.lineno)
            elif isinstance(node.value, ast.Attribute) and is_package(node.value.value):
                uses.setdefault(f"{node.value.attr}.{node.attr}", node.lineno)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and is_package(node.func.value)
            and node.func.attr[
                :1
            ].isupper()  # a type's fields; a function's keywords are not listed
        ):
            for keyword in node.keywords:
                if keyword.arg is not None:
                    uses.setdefault(f"{node.func.attr}.{keyword.arg}", node.lineno)
    return uses


def test_every_name_of_the_package_advtext_uses_is_on_the_list() -> None:
    """
    THE test that fails when advtext starts calling a name the gate does not
    ask for. The fix is one line in `typesetter.REQUIRED`.
    """
    listed = _listed()
    seen: set[str] = set()
    unlisted: list[str] = []
    for path in _SOURCES:
        for name, line in _package_uses(path).items():
            seen.add(name)
            if name not in listed:
                unlisted.append(f"{path.relative_to(_ROOT)}:{line}: {name}")
    assert not unlisted, (
        "advtext uses names of imtypeset that typesetter.REQUIRED does not list, so an "
        "imtypeset without them would not be refused at the gate:\n  " + "\n  ".join(unlisted)
    )
    # The reader itself: if it stopped seeing the package it would pass blind.
    assert {"Document", "BlockStyle.Scale", "Face.Code", "add_font", "font_atlas_index"} <= seen


def test_every_document_method_advtext_calls_is_on_the_list() -> None:
    listed = set(typesetter.REQUIRED["Document"])
    seen: set[str] = set()
    unlisted: list[str] = []
    for path in _SOURCES:
        if path.name not in _DOCUMENT_FILES:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and _DOCUMENT.match(ast.unparse(node.value)):
                seen.add(node.attr)
                if node.attr.startswith("_") or node.attr in _ON_AN_INSTANCE:
                    continue
                if node.attr not in listed:
                    unlisted.append(
                        f"{path.relative_to(_ROOT)}:{node.lineno}: Document.{node.attr}"
                    )
    assert not unlisted, (
        "advtext calls methods of an imtypeset Document that typesetter.REQUIRED does not "
        "list:\n  " + "\n  ".join(unlisted)
    )
    assert {"layout", "draw", "hit_test", "set_blocks", "pack_marks", "append_text"} <= seen
    assert set(_ON_AN_INSTANCE) <= seen, "an explanation of something no longer used"
    assert not set(_ON_AN_INSTANCE) & listed


# A public name of the pinned `imtypeset.Document` that appears as an
# attribute in advtext's typeset layer and is NOT a call on a library
# document there. Each needs its reason; a name that is neither here nor on
# the list fails the test below.
_NOT_THE_LIBRARYS = {
    "view": "a hosted block's `view`, and a page's: advtext's own views",
}


def test_no_document_method_is_used_under_a_name_the_reader_does_not_know() -> None:
    """
    The net under the test above, which knows a document by what it is called.
    This one knows it by what the pinned package's `Document` HAS: any of its
    public names used as an attribute anywhere in the typeset layer is on the
    list or explained.
    """
    where = os.environ.get(typesetter.PACKAGE_VARIABLE)
    if not where:
        pytest.skip(
            "IMTYPESET_PYTHON is not set: run `make test TYPESET=1` to read the pinned "
            "package's Document for its method names"
        )
    source = (Path(where) / "imtypeset" / "__init__.py").read_text(encoding="utf-8")
    document = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "Document"
    )
    public = {
        node.name
        for node in document.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert set(typesetter.REQUIRED["Document"]) <= public, "the list names what is not there"
    used: dict[str, str] = {}
    for path in _SOURCES:
        if path.name not in (*_DOCUMENT_FILES, "typeset_hosts.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in public:
                used.setdefault(node.attr, f"{path.relative_to(_ROOT)}:{node.lineno}")
    unexplained = {
        name: at
        for name, at in used.items()
        if name not in typesetter.REQUIRED["Document"] and name not in _NOT_THE_LIBRARYS
    }
    assert not unexplained, unexplained
    assert set(_NOT_THE_LIBRARYS) <= set(used), "an explanation of something no longer there"


# ---------------------------------------------------------------------------
# P2: a verdict from a child, and the command line
# ---------------------------------------------------------------------------


def _command_line(env: dict[str, str], *path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-B", "-W", "error", "-m", "advtext.typesetter"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**env, "PYTHONPATH": os.pathsep.join([str(_ROOT), *map(str, path)])},
        cwd=str(_ROOT),
    )


def test_the_command_line_prints_the_pairing_and_exits_by_its_kind(tmp_path: Path) -> None:
    nothing = _command_line(pairing._without())
    assert nothing.returncode == typesetter.EXIT_CODES[Kind.NOT_INSTALLED] == 3, nothing.stderr
    assert nothing.stdout.count("\n") == 1, "one line, for whoever reads it with a program"
    said = json.loads(nothing.stdout)
    assert set(said) == pairing._KEYS
    assert said["kind"] == "not-installed" and said["reason"] == "IMTYPESET_LIBRARY is not set"
    assert nothing.stderr == "", "running the module by -m warned, or logged"

    site = pairing._a_distribution(tmp_path / "whole")
    ready = _command_line(pairing._without(), site)
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["kind"] == "ready"
    assert json.loads(ready.stdout)["distribution"] == "imtypeset 0.9.0"

    old = pairing._a_distribution(tmp_path / "old", without=("Document.set_columns",))
    refused = _command_line(pairing._without(), old)
    assert refused.returncode == typesetter.EXIT_CODES[Kind.REFUSED] == 4, refused.stderr
    said = json.loads(refused.stdout)
    assert said["kind"] == "refused" and "Document.set_columns" in said["reason"]
    assert said["package"] == str(old / "imtypeset")


def _asking(monkeypatch: pytest.MonkeyPatch, *path: Path) -> None:
    """
    This process, as a host that has `path` on its own path and no variable.
    """
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(_ROOT), *map(str, path)]))


def test_a_verdict_is_a_childs_answer_and_leaves_the_asking_process_as_it_was(
    gate: Gate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    pptmstr: "A gate verdict for a pair without drawing, and without it being
    remembered for the process ... `module()` is once per process."
    """
    site = pairing._a_distribution(tmp_path)
    _asking(monkeypatch, site)
    # This process has been switched off; that is not the child's business.
    typesetter.disable("a view's draw raised")
    before = {name: getattr(typesetter, name) for name in _STATE}

    said = typesetter.verdict()
    assert set(said) == pairing._KEYS
    assert said["kind"] == "ready" and said["reason"] == ""
    assert said["route"] == typesetter.ROUTE_DISTRIBUTION
    assert said["package"] == str(site / "imtypeset")
    assert said["wheel_version"] == "1.92.900"

    assert {name: getattr(typesetter, name) for name in _STATE} == before, "it was remembered"
    assert "imtypeset" not in sys.modules, "the library's package was loaded into this process"
    assert typesetter.kind() is Kind.FAILED and gate.imports == 0
    assert typesetter.verdict() == said, "it can be asked as often as wanted"


def test_a_verdict_names_the_library_for_the_child_and_an_empty_one_takes_it_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = pairing._a_distribution(tmp_path)
    _asking(monkeypatch, site)
    named = typesetter.verdict(tmp_path / "dev" / "lib.so")
    assert named["kind"] == "ready" and named["route"] == typesetter.ROUTE_ENVIRONMENT
    # This process names a library; "" asks about the installed distribution alone.
    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "dev" / "lib.so"))
    assert typesetter.verdict()["route"] == typesetter.ROUTE_ENVIRONMENT
    assert typesetter.verdict("")["route"] == typesetter.ROUTE_DISTRIBUTION
    # And a pair that would be refused is said so, without this process trying it.
    _asking(monkeypatch)
    refused = typesetter.verdict(tmp_path / "absent.so", tmp_path / "nowhere")
    assert refused["kind"] == "refused"
    assert refused["reason"].startswith("ModuleNotFoundError: ")
    assert typesetter.verdict("", "")["kind"] == "not-installed"


def test_in_a_frozen_application_the_verdict_is_unchecked_and_no_child_is_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    There `sys.executable` is the application, which would be started a
    second time with `-P -B -c`: pptmstr's argument parser rejects that (P6).
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("a child was started"))
    said = typesetter.verdict()
    assert set(said) == pairing._KEYS
    assert said["kind"] == "unchecked" and said["route"] == typesetter.ROUTE_NONE
    assert said["reason"].startswith("this is a frozen application (sys.frozen)")
    assert {key for key, value in said.items() if value is None} == pairing._KEYS - {
        "kind",
        "reason",
        "route",
    }


def test_a_child_that_cannot_be_asked_is_unchecked_and_one_that_is_killed_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _asking(monkeypatch)
    monkeypatch.setattr(typesetter, "_CHILD", "import time; time.sleep(60)")
    slow = typesetter.verdict(timeout=0.5)
    assert slow["kind"] == "unchecked"
    assert slow["reason"] == "the child interpreter did not answer in 0.5 seconds"

    monkeypatch.setattr(typesetter, "_CHILD", "import sys; sys.exit('no advtext here')")
    silent = typesetter.verdict()
    assert silent["kind"] == "unchecked"
    assert silent["reason"] == (
        "the child interpreter exited 1 without an answer (no advtext here)"
    )

    monkeypatch.setattr(
        typesetter, "_CHILD", f"import os; os.kill(os.getpid(), {int(signal.SIGKILL)})"
    )
    killed = typesetter.verdict()
    assert killed["kind"] == "refused", "a library that kills what loads it must not be switched to"
    assert killed["reason"].startswith(
        f"the child interpreter was killed by signal {int(signal.SIGKILL)} before it answered"
    )

    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-such-python"))
    absent = typesetter.verdict()
    assert absent["kind"] == "unchecked"
    assert absent["reason"].startswith("the child interpreter did not start: FileNotFoundError")
    monkeypatch.setattr(sys, "executable", "")
    assert typesetter.verdict()["reason"].startswith("sys.executable is empty")


@pytest.mark.parametrize(
    ("arguments", "error", "says"),
    [
        ({"library": 3}, TypeError, "takes a path for IMTYPESET_LIBRARY, not int"),
        ({"library": b"lib.so"}, TypeError, "takes a path for IMTYPESET_LIBRARY, not bytes"),
        ({"python_path": ["a"]}, TypeError, "takes a path for IMTYPESET_PYTHON, not list"),
        ({"timeout": "5"}, TypeError, "takes a timeout in seconds, not str"),
        ({"timeout": True}, TypeError, "takes a timeout in seconds, not bool"),
        ({"timeout": 0}, ValueError, "takes a timeout above zero, not 0"),
        ({"timeout": float("nan")}, ValueError, "takes a timeout above zero, not nan"),
    ],
    ids=lambda value: None if isinstance(value, type) else str(value),
)
def test_what_verdict_is_handed_is_checked_before_any_child_is_started(
    arguments: dict[str, Any], error: type[Exception], says: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("a child was started"))
    with pytest.raises(error, match=re.escape(says)):
        typesetter.verdict(**arguments)


# ---------------------------------------------------------------------------
# P14: the ImFont of a face
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("given", ["CODE", 5, None, Face], ids=repr)
def test_font_takes_a_face_and_nothing_else(gate: Gate, given: Any) -> None:
    with pytest.raises(TypeError, match="font\\(\\) takes an advtext Face, not "):
        typesetter.font(given)


def test_font_is_none_until_the_fonts_are_loaded_and_never_asks_before(
    gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[int] = []
    package = _package()
    package.font_atlas_index = lambda role: asked.append(role)  # type: ignore[attr-defined]
    gate.name_a_library()
    gate.offer(package)
    assert typesetter.font(Face.CODE) is None and gate.imports == 0, "font() made the import"
    assert typesetter.module() is package
    assert typesetter.font(Face.CODE) is None and asked == [], "asked before load_fonts"
    monkeypatch.setattr(typesetter, "_ready", True)
    assert typesetter.font(Face.CODE) is None, "a role with no font is None"
    assert asked == [typesetter.FACE_ROLE[Face.CODE]]


def test_a_library_that_raises_when_asked_for_a_font_is_a_trouble_and_none(
    gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raises(role: int) -> int:
        raise ValueError("no context")

    package = _package()
    package.font_atlas_index = raises  # type: ignore[attr-defined]
    gate.name_a_library()
    gate.offer(package)
    assert typesetter.module() is package
    monkeypatch.setattr(typesetter, "_ready", True)
    assert typesetter.font(Face.PROSE) is None
    assert typesetter.trouble() == "font: ValueError: no context"
    assert typesetter.kind() is Kind.READY, "a question switched the library off"


# ---------------------------------------------------------------------------
# With the library: the pinned pair
# ---------------------------------------------------------------------------

_REAL = """
import json, sys
from imgui_bundle import imgui
from advtext import Face, typesetter
from advtext.typesetter import Kind
report = {"verdict": typesetter.verdict(),
          "loaded_by_the_verdict": sorted(n for n in sys.modules if n.split(".")[0] == "imtypeset"),
          "before": typesetter.font(Face.CODE) is None}
ts = typesetter.module()
report["missing"] = typesetter.missing(ts)
report["kind"] = typesetter.kind().value
context = imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures
imgui.get_io().set_ini_filename(None)
report["unloaded"] = typesetter.font(Face.CODE) is None
report["fonts"] = typesetter.load_fonts()
atlas = imgui.get_io().fonts.fonts
report["faces"] = {}
for face in Face:
    font = typesetter.font(face)
    index = ts.font_atlas_index(typesetter.FACE_ROLE[face])
    report["faces"][face.name] = [index, font is not None and font is atlas[index]]

# The way back, with real fonts: a provoked failure, reset, load again.
typesetter.disable("a provoked failure")
report["failed"] = [typesetter.kind().value, typesetter.ready(), typesetter.font(Face.CODE) is None]
typesetter.reset()
report["reset"] = [typesetter.module() is ts, typesetter.kind().value, typesetter.ready()]
report["again"] = [typesetter.load_fonts(), typesetter.ready(), typesetter.reason()]
theme_blocks = [ts.Block(ts.BlockKind.Paragraph, "set after the way back")]
doc = ts.Document.from_blocks(theme_blocks, [ts.BlockStyle(Scale=1.0)])
report["laid_out"] = bool(doc.layout(300.0, ts.Style(EmSize=16.0, PixelsPerInch=96.0)))
report["size"] = list(doc.size())
doc.close()
typesetter.unload()
report["after_unload"] = typesetter.font(Face.CODE) is None
imgui.destroy_context(context)
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def real() -> dict[str, Any]:
    pairing._the_pair()
    return pairing._child(_REAL, dict(os.environ))


def test_the_pinned_library_has_every_name_on_the_list(real: dict[str, Any]) -> None:
    assert real["missing"] == []
    assert real["kind"] == "ready"


def test_the_verdict_on_the_pinned_pair_is_ready_and_loads_nothing_into_the_asker(
    real: dict[str, Any],
) -> None:
    library, package = pairing._the_pair()
    said = real["verdict"]
    assert said["kind"] == "ready", said["reason"]
    assert said["library"] == str(library) and said["package"] == str(package)
    assert said["wheel_version"] == metadata.version("imgui-bundle")
    assert real["loaded_by_the_verdict"] == [], "the asking process loaded the package"


def test_the_command_line_on_the_pinned_pair_exits_zero_and_on_a_bad_library_four(
    tmp_path: Path,
) -> None:
    library, _package_directory = pairing._the_pair()
    ready = _command_line(dict(os.environ))
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["library"] == str(library)
    bad = tmp_path / "not-a-library.so"
    bad.write_bytes(b"not a shared object")
    refused = _command_line({**os.environ, typesetter.LIBRARY_VARIABLE: str(bad)})
    assert refused.returncode == typesetter.EXIT_CODES[Kind.REFUSED], refused.stdout
    assert json.loads(refused.stdout)["kind"] == "refused"


def test_font_is_the_librarys_own_entry_in_the_atlas_for_every_face(real: dict[str, Any]) -> None:
    assert real["before"] is True and real["unloaded"] is True, "a font before load_fonts()"
    assert real["fonts"] is True
    assert set(real["faces"]) == {face.name for face in Face}
    for name, (index, same) in real["faces"].items():
        assert index is not None and same, f"{name}: font() is not atlas entry {index}"
    assert real["after_unload"] is True, "a font after unload()"


def test_the_way_back_with_real_fonts_sets_text_again(real: dict[str, Any]) -> None:
    assert real["failed"] == ["failed", False, True]
    assert real["reset"] == [True, "ready", False], "same package, ready() false until loaded"
    assert real["again"] == [True, True, ""]
    assert real["laid_out"] is True and real["size"][1] > 0


# ---------------------------------------------------------------------------
# P17: load_fonts() again, long after start-up, in a real window
# ---------------------------------------------------------------------------

_LATE = '''
"""load_fonts() called again between frames after start-up, with a view open. One JSON line."""
import json
import sys
import time
from pathlib import Path

import imgui_bundle
from imgui_bundle import hello_imgui, imgui, immapp

from advtext import DARK_PALETTE, Face, Theme, TypesetUnavailable, TypesetView, register_font
from advtext import typesetter

SOURCE = (
    "# Heading\\n\\nprose **bold** *it* `code` and a [link](http://x)\\n\\n"
    "```\\nx = 1\\n```\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n"
)
TEXT = "Hxg0123456789"
SAMPLE = "The quick brown fox jumps over the lazy dog"
other = Path(imgui_bundle.__file__).parent / "assets" / "fonts" / "DroidSans.ttf"
theme = Theme.build()
report = {"loads": [], "frames": [], "raised": []}
state = {"frame": 0, "view": None, "kept": None, "document": None}


def atlas():
    return imgui.get_io().fonts.fonts


def load(label):
    before = len(atlas())
    kept = state["kept"]
    started = time.perf_counter()
    ok = typesetter.load_fonts()
    took = 1000 * (time.perf_counter() - started)
    prose = typesetter.font(Face.PROSE)
    report["loads"].append({
        "label": label, "frame": state["frame"], "ok": ok, "ms": round(took, 2),
        "fonts_before": before, "fonts_after": len(atlas()),
        "ready": typesetter.ready(), "reason": typesetter.reason(),
        "kind": typesetter.kind().value,
        "prose": None if prose is None else prose.get_debug_name(),
        "prose_is_a_new_entry": kept is not None and prose is not kept,
        "kept_still_in_the_atlas": None if kept is None else any(f is kept for f in atlas()),
    })
    state["kept"] = prose


def start():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    load("start-up")


def between_frames():
    frame = state["frame"]
    if frame == 5:
        load("again, the same files")
    if frame == 8:
        typesetter.disable("a provoked failure")
    if frame == 9:
        typesetter.reset()
        load("after disable and reset")
    if frame == 12:
        register_font(Face.PROSE, other)
        load("PROSE is another file")
    if frame == 15:
        before = len(atlas())
        typesetter.unload()
        report["unload"] = {"fonts_before": before, "fonts_after": len(atlas())}
    if frame == 17:
        load("after unload")


def ink(draw_list, start):
    """The box around every vertex added since `start`: [width, height]."""
    buffer = draw_list.vtx_buffer
    xs = [buffer[i].pos.x for i in range(start, buffer.size())]
    ys = [buffer[i].pos.y for i in range(start, buffer.size())]
    return [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]


def sizes(draw_list):
    """The same characters typeset at an em, and native at the em and at the em's line height."""
    from fontTools.ttLib import TTFont

    from advtext import fontlib

    ts = typesetter.module()
    rows = []
    for face, em in ((Face.CODE, 16.0), (Face.PROSE, 16.0), (Face.CODE, 21.0)):
        file = TTFont(str(fontlib.font_file(face)))
        ratio = (file["hhea"].ascent - file["hhea"].descent) / file["head"].unitsPerEm
        origin = imgui.get_cursor_screen_pos()
        with ts.Document.from_blocks(
            [ts.Block(ts.BlockKind.Paragraph, TEXT)],
            [ts.BlockStyle(
                Face=int(typesetter.FACE_ROLE[face]), Scale=1.0, Align=int(ts.Align.Left)
            )],
        ) as tiny:
            tiny.layout(650.0, ts.Style(EmSize=em, PixelsPerInch=96.0))
            before = draw_list.vtx_buffer.size()
            tiny.draw(None, (origin.x, origin.y))
            row = {"face": face.name, "em": em, "ratio": round(ratio, 4),
                   "typeset_ink": ink(draw_list, before),
                   "typeset_laid": round(float(tiny.caret_rect((0, len(TEXT)))[0]), 3)}
            imgui.dummy((10.0, tiny.size()[1]))
        font = typesetter.font(face)
        for label, size in (("at_the_em", em), ("at_the_line", em * ratio)):
            imgui.push_font(font, size)
            before = draw_list.vtx_buffer.size()
            imgui.text_unformatted(TEXT)
            row[label] = {"pushed": round(imgui.get_font_size(), 3),
                          "ink": ink(draw_list, before),
                          "wide": round(imgui.calc_text_size(TEXT).x, 3)}
            imgui.pop_font()
        rows.append(row)
    return rows


def gui():
    frame = state["frame"]
    imgui.set_next_window_size((700, 500))
    imgui.begin("w")
    row = {"frame": frame, "atlas": len(atlas())}
    try:
        if state["view"] is None:
            state["view"] = TypesetView(SOURCE, theme=theme, palette=DARK_PALETTE)
        view = state["view"]
        draw_list = imgui.get_window_draw_list()
        before = draw_list.vtx_buffer.size()
        view.draw(palette=DARK_PALETTE)
        row["vertices"] = draw_list.vtx_buffer.size() - before
        row["same_document"] = view._doc is state["document"]
        state["document"] = view._doc
        imgui.push_font(typesetter.font(Face.PROSE), 16.0)
        row["native_prose"] = round(imgui.calc_text_size(SAMPLE).x, 3)
        imgui.pop_font()
        if frame == 3:
            report["sizes"] = sizes(draw_list)
    except TypesetUnavailable as exc:
        row["unavailable"] = str(exc)
    except Exception as exc:  # noqa: BLE001 -- reported, and the test fails on it
        report["raised"].append(f"frame {frame}: {type(exc).__name__}: {exc}")
    imgui.end()
    report["frames"].append(row)
    state["frame"] += 1
    if state["frame"] >= 20:
        hello_imgui.get_runner_params().app_shall_exit = True


params = hello_imgui.RunnerParams()
params.ini_disable = True
params.app_window_params.window_geometry.size = (800, 600)
params.callbacks.load_additional_fonts = start
params.callbacks.pre_new_frame = between_frames
params.callbacks.show_gui = gui
params.callbacks.before_exit = typesetter.unload
immapp.run(params)
report["roles"] = len(set(typesetter.FACE_ROLE.values()))
print(json.dumps(report))
'''


@pytest.fixture(scope="module")
def late(window: Window) -> dict[str, Any]:
    pairing._the_pair()
    script = window.out / "typesetter_late_load.py"
    script.write_text(_LATE, encoding="utf-8")
    done = window.run([str(script)], timeout=300.0)
    assert done.returncode == 0, f"the window run failed:\n{done.stdout}\n{done.stderr[-3000:]}"
    report: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["raised"] == [], report["raised"]
    return report


def test_after_start_up_the_atlas_takes_the_fonts_every_time(late: dict[str, Any]) -> None:
    """
    pptmstr, P17: "The operator turns typeset text on, and changes the
    proportional family, from the settings dialog while sessions are open."
    """
    loads = late["loads"]
    assert [load["label"] for load in loads] == [
        "start-up",
        "again, the same files",
        "after disable and reset",
        "PROSE is another file",
        "after unload",
    ]
    assert [load["frame"] for load in loads] == [0, 5, 9, 12, 17], "not after start-up"
    for load in loads:
        assert load["ok"] is True and load["ready"] is True, load
        assert load["reason"] == "" and load["kind"] == "ready", load
        assert load["fonts_after"] - load["fonts_before"] == late["roles"] == 7, load
    assert loads[3]["prose"] != loads[1]["prose"], "the role's new file was not the one loaded"


def test_nothing_is_taken_off_the_atlas_by_a_later_load_or_by_unload(late: dict[str, Any]) -> None:
    """
    What is NOT promised, held so that the docstring cannot drift from it: 7
    more fonts for every call. When the library starts taking its fonts off,
    this fails and the docstring is what changes.
    """
    loads = late["loads"]
    assert [load["fonts_after"] for load in loads] == [8, 15, 22, 29, 36]
    assert late["unload"] == {"fonts_before": 29, "fonts_after": 29}
    for load in loads[1:]:
        assert load["prose_is_a_new_entry"] is True, load
        assert load["kept_still_in_the_atlas"] is True, load


def test_an_open_view_draws_the_frame_after_as_it_did_the_frame_before(
    late: dict[str, Any],
) -> None:
    frames = {row["frame"]: row for row in late["frames"]}
    assert len(frames) == 20
    unavailable = sorted(frame for frame, row in frames.items() if "unavailable" in row)
    # Switched off at 8 and back at 9; unloaded at 15 and loaded at 17.
    assert unavailable == [8, 15, 16], unavailable
    drawn = {frame: row for frame, row in frames.items() if frame not in unavailable}
    assert {row["vertices"] for row in drawn.values()} == {frames[0]["vertices"]}
    assert frames[0]["vertices"] > 100, "nothing much was drawn in the first place"
    remade = sorted(frame for frame, row in drawn.items() if frame and not row["same_document"])
    assert remade == [5, 9, 12, 17], "the view makes its document again after each load, only"


def test_a_native_line_in_a_typeset_face_is_the_texts_size_at_its_line_height_not_its_em(
    late: dict[str, Any],
) -> None:
    """
    pptmstr, P14: `test_a_native_line_in_a_typeset_face_is_the_texts_size`
    ("a header drawn with `font()` beside typeset text has to scale with it").
    The font pushed at a size IS that size; which size is the text's is what
    `font`'s docstring says with these numbers, and they are held here so
    that it cannot drift: the em times the file's line height, not the em.
    """
    code, prose, larger = late["sizes"]
    assert [(row["face"], row["em"], row["ratio"]) for row in late["sizes"]] == [
        ("CODE", 16.0, 1.049),
        ("PROSE", 16.0, 1.1719),
        ("CODE", 21.0, 1.049),
    ]
    for row in late["sizes"]:
        assert row["at_the_em"]["pushed"] == row["em"], "a pushed size is not the size"
        # Dear ImGui makes a pushed size a whole pixel: 16.78 is 17, 18.75 is 19.
        assert row["at_the_line"]["pushed"] == round(row["em"] * row["ratio"])
        # The same height of ink as the typeset text at the line height...
        assert row["at_the_line"]["ink"][1] == row["typeset_ink"][1], row
        # ...and smaller than it at the em.
        assert row["at_the_em"]["ink"][1] < row["typeset_ink"][1], row
    assert code["typeset_ink"] == code["at_the_line"]["ink"] == [104.0, 14.0]
    assert prose["typeset_ink"] == prose["at_the_line"]["ink"] == [116.0, 15.0]
    assert (code["at_the_em"]["ink"][1], prose["at_the_em"]["ink"][1]) == (11.0, 13.0)
    # The same advances only where the file's advance is a whole pixel.
    assert code["typeset_laid"] == code["at_the_line"]["wide"] == 104.0
    assert (larger["typeset_laid"], larger["at_the_line"]["wide"]) == (136.5, 143.0)


def test_a_native_line_is_set_in_the_roles_new_file_after_a_later_load(
    late: dict[str, Any],
) -> None:
    rows = [row for row in late["frames"] if "native_prose" in row]
    assert len(rows) == 17
    before = {row["native_prose"] for row in rows if row["frame"] < 12}
    after = {row["native_prose"] for row in rows if row["frame"] >= 12}
    assert len(before) == 1 and len(after) == 1 and before != after

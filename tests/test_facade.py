r"""
The import surface of `advtext`: what is promised, and that importing it is free.

`advtext/__init__.py` used to export nothing and say so. It now resolves a small
set of names lazily, and three properties of that are worth a test each because
each is the kind that rots quietly:

- **The three lists agree.** The names are written in `__all__`, in `_HOMES`
  (name to defining module) and in the `TYPE_CHECKING` imports a type checker
  reads. A name in one and not another is promised and unresolvable, or
  resolvable and unpromised, or resolvable and invisible to mypy.
- **Every name is the object its module defines**, not a copy or a wrapper.
- **Importing costs nothing.** `import advtext` loads no other module of the
  package, and resolving the *whole* surface still loads neither ImGui nor
  fontTools. Checked in a fresh interpreter, because this one has had both in
  `sys.modules` since the first test that drew or measured anything.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import advtext

REPO = Path(__file__).resolve().parent.parent


def _fresh(source: str) -> list[str]:
    """
    Run a snippet in a new interpreter from the repository root; return its stdout lines.
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def _type_checking_imports() -> dict[str, str]:
    """
    Name to module for every import under `if TYPE_CHECKING:` in the package's `__init__`.
    """
    tree = ast.parse((REPO / "advtext" / "__init__.py").read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.If) and getattr(node.test, "id", "") == "TYPE_CHECKING":
            for statement in node.body:
                assert isinstance(statement, ast.ImportFrom) and statement.module
                for alias in statement.names:
                    found[alias.asname or alias.name] = statement.module
    return found


def test_the_three_lists_of_names_are_one_list() -> None:
    """
    `__all__`, `_HOMES` and the `TYPE_CHECKING` imports name the same things from the same places.

    The last comparison is on the *modules* as well as the names: a type checker
    told `Theme` comes from one module while the runtime fetches it from another
    would be checking a different class from the one that runs.
    """
    assert len(advtext.__all__) == len(set(advtext.__all__)), "a name is listed twice"
    assert set(advtext.__all__) == set(advtext._HOMES)
    assert _type_checking_imports() == advtext._HOMES
    assert len(advtext.__all__) >= 30, "the surface has shrunk to almost nothing"


@pytest.mark.parametrize("name", advtext.__all__)
def test_every_name_is_the_object_its_own_module_defines(name: str) -> None:
    """
    `advtext.X is advtext.<home>.X`, for every X promised.
    """
    home = importlib.import_module(advtext._HOMES[name])
    assert getattr(advtext, name) is getattr(home, name)
    assert name in dir(advtext)


def test_the_surface_covers_the_pipeline_the_plan_names() -> None:
    """
    Parse, block constructors, theme, compose, ship, draw and font setup are all there.

    `docs/adoption-plan.md` phase 1 lists what the facade must cover. Spelled out
    so that removing one of them is a failing test with the plan's name on it
    rather than a quiet edit to a list.
    """
    promised = set(advtext.__all__)
    assert {"build_document", "text_block", "code_block"} <= promised
    assert {"Theme", "Faces", "Align"} <= promised
    assert {"compose", "compose_blocks", "ship", "draw"} <= promised
    assert {"load_faces", "register_font", "em_size_for_pixel_height"} <= promised


def test_the_surface_covers_what_the_second_build_added() -> None:
    """
    A diff and its view, a widget hosted in a document, mathematics in text, find.

    `.concerns/lead--demo-tasks.md` ("Facade") put these names here in one task
    at the end of that build. Spelled out by group for the same reason as the
    test above. The last line is the other half of the decision: two names a
    reader would look for and that are deliberately absent, because
    `advtext.parse` would read as the markdown parser and is the formula one.
    """
    promised = set(advtext.__all__)
    assert {"Diff", "FileDiff", "Hunk", "DiffRow", "RowKind", "FileStatus"} <= promised
    assert {"UnifiedDiffStream", "DiffApplyError", "ContextUnavailable"} <= promised
    assert {"DiffView", "DiffLayout", "SyntaxColour", "language_for"} <= promised
    assert {"DiffPalette", "DEFAULT_DIFF_PALETTE", "DARK_DIFF_PALETTE"} <= promised
    assert {"HostFor", "Hosted", "HostBlock", "DiffFences", "HostedDiff"} <= promised
    assert {"markdown_math", "MathBuilder", "MathRefused"} <= promised
    assert {"formula_spans", "FormulaSpan", "typeset", "Typeset"} <= promised
    assert {"Refusal", "RefusalKind", "supported_commands"} <= promised
    assert {"FindIndex", "TextMatch", "LayoutStats"} <= promised
    assert {"ColumnLimits", "table_column_limits"} <= promised
    assert not {"parse", "set_formula"} & promised


def test_a_diff_and_a_formula_are_made_through_the_surface() -> None:
    """
    The new names do what they are for, reached only from the package root.

    A fresh interpreter: a diff from two texts, one from a list of edits, one
    read from unified text, then a document with a formula in it. Making the
    diffs and resolving the *view's* class -- the name most likely to drag
    ImGui in -- loads neither ImGui nor fontTools; that is the fifth line. The
    document is built after it, because measuring a face finds the bundled
    fonts by importing `imgui_bundle` (`advtext.fontlib`), as it always has.
    """
    lines = _fresh(r"""
        import sys
        from advtext import (
            Diff, DiffLayout, DiffView, RowKind, Theme, build_document,
            fontlib_metrics, formula_spans, markdown_math,
        )

        diff = Diff.from_texts("a\nb\n", "a\nc\n", "f.txt")
        kinds = [row.kind for _file, _hunk, row in diff.rows()]
        print(diff.added, diff.removed, kinds == [RowKind.CONTEXT, RowKind.REMOVE, RowKind.ADD])

        edits = Diff.from_edits([("foo", "bar", "edit 1"), ("x", "y", "edit 2")])
        print([(file.label, file.added, file.removed) for file in edits.files])
        print(Diff.from_unified(diff.to_unified()).to_unified() == diff.to_unified())
        print(DiffView.__name__, DiffLayout.UNIFIED.name)
        math = markdown_math()
        heavy = ("imgui_bundle", "fontTools")
        print(any(name.split(".")[0] in heavy for name in sys.modules))

        document = build_document(
            "Euler: $e^{i\\pi} = -1$ and $\\nosuch$.", Theme.build(), fontlib_metrics, math=math
        )
        spans = formula_spans(document.blocks[0])
        print([(span.text, bool(span.refusal)) for span in spans])
        """)
    assert lines == [
        "1 1 True",
        "[('edit 1', 1, 1), ('edit 2', 1, 1)]",
        "True",
        "DiffView UNIFIED",
        "False",
        r"[('$e^{i\\pi} = -1$', False), ('$\\nosuch$', True)]",
    ]


def test_a_name_that_is_not_promised_is_an_attribute_error() -> None:
    """
    The lazy lookup does not turn a typo into something else.

    `hasattr` relies on `AttributeError` specifically, and so does
    `from advtext import nosuch`, which must stay an `ImportError`.
    """
    with pytest.raises(AttributeError, match="no attribute 'no_such_name'"):
        advtext.no_such_name  # noqa: B018 - the access is the test
    assert not hasattr(advtext, "DocumentView"), "a name outside the surface resolved"
    with pytest.raises(ImportError):
        exec("from advtext import no_such_name", {})


def test_importing_the_package_imports_nothing_else_of_it() -> None:
    """
    `import advtext` runs one file.

    Not the markdown parser, not the style module, not a font: a host that
    imports the package to reach one submodule pays for that submodule only.
    """
    lines = _fresh("""
        import sys
        before = set(sys.modules)
        import advtext
        loaded = sorted(set(sys.modules) - before)
        print([name for name in loaded if name.startswith("advtext")])
        heavy = ("imgui_bundle", "fontTools", "markdown_it")
        print(any(name.split(".")[0] in heavy for name in loaded))
        """)
    assert lines == ["['advtext']", "False"]


def test_resolving_the_whole_surface_imports_neither_imgui_nor_fonttools() -> None:
    """
    The plan's sentence, at its strongest: not only `import advtext` but every name in it.

    After touching all of `__all__` and after `from advtext import *`, neither
    library is loaded. The second line of output is the control, so the first is
    not passing because the check cannot see the modules: the same interpreter,
    one measured document later, has loaded fontTools.
    """
    lines = _fresh("""
        import sys

        def loaded(prefix):
            return any(name.split(".")[0] == prefix for name in sys.modules)

        import advtext
        for name in advtext.__all__:
            getattr(advtext, name)
        from advtext import *
        print(loaded("imgui_bundle"), loaded("fontTools"))

        theme = Theme.build()
        document = build_document("Some *words*.", theme, fontlib_metrics)
        print(loaded("fontTools"), len(document.blocks))
        """)
    assert lines == ["False False", "True 1"]


def test_a_submodule_is_still_reached_by_its_own_path() -> None:
    """
    The surface is in front of the modules, not instead of them.

    Everything not promised is imported from where it is defined, as before, and
    a submodule that shares no name with the surface is unaffected by the lazy
    lookup -- `advtext.fontlib` is a module, found by the import system, and
    never goes through `__getattr__`.
    """
    lines = _fresh("""
        import advtext
        import advtext.fontlib
        from advtext.ui import Viewport
        print(type(advtext.fontlib).__name__, Viewport.__module__)
        """)
    assert lines == ["module advtext.ui"]

r"""
The import surface of `advtext`: what is promised, and that importing it is free.

`advtext/__init__.py` resolves a small set of names lazily. Five properties of
that are worth a test each because each is the kind that rots quietly:

- **The surface is this list.** `SURFACE` below writes it out, in the three
  groups the facade keeps apart, and its count. A name added or removed
  without this file changing is a failure, in either direction.
- **The three lists agree.** The names are written in `__all__`, in `_HOMES`
  (name to defining module) and in the `TYPE_CHECKING` imports a type checker
  reads. A name in one and not another is promised and unresolvable, or
  resolvable and unpromised, or resolvable and invisible to mypy.
- **Every name is the object its module defines**, not a copy or a wrapper.
- **A name whose module was deleted is gone.** Tranche 5 of the swap deleted
  the Python views, the draw backend and the LaTeX subset; their names are
  not aliased to something similar, and asking for one is an
  `AttributeError` like any other name the package does not have.
- **Importing costs nothing.** `import advtext` loads no other module of the
  package; resolving the typeset layer's names loads none of the reference
  core; resolving the *whole* surface loads none of ImGui, fontTools and
  imtypeset. Checked in a fresh interpreter, because this one has had them
  in `sys.modules` since the first test that drew or measured anything.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

import advtext

REPO = Path(__file__).resolve().parent.parent

TYPESET_LAYER = {
    "advtext.typesetter": ("load_fonts", "ready", "reason"),
    "advtext.typeset_markdown": (
        "parse_markdown",
        "MarkdownDocument",
        "MarkdownStream",
        "MarkdownConverter",
    ),
    "advtext.markdown_rules": ("BlockSource", "SourceSpan"),
    "advtext.description": ("Description", "BlockDescription"),
    "advtext.typeset_find": ("Finder", "FindIndex", "Match"),
    "advtext.theme": ("Theme", "Faces", "Align", "Spacing", "BlockKind", "Emphasis"),
    "advtext.primitives": ("Face", "Scaled", "sp_from_px", "px_from_sp"),
    "advtext.ui.palette": (
        "Palette",
        "DEFAULT_PALETTE",
        "DARK_PALETTE",
        "DrawStats",
        "DiffPalette",
        "DEFAULT_DIFF_PALETTE",
        "DARK_DIFF_PALETTE",
    ),
    "advtext.ui.typeset_view": (
        "TypesetView",
        "TypesetUnavailable",
        "SetLine",
        "HostFor",
        "Hosted",
    ),
    "advtext.ui.typeset_stream_view": ("TypesetStreamView",),
    "advtext.diff": (
        "Diff",
        "FileDiff",
        "Hunk",
        "DiffRow",
        "RowKind",
        "FileStatus",
        "UnifiedDiffStream",
        "DiffApplyError",
        "ContextUnavailable",
    ),
    "advtext.ui.typeset_diff_view": (
        "TypesetDiffView",
        "DiffLayout",
        "SyntaxColour",
        "language_for",
    ),
    "advtext.ui.typeset_hosts": ("TypesetDiffFences", "HostedDiff"),
}
"""
What a host draws with, by the module each name is fetched from: 52 names.
None of these modules is reference core, and none imports it.
"""

FONT_FILES = {
    "advtext.fontlib": (
        "register_font",
        "unregister_font",
        "registered_fonts",
        "em_size_for_pixel_height",
    ),
    "advtext.ui.fonts": ("load_faces", "LoadedFaces", "TEXT_FACES", "ALL_FACES"),
}
"""
Where the font files are and the Python atlas loader: 8 names. Both modules
are kept by a decision (`.concerns/lead--tranche-5.md`, 5 and 6) and not
because the typeset layer is built on them.
"""

REFERENCE_CORE = {
    "advtext.markdown": (
        "build_document",
        "text_block",
        "code_block",
        "Document",
        "Block",
        "TextBlock",
        "CodeBlock",
        "RuleBlock",
        "TableBlock",
        "MathBuilder",
        "MathRefused",
        "FormulaSpan",
        "formula_spans",
    ),
    "advtext.style": ("MetricsResolver", "fontlib_metrics", "char_measure"),
    "advtext.ui": (
        "compose",
        "compose_blocks",
        "ComposeParams",
        "PROSE_BREAKING_TOTAL_FIT_RAGGED",
        "with_columns",
        "table_columns",
        "SizedTable",
        "ColumnLimits",
        "table_column_limits",
        "HostBlock",
    ),
    "advtext.shipout": ("ship", "Point", "DrawCmd"),
}
"""
The Python layout core's names, on the surface because their modules are in
the tree for the SVG litmus renderer: 29 names.
"""

SURFACE = {
    name: home
    for group in (TYPESET_LAYER, FONT_FILES, REFERENCE_CORE)
    for home, names in group.items()
    for name in names
}

REMOVED = (
    # advtext.stream
    "StreamDocument",
    "CommitPolicy",
    "live_theme",
    # advtext.mathtext
    "markdown_math",
    "typeset",
    "Typeset",
    "Refusal",
    "RefusalKind",
    "supported_commands",
    # advtext.backends.imgui_draw
    "draw",
    # advtext.ui.bare_view, stream_view, units, diff_view
    "BareView",
    "StreamView",
    "LayoutStats",
    "DiffView",
    "DiffFences",
    # advtext.spans
    "ColourSpan",
    "code_position",
    "colour_text",
    "find_spans",
    "material_text",
    "TextMatch",
)
"""
The 21 names that were on the surface until tranche 5 and are on it under no
form: the module that defined each was deleted.
"""

REPLACED = {
    "HostFor": "advtext.ui.typeset_view",
    "SetLine": "advtext.ui.typeset_view",
    "DiffLayout": "advtext.ui.typeset_diff_view",
    "SyntaxColour": "advtext.ui.typeset_diff_view",
    "language_for": "advtext.ui.typeset_diff_view",
    "HostedDiff": "advtext.ui.typeset_hosts",
    "FindIndex": "advtext.typeset_find",
    "Hosted": "advtext.ui.typeset_view",
}
"""
Eight names that were on the surface before and are on it now as the typeset
layer's object of that name. For the first seven the old object's module was
deleted (`bare_view`, `diff_view`, `spans`). `Hosted` is the exception:
`advtext.ui.Hosted`, the protocol of the deleted `BareView`'s widgets, still
exists for the reference compositor, and the surface's `Hosted` is no longer
it.
"""


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


def test_the_surface_is_this_list_and_this_many() -> None:
    """
    89 names: 52 of the typeset layer, 8 for font files, 29 of the reference core.

    It was 94 until tranche 5. 28 of those named a deleted module; 21 are gone
    by name (`REMOVED`) and 7 are back as the typeset layer's object of the
    same name (`REPLACED`), with 16 names that are new.
    """
    counts = [
        sum(len(names) for names in group.values())
        for group in (TYPESET_LAYER, FONT_FILES, REFERENCE_CORE)
    ]
    assert counts == [52, 8, 29]
    assert len(SURFACE) == 89, "a name is in two groups"
    assert advtext._HOMES == SURFACE
    assert sorted(advtext.__all__) == sorted(SURFACE)
    assert not set(REMOVED) & set(SURFACE)
    assert len(REMOVED) == 21 and len(set(REMOVED)) == 21
    for name, home in REPLACED.items():
        assert SURFACE[name] == home


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


@pytest.mark.parametrize("name", sorted(SURFACE))
def test_every_name_is_the_object_its_own_module_defines(name: str) -> None:
    """
    `advtext.X is advtext.<home>.X`, for every X promised, and `<home>` is where X is defined.

    The second half is for classes and functions, which know their module
    (`Scaled` is `int` and knows another). The compositor's names are the
    stated exception: their home is the package `advtext.ui`, which hands out
    `advtext.ui.composition`'s objects.
    """
    home = SURFACE[name]
    value = getattr(advtext, name)
    assert value is getattr(importlib.import_module(home), name)
    assert name in dir(advtext)
    if isinstance(value, type | types.FunctionType) and value is not int:
        defined = "advtext.ui.composition" if home == "advtext.ui" else home
        assert value.__module__ == defined


@pytest.mark.parametrize("name", REMOVED)
def test_a_name_whose_module_was_deleted_is_not_there(name: str) -> None:
    """
    `AttributeError`, as for any name the package lacks, so `hasattr` answers False.

    Between the deletion and this rule a dead row raised `ModuleNotFoundError`
    out of `hasattr(advtext, "BareView")`, which is not an answer to `hasattr`.
    """
    assert not hasattr(advtext, name)
    with pytest.raises(AttributeError, match=f"no attribute {name!r}"):
        getattr(advtext, name)
    with pytest.raises(ImportError):
        exec(f"from advtext import {name}", {})
    assert name not in dir(advtext)


def test_no_home_is_a_module_that_is_not_in_the_tree() -> None:
    """
    The rule itself: a name is on the surface only while its defining module exists.

    Read from the file system and not by importing, so a module deleted
    tomorrow fails here by name and not as 1 of 89 parametrised cases.
    """
    for home in sorted(set(advtext._HOMES.values())):
        path = REPO / home.replace(".", "/")
        assert path.with_suffix(".py").is_file() or (path / "__init__.py").is_file(), home


def test_the_surface_covers_what_a_host_of_the_typeset_layer_needs() -> None:
    """
    The library's gate, markdown, a stream, find, the looks, the three views, a diff.

    Spelled out by group so that removing one is a failing test with a reason
    on it rather than a quiet edit to a list. The last line is the names a
    reader would look for that are deliberately absent: the typesetter's
    `module` and `unload` (a host takes the module `advtext.typesetter` for
    those; `advtext.module` would say nothing), and `typeset`, which was the
    deleted formula function and must not come back meaning something else.
    """
    promised = set(advtext.__all__)
    assert {"load_fonts", "ready", "reason"} <= promised
    assert {"parse_markdown", "MarkdownDocument", "MarkdownStream"} <= promised
    assert {"MarkdownConverter", "Description", "BlockDescription"} <= promised
    assert {"Finder", "FindIndex", "Match"} <= promised
    assert {"Theme", "Faces", "Face", "Align", "Palette", "DARK_PALETTE"} <= promised
    assert {"TypesetView", "TypesetStreamView", "TypesetDiffView"} <= promised
    assert {"TypesetUnavailable", "HostFor", "Hosted", "TypesetDiffFences"} <= promised
    assert {"Diff", "FileDiff", "Hunk", "DiffRow", "RowKind", "FileStatus"} <= promised
    assert {"UnifiedDiffStream", "DiffApplyError", "ContextUnavailable"} <= promised
    assert {"DiffLayout", "SyntaxColour", "language_for"} <= promised
    assert {"DiffPalette", "DEFAULT_DIFF_PALETTE", "DARK_DIFF_PALETTE"} <= promised
    assert not {"module", "unload", "typeset", "parse"} & promised


def test_a_diff_a_document_and_a_search_are_made_through_the_surface() -> None:
    """
    The names do what they are for, reached only from the package root, with no library.

    A fresh interpreter: a diff from two texts, one from a list of edits, one
    read from unified text; markdown parsed, described and searched; the three
    view classes resolved. None of it loads ImGui, fontTools or imtypeset, or
    any module of the reference core: the last two lines.
    """
    lines = _fresh(r"""
        import sys
        from advtext import (
            Diff, DiffLayout, FindIndex, Finder, MarkdownConverter, RowKind, Theme,
            TypesetDiffView, TypesetStreamView, TypesetView, parse_markdown, ready,
        )

        diff = Diff.from_texts("a\nb\n", "a\nc\n", "f.txt")
        kinds = [row.kind for _file, _hunk, row in diff.rows()]
        print(diff.added, diff.removed, kinds == [RowKind.CONTEXT, RowKind.REMOVE, RowKind.ADD])

        edits = Diff.from_edits([("foo", "bar", "edit 1"), ("x", "y", "edit 2")])
        print([(file.label, file.added, file.removed) for file in edits.files])
        print(Diff.from_unified(diff.to_unified()).to_unified() == diff.to_unified())
        print(TypesetDiffView.__name__, DiffLayout.UNIFIED.name)
        print(TypesetView.__name__, issubclass(TypesetStreamView, TypesetView), ready())

        theme = Theme.build()
        parsed = parse_markdown("# A head\n\nSome *words*, and words again.\n", theme)
        described = MarkdownConverter(theme).describe(parsed.blocks)
        finder = Finder(FindIndex.of(described.blocks))
        print(len(parsed.blocks), [(m[0], m[1]) for m in finder.search("words")])

        heavy = ("imgui_bundle", "fontTools", "imtypeset")
        print(any(name.split(".")[0] in heavy for name in sys.modules))
        core = ("units", "fontmetrics", "nodes", "pack", "badness", "style", "markdown",
                "shipout", "selection", "linebreak", "fontlib", "math", "backends")
        ours = [name.split(".") for name in sys.modules if name.startswith("advtext.")]
        print(sorted(".".join(parts) for parts in ours if parts[1] in core))
        """)
    assert lines == [
        "1 1 True",
        "[('edit 1', 1, 1), ('edit 2', 1, 1)]",
        "True",
        "TypesetDiffView UNIFIED",
        "TypesetView True False",
        "2 [(1, 5), (1, 16)]",
        "False",
        "[]",
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

    Not the markdown parser, not the theme, not a font: a host that imports
    the package to reach one submodule pays for that submodule only.
    """
    lines = _fresh("""
        import sys
        before = set(sys.modules)
        import advtext
        loaded = sorted(set(sys.modules) - before)
        print([name for name in loaded if name.startswith("advtext")])
        heavy = ("imgui_bundle", "fontTools", "markdown_it", "imtypeset")
        print(any(name.split(".")[0] in heavy for name in loaded))
        """)
    assert lines == ["['advtext']", "False"]


def test_the_typeset_layers_names_are_reached_without_the_reference_core() -> None:
    """
    `from advtext import <all 52>` loads the modules that define them and one leaf.

    The whole of what a host of the typeset layer can take from the facade,
    in one statement, and then a theme built: what is in `sys.modules` of
    advtext is the thirteen homes, the two packages, the selection counter
    the views share (`advtext.ui.ownership`), and nothing else. No
    `advtext.units`, no `advtext.fontmetrics` (the floor until
    `advtext.primitives` existed), no node, no packer.

    Before the homes were the defining modules, `Theme` came through
    `advtext.style` and `Palette` through the draw backend, and a host that
    drew through imtypeset loaded eight modules of the old core for two names.
    """
    names = ", ".join(name for group in TYPESET_LAYER.values() for name in group)
    lines = _fresh(f"""
        import sys
        from advtext import {names}
        Theme.build()
        print(sorted(name for name in sys.modules if name.split(".")[0] == "advtext"))
        """)
    expected = {"advtext", "advtext.ui", "advtext.ui.ownership", *TYPESET_LAYER}
    assert lines == [str(sorted(expected))]


def test_a_replaced_name_is_the_typeset_layers_and_not_an_alias_of_the_old() -> None:
    """
    `Hosted` is the view's protocol; `advtext.ui.Hosted` is another class and still there.
    """
    from advtext.ui import typeset_hosts, typeset_view

    assert advtext.Hosted is typeset_view.Hosted is typeset_hosts.Hosted
    assert advtext.HostFor is typeset_view.HostFor is typeset_hosts.HostFor
    old = importlib.import_module("advtext.ui").Hosted
    assert old is not advtext.Hosted and old.__module__ == "advtext.ui"


def test_resolving_the_whole_surface_imports_no_imgui_no_fonttools_and_no_library() -> None:
    """
    Not only `import advtext` but every name in it, the reference core's included.

    After touching all of `__all__` and after `from advtext import *`, none of
    the three is loaded. The second line of output is the control, so the
    first is not passing because the check cannot see the modules: the same
    interpreter, one measured document later, has loaded fontTools.
    """
    lines = _fresh("""
        import sys

        def loaded(prefix):
            return any(name.split(".")[0] == prefix for name in sys.modules)

        import advtext
        for name in advtext.__all__:
            getattr(advtext, name)
        from advtext import *
        print(loaded("imgui_bundle"), loaded("fontTools"), loaded("imtypeset"))

        theme = Theme.build()
        document = build_document("Some *words*.", theme, fontlib_metrics)
        print(loaded("fontTools"), len(document.blocks))
        """)
    assert lines == ["False False False", "True 1"]


def test_a_submodule_is_still_reached_by_its_own_path() -> None:
    """
    The surface is in front of the modules, not instead of them.

    Everything not promised is imported from where it is defined, as before, and
    a submodule that shares no name with the surface is unaffected by the lazy
    lookup -- `advtext.fontlib` is a module, found by the import system, and
    never goes through `__getattr__`. `advtext.typesetter` is the one the
    examples take this way.
    """
    lines = _fresh("""
        import advtext
        import advtext.fontlib
        from advtext import typesetter
        from advtext.ui import Viewport
        print(type(advtext.fontlib).__name__, Viewport.__module__, typesetter.__name__)
        print(advtext.ready is typesetter.ready, advtext.load_fonts is typesetter.load_fonts)
        """)
    assert lines == ["module advtext.ui advtext.typesetter", "True True"]


def _imports_of_advtext(path: Path) -> list[tuple[int, str, str]]:
    """
    `(line, module, name)` for every `from advtext... import name` in a file, wherever it is.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module == "advtext" or module.startswith("advtext."):
                found.extend((node.lineno, module, alias.name) for alias in node.names)
    return found


def test_every_import_of_advtext_in_the_tree_names_something_that_exists() -> None:
    """
    Every `from advtext... import name` in the package, the examples and the
    scripts: the module is there and has the name (or the name is a submodule).

    At module level, inside a function, and under `TYPE_CHECKING`. The last
    is why this is a test: mypy runs with `ignore_missing_imports`, so after
    the old views were deleted the facade's `TYPE_CHECKING` block imported
    from eight modules that did not exist and the type check stayed green.
    A lazy import in a function body is likewise found by nothing until it runs.
    """
    files = [
        *sorted((REPO / "advtext").rglob("*.py")),
        *sorted((REPO / "examples").glob("*.py")),
        *sorted((REPO / "scripts").glob("*.py")),
    ]
    assert len(files) > 50
    wrong = []
    for path in files:
        for line, module, name in _imports_of_advtext(path):
            where = f"{path.relative_to(REPO)}:{line}: from {module} import {name}"
            try:
                home = importlib.import_module(module)
            except ImportError:
                wrong.append(where + " (no such module)")
                continue
            if not hasattr(home, name):
                try:
                    importlib.import_module(f"{module}.{name}")
                except ImportError:
                    wrong.append(where)
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("example", sorted(path.name for path in (REPO / "examples").glob("*.py")))
def test_an_example_imports_from_the_package_root_and_nowhere_else_in_it(example: str) -> None:
    """
    Names of `__all__`, and the module `typesetter`. All four examples, by source.
    """
    found = _imports_of_advtext(REPO / "examples" / example)
    assert found, "the example imports nothing of advtext"
    assert {module for _line, module, _name in found} == {"advtext"}
    names = {name for _line, _module, name in found}
    assert names - {"typesetter"} <= set(advtext.__all__), sorted(names - set(advtext.__all__))
    assert not names & set(REMOVED)

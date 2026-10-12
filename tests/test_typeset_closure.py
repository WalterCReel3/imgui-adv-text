r"""
What the typeset layer loads of the reference core, as sets this file holds.

imscribe draws through imtypeset. The Python layout core it used to draw with
(line breaking, packing, ship-out, the selection model, the ImGui draw
backend and the views built on them) was deleted in tranche 5, **except what
the SVG litmus renderer needs**: `imscribe/backends/svg.py`,
`scripts/render_litmus.py`, and the modules they import. That
remainder is called the reference core here. `SVG_CLOSURE` is its list, as
`.concerns/T5-B1--svg-closure.md` measured it, and a test below measures it
again, so the list is the chain's and not a memory of it.

**The claim: no module of the typeset layer, the app, the pages or the
examples imports the reference core. None of it, at import, and none when a
theme is built.** `EXPECTED` states, for each module, exactly which
reference-core modules a fresh interpreter has loaded after importing it and
nothing else, and every entry is the empty set. Exactly, in both directions:
a new import fails here, and a removal did too, which is how the swap showed
in this file's diffs as a number going down (twenty-one modules, eighteen,
six, two, none) rather than as a sentence saying it would.

Until T5-B2 there was a floor of two: `imscribe.units` (arithmetic) and
`imscribe.fontmetrics` (the `Face` enum), which `imscribe.theme` imported, and
`Theme.build` loaded three more (`THEME_BUILD`) because a block style held
its leading as the core's `InterlineSkip`. The lengths and `Face` are
defined in `imscribe.primitives` now, which imports nothing, and the two old
modules import them back (the identities are held below); a style's leading
is a number.

Six modules are in the chain's closure and are NOT reference core, because
the typeset layer is built on them too (`SHARED`): the package `imscribe`
itself, the package `imscribe.ui` (which defines `Viewport` and `Hosted` and
is the door to composition only when composition is asked for),
`imscribe.markdown_rules` (the parser's rules, which import nothing of
imscribe), `imscribe.theme`, `imscribe.primitives`, and since 2026-10-12
`imscribe.fontfiles` (which file backs which role: a table that opens no
font, which `imscribe.fontlib` imports back).

**Both ways of writing the import are measured**, `import a.b.c` and `from a.b
import c`. They are not the same question to a package: for the second,
Python first asks `a.b` for an attribute `c` and imports the submodule only
if that fails. `imscribe.ui` answers missing attributes itself (it forwards
them to `imscribe.ui.composition`), and until 2026-10-11 it answered *that*
question by importing the compositor, so `from imscribe.ui import typeset_view`
loaded the line breaker while this file, measuring only the first form, stayed
green.

Two limits, so the claim is not read as more than it is:

- **`EXPECTED` is import time only.** A function that imports when called
  is not seen by it. Until 2026-10-12 five did. **Two are left, and one of
  them only while the library has no fonts**; each is named here and
  measured below, and there is no third that a page's constructor or a drawn
  frame reaches:
  - **Sizing to a pixel height while `imscribe.typesetter.ready()` is
    false** (no library; or the library imported and `load_fonts()` not yet
    succeeded in the current Dear ImGui context). `Theme.at_pixel_height`
    with no resolver and `imscribe.ui.pages.face_metrics` then ask
    `imscribe.style.fontlib_metrics` to measure a face from its font file:
    `MEASURING`, which is `imscribe.style`, `imscribe.fontlib` and the five
    modules `imscribe.style` imports. `imscribe.ui.typeset_diff_view.code_size`
    given a pixel height, and `imscribe.em_size_for_pixel_height`, then ask
    `imscribe.fontlib` for the em: `OLD_READER`, which is `imscribe.fontlib`
    and the `imscribe.fontmetrics` it imports. It is kept because imscribe's
    app and pages size their themes before there is a window, and a host
    may have no library (`imscribe.typeset_metrics` has the argument and the
    measurement of who would break).
    **With `ready()` true the same four calls load NOTHING of the reference
    core and no fontTools**: imtypeset answers (`font_metrics`,
    `glyph_advance`; `test_with_the_library_ready_nothing_reaches_the_reference_core`).
    Nor does `imscribe.typesetter.load_fonts`, in either state: it finds the
    files in `imscribe.fontfiles`.
  - `BlockStyle.interline` builds the reference core's `InterlineSkip`
    through `imscribe.style` (`INTERLINE`). Only the reference compositor
    reads it; no module of the typeset layer does, which a test below holds
    by reading their source.
- **`imscribe.ui.fonts` is not measured by `EXPECTED`** and is the one module
  of imscribe outside both lists. It is the old Python atlas loader, it
  imports `imscribe.fontlib` at the top, and `imscribe.ui.app.load_fonts`
  imports it when the app's font callback runs without the library, for one
  UI font (decision 6). T5-B1 left it for that.
- **`OLD_CORE` is the older, narrower list** that other test files import
  (`tests/test_page_*.py`): the reference core without `imscribe.markdown`,
  `imscribe.style` and the package `imscribe.backends`. It is kept under that
  name with that meaning so that their exact sets go on meaning what they
  did; `REFERENCE_CORE` is the whole of it and is what this file measures.

The second half of the file is about the moves themselves: replacing a name
on `imscribe.ui` still reaches the code that reads it, and the theme's names
are one object under `imscribe.style` and `imscribe.theme`. (The halves about
the draw backend's palette path and `BareView`'s ownership path went with
those modules.)
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SVG_CLOSURE = frozenset(
    {
        "imscribe",
        "imscribe.backends",
        "imscribe.backends.svg",
        "imscribe.badness",
        "imscribe.fontfiles",
        "imscribe.fontlib",
        "imscribe.fontmetrics",
        "imscribe.linebreak",
        "imscribe.markdown",
        "imscribe.markdown_rules",
        "imscribe.math",
        "imscribe.math.atoms",
        "imscribe.math.mlist",
        "imscribe.nodes",
        "imscribe.pack",
        "imscribe.primitives",
        "imscribe.selection",
        "imscribe.shipout",
        "imscribe.style",
        "imscribe.theme",
        "imscribe.ui",
        "imscribe.ui.composition",
        "imscribe.units",
    }
)
"""
Every `imscribe` module the SVG litmus chain loads: `imscribe.backends.svg`, and
what `scripts/render_litmus.py` imports to feed it. Measured before the
deletion (`.concerns/T5-B1--svg-closure.md`: 21 names) and held by
`test_the_reference_core_is_what_the_litmus_chain_loads`. `imscribe.primitives`
is the twenty-second, added by T5-B2: `imscribe.units` and
`imscribe.fontmetrics` import their lengths and `Face` from it.
`imscribe.fontfiles` is the twenty-third (2026-10-12): `imscribe.fontlib`
imports the table of font files from it.
"""

SHARED = frozenset(
    {
        "imscribe",
        "imscribe.ui",
        "imscribe.markdown_rules",
        "imscribe.theme",
        "imscribe.primitives",
        "imscribe.fontfiles",
    }
)
"""
In the chain's closure and the typeset layer's own as well: not reference core.
"""

REFERENCE_CORE = SVG_CLOSURE - SHARED
"""
What is left of the old layout core, kept for the litmus renderer and for
nothing else: what no typeset module may load.
"""

OLD_CORE = REFERENCE_CORE - {"imscribe.markdown", "imscribe.style", "imscribe.backends"}
"""
The list this file had before tranche 5, less the modules deleted then, for
the test files that import it by this name: the reference core without the
two modules that "stand on the core" and without the backends package. Until
tranche 5 it also named `imscribe.mathtext`, `imscribe.spans`,
`imscribe.columns`, `imscribe.blocklayout`, `imscribe.backends.imgui_draw` and
`imscribe.ui.units`, `bare_view`, `stream_view`, `document_view`, `diff_view`,
`specimen`, `formulas`: all deleted.
"""

NOTHING: frozenset[str] = frozenset()
"""
What `imscribe.typesetter` and the description types load of the reference
core at import since 2026-10-11: none of it. It was six modules (`units,
badness, nodes, pack, shipout, fontmetrics`, through `imscribe.markdown`,
`imscribe.style` and the typesetter's own walk over node material). That walk
(`Converter`) was deleted in tranche 5.
"""

THEME: frozenset[str] = frozenset()
"""
What `imscribe.theme` loads of the reference core at import, and so the least
anything that names a `Theme` can load: nothing, since T5-B2. It was
`imscribe.units` and `imscribe.fontmetrics`. The name is kept, empty, because
the page tests state their own closures as "the theme's and no more".
"""

THEME_BUILD: frozenset[str] = frozenset()
"""
What the first `Theme.build()` loads on top of `THEME`: nothing, since T5-B2.
It was `imscribe.nodes`, `imscribe.pack` and `imscribe.badness`, for the
`InterlineSkip` each block style held.
"""

STYLE = frozenset(
    {
        "imscribe.units",
        "imscribe.fontmetrics",
        "imscribe.nodes",
        "imscribe.pack",
        "imscribe.badness",
    }
)
"""
What `imscribe.style`, the measuring half, loads of the reference core at
import: the node and packing types its adapters are written against, and the
two modules that hand it the lengths and `Face`. `imscribe.style` is reference
core itself; this is what reaching it costs.
"""

OLD_READER = frozenset({"imscribe.fontlib", "imscribe.fontmetrics"})
"""
What asking `imscribe.fontlib` for an em size loads (`code_size` given a
pixel height, `imscribe.em_size_for_pixel_height`, WHILE THE LIBRARY HAS NO
FONTS): `imscribe.fontlib` and the metrics protocols it implements. Until
2026-10-12 this set was called `FONT_FILES` and `imscribe.typesetter.load_fonts`
loaded it too, to find a file; the table of files is `imscribe.fontfiles`'
now, which is not reference core.
"""

FONT_FILES = OLD_READER
"""The old name of `OLD_READER`, for the test files that import it."""

INTERLINE = STYLE | {"imscribe.style"}
"""
What `BlockStyle.interline` loads when it is first read: `imscribe.style`
builds the triple. The reference compositor's door, not the typeset layer's.
"""

MEASURING = STYLE | OLD_READER | {"imscribe.style"}
"""
What measuring a face from its font file loads of the reference core, when
it is called and not before, AND ONLY WHILE `imscribe.typesetter.ready()` IS
FALSE: `imscribe.style.fontlib_metrics`, which is `imscribe.style` (and so
`STYLE`) and `imscribe.fontlib`. The one thing a page may take from the
reference core, when it calls `Theme.at_pixel_height` or
`imscribe.ui.pages.face_metrics` before the library has its fonts.
"""

METRICS_OWN = frozenset(
    {
        "imscribe.typeset_metrics",
        "imscribe.typesetter",
        "imscribe.description",
        "imscribe.fontfiles",
        "imscribe.primitives",
        "imscribe.theme",
    }
)
"""
What asking for a face's metrics may load of imscribe that is NOT reference
core: `imscribe.typeset_metrics`, which decides who answers, and what it
imports.
"""

EXPECTED = {
    "imscribe.ui": NOTHING,
    "imscribe.ui.palette": NOTHING,
    "imscribe.ui.ownership": NOTHING,
    "imscribe.primitives": NOTHING,
    "imscribe.theme": THEME,
    "imscribe.ui.pages": THEME,
    "imscribe.ui.app": THEME,
    "imscribe.description": NOTHING,
    "imscribe.typesetter": NOTHING,
    "imscribe.typeset_find": NOTHING,
    "imscribe.typeset_markdown": THEME,
    "imscribe.markdown_rules": NOTHING,
    "imscribe.diff": NOTHING,
    "imscribe.fontfiles": NOTHING,
    "imscribe.typeset_metrics": NOTHING,
    "imscribe.ui.typeset_view": THEME,
    "imscribe.ui.typeset_stream_view": THEME,
    "imscribe.ui.typeset_diff_view": THEME,
    "imscribe.ui.typeset_hosts": THEME,
    "imscribe.ui.pages._syntax": THEME,
    "imscribe.ui.pages.chat": THEME,
    "imscribe.ui.pages.columns": THEME,
    "imscribe.ui.pages.diff": THEME,
    "imscribe.ui.pages.document": THEME,
    "imscribe.ui.pages.find": THEME,
    "imscribe.ui.pages.formula": THEME,
    "imscribe.ui.pages.inspector": THEME,
    "imscribe.ui.pages.mathtext": THEME,
    "imscribe.ui.pages.specimen": THEME,
    "imscribe.ui.pages.stream": THEME,
    "imscribe.ui.pages.stress": THEME,
    "imscribe.ui.pages.tables": THEME,
    "imscribe.ui.pages.themes": THEME,
    "imscribe.ui.pages.typeset": THEME,
}
"""
Every module of the typeset layer loads nothing of the reference core
(`THEME` is empty and is written where a module names a theme, which is where
the floor of two leaves was until T5-B2).

That includes every demo page (measured 2026-10-11, both forms of the
import); none has a fallback to an old view any more. `imscribe.ui.typeset_table`
(the stopgap for tables) was deleted when tables became the library's, and the
Typeset page, which loaded eighteen modules of the core for its fallback and
for `imscribe.markdown`, loads the two leaves like the rest.

`imscribe.ui.app` joined the list on 2026-10-11 (tranche 5). It loaded
twenty-one modules of the core at import, for a `DocumentView`, a specimen
and a formula gallery it built whichever renderer drew; it builds none of
them now. `pages.blocks` and the three `pages._old_*` galleries, which stood
on the core, are deleted, and `pages.columns`, which loaded the same
twenty-one as the app, cuts its columns with the library and is on the list:
every page module is (`test_every_page_module_has_a_stated_closure`).
"""

FORMS = ("import", "from")


def _fresh(source: str) -> list[str]:
    """
    Run a snippet in a new interpreter from the repository root; return its stdout lines.

    The environment is this process's, so under `make test TYPESET=1` the child
    has the library's two variables and the closure is measured with them set.
    """
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


_PRINT_LOADED = "print('\\n'.join(sorted(m for m in sys.modules if m.split('.')[0] == 'imscribe')))"


def _statement(module: str, form: str) -> str:
    """
    The line that imports `module`: `import a.b.c`, or `from a.b import c`.
    """
    if form == "import":
        return f"import {module}"
    package, _, name = module.rpartition(".")
    return f"from {package} import {name}"


def _loaded_by(module: str, form: str = "import") -> set[str]:
    """
    Every `imscribe` module in a fresh interpreter's `sys.modules` after one import.

    `form` is which way the import is written; see the module docstring for
    why that is a parameter.
    """
    return set(_fresh(f"import sys\n{_statement(module, form)}\n{_PRINT_LOADED}"))


def test_every_reference_core_name_is_a_module_that_exists() -> None:
    """
    A name in `SVG_CLOSURE` that is no file can never be loaded, so it would assert nothing.

    When a module of the reference core is deleted this fails: remove its
    name here and from the sets that hold it.
    """
    missing = sorted(
        name
        for name in SVG_CLOSURE
        if not (REPO / (name.replace(".", "/") + ".py")).is_file()
        and not (REPO / name.replace(".", "/") / "__init__.py").is_file()
    )
    assert not missing, f"no such module (deleted? then delete the name here): {missing}"
    assert OLD_CORE < REFERENCE_CORE < SVG_CLOSURE and SHARED < SVG_CLOSURE


def test_the_reference_core_is_what_the_litmus_chain_loads() -> None:
    """
    `SVG_CLOSURE` measured, not remembered: a fresh interpreter loads
    `scripts/render_litmus.py` as a module (which imports the SVG backend and
    everything it feeds it) and what it has of imscribe is the set, exactly.

    A module of imscribe that is in neither this set nor the typeset layer has
    no reason to be in the tree; one the chain newly needs shows here.
    """
    lines = _fresh(
        "import importlib.util, sys\n"
        "where = 'scripts/render_litmus.py'\n"
        "spec = importlib.util.spec_from_file_location('render_litmus', where)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['render_litmus'] = module\n"
        "spec.loader.exec_module(module)\n"
        f"{_PRINT_LOADED}"
    )
    loaded = set(lines)
    assert loaded == SVG_CLOSURE, (sorted(loaded - SVG_CLOSURE), sorted(SVG_CLOSURE - loaded))


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("module", sorted(EXPECTED))
def test_importing_a_typeset_module_loads_exactly_the_stated_old_core(
    module: str, form: str
) -> None:
    """
    The measurement: a fresh interpreter, one import, `sys.modules` against `EXPECTED`.

    Once per way of writing the import. The two must agree; when they did not,
    the `from` form of everything under `imscribe.ui` loaded the compositor.

    Against the WHOLE reference core (`REFERENCE_CORE`: the SVG litmus
    chain's closure but for the five modules the typeset layer shares with
    it), so `imscribe.markdown` and `imscribe.style` are measured too; until
    tranche 5 this was against `OLD_CORE`, which names neither.

    **Twice in the one child: after the import, and again after a theme has
    been built there** (`Theme.build()`, the default and an all-mono one).
    The second is what a host does next, and until T5-B2 it was where three
    more modules of the core came in.
    """
    statement = _statement(module, form)
    lines = _fresh(
        f"import sys\n{statement}\n{_PRINT_LOADED}\nprint('--')\n"
        "from imscribe.theme import Faces, Theme\n"
        "Theme.build()\n"
        "Theme.build(20.0, faces=Faces.mono())\n"
        f"{_PRINT_LOADED}"
    )
    cut = lines.index("--")
    loaded, built = set(lines[:cut]), set(lines[cut + 1 :])
    assert module in loaded, "the child did not import what it was asked to"
    core = (loaded & REFERENCE_CORE) - {module}
    expected = EXPECTED[module]
    more, fewer = sorted(core - expected), sorted(expected - core)
    assert not more, f"`{statement}` now also loads {more} of the reference core"
    assert (
        not fewer
    ), f"`{statement}` no longer loads {fewer}: remove them from EXPECTED in this file"
    after = sorted(built & REFERENCE_CORE)
    assert not after, f"`{statement}` and then `Theme.build()` loads {after}"
    assert built - loaded <= {"imscribe.theme", "imscribe.primitives"}, sorted(built - loaded)


def test_importing_the_package_loads_nothing_and_a_theme_built_through_it_loads_no_core() -> None:
    """
    The package itself, which has one way of being imported: `import imscribe`
    loads no other module of it, and `imscribe.Theme.build()` loads the theme
    and its leaf.
    """
    lines = _fresh(
        f"import sys\nimport imscribe\n{_PRINT_LOADED}\nprint('--')\n"
        f"imscribe.Theme.build()\n{_PRINT_LOADED}"
    )
    cut = lines.index("--")
    assert lines[:cut] == ["imscribe"]
    assert lines[cut + 1 :] == ["imscribe", "imscribe.primitives", "imscribe.theme"]


def test_every_page_module_has_a_stated_closure() -> None:
    """
    `EXPECTED` names every module under `imscribe/ui/pages/`, helpers included,
    so a page added tomorrow is measured or this is red. Until tranche 5 the
    pages that stood on the old core were left off the list, which is how a
    list of "the typeset layer" came to say nothing about five modules.
    """
    pages = REPO / "imscribe" / "ui" / "pages"
    on_disk = {f"imscribe.ui.pages.{path.stem}" for path in pages.glob("*.py")} - {
        "imscribe.ui.pages.__init__"
    }
    stated = {name for name in EXPECTED if name.startswith("imscribe.ui.pages.")}
    assert on_disk - stated == set(), "a page module has no entry in EXPECTED"
    assert stated - on_disk == set(), "EXPECTED names a page module that is not there"
    assert {EXPECTED[name] for name in stated} == {NOTHING}


def test_every_module_outside_the_reference_core_has_a_stated_closure() -> None:
    """
    `EXPECTED` names every module of `imscribe` that is not reference core, but
    for two: the package itself (it imports nothing: `tests/test_facade.py`)
    and `imscribe.ui.fonts`, which T5-B1 left in place and which is the old
    atlas loader (it imports `imscribe.fontlib` at the top and is imported
    only when the app's font callback runs without the library).

    So "the typeset layer, the app and the pages" is not a list somebody
    keeps: a module added to the package tomorrow is measured or this is red.
    """
    root = REPO / "imscribe"
    on_disk = set()
    for path in root.rglob("*.py"):
        parts = list(path.relative_to(REPO).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        on_disk.add(".".join(parts))
    unstated = on_disk - SVG_CLOSURE - set(EXPECTED)
    assert unstated == {"imscribe.ui.fonts"}, sorted(unstated)
    assert set(EXPECTED) - on_disk == set(), "EXPECTED names a module that is not there"
    # Nothing stated loads anything of the reference core.
    assert {name for held in EXPECTED.values() for name in held} == set()
    assert THEME == THEME_BUILD == NOTHING


EXAMPLES = sorted(path.name for path in (REPO / "examples").glob("*.py"))


@pytest.mark.parametrize("example", EXAMPLES)
def test_loading_an_example_loads_no_more_of_the_reference_core_than_a_theme(
    example: str,
) -> None:
    """
    Each file under `examples/`, loaded as a module in a fresh interpreter
    (its `main` not run), and then a theme built there: of the reference
    core it has nothing, and no module of imscribe that is not on a list here.
    """
    assert len(EXAMPLES) == 4, EXAMPLES
    lines = _fresh(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('example', 'examples/{example}')\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['example'] = module\n"
        "spec.loader.exec_module(module)\n"
        f"{_PRINT_LOADED}\n"
        "module.Theme.build()\n"
        f"{_PRINT_LOADED}"
    )
    loaded = set(lines)
    assert "imscribe.theme" in loaded and lines[: len(lines) // 2] == lines[len(lines) // 2 :]
    assert loaded & REFERENCE_CORE == NOTHING, sorted(loaded & REFERENCE_CORE)
    assert loaded <= set(EXPECTED) | SHARED | THEME, sorted(loaded - set(EXPECTED) - SHARED - THEME)


def _submodules_of_the_ui_package() -> list[str]:
    """
    Every module and package directly under `imscribe/ui`, by name.
    """
    root = REPO / "imscribe" / "ui"
    stems = {path.stem for path in root.glob("*.py")} - {"__init__"}
    stems |= {path.parent.name for path in root.glob("*/__init__.py")}
    return sorted(stems)


def test_asking_the_package_for_a_submodule_does_not_import_composition() -> None:
    """
    The question `from imscribe.ui import <submodule>` begins with, for every submodule.

    `hasattr` is that question exactly (CPython's `_handle_fromlist`). Each
    name is asked before its module has been imported, the answer must be "not
    here", and nothing of imscribe may have been loaded to give it -- then the
    import system goes on to import the submodule, which the test above
    measures for the modules it names.
    """
    names = _submodules_of_the_ui_package()
    assert {"typeset_view", "palette", "ownership", "composition", "pages"} <= set(names)
    lines = _fresh(
        "import sys\n"
        "import imscribe.ui\n"
        "before = set(sys.modules)\n"
        f"print([name for name in {names!r} if hasattr(imscribe.ui, name)])\n"
        "print(sorted(set(sys.modules) - before))\n"
        # ... and a name that is no submodule is still composition's to answer.
        "print(hasattr(imscribe.ui, 'compose'), 'imscribe.ui.composition' in sys.modules)\n"
        # With composition loaded the answer for a submodule is the same.
        f"rest = [name for name in {names!r} if name != 'composition']\n"
        "print([name for name in rest if hasattr(imscribe.ui, name)])"
    )
    assert lines == ["[]", "[]", "True True", "[]"]


def test_a_name_that_is_no_submodule_and_no_identifier_is_refused_as_before() -> None:
    lines = _fresh(
        "import imscribe.ui\n"
        "for name in ('no_such_thing', 'not an identifier', 'pages.typeset', ''):\n"
        "    try:\n"
        "        getattr(imscribe.ui, name)\n"
        "    except AttributeError as error:\n"
        "        print(str(error))"
    )
    assert lines == [
        f"module 'imscribe.ui' has no attribute {name!r}"
        for name in ("no_such_thing", "not an identifier", "pages.typeset", "")
    ]


@pytest.mark.parametrize("form", FORMS)
def test_building_a_theme_loads_nothing_and_reading_a_style_loads_nothing(form: str) -> None:
    """
    The limit of `EXPECTED["imscribe.theme"]`, measured so it cannot be overread.

    Importing the module (either way of writing it) loads itself and
    `imscribe.primitives`. Building themes, asking one for a face, and reading
    every block style's leading and strut load nothing more: no font is
    opened, no line is packed, no class of the reference core is made. Until
    T5-B2 the first `Theme.build()` loaded `imscribe.nodes`, `imscribe.pack`
    and `imscribe.badness`.

    Then the door, so that it is known to be one: reading `interline`, which
    only the reference compositor does, loads `INTERLINE` and nothing else,
    and answers the triple `Theme.build` used to store.
    """
    lines = _fresh(
        "import sys\n"
        f"{_statement('imscribe.theme', form)}\n"
        "theme = sys.modules['imscribe.theme']\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "built = theme.Theme.build()\n"
        "built.face_for(theme.BlockKind.PARAGRAPH, theme.Emphasis(bold=True))\n"
        "mono = theme.Theme.build(20.0, faces=theme.Faces.mono())\n"
        "for style in (*built.blocks.values(), *mono.blocks.values()):\n"
        "    assert style.strut.total == style.leading and type(style.leading) is int\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "skip = built.style(theme.BlockKind.CODE).interline\n"
        "style = built.style(theme.BlockKind.CODE)\n"
        "print(type(skip).__module__, skip.baselineskip.width == style.leading,\n"
        "      skip.lineskip.width == round(style.font.size * 0.1), skip.lineskiplimit,\n"
        "      skip.baselineskip.stretch, skip.baselineskip.shrink)\n"
        f"{_PRINT_LOADED}"
    )
    first = lines.index("--")
    second = lines.index("--", first + 1)
    imported, built = set(lines[:first]), set(lines[first + 1 : second])
    assert imported == {"imscribe", "imscribe.theme", "imscribe.primitives"}
    assert built == imported, f"`Theme.build()` now loads {sorted(built - imported)}"
    assert lines[second + 1] == "imscribe.pack True True 0 0 0"
    asked = set(lines[second + 2 :])
    assert asked - imported == INTERLINE, sorted((asked - imported) ^ INTERLINE)


def test_the_reference_cores_own_modules_load_what_is_stated() -> None:
    """
    `STYLE` and `FONT_FILES` measured at import, so that the sets the named
    exceptions are stated in are facts about `imscribe.style` and
    `imscribe.fontlib` and not memories of them.
    """
    assert _loaded_by("imscribe.style") & REFERENCE_CORE == STYLE | {"imscribe.style"}
    assert _loaded_by("imscribe.fontlib") & REFERENCE_CORE == OLD_READER
    assert STYLE | OLD_READER | {"imscribe.style"} <= REFERENCE_CORE


def test_the_named_exceptions_load_exactly_what_is_stated() -> None:
    """
    Each call that still reaches the reference core, alone in a fresh
    interpreter after a theme has been built, and what it loaded: exactly the
    set stated for it. **The library has no fonts in that interpreter** (no
    Dear ImGui context is made, so `typesetter.ready()` is false whether or
    not the library is there), which is the one state in which the first
    four reach it. Beside the reference core each may load
    `imscribe.typeset_metrics` and what that imports (`METRICS_OWN`), and
    nothing else of imscribe.
    """
    calls = {
        "at_pixel_height": "Theme.at_pixel_height(18.0)",
        "face_metrics": (
            "from imscribe.ui.pages import face_metrics\n"
            "before = loaded()\n"
            "from imscribe.theme import font_key\n"
            "from imscribe.primitives import Face, sp_from_px\n"
            "face_metrics(font_key(Face.CODE, sp_from_px(20.0)))"
        ),
        "code_size": (
            "from imscribe.ui.typeset_diff_view import code_size\n"
            "code_size(theme)\n"
            # Without a pixel height it asks nothing of a font file.
            "assert not loaded() & CORE, sorted(loaded() & CORE)\n"
            "before = loaded()\n"
            "code_size(theme, pixel_height=16.0)"
        ),
        "em_size": (
            "import imscribe\n"
            "before = loaded()\n"
            "imscribe.em_size_for_pixel_height(imscribe.Face.PROSE, 16.0)"
        ),
        "interline": "theme.style(BlockKind.PARAGRAPH).interline",
    }
    stated = {
        "at_pixel_height": MEASURING,
        "face_metrics": MEASURING,
        "code_size": OLD_READER,
        "em_size": OLD_READER,
        "interline": INTERLINE,
    }
    for name, call in calls.items():
        lines = _fresh(
            "import sys\n"
            "def loaded():\n"
            "    return {m for m in sys.modules if m.split('.')[0] == 'imscribe'}\n"
            f"CORE = set({sorted(REFERENCE_CORE)!r})\n"
            "from imscribe.theme import BlockKind, Theme\n"
            "theme = Theme.build()\n"
            "before = loaded()\n"
            "assert not before & CORE\n"
            f"{call}\n"
            "from imscribe import typesetter\n"
            "assert not typesetter.ready()\n"
            "print('\\n'.join(sorted(loaded() - before)))"
        )
        new = set(lines)
        assert new & REFERENCE_CORE == stated[name], (name, sorted(new ^ stated[name]))
        own = new - REFERENCE_CORE
        assert own <= METRICS_OWN, (name, sorted(own - METRICS_OWN))
        assert stated[name] <= REFERENCE_CORE


_READY = (
    "import os, sys\n"
    "def loaded():\n"
    "    return {m for m in sys.modules if m.split('.')[0] in ('imscribe', 'fontTools')}\n"
    "from imscribe import typesetter\n"
    "before = loaded()\n"
    "if os.environ.get('IMTYPESET_LIBRARY'):\n"
    "    from imgui_bundle import imgui\n"
    "    imgui.create_context()\n"
    "    imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value\n"
    "print(typesetter.load_fonts(), typesetter.ready(), typesetter.reason())\n"
)
"""A fresh interpreter's first lines: the library's fonts loaded, when there is a library."""


def test_loading_the_fonts_loads_the_table_of_files_and_no_reference_core() -> None:
    """
    `imscribe.typesetter.load_fonts`, with the library and a Dear ImGui
    context of its own, in a fresh interpreter: it answers True and what it
    loaded of imscribe is `imscribe.fontfiles` and the leaf, exactly. No
    `imscribe.fontlib` (which it loaded until 2026-10-12, to find a file) and
    no fontTools. Skipped without the library, where `load_fonts` answers
    False before it asks for a file (the first half, which runs either way).
    """
    script = _READY + "print('\\n'.join(sorted(loaded() - before)))"
    without = {
        name: value for name, value in os.environ.items() if not name.startswith("IMTYPESET_")
    }
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=REPO, env=without
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("\n") == ["False False IMTYPESET_LIBRARY is not set", "", ""]
    if not os.environ.get("IMTYPESET_LIBRARY"):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    lines = _fresh(script)
    assert lines[0] == "True True ", lines[0]
    assert set(lines[1:]) == {"imscribe.fontfiles", "imscribe.primitives"}, sorted(lines[1:])


def test_with_the_library_ready_nothing_reaches_the_reference_core() -> None:
    """
    THE claim of 2026-10-12, measured: once `typesetter.load_fonts()` has
    succeeded, every call that used to open a font file with the old reader
    is answered by imtypeset, and a fresh interpreter that makes all of them
    has loaded NO module of the reference core and no fontTools.

    The calls: a host's `register_font` (before the load, as it must be),
    `load_fonts`, `Theme.at_pixel_height` with no resolver (the default
    faces and all-mono), `imscribe.ui.pages.face_metrics` and a theme sized
    through a `PageContext`'s resolver, `code_size` given a pixel height,
    `imscribe.em_size_for_pixel_height` for every face, and the markdown of
    `demo/sample.md` described under the theme.

    Then `unload()`: the library has no fonts again, and the same question
    is the old reader's (`MEASURING`), which is the exception as stated.
    Skipped without the library.
    """
    if not os.environ.get("IMTYPESET_LIBRARY"):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    lines = _fresh(
        "import sys\n"
        "import imscribe\n"
        "from imscribe import Face, register_font, unregister_font\n"
        "from imscribe.fontfiles import font_file\n"
        "register_font(Face.CODE_BOLD, font_file(Face.CODE))\n"
        + _READY
        + "from imscribe.theme import Faces, Theme, font_key\n"
        "from imscribe.primitives import sp_from_px\n"
        "from imscribe.ui.pages import PageContext, face_metrics\n"
        "from imscribe.ui.typeset_diff_view import code_size\n"
        "from imscribe.typeset_markdown import MarkdownConverter, parse_markdown\n"
        "theme = Theme.at_pixel_height(16.0)\n"
        "mono = Theme.at_pixel_height(18.0, faces=Faces.mono())\n"
        "probe = face_metrics(font_key(Face.CODE, sp_from_px(20.0)))\n"
        "print(type(probe).__module__, type(probe).__name__, probe.ascent > probe.descent > 0)\n"
        "Theme.at_pixel_height(15.0, metrics=PageContext.build().metrics)\n"
        "code_size(theme, pixel_height=16.0)\n"
        "print([imscribe.em_size_for_pixel_height(face, 16.0) > 0 for face in Face])\n"
        "source = open('demo/sample.md', encoding='utf-8').read()\n"
        "MarkdownConverter(theme).describe(parse_markdown(source, theme).blocks)\n"
        "print('\\n'.join(sorted(loaded())))\n"
        "print('--')\n"
        "typesetter.unload()\n"
        "unregister_font(Face.CODE_BOLD)\n"
        "print(typesetter.ready(), Theme.at_pixel_height(16.0) == theme)\n"
        "print('\\n'.join(sorted(loaded())))"
    )
    assert lines[0] == "True True ", lines[0]
    assert lines[1] == "imscribe.typeset_metrics LibraryMetrics True"
    assert lines[2] == str([True] * 7)
    cut = lines.index("--")
    ready = set(lines[3:cut])
    assert not ready & REFERENCE_CORE, sorted(ready & REFERENCE_CORE)
    assert not {name for name in ready if name.split(".")[0] == "fontTools"}
    assert ready <= set(EXPECTED) | SHARED, sorted(ready - set(EXPECTED) - SHARED)
    # ... and the exception, exactly: with no fonts the old reader is asked,
    # and it gives the theme the library gave.
    assert lines[cut + 1] == "False True"
    after = set(lines[cut + 2 :])
    assert after & REFERENCE_CORE == MEASURING
    assert "fontTools" in after


def test_no_module_of_the_typeset_layer_reads_a_styles_interline() -> None:
    """
    `BlockStyle.interline` is the one attribute of a theme that loads the
    reference core, so no module `EXPECTED` names may read it: by source,
    since a read happens at a draw and `EXPECTED` is import time. They read
    `leading`.
    """
    for module in sorted(EXPECTED):
        path = REPO / module.replace(".", "/")
        file = (
            path.with_suffix(".py") if path.with_suffix(".py").is_file() else path / "__init__.py"
        )
        if module == "imscribe.theme":
            continue  # it defines the property
        assert ".interline" not in file.read_text(encoding="utf-8"), module
    for example in EXAMPLES:
        assert ".interline" not in (REPO / "examples" / example).read_text(encoding="utf-8")


def test_the_views_do_not_load_one_anothers_old_counterparts() -> None:
    """
    Stated on its own because it is the reason for the moves: no line breaker,
    no selection model, no compositor, no node-making parser and no measuring
    adapters behind `TypesetView`. (It also named the draw backend, the unit
    layout, `BareView` and `StreamView` until they were deleted.)
    """
    loaded = _loaded_by("imscribe.ui.typeset_stream_view")
    for gone in (
        "imscribe.linebreak",
        "imscribe.selection",
        "imscribe.shipout",
        "imscribe.markdown",
        "imscribe.style",
        "imscribe.ui.composition",
        "imscribe.ui.fonts",
    ):
        assert gone not in loaded
    assert {"imscribe.ui.palette", "imscribe.ui.ownership", "imscribe.ui.typeset_view"} <= loaded


# ---- the moves: one object under both paths --------------------------------

PALETTE_NAMES = (
    "DARK_DIFF_PALETTE",
    "DARK_PALETTE",
    "DEFAULT_DIFF_PALETTE",
    "DEFAULT_PALETTE",
    "DiffPalette",
    "DrawStats",
    "Palette",
    "rgba",
)
OWNERSHIP_NAMES = (
    "CLIPBOARD_NUL",
    "MIN_WIDTH_PX",
    "SELECTION_OWNERSHIP",
    "SelectionOwnership",
    "clipboard_text",
    "scroll_for",
)
COMPOSITION_PRIVATE = (
    "_Context",
    "_WrappedRow",
    "_apportioned",
    "_cell_lines",
    "_extent",
    "_hang_marker",
    "_longest_word",
    "_natural_widths",
    "_skips",
    "_stacked",
    "_table_boxes",
    "_table_row",
    "_table_rows",
    "_text_boxes",
    "break_paragraph",
)
"""Names the tests reach as `imscribe.ui.<name>` that are not in its `__all__`."""


@pytest.mark.parametrize("name", PALETTE_NAMES)
def test_a_palette_name_is_one_object_under_both_paths(name: str) -> None:
    """
    `imscribe.ui.palette` defines it and the facade, where it promises the
    name, hands out that object. (A third path, the old ImGui draw backend,
    which the palettes were moved out of, was deleted in tranche 5.)
    """
    import imscribe
    from imscribe.ui import palette

    assert name in palette.__all__
    assert getattr(palette, name).__module__ == "imscribe.ui.palette" or name.isupper()
    if name in imscribe.__all__:
        assert getattr(imscribe, name) is getattr(palette, name)


def test_the_ownership_names_are_where_the_views_take_them_from() -> None:
    """
    They were `BareView`'s module's and were moved out so that a view could
    take turns without loading it; that module is deleted, and with it the
    test that each name was one object under both paths.
    """
    from imscribe.ui import ownership

    assert set(OWNERSHIP_NAMES) <= set(ownership.__all__)


def test_there_is_one_selection_counter_and_every_view_takes_turns_on_it() -> None:
    """
    The defect `SelectionOwnership` exists to prevent is a second counter.
    """
    from imscribe.ui import ownership, typeset_diff_view, typeset_view

    counter = ownership.SELECTION_OWNERSHIP
    assert typeset_view.SELECTION_OWNERSHIP is counter
    assert typeset_diff_view.SELECTION_OWNERSHIP is counter
    taken = typeset_diff_view.SELECTION_OWNERSHIP.take()
    assert typeset_view.SELECTION_OWNERSHIP.holds(taken)


def test_the_tail_following_numbers_are_stated_once() -> None:
    """
    `FAR_PX` and `AT_BOTTOM_PX` are `imscribe.ui.ownership`'s, and the stream
    view imports them: one statement, read from the source so that a second
    one put in `typeset_stream_view.py` with the same value is still caught.
    (The old `stream_view.py`, where they came from, is deleted.)
    """
    import ast

    from imscribe.ui import ownership, typeset_stream_view

    for view in (typeset_stream_view,):
        assert view.FAR_PX is ownership.FAR_PX
        assert view.AT_BOTTOM_PX is ownership.AT_BOTTOM_PX
        tree = ast.parse(Path(view.__file__).read_text(encoding="utf-8"))
        assigned = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign | ast.AnnAssign)
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        assert not assigned & {"FAR_PX", "AT_BOTTOM_PX"}, view.__name__


THEME_NAMES = (
    "Align",
    "BODY_SIZE_PX",
    "BlockKind",
    "BlockStyle",
    "DEFAULT_FACES",
    "Emphasis",
    "Faces",
    "FontSpec",
    "MARKER_GAP_EM",
    "QUOTE_INDENT_EM",
    "STRUT_HEIGHT_FRACTION",
    "Spacing",
    "Strut",
    "TYPE_SCALE_RATIO",
    "Theme",
    "WIDEST_MARKER_EM",
    "font_key",
    "parse_font_key",
)
"""
What moved from `imscribe.style` to `imscribe.theme`. `TYPE_SCALE_RATIO` is in
neither `__all__` (it never was) and is read from `imscribe.style` by name.
"""

STYLE_KEPT = (
    "MetricsResolver",
    "NEUTRAL_SPACE_FACTOR",
    "char_measure",
    "fontlib_metrics",
    "interline_skip",
    "interword_glue",
    "space_factor_after",
)
"""What `imscribe.style` still defines itself: the half that measures."""


@pytest.mark.parametrize("name", THEME_NAMES)
def test_a_theme_name_is_one_object_under_every_path(name: str) -> None:
    """
    `isinstance` and `is` across the old home and the new one are the same test.
    """
    import imscribe
    from imscribe import style, theme

    assert getattr(style, name) is getattr(theme, name)
    if name != "TYPE_SCALE_RATIO":
        assert name in style.__all__ and name in theme.__all__
    if name in imscribe.__all__:
        assert getattr(imscribe, name) is getattr(theme, name)
    defined = getattr(theme, name)
    if isinstance(defined, type) or callable(defined):
        assert defined.__module__ == "imscribe.theme"


def test_the_two_halves_of_style_account_for_every_name_it_exported() -> None:
    from imscribe import style, theme

    assert sorted(style.__all__) == sorted({*THEME_NAMES, *STYLE_KEPT} - {"TYPE_SCALE_RATIO"})
    assert sorted(theme.__all__) == sorted(set(THEME_NAMES) - {"TYPE_SCALE_RATIO"})
    for name in STYLE_KEPT:
        assert not hasattr(theme, name), name
    assert style.fontlib_metrics.__module__ == "imscribe.style"
    # A theme built through either path is made of the one set of classes.
    built = style.Theme.build()
    assert type(built) is theme.Theme
    assert all(type(block) is theme.BlockStyle for block in built.blocks.values())
    assert built == theme.Theme.build()
    assert isinstance(built.style(theme.BlockKind.CODE).strut, style.Strut)


def test_style_still_has_the_names_it_only_ever_imported() -> None:
    """
    `from imscribe.style import Face` was never promised and is written all the same.

    The split's first version dropped it (the name went with the code that used
    it) and `tests/test_page_math.py` stopped importing. What a module imported
    for itself is part of what can be imported from it.
    """
    from imscribe import fontmetrics, nodes, pack, primitives, style, units

    assert style.Face is fontmetrics.Face is primitives.Face
    assert style.Box is nodes.Box
    assert style.InterlineSkip is pack.InterlineSkip
    assert style.sp_from_px is units.sp_from_px
    assert style.DEFAULT_PX_PER_INCH == units.DEFAULT_PX_PER_INCH


PRIMITIVES_OF_UNITS = (
    "BP_PER_INCH",
    "DEFAULT_PX_PER_INCH",
    "PT_PER_INCH",
    "UNITY",
    "Scaled",
    "pt_from_sp",
    "px_from_sp",
    "round_to_px",
    "sp_from_bp",
    "sp_from_pt",
    "sp_from_px",
)
"""
What moved from `imscribe.units` to `imscribe.primitives`. `Face` moved there
from `imscribe.fontmetrics`.
"""


def test_a_moved_length_or_face_is_one_object_under_both_paths() -> None:
    """
    `imscribe.units` and `imscribe.fontmetrics` import back what
    `imscribe.primitives` defines: `is`, `isinstance` and enum membership
    across the old home and the new are the same test. What `imscribe.units`
    kept (`GlueOrder`, `MAX_DIMEN`, `RUNNING`) is the layout core's and is
    not in the new module.
    """
    import imscribe
    from imscribe import fontmetrics, primitives, units

    assert sorted(primitives.__all__) == sorted({*PRIMITIVES_OF_UNITS, "Face"})
    for name in PRIMITIVES_OF_UNITS:
        assert getattr(units, name) is getattr(primitives, name), name
        assert name in units.__all__
    assert set(units.__all__) - set(PRIMITIVES_OF_UNITS) == {"GlueOrder", "MAX_DIMEN", "RUNNING"}
    for name in ("GlueOrder", "MAX_DIMEN", "RUNNING"):
        assert not hasattr(primitives, name), name
    assert units.sp_from_px.__module__ == "imscribe.primitives"
    assert (
        fontmetrics.Face is primitives.Face and primitives.Face.__module__ == "imscribe.primitives"
    )
    assert [face.value for face in fontmetrics.Face] == [
        "prose",
        "prose-bold",
        "prose-italic",
        "prose-bold-italic",
        "code",
        "code-bold",
        "math",
    ]
    for name in ("Face", "Scaled", "sp_from_px", "px_from_sp"):
        assert getattr(imscribe, name) is getattr(primitives, name)


FONTFILES_NAMES = (
    "MissingFontError",
    "backing_face",
    "font_directory",
    "font_file",
    "on_registry_change",
    "register_font",
    "registered_fonts",
    "unregister_font",
)
"""What moved from `imscribe.fontlib` to `imscribe.fontfiles` on 2026-10-12."""


def test_a_moved_font_file_name_is_one_object_under_every_path() -> None:
    """
    `imscribe.fontlib` imports back what `imscribe.fontfiles` defines, tables
    included, so a file registered through either path (or the facade) is
    seen by both, and `except fontlib.MissingFontError` catches what
    `fontfiles.font_file` raises.
    """
    import imscribe
    from imscribe import fontfiles, fontlib

    assert sorted(fontfiles.__all__) == sorted(FONTFILES_NAMES)
    for name in FONTFILES_NAMES:
        assert getattr(fontlib, name) is getattr(fontfiles, name), name
        assert name in fontlib.__all__
        assert getattr(fontfiles, name).__module__ == "imscribe.fontfiles"
        if name in imscribe.__all__:
            assert getattr(imscribe, name) is getattr(fontfiles, name)
    for table in ("_FONT_FILES", "_STAND_INS", "_REGISTERED", "_LISTENERS"):
        assert getattr(fontlib, table) is getattr(fontfiles, table), table
    # The old reader drops what it read when a file changes: it is a listener.
    assert fontlib._registry_changed in fontfiles._LISTENERS


def test_the_font_file_table_imports_only_the_leaf() -> None:
    """
    By source: `imscribe/fontfiles.py` imports `imscribe.primitives` and no
    other module of imscribe, a function's body included; and a fresh
    interpreter that imports it, registers a file and asks for every role's
    file has loaded those two modules and no fontTools.
    """
    import ast

    tree = ast.parse((REPO / "imscribe" / "fontfiles.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not [alias.name for alias in node.names if alias.name.startswith("imscribe")]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert not (node.module or "").startswith("imscribe") or node.module == (
                "imscribe.primitives"
            )
    lines = _fresh(
        "import sys\n"
        "from imscribe import Face, register_font, registered_fonts, unregister_font\n"
        "from imscribe.fontfiles import font_file\n"
        "register_font(Face.CODE_BOLD, font_file(Face.CODE))\n"
        "assert font_file(Face.CODE_BOLD) == font_file(Face.CODE)\n"
        "assert list(registered_fonts()) == [Face.CODE_BOLD]\n"
        "unregister_font(Face.CODE_BOLD)\n"
        "assert [font_file(face).is_file() for face in Face] == [True] * len(Face)\n"
        "print('fontTools' in sys.modules)\n"
        f"{_PRINT_LOADED}"
    )
    assert lines == ["False", "imscribe", "imscribe.fontfiles", "imscribe.primitives"]


def test_the_new_leaf_imports_nothing_of_imscribe() -> None:
    """
    By source: no `import` of `imscribe` anywhere in `imscribe/primitives.py`,
    a function's body included. It is the floor of everything; an import
    added to it is added to every module here.
    """
    import ast

    tree = ast.parse((REPO / "imscribe" / "primitives.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not [alias.name for alias in node.names if alias.name.startswith("imscribe")]
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("imscribe") and node.level == 0
    assert _loaded_by("imscribe.primitives") == {"imscribe", "imscribe.primitives"}


def test_a_page_context_measures_with_the_real_resolver_asked_at_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `PageContext.metrics` defaults to `imscribe.ui.pages.face_metrics`, which
    WHILE THE LIBRARY HAS NO FONTS is `imscribe.style.fontlib_metrics` looked
    up when it is called: the same answer, a replacement of the name on
    `imscribe.style` is the one asked, and a caller's own resolver is kept.
    (With the library ready it is the library's answer:
    `tests/test_typeset_metrics.py`. This process may have loaded the
    library's fonts in another test, so `ready` is held false here.)

    It was the object itself, fetched when a context was made, until tranche
    5: making a context then loaded `imscribe.style`
    (`test_the_app_and_a_context_load_no_more_than_a_built_theme` is what
    holds that it no longer does).
    """
    import imscribe.style as style
    from imscribe import typesetter
    from imscribe.fontmetrics import Face
    from imscribe.theme import Theme, font_key
    from imscribe.ui.pages import PageContext, face_metrics
    from imscribe.units import sp_from_px

    monkeypatch.setattr(typesetter, "ready", lambda: False)
    key = font_key(Face.CODE, sp_from_px(20.0))
    assert PageContext.build().metrics is face_metrics
    assert PageContext(theme=Theme.build()).metrics is face_metrics
    assert face_metrics(key) == style.fontlib_metrics(key)
    chosen = PageContext.build(metrics=len).metrics
    assert chosen is len  # type: ignore[comparison-overlap]

    asked: list[str] = []
    real = style.fontlib_metrics

    def watching(font: str) -> object:
        asked.append(font)
        return real(font)

    style.fontlib_metrics = watching  # type: ignore[assignment]
    try:
        face_metrics(key)
    finally:
        style.fontlib_metrics = real
    assert asked == [key]


RUN_FLOOR = THEME | THEME_BUILD
"""
What a process has loaded of the reference core once the demo app has been
built and has shown a page with no library: what a BUILT theme loads, which
since T5-B2 is nothing.
"""


def test_the_app_and_a_context_load_no_more_than_a_built_theme() -> None:
    """
    `EXPECTED` is import time. This is the app at run, with no library:
    import it, make a context from the defaults, build the `App` (which scans
    and imports every page) and call the font lookup the context carries.
    After each step the reference core in `sys.modules` is `RUN_FLOOR`, which
    is empty: no node, no packer, no ship-out, no selection model, no view,
    no `imscribe.style`, no `imscribe.fontlib`, no `imscribe.units`.

    Until tranche 5 the app built a `DocumentView` and the measuring adapters
    in its constructor and this set was twenty-one modules at import.

    **Then every page object is built, and the one allowance is
    `MEASURING`.** A page that sizes a theme to a pixel height
    (`Theme.at_pixel_height`: the Themes page does it in its constructor)
    measures a face from its font file, through `imscribe.style` (and what
    it imports) and `imscribe.fontlib`: there is no window yet, so the
    library has no fonts and cannot be asked (`imscribe.typeset_metrics`).
    No page's constructor loads anything else of the core, and none loads
    an old view.

    The same measurement is what `PageContext.metrics` is for
    (`imscribe.ui.pages.face_metrics`); the last step calls it. The other
    thing that loads `imscribe.fontlib` when called is the app's font
    callback, to find one font file (`tests/test_app_typeset.py`).
    """
    environment_free = (
        "import os\n"
        "for name in [n for n in os.environ if n.startswith('IMTYPESET_')]:\n"
        "    del os.environ[name]\n"
    )
    lines = _fresh(
        environment_free + "import sys\n"
        "import imscribe.ui.app as app\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "from imscribe.ui.pages import PageContext\n"
        "context = PageContext.build()\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "made = app.App(source='# t\\n\\nwords\\n', open_tab='document:debug')\n"
        "from imscribe.primitives import Face\n"
        "assert [made.context.fonts(face) for face in Face] == [None] * len(Face)\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "for name in app.page_names():\n"
        "    made.page(name)\n"
        f"{_PRINT_LOADED}\n"
        "print('--')\n"
        "from imscribe.theme import Theme\n"
        "Theme.at_pixel_height(18.0, metrics=context.metrics)\n"
        f"{_PRINT_LOADED}"
    )
    cuts = [at for at, line in enumerate(lines) if line == "--"]
    imported = set(lines[: cuts[0]])
    built = set(lines[cuts[0] + 1 : cuts[1]])
    ran = set(lines[cuts[1] + 1 : cuts[2]])
    paged = set(lines[cuts[2] + 1 : cuts[3]])
    measured = set(lines[cuts[3] + 1 :])
    assert RUN_FLOOR == NOTHING
    assert imported & REFERENCE_CORE == THEME
    assert built & REFERENCE_CORE == RUN_FLOOR
    assert ran & REFERENCE_CORE == RUN_FLOOR, sorted((ran & REFERENCE_CORE) - RUN_FLOOR)
    for module in ("imscribe.style", "imscribe.markdown", "imscribe.ui.fonts"):
        assert module not in ran, f"building the app loaded {module}"
    beyond = (paged & REFERENCE_CORE) - RUN_FLOOR
    assert beyond in (set(), MEASURING), f"a page's constructor loaded {sorted(beyond)}"
    for module in ("imscribe.markdown", "imscribe.ui.fonts"):
        assert module not in paged, f"a page's constructor loaded {module}"
    # The one thing, when it is called: the measuring half and a font file.
    assert measured & REFERENCE_CORE == RUN_FLOOR | MEASURING


def test_every_composition_name_is_the_same_object_on_the_package() -> None:
    import imscribe.ui as package
    from imscribe.ui import composition

    assert package.__all__ == composition.__all__
    for name in (*package.__all__, *COMPOSITION_PRIVATE):
        assert getattr(package, name) is getattr(composition, name), name
    assert package.compose is composition.compose and callable(package.compose)
    assert composition.Viewport is package.Viewport
    assert composition.Hosted is package.Hosted
    assert package.Viewport.__module__ == "imscribe.ui"
    assert package.Hosted.__module__ == "imscribe.ui"
    assert set(package.__all__) <= set(dir(package))


def test_the_package_caches_nothing_of_composition() -> None:
    """
    One binding per name, composition's: a copy on the package would be a second.
    """
    import imscribe.ui as package
    from imscribe.ui import composition

    for name in (*package.__all__, *COMPOSITION_PRIVATE):
        getattr(package, name)
    kept = sorted(set(vars(package)) & set(vars(composition)) - {"Viewport", "Hosted"})
    kept = [name for name in kept if not name.startswith("__")]
    shared_imports = {"annotations", "dataclass", "Scaled", "sp_from_px", "Any", "sys"}
    assert set(kept) <= shared_imports, kept


def test_no_submodule_of_the_package_shares_a_name_with_composition() -> None:
    """
    `imscribe.ui.<x>` is a submodule or composition's `<x>`, never a choice.

    This is why the module is not `imscribe/ui/compose.py`.
    """
    from imscribe.ui import composition

    stems = {path.stem for path in (REPO / "imscribe" / "ui").glob("*.py")} | {"pages"}
    assert not (stems - {"__init__"}) & set(vars(composition))


def test_the_function_survives_importing_the_module_first() -> None:
    lines = _fresh(
        "import imscribe.ui.composition\n"
        "from imscribe.ui import compose, LayoutCache\n"
        "import imscribe.ui\n"
        "print(type(compose).__name__, compose.__module__, LayoutCache.__module__)\n"
        "print(type(imscribe.ui.composition).__name__)"
    )
    assert lines == ["function imscribe.ui.composition imscribe.ui.composition", "module"]


def test_importing_the_package_does_not_import_composition() -> None:
    lines = _fresh(
        "import sys\n"
        "import imscribe.ui\n"
        "from imscribe.ui import Viewport, Hosted\n"
        "print('imscribe.ui.composition' in sys.modules, Viewport.__module__)\n"
        "from imscribe.ui import compose\n"
        "print('imscribe.ui.composition' in sys.modules)"
    )
    assert lines == ["False imscribe.ui", "True"]


def test_replacing_a_name_on_the_package_reaches_the_code_that_reads_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `monkeypatch.setattr(imscribe.ui, "break_paragraph", spy)` is how
    `tests/test_compose.py` and `tests/test_tables.py` watch the breaker. It
    worked because the package was the namespace `compose` ran in; it works now
    because the package hands the assignment to that namespace.
    """
    import imscribe.ui as package
    from imscribe.ui import composition

    real = composition.break_paragraph

    def spy(*args: object, **kwargs: object) -> object:
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(package, "break_paragraph", spy)
    assert composition.break_paragraph is spy
    assert package.break_paragraph is spy
    assert "break_paragraph" not in vars(package)
    monkeypatch.undo()
    assert composition.break_paragraph is real
    assert package.break_paragraph is real


def test_setting_and_deleting_on_the_package_follow_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import imscribe.ui as package
    from imscribe.ui import composition

    # A name both have: set in both, since code in either may read it.
    real = package.Viewport
    monkeypatch.setattr(package, "Viewport", object)
    assert composition.Viewport is object and vars(package)["Viewport"] is object
    monkeypatch.undo()
    assert composition.Viewport is real and package.Viewport is real

    # A name neither has: composition's, as it would have been in the one
    # namespace there was, and gone again when deleted.
    package.sw1_probe = 1  # type: ignore[attr-defined]
    assert "sw1_probe" not in vars(package) and vars(composition)["sw1_probe"] == 1
    del package.sw1_probe  # type: ignore[attr-defined]
    assert "sw1_probe" not in vars(composition)
    with pytest.raises(AttributeError, match="imscribe.ui"):
        del package.sw1_probe  # type: ignore[attr-defined]
    with pytest.raises(AttributeError, match="imscribe.ui"):
        _ = package.sw1_probe  # type: ignore[attr-defined]

    # A name only composition has: deleted there, and put back.
    monkeypatch.delattr(package, "_apportioned")
    assert not hasattr(composition, "_apportioned")
    monkeypatch.undo()
    assert "_apportioned" not in vars(package)
    assert package._apportioned is composition._apportioned


def test_a_submodule_is_still_a_module_on_the_package() -> None:
    import imscribe.ui as package

    for name in ("palette", "ownership", "composition", "typeset_view", "typeset_hosts"):
        module = importlib.import_module(f"imscribe.ui.{name}")
        assert getattr(package, name) is module
        assert vars(package)[name] is module


def test_giving_a_palette_roles_loads_the_theme_and_not_the_measuring_half() -> None:
    """
    `Palette.with_roles` needs `BlockKind`, to refuse a role for a rule, and
    takes it from `imscribe.theme` when called. Until 2026-10-11 it took it from
    `imscribe.style`, which loads `STYLE`; the Themes page carried a copy
    of the merge to avoid that.
    """
    lines = _fresh(
        "import sys\n"
        "from imscribe.ui.palette import DARK_PALETTE, Palette, rgba\n"
        "print('imscribe.theme' in sys.modules)\n"
        "from imscribe.theme import BlockKind\n"
        "p = DARK_PALETTE.with_roles({BlockKind.CODE: rgba(1, 2, 3)})\n"
        "print(p.ink_for(BlockKind.CODE) == rgba(1, 2, 3), p.ink_for(BlockKind.QUOTE) == p.ink)\n"
        "try:\n"
        "    p.with_roles({BlockKind.RULE: 0})\n"
        "except ValueError:\n"
        "    print('refused')\n"
        f"{_PRINT_LOADED}"
    )
    assert lines[:3] == ["False", "True True", "refused"]
    loaded = set(lines[3:])
    assert "imscribe.style" not in loaded
    assert loaded & REFERENCE_CORE == THEME

"""
imscribe -- markdown, streams and diffs as selectable text in a Dear ImGui pane.

The text is set and drawn by the imtypeset library (a sidecar built for one
imgui-bundle wheel; `imscribe.typesetter` is the gate, and `make typeset-lib`
builds it). imscribe is what stands in front of it: a markdown reader that
writes what the library takes, a theme and a palette as data, a diff model,
and three views a host calls `draw()` on inside a window of its own
(`TypesetView`, `TypesetStreamView`, `TypesetDiffView`). **Without the library
nothing here draws**: a view raises `TypesetUnavailable`, and `reason()` has
the sentence. There is no second renderer.

Until 2026-10-12 this package was named `advtext`. The rename changed no
signature and no behaviour, and left no alias: `import advtext` is a
`ModuleNotFoundError` (`tests/test_rename.py`). What a host that held the old
name changes is in `HANDOFF-pptmstr.md`, "Renamed".

Until tranche 5 of the swap (2026-10-11) there was one: a Python
box-and-glue layout core after TeX, with its own line breaker, ship-out,
ImGui draw backend and views. The views and the backend are deleted. What is
left of the core is what the SVG litmus renderer needs (`make svg`:
`scripts/render_litmus.py`, `imscribe.backends.svg`, and the modules they
import), and it is called the reference core here. No module of the typeset
layer imports it, at import or when a theme is built, with the one exception
`tests/test_typeset_closure.py` names: sizing a theme to a pixel height
(`Theme.at_pixel_height`, `imscribe.ui.typeset_diff_view.code_size`) BEFORE
`load_fonts()` has succeeded, or without the library, measures the face
through `imscribe.fontlib`. After it the library answers
(`imscribe.typeset_metrics`), and finding the font files never needed it
(`imscribe.fontfiles`).

## The names importable from here

One small surface, listed in `__all__` below and nowhere else: the names this
project undertakes to keep importable from `imscribe` while the modules behind
them move. Everything not listed is reached through its module, with no
promise attached, and modules inside the package import each other by their
real paths.

**The rule for what is on it** (tranche 5): a name is here if and only if
the module that defines it is in the tree. A name whose module was deleted
is gone, not aliased to something similar. That removed 28 of the 94 names
there were: the old views (`BareView`, `StreamView`, `DiffView`,
`DiffFences`), the old stream (`StreamDocument`, `CommitPolicy`,
`live_theme`), the old draw backend's `draw`, the LaTeX subset
(`markdown_math`, `typeset`, `Typeset`, `Refusal`, `RefusalKind`,
`supported_commands`), colour spans and find over node material
(`ColourSpan`, `colour_text`, `find_spans`, `code_position`, `material_text`,
`TextMatch`), and `LayoutStats`.

In three groups, which `_HOMES` keeps apart:

- **The typeset layer**, what a host draws with, and what the four files
  under `examples/` import from here and from nowhere else in the package
  (they also take the module `imscribe.typesetter` itself, for `module()` and
  `unload()`; tests read their imports):
  - the library: `load_fonts` (in hello_imgui's `load_additional_fonts`),
    `ready`, `reason`; why it is not drawing as a `Kind` (`kind`), the way
    back from a failure (`reset`, then `load_fonts` again), what was found
    and by which route (`pairing`), and the same asked of a child process
    without loading anything here (`verdict`);
  - markdown: `parse_markdown` answering a `MarkdownDocument`, `MarkdownStream`
    for a source still arriving, `MarkdownConverter` and the `Description` of
    `BlockDescription`s it answers, `BlockSource` / `SourceSpan` for where a
    block came from; `ReaderOptions` for a host that wants more shown than
    CommonMark's reading shows, the same object for a parse and a stream;
  - blocks a host makes itself and hands a view in place of markdown:
    `MarkdownText`, `MarkdownCode`, `MarkdownRule`, and `MarkdownTable` with
    the `MarkdownCell` and `ColumnAlign` it cannot be built without. A
    block's `style` is `theme.style(BlockKind...)`;
  - find: `FindIndex` over a description, `Finder` (the current match and
    the marks a view takes), `Match`;
  - looks: `Theme`, `Faces`, `Face`, `Align`, `Spacing`, `BlockKind`,
    `Emphasis`; `Palette`, `DiffPalette` and the four constants; `DrawStats`;
    `Scaled`, `sp_from_px`, `px_from_sp`;
  - views: `TypesetView`, `TypesetStreamView`, `TypesetUnavailable`,
    `SetLine`; a widget inside a document (`HostFor`, `Hosted`), and fenced
    diffs as one (`TypesetDiffFences`, `HostedDiff`);
  - a diff: `Diff`, `FileDiff`, `Hunk`, `DiffRow`, `RowKind`, `FileStatus`,
    `UnifiedDiffStream`, `DiffApplyError`, `ContextUnavailable`; its view
    `TypesetDiffView` with `DiffLayout`, `SyntaxColour`, `language_for`, and
    `DiffHeader`, what `TypesetDiffView.headers` answers (a file header's
    text and whether it fit).
- **Font files**: `register_font`, `unregister_font`, `registered_fonts`
  (`imscribe.fontfiles`: the files `load_fonts` hands the library are the
  ones registered there; register before `load_fonts`),
  `em_size_for_pixel_height` (`imscribe.typeset_metrics`: the library's
  answer after `load_fonts`, the old reader's before), and the Python atlas
  loader `load_faces`, `LoadedFaces`, `TEXT_FACES`, `ALL_FACES`
  (`imscribe.ui.fonts`), which the demo app uses for one UI font when the
  library is not drawing and nothing sets text with.
- **The reference core, kept for the litmus renderer**: `build_document` and
  the block types of `imscribe.markdown`, the measuring adapters of
  `imscribe.style`, `compose` and the table functions of `imscribe.ui`, `ship`
  and its types. They are here because their modules are. None of them puts
  anything in a window.

Seven names were on the surface before and are on it now as **different
objects**, the typeset layer's of the same name, because the thing they named
was deleted and the layer has its own: `HostFor`, `SetLine`, `DiffLayout`,
`SyntaxColour`, `language_for`, `HostedDiff`, `FindIndex`. And one changed
without its old module being deleted: `Hosted` is `imscribe.ui.typeset_view`'s
protocol (what a `TypesetView` asks of a widget: `draw(palette=, width_px=)`),
no longer `imscribe.ui.Hosted` (what the deleted `BareView` asked:
`draw(fonts=, ...)`), which is still at that path for the reference
compositor's `HostBlock`. Code that imported any of the eight gets a class
of the same name and a different signature; that is a break, stated here
rather than hidden behind the name.

Not here, deliberately, and reached through their modules: the rest of the
description (`imscribe.description`: the run, cell, column and style tuples
and the enumerators, and `description_of` / `check_description` for a host
that describes its own blocks: it takes the tuples from that module anyway),
the rest of what a parse holds (`LinkRange`, `FormulaRange`,
`reader_options`), `MarkDescription` and `marks_for`, the view's other records
(`ViewStats`, `ViewColumns`, `Position`, `Range`), the diff view's frame
plan, the rest of the diff model (`Gap`, `SidePair`, `tokenize`), selection
ownership (`imscribe.ui.ownership`), the typesetter's `module`, `unload`,
`note`, `trouble`, `disable`, `font`, `unsupported`, `missing`, `REQUIRED`
and `EXIT_CODES` (a word like `font` or `module` says nothing without its
module's name in front of it), the demo app and its pages, and all of the
reference core that is not listed above (`imscribe.linebreak`, `imscribe.pack`,
`imscribe.nodes`, `imscribe.selection`, `imscribe.math`).

## Nothing is imported until it is asked for

`import imscribe` executes this file and nothing else. The names resolve on
first access through a module-level `__getattr__` (PEP 562) and are then
ordinary module attributes. Three reasons, in order of weight:

- **A host pays for what it uses.** Importing the package to read its
  version, or to reach one module directly, loads no markdown parser and no
  font code; resolving a name of the typeset layer loads none of the
  reference core.
- **ImGui, fontTools and imtypeset stay out until needed.** Measured in a
  fresh interpreter by `tests/test_facade.py`: after `import imscribe`, and
  after resolving *every* name in `__all__`, none of `imgui_bundle`,
  `fontTools` and `imtypeset` is in `sys.modules`. A view imports ImGui when
  it is first *drawn*; the library is imported when `load_fonts` or
  `imscribe.typesetter.module` is first *called*.
- **No import cycle.** Every module here does `from imscribe.x import y`,
  which imports this package first. An eager barrel would re-enter those
  modules half-initialised; a lazy one cannot.

A type checker does not run `__getattr__`, so the same names are imported
eagerly under `TYPE_CHECKING`, which costs nothing at run time and makes
`imscribe.Theme` a real type to mypy. The two lists are held equal by a test.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers; see the module docstring
    from imscribe.description import BlockDescription, Description
    from imscribe.diff import (
        ContextUnavailable,
        Diff,
        DiffApplyError,
        DiffRow,
        FileDiff,
        FileStatus,
        Hunk,
        RowKind,
        UnifiedDiffStream,
    )
    from imscribe.fontfiles import register_font, registered_fonts, unregister_font
    from imscribe.markdown import (
        Block,
        CodeBlock,
        Document,
        FormulaSpan,
        MathBuilder,
        MathRefused,
        RuleBlock,
        TableBlock,
        TextBlock,
        build_document,
        code_block,
        formula_spans,
        text_block,
    )
    from imscribe.markdown_rules import BlockSource, ColumnAlign, SourceSpan
    from imscribe.primitives import Face, Scaled, px_from_sp, sp_from_px
    from imscribe.shipout import DrawCmd, Point, ship
    from imscribe.style import MetricsResolver, char_measure, fontlib_metrics
    from imscribe.theme import Align, BlockKind, Emphasis, Faces, Spacing, Theme
    from imscribe.typeset_find import Finder, FindIndex, Match
    from imscribe.typeset_markdown import (
        MarkdownCell,
        MarkdownCode,
        MarkdownConverter,
        MarkdownDocument,
        MarkdownRule,
        MarkdownStream,
        MarkdownTable,
        MarkdownText,
        ReaderOptions,
        parse_markdown,
    )
    from imscribe.typeset_metrics import em_size_for_pixel_height
    from imscribe.typesetter import (
        Kind,
        kind,
        load_fonts,
        pairing,
        ready,
        reason,
        reset,
        verdict,
    )
    from imscribe.ui import (
        PROSE_BREAKING_TOTAL_FIT_RAGGED,
        ColumnLimits,
        ComposeParams,
        HostBlock,
        SizedTable,
        compose,
        compose_blocks,
        table_column_limits,
        table_columns,
        with_columns,
    )
    from imscribe.ui.fonts import ALL_FACES, TEXT_FACES, LoadedFaces, load_faces
    from imscribe.ui.palette import (
        DARK_DIFF_PALETTE,
        DARK_PALETTE,
        DEFAULT_DIFF_PALETTE,
        DEFAULT_PALETTE,
        DiffPalette,
        DrawStats,
        Palette,
    )
    from imscribe.ui.typeset_diff_view import (
        DiffHeader,
        DiffLayout,
        SyntaxColour,
        TypesetDiffView,
        language_for,
    )
    from imscribe.ui.typeset_hosts import HostedDiff, TypesetDiffFences
    from imscribe.ui.typeset_stream_view import TypesetStreamView
    from imscribe.ui.typeset_view import Hosted, HostFor, SetLine, TypesetUnavailable, TypesetView

__version__ = "0.2.0b1"
"""
This imscribe's version, as a host reads it at run time.

A literal, and the same string as `version` in `pyproject.toml`
(`tests/test_dist.py` holds the two equal). It is not read from the installed
metadata on purpose: an editable install keeps the metadata of the day it was
installed (this tree's `./.venv` said 0.1.0 and a floor on imgui-bundle long
after both had changed), and a frozen application may carry none.
`typesetter.pairing()["imscribe_version"]` is this string.

What the number says (an agent's decision, 2026-10-12; `docs/decisions.md`):

- `0.1.0` was imscribe with its own Python layout core. `0.2` is imscribe that
  draws through imtypeset and through nothing else: a host of 0.1 does not
  run on 0.2.
- `.devN` means NO release exists and nothing is promised from one commit to
  the next: two commits with the same string can differ in anything. That is
  why a requirement names the commit, or a file by its sha256 (`make dist`
  prints both), and never the version alone. `N` goes up when an artefact is
  cut for a host to pin, so that two artefacts a host was given never share a
  file name.
- `0.2.0b1` (2026-10-13) is the first version made for PyPI: a beta, which
  `pip` installs only when asked for (`--pre`, or the exact version). It is
  one commit, the one tagged `v0.2.0b1`.
- `0.2.0` without a suffix is for the first full release, which is the
  user's to make. From there until 1.0: the middle number changes when a
  name in `__all__` is removed or changes what it means, or when the
  imgui-bundle pin or the imtypeset line (`0.4.*` today) changes; the last
  number changes for anything else.

Not in `__all__`: it is not one of the names of the surface, and
`from imscribe import *` does not need it.
"""

_HOMES: dict[str, str] = {
    # === The typeset layer: what a host draws with ===
    # The library: its fonts into the host's atlas, whether it is drawing, and why not.
    "load_fonts": "imscribe.typesetter",
    "ready": "imscribe.typesetter",
    "reason": "imscribe.typesetter",
    # Why it is not drawing as a kind, the way back, and what was found: here, or by a child.
    "Kind": "imscribe.typesetter",
    "kind": "imscribe.typesetter",
    "reset": "imscribe.typesetter",
    "pairing": "imscribe.typesetter",
    "verdict": "imscribe.typesetter",
    # Parse: markdown in, blocks of text and runs out; or the same from a source still arriving.
    "parse_markdown": "imscribe.typeset_markdown",
    "MarkdownDocument": "imscribe.typeset_markdown",
    "MarkdownStream": "imscribe.typeset_markdown",
    "MarkdownConverter": "imscribe.typeset_markdown",
    # How it is read, where a host wants more shown than CommonMark's reading shows.
    "ReaderOptions": "imscribe.typeset_markdown",
    # The blocks, for a host that makes its own and hands them to a view.
    "MarkdownText": "imscribe.typeset_markdown",
    "MarkdownCode": "imscribe.typeset_markdown",
    "MarkdownRule": "imscribe.typeset_markdown",
    "MarkdownTable": "imscribe.typeset_markdown",
    "MarkdownCell": "imscribe.typeset_markdown",
    # Where a block came from in the source; and a table column's alignment.
    "BlockSource": "imscribe.markdown_rules",
    "SourceSpan": "imscribe.markdown_rules",
    "ColumnAlign": "imscribe.markdown_rules",
    # The description `MarkdownConverter.describe` answers, which find reads.
    "Description": "imscribe.description",
    "BlockDescription": "imscribe.description",
    # Find: every occurrence of a string in a described document, and the marks for a view.
    "Finder": "imscribe.typeset_find",
    "FindIndex": "imscribe.typeset_find",
    "Match": "imscribe.typeset_find",
    # Theme: what the blocks look like.
    "Theme": "imscribe.theme",
    "Faces": "imscribe.theme",
    "Align": "imscribe.theme",
    "Spacing": "imscribe.theme",
    "BlockKind": "imscribe.theme",
    "Emphasis": "imscribe.theme",
    # A face by role, and the one unit conversion a host cannot avoid.
    "Face": "imscribe.primitives",
    "Scaled": "imscribe.primitives",
    "sp_from_px": "imscribe.primitives",
    "px_from_sp": "imscribe.primitives",
    # Colour: a view's inks.
    "Palette": "imscribe.ui.palette",
    "DEFAULT_PALETTE": "imscribe.ui.palette",
    "DARK_PALETTE": "imscribe.ui.palette",
    "DrawStats": "imscribe.ui.palette",
    "DiffPalette": "imscribe.ui.palette",
    "DEFAULT_DIFF_PALETTE": "imscribe.ui.palette",
    "DARK_DIFF_PALETTE": "imscribe.ui.palette",
    # View: a document in a pane of the host's, selectable; and a widget drawn inside one.
    "TypesetView": "imscribe.ui.typeset_view",
    "TypesetUnavailable": "imscribe.ui.typeset_view",
    "SetLine": "imscribe.ui.typeset_view",
    "HostFor": "imscribe.ui.typeset_view",
    "Hosted": "imscribe.ui.typeset_view",
    # The same over a stream.
    "TypesetStreamView": "imscribe.ui.typeset_stream_view",
    # Diff: before and after text, or unified text, as one model.
    "Diff": "imscribe.diff",
    "FileDiff": "imscribe.diff",
    "Hunk": "imscribe.diff",
    "DiffRow": "imscribe.diff",
    "RowKind": "imscribe.diff",
    "FileStatus": "imscribe.diff",
    "UnifiedDiffStream": "imscribe.diff",
    "DiffApplyError": "imscribe.diff",
    "ContextUnavailable": "imscribe.diff",
    # Diff view: unified or side by side, in a pane of the host's.
    "TypesetDiffView": "imscribe.ui.typeset_diff_view",
    "DiffLayout": "imscribe.ui.typeset_diff_view",
    "SyntaxColour": "imscribe.ui.typeset_diff_view",
    "language_for": "imscribe.ui.typeset_diff_view",
    "DiffHeader": "imscribe.ui.typeset_diff_view",
    # Fenced diffs drawn as diff views inside a document.
    "TypesetDiffFences": "imscribe.ui.typeset_hosts",
    "HostedDiff": "imscribe.ui.typeset_hosts",
    # === Font files ===
    # The host's own files by role, which `load_fonts` hands the library
    # (`imscribe.fontfiles`: a table, no font is opened), and the size conversion
    # `Theme.at_pixel_height` applies (`imscribe.typeset_metrics`: the library's answer
    # once `load_fonts` has succeeded, the reference core's `imscribe.fontlib` before).
    # `imscribe.fontlib` has the same four names; the first three are these objects.
    "register_font": "imscribe.fontfiles",
    "unregister_font": "imscribe.fontfiles",
    "registered_fonts": "imscribe.fontfiles",
    "em_size_for_pixel_height": "imscribe.typeset_metrics",
    # The Python atlas loader. The demo app uses it for one UI font when the library is
    # not drawing (decision 6); nothing sets text with the faces it loads.
    "load_faces": "imscribe.ui.fonts",
    "LoadedFaces": "imscribe.ui.fonts",
    "TEXT_FACES": "imscribe.ui.fonts",
    "ALL_FACES": "imscribe.ui.fonts",
    # === The reference core, kept for the litmus renderer ===
    # The Python box-and-glue pipeline that `make svg` renders with
    # (`scripts/render_litmus.py`, `imscribe.backends.svg`). Nothing here reaches a
    # window: these names are here because their modules are, and for no other reason.
    # Parse to node material.
    "build_document": "imscribe.markdown",
    "text_block": "imscribe.markdown",
    "code_block": "imscribe.markdown",
    "Document": "imscribe.markdown",
    "Block": "imscribe.markdown",
    "TextBlock": "imscribe.markdown",
    "CodeBlock": "imscribe.markdown",
    "RuleBlock": "imscribe.markdown",
    "TableBlock": "imscribe.markdown",
    "MathBuilder": "imscribe.markdown",
    "MathRefused": "imscribe.markdown",
    "FormulaSpan": "imscribe.markdown",
    "formula_spans": "imscribe.markdown",
    # Measure: how a font key becomes numbers.
    "MetricsResolver": "imscribe.style",
    "fontlib_metrics": "imscribe.style",
    "char_measure": "imscribe.style",
    # Compose: blocks to a box; table column widths.
    "compose": "imscribe.ui",
    "compose_blocks": "imscribe.ui",
    "ComposeParams": "imscribe.ui",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED": "imscribe.ui",
    "with_columns": "imscribe.ui",
    "table_columns": "imscribe.ui",
    "SizedTable": "imscribe.ui",
    "ColumnLimits": "imscribe.ui",
    "table_column_limits": "imscribe.ui",
    "HostBlock": "imscribe.ui",
    # Ship: a box to draw commands.
    "ship": "imscribe.shipout",
    "Point": "imscribe.shipout",
    "DrawCmd": "imscribe.shipout",
}
"""
Each name of the surface, and the module it is fetched from.

The module that DEFINES it, where that differs from one it can also be
imported from: `Theme` is `imscribe.theme`'s and not `imscribe.style`'s, `Face`
is `imscribe.primitives`' and not `imscribe.fontmetrics`', `Hosted` and
`HostFor` are `imscribe.ui.typeset_view`'s and not `imscribe.ui.typeset_hosts`'.
They are one object under either path, and the path matters for what
resolving the name loads: through the older module it is the reference core.
The one exception is the compositor's names, fetched from the package
`imscribe.ui`, which hands out `imscribe.ui.composition`'s objects.

In three groups, and the grouping is the point: what a host draws with, the
font files, and the reference core. A name here and not in `__all__` would
resolve without being promised, and one in `__all__` and not here would be
promised and fail; a test refuses both.
"""

__all__ = [
    "ALL_FACES",
    "DARK_DIFF_PALETTE",
    "DARK_PALETTE",
    "DEFAULT_DIFF_PALETTE",
    "DEFAULT_PALETTE",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED",
    "TEXT_FACES",
    "Align",
    "Block",
    "BlockDescription",
    "BlockKind",
    "BlockSource",
    "CodeBlock",
    "ColumnAlign",
    "ColumnLimits",
    "ComposeParams",
    "ContextUnavailable",
    "Description",
    "Diff",
    "DiffApplyError",
    "DiffHeader",
    "DiffLayout",
    "DiffPalette",
    "DiffRow",
    "Document",
    "DrawCmd",
    "DrawStats",
    "Emphasis",
    "Face",
    "Faces",
    "FileDiff",
    "FileStatus",
    "FindIndex",
    "Finder",
    "FormulaSpan",
    "HostBlock",
    "HostFor",
    "Hosted",
    "HostedDiff",
    "Hunk",
    "Kind",
    "LoadedFaces",
    "MarkdownCell",
    "MarkdownCode",
    "MarkdownConverter",
    "MarkdownDocument",
    "MarkdownRule",
    "MarkdownStream",
    "MarkdownTable",
    "MarkdownText",
    "Match",
    "MathBuilder",
    "MathRefused",
    "MetricsResolver",
    "Palette",
    "Point",
    "ReaderOptions",
    "RowKind",
    "RuleBlock",
    "Scaled",
    "SetLine",
    "SizedTable",
    "SourceSpan",
    "Spacing",
    "SyntaxColour",
    "TableBlock",
    "TextBlock",
    "Theme",
    "TypesetDiffFences",
    "TypesetDiffView",
    "TypesetStreamView",
    "TypesetUnavailable",
    "TypesetView",
    "UnifiedDiffStream",
    "build_document",
    "char_measure",
    "code_block",
    "compose",
    "compose_blocks",
    "em_size_for_pixel_height",
    "fontlib_metrics",
    "formula_spans",
    "kind",
    "language_for",
    "load_faces",
    "load_fonts",
    "pairing",
    "parse_markdown",
    "px_from_sp",
    "ready",
    "reason",
    "register_font",
    "registered_fonts",
    "reset",
    "ship",
    "sp_from_px",
    "table_column_limits",
    "table_columns",
    "text_block",
    "unregister_font",
    "verdict",
    "with_columns",
]
"""
The surface. Written out rather than derived from `_HOMES` because a linter and
a type checker read `__all__` without running anything; `tests/test_facade.py`
holds the two, and the `TYPE_CHECKING` imports above, to the same set.
"""


def __getattr__(name: str) -> Any:
    """
    Resolve a name of the surface on first access, then get out of the way.

    The value is stored in the module's globals, so this runs once per name and
    every later `imscribe.Theme` is a plain attribute lookup. A name that is not
    part of the surface is an `AttributeError` naming the package, as it would
    be with no `__getattr__` at all -- which is also what keeps `hasattr` and
    `import imscribe.nosuch` honest.
    """
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(home), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """
    The surface, plus what the module really holds, so completion shows both.
    """
    return sorted({*globals(), *_HOMES})

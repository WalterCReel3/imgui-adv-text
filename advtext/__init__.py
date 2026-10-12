"""
advtext -- markdown, streams and diffs as selectable text in a Dear ImGui pane.

The text is set and drawn by the imtypeset library (a sidecar built for one
imgui-bundle wheel; `advtext.typesetter` is the gate, and `make typeset-lib`
builds it). advtext is what stands in front of it: a markdown reader that
writes what the library takes, a theme and a palette as data, a diff model,
and three views a host calls `draw()` on inside a window of its own
(`TypesetView`, `TypesetStreamView`, `TypesetDiffView`). **Without the library
nothing here draws**: a view raises `TypesetUnavailable`, and `reason()` has
the sentence. There is no second renderer.

Until tranche 5 of the swap (2026-10-11) there was one: a Python
box-and-glue layout core after TeX, with its own line breaker, ship-out,
ImGui draw backend and views. The views and the backend are deleted. What is
left of the core is what the SVG litmus renderer needs (`make svg`:
`scripts/render_litmus.py`, `advtext.backends.svg`, and the modules they
import), and it is called the reference core here. No module of the typeset
layer imports it, at import or when a theme is built, with the exceptions
`tests/test_typeset_closure.py` names: measuring a face from its font file
(`Theme.at_pixel_height`, `advtext.ui.typeset_diff_view.code_size`) and
finding the font files (`load_fonts`) go through `advtext.fontlib`, until the
library answers a face's metrics.

## The names importable from here

One small surface, listed in `__all__` below and nowhere else: the names this
project undertakes to keep importable from `advtext` while the modules behind
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
  (they also take the module `advtext.typesetter` itself, for `module()` and
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
- **Font files**: `register_font`, `unregister_font`, `registered_fonts`,
  `em_size_for_pixel_height` (`advtext.fontlib`: the files `load_fonts`
  hands the library are the ones registered there), and the Python atlas
  loader `load_faces`, `LoadedFaces`, `TEXT_FACES`, `ALL_FACES`
  (`advtext.ui.fonts`), which the demo app uses for one UI font when the
  library is not drawing and nothing sets text with.
- **The reference core, kept for the litmus renderer**: `build_document` and
  the block types of `advtext.markdown`, the measuring adapters of
  `advtext.style`, `compose` and the table functions of `advtext.ui`, `ship`
  and its types. They are here because their modules are. None of them puts
  anything in a window.

Seven names were on the surface before and are on it now as **different
objects**, the typeset layer's of the same name, because the thing they named
was deleted and the layer has its own: `HostFor`, `SetLine`, `DiffLayout`,
`SyntaxColour`, `language_for`, `HostedDiff`, `FindIndex`. And one changed
without its old module being deleted: `Hosted` is `advtext.ui.typeset_view`'s
protocol (what a `TypesetView` asks of a widget: `draw(palette=, width_px=)`),
no longer `advtext.ui.Hosted` (what the deleted `BareView` asked:
`draw(fonts=, ...)`), which is still at that path for the reference
compositor's `HostBlock`. Code that imported any of the eight gets a class
of the same name and a different signature; that is a break, stated here
rather than hidden behind the name.

Not here, deliberately, and reached through their modules: the rest of the
description (`advtext.description`: the run, cell, column and style tuples
and the enumerators, and `description_of` / `check_description` for a host
that describes its own blocks: it takes the tuples from that module anyway),
the rest of what a parse holds (`LinkRange`, `FormulaRange`,
`reader_options`), `MarkDescription` and `marks_for`, the view's other records
(`ViewStats`, `ViewColumns`, `Position`, `Range`), the diff view's frame
plan, the rest of the diff model (`Gap`, `SidePair`, `tokenize`), selection
ownership (`advtext.ui.ownership`), the typesetter's `module`, `unload`,
`note`, `trouble`, `disable`, `font`, `unsupported`, `missing`, `REQUIRED`
and `EXIT_CODES` (a word like `font` or `module` says nothing without its
module's name in front of it), the demo app and its pages, and all of the
reference core that is not listed above (`advtext.linebreak`, `advtext.pack`,
`advtext.nodes`, `advtext.selection`, `advtext.math`).

## Nothing is imported until it is asked for

`import advtext` executes this file and nothing else. The names resolve on
first access through a module-level `__getattr__` (PEP 562) and are then
ordinary module attributes. Three reasons, in order of weight:

- **A host pays for what it uses.** Importing the package to read its
  version, or to reach one module directly, loads no markdown parser and no
  font code; resolving a name of the typeset layer loads none of the
  reference core.
- **ImGui, fontTools and imtypeset stay out until needed.** Measured in a
  fresh interpreter by `tests/test_facade.py`: after `import advtext`, and
  after resolving *every* name in `__all__`, none of `imgui_bundle`,
  `fontTools` and `imtypeset` is in `sys.modules`. A view imports ImGui when
  it is first *drawn*; the library is imported when `load_fonts` or
  `advtext.typesetter.module` is first *called*.
- **No import cycle.** Every module here does `from advtext.x import y`,
  which imports this package first. An eager barrel would re-enter those
  modules half-initialised; a lazy one cannot.

A type checker does not run `__getattr__`, so the same names are imported
eagerly under `TYPE_CHECKING`, which costs nothing at run time and makes
`advtext.Theme` a real type to mypy. The two lists are held equal by a test.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers; see the module docstring
    from advtext.description import BlockDescription, Description
    from advtext.diff import (
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
    from advtext.fontlib import (
        em_size_for_pixel_height,
        register_font,
        registered_fonts,
        unregister_font,
    )
    from advtext.markdown import (
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
    from advtext.markdown_rules import BlockSource, ColumnAlign, SourceSpan
    from advtext.primitives import Face, Scaled, px_from_sp, sp_from_px
    from advtext.shipout import DrawCmd, Point, ship
    from advtext.style import MetricsResolver, char_measure, fontlib_metrics
    from advtext.theme import Align, BlockKind, Emphasis, Faces, Spacing, Theme
    from advtext.typeset_find import Finder, FindIndex, Match
    from advtext.typeset_markdown import (
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
    from advtext.typesetter import (
        Kind,
        kind,
        load_fonts,
        pairing,
        ready,
        reason,
        reset,
        verdict,
    )
    from advtext.ui import (
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
    from advtext.ui.fonts import ALL_FACES, TEXT_FACES, LoadedFaces, load_faces
    from advtext.ui.palette import (
        DARK_DIFF_PALETTE,
        DARK_PALETTE,
        DEFAULT_DIFF_PALETTE,
        DEFAULT_PALETTE,
        DiffPalette,
        DrawStats,
        Palette,
    )
    from advtext.ui.typeset_diff_view import (
        DiffHeader,
        DiffLayout,
        SyntaxColour,
        TypesetDiffView,
        language_for,
    )
    from advtext.ui.typeset_hosts import HostedDiff, TypesetDiffFences
    from advtext.ui.typeset_stream_view import TypesetStreamView
    from advtext.ui.typeset_view import Hosted, HostFor, SetLine, TypesetUnavailable, TypesetView

_HOMES: dict[str, str] = {
    # === The typeset layer: what a host draws with ===
    # The library: its fonts into the host's atlas, whether it is drawing, and why not.
    "load_fonts": "advtext.typesetter",
    "ready": "advtext.typesetter",
    "reason": "advtext.typesetter",
    # Why it is not drawing as a kind, the way back, and what was found: here, or by a child.
    "Kind": "advtext.typesetter",
    "kind": "advtext.typesetter",
    "reset": "advtext.typesetter",
    "pairing": "advtext.typesetter",
    "verdict": "advtext.typesetter",
    # Parse: markdown in, blocks of text and runs out; or the same from a source still arriving.
    "parse_markdown": "advtext.typeset_markdown",
    "MarkdownDocument": "advtext.typeset_markdown",
    "MarkdownStream": "advtext.typeset_markdown",
    "MarkdownConverter": "advtext.typeset_markdown",
    # How it is read, where a host wants more shown than CommonMark's reading shows.
    "ReaderOptions": "advtext.typeset_markdown",
    # The blocks, for a host that makes its own and hands them to a view.
    "MarkdownText": "advtext.typeset_markdown",
    "MarkdownCode": "advtext.typeset_markdown",
    "MarkdownRule": "advtext.typeset_markdown",
    "MarkdownTable": "advtext.typeset_markdown",
    "MarkdownCell": "advtext.typeset_markdown",
    # Where a block came from in the source; and a table column's alignment.
    "BlockSource": "advtext.markdown_rules",
    "SourceSpan": "advtext.markdown_rules",
    "ColumnAlign": "advtext.markdown_rules",
    # The description `MarkdownConverter.describe` answers, which find reads.
    "Description": "advtext.description",
    "BlockDescription": "advtext.description",
    # Find: every occurrence of a string in a described document, and the marks for a view.
    "Finder": "advtext.typeset_find",
    "FindIndex": "advtext.typeset_find",
    "Match": "advtext.typeset_find",
    # Theme: what the blocks look like.
    "Theme": "advtext.theme",
    "Faces": "advtext.theme",
    "Align": "advtext.theme",
    "Spacing": "advtext.theme",
    "BlockKind": "advtext.theme",
    "Emphasis": "advtext.theme",
    # A face by role, and the one unit conversion a host cannot avoid.
    "Face": "advtext.primitives",
    "Scaled": "advtext.primitives",
    "sp_from_px": "advtext.primitives",
    "px_from_sp": "advtext.primitives",
    # Colour: a view's inks.
    "Palette": "advtext.ui.palette",
    "DEFAULT_PALETTE": "advtext.ui.palette",
    "DARK_PALETTE": "advtext.ui.palette",
    "DrawStats": "advtext.ui.palette",
    "DiffPalette": "advtext.ui.palette",
    "DEFAULT_DIFF_PALETTE": "advtext.ui.palette",
    "DARK_DIFF_PALETTE": "advtext.ui.palette",
    # View: a document in a pane of the host's, selectable; and a widget drawn inside one.
    "TypesetView": "advtext.ui.typeset_view",
    "TypesetUnavailable": "advtext.ui.typeset_view",
    "SetLine": "advtext.ui.typeset_view",
    "HostFor": "advtext.ui.typeset_view",
    "Hosted": "advtext.ui.typeset_view",
    # The same over a stream.
    "TypesetStreamView": "advtext.ui.typeset_stream_view",
    # Diff: before and after text, or unified text, as one model.
    "Diff": "advtext.diff",
    "FileDiff": "advtext.diff",
    "Hunk": "advtext.diff",
    "DiffRow": "advtext.diff",
    "RowKind": "advtext.diff",
    "FileStatus": "advtext.diff",
    "UnifiedDiffStream": "advtext.diff",
    "DiffApplyError": "advtext.diff",
    "ContextUnavailable": "advtext.diff",
    # Diff view: unified or side by side, in a pane of the host's.
    "TypesetDiffView": "advtext.ui.typeset_diff_view",
    "DiffLayout": "advtext.ui.typeset_diff_view",
    "SyntaxColour": "advtext.ui.typeset_diff_view",
    "language_for": "advtext.ui.typeset_diff_view",
    "DiffHeader": "advtext.ui.typeset_diff_view",
    # Fenced diffs drawn as diff views inside a document.
    "TypesetDiffFences": "advtext.ui.typeset_hosts",
    "HostedDiff": "advtext.ui.typeset_hosts",
    # === Font files (decision 5 of .concerns/lead--tranche-5.md) ===
    # The host's own files by role, which `load_fonts` hands the library, and the size
    # conversion `Theme.at_pixel_height` applies. `advtext.fontlib` is the reference
    # core's and stays until imtypeset answers a face's metrics.
    "register_font": "advtext.fontlib",
    "unregister_font": "advtext.fontlib",
    "registered_fonts": "advtext.fontlib",
    "em_size_for_pixel_height": "advtext.fontlib",
    # The Python atlas loader. The demo app uses it for one UI font when the library is
    # not drawing (decision 6); nothing sets text with the faces it loads.
    "load_faces": "advtext.ui.fonts",
    "LoadedFaces": "advtext.ui.fonts",
    "TEXT_FACES": "advtext.ui.fonts",
    "ALL_FACES": "advtext.ui.fonts",
    # === The reference core, kept for the litmus renderer ===
    # The Python box-and-glue pipeline that `make svg` renders with
    # (`scripts/render_litmus.py`, `advtext.backends.svg`). Nothing here reaches a
    # window: these names are here because their modules are, and for no other reason.
    # Parse to node material.
    "build_document": "advtext.markdown",
    "text_block": "advtext.markdown",
    "code_block": "advtext.markdown",
    "Document": "advtext.markdown",
    "Block": "advtext.markdown",
    "TextBlock": "advtext.markdown",
    "CodeBlock": "advtext.markdown",
    "RuleBlock": "advtext.markdown",
    "TableBlock": "advtext.markdown",
    "MathBuilder": "advtext.markdown",
    "MathRefused": "advtext.markdown",
    "FormulaSpan": "advtext.markdown",
    "formula_spans": "advtext.markdown",
    # Measure: how a font key becomes numbers.
    "MetricsResolver": "advtext.style",
    "fontlib_metrics": "advtext.style",
    "char_measure": "advtext.style",
    # Compose: blocks to a box; table column widths.
    "compose": "advtext.ui",
    "compose_blocks": "advtext.ui",
    "ComposeParams": "advtext.ui",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED": "advtext.ui",
    "with_columns": "advtext.ui",
    "table_columns": "advtext.ui",
    "SizedTable": "advtext.ui",
    "ColumnLimits": "advtext.ui",
    "table_column_limits": "advtext.ui",
    "HostBlock": "advtext.ui",
    # Ship: a box to draw commands.
    "ship": "advtext.shipout",
    "Point": "advtext.shipout",
    "DrawCmd": "advtext.shipout",
}
"""
Each name of the surface, and the module it is fetched from.

The module that DEFINES it, where that differs from one it can also be
imported from: `Theme` is `advtext.theme`'s and not `advtext.style`'s, `Face`
is `advtext.primitives`' and not `advtext.fontmetrics`', `Hosted` and
`HostFor` are `advtext.ui.typeset_view`'s and not `advtext.ui.typeset_hosts`'.
They are one object under either path, and the path matters for what
resolving the name loads: through the older module it is the reference core.
The one exception is the compositor's names, fetched from the package
`advtext.ui`, which hands out `advtext.ui.composition`'s objects.

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
    every later `advtext.Theme` is a plain attribute lookup. A name that is not
    part of the surface is an `AttributeError` naming the package, as it would
    be with no `__getattr__` at all -- which is also what keeps `hasattr` and
    `import advtext.nosuch` honest.
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

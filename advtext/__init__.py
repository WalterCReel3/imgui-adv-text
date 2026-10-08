"""
advtext -- TeX's box-and-glue layout model, rendered by Dear ImGui.

A document is a tree of boxes, glue, kerns and penalties. `hpack` and `vpack`
measure it, a total-fit line breaker over badness and demerits cuts justified
text into lines (text that is not justified is filled first-fit at its natural
spacing: `advtext.linebreak`, `LineBreakParams.first_fit`), and ship-out
flattens the result to absolute glyph positions. Because we
own every position, hit testing is arithmetic rather than a missing widget
feature -- selectable text is the return on doing layout from scratch.

The layout core imports neither ImGui nor fontTools. It consumes a metrics
interface and emits draw commands; an SVG backend and an ImDrawList backend
consume those. A layout two unrelated backends can render has had its geometry
separated from its drawing, which is the property selection depends on.

Deliberately out of scope, so nobody looks for them: hyphenation, `ext_tag`
extensible glyph assembly, delta nodes in `try_break`, `\\mathchoice`, `\\halign`,
ligature reconstruction, page breaking, bidi, complex shaping and CJK line
breaking. `docs/decisions.md` gives the reason for each, along with the
environment constraints that forced the two-backend split, and it is the
document every module here is written against.

Also out of scope, and refused rather than merely absent: a LaTeX parser. What
there is instead is an extension on top of the engine, `advtext.mathtext`, which
turns a fixed subset of `$...$` source into the engine's atoms and answers
anything outside it with a reason (no macros, no environments, no matrices);
`build_document(..., math=markdown_math())` is how a host turns it on, and it
is off unless asked for. Two things this list used to imply and no longer does,
both since `docs/adoption-plan.md`: a document need not be a whole file
(`advtext.stream` takes it a piece at a time), and the demo's page is not the
only view (`advtext.ui.bare_view`, `advtext.ui.stream_view`,
`advtext.ui.diff_view`). That plan's first section says what of this has been
run in a window and what nobody has looked at.

## The names importable from here, and why there are now some

This docstring used to end "No re-export barrel: import from the module that
defines the thing", and `__all__` was empty. That was the right rule for a
project whose only consumer was its own demo: every import said where a thing
lived, and nothing could be reached two ways.

It is the wrong rule for a host. `docs/adoption-plan.md` makes this a library
another application embeds, and what that application needs -- parse, theme,
compose, ship, draw, load fonts -- was spread over seven modules whose names
are this project's internal structure. A host that imports
`advtext.backends.imgui_draw.draw` has pinned that structure, and the next
refactor here breaks it. So there is one **small** surface, listed in `__all__`
below and nowhere else, and it is the set of names this project undertakes to
keep importable from `advtext` while the modules behind them move.

The old rule still holds for everything *inside* the package and for everything
not listed: modules here import each other by their real paths, and a name that
is not in `__all__` is reached through its module, with no promise attached.
The surface is deliberately not "everything public". It is what
`examples/minimal.py` needs to put a markdown string in a window, plus the two
block constructors and the font registry, and that example imports from nowhere
else -- `tests/test_examples.py` reads its imports to hold it to that.

Each public piece that landed after that added its own names here, so that the
examples built on it can keep to this one import: the embeddable view
(`BareView`, its source map `BlockSource` / `SourceSpan`, and `SetLine`, the
record `BareView.set_lines` answers with), the streaming document and its view
(`StreamDocument`, `CommitPolicy`, `live_theme`, `StreamView`), a dark palette
(`DARK_PALETTE`), a host's colour spans (`ColourSpan`, `colour_text`,
`find_spans`, `code_position`, `material_text`), and what a host needs to give a
table its column widths or to ask for the older total-fit ragged breaking
(`with_columns`, `table_columns`, `SizedTable`, `ComposeParams`,
`PROSE_BREAKING_TOTAL_FIT_RAGGED`). `examples/theme_gallery.py`,
`examples/stream_replay.py` and `examples/chat_transcript.py` import from here
and nowhere else in the package, and a test reads each one's imports to hold it
to that.

The second build (`.concerns/lead--demo-tasks.md`) added three more groups, and
`examples/diff_minimal.py` is held to this one import the same way:

- **A diff.** The model (`Diff` with `from_texts`, `from_edits` and
  `from_unified`; `FileDiff`, `Hunk`, `DiffRow`, `RowKind`, `FileStatus`;
  `UnifiedDiffStream` for text still arriving; the two errors `DiffApplyError`
  and `ContextUnavailable`), its view (`DiffView`, `DiffLayout`, the
  `SyntaxColour` callable a host supplies and `language_for`, which reads a
  language off a label), and its colours (`DiffPalette`, `DEFAULT_DIFF_PALETTE`,
  `DARK_DIFF_PALETTE`; a `Palette` carries one as `.diff`).
- **A widget inside a document.** `HostFor` is the hook a view is given,
  `Hosted` what it returns, `HostBlock` the block the rectangle is reserved
  for; `DiffFences` is the ready-made hook that draws fenced `diff` blocks with
  a `DiffView`, and `HostedDiff` is what it hands back.
- **Mathematics in text.** `markdown_math()` is the value of the `math=`
  argument of `build_document` and `StreamDocument`; `MathBuilder` is that
  argument's type and `MathRefused` what a builder of the host's own returns
  to decline; `formula_spans` and `FormulaSpan` say what was set and what was
  refused, and why. For a formula on its own: `typeset`, answering a `Typeset`
  or a `Refusal` with its `RefusalKind`, and `supported_commands`.

And four things pages of the demo could only reach privately until
C-viewapi made them public: `FindIndex` and `TextMatch` (search over a
document's blocks), `LayoutStats` (what the last layout built and reused),
`ColumnLimits` and `table_column_limits` (how narrow a table's columns may go).

Not here, deliberately, and reached through their modules with no promise:
selection and culling types (`advtext.selection`, `advtext.ui.units`), the
caches, the line-breaking parameters other than `ComposeParams`, the multi-run
draw (`advtext.backends.imgui_draw.draw_runs`; a host calls a view's `draw`),
the demo's `DocumentView`, its pages and `PageError`. Also not here:
`advtext.mathtext.parse` and `set_formula` (the name `advtext.parse` would read
as the markdown parser, and `typeset` is the pair of them that never raises);
the math engine's atoms (`advtext.math`), which a host building formulas by
hand imports from there; the rest of the diff model (`Gap`, `SidePair`,
`tokenize` and the tuning constants) and of the view's frame plan (`FramePlan`,
`Region`, `RowInfo`, `DiffMetrics`), which tests and the demo read and an
embedding host has not needed; and `SELECTION_OWNERSHIP` / `granularity_for`
(`advtext.ui.bare_view`), which only a host writing a selectable widget of its
own wants -- C-viewapi suggested them and C-facade left them out as the names
most likely to change shape, a decision recorded in
`.concerns/C-facade--builder--result.md`.

## Nothing is imported until it is asked for

`import advtext` executes this file and nothing else. The names resolve on
first access through a module-level `__getattr__` (PEP 562) and are then
ordinary module attributes. Three reasons, in order of weight:

- **A host pays for what it uses.** Importing the package to read its version,
  or to reach one module directly, loads no markdown parser and no font code.
- **ImGui and fontTools stay out until needed.** The layout core's claim to
  import neither would be empty if the package's front door imported both.
  Measured in a fresh interpreter by `tests/test_facade.py`: after
  `import advtext`, and after resolving *every* name in `__all__`, neither
  `imgui_bundle` nor `fontTools` is in `sys.modules`. `draw` imports ImGui when
  it is first *called*; a face is opened with fontTools when it is first
  *measured*.
- **No import cycle.** Every module here does `from advtext.x import y`, which
  imports this package first. An eager barrel would re-enter those modules
  half-initialised; a lazy one cannot.

A type checker does not run `__getattr__`, so the same names are imported
eagerly under `TYPE_CHECKING`, which costs nothing at run time and makes
`advtext.Theme` a real type to mypy. The two lists are held equal by a test.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers; see the module docstring
    from advtext.backends.imgui_draw import (
        DARK_DIFF_PALETTE,
        DARK_PALETTE,
        DEFAULT_DIFF_PALETTE,
        DEFAULT_PALETTE,
        DiffPalette,
        DrawStats,
        Palette,
        draw,
    )
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
    from advtext.fontmetrics import Face
    from advtext.markdown import (
        Block,
        BlockSource,
        CodeBlock,
        Document,
        FormulaSpan,
        MathBuilder,
        MathRefused,
        RuleBlock,
        SourceSpan,
        TableBlock,
        TextBlock,
        build_document,
        code_block,
        formula_spans,
        text_block,
    )
    from advtext.mathtext import (
        Refusal,
        RefusalKind,
        Typeset,
        markdown_math,
        supported_commands,
        typeset,
    )
    from advtext.shipout import DrawCmd, Point, ship
    from advtext.spans import (
        ColourSpan,
        FindIndex,
        TextMatch,
        code_position,
        colour_text,
        find_spans,
        material_text,
    )
    from advtext.stream import CommitPolicy, StreamDocument, live_theme
    from advtext.style import (
        Align,
        BlockKind,
        Emphasis,
        Faces,
        MetricsResolver,
        Spacing,
        Theme,
        char_measure,
        fontlib_metrics,
    )
    from advtext.ui import (
        PROSE_BREAKING_TOTAL_FIT_RAGGED,
        ColumnLimits,
        ComposeParams,
        HostBlock,
        Hosted,
        SizedTable,
        compose,
        compose_blocks,
        table_column_limits,
        table_columns,
        with_columns,
    )
    from advtext.ui.bare_view import BareView, HostFor, SetLine
    from advtext.ui.diff_view import (
        DiffFences,
        DiffLayout,
        DiffView,
        HostedDiff,
        SyntaxColour,
        language_for,
    )
    from advtext.ui.fonts import ALL_FACES, TEXT_FACES, LoadedFaces, load_faces
    from advtext.ui.stream_view import StreamView
    from advtext.ui.units import LayoutStats
    from advtext.units import Scaled, px_from_sp, sp_from_px

_HOMES: dict[str, str] = {
    # Parse: markdown in, or plain text in, blocks out.
    "build_document": "advtext.markdown",
    "text_block": "advtext.markdown",
    "code_block": "advtext.markdown",
    "Document": "advtext.markdown",
    "Block": "advtext.markdown",
    "TextBlock": "advtext.markdown",
    "CodeBlock": "advtext.markdown",
    "RuleBlock": "advtext.markdown",
    "TableBlock": "advtext.markdown",
    "BlockSource": "advtext.markdown",
    "SourceSpan": "advtext.markdown",
    # Stream: the same blocks from a source that arrives a piece at a time.
    "StreamDocument": "advtext.stream",
    "CommitPolicy": "advtext.stream",
    "live_theme": "advtext.stream",
    # Mathematics in text: the `math=` switch of the two above, and what it reports.
    "markdown_math": "advtext.mathtext",
    "MathBuilder": "advtext.markdown",
    "MathRefused": "advtext.markdown",
    "FormulaSpan": "advtext.markdown",
    "formula_spans": "advtext.markdown",
    "typeset": "advtext.mathtext",
    "Typeset": "advtext.mathtext",
    "Refusal": "advtext.mathtext",
    "RefusalKind": "advtext.mathtext",
    "supported_commands": "advtext.mathtext",
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
    # Theme: what the blocks look like.
    "Theme": "advtext.style",
    "Faces": "advtext.style",
    "Align": "advtext.style",
    "Spacing": "advtext.style",
    "BlockKind": "advtext.style",
    "Emphasis": "advtext.style",
    "Face": "advtext.fontmetrics",
    # Measure: how a font key becomes numbers.
    "MetricsResolver": "advtext.style",
    "fontlib_metrics": "advtext.style",
    "char_measure": "advtext.style",
    # Compose and ship: blocks to a box, a box to draw commands.
    "compose": "advtext.ui",
    "compose_blocks": "advtext.ui",
    "ComposeParams": "advtext.ui",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED": "advtext.ui",
    # Tables: column widths a host supplies, and the ones composition chose.
    "with_columns": "advtext.ui",
    "table_columns": "advtext.ui",
    "SizedTable": "advtext.ui",
    "ColumnLimits": "advtext.ui",
    "table_column_limits": "advtext.ui",
    "ship": "advtext.shipout",
    "Point": "advtext.shipout",
    "DrawCmd": "advtext.shipout",
    # Draw: commands onto an ImDrawList.
    "draw": "advtext.backends.imgui_draw",
    "Palette": "advtext.backends.imgui_draw",
    "DEFAULT_PALETTE": "advtext.backends.imgui_draw",
    "DARK_PALETTE": "advtext.backends.imgui_draw",
    "DrawStats": "advtext.backends.imgui_draw",
    "DiffPalette": "advtext.backends.imgui_draw",
    "DEFAULT_DIFF_PALETTE": "advtext.backends.imgui_draw",
    "DARK_DIFF_PALETTE": "advtext.backends.imgui_draw",
    # View: a document in a pane of the host's, selectable, nothing behind it.
    "BareView": "advtext.ui.bare_view",
    "SetLine": "advtext.ui.bare_view",
    "StreamView": "advtext.ui.stream_view",
    "LayoutStats": "advtext.ui.units",
    # Diff view: unified or side by side, in a pane of the host's.
    "DiffView": "advtext.ui.diff_view",
    "DiffLayout": "advtext.ui.diff_view",
    "SyntaxColour": "advtext.ui.diff_view",
    "language_for": "advtext.ui.diff_view",
    # Hosted blocks: a widget drawn inside a document, and fenced diffs as one.
    "HostFor": "advtext.ui.bare_view",
    "Hosted": "advtext.ui",
    "HostBlock": "advtext.ui",
    "DiffFences": "advtext.ui.diff_view",
    "HostedDiff": "advtext.ui.diff_view",
    # Colour: a host's spans for syntax and find hits, in a block's own coordinates.
    "ColourSpan": "advtext.spans",
    "code_position": "advtext.spans",
    "colour_text": "advtext.spans",
    "find_spans": "advtext.spans",
    "material_text": "advtext.spans",
    # Find: every occurrence of a string in a document's blocks.
    "FindIndex": "advtext.spans",
    "TextMatch": "advtext.spans",
    # Fonts: onto the host's atlas, and the host's own files.
    "load_faces": "advtext.ui.fonts",
    "LoadedFaces": "advtext.ui.fonts",
    "TEXT_FACES": "advtext.ui.fonts",
    "ALL_FACES": "advtext.ui.fonts",
    "register_font": "advtext.fontlib",
    "unregister_font": "advtext.fontlib",
    "registered_fonts": "advtext.fontlib",
    "em_size_for_pixel_height": "advtext.fontlib",
    # Units: the one conversion a host cannot avoid.
    "Scaled": "advtext.units",
    "sp_from_px": "advtext.units",
    "px_from_sp": "advtext.units",
}
"""
Each name of the surface, and the module that defines it.

Where each name lives. Grouped in the order a host uses them, which is also the
order of the pipeline. A name here and not in `__all__` would resolve without
being promised, and one in `__all__` and not here would be promised and fail;
a test refuses both.
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
    "BareView",
    "Block",
    "BlockKind",
    "BlockSource",
    "CodeBlock",
    "ColourSpan",
    "ColumnLimits",
    "CommitPolicy",
    "ComposeParams",
    "ContextUnavailable",
    "Diff",
    "DiffApplyError",
    "DiffFences",
    "DiffLayout",
    "DiffPalette",
    "DiffRow",
    "DiffView",
    "Document",
    "DrawCmd",
    "DrawStats",
    "Emphasis",
    "Face",
    "Faces",
    "FileDiff",
    "FileStatus",
    "FindIndex",
    "FormulaSpan",
    "HostBlock",
    "HostFor",
    "Hosted",
    "HostedDiff",
    "Hunk",
    "LayoutStats",
    "LoadedFaces",
    "MathBuilder",
    "MathRefused",
    "MetricsResolver",
    "Palette",
    "Point",
    "Refusal",
    "RefusalKind",
    "RowKind",
    "RuleBlock",
    "Scaled",
    "SetLine",
    "SizedTable",
    "SourceSpan",
    "Spacing",
    "StreamDocument",
    "StreamView",
    "SyntaxColour",
    "TableBlock",
    "TextBlock",
    "TextMatch",
    "Theme",
    "Typeset",
    "UnifiedDiffStream",
    "build_document",
    "char_measure",
    "code_block",
    "code_position",
    "colour_text",
    "compose",
    "compose_blocks",
    "draw",
    "em_size_for_pixel_height",
    "find_spans",
    "fontlib_metrics",
    "formula_spans",
    "language_for",
    "live_theme",
    "load_faces",
    "markdown_math",
    "material_text",
    "px_from_sp",
    "register_font",
    "registered_fonts",
    "ship",
    "sp_from_px",
    "supported_commands",
    "table_column_limits",
    "table_columns",
    "text_block",
    "typeset",
    "unregister_font",
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

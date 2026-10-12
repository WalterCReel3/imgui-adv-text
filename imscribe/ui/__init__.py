r"""
The UI package: two types of its own, and the door to composition.

Importing this package, which importing anything under `imscribe.ui.` does
first, loads `imscribe.primitives` and nothing else of imscribe. Until 2026-10-10 this
file *was* the compositor (`compose`, `LayoutCache`, the tables), so every
module under `imscribe.ui.` loaded the line breaker and the selection model
whether it used them or not, the views that set their text through imtypeset
included. Composition is now `imscribe.ui.composition`, and
`tests/test_typeset_closure.py` holds what importing each typeset module loads.

**Every name that was here still is**: `from imscribe.ui import compose`,
`imscribe.ui.LayoutCache`, `imscribe.ui._table_boxes` all work and give the very
object `imscribe.ui.composition` defines. The first such lookup imports that
module; nothing is copied into this one. So that a caller who *replaces* a
name here (a test's `monkeypatch.setattr(imscribe.ui, "break_paragraph", spy)`)
still reaches the code that reads it, setting or deleting a name composition
has sets or deletes it there. That is what `_Package` below is, and the one
piece of machinery in this file.

**A name that is a submodule is never composition's.** `from imscribe.ui import
typeset_view` makes Python ask this package for the attribute `typeset_view`
*before* it tries the submodule (`hasattr` first, the import only if that
fails). Until 2026-10-11 that question, like every other missing name, was
answered by importing composition, so the `from` form of importing any
module under here loaded the line breaker and the selection model, and only
the `import imscribe.ui.typeset_view` form did not. `_is_submodule` is asked
first now: a module or package found on this package's `__path__` is reported
as not here yet, which is the answer the import system is waiting for, and
composition is not imported to give it.

Two types are defined here and not there, and composition imports them from
here:

- `Viewport`, because it is arithmetic over scaled points alone and a view
  that composes nothing still has a visible band.
- `Hosted`, the protocol of a widget drawn in the place of a block, which
  imports nothing. `HostBlock`, its other half, is a `CodeBlock` and so stays
  with composition, where it is laid out.

`imscribe.ui.composition` is not named `compose` because `imscribe.ui.compose`
is the function: a submodule of that name would replace it on this package the
moment it was imported.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any, Protocol

from imscribe.primitives import DEFAULT_PX_PER_INCH, Scaled, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - a type checker does not run `_Package`
    from imscribe.ui.composition import (
        HSS,
        PROSE_BREAKING,
        PROSE_BREAKING_BOUNDED,
        PROSE_BREAKING_TOTAL_FIT_RAGGED,
        RAGGED_RIGHT,
        CacheStats,
        ColumnLimits,
        CommandIndex,
        ComposedRun,
        ComposeParams,
        HostBlock,
        LayoutCache,
        RunComposer,
        SizedTable,
        TableMeasure,
        block_runs,
        compose,
        compose_blocks,
        prev_depth_after,
        run_gap,
        table_column_limits,
        table_columns,
        table_natural_widths,
        visible_rects,
        with_columns,
    )

__all__ = [
    "HSS",
    "PROSE_BREAKING",
    "PROSE_BREAKING_BOUNDED",
    "PROSE_BREAKING_TOTAL_FIT_RAGGED",
    "RAGGED_RIGHT",
    "CacheStats",
    "ColumnLimits",
    "CommandIndex",
    "ComposeParams",
    "ComposedRun",
    "HostBlock",
    "Hosted",
    "LayoutCache",
    "RunComposer",
    "SizedTable",
    "TableMeasure",
    "Viewport",
    "block_runs",
    "compose",
    "compose_blocks",
    "prev_depth_after",
    "run_gap",
    "table_column_limits",
    "table_columns",
    "table_natural_widths",
    "visible_rects",
    "with_columns",
]


@dataclass(frozen=True, slots=True)
class Viewport:
    """
    The band of a document that is on screen, in **document** scaled points.

    Document coordinates and not screen ones: everything below `compose` works in
    the document's own space, where zero is the top of the first line and y grows
    downward, and converting once at the edge is what keeps the culling arithmetic
    testable with no window anywhere near it.

    Half-open, `[top, bottom)`, like every other range in this project.
    """

    top: Scaled
    bottom: Scaled

    @classmethod
    def of_pixels(
        cls,
        top_px: float,
        height_px: float,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        overscan_px: float = 0.0,
    ) -> Viewport:
        """
        A viewport from a scroll offset and a visible height, both in pixels.

        `overscan_px` widens the band at both ends. Zero is correct for a static
        frame -- `CommandIndex` bounds a glyph by its line box, and `hpack` takes
        the line's height as a maximum over its contents' *ink*, so nothing a line
        contains can extend past the extent the index gives it. It exists for a
        caller that wants material ready before a scroll reaches it, which is a
        different question from correctness and is the caller's to answer.
        """
        return cls(
            top=sp_from_px(top_px - overscan_px, px_per_inch),
            bottom=sp_from_px(top_px + height_px + overscan_px, px_per_inch),
        )

    def covers(self, top: Scaled, bottom: Scaled) -> bool:
        """
        Whether `[top, bottom)` overlaps this viewport at all.
        """
        return bottom > self.top and top < self.bottom


class Hosted(Protocol):
    """
    Something a host draws in the place of one block: the other half of `HostBlock`.

    Three things, and `imscribe.ui.diff_view.DiffView` already has the shape of
    the first two, which is where they came from:

    - `height_for(width_px)` is the height, in pixels, it will occupy at that
      width. The layout reserves exactly that, and the view asks again every
      frame, so a widget that grows (a diff still arriving, context expanded
      by a click) is given its new height on the frame it reports it.
    - `draw(fonts=, palette=, width_px=)` draws at ImGui's cursor in the
      current window, like any view here. It is called on the frames its
      rectangle meets the window and not on the others.
    - `text` is what a selection *running across* the widget copies in its
      place (`imscribe.ui.units.UnitModel.separators_within`), and what
      `BareView.block_text` gives for the block. The empty string copies
      nothing.

    One more, optional and so not part of the protocol: `handle_keys()`, if
    the widget has it, is called on the frames `draw` is *not* -- the widget
    is out of the window -- so that a widget which owns the current selection
    can still answer Ctrl+C.
    """

    def height_for(self, width_px: float) -> float: ...

    def draw(self, *, fonts: Any, palette: Any = None, width_px: float | None = None) -> object: ...

    @property
    def text(self) -> str: ...


def _composition() -> ModuleType:
    """
    `imscribe.ui.composition`, imported on first use.

    Through `sys.modules` on every call rather than kept in a global: the
    lookup is one dictionary read, and a global would be one more name for
    `_Package.__setattr__` to step around.
    """
    module = sys.modules.get("imscribe.ui.composition")
    if module is None:
        import importlib

        module = importlib.import_module("imscribe.ui.composition")
    return module


def _is_submodule(name: str) -> bool:
    """
    Whether `imscribe.ui.<name>` is a module or package on this package's path.

    Asked of the path finder and not of `sys.modules`: the question comes
    from `from imscribe.ui import <name>` *before* the submodule is imported,
    so it is not in `sys.modules` yet. Finding a spec imports nothing.
    """
    if not name.isidentifier():
        return False
    from importlib.machinery import PathFinder

    return PathFinder.find_spec(f"{__name__}.{name}", __path__) is not None


class _Package(ModuleType):
    """
    This package's own type: names it does not have are composition's.

    - **Reading** a name this module does not define asks
      `imscribe.ui.composition` for it, importing that on the first such read
      -- unless the name is a submodule of this package that has not been
      imported yet, which is refused without importing anything (the module
      docstring has why).
      Nothing is cached here, so there is one binding of each name and it is
      composition's: `imscribe.ui.compose is imscribe.ui.composition.compose`,
      and a name rebound there is seen here.
    - **Setting** a name sets it *there*, unless this file defines it, and
      then it is set here and, if composition imported it, there too. Before
      the move a caller who set `imscribe.ui.break_paragraph` changed what
      `compose` called, because they were one namespace; this keeps that
      true, and keeps this module from growing a second binding of anything
      (a name deleted and put back, as `monkeypatch.delattr` does, goes back
      where it was). A module is always set here: that is the import system
      recording a submodule (`imscribe.ui.units`). Dunder names likewise.
    - **Deleting** follows setting.

    A name neither module has raises `AttributeError` naming this package, as
    it always did.
    """

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")
        # Only while composition is not loaded: once it is, a name it lacks is
        # refused below anyway, and the path is not consulted on any read.
        if "imscribe.ui.composition" not in sys.modules and _is_submodule(name):
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")
        try:
            return getattr(_composition(), name)
        except AttributeError:
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}") from None

    def __setattr__(self, name: str, value: Any) -> None:
        if isinstance(value, ModuleType) or (name.startswith("__") and name.endswith("__")):
            super().__setattr__(name, value)
            return
        own = name in vars(self)
        if own:
            super().__setattr__(name, value)
        composition = _composition()
        if not own or name in vars(composition):
            setattr(composition, name, value)

    def __delattr__(self, name: str) -> None:
        own = name in vars(self)
        if own:
            super().__delattr__(name)
        composition = _composition()
        if name in vars(composition):
            delattr(composition, name)
        elif not own:
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __dir__(self) -> list[str]:
        return sorted(set(vars(self)) | set(__all__))


sys.modules[__name__].__class__ = _Package

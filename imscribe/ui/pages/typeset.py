r"""
The Typeset page: `demo/sample.md` drawn by the imtypeset library, with a
search box over it.

**Experimental** (branch `experimental/imtypeset-adoption`; plan step A2,
"demo pages opt in one at a time", `../imtypeset/docs/advtext-rework-plan.md`
section 6.3). It was the first page to draw through
`imscribe.ui.typeset_view.TypesetView`.

**The markdown goes straight to the view**: it is read once by
`imscribe.typeset_markdown.parse_markdown` (text and runs, no node material)
and the same blocks are given to the view and described for the find index.
Nothing of the old layout core or the old views is imported by this module,
at import or later.

## When the library is not drawing

There is no other renderer. The choice is made once, when the page is built:

- `imscribe.typesetter.ready()` true (the app's font callback loaded the
  library's fonts, which `imscribe.ui.app.run` does when `IMTYPESET_LIBRARY`
  is set): a `TypesetView` over the document.
- Otherwise the page draws ONE wrapped line of text and nothing else:
  `NOT_DRAWING` and the reason (`why_not()`). `say_why_not` draws it; the
  other pages of this file's task use the same function.

**The page asks `ready()` and never `typesetter.module()`.** `module()` is the
import of the library; `ready()` only reads a flag. A page is built in the
pytest process by every page-enumerating test, also under
`make test TYPESET=1`, and the library is kept out of that process
(`imscribe/typesetter.py`, `tests/test_app_typeset.py`). So with the variable
set and no `app.run` (a headless frame) this page draws the one line and says
the fonts were not loaded.

A view call that raises `TypesetUnavailable` (the library failed mid-draw and
was switched off) has drawn nothing; the page drops the view, keeps the
sentence, and from the next frame on draws the one line. The exception does
not leave `draw`, so the app's traceback page is not reached. Any other
exception is a bug and is not caught.

## Find

The search box is `imscribe.typeset_find.Finder` over the described texts
(`imscribe.typeset_markdown.MarkdownConverter`, which needs no library, so the
find state exists, and is tested, without it). The marks go to `set_marks` as
plain tuples, handed over again only when the finder's `revision` moved, and
next/previous is `scroll_to(block, offset)`.

**Table cells are searched and marked** like any other text: a table is a
block of the library's (imtypeset commit `be40444`) and a match in a cell is a
range of the table's text. Formula source is not searched
(`imscribe/typeset_find.py`).

## What is missing on screen

Links are coloured only with `on_link`, which this page does not set. What a
table set by the library differs in from the old core's is in
`imscribe/ui/typeset_view.py`, "Tables"; the page says how many tables the
document has.

Nobody has looked at this page. `tests/test_page_typeset.py` counts vertices
and matches; `report()` prints counts.
"""

from __future__ import annotations

import os
from typing import Any, Final

from imscribe import typesetter
from imscribe.typeset_find import Finder, FindIndex
from imscribe.typeset_markdown import MarkdownConverter, parse_markdown
from imscribe.ui.ownership import MIN_WIDTH_PX
from imscribe.ui.pages import PageContext, PageSpec, caption, demo_text
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

__all__ = [
    "DEFAULT_NEEDLE",
    "FALLBACK",
    "FONTS_NOT_LOADED",
    "NOT_DRAWING",
    "PAGE",
    "TEXT_WIDTH_PX",
    "TypesetPage",
    "not_drawing",
    "say_why_not",
    "why_not",
]

DEFAULT_NEEDLE: Final = "glue"
"""What the box holds as the page opens, as on the Find page."""

TEXT_WIDTH_PX: Final = 600.0
"""The widest the document is set, as on the Find page."""

SHOW_AT: Final = 1.0 / 3.0
"""How far down the pane the top of a match is put when the pane has to move for it."""

FALLBACK: Final = (
    "No `demo/sample.md` was found, so this paragraph is the whole document. It is "
    "long enough to break onto a few lines, and the word glue is in it twice so "
    "that the search box has something to find: glue.\n"
)

FONTS_NOT_LOADED: Final = (
    "imscribe.typesetter.load_fonts() has not succeeded in this process "
    "(imscribe.ui.app.run calls it from the font callback)"
)


def why_not() -> str:
    """
    Why imtypeset is not drawing, as one sentence; empty when `typesetter.ready()`.

    `typesetter.reason()`, except where that would be untrue: before anybody
    has asked `module()` it says nothing is installed or named
    (`typesetter.ABSENT_REASON`, or `SWITCHED_OFF_REASON`), whether or not
    `IMTYPESET_LIBRARY` names a library. This function does not ask `module()`
    (the module docstring has why).
    """
    if typesetter.ready():
        return ""
    said = typesetter.reason()
    unset = (typesetter.ABSENT_REASON, typesetter.SWITCHED_OFF_REASON)
    if said and not (said in unset and os.environ.get(typesetter.LIBRARY_VARIABLE)):
        return said
    return typesetter.trouble() or FONTS_NOT_LOADED


NOT_DRAWING: Final = "imtypeset is not drawing"
"""How the one line a page draws without the library begins."""


def not_drawing(reason: str) -> str:
    """
    The one line a page shows instead of its content: `NOT_DRAWING` and why.
    """
    return f"{NOT_DRAWING}: {reason}" if reason else NOT_DRAWING


def say_why_not(reason: str) -> None:
    """
    Draw that line, wrapped at the window's edge; the whole of a page's frame without the library.
    """
    from imgui_bundle import imgui

    imgui.text_wrapped(not_drawing(reason))


class TypesetPage:
    """
    One document, one search box, and a `TypesetView` when the library can draw.

    `renderer` is `"TypesetView"` while there is a view and `"none"` when
    there is not; `reason` is then why (`why_not()`, or what the view raised).
    """

    def __init__(self, context: PageContext, text: str | None = None) -> None:
        self.context = context
        if text is None:
            text = demo_text("sample.md")
        if text is None:
            text = FALLBACK
        self.text = text
        """The markdown on show."""
        # Read once. Described here as well as by the view: the find index
        # needs the block descriptions, and needs them without the library too.
        parsed = parse_markdown(text, context.theme, math=True)
        described = MarkdownConverter(context.theme).describe(parsed.blocks)
        self.texts: tuple[str, ...] = tuple(described.texts)
        self.table_count = len(described.tables)
        self.finder = Finder(FindIndex.of(described.blocks))
        self.finder.search(DEFAULT_NEEDLE)

        self.typeset: TypesetView | None = None
        self.reason = why_not()
        self.aligned = True
        """Whether the view's texts are the ones the find index was built from."""
        if not self.reason:
            try:
                self.typeset = TypesetView(parsed, theme=context.theme, palette=DARK_PALETTE)
                self.aligned = tuple(self.typeset.texts) == self.texts
            except TypesetUnavailable as exc:
                self.reason = str(exc)
        self.frames = 0
        self.vertices = 0
        """Vertices the view added to the pane's draw list in the last frame."""
        self.scrolls = 0
        self._marked: int | None = None
        self._reveal = False

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.typeset is not None else "none"

    # -- what the controls do --------------------------------------------

    def type(self, needle: str) -> None:
        """
        What an edit of the search box does: search, and show the current match.
        """
        self.finder.search(needle)
        self._reveal = True

    def step(self, delta: int) -> None:
        """
        What next (`+1`) and previous (`-1`) do: move the current match and show it.
        """
        if self.finder.step(delta) is not None:
            self._reveal = True

    @property
    def marks(self) -> int:
        """
        How many marks the view is drawing: zero when there is no view.
        """
        if self.typeset is None or not self.aligned:
            return 0
        return len(self.finder.marks())

    def lines(self) -> tuple[str, ...]:
        """
        The captions under the search row; the one "why not" line when nothing draws.
        """
        if self.typeset is None:
            return (not_drawing(self.reason),)
        finder = self.finder
        marked = (
            f"{self.marks} marked"
            if self.aligned
            else "not marked: the view's texts differ from the find index's"
        )
        found = f"{len(finder.matches)} found, {marked}" if finder.needle else "type to search"
        out = [
            "renderer: TypesetView (imtypeset, one retained document)",
            f"{found}  ·  table cells are searched, formula source is not",
        ]
        if self.table_count:
            out.append(
                f"{self.table_count} table(s) in this document, set by the library: "
                "selected, copied, searched and marked cell by cell"
            )
        return tuple(out)

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts.
        """
        finder = self.finder
        return [
            f"frames={self.frames} renderer={self.renderer} blocks={len(self.texts)} "
            f"tables={self.table_count} needle={finder.needle!r} found={len(finder.matches)} "
            f"marks={self.marks} current={-1 if finder.current is None else finder.current + 1} "
            f"aligned={int(self.aligned)} scrolls={self.scrolls} vertices={self.vertices}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        if self.typeset is None:
            self.vertices = 0
            say_why_not(self.reason)
            return
        self._controls(imgui)
        for line in self.lines():
            caption(line)
        imgui.separator()
        # The pane is the Find page's: a scrollbar that is always there, so
        # the measure does not depend on the document's length, and padding
        # asked for by name (`imscribe/ui/pages/find.py` has the measurements).
        imgui.begin_child(
            "##imscribe-typeset-text",
            imgui.ImVec2(0.0, 0.0),
            imgui.ChildFlags_.borders.value | imgui.ChildFlags_.always_use_window_padding.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        try:
            width_px = max(min(imgui.get_content_region_avail().x, TEXT_WIDTH_PX), MIN_WIDTH_PX)
            vertices = imgui.get_window_draw_list().vtx_buffer
            before = vertices.size()
            self._draw_document(self.typeset, width_px)
            self.vertices = vertices.size() - before
        finally:
            imgui.end_child()

    def _draw_document(self, view: TypesetView, width_px: float) -> None:
        reveal, self._reveal = self._reveal, False
        match = self.finder.match if reveal else None
        try:
            if self._marked != self.finder.revision:
                self._marked = self.finder.revision
                view.set_marks(self.finder.marks() if self.aligned else None)
            if match is not None:
                view.scroll_to(match.block, match.start, align=SHOW_AT)
            view.draw(palette=DARK_PALETTE, width_px=width_px)
        except TypesetUnavailable as exc:
            # Nothing was drawn or claimed. The pane is empty for this frame
            # and the page is the one line from the next.
            self.typeset = None
            self.reason = str(exc)
        else:
            self.scrolls += view.scrolled

    def _controls(self, imgui: Any) -> None:
        finder = self.finder
        imgui.set_next_item_width(280.0)
        changed, needle = imgui.input_text_with_hint(
            "##imscribe-typeset-needle", "find in the document", finder.needle
        )
        if changed and needle != finder.needle:
            self.type(needle)
        imgui.same_line()
        if imgui.button("Previous"):
            self.step(-1)
        imgui.same_line()
        if imgui.button("Next"):
            self.step(1)
        imgui.same_line()
        imgui.text(finder.status() or ("no matches" if finder.needle else ""))


PAGE = PageSpec(
    name="Typeset",
    order=510,
    factory=TypesetPage,
    group="Experimental",
    caption="the sample through imtypeset, with a search box over the described texts",
    shots=("",),
)

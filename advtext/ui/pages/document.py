"""
The Document page: the markdown litmus test, laid out on a page and selectable.

Drag to select, double click for a word, triple click for a line, Ctrl+C to copy.

## What draws

An `advtext.ui.typeset_view.TypesetView` over the markdown SOURCE the launch
named (`PageContext.source`; `demo/sample.md` when the context has none),
read by `advtext.typeset_markdown` with no node material and drawn on a sheet
this page works out and paints. There is no other renderer, and the page
needs no `App`: `PageContext.build()` is enough to make one.

The view is made once, when the page is built, if `advtext.typesetter.ready()`
(the app's font callback loaded the library's fonts). When it is not, the
page draws ONE wrapped line saying why (`advtext.ui.pages.typeset.why_not`,
drawn by that module's `say_why_not`) and nothing else. A view call that
raises `TypesetUnavailable` (the library failed and was switched off) has
drawn no text: the page drops the view, keeps the sentence, and is that one
line from the next frame on. The exception does not leave `draw`, so the
app's traceback page is not reached; any other exception is a bug and is not
caught.

`DocumentPage.renderer` is `"TypesetView"` while there is a view and
`"none"` when there is not; `reason` is then why.

Nothing of the old layout core or the old views is imported by this module,
at import or later (`tests/test_page_document.py` holds both).

## The sheet

`TypesetView` paints no page and has no `page()`; the recipe is its
docstring's: a cursor a margin in, and `draw(width_px=measure)`. `sheet_for`
is the one statement of the arithmetic (it was the old `DocumentView`'s
`page_for`, in scaled points; `tests/test_page_document.py` holds that
function's answers as literals):

- the measure is `MEASURE_ALPHABETS` lowercase alphabets of the body face.
  **The alphabet is measured by the library** (`imtypeset.calc_text_size` of
  `abc...z` in the theme's base style): 208.0 px in the stock theme, where the
  old page added up 207.55 from its own metrics;
- the text block is `TEXT_BLOCK_FRACTION` of the sheet, the side margin never
  under `MIN_MARGIN_LEADINGS` body leadings unless the canon's is smaller;
- the head (the white above the first line and below the last) is one body
  leading.

Nobody has judged the sheet this page paints.

The sheet's height is the document's, which the library only estimates until
every block has been in view once (`TypesetView.height`). It is asked for
before the draw (`layout_for`) so the fill can go under the text, so on a
frame whose draw lays out blocks for the first time the fill is the height
the document had a frame earlier.

## What the page does not say

The library counts no glyphs, so there is no "N glyph(s) absent" line; when
`draw` answers false, one line says that something in view was not set as
asked. The debug overlay is the library's own (line boxes).
"""

from __future__ import annotations

import string
from typing import Any, Final, NamedTuple

from advtext import typesetter
from advtext.primitives import px_from_sp
from advtext.theme import BlockKind
from advtext.ui.ownership import MIN_WIDTH_PX
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.palette import Palette
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView

__all__ = [
    "FALLBACK",
    "MEASURE_ALPHABETS",
    "MIN_MARGIN_LEADINGS",
    "NOT_WHOLE",
    "PAGE",
    "TEXT_BLOCK_FRACTION",
    "DocumentPage",
    "Sheet",
    "sheet_for",
]

MEASURE_ALPHABETS: Final = 2.25
"""The widest measure, in lowercase alphabets of the body face."""

TEXT_BLOCK_FRACTION: Final = 2.0 / 3.0
"""How much of a sheet that got its ideal width is text."""

MIN_MARGIN_LEADINGS: Final = 3.0
"""The narrowest side margin, in body leadings."""

FALLBACK: Final = (
    "# Document\n\nNo markdown was named and `demo/sample.md` was not found, so this "
    "paragraph is the whole document. It is long enough to break onto a few lines "
    "at any measure the sheet takes.\n"
)
"""What the page shows when the context names no source and this is not a checkout."""

NOT_WHOLE: Final = (
    "something in view was not set as asked (a face with no font, or a formula "
    "the library refused)"
)


class Sheet(NamedTuple):
    """
    Where the sheet sits in the content region and how wide the text on it is, in pixels.
    """

    offset: float
    """From the content region's left edge to the sheet's left edge."""
    width: float
    """The sheet: the filled rectangle, margins included."""
    margin: float
    """The white left and right of the text block, inside the sheet."""
    head: float
    """The white above the first line and below the last, inside the sheet."""

    @property
    def measure(self) -> float:
        """The width the document is set to: the sheet less both margins."""
        return self.width - 2.0 * self.margin


def sheet_for(available_px: float, *, alphabet_px: float, leading_px: float) -> Sheet:
    """
    The sheet for a content region `available_px` wide.

    Centred, never wider than `MEASURE_ALPHABETS` alphabets of text plus its
    margins; narrower than that, the whole region with a margin of
    `min(canon, max(floor, surplus))`. An alphabet of zero (the library could
    not measure one) gives the whole region rather than a sheet of no width.
    """
    ideal_body = alphabet_px * MEASURE_ALPHABETS
    ideal_sheet = ideal_body / TEXT_BLOCK_FRACTION
    sheet = min(available_px, ideal_sheet) if ideal_sheet > 0.0 else available_px
    canon = sheet * (1.0 - TEXT_BLOCK_FRACTION) / 2.0
    surplus = (sheet - ideal_body) / 2.0
    margin = min(canon, max(leading_px * MIN_MARGIN_LEADINGS, surplus))
    return Sheet((available_px - sheet) / 2.0, sheet, margin, leading_px)


def _why_not() -> str:
    """
    Why imtypeset is not drawing, as one sentence; empty when `typesetter.ready()`.

    `advtext.ui.pages.typeset.why_not`, which never asks `typesetter.module()`
    (a page is built in the pytest process by every page-enumerating test,
    and the library is kept out of that process). Imported when it is needed,
    so that importing this page imports no other page.
    """
    if typesetter.ready():
        return ""
    from advtext.ui.pages.typeset import why_not

    return why_not()


def _say_why_not(reason: str) -> None:
    """
    The whole of a frame without the library: one wrapped line, `say_why_not`'s.
    """
    from advtext.ui.pages.typeset import say_why_not

    say_why_not(reason)


class DocumentPage:
    """
    One frame of the Document page: the source on a sheet, or one line saying why not.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        source = context.source
        if source is None:
            source = demo_text("sample.md")
        self.source = FALLBACK if source is None else source
        """The markdown on show."""
        self.typeset: TypesetView | None = None
        self.reason = _why_not()
        """Why nothing is drawn, when nothing is; empty while the view draws."""
        if not self.reason:
            try:
                self.typeset = TypesetView(self.source, theme=context.theme, palette=Palette())
            except TypesetUnavailable as exc:
                self.reason = str(exc)
        self.frames = 0
        self.sheet: Sheet | None = None
        """The sheet painted on the last frame; `None` when nothing was."""
        self.whole = True
        """What the view's last `draw` answered."""
        self.vertices = 0
        """Vertices the page added to the pane's draw list in the last frame, the sheet included."""
        self._alphabet: float | None = None

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.typeset is not None else "none"

    def alphabet_px(self) -> float:
        """
        The width of `abc...z` in the theme's body style, as the library measures it.

        Asked once (the theme does not change under this page). Zero if the
        library cannot say, which `sheet_for` turns into the whole region.
        """
        if self._alphabet is None:
            self._alphabet = 0.0
            module = typesetter.module()
            if module is not None:
                try:
                    self._alphabet = float(
                        module.calc_text_size(
                            string.ascii_lowercase,
                            style=typesetter.base_style(self.context.theme),
                        )[0]
                    )
                except Exception:  # noqa: BLE001 -- no measure is a wide sheet, not a crash
                    self._alphabet = 0.0
        return self._alphabet

    def leading_px(self) -> float:
        """The body leading in pixels: the head, and the unit of the margin's floor."""
        theme = self.context.theme
        return px_from_sp(theme.style(BlockKind.PARAGRAPH).leading, theme.px_per_inch)

    def report(self) -> list[str]:
        """What an unattended run prints: counts."""
        sheet = self.sheet
        view = self.typeset
        return [
            f"frames={self.frames} renderer={self.renderer} "
            f"blocks={0 if view is None else len(view.texts)} "
            f"measure={0 if sheet is None else round(sheet.measure)} "
            f"margin={0 if sheet is None else round(sheet.margin)} "
            f"whole={int(self.whole)} vertices={self.vertices}"
        ]

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        view = self.typeset
        if view is None:
            self.vertices, self.sheet = 0, None
            _say_why_not(self.reason)
            return
        debug_toggle(self.context)
        imgui.same_line()
        caption("drag to select  ·  double click a word  ·  triple click a line  ·  ctrl+C copies")
        imgui.separator()
        try:
            if imgui.begin_child("##advtext-scroll"):
                vertices = imgui.get_window_draw_list().vtx_buffer
                before = vertices.size()
                try:
                    self._draw_sheet(imgui, view)
                except TypesetUnavailable as exc:
                    # No text was drawn and no item claimed. The pane holds at
                    # most an empty sheet for this frame, and the page is the
                    # one line from the next.
                    self.typeset = None
                    self.sheet = None
                    self.reason = str(exc)
                self.vertices = vertices.size() - before
        finally:
            imgui.end_child()

    def _draw_sheet(self, imgui: Any, view: TypesetView) -> None:
        """
        The frame through imtypeset, on a sheet. `TypesetUnavailable` is the caller's to catch.
        """
        colours = Palette()
        cursor = imgui.get_cursor_screen_pos()
        available = max(float(imgui.get_content_region_avail().x), MIN_WIDTH_PX)
        sheet = sheet_for(available, alphabet_px=self.alphabet_px(), leading_px=self.leading_px())
        left = cursor.x + sheet.offset
        view.debug = self.context.debug
        # Before the draw, so that the fill goes under the text. An estimate
        # until every block has been in view (the module docstring).
        height = view.layout_for(sheet.measure)
        imgui.get_window_draw_list().add_rect_filled(
            imgui.ImVec2(left, cursor.y),
            imgui.ImVec2(left + sheet.width, cursor.y + height + 2.0 * sheet.head),
            colours.page,
        )
        imgui.set_cursor_screen_pos(imgui.ImVec2(left + sheet.margin, cursor.y + sheet.head))
        try:
            self.whole = view.draw(palette=colours, width_px=sheet.measure)
            height = view.height
        except BaseException:
            # A view that raised claimed no item, and ImGui refuses to close a
            # window whose cursor was moved with nothing submitted after it
            # (measured: `end_child` asserts, which would hide what was
            # raised). Back to where the frame began, whatever the exception.
            imgui.set_cursor_screen_pos(cursor)
            raise
        self.sheet = sheet
        # The foot: the cursor goes below the text, and an item claims the
        # white under the last line so the pane scrolls to the sheet's edge.
        imgui.set_cursor_screen_pos(imgui.ImVec2(cursor.x, cursor.y + sheet.head + height))
        imgui.dummy(imgui.ImVec2(available, sheet.head))
        if not self.whole:
            caption(NOT_WHOLE)


PAGE = PageSpec(
    name="Document",
    order=10,
    factory=DocumentPage,
    group="Typesetting",
    caption="the markdown litmus test, justified on a page sheet and selectable",
    shots=("", "debug"),
)

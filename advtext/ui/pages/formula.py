"""
The Formula page: eleven formulae, each the only one that shows some rule of TeX's
math mode -- the display-size operator as a different glyph, the four math styles
and where they stop, the inter-atom spacing table with and without its classes,
a radical sign chosen to cover its radicand, parentheses fitted to a fraction.
`advtext.ui.formulas` builds the gallery by hand (there is no parser in it, and
that is deliberate); `App.gallery` caches it per measure.

The frame code moved unchanged from `advtext.ui.app.App._formula_tab` and
`App._draw_gallery`. The one piece of state that moved with it is the last
frame's draw statistics, which only this page ever read.
"""

from __future__ import annotations

from advtext.backends.imgui_draw import DrawStats
from advtext.ui.document_view import Page
from advtext.ui.formulas import ENTRIES as FORMULA_ENTRIES
from advtext.ui.formulas import missing_glyphs
from advtext.ui.pages import (
    PageContext,
    PageSpec,
    available_width,
    caption,
    claim,
    debug_toggle,
    draw_at,
    paint_sheet,
    plate,
)


class FormulaPage:
    """
    One frame of the Formula page.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.app = context.require_app()
        self.stats = DrawStats()

    def draw(self) -> None:
        from imgui_bundle import imgui

        debug_toggle(self.context)
        imgui.same_line()
        caption(
            f"{len(FORMULA_ENTRIES)} formulae, each one the only thing here that shows "
            "some rule of TeX's math mode"
        )
        # Two independent failures, reported separately because either can happen
        # alone. `missing_glyphs` is a codepoint the *font file* has no glyph for,
        # answerable before anything is drawn. `DrawStats.missing` is a glyph ImGui
        # could not raster, found while drawing. Collapsing them into one line
        # would make a font swap and an atlas problem look like the same fault.
        gallery_missing = missing_glyphs()
        if gallery_missing:
            imgui.text_colored(
                imgui.ImVec4(0.9, 0.6, 0.2, 1.0),
                f"{len(gallery_missing)} codepoint(s) have no glyph in the math face: "
                + " ".join(f"U+{code:04X}" for code in gallery_missing),
            )
        if self.stats.missing:
            imgui.text_colored(
                imgui.ImVec4(0.9, 0.6, 0.2, 1.0),
                f"{self.stats.missing} glyph(s) have no raster in ImGui's atlas. "
                "Use `make svg` to see them.",
            )
        imgui.separator()
        if imgui.begin_child("##advtext-formula"):
            self._draw_gallery()
        imgui.end_child()

    def _draw_gallery(self) -> None:
        """
        The gallery on one sheet, scrolling.

        A scroll of plates rather than a single plate, because there are eleven
        of them and an eleven-page-tall sheet of air between two formulae is not
        a page. The sheet grows sideways for a formula wider than the prose measure
        by exactly the arithmetic the Specimen page uses -- `build_gallery`
        reports that case as `Gallery.box.width` exceeding `Gallery.width`, and
        with the shipped entries at the default sizes it does not happen at any
        width this demo opens at.
        """
        context = self.context
        ppi = context.px_per_inch
        page = plate(self.app.view.page(available_width(context)))
        gallery = self.app.gallery(page.measure)
        content = max(page.measure, gallery.box.width)
        wide = Page(
            offset=max(0, (available_width(context) - content - 2 * page.margin) // 2),
            width=content + 2 * page.margin,
            margin=page.margin,
            head=page.head,
        )
        height = gallery.box.height + gallery.box.depth
        origin = paint_sheet(wide, ppi, content_height=height)
        self.stats = draw_at(context, gallery.box, origin, debug=context.debug)
        claim(wide, height, ppi)


PAGE = PageSpec(
    name="Formula",
    order=40,
    factory=FormulaPage,
    group="Typesetting",
    caption="a hand-built gallery of TeX math-mode rules",
)

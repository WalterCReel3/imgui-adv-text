"""
The Specimen page: every face this project renders, side by side, a size ladder,
and a kerning demonstration. `advtext.ui.specimen` builds it; `App.specimen`
caches it per measure. The frame code moved unchanged from
`advtext.ui.app.App._specimen_tab` and `App._draw_specimen`.
"""

from __future__ import annotations

from advtext.ui.document_view import Page
from advtext.ui.pages import (
    PageContext,
    PageSpec,
    available_width,
    caption,
    claim,
    debug_toggle,
    draw_at,
    paint_sheet,
)


class SpecimenPage:
    """
    One frame of the Specimen page.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.app = context.require_app()

    def draw(self) -> None:
        from imgui_bundle import imgui

        debug_toggle(self.context)
        imgui.same_line()
        caption("every face at one size, one face at every size, and the kerning underneath")
        imgui.separator()
        if imgui.begin_child("##advtext-specimen"):
            self._draw_specimen()
        imgui.end_child()

    def _draw_specimen(self) -> None:
        context = self.context
        ppi = context.px_per_inch
        page = self.app.view.page(available_width(context))
        specimen = self.app.specimen(page.measure)

        # The rows are packed at their natural width and are wider than the prose
        # measure -- `build_specimen` says so and it is the right call, because a
        # comparison chart is not something anyone reads at 66 characters. So the
        # sheet grows to hold them rather than the chart being cut to fit a sheet
        # sized for prose.
        content = max(page.measure, specimen.box.width)
        wide = Page(
            offset=max(0, (available_width(context) - content - 2 * page.margin) // 2),
            width=content + 2 * page.margin,
            margin=page.margin,
            head=page.head,
        )
        height = specimen.box.height + specimen.box.depth
        origin = paint_sheet(wide, ppi, content_height=height)
        draw_at(context, specimen.box, origin, debug=context.debug)
        claim(wide, height, ppi)
        if specimen.absent:
            caption(f"{len(specimen.absent)} face(s) could not be resolved: no row for them")


PAGE = PageSpec(
    name="Specimen",
    order=30,
    factory=SpecimenPage,
    group="Typesetting",
    caption="every face at one size, one face at every size, and the kerning",
)

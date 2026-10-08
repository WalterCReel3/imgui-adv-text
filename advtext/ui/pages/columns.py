"""
The Columns page: one document flowed into 1, 2 or 3 newspaper columns.

`advtext.columns` does the split, text continuing from the foot of one column to
the head of the next. The column count is a control rather than a constant,
because the *reflow* is the demonstration: a static two-column render could have
been faked with two documents.

The frame code here moved unchanged from `advtext.ui.app.App._columns_tab` and
`App._draw_columns`. The geometry (`column_page`) and the cached split
(`App.column_layout`) stayed in `advtext.ui.app`, where `tests/test_app.py` pins
them without a window; `--tab columns:3` still sets `App.columns`.
"""

from __future__ import annotations

from advtext.backends.imgui_draw import DrawStats, Palette
from advtext.ui import Viewport
from advtext.ui.app import COLUMN_COUNTS, COLUMN_RULE, MAX_COLUMN_PAGES, PAGE_GAP_PX
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle
from advtext.units import px_from_sp, sp_from_px


class ColumnsPage:
    """
    One frame of the Columns page.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.app = context.require_app()

    def draw(self) -> None:
        from imgui_bundle import imgui

        app = self.app
        debug_toggle(self.context)
        for count in sorted({*COLUMN_COUNTS, app.columns}):
            imgui.same_line()
            if imgui.radio_button(f"{count}##columns", app.columns == count):
                app.columns = count
        imgui.same_line()
        caption("columns  ·  text continues from the foot of one to the head of the next")
        imgui.separator()
        if imgui.begin_child("##advtext-columns"):
            self._draw_columns()
        imgui.end_child()

    def _draw_columns(self) -> None:
        """
        N columns a page, pages stacked down a scroll.

        The page height is the *visible* height of this child window, so a column
        is as tall as the window and the reader sees a whole page at once. A
        document longer than one page continues on the next sheet below, which is
        the only honest thing to do with material that outruns the page: the
        alternative is silently dropping the tail, and `ColumnSplit.overflow`
        exists precisely so that this decision is the caller's.
        """
        from imgui_bundle import imgui

        from advtext.backends.imgui_draw import draw

        app = self.app
        ppi = self.context.px_per_inch
        available = imgui.get_content_region_avail()
        page = app.page_for_columns(sp_from_px(max(available.x, 80.0), ppi), app.columns)
        column_height = max(
            page.page.head,
            sp_from_px(max(available.y, 80.0), ppi) - 2 * page.page.head,
        )
        layout = app.column_layout(page.column_width, column_height, app.columns)

        region = imgui.get_cursor_screen_pos()
        window_y = imgui.get_window_pos().y
        window_height = imgui.get_window_size().y
        draw_list = imgui.get_window_draw_list()
        colours = Palette()

        sheet_x = region.x + px_from_sp(page.page.offset, ppi)
        sheet_width_px = px_from_sp(page.page.width, ppi)
        head_px = px_from_sp(page.page.head, ppi)
        column_height_px = px_from_sp(column_height, ppi)
        sheet_height_px = column_height_px + 2 * head_px

        stats = DrawStats()
        for page_index in range(layout.pages):
            top = region.y + page_index * (sheet_height_px + PAGE_GAP_PX)
            draw_list.add_rect_filled(
                imgui.ImVec2(sheet_x, top),
                imgui.ImVec2(sheet_x + sheet_width_px, top + sheet_height_px),
                colours.page,
            )
            for index in range(layout.count):
                origin = imgui.ImVec2(
                    region.x + px_from_sp(page.column_offset(index), ppi), top + head_px
                )
                viewport = Viewport.of_pixels(
                    top_px=window_y - origin.y, height_px=window_height, px_per_inch=ppi
                )
                column = layout.indexes[page_index * layout.count + index]
                issued = draw(
                    draw_list,
                    column.visible(viewport),
                    origin,
                    fonts=self.context.fonts,
                    palette=colours,
                    px_per_inch=ppi,
                    debug=self.context.debug,
                )
                stats = DrawStats(
                    glyphs=stats.glyphs + issued.glyphs,
                    missing=stats.missing + issued.missing,
                    rules=stats.rules + issued.rules,
                )
            for index in range(layout.count - 1):
                rule_x = region.x + px_from_sp(page.rule_offset(index), ppi)
                draw_list.add_line(
                    imgui.ImVec2(rule_x, top + head_px),
                    imgui.ImVec2(rule_x, top + head_px + column_height_px),
                    COLUMN_RULE,
                )

        total = layout.pages * (sheet_height_px + PAGE_GAP_PX) - PAGE_GAP_PX
        imgui.dummy(imgui.ImVec2(px_from_sp(page.page.width, ppi), total))
        if layout.overflow:
            caption(f"{layout.overflow} node(s) past {MAX_COLUMN_PAGES} pages are not shown")


PAGE = PageSpec(
    name="Columns",
    order=20,
    factory=ColumnsPage,
    group="Typesetting",
    caption="the same material flowed into one, two or three columns",
    shots=("1", "2", "3"),
)

"""
The Blocks page: `advtext.blocklayout`'s toolbar at three widths, showing that a
centred item stays centred because two `fil` glues split the surplus evenly.

The frame code moved unchanged from `advtext.ui.app.App._blocks_tab`. It has no
debug checkbox and never had one: a `Leaf` has no glyphs, so the overlay is
always on here or the page would draw nothing.
"""

from __future__ import annotations

from advtext.nodes import Kern, Node
from advtext.pack import vpack
from advtext.style import BlockKind
from advtext.ui.pages import (
    PageContext,
    PageSpec,
    available_width,
    caption,
    claim,
    draw_at,
    paint_sheet,
    plate,
)
from advtext.units import sp_from_px


class BlocksPage:
    """
    One frame of the Blocks page.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.app = context.require_app()

    def draw(self) -> None:
        from imgui_bundle import imgui

        try:
            from advtext import blocklayout
        except ImportError:  # pragma: no cover - the stretch goal may be absent
            caption("advtext.blocklayout is not present in this build")
            return
        context = self.context
        caption(
            "a toolbar at three widths: the centred title stays centred because two "
            "fil glues split the surplus evenly"
        )
        imgui.separator()
        if imgui.begin_child("##advtext-blocks"):
            page = plate(self.app.view.page(available_width(context)))
            toolbar = blocklayout.Row(
                children=(
                    *blocklayout.centre(
                        (
                            blocklayout.Leaf(width=sp_from_px(80.0), height=sp_from_px(24.0)),
                            blocklayout.Leaf(width=sp_from_px(160.0), height=sp_from_px(24.0)),
                            blocklayout.Leaf(width=sp_from_px(80.0), height=sp_from_px(24.0)),
                        )
                    ),
                )
            )
            # One sheet with the three rows stacked on it, not a sheet each. The
            # claim is a *comparison* -- the same three leaves, three surpluses,
            # one centre line -- and three separate pages would put the thing
            # being compared on three different backgrounds.
            #
            # Fractions of the measure rather than the old fixed 420 and 700 px:
            # 700 px is wider than the page the rest of the demo sets, so the
            # wide row used to hang off the sheet. The narrowest is 0.75 and not
            # less because the three leaves are 320 px natural and a row narrower
            # than that has no surplus to split -- the glues collapse to zero and
            # the page demonstrates nothing.
            rows: list[Node] = []
            gap = context.theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
            for index, fraction in enumerate((0.75, 0.875, 1.0)):
                if index:
                    rows.append(Kern(width=gap))
                rows.append(blocklayout.layout(toolbar, width=round(page.measure * fraction)))
            stacked = vpack(rows).box
            height = stacked.height + stacked.depth
            origin = paint_sheet(page, context.px_per_inch, content_height=height)
            # Debug on unconditionally: a `Leaf` has no glyphs, so with the
            # overlay off this page draws nothing at all.
            draw_at(context, stacked, origin, debug=True)
            claim(page, height, context.px_per_inch)
        imgui.end_child()


PAGE = PageSpec(
    name="Blocks",
    order=50,
    factory=BlocksPage,
    group="Typesetting",
    caption="a toolbar at three widths, centred by two fil glues",
)

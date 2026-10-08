"""
The Document page: the markdown litmus test, laid out on a page and selectable.

Drag to select, double click for a word, triple click for a line, Ctrl+C to copy.
`advtext.ui.document_view.DocumentView` owns the page geometry and the
interaction; this module is the frame around it, moved here unchanged from
`advtext.ui.app.App._document_tab` when the tab bar became a sidebar.

The view itself is `App.view`, not something this page builds, because
`scripts/mouse_probe.py` and `tests/test_app.py` reach it there.
"""

from __future__ import annotations

from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle


class DocumentPage:
    """
    One frame of the Document page.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.app = context.require_app()

    def draw(self) -> None:
        from imgui_bundle import imgui

        debug_toggle(self.context)
        # The view carries its own flag; the context's is the one the checkbox
        # on every page writes, so it is copied across before the view draws.
        self.app.view.debug = self.context.debug
        imgui.same_line()
        caption("drag to select  ·  double click a word  ·  triple click a line  ·  ctrl+C copies")
        imgui.separator()
        if imgui.begin_child("##advtext-scroll"):
            stats = self.app.view.draw(fonts=self.context.fonts)
            if stats.missing:
                caption(f"{stats.missing} glyph(s) absent from the ImGui atlas")
        imgui.end_child()


PAGE = PageSpec(
    name="Document",
    order=10,
    factory=DocumentPage,
    group="Typesetting",
    caption="the markdown litmus test, justified on a page sheet and selectable",
    shots=("", "debug"),
)

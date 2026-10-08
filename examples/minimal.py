r"""
A markdown string in a plain ImGui window, using nothing but `import advtext`.

This is the smallest thing that embeds the library, and it exists to be read
by someone embedding it. The demo application (`advtext/ui/app.py`) is fourteen
hundred lines of tabs, toolbars and a page sheet; none of that is needed to put
typeset text in a window, and until this file existed there was nothing in the
tree that showed so. Everything here is importable from the package root:

    from advtext import build_document, Theme, compose, ship, draw, load_faces

**It does not import `advtext.ui.app`, and it imports no `advtext` submodule at
all.** `tests/test_examples.py` reads this file's imports and loads it in a
fresh interpreter to hold both, because "the facade is enough" is only true
while this file needs nothing else.

Run it with:

    python examples/minimal.py

## The four steps, which are the whole pipeline

1. **Parse.** `build_document(source, theme, fontlib_metrics)` turns markdown
   into blocks of unpacked boxes and glue. Done once; it does not depend on the
   window.
2. **Compose.** `compose(document, theme, width, measure)` breaks every
   paragraph to a width and stacks the result into one box. Done again whenever
   the width changes, and only then -- `MarkdownPane.layout` keeps the last one.
3. **Ship.** `ship(box, Point(0, box.height), measure=measure)` flattens the box
   to draw commands with absolute positions. The `Point` puts the document's
   top-left corner at (0, 0) with y downward, which is what `draw` expects.
4. **Draw.** `draw(draw_list, commands, origin, fonts=fonts, palette=palette)`
   issues them to any `ImDrawList`, every frame. `fonts` is what `load_faces()`
   returned when the atlas was built.

`show` is those four steps inside whatever window is current, plus the one
thing ImGui has to be told: an `imgui.dummy` the size of the document, so the
window knows how far it scrolls.

## Two things a host has to get right, both visible below

**Ink.** `DEFAULT_PALETTE` is dark ink for a light page, because the demo
paints a page. A plain ImGui window is dark, so drawing with the default palette
is black text on a dark background and looks like nothing was drawn. `show`
takes the ink from the host's own text colour instead. Per-role colours are a
later phase of `docs/adoption-plan.md`; this is one ink for everything.

**Fonts are loaded once, when the atlas is built**, and not per frame. Under
`hello_imgui` that moment is the `load_additional_fonts` callback. This example
loads the runner's default font first, so the window's own widgets keep it, and
then this library's faces; `load_faces()` with no arguments leaves the math font
unread, which is right for a document with no mathematics in it.

## What has been run, and what has not

`MarkdownPane` and `show` are driven by `tests/test_examples.py`: with fakes
for the bookkeeping, and inside a real ImGui frame with the real fonts for the
geometry. `main` opens a window, which the tests do too wherever an Xvfb can be
started in a user namespace -- that is how it was run where this was written
(`.concerns/A0-mouse--builder--result.md` has the recipe). **Nobody has looked
at it on a physical display**, and no claim is made here about how it looks.

Deliberately not here: selection, scrolling to a position, culling to the
visible region (this draws the whole document and lets the window clip it,
which is fine for a page and wrong for a book), links, and streaming. Each is a
phase of the adoption plan with its own example.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from typing import Any

from advtext import (
    DEFAULT_PALETTE,
    Document,
    DrawCmd,
    DrawStats,
    LoadedFaces,
    MetricsResolver,
    Palette,
    Point,
    Theme,
    build_document,
    char_measure,
    compose,
    draw,
    fontlib_metrics,
    load_faces,
    px_from_sp,
    ship,
    sp_from_px,
)

MARKDOWN = """\
# Typeset, not just drawn

This paragraph was broken into lines by a **total-fit** line breaker and
*justified* by stretching the glue between its words, the way TeX does it. Every
glyph was then placed by this library, one at a time, on a draw list that
belongs to the window around it.

## What the window had to do

1. Load the faces once, when its font atlas was built.
2. Ask for a layout at its own width.
3. Hand over its draw list.

> Nothing here is a widget. The text is geometry the host owns, which is why it
> can be hit-tested, selected and copied by arithmetic.

```
document = build_document(source, theme, fontlib_metrics)
box = compose(document, theme, width, measure)
commands = ship(box, Point(0, box.height), measure=measure)
```

| step | when |
|---|---|
| parse | once |
| compose, ship | when the width changes |
| draw | every frame |
"""

WINDOW_TITLE = "advtext: minimal"


@dataclass(frozen=True, slots=True)
class Layout:
    """
    One document at one width: the commands to draw and the space they take.

    The size is in pixels because the only thing done with it is telling ImGui
    how much room the text occupies.
    """

    width_px: float
    height_px: float
    commands: tuple[DrawCmd, ...]


@dataclass(slots=True)
class MarkdownPane:
    """
    A markdown string, parsed once and laid out again only when the width changes.

    `metrics` is how a font becomes numbers. It defaults to the real fonts and
    is a field so a test can supply round ones; whatever it is, the same
    resolver measures the document, composes it and is handed to `draw`, which
    is the one contract in this pipeline that nothing enforces and that shows
    up as text at the wrong size when it is broken.
    """

    source: str
    theme: Theme = field(default_factory=Theme.build)
    metrics: MetricsResolver = fontlib_metrics
    document: Document = field(init=False)
    layouts: int = field(init=False, default=0)
    _measure: Any = field(init=False, repr=False)
    _layout: Layout | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._measure = char_measure(self.metrics)
        self.document = build_document(self.source, self.theme, self.metrics)

    def layout(self, width_px: float) -> Layout:
        """
        The document broken to a width, reusing the last layout if the width is the same.

        The width is taken to a whole pixel first. A window being dragged
        reports fractional widths, and re-breaking every paragraph because the
        content region went from 480.0 to 480.4 would be a reflow per frame for
        a difference no line can show.

        `layouts` counts the times this actually composed, so a caller -- or a
        test -- can see that a frame at an unchanged width cost nothing here.
        """
        width_px = float(max(1, int(width_px)))
        if self._layout is not None and self._layout.width_px == width_px:
            return self._layout
        px_per_inch = self.theme.px_per_inch
        box = compose(self.document, self.theme, sp_from_px(width_px, px_per_inch), self._measure)
        commands = tuple(ship(box, Point(0, box.height), measure=self._measure))
        self.layouts += 1
        self._layout = Layout(
            width_px=width_px,
            height_px=px_from_sp(box.height + box.depth, px_per_inch),
            commands=commands,
        )
        return self._layout

    def draw(
        self,
        draw_list: Any,
        origin: Any,
        layout: Layout,
        fonts: Any,
        palette: Palette = DEFAULT_PALETTE,
    ) -> DrawStats:
        """
        Issue a layout to a draw list with its top-left corner at `origin`.

        `origin` is a screen position, as `imgui.get_cursor_screen_pos()` gives
        it. The return value says how many glyphs were drawn and how many the
        loaded faces could not raster; a host that cares shows the second.
        """
        return draw(
            draw_list,
            layout.commands,
            origin,
            fonts=fonts,
            palette=palette,
            px_per_inch=self.theme.px_per_inch,
            metrics=self.metrics,
        )


def host_palette(imgui: Any) -> Palette:
    """
    The default palette with its ink and rules in the host's own text colour.

    Read from the live style every frame rather than once, so the text follows
    a theme switch. See the module docstring on why the default will not do.
    """
    ink = int(imgui.get_color_u32(imgui.Col_.text))
    return replace(DEFAULT_PALETTE, ink=ink, rule=ink)


def show(pane: MarkdownPane, fonts: Any, imgui: Any) -> DrawStats:
    """
    Draw the pane in the current ImGui window, at the cursor, as wide as the window.

    Call it between `imgui.begin` and `imgui.end`, like any widget. `imgui` is
    passed in rather than imported so this module imports no ImGui until `main`
    runs, and so a test can pass a recording stand-in.

    The `dummy` is what makes the window scroll: ImGui learns a window's content
    size from the items submitted to it, and glyphs put straight on a draw list
    are not items.
    """
    layout = pane.layout(imgui.get_content_region_avail().x)
    origin = imgui.get_cursor_screen_pos()
    stats = pane.draw(imgui.get_window_draw_list(), origin, layout, fonts, host_palette(imgui))
    imgui.dummy(imgui.ImVec2(layout.width_px, layout.height_px))
    return stats


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the pane in it. Needs a display.

    `--frames N` closes the window after N frames and prints what the last one
    drew; it is how this is run unattended. Without it the window stays open
    until it is closed.
    """
    parser = argparse.ArgumentParser(description="A markdown string in a plain ImGui window.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    args = parser.parse_args(argv)

    from imgui_bundle import hello_imgui, imgui, immapp

    pane = MarkdownPane(MARKDOWN)
    loaded: list[LoadedFaces] = []
    drawn: list[DrawStats] = []

    def load_fonts() -> None:
        # The runner's own default first, so the window's widgets keep the font
        # they would have had; then ours. The first font added is ImGui's
        # default, and this order is what stops our body face becoming it.
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        loaded.append(load_faces())

    def gui() -> None:
        imgui.set_next_window_pos(imgui.ImVec2(40.0, 40.0), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size(imgui.ImVec2(560.0, 620.0), imgui.Cond_.first_use_ever)
        if imgui.begin(WINDOW_TITLE):
            drawn.append(show(pane, loaded[-1], imgui))
        imgui.end()
        if args.frames and len(drawn) >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (640, 700)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    # An example should not leave an .ini beside wherever it was launched from.
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    immapp.run(params)

    if drawn:
        last = drawn[-1]
        print(
            f"frames={len(drawn)} layouts={pane.layouts} "
            f"glyphs={last.glyphs} missing={last.missing} rules={last.rules}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

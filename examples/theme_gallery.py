r"""
One document, several palettes and face sets, side by side: the theme gallery.

`examples/minimal.py` puts typeset text in a window in one ink. This is the
next thing a host asks: *can it look like my application?* The same markdown is
shown here in four panes, each a `BareView` with its own theme and palette --
two light and two dark, three different assignments of faces, justified and
ragged -- and everything used to do it is importable from the package root:

    from advtext import BareView, Theme, Faces, Palette, DARK_PALETTE, ColourSpan

Run it with:

    python examples/theme_gallery.py

## What a scheme is made of

A `Scheme` here is four things, and they are the four things a host supplies:

1. **A `Theme`**: which face plays which role, the body size, the alignment.
   `Theme.build(...)` for a size in this library's own units,
   `Theme.at_pixel_height(...)` to land the body on an ImGui pixel height.
   The "terminal" scheme is the one call a monospace host makes:
   `Theme.at_pixel_height(15.0, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)`.
2. **A `Palette`**: one ink, plus an ink for any block role that should differ
   (`Palette.with_roles`), the rule colour, the selection highlight and the
   link ink. `BareView` paints no background and reads none.
3. **A background**, which is the host's own: this file pushes it as the child
   window's colour before drawing the view in it. The library never fills it.
4. **Inks for syntax colouring**, which the library knows nothing about. A
   fenced block is coloured by handing the view `ColourSpan`s -- ranges of the
   block's own characters, each with an ink -- and `highlight` below makes them
   with a regular expression. Any tokeniser would do; the view only wants the
   ranges.

**The document is built once per theme, not once.** A block holds its glyphs'
font keys and the kerns between them, so the same markdown under two themes is
two documents. Two schemes that share a theme could share a document; none
here does.

## Links

A view given `on_link` draws its links in the palette's link ink, underlines
them, and calls back with the target when one is clicked. This example does not
open a browser: `Gallery.followed` records what was clicked and the window shows
the last one. A press on a live link does not begin a selection; a press beside
it does, and Ctrl+C copies what is selected in whichever pane was last pressed.

## About the faces

The bundled files are one proportional family in four styles and one monospace
face in one weight. So the "terminal" scheme sets bold in the same face as
everything else (`Faces.mono(bold=Face.CODE)`): with no bold monospace file
registered, the bold role would otherwise be set in the proportional bold. A
host with its own files registers them first (`register_font`) and leaves that
argument out. The "notes" scheme swaps the upright and italic roles, which is
all a face set is: a table from role to face.

## What has been run, and what has not

`tests/test_example_gallery.py` drives everything here: the schemes and the
highlighter as plain functions, `show` inside real ImGui frames with the real
fonts (colours read back from the vertex buffer, a link clicked with injected
mouse events), and `main` in a real window wherever an Xvfb can be started in a
user namespace. **Nobody has looked at any of these palettes on a display.**
The tests say which colours reach the draw list and on which characters. They
say nothing about whether a scheme is pleasant or even legible, and the colour
values below are stated, not recommended.

Deliberately not here: a theme editor, loading a host's own font files (there
are none to load in this tree), find-in-document, and streaming.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from advtext import (
    DARK_PALETTE,
    DEFAULT_PALETTE,
    Align,
    BareView,
    BlockKind,
    CodeBlock,
    ColourSpan,
    Document,
    DrawStats,
    Face,
    Faces,
    LoadedFaces,
    MetricsResolver,
    Palette,
    Theme,
    build_document,
    char_measure,
    colour_text,
    fontlib_metrics,
    load_faces,
    material_text,
)

MARKDOWN = """\
# One document, four schemes

Every pane beside this one holds **the same markdown**. What differs is the
*theme* -- which face plays which role, how large, justified or ragged -- and
the *palette*, which is nothing but colours. The library paints no background:
the colour behind this text belongs to [the window](https://example.org/window)
that drew it.

## What a host supplies

1. A theme, built once.
2. A palette, with an ink for any role that should differ.
3. Its own background, and a callback for [links](https://example.org/links).

> A quotation takes the ink of its role, and so does each level of heading.
> Change the palette and nothing is laid out again.

```python
def highlight(block, inks):
    # ranges of characters, each with an ink
    for token in tokens(block):
        if token.kind == "keyword":
            yield span(token, inks.keyword)
    return 42, "done"
```

| role | where its colour comes from |
|---|---|
| body | `Palette.ink` |
| heading, quote, code | `Palette.with_roles` |
| link | `Palette.link`, see [the palette](https://example.org/palette) |

---

Select across any of it and copy.
"""

WINDOW_TITLE = "advtext: theme gallery"

MIN_PANE_PX = 160.0
"""
The narrowest a pane is drawn. Below this the panes overflow the window to the
right instead of being squeezed, because a measure of a dozen characters shows
nothing about a theme but its hyphenless overfull lines.
"""


def rgb(red: int, green: int, blue: int, alpha: int = 255) -> int:
    """
    A colour as ImGui packs it into 32 bits: alpha high, then blue, green, red.

    A `Palette` holds colours in this form. Written out here because a host
    will have its colours as three numbers and needs to know the order.
    """
    return (alpha << 24) | (blue << 16) | (green << 8) | red


def channels(colour: int) -> tuple[int, int, int, int]:
    """
    `rgb` undone: red, green, blue, alpha.
    """
    return (colour & 0xFF, (colour >> 8) & 0xFF, (colour >> 16) & 0xFF, (colour >> 24) & 0xFF)


def luminance(colour: int) -> float:
    """
    How light a colour is, 0 to 1, by the usual weighted sum of its channels.

    Used for one thing: saying whether a scheme is light ink on a dark ground
    or the reverse (`Scheme.dark`). Not a contrast measurement and not gamma
    correct; it orders a near-black and a near-white and is asked nothing finer.
    """
    red, green, blue, _alpha = channels(colour)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


@dataclass(frozen=True, slots=True)
class SyntaxInks:
    """
    The four inks `highlight` uses on a code block. A host's tokeniser has its own list.
    """

    keyword: int
    string: int
    comment: int
    number: int


@dataclass(frozen=True, slots=True)
class Scheme:
    """
    Everything that makes one pane look the way it does. The module docstring has the parts.
    """

    name: str
    theme: Theme
    palette: Palette
    background: int
    syntax: SyntaxInks

    @property
    def dark(self) -> bool:
        """
        Whether the ink is lighter than the background it is drawn on.
        """
        return luminance(self.palette.ink) > luminance(self.background)


def schemes() -> tuple[Scheme, ...]:
    """
    The four schemes the gallery shows. Two light, two dark; three face sets.

    Built when called and not at import, because `Theme.at_pixel_height` reads
    a font file to convert a pixel height into an em.
    """
    page = Theme.build()
    terminal = Theme.at_pixel_height(15.0, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)
    notes = Theme.build(
        17.0,
        faces=Faces(
            regular=Face.PROSE_ITALIC,
            italic=Face.PROSE,
            bold=Face.PROSE_BOLD_ITALIC,
            bold_italic=Face.PROSE_BOLD,
        ),
        align=Align.LEFT,
    )
    return (
        Scheme(
            name="page",
            theme=page,
            palette=DEFAULT_PALETTE.with_roles(
                {
                    BlockKind.HEADING_1: rgb(0x1F, 0x3A, 0x5F),
                    BlockKind.HEADING_2: rgb(0x1F, 0x3A, 0x5F),
                    BlockKind.QUOTE: rgb(0x55, 0x55, 0x55),
                }
            ),
            background=DEFAULT_PALETTE.page,
            syntax=SyntaxInks(
                keyword=rgb(0x7C, 0x3A, 0xED),
                string=rgb(0x16, 0x65, 0x34),
                comment=rgb(0x6B, 0x72, 0x80),
                number=rgb(0xB4, 0x53, 0x09),
            ),
        ),
        Scheme(
            name="dark",
            theme=page,
            palette=DARK_PALETTE.with_roles(
                {
                    BlockKind.HEADING_1: rgb(0xFF, 0xFF, 0xFF),
                    BlockKind.HEADING_2: rgb(0x9C, 0xDC, 0xFE),
                    BlockKind.QUOTE: rgb(0xA8, 0xA8, 0xA8),
                    BlockKind.CODE: rgb(0xD4, 0xD4, 0xD4),
                }
            ),
            background=DARK_PALETTE.page,
            syntax=SyntaxInks(
                keyword=rgb(0xC5, 0x86, 0xC0),
                string=rgb(0xCE, 0x91, 0x78),
                comment=rgb(0x6A, 0x99, 0x55),
                number=rgb(0xB5, 0xCE, 0xA8),
            ),
        ),
        Scheme(
            name="terminal",
            theme=terminal,
            palette=Palette(
                ink=rgb(0xC8, 0xD3, 0xC5),
                rule=rgb(0x4B, 0x5B, 0x4F),
                highlight=rgb(0x5F, 0x87, 0x5F, 0x66),
                link=rgb(0x87, 0xD7, 0xFF),
            ).with_roles(
                {
                    BlockKind.HEADING_1: rgb(0xFF, 0xD7, 0x5F),
                    BlockKind.HEADING_2: rgb(0xFF, 0xD7, 0x5F),
                    BlockKind.QUOTE: rgb(0x87, 0xAF, 0x87),
                    BlockKind.TABLE: rgb(0xAF, 0xD7, 0xD7),
                }
            ),
            background=rgb(0x0C, 0x10, 0x0E),
            syntax=SyntaxInks(
                keyword=rgb(0xFF, 0x87, 0xAF),
                string=rgb(0xD7, 0xD7, 0x87),
                comment=rgb(0x6C, 0x7C, 0x6C),
                number=rgb(0xAF, 0xAF, 0xFF),
            ),
        ),
        Scheme(
            name="notes",
            theme=notes,
            palette=Palette(
                ink=rgb(0x43, 0x34, 0x22),
                rule=rgb(0xA8, 0x90, 0x6C),
                highlight=rgb(0xD9, 0x77, 0x06, 0x4D),
                link=rgb(0x9A, 0x34, 0x12),
            ).with_roles({BlockKind.CODE: rgb(0x2B, 0x2B, 0x2B)}),
            background=rgb(0xF4, 0xEC, 0xD8),
            syntax=SyntaxInks(
                keyword=rgb(0x9A, 0x34, 0x12),
                string=rgb(0x3F, 0x62, 0x12),
                comment=rgb(0x8A, 0x7A, 0x60),
                number=rgb(0x1E, 0x40, 0xAF),
            ),
        ),
    )


KEYWORDS = frozenset(
    "and as class def else for from if import in is lambda not or return while with yield "
    "None True False".split()
)

_TOKEN = re.compile(
    r"(?P<comment>#[^\n]*)"
    r"|(?P<string>\"[^\"\n]*\"|'[^'\n]*')"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
    r"|(?P<word>\b[A-Za-z_]\w*\b)"
)


def highlight(block: CodeBlock, inks: SyntaxInks) -> list[ColourSpan]:
    """
    Colour spans for one code block: comments, strings, numbers and Python's keywords.

    Twenty lines of regular expression standing in for a real tokeniser. What
    matters is the shape of the hand-off: `material_text(block).text` is the
    block's text exactly as it is set -- tabs already expanded -- and
    `colour_text(block, start, end, ink=...)` turns a slice of that text into
    the range the view wants. The view never sees the tokens.
    """
    spans: list[ColourSpan] = []
    for match in _TOKEN.finditer(material_text(block).text):
        kind = match.lastgroup
        if kind == "word":
            if match.group() not in KEYWORDS:
                continue
            ink = inks.keyword
        elif kind == "comment":
            ink = inks.comment
        elif kind == "string":
            ink = inks.string
        else:
            ink = inks.number
        span = colour_text(block, match.start(), match.end(), ink=ink)
        if span is not None:
            spans.append(span)
    return spans


@dataclass(slots=True)
class Pane:
    """
    One scheme, the document built with its theme, and the view that draws it.
    """

    scheme: Scheme
    document: Document
    view: BareView
    stats: DrawStats | None = None


@dataclass(slots=True)
class Gallery:
    """
    One markdown source shown under several schemes.

    `followed` collects the target of every link clicked in any pane, in order.
    `on_link`, if given, is called as well -- a host that wants a browser opened
    passes `webbrowser.open`; this example passes nothing and only records.

    `metrics` is how a font becomes numbers and is a field for the reason
    `examples/minimal.py` gives: the same resolver must build the document and
    measure it for the view.
    """

    source: str = MARKDOWN
    schemes: Sequence[Scheme] = field(default_factory=schemes)
    metrics: MetricsResolver = fontlib_metrics
    on_link: Callable[[str], None] | None = None
    followed: list[str] = field(init=False, default_factory=list)
    panes: tuple[Pane, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.panes = tuple(self._pane(scheme) for scheme in self.schemes)

    def _pane(self, scheme: Scheme) -> Pane:
        document = build_document(self.source, scheme.theme, self.metrics)
        view = BareView(
            document=document,
            theme=scheme.theme,
            measure=char_measure(self.metrics),
            px_per_inch=scheme.theme.px_per_inch,
            on_link=self._follow,
        )
        for number, block in enumerate(document.blocks):
            if isinstance(block, CodeBlock):
                view.set_colours(number, highlight(block, scheme.syntax))
        return Pane(scheme=scheme, document=document, view=view)

    def _follow(self, target: str) -> None:
        self.followed.append(target)
        if self.on_link is not None:
            self.on_link(target)

    def pane(self, name: str) -> Pane:
        """
        The pane showing the scheme of that name. `KeyError` if there is none.
        """
        for pane in self.panes:
            if pane.scheme.name == name:
                return pane
        raise KeyError(name)

    def status(self) -> str:
        """
        The one line the window shows above the panes.
        """
        if not self.followed:
            return "Click a link in any pane. Nothing is opened; the target is shown here."
        return f"Link {len(self.followed)}: {self.followed[-1]}"


def show(gallery: Gallery, fonts: Any, imgui: Any) -> tuple[DrawStats, ...]:
    """
    Draw the status line and every pane, left to right, in the current window.

    Each pane is a child window so that it scrolls on its own, and three things
    about that child are the host's side of the bargain:

    - its background colour, pushed here from the scheme, since the view
      paints none;
    - a vertical scrollbar that is always there, so the pane's width -- and
      with it every line break -- does not change on the frame the document
      first grows taller than the pane;
    - a border, which is what gives a child window its padding, so the text
      does not start on the child's very edge.

    `imgui` is passed in, as in `examples/minimal.py`, so this module imports
    no ImGui until `main` runs. Returns each pane's draw statistics, which are
    also left on the pane.
    """
    imgui.text_unformatted(gallery.status())
    count = len(gallery.panes)
    spacing = imgui.get_style().item_spacing.x
    available = imgui.get_content_region_avail().x
    width = max(MIN_PANE_PX, (available - spacing * (count - 1)) / count)
    for number, pane in enumerate(gallery.panes):
        if number:
            imgui.same_line()
        scheme = pane.scheme
        imgui.push_style_color(imgui.Col_.child_bg, scheme.background)
        imgui.begin_child(
            f"##advtext-gallery-{scheme.name}",
            imgui.ImVec2(width, 0.0),
            imgui.ChildFlags_.borders.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        pane.stats = pane.view.draw(fonts=fonts, palette=scheme.palette)
        imgui.end_child()
        imgui.pop_style_color()
    return tuple(pane.stats for pane in gallery.panes if pane.stats is not None)


def report(gallery: Gallery, frames: int) -> list[str]:
    """
    What `main` prints when it was asked to stop by itself: one line per pane, then a total.

    Counts, not judgements: how many glyphs and rules the last frame drew in
    each pane, how many glyphs the loaded faces could not raster, how many
    links were on screen, and how many blocks the view could not map a colour
    or a link onto (which should be none).
    """
    lines = []
    for pane in gallery.panes:
        stats = pane.stats
        if stats is None:
            continue
        lines.append(
            f"scheme={pane.scheme.name} dark={int(pane.scheme.dark)} glyphs={stats.glyphs} "
            f"missing={stats.missing} rules={stats.rules} "
            f"links={len(pane.view.visible_links)} unmapped={pane.view.unmapped_blocks}"
        )
    lines.append(f"frames={frames} panes={len(lines)} followed={len(gallery.followed)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the gallery in it. Needs a display.

    `--frames N` closes the window after N frames and prints `report`; it is
    how this is run unattended.
    """
    parser = argparse.ArgumentParser(description="One document in several palettes and face sets.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    args = parser.parse_args(argv)

    from imgui_bundle import hello_imgui, imgui, immapp

    gallery = Gallery()
    loaded: list[LoadedFaces] = []
    frames = 0

    def load_fonts() -> None:
        # The runner's default first, so the status line and the scrollbars
        # keep the font they would have had; then this library's faces.
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        loaded.append(load_faces())

    def gui() -> None:
        nonlocal frames
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.work_pos)
        imgui.set_next_window_size(viewport.work_size)
        flags = (
            imgui.WindowFlags_.no_decoration.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_saved_settings.value
        )
        if imgui.begin(WINDOW_TITLE, None, flags):
            show(gallery, loaded[-1], imgui)
        imgui.end()
        frames += 1
        if args.frames and frames >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (1360, 820)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    # An example should not leave an .ini beside wherever it was launched from.
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    immapp.run(params)

    if args.frames:
        print("\n".join(report(gallery, frames)))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

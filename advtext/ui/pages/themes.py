r"""
The Themes page: one document, and the three things a host changes about how it is set.

`examples/theme_gallery.py` answers "can it look like my application?" with four
fixed panes. This page lets the three answers be turned separately, on one
document in a `BareView`, and counts what each turn costs:

- **the palette** -- four colour schemes, two of them light ink on a dark ground.
  Colours only: `BareView.draw(palette=...)` and, for the code blocks, a new set
  of `ColourSpan`s in the scheme's syntax inks;
- **the face set** -- which face plays which role, and the alignment that goes
  with it: Roboto justified, everything monospace and ragged, and a mix;
- **the size**, stated the way a host states it: the *pixel height* of its own
  UI font. `Theme.at_pixel_height` turns that into an em for the running text,
  and a line of ordinary `imgui.text` in the same face at the same number sits
  beside the slider so the two can be compared.

A **split** shows the document twice at one scroll position in two palettes.
Links are live and open nothing: the status line shows the target clicked.

## What a change rebuilds, and how this page knows

A page should rebuild what a change forces and nothing else, so each change is
handled by the least that is true of it:

| change | what is done | what it forces |
|---|---|---|
| palette | the pane's scheme is replaced; code blocks get new spans | nothing is laid out |
| faces, size | a new `Theme`, one `build_document`, both views invalidated | all of it |
| split on | the first pane narrows; the second view is drawn | all of it, in both |
| split off | the first pane widens; the second view is kept, undrawn | all of the first |

A theme change forces everything because a block holds its glyphs' font keys and
the kerns between them: the same markdown under two themes is two documents. A
width change forces everything because every line is broken to the width.
**Coming straight back is free**: the view's unit cache keeps the last two
passes, so turning the split off again, or returning to the face set just left,
re-ships nothing (measured; `tests/test_page_themes.py` pins both). A third
state in between pushes the first out and the return is paid in full. The
hidden second pane is not laid out at all while hidden.

The last frame's bill is on the page (`ThemesPage.last`, a `Rebuild`) and the
most recent one of each cause is kept (`ThemesPage.bills`).

**The counts are the layout's own.** `BareView.layout.stats`
(`advtext.ui.units.LayoutStats`) says which units `layout_units` composed and
shipped for that layout and how many blocks were broken into lines again, and
the page adds them up over the panes that were drawn. It used to work the
first out itself, by comparing each unit's composed box with those of the
pane's last four layouts by identity, and could only bound the second from
above; a test held that count equal to the unit cache's private miss counter
and still does, now for the library's figure.

## The size, and what "the same size" can mean

`Theme.at_pixel_height(h)` sizes the running text so that ImGui rasters the
theme's regular face at `h` pixels -- `h` being ascent plus descent, the number
ImGui calls a font size. The reference line is `imgui.push_font(face, h)` and
`imgui.text`. Both are then the same face from the same raster, so their glyphs
are the same height **when the regular face is the one the atlas loaded for
it**. Only the running text lands there: the page's docstring for
`Theme.at_pixel_height` says why code in a mixed theme does not.

The slider moves in half pixels. Each stop is a new theme and a new document,
and a continuous slider would build one per frame of a drag for sizes nobody
can tell apart.

## About the colours

The four schemes are `examples/theme_gallery.py`'s, copied: an example must run
on the facade alone and this module may not be imported by one, so the values
live twice. They are stated, not recommended. **Nobody has judged whether any of
them is pleasant or legible**; the tests say which inks reach which characters.

Syntax colouring is `advtext.ui.pages._syntax`, the demo's own small tokeniser,
which the Diff and Chat pages share. The library has none.

Deliberately not here: a theme editor, loading font files (the face sets are the
bundled faces rearranged), and more than two panes -- the example has four.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from advtext.backends.imgui_draw import (
    DARK_PALETTE,
    DEFAULT_PALETTE,
    DrawStats,
    Palette,
    rgba,
)
from advtext.fontmetrics import Face
from advtext.markdown import CodeBlock, Document, build_document
from advtext.style import Align, BlockKind, Faces, MetricsResolver, Theme
from advtext.ui.bare_view import BareView
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.pages._syntax import SyntaxInks, colour_spans
from advtext.ui.units import UnitLayout

__all__ = [
    "COLOURS",
    "FACE_SETS",
    "FALLBACK_MARKDOWN",
    "MAX_HEIGHT_PX",
    "MIN_HEIGHT_PX",
    "PAGE",
    "SIZE_STEP_PX",
    "Colours",
    "FaceSet",
    "Pane",
    "Rebuild",
    "ThemesPage",
    "snap_height",
]

FALLBACK_MARKDOWN: Final = """\
# One document, any scheme

`demo/themes.md` is not here, so this is an installed copy and not a checkout.
The pickers still change the **palette** and the *theme* of this text, and
[a link](https://example.org/fallback) is still live.

```python
def answer():
    return 42  # the only code block there is
```
"""

MIN_HEIGHT_PX: Final = 10.0
MAX_HEIGHT_PX: Final = 28.0
SIZE_STEP_PX: Final = 0.5
DEFAULT_HEIGHT_PX: Final = 16.0

"""
How many of a pane's past layouts a new one is compared with to find surviving units.

The view's unit cache keeps two passes; four is that with room, and bounds what
this page holds alive to four layouts of one small document per pane.
"""

CATCH_UP_FRAMES: Final = 4
"""
How many frames a pane is given to reach a scroll position the page sent it to.
"""

SAMPLE_ROW_PX: Final = MAX_HEIGHT_PX + 8.0
"""
The fixed height of the row holding the reference text, so that moving the size
slider does not move the panes under it.
"""


def snap_height(height_px: float) -> float:
    """
    A slider value as the size actually set: clamped, and on a half pixel.
    """
    clamped = min(max(height_px, MIN_HEIGHT_PX), MAX_HEIGHT_PX)
    return round(clamped / SIZE_STEP_PX) * SIZE_STEP_PX


@dataclass(frozen=True, slots=True)
class Colours:
    """
    Everything about a scheme that is a colour: palette, ground, syntax inks.

    `background` is the host's and is pushed as the pane's child colour; the
    view paints none and reads none.
    """

    name: str
    palette: Palette
    background: int
    syntax: SyntaxInks

    @property
    def dark(self) -> bool:
        """
        Whether the ink is lighter than the ground: a weighted sum of channels, no more.
        """
        return _luminance(self.palette.ink) > _luminance(self.background)


def _luminance(colour: int) -> float:
    red, green, blue = colour & 0xFF, (colour >> 8) & 0xFF, (colour >> 16) & 0xFF
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


COLOURS: Final[tuple[Colours, ...]] = (
    Colours(
        name="page",
        palette=DEFAULT_PALETTE.with_roles(
            {
                BlockKind.HEADING_1: rgba(0x1F, 0x3A, 0x5F),
                BlockKind.HEADING_2: rgba(0x1F, 0x3A, 0x5F),
                BlockKind.QUOTE: rgba(0x55, 0x55, 0x55),
            }
        ),
        background=DEFAULT_PALETTE.page,
        syntax=SyntaxInks(
            keyword=rgba(0x7C, 0x3A, 0xED),
            string=rgba(0x16, 0x65, 0x34),
            comment=rgba(0x6B, 0x72, 0x80),
            number=rgba(0xB4, 0x53, 0x09),
        ),
    ),
    Colours(
        name="dark",
        palette=DARK_PALETTE.with_roles(
            {
                BlockKind.HEADING_1: rgba(0xFF, 0xFF, 0xFF),
                BlockKind.HEADING_2: rgba(0x9C, 0xDC, 0xFE),
                BlockKind.QUOTE: rgba(0xA8, 0xA8, 0xA8),
                BlockKind.CODE: rgba(0xD4, 0xD4, 0xD4),
            }
        ),
        background=DARK_PALETTE.page,
        syntax=SyntaxInks(
            keyword=rgba(0xC5, 0x86, 0xC0),
            string=rgba(0xCE, 0x91, 0x78),
            comment=rgba(0x6A, 0x99, 0x55),
            number=rgba(0xB5, 0xCE, 0xA8),
        ),
    ),
    Colours(
        name="terminal",
        palette=Palette(
            ink=rgba(0xC8, 0xD3, 0xC5),
            rule=rgba(0x4B, 0x5B, 0x4F),
            highlight=rgba(0x5F, 0x87, 0x5F, 0x66),
            link=rgba(0x87, 0xD7, 0xFF),
        ).with_roles(
            {
                BlockKind.HEADING_1: rgba(0xFF, 0xD7, 0x5F),
                BlockKind.HEADING_2: rgba(0xFF, 0xD7, 0x5F),
                BlockKind.QUOTE: rgba(0x87, 0xAF, 0x87),
                BlockKind.TABLE: rgba(0xAF, 0xD7, 0xD7),
            }
        ),
        background=rgba(0x0C, 0x10, 0x0E),
        syntax=SyntaxInks(
            keyword=rgba(0xFF, 0x87, 0xAF),
            string=rgba(0xD7, 0xD7, 0x87),
            comment=rgba(0x6C, 0x7C, 0x6C),
            number=rgba(0xAF, 0xAF, 0xFF),
        ),
    ),
    Colours(
        name="notes",
        palette=Palette(
            ink=rgba(0x43, 0x34, 0x22),
            rule=rgba(0xA8, 0x90, 0x6C),
            highlight=rgba(0xD9, 0x77, 0x06, 0x4D),
            link=rgba(0x9A, 0x34, 0x12),
        ).with_roles({BlockKind.CODE: rgba(0x2B, 0x2B, 0x2B)}),
        background=rgba(0xF4, 0xEC, 0xD8),
        syntax=SyntaxInks(
            keyword=rgba(0x9A, 0x34, 0x12),
            string=rgba(0x3F, 0x62, 0x12),
            comment=rgba(0x8A, 0x7A, 0x60),
            number=rgba(0x1E, 0x40, 0xAF),
        ),
    ),
)
"""
The four schemes of `examples/theme_gallery.py`, as colours only. Two are dark.
"""


@dataclass(frozen=True, slots=True)
class FaceSet:
    """
    Which face plays which role, and the alignment that goes with the choice.
    """

    name: str
    label: str
    faces: Faces
    align: Align

    def theme(self, height_px: float, px_per_inch: float, metrics: MetricsResolver) -> Theme:
        """
        The theme whose running text ImGui rasters `height_px` tall in `faces.regular`.
        """
        return Theme.at_pixel_height(
            height_px, px_per_inch, faces=self.faces, align=self.align, metrics=metrics
        )


FACE_SETS: Final[tuple[FaceSet, ...]] = (
    FaceSet("roboto", "Roboto, justified", Faces(), Align.JUSTIFY),
    # `bold=Face.CODE` and not the default: with no bold monospace file registered
    # the bold role is backed by the proportional bold, and `Faces.mono()` alone
    # would set every heading in Roboto Bold (AD-gallery's finding). This is the
    # set that loses the weight and keeps the columns.
    FaceSet("mono", "all monospace, ragged", Faces.mono(bold=Face.CODE), Align.LEFT),
    # And this is the other answer to the same question, on purpose: monospace
    # running text with headings and bold in the proportional bold.
    FaceSet(
        "mixed",
        "monospace text, Roboto Bold headings",
        Faces.mono(bold=Face.PROSE_BOLD),
        Align.LEFT,
    ),
)


@dataclass(frozen=True, slots=True)
class Rebuild:
    """
    What one change cost, counted from the layouts. The module docstring has the method.

    `cause` is `"open"`, `"palette"`, `"faces"`, `"size"`, `"split"`, or
    `"width"` for a relayout nothing on this page asked for (the window was
    resized). `documents` is how many times `build_document` ran. `units` is how
    many units the panes that were drawn hold between them; `reshipped` is how
    many of those were composed and shipped again, and `blocks` how many blocks
    were broken into lines again (`advtext.ui.units.LayoutStats`).
    """

    cause: str
    documents: int
    units: int
    reshipped: int
    blocks: int

    def line(self) -> str:
        """
        The readout: one line, counts only.
        """
        return (
            f"last change: {self.cause} -- documents built {self.documents}, "
            f"units re-shipped {self.reshipped} of {self.units}, "
            f"blocks re-broken {self.blocks}"
        )


@dataclass(slots=True)
class Pane:
    """
    One view of the document, the scheme it is drawn in, and what it last laid out.
    """

    view: BareView
    colours: Colours
    stats: DrawStats | None = None
    scroll: float = 0.0
    """Where the page expects this pane's scroll to be: where it last found or sent it."""
    catching_up: int = 0
    """Frames left in which a scroll the page asked for may still be on its way."""
    _seen: UnitLayout | None = field(default=None, repr=False)

    def colour_code(self) -> int:
        """
        Hand the view this pane's syntax inks for every code block. Returns the span count.

        Replaces whatever the blocks had, so it serves a new document and a new
        scheme alike. A document with no code block clears nothing and sets nothing.
        """
        self.view.clear_colours()
        count = 0
        for number, block in enumerate(self.view.document.blocks):
            if isinstance(block, CodeBlock):
                spans = colour_spans(block, self.colours.syntax)
                self.view.set_colours(number, spans)
                count += len(spans)
        return count

    def settle(self) -> tuple[int, int, int]:
        """
        `(units, re-shipped, blocks broken again)` since this was last called.

        The layout's own account (`UnitLayout.stats`), counted once per
        layout: a frame that drew the layout it already had built nothing.
        """
        layout = self.view.layout
        if layout is None:
            return (0, 0, 0)
        if layout is self._seen:
            return (len(layout.placed), 0, 0)
        self._seen = layout
        stats = layout.stats
        return (stats.units, len(stats.built), stats.blocks_broken)


class ThemesPage:
    """
    The page's state and one frame of it.

    Everything a test wants is a method that needs no ImGui: `set_colours`,
    `set_face_set`, `set_height`, `set_split`. `draw` calls the same four from
    the widgets and then `account`s for the frame.
    """

    def __init__(self, context: PageContext, source: str | None = None) -> None:
        self.context = context
        if source is None:
            source = demo_text("themes.md")
        self.source = FALLBACK_MARKDOWN if source is None else source
        self.face_set = FACE_SETS[0]
        self.height_px = DEFAULT_HEIGHT_PX
        self.split = "split" in context.options_for("Themes")
        self.followed: list[str] = []
        self.documents_built = 0
        self.last: Rebuild | None = None
        self.bills: dict[str, Rebuild] = {}
        self._cause: str | None = "open"
        self._built_now = 0
        self._agreed = 0.0
        self.theme = self._theme()
        self.document = self._build()
        self.panes = [self._pane(COLOURS[0]), self._pane(COLOURS[1])]

    # -- building ----------------------------------------------------------

    def _theme(self) -> Theme:
        return self.face_set.theme(self.height_px, self.context.px_per_inch, self.context.metrics)

    def _build(self) -> Document:
        self.documents_built += 1
        self._built_now += 1
        return build_document(self.source, self.theme, self.context.metrics)

    def _pane(self, colours: Colours) -> Pane:
        view = BareView(
            document=self.document,
            theme=self.theme,
            measure=self.context.measure,
            px_per_inch=self.context.px_per_inch,
            on_link=self.followed.append,
        )
        pane = Pane(view=view, colours=colours)
        pane.colour_code()
        return pane

    @property
    def shown(self) -> tuple[Pane, ...]:
        """
        The panes that are drawn: one, or both when split.
        """
        return (self.panes[0], self.panes[1]) if self.split else (self.panes[0],)

    # -- the four changes --------------------------------------------------

    def set_colours(self, pane: int, colours: Colours) -> None:
        """
        Give a pane another scheme. Nothing is laid out; the code blocks are re-inked.
        """
        target = self.panes[pane]
        if target.colours is colours:
            return
        target.colours = colours
        target.colour_code()
        self._cause = "palette"

    def set_face_set(self, face_set: FaceSet) -> None:
        """
        Change which face plays which role. A new theme, one new document, both panes.
        """
        if face_set is self.face_set:
            return
        self.face_set = face_set
        self._retheme("faces")

    def set_height(self, height_px: float) -> None:
        """
        Change the pixel height of the running text, snapped to half a pixel.
        """
        snapped = snap_height(height_px)
        if snapped == self.height_px:
            return
        self.height_px = snapped
        self._retheme("size")

    def _retheme(self, cause: str) -> None:
        self.theme = self._theme()
        self.document = self._build()
        for pane in self.panes:
            # The hidden pane too: it is one assignment now, against a view
            # that would otherwise open on a document the page no longer has.
            pane.view.theme = self.theme
            pane.view.document = self.document
            pane.view.invalidate()
            pane.colour_code()
        self._cause = cause

    def set_split(self, split: bool) -> None:
        """
        Show the document once or twice. The second pane's view is kept while hidden.
        """
        if split == self.split:
            return
        self.split = split
        if split:
            # The second pane opens wherever its child window was left, which on
            # its first frame is the top. It is sent to the first pane's place
            # and given a few frames to arrive before it is taken to have been
            # moved by hand.
            self.panes[1].scroll = self._agreed
            self.panes[1].catching_up = CATCH_UP_FRAMES
        self._cause = "split"

    # -- accounting --------------------------------------------------------

    def account(self) -> Rebuild | None:
        """
        Close the books on a frame: what the panes laid out, and why.

        Call once after the panes have been drawn. Returns the frame's
        `Rebuild` if anything changed or was laid out, else `None`; either way
        `last` is the most recent one.
        """
        units = reshipped = blocks = 0
        for pane in self.shown:
            pane_units, pane_fresh, pane_blocks = pane.settle()
            units += pane_units
            reshipped += pane_fresh
            blocks += pane_blocks
        if self._cause is None and not reshipped:
            return None
        bill = Rebuild(
            cause=self._cause or "width",
            documents=self._built_now,
            units=units,
            reshipped=reshipped,
            blocks=blocks,
        )
        self._cause = None
        self._built_now = 0
        self.last = bill
        self.bills[bill.cause] = bill
        return bill

    def status(self) -> str:
        """
        The link line: what was last clicked, or what clicking does.
        """
        if not self.followed:
            return "Click a link. Nothing is opened; the target is shown here."
        return f"link {len(self.followed)}: {self.followed[-1]}"

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self._controls()
        caption(self.status())
        caption(self.last.line() if self.last is not None else "nothing has been laid out yet")
        imgui.separator()

        panes = self.shown
        spacing = imgui.get_style().item_spacing.x
        available = imgui.get_content_region_avail().x
        width = max((available - spacing * (len(panes) - 1)) / len(panes), 1.0)
        leader = self._leader(panes)
        for number, pane in enumerate(panes):
            if number:
                imgui.same_line()
            imgui.push_style_color(imgui.Col_.child_bg, pane.colours.background)
            imgui.begin_child(
                f"##advtext-themes-pane-{number}",
                imgui.ImVec2(width, 0.0),
                imgui.ChildFlags_.borders.value,
                imgui.WindowFlags_.always_vertical_scrollbar.value,
            )
            self._follow_scroll(pane, leader)
            pane.view.debug = self.context.debug
            pane.stats = pane.view.draw(fonts=self.context.fonts, palette=pane.colours.palette)
            imgui.end_child()
            imgui.pop_style_color()
        self.account()

    def _leader(self, panes: tuple[Pane, ...]) -> float:
        """
        The scroll position both panes are held to this frame.

        Whichever pane the user last scrolled leads. `Pane.scroll` is where the
        page expects a pane to be, so a pane whose value differs from the
        agreed one was found somewhere else last frame -- moved by the wheel or
        the scrollbar -- and takes the lead. A pane still catching up to a
        scroll the page itself asked for is not counted as moved.
        """
        # Each pane against what was agreed *before* this frame: comparing
        # against a value just taken from the first pane would make the second,
        # still where it was, look moved and hand the lead straight back.
        agreed = self._agreed
        for pane in panes:
            if not pane.catching_up and pane.scroll != agreed:
                self._agreed = pane.scroll
        return self._agreed

    def _follow_scroll(self, pane: Pane, leader: float) -> None:
        """
        Inside a pane's child: note where the user put it, or send it to the leader.

        `imgui.set_scroll_y` takes effect at the child's next `begin`, and a
        child on its first frame has no content height to scroll within, so a
        request is repeated for up to `CATCH_UP_FRAMES` frames. A pane that
        still is not there after that cannot get there (its document is
        shorter), and where it stopped becomes the lead.
        """
        from imgui_bundle import imgui

        here = imgui.get_scroll_y()
        if pane.catching_up:
            pane.catching_up -= 1
            if here == leader:
                pane.catching_up = 0
            elif pane.catching_up:
                imgui.set_scroll_y(leader)
            else:
                pane.scroll = here
                return
            pane.scroll = leader
            return
        if here != pane.scroll:
            # Moved by hand since it was last drawn. It leads from the next frame.
            pane.scroll = here
            return
        if here != leader:
            imgui.set_scroll_y(leader)
            pane.scroll = leader
            pane.catching_up = CATCH_UP_FRAMES

    def _controls(self) -> None:
        from imgui_bundle import imgui

        debug_toggle(self.context)
        imgui.same_line()
        self._colours_combo("##advtext-themes-palette-0", 0)
        imgui.same_line()
        imgui.set_next_item_width(280.0)
        if imgui.begin_combo("##advtext-themes-faces", self.face_set.label):
            for face_set in FACE_SETS:
                if imgui.selectable(face_set.label, face_set is self.face_set)[0]:
                    self.set_face_set(face_set)
            imgui.end_combo()
        imgui.same_line()
        _, split = imgui.checkbox("split", self.split)
        self.set_split(split)
        if self.split:
            imgui.same_line()
            self._colours_combo("##advtext-themes-palette-1", 1)

        imgui.set_next_item_width(220.0)
        changed, height = imgui.slider_float(
            "##advtext-themes-size", self.height_px, MIN_HEIGHT_PX, MAX_HEIGHT_PX, "%.1f px"
        )
        if changed:
            self.set_height(height)
        imgui.same_line()
        # A child of fixed height, so the reference line can be any size the
        # slider allows without moving the panes below it.
        imgui.begin_child(
            "##advtext-themes-sample",
            imgui.ImVec2(0.0, SAMPLE_ROW_PX),
            imgui.ChildFlags_.none.value,
            imgui.WindowFlags_.no_scrollbar.value | imgui.WindowFlags_.no_background.value,
        )
        imgui.push_font(self.context.fonts(self.face_set.faces.regular), self.height_px)
        imgui.text_unformatted(self.sample())
        imgui.pop_font()
        imgui.end_child()

    def sample(self) -> str:
        """
        The reference line: ordinary ImGui text, in the regular face, at the slider's size.
        """
        return f"imgui.text at {self.height_px:.1f} px, the size the running text is set to"

    def _colours_combo(self, label: str, pane: int) -> None:
        from imgui_bundle import imgui

        current = self.panes[pane].colours
        imgui.set_next_item_width(120.0)
        if imgui.begin_combo(label, current.name):
            for colours in COLOURS:
                if imgui.selectable(colours.name, colours is current)[0]:
                    self.set_colours(pane, colours)
            imgui.end_combo()


PAGE = PageSpec(
    name="Themes",
    order=110,
    factory=ThemesPage,
    group="Embedding",
    caption="one document under four palettes, three face sets and any pixel size",
    options=("split",),
    shots=("", "split"),
)

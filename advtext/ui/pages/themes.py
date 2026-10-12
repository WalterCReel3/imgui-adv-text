r"""
The Themes page: one document, and the three things a host changes about how it is set.

`examples/theme_gallery.py` answers "can it look like my application?" with four
fixed panes. This page lets the three answers be turned separately, on one
document, and counts what each turn costs:

- **the palette** -- four colour schemes, two of them light ink on a dark ground.
  `TypesetView.set_palette` and, for the code blocks, new inks in the scheme's
  syntax colours (`set_colours`);
- **the face set** -- which face plays which role, and the alignment that goes
  with it: Roboto justified, everything monospace and ragged, and a mix;
- **the size**, stated the way a host states it: the *pixel height* of its own
  UI font. `Theme.at_pixel_height` turns that into an em for the running text,
  and a line of ordinary `imgui.text` in the same face at the same number sits
  beside the slider so the two can be compared.

A **split** shows the document twice at one scroll position in two palettes.
Links are live and open nothing: the status line shows the target clicked.

## What draws

Each pane is an `advtext.ui.typeset_view.TypesetView`. There is no other
renderer. The views are made once, when the page is built, if
`advtext.typesetter.ready()` (the app's font callback loaded the library's
fonts). When it is not, the page draws ONE wrapped line saying why
(`advtext.ui.pages.typeset.why_not`, drawn by that module's `say_why_not`) and
nothing else: no controls, no panes. A view call that raises
`TypesetUnavailable` anywhere in a frame (the library failed and was switched
off) has drawn no text: both panes lose their views, the page keeps the
sentence and is that one line from the next frame on. The exception does not
leave `draw`, so the app's traceback page is not reached; any other exception
is a bug and is not caught. A combo's choice is applied after the combo is
closed, so that a view failing in a setter leaves no ImGui pair open.

**The page's state needs no library and exists without it**: the scheme of
each pane, the face set, the size, the theme, the split and the parsed
markdown (`ThemesPage.parsed`) are all there with no view, and the four
setters work on them.

`ThemesPage.renderer` is `"TypesetView"` while the panes have views and
`"none"` when they do not; `reason` is then why.

Nothing of the old views is imported by this module, at import or later.
**One thing of the old core can be reached, and only when a theme is made
before the library has its fonts**:
`Theme.at_pixel_height` measures the regular face (ascent, descent, the
widest list marker) to turn a pixel height into an em, and its measuring
source is `PageContext.metrics` -- by default
`advtext.ui.pages.face_metrics`. The page makes its first theme in its
constructor, before there is a window, and that one is measured by
`advtext.style.fontlib_metrics`, which loads `advtext.style` and
`advtext.fontlib`. Every theme made once `typesetter.load_fonts()` has
succeeded (a slider moved, a face table chosen) is measured by the
library and loads nothing; the two give the same theme
(`advtext.typeset_metrics`).

## What a change is, and what it costs

- **palette**: `set_palette`, and the code blocks get new inks. The link ink
  is in the runs, so every block is described again (not parsed) and the
  library is given a new document.
- **faces, size**: a new `Theme`, ONE `parse_markdown`, and
  `set_theme(theme, parsed)` on both views: a new library document in each.
- **split on**: the first pane narrows and the second view is drawn; the
  library lays out again what each window shows.
- **split off**: the first pane widens and the second view is kept, undrawn;
  the same, in the first.

So **a palette change is not free and coming straight back is not either**:
the library keeps no second layout, and nothing here caches one. The last
frame's bill is on the page (`ThemesPage.last`, a `Retypeset`, counted from
the views) and the most recent one of each cause is kept
(`ThemesPage.bills`). What a bill counts is the frame of the change only: the
library lays a block out when a window first reaches it, so the rest of the
cost is paid as the reader scrolls and is on no bill. The hidden second pane
has no library document at all until it is first shown.

The markdown is parsed once per theme and the result handed to both views.

## The face sets, the size, and the reference line

**The face sets are roles rearranged, and that is all that is served.** The
library draws each role from the file `typesetter.load_fonts()` registered
for it; a theme whose `Faces` put `Face.CODE` in the regular role is
described with the code role and drawn in the code file. A theme that named
another font FILE would not be.

`Theme.at_pixel_height(h)` sizes the running text so that the theme's regular
face is rastered `h` pixels tall -- `h` being ascent plus descent, the number
ImGui calls a font size. Only the running text lands there: the docstring of
`Theme.at_pixel_height` says why code in a mixed theme does not.

**The reference line** is pushed in the LIBRARY's font for the regular role
(`imtypeset.font_atlas_index`) when it has one, so it is the same raster the
pane's text is drawn from; `PageContext.fonts`' answer otherwise. Whether the two then
stand at one height is not asserted: `tests/test_page_themes.py` compares the
widths the two give one string.

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
from typing import TYPE_CHECKING, Any, Final

from advtext import typesetter
from advtext.description import FACE_ROLES
from advtext.primitives import Face
from advtext.theme import Align, BlockKind, Faces, Theme
from advtext.typeset_markdown import MarkdownCode, MarkdownDocument, parse_markdown
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.pages._syntax import SyntaxInks, plain_spans
from advtext.ui.palette import (
    DARK_PALETTE,
    DEFAULT_PALETTE,
    Palette,
    rgba,
)
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from advtext.style import MetricsResolver

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
    "Retypeset",
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
            },
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
            },
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

    def theme(
        self, height_px: float, px_per_inch: float, metrics: MetricsResolver | None = None
    ) -> Theme:
        """
        The theme whose running text is rastered `height_px` tall in `faces.regular`.

        `metrics` is `Theme.at_pixel_height`'s, and the page passes its
        context's: it measures the face, which is the one use of the old core
        this page has (the module docstring).
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
class Retypeset:
    """
    What one change cost, counted from the views that were drawn.

    `cause` is `"open"`, `"palette"`, `"faces"`, `"size"`, `"split"`, or
    `"width"` for a layout nothing on this page asked for (the window was
    resized). `documents` is how many times the markdown was
    parsed; `handed` how many times a view gave the library a whole document
    (`TypesetView.edits["set"]`); `blocks` how many blocks the drawn panes
    hold between them, and `laid_out` how many the library laid out in the
    frame of the change (`ViewStats.blocks_laid_out`: the ones a window
    showed; the rest are laid out when one reaches them, on no bill).
    """

    cause: str
    documents: int
    handed: int
    blocks: int
    laid_out: int

    def line(self) -> str:
        """
        The readout: one line, counts only.
        """
        return (
            f"last change: {self.cause} -- markdown parsed {self.documents}, "
            f"documents handed to the library {self.handed}, "
            f"blocks laid out in that frame {self.laid_out} of {self.blocks}"
        )


@dataclass(slots=True)
class Pane:
    """
    One view of the document, the scheme it is drawn in, and what it last laid out.

    `view` is a `TypesetView`, or `None` when the library is not drawing: the
    pane then still holds its scheme and its scroll position.
    """

    view: Any
    colours: Colours
    whole: bool = True
    """What the view's last `draw` answered."""
    width: float = 0.0
    """The width of the pane's content region at the last frame it was drawn, in pixels."""
    scroll: float = 0.0
    """Where the page expects this pane's scroll to be: where it last found or sent it."""
    catching_up: int = 0
    """Frames left in which a scroll the page asked for may still be on its way."""
    _counted: tuple[object, int, int, float] | None = field(default=None, repr=False)

    def colour_code(self) -> int:
        """
        Hand the view this pane's syntax inks for every code block. Returns the span count.

        Replaces whatever the blocks had, so it serves a new document and a new
        scheme alike. A document with no code block clears nothing and sets
        nothing. The spans are plain offsets into the block's text
        (`_syntax.plain_spans`). Zero with no view.
        """
        if self.view is None:
            return 0
        self.view.clear_colours()
        count = 0
        for number, block in enumerate(self.view.blocks):
            if isinstance(block, MarkdownCode):
                inks = plain_spans(block.text, self.colours.syntax, block.language)
                self.view.set_colours(number, inks)
                count += len(inks)
        return count

    def counted(self) -> tuple[int, int, int, bool]:
        """
        `(blocks, laid out, documents handed over, resized)` since this was last called.

        Read from the view after it has drawn: one call into the library
        (`TypesetView.stats`). The library's counter
        of blocks laid out belongs to one document and starts again with a
        new one, so a view that was given a new document counts from zero.
        `resized` is whether the pane's width is not the one counted last.
        """
        view = self.view
        stats = view.stats
        document = view.native_document
        handed = int(view.edits["set"])
        laid = int(stats.blocks_laid_out)
        before = self._counted
        self._counted = (document, laid, handed, self.width)
        if before is None:
            return (len(view.texts), laid, handed, False)
        was_document, was_laid, was_handed, was_width = before
        return (
            len(view.texts),
            laid - was_laid if document is was_document else laid,
            handed - was_handed,
            was_width != self.width,
        )


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
        """How many times the markdown was read (`parse_markdown`)."""
        self.last: Retypeset | None = None
        self.bills: dict[str, Retypeset] = {}
        self._cause: str | None = "open"
        self._built_now = 0
        self._agreed = 0.0
        self.theme = self._theme()
        self.parsed: MarkdownDocument = self._parse()
        """The markdown as read with the theme in use, shared by both panes."""
        self.panes: list[Pane] = [Pane(None, COLOURS[0]), Pane(None, COLOURS[1])]
        self.reason = _why_not()
        """Why nothing is drawn, when nothing is; empty while the views draw."""
        if not self.reason:
            try:
                for pane in self.panes:
                    pane.view = TypesetView(
                        self.parsed,
                        theme=self.theme,
                        palette=pane.colours.palette,
                        on_link=self.followed.append,
                    )
                    pane.colour_code()
            except TypesetUnavailable as exc:
                self._lose(str(exc))

    @property
    def typeset(self) -> bool:
        """Whether the panes have views: the library is drawing this page."""
        return self.panes[0].view is not None

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.typeset else "none"

    # -- building ----------------------------------------------------------

    def _theme(self) -> Theme:
        return self.face_set.theme(self.height_px, self.context.px_per_inch, self.context.metrics)

    def _parse(self) -> MarkdownDocument:
        self.documents_built += 1
        self._built_now += 1
        return parse_markdown(self.source, self.theme)

    def _lose(self, reason: str) -> None:
        """
        imtypeset stopped drawing: no pane has a view any more, and `reason` says why.

        The `Pane` objects are kept, with their schemes: the page's state is
        what it was, and it is drawn as one line.
        """
        for pane in self.panes:
            pane.view = None
        self.reason = reason

    @property
    def shown(self) -> tuple[Pane, ...]:
        """
        The panes that are drawn: one, or both when split.
        """
        return (self.panes[0], self.panes[1]) if self.split else (self.panes[0],)

    # -- the four changes --------------------------------------------------

    def set_colours(self, pane: int, colours: Colours) -> None:
        """
        Give a pane another scheme: the view's palette, and new inks for the code blocks.
        """
        target = self.panes[pane]
        if target.colours is colours:
            return
        target.colours = colours
        if target.view is not None:
            # Now and not at the next draw, so that a hidden pane is ready too.
            target.view.set_palette(colours.palette)
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
        # One parse for both views; a view given a document holds no source
        # to read again, and gives up its inks with its blocks.
        self.parsed = self._parse()
        for pane in self.panes:
            if pane.view is not None:
                pane.view.set_theme(self.theme, self.parsed)
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

    def account(self) -> Retypeset | None:
        """
        Close the books on a frame: what the panes laid out, and why.

        Call once after the panes have been drawn. Returns the frame's
        `Retypeset` if a change was made or the width changed, else `None`;
        either way `last` is the most recent one. `None` with no views:
        nothing was laid out, and the cause waits.

        Blocks the library lays out because a window reached them for the
        first time are the reader's scrolling and are on no bill.
        """
        if not self.typeset:
            return None
        blocks = laid = handed = 0
        resized = False
        for pane in self.shown:
            pane_blocks, pane_laid, pane_handed, pane_resized = pane.counted()
            blocks += pane_blocks
            laid += pane_laid
            handed += pane_handed
            resized = resized or pane_resized
        if self._cause is None and not resized:
            return None
        bill = Retypeset(
            cause=self._cause or "width",
            documents=self._built_now,
            handed=handed,
            blocks=blocks,
            laid_out=laid,
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
        if not self.typeset:
            _say_why_not(self.reason)
            return
        try:
            self._frame()
        except TypesetUnavailable as exc:
            # Whatever raised drew no text: what was drawn before it is this
            # frame, and the page is the one line from the next.
            self._lose(str(exc))

    def _frame(self) -> None:
        """
        The frame through imtypeset. `TypesetUnavailable` is the caller's to catch.

        Every pair opened here is closed on the way out of an exception, so
        the caller's handler leaves ImGui's stacks as it found them.
        """
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
            try:
                self._follow_scroll(pane, leader)
                pane.width = float(imgui.get_content_region_avail().x)
                pane.view.debug = self.context.debug
                pane.whole = pane.view.draw(palette=pane.colours.palette)
            finally:
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
        picked: FaceSet | None = None
        if imgui.begin_combo("##advtext-themes-faces", self.face_set.label):
            for face_set in FACE_SETS:
                if imgui.selectable(face_set.label, face_set is self.face_set)[0]:
                    picked = face_set
            imgui.end_combo()
        if picked is not None:
            # After the combo is closed: a setter reaches the views.
            self.set_face_set(picked)
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
        imgui.push_font(self.sample_font(), self.height_px)
        imgui.text_unformatted(self.sample())
        imgui.pop_font()
        imgui.end_child()

    def sample_font(self) -> Any:
        """
        The font the reference line is pushed in: the regular face's, or `None` for ImGui's own.

        The LIBRARY's font for that role, by its place in the atlas, so the
        reference is the raster the pane's text comes from; what the context
        has for the face when the library has none, and when it is not
        drawing (it is not asked then).
        """
        face = self.face_set.faces.regular
        if not self.typeset:
            return self.context.fonts(face)
        from imgui_bundle import imgui

        module = typesetter.module()
        try:
            index = None if module is None else module.font_atlas_index(FACE_ROLES[face.name])
        except Exception:  # noqa: BLE001 -- no font from the library is ImGui's own
            index = None
        fonts = imgui.get_io().fonts.fonts
        if index is not None and 0 <= index < len(fonts):
            return fonts[index]
        return self.context.fonts(face)

    def sample(self) -> str:
        """
        The reference line: ordinary ImGui text, in the regular face, at the slider's size.
        """
        return f"imgui.text at {self.height_px:.1f} px, the size the running text is set to"

    def _colours_combo(self, label: str, pane: int) -> None:
        from imgui_bundle import imgui

        current = self.panes[pane].colours
        imgui.set_next_item_width(120.0)
        picked: Colours | None = None
        if imgui.begin_combo(label, current.name):
            for colours in COLOURS:
                if imgui.selectable(colours.name, colours is current)[0]:
                    picked = colours
            imgui.end_combo()
        if picked is not None:
            # After the combo is closed: a setter reaches the view.
            self.set_colours(pane, picked)


PAGE = PageSpec(
    name="Themes",
    order=110,
    factory=ThemesPage,
    group="Embedding",
    caption="one document under four palettes, three face sets and any pixel size",
    options=("split",),
    shots=("", "split"),
)

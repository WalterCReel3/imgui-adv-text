r"""
The interactive widget: a laid-out document, scrolled, and selectable with the mouse.

**`draw` has now been executed and photographed.** `DISPLAY=:1` is live here,
`scripts/shot.py` runs the real app and grabs the window, and the numbers quoted
under "The page" below were read out of a running frame rather than reasoned
about. What is still unexercised by anything is the mouse: nothing in this
environment synthesises a click, so `_handle_mouse` and `_handle_copy` have run
sixty times a second with `is_mouse_clicked` false and no further.

This is where the project's whole argument cashes out. pptmstr records that ImGui
text is not selectable and calls that "a real gap in ImGui, not a workaround
failing" (`pptmstr/ui/transcript_pane.py:14-16`), and works around it by copying
whole blocks from a context menu (`rich_pane.py:417-421`). The gap is real *for a
widget*, because the widget owns the layout and never says where a glyph landed.
We computed every glyph position ourselves, so hit testing is arithmetic over
data we already have, and `advtext.selection` -- which is pure, and tested --
does all of it. This module converts mouse coordinates into that module's
coordinates and draws what it hands back. That is deliberately the whole job.

## Relayout happens on resize, not per frame

`compose` runs the total-fit line breaker over every paragraph. That is a
paragraph-level optimisation with an active-node list behind it, and it is far
too expensive to run sixty times a second: on a page of prose it is milliseconds,
not microseconds. So the composed box, the shipped command list and the
selection index are cached and rebuilt **only when the width changes**.

Two consequences worth stating because the next reader will otherwise guess:

- Scrolling does **not** relayout. The child window scrolls the drawn output; the
  document's own coordinates never move.
- A selection survives a resize as *boundary indices*, which is the right thing:
  the reading order does not change when the measure does, so the same words stay
  selected and only the rectangles move. That falls out of `advtext.selection`
  addressing items by index rather than by position, and is the reason it does.

## The page, and why the measure is not the window

The document is set on a **sheet** narrower than the window and centred in it,
not on the whole content region. `page_for` is the arithmetic and carries the
typographic argument; the two things it fixes are worth stating here because
both were found by looking at a screenshot and neither is visible from a test.

*The measure was the window.* At the 1100 px demo size the content region is
1070 px, which is 5.15 alphabets of the body face and 145 to 156 characters a
line -- more than twice the upper bound anyone recommends. It read as a debug
view because 150-character lines are what a debug view has.

*And the margin was zero.* With the measure set to the entire content region the
last glyph of a justified line lands within a pixel of the child window's clip
rectangle. Measured in a running frame: content region 1070 px at `origin.x` 8,
clip rectangle right edge 1078, glyph ink reaching column 1077 of a sheet whose
last white column is 1077. Nothing is actually cut -- ImGui's own clip predicate
(`trunc(x) + glyph.X1 > clip.z`) rejects zero of the 3443 glyphs the sample
carried when this was measured -- it ships 4362 today -- and the worst
ink overhang past the advance box is 0.586 px on an `r` -- but a letter with no
white after it and a scrollbar immediately behind it photographs as a sliced
letter, which is how this was reported. The margin removes the condition rather
than the symptom.

A hypothesis that turned out to be **wrong**, recorded so it is not re-tried:
that `get_content_region_avail().x` is measured before the child's scrollbar is
subtracted. It is not. Frame 1 reports 1084 with no scrollbar and a clip rect to
match; from frame 2 on it reports 1070 with a 14 px scrollbar and a clip rect to
match. ImGui and this module agreed all along; they simply agreed on a number
with no margin in it.

## Where the mouse goes

An `invisible_button` claims the document's rectangle after the draw list has
written to it. The draw list writes pixels without advancing the cursor
(`pptmstr/ui/inbox.py:722,785` had to do the same with `dummy`), so without it
everything below would be drawn on top of the document. `invisible_button` rather
than `dummy` because it also takes the mouse: hovering it suppresses the window
drag that would otherwise start when a user drags to select.

Granularity is state and not a gesture. A drag that began as a double click keeps
selecting whole words as it extends, which is what every text system does and is
why `advtext.selection.Granularity` is held here across frames.

Deliberately out of scope: a caret (there is no insertion point -- this is a
reader, not an editor), keyboard navigation, find, and any editing at all.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from advtext.backends.imgui_draw import DrawStats, FaceFont, Palette, draw
from advtext.markdown import Document
from advtext.nodes import Box, CharNode
from advtext.pack import CharMeasure
from advtext.selection import Granularity, Selection, SelectionModel
from advtext.shipout import DrawCmd, Point, ship
from advtext.style import BlockKind, Theme
from advtext.ui import CommandIndex, LayoutCache, Viewport, compose, visible_rects
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "MEASURE_ALPHABETS",
    "MIN_MARGIN_LEADINGS",
    "TEXT_BLOCK_FRACTION",
    "DocumentView",
    "Layout",
    "Page",
    "alphabet_length",
    "page_for",
    "text_margin",
]

# Below this the line breaker has nothing to work with and every line is
# overfull. A window narrower than this is a window being resized through zero.
MIN_WIDTH_PX = 80.0

MEASURE_ALPHABETS = 2.25
"""
The widest measure the page will set, in lowercase alphabets of the body face.

Bringhurst's rule (`The Elements of Typographic Style` 2.1.2) is that a
single-column measure of **two to three alphabets** -- the length of `abc...z`
set in the text face at the text size -- gives the 45 to 75 characters a line
that a reader handles comfortably, and that 66 characters, counting letters and
spaces alike, is the figure to aim at. Past the top of that band the sweep back
to the start of the next line stops being reliable and the eye reads a line
twice.

An alphabet is a *measurement of this font*, not a constant: `alphabet_length`
adds up the real advances the layout engine itself would use, so a theme at
another size or on another face moves the measure with it. Roboto at the 16 px
body comes to 207.55 px an alphabet, and the measure here is 467 px.

**The two halves of the rule disagree for this face, and the coefficient is set
by the half that can be measured.** "Two to three alphabets" and "45 to 75
characters" are the same statement only for the character mix Bringhurst had in
mind. Roboto's lowercase is wide against its space, so counting the glyphs and
interword glues on lines this project actually broke gives:

    2.00 alphabets   53 to 62 characters
    2.25 alphabets   58 to 70 characters, mean 65
    2.50 alphabets   70 to 78 characters
    3.00 alphabets   87 to 91 characters

Three alphabets -- inside Bringhurst's *alphabet* band -- is thirty characters
past the end of his *character* band. The character count is the quantity the
readability claim is about, so it wins, and **2.25 is the coefficient whose
measured lines centre on the 66 he names**. `tests/test_document_view.py`
recomputes that table rather than quoting it, so a font change that moved these
numbers would be a failure and not a stale comment.

The choice costs something and it is not free to reverse. Neither a table nor a
fenced code block is line-broken, so both are as wide as their content and a
narrow measure is a measure they overflow: `demo/sample.md`'s table is 520 px
against a 467 px measure. The margin absorbs it -- 117 px at the demo width, and
`test_a_table_wider_than_the_measure_still_lands_inside_the_sheet` pins that --
but a measure much narrower than this would push it off the paper.

For scale, the content region of the 1100 px demo window is 1070 px: 5.15
alphabets, and 145 to 156 characters a line, which is where the demo was.
"""

TEXT_BLOCK_FRACTION = 2.0 / 3.0
"""
How much of the sheet's width the text block occupies; the rest is margin.

The Van de Graaf canon puts the text block of a medieval codex at two thirds of
the page width, with a one-ninth inner margin and a two-ninths outer one. A
scrolling window has no spread and no gutter, so there is no inner and outer
here; symmetrising the canon's total margin of one third gives **one sixth of
the sheet on each side** and keeps the two-thirds text block that is the part
anyone can point at in a printed book.

A proportion rather than a pixel count on purpose. It is the one page-level
number here that is a choice rather than a measurement, and expressing it as a
ratio of a width that *is* measured means it never has to be retuned for a
different body size, a different face or a different window.

**It is the rule for a sheet that got the width it asked for, and only that.**
When the window is narrower than the ideal sheet, taking a third of the sheet
for margin makes the *text block* absorb the entire shortfall, and the measure
falls below the band `MEASURE_ALPHABETS` documents. `text_margin` is the
correction, and it leaves this constant alone.
"""

MIN_MARGIN_LEADINGS = 3.0
"""
The narrowest side margin `text_margin` will set, in body leadings.

**Measured, not chosen.** A margin has one hard duty beyond looking like a page:
it has to absorb the material the line breaker cannot break, because a table or
a fenced code block is as wide as its content and nothing narrows it. Shipping
out `demo/sample.md` at this project's own 2.25-alphabet measure and taking the
furthest ink past the right edge of the text block gives **61.0 px** of
overhang -- the table `MEASURE_ALPHABETS` already names. Against the 21.6 px
body leading that is **2.82 leadings**, and three is the next whole one above
it. `tests/test_document_view.py::test_the_minimum_margin_covers_the_widest_
unbreakable_object_the_demo_ships` recomputes the 61 px from the real document
rather than quoting it, so a demo file that grew a wider table would be a
failure here and not a stale comment.

In leadings rather than pixels for the reason `GUTTER_LEADINGS` is: the leading
is measured from the theme, so a larger body size widens this by exactly as much
as it widens the object it has to cover.

This is a *floor*, never a target. `text_margin` takes the smaller of it and the
Van de Graaf margin, so on a sheet too narrow to afford even three leadings the
canon still wins and the margin shrinks with the page rather than eating it.
"""


def text_margin(sheet: Scaled, *, ideal_body: float, leading: Scaled) -> Scaled:
    """
    The side margin for a sheet of this width, given the text block it wants.

    Three quantities, and the rule is one `min` of two of them:

    - **The canon margin**, `(1 - TEXT_BLOCK_FRACTION) / 2` of the sheet. Right
      when the sheet is the width the text asked for.
    - **The surplus**, half of whatever the sheet has over `ideal_body`. On a
      sheet that got its ideal width these two are the *same number* -- the
      canon is defined as the sheet less its ideal text block -- so the rule is
      continuous at the boundary and changes nothing above it.
    - **`MIN_MARGIN_LEADINGS`**, the floor, which stops the surplus from taking
      the margin to zero on a sheet that cannot afford the ideal text block at
      all.

    So: `min(canon, max(floor, surplus))`.

    **What it buys, and it is the whole reason this is not just the canon.**
    Below the ideal sheet the canon makes the text block pay the entire
    shortfall. On the Columns tab at three columns in a 1100 px window that put
    the measure at **1.08 alphabets, a mean of 28.9 characters a line**, against
    the 2.00-alphabet / 53-character floor `MEASURE_ALPHABETS` derives from
    Bringhurst. Under this rule the same window gives **1.44 alphabets, 39.2
    characters** -- still under the floor, because 1070 px of content region
    genuinely cannot hold three comfortable columns, but the margin is no longer
    taking width the text needed more. At 1600 px the same tab goes from 1.64
    alphabets to the **full 2.25**: the surplus term gives the text block its
    ideal width first and leaves the canon only what is over.

    The outer `min` is what keeps this honest on a very narrow window: when the
    canon margin is itself less than the floor, the canon wins. A floor that
    overrode it would grow the margin as the window shrank.
    """
    canon = round(sheet * (1.0 - TEXT_BLOCK_FRACTION) / 2.0)
    surplus = round((sheet - ideal_body) / 2.0)
    return min(canon, max(round(leading * MIN_MARGIN_LEADINGS), surplus))


@dataclass(frozen=True, slots=True)
class Page:
    """
    Where the sheet sits inside the content region, and how wide the text on it is.

    All four fields are scaled points measured from the left edge and the top of
    the content region, so nothing here knows about pixels or about ImGui. That
    is what lets `page_for` be exercised by `tests/test_document_view.py` with no
    window at all: a margin is arithmetic.

    `head` is the air above the first line and below the last. It is not called a
    margin because it is not one -- there is no page height to take a fraction of
    (`docs/status.md` section 3 records page breaking as deliberately absent, so
    the document is one continuous scroll), and a vertical canon needs a page
    bottom to measure from. What it is instead is one line of the body leading,
    which keeps the first baseline on the same rhythm as every baseline under it.
    """

    offset: Scaled
    """From the content region's left edge to the sheet's left edge."""
    width: Scaled
    """The sheet: the white rectangle, margins included."""
    margin: Scaled
    """The white left and right of the text block, inside the sheet."""
    head: Scaled
    """The white above the first line and below the last, inside the sheet."""

    @property
    def measure(self) -> Scaled:
        """
        The width the document is broken to: the sheet less both margins.

        Both, and the distinction is the whole point of the field -- a page that
        subtracted one margin would centre nothing and would leave the right edge
        exactly where it was.
        """
        return self.width - 2 * self.margin

    @property
    def text_offset(self) -> Scaled:
        """
        From the content region's left edge to the text block's left edge.
        """
        return self.offset + self.margin

    def sheet_height(self, content_height: Scaled) -> Scaled:
        """
        The sheet's full height for a document of this height, head and foot included.
        """
        return content_height + 2 * self.head


def alphabet_length(theme: Theme, measure: CharMeasure) -> Scaled:
    """
    The width of `abcdefghijklmnopqrstuvwxyz` set in the theme's body face.

    Bringhurst's unit for a measure, and this project can take it rather than
    assume it: the advances are the same ones `hpack` will use, resolved through
    the view's own `CharMeasure`, so the number cannot drift from the layout it
    is sizing. A theme at a larger body size returns a longer alphabet and the
    page widens by exactly as much as the type grew.

    The body face is the paragraph style's, not a face named here. Headings are
    set larger and would give a measure nobody reads a paragraph at.
    """
    font = theme.style(BlockKind.PARAGRAPH).font.key
    return sum(
        measure(CharNode(font=font, codepoint=ord(letter))).width
        for letter in string.ascii_lowercase
    )


def page_for(available: Scaled, *, alphabet: Scaled, leading: Scaled) -> Page:
    """
    The sheet for a content region of this width: centred, and never wider than the measure wants.

    Two regimes, and the switch between them is a `min`:

    - **Wider than the ideal sheet.** The sheet stops growing at
      `MEASURE_ALPHABETS` alphabets of text plus its margins, and the surplus
      becomes space either side of it. Letting the measure keep growing is what
      the demo did before this and it is why its lines ran to 150 characters.
    - **Narrower.** The sheet is the whole content region and the margin is
      `text_margin`: the canon's share of it while the sheet can still afford
      the ideal text block, and the surplus over that block once it cannot, down
      to a floor of `MIN_MARGIN_LEADINGS`. So the page keeps its proportions as
      the window shrinks rather than collapsing to text against an edge, but it
      stops making the *measure* pay for keeping them.

    The margin is never zero for a positive `available`, which is the other
    defect this fixes. With the measure set to the entire content region the last
    glyph of every justified line lands within a pixel of the child window's clip
    rectangle -- measured at 1070 px on the 1100 px demo window, ink reaching
    column 1077 of a page that ends at 1077 -- and a letter with no white after it
    reads as a sliced letter even when, as here, nothing is actually cut.

    An `alphabet` of zero -- a degenerate `CharMeasure` that returns nothing --
    falls back to the full content region rather than to a sheet of width zero.
    A blank window is a worse failure than a wide one.
    """
    ideal_body = alphabet * MEASURE_ALPHABETS
    ideal_sheet = round(ideal_body / TEXT_BLOCK_FRACTION)
    sheet = min(available, ideal_sheet) if ideal_sheet > 0 else available
    margin = text_margin(sheet, ideal_body=ideal_body, leading=leading)
    return Page(offset=(available - sheet) // 2, width=sheet, margin=margin, head=leading)


@dataclass(frozen=True, slots=True)
class Layout:
    """
    Everything derived from one width, cached together because it all expires together.

    Three things that must agree: the box the breaker produced, the commands
    ship-out flattened it to, and the index selection queries. Keeping them in one
    frozen record makes "the layout is stale" a single reference swap rather than
    three fields that can be half-updated.
    """

    width: Scaled
    box: Box
    index: CommandIndex
    model: SelectionModel

    @property
    def cmds(self) -> tuple[DrawCmd, ...]:
        """
        Every command in the document, uncalled by any viewport.

        The whole list and not a culled one: the selection model is built from
        this, and reading-order indices have to be dense over the document or a
        selection that runs off the bottom of the window copies the wrong text.
        Culling happens at the draw call and nowhere earlier.
        """
        return self.index.cmds

    @property
    def height(self) -> Scaled:
        """
        The document's full extent, top of the first line to bottom of the last.
        """
        return self.box.height + self.box.depth


@dataclass(slots=True)
class DocumentView:
    """
    A scrollable, selectable view of one markdown document.

    Mutable, unlike almost everything else in this project, and for the reason
    `advtext.pack` gives about `Store` in pptmstr's `STYLE.md`: this *is* the
    imperative shell. It holds a cache and three pieces of interaction state, and
    every decision it makes is delegated to a pure module.
    """

    document: Document
    theme: Theme
    measure: CharMeasure
    px_per_inch: float = DEFAULT_PX_PER_INCH
    debug: bool = False

    _layout: Layout | None = field(default=None, init=False)
    # The theme's alphabet length, measured once. It depends on the theme and the
    # measure and on nothing that changes per frame, but measuring it costs
    # twenty-six `CharMeasure` calls and `draw` runs sixty times a second.
    _alphabet: Scaled | None = field(default=None, init=False)
    # Survives `invalidate`, unlike `_layout`, and that is the point of it: a
    # caller that changed one block of the document drops the whole layout and
    # this re-breaks only the block that changed. `advtext.ui.LayoutCache` has
    # the measurement and the honest account of what it does not buy.
    _blocks: LayoutCache = field(default_factory=LayoutCache, init=False)
    _selection: Selection = field(default=Selection(0, 0), init=False)
    _anchor: Point = field(default=Point(0, 0), init=False)
    _granularity: Granularity = field(default=Granularity.CHARACTER, init=False)
    _dragging: bool = field(default=False, init=False)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def layout_for(self, width: Scaled) -> Layout:
        """
        The cached layout for a width, recomputing only when the width changed.

        The equality test is on the scaled-point width, not the pixel one: a
        window dragged by a sub-pixel amount produces the same measure and must
        not re-break the whole document.
        """
        cached = self._layout
        if cached is not None and cached.width == width:
            return cached
        box = compose(self.document, self.theme, width, self.measure, cache=self._blocks)
        cmds = tuple(ship(box, Point(0, box.height), measure=self.measure))
        fresh = Layout(
            width=width,
            box=box,
            index=CommandIndex.of(cmds),
            model=SelectionModel.from_commands(cmds),
        )
        self._layout = fresh
        return fresh

    def page(self, available: Scaled) -> Page:
        """
        The sheet this view would set inside a content region of this width.

        Public because the geometry is what a caller has to agree with: anything
        drawing beside the document -- a rule, a header, a second column -- has to
        put itself on the same sheet, and re-deriving the offset at the call site
        is how two of them end up a pixel apart.
        """
        if self._alphabet is None:
            self._alphabet = alphabet_length(self.theme, self.measure)
        return page_for(
            available,
            alphabet=self._alphabet,
            leading=self.theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width,
        )

    def invalidate(self) -> None:
        """
        Drop the cache, for a caller that changed the document or the theme.

        The alphabet goes with it. It is derived from the theme, and a caller
        swapping the theme is exactly the case that would otherwise keep setting
        the new type to the old page's measure.
        """
        self._layout = None
        self._alphabet = None

    @property
    def selection(self) -> Selection:
        """
        What is currently selected, as reading-order boundaries.
        """
        return self._selection

    def selected_text(self) -> str:
        """
        The current selection as text, or the empty string if nothing is selected.
        """
        layout = self._layout
        if layout is None:
            return ""
        return layout.model.text(self._selection)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, *, fonts: FaceFont, palette: Palette | None = None) -> DrawStats:
        """
        Draw the document into the current window and handle the mouse over it.

        Call inside a scrolling child window; this claims the full sheet height,
        so the child's own scrollbar does the scrolling and no coordinate here
        ever changes.

        **The document is broken to `self.page(...)`'s measure, not to the content
        region.** The sheet is narrower than the window and centred in it, the
        text block is inset inside the sheet, and the origin every glyph, every
        highlight and every mouse coordinate is measured from is the text block's
        corner. See "The page" in the module docstring for what that fixed and
        `page_for` for how wide it is. It is also cheaper: the total-fit breaker
        has fewer feasible breakpoints per line at a narrower measure, and a cold
        reflow of `demo/sample.md` fell from 180ms to 143ms here when the measure
        went from the full 1070px region to the page's 467px.

        **Only the visible commands are issued.** Drawing every glyph in the
        document costs 19.8ms a frame on `demo/sample.md` -- over a 16.7ms budget
        on its own, with the layout cached and nothing recomputed -- and culling
        to the window halves it. `advtext.ui.CommandIndex` has the measurements
        and the argument for why this is the cost worth cutting rather than
        ship-out. The selection model is built from the *whole* list and is not
        culled, so a selection running past the bottom of the window still copies
        in full.
        """
        from imgui_bundle import imgui

        available = imgui.get_content_region_avail()
        width_px = max(available.x, MIN_WIDTH_PX)
        page = self.page(sp_from_px(width_px, self.px_per_inch))
        layout = self.layout_for(page.measure)

        region = imgui.get_cursor_screen_pos()
        sheet_x = region.x + px_from_sp(page.offset, self.px_per_inch)
        sheet_width_px = px_from_sp(page.width, self.px_per_inch)
        sheet_height_px = px_from_sp(page.sheet_height(layout.height), self.px_per_inch)

        # Everything below is positioned against the *text block's* top-left
        # corner rather than the content region's, because that is where the
        # document's own (0, 0) is. Hit testing, culling and the draw all take
        # this one point, so the margin cannot be applied to some of them and not
        # the others -- which is the failure mode of insetting the draw call
        # alone, where the text moves and the mouse does not.
        origin = imgui.ImVec2(
            sheet_x + px_from_sp(page.margin, self.px_per_inch),
            region.y + px_from_sp(page.head, self.px_per_inch),
        )
        viewport = self.viewport_in(origin.y, imgui.get_window_pos().y, imgui.get_window_size().y)

        colours = palette or Palette()

        # The sheet, before anything that sits on it. The ink is dark because the
        # page is light, so drawing the glyphs without this leaves black text on
        # ImGui's dark theme -- invisible rather than wrong, which is the worse
        # failure. Drawn to the document's full height so scrolling stays on
        # paper; ImGui clips it to the child window.
        #
        # It stops at the sheet rather than filling the content region, so a
        # window wider than the measure shows the child's own dark background
        # either side of it. That is the arrangement `Palette` already argues
        # for -- "dark chrome around a light page" -- and it needs no new colour:
        # the surround is the absence of a fill, not a fill of its own.
        imgui.get_window_draw_list().add_rect_filled(
            imgui.ImVec2(sheet_x, region.y),
            imgui.ImVec2(sheet_x + sheet_width_px, region.y + sheet_height_px),
            colours.page,
        )

        stats = draw(
            imgui.get_window_draw_list(),
            layout.index.visible(viewport),
            origin,
            fonts=fonts,
            palette=colours,
            highlights=visible_rects(layout.model.rects(self._selection), viewport),
            px_per_inch=self.px_per_inch,
            debug=self.debug,
        )

        # The draw list wrote pixels without advancing the cursor, so the space
        # has to be claimed or anything after this is drawn on top of it. A button
        # rather than a dummy: it also takes the mouse, which stops a select-drag
        # from dragging the window.
        #
        # The whole content region and the whole sheet, not the text block: a
        # drag that starts in the margin is still a drag on the document, and a
        # button narrower than the sheet would let it drag the window instead.
        imgui.invisible_button("##advtext-document", imgui.ImVec2(width_px, sheet_height_px))
        self._handle_mouse(layout, origin)
        self._handle_copy(layout)
        return stats

    def viewport_in(
        self, origin_y_px: float, window_y_px: float, window_height_px: float
    ) -> Viewport:
        """
        The band of the document a window shows, from three screen coordinates.

        `origin_y_px` is where the document's y = 0 sits on screen, which is the
        cursor position `draw` anchors to; the other two are the window's own
        rectangle. Subtracting gives a document-space offset that is **positive
        once the view has scrolled past the top** and negative before it, which
        is why this is subtraction and not `get_scroll_y`: a document drawn below
        other widgets starts partway down its window and a raw scroll offset
        would be wrong by exactly that much.

        Separated out and taking plain floats because it is the one piece of the
        draw path that is arithmetic rather than ImGui, and nothing in this
        environment can execute the rest of `draw`. `tests/test_document_view.py`
        exercises it directly.
        """
        return Viewport.of_pixels(
            top_px=window_y_px - origin_y_px,
            height_px=window_height_px,
            px_per_inch=self.px_per_inch,
        )

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _document_point(self, origin: imgui.ImVec2) -> Point:
        """
        The mouse, in the document's own scaled-point coordinates.
        """
        from imgui_bundle import imgui

        mouse = imgui.get_mouse_pos()
        return Point(
            sp_from_px(mouse.x - origin.x, self.px_per_inch),
            sp_from_px(mouse.y - origin.y, self.px_per_inch),
        )

    def _handle_mouse(self, layout: Layout, origin: imgui.ImVec2) -> None:
        """
        Press sets an anchor, drag extends, release finishes.

        The drag branch deliberately does not test `is_item_hovered`: a drag that
        leaves the document should keep extending the selection, which is what
        `SelectionModel.fragment_at` snapping to the nearest line is for.
        """
        from imgui_bundle import imgui

        point = self._document_point(origin)

        if imgui.is_item_hovered() and imgui.is_mouse_clicked(imgui.MouseButton_.left):
            # The scalar accessor, not `get_io().mouse_clicked_count[0]`. The
            # array-valued fields on `ImGuiIO` are nanobind ndarrays, and
            # exporting one needs numpy, which is not a dependency of this
            # project or of imgui-bundle. Indexing it raises `TypeError: could
            # not export nanobind::ndarray` on the first click rather than at
            # import, so nothing before the first frame can catch it.
            self._granularity = _granularity_for(
                imgui.get_mouse_clicked_count(imgui.MouseButton_.left)
            )
            self._anchor = point
            self._dragging = True
            self._selection = layout.model.select_at(point, point, self._granularity)
            return

        if self._dragging:
            self._selection = layout.model.select_at(self._anchor, point, self._granularity)
            if imgui.is_mouse_released(imgui.MouseButton_.left):
                self._dragging = False

    def _handle_copy(self, layout: Layout) -> None:
        """
        Ctrl+C puts the selection on the clipboard.

        This is the payoff, and it is three lines because `advtext.selection`
        already turned a range of reading-order indices into text -- including
        deciding that a soft wrap serialises as a space rather than a newline.
        """
        from imgui_bundle import imgui

        if self._selection.is_empty:
            return
        if imgui.get_io().key_ctrl and imgui.is_key_pressed(imgui.Key.c, False):
            imgui.set_clipboard_text(layout.model.text(self._selection))


def _granularity_for(clicks: int) -> Granularity:
    """
    One click selects characters, two words, three the whole visual line.

    ImGui reports the running click count rather than firing a separate
    triple-click event, so this is a lookup rather than three predicates. A count
    past three wraps back to a line, which is what an editor does.
    """
    if clicks >= 3:
        return Granularity.LINE
    if clicks == 2:
        return Granularity.WORD
    return Granularity.CHARACTER

r"""
The Find page: a search box over a long document, every match marked where it
is set, and next/previous that scroll the current one into view.

The document is `demo/sample.md` repeated (five times as the page opens;
`--tab find:20` asks for twenty), set once by an `advtext.ui.bare_view.BareView`
and never set again by anything this page does. Typing searches the text of the
blocks, not the glyphs on screen, and hands the view *colour spans*: a mark
behind each match, a stronger one behind the current match. The view applies
them when it draws; no line is re-broken and no unit re-shipped.

## Where the answers come from (all of it the library's)

This page first restated each of these over lower-level calls, because the
library had no call for it; what it needed is now `advtext.spans.FindIndex`
and three methods of the view, and the restatements are gone.

- **The search** is `FindIndex.of(document.blocks).find(needle, ...)`: every
  block's text built once, a `str.find` per block per keystroke, with the
  rules `advtext.spans.find_spans` states (a space finds a hard break in
  prose and not a line end in code).
- **A match** is an `advtext.spans.TextMatch`: a block number and a half-open
  range of that block's material, which is exactly a `ColourSpan`.
  `BareView.set_colours(block, spans)` marks it.
- **Where a match is**, on or off screen, is `BareView.span_rects`: one
  rectangle per line the match is on, so a match across a line break is one
  match with two rectangles.
- **Showing it** is `BareView.scroll_to(rect, align=1/3)`: nothing moves if
  the match is already in view with a margin, else its top goes a third of
  the way down the pane.

## What is found and not marked, and what is not searched

**A match inside a table cell is counted and not marked.** The index finds it
(`TextMatch.cell`) and `span_rects(..., cell=)` could say where it is, but a
colour span carries one block number and one range, so
`BareView.set_colours` has no way to mark a cell. The page says how many
matches it found and how many it marked rather than letting the count quietly
be short. Next/previous visits marked matches only.

**An inline formula is not searched**: the index leaves out what is inside a
box.

## Cost

`find_spans` rebuilds a block's text on every call (about 14 ms a needle on
the sample twenty times over); the index is built once (about 13 ms for the
same document) and a keystroke is a fraction of a millisecond to two. The
readout under the search box shows what the last keystroke cost, split into
the search and the handing over of marks, and counts the layouts rebuilt and
units built at an unchanged width since the page opened -- from
`UnitLayout.stats`, the layout's own account. A change of width re-breaks the
document and is not typing; it is counted apart.

**None of the readouts is a measure of quality** (`docs/visual-review.md`).
The two mark colours are this page's own chrome and nobody has judged them.

Options (`--tab find:...`): `case` opens with case matching on; an integer is
how many copies of the sample make the document.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats, rgba
from advtext.markdown import Document, build_document
from advtext.selection import Rect
from advtext.spans import ColourSpan, FindIndex, TextMatch
from advtext.ui.bare_view import MIN_WIDTH_PX, BareView
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.units import UnitLayout
from advtext.units import px_from_sp, sp_from_px

__all__ = [
    "CURRENT_MARK",
    "DEFAULT_COPIES",
    "DEFAULT_NEEDLE",
    "FALLBACK",
    "HIT_MARK",
    "PAGE",
    "TEXT_WIDTH_PX",
    "FindPage",
    "Finder",
    "Found",
    "Index",
    "Match",
    "document_of",
    "readouts",
    "search",
]

HIT_MARK: Final = rgba(0xE8, 0xB3, 0x39, 0x59)
"""
The mark behind a match. Not a palette role: the library's `Palette` has none for find.
"""

CURRENT_MARK: Final = rgba(0xF2, 0x7A, 0x1A, 0xD0)
"""
The mark behind the current match.
"""

DEFAULT_COPIES: Final = 5
DEFAULT_NEEDLE: Final = "glue"
"""
What the box holds as the page opens: a word the sample has in prose and in a table cell.
"""

TEXT_WIDTH_PX: Final = 600.0
"""
The widest the document is set, so the 1068 px body does not make 150-character lines.
"""

FALLBACK: Final = (
    "No `demo/sample.md` was found, so this paragraph is the whole document. It is "
    "long enough to break onto a few lines, and the word glue is in it twice so "
    "that the search box has something to find: glue.\n"
)


# ----------------------------------------------------------------------
# The search: pure, no ImGui, no view
# ----------------------------------------------------------------------


Match = TextMatch
"""One occurrence: `advtext.spans.TextMatch`. The name this page's tests know it by."""

Index = FindIndex
"""Every block's text, built once: `advtext.spans.FindIndex`."""


@dataclass(frozen=True, slots=True)
class Found:
    """
    What one search found: the matches that can be marked, and the ones that cannot.

    `matches` is in reading order. `cells` are the occurrences inside table
    cells, which are found and cannot be marked (the module docstring).
    """

    matches: tuple[TextMatch, ...] = ()
    cells: tuple[TextMatch, ...] = ()

    @property
    def in_cells(self) -> int:
        return len(self.cells)

    @property
    def total(self) -> int:
        return len(self.matches) + len(self.cells)


def search(index: FindIndex, needle: str, *, ignore_case: bool = True) -> Found:
    """
    `index.find`, parted into what the view can mark and what it cannot.
    """
    hits = index.find(needle, ignore_case=ignore_case)
    return Found(
        tuple(hit for hit in hits if hit.cell is None),
        tuple(hit for hit in hits if hit.cell is not None),
    )


SHOW_AT: Final = 1.0 / 3.0
"""
How far down the pane the top of a match is put when the pane has to move for it.
"""


# ----------------------------------------------------------------------
# The state: a view, a needle, the matches and which one is current
# ----------------------------------------------------------------------


def document_of(context: PageContext, copies: int, text: str | None = None) -> Document:
    """
    The page's document: `demo/sample.md` (or `text`) `copies` times over.
    """
    if text is None:
        text = demo_text("sample.md")
    if text is None:
        text = FALLBACK
    source = "\n\n".join([text] * max(copies, 1))
    return build_document(source, context.theme, context.metrics)


@dataclass(slots=True)
class Finder:
    """
    A search over one view's document: the needle, what it found, the current match.

    No ImGui. `search` and `step` are what a keystroke and a press of
    next/previous do; `observe` is called once a frame after the view has drawn
    and keeps the two counters the module docstring describes.
    """

    view: BareView
    timer: Callable[[], float] = time.perf_counter
    needle: str = ""
    ignore_case: bool = True
    found: Found = field(default_factory=Found)
    current: int | None = None
    """Index into `found.matches` of the current match, or `None` when there is none."""
    keystrokes: int = 0
    """Searches run: one for each edit of the box and each flip of the case checkbox."""
    search_ms: float = 0.0
    """What the last `search` took to find its matches."""
    mark_ms: float = 0.0
    """What the last `search` took to hand the marks to the view."""
    rebuilt: int = 0
    """Layouts built at an unchanged width since the first. Typing should leave this at zero."""
    reshipped: int = 0
    """Units those layouts composed and shipped (`UnitLayout.stats.built`)."""
    resized: int = 0
    """Layouts built because the width changed. Not typing's doing; counted apart."""
    index: Index = field(init=False)
    _spans: dict[int, tuple[int, int]] = field(default_factory=dict, init=False)
    _seen: UnitLayout | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.index = Index.of(self.view.document.blocks)

    # -- searching ------------------------------------------------------

    def search(self, needle: str, *, ignore_case: bool | None = None) -> Found:
        """
        Search for `needle`, mark every match, and keep the current one near where it was.

        The current match becomes the first at or after the place the previous
        current match started, so typing another letter of a word does not
        throw the reader back to the top. With no previous one it is the first.
        """
        began = self.timer()
        if ignore_case is not None:
            self.ignore_case = ignore_case
        before = None if self.current is None else self.found.matches[self.current]
        self.needle = needle
        self.found = found = search(self.index, needle, ignore_case=self.ignore_case)
        self.current = None
        if found.matches:
            self.current = 0
            if before is not None:
                place = (before.block, before.start)
                self.current = next(
                    (
                        number
                        for number, match in enumerate(found.matches)
                        if (match.block, match.start) >= place
                    ),
                    0,
                )
        searched = self.timer()
        self._mark_all()
        self.search_ms = (searched - began) * 1000.0
        self.mark_ms = (self.timer() - searched) * 1000.0
        self.keystrokes += 1
        return found

    def step(self, delta: int) -> Match | None:
        """
        Move the current match by `delta`, wrapping at both ends. Returns it, or `None`.
        """
        matches = self.found.matches
        if not matches or self.current is None:
            return None
        old = matches[self.current]
        self.current = (self.current + delta) % len(matches)
        new = matches[self.current]
        for block in {old.block, new.block}:
            self._mark(block)
        return new

    @property
    def match(self) -> Match | None:
        """
        The current match, or `None`.
        """
        return None if self.current is None else self.found.matches[self.current]

    def _mark_all(self) -> None:
        self.view.clear_colours()
        self._spans = {}
        matches = self.found.matches
        start = 0
        while start < len(matches):
            block = matches[start].block
            stop = start
            while stop < len(matches) and matches[stop].block == block:
                stop += 1
            self._spans[block] = (start, stop)
            self._mark(block)
            start = stop

    def _mark(self, block: int) -> None:
        start, stop = self._spans[block]
        matches = self.found.matches
        self.view.set_colours(
            block,
            [
                ColourSpan(
                    matches[number].start,
                    matches[number].end,
                    mark=CURRENT_MARK if number == self.current else HIT_MARK,
                )
                for number in range(start, stop)
            ],
        )

    # -- where the current match is --------------------------------------

    def rects(self) -> list[Rect]:
        """
        The current match's rectangles in the view's layout; empty with no match or no layout.
        """
        match = self.match
        if match is None:
            return []
        return self.view.span_rects(match.block, match.start, match.end)

    def place(self) -> Rect | None:
        """
        One rectangle to bring into view for the current match, in document scaled points.

        The extent of its rectangles; its block's, if it has none (its
        material could not be matched to what was shipped). `None` with no
        match or no layout.
        """
        match = self.match
        if match is None:
            return None
        rects = self.rects()
        if not rects:
            return self.view.block_rect(match.block)
        top = min(rect.y for rect in rects)
        bottom = max(rect.y + rect.height for rect in rects)
        return Rect(0, top, 0, bottom - top)

    def span_px(self) -> tuple[float, float] | None:
        """
        The current match's top and bottom in pixels below the document's top, or `None`.

        `place`, in pixels.
        """
        place = self.place()
        if place is None:
            return None
        ppi = self.view.px_per_inch
        return px_from_sp(place.y, ppi), px_from_sp(place.y + place.height, ppi)

    # -- what it cost ----------------------------------------------------

    def observe(self) -> None:
        """
        Compare the view's layout with the one seen last time. Call once a frame, after `draw`.
        """
        layout, seen = self.view.layout, self._seen
        if layout is None or layout is seen:
            return
        if seen is not None:
            if layout.width != seen.width:
                self.resized += 1
            else:
                self.rebuilt += 1
                # The layout's own account of what it built. A document
                # parsed again is given new `Unit` objects around the
                # commands it already had, and that is not shipping.
                self.reshipped += len(layout.stats.built)
        self._seen = layout

    @property
    def label(self) -> str:
        """
        `3 of 17`, `no matches`, or nothing for an empty needle.
        """
        if not self.needle:
            return ""
        if self.current is None:
            return "no matches"
        return f"{self.current + 1} of {len(self.found.matches)}"


def readouts(finder: Finder) -> tuple[str, ...]:
    """
    The lines under the search box: found against marked, then cost. Counts, no judgement.
    """
    found = finder.found
    marked = len(found.matches)
    cells = (
        f"{found.in_cells} more in table cells, found and not marked"
        if found.in_cells
        else "none in table cells"
    )
    return (
        f"marked {marked} of {found.total} found  ·  {cells} "
        "(a colour span cannot name a cell)  ·  formulae are not searched",
        f"last keystroke: search {finder.search_ms:.2f} ms, marks {finder.mark_ms:.2f} ms"
        f"  ·  {finder.keystrokes} keystrokes: {finder.rebuilt} layouts rebuilt, "
        f"{finder.reshipped} units re-shipped  ·  {finder.resized} resizes (not counted)",
    )


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


class FindPage:
    """
    The page: a `Finder` over a `BareView`, the search row, and the scrolling pane.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        count = context.count_for(PAGE.name)
        self.copies = DEFAULT_COPIES if count is None else max(count, 1)
        self.view = BareView(
            document=document_of(context, self.copies),
            theme=context.theme,
            measure=context.measure,
            px_per_inch=context.px_per_inch,
        )
        self.finder = Finder(self.view, ignore_case="case" not in context.options_for(PAGE.name))
        self.finder.search(DEFAULT_NEEDLE)
        self.finder.keystrokes = 0
        self.frames = 0
        self.scrolls = 0
        """How many times a step or a search asked the pane to scroll."""
        self.stats: DrawStats | None = None
        self.pane: tuple[float, float] | None = None
        """The scrolling pane's top and bottom on screen at the last frame, in pixels."""
        self._reveal = False
        self._refocus = False
        self._rearming = 0

    # -- what the controls do --------------------------------------------

    def type(self, needle: str) -> None:
        """
        What an edit of the search box does: search, and show the current match.
        """
        self.finder.search(needle)
        self._reveal = True

    def match_case(self, on: bool) -> None:
        """
        What the checkbox does: search again with case matching on or off.
        """
        self.finder.search(self.finder.needle, ignore_case=not on)
        self._reveal = True

    def step(self, delta: int) -> None:
        """
        What next (`+1`) and previous (`-1`) do: move the current match and show it.
        """
        if self.finder.step(delta) is not None:
            self._reveal = True

    def focus(self) -> None:
        """
        Give the search box the keyboard on the next frame.
        """
        self._refocus = True

    def shown(self) -> bool:
        """
        Whether the current match lay wholly inside the pane as of the last frame drawn.
        """
        origin, span, pane = self.view.origin, self.finder.span_px(), self.pane
        if origin is None or span is None or pane is None:
            return False
        return pane[0] <= origin[1] + span[0] and origin[1] + span[1] <= pane[1]

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts.
        """
        finder, stats = self.finder, self.stats
        layout = self.view.layout
        return [
            f"frames={self.frames} copies={self.copies} blocks={len(self.view.document.blocks)} "
            f"units={0 if layout is None else len(layout.placed)} "
            f"needle={finder.needle!r} marked={len(finder.found.matches)} "
            f"found={finder.found.total} cells={finder.found.in_cells} "
            f"current={-1 if finder.current is None else finder.current + 1} "
            f"rects={len(finder.rects())} shown={int(self.shown())} scrolls={self.scrolls} "
            f"keystrokes={finder.keystrokes} rebuilt={finder.rebuilt} "
            f"reshipped={finder.reshipped} resized={finder.resized} "
            f"unmapped={self.view.unmapped_blocks} "
            f"glyphs={0 if stats is None else stats.glyphs} "
            f"missing={0 if stats is None else stats.missing}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        self._controls(imgui)
        for line in readouts(self.finder):
            caption(line)
        imgui.separator()

        # The scrollbar is always there so the pane's width, and with it every
        # line break, does not depend on how long the document is.
        #
        # Padding is asked for by name. The demo's style gives a child no
        # border, and ImGui gives a child with no border no padding either:
        # measured in a window, the text began on the pane's top edge and, at
        # the end of the scroll, the last line's box ended 0.9 px *below* the
        # pane (ImGui keeps a whole number of pixels of content and the
        # document is 44204.9 px tall), so the last match was not wholly shown.
        imgui.begin_child(
            "##advtext-find-text",
            imgui.ImVec2(0.0, 0.0),
            imgui.ChildFlags_.borders.value | imgui.ChildFlags_.always_use_window_padding.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        view = self.view
        self.pane = (imgui.get_window_pos().y, imgui.get_window_pos().y + imgui.get_window_height())
        width_px = max(min(imgui.get_content_region_avail().x, TEXT_WIDTH_PX), MIN_WIDTH_PX)
        # Laid out before the scroll is decided, at the width `draw` is about
        # to choose: the match's place is asked of this layout.
        view.layout_for(sp_from_px(width_px, view.px_per_inch))
        if self._reveal:
            self._reveal = False
            place = self.finder.place()
            if place is not None:
                view.scroll_to(place, align=SHOW_AT)
        view.debug = self.context.debug
        self.stats = view.draw(fonts=self.context.fonts, palette=DARK_PALETTE, width_px=width_px)
        if view.scrolled:
            self.scrolls += 1
        self.finder.observe()
        imgui.end_child()

    def _controls(self, imgui: Any) -> None:
        finder = self.finder
        imgui.set_next_item_width(280.0)
        if self._refocus:
            self._refocus = False
            imgui.set_keyboard_focus_here()
        changed, needle = imgui.input_text_with_hint(
            "##advtext-find-needle", "find in the document", finder.needle
        )
        # Enter ends the edit, so it is read on the frame the box lets go of
        # the keyboard, and the box is given the keyboard back: Enter, Enter,
        # Enter walks the matches. Only while the box was being typed in --
        # ImGui's navigation rests on the first item of a window whether or
        # not anybody put it there, and Enter with a selection in the text
        # below must not move the search.
        #
        # Getting the keyboard back takes a frame or two, and a second Enter
        # inside them is still an Enter in the box (measured in frames: one
        # pressed two frames after the last was dropped). `_rearming` counts
        # those frames down and ends early once the box is active again.
        entered = (imgui.is_item_deactivated() or self._rearming > 0) and (
            imgui.is_key_pressed(imgui.Key.enter, False)
            or imgui.is_key_pressed(imgui.Key.keypad_enter, False)
        )
        self._rearming = 0 if imgui.is_item_active() else max(self._rearming - 1, 0)
        if changed and needle != finder.needle:
            self.type(needle)
        if entered:
            self.step(-1 if imgui.get_io().key_shift else 1)
            self._refocus = True
            self._rearming = 3
        imgui.same_line()
        if imgui.button("Previous"):
            self.step(-1)
        imgui.same_line()
        if imgui.button("Next"):
            self.step(1)
        imgui.same_line()
        flipped, on = imgui.checkbox("Match case", not finder.ignore_case)
        if flipped:
            self.match_case(on)
        imgui.same_line()
        imgui.text(finder.label)
        imgui.same_line()
        debug_toggle(self.context)


PAGE = PageSpec(
    name="Find",
    order=130,
    factory=FindPage,
    group="Embedding",
    caption="a search box over a long document: every match marked, next and previous",
    options=("case",),
    shots=("",),
)

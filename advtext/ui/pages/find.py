r"""
The Find page: a search box over a long document, every match marked where it
is set, and next/previous that scroll the current one into view.

The document is `demo/sample.md` repeated (five times as the page opens;
`--tab find:20` asks for twenty).

## What draws

An `advtext.ui.typeset_view.TypesetView` over the markdown SOURCE, read by
`advtext.typeset_markdown` with no node material. There is no other renderer.

The view is made once, when the page is built, if `advtext.typesetter.ready()`
(the app's font callback loaded the library's fonts). When it is not, the
page draws ONE wrapped line saying why (`advtext.ui.pages.typeset.why_not`,
drawn by that module's `say_why_not`) and nothing else: no box, no pane. A
view call that raises `TypesetUnavailable` anywhere in a frame (the library
failed and was switched off) has drawn no text: the page drops the view,
keeps the sentence, and is that one line from the next frame on. The
exception does not leave `draw`, so the app's traceback page is not reached;
any other exception is a bug and is not caught.

**The search needs no library and exists without it.** The index is built
from block descriptions (`MarkdownConverter.describe`), so `finder` holds the
needle, the matches and the current one whether or not anything is drawn;
only the marks and the scrolling are the view's.

`FindPage.renderer` is `"TypesetView"` while there is a view and `"none"`
when there is not; `reason` is then why.

Nothing of the old layout core or the old views is imported by this module,
at import or later (`tests/test_page_document.py` holds the first,
`tests/test_page_find.py` the second).

## How it works

- **The search** is `advtext.typeset_find.FindIndex` over the block
  descriptions (`MarkdownConverter.describe` of the view's own blocks; the
  page checks that their texts ARE the view's, and marks nothing if they are
  not) and `advtext.typeset_find.Finder`, wrapped here as `TypesetFinder` for
  the timings the readout shows.
- **A match** is `(block, start, end)` into the block's `str`. The marks are
  plain tuples (`Finder.marks()`), handed to `TypesetView.set_marks` when the
  finder's `revision` moved and never per frame.
- **Showing it** is `TypesetView.scroll_to(block, start, align=1/3)`: the
  view asks the library for the caret rectangle at that offset, so the LINE
  holding the match is what is brought into view, however long the block
  (`tests/test_page_find.py` steps to a match 400 lines into one code block).
  A block's place is an estimate until what is above it has been laid out, so
  the view corrects itself over the next few frames (`scrolls` counts the
  frames in which the pane was moved, not the requests).
- **Where a match is** is `TypesetView.span_rects`, pixels from the
  document's corner: `shown()` reads it.

## What is searched, and what is marked

Whatever `advtext.typeset_find.FindIndex.of` indexes. That includes table
cells, and **a match in a cell is marked** like any other. An inline
formula's source is not searched.

**At most `advtext.typeset_find.MARK_LIMIT` marks are handed over** (the
first of them and the current one); the readout says "marked N of M found".

The totals are the ones the old page's index (`advtext.spans.FindIndex`)
found in the same document, measured for nine needles on 2026-10-11 before
that page body was removed; `tests/test_page_find.py` holds them as literals.

## Cost

The index is built once and a keystroke is a `str.find` per block. The
readout under the search box shows what the last keystroke cost, split into
the search and the handing over of marks (making the tuples and `set_marks`
checking their shape; the view packs them for the library at its next draw,
which is not in the number), then the view's own counts: edits of the
document (typing should leave it at zero) and blocks laid out so far. One
more call into the library a frame, for that readout.

**None of the readouts is a measure of quality** (`docs/visual-review.md`).
The two mark colours are this page's own chrome and nobody has judged them.

Options (`--tab find:...`): `case` opens with case matching on; an integer is
how many copies of the sample make the document.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Final

from advtext import typesetter
from advtext.typeset_find import MARK_LIMIT
from advtext.typeset_find import Finder as _TextFinder
from advtext.typeset_find import FindIndex as _TextIndex
from advtext.typeset_find import Match as TextRange
from advtext.typeset_markdown import MarkdownConverter, parse_markdown
from advtext.ui.ownership import MIN_WIDTH_PX
from advtext.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from advtext.ui.palette import DARK_PALETTE, rgba
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView

__all__ = [
    "CURRENT_MARK",
    "DEFAULT_COPIES",
    "DEFAULT_NEEDLE",
    "FALLBACK",
    "HIT_MARK",
    "PAGE",
    "TEXT_WIDTH_PX",
    "FindPage",
    "TextRange",
    "TypesetFinder",
    "source_of",
    "typeset_readouts",
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


SHOW_AT: Final = 1.0 / 3.0
"""
How far down the pane the top of a match is put when the pane has to move for it.
"""


# ----------------------------------------------------------------------
# The document, and the finder over it
# ----------------------------------------------------------------------


def source_of(copies: int, text: str | None = None) -> str:
    """
    The page's markdown: `demo/sample.md` (or `text`) `copies` times over.
    """
    if text is None:
        text = demo_text("sample.md")
    if text is None:
        text = FALLBACK
    return "\n\n".join([text] * max(copies, 1))


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


def _not_drawing(reason: str) -> str:
    """
    The one line a page shows instead of its content: `advtext.ui.pages.typeset.not_drawing`.
    """
    from advtext.ui.pages.typeset import not_drawing

    return not_drawing(reason)


def _say_why_not(reason: str) -> None:
    """
    The whole of a frame without the library: one wrapped line, `say_why_not`'s.
    """
    from advtext.ui.pages.typeset import say_why_not

    say_why_not(reason)


class TypesetFinder:
    """
    A search over a `TypesetView`'s document: `advtext.typeset_find.Finder`, with the timings.

    What the controls read: `needle`, `ignore_case`, `current`, `match`,
    `label`, `keystrokes`, `search_ms`, `mark_ms`, `search`, `step`.
    `matches` are `(block, start, end)` into the view's `texts`.

    **`view` may be `None`** (the library is not drawing): the search, the
    current match and the label are all there, nothing is handed over,
    `marked` is zero and `rects()` is empty.

    `mark_ms` is what handing the marks to the view took: making the tuples
    and `set_marks` checking their shape. The view packs them for the library
    at its next draw, which is not in this number.

    `aligned` is whether the texts the index was built from are the view's
    own. When they are not, nothing is marked (a mark is an offset into the
    view's text) and the page says so.
    """

    def __init__(
        self,
        view: Any,
        index: _TextIndex,
        *,
        aligned: bool = True,
        ignore_case: bool = True,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.view = view
        self.aligned = aligned
        self.timer = timer
        self.finder = _TextFinder(
            index, color=int(HIT_MARK), current_color=int(CURRENT_MARK), limit=MARK_LIMIT
        )
        self.finder.ignore_case = ignore_case
        self.keystrokes = 0
        self.search_ms = 0.0
        self.mark_ms = 0.0
        self._handed: int | None = None

    # -- what the controls read -----------------------------------------

    @property
    def needle(self) -> str:
        return self.finder.needle

    @property
    def ignore_case(self) -> bool:
        return self.finder.ignore_case

    @property
    def current(self) -> int | None:
        return self.finder.current

    @property
    def matches(self) -> tuple[TextRange, ...]:
        return self.finder.matches

    @property
    def match(self) -> TextRange | None:
        return self.finder.match

    @property
    def marked(self) -> int:
        """How many marks the view has been handed: zero with no view, or texts that are not its."""
        return len(self.finder.marks()) if self.aligned and self.view is not None else 0

    @property
    def label(self) -> str:
        """`3 of 17`, `no matches`, or nothing for an empty needle."""
        if not self.needle:
            return ""
        return self.finder.status() or "no matches"

    def search(self, needle: str, *, ignore_case: bool | None = None) -> tuple[TextRange, ...]:
        """
        Search for `needle`, hand the marks over, keep the current match near where it was.
        """
        began = self.timer()
        found = self.finder.search(needle, ignore_case=ignore_case)
        searched = self.timer()
        self.hand_over()
        self.search_ms = (searched - began) * 1000.0
        self.mark_ms = (self.timer() - searched) * 1000.0
        self.keystrokes += 1
        return found

    def step(self, delta: int) -> TextRange | None:
        """
        Move the current match by `delta`, wrapping at both ends. Returns it, or `None`.
        """
        moved = self.finder.step(delta)
        self.hand_over()
        return moved

    def hand_over(self) -> None:
        """
        Give the view the marks if the finder changed since it was last given them.
        """
        if self.view is None or self._handed == self.finder.revision:
            return
        self._handed = self.finder.revision
        self.view.set_marks(self.finder.marks() if self.aligned else None)

    def rects(self) -> list[tuple[float, float, float, float]]:
        """
        The current match's rectangles, pixels from the document's corner; empty with none.

        One call into the library (`TypesetView.span_rects`), and empty before
        the first draw.
        """
        match = self.match
        if match is None or self.view is None:
            return []
        found: list[tuple[float, float, float, float]] = self.view.span_rects(
            match.block, match.start, match.end
        )
        return found

    def span_px(self) -> tuple[float, float] | None:
        """
        The current match's top and bottom in pixels below the document's top, or `None`.
        """
        rects = self.rects()
        if not rects:
            return None
        return min(rect[1] for rect in rects), max(rect[3] for rect in rects)


def typeset_readouts(finder: TypesetFinder, edits: int, stats: Any) -> tuple[str, ...]:
    """
    The lines under the search box: found against marked, then cost.

    `edits` is how many times the view's document changed since the page
    opened (typing should leave it at zero) and `stats` the view's
    `ViewStats`, or `None` before the first draw. Counts, no judgement.
    """
    found = len(finder.matches)
    marked = (
        f"marked {finder.marked} of {found} found"
        if finder.aligned
        else f"{found} found, not marked: the view's texts differ from the find index's"
    )
    laid = (
        "nothing drawn yet"
        if stats is None
        else f"blocks laid out so far {stats.blocks_laid_out} "
        f"({stats.blocks} in the document, {stats.blocks_deferred} not reached yet)"
    )
    return (
        f"{marked}  ·  table cells are searched and marked  ·  formula source is not searched",
        f"last keystroke: search {finder.search_ms:.2f} ms, marks {finder.mark_ms:.2f} ms"
        f"  ·  {finder.keystrokes} keystrokes: {edits} edits of the document  ·  {laid}",
    )


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


class FindPage:
    """
    The page: a finder over a view, the search row, and the scrolling pane.

    `typeset` is the `TypesetView`, or `None` when the library is not drawing
    (`reason` says why, and the page is that one line). `finder` is a
    `TypesetFinder` either way: the search needs no library.
    """

    def __init__(self, context: PageContext, text: str | None = None) -> None:
        self.context = context
        count = context.count_for(PAGE.name)
        self.copies = DEFAULT_COPIES if count is None else max(count, 1)
        self.text = text
        self.source = source_of(self.copies, text)
        """The markdown on show."""
        self.typeset: TypesetView | None = None
        self.reason = _why_not()
        """Why nothing is drawn, when nothing is; empty while the view draws."""
        if not self.reason:
            try:
                self.typeset = TypesetView(self.source, theme=context.theme, palette=DARK_PALETTE)
            except TypesetUnavailable as exc:
                self.reason = str(exc)
        view = self.typeset
        self._revision = 0 if view is None else view.revision
        # Described here as well as by the view: the find index wants the
        # block descriptions and the view does not hand its own out. The
        # texts are compared, so an index that is not the view's marks
        # nothing. With no view the markdown is read here, by the reader the
        # view uses, so that the search is the same search.
        blocks = (
            view.blocks if view is not None else parse_markdown(self.source, context.theme).blocks
        )
        described = MarkdownConverter(context.theme).describe(blocks)
        self.blocks = len(described.blocks)
        """How many blocks the document has, as the index counts them."""
        self.finder = TypesetFinder(
            view,
            _TextIndex.of(described.blocks),
            aligned=view is None or tuple(described.texts) == tuple(view.texts),
            ignore_case="case" not in context.options_for(PAGE.name),
        )
        self.finder.search(DEFAULT_NEEDLE)
        self.finder.keystrokes = 0
        self.frames = 0
        self.scrolls = 0
        """How many frames moved the pane for a step or a search."""
        self.view_stats: Any = None
        """The view's `ViewStats` as of the last frame, or `None`."""
        self.vertices = 0
        """Vertices the view added to the pane's draw list in the last frame."""
        self.pane: tuple[float, float] | None = None
        """The scrolling pane's top and bottom on screen at the last frame, in pixels."""
        self._reveal = False
        self._refocus = False
        self._rearming = 0

    @property
    def renderer(self) -> str:
        """`"TypesetView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetView" if self.typeset is not None else "none"

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
        view = self.typeset
        if view is None or view.origin is None or self.pane is None:
            return False
        if not typesetter.ready():
            return False
        origin, span, pane = view.origin, self.finder.span_px(), self.pane
        if span is None:
            return False
        return bool(pane[0] <= origin[1] + span[0] and origin[1] + span[1] <= pane[1])

    @property
    def edits(self) -> int:
        """
        How many times the view's document changed since the page opened; 0 with no view.
        """
        return 0 if self.typeset is None else self.typeset.revision - self._revision

    def lines(self) -> tuple[str, ...]:
        """
        The captions under the search row; the one "why not" line when nothing draws.
        """
        if self.typeset is None:
            return (_not_drawing(self.reason),)
        return typeset_readouts(self.finder, self.edits, self.view_stats)

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts.
        """
        finder = self.finder
        stats = self.view_stats
        return [
            f"frames={self.frames} renderer={self.renderer} copies={self.copies} "
            f"blocks={self.blocks} needle={finder.needle!r} "
            f"marked={finder.marked} found={len(finder.matches)} "
            f"aligned={int(finder.aligned)} "
            f"current={-1 if finder.current is None else finder.current + 1} "
            f"shown={int(self.shown())} scrolls={self.scrolls} "
            f"keystrokes={finder.keystrokes} edits={self.edits} "
            f"laid_out={0 if stats is None else stats.blocks_laid_out} "
            f"deferred={0 if stats is None else stats.blocks_deferred} "
            f"whole={1 if stats is None else int(stats.whole)} vertices={self.vertices}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        self.frames += 1
        view = self.typeset
        if view is None:
            self.vertices, self.pane = 0, None
            _say_why_not(self.reason)
            return
        try:
            self._frame(imgui, view)
        except TypesetUnavailable as exc:
            # Whatever raised drew no text: the search row and an empty pane
            # are this frame, and the page is the one line from the next.
            # The finder keeps the needle and the matches; it has no view.
            self.typeset = None
            self.finder.view = None
            self.view_stats = None
            self.reason = str(exc)

    def _frame(self, imgui: Any, view: TypesetView) -> None:
        """
        The frame through imtypeset. `TypesetUnavailable` is the caller's to catch.

        Every pair opened here is closed on the way out of an exception, so
        the caller's handler leaves ImGui's stacks as it found them.
        """
        self._controls(imgui)
        for line in self.lines():
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
        try:
            self.pane = (
                imgui.get_window_pos().y,
                imgui.get_window_pos().y + imgui.get_window_height(),
            )
            width_px = max(min(imgui.get_content_region_avail().x, TEXT_WIDTH_PX), MIN_WIDTH_PX)
            vertices = imgui.get_window_draw_list().vtx_buffer
            before = vertices.size()
            self.vertices = 0
            reveal, self._reveal = self._reveal, False
            finder = self.finder
            finder.hand_over()
            match = finder.match if reveal else None
            if match is not None:
                # The line holding the match's first character, not the block.
                view.scroll_to(match.block, match.start, align=SHOW_AT)
            view.debug = self.context.debug
            view.draw(palette=DARK_PALETTE, width_px=width_px)
            # One more call into the library a frame, for the readout.
            self.view_stats = view.stats
            if view.scrolled:
                self.scrolls += 1
            self.vertices = vertices.size() - before
        finally:
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

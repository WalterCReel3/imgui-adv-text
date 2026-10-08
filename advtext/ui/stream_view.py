r"""
The streaming view: a document that is still arriving, drawn as it arrives.

`advtext.stream.StreamDocument` turns text received in pieces into blocks that
are settled and a tail that is not. `StreamView` is the `BareView` over one:
the same pane, the same selection, links, copy and colour, with four things
added that a document which grows needs and a finished one does not.

## 1. Only what changed is laid out, and at most once a frame

The view reads `stream.revision` once at the top of `draw`. `StreamDocument`
defers its parse to the first read, so however many pieces were appended since
the last frame there is **one parse and one layout**, and none at all on a
frame where nothing arrived.

The layout is `advtext.ui.units.layout_units` with the view's `UnitCache`. A
committed block is the same object from the moment it commits, so its unit is
found by identity -- not composed, not shipped, not indexed, not hashed --
and what is built per change is the live tail's units and nothing else.
`tests/test_stream_view.py` counts the calls to `ship` and to
`SelectionModel.from_commands` across a whole replay rather than timing them.

**A code block is laid out in pieces of `CODE_PIECE_LINES` lines**
(`advtext.ui.units` has the mechanism and its figures). A fence still open is
one live block however long it gets, and as one unit it was composed and
shipped whole for every line appended: 102 ms a line at 600 lines, measured
here. In pieces, the lines already written are settled units and a new line
re-does the last piece. What a host sees of this: `layout.placed` has several
units for such a block, all with its `block_start`; everything addressed by
block number -- `set_colours`, `block_text`, `block_at`, `selected_blocks`,
the source map -- means the whole block, as before. The block keeps its
pieces when it commits, so committing moves nothing and rebuilds nothing.

**A table is laid out in pieces of `TABLE_PIECE_ROWS` rows**, for the same
reason and with the same consequences for a host that walks `placed`. A row
added to a long table sets the last piece again and nothing else, *as long
as no column's width changed*; when one does -- a cell arrives that is the
widest its column has had -- every piece is set again, because every row's
cells have moved. On a thirty-row table of varied cells fed four characters
at a time that was 26 layouts of 647, 8 of them after the table was longer
than one piece (`.concerns/AF-livetable-scripts/measure.py.txt`). The widths
themselves are kept up a row at a time (`advtext.ui.TableMeasure`): a row is
measured when it arrives, not again for every row after it.

## 2. Follow the tail, until the reader scrolls away

Drawn in a scrolling child, the view keeps the end of the document in sight
while the reader is at the bottom, and stops the moment they are not:

- at the top of `draw`, "at the bottom" is `scroll_y >= scroll_max_y - 1`. If
  so the view follows; if the reader has wheeled or dragged up, it does not;
- when following, the view asks ImGui for the end of the pane after it has
  claimed its new height. The end of the *pane*: whatever the host draws
  after the view in the same child is part of what is followed;
- scrolling back to the bottom resumes following, with no button to press.
  `follow_tail()` does the same from code;
- "at the bottom" is asked of the pane, not of the reader's hand. If the
  content gets *shorter* by more than the reader had scrolled up, ImGui
  clamps the pane to its new end and the view follows again. Looked for
  and found in one place only: a reader 13 px above the end when `close()`
  committed the last paragraph under `RESET`, which set it again a line
  (21.6 px) shorter. A commit in mid-stream is caused by the next block's
  first line, which adds more than a re-set takes away; no case of that
  shortening the document was found, and none is ruled out.

ImGui applies a scroll request at the next frame's `Begin`, so new lines are
drawn one frame before the pane moves to show them. That is ImGui's own order
of events, not something this module can reorder; at sixty frames a second it
is one frame of the tail below the fold.

## 3. A table that is still being written does not rescale under the reader

`advtext.ui` apportions a table's columns to fill the measure, in proportion
to their natural widths. While a table streams, one long cell arriving
therefore narrows every *other* column, and each row already on screen moves.
The plan calls it table jitter and it is measured in the tests.

What this view does instead, while a table is live: **each column is as wide
as the widest cell it has had so far, and the table is as wide as that comes
to.** A column's natural width only grows as text arrives, so no column ever
narrows; a column moves only when one to its left grows; and nothing is
scaled. Once the columns no longer fit the measure the table is handed back
to the default apportioning, which wraps its cells -- something has to give
then, and wrapping is what gives.

**This is not the rule the plan's notes proposed**, which was a running
maximum of each column's *apportioned* width. Apportioned widths always sum
to the measure, so the maximum over time of each sums to more than it: the
table would overflow the pane as soon as two columns had each been the wide
one. `tests/test_stream_view.py` shows that with numbers before testing this.

At commit: under `CommitPolicy.RESET` the table is apportioned once, normally,
and so fills the measure (one visible change, as RESET is for a paragraph).
Under `KEEP_STREAMED` it is measured once more, whole, and keeps the wider of
that and the widths it had, for as long as they fit -- including a table
that committed before any layout saw it live, so the result does not depend
on how the stream was cut into frames (`_layout_blocks`).

## 4. A selection survives the text arriving under it, or is cut back -- never reinterpreted

`advtext.ui.units.carry_selection` restates a selection as glyph positions in
the blocks it touches and finds the same glyphs in the new layout. A selection
entirely in settled text is untouched by anything that streams in after it. A
selection that reaches into the live tail is carried too **as long as the text
up to its end is still the same text**: more words arriving after it, or the
tail re-breaking, or the block committing under either policy, do not
disturb it.

When that fails -- markup closed late and the characters before the
selection's end are no longer what they were -- the selection is **cut back
to the end of the last block that is still the same text**, and cleared if
it began in the block that changed. Usually that is the end of the settled
text, which is the rule the plan's notes gave for every append; here it is
the fallback, and it does not depend on whether the block that changed also
committed in the same step.

**A drag in progress is anchored to text too** (`BareView._handle_mouse`): the
end of the selection that is supposed to stay put is carried by the same
rule when the block under it is set again, and the drag ends if it cannot be.

## 5. A block the host draws grows without being set

`host_for` is `BareView`'s (that module's docstring has the contract) and a
stream is what it was built for: a fenced `diff` still being written, drawn by
an `advtext.ui.diff_view.DiffView` through `advtext.ui.diff_view.DiffFences`.
Two things are this view's:

- **The hook is asked about what could have changed and nothing else.** A
  committed block is the same object for good, so each sync asks about the
  blocks that committed since the last one and the unfinished tail.
- **A hosted fence is never cut into pieces**, because it is never laid out
  as a code block: its unit is one empty box of the widget's height, and a
  new line rebuilds that box if the height changed and nothing if it did not
  (a diff at its height cap). `tests/test_hostdiff.py` counts, per appended
  line at fifty lines and at five hundred: one diff line read, one row
  measured, one unit composed and shipped, one block asked about.

What is still linear in a long live fence is what was linear before any of
this: `advtext.stream` re-reads the open fence into a `CodeBlock` on every
piece, `StreamDocument.source` joins its pieces on every read, and
`advtext.diff` re-derives the open hunk's pairing for every line
(`.concerns/C-diffview--builder--result.md`).

## What has not been done

- `tests/test_stream_view.py` runs real ImGui frames with no display,
  including the scrolling. **In a real window it was run once**, on
  2026-10-07, under Xvfb with software GL and no window manager, by a
  throwaway script: `demo/stream.md` fed four pieces a frame gave 110 layouts
  in 112 frames with the pane at the end of its range throughout; a wheel up
  released it (scroll 790 of 1090), wheeling back down took it again; the
  view's origin was a whole pixel on every frame. Nobody has looked at it.
- **One long paragraph in a live list item is still one unit**, composed
  and shipped whole on every piece appended: measured at 560 ms a sentence
  for one paragraph of 600 sentences. Its breaks are chosen along its whole
  length, so it cannot be cut as a code block or a table is. A paragraph
  that long is not something a model writes.
- **A live table inside a list item or a quote** is laid out in pieces like
  any other, but `advtext.stream` reads it whole with its container on every
  piece (only a top-level table is followed row by row), and its rows are
  then new objects each time: every piece is compared by value to be found.
  Not measured.
- **A live table's last piece is set again for every piece of a row**, up
  to `TABLE_PIECE_ROWS` rows, and a row that wraps costs a line break a
  cell: about 1.1 ms a row held at natural widths and 2.5 ms wrapped to a
  260 px measure, at any length (was 42 and 97 ms at 200 rows).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from advtext.backends.imgui_draw import DrawStats, FaceFont, Palette
from advtext.markdown import Block, TableBlock
from advtext.pack import CharMeasure
from advtext.selection import Selection
from advtext.stream import CommitPolicy, StreamDocument
from advtext.ui import TableMeasure, table_natural_widths, with_columns
from advtext.ui.bare_view import BareView, HostFor
from advtext.ui.units import CODE_PIECE_LINES, TABLE_PIECE_ROWS, UnitLayout, carry_selection
from advtext.units import DEFAULT_PX_PER_INCH, UNITY, Scaled

__all__ = ["StreamView"]

FAR_PX = 1.0e7
"""
A scroll position past the end of any pane: asking for it is asking for the end.
"""

AT_BOTTOM_PX = 1.0
"""
How close to the end of its scroll range a pane must be to count as "at the bottom".

One pixel, because ImGui keeps scroll positions as whole pixels and a
comparison for equality would be at the mercy of that staying true.
"""


@dataclass(slots=True, init=False)
class StreamView(BareView):
    """
    A `BareView` over a `StreamDocument`: draw it every frame, append whenever text arrives.

        stream = StreamDocument(theme, fontlib_metrics)
        view = StreamView(stream, measure)
        ...
        stream.append(piece)          # any number of times, from the same thread
        view.draw(fonts=fonts)        # once a frame, inside a scrolling child

    Everything `BareView` offers is here unchanged -- selection, copy, links,
    colour spans, the host hooks. `document` is the stream's and is replaced
    by the view; set colour spans by block number, which a committed block
    keeps for good.

    The module docstring has the four things this adds.
    """

    _CODE_LINES: ClassVar[int] = CODE_PIECE_LINES
    _TABLE_ROWS: ClassVar[int] = TABLE_PIECE_ROWS

    stream: StreamDocument = field(init=False)
    follow: bool = field(init=False)
    """Whether the view keeps the end in sight at all. Off: it never scrolls."""

    _revision: int = field(init=False)
    _following: bool = field(init=False)
    _jump: bool = field(init=False)
    # The widest each column of a live table has been, by the table's block
    # number, and the same for tables that committed under KEEP_STREAMED.
    _held: dict[int, tuple[Scaled, ...]] = field(init=False)
    _kept: dict[int, tuple[Scaled, ...]] = field(init=False)
    # The sized stand-in for a table, by block number, with the block it was
    # made from: reused while both are unchanged so that a committed table is
    # the same object from frame to frame.
    _sized: dict[int, tuple[TableBlock, tuple[Scaled, ...], TableBlock]] = field(init=False)
    # What has been measured of each live table, by block number, so that a
    # row is measured when it arrives and not again for every row after it.
    _measures: dict[int, TableMeasure] = field(init=False)
    _relayouts: int = field(init=False)
    # How many of the stream's blocks had committed as of the last `sync`
    # (the document the next layout is of), and as of the last layout built.
    # Between them are the blocks that committed since anything was laid out.
    _settled: int = field(init=False)
    _laid_settled: int = field(init=False)
    _host_settled: int = field(init=False)

    def __init__(
        self,
        stream: StreamDocument,
        measure: CharMeasure,
        *,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        debug: bool = False,
        on_link: Callable[[str], None] | None = None,
        hand_cursor: bool = True,
        copy_as: Callable[[BareView], str] | None = None,
        style_links: bool | None = None,
        follow: bool = True,
        host_for: HostFor | None = None,
    ) -> None:
        BareView.__init__(
            self,
            document=stream.document,
            theme=stream.theme,
            measure=measure,
            px_per_inch=px_per_inch,
            debug=debug,
            on_link=on_link,
            hand_cursor=hand_cursor,
            copy_as=copy_as,
            style_links=style_links,
            host_for=host_for,
        )
        self.stream = stream
        self.follow = follow
        self._revision = stream.revision
        self._following = True
        self._jump = False
        self._held = {}
        self._kept = {}
        self._sized = {}
        self._measures = {}
        self._relayouts = 0
        self._settled = len(stream.committed)
        self._laid_settled = 0
        self._host_settled = 0

    # ------------------------------------------------------------------
    # Keeping up with the stream
    # ------------------------------------------------------------------

    def sync(self) -> bool:
        """
        Take in whatever the stream has received since the last call. True if anything changed.

        `draw` calls this; it is public for a caller that wants the layout
        without drawing -- a test, a benchmark, a host measuring a height. It
        reads `stream.revision`, which runs the stream's deferred parse, so
        this is the one place per frame the stream is parsed.
        """
        revision = self.stream.revision
        if revision == self._revision:
            return False
        self._revision = revision
        self.document = self.stream.document
        self._settled = len(self.stream.committed)
        self.invalidate()
        return True

    @property
    def relayouts(self) -> int:
        """
        How many layouts this view has built: at most one a frame, and none when nothing arrived.
        """
        return self._relayouts

    def layout_for(self, width: Scaled) -> UnitLayout:
        """
        `BareView.layout_for`, counting the layouts it actually builds.
        """
        before = self._layout
        layout = BareView.layout_for(self, width)
        if layout is not before:
            self._relayouts += 1
            self._laid_settled = self._settled
        return layout

    # ------------------------------------------------------------------
    # Tables that are still being written
    # ------------------------------------------------------------------

    def _layout_blocks(self, width: Scaled) -> tuple[Block, ...]:
        """
        The stream's blocks, with a live table's columns held at their widest so far.

        The module docstring has the rule and why it is not a running maximum
        of apportioned widths. A document with no table in its tail and none
        kept from before comes back as the stream's own tuple, untouched.

        **A table that commits under `KEEP_STREAMED` is measured once more,
        at the commit**, and kept at the wider of that and what it was held
        at. The held widths are only as recent as the last layout, and a
        table's last rows can arrive in the same sync as the block after it:
        there is then no layout at which the table is live and whole.
        Measured before this was done: a first row of `| a | b |` laid out,
        then a wide row and the next paragraph together, left the committed
        table at 25 and 25 px in ten lines, for good, where a word at a time
        gave 188 and 168 px in three.

        The same measurement is taken for a table that was *never* seen live
        -- it arrived and committed between two layouts, or the view was
        made over a stream that already had it. So under `KEEP_STREAMED` a
        committed table is at its natural widths whenever they fit, however
        the stream was cut into frames (`tests/test_stream_view.py` holds a
        word at a time, a character at a time, two bursts and one burst to
        the same glyph positions). It used to depend on the cut: never held
        meant the default apportioning, which fills the measure.

        One dependence on timing is left, and is the price of nothing
        narrowing: a cell is briefly *wider* while markup in it is unclosed
        (`**wide` is two asterisks wider than the bold it becomes), and a
        layout that saw it then holds that width.
        """
        blocks = self.document.blocks
        settled = self._settled
        keep = self.stream.policy is CommitPolicy.KEEP_STREAMED

        # A table that committed since the last layout stops being held: kept
        # under KEEP_STREAMED, at its widths now it is whole and never
        # narrower than it was held; let go under RESET.
        if keep:
            for number in range(self._laid_settled, min(settled, len(blocks))):
                table = blocks[number]
                if number in self._kept or not isinstance(table, TableBlock):
                    continue
                widths = table_natural_widths(table, self.theme, self.measure)
                held = self._held.get(number, ())
                if len(held) == len(widths):
                    widths = tuple(max(a, b) for a, b in zip(held, widths, strict=True))
                self._kept[number] = widths
        live_tables = [
            number
            for number in range(settled, len(blocks))
            if isinstance(blocks[number], TableBlock)
        ]
        for number in [number for number in self._held if number not in live_tables]:
            del self._held[number]
        for number in [number for number in self._measures if number not in live_tables]:
            del self._measures[number]
        if not live_tables and not self._kept:
            self._sized.clear()
            return self._hosted_stream(blocks, blocks, width)

        out = list(blocks)
        for number in live_tables:
            table = blocks[number]
            assert isinstance(table, TableBlock)
            measured = self._measures.setdefault(number, TableMeasure())
            natural = measured.natural(table, self.theme, self.measure)
            before = self._held.get(number, ())
            if len(before) == len(natural):
                natural = tuple(max(a, b) for a, b in zip(before, natural, strict=True))
            self._held[number] = natural
            out[number] = self._sized_to(number, table, natural, width, measured)
        for number, widths in self._kept.items():
            table = blocks[number]
            if isinstance(table, TableBlock):
                out[number] = self._sized_to(number, table, widths, width)
        for number in [number for number in self._sized if number >= len(blocks)]:
            del self._sized[number]
        return self._hosted_stream(blocks, tuple(out), width)

    # ------------------------------------------------------------------
    # Blocks the host draws
    # ------------------------------------------------------------------

    def _unchanged_blocks(self, blocks: tuple[Block, ...]) -> int:
        """
        The blocks that had committed when `host_for` was last asked: those are the same objects.

        So each sync asks about the blocks that committed since and the
        unfinished tail, and about nothing that had settled -- however long
        the document is.
        """
        return min(self._host_settled, len(blocks))

    def _hosted_stream(
        self, blocks: tuple[Block, ...], out: tuple[Block, ...], width: Scaled
    ) -> tuple[Block, ...]:
        """
        `BareView._hosted`, remembering how much of the stream had settled when it ran.
        """
        laid = self._hosted(blocks, out, width)
        self._host_settled = self._settled
        return laid

    def _sized_to(
        self,
        number: int,
        table: TableBlock,
        widths: tuple[Scaled, ...],
        width: Scaled,
        measured: TableMeasure | None = None,
    ) -> TableBlock:
        """
        `table` at these column widths if they fit the measure, else `table` as it is.

        "Fit" is the widths summing to no more than the measure less the
        table's indent. A table that does not fit goes to the default
        apportioning, which narrows and wraps; holding it wider than the pane
        would be trading jitter for text nobody can see.

        **A column of no width is given one scaled point.** A column whose
        every cell is empty has a natural width of twice the cell padding,
        which is nothing in a theme that pads by nothing, and `with_columns`
        refuses a width under one scaled point -- rightly, for a host, and it
        raised out of `draw` on every frame here for a table the
        whole-document path lays out. One scaled point is 1/65536 pt: the
        column is still empty and still takes no room, and when a cell of it
        gets text it grows like any other. Should `with_columns` refuse for
        a reason not foreseen here, the table goes to the default
        apportioning: this runs inside a per-frame draw and must not raise
        for content the plain path accepts.
        """
        columns = max((len(row) for row in (table.header, *table.rows)), default=0)
        available = max(width - table.left_indent, UNITY)
        widths = tuple(max(column, 1) for column in widths)
        if not widths or len(widths) != columns:
            self._sized.pop(number, None)
            return table
        if sum(widths) > available:
            if measured is None:
                self._sized.pop(number, None)
                return table
            # A live table too wide to hold. It is still handed back to the
            # default apportioning, but as the widths that apportioning
            # gives, stated: worked out from `measured`, which has every row
            # but the newest already, where composing the plain table would
            # measure and break every cell of it again for this one row.
            # `TableMeasure.columns` is `table_columns` to the scaled point,
            # so the table is set exactly as the plain one would be.
            widths = measured.columns(table, self.theme, width, self.measure)
            if len(widths) != columns or any(column < 1 for column in widths):
                self._sized.pop(number, None)
                return table
        found = self._sized.get(number)
        if found is not None and found[0] is table and found[1] == widths:
            return found[2]
        try:
            sized = with_columns(table, widths=widths)
        except ValueError:
            self._sized.pop(number, None)
            return table
        self._sized[number] = (table, widths, sized)
        return sized

    # ------------------------------------------------------------------
    # The selection, across text arriving
    # ------------------------------------------------------------------

    def _carry(self, selection: Selection, old: UnitLayout, new: UnitLayout) -> Selection:
        """
        The selection after a relayout: the same text; else as much of it as is; else nothing.

        `carry_selection` first, on the whole of it. If that fails, some
        block the selection reaches into no longer sets the characters it
        did -- markup closed late in the live tail -- and the selection's
        end is pulled back to **the last block boundary before which
        everything is still the same text**. Usually that is the start of
        the block being written, so what is left is the settled part of the
        selection; in a tail of several blocks (a list being written) it is
        the end of the last item that did not change. If the selection
        began in the block that changed, nothing of it is left.

        The boundary is looked for among the tops of the units the selection
        covers, by bisection: carrying up to a boundary succeeds exactly
        when every unit before it is unchanged, so success is monotone in
        the boundary and a long live list costs a handful of attempts, not
        one per item. Whatever comes back was carried, so it is the same
        text whether or not that argument holds for some input.

        **It does not ask which blocks have committed**, and used to: the
        boundary was where the live tail begins *now*, measured in the old
        layout. A block that changed its text and committed between two
        layouts put that boundary after itself, and the whole selection was
        cleared where the same change without the commit cut it back.
        """
        carried = carry_selection(selection, old, new)
        if carried is not None:
            return carried
        boundaries = [
            unit.base for unit in old.placed if selection.start < unit.base < selection.end
        ]
        best: Selection | None = None
        low, high = 0, len(boundaries)
        while low < high:
            middle = (low + high) // 2
            clamped = carry_selection(Selection(selection.start, boundaries[middle]), old, new)
            if clamped is None:
                high = middle
            else:
                best = clamped
                low = middle + 1
        return Selection(0, 0) if best is None else best

    # ------------------------------------------------------------------
    # Drawing, and following the tail
    # ------------------------------------------------------------------

    @property
    def following(self) -> bool:
        """
        Whether the view is keeping the end in sight, as of the last `draw`.
        """
        return self.follow and self._following

    def follow_tail(self) -> None:
        """
        Go to the end and follow it again, whatever the reader had scrolled to.
        """
        self._jump = True

    def draw(
        self,
        *,
        fonts: FaceFont,
        palette: Palette | None = None,
        width_px: float | None = None,
    ) -> DrawStats:
        """
        Take in what has arrived, draw, and keep the end in sight if the reader is there.

        Call once a frame inside a scrolling child window; the scrolling it
        does is that window's. See `BareView.draw` for the rest.
        """
        from imgui_bundle import imgui

        self.sync()
        # Read before anything is drawn: where the reader has left the pane
        # as of this frame, against the range it had before this frame's
        # growth. A request from last frame has been applied by now.
        at_bottom = imgui.get_scroll_y() >= imgui.get_scroll_max_y() - AT_BOTTOM_PX
        self._following = at_bottom or self._jump
        stats = BareView.draw(self, fonts=fonts, palette=palette, width_px=width_px)
        if self._scrolled:
            # Sent somewhere by `scroll_to` on this frame: that is where the
            # reader asked to be, and the request must not be overwritten by
            # one for the end. The next frame reads the pane as scrolled up.
            self._following = False
        if self.follow and self._following:
            # The end of the *pane*, not of this view: a host may draw more
            # after it in the same child -- a spacer, an input box -- and a
            # request aimed at the view's own last pixel would leave the pane
            # short of its end by that much, which the next frame reads as the
            # reader having scrolled up. ImGui clamps a scroll request to the
            # range the content turns out to have.
            imgui.set_scroll_y(FAR_PX)
        self._jump = False
        return stats

r"""
The streaming view again, over ONE retained `imtypeset.Document`.

**Experimental** (branch `experimental/imtypeset-adoption`, step A3 of
`../imtypeset/docs/advtext-rework-plan.md` section 6.3). Of the facade:
`TypesetStreamView`; the rest is reached from here. It is not a name of
`advtext.ui`.

`TypesetStreamView` is to `advtext.ui.stream_view.StreamView` what
`TypesetView` is to `BareView`: a `TypesetView` over a stream, drawn every
frame while text is still being appended. The stream is what parses; what is
different is what a piece of new text costs after the parse.

    stream = MarkdownStream(theme, math=True)  # advtext.typeset_markdown: the direct path
    view = TypesetStreamView(stream)           # TypesetUnavailable without the library

**The stream is an `advtext.typeset_markdown.MarkdownStream`** (text and runs,
no node material, no old-core object). The view reads its `theme`, `revision`
and `blocks`, and `source` / `sources` for the source map. Until tranche 5 an
`advtext.stream.StreamDocument` was taken too; that module is deleted.
`tests/test_typeset_stream_view.py` replays whole documents and holds each
against the same document given whole, and against what the old core
described it as (frozen).
    ...
    stream.append(piece)                      # any number of times
    view.draw(palette=palette)                # once a frame, inside a scrolling child

When it cannot be used it says so exactly as `TypesetView` does
(`TypesetUnavailable` from the constructor and from `draw`), and the host
draws a `StreamView` over the same stream instead.

## One edit in the library per change of the stream

`sync` (which `draw` calls) reads `stream.revision` once. Unchanged: nothing is
described and the library is not called. Changed: the blocks from the first
one that is not the same object as before are described again, as in
`TypesetView`, and then **the descriptions are compared**, because the stream
makes every block of its unfinished tail anew at each change and that tail is
often more than the block being written (a list's items; a rule or a short
paragraph the parser cannot yet call finished). Blocks whose description is
equal to the one the library already holds are left alone, and what is left
is AT MOST ONE edit:

- nothing, when no description changed (white space arrived);
- `append_text`, when the only thing that changed is that **the last block's
  text grew**: its new text begins with its old text, everything else about
  it is equal (kind, style, marker, indent, flags), and the runs it had are
  the first of the runs it has. The library is given the new characters and
  the new runs and lays out that block alone;
- `append_table_rows`, when the last block is a table and the only thing that
  changed is that **it has more rows**: the rows it had are the first of the
  rows it has. The library sets the new rows, and the old ones again only if
  a column's width moved;
- `append_text` again, when the last block is a table and only **its last
  cell's text grew** (the library appends to a table's last cell);
- `replace_blocks` of the blocks from the first whose description changed to
  the last whose description changed, otherwise. That is what a new block, a
  block re-set at its commit (a stream with a live theme), markup closing late, and
  a table whose unfinished row gained a cell get.

`edits` counts them by kind (`"append"` is all three appends).

## A table that is still being written holds its columns

`StreamView`'s rule (its section 3), which the library has as a block flag
since imtypeset commit `be40444`: a table of the stream's unfinished tail is
described with `BLOCK_TABLE_HELD`, and the library then keeps each column as
wide as the widest cell it has had since the block was described, the table
as wide as its columns and not the pane; a column moves only when a wider
cell arrives in it, and when the held widths stop fitting, the table is
fitted as any other until they fit again. The widths survive the appends
above and a `replace_blocks` of the one table by one table with the flag and
as many columns, which is what every change to its unfinished row is.

At the commit, by the stream's policy:

- **keep** (a `MarkdownStream` whose `live_theme` is its `theme`): the flag
  stays, for good. A committed
  table goes on being as wide as its columns want. So that this does not
  depend on how the stream was cut into frames, EVERY table of such a stream
  has the flag, one that arrived and committed between two draws included
  (`StreamView` measures such a table once more for the same reason).
- **reset** (a `MarkdownStream` with another `live_theme`): the table is
  replaced once more without the flag, and is
  fitted to the pane like a table given whole: one visible change, as a
  reset is for a paragraph.

Not `StreamView`'s: while the held widths do not fit, the library fits the
table by its own rule at each change, where `StreamView` stated the widths
the default apportioning gave. And, from the other team's list of defects at
that commit: a held table keeps its old widths after a change of font size.

Measured before the comparison was there (2026-10-10, `demo/math.md`, 24
characters a frame): 6 appends and 231 replaces, because the tail was two
blocks or more for most of the document.

A stream's `blocks` may be a new tuple at every read, so "did anything
change" is asked of `revision` and never of the tuple's identity.

Before the first `draw` there is no document in the library: a `sync` then
only describes, and the first draw sets everything in one `set_blocks`.

## Follow the tail

As `StreamView` does, by the same two constants: at the top of `draw` the pane
is "at the bottom" when `scroll_y >= scroll_max_y - AT_BOTTOM_PX`; if it is,
the view asks for the end of the pane after it has claimed its new height. A
reader who scrolls up is left alone, scrolling back to the bottom resumes,
`follow_tail()` does so from code, `follow=False` never scrolls, and a
`scroll_to` carried out on a frame wins over the tail.

## A selection while text arrives: what is and is not `StreamView`'s

`TypesetView` drops a selection that ends in a replaced block, and a stream
replaces its tail at every change. This class puts it back when it still
names **the same text**: every replaced block the selection covers whole has
the text it had, and the block it ends in has the same characters up to where
the selection ends. So a selection in the block being written survives more
words arriving after it, by `append_text` or by `replace_blocks` alike, and a
drag in progress goes on by the same rule applied to its anchor.

When that is not so (markup closed late and the characters before the
selection's end are other characters) the selection is **dropped whole**.
`StreamView` cuts it back to the last block that is still the same text; that
is its `_carry`, which is not here. `select_all()` goes on selecting
everything, as in `TypesetView`.

## What else differs from `StreamView`

- No `measure`, `px_per_inch`, `relayouts`: there is no layout on this side
  to count (`edits`, `revision` and `stats` are the counts). `host_for`,
  `debug`, `layout_for`, `set_lines` and the source map are `TypesetView`'s;
  `source` and `source_of` read the stream.
- `sync` answers whether the blocks changed, not whether the revision did.
- `set_document` and `set_theme` are refused: the stream is the document,
  and its theme is the one its blocks are built with. So are its reader
  options (`MarkdownStream(..., reader=...)`): the view is given none.
- `code_overflow` and `fixed_line_height` are `TypesetView`'s, as
  constructor arguments and setters. `table_widths` is not: a stream's
  tables are sized by its policy (the section above), and
  `set_table_widths` is refused. A stream whose blocks hold something that
  is no block raises `TypeError` at the `sync` that meets it.
- What `TypesetView`'s docstring lists against `BareView` (copy, colour,
  `fonts=` ignored, the height an estimate until seen) applies here too.

## What has and has not been run

`tests/test_typeset_stream_view.py`: real ImGui frames with no window for the
edits, the tail and the selection, and one run in a real window (the `window`
fixture) for vertices and for the times it reports against `StreamView`.
Nobody has looked at what it draws.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from advtext import typesetter
from advtext.description import (
    BLOCK_TABLE_HELD,
    KIND_HOST,
    KIND_RULE,
    KIND_TABLE,
    BlockDescription,
    CellDescription,
    Description,
    RunDescription,
    StyleDescription,
)
from advtext.markdown_rules import BlockSource
from advtext.ui.ownership import AT_BOTTOM_PX, FAR_PX
from advtext.ui.palette import Palette
from advtext.ui.typeset_view import HostFor, Range, TypesetUnavailable, TypesetView

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from advtext.theme import Theme

__all__ = [
    "TypesetStreamView",
    "TypesetUnavailable",
    "appended",
    "appended_cell_text",
    "appended_rows",
]


def appended(
    before: BlockDescription, after: BlockDescription
) -> tuple[str, tuple[RunDescription, ...]] | None:
    """
    What `append_text` needs to turn `before` into `after`, or `None` if it cannot.

    The new characters and the runs that are new, when `after` is `before`
    with more text at its end and nothing else changed. Never for a Host
    block or a rule: the library raises for a last block that is "not one
    that holds text" (run on 2026-10-10), and what the library raises
    switches it off. A paragraph or a code block with no text YET is appended
    to like any other (run the same day). Never for a table either: its text
    is its cells', and `appended_rows` and `appended_cell_text` say what can
    be appended to one.
    """
    if before.kind in (KIND_HOST, KIND_RULE, KIND_TABLE):
        return None
    old, new = before.text, after.text
    if len(new) <= len(old) or not new.startswith(old):
        return None
    if before._replace(text="", runs=()) != after._replace(text="", runs=()):
        return None
    held = len(before.runs)
    if after.runs[:held] != before.runs:
        return None
    return new[len(old) :], after.runs[held:]


def _tables_alike(before: BlockDescription, after: BlockDescription) -> bool:
    """Whether two descriptions are tables that differ in nothing but their cells."""
    return (
        before.kind == KIND_TABLE
        and after.kind == KIND_TABLE
        and before._replace(text="", rows=()) == after._replace(text="", rows=())
    )


def appended_rows(
    before: BlockDescription, after: BlockDescription
) -> tuple[tuple[CellDescription, ...], ...] | None:
    """
    What `append_table_rows` needs to turn table `before` into `after`, or `None` if it cannot.

    The rows that are new, when `after` is `before` with more rows after
    the ones it had and nothing else changed (columns, flags, style, indent).
    """
    if not _tables_alike(before, after):
        return None
    held = len(before.rows)
    if len(after.rows) <= held or after.rows[:held] != before.rows:
        return None
    return after.rows[held:]


def appended_cell_text(
    before: BlockDescription, after: BlockDescription
) -> tuple[str, tuple[RunDescription, ...]] | None:
    """
    What `append_text` needs to turn table `before` into `after`, or `None` if it cannot.

    The library appends text to a table's LAST cell. So: the new characters,
    and the runs that are new **as ranges of the block's text**, when the
    two tables are equal but for their last cell, whose text grew at its end
    and whose runs before are the first of its runs now.
    """
    if not _tables_alike(before, after) or not before.rows or len(before.rows) != len(after.rows):
        return None
    if before.rows[:-1] != after.rows[:-1]:
        return None
    old_row, new_row = before.rows[-1], after.rows[-1]
    if not old_row or len(old_row) != len(new_row) or old_row[:-1] != new_row[:-1]:
        return None
    old, new = old_row[-1], new_row[-1]
    if len(new.text) <= len(old.text) or not new.text.startswith(old.text):
        return None
    held = len(old.runs)
    if new.runs[:held] != old.runs:
        return None
    # The last cell ends the block's text, so it starts this far into it.
    base = len(before.text) - len(old.text)
    runs = tuple(
        run._replace(start=run.start + base, end=run.end + base) for run in new.runs[held:]
    )
    return new.text[len(old.text) :], runs


class TypesetStreamView(TypesetView):
    """
    A `TypesetView` over a stream: draw it every frame, append whenever text arrives.

    The module docstring has the contract.
    """

    def __init__(
        self,
        stream: Any,
        *,
        palette: Palette | None = None,
        on_link: Callable[[str], None] | None = None,
        hand_cursor: bool = True,
        copy_as: Callable[[TypesetView], str] | None = None,
        style_links: bool | None = None,
        separator: str = "\n\n",
        follow: bool = True,
        host_for: HostFor | None = None,
        code_overflow: str = "wrap",
        fixed_line_height: bool = False,
    ) -> None:
        """
        `stream` is an `advtext.typeset_markdown.MarkdownStream`: it is read
        for `theme`, `revision`, `blocks`, `committed`, `live_theme`,
        `closed` and, for the source map, `source` and `sources`.
        The theme is the stream's, and so are the reader options: a
        `MarkdownStream(..., reader=...)` reads with them, and the view is
        given none. `code_overflow` and `fixed_line_height` are
        `TypesetView`'s ("How it is set" in its module docstring), checked
        here as there. Raises `TypesetUnavailable` when the library is not
        in use.
        """
        super().__init__(
            None,
            theme=stream.theme,
            palette=palette,
            on_link=on_link,
            hand_cursor=hand_cursor,
            copy_as=copy_as,
            style_links=style_links,
            separator=separator,
            host_for=host_for,
            code_overflow=code_overflow,
            fixed_line_height=fixed_line_height,
        )
        self.stream = stream
        self.follow = follow
        """Whether the view keeps the end in sight at all. Off: it never scrolls."""
        self._stream_revision: int | None = None
        # How many of the stream's blocks had committed at the last sync: a
        # table at or past this is still being written.
        self._live_from = 0
        self._following = True
        self._jump = False
        # The descriptions of the blocks `_set_blocks` is replacing, as they
        # were: what `_edit` compares the new ones with.
        self._before: list[BlockDescription] = []
        self.sync()

    # ------------------------------------------------------------------
    # Keeping up with the stream
    # ------------------------------------------------------------------

    def sync(self) -> bool:
        """
        Take in whatever the stream has received since the last call. True if a block changed.

        `draw` calls this. It reads `stream.revision`, which runs the stream's
        deferred parse; with the revision unchanged nothing else happens.
        At most one edit reaches the library, and none when the blocks are
        new objects that describe as the old ones did (`revision` still
        counts that as a change).

        Does nothing, and leaves the stream unread, once the library has been
        switched off (`typesetter.module()` is `None`): an edit would then
        raise out of here, where no caller expects `TypesetUnavailable`.
        """
        if typesetter.module() is None:
            return False
        revision = self.stream.revision
        if revision == self._stream_revision:
            return False
        self._stream_revision = revision
        return self._set_blocks(self.stream.blocks)

    def set_document(self, document: object, *, reader: Any = None) -> bool:
        """Refused: the stream is the document, and the next `sync` would put it back."""
        raise TypeError("a TypesetStreamView shows its stream; append to the stream instead")

    def set_table_widths(self, widths: str) -> bool:
        """
        Refused: how a stream's tables are sized is the stream's policy (`keeps_streamed`).

        A table still being written holds its columns, and a committed one
        keeps them or is fitted as the module docstring says. A settled
        `TypesetView` is what takes `table_widths="natural"`, to show a
        finished text as a stream that keeps had shown it.
        """
        raise TypeError(
            "a TypesetStreamView sizes its tables by its stream's policy (keeps_streamed); "
            "table_widths is a TypesetView's"
        )

    def set_theme(self, theme: Theme, document: object = None) -> bool:
        """Refused: the theme is the stream's, whose blocks are built with it."""
        raise TypeError("a TypesetStreamView is set in its stream's theme; make another stream")

    @property
    def source(self) -> str | None:
        """Everything the stream has been given (`stream.source`): what `source_of` indexes."""
        found = getattr(self.stream, "source", None)
        return found if isinstance(found, str) else None

    def source_of(self, block: int) -> BlockSource | None:
        """
        Where block `block` came from in `source`, as of the last `sync`; `None` if out of range.

        Read from the stream at each call (`stream.sources`), which is the
        stream's cost.
        """
        if not 0 <= block < len(self._blocks):
            return None
        sources = getattr(self.stream, "sources", ())
        return sources[block] if block < len(sources) else None

    def _asked_as(self, block: int) -> object:
        """
        `TypesetView._asked_as`, and whether the stream will change the block no more.

        A fence's last line with no newline is a line only once the block
        has committed or the stream has closed, neither of which changes the
        block (`advtext.ui.typeset_hosts.TypesetDiffFences` reads both).
        """
        settled = bool(getattr(self.stream, "closed", False)) or block < self._live_from
        return (super()._asked_as(block), settled)

    def keeps_streamed(self) -> bool:
        """
        Whether a block stays as it was shown when it commits: the stream's policy.

        Whether the stream's `live_theme` is its `theme` (a `MarkdownStream`
        given none builds its tail with the host's). True for a stream that
        has no `live_theme`. What it decides here is a committed table's
        columns (the module docstring).
        """
        live = getattr(self.stream, "live_theme", None)
        return live is None or live is self.stream.theme

    def _kept(self, blocks: Sequence[object]) -> int:
        """
        `TypesetView._kept`, stopping at a table that is held and has committed under reset.

        Such a table is described once more, without the flag, even when the
        block the stream committed is the object, or equal to the value, it
        showed live.
        """
        first = super()._kept(blocks)
        if not self.keeps_streamed():
            for at in self._tables:
                if at >= min(first, self._live_from):
                    break
                if self._described[at].flags & BLOCK_TABLE_HELD:
                    return at
        return first

    def _refuse_columns(self, count: int, height: float, gutter: float, balance: bool) -> None:
        """
        A stream is not shown in balanced columns: `ValueError`, and nothing changes.

        Balancing lays out every block and searches for the height again
        after every edit, and a stream is edited every time text arrives
        (`../imtypeset/docs/advtext-swap-status.md`, "Columns": "do not use
        it on a document that streams"). Columns filled in order
        (`height=`) are taken: the columns before an edit stand.

        **Not built**: following the tail in columns. `follow` scrolls the
        pane DOWN; in columns filled in order the newest text is in the last
        column, to the right, and a host that wants it in view scrolls there
        itself (`scroll_to` goes sideways).
        """
        if balance:
            raise ValueError(
                "set_columns: a TypesetStreamView does not balance its columns: the library "
                "lays out every block and searches for the height again after each edit, and "
                "a stream is edited whenever text arrives. Fill them in order (height=...), "
                "or show the finished text in a TypesetView"
            )

    def _describe_more(self, first: int) -> None:
        """Flag the tables that hold their columns: all under keep, the live ones under reset."""
        keep = self.keeps_streamed()
        for at in self._tables:
            if at >= first and (keep or at >= self._live_from):
                described = self._described[at]
                self._described[at] = described._replace(flags=described.flags | BLOCK_TABLE_HELD)

    def _set_blocks(self, given: Sequence[object], sources: Sequence[BlockSource] = ()) -> bool:
        blocks = tuple(given)
        self._live_from = len(getattr(self.stream, "committed", blocks))
        first = self._kept(blocks)
        self._before = self._described[first:]
        selection, dragging, anchor = self._selection, self._dragging, self._anchor
        texts = list(self._texts[first:]) if selection is not None or dragging else []
        try:
            changed = super()._set_blocks(blocks, sources)
        finally:
            self._before = []
        if changed and not self._all_selected:
            if selection is not None and self._selection is None:
                if self._same_text(selection, first, texts):
                    self._selection = selection
            if dragging and not self._dragging and self._same_text(anchor, first, texts):
                self._dragging = True
        return changed

    def _same_text(self, held: Range, first: int, texts: Sequence[str]) -> bool:
        """
        Whether `held` names the text it did before blocks `first` on were replaced.

        `texts` are those blocks' texts as they were.
        """
        (start, _), (end, offset) = held
        if end < first:
            return True
        now = self._texts
        if end >= len(now) or end - first >= len(texts):
            return False
        for block in range(max(start, first), end):
            if now[block] != texts[block - first]:
                return False
        was = texts[end - first]
        return offset <= len(was) and now[end][:offset] == was[:offset]

    def _edit(
        self,
        first: int,
        removed: int,
        described: Description,
        fresh: Sequence[StyleDescription],
    ) -> None:
        """
        Nothing, one append or one `replace_blocks`: the module docstring has which.

        A style the library has not been given (`fresh`) can only reach it
        through `replace_blocks`, so no shortcut is taken with one.
        """
        before, after = self._before, described.blocks
        same = 0
        limit = min(len(before), len(after))
        while same < limit and before[same] == after[same]:
            same += 1
        tail = 0
        if len(before) == len(after):
            if not fresh:
                if same == len(after):
                    return
                if same == len(after) - 1 and self._append(before[same], after[same]):
                    return
            # The blocks after the last one that changed stay as they are too.
            while tail < len(after) - same and before[-1 - tail] == after[-1 - tail]:
                tail += 1
        if same or tail:
            described = described._replace(blocks=after[same : len(after) - tail])
        super()._edit(first + same, removed - same - tail, described, fresh)

    def _append(self, before: BlockDescription, after: BlockDescription) -> bool:
        """
        Turn the document's last block from `before` into `after` by an append, if one can.
        """
        more = appended(before, after) or appended_cell_text(before, after)
        if more is not None:
            whole = self._doc.append_text(*more)
        else:
            rows = appended_rows(before, after)
            if rows is None:
                return False
            whole = self._doc.append_table_rows(rows)
        self.edits["append"] += 1
        self._cut(whole)
        return True

    # ------------------------------------------------------------------
    # Drawing, and following the tail
    # ------------------------------------------------------------------

    @property
    def following(self) -> bool:
        """Whether the view is keeping the end in sight, as of the last `draw`."""
        return self.follow and self._following

    def follow_tail(self) -> None:
        """Go to the end and follow it again, whatever the reader had scrolled to."""
        self._jump = True

    def draw(
        self,
        *,
        fonts: object = None,
        palette: Palette | None = None,
        width_px: float | None = None,
    ) -> bool:
        """
        Take in what has arrived, draw, and keep the end in sight if the reader is there.

        Call once a frame inside a scrolling child window; the scrolling it
        does is that window's. See `TypesetView.draw` for the rest, including
        `TypesetUnavailable`: while the library is not ready the stream is not
        read here at all, so a `StreamView` drawn instead over the same stream
        is the only one paying for it, and this view catches up in one edit
        if the library becomes ready.
        """
        from imgui_bundle import imgui

        if typesetter.ready():
            self.sync()
        # Read before anything is drawn: where the reader has left the pane as
        # of this frame, against the range it had before this frame's growth.
        at_bottom = imgui.get_scroll_y() >= imgui.get_scroll_max_y() - AT_BOTTOM_PX
        self._following = at_bottom or self._jump
        whole = super().draw(fonts=fonts, palette=palette, width_px=width_px)
        if self._scrolled:
            # Sent somewhere by `scroll_to` on this frame: that must not be
            # overwritten by a request for the end.
            self._following = False
        if self.follow and self._following:
            # The end of the pane, not of this view: a host may draw more
            # after it in the same child (`StreamView.draw` has the reasoning).
            imgui.set_scroll_y(FAR_PX)
        self._jump = False
        return whole

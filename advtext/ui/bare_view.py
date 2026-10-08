r"""
The embeddable view: a laid-out document in whatever pane the host gives it.

`advtext.ui.document_view.DocumentView` is the demo's presentation. It sets the
document on a light sheet narrower than the window, centres the sheet, and
claims the whole of it with one `invisible_button`. Every one of those is right
for a page and wrong for a pane in somebody else's application, where the text
should fill the width it is given, sit on the host's own background, and leave
the host's hover and context menus alone.

`BareView` is that view, and it is also **where the machinery both views share
lives**: the per-unit layout and its caches, the selection state, the mouse
handling, the copy, the cull. `DocumentView` is a subclass that adds a page and
overrides `draw`. There is one implementation of each of those things and the
demo runs on the same one a host does.

## What `BareView.draw` does and does not do

- **Fills the pane.** The measure is the content region's width (or the
  `width_px` the caller passes). No cap, no centring, no margin.
- **Paints no background.** Glyphs and the selection highlight go on whatever
  is already there. The default `Palette` has dark ink for a light page, so a
  host on a dark theme passes its own -- `DARK_PALETTE` in
  `advtext.backends.imgui_draw` is one, and nothing in the draw path reads a
  colour from anywhere but the palette it is given.
- **Draws each block in its role's ink** when the palette names any
  (`Palette.with_roles`): a heading, a quote, code and a table can each have
  their own. The role is the block's and the colour is chosen here, per unit;
  no glyph carries one.
- **Culls to the window.** Only the units the window can see are moved into
  place and drawn (`advtext.ui.units`).
- **Claims its height** so that what the host draws next lands below it.

## Where the mouse goes, and what is left for the caller

**While no drag is in progress the view submits no interactive item at all.**
It claims its rectangle with `imgui.dummy`, which has no ID: it is never the
hovered item, never the active one, and takes no click. So over the text

- `imgui.is_any_item_hovered()` is false and a host's
  `begin_popup_context_window` opens;
- right after `draw()`, `imgui.is_item_hovered()` is the dummy's and tells the
  host the mouse is over the document, and `begin_popup_context_item("an-id")`
  opens a menu for it (an explicit ID, because a dummy has none);
- `block_under_mouse()` says which block that is, so the tooltip or the menu
  can be about the paragraph or the code block being pointed at.

The view opens nothing itself.

**A left press on the text begins a selection, and only then is there an
item.** On the frame of the press, and on every frame until the button is
released, the view submits an `invisible_button` over its rectangle instead of
the dummy. ImGui makes a button clicked this frame the active item, and an
active item is what stops the press from also dragging the host's window --
which is the only reason `DocumentView` had its button in the first place.
When the button comes up the item is gone again.

A press begins a selection only if all of these hold, and the conditions are
the contract with the host:

- the left button went down this frame, inside the view's rectangle;
- the view's window is the hovered one (not behind a popup, not under another
  window, no other item active);
- **no item of the host's is under the mouse** -- so anything interactive the
  host draws over the text keeps its click, whether it is submitted before
  `draw` or after it. ImGui reports the item hovered so far this frame and
  otherwise the one hovered on the previous frame, and a press is always
  preceded by a frame of hovering, so an overlay submitted after the view is
  seen too. The view's own drag button is recognised and does not count, or
  the second press of a quick double click would be refused.

`_press_begins` is that predicate, in one place, for a subclass to narrow: a
view that draws links will want a press on a link not to start a drag.

**A drag, once begun, is anchored to text and lasts only while the view sees
it.** The fixed end of the selection is the characters the press landed on,
carried across a relayout the way a finished selection is, so resizing the
pane under a drag does not move it; and a view that is not drawn for a frame
has stopped dragging (and stopped holding a link down), because it cannot
know what the button did while it was away. `_begin_frame` and
`_carried_anchor` have the two cases that were measured.

## Links

A markdown link is live if the host gives the view an `on_link` callback, and a
live link is drawn in the palette's `link` ink with an underline. (`style_links`
overrides the second half either way; left alone, a view that cannot follow a
link draws it as text, which is also why the demo's page view looks as it did.)
Like everything else here a link is **not an ImGui item**: where it is comes
from the layout (`advtext.spans.LinkArea`), and the view asks whether the mouse
is in one of its rectangles.

- **Hover.** `hovered_link` is the target under the mouse as of the last
  `draw`, or `None` -- for the host's tooltip or status line. With
  `hand_cursor` (the default) the view also asks ImGui for the hand cursor
  while a live link is hovered.
- **Click.** A left press on a link followed by a release on *the same link*
  calls `on_link(target)`. A link broken across two lines is one link: press
  on one half, release on the other, and it is still a click.
- **A press on a live link never begins a selection.** That is the decision
  the two gestures needed, and it is the browser's: to select a link's text,
  start the drag beside it and drag across. The alternative -- start a drag,
  and call it a click only if the mouse did not move -- makes every click on
  a link a one-frame selection first and needs a movement threshold nobody
  can state a right value for. With no `on_link` a link is only styled, and a
  press on it selects like any other text.
- While a link is held down the view submits the same button it submits for a
  drag, for the same reason: so the press does not move the host's window.

A link in a table cell is a link like any other, wrapped cell or not
(`advtext.spans.map_table`).

## Colour finer than a block

`set_colours(block, spans)` gives one block a list of
`advtext.spans.ColourSpan`s -- an ink for some of its glyphs, a mark behind
them, or both, in the block's own material coordinates. That is the whole
interface for syntax highlighting (`ColourSpan(code_position(...), ..., ink=)`)
and for find-in-document (`find_spans(block, needle, mark=)`). Spans are kept
by block *number*, so a host that replaces the document sets them again.

Nothing is recomputed per frame for a block whose layout, spans and palette
have not changed: the decoration of each visible unit is kept from one frame
to the next and dropped when the unit scrolls out of view.

## Copy, and which view a keypress belongs to

Ctrl+C puts the selection on the clipboard **as the document reads**, not as it
happens to be wrapped: a blank line between blocks, a newline between code
lines, list items and table rows, a tab between cells, a space where the line
breaker wrapped (`advtext.ui.units.UnitModel.copy_text`). `selected_text()` is
that same string.

**One selection is current at a time, across every view in the process.** A
press that begins a selection in one view makes that view the owner; the view
that owned it before drops its selection on its next frame. Only the owner
answers Ctrl+C, so two panes with text in them do not both write the clipboard
on one keypress -- which they did, the second silently winning -- and a
keypress is never answered at all while ImGui has a text input active, because
then Ctrl+C is that input's. A selection made in code (`select`, `select_all`)
takes ownership the same way.

The host decides what a copy *is*. `copy_as` replaces the text Ctrl+C writes;
`selected_source(source)` is the verbatim markdown of the blocks the selection
touches, so `copy_as=lambda view: view.selected_source(source)` is "copy as
markdown". `copy(text)` writes the clipboard for a menu item of the host's.

## Context menus are the caller's

The view opens nothing. `pointed(x, y)` and `under_mouse()` say what is at a
screen position -- which block, which link if any, and whether the point is on
selected text -- and `block_text`, `block_source` and `source_of` turn a block
number into what a menu item would copy. A menu for "this paragraph" is then
`begin_popup_context_item("id")` straight after `draw`, as described above.

## Where the lines are

`set_lines(first_block, stop_block)` gives each line of text in the current
layout as a `SetLine` -- its block, its baseline, its glyphs and their x --
for a caller that wants to know what moved between two layouts, without
reaching into the layout's own structures and without the selection index
being built for it. `examples/stream_replay.py`'s counter is the caller it
was written for.

## A block the host draws: `host_for`

`host_for` is a callable, `(view, number, block) -> Hosted | None`. The view
asks it about each block of the document, once per block *object*, and a block
it answers for is not set as text: the layout reserves a rectangle as tall as
the `advtext.ui.Hosted` says it is, and `draw` hands that rectangle to it,
after the text and before the mouse is looked at. With no `host_for` (the
default) nothing is asked and every document is laid out as it always was.

It was built so that a fenced `diff` block is drawn by a
`advtext.ui.diff_view.DiffView` (`advtext.ui.diff_view.DiffFences` is that
callable), and it carries any widget with a height and a `draw`: nothing in
this module knows what a diff is.

- **The document is not changed.** `document.blocks[n]` is still the block
  the markdown made. `block_at`, `pointed`, `source_of`, `block_source` and
  `selected_source` name it as before, so "copy as markdown" over a hosted
  fence is the fence, verbatim. Only the layout holds the stand-in
  (`advtext.ui.HostBlock`), in a unit with no commands.
- **Its height is asked for every frame** and the layout is rebuilt on the
  frame it changes. Rebuilt means the stand-in's unit and the offsets below
  it; nothing above moves and no text is set again.
- **It is drawn only while its rectangle meets the window.**
- **The mouse over it is its own.** A press inside a hosted rectangle never
  begins a selection in this view, whatever the widget does with it. A
  `DiffView` takes its turn on the same selection counter as this view
  (`Copy`, above), so the document and the diffs in it hold one selection
  between them.
- **A selection that runs across it copies `Hosted.text` in its place**, on
  its own lines between the text either side, and the rectangle is washed in
  the selection colour while it does. A selection that stops at either edge
  of the widget copies none of it: the widget has no characters of its own
  in the reading order, so "part of it" is not something this view's
  selection can mean. To copy from inside it, select inside it.
  `block_text(n)` is `Hosted.text` too.
- **At an edge of the document it is taken by the select-all gesture, and
  by nothing else.** A widget that is the first or last thing in the
  document has text on one side at most, so the rule above never reaches it
  -- and a reply that ends in a diff is the usual shape. `select_all()`, or
  Ctrl+A while this view owns the selection, copies, washes and lists in
  `selected_blocks` the widgets before the first character and after the
  last. A drag or a click never does, however far it reaches: the boundary
  after the last character is also the boundary after the widget under it,
  and nobody pointed at the widget -- in a reply of one sentence and a diff,
  selecting the sentence is a selection from the first boundary to the last.
  The gesture is kept as state (it is not read off the range), so it lasts
  until the selection is next set or cleared, **and it stays select-all
  while the document grows**: a stream that gains text or a diff under it
  is still all selected. `advtext.ui.units.UnitModel.copy_text(...,
  everything=True)` is what it calls.
- **Text in the window does not move when a widget above the window changes
  height** (`_held_in_place`): the pane is scrolled by what the block at its
  top moved, and the frame is drawn from there.
- **A widget out of the window is not drawn, and is still asked for its
  keys** if it has a `handle_keys()`: a diff that owns the selection answers
  Ctrl+C after it has scrolled away.
- `DocumentView` draws hosted blocks the same way. It does not hold text in
  place when one grows above the window.
- Colour spans set on a hosted block are kept and not applied.
- `hosted(n)` is the widget standing for block `n`, for a host that wants to
  reach it (switch a diff to side by side, step through its hunks).

The hook is `BareView`'s and `StreamView`'s; `DocumentView` takes the same
`host_for` and has drawn what it hosts since review 2 (it reserved the room
and drew nothing in it before that).

## Width, and the scrollbar

The view draws from the cursor **snapped to a whole pixel** (`_cursor_origin`
says why a fraction matters and what was measured).


The layout is keyed by the measure, so a pane whose width changes re-breaks
every block. A child window's content region narrows by the scrollbar's width
on the frame the scrollbar first appears -- measured at 1084 to 1070 px in the
demo -- and a document that grows past the window therefore re-breaks once,
entirely. A host that cares gives the child `always_vertical_scrollbar`, or
passes a `width_px` it controls.

## What has and has not been run

- **Real ImGui frames with no display** (`tests/test_bare_view.py`): mouse
  events queued before `new_frame`, the selection read back, the item state
  asserted, the host's window watched for movement, both kinds of context
  menu opened.
- **A real window**, once, on 2026-10-06, under Xvfb with software GL and no
  window manager: a throwaway script drew a `BareView` in an `immapp` window,
  injected a hover, a press, a drag, a release and Ctrl+C through
  `io.add_*_event`, and read back: no item hovered over the text while idle,
  the block under the mouse, a drag that became the active item, the selected
  text, and the same text on the clipboard. That script is not in the tree;
  `scripts/mouse_probe.py` is the kept probe and it watches `DocumentView`,
  which runs the same `_handle_mouse` and `_handle_copy`.
- **Links, in the same kind of window**, on 2026-10-07: hovering the first
  line of a link set across two reported its target and the hand cursor;
  pressing made the view's button the active item and began no selection;
  releasing on the link's *second* line called `on_link` once; a link in a
  table cell was followed the same way. Also a throwaway script.
- **Copy, ownership and the host hooks**: headless frames only
  (`tests/test_bare_view.py`), with ImGui's in-memory clipboard. The page
  view's Ctrl+C, on the same `_handle_copy`, is what `scripts/mouse_probe.py`
  reads back from a real window.
- **Not run anywhere**: a real pointer, a window manager's focus and capture,
  a host with several panes. Nobody has looked at how a styled link or a
  marked find hit *looks*; the tests say which colours reach the draw list and
  where.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import chain
from typing import TYPE_CHECKING, ClassVar

from advtext.backends.imgui_draw import DrawStats, FaceFont, Palette, draw_runs
from advtext.markdown import (
    Block,
    BlockSource,
    CodeBlock,
    Document,
    LinkSpan,
    RuleBlock,
    TableBlock,
    TextBlock,
)
from advtext.pack import CharMeasure
from advtext.selection import Granularity, Rect, Selection
from advtext.shipout import DrawCmd, Glyph, Line, Point
from advtext.spans import (
    ColourSpan,
    Decoration,
    LinkArea,
    ShippedRun,
    SpanMap,
    SpanMapError,
    decorate,
    map_code_block,
    map_table,
    map_text_block,
    span_rects,
)
from advtext.style import BlockKind, Theme
from advtext.ui import HostBlock, Hosted, LayoutCache, Viewport
from advtext.ui.units import (
    LayoutStats,
    PlacedUnit,
    UnitCache,
    UnitLayout,
    carry_caret,
    carry_selection,
    layout_units,
)
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "CLIPBOARD_NUL",
    "MIN_WIDTH_PX",
    "SELECTION_OWNERSHIP",
    "BareView",
    "HostFor",
    "Hosted",
    "Pointed",
    "SelectionOwnership",
    "SetLine",
    "block_kind",
    "clipboard_text",
    "granularity_for",
    "scroll_for",
]

# Below this the line breaker has nothing to work with and every line is
# overfull. A window narrower than this is a window being resized through zero.
MIN_WIDTH_PX = 80.0


@dataclass(slots=True)
class SelectionOwnership:
    """
    Whose selection is current: a counter, bumped each time a view takes its turn.

    **Public for a widget of a host's own that has a selection** and wants to
    take turns with the views here, as `advtext.ui.diff_view.DiffView` does:
    call `take()` on `SELECTION_OWNERSHIP` when the widget's selection
    becomes the current one, keep the number, and answer Ctrl+C only while
    `holds(number)`. A second counter is the defect this exists to prevent --
    two panes both copying on one Ctrl+C.

    Module state, deliberately, and the only such state here. "Which view
    does Ctrl+C belong to" is a fact about the whole application and no one
    view can hold it; ImGui's own answer (keyboard focus) is not usable,
    because a view that submits no item cannot have it. A counter rather than
    a reference to the owning view, so that a view that has been dropped is
    not kept alive by having been the last one clicked in.

    One process, one current selection. Two ImGui contexts in one process
    share it, which is wrong for them and has not come up.
    """

    turn: int = 0

    def take(self) -> int:
        """
        Take the next turn: the number to keep, which is the current one until someone else takes.
        """
        self.turn += 1
        return self.turn

    def holds(self, taken: int) -> bool:
        """
        Whether the turn `taken` (from `take`) is still the current one. Zero never is.
        """
        return taken != 0 and taken == self.turn


SELECTION_OWNERSHIP = SelectionOwnership()
"""The one counter of this process. Every view here takes its turns on it."""

# The name it had before it was public.
_OWNERSHIP = SELECTION_OWNERSHIP


HostFor = Callable[["BareView", int, Block], Hosted | None]
"""
What `BareView.host_for` is: asked about a block, it answers with what draws it, or `None`.

Called with the view, the block's index into `document.blocks` and the block,
whenever the block at that index is an object the view has not asked about. A
finished document is therefore asked once per block; a stream is asked again
about each block of its unfinished tail every time the tail changes, which is
how a widget over a block still being written is told to grow. Returning the
same `Hosted` again keeps everything the view holds for it.
"""


@dataclass(slots=True)
class _Host:
    """
    One hosted block as the view holds it: who was asked about, who answered, what was reserved.
    """

    block: Block
    hosted: Hosted
    stand_in: HostBlock | None = None
    indent: Scaled = 0
    width_px: float = 0.0
    height_px: float = -1.0


@dataclass(frozen=True, slots=True)
class Pointed:
    """
    What is at a point of a view, for a caller building a menu or a tooltip.

    `block` indexes `document.blocks` and is `None` between blocks and outside
    the document. `link` is the target of the link at the point, if there is
    one. `selected` says whether the point is on selected text, which is what
    decides between a menu about the selection and a menu about the block.
    """

    block: int | None
    link: str | None
    selected: bool


@dataclass(frozen=True, slots=True)
class SetLine:
    """
    One line of text as it was set: which block it is a line of, and where its glyphs are.

    What `BareView.set_lines` returns. `baseline` is the line's baseline in
    the document's scaled points, measured down from the document's top;
    `glyphs` is each glyph on it, left to right in reading order, as
    `(codepoint, x)` with `x` the glyph's left edge in the same units.
    Spaces are not in it: a space is glue and has no codepoint.

    Frozen and hashable, so two layouts' lines can be compared as sets:
    a line is equal to another when it is a line of the same block with the
    same glyphs at the same places on the same baseline, and a line that
    kept its words and moved by one scaled point is a different line.
    """

    block: int
    """Index into `document.blocks` of the block this is a line of."""
    baseline: Scaled
    glyphs: tuple[tuple[int, Scaled], ...]


def block_kind(block: Block) -> BlockKind:
    """
    The role a block plays, for anything that treats one kind differently from another.

    A `TextBlock` says so itself -- a heading level, a paragraph, a list item,
    a quote. The other three block types are each one kind and do not carry
    the field, so it is read off the type. This is the lookup a per-role
    palette is keyed by (`advtext.backends.imgui_draw.Palette.ink_for`).
    """
    match block:
        case TextBlock():
            return block.kind
        case CodeBlock():
            return BlockKind.CODE
        case TableBlock():
            return BlockKind.TABLE
        case RuleBlock():
            return BlockKind.RULE


@dataclass(slots=True)
class BareView:
    """
    A selectable view of one document that fills the pane it is drawn in.

    Mutable, unlike almost everything else in this project, and for the reason
    `advtext.pack` gives about `Store` in pptmstr's `STYLE.md`: this *is* the
    imperative shell. It holds caches and a few pieces of interaction state,
    and every decision it makes is delegated to a pure module.

    Replace `document` (or `theme`) and call `invalidate`; the next `draw`
    re-lays-out only the blocks that changed. The module docstring has the
    mouse contract.
    """

    document: Document
    theme: Theme
    measure: CharMeasure
    px_per_inch: float = DEFAULT_PX_PER_INCH
    debug: bool = False
    on_link: Callable[[str], None] | None = None
    """Called with a link's target when it is clicked. `None`: links are not live."""
    hand_cursor: bool = True
    """Whether to ask ImGui for the hand cursor while a live link is hovered."""
    copy_as: Callable[[BareView], str] | None = None
    """What Ctrl+C writes, given this view. `None`: `selected_text()`."""
    style_links: bool | None = None
    """
    Whether links are drawn in the palette's `link` ink and underlined.

    `None`, the default, means "when they are live": styled if `on_link` is
    set and plain text if it is not, so that a view which cannot follow a link
    does not draw one as though it could. `True` styles them regardless and
    `False` never does.
    """
    host_for: HostFor | None = None
    """
    Which blocks something else draws, and what draws them. `None`: none are.

    See "A block the host draws" in the module docstring. Give it when the
    view is made: a block is asked about once, so a hook put in later is
    asked only about blocks the view has not yet seen as they are.
    """

    _CODE_LINES: ClassVar[int] = 0
    """
    Passed to `layout_units` as `code_lines`: zero lays every code block out whole.

    A class constant and not an option, because for a document that is not
    changing there is nothing to gain: a settled block's unit is built once
    either way. `advtext.ui.stream_view.StreamView` overrides it, and
    everything in this class that names a block copes with one laid out in
    pieces whether or not that ever happens here.
    """

    _TABLE_ROWS: ClassVar[int] = 0
    """
    Passed to `layout_units` as `table_rows`: zero lays every table out whole.

    The same switch for a table, off here for the same reason and on in
    `advtext.ui.stream_view.StreamView`, where a table gains a row at a time.
    """

    _layout: UnitLayout | None = field(default=None, init=False)
    # Survives `invalidate`, unlike `_layout`, and that is the point of it: a
    # caller that changed one block of the document drops the whole layout and
    # this re-breaks only the block that changed. `advtext.ui.LayoutCache` has
    # the measurement and the honest account of what it does not buy.
    _blocks: LayoutCache = field(default_factory=LayoutCache, init=False)
    # One stage later, and in front of `_blocks`: the *shipped* form of each
    # unit. It also survives `invalidate`, so a caller that changed one block
    # re-ships one block. `advtext.ui.units` has the measurements.
    _units: UnitCache = field(default_factory=UnitCache, init=False)
    # The last layout built, kept across `invalidate` so that the units an edit
    # did not move keep their placed commands and their selection index. Not
    # the cache `layout_for` answers from -- that is `_layout`.
    _previous: UnitLayout | None = field(default=None, init=False)
    _selection: Selection = field(default=Selection(0, 0), init=False)
    # The select-all gesture (`select_all`, Ctrl+A) was the last thing to set
    # the selection: the hosted blocks at the document's edges are part of
    # it, and it grows with the document. See `_everything`.
    _all_selected: bool = field(default=False, init=False)
    # Where a drag was put down, as reading-order boundaries of the layout in
    # `_previous`: a caret for a single click, the word for a double, the
    # line for a triple. Text, not a place; `_carried_anchor` says why.
    _anchor: Selection = field(default=Selection(0, 0), init=False)
    _granularity: Granularity = field(default=Granularity.CHARACTER, init=False)
    _dragging: bool = field(default=False, init=False)
    # The ImGui frame this view was last drawn on. A drag or a held link goes
    # on only from one frame to the very next (`_begin_frame`).
    _drawn_frame: int = field(default=-(2**31), init=False)
    # Whether a left press began on the text this frame. Decided in `draw`
    # before any item exists, and read by `_pressed`.
    _press: bool = field(default=False, init=False)
    # Where the document's (0, 0) was on screen at the last `draw`, in pixels.
    _origin: tuple[float, float] | None = field(default=None, init=False)
    # The host's colour spans, by block number.
    _colours: dict[int, tuple[ColourSpan, ...]] = field(default_factory=dict, init=False)
    # Each visible unit's decoration, kept between frames. Keyed by the unit's
    # shipped commands (by identity; the tuple is held so the id stays valid),
    # where it sits and what it was decorated with.
    _decorated: dict[tuple[int, int, Scaled], tuple[object, object, Decoration]] = field(
        default_factory=dict, init=False
    )
    # A block's colour spans restated for one piece of it, by block number
    # and piece: the spans they were cut from (by identity), the material
    # range of the piece, and the result. Rebuilt each paint from what it used.
    _pieced: dict[
        tuple[int, int], tuple[tuple[ColourSpan, ...], tuple[int, int], tuple[ColourSpan, ...]]
    ] = field(default_factory=dict, init=False)
    # The links on screen at the last paint, the one under the mouse, and the
    # one the left button went down on.
    _links: tuple[LinkArea, ...] = field(default=(), init=False)
    _hot: LinkArea | None = field(default=None, init=False)
    _link_down: tuple[int, int] | None = field(default=None, init=False)
    _unmapped: int = field(default=0, init=False)
    # Which turn at owning the selection this view last took; zero for never.
    # It owns the selection while this equals `_OWNERSHIP.turn`.
    _owned: int = field(default=0, init=False)
    # The hosted blocks, by block number; the `document.blocks` tuple they
    # were last asked about; and where each one drawn on the last frame was
    # on screen, as (left, top, right, bottom) pixels.
    _hosts: dict[int, _Host] = field(default_factory=dict, init=False)
    _host_seen: tuple[Block, ...] | None = field(default=None, init=False)
    _host_rects: tuple[tuple[float, float, float, float], ...] = field(default=(), init=False)
    # A `scroll_to` not yet carried out: the rectangle, the margin in pixels,
    # the fraction and whether to move what is already in view. Carried out
    # and dropped by the next `draw`, which is the only place that is inside
    # the window being scrolled.
    _scroll: tuple[Rect, float, float | None, bool] | None = field(default=None, init=False)
    # Whether the last `draw` asked ImGui to scroll for a `scroll_to`.
    _scrolled: bool = field(default=False, init=False)
    # The band of the document the last `draw` showed.
    _viewport: Viewport | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def layout_for(self, width: Scaled) -> UnitLayout:
        """
        The cached layout for a width, recomputing only when the width changed.

        The equality test is on the scaled-point width, not the pixel one: a
        window dragged by a sub-pixel amount produces the same measure and must
        not re-break the whole document.

        **A recompute is per unit, not per document.** `advtext.ui.units` ships
        and indexes each independent run of blocks on its own and stacks them
        by offset, and `_units` keeps the shipped ones. After `invalidate`, a
        document in which one block changed composes, ships and indexes that
        block; the rest are found, not rebuilt. A changed *width* still misses
        on every unit, for the reason `LayoutCache` gives.
        """
        cached = self._layout
        if cached is not None and cached.width == width:
            return cached
        fresh = layout_units(
            self._layout_blocks(width),
            self.theme,
            width,
            self.measure,
            units=self._units,
            cache=self._blocks,
            previous=self._previous,
            code_lines=self._CODE_LINES,
            table_rows=self._TABLE_ROWS,
        )
        if self._previous is not None:
            # The reading order may have been renumbered under the selection,
            # and under the anchor of a drag in progress. Both are carried: a
            # drag restates its selection from the anchor on every frame it
            # is drawn, but the anchor is integers too, and a drag that ends
            # before the next frame leaves the selection as it stands here.
            if self._dragging:
                anchor = _carried_anchor(self._anchor, self._previous, fresh)
                if anchor is None:
                    # The text the drag was put down on is no longer there to
                    # drag from. The drag is over; what was selected is
                    # carried or cleared below like any other selection.
                    self._dragging = False
                else:
                    self._anchor = anchor
            if not self._selection.is_empty and not self._all_selected:
                self._selection = self._carry(self._selection, self._previous, fresh)
        if self._all_selected:
            # Select-all is a statement about the document, not about the
            # characters it had when it was made: a stream that grows under
            # it is still all selected (review 3, item 4).
            self._selection = Selection(0, fresh.length)
        self._layout = fresh
        self._previous = fresh
        return fresh

    def _layout_blocks(self, width: Scaled) -> tuple[Block, ...]:
        """
        The blocks to lay out at this width. The document's, unless a subclass says otherwise.

        The seam a view uses to lay out something a little different from
        what it was given -- a streaming view holds a growing table's columns
        still -- without owning a second layout path.

        `_hosted` is the other user of it: a block the host draws is laid out
        as an `advtext.ui.HostBlock` of the height its widget asks for.
        """
        blocks = self.document.blocks
        return self._hosted(blocks, blocks, width)

    def _unchanged_blocks(self, blocks: tuple[Block, ...]) -> int:
        """
        How many leading blocks are known to be the objects `host_for` was last asked about.

        All of them if this is the very tuple last looked at, and none
        otherwise: a view of a finished document has nothing finer to go on.
        `advtext.ui.stream_view.StreamView` knows its committed blocks never
        change and says so.
        """
        return len(blocks) if blocks is self._host_seen else 0

    def _hosted(
        self, blocks: tuple[Block, ...], out: tuple[Block, ...], width: Scaled
    ) -> tuple[Block, ...]:
        """
        `out` with every block the host draws replaced by a stand-in of its widget's height.

        `blocks` is the document's; `out` is what would be laid out, which is
        the same tuple unless a subclass has already replaced something in it.
        With no `host_for`, or nothing hosted, `out` comes back as it is.

        **`host_for` is asked about a block once per object** (`HostFor`), and
        a stand-in is the same object for as long as it stands for the same
        widget at the same height and indent -- so a layout pass in which no
        widget changed finds every hosted unit by identity, like any other.
        A widget whose height changed gets a new stand-in and with it a new
        unit, which costs composing one kern.

        The widget is as wide as the measure less whatever the block is
        indented by *beyond its own style* -- a fence in a list item starts at
        the item's text, and one at the top level at the margin, not at the
        code style's indent: it is not being set as code.
        """
        hosts = self._hosts
        if self.host_for is None:
            hosts.clear()
            self._host_seen = None
            return out
        for number in [number for number in hosts if number >= len(blocks)]:
            del hosts[number]
        for number in range(self._unchanged_blocks(blocks), len(blocks)):
            block = blocks[number]
            known = hosts.get(number)
            if known is not None and known.block is block:
                continue
            hosted = self.host_for(self, number, block)
            if hosted is None:
                hosts.pop(number, None)
            elif known is not None and known.hosted is hosted:
                known.block = block
            else:
                hosts[number] = _Host(block, hosted)
        self._host_seen = blocks
        if not hosts:
            return out

        laid = list(out)
        for number, host in hosts.items():
            block = host.block
            indent = max(block.left_indent - block.style.left_indent, 0)
            width_px = max(px_from_sp(width - indent, self.px_per_inch), 1.0)
            height_px = max(float(host.hosted.height_for(width_px)), 0.0)
            stand_in = host.stand_in
            if (
                stand_in is None
                or host.height_px != height_px
                or stand_in.left_indent != block.left_indent
                or stand_in.style is not block.style
            ):
                stand_in = HostBlock(
                    style=block.style,
                    lines=(),
                    language=block.language if isinstance(block, CodeBlock) else "",
                    left_indent=block.left_indent,
                    height=sp_from_px(height_px, self.px_per_inch),
                    host=host.hosted,
                )
            host.stand_in = stand_in
            host.indent = indent
            host.width_px = width_px
            host.height_px = height_px
            laid[number] = stand_in
        return tuple(laid)

    def _hosts_resized(self) -> bool:
        """
        Whether some hosted widget now wants a height other than the one reserved for it.

        Asked once a frame, before the layout is: a diff that gained a line,
        or had its context expanded by a click, is given its room on the
        frame it says so. One `height_for` per hosted block and nothing else.
        """
        return any(
            max(float(host.hosted.height_for(host.width_px)), 0.0) != host.height_px
            for host in self._hosts.values()
            if host.stand_in is not None
        )

    def hosted(self, block: int) -> Hosted | None:
        """
        What draws `document.blocks[block]` in this view, or `None` if the view sets it itself.

        As of the last layout. For a host that wants the widget back: to
        switch an embedded diff to side by side, or step through its hunks.
        """
        host = self._hosts.get(block)
        return None if host is None else host.hosted

    def _carry(self, selection: Selection, old: UnitLayout, new: UnitLayout) -> Selection:
        """
        The selection after a relayout: the same text, or nothing.

        `advtext.ui.units.carry_selection` has the rule and the reason. What
        it cannot carry is cleared here, because the alternative is a
        selection that silently means other words.
        """
        carried = carry_selection(selection, old, new)
        return Selection(0, 0) if carried is None else carried

    def invalidate(self) -> None:
        """
        Drop the layout, for a caller that changed the document or the theme.

        The caches underneath are kept, which is what makes this cheap: the
        next layout finds every block that did not change.
        """
        self._layout = None

    @property
    def layout(self) -> UnitLayout | None:
        """
        The layout the last `draw` or `layout_for` produced, or `None` before the first.

        Public so that a host, a test or a probe can ask where things are --
        which unit sits where, which indices it owns -- without re-deriving a
        width the view chose inside `draw`.
        """
        return self._layout

    @property
    def origin(self) -> tuple[float, float] | None:
        """
        Where the document's top-left was on screen at the last `draw`, in pixels.

        `None` until something has been drawn. This is the point every glyph,
        every highlight and every hit test was measured from on that frame, so
        screen coordinates minus this are document coordinates.
        """
        return self._origin

    @property
    def selection(self) -> Selection:
        """
        What is currently selected, as reading-order boundaries.
        """
        return self._selection

    def _selection_layout(self) -> UnitLayout | None:
        """
        The layout the selection's boundaries count in: the current one, else the last built.

        Between `invalidate` (or a stream view's `sync`) and the next layout
        there is no current layout, and the selection is still what it was:
        boundaries in the layout that was current when it was made, which
        `_previous` keeps until the next one carries them across. Reading
        the selection in that gap used to give the empty string.
        """
        return self._layout if self._layout is not None else self._previous

    def selected_text(self) -> str:
        """
        The current selection as text, or the empty string if nothing is selected.

        After `invalidate` and before the next layout this is the text as it
        was last laid out, which is the text the selection was made on.
        """
        layout = self._selection_layout()
        if layout is None:
            return ""
        return layout.model.copy_text(self._selection, everything=self._everything(layout))

    def _everything(self, layout: UnitLayout) -> bool:
        """
        Whether the selection is the whole document, hosted blocks at its
        edges included (`UnitModel.copy_text` has the rule and its reason).

        **Only the select-all gesture makes it so** -- `select_all()`, or
        Ctrl+A in the view that owns the selection -- and it is kept as
        state until the selection is next set or cleared. It is never read
        off the range. It was, for one task (C-hostfix: "from the first
        boundary to the last"), and that got both cases wrong (review 3,
        item 4): in a reply of one sentence and a diff, selecting the
        sentence *is* first-to-last and copied the diff nobody pointed at;
        and select-all made while a reply was arriving stopped being
        everything when the next piece came. `layout` is not read; the
        argument stays because callers have one.
        """
        return self._all_selected

    def clear_selection(self) -> None:
        """
        Select nothing, and abandon a drag in progress.
        """
        self._selection = Selection(0, 0)
        self._all_selected = False
        self._dragging = False

    def select(self, selection: Selection) -> None:
        """
        Make `selection` this view's selection, and this view the one Ctrl+C answers for.

        Boundaries are clamped to the document on the next layout query, as a
        dragged selection's are. Selecting takes ownership (see "Copy" in the
        module docstring), so whichever view held the current selection drops
        it on its next frame.
        """
        self._selection = selection
        self._all_selected = False
        self._dragging = False
        self._own()

    def select_all(self) -> None:
        """
        Select the whole document as last laid out. Nothing, before the first layout.
        """
        layout = self._selection_layout()
        self.select(Selection(0, 0 if layout is None else layout.length))
        self._all_selected = True

    @property
    def owns_selection(self) -> bool:
        """
        Whether this view's selection is the current one: the one Ctrl+C copies.
        """
        return SELECTION_OWNERSHIP.holds(self._owned)

    def _own(self) -> None:
        self._owned = SELECTION_OWNERSHIP.take()

    # ------------------------------------------------------------------
    # What a copy or a context menu would want
    # ------------------------------------------------------------------

    def selected_blocks(self) -> tuple[int, ...]:
        """
        The blocks the selection touches, as indices into `document.blocks`, in order.

        As last laid out, like `selected_text`: after `invalidate` and before
        the next layout these number the blocks of the document that layout
        was of. A stream's blocks keep their numbers; a host that replaced
        the document with an unrelated one should lay out before asking.
        """
        layout = self._selection_layout()
        if layout is None:
            return ()
        everything = self._everything(layout)
        if self._selection.is_empty and not everything:
            return ()
        chosen = layout.model.select(self._selection.start, self._selection.end)
        blocks: list[int] = []
        # A hosted block at an edge of the document holds no index, so no
        # range of indices touches it: it is selected with everything, as it
        # is copied with everything (`UnitModel.copy_text`).
        leading, trailing = layout.model.edge_hosts() if everything else ((), ())
        blocks += [layout.placed[position].block_start for position in leading]
        for unit in layout.placed:
            if unit.base >= chosen.end:
                break
            for number in unit.block_range:
                own = unit.indices_of(number)
                if own.start < chosen.end and own.stop > chosen.start:
                    # Once, for a code block several of whose pieces it touches.
                    if not blocks or blocks[-1] != number:
                        blocks.append(number)
        blocks += [layout.placed[position].block_start for position in trailing]
        return tuple(blocks)

    def block_text(self, block: int) -> str:
        """
        One block as a copy would give it: its text, structure and all. Empty if unknown.

        A code block's lines come back newline-joined, a table as tabs and
        newlines, a list item with its marker. A block the host draws
        (`host_for`) comes back as its widget's `text`.
        """
        layout = self._layout
        if layout is None or not layout.units_of_block(block):
            return ""
        host = self._hosts.get(block)
        if host is not None and host.stand_in is not None:
            # A hosted block has no item of its own to select; what it copies
            # as is its widget's to say.
            return str(host.hosted.text).removesuffix("\n")
        own = layout.indices_of_block(block)
        return layout.model.copy_text(Selection(own.start, own.stop))

    def block_source(self, block: int, source: str, *, top: bool = False) -> str | None:
        """
        One block's markdown, cut verbatim from `source`, or `None` if it has no record.

        `source` is the string the document was built from; the view does not
        keep it. `top=True` gives the whole top-level block the block is part
        of -- the whole list for one of its items, the whole quote for one of
        its paragraphs.
        """
        where = self.document.source_of(block)
        if where is None:
            return None
        return (where.top if top else where.span).of(source)

    def selected_source(self, source: str) -> str:
        """
        The verbatim markdown of every block the selection touches: "copy as markdown".

        **Whole blocks, not the selected characters.** Nothing maps a
        character of rendered text back to an offset in the markdown -- white
        space is collapsed and markup dropped on the way in -- so a selection
        of two words gives its whole paragraph. Each block's own source lines
        are taken once, in document order; lines that are next to each other
        in the source stay next to each other, and where the selection skips
        source lines one blank line stands for the gap.
        """
        spans = []
        for block in self.selected_blocks():
            where = self.document.source_of(block)
            if where is not None and where.span not in spans:
                spans.append(where.span)
        spans.sort(key=lambda span: span.line_start)
        pieces: list[str] = []
        previous_end: int | None = None
        for span in spans:
            if previous_end is not None and span.line_start < previous_end:
                continue
            text = span.of(source)
            if pieces and previous_end is not None and span.line_start > previous_end:
                if not pieces[-1].endswith("\n"):
                    pieces.append("\n")
                pieces.append("\n")
            pieces.append(text)
            previous_end = span.line_end
        return "".join(pieces)

    def copy(self, text: str | None = None) -> None:
        """
        Put `text` on the clipboard, or the selection as Ctrl+C would if none is given.
        A NUL in it goes as `CLIPBOARD_NUL` (`clipboard_text`), here and for Ctrl+C.

        For a menu item of the host's. Needs a live ImGui context and nothing
        else; it does not check ownership, because the host asked.
        """
        from imgui_bundle import imgui

        imgui.set_clipboard_text(clipboard_text(self._copied() if text is None else text))

    def _copied(self) -> str:
        """
        What a copy of the selection writes: the host's `copy_as`, else the text.
        """
        return self.selected_text() if self.copy_as is None else self.copy_as(self)

    def pointed(self, screen_x: float, screen_y: float) -> Pointed:
        """
        What is at a screen position, as of the last `draw`: block, link, selection.

        Geometry only -- it does not ask whether this view's window is the
        hovered one -- so it is for a host that already knows the mouse is
        over the document (`imgui.is_item_hovered()` after `draw`) and wants
        to know what to put in its menu or its tooltip. Any link counts here,
        live or not: a "copy link address" item does not need `on_link`.

        **Cheap enough to call every frame.** Whether the point is on
        selected text is asked of the units that have ink at the point's y
        (`UnitLayout.visible_rects` over a band one scaled point tall), so at
        most the unit under the point has its selection index built. Asking
        the whole selection for its rectangles instead indexed every unit a
        select-all covers: measured at 5 units indexed before one call and
        740 after, on twenty copies of `demo/sample.md`.
        """
        point = self.document_point(screen_x, screen_y)
        layout = self._layout
        if point is None or layout is None:
            return Pointed(block=None, link=None, selected=False)
        link = next((area.target for area in self._links if area.contains(point.x, point.y)), None)
        selected = any(
            rect.x <= point.x < rect.x + rect.width and rect.y <= point.y < rect.y + rect.height
            for rect in layout.visible_rects(self._selection, Viewport(point.y, point.y + 1))
        )
        return Pointed(block=layout.block_at(point), link=link, selected=selected)

    def under_mouse(self) -> Pointed:
        """
        `pointed` at the mouse: what a right click here would be about.
        """
        from imgui_bundle import imgui

        mouse = imgui.get_mouse_pos()
        return self.pointed(mouse.x, mouse.y)

    # ------------------------------------------------------------------
    # Colour and links
    # ------------------------------------------------------------------

    def set_colours(self, block: int, spans: Sequence[ColourSpan]) -> None:
        """
        Colour parts of one block: replaces whatever spans that block had.

        `block` is an index into `document.blocks`; the spans are in that
        block's material coordinates (`advtext.spans.ColourSpan`). An empty
        sequence removes the block's colours. Takes effect on the next `draw`
        and costs nothing on the frames after it until something changes.

        Only text blocks and code blocks can be coloured. Spans set on a table
        or a rule are kept and ignored: a table's cells each have their own
        material and one span cannot say which it means.
        """
        if spans:
            self._colours[block] = tuple(spans)
        else:
            self._colours.pop(block, None)

    def clear_colours(self) -> None:
        """
        Remove every colour span from every block.
        """
        self._colours.clear()

    @property
    def hovered_link(self) -> str | None:
        """
        The target of the live link under the mouse at the last `draw`, or `None`.

        `None` when the view has no `on_link`, when the mouse is elsewhere, and
        when something of the host's is in front of the text.
        """
        return None if self._hot is None else self._hot.target

    @property
    def visible_links(self) -> tuple[LinkArea, ...]:
        """
        Every link on screen at the last `draw`, with its rectangles in document space.
        """
        return self._links

    @property
    def unmapped_blocks(self) -> int:
        """
        How many times a block's decoration was skipped because it could not be mapped.

        Zero unless `advtext.spans` refused a block (`SpanMapError`). A refusal
        is swallowed here rather than raised -- an exception out of a draw
        call takes the host's frame with it, sixty times a second -- so this
        counter is where it shows. The block is drawn undecorated.
        """
        return self._unmapped

    # ------------------------------------------------------------------
    # Where things are, for the caller's hover and context menus
    # ------------------------------------------------------------------

    def document_point(self, screen_x: float, screen_y: float) -> Point | None:
        """
        A screen position in the document's own scaled points, or `None` before a draw.
        """
        if self._origin is None:
            return None
        return Point(
            sp_from_px(screen_x - self._origin[0], self.px_per_inch),
            sp_from_px(screen_y - self._origin[1], self.px_per_inch),
        )

    def block_at(self, screen_x: float, screen_y: float) -> int | None:
        """
        The index into `document.blocks` of the block at a screen position, or `None`.

        `None` between blocks, outside the document, and before the first
        draw. By `y` alone (`UnitLayout.unit_at` says why): a point in the
        white beside a paragraph is beside that paragraph.
        """
        point = self.document_point(screen_x, screen_y)
        if point is None or self._layout is None:
            return None
        return self._layout.block_at(point)

    def block_under_mouse(self) -> int | None:
        """
        The block the mouse is over, as an index into `document.blocks`, or `None`.

        Pure geometry against the last draw: it does not ask whether this
        view's window is the hovered one. Call it when `imgui.is_item_hovered()`
        is true right after `draw`, which is the question "is the mouse over
        this document and nothing in front of it".
        """
        from imgui_bundle import imgui

        mouse = imgui.get_mouse_pos()
        return self.block_at(mouse.x, mouse.y)

    def source_of(self, block: int) -> BlockSource | None:
        """
        Where a block came from in the markdown source, if the document records it.

        With `block_under_mouse` this is "the verbatim source of the block
        being pointed at": `view.source_of(block).span.of(source)`.
        """
        return self.document.source_of(block)

    @property
    def layout_stats(self) -> LayoutStats | None:
        """
        What the last layout this view *built* did, or `None` before the first.

        Units built and found, blocks broken, and the time
        (`advtext.ui.units.LayoutStats`). Kept across `invalidate`, and
        unchanged by a frame that answered from the layout it already had --
        so a host reads it after `draw` or `layout_for` and knows a relayout
        happened when `layout.stats` is a new object. Each unit's own build
        time is `layout.placed[i].unit.build_seconds`.
        """
        return None if self._previous is None else self._previous.stats

    def block_rect(self, block: int) -> Rect | None:
        """
        Where `document.blocks[block]` is in the current layout, in document scaled points.

        `None` when there is no current layout (before the first, and after
        `invalidate` until the next) or no such block. On or off screen: this
        is the layout's answer and the window is not asked. `to_screen` turns
        it into pixels and `scroll_to` brings it into view.

        **The full measure wide, and as tall as the block's own extent.**
        One paragraph of a quote has its own rectangle, not the quote's; a
        code block or a table laid out in pieces has one rectangle from the
        top of its first piece to the bottom of its last. The width is the
        layout's and not the ink's: a view has no per-block x extent, and a
        host that wants the indent has `block.left_indent`. The space
        between two blocks belongs to neither rectangle.
        """
        layout = self._layout
        if layout is None:
            return None
        units = layout.units_of_block(block)
        if not units:
            return None
        first, last = units[0], units[-1]
        if first.part is None:
            top, bottom = first.unit.extents[block - first.block_start]
            return Rect(0, first.y + top, layout.width, bottom - top)
        return Rect(0, first.y, layout.width, last.bottom - first.y)

    def span_rects(
        self, block: int, start: int, end: int, *, cell: tuple[int, int] | None = None
    ) -> list[Rect]:
        """
        Where material `[start, end)` of a block is: a rectangle a line, in document scaled points.

        The coordinates are a `ColourSpan`'s: a text block's material
        indices, a code block's flat ones (`advtext.spans.code_position`).
        For a table give `cell=(row, column)` -- the header is row zero when
        there is one -- and the range is in that cell's material. An
        `advtext.spans.TextMatch` carries all four, so a find hit is
        `view.span_rects(m.block, m.start, m.end, cell=m.cell)`.

        Top to bottom, on or off screen, each the full height of its line:
        the rectangles a `ColourSpan`'s `mark` would fill. Empty when there
        is no current layout, no such block or cell, nothing in the range
        that was shipped, for a table without a `cell` or anything else with
        one, for a block the host draws, and when the block's material
        cannot be matched to what was shipped (`SpanMapError`; not counted in
        `unmapped_blocks`, which is about drawing).

        **Not free**: it maps the block and builds the selection index of
        each unit that sets it, and a table is mapped whole for one cell.
        Nothing is kept between calls. It is for the one match a host is
        about to scroll to or outline, not for every match every frame --
        `set_colours` marks those, and caches.
        """
        layout = self._layout
        if layout is None or end <= start or block in self._hosts:
            return []
        if not 0 <= block < len(self.document.blocks):
            return []
        rects: list[Rect] = []
        rows_before = 0
        for unit in layout.units_of_block(block):
            # The block as this unit set it: the document's own, or the piece
            # of it this unit is.
            piece = unit.blocks[block - unit.block_start]
            own = unit.indices_of(block)
            before = unit.skipped if unit.part is not None else 0
            runs: tuple[ShippedRun, ...]
            try:
                match piece:
                    case TextBlock() if cell is None:
                        if len(unit.blocks) == 1:
                            mapped = map_text_block(piece, unit.cmds)
                        else:
                            mapped = map_text_block(
                                piece, unit.cmds, start=own.start, stop=own.stop
                            )
                        runs = mapped.runs(start, end)
                    case CodeBlock() if cell is None:
                        # A piece is mapped from zero and the span counts from
                        # the start of the block; `runs` clips to the piece.
                        runs = map_code_block(piece, base=own.start).runs(
                            start - before, end - before
                        )
                    case TableBlock() if cell is not None:
                        rows = [piece.header, *piece.rows] if piece.header else list(piece.rows)
                        local = cell[0] - rows_before
                        rows_before += len(rows)
                        if not 0 <= local < len(rows) or not 0 <= cell[1] < len(rows[local]):
                            continue
                        wanted = rows[local][cell[1]]
                        runs = ()
                        for held, mapped in map_table(piece, unit.unit.box, base=own.start):
                            if held is wanted:
                                runs = mapped.runs(start, end)
                                break
                    case _:
                        return []
            except SpanMapError:
                continue
            if runs:
                rects.extend(span_rects(unit.model, runs))
        return rects

    def to_screen(self, rect: Rect) -> tuple[float, float, float, float] | None:
        """
        A document-space rectangle as `(left, top, right, bottom)` screen pixels, or `None`.

        Against the origin of the last `draw` (`origin`), so `None` before
        anything has been drawn, and one frame stale on a frame the pane
        scrolled or the window moved before this view was drawn. Not clipped:
        a rectangle that is off screen comes back with coordinates outside
        the window, which is how a host tells.
        """
        if self._origin is None:
            return None
        ppi = self.px_per_inch
        left = self._origin[0] + px_from_sp(rect.x, ppi)
        top = self._origin[1] + px_from_sp(rect.y, ppi)
        return (left, top, left + px_from_sp(rect.width, ppi), top + px_from_sp(rect.height, ppi))

    def next_origin(self) -> tuple[float, float]:
        """
        Where `draw` would put the document's top-left if it were called now, in screen pixels.

        ImGui's cursor, snapped as `draw` snaps it. For a host that submits
        widgets of its own over the text *before* the view -- a column handle
        that must be an item by the time the view judges a press -- and so
        needs the frame's geometry before `draw` has produced it: this for
        the origin, `layout_for(width)` for the layout. `origin` is the
        same point as of the *last* draw. Needs a live ImGui frame, inside
        the window the view is about to be drawn in.
        """
        origin = self._cursor_origin()
        return (float(origin.x), float(origin.y))

    @property
    def viewport(self) -> Viewport | None:
        """
        The band of the document the last `draw` showed, in document scaled points, or `None`.

        `viewport.top` is how far the pane was scrolled past the document's
        top (negative when the document starts below the window's top edge).
        What a host reads to keep a second view at the same place, with
        `scroll_to` on the other one.
        """
        return self._viewport

    def scroll_to(
        self,
        rect: Rect,
        *,
        margin_px: float = 24.0,
        align: float | None = None,
        always: bool = False,
    ) -> None:
        """
        Ask for a document-space rectangle to be brought into view by the next `draw`.

        `rect` is `block_rect`'s or one of `span_rects`'. **Callable from
        anywhere** -- outside the child window, before the frame's layout --
        because nothing is done here: the request is kept, and the next
        `draw` carries it out against the layout and the window it is drawn
        in, which is the only place the scrolling can be asked of ImGui. One
        request is held, the latest; it is carried out once and dropped, so
        the reader can scroll away afterwards. The scroll is the enclosing
        window's and ImGui applies it at the start of the frame after, so the
        rectangle is in view one frame after the draw that carried it out.

        The rule is `scroll_for`'s. By default the pane moves only if the
        rectangle is not already in view with `margin_px` to spare, and then
        by as little as shows it. `align` is a fraction of the window's
        height at which to put the rectangle's top instead (0.0 the top edge,
        1/3 for a find hit with context above it). `always=True` with an
        `align` moves even what is in view, which is what following another
        view's `viewport` wants: `scroll_to(Rect(0, top, 0, 0), align=0.0,
        always=True, margin_px=0.0)`.

        A `StreamView` that is following its tail stops following when it is
        sent somewhere, as it does when the reader scrolls up.
        """
        self._scroll = (rect, float(margin_px), align, always)

    @property
    def scrolled(self) -> bool:
        """
        Whether the last `draw` moved the pane for a `scroll_to`.

        False when there was no request and when the rectangle was already
        in view: a host counting how often it sent the reader somewhere
        reads this after `draw`.
        """
        return self._scrolled

    def _carry_out_scroll(self, origin: imgui.ImVec2) -> bool:
        """
        Make of ImGui the scroll a `scroll_to` asked for, if one is waiting. True if it moved.
        """
        request = self._scroll
        if request is None:
            return False
        self._scroll = None
        from imgui_bundle import imgui

        rect, margin, align, always = request
        scroll = float(imgui.get_scroll_y())
        # The rectangle in the window's scrolled content: its place on screen
        # relative to the window, plus what is scrolled off above.
        top = origin.y - imgui.get_window_pos().y + scroll + px_from_sp(rect.y, self.px_per_inch)
        target = scroll_for(
            top,
            top + px_from_sp(rect.height, self.px_per_inch),
            scroll,
            float(imgui.get_window_size().y),
            margin=margin,
            align=align,
            always=always,
        )
        if target is None:
            return False
        # ImGui clamps to the range the content turns out to have.
        imgui.set_scroll_y(target)
        return True

    def set_lines(self, first_block: int = 0, stop_block: int | None = None) -> tuple[SetLine, ...]:
        """
        Where each line of text is in the current layout, for blocks `[first_block, stop_block)`.

        Every line that holds at least one glyph, in reading order -- top to
        bottom, and a table's cells row by row -- as a `SetLine`: its block,
        its baseline and its glyphs' codepoints and left edges, in document
        scaled points. They are the lines a click lands on (the selection
        index's fragments, less the ones with no glyph), and
        `tests/test_bare_view.py` holds the two equal. Empty before the first
        layout and after `invalidate` until the next: this describes
        `layout`, and says nothing when there is none.

        `first_block` and `stop_block` index `document.blocks`; the default
        is every block. **The cost is the blocks asked for, not the
        document**: the units before `first_block` are stepped over by
        bisection, each unit asked for is read once from the commands it
        shipped, and nothing is indexed for selection or moved into place to
        answer. That is what this is for -- a caller that watches whether
        set lines move as a document changes (`examples/stream_replay.py`)
        can ask for the blocks that could have changed and not walk the
        rest. In a `StreamView` those are the blocks from
        `len(stream.committed)` *as it was at the previous layout* onward:
        a block that had committed by then keeps its unit for good, and
        under either commit policy nothing above it can change height, so
        its lines are where they were for as long as the width is
        (`layout.width`). A change of width moves everything and is the
        caller's to tell apart.

        A code block laid out in pieces is one block here, as everywhere
        else that names a block.
        """
        layout = self._layout
        if layout is None:
            return ()
        placed = layout.placed
        # Units are in block order, and a unit's blocks end where the next
        # one's begin, so the first unit that reaches `first_block` is found
        # by its last block.
        low = bisect_left(placed, first_block, key=_last_block)
        lines: list[SetLine] = []
        for unit in placed[low:]:
            if stop_block is not None and unit.block_start >= stop_block:
                break
            _lines_of_unit(unit, first_block, stop_block, lines)
        return tuple(lines)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(
        self,
        *,
        fonts: FaceFont,
        palette: Palette | None = None,
        width_px: float | None = None,
    ) -> DrawStats:
        """
        Draw the document at the cursor, as wide as the pane, and handle selection.

        Call inside any window; a scrolling child is the usual one, and its
        own scrollbar does the scrolling. `width_px` overrides the content
        region's width for a host that wants the measure held steady.

        The item this leaves as ImGui's "last item" is the view's whole
        rectangle, so `imgui.is_item_hovered()` straight after the call is
        "the mouse is over the document". The module docstring has the rest
        of the mouse contract and it is worth reading before wiring a menu.
        """
        from imgui_bundle import imgui

        self._begin_frame()
        if width_px is None:
            width_px = imgui.get_content_region_avail().x
        width_px = max(width_px, MIN_WIDTH_PX)
        anchor: tuple[int, Scaled] | None = None
        if self._hosts and self._hosts_resized():
            anchor = self._top_anchor()
            self.invalidate()
        layout = self.layout_for(sp_from_px(width_px, self.px_per_inch))

        origin = self._cursor_origin()
        self._scrolled = self._carry_out_scroll(origin)
        if anchor is not None and not self._scrolled:
            origin = self._held_in_place(anchor, layout, origin)
        size = imgui.ImVec2(width_px, px_from_sp(layout.height, self.px_per_inch))
        colours = palette or Palette()
        stats = self._paint(layout, origin, fonts=fonts, colours=colours)
        # Before the mouse is looked at: a hosted widget's own items have to
        # exist by then, so that they count as "an item of the host's in
        # front" and keep their clicks.
        stats = self._draw_hosts(layout, origin, stats, fonts=fonts, colours=colours)

        # Links are judged before selection, because a press on a live link is
        # the link's and must not also begin a drag.
        self._hot = self._link_under_mouse(origin, size)
        if self._hot is not None and imgui.is_mouse_clicked(imgui.MouseButton_.left):
            self._link_down = (self._hot.block, self._hot.number)

        # An item only for the length of a drag or a held link; see "Where the
        # mouse goes". Both branches advance the cursor by the same size, so
        # the layout of whatever follows does not depend on which is taken.
        self._press = self._hot is None and self._press_begins(origin, size)
        # A button of no height is an assertion in ImGui, and a document can
        # become empty under a drag. Then there is nothing to hold on to.
        self._end_a_drag_that_missed_its_release()
        held = self._press or self._dragging or self._link_down is not None
        if held and size.y > 0.0:
            imgui.invisible_button(self._button_id(), size)
        else:
            imgui.dummy(size)
        self._handle_mouse(layout, origin)
        self._handle_copy(layout)
        self._handle_link()
        return stats

    def _top_anchor(self) -> tuple[int, Scaled] | None:
        """
        The block at the top of the window and where the layout about to be
        replaced puts it, or `None` when the document's top is in the window.
        """
        from imgui_bundle import imgui

        old = self._layout if self._layout is not None else self._previous
        if old is None or not old.placed or getattr(self, "_following", False):
            return None
        above = imgui.get_window_pos().y - self._cursor_origin().y
        if above <= 0.0:
            return None
        placed = old.placed
        position = bisect_right(placed, sp_from_px(above, self.px_per_inch), key=_bottom)
        if position >= len(placed):
            return None
        return placed[position].block_start, placed[position].y

    def _held_in_place(
        self, anchor: tuple[int, Scaled], layout: UnitLayout, origin: imgui.ImVec2
    ) -> imgui.ImVec2:
        """
        The origin to draw from so that what was at the top of the window
        still is, after a hosted widget changed height.

        A widget *above* the window that grows moves everything under it
        down the document, and the reader's text with it: measured, a widget
        going from 80 to 230 px moved the paragraph being read by 150 px on
        screen (review 2 asked; nobody had looked). The block at the top of
        the window is found again in the new layout, the window is scrolled
        by how far it moved, and -- because ImGui applies a scroll on the
        next frame -- this frame is drawn from where that scroll will put it.
        Whole pixels. A widget in or below the window moves nothing above
        the block at the top, so nothing is done for it; a stream view that
        is following its tail keeps following instead.
        """
        from imgui_bundle import imgui

        block, was = anchor
        placed = layout.placed
        position = bisect_left(placed, block, key=lambda unit: unit.block_start)
        if position >= len(placed) or placed[position].block_start != block:
            return origin
        moved = math.floor(px_from_sp(placed[position].y - was, self.px_per_inch) + 0.5)
        if not moved:
            return origin
        imgui.set_scroll_y(max(0.0, imgui.get_scroll_y() + moved))
        return imgui.ImVec2(origin.x, origin.y - moved)

    def _draw_hosts(
        self,
        layout: UnitLayout,
        origin: imgui.ImVec2,
        stats: DrawStats,
        *,
        fonts: FaceFont,
        colours: Palette,
    ) -> DrawStats:
        """
        Draw each hosted widget whose rectangle meets the window, in its rectangle.

        The widget is given ImGui's cursor at its top-left and its width, and
        draws as it would anywhere; the cursor is then put back, so the item
        this view claims afterwards -- and whatever the host lays out next --
        is where it would have been with nothing hosted. What each widget
        reports having drawn is added to `stats` when it is a `DrawStats`.

        A widget a selection runs across is washed in the selection colour
        first: it will be copied (`UnitModel.separators_within`), and nothing
        else on screen would say so. "Across" here is by index -- the
        selection begins before the widget and ends after it -- where a copy
        asks for a *character* either side; they differ only for a selection
        that begins on the fill at the end of the paragraph above, which
        washes the widget and copies none of it.
        """
        from imgui_bundle import imgui

        rects: list[tuple[float, float, float, float]] = []
        if self._hosts:
            cursor = imgui.get_cursor_screen_pos()
            window_top = imgui.get_window_pos().y
            window_bottom = window_top + imgui.get_window_size().y
            placed = layout.placed
            ppi = self.px_per_inch
            glyphs, missing, rules = stats.glyphs, stats.missing, stats.rules
            # The widgets at an edge of the document, washed when everything
            # is selected: the same test a copy makes.
            edges: frozenset[int] = frozenset()
            if self._everything(layout):
                leading, trailing = layout.model.edge_hosts()
                edges = frozenset(leading + trailing)
            for number, host in self._hosts.items():
                position = bisect_left(placed, number, key=lambda unit: unit.block_start)
                if position >= len(placed):
                    continue
                unit = placed[position]
                if unit.block_start != number or unit.blocks[0] is not host.stand_in:
                    continue
                top = origin.y + px_from_sp(unit.y, ppi)
                bottom = origin.y + px_from_sp(unit.bottom, ppi)
                if bottom <= top or bottom <= window_top or top >= window_bottom:
                    # Not drawn -- but it may own the selection, and a widget
                    # that reads its keys while drawing would then be deaf to
                    # Ctrl+C the moment it scrolled out of the window.
                    unseen = getattr(host.hosted, "handle_keys", None)
                    if unseen is not None:
                        unseen()
                    continue
                left = origin.x + px_from_sp(host.indent, ppi)
                right = left + host.width_px
                if self._selection.start < unit.base < self._selection.end or position in edges:
                    imgui.get_window_draw_list().add_rect_filled(
                        imgui.ImVec2(math.floor(left + 0.5), math.floor(top + 0.5)),
                        imgui.ImVec2(math.floor(right + 0.5), math.floor(bottom + 0.5)),
                        colours.highlight,
                    )
                imgui.set_cursor_screen_pos(imgui.ImVec2(left, top))
                # A widget that opens a child window of its own (a diff with
                # a height cap) would otherwise paint the style's child
                # background over the wash, and over whatever the host put
                # behind the document: this view paints no background, and
                # what it hosts is on the same footing.
                imgui.push_style_color(imgui.Col_.child_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.0))
                try:
                    drawn = host.hosted.draw(fonts=fonts, palette=colours, width_px=host.width_px)
                finally:
                    imgui.pop_style_color()
                if isinstance(drawn, DrawStats):
                    glyphs += drawn.glyphs
                    missing += drawn.missing
                    rules += drawn.rules
                rects.append((left, top, right, bottom))
            imgui.set_cursor_screen_pos(cursor)
            stats = DrawStats(glyphs=glyphs, missing=missing, rules=rules)
        self._host_rects = tuple(rects)
        return stats

    def _over_host(self) -> bool:
        """
        Whether the mouse is inside a hosted widget's rectangle, as drawn this frame.
        """
        from imgui_bundle import imgui

        if not self._host_rects:
            return False
        mouse = imgui.get_mouse_pos()
        return any(
            left <= mouse.x < right and top <= mouse.y < bottom
            for left, top, right, bottom in self._host_rects
        )

    def _begin_frame(self) -> None:
        """
        End a drag or a held link that this view did not see through the previous frame.

        Called first thing in `draw`, before the layout, by both views.

        **A gesture goes on only from one drawn frame to the very next.** A
        view that was not drawn for a frame -- its tab away, its pane
        collapsed -- cannot know what the button did meanwhile. It may have
        come up and gone down again somewhere else entirely, and the view
        then returns to find the button down exactly as it left it: it used
        to resume the old drag from the old anchor and select to wherever
        the mouse now was, and to take the eventual release for a click on
        the link it had been holding. Measured with review 4's third
        snippet. `_end_a_drag_that_missed_its_release` cannot see this case,
        because the button *is* down. So the frame count is compared, and a
        gap ends both; the selection is left as the view last saw it.

        Before the layout, so that a drag that is over is known to be over
        when the layout carries the selection.
        """
        from imgui_bundle import imgui

        frame = int(imgui.get_frame_count())
        if frame - self._drawn_frame > 1:
            self._dragging = False
            self._link_down = None
        self._drawn_frame = frame

    def _cursor_origin(self) -> imgui.ImVec2:
        """
        ImGui's cursor, as a whole number of pixels: where this view starts on screen.

        **The view's origin is snapped here, and only here.** Each line's top
        is rounded to a pixel on its own (`advtext.backends.imgui_draw`), and
        the body leading is 21.6 px, so consecutive lines are 21 or 22 px
        apart in a pattern fixed by the fraction of the origin. A whole
        origin moved by whole pixels keeps the pattern; a fractional one
        re-rounds every line, and measured on one paragraph of 55 lines,
        origins a quarter, a half and three quarters of a pixel off changed
        21, 43 and 44 of the 54 gaps. That is settled text shimmering.

        ImGui's own windows and scroll positions are whole in 1.92 (a window
        placed at (10.5, 20.25) and a scroll set to 123.4 both hand the view
        a whole cursor; `tests/test_stream_view.py` keeps that measurement).
        A *host* is not bound by that: `set_cursor_pos` with a fractional
        value reaches the view as given. So the view does not rely on it.

        Rounded half up, both axes. The item the view claims afterwards still
        starts at ImGui's own cursor, so what the host lays out next is where
        it would have been; the text is at most half a pixel from it.
        """
        from imgui_bundle import imgui

        cursor = imgui.get_cursor_screen_pos()
        return imgui.ImVec2(math.floor(cursor.x + 0.5), math.floor(cursor.y + 0.5))

    def _paint(
        self,
        layout: UnitLayout,
        origin: imgui.ImVec2,
        *,
        fonts: FaceFont,
        colours: Palette,
    ) -> DrawStats:
        """
        Issue the visible commands and the selection highlight, anchored at `origin`.

        `origin` is where the document's (0, 0) sits on screen. Hit testing,
        culling and the draw all take this one point, so an inset cannot be
        applied to some of them and not the others -- which is the failure
        mode of offsetting the draw call alone, where the text moves and the
        mouse does not. It is recorded for `document_point` for the same
        reason.

        **Only the visible commands are issued.** `advtext.ui.units.UnitLayout`
        moves into place and hands over the units the window can see; the
        selection model is not culled, so a selection running past the bottom
        of the window still copies in full.

        **Each unit is drawn in its block's ink** (`_inked`). With a palette
        that names no roles that is one run in `colours.ink`, which is the
        call this made before roles existed.
        """
        from imgui_bundle import imgui

        self._origin = (float(origin.x), float(origin.y))
        viewport = self.viewport_in(origin.y, imgui.get_window_pos().y, imgui.get_window_size().y)
        self._viewport = viewport
        visible = list(layout.visible_units(viewport))
        inks, fills = self._decorate(visible, colours)
        inks = _overlaid(_role_inks(visible, colours), inks)
        return draw_runs(
            imgui.get_window_draw_list(),
            _inked(visible, colours),
            origin,
            fonts=fonts,
            palette=colours,
            highlights=layout.visible_rects(self._selection, viewport),
            px_per_inch=self.px_per_inch,
            debug=self.debug,
            inks=inks,
            fills=fills,
        )

    def _decorate(
        self, visible: list[tuple[PlacedUnit, tuple[DrawCmd, ...]]], colours: Palette
    ) -> tuple[list[tuple[int, int, int]], list[tuple[Rect, int]]]:
        """
        The ink ranges and fills for the units on screen, and their links in `_links`.

        Only a unit that has something to decorate is looked at twice: a block
        with links, or one the host gave colour spans. For those the decoration
        is built once and kept for as long as the unit stays on screen where
        it is, with the same spans and the same link ink; what is not used on
        a frame is dropped on that frame, so the cache is never larger than
        one screen of units.

        Units arrive top to bottom and their indices ascend, so concatenating
        their ink ranges keeps them sorted, which is what `draw_runs` asks for.
        """
        styled = self.on_link is not None if self.style_links is None else self.style_links
        link_ink = colours.link if styled else None
        thickness = self.theme.table_rule_thickness
        underline = (2 * thickness, thickness)

        kept: dict[tuple[int, int, Scaled], tuple[object, object, Decoration]] = {}
        inks: list[tuple[int, int, int]] = []
        fills: list[tuple[Rect, int]] = []
        links: list[LinkArea] = []
        pieced = self._pieced
        self._pieced = {}
        for unit, _ in visible:
            spans = tuple(self._spans_for(unit, number, pieced) for number in unit.block_range)
            if not any(spans) and not any(_has_links(block) for block in unit.blocks):
                continue
            key = (id(unit.unit.cmds), unit.base, unit.y)
            token = (spans, link_ink, underline)
            found = self._decorated.get(key)
            if found is not None and found[0] is unit.unit.cmds and found[1] == token:
                decoration = found[2]
            else:
                decoration = self._decorate_unit(unit, spans, link_ink, underline)
            kept[key] = (unit.unit.cmds, token, decoration)
            inks.extend(decoration.inks)
            fills.extend(decoration.marks)
            fills.extend(decoration.underlines)
            links.extend(decoration.links)
        self._decorated = kept
        self._links = tuple(links)
        return inks, fills

    def _spans_for(
        self,
        unit: PlacedUnit,
        number: int,
        before: dict[
            tuple[int, int], tuple[tuple[ColourSpan, ...], tuple[int, int], tuple[ColourSpan, ...]]
        ],
    ) -> tuple[ColourSpan, ...]:
        """
        The host's colour spans for block `number`, in the coordinates of the unit that sets it.

        The host's own tuple, for a unit that is its whole block. A piece of a
        code block is mapped on its own, from zero (`map_code_block` is given
        the piece), while the host's spans count from the start of the block:
        each span is cut to the piece's range of the block's material and
        moved down by what comes before it (`PlacedUnit.skipped`). A span
        across two pieces becomes one in each, which draws the same glyphs in
        the same ink.

        Kept per piece for as long as the host's tuple is the same object and
        the piece covers the same range, so a frame on which nothing changed
        hands `_decorate` the tuple it was handed last time and its own cache
        still matches. Cutting is a pass over every span of the block, paid
        once per piece that comes on screen and once per change to the live one.
        """
        spans = self._colours.get(number, ())
        part = unit.part
        if part is None or not spans:
            return spans
        block = unit.blocks[0]
        if not isinstance(block, CodeBlock):
            # A piece of a table. Spans set on a table are kept and not
            # applied (`set_colours`), in pieces as whole.
            return spans
        low = unit.skipped
        high = low + sum(map(len, block.lines))
        found = before.get((number, part))
        if found is not None and found[0] is spans and found[1] == (low, high):
            cut = found[2]
        else:
            cut = tuple(
                ColourSpan(
                    max(span.start, low) - low, min(span.end, high) - low, span.ink, span.mark
                )
                for span in spans
                if span.start < high and span.end > low
            )
        self._pieced[(number, part)] = (spans, (low, high), cut)
        return cut

    def _decorate_unit(
        self,
        unit: PlacedUnit,
        spans: tuple[tuple[ColourSpan, ...], ...],
        link_ink: int | None,
        underline: tuple[Scaled, Scaled],
    ) -> Decoration:
        """
        One unit's decoration, in document coordinates: each of its blocks mapped and decorated.

        A text block alone in its unit is mapped against the unit's commands
        as they are. A paragraph of a block quote shares its unit's commands
        with its neighbours and is mapped against its own index range
        (`PlacedUnit.indices_of`). A code block needs no commands at all. A
        table is mapped cell by cell from the unit's box, for its links; a
        rule has nothing to decorate.
        """
        parts: list[Decoration] = []
        for number, block, colours in zip(unit.block_range, unit.blocks, spans, strict=True):
            # Each entry: a map, the links of the material it maps, the colour
            # spans for it, and the number its first link takes.
            pieces: list[tuple[SpanMap, tuple[LinkSpan, ...], tuple[ColourSpan, ...], int]] = []
            try:
                match block:
                    case TextBlock():
                        if not colours and not block.links:
                            continue
                        if len(unit.blocks) == 1:
                            mapped = map_text_block(block, unit.cmds)
                        else:
                            own = unit.indices_of(number)
                            mapped = map_text_block(
                                block, unit.cmds, start=own.start, stop=own.stop
                            )
                        pieces.append((mapped, block.links, colours, 0))
                    case CodeBlock():
                        if not colours:
                            continue
                        mapped = map_code_block(block, base=unit.indices_of(number).start)
                        pieces.append((mapped, (), colours, 0))
                    case TableBlock():
                        # A table's links are its cells'. Colour spans have no
                        # coordinates across cells and are not applied. A link
                        # is numbered among the links of its *block*, so a
                        # piece of a table starts counting where the pieces
                        # before it stopped (`PlacedUnit.skipped`): two links
                        # in two pieces must not be taken for one.
                        seen = unit.skipped if unit.part is not None else 0
                        start = unit.indices_of(number).start
                        for cell, mapped in map_table(block, unit.unit.box, base=start):
                            if cell.links:
                                pieces.append((mapped, cell.links, (), seen))
                                seen += len(cell.links)
                    case _:
                        continue
            except SpanMapError:
                self._unmapped += 1
                continue
            for mapped, links, coloured, first in pieces:
                parts.append(
                    decorate(
                        mapped,
                        unit.model,
                        links=links,
                        number=number,
                        first_link=first,
                        colours=coloured,
                        link_ink=link_ink,
                        underline=underline,
                    )
                )
        if not parts:
            return Decoration()
        if len(parts) == 1:
            return parts[0]
        return Decoration(
            inks=tuple(chain.from_iterable(part.inks for part in parts)),
            marks=tuple(chain.from_iterable(part.marks for part in parts)),
            underlines=tuple(chain.from_iterable(part.underlines for part in parts)),
            links=tuple(chain.from_iterable(part.links for part in parts)),
        )

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

    def _press_begins(self, origin: imgui.ImVec2, size: imgui.ImVec2) -> bool:
        """
        Whether a left press this frame should begin a selection on this view.

        Judged before the view has submitted any item, from the conditions the
        module docstring lists: the button went down this frame, inside the
        view's rectangle as the window clips it, in the hovered window, with
        no item under the mouse. The last one is what gives a host's own
        widgets priority over the text beneath them.
        """
        from imgui_bundle import imgui

        if not imgui.is_mouse_clicked(imgui.MouseButton_.left):
            return False
        if not imgui.is_window_hovered() or self._item_in_front():
            return False
        # A press on a widget the host draws in this view's rectangle is the
        # widget's. It judges the press from geometry as this view does, and
        # without this both began a selection on one click.
        if self._over_host():
            return False
        return bool(
            imgui.is_mouse_hovering_rect(origin, imgui.ImVec2(origin.x + size.x, origin.y + size.y))
        )

    def _link_under_mouse(self, origin: imgui.ImVec2, size: imgui.ImVec2) -> LinkArea | None:
        """
        The live link the mouse is on, or `None`.

        The same conditions a selection press has to meet, for the same
        reasons -- the view's window is the hovered one and nothing of the
        host's is in front -- and then geometry against the links on screen.
        While a link is held down the view's own button is the active item,
        which ImGui counts as blocking the window's hover; that is this view
        blocking itself, so it is allowed through for exactly that case.
        """
        from imgui_bundle import imgui

        if self.on_link is None or not self._links:
            return None
        flags = (
            imgui.HoveredFlags_.allow_when_blocked_by_active_item.value
            if self._link_down is not None
            else 0
        )
        if not imgui.is_window_hovered(flags) or self._item_in_front():
            return None
        if not imgui.is_mouse_hovering_rect(
            origin, imgui.ImVec2(origin.x + size.x, origin.y + size.y)
        ):
            return None
        point = self._document_point(origin)
        for link in self._links:
            if link.contains(point.x, point.y):
                return link
        return None

    def _handle_link(self) -> None:
        """
        The hand cursor over a live link, and the callback when one is clicked.

        A click is a press and a release on the same link, identified by its
        block and its position among that block's links rather than by its
        target, because two links may point at one URL. Released anywhere
        else, the press is forgotten and nothing is called.
        """
        from imgui_bundle import imgui

        if self._hot is not None and self.hand_cursor:
            imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
        released = imgui.is_mouse_released(imgui.MouseButton_.left)
        if self._link_down is not None and not released:
            if not imgui.is_mouse_down(imgui.MouseButton_.left):
                # The release happened on a frame this view was not drawn.
                self._link_down = None
            return
        if self._link_down is not None and released:
            pressed, self._link_down = self._link_down, None
            if (
                self._hot is not None
                and (self._hot.block, self._hot.number) == pressed
                and self.on_link is not None
            ):
                self.on_link(self._hot.target)

    def _button_id(self) -> str:
        """
        The label of the button that exists while a drag does. One per view object.
        """
        return f"##advtext-bare-{id(self):x}"

    def _item_in_front(self) -> bool:
        """
        Whether some item other than this view's own drag button is under the mouse.

        `imgui.is_any_item_hovered` is true for the item hovered so far this
        frame *or on the previous one*. The second half is what lets an overlay
        the host submits after the view keep its click; it is also true of this
        view's own button on the frame after a drag ends, which would refuse
        the second press of a double click made within two frames. So the
        hovered ID itself is compared, through `imgui.internal`, which is the
        one use of ImGui's internal API in this module. Without it (a build
        that does not expose it) the answer falls back to the public call and
        the frame-perfect double click is the price.
        """
        from imgui_bundle import imgui

        hovered_id = getattr(getattr(imgui, "internal", None), "get_hovered_id", None)
        if hovered_id is None:
            return bool(imgui.is_any_item_hovered())
        hovered = hovered_id()
        return bool(hovered != 0 and hovered != imgui.get_id(self._button_id()))

    def _pressed(self) -> bool:
        """
        Whether a selection press began this frame. `draw` decided; this reports it.
        """
        return self._press

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

    def _handle_mouse(self, layout: UnitLayout, origin: imgui.ImVec2) -> None:
        """
        Press sets an anchor, drag extends, release finishes.

        **The anchor is text, not a place.** It is kept as the boundaries the
        press selected and carried across a relayout like any selection
        (`layout_for`, `_carried_anchor`). It was the document point of the
        press, and a point is other words once the lines under it re-break:
        a pane resized under a drag, or a stream's block set again at
        commit, moved the end of the selection that is supposed to be fixed.

        The drag branch deliberately does not test `is_item_hovered`: a drag that
        leaves the document should keep extending the selection, which is what
        `SelectionModel.fragment_at` snapping to the nearest line is for.

        Whether a press *begins* here is `_pressed`'s to say, and it is the one
        thing the two views disagree about: `DocumentView` owns an item over the
        whole sheet and asks ImGui whether that item was clicked; `BareView` owns
        no item until a press has begun and decides from geometry.
        """
        from imgui_bundle import imgui

        point = self._document_point(origin)

        # Another view began a selection since this one last did: that one is
        # current now, and this one's goes.
        if self._owned and not self.owns_selection:
            self._selection = Selection(0, 0)
            self._all_selected = False
            self._dragging = False
            self._owned = 0

        if self._pressed():
            self._own()
            # The scalar accessor, not `get_io().mouse_clicked_count[0]`. The
            # array-valued fields on `ImGuiIO` are nanobind ndarrays, and
            # exporting one needs numpy, which is not a dependency of this
            # project or of imgui-bundle. Indexing it raises `TypeError: could
            # not export nanobind::ndarray` on the first click rather than at
            # import, so nothing before the first frame can catch it.
            self._granularity = _granularity_for(
                imgui.get_mouse_clicked_count(imgui.MouseButton_.left)
            )
            # What the press itself selects is the anchor: a caret, a word or
            # a line, as boundaries. `select_at` between two points is the
            # union of what is under each, so extending from this is the same
            # selection the point gave -- for as long as the layout is the
            # same one, which is the case a point cannot survive.
            self._anchor = layout.model.select_at(point, point, self._granularity)
            self._dragging = True
            self._selection = self._anchor
            self._all_selected = False  # a press is a new selection, never "everything"
            return

        self._end_a_drag_that_missed_its_release()
        if self._dragging:
            under = layout.model.select_at(point, point, self._granularity)
            self._selection = Selection(
                min(self._anchor.start, under.start), max(self._anchor.end, under.end)
            )
            if not imgui.is_mouse_down(imgui.MouseButton_.left):
                self._dragging = False

    def _end_a_drag_that_missed_its_release(self) -> None:
        """
        Stop dragging if the button is up and did not come up on this frame.

        A drag ends on the frame the button is released, and a view learns
        that from `is_mouse_released` -- which is true for one frame. A view
        that was not drawn on that frame (its tab switched away, its pane
        hidden, the application's focus lost) never saw it, and used to go on
        extending the selection to wherever the mouse wandered, with no button
        held and its drag button still submitted, until the next press. The
        button being up *now* is the fact that matters. The selection is left
        as it was when the view last saw the drag: where the mouse has gone
        since is not part of it.
        """
        from imgui_bundle import imgui

        left = imgui.MouseButton_.left
        if self._dragging and not imgui.is_mouse_down(left) and not imgui.is_mouse_released(left):
            self._dragging = False

    def _handle_copy(self, layout: UnitLayout) -> None:
        """
        Ctrl+C puts the selection on the clipboard, if it is this view's to copy;
        Ctrl+A, on the same conditions, selects everything (`select_all`).

        Three conditions beyond the key, and each is a defect this had when it
        tested only the key and a non-empty selection:

        - **this view owns the current selection.** Two views drawn in one
          frame both saw the keypress and both wrote the clipboard, the second
          overwriting the first;
        - **ImGui has no text input active.** While it does, Ctrl+C belongs
          to that input, which copies its own selection;
        - **the text is the document's, not the layout's**: `_copied` goes
          through `UnitModel.copy_text`, so a fenced code block keeps its
          lines. It used to be `text()` with no separators, which joined them
          with spaces.

        `layout` is read only to tell a document with no text in it (whose
        whole selection is the empty range) from an empty selection.
        """
        from imgui_bundle import imgui

        if not self.owns_selection:
            return
        io = imgui.get_io()
        if io.want_text_input:
            return
        if io.key_ctrl and imgui.is_key_pressed(imgui.Key.a, False):
            # The select-all gesture: the one thing that takes the hosted
            # blocks at the document's edges (`_everything`).
            self._selection = Selection(0, layout.length)
            self._all_selected = True
            self._dragging = False
        if self._selection.is_empty and not (self._all_selected and layout.length == 0):
            return  # (a document with no text, all of it selected, is not "nothing")
        if io.key_ctrl and imgui.is_key_pressed(imgui.Key.c, False):
            imgui.set_clipboard_text(clipboard_text(self._copied()))


CLIPBOARD_NUL = "\u2400"
"""
What a NUL becomes on its way to the clipboard: U+2400, the picture of one.
"""


def clipboard_text(text: str) -> str:
    """
    `text` as it is handed to the clipboard: each NUL as `CLIPBOARD_NUL`.

    The clipboard is a C string, and a NUL ends one: a copy of
    `key = 'ab\\0cd'` and the line after it put `key = 'ab` on the clipboard
    and nothing else -- text that was never in the document, with no sign
    that anything was missing (review 3, item 9). So every text this module
    and `advtext.ui.diff_view` hand to `imgui.set_clipboard_text` goes
    through here, a host's own `copy(text)` and `copy_as` included.
    `selected_text()` is not changed: it returns the characters that are
    there, NUL and all, for a host that does something else with them.
    """
    return text.replace("\0", CLIPBOARD_NUL) if "\0" in text else text


def _carried_anchor(anchor: Selection, old: UnitLayout, new: UnitLayout) -> Selection | None:
    """
    The anchor of a drag, made against `old`, as the same text in `new`; `None` if it is gone.

    A word or a line (a double or triple click) is a selection and is carried
    as one, by `advtext.ui.units.carry_selection`. A caret selects nothing,
    and `carry_selection` hands an empty selection back unchanged, so a caret
    is carried by `advtext.ui.units.carry_caret`, which has the rules: by its
    place in a unit that was not re-shipped, whatever is beside it; else by a
    glyph beside it; else by the glyphs before it in a unit that was set
    again with the same characters.

    `None` means there is no text left to say where the caret was -- the
    block was replaced, or reads differently before the caret -- and the
    caller ends the drag: the rule for a relayout is the same text or
    nothing, and it holds for the fixed end of a drag as for a selection.

    **A press on fill used to be `None` always**, because only a glyph next
    to the caret could carry it: review 5 measured 198 of 500 press positions
    on unchanged blocks losing their drag at the next relayout, and in a
    stream that is the next token. `tests/test_bare_view.py` has that sweep.
    """
    if not anchor.is_empty:
        return carry_selection(anchor, old, new)
    at = carry_caret(anchor.start, old, new)
    return None if at is None else Selection(at, at)


def _bottom(unit: PlacedUnit) -> Scaled:
    return unit.bottom


def _last_block(unit: PlacedUnit) -> int:
    """
    The number of the last document block a unit sets: what `set_lines` bisects on.
    """
    return unit.block_start + len(unit.unit.blocks) - 1


def _lines_of_unit(
    unit: PlacedUnit, first_block: int, stop_block: int | None, out: list[SetLine]
) -> None:
    """
    Append to `out` the lines of one unit that hold a glyph and belong to a block in range.

    One forward pass over the unit's **own** commands -- the tuple it
    shipped, in its own coordinates -- so the unit is neither moved into
    place nor indexed for selection to answer; the unit's `y` is added to
    each baseline. The grouping is `advtext.selection`'s: ship-out emits a
    `Line` before what it covers and nests them where boxes nest, and a
    glyph belongs to the innermost line whose index range holds it. Lines
    come out in reading order, which is the order of their first index.

    Which block a line is of is read from `Unit.spans`: one block for almost
    every unit, the paragraph's own for a line inside a quote.
    """
    stack: list[tuple[Line, list[tuple[int, Scaled]]]] = []
    found: list[tuple[Line, list[tuple[int, Scaled]]]] = []
    for cmd in unit.unit.cmds:
        if isinstance(cmd, Line):
            while stack and cmd.start >= stack[-1][0].end:
                stack.pop()
            entry: tuple[Line, list[tuple[int, Scaled]]] = (cmd, [])
            stack.append(entry)
            found.append(entry)
        elif isinstance(cmd, Glyph):
            while stack and cmd.index >= stack[-1][0].end:
                stack.pop()
            if stack:
                stack[-1][1].append((cmd.codepoint, cmd.x))
    starts = [start for start, _ in unit.unit.spans]
    held = [(line, glyphs) for line, glyphs in found if glyphs]
    held.sort(key=lambda entry: entry[0].start)
    for line, glyphs in held:
        block = unit.block_start + max(0, bisect_right(starts, line.start) - 1)
        if block < first_block or (stop_block is not None and block >= stop_block):
            continue
        out.append(SetLine(block=block, baseline=unit.y + line.y, glyphs=tuple(glyphs)))


def _has_links(block: Block) -> bool:
    """
    Whether a block holds any link: its own, or for a table one of its cells'.
    """
    match block:
        case TextBlock():
            return bool(block.links)
        case TableBlock():
            return any(cell.links for row in (block.header, *block.rows) for cell in row)
        case _:
            return False


def _inked(
    visible: list[tuple[PlacedUnit, tuple[DrawCmd, ...]]], colours: Palette
) -> list[tuple[tuple[DrawCmd, ...], int]]:
    """
    The visible commands as `(commands, ink)` runs, one ink per run of like units.

    A palette with no role inks gives a single run of everything visible in
    `colours.ink` -- exactly what was drawn before a role could have an ink.
    Otherwise each visible unit's run is in the ink of its **first** block's
    kind, and neighbours that come out the same colour are joined so that the
    backend is not handed forty runs for a page of body text.

    A unit of several blocks -- a block quote -- is still one run, because its
    blocks share one command list and a rule down the side of all of them. The
    blocks after the first get their own ink through the index channel
    instead (`_role_inks`), so a heading inside a quote is drawn in the
    heading's ink and the paragraph under it in the quote's.
    """
    if not colours.roles:
        return [(tuple(chain.from_iterable(cmds for _, cmds in visible)), colours.ink)]
    grouped: list[tuple[list[tuple[DrawCmd, ...]], int]] = []
    for unit, cmds in visible:
        ink = colours.ink_for(block_kind(unit.blocks[0]))
        if grouped and grouped[-1][1] == ink:
            grouped[-1][0].append(cmds)
        else:
            grouped.append(([cmds], ink))
    # Joined once per run, not once per unit: adding tuples as they arrive
    # copies everything gathered so far each time.
    return [(tuple(chain.from_iterable(parts)), ink) for parts, ink in grouped]


def _role_inks(
    visible: list[tuple[PlacedUnit, tuple[DrawCmd, ...]]], colours: Palette
) -> list[tuple[int, int, int]]:
    """
    Ink ranges for the blocks of a multi-block unit whose role differs from the unit's first.

    One run has one ink (`_inked`), and a block quote is one run. Each later
    block of it that wants another ink gets `(start, end, ink)` over its own
    reading-order indices (`PlacedUnit.indices_of`). Empty unless the palette
    names roles and a unit of several blocks is on screen.
    """
    if not colours.roles:
        return []
    ranges: list[tuple[int, int, int]] = []
    for unit, _ in visible:
        if len(unit.blocks) < 2:
            continue
        base = colours.ink_for(block_kind(unit.blocks[0]))
        for number, block in zip(unit.block_range, unit.blocks, strict=True):
            ink = colours.ink_for(block_kind(block))
            own = unit.indices_of(number)
            if ink != base and own.start < own.stop:
                ranges.append((own.start, own.stop, ink))
    return ranges


def _overlaid(
    under: list[tuple[int, int, int]], over: list[tuple[int, int, int]]
) -> list[tuple[int, int, int]]:
    """
    Two sorted lists of ink ranges as one, `over` winning wherever they overlap.

    The backend wants ranges sorted and non-overlapping. A block's role ink
    (`under`) covers the whole block; a link or a host's span inside it
    (`over`) is finer and must show. So each `under` range is cut around the
    `over` ranges that fall in it.
    """
    if not under:
        return over
    if not over:
        return under
    merged: list[tuple[int, int, int]] = list(over)
    for start, end, ink in under:
        cursor = start
        for top_start, top_end, _ in over:
            if top_end <= cursor or top_start >= end:
                continue
            if top_start > cursor:
                merged.append((cursor, top_start, ink))
            cursor = max(cursor, top_end)
        if cursor < end:
            merged.append((cursor, end, ink))
    merged.sort()
    return merged


def scroll_for(
    top: float,
    bottom: float,
    scroll: float,
    height: float,
    *,
    margin: float = 24.0,
    align: float | None = None,
    always: bool = False,
) -> float | None:
    """
    The scroll offset that brings `[top, bottom)` into a window, or `None` to stay put.

    All in pixels of the scrolled content: where the span is, how far the
    window is scrolled, and how tall the window is. The arithmetic behind
    `BareView.scroll_to`, separate because it is arithmetic.

    `None` when the span is already inside the window with `margin` to spare
    above and below, so stepping through places that are on screen moves
    nothing. Otherwise, with no `align`, the nearer edge: a span above comes
    to the top and a span below to the bottom, each `margin` in; a span
    taller than the window shows its top. With `align`, the span's top is put
    that fraction of the window's height down. Never above the start;
    whoever applies it clamps to the end.

    `always` moves a span that is already in view, to where `align` says.
    Without an `align` it changes nothing: the nearest place from which a
    visible span is visible is here.
    """
    if top - margin >= scroll and bottom + margin <= scroll + height:
        if not always or align is None:
            return None
    if align is not None:
        return max(top - align * height, 0.0)
    if top - margin < scroll or bottom - top + 2.0 * margin > height:
        return max(top - margin, 0.0)
    return max(bottom + margin - height, 0.0)


def granularity_for(clicks: int) -> Granularity:
    """
    One click selects characters, two words, three the whole visual line.

    Given `imgui.get_mouse_clicked_count(...)`. Public so that a widget of a
    host's own selects by the same rule as the views here.

    ImGui reports the running click count rather than firing a separate
    triple-click event, so this is a lookup rather than three predicates. A count
    past three wraps back to a line, which is what an editor does.
    """
    if clicks >= 3:
        return Granularity.LINE
    if clicks == 2:
        return Granularity.WORD
    return Granularity.CHARACTER


_granularity_for = granularity_for
"""The name this had before it was public; `advtext.ui.document_view` re-exports it."""

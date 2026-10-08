r"""
The diff view: `advtext.diff`'s model, unified or side by side, in any pane.

`DiffView` is to a `Diff` what `advtext.ui.bare_view.BareView` is to a
`Document`: it draws at the cursor in whatever window the host has open, paints
no background, claims its height, and leaves the host's hover and context menus
alone. It shares `BareView`'s input model -- and its selection ownership, the
*same* counter -- but not its layout, and the difference is deliberate.

## Why this does not lay out through `advtext.ui.units`

Measured before this was written (`.concerns/lead--demo-review0-findings.md`,
S4): a 5,000-line diff as code pieces costs over a second before anything is
drawn, and nothing in that path culls by x. A diff is also not typeset: it is
monospace, never justified, never wrapped, and every line is one row. So the
view is a **grid**. A row is `row` whole pixels tall and a character is `cell`
whole pixels wide (`DiffMetrics`), display row `n` is at `n * row`, column `c`
at `c * cell`, and what is on screen is found by division. The only thing built
per frame is `advtext.shipout.Glyph` commands for the rows and the columns the
window shows, handed to `advtext.backends.imgui_draw.draw_runs` like any other
text. `frame_plan` is that step with no ImGui in it.

**The cell is a whole number of pixels, and that is the backend's rule, not a
new one.** `draw_runs` places each glyph of a rigid span by a gap rounded to a
pixel, so a face whose advance is 6.5 px is already drawn on a 7 px pitch.
The view rounds the *measured* advance of the code face the same way and
places every glyph on that pitch itself, so the column arithmetic used for hit
testing, highlights and culling is the arithmetic the glyphs were drawn with.
(Inconsolata's advance is a whole number of pixels only at even pixel sizes --
A4-draw measured it -- so at odd sizes the letters sit half a pixel looser than
the font says. That is a statement of where they are, not of how it looks.)
One character is one cell: a wide CJK glyph or a combining mark is not given
two cells or none. Tabs are expanded to `advtext.markdown.TAB_WIDTH` columns
from the start of the line, as a fenced code block's are.

## Characters that are not what they look like

A diff is read by somebody deciding whether to approve it, so the view never
issues a character that draws as nothing or as something else:

- A **control character** (C0, DEL, C1) and an **invisible or bidirectional
  one** (`advtext.diff.has_invisible`: Unicode's format characters -- the
  zero-width space and joiners, the byte-order mark, the right-to-left
  override and its relatives -- and the two line separators) is one cell
  holding `CONTROL_PLACEHOLDER` in the warning ink, and the file's header
  says which kind the file contains. This goes for every text the view
  draws from a diff: rows, lines shown as written, a file's label, a hunk's
  section.
- A **character the code face has no glyph for** is drawn from the first of
  the theme's prose face and the math face that has it (the chain
  `advtext.markdown` uses for a code block), at the code face's size, **in
  its own cell**; one that no face has is a placeholder too. (They were
  issued in the code face, and drew as blank cells: `π`, CJK.) The host's
  `fonts` must be able to give those faces; a face it cannot give is
  counted in `DrawStats.missing`, as anywhere.
- Columns do not move for any of this: one character is one cell in
  `_columns`, which is where widths, glyph cells, marks, highlights and hit
  testing all come from. A borrowed glyph wider than a cell overlaps its
  neighbour. A copy returns the characters that are there.

Not covered: a file in which characters no face has are *not* flagged in the
header (the model does not know the fonts); combining marks are a cell each.

## What is drawn

Display rows, top to bottom, per file: a **file header** (label, `+n -m`, the
state -- new file, deleted file, binary, no changes, renamed, mode changed,
line endings only -- and, in the palette's warning ink, the host's
*will not apply* label, "contains control characters" or "contains invisible
or bidirectional control characters", and how many lines under a hunk were not
read as part of the diff -- `FileDiff.unread`); then for each hunk a
**collapsed-context row** when the model knows lines were left out before it,
a **hunk header**, and the hunk's rows; then a last collapsed-context row.

- **Unified**: one row per `DiffRow`. The gutter holds the old number, the new
  number and the marker.
- **Side by side**: one row per `Hunk.side_by_side` pair; old on the left, new
  on the right, each with its own number and marker; a blank cell where one
  side has no line.

The gutter does not scroll horizontally; the code does, under a clip, by one
offset shared by both sides (`scroll_x`). **The `+` or `-` is always drawn**,
in the gutter's ink, whatever the colours are: it is the channel that does not
depend on hue. Added and removed rows have a band behind them
(`DiffPalette.add_fill`, `remove_fill`), the part of a line that changed has a
stronger mark over that (`Hunk.spans`), and the hunk `next_hunk` /
`previous_hunk` is on has a bar down its left edge.

Three things the model flags are drawn differently (review 1):

- **A control character** (NUL, escape, a lone carriage return, ...) is one
  cell holding `CONTROL_PLACEHOLDER` in the warning ink, and the file's header
  says the file contains them. The row is never hidden and a copy returns the
  real character.
- **A line whose ending is the change** (`Hunk.eol_rows`) ends in a mark for
  the terminator it has -- `\r\n`, `\n` -- in the meta ink, one cell clear of
  the text. A file whose two texts differ *only* in line endings
  (`FileDiff.line_endings`) says so in its header and is folded to one row;
  a click on it, or `show_line_endings(file)`, shows the rows.
- **A file that is not read as rows** (`FileDiff.dialect`: a combined diff, a
  text that is no diff) is its lines as written, under a header saying so:
  the full width, scrolled with the code, no gutter, no bands, no counts. Its
  lines cannot be selected -- a selection is positions in hunks -- which is a
  limit of this view and is not a decision about what should be copyable.

Every colour comes from `Palette.diff` (and `Palette.highlight` for the
selection), except the horizontal scrollbar, which is drawn in ImGui's own
scrollbar colours because it is standing in for ImGui's own scrollbar.

## Scrolling

Vertical scrolling is the window's. With `height_cap` unset the view claims
its whole height at the cursor and culls to the window, exactly as `BareView`
does. With `height_cap` set it opens a child window no taller than the cap and
scrolls inside that; `height_for(width)` is what it will occupy either way.

Horizontal scrolling is the view's own: Shift+wheel or a horizontal wheel over
the view, dragging a selection past either edge of the code, the `scroll_x`
property, and a scrollbar the view draws along the bottom of what is visible
of it. The scrollbar is an ImGui item (it is a scrollbar); nothing else is.

`set_layout` switches layout and keeps the row that was at the top of the
window at the top. `scroll_to_row`, `next_hunk` and `previous_hunk` scroll the
window on the next `draw`. `top_row` is the display row at the top of the
window, readable and assignable, which with `row_info` / `row_of` is what a
host needs to keep two views of one diff on the same line.

## Selection and copy

The `BareView` contract, restated because it is the contract with a host:
while nothing is being dragged the view submits **no item** over the text
(a `dummy`), so the host's `is_any_item_hovered` is false there and its
context menus open; a left press on the view, in the hovered window, with no
item of the host's under the mouse, begins a selection and from then until
release there is an `invisible_button`, which is what stops the press from
dragging the host's window. A view not drawn for a frame has stopped dragging.
One selection is current across every view in the process -- this view and
every `BareView` take turns on one counter -- and only its owner answers
Ctrl+C, and never while ImGui has a text input active.

Double click selects a word (`advtext.diff.tokenize`'s tokens), triple click a
line, and a drag extends by whichever began it. Ctrl+A, while this view owns
the selection, selects everything (on the side last clicked, in side by side).

**What a copy returns is code: no markers, no numbers, no headers, no filler.**
It is cut from the model's text, never from glyphs, so tabs come back as tabs
and a control character as itself (`selected_text`) -- except that on its way
to the *clipboard* a NUL becomes U+2400, because a NUL ends the clipboard's
string and everything after it was lost (`copy`). Lines are joined with `"\n"`, whatever
their own endings were. Pieces that are not next to each other in the file
are never joined as if they were: a line holding only `COPY_GAP` (an ellipsis)
stands between them, and the next file's label after it between files
(`selected_text`). Ctrl+C with nothing to copy leaves the clipboard as it was.

Ctrl+A and Ctrl+C go on answering after the user has clicked some unrelated
widget of the host's: ownership passes between views that select, and a
button is not one. That is `BareView`'s contract too, and is left as it is.

- **Side by side selects one side at a time.** A selection begun on the left
  is of the old text -- context and removed lines; on the right, the new text
  -- context and added lines. A blank filler cell is not a line and copies as
  nothing.
- **Unified: removed lines are left out whenever the selection also takes in
  a context or an added line.** So what is copied is always text that exists
  on one side: the new side if the selection touches it at all, and the
  removed lines only when they are all that was selected. Set
  `copy_removed_lines=True` to get every selected line in display order
  instead. Either way **the highlight covers exactly the lines a copy would
  return**, so a removed line in a mixed selection is visibly not selected.
- Selecting changes nothing about the model, and a selection survives a model
  that grew (a stream) or was expanded as long as the rows at its two ends
  are still where they were; otherwise it is cleared. Switching layout clears
  it: "one side" and "every line" are different selections.

## Collapsed context

A collapsed-context row says how many lines were left out. When the model can
reveal them (`FileDiff.expandable`), the row says so, shows the hand cursor,
and a click reveals `expand_step` lines: at the top of the gap, or at the
bottom with Shift held (the gap before a file's first hunk and the one after
its last have only one end). `expand` is the same thing for a host's own
control. The view then shows its own, expanded, `Diff` (`diff`), and keeps
showing it until the host gives it a *different object* with `set_diff`.

## Syntax colour

`syntax` is a host's callable, `(lines, language) -> spans per line`, where
each span is `(start, end, colour)` in character offsets of that line. The
library ships no tokeniser. `lines` are consecutive lines of **one side** of
one hunk -- old or new, so a string that opens on one line and closes on the
next is seen whole -- in chunks of at most `SYNTAX_CHUNK` lines, asked for
when a row of the chunk first comes on screen and kept while its rows are the
same objects. A context row takes the new side's colours (the old side's in
the left pane). `language` is `language_for(file.label)`: the extension, with
a few common ones spelled out. A callable that raises is counted
(`syntax_errors`) and the chunk is drawn uncoloured.

## A model that grows

`set_diff(stream.diff)` each time a `UnifiedDiffStream` has a new snapshot.
The view's own work for a grown model is the new rows only: widths are
measured once per row object (`measured_rows` counts them), settled hunks are
recognised by identity, and syntax chunks whose rows have not changed are not
asked for again. The last rows of a stream can still change -- the line being
typed is a new object in every snapshot, and `Diff.unsettled` rows may go --
and those are measured again by themselves, not with the hunk (a stream that
ended mid-line used to re-measure its whole open hunk per character). The
model's pairing of the open hunk is incremental as well
(`advtext.diff._Deriver`), except while its open change group has adds: an
add may pair with any removal of the group, so the group is aligned again for
each line that joins it. (A run of removals alone is no longer the exception:
review 3, item 8.)

One thing a streamed fragment does that a host will see: **a fragment with no
headers is "not a diff" until its first `+` or `-` line arrives.** Until then
nothing in it is a diff, and it is drawn as its lines as written under that
header (`FileDiff.dialect`, a `"raw"` region); on that line the lines above
become its context rows and the header a file header. Every line is on screen
before and after, and `Diff.rows()` keeps its prefix invariant (there were no
rows to contradict), but the display changes kind once.

## A diff inside a document: `DiffFences`

A fenced block whose info string begins `diff` or `patch`, in a document shown
by `advtext.ui.bare_view.BareView` or `advtext.ui.stream_view.StreamView`, can
be drawn by a `DiffView` in place of the code block:

    view = StreamView(stream, measure, host_for=DiffFences(height_cap=320))
    view = BareView(document=doc, theme=theme, measure=measure,
                    host_for=DiffFences(source=markdown_text))

`DiffFences` is a `BareView.host_for` (that module's docstring has what the
outer view does with one: the rectangle, the mouse, what a selection across
the diff copies). What is here is how the fence becomes a diff:

- **The diff is parsed from the markdown source, not from the code block.**
  A `CodeBlock` has its tabs expanded and its trailing blank lines dropped,
  and a diff with either is a different diff. A stream view has the source
  (`StreamDocument.source`); a bare view is handed it (`source=`, a string or
  a callable returning one). The fence's lines are found through
  `Document.sources`, the opening line's indentation is taken off each line,
  and the closing fence is recognised and left out. A fence that does not
  begin its own source line (`1. ```diff`), a document with no source map,
  or no `source` at all, falls back to the code block's own lines: tabs as
  spaces.
- **A fence still being written is read a line at a time.** Only what has
  arrived since the last look is cut from the source, split into lines and
  fed to a `advtext.diff.UnifiedDiffStream`; a line is fed when its newline
  has arrived, so the diff grows by whole lines (and a half-typed closing
  fence is never mistaken for a diff line). `fed_lines` counts them, and
  `tests/test_hostdiff.py` holds it to one per line appended at fifty lines
  and at five hundred.
- `HostedDiff.text`, which is what a selection across the diff copies and
  what `BareView.block_text` returns, is **the fence's body verbatim**:
  markers, headers and all. It is the text the markdown has there. A
  selection made *inside* the diff is `DiffView`'s and copies code.
- One `DiffView` per fence, kept for as long as the fence is the same text
  at the same place, so its horizontal scroll, its selection and its current
  hunk survive the document growing. `view_of(view, number)` and
  `BareView.hosted(number).view` reach it; `set_layout` switches every one.

## What has and has not been run

Headless ImGui frames (`tests/test_diff_view.py`) for geometry, items,
selection, copy, scrolling and culling; one real window under Xvfb for both
layouts, reporting counts. No person has looked at it, and nothing here says
how it looks.
"""

from __future__ import annotations

import math
import weakref
from bisect import bisect_right
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from advtext.backends.imgui_draw import (
    DEFAULT_PALETTE,
    DrawStats,
    FaceFont,
    Palette,
    draw_runs,
    snap_px,
)
from advtext.diff import (
    Diff,
    DiffRow,
    FileDiff,
    FileStatus,
    Hunk,
    RowKind,
    UnifiedDiffStream,
    has_control,
    has_invisible,
    tokenize,
)
from advtext.fontmetrics import Face
from advtext.markdown import TAB_WIDTH, Block, CodeBlock
from advtext.selection import Granularity, Rect
from advtext.shipout import DrawCmd, Glyph, Line
from advtext.spans import material_text
from advtext.style import BlockKind, FontSpec, MetricsResolver, Strut, Theme, fontlib_metrics
from advtext.ui.bare_view import SELECTION_OWNERSHIP, BareView, clipboard_text, granularity_for
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

__all__ = [
    "CONTROL_PLACEHOLDER",
    "COPY_GAP",
    "FENCE_LANGUAGES",
    "SYNTAX_CHUNK",
    "DiffFences",
    "DiffLayout",
    "DiffMetrics",
    "DiffView",
    "FramePlan",
    "HostedDiff",
    "Region",
    "RowInfo",
    "SyntaxColour",
    "language_for",
]

CONTROL_PLACEHOLDER = "\ufffd"
"""
What is drawn, in one cell and in the palette's *warning* ink, for a character
that cannot be drawn as itself (`advtext.diff.has_control`: NUL, escape, form
feed, a lone carriage return, DEL, ...). U+FFFD because the bundled code face
has it and has none of the Control Pictures block (measured: `FaceMetrics.has`
is false for U+2400, U+240D and U+2421 in Inconsolata). A U+FFFD that is really
in the text is drawn in the row's own ink, so the two are told apart by ink --
and the file's header says "contains control characters" whenever one is shown.
"""

COPY_GAP = "\u2026"
"""
The line a copy puts between two pieces of text that are not next to each
other in the file: an ellipsis, U+2026, alone on its line. See
`DiffView.selected_text`.

Known and not solved: a line of the *file* that is exactly this character
copies as the same line, and nothing in the copied text tells the two apart.
The separator was chosen to be something that is not code, not something that
cannot occur.
"""

# What is drawn after a line whose ending is the change (`Hunk.eol_rows`), by
# the terminator the line really has. A line with none gets no mark: the
# "No newline at end of file" row under it says so.
_EOL_MARKS = {"\r\n": "\\r\\n", "\n": "\\n", "\r": "\\r"}

#: The most lines of one side of one hunk handed to `syntax` in one call.
SYNTAX_CHUNK = 200

SyntaxColour = Callable[[Sequence[str], str], Sequence[Sequence[tuple[int, int, int]]]]
"""
A host's highlighter: `(lines, language)` to, for each line, `(start, end,
colour)` spans in character offsets of that line. See "Syntax colour" above.
"""

#: How far a selection is searched for the nearest line when the pointer is on
#: a row that has none (a header, a filler cell), in display rows.
_SNAP_REACH = 4096

_LANGUAGES = {
    "py": "python",
    "pyi": "python",
    "js": "javascript",
    "mjs": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "jsx": "javascript",
    "md": "markdown",
    "rs": "rust",
    "h": "c",
    "hpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "sh": "bash",
    "yml": "yaml",
    "rb": "ruby",
    "kt": "kotlin",
}


def language_for(label: str) -> str:
    """
    A language name guessed from a file label: its extension, lower-cased,
    with a few common ones spelled out (`py` is `python`). Empty for none.
    """
    name = label.rsplit("/", 1)[-1]
    if "." not in name:
        return {"makefile": "make", "dockerfile": "dockerfile"}.get(name.lower(), "")
    extension = name.rsplit(".", 1)[1].lower()
    return _LANGUAGES.get(extension, extension)


class DiffLayout(Enum):
    UNIFIED = "unified"
    SIDE_BY_SIDE = "side-by-side"


@dataclass(frozen=True, slots=True)
class DiffMetrics:
    """
    The grid, in whole pixels: `cell` wide, `row` tall, baseline `baseline`
    below a row's top. `font` is the code face at the size it is drawn at, and
    `advance` is what that face says a character is wide, unrounded.
    """

    font: FontSpec
    cell: int
    row: int
    baseline: int
    advance: float


@dataclass(frozen=True, slots=True)
class RowInfo:
    """
    What one display row is. `kind` is `"file"`, `"gap"`, `"hunk"` or `"row"`
    -- or `"fold"`, the one row standing for a file whose rows differ only in
    line endings and are not being shown, or `"raw"`, a line of a file that is
    shown as written (`FileDiff.dialect`).

    `hunk` is the hunk's index for `"hunk"` and `"row"`, and the gap's for
    `"gap"`. For a `"row"`, `left` and `right` index `Hunk.rows`: the same
    index on both for a unified row, and a side-by-side pair's two (either
    may be `None`) otherwise. For a `"raw"` row both index `FileDiff.raw`.
    """

    kind: str
    file: int
    hunk: int | None = None
    left: int | None = None
    right: int | None = None


@dataclass(frozen=True, slots=True)
class Region:
    """
    One clipped part of a frame, as `draw_runs` wants it.

    `x` is where the commands' x = 0 is, and `clip` the horizontal extent
    nothing may be drawn outside, both in pixels from the view's left edge.
    Command coordinates are scaled points from (`x`, the view's top).
    """

    name: str
    x: float
    clip: tuple[float, float]
    cmds: tuple[DrawCmd, ...]
    ink: int
    inks: tuple[tuple[int, int, int], ...]
    fills: tuple[tuple[Rect, int], ...]
    highlights: tuple[Rect, ...]

    def text_at(self, y: Scaled) -> str:
        """The characters on the row whose baseline is `y`, left to right, no spaces."""
        return "".join(
            chr(c.codepoint)
            for c in sorted(
                (c for c in self.cmds if isinstance(c, Glyph) and c.y == y), key=lambda c: c.x
            )
        )


@dataclass(frozen=True, slots=True)
class FramePlan:
    """What one frame draws: the regions, in order, and the rows they cover."""

    regions: tuple[Region, ...]
    first_row: int
    stop_row: int

    def region(self, name: str) -> Region:
        return next(r for r in self.regions if r.name == name)

    @property
    def glyphs(self) -> int:
        return sum(1 for r in self.regions for c in r.cmds if isinstance(c, Glyph))


# A position in the model: file, hunk, row of `Hunk.rows`, character of the row.
_Pos = tuple[int, int, int, int]

_FILE, _GAP, _HUNK, _ROWS, _FOLD, _RAW = range(6)


@dataclass(slots=True)
class _HunkInfo:
    """What the view has worked out about one hunk, extended as the hunk grows."""

    count: int = 0
    last: DiffRow | None = None
    columns: int = 0
    # Row indices on each side, in order, and each row's place in them.
    old: list[int] = field(default_factory=list)
    new: list[int] = field(default_factory=list)
    place: list[tuple[int, int]] = field(default_factory=list)
    # The last few rows measured, each with what `columns`, `len(old)` and
    # `len(new)` were before it: how a row that changed is taken back out.
    recent: list[tuple[DiffRow, int, int, int]] = field(default_factory=list)


@dataclass(slots=True, eq=False)
class _Index:
    """
    The display rows of one diff in one layout, as segments. Compared by
    identity: two indexes are the same only if they are the same object.
    """

    diff: Diff
    layout: DiffLayout
    # (kind, file, hunk or gap, rows), and the display row each starts at.
    segments: list[tuple[int, int, int, int]]
    starts: list[int]
    total: int
    columns: int
    digits: tuple[int, int]
    hunks: list[tuple[int, int, int]]  # (display row of the header, file, hunk)


@dataclass(frozen=True, slots=True)
class _Pane:
    """One column of code with its gutter. Pixels from the view's left edge."""

    side: int | None  # None: unified. 0: old. 1: new.
    x0: int
    x1: int
    numbers: tuple[tuple[int, int], ...]  # (right edge in cells from x0, 0 old / 1 new)
    marker: int  # cells from x0
    code: int  # pixels: where code column 0 is when not scrolled


class _Builder:
    """Glyph commands, and the ink ranges over them, for one region."""

    __slots__ = ("cmds", "font", "index", "inks", "xs")

    def __init__(self, font: str, xs: Callable[[int], Scaled]) -> None:
        self.cmds: list[DrawCmd] = []
        self.inks: list[tuple[int, int, int]] = []
        self.index = 0
        self.font = font
        self.xs = xs

    def line(self, baseline: Scaled, height: Scaled, depth: Scaled) -> None:
        # A `Line` ends the backend's rigid span, so each row is placed from
        # its own first glyph.
        self.cmds.append(Line(0, baseline, 0, height, depth, self.index, self.index))

    def text(
        self,
        text: str,
        column: int,
        baseline: Scaled,
        ink: int | Sequence[int] | None,
        low: int = 0,
        high: int | None = None,
        faces: dict[int, str] | None = None,
    ) -> None:
        """
        `text` from cell `column`, keeping the characters in cells `[low, high)`.

        `ink` is one colour, a colour per character of `text`, or `None` for
        the region's own. Spaces are not drawn: they have no ink. `faces`
        names the font of each character that is not in the region's own
        (a character borrowed from another face), by its index in `text`.
        """
        first = max(0, low - column)
        stop = len(text) if high is None else min(len(text), high - column)
        cmds, own, xs = self.cmds, self.font, self.xs
        for at in range(first, stop):
            character = text[at]
            if character == " ":
                continue
            colour = ink if ink is None or isinstance(ink, int) else ink[at]
            if colour is not None:
                if self.inks and self.inks[-1][1] == self.index and self.inks[-1][2] == colour:
                    start = self.inks[-1][0]
                    self.inks[-1] = (start, self.index + 1, colour)
                else:
                    self.inks.append((self.index, self.index + 1, colour))
            font = own if faces is None else faces.get(at, own)
            cmds.append(Glyph(font, ord(character), xs(column + at), baseline, self.index))
            self.index += 1


def _columns(text: str, tab: int) -> list[int] | None:
    """
    The cell each character of `text` starts in, with one more entry for the
    end of the line; `None` when there is no tab and a character is its index.

    **This is the one source of column arithmetic**: the width a row is
    measured at, the cell a glyph is issued in, the cell a mark or a
    highlight covers and the character a click lands on all come from here
    (through `_shown` for the glyphs). A tab advances to the next multiple of
    `tab`; every other character, a control character included, is one cell.
    `str.expandtabs` is not used anywhere: it restarts its count at a carriage
    return, which this does not.
    """
    if "\t" not in text:
        return None
    out = [0]
    for character in text:
        at = out[-1]
        out.append(at + tab - at % tab if character == "\t" else at + 1)
    return out


def _git_state(header: Sequence[str]) -> str:
    """
    What git's header lines say happened to a file besides its content: a
    rename, a copy, a mode change. A file that was only renamed or only had
    its mode changed has no rows, and without this it drew as `+0 -0` and
    nothing else.
    """
    found: dict[str, str] = {}
    for line in header:
        for key in (
            "rename from ",
            "rename to ",
            "copy from ",
            "copy to ",
            "old mode ",
            "new mode ",
        ):
            if line.startswith(key):
                found[key] = line[len(key) :]
    out = ""
    if "rename from " in found:
        out += f"  (renamed from {found['rename from ']})"
    if "copy from " in found:
        out += f"  (copied from {found['copy from ']})"
    if "old mode " in found and "new mode " in found:
        out += f"  (mode {found['old mode ']} -> {found['new mode ']})"
    return out


def _character_warning(file: FileDiff) -> str:
    """
    What a file's header says, in the warning ink, about characters drawn as
    placeholders in it. The two kinds are named apart: a NUL in a file is
    noise, and a right-to-left override is text that reads differently from
    what it is.
    """
    if not file.control_characters:
        return ""
    if not file.invisible_characters:
        return "  ! contains control characters"
    said = "  ! contains invisible or bidirectional control characters"
    if any(has_control(r.text) for h in file.hunks for r in h.rows) or any(
        has_control(line) for line in file.raw
    ):
        said = "  ! contains control characters" + said
    return said


def _width(text: str, tab: int) -> int:
    """How many cells `text` takes."""
    cells = _columns(text, tab)
    return len(text) if cells is None else cells[-1]


@dataclass(frozen=True, slots=True)
class _Shown:
    """
    One line as it is drawn: `text`, one character per cell (tabs as the
    spaces `_columns` gives them); `marked`, the cells holding a placeholder,
    which take the warning ink; `faces`, the font of each cell whose
    character is drawn from a face other than the code face.
    """

    text: str
    marked: tuple[int, ...] = ()
    faces: dict[int, str] | None = None

    def inks(self, ink: int | list[int], warning: int) -> int | list[int]:
        """`ink` (one colour, or one per cell) with the placeholders in `warning`."""
        if not self.marked:
            return ink
        out = [ink] * len(self.text) if isinstance(ink, int) else ink
        for cell in self.marked:
            out[cell] = warning
        return out


class DiffView:
    """
    A selectable view of one `Diff`. The module docstring is the contract.

    `theme` supplies the code face and its leading (`BlockKind.CODE`).
    `pixel_height`, if given, is the height the code face is drawn at as ImGui
    means it, for a host whose own font is "14"; otherwise the theme's size is
    used. Mutable for the reason `BareView` is: it is the imperative shell.
    """

    def __init__(
        self,
        diff: Diff,
        theme: Theme,
        *,
        layout: DiffLayout = DiffLayout.UNIFIED,
        pixel_height: float | None = None,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        metrics: MetricsResolver = fontlib_metrics,
        syntax: SyntaxColour | None = None,
        height_cap: float | None = None,
        expand_step: int = 20,
        copy_removed_lines: bool = False,
        copy_as: Callable[[DiffView], str] | None = None,
    ) -> None:
        self.theme = theme
        self.pixel_height = pixel_height
        self.px_per_inch = px_per_inch
        self.metrics = metrics
        self.syntax = syntax
        self.height_cap = height_cap
        self.expand_step = expand_step
        self.copy_removed_lines = copy_removed_lines
        self.copy_as = copy_as
        self.hand_cursor = True
        #: Rows whose width has been measured, ever. A stream adds its new rows.
        self.measured_rows = 0
        #: Calls made to `syntax`, the lines handed over, and calls that raised.
        self.syntax_calls = 0
        self.syntax_lines = 0
        self.syntax_errors = 0

        self._source = diff
        self._diff = diff
        self._layout = layout
        self._index: _Index | None = None
        self._hunks: dict[tuple[int, int], _HunkInfo] = {}
        self._raws: dict[int, tuple[int, str, int]] = {}
        self._unfolded: set[int] = set()
        self._coloured: dict[
            tuple[int, int, int, int],
            tuple[int, DiffRow, DiffRow, Sequence[Sequence[tuple[int, int, int]]], object],
        ] = {}
        self._metrics: tuple[tuple[object, ...], DiffMetrics] | None = None
        self._chars: dict[str, tuple[str, str | None, bool]] = {}
        self._xs: list[Scaled] = []
        self._scroll_x = 0
        self._max_scroll_x = 0
        self._bar_drag: tuple[float, int] | None = None
        self._origin: tuple[float, float] | None = None
        self._width = 0.0
        self._visible = range(0)
        self._scroll_to: int | None = None
        self._keep_top: RowInfo | None = None
        self._top_row = 0
        self._current: tuple[int, int] | None = None
        self._hot_gap: tuple[int, int] | None = None
        # The selection: two positions, start before end, and the side it is of.
        self._selection: tuple[_Pos, _Pos] | None = None
        self._side: int | None = None
        self._anchor: tuple[_Pos, _Pos] | None = None
        self._ends: tuple[DiffRow, DiffRow] | None = None
        self._kinds: tuple[object, frozenset[RowKind]] | None = None
        self._granularity = Granularity.CHARACTER
        self._dragging = False
        self._press = False
        self._drawn_frame = -(2**31)
        self._owned = 0
        self._plan: tuple[tuple[object, ...], FramePlan] | None = None
        #: Frames whose plan had to be built rather than reused from the last.
        self.plans_built = 0

    # ------------------------------------------------------------------
    # The model and the layout
    # ------------------------------------------------------------------

    @property
    def diff(self) -> Diff:
        """The diff being shown: the host's, with whatever context was expanded here."""
        return self._diff

    def set_diff(self, diff: Diff) -> None:
        """
        Show `diff`. Nothing happens if it is the object last given, so this
        can be called every frame; a different object replaces what is shown,
        expansions made here included.
        """
        if diff is self._source:
            return
        # Which files had their line-ending rows unfolded is about the object
        # that was shown. (Only `from_texts` sets `line_endings`, so a stream,
        # which is a new object per line, never has anything to lose here.)
        self._unfolded.clear()
        self._source = diff
        self._replace(diff)

    def _replace(self, diff: Diff) -> None:
        # The hunk `next_hunk` is on is followed by a row of it, not by its
        # number: expanding a gap away merges two hunks and renumbers the
        # rest (review 1, item 11).
        held: DiffRow | None = None
        if self._current is not None:
            was = self._hunk(*self._current)
            held = was.rows[0] if was is not None and was.rows else None
        self._diff = diff
        self._index = None
        self._kinds = None
        if self._current is not None and held is not None:
            f, h = self._current
            now = self._hunk(f, h)
            if (now is None or not now.rows or now.rows[0] is not held) and f < len(diff.files):
                for number, hunk in enumerate(diff.files[f].hunks):
                    if any(row is held for row in hunk.rows):
                        self._current = (f, number)
                        break
        if self._selection is not None and self._ends is not None:
            # The same text or nothing: the rows at both ends must still be there.
            start, end = self._selection
            if self._row(start) is not self._ends[0] or self._row(end) is not self._ends[1]:
                self.clear_selection()
        if self._current is not None and self._hunk(*self._current) is None:
            self._current = None

    @property
    def layout(self) -> DiffLayout:
        return self._layout

    def set_layout(self, layout: DiffLayout) -> None:
        """
        Switch layout, keeping the row at the top of the window at the top.
        The selection is cleared (see "Selection and copy").
        """
        if layout is self._layout:
            return
        if self._origin is not None and self._indexed().total:
            self._keep_top = self.row_info(min(self._top_row, self._indexed().total - 1))
        self._layout = layout
        self._index = None
        self.clear_selection()

    @property
    def metrics_px(self) -> DiffMetrics:
        """The grid this view draws on. Opens the code face on first use."""
        style = self.theme.style(BlockKind.CODE)
        key = (style.font, style.interline.baselineskip.width, self.pixel_height, self.px_per_inch)
        if self._metrics is not None and self._metrics[0] == key:
            return self._metrics[1]
        size = style.font.size
        if self.pixel_height is not None:
            from advtext import fontlib

            em_px = fontlib.em_size_for_pixel_height(style.font.face, self.pixel_height)
            size = sp_from_px(em_px, self.px_per_inch)
        font = FontSpec(style.font.face, size)
        leading = round(style.interline.baselineskip.width * size / max(1, style.font.size))
        strut = Strut.filling(leading)
        advance = px_from_sp(round(self.metrics(font.key).advance(ord("0"))), self.px_per_inch)
        made = DiffMetrics(
            font=font,
            cell=max(1, int(snap_px(advance))),
            row=max(1, math.ceil(px_from_sp(leading, self.px_per_inch) - 1e-6)),
            baseline=int(snap_px(px_from_sp(strut.height, self.px_per_inch))),
            advance=advance,
        )
        self._metrics = (key, made)
        self._xs = []
        self._chars = {}
        return made

    def _character(self, character: str) -> tuple[str, str | None, bool]:
        """
        What is drawn for one character of a line that is not plain ASCII:
        the character to issue, the font to issue it in when that is not the
        code face (`None` when it is), and whether it is a placeholder.

        The rules, which are review 1's (item 1) and review 3's (item 1):

        - A control character (`advtext.diff.has_control`) and an invisible
          or bidirectional one (`has_invisible`) is `CONTROL_PLACEHOLDER`.
          Neither draws as itself in any face, and the second kind is the
          dangerous one: it draws as nothing and changes what the rest of
          the line reads as.
        - A character the code face has is itself.
        - A character the code face lacks is drawn from the first face of
          the fallback chain `advtext.markdown` uses for a code block that
          has it -- the theme's prose face, then the math face -- at the
          code face's size and **in its own cell**: the grid does not move
          for it, so a glyph wider than a cell (CJK) overlaps its neighbour
          rather than shifting the columns a click is resolved on.
        - A character no face has is `CONTROL_PLACEHOLDER` too, so that it
          is seen to be there; white space no face has is a blank cell.

        Remembered per character for as long as the metrics stand.
        """
        found = self._chars.get(character)
        if found is not None:
            return found
        made: tuple[str, str | None, bool]
        if has_control(character) or has_invisible(character):
            made = (CONTROL_PLACEHOLDER, None, True)
        else:
            made = (" " if character.isspace() else CONTROL_PLACEHOLDER, None, True)
            font = self.metrics_px.font
            codepoint = ord(character)
            for face in dict.fromkeys((font.face, self.theme.faces.regular, Face.MATH)):
                key = FontSpec(face, font.size).key
                try:
                    has = self.metrics(key).has(codepoint)
                except Exception:  # noqa: BLE001 - a resolver that lacks a face is the host's
                    continue
                if has:
                    made = (character, None if face is font.face else key, False)
                    break
            if made[0] == " ":
                made = (" ", None, False)
        self._chars[character] = made
        return made

    def _shown(self, text: str, cells: list[int] | None = None) -> _Shown:
        """
        `text` as drawn; `cells` is `_columns(text)`, which is where every
        character's cell comes from here as everywhere else.
        """
        if cells is None and text.isascii() and not has_control(text):
            return _Shown(text)
        out: list[str] = []
        marked: list[int] = []
        faces: dict[int, str] = {}
        for at, character in enumerate(text):
            if character == "\t" and cells is not None:
                out.append(" " * (cells[at + 1] - cells[at]))
            elif " " <= character <= "~":
                out.append(character)
            else:
                cell = at if cells is None else cells[at]
                shown, font, placeholder = self._character(character)
                out.append(shown)
                if placeholder:
                    marked.append(cell)
                elif font is not None:
                    faces[cell] = font
        return _Shown("".join(out), tuple(marked), faces or None)

    def _x(self, column: int) -> Scaled:
        """Cell `column`'s left edge, in scaled points."""
        xs = self._xs
        if column >= len(xs):
            cell = self.metrics_px.cell
            xs.extend(
                sp_from_px(float(c * cell), self.px_per_inch) for c in range(len(xs), column + 64)
            )
        return xs[column]

    def _sp(self, pixels: float) -> Scaled:
        return sp_from_px(pixels, self.px_per_inch)

    def _hunk(self, file: int, hunk: int) -> Hunk | None:
        files = self._diff.files
        if file < len(files) and hunk < len(files[file].hunks):
            return files[file].hunks[hunk]
        return None

    def _row(self, pos: _Pos) -> DiffRow | None:
        hunk = self._hunk(pos[0], pos[1])
        return hunk.rows[pos[2]] if hunk is not None and pos[2] < len(hunk.rows) else None

    def _info(self, file: int, number: int, hunk: Hunk) -> _HunkInfo:
        """
        The view's record of a hunk, brought up to date with its rows.

        A hunk that grew keeps what was worked out for the rows it had: the
        check is that the last row measured is still the same object in the
        same place, which a stream guarantees and anything else fails.
        """
        info = self._hunks.get((file, number))
        rows = hunk.rows
        if info is not None and info.count:
            # How much of what was measured still stands. Only the last few
            # rows of a stream's open hunk can change (`Diff.unsettled`: the
            # line being typed, and two that may turn into a file header), so
            # those are taken back out one by one; if even the oldest of the
            # rows remembered is gone this is another hunk, and it starts over.
            base = info.count - len(info.recent)
            keep = 0
            for row, _, _, _ in info.recent:
                if base + keep >= len(rows) or rows[base + keep] is not row:
                    break
                keep += 1
            if keep == 0:
                info = None
            elif keep < len(info.recent):
                _, info.columns, old_kept, new_kept = info.recent[keep]
                info.count = base + keep
                del info.old[old_kept:]
                del info.new[new_kept:]
                del info.place[info.count :]
                del info.recent[keep:]
        if info is None:
            info = self._hunks[(file, number)] = _HunkInfo()
        if info.count == len(rows):
            return info
        tab = TAB_WIDTH
        for at in range(info.count, len(rows)):
            row = rows[at]
            info.recent.append((row, info.columns, len(info.old), len(info.new)))
            if row.kind is RowKind.META:
                # The line above may get an end-of-line mark (`_EOL_MARKS`):
                # room for the longest its partner can have, `\n`.
                width = _width(rows[at - 1].text, tab) + 3 if at else 0
            else:
                width = _width(row.text, tab)
                if row.eol != "\n":
                    width += 5  # room for a `\r\n` mark, should it be drawn
            if width > info.columns:
                info.columns = width
            old = new = -1
            if row.kind in (RowKind.CONTEXT, RowKind.REMOVE):
                old = len(info.old)
                info.old.append(at)
            if row.kind in (RowKind.CONTEXT, RowKind.ADD):
                new = len(info.new)
                info.new.append(at)
            info.place.append((old, new))
        self.measured_rows += len(rows) - info.count
        info.count = len(rows)
        info.last = rows[-1]
        del info.recent[:-4]
        return info

    def _raw_columns(self, f: int, file: FileDiff) -> int:
        """The widest line of a file shown as written; new lines only, for one that grows."""
        raw = file.raw
        count, last, columns = self._raws.get(f, (0, "", 0))
        if count > len(raw) or (count and raw[count - 1] is not last):
            count = columns = 0
        for line in raw[count:]:
            columns = max(columns, _width(line, TAB_WIDTH))
        self.measured_rows += len(raw) - count
        self._raws[f] = (len(raw), raw[-1] if raw else "", columns)
        return columns

    def _folded(self, f: int) -> bool:
        """Whether file `f`'s rows are folded away behind its header."""
        files = self._diff.files
        return f < len(files) and bool(files[f].line_endings) and f not in self._unfolded

    def line_endings_shown(self, file: int) -> bool:
        """Whether the rows of a line-endings-only file are being shown."""
        return file in self._unfolded

    def show_line_endings(self, file: int, shown: bool = True) -> None:
        """
        Show (or fold away again) the rows of a file whose two texts differ
        only in line endings (`FileDiff.line_endings`). Such a file is drawn
        as its header, which says so, and one row to click; this is that
        click. Folding clears the selection.
        """
        if shown == (file in self._unfolded):
            return
        if shown:
            self._unfolded.add(file)
        else:
            self._unfolded.discard(file)
            self.clear_selection()
        self._index = None

    def _indexed(self) -> _Index:
        """The display rows of the current diff and layout, built once per pair."""
        index = self._index
        if index is not None and index.diff is self._diff and index.layout is self._layout:
            return index
        unified = self._layout is DiffLayout.UNIFIED
        segments: list[tuple[int, int, int, int]] = []
        hunks: list[tuple[int, int, int]] = []
        seen: set[tuple[int, int]] = set()
        columns = 0
        old_max = new_max = 0
        total = 0

        def add(kind: int, file: int, number: int, rows: int) -> None:
            nonlocal total
            segments.append((kind, file, number, rows))
            total += rows

        for f, file in enumerate(self._diff.files):
            add(_FILE, f, 0, 1)
            if file.dialect:
                if file.raw:
                    add(_RAW, f, 0, len(file.raw))
                    columns = max(columns, self._raw_columns(f, file))
                continue
            if self._folded(f):
                add(_FOLD, f, 0, 1)
                continue
            gaps = file.gaps
            for h, hunk in enumerate(file.hunks):
                if gaps[h].count:
                    add(_GAP, f, h, 1)
                hunks.append((total, f, h))
                add(_HUNK, f, h, 1)
                info = self._info(f, h, hunk)
                seen.add((f, h))
                columns = max(columns, info.columns)
                add(_ROWS, f, h, len(hunk.rows) if unified else len(hunk.side_by_side))
                if hunk.old_start is not None and hunk.new_start is not None:
                    old_max = max(old_max, hunk.old_start + hunk.old_count)
                    new_max = max(new_max, hunk.new_start + hunk.new_count)
            if gaps and gaps[-1].count:
                add(_GAP, f, len(file.hunks), 1)
        for key in [key for key in self._hunks if key not in seen]:
            del self._hunks[key]
        starts: list[int] = []
        at = 0
        for segment in segments:
            starts.append(at)
            at += segment[3]
        for stale in [f for f in self._raws if f >= len(self._diff.files)]:
            del self._raws[stale]
        index = self._index = _Index(
            diff=self._diff,
            layout=self._layout,
            segments=segments,
            starts=starts,
            total=total,
            columns=columns,
            digits=(max(2, len(str(old_max))), max(2, len(str(new_max)))),
            hunks=hunks,
        )
        return index

    def _locate(self, row: int) -> tuple[int, int, int, int]:
        """Display row `row` as (kind, file, hunk or gap, offset in the segment)."""
        index = self._indexed()
        at = bisect_right(index.starts, row) - 1
        kind, file, number, _ = index.segments[at]
        return kind, file, number, row - index.starts[at]

    @property
    def row_count(self) -> int:
        """How many display rows the diff is, in the current layout."""
        return self._indexed().total

    def row_info(self, row: int) -> RowInfo:
        """What display row `row` is."""
        kind, file, number, offset = self._locate(row)
        if kind == _FILE:
            return RowInfo("file", file)
        if kind == _GAP:
            return RowInfo("gap", file, number)
        if kind == _HUNK:
            return RowInfo("hunk", file, number)
        if kind == _FOLD:
            return RowInfo("fold", file)
        if kind == _RAW:
            return RowInfo("raw", file, None, offset, offset)
        if self._layout is DiffLayout.UNIFIED:
            return RowInfo("row", file, number, offset, offset)
        pair = self._diff.files[file].hunks[number].side_by_side[offset]
        return RowInfo("row", file, number, pair.left, pair.right)

    def row_of(self, info: RowInfo) -> int:
        """
        The display row that shows `info` in the current layout, or failing
        that the nearest row before where it would be.
        """
        index = self._indexed()
        best = 0
        for at, (kind, file, number, _) in enumerate(index.segments):
            if file < info.file:
                continue
            if file > info.file:
                break
            start = index.starts[at]
            if kind == _FILE:
                best = start
                if info.kind == "file":
                    return start
                continue
            if kind in (_FOLD, _RAW):
                best = start
                if kind == _RAW and info.kind == "raw":
                    return start + max(0, min(info.left or 0, index.segments[at][3] - 1))
                if kind == _FOLD and info.kind == "fold":
                    return start
                continue
            if info.hunk is None or number > info.hunk:
                break
            if kind == _GAP:
                if info.kind == "gap" and number == info.hunk:
                    return start
                best = start
                continue
            best = start
            if number < info.hunk or kind == _HUNK:
                if kind == _HUNK and number == info.hunk and info.kind != "row":
                    return start
                continue
            # The rows of the hunk asked for.
            target = info.left if info.left is not None else info.right
            if info.kind != "row" or target is None:
                return start
            hunk = self._diff.files[file].hunks[number]
            if self._layout is DiffLayout.UNIFIED:
                return start + min(target, len(hunk.rows) - 1)
            for offset, pair in enumerate(hunk.side_by_side):
                if pair.left == target or pair.right == target:
                    return start + offset
            return start
        return best

    def row_of_hunk(self, file: int, hunk: int) -> int | None:
        """The display row of a hunk's header."""
        for row, f, h in self._indexed().hunks:
            if (f, h) == (file, hunk):
                return row
        return None

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def _panes(self, width: float) -> tuple[_Pane, ...]:
        cell = self.metrics_px.cell
        old, new = self._indexed().digits
        whole = int(width)
        if self._layout is DiffLayout.UNIFIED:
            marker = 1 + old + 1 + new + 1
            return (
                _Pane(
                    None, 0, whole, ((1 + old, 0), (2 + old + new, 1)), marker, (marker + 2) * cell
                ),
            )
        # Both panes start on the cell grid, so a gutter's columns and its
        # code's are the same columns; the right pane takes the odd pixels.
        half = max(0, (whole // cell - 1) // 2)
        left = _Pane(0, 0, half * cell, ((1 + old, 0),), 2 + old, (4 + old) * cell)
        start = (half + 1) * cell
        right = _Pane(
            1, start, max(start, whole), ((1 + new, 1),), 2 + new, start + (4 + new) * cell
        )
        return (left, right)

    def _code_width(self, panes: tuple[_Pane, ...]) -> int:
        return max(0, min(pane.x1 - pane.code for pane in panes))

    def _bar_height(self) -> int:
        return max(6, self.metrics_px.row // 2)

    @property
    def content_width(self) -> float:
        """
        The width, in pixels, at which no line would need to scroll, in the
        current layout: gutters and the longest line (twice, side by side).
        """
        index = self._indexed()
        cell = self.metrics_px.cell
        code = (index.columns + 1) * cell
        old, new = index.digits
        if self._layout is DiffLayout.UNIFIED:
            return float((old + new + 5) * cell + code)
        return float((old + 4) * cell + (new + 4) * cell + 2 * code + cell)

    @property
    def content_height(self) -> float:
        """The height of every row, in pixels, without the horizontal scrollbar."""
        return float(self._indexed().total * self.metrics_px.row)

    def height_for(self, width_px: float) -> float:
        """
        The height `draw` will claim at this width: every row, the horizontal
        scrollbar if a line is too long for it, and no more than `height_cap`.
        """
        full = self.content_height
        if full and self._overflow(self._panes(width_px)) > 0:
            full += self._bar_height()
        return full if self.height_cap is None else min(full, self.height_cap)

    def _overflow(self, panes: tuple[_Pane, ...]) -> int:
        """How far the code can scroll horizontally at these panes, in pixels."""
        needed = (self._indexed().columns + 1) * self.metrics_px.cell
        return max(0, needed - self._code_width(panes))

    @property
    def scroll_x(self) -> int:
        """The horizontal offset of the code, in pixels: a whole number of them."""
        return self._scroll_x

    @scroll_x.setter
    def scroll_x(self, value: float) -> None:
        # Clamped again at the next draw, when the width is known.
        self._scroll_x = max(0, int(snap_px(value)))

    @property
    def origin(self) -> tuple[float, float] | None:
        """Where the view's top-left was on screen at the last `draw`."""
        return self._origin

    @property
    def visible_rows(self) -> range:
        """The display rows the last `draw` issued."""
        return self._visible

    # ------------------------------------------------------------------
    # Hunks, for a host's keys
    # ------------------------------------------------------------------

    @property
    def current_hunk(self) -> tuple[int, int] | None:
        """The (file, hunk) `next_hunk`/`previous_hunk` is on, or `None`."""
        return self._current

    @property
    def top_row(self) -> int:
        """
        The display row at the top of the window, as of the last `draw` (0
        before any). Assigning to it is `scroll_to_row`. With `row_info` and
        `row_of` this is what keeps two views of one diff on the same line:

            other.top_row = other.row_of(leader.row_info(leader.top_row))

        in whatever layouts the two are in. Like every scroll here it lands
        on the frame after it is asked for.
        """
        return self._top_row

    @top_row.setter
    def top_row(self, row: int) -> None:
        self.scroll_to_row(row)

    def scroll_to_row(self, row: int) -> None:
        """Bring display row `row` to the top of the window on the next `draw`."""
        self._scroll_to = max(0, min(row, max(0, self._indexed().total - 1)))

    def _step(self, by: int) -> tuple[int, int] | None:
        hunks = self._indexed().hunks
        if not hunks:
            self._current = None
            return None
        keys = [(f, h) for _, f, h in hunks]
        if self._current in keys:
            at = max(0, min(len(keys) - 1, keys.index(self._current) + by))
        elif self._origin is None:
            at = 0 if by > 0 else len(keys) - 1
        else:
            # Nothing is current and the view has been drawn: start from
            # what is on screen -- the first hunk at or below the top of the
            # window going forwards (the last hunk if all are above), the
            # last one above it going back (the first if none is).
            rows = [row for row, _, _ in hunks]
            below = bisect_right(rows, self._top_row - 1)
            at = min(below, len(keys) - 1) if by > 0 else max(0, below - 1)
        self._current = keys[at]
        self.scroll_to_row(hunks[at][0])
        return self._current

    def next_hunk(self) -> tuple[int, int] | None:
        """
        Make the next hunk current and scroll to it. If none was current: the
        first hunk at or below the top of the window (the first of all, before
        the view has been drawn). Stays on the last. Returns the current
        (file, hunk), `None` if no hunks.
        """
        return self._step(1)

    def previous_hunk(self) -> tuple[int, int] | None:
        """
        The same, backwards. If none was current: the last hunk above the top
        of the window (the last of all, before the view has been drawn).
        """
        return self._step(-1)

    def expand(
        self,
        file: int,
        gap: int,
        lines: int | None = None,
        edge: Literal["top", "bottom"] = "top",
    ) -> None:
        """
        Reveal collapsed context: `Diff.expand`, applied to what is shown.
        `lines=None` is `expand_step`. Raises what the model raises.
        """
        self._replace(
            self._diff.expand(file, gap, self.expand_step if lines is None else lines, edge)
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    @property
    def selection(self) -> tuple[_Pos, _Pos] | None:
        """
        The selection as two positions `(file, hunk, row, character)`, start
        first, or `None`. `selection_side` says which side it is of.
        """
        return self._selection

    @property
    def selection_side(self) -> int | None:
        """0 for the old side, 1 for the new, `None` in the unified layout."""
        return self._side

    @property
    def owns_selection(self) -> bool:
        """Whether this view's selection is the one Ctrl+C copies."""
        return SELECTION_OWNERSHIP.holds(self._owned)

    def _own(self) -> None:
        self._owned = SELECTION_OWNERSHIP.take()

    def clear_selection(self) -> None:
        self._selection = None
        self._anchor = None
        self._ends = None
        self._kinds = None
        self._dragging = False

    def _select(self, start: _Pos, end: _Pos, side: int | None) -> None:
        if end < start:
            start, end = end, start
        first, last = self._row(start), self._row(end)
        if first is None or last is None:
            self.clear_selection()
            return
        self._selection = (start, end)
        self._side = side
        self._ends = (first, last)
        self._kinds = None

    def select(self, start: _Pos, end: _Pos, side: int | None = None) -> None:
        """
        Select from `start` to `end` and take ownership of the current
        selection. `side` matters only side by side, where it defaults to new.
        """
        if self._layout is DiffLayout.UNIFIED:
            side = None
        elif side is None:
            side = 1
        self._dragging = False
        self._select(start, end, side)
        self._own()

    def select_all(self, side: int | None = None) -> None:
        """Select every line (of `side`, side by side: the side last used, else new)."""
        self._dragging = False
        self._select_all(side)
        self._own()

    def _select_all(self, side: int | None) -> None:
        if self._layout is DiffLayout.UNIFIED:
            side = None
        elif side is None:
            side = self._side if self._side is not None else 1
        files = self._diff.files
        filled = [
            (f, h)
            for f, file in enumerate(files)
            if not self._folded(f)
            for h, hunk in enumerate(file.hunks)
            if hunk.rows
        ]
        if not filled:
            self.clear_selection()
            return
        f, h = filled[-1]
        rows = files[f].hunks[h].rows
        self._select((*filled[0], 0, 0), (f, h, len(rows) - 1, len(rows[-1].text)), side)

    def _between(self, start: _Pos, end: _Pos) -> Iterator[tuple[int, int, int, DiffRow]]:
        """Every row from `start`'s to `end`'s, in order, with where it is."""
        files = self._diff.files
        for f in range(start[0], min(end[0], len(files) - 1) + 1):
            if self._folded(f):
                continue  # rows that are not shown are not selected
            hunks = files[f].hunks
            low = start[1] if f == start[0] else 0
            high = end[1] if f == end[0] else len(hunks) - 1
            for h in range(low, min(high, len(hunks) - 1) + 1):
                rows = hunks[h].rows
                first = start[2] if (f, h) == start[:2] else 0
                last = end[2] if (f, h) == end[:2] else len(rows) - 1
                for r in range(first, min(last, len(rows) - 1) + 1):
                    yield f, h, r, rows[r]

    def _selected_kinds(self) -> frozenset[RowKind]:
        """
        Which kinds of row the selection takes: the rule under "Selection and
        copy". Worked out once per selection; the scan stops at the first row
        that settles it.
        """
        selection = self._selection
        if selection is None:
            return frozenset()
        key = (selection, self._side, self.copy_removed_lines)
        if self._kinds is not None and self._kinds[0] == key:
            return self._kinds[1]
        if self._side == 0:
            kinds = frozenset((RowKind.CONTEXT, RowKind.REMOVE))
        elif self._side == 1:
            kinds = frozenset((RowKind.CONTEXT, RowKind.ADD))
        elif self.copy_removed_lines:
            kinds = frozenset((RowKind.CONTEXT, RowKind.ADD, RowKind.REMOVE))
        else:
            start, end = selection
            kinds = frozenset((RowKind.REMOVE,))
            for f, h, r, row in self._between(start, end):
                if row.kind not in (RowKind.CONTEXT, RowKind.ADD):
                    continue
                # A line the selection only touches the edge of does not count:
                # it begins at or after the line's last character, or ends
                # before its first. That is a rule about the row and the
                # column and nothing else -- it used to ask also that the
                # line not be empty, so a blank context line above some
                # removed lines counted as selected where a non-blank one did
                # not, and the removed lines were left out of the copy
                # (review 1, item 6).
                if (f, h, r) == start[:3] != end[:3] and start[3] >= len(row.text):
                    continue
                if (f, h, r) == end[:3] != start[:3] and end[3] == 0:
                    continue
                kinds = frozenset((RowKind.CONTEXT, RowKind.ADD))
                break
        self._kinds = (key, kinds)
        return kinds

    def selected_text(self) -> str:
        """
        The selection as code: see "Selection and copy". Empty for none.

        Lines are joined with `"\\n"`, whatever their own endings were. **Text
        from pieces that are not next to each other in the file is never
        joined as if it were**: where the selection runs from one hunk into
        the next across lines that are not shown (a collapsed-context row),
        the copy has a line holding only `COPY_GAP` (an ellipsis, U+2026)
        between the two pieces; and where it runs from one file into the
        next, that line and then a line holding the next file's label. Those
        lines are in neither text, which is why they are these and nothing
        that could be code. The same holds for either side, side by side. A
        selection inside one hunk, or across hunks that an expansion has
        made adjacent, has neither.
        """
        selection = self._selection
        if selection is None or selection[0] == selection[1]:
            return ""
        start, end = selection
        kinds = self._selected_kinds()
        files = self._diff.files
        pieces: list[str] = []
        last: tuple[int, int] | None = None
        for f, h, r, row in self._between(start, end):
            if row.kind not in kinds:
                continue
            if last is not None and last != (f, h):
                if last[0] != f:
                    pieces += [COPY_GAP, files[f].label or "(unnamed)"]
                elif h != last[1] + 1 or files[f].gaps[h].count != 0:
                    pieces.append(COPY_GAP)
            last = (f, h)
            low = start[3] if (f, h, r) == start[:3] else 0
            high = end[3] if (f, h, r) == end[:3] else len(row.text)
            pieces.append(row.text[low:high])
        return "\n".join(pieces)

    def copy(self, text: str | None = None) -> None:
        """
        Put `text` on the clipboard, or the selection as Ctrl+C would. With
        nothing to copy (no `text`, and a selection that copies as nothing)
        the clipboard is left as it was. A NUL goes to the clipboard as
        U+2400 (`advtext.ui.bare_view.clipboard_text`: the clipboard is a C
        string, and a NUL cut the copy short); `selected_text` keeps it.
        """
        from imgui_bundle import imgui

        if text is None:
            text = self._copied()
            if not text:
                return
        imgui.set_clipboard_text(clipboard_text(text))

    def _copied(self) -> str:
        return self.selected_text() if self.copy_as is None else self.copy_as(self)

    # -- from a point to a position -------------------------------------

    def _line_at(self, row: int, side: int | None) -> tuple[int, int, int] | None:
        """The selectable line display row `row` shows on `side`, if it shows one."""
        kind, file, number, offset = self._locate(row)
        if kind != _ROWS:
            return None
        hunk = self._diff.files[file].hunks[number]
        if side is None:
            at: int | None = offset
        else:
            pair = hunk.side_by_side[offset]
            at = pair.left if side == 0 else pair.right
        if at is None or hunk.rows[at].kind is RowKind.META:
            return None
        return file, number, at

    def _position(self, row: int, column: int, side: int | None) -> _Pos | None:
        """
        The position nearest display row `row`, cell `column`: on that row if
        it shows a line on `side`, else the start of the next line that does,
        else the end of the one before.
        """
        total = self._indexed().total
        if total == 0:
            return None
        row = max(0, min(row, total - 1))
        line = self._line_at(row, side)
        if line is not None:
            text = self._diff.files[line[0]].hunks[line[1]].rows[line[2]].text
            cells = _columns(text, TAB_WIDTH)
            if cells is None:
                return (*line, max(0, min(column, len(text))))
            return (*line, max(0, min(len(text), bisect_right(cells, max(0, column)) - 1)))
        for other in range(row + 1, min(total, row + _SNAP_REACH)):
            line = self._line_at(other, side)
            if line is not None:
                return (*line, 0)
        for other in range(row - 1, max(-1, row - _SNAP_REACH), -1):
            line = self._line_at(other, side)
            if line is not None:
                text = self._diff.files[line[0]].hunks[line[1]].rows[line[2]].text
                return (*line, len(text))
        return None

    def _extent(self, pos: _Pos, granularity: Granularity) -> tuple[_Pos, _Pos]:
        """What a click at `pos` selects: a caret, the word, or the line."""
        row = self._row(pos)
        if granularity is Granularity.CHARACTER or row is None:
            return pos, pos
        if granularity is Granularity.LINE:
            return (*pos[:3], 0), (*pos[:3], len(row.text))
        spans = tokenize(row.text)
        for start, end in spans:
            if start <= pos[3] < end:
                return (*pos[:3], start), (*pos[:3], end)
        if spans:
            return (*pos[:3], spans[-1][0]), (*pos[:3], spans[-1][1])
        return pos, pos

    # ------------------------------------------------------------------
    # What a frame draws
    # ------------------------------------------------------------------

    def _syntax_for(
        self, file: int, number: int, hunk: Hunk, info: _HunkInfo, row: int, side: int
    ) -> Sequence[tuple[int, int, int]]:
        """The host's colour spans for one row, as seen from one side of its hunk."""
        syntax = self.syntax
        place = info.place[row][side]
        if syntax is None or place < 0:
            return ()
        chunk = place // SYNTAX_CHUNK
        members = (info.old if side == 0 else info.new)[
            chunk * SYNTAX_CHUNK : (chunk + 1) * SYNTAX_CHUNK
        ]
        rows = hunk.rows
        first, last = rows[members[0]], rows[members[-1]]
        key = (file, number, side, chunk)
        found = self._coloured.get(key)
        if (
            found is None
            or found[0] != len(members)
            or found[1] is not first
            or found[2] is not last
            or found[4] is not syntax  # another highlighter: its colours, not the last one's
        ):
            lines = [rows[at].text for at in members]
            self.syntax_calls += 1
            self.syntax_lines += len(lines)
            try:
                spans = syntax(lines, language_for(self._diff.files[file].label))
            except Exception:  # noqa: BLE001 - a host's error must not take the frame
                self.syntax_errors += 1
                spans = ()
            found = self._coloured[key] = (len(members), first, last, spans, syntax)
        at = place - chunk * SYNTAX_CHUNK
        return found[3][at] if at < len(found[3]) else ()

    def _file_header(self, file: FileDiff) -> tuple[str, str]:
        """A file header's text, and the part of it that is a warning."""
        if file.dialect:
            # Not read as rows: no counts to give, and saying "+0 -0" of a
            # file that is shown as written would be a statement about it.
            name = f"{file.label}  " if file.label else ""
            return f"{name}({file.dialect}: shown as written)", _character_warning(file)
        text = f"{file.label or '(unnamed)'}  +{file.added} -{file.removed}"
        state = {
            FileStatus.NEW: "  (new file)",
            FileStatus.DELETED: "  (deleted file)",
            FileStatus.BINARY: "  (binary file)",
            FileStatus.UNCHANGED: "  (no changes)",
        }.get(file.status, "")
        if file.line_endings:
            state += f"  (line endings only: {file.line_endings})"
        state += _git_state(file.header)
        warning = f"  ! {file.will_not_apply}" if file.will_not_apply else ""
        if file.unread:
            # Lines under a hunk that were read as nothing (`FileDiff.unread`):
            # not drawn, so said -- a view must not show less than it was given
            # without saying so.
            count = len(file.unread)
            warning += f"  ! {count} line{'s' if count != 1 else ''} not read as part of the diff"
        warning += _character_warning(file)
        return text + state, warning

    def _fold_text(self, file: FileDiff) -> str:
        rows = sum(1 for h in file.hunks for r in h.rows if r.kind is not RowKind.META)
        return f"... {rows} rows differ only in how the line ends  (click to show them)"

    def _gap_text(self, file: FileDiff, gap: int) -> str:
        found = file.gaps[gap]
        lines = "1 unchanged line" if found.count == 1 else f"{found.count} unchanged lines"
        return f"... {lines}" + ("  (click to show more)" if found.expandable else "")

    def frame_plan(
        self,
        width_px: float,
        first_row: int = 0,
        stop_row: int | None = None,
        palette: Palette = DEFAULT_PALETTE,
    ) -> FramePlan:
        """
        What drawing display rows `[first_row, stop_row)` at this width issues.

        Pure: no ImGui, no window. `draw` calls it with the rows the window
        shows and paints the result; a test calls it to see what a frame holds.
        Three kinds of region come back, in drawing order: `"frame"` (bands,
        gutters and headers, not scrolled), then one `"code"`, or `"old"` and
        `"new"`, clipped to their pane and shifted by `scroll_x`.
        """
        metrics = self.metrics_px
        index = self._indexed()
        colours = palette.diff
        cell, row_px = metrics.cell, metrics.row
        font = metrics.font.key
        stop = index.total if stop_row is None else min(stop_row, index.total)
        first = max(0, min(first_row, stop))
        panes = self._panes(width_px)
        scroll = min(self._scroll_x, self._overflow(panes))
        row_sp = self._sp(float(row_px))
        strut_height = self._sp(float(metrics.baseline))
        strut_depth = row_sp - strut_height
        whole = self._sp(float(int(width_px)))
        x = self._x

        frame = _Builder(font, x)
        frame_fills: list[tuple[Rect, int]] = []
        low = scroll // cell
        code = [_Builder(font, x) for _ in panes]
        raw = _Builder(font, x)
        raw_high = low + (int(width_px) - panes[0].code) // cell + 2
        code_fills: list[list[tuple[Rect, int]]] = [[] for _ in panes]
        code_marks: list[list[Rect]] = [[] for _ in panes]
        highs = [low + (pane.x1 - pane.code) // cell + 2 for pane in panes]

        selection = self._selection
        kinds = self._selected_kinds() if selection is not None else frozenset()
        current = self._current
        files = self._diff.files
        row = first
        while row < stop:
            kind, f, number, offset = self._locate(row)
            file = files[f]
            top = self._sp(float(row * row_px))
            baseline = top + strut_height
            if kind == _RAW:
                # A line of a file shown as written: the whole width, scrolled
                # with the code, in the context ink, and no gutter -- there is
                # no number or marker this module vouches for.
                text = file.raw[offset]
                drawn = self._shown(text, _columns(text, TAB_WIDTH))
                raw.line(baseline, strut_height, strut_depth)
                raw.text(
                    drawn.text,
                    0,
                    baseline,
                    drawn.inks(colours.context, colours.warning),
                    low,
                    raw_high,
                    drawn.faces,
                )
                row += 1
                continue
            if kind != _ROWS:
                frame_fills.append((Rect(0, top, whole, row_sp), colours.header_fill))
                frame.line(baseline, strut_height, strut_depth)
                if kind == _FILE:
                    text, warning = self._file_header(file)
                    said = self._shown(text)
                    frame.text(
                        said.text,
                        1,
                        baseline,
                        said.inks(colours.header, colours.warning),
                        faces=said.faces,
                    )
                    said = self._shown(warning)
                    frame.text(
                        said.text, 1 + len(text), baseline, colours.warning, faces=said.faces
                    )
                elif kind == _HUNK:
                    # A label and a hunk's section are text from the diff too:
                    # a file *named* with a right-to-left override is the
                    # oldest trick of this kind.
                    said = self._shown(file.hunks[number].header)
                    frame.text(
                        said.text,
                        1,
                        baseline,
                        said.inks(colours.header, colours.warning),
                        faces=said.faces,
                    )
                elif kind == _FOLD:
                    frame.text(self._fold_text(file), 1, baseline, colours.meta)
                else:
                    frame.text(self._gap_text(file, number), 1, baseline, colours.meta)
                if kind == _HUNK and current == (f, number):
                    frame_fills.append((Rect(0, top, self._sp(3.0), row_sp), colours.current))
                row += 1
                continue

            hunk = file.hunks[number]
            info = self._info(f, number, hunk)
            rows = hunk.rows
            spans = hunk.spans
            eol_rows = hunk.eol_rows
            if current == (f, number):
                frame_fills.append((Rect(0, top, self._sp(3.0), row_sp), colours.current))
            frame.line(baseline, strut_height, strut_depth)
            for at, pane in enumerate(panes):
                if pane.side is None:
                    shown: int | None = offset
                else:
                    pair = hunk.side_by_side[offset]
                    shown = pair.left if pane.side == 0 else pair.right
                if shown is None:
                    continue
                line = rows[shown]
                left = pane.x0 // cell
                # The band, the numbers and the marker: never scrolled.
                band = {RowKind.ADD: colours.add_fill, RowKind.REMOVE: colours.remove_fill}.get(
                    line.kind
                )
                if band is not None:
                    frame_fills.append(
                        (
                            Rect(
                                self._sp(float(pane.x0)),
                                top,
                                self._sp(float(pane.x1 - pane.x0)),
                                row_sp,
                            ),
                            band,
                        )
                    )
                for right, which in pane.numbers:
                    value = line.old_no if which == 0 else line.new_no
                    if value is not None:
                        digits = str(value)
                        frame.text(digits, left + right - len(digits), baseline, colours.gutter)
                if line.kind is not RowKind.CONTEXT:
                    frame.text(line.kind.value, left + pane.marker, baseline, colours.gutter)

                # The code: scrolled, clipped, and only the columns in view.
                builder = code[at]
                text = line.text
                cells = _columns(text, TAB_WIDTH)
                drawn = self._shown(text, cells)
                shown_text = drawn.text
                ink = {
                    RowKind.ADD: colours.add,
                    RowKind.REMOVE: colours.remove,
                    RowKind.META: colours.meta,
                }.get(line.kind, colours.context)
                inks: int | list[int] = ink
                if self.syntax is not None and line.kind is not RowKind.META:
                    side = 0 if (pane.side == 0 or line.kind is RowKind.REMOVE) else 1
                    tokens = self._syntax_for(f, number, hunk, info, shown, side)
                    if tokens:
                        inks = [ink] * len(shown_text)
                        for start, end, colour in tokens:
                            start = max(0, min(start, len(text)))
                            end = max(start, min(end, len(text)))
                            a = start if cells is None else cells[start]
                            b = end if cells is None else cells[end]
                            inks[a:b] = [colour] * (b - a)
                inks = drawn.inks(inks, colours.warning)
                builder.line(baseline, strut_height, strut_depth)
                builder.text(shown_text, 0, baseline, inks, low, highs[at], drawn.faces)
                if shown in eol_rows:
                    ending = _EOL_MARKS.get(hunk.terminator(shown), "")
                    builder.text(
                        ending, len(shown_text) + 1, baseline, colours.meta, low, highs[at]
                    )
                mark = {
                    RowKind.ADD: colours.add_emphasis,
                    RowKind.REMOVE: colours.remove_emphasis,
                }.get(line.kind)
                if mark is not None:
                    for start, end in spans[shown]:
                        a = start if cells is None else cells[start]
                        b = end if cells is None else cells[end]
                        code_fills[at].append((Rect(x(a), top, x(b) - x(a), row_sp), mark))
                if (
                    selection is not None
                    and pane.side == self._side
                    and line.kind in kinds
                    and selection[0][:3] <= (f, number, shown) <= selection[1][:3]
                ):
                    start_pos, end_pos = selection
                    here = (f, number, shown)
                    a = start_pos[3] if here == start_pos[:3] else 0
                    b = end_pos[3] if here == end_pos[:3] else len(text)
                    a = a if cells is None else cells[min(a, len(text))]
                    b = b if cells is None else cells[min(b, len(text))]
                    if here != end_pos[:3]:
                        b += 1  # the line end, so a selected empty line shows
                    if b > a:
                        code_marks[at].append(Rect(x(a), top, x(b) - x(a), row_sp))
            row += 1

        regions = [
            Region(
                "frame",
                0.0,
                (0.0, float(int(width_px))),
                tuple(frame.cmds),
                colours.context,
                tuple(frame.inks),
                tuple(frame_fills),
                (),
            )
        ]
        for at, pane in enumerate(panes):
            regions.append(
                Region(
                    {None: "code", 0: "old", 1: "new"}[pane.side],
                    float(pane.code - scroll),
                    (float(pane.code), float(pane.x1)),
                    tuple(code[at].cmds),
                    colours.context,
                    tuple(code[at].inks),
                    tuple(code_fills[at]),
                    tuple(code_marks[at]),
                )
            )
        if raw.cmds:
            regions.append(
                Region(
                    "raw",
                    float(panes[0].code - scroll),
                    (float(panes[0].code), float(int(width_px))),
                    tuple(raw.cmds),
                    colours.context,
                    tuple(raw.inks),
                    (),
                    (),
                )
            )
        return FramePlan(tuple(regions), first, stop)

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
        Draw the diff at the cursor and handle the mouse and the keys.

        The item this leaves as ImGui's last item is the view's rectangle (the
        child window, with `height_cap`), so `imgui.is_item_hovered()` straight
        after is "the mouse is over the diff".
        """
        from imgui_bundle import imgui

        self._begin_frame()
        colours = palette or DEFAULT_PALETTE
        metrics = self.metrics_px
        index = self._indexed()
        if width_px is None:
            width_px = imgui.get_content_region_avail().x
        width_px = max(float(width_px), float(metrics.cell * 8))

        capped = self.height_cap is not None
        if capped:
            imgui.begin_child(
                f"##advtext-diff-child-{id(self):x}",
                imgui.ImVec2(width_px, max(1.0, self.height_for(width_px))),
            )
            # Less the child's own vertical scrollbar, when it has one.
            width_px = max(float(metrics.cell * 8), imgui.get_content_region_avail().x)
        try:
            return self._draw_here(imgui, index, metrics, colours, fonts, width_px)
        finally:
            if capped:
                imgui.end_child()

    def _draw_here(
        self,
        imgui: Any,
        index: _Index,
        metrics: DiffMetrics,
        colours: Palette,
        fonts: FaceFont,
        width_px: float,
    ) -> DrawStats:
        panes = self._panes(width_px)
        overflow = self._overflow(panes)
        self._max_scroll_x = overflow
        self._scroll_x = min(self._scroll_x, overflow)
        bar = self._bar_height() if overflow > 0 and index.total else 0
        row_px = metrics.row
        height = float(index.total * row_px + bar)

        cursor = imgui.get_cursor_screen_pos()
        origin = imgui.ImVec2(math.floor(cursor.x + 0.5), math.floor(cursor.y + 0.5))
        size = imgui.ImVec2(width_px, height)
        self._origin = (float(origin.x), float(origin.y))
        self._width = width_px
        window_top = imgui.get_window_pos().y
        window_bottom = window_top + imgui.get_window_size().y
        # Where the window's content begins on screen, under any title bar:
        # what "the top of the window" means for a row being scrolled to.
        # (`get_cursor_start_pos` is where the content starts *as scrolled*,
        # so the scroll is added back to get where it is clipped.)
        content_top = window_top + imgui.get_cursor_start_pos().y + imgui.get_scroll_y()

        # Scrolling asked for since the last frame. ImGui applies a scroll on
        # the next frame, so the rows are culled against where they are now.
        target: float | None = None
        if self._keep_top is not None:
            target = float(self.row_of(self._keep_top) * row_px)
            self._keep_top = None
        if self._scroll_to is not None:
            target = float(self._scroll_to * row_px)
            self._scroll_to = None
        if target is not None:
            imgui.set_scroll_y(max(0.0, imgui.get_scroll_y() + (origin.y + target) - content_top))

        first = max(0, int((window_top - origin.y) // row_px))
        stop = min(index.total, int(math.ceil((window_bottom - origin.y) / row_px)))
        stop = max(first, stop)
        self._visible = range(first, stop)
        self._top_row = max(0, min(index.total - 1, int((content_top - origin.y) // row_px)))
        # The plan is a function of these and nothing else, and on most
        # frames none of them has changed: measured at 3.4 ms of a 10 ms frame
        # for 35 rows of code, so it is kept from one frame to the next.
        key = (
            index,
            metrics,
            first,
            stop,
            int(width_px),
            self._scroll_x,
            self._selection,
            self._side,
            self._current,
            self.copy_removed_lines,
            self.syntax,
            colours,
        )
        kept = self._plan
        if kept is not None and all(a is b or a == b for a, b in zip(kept[0], key, strict=True)):
            plan = kept[1]
        else:
            plan = self.frame_plan(width_px, first, stop, colours)
            self._plan = (key, plan)
            self.plans_built += 1

        draw_list = imgui.get_window_draw_list()
        glyphs = missing = rules = 0
        top = max(window_top, origin.y)
        bottom = min(window_bottom, origin.y + height)
        for region in plan.regions:
            if not region.cmds and not region.fills and not region.highlights:
                continue
            draw_list.push_clip_rect(
                imgui.ImVec2(origin.x + region.clip[0], top),
                imgui.ImVec2(origin.x + region.clip[1], bottom),
                True,
            )
            try:
                stats = draw_runs(
                    draw_list,
                    ((region.cmds, region.ink),),
                    imgui.ImVec2(origin.x + region.x, origin.y),
                    fonts=fonts,
                    palette=colours,
                    highlights=region.highlights,
                    px_per_inch=self.px_per_inch,
                    metrics=self.metrics,
                    inks=region.inks,
                    fills=region.fills,
                )
            finally:
                draw_list.pop_clip_rect()
            glyphs += stats.glyphs
            missing += stats.missing
            rules += stats.rules

        if bar:
            self._scrollbar(imgui, origin, width_px, bottom - bar, bar, panes)
            imgui.set_cursor_screen_pos(cursor)

        over = self._hovering(imgui, origin, size)
        self._hot_gap = self._gap_under_mouse(imgui, origin, row_px) if over else None
        hot_fold = self._fold_under_mouse(imgui, origin, row_px) if over else None
        clicked = imgui.is_mouse_clicked(imgui.MouseButton_.left)
        self._press = over and clicked and self._hot_gap is None and hot_fold is None
        self._end_a_drag_that_missed_its_release(imgui)
        if (self._press or self._dragging) and height > 0.0:
            imgui.invisible_button(self._button_id(), size)
        else:
            imgui.dummy(size)
        if self._hot_gap is not None:
            if self.hand_cursor:
                imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
            if clicked:
                edge: Literal["top", "bottom"] = "bottom" if imgui.get_io().key_shift else "top"
                self.expand(*self._hot_gap, None, edge)
        if hot_fold is not None:
            if self.hand_cursor:
                imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
            if clicked:
                self.show_line_endings(hot_fold)
        self._handle_mouse(imgui, origin, panes, metrics)
        self._handle_keys(imgui)
        if over:
            self._handle_wheel(imgui, metrics)
        return DrawStats(glyphs=glyphs, missing=missing, rules=rules)

    # ------------------------------------------------------------------
    # Interaction. The rules are `BareView`'s; its docstrings have the
    # measurements behind each of them.
    # ------------------------------------------------------------------

    def _begin_frame(self) -> None:
        """A drag goes on only from one drawn frame to the very next."""
        from imgui_bundle import imgui

        frame = int(imgui.get_frame_count())
        if frame - self._drawn_frame > 1:
            self._dragging = False
            self._bar_drag = None
        self._drawn_frame = frame

    def _button_id(self) -> str:
        return f"##advtext-diff-{id(self):x}"

    def _item_in_front(self, imgui: Any) -> bool:
        """Whether an item other than this view's own drag button is under the mouse."""
        hovered_id = getattr(getattr(imgui, "internal", None), "get_hovered_id", None)
        if hovered_id is None:
            return bool(imgui.is_any_item_hovered())
        hovered = hovered_id()
        return bool(hovered != 0 and hovered != imgui.get_id(self._button_id()))

    def _hovering(self, imgui: Any, origin: Any, size: Any) -> bool:
        """The mouse is on the view, in the hovered window, with nothing in front."""
        if not imgui.is_window_hovered() or self._item_in_front(imgui):
            return False
        return bool(
            imgui.is_mouse_hovering_rect(origin, imgui.ImVec2(origin.x + size.x, origin.y + size.y))
        )

    def _end_a_drag_that_missed_its_release(self, imgui: Any) -> None:
        left = imgui.MouseButton_.left
        if self._dragging and not imgui.is_mouse_down(left) and not imgui.is_mouse_released(left):
            self._dragging = False

    def _gap_under_mouse(self, imgui: Any, origin: Any, row_px: int) -> tuple[int, int] | None:
        """The expandable collapsed-context row under the mouse, as (file, gap)."""
        total = self._indexed().total
        row = int((imgui.get_mouse_pos().y - origin.y) // row_px)
        if not 0 <= row < total:
            return None
        kind, file, number, _ = self._locate(row)
        if kind == _GAP and self._diff.files[file].gaps[number].expandable:
            return file, number
        return None

    def _fold_under_mouse(self, imgui: Any, origin: Any, row_px: int) -> int | None:
        """The file whose folded line-ending row is under the mouse."""
        total = self._indexed().total
        row = int((imgui.get_mouse_pos().y - origin.y) // row_px)
        if not 0 <= row < total:
            return None
        kind, file, _, _ = self._locate(row)
        return file if kind == _FOLD else None

    def _pointed(
        self,
        imgui: Any,
        origin: Any,
        panes: tuple[_Pane, ...],
        metrics: DiffMetrics,
        side: Any,
        press: bool = False,
    ) -> tuple[_Pos | None, int | None]:
        """
        The position under the mouse and the side it is on. `side` fixes the
        side (a drag stays on the side it began on); `...` means "whichever
        pane the mouse is in".
        """
        mouse = imgui.get_mouse_pos()
        x = mouse.x - origin.x
        if side is ...:
            pane = panes[0] if len(panes) == 1 or x < panes[1].x0 else panes[1]
        else:
            pane = next(p for p in panes if p.side == side)
        row = int((mouse.y - origin.y) // metrics.row)
        column = int(math.floor((x - pane.code + self._scroll_x) / metrics.cell + 0.5))
        if press and x < pane.code:
            # A press on the gutter is a press at the start of the line. With
            # the code scrolled sideways the arithmetic above lands on a
            # character that is hidden behind the gutter.
            column = 0
        return self._position(row, column, pane.side), pane.side

    def _handle_mouse(
        self, imgui: Any, origin: Any, panes: tuple[_Pane, ...], metrics: DiffMetrics
    ) -> None:
        """Press sets an anchor, drag extends, release finishes."""
        if self._owned and not self.owns_selection:
            # Another view began a selection since this one last did.
            self.clear_selection()
            self._owned = 0

        if self._press:
            self._own()
            self._granularity = granularity_for(
                imgui.get_mouse_clicked_count(imgui.MouseButton_.left)
            )
            pos, side = self._pointed(imgui, origin, panes, metrics, ..., press=True)
            if pos is None:
                self.clear_selection()
                return
            self._anchor = self._extent(pos, self._granularity)
            self._select(*self._anchor, side)
            self._dragging = True
            return

        self._end_a_drag_that_missed_its_release(imgui)
        if not self._dragging or self._anchor is None:
            return
        pos, _ = self._pointed(imgui, origin, panes, metrics, self._side)
        if pos is not None:
            under = self._extent(pos, self._granularity)
            self._select(min(self._anchor[0], under[0]), max(self._anchor[1], under[1]), self._side)
            # A drag past either edge of the code scrolls it.
            pane = next(p for p in panes if p.side == self._side)
            x = imgui.get_mouse_pos().x - origin.x
            if x > pane.x1:
                self._scroll_x = min(self._max_scroll_x, self._scroll_x + 2 * metrics.cell)
            elif x < pane.code:
                self._scroll_x = max(0, self._scroll_x - 2 * metrics.cell)
        if not imgui.is_mouse_down(imgui.MouseButton_.left):
            self._dragging = False

    def _handle_keys(self, imgui: Any) -> None:
        """Ctrl+C and Ctrl+A, for the view that owns the selection and no text input."""
        if not self.owns_selection:
            return
        io = imgui.get_io()
        if io.want_text_input or not io.key_ctrl:
            return
        if imgui.is_key_pressed(imgui.Key.a, False):
            self._dragging = False
            self._select_all(None)
        if imgui.is_key_pressed(imgui.Key.c, False) and self._selection is not None:
            if self._selection[0] != self._selection[1]:
                copied = self._copied()
                if copied:  # nothing to copy: what the clipboard holds stays
                    imgui.set_clipboard_text(clipboard_text(copied))

    def handle_keys(self) -> None:
        """
        Answer Ctrl+C and Ctrl+A on a frame this view is **not** drawn.

        The keys are read in `draw`. A host that culls the view -- it has
        scrolled out of the window -- stops calling `draw`, and the view
        still owns the selection the user made in it: Ctrl+C then did
        nothing at all (review 2, item 7). Call this instead of `draw` on
        those frames, never as well as. `BareView` does, for a diff it hosts
        (`HostedDiff.handle_keys`).
        """
        from imgui_bundle import imgui

        self._handle_keys(imgui)

    def _handle_wheel(self, imgui: Any, metrics: DiffMetrics) -> None:
        io = imgui.get_io()
        wheel = float(io.mouse_wheel_h)
        if io.key_shift:
            wheel += float(io.mouse_wheel)
        if wheel:
            step = int(snap_px(wheel * 4 * metrics.cell))
            self._scroll_x = max(0, min(self._max_scroll_x, self._scroll_x - step))

    def _scrollbar(
        self,
        imgui: Any,
        origin: Any,
        width_px: float,
        top: float,
        bar: int,
        panes: tuple[_Pane, ...],
    ) -> None:
        """
        The horizontal scrollbar: under the code of the first pane to the
        view's right edge, along the bottom of what the window shows of it.
        """
        overflow = self._max_scroll_x
        left = origin.x + panes[0].code
        track = max(1.0, origin.x + width_px - left)
        view = float(self._code_width(panes))
        thumb = max(float(bar), track * view / (view + overflow))
        travel = max(1.0, track - thumb)
        imgui.set_cursor_screen_pos(imgui.ImVec2(left, top))
        imgui.invisible_button(f"##advtext-diff-bar-{id(self):x}", imgui.ImVec2(track, float(bar)))
        mouse = imgui.get_mouse_pos().x
        if imgui.is_item_activated():
            at = left + travel * self._scroll_x / overflow
            if not at <= mouse <= at + thumb:
                # A press on the track: the thumb comes to the mouse first.
                self._scroll_x = int(
                    snap_px(max(0.0, min(1.0, (mouse - left - thumb / 2) / travel)) * overflow)
                )
            self._bar_drag = (mouse, self._scroll_x)
        if imgui.is_item_active() and self._bar_drag is not None:
            start, was = self._bar_drag
            moved = (mouse - start) * overflow / travel
            self._scroll_x = int(snap_px(max(0.0, min(float(overflow), was + moved))))
        elif not imgui.is_item_active():
            self._bar_drag = None
        at = left + travel * self._scroll_x / overflow
        grab = (
            imgui.Col_.scrollbar_grab_active
            if imgui.is_item_active()
            else (
                imgui.Col_.scrollbar_grab_hovered
                if imgui.is_item_hovered()
                else imgui.Col_.scrollbar_grab
            )
        )
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            imgui.ImVec2(left, top),
            imgui.ImVec2(left + track, top + bar),
            imgui.get_color_u32(imgui.Col_.scrollbar_bg),
        )
        draw_list.add_rect_filled(
            imgui.ImVec2(math.floor(at), top + 1),
            imgui.ImVec2(math.floor(at + thumb), top + bar - 1),
            imgui.get_color_u32(grab),
            float(bar) / 2,
        )


# ----------------------------------------------------------------------
# A diff inside a document
# ----------------------------------------------------------------------

FENCE_LANGUAGES = ("diff", "patch")
"""
The first words of a fence's info string that `DiffFences` takes for a diff.
"""


class HostedDiff:
    """
    One fenced diff as a document view holds it: an `advtext.ui.Hosted` around a `DiffView`.

    `view` is the `DiffView`, for a host that wants to drive it. `text` is the
    fence's body as read so far.
    """

    __slots__ = ("__weakref__", "fence", "stream", "view")

    def __init__(self, view: DiffView) -> None:
        self.view = view
        self.stream = UnifiedDiffStream()
        # How far `DiffFences` has read this fence. Kept here, on the object
        # the document view holds for the block, and not in a table of the
        # `DiffFences`: it then lives exactly as long as the view shows it.
        self.fence: _Fence | None = None

    def height_for(self, width_px: float) -> float:
        return self.view.height_for(width_px)

    def draw(
        self, *, fonts: FaceFont, palette: Palette | None = None, width_px: float | None = None
    ) -> DrawStats:
        return self.view.draw(fonts=fonts, palette=palette, width_px=width_px)

    def handle_keys(self) -> None:
        """What the outer view calls on a frame the diff is out of the window."""
        self.view.handle_keys()

    @property
    def text(self) -> str:
        return self.stream.text


@dataclass(slots=True)
class _Fence:
    """
    How far into one fence's source `DiffFences` has read.

    `start` is where the fence's first line begins in the source and `opener`
    is that line; together they are how the same fence is known again. `fed`
    is the offset of the first character not yet read, or -1 while the
    opening line has not ended. `plain` marks a fence read from its code
    block because its source could not be.
    """

    hosted: HostedDiff
    start: int = -1
    opener: str = ""
    fed: int = -1
    indent: int = 0
    mark: str = ""
    closed: bool = False
    plain: bool = False


class DiffFences:
    """
    A `BareView.host_for` that draws fenced `diff` and `patch` blocks as diffs.

    The module docstring ("A diff inside a document") is the contract. The
    keyword arguments are `DiffView`'s and are given to each view as it is
    made; `layout`, `height_cap` and `syntax` may be changed afterwards and
    apply to the fences met from then on (`set_layout` also switches the ones
    already made).

    One instance serves any number of views: what it keeps is per view and
    per block number.
    """

    def __init__(
        self,
        *,
        source: str | Callable[[], str] | None = None,
        languages: Sequence[str] = FENCE_LANGUAGES,
        layout: DiffLayout = DiffLayout.UNIFIED,
        height_cap: float | None = None,
        syntax: SyntaxColour | None = None,
        pixel_height: float | None = None,
        metrics: MetricsResolver = fontlib_metrics,
        expand_step: int = 20,
    ) -> None:
        self.source = source
        self.languages = tuple(word.lower() for word in languages)
        self.layout = layout
        self.height_cap = height_cap
        self.syntax = syntax
        self.pixel_height = pixel_height
        self.metrics = metrics
        self.expand_step = expand_step
        #: Diff lines read from fences, ever: one per line of a fence's body.
        self.fed_lines = 0
        #: Times a fence was read again from its first line.
        self.restarts = 0
        # Every hosted diff made and still held by some view. Weak: a view
        # that is gone takes its diffs with it. (They were in a dict keyed by
        # `id(view)`, which was never pruned and could name a later view that
        # happened to get the same id.)
        self._made: weakref.WeakSet[HostedDiff] = weakref.WeakSet()

    # -- what a host reaches for ------------------------------------------

    def view_of(self, view: BareView, number: int) -> DiffView | None:
        """
        The `DiffView` drawing block `number` of `view`, or `None` if that block is not a diff.
        """
        hosted = view.hosted(number)
        if isinstance(hosted, HostedDiff) and hosted in self._made:
            return hosted.view
        return None

    @property
    def live(self) -> int:
        """How many hosted diffs this has made that some view still holds."""
        return len(self._made)

    def set_layout(self, layout: DiffLayout) -> None:
        """
        Unified or side by side, for every diff made so far and every one made later.
        """
        self.layout = layout
        for hosted in list(self._made):
            hosted.view.set_layout(layout)

    def accepts(self, block: Block) -> bool:
        """
        Whether `block` is a fence this draws: a code block whose info string begins with one
        of `languages`.
        """
        if not isinstance(block, CodeBlock):
            return False
        words = block.language.split(None, 1)
        return bool(words) and words[0].lower() in self.languages

    # -- the hook ------------------------------------------------------------

    def __call__(self, view: BareView, number: int, block: Block) -> HostedDiff | None:
        if not self.accepts(block):
            return None
        assert isinstance(block, CodeBlock)
        stream = getattr(view, "stream", None)
        source = self._source_of(stream)
        where = view.document.source_of(number) if source is not None else None
        known = view.hosted(number)
        fence = known.fence if isinstance(known, HostedDiff) and known in self._made else None

        if source is not None and where is not None:
            span = where.span
            if (
                fence is None
                or fence.plain
                or fence.start != span.start
                or fence.fed > span.end
                or not source.startswith(fence.opener, span.start)
            ):
                if fence is not None:
                    self.restarts += 1
                fence = _Fence(self._hosted(view), start=span.start)
            # Whether this is all the fence will ever be: then a last line
            # with no newline is a line, and not one still being typed.
            final = stream is None or stream.closed or number < len(stream.committed)
            self._read(fence, source, span.end, final)
            if final or fence.closed:
                # Nothing more will come: a last line the parser was holding
                # for the line after it (`UnifiedDiffStream.close`) is settled.
                fence.hosted.stream.close()
        if fence is None or fence.plain or source is None or where is None:
            # No source to cut from: the code block's own lines, whole, every
            # time. Tabs are spaces in these.
            if fence is None or not fence.plain:
                fence = _Fence(self._hosted(view), plain=True)
            text = material_text(block).text
            text = text + "\n" if text else ""
            before = fence.hosted.stream.text
            fence.hosted.stream.set_text(text)
            self.fed_lines += text.count("\n") - (
                before.count("\n") if text.startswith(before) else 0
            )
        fence.hosted.fence = fence
        self._made.add(fence.hosted)
        fence.hosted.view.set_diff(fence.hosted.stream.diff)
        return fence.hosted

    def _source_of(self, stream: object) -> str | None:
        if stream is not None:
            text = getattr(stream, "source", None)
            if isinstance(text, str):
                return text
        if callable(self.source):
            return self.source()
        return self.source

    def _hosted(self, view: BareView) -> HostedDiff:
        return HostedDiff(
            DiffView(
                Diff(),
                view.theme,
                layout=self.layout,
                pixel_height=self.pixel_height,
                px_per_inch=view.px_per_inch,
                metrics=self.metrics,
                syntax=self.syntax,
                height_cap=self.height_cap,
                expand_step=self.expand_step,
            )
        )

    def _read(self, fence: _Fence, source: str, end: int, final: bool) -> None:
        """
        Feed the fence's lines in `source[fence.fed:end]` to its diff, whole lines only.

        The opening line is read first, once it has ended: its indentation is
        what every later line loses (CommonMark's rule for an indented fence),
        and its run of backticks or tildes is what a closing line must match.
        A line is fed when its newline is in the source -- or, if `final`,
        when it is the last thing there.
        """
        if fence.fed < 0:
            stop = source.find("\n", fence.start, end)
            if stop < 0:
                return
            opener = source[fence.start : stop]
            bare = opener.lstrip(" ")
            mark = bare[:1]
            if mark not in ("`", "~") or not bare.startswith(mark * 3):
                # Not a fence on a line of its own: a list marker or a quote
                # mark comes first, and stripping those is markdown's job.
                fence.plain = True
                return
            fence.opener = opener
            fence.indent = len(opener) - len(bare)
            fence.mark = mark * (len(bare) - len(bare.lstrip(mark)))
            fence.fed = stop + 1
        if fence.closed or fence.fed >= end:
            return
        chunk = source[fence.fed : end]
        if not final:
            chunk = chunk[: chunk.rfind("\n") + 1]
        if not chunk:
            return
        fence.fed += len(chunk)
        lines: list[str] = []
        # Cut at "\n" and nowhere else, as `advtext.diff` cuts: `splitlines`
        # also cuts at a form feed, U+2028 and five more, and a diff line
        # holding one became two.
        pieces = chunk.split("\n")
        tail = pieces.pop()
        cut = [piece + "\n" for piece in pieces] + ([tail] if tail else [])
        for at, line in enumerate(cut):
            body = line
            for _ in range(fence.indent):
                if not body.startswith(" "):
                    break
                body = body[1:]
            closing = body.strip()
            if (
                closing.startswith(fence.mark)
                and not closing.strip(fence.mark[0])
                and len(line) - len(line.lstrip(" ")) < fence.indent + 4
                and at == len(cut) - 1
                and fence.fed >= end
            ):
                # It looks like the closing fence, and it is the last line of
                # the block's source: markdown, which has already decided
                # where the block ends, is the judge of whether it *is*. A
                # run of backticks with lines of the block after it was not
                # the closing fence (it was indented too far, say), whatever
                # it looks like, and is a line of the diff. While the block
                # is still being written the line is neither: it is read
                # again when more has arrived.
                if final:
                    fence.closed = True
                else:
                    fence.fed -= len(line)
                break
            lines.append(body)
        if lines:
            self.fed_lines += len(lines)
            fence.hosted.stream.feed("".join(lines))

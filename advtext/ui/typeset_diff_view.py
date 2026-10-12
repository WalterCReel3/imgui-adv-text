r"""
The diff view again, set and drawn by imtypeset: `TypesetDiffView`.

**Experimental** (branch `experimental/imtypeset-adoption`, tasks SW-3, T3-C
and T4-DIFF of the swap build). `advtext.ui.diff_view.DiffView` builds glyph commands itself and
hands them to advtext's own ImGui backend; this draws the same `advtext.diff`
model through `imtypeset.Document`s and Dear ImGui's own rectangles, and calls
nothing of advtext's layout core. Nothing in advtext imports this module: a
host asks for it by name, beside `advtext.typesetter`, and falls back to
`DiffView` when it raises `advtext.ui.typeset_view.TypesetUnavailable`.

Two classes:

- `DiffRows` is everything that needs neither the library nor Dear ImGui: the
  display rows of a `Diff` in a layout, hunk navigation, expanding collapsed
  context, the selection as positions in the model and what a copy of it
  returns, and the description of the rows as blocks of text. **Lifted from
  `DiffView`**, not imported from it: importing `advtext.ui.diff_view` loads
  advtext's layout core (measured: see `tests/test_typeset_diff_view.py`),
  which the swap is removing. The rules are `DiffView`'s, and the tests hold
  the two to the same rows and the same copies.
- `TypesetDiffView(DiffRows)` adds the documents, the frame and the input.

A diff inside a document (a fenced `diff` block of a `TypesetView`) is
`advtext.ui.typeset_hosts.TypesetDiffFences`, which makes these views; there is
no fence reader in this module.

## When it can be used

As `TypesetView`: the constructor raises `TypesetUnavailable` naming
`typesetter.reason()` when `typesetter.module()` is `None`; `draw`,
`height_for`, `content_width` and `grid` raise it when `typesetter.ready()` is
false (the width of a cell is asked of the library, so nothing that needs a
width can be answered without it), and `draw` raises it when the library fails
mid-draw, having called `typesetter.disable(why)`. `draw` checks readiness and
hands the description over **before** it opens the `height_cap` child window,
so the usual refusals leave the cursor and ImGui's stacks as the host had
them. A failure later in the frame can leave that frame's bands on the draw
list and, with `height_cap`, the child submitted.

**Only the library's own failure switches it off.** What `draw` catches is
sorted by whose it is (`_library_failed`): an exception the `imtypeset`
package defines becomes `TypesetUnavailable` after `typesetter.disable`;
anything else -- an error of the model's, of a host's highlighter or `copy_as`,
a slip in this module -- leaves `draw` as itself, the library still in use,
the clip rectangles popped and the `height_cap` child ended.

## The shape (`.concerns/FS-S1--builder--result.md` found it)

Per pane -- one unified, two side by side -- a **code** `Document` and a
**gutter** `Document`, both `CodeOverflow.Grow` (no line is ever wrapped). A display row is one line
of a `BlockKind.Code` block, and every document of the view has the same
blocks with the same number of lines, so one table says which block and line a
row is. A block is a file header, a collapsed-context row, a hunk header, a
fold row, or at most `CHUNK` (64) rows of a hunk. `BlockStyle.LineHeight`
with `BlockFlags.FixedLineHeight` on every block puts every line on a pitch of
`row` whole pixels whatever it holds, so row `n` is at `n * row` in every
document and is found by division, as in `DiffView`. `content_height` is
`row_count * row_px`: `DiffView`'s, exactly.

- Bands (added, removed, headers), the bar beside the current hunk and the
  horizontal scrollbar are Dear ImGui's own rectangles.
- The gutter document does not scroll sideways; the code document is drawn at
  `x - scroll_x` under a clip. Header rows (file, hunk, gap, fold) are text of
  the **first pane's gutter document**, which is clipped to the whole view and
  not to its gutter: they span the view and do not scroll, as `DiffView`'s do.
- Row ink (added, removed, meta), the host's syntax colours, placeholders and
  the intra-line emphasis are `imtypeset.Mark`s, built and packed **for the
  rows in view only**, and again only when those rows, the selection, the
  palette or the highlighter change. The selection is marks too
  (`MarkPlace.Behind`), one per row, because the highlight leaves out rows a
  copy would leave out, which one range cannot say.
- An empty line is handed over as one space: a Code block drops blank lines
  at its end.

Calls into the library per frame: `layout` and `draw` for each document --
**4 unified, 8 side by side** -- plus one `hit_test` on a frame with a press
or a drag in progress. `draw` is `Document.draw(None, pos)`: no draw list is
the current window's, so nothing here finds one. Not per frame: an edit
(`set_diff`, `expand`, a layout switch, rows coming into the window for the
first time) is one `replace_blocks` per document, over the blocks that
differ; the first draw makes the documents and measures a cell (once per
size). `tests/test_typeset_diff_view.py` counts them in a window.

## What is described, and when (T3-C)

SW-3 turned every row into text before the first frame, and all of them again
for each `set_diff`: measured 2.3 to 3.6 times `DiffView`'s first frame on a
4,850-row diff. Now:

- **Which rows are in which block is worked out for the whole diff** (so every
  block is where it will be and row `n` is still found by division), but **the
  text of a block of hunk rows is made when rows of it come into the window**
  (`DiffRows._realise`). Until then the block is that many lines of one space
  in every document: the same height. Header rows are text from the start.
  `draw` works out the rows it will
  show before it hands anything over, so a frame is still one edit a document;
  with `height_cap` (a child whose scroll is not known until it is begun) it
  goes by the rows last shown and hands over once more if that missed.
  `blocks_realised` counts the times.
- **A hunk is read a row at a time** (`_info`, `DiffView`'s rule): one that
  grew is read from where it stopped.
- **A diff described again keeps the blocks of every hunk that is the same
  object** (`_describe`), with whatever text they have: after `expand`, the
  hunks beside the gap are described; after a line of a stream, the open hunk.
  The open hunk itself is described again whole (stand-ins, and the text of
  what is in the window): an end-of-line mark or a side-by-side
  pairing of an earlier row can change when a later row arrives, and nothing
  here tries to prove it did not.
- Nothing is ever turned back into a stand-in while its hunk lives, so a diff
  scrolled from end to end holds what SW-3's held.

## A glyph taller than the pitch, or not the code face's

Until the library had `BlockFlags.FixedLineHeight` (its commit `be40444`) a
line was AT LEAST its pitch, and one holding a taller glyph moved every row
below it in the one document holding it. This module then measured every line
with a character above U+007E in a scratch document, gave each a block of its
own, made its row a whole pixel taller in every document (`SpaceBelow`), kept a
table of tall rows, and reported them (`off_grid`, `extra_height`,
`lines_measured`, `placeholder_off_grid`). **All of that is gone**: with the
flag a line is its pitch, asked or not, laid out or not (measured at 13, 16 and
24 px: `.concerns/T4-DIFF-scripts/probe_fixed.out.json`).

What is still true of such a line, measured with the bundled faces at 16 px on
a 20 px pitch:

- **Its ink overhangs its row.** U+2502 -- which the bundled code face HAS
  (`face_has_glyph` says so; the earlier text here called it borrowed, wrongly)
  -- is 22.4 px tall as set, U+4E2D 21.9: the quads reach 2 px above the row
  and 1 px below. Nothing moves; the band of the row above or below is under
  that ink.
- **The library can leave that overhang undrawn in the strip at the window's
  edge**, when the line's row is just outside the clip rectangle and only the
  overhang is inside it (its header at `ImTypesetBlockFlags_FixedLineHeight`).
  Observed here once, at the level of quads, in headless frames
  (`.concerns/T4-DIFF-scripts/probe_overhang.out.json`): with the window's
  clip ending exactly at the top of the row holding them, the quad of U+4E2D
  (2 px of it inside the clip) was emitted and the quad of U+2502 (1 px) was
  not; with the clip a pixel into the row, or a pixel above it, every quad
  that reached into the clip was emitted. Nobody has looked at pixels.
- **A character the code face lacks is set from another face at that face's
  advance**, so on that line, and only there, columns to its right are not on
  the cell grid (`DiffView` draws the glyph in its own cell and lets it
  overlap): U+4E2D is 16.4 px wide for an 8 px cell. Nothing is substituted.
  Hit testing, marks and the selection on that line are the library's and stay
  right. `code_face_lacks(text)` says which characters of a text these are
  (U+03C0 and U+0416 are, in the bundled code face; U+2502 and U+FFFD are not).
- A character **no** face has is whatever the library draws for it; `DiffView`
  draws a placeholder there. `face_has_glyph` over every role could tell
  (U+4E2D is in none of the bundled faces); nothing here asks.

## What is `DiffView`'s, kept

`DiffLayout.UNIFIED` / `SIDE_BY_SIDE` and `set_layout` (the top row is kept);
`set_diff` by identity; `row_count`, `row_info`, `row_of`, `row_of_hunk`,
`top_row`, `scroll_to_row`, `visible_rows`, `origin`; `next_hunk`,
`previous_hunk`, `current_hunk`; `expand`, `expand_step`, and the click on an
expandable collapsed-context row (Shift: from the bottom); `height_cap` and
`height_for`; `content_width`, `content_height`, `scroll_x`, Shift+wheel, the
scrollbar, a drag past the edge; `syntax` and its three counters; file headers
with their state, `will_not_apply`, unread lines and character warnings; the
`+`/`-` marker always drawn; control and invisible characters as
`CONTROL_PLACEHOLDER` in the warning ink (the copy returns the real one);
end-of-line marks; the folded line-endings file and `show_line_endings`; files
shown as written (`dialect`); the selection -- press, drag, double and triple
click, Ctrl+A, Ctrl+C, `select`, `select_all`, `selected_text`, `copy`,
`copy_as`, `copy_removed_lines`, `handle_keys`, one owner per process
(`advtext.ui.ownership.SELECTION_OWNERSHIP`, the counter `DiffView` uses) --
and the no-item-while-idle rule (`dummy`; an `invisible_button` from a press
to its release).

## What is different, and what has no counterpart

- **`DiffLayout` and `RowInfo` here are this module's own classes** with the
  same values and fields, since `DiffView`'s live in a module that loads the
  core. A layout is accepted from either enum; `row_of` reads attributes, so
  a `RowInfo` of `DiffView`'s works here and one of these works there.
- **`draw` returns a `bool`** (everything in view was set as asked), not a
  `DrawStats`; `fonts=` is accepted and ignored.
- **`grid`** (a `DiffGrid`) stands for `metrics_px`. **The cell is the code
  face's own advance, not a whole pixel**: 8.0 px at the theme's 16 px, and
  6.196 px at `pixel_height=13` where `DiffView` draws on 6 (both measured in
  a window). Pane edges are rounded to a pixel.
- `metrics=` (a `MetricsResolver`) is not taken. `pixel_height` is, and
  imports `advtext.fontlib` when given: the one place this module asks the
  old core for anything (a face's line metrics from the library would remove
  it). The theme is `advtext.theme`'s, which loads `fontmetrics` and `units`
  for its own purposes; nothing here calls them.
- A character the code face lacks is not in its own cell, and a glyph taller
  than the pitch is not cut to it (above).
- The selection highlight does not extend one cell past the end of a line
  that is selected through its end; a selected empty line shows one cell.
- A file shown as written is clipped to the first pane side by side
  (`DiffView` gives it the whole width).
- A grown model (a stream): the hunks that are the same objects keep their
  blocks and the open hunk is described again ("What is described, and
  when"); `DiffView` measures only the new rows.
- No `frame_plan` / `FramePlan` / `Region` (they are draw commands of the old
  backend), no `measured_rows`, no `plans_built` (`marks_built`,
  `blocks_realised` and `edits` count what is done here).
- `DiffFences` / `HostedDiff` are `TypesetDiffFences` / `HostedDiff` of
  `advtext.ui.typeset_hosts`.

## What has and has not been run

`tests/test_typeset_diff_view.py`: the pure half without the library; with
it, in a real window through `hello_imgui`, both layouts against what
`DiffView` answers on the same diffs (asked of it while it exists, and frozen
in `tests/data/diff_view_answers.json` for when it does not), with mouse and
key events queued through `io.add_*_event`. In a window too:
`handle_keys` on a frame the view is not drawn (as a diff hosted in a
`TypesetStreamView` and scrolled out of it: `tests/test_typeset_hosts.py`),
and `copy_as` (the Diff page's, in the application:
`tests/test_page_diff.py`). Not run in a window: a real pointer, a window
manager, a drag past the edge of the code (the scroll it causes) or past the
window's (the rows it reaches are made into text then: read, not run), a
highlighter that raises, a second `load_fonts()` after `unload()` (the
documents are made again: read, not run). Sizes run: 16 px, and 13 px for
rows, the cell and one press. Nobody has looked at what it draws: the tests
count vertices and compare positions, rows and text.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, NoReturn

from advtext import typesetter
from advtext.diff import (
    Diff,
    DiffRow,
    FileDiff,
    FileStatus,
    Hunk,
    RowKind,
    has_control,
    has_invisible,
    tokenize,
)
from advtext.ui.ownership import SELECTION_OWNERSHIP, clipboard_text
from advtext.ui.palette import DEFAULT_PALETTE, Palette
from advtext.ui.typeset_view import TypesetUnavailable, library_failed, raise_failed

if TYPE_CHECKING:
    from advtext.theme import Theme

__all__ = [
    "CHUNK",
    "CONTROL_PLACEHOLDER",
    "COPY_GAP",
    "SYNTAX_CHUNK",
    "TAB_WIDTH",
    "DiffGrid",
    "DiffLayout",
    "DiffRows",
    "RowInfo",
    "SyntaxColour",
    "TypesetDiffView",
    "code_face_lacks",
    "code_size",
    "language_for",
]

CONTROL_PLACEHOLDER = "�"
"""What stands, in the warning ink, for a control or an invisible character: `DiffView`'s."""

COPY_GAP = "…"
"""The line a copy puts between two pieces that are not adjacent in the file: `DiffView`'s."""

#: The most lines of one side of one hunk handed to `syntax` in one call.
SYNTAX_CHUNK = 200

#: The most rows in one block. FS-S1 measured one block per hunk not to scale.
CHUNK = 64

#: Columns a tab advances to the next multiple of: `advtext.markdown.TAB_WIDTH`
#: and the library's own for a Code block (a test holds the three together).
TAB_WIDTH = 4

SyntaxColour = Callable[[Sequence[str], str], Sequence[Sequence[tuple[int, int, int]]]]
"""A host's highlighter: `(lines, language)` to `(start, end, colour)` spans per line."""

_EOL_MARKS = {"\r\n": "\\r\\n", "\n": "\\n", "\r": "\\r"}
_SNAP_REACH = 4096
_PT_PER_INCH = 72.27
# The column every document is laid out at. Lines are never wrapped (`CodeOverflow.Grow`)
# and are clipped by Dear ImGui's clip rectangle, so the column only has to be the same
# from frame to frame: a change of it lays the document out again.
_COLUMN = 4096.0
_UNITY = 1 << 16

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
    """A language name guessed from a file label, as `advtext.ui.diff_view.language_for`."""
    name = label.rsplit("/", 1)[-1]
    if "." not in name:
        return {"makefile": "make", "dockerfile": "dockerfile"}.get(name.lower(), "")
    extension = name.rsplit(".", 1)[1].lower()
    return _LANGUAGES.get(extension, extension)


class DiffLayout(Enum):
    """The two layouts. The values are `advtext.ui.diff_view.DiffLayout`'s."""

    UNIFIED = "unified"
    SIDE_BY_SIDE = "side-by-side"


def _layout(given: Any) -> DiffLayout:
    """`given` as this module's enum: a member of it, of `DiffView`'s, or a value."""
    if isinstance(given, DiffLayout):
        return given
    return DiffLayout(getattr(given, "value", given))


@dataclass(frozen=True, slots=True)
class RowInfo:
    """What one display row is: the fields of `advtext.ui.diff_view.RowInfo`."""

    kind: str
    file: int
    hunk: int | None = None
    left: int | None = None
    right: int | None = None


@dataclass(frozen=True, slots=True)
class DiffGrid:
    """
    The grid the view draws on. `row` is whole pixels; `cell` is the code
    face's advance as the library sets it, which need not be. `em` and `scale`
    are the document style's em and the code face's size as a multiple of it.
    """

    cell: float
    row: int
    em: float
    scale: float


_Pos = tuple[int, int, int, int]

_FILE, _GAP, _HUNK, _ROWS, _FOLD, _RAW = range(6)
_KIND_NAMES = {_FILE: "file", _GAP: "gap", _HUNK: "hunk", _FOLD: "fold", _RAW: "raw"}

# The ink a block is set in (`BlockStyle.Color`); a mark changes it for a range.
_R_CODE, _R_HEADER, _R_META, _R_GUTTER = range(4)

_CHARACTER, _WORD, _LINE = range(3)


def _px(length: float, px_per_inch: float) -> float:
    """Scaled points to pixels: `advtext.primitives.px_from_sp`'s arithmetic."""
    return length * (px_per_inch / _PT_PER_INCH) / _UNITY


def _columns(text: str, tab: int = TAB_WIDTH) -> list[int] | None:
    """The cell each character starts in, one more for the end; `None` with no tab."""
    if "\t" not in text:
        return None
    out = [0]
    for character in text:
        at = out[-1]
        out.append(at + tab - at % tab if character == "\t" else at + 1)
    return out


def _width(text: str) -> int:
    """How many cells `text` takes."""
    cells = _columns(text)
    return len(text) if cells is None else cells[-1]


def _shown(text: str) -> tuple[str, tuple[int, ...]]:
    """
    `text` as handed to the library, and the offsets that hold a placeholder.

    One character for one, so an offset into one is an offset into the other.
    Tabs stay tabs: the library sets them to `TAB_WIDTH` columns.
    """
    if text.isascii() and text.isprintable():
        return text, ()
    return _shown_slowly(text)


@lru_cache(maxsize=4096)
def _shown_slowly(text: str) -> tuple[str, tuple[int, ...]]:
    """`_shown` for a text with a tab, a control or anything outside ASCII, remembered."""
    out: list[str] = []
    marked: list[int] = []
    for at, character in enumerate(text):
        if character == "\t" or " " <= character <= "~":
            out.append(character)
        elif has_control(character) or has_invisible(character):
            out.append(CONTROL_PLACEHOLDER)
            marked.append(at)
        else:
            out.append(character)
    return "".join(out), tuple(marked)


_BLANKS: dict[int, str] = {}


def _blank(count: int) -> str:
    """
    `count` lines of one space: what stands for the rows of a block until they
    are near the window. One object per count, so two of them compare at once.
    """
    text = _BLANKS.get(count)
    if text is None:
        text = _BLANKS[count] = "\n".join([" "] * count)
    return text


def _line_starts(lines: Sequence[str]) -> list[int]:
    """Where each line starts in the lines joined by a newline."""
    starts: list[int] = []
    at = 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    return starts


_library_failed = library_failed
"""`advtext.ui.typeset_view.library_failed`: the rule was this module's first and is shared now."""


def _git_state(header: Sequence[str]) -> str:
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


def _file_header(file: FileDiff) -> tuple[str, str]:
    """A file header's text, and the part after it that is a warning: `DiffView`'s."""
    if file.dialect:
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
        count = len(file.unread)
        warning += f"  ! {count} line{'s' if count != 1 else ''} not read as part of the diff"
    warning += _character_warning(file)
    return text + state, warning


def _fold_text(file: FileDiff) -> str:
    rows = sum(1 for h in file.hunks for r in h.rows if r.kind is not RowKind.META)
    return f"... {rows} rows differ only in how the line ends  (click to show them)"


def _gap_text(file: FileDiff, gap: int) -> str:
    found = file.gaps[gap]
    lines = "1 unchanged line" if found.count == 1 else f"{found.count} unchanged lines"
    return f"... {lines}" + ("  (click to show more)" if found.expandable else "")


def _code_line(hunk: Hunk, at: int) -> tuple[str, tuple[int, ...], int]:
    """
    Row `at` of a hunk as the code document holds it: the text, the offsets
    holding a placeholder, and where an end-of-line mark starts (-1: none).
    """
    shown, marked = _shown(hunk.rows[at].text)
    if at in hunk.eol_rows:
        ending = _EOL_MARKS.get(hunk.terminator(at), "")
        if ending:
            return f"{shown} {ending}", marked, len(shown) + 1
    return shown, marked, -1


@dataclass(slots=True)
class _HunkInfo:
    """
    What is worked out about a hunk, a row at a time: its width in cells and
    its two sides. `advtext.ui.diff_view._HunkInfo`.

    `count` rows have been read. `recent` is the last few of them, each with
    what stood before it was read -- (row, columns, old, new) -- so that the
    rows a stream takes back can be taken back out.
    """

    columns: int = 0
    old: list[int] = field(default_factory=list)
    new: list[int] = field(default_factory=list)
    place: list[tuple[int, int]] = field(default_factory=list)
    count: int = 0
    recent: list[tuple[DiffRow, int, int, int]] = field(default_factory=list)


@dataclass(slots=True, eq=False)
class _Index:
    """The display rows of one diff in one layout, as segments. Compared by identity."""

    diff: Diff
    layout: DiffLayout
    segments: list[tuple[int, int, int, int]]  # (kind, file, hunk or gap, rows)
    starts: list[int]
    total: int
    columns: int
    digits: tuple[int, int]
    hunks: list[tuple[int, int, int]]  # (display row of the header, file, hunk)


@dataclass(slots=True, eq=False)
class _Sheet:
    """
    The rows as the documents hold them. Documents are numbered gutter then
    code per pane (`2 * pane`, `2 * pane + 1`); all have the same blocks.

    Which rows are in which block is worked out for the whole diff; the TEXT
    of a block of hunk rows is not, until `DiffRows._realise` is asked for
    rows in it. Until then the block is in `lazy`, its text in every document
    is that many lines of one space (the same height, so every block is where
    it will be) and its `starts` are `None`. Header rows are text from the
    start. `dirty` is set by whatever changes a text here.
    """

    index: _Index
    panes: int
    texts: list[list[str]]  # [document][block]
    styles: list[list[int]]  # [document][block]: the block's role (`_R_CODE` ...)
    first_row: list[int] = field(default_factory=list)  # [block]
    row_block: list[int] = field(default_factory=list)  # [row]
    starts: list[list[list[int] | None]] = field(default_factory=list)  # [pane][block][line]
    # A block whose text is not made yet: (kind, file, hunk, first row of the segment, end).
    lazy: dict[int, tuple[int, int, int, int, int]] = field(default_factory=dict)
    # The first block of each segment of the index, and one more: the count.
    segment_blocks: list[int] = field(default_factory=list)
    dirty: bool = True
    # Per header row: the (start, end) ranges of its line set in the warning ink.
    header_inks: dict[int, tuple[tuple[int, int], ...]] = field(default_factory=dict)
    blocks: int = 0


class DiffRows:
    """
    The rows of a `Diff` in a layout, their selection and their description.

    Pure: no library, no Dear ImGui. `TypesetDiffView` is this with a frame.
    `row` is the pitch in whole pixels: every display row is exactly that tall.
    """

    def __init__(
        self,
        diff: Diff,
        *,
        layout: Any = DiffLayout.UNIFIED,
        row: int = 20,
        expand_step: int = 20,
        copy_removed_lines: bool = False,
    ) -> None:
        self.expand_step = expand_step
        self.copy_removed_lines = copy_removed_lines
        self._row_px = max(1, int(row))
        self._source = diff
        self._diff = diff
        self._layout = _layout(layout)
        self._index: _Index | None = None
        self._infos: dict[tuple[int, int], _HunkInfo] = {}
        self._unfolded: set[int] = set()
        self._origin: tuple[float, float] | None = None
        self._scroll_to: int | None = None
        self._keep_top: RowInfo | None = None
        self._top_row = 0
        self._current: tuple[int, int] | None = None
        self._selection: tuple[_Pos, _Pos] | None = None
        self._side: int | None = None
        self._anchor: tuple[_Pos, _Pos] | None = None
        self._ends: tuple[DiffRow, DiffRow] | None = None
        self._kinds: tuple[object, frozenset[RowKind]] | None = None
        self._dragging = False
        self._owned = 0
        self._sheet: _Sheet | None = None

    # ------------------------------------------------------------------
    # The model and the layout
    # ------------------------------------------------------------------

    @property
    def diff(self) -> Diff:
        """The diff being shown: the host's, with whatever context was expanded here."""
        return self._diff

    def set_diff(self, diff: Diff) -> None:
        """Show `diff`. Nothing happens if it is the object last given."""
        if diff is self._source:
            return
        self._unfolded.clear()
        self._source = diff
        self._replace(diff)

    def _replace(self, diff: Diff) -> None:
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
            start, end = self._selection
            if self._row(start) is not self._ends[0] or self._row(end) is not self._ends[1]:
                self.clear_selection()
        if self._current is not None and self._hunk(*self._current) is None:
            self._current = None

    @property
    def layout(self) -> DiffLayout:
        return self._layout

    def set_layout(self, layout: Any) -> None:
        """Switch layout, keeping the row at the top of the window; clears the selection."""
        layout = _layout(layout)
        if layout is self._layout:
            return
        if self._origin is not None and self._indexed().total:
            self._keep_top = self.row_info(min(self._top_row, self._indexed().total - 1))
        self._layout = layout
        self._index = None
        self.clear_selection()

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
        The record of a hunk, brought up to date with its rows:
        `DiffView._info`'s rule. A hunk that grew keeps what was worked out
        for the rows it had -- the check is that the last rows read are still
        the same objects in the same places, which a stream guarantees (it
        takes back only its last few, `Diff.unsettled`) and anything else
        fails, and then the hunk is read from its first row.
        """
        info = self._infos.get((file, number))
        rows = hunk.rows
        if info is not None and info.count:
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
            info = self._infos[(file, number)] = _HunkInfo()
        if info.count == len(rows):
            return info
        for at in range(info.count, len(rows)):
            row = rows[at]
            text = row.text
            info.recent.append((row, info.columns, len(info.old), len(info.new)))
            if row.kind is RowKind.META:
                width = _width(rows[at - 1].text) + 3 if at else 0
            else:
                width = _width(text)
                if row.eol != "\n":
                    width += 5  # room for a `\r\n` mark, should it be drawn
            if width > info.columns:
                info.columns = width
            a = b = -1
            if row.kind in (RowKind.CONTEXT, RowKind.REMOVE):
                a = len(info.old)
                info.old.append(at)
            if row.kind in (RowKind.CONTEXT, RowKind.ADD):
                b = len(info.new)
                info.new.append(at)
            info.place.append((a, b))
        info.count = len(rows)
        del info.recent[:-4]
        return info

    def _folded(self, f: int) -> bool:
        files = self._diff.files
        return f < len(files) and bool(files[f].line_endings) and f not in self._unfolded

    def line_endings_shown(self, file: int) -> bool:
        """Whether the rows of a line-endings-only file are being shown."""
        return file in self._unfolded

    def show_line_endings(self, file: int, shown: bool = True) -> None:
        """Show (or fold away again) the rows of a file that differs only in line endings."""
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
                    columns = max(columns, max(_width(line) for line in file.raw))
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
        for gone in [key for key in self._infos if key not in seen]:
            del self._infos[gone]
        starts: list[int] = []
        at = 0
        for segment in segments:
            starts.append(at)
            at += segment[3]
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
        if kind in (_FILE, _FOLD):
            return RowInfo(_KIND_NAMES[kind], file)
        if kind in (_GAP, _HUNK):
            return RowInfo(_KIND_NAMES[kind], file, number)
        if kind == _RAW:
            return RowInfo("raw", file, None, offset, offset)
        if self._layout is DiffLayout.UNIFIED:
            return RowInfo("row", file, number, offset, offset)
        pair = self._diff.files[file].hunks[number].side_by_side[offset]
        return RowInfo("row", file, number, pair.left, pair.right)

    def row_of(self, info: Any) -> int:
        """
        The display row that shows `info` in the current layout, or failing
        that the nearest row before where it would be. `info` is a `RowInfo`
        of this module's or of `DiffView`'s.
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
            target = info.left if info.left is not None else info.right
            if info.kind != "row" or target is None:
                return start
            hunk = self._diff.files[file].hunks[number]
            if self._layout is DiffLayout.UNIFIED:
                return start + min(int(target), len(hunk.rows) - 1)
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
    # Height, which needs no library
    # ------------------------------------------------------------------

    @property
    def row_px(self) -> int:
        """The pitch: how tall every row is, in whole pixels."""
        return self._row_px

    @property
    def content_height(self) -> float:
        """
        The height of every row, in pixels, without the horizontal scrollbar:
        `row_count * row_px`, which is `DiffView.content_height`.
        """
        return float(self._indexed().total * self._row_px)

    def row_top(self, row: int) -> float:
        """Where display row `row` begins, in pixels below the view's top."""
        return float(row * self._row_px)

    @property
    def origin(self) -> tuple[float, float] | None:
        """Where the view's top-left was on screen at the last `draw`."""
        return self._origin

    # ------------------------------------------------------------------
    # Hunks, for a host's keys
    # ------------------------------------------------------------------

    @property
    def current_hunk(self) -> tuple[int, int] | None:
        """The (file, hunk) `next_hunk`/`previous_hunk` is on, or `None`."""
        return self._current

    @property
    def top_row(self) -> int:
        """The display row at the top of the window at the last `draw`; assignable."""
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
            rows = [row for row, _, _ in hunks]
            below = bisect_right(rows, self._top_row - 1)
            at = min(below, len(keys) - 1) if by > 0 else max(0, below - 1)
        self._current = keys[at]
        self.scroll_to_row(hunks[at][0])
        return self._current

    def next_hunk(self) -> tuple[int, int] | None:
        """Make the next hunk current and scroll to it: `DiffView.next_hunk`'s rule."""
        return self._step(1)

    def previous_hunk(self) -> tuple[int, int] | None:
        """The same, backwards."""
        return self._step(-1)

    def expand(
        self,
        file: int,
        gap: int,
        lines: int | None = None,
        edge: Literal["top", "bottom"] = "top",
    ) -> None:
        """Reveal collapsed context: `Diff.expand`, applied to what is shown."""
        self._replace(
            self._diff.expand(file, gap, self.expand_step if lines is None else lines, edge)
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    @property
    def selection(self) -> tuple[_Pos, _Pos] | None:
        """The selection as two `(file, hunk, row, character)`, start first, or `None`."""
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
        """Select from `start` to `end` and take ownership; `side` defaults to new."""
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
                continue
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
        """Which kinds of row the selection takes: `DiffView`'s rule, worked out once."""
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
        The selection as code, cut from the model: `DiffView.selected_text`'s
        rules (no markers or numbers; `COPY_GAP` between pieces that are not
        adjacent, and the next file's label between files). Empty for none.
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

    def _position(
        self, row: int, side: int | None, character: Callable[[int, str], int]
    ) -> _Pos | None:
        """
        The position nearest display row `row`: on that row if it shows a line
        on `side` (`character(row, text)` says where along it), else the start
        of the next line that does, else the end of the one before.
        """
        total = self._indexed().total
        if total == 0:
            return None
        row = max(0, min(row, total - 1))
        line = self._line_at(row, side)
        if line is not None:
            text = self._diff.files[line[0]].hunks[line[1]].rows[line[2]].text
            return (*line, max(0, min(len(text), character(row, text))))
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

    def _extent(self, pos: _Pos, granularity: int) -> tuple[_Pos, _Pos]:
        """What a click at `pos` selects: a caret, the word, or the line."""
        row = self._row(pos)
        if granularity == _CHARACTER or row is None:
            return pos, pos
        if granularity == _LINE:
            return (*pos[:3], 0), (*pos[:3], len(row.text))
        spans = tokenize(row.text)
        for start, end in spans:
            if start <= pos[3] < end:
                return (*pos[:3], start), (*pos[:3], end)
        if spans:
            return (*pos[:3], spans[-1][0]), (*pos[:3], spans[-1][1])
        return pos, pos

    # ------------------------------------------------------------------
    # The description: rows as blocks of text
    # ------------------------------------------------------------------

    def _described(self, whole: bool = False) -> _Sheet:
        """
        The current rows as blocks, described once per index.

        The text of a block of hunk rows is made when rows in it are asked for
        (`_realise`); `whole` asks for all of them, which is what a reader of
        `texts` wants and what no frame does.
        """
        index = self._indexed()
        sheet = self._sheet
        if sheet is None or sheet.index is not index:
            # The hunks that are the same objects are not described again.
            sheet = self._sheet = self._describe(index, sheet)
        if whole:
            self._realise(sheet, 0, index.total)
        return sheet

    def _lines(
        self, index: _Index, kind: int, f: int, number: int, begun: int, end: int
    ) -> list[list[str]]:
        """Rows `[begun, end)` of a segment of hunk rows (or of a raw file), per document."""
        file = index.diff.files[f]
        if kind == _RAW:
            documents = 2 if index.layout is DiffLayout.UNIFIED else 4
            lines = [[" "] * (end - begun) for _ in range(documents)]
            lines[1] = [_shown(line)[0] or " " for line in file.raw[begun:end]]
            return lines
        old_digits, new_digits = index.digits
        hunk = file.hunks[number]
        model = hunk.rows
        if index.layout is DiffLayout.UNIFIED:
            gutter = [
                f" {'' if r.old_no is None else r.old_no:>{old_digits}}"
                f" {'' if r.new_no is None else r.new_no:>{new_digits}}"
                f" {r.kind.value} "
                for r in model[begun:end]
            ]
            return [gutter, [_code_line(hunk, at)[0] or " " for at in range(begun, end)]]
        lines = [[], [], [], []]
        for pair in hunk.side_by_side[begun:end]:
            for side, at in ((0, pair.left), (1, pair.right)):
                if at is None:
                    lines[2 * side].append(" ")
                    lines[2 * side + 1].append(" ")
                    continue
                r = model[at]
                value = r.old_no if side == 0 else r.new_no
                digits = old_digits if side == 0 else new_digits
                lines[2 * side].append(
                    f" {'' if value is None else value:>{digits}} {r.kind.value} "
                )
                lines[2 * side + 1].append(_code_line(hunk, at)[0] or " ")
        return lines

    def _realise(self, sheet: _Sheet, first: int, stop: int) -> bool:
        """
        Make the text of every block holding a display row in `[first, stop)`
        that has none yet. True if one was made: the sheet is then `dirty`, and
        a view hands the blocks over again.
        """
        lazy = sheet.lazy
        total = len(sheet.row_block)
        if not lazy or not total or stop <= first:
            return False
        first = max(0, min(first, total - 1))
        stop = max(first + 1, min(stop, total))
        made = False
        for number in range(sheet.row_block[first], sheet.row_block[stop - 1] + 1):
            where = lazy.pop(number, None)
            if where is None:
                continue
            lines = self._lines(sheet.index, *where)
            for d, own in enumerate(lines):
                sheet.texts[d][number] = "\n".join(own)
            for p in range(sheet.panes):
                sheet.starts[p][number] = _line_starts(lines[2 * p + 1])
            made = True
        if made:
            sheet.dirty = True
        return made

    def _describe(self, index: _Index, before: _Sheet | None = None) -> _Sheet:
        """
        Which rows are in which block, the text of the header rows, and a
        stand-in for the rest (`_Sheet`). The cost is per block and per hunk,
        not per row.

        `before` is the description this one replaces. A
        hunk that is the same object at the same rows in the same layout is
        the same blocks: they are copied, with whatever text they have. So a
        diff that grew at its end, or had one gap opened, is described from
        the hunk that changed.
        """
        unified = index.layout is DiffLayout.UNIFIED
        panes = 1 if unified else 2
        documents = 2 * panes
        sheet = _Sheet(
            index=index,
            panes=panes,
            texts=[[] for _ in range(documents)],
            styles=[[] for _ in range(documents)],
            starts=[[] for _ in range(panes)],
        )
        files = index.diff.files
        # The roles of a block's documents, when nothing says otherwise.
        plain = [(_R_GUTTER if d % 2 == 0 else _R_CODE) for d in range(documents)]
        row = 0
        was = before.index if before is not None else None
        if was is not None and (was.layout is not index.layout or was.digits != index.digits):
            was = before = None

        def kept(at: int, segment: tuple[int, int, int, int]) -> bool:
            """Copy segment `at`'s blocks from `before`, if they are the same blocks there."""
            nonlocal row
            if before is None or was is None or segment[0] != _ROWS:
                return False
            if at >= len(was.segments) or was.segments[at] != segment:
                return False
            _, f, number, rows = segment
            old = was.diff.files
            if f >= len(old) or number >= len(old[f].hunks):
                return False
            if old[f].hunks[number] is not files[f].hunks[number]:
                return False
            first, stop = before.segment_blocks[at], before.segment_blocks[at + 1]
            # The same blocks, some rows and some blocks further on (an
            # expansion above them) or exactly where they were (a stream).
            by_blocks = sheet.blocks - first
            by_rows = row - was.starts[at]
            for d in range(documents):
                sheet.texts[d].extend(before.texts[d][first:stop])
                sheet.styles[d].extend(before.styles[d][first:stop])
            for p in range(panes):
                sheet.starts[p].extend(before.starts[p][first:stop])
            if by_blocks == 0 and by_rows == 0:
                sheet.first_row.extend(before.first_row[first:stop])
                sheet.row_block.extend(before.row_block[row : row + rows])
            else:
                for block in range(first, stop):
                    begun = before.first_row[block]
                    end = before.first_row[block + 1] if block + 1 < before.blocks else was.total
                    sheet.first_row.append(begun + by_rows)
                    sheet.row_block.extend([block + by_blocks] * (end - begun))
            for block in range(first, stop):
                where = before.lazy.get(block)
                if where is not None:
                    sheet.lazy[block + by_blocks] = where
            sheet.blocks += stop - first
            row += rows
            return True

        def block(lines: list[list[str]], roles: list[int]) -> None:
            """One block in every document: `lines[d]` are document d's lines."""
            count = len(lines[0])
            number = sheet.blocks
            for d in range(documents):
                sheet.texts[d].append("\n".join(lines[d]))
                sheet.styles[d].append(roles[d])
            for p in range(panes):
                sheet.starts[p].append(_line_starts(lines[2 * p + 1]))
            sheet.first_row.append(row)
            sheet.row_block.extend([number] * count)
            sheet.blocks += 1

        def later(kind: int, f: int, number: int, begun: int, end: int) -> None:
            """One block whose text is made when it is wanted: `_realise`."""
            count = end - begun
            text = _blank(count)
            at = sheet.blocks
            for d in range(documents):
                sheet.texts[d].append(text)
                sheet.styles[d].append(plain[d])
            for p in range(panes):
                sheet.starts[p].append(None)
            sheet.lazy[at] = (kind, f, number, begun, end)
            sheet.first_row.append(row)
            sheet.row_block.extend([at] * count)
            sheet.blocks += 1

        def chunks(kind: int, f: int, number: int, count: int) -> None:
            """Rows of a segment, in blocks of at most `CHUNK`."""
            nonlocal row
            for begun in range(0, count, CHUNK):
                end = min(count, begun + CHUNK)
                later(kind, f, number, begun, end)
                row += end - begun

        def header(text: str, role: int, inks: tuple[tuple[int, int], ...] = ()) -> None:
            nonlocal row
            shown, marked = _shown(text)
            warning = tuple((1 + at, 2 + at) for at in marked)
            if inks or warning:
                sheet.header_inks[row] = inks + warning
            lines = [[" "] for _ in range(documents)]
            lines[0] = [" " + shown]
            roles = list(plain)
            roles[0] = role
            block(lines, roles)
            row += 1

        for at, (kind, f, number, rows) in enumerate(index.segments):
            file = files[f]
            sheet.segment_blocks.append(sheet.blocks)
            if kind == _FILE:
                text, warning = _file_header(file)
                inks = ((1 + len(text), 1 + len(text) + len(warning)),)
                header(text + warning, _R_HEADER, inks if warning else ())
            elif kind == _HUNK:
                header(file.hunks[number].header, _R_HEADER)
            elif kind == _GAP:
                header(_gap_text(file, number), _R_META)
            elif kind == _FOLD:
                header(_fold_text(file), _R_META)
            elif not kept(at, (kind, f, number, rows)):
                chunks(kind, f, number, rows)
        sheet.segment_blocks.append(sheet.blocks)
        return sheet

    def _place(self, sheet: _Sheet, pane: int, row: int) -> tuple[int, int]:
        """(block, offset of the line's start) of display row `row` in a pane's code document."""
        number = sheet.row_block[row]
        starts = sheet.starts[pane][number]
        if starts is None:
            self._realise(sheet, row, row + 1)
            starts = sheet.starts[pane][number]
            assert starts is not None
        return number, starts[row - sheet.first_row[number]]


def code_size(
    theme: Theme, pixel_height: float | None = None, px_per_inch: float | None = None
) -> tuple[float, int, object]:
    """
    The code face's size in pixels and the pitch in whole pixels, as `DiffView`
    reads them from a theme (`DiffMetrics.font` and `.row`); and, third, what
    they were read from, to compare. `pixel_height` is the height the face is
    drawn at as ImGui means it, and is the one thing here that asks the old
    core (`advtext.fontlib`, imported only then) for a face's line metrics.
    """
    # Here and not at the top: a `Theme` is handed in, and importing its module
    # is the caller's business (`tests/test_typeset_diff_view.py` holds what
    # importing this one loads).
    from advtext.theme import BlockKind

    ppi = float(theme.px_per_inch if px_per_inch is None else px_per_inch)
    style = theme.style(BlockKind.CODE)
    key = (style.font, style.leading, pixel_height, ppi)
    size = style.font.size
    if pixel_height is not None:
        from advtext import fontlib

        em_px = fontlib.em_size_for_pixel_height(style.font.face, pixel_height)
        size = round(em_px * _PT_PER_INCH / ppi * _UNITY)
    leading = round(style.leading * size / max(1, style.font.size))
    row = max(1, math.ceil(_px(leading, ppi) - 1e-6))
    return _px(size, ppi), row, key


def code_face_lacks(text: str) -> tuple[str, ...]:
    """
    The characters of `text` (as it is handed to the library: a control or
    invisible character is `CONTROL_PLACEHOLDER` there) that the code face has
    no glyph for, each once, in the order met. The library sets such a
    character from another face at that face's advance, so the line holding it
    is not on the cell grid to its right (module docstring). One library call
    per distinct character above U+007E; none for ASCII.

    Raises `TypesetUnavailable` when the library cannot be asked: before
    `typesetter.load_fonts()` no role has a font and every character would be
    "lacking".
    """
    if text.isascii():
        return ()
    if not typesetter.ready():
        why = typesetter.reason() or "typesetter.load_fonts() has not succeeded"
        raise TypesetUnavailable(f"imtypeset cannot be asked: {why}")
    ts: Any = typesetter.module()
    face = int(ts.Face.Code)
    distinct = dict.fromkeys(character for character in _shown(text)[0] if character > "~")
    return tuple(character for character in distinct if not ts.face_has_glyph(face, character))


@dataclass(frozen=True, slots=True)
class _Pane:
    """One column of code with its gutter. Pixels from the view's left edge."""

    side: int | None  # None: unified. 0: old. 1: new.
    x0: float
    x1: float
    code: float  # where code column 0 is when not scrolled


class TypesetDiffView(DiffRows):
    """
    A selectable view of one `Diff`, set and drawn by imtypeset.

    The module docstring is the contract. `theme` supplies the code face's
    size and its leading (`BlockKind.CODE`), as it does for `DiffView`.
    """

    def __init__(
        self,
        diff: Diff,
        theme: Theme,
        *,
        layout: Any = DiffLayout.UNIFIED,
        pixel_height: float | None = None,
        px_per_inch: float | None = None,
        syntax: SyntaxColour | None = None,
        height_cap: float | None = None,
        expand_step: int = 20,
        copy_removed_lines: bool = False,
        copy_as: Callable[[TypesetDiffView], str] | None = None,
        palette: Palette | None = None,
    ) -> None:
        if typesetter.module() is None:
            raise TypesetUnavailable(f"imtypeset is not in use: {typesetter.reason()}")
        self.theme = theme
        self.pixel_height = pixel_height
        self.px_per_inch = float(theme.px_per_inch if px_per_inch is None else px_per_inch)
        self.syntax = syntax
        self.height_cap = height_cap
        self.copy_as = copy_as
        self.hand_cursor = True
        #: Calls made to `syntax`, the lines handed over, and calls that raised.
        self.syntax_calls = 0
        self.syntax_lines = 0
        self.syntax_errors = 0
        #: Times the marks of the rows in view were built and packed again.
        self.marks_built = 0
        #: Edits made in the library, by the call that made them, over all documents.
        self.edits: dict[str, int] = {"set": 0, "replace": 0}
        self._size = self._code_size()
        super().__init__(
            diff,
            layout=layout,
            row=self._size[1],
            expand_step=expand_step,
            copy_removed_lines=copy_removed_lines,
        )
        self._palette = palette if palette is not None else DEFAULT_PALETTE
        self._grid: tuple[tuple[object, ...], DiffGrid, Any] | None = None
        self._docs: list[Any] = []
        self._held: list[list[tuple[str, int]]] = []
        self._synced: tuple[object, ...] | None = None
        self._styled: object = None
        self._coloured: dict[
            tuple[int, int, int, int],
            tuple[int, DiffRow, DiffRow, Sequence[Sequence[tuple[int, int, int]]], object],
        ] = {}
        self._marks: tuple[tuple[object, ...], list[Any]] | None = None
        self._scroll_x = 0
        self._max_scroll_x = 0
        self._bar_drag: tuple[float, int] | None = None
        self._width = 0.0
        self._visible = range(0)
        self._hot_gap: tuple[int, int] | None = None
        self._granularity = _CHARACTER
        self._press = False
        self._drawn_frame = -(2**31)
        #: Times the text of blocks was made because rows of theirs came into the window.
        self.blocks_realised = 0
        # The library, the grid and the document style of the frame being drawn.
        self._live: tuple[Any, DiffGrid, Any] | None = None

    # ------------------------------------------------------------------
    # The grid
    # ------------------------------------------------------------------

    def _code_size(self) -> tuple[float, int, object]:
        return code_size(self.theme, self.pixel_height, self.px_per_inch)

    def _ready(self) -> Any:
        if not typesetter.ready():
            why = typesetter.reason() or "typesetter.load_fonts() has not succeeded"
            raise TypesetUnavailable(f"imtypeset cannot draw: {why}")
        return typesetter.module()

    @property
    def grid(self) -> DiffGrid:
        """The grid this view draws on. Asks the library for a cell's width on first use."""
        return self._gridded()[1]

    def _gridded(self) -> tuple[tuple[object, ...], DiffGrid, Any]:
        ts = self._ready()
        size = self._code_size()
        if size[2] != self._size[2]:
            # The theme's code style or `pixel_height` changed under the view.
            self._size = size
            self._row_px = size[1]
        if any(doc is not None and doc.closed for doc in self._docs):
            # `typesetter.unload()` closed them: another context, and maybe other fonts.
            self.close()
            self._grid = None
        key = (size[2],)
        if self._grid is not None and self._grid[0] == key:
            return self._grid
        try:
            base = typesetter.base_style(self.theme, 0)
            em = float(base.EmSize)
            scale = size[0] / em
            pitched = ts.BlockStyle(Scale=scale, LineHeight=size[1] / (em * scale))
            with ts.Document.from_blocks(
                [ts.Block(ts.BlockKind.Code, "0000000000")], [pitched]
            ) as tiny:
                tiny.layout(1000.0, base)
                cell = float(tiny.caret_rect((0, 10))[0]) / 10.0
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        if not cell > 0.0:
            why = "the code face has no advance: was it loaded?"
            typesetter.disable(why)
            raise TypesetUnavailable(f"imtypeset failed and is switched off: {why}")
        self._grid = (key, DiffGrid(cell=cell, row=size[1], em=em, scale=scale), base)
        self._synced = None
        return self._grid

    def _failed(self, exc: Exception) -> NoReturn:
        """
        What was raised while the library was in use. The library's own
        failure (`library_failed`) switches it off for the run and the caller
        is told with `TypesetUnavailable`; anything else -- the model's error,
        a slip in this module -- is raised as it is, and the library stays in
        use. `advtext.ui.typeset_view.raise_failed`, shared with `TypesetView`.
        """
        raise_failed(exc)

    def close(self) -> None:
        """Release the library's documents. The view can still be drawn: they are made again."""
        for doc in self._docs:
            if doc is not None and not doc.closed:
                doc.close()
        self._docs = []
        self._held = []
        self._synced = None
        self._marks = None
        self._live = None

    @property
    def native_documents(self) -> tuple[Any, ...]:
        """
        The `imtypeset.Document`s, gutter then code for each pane; empty before the first draw.
        """
        return tuple(doc for doc in self._docs if doc is not None and not doc.closed)

    @property
    def palette(self) -> Palette:
        """The palette in use: the constructor's, or the last one given to `draw`."""
        return self._palette

    def set_palette(self, palette: Palette) -> None:
        """Draw with `palette` from now on. A change of its diff inks sets the blocks again."""
        self._palette = palette

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def _panes(self, width: float, cell: float) -> tuple[_Pane, ...]:
        old, new = self._indexed().digits
        whole = float(int(width))
        if self._layout is DiffLayout.UNIFIED:
            return (_Pane(None, 0.0, whole, _snap((old + new + 5) * cell)),)
        # Both panes start on the cell grid; the right one takes the odd pixels.
        half = max(0, (int(whole // cell) - 1) // 2)
        start = _snap((half + 1) * cell)
        return (
            _Pane(0, 0.0, _snap(half * cell), _snap((4 + old) * cell)),
            _Pane(1, start, max(start, whole), _snap((half + 1 + 4 + new) * cell)),
        )

    def _code_width(self, panes: tuple[_Pane, ...]) -> float:
        return max(0.0, min(pane.x1 - pane.code for pane in panes))

    def _bar_height(self) -> int:
        return max(6, self._row_px // 2)

    def _overflow(self, panes: tuple[_Pane, ...], cell: float) -> int:
        """How far the code can scroll horizontally at these panes, in whole pixels."""
        needed = (self._indexed().columns + 1) * cell
        return max(0, math.ceil(needed - self._code_width(panes) - 1e-3))

    @property
    def content_width(self) -> float:
        """The width at which no line would need to scroll, in the current layout."""
        index = self._indexed()
        cell = self.grid.cell
        code = (index.columns + 1) * cell
        old, new = index.digits
        if self._layout is DiffLayout.UNIFIED:
            return float((old + new + 5) * cell + code)
        return float((old + 4) * cell + (new + 4) * cell + 2 * code + cell)

    def height_for(self, width_px: float) -> float:
        """
        The height `draw` will claim at this width: every row, the horizontal
        scrollbar if a line is too long for it, and no more than `height_cap`.
        """
        cell = self.grid.cell
        full = self.content_height
        if full and self._overflow(self._panes(max(width_px, cell * 8), cell), cell) > 0:
            full += self._bar_height()
        return full if self.height_cap is None else min(full, self.height_cap)

    @property
    def scroll_x(self) -> int:
        """The horizontal offset of the code, in whole pixels."""
        return self._scroll_x

    @scroll_x.setter
    def scroll_x(self, value: float) -> None:
        self._scroll_x = max(0, int(math.floor(value + 0.5)))

    @property
    def visible_rows(self) -> range:
        """The display rows the last `draw` put bands and marks on."""
        return self._visible

    # ------------------------------------------------------------------
    # The documents
    # ------------------------------------------------------------------

    def _ink(self, role: int) -> int:
        colours = self._palette.diff
        return int((colours.context, colours.header, colours.meta, colours.gutter)[role])

    def _sync(self, ts: Any, grid: DiffGrid, base: Any, imgui: Any = None) -> _Sheet:
        """
        Bring the library's documents to the description.

        The text of the blocks holding the rows this frame will show is made
        (`_expected`; none without `imgui`), and each document that differs
        gets ONE `replace_blocks`, over the blocks that differ.
        """
        sheet = self._described()
        if imgui is not None:
            rows = self._expected(imgui, sheet)
            if self._realise(sheet, rows.start, rows.stop):
                self.blocks_realised += 1
        colours = self._palette.diff
        key = (sheet, grid, colours.context, colours.header, colours.meta, colours.gutter)
        if (
            sheet.dirty
            or self._synced is None
            or not all(a is b or a == b for a, b in zip(self._synced, key, strict=True))
        ):
            self._hand_over(ts, grid, base, sheet, key[1:])
            self._synced = key
        return sheet

    def _expected(self, imgui: Any, sheet: _Sheet) -> range:
        """
        The display rows the frame about to be drawn will show, worked out
        before anything is submitted: exactly, from the window and the cursor,
        when the view draws into the host's window; with `height_cap` (a child
        whose scroll is not known until it is begun) the rows last shown, or
        the first rows that fit under the cap. `_ensure` covers a miss.
        """
        total = sheet.index.total
        if not total:
            return range(0)
        if self.height_cap is not None:
            if len(self._visible) and int(imgui.get_frame_count()) - self._drawn_frame <= 1:
                return range(min(self._visible.start, total - 1), min(self._visible.stop, total))
            return range(0, min(total, int(float(self.height_cap) // self._row_px) + 1))
        oy = math.floor(imgui.get_cursor_screen_pos().y + 0.5)
        window_top = imgui.get_window_pos().y
        return self._rows_between(window_top - oy, window_top + imgui.get_window_size().y - oy)

    def _rows_between(self, top: float, bottom: float) -> range:
        """The display rows with a pixel in `[top, bottom)`, pixels below the view's top."""
        total = self._indexed().total
        row = self._row_px
        first = max(0, min(total, int(top // row)))
        return range(first, max(first, min(total, math.ceil(bottom / row))))

    def _hand_over(self, ts: Any, grid: DiffGrid, base: Any, sheet: _Sheet, key_of: object) -> None:
        documents = 2 * sheet.panes
        for extra in self._docs[documents:]:
            if extra is not None and not extra.closed:
                extra.close()
        del self._docs[documents:], self._held[documents:]
        restyled = self._styled != key_of
        self._styled = key_of
        line_height = grid.row / (grid.em * grid.scale)
        code = int(ts.BlockKind.Code)
        # Every line exactly the pitch, whatever it holds: a glyph taller than
        # the pitch (U+2502 is, in the bundled code face) or one borrowed from
        # another face overhangs its row and moves nothing.
        fixed = int(ts.BlockFlags.FixedLineHeight)
        for d in range(documents):
            blocks = list(zip(sheet.texts[d], sheet.styles[d], strict=True))
            fresh = d >= len(self._docs) or self._docs[d] is None or self._docs[d].closed
            if fresh:
                doc = ts.Document()
                doc.set_options(ts.DocumentOptions(CodeOverflow=int(ts.CodeOverflow.Grow)))
                if d < len(self._docs):
                    self._docs[d] = doc
                else:
                    self._docs.append(doc)
                    self._held.append([])
            doc = self._docs[d]
            first = 0
            if fresh or restyled:
                # One style a role (`_R_CODE` ...): a block's style is its role.
                styles = [
                    ts.BlockStyle(
                        Scale=grid.scale,
                        LineHeight=line_height,
                        Align=ts.Align.Left,
                        Color=self._ink(role),
                    )
                    for role in range(4)
                ]
                whole = doc.set_blocks(
                    [ts.Block(code, text, style=role, flags=fixed) for text, role in blocks], styles
                )
                self.edits["set"] += 1
            else:
                # The blocks that differ: what is the same at the start and at
                # the end stays as the library has it.
                held = self._held[d]
                limit = min(len(held), len(blocks))
                while first < limit and held[first] == blocks[first]:
                    first += 1
                if first == len(held) == len(blocks):
                    continue
                same = 0
                limit -= first
                while same < limit and held[-1 - same] == blocks[-1 - same]:
                    same += 1
                whole = doc.replace_blocks(
                    first,
                    len(held) - first - same,
                    [
                        ts.Block(code, text, style=role, flags=fixed)
                        for text, role in blocks[first : len(blocks) - same]
                    ],
                )
                self.edits["replace"] += 1
            if whole is not True:
                typesetter.note(f"a diff edit was cut: {doc.edit_error.message}")
            self._held[d] = blocks
        sheet.dirty = False
        self._marks = None

    def _ensure(self, sheet: _Sheet, first: int, stop: int) -> None:
        """
        Rows `[first, stop)` as text in the library, if they are not yet: what
        `draw` could not know it would show when it handed the blocks over (a
        first frame inside a scrolled child, a drag past the window's edge).
        """
        if self._live is None or not self._realise(sheet, first, stop):
            return
        ts, grid, base = self._live
        self.blocks_realised += 1
        try:
            self._hand_over(ts, grid, base, sheet, self._styled)
            for doc in self._docs:
                doc.layout(_COLUMN, base)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)

    # ------------------------------------------------------------------
    # Marks: what is drawn over the rows in view
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
            or found[4] is not syntax
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

    def _marks_for(self, ts: Any, sheet: _Sheet, first: int, stop: int) -> list[Any]:
        """Per document, the packed marks of display rows `[first, stop)`, or `None`."""
        key = (
            sheet,
            first,
            stop,
            self._selection,
            self._side,
            self.copy_removed_lines,
            self.syntax,
            self._palette,
        )
        kept = self._marks
        if kept is not None and all(a is b or a == b for a, b in zip(kept[0], key, strict=True)):
            return kept[1]
        colours = self._palette.diff
        ink, behind = int(ts.MarkPlace.Ink), int(ts.MarkPlace.Behind)
        highlight = int(self._palette.highlight)
        selection = self._selection
        kinds = self._selected_kinds() if selection is not None else frozenset()
        unified = sheet.panes == 1
        files = self._diff.files
        per: list[list[Any]] = [[] for _ in range(2 * sheet.panes)]
        row_ink = {
            RowKind.ADD: int(colours.add),
            RowKind.REMOVE: int(colours.remove),
            RowKind.META: int(colours.meta),
        }
        emphasis = {
            RowKind.ADD: int(colours.add_emphasis),
            RowKind.REMOVE: int(colours.remove_emphasis),
        }
        warning = int(colours.warning)
        for row in range(first, stop):
            kind, f, number, offset = self._locate(row)
            block = sheet.row_block[row]
            if kind == _RAW:
                start = self._place(sheet, 0, row)[1]
                for at in _shown(files[f].raw[offset])[1]:
                    per[1].append((((block, start + at), (block, start + at + 1)), warning, ink))
                continue
            if kind != _ROWS:
                for a, b in sheet.header_inks.get(row, ()):
                    per[0].append((((block, a), (block, b)), warning, ink))
                continue
            hunk = files[f].hunks[number]
            info = self._info(f, number, hunk)
            rows = hunk.rows
            pair = None if unified else hunk.side_by_side[offset]
            for p in range(sheet.panes):
                side = None if pair is None else p
                shown = offset if pair is None else (pair.left if p == 0 else pair.right)
                if shown is None:
                    continue
                line = rows[shown]
                marks = per[2 * p + 1]
                start = self._place(sheet, p, row)[1]
                size = len(line.text)
                handed, marked, eol = _code_line(hunk, shown)
                own = row_ink.get(line.kind)
                if own is not None and size:
                    marks.append((((block, start), (block, start + size)), own, ink))
                if self.syntax is not None and line.kind is not RowKind.META:
                    seen = 0 if (side == 0 or line.kind is RowKind.REMOVE) else 1
                    for a, b, colour in self._syntax_for(f, number, hunk, info, shown, seen):
                        a = max(0, min(a, size))
                        b = max(a, min(b, size))
                        if b > a:
                            marks.append((((block, start + a), (block, start + b)), colour, ink))
                for at in marked:
                    marks.append((((block, start + at), (block, start + at + 1)), warning, ink))
                if eol >= 0:
                    end = start + len(handed)
                    marks.append((((block, start + eol), (block, end)), row_ink[RowKind.META], ink))
                fill = emphasis.get(line.kind)
                if fill is not None:
                    for a, b in hunk.spans[shown]:
                        marks.append((((block, start + a), (block, start + b)), fill, behind))
                if (
                    selection is not None
                    and side == self._side
                    and line.kind in kinds
                    and selection[0][:3] <= (f, number, shown) <= selection[1][:3]
                ):
                    here = (f, number, shown)
                    a = selection[0][3] if here == selection[0][:3] else 0
                    b = selection[1][3] if here == selection[1][:3] else size
                    if size == 0 and here != selection[1][:3]:
                        b = 1  # the one space an empty line is: so that it shows
                    if b > a:
                        marks.append((((block, start + a), (block, start + b)), highlight, behind))
        packed = [self._docs[d].pack_marks(marks) if marks else None for d, marks in enumerate(per)]
        self._marks = (key, packed)
        self.marks_built += 1
        return packed

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(
        self,
        *,
        fonts: object = None,
        palette: Palette | None = None,
        width_px: float | None = None,
    ) -> bool:
        """
        Draw the diff at the cursor and handle the mouse and the keys.

        The item this leaves as ImGui's last item is the view's rectangle (the
        child window, with `height_cap`). `fonts` is ignored. False when
        something in view could not be set as asked. Raises
        `TypesetUnavailable` when the library cannot draw (module docstring).
        """
        from imgui_bundle import imgui

        if palette is not None:
            self._palette = palette
        _, grid, base = self._gridded()
        ts = typesetter.module()
        self._live = (ts, grid, base)
        try:
            sheet = self._sync(ts, grid, base, imgui)
        except Exception as exc:  # noqa: BLE001 -- see `_failed`
            self._failed(exc)
        self._begin_frame(imgui)
        if width_px is None:
            width_px = imgui.get_content_region_avail().x
        width_px = max(float(width_px), grid.cell * 8)

        capped = self.height_cap is not None
        if capped:
            imgui.begin_child(
                f"##advtext-typeset-diff-child-{id(self):x}",
                imgui.ImVec2(width_px, max(1.0, self.height_for(width_px))),
            )
            width_px = max(grid.cell * 8, imgui.get_content_region_avail().x)
        clicked: list[tuple[Any, ...]] = []
        try:
            try:
                whole = self._draw_here(imgui, ts, grid, base, sheet, width_px, clicked)
            except Exception as exc:  # noqa: BLE001 -- see `_failed`
                self._failed(exc)
        finally:
            if capped:
                imgui.end_child()
        # What the model or a host's callback raises here is theirs. (So is what
        # they raise above: `_failed` switches the library off for the
        # library's own failures and for nothing else.)
        for action in clicked:
            if action[0] == "gap":
                self.expand(action[1], action[2], None, action[3])
            else:
                self.show_line_endings(action[1])
        self._handle_keys(imgui)
        return whole

    def _draw_here(
        self,
        imgui: Any,
        ts: Any,
        grid: DiffGrid,
        base: Any,
        sheet: _Sheet,
        width_px: float,
        clicked: list[tuple[Any, ...]],
    ) -> bool:
        index = sheet.index
        cell = grid.cell
        row_px = self._row_px
        panes = self._panes(width_px, cell)
        overflow = self._overflow(panes, cell)
        self._max_scroll_x = overflow
        self._scroll_x = min(self._scroll_x, overflow)
        bar = self._bar_height() if overflow > 0 and index.total else 0
        height = float(index.total * row_px) + bar

        cursor = imgui.get_cursor_screen_pos()
        ox, oy = math.floor(cursor.x + 0.5), math.floor(cursor.y + 0.5)
        origin = imgui.ImVec2(ox, oy)
        size = imgui.ImVec2(width_px, height)
        self._origin = (float(ox), float(oy))
        self._width = width_px
        window_top = imgui.get_window_pos().y
        window_bottom = window_top + imgui.get_window_size().y
        content_top = window_top + imgui.get_cursor_start_pos().y + imgui.get_scroll_y()

        target: float | None = None
        if self._keep_top is not None:
            target = float(self.row_of(self._keep_top) * row_px)
            self._keep_top = None
        if self._scroll_to is not None:
            target = float(self._scroll_to * row_px)
            self._scroll_to = None
        if target is not None:
            imgui.set_scroll_y(max(0.0, imgui.get_scroll_y() + (oy + target) - content_top))

        self._visible = self._rows_between(window_top - oy, window_bottom - oy)
        first, stop = self._visible.start, self._visible.stop
        self._top_row = max(0, min(index.total - 1, int((content_top - oy) // row_px)))
        self._ensure(sheet, first, stop)

        draw_list = imgui.get_window_draw_list()
        top = max(window_top, oy)
        bottom = min(window_bottom, oy + height)
        whole = True
        if index.total:
            self._bands(imgui, draw_list, sheet, panes, ox, oy, width_px, first, stop)
            marks = self._marks_for(ts, sheet, first, stop)
            # No draw list is the current window's (`Document.draw`): the same
            # list the bands above went to.
            address = None
            right = ox + float(int(width_px))
            for p, pane in enumerate(panes):
                gutter, code = self._docs[2 * p], self._docs[2 * p + 1]
                # The first pane's gutter document holds the header rows, which
                # span the view; its numbers are text no wider than its gutter.
                edge = right if p == 0 else ox + pane.code
                gutter.layout(_COLUMN, base)
                draw_list.push_clip_rect(
                    imgui.ImVec2(ox + pane.x0, top), imgui.ImVec2(edge, bottom), True
                )
                try:
                    whole = (
                        gutter.draw(address, (ox + pane.x0, float(oy)), None, marks[2 * p] or ())
                        and whole
                    )
                finally:
                    draw_list.pop_clip_rect()
                code.layout(_COLUMN, base)
                draw_list.push_clip_rect(
                    imgui.ImVec2(ox + pane.code, top), imgui.ImVec2(ox + pane.x1, bottom), True
                )
                try:
                    whole = (
                        code.draw(
                            address,
                            (ox + pane.code - self._scroll_x, float(oy)),
                            None,
                            marks[2 * p + 1] or (),
                        )
                        and whole
                    )
                finally:
                    draw_list.pop_clip_rect()

        if bar:
            self._scrollbar(imgui, origin, width_px, bottom - bar, bar, panes)
            imgui.set_cursor_screen_pos(cursor)

        over = self._hovering(imgui, origin, size)
        mouse_row = int((imgui.get_mouse_pos().y - oy) // row_px)
        hot_fold: int | None = None
        self._hot_gap = None
        if over and 0 <= mouse_row < index.total:
            kind, file, number, _ = self._locate(mouse_row)
            if kind == _GAP and self._diff.files[file].gaps[number].expandable:
                self._hot_gap = (file, number)
            elif kind == _FOLD:
                hot_fold = file
        pressed = imgui.is_mouse_clicked(imgui.MouseButton_.left)
        self._press = over and pressed and self._hot_gap is None and hot_fold is None
        self._end_a_drag_that_missed_its_release(imgui)
        if (self._press or self._dragging) and height > 0.0:
            imgui.invisible_button(self._button_id(), size)
        else:
            imgui.dummy(size)
        if self._hot_gap is not None or hot_fold is not None:
            if self.hand_cursor:
                imgui.set_mouse_cursor(imgui.MouseCursor_.hand)
            if pressed and self._hot_gap is not None:
                clicked.append(
                    ("gap", *self._hot_gap, "bottom" if imgui.get_io().key_shift else "top")
                )
            elif pressed:
                clicked.append(("fold", hot_fold))
        self._handle_mouse(imgui, sheet, panes, ox, oy, cell)
        if over:
            self._handle_wheel(imgui, cell)
        return bool(whole)

    def _bands(
        self,
        imgui: Any,
        draw_list: Any,
        sheet: _Sheet,
        panes: tuple[_Pane, ...],
        ox: float,
        oy: float,
        width_px: float,
        first: int,
        stop: int,
    ) -> None:
        """Row bands and the current hunk's bar: Dear ImGui's own rectangles."""
        colours = self._palette.diff
        files = self._diff.files
        right = ox + float(int(width_px))
        current = self._current
        unified = sheet.panes == 1
        fills = {RowKind.ADD: colours.add_fill, RowKind.REMOVE: colours.remove_fill}
        for row in range(first, stop):
            kind, f, number, offset = self._locate(row)
            if kind == _RAW:
                continue
            y0 = oy + float(row * self._row_px)
            y1 = y0 + self._row_px
            if kind != _ROWS:
                draw_list.add_rect_filled(
                    imgui.ImVec2(ox, y0), imgui.ImVec2(right, y1), colours.header_fill
                )
            else:
                hunk = files[f].hunks[number]
                pair = None if unified else hunk.side_by_side[offset]
                for p, pane in enumerate(panes):
                    shown = offset if pair is None else (pair.left if p == 0 else pair.right)
                    if shown is None:
                        continue
                    band = fills.get(hunk.rows[shown].kind)
                    if band is not None:
                        draw_list.add_rect_filled(
                            imgui.ImVec2(ox + pane.x0, y0), imgui.ImVec2(ox + pane.x1, y1), band
                        )
            if kind in (_HUNK, _ROWS) and current == (f, number):
                draw_list.add_rect_filled(
                    imgui.ImVec2(ox, y0), imgui.ImVec2(ox + 3.0, y1), colours.current
                )

    # ------------------------------------------------------------------
    # Interaction. The rules are `DiffView`'s, which are `BareView`'s.
    # ------------------------------------------------------------------

    def _begin_frame(self, imgui: Any) -> None:
        """A drag goes on only from one drawn frame to the very next."""
        frame = int(imgui.get_frame_count())
        if frame - self._drawn_frame > 1:
            self._dragging = False
            self._bar_drag = None
        self._drawn_frame = frame

    def _button_id(self) -> str:
        return f"##advtext-typeset-diff-{id(self):x}"

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

    def _pointed(
        self,
        imgui: Any,
        sheet: _Sheet,
        panes: tuple[_Pane, ...],
        ox: float,
        oy: float,
        side: Any,
        press: bool = False,
    ) -> tuple[_Pos | None, int | None]:
        """
        The position under the mouse and the side it is on. `side` fixes the
        side (a drag stays on the side it began on); `...` is "whichever pane
        the mouse is in". The row is found from y by the view; the character
        along it is the library's answer (one `hit_test`), which is right for
        tabs and for a glyph that is not one cell wide.
        """
        mouse = imgui.get_mouse_pos()
        x = mouse.x - ox
        if side is ...:
            at = 0 if len(panes) == 1 or x < panes[1].x0 else 1
        else:
            at = next(n for n, p in enumerate(panes) if p.side == side)
        pane = panes[at]

        def character(row: int, text: str) -> int:
            if press and x < pane.code:
                # A press on the gutter is a press at the start of the line.
                return 0
            self._ensure(sheet, row, row + 1)  # a drag can reach a row not in the window
            number, start = self._place(sheet, at, row)
            middle = (row + 0.5) * self._row_px
            hit = self._docs[2 * at + 1].hit_test((x - pane.code + self._scroll_x, middle))
            block, offset = int(hit.position[0]), int(hit.position[1])
            # A point right of a line's end answers the start of the next line.
            if (block, offset) < (number, start):
                return 0
            if block > number:
                return len(text)
            starts = sheet.starts[at][number] or []
            line = row - sheet.first_row[number]
            if line + 1 < len(starts) and offset >= starts[line + 1]:
                return len(text)
            return offset - start

        return self._position(int((mouse.y - oy) // self._row_px), pane.side, character), pane.side

    def _handle_mouse(
        self,
        imgui: Any,
        sheet: _Sheet,
        panes: tuple[_Pane, ...],
        ox: float,
        oy: float,
        cell: float,
    ) -> None:
        """Press sets an anchor, drag extends, release finishes."""
        if self._owned and not self.owns_selection:
            # Another view began a selection since this one last did.
            self.clear_selection()
            self._owned = 0
        if not sheet.index.total:
            return

        if self._press:
            self._own()
            clicks = int(imgui.get_mouse_clicked_count(imgui.MouseButton_.left))
            self._granularity = min(max(clicks, 1), 3) - 1
            pos, side = self._pointed(imgui, sheet, panes, ox, oy, ..., press=True)
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
        pos, _ = self._pointed(imgui, sheet, panes, ox, oy, self._side)
        if pos is not None:
            under = self._extent(pos, self._granularity)
            self._select(min(self._anchor[0], under[0]), max(self._anchor[1], under[1]), self._side)
            # A drag past either edge of the code scrolls it.
            pane = next(p for p in panes if p.side == self._side)
            x = imgui.get_mouse_pos().x - ox
            step = int(math.ceil(2 * cell))
            if x > pane.x1:
                self._scroll_x = min(self._max_scroll_x, self._scroll_x + step)
            elif x < pane.code:
                self._scroll_x = max(0, self._scroll_x - step)
        if not imgui.is_mouse_down(imgui.MouseButton_.left):
            self._dragging = False

    def _copied(self) -> str:
        return self.selected_text() if self.copy_as is None else self.copy_as(self)

    def copy(self, text: str | None = None) -> None:
        """
        Put `text` on the clipboard, or the selection as Ctrl+C would; with
        nothing to copy the clipboard is left as it was. A NUL goes as U+2400.
        """
        from imgui_bundle import imgui

        if text is None:
            text = self._copied()
            if not text:
                return
        imgui.set_clipboard_text(clipboard_text(text))

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
        """Answer Ctrl+C and Ctrl+A on a frame this view is not drawn; never as well as `draw`."""
        from imgui_bundle import imgui

        self._handle_keys(imgui)

    def _handle_wheel(self, imgui: Any, cell: float) -> None:
        io = imgui.get_io()
        wheel = float(io.mouse_wheel_h)
        if io.key_shift:
            wheel += float(io.mouse_wheel)
        if wheel:
            step = int(math.floor(wheel * 4 * cell + 0.5))
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
        An ImGui item, drawn in ImGui's own scrollbar colours.
        """
        overflow = self._max_scroll_x
        left = origin.x + panes[0].code
        track = max(1.0, origin.x + width_px - left)
        view = float(self._code_width(panes))
        thumb = max(float(bar), track * view / (view + overflow))
        travel = max(1.0, track - thumb)
        imgui.set_cursor_screen_pos(imgui.ImVec2(left, top))
        imgui.invisible_button(
            f"##advtext-typeset-diff-bar-{id(self):x}", imgui.ImVec2(track, float(bar))
        )
        mouse = imgui.get_mouse_pos().x
        if imgui.is_item_activated():
            at = left + travel * self._scroll_x / overflow
            if not at <= mouse <= at + thumb:
                # A press on the track: the thumb comes to the mouse first.
                share = max(0.0, min(1.0, (mouse - left - thumb / 2) / travel))
                self._scroll_x = int(math.floor(share * overflow + 0.5))
            self._bar_drag = (mouse, self._scroll_x)
        if imgui.is_item_active() and self._bar_drag is not None:
            start, was = self._bar_drag
            moved = (mouse - start) * overflow / travel
            self._scroll_x = int(math.floor(max(0.0, min(float(overflow), was + moved)) + 0.5))
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


def _snap(value: float) -> float:
    """A position on a whole pixel."""
    return float(math.floor(value + 0.5))

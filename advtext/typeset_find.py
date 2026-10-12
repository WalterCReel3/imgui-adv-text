"""
Find in a document described for imtypeset: the matches, the current one, the marks.

**Experimental** (branch `experimental/imtypeset-adoption`, step A4 of
`../imtypeset/docs/advtext-rework-plan.md` section 6.3). Of the facade:
`FindIndex`, `Finder` and `Match`; the rest is reached from here.

`advtext.spans.FindIndex` searches advtext's *material* and answers material
indices, which a `ColourSpan` takes. A document handed to imtypeset is text
with runs (`advtext.typesetter.Converter`), and what marks a range of it is an
`imtypeset.Mark` over `(block, offset)` positions. So this is the same search
over the other representation:

    index = FindIndex.of(described.blocks)        # when the document changes
    matches = index.find("glue", ignore_case=True)  # per keystroke: str.find

and `Finder` keeps a needle, its matches, which one is current, and the marks
packed for the library until one of those changes.

**Offsets are indices into the block's `str`** (codepoints), in a `Match` and
in a mark alike. `imtypeset.Document.pack_marks` converts to the library's
byte offsets itself, against the texts the document holds *at that moment*
(read in `../imtypeset/python/imtypeset/__init__.py`, `Document._byte`, and
held by `tests/test_typeset_find.py` on a text with two-, three- and four-byte
characters). Two things follow:

- the index must be built from the very descriptions the document was given,
  not from `material_text` of the advtext block, which is another string;
- marks packed before an edit are stale after it. `Finder.set_index` is how a
  host says the document changed, and it drops the pack.

**What carries over from `advtext.spans.FindIndex`, and what does not.**

Carried, with the same rules: every non-overlapping occurrence in reading
order; an empty needle finds nothing; with `ignore_case` both sides are
`casefold()`ed, and a stretch whose folded form has another length (a sharp s,
a dotted capital I) is searched as it stands, since offsets into the folded
string would be wrong; in prose a hard break is a newline in the text and a
space in the needle matches it, in a code block it does not. **Table cells
are searched**, each by itself, as there: a table is one block whose text is
its cells with a tab between the cells of a row and a newline between rows
(`advtext.description.table_text`), and every cell is a stretch of that text,
so a needle never matches across two cells and a match's offsets are offsets
into the table's text, which is what the library's marks take in a table
(marks draw in cells since imtypeset commit `be40444`).

Not carried:

- **A Host block is not searched**, with text or without: what it holds is a
  host widget's copy text, and the library draws no mark there.
- **A match has no `cell`**: `Match` is `(block, start, end)`, in a table too.
  `advtext.description.cell_spans` says which cell an offset is in.
- **Formulas.** The described text holds a formula's *source* where the
  material holds a box. Neither index searches it: here a formula's run cuts
  the block into stretches and each is searched by itself. The one difference
  is that `FindIndex` sees the text either side of an inline formula as
  adjoining, so a needle can match across the box; here it cannot. A formula
  advtext's builder refused is described as plain text in the code face, not
  as a formula run, and IS searched.
- **Indices are another coordinate.** A `TextMatch` indexes material (nodes),
  a `Match` the described string. They are not interchangeable.

Pure Python but for `Finder.packed`, which calls the document's `pack_marks`.
The marks themselves are plain tuples in the field order of `imtypeset.Mark`,
which `pack_marks` and `Document.draw` take as they are.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final, NamedTuple

from advtext.description import (
    KIND_CODE,
    KIND_HOST,
    KIND_TABLE,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    BlockDescription,
    RunDescription,
    cell_spans,
)

__all__ = [
    "CURRENT_COLOR",
    "FindIndex",
    "Finder",
    "HIT_COLOR",
    "MARK_BEHIND",
    "MARK_INK",
    "MARK_LIMIT",
    "MARK_UNDER",
    "MarkDescription",
    "Match",
    "marks_for",
]

# `ImTypesetMarkPlace` (../imtypeset/include/imtypeset.h), as integers, so that
# marks need no library. `tests/test_typeset_find.py` compares them with the
# loaded package's own when there is one.
MARK_INK, MARK_BEHIND, MARK_UNDER = 0, 1, 2

# ImU32 as Dear ImGui packs it (A in the top byte, then B, G, R). The two
# colours of the demo's Find page (`advtext.ui.pages.find.HIT_MARK` and
# `CURRENT_MARK`), written out so this module imports nothing of `advtext.ui`.
HIT_COLOR: Final = 0x5939B3E8
CURRENT_COLOR: Final = 0xD01A7AF2

MARK_LIMIT: Final = 4000
"""
The most marks `marks_for` makes unless told otherwise.

The header: "Every mark costs a comparison each draw, in view or not: for tens
of thousands, hand over the ones near the view." A one-letter needle over a
long document is tens of thousands. The spike stopped at the same number; the
count is not measured here.
"""

_FORMULA: Final = RUN_FORMULA | RUN_DISPLAY_FORMULA


class Match(NamedTuple):
    """
    One occurrence: `[start, end)` of block `block`'s text, as `str` indices.
    """

    block: int
    start: int
    end: int


class MarkDescription(NamedTuple):
    """
    A mark: `imtypeset.Mark`, field for field, so the library takes it as it is.

    `range` is `((block, offset), (block, offset))` with `str` offsets.
    """

    range: tuple[tuple[int, int], tuple[int, int]]
    color: int
    place: int = MARK_INK
    thickness: float = 0.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True)
class _Stretch:
    """
    One searchable stretch of a block's text: as it stands, and case-folded.

    `offset` is where it starts in the block's text. `folded` is `None` when
    folding changes the length.
    """

    block: int
    offset: int
    plain: str
    folded: str | None
    prose: bool


@dataclass(frozen=True, slots=True)
class FindIndex:
    """
    The searchable text of every described block, built once per document.

    Frozen, as `advtext.spans.FindIndex` is: a document that changed wants a
    new one, built from all of its descriptions.
    """

    stretches: tuple[_Stretch, ...]
    blocks: int
    """How many blocks were indexed, searchable or not."""

    @classmethod
    def of(cls, blocks: Iterable[BlockDescription], base: int = 0) -> FindIndex:
        """
        Index `blocks` (a `Description.blocks`); `base` is the first one's index in the document.

        A Host block is counted and not searched, whatever text it holds
        (a host widget's, for a copy; the library draws no mark there). A
        table's cells are searched one by one, at their offsets in the
        table's text.
        """
        stretches: list[_Stretch] = []
        count = 0
        for number, block in enumerate(blocks, base):
            count += 1
            if block.kind == KIND_HOST:
                continue
            if block.kind == KIND_TABLE:
                for row, spans in zip(block.rows, cell_spans(block.rows), strict=True):
                    for cell, (start, _) in zip(row, spans, strict=False):
                        _add_text(stretches, number, start, cell.text, cell.runs, True)
                continue
            _add_text(stretches, number, 0, block.text, block.runs, block.kind != KIND_CODE)
        return cls(tuple(stretches), count)

    def find(self, needle: str, *, ignore_case: bool = False) -> tuple[Match, ...]:
        """
        Every non-overlapping occurrence of `needle`, in reading order.

        The rules are `advtext.spans.FindIndex.find`'s; the module's docstring
        says which of them carry over.
        """
        if not needle:
            return ()
        folded = needle.casefold()
        spaced, spaced_folded = needle.replace("\n", " "), folded.replace("\n", " ")
        matches: list[Match] = []
        for stretch in self.stretches:
            if ignore_case and stretch.folded is not None:
                haystack, wanted = stretch.folded, spaced_folded if stretch.prose else folded
            else:
                haystack, wanted = stretch.plain, spaced if stretch.prose else needle
            size = len(wanted)
            position = haystack.find(wanted)
            while position != -1:
                start = stretch.offset + position
                matches.append(Match(stretch.block, start, start + size))
                position = haystack.find(wanted, position + size)
        return tuple(matches)


def _add_text(
    stretches: list[_Stretch],
    block: int,
    base: int,
    text: str,
    runs: Sequence[RunDescription],
    prose: bool,
) -> None:
    """
    The stretches of one text (a block's, or a cell's at `base` of its block's): cut at formulas.
    """
    at = 0
    # Runs are ascending and do not overlap (`RunDescription`).
    for run in runs:
        if run.flags & _FORMULA:
            _add(stretches, block, base + at, text[at : run.start], prose)
            at = max(at, run.end)
    _add(stretches, block, base + at, text[at:], prose)


def _add(stretches: list[_Stretch], block: int, offset: int, text: str, prose: bool) -> None:
    if not text:
        return
    # In prose a hard break and a space are one character each, so every
    # offset still stands (`advtext.spans.FindIndex.of`).
    plain = text.replace("\n", " ") if prose else text
    folded = plain.casefold()
    stretches.append(
        _Stretch(block, offset, plain, folded if len(folded) == len(plain) else None, prose)
    )


def marks_for(
    matches: Sequence[Match],
    current: int | None = None,
    *,
    color: int = HIT_COLOR,
    current_color: int = CURRENT_COLOR,
    limit: int = MARK_LIMIT,
) -> tuple[MarkDescription, ...]:
    """
    A mark behind each match, and a stronger one behind `matches[current]`.

    The current match's mark is last, so it is drawn over a neighbour's. No
    more than `limit` marks are made: the first `limit` matches, with the
    current one in place of the last of them when it lies beyond.
    """
    chosen = set(range(min(len(matches), max(limit, 0))))
    if current is not None and 0 <= current < len(matches) and limit > 0:
        if current not in chosen:
            chosen.discard(max(chosen))
        chosen.discard(current)
    else:
        current = None
    marks = [_mark(matches[number], color) for number in sorted(chosen)]
    if current is not None:
        marks.append(_mark(matches[current], current_color))
    return tuple(marks)


def _mark(match: Match, color: int) -> MarkDescription:
    return MarkDescription(
        ((match.block, match.start), (match.block, match.end)), color, MARK_BEHIND
    )


class Finder:
    """
    A needle over one document: its matches, the current one, and the marks.

    A host with a search box keeps one of these beside its view:

        finder.set_index(FindIndex.of(described.blocks))   # after EVERY edit
        finder.search(needle)                              # the box changed
        finder.step(+1)                                    # next; -1 is previous
        view.set_marks(finder.marks())                     # when `revision` moved

    `marks()` are plain tuples, which an `advtext.ui.typeset_view.TypesetView`
    packs itself and packs again after an edit; `revision` counts the changes
    of index, needle and current match. A host that draws an
    `imtypeset.Document` of its own can pass `packed(document)` to its draw
    instead: that calls `document.pack_marks` only when the revision or the
    document object differs from the last call. Do not give a view the pack
    and hold it across an edit: it has byte offsets into the texts as they
    were, and the view drops it.
    `match` is the place to scroll to: `(block, start, end)`.

    The current match follows the demo's Find page: after a search or a new
    index it is the first match at or after where the previous current match
    started (so another letter typed, or more text streamed in, does not throw
    the reader to the top), the first when there was none, `None` when nothing
    matched. `step` wraps at both ends.
    """

    def __init__(
        self,
        index: FindIndex | None = None,
        *,
        color: int = HIT_COLOR,
        current_color: int = CURRENT_COLOR,
        limit: int = MARK_LIMIT,
    ) -> None:
        self.index: FindIndex = index if index is not None else FindIndex((), 0)
        self.color = color
        self.current_color = current_color
        self.limit = limit
        self.needle = ""
        self.ignore_case = True
        self.matches: tuple[Match, ...] = ()
        self.current: int | None = None
        self.revision = 0
        self._marks: tuple[MarkDescription, ...] | None = ()
        self._packed: tuple[int, Any, Any] | None = None

    # -- changing what is searched --------------------------------------

    def set_index(self, index: FindIndex) -> tuple[Match, ...]:
        """
        The document changed: search `index` for the same needle. Returns the matches.

        Call it after EVERY edit of the document, whether or not the matches
        could have moved: the pack holds byte offsets into the texts the
        document had when it was made.
        """
        self.index = index
        return self._search()

    def search(self, needle: str, *, ignore_case: bool | None = None) -> tuple[Match, ...]:
        """
        Search for `needle`. Returns the matches. The same needle again does nothing.
        """
        case = self.ignore_case if ignore_case is None else ignore_case
        if needle == self.needle and case == self.ignore_case:
            return self.matches
        self.needle, self.ignore_case = needle, case
        return self._search()

    def _search(self) -> tuple[Match, ...]:
        before = self.match
        self.matches = self.index.find(self.needle, ignore_case=self.ignore_case)
        self.current = None
        if self.matches:
            self.current = 0
            if before is not None:
                place = (before.block, before.start)
                self.current = next(
                    (
                        number
                        for number, match in enumerate(self.matches)
                        if (match.block, match.start) >= place
                    ),
                    0,
                )
        self._stale()
        return self.matches

    def _stale(self) -> None:
        self.revision += 1
        self._marks = None
        self._packed = None

    # -- the current match ----------------------------------------------

    @property
    def match(self) -> Match | None:
        """
        The current match, or `None`.
        """
        return None if self.current is None else self.matches[self.current]

    def step(self, delta: int) -> Match | None:
        """
        Move the current match by `delta`, wrapping at both ends. Returns it, or `None`.
        """
        if not self.matches or self.current is None:
            return None
        moved = (self.current + delta) % len(self.matches)
        if moved != self.current:
            self.current = moved
            self._stale()
        return self.matches[moved]

    def next(self) -> Match | None:
        """
        The match after the current one becomes current; the first after the last.
        """
        return self.step(1)

    def previous(self) -> Match | None:
        """
        The match before the current one becomes current; the last before the first.
        """
        return self.step(-1)

    def status(self) -> str:
        """
        "3 of 17", or "" when nothing matched.
        """
        if self.current is None:
            return ""
        return f"{self.current + 1} of {len(self.matches)}"

    # -- the marks ------------------------------------------------------

    def marks(self) -> tuple[MarkDescription, ...]:
        """
        The marks as plain tuples, made once per change. `Document.draw` takes them too.
        """
        if self._marks is None:
            self._marks = marks_for(
                self.matches,
                self.current,
                color=self.color,
                current_color=self.current_color,
                limit=self.limit,
            )
        return self._marks

    def packed(self, document: Any) -> Any:
        """
        The marks as `document.pack_marks` packs them, or `None` when there are none.

        `document` is an `imtypeset.Document` holding the blocks the index was
        built from. Packed once per `revision` and per document object; every
        other call answers what the last one made.
        """
        marks = self.marks()
        if not marks:
            return None
        held = self._packed
        if held is not None and held[0] == self.revision and held[1] is document:
            return held[2]
        packed = document.pack_marks(marks)
        self._packed = (self.revision, document, packed)
        return packed

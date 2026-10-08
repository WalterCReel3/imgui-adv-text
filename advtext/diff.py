r"""
Diffs as data: two ways in, one model out, and nothing here draws.

A host that reviews a pending file write has the whole *before* and the whole
*after* in hand; a chat transcript has whatever unified-diff text a model typed
into a fenced block, possibly still arriving. Both become the same structure --

    Diff -> FileDiff -> Hunk -> DiffRow

-- so a view is written once. This module is pure Python over the standard
library (`difflib`, `re`): no ImGui, no fonts, no new dependency.

**The two constructors.**

- `Diff.from_texts(before, after, label)` is the primary one. `None` for
  *before* is a new file and `None` for *after* a deleted one. Because the full
  texts are kept, collapsed context between hunks can be revealed in steps
  (`FileDiff.expand`), and `FileDiff.apply(before)` gives back *after* exactly.
- `Diff.from_unified(text)` reads unified-diff text, and `UnifiedDiffStream`
  reads the same text as it grows. Only what the text states is known, so
  `FileDiff.expandable` is false and `expand` raises `ContextUnavailable`.

**What a row is.** `DiffRow.text` is the line without its `+`/`-`/space marker
and without its line terminator; `DiffRow.eol` is the terminator (`"\n"`, or
`"\r\n"` when the line ended in a carriage return, so a view never has to draw
one). A file whose last line has no closing newline is recorded the way the
unified format records it: a `RowKind.META` row follows the line it speaks
for, and the terminator that line really has is its `eol` less the final
`"\n"` (`Hunk.terminator`). The marker row is the only META row this module
produces. Line numbers are 1-based and are `None` on the side a row does not
exist on, and on both sides in a hunk whose header gave no ranges.

**Characters that are not what they look like.** Content is never hidden
because of a character in it. A text holding a NUL, an escape, a form feed, a
lone carriage return or any other C0 or C1 control (or DEL) is diffed like any
other text: its rows carry the real characters, `apply` returns them, and
`Hunk.control_characters` / `FileDiff.control_characters` say that some row
holds one, so that a view can draw a visible placeholder for each and say so
in the file's header. (Until review 1 a NUL made the whole file `BINARY` with
no rows and `+0 -0`: a one-byte way to hide a change from the person
approving it.) The same goes for a character that draws as *nothing* and
changes what the text reads as -- a zero-width space inside `admin`, a
right-to-left override that reorders the rest of a line (`has_invisible`:
Unicode's format characters and its two line separators). Those set
`invisible_characters` as well as `control_characters`, so a view can name
the kind (review 3, item 1).
`FileStatus.BINARY` is a status somebody *states*: the host, with
`from_texts(..., binary=True)`, or git, with `Binary files ... differ`.

**Line endings.** A row's `text` never holds its terminator, so two rows can
be equal in `text` and differ in `eol` -- and a file converted from CRLF to LF
is, row for row, a list of removed lines beside identical added ones. Two
things say what happened. `Hunk.eol_rows` is the rows of every remove/add pair
whose texts are the same characters (their endings are what differ: CRLF and
LF, or a closing newline gained or lost); a view draws the ending of those
rows. `FileDiff.line_endings` is set by `from_texts` when the two texts are
equal once every CRLF is read as LF, to `"CRLF -> LF"`, `"LF -> CRLF"` or the
same with `"mixed"` on a side; a view says so in the file's header and folds
the rows away behind it. A diff read from unified text knows the first and
not the second (context it was not given may hold a real change). Lines a
view copies are joined with `"\n"` whatever their `eol` was.

**Counts.** `added`/`removed` count ADD and REMOVE rows, per file and in total.
Rows are classified by position inside a hunk's declared budget and not by
what the line looks like, which is pptmstr's `model.count_diff_lines` rule and
exists for the same reason: removing a markdown rule gives the physical line
`----`, and adding `++ x` gives `+++ x`, and neither is a file header. (The
one exception is a whole `---` / `+++` / `@@` header, below, where this module
and pptmstr's counter now differ on purpose: on malformed text the two used to
agree on a wrong number.)
`tests/test_diff.py` carries a copy of that function as an oracle.

**Intra-line spans and side-by-side rows** are derived per hunk on first use
and cached on the hunk (`Hunk.spans`, `Hunk.side_by_side`); they are not
stored on rows, which is what lets a streamed row stay the same object while
the add run that will be paired with it is still arriving.

*Grouping.* A change group is a run of REMOVE rows followed directly by a run
of ADD rows (either may be empty). An ADD followed by a REMOVE starts a new
group, so old and new numbers both rise down a side-by-side column.

*Pairing rule.* Inside a group, removes and adds are aligned in order by an
exact dynamic programme that maximises total similarity over pairs at or above
`SIMILARITY_FLOOR`, when the group has at most `ALIGN_CELLS` remove x add
cells; a larger group is paired by position. Lines left unpaired between two
aligned pairs are laid beside each other by position with no spans, so the
side-by-side view shows "a remove run beside its add run, blanks where one
side is shorter" and a line inserted at the top of a changed block does not
shear every pair below it.

*Tokenisation.* `\w+ | \s+ | one other character`: identifiers and numbers are
whole tokens, a run of whitespace is one token, each punctuation mark is its
own. Spans are the token ranges `difflib` does not match, as character offsets
into `DiffRow.text` (Python `str` indices, half open). Similarity is
`2 * matched / total` counted in *characters of non-whitespace tokens*, so
indentation and single punctuation marks do not make two unrelated lines look
alike. A pair below the floor carries no spans: the row background already
says the whole line changed, and emphasis on all of it says nothing more.

*Cost bound.* A line longer than `MAX_INTRALINE_CHARS` is never tokenised, and
one hunk spends at most `INTRALINE_BUDGET` characters on pair comparisons
before the rest of its groups are laid out by position with no spans. Pair
results are memoised by text, and a streamed hunk is not re-derived after
every line: see `_Deriver`. The figures measured for a
5,000-line diff are in `.concerns/C-diffmodel--builder--result.md`.

**The streaming invariant.** Let `P` be a prefix of a unified text `T`. Then
the rows of `P`, listed as `(file index, hunk index, row)`, are a prefix of the
rows of `T` -- after dropping `P`'s last `Diff.unsettled` rows. Those are the
row of a line whose newline has not arrived (`Diff.provisional`), and at most
two complete lines that the line after them may still turn into a file header
(below). Every other complete line is decided when it is read and never
reinterpreted. Closed hunks and closed files are the *same objects* from one
snapshot to the next, so a view can key its caches on identity; `feed` costs
the new text, a snapshot costs one tuple of the open hunk's rows, and pairing
the open hunk costs the adds of its open change group, or one row while that
group is removals only (`_Deriver`). `tests/test_diff.py`
holds the invariant over every character prefix of twelve texts and checks a
randomly cut stream of sixty awkward ones against the texts they came from.

**Lines decided by the line after them.** Until review 1 the parser had no
lookahead at all; it now holds three kinds of line for one line (two, for the
first), because being wrong about them put changes under the wrong file:

- `--- X`, then `+++ Y`, then a line starting `@@`, one straight after the
  other, inside a hunk's declared lengths: **the counts decide.** When the
  hunk is still owed exactly one old line and one new line, the first two are
  those rows -- the removal of `-- X` and the addition of `++ Y` -- and the
  `@@` is the same file's next hunk; an honest `diff -U0` of such a file is
  exactly that (review 3, item 2). In every other case the three are a file
  header, owed lines or not: a hunk header that over-declares is common
  (every pptmstr diff of a text with no closing newline does).
- Outside declared lengths, `--- X` then `+++ Y` is a file header without
  waiting for the `@@`. `--- X` followed by anything else **opens no file**
  (review 3, item 6: test output in a `diff` fence has `--- FAIL: TestX`
  lines): it is the removal of `-- X` when a hunk is taking lines (so
  removing the SQL comment `-- x`, or a line that is exactly `--`, is a
  removal everywhere), and otherwise a line like any unmarked one -- kept,
  and context or a removal only if the text turns out to be a fragment. A
  sloppy header (`--- a/y.py` with no `+++` line) is therefore not a header:
  under a hunk that is taking lines it is a removed row of the file above,
  which is the price of reading `-- x` right.
- `-- ` after a hunk has had every line it declared, followed by a version
  number, is the signature of a `git format-patch` mail and ends the patch.

A snapshot taken while such a line is the last one read shows it as content
inside declared lengths (counted in `unsettled`) and as the header or
signature it probably is outside them; `UnifiedDiffStream.close()` -- which
`Diff.from_unified` calls -- settles it as what it is with nothing after it.

**Dialects read, and what is forgiven.** `---`/`+++` headers with or without a
tab-separated timestamp, `/dev/null`, git's `diff --git` block (`new file
mode`, `deleted file mode`, renames and mode changes kept in `FileDiff.header`,
`Binary files ... differ`, `GIT binary patch`), `@@` ranges with omitted
lengths, the `\` marker, several files in one text, fragments that start at
`@@` with no file header, a `git format-patch` mail around any of it (known
by its first line, `From <40 or 64 hex digits> <date>`, and not by the word), CRLF on
any line, tabs. Forgiven, because model-written diffs do these: a hunk header
with no ranges (`@@`, `@@ ... @@`), no hunk header at all, a blank line
standing for a blank context line, a hunk that runs past its declared lengths,
and -- in a fragment with no headers -- leading lines with no marker, which
are the context above the first `+` or `-` line.

**No line is dropped.** Every non-blank line of a text given to
`from_unified` or a stream is somewhere in the result: a row, the `@@` line
of a hunk, a line of `FileDiff.raw`, or a line of `FileDiff.header` -- which
holds, besides real header lines, whatever else was read as nothing (a mail's
message, prose above a header). The ones that came *after* a file's first
hunk began are listed in `FileDiff.unread` as well, for a view to say it is
not showing them. `tests/test_diff.py` holds this over random texts made of
lines that look like every part of a diff, whole and a character at a time.

**Not read as rows, and said so** (`FileDiff.dialect`, with the file's lines
in `FileDiff.raw` for a view to show as written):

- `COMBINED`: git's combined format (`diff --cc`, `diff --combined`, `@@@`).
  Its lines carry a marker column per parent; read with one, `-theirs` came
  out as a context line. No rows, no counts.
- `NOT_A_DIFF`: a text with something in it and nothing recognised. A diff
  that would have been shown as nothing is shown as what was written.

**Known limits, stated rather than discovered.**

- A physical line of the shape `-foo+bar` -- what `difflib.unified_diff`
  writes from `keepends=True` lines when a text has no closing newline, which
  is pptmstr's `approval._unified` -- is one REMOVE row `foo+bar` and the hunk
  is left `complete=False`. Nothing in the text says where `foo` ends, so it
  cannot be repaired here; the file it belongs to is now always the right one.
  `from_texts` / `from_edits` have no such problem and are what a host holding
  the texts must call.
- Inside declared lengths a `---` line, a `+++` line and a `@@` line in a
  row are a file header unless the hunk is owed exactly one old and one new
  line (above). One shape is therefore still misread, and no rule over the
  text alone reads both it and its opposite: a hunk whose header
  over-declares each side by *exactly one* line, directly followed by the
  next file's header, takes that header as two rows (and the next file's
  hunks with it). Honest text is read right: `tests/test_diff.py` holds
  difflib's own output, over a pool of lines that look like every part of a
  diff, to `apply` at context 0, 1 and 3.
- A snapshot of a stream that has just read `--- x` outside declared lengths
  shows a new file that the next line may take back (it was the removal of
  `-- x`). Rows are never shown and taken back except those `unsettled` counts.
- Lines are split on `"\n"` only. `str.splitlines` also splits on form feed,
  `\x1c`-`\x1e`, `\x85` and the Unicode separators, so a file containing those
  has more lines by difflib's count than by this module's.
- git's C-quoted paths (`"a/\303\251"`) are kept as written, quotes included.
- `FileDiff.line_endings` is known only from the texts; rename and mode
  changes are kept as header lines and have no status of their own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from enum import Enum
from functools import cached_property, lru_cache
from typing import Literal

__all__ = [
    "ALIGN_CELLS",
    "COMBINED",
    "INTRALINE_BUDGET",
    "MAX_INTRALINE_CHARS",
    "NOT_A_DIFF",
    "NO_NEWLINE",
    "SIMILARITY_FLOOR",
    "ContextUnavailable",
    "Diff",
    "DiffApplyError",
    "DiffRow",
    "FileDiff",
    "FileStatus",
    "Gap",
    "Hunk",
    "RowKind",
    "SidePair",
    "Span",
    "UnifiedDiffStream",
    "has_control",
    "has_invisible",
    "tokenize",
]

#: A changed stretch of one row: character offsets into `DiffRow.text`, half open.
Span = tuple[int, int]

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

# Every character of general category Cf (format), Zl and Zp (the line and
# paragraph separators) -- written out, because finding them by a scan of the
# Unicode database costs more than importing the rest of this module.
# `tests/test_diff.py` holds the class equal to the running Python's database.
_INVISIBLE = re.compile(
    "[\u00ad\u0600-\u0605\u061c\u06dd\u070f\u0890\u0891\u08e2\u180e"
    "\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb"
    "\U000110bd\U000110cd\U00013430-\U0001343f\U0001bca0-\U0001bca3"
    "\U0001d173-\U0001d17a\U000e0001\U000e0020-\U000e007f]"
)


def has_control(text: str) -> bool:
    """
    Whether `text` holds a control character: a C0 control other than tab
    (NUL, escape, form feed, a carriage return that is not part of a CRLF
    line end, ...), DEL, or a C1 control (U+0080 to U+009F: NEL, CSI, ...).
    See "Characters that are not what they look like" in the module docstring.
    """
    return _CONTROL.search(text) is not None


def has_invisible(text: str) -> bool:
    """
    Whether `text` holds a character that draws as nothing and can change
    what the text around it *reads as*: every format character (Unicode
    general category Cf -- the zero-width space and joiners, the byte-order
    mark, the soft hyphen, the tag characters, and the bidirectional controls
    U+202A to U+202E and U+2066 to U+2069, which reorder the letters after
    them: the "Trojan Source" class) and the line and paragraph separators
    U+2028 and U+2029.
    """
    return not text.isascii() and _INVISIBLE.search(text) is not None


#: The text of the META row that follows a line with no closing newline.
NO_NEWLINE = "No newline at end of file"

#: `FileDiff.dialect` for git's combined format (`diff --cc`, `@@@`), whose
#: lines carry one marker column per parent.
COMBINED = "combined diff"

#: `FileDiff.dialect` for a text in which nothing was recognised as a diff.
NOT_A_DIFF = "not a diff"

#: A pair of lines must be at least this similar (see the module docstring for
#: the measure) to be aligned with each other and to carry intra-line spans.
#: A choice, not a measurement: 0.5 is "at least as much kept as changed".
SIMILARITY_FLOOR = 0.5

#: A change group of R removes and A adds is aligned by dynamic programme when
#: R * A is at most this, and by position otherwise.
ALIGN_CELLS = 256

#: Lines longer than this are never tokenised (minified files, data blobs).
MAX_INTRALINE_CHARS = 500

#: Characters one hunk may spend on pair comparisons before the rest of its
#: groups go without spans.
INTRALINE_BUDGET = 400_000


class RowKind(Enum):
    """What a row is. The value is the row's marker in unified-diff text."""

    CONTEXT = " "
    ADD = "+"
    REMOVE = "-"
    META = "\\"


class FileStatus(Enum):
    MODIFIED = "modified"
    NEW = "new"
    DELETED = "deleted"
    #: The content is not text, **because somebody said so**: the host
    #: (`Diff.from_texts(..., binary=True)`) or git (`Binary files ... differ`,
    #: `GIT binary patch`). No hunks. Nothing in a text makes it binary here --
    #: see "Control characters" in the module docstring.
    BINARY = "binary"
    #: Before and after are the same text. No hunks.
    UNCHANGED = "unchanged"


class ContextUnavailable(Exception):
    """Collapsed context was asked for and only a unified text was given."""


class DiffApplyError(Exception):
    """`FileDiff.apply` was given a text the diff does not describe."""


@dataclass(frozen=True, slots=True)
class DiffRow:
    """
    One line of a hunk.

    `text` has neither marker nor terminator. `old_no`/`new_no` are 1-based and
    `None` where the row has no line on that side or the hunk stated no ranges.
    """

    kind: RowKind
    text: str
    old_no: int | None = None
    new_no: int | None = None
    eol: str = "\n"


@dataclass(frozen=True, slots=True)
class SidePair:
    """
    One side-by-side row: indices into `Hunk.rows`, `None` for a blank side.

    A context row is on both sides with the same index. A META row sits on the
    side(s) of the line it follows.
    """

    left: int | None
    right: int | None


@dataclass(frozen=True, slots=True)
class Gap:
    """
    The lines not shown before hunk `index` (or after the last hunk, for
    `index == len(hunks)`).

    `count` is `None` where it cannot be known: the stretch after the last hunk
    of a diff read from unified text, or either side of a hunk with no ranges.
    `expandable` is true only when the full texts are held *and* there is
    something to reveal.
    """

    index: int
    old_start: int | None
    new_start: int | None
    count: int | None
    expandable: bool


@dataclass(frozen=True)
class Hunk:
    """
    A run of rows with the position it claims.

    `old_start`/`new_start` are the 1-based number of the first line the hunk
    covers on that side, or `None` when its header gave no ranges. (The unified
    format writes an empty side as "the line before", `-0,0`; that is undone
    here and redone by `header`, so a start is always where the next line on
    that side would be.) `old_count`/`new_count` are counted from the rows, not
    copied from the header, so `header` is right even where the text was not.

    `complete` is false when the header declared more lines than have arrived:
    the text is still streaming, or was cut short.
    """

    old_start: int | None
    new_start: int | None
    rows: tuple[DiffRow, ...]
    section: str = ""
    complete: bool = True
    # A stream's open hunk shares one `_Deriver` with its later snapshots, so
    # that pairing a hunk that grew costs what is new: (the deriver, how many
    # of `rows` are settled). Not part of equality.
    _live: tuple[_Deriver, int] | None = field(default=None, repr=False, compare=False)

    @cached_property
    def old_count(self) -> int:
        return sum(1 for r in self.rows if r.kind in (RowKind.CONTEXT, RowKind.REMOVE))

    @cached_property
    def new_count(self) -> int:
        return sum(1 for r in self.rows if r.kind in (RowKind.CONTEXT, RowKind.ADD))

    @cached_property
    def added(self) -> int:
        return sum(1 for r in self.rows if r.kind is RowKind.ADD)

    @cached_property
    def removed(self) -> int:
        return sum(1 for r in self.rows if r.kind is RowKind.REMOVE)

    @cached_property
    def control_characters(self) -> bool:
        """
        Whether a line of this hunk holds a character a view draws a
        placeholder for: a control (`has_control`) or an invisible or
        bidirectional one (`has_invisible`).
        """
        return self.invisible_characters or any(
            has_control(r.text) for r in self.rows if r.kind is not RowKind.META
        )

    @cached_property
    def invisible_characters(self) -> bool:
        """Whether a line of this hunk holds an invisible or bidirectional character."""
        return any(has_invisible(r.text) for r in self.rows if r.kind is not RowKind.META)

    @property
    def header(self) -> str:
        """The `@@` line for this hunk, without a terminator."""
        if self.old_start is None or self.new_start is None:
            return "@@ " + self.section if self.section else "@@"
        text = (
            f"@@ -{_range(self.old_start, self.old_count)}"
            f" +{_range(self.new_start, self.new_count)} @@"
        )
        return f"{text} {self.section}" if self.section else text

    def terminator(self, index: int) -> str:
        """
        The line terminator row `index` really has: its `eol`, less the final
        newline when the next row is the no-newline marker. `""` for META.
        """
        row = self.rows[index]
        if row.kind is RowKind.META:
            return ""
        if index + 1 < len(self.rows) and self.rows[index + 1].kind is RowKind.META:
            return row.eol[:-1]
        return row.eol

    @cached_property
    def _derived(self) -> _Derived:
        if self._live is not None:
            return self._live[0].derive(self.rows, self._live[1])
        return _derive(self.rows)

    @property
    def side_by_side(self) -> tuple[SidePair, ...]:
        """The hunk as side-by-side rows; see the module docstring's pairing rule."""
        return self._derived[0]

    @property
    def spans(self) -> tuple[tuple[Span, ...], ...]:
        """
        Intra-line changed spans, one tuple per row of `rows` (empty for a row
        with none). Offsets are into that row's `text`.
        """
        return self._derived[1]

    @property
    def eol_rows(self) -> frozenset[int]:
        """
        The rows of a remove/add pair whose texts are the same characters:
        what changed is the line's ending (CRLF for LF, a closing newline
        gained or lost), which `text` does not hold. A view marks the end of
        these lines, since nothing else about the two rows differs.
        """
        return self._derived[2]

    def to_unified(self) -> str:
        out = [self.header, "\n"]
        for row in self.rows:
            if row.kind is RowKind.META:
                out += ["\\ ", row.text, "\n"]
            else:
                out += [row.kind.value, row.text, row.eol]
        return "".join(out)


@dataclass(frozen=True)
class FileDiff:
    """
    One file's changes.

    `label` is what a view titles the file with. `old_path`/`new_path` are as
    the diff text wrote them (`/dev/null`, `a/` and `b/` prefixes and all).
    `will_not_apply` is the host's to set -- this module cannot know it -- and
    is the label to show (pptmstr's "anchor not found in file"); empty means
    nothing is claimed. `header` holds the raw header lines of a parsed diff
    (`diff --git`, `index`, modes, `---`, `+++`) for a view that wants them --
    **and every other line of the file's text that is not a row**, in the
    order read: a mail's message and diffstat above the diff, prose above a
    header, and the lines listed again in `unread`. No line of a text given
    to `from_unified` is dropped: it is a row, a hunk's `@@` line, a line of
    `raw`, or here (review 3, item 6; blank lines outside a hunk excepted).
    """

    label: str
    hunks: tuple[Hunk, ...] = ()
    status: FileStatus = FileStatus.MODIFIED
    old_path: str = ""
    new_path: str = ""
    will_not_apply: str = ""
    header: tuple[str, ...] = ()
    #: Set when the text is in a form this module does not read as rows
    #: (`COMBINED`, `NOT_A_DIFF`): the file then has no hunks, and `raw` is
    #: its lines exactly as written, for a view to show as they are.
    dialect: str = ""
    raw: tuple[str, ...] = ()
    #: `"CRLF -> LF"` and the like when the two texts differ in line endings
    #: and in nothing else; see "Line endings" in the module docstring.
    line_endings: str = ""
    #: Lines of a parsed text that came after this file's first hunk began
    #: and were read as nothing: not a row, not a header of any kind (prose
    #: a model wrote under a hunk that had had all its lines, say). They are
    #: in `header` too, which holds every line of the file that is not a
    #: row; these are the ones a view should say it is not showing.
    unread: tuple[str, ...] = ()
    # The full texts as raw lines (terminators kept), when the diff was built
    # from them. Not part of equality: two diffs with the same rows are equal.
    _old_lines: tuple[str, ...] | None = field(default=None, repr=False, compare=False)
    _new_lines: tuple[str, ...] | None = field(default=None, repr=False, compare=False)

    @cached_property
    def added(self) -> int:
        return sum(h.added for h in self.hunks)

    @cached_property
    def removed(self) -> int:
        return sum(h.removed for h in self.hunks)

    @cached_property
    def control_characters(self) -> bool:
        """
        Whether a line shown for this file -- a row, or a line of `raw` --
        holds a character a view draws a placeholder for (`has_control`,
        `has_invisible`): the view says so in the file's header.
        """
        return (
            self.invisible_characters
            or any(h.control_characters for h in self.hunks)
            or any(has_control(line) for line in self.raw)
        )

    @cached_property
    def invisible_characters(self) -> bool:
        """
        Whether a line shown for this file holds an invisible or
        bidirectional control character (`has_invisible`). The header's
        warning names this kind in words of its own: such a character is not
        noise in a file, it is text that reads differently from what it is.
        """
        return any(h.invisible_characters for h in self.hunks) or any(
            has_invisible(line) for line in self.raw
        )

    @property
    def expandable(self) -> bool:
        """Whether collapsed context can be revealed at all (full texts held)."""
        return self._old_lines is not None and self._new_lines is not None

    @cached_property
    def gaps(self) -> tuple[Gap, ...]:
        """
        `len(hunks) + 1` gaps -- before each hunk and after the last -- or `()`
        for a file with no hunks. A gap of `count == 0` is listed so that
        `gaps[i]` is always the gap before hunk `i`.
        """
        if not self.hunks:
            return ()
        out: list[Gap] = []
        old_at: int | None = 1
        new_at: int | None = 1
        for i, hunk in enumerate(self.hunks):
            count = None if old_at is None or hunk.old_start is None else hunk.old_start - old_at
            if count is not None and count < 0:
                count = None  # overlapping or out-of-order hunks: nothing is known
            out.append(Gap(i, old_at, new_at, count, self.expandable and bool(count)))
            old_at = None if hunk.old_start is None else hunk.old_start + hunk.old_count
            new_at = None if hunk.new_start is None else hunk.new_start + hunk.new_count
        tail: int | None = None
        if self._old_lines is not None and old_at is not None:
            tail = len(self._old_lines) - (old_at - 1)
        out.append(Gap(len(self.hunks), old_at, new_at, tail, self.expandable and bool(tail)))
        return tuple(out)

    def expand(
        self, gap: int, lines: int | None = 20, edge: Literal["top", "bottom"] = "top"
    ) -> FileDiff:
        """
        A new `FileDiff` with up to `lines` more context lines shown in `gap`
        (`None` for all of them).

        `edge="top"` reveals the first lines of the gap, attached to the hunk
        above; `"bottom"` reveals the last, attached to the hunk below. The gap
        before the first hunk and the one after the last have one neighbour and
        ignore `edge`. When a gap between two hunks is used up the two become
        one hunk, so `gaps` and `hunks` renumber: re-read them from the result.

        Raises `ContextUnavailable` when the full texts are not held.
        """
        old, new = self._old_lines, self._new_lines
        if old is None or new is None:
            raise ContextUnavailable(
                "context outside the hunks is not available: this diff was read from "
                "unified text, which does not contain it"
            )
        if not 0 <= gap < len(self.gaps):
            raise IndexError(f"no gap {gap}: this file has {len(self.gaps)}")
        found = self.gaps[gap]
        count = found.count or 0
        take = count if lines is None else max(0, min(lines, count))
        if take == 0:
            return self
        assert found.old_start is not None and found.new_start is not None
        hunks = list(self.hunks)
        from_top = (edge == "top" or gap == len(hunks)) and gap != 0
        skip = 0 if from_top else count - take
        shown = _context_rows(old, found.old_start + skip, found.new_start + skip, take)
        above = hunks[gap - 1] if gap > 0 else None
        below = hunks[gap] if gap < len(hunks) else None
        if above is not None and below is not None and take == count:
            hunks[gap - 1 : gap + 1] = [
                Hunk(above.old_start, above.new_start, above.rows + shown + below.rows)
            ]
        elif from_top:
            assert above is not None
            hunks[gap - 1] = replace(above, rows=above.rows + shown)
        else:
            assert below is not None
            hunks[gap] = Hunk(
                found.old_start + skip,
                found.new_start + skip,
                shown + below.rows,
                below.section,
                below.complete,
            )
        return replace(self, hunks=tuple(hunks))

    def apply(self, before: str | None) -> str | None:
        """
        The text this diff turns `before` into; `None` for a deleted file.

        Every CONTEXT and REMOVE row is checked against `before`, terminator
        included, and a mismatch raises `DiffApplyError`. So does a hunk with
        no ranges (there is nowhere to apply it) and a binary file.
        """
        if self.status is FileStatus.BINARY:
            raise DiffApplyError("a binary diff carries no content to apply")
        source = _split_lines(before or "")
        out: list[str] = []
        at = 0  # index into `source` of the next line not yet consumed
        for hunk in self.hunks:
            if hunk.old_start is None:
                raise DiffApplyError("a hunk with no line ranges cannot be placed")
            start = hunk.old_start - 1
            if start < at or start > len(source):
                raise DiffApplyError(f"hunk at old line {hunk.old_start} is out of order or range")
            out += source[at:start]
            at = start
            for i, row in enumerate(hunk.rows):
                if row.kind is RowKind.META:
                    continue
                raw = row.text + hunk.terminator(i)
                if row.kind is not RowKind.ADD:
                    if at >= len(source) or source[at] != raw:
                        raise DiffApplyError(
                            f"old line {at + 1} is not the line the diff expects there"
                        )
                    at += 1
                if row.kind is not RowKind.REMOVE:
                    out.append(raw)
        out += source[at:]
        if self.status is FileStatus.DELETED and not out:
            return None
        return "".join(out)

    def to_unified(self) -> str:
        """
        This file as unified-diff text. `Diff.from_unified` reads it back to
        the same rows. A file in a `dialect` is its `raw` lines.
        """
        if self.dialect:
            return "".join(line + "\n" for line in self.raw)
        out: list[str] = []
        if self.old_path or self.new_path:
            out.append(f"--- {self.old_path}\n+++ {self.new_path}\n")
        if self.status is FileStatus.BINARY:
            out.append(f"Binary files {self.old_path} and {self.new_path} differ\n")
        out += [h.to_unified() for h in self.hunks]
        return "".join(out)


@dataclass(frozen=True)
class Diff:
    """
    Some files' changes. Immutable: `expand` and `mark_will_not_apply` return a
    new one. Several diffs are joined by adding their `files`
    (`Diff(a.files + b.files)`), which is how a MultiEdit's fragments built by
    `from_texts` become one diff.

    `provisional` is set only on a `UnifiedDiffStream` snapshot, and says the
    last row of the last hunk came from a line whose newline has not arrived:
    its text may still grow and its kind may still change.
    """

    files: tuple[FileDiff, ...] = ()
    provisional: bool = False
    #: How many rows at the end of the last hunk may still change or go: the
    #: unfinished line (`provisional`) and at most two complete lines that
    #: the next line may turn into a file header. 0 outside a stream.
    unsettled: int = 0

    @cached_property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @cached_property
    def removed(self) -> int:
        return sum(f.removed for f in self.files)

    @classmethod
    def from_texts(
        cls,
        before: str | None,
        after: str | None,
        label: str = "",
        *,
        context: int = 3,
        will_not_apply: str = "",
        binary: bool = False,
    ) -> Diff:
        """
        The diff that turns `before` into `after`, as one file.

        `binary=True` is the host saying the content is not text: the file is
        `FileStatus.BINARY` with no hunks. It is never inferred -- a text with
        a NUL in it is diffed like any other.

        `before=None` is a new file and `after=None` a deleted one. `context`
        is the number of unchanged lines kept around each change (3 is what
        pptmstr asks `difflib` for). The line matching is `difflib`'s, run on
        what is left after the common leading and trailing lines are set aside
        -- which is what makes one edit in a long file cost the edit and not
        the file, and means the hunks are a valid diff but not always the
        byte-for-byte one `difflib.unified_diff` would print.
        """
        return cls((_file_from_texts(before, after, label, context, will_not_apply, binary),))

    @classmethod
    def from_edits(
        cls, edits: Iterable[tuple[str | None, str | None, str]], *, context: int = 3
    ) -> Diff:
        """
        Several `(before, after, label)` edits as one diff, a file each: what
        `from_texts` gives for each, joined. This is the way in for a host
        that holds the texts of a multi-part edit (pptmstr's MultiEdit:
        `[(e.old_string, e.new_string, f"edit {i}") ...]`), and such a host
        must not go through unified text instead -- see `from_unified`.

        Two things it does not do. There is no per-edit *will not apply*
        here: build the diff and then `mark_will_not_apply(label, file=i)`
        for the edit that will not. And each edit is diffed as a text of its
        own, so **its line numbers start at 1**: they are positions in the
        fragment, not in the file the edit is to be applied to (which this
        function is not given).
        """
        return cls(
            tuple(
                _file_from_texts(before, after, label, context, "")
                for before, after, label in edits
            )
        )

    @classmethod
    def from_unified(cls, text: str) -> Diff:
        """
        Read complete unified-diff text. See the module docstring for the
        dialects, and `UnifiedDiffStream` for text that is still arriving.

        **A host that holds the before and after texts must not use this**;
        `from_texts` and `from_edits` are for it. Unified text cannot say
        everything the texts do, and text made by `difflib.unified_diff` from
        `keepends=True` lines (pptmstr's `approval._unified`) says something
        false whenever a text has no closing newline. For the edits
        `("foo", "bar")` and `("x", "y")` joined as pptmstr joins them it is

            --- a/edit 1
            +++ b/edit 1
            @@ -1 +1 @@
            -foo+bar
            --- a/edit 2
            ...

        where `-foo+bar` is one physical line. It is read as what it says --
        one REMOVE row `foo+bar`, a hunk left `complete=False`, +0 -1 -- and
        cannot be read as anything better: nothing in the text says where
        `foo` ends. `from_edits` gives +1 -1 per edit. The same goes for a
        form feed or a lone carriage return, which `str.splitlines` cuts a
        line at and this module does not.
        """
        stream = UnifiedDiffStream()
        stream.feed(text)
        stream.close()
        return stream.diff

    def to_unified(self) -> str:
        return "".join(f.to_unified() for f in self.files)

    def rows(self) -> Iterator[tuple[int, int, DiffRow]]:
        """Every row as `(file index, hunk index, row)`, in order."""
        for f, file in enumerate(self.files):
            for h, hunk in enumerate(file.hunks):
                for row in hunk.rows:
                    yield f, h, row

    def expand(
        self,
        file: int,
        gap: int,
        lines: int | None = 20,
        edge: Literal["top", "bottom"] = "top",
    ) -> Diff:
        """`FileDiff.expand` on file `file`, returned as a new `Diff`."""
        grown = self.files[file].expand(gap, lines, edge)
        return replace(self, files=self.files[:file] + (grown,) + self.files[file + 1 :])

    def mark_will_not_apply(self, label: str, file: int | None = None) -> Diff:
        """A new `Diff` with `will_not_apply` set on file `file`, or on all."""
        return replace(
            self,
            files=tuple(
                replace(f, will_not_apply=label) if file is None or i == file else f
                for i, f in enumerate(self.files)
            ),
        )


# ---------------------------------------------------------------------------
# before / after
# ---------------------------------------------------------------------------


def _range(start: int, count: int) -> str:
    # The unified format's own conventions: an empty side names the line before
    # it, and a length of one is left out.
    if count == 0:
        return f"{start - 1},0"
    return str(start) if count == 1 else f"{start},{count}"


def _split_lines(text: str) -> list[str]:
    """`text` as raw lines, each keeping its `"\\n"`; the last may have none."""
    lines = text.split("\n")
    last = lines.pop()
    out = [line + "\n" for line in lines]
    if last:
        out.append(last)
    return out


def _row(kind: RowKind, raw: str, old_no: int | None, new_no: int | None) -> list[DiffRow]:
    """The row for raw line `raw`, and the marker row after it if it has no newline."""
    closed = raw.endswith("\n")
    body = raw[:-1] if closed else raw
    if body.endswith("\r"):
        row = DiffRow(kind, body[:-1], old_no, new_no, "\r\n")
    else:
        row = DiffRow(kind, body, old_no, new_no)
    return [row] if closed else [row, DiffRow(RowKind.META, NO_NEWLINE)]


def _context_rows(old: Sequence[str], old_no: int, new_no: int, count: int) -> tuple[DiffRow, ...]:
    out: list[DiffRow] = []
    for k in range(count):
        out += _row(RowKind.CONTEXT, old[old_no - 1 + k], old_no + k, new_no + k)
    return tuple(out)


def _prefixed(label: str) -> tuple[str, str]:
    # pptmstr's convention, kept so its labels read the same here: git's a/ b/
    # prefixes, except on an absolute path, where they would print "b//tmp/x".
    if not label or label.startswith("/"):
        return label, label
    return "a/" + label, "b/" + label


def _file_from_texts(
    before: str | None,
    after: str | None,
    label: str,
    context: int,
    will_not_apply: str,
    binary: bool = False,
) -> FileDiff:
    old_path, new_path = _prefixed(label)
    if before is None and after is not None:
        status, old_path = FileStatus.NEW, "/dev/null"
    elif after is None and before is not None:
        status, new_path = FileStatus.DELETED, "/dev/null"
    elif before == after:
        status = FileStatus.UNCHANGED
    else:
        status = FileStatus.MODIFIED
    if binary:
        return FileDiff(
            label, (), FileStatus.BINARY, old_path, new_path, will_not_apply=will_not_apply
        )
    a = _split_lines(before or "")
    b = _split_lines(after or "")
    hunks = tuple(_hunks(a, b, max(0, context)))
    endings = ""
    if before is not None and after is not None and before != after:
        if before.replace("\r\n", "\n") == after.replace("\r\n", "\n"):
            endings = f"{_endings(a)} -> {_endings(b)}"
    return FileDiff(
        label,
        hunks,
        status,
        old_path,
        new_path,
        will_not_apply,
        line_endings=endings,
        _old_lines=tuple(a),
        _new_lines=tuple(b),
    )


def _endings(lines: Sequence[str]) -> str:
    """How the lines of a text end: `"CRLF"`, `"LF"`, or `"mixed"`."""
    crlf = sum(1 for line in lines if line.endswith("\r\n"))
    lf = sum(1 for line in lines if line.endswith("\n")) - crlf
    return "mixed" if crlf and lf else "CRLF" if crlf else "LF"


_Op = tuple[str, int, int, int, int]


def _opcodes(a: list[str], b: list[str]) -> list[_Op]:
    """`SequenceMatcher` opcodes for a -> b, with common ends set aside first."""
    head = 0
    limit = min(len(a), len(b))
    while head < limit and a[head] == b[head]:
        head += 1
    tail = 0
    while tail < limit - head and a[len(a) - 1 - tail] == b[len(b) - 1 - tail]:
        tail += 1
    ops: list[_Op] = []
    if head:
        ops.append(("equal", 0, head, 0, head))
    middle_a = a[head : len(a) - tail]
    middle_b = b[head : len(b) - tail]
    if middle_a or middle_b:
        matcher = SequenceMatcher(None, middle_a, middle_b)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            ops.append((tag, i1 + head, i2 + head, j1 + head, j2 + head))
    if tail:
        ops.append(("equal", len(a) - tail, len(a), len(b) - tail, len(b)))
    return ops


def _hunks(a: list[str], b: list[str], context: int) -> Iterator[Hunk]:
    ops = _opcodes(a, b)
    if all(op[0] == "equal" for op in ops):
        return
    # `difflib.SequenceMatcher.get_grouped_opcodes`, over our own opcode list:
    # trim the equal runs at both ends to `context`, and split wherever an
    # equal run is longer than twice that.
    tag, i1, i2, j1, j2 = ops[0]
    if tag == "equal":
        ops[0] = (tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)
    tag, i1, i2, j1, j2 = ops[-1]
    if tag == "equal":
        ops[-1] = (tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context))
    group: list[_Op] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal" and i2 - i1 > 2 * context and group:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            yield _hunk(a, b, group)
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        yield _hunk(a, b, group)


def _hunk(a: list[str], b: list[str], group: list[_Op]) -> Hunk:
    rows: list[DiffRow] = []
    for tag, i1, i2, j1, j2 in group:
        if tag == "equal":
            for k in range(i2 - i1):
                rows += _row(RowKind.CONTEXT, a[i1 + k], i1 + k + 1, j1 + k + 1)
            continue
        for i in range(i1, i2):
            rows += _row(RowKind.REMOVE, a[i], i + 1, None)
        for j in range(j1, j2):
            rows += _row(RowKind.ADD, b[j], None, j + 1)
    return Hunk(group[0][1] + 1, group[0][3] + 1, tuple(rows))


# ---------------------------------------------------------------------------
# intra-line spans and side-by-side pairing
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")


def tokenize(text: str) -> list[Span]:
    """
    `text` as token spans covering every character: a run of word characters,
    a run of whitespace, or one other character.
    """
    return [m.span() for m in _TOKEN.finditer(text)]


@lru_cache(maxsize=8192)
def _compare(a: str, b: str) -> tuple[float, tuple[Span, ...], tuple[Span, ...]]:
    """Similarity of two lines, and the spans of each that the other lacks."""
    if a == b:
        return 1.0, (), ()
    if len(a) > MAX_INTRALINE_CHARS or len(b) > MAX_INTRALINE_CHARS:
        return 0.0, (), ()
    spans_a, spans_b = tokenize(a), tokenize(b)
    tokens_a = [a[s:e] for s, e in spans_a]
    tokens_b = [b[s:e] for s, e in spans_b]
    matcher = SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
    total = sum(len(t) for t in tokens_a + tokens_b if not t.isspace())
    kept = 0
    out_a: list[Span] = []
    out_b: list[Span] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            kept += sum(len(t) for t in tokens_a[i1:i2] if not t.isspace())
            continue
        if i2 > i1:
            out_a.append((spans_a[i1][0], spans_a[i2 - 1][1]))
        if j2 > j1:
            out_b.append((spans_b[j1][0], spans_b[j2 - 1][1]))
    similarity = 2.0 * kept / total if total else 1.0
    return similarity, tuple(out_a), tuple(out_b)


def _align(
    rows: Sequence[DiffRow], removes: list[int], adds: list[int], budget: list[int]
) -> list[tuple[int, int]]:
    """
    Which remove is the same line as which add: `(remove row, add row)` index
    pairs, rising on both sides, each at or above the similarity floor.
    `budget[0]` is what the hunk has left to spend and is drawn down here.
    """

    def similar(i: int, j: int) -> float:
        a, b = rows[removes[i]].text, rows[adds[j]].text
        if a == b:
            # Free, so not charged: a pair of equal lines is what a changed
            # line ending looks like, and a long file of them spent the
            # budget and left its last pairs unmarked (review 3, item 10).
            return 1.0
        cost = len(a) + len(b)
        if budget[0] < cost:
            return 0.0
        budget[0] -= cost
        return _compare(a, b)[0]

    n, m = len(removes), len(adds)
    if n * m > ALIGN_CELLS:
        return [
            (removes[k], adds[k]) for k in range(min(n, m)) if similar(k, k) >= SIMILARITY_FLOOR
        ]
    score = [[similar(i, j) for j in range(m)] for i in range(n)]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            value = max(best[i + 1][j], best[i][j + 1])
            if score[i][j] >= SIMILARITY_FLOOR:
                value = max(value, score[i][j] + best[i + 1][j + 1])
            best[i][j] = value
    out: list[tuple[int, int]] = []
    i = j = 0
    while i < n and j < m:
        if score[i][j] >= SIMILARITY_FLOOR and best[i][j] == score[i][j] + best[i + 1][j + 1]:
            out.append((removes[i], adds[j]))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1
    return out


_Derived = tuple[tuple[SidePair, ...], tuple[tuple[Span, ...], ...], frozenset[int]]

#: Rows walked by `_Deriver.derive`, ever: what the count-based tests read.
_DERIVED_ROWS = [0]


class _Deriver:
    """
    Side-by-side pairs, intra-line spans and ending-only rows for one hunk's
    rows -- resumable, for a hunk that grows.

    A hunk built once (`from_texts`, a closed hunk of a parsed text) is
    derived in one walk. A stream's *open* hunk is a new `Hunk` in every
    snapshot, and until review 1 (item 7) each was derived whole: 2.4
    microseconds a row, per line received, for the whole length of the hunk.
    The stream now gives every snapshot of its open hunk the same `_Deriver`,
    which keeps what cannot change and walks only what follows it.

    *What cannot change.* A change group is a run of removes and the adds
    after it; nothing before a group is touched by anything in or after it.
    So the walk can be resumed at any row where no group is open: after a
    context row, and after an add that no remove precedes (it pairs with
    nothing, whatever arrives). The point is kept only if the row *after* it
    is settled too -- a row's `\\ No newline` marker is found by looking one
    row ahead -- and settled means the stream will not take it back
    (`Diff.unsettled`).

    *Inside a run of removes too* (review 3, item 8). A remove with no add
    after it yet is laid beside nothing, and another remove arriving does
    not change that; so the walk also resumes inside an open run of removes,
    carrying the run (`removes`) and where its pairs begin (`group`). Only
    the first add takes those pairs back, to align the group as one. Until
    this, the run was walked again for every line that joined it: a file
    deleted line by line cost 1,125,750 rows walked for 1,500 lines.

    *What is still linear:* a group that has its adds and no context after
    it yet. An add may pair with any remove of the group, so the group is
    aligned again for each line that arrives while it is open (`_align`,
    memoised by text; position only, past `ALIGN_CELLS`).
    """

    __slots__ = (
        "anchor",
        "budget",
        "done",
        "eols",
        "frozen",
        "group",
        "pairs",
        "removes",
        "spans",
    )

    def __init__(self) -> None:
        self.done = 0  # rows behind the resume point
        self.anchor: DiffRow | None = None  # rows[done - 1], to know the hunk again
        # The open run of removes behind the resume point (no add has
        # followed it), and the length `pairs` had when it began.
        self.removes: list[int] = []
        self.group = 0
        self.pairs: list[SidePair] = []
        self.spans: list[tuple[Span, ...]] = []
        self.eols: set[int] = set()
        self.frozen: frozenset[int] = frozenset()
        self.budget = INTRALINE_BUDGET

    def derive(self, rows: tuple[DiffRow, ...], settled: int) -> _Derived:
        """
        The derived values for `rows`, of which the first `settled` are
        final. Rows that are not an extension of what was kept (an older
        snapshot asked late, a different hunk) are derived from scratch.
        """
        if self.done > len(rows) or (self.done and rows[self.done - 1] is not self.anchor):
            return _Deriver().derive(rows, 0)
        pairs, spans = self.pairs, self.spans
        budget = [self.budget]
        fresh: list[int] = []  # ending-only rows found past the resume point

        def meta_after(index: int | None) -> int | None:
            if index is None or index + 1 >= len(rows):
                return None
            return index + 1 if rows[index + 1].kind is RowKind.META else None

        def emit(left: int | None, right: int | None) -> None:
            pairs.append(SidePair(left, right))
            left_meta, right_meta = meta_after(left), meta_after(right)
            if left_meta is not None or right_meta is not None:
                pairs.append(SidePair(left_meta, right_meta))

        def flush(removes: list[int], adds: list[int]) -> None:
            matched = _align(rows, removes, adds, budget) if removes and adds else []
            r = a = 0
            for left, right in [*matched, (-1, -1)]:
                # The unmatched lines ahead of this pair, beside each other by position.
                loose_r: list[int] = []
                while r < len(removes) and removes[r] != left:
                    loose_r.append(removes[r])
                    r += 1
                loose_a: list[int] = []
                while a < len(adds) and adds[a] != right:
                    loose_a.append(adds[a])
                    a += 1
                for k in range(max(len(loose_r), len(loose_a))):
                    emit(
                        loose_r[k] if k < len(loose_r) else None,
                        loose_a[k] if k < len(loose_a) else None,
                    )
                if left >= 0:
                    _, spans[left], spans[right] = _compare(rows[left].text, rows[right].text)
                    if rows[left].text == rows[right].text:
                        # The same characters, removed and added: what differs
                        # is how the line ends (`Hunk.eol_rows`).
                        fresh.extend((left, right))
                    emit(left, right)
                    r, a = r + 1, a + 1

        # `removes` is the carried list itself, appended to in place: what is
        # added past the last resume point is cut off again below. A group
        # that closes leaves it be and starts a list of its own.
        removes = self.removes
        group = self.group
        adds: list[int] = []
        kept_run = (removes, len(removes), group)
        spoiled = False  # the kept run's pairs were taken back for an add
        kept = (self.done, len(pairs), self.budget)
        for index in range(self.done, len(rows)):
            row = rows[index]
            spans.append(())
            if row.kind is RowKind.META:
                if index == 0 or rows[index - 1].kind is RowKind.META:
                    pairs.append(SidePair(index, index))  # a marker with no line: not ours
            elif row.kind is RowKind.REMOVE:
                if adds:
                    flush(removes, adds)
                    removes, adds = [], []
                if not removes:
                    group = len(pairs)
                removes.append(index)
                # Beside nothing, for as long as no add follows the run: what
                # `flush` does with removes alone.
                emit(index, None)
            elif row.kind is RowKind.ADD:
                if removes:
                    if not adds:
                        del pairs[group:]  # the run is aligned with its adds, as one group
                        spoiled = spoiled or removes is kept_run[0]
                    adds.append(index)
                else:
                    emit(None, index)  # what `flush` does with adds alone
            else:
                if adds:
                    flush(removes, adds)
                removes, adds = [], []
                emit(index, index)
            if not adds and index + 1 < settled:
                kept = (index + 1, len(pairs), budget[0])
                kept_run = (removes, len(removes), group)
                spoiled = False
                if fresh:
                    self.eols.update(fresh)
                    self.frozen = frozenset(self.eols)
                    fresh.clear()
        _DERIVED_ROWS[0] += len(rows) - self.done
        if adds:
            flush(removes, adds)
        out = (tuple(pairs), tuple(spans), self.frozen.union(fresh) if fresh else self.frozen)
        # Keep what is behind the last resume point; the rest is walked again.
        self.done, cut, self.budget = kept
        self.removes, run, self.group = kept_run
        del self.removes[run:]
        if spoiled and run:
            # An add followed the run that the resume point is inside, and
            # the run's pairs went to make room for the aligned group. Behind
            # the resume point they are what they were: each remove beside
            # nothing. (Only on this path is the run walked again.)
            del pairs[self.group :]
            for index in self.removes:
                emit(index, None)
                spans[index] = ()  # (a span it was given was the pairing's)
        del pairs[cut:]
        del spans[self.done :]
        self.anchor = rows[self.done - 1] if self.done else None
        return out


def _derive(rows: tuple[DiffRow, ...]) -> _Derived:
    return _Deriver().derive(rows, 0)


# ---------------------------------------------------------------------------
# unified text
# ---------------------------------------------------------------------------

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_GIT_HEADERS = (
    "index ",
    "old mode ",
    "new mode ",
    "new file mode ",
    "deleted file mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "GIT binary patch",
)
_DIFF_LINES = ("diff --git ", "diff --cc ", "diff --combined ")
_COMBINED_LINES = ("diff --cc ", "diff --combined ")
_SIGNATURE = "-- "
_GIT_VERSION = re.compile(r"^\d+\.\d+[\w.+() -]*$")
# The first line of a `git format-patch` mail: `From <object name> <date>`,
# the name being 40 hexadecimal digits (64 in a SHA-256 repository).
_MBOX_FROM = re.compile(r"^From (?:[0-9a-f]{40}|[0-9a-f]{64}) \S")


def _is_old_header(line: str) -> bool:
    return line.startswith("--- ") or line == "---"


def _path(line: str) -> str:
    # `--- a/x<TAB>2026-10-07 ...`: GNU diff and difflib (given dates) add a
    # timestamp after a tab.
    return line[4:].split("\t", 1)[0]


def _label(old_path: str, new_path: str) -> str:
    path = new_path if new_path and new_path != "/dev/null" else old_path
    if path == "/dev/null":
        return ""
    old_ok = old_path in ("", "/dev/null") or old_path.startswith("a/")
    new_ok = new_path in ("", "/dev/null") or new_path.startswith("b/")
    if old_ok and new_ok and path[:2] in ("a/", "b/"):
        return path[2:]
    return path


class _FileBuilder:
    def __init__(self) -> None:
        self.old_path = ""
        self.new_path = ""
        self.git_name = ""
        self.header: list[str] = []
        self.hunks: list[Hunk] = []  # closed ones
        self.new = False
        self.deleted = False
        self.binary = False
        # The file's lines as written, for a dialect that is not read as rows
        # (`FileDiff.dialect`); `None` for a file that is.
        self.raw: list[str] | None = None
        self.dialect = ""
        self.unread: list[str] = []

    @property
    def headed(self) -> bool:
        """Whether a `---` or `+++` line has been seen for this file."""
        return bool(self.old_path or self.new_path)

    def copy(self) -> _FileBuilder:
        made = _FileBuilder()
        vars(made).update(vars(self))
        made.header = list(self.header)
        made.hunks = list(self.hunks)
        made.raw = None if self.raw is None else list(self.raw)
        made.unread = list(self.unread)
        return made

    def build(self, open_hunk: Hunk | None) -> FileDiff:
        hunks = tuple(self.hunks) if open_hunk is None else (*self.hunks, open_hunk)
        if self.binary:
            status = FileStatus.BINARY
        elif self.new or self.old_path == "/dev/null":
            status = FileStatus.NEW
        elif self.deleted or self.new_path == "/dev/null":
            status = FileStatus.DELETED
        else:
            status = FileStatus.MODIFIED
        label = _label(self.old_path, self.new_path) or self.git_name
        return FileDiff(
            label,
            hunks,
            status,
            self.old_path,
            self.new_path,
            header=tuple(self.header),
            dialect=self.dialect,
            raw=() if self.raw is None else tuple(self.raw),
            unread=tuple(self.unread),
        )


def _git_name(rest: str) -> str:
    """
    The path in `diff --git a/<path> b/<path>`, the two being the same path
    unless the file was renamed. Split in the middle when the halves agree,
    so a path with ` b/` inside it (`a b/c`) is read whole; otherwise at the
    last ` b/`, which is right for a rename to a path without one.
    """
    if not rest.startswith("a/"):
        return ""
    half = (len(rest) - 5) // 2
    if half > 0 and len(rest) == 2 * half + 5:
        path = rest[2 : 2 + half]
        if rest == f"a/{path} b/{path}":
            return path
    return rest.rsplit(" b/", 1)[1] if " b/" in rest else ""


class UnifiedDiffStream:
    """
    Unified-diff text read as it arrives.

        stream = UnifiedDiffStream()
        stream.feed(chunk)          # any split: mid-line, mid-header
        stream.diff                 # the Diff of everything fed so far
        stream.close()              # no more text will come

    `set_text(whole)` is for a host that holds the whole text each frame: it
    feeds the new suffix when `whole` extends what was read, and starts over
    when it does not. The invariant this class keeps, and its cost, are in the
    module docstring under "The streaming invariant".

    **`close()`** says the text is complete, and it matters: a line that may
    yet turn out to be the first of a file header (`--- x` after a hunk's
    rows), or a mail signature (`-- `), is decided by the line after it, and
    the last line of a text has none. Until `close`, `diff` shows such a line
    the way it most likely is and counts it in `Diff.unsettled`; after it,
    the line is what it must be with nothing following, an unfinished last
    line is a line, and `unsettled` is 0. `Diff.from_unified` closes. Text fed
    after a close is read together with what came before, from the start.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._text = ""
        self._tail = ""  # the last line, while its newline has not arrived
        self._closed: list[FileDiff] = []
        self._file: _FileBuilder | None = None
        # The open hunk. `_left` is the declared budget still unmet, `None` for
        # a hunk whose header gave no ranges.
        self._rows: list[DiffRow] | None = None
        self._start: tuple[int, int] | None = None
        self._section = ""
        self._next: tuple[int, int] | None = None
        self._left: tuple[int, int] | None = None
        # Whether a line beginning +, - or a space still belongs to the open
        # hunk once its budget is spent (a miscounted header).
        self._accepting = False
        self._seen_any = False
        self._controls = False  # whether a row of the open hunk has a control character
        self._invisibles = False  # ... or an invisible or bidirectional one
        self._deriver: _Deriver | None = None  # the open hunk's pairing, kept between snapshots
        # Complete lines not yet decided, because the next line decides them:
        # `--- x` (and then `+++ y`), or `-- `. At most two. See `_lookahead`.
        self._held: list[tuple[str, str]] = []
        self._ended = False  # `close()` was called
        # Lines read before anything that is a diff: candidates for the
        # context above a model's unmarked fragment (`None` once that is
        # ruled out), and every line so far, for a text that is no diff.
        self._preamble: list[tuple[str, str]] | None = []
        self._raw: list[str] | None = []
        self._raw_ink = False
        # Lines read as nothing while no file was open (a mail's message,
        # prose above a header): the next file's first `header` lines.
        self._loose: list[str] = []
        self._snapshot: Diff | None = None

    @property
    def text(self) -> str:
        """Everything fed so far."""
        return self._text

    @property
    def closed(self) -> bool:
        """Whether `close()` has been called since the last text arrived."""
        return self._ended

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        if self._ended:
            chunk = self._text + chunk
            self.reset()
        self._text += chunk
        self._snapshot = None
        lines = (self._tail + chunk).split("\n")
        self._tail = lines.pop()
        for line in lines:
            self._line(line)

    def set_text(self, text: str) -> None:
        if text.startswith(self._text):
            self.feed(text[len(self._text) :])
        else:
            self.reset()
            self.feed(text)

    def close(self) -> None:
        """The text is complete: settle what was waiting on a next line."""
        if self._ended:
            return
        self._ended = True
        self._snapshot = None
        if self._tail:
            tail, self._tail = self._tail, ""
            self._line(tail)
        if self._held:
            self._resolve(final=True)

    @property
    def diff(self) -> Diff:
        if self._snapshot is None:
            self._snapshot = self._build()
        return self._snapshot

    # -- snapshot -----------------------------------------------------------

    def _build(self) -> Diff:
        if not self._held:
            return self._built(0)
        # Lines are waiting on the one after them. The snapshot shows them as
        # what they most likely are (`_resolve`), worked out on a copy of the
        # parser's state that is thrown away: the real decision is the next
        # line's. This copies the open hunk's rows, and happens only for the
        # snapshots taken while a `---` line is the last one read.
        saved = dict(vars(self))
        rows = self._rows
        working = None if rows is None else list(rows)
        self._rows = working
        self._closed = list(self._closed)
        self._file = None if self._file is None else self._file.copy()
        self._preamble = None if self._preamble is None else list(self._preamble)
        self._raw = None if self._raw is None else list(self._raw)
        self._loose = list(self._loose)
        try:
            self._resolve(final=False)
            shown = 0
            if working is not None and self._rows is working and rows is not None:
                shown = len(working) - len(rows)
            return self._built(shown)
        finally:
            vars(self).update(saved)

    def _built(self, unsettled: int) -> Diff:
        extra = self._tail_row()
        if extra is not None:
            unsettled += 1
        if self._file is None:
            if not self._closed and self._raw and self._raw_ink:
                # Something was written and none of it is a diff: shown as it
                # is, never as nothing (review 1, item 10).
                return Diff((FileDiff("", dialect=NOT_A_DIFF, raw=tuple(self._raw)),))
            return Diff(tuple(self._closed))
        open_hunk: Hunk | None = None
        if self._rows is not None:
            rows = tuple(self._rows) if extra is None else (*self._rows, extra)
            open_hunk = self._make_hunk(rows, len(rows) - unsettled)
        current = self._file.build(open_hunk)
        return Diff((*self._closed, current), provisional=extra is not None, unsettled=unsettled)

    def _make_hunk(self, rows: tuple[DiffRow, ...], settled: int | None = None) -> Hunk:
        old, new = self._start if self._start is not None else (None, None)
        complete = self._left is None or (self._left[0] <= 0 and self._left[1] <= 0)
        live: tuple[_Deriver, int] | None = None
        if settled is not None and self._deriver is not None:
            live = (self._deriver, settled)
        hunk = Hunk(old, new, rows, self._section, complete, live)
        if self._start is not None and self._next is not None and self._rows is not None:
            # The counts are known without counting, and are handed to the
            # hunk. `Hunk.old_count` and `new_count` are sums over the rows,
            # cached per hunk; the open hunk is a new object in every
            # snapshot, and `FileDiff.gaps` asks for them, so a view of a
            # stream paid a pass over the whole hunk for each line that
            # arrived (by profile 0.29 of 0.33 s for 200 lines appended to a
            # hunk of 2,000). `_next` has advanced by one for every content
            # row read (`_content_row`); the unfinished last line, if `rows`
            # ends with it, is not in that and is added here.
            old_count = self._next[0] - self._start[0]
            new_count = self._next[1] - self._start[1]
            for row in rows[len(self._rows) :]:
                old_count += row.kind is not RowKind.ADD
                new_count += row.kind is not RowKind.REMOVE
            vars(hunk)["old_count"] = old_count
            vars(hunk)["new_count"] = new_count
        if self._rows is not None:
            # Likewise known without a pass over the hunk: see `_content_row`.
            late = rows[len(self._rows) :]
            invisible = self._invisibles or any(has_invisible(row.text) for row in late)
            vars(hunk)["invisible_characters"] = invisible
            vars(hunk)["control_characters"] = (
                invisible or self._controls or any(has_control(row.text) for row in late)
            )
        return hunk

    def _tail_row(self) -> DiffRow | None:
        """The unfinished last line as a row, if it can only be one."""
        line = self._tail
        if not line or self._rows is None or line[0] not in "+- ":
            return None
        if not (self._in_budget() or self._accepting):
            return None
        return self._content_row(line.removesuffix("\r"), "\n", advance=False)

    # -- state --------------------------------------------------------------

    def _in_budget(self) -> bool:
        return self._left is not None and (self._left[0] > 0 or self._left[1] > 0)

    def _content_ok(self) -> bool:
        """Whether a content line would join the open hunk."""
        return self._rows is not None and (self._in_budget() or self._accepting)

    def _close_hunk(self) -> None:
        if self._rows is not None and self._file is not None:
            self._file.hunks.append(self._make_hunk(tuple(self._rows), len(self._rows)))
        self._rows = None
        self._deriver = None
        self._start = self._next = self._left = None
        self._section = ""
        self._accepting = False

    def _new_file(self) -> _FileBuilder:
        self._close_hunk()
        if self._file is not None:
            self._closed.append(self._file.build(None))
        self._file = _FileBuilder()
        if self._preamble:
            # Lines above the first thing that is a diff, which turned out
            # not to be a fragment's context: kept, above the file's own.
            self._loose += [text for text, _ in self._preamble if text.strip()]
        self._file.header, self._loose = self._loose, []
        self._preamble = None
        self._raw = None
        return self._file

    def _stray(self, line: str, unread: bool = True) -> None:
        """
        Keep a line that was read as nothing: **no line is dropped** (review
        3, item 6). It goes among the open file's `header` lines -- and in
        its `unread`, which a view reports, unless `unread` is false (a line
        that belongs above or below the diff: a mail's signature) -- or, with
        no file open, waits for the next one. Blank lines are not kept.
        """
        if not line.strip():
            return
        file = self._file
        if file is None:
            self._loose.append(line)
            return
        (file.raw if file.raw is not None else file.header).append(line)
        if unread and file.raw is None and (file.hunks or self._rows is not None):
            file.unread.append(line)

    def _open_hunk(
        self, start: tuple[int, int] | None, left: tuple[int, int] | None, section: str
    ) -> None:
        if self._file is None:
            self._new_file()
        else:
            self._close_hunk()
        self._rows = []
        self._deriver = _Deriver()
        self._controls = False
        self._invisibles = False
        self._start = self._next = start
        self._left = left
        self._section = section
        self._accepting = True

    def _content_row(self, line: str, eol: str, advance: bool = True) -> DiffRow:
        """The row for a content line (marker first, or blank, or unmarked)."""
        kind = {"+": RowKind.ADD, "-": RowKind.REMOVE}.get(line[:1], RowKind.CONTEXT)
        text = line[1:] if line[:1] in ("+", "-", " ") else line
        old = kind is not RowKind.ADD
        new = kind is not RowKind.REMOVE
        old_no = new_no = None
        if self._next is not None:
            old_no = self._next[0] if old else None
            new_no = self._next[1] if new else None
        if advance:
            if self._next is not None:
                self._next = (self._next[0] + old, self._next[1] + new)
            if self._left is not None:
                self._left = (self._left[0] - old, self._left[1] - new)
            self._controls = self._controls or has_control(text)
            self._invisibles = self._invisibles or has_invisible(text)
        return DiffRow(kind, text, old_no, new_no, eol)

    def _content(self, line: str, eol: str) -> None:
        assert self._rows is not None
        self._rows.append(self._content_row(line, eol))
        self._seen_any = True

    def _old_header(self, line: str) -> None:
        """`line` is a `---` file header: the file it opens, or the open one's."""
        file = self._file
        if (
            file is None
            or file.hunks
            or self._rows is not None
            or file.headed
            or file.raw is not None
        ):
            file = self._new_file()
        file.old_path = _path(line)
        file.header.append(line)
        self._seen_any = True

    # -- one complete line --------------------------------------------------

    def _line(self, raw: str) -> None:
        if raw.endswith("\r"):
            self._take(raw[:-1], "\r\n")
        else:
            self._take(raw, "\n")

    def _take(self, line: str, eol: str) -> None:
        if self._raw is not None and self._file is None:
            self._raw.append(line if eol == "\n" else line + "\r")
            self._raw_ink = self._raw_ink or bool(line.strip())
        self._route(line, eol)

    def _route(self, line: str, eol: str) -> None:
        # Apart from `_take` because a held line is routed a second time once
        # the line after it has been read, and is one line of the text: it
        # was in `_raw` twice (a text that was no diff, with a `---` in it,
        # was shown with the line under the `---` doubled).
        file = self._file
        if file is not None and file.raw is not None and not line.startswith(_DIFF_LINES):
            file.raw.append(line if eol == "\n" else line + "\r")
            return
        if self._held:
            self._lookahead(line, eol)
        elif self._holds(line):
            self._held.append((line, eol))
        else:
            self._plain(line, eol)

    def _plain(self, line: str, eol: str) -> None:
        blank = not line
        try:
            self._dispatch(line, eol)
        finally:
            self._seen_any = self._seen_any or not blank

    def _holds(self, line: str) -> bool:
        """Whether `line` cannot be decided until the next line is read."""
        if _is_old_header(line):
            return True
        # A mail's signature, `-- ` and then git's version: only where the
        # declared lines of a hunk have all arrived, so it cannot be owed.
        return (
            line == _SIGNATURE
            and self._rows is not None
            and self._left is not None
            and not self._in_budget()
            and self._accepting
        )

    def _lookahead(self, line: str, eol: str) -> None:
        """
        Decide the held line(s) now that `line` has followed, then read `line`.

        The rules, which are review 1's decisions (items 2, 3 and 8):

        - `--- X`, `+++ Y`, `@@...`, one straight after the other, inside a
          hunk's declared lengths: **counts decide** (review 3, item 2). If
          one removed and one added line are exactly what the hunk is still
          owed, the two lines are those rows and the `@@` is the next hunk:
          that is an honest context-free diff (`diff -U0`) of a file in
          which `-- x` became `++ y`, and reading it as a header closed the
          hunk empty and filed the rest of the file's changes under a file
          named `y`. Otherwise the three are a file header, though lines are
          still owed: a hunk header that over-declares its lengths is common
          (pptmstr's own, whenever an edit has no closing newline -- there
          the old side is already spent when `--- a/edit 2` arrives).
        - Outside declared lengths, `--- X` then `+++ Y` is a file header
          without waiting for the `@@` (a model leaves it out).
        - `--- X` followed by anything else is the removal of `-- X` if a
          hunk is taking lines; else a file header with no `+++` if it names
          a path; else (a bare `---`, as before a mail's diffstat) nothing.
        - `-- ` followed by a version number is the end of a mailed patch.
        """
        held = self._held
        first, first_eol = held[0]
        if first == _SIGNATURE:
            held.clear()
            if _GIT_VERSION.match(line):
                self._accepting = False
                self._stray(first, unread=False)
                self._stray(line, unread=False)
                return
            self._content(first, first_eol)
            self._route(line, eol)
            return
        if len(held) == 1:
            if line.startswith("+++ ") or line == "+++":
                if self._rows is not None and self._in_budget():
                    held.append((line, eol))
                    return
                held.clear()
                self._old_header(first)
                self._plain(line, eol)
                return
            held.clear()
            self._alone(first, first_eol)
            self._route(line, eol)
            return
        second, second_eol = held[1]
        held.clear()
        if line.startswith("@@") and self._left != (1, 1):
            self._old_header(first)
            self._plain(second, second_eol)
            self._plain(line, eol)
            return
        self._content(first, first_eol)
        self._route(second, second_eol)
        self._route(line, eol)

    def _alone(self, line: str, eol: str) -> None:
        """
        A `---` line that no `+++` followed. **It opens no file** (review 3,
        item 6: `--- FAIL: TestX (0.00s)`, in test output put in a `diff`
        fence, was a file header, and the lines around it were lost). With a
        hunk taking lines it is the removal of `-- X`. Otherwise it is a
        line like any unmarked one: above anything that is a diff, it waits
        with the lines that may be a fragment's context (and is the removal
        of `-- X` there if a `+`/`-` line follows); anywhere else it is kept
        and read as nothing.
        """
        if self._content_ok():
            self._content(line, eol)
        elif line == "---":
            # A rule in a mail or in prose: what is above it is a message,
            # not the context of a fragment.
            if self._file is None and self._preamble:
                self._loose += [text for text, _ in self._preamble if text.strip()]
            self._preamble = None
            self._stray(line, unread=False)
        elif self._file is None and self._preamble is not None:
            self._preamble.append((line, eol))
        else:
            self._stray(line)

    def _resolve(self, final: bool) -> None:
        """
        Decide the held lines with no next line to go by. `final` is the end
        of the text: they are what they are with nothing after them. Not
        final is a snapshot of a stream, which shows the likelier reading and
        no row it would probably take back: inside a hunk's declared lengths
        a `---` line is content (and counted in `Diff.unsettled`); outside
        them it is the next file's header, and `-- ` is a signature.
        """
        held, self._held = self._held, []
        first, first_eol = held[0]
        if first == _SIGNATURE:
            if final:
                self._content(first, first_eol)
        elif len(held) == 2:
            self._content(first, first_eol)
            self._route(*held[1])
        elif final or (self._rows is not None and self._in_budget()):
            self._alone(first, first_eol)
        elif first != "---":
            # Not the end, and outside declared lengths: most likely the
            # first line of a header whose `+++` line is the next to come.
            self._old_header(first)

    def _dispatch(self, line: str, eol: str) -> None:
        rows = self._rows
        if line.startswith(_COMBINED_LINES):
            self._raw_file(line, COMBINED)
            return
        if line.startswith("@@@"):
            # A combined diff's hunk: two marker columns, which this module
            # does not read (review 1, item 9). The file becomes its lines.
            self._raw_file(line, COMBINED, keep=True)
            return
        if line.startswith("@@"):
            self._hunk_header(line)
            return
        if line.startswith("\\"):
            # Belongs to the line above, in or out of budget: the marker for a
            # hunk's last line arrives after the budget is spent.
            if rows:
                rows.append(DiffRow(RowKind.META, line[1:].lstrip()))
            else:
                self._unmarked(line, eol)
            return
        if rows is not None and self._in_budget():
            if line.startswith("diff --git "):
                self._git_header(line)  # a hunk cut short by the next file
                return
            # Inside the declared lengths every line is content, whatever it
            # looks like (a `---` line is decided before it gets here).
            rows.append(self._content_row(line, eol))
            return
        # Outside any declared budget: headers are headers.
        if line.startswith("diff --git "):
            self._git_header(line)
            return
        file = self._file
        if rows is None and file is not None and not file.hunks:
            if (line.startswith("+++ ") or line == "+++") and not file.new_path:
                file.new_path = _path(line)
                file.header.append(line)
                return
            if line.startswith(_GIT_HEADERS) or line.startswith("Binary files "):
                file.header.append(line)
                file.new = file.new or line.startswith("new file mode ")
                file.deleted = file.deleted or line.startswith("deleted file mode ")
                file.binary = file.binary or line.startswith(("Binary files ", "GIT binary"))
                return
        if line.startswith("Binary files ") and line.endswith(" differ"):
            file = self._new_file()  # GNU diff: no header lines around it
            file.binary = True
            file.header.append(line)
            return
        marked = line[:1] in ("+", "-", " ")
        if rows is not None and self._accepting:
            if self._left is None:
                # No declared lengths: lenient. A blank line is a blank context
                # line, and an unmarked line is context a model forgot to mark.
                rows.append(self._content_row(line, eol))
                return
            if marked:
                rows.append(self._content_row(line, eol))  # a hunk past its count
                return
            self._accepting = False
            self._stray(line)
            return
        if marked and rows is None:
            headed = file is not None and not file.hunks and file.headed
            if headed or not self._seen_any:
                # No `@@` at all: a bare fragment.
                self._open_hunk(None, None, "")
                assert self._rows is not None
                self._rows.append(self._content_row(line, eol))
                return
        self._unmarked(line, eol)

    def _unmarked(self, line: str, eol: str) -> None:
        """A line that is no header and joins no hunk: context-to-be, or kept as nothing."""
        file = self._file
        if file is None and self._preamble is not None:
            # Nothing yet is a diff. A model's fenced fragment may begin with
            # context it did not mark (review 1, item 10): the lines so far
            # are that context the moment a `+` or `-` line follows them.
            lead = self._preamble
            if line[:1] in ("+", "-"):
                while lead and not lead[0][0]:
                    lead.pop(0)
                self._preamble = None  # they are rows now, not lines above a file
                self._open_hunk(None, None, "")
                assert self._rows is not None
                for text, ending in lead:
                    self._rows.append(self._content_row(text, ending))
                self._rows.append(self._content_row(line, eol))
                return
            if not any(text for text, _ in lead) and _MBOX_FROM.match(line):
                # A mail (`git format-patch`): a message, then a diff. Known
                # by git's own first line and not by the word `From`, which
                # begins plenty of prose (review 3, item 5).
                self._preamble = None
                self._stray(line, unread=False)
                return
            lead.append((line, eol))
            return
        self._stray(line)

    def _hunk_header(self, line: str) -> None:
        match = _HUNK.match(line)
        if match is None:
            self._open_hunk(None, None, line.strip("@ "))
            return
        old_start, new_start = int(match[1]), int(match[3])
        old_count = 1 if match[2] is None else int(match[2])
        new_count = 1 if match[4] is None else int(match[4])
        # An empty side names the line before it; see `Hunk`.
        start = (old_start + (old_count == 0), new_start + (new_count == 0))
        self._open_hunk(start, (old_count, new_count), match[5])

    def _git_header(self, line: str) -> None:
        file = self._new_file()
        file.header.append(line)
        # `diff --git a/x b/x`; the `---` and `+++` lines, when present, are
        # what the label is taken from.
        file.git_name = _git_name(line[len("diff --git ") :])

    def _raw_file(self, line: str, dialect: str, keep: bool = False) -> None:
        """
        From `line` on, the file is its lines as written, until the next
        `diff --git` / `diff --cc` line. `keep` turns the file being read
        into that file (its header lines so far become its first lines) when
        it has no hunks yet; otherwise a new file begins.
        """
        file = self._file
        if keep and file is not None and not file.hunks and self._rows is None:
            file.raw = list(file.header)
        else:
            file = self._new_file()
            file.raw = []
            if line.startswith(_COMBINED_LINES):
                file.git_name = line.split(" ", 2)[2] if line.count(" ") >= 2 else ""
        file.dialect = dialect
        file.raw.append(line)

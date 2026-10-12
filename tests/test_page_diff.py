"""
The Diff page: its cases as data, its controls as state, and the page in real frames.

**What draws, and what these tests can see of it.** The page draws with
`advtext.ui.typeset_diff_view.TypesetDiffView` and with nothing else: when the
imtypeset library cannot draw it has no views and says why in one line
(T5-FB-C removed the fallback to the old `DiffView`). In this process the
library never can -- it is kept out of the pytest process and a headless frame
has none of its fonts. So:

- **the cases** -- each is the shape its label says, read from the model:
  statuses, counts, what can be expanded, where the long lines and the
  one-token changes are. And the generated files under `demo/diff/` agree with
  the files they were generated from.
- **without the library** -- the page as this process builds it: no views, one
  line, and every control still a method that moves the page's own state.
- **the page's state over a stand-in view** -- `_Stand` is
  `typeset_diff_view.DiffRows` (the real rows, hunks, selection and copy
  text, which need no library) with the switches as attributes and a `draw`
  that draws nothing. Every control is a method; a click on a widget calls
  nothing else. In real ImGui frames with no backend: which panes are drawn,
  the keys, the replay on the frame clock, the cost line, and what the page
  does when a view says the library is gone.
- **the application in a real window**, without the library (the one line)
  and with it (skipped with the reason when `IMTYPESET_LIBRARY` is not set):
  the real `TypesetDiffView`, culling, a replay, a copy, the library switched
  off mid-run.

What a `TypesetDiffView` puts on the draw list (inks, glyph faces, the capped
child, a click on a row) is `tests/test_typeset_diff_view.py`'s.

Nothing here says how a diff looks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext import typesetter
from advtext.diff import MAX_INTRALINE_CHARS, Diff, FileStatus, RowKind
from advtext.ui.pages import PageContext, demo_text, discover
from advtext.ui.pages import diff as page_module
from advtext.ui.pages import typeset as typeset_page
from advtext.ui.pages.diff import (
    BOTH_MIN_PX,
    CAP_PX,
    PAGE,
    Case,
    DiffPage,
    Mode,
    cases,
    long_texts,
    unified_as_pptmstr,
    wide_texts,
)
from advtext.ui.pages.themes import COLOURS
from advtext.ui.palette import DARK_PALETTE, DEFAULT_PALETTE
from advtext.ui.typeset_diff_view import DiffLayout, DiffRows
from advtext.ui.typeset_view import TypesetUnavailable

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from conftest import Window

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)

UNIFIED = DiffLayout.UNIFIED
SIDE = DiffLayout.SIDE_BY_SIDE
DISPLAY = (1100.0, 800.0)
PARKED = (DISPLAY[0] - 2.0, 2.0)

HARD = ("nul", "noeol", "noeol-text", "eol", "mail", "combined", "fence", "unseen", "u0")
KEYS = ("edit", "new", "long", "multiedit", "anchor", "git", "wide", "tokens", "deleted", *HARD)


def case(key: str) -> Case:
    return next(found for found in cases() if found.key == key)


def _layouts(views: Any) -> list[DiffLayout]:
    return [view.layout for view in views]


class _Stand(DiffRows):
    """
    A `TypesetDiffView` as far as the page reads one -- the real rows, hunks
    and selection (`DiffRows`), the switches as attributes -- whose `draw`
    does what the test tells the class to.
    """

    raises: Exception | None = None
    made: list[Any] = []

    def __init__(self, diff: Diff, theme: Any, *, layout: Any, **switches: Any) -> None:
        super().__init__(diff, layout=layout)
        self.switches = dict(switches)
        self.syntax = switches.get("syntax")
        self.height_cap = switches.get("height_cap")
        self.copy_as = switches.get("copy_as")
        self.edits = {"set": 2, "replace": 3}
        self.scroll_x = 0
        self.visible_rows = range(0, 3)
        self.draws = 0
        self.palettes: list[Any] = []
        self.closed = 0
        type(self).made.append(self)

    def draw(self, *, fonts: Any = None, palette: Any = None, width_px: Any = None) -> bool:
        if type(self).raises is not None:
            raise type(self).raises
        self.draws += 1
        self.palettes.append(palette)
        self._origin = (0.0, 0.0)
        return True

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def page(monkeypatch: pytest.MonkeyPatch) -> DiffPage:
    """The page as it is built when the library can draw, over `_Stand`."""
    monkeypatch.setattr(page_module, "why_not", lambda: "")
    monkeypatch.setattr(page_module, "TypesetDiffView", _Stand)
    monkeypatch.setattr(_Stand, "raises", None)
    monkeypatch.setattr(_Stand, "made", [])
    made = PAGE.factory(PageContext.build())
    assert isinstance(made, DiffPage)
    assert made.renderer == "TypesetDiffView" and len(made.views) == 2
    return made


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> DiffPage:
    """The page as this process builds it: the library cannot draw, so no views."""
    typesetter._forget()
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("the page asked for the library"))
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    made = PAGE.factory(PageContext.build())
    assert isinstance(made, DiffPage)
    return made


# ----------------------------------------------------------------------
# The cases
# ----------------------------------------------------------------------


def test_the_picker_holds_the_nine_cases_and_the_hard_ones_and_the_launch_accepts_each() -> None:
    assert tuple(found.key for found in cases()) == KEYS
    assert tuple(found.key for found in cases() if found.hard) == HARD
    assert [found.hard for found in cases()] == sorted(found.hard for found in cases())
    assert len({found.label for found in cases()}) == len(KEYS)
    assert all(PAGE.accepts(key) for key in KEYS)
    assert all(PAGE.accepts(mode.value) for mode in Mode)
    assert all(found.note for found in cases())


def test_the_page_is_where_the_lead_put_it_in_the_sidebar() -> None:
    assert discover().find("diff") is PAGE
    assert (PAGE.name, PAGE.group, PAGE.order) == ("Diff", "Diff", 310)
    assert "" in PAGE.shots


def test_a_small_edit_is_one_hunk_with_collapsed_context_either_side() -> None:
    diff = case("edit").diff()
    (file,) = diff.files
    assert file.status is FileStatus.MODIFIED and file.label == "retry.py"
    assert (diff.added, diff.removed, len(file.hunks)) == (2, 1, 1)
    assert [gap.expandable for gap in file.gaps] == [True, True]
    assert all(gap.count and gap.count > 5 for gap in file.gaps)


def test_a_new_file_and_a_deleted_one_have_one_empty_side() -> None:
    new = case("new").diff().files[0]
    assert new.status is FileStatus.NEW and new.removed == 0 and new.added == 30
    assert {row.kind for row in new.hunks[0].rows} == {RowKind.ADD}
    gone = case("deleted").diff().files[0]
    assert gone.status is FileStatus.DELETED and gone.added == 0 and gone.removed == 8
    assert {row.kind for row in gone.hunks[0].rows} == {RowKind.REMOVE}


def test_the_long_case_is_thousands_of_lines_in_many_hunks() -> None:
    before, after = long_texts()
    assert before.count("\n") >= 4000
    assert (before, after) == long_texts()  # generated, and the same every time
    diff = case("long").diff()
    (file,) = diff.files
    assert len(file.hunks) >= 30
    # About one line in ninety-seven touched, forty dropped, twenty-five added:
    # the alignment found those and did not invent a thousand more.
    assert 40 <= diff.added <= 80 and 60 <= diff.removed <= 100
    assert sum(1 for gap in file.gaps if gap.expandable) >= 30
    whole = diff.expand(0, 0, None)
    assert whole is not diff


def test_the_long_case_is_generated_and_reads_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The long text is made up, the same in every tree, and read from nowhere.

    It was seven of this package's own modules end to end (`linebreak.py`,
    `pack.py`, `style.py`, `shipout.py`, `nodes.py`, `selection.py`,
    `markdown.py`), with numbered filler "if the sources are not readable":
    every one of those is the old layout core's or stands on it, so the
    removal of the core would have turned the page's culling case into four
    thousand lines of `value_N = compute(N, ...)` without a test going red,
    and until then the text moved whenever one of them was edited. It is the
    corpus `tests/test_typeset_diff_view.py` generates for the same reason
    (`fixed_long_texts`), and is held equal to it here so that the answers
    measured on one are answers about the other.
    """
    from test_typeset_diff_view import fixed_long_texts

    def refuse(*args: object, **kwargs: object) -> str:
        raise AssertionError(f"the long case read a file: {args[0]}")

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    before, after = long_texts()
    assert (before, after) == fixed_long_texts()
    assert before.count("\n") == 4000
    assert not hasattr(page_module, "_LONG_SOURCES")
    assert "value_0 = compute(0" not in before
    # Code the tokeniser has something to colour, and not one function repeated.
    written = [line for line in before.splitlines() if line]
    assert before.startswith("def step_1(") and len(set(written)) == len(written) > 3300
    assert long_texts(120)[0].count("\n") == 120


def test_the_wide_case_has_lines_several_panes_wide_and_one_past_the_marking_limit() -> None:
    before, after = wide_texts()
    lengths = [len(line) for line in before.splitlines()]
    assert len(lengths) == 30 and min(lengths) >= 300
    assert sum(1 for length in lengths if length > MAX_INTRALINE_CHARS) == 1
    (hunk,) = case("wide").diff(40).files[0].hunks
    marked = [(row, spans) for row, spans in zip(hunk.rows, hunk.spans, strict=True) if spans]
    assert marked, "no changed word was marked in any line"
    # A mark that starts beyond column 280: off screen until the view is scrolled.
    assert any(start > 280 for _, spans in marked for start, _ in spans)
    # And the over-long pair is a whole-line change: changed, and not marked.
    over = [
        spans
        for row, spans in zip(hunk.rows, hunk.spans, strict=True)
        if len(row.text) > MAX_INTRALINE_CHARS and row.kind is not RowKind.CONTEXT
    ]
    assert len(over) == 2 and not any(over)


def test_the_token_case_marks_one_token_and_holds_real_tabs() -> None:
    before = demo_text("diff/tokens.before.py")
    assert before is not None and before.count("\t") == 2
    (hunk,) = case("tokens").diff(40).files[0].hunks
    marked = {
        row.text[start:end]
        for row, spans in zip(hunk.rows, hunk.spans, strict=True)
        for start, end in spans
    }
    # One number, one character of an operator (`>` to `>=`), one name, a tab.
    assert {"20", "21", "=", "i", "item", "\t"} <= marked
    assert any(piece.strip() == "" and piece for piece in marked)


def test_a_multiedit_is_three_headed_fragments_with_nothing_to_expand() -> None:
    found = case("multiedit")
    assert not found.from_texts
    diff = found.diff()
    assert [file.label for file in diff.files] == ["edit 1", "edit 2", "edit 3"]
    assert (diff.added, diff.removed) == (4, 3)
    assert not any(gap.expandable for file in diff.files for gap in file.gaps)
    # The text is what pptmstr's own function writes for those edits, joined.
    text = found.unified_text()
    assert text.count("--- a/edit ") == 3 and text.count("\n\n--- ") == 2


def test_an_unanchored_edit_carries_the_hosts_verdict() -> None:
    (file,) = case("anchor").diff().files
    assert file.will_not_apply == "anchor not found in file"
    assert (file.added, file.removed) == (2, 1)


def test_the_git_diff_is_four_files_and_agrees_with_the_files_it_was_made_from() -> None:
    diff = case("git").diff()
    assert [(file.label, file.status) for file in diff.files] == [
        ("README.md", FileStatus.MODIFIED),
        ("limits.py", FileStatus.NEW),
        ("retry.py", FileStatus.MODIFIED),
        ("setup.sh", FileStatus.DELETED),
    ]
    assert all(hunk.complete for file in diff.files for hunk in file.hunks)

    def texts(file: Any) -> list[tuple[RowKind, str]]:
        return [(row.kind, row.text) for hunk in file.hunks for row in hunk.rows]

    # If one of the source files is edited and the script not re-run, this says so.
    assert texts(diff.files[1]) == texts(case("new").diff().files[0])
    assert texts(diff.files[2]) == texts(case("edit").diff().files[0])
    assert texts(diff.files[3]) == texts(case("deleted").diff().files[0])


def test_the_pptmstr_shaped_text_parses_back_to_the_same_change() -> None:
    before = demo_text("diff/edit.before.py")
    after = demo_text("diff/edit.after.py")
    assert before is not None and after is not None
    text = unified_as_pptmstr(before, after, "retry.py")
    assert text.startswith("--- a/retry.py\n+++ b/retry.py\n@@ ")
    parsed = Diff.from_unified(text)
    assert (parsed.added, parsed.removed) == (2, 1)
    assert parsed.files[0].apply(before) == after
    # An absolute path takes no a/ b/ prefix, and a missing file is /dev/null.
    assert unified_as_pptmstr(None, "x\n", "/tmp/x").startswith("--- /dev/null\n+++ /tmp/x\n")


@pytest.mark.parametrize("key", KEYS)
def test_every_case_can_be_written_out_and_read_back_as_a_stream_would(key: str) -> None:
    found = case(key)
    whole = found.diff(3)
    parsed = Diff.from_unified(found.unified_text())
    assert (parsed.added, parsed.removed) == (whole.added, whole.removed)
    assert len(parsed.files) == len(whole.files)


# ----------------------------------------------------------------------
# The hard cases (review 1): each shows what its note says
# ----------------------------------------------------------------------


def test_hard_a_nul_byte_hides_nothing() -> None:
    (file,) = case("nul").diff().files
    assert file.status is FileStatus.MODIFIED and file.control_characters
    assert (file.added, file.removed) == (2, 1)  # two lines in, and `make test` gained a prefix
    assert any("\0" in row.text and "\x1b" in row.text for hunk in file.hunks for row in hunk.rows)


def test_hard_a_multiedit_without_closing_newlines_from_texts_and_from_text() -> None:
    texts, text = case("noeol").diff(), case("noeol-text").diff()
    assert (
        [f.label for f in texts.files]
        == [f.label for f in text.files]
        == [
            "edit 1",
            "edit 2",
            "edit 3",
        ]
    )
    assert (texts.added, texts.removed) == (3, 3)
    assert texts == Diff.from_edits([(p.before, p.after, p.label) for p in case("noeol").pairs])
    # The text's limit, shown and not hidden: one removed row per edit, each
    # under its own edit, the hunk left incomplete.
    assert (text.added, text.removed) == (0, 3)
    assert [r.text for _, _, r in text.rows()] == [
        "timeout = 5+timeout = 30",
        "retries = 3+retries = 5",
        "    return None+    raise TimeoutError(url)",
    ]
    assert not any(hunk.complete for file in text.files for hunk in file.hunks)


def test_hard_a_line_ending_change_says_so_and_is_folded(page: DiffPage) -> None:
    (file,) = case("eol").diff().files
    assert file.line_endings == "CRLF -> LF" and (file.added, file.removed) == (7, 7)
    page.choose(case("eol"))
    for view in page.views.values():
        assert [view.row_info(row).kind for row in range(view.row_count)] == ["file", "fold"]
        view.show_line_endings(0)
        assert view.row_count > 8


def test_hard_a_mail_a_combined_diff_and_an_unmarked_fragment() -> None:
    (mail,) = case("mail").diff().files
    assert mail.label == "retry.py" and (mail.added, mail.removed) == (4, 3)
    assert mail.hunks[0].complete and len(mail.hunks) == 1
    (combined,) = case("combined").diff().files
    assert combined.dialect == "combined diff" and combined.hunks == ()
    assert combined.raw == tuple((demo_text("diff/combined.diff") or "").splitlines())
    (fence,) = case("fence").diff().files
    kinds = "".join(row.kind.value for row in fence.hunks[0].rows)
    assert kinds == " -+  --++" and fence.hunks[0].rows[0].text == "def retry(call, attempts=3):"


def test_hard_unseen_characters_are_flagged_by_the_model_and_are_rows_of_the_page(
    page: DiffPage,
) -> None:
    """
    Review 3, item 1, as far as the page goes: the file says it holds
    invisible characters, and the case is rows in both layouts. Which glyphs
    the library draws for them is `tests/test_typeset_diff_view.py`'s.
    """
    (file,) = case("unseen").diff().files
    assert file.invisible_characters and (file.added, file.removed) == (4, 4)
    page.choose(case("unseen"))
    for view in page.views.values():
        kinds = [view.row_info(row).kind for row in range(view.row_count)]
        assert kinds[0] == "file" and view.row_count > 4
    assert page.readouts()[1].startswith("+4 -4 in 1 file(s)")


def test_hard_an_honest_u0_diff_with_dash_dash_lines_is_one_file_that_applies() -> None:
    """Review 3, item 2, on the page."""
    from advtext.ui.pages.diff import u0_text

    text = u0_text()
    assert text.count("\n--- ") == 2 and "\n+++ added entry\n@@ " in text
    diff = case("u0").diff()
    assert [(f.label, f.added, f.removed, len(f.hunks)) for f in diff.files] == [
        ("notes.txt", 3, 3, 2)
    ]
    before = "title\n-- removed entry\nkeep 1\nkeep 2\nkeep 3\nold tail\n-- x\nend\n"
    after = before.replace("-- removed", "++ added").replace("old", "new").replace("-- x", "++ y")
    assert diff.files[0].apply(before) == after


def test_in_both_the_other_pane_follows_the_one_being_scrolled(page: DiffPage) -> None:
    page.choose(case("long"))
    page.expand(everything=True)
    unified, side = page.views[UNIFIED], page.views[SIDE]
    target = 900
    unified._top_row = target  # what a draw records after the user scrolled this pane
    assert page.follow(UNIFIED)
    want = side.row_of(unified.row_info(target))
    assert side._scroll_to == want and want != target
    # It shows the same line, by the model and not by the row number.
    here, there = unified.row_info(target), side.row_info(want)
    assert (here.file, here.hunk) == (there.file, there.hunk)
    assert here.left in (there.left, there.right)
    assert not page.follow(UNIFIED)  # asked once, not every frame
    side._top_row = want
    assert not page.follow(UNIFIED) and not page.follow(SIDE)


# ----------------------------------------------------------------------
# The page's state, without a frame
# ----------------------------------------------------------------------


def test_the_page_opens_on_the_edit_both_layouts_light_uncapped_whole(page: DiffPage) -> None:
    assert page.case.key == "edit" and page.mode is Mode.BOTH
    assert page.context_lines == 3 and page.syntax_on
    assert not page.dark and not page.capped and not page.replaying
    assert page.palette is DEFAULT_PALETTE
    assert list(page.views) == _layouts(page.views.values()) == [UNIFIED, SIDE]
    assert all(view.diff is page.diff for view in page.views.values())


def test_the_launch_options_set_the_case_the_mode_and_the_switches(page: DiffPage) -> None:
    context = PageContext.build(
        request_page="diff", request_options=("git", "side", "dark", "cap"), request_count=7
    )
    made = DiffPage(context)
    assert made.case.key == "git" and made.mode is Mode.SIDE and made.single is SIDE
    assert made.dark and made.capped and made.context_lines == 7
    assert made.palette is DARK_PALETTE
    assert all(view.height_cap == CAP_PX for view in made.views.values())
    streamed = DiffPage(PageContext.build(request_page="Diff", request_options=("stream",)))
    assert streamed.replaying and streamed.fed == 0
    # Options meant for another page are not this page's.
    other = DiffPage(PageContext.build(request_page="themes", request_options=("dark",)))
    assert not other.dark


def test_both_is_two_views_when_the_body_is_wide_enough_and_one_when_it_is_not(
    page: DiffPage,
) -> None:
    assert _layouts(page.shown(BOTH_MIN_PX)) == [UNIFIED, SIDE]
    assert _layouts(page.shown(BOTH_MIN_PX - 1.0)) == [UNIFIED]
    page.set_mode(Mode.SIDE)
    assert _layouts(page.shown(2000.0)) == [SIDE]
    # Narrow, "both" falls back to whichever single layout was last chosen.
    page.set_mode(Mode.BOTH)
    assert _layouts(page.shown(600.0)) == [SIDE]
    page.set_mode(Mode.UNIFIED)
    assert _layouts(page.shown(2000.0)) == [UNIFIED]


def test_choosing_a_case_shows_it_whole_in_both_views(page: DiffPage) -> None:
    page.choose(case("git"))
    assert page.case.key == "git" and len(page.diff.files) == 4
    assert all(view.diff is page.diff for view in page.views.values())
    assert page.views[UNIFIED].row_count > page.views[SIDE].row_count > 40


def test_more_context_is_a_new_diff_for_texts_and_refused_for_a_parsed_one(
    page: DiffPage,
) -> None:
    rows = page.views[UNIFIED].row_count
    assert page.set_context(6) is True
    assert page.views[UNIFIED].row_count == rows + 6
    assert page.set_context(0) is True
    assert page.views[UNIFIED].row_count == rows - 6
    assert page.set_context(99) is True and page.context_lines == 12

    page.choose(case("multiedit"))
    shown = page.diff
    assert page.set_context(1) is False
    assert page.diff is shown


def test_expand_reveals_a_step_in_every_gap_and_all_reveals_the_file(page: DiffPage) -> None:
    before = demo_text("diff/edit.before.py")
    assert before is not None
    lines = before.count("\n")
    hunk = page.diff.files[0].hunks[0]
    assert page.expandable == 2
    counts = [gap.count for gap in page.diff.files[0].gaps]
    assert page.expand() == 2
    grown = page.diff.files[0].hunks[0]
    assert grown.old_count == hunk.old_count + sum(min(20, count or 0) for count in counts)
    assert all(view.diff is page.diff for view in page.views.values())
    page.expand(everything=True)
    (whole,) = page.diff.files[0].hunks
    assert whole.old_count == lines and page.expandable == 0
    assert page.expand() == 0


def test_expand_on_a_parsed_diff_widens_nothing_and_does_not_raise(page: DiffPage) -> None:
    page.choose(case("git"))
    shown = page.diff
    assert page.expandable == 0
    assert page.expand() == 0 and page.expand(everything=True) == 0
    assert page.diff is shown


def test_expanding_the_long_case_shows_every_line_of_it(page: DiffPage) -> None:
    page.choose(case("long"))
    collapsed = page.views[UNIFIED].row_count
    page.expand(everything=True)
    assert page.views[UNIFIED].row_count > 4000 > collapsed
    assert len(page.diff.files[0].hunks) == 1


def test_stepping_hunks_moves_both_views_to_the_same_one(page: DiffPage) -> None:
    page.choose(case("git"))
    keys = page.hunks()
    assert keys == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert page.hunk_line().startswith("4 hunk(s)")
    assert page.next_hunk() == (0, 0)
    assert page.next_hunk() == (1, 0)
    assert {view.current_hunk for view in page.views.values()} == {(1, 0)}
    assert page.hunk_line() == f"hunk 2 of 4 -- limits.py {page.diff.files[1].hunks[0].header}"
    assert page.previous_hunk() == (0, 0)
    assert page.previous_hunk() == (0, 0)  # stays on the first
    # A view that had gone somewhere else by itself is walked back into step.
    side = page.views[SIDE]
    side.next_hunk()
    side.next_hunk()
    assert side.current_hunk == (2, 0)
    assert page.next_hunk() == (1, 0)
    assert side.current_hunk == (1, 0)


def test_syntax_off_and_on_is_the_same_callable_put_back(page: DiffPage) -> None:
    colour = page.views[UNIFIED].syntax
    assert colour is not None and page.views[SIDE].syntax is colour
    page.set_syntax(False)
    assert all(view.syntax is None for view in page.views.values())
    page.set_syntax(True)
    assert all(view.syntax is colour for view in page.views.values())


def _inks(view: Any) -> set[int]:
    """The inks the view's highlighter gives four lines of Python."""
    lines = ["import os  # a comment", "def f(x):", "    return 'text' + str(12)", "class A: pass"]
    return {ink for line in view.syntax(lines, "python") for _, _, ink in line}


def test_going_dark_recolours_the_syntax_and_keeps_what_can_be_kept(page: DiffPage) -> None:
    """
    The scheme change: one assignment per view, since review 1's item 14.

    After `set_dark` the views' highlighter gives the dark scheme's syntax
    inks and none of the light scheme's, **in the same views** -- the page
    once built new views for it and lost the current hunk and the selection.
    """
    page.expand(everything=True)
    page.next_hunk()
    for view in page.views.values():
        view.select((0, 0, 0, 0), (0, 0, 1, 2))
    shown = page.diff
    light = {COLOURS[0].syntax.ink(kind) for kind in ("number", "string", "keyword", "comment")}
    dark = {COLOURS[1].syntax.ink(kind) for kind in ("number", "string", "keyword", "comment")}
    assert light <= _inks(page.views[UNIFIED]) and not _inks(page.views[UNIFIED]) & (dark - light)
    old = dict(page.views)
    page.set_capped(True)

    page.set_dark(True)
    assert page.palette is DARK_PALETTE
    assert all(page.views[layout] is old[layout] for layout in DiffLayout)
    assert all(view.current_hunk == (0, 0) for view in page.views.values())
    assert all(view.selection == ((0, 0, 0, 0), (0, 0, 1, 2)) for view in page.views.values())
    inks = _inks(page.views[UNIFIED])
    assert dark <= inks and not inks & (light - dark)
    assert all(view.diff is shown for view in page.views.values())
    assert all(view.height_cap == CAP_PX for view in page.views.values())
    assert _layouts(page.views.values()) == [UNIFIED, SIDE]
    page.set_dark(True)  # already so: nothing is rebuilt
    assert page.views[UNIFIED].syntax is page.views[SIDE].syntax
    # With syntax off a scheme change gives the views no highlighter back.
    page.set_syntax(False)
    page.set_dark(False)
    assert all(view.syntax is None for view in page.views.values())
    page.set_syntax(True)
    assert light <= _inks(page.views[SIDE])


def test_the_cap_is_the_views_own_switch(page: DiffPage) -> None:
    page.set_capped(True)
    assert all(view.height_cap == CAP_PX for view in page.views.values())
    page.set_capped(False)
    assert all(view.height_cap is None for view in page.views.values())


def test_a_replay_feeds_whole_lines_and_ends_on_the_diff_it_was_made_from(
    page: DiffPage,
) -> None:
    page.choose(case("git"))
    whole = page.diff
    page.start_replay()
    assert page.replaying and page.fed == 0 and not page.diff.files
    total = len(case("git").unified_text().splitlines())
    # 30 lines a second at sixty frames a second: a line every other frame,
    # the half carried between them.
    page.rate = 30.0
    fed = [page.advance(1.0 / 60.0) for _ in range(6)]
    assert fed == [0, 1, 0, 1, 0, 1]
    assert all(view.diff is page.diff for view in page.views.values())
    page.paused = True
    assert page.advance(10.0) == 0
    page.paused = False
    page.rate = 400.0
    while not page.replay_done:
        assert page.advance(0.05) > 0
    assert page.fed == total and page.advance(1.0) == 0
    assert (page.diff.added, page.diff.removed) == (whole.added, whole.removed)
    assert "replay done" in page.readouts()[2]
    assert f"line {total} of {total}" in page.readouts()[2]


def test_a_replay_of_a_text_case_cannot_expand_until_it_is_shown_whole(page: DiffPage) -> None:
    page.start_replay()
    page.feed(10_000)
    assert page.replay_done and page.expandable == 0
    assert page.set_context(5) is False
    page.stop_replay()
    assert not page.replaying and page.expandable == 2
    # The context asked for while replaying is the context it comes back with.
    assert page.context_lines == 5
    page.start_replay()
    page.choose(case("new"))
    assert not page.replaying


def test_the_clipboard_readout_says_what_was_copied_and_how_much(page: DiffPage) -> None:
    assert page.copied_line().startswith("clipboard: nothing copied yet")
    view = page.views[UNIFIED]
    view.select_all()
    text = page._record_copy(view)
    assert text == view.selected_text() and page.copies == 1
    lines = text.split("\n")
    assert page.copied_line() == (
        f"clipboard (copy 1): {len(lines)} line(s), {len(text)} character(s), "
        f"first line {lines[0]!r}"
    )


# ----------------------------------------------------------------------
# Real frames
# ----------------------------------------------------------------------


def _frame(
    page: DiffPage,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    keys: Sequence[str] = (),
    release: Sequence[str] = (),
    size: tuple[float, float] = DISPLAY,
    seconds: float = 1.0 / 60.0,
) -> set[int]:
    """
    One frame of the page in a window filling the display. Returns every vertex colour.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*size)
    io.delta_time = seconds
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    for key in keys:
        io.add_key_event(getattr(imgui.Key, key), True)
    for key in release:
        io.add_key_event(getattr(imgui.Key, key), False)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*size))
        imgui.begin("##advtext-diff-page-test", None, imgui.WindowFlags_.no_decoration.value)
        try:
            page.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    colours: set[int] = set()
    for draw_list in imgui.get_draw_data().cmd_lists:
        buffer = draw_list.vtx_buffer
        colours.update(int(buffer[index].col) for index in range(buffer.size()))
    return colours


ALL_KEYS_UP = ("mod_ctrl", "mod_shift", "c", "a", "j", "k")


@pytest.fixture
def shown(page: DiffPage) -> Iterator[DiffPage]:
    """
    The page over `_Stand` after two settling frames: mouse parked and up, every key up.
    """
    _frame(page, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    _frame(page, mouse=PARKED)
    yield page
    _frame(page, mouse=PARKED, left=False, release=ALL_KEYS_UP)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("mode", list(Mode), ids=lambda mode: mode.value)
def test_every_case_is_drawn_in_every_mode(shown: DiffPage, key: str, mode: Mode) -> None:
    """
    Which views the page asks to draw, and that its readouts can be made for
    every case: the view's own drawing is not here (`_Stand.draw` draws nothing).
    """
    shown.choose(case(key))
    shown.set_mode(mode)
    before = {layout: view.draws for layout, view in shown.views.items()}
    _frame(shown)
    _frame(shown)
    expected = [UNIFIED, SIDE] if mode is Mode.BOTH else [shown.single]
    assert list(shown.stats) == expected and all(shown.stats.values())
    for layout, view in shown.views.items():
        assert view.draws - before[layout] == (2 if layout in expected else 0), (key, layout)
        assert view.diff is shown.diff
    lines = shown.readouts()
    assert len(lines) == 5
    assert lines[0] == "renderer: TypesetDiffView (imtypeset)"
    assert lines[1].startswith(f"+{shown.diff.added} -{shown.diff.removed} in ")
    rows = (shown.views[UNIFIED].row_count, shown.views[SIDE].row_count)
    assert f"rows: unified {rows[0]}, side by side {rows[1]}; " in lines[1]
    assert lines[1].endswith("on screen " + " / ".join(["3"] * len(expected)))


def test_a_narrow_body_shows_one_layout_though_both_was_asked_for(shown: DiffPage) -> None:
    assert shown.mode is Mode.BOTH and list(shown.stats) == [UNIFIED, SIDE]
    _frame(shown, size=(700.0, 800.0))
    assert list(shown.stats) == [UNIFIED]


def test_j_and_k_step_the_hunks_of_both_views(shown: DiffPage) -> None:
    shown.choose(case("git"))
    _frame(shown)
    _frame(shown, keys=("j",))
    _frame(shown, release=("j",))
    assert {view.current_hunk for view in shown.views.values()} == {(0, 0)}
    _frame(shown, keys=("j",))
    _frame(shown, release=("j",))
    assert shown.hunk_line().startswith("hunk 2 of 4 -- limits.py @@")
    _frame(shown, keys=("k",))
    _frame(shown, release=("k",))
    assert {view.current_hunk for view in shown.views.values()} == {(0, 0)}
    # Held down is one step, not one a frame.
    _frame(shown, keys=("j",))
    _frame(shown)
    _frame(shown)
    _frame(shown, release=("j",))
    assert shown.hunk_line().startswith("hunk 2 of 4")


def test_a_view_that_expanded_a_gap_by_itself_is_adopted_by_the_page_and_the_other_view(
    shown: DiffPage,
) -> None:
    """
    What a click on a collapsed row does in a view is `view.expand` (the click
    itself is `tests/test_typeset_diff_view.py`'s). After the frame the page
    shows that diff and so does the other view.
    """
    unified, side = shown.views[UNIFIED], shown.views[SIDE]
    gaps = [row for row in range(unified.row_count) if unified.row_info(row).kind == "gap"]
    first = unified.row_info(gaps[0])
    assert len(gaps) == 2 and (first.kind, first.file, first.hunk) == ("gap", 0, 0)
    before = shown.diff
    rows = (unified.row_count, side.row_count)
    unified.expand(0, shown.diff.files[0].gaps[0].index)
    assert unified.diff is not before and side.diff is before and shown.diff is before
    _frame(shown)
    assert shown.diff is not before
    assert unified.diff is shown.diff and side.diff is shown.diff
    assert unified.row_count > rows[0] and side.row_count > rows[1]


def test_a_replay_runs_on_the_frame_clock_and_the_views_follow(shown: DiffPage) -> None:
    shown.choose(case("git"))
    whole_rows = shown.views[UNIFIED].row_count
    shown.rate = 300.0
    shown.start_replay()
    _frame(shown, seconds=0.1)
    assert shown.fed == 30
    partial = shown.views[UNIFIED].row_count
    assert 0 < partial < whole_rows
    frames = 0
    while not shown.replay_done:
        _frame(shown, seconds=0.1)
        frames += 1
        assert frames < 20
    _frame(shown)
    assert shown.views[UNIFIED].row_count == whole_rows
    assert shown.stats[UNIFIED] is True and "replay done" in shown.readouts()[2]


def test_a_views_sideways_scroll_survives_a_scheme_change(shown: DiffPage) -> None:
    shown.choose(case("wide"))
    _frame(shown)
    view = shown.views[UNIFIED]
    view.scroll_x = 480
    _frame(shown)
    shown.set_dark(True)
    _frame(shown)
    _frame(shown)
    assert shown.views[UNIFIED] is view and view.scroll_x == 480
    # A new case starts from the left.
    shown.choose(case("edit"))
    assert view.scroll_x == 0


def test_dark_hands_the_views_the_dark_palette_and_paints_its_ground(shown: DiffPage) -> None:
    """
    The palette is an argument of `draw`, and the pane's ground is the page's
    own: the child window's background, in the vertex buffer.
    """
    light = _frame(shown)
    assert DEFAULT_PALETTE.page in light
    assert {view.palettes[-1] for view in shown.views.values()} == {DEFAULT_PALETTE}
    shown.set_dark(True)
    _frame(shown)
    dark = _frame(shown)
    assert DARK_PALETTE.page in dark and DEFAULT_PALETTE.page not in dark
    assert {view.palettes[-1] for view in shown.views.values()} == {DARK_PALETTE}


def test_the_cost_readout_is_the_time_around_the_views_and_nothing_else(
    page: DiffPage,
) -> None:
    ticks = iter(range(1000))
    made = DiffPage(PageContext.build(), timer=lambda: next(ticks) * 0.002)
    assert made.renderer == "TypesetDiffView"
    _frame(made, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    assert made.draw_ms == pytest.approx(2.0)
    _frame(made)
    assert made.draw_ms == pytest.approx(2.0) and made.mean_ms == pytest.approx(2.0)
    assert "2.00 ms this frame, 2.00 mean" in made.readouts()[2]
    assert made.frames == 2


# ----------------------------------------------------------------------
# Without the library: no views, one line, and the state all the same
# ----------------------------------------------------------------------

_CLOSURE = r"""
import json, sys
import advtext.ui.pages.diff as page

def loaded():
    return sorted(m for m in sys.modules if m.split(".")[0] == "advtext")

report = {"at_import": loaded()}
from imgui_bundle import imgui
from advtext.ui.pages import PageContext

context = PageContext.build(request_page="diff", request_options=("long", "both"))
before = set(sys.modules)
made = page.DiffPage(context)
made.expand(everything=True)
made.start_replay()
made.feed(50)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
for _ in range(3):
    io.delta_time = 1.0 / 60.0
    imgui.new_frame()
    imgui.begin("x")
    made.draw()
    imgui.end()
    imgui.render()
report["added"] = sorted(m for m in set(sys.modules) - before if m.split(".")[0] == "advtext")
report["loaded"] = loaded()
report["page"] = [made.renderer, made.reason, made.frames, list(made.readouts()), made.fed]
report["imtypeset"] = "imtypeset" in sys.modules
print("REPORT " + json.dumps(report))
"""

# What the old `DiffView` stood on, none of which the page may load any more.
_OLD_CORE = {
    "advtext.ui.diff_view",
    "advtext.ui.bare_view",
    "advtext.ui.composition",
    "advtext.ui.units",
    "advtext.backends.imgui_draw",
    "advtext.linebreak",
    "advtext.selection",
    "advtext.shipout",
    "advtext.spans",
    "advtext.fontlib",
    "advtext.markdown",
    "advtext.stream",
    "advtext.mathtext",
}


def test_importing_and_drawing_the_page_load_neither_diff_view_nor_the_old_core() -> None:
    """
    Measured in a fresh interpreter, the library's variables removed. Importing
    the page loads nothing of what `DiffView` stood on (nor `pack`, `nodes`,
    `style`, which `PageContext.build` loads afterwards and the page does
    not); building the page, moving its state and drawing three frames of it
    add no `advtext` module at all.
    """
    pytest.importorskip("imgui_bundle")
    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CLOSURE],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout.split("REPORT ", 1)[1])
    at_import = set(report["at_import"])
    assert {"advtext.ui.pages.diff", "advtext.ui.typeset_diff_view", "advtext.diff"} <= at_import
    at_import_old = at_import & (_OLD_CORE | {"advtext.pack", "advtext.nodes", "advtext.style"})
    assert not at_import_old, sorted(at_import_old)
    assert report["added"] == [] and report["imtypeset"] is False
    assert not set(report["loaded"]) & _OLD_CORE, sorted(set(report["loaded"]) & _OLD_CORE)
    line = "imtypeset is not drawing: IMTYPESET_LIBRARY is not set"
    assert report["page"] == ["none", "IMTYPESET_LIBRARY is not set", 3, [line], 50]


def test_headless_the_page_has_no_views_and_draws_one_line_saying_why(bare: DiffPage) -> None:
    """
    In this process the library has no fonts (and the page never asks for the
    library itself: `advtext.ui.pages.typeset.why_not`), so there are no
    views, and the page's frame is its sentence and nothing else: no
    controls, no panes.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    assert bare.renderer == "none" and bare.views == {}
    assert bare.reason == "IMTYPESET_LIBRARY is not set"
    sentence = f"{typeset_page.NOT_DRAWING}: {bare.reason}"
    assert bare.readouts() == (sentence,)

    counts: list[int] = []

    def count(draw: Any) -> None:
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(*DISPLAY))
            imgui.begin("##advtext-diff-page-test", None, imgui.WindowFlags_.no_decoration.value)
            try:
                vertices = imgui.get_window_draw_list().vtx_buffer
                before = vertices.size()
                draw()
                counts.append(vertices.size() - before)
            finally:
                imgui.end()
        finally:
            imgui.render()

    _frame(bare, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    count(bare.draw)
    count(lambda: imgui.text_wrapped(sentence))
    assert counts[0] == counts[1] > 0
    assert bare.frames == 2 and bare.stats == {} and bare.draw_ms == 0.0


def test_without_views_every_control_still_moves_the_pages_own_state(bare: DiffPage) -> None:
    """
    The case, the context, what is expanded, the mode, the switches and the
    replay are the page's. What is a view's is absent, and says so by its
    value: no hunk is current, nothing is shown, nothing follows.
    """
    assert bare.case.key == "edit" and bare.mode is Mode.BOTH and not bare.replaying
    assert bare.shown(2000.0) == () and bare.shown(100.0) == ()
    assert bare.next_hunk() is None and bare.previous_hunk() is None
    assert bare.follow(UNIFIED) is False and bare.adopt() is False
    assert bare.hunk_line() == "1 hunk(s); j / k or the buttons step through them"

    assert bare.expandable == 2
    hunk = bare.diff.files[0].hunks[0]
    counts = [gap.count for gap in bare.diff.files[0].gaps]
    assert bare.expand() == 2
    step = page_module.EXPAND_STEP
    grown = bare.diff.files[0].hunks[0].old_count
    assert grown == hunk.old_count + sum(min(step, count or 0) for count in counts)
    assert bare.expand(everything=True) >= 0 and bare.expandable == 0
    assert bare.set_context(6) is True and bare.context_lines == 6 and bare.expandable == 2

    bare.choose(case("git"))
    assert bare.case.key == "git" and len(bare.diff.files) == 4 and len(bare.hunks()) == 4
    assert bare.set_context(1) is False
    bare.set_mode(Mode.SIDE)
    assert bare.single is SIDE
    bare.set_dark(True)
    bare.set_capped(True)
    bare.set_syntax(False)
    assert bare.palette is DARK_PALETTE and bare.capped and not bare.syntax_on

    whole = bare.diff
    bare.start_replay()
    assert bare.replaying and not bare.diff.files
    bare.rate = 400.0
    while not bare.replay_done:
        assert bare.advance(0.05) > 0
    assert (bare.diff.added, bare.diff.removed) == (whole.added, whole.removed)
    bare.stop_replay()
    assert not bare.replaying and bare.copied_line().startswith("clipboard: nothing copied yet")
    assert bare.views == {} and len(bare.readouts()) == 1


def test_the_step_expand_uses_without_a_view_is_the_views_default() -> None:
    import inspect

    from advtext.ui.typeset_diff_view import TypesetDiffView

    default = inspect.signature(TypesetDiffView.__init__).parameters["expand_step"].default
    assert page_module.EXPAND_STEP == default


def test_a_view_that_cannot_be_made_leaves_the_page_with_none_and_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ready()` said yes and the constructor said no: no half-made pair is kept."""

    class Refusing(_Stand):
        def __init__(self, diff: Diff, theme: Any, *, layout: Any, **switches: Any) -> None:
            if layout is SIDE:
                raise TypesetUnavailable("imtypeset is not in use: gone between the two")
            super().__init__(diff, theme, layout=layout, **switches)

    monkeypatch.setattr(page_module, "why_not", lambda: "")
    monkeypatch.setattr(page_module, "TypesetDiffView", Refusing)
    made = DiffPage(PageContext.build())
    assert made.views == {} and made.renderer == "none"
    assert made.reason == "imtypeset is not in use: gone between the two"


# ----------------------------------------------------------------------
# With views: what the page makes, and what it does when one refuses
# ----------------------------------------------------------------------


@pytest.fixture
def stood(page: DiffPage) -> Iterator[DiffPage]:
    yield page
    _frame(page, mouse=PARKED, left=False, release=ALL_KEYS_UP)


def test_when_the_library_can_draw_the_page_makes_typeset_views(
    stood: DiffPage,
) -> None:
    """
    Two views of the typeset class, with the page's switches and WITHOUT
    `metrics=` (the library measures). The cost line counts library edits.
    """
    assert stood.renderer == "TypesetDiffView" and stood.reason == ""
    assert [type(view) for view in stood.views.values()] == [_Stand, _Stand]
    for layout, view in stood.views.items():
        assert view.layout is layout
        assert set(view.switches) == {"px_per_inch", "syntax", "height_cap", "copy_as"}
        assert view.syntax is not None and view.height_cap is None
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    _frame(stood)
    assert stood.stats == {UNIFIED: True, SIDE: True}
    assert all(view.draws == 2 for view in stood.views.values())
    lines = stood.readouts()
    assert lines[0] == "renderer: TypesetDiffView (imtypeset)"
    assert "library edits 10" in lines[2] and "glyphs" not in lines[2]
    # Every switch is an attribute of a view.
    stood.set_capped(True)
    stood.set_syntax(False)
    assert all(view.height_cap == CAP_PX and view.syntax is None for view in stood.views.values())
    stood.choose(case("git"))
    assert all(view.diff is stood.diff for view in stood.views.values())
    first, second = stood.hunks()[:2]
    assert stood.next_hunk() == first and stood.next_hunk() == second
    assert all(view.current_hunk == second for view in stood.views.values())


def test_a_draw_that_answers_false_is_said_in_the_cost_line(
    stood: DiffPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    assert "not answered" not in stood.readouts()[2]
    monkeypatch.setattr(stood.views[SIDE], "draw", lambda **_: False)
    _frame(stood)
    assert stood.stats == {UNIFIED: True, SIDE: False}
    assert "(not answered: something in view was not set as asked)" in stood.readouts()[2]


def test_a_view_that_refuses_mid_run_leaves_the_page_alive_with_no_views_saying_why(
    stood: DiffPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    `TypesetUnavailable` out of `draw` (the library failed and was switched
    off) does not leave the page's `draw`: the pane's child is ended and its
    colour popped (or the frame could not be closed), both views are dropped
    and closed, the reason is the exception's, the page's own state is as it
    was, and every frame after it is the one line.
    """
    stood.choose(case("git"))
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    stood.next_hunk()
    stood.set_capped(True)
    before = dict(stood.views)
    shown = stood.diff
    monkeypatch.setattr(
        _Stand, "raises", TypesetUnavailable("imtypeset failed and is switched off: x")
    )
    _frame(stood)
    assert stood.renderer == "none" and stood.views == {} and stood.stats == {}
    assert stood.reason == "imtypeset failed and is switched off: x"
    assert all(view.closed == 1 for view in before.values())
    assert stood.readouts() == (
        "imtypeset is not drawing: imtypeset failed and is switched off: x",
    )
    assert stood.diff is shown and stood.case.key == "git" and stood.capped
    made = len(_Stand.made)
    draws = [view.draws for view in before.values()]
    monkeypatch.setattr(_Stand, "raises", None)  # the library "coming back" makes no view again
    _frame(stood)
    _frame(stood)
    assert stood.renderer == "none" and len(_Stand.made) == made
    assert [view.draws for view in before.values()] == draws


def test_the_second_pane_refusing_after_the_first_drew_leaves_a_page_that_can_be_drawn(
    stood: DiffPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    In `both`, the library can fail between the two panes: the first drew and
    answered, the second raised. (With the fallback this left a `bool` among
    `DrawStats` and an `AttributeError` on every later frame: the reviewer of
    tranche 4, from reading.) The first pane's answer is dropped with its
    view, and the next frame begins by reading the readouts: one line.
    """
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    assert stood.stats == {UNIFIED: True, SIDE: True}
    refusal = TypesetUnavailable("imtypeset failed and is switched off: between the panes")

    def refuse(**_: Any) -> bool:
        raise refusal

    first = stood.views[UNIFIED]
    monkeypatch.setattr(stood.views[SIDE], "draw", refuse)
    _frame(stood)
    assert first.draws == 2, "the first pane was drawn by its view before the second failed"
    assert stood.renderer == "none" and stood.stats == {}
    assert stood.readouts() == (f"imtypeset is not drawing: {refusal}",)
    _frame(stood)
    _frame(stood)
    assert first.draws == 2 and stood.views == {}


@pytest.mark.parametrize("where", ["set_diff", "next_hunk", "visible_rows"])
def test_a_view_that_refuses_outside_its_draw_is_caught_the_same_way(
    stood: DiffPage, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """
    The views are asked things before the panes: by the replay (`set_diff`,
    from `advance`), by the keys (`next_hunk`) and by the readouts
    (`visible_rows`). `TypesetUnavailable` from any of them is the same
    event as from `draw`, and no widget is left open.
    """
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    _frame(stood, mouse=PARKED)

    def refuse(*_: Any, **__: Any) -> Any:
        raise TypesetUnavailable(f"imtypeset cannot draw: {where}")

    if where == "visible_rows":
        # A property on the class is read before the instances' own attribute.
        monkeypatch.setattr(_Stand, "visible_rows", property(refuse), raising=False)
        _frame(stood)
    elif where == "set_diff":
        stood.rate = 600.0
        stood.start_replay()
        monkeypatch.setattr(_Stand, "set_diff", refuse)
        _frame(stood, seconds=0.1)
    else:
        monkeypatch.setattr(_Stand, "next_hunk", refuse)
        _frame(stood, keys=("j",))
        _frame(stood, release=("j",))
    assert stood.renderer == "none" and stood.reason == f"imtypeset cannot draw: {where}"
    _frame(stood)
    assert stood.readouts() == (f"imtypeset is not drawing: imtypeset cannot draw: {where}",)


def test_an_error_that_is_not_the_library_s_refusal_is_not_caught(
    stood: DiffPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Only `TypesetUnavailable` is the library's. An `IndexError` out of a
    view's `draw` leaves the page as itself -- with the pane's child window
    ended and its colour popped, so the frame can still be closed -- and the
    views are still there.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    _frame(stood, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    monkeypatch.setattr(_Stand, "raises", IndexError("a slip of the view's own"))
    imgui.new_frame()
    try:
        imgui.begin("##advtext-diff-page-test", None, imgui.WindowFlags_.no_decoration.value)
        try:
            with pytest.raises(IndexError, match="a slip of the view's own"):
                stood.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()  # asserts if a child or a style colour had been left open
    assert stood.renderer == "TypesetDiffView" and stood.reason == ""
    assert [type(view) for view in stood.views.values()] == [_Stand, _Stand]
    monkeypatch.setattr(_Stand, "raises", None)


# ----------------------------------------------------------------------
# The application in a real window, with the library and without
# ----------------------------------------------------------------------

WINDOWED = r"""
import json
import sys

from imgui_bundle import hello_imgui, imgui

from advtext import typesetter
from advtext.ui import app as advtext_app

WANT_LIBRARY = sys.argv[1] == "with"
report = {"frames": 0}
real_gui = advtext_app.App.gui


def snapshot(made):
    views = made.views
    return {
        "renderer": made.renderer,
        "reason": made.reason,
        "classes": sorted({type(view).__name__ for view in views.values()}),
        "drawn": [layout.value for layout in made.stats],
        "answered": list(made.stats.values()),
        "rows": {layout.value: view.row_count for layout, view in views.items()},
        "on_screen": {layout.value: len(views[layout].visible_rows) for layout in made.stats},
        "edits": {
            layout.value: dict(getattr(view, "edits", {})) for layout, view in views.items()
        },
        "readouts": list(made.readouts()),
        "case": made.case.key,
        "fed": made.fed,
        "old_view_loaded": "advtext.ui.diff_view" in sys.modules,
        "caps": [view.height_cap for view in views.values()],
        "hunk": [view.current_hunk for view in views.values()],
    }


def watched_gui(self):
    real_gui(self)
    report["frames"] += 1
    frame = report["frames"]
    made = self._views.get("Diff")
    if frame == 6:
        report["current"] = self.current
        report["ready"] = typesetter.ready()
        if WANT_LIBRARY:
            assert typesetter.module() is not None, "imtypeset is not in use: " + made.reason
            assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
        report["long"] = snapshot(made)
        made.expand(everything=True)
    elif frame == 10:
        report["expanded"] = snapshot(made)
        made.choose(next(case for case in made.cases if case.key == "git"))
        made.rate = 600.0
        made.start_replay()
    elif frame == 14:
        report["replaying"] = snapshot(made)
    elif frame == 40:
        report["replayed"] = snapshot(made)
        report["replay_done"] = made.replay_done
        report["errors"] = len(self.page_errors)
        if not WANT_LIBRARY:
            hello_imgui.get_runner_params().app_shall_exit = True
            return
        made.stop_replay()
        view = next(iter(made.views.values()))
        view.select_all()
        imgui.set_clipboard_text("untouched")
        view.copy()
        report["clipboard"] = imgui.get_clipboard_text()
        report["copied"] = [made.copies, made.copied == report["clipboard"]]
    elif frame == 44:
        report["after"] = snapshot(made)
        report["trouble"] = typesetter.trouble()
        # With the library: capped (each view in a child of its own), on the second hunk.
        made.set_capped(True)
        made.next_hunk()
        made.next_hunk()
    elif frame == 48:
        report["capped"] = snapshot(made)
        # What a view does when its imtypeset path raises mid-draw: from the next draw on the
        # library cannot draw, and `TypesetDiffView.draw` says so.
        typesetter.disable("switched off by the test")
    elif frame == 52:
        report["fallen"] = snapshot(made)
        report["fallen_errors"] = len(self.page_errors)
        report["fallen_frames"] = made.frames
    elif frame == 56:
        report["later_frames"] = made.frames
        hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="diff:long")
report["imported"] = "imtypeset" in sys.modules
print(json.dumps(report))
"""


def _run(window: Window, how: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    script = window.out / "page_diff.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    report: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    print(how, window.where, json.dumps(report)[:3000])  # shown by pytest when the test fails
    return report


def _with_the_library(report: dict[str, Any]) -> None:
    """What the page does in the window while the library draws."""
    assert report["current"] == "Diff" and report["errors"] == 0
    long, expanded = report["long"], report["expanded"]
    assert long["case"] == "long" and long["drawn"]
    assert set(long["drawn"]) <= {"unified", "side-by-side"}
    # Culling: every line of the long file revealed, and no more rows on screen than before.
    assert expanded["rows"]["unified"] > 4000 > long["rows"]["unified"]
    for layout in long["drawn"]:
        assert 0 < expanded["on_screen"][layout] <= long["on_screen"][layout] + 1 < 80
    # The replay: lines arrive on the frame clock, and it ends on the diff it was made from.
    replaying, replayed = report["replaying"], report["replayed"]
    assert replaying["case"] == "git" and 0 < replaying["fed"]
    assert report["replay_done"] is True and replayed["fed"] >= replaying["fed"]
    assert replayed["rows"]["unified"] >= replaying["rows"]["unified"] > 0
    # A copy goes through the page's `copy_as`.
    assert report["copied"] == [1, True] and report["clipboard"] != "untouched"
    assert not any(line.startswith(("+", "-", "@@")) for line in report["clipboard"].split("\n"))
    assert report["after"]["readouts"][4].startswith("clipboard (copy 1): ")


def test_in_a_real_window_without_the_library_the_page_says_why_not_and_stays_alive(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The application, `diff:long`, the library's variables removed: forty
    frames with no views, no error page, the library and the old view never
    imported, and the readout is the one line. The test's own calls of
    `expand`, `choose` and `start_replay` moved the page's state; with no
    frame of the page's advancing it, the replay fed nothing.
    """
    report = _run(window, "without", monkeypatch)
    assert report["current"] == "Diff" and report["errors"] == 0
    assert report["imported"] is False and report["ready"] is False
    for moment in ("long", "expanded", "replaying", "replayed"):
        entry = report[moment]
        assert entry["renderer"] == "none" and entry["classes"] == [], moment
        assert entry["reason"] == "IMTYPESET_LIBRARY is not set"
        assert entry["readouts"] == ["imtypeset is not drawing: IMTYPESET_LIBRARY is not set"]
        assert entry["drawn"] == [] and entry["rows"] == {} and entry["answered"] == []
        assert entry["old_view_loaded"] is False, moment
    assert report["long"]["case"] == "long" and report["replaying"]["case"] == "git"
    assert report["replayed"]["fed"] == 0 and report["replay_done"] is False


def test_in_a_real_window_with_the_library_the_page_draws_with_typeset_diff_view(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The application, `diff:long`, with the library: both views are
    `TypesetDiffView`s from the first frame until the library is switched
    off, every draw answers True, `advtext.ui.diff_view` is never imported,
    and the library is edited when the diff changes and not otherwise.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    report = _run(window, "with", monkeypatch)
    _with_the_library(report)
    assert report["imported"] is True and report["ready"] is True and report["trouble"] == ""
    for moment in ("long", "expanded", "replaying", "replayed", "after"):
        entry = report[moment]
        assert entry["renderer"] == "TypesetDiffView", moment
        assert entry["classes"] == ["TypesetDiffView"] and entry["reason"] == "", moment
        assert entry["answered"] and all(answer is True for answer in entry["answered"]), moment
        assert entry["readouts"][0] == "renderer: TypesetDiffView (imtypeset)"
        assert "library edits " in entry["readouts"][2] and "glyphs" not in entry["readouts"][2]
        assert entry["old_view_loaded"] is False, moment
    # The documents were set once, for the views that were drawn; an expansion, a new case and
    # every line of the replay replaced blocks and set nothing again.
    for layout in report["long"]["drawn"]:
        documents = 2 if layout == "unified" else 4
        assert report["long"]["edits"][layout] == {"set": documents, "replace": 0}
        for moment in ("expanded", "replaying", "replayed", "after"):
            assert report[moment]["edits"][layout]["set"] == documents, (moment, layout)
        replaces = [
            report[moment]["edits"][layout]["replace"]
            for moment in ("expanded", "replaying", "replayed")
        ]
        assert 0 < replaces[0] < replaces[1] <= replaces[2]

    # The library switched off mid-run, with the views capped and on the second hunk: the
    # real `TypesetDiffView.draw` raises `TypesetUnavailable`; the page catches it (no error
    # page), has no views from then on, says why in one line, and goes on being drawn.
    capped, fallen = report["capped"], report["fallen"]
    assert capped["renderer"] == "TypesetDiffView" and all(capped["answered"])
    assert capped["caps"] == [CAP_PX, CAP_PX] and capped["old_view_loaded"] is False
    assert capped["hunk"][0] == capped["hunk"][1] and capped["hunk"][0] is not None
    assert fallen["renderer"] == "none" and fallen["classes"] == []
    assert fallen["reason"] == "imtypeset cannot draw: switched off by the test"
    assert fallen["readouts"] == [f"imtypeset is not drawing: {fallen['reason']}"]
    assert fallen["drawn"] == [] and fallen["old_view_loaded"] is False
    assert fallen["case"] == capped["case"]
    assert report["fallen_errors"] == 0
    assert report["later_frames"] == report["fallen_frames"] + 4

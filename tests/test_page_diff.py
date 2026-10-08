"""
The Diff page: its cases as data, its controls as state, and the page in real frames.

Three kinds of test:

- **the cases** -- each of the nine is the shape its label says, read from the
  model: statuses, counts, what can be expanded, where the long lines and the
  one-token changes are. And the generated files under `demo/diff/` agree with
  the files they were generated from.
- **the page's state without a frame** -- every control is a method; a click
  on a widget calls nothing else.
- **real ImGui frames with no backend** -- `DiffPage.draw` inside
  `imgui.new_frame()` / `imgui.render()`, as `tests/test_pages.py` drives the
  shell: widgets run, the views cull and emit vertices, injected keys and
  mouse events are handled. No window, no GPU, no font atlas
  (`PageContext.build()` has no fonts), which changes no count asserted here.

The real window is `tests/test_pages.py::test_every_discovered_page_runs_in_a_real_window`.

Nothing here says how a diff looks. Colour assertions are "this ink reached
the vertex buffer".
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from advtext.backends.imgui_draw import DARK_PALETTE, DEFAULT_PALETTE
from advtext.diff import MAX_INTRALINE_CHARS, Diff, FileStatus, RowKind
from advtext.ui.diff_view import DiffLayout, DiffView, RowInfo
from advtext.ui.pages import PageContext, demo_text, discover
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

UNIFIED = DiffLayout.UNIFIED
SIDE = DiffLayout.SIDE_BY_SIDE
DISPLAY = (1100.0, 800.0)
PARKED = (DISPLAY[0] - 2.0, 2.0)

HARD = ("nul", "noeol", "noeol-text", "eol", "mail", "combined", "fence", "unseen", "u0")
KEYS = ("edit", "new", "long", "multiedit", "anchor", "git", "wide", "tokens", "deleted", *HARD)


def case(key: str) -> Case:
    return next(found for found in cases() if found.key == key)


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


def test_hard_a_line_ending_change_says_so_and_is_folded(bundled_fonts: Path) -> None:
    (file,) = case("eol").diff().files
    assert file.line_endings == "CRLF -> LF" and (file.added, file.removed) == (7, 7)
    page = PAGE.factory(PageContext.build())
    assert isinstance(page, DiffPage)
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


def test_hard_unseen_characters_are_placeholders_and_the_header_says_so(
    bundled_fonts: Path,
) -> None:
    """
    Review 3, item 1, on the page: no glyph is issued in a face that lacks
    it, the invisible ones are never issued at all, and the header names them.
    """
    from advtext.shipout import Glyph
    from advtext.style import fontlib_metrics
    from advtext.ui.diff_view import CONTROL_PLACEHOLDER

    (file,) = case("unseen").diff().files
    assert file.invisible_characters and (file.added, file.removed) == (4, 4)
    page = PAGE.factory(PageContext.build())
    assert isinstance(page, DiffPage)
    page.choose(case("unseen"))
    for view in page.views.values():
        plan = view.frame_plan(1200.0)
        glyphs = [c for r in plan.regions for c in r.cmds if isinstance(c, Glyph)]
        assert [g for g in glyphs if not fontlib_metrics(g.font).has(g.codepoint)] == []
        drawn = {chr(g.codepoint) for g in glyphs}
        assert not drawn & {chr(0x200B), chr(0x202E)} and CONTROL_PLACEHOLDER in drawn
        assert {chr(0x3C0), chr(0x3C4)} & drawn  # Greek, from another face
        code_face = view.metrics_px.font.key
        assert {g.font for g in glyphs if chr(g.codepoint) in (chr(0x3C0), chr(0x3C4))} != {
            code_face
        }
        header = "".join(
            chr(g.codepoint) for g in sorted(glyphs, key=lambda g: (g.y, g.x)) if g.y == glyphs[0].y
        )
        assert "invisibleorbidirectionalcontrolcharacters" in header


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


@pytest.fixture
def page(bundled_fonts: Path) -> DiffPage:
    made = PAGE.factory(PageContext.build())
    assert isinstance(made, DiffPage)
    return made


def test_the_page_opens_on_the_edit_both_layouts_light_uncapped_whole(page: DiffPage) -> None:
    assert page.case.key == "edit" and page.mode is Mode.BOTH
    assert page.context_lines == 3 and page.syntax_on
    assert not page.dark and not page.capped and not page.replaying
    assert page.palette is DEFAULT_PALETTE
    assert {layout: view.layout for layout, view in page.views.items()} == {
        UNIFIED: UNIFIED,
        SIDE: SIDE,
    }
    assert all(view.diff is page.diff for view in page.views.values())


def test_the_launch_options_set_the_case_the_mode_and_the_switches(bundled_fonts: Path) -> None:
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
    assert [view.layout for view in page.shown(BOTH_MIN_PX)] == [UNIFIED, SIDE]
    assert [view.layout for view in page.shown(BOTH_MIN_PX - 1.0)] == [UNIFIED]
    page.set_mode(Mode.SIDE)
    assert [view.layout for view in page.shown(2000.0)] == [SIDE]
    # Narrow, "both" falls back to whichever single layout was last chosen.
    page.set_mode(Mode.BOTH)
    assert [view.layout for view in page.shown(600.0)] == [SIDE]
    page.set_mode(Mode.UNIFIED)
    assert [view.layout for view in page.shown(2000.0)] == [UNIFIED]


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


def _inks(view: DiffView, palette: Any) -> set[int]:
    plan = view.frame_plan(900.0, palette=palette)
    return {ink for region in plan.regions for _, _, ink in region.inks}


def test_going_dark_recolours_the_syntax_and_keeps_what_can_be_kept(page: DiffPage) -> None:
    """
    The scheme change: one assignment per view, since review 1's item 14.

    After `set_dark` the plan carries the dark scheme's syntax inks and none
    of the light scheme's, **in the same views** -- which used to keep the
    first highlighter's colours, so the page built new views and lost the
    current hunk and the selection.
    """
    page.expand(everything=True)
    page.next_hunk()
    for view in page.views.values():
        view.select((0, 0, 0, 0), (0, 0, 1, 2))
    shown = page.diff
    light = {COLOURS[0].syntax.ink(kind) for kind in ("number", "string", "keyword", "comment")}
    dark = {COLOURS[1].syntax.ink(kind) for kind in ("number", "string", "keyword", "comment")}
    assert _inks(page.views[UNIFIED], DEFAULT_PALETTE) & light
    old = dict(page.views)
    page.set_capped(True)

    page.set_dark(True)
    assert page.palette is DARK_PALETTE
    assert all(page.views[layout] is old[layout] for layout in DiffLayout)
    assert all(view.current_hunk == (0, 0) for view in page.views.values())
    assert all(view.selection == ((0, 0, 0, 0), (0, 0, 1, 2)) for view in page.views.values())
    inks = _inks(page.views[UNIFIED], DARK_PALETTE)
    assert inks & dark and not inks & light
    assert all(view.diff is shown for view in page.views.values())
    assert all(view.height_cap == CAP_PX for view in page.views.values())
    assert [view.layout for view in page.views.values()] == [UNIFIED, SIDE]
    page.set_dark(True)  # already so: nothing is rebuilt
    assert page.views[UNIFIED].syntax is page.views[SIDE].syntax


def test_the_cap_is_the_views_own_switch(page: DiffPage) -> None:
    page.set_capped(True)
    assert all(view.height_cap == CAP_PX for view in page.views.values())
    assert page.views[UNIFIED].height_for(600.0) <= CAP_PX + 40.0
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
    assert "replay done" in page.readouts()[1]
    assert f"line {total} of {total}" in page.readouts()[1]


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
        page.draw()
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
    The page after two settling frames: mouse parked and up, every key up.
    """
    _frame(page, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    _frame(page, mouse=PARKED)
    yield page
    _frame(page, mouse=PARKED, left=False, release=ALL_KEYS_UP)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("mode", list(Mode), ids=lambda mode: mode.value)
def test_every_case_draws_in_every_mode(shown: DiffPage, key: str, mode: Mode) -> None:
    shown.choose(case(key))
    shown.set_mode(mode)
    _frame(shown)
    _frame(shown)
    expected = [UNIFIED, SIDE] if mode is Mode.BOTH else [shown.single]
    assert list(shown.stats) == expected
    for layout, stats in shown.stats.items():
        assert stats.glyphs > 50 and stats.missing == 0, (key, layout)
        assert len(shown.views[layout].visible_rows) > 0
    assert len(shown.readouts()) == 4
    assert shown.readouts()[0].startswith(f"+{shown.diff.added} -{shown.diff.removed} in ")


def test_a_narrow_body_shows_one_layout_though_both_was_asked_for(shown: DiffPage) -> None:
    assert shown.mode is Mode.BOTH and list(shown.stats) == [UNIFIED, SIDE]
    _frame(shown, size=(700.0, 800.0))
    assert list(shown.stats) == [UNIFIED]


def test_the_rows_drawn_are_the_rows_on_screen_however_long_the_diff(shown: DiffPage) -> None:
    """
    Culling, by count: twelve times the rows, about the same glyphs.
    """
    shown.choose(case("long"))
    _frame(shown)
    _frame(shown)
    collapsed = shown.views[UNIFIED].row_count
    glyphs = sum(stats.glyphs for stats in shown.stats.values())
    on_screen = len(shown.views[UNIFIED].visible_rows)
    shown.expand(everything=True)
    _frame(shown)
    _frame(shown)
    assert shown.views[UNIFIED].row_count > 8 * collapsed
    assert len(shown.views[UNIFIED].visible_rows) == on_screen < 60
    after = sum(stats.glyphs for stats in shown.stats.values())
    assert 0.3 * glyphs < after < 3.0 * glyphs
    assert f"rows: unified {shown.views[UNIFIED].row_count}" in shown.readouts()[0]


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


def test_ctrl_c_copies_code_with_no_marker_and_no_line_number(shown: DiffPage) -> None:
    """
    The readout the spec asks for, from a real key event through the view.

    The selection is the whole unified diff of the small edit: a removed line,
    two added ones and their context. What reaches the clipboard is lines of
    the *file* -- the new side -- and the page's readout is that text.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    imgui.set_clipboard_text("sentinel")
    view = shown.views[UNIFIED]
    view.select_all()
    assert view.owns_selection
    _frame(shown, keys=("mod_ctrl", "c"))
    _frame(shown, release=("mod_ctrl", "c"))
    copied = imgui.get_clipboard_text()
    assert shown.copied == copied and shown.copies == 1
    after = demo_text("diff/edit.after.py")
    assert after is not None
    lines = copied.split("\n")
    assert len(lines) == 8  # three of context, two added, three of context
    assert "\n".join(lines) in after
    assert not any(line.startswith(("+", "-", "@@")) for line in lines)
    assert "time.sleep(jittered(waits[attempt]))" in copied
    assert "time.sleep(waits[attempt])" not in copied  # the removed line is not on that side
    assert shown.readouts()[3].startswith("clipboard (copy 1): 8 line(s)")


def _row_centre(view: DiffView, row: int) -> tuple[float, float]:
    assert view.origin is not None
    metrics = view.metrics_px
    return (view.origin[0] + 30.0 * metrics.cell, view.origin[1] + (row + 0.5) * metrics.row)


def test_a_click_on_a_collapsed_row_in_one_view_expands_both(shown: DiffPage) -> None:
    unified, side = shown.views[UNIFIED], shown.views[SIDE]
    gaps = [row for row in range(unified.row_count) if unified.row_info(row).kind == "gap"]
    assert len(gaps) == 2 and unified.row_info(gaps[0]) == RowInfo("gap", 0, 0)
    before = shown.diff
    rows = (unified.row_count, side.row_count)
    _frame(shown, mouse=_row_centre(unified, gaps[0]))
    _frame(shown, left=True)
    _frame(shown, left=False)
    _frame(shown, mouse=PARKED)
    assert shown.diff is not before
    assert unified.diff is shown.diff and side.diff is shown.diff
    assert unified.row_count > rows[0] and side.row_count > rows[1]
    assert unified.selection is None


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
    assert shown.stats[UNIFIED].glyphs > 50


def test_a_wide_line_scrolls_sideways_and_the_scroll_survives_a_scheme_change(
    shown: DiffPage,
) -> None:
    shown.choose(case("wide"))
    _frame(shown)
    _frame(shown)
    view = shown.views[UNIFIED]
    assert view.content_width > 4 * DISPLAY[0]
    view.scroll_x = 480
    _frame(shown)
    assert view.scroll_x == 480
    shown.set_dark(True)
    _frame(shown)
    _frame(shown)
    assert shown.views[UNIFIED] is view and view.scroll_x == 480


def test_dark_draws_the_dark_palette_and_its_ground(shown: DiffPage) -> None:
    light = _frame(shown)
    assert {DEFAULT_PALETTE.page, DEFAULT_PALETTE.diff.add, DEFAULT_PALETTE.diff.remove} <= light
    shown.set_dark(True)
    _frame(shown)
    dark = _frame(shown)
    wanted = {DARK_PALETTE.page, DARK_PALETTE.diff.add, DARK_PALETTE.diff.remove}
    assert wanted <= dark
    assert COLOURS[1].syntax.keyword in dark and COLOURS[0].syntax.keyword not in dark
    assert DEFAULT_PALETTE.page not in dark


def test_syntax_off_takes_the_syntax_inks_out_of_the_frame(shown: DiffPage) -> None:
    keyword = COLOURS[0].syntax.keyword
    assert keyword in _frame(shown)
    shown.set_syntax(False)
    assert keyword not in _frame(shown)
    shown.set_syntax(True)
    assert keyword in _frame(shown)


def test_capped_the_view_scrolls_inside_its_own_short_child(shown: DiffPage) -> None:
    shown.choose(case("git"))
    _frame(shown)
    _frame(shown)
    tall = len(shown.views[UNIFIED].visible_rows)
    shown.set_capped(True)
    _frame(shown)
    _frame(shown)
    row = shown.views[UNIFIED].metrics_px.row
    short = len(shown.views[UNIFIED].visible_rows)
    assert short < tall and short <= CAP_PX / row + 2
    assert shown.stats[UNIFIED].glyphs > 50


def test_the_cost_readout_is_the_time_around_the_views_and_nothing_else(
    bundled_fonts: Path,
) -> None:
    ticks = iter(range(1000))
    made = DiffPage(PageContext.build(), timer=lambda: next(ticks) * 0.002)
    _frame(made, mouse=PARKED, left=False, release=ALL_KEYS_UP)
    assert made.draw_ms == pytest.approx(2.0)
    _frame(made)
    assert made.draw_ms == pytest.approx(2.0) and made.mean_ms == pytest.approx(2.0)
    assert "2.00 ms this frame, 2.00 mean" in made.readouts()[1]
    assert made.frames == 2

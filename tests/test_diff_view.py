r"""
`DiffView`: what a frame holds, and what the mouse and the keys do to it.

Two fidelities, as in `tests/test_bare_view.py`:

- `DiffView.frame_plan` is pure, so what a frame would issue -- which glyphs,
  in which region, in which ink, over which fills -- is asserted with no ImGui
  at all. The real code face is measured (`bundled_fonts`), so the grid is the
  one a window would get.
- Real ImGui frames with no display, for everything that is about items, the
  mouse, the clipboard and scrolling. `fonts=lambda face: None` throughout, so
  the process-global atlas is never touched and glyphs go out in ImGui's
  default face.

And once, at the end, a real window: both layouts on an Xvfb, counts only.
Nothing here says how any of it looks.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Sequence
from dataclasses import fields
from typing import Any

import pytest

from advtext.backends.imgui_draw import (
    DARK_PALETTE,
    DEFAULT_PALETTE,
    DiffPalette,
    Palette,
)
from advtext.diff import ContextUnavailable, Diff, RowKind, UnifiedDiffStream
from advtext.markdown import build_document
from advtext.selection import Selection
from advtext.shipout import Glyph
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui.bare_view import BareView
from advtext.ui.diff_view import (
    CONTROL_PLACEHOLDER,
    COPY_GAP,
    SYNTAX_CHUNK,
    DiffLayout,
    DiffView,
    FramePlan,
    Region,
    RowInfo,
    language_for,
)
from advtext.units import px_from_sp, sp_from_px
from tests.conftest import Window

UNIFIED, SIDE = DiffLayout.UNIFIED, DiffLayout.SIDE_BY_SIDE


def numbered(count: int) -> str:
    return "".join(f"line {i}\n" for i in range(1, count + 1))


BEFORE = numbered(100)
AFTER = (
    BEFORE.replace("line 20\n", "line 20 changed\n")
    .replace("line 21\n", "")
    .replace("line 60\n", "line 60\nan added line\n")
)
"""
A hundred lines, three edits in two hunks: a line changed (one pair, with an
intra-line span), a line removed, a line added.
"""

WIDTH = 640.0


@pytest.fixture
def view(bundled_fonts: Any) -> DiffView:
    return DiffView(Diff.from_texts(BEFORE, AFTER, "notes.py"), Theme.build())


def rows_of(view: DiffView, kind: str = "row") -> list[int]:
    return [row for row in range(view.row_count) if view.row_info(row).kind == kind]


def baseline(view: DiffView, row: int) -> int:
    metrics = view.metrics_px
    return sp_from_px(float(row * metrics.row)) + sp_from_px(float(metrics.baseline))


def column(view: DiffView, glyph: Glyph) -> int:
    """Which cell a glyph of a region is in."""
    return round(px_from_sp(glyph.x) / view.metrics_px.cell)


def glyphs_on(view: DiffView, region: Region, row: int) -> list[Glyph]:
    y = baseline(view, row)
    return sorted((c for c in region.cmds if isinstance(c, Glyph) and c.y == y), key=lambda c: c.x)


def ink_of(region: Region, glyph: Glyph) -> int:
    for start, end, colour in region.inks:
        if start <= glyph.index < end:
            return colour
    return region.ink


def find_row(view: DiffView, text: str, kind: RowKind) -> int:
    """The display row showing the line `text` of kind `kind`."""
    for row in rows_of(view):
        info = view.row_info(row)
        hunk = view.diff.files[info.file].hunks[info.hunk or 0]
        for at in (info.left, info.right):
            if at is not None and hunk.rows[at].kind is kind and hunk.rows[at].text == text:
                return row
    raise AssertionError(f"no {kind} row {text!r}")


# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------


def test_the_grid_is_whole_pixels_measured_from_the_code_face(view: DiffView) -> None:
    metrics = view.metrics_px
    assert isinstance(metrics.cell, int) and isinstance(metrics.row, int)
    assert metrics.cell == round(metrics.advance) >= 1
    assert 0 < metrics.baseline < metrics.row
    assert metrics.font.face is view.theme.faces.code
    assert view.content_height == view.row_count * metrics.row


def test_a_host_pixel_height_sizes_the_code_face(bundled_fonts: Any) -> None:
    diff = Diff.from_texts("a\n", "b\n", "f")
    small = DiffView(diff, Theme.build(), pixel_height=12.0).metrics_px
    large = DiffView(diff, Theme.build(), pixel_height=24.0).metrics_px
    assert small.cell < large.cell and small.row < large.row
    # Inconsolata's advance is half its em: 24 px tall is a 12 px pitch, exactly.
    assert abs(large.advance - 2 * small.advance) < 0.01


def test_every_glyph_sits_on_the_grid(view: DiffView) -> None:
    plan = view.frame_plan(WIDTH)
    cell = view.metrics_px.cell
    seen = 0
    for region in plan.regions:
        for cmd in region.cmds:
            if isinstance(cmd, Glyph):
                assert abs(px_from_sp(cmd.x) / cell - round(px_from_sp(cmd.x) / cell)) < 1e-3
                seen += 1
    assert seen == plan.glyphs > 200


# ---------------------------------------------------------------------------
# what is drawn: unified
# ---------------------------------------------------------------------------


def test_display_rows_are_file_gap_hunk_and_rows_in_order(view: DiffView) -> None:
    kinds = [view.row_info(row).kind for row in range(view.row_count)]
    assert kinds[:3] == ["file", "gap", "hunk"]
    assert kinds.count("file") == 1 and kinds.count("hunk") == 2 and kinds.count("gap") == 3
    assert kinds[-1] == "gap"
    assert kinds.count("row") == sum(len(h.rows) for h in view.diff.files[0].hunks)


def test_the_gutter_holds_both_numbers_and_the_marker_and_the_code_holds_neither(
    view: DiffView,
) -> None:
    plan = view.frame_plan(WIDTH)
    frame, code = plan.region("frame"), plan.region("code")
    removed = find_row(view, "line 21", RowKind.REMOVE)
    added = find_row(view, "an added line", RowKind.ADD)
    context = find_row(view, "line 19", RowKind.CONTEXT)
    assert frame.text_at(baseline(view, removed)) == "21-"
    assert frame.text_at(baseline(view, added)) == "60+"
    assert frame.text_at(baseline(view, context)) == "1919"
    assert code.text_at(baseline(view, removed)) == "line21"
    assert code.text_at(baseline(view, added)) == "anaddedline"
    # ... and the marker is in the gutter's ink, the same for both kinds.
    colours = DEFAULT_PALETTE.diff
    for row in (removed, added):
        marker = glyphs_on(view, frame, row)[-1]
        assert chr(marker.codepoint) in "+-" and ink_of(frame, marker) == colours.gutter


def test_the_gutter_does_not_scroll_and_the_code_does(view: DiffView) -> None:
    still = view.frame_plan(WIDTH)
    view.scroll_x = 5 * view.metrics_px.cell  # clamped at draw, not here
    view._max_scroll_x = 10**6
    moved = view.frame_plan(WIDTH)
    assert moved.region("frame") == still.region("frame")
    # No line here is long enough to scroll at this width: the plan clamps.
    assert moved.region("code").x == still.region("code").x


LONG = "x = [" + ", ".join(str(i) for i in range(2000)) + "]"


@pytest.fixture
def wide(bundled_fonts: Any) -> DiffView:
    before = numbered(30)
    after = before.replace("line 10\n", LONG + "\n")
    return DiffView(Diff.from_texts(before, after, "wide.py"), Theme.build())


def test_a_long_line_is_scrolled_under_a_clip_and_only_its_visible_columns_are_issued(
    wide: DiffView,
) -> None:
    cell = wide.metrics_px.cell
    row = find_row(wide, LONG, RowKind.ADD)
    still = wide.frame_plan(WIDTH)
    code = still.region("code")
    in_view = int((code.clip[1] - code.clip[0]) // cell)
    drawn = glyphs_on(wide, code, row)
    assert 0 < len(drawn) <= in_view + 2 < len(LONG)
    assert code.clip[0] == code.x  # not scrolled: column 0 is at the clip's left edge
    assert wide.content_width > WIDTH

    wide.scroll_x = 400 * cell
    moved = wide.frame_plan(WIDTH)
    shifted = moved.region("code")
    assert shifted.x == code.x - 400 * cell and shifted.clip == code.clip
    assert moved.region("frame") == still.region("frame")  # the gutter stayed
    columns = [column(wide, glyph) for glyph in glyphs_on(wide, shifted, row)]
    assert min(columns) >= 400 and max(columns) <= 400 + in_view + 2
    assert all(chr(g.codepoint) == LONG[column(wide, g)] for g in glyphs_on(wide, shifted, row))


def test_added_and_removed_rows_have_a_band_and_the_changed_part_a_mark(view: DiffView) -> None:
    plan = view.frame_plan(WIDTH)
    colours = DEFAULT_PALETTE.diff
    metrics = view.metrics_px
    bands = {
        round(px_from_sp(rect.y) / metrics.row): colour
        for rect, colour in plan.region("frame").fills
        if colour in (colours.add_fill, colours.remove_fill)
    }
    old = find_row(view, "line 20", RowKind.REMOVE)
    new = find_row(view, "line 20 changed", RowKind.ADD)
    gone = find_row(view, "line 21", RowKind.REMOVE)
    more = find_row(view, "an added line", RowKind.ADD)
    assert bands == {
        old: colours.remove_fill,
        gone: colours.remove_fill,
        new: colours.add_fill,
        more: colours.add_fill,
    }
    # One intra-line mark: " changed" on the added line, from column 7 to 15.
    marks = plan.region("code").fills
    assert [colour for _, colour in marks] == [colours.add_emphasis]
    rect = marks[0][0]
    assert round(px_from_sp(rect.y) / metrics.row) == new
    assert round(px_from_sp(rect.x) / metrics.cell) == 7
    assert round(px_from_sp(rect.width) / metrics.cell) == 8


def test_text_is_inked_by_kind(view: DiffView) -> None:
    code = view.frame_plan(WIDTH).region("code")
    colours = DEFAULT_PALETTE.diff
    for text, kind, ink in (
        ("line 21", RowKind.REMOVE, colours.remove),
        ("an added line", RowKind.ADD, colours.add),
        ("line 19", RowKind.CONTEXT, colours.context),
    ):
        drawn = glyphs_on(view, code, find_row(view, text, kind))
        assert drawn and {ink_of(code, glyph) for glyph in drawn} == {ink}


def test_tabs_are_expanded_to_four_columns_and_marks_follow_them(bundled_fonts: Any) -> None:
    view = DiffView(Diff.from_texts("\tif x:\n", "\tif why:\n", "t.py"), Theme.build())
    plan = view.frame_plan(WIDTH)
    code = plan.region("code")
    row = find_row(view, "\tif why:", RowKind.ADD)
    assert [column(view, glyph) for glyph in glyphs_on(view, code, row)] == [4, 5, 7, 8, 9, 10]
    cell = view.metrics_px.cell
    spans = sorted(
        (round(px_from_sp(r.x) / cell), round(px_from_sp(r.width) / cell)) for r, _ in code.fills
    )
    assert spans == [(7, 1), (7, 3)]  # "x" and "why", both starting in column 7


def test_headers_say_the_file_its_counts_its_state_and_whether_it_will_apply(
    bundled_fonts: Any,
) -> None:
    files = (
        Diff.from_texts("a\n", "b\nc\n", "changed.py").files
        + Diff.from_texts(None, "x\n", "fresh.py").files
        + Diff.from_texts("x\n", None, "gone.py").files
        + Diff.from_texts("a\0", "b", "blob.bin", binary=True).files
        + Diff.from_texts("a\n", "a\n", "same.py").files
        + Diff.from_texts("old", "new", "x.py", will_not_apply="anchor not found in file").files
    )
    view = DiffView(Diff(files), Theme.build())
    frame = view.frame_plan(2000.0).region("frame")
    headers = [frame.text_at(baseline(view, row)) for row in rows_of(view, "file")]
    assert headers == [
        "changed.py+2-1",
        "fresh.py+1-0(newfile)",
        "gone.py+0-1(deletedfile)",
        "blob.bin+0-0(binaryfile)",
        "same.py+0-0(nochanges)",
        "x.py+1-1!anchornotfoundinfile",
    ]
    colours = DEFAULT_PALETTE.diff
    last = glyphs_on(view, frame, rows_of(view, "file")[-1])
    assert {ink_of(frame, glyph) for glyph in last} == {colours.header, colours.warning}
    assert ink_of(frame, last[-1]) == colours.warning
    hunk = rows_of(view, "hunk")[0]
    assert frame.text_at(baseline(view, hunk)) == "@@-1+1,2@@"
    assert {ink_of(frame, glyph) for glyph in glyphs_on(view, frame, hunk)} == {colours.header}


def test_a_collapsed_context_row_says_how_many_lines_and_whether_it_can_show_them(
    view: DiffView,
) -> None:
    frame = view.frame_plan(WIDTH).region("frame")
    gaps = rows_of(view, "gap")
    assert [frame.text_at(baseline(view, row)) for row in gaps] == [
        "...16unchangedlines(clicktoshowmore)",
        "...33unchangedlines(clicktoshowmore)",
        "...37unchangedlines(clicktoshowmore)",
    ]
    parsed = DiffView(Diff.from_unified(view.diff.to_unified()), Theme.build())
    frame = parsed.frame_plan(WIDTH).region("frame")
    # Read from text: the sizes its ranges bracket, no offer, and no last gap.
    assert [frame.text_at(baseline(parsed, row)) for row in rows_of(parsed, "gap")] == [
        "...16unchangedlines",
        "...33unchangedlines",
    ]
    with pytest.raises(ContextUnavailable):
        parsed.expand(0, 1)


def test_every_colour_in_a_frame_comes_from_the_palette(view: DiffView) -> None:
    names = [f.name for f in fields(DiffPalette)]
    odd = DiffPalette(**{name: 0xB0000000 + at for at, name in enumerate(names)})
    palette = Palette(highlight=0xB00000FF, diff=odd)
    view.select_all()
    view.next_hunk()
    plan = view.frame_plan(WIDTH, palette=palette)
    used: set[int] = set()
    for region in plan.regions:
        used.add(region.ink)
        used.update(colour for _, _, colour in region.inks)
        used.update(colour for _, colour in region.fills)
    allowed = {getattr(odd, name) for name in names}
    assert used <= allowed
    # Every role this diff can show was used: nothing is silently unread.
    assert allowed - used == {odd.warning, odd.remove_emphasis}
    assert any(region.highlights for region in plan.regions)


def test_light_and_dark_defaults_differ_and_neither_drops_the_markers(view: DiffView) -> None:
    assert DEFAULT_PALETTE.diff != DARK_PALETTE.diff
    for palette in (DEFAULT_PALETTE, DARK_PALETTE):
        frame = view.frame_plan(WIDTH, palette=palette).region("frame")
        markers = [
            chr(glyphs_on(view, frame, row)[-1].codepoint)
            for row in (
                find_row(view, "line 21", RowKind.REMOVE),
                find_row(view, "an added line", RowKind.ADD),
            )
        ]
        assert markers == ["-", "+"]


# ---------------------------------------------------------------------------
# what is drawn: side by side
# ---------------------------------------------------------------------------


def test_side_by_side_puts_old_on_the_left_new_on_the_right_and_blanks_between(
    view: DiffView,
) -> None:
    view.set_layout(SIDE)
    plan = view.frame_plan(WIDTH)
    assert [region.name for region in plan.regions] == ["frame", "old", "new"]
    old, new, frame = plan.region("old"), plan.region("new"), plan.region("frame")
    pair = find_row(view, "line 20", RowKind.REMOVE)
    assert view.row_info(pair) == RowInfo("row", 0, 0, 3, 5)
    assert old.text_at(baseline(view, pair)) == "line20"
    assert new.text_at(baseline(view, pair)) == "line20changed"
    assert frame.text_at(baseline(view, pair)) == "20-20+"
    lone = find_row(view, "line 21", RowKind.REMOVE)
    assert view.row_info(lone).right is None
    assert old.text_at(baseline(view, lone)) == "line21"
    assert new.text_at(baseline(view, lone)) == ""  # a blank cell
    assert frame.text_at(baseline(view, lone)) == "21-"
    added = find_row(view, "an added line", RowKind.ADD)
    assert old.text_at(baseline(view, added)) == ""
    assert frame.text_at(baseline(view, added)) == "60+"
    # A context row is on both sides, numbered on each.
    context = find_row(view, "line 19", RowKind.CONTEXT)
    assert old.text_at(baseline(view, context)) == new.text_at(baseline(view, context)) == "line19"
    # The bands stay in their own pane.
    colours = DEFAULT_PALETTE.diff
    for rect, colour in frame.fills:
        if colour == colours.remove_fill:
            assert px_from_sp(rect.x + rect.width) <= old.clip[1] + 0.01
        if colour == colours.add_fill:
            assert px_from_sp(rect.x) >= new.clip[0] - view.metrics_px.cell * 8


def test_both_sides_share_one_horizontal_offset(wide: DiffView) -> None:
    wide.set_layout(SIDE)
    still = wide.frame_plan(WIDTH)
    wide.scroll_x = 300 * wide.metrics_px.cell
    moved = wide.frame_plan(WIDTH)
    for name in ("old", "new"):
        assert moved.region(name).x == still.region(name).x - 300 * wide.metrics_px.cell
        assert moved.region(name).clip == still.region(name).clip
    assert moved.region("frame") == still.region("frame")
    assert still.region("old").clip[1] <= still.region("new").clip[0]


def test_side_by_side_has_fewer_rows_than_unified_and_a_wider_natural_width(
    view: DiffView,
) -> None:
    unified_rows, unified_width = view.row_count, view.content_width
    view.set_layout(SIDE)
    assert view.row_count == unified_rows - 1  # one pair shares a row
    assert view.content_width > unified_width


# ---------------------------------------------------------------------------
# culling
# ---------------------------------------------------------------------------


def test_a_plan_holds_only_the_rows_asked_for(view: DiffView) -> None:
    plan = view.frame_plan(WIDTH, 5, 9)
    assert (plan.first_row, plan.stop_row) == (5, 9)
    metrics = view.metrics_px
    rows = {
        int(px_from_sp(c.y) // metrics.row)
        for region in plan.regions
        for c in region.cmds
        if isinstance(c, Glyph)
    }
    assert rows == {5, 6, 7, 8}
    assert view.frame_plan(WIDTH, 10**6, 10**7).glyphs == 0


def test_the_cost_of_a_frame_does_not_grow_with_the_diff(bundled_fonts: Any) -> None:
    """Counted, not timed: the commands issued for one window of rows."""
    counts = []
    for lines in (60, 6000):
        # Lines of one width whatever the count, so the two windows differ
        # in nothing but how much diff there is around them.
        before = "".join(f"line {i:05d}\n" for i in range(1, lines + 1))
        after = "".join(
            f"line {i:05d} edited\n" if i % 7 == 3 else f"line {i:05d}\n"
            for i in range(1, lines + 1)
        )
        view = DiffView(Diff.from_texts(before, after, "big.py", context=10**9), Theme.build())
        middle = view.row_count // 2
        plan = view.frame_plan(WIDTH, middle, middle + 30)
        counts.append(sum(len(region.cmds) for region in plan.regions))
    assert counts[1] < counts[0] * 1.3, counts  # a hundred times the rows


# ---------------------------------------------------------------------------
# syntax colour
# ---------------------------------------------------------------------------


def test_language_is_guessed_from_the_label() -> None:
    assert language_for("advtext/diff.py") == "python"
    assert language_for("a/b/thing.RS") == "rust"
    assert language_for("notes.txt") == "txt"
    assert language_for("Makefile") == "make"
    assert language_for("edit 1") == ""


def test_the_highlighter_sees_one_sides_lines_and_its_colours_reach_the_glyphs(
    bundled_fonts: Any,
) -> None:
    calls: list[tuple[list[str], str]] = []
    KEYWORD = 0xC0000001

    def syntax(lines: Sequence[str], language: str) -> list[list[tuple[int, int, int]]]:
        calls.append((list(lines), language))
        return [[(0, 4, KEYWORD)] if line.startswith("line") else [] for line in lines]

    view = DiffView(Diff.from_texts(BEFORE, AFTER, "notes.py"), Theme.build(), syntax=syntax)
    plan = view.frame_plan(WIDTH)
    code = plan.region("code")
    first = view.diff.files[0].hunks[0]
    old_side = [r.text for r in first.rows if r.kind in (RowKind.CONTEXT, RowKind.REMOVE)]
    new_side = [r.text for r in first.rows if r.kind in (RowKind.CONTEXT, RowKind.ADD)]
    assert (old_side, "python") in calls and (new_side, "python") in calls
    # Both sides of the first hunk. The second removes nothing, and a context
    # row takes the new side's colours, so its old side is never asked for.
    assert len(calls) == 3 == view.syntax_calls
    colours = DEFAULT_PALETTE.diff
    for text, kind, ink in (
        ("line 19", RowKind.CONTEXT, colours.context),
        ("line 21", RowKind.REMOVE, colours.remove),
        ("line 20 changed", RowKind.ADD, colours.add),
    ):
        drawn = glyphs_on(view, code, find_row(view, text, kind))
        assert [ink_of(code, glyph) for glyph in drawn[:4]] == [KEYWORD] * 4
        assert {ink_of(code, glyph) for glyph in drawn[4:]} == {ink}
    view.frame_plan(WIDTH)
    assert view.syntax_calls == 3  # kept: the rows are the same objects


def test_only_the_chunks_on_screen_are_highlighted_and_a_failure_is_counted(
    bundled_fonts: Any,
) -> None:
    def syntax(lines: Sequence[str], language: str) -> list[list[tuple[int, int, int]]]:
        if any(line == "line 3" for line in lines):
            raise RuntimeError("the host's tokeniser fell over")
        return [[] for _ in lines]

    lines = SYNTAX_CHUNK * 5
    view = DiffView(Diff.from_texts(None, numbered(lines), "new.py"), Theme.build(), syntax=syntax)
    view.frame_plan(WIDTH, 2 * SYNTAX_CHUNK + 10, 2 * SYNTAX_CHUNK + 40)
    assert (view.syntax_calls, view.syntax_lines, view.syntax_errors) == (1, SYNTAX_CHUNK, 0)
    plan = view.frame_plan(WIDTH, 0, 30)  # the chunk that raises: drawn, uncoloured
    assert (view.syntax_calls, view.syntax_errors) == (2, 1)
    assert plan.glyphs > 100
    view.frame_plan(WIDTH, 0, 30)
    assert view.syntax_calls == 2  # and not asked again every frame


# ---------------------------------------------------------------------------
# a model that grows
# ---------------------------------------------------------------------------


def test_a_stream_that_grew_by_rows_costs_the_new_rows(bundled_fonts: Any) -> None:
    """
    Count-based. Per new line: one row measured, one syntax chunk re-asked
    (the last one of the side that grew), and settled chunks left alone.
    """
    asked: list[int] = []

    def syntax(lines: Sequence[str], language: str) -> list[list[tuple[int, int, int]]]:
        asked.append(len(lines))
        return [[] for _ in lines]

    text = Diff.from_texts(None, numbered(SYNTAX_CHUNK * 3 + 50), "new.py").to_unified()
    lines = text.splitlines(keepends=True)
    stream = UnifiedDiffStream()
    stream.feed("".join(lines[:-40]))
    view = DiffView(stream.diff, Theme.build(), syntax=syntax)
    last = view.row_count
    view.frame_plan(WIDTH, last - 8, last)
    measured = view.measured_rows
    assert measured == SYNTAX_CHUNK * 3 + 50 - 40
    assert asked == [10]  # the fourth chunk holds ten lines so far
    for line in lines[-40:-30]:
        stream.feed(line)
        view.set_diff(stream.diff)
        before, calls = view.measured_rows, len(asked)
        view.frame_plan(WIDTH, view.row_count - 8, view.row_count)
        assert view.measured_rows == before + 1
        assert len(asked) == calls + 1 and asked[-1] <= SYNTAX_CHUNK
    assert view.row_count == last + 10
    # Scrolling back over a settled chunk asks once, and never again.
    view.frame_plan(WIDTH, 5, 35)
    settled = len(asked)
    stream.feed(lines[-30])
    view.set_diff(stream.diff)
    view.frame_plan(WIDTH, 5, 35)
    assert len(asked) == settled and view.measured_rows == measured + 11


def test_set_diff_with_the_same_object_does_nothing_and_a_new_one_replaces_it(
    view: DiffView,
) -> None:
    shown = view.diff
    view.expand(0, 1, 5)
    expanded = view.diff
    assert expanded is not shown and view.row_count > 0
    view.set_diff(shown)  # the host calling every frame with its own object
    assert view.diff is expanded
    other = Diff.from_texts("a\n", "b\n", "other.py")
    view.set_diff(other)
    assert view.diff is other and view.row_count == 4


# ---------------------------------------------------------------------------
# selection and copy, through the methods
# ---------------------------------------------------------------------------


def side_of(diff: Diff, kinds: tuple[RowKind, ...]) -> str:
    """
    One side of every hunk, as a copy of everything gives it since review 1
    (item 5): hunks that are not next to each other are parted by a line
    holding `COPY_GAP`, and files by that and the next file's label. Written
    out here from the model, not taken from the view.
    """
    out: list[str] = []
    for file in diff.files:
        for h, hunk in enumerate(file.hunks):
            lines = [row.text for row in hunk.rows if row.kind in kinds]
            if not lines:
                continue
            if out and h == 0:
                out += [COPY_GAP, file.label]
            elif out and file.gaps[h].count != 0:
                out.append(COPY_GAP)
            out += lines
    return "\n".join(out)


def new_side_of(diff: Diff) -> str:
    return side_of(diff, (RowKind.CONTEXT, RowKind.ADD))


def old_side_of(diff: Diff) -> str:
    return side_of(diff, (RowKind.CONTEXT, RowKind.REMOVE))


def test_select_all_in_unified_is_the_new_text_with_no_markers_or_numbers(view: DiffView) -> None:
    view.select_all()
    assert view.owns_selection
    copied = view.selected_text()
    assert copied == new_side_of(view.diff)
    assert "line 20 changed" in copied and "an added line" in copied
    assert "line 21" not in copied.split("\n")  # the removed line
    assert "@@" not in copied and "+" not in copied and "unchanged" not in copied


def test_removed_lines_are_copied_only_when_they_are_all_that_is_selected(view: DiffView) -> None:
    hunk = view.diff.files[0].hunks[0]
    kinds = "".join(row.kind.value for row in hunk.rows)
    assert kinds == "   --+   "
    view.select((0, 0, 3, 0), (0, 0, 4, 7))  # the two removed lines
    assert view.selected_text() == "line 20\nline 21"
    view.select((0, 0, 3, 5), (0, 0, 3, 7))  # part of one
    assert view.selected_text() == "20"
    view.select((0, 0, 2, 0), (0, 0, 5, 15))  # context, both removed, the added one
    assert view.selected_text() == "line 19\nline 20 changed"
    # A context line touched only at its very end does not count as selected.
    view.select((0, 0, 2, 7), (0, 0, 4, 7))
    assert view.selected_text() == "line 20\nline 21"
    view.copy_removed_lines = True
    view.select((0, 0, 2, 0), (0, 0, 5, 15))
    assert view.selected_text() == "line 19\nline 20\nline 21\nline 20 changed"


def test_the_highlight_covers_exactly_the_lines_a_copy_returns(view: DiffView) -> None:
    view.select((0, 0, 2, 0), (0, 0, 5, 15))
    marks = view.frame_plan(WIDTH).region("code").highlights
    metrics = view.metrics_px
    rows = sorted(round(px_from_sp(rect.y) / metrics.row) for rect in marks)
    assert rows == [
        find_row(view, "line 19", RowKind.CONTEXT),
        find_row(view, "line 20 changed", RowKind.ADD),
    ]
    widths = sorted(round(px_from_sp(rect.width) / metrics.cell) for rect in marks)
    assert widths == [8, 15]  # "line 19" and its line end; "line 20 changed" to the caret


def test_side_by_side_selects_one_side_and_fillers_are_not_lines(view: DiffView) -> None:
    view.set_layout(SIDE)
    view.select_all(0)
    assert view.selection_side == 0
    assert view.selected_text() == old_side_of(view.diff)
    assert "line 21" in view.selected_text() and "an added line" not in view.selected_text()
    plan = view.frame_plan(WIDTH)
    assert plan.region("old").highlights and not plan.region("new").highlights
    view.select_all(1)
    assert view.selected_text() == new_side_of(view.diff)
    assert view.selected_text().count("\n\n") == 0  # no blank line for a filler cell
    plan = view.frame_plan(WIDTH)
    assert plan.region("new").highlights and not plan.region("old").highlights


def test_a_copy_is_cut_from_the_models_text_so_tabs_come_back_as_tabs(bundled_fonts: Any) -> None:
    view = DiffView(Diff.from_texts("\tif x:\n", "\tif why:\n\t\tpass\n", "t.py"), Theme.build())
    view.select_all()
    assert view.selected_text() == "\tif why:\n\t\tpass"


def test_the_host_decides_what_a_copy_is(view: DiffView) -> None:
    view.copy_as = lambda v: f"<{len(v.selected_text())}>"
    view.select((0, 0, 3, 0), (0, 0, 3, 7))
    assert view._copied() == "<7>"


def test_a_selection_survives_a_model_that_grew_and_is_cleared_when_its_rows_are_gone(
    bundled_fonts: Any,
) -> None:
    stream = UnifiedDiffStream()
    stream.feed("@@ -1,3 +1,4 @@\n one\n-two\n+TWO\n")
    view = DiffView(stream.diff, Theme.build())
    view.select((0, 0, 1, 0), (0, 0, 2, 3))
    stream.feed("+and a half\n three\n")
    view.set_diff(stream.diff)
    assert view.selection == ((0, 0, 1, 0), (0, 0, 2, 3)) and view.selected_text() == "TWO"
    view.set_diff(Diff.from_unified("@@ -1 +1 @@\n-something\n+else\n"))
    assert view.selection is None and view.selected_text() == ""
    view.select_all()
    view.set_layout(SIDE)
    assert view.selection is None


# ---------------------------------------------------------------------------
# hunks and rows, for a host's keys
# ---------------------------------------------------------------------------


def test_next_and_previous_hunk_walk_the_hunks_and_stop_at_the_ends(view: DiffView) -> None:
    assert view.current_hunk is None
    assert view.next_hunk() == (0, 0) == view.current_hunk
    assert view.next_hunk() == (0, 1)
    assert view.next_hunk() == (0, 1)  # stays on the last
    assert view.previous_hunk() == (0, 0)
    assert view.previous_hunk() == (0, 0)
    fresh = DiffView(view.diff, view.theme)
    assert fresh.previous_hunk() == (0, 1)  # none current: the last
    empty = DiffView(Diff(), view.theme)
    assert empty.next_hunk() is None and empty.row_count == 0


def test_the_current_hunk_has_a_bar_down_its_rows(view: DiffView) -> None:
    colours = DEFAULT_PALETTE.diff
    assert not [1 for _, c in view.frame_plan(WIDTH).region("frame").fills if c == colours.current]
    view.next_hunk()
    bars = [r for r, c in view.frame_plan(WIDTH).region("frame").fills if c == colours.current]
    hunk = view.diff.files[0].hunks[0]
    assert len(bars) == 1 + len(hunk.rows)  # the header and every row
    assert {px_from_sp(rect.x) for rect in bars} == {0.0}


def test_a_row_can_be_found_again_in_the_other_layout(view: DiffView) -> None:
    for row in range(view.row_count):
        assert view.row_of(view.row_info(row)) == row
    infos = [view.row_info(row) for row in range(view.row_count)]
    view.set_layout(SIDE)
    for row in range(view.row_count):
        assert view.row_of(view.row_info(row)) == row
    for info in infos:
        again = view.row_info(view.row_of(info))
        assert (again.kind, again.file, again.hunk) == (info.kind, info.file, info.hunk)
        if info.kind == "row":
            assert info.left in (again.left, again.right)
    assert view.row_of_hunk(0, 1) == rows_of(view, "hunk")[1]
    assert view.row_of_hunk(3, 0) is None


def test_expanding_reveals_rows_and_the_last_step_merges_two_hunks(view: DiffView) -> None:
    rows, hunks = view.row_count, len(view.diff.files[0].hunks)
    view.expand(0, 1, 10)
    assert view.row_count == rows + 10
    view.expand(0, 1, 10, "bottom")
    assert view.row_count == rows + 20
    view.expand(0, 1, 1000)
    # 33 lines in all; the gap row and one hunk header are gone.
    assert view.row_count == rows + 33 - 2
    assert len(view.diff.files[0].hunks) == hunks - 1
    assert view.diff.files[0].apply(BEFORE) == AFTER


# ---------------------------------------------------------------------------
# real frames, no display
# ---------------------------------------------------------------------------

WINDOW = (40.0, 30.0)


class Seen:
    cursor: Any = None
    after: Any = None
    item_hovered: bool = False
    any_hovered: bool = False
    any_active: bool = False
    window_pos: tuple[float, float] = (0.0, 0.0)
    glyphs: int = 0
    scroll_y: float = 0.0
    host_clicked: bool = False
    cursor_kind: Any = None
    clipboard: str = ""


def frame(
    *views: Any,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    keys: Sequence[str] = (),
    release: Sequence[str] = (),
    wheel: tuple[float, float] | None = None,
    before: Callable[[Any, Seen], None] | None = None,
    after: Callable[[Any, Seen], None] | None = None,
    skip_draw: bool = False,
    width_px: float | None = None,
    name: str = "##advtext-diff-test",
) -> Seen:
    """One frame: a movable window, a scrolling child, each view drawn in turn."""
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1200.0, 800.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    for key in keys:
        io.add_key_event(getattr(imgui.Key, key), True)
    for key in release:
        io.add_key_event(getattr(imgui.Key, key), False)
    if wheel is not None:
        io.add_mouse_wheel_event(*wheel)
    seen = Seen()
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(*WINDOW), imgui.Cond_.first_use_ever.value)
        imgui.set_next_window_size(imgui.ImVec2(900.0, 500.0), imgui.Cond_.first_use_ever.value)
        imgui.begin(name)
        position = imgui.get_window_pos()
        seen.window_pos = (float(position.x), float(position.y))
        imgui.begin_child(name + "-child")
        if before is not None:
            before(imgui, seen)
        seen.cursor = imgui.get_cursor_screen_pos()
        seen.scroll_y = float(imgui.get_scroll_y())
        for view in () if skip_draw else views:
            if isinstance(view, DiffView):
                seen.glyphs += view.draw(fonts=lambda face: None, width_px=width_px).glyphs
            else:
                view.draw(fonts=lambda face: None)
        seen.item_hovered = bool(imgui.is_item_hovered())
        seen.cursor_kind = imgui.get_mouse_cursor()
        seen.any_hovered = bool(imgui.internal.get_hovered_id() != 0)
        seen.any_active = bool(imgui.is_any_item_active())
        seen.after = imgui.get_cursor_screen_pos()
        if after is not None:
            after(imgui, seen)
        imgui.end_child()
        imgui.end()
        try:
            seen.clipboard = imgui.get_clipboard_text() or ""
        except RuntimeError:
            # Nothing has been copied in this context yet: the binding cannot
            # build a string from the null ImGui hands back.
            seen.clipboard = ""
    finally:
        imgui.render()
    return seen


OFF = (1190.0, 790.0)


def settle(*views: Any, **kwargs: Any) -> None:
    """Two frames with the mouse parked off the window and every key up."""
    frame(*views, mouse=OFF, left=False, release=("mod_ctrl", "mod_shift", "c", "a"), **kwargs)
    frame(*views, mouse=OFF, **kwargs)


def at(view: DiffView, row: int, col: float, side: str = "code") -> tuple[float, float]:
    """A screen point over display row `row`, `col` cells into a pane's code."""
    assert view.origin is not None
    metrics = view.metrics_px
    region = view.frame_plan(view._width, row, row + 1).region(side)
    return (
        view.origin[0] + region.x + col * metrics.cell,
        view.origin[1] + row * metrics.row + metrics.row / 2,
    )


def drag(view: DiffView, start: tuple[float, float], end: tuple[float, float]) -> None:
    frame(view, mouse=start)
    frame(view, mouse=start, left=True)
    frame(view, mouse=end)
    frame(view, mouse=end, left=False)
    frame(view, mouse=OFF)


@pytest.fixture
def shown(view: DiffView) -> DiffView:
    settle(view)
    return view


def test_the_view_claims_its_height_and_culls_to_the_window(shown: DiffView) -> None:
    seen = frame(shown)
    assert seen.after.y - seen.cursor.y >= shown.content_height
    # Twenty-two rows fit this window; a longer diff is culled below, in
    # `test_switching_layout_keeps_the_row_at_the_top_of_the_window`.
    assert shown.visible_rows == range(0, shown.row_count)
    assert (
        seen.glyphs
        == shown.frame_plan(shown._width, shown.visible_rows.start, shown.visible_rows.stop).glyphs
    )


def test_over_the_text_there_is_no_item_while_nothing_is_dragged(shown: DiffView) -> None:
    seen = frame(shown, mouse=at(shown, 5, 3))
    seen = frame(shown, mouse=at(shown, 5, 3))
    assert seen.item_hovered and not seen.any_hovered and not seen.any_active


def test_a_press_and_drag_selects_and_does_not_move_the_hosts_window(shown: DiffView) -> None:
    row = find_row(shown, "line 19", RowKind.CONTEXT)
    start, end = at(shown, row, 5), at(shown, row + 3, 4)
    frame(shown, mouse=start)
    pressed = frame(shown, mouse=start, left=True)
    assert pressed.any_active and shown.owns_selection
    dragging = frame(shown, mouse=end)
    assert dragging.any_active and dragging.window_pos == pressed.window_pos == WINDOW
    done = frame(shown, mouse=end, left=False)
    idle = frame(shown, mouse=OFF)
    assert not idle.any_active and done.window_pos == WINDOW
    # From "19" on a context line, across two removed lines, to "line" on the
    # added one: the removed lines are left out.
    assert shown.selection == ((0, 0, 2, 5), (0, 0, 5, 4))
    assert shown.selected_text() == "19\nline"


def test_a_drag_backwards_selects_the_same_text(shown: DiffView) -> None:
    row = find_row(shown, "line 19", RowKind.CONTEXT)
    drag(shown, at(shown, row + 3, 4), at(shown, row, 5))
    assert shown.selected_text() == "19\nline"


def test_double_click_selects_a_word_and_triple_click_a_line(shown: DiffView) -> None:
    point = at(shown, find_row(shown, "line 20 changed", RowKind.ADD), 9.4)
    frame(shown, mouse=point)
    frame(shown, mouse=point, left=True)
    frame(shown, mouse=point, left=False)
    frame(shown, mouse=point, left=True)
    frame(shown, mouse=point, left=False)
    assert shown.selected_text() == "changed"
    frame(shown, mouse=point, left=True)
    frame(shown, mouse=point, left=False)
    assert shown.selected_text() == "line 20 changed"


def test_ctrl_c_copies_code_and_ctrl_a_selects_everything(shown: DiffView) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    imgui.set_clipboard_text("sentinel")
    row = find_row(shown, "line 21", RowKind.REMOVE)
    drag(shown, at(shown, row, 0), at(shown, row, 7))
    assert shown.selected_text() == "line 21"
    frame(shown, keys=("mod_ctrl", "c"))
    copied = frame(shown, release=("mod_ctrl", "c"))
    assert copied.clipboard == "line 21"
    frame(shown, keys=("mod_ctrl", "a"))
    frame(shown, release=("a",))
    frame(shown, keys=("c",))
    copied = frame(shown, release=("mod_ctrl", "c"))
    assert copied.clipboard == new_side_of(shown.diff)
    assert shown.owns_selection


def test_a_press_on_a_header_selects_from_the_next_line(shown: DiffView) -> None:
    header = rows_of(shown, "hunk")[0]
    drag(shown, at(shown, header, 3), at(shown, header + 1, 4))
    assert shown.selection == ((0, 0, 0, 0), (0, 0, 0, 4))
    assert shown.selected_text() == "line"


def test_side_by_side_a_drag_stays_on_the_side_it_began_on(shown: DiffView) -> None:
    shown.set_layout(SIDE)
    settle(shown)
    pair = find_row(shown, "line 20", RowKind.REMOVE)
    drag(shown, at(shown, pair, 0, "old"), at(shown, pair + 1, 60, "new"))
    assert shown.selection_side == 0
    assert shown.selected_text() == "line 20\nline 21"
    drag(shown, at(shown, pair, 0, "new"), at(shown, pair + 2, 4, "new"))
    assert shown.selection_side == 1
    # The row between is a blank cell on this side: it is not a line.
    assert shown.selected_text() == "line 20 changed\nline"


def test_one_selection_is_current_across_a_diff_view_and_a_document_view(
    shown: DiffView,
) -> None:
    """The same counter as `BareView`: a second one would let both answer Ctrl+C."""
    theme = Theme.build()
    document = BareView(
        document=build_document("Alpha bravo charlie delta.\n", theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    settle(document, shown)
    document.select(Selection(0, 5))
    assert document.owns_selection and not shown.owns_selection
    row = find_row(shown, "line 19", RowKind.CONTEXT)
    start, end = at(shown, row, 0), at(shown, row, 4)
    frame(document, shown, mouse=start)
    frame(document, shown, mouse=start, left=True)
    frame(document, shown, mouse=end)
    frame(document, shown, mouse=end, left=False)
    frame(document, shown, mouse=OFF)
    assert shown.owns_selection and not document.owns_selection
    assert shown.selected_text() == "line" and document.selected_text() == ""
    document.select_all()
    frame(document, shown)
    assert document.owns_selection and shown.selection is None
    frame(document, shown, keys=("mod_ctrl", "c"))
    copied = frame(document, shown, release=("mod_ctrl", "c"))
    assert copied.clipboard == "Alpha bravo charlie delta."


def test_an_item_the_host_drew_over_the_diff_keeps_its_click(shown: DiffView) -> None:
    point = at(shown, 6, 4)

    def overlay(imgui: Any, seen: Seen) -> None:
        imgui.set_cursor_screen_pos(imgui.ImVec2(point[0] - 20.0, point[1] - 8.0))
        seen.host_clicked = bool(imgui.button("host", imgui.ImVec2(60.0, 20.0)))

    frame(shown, mouse=point, after=overlay)
    frame(shown, mouse=point, after=overlay)
    frame(shown, mouse=point, left=True, after=overlay)
    released = frame(shown, mouse=point, left=False, after=overlay)
    assert released.host_clicked
    assert shown.selection is None and not shown.owns_selection


def test_a_view_that_was_not_drawn_for_a_frame_has_stopped_dragging(shown: DiffView) -> None:
    row = find_row(shown, "line 19", RowKind.CONTEXT)
    start = at(shown, row, 0)
    frame(shown, mouse=start)
    frame(shown, mouse=start, left=True)
    frame(shown, mouse=at(shown, row, 4))
    kept = shown.selection
    frame(shown, skip_draw=True)
    frame(shown, mouse=at(shown, row + 3, 6))
    assert shown.selection == kept and not shown._dragging
    frame(shown, left=False)


def test_switching_layout_keeps_the_row_at_the_top_of_the_window(bundled_fonts: Any) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    before = numbered(400)
    after = "".join(f"line {i} edited\n" if i % 9 == 4 else f"line {i}\n" for i in range(1, 401))
    view = DiffView(Diff.from_texts(before, after, "long.py", context=10**9), Theme.build())
    name = "##advtext-diff-layout"
    settle(view, name=name)
    target = find_row(view, "line 203", RowKind.CONTEXT)
    view.scroll_to_row(target)
    frame(view, name=name)
    frame(view, name=name)
    assert view._top_row == target
    assert view.visible_rows.start == target and len(view.visible_rows) < 40 < view.row_count
    for layout in (SIDE, UNIFIED, SIDE):
        view.set_layout(layout)
        frame(view, name=name)
        frame(view, name=name)
        info = view.row_info(view._top_row)
        hunk = view.diff.files[info.file].hunks[info.hunk or 0]
        shown_text = {hunk.rows[i].text for i in (info.left, info.right) if i is not None}
        assert shown_text == {"line 203"}, layout
    assert imgui.get_current_context() is not None


def test_next_hunk_scrolls_the_window_to_it(bundled_fonts: Any) -> None:
    before = numbered(600)
    after = "".join(f"line {i} edited\n" if i % 50 == 25 else f"line {i}\n" for i in range(1, 601))
    view = DiffView(Diff.from_texts(before, after, "far.py"), Theme.build())
    name = "##advtext-diff-hunks"
    settle(view, name=name)
    assert len(view.diff.files[0].hunks) == 12
    assert view.row_of_hunk(0, 7) not in view.visible_rows
    for _ in range(8):
        view.next_hunk()
    assert view.current_hunk == (0, 7)
    frame(view, name=name)
    moved = frame(view, name=name)
    assert moved.scroll_y > 0 and view._top_row == view.row_of_hunk(0, 7)
    view.previous_hunk()
    view.previous_hunk()
    frame(view, name=name)
    frame(view, name=name)
    assert view._top_row == view.row_of_hunk(0, 5)


def test_a_click_on_a_collapsed_context_row_expands_it(shown: DiffView) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    gap = rows_of(shown, "gap")[1]
    rows = shown.row_count
    point = at(shown, gap, 6)
    hovering = frame(shown, mouse=point)
    hovering = frame(shown, mouse=point)
    assert hovering.cursor_kind == imgui.MouseCursor_.hand
    frame(shown, mouse=point, left=True)
    frame(shown, mouse=point, left=False)
    assert shown.row_count == rows + shown.expand_step
    assert shown.selection is None  # the click was the row's, not a selection
    # The first lines of the gap, under the hunk above.
    assert shown.diff.files[0].hunks[0].rows[-1].text == "line 44"
    # The row is below the window now: bring it back, then Shift+click it.
    shown.scroll_to_row(rows_of(shown, "gap")[1] - 3)
    settle(shown)
    frame(shown, mouse=at(shown, rows_of(shown, "gap")[1], 6), keys=("mod_shift",))
    frame(shown, left=True)
    frame(shown, left=False, release=("mod_shift",))
    # Thirteen were left; with Shift they come from the bottom, and the hunks merge.
    assert len(shown.diff.files[0].hunks) == 1
    assert shown.diff.files[0].apply(BEFORE) == AFTER


def test_shift_wheel_and_the_scrollbar_scroll_the_code_sideways(wide: DiffView) -> None:
    settle(wide)
    cell = wide.metrics_px.cell
    assert wide._max_scroll_x > 0
    row = find_row(wide, LONG, RowKind.ADD)
    over = at(wide, row, 10)
    frame(wide, mouse=over)
    frame(wide, mouse=over, keys=("mod_shift",), wheel=(0.0, -3.0))
    frame(wide, release=("mod_shift",))
    assert wide.scroll_x == 12 * cell
    frame(wide, wheel=(-2.0, 0.0))  # a horizontal wheel needs no Shift
    frame(wide)
    assert wide.scroll_x == 20 * cell
    frame(wide, wheel=(0.0, -3.0))  # a plain wheel is the window's
    frame(wide)
    assert wide.scroll_x == 20 * cell

    # The scrollbar is along the bottom of the view; a press on it is the
    # scrollbar's and begins no selection.
    wide.scroll_x = 0
    settle(wide)
    assert wide.origin is not None
    height = wide.height_for(wide._width)
    assert height == wide.content_height + wide._bar_height()
    grab = (wide.origin[0] + wide._panes(wide._width)[0].code + 4.0, wide.origin[1] + height - 3.0)
    frame(wide, mouse=grab)
    frame(wide, mouse=grab)
    pressed = frame(wide, mouse=grab, left=True)
    assert pressed.any_active and wide.selection is None
    frame(wide, mouse=(grab[0] + 200.0, grab[1]))
    frame(wide, mouse=(grab[0] + 200.0, grab[1]), left=False)
    assert 0 < wide.scroll_x <= wide._max_scroll_x and wide.selection is None
    # A press on the track, away from the thumb, brings the thumb to the mouse.
    end = (wide.origin[0] + wide._width - 2.0, grab[1])
    frame(wide, mouse=end)
    frame(wide, mouse=end)
    frame(wide, mouse=end, left=True)
    frame(wide, left=False)
    assert wide.scroll_x == wide._max_scroll_x and wide.selection is None


def test_dragging_a_selection_past_the_edge_scrolls_the_code(wide: DiffView) -> None:
    settle(wide)
    row = find_row(wide, LONG, RowKind.ADD)
    start = at(wide, row, 2)
    assert wide.origin is not None
    frame(wide, mouse=start)
    frame(wide, mouse=start, left=True)
    beyond = (wide.origin[0] + wide._width + 30.0, start[1])
    for _ in range(5):
        frame(wide, mouse=beyond)
    frame(wide, left=False)  # still a frame of the drag: six in all, two cells each
    assert wide.scroll_x == 12 * wide.metrics_px.cell
    assert wide.selected_text().startswith("= [0, 1, 2") and len(wide.selected_text()) > 60


def test_with_a_height_cap_the_view_scrolls_inside_a_child_of_that_height(
    bundled_fonts: Any,
) -> None:
    view = DiffView(Diff.from_texts(BEFORE, AFTER, "notes.py"), Theme.build(), height_cap=120.0)
    name = "##advtext-diff-capped"
    assert view.height_for(600.0) == 120.0 < view.content_height
    settle(view, name=name)
    seen = frame(view, name=name)
    assert seen.after.y - seen.cursor.y < 130.0  # the cap and ImGui's item spacing
    assert len(view.visible_rows) <= 120 // view.metrics_px.row + 2
    short = DiffView(Diff.from_texts("a\n", "b\n", "s.py"), Theme.build(), height_cap=400.0)
    assert short.height_for(600.0) == short.content_height == 4 * short.metrics_px.row
    # Scrolling to a hunk scrolls the child, not the host's window.
    view.next_hunk()
    view.next_hunk()
    frame(view, name=name)
    moved = frame(view, name=name)
    assert moved.scroll_y == 0.0
    assert view.row_of_hunk(0, 1) in view.visible_rows
    # ... and a drag inside it selects as anywhere else.
    row = view.visible_rows.start + 2
    start, end = at(view, row, 0), at(view, row, 4)
    frame(view, mouse=start, name=name)
    frame(view, mouse=start, left=True, name=name)
    frame(view, mouse=end, name=name)
    frame(view, mouse=end, left=False, name=name)
    assert len(view.selected_text()) == 4


def test_an_unchanged_frame_reuses_its_plan_and_a_changed_one_does_not(shown: DiffView) -> None:
    built = shown.plans_built
    frame(shown)
    frame(shown)
    assert shown.plans_built == built
    shown.select_all()
    frame(shown)
    assert shown.plans_built == built + 1
    shown.next_hunk()
    frame(shown)
    assert shown.plans_built == built + 2


def test_an_empty_diff_draws_nothing_and_takes_no_click(bundled_fonts: Any) -> None:
    view = DiffView(Diff(), Theme.build())
    settle(view)
    seen = frame(view, mouse=(200.0, 200.0), left=True)
    frame(view, left=False)
    assert seen.glyphs == 0 and view.selection is None and view.content_height == 0.0
    assert isinstance(view.frame_plan(WIDTH), FramePlan)


# ---------------------------------------------------------------------------
# a real window
# ---------------------------------------------------------------------------

REAL = r"""
from imgui_bundle import hello_imgui, imgui, immapp

from advtext.backends.imgui_draw import DARK_PALETTE
from advtext.diff import Diff
from advtext.style import Theme
from advtext.ui.diff_view import DiffLayout, DiffView
from advtext.ui.fonts import load_faces

before = "".join(f"value_{i} = {i}\n" for i in range(1, 301))
after = before.replace("value_40 = 40\n", "value_40 = forty()\n").replace("value_41 = 41\n", "")
after = after.replace("value_200 = 200\n", "value_200 = 200\n\tadded = True\n")
view = DiffView(Diff.from_texts(before, after, "values.py"), Theme.build())
loaded = []
state = {"frame": 0}
seen = {}


def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    loaded.append(load_faces())


def gui():
    viewport = imgui.get_main_viewport()
    imgui.set_next_window_pos(viewport.work_pos)
    imgui.set_next_window_size(viewport.work_size)
    imgui.begin("diff", None, imgui.WindowFlags_.no_decoration.value)
    layout = DiffLayout.UNIFIED if state["frame"] < 6 else DiffLayout.SIDE_BY_SIDE
    if state["frame"] == 3:
        view.select_all()
        view.next_hunk()
    view.set_layout(layout)
    start = imgui.get_window_draw_list().vtx_buffer.size()
    stats = view.draw(fonts=loaded[-1], palette=DARK_PALETTE)
    vertices = imgui.get_window_draw_list().vtx_buffer.size() - start
    seen[layout.value] = (stats.glyphs, stats.missing, len(view.visible_rows), vertices)
    imgui.end()
    state["frame"] += 1
    if state["frame"] >= 12:
        hello_imgui.get_runner_params().app_shall_exit = True


params = hello_imgui.RunnerParams()
params.app_window_params.window_geometry.size = (1100, 700)
params.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
params.ini_disable = True
params.callbacks.load_additional_fonts = load_fonts
params.callbacks.show_gui = gui
immapp.run(params)
for name, (glyphs, missing, rows, vertices) in seen.items():
    print(f"layout={name} glyphs={glyphs} missing={missing} rows={rows} vertices={vertices}")
print(f"frames={state['frame']} cell={view.metrics_px.cell} row={view.metrics_px.row}")
"""


def test_both_layouts_draw_in_a_real_window(window: Window) -> None:
    """
    `DiffView.draw` in a GLFW window with a GL context and the bundled faces
    on the atlas: twelve frames, six in each layout, a selection and a current
    hunk set on the way. Asserted: it exits cleanly, both layouts issued
    glyphs, none was missing from the code face, and each glyph became a quad.
    Counts only; nobody looked at it.
    """
    script = window.out / "diff_view_real.py"
    script.write_text(textwrap.dedent(REAL), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("layout=")]
    found = {
        parts["layout"]: {key: int(value) for key, value in parts.items() if key != "layout"}
        for parts in (dict(part.split("=") for part in line.split()) for line in lines)
    }
    assert set(found) == {"unified", "side-by-side"}, done.stdout
    for name, counts in found.items():
        assert counts["glyphs"] > 300 and counts["missing"] == 0, (name, counts)
        assert counts["rows"] >= 15, (name, counts)
        assert counts["vertices"] >= 4 * counts["glyphs"], (name, counts)
    assert "frames=12" in done.stdout


# ---------------------------------------------------------------------------
# review 1 (.concerns/lead--demo-review1-findings.md), item by item
# ---------------------------------------------------------------------------


def test_item_1_a_control_character_is_drawn_as_a_placeholder_and_copied_as_itself(
    bundled_fonts: Any,
) -> None:
    diff = Diff.from_texts("x = 1\n", "import os\n\0ab\x1bc\n", "run.py")
    view = DiffView(diff, Theme.build())
    plan = view.frame_plan(2000.0)
    (header,) = [plan.region("frame").text_at(baseline(view, row)) for row in rows_of(view, "file")]
    assert header == "run.py+2-1!containscontrolcharacters"
    code = plan.region("code")
    row = find_row(view, "\0ab\x1bc", RowKind.ADD)
    glyphs = glyphs_on(view, code, row)
    assert [chr(g.codepoint) for g in glyphs] == [
        CONTROL_PLACEHOLDER,
        "a",
        "b",
        CONTROL_PLACEHOLDER,
        "c",
    ]
    assert [column(view, g) for g in glyphs] == [0, 1, 2, 3, 4]  # one cell each
    warning, add = DEFAULT_PALETTE.diff.warning, DEFAULT_PALETTE.diff.add
    assert [ink_of(code, g) for g in glyphs] == [warning, add, add, warning, add]
    view.select_all()
    assert view.selected_text() == "import os\n\0ab\x1bc"
    # A file with none says nothing.
    plain = DiffView(Diff.from_texts("a\n", "b\n", "f"), Theme.build())
    assert "control" not in plain._file_header(plain.diff.files[0])[1]


def test_item_12_drawing_and_hit_testing_share_one_column_arithmetic(bundled_fonts: Any) -> None:
    """
    A lone carriage return before a tab. `str.expandtabs` restarts its column
    count at a CR, so the glyphs were issued on one set of columns and a click
    was resolved on another (7 against 5 for this line).
    """
    text = "a\r\tb"
    assert len(text.expandtabs(4)) == 7  # why `expandtabs` is not used
    view = DiffView(Diff.from_texts("x\n", text + "\n", "f"), Theme.build())
    row = find_row(view, text, RowKind.ADD)
    glyphs = glyphs_on(view, view.frame_plan(2000.0).region("code"), row)
    assert [(chr(g.codepoint), column(view, g)) for g in glyphs] == [
        ("a", 0),
        (CONTROL_PLACEHOLDER, 1),
        ("b", 4),
    ]
    assert view._hunks[(0, 0)].columns == 5
    assert [view._position(row, c, None)[3] for c in range(7)] == [0, 1, 2, 2, 3, 4, 4]  # type: ignore[index]
    # A selection of "b" is highlighted where "b" is drawn.
    view.select((0, 0, 1, 3), (0, 0, 1, 4))
    (mark,) = view.frame_plan(2000.0).region("code").highlights
    cell = view.metrics_px.cell
    assert (round(px_from_sp(mark.x) / cell), round(px_from_sp(mark.width) / cell)) == (4, 1)


def header_of(view: DiffView, file: int = 0, width: float = 2000.0) -> str:
    row = [r for r in rows_of(view, "file") if view.row_info(r).file == file][0]
    return view.frame_plan(width).region("frame").text_at(baseline(view, row))


def test_item_4_a_line_ending_change_is_said_in_the_header_and_folded_behind_it(
    bundled_fonts: Any,
) -> None:
    diff = Diff.from_texts("a\r\nb\r\n", "a\nb\n", "f.txt")
    view = DiffView(diff, Theme.build())
    assert header_of(view) == "f.txt+2-2(lineendingsonly:CRLF->LF)"
    assert [view.row_info(row).kind for row in range(view.row_count)] == ["file", "fold"]
    frame_region = view.frame_plan(2000.0).region("frame")
    assert frame_region.text_at(baseline(view, 1)) == (
        "...4rowsdifferonlyinhowthelineends(clicktoshowthem)"
    )
    assert not view.line_endings_shown(0) and view.next_hunk() is None
    view.show_line_endings(0)
    assert view.line_endings_shown(0)
    assert [view.row_info(row).kind for row in range(view.row_count)] == [
        "file",
        "hunk",
        "row",
        "row",
        "row",
        "row",
    ]
    # Each row now ends in a mark for its terminator, in the meta ink, one cell clear.
    code = view.frame_plan(2000.0).region("code")
    meta = DEFAULT_PALETTE.diff.meta
    shown = []
    for row in rows_of(view):
        glyphs = glyphs_on(view, code, row)
        mark = [g for g in glyphs if ink_of(code, g) == meta]
        shown.append(("".join(chr(g.codepoint) for g in mark), column(view, mark[0])))
    assert shown == [("\\r\\n", 2), ("\\r\\n", 2), ("\\n", 2), ("\\n", 2)]
    # The marks are not text: a copy is the lines, joined with a newline.
    view.select_all()
    assert view.selected_text() == "a\nb"
    # Room for the mark is part of the width a line needs.
    assert view._hunks[(0, 0)].columns == 1 + 5
    view.show_line_endings(0, False)
    assert view.row_count == 2 and view.selection is None


def test_item_4_an_ending_only_pair_among_real_changes_is_marked_in_place(
    bundled_fonts: Any,
) -> None:
    view = DiffView(Diff.from_texts("a\r\nb\r\nc\n", "a\nB\r\nc\n", "f"), Theme.build())
    assert "lineendings" not in header_of(view)
    code = view.frame_plan(2000.0).region("code")
    meta = DEFAULT_PALETTE.diff.meta
    marks = {}
    for row in rows_of(view):
        info = view.row_info(row)
        line = view.diff.files[0].hunks[0].rows[info.left or 0]
        marks[(line.kind.value, line.text)] = "".join(
            chr(g.codepoint) for g in glyphs_on(view, code, row) if ink_of(code, g) == meta
        )
    assert marks == {
        ("-", "a"): "\\r\\n",
        ("-", "b"): "",
        ("+", "a"): "\\n",
        ("+", "B"): "",
        (" ", "c"): "",
    }
    side = DiffView(view.diff, Theme.build(), layout=SIDE)
    plan = side.frame_plan(2000.0)
    old, new = plan.region("old"), plan.region("new")
    row = find_row(side, "a", RowKind.REMOVE)
    assert "".join(chr(g.codepoint) for g in glyphs_on(side, old, row)) == "a\\r\\n"
    assert "".join(chr(g.codepoint) for g in glyphs_on(side, new, row)) == "a\\n"


def test_item_4_a_click_on_the_folded_row_shows_the_rows(bundled_fonts: Any) -> None:
    view = DiffView(Diff.from_texts("a\r\nb\r\n", "a\nb\n", "f.txt"), Theme.build())
    settle(view)
    point = at(view, 1, 6)
    frame(view, mouse=point)
    frame(view, mouse=point, left=True)
    frame(view, mouse=point, left=False)
    assert view.line_endings_shown(0) and view.row_count == 6
    assert view.selection is None


def test_item_5_a_copy_never_joins_pieces_that_are_not_next_to_each_other(view: DiffView) -> None:
    view.select_all()
    copied = view.selected_text()
    first, second = view.diff.files[0].hunks
    above, below = first.rows[-1].text, second.rows[0].text
    assert (above, below) == ("line 24", "line 58")  # thirty-three lines apart in the file
    assert f"{above}\n{below}" not in copied  # what review 1 found on the clipboard
    assert copied.count(COPY_GAP) == 1 and f"{above}\n{COPY_GAP}\n{below}" in copied
    pieces = copied.split("\n" + COPY_GAP + "\n")
    assert all((piece + "\n") in AFTER for piece in pieces) and len(pieces) == 2
    # Fully expanded, the hunks are one and the copy is the file.
    view.expand(0, 1, 10**6)
    view.expand(0, 0, 10**6)
    view.expand(0, 1, 10**6)
    view.select_all()
    assert view.selected_text() + "\n" == AFTER
    # Within one hunk nothing is added.
    view.select((0, 0, 0, 0), (0, 0, 2, 4))
    assert COPY_GAP not in view.selected_text()


def test_item_5_side_by_side_and_across_files(bundled_fonts: Any) -> None:
    files = (
        Diff.from_texts(BEFORE, AFTER, "notes.py").files
        + Diff.from_texts("x\n", "y\n", "other.py").files
    )
    view = DiffView(Diff(files), Theme.build(), layout=SIDE)
    view.select_all(0)
    old = view.selected_text().split("\n")
    assert old[old.index("line 24") + 1 : old.index("line 24") + 3] == [COPY_GAP, "line 58"]
    assert old[-3:] == [COPY_GAP, "other.py", "x"]
    view.select_all(1)
    assert view.selected_text().split("\n")[-3:] == [COPY_GAP, "other.py", "y"]
    assert "other.py" not in BEFORE + AFTER  # so the docstring has to say it is added
    said = DiffView.selected_text.__doc__ or ""
    assert "COPY_GAP" in said and "U+2026" in said and "label" in said


def test_item_6_whether_removed_lines_copy_does_not_depend_on_a_blank_line_above(
    bundled_fonts: Any,
) -> None:
    for blank in ("", "x"):
        diff = Diff.from_texts(f"a\n{blank}\nold1\nold2\nz\n", f"a\n{blank}\nz\n", "f")
        view = DiffView(diff, Theme.build())
        assert [r.kind.value for _, _, r in diff.rows()] == [" ", " ", "-", "-", " "]
        # From the end of the context line above to the end of the removed lines.
        view.select((0, 0, 1, len(blank)), (0, 0, 3, 4))
        assert view.selected_text() == "old1\nold2", repr(blank)
        marks = view.frame_plan(WIDTH).region("code").highlights
        rows = sorted(round(px_from_sp(r.y) / view.metrics_px.row) for r in marks)
        assert rows == [
            find_row(view, "old1", RowKind.REMOVE),
            find_row(view, "old2", RowKind.REMOVE),
        ]
    # A blank line strictly inside the selection is a selected line.
    view = DiffView(Diff.from_texts("a\n\nold\nz\n", "a\n\nz\n", "f"), Theme.build())
    view.select((0, 0, 0, 0), (0, 0, 2, 3))
    assert view.selected_text() == "a\n"


def test_item_6_ctrl_c_with_nothing_to_copy_leaves_the_clipboard_alone(shown: DiffView) -> None:
    imgui = pytest.importorskip("imgui_bundle").imgui
    imgui.set_clipboard_text("sentinel")
    shown.copy_as = lambda view: ""
    row = find_row(shown, "line 21", RowKind.REMOVE)
    drag(shown, at(shown, row, 0), at(shown, row, 7))
    assert shown.selection is not None
    frame(shown, keys=("mod_ctrl", "c"))
    assert frame(shown, release=("mod_ctrl", "c")).clipboard == "sentinel"
    shown.copy()
    assert frame(shown).clipboard == "sentinel"
    shown.copy_as = None
    shown.copy()
    assert frame(shown).clipboard == "line 21"


def test_item_7_a_stream_ending_mid_line_measures_the_line_and_not_the_hunk(
    bundled_fonts: Any,
) -> None:
    stream = UnifiedDiffStream()
    stream.feed("@@ -1,400 +1,400 @@\n" + "".join(f"+line {i}\n" for i in range(300)))
    view = DiffView(stream.diff, Theme.build())
    assert view.row_count == 302 and view.measured_rows == 300
    measured = []
    for character in "+abcd\n-x\n--- y\n+++ z\n q\n+a much longer line than any before it":
        stream.feed(character)
        view.set_diff(stream.diff)
        before = view.measured_rows
        rows = view.row_count
        measured.append(view.measured_rows - before)
        hunk = stream.diff.files[0].hunks[0]
        info = view._hunks[(0, 0)]
        assert rows == 2 + len(hunk.rows)
        assert info.columns == max(len(r.text) for r in hunk.rows)
        assert len(info.place) == len(hunk.rows)
        assert [hunk.rows[i].text for i in info.new] == [
            r.text for r in hunk.rows if r.kind is not RowKind.REMOVE
        ]
    assert max(measured) <= 3, measured  # was 301 for each of these characters
    assert sum(measured) < 150


COMBINED_TEXT = (
    "diff --cc f.py\nindex 1,2..3\n--- a/f.py\n+++ b/f.py\n@@@ -1,2 -1,2 +1,3 @@@\n"
    "  keep\n- ours\n -theirs\n++merged\n +from-theirs\n"
)


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_items_9_and_10_a_file_that_is_not_read_as_rows_is_drawn_as_written(
    bundled_fonts: Any, layout: DiffLayout
) -> None:
    text = COMBINED_TEXT + "diff --git a/g b/g\n--- a/g\n+++ b/g\n@@ -1 +1 @@\n-x\n+y\n"
    view = DiffView(Diff.from_unified(text), Theme.build(), layout=layout)
    kinds = [view.row_info(row).kind for row in range(view.row_count)]
    assert kinds[:11] == ["file"] + ["raw"] * 10 and kinds[11:13] == ["file", "hunk"]
    assert header_of(view) == "f.py(combineddiff:shownaswritten)"
    plan = view.frame_plan(2000.0)
    raw = plan.region("raw")
    lines = [raw.text_at(baseline(view, row)) for row in rows_of(view, "raw")]
    assert lines == ["".join(line.split()) for line in COMBINED_TEXT.splitlines()]
    # Its `+` and `-` are characters of the line: no band, no gutter marker, no count.
    frame_region = plan.region("frame")
    for row in rows_of(view, "raw"):
        assert frame_region.text_at(baseline(view, row)) == ""
        top = sp_from_px(float(row * view.metrics_px.row))
        assert not [rect for rect, _ in frame_region.fills if rect.y == top]
    assert (view.diff.added, view.diff.removed) == (1, 1)
    # It scrolls with the code and is as wide as its longest line.
    assert view._indexed().columns >= len("@@@ -1,2 -1,2 +1,3 @@@")
    # Raw lines are not selectable; a selection of everything is the rows of the real file.
    view.select_all(1)
    assert view.selected_text() == "y"
    assert view.row_of(view.row_info(4)) == 4
    # Text that is no diff at all.
    plain = DiffView(Diff.from_unified("hello there\nworld\n"), Theme.build(), layout=layout)
    assert header_of(plain) == "(notadiff:shownaswritten)"
    assert plain.frame_plan(2000.0).region("raw").text_at(baseline(plain, 1)) == "hellothere"
    assert plain.row_count == 3 and plain.next_hunk() is None


def test_a_raw_file_that_grows_measures_its_new_lines(bundled_fonts: Any) -> None:
    stream = UnifiedDiffStream()
    stream.feed("some prose\n" * 200)
    view = DiffView(stream.diff, Theme.build())
    assert view.row_count == 201
    before = view.measured_rows
    stream.feed("one more line\n")
    view.set_diff(stream.diff)
    assert view.row_count == 202 and view.measured_rows == before + 1


def test_item_11_the_current_hunk_is_still_the_same_hunk_after_an_expand_merges_two(
    bundled_fonts: Any,
) -> None:
    before = numbered(100)
    after = (
        before.replace("line 10\n", "L10\n")
        .replace("line 40\n", "L40\n")
        .replace("line 80\n", "L80\n")
    )
    view = DiffView(Diff.from_texts(before, after, "f"), Theme.build())
    view.next_hunk()
    assert view.next_hunk() == (0, 1)
    assert "line 40" in [r.text for r in view.diff.files[0].hunks[1].rows]
    view.expand(0, 1, 10**6)  # the gap above it: hunks 0 and 1 become hunk 0
    assert view.current_hunk == (0, 0)
    assert "line 40" in [r.text for r in view.diff.files[0].hunks[0].rows]
    assert view.next_hunk() == (0, 1)
    assert "line 80" in [r.text for r in view.diff.files[0].hunks[1].rows]
    # Expanding below the current hunk leaves it where it is; revealing lines
    # above it (its first row changes) does too.
    view.expand(0, 2, 5)
    assert view.current_hunk == (0, 1)
    view.expand(0, 1, 5, "bottom")
    assert view.current_hunk == (0, 1)
    assert "line 80" in [r.text for r in view.diff.files[0].hunks[1].rows]


def test_item_14_a_different_highlighter_gives_its_own_colours(view: DiffView) -> None:
    def red(lines: Sequence[str], language: str) -> list[list[tuple[int, int, int]]]:
        return [[(0, 1, 0xFF0000FF)] for _ in lines]

    def green(lines: Sequence[str], language: str) -> list[list[tuple[int, int, int]]]:
        return [[(0, 1, 0xFF00FF00)] for _ in lines]

    def first_inks(target: DiffView) -> set[int]:
        code = target.frame_plan(WIDTH).region("code")
        return {ink_of(code, glyphs_on(target, code, row)[0]) for row in rows_of(target)[:6]}

    view.next_hunk()
    view.select((0, 0, 0, 0), (0, 0, 1, 3))
    view.syntax = red
    assert first_inks(view) == {0xFF0000FF}
    calls = view.syntax_calls
    view.syntax = green
    assert first_inks(view) == {0xFF00FF00}  # was still red: the cache did not know who filled it
    assert view.syntax_calls > calls
    calls = view.syntax_calls
    assert first_inks(view) == {0xFF00FF00} and view.syntax_calls == calls
    view.syntax = None
    assert not first_inks(view) & {0xFF0000FF, 0xFF00FF00}
    # Nothing else about the view was disturbed by the swap.
    assert view.current_hunk == (0, 0) and view.selection == ((0, 0, 0, 0), (0, 0, 1, 3))


def test_item_15_the_top_row_is_readable_and_settable_and_ties_two_views(
    bundled_fonts: Any,
) -> None:
    diff = Diff.from_texts(BEFORE, AFTER, "notes.py").expand(0, 1, None)
    unified = DiffView(diff, Theme.build())
    side = DiffView(diff, Theme.build(), layout=SIDE)
    assert unified.top_row == 0
    settle(unified, name="##advtext-diff-top-a")
    settle(side, name="##advtext-diff-top-b")
    target = find_row(unified, "line 40", RowKind.CONTEXT)
    unified.top_row = target
    settle(unified, name="##advtext-diff-top-a")
    assert unified.top_row == target
    # The follower is put on the row that shows the same line, whatever its layout.
    side.top_row = side.row_of(unified.row_info(unified.top_row))
    settle(side, name="##advtext-diff-top-b")
    assert side.top_row == find_row(side, "line 40", RowKind.CONTEXT)
    assert side.top_row != unified.top_row  # the layouts number their rows differently
    info = side.row_info(side.top_row)
    assert side.diff.files[0].hunks[info.hunk or 0].rows[info.left or 0].text == "line 40"


def test_next_hunk_with_none_current_starts_from_what_is_on_screen(bundled_fonts: Any) -> None:
    before = numbered(400)
    after = before
    for number in (10, 150, 300):
        after = after.replace(f"line {number}\n", f"L{number}\n")
    view = DiffView(Diff.from_texts(before, after, "f").expand(0, 1, None), Theme.build())
    assert len(view.diff.files[0].hunks) == 2
    fresh = DiffView(view.diff, Theme.build())
    assert fresh.next_hunk() == (0, 0)  # never drawn: the first, as before
    assert DiffView(view.diff, Theme.build()).previous_hunk() == (0, 1)
    settle(view, name="##advtext-diff-next")
    second = view.row_of_hunk(0, 1)
    assert second is not None and second > 100
    view.top_row = second - 1  # the collapsed-context row above the second hunk
    settle(view, name="##advtext-diff-next")
    # (As far down as the window scrolls: below the first hunk's header, above the second's.)
    assert 100 < view.top_row < second and view.current_hunk is None
    assert view.next_hunk() == (0, 1)  # the first hunk at or below the top of the window
    view._current = None
    assert view.previous_hunk() == (0, 0)  # the last one above it


def test_a_press_on_the_gutter_while_scrolled_sideways_is_a_press_at_column_0(
    wide: DiffView,
) -> None:
    settle(wide, width_px=400.0)
    wide.scroll_x = 40 * wide.metrics_px.cell
    settle(wide, width_px=400.0)
    assert wide.scroll_x > 0
    row = rows_of(wide)[0]
    assert wide.origin is not None
    gutter = (wide.origin[0] + wide.metrics_px.cell * 1.5, at(wide, row, 0)[1])
    frame(wide, mouse=gutter, width_px=400.0)
    frame(wide, mouse=gutter, left=True, width_px=400.0)
    frame(wide, mouse=gutter, left=False, width_px=400.0)
    assert wide.selection is not None
    assert wide.selection[0][3] == 0  # not a character hidden behind the gutter
    frame(wide, mouse=OFF, width_px=400.0)


def test_a_rename_or_a_mode_change_with_no_rows_still_says_what_happened(
    bundled_fonts: Any,
) -> None:
    text = (
        "diff --git a/old.py b/new.py\nsimilarity index 100%\n"
        "rename from old.py\nrename to new.py\n"
        "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
    )
    view = DiffView(Diff.from_unified(text), Theme.build())
    assert [header_of(view, f) for f in (0, 1)] == [
        "new.py+0-0(renamedfromold.py)",
        "run.sh+0-0(mode100644->100755)",
    ]


# ---------------------------------------------------------------------------
# review 3 (.concerns/lead--demo-review3-findings.md), item by item
# ---------------------------------------------------------------------------

ZWSP, RLO, PI, TAU = chr(0x200B), chr(0x202E), chr(0x3C0), chr(0x3C4)
CJK = chr(0x6CE8) + chr(0x91CA)


def test_review3_item_1_no_glyph_is_issued_in_a_face_that_lacks_it(bundled_fonts: Any) -> None:
    """
    The reviewer's snippet, per glyph and in every region. `\u03c0` and `\u03c4` are not
    in the code face and were issued in it (a blank cell each); the CJK pair
    is in no bundled face; the zero-width space and the right-to-left override
    were issued as themselves, which draws nothing and reorders the line.
    """
    before = f"area = {PI} * r\nuser = admin\n# note\n"
    after = f"area = {TAU} * r\nuser = ad{ZWSP}min{RLO}\n# {CJK}\n"
    diff = Diff.from_texts(before, after, "geom.py")
    theme = Theme.build()
    view = DiffView(diff, theme)
    code_face = view.metrics_px.font
    assert not fontlib_metrics(code_face.key).has(ord(PI))  # the premise
    for layout in (UNIFIED, SIDE):
        view.set_layout(layout)
        plan = view.frame_plan(1400.0)
        glyphs = [c for r in plan.regions for c in r.cmds if isinstance(c, Glyph)]
        assert [g for g in glyphs if not fontlib_metrics(g.font).has(g.codepoint)] == []
        # Neither invisible character is ever issued, in any face.
        assert not {chr(g.codepoint) for g in glyphs} & {ZWSP, RLO}
    view.set_layout(UNIFIED)
    code = view.frame_plan(1400.0).region("code")
    warning, add, remove = (
        DEFAULT_PALETTE.diff.warning,
        DEFAULT_PALETTE.diff.add,
        DEFAULT_PALETTE.diff.remove,
    )
    # A character another face has: itself, from that face, in its own cell.
    row = find_row(view, f"area = {PI} * r", RowKind.REMOVE)
    glyphs = glyphs_on(view, code, row)
    assert [chr(g.codepoint) for g in glyphs] == ["a", "r", "e", "a", "=", PI, "*", "r"]
    assert [column(view, g) for g in glyphs] == [0, 1, 2, 3, 5, 7, 9, 11]
    borrowed = glyphs[5]
    assert borrowed.font != code_face.key and fontlib_metrics(borrowed.font).has(ord(PI))
    assert borrowed.font.endswith(code_face.key.split("@")[1])  # the code face's size
    assert {g.font for g in glyphs if g is not borrowed} == {code_face.key}
    assert ink_of(code, borrowed) == remove
    # Invisible and bidirectional controls: a placeholder each, in the warning ink.
    row = find_row(view, f"user = ad{ZWSP}min{RLO}", RowKind.ADD)
    glyphs = glyphs_on(view, code, row)
    shown = [(chr(g.codepoint), column(view, g)) for g in glyphs]
    assert shown[-5:] == [
        (CONTROL_PLACEHOLDER, 9),
        ("m", 10),
        ("i", 11),
        ("n", 12),
        (CONTROL_PLACEHOLDER, 13),
    ]
    assert [ink_of(code, g) for g in glyphs[-5:]] == [warning, add, add, add, warning]
    # A character no face has: a placeholder too, so it is seen to be there.
    row = find_row(view, f"# {CJK}", RowKind.ADD)
    glyphs = glyphs_on(view, code, row)
    assert [(chr(g.codepoint), column(view, g)) for g in glyphs] == [
        ("#", 0),
        (CONTROL_PLACEHOLDER, 2),
        (CONTROL_PLACEHOLDER, 3),
    ]
    assert [ink_of(code, g) for g in glyphs] == [add, warning, warning]
    # The header names the kind, and the copy is the text.
    assert header_of(view, 0) == "geom.py+3-3!containsinvisibleorbidirectionalcontrolcharacters"
    view.select_all()
    assert view.selected_text() == after.rstrip("\n")
    # Hit testing is on the same cells: the character after the placeholder.
    position = view._position(find_row(view, f"user = ad{ZWSP}min{RLO}", RowKind.ADD), 10, None)
    assert position is not None and position[3] == 10


def test_review3_item_1_the_header_names_each_kind_of_character(bundled_fonts: Any) -> None:
    theme = Theme.build()

    def warning_of(after: str) -> str:
        view = DiffView(Diff.from_texts("a\n", after, "f"), theme)
        return view._file_header(view.diff.files[0])[1]

    assert warning_of("b\n") == ""
    assert warning_of("b\0\n") == "  ! contains control characters"
    assert warning_of(f"b{RLO}\n") == "  ! contains invisible or bidirectional control characters"
    assert warning_of(f"b{RLO}\0\n") == (
        "  ! contains control characters  ! contains invisible or bidirectional control characters"
    )
    # A file shown as written, and a file whose NAME holds the override.
    view = DiffView(Diff.from_unified(f"prose with {RLO} in it\n"), theme)
    assert "invisible or bidirectional" in view._file_header(view.diff.files[0])[1]
    plan = view.frame_plan(900.0)
    raw = plan.region("raw")
    assert CONTROL_PLACEHOLDER in raw.text_at(baseline(view, 1)) and RLO not in raw.text_at(
        baseline(view, 1)
    )
    named = DiffView(Diff.from_texts("a\n", "b\n", f"evil{RLO}txt.exe"), theme)
    frame_region = named.frame_plan(900.0).region("frame")
    title = frame_region.text_at(baseline(named, 0))
    assert title.startswith("evil" + CONTROL_PLACEHOLDER + "txt.exe") and RLO not in title


def test_review3_item_6_lines_not_read_as_diff_are_counted_in_the_header(
    bundled_fonts: Any,
) -> None:
    text = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\nand some prose\nmore of it\n"
    diff = Diff.from_unified(text)
    assert diff.files[0].unread == ("and some prose", "more of it")
    view = DiffView(diff, Theme.build())
    assert header_of(view) == "x+1-1!2linesnotreadaspartofthediff"
    assert "not read" not in header_of(DiffView(Diff.from_texts("a\n", "b\n", "x"), Theme.build()))


def test_review3_item_9_a_nul_does_not_cut_the_clipboard_short(bundled_fonts: Any) -> None:
    """
    The clipboard is a C string: `set_clipboard_text("key = 'ab\\0cd'\\n...")`
    put `key = 'ab` on it and nothing after -- text that is on neither side,
    without saying so. What is handed to the clipboard has U+2400 (the
    picture of a NUL) for each NUL; `selected_text` keeps the character.
    """
    from imgui_bundle import imgui

    from advtext.ui.bare_view import CLIPBOARD_NUL, clipboard_text

    assert CLIPBOARD_NUL == chr(0x2400)
    assert clipboard_text("a\0b\0") == f"a{CLIPBOARD_NUL}b{CLIPBOARD_NUL}"
    assert clipboard_text("plain") == "plain"
    after = "key = 'ab\0cd'\nnext line\n"
    view = DiffView(Diff.from_texts("a\n", after, "f.py"), Theme.build())
    wanted = f"key = 'ab{CLIPBOARD_NUL}cd'\nnext line"
    context = imgui.create_context()
    try:
        view.select_all()
        assert view.selected_text() == "key = 'ab\0cd'\nnext line"  # the real character
        view.copy()
        assert imgui.get_clipboard_text() == wanted
        view.copy("x\0y")
        assert imgui.get_clipboard_text() == f"x{CLIPBOARD_NUL}y"
    finally:
        imgui.destroy_context(context)
    # Ctrl+C, in frames: the same text.
    imgui.set_clipboard_text("sentinel")
    settle(view)
    view.select_all()
    frame(view, keys=("mod_ctrl", "c"))
    copied = frame(view, release=("mod_ctrl", "c"))
    assert copied.clipboard == wanted

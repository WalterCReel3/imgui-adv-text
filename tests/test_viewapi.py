r"""
The view API the demo pages had to work around (C-viewapi).

Each page builder was told to use public routes and report what was missing.
What they converged on is tested here, one section a need:

1. where a block and a span of a block are, on or off screen, and scrolling
   there (`BareView.block_rect`, `span_rects`, `to_screen`, `scroll_to`,
   `viewport`, `next_origin`);
2. what a layout cost (`UnitLayout.stats`, `Unit.build_seconds`,
   `BareView.layout_stats`);
3. a table's column floors and natural widths in one call
   (`advtext.ui.table_column_limits`);
4. a find index over a whole document, table cells included
   (`advtext.spans.FindIndex`);
5. public names for the selection-ownership counter and the click-count
   lookup (`SELECTION_OWNERSHIP`, `granularity_for`).

**The oracles are the pages' own substitutes where one existed**, because those
were checked against the library by their builders: `find_spans` for the index,
`table_columns` at a one-point measure for the floors, `UnitCache.misses` for
the build count.

Frames are headless (`tests/test_bare_view.py::frame`): no pixels, no window.
"""

from __future__ import annotations

from typing import Any

import pytest

from advtext.markdown import CodeBlock, TableBlock, TextBlock, build_document
from advtext.selection import Granularity, Rect
from advtext.shipout import Glyph
from advtext.spans import FindIndex, TextMatch, find_spans, material_text
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import ColumnLimits, table_column_limits, table_columns, table_natural_widths
from advtext.ui.bare_view import (
    SELECTION_OWNERSHIP,
    BareView,
    SelectionOwnership,
    granularity_for,
    scroll_for,
)
from advtext.ui.stream_view import StreamView
from advtext.ui.units import LayoutStats, UnitCache, layout_units
from advtext.units import UNITY, px_from_sp
from tests.test_bare_view import frame

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky"
)

SOURCE = (
    f"First paragraph: {WORDS}.\n\n"
    "> A quoted paragraph with the needle in it.\n"
    ">\n"
    "> A second quoted paragraph, needle again.\n\n"
    "```\nfirst line\nsecond needle line\n\nfourth\n```\n\n"
    "| name | what it says |\n"
    "| --- | --- |\n"
    "| one | a cell with a needle in it |\n"
    "| needle | supercalifragilistic and some more words |\n\n"
    "Last paragraph, with one more needle at the end.\n"
)
"""
A paragraph, a two-paragraph quote (one unit, two blocks), a code block with a
blank line, a table with the needle in two cells, and a closing paragraph.
"""

WIDTH = 360 * UNITY


@pytest.fixture
def theme(bundled_fonts: Any) -> Theme:
    return Theme.build()


@pytest.fixture
def measure(bundled_fonts: Any) -> Any:
    return char_measure(fontlib_metrics)


def _view(theme: Theme, measure: Any, source: str = SOURCE) -> BareView:
    return BareView(
        document=build_document(source, theme, fontlib_metrics), theme=theme, measure=measure
    )


def _long(theme: Theme, measure: Any) -> BareView:
    paragraphs = [f"Paragraph {number}: {WORDS}." for number in range(60)]
    paragraphs[45] = f"Paragraph 45 holds the needle. {WORDS}."
    return _view(theme, measure, "\n\n".join(paragraphs) + "\n")


def _settle(view: BareView) -> Any:
    """
    Draw `view` until it is settled at the top of the pane, and return what the last frame saw.

    Every test here draws into the one child window `frame` makes, and ImGui
    keeps that window's scroll from one test to the next: without this a
    test would start wherever the test before it left the pane.
    """
    frame(view, mouse=(1190.0, 790.0), left=False, right=False)
    view.scroll_to(Rect(0, 0, 0, 0), align=0.0, always=True, margin_px=0.0)
    frame(view)
    frame(view)
    return frame(view)


def _first(view: BareView, kind: type) -> int:
    return next(
        number for number, block in enumerate(view.document.blocks) if isinstance(block, kind)
    )


def _baselines(view: BareView, block: int) -> list[int]:
    """
    The baseline of every glyph of one block, in document scaled points, by the commands.
    """
    layout = view.layout
    assert layout is not None
    own = layout.indices_of_block(block)
    return [
        cmd.y
        for unit in layout.units_of_block(block)
        for cmd in unit.cmds
        if isinstance(cmd, Glyph) and own.start <= cmd.index < own.stop
    ]


# -- 5: public names ---------------------------------------------------------


def test_the_ownership_counter_and_the_click_lookup_have_public_names() -> None:
    import advtext.ui.bare_view as bare
    import advtext.ui.diff_view as diff

    assert isinstance(SELECTION_OWNERSHIP, SelectionOwnership)
    # One counter, whatever name it is reached by: a second one is the
    # two-panes-both-copy defect review 0 warned of.
    assert bare._OWNERSHIP is SELECTION_OWNERSHIP
    assert diff.SELECTION_OWNERSHIP is SELECTION_OWNERSHIP
    assert bare._granularity_for is granularity_for
    assert [granularity_for(count) for count in (0, 1, 2, 3, 4)] == [
        Granularity.CHARACTER,
        Granularity.CHARACTER,
        Granularity.WORD,
        Granularity.LINE,
        Granularity.LINE,
    ]
    assert {"SELECTION_OWNERSHIP", "SelectionOwnership", "granularity_for"} <= set(bare.__all__)


def test_a_bare_view_and_a_diff_view_take_turns_on_the_one_counter(
    theme: Theme, measure: Any
) -> None:
    from advtext.diff import Diff
    from advtext.selection import Selection
    from advtext.ui.diff_view import DiffView

    text = _view(theme, measure)
    text.layout_for(WIDTH)
    diff = DiffView(Diff.from_texts("a\n", "b\n", "f"), theme)

    text.select(Selection(0, 3))
    assert text.owns_selection and not diff.owns_selection
    diff.select_all()
    assert diff.owns_selection and not text.owns_selection
    text.select_all()
    assert text.owns_selection and not diff.owns_selection


# -- 2: what a layout cost ---------------------------------------------------


def test_a_layouts_stats_are_the_unit_caches_own_counts(theme: Theme, measure: Any) -> None:
    document = build_document(SOURCE, theme, fontlib_metrics)
    units = UnitCache()

    cold = layout_units(document.blocks, theme, WIDTH, measure, units=units)
    stats = cold.stats
    assert isinstance(stats, LayoutStats)
    assert stats.units == len(cold.placed)
    assert stats.built == tuple(range(len(cold.placed)))
    assert len(stats.built) == units.misses
    assert stats.reused == 0 == units.hits
    # Every block was broken: nothing was there to find.
    assert stats.blocks_broken == len(document.blocks)
    assert all(stats.was_built(position) for position in range(stats.units))
    assert stats.seconds > 0.0
    assert 0.0 < stats.build_seconds <= stats.seconds
    assert stats.build_seconds == pytest.approx(
        sum(unit.unit.build_seconds for unit in cold.placed)
    )

    warm = layout_units(document.blocks, theme, WIDTH, measure, units=units, previous=cold)
    assert warm.stats.built == ()
    assert warm.stats.reused == warm.stats.units == len(cold.placed)
    assert warm.stats.blocks_broken == 0
    assert warm.stats.build_seconds == 0.0
    assert units.misses == len(cold.placed)
    # A reused unit still says what it cost when it was built.
    assert [unit.unit.build_seconds for unit in warm.placed] == [
        unit.unit.build_seconds for unit in cold.placed
    ]


def test_a_re_parsed_document_is_reported_reused_though_every_unit_object_is_new(
    theme: Theme, measure: Any
) -> None:
    # The substitute review 0 suggested (`placed[i].unit is previous.placed[i].unit`)
    # reports a full rebuild here; two pages measured that. The cache re-homes
    # a unit found by value, and the stats say what it did.
    units = UnitCache()
    first = layout_units(
        build_document(SOURCE, theme, fontlib_metrics).blocks, theme, WIDTH, measure, units=units
    )
    again = layout_units(
        build_document(SOURCE, theme, fontlib_metrics).blocks,
        theme,
        WIDTH,
        measure,
        units=units,
        previous=first,
    )
    assert any(
        new.unit is not old.unit for new, old in zip(again.placed, first.placed, strict=True)
    )
    assert again.stats.built == ()
    assert again.stats.reused == len(again.placed)
    assert units.misses == len(first.placed)


def test_one_changed_block_is_one_unit_built_and_it_is_named(theme: Theme, measure: Any) -> None:
    units = UnitCache()
    before = build_document(SOURCE, theme, fontlib_metrics)
    first = layout_units(before.blocks, theme, WIDTH, measure, units=units)
    after = build_document(
        SOURCE.replace("Last paragraph", "Final paragraph"), theme, fontlib_metrics
    )
    second = layout_units(after.blocks, theme, WIDTH, measure, units=units, previous=first)

    last = len(second.placed) - 1
    assert second.stats.built == (last,)
    assert second.stats.was_built(last) and not second.stats.was_built(0)
    assert second.stats.reused == last
    assert second.stats.blocks_broken == 1
    assert units.misses == len(first.placed) + 1


def test_a_quote_whose_one_paragraph_changed_breaks_one_block_of_its_unit(
    theme: Theme, measure: Any
) -> None:
    # A run of several blocks goes through the block cache, so the unit is
    # rebuilt and only the paragraph that changed is broken again. Needs the
    # `LayoutCache` a view passes; without one both would be broken.
    from advtext.ui import LayoutCache

    units, blocks = UnitCache(), LayoutCache()
    before = build_document(SOURCE, theme, fontlib_metrics)
    first = layout_units(before.blocks, theme, WIDTH, measure, units=units, cache=blocks)
    after = build_document(SOURCE.replace("needle again", "nothing here"), theme, fontlib_metrics)
    second = layout_units(
        after.blocks, theme, WIDTH, measure, units=units, cache=blocks, previous=first
    )
    assert len(second.stats.built) == 1
    quote = second.placed[second.stats.built[0]]
    assert len(quote.blocks) == 2
    assert second.stats.blocks_broken == 1


def test_position_of_is_the_index_in_placed(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    layout = view.layout_for(WIDTH)
    assert [layout.position_of(unit) for unit in layout.placed] == list(range(len(layout.placed)))
    other = _view(theme, measure, "Another document.\n").layout_for(WIDTH)
    assert layout.position_of(other.placed[0]) is None


def test_units_of_block_still_finds_every_piece_and_nothing_else(
    theme: Theme, measure: Any
) -> None:
    document = build_document(SOURCE, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, WIDTH, measure, code_lines=2, table_rows=1)
    for number in range(-1, len(document.blocks) + 2):
        expected = tuple(unit for unit in layout.placed if number in unit.block_range)
        assert layout.units_of_block(number) == expected
    code = next(n for n, block in enumerate(document.blocks) if isinstance(block, CodeBlock))
    assert len(layout.units_of_block(code)) == 2


def test_a_view_reports_its_last_relayout_and_keeps_it_across_invalidate(
    theme: Theme, measure: Any
) -> None:
    view = _view(theme, measure)
    assert view.layout_stats is None
    layout = view.layout_for(WIDTH)
    assert view.layout_stats is layout.stats
    assert len(layout.stats.built) == view._units.stats().misses  # the oracle, read once

    view.invalidate()
    assert view.layout_stats is layout.stats
    again = view.layout_for(WIDTH)
    assert again is not layout
    assert view.layout_stats is again.stats
    assert again.stats.built == () and again.stats.reused == len(again.placed)


# -- 3: a table's column limits ---------------------------------------------


def test_a_tables_floors_and_natural_widths_come_from_one_call(theme: Theme, measure: Any) -> None:
    document = build_document(SOURCE, theme, fontlib_metrics)
    table = next(block for block in document.blocks if isinstance(block, TableBlock))

    limits = table_column_limits(table, theme, measure)
    assert isinstance(limits, ColumnLimits)
    assert limits.natural == table_natural_widths(table, theme, measure)
    # The Tables page's route to the floors: at a one-point measure nothing
    # fits, and the library's third regime returns each column's longest word.
    assert limits.floor == table_columns(table, theme, UNITY, measure)
    assert len(limits.floor) == 2
    assert all(low <= high for low, high in zip(limits.floor, limits.natural, strict=True))
    # The second column's floor is its longest word and not its longest cell.
    assert limits.floor[1] < limits.natural[1]
    # A measure between the two sums squeezes: no column under its floor.
    between = (sum(limits.floor) + sum(limits.natural)) // 2
    squeezed = table_columns(table, theme, between, measure)
    assert sum(squeezed) == between
    assert all(got >= low for got, low in zip(squeezed, limits.floor, strict=True))


def test_a_table_with_no_rows_has_no_limits(theme: Theme, measure: Any) -> None:
    from dataclasses import replace

    document = build_document(SOURCE, theme, fontlib_metrics)
    table = next(block for block in document.blocks if isinstance(block, TableBlock))
    empty = replace(table, header=(), rows=())
    assert table_column_limits(empty, theme, measure) == ColumnLimits((), ())


# -- 4: a find index over a document -----------------------------------------


@pytest.mark.parametrize("ignore_case", [False, True])
@pytest.mark.parametrize("needle", ["needle", "Needle", "a ", "line\n", "paragraph", "zzz", "e"])
def test_the_index_finds_in_text_and_code_what_find_spans_finds(
    theme: Theme, measure: Any, needle: str, ignore_case: bool
) -> None:
    document = build_document(SOURCE, theme, fontlib_metrics)
    index = FindIndex.of(document.blocks)
    found = [
        (match.block, match.start, match.end)
        for match in index.find(needle, ignore_case=ignore_case)
        if match.cell is None
    ]
    expected = [
        (number, span.start, span.end)
        for number, block in enumerate(document.blocks)
        if isinstance(block, (TextBlock, CodeBlock))
        for span in find_spans(block, needle, ignore_case=ignore_case)
    ]
    assert found == expected


def test_the_index_finds_in_table_cells_and_says_which(theme: Theme, measure: Any) -> None:
    document = build_document(SOURCE, theme, fontlib_metrics)
    table = next(n for n, block in enumerate(document.blocks) if isinstance(block, TableBlock))
    index = FindIndex.of(document.blocks)

    matches = index.find("needle")
    cells = [match for match in matches if match.cell is not None]
    assert [(match.block, match.cell) for match in cells] == [(table, (1, 1)), (table, (2, 0))]
    # Reading order: every match is in a block at or after the one before.
    assert [match.block for match in matches] == sorted(match.block for match in matches)
    assert sum(1 for match in matches if match.cell is None) == 4
    # A cell's range is material indices of that cell, like a block's.
    block = document.blocks[table]
    assert isinstance(block, TableBlock)
    first = cells[0]
    assert isinstance(first, TextMatch)
    material = block.rows[0][1].material[first.start : first.end]
    assert "".join(chr(node.codepoint) for node in material) == "needle"  # type: ignore[union-attr]

    assert index.find("") == ()
    assert index.find("NEEDLE") == ()
    assert len(index.find("NEEDLE", ignore_case=True)) == len(matches)


def test_the_index_is_built_once_and_a_search_builds_no_text(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import advtext.spans as spans

    document = build_document(SOURCE, theme, fontlib_metrics)
    index = FindIndex.of(document.blocks)
    calls = 0
    real = spans.material_text

    def counted(block: Any) -> Any:
        nonlocal calls
        calls += 1
        return real(block)

    monkeypatch.setattr(spans, "material_text", counted)
    monkeypatch.setattr(spans, "_prose_text", lambda material: pytest.fail("text rebuilt"))
    for needle in ("needle", "a", "paragraph"):
        index.find(needle)
        index.find(needle, ignore_case=True)
    assert calls == 0


# -- 1: where things are -----------------------------------------------------


def test_nothing_is_anywhere_before_a_layout(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    assert view.block_rect(0) is None
    assert view.span_rects(0, 0, 5) == []
    assert view.to_screen(Rect(0, 0, 1, 1)) is None
    assert view.viewport is None
    view.layout_for(WIDTH)
    # Laid out and never drawn: document space is known, the screen is not.
    assert view.block_rect(0) is not None
    assert view.to_screen(Rect(0, 0, 1, 1)) is None
    assert view.block_rect(999) is None and view.block_rect(-1) is None


def test_a_blocks_rect_is_its_own_extent_the_full_measure_wide(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    layout = view.layout_for(WIDTH)
    rects = [view.block_rect(number) for number in range(len(view.document.blocks))]
    assert all(rect is not None for rect in rects)
    previous_bottom = 0
    for number, rect in enumerate(rects):
        assert rect is not None
        assert (rect.x, rect.width) == (0, layout.width)
        assert rect.height > 0
        # In document order, never overlapping, and inside the document.
        assert rect.y >= previous_bottom
        previous_bottom = rect.y + rect.height
        # Every glyph of the block sits on a baseline inside it.
        for baseline in _baselines(view, number):
            assert rect.y < baseline <= rect.y + rect.height
    assert previous_bottom <= layout.height

    # The quote's two paragraphs share a unit and have a rectangle each.
    quote = next(unit for unit in layout.placed if len(unit.blocks) == 2)
    upper, lower = (view.block_rect(number) for number in quote.block_range)
    assert upper is not None and lower is not None
    assert quote.y <= upper.y < upper.y + upper.height <= lower.y
    assert lower.y + lower.height <= quote.bottom


def test_a_block_in_pieces_has_one_rect_from_its_first_piece_to_its_last(
    theme: Theme, measure: Any
) -> None:
    from advtext.stream import StreamDocument

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("```\n" + "".join(f"line {number}\n" for number in range(70)) + "```\n\nAfter.\n")
    stream.close()
    view = StreamView(stream, measure)
    view.sync()
    layout = view.layout_for(WIDTH)
    code = _first(view, CodeBlock)
    pieces = layout.units_of_block(code)
    assert len(pieces) > 1
    rect = view.block_rect(code)
    assert rect == Rect(0, pieces[0].y, layout.width, pieces[-1].bottom - pieces[0].y)

    # A span on a line in a late piece is found in that piece.
    block = view.document.blocks[code]
    assert isinstance(block, CodeBlock)
    text = material_text(block)
    at = text.text.index("line 60")
    behind = text.span(at, at + len("line 60"))
    assert behind is not None
    (found,) = view.span_rects(code, *behind)
    # Line 60 of 70 is in a piece after the first, and inside the block.
    assert pieces[1].y <= found.y and found.y + found.height <= pieces[-1].bottom
    assert found.width > 0


def test_span_rects_cover_the_glyphs_of_the_span_and_no_others(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    layout = view.layout_for(WIDTH)
    index = FindIndex.of(view.document.blocks)
    matches = index.find("needle")
    assert len(matches) == 6
    for match in matches:
        rects = view.span_rects(match.block, match.start, match.end, cell=match.cell)
        assert len(rects) == 1, match
        (rect,) = rects
        inside = sorted(
            (cmd.x, chr(cmd.codepoint))
            for unit in layout.units_of_block(match.block)
            for cmd in unit.cmds
            if isinstance(cmd, Glyph)
            and rect.y < cmd.y <= rect.y + rect.height
            and rect.x <= cmd.x < rect.x + rect.width
        )
        assert "".join(char for _, char in inside) == "needle", match
        block = view.block_rect(match.block)
        assert block is not None
        assert block.y <= rect.y and rect.y + rect.height <= block.y + block.height

    # A span over a line break is a rectangle a line.
    first = view.document.blocks[0]
    assert isinstance(first, TextBlock)
    assert len(view.span_rects(0, 0, len(first.material))) > 1
    # Nothing for an empty range, a table without a cell, or a cell that is not there.
    table = _first(view, TableBlock)
    assert view.span_rects(0, 5, 5) == []
    assert view.span_rects(table, 0, 3) == []
    assert view.span_rects(table, 0, 3, cell=(9, 0)) == []
    assert view.span_rects(table, 0, 3, cell=(0, 9)) == []
    assert view.span_rects(0, 0, 3, cell=(0, 0)) == []


def test_span_rects_in_a_table_laid_out_in_pieces(theme: Theme, measure: Any) -> None:
    from advtext.stream import StreamDocument

    rows = "".join(f"| row {number} | value {number} here |\n" for number in range(11))
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("| a | b |\n| --- | --- |\n" + rows + "\nAfter.\n")
    stream.close()
    view = StreamView(stream, measure)
    view.sync()
    layout = view.layout_for(WIDTH)
    table = _first(view, TableBlock)
    pieces = layout.units_of_block(table)
    assert len(pieces) > 1

    index = FindIndex.of(view.document.blocks)
    (match,) = index.find("value 9")
    assert match.cell == (10, 1)
    (rect,) = view.span_rects(match.block, match.start, match.end, cell=match.cell)
    assert pieces[-1].y <= rect.y < pieces[-1].bottom
    header = index.find("b")[0]
    assert header.cell == (0, 1)
    (top,) = view.span_rects(header.block, header.start, header.end, cell=header.cell)
    assert pieces[0].y <= top.y < pieces[0].bottom


def test_to_screen_is_the_origin_plus_the_rect_in_pixels(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    _settle(view)
    assert view.origin is not None
    rect = view.block_rect(1)
    assert rect is not None
    left, top, right, bottom = view.to_screen(rect)  # type: ignore[misc]
    assert left == view.origin[0] + px_from_sp(rect.x)
    assert top == view.origin[1] + px_from_sp(rect.y)
    assert right - left == pytest.approx(px_from_sp(rect.width))
    assert bottom - top == pytest.approx(px_from_sp(rect.height))
    # The same place `block_at` answers for.
    assert view.block_at(left + 1.0, (top + bottom) / 2.0) == 1


def test_next_origin_is_the_origin_the_draw_then_uses(theme: Theme, measure: Any) -> None:
    view = _view(theme, measure)
    told: list[tuple[float, float]] = []

    def before(imgui: Any, seen: Any) -> None:
        imgui.set_cursor_pos(imgui.ImVec2(10.4, 20.6))
        told.append(view.next_origin())

    frame(view, before=before)
    frame(view, before=before)
    assert view.origin == told[-1]
    assert told[-1] == (float(round(told[-1][0])), float(round(told[-1][1])))


def test_the_viewport_is_the_band_the_last_draw_showed(theme: Theme, measure: Any) -> None:
    view = _long(theme, measure)
    seen = _settle(view)
    shown = view.viewport
    assert shown is not None and view.layout is not None
    assert seen.scroll_max > 0.0
    assert shown.top <= 0 < shown.bottom < view.layout.height


# The arithmetic, in pixels of scrolled content: (top, bottom, scroll, height).


def test_scroll_for_leaves_what_is_in_view_alone() -> None:
    assert scroll_for(300.0, 320.0, 200.0, 400.0) is None
    assert scroll_for(300.0, 320.0, 200.0, 400.0, align=0.5) is None
    # Inside the window but inside the margin too: it moves.
    assert scroll_for(210.0, 230.0, 200.0, 400.0) == 186.0
    assert scroll_for(210.0, 230.0, 200.0, 400.0, margin=0.0) is None


def test_scroll_for_goes_to_the_nearer_edge() -> None:
    # Above: the top comes to the top, less the margin.
    assert scroll_for(100.0, 120.0, 200.0, 400.0) == 76.0
    # Below: the bottom comes to the bottom, plus the margin.
    assert scroll_for(900.0, 920.0, 200.0, 400.0) == 920.0 + 24.0 - 400.0
    # Taller than the window: its top wins.
    assert scroll_for(900.0, 1900.0, 200.0, 400.0) == 876.0
    # Never above the start.
    assert scroll_for(5.0, 25.0, 200.0, 400.0) == 0.0


def test_scroll_for_puts_the_top_a_fraction_down_when_asked() -> None:
    assert scroll_for(900.0, 920.0, 200.0, 400.0, align=0.0) == 900.0
    assert scroll_for(900.0, 920.0, 200.0, 400.0, align=0.25) == 800.0
    assert scroll_for(50.0, 70.0, 200.0, 400.0, align=0.5) == 0.0
    # `always` moves what is already in view; without a fraction there is
    # nowhere nearer than where it is.
    assert scroll_for(300.0, 320.0, 200.0, 400.0, align=0.0, always=True) == 300.0
    assert scroll_for(300.0, 320.0, 200.0, 400.0, always=True) is None


def test_scroll_to_brings_an_off_screen_match_into_the_window(theme: Theme, measure: Any) -> None:
    view = _long(theme, measure)
    seen = _settle(view)
    assert seen.scroll_y == 0.0
    (match,) = FindIndex.of(view.document.blocks).find("needle")
    (rect,) = view.span_rects(match.block, match.start, match.end)
    shown = view.viewport
    assert shown is not None and rect.y > shown.bottom

    # Asked from outside the child, as a host's "next match" button is.
    view.scroll_to(rect)
    frame(view)  # the request is made of ImGui inside this draw
    seen = frame(view)  # and has taken effect by this one
    assert seen.scroll_y > 0.0
    shown = view.viewport
    assert shown is not None
    assert shown.top <= rect.y and rect.y + rect.height <= shown.bottom
    left, top, right, bottom = view.to_screen(rect)  # type: ignore[misc]
    assert top >= seen.window_pos[1]

    # One request, one scroll: nothing is held, so the reader can scroll away.
    settled = frame(view).scroll_y
    assert frame(view).scroll_y == settled
    view.scroll_to(rect)
    frame(view)
    assert frame(view).scroll_y == settled  # already in view: it stays put

    # Back to the top, exactly: a fraction and `always`.
    top_rect = view.block_rect(0)
    assert top_rect is not None
    view.scroll_to(top_rect, align=0.0, always=True, margin_px=0.0)
    frame(view)
    assert frame(view).scroll_y == 0.0


def test_two_views_are_kept_on_one_place_by_viewport_and_scroll_to(
    theme: Theme, measure: Any
) -> None:
    # What the Themes page's split and the Diff page's two panes want: read
    # where one view is, put the other there.
    leader = _long(theme, measure)
    _settle(leader)
    target = leader.block_rect(30)
    assert target is not None
    leader.scroll_to(target, align=0.0, always=True, margin_px=0.0)
    frame(leader)
    seen = frame(leader)
    shown = leader.viewport
    assert shown is not None
    assert seen.scroll_y == pytest.approx(px_from_sp(target.y), abs=1.0)

    follower = _long(theme, measure)
    _settle(follower)
    assert follower.viewport is not None and follower.viewport.top != shown.top
    follower.scroll_to(Rect(0, shown.top, 0, 0), align=0.0, always=True, margin_px=0.0)
    frame(follower)
    frame(follower)
    assert follower.viewport is not None
    assert abs(px_from_sp(follower.viewport.top - shown.top)) <= 1.0


def test_a_stream_view_that_is_sent_somewhere_stops_following_its_tail(
    theme: Theme, measure: Any
) -> None:
    from advtext.stream import StreamDocument

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("\n\n".join(f"Paragraph {number}: {WORDS}." for number in range(60)) + "\n\n")
    view = StreamView(stream, measure)
    frame(view, mouse=(1190.0, 790.0), left=False, right=False)
    view.follow_tail()
    frame(view)
    frame(view)
    seen = frame(view)
    assert view.following and seen.scroll_y == seen.scroll_max > 0.0

    rect = view.block_rect(3)
    assert rect is not None
    view.scroll_to(rect)
    frame(view)
    seen = frame(view)
    assert seen.scroll_y < seen.scroll_max
    assert not view.following
    shown = view.viewport
    assert shown is not None and shown.top <= rect.y < shown.bottom
    # More text arriving does not drag it back.
    stream.append("One more paragraph arrives.\n\n")
    frame(view)
    assert frame(view).scroll_y == seen.scroll_y


def test_scroll_to_allows_for_what_the_host_drew_above_the_view(theme: Theme, measure: Any) -> None:
    # The pane's scroll counts from the top of the child, the rectangle from
    # the top of the document, and here they differ by a host widget.
    view = _long(theme, measure)

    def above(imgui: Any, seen: Any) -> None:
        imgui.dummy(imgui.ImVec2(10.0, 137.0))

    frame(view, before=above, mouse=(1190.0, 790.0), left=False, right=False)
    frame(view, before=above)
    target = view.block_rect(40)
    assert target is not None
    view.scroll_to(target, align=0.0, always=True, margin_px=0.0)
    frame(view, before=above)
    seen = frame(view, before=above)
    # Scrolled by the block's offset *and* the widget above (137 px and one
    # item spacing), so the block's top is at the pane's top edge.
    assert 137.0 <= seen.scroll_y - px_from_sp(target.y) <= 137.0 + 12.0
    assert view.viewport is not None
    assert abs(px_from_sp(view.viewport.top - target.y)) <= 1.0

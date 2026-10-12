r"""
Tables whose cells wrap, and columns a caller can size.

Before this file existed a cell was one line however wide its column, so a table
wider than the measure had its columns scaled down and its cells run into each
other. `imscribe.ui._table_boxes` now breaks a cell that is wider than its
column as a paragraph, and `imscribe.ui.with_columns` lets a caller fix the
widths. Four claims are defended here, in this order:

1. **A table that fits is set exactly as it was.** `_before_wrapping` below is
   the old `_table_boxes`, transcribed, and the demo document's table is
   compared against it box for box at the measures the demo and the litmus
   render actually use. That is the assertion that the demo did not move.
2. **A table that does not fit wraps instead of overflowing**: no column below
   its longest word, no glyph outside its column, no row overlapping the next.
3. **A caller's widths are honoured and re-wrap the cells.**
4. **Reading order over wrapped cells is cell by cell, a row at a time.** The
   exact copied string is asserted, because "sane" is not a property and a
   string is.

The last section is hit testing. Wrapped cells put lines side by side in one
vertical band, and `SelectionModel.fragment_at` used to choose a line by `y`
alone, so a click in the second column of a wrapped row selected in the first.
`test_a_click_in_the_second_column_of_a_wrapped_row_lands_in_that_column`
failed against that rule (it was run as a strict `xfail` before
`imscribe.selection.fragment_nearest` existed) and passes against the new one.

**Row rhythm** (review 2, item 1) is the section after wrapping: a wrapped row
used to push the next row a `\lineskip` off the baseline grid, and the tests
there failed against that before `imscribe.ui._WrappedRow` existed. The
validation tests in section 3 likewise failed first: `with_columns` accepted a
width of 0.4 as 0 and a NaN fraction, and both surfaced at compose.

Real fonts throughout: the claims are about where glyphs land against column
edges, and a fake with one advance for every glyph cannot tell a wrapped cell
from a lucky one.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import imscribe.ui as ui
from imscribe.linebreak import LineBreakParams
from imscribe.markdown import ColumnAlign, TableBlock, TextBlock, build_document
from imscribe.nodes import Box, CharNode, Glue, Kern, Rule
from imscribe.pack import hpack
from imscribe.selection import Selection, SelectionModel
from imscribe.shipout import DrawCmd, Glyph, Line, Point, RuleRect, ship
from imscribe.style import Theme, char_measure, fontlib_metrics
from imscribe.ui import (
    PROSE_BREAKING,
    LayoutCache,
    SizedTable,
    compose_blocks,
    table_columns,
    table_natural_widths,
    with_columns,
)
from imscribe.units import UNITY, Scaled, sp_from_pt, sp_from_px

ROOT = Path(__file__).resolve().parent.parent

PROSE = (
    "| Name | What it does | Font |\n"
    "|:-----|:------------:|-----:|\n"
    "| alpha | Breaks a paragraph into lines by choosing every break at once | no |\n"
    "| bravo | Short | yes |\n"
    "| charlie | Packs a horizontal list to a width and reports how it went | no |\n"
)
"""
Three columns, one of each alignment, with two cells long enough to need several lines.
"""


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure(bundled_fonts: Any) -> Any:
    return char_measure(fontlib_metrics)


def table_of(source: str, theme: Theme) -> TableBlock:
    (block,) = build_document(source, theme, fontlib_metrics).blocks
    assert isinstance(block, TableBlock)
    return block


@pytest.fixture(scope="module")
def prose(theme: Theme, bundled_fonts: Any) -> TableBlock:
    return table_of(PROSE, theme)


@pytest.fixture(scope="module")
def demo(theme: Theme, bundled_fonts: Any) -> TableBlock:
    source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    tables = [
        block
        for block in build_document(source, theme, fontlib_metrics).blocks
        if isinstance(block, TableBlock)
    ]
    assert len(tables) == 1, "the demo document is expected to hold exactly one table"
    return tables[0]


def shipped(block: TableBlock, theme: Theme, width: Scaled, measure: Any) -> list[DrawCmd]:
    box = compose_blocks((block,), theme, width, measure)
    return ship(box, Point(0, box.height), measure=measure)


def columns_of(block: TableBlock, theme: Theme, width: Scaled, measure: Any) -> list[range]:
    """
    Each column's horizontal extent, as a half-open range of scaled points.
    """
    out: list[range] = []
    left = block.left_indent
    for column in table_columns(block, theme, width, measure):
        out.append(range(left, left + column))
        left += column
    return out


def advance(glyph: Glyph, measure: Any) -> Scaled:
    return int(measure(CharNode(font=glyph.font, codepoint=glyph.codepoint)).width)


def cell_lines(cmds: list[DrawCmd]) -> list[Line]:
    """
    The lines that hold glyphs: one a row unwrapped, several a cell wrapped.
    """
    model = SelectionModel.from_commands(cmds)
    return [fragment.line for fragment in model.fragments if fragment.items]


# -- 1. a table that fits is set as it always was -------------------------


def _before_wrapping(block: TableBlock, theme: Theme, width: Scaled, measure: Any) -> list[Box]:
    """
    `imscribe.ui._table_boxes` as it stood before cells could wrap, transcribed.

    Kept here as the oracle for "a table whose cells all fit lays out exactly
    as before". It calls the module's own `_apportioned` and `_table_row`,
    neither of which this change edited, so what it pins is the control flow
    around them: which widths are chosen and which row builder is used.
    """
    rows = [block.header, *block.rows] if block.header else list(block.rows)
    columns = max(len(row) for row in rows)
    padding = theme.cell_padding
    natural = [0] * columns
    for row in rows:
        for index, cell in enumerate(row):
            packed = hpack(cell.material, measure=measure).box
            natural[index] = max(natural[index], packed.width + 2 * padding)
    widths = ui._apportioned(natural, max(width - block.left_indent, UNITY))
    aligns = tuple(block.aligns) + (ColumnAlign.LEFT,) * (columns - len(block.aligns))
    strut = block.style.strut
    boxes: list[Box] = []
    for row in rows:
        boxes.append(
            strut.applied_to(
                ui._table_row(row, widths, aligns, block.left_indent, padding, measure)
            )
        )
        if block.header and row is rows[0] and theme.table_rule_thickness:
            boxes.append(
                hpack(
                    [
                        Kern(width=block.left_indent),
                        Rule(width=sum(widths), height=theme.table_rule_thickness, depth=0),
                    ],
                    measure=measure,
                ).box
            )
    return boxes


@pytest.mark.parametrize("width_px", [467.0, 558.0, 1070.0])
def test_the_demo_table_is_set_exactly_as_before_wherever_it_fits(
    demo: TableBlock, theme: Theme, measure: Any, width_px: float
) -> None:
    # 467 px is the demo page's 2.25-alphabet measure, 558 px is the litmus
    # render's 420 pt, 1070 px is the whole content region. The demo table's
    # natural width is under all three, which the first assertion checks so
    # that this cannot pass by comparing two wrapped layouts.
    width = sp_from_px(width_px)
    natural = ui._natural_widths(ui._table_rows(demo), theme.cell_padding, measure)
    assert sum(max(row[i] for row in natural) for i in range(len(natural[0]))) <= width
    now = ui._table_boxes(demo, theme, width, measure, PROSE_BREAKING)
    assert now == _before_wrapping(demo, theme, width, measure)


def test_a_table_that_fits_has_one_line_per_row_and_nothing_nested(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    wide = sp_from_px(1400.0)
    lines = [cmd for cmd in shipped(prose, theme, wide, measure) if isinstance(cmd, Line)]
    # Four rows, plus the box that carries the header rule.
    assert len(lines) == 5
    assert ui._table_boxes(prose, theme, wide, measure, PROSE_BREAKING) == _before_wrapping(
        prose, theme, wide, measure
    )


# -- 2. a table that does not fit wraps ----------------------------------


@pytest.mark.parametrize("width_px", [420.0, 330.0, 260.0])
def test_a_squeezed_table_fills_the_measure_and_keeps_every_glyph_in_its_column(
    prose: TableBlock, theme: Theme, measure: Any, width_px: float
) -> None:
    width = sp_from_px(width_px)
    widths = table_columns(prose, theme, width, measure)
    assert sum(widths) == width
    (rule,) = [cmd for cmd in shipped(prose, theme, width, measure) if isinstance(cmd, RuleRect)]
    assert rule.width == width

    cmds = shipped(prose, theme, width, measure)
    spans = columns_of(prose, theme, width, measure)
    glyphs = [cmd for cmd in cmds if isinstance(cmd, Glyph)]
    assert len(glyphs) > 100
    for glyph in glyphs:
        (owner,) = [span for span in spans if glyph.x in span]
        # Ink ends inside the column it starts in. Before wrapping this failed
        # for every cell wider than its scaled-down column.
        assert glyph.x + advance(glyph, measure) <= owner.stop, chr(glyph.codepoint)


def test_before_wrapping_the_same_table_ran_its_cells_into_each_other(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    # The control for the test above: the old layout at the same measure puts
    # ink past the right edge of the table. Without this, "every glyph is in
    # its column" could be true of both and would say nothing about wrapping.
    width = sp_from_px(330.0)
    from imscribe.pack import vpack

    box = vpack(_before_wrapping(prose, theme, width, measure)).box
    cmds = ship(box, Point(0, box.height), measure=measure)
    furthest = max(cmd.x + advance(cmd, measure) for cmd in cmds if isinstance(cmd, Glyph))
    assert furthest > width


def test_no_column_is_squeezed_below_its_longest_word(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    # The floors are worked out here from the *source*, one word at a time,
    # and not asked of `ui._longest_word`: a floor taken from the code under
    # test agrees with it whatever it computes. Each word is converted on its
    # own and packed at its natural width, which involves neither the line
    # breaker nor anything in `imscribe.ui`.
    padding = theme.cell_padding
    cells = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in PROSE.splitlines()
        if not line.startswith("|:")
    ]
    assert len(cells) == 4 and all(len(row) == 3 for row in cells)

    def word_width(word: str, header: bool) -> Scaled:
        # A header cell is set bold, so its words are measured from a table
        # whose header they are.
        source = f"| {word} |\n|---|\n" if header else f"| h |\n|---|\n| {word} |\n"
        table = table_of(source, theme)
        cell = table.header[0] if header else table.rows[0][0]
        return hpack(cell.material, measure=measure).box.width

    floors = [
        max(
            word_width(word, header=row_index == 0)
            for row_index, row in enumerate(cells)
            for word in row[i].split()
        )
        + 2 * padding
        for i in range(3)
    ]
    # "paragraph" is the longest word of the middle column and "charlie" of the
    # first; a floor of zero or of a whole cell would be a different number.
    assert floors[1] == word_width("paragraph", header=False) + 2 * padding
    assert floors[0] == word_width("charlie", header=False) + 2 * padding
    for width_px in (420.0, 330.0, 260.0, 120.0):
        widths = table_columns(prose, theme, sp_from_px(width_px), measure)
        assert all(got >= floor for got, floor in zip(widths, floors, strict=True))
    # And at a measure the longest words alone exceed, the table is exactly
    # its floors: wider than the measure, which is the overfull case that is left.
    narrow = sp_from_px(120.0)
    assert sum(floors) > narrow
    assert list(table_columns(prose, theme, narrow, measure)) == floors


def test_a_column_of_single_words_is_not_wrapped_to_make_room_for_prose(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    # The first and last columns hold one word a cell, so they have nothing to
    # give up. Scaling every column by the same factor, as the old apportioning
    # did, would take width from them that they cannot yield.
    rows = ui._table_rows(prose)
    padding = theme.cell_padding
    natural = ui._natural_widths(rows, padding, measure)
    first_natural = max(row[0] for row in natural)
    widths = table_columns(prose, theme, sp_from_px(330.0), measure)
    assert widths[0] == first_natural
    assert widths[1] < max(row[1] for row in natural)


def test_a_wrapped_rows_cells_hang_from_one_first_baseline_and_rows_do_not_overlap(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    width = sp_from_px(330.0)
    cmds = shipped(prose, theme, width, measure)
    spans = columns_of(prose, theme, width, measure)
    # A row is a line of the table's own vertical list; the lines that hold
    # glyphs inside its index range are its cells' lines (or the row itself,
    # when nothing in it wrapped).
    outer: list[Line] = []
    for cmd in cmds:
        if isinstance(cmd, Line) and cmd.end > cmd.start:
            if not outer or cmd.start >= outer[-1].end:
                outer.append(cmd)
    rows = [
        [line for line in cell_lines(cmds) if row.start <= line.start < row.end] for row in outer
    ]
    assert len(rows) == 4
    wrapped = [row for row in rows if len(row) > 3]
    assert len(wrapped) == 2, "the two long cells must each have wrapped"

    for row in wrapped:
        firsts = [min(ln.y for ln in row if ln.x in span) for span in spans]
        assert len(set(firsts)) == 1
    bottoms = [max(ln.y + ln.depth for ln in row) for row in rows]
    tops = [min(ln.y - ln.height for ln in row) for row in rows]
    # Rows abut exactly, except across the header rule. `top >= bottom` alone
    # is satisfied by rows any distance apart; the strut fills a leading
    # (`Strut.filling`), so on the baseline grid one row's ink box ends where
    # the next begins, and the rule's row is one further leading.
    leading = prose.style.interline.baselineskip.width
    gaps = [top - bottom for bottom, top in zip(bottoms, tops[1:], strict=False)]
    assert gaps == [leading, 0, 0]
    # A wrapped cell's lines are a leading apart, like the lines of a paragraph.
    middle = sorted(ln.y for ln in wrapped[0] if ln.x in spans[1])
    assert len(middle) >= 2
    assert {b - a for a, b in zip(middle, middle[1:], strict=False)} == {leading}


ALIGNED = (
    "| left column heading words | centre column heading words | right column heading words |\n"
    "|:--|:-:|--:|\n"
    "| alpha bravo charlie delta echo | foxtrot golf hotel india juliet "
    "| kilo lima mike november |\n"
    "| oscar papa quebec romeo | sierra tango uniform victor whiskey | xray yankee zulu alpha |\n"
)
"""
One column of each alignment, and **every cell of every column** long enough to wrap.
"""


def test_wrapped_lines_keep_their_columns_alignment(theme: Theme, measure: Any) -> None:
    # Column 0 is left-aligned, column 1 centred, column 2 right-aligned, and a
    # wrapped line is placed by the same infinitely stretchable glue an
    # unwrapped cell is. Measured as the white either side of each line's ink.
    #
    # Every column is asserted on every line. The test this replaces skipped a
    # column unless it had more than four lines, which at its measure left the
    # left and right columns unexamined, and it had no right-aligned cell of
    # more than one line.
    block = with_columns(table_of(ALIGNED, theme), fractions=(1, 1, 1))
    width = sp_from_px(330.0)
    cmds = shipped(block, theme, width, measure)
    spans = columns_of(block, theme, width, measure)
    padding = theme.cell_padding
    model = SelectionModel.from_commands(cmds)
    white: list[list[tuple[Scaled, Scaled]]] = [[], [], []]
    for fragment in model.fragments:
        glyphs = [item for item in fragment.items if isinstance(item, Glyph)]
        if not glyphs:
            continue
        column = next(i for i, span in enumerate(spans) if glyphs[0].x in span)
        # Every row wraps, so every line with ink is one cell's line and lies
        # inside one column: nothing is a whole-row line spanning all three.
        assert fragment.line.x in spans[column]
        assert fragment.line.x + fragment.line.width <= spans[column].stop
        left = glyphs[0].x - (spans[column].start + padding)
        right = (spans[column].stop - padding) - (glyphs[-1].x + advance(glyphs[-1], measure))
        white[column].append((left, right))

    # Three rows, every cell at least two lines: at least six lines a column.
    assert [len(column) >= 6 for column in white] == [True, True, True]
    # Left: flush left, and the slack is all on the right.
    assert all(left == 0 and right >= 0 for left, right in white[0])
    assert len({right for _, right in white[0]}) > 2, "lines of one width would prove nothing"
    # Right: flush right to within the one unit glue setting rounds by, and
    # the slack is all on the left -- on every line, not only the last.
    assert all(abs(right) <= 1 and left >= 0 for left, right in white[2])
    assert len({left for left, _ in white[2]}) > 2
    assert sum(1 for left, _ in white[2] if left > UNITY) >= 4
    # Centred: the same white either side, to within the rounding of two glues.
    assert all(abs(left - right) <= 2 for left, right in white[1])
    assert sum(1 for left, _ in white[1] if left > UNITY) >= 4


def test_an_empty_cell_is_still_one_line_of_its_column(theme: Theme, measure: Any) -> None:
    # `_cell_lines` used to carry a fallback for a paragraph that broke into no
    # lines at all. The breaker never returns that -- an empty paragraph is one
    # line holding its `\parfillskip` -- so the fallback could not run and was
    # removed; this is the fact it was removed on.
    block = table_of("| a | b |\n|---|---|\n| x | y |\n", theme)
    inner = sp_from_px(40.0)
    for align in ColumnAlign:
        cell, below = ui._cell_lines(
            (),
            align,
            inner + 2 * theme.cell_padding,
            block,
            theme.cell_padding,
            measure,
            PROSE_BREAKING,
        )
        lines = [node for node in cell.contents if isinstance(node, Box)]
        assert len(lines) == 1 and lines[0].width == inner
        assert below == 0
        assert (cell.height, cell.depth) == (block.style.strut.height, block.style.strut.depth)


def test_cells_are_broken_first_fit(
    prose: TableBlock, theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ragged setting through the total-fit breaker is the 80-300x case
    # `.concerns/A0-bench--builder-2--ragged-compose-is-100x-slower.md` measured.
    seen: list[LineBreakParams] = []
    shrinkable: list[bool] = []
    real = ui.break_paragraph

    def spy(material: Any, shape: Any, params: LineBreakParams, **kwargs: Any) -> Any:
        seen.append(params)
        if params.right_skip.stretch or params.left_skip.stretch:
            # A cell being set, as opposed to `_longest_word` sizing a column.
            shrinkable.append(any(isinstance(n, Glue) and n.spec.shrink for n in material))
        return real(material, shape, params, **kwargs)

    monkeypatch.setattr(ui, "break_paragraph", spy)
    ui._table_boxes(prose, theme, sp_from_px(330.0), measure, PROSE_BREAKING)
    assert seen and all(params.first_fit for params in seen)
    # And at natural spacing: a cell is handed nothing it could be compressed by,
    # though the cells as the converter emitted them do carry shrink.
    assert shrinkable and not any(shrinkable)
    assert any(
        isinstance(node, Glue) and node.spec.shrink
        for row in prose.rows
        for cell in row
        for node in cell.material
    )
    # And a table that fits breaks nothing at all.
    seen.clear()
    ui._table_boxes(prose, theme, sp_from_px(1400.0), measure, PROSE_BREAKING)
    assert seen == []


def test_a_row_shorter_than_the_table_and_an_empty_cell_still_wrap(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Where the empty cell and the missing cell *land*, not only that lines
    # came out: each still occupies its column, so what follows an empty cell
    # is not pulled left into it and the table keeps its width.
    block = table_of(
        "| a | b | c |\n|---|---|---|\n"
        "| some words that will certainly need wrapping here |  | x |\n",
        theme,
    )
    short = replace(block, rows=(block.rows[0][:2],))
    width = sp_from_px(150.0)
    for candidate in (block, short):
        widths = table_columns(candidate, theme, width, measure)
        assert len(widths) == 3
        spans = columns_of(candidate, theme, width, measure)
        header, rule, body = ui._table_boxes(candidate, theme, width, measure, PROSE_BREAKING)
        # One sub-box per column, each exactly its column's width, in both rows.
        for row in (header, body):
            cells = [node for node in row.contents if isinstance(node, Box)]
            assert [cell.width for cell in cells] == list(widths)
            assert row.width == sum(widths)
        assert rule.width == sum(widths)

        cmds = shipped(candidate, theme, width, measure)
        glyphs = [cmd for cmd in cmds if isinstance(cmd, Glyph)]
        body_top = min(cmd.y for cmd in glyphs) + 1
        per_column = [
            "".join(chr(g.codepoint) for g in glyphs if g.x in span and g.y > body_top)
            for span in spans
        ]
        # The wrapped cell's ink is all in the first column, on several lines.
        assert per_column[0] == "somewordsthatwillcertainlyneedwrappinghere"
        assert len({g.y for g in glyphs if g.x in spans[0] and g.y > body_top}) > 2
        # The empty cell holds nothing, and the cell after it is in the third
        # column -- or absent, in the row that has no third cell.
        assert per_column[1] == ""
        assert per_column[2] == ("x" if candidate is block else "")
        # The cell after the empty one hangs from the row's first baseline.
        if candidate is block:
            (x,) = [g for g in glyphs if g.x in spans[2] and g.y > body_top]
            assert x.y == min(g.y for g in glyphs if g.y > body_top)


# -- 2b. row rhythm ---------------------------------------------------------


def baselines(cmds: list[DrawCmd]) -> list[Scaled]:
    return sorted({cmd.y for cmd in cmds if isinstance(cmd, Glyph)})


def steps(cmds: list[DrawCmd]) -> list[Scaled]:
    ys = baselines(cmds)
    return [b - a for a, b in zip(ys, ys[1:], strict=False)]


WRAPS_IN_BODY = (
    "| k | v |\n|---|---|\n"
    "| r1 | alpha bravo charlie delta echo foxtrot |\n"
    "| r2 | x |\n"
    "| r3 | y |\n"
)
WRAPS_IN_HEADER = (
    "| k | alpha bravo charlie delta echo foxtrot |\n|---|---|\n| r1 | x |\n| r2 | y |\n"
)
"""
Review 2's two sources, verbatim: the lead measured them at 150 px.
"""


def test_the_row_after_a_wrapped_row_is_one_leading_below_its_last_baseline(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Measured before the fix (review 2, item 1): steps of 2, 1, 1, 1.074, 1
    # leadings -- the row after the wrapped one sat a `\lineskip` low, because
    # the wrapped row's box is as deep as all its lines and §679 falls back to
    # `\lineskip` when the previous depth leaves no room for `\baselineskip`.
    block = table_of(WRAPS_IN_BODY, theme)
    leading = block.style.interline.baselineskip.width
    fits = steps(shipped(block, theme, sp_from_px(900.0), measure))
    assert fits == [2 * leading, leading, leading]
    wraps = steps(shipped(block, theme, sp_from_px(150.0), measure))
    assert len(wraps) > len(fits), "the long cell must have wrapped"
    assert wraps == [2 * leading] + [leading] * (len(wraps) - 1)


def test_a_wrapped_header_keeps_the_rule_and_the_first_row_where_an_unwrapped_one_has_them(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Measured before the fix: the first body row 1.369 leadings below the
    # header's last baseline, where an unwrapped header gives 2.0.
    block = table_of(WRAPS_IN_HEADER, theme)
    leading = block.style.interline.baselineskip.width

    def rule_below_header(width: Scaled) -> tuple[list[Scaled], Scaled]:
        cmds = shipped(block, theme, width, measure)
        (rule,) = [cmd for cmd in cmds if isinstance(cmd, RuleRect)]
        header_last = max(y for y in baselines(cmds) if y < rule.y)
        return steps(cmds), rule.y - header_last

    fits, rule_fits = rule_below_header(sp_from_px(900.0))
    assert fits == [2 * leading, leading]
    wraps, rule_wraps = rule_below_header(sp_from_px(150.0))
    assert len(wraps) > len(fits), "the header must have wrapped"
    assert wraps == [leading] * (len(wraps) - 2) + [2 * leading, leading]
    assert rule_wraps == rule_fits


@pytest.mark.parametrize("width_px", [420.0, 330.0, 260.0, 200.0])
def test_every_baseline_of_a_wrapped_table_is_on_one_grid(
    prose: TableBlock, theme: Theme, measure: Any, width_px: float
) -> None:
    # Cells of one row wrap to different numbers of lines here, so the row's
    # lowest baseline belongs to one cell and the next row has to step from
    # *that* one. Every step is one leading but the one across the header rule.
    leading = prose.style.interline.baselineskip.width
    cmds = shipped(prose, theme, sp_from_px(width_px), measure)
    (rule,) = [cmd for cmd in cmds if isinstance(cmd, RuleRect)]
    ys = baselines(cmds)
    assert len(ys) > 4, "something must have wrapped"
    for above, below in zip(ys, ys[1:], strict=False):
        assert below - above == (2 * leading if above < rule.y < below else leading)


def test_a_wrapped_row_does_not_change_what_surrounds_the_table(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # The resumed depth is used between the rows of a table and nowhere else:
    # the space to the next block is measured from the table's real bottom
    # edge, wrapped or not, and the table's first row still starts where the
    # block gap ends.
    source = "Before.\n\n" + WRAPS_IN_BODY.replace("| r3 | y |\n", "") + "\nAfter.\n"
    blocks = build_document(source, theme, fontlib_metrics).blocks
    table = next(block for block in blocks if isinstance(block, TableBlock))
    last = next(block for block in reversed(blocks) if isinstance(block, TextBlock))
    width = sp_from_px(150.0)
    # Make the *last* row the wrapped one, so the block after it follows a deep box.
    flipped = replace(table, rows=tuple(reversed(table.rows)))
    box = compose_blocks((blocks[0], flipped, last), theme, width, measure)
    cmds = ship(box, Point(0, box.height), measure=measure)
    ys = baselines(cmds)
    strut = table.style.strut
    gap = table.style.space_below + last.style.space_above
    # Bottom of the table is its lowest baseline plus the strut's depth.
    assert ys[-1] - ys[-2] == strut.depth + gap + last.style.strut.height
    first = blocks[0]
    assert isinstance(first, TextBlock)
    assert ys[1] - ys[0] == (
        first.style.strut.depth + first.style.space_below + table.style.space_above + strut.height
    )


# -- 3. caller-supplied widths ---------------------------------------------


def test_supplied_widths_are_used_as_given_and_rewrap_the_cells(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    width = sp_from_px(600.0)
    default = table_columns(prose, theme, width, measure)
    # A host dragging the border between columns 1 and 2 leftwards.
    dragged = (default[0], default[1] - sp_from_px(140.0), default[2] + sp_from_px(140.0))
    sized = with_columns(prose, widths=dragged)
    assert isinstance(sized, SizedTable) and isinstance(sized, TableBlock)
    assert table_columns(sized, theme, width, measure) == dragged

    before = shipped(prose, theme, width, measure)
    after = shipped(sized, theme, width, measure)
    assert len(cell_lines(after)) > len(cell_lines(before))
    spans = columns_of(sized, theme, width, measure)
    for glyph in (cmd for cmd in after if isinstance(cmd, Glyph)):
        (owner,) = [span for span in spans if glyph.x in span]
        assert glyph.x + advance(glyph, measure) <= owner.stop
    # Dragging it back un-wraps them: the same widths give the same table.
    assert shipped(with_columns(sized, widths=default), theme, width, measure) == before


def test_supplied_widths_need_not_add_up_to_the_measure(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    width = sp_from_px(600.0)
    third = sp_from_px(100.0)
    cmds = shipped(with_columns(prose, widths=(third, third, third)), theme, width, measure)
    (rule,) = [cmd for cmd in cmds if isinstance(cmd, RuleRect)]
    assert rule.width == 3 * third


def test_supplied_fractions_fill_the_measure_in_their_proportions(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    sized = with_columns(prose, fractions=(1, 2, 1))
    for width_px in (333.0, 600.0):
        width = sp_from_px(width_px)
        widths = table_columns(sized, theme, width, measure)
        assert sum(widths) == width
        assert abs(widths[1] - 2 * widths[0]) <= 2
    # In any unit: only the ratios matter.
    assert table_columns(
        with_columns(prose, fractions=(0.25, 0.5, 0.25)), theme, sp_from_px(600.0), measure
    ) == table_columns(sized, theme, sp_from_px(600.0), measure)


def test_with_columns_refuses_what_it_cannot_honour(prose: TableBlock) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        with_columns(prose)
    with pytest.raises(ValueError, match="exactly one"):
        with_columns(prose, widths=(1, 2, 3), fractions=(1, 1, 1))
    with pytest.raises(ValueError, match="3 columns"):
        with_columns(prose, widths=(UNITY, UNITY))
    with pytest.raises(ValueError, match="positive"):
        with_columns(prose, fractions=(1, 0, 1))


@pytest.mark.parametrize(
    "widths",
    [
        (0.4, UNITY, UNITY),  # measured before the fix: accepted, and became a width of 0
        (0, UNITY, UNITY),
        (-UNITY, UNITY, UNITY),
        (math.nan, UNITY, UNITY),
        (math.inf, UNITY, UNITY),
        (UNITY, UNITY, "wide"),
    ],
)
def test_with_columns_refuses_a_width_that_is_not_at_least_one_unit(
    prose: TableBlock, widths: Any
) -> None:
    with pytest.raises(ValueError, match="column width"):
        with_columns(prose, widths=widths)


@pytest.mark.parametrize(
    "fractions",
    [
        (math.nan, 1, 1),  # measured before the fix: accepted here, raised at compose
        (math.inf, 1, 1),
        (-1, 1, 1),
        (1e308, 1e308, 1e308),  # each finite, their sum is not
        (1e-320, 1e300, 1),  # a share that is zero once divided by the total
        (1, "half", 1),
    ],
)
def test_with_columns_refuses_a_fraction_that_is_no_share_of_anything(
    prose: TableBlock, fractions: Any
) -> None:
    with pytest.raises(ValueError, match="column fraction"):
        with_columns(prose, fractions=fractions)


def test_supplied_widths_that_are_not_whole_units_are_rounded_to_them(prose: TableBlock) -> None:
    # A drag handler multiplies and divides; what it has is a float of scaled
    # points. Rounded, not truncated, and never to zero (the test above).
    sized = with_columns(prose, widths=(UNITY + 0.6, 2.0 * UNITY, 3 * UNITY - 0.4))
    assert sized.column_widths == (UNITY + 1, 2 * UNITY, 3 * UNITY)
    assert all(type(entry) is int for entry in sized.column_widths)


def test_a_sized_table_built_directly_is_held_to_the_same_rules(prose: TableBlock) -> None:
    # `SizedTable` is public, so `with_columns` is not the only way in. Read by
    # the reviewer and confirmed here before the fix: two widths for three
    # columns constructed without complaint and raised `IndexError` in
    # `_table_boxes`, a frame later.
    def build(**sizes: Any) -> SizedTable:
        return SizedTable(
            style=prose.style,
            header=prose.header,
            rows=prose.rows,
            aligns=prose.aligns,
            left_indent=prose.left_indent,
            **sizes,
        )

    with pytest.raises(ValueError, match="3 columns"):
        build(column_widths=(UNITY, UNITY))
    with pytest.raises(ValueError, match="3 columns"):
        build(column_fractions=(1.0, 1.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="exactly one|both"):
        build(column_widths=(UNITY, UNITY, UNITY), column_fractions=(1.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="column width"):
        build(column_widths=(0, UNITY, UNITY))
    with pytest.raises(ValueError, match="column width"):
        build(column_widths=(0.4, UNITY, UNITY))
    with pytest.raises(ValueError, match="column fraction"):
        build(column_fractions=(math.nan, 1.0, 1.0))
    # What is allowed: either one, or neither -- which is a plain table.
    assert build(column_widths=(UNITY, UNITY, UNITY)) == with_columns(prose, widths=(UNITY,) * 3)
    assert build(column_fractions=(1.0, 2.0, 1.0)) == with_columns(prose, fractions=(1, 2, 1))
    assert build().column_widths == () and build().column_fractions == ()
    # `replace` re-validates: dropping a column from a sized table is refused
    # where it is done.
    sized = with_columns(prose, widths=(UNITY, UNITY, UNITY))
    with pytest.raises(ValueError, match="2 columns"):
        replace(sized, header=sized.header[:2], rows=tuple(row[:2] for row in sized.rows))


@pytest.mark.parametrize("fractions", [(1e-30, 1, 1), (1, 1, 1e-30), (1e-9, 1e-9, 1)])
@pytest.mark.parametrize("width_px", [1.0, 150.0, 600.0])
def test_no_accepted_fraction_gives_a_column_of_no_width_at_compose(
    prose: TableBlock, theme: Theme, measure: Any, fractions: Any, width_px: float
) -> None:
    # A tiny share is a legitimate share, so it cannot be refused at the call
    # -- which does not know the measure. What it must not do is become a
    # column of zero or negative width at compose (read by the reviewer:
    # rounding gives 0, and the remainder on the last column can give -1).
    sized = with_columns(prose, fractions=fractions)
    width = sp_from_px(width_px)
    widths = table_columns(sized, theme, width, measure)
    assert all(entry >= 1 for entry in widths)
    assert sum(widths) == max(width, UNITY)
    assert shipped(sized, theme, width, measure)


def test_a_cache_does_not_return_one_set_of_widths_for_another(
    prose: TableBlock, theme: Theme, measure: Any
) -> None:
    # The widths are part of the block, so they are part of every cache key
    # with no key having been changed.
    width = sp_from_px(600.0)
    cache = LayoutCache()
    narrow = with_columns(prose, fractions=(1, 1, 4))
    wide = with_columns(prose, fractions=(1, 4, 1))
    assert narrow != wide and narrow != prose
    results = [
        compose_blocks((block,), theme, width, measure, cache=cache)
        for block in (prose, narrow, wide, prose, narrow, wide)
    ]
    assert results[0] == results[3] and results[1] == results[4] and results[2] == results[5]
    assert len({id(r) for r in results[:3]}) == 3
    assert results[0] != results[1] != results[2]
    for block, result in zip((prose, narrow, wide), results, strict=False):
        assert result == compose_blocks((block,), theme, width, measure)


# -- 4. reading order ------------------------------------------------------


def test_copying_a_wrapped_table_reads_each_cell_whole_a_row_at_a_time(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    block = table_of(
        "| k | v |\n|---|---|\n"
        "| one | alpha bravo charlie delta echo foxtrot |\n"
        "| two | golf hotel |\n",
        theme,
    )
    width = sp_from_px(150.0)
    cmds = shipped(block, theme, width, measure)
    model = SelectionModel.from_commands(cmds)
    # Unwrapped it would be three: one line a row.
    assert len(cell_lines(cmds)) > 3, "the long cell must have wrapped"
    # What is reported, exactly: the header row, then each row's cells in
    # column order, a wrapped cell's lines run together -- never a line of one
    # cell followed by a line of its neighbour. The string itself and not its
    # words: this compared `.split()` while the flat text had doubled spaces
    # in it (review 2, item 4), which A6-copy has since removed. (The copy the old
    # views made, with tabs and newlines, was `imscribe.ui.units.UnitModel.copy_text`,
    # deleted with them in tranche 5, as is the per-unit layout this test also
    # compared with.)
    assert (
        model.text(Selection(0, model.length))
        == "k v one alpha bravo charlie delta echo foxtrot two golf hotel"
    )


def test_selecting_inside_one_wrapped_cell_copies_only_that_cell(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    block = table_of(
        "| k | v |\n|---|---|\n| one | alpha bravo charlie delta echo foxtrot |\n",
        theme,
    )
    cmds = shipped(block, theme, sp_from_px(150.0), measure)
    model = SelectionModel.from_commands(cmds)
    by_word = {
        fragment.items[0].index: fragment
        for fragment in model.fragments
        if fragment.items and isinstance(fragment.items[0], Glyph)
    }
    cell = [
        f for f in by_word.values() if chr(f.items[0].codepoint) in "abcdef" and len(f.items) > 1  # type: ignore[union-attr]
    ]
    assert len(cell) >= 2
    selection = Selection(cell[0].start, cell[-1].end)
    assert model.text(selection).split() == "alpha bravo charlie delta echo foxtrot".split()
    # One rectangle per line of the cell, all inside the second column.
    rects = model.rects(selection)
    assert len(rects) == len(cell)
    left = min(rect.x for rect in rects)
    assert all(rect.x == left for rect in rects)


def test_a_click_in_the_second_column_of_a_wrapped_row_lands_in_that_column(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    block = table_of(
        "| k | v |\n|---|---|\n| one | alpha bravo charlie delta echo foxtrot |\n",
        theme,
    )
    width = sp_from_px(150.0)
    cmds = shipped(block, theme, width, measure)
    model = SelectionModel.from_commands(cmds)
    spans = columns_of(block, theme, width, measure)
    target = next(
        fragment
        for fragment in model.fragments
        if fragment.items and fragment.line.x in spans[1] and fragment.line.y > 2 * sp_from_pt(16.0)
    )
    middle = Point((target.edges[0] + target.edges[1]) // 2, (target.top + target.bottom) // 2)
    assert model.fragment_at(middle) == target
    assert model.hit(middle) in range(target.start, target.end + 1)
    # A double click there selects a word of that cell and not of its neighbour.
    word = model.text(model.word_at(middle))
    assert word in "alpha bravo charlie delta echo foxtrot".split()
    # The padding between the two columns belongs to whichever cell is nearer.
    gutter = spans[1].start
    assert model.fragment_at(Point(gutter + 1, middle.y)) == target
    first = model.fragment_at(Point(spans[0].start + 1, middle.y))
    assert first is not None and first.line.x in spans[0]


def test_a_point_below_a_wrapped_row_goes_to_the_cell_it_is_under(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Outside every band, the nearest line in `y` wins -- and the last lines of
    # two cells that wrapped to the same depth are equally near. `x` breaks the
    # tie, or a drag that leaves the bottom of the table always ends in its
    # first column.
    block = table_of(
        "| k | v |\n|---|---|\n| alpha bravo charlie delta | echo foxtrot golf hotel |\n",
        theme,
    )
    sized = with_columns(block, fractions=(1, 1))
    width = sp_from_px(220.0)
    cmds = shipped(sized, theme, width, measure)
    model = SelectionModel.from_commands(cmds)
    spans = columns_of(sized, theme, width, measure)
    last = max(fragment.bottom for fragment in model.fragments)
    lowest = [f for f in model.fragments if f.bottom == last and f.items]
    assert len(lowest) == 2, "both cells must end on the same line for there to be a tie"
    below = last + sp_from_px(40.0)
    left = model.fragment_at(Point(spans[0].start + sp_from_px(10.0), below))
    right = model.fragment_at(Point(spans[1].start + sp_from_px(10.0), below))
    assert left is lowest[0] and right is lowest[1]


# -- AF-livetable: a table's columns measured a row at a time ----------------------

GROWING = (
    "| key | value | note |\n|:--|--:|:-:|\n"
    "| a | 1 | short |\n"
    "| a longer key | 22.50 | several words in a cell, enough that it wraps when narrow |\n"
    "| | 3 | |\n"
    "| k | an-unbreakable-word-that-is-long | x |\n"
    "| the widest key of them all, by far | 5 | y |\n"
    "| k | 6 | z |\n"
)

MEASURE_WIDTHS = (sp_from_px(120.0), sp_from_px(300.0), sp_from_px(520.0), sp_from_px(2000.0))
"""
The longest words do not fit; the table wraps; it wraps a little; it fits and is scaled up.
"""


def _agrees(kept: ui.TableMeasure, table: TableBlock, theme: Theme, measure: Any) -> None:
    assert kept.natural(table, theme, measure) == table_natural_widths(table, theme, measure)
    for width in MEASURE_WIDTHS:
        assert kept.columns(table, theme, width, measure) == table_columns(
            table, theme, width, measure
        ), width


def test_a_table_measure_gives_the_columns_of_a_table_as_it_grows_changes_and_shrinks(
    theme: Theme, measure: Any
) -> None:
    """
    `TableMeasure` is `table_natural_widths` and `table_columns`, to the scaled point.

    Through everything a table being written does: a row added (the same row
    objects before it, as `imscribe.stream` hands them over), the last row
    replaced by another, rows taken away, the header replaced, and a
    different table given to the same measure. At four widths, one for each
    regime of `_column_widths` and one where even the longest words do not fit.
    """
    whole = table_of(GROWING, theme)
    kept = ui.TableMeasure()
    _agrees(kept, replace(whole, rows=()), theme, measure)
    for count in range(1, len(whole.rows) + 1):
        _agrees(kept, replace(whole, rows=whole.rows[:count]), theme, measure)
    # The last row changes under it: a cell still being typed.
    other = table_of("| a | b | c |\n|---|---|---|\n| typing | 1 | and then more words |\n", theme)
    for count in (2, 4, len(whole.rows)):
        _agrees(
            kept, replace(whole, rows=(*whole.rows[: count - 1], other.rows[0])), theme, measure
        )
        _agrees(kept, replace(whole, rows=whole.rows[:count]), theme, measure)
    # Cut back, then a different header, then another table altogether.
    _agrees(kept, replace(whole, rows=whole.rows[:1]), theme, measure)
    _agrees(kept, replace(whole, header=other.header), theme, measure)
    _agrees(kept, other, theme, measure)
    _agrees(kept, whole, theme, measure)
    # No header, no rows, and rows of differing lengths (a table built by hand).
    _agrees(kept, replace(whole, header=()), theme, measure)
    _agrees(kept, replace(whole, header=(), rows=()), theme, measure)
    ragged = replace(whole, rows=(whole.rows[0][:1], whole.rows[1], whole.rows[2][:2]))
    _agrees(kept, ragged, theme, measure)
    _agrees(kept, replace(ragged, header=whole.header[:2]), theme, measure)
    # A table that states its own columns is answered as `table_columns` answers it.
    _agrees(kept, with_columns(whole, fractions=(1.0, 2.0, 3.0)), theme, measure)
    _agrees(kept, with_columns(whole, widths=(700000, 900000, 1100000)), theme, measure)


def test_a_table_measure_measures_a_row_once_and_breaks_cells_only_for_a_table_that_does_not_fit(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = table_of(GROWING, theme)
    measured: list[int] = []
    broken = [0]
    real_natural, real_longest = ui._natural_widths, ui._longest_word

    def natural(rows: Any, *args: Any, **kwargs: Any) -> Any:
        measured.append(len(rows))
        return real_natural(rows, *args, **kwargs)

    def longest(*args: Any, **kwargs: Any) -> Any:
        broken[0] += 1
        return real_longest(*args, **kwargs)

    monkeypatch.setattr(ui, "_natural_widths", natural)
    monkeypatch.setattr(ui, "_longest_word", longest)
    kept = ui.TableMeasure()
    wide, narrow = MEASURE_WIDTHS[3], MEASURE_WIDTHS[1]
    for count in range(len(whole.rows) + 1):
        table = replace(whole, rows=whole.rows[:count])
        kept.natural(table, theme, measure)
        kept.columns(table, theme, wide, measure)
    # The header and each row, once each, one row to a call.
    assert measured == [1] * (1 + len(whole.rows))
    assert broken[0] == 0, "a table that fits has no cell broken to find its longest word"
    # Asked at a width it does not fit: every cell broken once, to catch up...
    kept.columns(whole, theme, narrow, measure)
    cells = 3 * (1 + len(whole.rows))
    assert broken[0] == cells and len(measured) == 1 + len(whole.rows)
    # ...and after that a new row is its own three cells and nothing else.
    extra = table_of("| a | b | c |\n|---|---|---|\n| one more | 7 | row |\n", theme).rows[0]
    kept.columns(replace(whole, rows=(*whole.rows, extra)), theme, narrow, measure)
    assert broken[0] == cells + 3 and len(measured) == 2 + len(whole.rows)
    # Asked again about the same table: nothing at all.
    kept.columns(replace(whole, rows=(*whole.rows, extra)), theme, narrow, measure)
    kept.natural(replace(whole, rows=(*whole.rows, extra)), theme, measure)
    assert broken[0] == cells + 3 and len(measured) == 2 + len(whole.rows)


def test_a_table_measure_starts_again_for_another_padding_or_another_measure(
    theme: Theme, measure: Any
) -> None:
    whole = table_of(GROWING, theme)
    kept = ui.TableMeasure()
    _agrees(kept, whole, theme, measure)
    padded = replace(theme, cell_padding=theme.cell_padding * 3)
    _agrees(kept, whole, padded, measure)
    other_measure = char_measure(fontlib_metrics)
    assert other_measure is not measure
    _agrees(kept, whole, theme, other_measure)
    tolerant = LineBreakParams(tolerance=200)
    for width in MEASURE_WIDTHS:
        assert kept.columns(whole, theme, width, measure, tolerant) == table_columns(
            whole, theme, width, measure, tolerant
        )
        assert kept.columns(whole, theme, width, measure) == table_columns(
            whole, theme, width, measure
        )

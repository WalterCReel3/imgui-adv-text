"""
Composition: the last pure step before ship-out, and the only part of the UI that runs.

`advtext.ui.compose` breaks every paragraph, hangs every list marker and sizes
every table column. It is roughly the same amount of real layout logic as the
line breaker consumes, and none of it is ImGui's, so it is testable here and it
is tested here.

**Nothing in this file opens a window.** What is asserted here is everything
that happens before a pixel would be touched. (Until tranche 5 it also held
four tests of `advtext.ui.document_view.DocumentView`'s layout cache; that view
is deleted with the old ImGui draw backend. `advtext.ui.composition` is kept as
part of the reference core the SVG litmus renderer uses.)

Widths are worked out from a fake font with round numbers, as in
`tests/test_markdown.py`, so a measure of 1000 holds exactly 100 ten-wide glyphs
and a stretched space is visible as a number rather than as an inequality.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from pathlib import Path

import pytest

import advtext.ui as ui_module
from advtext.badness import INF_BAD, badness
from advtext.fontmetrics import Face, FontMetrics, GlyphBBox
from advtext.linebreak import LineBreakParams
from advtext.markdown import TextBlock, build_document
from advtext.nodes import Box, BoxKind, CharNode, FontKey, Glue, GlueSign, GlueSpec
from advtext.pack import CharMeasure
from advtext.selection import SelectionModel
from advtext.shipout import Glyph, Line, Point, RuleRect, SetGlue, ship
from advtext.style import Align, Spacing, Theme, char_measure, fontlib_metrics, parse_font_key
from advtext.ui import (
    PROSE_BREAKING,
    PROSE_BREAKING_BOUNDED,
    PROSE_BREAKING_TOTAL_FIT_RAGGED,
    CacheStats,
    ComposeParams,
    LayoutCache,
    _theme_key,
    compose,
)
from advtext.ui.palette import DEFAULT_PALETTE, DrawStats, rgba
from advtext.units import UNITY, GlueOrder, sp_from_px

# Scaled points, not pixels: the theme's indents and sizes are in scaled points
# and a fake measuring in raw units would make every list item overfull by a
# factor of ten thousand. Ten pixels a glyph and eight a space, converted once.
GLYPH = sp_from_px(10.0)
SPACE = sp_from_px(8.0)

# Wide enough for a paragraph to break over several lines at ten pixels a glyph.
MEASURE = sp_from_px(600.0)


@dataclass(frozen=True, slots=True)
class FakeMetrics:
    """
    A `FontMetrics` with round numbers and no font behind it.

    `advance_scale` exists so a test can build a *second* measure that disagrees
    with the first about every width. `advtext.ui.LayoutCache` keys the measure
    by identity, so a second closure over the same metrics would miss for the
    wrong reason and prove nothing; this one produces a different layout.
    """

    face: Face
    size: float
    advance_scale: float = 1.0

    @property
    def ascent(self) -> float:
        return 0.8 * GLYPH

    @property
    def descent(self) -> float:
        return 0.2 * GLYPH

    @property
    def x_height(self) -> float:
        return 0.5 * GLYPH

    @property
    def em(self) -> float:
        return self.size

    @property
    def space_width(self) -> float:
        return float(SPACE)

    def has(self, codepoint: int) -> bool:
        return True

    def advance(self, codepoint: int) -> float:
        return self.advance_scale * float(SPACE if codepoint == 0x20 else GLYPH)

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(0.0, -0.2 * GLYPH, 0.9 * GLYPH, 0.7 * GLYPH)

    def kern(self, codepoint: int, following: int) -> float:
        return 0.0


def fake_resolve(key: FontKey) -> FontMetrics:
    spec = parse_font_key(key)
    return FakeMetrics(face=spec.face, size=float(spec.size))


def wide_resolve(key: FontKey) -> FontMetrics:
    """
    The same fake with every glyph half again as wide.
    """
    spec = parse_font_key(key)
    return FakeMetrics(face=spec.face, size=float(spec.size), advance_scale=1.5)


@pytest.fixture
def theme() -> Theme:
    return Theme.build()


def composed(source: str, theme: Theme, width: int = MEASURE) -> list:
    """
    A source string, composed and shipped, as a flat command list.
    """
    document = build_document(source, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    box = compose(document, theme, width, measure)
    return ship(box, Point(0, box.height), measure=measure)


def lines(cmds: list) -> list[Line]:
    return [c for c in cmds if isinstance(c, Line)]


def glyphs_on(cmds: list, line: Line) -> list[Glyph]:
    return [c for c in cmds if isinstance(c, Glyph) and line.start <= c.index < line.end]


# -- structure -----------------------------------------------------------


def test_a_composed_document_stacks_every_block_into_one_vertical_box(
    theme: Theme,
) -> None:
    source = "# Heading\n\nA paragraph.\n\n- item\n\n---\n\n```\ncode\n```\n"
    document = build_document(source, theme, fake_resolve)
    box = compose(document, theme, MEASURE, char_measure(fake_resolve))
    assert box.width == MEASURE
    assert box.height + box.depth > 0
    # One line each for the heading, the paragraph, the item and the code, and
    # not one more: a spurious blank line per block is exactly the defect that
    # duplicating section 816's terminator used to produce. The thematic break
    # is a line too, and carries no pointable material, which is why the count
    # is over the lines that have some.
    shipped = ship(box, Point(0, box.height), measure=char_measure(fake_resolve))
    assert len([line for line in lines(shipped) if line.start < line.end]) == 4


def test_a_one_line_paragraph_produces_exactly_one_line(theme: Theme) -> None:
    # The assertion that catches section 816's terminator being appended twice.
    # Nothing in tests/test_markdown.py can see it: the second line only exists
    # once the breaker has run over material that already ended in one.
    assert len(lines(composed("Short.\n", theme))) == 1


def test_blocks_are_stacked_downward_in_source_order(theme: Theme) -> None:
    cmds = composed("First para.\n\nSecond para.\n\nThird para.\n", theme)
    baselines = [line.y for line in lines(cmds)]
    assert baselines == sorted(baselines)
    assert len(set(baselines)) == len(baselines)


def test_a_wider_measure_produces_fewer_lines(theme: Theme) -> None:
    source = "One two three four five six seven eight nine ten eleven twelve thirteen.\n"
    narrow = len(lines(composed(source, theme, sp_from_px(200.0))))
    wide = len(lines(composed(source, theme, sp_from_px(900.0))))
    assert narrow > wide >= 1


# -- justification -------------------------------------------------------


def test_a_justified_paragraph_reaches_the_right_margin_on_every_line_but_the_last(
    theme: Theme,
) -> None:
    source = (
        "Justified prose has its interword glue stretched so that every line "
        "but the last reaches the right margin exactly, which is the whole "
        "reason a space is glue and not a fixed advance in this project.\n"
    )
    cmds = composed(source, theme)
    body = lines(cmds)
    assert len(body) >= 3
    for line in body[:-1]:
        last = glyphs_on(cmds, line)[-1]
        # The last glyph's advance ends on the margin. Within one glyph of the
        # measure is "on it"; a ragged line would be several glyphs short.
        assert line.width - (last.x + GLYPH) < GLYPH
    # And it got there by stretching the spaces, which is what makes it
    # justification rather than a lucky break.
    stretched = [
        glue
        for glue in cmds
        if isinstance(glue, SetGlue)
        and body[0].start <= glue.index < body[0].end
        and glue.natural > 0
        and glue.width != glue.natural
    ]
    assert stretched


def test_a_heading_is_set_ragged_right_so_none_of_its_spaces_are_stretched(
    theme: Theme,
) -> None:
    # The real difference between ragged and justified is not where a line ends
    # -- a ragged line can end anywhere up to a word short of the margin -- it is
    # whether the interword glue was stretched to get there. A rightskip of
    # 0pt plus 1fil absorbs the slack instead, so every space stays natural.
    source = "# A heading long enough that it has to break over two whole lines here\n"
    cmds = composed(source, theme, sp_from_px(320.0))
    body = lines(cmds)
    assert len(body) >= 2
    on_first_line = [
        glue
        for glue in cmds
        if isinstance(glue, SetGlue) and body[0].start <= glue.index < body[0].end
    ]
    # An interword space has a natural width; the rightskip's is zero, and it is
    # the one that is allowed to grow.
    spaces = [glue for glue in on_first_line if glue.natural > 0]
    skips = [glue for glue in on_first_line if glue.natural == 0]
    assert spaces and skips
    assert all(glue.width == glue.natural for glue in spaces)
    assert any(glue.width > 0 for glue in skips)


# -- sentence spacing ----------------------------------------------------
#
# The defect these cover was found by eye, in `demo/columns.md`, on the line
# "people guess.   Robert Bringhurst gives sixty-six characters,". The space
# after "guess." set to 23.72 px against 10.11 px either side of it. Section
# 1044 (`docs/tex.web:20373-20375`) multiplies a sentence space's *stretch* by
# the space factor, so it takes three times its neighbours' share of whatever
# a justified line was short by, and the gap grows with the stretch.
#
# So every assertion below is about the SET width of glue on a line that
# actually stretched. Natural widths cannot see the defect: at natural setting
# the ratio is only 1.33, and `tests/test_markdown.py` already pins those.

# One sentence-ending period, mid-line, with more text after it on the same
# line -- the shape the defect needs, and the shape the trap needs too: a
# fixture with no mid-line period makes "all spaces are equal" true for free.
SENTENCE_SOURCE = (
    "Reading is not a smooth glide along a line of type. The eye moves in jumps "
    "and takes in a few characters at each brief stop between them.\n"
)
# Chosen by scanning 200 px to 410 px in tens: at this one all three modes pick
# the *same* breaks, so the widths below compare on an identical line, and the
# line carrying the period is stretched rather than shrunk. Both are asserted
# rather than trusted -- see `_sentence_line` and the ratio test.
SENTENCE_MEASURE = sp_from_px(220.0)


def _sentence_line(theme: Theme) -> tuple[list[SetGlue], SetGlue]:
    """
    The interword glue of the line carrying the sentence break, and that space.

    Returns every space on the line and the one immediately after the period.
    Located by content and not by index: crops and slices that silently land in
    the wrong place are how three of this project's visual comparisons went
    wrong, so a fixture that stops containing the line raises here instead.
    """
    cmds = composed(SENTENCE_SOURCE, theme, SENTENCE_MEASURE)
    for line in lines(cmds):
        on_line = glyphs_on(cmds, line)
        text = "".join(chr(glyph.codepoint) for glyph in on_line)
        if "type.The" not in text:
            continue
        period = next(glyph for glyph in on_line if glyph.codepoint == ord("."))
        spaces = [
            glue
            for glue in cmds
            if isinstance(glue, SetGlue) and line.start <= glue.index < line.end
            # The rightskip has no natural width and is not an interword space.
            and glue.natural > 0
        ]
        # The one under test is the first glue after the period's glyph -- found
        # by index rather than counted, so a reworded fixture cannot quietly
        # point this at an ordinary space.
        after_period = next(glue for glue in spaces if glue.index > period.index)
        assert len(spaces) >= 3, spaces
        # Stretched, not shrunk. Every claim below is about how the slack on a
        # *stretched* line is shared out; on a shrunk line the arithmetic runs
        # the other way and `EXTRA_SPACE_ONLY`'s bound is 1.5 rather than 4/3.
        assert all(glue.width > glue.natural for glue in spaces), spaces
        return spaces, after_period
    raise AssertionError("no line carries 'type.The'; the fixture stopped being one")


def test_the_sentence_spacing_fixture_really_earns_a_space_factor_of_3000() -> None:
    # The meta-test. Every assertion in this section is about a space that
    # section 1034 gave a factor of 3000; drop the period from the fixture and
    # they all pass while covering nothing. This is the one that goes red.
    #
    # Checked against the unfixed path -- NONFRENCH, the faithful transcription
    # -- because that is where a factor of 3000 is visible in the glue spec, in
    # all three of the numbers section 1044 touches.
    theme = Theme.build(spacing=Spacing.NONFRENCH)
    spaces, after_period = _sentence_line(theme)
    assert after_period.natural > max(glue.natural for glue in spaces if glue is not after_period)
    block = build_document(SENTENCE_SOURCE, theme, fake_resolve).blocks[0]
    assert isinstance(block, TextBlock)
    specs = [node.spec for node in block.material if isinstance(node, Glue)]
    ordinary = specs[0]
    sentence = [spec for spec in specs if spec.stretch > ordinary.stretch]
    assert len(sentence) == 1, "exactly one space in the fixture should be a sentence space"
    # Section 1044 entire: width plus extra_space, stretch times three, shrink
    # divided by three. `xn_over_d` rounds, so the last two are within one sp.
    assert sentence[0].width == ordinary.width + round(ordinary.width / 3)
    assert sentence[0].stretch == 3 * ordinary.stretch
    assert abs(3 * sentence[0].shrink - ordinary.shrink) <= 1


def test_the_faithful_transcription_sets_a_sentence_space_twice_its_neighbours(
    theme: Theme,
) -> None:
    # The control, and the reason the two tests after it are not vacuous: they
    # would both pass on a fixture where no space was ever wide. This one fails
    # unless the defect is reproducible here.
    #
    # It is the defect the user objected to, on the fake font. Measured on
    # `demo/columns.md` with the real font at a 468 px measure the same figure
    # is 2.35; here it is 2.09, and the difference is the fake font's space
    # being 0.8 em rather than Roboto's 0.25.
    spaces, after_period = _sentence_line(Theme.build(spacing=Spacing.NONFRENCH))
    neighbours = max(glue.width for glue in spaces if glue is not after_period)
    assert after_period.width > 2 * neighbours
    # And the theme's default is not that.
    assert theme.spacing is Spacing.EXTRA_SPACE_ONLY


def test_french_spacing_sets_every_space_on_a_stretched_line_to_the_same_width() -> None:
    # `\frenchspacing`: section 1034's neutral branch always fires, so section
    # 1044 is never reached and the sentence space is an ordinary one.
    spaces, after_period = _sentence_line(Theme.build(spacing=Spacing.FRENCH))
    # Set widths, not natural: a line is justified by handing out a rounded
    # difference per glue (section 625), so two equal specs on one line can
    # still differ by a scaled point. Equal to within that, and no more.
    widths = [glue.width for glue in spaces]
    assert max(widths) - min(widths) <= 1
    assert after_period.width in widths


def test_the_default_keeps_the_wider_sentence_space_but_not_its_extra_stretch(
    theme: Theme,
) -> None:
    # `EXTRA_SPACE_ONLY`, the theme default. The sentence space keeps section
    # 1044's extra_space -- a third wider at natural setting, so the sentence
    # break is still visible -- but carries ordinary elasticity, so it takes an
    # ordinary share of the slack and the ratio does not grow with the stretch.
    spaces, after_period = _sentence_line(theme)
    neighbours = [glue for glue in spaces if glue is not after_period]
    assert after_period.natural > max(glue.natural for glue in neighbours)
    widest = max(glue.width for glue in neighbours)
    assert after_period.width > widest
    # A third wider is the most it can ever be on a stretched line, and the
    # harder the line stretches the closer to 1.0 it gets, because the sentence
    # space and its neighbours now grow by the same absolute amount.
    assert after_period.width < (4 / 3) * widest
    # The *same* absolute amount, in fact: that is the whole mechanism, and
    # asserting the difference is constant is what distinguishes this mode from
    # a merely smaller multiplier.
    grown = {glue.width - glue.natural for glue in spaces}
    assert max(grown) - min(grown) <= 1, grown


def test_the_spacing_mode_is_part_of_the_layout_cache_key(theme: Theme) -> None:
    # `_theme_key` is derived from `dataclasses.fields`, so `spacing` joins it
    # without anyone listing it -- but a cache that served a French layout to a
    # non-French document would be silent, so it is asserted rather than
    # assumed. Two themes differing in nothing else must key differently.
    other = Theme.build(spacing=Spacing.FRENCH)
    assert theme.spacing is not other.spacing
    assert _theme_key(theme) != _theme_key(other)


# -- list markers --------------------------------------------------------


def test_a_bullet_hangs_in_the_margin_and_the_text_starts_past_it(theme: Theme) -> None:
    cmds = composed("- item text\n", theme)
    drawn = glyphs_on(cmds, lines(cmds)[0])
    bullet, first_letter = drawn[0], drawn[1]
    assert bullet.codepoint == ord("•")
    assert bullet.x < first_letter.x
    # The text starts exactly at the indent; the marker lives entirely to its left.
    assert first_letter.x == theme.list_indent


def test_markers_of_different_widths_leave_every_items_text_aligned(theme: Theme) -> None:
    source = "".join(f"{n}. item\n" for n in range(1, 12))
    cmds = composed(source, theme)
    body = lines(cmds)
    assert len(body) == 11
    # "1." is two glyphs and "10." is three. The marker box absorbs the
    # difference, so every item's text still starts at the same x.
    starts = {glyphs_on(cmds, line)[-1].x for line in body}
    assert len(starts) == 1
    assert starts == {theme.list_indent + 3 * GLYPH}


def test_a_nested_list_item_starts_further_right_than_its_parent(theme: Theme) -> None:
    cmds = composed("- outer\n  - inner\n", theme)
    outer, inner = lines(cmds)[:2]
    # Compare the text, not the marker: the marker hangs left of the indent.
    assert glyphs_on(cmds, inner)[1].x == glyphs_on(cmds, outer)[1].x + theme.list_indent


# -- rules and tables ----------------------------------------------------


def test_a_thematic_break_spans_the_measure(theme: Theme) -> None:
    cmds = composed("Before.\n\n---\n\nAfter.\n", theme)
    rules = [c for c in cmds if isinstance(c, RuleRect)]
    assert len(rules) == 1
    assert rules[0].width == MEASURE
    assert rules[0].height == theme.rule_thickness


def test_every_row_of_a_table_shares_its_columns_left_edges(theme: Theme) -> None:
    # Named for what it checks. It used to be named for the columns each being as
    # wide as their widest cell, which stopped being true when `_apportioned`
    # started scaling them to the measure -- the *proportions* are still the
    # natural ones and the widths are not, and the alignment below is what the
    # assertions were always about.
    source = "| a | bbbbbbbb | c |\n|---|---|---|\n| dd | e | fff |\n"
    cmds = composed(source, theme)
    body = lines(cmds)
    assert len(body) >= 2
    header, first_row = body[0], body[-1]
    header_starts = sorted({g.x for g in glyphs_on(cmds, header)})
    row_starts = sorted({g.x for g in glyphs_on(cmds, first_row)})
    # Three columns in each, and the first cell of each row shares a left edge.
    assert header_starts[0] == row_starts[0]


def test_a_table_draws_a_rule_under_its_header(theme: Theme) -> None:
    source = "| a | b |\n|---|---|\n| c | d |\n"
    rules = [c for c in composed(source, theme) if isinstance(c, RuleRect)]
    assert len(rules) == 1
    assert rules[0].height == theme.table_rule_thickness


def test_a_tables_columns_add_up_to_the_measure_however_narrow_its_cells(
    theme: Theme,
) -> None:
    # Apportioning by natural width and scaling *down* only left the table
    # stopping short of the margin the prose beside it reaches, which reads as a
    # table that failed to lay out. Two one-letter columns is the extreme case:
    # their natural width is a fraction of the measure and the table still has to
    # fill it. The header rule is drawn at the summed column widths, so its width
    # is the measurement.
    source = "| a | b |\n|---|---|\n| c | d |\n"
    cmds = composed(source, theme)
    (rule,) = [c for c in cmds if isinstance(c, RuleRect)]
    assert rule.width == MEASURE

    # And the proportions survive: a column whose cells are eight times wider
    # than its neighbour's is still the wider column afterwards.
    wide = composed("| a | bbbbbbbb |\n|---|---|\n| c | d |\n", theme)
    (wide_rule,) = [c for c in wide if isinstance(c, RuleRect)]
    assert wide_rule.width == MEASURE
    second_column = sorted({g.x for g in glyphs_on(wide, lines(wide)[0])})[-1]
    assert second_column > MEASURE // 4


def test_a_block_quotes_bar_is_one_unbroken_rule_across_all_its_paragraphs(
    theme: Theme,
) -> None:
    # The bar needs the quote's total height, which is known only once its
    # paragraphs are broken and packed, so it is the one second pass in
    # `advtext.ui`. Two paragraphs and not one, because the obvious
    # implementation -- bar each block as it is composed -- gives two bars with a
    # gap between them and looks like a rendering glitch rather than a quote.
    cmds = composed("Before.\n\n> First quoted paragraph.\n>\n> Second one.\n\nAfter.\n", theme)
    bars = [c for c in cmds if isinstance(c, RuleRect) and c.width == theme.quote_rule_thickness]
    assert len(bars) == 1
    (bar,) = bars

    model = SelectionModel.from_commands(cmds)
    inside = [
        fragment.line
        for fragment in model.fragments
        if bar.y <= fragment.line.y - fragment.line.height
        and fragment.line.y + fragment.line.depth <= bar.y + bar.height
    ]
    # Both quoted paragraphs, and neither of the unquoted ones either side.
    assert len(inside) == 2
    assert bar.y == min(line.y - line.height for line in inside)
    assert bar.y + bar.height == max(line.y + line.depth for line in inside)
    # It sits in the margin the quote gave up, clear of the text.
    assert bar.x + bar.width <= min(line.x for line in inside)


# -- code blocks ---------------------------------------------------------


def test_a_fenced_block_keeps_one_line_per_source_line_however_wide_the_measure(
    theme: Theme,
) -> None:
    source = "```\nalpha\nbeta\ngamma\n```\n"
    assert len(lines(composed(source, theme, sp_from_px(90.0)))) == 3
    assert len(lines(composed(source, theme, sp_from_px(900.0)))) == 3


def test_a_fenced_blocks_indentation_survives_because_its_spaces_are_characters(
    theme: Theme,
) -> None:
    cmds = composed("```\nx\n    y\n```\n", theme)
    first, second = lines(cmds)[:2]
    letter = next(g for g in glyphs_on(cmds, second) if g.codepoint != 0x20)
    # Four spaces at eight pixels apiece, and not one of them stretchable: they
    # are CharNodes, so the line breaker never sees a breakpoint in them either.
    assert letter.x - glyphs_on(cmds, first)[0].x == 4 * SPACE


# -- the palette's pure parts (`advtext.ui.palette`; they were the draw backend's) --


def test_rgba_packs_bytes_the_way_im_col32_does() -> None:
    # ImGui's IM_COL32 is A B G R from the top, which is not what the name says.
    assert rgba(0xFF, 0x00, 0x00) == 0xFF0000FF
    assert rgba(0x00, 0x00, 0xFF) == 0xFFFF0000
    assert rgba(0x11, 0x22, 0x33, 0x44) == 0x44332211


def test_the_default_palette_is_opaque_ink_and_translucent_highlight() -> None:
    assert DEFAULT_PALETTE.ink >> 24 == 0xFF
    assert 0 < (DEFAULT_PALETTE.highlight >> 24) < 0xFF


def test_draw_stats_start_at_nothing_drawn() -> None:
    assert DrawStats() == DrawStats(glyphs=0, missing=0, rules=0)


# -- the per-block layout cache ------------------------------------------
#
# Every test below is about one question: can this cache ever hand back a
# layout that belongs to a different set of inputs. The five inputs
# `_block_boxes` reads are the block, the width, the theme, the break params and
# the measure, and there is one test per input that fails if the key drops it.
#
# The shape is always the same and is chosen to defeat the two-generation
# eviction: compose input A, then input B differing in one thing, through the
# *same* cache and back to back, so A is still resident when B is looked up. A
# key missing that thing returns A's boxes for B and the comparison against an
# uncached compose of B fails.


CACHE_SOURCE = (
    "# Heading\n\n"
    "One two three four five six seven eight nine ten eleven twelve thirteen.\n\n"
    "1. first item\n2. second item\n\n"
    "> A quoted paragraph that is long enough to break over more than one line.\n\n"
    "| a | bb |\n|---|---|\n| 1 | 2 |\n\n"
    "---\n\n"
    "```\nindented  code\n```\n"
)
"""
One of every block kind, so a cache test exercises all four `_block_boxes` arms.
"""


def cached_and_uncached(
    source: str,
    theme: Theme,
    cache: LayoutCache,
    measure: CharMeasure,
    width: int = MEASURE,
    params: LineBreakParams | None = None,
    resolve: Callable[[FontKey], FontMetrics] = fake_resolve,
) -> tuple[Box, Box]:
    """
    One composition done twice: through `cache`, and with no cache at all.

    The uncached box is the reference. Anything the cache does other than being
    faster shows up as an inequality between the two.

    **`measure` is a parameter and is not built here**, and that is load-bearing
    rather than tidy. `LayoutCache` keys the measure by identity, so a fresh
    `char_measure` closure per call misses on every lookup -- and a test that
    varies the width or the theme through such a helper passes whether or not
    the key carries the width or the theme. Checked by dropping each component
    of the key in turn and confirming a test goes red.
    """
    document = build_document(source, theme, resolve)
    through = compose(document, theme, width, measure, params, cache=cache)
    direct = compose(document, theme, width, measure, params)
    return through, direct


def test_a_cache_never_changes_the_composed_box(theme: Theme) -> None:
    cache = LayoutCache()
    through, direct = cached_and_uncached(CACHE_SOURCE, theme, cache, char_measure(fake_resolve))
    assert through == direct
    assert cache.stats().misses > 0


def test_a_second_compose_at_the_same_width_is_served_entirely_from_the_cache(
    theme: Theme,
) -> None:
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    first = compose(document, theme, MEASURE, measure, cache=cache)
    filled = cache.stats()
    second = compose(document, theme, MEASURE, measure, cache=cache)
    assert second == first
    assert cache.stats().misses == filled.misses
    assert cache.stats().hits == filled.misses


def test_a_cached_compose_at_a_new_width_does_not_return_the_old_widths_layout(
    theme: Theme,
) -> None:
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    narrow, _ = cached_and_uncached(CACHE_SOURCE, theme, cache, measure, width=sp_from_px(300.0))
    wide, wide_direct = cached_and_uncached(
        CACHE_SOURCE, theme, cache, measure, width=sp_from_px(900.0)
    )
    assert wide == wide_direct
    assert wide != narrow


def test_a_cached_compose_of_a_different_document_does_not_return_the_first_ones_layout(
    theme: Theme,
) -> None:
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    first, _ = cached_and_uncached("Alpha beta gamma delta.\n", theme, cache, measure)
    second, second_direct = cached_and_uncached("Epsilon zeta eta theta.\n", theme, cache, measure)
    assert second == second_direct
    assert second != first


def test_a_cached_compose_under_a_different_theme_does_not_return_the_old_themes_layout(
    theme: Theme,
) -> None:
    # marker_gap is read by `_hang_marker` alone and never reaches a `Block`, so
    # a key built from the blocks and not from the theme would miss it entirely.
    roomy = replace(theme, marker_gap=theme.marker_gap * 3)
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    tight_box, _ = cached_and_uncached("- an item\n", theme, cache, measure)
    roomy_box, roomy_direct = cached_and_uncached("- an item\n", roomy, cache, measure)
    assert roomy_box == roomy_direct
    assert roomy_box != tight_box


def test_a_cached_compose_with_different_break_params_does_not_return_the_old_params_layout(
    theme: Theme,
) -> None:
    # A par_fill_skip with no stretch makes the last line of a paragraph justify
    # to the margin like any other; the default fil leaves it short. Nothing
    # about the block or the width changes, so only the params can tell them
    # apart.
    filled = replace(PROSE_BREAKING, par_fill_skip=GlueSpec())
    source = "One two three four five six seven eight nine ten eleven twelve thirteen.\n"
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    ragged_box, _ = cached_and_uncached(source, theme, cache, measure)
    filled_box, filled_direct = cached_and_uncached(source, theme, cache, measure, params=filled)
    assert filled_box == filled_direct
    assert filled_box != ragged_box


def test_a_cached_compose_with_a_different_measure_does_not_return_the_old_measures_layout(
    theme: Theme,
) -> None:
    source = "One two three four five six seven eight nine ten eleven twelve thirteen.\n"
    cache = LayoutCache()
    narrow_glyphs, _ = cached_and_uncached(source, theme, cache, char_measure(fake_resolve))
    wide_glyphs, wide_direct = cached_and_uncached(
        source, theme, cache, char_measure(wide_resolve), resolve=wide_resolve
    )
    assert wide_glyphs == wide_direct
    assert wide_glyphs != narrow_glyphs


def test_the_theme_cache_key_covers_every_field_of_theme() -> None:
    # The key is derived from `dataclasses.fields`, so a field added to `Theme`
    # joins it automatically. This is the assertion that fails if someone
    # replaces that derivation with a hand-written list and then adds a field.
    assert len(_theme_key(Theme.build())) == len(fields(Theme))


def test_a_theme_that_is_not_hashable_still_produces_a_hashable_key(theme: Theme) -> None:
    # `Theme.blocks` is a dict, so `hash(theme)` raises and the frozen dataclass
    # cannot be a dict key on its own. That is the whole reason `_theme_key`
    # exists, and it is checked rather than assumed.
    with pytest.raises(TypeError):
        hash(theme)
    assert hash(_theme_key(theme)) == hash(_theme_key(Theme.build()))


def test_a_resize_drag_gets_no_cache_hits_at_all(theme: Theme) -> None:
    # The honest result, pinned so nobody later reads the cache as a fix for
    # resizing. Every text block is broken to a width, so every consecutive
    # width is a full reflow. `scripts/bench_reflow.py` measures the same thing
    # in milliseconds.
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    for step in range(4):
        compose(document, theme, MEASURE + step * sp_from_px(1.0), measure, cache=cache)
    assert cache.stats().hits == 0


def test_a_cache_keeps_two_generations_and_no_more(theme: Theme) -> None:
    # The residency bound. Without it a drag across a thousand pixels retains a
    # thousand broken copies of every paragraph -- a leak under exactly the
    # workload the cache cannot accelerate.
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    blocks = len(document.blocks)
    for step in range(6):
        compose(document, theme, MEASURE + step * sp_from_px(1.0), measure, cache=cache)
    assert cache.stats().entries == 2 * blocks


def test_a_width_pushed_out_by_more_measures_than_are_resident_is_re_broken(
    theme: Theme,
) -> None:
    # The retention rule stated as its own claim. `resident_passes` measures stay
    # alive; the one before them is gone and comes back only by being re-broken.
    # At the default of two, three widths is one too many. This test and
    # `test_two_consumers_at_two_measures_do_not_evict_each_other` are the two
    # halves of the same rule and neither is meaningful without the other.
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    for step in (0.0, 30.0, 60.0):
        compose(document, theme, MEASURE + sp_from_px(step), measure, cache=cache)
    before = cache.stats().hits
    compose(document, theme, MEASURE, measure, cache=cache)
    assert cache.stats().hits == before


def test_two_consumers_at_two_measures_do_not_evict_each_other(theme: Theme) -> None:
    # The defect this cache was rebuilt for. A Document tab at the page measure
    # and a Columns tab at a column measure, sharing one cache and composing turn
    # about, used to evict each other outright: every pass rotated away the
    # generation the other was about to read, so the hit count stayed at zero
    # forever. Measured on `demo/sample.md` at 420pt and 205pt that was 0 hits
    # and 272 misses over eight passes, at 163ms and 300ms a pass.
    #
    # `measure` is hoisted, and that is load-bearing for the reason
    # `cached_and_uncached` gives: a fresh closure per call misses on identity
    # and this test would pass with the fix reverted.
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    page = MEASURE
    column = MEASURE // 2
    compose(document, theme, page, measure, cache=cache)
    compose(document, theme, column, measure, cache=cache)
    filled = cache.stats()
    assert filled.hits == 0
    for _ in range(3):
        compose(document, theme, page, measure, cache=cache)
        compose(document, theme, column, measure, cache=cache)
    # Not merely "some hits": every lookup after the two filling passes is served,
    # so the steady state is six full passes of pure cache and no reflow at all.
    assert cache.stats().misses == filled.misses
    assert cache.stats().hits == 3 * filled.misses


def test_two_consumers_at_two_measures_still_get_each_others_layout_right(
    theme: Theme,
) -> None:
    # Coexisting is worthless if it is coexisting on the wrong layout. The whole
    # hazard of bucketing entries by pass key is that a lookup lands in the wrong
    # bucket, and a hit-count test cannot tell a right hit from a wrong one.
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    page = MEASURE
    column = MEASURE // 2
    compose(build_document(CACHE_SOURCE, theme, fake_resolve), theme, page, measure, cache=cache)
    compose(build_document(CACHE_SOURCE, theme, fake_resolve), theme, column, measure, cache=cache)
    wide, wide_direct = cached_and_uncached(CACHE_SOURCE, theme, cache, measure, width=page)
    narrow, narrow_direct = cached_and_uncached(CACHE_SOURCE, theme, cache, measure, width=column)
    assert cache.stats().hits > 0
    assert wide == wide_direct
    assert narrow == narrow_direct
    assert wide != narrow


def test_the_measure_evicted_is_the_least_recently_used_and_not_the_oldest(
    theme: Theme,
) -> None:
    # A columns view toggling 2, 3, 2, 3 and occasionally 1 should keep the two it
    # keeps returning to. Insertion order would keep the first two seen instead
    # and throw away the one in constant use, so this is the assertion that a
    # `dict` used as an LRU is actually being re-inserted on every pass.
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    kept = MEASURE
    stale = MEASURE + sp_from_px(30.0)
    fresh = MEASURE + sp_from_px(60.0)
    compose(document, theme, kept, measure, cache=cache)
    compose(document, theme, stale, measure, cache=cache)
    compose(document, theme, kept, measure, cache=cache)
    compose(document, theme, fresh, measure, cache=cache)
    before = cache.stats().hits
    compose(document, theme, kept, measure, cache=cache)
    assert cache.stats().hits > before


def test_a_cache_with_room_for_three_measures_serves_a_three_way_toggle(
    theme: Theme,
) -> None:
    # What a 1/2/3-column control needs, and the reason `resident_passes` is a
    # parameter rather than the constant two it replaced.
    cache = LayoutCache(resident_passes=3)
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    widths = [MEASURE, MEASURE + sp_from_px(30.0), MEASURE + sp_from_px(60.0)]
    for width in widths:
        compose(document, theme, width, measure, cache=cache)
    filled = cache.stats()
    for width in widths:
        compose(document, theme, width, measure, cache=cache)
    assert cache.stats().misses == filled.misses
    assert cache.stats().hits == filled.misses


def test_a_cache_with_room_for_three_measures_holds_three_documents_worth(
    theme: Theme,
) -> None:
    # The other side of that: asking for a third resident measure costs a third
    # document's worth of boxes, and the bound is still a bound.
    cache = LayoutCache(resident_passes=3)
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    for step in range(6):
        compose(document, theme, MEASURE + step * sp_from_px(1.0), measure, cache=cache)
    assert cache.stats().entries == 3 * len(document.blocks)


def test_a_cache_with_no_room_for_any_measure_is_refused() -> None:
    # Zero would be a cache that does every lookup and answers none of them, and
    # the symptom of that is a frame rate rather than an exception.
    with pytest.raises(ValueError, match="at least 1"):
        LayoutCache(resident_passes=0)


def test_a_block_that_leaves_the_document_is_dropped_within_one_further_pass(
    theme: Theme,
) -> None:
    # Bounding the *number* of generations is not enough if one generation can
    # grow without limit. A block that is no longer in the document survives one
    # more pass at its measure -- it was used by the pass before -- and then goes.
    # Without that, an editor re-composing at one unchanged width accumulates
    # every version of every paragraph it has ever shown.
    cache = LayoutCache()
    measure = char_measure(fake_resolve)
    long = build_document("Alpha beta.\n\nGamma delta.\n\nEpsilon zeta.\n", theme, fake_resolve)
    short = build_document("Alpha beta.\n", theme, fake_resolve)
    compose(long, theme, MEASURE, measure, cache=cache)
    assert cache.stats().entries == 3
    compose(short, theme, MEASURE, measure, cache=cache)
    assert cache.stats().entries == 3
    compose(short, theme, MEASURE, measure, cache=cache)
    assert cache.stats().entries == 1


def test_clearing_a_cache_forgets_everything(theme: Theme) -> None:
    cache = LayoutCache()
    document = build_document(CACHE_SOURCE, theme, fake_resolve)
    measure = char_measure(fake_resolve)
    compose(document, theme, MEASURE, measure, cache=cache)
    cache.clear()
    assert cache.stats() == CacheStats(hits=0, misses=0, entries=0)
    compose(document, theme, MEASURE, measure, cache=cache)
    assert cache.stats().hits == 0


def test_two_identical_paragraphs_share_a_cache_entry_and_still_stack(theme: Theme) -> None:
    # Two equal blocks produce one key. They therefore share the very same `Box`
    # objects, which is safe only because a box is frozen and ship-out places it
    # by where it sits in the vertical list rather than by identity. A regression
    # here would put the second paragraph on top of the first.
    cache = LayoutCache()
    document = build_document("Same words here.\n\nSame words here.\n", theme, fake_resolve)
    measure = char_measure(fake_resolve)
    box = compose(document, theme, MEASURE, measure, cache=cache)
    baselines = [line.y for line in lines(ship(box, Point(0, box.height), measure=measure))]
    assert len(baselines) == 2
    assert baselines[0] < baselines[1]
    assert cache.stats().misses == 1
    assert cache.stats().hits == 1


# -- the breaking tolerance ----------------------------------------------
#
# `advtext.ui.PROSE_BREAKING` is the one parameter in this project that is a
# judgement about how a page should look. What is *not* a judgement is that the
# parameter should mean what it says. `tolerance` is the maximum badness the
# breaker will accept on a line -- and while `PROSE_BREAKING` carried
# `\emergencystretch` it bounded nothing at all, because §828 grants the extra
# stretchability to the breaker's *scoring* and `advtext.linebreak._assemble`
# packs the winner without it. A line admitted as "badness under 1000" came out
# set at a measured badness of 10000.
#
# These run against the real demo documents and the real fonts rather than
# against this file's fake, and that is deliberate: the claim is about ordinary
# English prose at ordinary measures, and a fake font with ten-pixel glyphs and
# invented words is not evidence for it. `tests/test_litmus.py` takes the same
# fixture for the same reason.

TOLERANCE_DOCUMENTS = ("columns.md", "sample.md")

# Measures spanning the regime this demo actually reaches: 300px is well below
# the project's own two-alphabet floor (the starved three-column case), 440px
# and 560px sit either side of `document_view.page_for`'s 468.75px.
TOLERANCE_MEASURES = tuple(sp_from_px(float(px)) for px in (300, 440, 560))

# The two measures this project sets by rule, and the only two where "no
# overfull line" is a requirement rather than an aspiration:
# `scripts/render_litmus.py`'s 420pt, and `page_for`'s 2.25 alphabets.
RULED_MEASURES = (420 * UNITY, sp_from_px(468.75))

_COMPOSED: dict[tuple[str, LineBreakParams, int], Box] = {}


def _hboxes(box: Box) -> list[Box]:
    """
    Every horizontal box in a composed tree, innermost included.
    """
    found: list[Box] = []
    stack = [box]
    while stack:
        current = stack.pop()
        for node in current.contents:
            if isinstance(node, Box):
                stack.append(node)
        if current.kind is BoxKind.HLIST:
            found.append(current)
    return found


def _finitely_stretched(box: Box) -> list[Box]:
    """
    The hboxes whose glue was set by stretching *finite* glue.

    The filter on `glue_order` is load-bearing and not defensive. A paragraph's
    last line carries `\\parfillskip`, a ragged line and a hanging marker carry a
    `fil` rightskip, and all three have a `glue_set` in the millions that means
    "infinite glue absorbed the slack", not "these spaces are enormous". A first
    draft of this test counted them and concluded, wrongly and confidently, that
    no setting could improve on any other.
    """
    return [
        b
        for b in _hboxes(box)
        if b.glue_sign is GlueSign.STRETCHING and b.glue_order is GlueOrder.NORMAL
    ]


def _overfull(box: Box) -> list[Box]:
    """
    The hboxes that stick out past their own width: §666's black rule, as state.

    `advtext.pack._set_glue` returns `glue_set` of exactly `1.0` with a shrinking
    sign when the overflow is *not* distributed, so this triple is the packer's
    own overfull flag read back off the box. `PackResult.fitness` says it more
    directly and `compose` does not return one.
    """
    return [
        b
        for b in _hboxes(box)
        if b.glue_sign is GlueSign.SHRINKING
        and b.glue_order is GlueOrder.NORMAL
        and b.glue_set >= 1.0
    ]


def _compose_demo(name: str, theme: Theme, params: LineBreakParams, width: int) -> Box:
    """
    One demo document composed at one measure, memoised: each costs ~250ms of real fonts.
    """
    key = (name, params, width)
    if key not in _COMPOSED:
        source = (Path(__file__).resolve().parent.parent / "demo" / name).read_text(
            encoding="utf-8"
        )
        document = build_document(source, theme, fontlib_metrics)
        _COMPOSED[key] = compose(document, theme, width, char_measure(fontlib_metrics), params)
    return _COMPOSED[key]


def _worst_badness(theme: Theme, params: LineBreakParams) -> int:
    """
    The badness the packer's own `glue_set` implies, worst over the sweep.

    `advtext.badness.badness` depends only on the ratio of what had to be made up
    to what was available, and `glue_set` *is* that ratio (`advtext.nodes.Box`).
    Going through the project's §108 transcription rather than through
    `100 * ratio ** 3` keeps the test and the breaker on one arithmetic: the
    integer approximation and the textbook cube disagree by a few units either
    side of the fitness-class boundaries, which is exactly the range this asserts
    in.
    """
    return max(
        badness(round(line.glue_set * UNITY), UNITY)
        for name in TOLERANCE_DOCUMENTS
        for width in TOLERANCE_MEASURES
        for line in _finitely_stretched(_compose_demo(name, theme, params, width))
    )


def _overfull_lines_at_the_ruled_measures(theme: Theme, params: LineBreakParams) -> int:
    return sum(
        len(_overfull(_compose_demo(name, theme, params, width)))
        for name in TOLERANCE_DOCUMENTS
        for width in RULED_MEASURES
    )


def test_prose_breaking_does_not_bound_how_loose_a_line_can_be(
    bundled_fonts: Path, theme: Theme
) -> None:
    # **This asserts a defect, deliberately.** `tolerance` is the largest
    # badness the breaker will accept on a line, and while `\emergencystretch`
    # is in `PROSE_BREAKING` the packed line can be arbitrarily worse than that:
    # §828 grants the stretch to the scoring and `advtext.linebreak._assemble`
    # packs without it. Over the two demo documents the shipped setting reaches
    # `INF_BAD` -- ten times its own declared 1000.
    #
    # It is asserted rather than merely written down because the number is the
    # whole case for changing the setting, and a number in a docstring rots. The
    # day someone takes the emergency stretch out, this goes red and sends them
    # to `PROSE_BREAKING`'s docstring, which says what the swap costs and which
    # of the tests below already measure it.
    assert PROSE_BREAKING.emergency_stretch > 0
    worst = _worst_badness(theme, PROSE_BREAKING)
    assert worst == INF_BAD
    assert worst >= 10 * PROSE_BREAKING.tolerance


def test_taking_the_emergency_stretch_out_restores_the_bound_it_is_named_for(
    bundled_fonts: Path, theme: Theme
) -> None:
    # The other half, and the reason the test above is a finding and not a
    # shrug: with `emergency_stretch` at zero the line the breaker scored is the
    # line the packer emits, so `tolerance` becomes a real ceiling. Same
    # documents, same measures, same arithmetic -- only the setting differs.
    assert PROSE_BREAKING_BOUNDED.emergency_stretch == 0
    worst = _worst_badness(theme, PROSE_BREAKING_BOUNDED)
    assert worst <= PROSE_BREAKING_BOUNDED.tolerance

    # And the fixture has to *reach* for the ceiling, or the line above is an
    # assertion about nothing. `demo/columns.md` at the 300px measure lands at
    # 5893 of the 6000 allowed; dropping that document, or narrowing the sweep
    # to comfortable measures, leaves the worst at 4582 and this goes red. The
    # cost of saying it this way is that rewriting the demo prose can move the
    # number -- which is worth being told about, not a flake.
    assert worst > 0.85 * PROSE_BREAKING_BOUNDED.tolerance


def test_the_bounded_setting_is_the_loosest_line_this_project_would_accept(
    bundled_fonts: Path, theme: Theme
) -> None:
    # Why 6000 and not a rounder number. Overfull is the worse failure
    # (`docs/status.md` section 4), so the tolerance cannot be tightened until
    # the loose lines go away -- only until text reaches the margin, and 6000 is
    # where that happens. One notch below it `demo/sample.md` puts a line in the
    # margin at the litmus measure. Taking the notch from the constant rather
    # than writing 5900 here is what makes *raising* the tolerance go red too,
    # so the number is pinned from both sides and is a measurement rather than a
    # preference.
    one_notch_below = replace(
        PROSE_BREAKING_BOUNDED, tolerance=PROSE_BREAKING_BOUNDED.tolerance - 100
    )
    assert _overfull_lines_at_the_ruled_measures(theme, PROSE_BREAKING_BOUNDED) == 0
    assert _overfull_lines_at_the_ruled_measures(theme, one_notch_below) > 0


def test_the_bounded_setting_costs_the_column_document_a_line_in_the_margin(
    bundled_fonts: Path, theme: Theme
) -> None:
    # The price, as an executable fact rather than a paragraph, because it is
    # the only reason `PROSE_BREAKING_BOUNDED` is not simply `PROSE_BREAKING`.
    # At the measure the three-column tab actually sets -- 399.5px, instrumented
    # out of the running app, and 1.92 alphabets against this project's own 2.00
    # floor -- the bounded setting puts one line of `demo/columns.md` past the
    # column edge and the shipped one does not.
    # `tests/test_demo_content.py` asserts that document ships no glyph outside
    # a column, so this is exactly what the swap would break, and whoever makes
    # it should re-measure here first. The band is narrow: columns.md is clean
    # under the bounded setting at 390, 395 and 415-480px.
    three_column = sp_from_px(399.5)
    assert _overfull(_compose_demo("columns.md", theme, PROSE_BREAKING, three_column)) == []
    assert _overfull(_compose_demo("columns.md", theme, PROSE_BREAKING_BOUNDED, three_column)) != []


# -- non-justified blocks are broken first-fit, at natural spacing ---------
#
# Decision 13 in `.concerns/lead--adoption-tasks.md`, wired in
# `advtext.ui._text_boxes`. What changed is a statement about *which lines are
# produced*, and each test below either compares the two paths or pins one of
# the measured reasons for preferring one. None of them says which looks better.


def _ragged(theme: Theme) -> Theme:
    """
    `theme` with every block `Align.LEFT`, which is what a ragged host theme is.
    """
    return replace(
        theme,
        blocks={kind: replace(style, align=Align.LEFT) for kind, style in theme.blocks.items()},
    )


def _compressed(box: Box) -> bool:
    """
    Whether any line inside `box` was set with its glue shrunk.

    Recursive because a list item's first line is re-wrapped by `_hang_marker`
    and the box that was actually set tight is one level down.
    """
    if box.kind is BoxKind.HLIST and box.glue_sign is GlueSign.SHRINKING and box.glue_set > 0:
        return True
    return any(_compressed(node) for node in box.contents if isinstance(node, Box))


def _characters(box: Box) -> int:
    """
    How many characters a line box holds, at any depth.
    """
    return sum(
        _characters(node) if isinstance(node, Box) else isinstance(node, CharNode)
        for node in box.contents
    )


def test_only_a_block_that_is_not_justified_is_broken_first_fit(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[tuple, LineBreakParams]] = []
    real = ui_module.break_paragraph

    def spy(material: tuple, shape: object, params: LineBreakParams, **kwargs: object) -> object:
        seen.append((material, params))
        return real(material, shape, params, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ui_module, "break_paragraph", spy)
    document = build_document("# A heading here\n\nA paragraph here.\n", theme, fake_resolve)
    compose(document, theme, MEASURE, char_measure(fake_resolve))
    (heading_material, heading_params), (body_material, body_params) = seen
    heading, body = document.blocks
    assert isinstance(heading, TextBlock) and isinstance(body, TextBlock)

    # The heading is ragged: first-fit, and handed nothing that can shrink.
    assert heading_params.first_fit
    glues = [node for node in heading_material if isinstance(node, Glue)]
    assert glues and all(glue.spec.shrink == 0 for glue in glues)
    assert any(
        isinstance(n, Glue) and n.spec.shrink for n in heading.material
    ), "the fixture's glue must have had shrink to remove"
    # The paragraph is justified: the optimiser, and its material untouched.
    assert not body_params.first_fit
    assert body_material is body.material


def test_asking_for_total_fit_ragged_gets_the_path_every_block_used_to_take(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[tuple, LineBreakParams]] = []
    real = ui_module.break_paragraph

    def spy(material: tuple, shape: object, params: LineBreakParams, **kwargs: object) -> object:
        seen.append((material, params))
        return real(material, shape, params, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ui_module, "break_paragraph", spy)
    ragged = _ragged(theme)
    document = build_document(
        "Enough words in a row that the line has to be broken somewhere.\n", ragged, fake_resolve
    )
    (block,) = document.blocks
    assert isinstance(block, TextBlock)
    measure = char_measure(fake_resolve)
    width = sp_from_px(200.0)
    old = compose(document, ragged, width, measure, PROSE_BREAKING_TOTAL_FIT_RAGGED)
    ((material, params),) = seen
    # The material as emitted, the optimiser, and the same skips as before.
    assert material is block.material
    assert not params.first_fit
    assert params == ui_module._skips(Align.LEFT, PROSE_BREAKING_TOTAL_FIT_RAGGED)
    # And the constant is `PROSE_BREAKING` in everything but the one switch.
    for spec in fields(LineBreakParams):
        assert getattr(PROSE_BREAKING_TOTAL_FIT_RAGGED, spec.name) == getattr(
            PROSE_BREAKING, spec.name
        )
    assert isinstance(PROSE_BREAKING_TOTAL_FIT_RAGGED, ComposeParams)

    # One cache serves both without confusing them: the params are in the key.
    cache = LayoutCache()
    new = compose(document, ragged, width, measure, cache=cache)
    assert (
        compose(document, ragged, width, measure, PROSE_BREAKING_TOTAL_FIT_RAGGED, cache=cache)
        == old
    )
    assert compose(document, ragged, width, measure, cache=cache) == new


def test_a_ragged_line_is_never_compressed_and_the_optimiser_used_to_compress_some(
    bundled_fonts: Path, theme: Theme
) -> None:
    # The measured difference between the two paths, on the demo document set
    # ragged at the demo page's measure: the optimiser sets some ragged lines
    # with their spaces shrunk, and so fits a word that natural spacing puts
    # on the next line. The search is for the first short block where it did,
    # so the test does not depend on a block number and cannot pass on a
    # document where the two paths agree everywhere.
    ragged = _ragged(theme)
    source = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(
        encoding="utf-8"
    )
    measure = char_measure(fontlib_metrics)
    width = sp_from_px(467.0)
    found = 0
    for block in build_document(source, ragged, fontlib_metrics).blocks:
        # Short blocks only: the optimiser's ragged cost is why this path exists.
        if not isinstance(block, TextBlock) or len(block.material) > 100:
            continue
        before = ui_module._text_boxes(
            block, ragged, width, measure, PROSE_BREAKING_TOTAL_FIT_RAGGED
        )
        after = ui_module._text_boxes(block, ragged, width, measure, PROSE_BREAKING)
        assert not any(_compressed(line) for line in after)
        if any(_compressed(line) for line in before):
            found += 1
            # A compressed line held a word that natural spacing moves down.
            assert [_characters(line) for line in before] != [_characters(line) for line in after]
    assert found >= 1, "no short block of the sample is compressed by the optimiser any more"


def test_the_default_themes_demo_document_did_not_move(bundled_fonts: Path, theme: Theme) -> None:
    # In the default theme only headings are not justified, and at the measures
    # the demo and the litmus render use every heading is one line. One line is
    # one line under either breaker, so the shipped commands are identical.
    # This is the assertion that the change of breaker did not alter the demo.
    measure = char_measure(fontlib_metrics)
    for width in (sp_from_px(467.0), sp_from_px(558.0)):
        new = _compose_demo("sample.md", theme, PROSE_BREAKING, width)
        old = _compose_demo("sample.md", theme, PROSE_BREAKING_TOTAL_FIT_RAGGED, width)
        assert ship(new, Point(0, new.height), measure=measure) == ship(
            old, Point(0, old.height), measure=measure
        )


def test_a_word_wider_than_the_measure_no_longer_unsets_the_words_before_it(
    theme: Theme,
) -> None:
    # The other measured reason. Ahead of a word that cannot fit, the
    # optimiser's last-resort break comes from the chain with the most lines:
    # every earlier word on a line of its own. First-fit fills the lines before
    # the wide word as if it were not there.
    ragged = _ragged(theme)
    source = "aa bb cc dd ee ff " + "W" * 40 + " gg hh\n"
    document = build_document(source, ragged, fake_resolve)
    measure = char_measure(fake_resolve)
    width = sp_from_px(200.0)

    def words_per_line(params: LineBreakParams) -> list[int]:
        box = compose(document, ragged, width, measure, params)
        cmds = ship(box, Point(0, box.height), measure=measure)
        model = SelectionModel.from_commands(cmds)
        return [len(model.text(model.select(f.start, f.end)).split()) for f in model.fragments]

    assert words_per_line(PROSE_BREAKING) == [6, 1, 2]
    assert words_per_line(PROSE_BREAKING_TOTAL_FIT_RAGGED) == [1, 1, 1, 1, 1, 1, 1, 2]

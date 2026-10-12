"""
The converter and the theme, measured against a fake font with round numbers.

**No test here opens a real font.** Every expected width in this file was worked
out by hand from `FakeMetrics`, whose advances are 10 and whose space is 8, and
that is the whole reason the metrics interface is a Protocol: a test that
measured Roboto could assert that a space is glue but could not assert that the
glue is 8 wide with 4 of stretch and 3 of shrink, which is the claim that would
actually catch the space-factor arithmetic going wrong.

`tests/test_fontmetrics.py` is where real fonts are exercised. The two suites
meet at `advtext.style.MetricsResolver`, and a fake that satisfies it here while
`fontlib` satisfies it there is the evidence that the seam is real.

Deliberately not here: anything that packs, breaks or positions. This module
produces unpacked material and the tests assert its shape, never its geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from advtext.fontmetrics import Face, FontMetrics, GlyphBBox
from advtext.linebreak import LineBreakParams, ParShape, break_paragraph
from advtext.markdown import (
    PARFILLSKIP,
    REPLACEMENT_CHARACTER,
    BlockSource,
    CodeBlock,
    ColumnAlign,
    Document,
    RuleBlock,
    SourceSpan,
    TableBlock,
    TextBlock,
    _convert,
    _leading_fence,
    _line_starts,
    _opens,
    _resume_point,
    _tokens,
    build_document,
    code_block,
    replaced_characters,
    text_block,
)
from advtext.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    CharNode,
    FontKey,
    Glue,
    Kern,
    KernKind,
    Node,
    Penalty,
)
from advtext.style import (
    Align,
    BlockKind,
    Emphasis,
    Spacing,
    Theme,
    char_measure,
    font_key,
    interword_glue,
    parse_font_key,
    space_factor_after,
)

# Chosen so every expected number below can be done in the head: a glyph is 10
# wide, a space is 8, and the only kerned pair is "To".
GLYPH_ADVANCE = 10.0
SPACE_ADVANCE = 8.0
KERNED_PAIR = (ord("T"), ord("o"))
KERN_VALUE = -2.0


@dataclass(frozen=True, slots=True)
class FakeMetrics:
    """
    A `FontMetrics` with no font behind it.

    Structural typing is what makes this possible: it inherits nothing, imports
    no fontTools, and satisfies the protocol by having the right members.
    """

    face: Face
    size: float

    @property
    def ascent(self) -> float:
        return 8.0

    @property
    def descent(self) -> float:
        return 2.0

    @property
    def x_height(self) -> float:
        return 5.0

    @property
    def em(self) -> float:
        return self.size

    @property
    def space_width(self) -> float:
        return SPACE_ADVANCE

    def has(self, codepoint: int) -> bool:
        return True

    def advance(self, codepoint: int) -> float:
        return SPACE_ADVANCE if codepoint == 0x20 else GLYPH_ADVANCE

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(x_min=0.0, y_min=-2.0, x_max=9.0, y_max=7.0)

    def kern(self, codepoint: int, following: int) -> float:
        return KERN_VALUE if (codepoint, following) == KERNED_PAIR else 0.0


def fake_resolve(key: FontKey) -> FontMetrics:
    """
    The test suite's `MetricsResolver`: a key in, a fake face out.
    """
    spec = parse_font_key(key)
    return FakeMetrics(face=spec.face, size=float(spec.size))


@pytest.fixture
def theme() -> Theme:
    return Theme.build()


def convert(source: str, theme: Theme) -> Document:
    return build_document(source, theme, fake_resolve)


def faces(nodes: tuple[Node, ...]) -> list[Face]:
    return [parse_font_key(n.font).face for n in nodes if isinstance(n, CharNode)]


def text_of(nodes: tuple[Node, ...]) -> str:
    return "".join(chr(n.codepoint) for n in nodes if isinstance(n, CharNode))


def face_by_letter(nodes: tuple[Node, ...]) -> dict[str, Face]:
    """
    Which face each distinct letter was set in. Only useful where every letter
    the test asserts on occurs once, which is why those sources spell out one
    letter per style.
    """
    return dict(zip(text_of(nodes), faces(nodes), strict=True))


def glues(nodes: tuple[Node, ...]) -> list[Glue]:
    return [n for n in nodes if isinstance(n, Glue)]


# -- the shape of a document ---------------------------------------------


def test_the_litmus_documents_block_kinds_each_produce_their_own_block(theme: Theme) -> None:
    source = (
        "# One\n\n## Two\n\n### Three\n\nA paragraph.\n\n"
        "- bullet\n\n1. ordered\n\n> quoted\n\n```py\nx = 1\n```\n\n---\n\n"
        "| a | b |\n|---|---|\n| c | d |\n"
    )
    blocks = convert(source, theme).blocks
    kinds = [b.kind for b in blocks if isinstance(b, TextBlock)]
    assert kinds == [
        BlockKind.HEADING_1,
        BlockKind.HEADING_2,
        BlockKind.HEADING_3,
        BlockKind.PARAGRAPH,
        BlockKind.BULLET_ITEM,
        BlockKind.ORDERED_ITEM,
        BlockKind.QUOTE,
    ]
    assert any(isinstance(b, CodeBlock) for b in blocks)
    assert any(isinstance(b, RuleBlock) for b in blocks)
    assert any(isinstance(b, TableBlock) for b in blocks)


def test_every_heading_level_is_its_own_kind(theme: Theme) -> None:
    """
    Six levels in, six kinds out, each set in its own style.

    This test used to be `test_a_heading_deeper_than_level_three_is_set_as_level_
    three` and asserted that `#####` came out as `HEADING_3`. That was the
    behaviour and it is the behaviour that was asked to change: levels four to
    six collapsed into one, so a section and its sub-sub-section were set alike.
    What the old test was guarding against still holds and is the last line --
    no level falls through to body text.
    """
    source = "".join(f"{'#' * level} Level {level}\n\n" for level in range(1, 7))
    blocks = convert(source, theme).blocks
    assert [block.kind for block in blocks if isinstance(block, TextBlock)] == [
        BlockKind.HEADING_1,
        BlockKind.HEADING_2,
        BlockKind.HEADING_3,
        BlockKind.HEADING_4,
        BlockKind.HEADING_5,
        BlockKind.HEADING_6,
    ]
    styles = [block.style for block in blocks]
    assert all(one != other for index, one in enumerate(styles) for other in styles[index + 1 :])
    assert all(block.style == theme.style(block.kind) for block in blocks)  # type: ignore[union-attr]
    assert BlockKind.PARAGRAPH not in {block.kind for block in blocks}  # type: ignore[union-attr]


def test_a_text_block_leaves_section_816s_terminator_to_the_line_breaker(
    theme: Theme,
) -> None:
    # Section 816 lives in line_break, not in the code that builds the horizontal
    # list: advtext.linebreak._prepare replaces a trailing glue with an infinite
    # penalty and appends \\parfillskip itself. Emitting one here too leaves the
    # breaker a parfillskip after the forced break it already took, and every
    # block comes out with a blank line under it. tests/test_compose.py has the
    # assertion that catches the duplicate, because it needs the breaker to run.
    for block in convert("Hello there world.\n\n- item\n", theme).blocks:
        assert isinstance(block, TextBlock)
        assert not isinstance(block.material[-1], Penalty)
        assert isinstance(block.material[-1], CharNode)


def test_a_hard_break_still_fills_the_line_and_cuts_it(theme: Theme) -> None:
    # The one place those three nodes are still this module's to emit: a hard
    # break is mid-paragraph, so nothing else would produce it.
    block = convert("first line  \nsecond line\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    penalties = [n for n in block.material if isinstance(n, Penalty)]
    assert any(p.forbids_break for p in penalties)
    assert any(p.forces_break for p in penalties)


# -- spaces are glue -----------------------------------------------------


def test_an_interword_space_is_glue_with_stretch_and_shrink_not_a_character(
    theme: Theme,
) -> None:
    block = convert("one two\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert 0x20 not in [n.codepoint for n in block.material if isinstance(n, CharNode)]
    spec = glues(block.material)[0].spec
    # 8 wide, half of that in stretch, a third in shrink: cmr10's own ratios.
    assert (spec.width, spec.stretch, spec.shrink) == (8, 4, 3)


def test_a_run_of_spaces_collapses_so_that_no_two_glues_are_ever_adjacent(
    theme: Theme,
) -> None:
    # Two adjacent glues would offer a breakpoint between them, and the break
    # would leave a space at the head of the next line.
    block = convert("one     two   three\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    material = block.material
    assert not any(
        isinstance(a, Glue) and isinstance(b, Glue)
        for a, b in zip(material, material[1:], strict=False)
    )
    # Exactly two: one per collapsed run. The paragraph's \\parfillskip is the
    # line breaker's to append, not this module's.
    assert len(glues(material)) == 2


def test_a_sentence_ending_period_widens_the_space_that_follows_it() -> None:
    # Space factor 3000: width plus extra_space, stretch tripled, shrink cut to
    # a third (section 1044). 8 -> 11 wide, 4 -> 12 stretch, 3 -> 1 shrink.
    #
    # Explicitly NONFRENCH rather than the `theme` fixture: the default theme
    # now sets `Spacing.EXTRA_SPACE_ONLY`, which keeps the width and drops the
    # elasticity scaling. This test is the transcription's coverage and has to
    # go on asserting all three of section 1044's effects, so it asks for the
    # mode that applies them. `tests/test_compose.py` covers the other two.
    theme = Theme.build(spacing=Spacing.NONFRENCH)
    block = convert("one ends. next\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    after_period = glues(block.material)[1].spec
    assert (after_period.width, after_period.stretch, after_period.shrink) == (11, 12, 1)


def test_a_period_after_a_capital_does_not_widen_the_space(theme: Theme) -> None:
    # Section 1034's rule that makes the space factor usable: an uppercase letter
    # sets it to 999, and a period then raises it only to 1000, so an initialism
    # at the end of a clause does not earn a sentence space.
    block = convert("built by NASA. next\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    after_period = glues(block.material)[2].spec
    assert (after_period.width, after_period.stretch, after_period.shrink) == (8, 4, 3)


def test_the_space_factor_rule_is_the_sources_four_branches(theme: Theme) -> None:
    assert space_factor_after("a") == 1000
    assert space_factor_after("A") == 999
    assert space_factor_after(".") == 3000
    assert space_factor_after(".", current=999) == 1000
    # A closing mark is transparent: it leaves whatever the character before set.
    assert space_factor_after('"', current=3000) == 3000


# -- emphasis and faces --------------------------------------------------


def test_emphasis_selects_the_face_that_matches_it(theme: Theme) -> None:
    # One letter per style, all distinct, so the lookup below cannot be shadowed
    # by a second occurrence in a different face.
    block = convert("p *q* **r** ***s*** t\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    by_face = face_by_letter(block.material)
    assert by_face["p"] is Face.PROSE
    assert by_face["q"] is Face.PROSE_ITALIC
    assert by_face["r"] is Face.PROSE_BOLD
    assert by_face["s"] is Face.PROSE_BOLD_ITALIC
    assert by_face["t"] is Face.PROSE


def test_bold_italic_is_a_real_fourth_face_and_not_a_synthesis(theme: Theme) -> None:
    block = convert("***both***\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert set(faces(block.material)) == {Face.PROSE_BOLD_ITALIC}


def test_italic_inside_a_heading_is_bold_italic_not_a_drop_to_regular(theme: Theme) -> None:
    block = convert("# a *b*\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    by_face = face_by_letter(block.material)
    assert by_face["a"] is Face.PROSE_BOLD
    assert by_face["b"] is Face.PROSE_BOLD_ITALIC


def test_inline_code_uses_the_monospace_face(theme: Theme) -> None:
    block = convert("call `f(x)` now\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    by_face = face_by_letter(block.material)
    assert by_face["f"] is Face.CODE
    assert by_face["n"] is Face.PROSE


def test_a_space_inside_inline_code_is_preceded_by_a_penalty_that_forbids_the_break(
    theme: Theme,
) -> None:
    block = convert("run `git push` now\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    material = block.material
    space = next(
        i
        for i, n in enumerate(material)
        if isinstance(n, Glue) and isinstance(material[i - 1], Penalty)
    )
    before = material[space - 1]
    assert isinstance(before, Penalty) and before.forbids_break


def test_underscore_emphasis_does_not_fire_inside_a_dunder_name(theme: Theme) -> None:
    # CommonMark's intraword rule protects foo_bar_baz and not __init__, whose
    # underscore runs sit at word boundaries. A typography demo about a Python
    # project must not render __init__ in bold.
    block = convert("the __init__ method\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert text_of(block.material) == "the__init__method"
    assert set(faces(block.material)) == {Face.PROSE}


def test_asterisk_emphasis_still_fires_after_the_underscore_override(theme: Theme) -> None:
    block = convert("the *real* thing\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert Face.PROSE_ITALIC in faces(block.material)


# -- kerning -------------------------------------------------------------


def test_a_kern_node_is_inserted_where_the_metrics_report_one(theme: Theme) -> None:
    block = convert("To\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    kerns = [n for n in block.material if isinstance(n, Kern)]
    assert [(k.width, k.kind) for k in kerns] == [(-2, KernKind.NORMAL)]


def test_no_kern_crosses_an_emphasis_boundary(theme: Theme) -> None:
    # The two glyphs are set in different faces, so there is no pair to kern --
    # which is also what TeX does, since a kern comes from one font's table.
    block = convert("T*o*\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert not [n for n in block.material if isinstance(n, Kern)]


def test_font_kerns_are_normal_so_they_are_not_legal_breakpoints(theme: Theme) -> None:
    # A break at a kern needs KernKind.EXPLICIT and a following glue, so marking
    # these NORMAL is what keeps a word from breaking at its own kern.
    block = convert("To and Tomorrow\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert all(n.kind is KernKind.NORMAL for n in block.material if isinstance(n, Kern))


# -- links ---------------------------------------------------------------


def test_a_links_text_is_present_as_nodes_and_its_target_is_retained(theme: Theme) -> None:
    block = convert("see [the docs](https://example.test/x) now\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert len(block.links) == 1
    link = block.links[0]
    assert link.target == "https://example.test/x"
    assert text_of(block.material[link.start : link.end]) == "thedocs"


def test_a_links_span_covers_only_its_own_text(theme: Theme) -> None:
    block = convert("before [inside](http://x/) after\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    link = block.links[0]
    assert "before" not in text_of(block.material[link.start : link.end])
    assert "after" not in text_of(block.material[link.start : link.end])


# -- lists, quotes, rules ------------------------------------------------


def test_a_bullet_item_carries_a_marker_and_a_paragraph_does_not(theme: Theme) -> None:
    blocks = convert("plain\n\n- item\n", theme).blocks
    paragraph, item = blocks[0], blocks[1]
    assert isinstance(paragraph, TextBlock) and isinstance(item, TextBlock)
    assert paragraph.marker == ()
    assert text_of(item.marker) == "•"


def test_an_ordered_list_numbers_its_items_in_order(theme: Theme) -> None:
    blocks = convert("1. one\n2. two\n3. three\n", theme).blocks
    markers = [text_of(b.marker) for b in blocks if isinstance(b, TextBlock)]
    assert markers == ["1.", "2.", "3."]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # The last item is empty: it emits no block to take its bullet.
        ("- a\n-\n\npara\n\nend\n", ["•", "", ""]),
        # The only item starts with a fence, and a code block has no marker.
        ("1. ```\n   code\n   ```\n\npara\n\nend\n", ["", ""]),
        # The same, with the item not the last of its list.
        ("-\n- b\n\npara\n", ["•", ""]),
        # The control: an item whose paragraph does take the marker.
        ("- a\n- b\n\npara\n", ["•", "•", ""]),
    ],
)
def test_a_marker_no_block_took_does_not_land_on_the_paragraph_after_the_list(
    source: str, expected: list[str], theme: Theme
) -> None:
    """
    Review 3, item 1, measured before the fix: the paragraph after the list was a bullet.

    A list item's marker waits for the item's first text block. An item with no
    text block -- empty, or holding only a fence -- left it waiting, and the
    next paragraph in the document took it, however far outside the list. The
    first two sources gave markers of `["•", "•", ""]` and `["2.", ""]`
    (`.concerns/review3-snippets/s1.py.txt`); a stream, which parses that
    paragraph from its own first line, never did, so the two disagreed and it
    was the whole parse that was wrong.

    The third source is the case the fix must not overdo: an empty item's
    marker is dropped at the item's end, not handed to the next item, which has
    its own.
    """
    blocks = convert(source, theme).blocks
    assert [text_of(b.marker) for b in blocks if isinstance(b, TextBlock)] == expected


def test_a_nested_list_indents_one_step_further_than_its_parent(theme: Theme) -> None:
    blocks = convert("- outer\n  - inner\n", theme).blocks
    outer, inner = blocks[0], blocks[1]
    assert isinstance(outer, TextBlock) and isinstance(inner, TextBlock)
    assert inner.left_indent == outer.left_indent + theme.list_indent


def test_a_block_quote_sets_its_paragraphs_as_quotes_and_indents_them(theme: Theme) -> None:
    block = convert("> quoted\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert block.kind is BlockKind.QUOTE
    assert block.quote_depth == 1
    assert block.left_indent == theme.quote_indent


def test_a_thematic_break_is_a_rule_block_carrying_the_themes_thickness(theme: Theme) -> None:
    block = convert("---\n", theme).blocks[0]
    assert isinstance(block, RuleBlock)
    assert block.thickness == theme.rule_thickness
    assert block.thickness > 0


# -- fenced code ---------------------------------------------------------


def test_a_fenced_block_is_one_node_list_per_source_line(theme: Theme) -> None:
    block = convert("```python\nfirst\nsecond\n```\n", theme).blocks[0]
    assert isinstance(block, CodeBlock)
    assert block.language == "python"
    assert [text_of(line) for line in block.lines] == ["first", "second"]


def test_a_fenced_blocks_spaces_are_characters_so_indentation_cannot_stretch(
    theme: Theme,
) -> None:
    # Glue here would let the line breaker justify source code, and indentation
    # is content rather than spacing.
    block = convert("```\n    indented\n```\n", theme).blocks[0]
    assert isinstance(block, CodeBlock)
    line = block.lines[0]
    assert not [n for n in line if isinstance(n, Glue)]
    assert text_of(line) == "    indented"


def test_a_tab_in_a_fenced_block_becomes_four_columns(theme: Theme) -> None:
    block = convert("```\n\tx\n```\n", theme).blocks[0]
    assert isinstance(block, CodeBlock)
    assert text_of(block.lines[0]) == "    x"


def test_a_fenced_block_is_set_in_the_monospace_face(theme: Theme) -> None:
    block = convert("```\nx\n```\n", theme).blocks[0]
    assert isinstance(block, CodeBlock)
    assert faces(block.lines[0]) == [Face.CODE]


# -- tables --------------------------------------------------------------


def test_a_table_keeps_its_column_alignments_and_marks_its_header_cells(theme: Theme) -> None:
    source = "| L | C | R |\n|:--|:-:|--:|\n| a | b | c |\n"
    block = convert(source, theme).blocks[0]
    assert isinstance(block, TableBlock)
    assert block.aligns == (ColumnAlign.LEFT, ColumnAlign.CENTER, ColumnAlign.RIGHT)
    assert [cell.header for cell in block.header] == [True, True, True]
    assert [text_of(cell.material) for cell in block.rows[0]] == ["a", "b", "c"]


def test_a_table_cell_carries_unpacked_material_and_no_paragraph_terminator(
    theme: Theme,
) -> None:
    # A cell is hpacked to its column's width, not broken into lines, so the
    # parfillskip a paragraph ends with would be infinite stretch inside a box
    # that is being set to an exact width.
    source = "| head |\n|---|\n| body |\n"
    block = convert(source, theme).blocks[0]
    assert isinstance(block, TableBlock)
    assert not [n for n in block.rows[0][0].material if isinstance(n, Penalty)]


# -- the theme -----------------------------------------------------------


def test_the_type_scale_is_a_geometric_progression_not_a_hand_picked_set(
    theme: Theme,
) -> None:
    sizes = [
        theme.style(kind).font.size
        for kind in (
            BlockKind.PARAGRAPH,
            BlockKind.HEADING_3,
            BlockKind.HEADING_2,
            BlockKind.HEADING_1,
        )
    ]
    ratios = [b / a for a, b in zip(sizes, sizes[1:], strict=False)]
    assert ratios == pytest.approx([1.25, 1.25, 1.25], abs=1e-4)


def test_headings_are_ragged_right_and_body_text_is_justified(theme: Theme) -> None:
    assert theme.style(BlockKind.HEADING_1).align is Align.LEFT
    assert theme.style(BlockKind.PARAGRAPH).align is Align.JUSTIFY


def test_code_is_set_at_the_body_size_rather_than_smaller(theme: Theme) -> None:
    # Inconsolata's x-height is 0.457 em against Roboto's 0.528, so equal em
    # sizes already read smaller and shrinking further would compound it.
    assert theme.style(BlockKind.CODE).font.size == theme.style(BlockKind.PARAGRAPH).font.size
    assert theme.style(BlockKind.CODE).font.face is Face.CODE


def test_block_spacing_is_rigid_because_nothing_packs_a_page_to_a_height(
    theme: Theme,
) -> None:
    style = theme.style(BlockKind.PARAGRAPH)
    assert style.space_below > 0
    assert isinstance(style.space_below, int)


def test_headings_are_led_more_tightly_than_body_text_in_proportion_to_their_size(
    theme: Theme,
) -> None:
    heading = theme.style(BlockKind.HEADING_1)
    body = theme.style(BlockKind.PARAGRAPH)
    heading_ratio = heading.interline.baselineskip.width / heading.font.size
    body_ratio = body.interline.baselineskip.width / body.font.size
    assert heading_ratio < body_ratio


def test_a_font_key_round_trips_through_its_own_encoding() -> None:
    key = font_key(Face.PROSE_BOLD_ITALIC, 123456)
    assert parse_font_key(key).face is Face.PROSE_BOLD_ITALIC
    assert parse_font_key(key).size == 123456


def test_a_key_this_module_did_not_write_is_rejected_rather_than_guessed() -> None:
    with pytest.raises(ValueError):
        parse_font_key("prose")


def test_the_face_for_a_run_is_resolved_against_the_blocks_own_face(theme: Theme) -> None:
    assert theme.face_for(BlockKind.PARAGRAPH, Emphasis()) is Face.PROSE
    assert theme.face_for(BlockKind.PARAGRAPH, Emphasis(bold=True)) is Face.PROSE_BOLD
    assert theme.face_for(BlockKind.HEADING_2, Emphasis()) is Face.PROSE_BOLD
    # There is one monospace face, so code wins over everything.
    assert theme.face_for(BlockKind.HEADING_2, Emphasis(bold=True, code=True)) is Face.CODE


def test_interword_glue_at_the_neutral_factor_costs_nothing(theme: Theme) -> None:
    assert interword_glue(300) == interword_glue(300, 1000)


# -- the measure adapter -------------------------------------------------


def test_char_measure_rounds_the_metrics_floats_into_scaled_points() -> None:
    measure = char_measure(fake_resolve)
    dimens = measure(CharNode(font_key(Face.PROSE, 100), ord("x")))
    assert (dimens.width, dimens.height, dimens.depth) == (10, 7, 2)
    assert all(isinstance(v, int) for v in (dimens.width, dimens.height, dimens.depth))


def test_char_measure_memoises_because_every_pass_measures_every_glyph() -> None:
    measure = char_measure(fake_resolve)
    node = CharNode(font_key(Face.PROSE, 100), ord("x"))
    assert measure(node) is measure(node)


# ----------------------------------------------------------------------
# A space before a hard break
#
# `.concerns/A1-blocks--lead--unskip-before-hardbreak.md`. The reviewer predicted
# it by reading, the lead measured it on boxes, and `_unskip` is the fix. The
# tests below are on the material first and then through the real breaker, and
# the second one rebuilds the old material so it can show the defect it guards
# against rather than only its absence.


BACKSLASH_BREAK = "aaa bbb \\\nccc\n"
"""
Two words, a space, a backslash, a newline, a word: the source that leaves a space.
"""


def test_a_space_before_a_backslash_break_leaves_no_glue_in_front_of_it(theme: Theme) -> None:
    """
    The three spellings of "break here" build the same material.

    With the space, without it, and as two trailing spaces. Only the first ever
    differed: markdown-it keeps the space before a backslash break in the text
    token and strips the two-space form's.
    """
    spaced = convert(BACKSLASH_BREAK, theme).blocks[0]
    assert isinstance(spaced, TextBlock)
    assert spaced == convert("aaa bbb\\\nccc\n", theme).blocks[0]
    assert spaced == convert("aaa bbb  \nccc\n", theme).blocks[0]

    forced = next(i for i, node in enumerate(spaced.material) if isinstance(node, Penalty))
    assert isinstance(spaced.material[forced - 1], CharNode)
    assert sum(isinstance(node, Glue) for node in spaced.material) == 2, "one interword, one fil"


def test_a_code_span_ending_in_a_space_before_a_break_loses_the_space_and_its_guard(
    theme: Theme,
) -> None:
    """
    Inside a code span the space is `INF_PENALTY, Glue`, and both go.

    The penalty guarded a space that is no longer there; leaving it would be
    harmless and would also be a node that means nothing.
    """
    block = convert("aaa `bbb `\\\nccc\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    penalties = [node.value for node in block.material if isinstance(node, Penalty)]
    assert penalties == [INF_PENALTY, EJECT_PENALTY]
    assert text_of(block.material) == "aaabbbccc"


def test_a_link_that_ended_on_the_dropped_space_ends_on_its_last_character(theme: Theme) -> None:
    """
    Link spans index the material, so removing a node has to move them.

    `[bbb ](x)` closes its link *after* the trailing space, so the span's end was
    one past the glue. Left alone it would point at the first of the three break
    nodes appended next, and a backend underlining the link would underline the
    line's fill.
    """
    block = convert("aaa [bbb ](x)\\\nccc\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    (link,) = block.links
    assert link.target == "x"
    assert text_of(block.material[link.start : link.end]) == "bbb"
    assert isinstance(block.material[link.end - 1], CharNode)
    assert isinstance(block.material[link.end], Penalty)

    spanning = convert("aaa [bbb \\\nccc](x)\n", theme).blocks[0]
    assert isinstance(spanning, TextBlock)
    (across,) = spanning.links
    assert text_of(spanning.material[across.start : across.end]) == "bbbccc"


def _line_texts(material: tuple[Node, ...], width: int, params: Any) -> list[str]:
    """
    The text on each line `break_paragraph` makes of some material at a width.
    """
    paragraph = break_paragraph(
        material, ParShape.uniform(width), params, measure=char_measure(fake_resolve)
    )
    return [text_of(box.contents) for box in paragraph.boxes]


def test_a_space_before_a_hard_break_no_longer_sets_an_empty_line(theme: Theme) -> None:
    """
    End to end through the real breaker, with the old material as the control.

    The material as it used to be is rebuilt by putting the interword glue back
    in front of the forced break. Under each of four parameter sets -- the
    project's prose breaking, plain TeX's, ragged right, and ragged first-fit --
    that material sets an empty middle line at some measure between 40 and 120,
    which is the defect; the windows are printed in the assertion so a reader
    can see how wide each was. The material as it is now sets no empty line at
    any of those measures under any of them.

    Units are the fake metrics' own: a glyph is 10 and a space is 8, so
    `aaa bbb` is 68 wide and the space after it is the 8 that did not fit.
    """
    from dataclasses import replace

    from advtext.ui import PROSE_BREAKING, RAGGED_RIGHT

    now = convert(BACKSLASH_BREAK, theme).blocks[0]
    assert isinstance(now, TextBlock)
    forced = next(i for i, node in enumerate(now.material) if isinstance(node, Penalty))
    space = next(node for node in now.material if isinstance(node, Glue))
    before = (*now.material[:forced], space, *now.material[forced:])

    widths = range(40, 121)
    for name, params in {
        "prose": PROSE_BREAKING,
        "plain": LineBreakParams(),
        "ragged": replace(PROSE_BREAKING, right_skip=RAGGED_RIGHT),
        "first-fit": replace(PROSE_BREAKING, right_skip=RAGGED_RIGHT, first_fit=True),
    }.items():
        was_blank = [w for w in widths if "" in _line_texts(before, w, params)]
        assert 68 in was_blank, f"{name}: the old material no longer shows the defect"
        assert all(_line_texts(before, w, params) == ["aaabbb", "", "ccc"] for w in was_blank)

        is_blank = [w for w in widths if "" in _line_texts(now.material, w, params)]
        assert not is_blank, f"{name}: empty line at measures {is_blank} (was {was_blank})"
        assert _line_texts(now.material, 68, params) == ["aaabbb", "ccc"], name


# ----------------------------------------------------------------------
# Blocks without markdown: `text_block` and `code_block`
#
# The claim under test is "the same block the converter would have made", so
# almost every assertion here is an equality with `build_document` on a source
# where the two should agree. Blocks are frozen dataclasses of frozen nodes, so
# `==` compares every node, every kern, every glue and every style field; a
# constructor that had grown its own copy of `_append_text` would have to
# reproduce all of it to pass.


PLAIN = "To the end. Next sentence, with a To in it."
"""
Chosen to cross the three things `_append_text` does beyond emitting characters:
the kerned pair, a sentence end (the space factor), and ordinary interword glue.
"""


def test_plain_text_becomes_the_block_the_converter_makes_for_the_same_paragraph(
    theme: Theme,
) -> None:
    built = convert(PLAIN + "\n", theme).blocks[0]
    assert text_block(PLAIN, theme, fake_resolve) == built
    assert any(isinstance(node, Kern) for node in built.material)  # type: ignore[union-attr]
    assert len({node.spec for node in built.material if isinstance(node, Glue)}) > 1  # type: ignore[union-attr]


def test_markdown_syntax_in_plain_text_is_set_and_not_read(theme: Theme) -> None:
    """
    The reason the constructor exists: an asterisk is an asterisk.

    The same string through `build_document` is the control. It comes out with
    three faces and without its punctuation; through `text_block` every
    character survives and all of it is in the one face.
    """
    hostile = "**not bold**, `not code`, [not a link](x) and __init__"

    parsed = convert(hostile + "\n", theme).blocks[0]
    assert isinstance(parsed, TextBlock)
    assert len(set(faces(parsed.material))) == 3 and parsed.links

    block = text_block(hostile, theme, fake_resolve)
    assert text_of(block.material) == hostile.replace(" ", "")
    assert set(faces(block.material)) == {Face.PROSE}
    assert block.links == ()


def test_surrounding_whitespace_is_not_material(theme: Theme) -> None:
    assert text_block(f"  \n{PLAIN}\n\n ", theme, fake_resolve) == text_block(
        PLAIN, theme, fake_resolve
    )


def test_a_kind_and_an_emphasis_choose_the_style_and_the_face(theme: Theme) -> None:
    """
    A heading is a `kind`, and bold is an `emphasis`, exactly as in the converter.
    """
    assert (
        text_block("A Title", theme, fake_resolve, kind=BlockKind.HEADING_2)
        == convert("## A Title\n", theme).blocks[0]
    )
    assert (
        text_block("all of it", theme, fake_resolve, emphasis=Emphasis(bold=True))
        == convert("**all of it**\n", theme).blocks[0]
    )
    assert (
        text_block(
            "both",
            theme,
            fake_resolve,
            kind=BlockKind.HEADING_3,
            emphasis=Emphasis(italic=True),
        )
        == convert("### *both*\n", theme).blocks[0]
    )


def test_a_marker_and_an_indent_make_the_block_a_list_item(theme: Theme) -> None:
    """
    Both list kinds, and a nested one, equal to the converter's.

    Nothing is inferred from `kind`, so the marker text and the indent are the
    caller's to give; the control at the end is the same kind with neither.
    """
    bullet = convert("- an item\n", theme).blocks[0]
    assert (
        text_block(
            "an item",
            theme,
            fake_resolve,
            kind=BlockKind.BULLET_ITEM,
            marker="•",
            indent=theme.list_indent,
        )
        == bullet
    )

    third = convert("3. an item\n", theme).blocks[0]
    assert (
        text_block(
            "an item",
            theme,
            fake_resolve,
            kind=BlockKind.ORDERED_ITEM,
            marker="3.",
            indent=theme.list_indent,
        )
        == third
    )

    nested = convert("- outer\n  - inner\n", theme).blocks[1]
    assert (
        text_block(
            "inner",
            theme,
            fake_resolve,
            kind=BlockKind.BULLET_ITEM,
            marker="•",
            indent=2 * theme.list_indent,
        )
        == nested
    )

    bare = text_block("an item", theme, fake_resolve, kind=BlockKind.BULLET_ITEM)
    assert bare.marker == () and bare.left_indent == 0
    assert bare != bullet


def test_a_quote_is_a_kind_an_indent_and_a_depth(theme: Theme) -> None:
    assert (
        text_block(
            "quoted words",
            theme,
            fake_resolve,
            kind=BlockKind.QUOTE,
            indent=theme.quote_indent,
            quote_depth=1,
        )
        == convert("> quoted words\n", theme).blocks[0]
    )


def test_newlines_are_spaces_unless_hard_breaks_are_asked_for(theme: Theme) -> None:
    """
    Both newline rules, each equal to the markdown that means the same thing.

    Default: a newline is a space, which is CommonMark's soft break. With
    `hard_breaks`: a newline is the three nodes of a markdown hard break -- two
    trailing spaces before the newline, in the source on the right.
    """
    two_lines = "first line\nsecond line"

    soft = text_block(two_lines, theme, fake_resolve)
    assert soft == convert(two_lines + "\n", theme).blocks[0]
    assert not any(isinstance(node, Penalty) for node in soft.material)

    hard = text_block(two_lines, theme, fake_resolve, hard_breaks=True)
    assert hard == convert("first line  \nsecond line\n", theme).blocks[0]
    assert [node.value for node in hard.material if isinstance(node, Penalty)] == [
        INF_PENALTY,
        EJECT_PENALTY,
    ]
    assert hard == text_block("\n" + two_lines + "\n\n", theme, fake_resolve, hard_breaks=True)


def test_a_blank_line_under_hard_breaks_is_two_breaks_and_still_one_block(theme: Theme) -> None:
    """
    `text_block` returns one block whatever the text holds.

    A blank line is not a paragraph boundary here -- the function cannot return
    two blocks -- so it is two forced breaks in a row, which sets an empty line.
    """
    block = text_block("above\n\nbelow", theme, fake_resolve, hard_breaks=True)
    assert isinstance(block, TextBlock)
    ejects = [
        node for node in block.material if isinstance(node, Penalty) and node.value == EJECT_PENALTY
    ]
    assert len(ejects) == 2
    assert text_of(block.material) == "abovebelow"


@pytest.mark.parametrize("kind", [BlockKind.CODE, BlockKind.RULE, BlockKind.TABLE])
def test_a_kind_that_is_not_text_is_refused_by_name(kind: BlockKind) -> None:
    """
    `text_block(kind=CODE)` would return prose in the code style, silently.
    """
    with pytest.raises(ValueError, match=kind.name):
        text_block("anything", Theme.build(), fake_resolve, kind=kind)


def test_source_text_becomes_the_block_a_fence_makes(theme: Theme) -> None:
    """
    `code_block` against a fenced block: tabs, blank lines, trailing newlines, language.
    """
    source = "def f():\n\treturn  1\n\n# after a blank\n\n\n"
    fenced = convert(f"```python\n{source}```\n", theme).blocks[0]
    assert isinstance(fenced, CodeBlock)

    block = code_block(source, theme, fake_resolve, language="python")
    assert block == fenced
    assert len(block.lines) == 4 and block.lines[2] == ()
    assert text_of(block.lines[1]) == "    return  1", "a tab is four columns and spaces are kept"
    assert block.language == "python"


def test_a_code_block_s_indent_is_added_to_the_style_s_own(theme: Theme) -> None:
    """
    Equal to a fence inside a list item, whose indent the converter adds the same way.
    """
    inside = convert("- item\n\n  ```\n  x = 1\n  ```\n", theme).blocks[1]
    assert isinstance(inside, CodeBlock)
    block = code_block("x = 1\n", theme, fake_resolve, indent=theme.list_indent)
    assert block == inside
    assert block.left_indent == theme.list_indent + theme.style(BlockKind.CODE).left_indent


def test_constructed_blocks_and_all_six_headings_compose_and_ship(theme: Theme) -> None:
    """
    The new kinds and the new constructors reach the far end of the pipeline.

    `advtext.ui.compose` does not branch on `BlockKind` -- checked by reading it
    -- so three new kinds should need nothing from it, and this is the run that
    says so: a document of all six headings from markdown, followed by blocks
    that never were markdown, composed and shipped. Every character comes out
    as a glyph -- the code block's spaces among them, which are characters and
    not glue -- and the hard-broken text with a blank line in it sets three
    lines, the middle one empty.
    """
    from advtext.shipout import Glyph, Line, Point, ship
    from advtext.ui import compose

    measure = char_measure(fake_resolve)
    headings = convert("".join(f"{'#' * n} H{n}\n\n" for n in range(1, 7)), theme).blocks
    broken = text_block("above\n\nbelow", theme, fake_resolve, hard_breaks=True)
    blocks = (
        *headings,
        text_block("**plain** words", theme, fake_resolve),
        broken,
        code_block("a = 1\nb = 2\n", theme, fake_resolve),
    )

    box = compose(Document(blocks=blocks), theme, 400 * 65536, measure)
    commands = tuple(ship(box, Point(0, box.height), measure=measure))

    drawn = "".join(chr(cmd.codepoint) for cmd in commands if isinstance(cmd, Glyph))
    assert drawn == "H1H2H3H4H5H6**plain**wordsabovebelowa = 1b = 2"

    alone = compose(Document(blocks=(broken,)), theme, 400 * 65536, measure)
    lines = [
        cmd for cmd in ship(alone, Point(0, alone.height), measure=measure) if isinstance(cmd, Line)
    ]
    assert len(lines) == 3


# -- the block-to-source map ----------------------------------------------
#
# `Document.sources` says where each block came from, so that a host can hand
# back the markdown of whatever the user is pointing at. Every expectation here
# is the literal text a person would expect to get, cut from the source by the
# span, rather than a pair of line numbers: a span that is off by a line still
# has plausible numbers and never has the right text.

MAPPED = (
    "# Title\n"
    "\n"
    "para one\n"
    "line two\n"
    "\n"
    "- a\n"
    "- b\n"
    "  more\n"
    "\n"
    "  second para in b\n"
    "\n"
    "> q1\n"
    ">\n"
    "> q2\n"
    "\n"
    "```py\n"
    "code\n"
    "```\n"
    "\n"
    "---\n"
    "\n"
    "| a | b |\n"
    "|---|---|\n"
    "| 1 | 2 |\n"
    "\n"
    "1. x\n"
    "\n"
    "   ```\n"
    "   f\n"
    "   ```\n"
)


def test_every_block_records_the_source_lines_it_came_from(theme: Theme) -> None:
    document = build_document(MAPPED, theme, fake_resolve)
    assert len(document.sources) == len(document.blocks)
    own = [source.span.of(MAPPED) for source in document.sources]
    assert own == [
        "# Title\n",
        "para one\nline two\n",
        "- a\n",
        "- b\n  more\n",
        "  second para in b\n",
        "> q1\n",
        "> q2\n",
        "```py\ncode\n```\n",
        "---\n",
        "| a | b |\n|---|---|\n| 1 | 2 |\n",
        "1. x\n",
        "   ```\n   f\n   ```\n",
    ]
    # The kinds line up with the text, so a span is not merely *a* block's.
    kinds = [type(block).__name__ for block in document.blocks]
    assert kinds[7:10] == ["CodeBlock", "RuleBlock", "TableBlock"]
    assert kinds[-1] == "CodeBlock"


def test_a_setext_headings_own_span_includes_its_underline(theme: Theme) -> None:
    """
    Review 3, item 6, measured before the fix: the span was `'Title\\n'`.

    The text of a heading is an `inline` token whose line range is the text's
    lines; for a setext heading the underline is a line more, and only the
    `heading_open` token's range has it. A host copying the block as markdown
    from the short span got a paragraph. `top` was right all along, which is
    the control here and why no streaming commit was ever wrong because of it.

    The other cases pin what must not change: an ATX heading is its one line, a
    two-line setext heading keeps both text lines, and inside a list item the
    span is still the heading's own lines and not the list's.
    """
    source = "Title\n=====\n\npara\n\nTwo\nlines\n---\n\n# atx\n\n- In an item\n  ---\n- next\n"
    document = build_document(source, theme, fake_resolve)
    kinds = [block.kind for block in document.blocks if isinstance(block, TextBlock)]
    assert kinds[:5] == [
        BlockKind.HEADING_1,
        BlockKind.PARAGRAPH,
        BlockKind.HEADING_2,
        BlockKind.HEADING_1,
        BlockKind.HEADING_2,
    ]
    assert [item.span.of(source) for item in document.sources] == [
        "Title\n=====\n",
        "para\n",
        "Two\nlines\n---\n",
        "# atx\n",
        "- In an item\n  ---\n",
        "- next\n",
    ]
    assert document.sources[0].top == document.sources[0].span
    assert document.sources[4].top.of(source) == "- In an item\n  ---\n- next\n"


@pytest.mark.parametrize(
    ("source", "lines", "closed"),
    [
        ("```py\na\nb\n", ["a", "b"], False),
        ("```py\na\nb\n```\n", ["a", "b"], True),
        ("```py\na\nb\n```\nafter\n", ["a", "b"], True),
        # Blank lines at the end are lines: the fence may not be finished.
        ("```\na\n\n\n", ["a", "", ""], False),
        ("```\na\n\n```\n", ["a", ""], True),
        # Not closing lines: too short, indented four, wrong character, text after.
        ("```\n``\n    ```\n~~~\n``` x\n", ["``", "    ```", "~~~", "``` x"], False),
        ("~~~\n```\n~~~~  \n", ["```"], True),
        # An unfinished last line: content if it has anything on it, a closing
        # line if it is one, and no line at all if it is only whitespace.
        ("```\na\nb", ["a", "b"], False),
        ("```\na\n```", ["a"], True),
        ("```\na\n  \t", ["a"], False),
        ("```\na\n  \n", ["a", "  "], False),
        # The fence's indent comes off each line, a tab counted as columns.
        ("  ```\n  a\n b\n\tc\n", ["a", "b", "  c"], False),
        ("```\n", [], False),
        ("```\n```\n", [], True),
    ],
)
def test_the_leading_fence_is_read_with_its_blank_lines_and_whether_it_closed(
    source: str, lines: list[str], closed: bool, theme: Theme
) -> None:
    """
    `_leading_fence`, which `advtext.stream` trusts for the two facts a block does not keep.

    "Closed" is inferred from a line count markdown-it does not document
    (the function's docstring has the reading), so every row here is a case
    where that inference could be off by one: blank lines at the end, an
    unfinished last line of each kind, an empty fence. The control against the
    converter is that the lines, trailing blank ones dropped, are the lines of
    the `CodeBlock` the same source gives.
    """
    found = _leading_fence(source, theme)
    assert found is not None
    assert [text_of(line) for line in found.lines] == lines
    assert found.closed is closed
    block = build_document(source, theme, fake_resolve).blocks[0]
    assert isinstance(block, CodeBlock)
    kept = list(found.lines)
    while kept and not kept[-1]:
        kept.pop()
    assert tuple(kept) == block.lines and found.language == block.language


@pytest.mark.parametrize(
    "source",
    [
        "",
        "para\n```\ncode\n",
        "    ```\nindented code, not a fence\n",
        "- ```\n  in an item\n",
        "```a`b\na backtick in the info string\n",
        # The table rule runs before the fence rule.
        "~~~a|b\n-|-\n",
    ],
)
def test_a_source_that_does_not_begin_with_a_top_level_fence_has_no_leading_fence(
    source: str, theme: Theme
) -> None:
    assert _leading_fence(source, theme) is None
    # And the last one is a fence as soon as its second line is not a delimiter row.
    assert _leading_fence("~~~a|b\nx\n-|-\n", theme) is not None


def test_blocks_from_one_list_or_quote_share_the_top_level_block_they_are_part_of(
    theme: Theme,
) -> None:
    document = build_document(MAPPED, theme, fake_resolve)
    tops = [source.top.of(MAPPED) for source in document.sources]
    whole_list = "- a\n- b\n  more\n\n  second para in b\n"
    whole_quote = "> q1\n>\n> q2\n"
    numbered = "1. x\n\n   ```\n   f\n   ```\n"
    assert tops[2:5] == [whole_list] * 3
    assert tops[5:7] == [whole_quote] * 2
    assert tops[10:12] == [numbered] * 2
    # A block that is top-level itself is its own top.
    for index in (0, 1, 7, 8, 9):
        assert document.sources[index].top == document.sources[index].span
    # And grouping by `top` recovers the top-level blocks, in order.
    distinct = list(dict.fromkeys(source.top for source in document.sources))
    assert len(distinct) == 8
    assert [span.line_start for span in distinct] == sorted(span.line_start for span in distinct)


def test_a_span_is_whole_lines_and_never_ends_in_a_blank_one(theme: Theme) -> None:
    # markdown-it's own range for a list runs over the blank line after it.
    # That line belongs to no block, and a span that kept it would overlap
    # nothing but would hand a host a trailing blank line to paste.
    document = build_document(MAPPED, theme, fake_resolve)
    lines = MAPPED.splitlines(keepends=True)
    for source in document.sources:
        for span in (source.span, source.top):
            assert span.of(MAPPED) == "".join(lines[span.line_start : span.line_end])
            assert span.of(MAPPED).splitlines()[-1].strip()
            assert span.line_end > span.line_start
    # Top-level spans do not overlap, and everything between them is blank.
    distinct = list(dict.fromkeys(source.top for source in document.sources))
    position = 0
    for span in distinct:
        assert span.start >= position
        assert not MAPPED[position : span.start].strip()
        position = span.end
    assert not MAPPED[position:].strip()


def test_the_source_map_is_beside_the_blocks_so_moving_text_rebreaks_nothing(
    theme: Theme,
) -> None:
    # The reason it is not a field of the block: caches key blocks by value.
    # Two blank lines inserted above the document move every span and leave
    # every block equal, so every cached layout is still found.
    original = build_document(MAPPED, theme, fake_resolve)
    moved = build_document("\n\n" + MAPPED, theme, fake_resolve)
    assert moved.blocks == original.blocks
    assert moved.sources != original.sources
    assert moved.sources == tuple(
        BlockSource(span=source.span.shifted(2, 2), top=source.top.shifted(2, 2))
        for source in original.sources
    )
    assert moved != original


def test_a_source_without_a_final_newline_and_one_with_crlf_still_slice_verbatim(
    theme: Theme,
) -> None:
    bare = "first\n\nlast line"
    document = build_document(bare, theme, fake_resolve)
    assert [source.span.of(bare) for source in document.sources] == ["first\n", "last line"]
    assert document.sources[-1].span.end == len(bare)

    crlf = "first\r\n\r\n- item\r\n- other\r\n"
    document = build_document(crlf, theme, fake_resolve)
    assert [source.span.of(crlf) for source in document.sources] == [
        "first\r\n",
        "- item\r\n",
        "- other\r\n",
    ]
    assert document.sources[1].top.of(crlf) == "- item\r\n- other\r\n"


def test_a_document_built_by_hand_records_no_sources(theme: Theme) -> None:
    by_hand = Document(blocks=(text_block("no markdown here", theme, fake_resolve),))
    assert by_hand.sources == ()
    assert by_hand.source_of(0) is None
    built = build_document("one\n\ntwo\n", theme, fake_resolve)
    first = built.source_of(0)
    assert first is not None and first.span == SourceSpan(0, 1, 0, 4)
    assert built.source_of(2) is None and built.source_of(-1) is None
    assert build_document("", theme, fake_resolve).sources == ()


def test_the_demo_document_maps_every_block_and_leaves_only_blank_lines_unclaimed(
    theme: Theme,
) -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(
        encoding="utf-8"
    )
    document = build_document(source, theme, fake_resolve)
    assert len(document.sources) == len(document.blocks) > 30
    position = 0
    for span in dict.fromkeys(item.top for item in document.sources):
        assert not source[position : span.start].strip()
        assert span.of(source).strip()
        position = span.end
    assert not source[position:].strip()


# ----------------------------------------------------------------------
# Review 2, items 3 and 5; and the parser `advtext.stream` reads with.
#
# Item 3 is about geometry, which this file otherwise leaves alone. It is here
# because the defect was in the *material* this module emits and the only way
# to show that material wrong is to set it.


def _line_starts_and_ends(block: TextBlock, theme: Theme, width: int) -> list[tuple[int, int]]:
    """
    Left edge of the first glyph and right edge of the last, per line, composed and shipped.

    Through `compose_blocks`, because the alignment is carried out there
    (`advtext.ui._skips`). Fake metrics: every glyph is 10 wide.
    """
    from advtext.shipout import Glyph, Point, ship
    from advtext.ui import compose_blocks

    measure = char_measure(fake_resolve)
    box = compose_blocks((block,), theme, width, measure)
    lines: dict[int, list[int]] = {}
    for command in ship(box, Point(0, box.height), measure=measure):
        if isinstance(command, Glyph):
            lines.setdefault(command.y, []).append(command.x)
    return [(min(xs), max(xs) + int(GLYPH_ADVANCE)) for _, xs in sorted(lines.items())]


@pytest.mark.parametrize("markdown", [False, True], ids=["text_block", "markdown"])
def test_a_line_before_a_hard_break_is_placed_as_every_other_line_of_its_block_is(
    markdown: bool,
) -> None:
    r"""
    Ragged left, the line before a hard break ends at the right margin; centred, it is centred.

    Three lines of 30, 50 and 20 at a measure of 100000. **Before the fix the
    first two were not where the third was**: ragged left they ended at about
    50015 and 50025 instead of 100000, centred they sat a quarter of the way
    along instead of half, because the hard break's own `1fil` fill took half
    of the slack that the `\leftskip` should have had all of. Measured with the
    real fonts by the lead (review 2, item 3) and re-measured here before
    changing anything; the fake numbers are the same defect in round figures.

    Only the first two lines are asserted exactly. The third is the paragraph's
    last and is `advtext.linebreak`'s and `advtext.ui`'s to place; it is a unit
    or two short, and the strict `xfail` below says why and whose that is.

    The lead's snippet compared the first glyph's x of `aaa` and `bbb`. Those
    two words are not the same width in Roboto, so that comparison is unequal
    after the fix too; what a ragged-left block shares is its *right* edge,
    which is what is asserted.

    `LEFT` and `JUSTIFY` are the controls that nothing moved where it was right.
    """

    def block_in(align: Align) -> tuple[TextBlock, Theme]:
        theme = Theme.build(align=align)
        if markdown:
            (block,) = build_document("aaa\\\nbbbbb  \ncc\n", theme, fake_resolve).blocks
        else:
            block = text_block("aaa\nbbbbb\ncc", theme, fake_resolve, hard_breaks=True)
        assert isinstance(block, TextBlock)
        return block, theme

    width = 100_000
    ragged_left = _line_starts_and_ends(*block_in(Align.RIGHT), width)
    assert ragged_left[:2] == [(99_970, 100_000), (99_950, 100_000)]
    assert ragged_left[2][1] == pytest.approx(width, abs=2)
    centred = _line_starts_and_ends(*block_in(Align.CENTER), width)
    assert centred[:2] == [(49_985, 50_015), (49_975, 50_025)]
    assert centred[2][0] == pytest.approx(49_990, abs=2)
    for align in (Align.LEFT, Align.JUSTIFY):
        assert _line_starts_and_ends(*block_in(align), width) == [(0, 30), (0, 50), (0, 20)]


def test_the_fill_before_a_forced_break_is_left_out_only_where_a_left_skip_would_fight_it() -> None:
    """
    The material itself: three nodes justified and ragged right, one otherwise.

    Justified and ragged-right material are *equal*, node for node. That is
    relied on by `advtext.stream`, which sets a block ragged while it is being
    written and may re-set it justified when it is finished: the two blocks
    then differ in their style and in nothing else.
    """
    fill_and_break = (Penalty(INF_PENALTY), Glue(PARFILLSKIP), Penalty(EJECT_PENALTY))

    def material(align: Align) -> tuple[Node, ...]:
        theme = Theme.build(align=align)
        return text_block("ab\ncd", theme, fake_resolve, hard_breaks=True).material

    justified = material(Align.JUSTIFY)
    assert justified[2:5] == fill_and_break and len(justified) == 7
    assert material(Align.LEFT) == justified
    for align in (Align.RIGHT, Align.CENTER):
        ragged_left = material(align)
        assert ragged_left[2:3] == (Penalty(EJECT_PENALTY),) and len(ragged_left) == 5
        assert not any(isinstance(node, Glue) for node in ragged_left)


def test_a_blank_line_between_hard_breaks_is_still_a_blank_line_in_every_alignment() -> None:
    """
    Two forced breaks with nothing between them set an empty line, fill or no fill.

    `text_block`'s docstring promises it, and taking the fill away for two
    alignments is exactly the kind of change that could have cost it: the
    middle line is then two penalties and nothing else.
    """
    from advtext.ui import PROSE_BREAKING, _skips

    for align in Align:
        theme = Theme.build(align=align)
        block = text_block("above\n\nbelow", theme, fake_resolve, hard_breaks=True)
        params = _skips(align, PROSE_BREAKING)
        if align is not Align.JUSTIFY:
            from dataclasses import replace

            params = replace(params, first_fit=True)
        assert _line_texts(block.material, 400, params) == ["above", "", "below"], align


def test_the_last_line_of_a_ragged_left_block_ends_exactly_at_the_margin() -> None:
    r"""
    What was left of review 2's item 3 after this module's half was fixed.

    At a measure of twenty million units -- about 305 pt, a real one -- the
    last line of a ragged-left block ended 305 units (thousandths of a point)
    short of the margin, where the lines before the hard breaks ended on it
    exactly: `advtext.ui._skips` left the `\parfillskip` at `1sp plus 1fil`
    beside a left skip of 65536 times that, and the two shared the slack. Far
    below a pixel, and so a statement about exactness and not about anything a
    reader could see.

    This was a strict `xfail` until `_skips` dropped the `\parfillskip` for
    ragged-left and centred blocks (AF-tables); it failed as "unexpectedly
    passing" the moment that landed, which is what the marker was for. The
    centred half is asserted too: before, its last line sat 76 units left of
    centre.
    """
    width = 20_000_000
    theme = Theme.build(align=Align.RIGHT)
    block = text_block("aaa\nbbbbb\ncc", theme, fake_resolve, hard_breaks=True)
    ends = [end for _, end in _line_starts_and_ends(block, theme, width)]
    assert ends[:2] == [width, width], "the hard-break lines are this module's and are exact"
    assert ends[2] == width

    theme = Theme.build(align=Align.CENTER)
    block = text_block("aaa\nbbbbb\ncc", theme, fake_resolve, hard_breaks=True)
    for start, end in _line_starts_and_ends(block, theme, width):
        assert start + end == width


@pytest.mark.parametrize("ending", ["\r\n", "\r"])
def test_carriage_returns_are_line_ends_to_the_two_constructors(theme: Theme, ending: str) -> None:
    r"""
    `\r\n` and a lone `\r` mean what `\n` means, in `code_block` and in `text_block`.

    The defect, measured (review 2, item 5): `code_block("a\r\nb\r\n", ...)`
    set a carriage return as a character at the end of each line -- code points
    `[97, 13]` -- because the lines were split on `\n` alone. With a lone `\r`
    the whole source was one line. `text_block` did not show it without
    `hard_breaks`, where any whitespace is a space; with them, `\r\n` happened
    to work (the `\r` was stripped as whitespace) and a lone `\r` did not break
    the line at all.
    """
    plain = "first\n  second\n\nthird\n"
    source = plain.replace("\n", ending)
    assert "\n" not in source or ending == "\r\n"

    expected = code_block(plain, theme, fake_resolve)
    assert [text_of(line) for line in expected.lines] == ["first", "  second", "", "third"]
    assert code_block(source, theme, fake_resolve) == expected

    for hard_breaks in (False, True):
        assert text_block(source, theme, fake_resolve, hard_breaks=hard_breaks) == text_block(
            plain, theme, fake_resolve, hard_breaks=hard_breaks
        )
    broken = text_block(source, theme, fake_resolve, hard_breaks=True)
    assert sum(node == Penalty(EJECT_PENALTY) for node in broken.material) == 3


def test_references_off_reads_a_definition_as_text_and_leaves_the_default_alone(
    theme: Theme,
) -> None:
    """
    `build_document(..., references=False)`: a definition is a paragraph, a use is not a link.

    And the default is what it was -- the definition consumed, the use a link
    -- before and after the other parser has been used, since the two must not
    share state. `tests/test_stream.py` has why a streaming caller needs this.
    """
    source = "[name]\n\n[name]: https://example.org\n"
    default = convert(source, theme)
    (only,) = default.blocks
    assert isinstance(only, TextBlock) and [link.target for link in only.links] == [
        "https://example.org"
    ]

    off = build_document(source, theme, fake_resolve, references=False)
    assert len(off.blocks) == 2
    assert all(isinstance(block, TextBlock) and not block.links for block in off.blocks)
    assert [text_of(block.material) for block in off.blocks if isinstance(block, TextBlock)] == [
        "[name]",
        "[name]:https://example.org",
    ]
    assert convert(source, theme) == default

    no_definitions = "A [link](https://example.org) and *text*.\n\n- item\n"
    assert build_document(no_definitions, theme, fake_resolve, references=False) == convert(
        no_definitions, theme
    )


# ----------------------------------------------------------------------
# Resuming inside an unfinished list or quote (`_resume_point`, for `advtext.stream`)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Nothing to resume inside: no container, or still on its first child.
        ("para\n\nmore\n", None),
        ("- a\n", None),
        ("```\ncode\n", None),
        # The container is over: the last block is a raw HTML block after it.
        ("- a\n\n<div>\nx\n", None),
        # A tab in an opening line is not reasoned about.
        ("-\ta\n\n\tb\n", None),
        # A new item: the list is re-opened padded by four, so that an item
        # indented up to three columns is still a sibling of the opener's.
        ("- a\n- b\n", (1, "-    ***\n")),
        ("1. a\n2. b\n3. c\n", (2, "1.    ***\n")),
        ("-    wide\n  - sibling\n", (1, "-    ***\n")),
        # The break is dashes under an asterisk marker: `* ***` is itself a break.
        ("* a\n* b\n", (1, "*    ---\n")),
        # Inside an item: its own marker and padding, so the columns are its own.
        ("- a\n\n  second\n", (2, "- ***\n")),
        ("10. a\n\n    b\n\n    c\n", (4, "10. ***\n")),
        ("7) a\n\n   ```\n   x\n", (2, "7) ***\n")),
        # A closed fence: resume on the line after its closing line.
        ("7) a\n\n   ```\n   x\n   ```\n", (5, "7) ***\n")),
        ("- ```\n  x\n  ```\n", (3, "- ***\n")),
        # Quotes, and containers inside containers.
        ("> a\n>\n> b\n", (2, "> ***\n")),
        ("> - a\n> - b\n>   c\n>\n>   d\n", (4, "> - ***\n")),
        ("- > q\n  >\n  > r\n", (2, "- > ***\n")),
        ("- a\n  1. b\n  2. c\n\n     d\n", (4, "- 2. ***\n")),
        # An inner item indented by one, under an outer item whose marker is
        # followed by more than four spaces (so its content starts after one):
        # the inner indent is written after the inner marker, not before it.
        (" -      1.     x\n    2.     y\n       z\n\n       w\n", (4, " - 2.  ***\n")),
    ],
)
def test_where_an_unfinished_container_can_be_resumed_and_with_what_opener(
    source: str, expected: tuple[int, str] | None
) -> None:
    """
    `_resume_point` on sources small enough to check by eye.

    The opener is the claim: one line that leaves a parser where the real
    source left it at the start of the line named. The next test is what holds
    that claim to the whole parse; this one pins what the line *is*, so that a
    change to how it is written is seen as one.
    """
    point = _resume_point(_tokens(source), source, _line_starts(source))
    assert (None if point is None else (point.line, point.opener)) == expected


NESTED_SOURCES = [
    "- a\n- b\n\n  in b\n\n      code in b\n- c\n\nafter\n",
    "1. step\n\n   ```sh\n   make\n\n   check\n   ```\n\n   and text\n\n2. two\n3. three\n\nend\n",
    "7. a\n1. b\n1. c\n   lazy\nlazier\n1. d\n",
    "> a\n>\n> b\nlazy\n>\n> - c\n> - d\n>\n> > e\n> > f\n\nout\n",
    "-    wide\n  - sibling\n   - third\n     in third\n  in none\n",
    " -      1.     x\n    2.     y\n       ````\n       z\n       ````\n   =\n",
    "100. 1.   ~~~\n        5.     t\n           u\n\n     v\n",
    "- - a\n  - b\n    1. c\n    2. d\n\n       e\n  - f\n- g\n",
    "- > q\n  >\n  > r\n  > - s\n  >   t\n\n  u\n- v\n",
    "- a|b\n- -|-\n- c\n  -|-\n  1|2\n-|-\n",
    "* a\n* b\n* * *\n* c\n",
    "- # h\n  text\n  ===\n  more\n  ---\n- | a | b |\n  |---|---|\n  | 1 | 2 |\n",
    "1. ```\n   x\n   ```\n   after the fence\n2. ```\n   y\n\n3. z\n",
    "> intro\n> ```\n> x\n>\ny\n> text\n> ```\n> z\n> ```\n> w\n",
    "- a\n\n  <div>\n  raw\n\n  b\n- c\n<!--\n- d\n",
    "- a\n-\n- b\n\n\n- c\n",
]


@pytest.mark.parametrize("source", NESTED_SOURCES)
def test_resuming_from_any_finished_line_gives_the_blocks_of_the_whole_source(
    source: str, theme: Theme
) -> None:
    """
    Kept blocks plus the resumed parse equal one parse, from every line, for every later text.

    For each prefix of whole lines that has a resume point, the blocks emitted
    before it are kept and the rest of the source is read as opener plus
    suffix, with the converter put back in the state it was in -- for every
    longer prefix, each also with the first half of its next line unfinished.
    That is the stream's use of it, without the stream. Where the opener is not
    read as the containers it names (`_opens`), the caller is told so and
    parses the whole source; that is counted, not excused, and must not be the
    only thing that ever happens.

    Blocks only. Spans are moved by the caller and are compared where the
    caller is tested, in `tests/test_stream.py`.
    """
    lines = source.splitlines(keepends=True)
    resumed = refused = 0
    for count in range(1, len(lines) + 1):
        prefix = "".join(lines[:count])
        tokens = _tokens(prefix)
        starts = _line_starts(prefix)
        point = _resume_point(tokens, prefix, starts)
        if point is None:
            continue
        document, kept, state = _convert(
            tokens, prefix, starts, theme, fake_resolve, mark=point.mark
        )
        assert state is not None
        assert document == build_document(prefix, theme, fake_resolve, references=False)
        offset = starts[point.line]
        for longer in range(count, len(lines) + 1):
            whole = "".join(lines[:longer])
            half = lines[longer][: len(lines[longer]) // 2] if longer < len(lines) else ""
            for text in {whole, whole + half}:
                joined = point.opener + text[offset:]
                again = _tokens(joined)
                if not _opens(again, point.shape):
                    refused += 1
                    continue
                rest, _, _ = _convert(
                    again,
                    joined,
                    _line_starts(joined),
                    theme,
                    fake_resolve,
                    first=len(point.shape),
                    state=state,
                )
                expected = build_document(text, theme, fake_resolve, references=False)
                assert document.blocks[:kept] + rest.blocks == expected.blocks, (prefix, text)
                resumed += 1
    assert resumed > refused, "the opener was hardly ever read as written"


def test_an_opener_is_believed_only_when_it_was_read_as_its_containers() -> None:
    """
    `_opens`, with controls: the same shape against tokens that are and are not it.

    No source is known that makes a well-formed opener read as anything else
    -- the table rule, which would, needs a pipe in the line -- so the refusals
    here are made by hand: the opener indented into a code block, a different
    marker, and the right containers with something other than the break in
    them. After a closed fence the next line may be anything, and a delimiter
    row is the one a table would need; it is not one, and is believed.
    """
    source = "> ```\n> x\n> ```\n"
    point = _resume_point(_tokens(source), source, _line_starts(source))
    assert point is not None and point.line == 3 and point.opener == "> ***\n"
    assert _opens(_tokens(point.opener + "text\n"), point.shape)
    assert _opens(_tokens(point.opener), point.shape)
    after_a_delimiter_row = _tokens(point.opener + "|-\n")
    assert _opens(after_a_delimiter_row, point.shape)
    assert [token.type for token in after_a_delimiter_row][3] == "paragraph_open"

    assert not _opens(_tokens("    " + point.opener), point.shape)
    assert not _opens(_tokens("- ***\n"), point.shape)
    assert not _opens(_tokens("> text\n"), point.shape)
    assert not _opens(_tokens("> > ***\n"), point.shape)
    assert not _opens([], point.shape)


_QUOTE_SHAPE = (("blockquote_open", ">"), ("hr", "***"))
_ITEM_SHAPE = (("bullet_list_open", "-"), ("list_item_open", "-"), ("hr", "***"))


@pytest.mark.parametrize(
    ("source", "shape", "lines", "end", "outer_end", "last"),
    [
        # The unended `>` is the quote's line and not the fence's ...
        ("> ***\n> ~~~\n> \n>", _QUOTE_SHAPE, [""], 3, 4, True),
        # ... and with its newline it is both's.
        ("> ***\n> ~~~\n> \n>\n", _QUOTE_SHAPE, ["", ""], 4, 4, True),
        ("- ***\n  ```\n  a\n  b", _ITEM_SHAPE, ["a", "b"], 4, 4, True),
        # Not indented far enough: out of the item, and a block of its own.
        ("- ***\n  ```\n  a\n2", _ITEM_SHAPE, ["a"], 3, 3, False),
        # The fence's own line may close the opener's item and open more
        # containers on the way (not followed at all at first: the closing
        # token between the break and the fence was not stepped over).
        ("-    ***\n- > ```\n  > a\n  > b", _ITEM_SHAPE, ["a", "b"], 4, 4, True),
    ],
)
def test_a_fence_under_an_opener_is_read_exactly_as_the_text_stands(
    source: str,
    shape: tuple[tuple[str, str], ...],
    lines: list[str],
    end: int,
    outer_end: int,
    last: bool,
    theme: Theme,
) -> None:
    """
    `_leading_fence(..., shape, verbatim=True)`: the three facts a nested fence is shown by.

    The first two rows are the measured pair the function's docstring quotes;
    the stream reported the fence a line too long before `verbatim` existed.
    """
    found = _leading_fence(source, theme, shape, verbatim=True)
    assert found is not None
    assert [text_of(line) for line in found.lines] == lines
    assert (found.end, found.outer_end, found.last) == (end, outer_end, last)


def test_a_fence_in_another_top_level_block_is_not_the_opener_s_fence(theme: Theme) -> None:
    """
    The control for stepping over closing tokens: the outermost container must not close.

    `> ***` then `- ~~~`: the quote ends and a list begins, so the fence on the
    second line is in a different top-level block from the one the opener
    re-opened, and following it as that block's would give it the wrong `top`
    and keep the quote from committing.
    """
    assert _leading_fence("> ***\n- ~~~\n  a\n", theme, _QUOTE_SHAPE) is None
    assert _leading_fence("> ***\n> - ~~~\n>   a\n", theme, _QUOTE_SHAPE) is not None


@pytest.mark.parametrize("source", ["> a|b\n>-|-\n>", "> a|b\n> -|-\n> ", "> a|b\n>-|-\n>1|2\n>"])
def test_a_quoted_table_under_an_unended_quote_marker_does_not_crash_the_parse(
    source: str, theme: Theme
) -> None:
    """
    markdown-it 4.2.0 raises `IndexError` on these; `build_document` must not.

    The control is the library itself, asked directly: if an upgrade fixes it
    this test says so, and `advtext.markdown._parse` can go. What comes back
    is what the same text with its last line ended gives.
    """
    from markdown_it import MarkdownIt

    with pytest.raises(IndexError):
        MarkdownIt("commonmark").enable("table").parse(source)
    document = build_document(source, theme, fake_resolve)
    assert document.blocks == build_document(source + "\n", theme, fake_resolve).blocks
    assert any(isinstance(block, TableBlock) for block in document.blocks)
    assert all(where.span.end <= len(source) for where in document.sources)


# ----------------------------------------------------------------------
# Review 2, item 5b: a character the bound face has no glyph for.
#
# Real fonts, because which face lacks what is a fact about the files: the
# code face shipped here has no Greek, the prose face has no arrows, the math
# face has both, and nothing has CJK.
# ----------------------------------------------------------------------


def _chars(nodes: tuple[Node, ...]) -> list[tuple[str, str]]:
    return [
        (parse_font_key(node.font).face.value, chr(node.codepoint))
        for node in nodes
        if isinstance(node, CharNode)
    ]


def test_the_faces_lack_what_the_tests_below_say_they_lack(bundled_fonts: Path) -> None:
    from advtext import fontlib

    code, prose = fontlib.metrics(Face.CODE, 16.0), fontlib.metrics(Face.PROSE, 16.0)
    maths = fontlib.math_metrics(16.0)
    assert not code.has(ord("π")) and prose.has(ord("π"))
    assert not prose.has(ord("→")) and maths.has(ord("→")) and code.has(ord("→"))
    assert not prose.has(ord("∀")) and not code.has(ord("∀")) and maths.has(ord("∀"))
    assert not any(face.has(ord("速")) for face in (code, prose, maths))
    assert prose.has(0xFFFD)


def test_a_character_the_code_face_lacks_is_set_from_the_prose_face(
    theme: Theme, bundled_fonts: Path
) -> None:
    from advtext.style import fontlib_metrics

    (block,) = build_document("area `πr` done", theme, fontlib_metrics).blocks
    assert isinstance(block, TextBlock)
    assert _chars(block.material)[4:6] == [("prose", "π"), ("code", "r")]
    # The character is the character still: a copy of it is `π`.
    assert "".join(character for _, character in _chars(block.material)) == "areaπrdone"
    assert replaced_characters(block) == 0
    # It has the borrowed face's width, not nothing.
    borrowed = next(n for n in block.material if isinstance(n, CharNode) and n.codepoint == 0x3C0)
    assert char_measure(fontlib_metrics)(borrowed).width > 0
    # ... and there is no kern after a character that was stood in for.
    after = block.material.index(borrowed) + 1
    assert isinstance(block.material[after], CharNode)


def test_the_order_is_prose_then_math_then_code(theme: Theme, bundled_fonts: Path) -> None:
    from advtext.style import fontlib_metrics

    (block,) = build_document("a → b `x ∀ π`", theme, fontlib_metrics).blocks
    assert isinstance(block, TextBlock)
    faces = dict((character, face) for face, character in _chars(block.material))
    # The prose face lacks the arrow; math is asked before code and has it.
    assert faces["→"] == "math"
    # The code face lacks both: prose has the pi, only math has the quantifier.
    assert (faces["π"], faces["∀"]) == ("prose", "math")
    assert replaced_characters(block) == 0


def test_a_character_no_face_has_is_the_prose_faces_replacement_and_is_counted(
    theme: Theme, bundled_fonts: Path
) -> None:
    from advtext.style import fontlib_metrics

    source = (
        "# 速 title\n\n速度 is `速` here\n\n```\nv = 速度\n```\n\n"
        "| 速 | b |\n|---|---|\n| c | 速度 |\n"
    )
    document = build_document(source, theme, fontlib_metrics)
    heading, paragraph, code, table = document.blocks
    assert [replaced_characters(block) for block in document.blocks] == [1, 3, 2, 3]
    assert isinstance(paragraph, TextBlock) and isinstance(code, CodeBlock)
    assert _chars(paragraph.material)[:2] == [("prose", "�")] * 2
    # In a heading, a code span and a code block alike it is the regular prose face's.
    for nodes in (heading.material, code.lines[0]):  # type: ignore[union-attr]
        stood = [face for face, character in _chars(nodes) if character == "�"]
        assert stood and set(stood) == {"prose"}
    assert REPLACEMENT_CHARACTER == 0xFFFD
    # The source still has the characters; the block does not.
    assert "速度" in document.sources[1].top.of(source)


def test_what_draws_nothing_on_purpose_is_left_alone(theme: Theme, bundled_fonts: Path) -> None:
    from advtext.style import fontlib_metrics

    # A zero-width joiner, a soft hyphen, a variation selector, a combining
    # mark: none is replaced, whatever the face has.
    source = "a‍b­c️d́e"
    (block,) = build_document(source, theme, fontlib_metrics).blocks
    assert "".join(character for _, character in _chars(block.material)) == source  # type: ignore[union-attr]
    assert replaced_characters(block) == 0


def test_text_the_faces_cover_is_node_for_node_what_it_was(
    theme: Theme, bundled_fonts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    `demo/sample.md` never reaches the stand-in rule, so its material is what
    it was before the rule existed -- which the second half shows by putting
    the old behaviour back and comparing. The control is a document that does
    reach it.
    """
    import advtext.markdown as markdown_module
    from advtext.style import fontlib_metrics

    source = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(
        encoding="utf-8"
    )
    now = build_document(source, theme, fontlib_metrics)
    asked: list[int] = []

    def as_it_was(theme: Theme, resolve: object, key: FontKey, codepoint: int) -> tuple[str, int]:
        asked.append(codepoint)
        return key, codepoint

    monkeypatch.setattr(markdown_module, "_stand_in", as_it_was)
    before = build_document(source, theme, fontlib_metrics)
    assert asked == []
    assert now == before and len(now.blocks) > 30
    assert sum(replaced_characters(block) for block in now.blocks) == 0
    changed = build_document("a → b", theme, fontlib_metrics)
    assert asked == [ord("→")]
    monkeypatch.undo()
    assert build_document("a → b", theme, fontlib_metrics) != changed


def test_a_resolver_that_knows_only_the_bound_face_changes_nothing(theme: Theme) -> None:
    # A host with no math face, or a test's fake: a face that does not
    # resolve is skipped. Here only the code face lacks the character and no
    # other face resolves, so it is left exactly as it was.
    @dataclass(frozen=True, slots=True)
    class Ascii(FakeMetrics):
        def has(self, codepoint: int) -> bool:
            return codepoint < 0x80

    def resolve(key: FontKey) -> FontMetrics:
        spec = parse_font_key(key)
        if spec.face is not Face.CODE:
            raise KeyError(key)
        return Ascii(face=spec.face, size=float(spec.size))

    block = code_block("π = 3\n", theme, resolve)
    assert _chars(block.lines[0])[0] == ("code", "π")


# Until tranche 5 this file ended with seven tests of what the old views and the old
# stream did with a replaced character: `advtext.stream.StreamDocument` standing in for
# the same characters as one parse, `advtext.ui.units.UnitModel.copy_text` copying the
# character that was written, `advtext.spans` finding it, and the old ImGui draw backend
# drawing the stand-in in a real window. Those four modules are deleted. What is kept
# above is the parser's own half: which character is replaced, by what, and how many.

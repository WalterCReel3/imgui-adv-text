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

import pytest

from advtext.fontmetrics import Face, FontMetrics, GlyphBBox
from advtext.markdown import (
    CodeBlock,
    ColumnAlign,
    Document,
    RuleBlock,
    TableBlock,
    TextBlock,
    build_document,
)
from advtext.nodes import CharNode, FontKey, Glue, Kern, KernKind, Node, Penalty
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


def test_a_heading_deeper_than_level_three_is_set_as_level_three(theme: Theme) -> None:
    # Dropping it would make a level-five heading render as body text, which
    # reads as a parser failure rather than as a decision.
    block = convert("##### Deep\n", theme).blocks[0]
    assert isinstance(block, TextBlock)
    assert block.kind is BlockKind.HEADING_3


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

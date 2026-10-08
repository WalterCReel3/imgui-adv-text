r"""
`advtext.spans`: material indices against shipped indices.

The module recovers the correspondence by counting, without being told where
the breaker cut. So the test that matters is the one that *is* told:
`test_the_map_agrees_with_what_the_breaker_actually_did` wraps
`advtext.linebreak._line_nodes`, records which nodes of the paragraph each line
was built from **by object identity**, and derives the expected shipped index
of every material node from that. Nothing in that oracle shares a line of
reasoning with the code under test -- it does not count glue, it reads off what
happened -- and it runs over every text block of `demo/sample.md` and of a
second corpus chosen for the cases the sample lacks (lists, hard breaks, a
link that has to break), at several measures and all four alignments.

The rest check the things a consumer does with the map: a link across a break
is two runs whose text is the link's text, a marker is stepped over, a quote's
enclosing line is seen through, a block inside a larger shipment is found from
`index_count`, and a map built against the wrong commands raises instead of
returning something plausible.

Fonts are faked with round numbers, as in `tests/test_compose.py`; nothing here
opens a window or reads a font file.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import advtext.linebreak as linebreak
from advtext.fontmetrics import Face, FontMetrics, GlyphBBox
from advtext.markdown import (
    PARFILLSKIP,
    Block,
    CodeBlock,
    ColumnAlign,
    TableBlock,
    TextBlock,
    build_document,
)
from advtext.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    CharNode,
    Disc,
    FontKey,
    Glue,
    GlueSpec,
    Kern,
    Node,
    Penalty,
)
from advtext.pack import PackMode, hpack, vpack
from advtext.selection import Selection, SelectionModel
from advtext.shipout import DrawCmd, Glyph, Line, Point, SetGlue, ship
from advtext.spans import (
    ColourSpan,
    Decoration,
    ShippedRun,
    SpanMap,
    SpanMapError,
    code_position,
    colour_text,
    decorate,
    find_spans,
    index_count,
    map_code_block,
    map_material,
    map_table,
    map_text_block,
    map_text_boxes,
    material_text,
    span_rects,
)
from advtext.style import Align, BlockKind, Theme, char_measure, parse_font_key
from advtext.ui import PROSE_BREAKING, _aligned, _block_boxes, compose, compose_blocks
from advtext.units import sp_from_px

GLYPH = sp_from_px(10.0)
SPACE = sp_from_px(8.0)
MEASURE = sp_from_px(600.0)

SAMPLE = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(encoding="utf-8")

CORPUS = """\
# A heading long enough that at a narrow measure it has to break somewhere

Plain words then [a link whose text is long enough that it must break across
a line at any measure this test uses](https://example.com/a) and words after
it, with *emphasis*, **strong**, `inline code with spaces` and a second
[short link](https://example.com/b) near the end. A sentence. Another one.

A line with a hard break here\\
and the paragraph carries on after it for long enough to wrap at least once
more before it ends.

- a bullet with [a link](https://example.com/c) inside it and enough further
  words that the item wraps onto a second line under the hanging indent
- a second bullet

1. a numbered item with [another link](https://example.com/d) and more words
   so that this one wraps too, which it will at these widths
10. a wider marker

> A quoted paragraph with [a quoted link](https://example.com/e) in it that is
> long enough to wrap inside the bar.
>
> A second quoted paragraph, so the quote is a run of two blocks.

Last paragraph.
"""


@dataclass(frozen=True, slots=True)
class FakeMetrics:
    """
    Round numbers and no font: ten pixels a glyph, eight a space, no kerning.
    """

    face: Face
    size: float

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
        return float(SPACE if codepoint == 0x20 else GLYPH)

    def bbox(self, codepoint: int) -> GlyphBBox:
        return GlyphBBox(0.0, -0.2 * GLYPH, 0.9 * GLYPH, 0.7 * GLYPH)

    def kern(self, codepoint: int, following: int) -> float:
        return 0.0


def fake_resolve(key: FontKey) -> FontMetrics:
    spec = parse_font_key(key)
    return FakeMetrics(face=spec.face, size=float(spec.size))


MEASURE_FN = char_measure(fake_resolve)


@pytest.fixture
def theme() -> Theme:
    return Theme.build()


def blocks_of(source: str, theme: Theme) -> tuple[Block, ...]:
    return build_document(source, theme, fake_resolve).blocks


def text_blocks(source: str, theme: Theme) -> list[TextBlock]:
    return [block for block in blocks_of(source, theme) if isinstance(block, TextBlock)]


def shipped_alone(block: Block, theme: Theme, width: int) -> list[DrawCmd]:
    """
    One block composed and shipped by itself, which is the phase 2 arrangement.
    """
    box = compose_blocks((block,), theme, width, MEASURE_FN)
    return ship(box, Point(0, box.height), measure=MEASURE_FN)


def items(cmds: Sequence[DrawCmd]) -> dict[int, Glyph | SetGlue]:
    return {cmd.index: cmd for cmd in cmds if isinstance(cmd, Glyph | SetGlue)}


def aligned(block: TextBlock, align: Align) -> TextBlock:
    return replace(block, style=replace(block.style, align=align))


def block_with(source: str, theme: Theme, needle: str) -> TextBlock:
    """
    The text block whose text contains `needle`, or a loud failure.
    """
    for block in text_blocks(source, theme):
        if needle in material_text(block).text:
            return block
    raise AssertionError(f"no block contains {needle!r}; the fixture stopped being one")


# -- the oracle ------------------------------------------------------------


@dataclass
class _Recorded:
    body: Sequence[Node]
    out: list[Node]


@dataclass
class _Case:
    """
    One block set at one measure: its line boxes, the commands shipped from
    them, and the `_line_nodes` calls `_assemble` made to build those lines.
    """

    block: TextBlock
    width: int
    boxes: tuple[Box, ...]
    cmds: list[DrawCmd]
    final: list[_Recorded]


def _takes_index(node: Node) -> bool:
    return isinstance(node, CharNode | Glue)


def expected_from_breaker(case: _Case) -> tuple[list[int | None], int, int]:
    """
    What the map should be, read off what the breaker did.

    A node of a line that **is** a node of the paragraph body (the same object)
    came from the material at that position, and anything else on the line was
    inserted. Its shipped index is its ordinal among the index-taking nodes
    shipped so far.

    Returns the expected `shipped` list, how many material glue nodes were
    discarded, and how many shipped items were insertions -- the last two so
    the caller can assert the run was not vacuous.
    """
    block = case.block
    expected: list[int | None] = [None] * len(block.material)
    cursor = 0
    inserted = 0
    for number, (call, box) in enumerate(zip(case.final, case.boxes, strict=True)):
        position = {id(node): j for j, node in enumerate(call.body)}
        assert len(position) == len(call.body), "the body repeats an object; identity is useless"
        on_line = [node for node in call.out if _takes_index(node)]
        lead = index_count(box) - len(on_line)
        assert lead == 0 or (number == 0 and block.marker), "only a marker may precede a line"
        inserted += lead
        cursor += lead
        for node in on_line:
            j = position.get(id(node))
            if j is not None and j < len(block.material):
                expected[j] = cursor
            else:
                inserted += 1
            cursor += 1
    discarded = sum(
        1 for j, node in enumerate(block.material) if isinstance(node, Glue) and expected[j] is None
    )
    return expected, discarded, inserted


def _settings() -> Iterator[tuple[str, Align, float]]:
    """
    Which block is set how. Not the full product, and the reason is measured:
    with these fake metrics a ragged setting of `demo/sample.md` takes about 70
    times as long to break as a justified one (9.5s against 0.14s at 600px for
    its text blocks), so the sample is set ragged at one narrow measure only
    and the short corpus carries the other alignments.
    """
    for width in (140.0, 230.0, 377.0, 600.0, 1500.0):
        yield SAMPLE, Align.JUSTIFY, width
        yield CORPUS, Align.JUSTIFY, width
    yield SAMPLE, Align.LEFT, 140.0
    yield CORPUS, Align.LEFT, 377.0
    for align in (Align.LEFT, Align.CENTER, Align.RIGHT):
        for width in (140.0, 230.0):
            yield CORPUS, align, width


@pytest.fixture(scope="module")
def cases() -> list[_Case]:
    """
    Every setting, broken once with `advtext.linebreak._line_nodes` wrapped.

    The last `len(boxes)` recorded calls are `_assemble`'s, one per line in
    order; the ones before are the search trying candidates and are dropped.
    The commands are shipped from the boxes stacked as they stand, which is
    index-for-index what `compose_blocks` ships for an unquoted block; the real
    compose path is exercised by the tests further down.
    """
    theme = Theme.build()
    calls: list[_Recorded] = []
    original = linebreak._line_nodes

    def spy(body: Sequence[Node], *args: object) -> list[Node]:
        out = original(body, *args)  # type: ignore[arg-type]
        calls.append(_Recorded(body, list(out)))
        return out

    built: list[_Case] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(linebreak, "_line_nodes", spy)
        for source, align, width_px in _settings():
            for plain in text_blocks(source, theme):
                block = aligned(plain, align)
                width = sp_from_px(width_px)
                calls.clear()
                boxes = _block_boxes(block, theme, width, MEASURE_FN, PROSE_BREAKING)
                final = calls[-len(boxes) :]
                assert len(final) == len(boxes)
                page = vpack(list(boxes)).box
                cmds = ship(page, Point(0, page.height), measure=MEASURE_FN)
                built.append(_Case(block, width, boxes, cmds, final))
    return built


def test_the_map_agrees_with_what_the_breaker_actually_did(cases: list[_Case]) -> None:
    multi_line = 0
    total_discarded = 0
    total_inserted = 0
    with_lead = 0
    for case in cases:
        expected, discarded, inserted = expected_from_breaker(case)
        block = case.block

        from_boxes = map_text_boxes(block, case.boxes)
        assert list(from_boxes.shipped) == expected, (block.kind, block.style.align, case.width)
        assert from_boxes.count == index_count(case.boxes)

        # And the same answer from commands alone, which is what a view holds.
        from_cmds = map_text_block(block, case.cmds)
        assert from_cmds == from_boxes

        multi_line += len(case.boxes) > 1
        total_discarded += discarded
        total_inserted += inserted
        with_lead += block.style.align in (Align.CENTER, Align.RIGHT)

    # Guards against the loop quietly covering nothing interesting.
    assert len(cases) > 300
    assert multi_line > 200, "hardly any case broke across lines"
    assert total_discarded > 1500, "hardly any glue was discarded, so nothing was tested"
    assert total_inserted > 2500
    assert with_lead > 30, "no case had a \\leftskip to infer"


def test_every_mapped_node_is_the_shipped_item_it_claims_to_be(cases: list[_Case]) -> None:
    """
    Independent of the oracle: read the commands and compare what is there.
    """
    checked = 0
    for case in cases:
        block = case.block
        by_index = items(case.cmds)
        span_map = map_text_block(block, case.cmds)
        previous = -1
        for index, node in enumerate(block.material):
            shipped = span_map.shipped_index(index)
            if shipped is None:
                assert not isinstance(node, CharNode), "a character was reported as not shipped"
                continue
            assert shipped > previous, "the map is not monotone in reading order"
            previous = shipped
            cmd = by_index[shipped]
            if isinstance(node, CharNode):
                assert isinstance(cmd, Glyph)
                assert (cmd.font, cmd.codepoint) == (node.font, node.codepoint)
            else:
                assert isinstance(node, Glue) and isinstance(cmd, SetGlue)
                assert cmd.natural == node.spec.width
            checked += 1
        # `material_index` is linear, so the inverse is sampled, not swept.
        for index in range(0, len(block.material), 37):
            shipped = span_map.shipped_index(index)
            if shipped is not None:
                assert span_map.material_index(shipped) == index
    assert checked > 30_000


def test_the_index_rule_here_is_the_one_ship_out_uses(theme: Theme) -> None:
    """
    `index_count` repeats ship-out's rule; this is what stops the two drifting.
    """
    for source in (SAMPLE, CORPUS):
        document = build_document(source, theme, fake_resolve)
        box = compose(document, theme, MEASURE, MEASURE_FN)
        cmds = ship(box, Point(0, box.height), measure=MEASURE_FN)
        assert index_count(box) == len(items(cmds)) > 500


# -- links -----------------------------------------------------------------


def _selected(cmds: Sequence[DrawCmd], runs: Sequence[ShippedRun]) -> str:
    model = SelectionModel.from_commands(cmds)
    return " ".join(model.text(Selection(run.start, run.end)) for run in runs)


def test_a_link_broken_across_lines_is_one_run_per_line_and_reads_as_its_text(
    theme: Theme,
) -> None:
    block = block_with(CORPUS, theme, "must break across")
    link = block.links[0]
    assert link.target == "https://example.com/a"
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)

    runs = span_map.link_runs(link)
    assert len(runs) >= 2, "the link fits on one line, so this test shows nothing"
    assert [run.line for run in runs] == list(range(runs[0].line, runs[0].line + len(runs)))
    assert _selected(cmds, runs) == (
        "a link whose text is long enough that it must break across "
        "a line at any measure this test uses"
    )

    by_index = items(cmds)
    lines = [cmd for cmd in cmds if isinstance(cmd, Line)]
    for run in runs:
        # Each run starts and ends on a letter of the link: no \rightskip, no
        # interword space left dangling at a line end.
        assert isinstance(by_index[run.start], Glyph)
        assert isinstance(by_index[run.end - 1], Glyph)
        line = lines[run.line]
        assert line.start <= run.start < run.end <= line.end
    # The glue the breaker discarded at each break is in the span and in no run.
    covered = sum(run.end - run.start for run in runs)
    in_span = sum(
        1 for node in block.material[link.start : link.end] if isinstance(node, CharNode | Glue)
    )
    assert in_span - covered == len(runs) - 1


def test_a_links_rects_are_one_per_line_and_match_a_selection_of_the_same_items(
    theme: Theme,
) -> None:
    block = block_with(CORPUS, theme, "must break across")
    cmds = shipped_alone(block, theme, MEASURE)
    model = SelectionModel.from_commands(cmds)
    runs = map_text_block(block, cmds).link_runs(block.links[0])
    rects = span_rects(model, runs)
    assert len(rects) == len(runs)
    assert len({rect.y for rect in rects}) == len(rects), "two runs landed on one line"
    assert all(rect.width > 0 for rect in rects)
    # Ten pixels a glyph, eight a space, set ragged so nothing is stretched:
    # the first run's width is exactly its characters.
    ragged = aligned(block, Align.LEFT)
    cmds = shipped_alone(ragged, theme, MEASURE)
    first = map_text_block(ragged, cmds).link_runs(ragged.links[0])[0]
    by_index = items(cmds)
    glyphs = sum(isinstance(by_index[i], Glyph) for i in range(first.start, first.end))
    spaces = (first.end - first.start) - glyphs
    rect = span_rects(SelectionModel.from_commands(cmds), [first])[0]
    assert rect.width == glyphs * GLYPH + spaces * SPACE


def test_a_second_link_in_the_same_block_is_found_after_the_first(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    cmds = shipped_alone(block, theme, MEASURE)
    runs = map_text_block(block, cmds).link_runs(block.links[1])
    assert _selected(cmds, runs) == "short link"


@pytest.mark.parametrize(
    ("needle", "text"),
    [("a bullet with", "a link"), ("a numbered item", "another link")],
)
def test_a_link_in_a_list_item_is_not_shifted_by_the_marker(
    theme: Theme, needle: str, text: str
) -> None:
    block = block_with(CORPUS, theme, needle)
    assert block.marker, "the fixture is not a list item"
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)
    assert _selected(cmds, span_map.link_runs(block.links[0])) == text
    # The marker's own items map back to nothing in the material.
    first_material = span_map.shipped_index(0)
    assert first_material is not None and first_material >= 2
    assert all(span_map.material_index(index) is None for index in range(first_material))


def test_a_marker_that_is_not_where_the_map_expects_raises(theme: Theme) -> None:
    """
    The prefix is knowledge of `advtext.ui._hang_marker`; if it stops being
    true the map must refuse rather than shift every link in every list.
    """
    block = block_with(CORPUS, theme, "a bullet with")
    plain = replace(block, marker=())
    cmds = shipped_alone(plain, theme, MEASURE)
    with pytest.raises(SpanMapError, match="marker"):
        map_text_block(block, cmds)
    # And the other way round: a marker shipped that the block does not declare.
    with pytest.raises(SpanMapError):
        map_text_block(plain, shipped_alone(block, theme, MEASURE))


def test_a_quoted_paragraph_is_mapped_through_the_line_that_encloses_the_quote(
    theme: Theme,
) -> None:
    block = block_with(CORPUS, theme, "A quoted paragraph")
    assert block.quote_depth == 1
    cmds = shipped_alone(block, theme, MEASURE)
    lines = [cmd for cmd in cmds if isinstance(cmd, Line)]
    assert lines[0].start == 0 and lines[0].end == lines[-1].end, "no enclosing line: fixture"
    span_map = map_text_block(block, cmds)
    assert len(span_map.lines) == len(lines) - 1
    assert _selected(cmds, span_map.link_runs(block.links[0])) == "a quoted link"


def test_every_block_of_a_whole_shipment_is_found_from_index_count(theme: Theme) -> None:
    """
    The other arrangement: one `ship` for the document, as `DocumentView` does
    today. A block's base is the index count of the line boxes before it.
    """
    blocks = blocks_of(CORPUS, theme)
    box = compose_blocks(blocks, theme, MEASURE, MEASURE_FN)
    cmds = ship(box, Point(0, box.height), measure=MEASURE_FN)
    by_index = items(cmds)
    model = SelectionModel.from_commands(cmds)

    base = 0
    links_seen: list[str] = []
    for block in blocks:
        boxes = _block_boxes(block, theme, MEASURE, MEASURE_FN, PROSE_BREAKING)
        count = index_count(boxes)
        if isinstance(block, TextBlock):
            span_map = map_text_block(block, cmds, start=base, stop=base + count)
            assert (span_map.base, span_map.count) == (base, count)
            assert span_map == map_text_boxes(block, boxes, base=base)
            for index, node in enumerate(block.material):
                if isinstance(node, CharNode):
                    shipped = span_map.shipped_index(index)
                    assert shipped is not None
                    cmd = by_index[shipped]
                    assert isinstance(cmd, Glyph) and cmd.codepoint == node.codepoint
            for link in block.links:
                runs = span_map.link_runs(link)
                links_seen.append(" ".join(model.text(Selection(r.start, r.end)) for r in runs))
        base += count
    assert base == len(by_index)
    assert links_seen == [
        "a link whose text is long enough that it must break across "
        "a line at any measure this test uses",
        "short link",
        "a link",
        "another link",
        "a quoted link",
    ]


# -- the cases the counting rules exist for --------------------------------


def test_a_hard_break_keeps_its_fill_glue_and_loses_nothing_after_it(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "a hard break here")
    fills = [i for i, node in enumerate(block.material) if node == Glue(PARFILLSKIP)]
    assert len(fills) == 1, "the fixture has no hard break in it"
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)
    fill = span_map.shipped_index(fills[0])
    assert fill is not None, "the fill before a hard break is set, not discarded"
    line = span_map.line_of(fill)
    assert line is not None
    # It is the last-but-one item on its line: only \rightskip follows.
    assert fill == span_map.base + span_map.lines[line][1] - 2
    after = span_map.shipped_index(fills[0] + 2)
    assert after is not None and span_map.line_of(after) == line + 1


def _chars(text: str) -> list[Node]:
    key = Theme.build().style(BlockKind.PARAGRAPH).font.key
    return [CharNode(key, ord(ch)) for ch in text]


def _paragraph(theme: Theme, material: Sequence[Node], align: Align = Align.JUSTIFY) -> TextBlock:
    style = replace(theme.style(BlockKind.PARAGRAPH), align=align)
    return TextBlock(kind=BlockKind.PARAGRAPH, style=style, material=tuple(material))


def test_a_blank_line_between_two_hard_breaks_maps_to_nothing(theme: Theme) -> None:
    """
    The line with no anchor on it. Its only shipped item is an inserted
    `\\rightskip`; the second break's fill glue is pruned from its start.
    """
    stop: tuple[Node, ...] = (Penalty(INF_PENALTY), Glue(PARFILLSKIP), Penalty(EJECT_PENALTY))
    block = _paragraph(theme, [*_chars("ab"), *stop, *stop, *_chars("cd")])
    cmds = shipped_alone(block, theme, MEASURE)
    lines = [cmd for cmd in cmds if isinstance(cmd, Line)]
    assert len(lines) == 3 and lines[1].end - lines[1].start == 1, "not the layout expected"
    span_map = map_text_block(block, cmds)
    assert span_map.shipped == (0, 1, None, 2, None, None, None, None, 5, 6)
    assert span_map.material_index(lines[1].start) is None


def test_material_ending_in_glue_loses_that_glue_to_the_paragraph_end(theme: Theme) -> None:
    space = Glue(GlueSpec(width=SPACE))
    block = _paragraph(theme, [*_chars("ab"), space, *_chars("cd"), space])
    span_map = map_text_block(block, shipped_alone(block, theme, MEASURE))
    assert span_map.shipped == (0, 1, 2, 3, 4, None)
    # ab, space, cd, then \parfillskip and \rightskip, which are nobody's.
    assert span_map.count == 7


def test_material_opening_with_glue_keeps_it_under_every_alignment(theme: Theme) -> None:
    """
    Nothing is pruned from a paragraph's start, which is how the lead is learnt.
    """
    space = Glue(GlueSpec(width=SPACE))
    for align, lead in ((Align.JUSTIFY, 0), (Align.LEFT, 0), (Align.RIGHT, 1), (Align.CENTER, 1)):
        block = _paragraph(theme, [space, *_chars("ab")], align)
        span_map = map_text_block(block, shipped_alone(block, theme, MEASURE))
        assert span_map.shipped == (lead, lead + 1, lead + 2), align


def test_a_box_in_the_material_is_an_anchor_as_wide_as_what_it_ships(theme: Theme) -> None:
    space = Glue(GlueSpec(width=SPACE))
    inner = hpack([*_chars("xy"), space, *_chars("z")], measure=MEASURE_FN).box
    block = _paragraph(theme, [*_chars("a"), space, inner, space, *_chars("b")])
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)
    assert span_map.shipped == (0, 1, 2, 6, 7)
    assert span_map.extent == (1, 1, 4, 1, 1)
    assert span_map.runs(2, 3) == (ShippedRun(0, 2, 6),)
    assert span_map.material_index(4) == 2


def test_a_table_cell_can_be_mapped_as_unbroken_material(theme: Theme) -> None:
    """
    Not wired up for `TableBlock` (see the module docstring), but the piece a
    cell needs is measured here against today's cell layout: `\\hss` either
    side by alignment, no paragraph ending.
    """
    table = next(b for b in blocks_of(SAMPLE, theme) if isinstance(b, TableBlock))
    cell = table.rows[0][1]
    assert sum(isinstance(node, Glue) for node in cell.material) >= 1
    for align, lead in ((ColumnAlign.LEFT, 0), (ColumnAlign.RIGHT, 1), (ColumnAlign.CENTER, 1)):
        box = hpack(
            [Kern(width=1), *_aligned(cell.material, align), Kern(width=1)],
            sp_from_px(900.0),
            PackMode.EXACTLY,
            measure=MEASURE_FN,
        ).box
        span_map = map_material(cell.material, [box], paragraph=False)
        mapped = [index for index in span_map.shipped if index is not None]
        assert mapped == list(range(lead, lead + len(mapped)))
        assert len(mapped) == sum(isinstance(n, CharNode | Glue) for n in cell.material)


# -- refusing --------------------------------------------------------------


def test_commands_from_a_different_block_raise_rather_than_map(theme: Theme) -> None:
    first, second = text_blocks(CORPUS, theme)[1:3]
    with pytest.raises(SpanMapError):
        map_text_block(first, shipped_alone(second, theme, MEASURE))


def test_a_slice_that_is_not_a_whole_number_of_lines_raises(theme: Theme) -> None:
    blocks = blocks_of(CORPUS, theme)
    box = compose_blocks(blocks, theme, MEASURE, MEASURE_FN)
    cmds = ship(box, Point(0, box.height), measure=MEASURE_FN)
    block = blocks[1]
    assert isinstance(block, TextBlock)
    with pytest.raises(SpanMapError, match="whole number of lines"):
        map_text_block(block, cmds, start=3, stop=40)


def test_a_discretionary_in_the_material_is_refused(theme: Theme) -> None:
    block = _paragraph(theme, [*_chars("ab"), Disc(), *_chars("cd")])
    with pytest.raises(SpanMapError, match="discretionary"):
        map_text_boxes(block, [])


def test_one_changed_character_is_caught(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "Last paragraph")
    cmds = shipped_alone(block, theme, MEASURE)
    material = list(block.material)
    material[3] = _chars("Q")[0]
    with pytest.raises(SpanMapError, match=r"material\[3\]"):
        map_text_block(replace(block, material=tuple(material)), cmds)


# -- runs ------------------------------------------------------------------


def test_runs_of_nothing_and_of_only_discarded_material_are_empty(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    span_map = map_text_block(block, shipped_alone(block, theme, MEASURE))
    assert span_map.runs(5, 5) == ()
    discarded = next(
        i
        for i, node in enumerate(block.material)
        if isinstance(node, Glue) and span_map.shipped[i] is None
    )
    assert span_map.runs(discarded, discarded + 1) == ()
    whole = span_map.runs(0, len(block.material))
    assert len(whole) == len(span_map.lines)
    assert span_map.runs(-10, 10**6) == whole


def test_a_search_match_in_the_blocks_text_becomes_runs_over_those_words(theme: Theme) -> None:
    """
    Text coordinates, for find-in-document: search `material_text`, map the hit.
    """
    block = block_with(CORPUS, theme, "must break across")
    text = material_text(block)
    assert "inline code with spaces" in text.text
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)
    for needle in ("inline code with spaces", "must break across a line", "Another one."):
        at = text.text.index(needle)
        span = text.span(at, at + len(needle))
        assert span is not None
        assert _selected(cmds, span_map.runs(*span)) == needle
    assert text.span(0, 0) is None


def test_material_text_writes_a_hard_break_as_a_newline(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "a hard break here")
    assert "a hard break here\nand the paragraph" in material_text(block).text


# -- code ------------------------------------------------------------------

CODE = """\
```python
def f(x):
\treturn x  # tab

print(f(1))
```
"""


def _code(theme: Theme) -> CodeBlock:
    block = blocks_of(CODE, theme)[0]
    assert isinstance(block, CodeBlock)
    return block


def test_a_code_blocks_flat_index_is_its_shipped_index(theme: Theme) -> None:
    block = _code(theme)
    cmds = shipped_alone(block, theme, MEASURE)
    by_index = items(cmds)
    span_map = map_code_block(block)
    assert (
        span_map.count
        == len(by_index)
        == index_count(_block_boxes(block, theme, MEASURE, MEASURE_FN, PROSE_BREAKING))
    )
    lines = [cmd for cmd in cmds if isinstance(cmd, Line)]
    assert span_map.lines == tuple((line.start, line.end) for line in lines)
    assert lines[2].start == lines[2].end, "the blank source line should be an empty line"

    text = material_text(block)
    assert text.text == "def f(x):\n    return x  # tab\n\nprint(f(1))"
    for offset, flat in enumerate(text.indices):
        if flat is None:
            assert text.text[offset] == "\n"
            continue
        shipped = span_map.shipped_index(flat)
        assert shipped is not None
        cmd = by_index[shipped]
        assert isinstance(cmd, Glyph) and chr(cmd.codepoint) == text.text[offset]


def test_a_colour_span_given_as_line_and_column_lands_on_those_characters(theme: Theme) -> None:
    block = _code(theme)
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_code_block(block)
    # `return`, after the tab has become four spaces.
    start = code_position(block, 1, 4)
    runs = span_map.runs(start, code_position(block, 1, 10))
    assert runs == (ShippedRun(1, start, start + 6),)
    assert _selected(cmds, runs) == "return"
    # A span over the blank line is one run per non-empty line it touches.
    across = span_map.runs(code_position(block, 1, 11), code_position(block, 3, 5))
    assert [run.line for run in across] == [1, 3]
    with pytest.raises(IndexError):
        code_position(block, 2, 1)


def test_a_based_map_reports_absolute_indices() -> None:
    span_map = SpanMap(base=100, count=3, shipped=(0, None, 2), extent=(1, 0, 1), lines=((0, 3),))
    assert span_map.shipped_index(0) == 100
    assert span_map.shipped_index(1) is None
    assert span_map.material_index(102) == 2
    assert span_map.material_index(101) is None
    assert span_map.line_of(102) == 0 and span_map.line_of(99) is None
    assert span_map.runs(0, 3) == (ShippedRun(0, 100, 101), ShippedRun(0, 102, 103))


def test_vpack_is_not_needed_to_count_a_blocks_lines(theme: Theme) -> None:
    """
    `index_count` over loose line boxes equals the count once they are stacked,
    which is the claim that lets a caller sum it block by block.
    """
    block = block_with(CORPUS, theme, "must break across")
    boxes = _block_boxes(block, theme, MEASURE, MEASURE_FN, PROSE_BREAKING)
    assert (
        index_count(boxes)
        == index_count(vpack(list(boxes)).box)
        == sum(index_count(box) for box in boxes)
    )


# -- decoration: colour spans and links as things to draw ------------------
#
# `decorate` is what turns "this stretch of this block" into ink ranges over
# shipped indices, rectangles and link areas. Each test reads the result back
# through the shipped commands -- which glyphs an ink range covers, what text a
# link's runs select -- so a range that is off by one item is a different word
# and not a slightly different number.

RED, GREEN, BLUE, AMBER = 0xFF0000FF, 0xFF00FF00, 0xFFFF0000, 0xFF00BFFF


def _decorated(
    block: TextBlock | CodeBlock, theme: Theme, **kwargs: object
) -> tuple[Decoration, list[DrawCmd]]:
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = (
        map_code_block(block) if isinstance(block, CodeBlock) else map_text_block(block, cmds)
    )
    model = SelectionModel.from_commands(cmds)
    links = block.links if isinstance(block, TextBlock) else ()
    return decorate(span_map, model, links=links, **kwargs), cmds  # type: ignore[arg-type]


def _inked_text(cmds: Sequence[DrawCmd], inks: Sequence[tuple[int, int, int]], colour: int) -> str:
    """
    The characters whose glyph index falls in an ink range of `colour`, in order.
    """
    by_index = items(cmds)
    out: list[str] = []
    for start, end, ink in inks:
        if ink != colour:
            continue
        for index in range(start, end):
            cmd = by_index[index]
            out.append(chr(cmd.codepoint) if isinstance(cmd, Glyph) else " ")
        out.append("|")
    return "".join(out)


def test_a_block_with_nothing_to_decorate_decorates_nothing(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "Last paragraph")
    decoration, _ = _decorated(block, theme, link_ink=BLUE, underline=(2, 1))
    assert decoration == Decoration()
    assert not decoration


def test_a_link_across_two_lines_is_one_area_with_a_rect_and_an_underline_per_line(
    theme: Theme,
) -> None:
    block = block_with(CORPUS, theme, "must break across")
    offset, thickness = sp_from_px(2.0), sp_from_px(1.0)
    decoration, cmds = _decorated(
        block, theme, number=7, link_ink=BLUE, underline=(offset, thickness)
    )
    first, second = decoration.links
    assert (first.target, first.block, first.number) == ("https://example.com/a", 7, 0)
    assert (second.target, second.block, second.number) == ("https://example.com/b", 7, 1)
    # One link, several lines: one area, one rect a line, and the runs read as
    # the link's text.
    assert len(first.runs) >= 2 and len(first.rects) == len(first.runs)
    assert _selected(cmds, first.runs) == (
        "a link whose text is long enough that it must break across "
        "a line at any measure this test uses"
    )
    assert len(second.rects) == 1

    # An underline under every line of every link, as wide as the link's rect
    # on that line, the stated distance below that line's baseline.
    rects = [*first.rects, *second.rects]
    assert len(decoration.underlines) == len(rects)
    baselines = {
        (line.y - line.height): line.y
        for line in cmds
        if isinstance(line, Line) and line.end > line.start
    }
    for (under, colour), rect in zip(decoration.underlines, rects, strict=True):
        assert colour == BLUE
        assert (under.x, under.width, under.height) == (rect.x, rect.width, thickness)
        assert under.y == baselines[rect.y] + offset

    # The link's glyphs, and only they, are in the link ink.
    assert (
        _inked_text(cmds, decoration.inks, BLUE).replace("|", " ").split()
        == (
            "a link whose text is long enough that it must break across "
            "a line at any measure this test uses short link"
        ).split()
    )
    assert decoration.marks == ()


def test_a_point_is_on_a_link_exactly_where_its_text_is(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    decoration, _ = _decorated(block, theme, link_ink=BLUE)
    link = decoration.links[0]
    for rect in link.rects:
        assert link.contains(rect.x, rect.y)
        assert link.contains(rect.x + rect.width - 1, rect.y + rect.height - 1)
        assert not link.contains(rect.x - 1, rect.y)
        assert not link.contains(rect.x + rect.width, rect.y)
    top = min(rect.y for rect in link.rects)
    assert not link.contains(link.rects[0].x, top - 1)
    # The other link of the paragraph is somewhere else.
    other = decoration.links[1]
    assert not other.contains(link.rects[0].x, link.rects[0].y)


def test_unstyled_links_are_still_found_and_draw_nothing(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    styled, _ = _decorated(block, theme, link_ink=BLUE, underline=(2, 1))
    plain, _ = _decorated(block, theme)
    assert plain.links == styled.links
    assert plain.inks == () and plain.underlines == () and plain.marks == ()
    # A zero thickness is ink without an underline.
    inked, _ = _decorated(block, theme, link_ink=BLUE, underline=(2, 0))
    assert inked.inks == styled.inks and inked.underlines == ()


def test_a_find_hit_marks_every_occurrence_and_survives_a_line_break(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    hits = find_spans(block, "link", mark=AMBER)
    assert len(hits) == 2
    decoration, cmds = _decorated(block, theme, colours=hits)
    model = SelectionModel.from_commands(cmds)
    assert [colour for _, colour in decoration.marks] == [AMBER, AMBER]
    for (rect, _), hit in zip(decoration.marks, hits, strict=True):
        (run,) = map_text_block(block, cmds).runs(hit.start, hit.end)
        assert model.text(Selection(run.start, run.end)) == "link"
        assert rect == model.rects(Selection(run.start, run.end))[0]
    assert decoration.inks == ()

    # A phrase set across a break is found as one hit and marked on both lines.
    phrase = "must break across a line"
    (span,) = find_spans(block, phrase, mark=AMBER)
    crossing, cmds = _decorated(block, theme, colours=[span])
    runs = map_text_block(block, cmds).runs(span.start, span.end)
    assert len(runs) == 2, "the phrase did not straddle a break at this measure"
    assert len(crossing.marks) == 2
    assert _selected(cmds, runs) == phrase

    assert find_spans(block, "", mark=AMBER) == []
    assert find_spans(block, "LINK", mark=AMBER) == []
    assert len(find_spans(block, "LINK", mark=AMBER, ignore_case=True)) == 2


def test_syntax_colours_on_a_code_block_ink_exactly_their_tokens(theme: Theme) -> None:
    block = _code(theme)
    tokens = [
        ColourSpan(code_position(block, 0, 0), code_position(block, 0, 3), ink=RED),  # def
        ColourSpan(code_position(block, 1, 4), code_position(block, 1, 10), ink=RED),  # return
        ColourSpan(code_position(block, 1, 14), code_position(block, 1, 19), ink=GREEN),  # # tab
    ]
    decoration, cmds = _decorated(block, theme, colours=tokens)
    assert _inked_text(cmds, decoration.inks, RED) == "def|return|"
    assert _inked_text(cmds, decoration.inks, GREEN) == "# tab|"
    # Sorted and non-overlapping, which is what the backend bisects on.
    starts = [start for start, _, _ in decoration.inks]
    assert starts == sorted(starts)
    assert all(a[1] <= b[0] for a, b in zip(decoration.inks, decoration.inks[1:], strict=False))
    # The same span given in text coordinates.
    text = material_text(block).text
    at = text.index("return")
    assert colour_text(block, at, at + 6, ink=RED) == tokens[1]
    assert colour_text(block, text.index("\n"), text.index("\n") + 1, ink=RED) is None


def test_where_inks_overlap_the_later_span_wins_and_any_span_beats_the_link_ink(
    theme: Theme,
) -> None:
    block = block_with(CORPUS, theme, "must break across")
    whole = find_spans(block, "long enough", ink=RED)
    inner = find_spans(block, "enough", ink=GREEN)
    decoration, cmds = _decorated(block, theme, colours=[*whole, *inner], link_ink=BLUE)
    assert _inked_text(cmds, decoration.inks, GREEN) == "enough|"
    assert _inked_text(cmds, decoration.inks, RED) == "long |"
    blue = _inked_text(cmds, decoration.inks, BLUE)
    assert "long" not in blue and "enough" not in blue and "whose text is " in blue
    # Given the other way round, the outer span paints over the inner one.
    flipped, cmds = _decorated(block, theme, colours=[*inner, *whole], link_ink=BLUE)
    assert _inked_text(cmds, flipped.inks, GREEN) == ""
    assert _inked_text(cmds, flipped.inks, RED) == "long enough|"
    for a, b in zip(decoration.inks, decoration.inks[1:], strict=False):
        assert a[1] <= b[0]


def test_a_span_over_only_discarded_material_decorates_nothing(theme: Theme) -> None:
    block = block_with(CORPUS, theme, "must break across")
    cmds = shipped_alone(block, theme, MEASURE)
    span_map = map_text_block(block, cmds)
    discarded = next(
        index
        for index, node in enumerate(block.material)
        if isinstance(node, Glue) and span_map.shipped[index] is None and index > 3
    )
    decoration, _ = _decorated(
        block, theme, colours=[ColourSpan(discarded, discarded + 1, ink=RED, mark=AMBER)]
    )
    assert decoration.inks == () and decoration.marks == ()


# -- table cells -------------------------------------------------------------

LINKED_TABLE = (
    "| Name | What it is | Where |\n"
    "|:-----|:----------:|------:|\n"
    "| alpha | A long description with [a link in the middle](https://example.com/t1) "
    "of it | [here](https://example.com/t2) |\n"
    "| bravo | Short | there and [also here](https://example.com/t3) |\n"
)


def _table(theme: Theme) -> TableBlock:
    (block,) = blocks_of(LINKED_TABLE, theme)
    assert isinstance(block, TableBlock)
    return block


@pytest.mark.parametrize("width_px", [1400.0, 420.0, 300.0])
def test_every_cell_of_a_table_maps_to_the_items_shipped_for_it(
    theme: Theme, width_px: float
) -> None:
    # Wide enough that nothing wraps, and twice narrow enough that rows do:
    # the two row shapes composition builds, and both alignments that put glue
    # ahead of a cell's text.
    block = _table(theme)
    width = sp_from_px(width_px)
    box = compose_blocks((block,), theme, width, MEASURE_FN)
    cmds = ship(box, Point(0, box.height), measure=MEASURE_FN)
    by_index = items(cmds)
    cells = map_table(block, box)
    lines = sum(isinstance(cmd, Line) for cmd in cmds)
    assert (lines > 4) == (width_px < 1000.0), "the fixture did not wrap where it should"

    every = [cell for row in (block.header, *block.rows) for cell in row]
    assert [cell for cell, _ in cells] == every
    claimed: list[int] = []
    for cell, span_map in cells:
        for index, node in enumerate(cell.material):
            shipped = span_map.shipped_index(index)
            if isinstance(node, CharNode):
                assert shipped is not None
                cmd = by_index[shipped]
                assert isinstance(cmd, Glyph) and cmd.codepoint == node.codepoint
                claimed.append(shipped)
    # No shipped glyph is claimed by two cells, and none is left over.
    glyphs = [index for index, cmd in by_index.items() if isinstance(cmd, Glyph)]
    assert sorted(claimed) == sorted(glyphs)


@pytest.mark.parametrize("width_px", [1400.0, 300.0])
def test_a_link_in_a_table_cell_reads_as_its_text_wrapped_or_not(
    theme: Theme, width_px: float
) -> None:
    block = _table(theme)
    box = compose_blocks((block,), theme, sp_from_px(width_px), MEASURE_FN)
    cmds = ship(box, Point(0, box.height), measure=MEASURE_FN)
    model = SelectionModel.from_commands(cmds)
    found: dict[str, str] = {}
    areas = []
    seen = 0
    for cell, span_map in map_table(block, box):
        decoration = decorate(
            span_map, model, links=cell.links, number=5, first_link=seen, link_ink=BLUE
        )
        seen += len(cell.links)
        for area in decoration.links:
            areas.append(area)
            found[area.target] = _selected(cmds, area.runs)
    assert found == {
        "https://example.com/t1": "a link in the middle",
        "https://example.com/t2": "here",
        "https://example.com/t3": "also here",
    }
    # Every link of the table has its own name, though they share a block.
    assert [(area.block, area.number) for area in areas] == [(5, 0), (5, 1), (5, 2)]
    if width_px < 1000.0:
        assert max(len(area.rects) for area in areas) >= 2, "no cell link wrapped"


def test_a_based_table_map_reports_absolute_indices(theme: Theme) -> None:
    block = _table(theme)
    box = compose_blocks((block,), theme, sp_from_px(300.0), MEASURE_FN)
    local = map_table(block, box)
    moved = map_table(block, box, base=1000)
    assert [m.base - 1000 for _, m in moved] == [m.base for _, m in local]
    assert all(a.shipped == b.shipped for (_, a), (_, b) in zip(local, moved, strict=True))


def test_a_box_that_is_not_this_tables_is_refused(theme: Theme) -> None:
    block = _table(theme)
    box = compose_blocks((block,), theme, sp_from_px(300.0), MEASURE_FN)
    fewer = replace(block, rows=block.rows[:1])
    with pytest.raises(SpanMapError, match="rows"):
        map_table(fewer, box)
    other = blocks_of(
        "| x | y | z |\n|---|---|---|\n| one | two | three |\n| a | b | c |\n", theme
    )[0]
    assert isinstance(other, TableBlock)
    with pytest.raises(SpanMapError):
        map_table(other, box)


@pytest.mark.parametrize("align", [Align.JUSTIFY, Align.LEFT, Align.RIGHT, Align.CENTER])
@pytest.mark.parametrize("source", ["one two\\\nthree four\n", "one two  \nthree four\n"])
def test_a_phrase_is_found_across_a_hard_break_as_across_a_soft_one(
    source: str, align: Align
) -> None:
    """
    Review 4: a reader who searches for two words that sit either side of a forced break.

    Measured before the fix: `two three` was not found across a hard break in
    any alignment, because the break is a newline in `material_text` and the
    needle has a space. And in a centred or ragged-left block, where a hard
    break is a lone penalty with no fill glue, the text had *nothing* between
    the two words -- `twothree` was found and `two three` was not. A space in
    the needle now matches a forced break, and a forced break is a newline in
    the text whichever way the block is aligned.
    """
    (block,) = build_document(source, Theme.build(align=align), fake_resolve).blocks
    assert isinstance(block, TextBlock)
    assert material_text(block).text == "one two\nthree four"
    (hit,) = find_spans(block, "two three", mark=AMBER)
    covered = material_text(block)
    inside = [
        covered.text[position]
        for position, index in enumerate(covered.indices)
        if index is not None and hit.start <= index < hit.end
    ]
    assert "".join(inside) == "two\nthree"
    assert find_spans(block, "twothree", mark=AMBER) == []
    assert len(find_spans(block, "two\nthree", mark=AMBER)) == 1
    # Within a line nothing changed.
    assert len(find_spans(block, "one two", mark=AMBER)) == 1


def test_a_space_in_the_needle_does_not_join_two_lines_of_code(theme: Theme) -> None:
    """
    The control: a code block's line ends are content, and `a b` is not `a`, newline, `b`.
    """
    (block,) = build_document("```\nlet a\nb = 1\n```\n", theme, fake_resolve).blocks
    assert isinstance(block, CodeBlock)
    assert find_spans(block, "a b", mark=AMBER) == []
    assert len(find_spans(block, "a\nb", mark=AMBER)) == 1

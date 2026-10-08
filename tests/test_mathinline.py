r"""
Math inside a document: `$...$` in a line, `$$` as a block, in markdown and in a stream.

What is claimed, section by section, and against what:

1. **A formula ships as one item.** The defect this replaces was measured
   (`.concerns/demo-review0-snippets/S12.py.txt`): a stacked box inside a line
   shipped a `Line` of its own, the glyph after it was culled with the inner
   line's band, and a copy came out of reading order. The first test rebuilds
   that box bare and shows the defect is still what a bare box does; the ones
   after it show an atom box does not.
2. **The markdown rules**: pandoc's guards, the escape, code, the two block
   forms, and that nothing changes when math is off.
3. **Layout**: a formula is never broken, and a tall one moves the lines by a
   stated amount.
4. **Selection and copy**: one item, copied as its source, with links and
   colours beside it still landing on the right glyphs.
5. **Streaming**: after every piece of a math-on corpus the stream's blocks
   are the blocks of one parse, and no committed block changes.
6. **A real window**, for the counts only.

Real fonts throughout. `MATH` is one builder for the module, so a formula set
for the stream and the same formula set for the whole parse are the same box.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import advtext.markdown
from advtext.fontmetrics import Face
from advtext.markdown import (
    Block,
    CodeBlock,
    FormulaSpan,
    MathRefused,
    TableBlock,
    TextBlock,
    build_document,
    formula_spans,
)
from advtext.mathtext import markdown_math
from advtext.nodes import Box, CharNode, Glue, GlueSpec, Node
from advtext.pack import CharDimens, hpack, vpack
from advtext.selection import Granularity, Selection, SelectionModel
from advtext.shipout import Atom, DrawCmd, Glyph, Line, Point, SetGlue, atom_box, is_atom, ship
from advtext.spans import index_count, map_material, map_text_block
from advtext.stream import CommitPolicy, StreamDocument
from advtext.style import Align, BlockKind, Emphasis, Theme, char_measure, fontlib_metrics
from advtext.ui import CommandIndex, Viewport, compose
from advtext.ui.fonts import ALL_FACES, TEXT_FACES
from advtext.ui.units import UnitLayout, layout_units, moved
from advtext.units import Scaled, px_from_sp, sp_from_px
from tests.conftest import Window

THEME = Theme.build()
MEASURE = char_measure(fontlib_metrics)
MATH = markdown_math()


def document(source: str, *, theme: Theme = THEME) -> tuple[Block, ...]:
    return build_document(source, theme, fontlib_metrics, math=MATH).blocks


def laid(source: str, width_px: float = 420.0) -> tuple[tuple[Block, ...], UnitLayout]:
    blocks = document(source)
    return blocks, layout_units(blocks, THEME, sp_from_px(width_px, THEME.px_per_inch), MEASURE)


def text_of(block: Block) -> str:
    assert isinstance(block, TextBlock)
    return "".join(
        chr(node.codepoint) if isinstance(node, CharNode) else " " if isinstance(node, Glue) else ""
        for node in block.material
    )


def sources(block: Block) -> list[str]:
    return [span.source for span in formula_spans(block) if not span.refusal]


# --------------------------------------------------------------------------------
# 1. Ship-out: an atom is one item
# --------------------------------------------------------------------------------


def _fake(node: CharNode) -> CharDimens:
    return CharDimens(width=10, height=7, depth=2)


def _stacked() -> Box:
    """`B`, a space and `D` in a vbox, hung twelve units low: a tiny fraction."""
    row = hpack([CharNode("f@1", 66), Glue(GlueSpec(5)), CharNode("f@1", 68)], measure=_fake).box
    return replace(vpack([row]).box, shift_amount=12)


def _line_with(box: Box) -> tuple[list[Node], Box, list[DrawCmd]]:
    material: list[Node] = [CharNode("f@1", 65), box, CharNode("f@1", 67)]
    line = hpack(material, measure=_fake).box
    return material, line, ship(line, Point(0, line.height), measure=_fake)


def test_a_bare_stacked_box_in_a_line_still_ships_a_line_of_its_own() -> None:
    # The control: review 0's defect, unchanged for a box nobody marked.
    _, _, cmds = _line_with(_stacked())
    assert [type(cmd) for cmd in cmds] == [Line, Glyph, Line, Glyph, SetGlue, Glyph, Glyph]
    index = CommandIndex.of(cmds)
    assert index.tops[1] != index.tops[-1]
    text = SelectionModel.from_commands(cmds).text(Selection(0, 5))
    assert text != "AB DC" and set(text) == set("AB DC")


def test_an_atom_box_ships_as_one_item_followed_by_its_ink() -> None:
    atom = atom_box(hpack([_stacked()], measure=_fake).box)
    assert is_atom(atom) and not is_atom(_stacked())
    _, line, cmds = _line_with(atom)
    assert [type(cmd) for cmd in cmds] == [Line, Glyph, Atom, Glyph, Glyph, Glyph]
    assert [cmd.index for cmd in cmds[1:]] == [0, 1, 1, 1, 2]  # type: ignore[union-attr]
    header = cmds[0]
    assert isinstance(header, Line) and (header.start, header.end) == (0, 3)
    marker = cmds[2]
    assert isinstance(marker, Atom)
    assert (marker.x, marker.width, marker.natural) == (10, atom.width, atom.width)
    assert (marker.height, marker.depth) == (line.height, line.depth)
    # The ink is where the bare box put it: only the bookkeeping differs.
    bare = [cmd for cmd in _line_with(_stacked())[2] if isinstance(cmd, Glyph)]
    inked = [cmd for cmd in cmds if isinstance(cmd, Glyph)]
    assert [(g.codepoint, g.x, g.y) for g in inked] == [(g.codepoint, g.x, g.y) for g in bare]


def test_nothing_after_an_atom_is_culled_with_a_band_that_is_not_its_own() -> None:
    _, line, cmds = _line_with(atom_box(hpack([_stacked()], measure=_fake).box))
    index = CommandIndex.of(cmds)
    assert len(set(index.tops)) == 1 and len(set(index.bottoms)) == 1
    assert cmds[-1] in index.visible(Viewport(0, 10))
    assert index_count([line]) == 3


def test_an_atom_copies_in_reading_order_as_what_it_is_named() -> None:
    _, _, cmds = _line_with(atom_box(hpack([_stacked()], measure=_fake).box))
    model = SelectionModel.from_commands(cmds)
    assert model.length == 3
    assert model.text(Selection(0, 3), atoms={1: "$B D$"}) == "A$B D$C"
    assert model.text(Selection(1, 2), atoms={1: "$B D$"}) == "$B D$"
    # Unnamed, it is nothing: never the glyphs, which are not what was typed.
    assert model.text(Selection(0, 3)) == "AC"


def test_there_is_no_boundary_inside_an_atom() -> None:
    _, _, cmds = _line_with(atom_box(hpack([_stacked()], measure=_fake).box))
    model = SelectionModel.from_commands(cmds)
    (fragment,) = model.fragments
    assert fragment.indices == (0, 1, 2)
    left, right = fragment.edges[1], fragment.edges[2]
    hits = {model.hit(Point(x, 0)) for x in range(left, right)}
    assert hits == {1, 2}
    assert model.rects(Selection(1, 2))[0].x == left
    assert model.rects(Selection(1, 2))[0].width == right - left
    inside = Point((left + right) // 2, 0)
    assert model.select_at(inside, inside, Granularity.WORD) == Selection(1, 2)


def test_spans_count_an_atom_as_one_and_find_it_among_the_commands() -> None:
    material, line, cmds = _line_with(atom_box(hpack([_stacked()], measure=_fake).box))
    by_box = map_material(material, [line], paragraph=False)
    assert by_box.shipped == (0, 1, 2) and by_box.extent == (1, 1, 1)


def test_moving_commands_keeps_an_atom_an_atom() -> None:
    _, _, cmds = _line_with(atom_box(hpack([_stacked()], measure=_fake).box))
    shifted = moved(cmds, 100, 7)
    assert [type(cmd) for cmd in shifted] == [type(cmd) for cmd in cmds]
    marker = shifted[2]
    before = cmds[2]
    assert isinstance(marker, Atom) and isinstance(before, Atom)
    assert (marker.index, marker.y) == (8, before.y + 100)


# --------------------------------------------------------------------------------
# 2. Markdown
# --------------------------------------------------------------------------------


def test_math_is_off_unless_asked_for() -> None:
    source = "A price of $5 and $x^2$ here.\n\n$$\na+b\n$$\n"
    off = build_document(source, THEME, fontlib_metrics)
    assert all(not formula_spans(block) for block in off.blocks)
    assert "$x^2$" in text_of(off.blocks[0])
    assert [text_of(block) for block in off.blocks[1:]] == ["$$ a+b $$"]
    assert off == build_document(source, THEME, fontlib_metrics, math=None)
    on = document(source)
    assert sources(on[0]) == ["x^2"] and sources(on[1]) == ["a+b"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("$x$", ["x"]),
        ("a $x+y$ b", ["x+y"]),
        ("It costs $5 and $10.", []),
        ("$5 and $10, but $e^{i\\pi}+1=0$ is math", ["e^{i\\pi}+1=0"]),
        ("between $20 and 30$ dollars", ["20 and 30"]),
        ("from $20 to $30", []),
        ("$ x$", []),
        ("$x $", []),
        ("$x$5", []),
        ("$x$ 5", ["x"]),
        ("\\$x$", []),
        ("$a\\$b$", ["a\\$b"]),
        ("`$x$`", []),
        ("``a $x$ b``", []),
        ("$x$ and $y$", ["x", "y"]),
        ("($x$)", ["x"]),
        ("$$x$$ in a line", ["x"]),
        ("a $$x + y$$ b", ["x + y"]),
        ("a lone $ sign", []),
        ("$", []),
        # A line that is `$$` opens a display block, here an empty one.
        ("$$", [""]),
        ("x$", []),
        ("**$x$**", ["x"]),
        ("[$x$](http://e.org)", ["x"]),
        ("line one $a\nb$ line two", ["a\nb"]),
    ],
)
def test_the_inline_rule_follows_pandocs_guards(source: str, expected: list[str]) -> None:
    blocks = document(source)
    found = [span.source for block in blocks for span in formula_spans(block)]
    assert found == expected


def test_a_dollar_that_opens_nothing_is_still_a_dollar() -> None:
    (block,) = document("It costs $5 and $10, or \\$3.")
    assert text_of(block) == "It costs $5 and $10, or $3."


def test_a_formula_is_one_atom_node_where_it_was_written() -> None:
    (block,) = document("Euler: $e^{i\\pi}+1=0$ holds.")
    assert isinstance(block, TextBlock)
    (span,) = block.formulas
    assert (span.source, span.display, span.refusal) == ("e^{i\\pi}+1=0", False, "")
    assert span.end == span.start + 1 and span.index == span.start
    box = block.material[span.start]
    assert isinstance(box, Box) and is_atom(box) and box.width > 0
    assert span.text == "$e^{i\\pi}+1=0$"
    assert text_of(block) == "Euler:  holds."
    boxes = [node for node in block.material if isinstance(node, Box)]
    assert len(boxes) == 1


def test_the_space_after_a_formula_is_an_ordinary_space() -> None:
    # `x.` earns a sentence space; a formula between the full stop and the
    # space puts the factor back, as a box does in TeX.
    plain = document("So x. Then")[0]
    after = document("So x.$y$ Then")[0]
    assert isinstance(plain, TextBlock) and isinstance(after, TextBlock)

    def spaces(block: TextBlock) -> list[GlueSpec]:
        return [node.spec for node in block.material if isinstance(node, Glue)]

    assert spaces(after)[1] == spaces(plain)[0]


def test_a_refused_formula_is_its_source_in_the_code_face_with_the_reason_kept() -> None:
    (block,) = document("A matrix $\\begin{pmatrix}a\\end{pmatrix}$ here.")
    assert isinstance(block, TextBlock)
    (span,) = block.formulas
    assert "matrices are left out for now" in span.refusal
    assert span.source == "\\begin{pmatrix}a\\end{pmatrix}" and span.position == 0
    shown = block.material[span.start : span.end]
    assert all(isinstance(node, CharNode) for node in shown)
    assert "".join(chr(node.codepoint) for node in shown) == span.text  # type: ignore[union-attr]
    code = THEME.font_for(BlockKind.PARAGRAPH, Emphasis(code=True)).key
    assert {node.font for node in shown} == {code}  # type: ignore[union-attr]
    assert not any(isinstance(node, Box) for node in block.material)
    assert sources(block) == []


def test_the_builder_is_asked_at_the_size_of_the_text_around_it() -> None:
    asked: list[tuple[str, bool, Scaled]] = []

    def spy(source: str, display: bool, size: Scaled) -> Box | MathRefused:
        asked.append((source, display, size))
        return MATH(source, display, size)

    build_document("# Big $a$\n\nsmall $b$\n\n$$\nc\n$$\n", THEME, fontlib_metrics, math=spy)
    heading = THEME.style(BlockKind.HEADING_1).font.size
    body = THEME.style(BlockKind.PARAGRAPH).font.size
    assert asked == [("a", False, heading), ("b", False, body), ("c", True, body)]
    assert heading > body


def test_a_builder_that_refuses_everything_sets_everything_as_code() -> None:
    def never(source: str, display: bool, size: Scaled) -> Box | MathRefused:
        return MathRefused("not today", 2)

    blocks = build_document("a $x^2$ b\n\n$$\ny\n$$\n", THEME, fontlib_metrics, math=never).blocks
    assert [text_of(block) for block in blocks] == ["a $x^2$ b", "$$y$$"]
    spans = [span for block in blocks for span in formula_spans(block)]
    assert [(span.refusal, span.position) for span in spans] == [("not today", 2)] * 2


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("$$\nx = a\n+ b\n$$\n", ["x = a + b"]),
        ("$$ x = a $$\n", ["x = a"]),
        ("$$x$$\n", ["x"]),
        ("before\n$$\nx\n$$\nafter\n", ["x"]),
        ("$$\nx\n", ["x"]),
        ("$$\nx\n\ny\n\n# not a heading\n", ["x y # not a heading"]),
        ("  $$\n  x\n  $$\n", ["x"]),
        ("$$\n```\nx\n```\n$$\n", ["``` x ```"]),
    ],
)
def test_a_dollar_dollar_line_opens_a_display_block_like_a_fence(
    source: str, expected: list[str]
) -> None:
    blocks = document(source)
    display = [span for block in blocks for span in formula_spans(block) if span.display]
    assert [span.source for span in display] == expected


@pytest.mark.parametrize(
    "source",
    [
        "    $$\n    x\n    $$\n",
        "```\n$$\nx\n$$\n```\n",
        "$$ x = a\n+ b\n$$ tail\n",
        "text $$ x\n",
    ],
)
def test_these_are_not_display_blocks(source: str) -> None:
    blocks = document(source)
    assert not [span for block in blocks for span in formula_spans(block) if span.display]


def test_a_display_formula_is_a_centred_block_of_the_enclosing_kind() -> None:
    blocks = document("para\n\n$$\n\\sum_{i=1}^n i\n$$\n\n- item\n\n  $$\n  x\n  $$\n\n> $$ y $$\n")
    kinds = [(block.kind, block.style.align) for block in blocks if isinstance(block, TextBlock)]
    assert kinds == [
        (BlockKind.PARAGRAPH, THEME.style(BlockKind.PARAGRAPH).align),
        (BlockKind.PARAGRAPH, Align.CENTER),
        (BlockKind.BULLET_ITEM, THEME.style(BlockKind.BULLET_ITEM).align),
        (BlockKind.BULLET_ITEM, Align.CENTER),
        (BlockKind.QUOTE, Align.CENTER),
    ]
    display = blocks[1]
    assert isinstance(display, TextBlock)
    assert len(display.material) == 1 and is_atom(display.material[0])  # type: ignore[arg-type]
    assert display.formulas == (FormulaSpan("\\sum_{i=1}^n i", 0, 1, True),)
    assert display.style.first_line_indent == 0
    quoted = blocks[4]
    assert isinstance(quoted, TextBlock) and quoted.quote_depth == 1
    inline = document("$\\sum_{i=1}^n i$")[0]
    assert isinstance(inline, TextBlock)
    shown, beside = display.material[0], inline.material[0]
    assert isinstance(shown, Box) and isinstance(beside, Box)
    assert shown.depth > beside.depth  # display style stacks the limits


def test_a_refused_display_formula_is_a_block_of_its_source() -> None:
    (block,) = document("$$\n\\begin{matrix}a\\end{matrix}\n$$\n")
    assert isinstance(block, TextBlock) and block.style.align is Align.CENTER
    assert text_of(block) == "$$\\begin{matrix}a\\end{matrix}$$"
    assert "matrices" in block.formulas[0].refusal


def test_formulas_are_found_in_headings_items_quotes_and_cells() -> None:
    blocks = document(
        "# H $a$\n\n- item $b$\n\n1. step $c$\n\n> quote $d$\n\n"
        "| $e$ | f |\n|---|---|\n| g | $h$ and $\\hat2$ |\n"
    )
    assert [sources(block) for block in blocks] == [["a"], ["b"], ["c"], ["d"], ["e", "h"]]
    table = blocks[-1]
    assert isinstance(table, TableBlock)
    cell = table.rows[0][1]
    assert [bool(span.refusal) for span in cell.formulas] == [False, True]
    head = table.header[0]
    box = head.material[head.formulas[0].start]
    assert isinstance(box, Box) and is_atom(box)
    assert not any(isinstance(block, CodeBlock) for block in blocks)


def test_a_pipe_inside_a_formula_in_a_table_row_is_a_cell_boundary() -> None:
    # The table rule runs before any inline rule and counts the bars. Two
    # outcomes, both recorded and neither fixed here. With the delimiter row
    # the author meant, the header has too many cells and there is no table:
    (paragraph,) = document("| $|x|$ | b |\n|---|---|\n")
    assert isinstance(paragraph, TextBlock) and sources(paragraph) == ["|x|"]
    # and with a delimiter row that matches the bars, the formula is cut into
    # cells and none of the pieces is one. `\vert` is the way to write it.
    (table,) = document("| $|x|$ | b |\n|---|---|---|---|\n| c | d | e | f |\n")
    assert isinstance(table, TableBlock) and sources(table) == []
    (table,) = document("| $\\vert x\\vert$ | b |\n|---|---|\n| c | d |\n")
    assert isinstance(table, TableBlock) and sources(table) == ["\\vert x\\vert"]


def test_markdown_does_not_import_a_formula_parser() -> None:
    tree = ast.parse(Path(advtext.markdown.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert imported and not [name for name in imported if "mathtext" in name or ".math" in name]


def test_the_shipped_builder_remembers_what_it_built() -> None:
    builder = markdown_math()
    size = THEME.style(BlockKind.PARAGRAPH).font.size
    first = builder("x^2", False, size)
    assert isinstance(first, Box)
    assert builder("x^2", False, size) is first
    assert builder("x^2", True, size) is not first
    refused = builder("\\hat x", False, size)
    assert isinstance(refused, MathRefused) and builder("\\hat x", False, size) is refused
    small = markdown_math(remember=2)
    kept = small("a", False, size)
    small("b", False, size)
    small("c", False, size)
    assert small("a", False, size) is not kept and small("a", False, size) == kept


def test_the_math_face_is_not_among_the_faces_loaded_by_default() -> None:
    # What `markdown_math`'s docstring tells a host to do rests on this.
    assert Face.MATH in ALL_FACES and Face.MATH not in TEXT_FACES


# --------------------------------------------------------------------------------
# 3. Layout
# --------------------------------------------------------------------------------

WORDS = "word " * 30


def _baselines(source: str, width_px: float = 420.0) -> list[float]:
    _, layout = laid(source, width_px)
    return [px_from_sp(cmd.y, THEME.px_per_inch) for cmd in layout.cmds if isinstance(cmd, Line)]


def _gaps(source: str) -> list[float]:
    lines = _baselines(source)
    return [round(after - before, 2) for before, after in zip(lines, lines[1:], strict=False)]


def test_a_formula_no_taller_than_the_text_moves_no_line() -> None:
    plain = _gaps(WORDS + "x " + WORDS)
    assert len(set(plain)) == 1
    assert _gaps(WORDS + "$x$ " + WORDS) == plain
    assert _gaps(WORDS + "$x^2$ " + WORDS) == plain


@pytest.mark.parametrize(
    ("formula", "extra_px"),
    [
        ("\\frac{a}{b}", 1.84),
        ("\\sum_{i=1}^n i", 2.56),
        ("\\frac{\\frac{a}{b}}{\\frac{c}{d}}", 7.93),
    ],
)
def test_a_tall_formula_opens_the_lines_around_it_by_this_much(
    formula: str, extra_px: float
) -> None:
    # Measured at the default theme (16 px body, 21.6 px leading), 420 px wide,
    # the formula in the middle of six lines. `extra_px` is how much taller the
    # paragraph is than the same paragraph with `x` in the formula's place; the
    # lines that do not touch the formula keep the leading exactly.
    plain = _gaps(WORDS + "x " + WORDS)
    tall = _gaps(WORDS + f"${formula}$ " + WORDS)
    assert len(tall) == len(plain)
    leading = plain[0]
    moved_gaps = [gap for gap in tall if gap != leading]
    assert 1 <= len(moved_gaps) <= 2 and all(gap > leading for gap in moved_gaps)
    assert round(sum(tall) - sum(plain), 2) == pytest.approx(extra_px, abs=0.02)


@pytest.mark.parametrize("width_px", [40.0, 80.0, 120.0, 200.0, 320.0])
def test_a_formula_is_never_broken_whatever_the_measure(width_px: float) -> None:
    source = "Some words then $a+b+c+d+e+f+g+h=\\frac{x}{y}$ and more words after it."
    blocks, layout = laid(source, width_px)
    atoms = [cmd for cmd in layout.cmds if isinstance(cmd, Atom)]
    assert len(atoms) == 1
    ink = [cmd for cmd in layout.cmds if isinstance(cmd, Glyph) and cmd.index == atoms[0].index]
    assert len(ink) == 18  # eight letters, seven pluses, an equals, x and y
    lines = [cmd for cmd in layout.cmds if isinstance(cmd, Line)]
    holding = [line for line in lines if line.start <= atoms[0].index < line.end]
    assert len(holding) == 1
    box = blocks[0].material[blocks[0].formulas[0].start]  # type: ignore[union-attr]
    assert isinstance(box, Box) and atoms[0].width == box.width
    assert min(g.x for g in ink) >= atoms[0].x and max(g.x for g in ink) < atoms[0].x + box.width


def test_a_display_formula_is_centred_on_the_measure() -> None:
    blocks, layout = laid("$$\na+b\n$$\n", 400.0)
    (atom,) = [cmd for cmd in layout.cmds if isinstance(cmd, Atom)]
    width = sp_from_px(400.0, THEME.px_per_inch)
    left = atom.x
    right = width - (atom.x + atom.width)
    assert abs(left - right) <= 1 and left > width // 4


def test_every_container_composes_with_a_formula_in_it() -> None:
    source = (
        "# H $a^2$\n\n- item $\\frac{1}{2}$\n\n> quote $x_i$\n\n"
        "| $e$ | f |\n|---|---|\n| g | $\\sum_i h_i$ |\n\n$$\n\\int_0^1 f(x) dx\n$$\n"
    )
    for width_px in (120.0, 420.0):
        _, layout = laid(source, width_px)
        atoms = [cmd for cmd in layout.cmds if isinstance(cmd, Atom)]
        assert len(atoms) == 6
        assert [atom.index for atom in atoms] == sorted({atom.index for atom in atoms})
        assert layout.model.length == max(c.end for c in layout.cmds if isinstance(c, Line))


def test_the_index_rule_in_spans_is_ship_outs_for_a_document_with_formulas() -> None:
    # `advtext.spans.index_count` repeats ship-out's rule for what takes an
    # index; `tests/test_spans.py` holds the two together for prose, and this
    # does for atoms, composed as one box the way a whole-document view does.
    source = "\n\n".join(STREAMS[name] for name in ("inline", "display", "in-a-list", "in-a-table"))
    built = build_document(source, THEME, fontlib_metrics, math=MATH)
    box = compose(built, THEME, sp_from_px(300.0, THEME.px_per_inch), MEASURE)
    cmds = ship(box, Point(0, box.height), measure=MEASURE)
    indices = {cmd.index for cmd in cmds if isinstance(cmd, Glyph | SetGlue)}
    atoms = [cmd for cmd in cmds if isinstance(cmd, Atom)]
    assert len(atoms) == 12  # 3 inline, 2 display, 3 in the list, 4 in the table
    assert index_count(box) == len(indices) == max(indices) + 1 > 100
    assert SelectionModel.from_commands(cmds).length == len(indices)


# --------------------------------------------------------------------------------
# 4. Selection, copy, links
# --------------------------------------------------------------------------------


def test_a_selected_formula_copies_as_its_source_with_the_dollars() -> None:
    source = "Euler: $e^{i\\pi}+1=0$ and then $\\frac{a}{b}$ end."
    _, layout = laid(source)
    model = layout.model
    assert model.copy_text(Selection(0, model.length)) == source
    first, second = [cmd for cmd in layout.cmds if isinstance(cmd, Atom)]
    assert model.copy_text(Selection(first.index, first.index + 1)) == "$e^{i\\pi}+1=0$"
    assert model.copy_text(Selection(first.index - 2, second.index + 1)).endswith("$\\frac{a}{b}$")
    assert model.atoms_within(0, model.length) == {
        first.index: "$e^{i\\pi}+1=0$",
        second.index: "$\\frac{a}{b}$",
    }


def test_a_drag_cannot_end_inside_a_formula() -> None:
    _, layout = laid("Before $a+b+c+d+e+f$ after.")
    model = layout.model
    (atom,) = [cmd for cmd in layout.cmds if isinstance(cmd, Atom)]
    start = Point(0, atom.y)
    ends = {
        model.select_at(start, Point(atom.x + offset, atom.y), Granularity.CHARACTER).end
        for offset in range(0, atom.width, max(1, atom.width // 40))
    }
    assert ends == {atom.index, atom.index + 1}
    inside = Point(atom.x + atom.width // 2, atom.y)
    assert model.select_at(inside, inside, Granularity.WORD) == Selection(
        atom.index, atom.index + 1
    )


@pytest.mark.parametrize(
    ("source", "copied"),
    [
        ("# Title $x^2$ here", "Title $x^2$ here"),
        ("- item $\\alpha$ one\n- two", "• item $\\alpha$ one\n• two"),
        ("> said $x_i$ once", "said $x_i$ once"),
        ("| a | $x^2$ |\n|---|---|\n| $y$ | d |\n", "a\t$x^2$\n$y$\td"),
        ("one\n\n$$\na+b\n$$\n\ntwo", "one\n\n$$a+b$$\n\ntwo"),
        ("a $\\hat2$ b", "a $\\hat2$ b"),
        ("a $$x$$ b", "a $$x$$ b"),
    ],
)
def test_a_copy_of_everything_reads_as_the_source_reads(source: str, copied: str) -> None:
    for width_px in (160.0, 420.0):
        _, layout = laid(source, width_px)
        assert layout.model.copy_text(Selection(0, layout.model.length)) == copied


def _linked_glyphs(source: str, width_px: float) -> tuple[str, int, int]:
    """The characters a link's runs cover, how many runs, and how many lines the block has."""
    blocks, layout = laid(source, width_px)
    block = blocks[0]
    assert isinstance(block, TextBlock)
    (unit,) = layout.placed
    mapped = map_text_block(block, unit.unit.cmds)
    (link,) = block.links
    runs = mapped.link_runs(link)
    by_index: dict[int, Glyph | SetGlue] = {}
    for cmd in unit.unit.cmds:
        if isinstance(cmd, Glyph | SetGlue):
            # An atom's ink repeats its index; the atom is the item.
            by_index.setdefault(cmd.index, cmd)
    covered: list[str] = []
    for run in runs:
        for index in range(run.start, run.end):
            cmd = by_index[index]
            if isinstance(cmd, Atom):
                covered.append("@")
            elif isinstance(cmd, Glyph):
                covered.append(chr(cmd.codepoint))
            else:
                covered.append(" ")
    return "".join(covered), len(runs), len(mapped.lines)


def test_a_link_after_a_formula_on_the_same_line_covers_its_own_words() -> None:
    covered, runs, lines = _linked_glyphs(
        "See $\\frac{a}{b}$ and [the linked words](http://e.org).", 420.0
    )
    assert (covered, runs, lines) == ("the linked words", 1, 1)


def test_a_link_after_a_formula_and_across_a_break_covers_its_own_words() -> None:
    covered, runs, lines = _linked_glyphs(
        "See $\\frac{a}{b}$ and [the linked words go on](http://e.org) after.", 150.0
    )
    assert lines > 1 and runs > 1
    assert covered.replace(" ", "") == "thelinkedwordsgoon"


def test_a_link_around_a_formula_covers_the_formula_as_one_item() -> None:
    covered, runs, _ = _linked_glyphs("See [the $x^2$ term](http://e.org) there.", 420.0)
    assert (covered, runs) == ("the @ term", 1)


def test_text_before_and_after_a_formula_maps_glyph_for_glyph() -> None:
    blocks, layout = laid("ab $\\sum_{i=1}^n i$ cd, then $x$ ef " + WORDS, 200.0)
    block = blocks[0]
    assert isinstance(block, TextBlock)
    (unit,) = layout.placed
    mapped = map_text_block(block, unit.unit.cmds)
    items = {cmd.index: cmd for cmd in unit.unit.cmds if isinstance(cmd, Atom)}
    glyphs = {
        cmd.index: cmd
        for cmd in unit.unit.cmds
        if isinstance(cmd, Glyph) and cmd.index not in items
    }
    checked = 0
    for index, node in enumerate(block.material):
        shipped = mapped.shipped_index(index)
        if isinstance(node, CharNode):
            assert shipped is not None and glyphs[shipped].codepoint == node.codepoint
            checked += 1
        elif isinstance(node, Box) and is_atom(node):
            assert shipped in items and mapped.extent[index] == 1
            checked += 1
    assert checked > 100 and len(items) == 2


# --------------------------------------------------------------------------------
# 5. Streaming
# --------------------------------------------------------------------------------

STREAMS = {
    "prices": "It costs $5 and $10 today.\n\nFrom $20 to $30, or \\$40.\n\nend\n",
    "inline": "Euler says $e^{i\\pi}+1=0$ and so $x^2$.\n\nThen $\\frac{a}{b}$ too.\n\nend\n",
    "unclosed-inline": "An open $x + y never closes.\n\nNext $a$ does.\n",
    "display": "Before.\n\n$$\n\\sum_{i=1}^n i\n= \\frac{n(n+1)}{2}\n$$\n\nAfter $x$.\n",
    "display-one-line": "Before.\n$$ a + b $$\nAfter.\n\n$$x$$\n\nend\n",
    "display-interrupts": "A paragraph\n$$\nx = a\n+ b\n$$\nand more text\n",
    "display-unclosed": "Before.\n\n$$\nx = a\n\n# swallowed\n\n- also\n",
    "display-not-opened": "$$ x = a\n+ b\n$$ tail\n\nend\n",
    "in-a-list": "- item $a$ one\n- two\n\n  $$\n  x^2\n  $$\n\n  more $b$\n- three\n\nend\n",
    "in-a-quote": "> quoted $a$\n>\n> $$\n> y_i\n> $$\n>\n> more\n\nend\n",
    "in-a-table": "| a | $x^2$ |\n|---|---|\n| $y$ | d |\n| e | $z$ |\n\n$$\nq\n$$\n\nend\n",
    "table-then-display": "| a | b |\n|---|---|\n| c | d |\n$$\nx\n$$\nend\n",
    "fence-with-dollars": "```\n$$\nnot math $x$\n$$\n```\n\n$$\n```\nmath\n```\n$$\n\nend\n",
    "refused": (
        "A $\\hat{2}$ and $\\vec{x}$.\n\n" "$$\n\\begin{pmatrix}a\\end{pmatrix}\n$$\n\nend\n"
    ),
    "heading": "# Title $x^2$\n\nSetext $y$\n===\n\n$$\nz\n$$\n",
    "crlf": "a $x$ b\r\n\r\n$$\r\ny\r\n$$\r\n\r\nend\r\n",
    "nested-list-display": (
        "1. a\n\n   $$\n   x\n   $$\n   - b $c$\n\n     $$\n     d\n2. e\n\nend\n"
    ),
    "dollar-lines": "$\n\n$$\n\n$$\n\n$$$\n\n$$ $$\n\n$$$$\n\nend\n",
    # A fence the stream follows line by line inside a container, then text,
    # then a `$$` line: lazy continuation to a parser without the math rules,
    # the end of the container to one with them.
    "quote-fence-then-display": "> ```\n> x\n> y\n> ```\n> text\n$$\nz\n$$\n\nend\n",
    "item-fence-then-display": "- a\n\n  ```\n  x\n  y\n  ```\n  text\n$$\nz\n$$\n- b\n\nend\n",
    "open-fence-with-dollars": "- a\n\n  ~~~\n  $$\n  x\n$$\ny\n",
}

CHUNKERS: dict[str, Callable[[str], list[str]]] = {
    "characters": list,
    "threes": lambda source: [source[i : i + 3] for i in range(0, len(source), 3)],
    "lines": lambda source: source.splitlines(keepends=True),
    "at-dollars": lambda source: [
        piece + ("$" if number < source.count("$") else "")
        for number, piece in enumerate(source.split("$"))
    ],
}


def test_every_chunker_reproduces_every_source() -> None:
    for source in STREAMS.values():
        for chunker in CHUNKERS.values():
            assert "".join(chunker(source)) == source


def test_the_corpus_holds_what_the_task_names() -> None:
    assert len(STREAMS) == 21
    on = {name: document(source) for name, source in STREAMS.items()}
    assert not any(formula_spans(block) for block in on["prices"])
    assert any(span.display for block in on["display"] for span in formula_spans(block))
    assert any(isinstance(b, TableBlock) and sources(b) for b in on["in-a-table"])
    assert any(
        isinstance(b, TextBlock) and b.kind is BlockKind.BULLET_ITEM and sources(b)
        for b in on["in-a-list"]
    )
    assert any(span.refusal for block in on["refused"] for span in formula_spans(block))
    assert sum("$" in piece for piece in CHUNKERS["at-dollars"](STREAMS["display"])) > 4


@pytest.mark.parametrize("policy", list(CommitPolicy), ids=lambda policy: policy.name)
@pytest.mark.parametrize("chunking", list(CHUNKERS))
@pytest.mark.parametrize("name", list(STREAMS))
def test_every_piece_of_a_math_source_leaves_the_stream_equal_to_one_parse(
    name: str, chunking: str, policy: CommitPolicy
) -> None:
    source = STREAMS[name]
    stream = StreamDocument(THEME, fontlib_metrics, policy=policy, math=MATH)
    commit_theme = THEME if policy is CommitPolicy.RESET else stream.live_theme

    def whole(text: str, theme: Theme, more: bool = True) -> advtext.markdown.Document:
        # A whole parse *told what the stream knows*: that the text may go
        # on (`more_may_follow`), so a closing dollar that is its very last
        # character has not closed anything yet. After `close` it is told
        # the opposite, which is `build_document`'s default.
        return build_document(
            text, theme, fontlib_metrics, references=False, math=MATH, more_may_follow=more
        )

    before: tuple[Block, ...] = ()
    for number, piece in enumerate(CHUNKERS[chunking](source)):
        stream.append(piece)
        text = stream.source
        committed = stream.committed
        where = f"piece {number}, after {text!r}"
        assert len(committed) >= len(before), where
        assert all(now is then for now, then in zip(committed, before, strict=False)), where
        live = whole(text, stream.live_theme)
        assert committed == whole(text, commit_theme).blocks[: len(committed)], where
        assert stream.live == live.blocks[len(committed) :], where
        assert stream.sources == live.sources, where
        before = committed
    stream.close()
    final = whole(stream.source, commit_theme, more=False)
    assert all(now is then for now, then in zip(stream.committed, before, strict=False))
    assert stream.committed == final.blocks and stream.sources == final.sources


def test_an_unclosed_dollar_in_the_live_block_is_text_until_it_closes() -> None:
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("Settled first.\n\nNow we say\n$x^2 + ")
    (settled,) = stream.committed
    (live,) = stream.live
    assert not formula_spans(live) and text_of(live) == "Now we say $x^2 +"
    stream.append("y$ done")
    assert stream.committed == (settled,) and stream.committed[0] is settled
    (live,) = stream.live
    assert sources(live) == ["x^2 + y"] and text_of(live) == "Now we say  done"


def test_a_display_block_grows_line_by_line_without_touching_what_is_settled() -> None:
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("Settled.\n\n$$\n")
    (settled,) = stream.committed
    seen: list[list[str]] = []
    for piece in ("x = a\n", "+ b\n", "+ c\n", "$$\n", "\nAfter.\n"):
        stream.append(piece)
        assert stream.committed[0] is settled
        seen.append([span.source for block in stream.blocks for span in formula_spans(block)])
    assert seen == [["x = a"], ["x = a + b"], ["x = a + b + c"], ["x = a + b + c"]] + [
        ["x = a + b + c"]
    ]
    assert len(stream.committed) == 2


def test_a_dollar_dollar_line_being_typed_commits_nothing() -> None:
    # `$$` with no newline yet may still become `$$x`, which is text. The
    # paragraph above must not be committed on the strength of it.
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("A paragraph\n$$")
    assert stream.committed == ()
    stream.append("x")
    assert stream.committed == () and len(stream.live) == 1
    assert text_of(stream.live[0]) == "A paragraph $$x"


def test_a_stream_with_math_off_treats_dollars_as_text() -> None:
    stream = StreamDocument(THEME, fontlib_metrics)
    stream.append("a $x$ b\n\n$$\ny\n$$\n")
    stream.close()
    assert not any(formula_spans(block) for block in stream.committed)
    assert (
        stream.committed
        == build_document(
            stream.source, stream.live_theme, fontlib_metrics, references=False
        ).blocks
    )


def test_the_live_block_is_not_set_again_for_every_piece() -> None:
    calls: list[str] = []
    inner = markdown_math()

    def counting(source: str, display: bool, size: Scaled) -> Box | MathRefused:
        calls.append(source)
        return inner(source, display, size)

    stream = StreamDocument(THEME, fontlib_metrics, math=counting)
    stream.append("Take $\\frac{a}{b}$ and")
    for word in " some more words arriving one at a time".split(" "):
        stream.append(word + " ")
        assert stream.live
    # The converter asks every time (it has no memory); the shipped builder
    # answers from what it kept, with the same box.
    assert len(calls) > 5 and set(calls) == {"\\frac{a}{b}"}
    boxes = {id(inner("\\frac{a}{b}", False, THEME.style(BlockKind.PARAGRAPH).font.size))}
    assert len(boxes) == 1


# --------------------------------------------------------------------------------
# 6. A real window
# --------------------------------------------------------------------------------

REAL = r"""
    import sys
    from imgui_bundle import hello_imgui, imgui, immapp
    from advtext import Theme, build_document, char_measure, compose, draw, fontlib_metrics, ship
    from advtext.mathtext import markdown_math
    from advtext.shipout import Atom, Glyph, Point
    from advtext.ui.fonts import ALL_FACES, TEXT_FACES, load_faces
    from advtext.units import sp_from_px

    faces = ALL_FACES if sys.argv[1] == "all" else TEXT_FACES
    SOURCE = (
        "# Math $x^2$ in a heading\n\n"
        "Euler: $e^{i\\pi}+1=0$, a fraction $\\frac{a}{b}$, a sum $\\sum_{i=1}^n i$, "
        "a price of $5 and $10, and a refusal $\\hat{2}$.\n\n"
        "$$\n\\int_0^1 f(x) dx = \\frac{\\pi^2}{6}\n$$\n\n"
        "| a | $\\alpha+\\beta$ |\n|---|---|\n| $\\lim_{x\\to0} x$ | d |\n"
    )
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    doc = build_document(SOURCE, theme, fontlib_metrics, math=markdown_math())
    box = compose(doc, theme, sp_from_px(520.0, theme.px_per_inch), measure)
    cmds = tuple(ship(box, Point(0, box.height), measure=measure))
    atoms = sum(isinstance(c, Atom) for c in cmds)
    ink = sum(isinstance(c, Glyph) and c.font.startswith("math") for c in cmds)
    loaded, drawn = [], []

    def load_fonts():
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        loaded.append(load_faces(faces))

    def gui():
        imgui.set_next_window_size(imgui.ImVec2(600.0, 560.0), imgui.Cond_.first_use_ever)
        if imgui.begin("math"):
            drawn.append(draw(imgui.get_window_draw_list(), cmds,
                              imgui.get_cursor_screen_pos(), fonts=loaded[-1],
                              px_per_inch=theme.px_per_inch, metrics=fontlib_metrics))
        imgui.end()
        if len(drawn) >= 8:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_geometry.size = (700, 640)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    immapp.run(params)
    first, last = drawn[0], drawn[-1]
    print(f"faces={sys.argv[1]} frames={len(drawn)} atoms={atoms} math_ink={ink} "
          f"first_glyphs={first.glyphs} first_missing={first.missing} "
          f"glyphs={last.glyphs} missing={last.missing} rules={last.rules}")
"""


def _counts(line: str) -> dict[str, int]:
    return {key: int(value) for key, value in (part.split("=") for part in line.split()[1:])}


def test_a_document_with_math_draws_in_a_real_window(window: Window) -> None:
    """
    `build_document(math=...)`, composed, shipped and drawn in a GLFW window
    with every face loaded: eight frames. Asserted: it exits cleanly, the
    seven formulas the source sets are seven atoms, their glyphs are in the
    math face, and the backend drew every glyph it was sent with none missing.
    Counts only; nobody looked at it.
    """
    script = window.out / "mathinline_real.py"
    script.write_text(textwrap.dedent(REAL), encoding="utf-8")
    done = window.run([str(script), "all"])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    (line,) = [line for line in done.stdout.splitlines() if line.startswith("faces=all")]
    counts = _counts(line)
    assert counts["frames"] == 8 and counts["atoms"] == 7
    # Measured on 2026-10-07 under Xvfb: atoms=7 math_ink=40 glyphs=117 rules=3,
    # the same on the first frame as on the eighth.
    assert counts["math_ink"] >= 30
    assert counts["missing"] == 0 and counts["first_missing"] == 0
    assert counts["glyphs"] == counts["first_glyphs"] > counts["math_ink"] + 50
    assert counts["rules"] >= 3  # two fraction bars and the table's rule, at least


# --------------------------------------------------------------------------------
# 7. Review 2: shell dollars, a live `$$` block, a formula of no width
# --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # What a transcript about code has. Each must be text, dollars and all.
        ("Then set $PATH=$HOME/bin and $EDITOR=$VISUAL in your shell.", []),
        ("cd $HOME/$USER", []),
        ("$a$b", []),
        ("the exit status $? is zero", []),
        ("arguments $1 $2 and $@", []),
        ("use ${VAR} or ${OTHER}", []),
        ('export PATH="${HOME}/bin:${PATH}"', []),
        ("run $(date) and $(whoami)", []),
        ("$(a)$(b)", []),
        ("it will cost $5 and $10", []),
        ("US$5 and CA$6", []),
        ("a$b$ c", []),
        ("2$x$", []),
        ("$$PID$$x", []),
        ("x$$a$$", []),
        # What the two extra guards give up: a formula hard against a word.
        ("the $n$th term", []),
        ("$x$y$", []),
        # ... and what they do not.
        ("the $n$-th term", ["n"]),
        ("the $n$ th term", ["n"]),
        ("$x$, $y$; ($z$).", ["x", "y", "z"]),
        ("so $x$\nand", ["x"]),
        ("—$x$—", ["x"]),
        # The heuristic's limit, pinned: nothing here knows a variable from a symbol.
        ("$PATH$", ["PATH"]),
    ],
)
def test_shell_text_is_not_math_and_what_that_costs(source: str, expected: list[str]) -> None:
    # Review 2, item 4: `set $PATH=$HOME/bin` set `PATH=` in math italic.
    blocks = document(source)
    assert [span.source for block in blocks for span in formula_spans(block)] == expected
    if not expected:
        assert [text_of(block) for block in blocks] == [source]
        assert blocks == build_document(source, THEME, fontlib_metrics).blocks


SUM = "Sum:\n\n$$\n\\sum_{k=0}^{\\infty} \\frac{x^k}{k!} = e^x\n$$\n\nAfter.\n"


def _display(stream: StreamDocument) -> tuple[TextBlock, FormulaSpan] | None:
    for block in stream.blocks:
        for span in formula_spans(block):
            if span.display:
                assert isinstance(block, TextBlock)
                return block, span
    return None


@pytest.mark.parametrize("step", [1, 2, 3, 5])
def test_a_live_display_block_is_source_until_its_closing_line_and_then_set_once(
    step: int,
) -> None:
    """
    Review 2, item 3: read three characters at a time this formula went from
    refused to set and back three times, and fourteen pieces drew a closing
    `$$` that had not been received.
    """
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    states: list[str] = []
    for start in range(0, len(SUM), step):
        stream.append(SUM[start : start + step])
        found = _display(stream)
        if found is None:
            continue
        block, span = found
        closed = stream.source.count("$$") == 2
        assert span.unclosed is not closed
        if span.unclosed:
            received = " ".join(stream.source.split("$$", 1)[1].split())
            assert span.source == received and span.refusal
            assert text_of(block) == f"$${received}".strip() == span.text
            assert not any(isinstance(node, Box) for node in block.material)
            states.append("source")
        else:
            assert not span.refusal and is_atom(block.material[span.start])  # type: ignore[arg-type]
            states.append("set")
    assert "source" in states and states[-1] == "set"
    assert sum(a != b for a, b in zip(states, states[1:], strict=False)) == 1


def test_an_unclosed_display_block_is_never_offered_to_the_builder() -> None:
    asked: list[str] = []

    def builder(source: str, display: bool, size: Scaled) -> Box | MathRefused:
        asked.append(source)
        return MATH(source, display, size)

    stream = StreamDocument(THEME, fontlib_metrics, math=builder)
    for character in "$$\nx^2 + \\frac{a}{b}\n$":
        stream.append(character)
    # The closing line has arrived as one dollar: still source, nothing refused.
    found = _display(stream)
    assert found is not None
    assert asked == []
    assert found[1].unclosed and text_of(found[0]) == "$$x^2 + \\frac{a}{b} $"
    stream.append("$")
    found = _display(stream)  # the stream converts when it is read
    assert found is not None and not found[1].unclosed and not found[1].refusal
    assert asked and set(asked) == {"x^2 + \\frac{a}{b}"}


def test_a_whole_file_ending_in_an_unclosed_block_shows_it_as_source_too() -> None:
    (block,) = document("$$\nx = a\n+ b\n")
    (span,) = formula_spans(block)
    assert span.unclosed and span.display and span.source == "x = a + b"
    assert text_of(block) == span.text == "$$x = a + b"
    assert (span.start, span.end) == (0, len(block.material))
    assert isinstance(block, TextBlock) and block.style.align is Align.CENTER
    # Closed, the same source is a formula.
    (closed,) = formula_spans(document("$$\nx = a\n+ b\n$$\n")[0])
    assert not closed.unclosed and not closed.refusal and closed.text == "$$x = a + b$$"
    # A one-line block is closed by construction.
    assert not formula_spans(document("$$ x $$\n")[0])[0].unclosed


INLINE_STREAMS = (
    "Euler says $e^{i\\pi}+1=0$ and so $x^2$, then $\\frac{a}{b}$ too.",
    "A refused $\\hat{2}$ beside a set $y_i$ and *emphasis $z$ here* end.",
    "It costs $5 and $10, but $n$ is math and $PATH=$HOME is not.",
)


@pytest.mark.parametrize("source", INLINE_STREAMS)
def test_an_inline_formula_does_not_change_state_once_a_character_follows_its_closer(
    source: str,
) -> None:
    """
    The inline half of review 2's item 3. A formula's closer is the first
    dollar after its opener and nothing later can move it, so once one more
    character has arrived -- the one the closing guard reads -- what the
    formula is (set, or refused) is settled for as long as the paragraph is
    live. Checked a character at a time: the list of formulas only grows, and
    no entry of it ever changes.
    """
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    settled: list[tuple[str, bool]] = []
    for position, character in enumerate(source):
        stream.append(character)
        (live,) = stream.blocks
        now = [(span.source, bool(span.refusal)) for span in formula_spans(live)]
        if source[position] == "$" and now and len(now) > len(settled):
            # The closer is the last character so far: the guard has not read on.
            assert now[: len(settled)] == settled
            continue
        assert now[: len(settled)] == settled, (position, now, settled)
        settled = now
    assert len(settled) == len(formula_spans(document(source)[0])) > 0


def test_the_one_character_after_a_closer_can_still_unmake_a_formula() -> None:
    # The closing guard reads one character on, and a stream cannot know it
    # early. Until review 3 (item 3) that was a window in which `$n$` was a
    # formula and `$n$t` was not; a closer that is the last character so far
    # now closes nothing, so that window is shut. The other one is still
    # open and pinned so that it is known: a code span closing later unmakes
    # everything inside it, as it does to emphasis.
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("so $n$")
    assert sources(stream.blocks[0]) == []
    stream.append("th")
    assert sources(stream.blocks[0]) == []
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("a `b $x$ c")
    assert sources(stream.blocks[0]) == ["x"]
    stream.append("`")
    assert sources(stream.blocks[0]) == []


@pytest.mark.parametrize("formula", ["{}", "\\!\\,", "\\!"])
def test_a_formula_of_no_width_is_still_selected_and_copied(formula: str) -> None:
    # Review 2, item 8: `${}$` is an atom zero wide, which the selection took
    # for fill -- glue that positions and is not text -- and dropped.
    source = f"a ${formula}$ b"
    blocks, layout = laid(source)
    (block,) = blocks
    assert sources(block) == [formula]
    model = layout.model
    everything = model.select(0, 10**9)
    assert model.copy_text(everything) == source
    (placed,) = layout.placed
    (index,) = placed.atoms
    alone = model.select(index, index + 1)
    assert model.copy_text(alone) == f"${formula}$"
    # Zero wide or narrower, it still has a place: one rectangle, on the line.
    rects = model.rects(alone)
    assert len(rects) == 1


# ---------------------------------------------------------------------------
# 8. Review 3, item 3: a closing dollar that is the last character so far
# ---------------------------------------------------------------------------

SHELL_LINE = "Then set $PATH=$HOME/bin and $EDITOR=$VISUAL in your shell.\n"


def set_formulas(blocks: tuple[Block, ...]) -> list[str]:
    return [span.source for block in blocks for span in formula_spans(block) if not span.refusal]


@pytest.mark.parametrize("step", [1, 2, 3, 5])
def test_a_streamed_shell_line_never_shows_a_formula(step: int) -> None:
    """
    `set $PATH=$` -- the text so far, cut after the second dollar -- is a
    formula to a parser that takes the end of the text for what follows the
    closer, and one character later (`H`) it is not: `PATH=` was set in math
    italic for one piece and unset in the next, twice in this line. While
    more may follow, a closing dollar that is the last character so far
    closes nothing.
    """
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    flashes = []
    for at in range(0, len(SHELL_LINE), step):
        stream.append(SHELL_LINE[at : at + step])
        if set_formulas(stream.blocks):
            flashes.append(stream.source)
    assert flashes == []
    stream.close()
    assert set_formulas(stream.committed) == []


def test_a_formula_ending_the_text_is_set_when_its_follower_arrives_or_the_stream_closes() -> None:
    stream = StreamDocument(THEME, fontlib_metrics, math=MATH)
    stream.append("The answer is $x^2$")
    assert set_formulas(stream.blocks) == []  # the next character may be a letter
    assert text_of(stream.live[0]) == "The answer is $x^2$"
    stream.append(".")
    assert set_formulas(stream.blocks) == ["x^2"]
    # ... a newline is a follower like any other,
    other = StreamDocument(THEME, fontlib_metrics, math=MATH)
    other.append("The answer is $x^2$")
    other.append("\n")
    assert set_formulas(other.blocks) == ["x^2"]
    # ... and so is the end of the input, once it is known to be the end.
    last = StreamDocument(THEME, fontlib_metrics, math=MATH)
    last.append("The answer is $x^2$")
    last.close()
    assert set_formulas(last.committed) == ["x^2"]


def test_more_may_follow_touches_only_a_closer_that_is_the_last_character_of_the_source() -> None:
    def told(source: str) -> list[str]:
        built = build_document(source, THEME, fontlib_metrics, math=MATH, more_may_follow=True)
        return set_formulas(built.blocks)

    assert told("a $x$") == [] and sources_of("a $x$") == ["x"]  # whole: the end is a follower
    assert told("a $x$ b") == ["x"]
    assert told("a $x$\n") == ["x"]
    assert told("a $x$ and $y$") == ["x"]  # only the last
    assert told("a $x$\n\nb $y$") == ["x"]  # an earlier paragraph ending in one is settled
    assert told("a $x$\n\n```\n$") == ["x"]  # the source ends in a dollar that is code
    assert told("| a | b |\n|---|---|\n| $x$ | $y$") == ["x"]
    assert told("| a | b |\n|---|---|\n| $y$ | $y$") == ["y"]  # equal cells are still two cells
    assert told("[a $x$](u) $y$") == ["x"]
    assert told("see [a $x$]") == ["x"]  # the closer is not the last character
    assert told("see [a $x$") == []
    assert told("a $$x$$") == [] and told("a $$x$$.") == ["x"]
    # Math off: the argument changes nothing.
    assert build_document("a $x$", THEME, fontlib_metrics, more_may_follow=True) == build_document(
        "a $x$", THEME, fontlib_metrics
    )


def sources_of(source: str) -> list[str]:
    return set_formulas(document(source))

r"""
The Math page (`advtext/ui/pages/mathtext.py`) and its text, `demo/math.md`.

Four layers, cheapest first:

1. **The candidates and the two generated sections.** Which side of the page a
   source is on is asked of the extension; these hold that the table is what
   sets, the list is what is refused, and the reason on the page is the reason
   the parser gives now.
2. **The witnesses in `demo/math.md`.** Each example the text claims something
   about is measured here in a layout, with a control where a zero would
   otherwise be free: the line gap, the formula at a line break, inline against
   display, the four places a formula can stand, the link, the prices, the copy.
3. **The source box and the stream**, without ImGui.
4. **The page in frames**, headless, and once in a real window
   (`tests/conftest.py::window`). The window test reports counts -- glyphs
   drawn, glyphs missing, atoms -- and says nothing of how any of it looks.

The four constructs of the extension's second pass (`\sqrt`, `\left`...`\right`,
spaces, `\text`) were candidates the page sorted by asking, and moved from the
list to the table when the parser took them; they are `REFERENCE` rows now.
What is still listed as refused includes one the *engine* refuses: content
taller than the largest parenthesis.
"""

from __future__ import annotations

import textwrap
from typing import Any

import pytest

from advtext.markdown import (
    Document,
    TableBlock,
    TextBlock,
    build_document,
    formula_spans,
)
from advtext.mathtext import Refusal, RefusalKind, Typeset, markdown_math, typeset
from advtext.nodes import CharNode, Glue
from advtext.shipout import Atom, Glyph, Line
from advtext.spans import material_text
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui.app import App, parse_tab_request
from advtext.ui.bare_view import BareView, block_kind
from advtext.ui.pages import PageContext, demo_text
from advtext.ui.pages import mathtext as page
from advtext.ui.pages.mathtext import (
    REFERENCE,
    REFUSED,
    MathPage,
    Sorted,
    Verdict,
    compose,
    loose_dollars,
    pieces,
    reference_markdown,
    refusals_markdown,
    sort_out,
    tally,
    verdict,
)
from advtext.units import Scaled, px_from_sp, sp_from_px
from tests.conftest import Window

PPI = 96.0
WIDTH = sp_from_px(page.DEFAULT_MEASURE_PX, PPI)


def _context(spec: str = "math") -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


@pytest.fixture(scope="module")
def made() -> MathPage:
    """
    One page for the tests that only read it. A test that edits builds its own.
    """
    built = MathPage(_context())
    built.text.layout_for(WIDTH)
    return built


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


def _text(block: Any) -> str:
    return material_text(block).text if isinstance(block, TextBlock) else ""


def _block(document: Document, opening: str) -> int:
    """
    The one text block whose words begin with `opening`.
    """
    found = [n for n, block in enumerate(document.blocks) if _text(block).startswith(opening)]
    assert len(found) == 1, (opening, found)
    return found[0]


# ----------------------------------------------------------------------
# 1. The candidates, and the sections made from them
# ----------------------------------------------------------------------

ALL = (*REFERENCE, *REFUSED)


def test_the_demo_text_is_there_and_has_both_placeholders() -> None:
    text = demo_text("math.md")
    assert text is not None
    assert text.count(page.REFERENCE_MARK) == 1 and text.count(page.REFUSALS_MARK) == 1
    assert "Matrices are left out for now" in text


@pytest.mark.parametrize(("what", "source"), ALL, ids=[what for what, _ in ALL])
def test_a_candidate_can_be_written_between_dollars_in_a_table_cell(what: str, source: str) -> None:
    """
    The guards the generated markdown relies on, for every candidate.

    No `$` (it would close the formula), no `|` or backtick (the table's
    source cell), no blank at either end and no newline (pandoc's rule would
    make the dollars text and the row would show a refusal that is not one).
    """
    assert what and source
    assert not set(source) & {"$", "|", "`", "\n"}
    assert source == source.strip()


def test_every_character_of_a_candidate_is_one_the_code_face_has() -> None:
    """
    The page shows every source in the code face, and a face draws nothing for
    a character it lacks. The control is the character that was found missing
    in a window: the code face has no `π`.
    """
    from advtext import fontlib
    from advtext.style import Face

    code = fontlib.metrics(Face.CODE, 16.0)
    assert not code.has(ord("π")) and code.has(ord("∑"))
    for _, source in ALL:
        absent = [ch for ch in source if not ch.isspace() and not code.has(ord(ch))]
        assert not absent, (source, absent)


def test_no_two_candidates_share_a_source() -> None:
    sources = [source for _, source in ALL]
    assert len(set(sources)) == len(sources)


@pytest.mark.parametrize(("what", "source"), REFERENCE, ids=[what for what, _ in REFERENCE])
def test_every_reference_source_sets(what: str, source: str, made: MathPage) -> None:
    result = typeset(source, made.size)
    assert isinstance(result, Typeset), getattr(result, "reason", "")


TOO_TALL = r"\left( 1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{x}}}}} \right)"

KINDS = {
    TOO_TALL: RefusalKind.LAYOUT,
    r"\sqrt{\sqrt{\sqrt{\sqrt{\sqrt{\sqrt{x}}}}}}": RefusalKind.LAYOUT,
    r"\sqrt[3]{x}": RefusalKind.RADICAL,
    r"\big( x \big)": RefusalKind.DELIMITER,
    r"\overbrace{a + b}": RefusalKind.DELIMITER,
    r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}": RefusalKind.MATRIX,
    r"\begin{cases} a \\ b \end{cases}": RefusalKind.MATRIX,
    r"\begin{align} a &= b \end{align}": RefusalKind.ENVIRONMENT,
    r"a & b": RefusalKind.ALIGNMENT,
    r"\newcommand{\R}{\mathbb{R}}": RefusalKind.MACRO,
    r"\def\half{\frac{1}{2}}": RefusalKind.MACRO,
    r"\hat{x}": RefusalKind.ACCENT,
    r"\displaystyle\sum_i a_i": RefusalKind.STYLE,
    r"a \over b": RefusalKind.INFIX,
    r"\frobnicate{x}": RefusalKind.UNKNOWN_COMMAND,
    r"x^": RefusalKind.SYNTAX,
    r"\frac{a}{b": RefusalKind.SYNTAX,
}


def test_every_refused_source_is_refused_for_the_reason_its_label_says(made: MathPage) -> None:
    """
    Matrices, environments and macros are all here, each with a kind of its own.
    """
    assert {source for _, source in REFUSED} == set(KINDS)
    for what, source in REFUSED:
        found = verdict(what, source, made.size)
        assert not found.sets, source
        assert found.kind is KINDS[source], (source, found.kind)
        assert found.reason and 0 <= found.position <= len(source)
    assert {
        RefusalKind.MATRIX,
        RefusalKind.ENVIRONMENT,
        RefusalKind.MACRO,
        RefusalKind.ACCENT,
        RefusalKind.LAYOUT,
    } <= set(KINDS.values())


def test_the_too_tall_pair_is_in_the_subset_and_refused_by_the_engine(made: MathPage) -> None:
    r"""
    The first refusal on the page is not the parser's: `parse` takes it, and
    `typeset` comes back with the engine's reason, which names the delimiter
    and a proportion. The control is the row of the table that sets the same
    `\left(`...`\right)` round a shorter fraction.
    """
    from advtext.mathtext import Formula, parse

    assert REFUSED[0][1] == TOO_TALL
    assert isinstance(parse(TOO_TALL), Formula)
    found = verdict("x", TOO_TALL, made.size)
    assert found.kind is RefusalKind.LAYOUT and found.position == 0
    assert found.reason.startswith("what is between the delimiters needs a ( 1.")
    assert found.reason.endswith("and one is not assembled from pieces here")
    assert verdict("x", r"\left( \frac{a}{b} \right)", made.size).sets
    assert r"\left( \frac{a}{b} \right)" in [source for _, source in REFERENCE]

    # On the page: the source as typed, in the code face, with that reason kept.
    document = made.text.document
    (span,) = [
        span
        for block in document.blocks
        for span in formula_spans(block)
        if span.source == TOO_TALL
    ]
    # A formula that set would be one node wide; this is its characters.
    assert span.refusal == found.reason and span.end - span.start > len(TOO_TALL) // 2


def test_the_second_pass_is_in_the_table_and_no_longer_in_the_list(made: MathPage) -> None:
    sets = " ".join(item.source for item in made.sorted.sets)
    for command in (r"\sqrt{", r"\left(", r"\right\rangle", r"\left\{", r"\right.", r"\,", r"\;"):
        assert command in sets, command
    for command in (r"\quad", r"\!", r"\text{"):
        assert command in sets, command
    for item in made.sorted.refused:
        assert "yet" not in item.reason.split(), item
    assert len(made.sorted.sets) == len(REFERENCE) >= 40
    assert len(made.sorted.refused) == len(REFUSED) == 17


def test_the_candidates_are_sorted_by_asking_and_each_is_on_one_side(made: MathPage) -> None:
    found = made.sorted
    sets = [item.source for item in found.sets]
    refused = [item.source for item in found.refused]
    assert sorted(sets + refused) == sorted(source for _, source in ALL)
    assert not set(sets) & set(refused)
    assert {source for _, source in REFERENCE} <= set(sets)
    assert {source for _, source in REFUSED} <= set(refused)
    for item in found.sets:
        assert isinstance(typeset(item.source, made.size), Typeset)
    for item in found.refused:
        again = typeset(item.source, made.size)
        assert isinstance(again, Refusal) and again.reason == item.reason


def test_a_source_changes_sides_when_the_answer_changes(
    made: MathPage, monkeypatch: pytest.MonkeyPatch
) -> None:
    r"""
    No list says which side a source is on: it is asked of `typeset` each time.

    With a `typeset` that accepts `\hat` and refuses `x^2`, the same candidates
    sort the other way round, and the generated sections follow.
    """
    real = page.typeset

    def contrary(source: str, size: Scaled) -> Typeset | Refusal:
        if source == r"\hat{x}":
            return real("x", size)
        if source == "x^2":
            return Refusal(source, False, RefusalKind.SYNTAX, "refused by the test", 1)
        return real(source, size)

    monkeypatch.setattr(page, "typeset", contrary)
    found = sort_out(made.size)
    assert r"\hat{x}" in [item.source for item in found.sets]
    (moved,) = [item for item in found.refused if item.source == "x^2"]
    assert moved.reason == "refused by the test" and moved.position == 1
    assert r"| `\hat{x}` | $\hat{x}$ |" in reference_markdown(found.sets)
    assert "- $x^2$ — superscript (syntax): refused by the test." in refusals_markdown(
        found.refused
    ).replace("\\", "")


def test_compose_fills_both_placeholders_and_appends_a_section_that_has_none() -> None:
    found = Sorted(
        (Verdict("a", "x^2"),),
        (Verdict("b", r"\hat{x}", RefusalKind.ACCENT, "no accents"),),
    )
    filled = compose("top\n\n{{reference}}\n\nmiddle\n\n{{refusals}}\n", found)
    assert "{{" not in filled
    assert filled.index("| a | `x^2` | $x^2$ |") < filled.index("middle") < filled.index("- $")
    bare = compose("only this\n", found)
    assert bare.startswith("only this\n\n| what |") and bare.endswith("(accent): no accents.\n")


def test_the_table_on_the_page_is_the_sources_that_set_each_beside_its_own_source(
    made: MathPage,
) -> None:
    """
    Every row: the code cell reads as the source and the result cell is that source, set.
    """
    document = made.text.document
    tables = [block for block in document.blocks if isinstance(block, TableBlock)]
    reference = tables[-1]
    assert len(reference.rows) == len(made.sorted.sets) >= len(REFERENCE)
    for row, item in zip(reference.rows, made.sorted.sets, strict=True):
        _, source_cell, result_cell = row
        assert page_cell_text(source_cell) == " ".join(item.source.split())
        (span,) = result_cell.formulas
        assert span.source == item.source and not span.refusal and not span.display


def page_cell_text(cell: Any) -> str:
    """
    A table cell's characters, a space for each glue; boxes left out.
    """
    return "".join(
        chr(node.codepoint) if isinstance(node, CharNode) else " "
        for node in cell.material
        if isinstance(node, CharNode | Glue)
    )


def test_the_list_on_the_page_is_the_refused_sources_each_with_the_reason_given_now(
    made: MathPage,
) -> None:
    """
    One list item for each refusal: the source as typed, then the parser's own reason.

    The reason is read back out of the set material, so the markdown escaping
    in between is shown to give back exactly the sentence that went in.
    """
    document = made.text.document
    items = [
        block
        for block in document.blocks
        if isinstance(block, TextBlock)
        and block_kind(block) is BlockKind.BULLET_ITEM
        and any(span.refusal for span in block.formulas)
    ]
    assert len(items) == len(made.sorted.refused) >= len(REFUSED)
    for block, item in zip(items, made.sorted.refused, strict=True):
        (span,) = block.formulas
        assert span.source == item.source
        assert span.refusal == item.reason and span.position == item.position
        words = _text(block)
        assert words.startswith(f"${item.source}$")
        assert item.reason in words, (item.reason, words)
        assert item.kind is not None and f"({item.kind.value})" in words


def test_matrices_are_refused_on_the_page_and_the_text_says_they_are_left_out(
    made: MathPage,
) -> None:
    document = made.text.document
    matrices = [
        span
        for block in document.blocks
        for span in formula_spans(block)
        if "is a matrix, and matrices are left out for now" in span.refusal
    ]
    assert len(matrices) == 2
    said = _text(document.blocks[_block(document, "Whatever cannot be set whole")])
    assert "Matrices are left out for now" in said
    # ... and the two other things still out are named beside them.
    assert "Accents are not built" in said and "never assembled from pieces" in said


def test_a_text_with_no_demo_file_still_makes_a_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    built = MathPage(_context())
    assert not built.from_file
    found = tally(built.text.document.blocks)
    assert found.sets == 3 + len(built.sorted.sets)
    assert len(found.refused) == len(built.sorted.refused)
    assert "from_file=0" in built.report()[-1]


# ----------------------------------------------------------------------
# 2. The witnesses in demo/math.md
# ----------------------------------------------------------------------


def _gaps(view: BareView, block: int) -> list[float]:
    lines = view.set_lines(block, block + 1)
    baselines = [px_from_sp(line.baseline, PPI) for line in lines]
    return [round(low - high, 2) for high, low in zip(baselines, baselines[1:], strict=False)]


def test_a_tall_fraction_opens_the_gaps_round_its_own_line_and_no_others(
    made: MathPage, theme: Theme
) -> None:
    """
    The paragraph with `\\frac{a}{b}` and the fraction of fractions, at the page's measure.

    Its line gaps are not all one leading, the smallest is exactly the leading
    of a paragraph with no formula, and most of its gaps are that leading.
    The control is the same paragraph with every formula replaced by a letter:
    every gap is one leading.
    """
    document = made.text.document
    number = _block(document, "A formula of plain letters")
    gaps = _gaps(made.text, number)
    assert len(gaps) >= 6

    source = demo_text("math.md")
    assert source is not None
    (paragraph,) = [part for part in source.split("\n\n") if part.startswith("A formula of plain")]
    plain = paragraph
    for span in document.blocks[number].formulas:  # type: ignore[union-attr]
        plain = plain.replace(span.text, "x")
    assert "$" not in plain
    control = BareView(
        document=build_document(plain, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    control.layout_for(WIDTH)
    leading = set(_gaps(control, 0))
    assert len(leading) == 1, leading
    (one,) = leading

    assert min(gaps) == one
    assert max(gaps) > one + 2.0, gaps
    wider = [gap for gap in gaps if gap > one]
    assert 1 <= len(wider) <= 4 and len(wider) < len(gaps) / 2, gaps


def _atoms_on_lines(view: BareView, block: int) -> list[tuple[Atom, int, bool, bool]]:
    """
    Each atom of a block: the command, its line, whether all its ink is on that
    line inside its box, and whether it is the first thing on the line.
    """
    layout = view.layout
    assert layout is not None
    unit = layout.unit_of_block(block)
    assert unit is not None
    line = -1
    opened: dict[int, tuple[Atom, int, bool]] = {}
    whole: dict[int, bool] = {}
    seen_on_line = 0
    for cmd in unit.cmds:
        if isinstance(cmd, Line):
            line += 1
            seen_on_line = 0
        elif isinstance(cmd, Atom):
            opened[cmd.index] = (cmd, line, seen_on_line == 0)
            whole[cmd.index] = True
            seen_on_line += 1
        elif isinstance(cmd, Glyph):
            if cmd.index in opened:
                atom, at, _ = opened[cmd.index]
                inside = atom.x - 1 <= cmd.x <= atom.x + atom.width + 1
                whole[cmd.index] = whole[cmd.index] and at == line and inside
            seen_on_line += 1
    return [(atom, at, whole[index], first) for index, (atom, at, first) in opened.items()]


def test_the_formula_at_a_line_break_moves_whole(made: MathPage, theme: Theme) -> None:
    """
    Every pixel of measure the slider offers, one at a time, on a view of its own.

    At each, the long formula is one atom with all of its ink on one line; and
    somewhere in the range it goes from following words on its line to opening
    the next line, which is the move the text tells the visitor to watch for.
    The slider's lowest measure is narrower than the formula, so the overhang
    the text describes is reachable.
    """
    source = demo_text("math.md")
    assert source is not None
    (paragraph,) = [part for part in source.split("\n\n") if part.startswith("A formula is never")]
    # The paragraph alone: the whole text costs about 110 ms to re-break at a
    # new measure (measured), and this asks for 389 of them.
    view = BareView(
        document=build_document(paragraph, theme, fontlib_metrics, math=markdown_math()),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    assert view.document.blocks == (
        made.text.document.blocks[_block(made.text.document, "A formula is never broken")],
    )
    number = 0
    low, high = page.MEASURE_PX
    firsts: list[bool] = []
    width_px = 0.0
    for width in range(int(high), int(low) - 1, -1):
        view.layout_for(sp_from_px(float(width), PPI))
        ((atom, _, whole, first),) = _atoms_on_lines(view, number)
        assert whole, width
        firsts.append(first)
        width_px = px_from_sp(atom.width, PPI)
    moves = sum(1 for was, now in zip(firsts, firsts[1:], strict=False) if not was and now)
    assert moves >= 1 and not all(firsts), firsts
    assert low < width_px < high, width_px


def test_one_source_is_set_inline_and_as_a_display_and_the_display_is_the_taller(
    made: MathPage,
) -> None:
    document = made.text.document
    source = r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}"
    spans = [
        (number, span)
        for number, block in enumerate(document.blocks)
        for span in formula_spans(block)
        if span.source == source
    ]
    assert [span.display for _, span in spans] == [False, True]
    assert all(not span.refusal for _, span in spans)
    inline, display = (typeset(source, made.size, display=flag) for flag in (False, True))
    assert isinstance(inline, Typeset) and isinstance(display, Typeset)
    assert (
        display.box.height + display.box.depth > inline.box.height + inline.box.depth
    ), "limits stacked and a full-size fraction make the display the taller box"
    # A display block holds its formula and nothing else, and is centred.
    block = document.blocks[spans[1][0]]
    assert isinstance(block, TextBlock) and _text(block) == "" and len(block.material) >= 1
    layout = made.text.layout
    assert layout is not None
    ((atom, _, whole, _),) = _atoms_on_lines(made.text, spans[1][0])
    assert whole
    left = px_from_sp(atom.x, PPI)
    right = page.DEFAULT_MEASURE_PX - px_from_sp(atom.x + atom.width, PPI)
    assert left > 20.0 and abs(left - right) < 1.0, (left, right)


@pytest.mark.parametrize(
    ("opening", "kind"),
    [
        ("In a heading", BlockKind.HEADING_3),
        ("In a list item", BlockKind.BULLET_ITEM),
        ("In a second item", BlockKind.BULLET_ITEM),
        ("In a quotation", BlockKind.QUOTE),
    ],
)
def test_a_formula_stands_in_a_heading_a_list_item_and_a_quotation(
    opening: str, kind: BlockKind, made: MathPage
) -> None:
    document = made.text.document
    number = _block(document, opening)
    block = document.blocks[number]
    assert isinstance(block, TextBlock) and block_kind(block) is kind
    (span,) = block.formulas
    assert not span.refusal and span.end - span.start == 1
    ((_, _, whole, _),) = _atoms_on_lines(made.text, number)
    assert whole


def test_a_formula_stands_in_a_table_cell_and_copies_from_it(made: MathPage) -> None:
    document = made.text.document
    (number,) = [
        n
        for n, block in enumerate(document.blocks)
        if isinstance(block, TableBlock) and len(block.header) == 2
    ]
    spans = formula_spans(document.blocks[number])
    assert [span.source for span in spans] == [
        r"e^{i\pi} + 1 = 0",
        r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}",
    ]
    assert all(not span.refusal for span in spans)
    assert made.text.block_text(number).splitlines() == [
        "name\tformula",
        "Euler\t$e^{i\\pi} + 1 = 0$",
        "Basel\t$\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}$",
    ]


def test_the_link_after_a_formula_begins_after_it_and_does_not_cover_it(made: MathPage) -> None:
    document = made.text.document
    block = document.blocks[_block(document, "A link straight after a formula")]
    assert isinstance(block, TextBlock)
    (span,) = block.formulas
    (link,) = block.links
    assert link.target.startswith("https://")
    assert link.start == span.end + 1, "one interword space between the formula and the link"
    assert not link.start <= span.start < link.end


def test_prices_stay_text(made: MathPage) -> None:
    """
    Five dollar signs in the paragraph, none of them a formula's.

    The control is the paragraph before the heading, where the same count is
    zero and the dollars all belong to formulas.
    """
    document = made.text.document
    prices = document.blocks[_block(document, "It cost")]
    assert isinstance(prices, TextBlock)
    assert prices.formulas == ()
    assert loose_dollars([prices]) == 5
    assert "$5 and $10" in _text(prices) and _text(prices).endswith("$ like this.")
    control = document.blocks[_block(document, "A formula of plain letters")]
    assert isinstance(control, TextBlock)
    assert loose_dollars([control]) == 0 and len(control.formulas) == 7


def test_copying_a_paragraph_gives_back_its_formulas_as_source(made: MathPage) -> None:
    """
    `block_text` of each paragraph with formulas has every one, dollars and all, in order.

    And the whole text copied reads as its markdown reads, for the paragraph
    whose markup is formulas and nothing else.
    """
    view, document = made.text, made.text.document
    checked = 0
    for number, block in enumerate(document.blocks):
        if not isinstance(block, TextBlock) or not block.formulas:
            continue
        copied = view.block_text(number)
        at = 0
        for span in block.formulas:
            found = copied.find(span.text, at)
            assert found >= 0, (span.text, copied)
            at = found + len(span.text)
            checked += 1
    assert checked >= 20

    source = demo_text("math.md")
    assert source is not None
    (paragraph,) = [part for part in source.split("\n\n") if part.startswith("A formula of plain")]
    number = _block(document, "A formula of plain letters")
    assert view.block_text(number) == paragraph

    view.select_all()
    everything = view.selected_text()
    view.clear_selection()
    assert paragraph in everything
    assert "$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$" in everything


def _ink(view: BareView, block: int) -> list[list[Glyph]]:
    """
    The glyphs of each atom of a block, in the order the atoms are set.
    """
    layout = view.layout
    assert layout is not None
    unit = layout.unit_of_block(block)
    assert unit is not None
    order: list[int] = []
    ink: dict[int, list[Glyph]] = {}
    for cmd in unit.cmds:
        if isinstance(cmd, Atom):
            order.append(cmd.index)
            ink[cmd.index] = []
        elif isinstance(cmd, Glyph) and cmd.index in ink:
            ink[cmd.index].append(cmd)
    return [ink[index] for index in order]


def test_fitted_parentheses_and_root_signs_are_chosen_outlines(made: MathPage) -> None:
    r"""
    The paragraph that sets `(\frac{a}{b})` beside `\left(\frac{a}{b}\right)`
    and `\sqrt{x}` beside `\sqrt{\frac{a}{b}}`.

    In each pair the two formulas open with different glyphs of the math face
    -- the plain parenthesis and a larger variant of it; two of the font's
    radical signs -- and the fraction between the parentheses is the same
    glyphs both times.
    """
    from advtext import fontlib
    from advtext.style import Face

    document = made.text.document
    number = _block(document, "Parentheses typed as themselves")
    block = document.blocks[number]
    assert isinstance(block, TextBlock)
    assert [span.source for span in block.formulas] == [
        r"(\frac{a}{b})",
        r"\left(\frac{a}{b}\right)",
        r"\sqrt{x}",
        r"\sqrt{\frac{a}{b}}",
    ]
    assert not any(span.refusal for span in block.formulas)
    fixed, fitted, root, tall_root = _ink(made.text, number)

    def name(glyph: Glyph) -> str:
        return str(fontlib.glyph_name(Face.MATH, glyph.codepoint))

    assert (name(fixed[0]), name(fixed[-1])) == ("parenleft", "parenright")
    assert name(fitted[0]).startswith("parenleft.v") and name(fitted[-1]).startswith("parenright.v")
    assert [g.codepoint for g in fixed[1:-1]] == [g.codepoint for g in fitted[1:-1]]
    assert name(root[0]).startswith("radical") and name(tall_root[0]).startswith("radical")
    assert name(root[0]) != name(tall_root[0])


def test_a_named_space_moves_the_differential_and_words_are_in_the_prose_face(
    made: MathPage,
) -> None:
    from advtext.style import Face, parse_font_key

    document = made.text.document
    number = _block(document, "A space can be asked for by name")
    block = document.blocks[number]
    assert isinstance(block, TextBlock)
    tight, spaced, worded = _ink(made.text, number)
    assert [g.codepoint for g in tight] == [g.codepoint for g in spaced]

    def span(ink: list[Glyph]) -> int:
        return ink[-1].x - ink[0].x

    # The same glyphs; the last of them three mu further from the first.
    quad = sp_from_px(16.0, PPI)
    assert abs((span(spaced) - span(tight)) - quad * 3 / 18) <= 3

    faces = [parse_font_key(glyph.font).face for glyph in worded]
    words = [chr(g.codepoint) for g, face in zip(worded, faces, strict=True) if face is Face.PROSE]
    assert words == ["i", "f"]
    assert faces.count(Face.MATH) == len(faces) - 2 > 0


def test_the_display_block_with_all_four_new_constructs_sets(made: MathPage) -> None:
    document = made.text.document
    (number,) = [
        n
        for n, block in enumerate(document.blocks)
        for span in formula_spans(block)
        if span.display and r"\left(" in span.source
    ]
    (span,) = formula_spans(document.blocks[number])
    assert not span.refusal
    for command in (r"\left(", r"\right)", r"\sqrt{", r"\quad", r"\text{"):
        assert command in span.source
    ((_, _, whole, _),) = _atoms_on_lines(made.text, number)
    assert whole


def test_every_formula_that_set_is_one_atom_in_the_layout(made: MathPage) -> None:
    found = tally(made.text.document.blocks)
    assert found.sets >= 40 and len(found.refused) == len(made.sorted.refused)
    assert page.atoms_in(made.text) == found.sets
    assert made.text.unmapped_blocks == 0


# ----------------------------------------------------------------------
# 3. The source box and the stream, without ImGui
# ----------------------------------------------------------------------


def _editor(theme: Theme) -> page.Editor:
    return page.Editor(theme, char_measure(fontlib_metrics), fontlib_metrics, markdown_math())


def test_the_source_box_opens_on_one_formula_one_refusal_and_one_price(theme: Theme) -> None:
    editor = _editor(theme)
    found = editor.tally
    assert (found.sets, len(found.refused)) == (1, 1)
    assert loose_dollars(editor.view.document.blocks) == 1
    counts, refusal = editor.lines()
    assert counts.startswith("1 set  ·  1 refused  ·  1 dollar")
    assert refusal.startswith(r"$\hat{x}$  refused at character 0: \hat is an accent")
    assert editor.edits == 0 and editor.error == ""


def test_an_edit_sets_the_paragraph_again_and_lists_each_refusal_with_its_reason(
    theme: Theme,
) -> None:
    editor = _editor(theme)
    editor.view.layout_for(WIDTH)
    before = editor.view.layout
    editor.set_text(r"Now $a^2 + b^2$ and $\begin{matrix} a \end{matrix}$ and $x^$ and $\pi$.")
    after = editor.view.layout_for(WIDTH)
    assert after is not before and editor.edits == 1
    found = editor.tally
    assert found.sets == 2
    assert [span.source for span in found.refused] == [r"\begin{matrix} a \end{matrix}", "x^"]
    lines = editor.lines()
    assert len(lines) == 3
    assert "matrices are left out for now" in lines[1]
    assert lines[2] == "$x^$  refused at character 1: ^ has nothing after it"
    assert page.atoms_in(editor.view) == 2

    editor.set_text("")
    assert editor.view.document.blocks == () and editor.lines()[0].startswith("0 set")
    editor.view.layout_for(WIDTH)


def test_an_edit_that_cannot_be_converted_is_shown_and_the_last_paragraph_kept(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor = _editor(theme)
    kept = editor.view.document

    def broken(*args: Any, **kwargs: Any) -> Document:
        raise ValueError("no such glyph")

    monkeypatch.setattr(page, "build_document", broken)
    editor.set_text("anything")
    assert editor.text == "anything" and editor.view.document is kept
    assert editor.error == "ValueError: no such glyph"
    assert "not converted: ValueError: no such glyph" in editor.lines()
    monkeypatch.undo()
    editor.set_text("plain")
    assert editor.error == "" and editor.view.document is not kept


def _replay(theme: Theme) -> page.Replay:
    return page.Replay(theme, char_measure(fontlib_metrics), fontlib_metrics, markdown_math())


def test_the_pieces_are_the_source_cut_small() -> None:
    cut = pieces(page.STREAM_SOURCE)
    assert "".join(cut) == page.STREAM_SOURCE
    assert all(len(piece) == page.PIECE for piece in cut[:-1]) and 1 <= len(cut[-1]) <= page.PIECE
    assert pieces("abcd", 0) == ("a", "b", "c", "d")
    assert page.opening_pieces("no dollars") == len(pieces("no dollars"))


def test_the_stream_opens_inside_its_first_formula_with_the_dollar_as_text(theme: Theme) -> None:
    replay = _replay(theme)
    fed = replay.stream.source
    assert fed.count("$") == 1 and not fed.endswith("$") and not replay.done
    assert (replay.tally.sets, len(replay.tally.refused)) == (0, 0)
    assert loose_dollars(replay.stream.blocks) == 1
    assert "0 set" in replay.line() and "1 dollar signs standing as text" in replay.line()


def test_an_unclosed_dollar_is_text_until_it_closes_and_the_words_before_it_stay_put(
    theme: Theme,
) -> None:
    """
    Piece by piece through the first paragraph's two formulas.

    While a `$` is open: one loose dollar, and the count of set formulas is
    what it was. On the piece that closes it: one more formula, no loose
    dollar, and every glyph that stood before the opening dollar is the same
    glyph at the same place on the same baseline.

    "Closes it" is the piece that brings the character *after* the closing
    dollar (review 3, item 3: that character decides whether the dollar
    closed anything, so a piece that ends exactly on it leaves both dollars
    standing as text for one piece -- two loose dollars, and no formula).
    """
    replay = _replay(theme)
    width = sp_from_px(420.0, PPI)
    closes = 0
    while closes < 2:
        sets = replay.tally.sets
        loose = 2 if replay.stream.source.endswith("$") else 1
        assert loose_dollars(replay.stream.blocks) == loose
        replay.view.sync()
        replay.view.layout_for(width)
        before = [glyph for line in replay.view.set_lines() for glyph in line.glyphs]
        # The open dollar is the one `$` among the glyphs: a set formula's ink has none.
        dollars = [n for n, (codepoint, _) in enumerate(before) if codepoint == page.DOLLAR]
        assert len(dollars) == loose
        letters = dollars[0]
        before = before[:letters]
        baselines = [line.baseline for line in replay.view.set_lines()]

        assert replay.step() == 1
        if replay.tally.sets == sets:
            continue
        closes += 1
        assert replay.tally.sets == sets + 1 and loose_dollars(replay.stream.blocks) == 0
        replay.view.sync()
        replay.view.layout_for(width)
        after = [glyph for line in replay.view.set_lines() for glyph in line.glyphs][:letters]
        assert after == before and letters >= 11
        assert [line.baseline for line in replay.view.set_lines()][: len(baselines) - 1] == (
            baselines[:-1]
        )
        # On to the next opening dollar, if this paragraph has another.
        while closes < 2 and loose_dollars(replay.stream.blocks) == 0:
            assert replay.step() == 1
    assert closes == 2


def test_the_stream_ends_closed_with_three_formulas_and_nothing_left_over(theme: Theme) -> None:
    replay = _replay(theme)
    assert replay.finish() == len(replay.parts) - page.opening_pieces(page.STREAM_SOURCE)
    assert replay.done and replay.stream.closed and replay.step() == 0
    found = replay.tally
    assert (found.sets, len(found.refused)) == (3, 0)
    assert loose_dollars(replay.stream.blocks) == 0
    spans = [span for block in replay.stream.blocks for span in formula_spans(block)]
    assert [span.display for span in spans] == [False, False, True]
    whole = build_document(page.STREAM_SOURCE, theme, fontlib_metrics, math=markdown_math())
    assert [s.source for s in spans] == [
        s.source for block in whole.blocks for s in formula_spans(block)
    ]
    replay.restart()
    assert replay.fed == 0 and replay.stream.source == "" and not replay.stream.closed


# ----------------------------------------------------------------------
# 4. The page, in frames
# ----------------------------------------------------------------------

SIZE = (1300.0, 800.0)


def _imgui() -> Any:
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    return imgui


def _frame(app: App) -> None:
    imgui = _imgui()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##advtext-math-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
    finally:
        imgui.render()


_OWN: list[Any] = []


def _open(spec: str = "math") -> tuple[App, MathPage]:
    """
    The app on the Math page after two frames, in an ImGui context of its own.

    Its own for the reason `tests/test_page_find.py::_open` measured: a text
    box's edit state is kept per context by id, and this page has a text box.
    """
    imgui = _imgui()
    fresh = imgui.create_context()
    imgui.set_current_context(fresh)
    while _OWN:
        imgui.destroy_context(_OWN.pop())
    _OWN.append(fresh)
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    _frame(app)
    _frame(app)
    built = app.page("math")
    assert isinstance(built, MathPage)
    return app, built


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_the_page_is_listed_where_the_lead_put_it() -> None:
    spec = page.PAGE
    assert (spec.name, spec.title, spec.group, spec.order) == (
        "Math",
        "Math in text",
        "Typesetting",
        60,
    )
    assert spec.label == "Math in text" and spec.shot_specs() == ("math", "math:done")
    assert spec.accepts("done") and not spec.accepts("nonsense")


def test_the_done_option_opens_with_the_stream_at_its_end() -> None:
    assert MathPage(_context("math:done")).replay.done
    assert not MathPage(_context("math")).replay.done


def test_the_page_draws_its_three_panes_with_glyphs_in_each() -> None:
    app, built = _open()
    assert app.current == "Math" and built.frames == 2
    assert set(built.stats) == {"text", "editor", "stream"}
    for name, stats in built.stats.items():
        assert stats.glyphs > 0, name
    panes = [_fields(line) for line in built.report()]
    assert [pane.get("pane") for pane in panes[:3]] == ["text", "editor", "stream"]
    for pane in panes[:3]:
        assert pane["atoms"] == pane["set"], pane
    total = panes[3]
    assert total["glyphs"] == str(sum(stats.glyphs for stats in built.stats.values()))
    assert total["table"] == str(len(built.sorted.sets))
    assert total["listed"] == str(len(built.sorted.refused))
    # The text pane is laid out at the slider's measure, not at the pane's width.
    layout = built.text.layout
    assert layout is not None and layout.width == WIDTH


def test_the_measure_slider_re_breaks_the_text_and_is_held_to_its_range() -> None:
    app, built = _open()
    before = built.text.layout
    assert before is not None
    built.set_measure(300.4)
    _frame(app)
    after = built.text.layout
    assert after is not None and after is not before
    assert after.width == sp_from_px(300.0, PPI) and after.height > before.height
    built.set_measure(10.0)
    assert built.measure_px == page.MEASURE_PX[0]
    built.set_measure(5000.0)
    assert built.measure_px == page.MEASURE_PX[1]
    _frame(app)
    assert page.atoms_in(built.text) == tally(built.text.document.blocks).sets


def test_typing_in_the_source_box_sets_the_paragraph_again() -> None:
    app, built = _open()
    built.type(r"Only $\frac{1}{2}$ here.")
    _frame(app)
    assert built.editor.edits == 1
    assert (built.editor.tally.sets, len(built.editor.tally.refused)) == (1, 0)
    assert page.atoms_in(built.editor.view) == 1 and built.stats["editor"].glyphs > 0
    built.type("")
    _frame(app)
    assert built.stats["editor"].glyphs == 0


def test_characters_typed_into_the_box_reach_the_editor() -> None:
    """
    The widget itself: keyboard focus on the box, then characters, a frame each.
    """
    app, built = _open()
    imgui = _imgui()
    io = imgui.get_io()
    # A click in the box: it is the first text box of the right-hand column.
    imgui.set_current_context(_OWN[-1])
    probe = {"at": (0.0, 0.0)}
    real = built._source_box

    def located(module: Any, padded: int, scrolls: int) -> None:
        cursor = module.get_cursor_screen_pos()
        # In the first line of the box, which is words: caption, then the box.
        probe["at"] = (
            cursor.x + 40.0,
            cursor.y + module.get_text_line_height_with_spacing() + 12.0,
        )
        real(module, padded, scrolls)

    built._source_box = located  # type: ignore[method-assign]
    _frame(app)
    io.add_mouse_pos_event(*probe["at"])
    _frame(app)
    io.add_mouse_button_event(0, True)
    _frame(app)
    io.add_mouse_button_event(0, False)
    _frame(app)
    before = built.editor.text
    # Spaces either side: typed into the middle of a word, the closing dollar
    # would be followed by a letter, and since C-mathfix that is text, not math.
    for character in " $x^2$ ":
        io.add_input_character(ord(character))
        _frame(app)
    assert built.editor.edits >= 1, "no character reached the box"
    assert len(built.editor.text) == len(before) + 7 and "$x^2$" in built.editor.text
    assert built.editor.tally.sets == 2


def test_playing_feeds_the_stream_by_the_clock_and_stops_at_its_end() -> None:
    app, built = _open()
    opening = built.replay.fed
    assert built.advance(1.0) == 0, "nothing is fed while it is not playing"
    built.play()
    assert built.advance(1.0) == int(page.PIECES_PER_SECOND)
    assert built.advance(0.5 / page.PIECES_PER_SECOND) == 0
    assert built.advance(0.5 / page.PIECES_PER_SECOND) == 1
    fed = built.replay.fed
    assert fed == opening + int(page.PIECES_PER_SECOND) + 1
    _frame(app)  # a sixtieth of a second: under one piece
    _frame(app)
    _frame(app)
    _frame(app)
    _frame(app)
    assert built.replay.fed == fed + 1
    built.advance(1000.0)
    assert built.replay.done and not built.playing
    _frame(app)
    assert built.stats["stream"].glyphs > 0 and built.replay.tally.sets == 3

    built.play()  # a finished stream begins again
    assert built.playing and built.replay.fed == 0
    built.restart()
    assert not built.playing and built.replay.fed == 0
    _frame(app)  # an empty stream draws
    assert built.stats["stream"].glyphs == 0


def test_the_header_line_shows_what_the_selection_would_copy() -> None:
    app, built = _open()
    idle = page.selection_line(built.views)
    assert idle.startswith("select across a formula")
    built.editor.view.select_all()
    _frame(app)
    line = page.selection_line(built.views)
    assert line.startswith("selection copies (")
    assert r"$\sum_{k=0}^{\infty} \frac{x^k}{k!} = e^x$" in line.replace("\\\\", "\\")
    # The text pane takes the selection over, and its copy is cut to fit the line.
    built.text.select_all()
    _frame(app)
    line = page.selection_line(built.views)
    assert "Math in text" in line and line.endswith("…'")
    assert not built.editor.view.owns_selection


def test_the_readouts_report_counts_and_judge_nothing() -> None:
    built = MathPage(_context())
    text = " ".join(
        [*built.report(), *built.editor.lines(), built.replay.line(), page.selection_line(())]
    ).lower()
    for word in ("better", "worse", "good", "bad", "clean", "crisp", "smooth", "fast", "slow"):
        assert word not in text.split(), word


# ----------------------------------------------------------------------
# 5. A real window
# ----------------------------------------------------------------------

WINDOWED = r"""
from imgui_bundle import hello_imgui

from advtext.ui import app as advtext_app

state = {"frames": 0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    state["frames"] += 1
    frame = state["frames"]
    made = self.page("math")
    if frame == 6:
        print("opened")
        print("\n".join(made.report()))
        made.type(r"Typed: $\int_0^1 x^2 dx = \frac{1}{3}$ and $\begin{matrix} a \end{matrix}$.")
        made.set_measure(300.0)
        made.replay.finish()
    elif frame == 12:
        print("edited")
        print("\n".join(made.report()))
        # From here the text pane is walked from top to bottom, a pane at a
        # time, so that every line of it is drawn in the window at least once.
        from imgui_bundle import imgui

        from advtext.ui.bare_view import BareView

        draw = BareView.draw
        state.update(at=0.0, glyphs=0, missing=0, steps=0, end=False)

        def scrolled(view, **kwargs):
            # A slotted class: the method is replaced on the class, for one view.
            if view is made.text:
                if imgui.get_scroll_y() >= imgui.get_scroll_max_y() - 1.0 and state["steps"]:
                    state["end"] = True
                imgui.set_scroll_y(state["at"])
            return draw(view, **kwargs)

        BareView.draw = scrolled
    elif frame > 12 and frame % 2 == 0:
        stats = made.stats["text"]
        state["glyphs"] += stats.glyphs
        state["missing"] += stats.missing
        state["steps"] += 1
        if state["end"] or state["steps"] > 200:
            print(
                f"walked steps={state['steps']} end={int(state['end'])} "
                f"glyphs={state['glyphs']} missing={state['missing']}"
            )
            hello_imgui.get_runner_params().app_shall_exit = True
        state["at"] += 500.0


advtext_app.App.gui = watched_gui
advtext_app.run(tab="math")
"""


def test_the_page_runs_in_a_real_window_with_no_glyph_missing(window: Window) -> None:
    """
    The real app on `--tab math`: six frames as it opens, then an edit of the
    source box, a narrower measure and the stream run to its end, six more;
    then the text pane scrolled from its top to its end, a pane at a time.

    Counts only. In every pane, before and after: glyphs were drawn, **none was
    missing** (the display sum is a synthetic codepoint of the math face, so
    this is the count that would show the face absent), and the layout holds
    one atom for each formula that set. Nobody looked at the window.
    """
    script = window.out / "math_page.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = done.stdout.splitlines()
    assert "opened" in lines and "edited" in lines, done.stdout
    opened = [_fields(line) for line in lines[lines.index("opened") + 1 : lines.index("edited")]]
    edited = [_fields(line) for line in lines[lines.index("edited") + 1 :]][:4]
    assert len(opened) == 4 and len(edited) == 4, done.stdout
    for report in (opened, edited):
        for pane in report[:3]:
            assert int(pane["glyphs"]) > 0, done.stdout
            assert pane["missing"] == "0", done.stdout
            assert pane["atoms"] == pane["set"], done.stdout
        assert report[3]["missing"] == "0" and report[3]["from_file"] == "1"

    headless = MathPage(_context())
    text, editor, stream, total = opened
    assert text["set"] == str(tally(headless.text.document.blocks).sets)
    assert text["refused"] == total["listed"] == str(len(headless.sorted.refused))
    assert (editor["set"], editor["refused"], editor["loose"]) == ("1", "1", "1")
    assert (stream["set"], stream["loose"]) == ("0", "1")
    assert total["measure"] == "520" and total["edits"] == "0"

    text, editor, stream, total = edited
    assert (editor["set"], editor["refused"]) == ("1", "1")
    assert (stream["set"], stream["refused"], stream["loose"]) == ("3", "0", "0")
    assert total["measure"] == "300" and total["edits"] == "1"
    assert total["fed"] == total["pieces"]
    # A narrower measure shows fewer glyphs of the same text, and still some.
    assert 0 < int(text["glyphs"]) < int(opened[0]["glyphs"]), done.stdout

    # The whole text, walked: at least as many glyphs drawn as the text has at
    # that measure (panes overlap, so more), the end reached, none missing.
    (walked,) = [_fields(line) for line in lines if line.startswith("walked ")]
    headless.text.layout_for(sp_from_px(300.0, PPI))
    layout = headless.text.layout
    assert layout is not None
    glyphs = sum(1 for cmd in layout.cmds if isinstance(cmd, Glyph))
    assert walked["end"] == "1" and int(walked["steps"]) >= 5, done.stdout
    assert int(walked["glyphs"]) >= glyphs > 5000, (walked, glyphs)
    assert walked["missing"] == "0", done.stdout

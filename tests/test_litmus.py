r"""
The two litmus tests, as executable claims rather than as artifacts to be looked at.

`docs/litmus.md` is the write-up and the pictures are the evidence a person
reads. This file is what stops either of them quietly stopping being true.

**The central assertion is `test_the_display_sigma_is_a_larger_glyph_and_not_the_body_one_scaled`.**
`docs/decisions.md` stakes the second litmus test on the display operator being
a *real larger glyph selected from real font data*, and names the failure it is
ruling out: emitting U+2211 at a bigger size, which looks almost right and is
not the claim. So the test does not compare formula heights -- it finds the
operator glyph in each rendering, resolves it back through `imscribe.fontlib` to
the name the font gave it, and asserts that display style reached
`summation.v1` while text style reached `summation`. A scaled-up body glyph
fails that even though its rendered height would pass a height comparison.

Everything here runs the real pipeline against real fonts, so it takes the
`bundled_fonts` fixture and skips without them.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ElementTree
from dataclasses import replace
from pathlib import Path

import pytest

from imscribe import fontlib
from imscribe.backends.svg import render
from imscribe.fontmetrics import Face
from imscribe.linebreak import LineBreakParams, LineSpec, ParShape
from imscribe.markdown import CodeBlock, RuleBlock, TableBlock, TextBlock, build_document
from imscribe.math.atoms import Style, group, op, ord_, rel
from imscribe.math.mlist import math_fonts, mlist_to_hlist
from imscribe.nodes import Box, CharNode, Glue, GlueSign, GlueSpec
from imscribe.pack import CharMeasure, PackFitness, hpack
from imscribe.selection import SelectionModel
from imscribe.shipout import DrawCmd, Glyph, Line, Point, RuleRect, SetGlue, pascal_round, ship
from imscribe.style import Align, BlockKind, Theme, char_measure, fontlib_metrics, parse_font_key
from imscribe.ui import compose
from imscribe.units import Scaled, pt_from_sp
from scripts.render_litmus import (
    MARGIN,
    MEASURE,
    Rendered,
    _sigma,
    render_markdown,
    render_selection,
    render_sigma,
    render_sigma_comparison,
)

SVG = "{http://www.w3.org/2000/svg}"
SOURCE = Path(__file__).resolve().parent.parent / "demo" / "sample.md"


@pytest.fixture(scope="session")
def sample(bundled_fonts: Path) -> str:
    """
    The litmus document's markdown source.
    """
    return SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def page(sample: str) -> Rendered:
    """
    The whole document laid out once, since every test below reads the same one.
    """
    return render_markdown(sample)


@pytest.fixture(scope="session")
def body_size() -> Scaled:
    """
    The size the formulas are set at: the document's body size.
    """
    return Theme.build().style(BlockKind.PARAGRAPH).font.size


def _parse(document: str) -> ElementTree.Element:
    """
    Parse a rendered document, which is also the "it is well formed" assertion.
    """
    return ElementTree.fromstring(document)


def _operator(rendered: Rendered) -> tuple[str, Scaled]:
    """
    The name the font gives the summation glyph in this rendering, and its ink height.

    Resolved through `imscribe.fontlib.glyph_name` because the display variant has
    **no codepoint in the font**: it is reachable only by the synthetic codepoint
    the font library mints for it, and going back through a cmap would find
    nothing. That indirection is the thing under test.
    """
    for cmd in rendered.cmds:
        if not isinstance(cmd, Glyph):
            continue
        name = fontlib.glyph_name(Face.MATH, cmd.codepoint)
        if name.startswith("summation"):
            face = fontlib.metrics(Face.MATH, float(parse_font_key(cmd.font).size))
            box = face.bbox(cmd.codepoint)
            return name, round(box.height + box.depth)
    raise AssertionError("no summation glyph was shipped")


# --------------------------------------------------------------------------
# Litmus test 2: the sigma
# --------------------------------------------------------------------------


def test_the_display_sigma_is_a_larger_glyph_and_not_the_body_one_scaled(
    body_size: Scaled,
) -> None:
    # The claim `docs/decisions.md` makes, and the one most likely to be doubted.
    # U+2211's vertical variant chain in Latin Modern Math is
    # [summation, summation.v1]; display style must follow it and text style
    # must not.
    display_name, display_height = _operator(render_sigma(body_size, Style.DISPLAY))
    text_name, text_height = _operator(render_sigma(body_size, Style.TEXT))

    assert display_name == "summation.v1"
    assert text_name == "summation"
    assert display_height > text_height

    # And by a real margin rather than a rounding: the variant is 1401 font
    # units tall against the body glyph's 1001, so at the same size the
    # rendered ink is about 40% taller.
    assert display_height / text_height > 1.3


def test_the_display_and_text_formulas_are_both_shipped_at_the_same_size(
    body_size: Scaled,
) -> None:
    # Otherwise the height comparison above would be measuring the size and not
    # the glyph, which is exactly the dishonest version being ruled out.
    def operator_size(rendered: Rendered) -> Scaled:
        for cmd in rendered.cmds:
            if isinstance(cmd, Glyph) and fontlib.glyph_name(Face.MATH, cmd.codepoint).startswith(
                "summation"
            ):
                return parse_font_key(cmd.font).size
        raise AssertionError("no summation glyph was shipped")

    assert operator_size(render_sigma(body_size, Style.DISPLAY)) == operator_size(
        render_sigma(body_size, Style.TEXT)
    )


def test_display_style_stacks_the_limits_above_and_below_the_operator(
    body_size: Scaled,
) -> None:
    # `\limits` behaviour: in display style the sub and superscript sit over and
    # under the operator, so the formula is tall and narrow. In text style they
    # sit beside it, so it is short and wide. Comparing the two shapes is the
    # cheapest way to assert the stacking without asserting a specific offset.
    display = _sigma(Style.DISPLAY, body_size)
    inline = _sigma(Style.TEXT, body_size)

    assert display.height + display.depth > inline.height + inline.depth
    assert display.width < inline.width


def test_the_limits_are_centred_over_and_under_the_operator(body_size: Scaled) -> None:
    # §750 centres each limit box on the operator's own centre line. The two
    # limits have very different widths -- "n" against "i=1" -- so a
    # left-aligned stack would put them at the same x and this would fail.
    # The operator alone, so that the `i^2` that follows it in the artifact --
    # whose own superscript also sits above the baseline -- cannot be mistaken
    # for an upper limit.
    fonts = math_fonts(body_size, lambda size: fontlib.math_metrics(float(size)))
    atoms = [op(chr(0x2211), sub=group(ord_("i"), rel("="), ord_("1")), sup=ord_("n"))]
    box = hpack(mlist_to_hlist(atoms, Style.DISPLAY, fonts), measure=fonts.measure).box
    glyphs = [
        cmd
        for cmd in ship(box, Point(0, box.height), measure=fonts.measure)
        if isinstance(cmd, Glyph)
    ]

    operator = next(
        cmd
        for cmd in glyphs
        if fontlib.glyph_name(Face.MATH, cmd.codepoint).startswith("summation")
    )
    above = [cmd for cmd in glyphs if cmd.y < operator.y]
    below = [cmd for cmd in glyphs if cmd.y > operator.y]
    assert len(above) == 1, "the upper limit is a single 'n'"
    assert len(below) == 3, "the lower limit is 'i', '=' and '1'"

    def centre(group: list[Glyph]) -> float:
        face = fontlib.metrics(Face.MATH, float(parse_font_key(group[0].font).size))
        left = min(cmd.x for cmd in group)
        right = max(cmd.x + face.advance(cmd.codepoint) for cmd in group)
        return (left + right) / 2

    face = fontlib.metrics(Face.MATH, float(parse_font_key(operator.font).size))
    operator_centre = operator.x + face.advance(operator.codepoint) / 2
    # Within a point of each other and of the operator: §750 centres each limit
    # box on the operator's own centre line, and the two limits are very
    # different widths, so a left-aligned stack would fail this.
    one_point = 65536
    assert abs(centre(above) - centre(below)) < one_point
    assert abs(centre(above) - operator_centre) < one_point


# --------------------------------------------------------------------------
# Litmus test 1: the document
# --------------------------------------------------------------------------


def test_the_sample_document_exercises_every_block_kind_the_litmus_test_names(
    sample: str,
) -> None:
    # "Multi-type markdown" is not satisfied by paragraphs alone, so the
    # document itself is part of the claim and is checked rather than trusted.
    document = build_document(sample, Theme.build(), fontlib_metrics)
    kinds = {block.kind for block in document.blocks if isinstance(block, TextBlock)}
    assert {
        BlockKind.HEADING_1,
        BlockKind.HEADING_2,
        BlockKind.HEADING_3,
        BlockKind.PARAGRAPH,
        BlockKind.BULLET_ITEM,
        BlockKind.ORDERED_ITEM,
        BlockKind.QUOTE,
    } <= kinds
    assert any(isinstance(block, CodeBlock) for block in document.blocks)
    assert any(isinstance(block, RuleBlock) for block in document.blocks)
    assert any(isinstance(block, TableBlock) for block in document.blocks)


def test_the_document_ships_glyphs_rules_and_lines(page: Rendered) -> None:
    assert sum(1 for cmd in page.cmds if isinstance(cmd, Glyph)) > 1000
    assert sum(1 for cmd in page.cmds if isinstance(cmd, Line)) > 30
    # The thematic break and the table's header rule.
    assert sum(1 for cmd in page.cmds if isinstance(cmd, RuleRect)) >= 2


def test_no_line_in_the_document_is_overfull(sample: str) -> None:
    # The honest version of "justification works". `docs/litmus.md` records what
    # this cost: without hyphenation the tolerance had to be raised well past
    # plain TeX's 200, and seven lines come back loose. None comes back in the
    # margin, and this is the assertion that keeps it that way.
    from imscribe.linebreak import break_paragraph
    from imscribe.ui import PROSE_BREAKING, _shape, _skips

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document(sample, theme, fontlib_metrics)
    offenders: list[tuple[str, float]] = []
    for block in document.blocks:
        if not isinstance(block, TextBlock):
            continue
        paragraph = break_paragraph(
            block.material,
            _shape(block, MEASURE),
            _skips(block.style.align, PROSE_BREAKING),
            measure=measure,
        )
        offenders.extend(
            (block.kind.name, pt_from_sp(line.overfull_by))
            for line in paragraph.lines
            if line.fitness is PackFitness.OVERFULL
        )
    assert offenders == []


JUSTIFIED_LINE_FLOOR = 30
r"""
How many justified lines `demo/sample.md` must still produce.

**This number is the anti-vacuity guard and not decoration.** The assertion it
guards -- zero residue -- is satisfied by the empty set, so a change that stops
justification happening at all would otherwise turn the project's headline test
green and silent. That is not hypothetical: it is what T14 did, and all nineteen
tests in this file passed while the prose was set to a 2 em rag.

Measured on this document: **42** lines qualify when the prose is justified.
Set the prose ragged and it collapses to **2**; give `\rightskip` a finite 2 em
of stretch and it is **4**. The floor sits at 30 so that both of those are red,
with room for the document to change without being tuned to it.
"""


def _line_commands(page: Rendered) -> list[tuple[Line, list[DrawCmd]]]:
    """
    Each line and the commands it covers, in one forward pass.

    `Line` is emitted *before* its material precisely so this pass is possible,
    so nothing here has to match a glyph to a line by coordinate. A container
    `Line` -- the one ship-out emits over a block quote's hbox -- collects
    nothing, because the inner lines follow it and take their own material.
    """
    lines: list[tuple[Line, list[DrawCmd]]] = []
    for cmd in page.cmds:
        if isinstance(cmd, Line):
            lines.append((cmd, []))
        elif lines:
            lines[-1][1].append(cmd)
    return lines


def _justified_line_residues(page: Rendered, measure: CharMeasure) -> list[tuple[Line, Scaled]]:
    r"""
    Every justified line, and how far short of its own right margin it stops.

    **Which lines count is read off the shipped glue, never assumed.** The same
    page carries ragged headings, the last line of every paragraph and the rows
    of a table, and each of those reaches the margin by way of an infinitely
    stretchable glue. Counting them would make an assertion about the margin
    true for reasons that have nothing to do with justification -- which is
    exactly how this test came to be vacuous. One condition does the work, and
    it is §886's:

    **Nothing filled the end of the line.** `\rightskip` is zero under
    justification and infinite under every other alignment, and `\parfillskip`
    closes the last line of a paragraph the same way. So every glue lying at or
    beyond the last glyph must have zero set width; if anything there carries a
    width, *that* is what reached the margin and the interword spaces are off
    the hook. The finite-rag control below is the case this exists for -- a
    two-em `\rightskip` moves the interword glue as well, so "did the spaces
    move?" cannot tell it from justification and this can.

    A line is taken at its **own** `x + width` rather than at `MARGIN +
    MEASURE`, so the four left-indented lines inside the block quote are held to
    a margin instead of being skipped for being narrow. On this page the two
    agree, because the quote gives up margin on the left only -- an ablation
    replacing one with the other stays green and is recorded as such -- but the
    line's own geometry is the thing being claimed. Nothing here excuses a line
    for having no stretchable glue: a justified line that cannot reach the
    margin is still a justified line that does not reach the margin.

    The residue is measured to the **advance** edge of the last glyph rather
    than its ink, because a line ends where the next character would begin.
    Positive means the line stops short; negative means it runs past.
    """
    residues: list[tuple[Line, Scaled]] = []
    for line, cmds in _line_commands(page):
        glues = [cmd for cmd in cmds if isinstance(cmd, SetGlue)]
        glyphs = [cmd for cmd in cmds if isinstance(cmd, Glyph)]
        if not glues or not glyphs:
            continue
        edge = max(
            glyph.x + measure(CharNode(glyph.font, glyph.codepoint)).width for glyph in glyphs
        )
        if any(glue.width for glue in glues if glue.x >= edge):
            continue
        residues.append((line, line.x + line.width - edge))
    return residues


def _assert_justified_lines_end_on_the_margin(page: Rendered, measure: CharMeasure) -> int:
    """
    The whole claim, as one function so the controls below can run it verbatim.

    Split out because a test that cannot be shown to fail is not evidence, and
    the only honest way to show it is to hand the same code a page that should
    make it red. Returns how many lines it checked.
    """
    residues = _justified_line_residues(page, measure)
    assert len(residues) >= JUSTIFIED_LINE_FLOOR, (
        f"only {len(residues)} justified lines were found, below the floor of "
        f"{JUSTIFIED_LINE_FLOOR}: justification has stopped happening, and the "
        f"residue assertion below is vacuous over a set this small"
    )
    adrift = [(line.y, pt_from_sp(residue)) for line, residue in residues if residue != 0]
    assert adrift == [], f"{len(adrift)} justified lines carry a residue, in (y, pt): {adrift}"
    return len(residues)


def test_every_justified_line_ends_exactly_on_the_right_margin(page: Rendered) -> None:
    # §625's accumulate-multiply-round-once-and-difference, seen from the far
    # end of the pipeline: the set widths of a line's glue sum to exactly the
    # excess the box was packed to absorb, so the last glyph's advance lands on
    # the margin with no residue at all. Rounding each space independently makes
    # this drift by a scaled point or two per line, and
    # `test_the_margin_assertion_is_red_when_each_glue_is_rounded_on_its_own`
    # is that statement run rather than asserted.
    #
    # This assertion was an inequality -- `<=`, "does not overflow" -- under a
    # name that promises equality, and it was measuring the last *glue* rather
    # than the last *glyph*, so the zero-width `\rightskip` sitting exactly on
    # the margin satisfied it whatever the text did. It could not fail.
    lines = [cmd for cmd in page.cmds if isinstance(cmd, Line)]
    assert len([line for line in lines if line.width == MEASURE]) > 20
    assert _assert_justified_lines_end_on_the_margin(page, char_measure(fontlib_metrics)) >= 30


def test_the_margin_assertion_is_red_when_the_prose_is_set_ragged(sample: str) -> None:
    # The control the original assertion never had. T14 ran this whole file with
    # justification effectively off and all nineteen tests passed, so "green"
    # said nothing; this is what makes green mean something.
    #
    # Ragged right is `\rightskip = 0pt plus 1fil` and nothing else, so the
    # interword glue is never asked to move and the fil closes every line at the
    # margin instead. A check that cannot tell that apart from justification is
    # not checking justification.
    theme = Theme.build()
    ragged = replace(
        theme,
        blocks={
            kind: replace(style, align=Align.LEFT) if style.align is Align.JUSTIFY else style
            for kind, style in theme.blocks.items()
        },
    )
    measure = char_measure(fontlib_metrics)
    page = render_markdown(sample, ragged)
    # Two lines survive, and they are honest: `fil` can stretch but not shrink,
    # so a line whose natural width overruns the measure still has to squeeze
    # its interword spaces and still lands exactly on the margin.
    assert len(_justified_line_residues(page, measure)) < 5
    with pytest.raises(AssertionError, match="justification has stopped happening"):
        _assert_justified_lines_end_on_the_margin(page, measure)


def test_the_margin_assertion_is_red_when_the_prose_is_set_to_a_finite_loose_rag(
    sample: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    r"""
    T14's exact configuration, which the assertion this replaces did not notice.

    A **finite** `\rightskip` is the hard case and the reason
    `_justified_line_residues` looks at what lies past the last glyph. Unlike
    `0pt plus 1fil`, two ems of finite stretch does not outrank the interword
    glue -- both are stretched, in proportion -- so the spaces really do move
    and any check that asks only "did the glue move?" still calls these lines
    justified. What gives it away is that the rag itself carries a width: the
    glue sitting past the last glyph is no longer zero, and the thing that
    reached the margin was the `\rightskip` and not the text.
    """
    from imscribe import ui

    body = Theme.build().style(BlockKind.PARAGRAPH).font.size
    unragged = ui._skips

    def loosened(align: Align, params: LineBreakParams) -> LineBreakParams:
        if align is Align.JUSTIFY:
            return replace(params, left_skip=GlueSpec(), right_skip=GlueSpec(stretch=2 * body))
        return unragged(align, params)

    monkeypatch.setattr(ui, "_skips", loosened)
    measure = char_measure(fontlib_metrics)
    page = render_markdown(sample)
    # Four survive, and they are the lines that had to *shrink*: a `\rightskip`
    # with stretch and no shrink contributes nothing when the line is over its
    # natural width, so the spaces do all the work and the margin is honest.
    assert len(_justified_line_residues(page, measure)) < 10
    with pytest.raises(AssertionError, match="justification has stopped happening"):
        _assert_justified_lines_end_on_the_margin(page, measure)


def test_the_margin_assertion_is_red_when_each_glue_is_rounded_on_its_own(
    sample: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other control, and the one that puts weight on the *equality* rather
    # than on the count: §625's rounding replaced by the obvious wrong version,
    # in which every glue node rounds its own share instead of taking the
    # difference between two rounded running totals.
    #
    # Measured: 36 of the 38 justified lines drift, by -7 to +7 scaled points.
    # Small enough that no picture would show it and no inequality would catch
    # it, which is the whole reason the claim is stated as equality.
    def independently_rounded(
        node: Glue, box: Box, cur_glue: float, cur_g: Scaled
    ) -> tuple[Scaled, float, Scaled]:
        spec = node.spec
        if box.glue_sign is GlueSign.STRETCHING and spec.stretch_order is box.glue_order:
            return spec.width + pascal_round(box.glue_set * spec.stretch), cur_glue, cur_g
        if box.glue_sign is GlueSign.SHRINKING and spec.shrink_order is box.glue_order:
            return spec.width - pascal_round(box.glue_set * spec.shrink), cur_glue, cur_g
        return spec.width, cur_glue, cur_g

    monkeypatch.setattr("imscribe.shipout._set_glue_width", independently_rounded)
    measure = char_measure(fontlib_metrics)
    page = render_markdown(sample)
    # The classifier still recognises the same lines -- the damage is to where
    # they end, not to what they are -- so it is the residue that fires here and
    # the count that fires in the ragged control. Two different assertions.
    assert len(_justified_line_residues(page, measure)) >= JUSTIFIED_LINE_FLOOR
    with pytest.raises(AssertionError, match="carry a residue"):
        _assert_justified_lines_end_on_the_margin(page, measure)


def test_the_margin_assertion_is_red_when_every_line_stops_a_scaled_point_short(
    sample: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The control aimed squarely at the defect this test had, and nothing else.

    The assertion here used to read `last.x + last.width <= line.x +
    line.width`: an inequality, under a name promising equality. It could only
    ever catch a line that ran *past* the margin, and a line that stopped short
    -- which is what losing justification looks like -- satisfied it.

    So: round every glue's share downward, which biases every line short and
    never long. Measured, 36 of the 38 justified lines come back 1 to 13 scaled
    points shy. This test asserts the residues are all non-negative first, which
    is the same thing as saying the old inequality would have passed on this
    page, and then asserts that the new check does not.
    """

    def rounded_short(
        node: Glue, box: Box, cur_glue: float, cur_g: Scaled
    ) -> tuple[Scaled, float, Scaled]:
        spec = node.spec
        if box.glue_sign is GlueSign.STRETCHING and spec.stretch_order is box.glue_order:
            return spec.width + math.floor(box.glue_set * spec.stretch), cur_glue, cur_g
        if box.glue_sign is GlueSign.SHRINKING and spec.shrink_order is box.glue_order:
            return spec.width - math.ceil(box.glue_set * spec.shrink), cur_glue, cur_g
        return spec.width, cur_glue, cur_g

    monkeypatch.setattr("imscribe.shipout._set_glue_width", rounded_short)
    measure = char_measure(fontlib_metrics)
    residues = [
        residue for _, residue in _justified_line_residues(render_markdown(sample), measure)
    ]
    assert len(residues) >= JUSTIFIED_LINE_FLOOR
    assert all(residue >= 0 for residue in residues), "the old `<=` would have caught this"
    assert sum(1 for residue in residues if residue > 0) > 30

    page = render_markdown(sample)
    with pytest.raises(AssertionError, match="carry a residue"):
        _assert_justified_lines_end_on_the_margin(page, measure)


def test_interline_glue_keeps_consecutive_baselines_a_constant_distance_apart(
    page: Rendered,
) -> None:
    # §679's whole purpose. Within one paragraph the baselines sit
    # `\baselineskip` apart whatever the ascenders and descenders on each line,
    # which is what makes prose look set rather than stacked.
    lines = [cmd for cmd in page.cmds if isinstance(cmd, Line) and cmd.width == MEASURE]
    gaps = [b.y - a.y for a, b in zip(lines, lines[1:], strict=False)]
    body = Theme.build().style(BlockKind.PARAGRAPH).interline.baselineskip.width
    # The commonest gap is the body baselineskip: most consecutive pairs are two
    # lines of the same paragraph.
    assert gaps
    assert max(set(gaps), key=gaps.count) == body


# --------------------------------------------------------------------------
# The artifacts
# --------------------------------------------------------------------------


def test_every_artifact_is_non_empty_well_formed_svg(page: Rendered, body_size: Scaled) -> None:
    sigma = render_sigma(body_size)
    comparison = render_sigma_comparison(body_size)
    highlighted, _ = render_selection(page)
    documents = {
        "markdown.svg": render(page.cmds, page.width, page.height),
        "markdown-debug.svg": render(page.cmds, page.width, page.height, debug=True),
        "sigma.svg": render(sigma.cmds, sigma.width, sigma.height),
        "sigma-compare.svg": render(comparison.cmds, comparison.width, comparison.height),
        "selection.svg": highlighted,
    }
    for name, document in documents.items():
        root = _parse(document)
        assert root.tag == f"{SVG}svg", name
        assert list(root.iter(f"{SVG}path")), f"{name} contains no glyph outlines"
        assert "<text" not in document, f"{name} fell back to a text element"


def test_the_debug_overlay_adds_structure_and_leaves_the_glyphs_alone(page: Rendered) -> None:
    plain = _parse(render(page.cmds, page.width, page.height))
    debugged = _parse(render(page.cmds, page.width, page.height, debug=True))

    def glyphs(root: ElementTree.Element) -> list[str | None]:
        return [path.get("transform") for path in root.iter(f"{SVG}path")]

    assert glyphs(plain) == glyphs(debugged)
    assert not list(plain.iter(f"{SVG}line"))
    assert len(list(debugged.iter(f"{SVG}line"))) > 30


def test_the_selection_artifact_highlights_several_lines_and_copies_their_text(
    page: Rendered,
) -> None:
    document, selected = render_selection(page)
    root = _parse(document)
    highlights = [rect for rect in root.iter(f"{SVG}rect") if rect.get("fill-opacity")]
    assert len(highlights) >= 3, "the selection should span several lines"
    assert len(selected) > 80
    # A line break introduced by wrapping is a space, not a newline: copying a
    # wrapped paragraph must not freeze this column's width into the clipboard.
    assert "\n" not in selected


def test_a_multi_line_selections_rects_all_have_the_same_height_within_a_paragraph(
    page: Rendered,
) -> None:
    # The descender case. A highlight sized to the ink of whichever glyphs happen
    # to be on a line makes a line of lowercase text visibly shorter than the one
    # above it; sizing it to the line box does not.
    document, _ = render_selection(page)
    root = _parse(document)
    heights = [
        int(rect.get("height") or 0) for rect in root.iter(f"{SVG}rect") if rect.get("fill-opacity")
    ]
    assert heights
    # More than one distinct height is expected -- the selection crosses a
    # heading -- but the body lines must agree with each other exactly.
    commonest = max(set(heights), key=heights.count)
    assert heights.count(commonest) >= len(heights) - 2


# --------------------------------------------------------------------------
# The layout layer this script owns
# --------------------------------------------------------------------------


def test_a_list_markers_first_line_starts_left_of_the_text_it_labels(sample: str) -> None:
    # TeX's `\item`: the marker hangs in the space the indent reserves, so every
    # item's text lines up whatever the marker's width -- which is what stops a
    # two-digit ordered marker pushing its own first line out of alignment.
    from imscribe.ui import PROSE_BREAKING, _text_boxes

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document(sample, theme, fontlib_metrics)
    items = [
        block
        for block in document.blocks
        if isinstance(block, TextBlock) and block.kind is BlockKind.ORDERED_ITEM
    ]
    assert items
    for block in items:
        boxes = _text_boxes(block, theme, MEASURE, measure, PROSE_BREAKING)
        assert boxes[0].shift_amount < block.left_indent
        for box in boxes[1:]:
            assert box.shift_amount == block.left_indent


def test_a_two_digit_ordered_marker_keeps_the_full_gap_before_its_own_text(
    bundled_fonts: Path,
) -> None:
    # The gutter is sized from the marker, so "10." has to fit in it with the
    # whole `marker_gap` still to spare -- not merely to stay on the page. At the
    # 1.5 em gutter this theme used to have, "10." in Roboto at the body size is
    # 1.39 em against 1.0 em of room, and the marker ate all but a tenth of an em
    # of the gap and touched its own text.
    #
    # Real fonts and not the fake: the claim is about one particular face's digit
    # advances, and a fake with round numbers would be asserting its own fixture.
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    source = "".join(f"{n}. Item {n} of the list.\n" for n in range(1, 13))
    box = compose(build_document(source, theme, fontlib_metrics), theme, MEASURE, measure)
    cmds = ship(box, Point(0, box.height), measure=measure)

    items = [cmd for cmd in cmds if isinstance(cmd, Line) and cmd.start < cmd.end]
    assert len(items) == 12
    for number, line in zip(range(1, 13), items, strict=True):
        glyphs = [
            cmd for cmd in cmds if isinstance(cmd, Glyph) and line.start <= cmd.index < line.end
        ]
        label = f"{number}."
        marker, first_letter = glyphs[: len(label)], glyphs[len(label)]
        assert [chr(glyph.codepoint) for glyph in marker] == list(label)

        last = marker[-1]
        marker_right = last.x + measure(CharNode(last.font, last.codepoint)).width
        # The text of every item starts at the gutter, one and two digits alike,
        # and the gap between the marker and it is exactly what the theme asked
        # for rather than whatever was left over.
        assert first_letter.x == theme.list_indent
        assert first_letter.x - marker_right == theme.marker_gap


def test_a_block_quote_is_barred_down_the_margin_it_gave_up(page: Rendered) -> None:
    # `Theme.quote_rule_thickness` existed and nothing drew it, because the rule
    # has to be exactly as tall as the quote and the quote's height is not known
    # until its paragraphs are packed. The bar is identified by its width here,
    # which is the only rule in the document narrower than the measure.
    theme = Theme.build()
    bars = [
        cmd
        for cmd in page.cmds
        if isinstance(cmd, RuleRect) and cmd.width == theme.quote_rule_thickness
    ]
    assert len(bars) == 1
    (bar,) = bars

    # Innermost lines only: the barred quote is an hbox, so ship-out emits a
    # container `Line` over the whole of it, and counting that one would make the
    # bar trivially agree with itself.
    model = SelectionModel.from_commands(page.cmds)
    quoted = [
        fragment.line
        for fragment in model.fragments
        if bar.y <= fragment.line.y - fragment.line.height
        and fragment.line.y + fragment.line.depth <= bar.y + bar.height
    ]
    assert len(quoted) >= 3
    assert bar.y == min(line.y - line.height for line in quoted)
    assert bar.y + bar.height == max(line.y + line.depth for line in quoted)
    assert bar.x + bar.width <= min(line.x for line in quoted)


def test_the_tables_header_rule_reaches_the_same_margin_the_prose_does(page: Rendered) -> None:
    # Columns were apportioned by natural width and scaled down only, so the
    # table stopped about 150 pt short of the right margin while the paragraph
    # above it ran to it. The thematic break always reached the margin; now the
    # table's header rule reaches the same number, and asserting they are the
    # *same* number is what stops one drifting from the other.
    theme = Theme.build()
    horizontals = [
        cmd
        for cmd in page.cmds
        if isinstance(cmd, RuleRect) and cmd.width > theme.quote_rule_thickness
    ]
    # The thematic break and the table's header rule, and nothing else.
    assert len(horizontals) == 2
    for rule in horizontals:
        assert rule.x + rule.width == MARGIN + MEASURE


def test_a_ragged_block_keeps_its_interword_spaces_at_their_natural_width(
    sample: str,
) -> None:
    # Ragged-right is `\rightskip = 0pt plus 1fil` and nothing else. Because the
    # `fil` outranks every finite stretch in the line, the interword glue is
    # never asked to move, which is why ragged text has even colour and
    # justified text does not.
    from imscribe.linebreak import break_paragraph
    from imscribe.ui import PROSE_BREAKING, _shape, _skips

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document(sample, theme, fontlib_metrics)
    heading = next(
        block
        for block in document.blocks
        if isinstance(block, TextBlock) and block.kind is BlockKind.HEADING_2
    )
    paragraph = break_paragraph(
        heading.material,
        _shape(heading, MEASURE),
        _skips(heading.style.align, PROSE_BREAKING),
        measure=measure,
    )
    from imscribe.units import GlueOrder

    assert all(line.box.glue_order is GlueOrder.FIL for line in paragraph.lines)


def test_a_hanging_indent_shape_narrows_every_line_after_the_first() -> None:
    shape = ParShape((LineSpec(MEASURE), LineSpec(MEASURE - 1000, 1000)))
    assert shape.for_line(1).width == MEASURE
    assert shape.for_line(2).indent == 1000
    assert shape.for_line(99) == shape.for_line(2)

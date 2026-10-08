"""
The Themes page and the demo's tokeniser: what a change rebuilds, counted.

Three kinds of test, and which is which matters when one goes red:

- **plain functions** -- `advtext.ui.pages._syntax` on strings, the schemes and
  face sets as data, `snap_height`. No ImGui.
- **the page's state without a frame** -- the four setters, the documents built.
- **real ImGui frames with no backend** -- `ThemesPage.draw` inside
  `imgui.new_frame()` / `imgui.render()` in a bare context, the way
  `tests/test_pages.py` drives the shell. The widgets run, the views lay out and
  emit vertices, injected mouse events are hit-tested. No window, no GPU, and
  **no font atlas**: `PageContext.build()` has no fonts, so every glyph is drawn
  in whatever ImGui has bound. That changes no count this file asserts.

The real window is `tests/test_pages.py::test_every_discovered_page_runs_in_a_real_window`,
which selects every page for a few frames under Xvfb.

**One private read, on purpose.** `test_the_public_count_is_the_unit_caches_own_miss_count`
reads `BareView._units.stats()` to check that the page's count of re-shipped
units -- made from `BareView.layout` alone -- is the number of units the cache
really built. It found two ways the public count was wrong before it was right;
the page's docstring has both.

Nothing here says how a scheme looks. The colour assertions are "this ink
reached the vertex buffer", per scheme.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from advtext import fontlib
from advtext.fontmetrics import Face
from advtext.markdown import CodeBlock, TextBlock, build_document
from advtext.nodes import CharNode
from advtext.spans import material_text
from advtext.style import Align, BlockKind, Theme, fontlib_metrics, parse_font_key
from advtext.ui.bare_view import block_kind
from advtext.ui.pages import PageContext, demo_text, discover
from advtext.ui.pages import _syntax as syntax
from advtext.ui.pages.themes import (
    COLOURS,
    FACE_SETS,
    FALLBACK_MARKDOWN,
    MAX_HEIGHT_PX,
    MIN_HEIGHT_PX,
    PAGE,
    Rebuild,
    ThemesPage,
    snap_height,
)
from advtext.units import px_from_sp

DISPLAY = (1100.0, 800.0)
PARKED = (DISPLAY[0] - 2.0, 2.0)

PYTHON = '''\
def spans(block, inks):
    """Ranges, each
    with an ink."""
    for start in tokens(block):  # a comment, with a "quote"
        if start == 0x2A or define_class:
            yield start, 1_000.5, 'it is # not a comment'
    return None
'''


# ----------------------------------------------------------------------
# The tokenisers
# ----------------------------------------------------------------------


def _kinds(text: str, language: str) -> list[tuple[str, str]]:
    return [(text[start:end], kind) for start, end, kind in syntax.tokens(text, language)]


def test_python_is_recognised_by_the_first_word_of_the_info_string() -> None:
    assert syntax.is_python("python")
    assert syntax.is_python("  Py title=x ")
    assert syntax.is_python("python3")
    assert not syntax.is_python("")
    assert not syntax.is_python("sh python")
    assert not syntax.is_python("pythonic")


def test_python_tokens_are_the_four_kinds_and_nothing_else() -> None:
    found = _kinds(PYTHON, "python")
    assert ("def", "keyword") in found
    assert ("for", "keyword") in found and ("in", "keyword") in found
    assert ("None", "keyword") in found and ("yield", "keyword") in found
    assert ("0x2A", "number") in found and ("1_000.5", "number") in found
    assert ('# a comment, with a "quote"', "comment") in found
    assert ("'it is # not a comment'", "string") in found
    assert ('"""Ranges, each\n    with an ink."""', "string") in found
    assert {kind for _, kind in found} == set(syntax.KINDS)
    # A keyword inside a name is part of the name: `define_class` holds two.
    words = [text for text, kind in found if kind == "keyword"]
    assert words.count("def") == 1 and "class" not in words
    # And the digits of a name are not a number.
    assert _kinds("x1 = y_2", "python") == []


def test_tokens_are_in_order_and_never_overlap() -> None:
    for language in ("python", "", "sh"):
        for text in (PYTHON, FALLBACK_MARKDOWN, "a = 'x' # y\n/* z\n */ 3", "", "'''"):
            end = 0
            for start, stop, kind in syntax.tokens(text, language):
                assert end <= start < stop <= len(text)
                assert kind in syntax.KINDS
                end = stop


def test_a_string_prefix_is_part_of_the_string_and_a_word_before_a_quote_is_not() -> None:
    assert _kinds("rb\"x\" f'y'", "python") == [('rb"x"', "string"), ("f'y'", "string")]
    assert _kinds('bar"x"', "python") == [('"x"', "string")]


def test_an_unclosed_string_runs_to_the_end_of_its_line_and_no_further() -> None:
    assert _kinds("a = 'half\nb = 1", "python") == [("'half", "string"), ("1", "number")]
    # A triple quote has no line to stop at: it takes the rest.
    assert _kinds('"""doc\nmore', "python") == [('"""doc\nmore', "string")]


def test_the_fallback_has_comments_strings_and_numbers_and_no_keywords() -> None:
    text = 'for x in 3: return "s" // c\n# d\n/* e\nf */ 0x1F'
    assert _kinds(text, "") == [
        ("3", "number"),
        ('"s"', "string"),
        ("// c", "comment"),
        ("# d", "comment"),
        ("/* e\nf */", "comment"),
        ("0x1F", "number"),
    ]
    # The same text as Python does have keywords, which is the whole difference.
    assert ("for", "keyword") in _kinds(text, "python")


def test_the_two_slashes_of_a_url_are_not_a_comment() -> None:
    assert _kinds("see http://example.org/a//b now", "sh") == [("//b now", "comment")]
    assert _kinds("see http://example.org/a now", "sh") == []


def test_line_tokens_cuts_a_multi_line_token_at_every_line_end() -> None:
    lines = PYTHON.splitlines()
    per_line = syntax.line_tokens(lines, "python")
    assert len(per_line) == len(lines)
    # The docstring opens on line 1 and closes on line 2: a string on both.
    assert [(lines[1][a:b], kind) for a, b, kind in per_line[1]] == [('"""Ranges, each', "string")]
    assert [(lines[2][a:b], kind) for a, b, kind in per_line[2]] == [
        ('    with an ink."""', "string")
    ]
    # Every piece is inside its own line, and the pieces say what `tokens` said.
    rebuilt = []
    for line, found in zip(lines, per_line, strict=True):
        for start, end, kind in found:
            assert 0 <= start < end <= len(line)
            rebuilt.append((line[start:end], kind))
    whole = [
        (piece, kind)
        for text, kind in _kinds("\n".join(lines), "python")
        for piece in text.split("\n")
        if piece
    ]
    assert rebuilt == whole


def test_line_tokens_keeps_empty_lines_and_an_empty_input() -> None:
    assert syntax.line_tokens([], "python") == ()
    assert syntax.line_tokens(["", "x = 1", ""], "python") == ((), ((4, 5, "number"),), ())
    # Tokenised one at a time the second line would be code, not a comment.
    assert syntax.line_tokens(["/* a", "b */"], "c") == (
        ((0, 4, "comment"),),
        ((0, 4, "comment"),),
    )


INKS = syntax.SyntaxInks(keyword=1, string=2, comment=3, number=4)


def test_an_ink_is_looked_up_by_kind_and_an_unknown_kind_is_an_error() -> None:
    assert [INKS.ink(kind) for kind in syntax.KINDS] == [3, 2, 4, 1]
    with pytest.raises(KeyError):
        INKS.ink("name")


def test_line_colours_is_the_shape_a_diff_view_takes() -> None:
    colour = syntax.line_colours(INKS)
    assert colour(["x = 1  # c", "return 'a'"], "python") == (
        ((4, 5, 4), (7, 10, 3)),
        ((0, 6, 1), (7, 10, 2)),
    )
    assert colour(["return 1"], "") == (((7, 8, 4),),)


def _code_blocks(source: str) -> list[CodeBlock]:
    document = build_document(source, Theme.build(), fontlib_metrics)
    return [block for block in document.blocks if isinstance(block, CodeBlock)]


def test_colour_spans_cover_exactly_the_tokens_of_the_block_as_it_is_set(
    bundled_fonts: Path,
) -> None:
    (block,) = _code_blocks("```python\ndef f():\n\treturn 'a'  # b\n```\n")
    text = material_text(block).text
    # The tab is expanded in the material, so the tokeniser must read that text.
    assert "\t" not in text
    spans = syntax.colour_spans(block, INKS)
    assert [span.ink for span in spans] == [
        INKS.ink(kind) for _, _, kind in syntax.tokens(text, "python")
    ]
    assert [span.ink for span in spans] == [1, 1, 2, 3]
    assert all(span.mark is None and span.end > span.start for span in spans)


def test_colour_spans_use_the_fences_own_language_unless_told_another(
    bundled_fonts: Path,
) -> None:
    (block,) = _code_blocks("```sh\nfor x in 1\n```\n")
    assert block.language == "sh"
    assert [span.ink for span in syntax.colour_spans(block, INKS)] == [4]
    assert [span.ink for span in syntax.colour_spans(block, INKS, "python")] == [1, 1, 4]


def test_the_page_scan_does_not_take_the_tokeniser_for_a_page() -> None:
    found = discover()
    assert all("_syntax" not in failure.module for failure in found.failures)
    assert found.find("Themes") is PAGE
    assert found.find("_syntax") is None


# ----------------------------------------------------------------------
# Schemes and face sets, as data
# ----------------------------------------------------------------------


def test_there_are_four_schemes_and_two_of_them_are_dark() -> None:
    assert [colours.name for colours in COLOURS] == ["page", "dark", "terminal", "notes"]
    assert [colours.dark for colours in COLOURS] == [False, True, True, False]
    # Colours only: every one of the sixteen syntax inks is opaque and distinct
    # within its scheme.
    for colours in COLOURS:
        inks = [colours.syntax.ink(kind) for kind in syntax.KINDS]
        assert len(set(inks)) == 4 and all(ink >> 24 == 0xFF for ink in inks)


def _faces_of(theme: Theme, source: str) -> dict[BlockKind, set[Face]]:
    document = build_document(source, theme, fontlib_metrics)
    out: dict[BlockKind, set[Face]] = {}
    for block in document.blocks:
        if isinstance(block, TextBlock):
            faces = {
                parse_font_key(node.font).face
                for node in block.material
                if isinstance(node, CharNode)
            }
            out.setdefault(block_kind(block), set()).update(faces)
    return out


SMALL = "# Heading\n\nBody with **bold** and *italic* words.\n"


def test_the_three_face_sets_put_the_faces_where_their_labels_say(bundled_fonts: Path) -> None:
    roboto, mono, mixed = (face_set.theme(16.0, 96.0, fontlib_metrics) for face_set in FACE_SETS)
    assert [face_set.name for face_set in FACE_SETS] == ["roboto", "mono", "mixed"]
    assert [face_set.align for face_set in FACE_SETS] == [Align.JUSTIFY, Align.LEFT, Align.LEFT]

    faces = _faces_of(roboto, SMALL)
    assert faces[BlockKind.PARAGRAPH] == {Face.PROSE, Face.PROSE_BOLD, Face.PROSE_ITALIC}

    # AD-gallery's finding, held: `Faces.mono()` alone would give Roboto Bold here.
    faces = _faces_of(mono, SMALL)
    assert faces[BlockKind.HEADING_1] == {Face.CODE}
    assert faces[BlockKind.PARAGRAPH] == {Face.CODE}

    # And the mix is that other answer, on purpose.
    faces = _faces_of(mixed, SMALL)
    assert faces[BlockKind.HEADING_1] == {Face.PROSE_BOLD}
    assert faces[BlockKind.PARAGRAPH] == {Face.CODE, Face.PROSE_BOLD}


@pytest.mark.parametrize("height", [10.0, 13.5, 16.0, 28.0])
@pytest.mark.parametrize("face_set", FACE_SETS, ids=lambda face_set: face_set.name)
def test_the_running_text_is_set_at_the_pixel_height_asked_for(
    bundled_fonts: Path, face_set: Any, height: float
) -> None:
    """
    The claim behind the reference line: ascent plus descent of the body, in pixels.

    Checked against `advtext.fontlib` directly rather than against
    `Theme.at_pixel_height`'s own arithmetic.
    """
    theme = face_set.theme(height, 96.0, fontlib_metrics)
    size = theme.style(BlockKind.PARAGRAPH).font.size
    metrics = fontlib.metrics(face_set.faces.regular, float(size))
    drawn = px_from_sp(round(metrics.ascent + metrics.descent), 96.0)
    assert drawn == pytest.approx(height, abs=0.01)


def test_a_slider_value_is_clamped_and_lands_on_a_half_pixel() -> None:
    assert snap_height(16.24) == 16.0
    assert snap_height(16.26) == 16.5
    assert snap_height(1.0) == MIN_HEIGHT_PX
    assert snap_height(99.0) == MAX_HEIGHT_PX


def test_the_demo_document_has_what_the_page_says_it_shows(bundled_fonts: Path) -> None:
    source = demo_text("themes.md")
    assert source is not None
    document = build_document(source, Theme.build(), fontlib_metrics)
    codes = [block for block in document.blocks if isinstance(block, CodeBlock)]
    assert [block.language for block in codes] == ["python", "sh"]
    # Both tokenisers have something to colour, in all four kinds between them.
    kinds = {
        kind
        for block in codes
        for _, _, kind in syntax.tokens(material_text(block).text, block.language)
    }
    assert kinds == set(syntax.KINDS)
    assert source.count("](https://example.org/") == 3


# ----------------------------------------------------------------------
# The page's state, without a frame
# ----------------------------------------------------------------------


@pytest.fixture
def page(bundled_fonts: Path) -> ThemesPage:
    made = PAGE.factory(PageContext.build())
    assert isinstance(made, ThemesPage)
    return made


def test_the_page_opens_on_one_pane_one_document_and_the_first_of_everything(
    page: ThemesPage,
) -> None:
    assert page.documents_built == 1
    assert not page.split and len(page.shown) == 1
    assert page.face_set is FACE_SETS[0] and page.height_px == 16.0
    assert [pane.colours.name for pane in page.panes] == ["page", "dark"]
    assert page.panes[0].view.document is page.panes[1].view.document is page.document
    assert page.status().startswith("Click a link")
    assert page.last is None


def test_the_launch_option_opens_it_split(bundled_fonts: Path) -> None:
    context = PageContext.build(request_page="themes", request_options=("split",))
    made = ThemesPage(context)
    assert made.split and len(made.shown) == 2
    other = PageContext.build(request_page="stream", request_options=("split",))
    assert not ThemesPage(other).split
    assert PAGE.accepts("split") and PAGE.shot_specs() == ("themes", "themes:split")


def test_a_palette_change_builds_no_document_and_touches_no_view(page: ThemesPage) -> None:
    view, document = page.panes[0].view, page.document
    page.set_colours(0, COLOURS[2])
    assert page.documents_built == 1
    assert page.panes[0].view is view and view.document is document
    assert page.panes[0].colours is COLOURS[2]
    # The other pane keeps its own scheme.
    assert page.panes[1].colours is COLOURS[1]


def test_a_theme_change_builds_exactly_one_document_for_both_panes(page: ThemesPage) -> None:
    before = page.document
    page.set_face_set(FACE_SETS[1])
    assert page.documents_built == 2
    assert page.document is not before
    assert all(pane.view.document is page.document for pane in page.panes)
    assert all(pane.view.theme is page.theme for pane in page.panes)
    page.set_height(20.2)
    assert page.height_px == 20.0 and page.documents_built == 3


def test_a_change_to_what_is_already_so_does_nothing(page: ThemesPage) -> None:
    page.set_colours(0, COLOURS[0])
    page.set_face_set(FACE_SETS[0])
    page.set_height(16.1)
    page.set_split(False)
    assert page.documents_built == 1
    assert page.account() is not None  # the opening bill, and only that
    assert page.account() is None


def test_without_the_demo_file_the_page_still_has_a_document(bundled_fonts: Path) -> None:
    made = ThemesPage(PageContext.build(), source=FALLBACK_MARKDOWN)
    assert any(isinstance(block, CodeBlock) for block in made.document.blocks)
    assert made.panes[0].colour_code() > 0


# ----------------------------------------------------------------------
# Real frames
# ----------------------------------------------------------------------


def _frame(
    page: ThemesPage,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    wheel: float | None = None,
    size: tuple[float, float] = DISPLAY,
) -> set[int]:
    """
    One frame of the page in a window filling the display. Returns every vertex colour.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*size)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*size))
        imgui.begin("##advtext-themes-test", None, imgui.WindowFlags_.no_decoration.value)
        page.draw()
        imgui.end()
    finally:
        imgui.render()
    colours: set[int] = set()
    for draw_list in imgui.get_draw_data().cmd_lists:
        buffer = draw_list.vtx_buffer
        colours.update(int(buffer[index].col) for index in range(buffer.size()))
    return colours


@pytest.fixture
def shown(page: ThemesPage) -> Iterator[ThemesPage]:
    """
    The page after two settling frames, mouse parked and up.
    """
    _frame(page, mouse=PARKED, left=False)
    _frame(page, mouse=PARKED)
    yield page
    _frame(page, mouse=PARKED, left=False)


def test_the_first_frame_lays_out_everything_and_the_second_nothing(page: ThemesPage) -> None:
    _frame(page, mouse=PARKED, left=False)
    opened = page.last
    assert opened is not None and opened.cause == "open"
    assert opened.documents == 1
    assert opened.reshipped == opened.units == opened.blocks > 10
    _frame(page, mouse=PARKED)
    assert page.last is opened
    stats = page.panes[0].stats
    assert stats is not None and stats.glyphs > 300 and stats.rules >= 1
    assert page.panes[0].view.unmapped_blocks == 0
    assert page.panes[1].stats is None  # hidden: never drawn


def test_a_palette_change_re_ships_nothing_and_lays_nothing_out(shown: ThemesPage) -> None:
    layout = shown.panes[0].view.layout
    shown.set_colours(0, COLOURS[1])
    _frame(shown)
    bill = shown.last
    assert bill is not None
    assert (bill.cause, bill.documents, bill.reshipped, bill.blocks) == ("palette", 0, 0, 0)
    assert bill.units > 10
    assert shown.panes[0].view.layout is layout
    assert bill.line() == (
        f"last change: palette -- documents built 0, units re-shipped 0 of {bill.units}, "
        "blocks re-broken 0"
    )


def test_every_scheme_reaches_the_vertex_buffer_and_the_last_one_leaves_it(
    shown: ThemesPage,
) -> None:
    """
    Per scheme: body ink, link ink, all four syntax inks and the ground are drawn.

    And the control: the syntax inks of the scheme just left are gone, so a
    palette change that kept the old `ColourSpan`s would fail here.
    """
    previous: set[int] = set()
    for colours in (COLOURS[1], COLOURS[2], COLOURS[3], COLOURS[0]):
        shown.set_colours(0, colours)
        drawn = _frame(shown)
        wanted = {
            colours.palette.ink,
            colours.palette.link,
            colours.background,
            *(colours.syntax.ink(kind) for kind in syntax.KINDS),
        }
        assert wanted <= drawn, colours.name
        assert not (previous - wanted) & drawn, colours.name
        previous = {colours.syntax.ink(kind) for kind in syntax.KINDS}


@pytest.mark.parametrize("change", ["faces", "size"])
def test_a_theme_change_re_ships_every_unit_once(shown: ThemesPage, change: str) -> None:
    if change == "faces":
        shown.set_face_set(FACE_SETS[1])
    else:
        shown.set_height(21.0)
    _frame(shown)
    bill = shown.last
    assert bill is not None and bill.cause == change
    assert bill.documents == 1
    assert bill.reshipped == bill.units == bill.blocks > 10
    _frame(shown)
    assert shown.last is bill


def test_the_split_lays_out_both_panes_and_coming_straight_back_is_free(
    shown: ThemesPage,
) -> None:
    single = shown.last
    assert single is not None
    shown.set_split(True)
    _frame(shown)
    both = shown.last
    assert both is not None and both.cause == "split" and both.documents == 0
    assert both.units == 2 * single.units == both.reshipped
    widths = {pane.view.layout.width for pane in shown.panes if pane.view.layout is not None}
    assert len(widths) == 1

    shown.set_split(False)
    _frame(shown)
    back = shown.last
    assert back is not None and back.cause == "split"
    assert (back.units, back.reshipped, back.documents) == (single.units, 0, 0)

    # The second view was kept as it was: showing it again costs nothing either.
    shown.set_split(True)
    _frame(shown)
    again = shown.last
    assert again is not None and (again.units, again.reshipped) == (both.units, 0)


def test_returning_to_the_face_set_just_left_builds_a_document_and_ships_nothing(
    shown: ThemesPage,
) -> None:
    shown.set_face_set(FACE_SETS[1])
    _frame(shown)
    shown.set_face_set(FACE_SETS[0])
    _frame(shown)
    bill = shown.last
    assert bill is not None and bill.cause == "faces"
    assert bill.documents == 1 and bill.reshipped == 0 and bill.units > 10
    # A third state in between pushes the first out, and the return is paid for.
    shown.set_face_set(FACE_SETS[1])
    _frame(shown)
    shown.set_face_set(FACE_SETS[2])
    _frame(shown)
    shown.set_face_set(FACE_SETS[0])
    _frame(shown)
    paid = shown.last
    assert paid is not None and paid.reshipped == paid.units


def test_a_resize_nobody_asked_for_is_billed_as_width(shown: ThemesPage) -> None:
    _frame(shown, size=(900.0, 800.0))
    bill = shown.last
    assert bill is not None and bill.cause == "width"
    assert bill.documents == 0 and bill.reshipped == bill.units


def _misses(page: ThemesPage) -> int:
    # The one private read in this file; see the module docstring.
    return sum(pane.view._units.stats().misses for pane in page.panes)


def test_the_public_count_is_the_unit_caches_own_miss_count(page: ThemesPage) -> None:
    """
    `Rebuild.reshipped`, made from `BareView.layout`, against the cache's own counter.

    Over a script that visits every cause, twice round, including the returns
    the cache answers by value and from two passes back. The two must agree at
    every step, and the block-level cache must never have been asked: every unit
    of this document is one block, which is what makes `Rebuild.blocks` exact
    here and not only a bound.
    """
    script: list[tuple[str, Any]] = [
        ("open", None),
        ("palette", lambda: page.set_colours(0, COLOURS[3])),
        ("size", lambda: page.set_height(19.0)),
        ("faces", lambda: page.set_face_set(FACE_SETS[1])),
        ("split", lambda: page.set_split(True)),
        ("palette", lambda: page.set_colours(1, COLOURS[2])),
        ("split", lambda: page.set_split(False)),
        ("split", lambda: page.set_split(True)),
        ("faces", lambda: page.set_face_set(FACE_SETS[2])),
        ("faces", lambda: page.set_face_set(FACE_SETS[1])),
        ("size", lambda: page.set_height(12.5)),
        ("size", lambda: page.set_height(19.0)),
        ("split", lambda: page.set_split(False)),
        ("faces", lambda: page.set_face_set(FACE_SETS[0])),
    ]
    seen: list[Rebuild] = []
    for cause, change in script:
        before = _misses(page)
        if change is not None:
            change()
        _frame(page, mouse=PARKED, left=False)
        bill = page.last
        assert bill is not None and bill.cause == cause
        assert bill.reshipped == _misses(page) - before, (cause, len(seen))
        assert bill.blocks == bill.reshipped
        seen.append(bill)
    assert {bill.cause for bill in seen} == {"open", "palette", "size", "faces", "split"}
    # Both outcomes happened, so agreement is not zero equalling zero throughout.
    assert any(bill.reshipped == 0 for bill in seen if bill.cause != "palette")
    assert any(bill.reshipped == bill.units for bill in seen)
    assert all(pane.view._blocks.stats().misses == 0 for pane in page.panes)
    assert page.bills.keys() == {"open", "palette", "size", "faces", "split"}


def _middle_of(view: Any, link: Any) -> tuple[float, float]:
    rect = link.rects[0]
    assert view.origin is not None
    return (
        view.origin[0] + px_from_sp(rect.x + rect.width // 2, view.px_per_inch),
        view.origin[1] + px_from_sp(rect.y + rect.height // 2, view.px_per_inch),
    )


def test_a_clicked_link_is_shown_on_the_status_line_and_opens_nothing(shown: ThemesPage) -> None:
    view = shown.panes[0].view
    links = view.visible_links
    assert [link.target for link in links[:2]] == [
        "https://example.org/window",
        "https://example.org/links",
    ]
    _frame(shown, mouse=_middle_of(view, links[1]))
    assert view.hovered_link == "https://example.org/links"
    _frame(shown, left=True)
    _frame(shown, left=False)
    assert shown.followed == ["https://example.org/links"]
    assert shown.status() == "link 1: https://example.org/links"
    assert view.selection.is_empty
    # A click is not a change to the layout: no bill.
    assert shown.last is not None and shown.last.cause == "open"


def test_the_two_panes_of_a_split_stay_at_one_scroll_position(shown: ThemesPage) -> None:
    """
    Wheel over either pane, and both documents' tops are at the same screen row.

    `BareView.origin` is where the document's top was drawn, so equal `y` in
    two panes of one row is equal scroll. Each pane leads in each direction,
    since the pane drawn second takes the lead a frame later than the first
    does -- and an earlier draft of the page handed the lead straight back to
    whichever pane had *not* moved, which this is the test for.

    A short window, so there is room to scroll both ways.
    """
    short = (DISPLAY[0], 420.0)
    parked = (short[0] - 2.0, 2.0)
    shown.set_split(True)
    for _ in range(6):
        _frame(shown, mouse=parked, size=short)
    first, second = (pane.view for pane in shown.panes)
    assert first.origin is not None and second.origin is not None
    top = first.origin[1]
    assert second.origin[1] == top

    for over, wheel in ((first, -2.0), (second, -1.0), (second, 1.0), (first, 1.0)):
        assert over.origin is not None
        before = first.origin[1]
        _frame(shown, mouse=(over.origin[0] + 40.0, 300.0), wheel=wheel, size=short)
        for _ in range(6):
            _frame(shown, size=short)
        assert first.origin is not None and second.origin is not None
        assert first.origin[1] == second.origin[1]
        if wheel < 0:
            assert first.origin[1] < before
        else:
            assert first.origin[1] > before
    assert first.origin[1] < top


def test_a_pane_opened_by_the_split_arrives_where_the_first_already_is(
    shown: ThemesPage,
) -> None:
    # A short window, so that the one wide pane has something to scroll: at the
    # full height the document is shorter than the pane and the wheel does nothing.
    short = (DISPLAY[0], 420.0)
    parked = (short[0] - 2.0, 2.0)
    for _ in range(3):
        _frame(shown, mouse=parked, size=short)
    view = shown.panes[0].view
    assert view.origin is not None
    top = view.origin[1]
    _frame(shown, mouse=(view.origin[0] + 40.0, 300.0), wheel=-4.0, size=short)
    for _ in range(3):
        _frame(shown, size=short)
    assert view.origin[1] < top
    shown.set_split(True)
    for _ in range(8):
        _frame(shown, mouse=parked, size=short)
    other = shown.panes[1].view
    assert other.origin is not None and view.origin is not None
    # The second pane's child window had never been drawn and opens at the top.
    # What is held: it was brought to the first, and the first was not taken
    # back to the top by it.
    assert other.origin[1] == view.origin[1] < top


def test_the_reference_line_states_the_size_the_slider_is_at(page: ThemesPage) -> None:
    page.set_height(13.26)
    assert page.sample().startswith("imgui.text at 13.5 px")


def test_the_debug_overlay_is_the_shared_flag(shown: ThemesPage) -> None:
    shown.context.debug = True
    _frame(shown)
    assert shown.panes[0].view.debug is True
    shown.context.debug = False
    _frame(shown)
    assert shown.panes[0].view.debug is False

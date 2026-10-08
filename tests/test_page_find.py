"""
The Find page: its search held to `find_spans`, its rectangles held to what the
view marks, its cost counted, and the page in frames and in a window.

**Four levels, so nobody reads more into a green run than is there.**

1. `search` over `Index`, and where a match is (`BareView.span_rects`,
   `scroll_for`): no ImGui.
2. `Finder` over a view that records what it is told to colour, and over a
   real `BareView` laid out at a width with no ImGui.
3. The page through `App.gui` in frames of a real `ImGuiContext` with no
   backend: a real `InputText` typed into with injected characters, real Enter
   and Shift+Enter, a real scrolling child.
4. The real app in a real window (`tests/conftest.py::window`), on the sample
   twenty times over: counts printed by the page and read back here.

**Nothing here judges how a mark looks.** A test says which glyph ranges were
handed to the view, where their rectangles are, and that nothing was re-set.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import advtext.ui
import advtext.ui.units
from advtext.markdown import CodeBlock, Document, TableBlock, TextBlock, build_document
from advtext.spans import (
    ColourSpan,
    decorate,
    find_spans,
    map_code_block,
    map_text_block,
    material_text,
)
from advtext.stream import StreamDocument
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui.app import App, parse_tab_request
from advtext.ui.bare_view import BareView, scroll_for
from advtext.ui.pages import PageContext
from advtext.ui.pages import find as page
from advtext.ui.pages.find import (
    CURRENT_MARK,
    HIT_MARK,
    Finder,
    Index,
    Match,
    search,
)
from advtext.ui.stream_view import StreamView
from advtext.units import Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

SAMPLE = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(encoding="utf-8")
WIDTH = sp_from_px(520.0)
NEEDLES = ("glue", "the", "e", "Knuth", "knuth", "a b", "hpack", "  ", "|", "zzqq", "The model")


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure() -> Any:
    return char_measure(fontlib_metrics)


@pytest.fixture(scope="module")
def sample(theme: Theme) -> Document:
    return build_document(SAMPLE, theme, fontlib_metrics)


def _doc(theme: Theme, source: str) -> Document:
    return build_document(textwrap.dedent(source), theme, fontlib_metrics)


class _Recording(BareView):
    """
    A `BareView` that remembers what it was told to colour, so no test reads a private field.
    """

    def set_colours(self, block: int, spans: Sequence[ColourSpan]) -> None:
        BareView.set_colours(self, block, spans)
        _told(self).append(block)
        if spans:
            _marks(self)[block] = tuple(spans)
        else:
            _marks(self).pop(block, None)

    def clear_colours(self) -> None:
        BareView.clear_colours(self)
        _marks(self).clear()


_MARKS: dict[int, dict[int, tuple[ColourSpan, ...]]] = {}
_TOLD: dict[int, list[int]] = {}


def _marks(view: BareView) -> dict[int, tuple[ColourSpan, ...]]:
    # `BareView` has slots and no room for a test's field, so the record is kept beside it.
    return _MARKS.setdefault(id(view), {})


def _told(view: BareView) -> list[int]:
    return _TOLD.setdefault(id(view), [])


def _view(document: Document, theme: Theme, measure: Any) -> _Recording:
    view = _Recording(document=document, theme=theme, measure=measure)
    _MARKS.pop(id(view), None)
    _TOLD.pop(id(view), None)
    return view


def match_rects(view: BareView, match: Match) -> list[Any]:
    """Where a match is: the view's answer, which is what the page asks."""
    return view.span_rects(match.block, match.start, match.end, cell=match.cell)


def scroll_to_show(top: float, bottom: float, scroll: float, height: float) -> float | None:
    """The page's scroll rule: `scroll_for` with the match's top a third of the way down."""
    return scroll_for(top, bottom, scroll, height, align=page.SHOW_AT)


def cell_text(cell: Any) -> str:
    """A table cell's text, worked out here: its characters, a space for each glue."""
    out = []
    for node in cell.material:
        if hasattr(node, "codepoint"):
            out.append(chr(node.codepoint))
        elif hasattr(node, "spec"):
            out.append(" ")
    return "".join(out)


# ----------------------------------------------------------------------
# 1. The search
# ----------------------------------------------------------------------


@pytest.mark.parametrize("ignore_case", [True, False])
@pytest.mark.parametrize("needle", NEEDLES)
def test_the_indexed_search_finds_exactly_what_find_spans_finds(
    sample: Document, needle: str, ignore_case: bool
) -> None:
    """
    The page searches an index and not `find_spans`, for cost. Same answer, every block.
    """
    found = search(Index.of(sample.blocks), needle, ignore_case=ignore_case)
    expected = [
        Match(number, span.start, span.end)
        for number, block in enumerate(sample.blocks)
        if isinstance(block, TextBlock | CodeBlock)
        for span in find_spans(block, needle, ignore_case=ignore_case)
    ]
    assert list(found.matches) == expected


def test_the_needles_above_are_not_all_misses(sample: Document) -> None:
    index = Index.of(sample.blocks)
    counts = {needle: len(search(index, needle).matches) for needle in NEEDLES}
    assert counts["zzqq"] == 0
    assert sum(1 for count in counts.values() if count) >= 7, counts
    # Case matters when asked to: the sample says "Knuth" and never "knuth".
    assert len(search(index, "knuth", ignore_case=False).matches) == 0
    assert len(search(index, "knuth").matches) == len(search(index, "Knuth").matches) > 0


def test_an_empty_needle_finds_nothing_and_matches_do_not_overlap(theme: Theme) -> None:
    index = Index.of(_doc(theme, "aaaaa aa\n").blocks)
    assert search(index, "") == page.Found()
    assert [(m.start, m.end) for m in search(index, "aa").matches] == [(0, 2), (2, 4), (6, 8)]


def test_a_sharp_s_falls_back_to_matching_case_as_find_spans_does(theme: Theme) -> None:
    """
    Folding `ß` makes two characters of one, so offsets into the folded text are wrong.
    """
    document = _doc(theme, "Die Straße und die STRASSE.\n")
    index = Index.of(document.blocks)
    block = document.blocks[0]
    assert isinstance(block, TextBlock)
    for needle in ("die", "Die", "straße", "strasse", "STRASSE"):
        expected = [(s.start, s.end) for s in find_spans(block, needle, ignore_case=True)]
        assert [(m.start, m.end) for m in search(index, needle).matches] == expected, needle
    assert len(search(index, "die").matches) == 1  # the fallback: "Die" is not found


def test_a_space_finds_a_hard_break_in_prose_and_not_a_line_end_in_code(theme: Theme) -> None:
    document = _doc(
        theme,
        """
        one two\\
        three four

        ```
        one two
        three four
        ```
        """,
    )
    found = search(Index.of(document.blocks), "two three")
    assert [match.block for match in found.matches] == [0]


def test_matches_in_table_cells_are_counted_and_not_among_the_marked(sample: Document) -> None:
    """
    The limit the page states: found in a cell, not markable. Counted independently here.
    """
    cells = [
        cell_text(cell)
        for block in sample.blocks
        if isinstance(block, TableBlock)
        for row in (block.header, *block.rows)
        for cell in row
    ]
    assert "Scaled points, glue orders" in cells
    tables = {n for n, block in enumerate(sample.blocks) if isinstance(block, TableBlock)}
    assert tables
    for needle in ("glue", "no", "Imports"):
        found = search(Index.of(sample.blocks), needle)
        assert found.in_cells == sum(cell.casefold().count(needle.casefold()) for cell in cells) > 0
        assert found.total == len(found.matches) + found.in_cells
        assert not tables & {match.block for match in found.matches}


# ----------------------------------------------------------------------
# 1b. Where a match is
# ----------------------------------------------------------------------


def _laid(document: Document, theme: Theme, measure: Any, width: Scaled = WIDTH) -> _Recording:
    view = _view(document, theme, measure)
    view.layout_for(width)
    return view


def test_a_match_across_a_line_break_is_one_match_with_two_rectangles(
    sample: Document, theme: Theme, measure: Any
) -> None:
    """
    The needle is cut from the text either side of the first line break of a
    paragraph, found by asking the span map where line one ends -- not by
    asking `match_rects`, which is what is under test.
    """
    view = _laid(sample, theme, measure)
    layout = view.layout
    assert layout is not None
    number = next(
        n
        for n, block in enumerate(sample.blocks)
        if isinstance(block, TextBlock) and len(material_text(block).text) > 300
    )
    block = sample.blocks[number]
    assert isinstance(block, TextBlock)
    (unit,) = layout.units_of_block(number)
    mapped = map_text_block(block, unit.cmds)
    assert len(mapped.lines) > 2
    # The line's last indices are what was put there at compose time (the
    # right skip); walk back to the last one that came from the material.
    end = mapped.base + mapped.lines[0][1]
    last = next(
        found
        for found in (mapped.material_index(end - back) for back in range(1, 6))
        if found is not None
    )
    text = material_text(block)
    at = text.indices.index(last)
    needle = text.text[at - 7 : at + 9]
    assert " " in needle and text.text.count(needle) == 1

    finder = Finder(view)
    found = finder.search(needle)
    here = [match for match in found.matches if match.block == number]
    assert len(here) == 1
    first, second = match_rects(view, here[0])
    assert second.y >= first.y + first.height
    assert second.x < first.x  # the second line starts again at the left
    assert first.width > 0 and second.width > 0


def test_a_match_on_one_line_is_one_rectangle_and_it_is_the_mark_the_view_draws(
    sample: Document, theme: Theme, measure: Any
) -> None:
    """
    `match_rects` against `advtext.spans.decorate`, which is what `BareView` fills from.
    """
    view = _laid(sample, theme, measure)
    layout = view.layout
    assert layout is not None
    checked = 0
    for match in search(Index.of(sample.blocks), "the").matches:
        block = sample.blocks[match.block]
        units = layout.units_of_block(match.block)
        if not isinstance(block, TextBlock) or len(units[0].blocks) != 1:
            continue
        mapped = map_text_block(block, units[0].cmds)
        marks = decorate(
            mapped, units[0].model, colours=[ColourSpan(match.start, match.end, mark=1)]
        ).marks
        rects = match_rects(view, match)
        assert rects == [rect for rect, _ in marks]
        assert len(rects) == 1 and rects[0].width > 0
        assert units[0].y <= rects[0].y < units[0].bottom
        checked += 1
    assert checked > 20


def test_a_match_in_a_code_block_and_in_a_quote_has_a_rectangle_inside_its_block(
    theme: Theme, measure: Any
) -> None:
    document = _doc(
        theme,
        """
        A paragraph first, so nothing starts at zero.

        > The first paragraph of a quote.
        >
        > The second holds the needle here.

        ```
        alpha = 1
        beta = needle
        ```
        """,
    )
    view = _laid(document, theme, measure)
    layout = view.layout
    assert layout is not None
    found = search(Index.of(document.blocks), "needle")
    assert len(found.matches) == 2
    quoted, coded = found.matches
    assert isinstance(document.blocks[coded.block], CodeBlock)
    (quote,) = layout.units_of_block(quoted.block)
    assert len(quote.blocks) == 2, "the quote is one unit of two paragraphs"
    for match in (quoted, coded):
        (rect,) = match_rects(view, match)
        (unit,) = layout.units_of_block(match.block)
        assert unit.y <= rect.y and rect.y + rect.height <= unit.bottom
        assert rect.width > 0
        # The rectangle starts at the left edge of the needle's first glyph
        # and reaches past the left edge of its last, as the view set them.
        placed = [
            (line, at)
            for line in view.set_lines(match.block, match.block + 1)
            if (at := "".join(chr(code) for code, _ in line.glyphs).find("needle")) != -1
        ]
        ((line, at),) = placed
        assert rect.y < line.baseline <= rect.y + rect.height
        assert rect.x == line.glyphs[at][1]
        assert line.glyphs[at + 5][1] < rect.x + rect.width
        if at + 6 < len(line.glyphs):
            assert rect.x + rect.width <= line.glyphs[at + 6][1]
    # The quote's needle is in its second paragraph: below the first one's line.
    (rect,) = match_rects(view, quoted)
    assert rect.y > quote.y + rect.height


def test_a_match_in_a_code_block_laid_out_in_pieces_is_found_in_the_right_piece(
    theme: Theme, measure: Any
) -> None:
    """
    `StreamView` cuts a long code block into pieces; a match counts from the block's start.
    """
    lines = [f"line_{number:03d} = {number}" for number in range(60)]
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("```\n" + "\n".join(lines) + "\n```\n")
    stream.close()
    view = StreamView(stream, measure)
    layout = view.layout_for(WIDTH)
    blocks = view.document.blocks
    units = layout.units_of_block(0)
    assert len(units) > 1, "the block was not laid out in pieces; this test tests nothing"
    for wanted in ("line_002", "line_041", "line_059"):
        (match,) = search(Index.of(blocks), wanted).matches
        (rect,) = match_rects(view, match)
        holder = [unit for unit in units if unit.y <= rect.y < unit.bottom]
        assert len(holder) == 1
        # The piece that holds the rectangle holds that source line.
        piece = holder[0].blocks[0]
        assert isinstance(piece, CodeBlock)
        assert wanted in material_text(piece).text
        mapped = map_code_block(piece, base=holder[0].indices_of(0).start)
        assert mapped.count > 0


def test_a_match_nobody_laid_out_has_no_rectangle(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _laid(sample, theme, measure)
    assert view.layout is not None
    assert match_rects(view, Match(len(sample.blocks) + 3, 0, 4)) == []
    table = next(n for n, block in enumerate(sample.blocks) if isinstance(block, TableBlock))
    assert match_rects(view, Match(table, 0, 4)) == []


def test_scroll_to_show_stays_put_for_what_is_in_view_and_moves_for_what_is_not() -> None:
    assert scroll_to_show(300.0, 320.0, 100.0, 600.0) is None
    # Within the margin of an edge counts as out of view.
    assert scroll_to_show(110.0, 130.0, 100.0, 600.0) == 0.0
    assert scroll_to_show(690.0, 710.0, 100.0, 600.0) == 490.0
    # Below, above, and above with nowhere further up to go.
    assert scroll_to_show(5000.0, 5020.0, 100.0, 600.0) == 4800.0
    assert scroll_to_show(900.0, 920.0, 3000.0, 600.0) == 700.0
    assert scroll_to_show(50.0, 70.0, 3000.0, 600.0) == 0.0
    # What it returns shows the span with room to spare.
    target = scroll_to_show(5000.0, 5020.0, 100.0, 600.0)
    assert target is not None and scroll_to_show(5000.0, 5020.0, target, 600.0) is None


# ----------------------------------------------------------------------
# 2. The finder
# ----------------------------------------------------------------------


def test_every_match_is_marked_and_exactly_one_is_the_current(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _view(sample, theme, measure)
    finder = Finder(view)
    found = finder.search("the")
    assert finder.label == f"1 of {len(found.matches)}"
    marks = _marks(view)
    told = [
        (block, span.start, span.end, span.mark, span.ink)
        for block in sorted(marks)
        for span in marks[block]
    ]
    assert [entry[:3] for entry in told] == [(m.block, m.start, m.end) for m in found.matches]
    assert [entry[3] for entry in told] == [CURRENT_MARK] + [HIT_MARK] * (len(told) - 1)
    assert {entry[4] for entry in told} == {None}
    assert CURRENT_MARK != HIT_MARK


def test_a_new_search_drops_the_marks_of_the_one_before(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _view(sample, theme, measure)
    finder = Finder(view)
    finder.search("the")
    assert _marks(view)
    finder.search("zzqq")
    assert _marks(view) == {} and finder.label == "no matches" and finder.match is None
    assert finder.step(1) is None
    finder.search("")
    assert finder.label == ""


def test_next_and_previous_wrap_and_recolour_only_the_blocks_they_leave_and_enter(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _view(sample, theme, measure)
    finder = Finder(view)
    found = finder.search("glue")
    count = len(found.matches)
    assert count > 3

    def current() -> list[tuple[int, int]]:
        return [
            (block, span.start)
            for block, spans in _marks(view).items()
            for span in spans
            if span.mark == CURRENT_MARK
        ]

    for expected in [1, 2, 3]:
        before = finder.match
        _told(view).clear()
        after = finder.step(1)
        assert finder.current == expected and before is not None and after is not None
        assert sorted(set(_told(view))) == sorted({before.block, after.block})
        assert current() == [(after.block, after.start)]
    finder.step(-4)
    assert finder.label == f"{count} of {count}"
    finder.step(1)
    assert finder.label == f"1 of {count}"
    assert current() == [(found.matches[0].block, found.matches[0].start)]


def test_typing_another_letter_keeps_the_current_match_where_the_reader_is(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _view(sample, theme, measure)
    finder = Finder(view)
    finder.search("th")
    finder.step(40)
    before = finder.match
    assert before is not None and before.block > 0
    finder.search("the")
    after = finder.match
    assert after is not None
    assert (after.block, after.start) >= (before.block, before.start)
    earlier = finder.found.matches[: finder.current]
    assert all((m.block, m.start) < (before.block, before.start) for m in earlier)
    # Past the last match there is nowhere at or after: the first one.
    finder.search("th")
    finder.step(-1)
    finder.search("This document is the first")
    assert finder.current == 0


def test_the_current_match_is_placed_in_pixels_of_the_layout(
    sample: Document, theme: Theme, measure: Any
) -> None:
    view = _view(sample, theme, measure)
    finder = Finder(view)
    finder.search("glue")
    assert finder.rects() == [] and finder.span_px() is None  # nothing laid out yet
    layout = view.layout_for(WIDTH)
    tops = []
    for _ in finder.found.matches:
        span = finder.span_px()
        match = finder.match
        assert span is not None and match is not None
        (unit,) = layout.units_of_block(match.block)
        assert px_from_sp(unit.y) <= span[0] < span[1] <= px_from_sp(unit.bottom) + 1e-6
        tops.append(span[0])
        finder.step(1)
    assert tops == sorted(tops) and tops[-1] > tops[0]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


def test_the_cost_of_a_search_is_split_into_finding_and_marking(
    sample: Document, theme: Theme, measure: Any
) -> None:
    finder = Finder(_view(sample, theme, measure), timer=_Clock())
    finder.search("glue")
    finder.search("glu")
    assert finder.keystrokes == 2
    assert finder.search_ms == pytest.approx(1.0) and finder.mark_ms == pytest.approx(1.0)
    lines = page.readouts(finder)
    assert "search 1.00 ms, marks 1.00 ms" in lines[1]
    assert "2 keystrokes: 0 layouts rebuilt, 0 units re-shipped" in lines[1]
    marked, total = len(finder.found.matches), finder.found.total
    assert lines[0].startswith(f"marked {marked} of {total} found")
    assert f"{total - marked} more in table cells, found and not marked" in lines[0]


def test_the_readouts_report_counts_and_judge_nothing(
    sample: Document, theme: Theme, measure: Any
) -> None:
    finder = Finder(_view(sample, theme, measure))
    finder.search("glue")
    text = " ".join(page.readouts(finder)).lower()
    for word in ("better", "worse", "good", "bad", "clean", "crisp", "smooth", "fast", "slow"):
        assert word not in text.split(), word


class _Work:
    """
    Counts the calls that break a block into lines and that ship a unit.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.composed = 0
        self.shipped = 0
        compose = advtext.ui.RunComposer.compose
        ship = advtext.ui.units.ship_unit

        def counted_compose(composer: Any, run: Any) -> Any:
            self.composed += 1
            return compose(composer, run)

        def counted_ship(composed: Any, measure: Any) -> Any:
            self.shipped += 1
            return ship(composed, measure)

        monkeypatch.setattr(advtext.ui.RunComposer, "compose", counted_compose)
        monkeypatch.setattr(advtext.ui.units, "ship_unit", counted_ship)


def test_the_counters_see_a_relayout_and_a_reship_when_there_is_one(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The control for the zero below: `observe` and `_Work` both count when work is done.
    """
    source = "First paragraph, of several words.\n\nSecond paragraph.\n\nThird.\n"
    view = _view(_doc(theme, source), theme, measure)
    finder = Finder(view)
    work = _Work(monkeypatch)
    view.layout_for(WIDTH)
    finder.observe()
    assert (work.composed, work.shipped) == (3, 3)
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (0, 0, 0)

    finder.observe()  # the same layout again: nothing
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (0, 0, 0)

    view.invalidate()  # nothing changed: a layout is built, every unit is found
    view.layout_for(WIDTH)
    finder.observe()
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (1, 0, 0)
    assert (work.composed, work.shipped) == (3, 3)

    view.document = _doc(theme, source.replace("Second", "A different second"))
    view.invalidate()
    view.layout_for(WIDTH)
    finder.observe()
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (2, 1, 0)
    assert (work.composed, work.shipped) == (4, 4)

    view.layout_for(WIDTH // 2)
    finder.observe()
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (2, 1, 1)
    assert work.shipped == 7


# ----------------------------------------------------------------------
# 3. The page, in frames
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
        imgui.begin("##advtext-find-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
    finally:
        imgui.render()


def _key(app: App, key: Any, *, shift: bool = False) -> None:
    """
    Press and release one key, a frame each, with Shift held around it if asked.
    """
    imgui = _imgui()
    io = imgui.get_io()
    if shift:
        io.add_key_event(imgui.Key.mod_shift, True)
    io.add_key_event(key, True)
    _frame(app)
    io.add_key_event(key, False)
    if shift:
        io.add_key_event(imgui.Key.mod_shift, False)
    _frame(app)


def _type(app: App, text: str) -> None:
    io = _imgui().get_io()
    for character in text:
        io.add_input_character(ord(character))
        _frame(app)


_OWN: list[Any] = []


def _open(spec: str = "find") -> tuple[App, page.FindPage]:
    """
    The app on the Find page after two frames, **in an ImGui context of its own**.

    Every other frame test in the suite shares whichever context is current,
    and that is not good enough here: the search box has the same id in every
    app, and ImGui keeps one text-edit state per context. Measured: a second
    app's box, focused after a first app's had been typed into, appended to
    the first app's text (`hpac` + `the`) instead of replacing its own. So each
    app gets a fresh context, left current for whoever runs next; the ones
    this module made earlier are destroyed, and nobody else's is touched.
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
    made = app.page("find")
    assert isinstance(made, page.FindPage)
    return app, made


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


def test_the_page_is_listed_where_the_lead_put_it() -> None:
    spec = page.PAGE
    assert (spec.name, spec.group, spec.order) == ("Find", "Embedding", 130)
    assert spec.shot_specs() == ("find",)
    assert spec.accepts("case") and not spec.accepts("nonsense")


def test_the_page_opens_with_a_needle_already_found_and_marked() -> None:
    made = page.FindPage(_context("find"))
    assert made.copies == page.DEFAULT_COPIES
    finder = made.finder
    assert finder.needle == page.DEFAULT_NEEDLE and finder.ignore_case
    assert len(finder.found.matches) > 0 and finder.found.in_cells > 0
    assert finder.label.startswith("1 of ")
    assert finder.keystrokes == 0, "the opening search is not something anybody typed"
    blocks = len(made.view.document.blocks)
    assert blocks == page.DEFAULT_COPIES * len(
        build_document(SAMPLE, made.context.theme, fontlib_metrics).blocks
    )


def test_the_launch_options_set_the_copies_and_case_matching() -> None:
    two = page.FindPage(_context("find:2,case"))
    one = page.FindPage(_context("find:1"))
    assert (two.copies, one.copies) == (2, 1)
    assert not two.finder.ignore_case and one.finder.ignore_case
    assert len(two.view.document.blocks) == 2 * len(one.view.document.blocks)
    other = page.FindPage(_context("document:3"))
    assert other.copies == page.DEFAULT_COPIES


def test_the_page_does_not_raise_for_a_missing_demo_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = page.FindPage(_context("find:1"))
    assert len(made.view.document.blocks) == 1
    assert len(made.finder.found.matches) == 2


def test_the_page_draws_through_the_shell_and_reports_counts() -> None:
    _, made = _open()
    assert made.frames == 2
    assert made.stats is not None and made.stats.glyphs > 0
    assert made.view.origin is not None and made.view.unmapped_blocks == 0
    layout = made.view.layout
    assert layout is not None
    assert layout.width == sp_from_px(page.TEXT_WIDTH_PX), "the measure is capped, not the body's"
    (line,) = made.report()
    fields = dict(part.split("=", 1) for part in line.split())
    assert fields["frames"] == "2" and fields["rebuilt"] == fields["reshipped"] == "0"
    assert int(fields["marked"]) + int(fields["cells"]) == int(fields["found"])
    assert fields["rects"] == "1" and fields["unmapped"] == "0"


def test_typing_in_the_box_searches_and_neither_breaks_nor_ships_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Real characters into the real `InputText`, a frame each; the work is counted
    at the two functions that do it, not read off the page's own counters.
    """
    app, made = _open()
    work = _Work(monkeypatch)
    layout = made.view.layout
    made.focus()
    _frame(app)
    _frame(app)
    # The box takes the keyboard with its text selected, so typing replaces it.
    _type(app, "hpack")
    finder = made.finder
    assert finder.needle == "hpack" and finder.keystrokes == 5
    assert len(finder.found.matches) > 0 and finder.label.startswith("1 of ")
    _key(app, _imgui().Key.backspace)
    assert finder.needle == "hpac" and finder.keystrokes == 6
    assert (work.composed, work.shipped) == (0, 0)
    assert (finder.rebuilt, finder.reshipped, finder.resized) == (0, 0, 0)
    assert made.view.layout is layout


def test_enter_and_shift_enter_step_and_the_box_keeps_the_keyboard() -> None:
    app, made = _open()
    imgui = _imgui()
    made.focus()
    _frame(app)
    _frame(app)
    _type(app, "the")
    finder = made.finder
    count = len(finder.found.matches)
    assert finder.label == f"1 of {count}"
    _key(app, imgui.Key.enter)
    assert finder.label == f"2 of {count}"
    _key(app, imgui.Key.enter)
    _key(app, imgui.Key.keypad_enter)
    assert finder.label == f"4 of {count}"
    _key(app, imgui.Key.enter, shift=True)
    assert finder.label == f"3 of {count}"
    # Still typing into the box, and appending: Enter did not take the keyboard away.
    _frame(app)
    _type(app, "r")
    assert finder.needle == "ther"


def test_enter_does_nothing_while_the_box_does_not_have_the_keyboard() -> None:
    app, made = _open()
    before = made.finder.label
    _key(app, _imgui().Key.enter)
    assert made.finder.label == before


def _on_screen(made: page.FindPage) -> bool:
    """
    Whether the current match lies inside the scrolling pane, as the page itself reports it.

    Held to the window as well, which is the cruder bound and does not depend
    on the page having recorded its pane correctly.
    """
    origin, span = made.view.origin, made.finder.span_px()
    assert origin is not None and span is not None
    inside = 0.0 <= origin[1] + span[0] and origin[1] + span[1] <= SIZE[1]
    assert made.shown() <= inside
    return made.shown()


def test_stepping_to_a_match_off_screen_scrolls_it_into_view_and_one_on_screen_moves_nothing() -> (
    None
):
    app, made = _open()
    finder = made.finder
    assert _on_screen(made) and made.scrolls == 0
    resting = made.view.origin

    # To the last match: several screens down.
    made.step(-1)
    assert finder.current == len(finder.found.matches) - 1
    span = finder.span_px()
    assert span is not None and span[0] > 3 * SIZE[1]
    assert not _on_screen(made)
    _frame(app)
    _frame(app)
    assert made.scrolls == 1 and _on_screen(made)
    assert made.view.origin is not None and resting is not None
    assert made.view.origin[1] < resting[1] - 2 * SIZE[1]
    assert made.view.origin[0] == resting[0]

    # And round to the first again.
    made.step(1)
    _frame(app)
    _frame(app)
    assert finder.current == 0 and made.scrolls == 2 and _on_screen(made)
    assert made.view.origin == resting

    # A match already in view: the step changes the mark and not the scroll.
    made.step(1)
    span = finder.span_px()
    assert span is not None
    if resting[1] + span[1] + 24.0 <= SIZE[1]:
        _frame(app)
        _frame(app)
        assert made.scrolls == 2 and made.view.origin == resting


def test_a_search_scrolls_to_its_current_match_and_the_checkbox_route_searches_again() -> None:
    app, made = _open()
    made.step(-1)
    _frame(app)
    _frame(app)
    far = made.view.origin
    made.type("first litmus test")  # only in the opening paragraph of each copy
    assert made.finder.current is not None
    _frame(app)
    _frame(app)
    assert _on_screen(made) and made.view.origin != far

    made.type("knuth")
    insensitive = len(made.finder.found.matches)
    made.match_case(True)
    assert not made.finder.ignore_case and made.finder.found.matches == ()
    made.match_case(False)
    assert len(made.finder.found.matches) == insensitive > 0
    _frame(app)


# ----------------------------------------------------------------------
# 4. A real window, on the sample twenty times over
# ----------------------------------------------------------------------

WINDOWED = """
from imgui_bundle import hello_imgui

from advtext.ui import app as advtext_app

state = {"frames": 0}
real_gui = advtext_app.App.gui
NEEDLES = ["g", "gl", "glu", "glue", "glue ", "glue o", "zzqq", "the"]


def watched_gui(self):
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    state["frames"] += 1
    frame = state["frames"]
    made = self.page("find")
    if frame < 5:
        return
    step = frame - 5
    if step % 3 == 0 and step // 3 < len(NEEDLES):
        made.type(NEEDLES[step // 3])
        print(made.report()[0])
    elif step == 3 * len(NEEDLES):
        made.step(-1)
    elif step == 3 * len(NEEDLES) + 4:
        print(made.report()[0])
        hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="find:20")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_the_page_searches_twenty_copies_in_a_real_window_without_resetting_a_line(
    window: Window,
) -> None:
    """
    The real app, `--tab find:20`: eight needles typed three frames apart, then
    a step back from the first match to the last, which is the whole document away.

    Counts only: every search found what the same search finds with no window,
    nothing was re-laid-out or re-shipped by any of it, glyphs were drawn with
    none missing, and the last match ended inside the scrolling pane.
    """
    script = window.out / "find_page.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
    assert len(lines) == 9, done.stdout

    theme = Theme.build()
    document = build_document("\n\n".join([SAMPLE] * 20), theme, fontlib_metrics)
    index = Index.of(document.blocks)
    for number, needle in enumerate(["g", "gl", "glu", "glue", "glue ", "glue o", "zzqq", "the"]):
        got = _fields(lines[number].replace(repr(needle), "_"))
        expected = search(index, needle)
        assert int(got["marked"]) == len(expected.matches), (needle, done.stdout)
        assert int(got["found"]) == expected.total, (needle, done.stdout)
        assert got["keystrokes"] == str(number + 1)
        assert got["rebuilt"] == got["reshipped"] == "0", done.stdout
        assert got["copies"] == "20" and got["blocks"] == str(len(document.blocks))
    last = _fields(lines[-1].replace(repr("the"), "_"))
    assert last["current"] == last["marked"] and int(last["marked"]) > 1000
    assert last["rects"] in ("1", "2") and last["unmapped"] == "0"
    assert int(last["glyphs"]) > 0 and last["missing"] == "0"
    assert int(last["scrolls"]) >= 1 and last["resized"] == "0"
    assert last["shown"] == "1", done.stdout

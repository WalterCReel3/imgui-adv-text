r"""
The page and the cull, and the promise that culling what is drawn does not cull what is copied.

`advtext.ui.CommandIndex` decides which shipped draw commands a window can see.
That decision is arithmetic over absolute coordinates and needs no window, which
is why almost everything here runs as a plain unit test. So does the page --
`page_for` turns a content region into a sheet, a margin and a measure with no
ImGui in sight, which is what lets the typographic argument behind the margin be
checked here rather than only by looking at a screenshot.

`DocumentView.draw` itself is exercised too, at the bottom of the file, in a real
frame with no display. Two things in this change live only there and no pure test
can reach them: which width reaches the line breaker, and which origin reaches
hit testing. A margin applied to the glyphs and not to the mouse looks perfect
and is wrong by a whole margin on every click.

**The claim this file exists to defend is the second one in its title.** Culling
happens after ship-out and after `SelectionModel.from_commands`, so the model
still indexes the whole document and reading-order indices stay dense over it. A
selection dragged past the bottom of the window must copy the off-screen half
too -- copying a long selection is the case `docs/decisions.md` says this project
exists to beat, and a cull that quietly truncated it would beat nothing. Several
tests here would go red if culling ever moved earlier in the pipeline.

Several tests open a real ImGui frame with no display, in the idiom
`tests/test_imgui_draw.py` established and `docs/decisions.md` records: a window
needs a display, a frame does not. They pass `fonts=lambda face: None` so that
they never touch the font atlas, because the atlas is process-global and a second
test module adding faces to it mid-session is a source of failures that have
nothing to do with what is under test.

That reaches further than this file used to claim. `imgui.begin` and
`imgui.begin_child` work inside such a frame, mouse events queued before
`new_frame` are delivered, and `is_item_hovered` answers from them -- so a press
and a drag really can be played into `DocumentView.draw` and the resulting
selection read back, with no window anywhere. `_page_frame` is that harness.

Deliberately not here: scrolling, which is the child window's own state and not
this module's, and anything that needs a swap chain. Those need `immapp.run`, and
`scripts/shot.py` is where they are looked at instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from advtext.backends.imgui_draw import Palette, draw
from advtext.markdown import build_document
from advtext.nodes import CharNode
from advtext.selection import Granularity, Rect, SelectionModel
from advtext.shipout import DrawCmd, Glyph, Line, Point, RuleRect, SetGlue, ship
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import CommandIndex, Viewport, compose, visible_rects
from advtext.ui.document_view import (
    MIN_WIDTH_PX,
    DocumentView,
    Page,
    _granularity_for,
    alphabet_length,
    page_for,
)
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_pt, sp_from_px

ROOT = Path(__file__).resolve().parent.parent
"""
The repository root, for the source check that no module indexes an ImGui IO array.
"""

MEASURE = sp_from_pt(300.0)
"""
A narrow measure, so a short source still produces a document several screens tall.
"""

_SECTION = (
    "# A heading\n\n"
    "One two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty.\n\n"
    "> A quoted paragraph long enough to break over several lines, so that the\n"
    "> bar down its left edge spans more than one of them and a viewport can\n"
    "> land in the middle of it.\n\n"
    "- first item\n- second item\n\n"
    "| a | bb |\n|---|---|\n| 1 | 2 |\n\n"
    "---\n\n"
    "Another paragraph, so that there is material below the table and the rule "
    "for a viewport to exclude.\n\n"
    "```\nfenced code\n```\n\n"
)

SOURCE = _SECTION * 4
"""
One of every block kind, four times over, with a quote whose bar spans several lines.

Repeated because the whole subject here is a document **taller than its window**:
at one section it comes to under 500px and every viewport in the file would cover
the lot, so every cull would be a no-op and every assertion would pass vacuously.
"""


@pytest.fixture(scope="module")
def shipped(bundled_fonts: Any) -> tuple[DrawCmd, ...]:
    """
    `SOURCE` composed at `MEASURE` with real fonts, and shipped.

    Real metrics rather than a fake: the point of these tests is where things
    land vertically, and a fake with round numbers would make every line the
    same height and hide exactly the case a quote bar exercises.
    """
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    box = compose(build_document(SOURCE, theme, fontlib_metrics), theme, MEASURE, measure)
    return tuple(ship(box, Point(0, box.height), measure=measure))


@pytest.fixture(scope="module")
def index(shipped: tuple[DrawCmd, ...]) -> CommandIndex:
    return CommandIndex.of(shipped)


def extent_of(index: CommandIndex, position: int) -> tuple[Scaled, Scaled]:
    """
    The vertical extent the index gives one command.
    """
    return index.tops[position], index.bottoms[position]


def enclosing_line(cmds: tuple[DrawCmd, ...], position: int) -> Line:
    """
    The innermost `Line` a command sits inside: the last one before it.
    """
    for candidate in range(position, -1, -1):
        cmd = cmds[candidate]
        if isinstance(cmd, Line):
            return cmd
    raise AssertionError("no line precedes this command, which ship-out should make impossible")


# -- what a viewport keeps -----------------------------------------------


def test_a_viewport_keeps_exactly_the_commands_whose_extent_it_overlaps(
    index: CommandIndex,
) -> None:
    # Set equality against a brute-force reference over the index's own extents,
    # so the test states the rule rather than re-implementing the filter.
    viewport = Viewport(top=sp_from_px(300.0), bottom=sp_from_px(700.0))
    expected = [
        cmd
        for position, cmd in enumerate(index.cmds)
        if viewport.covers(*extent_of(index, position))
    ]
    assert list(index.visible(viewport)) == expected
    assert 0 < len(expected) < len(index.cmds)


def test_a_viewport_above_the_document_keeps_nothing(index: CommandIndex) -> None:
    assert index.visible(Viewport(top=sp_from_px(-500.0), bottom=sp_from_px(-1.0))) == ()


def test_a_viewport_taller_than_the_document_keeps_every_command(index: CommandIndex) -> None:
    whole = Viewport(top=sp_from_px(-1.0), bottom=sp_from_px(100_000.0))
    assert index.visible(whole) == index.cmds


def test_culling_preserves_reading_order(index: CommandIndex) -> None:
    # A culled list is a legal command list in its own right, which is what lets
    # it go straight to a backend with no other change.
    viewport = Viewport(top=sp_from_px(200.0), bottom=sp_from_px(600.0))
    kept = index.visible(viewport)
    assert list(kept) == [cmd for cmd in index.cmds if cmd in set(kept)]


def test_a_glyph_is_culled_exactly_when_the_line_it_sits_on_is(index: CommandIndex) -> None:
    # The index gives a glyph the extent of its innermost line, and the argument
    # that this is exact rather than generous is in `CommandIndex`: hpack takes a
    # line's height as a maximum over its contents' ink and a strut only raises
    # it, so no glyph's ink escapes its line box.
    for position, cmd in enumerate(index.cmds):
        if not isinstance(cmd, Glyph):
            continue
        line = enclosing_line(index.cmds, position)
        assert extent_of(index, position) == (line.y - line.height, line.y + line.depth)


def test_a_kept_glyph_always_keeps_the_line_that_introduced_it(index: CommandIndex) -> None:
    # Falls out of the extents rather than being arranged: a glyph is given its
    # line's extent exactly, so the two are visible or culled together. It
    # matters because the debug overlay draws a box per `Line`, and a glyph whose
    # header had been culled would sit outside any box.
    viewport = Viewport(top=sp_from_px(250.0), bottom=sp_from_px(640.0))
    kept = index.visible(viewport)
    assert any(isinstance(cmd, Glyph) for cmd in kept)
    seen: set[int] = set()
    for position, cmd in enumerate(kept):
        if isinstance(cmd, Line):
            seen.add(id(cmd))
        elif isinstance(cmd, Glyph):
            assert seen, f"a glyph at {position} of the culled list has no line before it"


def test_command_tops_never_go_backwards_through_a_document(index: CommandIndex) -> None:
    # A single continuous column, which is what `docs/decisions.md` scopes this
    # project to. The property is not relied on for correctness -- the cull is a
    # full scan -- but it is what would let the scan become a binary search, and
    # it is the first thing a second column would break.
    assert list(index.tops) == sorted(index.tops)


def test_the_bar_down_a_block_quote_is_kept_for_a_viewport_over_any_of_its_lines(
    index: CommandIndex,
) -> None:
    # A rule carries its own extent rather than its line's. The bar spans every
    # line of the quote, so scrolling into the middle of a quote must not leave
    # the quoted text without its bar -- which is what a rule inheriting the
    # extent of one line would do.
    bars = [
        (position, cmd)
        for position, cmd in enumerate(index.cmds)
        if isinstance(cmd, RuleRect) and cmd.height > 3 * cmd.width
    ]
    assert bars, "the sample no longer contains a block quote with a bar"
    position, bar = bars[0]
    assert extent_of(index, position) == (bar.y, bar.y + bar.height)
    middle = bar.y + bar.height // 2
    assert bar in index.visible(Viewport(top=middle - 1, bottom=middle + 1))


# -- a viewport from screen coordinates ----------------------------------


def test_a_viewport_in_pixels_becomes_one_in_document_scaled_points() -> None:
    viewport = Viewport.of_pixels(top_px=100.0, height_px=400.0)
    assert viewport.top == sp_from_px(100.0)
    assert viewport.bottom == sp_from_px(500.0)


def test_overscan_widens_a_viewport_at_both_ends() -> None:
    plain = Viewport.of_pixels(top_px=100.0, height_px=400.0)
    padded = Viewport.of_pixels(top_px=100.0, height_px=400.0, overscan_px=50.0)
    assert padded.top == plain.top - sp_from_px(50.0)
    assert padded.bottom == plain.bottom + sp_from_px(50.0)


def test_a_view_measures_its_viewport_from_the_documents_origin_not_from_zero() -> None:
    # The document is drawn at the cursor, which may sit well below the top of
    # its window. Reading a raw scroll offset would be wrong by exactly that
    # gap, so the conversion is a subtraction of two screen coordinates.
    view = DocumentView(
        document=build_document("x\n", Theme.build(), fontlib_metrics),
        theme=Theme.build(),
        measure=char_measure(fontlib_metrics),
    )
    # The window's top edge is 200px above where the document starts: the view
    # has scrolled 200px into it.
    viewport = view.viewport_in(origin_y_px=-200.0, window_y_px=0.0, window_height_px=600.0)
    assert viewport.top == sp_from_px(200.0)
    assert viewport.bottom == sp_from_px(800.0)


def test_a_document_that_has_not_scrolled_yet_gets_a_viewport_starting_above_it() -> None:
    # Unscrolled, with the document starting 40px below the window's top edge.
    # The band therefore starts at a negative document coordinate, which is
    # correct and is why `Viewport.top` is not clamped at zero.
    view = DocumentView(
        document=build_document("x\n", Theme.build(), fontlib_metrics),
        theme=Theme.build(),
        measure=char_measure(fontlib_metrics),
    )
    viewport = view.viewport_in(origin_y_px=40.0, window_y_px=0.0, window_height_px=600.0)
    assert viewport.top == sp_from_px(-40.0)


# -- selection is not culled ---------------------------------------------


def test_a_layout_indexes_every_command_even_though_only_some_are_drawn(
    bundled_fonts: Any,
) -> None:
    theme = Theme.build()
    view = DocumentView(
        document=build_document(SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    layout = view.layout_for(MEASURE)
    box = compose(view.document, theme, MEASURE, view.measure)
    whole = tuple(ship(box, Point(0, box.height), measure=view.measure))
    assert layout.cmds == whole
    assert layout.model.length == SelectionModel.from_commands(whole).length


def test_a_selection_running_past_the_bottom_of_the_window_still_copies_in_full(
    shipped: tuple[DrawCmd, ...],
) -> None:
    # The claim this file exists for. The selection spans from the first line to
    # the last, the window shows only the top of the document, and the copied
    # text is the whole range rather than the visible part of it.
    model = SelectionModel.from_commands(shipped)
    index = CommandIndex.of(shipped)
    window = Viewport(top=0, bottom=sp_from_px(200.0))
    visible = index.visible(window)
    assert len(visible) < len(shipped), "the window would have to be shorter to prove anything"

    everything = model.select(0, model.length)
    copied = model.text(everything)
    assert len(copied) > 0
    # And the same selection made against a model built only from what is on
    # screen would copy less, which is what culling earlier would have produced.
    truncated = SelectionModel.from_commands(visible)
    assert len(truncated.text(truncated.select(0, truncated.length))) < len(copied)


def test_culling_the_highlights_does_not_change_the_selection_they_came_from(
    shipped: tuple[DrawCmd, ...],
) -> None:
    model = SelectionModel.from_commands(shipped)
    everything = model.select(0, model.length)
    rects = model.rects(everything)
    window = Viewport(top=0, bottom=sp_from_px(200.0))
    drawn = visible_rects(rects, window)
    assert 0 < len(drawn) < len(rects)
    # The rects that survived are exactly the ones the window overlaps, and the
    # selection itself is untouched.
    assert list(drawn) == [rect for rect in rects if window.covers(rect.y, rect.y + rect.height)]
    assert model.rects(everything) == rects


def test_a_rect_entirely_below_a_window_is_not_drawn() -> None:
    window = Viewport(top=0, bottom=sp_from_px(100.0))
    below = Rect(x=0, y=sp_from_px(200.0), width=sp_from_px(50.0), height=sp_from_px(10.0))
    straddling = Rect(x=0, y=sp_from_px(90.0), width=sp_from_px(50.0), height=sp_from_px(30.0))
    assert visible_rects([below, straddling], window) == (straddling,)


# -- the view's caches ---------------------------------------------------


def test_invalidating_a_view_keeps_the_block_cache_it_can_still_use(bundled_fonts: Any) -> None:
    # `invalidate` drops the whole layout, which is what a caller who changed one
    # block has to do. Without a block cache underneath, recovering from a
    # one-block change re-breaks every block in the document.
    theme = Theme.build()
    view = DocumentView(
        document=build_document(SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    first = view.layout_for(MEASURE)
    filled = view._blocks.stats()
    shipped = view._units.stats()
    view.invalidate()
    second = view.layout_for(MEASURE)
    assert second is not first
    assert second.cmds == first.cmds
    # Nothing was re-broken, and not one new miss.
    #
    # This used to read "one *hit* per block looked up" on `_blocks`. Since
    # `advtext.ui.units` the shipped unit is found first and the block cache
    # underneath is not consulted for it at all, so the block cache records
    # neither a hit nor a miss and the hits are the unit cache's -- one per
    # unit, which is one per run of blocks rather than one per block. What the
    # test defends is unchanged: recovering from `invalidate` re-breaks nothing.
    after = view._blocks.stats()
    assert after.misses == filled.misses
    assert after.hits == filled.hits
    units = view._units.stats()
    assert units.misses == shipped.misses
    assert units.hits == shipped.hits + len(second.placed)


# -- through a real ImGui frame ------------------------------------------


def test_a_culled_command_list_draws_every_glyph_it_still_contains(
    shipped: tuple[DrawCmd, ...],
) -> None:
    """
    A culled list goes to the real backend unchanged and every glyph in it is issued.

    Executed in a real ImGui frame with no display, which `docs/decisions.md`
    records as possible and `tests/test_imgui_draw.py` established: a window needs
    a display and a frame does not. What this rules out is a culled list being
    subtly malformed -- a command whose enclosing line went missing, a count that
    does not match -- in a way no pure test would see.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    index = CommandIndex.of(shipped)
    window = Viewport.of_pixels(top_px=400.0, height_px=300.0)
    culled = index.visible(window)
    assert 0 < len(culled) < len(shipped)

    imgui.new_frame()
    try:
        drawn = draw(
            imgui.get_background_draw_list(),
            culled,
            imgui.ImVec2(0.0, 0.0),
            # No face, so the atlas is never touched: ImGui's four-argument
            # add_text draws in whatever is bound, which the backend documents
            # as a usable answer rather than an error.
            fonts=lambda face: None,
            palette=Palette(),
            px_per_inch=DEFAULT_PX_PER_INCH,
        )
    finally:
        imgui.render()

    assert drawn.glyphs == sum(1 for cmd in culled if isinstance(cmd, Glyph))
    assert drawn.missing == 0
    assert drawn.glyphs < sum(1 for cmd in shipped if isinstance(cmd, Glyph))


def test_no_module_indexes_an_array_valued_imgui_io_field() -> None:
    """
    Nothing may subscript a field of `get_io()`, because that needs numpy.

    The array-valued members of `ImGuiIO` -- `mouse_clicked_count`, `mouse_down`,
    `keys_down` -- are nanobind ndarrays. Exporting one requires numpy, which is
    a dependency of neither this project nor imgui-bundle, so indexing it raises
    `TypeError: could not export nanobind::ndarray` **on the first click**: not
    at import, not on the first frame, and therefore nowhere any other test in
    this tree can reach. ImGui publishes a scalar accessor for each of them and
    those need nothing.

    This is a source check and not a runtime one on purpose. The obvious test --
    assert the crash happens without numpy -- passes vacuously on any machine
    that has numpy installed, which is most of them, and would have read as
    protection while protecting nothing.

    Everything from the first `#` is dropped before matching, so the comment at
    the call site naming the pattern it avoids does not trip this. That also
    blanks a `#` inside a string literal, which can only ever make the check
    miss something, never invent one.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
        for path in sorted(ROOT.joinpath("advtext").rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"get_io\(\)\s*\.\s*\w+\s*\[", line.split("#", 1)[0])
    ]
    assert offenders == []


def test_the_scalar_click_count_accessor_works_in_a_frame_without_numpy() -> None:
    """
    The replacement for the ndarray field returns a plain int.

    Double- and triple-click granularity is the one selection behaviour that
    reads this, so if the accessor ever stops being scalar the granularity
    silently stops working rather than failing.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    imgui.new_frame()
    try:
        count = imgui.get_mouse_clicked_count(imgui.MouseButton_.left)
    finally:
        imgui.render()

    assert isinstance(count, int)
    assert _granularity_for(count) is Granularity.CHARACTER


def test_a_click_count_selects_the_granularity_a_user_expects() -> None:
    # One click is a caret, two is a word, three is a line, and anything beyond
    # keeps the line rather than falling back to a character.
    assert _granularity_for(1) is Granularity.CHARACTER
    assert _granularity_for(2) is Granularity.WORD
    assert _granularity_for(3) is Granularity.LINE
    assert _granularity_for(4) is Granularity.LINE


def test_culling_a_tall_document_leaves_a_small_fraction_of_its_commands(
    index: CommandIndex,
) -> None:
    # The reason any of this exists, as a structural claim rather than a timing.
    # Drawing is linear in the number of commands issued -- one add_text per
    # glyph, which `docs/decisions.md` records as forced by the advance
    # disagreement -- so a fraction of the commands is a fraction of the frame.
    tall = max(index.bottoms)
    assert px_from_sp(tall) > 1500.0, "the sample is no longer taller than a screen"
    window = Viewport.of_pixels(top_px=0.0, height_px=768.0)
    assert len(index.visible(window)) < len(index.cmds) // 2


# -- the page: margins, the measure, and the sheet -----------------------
#
# `page_for` is arithmetic over scaled points and needs no window at all, which
# is what lets the whole typographic argument be checked here rather than by
# looking at a screenshot. Where a claim really is visual -- whether the sheet
# is centred *on screen* -- the test is on the numbers `draw` feeds to ImGui and
# the screenshot is the second check, not the only one.

PAGE_LEADING = sp_from_px(21.0)
"""
A stand-in body leading for the tests that do not care what it is.

Distinct from every margin and every sheet width below, so a `page_for` that
confused `head` with `margin` could not pass by coincidence.
"""

PROSE = (
    "Typography exists to honour content. The typographer must analyse and "
    "reveal the inner order of the text, as a musician reveals the inner order "
    "of the music he performs. A book is a flexible mirror of the mind and the "
    "body, and its pages evoke two clear and conscious images, one visible and "
    "one invisible, that meet along the spine and turn with every leaf a reader "
    "lifts. The page is a landscape the eye crosses and recrosses, and the "
    "measure is the width of that crossing; make it too wide and the eye loses "
    "its place on the return, make it too narrow and the rhythm of the prose is "
    "chopped to pieces.\n"
)
"""
One paragraph of ordinary English, long enough to break into eight or more lines.

One paragraph and not several because `characters_per_line` drops the last line
it sees and nothing else: the last line of a paragraph is short by construction
and would drag any band downwards. With one paragraph there is exactly one such
line and dropping it is exact rather than approximate.

Real prose rather than repeated filler. The whole quantity under test is a
character *count*, and a fixture of `"word " * 100` would have one word length
and one space frequency and would agree with any measure at all.
"""


def characters_per_line(measure: Scaled, source: str = PROSE) -> list[int]:
    """
    Characters on each full line of `source` set to `measure`, last line dropped.

    Letters and spaces both, because that is what Bringhurst's 45-to-75 counts:
    a `Glyph` is a letter and a `SetGlue` inside a line is an interword space.
    Counting glyphs alone would report about 15 per cent low and would make a
    measure look better than it reads.
    """
    theme = Theme.build()
    measure_fn = char_measure(fontlib_metrics)
    box = compose(build_document(source, theme, fontlib_metrics), theme, measure, measure_fn)
    counts: list[int] = []
    for cmd in ship(box, Point(0, box.height), measure=measure_fn):
        if isinstance(cmd, Line):
            counts.append(0)
        elif isinstance(cmd, (Glyph, SetGlue)) and counts:
            counts[-1] += 1
    return counts[:-1]


def default_page(available_px: float) -> Page:
    """
    The page the default theme sets in a content region of this many pixels.
    """
    theme = Theme.build()
    return page_for(
        sp_from_px(available_px),
        alphabet=alphabet_length(theme, char_measure(fontlib_metrics)),
        leading=theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width,
    )


def test_the_measure_is_the_sheet_less_both_margins_and_not_one(bundled_fonts: Any) -> None:
    # The arithmetic a half-applied margin passes. Insetting only the left edge
    # still gives a measure narrower than the sheet and a text block that starts
    # inboard, so "narrower than the window" and "does not start at zero" are
    # both satisfied by the bug. What is not is the right edge: the gap from the
    # end of the text block to the end of the sheet has to equal the gap before
    # it, and under a one-margin implementation it is zero.
    page = default_page(1070.0)
    assert page.margin > 0
    assert page.measure == page.width - 2 * page.margin
    assert page.width - (page.margin + page.measure) == page.margin
    assert page.measure != page.width - page.margin


def test_the_sheet_is_centred_so_the_space_beside_it_is_equal(bundled_fonts: Any) -> None:
    available = sp_from_px(1600.0)
    page = default_page(1600.0)
    # A wide region, so there is space to get wrong: on a narrow one the offset
    # is zero and the assertion below holds for any implementation.
    assert page.offset > 0
    assert page.offset + page.width < available
    # Equal to within one scaled point, which is where an odd surplus goes. A
    # scaled point is 1/65536 of a point, so the tolerance is four orders of
    # magnitude below a pixel and cannot hide a real asymmetry -- a sheet pushed
    # to one side by even half a pixel is 32768 out.
    assert abs(available - (page.offset + page.width) - page.offset) <= 1


def test_a_window_wider_than_the_sheet_stops_widening_the_measure(bundled_fonts: Any) -> None:
    # The cap binds rather than merely existing: two content regions 1400px
    # apart produce byte-identical measures and sheets, and differ only in how
    # far in the sheet sits. A measure that still crept upward with the window
    # would fail the first assertion while passing any "narrower than the
    # window" check.
    near = default_page(1000.0)
    far = default_page(2400.0)
    assert near.width == far.width
    assert near.measure == far.measure
    assert far.offset > near.offset


def test_a_window_narrower_than_the_sheet_gives_the_sheet_the_whole_region(
    bundled_fonts: Any,
) -> None:
    available = sp_from_px(500.0)
    page = default_page(500.0)
    assert page.offset == 0
    assert page.width == available
    # And the margins are still taken out of it, so the text block shrinks with
    # the window instead of the page losing its proportions.
    assert page.measure < available
    assert page.measure == available - 2 * page.margin


def test_no_content_region_is_ever_set_edge_to_edge(bundled_fonts: Any) -> None:
    """
    The regression for the defect this was built for: a zero margin at any width.

    Swept rather than spot-checked, because the two regimes of `page_for` meet
    at a width nothing here would think to name, and a rounding that produced a
    zero margin would do it at one width and not its neighbour.
    """
    theme = Theme.build()
    alphabet = alphabet_length(theme, char_measure(fontlib_metrics))
    leading = theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
    pages = [
        (width, page_for(sp_from_px(float(width)), alphabet=alphabet, leading=leading))
        for width in range(int(MIN_WIDTH_PX), 4000, 7)
    ]
    for width, page in pages:
        assert page.margin > 0, f"no margin at a content region of {width}px"
        assert page.text_offset > 0, f"text starts at the left edge at {width}px"
        assert page.text_offset + page.measure < sp_from_px(
            float(width)
        ), f"text reaches the right edge at {width}px"
    # The sweep really did cross both regimes. Without this it could all be the
    # capped branch, and the uncapped one -- the one the old code behaved like --
    # would be untested while the loop above stayed green.
    assert any(page.offset == 0 for _, page in pages)
    assert any(page.offset > 0 for _, page in pages)


def test_the_sheet_is_taller_than_the_document_by_a_head_and_a_foot(bundled_fonts: Any) -> None:
    page = default_page(1070.0)
    body = sp_from_px(900.0)
    assert page.head == Theme.build().style(BlockKind.PARAGRAPH).interline.baselineskip.width
    assert page.head > 0
    assert page.sheet_height(body) == body + 2 * page.head
    # Both ends, for the same reason the measure subtracts both margins: a head
    # with no foot leaves the last descender on the edge of the paper.
    assert page.sheet_height(body) != body + page.head


def test_a_degenerate_measure_gives_the_whole_region_rather_than_a_sheet_of_nothing() -> None:
    # A `CharMeasure` that reports nothing -- a face that failed to load -- must
    # not produce a page of width zero, which is a blank window and looks like a
    # crash. Needs no fonts, which is why it takes no fixture.
    page = page_for(sp_from_px(1070.0), alphabet=0, leading=PAGE_LEADING)
    assert page.width == sp_from_px(1070.0)
    assert page.measure > 0


def test_the_alphabet_is_the_body_faces_own_and_moves_with_the_type(
    bundled_fonts: Any,
) -> None:
    # `alphabet_length` must read the theme rather than name a face and a size,
    # or the page stops tracking the type it is sizing. A theme built at 24px
    # body has an alphabet 1.5 times as long, and a hard-coded 16px one would
    # return the same number twice.
    measure = char_measure(fontlib_metrics)
    small = alphabet_length(Theme.build(base_px=16.0), measure)
    large = alphabet_length(Theme.build(base_px=24.0), measure)
    assert large / small == pytest.approx(1.5, abs=0.01)
    # And it is the *paragraph* face, not the heading one, which is set larger
    # still and would give a measure nobody reads a paragraph at.
    body = Theme.build().style(BlockKind.PARAGRAPH).font
    expected = sum(
        measure(CharNode(font=body.key, codepoint=ord(letter))).width
        for letter in "abcdefghijklmnopqrstuvwxyz"
    )
    assert small == expected


def test_the_measure_sets_lines_inside_the_character_band_the_constant_claims(
    bundled_fonts: Any,
) -> None:
    """
    Every full line of real prose at the page measure falls inside 45 to 75 characters.

    The claim `MEASURE_ALPHABETS` is chosen on, checked against lines the line
    breaker actually produced rather than against a mean advance. A mean would
    hide the spread, and the spread is the whole risk: justification lets a loose
    line carry several characters more than a tight one, and it is the loose line
    that leaves the band first.
    """
    counts = characters_per_line(default_page(1070.0).measure)
    assert len(counts) >= 6, "the fixture no longer breaks into enough lines to have a spread"
    assert min(counts) >= 45, f"lines too short: {counts}"
    assert max(counts) <= 75, f"lines too long: {counts}"


def test_the_character_band_is_not_a_band_everything_passes(bundled_fonts: Any) -> None:
    """
    The same count over the old behaviour and over the next coefficient up, both red.

    Without this the test above is one assertion away from vacuous: a counter
    that under-reported, or a band wide enough to admit anything, would pass it
    silently. Two cases that must *fail* the same band, one of them the exact
    layout this change replaced.
    """
    theme = Theme.build()
    alphabet = alphabet_length(theme, char_measure(fontlib_metrics))

    # What the demo did before the page existed: the measure is the content
    # region, all 1070px of it.
    unmargined = characters_per_line(sp_from_px(1070.0))
    assert min(unmargined) > 75, f"the old full-width measure was inside the band: {unmargined}"

    # And the reason the coefficient is 2.25 and not the 2.5 that reads as the
    # obvious choice: at 2.5 alphabets this face runs past the band's top.
    wider = characters_per_line(round(alphabet * 2.5))
    assert max(wider) > 75, f"2.5 alphabets stayed inside the band: {wider}"


def test_a_table_wider_than_the_measure_still_lands_inside_the_sheet(
    bundled_fonts: Any,
) -> None:
    """
    The cost of a narrow measure, bounded: a table overhangs the text but not the paper.

    A table's columns are as wide as their content and nothing reflows them, so a
    measure chosen for prose is a measure some tables exceed. That is accepted --
    `MEASURE_ALPHABETS` says so -- on the condition that the margin absorbs the
    overhang. This is the condition, at the demo width, against the real table in
    `demo/sample.md`.
    """
    theme = Theme.build()
    measure_fn = char_measure(fontlib_metrics)
    source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    page = default_page(1070.0)
    box = compose(build_document(source, theme, fontlib_metrics), theme, page.measure, measure_fn)
    overhang = max(
        cmd.x + getattr(cmd, "width", 0)
        for cmd in ship(box, Point(0, box.height), measure=measure_fn)
        if isinstance(cmd, (Glyph, RuleRect))
    )
    # It really does overhang, or this asserts nothing.
    assert overhang > page.measure, "nothing in the sample exceeds the measure any more"
    assert overhang <= page.measure + page.margin, "the table runs off the right edge of the sheet"


def test_a_view_composes_to_the_pages_measure_and_not_to_the_region_it_was_given(
    bundled_fonts: Any,
) -> None:
    # The seam between the two halves of this change. `page_for` can be perfect
    # and `draw` can still hand `layout_for` the raw content region, which is
    # exactly what it used to do; this is the assertion that says which number
    # reaches the line breaker.
    theme = Theme.build()
    view = DocumentView(
        document=build_document(SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    available = sp_from_px(1070.0)
    page = view.page(available)
    assert page.measure < available
    layout = view.layout_for(page.measure)
    assert layout.width == page.measure
    # And the composed box is that wide, so the measure was honoured rather than
    # merely recorded.
    assert layout.box.width == page.measure


def test_changing_a_views_theme_and_invalidating_moves_its_page(bundled_fonts: Any) -> None:
    # `DocumentView` memoises the alphabet, because measuring it is twenty-six
    # `CharMeasure` calls and `draw` runs sixty times a second. A memo that
    # outlived a theme swap would keep setting the new type to the old page's
    # measure, and the page would silently stop matching the document on it.
    small = Theme.build(base_px=16.0)
    view = DocumentView(
        document=build_document("x\n", small, fontlib_metrics),
        theme=small,
        measure=char_measure(fontlib_metrics),
    )
    available = sp_from_px(1600.0)
    before = view.page(available)
    view.theme = Theme.build(base_px=24.0)
    view.invalidate()
    after = view.page(available)
    assert after.measure > before.measure
    assert after.head > before.head
    # Not merely different: 24px type wants a page half again as wide as 16px
    # type, because every length on it is a multiple of an advance.
    assert after.measure / before.measure == pytest.approx(1.5, abs=0.02)


# -- the page, through a real ImGui frame --------------------------------


def _page_frame(
    view: DocumentView,
    *,
    mouse: tuple[float, float] | None = None,
    button: bool | None = None,
    nudge: tuple[float, float] | None = None,
    skip_draw: bool = False,
) -> Any:
    """
    One frame of `DocumentView.draw` inside a child window, with no display.

    `nudge` moves the cursor by that many pixels before the view is drawn, as
    a host laying out by hand might; `skip_draw` is a frame on which the
    view's tab is elsewhere.

    The same idiom as `test_a_culled_command_list_draws_every_glyph_it_still_contains`
    and for the same reason: a window needs a display and a frame does not. What
    it buys over calling `layout_for` directly is the part of this change that
    lives in `draw` -- which width reaches the line breaker, and which origin
    reaches hit testing -- neither of which any pure test can see.

    Returns the child's cursor position, which is the content region's top-left
    and the point every page coordinate is measured from. `fonts` is
    `lambda face: None` so the process-global font atlas is never touched.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1200.0, 800.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

    # Queued before `new_frame`, which is where ImGui drains the event queue. An
    # event added after it is not visible until the frame after, and a release
    # posted a frame late leaves the view still dragging.
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)

    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(1200.0, 800.0))
        imgui.begin("##advtext-page-test")
        imgui.begin_child("##advtext-page-child")
        cursor = imgui.get_cursor_screen_pos()
        # Read before the nudge and passed on, so that a nudge moves the
        # cursor and does not also change the width the page is worked out in.
        available = imgui.get_content_region_avail().x
        if nudge is not None:
            imgui.set_cursor_screen_pos(imgui.ImVec2(cursor.x + nudge[0], cursor.y + nudge[1]))
        if not skip_draw:
            view.draw(fonts=lambda face: None, width_px=available)
        imgui.end_child()
        imgui.end()
    finally:
        imgui.render()
    return cursor


HIT_SOURCE = (
    "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whisky "
    "xray yankee zulu again alpha bravo charlie delta echo foxtrot golf hotel.\n"
)
"""
Prose whose every word is distinct, so a selection says where it started.

Distinct words are the point: with `"word word word"` a selection taken a line
too low or a margin too far right would return the same string as a correct one
and the test would pass on a wrong origin.
"""


def test_draw_breaks_the_document_to_the_pages_measure_and_not_to_the_window(
    bundled_fonts: Any,
) -> None:
    """
    The width that reaches the line breaker is the page's, not the content region's.

    `page_for` can be correct in every particular and `draw` can still hand
    `layout_for` the raw `get_content_region_avail().x`, which is exactly what it
    did before this change. This is the assertion that distinguishes the two, and
    it has to run a frame because the content region only exists inside one.
    """
    theme = Theme.build()
    view = DocumentView(
        document=build_document(SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    _page_frame(view)
    layout = view._layout
    assert layout is not None
    available = sp_from_px(1184.0)
    page = view.page(available)
    assert layout.width == page.measure
    # And that is materially narrower than the region, so the assertion above is
    # not satisfiable by an implementation that ignores the page entirely.
    assert layout.width < available // 2


def test_a_click_at_the_text_blocks_corner_selects_the_first_word_not_a_later_one(
    bundled_fonts: Any,
) -> None:
    """
    Hit testing is offset by the margin and the head, or the mouse lands elsewhere.

    The failure this exists for is a half-applied origin: `draw` insets the glyphs
    by the margin and hands `_handle_mouse` the un-inset corner. The text then
    looks perfect and every click is wrong by exactly one margin -- 358 px here,
    most of a line -- and one head, which is one line down. Nothing but a
    coordinate that has been through both catches it.

    Pressing at the text block's own top-left corner therefore has to select from
    the very first word of the very first line. Under the un-inset origin the same
    press lands in the middle of the second line, and `HIT_SOURCE` has no repeated
    word to let that pass.
    """
    theme = Theme.build()
    view = DocumentView(
        document=build_document(HIT_SOURCE, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )
    # Two settling frames: the first sizes the child window, and `is_item_hovered`
    # needs a mouse position that was current when the item was submitted.
    cursor = _page_frame(view)
    page = view.page(sp_from_px(1184.0))
    layout = view.layout_for(page.measure)
    assert layout.height > 3 * page.head, "the fixture must break into several lines"

    left = cursor.x + px_from_sp(page.text_offset)
    top = cursor.y + px_from_sp(page.head)
    _page_frame(view, mouse=(left + 2.0, top + 6.0))
    _page_frame(view, mouse=(left + 2.0, top + 6.0), button=True)
    _page_frame(view, mouse=(left + 140.0, top + 6.0))
    _page_frame(view, mouse=(left + 140.0, top + 6.0), button=False)

    selected = view.selected_text()
    assert selected.startswith("Alpha bravo"), selected
    # Released, so no later test inherits a held button.
    assert not view._dragging


# -- two page views, and what a copy holds (2026-10-07) -----------------------


def _pages_frame(
    *views: DocumentView,
    mouse: tuple[float, float] | None = None,
    button: bool | None = None,
    ctrl_c: bool | None = None,
) -> None:
    """
    `_page_frame` for several views in one window, with Ctrl+C.

    Each view gets a child of its own height so that both are on screen; they
    are still items of one window's ID stack, which is the case under test.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1200.0, 800.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    if ctrl_c is not None:
        io.add_key_event(imgui.Key.mod_ctrl, ctrl_c)
        io.add_key_event(imgui.Key.c, ctrl_c)

    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(1200.0, 800.0))
        imgui.begin("##advtext-pages-test", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##advtext-pages-child")
        for view in views:
            view.draw(fonts=lambda face: None)
        imgui.end_child()
        imgui.end()
    finally:
        imgui.render()


def _page_of(source: str) -> DocumentView:
    theme = Theme.build()
    return DocumentView(
        document=build_document(source, theme, fontlib_metrics),
        theme=theme,
        measure=char_measure(fontlib_metrics),
    )


def test_two_page_views_in_one_window_are_two_items(bundled_fonts: Any) -> None:
    """
    A press on the second page selects in the second page.

    Both used the fixed label `##advtext-document`, so in one window they were
    one ImGui ID twice, and the plan's reviewer predicted the press would go to
    whichever was submitted first. **That did not reproduce**: this test passes
    against the fixed label too (run on 2026-10-07), because the view asks
    `is_item_hovered`, which ImGui answers from each item's own rectangle. So
    this pins the behaviour and is not evidence of a defect that was fixed.
    Each view labels its button with itself now all the same -- two visible
    items under one ID is something ImGui itself reports as a programmer error
    -- and `tests/test_bare_view.py` has the equivalent for the bare view.
    """
    first = _page_of("First page words here.\n")
    second = _page_of("Second page other text.\n")
    _pages_frame(first, second, mouse=(1190.0, 790.0), button=False)
    _pages_frame(first, second, mouse=(1190.0, 790.0))
    assert first.origin is not None and second.origin is not None
    assert second.origin[1] > first.origin[1]

    start = (second.origin[0] + 2.0, second.origin[1] + 6.0)
    _pages_frame(first, second, mouse=start)
    _pages_frame(first, second, mouse=start, button=True)
    assert second._dragging and not first._dragging
    _pages_frame(first, second, mouse=(start[0] + 90.0, start[1]))
    _pages_frame(first, second, mouse=(start[0] + 90.0, start[1]), button=False)
    assert second.selected_text().startswith("Second")
    assert first.selection.is_empty


def test_the_page_view_copies_a_code_block_with_its_lines_and_only_from_the_owner(
    bundled_fonts: Any,
) -> None:
    """
    The two copy defects of `docs/adoption-plan.md` phase 6, through the page view.

    `DocumentView` runs `BareView`'s `_handle_copy`, so the fixes are one fix;
    this is the check that the page view really is on the shared code.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    code = _page_of("```\nline one\nline two\n\nline four\n```\n")
    prose = _page_of("Some prose in the other view.\n")
    _pages_frame(code, prose, mouse=(1190.0, 790.0), button=False)
    _pages_frame(code, prose)
    prose.select_all()
    code.select_all()

    imgui.set_clipboard_text("SENTINEL")
    _pages_frame(code, prose, ctrl_c=True)
    _pages_frame(code, prose, ctrl_c=False)
    assert imgui.get_clipboard_text() == "line one\nline two\n\nline four"
    # The other view gave up its selection when this one took its turn.
    assert prose.selection.is_empty and code.owns_selection


# -- review 4: what the page view shares with the bare one (2026-10-07) --------


def test_a_fractional_cursor_gives_the_page_the_origin_a_whole_one_does(
    bundled_fonts: Any,
) -> None:
    """
    The page view snaps the cursor it is handed, and nothing else about its origin.

    `BareView._cursor_origin` has why a fractional origin matters. For the
    page the snap is of **the cursor**: the text block's corner is the cursor
    plus the page's offset, margin and head, which are not whole pixels and
    are left as they are, so that the demo's glyphs are where they were. So
    a cursor nudged by a fraction gives exactly the origin of the whole
    cursor it rounds to, and an un-nudged frame gives the origin it gave
    before any of this existed: the cursor plus the page geometry.
    """
    view = _page_of(HIT_SOURCE)
    cursor = _page_frame(view)
    cursor = _page_frame(view)
    page = view.page(sp_from_px(1184.0))
    plain = view.origin
    assert plain is not None
    assert plain == pytest.approx(
        (cursor.x + px_from_sp(page.text_offset), cursor.y + px_from_sp(page.head)), abs=1e-3
    )
    assert plain[1] != float(int(plain[1])), "fixture: the head is not a whole number of pixels"

    for nudge, whole in (
        ((0.25, 0.25), (0.0, 0.0)),
        ((0.3, -0.4), (0.0, 0.0)),
        ((0.5, 0.75), (1.0, 1.0)),
        ((-0.6, 1.2), (-1.0, 1.0)),
    ):
        _page_frame(view, nudge=nudge)
        assert view.origin == pytest.approx((plain[0] + whole[0], plain[1] + whole[1]), abs=1e-3)
    _page_frame(view)
    assert view.origin == pytest.approx(plain, abs=1e-3)


def test_the_page_view_does_not_resume_a_drag_across_a_frame_it_was_not_drawn(
    bundled_fonts: Any,
) -> None:
    # Review 4, item 3, for the view the demo uses: the same `_begin_frame`.
    # Release and a new press elsewhere, both while the page is not drawn; it
    # comes back with the button down and must not take that for its drag.
    view = _page_of(HIT_SOURCE)
    cursor = _page_frame(view)
    page = view.page(sp_from_px(1184.0))
    left = cursor.x + px_from_sp(page.text_offset)
    top = cursor.y + px_from_sp(page.head)
    _page_frame(view, mouse=(left + 2.0, top + 6.0))
    _page_frame(view, mouse=(left + 2.0, top + 6.0), button=True)
    _page_frame(view, mouse=(left + 60.0, top + 6.0))
    _page_frame(view, mouse=(left + 60.0, top + 6.0))
    held = view.selection
    assert view._dragging and view.selected_text().startswith("Alpha")

    _page_frame(view, button=False, skip_draw=True)
    _page_frame(view, mouse=(5.0, 5.0), button=True, skip_draw=True)
    _page_frame(view, mouse=(left + 300.0, top + 50.0))
    assert not view._dragging
    _page_frame(view, mouse=(left + 300.0, top + 50.0))
    assert view.selection == held
    _page_frame(view, button=False)

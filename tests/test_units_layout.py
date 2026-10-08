r"""
Per-unit layout must be indistinguishable from whole-document layout, and cheaper.

`advtext.ui.units` ships each independent run of blocks on its own and stacks
the results by offset. Two claims ride on that and this file is the evidence
for both.

**The first is equality.** A `UnitLayout` has to give the same draw commands,
the same reading-order indices and the same answer to every selection query as
composing the whole document into one box, shipping it and indexing it flat --
which is what `DocumentView.layout_for` did before. Every test in the first
half builds both and compares them, on `demo/sample.md` (the document the demo
draws) and on a document with one of every block kind including a quote whose
bar spans several paragraphs. Nothing here asserts a number that was worked
out by hand: the flat pipeline is the oracle, so these would go red if the
stacking arithmetic were off by a single scaled point or a single index.

**The second is that an unchanged unit is not shipped again.** That is a claim
about work, so it is asserted by counting calls to `ship` and reading
`UnitCache`'s counters, not by timing.

What is *not* tested here: the draw backend. `advtext.backends.imgui_draw.draw`
is a function of the command list it is handed, so equal lists are equal
pixels, and `tests/test_imgui_draw.py` is where that function is exercised.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import pytest

from advtext.markdown import (
    Block,
    CodeBlock,
    Document,
    TableBlock,
    TextBlock,
    build_document,
    text_block,
)
from advtext.selection import Selection, SelectionModel
from advtext.shipout import DrawCmd, Glyph, Line, Point, RuleRect, SetGlue, ship
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import CommandIndex, LayoutCache, Viewport, block_runs, compose
from advtext.ui import units as units_module
from advtext.ui.document_view import DocumentView
from advtext.ui.units import UnitCache, UnitLayout, layout_units, moved
from advtext.units import Scaled, sp_from_pt, sp_from_px

ROOT = Path(__file__).resolve().parent.parent

EVERY_KIND = (
    "# A heading\n\n"
    "One two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty.\n\n"
    "> A quoted paragraph long enough to break over several lines, so that the\n"
    "> bar down its left edge spans more than one of them.\n"
    ">\n"
    "> A second paragraph of the same quote, which is the same unit as the\n"
    "> first because one bar runs down both.\n\n"
    "- first item\n- second item\n\n"
    "1. numbered\n2. also numbered\n\n"
    "| a | bb |\n|---|---|\n| 1 | 2 |\n\n"
    "---\n\n"
    "Another paragraph, so that there is material below the table and the rule.\n\n"
    "```\nfenced code\n\nwith a blank line in it\n```\n\n"
    "## A second heading\n\n"
    "And a last paragraph with *emphasis* and `code` in it.\n"
)
"""
One of every block kind, with a two-paragraph quote and a code block holding a blank line.

The quote is what makes a unit differ from a block; the blank line is the one
fragment that owns no item, which is the case `text()` and `fragments_within`
have to agree about at a unit boundary.
"""

MEASURES = (sp_from_pt(300.0), sp_from_pt(420.0), sp_from_px(467.0))
"""
A narrow measure, the litmus measure, and roughly the demo page's 2.25 alphabets.
"""


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure(bundled_fonts: Any) -> Any:
    """
    One `CharMeasure`, held for the module: the caches key it by identity.
    """
    return char_measure(fontlib_metrics)


@pytest.fixture(scope="module", params=["sample", "every-kind"])
def document(request: pytest.FixtureRequest, theme: Theme, bundled_fonts: Any) -> Document:
    if request.param == "sample":
        source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    else:
        source = EVERY_KIND
    return build_document(source, theme, fontlib_metrics)


def flat(document: Document, theme: Theme, width: Scaled, measure: Any) -> tuple[DrawCmd, ...]:
    """
    The whole-document pipeline `DocumentView.layout_for` used before units: the oracle.
    """
    box = compose(document, theme, width, measure)
    return tuple(ship(box, Point(0, box.height), measure=measure))


# -- equality with the whole-document pipeline ---------------------------


@pytest.mark.parametrize("width", MEASURES)
def test_stacked_units_ship_the_same_commands_as_the_whole_document(
    document: Document, theme: Theme, measure: Any, width: Scaled
) -> None:
    # The gate. Same commands, in the same order, at the same scaled-point
    # coordinates and with the same reading-order indices.
    expected = flat(document, theme, width, measure)
    layout = layout_units(document.blocks, theme, width, measure)
    assert len(layout.placed) > 1, "one unit would make stacking vacuous"
    assert layout.cmds == expected


@pytest.mark.parametrize("width", MEASURES)
def test_a_unit_layout_has_the_whole_documents_extent_and_item_count(
    document: Document, theme: Theme, measure: Any, width: Scaled
) -> None:
    box = compose(document, theme, width, measure)
    layout = layout_units(document.blocks, theme, width, measure)
    assert layout.height == box.height + box.depth
    assert (
        layout.length == SelectionModel.from_commands(flat(document, theme, width, measure)).length
    )
    assert (layout.box.width, layout.box.height + layout.box.depth) == (
        box.width,
        box.height + box.depth,
    )
    # And the assembled box is a real one: it ships to the same commands.
    assert tuple(ship(layout.box, Point(0, layout.box.height), measure=measure)) == layout.cmds


def test_units_tile_the_index_space_and_never_overlap_vertically(
    document: Document, theme: Theme, measure: Any
) -> None:
    layout = layout_units(document.blocks, theme, MEASURES[0], measure)
    base = 0
    bottom = 0
    block = 0
    for unit in layout.placed:
        assert unit.base == base
        assert unit.y >= bottom
        assert unit.block_start == block
        assert list(unit.index_range) == list(range(base, base + unit.unit.count))
        base += unit.unit.count
        bottom = unit.bottom
        block += len(unit.blocks)
    assert base == layout.length
    assert block == len(document.blocks)
    assert [unit.blocks for unit in layout.placed] == block_runs(document.blocks)


@pytest.mark.parametrize("width", MEASURES[:2])
def test_culling_by_unit_keeps_exactly_what_culling_by_command_kept(
    document: Document, theme: Theme, measure: Any, width: Scaled
) -> None:
    # `CommandIndex.visible` over the flat list is what the draw call used to
    # be handed. A window sliding down the document in steps that are not a
    # multiple of any leading crosses unit boundaries, line boundaries and the
    # middle of a quote bar.
    index = CommandIndex.of(flat(document, theme, width, measure))
    layout = layout_units(document.blocks, theme, width, measure)
    step = sp_from_px(37.0)
    tall = sp_from_px(240.0)
    seen = 0
    for top in range(-2 * step, layout.height + 2 * step, step):
        for window in (Viewport(top, top + tall), Viewport(top, top + 1), Viewport(top, top)):
            expected = index.visible(window)
            assert layout.visible(window) == expected
            seen += len(expected)
    assert seen > len(index.cmds), "the sweep has to see the document, not miss it"
    everything = Viewport(-1, layout.height + 1)
    assert layout.visible(everything) == index.cmds


def test_every_point_query_agrees_with_the_flat_selection_model(
    document: Document, theme: Theme, measure: Any
) -> None:
    width = MEASURES[0]
    oracle = SelectionModel.from_commands(flat(document, theme, width, measure))
    model = layout_units(document.blocks, theme, width, measure).model
    assert model.length == oracle.length

    # A grid that runs off every edge of the document: above it, below it, in
    # the gaps between units, left of the margin and right of it.
    xs = [sp_from_px(x) for x in (-20.0, 0.0, 3.0, 61.5, 140.0, 399.0, 900.0)]
    height = max(fragment.bottom for fragment in oracle.fragments)
    checked = 0
    for y in range(-sp_from_px(30.0), height + sp_from_px(30.0), sp_from_px(5.3)):
        for x in xs:
            point = Point(x, y)
            assert model.fragment_at(point) == oracle.fragment_at(point), point
            assert model.hit(point) == oracle.hit(point)
            assert model.word_at(point) == oracle.word_at(point)
            assert model.line_at(point) == oracle.line_at(point)
            checked += 1
    assert checked > 500


def test_every_range_query_agrees_with_the_flat_selection_model(
    document: Document, theme: Theme, measure: Any
) -> None:
    # Selection indices are continuous across units: a range that starts in
    # one and ends in another gives the rects and the text the flat model
    # gives, including the space or newline at each unit boundary.
    width = MEASURES[0]
    oracle = SelectionModel.from_commands(flat(document, theme, width, measure))
    layout = layout_units(document.blocks, theme, width, measure)
    model = layout.model
    boundaries = {0, 1, model.length - 1, model.length}
    for unit in layout.placed:
        boundaries.update(
            (unit.base - 1, unit.base, unit.base + 1, unit.base + unit.unit.count // 2)
        )
    edges = sorted(b for b in boundaries if 0 <= b <= model.length)
    compared = 0
    for position, start in enumerate(edges):
        for end in edges[position :: max(1, len(edges) // 12)]:
            selection = Selection(start, end)
            assert model.rects(selection) == oracle.rects(selection), selection
            assert model.text(selection) == oracle.text(selection), selection
            compared += 1
    assert compared > 100
    everything = Selection(0, model.length)
    assert model.text(everything) == oracle.text(everything)
    assert model.text(everything, hard_breaks=range(0, model.length, 7)) == oracle.text(
        everything, hard_breaks=range(0, model.length, 7)
    )
    assert model.select(model.length + 50, -3) == oracle.select(model.length + 50, -3)


def test_the_flat_fragment_list_is_still_available_and_is_the_flat_models(
    document: Document, theme: Theme, measure: Any
) -> None:
    width = MEASURES[1]
    oracle = SelectionModel.from_commands(flat(document, theme, width, measure))
    assert layout_units(document.blocks, theme, width, measure).model.fragments == oracle.fragments


def test_a_view_draws_the_demo_document_from_the_same_commands_as_before(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # The view's own path, at the measure its own page sets in the 1100 px demo
    # window, against the pipeline `layout_for` used to run inline.
    source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    view = DocumentView(
        document=build_document(source, theme, fontlib_metrics), theme=theme, measure=measure
    )
    page = view.page(sp_from_px(1070.0))
    layout = view.layout_for(page.measure)
    expected = flat(view.document, theme, page.measure, measure)
    assert layout.cmds == expected
    window = Viewport.of_pixels(top_px=400.0, height_px=768.0)
    assert layout.visible(window) == CommandIndex.of(expected).visible(window)


# -- the block hit test --------------------------------------------------


def test_a_point_on_any_line_resolves_to_the_block_that_set_it(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Each block is laid out alone to learn how many lines it has; the lines
    # of the stacked document are then walked in order and every one must
    # resolve to the block that the count says owns it.
    document = build_document(EVERY_KIND, theme, fontlib_metrics)
    width = MEASURES[0]
    layout = layout_units(document.blocks, theme, width, measure)
    quoted = [unit for unit in layout.placed if len(unit.blocks) > 1]
    assert quoted, "the fixture needs a unit of more than one block"

    owners: list[int] = []
    first_index = 0
    for number, block in enumerate(document.blocks):
        alone = layout_units((block,), theme, width, measure)
        owners.extend([number] * len(alone.model.fragments))
        # And the block's share of the reading order is what it has alone,
        # starting where the blocks before it stopped -- inside a quote too.
        unit = layout.unit_of_block(number)
        assert unit is not None
        assert unit.indices_of(number) == range(first_index, first_index + alone.length)
        first_index += alone.length
    assert first_index == layout.length
    fragments = layout.model.fragments
    assert len(owners) == len(fragments)
    for owner, fragment in zip(owners, fragments, strict=True):
        middle = Point(fragment.line.x, (fragment.top + fragment.bottom) // 2)
        assert layout.block_at(middle) == owner
        unit = layout.unit_at(middle)
        assert unit is not None and owner in unit.block_range
        assert layout.unit_of_block(owner) is unit
        if fragment.indices:
            assert layout.unit_of(fragment.indices[0]) is unit


def test_a_point_between_two_units_or_outside_the_document_is_in_no_block(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document(EVERY_KIND, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, MEASURES[0], measure)
    first, second = layout.placed[0], layout.placed[1]
    assert second.y > first.bottom, "the heading must have space below it"
    assert layout.block_at(Point(0, (first.bottom + second.y) // 2)) is None
    assert layout.unit_at(Point(0, -1)) is None
    assert layout.unit_at(Point(0, layout.height)) is None
    assert layout.unit_at(Point(0, layout.height - 1)) is layout.placed[-1]
    assert layout.unit_of(layout.length) is None
    assert layout.unit_of(-1) is None
    # Far to the right of the measure is still beside the first block.
    assert layout.block_at(Point(sp_from_px(5000.0), first.y)) == 0


def test_the_blocks_of_a_quote_have_extents_inside_their_unit_and_in_order(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document(EVERY_KIND, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, MEASURES[0], measure)
    for unit in layout.placed:
        extents = unit.unit.extents
        assert len(extents) == len(unit.blocks)
        if len(extents) == 1:
            assert extents == ((0, unit.height),)
            continue
        assert extents[0][0] == 0 and extents[-1][1] == unit.height
        for (_, bottom), (top, _) in zip(extents, extents[1:], strict=False):
            # Paragraphs of a quote are separated by the block gap, which
            # belongs to neither.
            assert top > bottom


# -- what is and is not redone -------------------------------------------


class _Counted:
    """
    `ship`, counting its calls, so "not re-shipped" is a number.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> list[DrawCmd]:
        self.calls += 1
        return ship(*args, **kwargs)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> _Counted:
    counter = _Counted()
    monkeypatch.setattr(units_module, "ship", counter)
    return counter


def edited(document: Document, number: int, theme: Theme) -> Document:
    """
    `document` with block `number` replaced by a different paragraph, others untouched.

    The other blocks are the *same objects*, which is what a host that edits
    one block of a document it holds would pass.
    """
    (changed,) = build_document(
        "A replacement paragraph with different words in it.\n", theme, fontlib_metrics
    ).blocks
    blocks = list(document.blocks)
    assert isinstance(blocks[number], TextBlock)
    blocks[number] = changed
    return Document(blocks=tuple(blocks))


def first_paragraph(document: Document) -> int:
    return next(
        number
        for number, block in enumerate(document.blocks)
        if isinstance(block, TextBlock) and not block.quote_depth and number > 0
    )


def test_an_unchanged_document_is_not_shipped_composed_or_hashed_again(
    document: Document, theme: Theme, measure: Any, counted: _Counted
) -> None:
    units, cache = UnitCache(), LayoutCache()
    first = layout_units(document.blocks, theme, MEASURES[0], measure, units=units, cache=cache)
    shipped, broken = counted.calls, cache.stats()
    assert shipped == units.stats().misses > 0

    second = layout_units(
        document.blocks, theme, MEASURES[0], measure, units=units, cache=cache, previous=first
    )
    assert counted.calls == shipped
    assert cache.stats() == broken, "the block cache underneath was not even consulted"
    assert units.stats().misses == shipped
    assert units.stats().hits == len(first.placed) + (len(first.placed) - shipped)
    # And the placements are the same objects, so nothing was moved again either.
    assert all(
        new._placement is old._placement
        for new, old in zip(second.placed, first.placed, strict=True)
    )


def test_editing_one_block_ships_one_unit(
    document: Document, theme: Theme, measure: Any, counted: _Counted
) -> None:
    units = UnitCache()
    width = MEASURES[0]
    first = layout_units(document.blocks, theme, width, measure, units=units)
    before = counted.calls
    number = first_paragraph(document)
    changed = edited(document, number, theme)

    second = layout_units(changed.blocks, theme, width, measure, units=units, previous=first)
    assert counted.calls == before + 1
    assert units.stats().misses == before + 1
    # Still the whole-document answer, for the document as it now is.
    assert second.cmds == flat(changed, theme, width, measure)
    # Everything above the edit kept its placement outright.
    position = next(p for p, unit in enumerate(second.placed) if number in unit.block_range)
    assert position > 0
    assert all(second.placed[p]._placement is first.placed[p]._placement for p in range(position))
    # The replaced unit is retired after one further pass that does not use it.
    resident = units.stats().entries
    layout_units(changed.blocks, theme, width, measure, units=units, previous=second)
    assert units.stats().entries == resident - 1
    assert counted.calls == before + 1


def test_an_edit_that_keeps_a_blocks_size_moves_nothing_below_it(
    theme: Theme, measure: Any, bundled_fonts: Any, counted: _Counted
) -> None:
    # One letter swapped for another of the same class in a one-line paragraph:
    # same height, same item count. Every unit below keeps its placement, so
    # its moved commands and its selection index are not derived again.
    source = "# Title\n\nAlpha bravo.\n\nCharlie delta echo.\n\n- one\n- two\n"
    before = build_document(source, theme, fontlib_metrics)
    after = build_document(source.replace("bravo", "brave"), theme, fontlib_metrics)
    units = UnitCache()
    width = MEASURES[0]
    first = layout_units(before.blocks, theme, width, measure, units=units)
    assert first.cmds  # place every unit, so there is something to keep
    index = first.placed[-1].model
    shipped = counted.calls

    second = layout_units(after.blocks, theme, width, measure, units=units, previous=first)
    # `after` is a fresh parse, so every block is a new object. Only the one
    # whose *value* changed is shipped.
    assert counted.calls == shipped + 1
    assert second.height == first.height and second.length == first.length
    kept = [
        new._placement is old._placement
        for new, old in zip(second.placed, first.placed, strict=True)
    ]
    assert kept == [True, False, True, True, True]
    assert second.placed[-1].model is index
    assert second.cmds == flat(after, theme, width, measure)


def test_a_reparsed_document_is_found_by_value_once_and_by_identity_after(
    theme: Theme, measure: Any, bundled_fonts: Any, counted: _Counted
) -> None:
    units = UnitCache()
    width = MEASURES[0]
    original = build_document(EVERY_KIND, theme, fontlib_metrics)
    first = layout_units(original.blocks, theme, width, measure, units=units)
    shipped = counted.calls

    again = build_document(EVERY_KIND, theme, fontlib_metrics)
    assert again.blocks == original.blocks and again.blocks[0] is not original.blocks[0]
    second = layout_units(again.blocks, theme, width, measure, units=units, previous=first)
    assert counted.calls == shipped
    assert second.cmds == first.cmds
    # The units were re-homed on the new objects...
    assert all(
        mine is theirs
        for unit in second.placed
        for mine, theirs in zip(unit.blocks, again.blocks[unit.block_start :], strict=False)
    )
    # ...and still share the placements, because the shipped commands are the same tuple.
    assert all(
        new._placement is old._placement
        for new, old in zip(second.placed, first.placed, strict=True)
    )


def test_two_equal_blocks_in_one_document_share_one_shipped_unit(
    theme: Theme, measure: Any, bundled_fonts: Any, counted: _Counted
) -> None:
    document = build_document(
        "Same words.\n\nSame words.\n\nOther words.\n", theme, fontlib_metrics
    )
    units = UnitCache()
    layout = layout_units(document.blocks, theme, MEASURES[0], measure, units=units)
    assert counted.calls == 2
    a, b, _ = layout.placed
    assert a.unit.cmds is b.unit.cmds
    # One unit, two places: the second is the first moved down and renumbered.
    assert b.cmds == moved(a.unit.cmds, b.y, b.base)
    assert layout.cmds == flat(document, theme, MEASURES[0], measure)
    # A second pass finds both by identity, and nothing is shipped.
    layout_units(document.blocks, theme, MEASURES[0], measure, units=units, previous=layout)
    assert counted.calls == 2


def test_a_unit_cache_never_returns_another_widths_or_another_themes_units(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document(EVERY_KIND, theme, fontlib_metrics)
    units = UnitCache()
    larger = Theme.build(base_px=20.0)
    bigger = build_document(EVERY_KIND, larger, fontlib_metrics)
    for _ in range(2):
        for width in MEASURES[:2]:
            layout = layout_units(document.blocks, theme, width, measure, units=units)
            assert layout.cmds == flat(document, theme, width, measure)
    assert units.stats().hits > 0
    # The same *blocks* under a different theme object is a different pass key.
    layout = layout_units(bigger.blocks, larger, MEASURES[0], measure, units=units)
    assert layout.cmds == flat(bigger, larger, MEASURES[0], measure)


def test_a_unit_cache_holds_a_bounded_number_of_widths(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document("One.\n\nTwo.\n", theme, fontlib_metrics)
    units = UnitCache()
    for extra in range(40):
        layout_units(document.blocks, theme, MEASURES[0] + extra, measure, units=units)
    # A resize drag: every width misses, and only the last two are resident.
    assert units.stats().hits == 0
    assert units.stats().entries == 2 * len(document.blocks)
    with pytest.raises(ValueError):
        UnitCache(resident_passes=0)


def test_an_offscreen_unit_is_never_moved_or_indexed(
    document: Document, theme: Theme, measure: Any
) -> None:
    # Placement is lazy. Drawing the top of the document and clicking in it
    # derives the moved commands and the selection index of the units involved
    # and of no other.
    layout = layout_units(document.blocks, theme, MEASURES[0], measure)
    window = Viewport(0, layout.placed[2].bottom)
    assert layout.visible(window)
    layout.model.hit(Point(0, layout.placed[1].y + 1))
    moved_units = [unit._placement._cmds is not None for unit in layout.placed]
    indexed = [unit._placement._model is not None for unit in layout.placed]
    assert moved_units[:3] == [True, True, True]
    assert not any(moved_units[4:])
    assert sum(indexed) <= 3 and not any(indexed[4:])


def test_moving_a_command_knows_every_field_it_has() -> None:
    # `moved` rebuilds each command field by field, for speed. A field added to
    # one of these in `advtext.shipout` would be dropped silently, so the field
    # lists are pinned here and adding one fails this test by name.
    assert [f.name for f in fields(Glyph)] == ["font", "codepoint", "x", "y", "index"]
    assert [f.name for f in fields(SetGlue)] == [
        "x",
        "y",
        "width",
        "natural",
        "height",
        "depth",
        "index",
    ]
    assert [f.name for f in fields(Line)] == ["x", "y", "width", "height", "depth", "start", "end"]
    assert [f.name for f in fields(RuleRect)] == ["x", "y", "width", "height"]
    cmds: tuple[DrawCmd, ...] = (
        Line(x=1, y=10, width=50, height=8, depth=2, start=0, end=2),
        Glyph(font="f", codepoint=65, x=1, y=10, index=0),
        SetGlue(x=9, y=10, width=4, natural=3, height=8, depth=2, index=1),
        RuleRect(x=0, y=20, width=50, height=1),
    )
    assert moved(cmds, 100, 7) == (
        replace(cmds[0], y=110, start=7, end=9),
        replace(cmds[1], y=110, index=7),
        replace(cmds[2], y=110, index=8),
        replace(cmds[3], y=120),
    )


def test_a_view_that_changed_one_block_reships_one_block(
    theme: Theme, measure: Any, bundled_fonts: Any, counted: _Counted
) -> None:
    # The same claim through `DocumentView`, which is where a host meets it:
    # swap the document, `invalidate`, and ask for the layout again.
    source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
    document = build_document(source, theme, fontlib_metrics)
    view = DocumentView(document=document, theme=theme, measure=measure)
    width = MEASURES[1]
    first = view.layout_for(width)
    everything = counted.calls
    assert everything == len({unit.unit.cmds for unit in first.placed})

    view._selection = first.model.select(3, first.length - 3)
    selected = view.selected_text()
    number = first_paragraph(document)
    view.document = edited(document, number, theme)
    view.invalidate()
    second = view.layout_for(width)
    assert isinstance(second, UnitLayout)
    assert counted.calls == everything + 1
    assert second.cmds == flat(view.document, theme, width, measure)
    # The selection is boundaries, so it survives as the same range of a
    # document that is now a different length; it is still serialisable.
    assert view.selected_text() != selected
    assert view.selected_text() == second.model.copy_text(view.selection)
    assert second.model.text(view.selection) == SelectionModel.from_commands(second.cmds).text(
        view.selection
    )


def test_block_runs_gathers_a_quote_into_one_run_and_nothing_else(
    theme: Theme, bundled_fonts: Any
) -> None:
    document = build_document(EVERY_KIND, theme, fontlib_metrics)
    runs = block_runs(document.blocks)
    flattened: list[Block] = [block for run in runs for block in run]
    assert tuple(flattened) == document.blocks
    for run in runs:
        if len(run) > 1:
            assert all(isinstance(block, TextBlock) and block.quote_depth for block in run)
    assert sum(len(run) > 1 for run in runs) == 1


NESTED_QUOTES = (
    "Before the quote.\n\n"
    "> An outer paragraph, long enough to break over more than one line at the\n"
    "> narrow measure so that its share of the index space is not one line's.\n"
    ">\n"
    "> > An inner paragraph, two bars deep, also long enough that it has to\n"
    "> > break and so has a line that starts with a bar and nothing else.\n"
    "> >\n"
    "> > A second inner paragraph.\n"
    ">\n"
    "> - an item inside the outer quote, long enough to wrap under its marker\n"
    ">   at the narrow measure\n"
    "> - a second item\n"
    ">\n"
    "> Back out to one bar.\n\n"
    "After the quote.\n"
)
"""
Depth 1, depth 2, a list inside the quote, depth 1 again, then out.

`EVERY_KIND`'s quote is two paragraphs at one depth, which is the only shape
`_spans` had been run on. Here the bars a block's lines carry change count from
block to block inside one unit, and one block brings a marker with it.
"""


@pytest.mark.parametrize("width", MEASURES)
def test_every_block_of_a_nested_quote_has_the_indices_it_has_alone(
    theme: Theme, measure: Any, bundled_fonts: Any, width: Scaled
) -> None:
    """
    `indices_of` inside a multi-block unit: each block's own count, consecutive.

    A block's share of the reading order is how many items it sets, and laying
    the block out alone is an independent way to count them -- alone it is its
    own unit and `_spans` has nothing to divide. So every block of the nested
    quote must own, in the stacked document, a range as long as its length
    alone, starting where the block before it stopped. The whole document is
    also held to the flat pipeline, so the ranges are ranges of the right thing.

    The preconditions are asserted because the test is about a shape of
    document, and a converter that flattened it would leave this passing on a
    document that no longer has the shape.
    """
    document = build_document(NESTED_QUOTES, theme, fontlib_metrics)
    depths = [block.quote_depth for block in document.blocks if isinstance(block, TextBlock)]
    assert len(depths) == len(document.blocks), "the fixture is text blocks only"
    assert depths == [0, 1, 2, 2, 1, 1, 1, 0], "depth 1, 2, a list at 1, back to 1, then out"

    layout = layout_units(document.blocks, theme, width, measure)
    assert layout.cmds == flat(document, theme, width, measure)
    quote = layout.unit_of_block(1)
    assert quote is not None and quote.block_range == range(1, 7), "one bar, one unit"

    first_index = 0
    for number, block in enumerate(document.blocks):
        alone = layout_units((block,), theme, width, measure)
        assert alone.length > 0, "a block that sets nothing would make its range say nothing"
        unit = layout.unit_of_block(number)
        assert unit is not None
        assert unit.indices_of(number) == range(first_index, first_index + alone.length), number
        first_index += alone.length
    assert first_index == layout.length
    assert quote.index_range == range(quote.indices_of(1).start, quote.indices_of(6).stop)


# -- what a copy reads as ----------------------------------------------------

COPIED = (
    "# Title\n"
    "\n"
    "First paragraph that is long enough to wrap onto a second line at the narrow width for sure.\n"
    "\n"
    "A line with a hard break here\\\n"
    "and the rest.\n"
    "\n"
    "- one\n"
    "- two with enough words to wrap around onto another line of the item\n"
    "\n"
    "1. first\n"
    "2. second\n"
    "\n"
    "> quoted one\n"
    ">\n"
    "> quoted two\n"
    "\n"
    "```\n"
    "def f(x):\n"
    "    return x\n"
    "\n"
    "print(f(1))\n"
    "```\n"
    "\n"
    "---\n"
    "\n"
    "| k | v | w |\n"
    "|---|:-:|--:|\n"
    "| one | alpha bravo charlie delta echo foxtrot | x |\n"
    "| two |  | y |\n"
    "\n"
    "Last.\n"
)

AS_COPIED = (
    "Title\n"
    "\n"
    "First paragraph that is long enough to wrap onto a second line at the narrow width for sure.\n"
    "\n"
    "A line with a hard break here\n"
    "and the rest.\n"
    "\n"
    "\u2022 one\n"
    "\u2022 two with enough words to wrap around onto another line of the item\n"
    "\n"
    "1. first\n"
    "2. second\n"
    "\n"
    "quoted one\n"
    "\n"
    "quoted two\n"
    "\n"
    "def f(x):\n"
    "    return x\n"
    "\n"
    "print(f(1))\n"
    "\n"
    "k\tv\tw\n"
    "one\talpha bravo charlie delta echo foxtrot\tx\n"
    "two\t\ty\n"
    "\n"
    "Last."
)
"""
`COPIED` as a copy of the whole of it reads, at any measure.

Every structural decision is in this one string: a blank line between blocks
and between two different lists, one newline between the items of a list and
between code lines (and two around the blank one), a newline at a hard break,
a list marker followed by one space, tabs between cells with an empty cell
keeping its tab, and nothing at all for the rule.
"""


@pytest.mark.parametrize("width_px", [300.0, 520.0, 1400.0])
def test_a_copy_of_a_whole_document_reads_as_its_structure_at_any_measure(
    theme: Theme, measure: Any, bundled_fonts: Any, width_px: float
) -> None:
    # 300 px wraps the paragraph, the list item and the table's cells; 1400 px
    # wraps nothing. The string is the same, which is the point of taking the
    # structure from the blocks and not from where the lines happened to end.
    document = build_document(COPIED, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, sp_from_px(width_px), measure)
    everything = Selection(0, layout.length)
    assert layout.model.copy_text(everything) == AS_COPIED
    if width_px == 300.0:
        assert len(layout.model.fragments) > 20, "nothing wrapped; the claim would be empty"

    # `text` is untouched by any of that: it is still the flat model's answer.
    box = compose(document, theme, sp_from_px(width_px), measure)
    oracle = SelectionModel.from_commands(ship(box, Point(0, box.height), measure=measure))
    assert layout.model.text(everything) == oracle.text(everything)
    assert "\t" not in oracle.text(everything)


def test_a_copy_that_starts_or_ends_inside_a_block_takes_no_separator_it_did_not_cross(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document(COPIED, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, sp_from_px(300.0), measure)
    model = layout.model
    whole = model.copy_text(Selection(0, layout.length))
    table = next(
        unit
        for unit in layout.placed
        if "one\talpha" in model.copy_text(Selection(unit.base, unit.base + unit.unit.count))
    )
    # The table alone: no blank line before it, none after.
    assert model.copy_text(Selection(table.base, table.base + table.unit.count)) == (
        "k\tv\tw\none\talpha bravo charlie delta echo foxtrot\tx\ntwo\t\ty"
    )
    # From the middle of the title to the middle of the first paragraph.
    assert model.copy_text(Selection(2, 12)) == "tle\n\nFirst"
    assert whole.startswith("Title\n\nFirst")
    assert model.copy_text(Selection(2, 2)) == ""
    # The separators are available without the text, by index.
    separators = model.separators_within(0, layout.length)
    assert separators[table.base] == "\n\n"
    assert sorted(set(separators.values())) == ["\t", "\n", "\n\n", " "]


# -- lists: one newline between the blocks of a list, two spaces a level ------


def _copied(source: str, theme: Theme, measure: Any, **kwargs: Any) -> str:
    document = build_document(source, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, sp_from_px(520.0), measure, **kwargs)
    return layout.model.copy_text(Selection(0, layout.length))


LISTS_AS_COPIED = {
    "flat": ("- one\n- two\n", "• one\n• two"),
    # Review 4, item 5, measured before the fix: '• one\n\n• two'. A quote is
    # one unit and every block after its first was given a blank line.
    "in a quote": ("> - one\n> - two\n", "• one\n• two"),
    "in a quote, between paragraphs": (
        "> before\n>\n> - one\n> - two\n>\n> after\n",
        "before\n\n• one\n• two\n\nafter",
    ),
    # Measured before the fix: '• a\n\n1. b\n2. c\n\n• d'. The rule compared
    # the kinds of two neighbours, and a nested list of the other kind read as
    # a second list.
    "numbers inside a bullet": (
        "- a\n  1. b\n  2. c\n- d\n",
        "• a\n  1. b\n  2. c\n• d",
    ),
    "two deep": (
        "- a\n  - b\n    - c\n  - d\n- e\n",
        "• a\n  • b\n    • c\n  • d\n• e",
    ),
    "two deep in a quote": (
        "> - a\n>   1. b\n>      - c\n> - d\n",
        "• a\n  1. b\n    • c\n• d",
    ),
    # A block inside an item starts a line where its item's marker does: the
    # indent says how deep the list is and nothing else.
    "a second paragraph": ("- a\n\n  second\n- b\n", "• a\nsecond\n• b"),
    "a second paragraph, nested": (
        "- a\n  - b\n\n    second\n  - c\n",
        "• a\n  • b\n  second\n  • c",
    ),
    "a fence": (
        "- a\n\n  ```\n  x = 1\n\n  y = 2\n  ```\n- b\n",
        "• a\nx = 1\n\ny = 2\n• b",
    ),
    "a fence, nested": (
        "- a\n  - b\n\n    ```\n    x = 1\n\n    y = 2\n    ```\n  - c\n",
        "• a\n  • b\n  x = 1\n\n  y = 2\n  • c",
    ),
    "a hard break, nested": ("- a\n  - b\\\n    c\n", "• a\n  • b\n  c"),
    "a quote inside an item": ("- a\n\n  > said\n- b\n", "• a\nsaid\n• b"),
    "then a paragraph": ("- one\n- two\n\nafter\n", "• one\n• two\n\nafter"),
    "nested, then a paragraph": (
        "before\n\n- a\n  - b\n\nafter\n",
        "before\n\n• a\n  • b\n\nafter",
    ),
    "then a fence outside it": ("- a\n\n```\nx\n```\n", "• a\n\nx"),
    # Two lists, as before: a blank line. Inside a quote the blocks' kind is
    # QUOTE for both, so this one is read off the markers.
    "bullets then numbers": ("- a\n\n1. b\n", "• a\n\n1. b"),
    "bullets then numbers, in a quote": ("> - a\n>\n> 1. b\n", "• a\n\n1. b"),
    "a quoted list then a list": ("> - a\n\n- b\n", "• a\n\n• b"),
    "a list then a quoted list": ("- a\n\n> - b\n", "• a\n\n• b"),
}
"""
Markdown, and what a copy of all of it gives: the whole rule for lists, as strings.

Every block inside one outermost list begins a new line -- one newline, never
a blank line -- and every line a copy begins inside a block that is two or
more lists deep is indented two spaces for each list beyond the first. A
blank line is what ends a list, or separates it from the next one.
"""


@pytest.mark.parametrize("case", sorted(LISTS_AS_COPIED))
def test_a_list_copies_one_block_to_a_line_indented_two_spaces_a_level(
    theme: Theme, measure: Any, bundled_fonts: Any, case: str
) -> None:
    source, expected = LISTS_AS_COPIED[case]
    assert _copied(source, theme, measure) == expected


def test_a_fence_in_a_nested_item_copies_the_same_in_pieces(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    lines = [f"line {number}" for number in range(7)]
    source = "- a\n  - b\n\n" + "".join(f"    {line}\n" for line in ["```", *lines, "```"])
    expected = "• a\n  • b\n" + "\n".join(f"  {line}" for line in lines)
    assert _copied(source, theme, measure) == expected
    assert _copied(source, theme, measure, code_lines=3) == expected


def test_a_copy_that_starts_or_ends_inside_a_nested_item_indents_only_lines_it_begins(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    document = build_document("- a\n  1. b\n  2. c\n- d\n", theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, sp_from_px(520.0), measure)
    model, length = layout.model, layout.length
    to_the_end = [model.copy_text(Selection(start, length)) for start in range(length)]
    from_the_top = [model.copy_text(Selection(0, end)) for end in range(1, length + 1)]

    # A separator, indent included, is written between two pieces of selected
    # text and nowhere else, so the line a selection starts on is not indented
    # -- whether it starts at the nested item's marker or inside its text --
    # and every later line is.
    assert "1. b\n  2. c\n• d" in to_the_end
    assert "b\n  2. c\n• d" in to_the_end
    assert "c\n• d" in to_the_end
    assert not [text for text in to_the_end if text[:1].isspace()]
    # Ending inside a nested item: the indent of the line it ends on is there.
    assert "• a\n  1. b" in from_the_top
    assert "• a\n  1." in from_the_top
    assert "• a\n  1. b\n  2. c\n• d" == from_the_top[-1]
    # ... and a selection that stops before anything of the next line does
    # not end with that line's newline or its indent.
    assert not [text for text in from_the_top if text[-1:].isspace()]


def test_a_list_block_built_by_hand_without_its_indent_is_still_an_item(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # `text_block` infers no indent from `kind`. A host that leaves it out
    # gets what it got before nesting was read: one newline between items of
    # one kind, no indent.
    blocks = tuple(
        text_block(text, theme, fontlib_metrics, kind=BlockKind.BULLET_ITEM, marker="•")
        for text in ("one", "two")
    )
    layout = layout_units(blocks, theme, sp_from_px(520.0), measure)
    assert layout.model.copy_text(Selection(0, layout.length)) == "• one\n• two"


# -- tables: copy, clicks and highlights over wrapped cells -------------------


def _table_layout(rule: str, theme: Theme, measure: Any, width_px: float = 150.0) -> UnitLayout:
    source = (
        f"| k | v |\n|---|{rule}|\n"
        "| one | alpha bravo charlie delta echo foxtrot |\n"
        "| two | golf |\n"
    )
    document = build_document(source, theme, fontlib_metrics)
    return layout_units(document.blocks, theme, sp_from_px(width_px), measure)


@pytest.mark.parametrize("rule", ["---", ":--", "--:", ":-:"])
@pytest.mark.parametrize("width_px", [150.0, 1200.0])
def test_a_table_copies_as_tabs_between_cells_and_newlines_between_rows(
    theme: Theme, measure: Any, bundled_fonts: Any, rule: str, width_px: float
) -> None:
    # Left, right and centred second columns, wrapped (150 px) and not: one
    # tab a cell, one newline a row, a wrapped cell's lines joined by single
    # spaces, and no space anywhere from the glue that does the aligning.
    layout = _table_layout(rule, theme, measure, width_px)
    assert layout.model.copy_text(Selection(0, layout.length)) == (
        "k\tv\none\talpha bravo charlie delta echo foxtrot\ntwo\tgolf"
    )
    wrapped = len(layout.model.fragments) > 4
    assert wrapped == (width_px < 1000.0)


def test_a_click_under_a_short_cell_stays_in_its_column(
    theme: Theme, measure: Any, bundled_fonts: Any
) -> None:
    # Review 2, item 2. Failed against the rule that looked at x only among
    # lines whose band held y: the answer was the neighbour's "echo foxtrot".
    layout = _table_layout("---", theme, measure)
    model = layout.model
    with_text = [f for f in model.fragments if any(isinstance(i, Glyph) for i in f.items)]
    one = next(f for f in with_text if model.text(Selection(f.start, f.end)).strip() == "one")
    tall = [f for f in with_text if f.outer == one.outer and f is not one]
    lowest = max(tall, key=lambda fragment: fragment.bottom)
    assert lowest.top >= one.bottom, "the neighbour must have a line below the short cell"
    under = Point(one.line.x + 1, (lowest.top + lowest.bottom) // 2)
    assert model.fragment_at(under) == one
    assert model.text(model.line_at(under)).strip() == "one"
    # And the flat model over the same commands agrees, as it must.
    flat_model = SelectionModel.from_commands(layout.cmds)
    assert flat_model.fragment_at(under) == one


@pytest.mark.parametrize("rule", ["--:", ":-:"])
def test_a_highlight_over_a_right_or_centred_wrapped_cell_covers_its_text_and_no_blank(
    theme: Theme, measure: Any, bundled_fonts: Any, rule: str
) -> None:
    # Review 2, item 4's second half. The glue that pushes a right-aligned
    # line to the right takes an index, so selecting the line selected it, and
    # the highlight ran from the cell's left edge.
    layout = _table_layout(rule, theme, measure)
    model = layout.model
    lines = [
        f
        for f in model.fragments
        if f.outer is not None and sum(isinstance(i, Glyph) for i in f.items) > 3
    ]
    assert len(lines) >= 3, "the second column must have wrapped"
    for fragment in lines:
        glyphs = [item for item in fragment.items if isinstance(item, Glyph)]
        assert isinstance(fragment.items[0], SetGlue), "no aligning glue ahead of the text"
        (rect,) = model.rects(Selection(fragment.start, fragment.end))
        assert rect.x == glyphs[0].x
        assert rect.x > fragment.line.x
        last = fragment.items.index(glyphs[-1])
        assert rect.x + rect.width == fragment.edges[last + 1]


# -- a long code block laid out in pieces ----------------------------------
#
# `layout_units(..., code_lines=n)` cuts a code block of more than `n` lines
# into units of `n`. The oracle for every test here is the same call without
# `code_lines`: the block as one unit, which the first half of this file has
# already tied to the whole-document pipeline.

PIECE = 4
"""
Lines a piece, in these tests: small, so that a block of a few dozen lines is many pieces.
"""


def code_source(lines: int, blank: tuple[int, ...] = ()) -> str:
    """
    A paragraph, a fence of `lines` lines (those numbered in `blank` empty), and a paragraph.
    """
    body = "".join(
        (
            "\n"
            if number in blank
            else f"value_{number} = compute({number})  # {'x' * (number % 7 + 1)}\n"
        )
        for number in range(lines)
    )
    return f"Before the code.\n\n```python\n{body}```\n\nAfter the code.\n"


BLANKS = (0, 1, 3, 4, 8, 9, 10, 11, 15, 16, 22)
"""
Blank lines where they are hardest for a copy: the block's first two lines, the last
line of a piece and the first of the next, a whole piece of nothing else, and the
block's last line. A blank line owns no index, so a piece that follows only blank
lines begins at the block's own first index.
"""

OPENS_BLANK = (0, 1, 2, 3, 4, 5, 9)
"""
The block's whole first piece blank, and the start of its second: the second piece then
begins at the block's own first index, where a newline written for the piece would
replace the blank line written for the block.
"""

LENGTHS = (PIECE, PIECE + 1, 2 * PIECE, 2 * PIECE + 1, 23)
"""
Not cut at all, cut into a piece and one line, two whole pieces, two and a line, six.
"""


def pieced_and_whole(
    source: str, theme: Theme, measure: Any, width: Scaled = MEASURES[1]
) -> tuple[UnitLayout, UnitLayout, Document]:
    document = build_document(source, theme, fontlib_metrics)
    pieced = layout_units(document.blocks, theme, width, measure, code_lines=PIECE)
    whole = layout_units(document.blocks, theme, width, measure)
    return pieced, whole, document


def loose_code(theme: Theme) -> Theme:
    """
    `theme` with code lines closer together than their own height, so `\\lineskip` applies.

    Under the default theme every code line is exactly one strut tall and the
    interline glue between two of them is zero, so a layout that forgot the
    glue between two pieces would still be right. Here the glue is the
    `\\lineskip`, three points, and forgetting it moves every later piece.
    """
    from advtext.nodes import GlueSpec
    from advtext.pack import InterlineSkip

    code = theme.blocks[BlockKind.CODE]
    tight = InterlineSkip(
        baselineskip=GlueSpec(width=code.font.size // 2),
        lineskip=GlueSpec(width=sp_from_pt(3.0)),
        lineskiplimit=0,
    )
    return replace(theme, blocks={**theme.blocks, BlockKind.CODE: replace(code, interline=tight)})


@pytest.mark.parametrize("lines", LENGTHS)
@pytest.mark.parametrize("blank", [(), BLANKS, OPENS_BLANK])
def test_a_code_block_in_pieces_ships_the_commands_of_the_block_laid_out_whole(
    theme: Theme, measure: Any, lines: int, blank: tuple[int, ...]
) -> None:
    pieced, whole, document = pieced_and_whole(code_source(lines, blank), theme, measure)
    # The shape first, or equal commands could mean nothing was cut. Counted
    # from the block and not from `lines`: a fence's trailing blank lines are
    # not lines of the block.
    block = document.blocks[1]
    assert isinstance(block, CodeBlock)
    lines = len(block.lines)
    expected = 1 if lines <= PIECE else -(-lines // PIECE)
    assert len(pieced.placed) == 2 + expected and len(whole.placed) == 3
    assert pieced.cmds == whole.cmds
    assert (pieced.height, pieced.length) == (whole.height, whole.length)
    assert tuple(ship(pieced.box, Point(0, pieced.box.height), measure=measure)) == whole.cmds
    parts = [unit.part for unit in pieced.placed]
    assert parts == ([None, None, None] if lines <= PIECE else [None, *range(expected), None])
    assert [unit.block_start for unit in pieced.placed] == [0, *([1] * expected), 2]


def test_pieces_are_stacked_with_the_interline_glue_the_whole_block_has_between_those_lines(
    theme: Theme, measure: Any
) -> None:
    loose = loose_code(theme)
    pieced, whole, _ = pieced_and_whole(code_source(23, BLANKS), loose, measure)
    assert pieced.cmds == whole.cmds and pieced.height == whole.height
    # And the glue really is something here: consecutive pieces do not abut.
    code = [unit for unit in pieced.placed if unit.part is not None]
    gaps = {below.y - above.bottom for above, below in zip(code, code[1:], strict=False)}
    # Both branches of the rule, in one block: a blank line is only as tall as
    # the strut, so the `\\baselineskip` still fits above or below it and comes
    # to nothing; between two lines of text it does not fit.
    assert gaps == {0, sp_from_pt(3.0)}
    # Under the default theme they do, which is why this test has its own.
    plain = [u for u in pieced_and_whole(code_source(23), theme, measure)[0].placed if u.part]
    assert {b.y - a.bottom for a, b in zip(plain, plain[1:], strict=False)} == {0}


@pytest.mark.parametrize("loosened", [False, True])
@pytest.mark.parametrize("blank", [BLANKS, OPENS_BLANK])
def test_every_query_on_a_code_block_in_pieces_gives_the_whole_blocks_answer(
    theme: Theme, measure: Any, loosened: bool, blank: tuple[int, ...]
) -> None:
    used = loose_code(theme) if loosened else theme
    pieced, whole, _ = pieced_and_whole(code_source(23, blank), used, measure)
    model, oracle = pieced.model, whole.model
    assert model.fragments == oracle.fragments
    assert model.separators_within(0, model.length) == oracle.separators_within(0, oracle.length)
    if blank is OPENS_BLANK:
        code = pieced.units_of_block(1)
        assert code[1].base == code[0].base, "the second piece must begin where the block does"

    xs = [sp_from_px(x) for x in (-20.0, 0.0, 14.0, 61.5, 140.0, 399.0, 900.0)]
    checked = 0
    for y in range(-sp_from_px(30.0), whole.height + sp_from_px(30.0), sp_from_px(2.3)):
        point = Point(0, y)
        # One block for every y the block covers, the glue between pieces included.
        assert pieced.block_at(point) == whole.block_at(point), y
        for x in xs:
            point = Point(x, y)
            assert model.fragment_at(point) == oracle.fragment_at(point), point
            assert model.hit(point) == oracle.hit(point)
            assert model.word_at(point) == oracle.word_at(point)
            assert model.line_at(point) == oracle.line_at(point)
            checked += 1
    assert checked > 500

    boundaries = {0, 1, model.length - 1, model.length}
    for unit in pieced.placed:
        boundaries.update((unit.base - 1, unit.base, unit.base + 1, unit.base + unit.unit.count))
    edges = sorted(b for b in boundaries if 0 <= b <= model.length)
    compared = 0
    for position, start in enumerate(edges):
        for end in edges[position:]:
            selection = Selection(start, end)
            assert model.rects(selection) == oracle.rects(selection), selection
            assert model.text(selection) == oracle.text(selection), selection
            # The copy: every line of the block ends in a newline, wherever
            # the selection starts and whichever pieces it crosses.
            assert model.copy_text(selection) == oracle.copy_text(selection), selection
            compared += 1
    assert compared > 200


@pytest.mark.parametrize("lines", LENGTHS)
def test_a_code_block_in_pieces_copies_as_its_source_lines(
    theme: Theme, measure: Any, lines: int
) -> None:
    # Against the source this time and not against the other layout: what a
    # copy of a code block *is*, is its lines with a newline between them.
    # Blank lines only inside the block: what a copy makes of a block's
    # leading and trailing blank lines is the whole-block path's business, and
    # the test above holds the pieces to it.
    source = code_source(lines, tuple(n for n in (2, 3, 4, 7, 8, 12, 15, 16) if n < lines - 1))
    pieced, whole, _ = pieced_and_whole(source, theme, measure)
    body = source.split("```python\n")[1].split("```")[0]
    everything = Selection(0, pieced.length)
    copied = pieced.model.copy_text(everything)
    assert copied == whole.model.copy_text(everything)
    assert copied == "Before the code.\n\n" + body.rstrip("\n") + "\n\nAfter the code."
    assert pieced.model.separators_within(0, pieced.length) == whole.model.separators_within(
        0, whole.length
    )
    own = pieced.indices_of_block(1)
    assert own == whole.indices_of_block(1) == whole.placed[1].index_range
    assert pieced.model.copy_text(Selection(own.start, own.stop)) == body.rstrip("\n")


def test_a_block_in_pieces_is_still_one_block_to_everything_addressed_by_number(
    theme: Theme, measure: Any
) -> None:
    pieced, whole, _ = pieced_and_whole(code_source(23, BLANKS), theme, measure)
    units = pieced.units_of_block(1)
    assert len(units) == 6 and [unit.part for unit in units] == list(range(6))
    assert pieced.unit_of_block(1) is units[0]
    assert all(unit.block_range == range(1, 2) for unit in units)
    # Each piece is a code block of its own lines; together, the block's.
    block = whole.placed[1].blocks[0]
    assert isinstance(block, CodeBlock)
    assert sum((unit.blocks[0].lines for unit in units), ()) == block.lines  # type: ignore[union-attr]
    assert all(isinstance(unit.blocks[0], CodeBlock) for unit in units)
    # `skipped` is the material before the piece, which is what a colour span
    # in the block's coordinates has to be moved down by.
    assert [unit.skipped for unit in units] == [
        sum(len(line) for line in block.lines[: PIECE * number]) for number in range(6)
    ]
    # The pieces tile the block's indices, and a block that is one unit says so too.
    assert units[0].base == whole.placed[1].base
    assert units[-1].base + units[-1].unit.count == whole.placed[1].index_range.stop
    assert pieced.units_of_block(0) == (pieced.placed[0],)
    assert pieced.indices_of_block(2) == pieced.placed[-1].index_range
    assert pieced.units_of_block(7) == () and pieced.indices_of_block(7) == range(0)


def test_a_code_block_inside_a_list_item_is_cut_too_and_keeps_its_indent(
    theme: Theme, measure: Any
) -> None:
    body = "".join(f"   line_{n} = {n}\n" for n in range(11))
    source = f"1. An item with code in it:\n\n   ```\n{body}   ```\n\n2. The next item.\n"
    pieced, whole, document = pieced_and_whole(source, theme, measure)
    code = [n for n, block in enumerate(document.blocks) if isinstance(block, CodeBlock)]
    assert len(code) == 1 and document.blocks[code[0]].left_indent > 0  # type: ignore[union-attr]
    assert len(pieced.units_of_block(code[0])) == 3
    assert pieced.cmds == whole.cmds
    everything = Selection(0, pieced.length)
    assert pieced.model.copy_text(everything) == whole.model.copy_text(everything)


def test_pieces_are_not_cut_unless_asked_for(theme: Theme, measure: Any) -> None:
    document = build_document(code_source(200), theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, MEASURES[1], measure)
    assert len(layout.placed) == 3 and all(unit.part is None for unit in layout.placed)
    # A view of a settled document does not ask.
    view = DocumentView(document=document, theme=theme, measure=measure)
    assert len(view.layout_for(MEASURES[1]).placed) == 3


def grown(lines: int, theme: Theme) -> Document:
    """
    A document whose code block has `lines` lines, re-parsed: no object shared with any other.
    """
    return build_document(code_source(lines), theme, fontlib_metrics)


def test_a_line_added_to_a_block_in_pieces_ships_the_last_piece_and_no_other(
    theme: Theme, measure: Any, counted: _Counted
) -> None:
    # The claim the pieces exist for, as a count of `ship` calls and of the
    # lines they shipped. The documents are parsed afresh each time, so every
    # earlier piece is found by value -- the harder case; a stream hands over
    # the same line objects and they are found by identity.
    width = MEASURES[1]
    units = UnitCache()
    shipped: list[int] = []
    previous: UnitLayout | None = None
    for lines in range(2 * PIECE, 6 * PIECE + 2):
        before = counted.calls
        document = grown(lines, theme)
        layout = layout_units(
            document.blocks, theme, width, measure, units=units, previous=previous, code_lines=PIECE
        )
        shipped.append(counted.calls - before)
        assert layout.cmds == layout_units(document.blocks, theme, width, measure).cmds
        if previous is not None:
            # Every piece but the last is the unit it was, shipped commands and all.
            for old, new in zip(previous.placed[1:-2], layout.placed[1:], strict=False):
                assert new.unit.cmds is old.unit.cmds
        previous = layout
    # The first layout ships everything; each one after it ships exactly one
    # unit, whatever the block's length, and that unit is at most a piece.
    assert shipped[0] == 2 + 2 and set(shipped[1:]) == {1}
    last = previous.placed[-2] if previous is not None else None
    assert last is not None and last.unit.lines <= PIECE


def test_a_block_that_grows_past_one_piece_keeps_the_unit_it_had_as_its_first(
    theme: Theme, measure: Any, counted: _Counted
) -> None:
    width = MEASURES[1]
    units = UnitCache()
    whole = layout_units(
        grown(PIECE, theme).blocks, theme, width, measure, units=units, code_lines=PIECE
    )
    assert [unit.part for unit in whole.placed] == [None, None, None]
    before = counted.calls
    cut = layout_units(
        grown(PIECE + 1, theme).blocks, theme, width, measure, units=units, code_lines=PIECE
    )
    assert [unit.part for unit in cut.placed] == [None, 0, 1, None]
    assert counted.calls - before == 1, "only the one new line is shipped"
    assert cut.placed[1].unit.cmds is whole.placed[1].unit.cmds


def test_the_same_document_laid_out_again_in_pieces_is_the_same_placed_units(
    theme: Theme, measure: Any, counted: _Counted
) -> None:
    document = grown(23, theme)
    units = UnitCache()
    width = MEASURES[1]
    first = layout_units(document.blocks, theme, width, measure, units=units, code_lines=PIECE)
    before = (counted.calls, units.stats().misses)
    again = layout_units(
        document.blocks, theme, width, measure, units=units, previous=first, code_lines=PIECE
    )
    assert (counted.calls, units.stats().misses) == before
    assert all(new is old for new, old in zip(again.placed, first.placed, strict=True))
    # The pieces themselves are the same objects, which is what lets the unit
    # cache answer by identity: nothing is compared by value on this path.
    assert all(
        new.blocks[0] is old.blocks[0] for new, old in zip(again.placed, first.placed, strict=True)
    )
    # At another width the pieces are still those objects; their units are not.
    other = layout_units(
        document.blocks, theme, MEASURES[0], measure, units=units, code_lines=PIECE
    )
    assert all(
        a.blocks[0] is b.blocks[0]
        for a, b in zip(other.placed[1:-1], first.placed[1:-1], strict=True)
    )


def test_a_piece_is_not_reused_for_lines_that_differ(theme: Theme, measure: Any) -> None:
    # The memo of pieces is keyed by the block's number; what it holds is
    # checked by value, so a block replaced by another of the same length
    # cannot be handed the first one's pieces.
    width = MEASURES[1]
    units = UnitCache()
    one = build_document(code_source(13), theme, fontlib_metrics)
    other = build_document(code_source(13).replace("value_6", "other_6"), theme, fontlib_metrics)
    layout_units(one.blocks, theme, width, measure, units=units, code_lines=PIECE)
    changed = layout_units(other.blocks, theme, width, measure, units=units, code_lines=PIECE)
    assert changed.cmds == layout_units(other.blocks, theme, width, measure).cmds
    assert "other_6" in changed.model.copy_text(Selection(0, changed.length))
    # And a different style is a different piece even with the same lines.
    restyled = loose_code(theme)
    block = one.blocks[1]
    assert isinstance(block, CodeBlock)
    moved_style = replace(block, style=restyled.blocks[BlockKind.CODE])
    again = layout_units(
        (one.blocks[0], moved_style, one.blocks[2]),
        theme,
        width,
        measure,
        units=units,
        code_lines=PIECE,
    )
    assert (
        again.cmds
        == layout_units((one.blocks[0], moved_style, one.blocks[2]), theme, width, measure).cmds
    )


def test_a_selection_is_carried_across_a_block_in_pieces_growing(
    theme: Theme, measure: Any
) -> None:
    width = MEASURES[1]
    old = layout_units(grown(10, theme).blocks, theme, width, measure, code_lines=PIECE)
    new = layout_units(grown(15, theme).blocks, theme, width, measure, code_lines=PIECE)
    pieces = old.units_of_block(1)
    assert len(pieces) == 3
    # From inside the first paragraph to inside the last (short) piece.
    selection = Selection(3, pieces[2].base + 5)
    carried = units_module.carry_selection(selection, old, new)
    assert carried is not None
    assert new.model.copy_text(carried) == old.model.copy_text(selection)
    # Within one middle piece, whose twin is the piece of the same number.
    inner = Selection(pieces[1].base + 2, pieces[1].base + 9)
    carried = units_module.carry_selection(inner, old, new)
    assert carried == inner and new.model.text(carried) == old.model.text(inner)
    # Not carried into other text: the same block with a line taken out of its middle.
    shorter = build_document(code_source(10).replace("value_4", "v_4"), theme, fontlib_metrics)
    other = layout_units(shorter.blocks, theme, width, measure, code_lines=PIECE)
    assert units_module.carry_selection(inner, old, other) is None


@pytest.mark.parametrize("width_px", [520.0, 160.0])
@pytest.mark.parametrize(
    ("first", "body"),
    [("", "x"), ("h", "x"), ("", "")],
    ids=["empty-header-cell", "control", "empty-first-column"],
)
def test_a_table_whose_header_begins_with_an_empty_cell_keeps_the_blank_line_before_it(
    first: str, body: str, width_px: float, theme: Theme, measure: Any
) -> None:
    """
    Review 4 suspected this was lost when the header row wraps. It is not: pinned, not fixed.

    The reviewer read that an empty first cell in a wrapped header row might
    overwrite the blank line a table is led by in copied text. Measured at a
    width where the header fits (520 px) and one where it wraps onto several
    lines (160 px), with the first header cell empty, with the whole first
    column empty, and with neither as the control: the paragraph before is
    followed by a blank line in every case, and the empty cell is a tab with
    nothing in front of it.
    """
    long = "a header cell with many words in it that must wrap at this width"
    source = f"before\n\n| {first} | {long} |\n|---|---|\n| {body} | y |\n\nafter\n"
    document = build_document(source, theme, fontlib_metrics)
    layout = layout_units(document.blocks, theme, sp_from_px(width_px), measure)
    copied = layout.model.copy_text(Selection(0, layout.length))
    assert copied == f"before\n\n{first}\t{long}\n{body}\ty\n\nafter"
    if width_px < 200.0:
        table = layout.placed[1]
        baselines = {cmd.y for cmd in table.unit.cmds if isinstance(cmd, Line)}
        assert len(baselines) > 3, "the header did not wrap at this width"


# -- a long table in pieces ------------------------------------------------------

LONG_CELL = "several words in one cell, enough of them that it wraps at any ordinary measure"


def table_source(rows: int) -> str:
    """
    A paragraph, a three-column table of `rows` rows, a paragraph.

    Rows are made to differ in the ways a cut could get wrong, and the ones
    either side of a cut at `PIECE` are the awkward ones: a long cell that
    wraps (row 3, the last of the first piece, and row 4, the first of the
    second), an empty first cell (rows 4 and 8, each the first of a piece),
    an empty last cell, a link, and alignment in every column.
    """
    lines = ["Before the table.", "", "| key | value | note |", "|:--|--:|:-:|"]
    for number in range(rows):
        key = "" if number in (4, 8, 13) else f"k{number}"
        value = LONG_CELL if number in (3, 4, 9, 15) else f"{number * 7}.{number:02d}"
        note = "" if number % 5 == 2 else f"n{number}"
        if number % 4 == 1:
            note = f"[link {number}](https://example.com/{number})"
        if number == 7:
            value = f"see [a](https://a.example) and [b](https://b.example) {LONG_CELL}"
        lines.append(f"| {key} | {value} | {note} |")
    lines += ["", "After the table.", ""]
    return "\n".join(lines)


TABLE_WIDTHS = (sp_from_px(150.0), sp_from_px(300.0), sp_from_px(520.0), sp_from_px(2400.0))
"""
Narrower than the longest words, wrapping, wrapping less, and wide enough that nothing wraps.
"""


def table_pieced_and_whole(
    rows: int, theme: Theme, measure: Any, width: Scaled, sized: bool = False
) -> tuple[UnitLayout, UnitLayout, Document]:
    """
    The same document with its table in pieces of `PIECE` rows, and whole.

    `sized` states the table's widths first (`with_columns`), which is how a
    streaming view hands a live table over; left alone the widths are the
    default apportioning's and the layout works them out.
    """
    from advtext.ui import table_natural_widths, with_columns

    document = build_document(table_source(rows), theme, fontlib_metrics)
    blocks = document.blocks
    if sized:
        table = blocks[1]
        assert isinstance(table, TableBlock)
        natural = table_natural_widths(table, theme, measure)
        # Held narrower than its content in the middle column, so rows wrap.
        widths = (natural[0], min(natural[1], sp_from_px(140.0)), natural[2])
        blocks = (blocks[0], with_columns(table, widths=widths), blocks[2])
    pieced = layout_units(blocks, theme, width, measure, table_rows=PIECE)
    whole = layout_units(blocks, theme, width, measure)
    return pieced, whole, document


@pytest.mark.parametrize("sized", [False, True])
@pytest.mark.parametrize("width", TABLE_WIDTHS)
@pytest.mark.parametrize("rows", LENGTHS)
def test_a_table_in_pieces_ships_the_commands_of_the_table_laid_out_whole(
    theme: Theme, measure: Any, rows: int, width: Scaled, sized: bool
) -> None:
    pieced, whole, _ = table_pieced_and_whole(rows, theme, measure, width, sized)
    expected = 1 if rows <= PIECE else -(-rows // PIECE)
    assert len(pieced.placed) == 2 + expected and len(whole.placed) == 3
    assert pieced.cmds == whole.cmds
    assert (pieced.height, pieced.length) == (whole.height, whole.length)
    assert tuple(ship(pieced.box, Point(0, pieced.box.height), measure=measure)) == whole.cmds
    parts = [unit.part for unit in pieced.placed]
    assert parts == ([None, None, None] if rows <= PIECE else [None, *range(expected), None])
    assert [unit.block_start for unit in pieced.placed] == [0, *([1] * expected), 2]


def test_the_cuts_of_the_table_fixture_fall_between_rows_that_wrapped(
    theme: Theme, measure: Any
) -> None:
    # What the equality above is worth at a cut: the row above it and the row
    # below it are both several lines deep at this width, so the glue between
    # two pieces is the glue after a wrapped row (`prev_depth_after`) and a
    # layout that read the row's own depth would move everything below.
    from advtext.ui import prev_depth_after

    pieced, whole, _ = table_pieced_and_whole(23, theme, measure, TABLE_WIDTHS[1])
    first, second = pieced.units_of_block(1)[:2]
    last_row, next_row = first.unit.box.contents[-1], second.unit.box.contents[0]
    leading = theme.blocks[BlockKind.TABLE].interline.baselineskip.width
    assert last_row.height + last_row.depth > 2 * leading  # type: ignore[union-attr]
    assert next_row.height + next_row.depth > 2 * leading  # type: ignore[union-attr]
    assert prev_depth_after(last_row) != last_row.depth  # type: ignore[arg-type, union-attr]
    assert pieced.cmds == whole.cmds


@pytest.mark.parametrize("sized", [False, True])
@pytest.mark.parametrize("width", TABLE_WIDTHS[:3])
def test_every_query_on_a_table_in_pieces_gives_the_whole_tables_answer(
    theme: Theme, measure: Any, width: Scaled, sized: bool
) -> None:
    pieced, whole, _ = table_pieced_and_whole(23, theme, measure, width, sized)
    model, oracle = pieced.model, whole.model
    assert model.fragments == oracle.fragments
    assert model.separators_within(0, model.length) == oracle.separators_within(0, oracle.length)

    xs = [sp_from_px(x) for x in (-20.0, 0.0, 14.0, 61.5, 140.0, 260.0, 399.0, 900.0)]
    checked = 0
    for y in range(-sp_from_px(30.0), whole.height + sp_from_px(30.0), sp_from_px(4.7)):
        point = Point(0, y)
        assert pieced.block_at(point) == whole.block_at(point), y
        for x in xs:
            point = Point(x, y)
            assert model.fragment_at(point) == oracle.fragment_at(point), point
            assert model.hit(point) == oracle.hit(point)
            assert model.word_at(point) == oracle.word_at(point)
            assert model.line_at(point) == oracle.line_at(point)
            checked += 1
    assert checked > 500

    boundaries = {0, 1, model.length - 1, model.length}
    for unit in pieced.placed:
        boundaries.update((unit.base - 1, unit.base, unit.base + 1, unit.base + unit.unit.count))
        boundaries.update(range(unit.base + 2, unit.base + unit.unit.count, 37))
    edges = sorted(b for b in boundaries if 0 <= b <= model.length)
    compared = 0
    for position, start in enumerate(edges):
        for end in edges[position:]:
            selection = Selection(start, end)
            assert model.rects(selection) == oracle.rects(selection), selection
            assert model.text(selection) == oracle.text(selection), selection
            assert model.copy_text(selection) == oracle.copy_text(selection), selection
            compared += 1
    assert compared > 300


@pytest.mark.parametrize("width", TABLE_WIDTHS)
def test_a_table_in_pieces_copies_as_tabs_and_newlines_from_its_source(
    theme: Theme, measure: Any, width: Scaled
) -> None:
    # Against the source and not against the other layout: a row to a line,
    # a tab between cells, an empty cell still a tab, markup gone.
    import re

    source = table_source(23)
    pieced, whole, _ = table_pieced_and_whole(23, theme, measure, width)
    rows = []
    for line in source.splitlines():
        if line.startswith("|") and not line.startswith("|:"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows.append("\t".join(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell) for cell in cells))
    everything = Selection(0, pieced.length)
    copied = pieced.model.copy_text(everything)
    assert copied == whole.model.copy_text(everything)
    assert copied == "Before the table.\n\n" + "\n".join(rows) + "\n\nAfter the table."
    own = pieced.indices_of_block(1)
    assert own == whole.indices_of_block(1) == whole.placed[1].index_range
    # The last row's last cell is empty, and a copy does not end in a
    # separator with nothing after it.
    alone = pieced.model.copy_text(Selection(own.start, own.stop))
    assert alone == whole.model.copy_text(Selection(own.start, own.stop))
    assert rows[-1].endswith("\t") and alone == "\n".join(rows).rstrip("\t")


def test_a_table_in_pieces_is_still_one_block_to_everything_addressed_by_number(
    theme: Theme, measure: Any
) -> None:
    from advtext.ui import SizedTable, table_columns

    pieced, whole, document = table_pieced_and_whole(23, theme, measure, TABLE_WIDTHS[1])
    units = pieced.units_of_block(1)
    assert len(units) == 6 and [unit.part for unit in units] == list(range(6))
    assert pieced.unit_of_block(1) is units[0]
    assert all(unit.block_range == range(1, 2) for unit in units)
    table = document.blocks[1]
    assert isinstance(table, TableBlock)
    pieces = [unit.blocks[0] for unit in units]
    assert all(isinstance(piece, SizedTable) for piece in pieces)
    # The header is the first piece's and nobody else's; the rows are the
    # table's, in order; every piece is at the whole table's widths.
    assert [piece.header for piece in pieces] == [table.header, (), (), (), (), ()]  # type: ignore[union-attr]
    assert sum((piece.rows for piece in pieces), ()) == table.rows  # type: ignore[union-attr]
    widths = table_columns(table, theme, TABLE_WIDTHS[1], measure)
    assert {piece.column_widths for piece in pieces} == {widths}  # type: ignore[union-attr]
    # `skipped` is the links in the rows before the piece.
    links = [sum(len(cell.links) for cell in row) for row in table.rows]
    assert [unit.skipped for unit in units] == [sum(links[: PIECE * n]) for n in range(6)]
    assert sum(links) > 6 and units[2].skipped != units[1].skipped
    assert units[0].base == whole.placed[1].base
    assert units[-1].base + units[-1].unit.count == whole.placed[1].index_range.stop
    assert pieced.indices_of_block(1) == whole.placed[1].index_range


def test_no_piece_of_a_table_has_a_separator_of_its_own_at_its_first_index(
    theme: Theme, measure: Any
) -> None:
    """
    The precondition of joining a piece to the one above with a lead and nothing more.

    `UnitModel.separators_within` writes the newline before a later piece at
    the piece's first index and then the piece's own separators over the
    top. In a whole table a newline and a tab at one index are concatenated
    (`_separators_within`), which could only matter here if a piece's first
    cell took no index at all, so that the tab after it sat on the piece's
    first index. It does not happen: an empty cell is still packed with its
    alignment glue, wrapped or not, and that glue has an index. Pinned on
    pieces that begin with an empty cell at a width where the row wraps and
    one where it does not, so that a change to how a cell is built is told
    it has a second thing to change.
    """
    for width in (TABLE_WIDTHS[0], TABLE_WIDTHS[3]):
        pieced, whole, document = table_pieced_and_whole(23, theme, measure, width)
        table = document.blocks[1]
        assert isinstance(table, TableBlock)
        units = pieced.units_of_block(1)
        empty_first = [n for n, unit in enumerate(units) if not unit.blocks[0].rows[0][0].material]  # type: ignore[union-attr]
        assert empty_first == [1, 2]
        for unit in units[1:]:
            assert unit.separators and min(unit.separators) > unit.base
        assert pieced.model.separators_within(0, pieced.length) == whole.model.separators_within(
            0, whole.length
        )


def test_a_table_inside_a_list_item_is_cut_too_and_copies_the_same(
    theme: Theme, measure: Any
) -> None:
    rows = "".join(f"   | k{n} | {LONG_CELL if n == 3 else n} |\n" for n in range(11))
    source = f"1. An item with a table:\n\n   | a | b |\n   |---|---|\n{rows}\n2. The next item.\n"
    document = build_document(source, theme, fontlib_metrics)
    (number,) = [n for n, block in enumerate(document.blocks) if isinstance(block, TableBlock)]
    assert document.blocks[number].left_indent > 0  # type: ignore[union-attr]
    width = TABLE_WIDTHS[1]
    pieced = layout_units(document.blocks, theme, width, measure, table_rows=PIECE)
    whole = layout_units(document.blocks, theme, width, measure)
    assert len(pieced.units_of_block(number)) == 3
    assert pieced.cmds == whole.cmds
    everything = Selection(0, pieced.length)
    assert pieced.model.copy_text(everything) == whole.model.copy_text(everything)
    assert pieced.model.separators_within(0, pieced.length) == whole.model.separators_within(
        0, whole.length
    )


def test_tables_are_not_cut_unless_asked_for_nor_when_a_sized_table_could_not_say_them(
    theme: Theme, measure: Any
) -> None:
    document = build_document(table_source(60), theme, fontlib_metrics)
    width = TABLE_WIDTHS[1]
    layout = layout_units(document.blocks, theme, width, measure)
    assert len(layout.placed) == 3 and all(unit.part is None for unit in layout.placed)
    # Asked for code pieces only: a table is not a code block.
    layout = layout_units(document.blocks, theme, width, measure, code_lines=PIECE)
    assert len(layout.placed) == 3

    # A table built by hand with a short row. Composition sets it; a piece
    # at stated widths could not be constructed for it, so it stays whole.
    table = document.blocks[1]
    assert isinstance(table, TableBlock)
    ragged = replace(table, rows=(*table.rows[:9], table.rows[9][:2], *table.rows[10:]))
    blocks = (document.blocks[0], ragged, document.blocks[2])
    pieced = layout_units(blocks, theme, width, measure, table_rows=PIECE)
    assert len(pieced.placed) == 3
    assert pieced.cmds == layout_units(blocks, theme, width, measure).cmds


def grown_table(rows: int, theme: Theme, last: str = "") -> Document:
    source = table_source(rows)
    if last:
        source = source.replace("\n\nAfter the table.", f"\n| k | {last} | x |\n\nAfter the table.")
    return build_document(source, theme, fontlib_metrics)


def test_a_row_added_to_a_table_in_pieces_ships_the_last_piece_and_no_other(
    theme: Theme, measure: Any, counted: _Counted
) -> None:
    """
    The count the pieces exist for, where the widths are stated and do not change.

    A streaming view states a live table's widths (`with_columns`), and a row
    that is no wider than its columns leaves them alone. Then a row costs the
    piece it lands in. The blocks here are re-parsed each time, so pieces are
    found by value; `advtext.stream` hands rows back by identity and it is
    cheaper still.
    """
    from advtext.ui import table_natural_widths, with_columns

    width = TABLE_WIDTHS[2]
    cache = UnitCache()
    widths = table_natural_widths(grown_table(40, theme).blocks[1], theme, measure)  # type: ignore[arg-type]
    previous: UnitLayout | None = None
    shipped: list[int] = []
    for rows in range(20, 41):
        document = grown_table(rows, theme)
        table = document.blocks[1]
        assert isinstance(table, TableBlock)
        blocks = (document.blocks[0], with_columns(table, widths=widths), document.blocks[2])
        before = counted.calls
        previous = layout_units(
            blocks, theme, width, measure, units=cache, previous=previous, table_rows=PIECE
        )
        shipped.append(counted.calls - before)
    assert shipped[0] == 2 + 5
    assert set(shipped[1:]) == {1}, shipped
    whole = layout_units(blocks, theme, width, measure)
    assert previous is not None and previous.cmds == whole.cmds


def test_a_cell_that_widens_a_column_lays_every_piece_out_again_and_only_then(
    theme: Theme, measure: Any, counted: _Counted
) -> None:
    # Not stated: the widths are the default apportioning's, worked out from
    # the whole table. A row that changes no column's widest cell changes no
    # width at a measure the table fits, and ships its own piece; a row with
    # the widest cell yet changes them all, and every piece is set again.
    width = TABLE_WIDTHS[3]
    cache = UnitCache()
    first = grown_table(12, theme)
    one = layout_units(first.blocks, theme, width, measure, units=cache, table_rows=PIECE)
    assert len(one.units_of_block(1)) == 3

    before = counted.calls
    same = grown_table(12, theme, last="1")
    two = layout_units(
        same.blocks, theme, width, measure, units=cache, previous=one, table_rows=PIECE
    )
    assert len(two.units_of_block(1)) == 4 and counted.calls - before == 1

    before = counted.calls
    wider = grown_table(12, theme, last=LONG_CELL + " and then a good deal more than that")
    three = layout_units(
        wider.blocks, theme, width, measure, units=cache, previous=two, table_rows=PIECE
    )
    assert counted.calls - before == 4
    assert three.cmds == layout_units(wider.blocks, theme, width, measure).cmds


def test_a_settled_table_in_pieces_is_measured_once_and_placed_as_the_same_units(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The widths of a table that does not state them are worked out from
    # every cell. For a table that is the same object from layout to layout
    # -- a committed one -- that is done once per width, not once per layout.
    document = build_document(table_source(23), theme, fontlib_metrics)
    asked = [0]
    real = units_module.table_columns

    def counting(*args: Any, **kwargs: Any) -> Any:
        asked[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(units_module, "table_columns", counting)
    cache = UnitCache()
    width = TABLE_WIDTHS[1]
    one = layout_units(document.blocks, theme, width, measure, units=cache, table_rows=PIECE)
    two = layout_units(
        document.blocks, theme, width, measure, units=cache, previous=one, table_rows=PIECE
    )
    assert asked[0] == 1
    assert all(a is b for a, b in zip(one.placed, two.placed, strict=True))
    # Another width is another answer, and is asked for.
    other = layout_units(
        document.blocks, theme, TABLE_WIDTHS[2], measure, units=cache, table_rows=PIECE
    )
    assert asked[0] == 2
    assert other.cmds == layout_units(document.blocks, theme, TABLE_WIDTHS[2], measure).cmds


def test_a_selection_is_carried_across_a_table_in_pieces_growing(
    theme: Theme, measure: Any
) -> None:
    width = TABLE_WIDTHS[2]
    cache = UnitCache()
    old = layout_units(
        grown_table(13, theme).blocks, theme, width, measure, units=cache, table_rows=PIECE
    )
    new = layout_units(
        grown_table(14, theme).blocks,
        theme,
        width,
        measure,
        units=cache,
        previous=old,
        table_rows=PIECE,
    )
    pieces = old.units_of_block(1)
    selection = Selection(pieces[0].base + 3, pieces[2].base + 5)
    carried = units_module.carry_selection(selection, old, new)
    assert carried is not None
    assert new.model.copy_text(carried) == old.model.copy_text(selection)
    # And a caret on a cell's fill, in a piece that did not change.
    at = pieces[1].base + pieces[1].unit.count
    assert units_module.carry_caret(at, old, new) is not None

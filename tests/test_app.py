r"""
The demo application's pure parts: the page arithmetic, the tab grammar, the caches.

**What this file can and cannot reach.** `advtext.ui.app` defers every
`imgui_bundle` import into the function that needs it, so the module imports and
most of it runs with no window anywhere. What needs one -- `gui`, the five `_*_tab`
methods, `apply_style`, `load_fonts` -- is verified by photograph instead:
`make shot --tab NAME` runs the real app and writes a PNG, and the tabs were
checked by reading those. `docs/decisions.md` records that nothing in this suite
may open a window, and that has not changed.

So the split here is deliberate rather than lazy. Everything in this file is a
claim a picture cannot check -- that a sequence is conserved across a split, that
two rounding paths agree exactly, that a cache returns the same object -- and
everything a picture *can* check is left to the picture.

**The conservation test is the one that matters.** `test_every_glyph_survives_the_
split_in_reading_order` reads the codepoints out of the columns, concatenates
them, and compares against the same document composed in one piece at the same
measure. A splitter that dropped the tail, repeated a line at a column head, or
mis-ordered the columns fails it, and no screenshot at any resolution would.
Its fixture is guarded by `test_the_conservation_fixture_really_does_fill_more_
than_one_column`, because conservation over a document that all fits in column
one is a statement about nothing.
"""

from __future__ import annotations

import inspect
import re
import statistics
from collections.abc import Sequence

import pytest

from advtext.backends.imgui_draw import rgba
from advtext.markdown import build_document
from advtext.nodes import Box, CharNode, Glue
from advtext.shipout import DrawCmd, Glyph, Point, ship
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import compose_blocks
from advtext.ui.app import (
    COLUMN_COUNTS,
    MAX_COLUMN_PAGES,
    PLATE_HEADS,
    TAB_NAMES,
    App,
    ColumnPage,
    TabRequest,
    _column_pages,
    _plate,
    _vec4,
    column_page,
    demo_text,
    parse_tab_request,
)
from advtext.ui.document_view import (
    MEASURE_ALPHABETS,
    MIN_MARGIN_LEADINGS,
    TEXT_BLOCK_FRACTION,
    Page,
    alphabet_length,
    page_for,
)
from advtext.units import Scaled, sp_from_px

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

# Four paragraphs of plain prose and nothing else. No table, no fenced block and
# no list: `advtext.columns` documents that a run of consecutive one-line blocks
# is one unbreakable atom, and a fixture made of atoms would test the splitter's
# ability to give up rather than its ability to split. Long enough that it fills
# several short columns, which the meta-test below insists on.
FLOWING = "\n\n".join(
    f"Paragraph {n} of the conservation fixture. It exists to be cut in half by a "
    f"column break and then put back together again by a test, so it has to be "
    f"long enough to run over several lines at a narrow measure and plain enough "
    f"that nothing in it is an unbreakable atom. Sentence {n} ends here."
    for n in range(1, 9)
)

TINY = "# t\n\nOne short paragraph.\n"


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure(theme: Theme) -> object:
    return char_measure(fontlib_metrics)


@pytest.fixture(scope="module")
def alphabet(theme: Theme, measure: object) -> Scaled:
    """
    The real body alphabet, which is what both page functions are parameterised by.

    Taken from the live font rather than made up: the point of comparing
    `column_page` against `page_for` is that the two agree on the *production*
    numbers, and a round fake alphabet could hide a rounding disagreement that a
    real one exposes.
    """
    return alphabet_length(theme, measure)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def leading(theme: Theme) -> Scaled:
    return theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width


@pytest.fixture(scope="module")
def flowing_app(theme: Theme) -> App:
    """
    An `App` whose Columns tab flows `FLOWING`, built once.

    Module scoped because `App.__post_init__` parses `source`, and the caches
    under test are the app's own -- a fresh app per test would make every
    `is`-identity assertion trivially true.
    """
    return App(source=TINY, columns_source=FLOWING)


def _glyphs(cmds: Sequence[DrawCmd]) -> list[int]:
    """
    Every glyph a command list draws, in reading order, as codepoints.

    Codepoints and not positions: a split moves every line in column two to a new
    y, so positions are *supposed* to change and comparing them would compare the
    wrong thing. What must not change is which glyphs there are and what order
    they come in.
    """
    return [cmd.codepoint for cmd in cmds if isinstance(cmd, Glyph)]


def _whole(source: str, theme: Theme, measure: object, width: Scaled) -> Box:
    return compose_blocks(
        build_document(source, theme, fontlib_metrics).blocks,
        theme,
        width,
        measure,  # type: ignore[arg-type]
    )


# ----------------------------------------------------------------------
# The tab grammar
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, TabRequest()),
        ("", TabRequest()),
        ("document", TabRequest(tab="document")),
        ("Columns", TabRequest(tab="Columns")),
        ("columns:3", TabRequest(tab="columns", columns=3)),
        ("columns:1", TabRequest(tab="columns", columns=1)),
        ("columns:12", TabRequest(tab="columns", columns=12)),
        ("document:debug", TabRequest(tab="document", debug=True)),
        ("columns:3,debug", TabRequest(tab="columns", columns=3, debug=True)),
        ("columns:debug,3", TabRequest(tab="columns", columns=3, debug=True)),
        ("columns: 3 , debug ", TabRequest(tab="columns", columns=3, debug=True)),
    ],
)
def test_the_tab_grammar_parses_a_name_and_its_options(
    spec: str | None, expected: TabRequest
) -> None:
    assert parse_tab_request(spec) == expected


@pytest.mark.parametrize(
    "spec", ["columns:x", "columns:0", "columns:-2", "columns:3,verbose", "columns:"]
)
def test_a_misspelt_tab_option_is_refused_rather_than_ignored(spec: str) -> None:
    """
    A bad option must raise, and the message must name the option that was bad.

    Silently ignoring it is the failure this guards: a screenshot asked for at
    `columns:3` that quietly came back at the default count would be filed under a
    name claiming three columns, and a wrong picture is worse than a refusal.
    """
    with pytest.raises(ValueError) as caught:
        parse_tab_request(spec)
    bad = spec.partition(":")[2].split(",")[-1]
    assert bad in str(caught.value)


def test_a_request_without_a_colon_leaves_every_option_alone() -> None:
    """
    Naming a tab must not disturb the state the tab is in.

    The bare-name path is the one `make shot --tab document` takes, so a default
    leaking in here would change what every unadorned screenshot photographs.
    """
    assert parse_tab_request("blocks") == TabRequest(tab="blocks", columns=None, debug=False)


@pytest.mark.parametrize("spec", ["colums", "Colums", "docment", "specimen2", "colums:3,debug"])
def test_a_misspelt_tab_name_is_refused_rather_than_ignored(spec: str) -> None:
    """
    The regression for a measured wrong-picture bug, not a hypothetical one.

    T15-shot-tabs ran `scripts/shot.py --tab colums` -- one letter wrong -- and
    got an image **byte-identical** to `--tab document`: 0 of 2,640,800
    decompressed bytes differed, exit 0, no warning. Nothing validated the name,
    so `App.gui` never matched it and ImGui opened the first tab. A reviewer can
    shoot five tabs, misspell one, and review a photograph of the wrong one.

    The message must name the bad token, for the reason the option test gives:
    a `ValueError` that does not say *which* word was wrong sends the reader back
    to the grammar rather than to their own command line.
    """
    with pytest.raises(ValueError) as caught:
        parse_tab_request(spec)
    assert spec.partition(":")[0] in str(caught.value)


def test_every_name_in_tab_names_is_accepted_in_any_case() -> None:
    """
    The other half, and without it the test above passes for a parser that
    refuses everything. Both cases, because `App.gui` matches `.lower()`.
    """
    for name in TAB_NAMES:
        assert parse_tab_request(name) == TabRequest(tab=name)
        assert parse_tab_request(name.lower()) == TabRequest(tab=name.lower())
        assert parse_tab_request(name.upper() + ":debug").debug is True


def test_the_tab_bar_draws_exactly_the_tabs_tab_names_lists() -> None:
    """
    `TAB_NAMES` is only worth exporting if it is what `gui` actually iterates.

    Read out of the source because `gui` needs a window and this suite may not
    open one (`docs/decisions.md`). That is a coupling of last resort and it is
    narrow on purpose: it checks the *body table*, which is the one place a tab
    can still be added without touching `TAB_NAMES`. The `KeyError` in `gui` --
    `bodies[name]` -- catches the opposite drift on the first frame.

    This replaces nothing: `tests/test_shot_all.py` and `tests/test_run_demo.py`
    both scrape `App.gui` for the same list and can now read `TAB_NAMES` instead.
    """
    source = inspect.getsource(App.gui)
    table = source.partition("bodies = {")[2].partition("}")[0]
    drawn = re.findall(r'"([A-Za-z]+)":', table)
    assert drawn == list(TAB_NAMES), f"gui draws {drawn}, TAB_NAMES says {list(TAB_NAMES)}"


def test_the_app_applies_a_tab_request_on_construction() -> None:
    app = App(source=TINY, columns_source=TINY, open_tab="columns:3,debug")
    assert (app.columns, app.view.debug, app.open_tab) == (3, True, "columns")


def test_a_request_that_names_no_count_leaves_the_apps_default_count() -> None:
    """
    `App.columns` is a field with a default, and a `None` in the request must not
    overwrite it with `None` or with a second copy of the default written here.
    """
    default = App(source=TINY, columns_source=TINY).columns
    assert App(source=TINY, columns_source=TINY, open_tab="columns").columns == default


# ----------------------------------------------------------------------
# Page arithmetic
# ----------------------------------------------------------------------

# Widths chosen to straddle the two regimes `page_for` switches between, which the
# meta-test below verifies rather than assumes. In scaled points: roughly 200 px
# to 3000 px at 96 dpi.
SWEEP = tuple(sp_from_px(width, 96.0) for width in (200.0, 400.0, 700.0, 1100.0, 1500.0, 3000.0))


def test_the_width_sweep_straddles_both_page_regimes(alphabet: Scaled, leading: Scaled) -> None:
    """
    Meta-test on the fixture for every sweep below.

    `page_for` is a `min` between an ideal sheet and the available width. A sweep
    that stayed on one side of it would exercise one branch and the agreement
    tests would pass with the other branch deleted. This asserts both branches are
    reached, so those tests mean what they say.
    """
    sheets = [page_for(width, alphabet=alphabet, leading=leading).width for width in SWEEP]
    clamped = [sheet == width for sheet, width in zip(sheets, SWEEP, strict=True)]
    assert any(clamped), "no width in the sweep is narrow enough to clamp the sheet"
    assert not all(clamped), "no width in the sweep is wide enough to reach the ideal sheet"


@pytest.mark.parametrize("available", SWEEP)
def test_one_column_sets_exactly_the_page_the_document_tab_sets(
    available: Scaled, alphabet: Scaled, leading: Scaled
) -> None:
    """
    `column_page(..., count=1).page` is `page_for`, to the scaled point.

    Equality and not "about the same": the two are separate expressions of the
    same arithmetic, and the whole justification for `ColumnPage` holding a `Page`
    rather than restating its fields is that they cannot drift. A one-scaled-point
    disagreement here would mean the Columns tab at one column sets a measure the
    Document tab does not, and `LayoutCache` would then miss on every block
    between the two tabs for a difference no one could see.
    """
    cut = column_page(available, alphabet=alphabet, leading=leading, count=1)
    assert cut.page == page_for(available, alphabet=alphabet, leading=leading)
    assert cut.column_width == cut.page.measure


@pytest.mark.parametrize("available", SWEEP)
@pytest.mark.parametrize("count", COLUMN_COUNTS)
def test_every_column_lands_inside_the_sheets_right_margin(
    available: Scaled, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    The last column ends at or before the text block's right edge, at every count.

    This is the property a reader sees: a column running past the margin is text
    touching the edge of the paper, which is the defect the page geometry exists
    to remove. Checked at the last column because the columns are laid out left to
    right and only the last one can overrun.
    """
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    right = cut.page.text_offset + cut.page.measure
    assert cut.column_offset(count - 1) + cut.column_width <= right
    assert cut.column_offset(0) == cut.page.text_offset


@pytest.mark.parametrize("available", SWEEP)
@pytest.mark.parametrize("count", COLUMN_COUNTS)
def test_the_columns_and_gutters_use_all_but_a_rounding_crumb_of_the_text_block(
    available: Scaled, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    Nothing is left over except the floor-division remainder.

    The bound is `count` scaled points -- a scaled point is 1/65536 of a printer's
    point, so this is slack no display can resolve. A looser bound would pass with
    a gutter counted twice or a column dropped.
    """
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    used = cut.column_width * count + cut.gutter * (count - 1)
    assert 0 <= cut.page.measure - used < count


def test_more_columns_buy_a_wider_sheet_when_the_window_can_afford_it(
    alphabet: Scaled, leading: Scaled
) -> None:
    """
    At a width past the ideal, the sheet grows with the count and the measure holds.

    This is the design claim `column_page` makes: a second column is a second
    comfortable measure beside the first, not the first one cut in half. Checked at
    a width wide enough that nothing is clamped -- asserted, not assumed.
    """
    wide = alphabet * 12
    cuts = [column_page(wide, alphabet=alphabet, leading=leading, count=n) for n in COLUMN_COUNTS]
    assert all(cut.page.width < wide for cut in cuts), "the sweep width clamps; widen it"
    assert [cut.page.width for cut in cuts] == sorted(cut.page.width for cut in cuts)
    # Every column is the same measure the single-column page sets, to within the
    # gutter's own rounding.
    one = cuts[0].column_width
    assert all(abs(cut.column_width - one) <= cut.count for cut in cuts)


def test_more_columns_share_a_fixed_sheet_once_the_window_bites(
    alphabet: Scaled, leading: Scaled
) -> None:
    """
    At a width the ideal sheet cannot have, the sheet stops growing and the columns
    get narrower instead. That is the regime a reader is in when they drag the
    window in, and the one that makes the reflow visible.
    """
    narrow = alphabet * 3
    cuts = [column_page(narrow, alphabet=alphabet, leading=leading, count=n) for n in COLUMN_COUNTS]
    assert all(cut.page.width == narrow for cut in cuts), "the width does not clamp; narrow it"
    widths = [cut.column_width for cut in cuts]
    assert widths == sorted(widths, reverse=True)
    assert widths[0] > widths[-1]


@pytest.mark.parametrize("count", (2, 3))
def test_a_gutter_rule_sits_strictly_between_the_two_columns_it_separates(
    count: int, alphabet: Scaled, leading: Scaled
) -> None:
    cut = column_page(alphabet * 12, alphabet=alphabet, leading=leading, count=count)
    for index in range(count - 1):
        left = cut.column_offset(index) + cut.column_width
        right = cut.column_offset(index + 1)
        assert left < cut.rule_offset(index) < right


def test_out_of_range_columns_and_gutters_raise(alphabet: Scaled, leading: Scaled) -> None:
    cut = column_page(alphabet * 12, alphabet=alphabet, leading=leading, count=2)
    for bad in (-1, 2):
        with pytest.raises(IndexError):
            cut.column_offset(bad)
    for bad in (-1, 1):
        with pytest.raises(IndexError):
            cut.rule_offset(bad)


def test_a_column_count_below_one_is_refused(alphabet: Scaled, leading: Scaled) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        column_page(alphabet * 12, alphabet=alphabet, leading=leading, count=0)


# -- the margin in the clamped branch ------------------------------------
#
# T7-look found the Columns tab setting a measure far under this project's own
# floor and traced it to the margin: `min(available, ideal_sheet)` clamps the
# sheet, and a margin taken as a flat sixth of the clamped sheet makes the text
# block pay the whole shortfall. Everything below is about the *clamped* branch,
# because a test at an unclamped width passes against the old code and covers
# nothing -- which is precisely how this shipped.

# (content region px, column count) pairs that clamp, and only those.
#
# Clamping is per-count, not per-width, and getting that wrong is the easiest way
# to write a vacuous test here: the ideal sheet is 700 px at one column, 1433 at
# two and 2166 at three, so 1600 px clamps three columns and does not clamp two.
# `test_the_clamped_widths_really_are_clamped` checks every pair rather than
# trusting this comment. 1070 is the demo window's content region; 1890 is the
# widest this 1920 px display can give; 500 is a window dragged in far enough to
# clamp even one column.
CLAMPED_PAIRS = (
    (500.0, 1),
    (500.0, 2),
    (500.0, 3),
    (1070.0, 2),
    (1070.0, 3),
    (1370.0, 2),
    (1370.0, 3),
    (1600.0, 3),
    (1890.0, 3),
)


def _old_margin(sheet: Scaled) -> Scaled:
    """
    The margin rule as it stood before `text_margin`: a flat sixth of the sheet.

    Kept here rather than described, so the improvement tests compare against
    something executable. If `TEXT_BLOCK_FRACTION` moves, this moves with it and
    the comparison stays honest.
    """
    return round(sheet * (1.0 - TEXT_BLOCK_FRACTION) / 2.0)


@pytest.mark.parametrize(("width_px", "count"), CLAMPED_PAIRS)
def test_the_clamped_widths_really_are_clamped(
    width_px: float, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    Meta-test on `CLAMPED_PAIRS`, and the one this whole section stands on.

    The defect lives only where the sheet cannot have its ideal width. A pair
    that turned out to be unclamped would make every assertion below a statement
    about code that did not change.
    """
    available = sp_from_px(width_px, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    assert cut.page.width == available, f"{width_px}px does not clamp {count} columns"


def test_the_clamped_pairs_cover_every_column_count_the_tab_offers(
    alphabet: Scaled, leading: Scaled
) -> None:
    """
    And they reach all three counts, so no count's clamped branch is untested.
    """
    assert {count for _, count in CLAMPED_PAIRS} == set(COLUMN_COUNTS)


@pytest.mark.parametrize(("width_px", "count"), CLAMPED_PAIRS)
def test_a_clamped_sheet_gives_the_columns_their_measure_before_it_takes_a_margin(
    width_px: float, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    The invariant, stated as the exhaustive alternative it is.

    On a clamped sheet the margin is `max(floor, surplus)` bounded above by the
    canon, and in that branch the canon never binds. So exactly one of two things
    is true at every clamped width, and there is no third case to hide in:

    - the columns got the **full** `MEASURE_ALPHABETS` measure, and the margin is
      whatever the sheet had left over; or
    - the margin is already down on its `MIN_MARGIN_LEADINGS` floor, and the
      columns are sharing everything above it.

    An implementation that split the shortfall between margin and measure in any
    other proportion -- the old one splits it entirely onto the measure -- fails
    both arms.
    """
    available = sp_from_px(width_px, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    ideal_column = round(alphabet * MEASURE_ALPHABETS)
    floor = round(leading * MIN_MARGIN_LEADINGS)
    got_its_measure = abs(cut.column_width - ideal_column) <= count
    on_the_floor = cut.page.margin == floor
    assert got_its_measure or on_the_floor, (
        f"{count} columns at {available} sp: measure {cut.column_width} sp "
        f"(wanted {ideal_column}), margin {cut.page.margin} sp (floor {floor})"
    )


def test_both_arms_of_that_invariant_are_actually_reached(
    alphabet: Scaled, leading: Scaled
) -> None:
    """
    Guard against the disjunction above passing for one reason at every width.

    Two arms joined by `or` is a test that one dead arm cannot fail. Both are
    exercised across `CLAMPED_PAIRS`: three columns at 1070 px is on the margin
    floor, and two columns at 1370 px has its full measure.
    """
    ideal_column = round(alphabet * MEASURE_ALPHABETS)
    floor = round(leading * MIN_MARGIN_LEADINGS)
    cuts = [
        column_page(sp_from_px(width_px, 96.0), alphabet=alphabet, leading=leading, count=count)
        for width_px, count in CLAMPED_PAIRS
    ]
    assert any(abs(cut.column_width - ideal_column) <= cut.count for cut in cuts)
    assert any(cut.page.margin == floor for cut in cuts)


@pytest.mark.parametrize(("width_px", "count"), CLAMPED_PAIRS)
def test_the_clamped_measure_is_strictly_wider_than_the_rule_it_replaced(
    width_px: float, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    The change is visible at every clamped width, not on average.

    Executable before-and-after rather than a quoted table: `_old_margin` is the
    rule that shipped, and the sheet is unchanged, so the measure is the only
    thing that can move. At the demo width and three columns this is 223.4 px to
    299.1 px -- 1.08 alphabets to 1.44.
    """
    available = sp_from_px(width_px, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    before = cut.page.width - 2 * _old_margin(cut.page.width)
    assert cut.page.measure > before, (
        f"{count} columns at {width_px}px: the measure did not widen "
        f"({before} sp before, {cut.page.measure} sp after)"
    )


@pytest.mark.parametrize(("width_px", "count"), CLAMPED_PAIRS)
def test_the_clamped_measure_clears_the_project_floor_wherever_the_sheet_can_afford_it(
    width_px: float, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    2.00 alphabets, the bottom of the band `MEASURE_ALPHABETS` derives from Bringhurst.

    **Conditional on purpose, and the condition is arithmetic rather than taste.**
    Three columns at 1070 px cannot reach the floor under any margin rule: three
    floor-width columns, two gutters and two floor-margins want more sheet than
    the window has. So the claim is "wherever it fits, it fits" -- and
    `test_the_floor_condition_is_met_by_some_of_these_widths_and_not_others`
    stops that from being vacuous.

    Where it does not fit, the weaker guarantee still holds and is asserted here:
    the margin is on its floor, so nothing but the window is costing the reader
    characters.
    """
    floor_alphabets = 2.00
    available = sp_from_px(width_px, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    floor_margin = round(leading * MIN_MARGIN_LEADINGS)
    needs = round(alphabet * floor_alphabets) * count + cut.gutter * (count - 1) + 2 * floor_margin
    if cut.page.width >= needs:
        assert cut.column_width / alphabet >= floor_alphabets, (
            f"{count} columns at a {cut.page.width} sp sheet: "
            f"{cut.column_width / alphabet:.2f} alphabets, under the 2.00 floor, "
            f"and the sheet could have afforded it"
        )
    else:
        assert cut.page.margin == floor_margin


def test_the_floor_condition_is_met_by_some_of_these_widths_and_not_others(
    alphabet: Scaled, leading: Scaled
) -> None:
    """
    Meta-test: the guarded assertion above must actually fire, and must not fire
    everywhere. A `needs` that no width met would make it a no-op; one every
    width met would mean the `else` arm is dead.
    """
    floor_margin = round(leading * MIN_MARGIN_LEADINGS)
    fits = []
    for width_px, count in CLAMPED_PAIRS:
        available = sp_from_px(width_px, 96.0)
        cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
        needs = round(alphabet * 2.00) * count + cut.gutter * (count - 1) + 2 * floor_margin
        fits.append(cut.page.width >= needs)
    assert any(fits), "no pair in CLAMPED_PAIRS can afford the floor; the assertion never runs"
    assert not all(fits), "every width affords the floor; the else arm is never taken"


@pytest.mark.parametrize(("width_px", "count"), CLAMPED_PAIRS)
def test_no_clamped_page_is_set_edge_to_edge(
    width_px: float, count: int, alphabet: Scaled, leading: Scaled
) -> None:
    """
    T4-page's defect must not come back through the margin floor.

    Narrowing the margin is the whole change here, and the failure mode it opens
    is narrowing it to nothing -- text flush against the edge of the paper, which
    is what T4 was boarded to fix. Both edges, and the head too.
    """
    available = sp_from_px(width_px, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=count)
    assert cut.page.margin > 0
    assert cut.page.text_offset > 0
    assert cut.page.text_offset + cut.page.measure < available
    assert cut.page.head > 0


def test_the_minimum_margin_covers_the_widest_unbreakable_object_the_demo_ships(
    theme: Theme, measure: object
) -> None:
    """
    `MIN_MARGIN_LEADINGS` is a measurement, and this is the measurement.

    A margin has one duty a proportion cannot express: absorbing material the
    line breaker cannot narrow. `demo/sample.md`'s table is as wide as its
    content. Shipped out at this project's 2.25-alphabet measure, its furthest
    ink lands **61.0 px** past the text block -- 2.82 body leadings -- so three
    leadings is the next whole number that covers it.

    Recomputed from the real file rather than quoted, so a demo document that
    grew a wider table fails here instead of quietly putting ink off the paper.
    Lives in this file and not `tests/test_document_view.py`, where the constant
    does, because the same file already carries the overhang machinery for
    `test_a_table_wider_than_the_measure_still_lands_inside_the_sheet`'s sibling
    claim and this one needs `demo_text`.
    """
    source = demo_text("sample.md")
    assert source is not None, "not a checkout; demo/sample.md is the subject of this test"
    alphabet = alphabet_length(theme, measure)  # type: ignore[arg-type]
    width = round(alphabet * MEASURE_ALPHABETS)
    box = _whole(source, theme, measure, width)
    overhang = (
        max(
            cmd.x + getattr(cmd, "width", 0)
            for cmd in ship(box, Point(0, box.height), measure=measure)  # type: ignore[arg-type]
        )
        - width
    )
    # It really does overhang, or the bound below is a statement about nothing.
    assert overhang > 0, "nothing in demo/sample.md exceeds the measure any more"
    leading = theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
    assert overhang / leading <= MIN_MARGIN_LEADINGS, (
        f"the widest unbreakable object overhangs by {overhang / leading:.2f} leadings, "
        f"more than the {MIN_MARGIN_LEADINGS} the margin floor guarantees"
    )
    # And the floor is not wastefully generous either: one leading less would not
    # cover it. Without this the constant could be raised to anything and pass.
    assert overhang / leading > MIN_MARGIN_LEADINGS - 1.0


def test_the_demo_window_gains_characters_a_line_at_three_columns(
    theme: Theme, measure: object
) -> None:
    """
    The measure, in the unit the reader actually experiences, on the real document.

    Alphabets are the design unit; characters a line are the readability claim,
    and `MEASURE_ALPHABETS` documents that the two do not track each other for
    this face. So this counts glyphs and interword glues on the full-measure
    lines `demo/columns.md` breaks to, at the demo window's 1070 px content
    region, three columns, before and after.

        before   1.08 alphabets, mean 28.9 characters
        after    1.44 alphabets, mean 39.2 characters

    Bringhurst's band is 45 to 75 and this still does not reach it -- 1070 px
    cannot hold three comfortable columns and no margin rule changes that. What
    the test pins is that the margin stopped taking characters the reader needed.
    """
    source = demo_text("columns.md")
    assert source is not None, "not a checkout; demo/columns.md is the subject of this test"
    alphabet = alphabet_length(theme, measure)  # type: ignore[arg-type]
    leading = theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
    available = sp_from_px(1070.0, 96.0)
    cut = column_page(available, alphabet=alphabet, leading=leading, count=3)
    before_width = (cut.page.width - 2 * _old_margin(cut.page.width) - 2 * cut.gutter) // 3

    def characters(width: Scaled) -> list[int]:
        box = _whole(source, theme, measure, width)
        counts = []
        for line in _hboxes(box):
            # Width alone is not enough to identify a line. Every vlist -- the
            # document's own included -- is also exactly the measure wide, and
            # its children are interline `Glue`, so a width-only filter counts
            # the baselineskips of the whole document as one very long line. It
            # put the "before" mean at 30.0 against a measured 28.9 until the
            # `CharNode` test was added.
            if line.width != width or not any(isinstance(n, CharNode) for n in line.contents):
                continue
            filled = sum(1 for n in line.contents if isinstance(n, (CharNode, Glue)))
            if filled > 5:
                counts.append(filled)
        assert counts, f"no full-measure line at {width} sp; the crop found nothing"
        return counts

    before = statistics.mean(characters(before_width))
    after = statistics.mean(characters(cut.column_width))
    assert before == pytest.approx(28.9, abs=0.5), f"the before figure moved: {before:.1f}"
    assert after == pytest.approx(39.2, abs=0.5), f"the after figure moved: {after:.1f}"
    assert after > before


def _hboxes(box: Box) -> list[Box]:
    """
    Every box under `box`, itself included, flattened.

    A line is an `hpack`ed `Box` whose width is exactly the measure; the caller
    filters on that. Recursive because a paragraph's lines sit under a vlist that
    sits under the document's own vlist.
    """
    found = [box]
    for node in box.contents:
        if isinstance(node, Box):
            found.extend(_hboxes(node))
    return found


def test_a_plate_deepens_the_head_and_changes_nothing_else() -> None:
    """
    `_plate` is the Formula and Blocks tabs' only departure from the document page.

    Asserting the *rest* of the page is untouched, not just that the head grew: a
    plate that also moved the sheet would put the formula on a page in a different
    place from the document's, which is exactly what one shared geometry is for.
    """
    page = Page(offset=100, width=900, margin=150, head=12)
    plate = _plate(page)
    assert plate.head == page.head * PLATE_HEADS
    assert (plate.offset, plate.width, plate.margin) == (page.offset, page.width, page.margin)
    assert plate.measure == page.measure


# ----------------------------------------------------------------------
# Page-count estimation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("material", "height", "count", "expected"),
    [
        (0, 100, 1, 1),
        (1, 100, 1, 2),  # ceil(0.01) = 1, plus the slack page
        (100, 100, 1, 2),
        (101, 100, 1, 3),
        (600, 100, 3, 3),  # ceil(600 / 300) = 2, plus one
        (100, 100, 3, 2),
    ],
)
def test_the_page_estimate_is_the_ceiling_plus_one_page_of_slack(
    material: Scaled, height: Scaled, count: int, expected: int
) -> None:
    """
    The slack page is deliberate and is the thing worth pinning.

    `advtext.columns` documents that a block boundary is not a legal breakpoint, so
    a column holds less than its height and an exact ceiling under-counts. The
    cases above include an exact multiple (600 over 3 x 100), which is where a
    ceiling with no slack and a ceiling with slack differ by a whole page.
    """
    assert _column_pages(material, height, count) == expected


def test_the_page_estimate_is_bounded_however_absurd_the_material() -> None:
    assert _column_pages(10**9, 1, 1) == MAX_COLUMN_PAGES


# ----------------------------------------------------------------------
# The split, through the app
# ----------------------------------------------------------------------

COLUMN_CASES = [(1, 400.0), (2, 300.0), (3, 220.0)]


@pytest.fixture(scope="module")
def flowing_baseline(theme: Theme, measure: object) -> dict[float, list[int]]:
    """
    `FLOWING` composed in one piece at each case's measure, shipped, as codepoints.

    Computed once for the whole module: composition is the expensive half -- 0.6 s
    for `demo/columns.md` at a narrow measure -- and this fixture is the same
    document at three widths.
    """
    out: dict[float, list[int]] = {}
    for _, width_px in COLUMN_CASES:
        width = sp_from_px(width_px, 96.0)
        box = _whole(FLOWING, theme, measure, width)
        out[width_px] = _glyphs(tuple(ship(box, Point(0, box.height), measure=measure)))  # type: ignore[arg-type]
    return out


@pytest.mark.parametrize(("count", "width_px"), COLUMN_CASES)
def test_every_glyph_survives_the_split_in_reading_order(
    count: int,
    width_px: float,
    flowing_app: App,
    flowing_baseline: dict[float, list[int]],
) -> None:
    """
    Concatenate the columns and you get the single-column document, exactly.

    Nothing dropped, nothing repeated, nothing out of order. That is the whole
    claim of the Columns tab -- "text continues from the foot of one column to the
    head of the next" -- reduced to something a test can hold, and it is the one
    claim on this tab that no screenshot can check: a reader looking at a page
    cannot see a paragraph that is missing from it.

    The comparison is against the same document composed at the *same measure*, so
    line breaking is held constant and only the split is under test.
    """
    width = sp_from_px(width_px, 96.0)
    layout = flowing_app.column_layout(width, sp_from_px(240.0, 96.0), count)
    flowed: list[int] = []
    for index in layout.indexes:
        flowed.extend(_glyphs(index.cmds))
    assert flowed == flowing_baseline[width_px]
    assert layout.overflow == 0


@pytest.mark.parametrize(("count", "width_px"), COLUMN_CASES)
def test_the_conservation_fixture_really_does_fill_more_than_one_column(
    count: int, width_px: float, flowing_app: App
) -> None:
    """
    Meta-test on the fixture the test above depends on.

    Conservation across a split of a document that all fits in the first column is
    a statement about nothing: the concatenation would equal the whole list because
    the first column *is* the whole list. `docs/status.md` section 5 records three
    families of tests in this tree that failed exactly this way, and the house rule
    it draws out is to attack the fixture. So: at least two columns must carry
    glyphs, and the last one must carry fewer than the first, which is what a
    document that ran out partway through the final column looks like.
    """
    layout = flowing_app.column_layout(sp_from_px(width_px, 96.0), sp_from_px(240.0, 96.0), count)
    per_column = [len(_glyphs(index.cmds)) for index in layout.indexes]
    assert sum(1 for n in per_column if n) >= 2, f"only one column has glyphs: {per_column}"
    assert per_column[-1] < per_column[0], f"the last column is not a remainder: {per_column}"


def test_the_layout_cache_returns_the_same_object_for_the_same_key(flowing_app: App) -> None:
    """
    `is`, not `==`. Two equal layouts built twice would pass an equality check and
    would still mean the cache never served anything -- which is precisely how
    three of this project's five cache-key tests came to be vacuous
    (`docs/status.md` section 5).
    """
    width, height = sp_from_px(300.0, 96.0), sp_from_px(240.0, 96.0)
    first = flowing_app.column_layout(width, height, 2)
    assert flowing_app.column_layout(width, height, 2) is first


@pytest.mark.parametrize("changed", ["width", "height", "count"])
def test_changing_any_part_of_the_key_rebuilds_the_layout(flowing_app: App, changed: str) -> None:
    """
    Ablation on the cache key, one component at a time.

    Each of the three is varied on its own; if any were missing from the key, the
    corresponding case would come back with the previous layout and fail. Varying
    them together would pass with a key of only one.
    """
    width, height, count = sp_from_px(300.0, 96.0), sp_from_px(240.0, 96.0), 2
    first = flowing_app.column_layout(width, height, count)
    if changed == "width":
        width += sp_from_px(37.0, 96.0)
    elif changed == "height":
        height += sp_from_px(37.0, 96.0)
    else:
        count = 3
    second = flowing_app.column_layout(width, height, count)
    assert second is not first
    assert second.key == (width, height, count)


@pytest.mark.parametrize(("count", "width_px"), COLUMN_CASES)
def test_the_last_page_is_never_a_blank_sheet(
    count: int, width_px: float, flowing_app: App
) -> None:
    """
    `_column_pages` asks for a page of slack it usually does not need, and the
    trim in `column_layout` is what stops that slack from being drawn.

    Without the trim the tab paints an entirely empty sheet below the last one
    with real text on it -- correct, conserving, and unmistakably a bug to anyone
    looking at the window. The check is on the *first* column of the last page,
    because a partly-filled last page is what the foot of a document looks like
    and is not a defect.
    """
    layout = flowing_app.column_layout(sp_from_px(width_px, 96.0), sp_from_px(240.0, 96.0), count)
    assert len(layout.indexes) == layout.pages * layout.count
    first_of_last = layout.indexes[(layout.pages - 1) * layout.count]
    assert _glyphs(first_of_last.cmds), f"page {layout.pages} of {layout.pages} is blank"


def test_a_full_cycle_of_the_column_control_warms_up_instead_of_evicting_itself() -> None:
    """
    Visit every count once, then again, and the second lap must be all cache hits.

    `LayoutCache` retains per pass key and a measure is part of that key, so each
    button on the column control is a key of its own. Its default capacity is two
    and the control has three, which means the default evicts the least recently
    used count on every lap and the tab never warms up -- measured at 448/535/937
    ms a lap against 19/20/22 ms once all three are resident.

    Behavioural rather than `assert resident_passes == 3`: that assertion would
    pass with the cache wired to nothing, and would say nothing about whether
    `column_layout` actually goes through it. Counting misses on the second lap
    is the claim. The first lap is not asserted on, because a cold miss per block
    is correct and is not what this is about.
    """
    app = App(source=TINY, columns_source=FLOWING)
    height = sp_from_px(240.0, 96.0)
    laps = [(1, 420.0), (2, 300.0), (3, 220.0)]
    for count, width_px in laps:
        app.column_layout(sp_from_px(width_px, 96.0), height, count)
    before = app._columns_blocks.stats().misses
    for count, width_px in laps:
        app._columns_layout = None  # force the split again; the block cache stands
        app.column_layout(sp_from_px(width_px, 96.0), height, count)
    after = app._columns_blocks.stats()
    assert after.misses == before, (
        f"the second lap missed {after.misses - before} time(s): the cache holds "
        f"fewer passes than the control has counts"
    )
    assert after.hits > 0, "the second lap did not consult the cache at all"


def test_the_real_columns_document_fits_in_the_pages_the_tab_gives_it(theme: Theme) -> None:
    """
    `demo/columns.md`, the document the tab actually ships, at three columns.

    Separate from the synthetic fixture because the estimate-plus-slack page count
    is a claim about *real* material: the synthetic document is eight uniform
    paragraphs and cannot produce the long unbreakable run that would exhaust the
    slack. Skipped rather than failed when the file is absent, which is what an
    installed wheel looks like.
    """
    source = demo_text("columns.md")
    if source is None:  # pragma: no cover - only outside a checkout
        pytest.skip("demo/columns.md is not present, so this is not a checkout")
    app = App(source=TINY, columns_source=source)
    layout = app.column_layout(sp_from_px(280.0, 96.0), sp_from_px(700.0, 96.0), 3)
    assert layout.overflow == 0
    assert layout.pages >= 1
    assert len(layout.indexes) == layout.pages * 3


def test_a_missing_demo_file_is_absent_rather_than_fatal() -> None:
    assert demo_text("no-such-document.md") is None


# ----------------------------------------------------------------------
# The formula cache and the colour conversion
# ----------------------------------------------------------------------


def test_the_formula_is_repacked_only_when_the_measure_changes(flowing_app: App) -> None:
    width = sp_from_px(600.0, 96.0)
    first = flowing_app.formula_box(width)
    assert flowing_app.formula_box(width) is first
    assert flowing_app.formula_box(width + 1) is not first
    assert flowing_app.formula_box(width + 1).width == width + 1


def test_a_packed_colour_converts_back_to_its_own_channels() -> None:
    """
    `rgba` packs alpha, blue, green, red with the low byte first -- `IM_COL32`'s
    order, which is not RGBA despite the name -- and `_vec4` reads it back.

    The four channel values are deliberately all different. With a grey, or with
    any two channels equal, a red/blue swap -- the exact mistake the byte order
    invites -- would be invisible.
    """
    packed = rgba(0x11, 0x55, 0xAA, 0xFF)
    vec = _vec4(packed)
    # `approx` because `ImVec4` stores single-precision floats and 0x11/255 is not
    # representable in one. The tolerance is 1e-6; the channels here are 0.27 and
    # 0.40 apart, so a swap misses by five orders of magnitude more than the
    # rounding this allows for.
    assert (vec.x, vec.y, vec.z) == pytest.approx(
        (0x11 / 255.0, 0x55 / 255.0, 0xAA / 255.0), abs=1e-6
    )
    assert vec.w == 1.0
    assert _vec4(packed, 0.25).w == 0.25


def test_the_column_page_is_a_page_and_not_a_copy_of_one(alphabet: Scaled, leading: Scaled) -> None:
    """
    A type-level version of the agreement test: `ColumnPage.page` must be the very
    class the document view uses, so a field added to `Page` reaches both tabs.
    """
    cut = column_page(alphabet * 12, alphabet=alphabet, leading=leading, count=2)
    assert isinstance(cut, ColumnPage)
    assert type(cut.page) is Page

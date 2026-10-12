r"""
The demo application's pure parts: the tab grammar, and what the shell holds and hands on.

**What this file can and cannot reach.** `advtext.ui.app` defers every
`imgui_bundle` import into the function that needs it, so the module imports
and most of it runs with no window anywhere. `tests/test_pages.py` drives
`gui` through frames of a context with no backend and once through a real
window; `tests/test_app_typeset.py` has the fonts. This file stays with the
parts that need neither.

**What left this file on 2026-10-11 (tranche 5, T5-APP).** Until then two
thirds of it was the Columns page's arithmetic and caches, which lived on
`App` and were built on advtext's own layout core: `column_page` against
`document_view.page_for`, the page estimate, the split through
`advtext.columns` (glyph conservation, the cached layout, the block cache's
laps), `_plate`, and the formula box. `App` holds none of that now: columns
are the imtypeset core's (`Document.set_columns`; the Columns page and
`tests/test_page_columns.py` are where they are tested), and the tests of the
removed members went with them. What they established about `advtext.columns`
itself is still held by `tests/test_columns.py` for as long as that module is
in the tree.
"""

from __future__ import annotations

import dataclasses
import inspect
import re

import pytest

from advtext.ui.app import (
    TAB_NAMES,
    App,
    TabRequest,
    _vec4,
    demo_text,
    parse_tab_request,
    sidebar_rows,
)
from advtext.ui.palette import rgba

TINY = "# t\n\nOne short paragraph.\n"


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
    assert parse_tab_request("formula") == TabRequest(tab="formula", columns=None, debug=False)


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


def test_the_sidebar_lists_exactly_the_pages_tab_names_lists() -> None:
    """
    `TAB_NAMES` is only worth exporting if it is what `gui` actually draws.

    This used to read the tab bar's body table out of `App.gui`'s source,
    because the names were literals there and `gui` needs a frame. The tab bar
    became a sidebar and the names are no longer written anywhere: `gui` draws
    `sidebar_rows(self.discovery)`, the scan of `advtext.ui.pages`, and
    `TAB_NAMES` is computed from the same scan. So the comparison is between
    two values now, not a value and a regular expression, and the other half --
    that `gui` draws those rows and nothing else -- is a real frame in
    `tests/test_pages.py`.

    The second assertion is the old test's structural half, kept: no page name
    is a literal inside `gui`, which is the one place a page could be added
    without being discovered.
    """
    app = App(source=TINY, columns_source=TINY)
    listed = [row.page.name for row in sidebar_rows(app.discovery) if row.page is not None]
    assert listed == list(
        TAB_NAMES
    ), f"the sidebar lists {listed}, TAB_NAMES says {list(TAB_NAMES)}"
    assert list(TAB_NAMES[:4]) == ["Document", "Columns", "Specimen", "Formula"]
    source = inspect.getsource(App.gui) + inspect.getsource(App._sidebar)
    named = [name for name in TAB_NAMES if re.search(rf"\b{name}\b", source)]
    assert not named, f"App.gui names {named} itself instead of drawing what was discovered"


def test_the_app_applies_a_tab_request_on_construction() -> None:
    app = App(source=TINY, columns_source=TINY, open_tab="columns:3,debug")
    assert (app.context.count_for("Columns"), app.context.debug, app.open_tab) == (
        3,
        True,
        "columns",
    )
    assert app.context.options_for("Columns") == ()


def test_a_request_that_names_no_count_hands_the_page_none() -> None:
    """
    The count belongs to the page it was addressed to, and a request without
    one says `None`: the Columns page then uses its own default, which is not
    written here a second time. (It was `App.columns`, a field with a default
    of two, until the Columns page stopped reading the app.)
    """
    assert App(source=TINY, open_tab="columns").context.count_for("Columns") is None
    assert App(source=TINY).context.count_for("Columns") is None
    assert App(source=TINY, open_tab="document:4").context.count_for("Columns") is None


# ----------------------------------------------------------------------
# What the shell holds, and what it hands a page
# ----------------------------------------------------------------------


def test_the_app_holds_the_shell_and_what_the_launch_named_and_nothing_else() -> None:
    """
    The fields of `App`, written out.

    A literal on purpose. Until tranche 5 the app also held a `DocumentView`,
    a glyph measure, and the caches of four pages; a page that wants state
    keeps it on its own object, and a field added here is a decision
    somebody should have to state.
    """
    assert [item.name for item in dataclasses.fields(App)] == [
        "theme",
        "px_per_inch",
        "source",
        "columns_source",
        "open_tab",
        "discovery",
        "context",
        "current",
        "page_errors",
        "_views",
    ]
    for gone in (
        "view",
        "measure",
        "columns",
        "alphabet",
        "page_for_columns",
        "column_layout",
        "columns_document",
        "formula_box",
        "specimen",
        "gallery",
    ):
        assert not hasattr(App, gone), f"App.{gone} is back"


def test_a_page_is_handed_what_the_launch_named_through_the_context() -> None:
    """
    The two sources, the count and the overlay flag reach a page without the page touching the app.
    """
    app = App(source=TINY, columns_source="# columns\n", open_tab="columns:3,debug")
    context = app.context
    assert context.source == TINY and context.columns_source == "# columns\n"
    assert context.count_for("Columns") == 3 and context.count_for("Document") is None
    assert context.debug is True
    assert context.theme is app.theme and context.px_per_inch == app.px_per_inch
    # And the page cannot reach the shell: the context no longer carries it.
    assert not hasattr(context, "app") and not hasattr(context, "measure")

    plain = App(source=TINY)
    assert plain.context.columns_source is None
    assert plain.context.count_for("Columns") is None and plain.context.debug is False


def test_a_missing_demo_file_is_absent_rather_than_fatal() -> None:
    assert demo_text("no-such-document.md") is None


# ----------------------------------------------------------------------
# The colour conversion
# ----------------------------------------------------------------------


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

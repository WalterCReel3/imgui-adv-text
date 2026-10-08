r"""
The demo application: a sidebar of pages, one window, and a theme that stays out of the way.

**This has been executed and photographed.** `scripts/shot.py` drives this
module's own `run` for N frames and grabs the window, and every claim below
about how something *looks* was checked by reading the resulting PNG, taken on
this machine's `DISPLAY=:1`. The module docstring here used to open "Never
executed"; that was true for most of this project's life and is not true now.

Two sentences that stood here are withdrawn. *"`DISPLAY=:1` is live in this
sandbox"*: whether a display is reachable is a fact about the session, and in
the session of 2026-10-06 it was set and unreachable (`socket(AF_UNIX)` was
refused), so every window opened then was on an Xvfb in a user namespace
(`scripts/mouse_probe.py`, `xvfb_command`). *"Nothing in this environment
synthesises a click"*: `scripts/mouse_probe.py` now does, into this app, through
the real `immapp.run` -- eight gestures, eighteen checks on the selection and
the clipboard, all passing in a real window and in a bare context. The events
enter at `ImGuiIO`, not at the X server, and no person has dragged anything.
`App.open_tab` and the grammar `parse_tab_request` implements were built when
nothing could click a tab, and are still how a screenshot selects a page.

**The tab bar is gone; the pages are discovered.** This module used to draw five
tabs out of five methods of `App` and export their names as a tuple. The
navigation is now a list down the left of the window, and what it lists is
whatever `advtext.ui.pages.discover` finds: one module per page under
`advtext/ui/pages/`, each exposing a `PAGE`. `advtext.ui.pages`' docstring is the
contract. The five original tabs are five of those modules, and their frame code
moved there unchanged; what stayed here is what `tests/test_app.py` pins without
a window -- the column geometry and the caches on `App` -- plus the shell: the
sidebar, the request grammar, the chrome, the fonts and `run`. The words "tab"
and `--tab` survive in the grammar and in `TAB_NAMES` because scripts, Makefile
targets and people's fingers already use them; they mean "page".

**This is the demo, and it is no longer the smallest consumer of the library.**
`examples/minimal.py` puts a markdown string in a plain ImGui window through
`import advtext` alone, and a host embeds `advtext.ui.bare_view.BareView` or
`advtext.ui.stream_view.StreamView`, not anything in this module. The page
sheet, the capped measure and the pages are this application's presentation.
`load_fonts` below is a thin caller of `advtext.ui.fonts.load_faces`.

The five original pages, one for each claim that was worth looking at first:

1. **Document** -- the markdown litmus test, laid out on a page and selectable.
   Drag to select, double click for a word, triple for a line, Ctrl+C to copy.
   `advtext.ui.document_view` owns the page geometry and the interaction.
2. **Columns** -- the same material flowed into 1, 2 or 3 newspaper columns by
   `advtext.columns`, text continuing from the foot of one column to the head of
   the next. The column count is a control rather than a constant, because the
   *reflow* is the demonstration: a static two-column render could have been
   faked with two documents.
3. **Specimen** -- every face this project renders, compared side by side, a size
   ladder, and a kerning demonstration. `advtext.ui.specimen` builds it.
4. **Formula** -- eleven formulae (nine until the second build added a radical and a
   sized pair of delimiters), each chosen because it is the only one that makes
   some rule of TeX's math mode visible: the display-size operator as a different
   glyph, the four math styles and where they stop, the inter-atom spacing table
   with and without its classes, and a binary operator that is only binary in
   context. `advtext.ui.formulas` builds it and its docstring has the table.
5. **Blocks** -- `advtext.blocklayout`'s toolbar at three widths, showing that a
   centred item stays centred because two `fil` glues split the surplus evenly.

## One page geometry, applied five times

`advtext.ui.document_view.page_for` decides where the sheet sits and how wide the
text on it is, and it carries the typographic argument for both. Each of the
five goes through it -- `advtext.ui.pages.paint_sheet` is the one place that turns a
`Page` into a filled rectangle and a text-block origin, so a margin cannot be applied to the
document and forgotten on the specimen. `column_page` is the same arithmetic
generalised to N columns and **reduces to `page_for` exactly at N = 1**, which is
what `tests/test_app.py` pins rather than leaving as a comment.

## The theme

`apply_style` is the whole of it: a neutral dark chrome around the light page
that `advtext.backends.imgui_draw.Palette` already argues for. It is restrained
on purpose. The text is the thing being shown and chrome that competes with it is
a regression, so there is no accent on anything that is not interactive, no
rounding on the sidebar's rows, and nothing that draws the eye off the sheet.

Set once from hello_imgui's `setup_imgui_style` callback rather than per frame,
for the reason pptmstr's `theme.apply_style` gives: `ImGuiStyle` is global mutable
state that persists across frames, unlike almost everything else in immediate
mode.

## The display sigma, which used to be the tab that could not work

`advtext.fontlib` mints private-use codepoints for glyphs a font leaves
unencoded, which is how `summation.v1` -- the display-size sigma, a glyph with no
codepoint at all -- is named. ImGui rasterises by Unicode codepoint and knows
nothing of that minting, so this operator did not draw through this backend.

It does now. `load_fonts` registers faces through `advtext.fontlib.
imgui_font_file`, which writes our mappings into a copy of the font's format-12
cmap subtables, and ImGui's own lookup finds the glyph unaided.
`tests/test_imgui_draw.py` pins it without a display, and the Formula tab
photographs it. `DrawStats.missing` is kept and still printed, because it is the
honest report for a face that fails to load.

## Fonts, twice

ImGui rasterises from the same TTF files fontTools measures, and the two know
nothing of each other. So the faces are registered with ImGui separately, in
`load_fonts`, from the paths `advtext.fontlib` resolves -- one place naming the
files, still. Since Dear ImGui 1.92 a face rasterises on demand at any pushed
size (pptmstr relies on this at `pptmstr/theme.py:804-806`), so one `ImFont` per
face at 16.0 is enough and the size is passed per draw call.

**The Specimen tab is the first thing here that leans hard on that**, because its
size ladder asks one face for six sizes in one frame. It holds: the ladder
photographs as six visibly different sizes, which is the observation that would
have failed if ImGui were re-using the baked 16 px raster for all of them.

ImGui's advances and ascents both disagree with the ones we laid out with, by
enough to see. Both are measured -- `scripts/verify_advances.py` and
`scripts/verify_ascent.py`, neither of which needs a display -- and
`advtext.backends.imgui_draw.baked_size_px` applies the correction they agree on.
`docs/imgui-risks.md` lists what is still open, in priority order.

Deliberately out of scope: docking, persistence beyond the ini file, and any
editing.
"""

from __future__ import annotations

import math
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from advtext import fontlib
from advtext.backends.imgui_draw import rgba
from advtext.columns import split_into_columns
from advtext.fontmetrics import Face
from advtext.markdown import Document, build_document
from advtext.math import Style, math_fonts, mlist_to_hlist
from advtext.nodes import Box, Glue, Kern, Node
from advtext.pack import CharMeasure, PackMode, hpack, vpack
from advtext.shipout import Point, ship
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import HSS, CommandIndex, LayoutCache, compose_blocks
from advtext.ui.document_view import (
    MEASURE_ALPHABETS,
    TEXT_BLOCK_FRACTION,
    DocumentView,
    Page,
    alphabet_length,
    text_margin,
)
from advtext.ui.formulas import SUMMATION, Gallery, build_gallery
from advtext.ui.pages import (
    DEMO_DIR,
    PLATE_HEADS,
    SHARED_OPTION,
    Discovery,
    Failure,
    PageContext,
    PageSpec,
    PageView,
    caption,
    demo_text,
    discover,
    is_count,
    plate,
    split_options,
)
from advtext.ui.specimen import Specimen, build_specimen
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "COLUMN_COUNTS",
    "DEFAULT_MARKDOWN",
    "DEMO_DIR",
    "GUTTER_LEADINGS",
    "PLATE_HEADS",
    "SIDEBAR_WIDTH_PX",
    "WINDOW_SIZE",
    "App",
    "ColumnPage",
    "Failure",
    "PageError",
    "SidebarRow",
    "TabRequest",
    "apply_style",
    "column_page",
    "demo_text",
    "load_fonts",
    "page_names",
    "parse_tab_request",
    "run",
    "sidebar_rows",
]

WINDOW_TITLE = "advtext"

SIDEBAR_WIDTH_PX: Final = 188.0
"""
The width of the navigation list, in pixels.

Fixed rather than proportional: the list is chrome, and chrome that grew with the
window would take width from the page when there is most of it to give. Wide
enough for a two-word label at the default face with the row padding
`apply_style` sets.
"""

WINDOW_SIZE: Final = (1300, 800)
"""
The window `run` opens, in pixels, and what `scripts/shot.py` photographs by default.

**1300 and not the 1100 it was, so that the page body is the width it was.** The
sidebar costs `SIDEBAR_WIDTH_PX` plus one `item_spacing.x` (12 px, `apply_style`)
between it and the body: 200 px. Under the tab bar the body was the window less
its padding, 1100 - 2 x 16 = 1068 px; at 1300 it is 1068 px again, so every page
sets the sheet it set before. The height is unchanged at 800, which makes the
body *taller* than it was by the tab bar's row, since nothing sits above a page
now.
"""


def _clip_depth(draw_list: Any) -> int | None:
    """
    How many clip rectangles are pushed on a draw list, or `None` if this
    binding does not expose the stack (`ImDrawList::_ClipRectStack`).
    """
    stack = getattr(draw_list, "_clip_rect_stack", None)
    try:
        return len(stack) if stack is not None else None
    except TypeError:
        return None


class PageError(RuntimeError):
    """
    Raised by `run` after the window has closed, if a page raised while it was open.

    The exception was caught for the window's sake (`App._draw_page`) and is
    not swallowed for the process's: a screenshot, a tour or a probe of a
    broken page exits non-zero, and the message is every failed page's
    traceback.
    """

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = dict(errors)
        names = ", ".join(self.errors)
        super().__init__(
            f"page(s) raised while drawing: {names}\n\n" + "\n".join(self.errors.values())
        )


def page_names() -> tuple[str, ...]:
    """
    The name of every discovered page, in sidebar order.

    What `--tab` accepts, case-insensitively. Read by scanning
    `advtext.ui.pages`, so there is no list here to keep.
    """
    return tuple(page.name for page in discover().pages)


def __getattr__(name: str) -> object:
    """
    `TAB_NAMES`, computed when asked for.

    It was a literal tuple of five names, "the single copy of this list", after
    three hand-kept copies had drifted (`Makefile`, `scripts/run_demo.py`,
    `scripts/shot.py`; `tests/test_shot_all.py` has the account). The pages are
    now discovered, so the single copy is the directory listing and this is a
    view of it: `scripts/visual_diff.py` and the tests that import the name keep
    working and now see a page the day its module lands. A module attribute
    cannot be computed at import here -- the page modules import this one --
    hence the hook, and hence its absence from `__all__`, which may only name
    what the module defines statically. New code should call `page_names()`.
    """
    if name == "TAB_NAMES":
        return page_names()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


COLUMN_COUNTS: Final = (1, 2, 3)
"""
The column counts the tab offers as buttons.

Not a bound on the engine -- `advtext.columns.split_into_columns` takes any count
of at least one, and `parse_tab_request` will accept any -- but the counts a
newspaper uses at a window's width, and the ones the user asked about.
"""

GUTTER_LEADINGS: Final = 1.0
"""
The gutter between two columns, as a multiple of the body leading.

A gutter has one job: make the return sweep land in the same column it started
in. Bringhurst's rule (`The Elements of Typographic Style` 2.2.2) is that the
space between columns should be visibly larger than the word space inside them,
and that a gutter near the leading is the safe default because it puts the
horizontal gap and the vertical one on the same scale -- the page then reads as a
grid rather than as text with slots cut in it.

Expressed against the leading rather than in points for the reason
`TEXT_BLOCK_FRACTION` is a proportion: the leading is *measured* from the theme,
so a larger body size widens the gutter by exactly as much as it widens the line.
"""

MAX_COLUMN_PAGES: Final = 24
"""
How many column pages the tab will lay out before it gives up and says so.

A bound rather than a belief. The page count is derived from the material's own
height, so it is right for every document the demo ships; this stops a caller who
points the tab at a book, in a window eighty pixels tall, from composing four
thousand columns inside one frame.
"""

PAGE_GAP_PX: Final = 28.0
"""
The dark band between one column page and the next, in pixels.

Wide enough to read as a gap between two sheets rather than as a rule. A page
break in a scroll needs to be unmistakable: the reader has to know that the text
at the top of the next sheet follows the foot of the *last* column above it and
not the foot of the first.
"""

COLUMN_RULE = rgba(0x11, 0x11, 0x11, 0x38)
"""
The hairline down the middle of a gutter: the page's ink, at 22% alpha.

Derived from `Palette.ink` rather than picked, because it sits on `Palette.page`
and has to belong to the same pair. Faint on purpose -- a full-strength rule
between columns reads as a table.
"""

# Used when neither a source nor `demo/sample.md` is available. Short on purpose:
# `demo/` is not shipped inside the wheel, so this is what an installed copy of
# the package shows, and it should say what the project is rather than be long.
DEFAULT_MARKDOWN = """\
# advtext

A text layout engine for Dear ImGui that borrows **TeX's model**: a document is a
tree of *boxes*, *glue*, *kerns* and *penalties*, packed by `hpack` and `vpack`,
broken into lines by a total-fit algorithm over badness and demerits, and shipped
out as absolute glyph positions.

Because every glyph position is computed here rather than inside a widget, hit
testing is arithmetic over data we already have. That is why this text is
selectable and ImGui's own is not.

- Drag to select, and drag backwards too.
- Double click for a word, triple click for a line.
- Ctrl+C copies the selection.

> Selection is the point. It is a gap in ImGui only because the widget owns the
> layout.
"""

# `DEMO_DIR` and `demo_text` live in `advtext.ui.pages` now, where a page can
# reach them without importing this module; they are re-exported above.


# ----------------------------------------------------------------------
# What a screenshot can ask for
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TabRequest:
    """
    A page to open on the first frame, and the state to open it in.

    Every field is `None`-or-default-meaning-"leave it alone", so a request can
    name a page without disturbing the column count and vice versa.

    `options` are the words that are the named page's own (`PageSpec.options`),
    in the order given. `debug` and the integer are not among them: every page
    accepts those two and they keep the fields they always had.
    """

    tab: str | None = None
    columns: int | None = None
    debug: bool = False
    options: tuple[str, ...] = ()


def _check_tab_name(spec: str, name: str, found: Discovery) -> PageSpec | None:
    """
    The page `name` addresses, refusing a name that is no page and naming the ones that are.

    An empty name is allowed and means "leave the page alone": `parse_tab_request`
    maps it to `TabRequest(tab=None)`, and `:debug` with no name in front of it
    is a legitimate way to ask for the overlay on whatever opens.
    """
    if not name:
        return None
    page = found.find(name)
    if page is not None:
        return page
    broken = ""
    if found.failures:
        broken = (
            " (Not loaded, and so not among them: "
            + "; ".join(f"{failure.module} -- {failure.reason}" for failure in found.failures)
            + ".)"
        )
    raise ValueError(
        f"{spec!r}: {name!r} is not a tab. "
        f"The tabs are {', '.join(page.name for page in found.pages)} -- case does not "
        f"matter.{broken} "
        "Refused rather than ignored because an unmatched name opens the first "
        "page, which is a photograph of the wrong thing under a filename that "
        "claims otherwise."
    )


def parse_tab_request(spec: str | None, found: Discovery | None = None) -> TabRequest:
    """
    Parse `NAME[:OPTION[,OPTION...]]`, the grammar a screenshot addresses a page with.

    Built when nothing could click a control, so that a page whose interesting
    states are only reachable by clicking could still be photographed in them:

        document            the Document page, as it opens
        document:debug      ... with the debug overlay on
        columns:3           the Columns page, at three columns
        columns:3,debug     ... and the overlay

    An option is an integer of 1 or more (the column count; any page may read it
    through `PageContext.count_for`), the word `debug`, or one of the words the
    named page declares in `PageSpec.options`. Anything else raises `ValueError`
    **before the window opens**: a misspelt option that silently did nothing
    would produce a photograph of the default state under a filename claiming
    otherwise, and a wrong picture is worse than a refusal.

    **The name is held to the same standard, and it was not always.** A name
    that is not a discovered page raises here, case-insensitively as `App.gui`
    matches it. Before this, an unknown name simply never matched, ImGui opened
    the first tab, and `--tab colums` produced an image byte-identical to
    `--tab document` at exit 0 -- the exact failure the paragraph above refuses
    for options, going unrefused for the thing the option is attached to.

    `found` is a scan the caller already has; without it the pages are scanned
    here, which imports every page module.
    """
    if spec is None:
        return TabRequest()
    if found is None:
        found = discover()
    name, separator, rest = spec.partition(":")
    page = _check_tab_name(spec, name, found)
    if not separator:
        return TabRequest(tab=name or None)

    columns: int | None = None
    debug = False
    words: list[str] = []
    for option in split_options(rest) or ("",):
        if option == SHARED_OPTION:
            debug = True
        elif is_count(option):
            columns = int(option)
        elif page is not None and option in page.options:
            words.append(option)
        else:
            own = (
                f" {page.name} also takes {', '.join(repr(word) for word in page.options)}."
                if page is not None and page.options
                else ""
            )
            raise ValueError(
                f"{spec!r}: {option!r} is not a tab option. "
                "Options are 'debug' or a column count of 1 or more, "
                f"comma separated, after a colon -- for instance 'columns:3,debug'.{own}"
            )
    return TabRequest(tab=name or None, columns=columns, debug=debug, options=tuple(words))


@dataclass(frozen=True, slots=True)
class SidebarRow:
    """
    One line of the navigation list: a group heading, a page, or a module that failed.

    A value and not a draw call so the list can be checked without a frame:
    `sidebar_rows` is pure, and `App._sidebar` draws exactly what it returns.
    """

    kind: str
    """`"heading"`, `"page"` or `"failure"`."""
    text: str
    page: PageSpec | None = None
    detail: str = ""


def sidebar_rows(found: Discovery) -> tuple[SidebarRow, ...]:
    """
    The navigation list for a scan, top to bottom.

    Pages are in `Discovery.pages`' order, which is `(order, name)`. A heading
    is emitted whenever the group changes from one page to the next, so pages
    of one group that are not adjacent in that order get the heading twice --
    which is visible, and is how a page whose `order` strays into another
    group's range gets noticed. Modules that could not be loaded come last,
    under their own heading, with the reason as the row's detail.
    """
    rows: list[SidebarRow] = []
    group: str | None = None
    for page in found.pages:
        if page.group != group:
            group = page.group
            if group:
                rows.append(SidebarRow("heading", group))
        rows.append(SidebarRow("page", page.label, page, page.caption))
    if found.failures:
        rows.append(SidebarRow("heading", "failed to load"))
        for failure in found.failures:
            rows.append(
                SidebarRow("failure", failure.module.rpartition(".")[2], None, failure.reason)
            )
    return tuple(rows)


# ----------------------------------------------------------------------
# Page geometry for N columns
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ColumnPage:
    """
    A sheet cut into `count` columns: where each one starts, and how wide it is.

    Holds a `Page` rather than restating it. That is not tidiness -- it is what
    makes "the Columns tab at one column sets exactly the page the Document tab
    does" a fact about this type instead of a coincidence between two copies of
    the same arithmetic.

    Everything is in scaled points measured from the left edge of the content
    region, like `Page`, so none of it knows about pixels or about ImGui.
    """

    page: Page
    count: int
    gutter: Scaled

    @property
    def column_width(self) -> Scaled:
        """
        One column's measure: the text block, less the gutters, divided up.

        Floor division, so `count` columns and `count - 1` gutters always fit
        inside the text block with at most `count - 1` scaled points of slack.
        Handing the remainder to one column would make that column wider than its
        neighbours by an amount no reader could see and every test would have to
        special-case.
        """
        return (self.page.measure - self.gutter * (self.count - 1)) // self.count

    def column_offset(self, index: int) -> Scaled:
        """
        From the content region's left edge to column `index`'s left edge.
        """
        if not 0 <= index < self.count:
            raise IndexError(f"column {index} of {self.count}")
        return self.page.text_offset + index * (self.column_width + self.gutter)

    def rule_offset(self, index: int) -> Scaled:
        """
        The middle of the gutter that follows column `index`, where the rule goes.

        `index` runs to `count - 2`: there is one gutter fewer than there are
        columns, and a rule after the last column would be a rule in the margin.
        """
        if not 0 <= index < self.count - 1:
            raise IndexError(f"gutter {index} of {self.count - 1}")
        return self.column_offset(index) + self.column_width + self.gutter // 2


def column_page(available: Scaled, *, alphabet: Scaled, leading: Scaled, count: int) -> ColumnPage:
    """
    The sheet for `count` columns in a content region of this width.

    `advtext.ui.document_view.page_for`, generalised. The ideal sheet is no longer
    one column of `MEASURE_ALPHABETS` alphabets plus its margins but `count` of
    them plus the gutters between them, and everything else -- the `min` against
    the available width, the centring, the `text_margin` rule -- is unchanged.

    **The margin is `text_margin` and not a flat sixth of the sheet, and this is
    the tab that made that necessary.** More columns want a wider sheet, so the
    Columns tab is in the clamped branch at every count above one on any window
    this display can show; taking the canon's third out of a clamped sheet made
    the columns pay the whole shortfall. Measured on `demo/columns.md` in the
    1100 px demo window, before and after, as a per-column measure in alphabets
    against the 2.00-alphabet floor `MEASURE_ALPHABETS` derives from Bringhurst:

        count   before          after
        1       2.25 / 62.2ch   2.25 / 62.2ch   (unclamped; unchanged)
        2       1.67 / 46.2ch   2.21 / 60.8ch
        3       1.08 / 28.9ch   1.44 / 39.2ch

    Three columns is still under the floor at 1100 px and no margin rule can fix
    that -- three comfortable measures plus two gutters want a 2166 px sheet and
    the window has 1070, so the margin is already down on its floor and the
    columns are sharing what is left. What changed is that the margin no longer
    takes width the text needed more. **At 1600 px all three counts set the full
    2.25 and 62.2 characters**, where before three columns got 1.64 and 45.4:
    once the sheet can afford the ideal text block, the surplus term hands the
    columns their whole measure and the canon keeps only what is over.
    Reproduce with `python /tmp/t18_measure.py`-style code, or read
    `tests/test_app.py::test_the_clamped_three_column_measure_is_not_below_the_
    project_floor`.

    **At `count = 1` this returns exactly what `page_for` returns**, and not
    approximately: the gutter term is multiplied by zero, which leaves the same
    float expression, and every subsequent line is the same line.
    `tests/test_app.py::test_one_column_sets_exactly_the_page_the_document_tab_sets`
    sweeps a range of widths against `page_for` rather than trusting that reading.

    The consequence worth stating is that **more columns make a wider sheet, not
    narrower columns**, until the window runs out. Two columns of the ideal
    measure want a sheet a little over twice as wide as one, so at a window that
    can afford it the reader sees the same comfortable measure twice over, which
    is what a newspaper is. Only once `available` bites do the columns start
    sharing a fixed sheet and getting narrower -- and that is the regime a reader
    sees when they drag the window in, which is the one that makes the reflow
    obvious.
    """
    if count < 1:
        raise ValueError(f"a column count must be at least 1, got {count}")

    gutter = round(leading * GUTTER_LEADINGS)
    ideal_body = alphabet * MEASURE_ALPHABETS * count + gutter * (count - 1)
    ideal_sheet = round(ideal_body / TEXT_BLOCK_FRACTION)
    sheet = min(available, ideal_sheet) if ideal_sheet > 0 else available
    margin = text_margin(sheet, ideal_body=ideal_body, leading=leading)
    page = Page(offset=(available - sheet) // 2, width=sheet, margin=margin, head=leading)
    return ColumnPage(page=page, count=count, gutter=gutter)


# ----------------------------------------------------------------------
# The columns tab's cached layout
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ColumnLayout:
    """
    Everything the Columns tab derives from one (measure, height, count), cached together.

    The three fields at the top are the cache key and are kept beside the result
    for the reason `document_view.Layout` keeps its own width: "the layout is
    stale" should be one comparison against the thing itself rather than three
    fields somewhere else that can drift out of step with it.

    `indexes` is one `CommandIndex` per column, in reading order across pages --
    column *k* of page *p* is `indexes[p * count + k]`. Flat rather than nested
    because that *is* the reading order, and a nested list would let a caller
    iterate it in the wrong one.
    """

    column_width: Scaled
    column_height: Scaled
    count: int
    pages: int
    indexes: tuple[CommandIndex, ...]
    overflow: int

    @property
    def key(self) -> tuple[Scaled, Scaled, int]:
        """
        What this layout is valid for.
        """
        return (self.column_width, self.column_height, self.count)


def _column_pages(material_height: Scaled, column_height: Scaled, count: int) -> int:
    """
    How many pages of `count` columns to ask for, given the material's natural height.

    The ceiling, **plus one page of slack**, because a column holds less than its
    height: `advtext.columns` documents that a block boundary is not a legal
    breakpoint, so every column loses whatever part of the last unbreakable run
    did not fit. That loss is measured at under 3% of a column on
    `demo/sample.md`, and a whole spare page covers a document many times worse
    than that.

    Slack rather than a retry loop on purpose. `split_into_columns` fills columns
    in order, so the first *n* columns of a split into *N* are the same for every
    `N >= n`; asking for one page too many therefore costs one extra `vsplit` per
    spare column -- 0.53 ms for three, measured -- where growing `count` and
    re-splitting would redo the whole cut. Trailing empty columns are dropped by
    the caller, so the slack is invisible unless it is needed.
    """
    per_page = column_height * count
    return min(MAX_COLUMN_PAGES, max(1, math.ceil(material_height / per_page) + 1))


# ----------------------------------------------------------------------


@dataclass(slots=True)
class App:
    """
    The shell, and the material of the five original pages.

    The shell is `discovery` (what the sidebar lists), `current` (the page that
    is showing), `context` (what every page is built from) and the page objects
    themselves, built on first showing and kept.

    The rest is two documents, one document view and three caches, which the
    five original pages draw from. The formula and the block layouts depend only
    on the measure; the specimen depends on the measure; the columns depend on
    the measure, the visible height and the column count. Each is cached against
    exactly what it depends on, and `DocumentView` owns the Document page's own
    cache. A new page keeps its state on its own object, not here.
    """

    theme: Theme = field(default_factory=Theme.build)
    measure: CharMeasure = field(default_factory=lambda: char_measure(fontlib_metrics))
    px_per_inch: float = DEFAULT_PX_PER_INCH
    source: str = DEFAULT_MARKDOWN
    columns_source: str | None = None
    """
    The markdown the Columns tab flows, or `None` to flow `source`.

    A second document because the two tabs want different prose and it is
    dishonest to pretend otherwise: newspaper columns need sustained paragraphs,
    and a document that is 40% headings and tables demonstrates nothing when it is
    cut into three. `run` fills this from `demo/columns.md`.
    """
    columns: int = 2
    """
    How many columns the Columns tab is showing. Two, because one demonstrates
    nothing and three is tight in the default 1100 px window (`run` sets
    1100 x 800; this said 980 px, which is not a size anything in the tree sets).
    """
    open_tab: str | None = None
    """
    A page to select on the first frame, in `parse_tab_request`'s grammar.

    Exists so a screenshot can name the page it wants, and the state it wants
    it in, without clicking for either. After construction it holds the bare
    name; the first frame moves it into `current` and clears it.
    """
    view: DocumentView = field(init=False)
    discovery: Discovery = field(init=False)
    """
    What `advtext.ui.pages.discover` found when this app was built. Scanned
    once: the sidebar is drawn from it every frame.
    """
    context: PageContext = field(init=False)
    current: str | None = field(default=None, init=False)
    """
    The name of the page that is showing; the first in sidebar order until
    `open_tab` or a click says otherwise. `None` only if no page was found.
    """
    page_errors: dict[str, str] = field(default_factory=dict, init=False)
    """
    The traceback of each page whose factory or `draw` raised, by page name.

    A page in here is not built or drawn; its body shows the traceback and a
    button that calls `retry`. Empty in a healthy app, which is what a test
    or `run` checks.
    """
    _views: dict[str, PageView] = field(default_factory=dict, init=False)
    _formula: Box | None = field(default=None, init=False)
    _formula_width: Scaled = field(default=0, init=False)
    _specimen: Specimen | None = field(default=None, init=False)
    _specimen_width: Scaled = field(default=0, init=False)
    _gallery: Gallery | None = field(default=None, init=False)
    _gallery_width: Scaled = field(default=0, init=False)
    _columns_document: Document | None = field(default=None, init=False)
    _columns_layout: ColumnLayout | None = field(default=None, init=False)
    # A cache of its own rather than the view's, and **sized to the column
    # control**. `LayoutCache` retains per pass key, and a pass key includes the
    # measure, so each of `COLUMN_COUNTS` is a separate key: one resident pass per
    # button. The default is two, and at two a viewer cycling 1 - 2 - 3 - 1 evicts
    # the least recently used count every time round and pays a cold reflow for
    # it. **Adding a fourth column count means raising this to four** -- the
    # coupling is the reason the number is not just `len(COLUMN_COUNTS)` written
    # out, which would hide that it is a memory bound as well as a hit rate.
    #
    # Separate from the view's cache rather than shared because the two tabs
    # compose different documents; that was load-bearing before T10 fixed
    # cross-consumer eviction and is now merely tidy.
    _columns_blocks: LayoutCache = field(
        default_factory=lambda: LayoutCache(resident_passes=len(COLUMN_COUNTS)), init=False
    )
    _alphabet: Scaled | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.view = DocumentView(
            document=build_document(self.source, self.theme, fontlib_metrics),
            theme=self.theme,
            measure=self.measure,
            px_per_inch=self.px_per_inch,
        )
        self.discovery = discover()
        request = parse_tab_request(self.open_tab, self.discovery)
        if request.columns is not None:
            self.columns = request.columns
        self.view.debug = request.debug
        self.open_tab = request.tab
        self.context = PageContext(
            theme=self.theme,
            measure=self.measure,
            px_per_inch=self.px_per_inch,
            fonts=_face_font,
            metrics=fontlib_metrics,
            debug=request.debug,
            request_page=request.tab,
            request_options=request.options,
            request_count=request.columns,
            app=self,
        )
        if self.discovery.pages:
            self.current = self.discovery.pages[0].name

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def page(self, name: str) -> PageView:
        """
        The page object for `name` (any case), built on first request and kept.

        Lazy because a factory may parse a document or lay one out, and a demo
        with a dozen pages should not pay for eleven it has not shown. Kept for
        the app's lifetime, which is what makes the object a place for a page
        to hold its state.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        made = self._views.get(spec.name)
        if made is None:
            made = self._views[spec.name] = spec.factory(self.context)
        return made

    def select(self, name: str) -> None:
        """
        Show page `name` (any case) from the next `gui` on. `KeyError` if it is no page.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        self.current = spec.name

    def retry(self, name: str) -> None:
        """
        Forget that page `name` failed, and the page object that did: the next frame builds it anew.

        The object is dropped because an exception partway through a `draw`
        or a constructor leaves no promise about its state.
        """
        spec = self.discovery.find(name)
        if spec is None:
            raise KeyError(f"{name!r} is not a page; the pages are {page_names()!r}")
        self.page_errors.pop(spec.name, None)
        self._views.pop(spec.name, None)

    # ------------------------------------------------------------------
    # Material
    # ------------------------------------------------------------------

    def columns_document(self) -> Document:
        """
        The document the Columns tab flows, parsed once.
        """
        if self._columns_document is None:
            self._columns_document = build_document(
                self.columns_source if self.columns_source is not None else self.source,
                self.theme,
                fontlib_metrics,
            )
        return self._columns_document

    def alphabet(self) -> Scaled:
        """
        The theme's lowercase alphabet, measured once.

        The same quantity `DocumentView` measures, and held here as well rather
        than reached for through the view: it costs twenty-six `CharMeasure` calls
        and the Columns tab needs it every frame to place its sheet.
        """
        if self._alphabet is None:
            self._alphabet = alphabet_length(self.theme, self.measure)
        return self._alphabet

    def page_for_columns(self, available: Scaled, count: int) -> ColumnPage:
        """
        Where the Columns tab's sheet sits, for a content region of this width.
        """
        return column_page(
            available,
            alphabet=self.alphabet(),
            leading=self.theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width,
            count=count,
        )

    def column_layout(
        self, column_width: Scaled, column_height: Scaled, count: int
    ) -> ColumnLayout:
        """
        The cached column split for one measure, height and count.

        **A column-count change is a full reflow and there is no way around it.**
        Narrowing the page into more columns changes the measure, and
        `advtext.ui.LayoutCache` correctly misses on every text block at a width it
        has not seen. The split itself is not the cost -- `advtext.columns` measures
        a three-way `vsplit` at 0.53 ms -- the line breaker is.

        **Measured here, on `demo/columns.md` at an 800 px column height, against a
        16.7 ms frame budget.** A viewer clicking 1, 2, 3, 1, 2, 3 -- so each count
        is visited cold once and warm once:

            first visit to a count     479 / 526 / 970 ms
            second visit, 3 resident    19 /  20 /  22 ms
            second visit, 2 resident   448 / 535 / 937 ms
            an unchanged (width, height, count)     9 us

        Four things follow, and together they are the honest account of this tab.

        - **The first click on a count is a freeze, not a jank**, and nothing here
          can fix that: the measure has never been composed, so the line breaker
          runs over the whole document.
        - **Every later click is 20 ms**, which is one dropped frame. That is what
          `_columns_blocks` being sized to the control buys, and the third row above
          is what it costs to get wrong -- at the `LayoutCache` default of two
          resident passes the least recently used count is evicted every time round
          and the cycle never warms up at all. A 25x difference from one argument.
        - **Narrower is slower.** Three columns cost twice one, at a third of the
          measure, because the breaker is superlinear in the number of lines and a
          narrower measure makes more of them.
        - **A resize drag is the bad case and this does not fix it.** Every pixel of
          the drag is a new measure, and `docs/status.md` section 4 records that the
          per-block cache gets zero hits across consecutive widths, so the tab pays
          the cold figure per frame. The Document tab has the same defect against a
          shorter document. Fixing it means quantising the width or deferring the
          reflow until the drag stops, and neither belongs in a demo tab.
        """
        cached = self._columns_layout
        if cached is not None and cached.key == (column_width, column_height, count):
            return cached

        material = compose_blocks(
            self.columns_document().blocks,
            self.theme,
            column_width,
            self.measure,
            cache=self._columns_blocks,
        ).contents
        natural = vpack(material).box
        pages = _column_pages(natural.height + natural.depth, column_height, count)
        split = split_into_columns(material, height=column_height, count=count * pages)

        # Trailing empty columns are the slack `_column_pages` deliberately asked
        # for. Dropping them here, rather than asking for a tighter number there,
        # is what lets the estimate be generous without ever showing a blank sheet.
        used = 0
        for index, result in enumerate(split.results):
            if result.box.contents:
                used = index + 1
        pages = max(1, math.ceil(used / count))

        fresh = ColumnLayout(
            column_width=column_width,
            column_height=column_height,
            count=count,
            pages=pages,
            indexes=tuple(
                CommandIndex.of(ship(result.box, Point(0, result.box.height), measure=self.measure))
                for result in split.results[: pages * count]
            ),
            overflow=len(split.overflow),
        )
        self._columns_layout = fresh
        return fresh

    def formula_box(self, width: Scaled) -> Box:
        """
        The summation in display and text style, side by side, packed to a measure.

        Side by side and not on two lines: the claim is that one is a *different
        glyph* from the other, and a reader compares them faster than they compare
        a picture with a memory.

        Packed to the caller's measure rather than to a fixed 600 px, so the two
        `HSS` glues centre the pair on the page the rest of the demo sets. The
        construction is otherwise the one `tests/test_imgui_draw.py` pins.

        **The Formula page no longer draws this.** It draws `gallery`, whose
        `operator-style` entry is the same comparison with a caption and a label
        under each half. This is kept as the smallest reproduction of it: it is
        what `tests/test_app.py` pins the repack-on-measure-change behaviour
        through, and `scripts/verify_ascent.py` names it for the size it sets.
        """
        if self._formula is None or self._formula_width != width:
            size = sp_from_px(36.0, self.px_per_inch)
            fonts = math_fonts(size, lambda at: fontlib.math_metrics(float(at)))
            parts: list[Node] = []
            for index, style in enumerate((Style.DISPLAY, Style.TEXT)):
                if index:
                    parts.append(Kern(width=size))
                parts.extend(mlist_to_hlist([SUMMATION], style, fonts))
            self._formula = hpack(
                [Glue(HSS), *parts, Glue(HSS)], width, PackMode.EXACTLY, measure=fonts.measure
            ).box
            self._formula_width = width
        return self._formula

    def specimen(self, width: Scaled) -> Specimen:
        """
        The cached font specimen for one prose measure.

        Cached for the reason `build_specimen`'s docstring asks it to be: 68 ms at
        a 760 pt measure, of which 62 ms is the three section notes going through
        the line breaker. Nothing in it depends on the window except that measure.
        """
        if self._specimen is None or self._specimen_width != width:
            self._specimen = build_specimen(
                self.theme, width, fontlib_metrics, measure=self.measure
            )
            self._specimen_width = width
        return self._specimen

    def gallery(self, width: Scaled) -> Gallery:
        """
        The cached formula gallery for one prose measure.

        Cached for the reason the specimen is: **45 ms at the 468 px measure this
        tab sets, warm, best of three, against a 16.7 ms frame budget** -- and
        nearly all of it is the captions going through `break_paragraph` (nine of
        them when that was measured; there are eleven now and it was not re-taken). The
        math is a few ms, because nothing in a formula is line-broken. Nothing in
        it depends on the window except the measure the captions break to.
        """
        if self._gallery is None or self._gallery_width != width:
            self._gallery = build_gallery(self.theme, width, fontlib_metrics, measure=self.measure)
            self._gallery_width = width
        return self._gallery

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    def gui(self) -> None:
        """
        One frame: the navigation list, and beside it whichever page is showing.

        The list is a child window of fixed width; the page is drawn after a
        `same_line`, inside a group and **not** inside a second child. A group
        only moves the left edge: the page's own header row is still drawn on
        the window's background and its own scrolling child is still a direct
        child of the window, exactly as under the tab bar, which is what keeps
        the five original pages' pixels where they were. A wrapping child would
        have put the header on the darker child background and nested every
        page's scroll one level down.

        `open_tab` selects a page once, on the first frame, and is then cleared;
        held, it would re-select every frame and the list could never be
        clicked away from.

        **An exception out of a page's factory or its `draw` is caught, per
        page** (`_draw_page`): the body shows the traceback, the list still
        works, and every other page is as it was. It used to end the app. The
        reason given then -- a screenshot run must not photograph a blank
        body -- is kept another way: `run` raises `PageError` once the window
        has closed if anything is in `page_errors`, so `scripts/shot.py` and
        the window tests still fail, with the page's own traceback.
        """
        from imgui_bundle import imgui

        if self.open_tab is not None:
            self.select(self.open_tab)
            self.open_tab = None
        self._sidebar()
        imgui.same_line()
        imgui.begin_group()
        if self.current is None:
            caption("no pages were found in advtext.ui.pages")
        else:
            self._draw_page(self.current)
        imgui.end_group()

    def _draw_page(self, name: str) -> None:
        """
        Build and draw page `name`, or show why it could not be.

        **ImGui's stacks are put back after an exception.** A `draw` that
        raises between a `begin_child` and its `end_child` (or a push and its
        pop) leaves the frame unbalanced, and ImGui then asserts at the
        window's `End` -- through imgui-bundle, a second exception, out of
        the frame. So the state is stored before the page runs
        (`error_recovery_store_state`) and restored if it raises, with
        ImGui's own reporting of what it had to close switched off for the
        length of that call: the traceback is the report. Measured in
        headless frames with a child, a style colour, an id and a group left
        open (`tests/test_pages.py`), and with a table, a tab bar, a tooltip,
        a disabled block and a second window.

        **A clip rectangle left pushed on this window's draw list is popped
        here**, because ImGui's recovery does not do it (review 3, item 11,
        measured: no assertion and no exception, on that frame or the next
        -- but everything drawn in the window after the page on the frame it
        raised, the traceback included, was clipped to the rectangle the
        page left: 58 vertices where the frames after it had 1,338). The
        depth is read from the draw list's own stack (`_clip_depth`); where
        a binding does not show it, nothing is popped and that one frame is
        clipped as before.

        `Exception` and not `BaseException`: Ctrl+C and `SystemExit` still
        end the app. The traceback goes to stderr once, when it happens.
        """
        from imgui_bundle import imgui

        error = self.page_errors.get(name)
        if error is None:
            state = imgui.internal.ErrorRecoveryState()
            imgui.internal.error_recovery_store_state(state)
            draw_list = imgui.get_window_draw_list()
            clips = _clip_depth(draw_list)
            try:
                self.page(name).draw()
            except Exception:
                error = self.page_errors[name] = traceback.format_exc()
                print(f"advtext: page {name!r} raised:\n{error}", file=sys.stderr)
                io = imgui.get_io()
                reporting = (
                    io.config_error_recovery_enable_assert,
                    io.config_error_recovery_enable_debug_log,
                    io.config_error_recovery_enable_tooltip,
                )
                io.config_error_recovery_enable_assert = False
                io.config_error_recovery_enable_debug_log = False
                io.config_error_recovery_enable_tooltip = False
                try:
                    imgui.internal.error_recovery_try_to_recover_state(state)
                finally:
                    (
                        io.config_error_recovery_enable_assert,
                        io.config_error_recovery_enable_debug_log,
                        io.config_error_recovery_enable_tooltip,
                    ) = reporting
                # The one stack ImGui's recovery does not look at: this
                # window's clip rectangles. `imgui.pop_clip_rect` and not the
                # draw list's own: it also puts the window's clip rectangle
                # back, which is what items and text are culled against, and
                # which `imgui.push_clip_rect` (as against the draw list's)
                # had changed.
                while clips is not None and (_clip_depth(draw_list) or 0) > clips:
                    imgui.pop_clip_rect()
        if error is not None:
            caption(f"{name} raised an exception and is not being drawn")
            imgui.same_line()
            if imgui.small_button(f"Retry##advtext-page-retry-{name}"):
                self.retry(name)
            imgui.begin_child(f"##advtext-page-error-{name}")
            imgui.text_unformatted(error)
            imgui.end_child()

    def _sidebar(self) -> None:
        """
        Draw `sidebar_rows` and take a click on one of them.

        The child's background is pushed to transparent, so the list sits on
        the window's own colour: `child_bg` is the dark surround a page sheet
        lies on, and the list is chrome, not a surround.
        """
        from imgui_bundle import imgui

        imgui.push_style_color(imgui.Col_.child_bg, imgui.ImVec4(0.0, 0.0, 0.0, 0.0))
        visible = imgui.begin_child("##advtext-sidebar", imgui.ImVec2(SIDEBAR_WIDTH_PX, 0.0))
        imgui.pop_style_color()
        if visible:
            for index, row in enumerate(sidebar_rows(self.discovery)):
                if row.kind == "heading":
                    if index:
                        imgui.spacing()
                    caption(row.text.upper())
                elif row.page is not None:
                    label = f"{row.text}##advtext-page-{row.page.name}"
                    if imgui.selectable(label, row.page.name == self.current)[0]:
                        self.current = row.page.name
                    if row.detail:
                        imgui.set_item_tooltip(row.detail)
                else:
                    imgui.text_colored(imgui.ImVec4(0.9, 0.6, 0.2, 1.0), row.text)
                    imgui.set_item_tooltip(row.detail)
        imgui.end_child()


# The drawing helpers every page shared (`_caption`, `_plate`, `_paint_sheet`,
# `_draw_at`, `_claim`) are `advtext.ui.pages.caption`, `plate`, `paint_sheet`,
# `draw_at` and `claim` now, so that a page module does not import this one to
# set a sheet. `_plate` keeps its old name here for `tests/test_app.py`.
_plate = plate


# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------


def _vec4(colour: int, alpha: float = 1.0) -> imgui.ImVec4:
    """
    One of this module's packed `IM_COL32` colours as ImGui's float vector.

    `rgba` packs alpha, blue, green, red with the low byte first -- the byte order
    is `IM_COL32`'s and is not RGBA despite the name -- so the shifts here are
    that order read back. Taking the colours from one place and converting is what
    keeps the chrome and the page from drifting apart.
    """
    from imgui_bundle import imgui

    return imgui.ImVec4(
        (colour & 0xFF) / 255.0,
        ((colour >> 8) & 0xFF) / 255.0,
        ((colour >> 16) & 0xFF) / 255.0,
        alpha,
    )


# The chrome. Neutral greys with one desaturated accent, because the page is the
# only saturated thing on screen and anything else competing with it is a
# regression. `SURROUND` is darker than `CHROME` so the sheet sits on the darkest
# surface in the window and reads as lit.
CHROME = rgba(0x1A, 0x1A, 0x1D)
SURROUND = rgba(0x0E, 0x0E, 0x10)
RAISED = rgba(0x26, 0x26, 0x2B)
HOVER = rgba(0x32, 0x32, 0x38)
LINE = rgba(0x38, 0x38, 0x3F)
LABEL = rgba(0xE4, 0xE4, 0xE6)
MUTED = rgba(0x8C, 0x8C, 0x96)
ACCENT = rgba(0x9F, 0xB4, 0xCC)


def apply_style() -> None:
    """
    Push the demo's chrome into `ImGuiStyle`. Needs a live context.

    A hello_imgui `setup_imgui_style` callback rather than something `run` calls
    directly, and set once rather than per frame: `ImGuiStyle` is global mutable
    state that persists across frames, unlike almost everything else in immediate
    mode, and a per-frame push would be a pair of calls to keep balanced for no
    gain.

    Restrained deliberately. Square corners everywhere the eye might otherwise
    read a widget as a card, no borders except the hairline under a tab bar, and
    the accent only on things that respond to a mouse. `docs/imgui-risks.md`'s
    argument that the text is what is being demonstrated applies to the chrome
    too: the most useful thing this function does is stop the default theme's blue
    from being the brightest object in a photograph of a page of type.

    The shell has no tab bar any more -- its navigation is a list of
    selectables, coloured by the three `header` entries below -- but the tab
    colours are kept for a page that wants tabs of its own inside its body.
    """
    from imgui_bundle import imgui

    style = imgui.get_style()
    style.window_rounding = 0.0
    style.child_rounding = 0.0
    style.frame_rounding = 3.0
    style.grab_rounding = 3.0
    style.tab_rounding = 0.0
    style.scrollbar_rounding = 0.0
    style.window_border_size = 0.0
    style.child_border_size = 0.0
    style.frame_border_size = 0.0
    style.tab_bar_border_size = 1.0
    style.tab_bar_overline_size = 2.0
    style.window_padding = imgui.ImVec2(16, 12)
    style.frame_padding = imgui.ImVec2(10, 6)
    style.item_spacing = imgui.ImVec2(12, 8)
    style.scrollbar_size = 12.0
    style.grab_min_size = 10.0

    colour = imgui.Col_
    put = style.set_color_
    put(colour.text, _vec4(LABEL))
    put(colour.text_disabled, _vec4(MUTED))
    put(colour.window_bg, _vec4(CHROME))
    # The scrolling children are the surround the page sits on, so they are the
    # darkest surface here and not a lighter "panel" -- see `Palette`, which makes
    # the same argument from the other side.
    put(colour.child_bg, _vec4(SURROUND))
    put(colour.popup_bg, _vec4(RAISED))
    put(colour.border, _vec4(LINE))
    put(colour.border_shadow, imgui.ImVec4(0, 0, 0, 0))
    put(colour.frame_bg, _vec4(RAISED))
    put(colour.frame_bg_hovered, _vec4(HOVER))
    put(colour.frame_bg_active, _vec4(HOVER))
    put(colour.check_mark, _vec4(ACCENT))
    put(colour.button, _vec4(RAISED))
    put(colour.button_hovered, _vec4(HOVER))
    put(colour.button_active, _vec4(ACCENT, 0.45))
    put(colour.header, _vec4(RAISED))
    put(colour.header_hovered, _vec4(HOVER))
    put(colour.header_active, _vec4(HOVER))
    put(colour.separator, _vec4(LINE))
    put(colour.scrollbar_bg, _vec4(SURROUND))
    put(colour.scrollbar_grab, _vec4(RAISED))
    put(colour.scrollbar_grab_hovered, _vec4(HOVER))
    put(colour.scrollbar_grab_active, _vec4(ACCENT, 0.6))
    put(colour.tab, _vec4(CHROME))
    put(colour.tab_hovered, _vec4(HOVER))
    put(colour.tab_selected, _vec4(RAISED))
    put(colour.tab_selected_overline, _vec4(ACCENT))
    put(colour.tab_dimmed, _vec4(CHROME))
    put(colour.tab_dimmed_selected, _vec4(RAISED))
    put(colour.tab_dimmed_selected_overline, _vec4(ACCENT, 0.4))


# ----------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------

_FACES: dict[Face, imgui.ImFont | None] = {}


def load_fonts() -> None:
    """
    Register every face with ImGui, from the paths `advtext.fontlib` resolves.

    A thin caller of `advtext.ui.fonts.load_faces`, which is where the loading
    now lives so that a host can call it too. What stays here is what is the
    demo's own: `hello_imgui`'s loader, the decision to load mathematics up
    front (`ALL_FACES` -- the first page has a formula in it), and the module
    global the pages read through `PageContext.fonts`.

    A hello_imgui callback rather than something `run` calls directly: fonts must
    be built after the backend exists and before the first frame, and the runner
    owns that window. A face that fails to load is left absent rather than fatal
    -- `draw` treats `None` as "use whatever is bound", so the demo degrades to
    the default face at the right positions instead of not starting.

    **The dict is cleared first.** It is a module global, and a second `run` in
    one process would otherwise keep `ImFont` pointers belonging to the atlas the
    first run destroyed -- `docs/status.md` section 4 records that hazard. Nothing
    in the tree calls `run` twice today; clearing costs one statement and removes
    a use-after-free from the list of things a future screenshot harness has to
    know about.
    """
    from imgui_bundle import hello_imgui

    from advtext.ui.fonts import ALL_FACES, DEFAULT_LOAD_PX, load_faces

    _FACES.clear()
    params = hello_imgui.FontLoadingParams()
    # The files live in the imgui-bundle wheel, not in an assets folder of ours,
    # so they are loaded by absolute path rather than through the asset system.
    params.inside_assets = False
    loaded = load_faces(
        ALL_FACES,
        loader=lambda path: hello_imgui.load_font(str(path), DEFAULT_LOAD_PX, params),
    )
    _FACES.update(loaded.fonts)


def _face_font(face: Face) -> imgui.ImFont | None:
    """
    The loaded `ImFont` for a role, or `None` if it did not load.
    """
    return _FACES.get(face)


# ----------------------------------------------------------------------


def run(
    source: str | None = None,
    *,
    ini_folder: str | None = None,
    tab: str | None = None,
    columns_source: str | None = None,
) -> None:
    """
    Open the demo window. Needs a display.

    On this machine's `DISPLAY=:1` a window opens in about 0.4 s. Whether that
    display is reachable is a fact about the session and not about this
    function: from the sandbox of 2026-10-06 it was not, and the window was
    opened on an Xvfb in a user namespace instead (`scripts/mouse_probe.py`,
    `xvfb_command`). Without a reachable display this does not hang: GLFW
    aborts in about 0.6 s with
    `IM_ASSERT( glfwInitSuccess )`, and `scripts/run_demo.py` turns that into
    something readable. `make shot` photographs any page without a terminal
    attached to a display, and `make shot-headless` is the Xvfb fallback for a
    machine that has none.

    `source` and `columns_source` both default to the files in `demo/`, falling
    back to `DEFAULT_MARKDOWN` when this is not a checkout -- `demo/` is not
    inside the package and is absent from an installed wheel.

    `tab` selects a page on the first frame in `parse_tab_request`'s grammar, which
    is how a screenshot reaches a state without clicking for it. (This used to
    say "a state no click in this environment can produce";
    `scripts/mouse_probe.py` posts clicks into this app now, though it does not
    click the navigation list.)

    `ini_folder_type` is set to the app's own user-config folder rather than the
    default current folder, so running this does not scatter `.ini` files across
    whatever directory it was launched from. pptmstr's app does this and its
    verify scripts do not, which is why that tree has stray ini files in it.
    """
    from imgui_bundle import hello_imgui, immapp

    app = App(
        source=source or demo_text("sample.md") or DEFAULT_MARKDOWN,
        columns_source=columns_source or demo_text("columns.md"),
        open_tab=tab,
    )

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = WINDOW_SIZE
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.provide_full_screen_window
    )
    params.ini_folder_type = hello_imgui.IniFolderType.app_user_config_folder
    if ini_folder is not None:
        params.ini_folder_type = hello_imgui.IniFolderType.absolute_path
        params.ini_filename = str(Path(ini_folder) / "advtext.ini")
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.setup_imgui_style = apply_style
    params.callbacks.show_gui = app.gui
    immapp.run(params)
    if app.page_errors:
        raise PageError(app.page_errors)

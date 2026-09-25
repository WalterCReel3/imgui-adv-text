r"""
The demo application: five tabs, one window, and a theme that stays out of the way.

**This has been executed and photographed.** `DISPLAY=:1` is live in this
sandbox, `scripts/shot.py` drives this module's own `run` for N frames and grabs
the window, and every claim below about how something *looks* was checked by
reading the resulting PNG. The module docstring here used to open "Never
executed"; that was true for most of this project's life and is not true now.
What is still unexercised is input: nothing in this environment synthesises a
click, which is why `App.open_tab` exists and why it grew the small grammar
`parse_tab_request` implements.

Five tabs, because there are five claims worth looking at:

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
4. **Formula** -- nine formulae, each chosen because it is the only one that makes
   some rule of TeX's math mode visible: the display-size operator as a different
   glyph, the four math styles and where they stop, the inter-atom spacing table
   with and without its classes, and a binary operator that is only binary in
   context. `advtext.ui.formulas` builds it and its docstring has the table.
5. **Blocks** -- `advtext.blocklayout`'s toolbar at three widths, showing that a
   centred item stays centred because two `fil` glues split the surplus evenly.

## One page geometry, applied five times

`advtext.ui.document_view.page_for` decides where the sheet sits and how wide the
text on it is, and it carries the typographic argument for both. Every tab here
goes through it -- `_paint_sheet` is the one place that turns a `Page` into a
filled rectangle and a text-block origin, so a margin cannot be applied to the
document and forgotten on the specimen. `column_page` is the same arithmetic
generalised to N columns and **reduces to `page_for` exactly at N = 1**, which is
what `tests/test_app.py` pins rather than leaving as a comment.

## The theme

`apply_style` is the whole of it: a neutral dark chrome around the light page
that `advtext.backends.imgui_draw.Palette` already argues for. It is restrained
on purpose. The text is the thing being shown and chrome that competes with it is
a regression, so there is no accent on anything that is not interactive, no
rounding on the tab bar, and nothing that draws the eye off the sheet.

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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from advtext import fontlib
from advtext.backends.imgui_draw import DrawStats, Palette, rgba
from advtext.columns import split_into_columns
from advtext.fontmetrics import Face
from advtext.markdown import Document, build_document
from advtext.math import Style, math_fonts, mlist_to_hlist
from advtext.nodes import Box, Glue, Kern, Node
from advtext.pack import CharMeasure, PackMode, hpack, vpack
from advtext.shipout import Point, ship
from advtext.style import BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import HSS, CommandIndex, LayoutCache, Viewport, compose_blocks
from advtext.ui.document_view import (
    MEASURE_ALPHABETS,
    TEXT_BLOCK_FRACTION,
    DocumentView,
    Page,
    alphabet_length,
    text_margin,
)
from advtext.ui.formulas import ENTRIES as FORMULA_ENTRIES
from advtext.ui.formulas import SUMMATION, Gallery, build_gallery, missing_glyphs
from advtext.ui.specimen import Specimen, build_specimen
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "COLUMN_COUNTS",
    "DEFAULT_MARKDOWN",
    "GUTTER_LEADINGS",
    "TAB_NAMES",
    "App",
    "ColumnPage",
    "TabRequest",
    "apply_style",
    "column_page",
    "load_fonts",
    "parse_tab_request",
    "run",
]

WINDOW_TITLE = "advtext"

TAB_NAMES: Final = ("Document", "Columns", "Specimen", "Formula", "Blocks")
"""
Every tab, in the order the tab bar shows them. **The single copy of this list.**

`App.gui` iterates it and `parse_tab_request` validates against it, so the two
cannot disagree, and a consumer outside this module has something to read
instead of a copy to keep.

**Three copies drifted before this existed, and the damage was measured.**
`Makefile`'s `SHOT_TABS` listed the original three, so `make shot-all` silently
skipped Columns and Specimen; `scripts/run_demo.py` rejected `columns:3` and
`specimen` outright, so `make run` could not open either; and `scripts/shot.py`
deliberately kept no copy, its comment reading "a copy of the tab list would go
stale the first time a tab was added" -- a prediction that came true twice in one
batch.

Worse, nothing validated the *name*. T15-shot-tabs measured
`scripts/shot.py --tab colums`, one letter wrong, producing an image
**byte-identical to `--tab document`**: 0 of 2,640,800 decompressed bytes
differed, exit 0, no warning. `parse_tab_request` already refused an unknown
option after the colon on the stated grounds that "a wrong picture is worse than
a refusal"; it now refuses an unknown name on the same grounds.
"""

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

# The demo documents, beside the repository rather than inside the package. A
# checkout therefore opens on the real document and an installed wheel opens on
# DEFAULT_MARKDOWN, which is the honest degradation: the files are genuinely not
# there in the second case.
DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


def demo_text(name: str) -> str | None:
    """
    A file from `demo/`, or `None` when this is not a checkout.

    `OSError` and not `FileNotFoundError`: a wheel installed into a read-only
    prefix, a broken symlink and a directory of the same name all have to come
    back as "not available" rather than as a traceback on the way to a window.
    """
    try:
        return (DEMO_DIR / name).read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - exercised only outside a checkout
        return None


# ----------------------------------------------------------------------
# What a screenshot can ask for
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TabRequest:
    """
    A tab to open on the first frame, and the state to open it in.

    Every field is `None`-or-default-meaning-"leave it alone", so a request can
    name a tab without disturbing the column count and vice versa.
    """

    tab: str | None = None
    columns: int | None = None
    debug: bool = False


def _check_tab_name(spec: str, name: str) -> None:
    """
    Refuse a tab name that is not in `TAB_NAMES`, naming the ones that are.

    An empty name is allowed and means "leave the tab alone": `parse_tab_request`
    maps it to `TabRequest(tab=None)`, and `:debug` with no name in front of it
    is a legitimate way to ask for the overlay on whatever opens.
    """
    if not name or name.lower() in {tab.lower() for tab in TAB_NAMES}:
        return
    raise ValueError(
        f"{spec!r}: {name!r} is not a tab. "
        f"The tabs are {', '.join(TAB_NAMES)} -- case does not matter. "
        "Refused rather than ignored because an unmatched name opens the first "
        "tab, which is a photograph of the wrong thing under a filename that "
        "claims otherwise."
    )


def parse_tab_request(spec: str | None) -> TabRequest:
    """
    Parse `NAME[:OPTION[,OPTION...]]`, the grammar a screenshot addresses a tab with.

    Nothing in this environment can click a control, so a tab whose interesting
    states are only reachable by clicking is a tab that can never be photographed
    in any of them. `App.open_tab` already existed to name the tab; this widens it
    to the two pieces of state the tabs have:

        document            the Document tab, as it opens
        document:debug      ... with the debug overlay on
        columns:3           the Columns tab, at three columns
        columns:3,debug     ... and the overlay

    An option is either an integer, meaning the column count, or the word
    `debug`. Anything else raises `ValueError` **before the window opens**: a
    misspelt option that silently did nothing would produce a photograph of the
    default state under a filename claiming otherwise, and a wrong picture is
    worse than a refusal.

    **The name is held to the same standard, and it was not always.** A name not
    in `TAB_NAMES` raises here, case-insensitively as `App.gui` matches it.
    Before this, an unknown name simply never matched, ImGui opened the first
    tab, and `--tab colums` produced an image byte-identical to `--tab document`
    at exit 0 -- the exact failure the paragraph above refuses for options, going
    unrefused for the thing the option is attached to.
    """
    if spec is None:
        return TabRequest()
    name, separator, rest = spec.partition(":")
    _check_tab_name(spec, name)
    if not separator:
        return TabRequest(tab=name or None)

    columns: int | None = None
    debug = False
    for option in rest.split(","):
        option = option.strip()
        if option == "debug":
            debug = True
        elif option.isdigit() and int(option) >= 1:
            columns = int(option)
        else:
            raise ValueError(
                f"{spec!r}: {option!r} is not a tab option. "
                "Options are 'debug' or a column count of 1 or more, "
                "comma separated, after a colon -- for instance 'columns:3,debug'."
            )
    return TabRequest(tab=name or None, columns=columns, debug=debug)


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
    The demo's whole state: two documents, one document view and three caches.

    The formula and the block layouts depend only on the measure; the specimen
    depends on the measure; the columns depend on the measure, the visible height
    and the column count. Each is cached against exactly what it depends on, and
    `DocumentView` owns the Document tab's own cache.
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
    nothing and three is tight in the default 980 px window.
    """
    open_tab: str | None = None
    """
    A tab to select on the first frame, in `parse_tab_request`'s grammar.

    Exists so a screenshot can name the tab it wants, and now the state it wants
    it in. There is no synthetic-input tool in the environment that captures a
    click, so without it only the tab ImGui opens by default, in the state it
    opens in, could ever be photographed.
    """
    view: DocumentView = field(init=False)
    _formula: Box | None = field(default=None, init=False)
    _formula_width: Scaled = field(default=0, init=False)
    _formula_stats: DrawStats = field(default_factory=DrawStats, init=False)
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
        request = parse_tab_request(self.open_tab)
        if request.columns is not None:
            self.columns = request.columns
        self.view.debug = request.debug
        self.open_tab = request.tab

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

        **The Formula tab no longer draws this.** It draws `gallery`, whose
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
        nearly all of it is the nine captions going through `break_paragraph`. The
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
        One frame: the tab bar and whichever tab is open.

        The order is `TAB_NAMES`'; the bodies are looked up by name out of it, so
        a tab added to one and not the other is a `KeyError` on the first frame
        rather than a tab that quietly never appears.
        """
        from imgui_bundle import imgui

        if not imgui.begin_tab_bar("##advtext-tabs"):
            return
        bodies = {
            "Document": self._document_tab,
            "Columns": self._columns_tab,
            "Specimen": self._specimen_tab,
            "Formula": self._formula_tab,
            "Blocks": self._blocks_tab,
        }
        for name in TAB_NAMES:
            body = bodies[name]
            # `open_tab` selects a tab once, on the first frame that draws it,
            # and is then cleared. Without the clear the flag would re-select it
            # every frame and the tab bar could never be clicked away from --
            # which looks like a broken tab bar rather than like a held flag.
            flags = 0
            if self.open_tab is not None and name.lower() == self.open_tab.lower():
                flags = int(imgui.TabItemFlags_.set_selected)
                self.open_tab = None
            if imgui.begin_tab_item(name, None, flags)[0]:
                body()
                imgui.end_tab_item()
        imgui.end_tab_bar()

    def _document_tab(self) -> None:
        from imgui_bundle import imgui

        self._debug_toggle()
        imgui.same_line()
        _caption("drag to select  ·  double click a word  ·  triple click a line  ·  ctrl+C copies")
        imgui.separator()
        if imgui.begin_child("##advtext-scroll"):
            stats = self.view.draw(fonts=_face_font)
            if stats.missing:
                _caption(f"{stats.missing} glyph(s) absent from the ImGui atlas")
        imgui.end_child()

    def _columns_tab(self) -> None:
        from imgui_bundle import imgui

        self._debug_toggle()
        for count in sorted({*COLUMN_COUNTS, self.columns}):
            imgui.same_line()
            if imgui.radio_button(f"{count}##columns", self.columns == count):
                self.columns = count
        imgui.same_line()
        _caption("columns  ·  text continues from the foot of one to the head of the next")
        imgui.separator()
        if imgui.begin_child("##advtext-columns"):
            self._draw_columns()
        imgui.end_child()

    def _specimen_tab(self) -> None:
        from imgui_bundle import imgui

        self._debug_toggle()
        imgui.same_line()
        _caption("every face at one size, one face at every size, and the kerning underneath")
        imgui.separator()
        if imgui.begin_child("##advtext-specimen"):
            self._draw_specimen()
        imgui.end_child()

    def _formula_tab(self) -> None:
        from imgui_bundle import imgui

        self._debug_toggle()
        imgui.same_line()
        _caption(
            f"{len(FORMULA_ENTRIES)} formulae, each one the only thing here that shows "
            "some rule of TeX's math mode"
        )
        # Two independent failures, reported separately because either can happen
        # alone. `missing_glyphs` is a codepoint the *font file* has no glyph for,
        # answerable before anything is drawn. `DrawStats.missing` is a glyph ImGui
        # could not raster, found while drawing. Collapsing them into one line
        # would make a font swap and an atlas problem look like the same fault.
        gallery_missing = missing_glyphs()
        if gallery_missing:
            imgui.text_colored(
                imgui.ImVec4(0.9, 0.6, 0.2, 1.0),
                f"{len(gallery_missing)} codepoint(s) have no glyph in the math face: "
                + " ".join(f"U+{code:04X}" for code in gallery_missing),
            )
        if self._formula_stats.missing:
            imgui.text_colored(
                imgui.ImVec4(0.9, 0.6, 0.2, 1.0),
                f"{self._formula_stats.missing} glyph(s) have no raster in ImGui's atlas. "
                "Use `make svg` to see them.",
            )
        imgui.separator()
        if imgui.begin_child("##advtext-formula"):
            self._draw_gallery()
        imgui.end_child()

    def _blocks_tab(self) -> None:
        from imgui_bundle import imgui

        try:
            from advtext import blocklayout
        except ImportError:  # pragma: no cover - the stretch goal may be absent
            _caption("advtext.blocklayout is not present in this build")
            return
        _caption(
            "a toolbar at three widths: the centred title stays centred because two "
            "fil glues split the surplus evenly"
        )
        imgui.separator()
        if imgui.begin_child("##advtext-blocks"):
            page = _plate(self.view.page(self._available_width()))
            toolbar = blocklayout.Row(
                children=(
                    *blocklayout.centre(
                        (
                            blocklayout.Leaf(width=sp_from_px(80.0), height=sp_from_px(24.0)),
                            blocklayout.Leaf(width=sp_from_px(160.0), height=sp_from_px(24.0)),
                            blocklayout.Leaf(width=sp_from_px(80.0), height=sp_from_px(24.0)),
                        )
                    ),
                )
            )
            # One sheet with the three rows stacked on it, not a sheet each. The
            # claim is a *comparison* -- the same three leaves, three surpluses,
            # one centre line -- and three separate pages would put the thing
            # being compared on three different backgrounds.
            #
            # Fractions of the measure rather than the old fixed 420 and 700 px:
            # 700 px is wider than the page the rest of the demo sets, so the
            # wide row used to hang off the sheet. The narrowest is 0.75 and not
            # less because the three leaves are 320 px natural and a row narrower
            # than that has no surplus to split -- the glues collapse to zero and
            # the tab demonstrates nothing.
            rows: list[Node] = []
            gap = self.theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
            for index, fraction in enumerate((0.75, 0.875, 1.0)):
                if index:
                    rows.append(Kern(width=gap))
                rows.append(blocklayout.layout(toolbar, width=round(page.measure * fraction)))
            stacked = vpack(rows).box
            height = stacked.height + stacked.depth
            origin = _paint_sheet(page, self.px_per_inch, content_height=height)
            # Debug on unconditionally: a `Leaf` has no glyphs, so with the
            # overlay off this tab draws nothing at all.
            _draw_at(stacked, origin, self.measure, self.px_per_inch, True)
            _claim(page, height, self.px_per_inch)
        imgui.end_child()

    # ------------------------------------------------------------------

    def _debug_toggle(self) -> None:
        from imgui_bundle import imgui

        _, self.view.debug = imgui.checkbox("debug overlay", self.view.debug)

    def _available_width(self) -> Scaled:
        from imgui_bundle import imgui

        return sp_from_px(max(imgui.get_content_region_avail().x, 80.0), self.px_per_inch)

    def _draw_specimen(self) -> None:

        page = self.view.page(self._available_width())
        specimen = self.specimen(page.measure)

        # The rows are packed at their natural width and are wider than the prose
        # measure -- `build_specimen` says so and it is the right call, because a
        # comparison chart is not something anyone reads at 66 characters. So the
        # sheet grows to hold them rather than the chart being cut to fit a sheet
        # sized for prose.
        content = max(page.measure, specimen.box.width)
        wide = Page(
            offset=max(0, (self._available_width() - content - 2 * page.margin) // 2),
            width=content + 2 * page.margin,
            margin=page.margin,
            head=page.head,
        )
        origin = _paint_sheet(
            wide,
            self.px_per_inch,
            content_height=specimen.box.height + specimen.box.depth,
        )
        _draw_at(specimen.box, origin, self.measure, self.px_per_inch, self.view.debug)
        _claim(wide, specimen.box.height + specimen.box.depth, self.px_per_inch)
        if specimen.absent:
            _caption(f"{len(specimen.absent)} face(s) could not be resolved: no row for them")

    def _draw_gallery(self) -> None:
        """
        One frame of the Formula tab: the gallery on one sheet, scrolling.

        A scroll of plates rather than the single `_plate` this tab used to set,
        because there are now nine of them and a nine-page-tall sheet of air
        between two formulae is not a page. The sheet grows sideways for a formula
        wider than the prose measure by exactly the arithmetic `_draw_specimen`
        uses -- `build_gallery` reports that case as `Gallery.box.width` exceeding
        `Gallery.width`, and with the shipped entries at the default sizes it does
        not happen at any width this demo opens at.
        """
        page = _plate(self.view.page(self._available_width()))
        gallery = self.gallery(page.measure)
        content = max(page.measure, gallery.box.width)
        wide = Page(
            offset=max(0, (self._available_width() - content - 2 * page.margin) // 2),
            width=content + 2 * page.margin,
            margin=page.margin,
            head=page.head,
        )
        height = gallery.box.height + gallery.box.depth
        origin = _paint_sheet(wide, self.px_per_inch, content_height=height)
        self._formula_stats = _draw_at(
            gallery.box, origin, self.measure, self.px_per_inch, self.view.debug
        )
        _claim(wide, height, self.px_per_inch)

    def _draw_columns(self) -> None:
        """
        One frame of the Columns tab: N columns a page, pages stacked down a scroll.

        The page height is the *visible* height of this child window, so a column
        is as tall as the window and the reader sees a whole page at once. A
        document longer than one page continues on the next sheet below, which is
        the only honest thing to do with material that outruns the page: the
        alternative is silently dropping the tail, and `ColumnSplit.overflow`
        exists precisely so that this decision is the caller's.
        """
        from imgui_bundle import imgui

        from advtext.backends.imgui_draw import draw

        available = imgui.get_content_region_avail()
        page = self.page_for_columns(
            sp_from_px(max(available.x, 80.0), self.px_per_inch), self.columns
        )
        column_height = max(
            page.page.head,
            sp_from_px(max(available.y, 80.0), self.px_per_inch) - 2 * page.page.head,
        )
        layout = self.column_layout(page.column_width, column_height, self.columns)

        ppi = self.px_per_inch
        region = imgui.get_cursor_screen_pos()
        window_y = imgui.get_window_pos().y
        window_height = imgui.get_window_size().y
        draw_list = imgui.get_window_draw_list()
        colours = Palette()

        sheet_x = region.x + px_from_sp(page.page.offset, ppi)
        sheet_width_px = px_from_sp(page.page.width, ppi)
        head_px = px_from_sp(page.page.head, ppi)
        column_height_px = px_from_sp(column_height, ppi)
        sheet_height_px = column_height_px + 2 * head_px

        stats = DrawStats()
        for page_index in range(layout.pages):
            top = region.y + page_index * (sheet_height_px + PAGE_GAP_PX)
            draw_list.add_rect_filled(
                imgui.ImVec2(sheet_x, top),
                imgui.ImVec2(sheet_x + sheet_width_px, top + sheet_height_px),
                colours.page,
            )
            for index in range(layout.count):
                origin = imgui.ImVec2(
                    region.x + px_from_sp(page.column_offset(index), ppi), top + head_px
                )
                viewport = Viewport.of_pixels(
                    top_px=window_y - origin.y, height_px=window_height, px_per_inch=ppi
                )
                column = layout.indexes[page_index * layout.count + index]
                issued = draw(
                    draw_list,
                    column.visible(viewport),
                    origin,
                    fonts=_face_font,
                    palette=colours,
                    px_per_inch=ppi,
                    debug=self.view.debug,
                )
                stats = DrawStats(
                    glyphs=stats.glyphs + issued.glyphs,
                    missing=stats.missing + issued.missing,
                    rules=stats.rules + issued.rules,
                )
            for index in range(layout.count - 1):
                rule_x = region.x + px_from_sp(page.rule_offset(index), ppi)
                draw_list.add_line(
                    imgui.ImVec2(rule_x, top + head_px),
                    imgui.ImVec2(rule_x, top + head_px + column_height_px),
                    COLUMN_RULE,
                )

        total = layout.pages * (sheet_height_px + PAGE_GAP_PX) - PAGE_GAP_PX
        imgui.dummy(imgui.ImVec2(px_from_sp(page.page.width, ppi), total))
        if layout.overflow:
            _caption(f"{layout.overflow} node(s) past {MAX_COLUMN_PAGES} pages are not shown")


# ----------------------------------------------------------------------
# Drawing helpers, shared by every tab so the page is set once
# ----------------------------------------------------------------------


def _caption(text: str) -> None:
    """
    One line of chrome, in the muted colour `apply_style` reserves for it.
    """
    from imgui_bundle import imgui

    imgui.text_disabled(text)


PLATE_HEADS: Final = 3
"""
How many body leadings of air a plate gets above and below its content.

A *plate* is the page the Formula and Blocks tabs set: one short thing on a sheet
of its own. `Page.head` is one leading, which is right for a scroll of continuous
prose -- it keeps the first baseline on the same rhythm as every baseline under it
-- and wrong for a sheet with a single line on it, where a one-line margin reads
as a mis-cut scrap rather than as a page. Three is the smallest multiple at which
the sheet stops looking like a strip.
"""


def _plate(page: Page) -> Page:
    """
    The same sheet, with the head a plate wants rather than the one a scroll wants.
    """
    return replace(page, head=page.head * PLATE_HEADS)


def _paint_sheet(page: Page, px_per_inch: float, *, content_height: Scaled) -> imgui.ImVec2:
    """
    Fill the sheet at the cursor and return the text block's top-left corner.

    The one place a `Page` becomes pixels, which is the point of it: hit testing,
    culling and the draw all take the origin this returns, so a margin cannot be
    applied to some of them and not the others. That is the failure mode of
    insetting a draw call on its own, where the text moves and the mouse does not.
    """
    from imgui_bundle import imgui

    region = imgui.get_cursor_screen_pos()
    sheet_x = region.x + px_from_sp(page.offset, px_per_inch)
    height_px = px_from_sp(page.sheet_height(content_height), px_per_inch)
    imgui.get_window_draw_list().add_rect_filled(
        imgui.ImVec2(sheet_x, region.y),
        imgui.ImVec2(sheet_x + px_from_sp(page.width, px_per_inch), region.y + height_px),
        Palette().page,
    )
    return imgui.ImVec2(
        sheet_x + px_from_sp(page.margin, px_per_inch),
        region.y + px_from_sp(page.head, px_per_inch),
    )


def _draw_at(
    box: Box, origin: imgui.ImVec2, measure: CharMeasure, px_per_inch: float, debug: bool
) -> DrawStats:
    """
    Ship one packed box and draw it at a screen position.
    """
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import draw

    return draw(
        imgui.get_window_draw_list(),
        ship(box, Point(0, box.height), measure=measure),
        origin,
        fonts=_face_font,
        palette=Palette(),
        px_per_inch=px_per_inch,
        debug=debug,
    )


def _claim(page: Page, content_height: Scaled, px_per_inch: float) -> None:
    """
    Advance the cursor past a sheet the draw list wrote without advancing it.

    The draw list writes pixels and does not move the cursor, so without this the
    next widget is drawn on top of the page. `pptmstr/ui/inbox.py:722,785` had to
    do the same thing for the same reason.
    """
    from imgui_bundle import imgui

    imgui.dummy(
        imgui.ImVec2(
            px_from_sp(page.width, px_per_inch),
            px_from_sp(page.sheet_height(content_height), px_per_inch),
        )
    )


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
    read a widget as a card, no borders except the hairline under the tab bar, and
    the accent only on things that respond to a mouse. `docs/imgui-risks.md`'s
    argument that the text is what is being demonstrated applies to the chrome
    too: the most useful thing this function does is stop the default theme's blue
    tabs from being the brightest object in a photograph of a page of type.
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

    _FACES.clear()
    params = hello_imgui.FontLoadingParams()
    # The files live in the imgui-bundle wheel, not in an assets folder of ours,
    # so they are loaded by absolute path rather than through the asset system.
    params.inside_assets = False
    for face in Face:
        try:
            # `imgui_font_file`, not `font_file`: the math face needs our synthetic
            # codepoints written into its cmap or ImGui cannot find the display-size
            # summation, which is the one glyph this demo exists to show. For every
            # other face the two return the same path.
            _FACES[face] = hello_imgui.load_font(str(fontlib.imgui_font_file(face)), 16.0, params)
        except Exception:  # pragma: no cover - a missing face must not be fatal
            _FACES[face] = None


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
    Open the demo window. Needs a display, and there is one here.

    `DISPLAY=:1` is live in this sandbox and a window opens in about 0.4 s. On a
    machine without one this does not hang: GLFW aborts in about 0.6 s with
    `IM_ASSERT( glfwInitSuccess )`, and `scripts/run_demo.py` turns that into
    something readable. `make shot` photographs any tab without a terminal
    attached to a display, and `make shot-headless` is the Xvfb fallback for a
    machine that has none.

    `source` and `columns_source` both default to the files in `demo/`, falling
    back to `DEFAULT_MARKDOWN` when this is not a checkout -- `demo/` is not
    inside the package and is absent from an installed wheel.

    `tab` selects a tab on the first frame in `parse_tab_request`'s grammar, which
    is how a screenshot reaches a state no click in this environment can produce.

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
    params.app_window_params.window_geometry.size = (1100, 800)
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

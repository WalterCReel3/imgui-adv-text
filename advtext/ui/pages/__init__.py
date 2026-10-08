r"""
The demo's pages: what one is, how the app finds them, and what a page is handed.

The demo used to be a tab bar over five methods of `advtext.ui.app.App`, with the
five names written down in the app, in the Makefile and in two scripts. Three of
those copies went stale inside one batch (`tests/test_shot_all.py` has the
account). This package replaces the list with a scan: **a page is a module in
this package that defines `PAGE`**, and nothing else anywhere names it. Adding a
page is adding one file.

## The contract

A page module is `advtext/ui/pages/<anything>.py` and defines one name:

    PAGE = PageSpec(
        name="Tables",            # one word; what `--tab tables` matches
        order=120,                # position in the sidebar, ascending
        factory=TablesPage,       # called once with a PageContext
        group="Layout",           # sidebar heading it is listed under
        title="Tables",           # sidebar label, if it should differ from name
        caption="drag a column edge and the cells re-wrap",
        options=("wide",),        # words `--tab tables:wide` may carry
        shots=("", "wide"),       # the states `make shot-all` photographs
    )

`factory(context)` is called **once, on the first frame the page is shown**, and
returns the page: any object with a `draw()` method taking no arguments. That
object is where a page keeps its state -- documents, views, caches, the position
of a slider -- for as long as the app lives; nothing is kept for it elsewhere.
`draw()` is called once a frame while the page is selected, inside the app's
window, with the cursor at the top-left corner of the body and
`imgui.get_content_region_avail()` reporting what is left of the window beside
the sidebar. A page draws its own header row and its own scrolling child, as
the five original pages do.

What the factory is handed, `PageContext`:

    context.theme          advtext.style.Theme        the demo's theme
    context.measure        advtext.pack.CharMeasure   glyph advances, for packing and shipping
    context.metrics        MetricsResolver            `advtext.style.fontlib_metrics`
    context.px_per_inch    float                      the pixel density everything converts at
    context.fonts          FaceFont                   Face -> loaded ImFont, or None
    context.debug          bool                       the shared debug overlay; mutable
    context.options_for(PAGE.name) -> tuple[str, ...] the option words the launch named
    context.count_for(PAGE.name)   -> int | None      the integer the launch named
    context.app            App | None                 the demo application, see below

`context.fonts` reads the atlas at call time, so it is safe to hold: a page built
before the fonts loaded, or in a test with no atlas at all, gets `None` for every
face and `advtext.backends.imgui_draw.draw` then draws in whatever is bound.

`context.app` exists for the five original pages, whose cached material
(`App.column_layout`, `App.gallery`, `App.specimen`, the `DocumentView`) stayed
on `App` because `tests/test_app.py` pins it there. **A new page should not need
it**, and a page that does not touch it can be built from `PageContext.build()`
in a test with no app and no window.

`PageContext.build()` makes a context out of the defaults -- the stock theme,
real metrics, no fonts -- which is what a headless test of a page wants:

    page = PAGE.factory(PageContext.build())
    # one frame of a bare ImGui context, as tests/test_pages.py does
    page.draw()

## Rules a page module is held to

* **`name` is one word** (`[A-Za-z][A-Za-z0-9_-]*`). It is typed after `--tab`,
  it becomes part of a filename, and `make shot-all` splits its list on spaces.
  A label with spaces in it is what `title` is for.
* **Names are unique without regard to case**, since `--tab` matches that way.
* **A module whose name starts with an underscore is not a page** and is never
  imported by the scan. That is where a helper shared by pages goes.
* **Every other module must define `PAGE`.** One that fails to import, has no
  `PAGE`, or collides with another page's name is a `Failure`: `discover`
  reports it, the sidebar lists it under "failed to load" with the reason,
  `scripts/shot.py --list` exits non-zero, and `tests/test_pages.py` is red.
  It is never a silent omission, which is the defect the old list had.
* `options` are the words a page accepts after the colon, beyond the two every
  page accepts (`debug`, and an integer). A word that is not listed is refused
  by `advtext.ui.app.parse_tab_request` before a window opens.
* `shots` are option strings, one per photograph: `""` is the page as it opens,
  `"3"` is `--tab name:3`. The default is one photograph of the page as it
  opens. `make shot-all` shoots exactly `shot_specs()` of every page.
* Suggested `order` ranges: the five original pages hold 10 to 50; leave gaps of
  ten. Pages with the same `group` are listed together under its heading, and
  groups appear in the order of their first page.

## Why the scan reports failures instead of raising

Several people add pages at once. If one half-written module raised out of
`discover`, the app, `--tab` validation and every other page's tests would go
down with it. So the scan is tolerant and loud: the demo opens with the rest,
the broken module is named in the sidebar, and `require` -- which is what the
test and `scripts/shot.py --list` call -- raises with every reason at once.

The sheet helpers below (`paint_sheet`, `draw_at`, `claim`, `plate`, `caption`)
are the ones the original pages share. They moved here from `advtext.ui.app` so
that a new page can set a sheet the same way without importing the app.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from advtext.backends.imgui_draw import DrawStats, Palette
from advtext.nodes import Box
from advtext.pack import CharMeasure
from advtext.shipout import Point, ship
from advtext.style import MetricsResolver, Theme, char_measure, fontlib_metrics
from advtext.ui.document_view import Page
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import FaceFont
    from advtext.ui.app import App

__all__ = [
    "DEMO_DIR",
    "PLATE_HEADS",
    "Discovery",
    "Failure",
    "PageContext",
    "PageLoadError",
    "PageSpec",
    "PageView",
    "available_width",
    "caption",
    "claim",
    "debug_toggle",
    "demo_text",
    "discover",
    "draw_at",
    "paint_sheet",
    "plate",
    "require",
]

NAME_PATTERN: Final = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
OPTION_PATTERN: Final = re.compile(r"[a-z][a-z0-9_-]*\Z")

SHARED_OPTION: Final = "debug"
"""
The one option word every page accepts: the debug overlay, `PageContext.debug`.
"""

# The demo documents, beside the repository rather than inside the package. A
# checkout therefore opens on the real document and an installed wheel opens on
# `advtext.ui.app.DEFAULT_MARKDOWN`, which is the honest degradation: the files
# are genuinely not there in the second case.
DEMO_DIR = Path(__file__).resolve().parents[3] / "demo"


def demo_text(name: str) -> str | None:
    """
    A file from `demo/`, or `None` when this is not a checkout.

    `name` may have directories in it (`"stream/steps.md"`).

    `OSError` and not `FileNotFoundError`: a wheel installed into a read-only
    prefix, a broken symlink and a directory of the same name all have to come
    back as "not available" rather than as a traceback on the way to a window.
    """
    try:
        return (DEMO_DIR / name).read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - exercised only outside a checkout
        return None


# ----------------------------------------------------------------------
# The contract
# ----------------------------------------------------------------------


class PageView(Protocol):
    """
    What a factory returns: something that draws one frame of itself.
    """

    def draw(self) -> None: ...


def _no_font(face: object) -> None:
    """
    The `fonts` of a context with no atlas: every face is absent.
    """
    return None


@dataclass(slots=True)
class PageContext:
    """
    What a page is built from. One per app, shared by every page.

    Mutable on purpose, in one field: `debug` is the overlay toggle, and the
    original pages have always shared it -- ticking it on one page leaves it
    ticked on the next. Everything else is set at construction and read.
    """

    theme: Theme
    measure: CharMeasure
    px_per_inch: float = DEFAULT_PX_PER_INCH
    fonts: FaceFont = _no_font
    metrics: MetricsResolver = fontlib_metrics
    debug: bool = False
    request_page: str | None = None
    """
    The page the launch named (`--tab NAME:...`), or `None`. Read it through
    `options_for` / `count_for`, which compare names the way `--tab` does.
    """
    request_options: tuple[str, ...] = ()
    request_count: int | None = None
    app: App | None = None

    @classmethod
    def build(cls, theme: Theme | None = None, **fields: object) -> PageContext:
        """
        A context from the defaults: the stock theme, real metrics, no fonts.

        For a test, and for anything else that wants a page without the app.
        """
        return cls(
            theme=theme if theme is not None else Theme.build(),
            measure=char_measure(fontlib_metrics),
            **fields,  # type: ignore[arg-type]
        )

    def require_app(self) -> App:
        """
        The demo application, for the five original pages; a clear error without one.
        """
        if self.app is None:
            raise RuntimeError(
                "this page draws material cached on advtext.ui.app.App and was built "
                "from a context with no app; construct it through App.page(name)"
            )
        return self.app

    def _named(self, name: str) -> bool:
        return self.request_page is not None and self.request_page.lower() == name.lower()

    def options_for(self, name: str) -> tuple[str, ...]:
        """
        The option words the launch gave page `name`, or `()` if it named another.
        """
        return self.request_options if self._named(name) else ()

    def count_for(self, name: str) -> int | None:
        """
        The integer the launch gave page `name` (`--tab name:3`), or `None`.
        """
        return self.request_count if self._named(name) else None


@dataclass(frozen=True, slots=True)
class PageSpec:
    """
    A page's entry in the sidebar, and how to build it. See the module docstring.

    Validated on construction, so a page with a name `--tab` could not address
    or a shot it would itself refuse fails where it is written -- at import,
    which `discover` turns into a named `Failure` -- and not on a first frame.
    """

    name: str
    order: int
    factory: Callable[[PageContext], PageView]
    group: str = ""
    title: str = ""
    caption: str = ""
    options: tuple[str, ...] = ()
    shots: tuple[str, ...] = ("",)

    def __post_init__(self) -> None:
        if not NAME_PATTERN.match(self.name):
            raise ValueError(
                f"page name {self.name!r} must be one word of letters, digits, '-' and '_' "
                "starting with a letter: it is typed after --tab and becomes part of a "
                "filename. Put a label with spaces in `title`."
            )
        for word in self.options:
            if not OPTION_PATTERN.match(word) or word == SHARED_OPTION:
                raise ValueError(
                    f"page {self.name!r}: option {word!r} must be a lower-case word other "
                    f"than {SHARED_OPTION!r}, which every page already accepts"
                )
        if not self.shots:
            raise ValueError(
                f"page {self.name!r}: `shots` is empty, so `make shot-all` would skip the "
                'page without saying so. One photograph of the page as it opens is `("",)`.'
            )
        for shot in self.shots:
            for word in split_options(shot):
                if not self.accepts(word):
                    raise ValueError(
                        f"page {self.name!r}: shot {shot!r} carries {word!r}, which is not "
                        "one of the page's own options"
                    )

    @property
    def label(self) -> str:
        """
        What the sidebar shows.
        """
        return self.title or self.name

    def accepts(self, word: str) -> bool:
        """
        Whether `word` may follow this page's name after the colon.
        """
        return word == SHARED_OPTION or is_count(word) or word in self.options

    def shot_specs(self) -> tuple[str, ...]:
        """
        The `--tab` requests `make shot-all` photographs this page with.
        """
        slug = self.name.lower()
        return tuple(f"{slug}:{shot}" if shot else slug for shot in self.shots)


def is_count(word: str) -> bool:
    """
    Whether an option is the integer every page accepts: digits, at least 1.
    """
    return word.isdigit() and int(word) >= 1


def split_options(rest: str) -> tuple[str, ...]:
    """
    The option words of what follows the colon, stripped. `""` has none.

    An empty word between commas, or a trailing colon with nothing after it, is
    kept as `""` so the caller's "is this a word I accept" refuses it by name.
    """
    if not rest.strip():
        return ()
    return tuple(word.strip() for word in rest.split(","))


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Failure:
    """
    A module in the package that is not a usable page, and why.
    """

    module: str
    reason: str


@dataclass(frozen=True, slots=True)
class Discovery:
    """
    What the scan found: the pages in sidebar order, and what could not be one.
    """

    pages: tuple[PageSpec, ...]
    failures: tuple[Failure, ...] = ()
    modules: dict[str, str] = field(default_factory=dict, compare=False)
    """
    Lower-cased page name to the module that defined it, for error messages.
    """

    def find(self, name: str) -> PageSpec | None:
        """
        The page `--tab name` addresses, without regard to case, or `None`.
        """
        wanted = name.lower()
        for page in self.pages:
            if page.name.lower() == wanted:
                return page
        return None

    def shot_specs(self) -> tuple[str, ...]:
        """
        Every request `make shot-all` photographs, in sidebar order.
        """
        return tuple(spec for page in self.pages for spec in page.shot_specs())


class PageLoadError(RuntimeError):
    """
    One or more modules in the pages package are not usable pages.
    """


def discover(package: str = __name__) -> Discovery:
    """
    Import every module of `package` that could be a page and collect its `PAGE`.

    Tolerant and complete: every module is tried, and one that cannot be a page
    becomes a `Failure` instead of an exception, for the reason the module
    docstring gives. `require` is the strict form.

    Not cached. A module that imported is in `sys.modules` and costs a dict
    lookup the second time; one that failed is tried again, which is what lets
    a page fixed on disk appear without restarting whatever holds this package.
    `advtext.ui.app.App` scans once at construction and keeps the result, so
    nothing here runs per frame.
    """
    root = importlib.import_module(package)
    found: list[tuple[PageSpec, str]] = []
    failures: list[Failure] = []
    for info in sorted(pkgutil.iter_modules(root.__path__), key=lambda item: item.name):
        if info.name.startswith("_"):
            continue
        qualified = f"{package}.{info.name}"
        try:
            module = importlib.import_module(qualified)
        except Exception as error:  # any failure to import is the finding
            failures.append(Failure(qualified, f"{type(error).__name__}: {error}"))
            continue
        page = getattr(module, "PAGE", None)
        if not isinstance(page, PageSpec):
            failures.append(
                Failure(
                    qualified,
                    (
                        "defines no PAGE"
                        if page is None
                        else f"PAGE is a {type(page).__name__}, not a PageSpec"
                    ),
                )
            )
            continue
        found.append((page, qualified))

    modules: dict[str, str] = {}
    pages: list[PageSpec] = []
    for page, qualified in found:
        key = page.name.lower()
        if key in modules:
            failures.append(
                Failure(qualified, f"its name {page.name!r} is already taken by {modules[key]}")
            )
            continue
        modules[key] = qualified
        pages.append(page)
    pages.sort(key=lambda page: (page.order, page.name.lower()))
    return Discovery(tuple(pages), tuple(failures), modules)


def require(package: str = __name__) -> Discovery:
    """
    `discover`, raising `PageLoadError` naming every module that is not a page.
    """
    found = discover(package)
    if found.failures:
        raise PageLoadError(
            "not every module in the pages package is a page:\n"
            + "\n".join(f"  {failure.module}: {failure.reason}" for failure in found.failures)
        )
    return found


# ----------------------------------------------------------------------
# Drawing helpers, shared by pages so a sheet is set one way
# ----------------------------------------------------------------------


def caption(text: str) -> None:
    """
    One line of chrome, in the muted colour `advtext.ui.app.apply_style` reserves for it.
    """
    from imgui_bundle import imgui

    imgui.text_disabled(text)


def debug_toggle(context: PageContext) -> None:
    """
    The "debug overlay" checkbox, bound to the flag every page shares.
    """
    from imgui_bundle import imgui

    _, context.debug = imgui.checkbox("debug overlay", context.debug)


def available_width(context: PageContext) -> Scaled:
    """
    The width left in the window at the cursor, in scaled points, never under 80 px.
    """
    from imgui_bundle import imgui

    return sp_from_px(max(imgui.get_content_region_avail().x, 80.0), context.px_per_inch)


PLATE_HEADS: Final = 3
"""
How many body leadings of air a plate gets above and below its content.

A *plate* is the page the Formula and Blocks pages set: one short thing on a sheet
of its own. `Page.head` is one leading, which is right for a scroll of continuous
prose -- it keeps the first baseline on the same rhythm as every baseline under it
-- and wrong for a sheet with a single line on it, where a one-line margin reads
as a mis-cut scrap rather than as a page. Three is the smallest multiple at which
the sheet stops looking like a strip.
"""


def plate(page: Page) -> Page:
    """
    The same sheet, with the head a plate wants rather than the one a scroll wants.
    """
    return replace(page, head=page.head * PLATE_HEADS)


def paint_sheet(page: Page, px_per_inch: float, *, content_height: Scaled) -> imgui.ImVec2:
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


def draw_at(context: PageContext, box: Box, origin: imgui.ImVec2, *, debug: bool) -> DrawStats:
    """
    Ship one packed box and draw it at a screen position.
    """
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import draw

    return draw(
        imgui.get_window_draw_list(),
        ship(box, Point(0, box.height), measure=context.measure),
        origin,
        fonts=context.fonts,
        palette=Palette(),
        px_per_inch=context.px_per_inch,
        debug=debug,
    )


def claim(page: Page, content_height: Scaled, px_per_inch: float) -> None:
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

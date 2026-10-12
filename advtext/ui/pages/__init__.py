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

    context.theme          advtext.theme.Theme        the demo's theme
    context.px_per_inch    float                      the pixel density everything converts at
    context.fonts          FaceFont                   Face -> an ImFont to push, or None
    context.metrics        MetricsResolver            `face_metrics`; measures a face when called
    context.debug          bool                       the shared debug overlay; mutable
    context.source         str | None                 the markdown the launch named
    context.columns_source str | None                 the Columns page's markdown
    context.options_for(PAGE.name) -> tuple[str, ...] the option words the launch named
    context.count_for(PAGE.name)   -> int | None      the integer the launch named

`context.fonts` reads the atlas at call time, so it is safe to hold: a page built
before the fonts loaded, or in a test with no atlas at all, gets `None` for every
face. In the app with the imtypeset library loaded it answers the library's font
for the role, which is the only copy of the face in the atlas.

**A page sets its text through the typeset layer and nothing else**
(`advtext.ui.typeset_view` and its siblings). When
`advtext.typesetter.ready()` is false it draws one wrapped line saying why
(`advtext.ui.pages.typeset.why_not()`) and builds nothing. The context
therefore carries no glyph measure and no draw backend; until 2026-10-11 it
carried `measure`, the old core's `CharMeasure`.

**A page does not reach the shell.** What the launch named is on the context
(`source`, `columns_source`, `count_for`, `options_for`), so every page can
be built from `PageContext.build()` in a test with no app and no window.
Until tranche 5 the context carried the `App` itself, for the pages whose
material was cached there.

`PageContext.build()` makes a context out of the defaults -- the stock theme,
no fonts, no sources -- which is what a headless test of a page wants:

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

The two helpers below (`caption`, `debug_toggle`) are the chrome the pages
share.

## What importing this package loads

Every page module imports this package for `PageSpec` and `PageContext`, so
what it loads every page loads: `advtext.theme` and `advtext.primitives`,
which is what a `Theme` needs (`tests/test_typeset_closure.py` holds the
set). Nothing of the reference layout core is loaded here at import, when a
context is made, or by any function below, with one exception that is named:
`face_metrics`, when it is called.

Until tranche 5 (2026-10-11) this package also carried the sheet helpers of
the pages that drew through the old ImGui backend (`paint_sheet`, `draw_at`,
`claim`, `plate`, `PLATE_HEADS`, `available_width`), `PageContext.measure`,
and `PageContext.app` with `require_app`. No page called any of them once
the fallbacks to the old views were removed, and they are deleted.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from advtext.primitives import DEFAULT_PX_PER_INCH
from advtext.theme import Theme

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

    from advtext.fontmetrics import FontMetrics
    from advtext.primitives import Face

    FaceFont = Callable[[Face], "imgui.ImFont | None"]
    MetricsResolver = Callable[[str], FontMetrics]

__all__ = [
    "DEMO_DIR",
    "Discovery",
    "Failure",
    "PageContext",
    "PageLoadError",
    "PageSpec",
    "PageView",
    "caption",
    "debug_toggle",
    "demo_text",
    "discover",
    "face_metrics",
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


def face_metrics(key: str) -> FontMetrics:
    """
    A face's measurements at a size: the default of `PageContext.metrics`.

    It is `advtext.typeset_metrics.face_metrics`, asked at the call: **the
    library, once `typesetter.load_fonts()` has succeeded**, and nothing of
    the old core is loaded then. Before that (the app builds its pages
    before there is a window) and without the library it is
    `advtext.style.fontlib_metrics`, read from that module at the call, so
    a caller who replaces the name there is still the one asked: the one
    thing a page context can still take from the old core, and only then.
    Its use is `Theme.at_pixel_height(height, metrics=context.metrics)`,
    which needs a face's ascent, descent, em and eleven advances to size a
    theme to a pixel height. The library's answer has no ink boxes and no
    kerns (`advtext.typeset_metrics.LibraryMetrics`).

    `key` is a font key as `advtext.theme.font_key` makes it.
    """
    from advtext import typeset_metrics

    return typeset_metrics.face_metrics(key)


@dataclass(slots=True)
class PageContext:
    """
    What a page is built from. One per app, shared by every page.

    Mutable on purpose, in one field: `debug` is the overlay toggle, and the
    original pages have always shared it -- ticking it on one page leaves it
    ticked on the next. Everything else is set at construction and read.
    """

    theme: Theme
    px_per_inch: float = DEFAULT_PX_PER_INCH
    fonts: FaceFont = _no_font
    """
    `Face` to the `ImFont` a page may push for it, or `None`. In the app with
    the library loaded it answers the library's font for the role
    (`advtext.ui.app._face_font`).
    """
    metrics: MetricsResolver = face_metrics
    """
    See `face_metrics`: resolved when called, never when a context is made.
    """
    debug: bool = False
    request_page: str | None = None
    """
    The page the launch named (`--tab NAME:...`), or `None`. Read it through
    `options_for` / `count_for`, which compare names the way `--tab` does.
    """
    request_options: tuple[str, ...] = ()
    request_count: int | None = None
    source: str | None = None
    """
    The markdown the launch named (`run`'s `source`), or `None` when the
    context was made without one: a page then reads its own file with
    `demo_text`.
    """
    columns_source: str | None = None
    """
    The markdown for the Columns page, or `None` to use `source`.
    """

    @classmethod
    def build(cls, theme: Theme | None = None, **fields: object) -> PageContext:
        """
        A context from the defaults: the stock theme, no fonts, no sources.

        For a test, and for anything else that wants a page without the app.
        It imports nothing: `metrics` measures a face when it is called.
        """
        return cls(
            theme=theme if theme is not None else Theme.build(),
            **fields,  # type: ignore[arg-type]
        )

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
    max_count: int | None = None
    """
    The most the launch's integer may be for this page, or `None` for any.

    The integer means what the page reads it as (`PageContext.count_for`): a
    page that hands it to something with a limit states the limit here, and
    `advtext.ui.app.parse_tab_request` refuses a larger one before a window
    opens. Without it the refusal came from inside the page's first `draw`
    (`--tab columns:4097`, until 2026-10-11).
    """

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
        if is_count(word):
            return self.max_count is None or int(word) <= self.max_count
        return word == SHARED_OPTION or word in self.options

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
# Chrome the pages share
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

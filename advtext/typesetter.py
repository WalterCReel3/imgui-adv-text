"""
imtypeset beside advtext: whether it is there, its faces, and the names of a description.

**Experimental** (branch `experimental/imtypeset-adoption`, step A1 of
`../imtypeset/docs/advtext-rework-plan.md` section 6.3). A host, or one of
the `Typeset*` views built on it, asks for this module by name
(`from advtext import typesetter`); `load_fonts`, `ready` and `reason` are
also names of the facade.

**Why `typesetter` and not `typeset`.** When this module was named,
`advtext.typeset` was taken: it was the facade's formula function
(`advtext.mathtext.typeset`). A submodule of that name would have replaced it
the moment anything imported the submodule -- Python binds a submodule as an
attribute of its package. `advtext.mathtext` was deleted in tranche 5 and the
name is free; this module keeps the one it has.

**Loading, gated.** imtypeset is a sidecar library built for ONE installed
imgui-bundle wheel, with a ctypes package in front of it. It is looked for in
this order, and `pairing()` says which was taken:

1.  **The environment** (`ROUTE_ENVIRONMENT`), when `IMTYPESET_LIBRARY` names
    the library: the development override, and until imtypeset can be
    installed the only route there is. The package is found on `sys.path`, or
    in the directory `IMTYPESET_PYTHON` names (`<imtypeset>/python`), which is
    added to the END of `sys.path` at that moment and not before; `make ...
    TYPESET=1` sets both variables. A variable of its own rather than
    `PYTHONPATH` because a child process that is given a `PYTHONPATH` of its
    own -- every script `tests/conftest.py`'s `window` runs -- would lose the
    package and keep the library, and then quietly draw the old way.
2.  **An installed distribution** (`ROUTE_DISTRIBUTION`), when the variable is
    not set and `importlib.metadata` finds a distribution named `imtypeset`.
    It is then imported with no variable set, and is expected to find the
    library it carries by itself. No such distribution exists yet (2026-10-11,
    HANDOFF-imtypeset.md, request H3); the route is tested with stand-ins
    (`tests/test_typesetter_pairing.py`). Metadata, and not merely a package
    that can be imported, because a source directory of imtypeset on the path
    -- which is what route 1 leaves behind in a process -- is importable too
    and carries no library. An application frozen without package metadata
    therefore names its library by the variable.
3.  **Neither**: not loaded, and `reason()` says `IMTYPESET_LIBRARY is not set`.

`import imtypeset` checks the
library against the wheel that is running and raises `ImportError` with a
sentence when it refuses. `module()` is where that import
happens, once; whatever goes wrong, it answers `None` and `reason()` keeps the
sentence. So the rule for everything built on this is one line: **when
`module()` is `None`, nothing here draws** (a view says so; there is no other
renderer since tranche 5). Importing this module imports nothing of imtypeset
and cannot raise because of it.

`load_fonts()` makes the library's context and gives its roles advtext's font
files. It belongs in hello_imgui's `load_additional_fonts` callback, after the
host's own faces, and **never in `post_init`**: the runner empties the atlas
before it calls `load_additional_fonts`, so a face added earlier is gone by the
first frame. `ready()` says whether that has happened; a view checks it before
it draws.

**The description.** imtypeset takes *text* with runs, a block at a time.
`advtext.typeset_markdown` makes that description straight from markdown
(`parse_markdown`, `MarkdownConverter`), and it is what every view hands the
library. Until tranche 5 this module had a second way to one: `Converter`,
which walked the old core's node material (`TextBlock.material`: `CharNode`,
`Glue`, `Kern`, `Penalty`, boxes) back into a string. It is deleted with the
last caller of that path; what it answered for the test corpus is frozen in
`tests/data/material_descriptions.json`, which the typeset tests are held to.

The description is plain tuples in the field order of `imtypeset.Block` and
`imtypeset.Run`, with the header's enumerators as integers, so it is built,
tested and searched without the library. **The tuples and the integers are
`advtext.description`'s**, and the ones this module always exported are still
names of this module. `imtypeset.Document` takes the tuples as they are; only
the styles need the library's own struct (`block_styles`).

Offsets are indices into the block's `str` (codepoints). The Python package
converts to the library's byte offsets itself.

**What importing this module loads of advtext: `advtext.description`, and
nothing else.** The gate, the description types and `block_styles` need no
more. `FACE_ROLE` and `ALIGN`, keyed by enums that live in
`advtext.primitives` and `advtext.theme`, are made when first read;
`load_fonts` imports `advtext.fontlib` for the font files (the one use of the
old core left here: `.concerns/lead--tranche-5.md`, decision 5).

Ported from `../imtypeset/python/spike_advtext/convert.py`. Where this differs
from the spike, and why, is in `.concerns/IT-A1--builder--result.md`.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from advtext.description import (
    ALIGNS,
    BLOCK_HARD_BREAKS,
    BLOCK_TABLE_HEADER,
    FACE_DEFAULT,
    FACE_ROLES,
    KIND_CODE,
    KIND_HEADING,
    KIND_HOST,
    KIND_LIST_ITEM,
    KIND_PARAGRAPH,
    KIND_RULE,
    KIND_TABLE,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    RUN_NO_BREAK,
    BlockDescription,
    CellDescription,
    ColumnDescription,
    Description,
    LinkRow,
    RunDescription,
    StyleDescription,
    cell_spans,
    table_text,
    with_tags,
)

if TYPE_CHECKING:  # pragma: no cover - for types only
    from advtext.primitives import Face
    from advtext.theme import Align, Theme

    FACE_ROLE: dict[Face, int]
    ALIGN: dict[Align, int]

__all__ = [
    "ALIGN",
    "BLOCK_HARD_BREAKS",
    "BLOCK_TABLE_HEADER",
    "BlockDescription",
    "CellDescription",
    "ColumnDescription",
    "Description",
    "FACE_DEFAULT",
    "FACE_ROLE",
    "KIND_CODE",
    "KIND_HEADING",
    "KIND_HOST",
    "KIND_LIST_ITEM",
    "KIND_PARAGRAPH",
    "KIND_RULE",
    "KIND_TABLE",
    "LIBRARY_VARIABLE",
    "PACKAGE_VARIABLE",
    "ROUTE_DISTRIBUTION",
    "ROUTE_ENVIRONMENT",
    "ROUTE_NONE",
    "LinkRow",
    "RUN_DISPLAY_FORMULA",
    "RUN_FORMULA",
    "RUN_NO_BREAK",
    "RunDescription",
    "StyleDescription",
    "base_style",
    "block_styles",
    "cell_spans",
    "disable",
    "load_fonts",
    "module",
    "note",
    "pairing",
    "ready",
    "reason",
    "table_text",
    "trouble",
    "unload",
    "window_draw_list",
]

# The description's types and integers are `advtext.description`'s, imported
# above and re-exported: `typesetter.BlockDescription is description.BlockDescription`.
_with_tags = with_tags

LIBRARY_VARIABLE = "IMTYPESET_LIBRARY"
PACKAGE_VARIABLE = "IMTYPESET_PYTHON"

# How the package was found: `pairing()["route"]`.
ROUTE_ENVIRONMENT = "environment"
ROUTE_DISTRIBUTION = "distribution"
ROUTE_NONE = "none"

_DISTRIBUTION = "imtypeset"


def __getattr__(name: str) -> Any:
    """
    `FACE_ROLE` and `ALIGN`, made the first time either is read.

    `advtext.description` has both tables by member NAME. Keyed by the
    members themselves they need the enums, `Face` from
    `advtext.primitives` and `Align` from `advtext.theme`, and importing
    this module should not load those for a caller that never asks.

    `FACE_ROLE` is which imtypeset role each advtext `Face` is registered
    under and named by. Both are roles *a font file is registered under*, so
    a theme's own mapping of document roles onto faces
    (`advtext.theme.Faces`) has already been applied by the time a node
    carries a font key.
    """
    made: dict[Any, int]
    if name == "FACE_ROLE":
        faces = importlib.import_module("advtext.primitives").Face
        made = {face: FACE_ROLES[face.name] for face in faces}
    elif name == "ALIGN":
        aligns = importlib.import_module("advtext.theme").Align
        made = {align: ALIGNS[align.name] for align in aligns}
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = made
    return made


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_NOT_SET = f"{LIBRARY_VARIABLE} is not set"

_ts: Any = None
# The package once imported, kept through `disable`: `_ts` is what answers
# "is the library in use", and this is what `unload` destroys the context with
# when it no longer is.
_package: Any = None
_tried = False
_route = ROUTE_NONE
# The installed distribution as "imtypeset <version>", "" when there is none,
# `None` until it has been looked for. Looked for once: a view asks `module()`
# every frame, and the answer is a walk over `sys.path`.
_installed: str | None = None
_reason = _NOT_SET
_disabled = False
_ready = False
_trouble = ""
_logged: set[str] = set()
_log = logging.getLogger("advtext.typesetter")


def module() -> Any:
    """
    The imtypeset package, or `None` when advtext should draw as it always has.

    The first call with `IMTYPESET_LIBRARY` set, or with an `imtypeset`
    distribution installed, is the import, and with it the library's gate (a
    child interpreter the first time a library meets a wheel, about a third
    of a second; in-process afterwards). It is tried once: a refusal is
    remembered and `reason()` holds it. While the variable is unset and no
    distribution is installed nothing is imported, and nothing is remembered
    but that no distribution was found, so setting the variable later in the
    same process still works. (Installing one later in the same process does
    not: it is looked for once.)

    The variable wins over an installed distribution; the module docstring
    has the order and why.

    Not `None` means the package is imported and accepted. It does not mean
    there is a context or a font: `ready()` says that.
    """
    global _ts, _package, _tried, _route, _reason
    if _ts is not None or _disabled or _tried:
        return _ts
    named = bool(os.environ.get(LIBRARY_VARIABLE))
    if not named and not _distribution():
        _reason = _NOT_SET
        return None
    _tried = True
    try:
        # Last on the path, so the directory can add a package and can never
        # stand in front of one advtext or its host already imports.
        where = os.environ.get(PACKAGE_VARIABLE) if named else None
        if where and where not in sys.path:
            sys.path.append(where)
        # By name, so that neither a type checker nor a reader looks for the
        # package where advtext's own modules are: it is found on the path the
        # host set, or not at all.
        loaded = importlib.import_module("imtypeset")
    except Exception as exc:  # noqa: BLE001 -- any failure here means "draw as before"
        _reason = f"{type(exc).__name__}: {exc}"
        if not named:
            _reason = f"the installed {_distribution()} did not load: {_reason}"
        _say(f"imtypeset is not in use: {_reason}")
        return None
    _reason = ""
    _route = ROUTE_ENVIRONMENT if named else ROUTE_DISTRIBUTION
    _ts = _package = loaded
    return _ts


def _distribution() -> str:
    """
    The installed `imtypeset` distribution as `imtypeset <version>`; empty when there is none.

    Asked of `importlib.metadata`, which imports nothing of the package. Any
    failure to read the metadata is "there is none".
    """
    global _installed
    if _installed is None:
        try:
            from importlib import metadata

            found = metadata.distribution(_DISTRIBUTION)
            _installed = f"{_DISTRIBUTION} {found.version or ''}".strip()
        except Exception:  # noqa: BLE001 -- not installed, or not readable: the same answer
            _installed = ""
    return _installed


def pairing() -> dict[str, str | None]:
    """
    Which imtypeset is paired with which imgui-bundle, for an About box and a bug report.

    It asks `module()` first, so the first call may be the import. Every
    value is a string or `None`, and the keys are always these:

    - `route`: `ROUTE_ENVIRONMENT`, `ROUTE_DISTRIBUTION` or `ROUTE_NONE` --
      how the package that is loaded was found. It stays what it was after
      `disable`: the pairing is still what is in the process.
    - `reason`: `reason()`. Empty while the library is in use.
    - `library`: the shared library's path.
    - `package`: the directory of the Python package that loaded it. Under
      `ROUTE_ENVIRONMENT` with a distribution also installed this is where to
      see which of the two packages met the library.
    - `distribution`: `imtypeset <version>` when one is installed, whichever
      route was taken.
    - `imtypeset_version`: the library's own version.
    - `imgui_version`: the Dear ImGui the library was compiled against.
    - `wheel_version`: the imgui-bundle that is running, which the library's
      import gate accepted it against.
    - `built_for`: the imgui-bundle the distribution DECLARES it was built
      for (its `Requires-Dist`, e.g. `imgui-bundle==1.92.900`), under
      `ROUTE_DISTRIBUTION` only. `None` under `ROUTE_ENVIRONMENT`: a library
      built by `make typeset-lib` does not record the wheel version it was
      linked against, only accepts or refuses the one it meets.
    - `headers`: `fork:<commit>` when the library was compiled against the
      wheel's own Dear ImGui headers, `stand-in:...` when against upstream's.
    - `accepted_by`: `imgui-check+probe` or `probe`, how the gate accepted it.

    Whatever the package cannot tell is `None`, and a package that raises
    when asked is a `trouble()`, never an exception here.
    """
    module()
    package = _package
    answer: dict[str, str | None] = {
        "route": _route if package is not None else ROUTE_NONE,
        "reason": _reason,
        "library": None,
        "package": None,
        "distribution": _distribution() or None,
        "imtypeset_version": None,
        "imgui_version": None,
        "wheel_version": None,
        "built_for": None,
        "headers": None,
        "accepted_by": None,
    }
    if package is None:
        return answer

    def said(value: Any) -> str | None:
        return None if value is None or value == "" else str(value)

    try:
        answer["package"] = said(os.path.dirname(getattr(package, "__file__", None) or ""))
        info = dict(package.host_info())
        gate = dict(info.get("bundle") or {})
        answer["library"] = said(info.get("library"))
        answer["imtypeset_version"] = said(info.get("imtypeset_version"))
        answer["imgui_version"] = said(info.get("imgui_version"))
        answer["wheel_version"] = said(gate.get("wheel_version"))
        answer["headers"] = said(gate.get("headers"))
        answer["accepted_by"] = said(gate.get("accepted_by"))
        if _route == ROUTE_DISTRIBUTION:
            from importlib import metadata

            for requirement in metadata.requires(_DISTRIBUTION) or ():
                name = requirement.split(";")[0].strip()
                if name.lower().replace("_", "-").replace(".", "-").startswith("imgui-bundle"):
                    answer["built_for"] = name
                    break
    except Exception as exc:  # noqa: BLE001 -- a report must not be what fails
        note(f"pairing: {type(exc).__name__}: {exc}")
    return answer


def reason() -> str:
    """
    Why `module()` is `None`, as one sentence; empty when it is not.

    Meaningful after `module()` has been asked. Before that it says the
    variable is not set, which may no longer be true. It does not say which
    route a loaded package came by -- it is empty then, and views test it for
    that; `pairing()["route"]` does.
    """
    return _reason


def ready() -> bool:
    """
    Whether `load_fonts()` has made the context and added the faces.

    False again once `disable` has switched the library off.
    """
    return _ready and _ts is not None


def load_fonts(faces: Iterable[Face] | None = None) -> bool:
    """
    Make the imtypeset context and give its roles advtext's font files. True when it is ready.

    Call it at the end of hello_imgui's `load_additional_fonts` callback, after
    the host's own faces (`advtext.ui.fonts.load_faces`), so `Fonts[0]` stays
    the host's. Never from `post_init`; the module docstring says why. It
    needs a current Dear ImGui context and says so, rather than crash, when
    there is none.

    `faces` are the roles to register, by default every `Face`: each gets
    `advtext.fontlib.font_file(face)` under `FACE_ROLE[face]`, so a font a
    host registered with `advtext.fontlib.register_font` is the one imtypeset
    draws too, and the two measure the same file. A role with no file
    (`MissingFontError`) is left out and said in `trouble()`; text in it is
    then set in the document's face. imtypeset loads each file into the atlas
    itself, so a face advtext also loaded is there twice.

    Any other failure -- the library refusing a font -- switches the library
    off for the run (`disable`), because a view that drew with half its faces
    would be wrong in a way nobody asked for.

    **Every call makes a new imtypeset context, in the Dear ImGui context
    that is current, and destroys the one there was.** A handle says a
    context exists and never that its ImGui context still does
    (`../imtypeset/docs/advtext-swap-status.md`, answer (c)): a context kept
    from an ImGui context that has since been destroyed refuses `add_font`,
    and until 2026-10-11 this function reused one it found, so a process
    that made a second ImGui context without calling `unload()` in between
    had the library switched off for the rest of its run. Destroying is safe
    at any time. What it costs: **a `Document` or `Paragraph` made before
    this call is closed** (using it raises `ValueError`), as after
    `unload()`; a view that keeps one makes it again, as it does then.
    hello_imgui calls the callback once, so a host sees none of this.

    `unload()` is still what whoever destroys the ImGui context calls first,
    so that nothing of the library outlives its atlas.
    """
    global _ready
    _ready = False
    ts = module()
    if ts is None:
        return False
    try:
        imgui_bundle = importlib.import_module("imgui_bundle")
        if imgui_bundle.imgui.get_current_context() is None:
            note("load_fonts was called with no Dear ImGui context; nothing was loaded")
            return False
        fontlib = importlib.import_module("advtext.fontlib")
        if faces is None:
            faces = tuple(importlib.import_module("advtext.primitives").Face)
        if ts.current_context() is not None:
            ts.destroy_context()
        ts.create_context()
        missing: list[str] = []
        for face in faces:
            try:
                path = fontlib.font_file(face)
            except fontlib.MissingFontError:
                missing.append(face.value)
                continue
            ts.add_font(FACE_ROLES[face.name], str(path))
        if missing:
            note(f"no font file for {', '.join(missing)}; set in the document's face")
    except Exception as exc:  # noqa: BLE001 -- any failure here means "draw as before"
        disable(f"{type(exc).__name__}: {exc}")
        return False
    _ready = True
    return True


def unload() -> None:
    """
    Destroy the imtypeset context, and with it every `Document` made in it.

    For whoever owns the Dear ImGui context, before destroying it. A
    `Document` kept across this is closed: using it raises `ValueError`.
    `ready()` is false afterwards and `load_fonts()` makes it true again;
    `module()` is unchanged. Does nothing when the package was never
    imported. **After `disable` it still destroys the context**: `disable`
    releases nothing itself (it is called from inside a draw, with documents
    in use further up the stack), so this is where a library that was
    switched off gives back its context and its fonts' share of the atlas.
    """
    global _ready
    _ready = False
    package = _package
    if package is None:
        return
    try:
        if package.current_context() is not None:
            package.destroy_context()
    except Exception as exc:  # noqa: BLE001 -- see load_fonts
        if _ts is not None:
            disable(f"{type(exc).__name__}: {exc}")
        else:
            note(f"unload: {type(exc).__name__}: {exc}")


def window_draw_list() -> int | None:
    """
    What to hand `imtypeset.Document.draw` for the current window's draw list: `None`.

    Kept for callers written when the library took an address and the
    binding could not give one: this used to find Dear ImGui's
    `GetWindowDrawList` by its mangled C++ name in the wheel's binary. Since
    imtypeset commit `12d77ac` a draw list of `None` IS the current window's
    (`Document.draw(None, pos)`, `Paragraph.draw(None, pos)`), so there is no
    symbol to find and nothing to call. `document.draw(None, pos)` says the
    same thing without this function.

    As before, only between `begin` and `end` of a window, and it raises
    `RuntimeError` when `load_fonts()` has not succeeded.
    """
    if not ready():
        raise RuntimeError("advtext.typesetter.load_fonts() has not succeeded; see reason()")
    return None


def trouble() -> str:
    """
    The last failure that was got over without switching the library off; empty if none.
    """
    return _trouble


def note(why: str) -> None:
    """
    Record a failure that was got over: the library stays in use.
    """
    global _trouble
    _trouble = why
    _say(f"imtypeset: {why}")


def disable(why: str) -> None:
    """
    Stop using the library for the rest of the run, and remember why.

    What a view calls when its imtypeset path raised mid-draw: from then on
    `module()` is `None`, `reason()` is `why`, and the caller draws the old
    way. Nothing re-enables it.

    It releases nothing: the context, its documents and its fonts stay as
    they are until `unload()`, which still works afterwards.
    """
    global _ts, _reason, _disabled, _ready
    _ts = None
    _ready = False
    _disabled = True
    _reason = why
    _say(f"imtypeset is switched off for this run: {why}")


def _say(message: str) -> None:
    """
    A warning, once per distinct message: a view calls this from its draw.
    """
    if message not in _logged and len(_logged) < 64:
        _logged.add(message)
        _log.warning("%s", message)


def _forget() -> None:
    """
    Back to the state at import. For tests; a host has no use for it.

    It forgets what this module knows, not what the process did: an imported
    imtypeset stays in `sys.modules` and its context stays made.
    """
    global _ts, _package, _tried, _route, _installed, _reason, _disabled, _ready, _trouble
    _ts = None
    _package = None
    _tried = False
    _route = ROUTE_NONE
    _installed = None
    _reason = _NOT_SET
    _disabled = False
    _ready = False
    _trouble = ""
    _logged.clear()


# ---------------------------------------------------------------------------
# What needs the library
# ---------------------------------------------------------------------------


def block_styles(styles: Iterable[StyleDescription]) -> list[Any]:
    """
    `styles` as `imtypeset.BlockStyle` structs, which is what a `Document` edit takes.

    For a first `set_blocks`, all of `Description.styles`; for a
    `replace_blocks`, the ones the describe added, since the library appends
    what it is given to what the document has. Raises `RuntimeError` naming
    `reason()` when the library is not in use.
    """
    ts = _must()
    return [ts.BlockStyle(**style._asdict()) for style in styles]


def base_style(theme: Theme, ink: int = 0) -> Any:
    """
    The `imtypeset.Style` a document described from `theme` is laid out with.

    The em is the theme's paragraph size in pixels, which is what every
    `StyleDescription.Scale` is a multiple of. `ink` is an ImGui packed colour
    (`Palette.ink`); 0 leaves the library's default. Raises `RuntimeError`
    naming `reason()` when the library is not in use.
    """
    ts = _must()
    paragraph = importlib.import_module("advtext.theme").BlockKind.PARAGRAPH
    to_px = importlib.import_module("advtext.primitives").px_from_sp
    return ts.Style(
        EmSize=to_px(theme.style(paragraph).font.size, theme.px_per_inch),
        PixelsPerInch=theme.px_per_inch,
        Color=ink,
    )


def _must() -> Any:
    ts = module()
    if ts is None:
        raise RuntimeError(f"imtypeset is not in use: {reason()}")
    return ts

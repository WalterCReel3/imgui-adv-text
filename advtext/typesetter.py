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

**What a host asks, beside `module()` and `reason()`** (2026-10-12, asked for
by pptmstr, the first host; none of these is on the facade, reach them as
`advtext.typesetter.<name>`):

- `kind()`, a `Kind`: ready, not installed, refused, failed, unsupported.
  The sentence is still `reason()`; the kind is what to branch on.
- `reset()`: the way back from `disable` or a refusal. `unsupported(why)`:
  the host's word that this platform has no library.
- `missing(package)` and `REQUIRED`: the names of imtypeset this advtext
  calls. `module()` refuses a package that lacks one, so that a partial
  update falls back at the gate and does not fail inside a draw.
- `verdict(library, python_path)`: what a NEW process would say, asked of a
  child, with nothing loaded here and nothing remembered. The same from a
  shell: `python -m advtext.typesetter` prints `pairing()` as one line of
  JSON and exits by the kind (`EXIT_CODES`), with no window.
- `font(face)`: the `ImFont` the library draws a role with.

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

import enum
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
    "EXIT_CODES",
    "Kind",
    "LIBRARY_VARIABLE",
    "PACKAGE_VARIABLE",
    "REQUIRED",
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
    "font",
    "kind",
    "load_fonts",
    "missing",
    "module",
    "note",
    "pairing",
    "ready",
    "reason",
    "reset",
    "table_text",
    "trouble",
    "unload",
    "unsupported",
    "verdict",
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


class Kind(enum.Enum):
    """
    Which of the things that can be so of the library is so: `kind()`, `pairing()["kind"]`.

    The sentence is `reason()`; this is what a host branches on. The values
    are strings, and they are what `pairing()` and the command line print.

    - `READY`: the package is imported, the library's gate accepted the
      wheel, and it has every name advtext calls. `module()` is not `None`.
      **It says nothing of fonts**: `ready()` does.
    - `NOT_INSTALLED`: `IMTYPESET_LIBRARY` is not set and no `imtypeset`
      distribution is installed. Nothing was imported and nothing is
      remembered. A normal state where a product ships without the library.
    - `REFUSED`: something was found and cannot be used: the import raised
      (the library's gate against the running wheel, a library that is not
      there, a package that is not on the path), or the package lacks names
      this advtext calls (`missing`). A fault somebody has to act on.
    - `FAILED`: it was accepted, and a library error has since switched it
      off (`disable`): a font it would not take in `load_fonts`, or a draw.
    - `UNSUPPORTED`: nothing was found, and the host has said that nothing
      is to be found here (`unsupported(why)`). **advtext cannot tell this
      from `NOT_INSTALLED` by itself**: imtypeset has no distribution yet
      (2026-10-12, HANDOFF-imtypeset.md, H3) and so no way of saying "there
      is no library for this platform", and advtext does not guess from
      `sys.platform`. Until a distribution can say it, only a host does.
    - `UNCHECKED`: `verdict()` could not ask (a frozen application, or the
      child interpreter did not answer). Never the answer of `kind()`.
    """

    READY = "ready"
    NOT_INSTALLED = "not-installed"
    REFUSED = "refused"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNCHECKED = "unchecked"


# What `python -m advtext.typesetter` exits with. 1 and 2 are left to the
# interpreter (an uncaught exception, a usage error).
EXIT_CODES: dict[Kind, int] = {
    Kind.READY: 0,
    Kind.NOT_INSTALLED: 3,
    Kind.REFUSED: 4,
    Kind.FAILED: 5,
    Kind.UNSUPPORTED: 6,
    Kind.UNCHECKED: 7,
}

# Every name of imtypeset that advtext calls, by what it is a name OF: `""`
# is the package itself, anything else a class or an enum of the package.
# `module()` holds the package it imported to this list (`missing`) and
# refuses one that lacks any of it, so that new advtext beside an old
# imtypeset falls back at the gate and does not raise AttributeError inside a
# draw. THE ONE PLACE: `tests/test_typesetter_kinds.py` reads advtext's
# sources and fails when one of them uses a name that is not here.
#
# What is not here, because advtext reads it and never names it: the fields of
# what the library ANSWERS (`DocumentHit`, `BlockGeometry`, `Line`, the
# statistics), and the keywords of its functions. `Mark` is not here either:
# a mark is handed over as a plain tuple and read by position.
REQUIRED: dict[str, tuple[str, ...]] = {
    "": (
        "Align",
        "Block",
        "BlockFlags",
        "BlockKind",
        "BlockStyle",
        "Cell",
        "CodeOverflow",
        "ColumnFlags",
        "Columns",
        "Document",
        "DocumentOptions",
        "Face",
        "MarkPlace",
        "Run",
        "Style",
        "TableColumn",
        "add_font",
        "calc_text_size",
        "create_context",
        "current_context",
        "destroy_context",
        "face_has_glyph",
        "font_atlas_index",
        "host_info",
        "stats",
    ),
    "Document": (
        "append_table_rows",
        "append_text",
        "block_geometry",
        "block_line",
        "caret_rect",
        "close",
        "closed",
        "column",
        "column_count",
        "column_pos",
        "draw",
        "from_blocks",
        "hit_test",
        "layout",
        "pack_marks",
        "range_rects",
        "range_text",
        "replace_blocks",
        "select_range",
        "set_block_extent",
        "set_blocks",
        "set_columns",
        "set_options",
        "set_table_columns",
        "size",
        "stats",
        "table_column",
        "table_geometry",
        "table_row",
    ),
    "BlockStyle": (*StyleDescription._fields, "Color"),
    "Style": ("EmSize", "PixelsPerInch", "Color"),
    "DocumentOptions": (
        "CodeOverflow",
        "QuoteBarColor",
        "RuleColor",
        "TableCellPadding",
        "TableRuleColor",
        "TableRuleThickness",
    ),
    "Columns": ("count", "height", "gutter", "flags"),
    "Align": ("Justify", "Left", "Center", "Right"),
    "BlockFlags": ("FixedLineHeight", "HardBreaks", "TableHeader"),
    "BlockKind": ("Paragraph", "Heading", "ListItem", "Code", "Rule", "Host", "Table"),
    "CodeOverflow": ("Wrap", "Clip", "Grow"),
    "ColumnFlags": ("None_", "Balance"),
    "Face": ("Default", "Regular", "Bold", "Italic", "BoldItalic", "Code", "CodeBold", "Math"),
    "MarkPlace": ("Ink", "Behind"),
}

# The description's tuples go to the library as they are and it reads them BY
# POSITION (`Block(*block)`), so the library's type must begin with advtext's
# fields in advtext's order. More fields after them, with defaults, are fine.
_IN_ORDER: dict[str, tuple[str, ...]] = {
    "Block": BlockDescription._fields,
    "Run": RunDescription._fields,
    "Cell": CellDescription._fields,
    "TableColumn": ColumnDescription._fields,
}

# The package's own demo, which advtext's gallery pages draw. Only that the
# submodule can be found is asked, and it is not imported to ask: a host that
# shows no gallery pays nothing for it.
_SUBMODULES = ("demo",)


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
# Which kind `_reason` is a sentence of, while `_ts` is `None`.
_why = Kind.NOT_INSTALLED
# The host's own sentence for "there is no library for this platform"
# (`unsupported`); empty when it has not said so.
_unsupported = ""
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
    global _ts, _package, _tried, _route, _reason, _why
    if _ts is not None or _disabled or _tried:
        return _ts
    named = bool(os.environ.get(LIBRARY_VARIABLE))
    if not named and not _distribution():
        _reason = _unsupported or _NOT_SET
        _why = Kind.UNSUPPORTED if _unsupported else Kind.NOT_INSTALLED
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
        _why = Kind.REFUSED
        _say(f"imtypeset is not in use: {_reason}")
        return None
    _route = ROUTE_ENVIRONMENT if named else ROUTE_DISTRIBUTION
    # Kept whether or not it is accepted: `pairing()` then says which package
    # and which library were refused, and `unload()` can still be asked.
    _package = loaded
    lacking = missing(loaded)
    if lacking:
        _reason = _lacks(loaded, lacking)
        _why = Kind.REFUSED
        _say(f"imtypeset is not in use: {_reason}")
        return None
    _reason = ""
    _ts = loaded
    return _ts


def missing(package: Any) -> list[str]:
    """
    The names of `REQUIRED` that `package` does not have, as `Owner.name`; empty when it has all.

    What `module()` asks of the imtypeset it imported, before it answers it.
    It reads attributes and calls nothing, so it needs no context and no
    font, and costs about a hundred `hasattr`. A type whose fields the
    library reads by position (`Block`, `Run`, `Cell`, `TableColumn`) is
    missing `Owner.field` for the first field that is absent or out of
    advtext's order. Never raises: a package that raises when asked for a
    name does not have it.

    **What it cannot see**: a name that is there and means something else.
    Which versions of the two belong together is for imtypeset to say
    (HANDOFF-imtypeset.md, H4); this is the part advtext can know alone.
    """
    lacking: list[str] = []

    def has(owner: Any, name: str) -> bool:
        try:
            return hasattr(owner, name)
        except Exception:  # noqa: BLE001 -- see the docstring
            return False

    for owner_name, names in REQUIRED.items():
        owner = package
        if owner_name:
            if not has(package, owner_name):
                continue  # Said once, as the owner's own name, by the "" entry.
            owner = getattr(package, owner_name)
        lacking += [f"{owner_name}.{name}".lstrip(".") for name in names if not has(owner, name)]
    for owner_name, ours in _IN_ORDER.items():
        if not has(package, owner_name):
            continue
        try:
            theirs = tuple(getattr(package, owner_name)._fields)
        except Exception:  # noqa: BLE001 -- not a tuple type at all
            theirs = ()
        for index, name in enumerate(ours):
            if index >= len(theirs) or theirs[index] != name:
                lacking.append(f"{owner_name}.{name}")
                break
    for name in _SUBMODULES:
        if has(package, name):
            continue
        try:
            from importlib import util

            found = util.find_spec(f"{package.__name__}.{name}")
        except Exception:  # noqa: BLE001 -- not a package, or a finder that raises
            found = None
        if found is None:
            lacking.append(name)
    return lacking


def _lacks(package: Any, lacking: list[str]) -> str:
    """
    The refusal for a package that lacks names: at most five of them, and how many more.
    """
    where = os.path.dirname(getattr(package, "__file__", None) or "") or "(no file)"
    named = ", ".join(lacking[:5])
    more = f" and {len(lacking) - 5} more" if len(lacking) > 5 else ""
    count = "1 name" if len(lacking) == 1 else f"{len(lacking)} names"
    return (
        f"the imtypeset at {where} lacks {count} this advtext calls: {named}{more}; "
        "the two were not installed together"
    )


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
      `disable`, and it is said of a package that was imported and then
      refused for the names it lacks: the pairing is still what is in the
      process, and a bug report needs to say which imtypeset was refused.
    - `reason`: `reason()`. Empty while the library is in use.
    - `kind`: `kind()`, as its string (`Kind.READY.value` is `"ready"`).
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
    found = kind()
    package = _package
    answer: dict[str, str | None] = {
        "route": _route if package is not None else ROUTE_NONE,
        "reason": _reason,
        "kind": found.value,
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


_PAIRING_KEYS = (
    "route",
    "reason",
    "kind",
    "library",
    "package",
    "distribution",
    "imtypeset_version",
    "imgui_version",
    "wheel_version",
    "built_for",
    "headers",
    "accepted_by",
)

# What the child of `verdict()` runs: `_main`, in the advtext the asking
# process has. `-P` keeps the child's working directory off its path, so the
# package's own directory is offered last for a parent that found advtext
# there or through a path of its own making.
_CHILD = (
    "import importlib.util, sys\n"
    "if importlib.util.find_spec('advtext') is None:\n"
    "    sys.path.append(sys.argv[1])\n"
    "from advtext import typesetter\n"
    "raise SystemExit(typesetter._main())\n"
)


def verdict(
    library: str | os.PathLike[str] | None = None,
    python_path: str | os.PathLike[str] | None = None,
    *,
    timeout: float = 120.0,
) -> dict[str, str | None]:
    """
    What `pairing()` would say in a NEW process: asked of a child interpreter, as data.

    For an updater that has to know whether a pair will be accepted before it
    switches to it, and for a `--version` that prints the pairing with no
    window. **Nothing is loaded into the asking process and nothing is
    remembered in it**: this module's state is not read and not written, so
    it can be asked before `module()`, after a `disable`, and as often as
    wanted. The child imports the package, runs the library's import gate
    against the wheel, holds the package to `REQUIRED`, and prints
    `pairing()`; it makes no Dear ImGui context, loads no font and opens no
    window.

    `library` is what `IMTYPESET_LIBRARY` is in the child and `python_path`
    what `IMTYPESET_PYTHON` is: `None` leaves each as this process has it, an
    empty string takes it out (so `verdict("")` asks about the installed
    distribution alone). Anything that is not a path is a `TypeError` here.
    The child is `sys.executable` with this process's environment otherwise,
    so the wheel it meets is the one this interpreter would import. **Another
    interpreter is asked with the command line**, which is the same answer:
    `<that python> -m advtext.typesetter`.

    The answer has `pairing()`'s keys. Its `kind` is the child's, or:

    - `"unchecked"` (`Kind.UNCHECKED`) when no child could be asked: a frozen
      application (`sys.frozen`), whose executable is the application and not
      an interpreter; no `sys.executable`; a child that did not start, did
      not finish in `timeout` seconds, or ended without an answer. `reason`
      says which. It means "not known", never "no".
    - `"refused"` when the child was KILLED before it answered (a signal: a
      library that crashes the interpreter that loads it).

    What is not promised: that fonts load, or that anything draws; and what a
    host's `unsupported()` said in this process is not known to the child,
    which answers `"not-installed"` there. The library's gate keeps a stamp
    of its own beside the library file; that is the library's memory and is
    written by the child as it would be by the application.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError(f"verdict() takes a timeout in seconds, not {type(timeout).__name__}")
    if not timeout > 0:
        raise ValueError(f"verdict() takes a timeout above zero, not {timeout!r}")
    environment = dict(os.environ)
    for variable, given in ((LIBRARY_VARIABLE, library), (PACKAGE_VARIABLE, python_path)):
        if given is None:
            continue
        if isinstance(given, bytes) or not isinstance(given, (str, os.PathLike)):
            raise TypeError(f"verdict() takes a path for {variable}, not {type(given).__name__}")
        value = os.fspath(given)
        if value:
            environment[variable] = value
        else:
            environment.pop(variable, None)

    def unchecked(why: str, found: Kind = Kind.UNCHECKED) -> dict[str, str | None]:
        answer: dict[str, str | None] = dict.fromkeys(_PAIRING_KEYS)
        answer.update(route=ROUTE_NONE, reason=why, kind=found.value)
        return answer

    if getattr(sys, "frozen", False):
        return unchecked(
            "this is a frozen application (sys.frozen): its executable is not an interpreter, "
            "so no child can be asked"
        )
    if not sys.executable:
        return unchecked("sys.executable is empty: there is no interpreter to ask")
    import json
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run(
            [sys.executable, "-P", "-B", "-c", _CHILD, root],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return unchecked(f"the child interpreter did not answer in {timeout:g} seconds")
    except Exception as exc:  # noqa: BLE001 -- it did not start: that is the answer
        return unchecked(f"the child interpreter did not start: {type(exc).__name__}: {exc}")
    lines = done.stdout.strip().splitlines()
    try:
        said = json.loads(lines[-1]) if lines else None
    except ValueError:
        said = None
    kinds = {member.value for member in Kind}
    if isinstance(said, dict) and said.get("kind") in kinds:
        answer: dict[str, str | None] = dict.fromkeys(_PAIRING_KEYS)
        for key in _PAIRING_KEYS:
            heard = said.get(key)
            answer[key] = heard if isinstance(heard, str) else None
        return answer
    tail = " ".join(done.stderr.strip().splitlines()[-1:]) or "nothing on its standard error"
    if done.returncode < 0:
        return unchecked(
            f"the child interpreter was killed by signal {-done.returncode} before it "
            f"answered ({tail})",
            Kind.REFUSED,
        )
    return unchecked(f"the child interpreter exited {done.returncode} without an answer ({tail})")


def _main() -> int:
    """
    `python -m advtext.typesetter`: print `pairing()` as one line of JSON; exit by its kind.

    `EXIT_CODES` has the numbers: 0 when the library would be in use, a
    different one for each other kind. No Dear ImGui context, no font, no
    window.
    """
    import json

    answer = pairing()
    print(json.dumps(answer, sort_keys=True))
    return EXIT_CODES[Kind(answer["kind"])]


def reason() -> str:
    """
    Why `module()` is `None`, as one sentence; empty when it is not.

    Meaningful after `module()` has been asked. Before that it says the
    variable is not set, which may no longer be true. It does not say which
    route a loaded package came by -- it is empty then, and views test it for
    that; `pairing()["route"]` does.
    """
    return _reason


def kind() -> Kind:
    """
    Which kind of thing `reason()` is a sentence of: `Kind.READY` when the library is in use.

    It asks `module()` first, as `pairing()` does, so the first call may be
    the import; after that it is a comparison. `Kind` says what each member
    means and what advtext cannot tell apart by itself. Never
    `Kind.UNCHECKED`: that is `verdict()`'s.
    """
    return Kind.READY if module() is not None else _why


def unsupported(why: str) -> None:
    """
    The host says there is no library for this platform, in its own sentence.

    From then on, **when nothing is found** -- no variable, no distribution
    -- `kind()` is `Kind.UNSUPPORTED` and `reason()` is `why`, where they
    would have been `Kind.NOT_INSTALLED` and `IMTYPESET_LIBRARY is not set`,
    which reads as a broken install on a platform that was never going to
    have one. When something IS found the host's sentence is not used: what
    is in the process is the evidence. An empty `why` takes it back.
    `reset()` keeps it; it is the host's statement and not a refusal.

    advtext does not work this out for itself; `Kind` says why.
    """
    global _unsupported, _reason, _why
    if not isinstance(why, str):
        raise TypeError(f"unsupported() takes a sentence, not {type(why).__name__}")
    _unsupported = why.strip()
    if _ts is None and not _disabled and not _tried:
        # Nothing has been found so far; say it the new way without waiting
        # for the next `module()`.
        _reason = _unsupported or _NOT_SET
        _why = Kind.UNSUPPORTED if _unsupported else Kind.NOT_INSTALLED


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
    hello_imgui calls the callback once, so a host that loads its fonts once
    sees none of this.

    **Called again after start-up, between frames** (an operator switches
    typeset text on, or chooses another font file for a role with
    `advtext.fontlib.register_font`). Measured 2026-10-12 in a real window
    (hello_imgui's runner, `imgui-bundle` 1.92.900, imtypeset `c9f8902`,
    Xvfb and a software renderer), calling this from `pre_new_frame` twice
    more, long after `load_additional_fonts` had returned, with a
    `TypesetView` open. `tests/test_typesetter_kinds.py` makes the run again
    and holds each line below, the times apart:

    - **The atlas takes the fonts.** It answered true each time, in 15 to 21
      ms; the seven roles were in the atlas after it (8 fonts, then 15, then
      22), and a role whose file had been changed in between was the new
      file.
    - **After `disable` and `reset()` too**: switched off between two frames
      and brought back between the next two, the view drew again as it had.
    - **An open view draws on the next frame without being told**: its
      library document is closed by the call and it makes another at its next
      `draw`. The same 152 vertices the frame before the call and the frame
      after, and no exception. A `Document` or `Paragraph` the HOST made is
      closed, and is the host's to make again.
    - **`font(face)` answers the new font.** One kept from before is still a
      font of the atlas, and is no longer the one the library draws with.

    What is NOT promised:

    - **Nothing is taken off the atlas.** Every call leaves the seven fonts
      of the context it destroyed where they were, and so does `unload()`
      (22 fonts before it and 22 after): 7 more for every call, for as long
      as the Dear ImGui context lives. That is the price of an operator's
      click and should not be paid per frame or per document. The library
      can take a role's font off (`imtypeset.remove_font`; in a run of the
      same window that no test repeats, 8 fonts became 1 and the next load
      made them 8), and this function does not do that for the caller,
      because a font a host has made Dear ImGui's default, or has pushed,
      would be freed under it.
    - **Inside a frame.** Between `new_frame` and `render` a document may be
      in use further up the stack, and it is closed under its user. A call at
      the top of a frame, before anything of the library had drawn, worked in
      the one run that tried it; no test repeats it and it is not promised.
    - **Anything about a second Dear ImGui context alive at the same time**,
      a GPU, a display scale other than 1, or macOS: none was run.

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


def font(face: Face) -> Any:
    """
    The `ImFont` the library draws `face` with, for native Dear ImGui text beside typeset text.

    `face` is an `advtext.Face`; anything else is a `TypeError` here. The
    answer is the library's own entry in Dear ImGui's atlas
    (`imtypeset.font_atlas_index`), so `imgui.push_font(font, size)` sets a
    native line in the very font, and the very file, typeset text of that
    role is drawn from.

    `None` when the library is not `ready()`, when the role has no font (no
    file for it at `load_fonts`: see `trouble()`), and when the library
    cannot say; a library that raises when asked is a `trouble()` and `None`,
    never an exception.

    **Ask every time; do not keep the answer across a `load_fonts()`.** A
    later load gives the role another entry in the atlas, and the one kept is
    then a font nothing typeset is drawn with (it stays in the atlas:
    `load_fonts` has the measurement). It is a dictionary lookup and an
    index.

    **The size is the caller's, and it is not the em**:
    `imgui.push_font(font, size)`, and a font in the atlas has no size of its
    own on the pinned wheel. advtext sets text by its EM (a theme's size is
    one); Dear ImGui's font size is the height of a line of that font, its
    ascent plus its descent. So native text is the size of typeset text of
    em `E` when it is pushed at `E * (ascent - descent) / unitsPerEm` of the
    role's font file (the `hhea` table's): 1.049 for the wheel's Inconsolata,
    1.172 for its Roboto. Dear ImGui makes a pushed size a whole number of
    pixels. Measured in a window (2026-10-12, software renderer), the ink of
    thirteen characters typeset at em 16 and of the same thirteen native at
    that size was the same box: 104 by 14 px in `Face.CODE` (pushed at 16.78,
    which Dear ImGui made 17) and 116 by 15 px in `Face.PROSE` (18.75, made
    19). Pushed at 16 the native ink was 11 and 13 px high.

    **The same font at the same size is not the same advances.** Native text
    is placed by Dear ImGui on its own whole-pixel advances, typeset text by
    the font file's. They agree where the file's advance is a whole pixel
    (`Face.CODE` at em 16: 8 px a character both ways) and not elsewhere:
    at em 21 the library lays those thirteen characters of `Face.CODE` out
    136.5 px wide and Dear ImGui 143. A native line beside typeset text is
    the same face at the same height; a native COLUMN lines up with a typeset
    one only at such a size.
    """
    faces = importlib.import_module("advtext.primitives").Face
    if not isinstance(face, faces):
        raise TypeError(f"font() takes an advtext Face, not {type(face).__name__}")
    ts = _ts
    if ts is None or not _ready:
        return None
    try:
        index = ts.font_atlas_index(FACE_ROLES[face.name])
        if index is None:
            return None
        fonts = importlib.import_module("imgui_bundle").imgui.get_io().fonts.fonts
        return fonts[index] if 0 <= index < len(fonts) else None
    except Exception as exc:  # noqa: BLE001 -- a question must not be what fails
        note(f"font: {type(exc).__name__}: {exc}")
        return None


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
    switched off gives back its context. **Its fonts stay in Dear ImGui's
    atlas** (measured in a window, 2026-10-12: 22 fonts before this call and
    22 after); they go when the atlas does.
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
    `module()` is `None`, `reason()` is `why`, `kind()` is `Kind.FAILED`, and
    the caller draws the old way. Only `reset()` re-enables it.

    It releases nothing: the context, its documents and its fonts stay as
    they are until `unload()`, which still works afterwards.
    """
    global _ts, _reason, _why, _disabled, _ready
    _ts = None
    _ready = False
    _disabled = True
    _reason = why
    _why = Kind.FAILED
    _say(f"imtypeset is switched off for this run: {why}")


def reset() -> None:
    """
    Forget a `disable` or a refusal, so that the next `module()` asks again.

    The way back, for an operator's "try again" and for a test process that
    provoked a failure. Afterwards `module()` looks for the variable and for
    an installed distribution as it did the first time (a distribution
    installed since is found), imports the package, and holds it to
    `REQUIRED`; `reason()` and `kind()` are then that attempt's.

    **`ready()` is false until `load_fonts()` is called again**, whatever it
    was: after a `disable` nobody knows what state the library's context was
    left in, so it is made again. Call `reset()` and then `load_fonts()`,
    between frames; `load_fonts` says what that costs and what it leaves
    behind.

    **What it does not undo:**

    - The shared library stays mapped and the package stays imported: Python
      cannot unload either. So after a `disable`, "asks again" finds the same
      package in `sys.modules` and takes it without running the library's
      import gate a second time. A package whose import RAISED is not in
      `sys.modules`, and is imported, and gated, again.
    - A library replaced on disk is not picked up: the one that is mapped is
      the one that is used. A new library needs a new process (`verdict()`
      asks one).
    - The library's context, its documents and its fonts in Dear ImGui's
      atlas are left as they are; `unload()` and `load_fonts()` are what
      change those.
    - `trouble()`, a host's `unsupported()` sentence, and which package
      `pairing()` describes.
    - The cause. If what failed fails again, the library is switched off
      again.

    A warning that was logged once is logged again if it happens again.
    """
    global _ts, _tried, _installed, _reason, _why, _disabled, _ready
    _ts = None
    _tried = False
    _installed = None
    _reason = _unsupported or _NOT_SET
    _why = Kind.UNSUPPORTED if _unsupported else Kind.NOT_INSTALLED
    _disabled = False
    _ready = False
    _logged.clear()


def _say(message: str) -> None:
    """
    A warning, once per distinct message: a view calls this from its draw.
    """
    if message not in _logged and len(_logged) < 64:
        _logged.add(message)
        _log.warning("%s", message)


def _forget() -> None:
    """
    Back to the state at import. For tests; a host calls `reset()`.

    `reset()`, and then what that keeps on purpose: which package this
    process imported, the last `trouble()`, and a host's `unsupported()`. It
    forgets what this module knows, not what the process did: an imported
    imtypeset stays in `sys.modules` and its context stays made.
    """
    global _package, _route, _trouble, _unsupported
    _unsupported = ""  # First: `reset` says the host's sentence while there is one.
    reset()
    _package = None
    _route = ROUTE_NONE
    _trouble = ""


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


if __name__ == "__main__":  # pragma: no cover - run as a child by tests/test_typesetter_kinds.py
    raise SystemExit(_main())

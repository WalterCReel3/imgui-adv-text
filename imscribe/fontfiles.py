r"""
Which font file backs each role: the table, and a host's own files in front of it.

**This module names font files and opens none.** It imports `imscribe.primitives`
(the `Face` enum) and nothing else of imscribe, so `imscribe.typesetter.load_fonts`
finds the files it hands imtypeset without loading a module of the reference
core, and a host that registers its own font (`register_font`) loads none
either. Until 2026-10-12 all of it was `imscribe.fontlib`'s, which reads fonts
with fontTools and is reference core; that module imports every name here
back, so `imscribe.fontlib.register_font is imscribe.fontfiles.register_font`
and the tables are the same dictionaries under either path
(`tests/test_typeset_closure.py` holds the identities).

## The files are a registry a host can write to

`_FONT_FILES` names what imgui-bundle ships and is the default for every role it
lists. `register_font` puts a host's own file in front of it for one role, and
that is how a role the bundle has no file for gets one: `Face.CODE_BOLD` has no
bundled file (the bundle ships one Inconsolata weight), so it is backed by
`Face.PROSE_BOLD`'s file -- which is exactly what bold inside code has always
been set in -- until a host registers a bold monospace. `backing_face` says
which of the two a role currently is.

**Registration must precede building, and precede `typesetter.load_fonts`.**
`register_font` tells every listener (`on_registry_change`), which is how
`imscribe.fontlib` and `imscribe.typeset_metrics` drop what they read from the
old file. It cannot reach what was already made from the old one: the
library's roles keep the files `load_fonts` gave them until it is called
again, and a `Theme` already sized keeps its sizes.

Fonts are resolved by importing `imgui_bundle` and walking from its `__file__`,
never by a hard-coded path.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType

from imscribe.primitives import Face

__all__ = [
    "MissingFontError",
    "backing_face",
    "font_directory",
    "font_file",
    "on_registry_change",
    "register_font",
    "registered_fonts",
    "unregister_font",
]

# Relative to the bundle's assets/fonts directory. `docs/decisions.md` explains the
# choices: four real Roboto faces so emphasis is a true italic rather than a colour
# shift, and Latin Modern Math because it is the only bundled face with a MATH table.
_FONT_FILES: dict[Face, str] = {
    Face.PROSE: "Roboto/Roboto-Regular.ttf",
    Face.PROSE_BOLD: "Roboto/Roboto-Bold.ttf",
    Face.PROSE_ITALIC: "Roboto/Roboto-RegularItalic.ttf",
    Face.PROSE_BOLD_ITALIC: "Roboto/Roboto-BoldItalic.ttf",
    Face.CODE: "Inconsolata-Medium.ttf",
    Face.MATH: "latex/latinmodern-math.otf",
}

# A role the bundle ships no file for, and the role whose file stands in for it
# until a host registers one. `Face.CODE_BOLD` -> `Face.PROSE_BOLD` is not a
# guess at what looks nearest: it is what `imscribe.style.Theme.face_for` already
# returned for bold on a monospace base before the role existed, so a tree with
# nothing registered sets the same glyphs at the same widths it always did.
_STAND_INS: dict[Face, Face] = {
    Face.CODE_BOLD: Face.PROSE_BOLD,
}

# What a host has registered, by role. Absolute paths, checked when registered.
_REGISTERED: dict[Face, Path] = {}

# Caches outside this module that are keyed by face and must go when a file
# changes. A dict used as an ordered set, so registering the same callable twice
# -- which `imscribe.backends.svg` does on every cache miss rather than keep a
# flag -- is one entry.
_LISTENERS: dict[Callable[[], None], None] = {}


class MissingFontError(RuntimeError):
    """
    A face was asked for and the bundle does not ship the file it maps to.
    """


@cache
def font_directory() -> Path:
    """
    The directory imgui-bundle ships its fonts in, resolved from the package itself.
    """
    try:
        import imgui_bundle
    except ImportError as exc:  # pragma: no cover - environment, not logic
        raise MissingFontError(
            "imgui-bundle is not importable, so its bundled fonts cannot be found"
        ) from exc
    directory = Path(imgui_bundle.__file__).parent / "assets" / "fonts"
    if not directory.is_dir():
        raise MissingFontError(f"imgui-bundle is installed but ships no fonts at {directory}")
    return directory


def backing_face(face: Face) -> Face:
    """
    The role whose file this role is currently read from: usually itself.

    Different only for a role with neither a registered file nor a bundled one,
    which today is `Face.CODE_BOLD` and answers `Face.PROSE_BOLD`. Two things
    read this. `imscribe.ui.fonts.load_faces` uses it to hand ImGui each file
    once rather than loading Roboto Bold a second time under another name. And a
    caller deciding whether a bold monospace really exists -- a theme choosing
    whether bold inside code keeps its columns -- asks
    `backing_face(Face.CODE_BOLD) is Face.CODE_BOLD`.
    """
    if face in _REGISTERED or face in _FONT_FILES:
        return face
    return _STAND_INS.get(face, face)


def font_file(face: Face) -> Path:
    """
    The file backing one role. The single place a font family is named.

    A registered file wins; then the bundle's; then the stand-in role's. A role
    with none of the three is a `MissingFontError` like any other missing file,
    not a `KeyError` -- `Face` is an enum a later change may add to, and the
    callers that degrade on a missing face catch this type.
    """
    registered = _REGISTERED.get(face)
    if registered is not None:
        return registered
    bundled = _FONT_FILES.get(face)
    if bundled is None:
        stand_in = _STAND_INS.get(face)
        if stand_in is None:
            raise MissingFontError(f"{face.value} has no bundled file and none is registered")
        return font_file(stand_in)
    path = font_directory() / bundled
    if not path.is_file():
        raise MissingFontError(f"{face.value} maps to {path}, which does not exist")
    return path


def register_font(face: Face, path: str | os.PathLike[str]) -> None:
    """
    Back a role with a host's own font file, replacing the bundled one if any.

    For a role the bundle has no file for -- `Face.CODE_BOLD` -- this is what
    gives it one; for the others it swaps the family. The file must exist now:
    a path that is wrong is a `MissingFontError` here, at the one call a host
    makes on purpose, rather than at the first glyph of the first frame.

    **Call it before anything is built, and before `typesetter.load_fonts`.**
    Every listener is told (`on_registry_change`), so metrics asked for
    afterwards come from the new file. What was built before is not repaired
    and cannot be: the module docstring says what holds numbers from the old
    file. In particular an `ImFont` already loaded from the old file stays
    loaded, and the library's role keeps the old file until
    `typesetter.load_fonts` is called again.

    The math role is registrable like any other, and a file with no `MATH`
    table is refused later, by `math_metrics`, with the file's name in the
    message.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise MissingFontError(f"{face.value} was registered as {resolved}, which does not exist")
    _REGISTERED[face] = resolved
    _registry_changed()


def unregister_font(face: Face) -> None:
    """
    Withdraw a host's file for a role, restoring the bundled file or the stand-in.

    A role with nothing registered is left alone and no cache is touched, so a
    teardown may call this unconditionally.
    """
    if _REGISTERED.pop(face, None) is not None:
        _registry_changed()


def registered_fonts() -> Mapping[Face, Path]:
    """
    The files a host has registered, by role. A read-only view, not a copy.
    """
    return MappingProxyType(_REGISTERED)


def on_registry_change(clear: Callable[[], None]) -> None:
    """
    Have `clear` called whenever a role's file changes. Idempotent per callable.

    For a cache outside this module that is keyed by face, which would otherwise
    go on answering from the old file: `imscribe.backends.svg.glyph_outline` is
    the one in this tree. Not a general event system -- there is no way to
    remove a listener because nothing has needed one, and the callables are
    module-level cache clears that live as long as the process.
    """
    _LISTENERS[clear] = None


def _registry_changed() -> None:
    """
    Tell whoever asked to be told that a role's file changed.

    Everyone and not just whoever holds the changed role: a stand-in role
    shares another role's file so the dependency is not one-to-one, and this
    runs a handful of times in the life of a process. `imscribe.fontlib`'s own
    caches are the first listener when that module is loaded (it asks at its
    import), and nothing is imported here to clear them when it is not: there
    is then nothing of its to clear.
    """
    for clear in tuple(_LISTENERS):
        clear()

r"""
Font setup a host can call: faces onto an atlas, a `FaceFont` back.

Until this module existed the only code that put this project's faces into an
ImGui atlas was `imscribe.ui.app.load_fonts`, a `hello_imgui` callback inside the
demo that filled a module global. An application embedding the library had to
copy it. `load_faces` is that function with the demo taken out: it asks
`imscribe.fontlib` which file backs each role, hands each file to a loader, and
returns the callable `imscribe.backends.imgui_draw.draw` takes as `fonts`.

    from imscribe.ui.fonts import load_faces

    fonts = load_faces()                       # once, after the context exists
    ...
    draw(draw_list, cmds, origin, fonts=fonts) # every frame

## What was executed, and what was not

`tests/test_fonts_setup.py` drives `load_faces` with a fake loader for the
bookkeeping -- which files are asked for, in what order, what a failure costs --
and once against a real `ImFontAtlas` in a context with no backend, asserting
that the fonts it returns can raster a glyph. **Nothing here has been run in a
window by this module's own tests.** The demo's `load_fonts` is now a caller of
`load_faces` with `hello_imgui`'s loader, so the path a photograph of the demo
exercises is this one; whoever takes that photograph is the one who can say so.

## The loader is the host's, because the atlas is

A `Loader` takes a path and returns an `ImFont` or `None`. The default,
`atlas_loader`, calls `add_font_from_file_ttf` on the current context's atlas.
A host using `hello_imgui` passes its own -- the demo does -- because
`hello_imgui.load_font` applies that runner's DPI handling and a second opinion
about it here would be a second source of truth. Nothing in this module imports
`hello_imgui`.

The size a face is *loaded* at is not the size anything is drawn at. ImGui 1.92
bakes a face on demand at whatever size `add_text` names, and `draw` names the
size the layout used. `DEFAULT_LOAD_PX` only decides what a bare
`imgui.push_font(font)` with no size would give, which this project never does.

## Mathematics is loaded when it is asked for

`TEXT_FACES` is every role but `Face.MATH`, and it is the default. A host that
sets no mathematics therefore never has the math font read, never has its 227
synthetic codepoints minted, and never has a patched copy of it written to a
temporary directory -- `imscribe.fontlib.imgui_font_file` does all three, and
only for that face. Measured here, once, cold: that call takes about 1.06 s,
nearly all of it fontTools re-serialising a 727 kB font. That second is what the
default saves a host at start-up, and `tests/test_fonts_setup.py` holds that it
is not spent.

A host that does set mathematics has two honest options and both are here.

- Say so: `load_faces(ALL_FACES)`. The demo does, because its first tab has a
  formula in it.
- Find out: `LoadedFaces` records every role it was asked for and did not have,
  and `load_pending()` loads them. The first frame that sets a formula draws it
  in whatever face is bound -- `draw` treats `None` that way -- and the host
  calls `load_pending()` before its next `new_frame`.

**Call `load_pending` and `load` between frames.** A missing face is *recorded*
by `__call__`, which runs inside `draw`, and loaded by a separate call the host
places, for two reasons of different strength.

The measured one: loading mathematics is that one-second call, and inside
`draw` it would be a one-second frame at a moment the host did not choose.

The unmeasured one: whether an atlas may be added to mid-frame at all. An
earlier draft of this docstring said ImGui locks the atlas for the length of a
frame and asserts. **That was checked and is false here**: on imgui-bundle
1.92.900, in a context with no backend, `io.fonts.locked` reads `False` inside
a frame, `add_font_from_file_ttf` succeeds there, and the font draws in the same
frame. What was *not* checked is the same thing under a real renderer backend,
which is the party that has to upload the texture the new glyphs land in. So
between frames is the placement this module recommends and tests, not one it
can say is required.

## A role that shares a file is loaded once

`Face.CODE_BOLD` has no file of its own in the bundle and is backed by the bold
prose file until a host registers one (`imscribe.fontlib.backing_face`). Loading
it separately would put Roboto Bold in the atlas twice. `load` gives such a role
the `ImFont` of the role that backs it, loading that one if it has to, so the
atlas the demo builds holds the same six files it held before the role existed.

Sharing has to survive a reload, and at first it did not. Measured before the
fix: after `register_font(Face.PROSE_BOLD, other)` and `load([Face.PROSE_BOLD])`
the bold prose role had the new `ImFont` and `Face.CODE_BOLD` still had the old
one, while the layout -- whose caches the registration had cleared -- measured
both from the new file. So `load` now keeps three things true, and
`tests/test_fonts_setup.py` holds each:

- loading a role hands its font to every held role that role stands in for;
- loading a stand-in role by name re-reads the backing file when the font held
  for it came from a different file than the role resolves to now, and only
  then, so a `load_pending` for a stand-in adds nothing to the atlas;
- one `load` call reads a file once, whichever of the roles sharing it is named
  first.

A fourth was measured later. A backing file that *failed* to load was treated as
held and current, so `load([Face.CODE_BOLD])` did nothing and the stand-in could
not be retried by name the way a role with its own file can -- against
`LoadedFaces`' own docstring. Naming a failed stand-in now reads the backing
file again and both roles take the result. `load_pending` still retries
nothing: a stand-in a `draw` asks for after its backing file failed is settled
as failed without a read.

Deliberately out of scope: unloading a face, merging icon fonts, glyph ranges
(1.92 needs none), and choosing a size for the host -- `em_size_for_pixel_height`
converts the size a host already has, and is here so that a host has one import
for everything about fonts.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeAlias

from imscribe import fontlib
from imscribe.fontlib import em_size_for_pixel_height
from imscribe.fontmetrics import Face

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "ALL_FACES",
    "DEFAULT_LOAD_PX",
    "TEXT_FACES",
    "LoadedFaces",
    "Loader",
    "atlas_loader",
    "em_size_for_pixel_height",
    "load_faces",
]

DEFAULT_LOAD_PX = 16.0
"""
The size a face is registered at when the host names none.

The value `imscribe.ui.app.load_fonts` always used. It is not a drawing size; see
the module docstring.
"""

ALL_FACES: tuple[Face, ...] = tuple(Face)
"""
Every role, mathematics included. What the demo loads.
"""

TEXT_FACES: tuple[Face, ...] = tuple(face for face in Face if face is not Face.MATH)
"""
Every role a document without mathematics can name. What a host loads by default.
"""

Loader: TypeAlias = "Callable[[Path], imgui.ImFont | None]"
"""
How one font file becomes an `ImFont` on the host's atlas.

`None` is an allowed answer and means the face did not load; so is raising, which
`LoadedFaces.load` treats the same way. A missing face must not stop a host from
starting, and `draw` already knows what to do without one.
"""


def atlas_loader(
    size_px: float = DEFAULT_LOAD_PX, atlas: imgui.ImFontAtlas | None = None
) -> Loader:
    """
    A `Loader` over a plain `ImFontAtlas`: the current context's unless one is given.

    The atlas is looked up when a file is loaded and not when this is called, so
    a loader built before the context exists still finds the right one.
    """

    def load(path: Path) -> Any:
        from imgui_bundle import imgui

        target = imgui.get_io().fonts if atlas is None else atlas
        return target.add_font_from_file_ttf(str(path), size_px)

    return load


class LoadedFaces:
    """
    The `FaceFont` a host hands `draw`: a role in, its `ImFont` or `None` out.

    A class rather than a dict's `.get` because it also has to *remember what it
    was asked for and did not have* -- that is the whole of lazy mathematics, and
    the module docstring says why the remembering and the loading are two calls.

    `None` for a role means one of three things and `pending` and `failed` tell
    them apart: never loaded and never asked for (in neither), asked for by a
    `draw` and waiting for `load_pending` (in `pending`), or tried and refused by
    the loader (in `failed`, and not retried until `load` is called for it by
    name -- a file that failed once fails every frame, and retrying inside
    `load_pending` would be a font-file read per frame for the life of the app).
    That holds for a role that shares another's file too: naming it retries the
    shared file, and the role that backs it takes whatever comes back.
    """

    __slots__ = ("_failed", "_fonts", "_loader", "_paths", "_pending")

    def __init__(self, loader: Loader | None = None) -> None:
        self._loader: Loader = atlas_loader() if loader is None else loader
        self._fonts: dict[Face, Any] = {}
        # The file each directly loaded role's font was asked for from; absent
        # when the path itself could not be resolved. What tells a stand-in
        # role that the font it would share has gone stale.
        self._paths: dict[Face, Path] = {}
        self._pending: dict[Face, None] = {}
        self._failed: dict[Face, None] = {}

    def __call__(self, face: Face) -> Any:
        """
        The loaded font for a role. Records the role as pending if there is none.
        """
        font = self._fonts.get(face)
        if font is None and face not in self._fonts:
            self._pending[face] = None
        return font

    @property
    def fonts(self) -> Mapping[Face, Any]:
        """
        Every role a load was attempted for, to its `ImFont` or `None`. Read-only.
        """
        return MappingProxyType(self._fonts)

    @property
    def pending(self) -> tuple[Face, ...]:
        """
        Roles a `draw` asked for that no load has been attempted for, in asking order.
        """
        return tuple(self._pending)

    @property
    def failed(self) -> tuple[Face, ...]:
        """
        Roles whose load was attempted and produced no font, in attempt order.
        """
        return tuple(self._failed)

    def load(self, faces: Iterable[Face]) -> None:
        """
        Load these roles now, replacing any font already held for them.

        Between frames; see the module docstring. Replacing is deliberate
        -- it is how a host reloads after `imscribe.fontlib.register_font` -- and
        the `ImFont` it replaces stays in the atlas, because nothing here can know
        whether the host still draws with it.

        A role backed by another role's file (`imscribe.fontlib.backing_face`)
        takes that role's font. The backing file is read if this object has no
        font for it, or has one that came from a file the backing role no longer
        resolves to -- the state `register_font` leaves behind -- or if this
        role is recorded as failed because that file would not load, which is
        the retry-by-name the class docstring promises; and otherwise is not
        read again. In the other direction, a role that is loaded hands its new
        font to every held role it stands in for. Within one call a file is read
        once. The module docstring has the defects these rules answer.

        The paths come from `imscribe.fontlib.imgui_font_file` and not
        `font_file`: the math face needs this project's synthetic codepoints
        written into its cmap or ImGui cannot find the display-size summation,
        and for every other face the two are the same path.
        """
        fresh: set[Face] = set()
        for face in faces:
            self._pending.pop(face, None)
            backing = fontlib.backing_face(face)
            if backing not in fresh and (
                backing is face or self._is_stale(backing) or self._failed_through(face, backing)
            ):
                self._load_file(backing)
                fresh.add(backing)
            if backing is not face:
                self._settle(face, self._fonts[backing])

    def load_pending(self) -> tuple[Face, ...]:
        """
        Load every role a `draw` asked for and did not get. Returns what it tried.

        Cheap when nothing is pending -- one empty tuple -- so a host can call it
        unconditionally before every `new_frame`.
        """
        wanted = self.pending
        if wanted:
            self.load(wanted)
        return wanted

    def _load_file(self, face: Face) -> None:
        """
        One role, one file, one call to the loader; a failure is recorded, not raised.
        """
        self._paths.pop(face, None)
        try:
            path = fontlib.imgui_font_file(face)
            self._paths[face] = path
            font = self._loader(path)
        # Bare `Exception` on purpose: the loader is the host's and may fail in
        # its own way, and `fontlib` raises `MissingFontError` for a file that is
        # not there. Either costs this role its face and nothing else.
        except Exception:
            font = None
        self._settle(face, font)
        # Every held role this one stands in for draws from the same file and
        # is measured from it, so it takes the same font -- including `None`.
        for other in tuple(self._fonts):
            if other is not face and fontlib.backing_face(other) is face:
                self._settle(other, font)

    def _is_stale(self, face: Face) -> bool:
        """
        Whether the font held for a role is not one loaded from its current file.

        True for a role never attempted. A role whose load *failed* is not stale
        while its path stands: the class docstring says why a failure is not
        retried on the way to something else, and `_failed_through` is the one
        case where it is retried. `imgui_font_file` is cached, so this is a dict
        lookup except once after a registration.
        """
        if face not in self._fonts:
            return True
        try:
            return self._paths.get(face) != fontlib.imgui_font_file(face)
        # As in `_load_file`: no path is no font, and `_load_file` records that.
        except Exception:
            return face in self._paths

    def _failed_through(self, face: Face, backing: Face) -> bool:
        """
        Whether a stand-in role is recorded as failed for want of its backing font.

        The condition under which naming a stand-in in `load` retries a file
        that already failed. Both halves are needed. `face in self._failed`
        separates a role the host is loading *again* from one a `draw` merely
        asked for: the second reaches `load` through `load_pending` without
        ever having been attempted, takes the backing role's `None`, and is
        failed from then on without a read. The backing font being `None`
        separates this from a stand-in that failed under a file of its own
        since unregistered, whose backing role may hold a good font that must
        not be put in the atlas a second time.
        """
        return face in self._failed and self._fonts.get(backing) is None

    def _settle(self, face: Face, font: Any) -> None:
        self._fonts[face] = font
        if font is None:
            self._failed[face] = None
        else:
            self._failed.pop(face, None)


def load_faces(
    faces: Iterable[Face] = TEXT_FACES,
    *,
    loader: Loader | None = None,
) -> LoadedFaces:
    """
    Register faces on the host's atlas and return the `FaceFont` to draw with.

    Call it once the ImGui context exists and before the first frame -- or, under
    `hello_imgui`, from `callbacks.load_additional_fonts`, which is that moment.
    `loader` defaults to `atlas_loader()`: the current context's atlas at
    `DEFAULT_LOAD_PX`.

    `faces` defaults to `TEXT_FACES`, which leaves the math font unread until a
    document sets mathematics. Pass `ALL_FACES` to load it up front. Register a
    host's own files with `imscribe.fontlib.register_font` *before* this call.

    The result is callable as `fonts(face)` and is what `draw`,
    `DocumentView.draw` and the rest take as `fonts`.
    """
    loaded = LoadedFaces(loader)
    loaded.load(faces)
    return loaded

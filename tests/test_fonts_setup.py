r"""
Font setup as a host meets it: the registry, the size helper, and `load_faces`.

Three things are under test and they are at three fidelities, so it is worth
saying which is which before any of them is read as more than it is.

- **The registry** (`imscribe.fontlib.register_font` and friends) is tested
  against real font files. There is no bold monospace in the fonts imgui-bundle
  ships -- that is the reason the registry exists -- so the "host's file" here is
  a copy of the bundle's one Inconsolata weight under another name. That proves a
  registered file is the one that gets read. It cannot prove anything about how a
  real bold monospace looks or measures, and nothing below claims to.
- **`load_faces`** is tested with a fake loader for its bookkeeping, and once
  against a real `ImFontAtlas` in a context with no backend. No window is opened.
- **Laziness** is tested in a fresh interpreter, because `sys.modules` in this
  one has had fontTools in it since the first test that measured a glyph.

Every test that registers a font runs under `_registry_restored`, which withdraws
whatever was registered. `register_font` clears process-wide caches, and a role
left pointing at a temporary file would fail some unrelated test much later with
a path that no longer exists.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from imscribe import fontlib
from imscribe.fontmetrics import Face
from imscribe.ui.fonts import (
    ALL_FACES,
    DEFAULT_LOAD_PX,
    TEXT_FACES,
    atlas_loader,
    em_size_for_pixel_height,
    load_faces,
)
from imscribe.units import px_from_sp, sp_from_px

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _registry_restored() -> Iterator[None]:
    """
    Leave the registry as it was found, whatever the test did to it.
    """
    before = dict(fontlib.registered_fonts())
    try:
        yield
    finally:
        for face in tuple(fontlib.registered_fonts()):
            if face not in before:
                fontlib.unregister_font(face)
        for face, path in before.items():
            if fontlib.registered_fonts().get(face) != path:
                fontlib.register_font(face, path)


@pytest.fixture
def host_mono(tmp_path: Path) -> Path:
    """
    A font file a host might vendor: the bundle's monospace, under the host's name.

    A stand-in for a bold monospace, and only in the sense that it is a file that
    is not the one the role would otherwise read. See the module docstring.
    """
    destination = tmp_path / "Host-Mono-Bold.ttf"
    shutil.copyfile(fontlib.font_file(Face.CODE), destination)
    return destination


# ----------------------------------------------------------------------
# The mono-bold role, with nothing registered


def test_the_mono_bold_role_is_backed_by_the_bold_prose_file_until_one_is_registered() -> None:
    """
    `Face.CODE_BOLD` resolves, and to exactly what bold inside code was set in before.

    Before the role existed `Theme.face_for` answered `Face.PROSE_BOLD` for bold
    on a monospace base. Backing the new role with that same file means a tree
    with nothing registered measures the same advances under the new name.
    """
    assert Face.CODE_BOLD not in fontlib.registered_fonts()
    assert fontlib.backing_face(Face.CODE_BOLD) is Face.PROSE_BOLD
    assert fontlib.font_file(Face.CODE_BOLD) == fontlib.font_file(Face.PROSE_BOLD)

    stand_in = fontlib.metrics(Face.CODE_BOLD, 16.0)
    prose_bold = fontlib.metrics(Face.PROSE_BOLD, 16.0)
    assert stand_in.face is Face.CODE_BOLD, "the metrics must still say which role they answer for"
    for character in "minW.":
        assert stand_in.advance(ord(character)) == prose_bold.advance(ord(character))
    assert stand_in.kern(ord("T"), ord("o")) == prose_bold.kern(ord("T"), ord("o")) != 0.0


def test_every_other_role_backs_itself() -> None:
    """
    The stand-in is the exception, and there is exactly one.
    """
    assert [face for face in Face if fontlib.backing_face(face) is not face] == [Face.CODE_BOLD]


# ----------------------------------------------------------------------
# The registry


def test_a_registered_file_is_the_one_the_role_is_read_from(host_mono: Path) -> None:
    """
    Registration is honoured by everything that names the role, at once.

    The measurement is taken **before** registering as well as after, on purpose:
    `metrics`, `_face_data` and `imgui_font_file` are all cached per process, so a
    `register_font` that only wrote the table would leave every one of them
    answering from the old file and this test would see Roboto's widths twice.
    """
    before = fontlib.metrics(Face.CODE_BOLD, 16.0)
    wide, narrow = before.advance(ord("m")), before.advance(ord("i"))
    assert wide != narrow, "the stand-in is proportional, which is what makes the change visible"
    assert fontlib.imgui_font_file(Face.CODE_BOLD) == fontlib.font_file(Face.PROSE_BOLD)

    fontlib.register_font(Face.CODE_BOLD, host_mono)

    assert fontlib.backing_face(Face.CODE_BOLD) is Face.CODE_BOLD
    assert fontlib.font_file(Face.CODE_BOLD) == host_mono.resolve()
    assert fontlib.imgui_font_file(Face.CODE_BOLD) == host_mono.resolve()
    assert dict(fontlib.registered_fonts()) == {Face.CODE_BOLD: host_mono.resolve()}

    after = fontlib.metrics(Face.CODE_BOLD, 16.0)
    assert after is not before
    assert after.advance(ord("m")) == after.advance(ord("i")) == 8.0, "half an em, every glyph"
    assert after.kern(ord("T"), ord("o")) == 0.0


def test_registering_reaches_the_svg_backend_s_outline_cache(host_mono: Path) -> None:
    """
    A cache outside `fontlib` that is keyed by face is dropped too.

    `imscribe.backends.svg.glyph_outline` memoises path data per (face, name). It
    is the one such cache in the tree, and without `on_registry_change` it would
    go on drawing Roboto's outline for a role that now measures as Inconsolata --
    the right widths around the wrong shapes.
    """
    from imscribe.backends.svg import glyph_outline

    name = fontlib.glyph_name(Face.CODE_BOLD, ord("m"))
    roboto = glyph_outline(Face.CODE_BOLD, name)
    assert roboto == glyph_outline(Face.PROSE_BOLD, fontlib.glyph_name(Face.PROSE_BOLD, ord("m")))

    fontlib.register_font(Face.CODE_BOLD, host_mono)

    name = fontlib.glyph_name(Face.CODE_BOLD, ord("m"))
    registered = glyph_outline(Face.CODE_BOLD, name)
    assert registered != roboto
    assert registered == glyph_outline(Face.CODE, fontlib.glyph_name(Face.CODE, ord("m")))


def test_unregistering_restores_the_stand_in_and_is_harmless_when_nothing_was_registered(
    host_mono: Path,
) -> None:
    """
    Withdrawal is the same invalidation in the other direction, and a no-op costs nothing.

    The identity check is what "costs nothing" means: an `unregister_font` that
    cleared the caches regardless would re-open every font file in the process
    each time a teardown called it defensively.
    """
    fontlib.register_font(Face.CODE_BOLD, host_mono)
    assert fontlib.metrics(Face.CODE_BOLD, 16.0).advance(ord("m")) == 8.0

    fontlib.unregister_font(Face.CODE_BOLD)
    assert fontlib.backing_face(Face.CODE_BOLD) is Face.PROSE_BOLD
    assert fontlib.metrics(Face.CODE_BOLD, 16.0).advance(ord("m")) == fontlib.metrics(
        Face.PROSE_BOLD, 16.0
    ).advance(ord("m"))

    held = fontlib.metrics(Face.PROSE, 16.0)
    fontlib.unregister_font(Face.CODE_BOLD)
    fontlib.unregister_font(Face.PROSE)
    assert fontlib.metrics(Face.PROSE, 16.0) is held


def test_a_bundled_role_can_be_given_another_family(host_mono: Path) -> None:
    """
    The registry overrides as well as extends: the prose role, read from a mono file.

    This is the all-monospace host -- pptmstr sets its transcript in one family --
    and it needs no stand-in logic at all, only that a registered file wins over
    the bundled one.
    """
    proportional = fontlib.metrics(Face.PROSE, 16.0)
    assert proportional.advance(ord("m")) != proportional.advance(ord("i"))

    fontlib.register_font(Face.PROSE, host_mono)
    mono = fontlib.metrics(Face.PROSE, 16.0)
    assert mono.advance(ord("m")) == mono.advance(ord("i"))
    assert fontlib.backing_face(Face.PROSE) is Face.PROSE

    fontlib.unregister_font(Face.PROSE)
    assert fontlib.metrics(Face.PROSE, 16.0).advance(ord("m")) == proportional.advance(ord("m"))


def test_a_path_that_does_not_exist_is_refused_when_it_is_registered(tmp_path: Path) -> None:
    """
    The error arrives at the call the host made, and the registry is left as it was.
    """
    held = fontlib.metrics(Face.PROSE, 16.0)
    with pytest.raises(fontlib.MissingFontError, match="Vendored-Bold.ttf"):
        fontlib.register_font(Face.CODE_BOLD, tmp_path / "Vendored-Bold.ttf")
    assert Face.CODE_BOLD not in fontlib.registered_fonts()
    assert fontlib.metrics(Face.PROSE, 16.0) is held, "a refused registration cleared the caches"


def test_the_view_of_what_is_registered_cannot_be_written_through(host_mono: Path) -> None:
    """
    `registered_fonts` is for reading. Writing goes through `register_font`, which
    is the only path that clears the caches.
    """
    view: Any = fontlib.registered_fonts()
    with pytest.raises(TypeError):
        view[Face.CODE_BOLD] = host_mono


# ----------------------------------------------------------------------
# The size helper


def _height_px(em_px: float, ascent: float, descent: float, em: float) -> float:
    """The pixel height Dear ImGui means by a font's size, for a face set at an em of `em_px`."""
    return em_px * (ascent + descent) / em


@pytest.mark.parametrize("face", [Face.PROSE, Face.PROSE_BOLD, Face.CODE, Face.MATH])
@pytest.mark.parametrize("height_px", [13.0, 16.0, 18.0, 24.0])
def test_the_size_helper_is_the_inverse_of_the_baked_size_correction(
    face: Face, height_px: float
) -> None:
    """
    A host's pixel height, converted to an em and drawn, is asked of ImGui at that height.

    Dear ImGui's size for a font is the height of its ascent and descent:
    `em * (ascent + descent) / em_units` (`_height_px` below; the old ImGui draw
    backend had it as `baked_size_px`, and is deleted). Composed with the
    helper it must be the identity, or text built "at the host's 16" would be
    drawn at some other size and resampled.

    Checked twice: exactly, in floats, and then through the rounding to scaled
    points that a real `FontSpec` imposes. The second is the one that matters in
    practice -- the result is no longer exactly the height, and what has to hold
    is that ImGui's `floor(size + 0.5)` still selects it.
    """
    em_px = em_size_for_pixel_height(face, height_px)

    exact = fontlib.metrics(face, em_px)
    assert _height_px(em_px, exact.ascent, exact.descent, exact.em) == pytest.approx(
        height_px, abs=1e-9
    )

    size = sp_from_px(em_px)
    ours = fontlib.metrics(face, float(size))
    asked = _height_px(px_from_sp(size), ours.ascent, ours.descent, ours.em)
    assert asked == pytest.approx(height_px, abs=1e-3)
    assert float(int(asked + 0.5)) == height_px


def test_the_size_helper_needs_the_face_because_the_ratio_is_the_face_s() -> None:
    """
    One host size is two different ems in the two families, and the figures are pinned.

    The module docstring of `em_size_for_pixel_height` quotes both numbers. They
    are a property of the bundled files (Roboto's `hhea` extent is 2400 units of a
    2048 em; Inconsolata's is 1049 of 1000), so a bundle that changed either
    would move them, and this is where that would show.
    """
    assert em_size_for_pixel_height(Face.PROSE, 16.0) == pytest.approx(13.653, abs=5e-4)
    assert em_size_for_pixel_height(Face.CODE, 16.0) == pytest.approx(15.253, abs=5e-4)
    assert em_size_for_pixel_height(Face.PROSE, 32.0) == pytest.approx(
        2 * em_size_for_pixel_height(Face.PROSE, 16.0)
    )


def test_the_size_helper_follows_the_registry(host_mono: Path) -> None:
    """
    The ratio is read from the file the role is backed by *now*.
    """
    assert em_size_for_pixel_height(Face.CODE_BOLD, 16.0) == em_size_for_pixel_height(
        Face.PROSE_BOLD, 16.0
    )
    fontlib.register_font(Face.CODE_BOLD, host_mono)
    assert em_size_for_pixel_height(Face.CODE_BOLD, 16.0) == em_size_for_pixel_height(
        Face.CODE, 16.0
    )


# ----------------------------------------------------------------------
# `load_faces`, with a loader that records instead of loading


class _Font:
    """
    What a fake loader returns: an object that knows which file it came from.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def __repr__(self) -> str:
        return f"_Font({self.path.name})"


class _RecordingLoader:
    """
    A `Loader` that keeps the paths it was handed, and can be told to refuse some.
    """

    def __init__(self, *, refuse: str = "", explode: str = "") -> None:
        self.paths: list[Path] = []
        self.refuse = refuse
        self.explode = explode

    def __call__(self, path: Path) -> Any:
        self.paths.append(path)
        if self.explode and self.explode in path.name:
            raise OSError(f"cannot read {path.name}")
        if self.refuse and self.refuse in path.name:
            return None
        return _Font(path)


def test_the_default_load_is_every_text_role_and_no_mathematics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A host that sets no mathematics never has the math font touched.

    `imgui_font_file(Face.MATH)` is the expensive call -- it reads the font, mints
    227 codepoints and writes a patched copy to a temporary directory -- so the
    assertion is on *that function's arguments* and not merely on what reached
    the loader. A `load_faces` that resolved every path first and filtered
    afterwards would pass a loader-only check and still have done the work.
    """
    resolved: list[Face] = []
    real = fontlib.imgui_font_file

    def spy(face: Face) -> Path:
        resolved.append(face)
        return real(face)

    monkeypatch.setattr(fontlib, "imgui_font_file", spy)
    loader = _RecordingLoader()

    fonts = load_faces(loader=loader)

    assert Face.MATH not in TEXT_FACES and set(TEXT_FACES) | {Face.MATH} == set(Face)
    assert Face.MATH not in resolved
    assert [path.name for path in loader.paths] == [
        "Roboto-Regular.ttf",
        "Roboto-Bold.ttf",
        "Roboto-RegularItalic.ttf",
        "Roboto-BoldItalic.ttf",
        "Inconsolata-Medium.ttf",
    ]
    assert set(fonts.fonts) == set(TEXT_FACES)
    assert all(fonts(face) is not None for face in TEXT_FACES)
    assert fonts.pending == () and fonts.failed == ()


def test_a_role_that_shares_a_file_shares_the_font_and_the_file_is_loaded_once() -> None:
    """
    `Face.CODE_BOLD` with nothing registered is the bold prose `ImFont`, not a second one.

    Loading it separately would put Roboto Bold into the atlas twice. The second
    half is the order-independence: asked for alone, the role still loads the
    file that backs it, once.
    """
    loader = _RecordingLoader()
    fonts = load_faces(loader=loader)
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)
    assert [path.name for path in loader.paths].count("Roboto-Bold.ttf") == 1

    alone = _RecordingLoader()
    only = load_faces([Face.CODE_BOLD], loader=alone)
    assert [path.name for path in alone.paths] == ["Roboto-Bold.ttf"]
    assert only(Face.CODE_BOLD) is not None
    assert only(Face.CODE_BOLD) is only(Face.PROSE_BOLD)


def test_a_registered_mono_bold_is_loaded_as_its_own_font(host_mono: Path) -> None:
    """
    Registration before loading is the whole of what a host does to get a bold mono.
    """
    fontlib.register_font(Face.CODE_BOLD, host_mono)
    loader = _RecordingLoader()

    fonts = load_faces(loader=loader)

    assert [path.name for path in loader.paths].count("Host-Mono-Bold.ttf") == 1
    assert fonts(Face.CODE_BOLD).path == host_mono.resolve()
    assert fonts(Face.CODE_BOLD) is not fonts(Face.PROSE_BOLD)


def test_reloading_a_role_reaches_the_role_it_stands_in_for(host_mono: Path) -> None:
    """
    After `register_font(PROSE_BOLD, ...)` and a reload, bold code draws from the new file.

    The defect this pins was measured, not read: `load([PROSE_BOLD])` replaced
    that role's `ImFont` and left `Face.CODE_BOLD` holding the one it replaced,
    while `fontlib.metrics(Face.CODE_BOLD, ...)` -- cleared by the registration
    -- measured the new file. Bold inside code was then set at one font's widths
    and drawn in another's glyphs. Before the fix the first assertion below
    failed with `_Font(Roboto-Bold.ttf) is _Font(Host-Mono-Bold.ttf)`.
    """
    loader = _RecordingLoader()
    fonts = load_faces(loader=loader)
    assert fonts(Face.CODE_BOLD).path.name == "Roboto-Bold.ttf"

    fontlib.register_font(Face.PROSE_BOLD, host_mono)
    fonts.load([Face.PROSE_BOLD])

    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)
    assert fonts(Face.CODE_BOLD).path == host_mono.resolve()
    assert [path.name for path in loader.paths].count("Host-Mono-Bold.ttf") == 1


def test_reloading_a_stand_in_role_by_name_reloads_a_file_that_changed(host_mono: Path) -> None:
    """
    `load([CODE_BOLD])` alone picks up a new file behind the role that backs it.

    The other route into the same defect: the role's backing font was already
    held, so `load` reused it without asking whether it still came from the file
    the role now resolves to. Both roles move together, because they are one
    file and the layout measures both from it.

    The last three lines are the control. With nothing re-registered, loading
    the stand-in by name again must *not* read the file again: that is what a
    `load_pending` for a stand-in role amounts to, and a second Roboto Bold in
    the atlas for it is what sharing exists to prevent.
    """
    loader = _RecordingLoader()
    fonts = load_faces(loader=loader)

    fontlib.register_font(Face.PROSE_BOLD, host_mono)
    fonts.load([Face.CODE_BOLD])

    assert fonts(Face.CODE_BOLD).path == host_mono.resolve()
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)
    assert [path.name for path in loader.paths].count("Host-Mono-Bold.ttf") == 1

    attempts = len(loader.paths)
    fonts.load([Face.CODE_BOLD])
    assert len(loader.paths) == attempts, "an unchanged backing file was read again"


def test_a_role_that_loses_its_own_file_follows_its_stand_in_on_the_next_reload(
    host_mono: Path,
) -> None:
    """
    Unregistering the mono bold and reloading the bold prose role re-joins the two.

    The reverse direction is deliberately not asserted: a host that *registers*
    `Face.CODE_BOLD` has named the role it changed and reloads that role.
    """
    fontlib.register_font(Face.CODE_BOLD, host_mono)
    fonts = load_faces(loader=_RecordingLoader())
    assert fonts(Face.CODE_BOLD) is not fonts(Face.PROSE_BOLD)

    fontlib.unregister_font(Face.CODE_BOLD)
    fonts.load([Face.PROSE_BOLD])

    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)
    assert fonts(Face.CODE_BOLD).path.name == "Roboto-Bold.ttf"


def test_one_load_reads_a_shared_file_once_whichever_role_is_named_first() -> None:
    """
    `[CODE_BOLD, PROSE_BOLD]` is one Roboto Bold, as `[PROSE_BOLD, CODE_BOLD]` is.

    `Face`'s own order names the backing role first, so the default never met
    this; a host's list might. Before the fix it read the file twice and left
    the two roles on different `ImFont`s.
    """
    loader = _RecordingLoader()
    fonts = load_faces([Face.CODE_BOLD, Face.PROSE_BOLD], loader=loader)

    assert [path.name for path in loader.paths] == ["Roboto-Bold.ttf"]
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD) is not None


def test_two_math_files_of_one_name_are_patched_to_two_files(tmp_path: Path) -> None:
    """
    Re-registering mathematics to a same-named file elsewhere does not overwrite the first.

    The patched copy was named for the role and the file's *name*, so a second
    file of that name in another directory was saved over the first -- the file
    an `ImFont` already in the atlas was loaded from. Read-derived by the
    reviewer and confirmed here before the fix: both calls returned one path.

    The two sources are copies of the bundled math font, so this says nothing
    about a second family; it says the destination follows the source's path.
    """
    sources = []
    for name in ("vendor-a", "vendor-b"):
        directory = tmp_path / name
        directory.mkdir()
        sources.append(directory / "Host-Math.otf")
        shutil.copyfile(fontlib.font_file(Face.MATH), sources[-1])

    fontlib.register_font(Face.MATH, sources[0])
    first = fontlib.imgui_font_file(Face.MATH)
    fontlib.register_font(Face.MATH, sources[1])
    second = fontlib.imgui_font_file(Face.MATH)

    assert first not in sources and second not in sources, "nothing was patched"
    assert first != second
    assert first.is_file() and second.is_file()
    assert first.name.endswith("Host-Math.otf") and second.name.endswith("Host-Math.otf")

    fontlib.register_font(Face.MATH, sources[0])
    assert fontlib.imgui_font_file(Face.MATH) == first, "the name must be a function of the source"


def test_a_face_a_draw_asked_for_is_remembered_and_loaded_between_frames() -> None:
    """
    Lazy mathematics: asked for, answered `None`, recorded, and loaded on request.

    `__call__` is what `draw` invokes inside a frame, and loading mathematics
    there would be a one-second frame, so it only *records*. `load_pending` is
    the call a host places before its next `new_frame`. The math font arrives
    through the patched file -- a different path from the bundled one -- which
    is the evidence that the synthetic codepoints went in.
    """
    loader = _RecordingLoader()
    fonts = load_faces(loader=loader)
    loaded_before = len(loader.paths)

    assert fonts(Face.MATH) is None
    assert fonts(Face.MATH) is None
    assert fonts.pending == (Face.MATH,)
    assert len(loader.paths) == loaded_before, "asking for a face inside a draw loaded it"

    assert fonts.load_pending() == (Face.MATH,)

    assert fonts.pending == ()
    font = fonts(Face.MATH)
    assert font is not None
    assert font.path != fontlib.font_file(
        Face.MATH
    ), "mathematics was loaded from the unpatched file"
    assert font.path.name.endswith("latinmodern-math.otf")
    assert fonts.load_pending() == ()
    assert len(loader.paths) == loaded_before + 1


@pytest.mark.parametrize("how", ["refuse", "explode"])
def test_a_face_that_will_not_load_costs_that_face_and_nothing_else(how: str) -> None:
    """
    A loader that returns `None` and one that raises are the same answer: no face.

    This is `imscribe.ui.app.load_fonts`'s old posture, which could not be tested
    where it was (its `except` carried a `no cover` pragma because the loader was
    `hello_imgui`'s). The failed role is not re-tried by `load_pending` -- a file
    that failed once fails every frame, and a host calling `load_pending` each
    frame would otherwise re-read it forever -- but it can be loaded by name.
    """
    loader = _RecordingLoader(**{how: "Inconsolata"})
    fonts = load_faces(loader=loader)

    assert fonts(Face.CODE) is None
    assert fonts.failed == (Face.CODE,)
    assert fonts.pending == (), "a face that failed must not also be queued for retry"
    assert all(fonts(face) is not None for face in TEXT_FACES if face is not Face.CODE)

    attempts = len(loader.paths)
    assert fonts.load_pending() == ()
    assert len(loader.paths) == attempts

    loader.refuse = loader.explode = ""
    fonts.load([Face.CODE])
    assert fonts(Face.CODE) is not None and fonts.failed == ()


@pytest.mark.parametrize("how", ["refuse", "explode"])
def test_a_failed_stand_in_role_is_retried_when_it_is_loaded_by_name(how: str) -> None:
    """
    `load([CODE_BOLD])` after its backing file failed reads that file again.

    The class docstring's promise is that a failed role is "not retried until
    `load` is called for it by name". For a role with its own file that held;
    for a stand-in it did not, and that was measured (review 2, item 8): the
    backing role's failure counted as "held and current", so the second `load`
    below made no loader call and the role stayed `None` with a file that would
    now have loaded. Before the fix the assertion on `len(loader.paths)` failed
    with `1 == 2`.

    Both roles come back, because they are one file: a retry that reached the
    stand-in and left the role backing it failed would be the sharing defect of
    review 1 again from the other side.
    """
    loader = _RecordingLoader(**{how: "Roboto-Bold"})
    fonts = load_faces([Face.PROSE_BOLD, Face.CODE_BOLD], loader=loader)

    assert fonts(Face.PROSE_BOLD) is None and fonts(Face.CODE_BOLD) is None
    assert fonts.failed == (Face.PROSE_BOLD, Face.CODE_BOLD)
    assert len(loader.paths) == 1, "one file, one attempt, however many roles share it"

    loader.refuse = loader.explode = ""
    fonts.load([Face.CODE_BOLD])

    assert len(loader.paths) == 2
    assert fonts(Face.CODE_BOLD) is not None
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)
    assert fonts.failed == ()


def test_a_failed_backing_file_is_not_re_read_by_load_pending() -> None:
    """
    The other half of the same promise: what a host calls every frame never retries.

    A `draw` that asks for `Face.CODE_BOLD` after the bold prose file failed
    queues the role, and `load_pending` settles it as failed *without* reading
    the file -- it was not named by the host, it was merely asked for, and the
    file it would share was already tried. After that the role is in `failed`
    and never pending again, so the cost of a file that will not load is the
    one attempt however many frames ask.

    The control at the end is the test above, reached from this state: naming
    the role is still what retries it.
    """
    loader = _RecordingLoader(refuse="Roboto-Bold")
    fonts = load_faces([Face.PROSE_BOLD], loader=loader)
    assert fonts.failed == (Face.PROSE_BOLD,)

    for _frame in range(3):
        assert fonts(Face.CODE_BOLD) is None
        fonts.load_pending()
    assert len(loader.paths) == 1, "a draw asking for a stand-in re-read a file that had failed"
    assert fonts.pending == ()
    assert fonts.failed == (Face.PROSE_BOLD, Face.CODE_BOLD)

    loader.refuse = ""
    fonts.load([Face.CODE_BOLD])
    assert len(loader.paths) == 2
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD) is not None


def test_a_role_with_no_file_at_all_is_a_missing_face_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `fontlib` raising for a role costs the role, the same as the loader refusing it.

    Reached by removing the stand-in, which is what a later `Face` member added
    without a file or a stand-in would look like. Before the registry that was a
    `KeyError` out of `font_file`; it is now the `MissingFontError` the callers
    that degrade already catch.
    """
    # The table itself, emptied: it is `imscribe.fontfiles`' since 2026-10-12 and
    # `fontlib._STAND_INS` is that dictionary, so a rebinding of the name on
    # either module would be read by nobody.
    monkeypatch.delitem(fontlib._STAND_INS, Face.CODE_BOLD)
    with pytest.raises(fontlib.MissingFontError, match="code-bold"):
        fontlib.font_file(Face.CODE_BOLD)

    fonts = load_faces(loader=_RecordingLoader())
    assert fonts(Face.CODE_BOLD) is None and fonts.failed == (Face.CODE_BOLD,)
    assert fonts(Face.PROSE_BOLD) is not None


# ----------------------------------------------------------------------
# `load_faces`, once, against a real atlas


@pytest.fixture(scope="module")
def imgui_context() -> Any:
    """
    The process's ImGui context, made if no other test module has made one.

    The same recipe as `tests/test_imgui_draw.py`'s fixture and for the same
    reasons, which that file gives. No backend, no window, and no frame: fonts
    are added between frames, which is where `imscribe.ui.fonts` says to add them.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    return imgui


def test_the_default_loader_puts_usable_fonts_on_the_real_atlas(imgui_context: Any) -> None:
    """
    `load_faces` with no loader, against ImGui itself: the fonts can raster what is asked.

    What this adds to the fakes is that the paths are ones ImGui accepts and that
    the math face it gets is the patched one: the display-size summation has no
    codepoint in the font and is findable only if `imgui_font_file` was used.
    **It opens no window and composites nothing.**
    """
    fonts = load_faces(ALL_FACES)

    assert fonts.failed == () and set(fonts.fonts) == set(Face)
    for face in TEXT_FACES:
        assert fonts(face).is_glyph_in_font(ord("A")), face
    assert fonts(Face.CODE_BOLD) is fonts(Face.PROSE_BOLD)

    display_summation = max(fontlib.synthetic_codepoints(Face.MATH))
    assert fonts(Face.MATH).is_glyph_in_font(display_summation)


def test_an_explicit_atlas_and_size_reach_the_loader(imgui_context: Any) -> None:
    """
    `atlas_loader` takes the atlas and the size a host names, not only the defaults.
    """
    imgui = imgui_context
    atlas = imgui.get_io().fonts
    font = atlas_loader(24.0, atlas)(fontlib.font_file(Face.CODE))
    assert font is not None and font.is_glyph_in_font(ord("A"))
    assert font.legacy_size == 24.0
    assert DEFAULT_LOAD_PX == 16.0


# ----------------------------------------------------------------------
# The demo's callback is now a caller of this


def test_the_demo_s_font_callback_loads_its_one_ui_font_through_load_faces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `imscribe.ui.app.load_fonts` is a caller of `load_faces`, for one face.

    One file, the running-text face's, at 16 px, by absolute path. Until
    tranche 5 (T5-APP) it was six files, every `Face` and mathematics among
    them, because the demo's pages drew through the old ImGui backend; this
    test then listed the six. The pages draw through imtypeset now, which
    brings its own fonts, and the app's own font is only what the sidebar
    and a page's one line are read in when the library is not loaded. That a
    role sharing a file shares the font is still held above, on `load_faces`
    itself (`test_a_role_that_shares_a_file_shares_the_font_...`).
    """
    from imgui_bundle import hello_imgui

    from imscribe.ui import app

    calls: list[tuple[str, float, bool]] = []

    def fake_load_font(path: str, size: float, params: Any) -> Any:
        assert Path(path).is_absolute()
        calls.append((Path(path).name, size, params.inside_assets))
        return _Font(Path(path))

    monkeypatch.setattr(hello_imgui, "load_font", fake_load_font)
    monkeypatch.setattr(app, "_FACES", {Face.MATH: "left over from a previous run"})

    app.load_fonts()

    assert calls == [("Roboto-Regular.ttf", 16.0, False)]
    assert calls[0][1] == DEFAULT_LOAD_PX == app.UI_FONT_PX
    assert set(app._FACES) == {Face.PROSE}
    assert app._face_font(Face.PROSE).path.name == "Roboto-Regular.ttf"
    # No library in this process: a role the app did not load has no font.
    assert app._face_font(Face.CODE_BOLD) is None and app._face_font(Face.MATH) is None


# ----------------------------------------------------------------------
# Laziness, in an interpreter that has not yet measured anything


def _fresh(source: str) -> str:
    """
    Run a snippet in a new interpreter from the repository root; return its stdout.
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_importing_the_library_imports_no_fonttools() -> None:
    """
    fontTools is imported when a font is opened and not when a module is.

    `imscribe.fontlib` used to import `fontTools.ttLib` and a pen at module level,
    so anything that imported it -- `imscribe.ui.app` does, and so does this
    module's `imscribe.ui.fonts` -- paid for fontTools before measuring a glyph.
    The second line of output is the control: the same interpreter, one metric
    later, *has* imported it, so the first line is not passing because the check
    cannot see the module.
    """
    out = _fresh("""
        import sys
        import imscribe, imscribe.fontlib, imscribe.style, imscribe.markdown
        import imscribe.shipout, imscribe.ui, imscribe.ui.fonts
        print(sorted(name for name in sys.modules if name.split(".")[0] == "fontTools")[:1])
        imscribe.fontlib.metrics(imscribe.fontlib.Face.PROSE, 16.0).advance(65)
        print("fontTools.ttLib" in sys.modules)
        """)
    assert out.splitlines() == ["[]", "True"]


def test_a_document_without_mathematics_never_opens_the_math_font() -> None:
    """
    The math face is read only when mathematics is set, end to end.

    Built, composed, shipped and "loaded" (with a loader that loads nothing), a
    document of prose, code, a list and a table opens four or five font files and
    the math font is not one of them; no patched copy is written. The last line
    is the control: asking for the math face's ImGui file does both.

    The faces are observed through `font_file`, which every open goes through,
    rather than through `_face_data`'s cache, which would say what is cached and
    not what was asked.
    """
    out = _fresh("""
        from imscribe import fontlib
        from imscribe.fontmetrics import Face

        asked = []
        real = fontlib.font_file

        def spy(face):
            asked.append(face)
            return real(face)

        fontlib.font_file = spy

        from imscribe.markdown import build_document
        from imscribe.shipout import Point, ship
        from imscribe.style import Theme, char_measure, fontlib_metrics
        from imscribe.ui import compose
        from imscribe.ui.fonts import load_faces
        from imscribe.units import sp_from_px

        source = (
            "# Title\\n\\nSome *prose* with `code`, **bold** and ***both***.\\n\\n"
            "- an item\\n\\n```\\ncode block\\n```\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n"
        )
        theme = Theme.build()
        measure = char_measure(fontlib_metrics)
        document = build_document(source, theme, fontlib_metrics)
        box = compose(document, theme, sp_from_px(600.0), measure)
        commands = tuple(ship(box, Point(0, box.height), measure=measure))
        load_faces(loader=lambda path: None)

        print(len(commands) > 20)
        print(Face.MATH in asked)
        print(fontlib._patched_font_directory.cache_info().currsize)
        fontlib.imgui_font_file(Face.MATH)
        print(Face.MATH in asked, fontlib._patched_font_directory.cache_info().currsize)
        """)
    assert out.splitlines() == ["True", "False", "0", "True 1"]

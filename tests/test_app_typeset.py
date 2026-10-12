r"""
The demo app's fonts and imtypeset: the callback `advtext.ui.app.run` gives the runner.

Experimental (branch `experimental/imtypeset-adoption`). Since tranche 5
(T5-APP) the rule is the other team's answer (f) in
`../imtypeset/docs/advtext-swap-status.md`: **with the library the app adds no
font of its own** and draws its own text in the library's font for one role;
**without it, one UI font**, so that the line each page then draws can be
read. `unload` still runs before the Dear ImGui context goes. This file holds
`_load_fonts_for_run` and its helpers to that:

1. **Without the library**: in this process, with the variable unset, the
   callback is `load_fonts` and nothing else, and `load_fonts` itself never
   asks for the library even when the variable IS set
   (`tests/test_fonts_setup.py` calls it in the pytest process). It loads one
   face.
2. **With a library that answers** (a stand-in, in this process): the
   callback does not call `load_fonts`, and the font the library names for
   `UI_FACE` becomes Dear ImGui's default at `UI_FONT_PX`.
3. **A failure does not stop the app.** A library that is asked for and
   absent, and one that loads and then cannot give its fonts, both leave the
   callback returning normally with the app's own font loaded.
4. **With the real library, in a real window** (skipped, with the reason,
   when `IMTYPESET_LIBRARY` is not set): the real app is run twice, with the
   variables and with them removed, and the two atlases are read at the third
   frame. The run with the library asserts IN THE CHILD that
   `typesetter.module()` is not `None` and `typesetter.ready()`, so it cannot
   pass through the one-font path; it then draws a three-block document into
   the app's window and counts vertices, because `ready()` alone would also
   be true of a context whose fonts the runner had since thrown away.

Until tranche 5 the fourth held the opposite: that the app's six fonts were
in the atlas at the same places with the library as without, the library's
seven after them (13 fonts). That test is replaced, not kept: what it pinned
is what was removed.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext import typesetter
from advtext.description import FACE_ROLES
from advtext.fontmetrics import Face
from advtext.ui import app

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from conftest import Window

_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)


@pytest.fixture
def forgotten() -> Any:
    """
    `advtext.typesetter` as at import, before and after: these tests ask `module()`.
    """
    typesetter._forget()
    yield
    typesetter._forget()


def test_the_ui_face_and_size_are_the_ones_the_old_loader_used() -> None:
    """
    `UI_FACE` names a `Face`, the running-text one, and `UI_FONT_PX` is the
    size `advtext.ui.fonts` loads at: the app states both without importing
    either module, and this is what keeps the statements true.
    """
    from advtext.ui.fonts import DEFAULT_LOAD_PX

    assert Face[app.UI_FACE] is Face.PROSE
    assert app.UI_FACE in FACE_ROLES
    assert app.UI_FONT_PX == DEFAULT_LOAD_PX


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------


def test_without_the_variable_the_callback_is_load_fonts_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, forgotten: None
) -> None:
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    calls: list[str] = []
    monkeypatch.setattr(app, "load_fonts", lambda: calls.append("own"))
    monkeypatch.setattr(typesetter, "load_fonts", lambda *a: pytest.fail("asked for fonts"))
    monkeypatch.setattr(
        typesetter.importlib, "import_module", lambda name: pytest.fail(f"imported {name}")
    )

    app._load_fonts_for_run()
    app._unload_typesetter()

    assert calls == ["own"]
    assert typesetter.module() is None and not typesetter.ready()
    assert typesetter.reason() == "IMTYPESET_LIBRARY is not set"


def test_load_fonts_itself_never_asks_for_the_library_and_loads_one_face(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forgotten: None
) -> None:
    """
    `load_fonts` is public and is called in the pytest process; the hook is not in it.

    One face, `UI_FACE`, from one file. It was every face, mathematics
    included, while the old draw backend drew the pages.
    """
    from imgui_bundle import hello_imgui

    loaded: list[str] = []

    def load_font(path: str, size: float, params: Any) -> object:
        loaded.append(Path(path).name)
        assert size == app.UI_FONT_PX
        return object()

    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "any.so"))
    monkeypatch.setattr(hello_imgui, "load_font", load_font)
    monkeypatch.setattr(app, "_FACES", {Face.MATH: object()})
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("asked for the library"))

    app.load_fonts()

    assert set(app._FACES) == {Face[app.UI_FACE]}, "a font from an earlier atlas was kept"
    assert loaded == ["Roboto-Regular.ttf"]
    assert app._face_font(Face.PROSE) is app._FACES[Face.PROSE]


def test_without_the_library_a_role_the_app_did_not_load_has_no_font(
    monkeypatch: pytest.MonkeyPatch, forgotten: None
) -> None:
    """
    `PageContext.fonts` answers `None`, and does not ask the library, when it is not ready.
    """
    for name in _VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(app, "_FACES", {})
    monkeypatch.setattr(typesetter, "module", lambda: pytest.fail("asked for the library"))
    assert [app._face_font(face) for face in Face] == [None] * len(Face)


# ---------------------------------------------------------------------------
# 2. With a library that answers (a stand-in)
# ---------------------------------------------------------------------------


class _Library:
    """
    What `advtext.ui.app` asks of the imtypeset package: where a role's font is in the atlas.
    """

    def __init__(self, places: dict[int, int | None]) -> None:
        self.places = places
        self.asked: list[int] = []

    def font_atlas_index(self, role: int) -> int | None:
        self.asked.append(role)
        return self.places.get(role)


@pytest.fixture
def atlas() -> Any:
    """
    A Dear ImGui context of its own with three fonts in its atlas, and no backend.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    before = imgui.get_current_context()
    own = imgui.create_context()
    imgui.set_current_context(own)
    try:
        fonts = imgui.get_io().fonts
        for _ in range(3):
            fonts.add_font_default()
        yield imgui
    finally:
        imgui.destroy_context(own)
        if before is not None:
            imgui.set_current_context(before)


def _stand_in(
    monkeypatch: pytest.MonkeyPatch, library: _Library, *, loads: bool = True
) -> list[str]:
    """
    Make `advtext.typesetter` answer `library`, ready once `load_fonts` has been called.
    """
    calls: list[str] = []
    state = {"ready": False}

    def load_fonts(*_: Any) -> bool:
        calls.append("library")
        state["ready"] = loads
        return loads

    def unload() -> None:
        calls.append("unload")
        state["ready"] = False

    monkeypatch.setattr(typesetter, "module", lambda: library)
    monkeypatch.setattr(typesetter, "ready", lambda: state["ready"])
    monkeypatch.setattr(typesetter, "load_fonts", load_fonts)
    monkeypatch.setattr(typesetter, "unload", unload)
    monkeypatch.setattr(app, "load_fonts", lambda: calls.append("own"))
    return calls


def test_with_the_library_the_app_adds_no_font_and_takes_its_ui_font_from_it(
    monkeypatch: pytest.MonkeyPatch, atlas: Any
) -> None:
    """
    The library's font for `UI_FACE` becomes the default, by name, at `UI_FONT_PX`.

    The stand-in puts that role SECOND in the atlas: `Fonts[0]` is what Dear
    ImGui would draw with if the app said nothing, and it is not the one.
    """
    role = FACE_ROLES[app.UI_FACE]
    library = _Library({role: 1, FACE_ROLES["CODE"]: 2})
    calls = _stand_in(monkeypatch, library)
    monkeypatch.setattr(app, "_FACES", {Face.PROSE: object()})
    io = atlas.get_io()
    assert io.font_default is None and atlas.get_style().font_size_base != app.UI_FONT_PX

    app._load_fonts_for_run()

    assert calls == ["library"], "the app loaded a font of its own beside the library's"
    assert app._FACES == {}
    assert library.asked == [role]
    fonts = io.fonts.fonts
    assert io.font_default is not None
    assert [io.font_default == font for font in fonts] == [False, True, False]
    assert atlas.get_style().font_size_base == app.UI_FONT_PX

    # A page asking for a role gets the library's font for it, or None.
    assert app._face_font(Face.CODE) == fonts[2]
    assert app._face_font(Face.MATH) is None
    assert library.asked[-2:] == [FACE_ROLES["CODE"], FACE_ROLES["MATH"]]


def test_an_index_outside_the_atlas_is_no_font(monkeypatch: pytest.MonkeyPatch, atlas: Any) -> None:
    library = _Library({FACE_ROLES[app.UI_FACE]: 7})
    _stand_in(monkeypatch, library)
    typesetter.load_fonts()
    assert app._library_font(app.UI_FACE) is None
    assert app._use_library_ui_font() is False
    assert atlas.get_io().font_default is None


# ---------------------------------------------------------------------------
# 3. A failure does not stop the app
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["fonts do not load", "no font for the role"])
def test_a_library_that_cannot_give_the_ui_font_is_unloaded_and_the_app_loads_its_own(
    how: str, monkeypatch: pytest.MonkeyPatch, atlas: Any
) -> None:
    """
    `unload`, then `load_fonts`, in that order, and then the app's font is
    NAMED the default at `UI_FONT_PX`: the library's fonts stay in the atlas
    after its context is destroyed (measured in a window; the stand-in atlas
    here has three fonts before the app's for the same reason), so being
    loaded is not being first.
    """
    loads = how != "fonts do not load"
    library = _Library({})
    calls = _stand_in(monkeypatch, library, loads=loads)
    io = atlas.get_io()
    fonts = io.fonts.fonts
    monkeypatch.setattr(app, "_FACES", {})

    def own() -> None:
        calls.append("own")
        app._FACES[Face[app.UI_FACE]] = fonts[2]

    monkeypatch.setattr(app, "load_fonts", own)

    app._load_fonts_for_run()

    assert calls == ["library", "unload", "own"]
    assert [io.font_default == font for font in fonts] == [False, False, True]
    assert atlas.get_style().font_size_base == app.UI_FONT_PX


def test_an_own_font_that_did_not_load_is_not_named(
    monkeypatch: pytest.MonkeyPatch, atlas: Any
) -> None:
    """
    `load_faces` leaves a face that failed absent; nothing is named and ImGui draws in `Fonts[0]`.
    """
    calls = _stand_in(monkeypatch, _Library({}), loads=False)
    monkeypatch.setattr(app, "_FACES", {})

    app._load_fonts_for_run()

    assert calls == ["library", "unload", "own"]
    assert app._use_own_ui_font() is False
    assert atlas.get_io().font_default is None


def test_a_library_that_is_asked_for_and_absent_does_not_stop_the_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forgotten: None
) -> None:
    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "absent.so"))
    monkeypatch.delenv(typesetter.PACKAGE_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "imtypeset" not in p])
    monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(app, "load_fonts", lambda: calls.append("own"))

    app._load_fonts_for_run()
    app._unload_typesetter()

    assert calls == ["own"]
    assert typesetter.module() is None and not typesetter.ready()
    assert "imtypeset" in typesetter.reason()


def test_what_the_pages_were_saying_when_the_window_closed_is_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forgotten: None
) -> None:
    """
    A1 (T5-R #2). `before_exit` unloads the library, after which `ready()` is
    false for a library that drew to the last frame as for one that never
    did. So the sentence the pages were showing (`why_not()`) is read BEFORE
    the unload and kept for `scripts/shot.py` and `scripts/run_demo.py`:
    `not_drawing_at_exit()`, empty for a library that was drawing.
    """
    from advtext.ui.pages.typeset import why_not

    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "any.so"))

    # Ready until the unload: nothing to report, though `ready()` is false afterwards.
    monkeypatch.setattr(typesetter, "_ts", object())
    monkeypatch.setattr(typesetter, "_ready", True)
    monkeypatch.setattr(typesetter, "_reason", "")
    assert typesetter.ready() and why_not() == ""
    app._unload_typesetter()
    assert not typesetter.ready()
    assert app.not_drawing_at_exit() == ""

    # Switched off in the middle of the run (a view's `raise_failed`): the reason.
    monkeypatch.setattr(typesetter, "_ts", object())
    monkeypatch.setattr(typesetter, "_ready", True)
    typesetter.disable("Error: Document.draw: the library said no")
    app._unload_typesetter()
    assert app.not_drawing_at_exit() == "Error: Document.draw: the library said no"

    # A run that begins forgets the last one's.
    from imgui_bundle import immapp

    monkeypatch.setattr(immapp, "run", lambda params, *rest: None)
    app.run("A paragraph.")
    assert app.not_drawing_at_exit() == ""


def test_a_library_with_no_font_for_the_ui_role_is_said_to_be_that(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, atlas: Any, forgotten: None
) -> None:
    """
    B2 (T5-R #3). The library loaded and gave its fonts, but none for the role
    the app draws its own text in (`UI_FACE`), so the app unloaded it. Every
    page then said `FONTS_NOT_LOADED`, "load_fonts() has not succeeded in this
    process", of a `load_fonts()` that had returned True. The pages now say
    what happened: which role had no font, and that the app unloaded the
    library for it.
    """
    from advtext.ui.pages.typeset import FONTS_NOT_LOADED, why_not

    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "any.so"))
    _stand_in(monkeypatch, _Library({}), loads=True)
    monkeypatch.setattr(typesetter, "_reason", "")  # as after a `module()` that answered

    app._load_fonts_for_run()

    said = why_not()
    assert said != FONTS_NOT_LOADED and "has not succeeded" not in said
    assert app.UI_FACE in said and "unloaded" in said
    assert typesetter.trouble() == said


def test_run_gives_the_runner_both_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The two functions above are what `run` hands to hello_imgui, and fonts are not in `post_init`.
    """
    from imgui_bundle import immapp

    seen: list[Any] = []
    monkeypatch.setattr(immapp, "run", lambda params, *rest: seen.append(params.callbacks))

    app.run("A paragraph.")

    (callbacks,) = seen
    assert callbacks.load_additional_fonts is app._load_fonts_for_run
    assert callbacks.before_exit is app._unload_typesetter
    assert callbacks.post_init is not app._load_fonts_for_run


# ---------------------------------------------------------------------------
# 4. A real window
# ---------------------------------------------------------------------------

WINDOWED = r"""
import json
import sys

from imgui_bundle import hello_imgui, imgui

from advtext import typesetter
from advtext.fontmetrics import Face
from advtext.theme import Theme
from advtext.typeset_markdown import describe_markdown
from advtext.ui import app as advtext_app

WANT_LIBRARY = sys.argv[1] == "with"
SAMPLE = "The quick brown fox, 0123456789"
report = {"frames": 0}
real_gui = advtext_app.App.gui
real_fonts = advtext_app.load_fonts
real_callback = advtext_app._load_fonts_for_run
real_unload = advtext_app._unload_typesetter


def names():
    return [font.get_debug_name() for font in imgui.get_io().fonts.fonts]


def watched_fonts():
    report["own_called"] = report.get("own_called", 0) + 1
    real_fonts()


def watched_callback():
    report["before"] = len(names())
    real_callback()
    report["after_callback"] = names()


def watched_unload():
    report["imgui_context_at_exit"] = imgui.get_current_context() is not None
    module = typesetter.module()
    report["context_before_unload"] = module is not None and module.current_context() is not None
    real_unload()
    report["context_after_unload"] = module is not None and module.current_context() is not None


def draw_something():
    ts = typesetter.module()
    theme = Theme.build()
    source = "# A heading\n\nPlain, **bold**, *italic* and `code` words.\n\n    a code block\n"
    described = describe_markdown(source, theme)
    doc = ts.Document.from_blocks(described.blocks, typesetter.block_styles(described.styles))
    report["edit_error"] = doc.edit_error.code
    report["layout"] = doc.layout(500.0, typesetter.base_style(theme, 0xFFFFFFFF))
    draw_list = imgui.get_window_draw_list()
    before = draw_list.vtx_buffer.size()
    doc.draw(None, (40.0, 40.0))
    report["vertices"] = draw_list.vtx_buffer.size() - before
    report["height"] = doc.size()[1]
    report["block_errors"] = [doc.block_error(i).code for i in range(len(doc))]
    report["roles"] = [ts.get_font(role) is not None for role in typesetter.FACE_ROLE.values()]
    report["places"] = {
        face.name: ts.font_atlas_index(typesetter.FACE_ROLE[face]) for face in Face
    }
    doc.close()


def watched_gui(self):
    real_gui(self)
    report["frames"] += 1
    if report["frames"] != 3:
        return
    io = imgui.get_io()
    report["module"] = typesetter.module() is not None
    report["ready"] = typesetter.ready()
    report["reason"] = typesetter.reason()
    report["trouble"] = typesetter.trouble()
    report["fonts"] = names()
    report["font_zero"] = io.fonts.fonts[0].get_debug_name()
    report["font_default"] = None if io.font_default is None else io.font_default.get_debug_name()
    report["current_font"] = imgui.get_font().get_debug_name()
    report["font_size"] = imgui.get_font_size()
    report["sample_width"] = imgui.calc_text_size(SAMPLE).x
    report["own_faces"] = [face.name for face in advtext_app._FACES]
    report["context_fonts"] = {
        face.name: None if (font := self.context.fonts(face)) is None else font.get_debug_name()
        for face in Face
    }
    if WANT_LIBRARY:
        assert report["module"], "imtypeset is not in use: " + report["reason"]
        assert report["ready"], "imtypeset has no fonts: " + report["reason"] + report["trouble"]
        draw_something()
    hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.load_fonts = watched_fonts
advtext_app._load_fonts_for_run = watched_callback
advtext_app._unload_typesetter = watched_unload
advtext_app.App.gui = watched_gui
advtext_app.run(tab="typeset")
report["ready_after_run"] = typesetter.ready()
report["imported"] = "imtypeset" in sys.modules
print(json.dumps(report))
"""


def _run(window: Window, how: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    script = window.out / "app_typeset.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    report: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return report


def test_in_a_real_window_without_the_library_the_atlas_is_the_one_ui_font(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The plain gate's half, and it needs no library: one font, the app's, drawn at `UI_FONT_PX`.
    """
    without = _run(window, "without", monkeypatch)

    assert without["module"] is False and without["ready"] is False
    assert without["imported"] is False
    assert without["own_called"] == 1
    assert without["before"] == 0
    assert without["fonts"] == without["after_callback"] and len(without["fonts"]) == 1
    assert without["own_faces"] == [app.UI_FACE]
    assert without["current_font"] == without["font_zero"] == without["fonts"][0]
    assert without["font_default"] is None
    assert without["font_size"] == app.UI_FONT_PX
    faces = without["context_fonts"]
    assert faces[app.UI_FACE] == without["fonts"][0]
    assert [name for name, font in faces.items() if font is not None] == [app.UI_FACE]
    assert without["context_before_unload"] is False


def test_in_a_real_window_the_library_is_ready_and_every_font_in_the_atlas_is_its_own(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    without = _run(window, "without", monkeypatch)
    with_library = _run(window, "with", monkeypatch)

    # Ready at a frame, with every role holding a font, and it draws.
    assert with_library["module"] is True and with_library["ready"] is True
    assert with_library["trouble"] == "" and with_library["reason"] == ""
    assert with_library["roles"] == [True] * len(Face)
    assert with_library["edit_error"] == 0 and with_library["layout"] is True
    assert with_library["block_errors"] == [0, 0, 0]
    assert with_library["vertices"] > 0 and with_library["height"] > 0

    # The atlas: one font per role, all the library's, and none of the app's.
    # It was 13 (the app's six, then these seven) until the app stopped
    # adding its own copies.
    fonts = with_library["fonts"]
    assert with_library.get("own_called", 0) == 0, "the app loaded a font of its own"
    assert with_library["own_faces"] == []
    assert with_library["before"] == 0
    assert fonts == with_library["after_callback"] and len(fonts) == len(Face)
    places = with_library["places"]
    assert sorted(places.values()) == list(range(len(Face)))
    assert without["fonts"][0] not in fonts, "the app's own font is in the atlas"

    # The UI font is the library's font for UI_FACE, set by name, at the
    # size the app's own font is drawn at; the same file, so the same width.
    ui = fonts[places[app.UI_FACE]]
    assert with_library["font_default"] == ui and with_library["current_font"] == ui
    assert with_library["font_size"] == without["font_size"] == app.UI_FONT_PX
    assert with_library["sample_width"] == pytest.approx(without["sample_width"], abs=1.0)

    # A page that asks for a role gets the library's font for it.
    assert with_library["context_fonts"] == {name: fonts[at] for name, at in places.items()}

    # Leaving: the library's context went while Dear ImGui's was still there.
    assert with_library["imgui_context_at_exit"] is True
    assert with_library["context_before_unload"] is True
    assert with_library["context_after_unload"] is False
    assert with_library["ready_after_run"] is False

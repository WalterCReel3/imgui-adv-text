"""
`typesetter.ready()` and the Dear ImGui context the fonts were loaded in (pptmstr's P24).

The library's context belongs to ONE Dear ImGui context: the one that was
current at `load_fonts()`. pptmstr found by a run that when that context is
destroyed without `typesetter.unload()` and another is made, `ready()` stayed
true and a kept view's `draw()` returned without raising. These tests make
that run again, twice, because where the allocator puts the new context
decides what can tell the two apart:

- **at the old address** (what the allocator often does when one is
  destroyed and the next made; the child makes contexts until one lands
  there and reports it): the binding answers the very same Python object
  for the new context, so comparing contexts says "the same";
- **at another address** (made while the first is still alive).

`ready()` is held false in both, and with no context current; true again
back in the context the fonts are in; and after `load_fonts()` in the new
one a kept view draws what it drew.

The children need the library: `make test TYPESET=1`. The tests at the foot
need nothing and hold the rule on stand-ins.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from advtext import typesetter
from advtext.typesetter import Kind

_ROOT = Path(__file__).resolve().parent.parent

_COMMON = r"""
import json, sys
from imgui_bundle import imgui
from advtext import typesetter
from advtext.theme import Theme
from advtext.typeset_markdown import parse_markdown
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView
from advtext.ui.typeset_diff_view import code_face_lacks

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)
report = {"module": True}

def context(made=None):
    made = imgui.create_context() if made is None else made
    imgui.set_current_context(made)
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(900.0, 700.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    return made

def context_at(old):
    # A new context at the address of a destroyed one. Where the allocator
    # puts ONE new context depends on everything else the process allocated
    # (measured: taking one line out of this script moved it), so contexts
    # are made, and kept, until one lands there; the others are destroyed.
    spare = []
    for _ in range(64):
        made = imgui.create_context()
        if made is old:
            break
        spare.append(made)
    else:
        made = spare.pop()
    for one in spare:
        imgui.destroy_context(one)
    return context(made), len(spare) + 1

def frame(view):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        before = imgui.get_window_draw_list().vtx_buffer.size()
        view.draw()
        return imgui.get_window_draw_list().vtx_buffer.size() - before
    except TypesetUnavailable as exc:
        return str(exc)
    finally:
        imgui.end()
        imgui.render()

def state():
    return [typesetter.ready(), typesetter.kind().value, typesetter.module() is not None,
            typesetter.reason(), typesetter.why_not_ready()]

def asked():
    try:
        return code_face_lacks("café")
    except TypesetUnavailable as exc:
        return str(exc)

theme = Theme.build()
blocks = parse_markdown("# One\n\nTwo words.\n\nThree more words.\n", theme).blocks
"""

# pptmstr's run: destroy the context without unload(), keep a view, make another.
_DESTROYED = _COMMON + r"""
first = context()
report["before_load"] = state()
report["load"] = typesetter.load_fonts()
report["loaded"] = state()
view = TypesetView(blocks, theme=theme)
report["drew"] = frame(view)
report["edits"] = dict(view.edits)

imgui.destroy_context(first)                    # and no typesetter.unload()
report["no_context"] = state()
second, report["tries"] = context_at(first)
report["at_the_old_address"] = second is first  # the binding's object for the new one
report["new_context"] = state()
report["kept_view"] = frame(view)
report["asked"] = asked()
report["edits_after"] = dict(view.edits)
report["still_in_use"] = [typesetter.module() is ts, typesetter.trouble()]
report["font"] = typesetter.font(__import__("advtext").Face.CODE) is None
try:
    typesetter.window_draw_list()
    report["draw_list"] = "answered"
except RuntimeError as exc:
    report["draw_list"] = "RuntimeError"

report["load_again"] = typesetter.load_fonts()
report["loaded_again"] = state()
report["drew_again"] = frame(view)
report["edits_again"] = dict(view.edits)
typesetter.unload()
report["unloaded"] = state()
imgui.destroy_context(second)
print(json.dumps(report))
"""

# The same with the new context somewhere else: it is made while the first is alive.
_BESIDE = _COMMON + r"""
first = context()
report["load"] = typesetter.load_fonts()
view = TypesetView(blocks, theme=theme)
report["drew"] = frame(view)
second = context()
report["at_the_old_address"] = second is first
report["in_the_second"] = state()
report["kept_view_in_the_second"] = frame(view)
imgui.set_current_context(first)
report["back_in_the_first"] = state()
report["drew_back_in_the_first"] = frame(view)
report["edits"] = dict(view.edits)
imgui.destroy_context(first)
imgui.set_current_context(second)
report["first_destroyed"] = state()
report["kept_view"] = frame(view)
report["load_again"] = typesetter.load_fonts()
report["drew_again"] = frame(view)
report["edits_again"] = dict(view.edits)
typesetter.unload()
imgui.destroy_context(second)
print(json.dumps(report))
"""

# A host that loads MORE fonts of its own into the new context than the old
# one held, and never the library's: twelve runs, since which of them puts a
# host font at the old library font's address is the allocator's to say.
_CROWDED = r"""
import json
from imgui_bundle import imgui
from advtext import Face, fontlib, typesetter

def context():
    made = imgui.create_context()
    imgui.set_current_context(made)
    io = imgui.get_io()
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    return made

def host_fonts(count, files):
    atlas = imgui.get_io().fonts
    for at in range(count):
        if files:
            atlas.add_font_from_file_ttf(str(fontlib.font_file(list(Face)[at % len(Face)])), 16.0)
        else:
            atlas.add_font_default()

rows = []
for files in (True, False):
    for before in (0, 1, 3):
        for after in (8, 12):
            first = context()
            host_fonts(before, files)
            loaded = typesetter.load_fonts()
            _, _, font, index, size = typesetter._home
            imgui.destroy_context(first)
            second = context()
            host_fonts(after, files)
            fonts = imgui.get_io().fonts.fonts
            rows.append({
                "loaded": loaded, "at_the_old_address": second is first,
                "same_object": [at for at in range(len(fonts)) if fonts[at] is font],
                "ready": typesetter.ready(), "module": typesetter.module() is not None,
            })
            typesetter.unload()
            imgui.destroy_context(second)
print(json.dumps({"module": typesetter.module() is not None, "rows": rows}))
"""

_GONE = "the Dear ImGui context typesetter.load_fonts() loaded the fonts in is not the current one"


def _child(code: str) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    pytest.importorskip("imgui_bundle")
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["module"] is True, report.get("reason")
    return report


@pytest.fixture(scope="module")
def destroyed() -> dict[str, Any]:
    return _child(_DESTROYED)


@pytest.fixture(scope="module")
def beside() -> dict[str, Any]:
    return _child(_BESIDE)


@pytest.fixture(scope="module")
def crowded() -> dict[str, Any]:
    return _child(_CROWDED)


def test_a_host_font_at_the_old_font_s_address_is_not_taken_for_the_library_s(
    crowded: dict[str, Any],
) -> None:
    """
    Measured 2026-10-12: in 3 of these 12 runs, and in 5 the next time, a
    font the HOST loaded into the new context was the same Python object as
    the font the library had added to the old one. `ready()` is false in all twelve. How many
    coincide is the allocator's and is not asserted.
    """
    rows = crowded["rows"]
    assert len(rows) == 12 and all(row["loaded"] and row["module"] for row in rows)
    assert [row["ready"] for row in rows] == [False] * 12, rows


def test_the_new_context_was_at_the_old_address_in_one_run_and_not_in_the_other(
    destroyed: dict[str, Any], beside: dict[str, Any]
) -> None:
    """
    Which case each child is. The allocator promises nothing: the child makes
    contexts until one lands at the old address, and when none of 64 does the
    same-address case is held by the stand-ins at the foot of this file alone.
    """
    assert beside["at_the_old_address"] is False, "two contexts alive at one address"
    if destroyed["at_the_old_address"] is not True:
        pytest.skip(f"no new context at the old address in {destroyed['tries']} tries")


def test_ready_is_false_once_the_context_the_fonts_were_loaded_in_is_destroyed(
    destroyed: dict[str, Any],
) -> None:
    assert destroyed["before_load"] == [
        False,
        "ready",
        True,
        "",
        "typesetter.load_fonts() has not succeeded",
    ]
    assert destroyed["load"] is True
    assert destroyed["loaded"] == [True, "ready", True, "", ""]
    gone = [False, "ready", True, "", _GONE]
    assert destroyed["no_context"][:4] == gone[:4]
    assert destroyed["no_context"][4].startswith(_GONE)
    assert destroyed["new_context"][:4] == gone[:4], "a new context was taken for the old one"
    assert destroyed["new_context"][4].startswith(_GONE)


def test_a_kept_view_raises_and_nothing_is_switched_off(destroyed: dict[str, Any]) -> None:
    assert isinstance(destroyed["drew"], int) and destroyed["drew"] > 0
    said = destroyed["kept_view"]
    assert isinstance(said, str), f"the kept view drew {said} vertices in a context without fonts"
    assert said.startswith("imtypeset cannot draw: " + _GONE)
    assert destroyed["asked"].startswith("imtypeset cannot be asked: " + _GONE)
    # Nothing was handed to the library, and it was not switched off.
    assert destroyed["edits_after"] == destroyed["edits"]
    assert destroyed["still_in_use"] == [True, ""]
    assert destroyed["font"] is True
    assert destroyed["draw_list"] == "RuntimeError"


def test_load_fonts_in_the_new_context_and_the_kept_view_draws_what_it_drew(
    destroyed: dict[str, Any],
) -> None:
    assert destroyed["load_again"] is True
    assert destroyed["loaded_again"] == [True, "ready", True, "", ""]
    assert destroyed["drew_again"] == destroyed["drew"]
    assert destroyed["edits_again"]["set"] == destroyed["edits"]["set"] + 1
    assert destroyed["unloaded"] == [
        False,
        "ready",
        True,
        "",
        "typesetter.load_fonts() has not succeeded",
    ]


def test_another_context_beside_the_first_is_not_ready_and_the_first_still_is(
    beside: dict[str, Any],
) -> None:
    assert beside["load"] is True and beside["drew"] > 0
    assert beside["in_the_second"][:4] == [False, "ready", True, ""]
    assert beside["in_the_second"][4].startswith(_GONE)
    assert isinstance(beside["kept_view_in_the_second"], str)
    # Not latched: the library's context is where it was, and so are its fonts.
    assert beside["back_in_the_first"] == [True, "ready", True, "", ""]
    assert beside["drew_back_in_the_first"] == beside["drew"]
    assert beside["edits"]["set"] == 1, "the document was made again for nothing"


def test_the_first_destroyed_under_a_second_made_beside_it(beside: dict[str, Any]) -> None:
    assert beside["first_destroyed"][:4] == [False, "ready", True, ""]
    assert isinstance(beside["kept_view"], str)
    assert beside["load_again"] is True
    assert beside["drew_again"] == beside["drew"]
    assert beside["edits_again"]["set"] == 2


# ---------------------------------------------------------------------------
# Without the library: the rule, on stand-ins
# ---------------------------------------------------------------------------


_STATE = ("_ts", "_package", "_tried", "_reason", "_why", "_disabled", "_ready", "_home")


@pytest.fixture(autouse=True)
def _as_it_was() -> Any:
    kept = {name: getattr(typesetter, name) for name in _STATE}
    yield
    for name, value in kept.items():
        setattr(typesetter, name, value)


class _Source:
    def __init__(self, size: int) -> None:
        self.font_data_size = size


class _Font:
    def __init__(self, size: int = 1000) -> None:
        self.sources = [_Source(size)]


class _Atlas:
    def __init__(self, fonts: list[object]) -> None:
        self.fonts = fonts


class _IO:
    def __init__(self, atlas: _Atlas) -> None:
        self.fonts = atlas


class _Imgui:
    """A stand-in for `imgui_bundle.imgui`: which context is current, and its atlas's fonts."""

    def __init__(self, current: object | None, fonts: list[object]) -> None:
        self.current = current
        self.fonts = _Atlas(fonts)
        self.asked = 0

    def get_current_context(self) -> object | None:
        return self.current

    def get_io(self) -> _IO:
        self.asked += 1
        return _IO(self.fonts)


class _Library:
    """A stand-in imtypeset that fails the test when it is asked anything."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the library was asked for {name}")


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> tuple[_Imgui, object, object]:
    home, font = object(), _Font(4321)
    imgui = _Imgui(home, [_Font(), _Font(), font])
    monkeypatch.setattr(typesetter, "_ts", _Library())
    monkeypatch.setattr(typesetter, "_ready", True)
    monkeypatch.setattr(typesetter, "_reason", "")
    monkeypatch.setattr(typesetter, "_home", (imgui, home, font, 2, 4321))
    return imgui, home, font


def test_ready_asks_dear_imgui_and_never_the_library(loaded: tuple[_Imgui, object, object]) -> None:
    assert typesetter.ready() and typesetter.why_not_ready() == ""
    assert typesetter.kind() is Kind.READY


def test_another_context_is_not_ready_and_its_atlas_is_not_read(
    loaded: tuple[_Imgui, object, object],
) -> None:
    imgui, home, _font = loaded
    for current in (None, object()):
        imgui.current = current
        assert not typesetter.ready()
        assert typesetter.why_not_ready().startswith(_GONE)
    assert imgui.asked == 0, "get_io() with no context current is an assertion in Dear ImGui"
    assert typesetter.kind() is Kind.READY and typesetter.reason() == ""
    imgui.current = home
    assert typesetter.ready(), "it is not latched"


def test_the_same_object_with_another_atlas_is_not_ready(
    loaded: tuple[_Imgui, object, object],
) -> None:
    """A new context at the old address: the binding's object is the same one."""
    imgui, _home, font = loaded
    for fonts in ([], [_Font()], [_Font(), _Font(), _Font(), _Font()]):
        imgui.fonts.fonts = fonts
        assert not typesetter.ready()
        assert typesetter.why_not_ready().startswith(_GONE)
    assert typesetter.kind() is Kind.READY
    imgui.fonts.fonts = [_Font(), _Font(), font]
    assert typesetter.ready()


def test_a_host_that_takes_a_font_of_its_own_off_the_atlas_is_still_ready(
    loaded: tuple[_Imgui, object, object],
) -> None:
    imgui, home, font = loaded
    imgui.fonts.fonts = [_Font(), font]
    assert typesetter.ready()
    assert typesetter._home == (imgui, home, font, 1, 4321), "where it stands now is remembered"
    imgui.fonts.fonts = [_Font(), _Font(), _Font(), font]
    assert typesetter.ready()


def test_the_same_font_object_with_other_bytes_is_a_host_s_font_at_the_old_address(
    loaded: tuple[_Imgui, object, Any],
) -> None:
    """Measured in 3 runs of 12 with a host that loads more fonts: the allocator's doing."""
    imgui, _home, font = loaded
    font.sources = [_Source(4320)]
    assert not typesetter.ready()
    imgui.fonts.fonts = [font]
    assert not typesetter.ready(), "found along the list and taken for the library's"


def test_with_no_font_to_go_by_the_context_alone_decides(
    loaded: tuple[_Imgui, object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    imgui, home, _font = loaded
    monkeypatch.setattr(typesetter, "_home", (imgui, home, None, 0, 0))
    imgui.fonts.fonts = []
    assert typesetter.ready()
    imgui.current = None
    assert not typesetter.ready()


def test_a_check_that_raises_is_not_ready_and_switches_nothing_off(
    loaded: tuple[_Imgui, object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    imgui, _home, _font = loaded

    def raises() -> Any:
        raise OSError("gone")

    monkeypatch.setattr(imgui, "get_io", raises)
    assert not typesetter.ready()
    assert typesetter.module() is typesetter._ts and typesetter.kind() is Kind.READY


def test_why_not_ready_says_the_reason_when_the_library_is_not_in_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(typesetter, "_ts", None)
    monkeypatch.setattr(typesetter, "_ready", False)
    monkeypatch.setattr(typesetter, "_reason", "a refusal")
    assert typesetter.why_not_ready() == "a refusal"
    monkeypatch.setattr(typesetter, "_ts", object())
    monkeypatch.setattr(typesetter, "_reason", "")
    assert typesetter.why_not_ready() == "typesetter.load_fonts() has not succeeded"


def test_unload_disable_and_reset_forget_the_context(
    loaded: tuple[_Imgui, object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(typesetter, "_package", None)
    for forget in (typesetter.unload, lambda: typesetter.disable("x"), typesetter.reset):
        monkeypatch.setattr(typesetter, "_home", loaded)
        forget()
        assert typesetter._home is None and not typesetter.ready()

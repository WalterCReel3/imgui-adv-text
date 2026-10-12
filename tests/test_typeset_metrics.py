r"""
A face's line metrics for sizing a theme: who answers, and that the two answers are one.

`imscribe.typeset_metrics` asks imtypeset once `imscribe.typesetter.ready()` is
true and the reference core's font reader before. Two halves:

1.  **Without fonts in the library** (this process, with `ready` held false:
    another file's test may have loaded the library's fonts here): the old
    reader answers, by the name on `imscribe.style` read at the call.
2.  **With them** (a fresh interpreter with a Dear ImGui context of its own;
    skipped without the library): the library answers, and for every face at
    14 to 20 px its em for a pixel height, the theme sized from it and the
    description of `demo/sample.md` under that theme are EQUAL to the old
    reader's. That equality is why the order a host sizes its themes in is a
    matter of cost and not of result; if it ever fails, a theme sized before
    the fonts are loaded and one sized after break their lines differently.

What reaching either loads of imscribe is `tests/test_typeset_closure.py`'s.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import fontfiles, typeset_metrics, typesetter
from imscribe.primitives import Face, sp_from_px
from imscribe.theme import Theme, font_key

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def no_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    """The library has no fonts, whatever another test left loaded in this process."""
    monkeypatch.setattr(typesetter, "ready", lambda: False)
    monkeypatch.setattr(typesetter, "why_not_ready", lambda: "held false by a test")


def test_without_fonts_in_the_library_the_old_reader_answers(no_fonts: None) -> None:
    from imscribe import fontlib, style

    assert not typeset_metrics.library_answers()
    key = font_key(Face.PROSE, sp_from_px(16.0))
    assert typeset_metrics.face_metrics(key) is style.fontlib_metrics(key)
    for face in Face:
        for height in (14.0, 16.0, 17.5, 20.0):
            assert typeset_metrics.em_size_for_pixel_height(
                face, height
            ) == fontlib.em_size_for_pixel_height(face, height)
    default = Theme.at_pixel_height(16.0)
    assert default == Theme.at_pixel_height(16.0, metrics=style.fontlib_metrics)
    assert default == Theme.at_pixel_height(16.0, metrics=typeset_metrics.face_metrics)


def test_a_replacement_of_the_old_readers_name_is_the_one_asked(
    no_fonts: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    `Theme.at_pixel_height` with no resolver reads `typeset_metrics.face_metrics`
    at the call, and that reads `imscribe.style.fontlib_metrics` at the call.
    """
    from imscribe import style

    real = style.fontlib_metrics
    asked: list[str] = []

    def watching(key: str) -> Any:
        asked.append(key)
        return real(key)

    monkeypatch.setattr(style, "fontlib_metrics", watching)
    Theme.at_pixel_height(16.0)
    assert len(asked) == 1

    mine: list[str] = []

    def own(key: str) -> Any:
        mine.append(key)
        return real(key)

    monkeypatch.setattr(typeset_metrics, "face_metrics", own)
    Theme.at_pixel_height(16.0)
    assert len(mine) == 1 and len(asked) == 1


def test_the_library_asked_before_it_has_fonts_says_so(no_fonts: None) -> None:
    """
    `library_metrics` is the library or an error, never the old reader: the
    error is the type the old reader raises for a role with no file.
    """
    with pytest.raises(fontfiles.MissingFontError, match="imtypeset cannot be asked: held false"):
        typeset_metrics.library_metrics(font_key(Face.PROSE, sp_from_px(16.0)))


def test_what_is_no_face_is_a_type_error_at_the_call() -> None:
    with pytest.raises(TypeError, match="takes an imscribe Face, not str"):
        typeset_metrics.em_size_for_pixel_height("prose", 16.0)  # type: ignore[arg-type]


def test_the_probe_em_is_one_the_library_takes_and_common_fonts_answer_exactly() -> None:
    """
    The em every question is asked at: within imtypeset's limit of 1,000,000,
    and a whole multiple of the units per em of the bundled fonts (1000 and
    2048) and of 1024, so their metrics come back as whole numbers a C float
    holds exactly.
    """
    probe = typeset_metrics.PROBE_EM
    assert 0 < probe <= 1_000_000
    for units in (1000, 1024, 2048):
        assert probe % units == 0
        # The largest font-unit value of a metric (an ascent of twice the em,
        # say), scaled, is still a whole number below 2**24.
        assert 2 * units * (probe / units) < 2**24


def test_the_two_calls_are_on_the_list_the_gate_holds_a_package_to() -> None:
    """
    An imtypeset without `font_metrics` or `glyph_advance` (before its commit
    `74f5116`) is refused at the gate with the sentence that names them; it
    is not found out at the first theme.
    """
    assert {"font_metrics", "glyph_advance", "face_has_glyph"} <= set(typesetter.REQUIRED[""])


def test_registering_a_font_drops_what_the_old_reader_read() -> None:
    """
    `register_font` is `imscribe.fontfiles`' and knows nothing of
    `imscribe.fontlib`; the old reader is told as a listener, so a theme sized
    by it after a registration is measured from the new file.
    """
    from imscribe import fontlib

    try:
        before = fontlib.em_size_for_pixel_height(Face.CODE_BOLD, 16.0)
        assert before == fontlib.em_size_for_pixel_height(Face.PROSE_BOLD, 16.0)
        fontfiles.register_font(Face.CODE_BOLD, fontfiles.font_file(Face.CODE))
        after = fontlib.em_size_for_pixel_height(Face.CODE_BOLD, 16.0)
        assert after == fontlib.em_size_for_pixel_height(Face.CODE, 16.0) != before
    finally:
        fontfiles.unregister_font(Face.CODE_BOLD)
    assert fontlib.em_size_for_pixel_height(Face.CODE_BOLD, 16.0) == before


_WITH_FONTS = r"""
import itertools, json, sys
from imgui_bundle import imgui
from imscribe import fontfiles, fontlib, style, typeset_metrics, typesetter
from imscribe.primitives import Face, sp_from_px
from imscribe.theme import Faces, Theme, font_key
from imscribe.typeset_markdown import MarkdownConverter, parse_markdown

imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
assert typesetter.load_fonts(), typesetter.reason()
out = {"ready": typeset_metrics.library_answers()}
heights = [14 + step / 4 for step in range(25)]
out["em"] = [
    (face.value, height)
    for face in Face
    for height in heights
    if fontlib.em_size_for_pixel_height(face, height)
    != typeset_metrics.em_size_for_pixel_height(face, height)
]
out["advances"] = []
out["lines"] = []
for face in Face:
    size = float(sp_from_px(fontlib.em_size_for_pixel_height(face, 16.0)))
    old, new = fontlib.metrics(face, size), typeset_metrics.LibraryMetrics(face, size)
    out["advances"] += [
        (face.value, code) for code in range(32, 127) if old.advance(code) != new.advance(code)
    ]
    for name in ("ascent", "descent", "x_height", "space_width", "em", "size"):
        a, b = getattr(old, name), getattr(new, name)
        if abs(a - b) > 1e-9 * max(1.0, abs(a)):
            out["lines"].append((face.value, name, a, b))
    assert new.face is face and new.has(ord("a")) and not new.has(0x10FFFF)
tables = {"default": Faces(), "mono": Faces.mono()}
out["themes"] = []
out["descriptions"] = []
source = open("demo/sample.md", encoding="utf-8").read()
for (name, faces), height in itertools.product(tables.items(), heights):
    old = Theme.at_pixel_height(height, faces=faces, metrics=style.fontlib_metrics)
    new = Theme.at_pixel_height(height, faces=faces)
    by_library = typeset_metrics.library_metrics
    assert new == Theme.at_pixel_height(height, faces=faces, metrics=by_library)
    if old != new:
        out["themes"].append((name, height))
    if height == int(height):
        a = MarkdownConverter(old).describe(parse_markdown(source, old).blocks)
        b = MarkdownConverter(new).describe(parse_markdown(source, new).blocks)
        if a != b:
            out["descriptions"].append((name, height))
probe = typeset_metrics.library_metrics(font_key(Face.PROSE, sp_from_px(16.0)))
refused = []
for ask in (lambda: probe.bbox(65), lambda: probe.kern(65, 86)):
    try:
        ask()
    except NotImplementedError as error:
        refused.append(str(error))
out["refused"] = refused
# A role the library was given no font for.
assert typesetter.load_fonts([Face.PROSE])
try:
    typeset_metrics.em_size_for_pixel_height(Face.CODE, 16.0)
except fontfiles.MissingFontError as error:
    out["no_font"] = str(error)
try:
    Theme.at_pixel_height(16.0, faces=Faces.mono())
except fontfiles.MissingFontError as error:
    out["no_font_theme"] = type(error).__name__
out["one_role"] = Theme.at_pixel_height(16.0) == Theme.at_pixel_height(
    16.0, metrics=style.fontlib_metrics
)
print(json.dumps(out))
"""


def test_with_fonts_the_library_answers_and_its_answers_are_the_old_readers() -> None:
    """
    The second half of the module docstring, in a fresh interpreter: 7 faces
    at 25 heights from 14 to 20 px, 95 advances a face, 50 themes and 14
    descriptions of `demo/sample.md`, by the two routes, and no difference.

    The line metrics themselves are held to nine digits and not to the last
    binary place: asked at `PROBE_EM` and scaled, a font of 2048 units per em
    (Roboto) can differ from the old reader's in the last place of a double
    at an em that is no whole number (measured: at most 1.8e-15 px). The em
    for a height, the advances at a whole size, and everything a theme is
    made of are equal exactly.
    """
    if not os.environ.get("IMTYPESET_LIBRARY"):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    result = subprocess.run(
        [sys.executable, "-c", _WITH_FONTS], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.splitlines()[-1])
    assert out["ready"] is True
    assert out["em"] == [], "the em for a pixel height differs between the two readers"
    assert out["advances"] == []
    assert out["lines"] == []
    assert out["themes"] == [], "a theme sized by the library differs from the old reader's"
    assert out["descriptions"] == []
    assert out["refused"] == [
        "imtypeset does not answer a glyph's ink box; imscribe.style.fontlib_metrics does",
        "imtypeset does not answer a pair's kern; imscribe.style.fontlib_metrics does",
    ]
    assert out["no_font"].startswith("imtypeset cannot measure code: ")
    assert out["no_font"].endswith("give the role a font with imscribe.typesetter.load_fonts()")
    assert out["no_font_theme"] == "MissingFontError"
    assert out["one_role"] is True

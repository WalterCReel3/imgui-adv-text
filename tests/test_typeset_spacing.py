"""
A theme's `Spacing` reaches the library: the space after a sentence is what the theme says.

pptmstr's P23 (its `HANDOFF-advtext.md`, A2 and P23): with
`Theme.at_pixel_height(..., spacing=Spacing.FRENCH)` one of 52 spaces of a
paragraph was laid out a third wider than the rest (10.168 px against 7.626).
It was the space after `waffle.`: `imscribe.typesetter.base_style` made the
library's `Style` from the theme's size and nothing else, so every document was
laid out under the library's default, `Spacing.Sentence`, whatever the theme
said. That default is what `Spacing.EXTRA_SPACE_ONLY`, the theme's own default,
means, which is why nothing showed until a host asked for something else.

Two halves. The table of names needs no library. What a view lays out does,
and runs in a child with a Dear ImGui context and no window, as
`tests/test_typeset.py` does: `make test TYPESET=1`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter
from imscribe.theme import Spacing

_ROOT = Path(__file__).resolve().parent.parent

# The sentence pptmstr's probe set (`scripts/measure_typeset_advances.py`): one
# full stop after a lower-case letter with a space after it, and two after a
# capital, which TeX's rule does not take for the end of a sentence.
_PROSE = (
    "To Wave at AVATAR Wavy Types we fix five affine offices: a Tyrant Yawns, "
    "Vows Await, and LT. P. Avery fills the final waffle. Typography of ordinary "
    "running text depends on the rhythm of its word spaces, which a reader takes "
    "in without ever looking at one of them directly."
)


def test_every_spacing_a_theme_can_name_has_the_librarys_number() -> None:
    assert set(typesetter.SPACINGS) == {member.name for member in Spacing}
    # `ImTypesetSpacing_` in imtypeset.h: Sentence 0, French 1, TeX 2.
    assert typesetter.SPACINGS == {"EXTRA_SPACE_ONLY": 0, "FRENCH": 1, "NONFRENCH": 2}


_CHILD = r"""
import json
import sys

from imgui_bundle import imgui

from imscribe import Align, Faces, Spacing, Theme, TypesetView, typesetter

PROSE = sys.argv[1]
ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)
report = {"module": True}
context = imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["ready"] = typesetter.load_fonts() and typesetter.ready()
report["enumerators"] = [
    [typesetter.SPACINGS["EXTRA_SPACE_ONLY"], int(ts.Spacing.Sentence)],
    [typesetter.SPACINGS["FRENCH"], int(ts.Spacing.French)],
    [typesetter.SPACINGS["NONFRENCH"], int(ts.Spacing.TeX)],
]


def spaces(view):
    # (the character before, the width as laid out) of every space not at a line's end.
    # Wide enough for one line, so that no full stop is at the end of one.
    view.layout_for(4000.0)
    ends = {line.end for line in view.set_lines(0, 1)}
    text = view.texts[0]
    out = []
    for at, char in enumerate(text):
        if char == " " and at + 1 not in ends:
            rects = view.span_rects(0, at, at + 1)
            out.append([text[at - 1], round(rects[0][2] - rects[0][0], 3)])
    return out


report["styles"] = {}
report["spaces"] = {}
report["fenced"] = {}
for faces_name, faces in (("mono", Faces.mono()), ("default", Faces())):
    for spacing in Spacing:
        theme = Theme.at_pixel_height(16.0, faces=faces, align=Align.LEFT, spacing=spacing)
        report["styles"][spacing.name] = int(typesetter.base_style(theme).Spacing)
        view = TypesetView(PROSE, theme=theme)
        report["spaces"][faces_name + " " + spacing.name] = spaces(view)
        view.close()
        view = TypesetView("```\n" + PROSE + "\n```", theme=theme)
        report["fenced"][faces_name + " " + spacing.name] = spaces(view)
        view.close()

# A view told another theme lays out under that theme's spacing.
view = TypesetView(PROSE, theme=Theme.build(align=Align.LEFT))
before = spaces(view)
view.set_theme(Theme.build(align=Align.LEFT, spacing=Spacing.FRENCH))
report["set_theme"] = [before, spaces(view)]
view.close()
report["default_is_extra_space_only"] = Theme.build().spacing.name
typesetter.unload()
imgui.destroy_context(context)
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    pytest.importorskip("imgui_bundle")
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, _PROSE],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    made: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    assert made["module"] is True, "imtypeset is not in use: " + made.get("reason", "")
    assert made["ready"] is True
    return made


def _widths(spaces: list[list[Any]]) -> set[float]:
    return {width for _, width in spaces}


def test_the_numbers_are_the_librarys_enumerators(report: dict[str, Any]) -> None:
    for ours, theirs in report["enumerators"]:
        assert ours == theirs


def test_the_style_a_document_is_laid_out_with_carries_the_themes_spacing(
    report: dict[str, Any],
) -> None:
    assert report["styles"] == {"EXTRA_SPACE_ONLY": 0, "FRENCH": 1, "NONFRENCH": 2}


@pytest.mark.parametrize("faces", ["mono", "default"])
def test_under_french_spacing_every_space_of_a_ragged_paragraph_is_one_width(
    report: dict[str, Any], faces: str
) -> None:
    spaces = report["spaces"][f"{faces} FRENCH"]
    assert len(spaces) > 40
    assert [before for before, _ in spaces].count(".") == 3
    assert len(_widths(spaces)) == 1, sorted(_widths(spaces))


@pytest.mark.parametrize("faces", ["mono", "default"])
@pytest.mark.parametrize("spacing", ["EXTRA_SPACE_ONLY", "NONFRENCH"])
def test_otherwise_the_space_after_a_sentence_is_a_third_wider_and_no_other_is(
    report: dict[str, Any], faces: str, spacing: str
) -> None:
    """
    **Restated for the mono page on imtypeset 0.4.1.** Until then this held
    for both sets of faces: one space, after "waffle.", a third wider than a
    word space. With `Faces.mono()` the prose is in the code face, which the
    library now sets on the device's grid, where "spaces never stretch"
    (imtypeset's H34: a fixed-pitch face on the device is on a grid of whole
    cells): under every spacing each space of the mono page is ONE CELL, the
    one after a sentence too. A third of a cell more would put everything
    after it off the columns, so the grid is what is asserted there; the
    proportional page is asserted as it was.
    """
    spaces = report["spaces"][f"{faces} {spacing}"]
    french = report["spaces"][f"{faces} FRENCH"]
    word = french[0][1]
    wider = [(before, width) for before, width in spaces if width != word]
    if faces == "mono":
        # Was `== ["."]`, a third wider (above).
        assert wider == []
        assert len(spaces) == len(french) > 40
        assert word == pytest.approx(round(word), abs=1e-3)  # a whole pixel: a cell
        return
    # One: after "waffle." and not after "LT." or "P.", which end in capitals.
    assert [before for before, _ in wider] == ["."]
    assert wider[0][1] == pytest.approx(word * 4.0 / 3.0, abs=0.002)


def test_a_fenced_blocks_spaces_are_one_width_whatever_the_spacing(report: dict[str, Any]) -> None:
    assert len(report["fenced"]) == 6
    for name, spaces in report["fenced"].items():
        assert len(spaces) > 40, name
        assert len(_widths(spaces)) == 1, (name, sorted(_widths(spaces)))


def test_the_default_theme_is_laid_out_as_it_was(report: dict[str, Any]) -> None:
    # The library's default is what the theme's default means: nothing moved
    # for a host that named no spacing.
    assert report["default_is_extra_space_only"] == "EXTRA_SPACE_ONLY"
    assert report["styles"]["EXTRA_SPACE_ONLY"] == 0


def test_set_theme_changes_the_spacing_a_view_lays_out_with(report: dict[str, Any]) -> None:
    before, after = report["set_theme"]
    assert len(_widths(before)) == 2
    assert len(_widths(after)) == 1

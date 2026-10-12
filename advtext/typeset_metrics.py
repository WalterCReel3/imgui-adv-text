r"""
A face's line metrics for sizing a theme: the library's when it has fonts, the old reader's before.

Three things in the typeset layer need numbers from a font and no text set:
`Theme.at_pixel_height` (the em at which a face is a given height as Dear
ImGui means it, and the widest list marker), `advtext.ui.pages.face_metrics`
(the same, as a resolver a page hands on) and
`advtext.ui.typeset_diff_view.code_size` given a pixel height. Until
2026-10-12 all three asked `advtext.fontlib`, the reference core's font
reader, which opens the file with fontTools and reads its `GPOS` kerning to
answer three numbers of `hhea` (measured by pptmstr, the first host: 265 ms
for a document theme cold). imtypeset answers them itself since its commit
`74f5116` (`font_metrics`, `glyph_advance`), from the font it draws with.

## Who answers, and the order a host must follow

**The library answers when `advtext.typesetter.ready()` is true, and only
then.** Established by a run against imtypeset `03b5cd4`
(`.concerns/N-METRICS-scripts/order_probe.py`): `font_metrics` needs the
library's own context and a font added for the role; the library's context
cannot be made without a current Dear ImGui context
(`create_context: ImTypeset::CreateContext needs a current ImGui context`);
so it needs exactly what `typesetter.load_fonts()` does, and nothing less
will do. It needs no frame. So a host that wants the library's numbers:

1.  makes its Dear ImGui context (hello_imgui does, before
    `load_additional_fonts`);
2.  registers its own font files, if any (`advtext.register_font`);
3.  calls `advtext.load_fonts()` (in `load_additional_fonts`);
4.  THEN sizes its themes (`Theme.at_pixel_height`, `code_size`).

On that path nothing of the reference core is loaded: no `advtext.fontlib`,
no `advtext.style`, no fontTools (`tests/test_typeset_closure.py` holds it).
advtext cannot hide the order: making the library's context for the host
would mean making or borrowing a Dear ImGui context the host has not made.

**Before that, and without the library, the old reader answers**
(`advtext.style.fontlib_metrics`, `advtext.fontlib.em_size_for_pixel_height`,
imported when called): the same numbers at the old cost. That is the one
door to the reference core left in the typeset layer, and it is open only
while `typesetter.ready()` is false. It is kept, and a theme sized early is
not refused, because the callers need it: advtext's own app and its pages
build their themes before there is a window; a host may build a theme with
no library at all; and the whole of the suite without the library sizes
themes at pixel heights.

**The two agree**, which is what makes the order a matter of cost and not of
result: for every bundled face the em for a pixel height and the themes
built from it are equal by either route
(`.concerns/N-METRICS--builder--result.md` has the table;
`tests/test_typeset_metrics.py` holds it with the library).

## What the library's answer is, and is not

`LibraryMetrics` has the names of `advtext.fontmetrics.FontMetrics` that the
library can answer: `face`, `size`, `em`, `ascent`, `descent`, `x_height`,
`space_width`, `has` and `advance`, in the unit the size was given in (a
font key's size is in scaled points, so they are scaled points). It has no
`bbox` and no `kern`: the library does not hand out an ink box or a pair's
kern, and a caller that needs them is the reference core's
(`advtext.style.fontlib_metrics`). Asked, they raise `NotImplementedError`
and say so.

The numbers are the font file's, `hhea` ascent and descent, scaled and not
rounded. The library hands them over as C floats (24 bits), so they are
asked at one large em, `PROBE_EM`, at which a font of 1000, 1024 or 2048
units per em answers whole numbers exactly, and scaled here in doubles. A
font of some other units per em answers to seven digits.

**The library's font is the one `load_fonts` gave it.** A file registered
after that (`register_font`) is the old reader's at once and the library's
only after the next `load_fonts()`; register first.

**A role the library has no font for** (a face left out of
`load_fonts(faces)`, or one with no file) is a `MissingFontError`, the type
the old reader raises for a role with no file, with the library's own
sentence in it. The old reader is not asked instead: with the library ready
its fonts are what text is set in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from advtext import typesetter
from advtext.description import FACE_ROLES
from advtext.fontfiles import MissingFontError
from advtext.primitives import Face

if TYPE_CHECKING:  # pragma: no cover - for types only
    from advtext.fontmetrics import FontMetrics

__all__ = [
    "PROBE_EM",
    "LibraryMetrics",
    "em_size_for_pixel_height",
    "face_metrics",
    "library_answers",
    "library_metrics",
]

PROBE_EM = 512000.0
"""
The em, in pixels, every question is put to the library at.

512000 is 512 times 1000 and 250 times 2048, so a font of either units per
em (and of 1024, 2000, 4000 or 4096) has its metrics come back as whole
numbers that a C float holds exactly; the library takes an em up to
1,000,000. Only ratios to it are read.
"""


def library_answers() -> bool:
    """
    Whether the library is who answers now: `advtext.typesetter.ready()`.

    True once `typesetter.load_fonts()` has succeeded in the Dear ImGui
    context that is current. False without the library, before the fonts are
    loaded, and in any other context; the old reader answers then.
    """
    return typesetter.ready()


def _cannot(face: Face, exc: Exception) -> MissingFontError:
    """
    The library's refusal to measure a role, as the error the old reader raises for no file.
    """
    return MissingFontError(
        f"imtypeset cannot measure {face.value}: {exc}; give the role a font "
        "with advtext.typesetter.load_fonts()"
    )


def _line_metrics(face: Face) -> Any:
    """
    The library's `FontMetrics` for a role's font at `PROBE_EM`, or `MissingFontError`.
    """
    ts = typesetter.module()
    try:
        return ts.font_metrics(FACE_ROLES[face.name], PROBE_EM)
    except Exception as exc:  # noqa: BLE001 -- the library's own Error, whatever it is called
        raise _cannot(face, exc) from exc


def _advance(face: Face, codepoint: int) -> float:
    """
    One character's advance in a role's font at `PROBE_EM`, or `MissingFontError`.
    """
    ts = typesetter.module()
    try:
        return float(ts.glyph_advance(FACE_ROLES[face.name], PROBE_EM, int(codepoint)))
    except Exception as exc:  # noqa: BLE001 -- as `_line_metrics`
        raise _cannot(face, exc) from exc


class LibraryMetrics:
    """
    One face at one size, answered by imtypeset from the font it draws that role with.

    See the module docstring for what it has of `FontMetrics` and what it
    has not. Made by `library_metrics`; the library is asked once here, for
    the line metrics, and once per distinct character afterwards.
    """

    __slots__ = ("_advances", "_face", "_raw", "_scale", "_size")

    def __init__(self, face: Face, size: float) -> None:
        self._face = face
        self._size = float(size)
        self._scale = self._size / PROBE_EM
        self._raw = _line_metrics(face)
        self._advances: dict[int, float] = {}

    @property
    def face(self) -> Face:
        return self._face

    @property
    def size(self) -> float:
        return self._size

    @property
    def em(self) -> float:
        return self._size

    @property
    def ascent(self) -> float:
        return float(self._raw.ascent) * self._scale

    @property
    def descent(self) -> float:
        return float(self._raw.descent) * self._scale

    @property
    def x_height(self) -> float:
        return float(self._raw.x_height) * self._scale

    @property
    def space_width(self) -> float:
        return float(self._raw.space_advance) * self._scale

    def has(self, codepoint: int) -> bool:
        ts = typesetter.module()
        try:
            return bool(ts.face_has_glyph(FACE_ROLES[self._face.name], int(codepoint)))
        except Exception as exc:  # noqa: BLE001 -- as `_line_metrics`
            raise _cannot(self._face, exc) from exc

    def advance(self, codepoint: int) -> float:
        """
        How far the pen moves after one character, kerning apart.

        The missing glyph's advance for a character the font lacks (`has`).
        """
        raw = self._advances.get(codepoint)
        if raw is None:
            raw = _advance(self._face, codepoint)
            self._advances[codepoint] = raw
        return raw * self._scale

    def bbox(self, codepoint: int) -> Any:
        raise NotImplementedError(
            "imtypeset does not answer a glyph's ink box; advtext.style.fontlib_metrics does"
        )

    def kern(self, codepoint: int, following: int) -> float:
        raise NotImplementedError(
            "imtypeset does not answer a pair's kern; advtext.style.fontlib_metrics does"
        )


def library_metrics(key: str) -> LibraryMetrics:
    """
    A font key (`advtext.theme.font_key`) measured by the library, whoever would answer by default.

    `MissingFontError` when the library cannot be asked (not `ready()`: the
    sentence is `typesetter.why_not_ready()`) or has no font for the role.
    """
    if not typesetter.ready():
        raise MissingFontError(f"imtypeset cannot be asked: {typesetter.why_not_ready()}")
    from advtext.theme import parse_font_key

    spec = parse_font_key(key)
    return LibraryMetrics(spec.face, float(spec.size))


def face_metrics(key: str) -> FontMetrics:
    """
    The resolver a theme is sized with by default: the library's when it is ready.

    What `Theme.at_pixel_height` asks when it is given no resolver, and what
    `advtext.ui.pages.face_metrics` is. With the library ready the answer is
    a `LibraryMetrics` and nothing of the reference core is loaded. Otherwise
    it is `advtext.style.fontlib_metrics`, read from that module at the call,
    so that a caller who replaces the name there is still the one asked.
    """
    if typesetter.ready():
        return library_metrics(key)
    from advtext import style

    return style.fontlib_metrics(key)


def em_size_for_pixel_height(face: Face, pixel_height: float) -> float:
    """
    The em size at which `face` comes out `pixel_height` tall, as Dear ImGui means it.

    Dear ImGui sizes a font by its height, the `hhea` ascent plus descent;
    advtext and imtypeset size a face by its em. A host whose UI font is
    "16" passes 16 here and builds its theme at the answer. The ratio is the
    face's own: a 16 px height is an em of 13.653 px in the bundled Roboto
    and 15.253 px in Inconsolata. The answer is in the unit `pixel_height`
    was given in and is not rounded.

    Answered by the library when it is ready (its `font_metrics`: the em for
    a height `h` is `h * em_size / font_size`), and by
    `advtext.fontlib.em_size_for_pixel_height` otherwise, imported then. The
    module docstring has the order a host follows to get the first.
    `face` that is no `Face` is a `TypeError`.
    """
    if not isinstance(face, Face):
        raise TypeError(
            f"em_size_for_pixel_height() takes an advtext Face, not {type(face).__name__}"
        )
    if typesetter.ready():
        raw = _line_metrics(face)
        extent = float(raw.font_size)
        if extent <= 0:
            return pixel_height
        return pixel_height * float(raw.em_size) / extent
    from advtext import fontlib

    return fontlib.em_size_for_pixel_height(face, pixel_height)

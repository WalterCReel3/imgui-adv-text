r"""
Claims about the SVG backend, with the geometry computed by hand rather than read back.

The expectations here are derived from two numbers that are properties of the
font file and are asserted separately, so a font swap produces one clear failure
rather than a dozen confusing ones: Roboto's `unitsPerEm` is 2048, and the ink
of its capital H reaches 1456 font units above the baseline and 0 below. Both
were read with fontTools; neither was copied out of a rendered document.

**The y-flip test is the reason this file exists.** Outlines are in font units
with y up and SVG has y down, so a missing minus sign produces output that looks
entirely plausible and is upside down about the baseline. It is asserted
explicitly -- the glyph's own ink top is pushed through the emitted transform and
must land *above* the baseline the shipper computed.

Font-dependent tests take the `bundled_fonts` fixture so they skip rather than
fail on a machine without imgui-bundle's assets.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from advtext.backends.svg import Palette, glyph_outline, render
from advtext.fontmetrics import Face
from advtext.selection import Rect
from advtext.shipout import DrawCmd, Glyph, Line, RuleRect, SetGlue
from advtext.style import font_key
from advtext.units import Scaled, sp_from_pt

SVG = "{http://www.w3.org/2000/svg}"
PT = sp_from_pt(1.0)

# A size chosen so the scale factor is exact: 10pt is 655360sp, and 655360/2048
# is 320 with nothing after the point. That removes float formatting from every
# assertion about position.
SIZE = sp_from_pt(10.0)
UNITS_PER_EM = 2048
SCALE = SIZE / UNITS_PER_EM

# Ink extent of Roboto's capital H, in font units, read with fontTools.
H_INK_TOP = 1456
H_INK_BOTTOM = 0

PROSE = font_key(Face.PROSE, SIZE)


def _parse(document: str) -> ElementTree.Element:
    """
    Parse a rendered document, which is also the "it is well formed" assertion.
    """
    return ElementTree.fromstring(document)


def _transform_of(element: ElementTree.Element) -> tuple[float, float, float, float]:
    """
    Pull `translate(tx ty) scale(sx sy)` apart into its four numbers.
    """
    raw = element.get("transform")
    assert raw is not None, "a glyph path must carry a transform"
    match = re.fullmatch(r"translate\((\S+) (\S+)\) scale\((\S+) (\S+)\)", raw)
    assert match is not None, f"unexpected transform syntax: {raw!r}"
    return tuple(float(group) for group in match.groups())  # type: ignore[return-value]


def _apply(element: ElementTree.Element, font_x: float, font_y: float) -> tuple[float, float]:
    """
    Where a point of the glyph's outline ends up in document coordinates.
    """
    translate_x, translate_y, scale_x, scale_y = _transform_of(element)
    return translate_x + scale_x * font_x, translate_y + scale_y * font_y


def _paths(document: str) -> list[ElementTree.Element]:
    """
    Every glyph path in a rendered document, in document order.
    """
    return list(_parse(document).iter(f"{SVG}path"))


def _rects(document: str) -> list[ElementTree.Element]:
    """
    Every rectangle in a rendered document, in document order.
    """
    return list(_parse(document).iter(f"{SVG}rect"))


def _glyph(codepoint: int, x: Scaled = 0, y: Scaled = 0, index: int = 0) -> Glyph:
    """
    A placed glyph in the prose face at the fixed test size.
    """
    return Glyph(font=PROSE, codepoint=codepoint, x=x, y=y, index=index)


def _line(width: Scaled = 100 * PT, y: Scaled = 20 * PT) -> Line:
    """
    A one-line box, as ship-out emits it before the material it covers.
    """
    return Line(x=0, y=y, width=width, height=8 * PT, depth=2 * PT, start=0, end=1)


# --------------------------------------------------------------------------
# The document itself
# --------------------------------------------------------------------------


def test_an_empty_command_list_still_produces_a_well_formed_document() -> None:
    root = _parse(render([], 100 * PT, 50 * PT))
    assert root.tag == f"{SVG}svg"


def test_the_size_is_stated_in_points_and_the_coordinate_system_in_scaled_points() -> None:
    # Points on the outside so the file opens at its true physical size; scaled
    # points on the inside so every coordinate is the integer ship-out produced
    # and nothing is converted on the way out.
    root = _parse(render([], 100 * PT, 50 * PT))
    assert root.get("width") == "100pt"
    assert root.get("height") == "50pt"
    assert root.get("viewBox") == f"0 0 {100 * PT} {50 * PT}"


def test_a_background_rectangle_covers_the_page_and_can_be_suppressed() -> None:
    painted = _rects(render([], 100 * PT, 50 * PT))
    assert len(painted) == 1
    assert painted[0].get("width") == str(100 * PT)
    assert painted[0].get("fill") == "#ffffff"

    bare = _rects(render([], 100 * PT, 50 * PT, palette=Palette(background=None)))
    assert bare == []


# --------------------------------------------------------------------------
# Glyphs: outlines, placement, and the flip
# --------------------------------------------------------------------------


def test_roboto_has_the_units_per_em_every_other_expectation_here_is_derived_from(
    bundled_fonts: Path,
) -> None:
    # Asserted on its own so that swapping the prose face produces one obvious
    # failure rather than a page of arithmetic that no longer holds.
    from fontTools.ttLib import TTFont

    from advtext import fontlib

    font = TTFont(fontlib.font_file(Face.PROSE), lazy=False)
    try:
        assert font["head"].unitsPerEm == UNITS_PER_EM
    finally:
        # `filterwarnings = ["error"]` turns a leaked handle into a failure, and
        # rightly so -- this test would otherwise fail somewhere else entirely.
        font.close()


def test_a_glyph_is_a_path_of_real_outline_data_and_never_a_text_element(
    bundled_fonts: Path,
) -> None:
    # `<text>` would hand positioning back to the viewer's own font machinery and
    # the picture would stop being evidence about our layout.
    document = render([_glyph(ord("H"))], 100 * PT, 50 * PT)
    assert "<text" not in document
    paths = _paths(document)
    assert len(paths) == 1
    data = paths[0].get("d")
    assert data and data.startswith("M")


def test_a_glyphs_transform_puts_its_origin_exactly_where_ship_out_placed_it(
    bundled_fonts: Path,
) -> None:
    placed = _glyph(ord("H"), x=17 * PT, y=33 * PT)
    translate_x, translate_y, _, _ = _transform_of(_paths(render([placed], 100 * PT, 50 * PT))[0])
    assert (translate_x, translate_y) == (float(placed.x), float(placed.y))


def test_the_glyph_scale_is_the_size_divided_by_units_per_em(bundled_fonts: Path) -> None:
    _, _, scale_x, scale_y = _transform_of(_paths(render([_glyph(ord("H"))], 100 * PT, 50 * PT))[0])
    assert scale_x == SCALE == 320.0
    # The y scale is the same magnitude with the sign inverted. That minus is the
    # entire coordinate-system conversion.
    assert scale_y == -SCALE


def test_a_glyph_with_positive_ascent_renders_above_its_baseline(bundled_fonts: Path) -> None:
    # The sign-error test. Font units go up from the baseline, SVG goes down, so
    # ink at +1456 font units must end up at a *smaller* y than the baseline.
    # Getting this wrong produces a document that looks fine until you notice
    # every letter is reflected about its own baseline.
    baseline = 33 * PT
    path = _paths(render([_glyph(ord("H"), x=0, y=baseline)], 100 * PT, 50 * PT))[0]

    _, top = _apply(path, 0.0, float(H_INK_TOP))
    _, bottom = _apply(path, 0.0, float(H_INK_BOTTOM))

    assert top < baseline
    assert top == baseline - H_INK_TOP * SCALE
    assert bottom == baseline


def test_the_outline_cache_returns_the_very_same_string_for_a_repeated_glyph(
    bundled_fonts: Path,
) -> None:
    # A page of prose repeats a few dozen glyphs thousands of times; re-running
    # the pen per occurrence is pure waste. Identity rather than equality,
    # because equality would also pass for an uncached implementation.
    first = glyph_outline(Face.PROSE, "H")
    second = glyph_outline(Face.PROSE, "H")
    assert first is second
    assert first != glyph_outline(Face.PROSE, "O")


def test_a_glyph_the_face_draws_as_nothing_contributes_no_path(bundled_fonts: Path) -> None:
    # A space has an advance and no contours. An empty `<path d="">` would be
    # noise in every artifact and would make the path count meaningless.
    assert glyph_outline(Face.PROSE, "space") == ""
    assert _paths(render([_glyph(ord(" "))], 100 * PT, 50 * PT)) == []


def test_the_display_sigma_is_reachable_by_the_synthetic_codepoint_and_is_a_different_glyph(
    bundled_fonts: Path,
) -> None:
    # The sigma litmus test's central claim, checked at the point where it could
    # quietly stop being true: `summation.v1` has no codepoint in the font, so
    # if the outline route went through a cmap instead of through
    # `fontlib.glyph_name` the display operator would silently become the body
    # one scaled up -- which is exactly the dishonest version decisions.md rules
    # out, and it would look almost right.
    from advtext import fontlib

    body = glyph_outline(Face.MATH, "summation")
    display = glyph_outline(Face.MATH, "summation.v1")
    assert body and display
    assert body != display

    variants = fontlib.math_metrics(float(SIZE)).vertical_variants(0x2211)
    assert len(variants) >= 2
    assert fontlib.glyph_name(Face.MATH, variants[-1].codepoint) == "summation.v1"


# --------------------------------------------------------------------------
# Rules and selection
# --------------------------------------------------------------------------


def test_a_rule_is_a_filled_rectangle_whose_y_is_its_top_edge() -> None:
    # Unlike a glyph, a rule has no baseline: §624 resolves it to a device
    # rectangle before drawing and `y` is already the top.
    rule = RuleRect(x=5 * PT, y=9 * PT, width=60 * PT, height=PT // 2)
    painted = _rects(render([rule], 100 * PT, 50 * PT, palette=Palette(background=None)))
    assert len(painted) == 1
    assert painted[0].get("x") == str(5 * PT)
    assert painted[0].get("y") == str(9 * PT)
    assert painted[0].get("height") == str(PT // 2)
    assert painted[0].get("fill-opacity") is None


def test_selection_highlights_are_drawn_before_the_glyphs_so_the_text_stays_on_top(
    bundled_fonts: Path,
) -> None:
    document = render(
        [_glyph(ord("H"))],
        100 * PT,
        50 * PT,
        highlights=[Rect(x=0, y=0, width=20 * PT, height=12 * PT)],
        palette=Palette(background=None),
    )
    children = list(_parse(document))
    assert children[0].tag == f"{SVG}rect"
    assert children[0].get("fill-opacity") == "0.3"
    assert children[-1].tag == f"{SVG}path"


# --------------------------------------------------------------------------
# The debug overlay
# --------------------------------------------------------------------------


def test_debug_mode_outlines_every_line_box_and_plain_mode_draws_none() -> None:
    cmds: list[DrawCmd] = [_line()]
    plain = _parse(render(cmds, 100 * PT, 50 * PT, palette=Palette(background=None)))
    assert list(plain) == []

    overlaid = _parse(render(cmds, 100 * PT, 50 * PT, debug=True, palette=Palette(background=None)))
    boxes = [element for element in overlaid.iter(f"{SVG}rect") if element.get("fill") == "none"]
    assert len(boxes) == 1
    # The box spans [y - height, y + depth) because y is the baseline.
    assert boxes[0].get("y") == str(20 * PT - 8 * PT)
    assert boxes[0].get("height") == str(10 * PT)
    assert len(list(overlaid.iter(f"{SVG}line"))) == 1


def test_the_debug_baseline_sits_on_the_baseline_and_not_on_the_box_edge() -> None:
    overlaid = _parse(
        render([_line()], 100 * PT, 50 * PT, debug=True, palette=Palette(background=None))
    )
    baseline = next(overlaid.iter(f"{SVG}line"))
    assert baseline.get("y1") == baseline.get("y2") == str(20 * PT)


def test_debug_mode_colours_a_stretched_space_differently_from_a_shrunk_one() -> None:
    # The overlay's whole purpose: justification becomes something you can see
    # rather than something you take on trust.
    stretched = SetGlue(
        x=0, y=20 * PT, width=9 * PT, natural=6 * PT, height=8 * PT, depth=2 * PT, index=0
    )
    shrunk = SetGlue(
        x=0, y=20 * PT, width=4 * PT, natural=6 * PT, height=8 * PT, depth=2 * PT, index=1
    )
    natural = SetGlue(
        x=0, y=20 * PT, width=6 * PT, natural=6 * PT, height=8 * PT, depth=2 * PT, index=2
    )

    palette = Palette(background=None)
    fills = [
        _rects(render([glue], 100 * PT, 50 * PT, debug=True, palette=palette))[0].get("fill")
        for glue in (stretched, shrunk, natural)
    ]
    assert fills == [palette.debug_stretched, palette.debug_shrunk, palette.debug_natural]
    assert len(set(fills)) == 3


def test_the_natural_width_of_a_stretched_space_is_marked_so_the_stretch_is_a_distance() -> None:
    glue = SetGlue(
        x=10 * PT, y=20 * PT, width=9 * PT, natural=6 * PT, height=8 * PT, depth=2 * PT, index=0
    )
    overlaid = _parse(
        render([glue], 100 * PT, 50 * PT, debug=True, palette=Palette(background=None))
    )
    tick = next(overlaid.iter(f"{SVG}line"))
    assert tick.get("x1") == tick.get("x2") == str(16 * PT)


def test_a_debug_render_and_a_plain_render_agree_glyph_for_glyph(bundled_fonts: Path) -> None:
    # The overlay adds and never alters, so the two documents can be diffed
    # against each other and any difference in the text is a real one.
    cmds: list[DrawCmd] = [_line(), _glyph(ord("H"), x=3 * PT, y=20 * PT)]
    plain = [
        (path.get("d"), path.get("transform")) for path in _paths(render(cmds, 100 * PT, 50 * PT))
    ]
    debugged = [
        (path.get("d"), path.get("transform"))
        for path in _paths(render(cmds, 100 * PT, 50 * PT, debug=True))
    ]
    assert plain == debugged
    assert plain


def test_the_renderer_refuses_nothing_and_places_every_command_it_is_given(
    bundled_fonts: Path,
) -> None:
    cmds: list[DrawCmd] = [
        _line(),
        _glyph(ord("H"), x=0, y=20 * PT, index=0),
        SetGlue(
            x=8 * PT, y=20 * PT, width=6 * PT, natural=6 * PT, height=8 * PT, depth=2 * PT, index=1
        ),
        _glyph(ord("O"), x=14 * PT, y=20 * PT, index=2),
        RuleRect(x=0, y=25 * PT, width=100 * PT, height=PT // 2),
    ]
    document = render(cmds, 100 * PT, 50 * PT, palette=Palette(background=None))
    assert len(_paths(document)) == 2
    assert len(_rects(document)) == 1


@pytest.mark.parametrize("codepoint", [ord("A"), ord("g"), ord("Q"), ord("1")])
def test_every_ordinary_glyph_has_a_non_empty_outline(bundled_fonts: Path, codepoint: int) -> None:
    paths = _paths(render([_glyph(codepoint)], 100 * PT, 50 * PT))
    assert len(paths) == 1
    assert (paths[0].get("d") or "").startswith("M")

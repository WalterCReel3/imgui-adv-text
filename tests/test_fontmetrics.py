"""
The metrics layer, checked against real measured values rather than against itself.

Every assertion here is a number that came out of a font file, so a font swap or a
fontTools upgrade that changes what we read fails loudly instead of quietly changing
every layout downstream. That is the point: nothing else in the tree can tell the
difference between a correct advance and a plausible one.

Two claims get their own tests because nothing else in the project would catch them
breaking. The summation variant chain is what makes a real display-size Σ possible
(`docs/decisions.md`), and if a future font lost it the math task would silently fall
back to a body-size glyph that still renders. And Inconsolata's kerning is zero
because the face carries no `kern` feature at all, which is a different fact from a
stubbed implementation returning zero; the test asserts the absence, not the zero.

Every test that opens a font goes through the `bundled_fonts` fixture, which skips
rather than fails when the bundle is absent -- a missing font directory is a statement
about the environment and not about this code.

Deliberately not here: anything that opens an ImGui context. No display exists.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from imscribe.fontlib import (
    SYNTHETIC_FIRST,
    SYNTHETIC_LAST,
    MathFaceMetrics,
    MissingFontError,
    _face_data,
    font_directory,
    font_file,
    glyph_name,
    glyph_set,
    math_metrics,
    metrics,
)
from imscribe.fontmetrics import Face

# Latin Modern Math is drawn on a 1000-unit em, so asking for a 1000.0 face makes
# every scaled value equal to the raw font-unit integer and the assertions below
# readable as the numbers actually in the file.
DESIGN_SIZE = 1000.0

# A CJK ideograph. None of the bundled faces map it, which is what makes it useful.
UNMAPPED = 0x4E00


def test_font_directory_is_resolved_from_the_installed_bundle_not_a_hardcoded_path(
    bundled_fonts: Path,
) -> None:
    assert font_directory() == bundled_fonts


def test_every_named_face_maps_to_a_file_the_bundle_actually_ships(
    bundled_fonts: Path,
) -> None:
    for face in Face:
        assert font_file(face).is_file()


def test_a_face_is_opened_once_and_shared_by_every_size_of_it(bundled_fonts: Path) -> None:
    assert _face_data(Face.PROSE) is _face_data(Face.PROSE)
    metrics(Face.PROSE, 12.0)
    metrics(Face.PROSE, 48.0)
    assert _face_data(Face.PROSE) is _face_data(Face.PROSE)


def test_identical_arguments_return_the_identical_metrics_object(bundled_fonts: Path) -> None:
    assert metrics(Face.PROSE, 16.0) is metrics(Face.PROSE, 16.0)
    assert metrics(Face.PROSE, 16.0) is not metrics(Face.PROSE, 17.0)
    assert metrics(Face.MATH, 16.0) is math_metrics(16.0)


def test_a_wide_glyph_advances_further_than_a_narrow_one_in_a_proportional_face(
    bundled_fonts: Path,
) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.advance(ord("W")) > 850.0
    assert prose.advance(ord("i")) < 300.0


def test_a_monospaced_face_gives_every_glyph_the_same_advance(bundled_fonts: Path) -> None:
    code = metrics(Face.CODE, 100.0)
    widths = {code.advance(ord(ch)) for ch in "Wim.|"}
    assert widths == {50.0}


def test_advances_scale_linearly_with_the_requested_size(bundled_fonts: Path) -> None:
    small = metrics(Face.PROSE, 10.0).advance(ord("W"))
    large = metrics(Face.PROSE, 30.0).advance(ord("W"))
    assert large == pytest.approx(3.0 * small)


def test_a_codepoint_the_face_does_not_map_is_reported_missing_and_still_has_a_width(
    bundled_fonts: Path,
) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert not prose.has(UNMAPPED)
    assert prose.has(ord("W"))
    # .notdef, not a zero-width hole: text that silently vanishes reads as a layout
    # bug, and a visible box reads as the missing glyph it is.
    assert prose.advance(UNMAPPED) > 0.0


def test_depth_is_measured_below_the_baseline_and_only_a_descender_has_any(
    bundled_fonts: Path,
) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.bbox(ord("g")).depth > 150.0
    assert prose.bbox(ord("x")).depth == pytest.approx(0.0)


def test_the_height_of_a_lowercase_x_is_the_faces_x_height(bundled_fonts: Path) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.bbox(ord("x")).height == pytest.approx(prose.x_height, abs=1.0)


def test_ascent_and_descent_are_both_positive_and_straddle_the_baseline(
    bundled_fonts: Path,
) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.ascent > 0.0
    # Positive *down*, matching TeX's depth, so a sign error here is not silent.
    assert prose.descent > 0.0
    assert prose.ascent > prose.descent


def test_kerning_pulls_the_classic_problem_pairs_together(bundled_fonts: Path) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.kern(ord("T"), ord("o")) < -40.0
    assert prose.kern(ord("A"), ord("V")) < -20.0
    assert prose.kern(ord("W"), ord("a")) < -5.0


def test_a_pair_the_font_chose_not_to_kern_is_zero_rather_than_absent(
    bundled_fonts: Path,
) -> None:
    prose = metrics(Face.PROSE, DESIGN_SIZE)
    assert prose.kern(ord("n"), ord("n")) == 0.0


def test_the_monospaced_face_reports_zero_because_it_ships_no_kern_feature(
    bundled_fonts: Path,
) -> None:
    # Asserting the absence, not the zero. A stubbed extractor would also return
    # 0.0 here, and the two are different states of the project.
    assert _face_data(Face.CODE).kern_subtables == ()
    assert metrics(Face.CODE, DESIGN_SIZE).kern(ord("T"), ord("o")) == 0.0


def test_kerns_scale_with_size_like_every_other_length(bundled_fonts: Path) -> None:
    at_ten = metrics(Face.PROSE, 10.0).kern(ord("T"), ord("o"))
    at_forty = metrics(Face.PROSE, 40.0).kern(ord("T"), ord("o"))
    assert at_forty == pytest.approx(4.0 * at_ten)


def test_the_summation_variant_chain_is_present_and_ascends(bundled_fonts: Path) -> None:
    chain = math_metrics(DESIGN_SIZE).vertical_variants(0x2211)
    assert [variant.name for variant in chain] == ["summation", "summation.v1"]
    assert chain[1].extent > chain[0].extent
    # The base entry of an OpenType variant chain is the glyph itself, which is what
    # makes "one step along the chain" (tex.web §749) a well-defined instruction.
    assert chain[0].name == "summation"


def test_a_glyph_with_no_variant_chain_reports_an_empty_one(bundled_fonts: Path) -> None:
    assert math_metrics(DESIGN_SIZE).vertical_variants(ord("x")) == ()


def test_display_operator_min_height_selects_exactly_the_second_summation_variant(
    bundled_fonts: Path,
) -> None:
    # OpenType says "the first variant at least this tall"; TeX says "one step along
    # the chain" (§749). This asserts the two agree for the litmus formula's operator,
    # which is why the math task may implement either rule and get the same Sigma.
    math = math_metrics(DESIGN_SIZE)
    chain = math.vertical_variants(0x2211)
    minimum = math.math.display_operator_min_height
    assert chain[0].extent < minimum <= chain[1].extent


def test_the_unencoded_display_summation_is_given_a_codepoint_it_can_be_named_by(
    bundled_fonts: Path,
) -> None:
    # latinmodern-math.otf does not encode summation.v1, and CharNode, Glyph and
    # every FontMetrics method name a glyph by codepoint and nothing else. Without
    # a minted one the display-style sigma is unexpressible and the litmus test
    # falls back to scaling the body glyph, which docs/decisions.md rules out.
    chain = math_metrics(DESIGN_SIZE).vertical_variants(0x2211)
    base, display = chain[0], chain[1]
    assert base.codepoint == 0x2211
    assert display.codepoint != base.codepoint
    assert SYNTHETIC_LAST <= display.codepoint <= SYNTHETIC_FIRST


def test_the_minted_codepoint_really_reaches_the_taller_glyph(bundled_fonts: Path) -> None:
    # The point of minting it: measuring through the ordinary codepoint path has
    # to land on summation.v1 and not on summation.
    math = math_metrics(DESIGN_SIZE)
    base, display = math.vertical_variants(0x2211)
    box = math.bbox(display.codepoint)
    assert math.has(display.codepoint)
    assert box.height + box.depth == pytest.approx(display.extent, abs=1.0)
    assert math.advance(display.codepoint) > math.advance(base.codepoint)


def test_a_minted_codepoint_resolves_back_to_the_fonts_own_glyph_name(
    bundled_fonts: Path,
) -> None:
    # The SVG backend pulls an outline by name, and a synthetic codepoint has no
    # other route to one.
    display = math_metrics(DESIGN_SIZE).vertical_variants(0x2211)[1]
    assert glyph_name(Face.MATH, display.codepoint) == "summation.v1"
    assert glyph_name(Face.MATH, 0x2211) == "summation"


def test_minting_is_deterministic_so_a_golden_artifact_stays_reproducible(
    bundled_fonts: Path,
) -> None:
    first = math_metrics(DESIGN_SIZE).vertical_variants(0x2211)[1].codepoint
    second = math_metrics(10.0).vertical_variants(0x2211)[1].codepoint
    assert first == second


def test_a_variant_the_font_does_encode_keeps_its_real_codepoint(bundled_fonts: Path) -> None:
    # Only the unencoded glyphs are minted; the base of every chain is a real
    # character and must stay one.
    math = math_metrics(DESIGN_SIZE)
    for codepoint in (0x2211, 0x222B, 0x220F):
        chain = math.vertical_variants(codepoint)
        if chain:
            assert chain[0].codepoint == codepoint


def test_the_math_axis_sits_above_the_baseline_and_below_the_math_x_height(
    bundled_fonts: Path,
) -> None:
    params = math_metrics(DESIGN_SIZE).math
    assert 0.0 < params.axis_height < params.math_x_height


def test_italic_correction_is_real_for_a_leaning_glyph_and_zero_for_an_upright_one(
    bundled_fonts: Path,
) -> None:
    math = math_metrics(DESIGN_SIZE)
    # An integral leans, so a following subscript must be pushed right; a summation
    # does not, and §749's delta is 0 for it.
    assert math.italic_correction(0x222B) > 100.0
    assert math.italic_correction(0x2211) == 0.0


def test_the_tex_parameters_carry_the_fonts_own_numbers_where_opentype_has_a_field(
    bundled_fonts: Path,
) -> None:
    # Read straight out of latinmodern-math.otf's MathConstants at its 1000-unit em.
    # If any of these move, the mapping table in imscribe/fontlib.py is out of date.
    params = math_metrics(DESIGN_SIZE).math
    assert params.axis_height == 250.0
    assert params.default_rule_thickness == 40.0
    assert params.num1 == 677.0
    assert params.num2 == 394.0
    assert params.num3 == 444.0
    assert params.denom1 == 686.0
    assert params.denom2 == 345.0
    assert params.sup3 == 289.0
    assert params.sup_drop == 250.0
    assert params.sub_drop == 200.0
    assert params.big_op_spacing1 == 200.0
    assert params.big_op_spacing2 == 167.0
    assert params.big_op_spacing3 == 111.0
    assert params.big_op_spacing4 == 600.0


def test_the_two_parameters_opentype_folds_into_one_field_come_back_equal(
    bundled_fonts: Path,
) -> None:
    # Documented in imscribe/fontlib.py: OpenType has one SuperscriptShiftUp where TeX
    # has sup1 and sup2, and one SubscriptShiftDown where TeX has sub1 and sub2. A
    # caller wanting TeX's split replaces the field rather than re-deriving it.
    params = math_metrics(DESIGN_SIZE).math
    assert params.sup1 == params.sup2
    assert params.sub1 == params.sub2


def test_the_parameters_with_no_opentype_counterpart_are_the_documented_em_fractions(
    bundled_fonts: Path,
) -> None:
    params = math_metrics(DESIGN_SIZE).math
    assert params.delim1 == 2.4 * DESIGN_SIZE
    assert params.delim2 == 1.0 * DESIGN_SIZE
    assert params.big_op_spacing5 == 0.1 * DESIGN_SIZE
    assert params.math_quad == DESIGN_SIZE


def test_the_script_scales_are_the_fonts_percentages_not_plain_texs_conventions(
    bundled_fonts: Path,
) -> None:
    params = math_metrics(DESIGN_SIZE).math
    assert params.script_scale == 0.7
    assert params.script_script_scale == 0.5


def test_math_parameters_scale_with_size_like_every_other_length(
    bundled_fonts: Path,
) -> None:
    assert math_metrics(20.0).math.axis_height == pytest.approx(
        2.0 * math_metrics(10.0).math.axis_height
    )


def test_asking_a_prose_face_for_math_parameters_fails_loudly(bundled_fonts: Path) -> None:
    # Roboto has no MATH table, and every parameter would have to be invented. The
    # type system stops this statically; this pins the runtime behaviour too.
    with pytest.raises(MissingFontError, match="no MATH table"):
        MathFaceMetrics(_face_data(Face.PROSE), 10.0)


# --------------------------------------------------------------------------------
# Glyph outlines, and the file handle behind them
#
# `fontlib` parses each face once and closes the file before `_face_data` returns.
# Two things have to hold for that to be safe, and neither is visible in a metrics
# number: outlines must still draw from memory after the close, and the process must
# end without a `ResourceWarning`. Both are asserted here because both would
# otherwise be discovered by a future test failing for an unrelated reason --
# `pyproject.toml` sets `filterwarnings = ["error"]`, and a leaked descriptor
# surfaces as a failure in whichever test happened to trigger the open.
# --------------------------------------------------------------------------------


def test_a_faces_glyph_set_and_em_size_come_from_the_one_parse(bundled_fonts: Path) -> None:
    glyphs, units_per_em = glyph_set(Face.PROSE)
    assert glyphs is _face_data(Face.PROSE).glyph_set
    assert units_per_em == _face_data(Face.PROSE).units_per_em
    assert glyph_name(Face.PROSE, ord("A")) in glyphs


def test_the_em_size_reported_with_a_glyph_set_is_the_faces_own_design_grid(
    bundled_fonts: Path,
) -> None:
    # Latin Modern Math is drawn on a 1000-unit em and Roboto on a 2048-unit one, so
    # a single hard-coded divisor in a renderer would be wrong for one of them.
    assert glyph_set(Face.MATH)[1] == 1000
    assert glyph_set(Face.PROSE)[1] == 2048


def test_a_truetype_glyf_outline_still_draws_after_the_font_file_is_closed(
    bundled_fonts: Path,
) -> None:
    from imscribe.backends.svg import glyph_outline

    path = glyph_outline(Face.PROSE, glyph_name(Face.PROSE, ord("A")))
    assert path.startswith("M")
    assert len(path) > 20


def test_a_cff_outline_still_draws_after_the_font_file_is_closed(bundled_fonts: Path) -> None:
    # Latin Modern Math is CFF, not glyf, and its charstrings are decompiled lazily.
    # They decompile from the table's own bytes rather than from the file, which is
    # what makes closing early safe -- a fontTools implementation fact, so it is
    # pinned here rather than assumed.
    from imscribe.backends.svg import glyph_outline

    path = glyph_outline(Face.MATH, glyph_name(Face.MATH, 0x2211))
    assert path.startswith("M")
    assert len(path) > 20


def test_the_display_size_summation_variant_draws_a_different_outline_from_the_body_one(
    bundled_fonts: Path,
) -> None:
    # The variant has no codepoint of its own, so it reaches an outline only through
    # the synthetic codepoint and `glyph_name`. If that route broke, the display sigma
    # would silently become the body sigma and still render.
    from imscribe.backends.svg import glyph_outline

    variants = math_metrics(DESIGN_SIZE).vertical_variants(0x2211)
    biggest = glyph_name(Face.MATH, variants[-1].codepoint)
    assert biggest == "summation.v1"
    assert glyph_outline(Face.MATH, biggest) != glyph_outline(Face.MATH, "summation")


def test_a_composite_glyph_resolves_its_components_after_the_font_file_is_closed(
    bundled_fonts: Path,
) -> None:
    # A composite references other glyphs by index, so drawing one exercises a lookup
    # back into the glyph set that a half-loaded font would fail.
    from imscribe.backends.svg import glyph_outline

    accented = glyph_outline(
        Face.PROSE, glyph_name(Face.PROSE, ord("\N{LATIN SMALL LETTER E WITH ACUTE}"))
    )
    plain = glyph_outline(Face.PROSE, glyph_name(Face.PROSE, ord("e")))
    assert accented.startswith("M")
    assert len(accented) > len(plain)


def test_reading_metrics_and_outlines_leaves_no_unclosed_file_at_interpreter_exit(
    bundled_fonts: Path,
) -> None:
    # The warning this guards against fires from the file object's finaliser during
    # shutdown, after pytest has stopped converting warnings to errors -- so it cannot
    # be caught in-process and a subprocess is the only honest check.
    source = textwrap.dedent("""
        from imscribe import fontlib
        from imscribe.backends.svg import glyph_outline
        from imscribe.fontmetrics import Face

        for face in Face:
            m = fontlib.metrics(face, 16.0)
            m.advance(ord("A"))
            m.bbox(ord("A"))
            m.kern(ord("T"), ord("o"))
            glyph_outline(face, fontlib.glyph_name(face, ord("A")))
        """)
    result = subprocess.run(
        [sys.executable, "-W", "error::ResourceWarning", "-c", source],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


# -- the radical constants and the delimiter chains (second build) ---------


def test_the_radical_constants_are_texs_own_formulas_evaluated(bundled_fonts: Path) -> None:
    # `make_radical` (docs/tex.web line 14476) computes its clearance from the rule
    # thickness and the x-height; OpenType states the results. For this font they
    # are the same numbers, which is what lets `imscribe.math.mlist` read the font's
    # fields and still be following TeX. If a font swap breaks this, the radical's
    # clearance has silently stopped being TeX's.
    math = math_metrics(DESIGN_SIZE)
    params = math.math
    thickness = int(params.default_rule_thickness)
    assert params.radical_rule_thickness == 40.0 == params.default_rule_thickness
    assert params.radical_vertical_gap == 50.0 == thickness + thickness // 4
    assert params.radical_display_style_vertical_gap == 148.0
    assert round(thickness + abs(params.math_x_height) / 4) == 148


def test_the_surd_chain_holds_five_and_only_the_first_keeps_the_tfm_convention(
    bundled_fonts: Path,
) -> None:
    # TeX assumes a surd's *height* is the thickness of its rule. The base glyph
    # obliges; the four larger ones straddle the axis like any delimiter, which is
    # why the radical is hung from the top of its ink and not from its baseline.
    math = math_metrics(DESIGN_SIZE)
    chain = math.vertical_variants(0x221A)
    assert [variant.name for variant in chain] == [
        "radical",
        "radical.v1",
        "radical.v2",
        "radical.v3",
        "radical.v4",
    ]
    boxes = [math.bbox(variant.codepoint) for variant in chain]
    assert [round(box.height + box.depth) for box in boxes] == [1000, 1200, 1800, 2400, 3000]
    assert boxes[0].height == math.math.radical_rule_thickness
    assert all(box.height > 20 * math.math.radical_rule_thickness for box in boxes[1:])
    # The stroke overhangs the advance, so the rule that starts there overlaps it.
    assert all(
        box.x_max > math.advance(variant.codepoint)
        for box, variant in zip(boxes, chain, strict=True)
    )


@pytest.mark.parametrize("delimiter", ["(", ")", "[", "]", "{", "}", "|"])
def test_a_delimiter_chain_ascends_from_the_body_glyph_and_stops_near_three_ems(
    bundled_fonts: Path, delimiter: str
) -> None:
    # Eight sizes each and no ninth: past the last one TeX would assemble a
    # delimiter from pieces, and this project refuses instead.
    math = math_metrics(DESIGN_SIZE)
    chain = math.vertical_variants(ord(delimiter))
    assert len(chain) == 8
    assert chain[0].codepoint == ord(delimiter)
    extents = []
    for variant in chain:
        box = math.bbox(variant.codepoint)
        extents.append(box.height + box.depth)
    assert extents == sorted(extents) and len(set(extents)) == 8
    assert 2900 < extents[-1] < 3700
    # Each is drawn about the axis, so centring one moves it by a unit at most.
    for variant in chain:
        box = math.bbox(variant.codepoint)
        assert abs((box.height - box.depth) / 2 - math.math.axis_height) <= 1.0

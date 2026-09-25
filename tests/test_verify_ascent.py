r"""
The arithmetic half of `scripts/verify_ascent.py`, checked without an atlas.

The script's value is that it compares two numbers correctly, and that comparison
is arithmetic that needs no font, no context and no imgui-bundle at all. Pinning
it here is what makes the script's output trustworthy rather than merely
plausible -- `tests/test_imgui_draw.py` is where the ImGui half is exercised.

The two functions worth the most attention are `predicted_glyph_top` and
`top_left_y`, because between them they are the whole of the baseline conversion
`advtext.backends.imgui_draw` performs. A sign error in either draws every line
in the document one ascent away from where it belongs, which is the failure
`advtext.shipout.Glyph` warns about in its own docstring.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from advtext.fontmetrics import Face
from advtext.style import Theme
from advtext.units import px_from_sp

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_ascent.py"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.

    The same loader `tests/test_verify_advances.py` uses, and for the reason
    stated there: a `scripts` directory on the path would let any test import any
    script by accident and would make the suite depend on collection order.
    """
    spec = importlib.util.spec_from_file_location("_verify_ascent_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = _load()

AscentReading = verify.AscentReading
OffsetResidual = verify.OffsetResidual
demo_sizes_px = verify.demo_sizes_px
format_ascent_report = verify.format_ascent_report
format_offset_report = verify.format_offset_report
predicted_glyph_top = verify.predicted_glyph_top
requested_size_px = verify.requested_size_px
top_left_y = verify.top_left_y
worst_residual_px = verify.worst_residual_px


def test_the_top_left_sits_one_ascent_above_the_baseline() -> None:
    """
    The conversion subtracts, so the top-left is above the baseline in screen coordinates.
    """
    assert top_left_y(100.0, 14.844) == pytest.approx(85.156)


def test_a_zero_ascent_leaves_the_baseline_where_it_was() -> None:
    """
    Nothing is added by the conversion itself; it is one subtraction and no more.
    """
    assert top_left_y(100.0, 0.0) == 100.0


def test_a_glyph_whose_ink_reaches_the_ascent_starts_at_the_top_left() -> None:
    """
    The tallest possible glyph has no gap above it, which is what makes the identity checkable.
    """
    assert predicted_glyph_top(26.0, 26.0) == 0.0


def test_a_shorter_glyph_starts_further_down_by_exactly_what_it_lacks() -> None:
    """
    The prediction is the ascent less the ink, so shorter ink means a larger offset.
    """
    assert predicted_glyph_top(26.0, 24.0) == pytest.approx(2.0)


def test_the_requested_size_is_the_faces_pixel_height_rather_than_its_em() -> None:
    """
    Roboto: hhea ascender 1900 and descender -500 give 2400, not the 2048 em.
    """
    assert requested_size_px(1900.0, 500.0) == 2400.0


def test_the_requested_size_equals_the_nominal_one_when_the_two_denominators_agree() -> None:
    """
    Latin Modern Math's ascent and descent sum to its em, so it needs no correction.
    """
    from advtext import fontlib

    metrics = fontlib.metrics(Face.MATH, 36.0)
    assert requested_size_px(metrics.ascent, metrics.descent) == pytest.approx(36.0)


def test_the_ascent_delta_is_theirs_minus_ours() -> None:
    """
    Negative means ImGui bakes a shorter ascent than fontTools measured.
    """
    reading = AscentReading(
        face=Face.PROSE, nominal_px=16.0, requested_px=16.0, ours_px=14.844, theirs_px=13.0
    )
    assert reading.delta_px == pytest.approx(-1.844)


def test_the_residual_is_actual_minus_predicted() -> None:
    """
    A positive residual means ImGui put the ink lower than the ascent predicts.
    """
    residual = OffsetResidual(
        face=Face.CODE,
        size_px=32.78,
        codepoint=0x41,
        actual_top_px=9.0,
        predicted_top_px=7.4,
    )
    assert residual.residual_px == pytest.approx(1.6)


def test_the_worst_residual_ignores_sign_so_opposite_errors_cannot_cancel() -> None:
    """
    A mean would hide a pair of equal and opposite errors; a screen would not.
    """
    residuals = [
        OffsetResidual(Face.PROSE, 16.0, 0x41, actual_top_px=3.0, predicted_top_px=6.0),
        OffsetResidual(Face.PROSE, 16.0, 0x67, actual_top_px=6.0, predicted_top_px=3.0),
    ]
    assert worst_residual_px(residuals) == pytest.approx(3.0)


def test_the_worst_residual_of_nothing_is_zero_rather_than_an_error() -> None:
    """
    A face covering none of the probes reports no residual, not a crash.
    """
    assert worst_residual_px([]) == 0.0


def test_the_demo_sizes_are_read_from_the_theme_rather_than_written_down() -> None:
    """
    Every size the theme generates appears, so the script cannot drift from the demo.
    """
    theme = Theme.build()
    sizes = demo_sizes_px(theme)
    for style in theme.blocks.values():
        assert px_from_sp(style.font.size, theme.px_per_inch) in sizes
    assert sizes == tuple(sorted(sizes)), "sizes are reported out of order"


def test_a_large_residual_is_reported_as_a_wrong_conversion_rather_than_quantisation() -> None:
    """
    The verdict must flip when the residual stops being explicable as rounding.
    """
    bad = [OffsetResidual(Face.PROSE, 16.0, 0x41, actual_top_px=0.0, predicted_top_px=14.0)]
    assert "WRONG" in format_offset_report("x", bad)

    good = [OffsetResidual(Face.PROSE, 16.0, 0x41, actual_top_px=3.0, predicted_top_px=2.5)]
    assert "WRONG" not in format_offset_report("x", good)


def test_the_ascent_report_names_every_face_it_was_given() -> None:
    """
    A report that silently drops a row would hide the face that disagrees.
    """
    readings = [
        AscentReading(Face.PROSE, 16.0, 18.75, 14.844, 16.0),
        AscentReading(Face.CODE, 16.0, 16.784, 13.744, 14.0),
    ]
    report = format_ascent_report("ascent", readings)
    assert Face.PROSE.value in report
    assert Face.CODE.value in report
    assert report.count("\n") == len(readings) + 1  # label, header, one row each

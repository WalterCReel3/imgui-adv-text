"""
Tests for the pure half of `scripts/verify_advances.py`.

The script is not a package and must not become one -- it is run as a file, the
way `scripts/render_litmus.py` is -- so it is loaded here by path rather than
imported. That keeps `scripts/` off `sys.path` for every other test in the suite,
which is worth a few lines of loader: a `scripts` directory on the path would let
any test import any script by accident and would make the suite depend on
collection order.

Only the arithmetic is covered. `imgui_advances` is excluded deliberately: it is
the one function that needs imgui-bundle, and a test asserting what ImGui's
advances *are* would pin this suite to a particular build of a particular font
renderer. What the script claims about ImGui belongs in its report, which is
regenerated on demand, not in an assertion.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_advances.py"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.
    """
    spec = importlib.util.spec_from_file_location("_verify_advances_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = _load()


# --------------------------------------------------------------------------------
# compare_advances
# --------------------------------------------------------------------------------


def test_compare_advances_reports_nothing_when_the_two_tables_agree() -> None:
    table = {65: 10.0, 66: 11.0}
    assert verify.compare_advances(table, dict(table)) == ()


def test_compare_advances_ignores_codepoints_only_one_side_has() -> None:
    ours = {65: 10.0, 66: 11.0}
    theirs = {65: 10.0, 67: 99.0}
    assert verify.compare_advances(ours, theirs) == ()


def test_compare_advances_records_delta_as_theirs_minus_ours() -> None:
    (only,) = verify.compare_advances({65: 10.0}, {65: 9.0})
    assert only.codepoint == 65
    assert only.ours_px == 10.0
    assert only.theirs_px == 9.0
    assert only.delta_px == pytest.approx(-1.0)


def test_compare_advances_suppresses_differences_within_the_tolerance() -> None:
    ours = {65: 10.0, 66: 10.0}
    theirs = {65: 10.4, 66: 11.5}
    (only,) = verify.compare_advances(ours, theirs, tolerance_px=0.5)
    assert only.codepoint == 66


def test_compare_advances_orders_results_by_codepoint() -> None:
    ours = {67: 1.0, 65: 1.0, 66: 1.0}
    theirs = {67: 2.0, 65: 2.0, 66: 2.0}
    assert [d.codepoint for d in verify.compare_advances(ours, theirs)] == [65, 66, 67]


# --------------------------------------------------------------------------------
# accumulated_drift
# --------------------------------------------------------------------------------


def test_accumulated_drift_is_zero_when_the_tables_agree() -> None:
    table = {ord("a"): 5.0, ord("b"): 6.0}
    drift = verify.accumulated_drift("abab", table, dict(table))
    assert drift.worst_px == 0.0
    assert drift.final_px == 0.0
    assert drift.compared == 4


def test_accumulated_drift_sums_a_systematic_error_rather_than_averaging_it() -> None:
    # The whole reason drift is the headline: a quarter-pixel per glyph is
    # invisible alone and is three pixels across a twelve-glyph word.
    ours = {ord("a"): 4.0}
    theirs = {ord("a"): 3.75}
    drift = verify.accumulated_drift("a" * 12, ours, theirs)
    assert drift.final_px == pytest.approx(-3.0)
    assert drift.worst_px == pytest.approx(3.0)


def test_accumulated_drift_worst_exceeds_final_when_deltas_cancel() -> None:
    # A total would report these as agreeing. On screen the reader sees two
    # pixels of error in the middle of the line, which is what `worst_px` keeps.
    ours = {ord("a"): 4.0, ord("b"): 4.0}
    theirs = {ord("a"): 6.0, ord("b"): 2.0}
    drift = verify.accumulated_drift("ab", ours, theirs)
    assert drift.final_px == pytest.approx(0.0)
    assert drift.worst_px == pytest.approx(2.0)


def test_accumulated_drift_counts_uncomparable_characters_instead_of_guessing() -> None:
    ours = {ord("a"): 4.0}
    theirs = {ord("a"): 5.0}
    drift = verify.accumulated_drift("axa", ours, theirs)
    assert drift.compared == 2
    assert drift.skipped == 1
    assert drift.final_px == pytest.approx(2.0)


def test_accumulated_drift_over_an_empty_sample_compares_nothing() -> None:
    drift = verify.accumulated_drift("", {65: 1.0}, {65: 2.0})
    assert drift.compared == 0
    assert drift.worst_px == 0.0


# --------------------------------------------------------------------------------
# uniform_ratio
# --------------------------------------------------------------------------------


def test_uniform_ratio_finds_the_constant_when_one_scale_explains_every_glyph() -> None:
    ours = {65: 10.0, 66: 20.0, 67: 7.5}
    theirs = {cp: value * 1.3333333 for cp, value in ours.items()}
    ratio = verify.uniform_ratio(ours, theirs)
    assert ratio is not None
    assert ratio == pytest.approx(1.3333333)


def test_uniform_ratio_returns_none_when_the_error_is_scattered_rather_than_a_unit() -> None:
    ours = {65: 10.0, 66: 20.0, 67: 30.0}
    theirs = {65: 10.0, 66: 21.0, 67: 29.0}
    assert verify.uniform_ratio(ours, theirs) is None


def test_uniform_ratio_ignores_zero_width_glyphs_rather_than_dividing_by_zero() -> None:
    ours = {65: 0.0, 66: 10.0}
    theirs = {65: 0.0, 66: 20.0}
    assert verify.uniform_ratio(ours, theirs) == pytest.approx(2.0)


def test_uniform_ratio_returns_none_when_no_glyph_carries_a_ratio() -> None:
    assert verify.uniform_ratio({65: 0.0}, {65: 0.0}) is None


def test_uniform_ratio_returns_none_when_the_tables_share_no_codepoint() -> None:
    assert verify.uniform_ratio({65: 1.0}, {66: 1.0}) is None


# --------------------------------------------------------------------------------
# format_report
# --------------------------------------------------------------------------------


def test_format_report_names_a_uniform_ratio_as_a_unit_disagreement() -> None:
    drift = verify.Drift(worst_px=1.0, final_px=1.0, compared=3, skipped=0)
    report = verify.format_report("prose", drift, (), 1.333333)
    assert "uniform ratio detected" in report
    assert "1.333333" in report


def test_format_report_does_not_call_a_ratio_of_exactly_one_a_disagreement() -> None:
    # Inconsolata produces this: every advance matches, so the ratio is 1.0.
    # Reporting that as "a unit disagreement" reads as a failure and is a pass.
    drift = verify.Drift(worst_px=0.0, final_px=0.0, compared=3, skipped=0)
    report = verify.format_report("code", drift, (), 1.0)
    assert "disagreement" not in report
    assert "agree exactly" in report


def test_format_report_omits_the_ratio_line_when_there_is_no_uniform_ratio() -> None:
    drift = verify.Drift(worst_px=1.0, final_px=1.0, compared=3, skipped=0)
    assert "uniform ratio" not in verify.format_report("prose", drift, (), None)


def test_format_report_singles_out_the_worst_glyph_by_absolute_delta() -> None:
    drift = verify.Drift(worst_px=3.0, final_px=3.0, compared=2, skipped=0)
    disagreements = (
        verify.Disagreement(codepoint=65, ours_px=10.0, theirs_px=11.0),
        verify.Disagreement(codepoint=66, ours_px=10.0, theirs_px=7.0),
    )
    report = verify.format_report("prose", drift, disagreements, None)
    assert "U+0042" in report
    assert "-3.0000" in report

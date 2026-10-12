r"""
Claims about the dimension type, concentrated on the errors that stay quiet.

`imscribe.units` is six short functions and there is nothing subtle in any one of
them. What is subtle is the seam they sit on, and every failure here is a failure
that produces plausible output:

- **`pt` and `bp` are different units.** 72.27 per inch against 72. Treating one
  as the other is a 0.4% error, which on a 500pt column is two points -- enough
  to move a line break and not enough to look like a unit bug.
- **Rounding to the pixel grid happens once, on a final absolute coordinate.**
  Rounding widths and summing them instead is the error that walks along a line
  and lands the last word off the right margin. One test below shows the two
  disagreeing by a whole pixel over three items, which is the smallest honest
  demonstration.
- **`px_per_inch` is a parameter, not a global.** A hidden DPI is a value two
  call sites disagree about and neither mentions, so the default is pinned and
  so is the behaviour at a second resolution.

`docs/decisions.md` settles the convention these tests encode: the layout core
carries integer scaled points, device space is pixels, and a font size given as
"16" means 16 device pixels rather than 16 points. That is checked here as an
arithmetic claim so that the number in the decisions file and the number the code
produces cannot drift apart silently.

Not tested here: `GlueOrder`'s ordering semantics, which `tests/test_nodes.py`
pins through `GlueTotal` where they are load-bearing.
"""

from __future__ import annotations

import pytest

from imscribe.units import (
    BP_PER_INCH,
    DEFAULT_PX_PER_INCH,
    MAX_DIMEN,
    PT_PER_INCH,
    RUNNING,
    UNITY,
    pt_from_sp,
    px_from_sp,
    round_to_px,
    sp_from_bp,
    sp_from_pt,
    sp_from_px,
)


def test_one_printers_point_is_exactly_the_unity_constant_the_source_names() -> None:
    # §101: `@d unity == '200000`. Every other conversion is scaled against this
    # one, so a slip here would be uniform and therefore invisible.
    assert UNITY == 65536
    assert sp_from_pt(1.0) == UNITY
    assert pt_from_sp(UNITY) == 1.0


def test_a_whole_number_of_points_round_trips_through_scaled_points_exactly() -> None:
    for points in (0.0, 1.0, 10.0, 12.0, -5.0, 16383.0):
        assert pt_from_sp(sp_from_pt(points)) == points

    # Halves, quarters and any other dyadic fraction are exact too, because a
    # scaled point is 2^-16 pt and the representation is binary all the way down.
    for points in (0.5, 0.25, 12.75, -3.125, 1.0 / 65536.0):
        assert pt_from_sp(sp_from_pt(points)) == points


def test_a_fractional_point_round_trips_to_within_the_half_scaled_point_it_was_rounded_by() -> None:
    # sp_from_pt rounds once on the way in, so the round trip is lossy by at most
    # half a scaled point -- 2^-17 pt, about 12 nanometres at any plausible size.
    # Asserting the bound rather than equality is what keeps this a claim about
    # the representation instead of a claim about floating point.
    for points in (0.1, 1.0 / 3.0, 9.9999, 12.045, 72.27, -0.7):
        assert pt_from_sp(sp_from_pt(points)) == pytest.approx(points, abs=0.5 / UNITY)


def test_a_point_and_a_big_point_are_different_lengths_and_do_not_silently_interchange() -> None:
    # The classic quiet error: `bp` is the PostScript/PDF/CSS "point" and `pt` is
    # TeX's. 72 of one and 72.27 of the other are both an inch, so the two agree
    # about the inch and about nothing else.
    assert PT_PER_INCH == 72.27
    assert BP_PER_INCH == 72.0

    one_inch = sp_from_pt(PT_PER_INCH)
    assert sp_from_bp(BP_PER_INCH) == one_inch

    assert sp_from_pt(72.0) != sp_from_bp(72.0)
    assert sp_from_bp(72.0) - sp_from_pt(72.0) == 17695
    assert pt_from_sp(sp_from_bp(1.0)) == pytest.approx(1.00375, abs=1e-5)


def test_a_font_size_of_sixteen_means_sixteen_device_pixels_not_sixteen_points() -> None:
    # `docs/decisions.md`: a size given as "16" is 16 device pixels, matching
    # ImGui's own convention, which at 96 px/inch is 12.045 pt internally. If the
    # ImGui backend turns out to read its coordinates as points, this is the seam
    # that is wrong and it is wrong by 96/72.27 = 1.33x -- large enough to see.
    sixteen_px = sp_from_px(16.0)
    assert pt_from_sp(sixteen_px) == pytest.approx(12.045, abs=1e-3)
    assert pt_from_sp(sixteen_px) != pytest.approx(16.0, abs=0.5)
    assert px_from_sp(sixteen_px) == pytest.approx(16.0, abs=1e-4)


def test_pixels_and_points_are_related_only_through_the_resolution_argument() -> None:
    assert DEFAULT_PX_PER_INCH == 96.0

    # At 72 px/inch a pixel is a big point by definition, so a length built from
    # bp comes back out as the same number of pixels.
    ten_bp = sp_from_bp(10.0)
    assert px_from_sp(ten_bp, 72.0) == pytest.approx(10.0, abs=1e-4)

    # At 96 the same length is 4/3 as many pixels. Nothing in the module knows
    # that; it falls out of the argument, which is the point of it being one.
    assert px_from_sp(ten_bp, 96.0) == pytest.approx(10.0 * 96.0 / 72.0, abs=1e-4)
    assert px_from_sp(ten_bp, 96.0) != px_from_sp(ten_bp, 72.0)


def test_converting_pixels_to_scaled_points_and_back_is_stable_at_both_resolutions() -> None:
    for px_per_inch in (96.0, 72.0):
        for pixels in (0.0, 1.0, 16.0, 800.0, -12.5):
            length = sp_from_px(pixels, px_per_inch)
            assert px_from_sp(length, px_per_inch) == pytest.approx(pixels, abs=1e-4)


def test_converting_scaled_points_to_pixels_deliberately_does_not_round() -> None:
    # `px_from_sp` is fractional on purpose: rounding here would round every
    # intermediate length and put the error back where the integer representation
    # exists to keep it out of. `round_to_px` is the one place that rounds.
    half_pixel = sp_from_px(0.5)
    assert px_from_sp(half_pixel) == pytest.approx(0.5, abs=1e-5)
    assert not float(px_from_sp(half_pixel)).is_integer()


def test_rounding_the_sum_of_widths_beats_rounding_each_width_and_summing() -> None:
    # The whole reason `round_to_px` is documented as applying to an absolute
    # coordinate. Three items of 3.4px are 10.2px and end at pixel 10; rounding
    # each to 3px and summing puts the third one at 9, a whole pixel short. Over
    # a justified line that error is what makes the right margin look ragged.
    item = sp_from_px(3.4)
    assert round_to_px(3 * item) == 10
    assert 3 * round_to_px(item) == 9

    # The general shape: rounding the running position is never off by more than
    # half a pixel however many items precede it, while rounding each width first
    # drifts without bound. Over 40 items the naive route is four pixels short.
    running = 0
    worst_positional = 0.0
    for _ in range(40):
        running += item
        worst_positional = max(worst_positional, abs(round_to_px(running) - px_from_sp(running)))
    assert worst_positional <= 0.5
    assert px_from_sp(running) - 40 * round_to_px(item) == pytest.approx(16.0, abs=0.05)


def test_rounding_to_the_pixel_grid_is_pythons_half_to_even_and_not_the_glue_rounding() -> None:
    # Correction C3 in `docs/tex-notes.md`: §625's glue rounding is sp to sp,
    # inside the layout core, and must be Pascal's half-away-from-zero. This
    # function is a different operation -- sp to device pixels, once, on a final
    # absolute coordinate -- and uses Python's `round`, which ties to even. The
    # two are pinned apart here so that nobody reaches for this one when
    # implementing that one: Pascal would give 3 and -3 on the first and third.
    #
    # At 72.27 px/inch a pixel is exactly a point, which is how these land on
    # exact halves rather than near them.
    per_inch = PT_PER_INCH
    assert px_from_sp(sp_from_pt(2.5), per_inch) == 2.5
    assert round_to_px(sp_from_pt(2.5), per_inch) == 2
    assert round_to_px(sp_from_pt(3.5), per_inch) == 4
    assert round_to_px(sp_from_pt(-2.5), per_inch) == -2


def test_the_running_sentinel_and_the_maximum_dimension_are_the_sources_values() -> None:
    # RUNNING is `null_flag` (§138) and must stay recognisable by identity of
    # value rather than by magnitude: it is a sentinel and adding it to anything
    # is a bug, so it sits well below any dimension MAX_DIMEN permits.
    assert RUNNING == -(1 << 30)
    assert MAX_DIMEN == (1 << 30) - 1
    assert RUNNING < -MAX_DIMEN
    assert pt_from_sp(MAX_DIMEN) == pytest.approx(16384.0, abs=1e-3)

"""
Claims about `badness`, pinned hard because its exact values are a public contract.

§108 says every implementation of TeX should use precisely this method, and the
fitness classes §817 *names* are sorted by thresholds applied to the integers it
returns. So these are not smoke tests: several assert a specific number, and a
change that moves one of them has changed where lines break even if nothing else
notices.

Where the thresholds actually live, because §817 is the wrong citation for them
and the wrong one is easy to keep copying: §817 declares the four class codes
(`very_loose_fit=0`, `loose_fit=1`, `decent_fit=2`, `tight_fit=3`). The
comparisons are in `try_break`. §852, stretching, is a three-way ladder --
`b > 99` very loose, `b > 12` loose, otherwise decent. §853, shrinking, is a
two-way one -- `b > 12` tight, otherwise decent. **There is no "very tight"**;
shrinking past the available shrinkability is not a worse class but a hard
`b := inf_bad + 1`, which is not a value this function can return.

Two of the tests check the source's own arithmetic claims rather than a
restatement of them -- the distinct-value count from §108 and the monotonicity
§108 says is provable. Those are the ones that would catch a transcription slip
in a constant, which is the failure mode a hand-copied integer approximation
actually has.
"""

from __future__ import annotations

import pytest

from advtext.badness import INF_BAD, badness

# With s = 297, the approximation collapses to r = t, which makes r directly
# addressable and lets the cutoff and the class boundaries be probed exactly.
_S_MAKING_R_EQUAL_T = 297


def test_badness_is_zero_when_nothing_has_to_be_made_up() -> None:
    assert badness(0, 0) == 0
    assert badness(0, 100) == 0
    assert badness(0, -1) == 0


def test_badness_saturates_at_inf_bad_when_there_is_no_stretch() -> None:
    assert badness(1, 0) == INF_BAD
    assert badness(65536, 0) == INF_BAD
    assert badness(1, -50) == INF_BAD


def test_badness_is_exactly_one_hundred_when_the_stretch_is_exactly_used_up() -> None:
    # The value §852's `b > 99` test is calibrated against: t == s is the edge
    # between "loose" and "very loose". If this drifts, that boundary moves.
    for s in (1, 10, 297, 65536, 1_000_000, 7_230_584):
        assert badness(s, s) == 100, f"badness({s}, {s})"


def test_badness_is_exactly_twelve_when_half_the_stretch_is_used() -> None:
    # The value the `b > 12` test is calibrated against, in both directions: it
    # is the edge between "decent" and loose in §852 and between "decent" and
    # tight in §853.
    for s in (100, 65536, 1_000_000, 7_000_000):
        assert badness(s // 2, s) == 12, f"badness({s // 2}, {s})"


def test_the_decent_fit_boundary_sits_between_r_of_148_and_149() -> None:
    assert badness(148, _S_MAKING_R_EQUAL_T) == 12
    assert badness(149, _S_MAKING_R_EQUAL_T) == 13


def test_the_loose_fit_boundary_sits_between_r_of_296_and_297() -> None:
    assert badness(296, _S_MAKING_R_EQUAL_T) == 99
    assert badness(297, _S_MAKING_R_EQUAL_T) == 100


def test_badness_is_still_finite_at_the_1290_cutoff_and_infinite_just_past_it() -> None:
    assert badness(1290, _S_MAKING_R_EQUAL_T) == 8189
    assert badness(1291, _S_MAKING_R_EQUAL_T) == INF_BAD


def test_the_largest_finite_badness_stays_under_the_2_to_the_13_ceiling_section_108_names() -> None:
    # §108: "Any badness of 2^13 or more is treated as infinitely bad." The
    # cutoff at r = 1290 lands at 8189, so the finite range stops short of 8192
    # and never collides with the 10000 sentinel. §828 depends on that.
    largest_finite = max(badness(r, _S_MAKING_R_EQUAL_T) for r in range(1, 1291))
    assert largest_finite == 8189
    assert largest_finite < 2**13 < INF_BAD


def test_badness_can_produce_exactly_the_1095_distinct_values_section_108_claims() -> None:
    # §108: "The badness function defined here is capable of computing at most
    # 1095 distinct values." Counting them exercises every branch of the
    # approximation against a number Knuth published, which is the check a
    # hand-transcribed constant most needs.
    produced = {badness(r, _S_MAKING_R_EQUAL_T) for r in range(0, 1292)}
    assert len(produced) == 1095
    assert INF_BAD in produced


def test_badness_never_decreases_as_more_has_to_be_made_up() -> None:
    # §108 proves badness(t+1, s) >= badness(t, s).
    s = 65536
    previous = 0
    for t in range(0, 3 * s, 97):
        current = badness(t, s)
        assert current >= previous, f"badness({t}, {s}) fell below its predecessor"
        previous = current


def test_badness_never_increases_as_more_stretch_becomes_available() -> None:
    # §108 proves badness(t, s) >= badness(t, s+1).
    t = 65536
    previous = INF_BAD
    for s in range(1, 4 * t, 211):
        current = badness(t, s)
        assert current <= previous, f"badness({t}, {s}) rose above its predecessor"
        previous = current


def test_badness_divides_before_multiplying_once_t_is_too_large_to_scale() -> None:
    # Above 7230584 the source divides first to keep `t * 297` inside 31 bits.
    # The two paths must still agree about the answer: 8e6 against 2e6 is four
    # times the available stretch either way.
    large = badness(8_000_000, 2_000_000)
    assert large == badness(4, 1)
    assert large == 6396


def test_dividing_before_multiplying_can_change_a_feasible_break_into_an_infeasible_one() -> None:
    # The test above passes whether or not the divide-first branch exists, so it
    # does not protect it. This input does. It is the maximally separating one:
    #
    #   s = 1663793 = 297 * 5601 + 296  -- the largest possible truncation loss
    #                                      in `s div 297`, and above 1663497 so
    #                                      the scaled-divide branch is taken.
    #   t = 7230891 = 5601 * 1291       -- above 7230584, so `t * 297` would not
    #                                      fit in a signed 32-bit word.
    #
    # TeX's path: r = t div (s div 297) = 7230891 div 5601 = 1291, past the 1290
    # cutoff, so INF_BAD. Always multiplying first: r = (t * 297) div s = 1290,
    # so 8189. Infinite against finite is the largest disagreement there is, and
    # it is the one that decides whether `try_break` considers the breakpoint
    # feasible at all.
    s = 1_663_793
    t = 7_230_891
    assert s // 297 == 5601 and s % 297 == 296
    assert t == 5601 * 1291

    assert badness(t, s) == INF_BAD

    multiply_first = (t * 297) // s
    assert multiply_first == 1290
    assert (multiply_first**3 + (1 << 17)) // (1 << 18) == 8189


def test_badness_is_infinite_when_t_is_too_large_to_scale_and_s_is_too_small_to_divide_by() -> None:
    # t > 7230584 and s < 1663497 sets r := t, which always exceeds the cutoff.
    assert badness(8_000_000, 1_000_000) == INF_BAD
    assert badness(7_230_585, 1_663_496) == INF_BAD


def test_badness_rejects_a_negative_total_because_the_source_defines_it_for_t_at_least_zero() -> (
    None
):
    # Callers measuring shrink negate their shortfall first (§853). Letting a
    # negative through would floor the wrong way under Python's `//` and return
    # a plausible wrong number instead of failing.
    with pytest.raises(ValueError, match="t >= 0"):
        badness(-1, 65536)


def test_badness_stays_within_its_documented_range_across_a_wide_sweep() -> None:
    # §828 relies on badness never exceeding 10000.
    for t in range(0, 20_000_000, 137_117):
        for s in (0, 1, 297, 65536, 1_663_497, 9_000_000):
            assert 0 <= badness(t, s) <= INF_BAD

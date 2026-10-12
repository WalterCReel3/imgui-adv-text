r"""
Claims about total-fit line breaking, built on round numbers so the arithmetic is checkable.

Words are boxes with whole-point widths and the interword space is 6pt plus 4pt
minus 2pt, so every line's natural width, stretch and shrink can be added up by
hand from the word list in the test name's paragraph. Nothing here opens a font.

**The important test is `test_the_chosen_breaking_has_the_fewest_total_demerits_of_
every_possible_breaking`.** It enumerates all 2^8 subsets of the breakpoints in a
nine-word paragraph, scores each one by forcing exactly that breaking, and
asserts the algorithm's answer is the minimum. That is the total-fit property
stated as an assertion rather than as an anecdote, and a greedy implementation
fails it on this paragraph -- which the next test demonstrates separately, so
the two claims do not lean on each other.

Forcing a specific breaking is done by putting `Penalty(EJECT_PENALTY)` before
the glue where a break is wanted and `Penalty(INF_PENALTY)` before every other
glue. An infinite penalty makes both the penalty *and* the glue after it illegal
(§868: a penalty does not permit a break at the following glue), so the only
breaks left are the forced ones. The demerits stay comparable because §859
charges nothing for a break at exactly `eject_penalty` and nothing for a break at
glue, so the two ways of arriving at the same line division score identically.
"""

from __future__ import annotations

import itertools

import pytest

from imscribe.linebreak import (
    BreakPass,
    Fitness,
    LineBreakParams,
    LineSpec,
    Paragraph,
    ParShape,
    break_paragraph,
)
from imscribe.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
    BoxKind,
    CharNode,
    Disc,
    Glue,
    GlueSpec,
    Kern,
    KernKind,
    MathOff,
    MathOn,
    Node,
    Penalty,
)
from imscribe.pack import CharDimens, PackFitness
from imscribe.units import GlueOrder, sp_from_pt

PT = sp_from_pt(1.0)
SPACE = GlueSpec(width=6 * PT, stretch=4 * PT, shrink=2 * PT)
LINE = 100 * PT

# Greedy first-fit crams four words onto line one, using every scrap of its
# shrink; the optimum gives one of them up so that neither line has to work
# hard. Both produce two lines, so the comparison is about quality and not
# about line count.
SHOWCASE = (12, 19, 27, 14, 12, 13, 19, 15, 18)

# Accept every finite badness, so that any breaking at all can be scored and the
# brute-force search is over the whole space rather than over the feasible part
# of it. `pretolerance` matching `tolerance` also keeps every scored paragraph on
# the first pass, where §854's zero-demerit escape cannot fire and silently make
# a hopeless breaking look free.
PERMISSIVE = LineBreakParams(pretolerance=10000, tolerance=10000)


def _word(points: int) -> Box:
    """
    A stand-in for a set word: a box of known width, with no contents to measure.
    """
    return Box(kind=BoxKind.HLIST, width=points * PT, height=7 * PT, depth=2 * PT)


def _para(widths: tuple[int, ...]) -> list[Node]:
    """
    Words separated by ordinary interword glue.
    """
    out: list[Node] = []
    for index, width in enumerate(widths):
        if index:
            out.append(Glue(SPACE))
        out.append(_word(width))
    return out


def _forced(widths: tuple[int, ...], breaks: frozenset[int]) -> list[Node]:
    """
    The same paragraph, breakable only at the word indices in `breaks`.
    """
    out: list[Node] = []
    for index, width in enumerate(widths):
        if index:
            out.append(Penalty(EJECT_PENALTY if index in breaks else INF_PENALTY))
            out.append(Glue(SPACE))
        out.append(_word(width))
    return out


def _score(widths: tuple[int, ...], breaks: frozenset[int]) -> int | None:
    """
    Total demerits of exactly this breaking, or `None` if it is not realisable.
    """
    result = break_paragraph(_forced(widths, breaks), ParShape.uniform(LINE), PERMISSIVE)
    if result.pass_used is not BreakPass.FIRST or len(result.lines) != len(breaks) + 1:
        return None
    return result.total_demerits


def _greedy(widths: tuple[int, ...]) -> frozenset[int]:
    """
    First-fit: keep adding words while the line can still be set without overfull.

    A fair greedy rather than a weak one -- it uses the available shrink, so it
    is not losing to the optimiser merely by refusing to squeeze.
    """
    breaks: set[int] = set()
    line: list[int] = []
    for index, width in enumerate(widths):
        trial = [*line, width]
        natural = sum(trial) + 6 * (len(trial) - 1)
        shrink = 2 * (len(trial) - 1)
        if line and natural - shrink > 100:
            breaks.add(index)
            line = [width]
        else:
            line = trial
    return frozenset(breaks)


def _words_per_line(result: Paragraph) -> list[int]:
    """
    How many word boxes ended up on each line, which is the shape of the breaking.
    """
    return [sum(1 for node in line.box.contents if isinstance(node, Box)) for line in result.lines]


def _glue_index(word: int) -> int:
    """
    Where the interword glue before `word` sits in a list built by `_para`.
    """
    return 2 * word - 1


# --------------------------------------------------------------------------
# The shape of the result
# --------------------------------------------------------------------------


def test_a_paragraph_that_fits_on_one_line_produces_one_line_and_does_not_stretch() -> None:
    result = break_paragraph(_para((10, 10, 10)), ParShape.uniform(200 * PT))
    assert len(result.lines) == 1
    assert result.pass_used is BreakPass.FIRST
    # `\parfillskip` is infinitely stretchable, so the last line's glue order is
    # `fil` and its badness is zero by §852. The interword spaces keep their
    # natural width instead of being spread across the empty half of the line.
    assert result.lines[0].box.glue_order is GlueOrder.FIL
    assert result.lines[0].badness == 0
    assert result.lines[0].fitness is PackFitness.INFINITE_GLUE


def test_a_short_last_line_is_left_short_instead_of_being_stretched_to_the_margin() -> None:
    # Two 48pt words fill line one exactly once their space shrinks; the 10pt
    # word is left alone on line two. Without `\parfillskip` that line would be
    # asked to make up 90pt and would come back very loose. With it, the fil
    # stretch absorbs everything, §852 scores the line at badness 0, and nothing
    # on it moves.
    result = break_paragraph(_para((48, 48, 10)), ParShape.uniform(LINE))
    assert len(result.lines) == 2
    last = result.lines[-1]
    assert last.box.glue_order is GlueOrder.FIL
    assert last.badness == 0
    assert last.natural < LINE


def test_the_final_penalty_and_parfillskip_are_appended_to_the_paragraph() -> None:
    # §816. Without them the last line would be justified like every other and
    # the paragraph would end with a stretched-out line of text.
    result = break_paragraph(_para((10,)), ParShape.uniform(LINE))
    kinds = [type(node).__name__ for node in result.lines[0].box.contents]
    assert kinds == ["Box", "Penalty", "Glue", "Glue"]


def test_a_trailing_space_is_replaced_by_the_final_penalty_rather_than_kept() -> None:
    # §816 replaces a trailing glue node instead of appending after it. Keeping
    # it would make it a legal breakpoint and allow an empty last line.
    with_space = break_paragraph([*_para((10, 10)), Glue(SPACE)], ParShape.uniform(LINE))
    without = break_paragraph(_para((10, 10)), ParShape.uniform(LINE))
    assert len(with_space.lines) == 1
    assert with_space.lines[0].natural == without.lines[0].natural


# --------------------------------------------------------------------------
# Total fit: the property that distinguishes this from a greedy filler
# --------------------------------------------------------------------------


def test_the_chosen_breaking_has_the_fewest_total_demerits_of_every_possible_breaking() -> None:
    chosen = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), PERMISSIVE)
    assert chosen.pass_used is BreakPass.FIRST

    scores = [
        score
        for size in range(len(SHOWCASE))
        for combination in itertools.combinations(range(1, len(SHOWCASE)), size)
        if (score := _score(SHOWCASE, frozenset(combination))) is not None
    ]
    assert scores, "no breaking of the showcase paragraph could be scored"
    assert chosen.total_demerits == min(scores)


def test_greedy_first_fit_picks_a_different_and_worse_breaking_for_the_same_paragraph() -> None:
    # Without this the optimality test proves nothing about total fit: an
    # implementation that filled each line greedily could still be "optimal"
    # among the breakings it was capable of finding.
    chosen = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), PERMISSIVE)
    greedy_breaks = _greedy(SHOWCASE)
    greedy_score = _score(SHOWCASE, greedy_breaks)

    assert greedy_score is not None
    assert greedy_score > chosen.total_demerits
    # Same number of lines, so the optimiser is not winning by being shorter.
    assert len(greedy_breaks) + 1 == len(chosen.lines)
    # Greedy fills line one to exactly its shrink limit; the optimum gives up a
    # word so that neither line is strained.
    assert greedy_breaks == frozenset({5})
    assert _words_per_line(chosen) == [4, 5]


def test_adjacent_lines_of_very_different_fitness_are_charged_adj_demerits() -> None:
    # A very loose line (fitness 0) next to a tight one (fitness 3) differ by 3,
    # which is more than 1, so §859 charges `adj_demerits`. The paragraph's own
    # beginning counts as decent (2), so a very loose *first* line is itself an
    # adjacency violation -- hence two charges, not one.
    loose_space = GlueSpec(width=6 * PT, stretch=5 * PT, shrink=2 * PT)
    tight_space = GlueSpec(width=7 * PT, stretch=5 * PT, shrink=5 * PT)
    nodes: list[Node] = [
        _word(40),
        Glue(loose_space),
        _word(39),
        Penalty(EJECT_PENALTY),
        Glue(loose_space),
        _word(48),
        Glue(tight_space),
        _word(48),
    ]

    def total(adj: int) -> int:
        params = LineBreakParams(pretolerance=10000, tolerance=10000, adj_demerits=adj)
        return break_paragraph(nodes, ParShape.uniform(LINE), params).total_demerits

    assert total(7777) - total(0) == 2 * 7777


def test_a_negative_penalty_attracts_a_break_that_a_zero_penalty_would_not() -> None:
    # §859 subtracts the square of a negative penalty, so a break there is
    # rewarded rather than merely permitted. This is how `\penalty-50` before a
    # heading pulls the break towards itself.
    neutral = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), PERMISSIVE)
    assert _words_per_line(neutral) == [4, 5]

    # Word 5 is where greedy breaks and is *not* the optimum, so an attractor
    # there has to overcome a real difference to win. 99 squared is 9801, which
    # is more than the 7611 by which that breaking was losing.
    nodes = _para(SHOWCASE)
    nodes.insert(_glue_index(5), Penalty(-99))
    attracted = break_paragraph(nodes, ParShape.uniform(LINE), PERMISSIVE)

    assert _words_per_line(attracted) == [5, 4]
    assert attracted.total_demerits < neutral.total_demerits


# --------------------------------------------------------------------------
# Forced and forbidden breaks
# --------------------------------------------------------------------------


def test_a_forced_break_ends_a_line_wherever_it_appears() -> None:
    nodes = [*_para(SHOWCASE)[:3], Penalty(EJECT_PENALTY), *_para(SHOWCASE)[3:]]
    result = break_paragraph(nodes, ParShape.uniform(LINE))
    # Two words on line one, whatever that does to the fit.
    assert _words_per_line(result)[0] == 2
    assert len(result.lines) > 1


def test_an_infinite_penalty_is_never_chosen_as_a_breakpoint() -> None:
    # §831 returns immediately for a penalty of inf_penalty or more, and §868
    # then refuses the glue after it too, because a penalty does not permit a
    # break at a following glue.
    unblocked = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), PERMISSIVE)
    assert _words_per_line(unblocked) == [4, 5]

    nodes = _para(SHOWCASE)
    nodes.insert(_glue_index(4), Penalty(INF_PENALTY))
    blocked = break_paragraph(nodes, ParShape.uniform(LINE), PERMISSIVE)
    assert _words_per_line(blocked) != [4, 5]


# --------------------------------------------------------------------------
# Where a break is legal (§866, §868)
# --------------------------------------------------------------------------


def test_glue_inside_a_formula_is_never_a_breakpoint() -> None:
    # §866 sets `auto_breaking := (subtype = after)`, so it is off from MathOn
    # until MathOff. Here the glue inside the formula would give a perfect 60pt
    # first line; refusing it costs an overfull line, and that is correct --
    # a formula is not split by the spaces inside it.
    nodes: list[Node] = [
        _word(50),
        MathOn(),
        _word(10),
        Glue(SPACE),
        _word(10),
        MathOff(),
        Glue(SPACE),
        _word(50),
    ]
    result = break_paragraph(nodes, ParShape.uniform(60 * PT))
    assert result.lines[0].fitness is PackFitness.OVERFULL
    # The formula's internal glue is still there, in the middle of line one.
    assert [type(n).__name__ for n in result.lines[0].box.contents] == [
        "Box",
        "MathOn",
        "Box",
        "Glue",
        "Box",
        "MathOff",
        "Glue",
    ]


def test_an_explicit_kern_before_glue_is_a_breakpoint_and_loses_its_width() -> None:
    # §866's `kern_break`, and §881's `width(q) := 0`. Breaking at the kern is
    # the only way to get an exact 30pt line here.
    nodes: list[Node] = [
        _word(30),
        Kern(2 * PT, KernKind.EXPLICIT),
        Glue(SPACE),
        _word(30),
        Glue(SPACE),
        _word(30),
    ]
    result = break_paragraph(nodes, ParShape.uniform(30 * PT))
    first = result.lines[0]
    assert first.fitness is PackFitness.EXACT
    assert [type(n).__name__ for n in first.box.contents] == ["Box", "Kern", "Glue"]
    assert first.box.contents[1] == Kern(0, KernKind.EXPLICIT)


def test_a_font_kern_is_not_a_breakpoint_but_still_permits_one_at_the_glue_after_it() -> None:
    # The same list with an implicit kern. The kern itself is no longer a break,
    # so the line runs on to the glue and keeps the kern's 2pt -- which is the
    # third branch of §868 doing its job. Were that branch missing there would
    # be no legal break here at all.
    nodes: list[Node] = [
        _word(30),
        Kern(2 * PT, KernKind.NORMAL),
        Glue(SPACE),
        _word(30),
        Glue(SPACE),
        _word(30),
    ]
    result = break_paragraph(nodes, ParShape.uniform(30 * PT))
    first = result.lines[0]
    assert first.fitness is PackFitness.OVERFULL
    assert first.overfull_by == 2 * PT
    assert first.box.contents[1] == Kern(2 * PT, KernKind.NORMAL)
    assert len(result.lines) == 3


# --------------------------------------------------------------------------
# Discretionaries (built by hand; nothing here hyphenates)
# --------------------------------------------------------------------------


def test_a_discretionary_puts_its_pre_break_text_at_the_end_of_the_broken_line() -> None:
    hyphen = Disc(pre_break=(_word(2),))
    nodes: list[Node] = [
        _word(40),
        Glue(SPACE),
        _word(30),
        hyphen,
        _word(30),
        Glue(SPACE),
        _word(40),
    ]
    result = break_paragraph(nodes, ParShape.uniform(80 * PT), LineBreakParams(hyphen_penalty=0))

    first = result.lines[0]
    assert [n for n in first.box.contents if isinstance(n, Box)] == [
        _word(40),
        _word(30),
        _word(2),
    ]
    # And the second line starts with the node the discretionary sat before.
    assert result.lines[1].box.contents[0] == _word(30)


def test_a_discretionarys_replacement_nodes_disappear_only_when_the_break_is_taken() -> None:
    # §881 destroys the `replace_count` nodes following the discretionary when
    # it breaks there, and leaves them alone otherwise.
    disc = Disc(pre_break=(_word(2),), post_break=(_word(3),), replace_count=1)
    nodes: list[Node] = [_word(40), Glue(SPACE), _word(30), disc, _word(9), Glue(SPACE), _word(40)]
    broken = break_paragraph(nodes, ParShape.uniform(80 * PT), LineBreakParams(hyphen_penalty=0))

    widths = [
        [n.width // PT for n in line.box.contents if isinstance(n, Box)] for line in broken.lines
    ]
    assert widths[0] == [40, 30, 2]
    # The 9pt replacement is gone; the post-break 3pt takes its place.
    assert widths[1] == [3, 40]


# --------------------------------------------------------------------------
# Per-line widths
# --------------------------------------------------------------------------


def test_a_narrower_first_line_produces_a_shorter_first_line() -> None:
    wide = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE))
    narrow = break_paragraph(
        _para(SHOWCASE), ParShape((LineSpec(60 * PT), LineSpec(LINE))), LineBreakParams()
    )
    assert narrow.lines[0].box.width == 60 * PT
    assert narrow.lines[1].box.width == LINE
    assert _words_per_line(narrow)[0] < _words_per_line(wide)[0]


def test_a_hanging_indent_shifts_every_line_after_the_first_and_narrows_it() -> None:
    # §849 with a non-negative `hang_after`: the first line keeps the full
    # width, the rest give up `indent` and are moved right by it. That is a
    # bulleted item, with the marker in the space line one gave up.
    shape = ParShape.hanging(LINE, 12 * PT)
    result = break_paragraph(_para(SHOWCASE), shape)
    assert result.lines[0].box.width == LINE
    assert result.lines[0].box.shift_amount == 0
    for line in result.lines[1:]:
        assert line.box.width == LINE - 12 * PT
        # §889 applies the indent as the box's shift_amount, not as glue, so it
        # cannot be stretched by justification.
        assert line.box.shift_amount == 12 * PT


def test_the_last_line_spec_applies_to_every_line_after_it() -> None:
    # §847: "the specifications for line n apply to all subsequent lines".
    shape = ParShape((LineSpec(40 * PT), LineSpec(70 * PT)))
    result = break_paragraph(_para(SHOWCASE), shape)
    assert len(result.lines) > 2
    assert [line.box.width for line in result.lines[1:]] == [70 * PT] * (len(result.lines) - 1)


def test_a_parshape_with_no_lines_is_rejected_rather_than_silently_overfulling() -> None:
    with pytest.raises(ValueError, match="at least one LineSpec"):
        ParShape(())


# --------------------------------------------------------------------------
# The cases that must not raise
# --------------------------------------------------------------------------


def test_a_word_wider_than_its_line_comes_back_overfull_rather_than_hanging_or_raising() -> None:
    # §854's last resort. Overfull output beats no output, and the PackResult
    # says by how much, so a caller that wants to complain has the number.
    result = break_paragraph([_word(300)], ParShape.uniform(LINE))
    assert len(result.lines) == 1
    assert result.lines[0].fitness is PackFitness.OVERFULL
    assert result.lines[0].overfull_by == 200 * PT


def test_the_emergency_pass_runs_only_when_the_tolerance_pass_cannot_break_the_paragraph() -> None:
    # With no emergency stretch the second pass is already the final one, so the
    # escape fires there. With emergency stretch there is a third pass, and it is
    # the one that has to rescue an unbreakable paragraph.
    without = break_paragraph([_word(300)], ParShape.uniform(LINE))
    assert without.pass_used is BreakPass.SECOND

    with_stretch = break_paragraph(
        [_word(300)], ParShape.uniform(LINE), LineBreakParams(emergency_stretch=50 * PT)
    )
    assert with_stretch.pass_used is BreakPass.EMERGENCY
    # The line is still honestly overfull: emergency stretch influenced which
    # breaking was accepted, and was not handed to the packer.
    assert with_stretch.lines[0].fitness is PackFitness.OVERFULL


def test_the_first_pass_is_skipped_when_pretolerance_is_negative() -> None:
    # §863: `threshold := pretolerance; if threshold >= 0 then ... else` go
    # straight to the tolerance pass.
    result = break_paragraph(
        _para(SHOWCASE), ParShape.uniform(LINE), LineBreakParams(pretolerance=-1)
    )
    assert result.pass_used is BreakPass.SECOND


def test_infinite_shrink_is_made_finite_so_a_line_can_still_be_overfull() -> None:
    # §825-§826. Left alone, a fil-shrinkable space would let any line shrink to
    # anything and nothing would ever be reported overfull -- which is also why
    # the algorithm needs only one shrink register and four for stretch.
    elastic = GlueSpec(width=6 * PT, shrink=1, shrink_order=GlueOrder.FIL)
    nodes: list[Node] = [_word(90), Glue(elastic), _word(90)]
    result = break_paragraph(nodes, ParShape.uniform(50 * PT))
    assert any(line.fitness is PackFitness.OVERFULL for line in result.lines)


# --------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------


def test_characters_are_measured_through_the_injected_callable() -> None:
    def measure(char: CharNode) -> CharDimens:
        return CharDimens(width=10 * PT, height=7 * PT, depth=2 * PT)

    nodes: list[Node] = [
        CharNode("prose-16", ord("a")),
        CharNode("prose-16", ord("b")),
        Glue(SPACE),
        CharNode("prose-16", ord("c")),
        CharNode("prose-16", ord("d")),
    ]
    result = break_paragraph(nodes, ParShape.uniform(20 * PT), measure=measure)
    assert len(result.lines) == 2
    assert result.lines[0].natural == 20 * PT
    assert result.lines[0].fitness is PackFitness.EXACT


def test_fitness_classes_carry_the_source_s_numbering_because_the_formula_subtracts_them() -> None:
    # §859 charges adj_demerits when `abs(fit_class - fitness(r)) > 1`, so the
    # values are arithmetic rather than labels (§817).
    assert (Fitness.VERY_LOOSE, Fitness.LOOSE, Fitness.DECENT, Fitness.TIGHT) == (0, 1, 2, 3)
    assert abs(Fitness.TIGHT - Fitness.LOOSE) > 1
    assert abs(Fitness.DECENT - Fitness.LOOSE) == 1

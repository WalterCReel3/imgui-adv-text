r"""
Claims about the first-fit breaker, `LineBreakParams(first_fit=True)`.

`imscribe.linebreak` optimises a paragraph as a whole, and that is the point of
it. This file is about the mode beside it that does the opposite: fill a line
until the next breakpoint would overfull it, take the break, never look back.
It was built because of two measurements, both about ragged-right setting
through the optimiser (`.concerns/A0-bench--builder-2--ragged-compose-is-100x-slower.md`
and `tests/test_stream_stability.py`): it costs seconds on a long paragraph, and
one word wider than the measure re-breaks everything before it one word to a
line. The four sections below are the four things the mode was asked to do.

## What was measured (2026-10-06; `.venv/bin/python tests/test_firstfit.py` reprints it)

1. **Prefix-stable.** Every word-prefix of the 635-node paragraph of
   `demo/sample.md`, 102 breakings and 101 steps, at 150, 200, 270, 420 and
   520 pt, with the interword shrink zeroed and with it left in: **0 of 101**
   steps changed a settled line, in all ten runs. At 150 and 200 pt the
   paragraph's 253.8 pt word overflows, so those runs include the case the
   optimiser fails. Each 101-step sweep took about 0.3 s; the same sweep through
   the optimiser is about 80 s where it works at all.
2. **Cost.** One breaking of that paragraph, best of 5, same machine and run:

       | width | justified total-fit | ragged total-fit | ragged first-fit |
       | 300pt |             31.3 ms |          2533 ms |           5.5 ms |
       | 420pt |             42.2 ms |          3639 ms |           6.2 ms |
       | 800pt |             28.1 ms |          9337 ms |           9.0 ms |

   The paragraph repeated 1, 2, 4 and 8 times at 420 pt: 6.1, 12.3, 24.5 and
   49.2 ms. The assertion here counts `hpack` calls rather than milliseconds,
   because a count does not depend on what else the machine is doing.
3. **Against the optimiser, on the whole of `demo/sample.md` set `Align.LEFT`**
   (34 text blocks, each with its own shape; lines compared as `PackResult`s):

       | width | glue          | blocks differing | lines differing |
       | 300pt | shrink zeroed |          0 of 34 |        0 of 112 |
       | 420pt | shrink zeroed |          0 of 34 |         0 of 76 |
       | 800pt | shrink zeroed |          0 of 34 |         0 of 50 |
       | 300pt | as emitted    |         12 of 34 |       56 of 111 |
       | 420pt | as emitted    |         11 of 34 |        34 of 76 |
       | 800pt | as emitted    |          6 of 34 |        18 of 50 |

   So the two agree exactly when the glue cannot shrink and disagree in about a
   third of the blocks when it can. The disagreement has one cause: first-fit
   squeezes a word onto a line whenever the shrink allows it, and the optimiser,
   which is charged for a tight line, mostly declines. Neither row says which
   looks better; that is not this file's to say. No line was overfull under
   either breaker at any of the three widths. The optimiser's side of this
   table took 6.6 to 29.5 s per row and first-fit's 38 to 60 ms.

## What "the same" means

Lines are compared as `PackResult`s by value -- nodes, width, glue set, fitness
-- which is the claim a renderer needs. The box-built paragraphs use the same
round numbers as `tests/test_linebreak.py`, so every width can be added up by
hand; the font-built ones need imgui-bundle's fonts and skip without them.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

import imscribe.linebreak as linebreak
from imscribe.linebreak import (
    BreakPass,
    LineBreakParams,
    LineSpec,
    Paragraph,
    ParShape,
    break_paragraph,
)
from imscribe.markdown import TextBlock, build_document
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
from imscribe.pack import PackFitness, PackResult, hpack
from imscribe.style import Theme, char_measure, fontlib_metrics
from imscribe.units import GlueOrder, Scaled, pt_from_sp, sp_from_pt

PT = sp_from_pt(1.0)
LINE = 100 * PT

SPACE = GlueSpec(width=6 * PT, stretch=4 * PT, shrink=2 * PT)
"""
The interword glue of `tests/test_linebreak.py`: 6pt plus 4pt minus 2pt.
"""

STIFF = GlueSpec(width=6 * PT, stretch=4 * PT)
"""
The same glue with no shrink, which is what makes the optimiser's ragged answer first-fit.
"""

FIL = GlueSpec(stretch=PT, stretch_order=GlueOrder.FIL)
r"""
`0pt plus 1fil`: a `\rightskip` of this is ragged-right. `imscribe.ui.RAGGED_RIGHT` by value.
"""

SHOWCASE = (12, 19, 27, 14, 12, 13, 19, 15, 18)
"""
`tests/test_linebreak.py`'s paragraph, on which greedy and optimal are known to differ.
"""

FIRST_FIT = LineBreakParams(first_fit=True)

RAGGED = LineBreakParams(
    right_skip=FIL, hyphen_penalty=0, double_hyphen_demerits=0, final_hyphen_demerits=0
)
"""
Ragged-right for the optimiser, with every charge that is not "one more line" removed.

The comparisons below need the optimiser to be indifferent between lines that
fit, so that its tie-break (§855, the later break wins) is the only thing
choosing -- and a discretionary break is otherwise charged its penalty squared
and the hyphen demerits. First-fit reads none of these fields.
"""

RAGGED_FIRST_FIT = replace(RAGGED, first_fit=True)

DEMO = Path(__file__).resolve().parent.parent / "demo"

_PARAGRAPH_NODES = 635
_WIDE_WORD = "W" * 60
_SHORT_WORDS = tuple(f"word{index}" for index in range(20))


# --------------------------------------------------------------------------
# Building paragraphs
# --------------------------------------------------------------------------


def _word(points: int) -> Box:
    """
    A stand-in for a set word: a box of known width, with no contents to measure.
    """
    return Box(kind=BoxKind.HLIST, width=points * PT, height=7 * PT, depth=2 * PT)


def _para(widths: Sequence[int], space: GlueSpec = SPACE) -> list[Node]:
    """
    Words separated by interword glue.
    """
    out: list[Node] = []
    for index, width in enumerate(widths):
        if index:
            out.append(Glue(space))
        out.append(_word(width))
    return out


def _widths(result: Paragraph) -> list[list[int]]:
    """
    The word boxes on each line, as whole-point widths.
    """
    return [
        [node.width // PT for node in line.box.contents if isinstance(node, Box)]
        for line in result.lines
    ]


def _greedy(widths: Sequence[int], line: int, *, shrink: int) -> list[list[int]]:
    """
    First-fit written out by hand over integers, sharing nothing with the breaker.

    A word joins the line while the line's natural width less its total shrink
    is within the measure. `shrink` is per space, in points.
    """
    lines: list[list[int]] = [[]]
    for width in widths:
        trial = [*lines[-1], width]
        if lines[-1] and sum(trial) + (6 - shrink) * (len(trial) - 1) > line:
            lines.append([width])
        else:
            lines[-1] = trial
    return lines


@cache
def _material(source: str) -> tuple[Node, ...]:
    """
    The horizontal material of the largest text block in a markdown source.
    """
    document = build_document(source, Theme.build(), fontlib_metrics)
    blocks = [block for block in document.blocks if isinstance(block, TextBlock)]
    return max(blocks, key=lambda block: len(block.material)).material


def _without_shrink(nodes: Sequence[Node]) -> tuple[Node, ...]:
    """
    The same material with every glue's shrink set to zero.
    """
    return tuple(
        replace(node, spec=replace(node.spec, shrink=0)) if isinstance(node, Glue) else node
        for node in nodes
    )


def _word_prefixes(nodes: Sequence[Node]) -> list[tuple[Node, ...]]:
    """
    The material cut before each interword glue, then whole: one entry per word count.
    """
    cuts = [index for index, node in enumerate(nodes) if isinstance(node, Glue)]
    return [tuple(nodes[:cut]) for cut in (*cuts, len(nodes))]


def _text(line: PackResult) -> str:
    """
    A line as the words on it, for a failure message a person can read.
    """
    out: list[str] = []
    for node in line.box.contents:
        if isinstance(node, CharNode):
            out.append(chr(node.codepoint))
        elif isinstance(node, Glue) and node.spec.width:
            out.append(" ")
    return "".join(out).strip()


def _set(nodes: Sequence[Node], width: Scaled, params: LineBreakParams) -> tuple[PackResult, ...]:
    """
    Break font-built material at one width.
    """
    return break_paragraph(
        nodes, ParShape.uniform(width), params, measure=char_measure(fontlib_metrics)
    ).lines


def _flips(
    nodes: Sequence[Node], width: Scaled, params: LineBreakParams
) -> tuple[list[tuple[int, tuple[str, ...], tuple[str, ...]]], int, int]:
    """
    Break every word-prefix; report each step at which an already-settled line changed.

    Returns the flips (words in the shorter prefix, its lines, the longer one's
    lines), the number of steps compared and the most lines any prefix had. The
    last two let a caller refuse a vacuous pass: no flips over no steps, or over
    prefixes that never had a second line, is not a result.

    "Settled" is every line but the last of the shorter prefix: the last is the
    one being written.
    """
    flips: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []
    most = 0
    before: tuple[PackResult, ...] | None = None
    prefixes = _word_prefixes(nodes)
    for count, prefix in enumerate(prefixes, start=1):
        after = _set(prefix, width, params)
        most = max(most, len(after))
        if before is not None and before[:-1] != after[: len(before) - 1]:
            flips.append(
                (count - 1, tuple(_text(x) for x in before), tuple(_text(x) for x in after))
            )
        before = after
    return flips, len(prefixes) - 1, most


@pytest.fixture(scope="module")
def paragraph(bundled_fonts: Path) -> tuple[Node, ...]:
    """
    The 635-node paragraph of `demo/sample.md`, with its size checked.
    """
    nodes = _material((DEMO / "sample.md").read_text(encoding="utf-8"))
    assert len(nodes) == _PARAGRAPH_NODES, (
        f"demo/sample.md's largest paragraph is {len(nodes)} nodes, not {_PARAGRAPH_NODES}; "
        "the figures in this file's docstring are about a different paragraph"
    )
    assert len(_word_prefixes(nodes)) == 102
    return nodes


def _ragged_prose(*, first_fit: bool) -> LineBreakParams:
    """
    What `imscribe.ui._skips` hands the breaker for `Align.LEFT`, with the mode chosen.

    Built from `imscribe.ui`'s own constants, imported here and not at the top so
    that the box-built half of this file opens neither a font nor the UI package.
    """
    from imscribe.ui import PROSE_BREAKING, RAGGED_RIGHT

    return replace(
        PROSE_BREAKING, left_skip=GlueSpec(), right_skip=RAGGED_RIGHT, first_fit=first_fit
    )


# --------------------------------------------------------------------------
# The mode, and that it is off unless asked for
# --------------------------------------------------------------------------


def test_first_fit_is_off_by_default_and_a_first_fit_paragraph_says_what_it_is() -> None:
    """
    The default is the optimiser; a first-fit result cannot be mistaken for one of its passes.
    """
    assert LineBreakParams().first_fit is False

    optimal = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE))
    greedy = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), FIRST_FIT)

    assert optimal.pass_used is BreakPass.FIRST
    assert optimal.total_demerits > 0
    assert greedy.pass_used is BreakPass.FIRST_FIT
    assert greedy.total_demerits == 0


def test_it_is_the_greedy_breaking_and_not_the_optimal_one() -> None:
    """
    On the paragraph where the two are known to differ, this is the greedy one.

    12+19+27+14+12 with four spaces is 108pt natural, and four spaces have
    exactly 8pt of shrink between them: the fifth word fits a 100pt line with
    nothing to spare. Greedy takes it, using every scrap of shrink the line has;
    the optimiser (`tests/test_linebreak.py`) leaves it for line two so that
    neither line has to work that hard.
    """
    greedy = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE), FIRST_FIT)
    optimal = break_paragraph(_para(SHOWCASE), ParShape.uniform(LINE))

    assert _widths(greedy) == _greedy(SHOWCASE, 100, shrink=2)
    assert _widths(greedy) == [[12, 19, 27, 14, 12], [13, 19, 15, 18]]
    assert _widths(optimal) == [[12, 19, 27, 14], [12, 13, 19, 15, 18]]
    assert _widths(greedy) != _widths(optimal)


def test_a_line_fits_if_its_shrink_can_reach_the_measure_and_not_otherwise() -> None:
    """
    "Fits" is the packer's verdict, so shrink is used -- and a caller can take it away.

    30+30+30 with two spaces is 102pt natural. With 2pt of shrink per space it
    packs to 100pt, tight; with none it does not fit and the third word moves
    down. This is the whole of the difference from the optimiser's ragged answer
    reported in the module docstring.
    """
    words = (30, 30, 30)

    squeezed = break_paragraph(_para(words, SPACE), ParShape.uniform(LINE), RAGGED_FIRST_FIT)
    stiff = break_paragraph(_para(words, STIFF), ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    assert _widths(squeezed) == [[30, 30, 30]]
    assert _widths(stiff) == [[30, 30], [30]]
    assert not any(line.fitness is PackFitness.OVERFULL for line in (*squeezed.lines, *stiff.lines))


# --------------------------------------------------------------------------
# 1. Settled lines stay settled
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shrink", [False, True], ids=["shrink-zeroed", "normal-glue"])
@pytest.mark.parametrize("width_pt", [150.0, 200.0, 270.0, 420.0])
def test_no_settled_line_changes_as_the_paragraph_arrives_a_word_at_a_time(
    paragraph: tuple[Node, ...], width_pt: float, shrink: bool
) -> None:
    """
    Every word-prefix of the 635-node paragraph: 102 breakings, 101 steps, no line moves.

    All of them and not a sample, because first-fit is cheap enough that there
    is no reason to sample. At 150 and 200 pt the paragraph's own 253.8 pt word
    is wider than the line, so half of these runs are the over-wide case, on
    text nobody contrived. With the shrink left in it still holds: a squeezed
    line is decided by the material up to its end like any other.
    """
    nodes = paragraph if shrink else _without_shrink(paragraph)
    width = sp_from_pt(width_pt)

    flips, steps, most = _flips(nodes, width, _ragged_prose(first_fit=True))

    assert steps == 101
    assert most >= 8, f"only {most} lines were ever set"
    assert not flips, (
        f"{len(flips)} of {steps} steps changed a settled line at {width_pt} pt; first after "
        f"word {flips[0][0]}:\n  before: {flips[0][1]}\n  after:  {flips[0][2]}"
    )


def test_the_detector_reports_a_flip_when_there_is_one(bundled_fonts: Path) -> None:
    """
    The same `_flips`, pointed at the optimiser on the case it is known to fail.

    Without this, "no flips" above could be a detector that never fires. The
    paragraph is `tests/test_stream_stability.py`'s counterexample; if the
    optimiser is ever changed so that it no longer flips here, this fails and
    should be given a different known-bad input rather than deleted.
    """
    nodes = _without_shrink(_material(" ".join([*_SHORT_WORDS, _WIDE_WORD, "four", "five"])))

    flips, _, _ = _flips(nodes, sp_from_pt(420.0), _ragged_prose(first_fit=False))

    assert [flip[0] for flip in flips] == [len(_SHORT_WORDS)]


def test_a_word_wider_than_the_measure_gets_its_own_line_and_disturbs_none_before_it(
    bundled_fonts: Path,
) -> None:
    """
    The over-wide word mid-paragraph: alone, overfull, and nothing above it moved.

    Twenty short words are two lines at 420 pt. With the wide word and two more
    after it there are four: the same two, the word, and the rest. The first
    line is identical as a `PackResult` to what it was before the word arrived;
    the second has the same words (it was the last line then, ending in
    `\\parfillskip`, and is not now, so it is not the same box and is not
    claimed to be).
    """
    width = sp_from_pt(420.0)
    params = _ragged_prose(first_fit=True)
    short = _without_shrink(_material(" ".join(_SHORT_WORDS)))
    whole = _without_shrink(_material(" ".join([*_SHORT_WORDS, _WIDE_WORD, "four", "five"])))

    before = _set(short, width, params)
    after = _set(whole, width, params)
    flips, steps, _ = _flips(whole, width, params)

    assert len(before) == 2
    assert [_text(line) for line in after] == [
        *(_text(line) for line in before),
        _WIDE_WORD,
        "four five",
    ]
    assert after[0] == before[0]
    assert [line.fitness is PackFitness.OVERFULL for line in after] == [False, False, True, False]
    assert steps == len(_SHORT_WORDS) + 2
    assert not flips


def test_the_sample_paragraphs_own_wide_word_is_the_only_overfull_line(
    paragraph: tuple[Node, ...],
) -> None:
    """
    At 200 pt: one overfull line, holding `sixty-five-...-thirty-sixth` and nothing else.
    """
    lines = _set(_without_shrink(paragraph), sp_from_pt(200.0), _ragged_prose(first_fit=True))

    overfull = [line for line in lines if line.fitness is PackFitness.OVERFULL]
    assert len(overfull) == 1
    assert len(_text(overfull[0]).split()) == 1
    assert _text(overfull[0]).startswith("sixty-five-thousand")
    assert pt_from_sp(overfull[0].natural) > 200.0


def test_a_wide_word_first_and_a_wide_word_last_are_each_one_line() -> None:
    """
    The two ends, in boxes: nothing to break at before the first, nothing after the last.

    No empty line appears on either side of the overfull one, which is the
    mistake a "break before the word that does not fit" filler makes when the
    line it is on is already empty.
    """
    first = break_paragraph(_para((300, 20, 20), STIFF), ParShape.uniform(LINE), RAGGED_FIRST_FIT)
    last = break_paragraph(_para((20, 20, 300), STIFF), ParShape.uniform(LINE), RAGGED_FIRST_FIT)
    alone = break_paragraph([_word(300)], ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    assert _widths(first) == [[300], [20, 20]]
    assert _widths(last) == [[20, 20], [300]]
    assert _widths(alone) == [[300]]
    assert first.lines[0].overfull_by == 200 * PT
    assert last.lines[1].overfull_by == 200 * PT
    assert alone.lines[0].overfull_by == 200 * PT


# --------------------------------------------------------------------------
# 2. Cost
# --------------------------------------------------------------------------


def _counting(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """
    Count the breaker's `hpack` calls; returns a function that reads and resets the count.
    """
    calls = [0]

    def counted(*args: object, **kwargs: object) -> PackResult:
        calls[0] += 1
        return hpack(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(linebreak, "hpack", counted)

    def read() -> int:
        count, calls[0] = calls[0], 0
        return count

    return read


def test_the_cost_is_one_pack_per_breakpoint_plus_two_per_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Counted, not timed: breakpoints, plus a re-look and a final pack for each line.

    Forty words at 100pt. There are 39 interword breakpoints and the paragraph's
    end, so 40 candidates; each line but the last costs one more look at the
    candidate that did not fit, and every line is packed once more for output.
    The bound is therefore `40 + (lines - 1) + lines`, and it is met exactly.
    """
    read = _counting(monkeypatch)
    words = (SHOWCASE * 5)[:40]

    result = break_paragraph(_para(words, STIFF), ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    lines = len(result.lines)
    assert lines > 5
    assert read() == 40 + (lines - 1) + lines


def test_the_cost_grows_in_proportion_to_the_paragraph_and_the_optimisers_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Eight times the words is eight times the packs, to within the line count's rounding.

    The optimiser's ragged count on the same paragraphs is beside it, because
    "linear" is only worth asserting next to the thing that is not: there the
    count grows faster than the paragraph does. Sizes are small so that the
    optimiser's half of this stays under a second.
    """
    read = _counting(monkeypatch)
    shape = ParShape.uniform(LINE)
    small = (SHOWCASE * 3)[:20]
    large = small * 8

    break_paragraph(_para(small, STIFF), shape, RAGGED_FIRST_FIT)
    first_small = read()
    break_paragraph(_para(large, STIFF), shape, RAGGED_FIRST_FIT)
    first_large = read()
    break_paragraph(_para(small, STIFF), shape, RAGGED)
    total_small = read()
    break_paragraph(_para(small * 2, STIFF), shape, RAGGED)
    total_double = read()

    assert first_small > 20
    assert 8 * first_small - 16 <= first_large <= 8 * first_small + 16
    assert total_double > 3 * total_small, (total_small, total_double)
    assert total_small > 4 * first_small, (total_small, first_small)


# --------------------------------------------------------------------------
# 3. Shapes, hard breaks and what is discarded at a break
# --------------------------------------------------------------------------


def _formula() -> list[Node]:
    """
    Two words, a formula with a space inside it, two more words.
    """
    return [
        _word(30),
        Glue(STIFF),
        _word(30),
        Glue(STIFF),
        MathOn(),
        _word(20),
        Glue(STIFF),
        _word(20),
        MathOff(),
        Glue(STIFF),
        _word(30),
        Glue(STIFF),
        _word(30),
    ]


def _kerned(kind: KernKind) -> list[Node]:
    """
    Three words, with a 2pt kern of the given kind before the first space.
    """
    return [_word(40), Kern(2 * PT, kind), Glue(STIFF), _word(40), Glue(STIFF), _word(40)]


def _hyphenated(replace_count: int) -> list[Node]:
    """
    `40 30-30 40`, where the hyphen is a discretionary that may replace the node after it.
    """
    disc = Disc(pre_break=(_word(2),), post_break=(_word(3),), replace_count=replace_count)
    return [_word(40), Glue(STIFF), _word(30), disc, _word(30), Glue(STIFF), _word(40)]


def _adjacent_breakpoints() -> list[Node]:
    """
    Two words with three legal breakpoints between them and nothing else.
    """
    return [
        _word(60),
        Glue(STIFF),
        Penalty(0),
        Kern(3 * PT, KernKind.EXPLICIT),
        Glue(STIFF),
        _word(60),
    ]


def _with_penalty(value: int, at_word: int) -> list[Node]:
    """
    `SHOWCASE` with a penalty before the glue that precedes word `at_word`.
    """
    nodes = _para(SHOWCASE, STIFF)
    nodes.insert(2 * at_word - 1, Penalty(value))
    return nodes


_AGREEMENT: list[tuple[str, list[Node], ParShape, LineBreakParams]] = [
    ("uniform", _para(SHOWCASE, STIFF), ParShape.uniform(LINE), RAGGED),
    ("narrow", _para(SHOWCASE, STIFF), ParShape.uniform(45 * PT), RAGGED),
    ("hanging", _para(SHOWCASE, STIFF), ParShape.hanging(LINE, 12 * PT), RAGGED),
    ("indented", _para(SHOWCASE, STIFF), ParShape.uniform(80 * PT, 20 * PT), RAGGED),
    (
        "parshape",
        _para(SHOWCASE * 2, STIFF),
        ParShape((LineSpec(40 * PT, 5 * PT), LineSpec(70 * PT), LineSpec(55 * PT, 9 * PT))),
        RAGGED,
    ),
    ("forced", _with_penalty(EJECT_PENALTY, 2), ParShape.uniform(LINE), RAGGED),
    ("adjacent-breakpoints", _adjacent_breakpoints(), ParShape.uniform(LINE), RAGGED),
    ("inhibited", _with_penalty(INF_PENALTY, 4), ParShape.uniform(LINE), RAGGED),
    ("formula", _formula(), ParShape.uniform(LINE), RAGGED),
    ("explicit-kern", _kerned(KernKind.EXPLICIT), ParShape.uniform(90 * PT), RAGGED),
    ("font-kern", _kerned(KernKind.NORMAL), ParShape.uniform(90 * PT), RAGGED),
    ("discretionary", _hyphenated(0), ParShape.uniform(80 * PT), RAGGED),
    ("discretionary-replacing", _hyphenated(1), ParShape.uniform(80 * PT), RAGGED),
    ("centred", _para(SHOWCASE, STIFF), ParShape.uniform(LINE), replace(RAGGED, left_skip=FIL)),
    (
        "trailing-space",
        [*_para(SHOWCASE, STIFF), Glue(STIFF)],
        ParShape.uniform(LINE),
        RAGGED,
    ),
]


@pytest.mark.parametrize(
    ("nodes", "shape", "params"),
    [case[1:] for case in _AGREEMENT],
    ids=[case[0] for case in _AGREEMENT],
)
def test_every_line_is_the_line_the_optimiser_builds_from_the_same_breaks(
    nodes: list[Node], shape: ParShape, params: LineBreakParams
) -> None:
    """
    Shapes, forced and inhibited breaks, kerns, formulas, discretionaries: the same breaks.

    Each case is set ragged with no shrink and no charge but the line count, so
    the optimiser's choice is first-fit's (the module docstring's table is the
    same statement about real text).

    **What this can detect is a difference in which breakpoints are chosen, and
    nothing else.** The lines are compared whole, as `PackResult`s, but both
    breakers hand their chosen breaks to the same `_assemble`, which builds each
    line with the same `_line_nodes` and the same `hpack` from the same
    `_breakpoints`. Given equal breaks, equal lines follow by construction: the
    nodes kept and dropped at each end, the width and the `shift_amount` are one
    piece of code agreeing with itself. So this test says first-fit *chooses* as
    the optimiser does on these fifteen inputs -- including that its trial pack
    measures each line against that line's own `LineSpec` -- and it would not
    notice a mistake in how a line is built, because the optimiser would make
    the same one. (An earlier wording claimed that second thing. The reviewer
    read it as more than the test holds; the shared path was checked in
    `imscribe/linebreak.py` and it is.)

    Whether a line is built *correctly* is what the tests after this one are
    for: they state the right answer by hand for the cases worth spelling out.
    """
    optimal = break_paragraph(nodes, shape, params)
    greedy = break_paragraph(nodes, shape, replace(params, first_fit=True))

    assert len(greedy.lines) >= 2, "one line has no break in it to compare"
    assert not any(line.fitness is PackFitness.OVERFULL for line in optimal.lines)
    assert greedy.lines == optimal.lines


def test_each_line_is_measured_against_its_own_width_and_shifted_by_its_own_indent() -> None:
    """
    A three-entry shape: 40pt, 70pt, then 55pt for every line after.

    Greedy by hand: `12 19` is 37 (a third word would be 70); `27 14 12` is 65
    (a fourth, 84); then 55pt lines of `13 19 15` at 59 -- too wide -- so
    `13 19`, `15 18`. The widths and shifts are the shape's, line by line, with
    the last entry repeating (§847).
    """
    shape = ParShape((LineSpec(40 * PT, 5 * PT), LineSpec(70 * PT), LineSpec(55 * PT, 9 * PT)))

    result = break_paragraph(_para(SHOWCASE, STIFF), shape, RAGGED_FIRST_FIT)

    assert _widths(result) == [[12, 19], [27, 14, 12], [13, 19], [15, 18]]
    assert [line.box.width // PT for line in result.lines] == [40, 70, 55, 55]
    assert [line.box.shift_amount // PT for line in result.lines] == [5, 0, 9, 9]


def test_a_hanging_indent_narrows_and_shifts_every_line_after_the_first() -> None:
    """
    The shape a list item is set in, and the reason this mode must honour shapes at all.
    """
    result = break_paragraph(
        _para(SHOWCASE, STIFF), ParShape.hanging(LINE, 30 * PT), RAGGED_FIRST_FIT
    )

    assert _widths(result) == [
        _greedy(SHOWCASE, 100, shrink=0)[0],
        *_greedy(SHOWCASE[4:], 70, shrink=0),
    ]
    assert len(result.lines) == 3
    assert [line.box.width // PT for line in result.lines] == [100, 70, 70]
    assert [line.box.shift_amount // PT for line in result.lines] == [0, 30, 30]


def test_a_forced_break_is_taken_where_it_stands_however_short_that_leaves_the_line() -> None:
    """
    `\\penalty-10000` after the second word: two words on line one, with room for four.
    """
    result = break_paragraph(_with_penalty(EJECT_PENALTY, 2), ParShape.uniform(LINE), FIRST_FIT)

    assert _widths(result)[0] == [12, 19]
    assert _widths(result) == [[12, 19], *_greedy(SHOWCASE[2:], 100, shrink=0)]


def test_a_forced_break_past_the_end_of_the_line_breaks_before_it_as_well() -> None:
    """
    The forced break is the candidate that does not fit: the line breaks, then it does.

    `40 40 40` then a forced break, at 100pt. The third word does not fit, so
    the line ends after the second, and the forced break still ends the short
    line holding the third -- it is not swallowed by the break before it.
    """
    nodes: list[Node] = [*_para((40, 40, 40), STIFF), Penalty(EJECT_PENALTY), Glue(STIFF)]
    nodes.extend(_para((10, 10), STIFF))

    result = break_paragraph(nodes, ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    assert _widths(result) == [[40, 40], [40], [10, 10]]


def test_an_infinite_penalty_keeps_two_words_together_even_when_that_overfulls() -> None:
    """
    §831: no break at `\\penalty10000`, nor at the glue after it (§868).

    `60 60` cannot share a 100pt line. Tied, they must, and the line is overfull
    by the 26pt it says it is; untied, they are two lines.
    """
    tied: list[Node] = [_word(60), Penalty(INF_PENALTY), Glue(STIFF), _word(60)]
    loose: list[Node] = [_word(60), Glue(STIFF), _word(60)]

    together = break_paragraph(tied, ParShape.uniform(LINE), RAGGED_FIRST_FIT)
    apart = break_paragraph(loose, ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    assert _widths(together) == [[60, 60]]
    assert together.lines[0].overfull_by == 26 * PT
    assert _widths(apart) == [[60], [60]]


def test_a_penalty_between_the_infinities_is_a_breakpoint_whatever_its_value() -> None:
    """
    What this mode does *not* honour, pinned so it is a decision and not a surprise.

    The optimiser adds a positive penalty's square to the cost of breaking there
    and will break somewhere cheaper if it can. First-fit has no cost to add it
    to: a `\\penalty9999` is a place a line may end, exactly like `\\penalty0`.

    `40 <space> 40 <penalty> 40` at 100pt has **two** places line one may end,
    and both leave two lines that fit: the space (`40 | 40 40`, free) and the
    penalty (`40 40 | 40`, charged). First-fit takes the later one whatever the
    charge, because it is the last that fits. A breaker that weighed the value
    would take the space when the penalty is positive -- and the last three
    lines show the optimiser doing exactly that on the same nodes, which is what
    makes the loop above them an assertion and not a tautology. The paragraph
    this test used before had the penalty as its only breakpoint, so every
    breaker conceivable gave the same answer and it could not fail.
    """
    for value in (0, 50, 9999, -50):
        nodes: list[Node] = [_word(40), Glue(STIFF), _word(40), Penalty(value), _word(40)]
        result = break_paragraph(nodes, ParShape.uniform(LINE), RAGGED_FIRST_FIT)
        assert _widths(result) == [[40, 40], [40]], value

    discouraged: list[Node] = [_word(40), Glue(STIFF), _word(40), Penalty(9999), _word(40)]
    weighed = break_paragraph(discouraged, ParShape.uniform(LINE), RAGGED)
    assert _widths(weighed) == [[40], [40, 40]], "the control: the optimiser must avoid it"


def test_the_glue_a_line_breaks_at_is_dropped_and_so_is_whatever_discardable_follows() -> None:
    """
    §879: the next line starts at its first word, not at a space, a penalty or an explicit kern.

    The only legal break is the first glue: the kern is not followed by glue,
    the penalty is infinite, and the glue after a penalty is not a breakpoint.
    So everything between that glue and the second word is at the start of line
    two, and all of it goes.
    """
    nodes: list[Node] = [
        _word(60),
        Glue(STIFF),
        Kern(3 * PT, KernKind.EXPLICIT),
        Penalty(INF_PENALTY),
        Glue(STIFF),
        _word(60),
    ]

    result = break_paragraph(nodes, ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    first, second = result.lines
    assert first.box.contents == (_word(60), Glue(FIL))
    assert second.box.contents[0] == _word(60)
    assert second.natural == 60 * PT


def test_of_several_breakpoints_with_no_word_between_them_the_last_that_fits_is_taken() -> None:
    """
    Glue, then a penalty, then an explicit kern before more glue: three places to end one line.

    All three fit, so the line ends at the last of them and keeps what stood
    before it -- the space and the penalty stay on line one, and its natural
    width is 66pt, not 60. Found by a test that expected otherwise. It is the
    choice the optimiser makes too (§855: of equal breaks the later wins; this
    case is in `_AGREEMENT`), and set ragged-right it cannot be seen, because the
    extra is at the ragged end. **Set centred or ragged-left it is a line that
    sits a space off**, which is true of the optimiser's answer as well and is
    recorded here rather than fixed in one breaker and not the other.
    """
    result = break_paragraph(_adjacent_breakpoints(), ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    first, second = result.lines
    assert first.box.contents == (
        _word(60),
        Glue(STIFF),
        Penalty(0),
        Kern(0, KernKind.EXPLICIT),
        Glue(FIL),
    )
    assert first.natural == 66 * PT
    assert second.box.contents[0] == _word(60)


def test_a_font_kern_at_the_start_of_a_line_is_kept() -> None:
    """
    §837: "Kern nodes do not disappear at a line break unless they are explicit".
    """
    nodes: list[Node] = [_word(60), Glue(STIFF), Kern(2 * PT, KernKind.NORMAL), _word(60)]

    result = break_paragraph(nodes, ParShape.uniform(LINE), RAGGED_FIRST_FIT)

    assert result.lines[1].box.contents[0] == Kern(2 * PT, KernKind.NORMAL)
    assert result.lines[1].natural == 62 * PT


def test_an_explicit_kern_before_glue_is_a_breakpoint_and_loses_its_width_there() -> None:
    """
    §866's `kern_break` and §881's `width(q) := 0`, reached greedily.

    40+2+6+40 is 88pt and fits 90pt; a third word does not. So the first line
    keeps its kern at full width, mid-line. At 40pt each word is alone, the
    break is *at* the kern, and the kern is still there with no width.
    """
    wide = break_paragraph(_kerned(KernKind.EXPLICIT), ParShape.uniform(90 * PT), RAGGED_FIRST_FIT)
    tight = break_paragraph(_kerned(KernKind.EXPLICIT), ParShape.uniform(40 * PT), RAGGED_FIRST_FIT)

    assert _widths(wide) == [[40, 40], [40]]
    assert wide.lines[0].box.contents[1] == Kern(2 * PT, KernKind.EXPLICIT)
    assert _widths(tight) == [[40], [40], [40]]
    assert tight.lines[0].box.contents == (
        _word(40),
        Kern(0, KernKind.EXPLICIT),
        Glue(FIL),
    )
    assert not any(line.fitness is PackFitness.OVERFULL for line in tight.lines)


def test_glue_inside_a_formula_is_not_a_breakpoint() -> None:
    """
    A formula is not split by the spaces inside it, even to avoid an overfull line.

    50pt, then a formula of `10 10` with a space, at a 60pt measure. Breaking
    inside the formula would give lines that fit; the legal breaks do not, so
    the formula goes down whole.
    """
    nodes: list[Node] = [
        _word(50),
        Glue(STIFF),
        MathOn(),
        _word(40),
        Glue(STIFF),
        _word(40),
        MathOff(),
        Glue(STIFF),
        _word(50),
    ]

    result = break_paragraph(nodes, ParShape.uniform(60 * PT), RAGGED_FIRST_FIT)

    assert _widths(result) == [[50], [40, 40], [50]]
    assert result.lines[1].overfull_by == 26 * PT


def test_a_discretionary_break_takes_its_pre_break_text_and_leaves_its_post_break_text() -> None:
    """
    `40 30-30 40` at 80pt: the hyphen ends line one and the replacement starts line two.

    With `replace_count=1` the 30pt node after the discretionary is consumed by
    the break and the 3pt post-break text stands in for it; untaken, at 200pt,
    the discretionary contributes nothing and the replaced node is still there.
    """
    broken = break_paragraph(_hyphenated(1), ParShape.uniform(80 * PT), RAGGED_FIRST_FIT)
    whole = break_paragraph(_hyphenated(1), ParShape.uniform(200 * PT), RAGGED_FIRST_FIT)

    assert _widths(broken) == [[40, 30, 2], [3, 40]]
    assert _widths(whole) == [[40, 30, 30, 40]]


def test_a_discretionary_whose_penalty_is_infinite_is_not_a_breakpoint() -> None:
    """
    `\\hyphenpenalty=10000` turns hyphenation off for the optimiser, and for this.
    """
    params = replace(RAGGED_FIRST_FIT, hyphen_penalty=INF_PENALTY)

    result = break_paragraph(_hyphenated(0), ParShape.uniform(80 * PT), params)

    assert _widths(result) == [[40], [30, 30], [40]]


# --------------------------------------------------------------------------
# 4. Against the optimiser, on the sample document
# --------------------------------------------------------------------------

_COMPARED_NODES = 260
"""
The largest block the default suite hands to the *optimiser* set ragged.

Cost again: ragged total-fit is seconds on a long paragraph, and the whole
document at 420 pt is over ten. Blocks up to this size are most of the document
by count and about two seconds together. The whole document's figures are in
the module docstring and `_report` reproduces them.
"""


def _sample_blocks() -> list[TextBlock]:
    """
    Every top-level text block of `demo/sample.md`, in order.
    """
    source = (DEMO / "sample.md").read_text(encoding="utf-8")
    document = build_document(source, Theme.build(), fontlib_metrics)
    return [block for block in document.blocks if isinstance(block, TextBlock)]


def _compare(
    blocks: Sequence[TextBlock], width: Scaled, *, shrink: bool
) -> tuple[int, int, int, float, float]:
    """
    Break each block ragged both ways: blocks differing, lines differing, lines, and seconds.

    Each block gets the shape `imscribe.ui` would give it at this width, so list
    items are compared in their hanging shape and not as bare paragraphs. A
    differing line is one position at which the two breakings hold different
    `PackResult`s, plus any difference in line count.
    """
    from imscribe.ui import _shape

    measure = char_measure(fontlib_metrics)
    differing_blocks = differing_lines = lines = 0
    optimal_s = greedy_s = 0.0
    for block in blocks:
        material = block.material if shrink else _without_shrink(block.material)
        shape = _shape(block, width)
        began = time.perf_counter()
        optimal = break_paragraph(
            material, shape, _ragged_prose(first_fit=False), measure=measure
        ).lines
        optimal_s += time.perf_counter() - began
        began = time.perf_counter()
        greedy = break_paragraph(
            material, shape, _ragged_prose(first_fit=True), measure=measure
        ).lines
        greedy_s += time.perf_counter() - began
        lines += len(optimal)
        if optimal != greedy:
            differing_blocks += 1
            differing_lines += sum(a != b for a, b in zip(optimal, greedy, strict=False))
            differing_lines += abs(len(optimal) - len(greedy))
    return differing_blocks, differing_lines, lines, optimal_s, greedy_s


def test_on_the_sample_document_it_matches_the_optimiser_when_the_glue_cannot_shrink(
    bundled_fonts: Path,
) -> None:
    """
    `demo/sample.md` set `Align.LEFT`, shrink zeroed: the same lines, block for block.

    Over the blocks of up to `_COMPARED_NODES` nodes; the whole document gave 0
    of 34 at three widths when this was written (module docstring).
    """
    blocks = [block for block in _sample_blocks() if len(block.material) <= _COMPARED_NODES]
    assert len(blocks) >= 20

    differing_blocks, differing_lines, lines, _, _ = _compare(
        blocks, sp_from_pt(420.0), shrink=False
    )

    assert lines > len(blocks), "nothing here ran to a second line"
    assert (differing_blocks, differing_lines) == (0, 0)


def test_on_the_sample_document_it_does_not_match_the_optimiser_with_the_glue_as_emitted(
    bundled_fonts: Path,
) -> None:
    """
    The same comparison with the shrink left in: they differ, and this says so out loud.

    Asserted as "differs", not as a count, because the count belongs to the
    sample and the theme and will move with either. The point being pinned is
    the one a reader of `first_fit` most needs: **switching `Align.LEFT` to
    first-fit is not a no-op unless the block's glue has no shrink.** Whoever
    makes that switch should read the module docstring's table first.
    """
    blocks = [block for block in _sample_blocks() if len(block.material) <= _COMPARED_NODES]

    differing_blocks, differing_lines, _, _, _ = _compare(blocks, sp_from_pt(420.0), shrink=True)

    assert differing_blocks > 0
    assert differing_lines > 0


# --------------------------------------------------------------------------
# The measurement run
# --------------------------------------------------------------------------


def _best(repeat: int, work: Callable[[], object]) -> float:
    """
    The fastest of `repeat` runs, in milliseconds.
    """
    best = float("inf")
    for _ in range(repeat):
        began = time.perf_counter()
        work()
        best = min(best, time.perf_counter() - began)
    return best * 1000


def _report() -> None:
    """
    Reprint the module docstring's three tables. Not a test; about two minutes.
    """
    from imscribe.ui import PROSE_BREAKING

    paragraph = _material((DEMO / "sample.md").read_text(encoding="utf-8"))
    measure = char_measure(fontlib_metrics)
    greedy = _ragged_prose(first_fit=True)
    print(f"{len(paragraph)} nodes, {len(_word_prefixes(paragraph))} word-prefixes")

    print("\nprefix stability, first-fit ragged\nmeasure  glue           flips/steps  lines  sweep")
    for width_pt in (150.0, 200.0, 270.0, 420.0, 520.0):
        for label, nodes in (
            ("shrink zeroed", _without_shrink(paragraph)),
            ("as emitted", paragraph),
        ):
            began = time.perf_counter()
            flips, steps, most = _flips(nodes, sp_from_pt(width_pt), greedy)
            print(
                f"{width_pt:5.0f} pt  {label:<14} {len(flips):3d}/{steps}  {most:5d}"
                f"  {time.perf_counter() - began:5.2f} s",
                flush=True,
            )

    print("\none breaking of the paragraph\nwidth  justified  ragged total-fit  ragged first-fit")
    for width_pt in (300.0, 420.0, 800.0):
        shape = ParShape.uniform(sp_from_pt(width_pt))
        justified = _best(
            5, lambda s=shape: break_paragraph(paragraph, s, PROSE_BREAKING, measure=measure)
        )
        slow = _best(
            1,
            lambda s=shape: break_paragraph(
                paragraph, s, _ragged_prose(first_fit=False), measure=measure
            ),
        )
        fast = _best(5, lambda s=shape: break_paragraph(paragraph, s, greedy, measure=measure))
        print(f"{width_pt:5.0f}  {justified:7.2f} ms  {slow:13.1f} ms  {fast:13.2f} ms", flush=True)

    print("\nthe paragraph repeated, first-fit at 420 pt")
    space = next(node for node in paragraph if isinstance(node, Glue))
    for copies in (1, 2, 4, 8):
        nodes: list[Node] = []
        for index in range(copies):
            if index:
                nodes.append(space)
            nodes.extend(paragraph)
        shape = ParShape.uniform(sp_from_pt(420.0))
        took = _best(3, lambda n=nodes, s=shape: break_paragraph(n, s, greedy, measure=measure))
        print(f"x{copies}  {len(nodes):5d} nodes  {took:6.2f} ms")

    print("\ndemo/sample.md, Align.LEFT, first-fit against total-fit")
    print("width  glue           blocks     lines      total-fit  first-fit")
    blocks = _sample_blocks()
    for width_pt in (300.0, 420.0, 800.0):
        for label, shrink in (("shrink zeroed", False), ("as emitted", True)):
            differing_blocks, differing_lines, lines, optimal_s, greedy_s = _compare(
                blocks, sp_from_pt(width_pt), shrink=shrink
            )
            print(
                f"{width_pt:5.0f}  {label:<14} {differing_blocks:2d} of {len(blocks)}"
                f"  {differing_lines:3d} of {lines:3d}  {optimal_s:7.2f} s"
                f"  {greedy_s * 1000:6.1f} ms",
                flush=True,
            )


if __name__ == "__main__":
    _report()

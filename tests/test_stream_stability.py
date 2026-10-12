r"""
Whether lines that have been set stay set while the paragraph is still arriving.

`docs/adoption-plan.md` phase 7 streams text into a *live block*: a paragraph
that grows a word at a time and is re-broken on every change. A reader is
looking at it while that happens, so the property that matters is not that each
re-break is good but that it **agrees with the last one** -- every line except
the one being written must be exactly where it was a word ago. This file asks
whether `imscribe.linebreak.break_paragraph`, unchanged, has that property.

**The plan's argument, which this file exists to test rather than to repeat.**
Set the block ragged (`right_skip=RAGGED_RIGHT`) and take the shrink out of the
interword glue. Every line that fits then ends in infinitely stretchable glue,
so §852 scores it badness 0 and every line costs the same `line_penalty²`. The
total is then 100 x the number of lines, total-fit degenerates to "fewest
lines", and `_Breaker._try_break`'s `d <= best_demerits[fit]` -- §855's "a
later break with equal demerits wins" -- picks, among the fewest-line breakings,
the one whose every line is as full as it can be. That is first-fit, and
first-fit never revisits a finished line. The plan calls this "a paper proof
about tie-breaking" and names the emergency pass as where it could fail.

## What was found (2026-10-06, measured; commands at the bottom)

1. **Where every word fits its line, the proof holds.** Over all 102
   word-prefixes of the 635-node paragraph of `demo/sample.md`, ragged with
   shrink zeroed: **0 of 101** steps changed a settled line, at each of 270,
   330, 420 and 520 pt under `PROSE_BREAKING`, and at 420 pt under
   `LineBreakParams()`.
2. **Where a word is wider than its line, it fails, and badly.** Twenty short
   words that set as two lines, followed by an over-wide word, come back as
   twenty one-word lines and the wide word: the damage reaches back to the
   start of the paragraph, not to the start of the line.
   `test_the_counterexample_is_exactly_this` pins it and
   `test_a_word_wider_than_the_measure_does_not_disturb_settled_lines` is the
   property, marked `xfail(strict=True)`.

   That much is observed. **The cause is read from the code and was not
   instrumented:** §854's last-resort break is taken from "the only active node
   left", `_try_break` walks the active list in line-number order, and with
   `easy_line` dropped (the module docstring of `imscribe.linebreak` says why it
   was) the last node standing is the one with the highest line number -- the
   chain that put every preceding word on a line of its own. The output is what
   that reading predicts, and the prediction was made before the run.

   It is not an artefact of zeroing the shrink, nor of either parameter set: it
   reproduces ragged with normal glue, under plain TeX's defaults (where the
   second pass is the final one) and under `PROSE_BREAKING` (where the emergency
   pass is). The same input set justified kept its words together. And it is
   not exotic: the sample paragraph itself contains
   `sixty-five-thousand-five-hundred-and-thirty-sixth`, 253.8 pt wide, so the
   paragraph the plan chose trips it below that (measured at 150 and 200 pt:
   the 12 words before it go from 2 or 3 lines to one each); a URL or a file
   path in model output is the same shape.
3. **Normal glue, counted rather than asserted.** Steps out of 101 that changed
   a settled line, all 102 prefixes, `PROSE_BREAKING`:

       | measure | ragged, shrink zeroed | ragged, normal glue | justified |
       | 270 pt  |                     0 |                  16 |         1 |
       | 330 pt  |                     0 |                   2 |         0 |
       | 420 pt  |                     0 |                   0 |         0 |
       | 520 pt  |                     0 |                   6 |         1 |

   So the shrink does flip settled lines, at a rate that depends on the measure
   and is zero at the one the litmus page uses. The justified column was not
   asked for and is there because the run was cheap; nothing asserts any of the
   three. Below 253.8 pt every column also contains finding 2.
4. **Not asked for, and it decides more than the stability does: ragged
   breaking is slow.** One breaking of the whole 635-node paragraph, ragged:
   1.6 s at 270 pt, 2.3 s at 330 pt, 2.6 to 3.3 s at 420 pt, 4.3 to 6.1 s at
   520 pt; justified, 15 to 52 ms. Single runs on a machine other agents were
   using, so read the ratio and not the digits. `scripts/bench_reflow.py`
   (`--ragged`) found the same thing independently the same day. The likely
   cause is the one in finding 2 -- with every line feasible, a break position
   stays reachable under every line count from the fewest up to one word per
   line, and nothing merges those classes -- and it is equally uninstrumented.
   This is why most of this file runs on the first 45 words; see
   `_DEFAULT_WORDS`.

**So the plan's "if it passes, the live block needs no change to
`linebreak.py`" does not follow.** It passes only when no word overflows, and
it costs seconds per re-break at paragraph length. Per the task, `linebreak.py`
was not edited; `.concerns/A7-stable--builder--result.md` carries the options.

## What "unchanged" means here

Lines are compared as `PackResult`s, by value: the same nodes, the same width,
the same glue set, the same fitness. That is stricter than "the same words" and
it is the claim a renderer needs, since a settled line that kept its words and
moved its glyphs has still moved.

A *word-prefix* is the material cut at an interword `Glue`: everything before
the *k*-th space. The paragraph is parsed once and cut as nodes, deliberately --
re-parsing a truncated source would mix the parser's behaviour on an unclosed
emphasis run into a question about the breaker.

## Reproducing the numbers

    .venv/bin/python tests/test_stream_stability.py            # the table, ~15 min
    IMSCRIBE_SLOW=1 .venv/bin/python -m pytest tests/test_stream_stability.py -q

The first is `_report` at the bottom of this file. The second runs the
whole-paragraph assertion that the default suite skips for cost (about 80 s for
one measure).
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

import pytest

from imscribe.linebreak import BreakPass, LineBreakParams, ParShape, break_paragraph
from imscribe.markdown import TextBlock, build_document
from imscribe.nodes import CharNode, Glue, GlueSpec, Node, Penalty
from imscribe.pack import PackFitness, PackResult, hpack
from imscribe.style import Theme, char_measure, fontlib_metrics
from imscribe.ui import PROSE_BREAKING, RAGGED_RIGHT
from imscribe.units import Scaled, pt_from_sp, sp_from_pt

DEMO = Path(__file__).resolve().parent.parent / "demo"

_PARAGRAPH_NODES = 635
"""
The size of the paragraph the plan names, checked rather than trusted.

`tests/test_bench_numbers.py` pins that it is the last block and the largest;
this pins the count, because "every word-prefix of the 635-node paragraph" is a
claim about a specific paragraph and a different one would be a different test.
"""

_DEFAULT_WORDS = 45
"""
How many word-prefixes the default suite breaks, and why it is not all 102.

Cost, measured: every prefix up to 45 words at 420 pt is about 4 s; up to 60 is
about 13 s; all 102 is about 80 s. It grows roughly as the cube because one
ragged break grows roughly as the square (finding 4 in the module docstring).
45 words is three settled lines at 420 pt and five at 270 pt. The whole
paragraph is `test_the_whole_paragraph_is_prefix_stable`, behind
`IMSCRIBE_SLOW=1`, and was run when this was written.
"""

_WIDE_WORD = "W" * 60
"""
A word wider than any measure used here (about 568 pt in the body face).
"""

_SHORT_WORDS = tuple(f"word{index}" for index in range(20))
"""
Twenty words that set as two lines at 420 pt, so that one of them is settled.
"""

_COUNTEREXAMPLE = " ".join([*_SHORT_WORDS, _WIDE_WORD, "four", "five"])
"""
The paragraph on which a settled line changes; `test_the_counterexample_is_exactly_this`.
"""

needs_slow = pytest.mark.skipif(
    os.environ.get("IMSCRIBE_SLOW") != "1",
    reason=(
        "about 80 s: every word-prefix of the 635-node paragraph. " "Set IMSCRIBE_SLOW=1 to run it."
    ),
)


@dataclass(frozen=True, slots=True)
class Flip:
    """
    One step at which a line that was already settled came out differently.

    `words` is how many words the *shorter* prefix had. `before` and `after` are
    the lines of the two breakings as text, whole, so the counterexample can be
    read without re-running anything.
    """

    words: int
    before: tuple[str, ...]
    after: tuple[str, ...]


@cache
def _material(source: str) -> tuple[Node, ...]:
    """
    The horizontal material of the largest text block in a markdown source.
    """
    document = build_document(source, Theme.build(), fontlib_metrics)
    blocks = [block for block in document.blocks if isinstance(block, TextBlock)]
    return max(blocks, key=lambda block: len(block.material)).material


def _sample_paragraph() -> tuple[Node, ...]:
    """
    The 635-node paragraph of `demo/sample.md`.
    """
    return _material((DEMO / "sample.md").read_text(encoding="utf-8"))


def _without_shrink(nodes: Sequence[Node]) -> tuple[Node, ...]:
    """
    The same material with every glue's shrink set to zero.

    This is the half of the plan's recipe that is not a breaking parameter: the
    shrink is in the nodes `imscribe.markdown` emitted, so a live block that wants
    it gone has to rewrite its material or be built without it.
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


def _ragged(params: LineBreakParams) -> LineBreakParams:
    r"""
    The parameters with `\rightskip = 0pt plus 1fil`, as `imscribe.ui._skips` sets `Align.LEFT`.
    """
    return replace(params, left_skip=GlueSpec(), right_skip=RAGGED_RIGHT)


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


def _lines(nodes: Sequence[Node], width: Scaled, params: LineBreakParams) -> tuple[PackResult, ...]:
    return break_paragraph(
        nodes, ParShape.uniform(width), params, measure=char_measure(fontlib_metrics)
    ).lines


def _flips(
    nodes: Sequence[Node],
    width: Scaled,
    params: LineBreakParams,
    *,
    words: int | None = None,
) -> tuple[list[Flip], int, int]:
    """
    Break every word-prefix and report each step that changed a settled line.

    Returns the flips, the number of steps compared, and the most lines any
    prefix had. The last two exist so a caller can refuse a vacuous pass: zero
    flips over zero steps, or over prefixes that never reached a second line and
    so never had a settled line to disturb, is not a result.

    The comparison is `before[:-1] == after[: len(before) - 1]` on `PackResult`s.
    The last line of the shorter prefix is excluded because it is the one being
    written; everything above it is the claim.
    """
    prefixes = _word_prefixes(nodes)[:words]
    flips: list[Flip] = []
    most = 0
    before: tuple[PackResult, ...] | None = None
    for count, prefix in enumerate(prefixes, start=1):
        after = _lines(prefix, width, params)
        most = max(most, len(after))
        if before is not None and before[:-1] != after[: len(before) - 1]:
            flips.append(
                Flip(
                    words=count - 1,
                    before=tuple(_text(line) for line in before),
                    after=tuple(_text(line) for line in after),
                )
            )
        before = after
    return flips, len(prefixes) - 1, most


def _widest_word(nodes: Sequence[Node]) -> Scaled:
    """
    The natural width of the widest run between two interword glues.
    """
    measure = char_measure(fontlib_metrics)
    edges = [-1, *(i for i, node in enumerate(nodes) if isinstance(node, Glue)), len(nodes)]
    return max(
        hpack(list(nodes[a + 1 : b]), measure=measure).box.width
        for a, b in zip(edges, edges[1:], strict=False)
    )


def _first_fit(nodes: Sequence[Node], width: Scaled) -> list[int]:
    """
    Words per line under a greedy filler, written here and sharing nothing with the breaker.

    Each line takes words until the next one would make its natural width exceed
    the measure. Natural width is `hpack`'s, of the words and the glue between
    them, so kerning is counted and the glue the line would break at is not.
    """
    measure = char_measure(fontlib_metrics)
    edges = [-1, *(i for i, node in enumerate(nodes) if isinstance(node, Glue)), len(nodes)]
    spans = list(zip(edges, edges[1:], strict=False))
    counts: list[int] = []
    start = 0
    while start < len(spans):
        end = start + 1
        while end < len(spans):
            candidate = list(nodes[spans[start][0] + 1 : spans[end][1]])
            if hpack(candidate, measure=measure).box.width > width:
                break
            end += 1
        counts.append(end - start)
        start = end
    return counts


@pytest.fixture(scope="module")
def paragraph(bundled_fonts: Path) -> tuple[Node, ...]:
    return _sample_paragraph()


def test_the_sample_paragraph_is_the_one_the_plan_names(paragraph: tuple[Node, ...]) -> None:
    """
    635 nodes, 102 words, and no penalty anywhere in it.

    The last clause is load-bearing for everything below. The first-fit argument
    needs every feasible line to cost the same, and a positive `Penalty` at a
    break adds its square (§859): `\\penalty50` is 2500 against the 100 a line
    costs, so the optimiser would add a line to avoid breaking there and the
    paragraph would no longer be first-fit at all. This paragraph has none, so
    it cannot show that failure -- which is a limit on what passing here means,
    not a reassurance. `imscribe.markdown` emits `INF_PENALTY` inside inline code
    spans; that one only removes a breakpoint and is harmless.
    """
    assert len(paragraph) == _PARAGRAPH_NODES, (
        f"demo/sample.md's largest paragraph is {len(paragraph)} nodes, not {_PARAGRAPH_NODES}: "
        "the plan's paragraph has changed and the figures in this file's docstring are stale"
    )
    assert len(_word_prefixes(paragraph)) == 102
    assert not [node for node in paragraph if isinstance(node, Penalty)]
    assert any(node.spec.shrink for node in paragraph if isinstance(node, Glue)), (
        "the interword glue has no shrink to zero, so the strict run and the "
        "normal-glue run would be the same run"
    )
    assert not any(
        node.spec.shrink for node in _without_shrink(paragraph) if isinstance(node, Glue)
    )


@pytest.mark.parametrize(
    ("width_pt", "params"),
    [(270.0, PROSE_BREAKING), (420.0, PROSE_BREAKING), (270.0, LineBreakParams())],
    ids=["270pt-prose", "420pt-prose", "270pt-plain"],
)
def test_settled_lines_do_not_change_as_words_arrive(
    paragraph: tuple[Node, ...], width_pt: float, params: LineBreakParams
) -> None:
    """
    The strict property, where every word fits: ragged, shrink zeroed, no flips.

    Both measures are wider than the paragraph's widest word, and that is
    asserted rather than assumed -- 253.8 pt of
    `sixty-five-thousand-five-hundred-and-thirty-sixth` is in the first line and
    a measure below it is the *other* test in this file.

    Over the first `_DEFAULT_WORDS` words; the whole paragraph is the slow test.
    """
    width = sp_from_pt(width_pt)
    assert _widest_word(paragraph) < width, "a word overflows this measure; wrong test"

    flips, steps, most = _flips(
        _without_shrink(paragraph), width, _ragged(params), words=_DEFAULT_WORDS
    )

    assert steps == _DEFAULT_WORDS - 1
    assert most >= 4, f"only {most} lines were ever set, so almost nothing was settled to compare"
    assert not flips, (
        f"{len(flips)} of {steps} steps changed a settled line at {width_pt} pt; "
        f"the first was after word {flips[0].words}:\n"
        f"  before: {flips[0].before}\n  after:  {flips[0].after}"
    )


@pytest.mark.parametrize("width_pt", [270.0, 420.0])
def test_the_ragged_breaking_is_first_fit(paragraph: tuple[Node, ...], width_pt: float) -> None:
    """
    The reason the property above holds, checked against an independent greedy filler.

    Stability alone could be satisfied by a breaker that put one word on every
    line. This says which breaking it is: the same words per line as a filler
    that takes words until the next will not fit. If this fails while the
    stability test passes, the breaker is stable for some other reason and the
    plan's proof is about a different algorithm.
    """
    width = sp_from_pt(width_pt)
    prefix = _word_prefixes(_without_shrink(paragraph))[_DEFAULT_WORDS - 1]

    lines = _lines(prefix, width, _ragged(PROSE_BREAKING))

    assert [len(_text(line).split()) for line in lines] == _first_fit(prefix, width)
    assert all(line.fitness is not PackFitness.OVERFULL for line in lines)


@needs_slow
@pytest.mark.parametrize("width_pt", [420.0])
def test_the_whole_paragraph_is_prefix_stable(paragraph: tuple[Node, ...], width_pt: float) -> None:
    """
    Every word-prefix of the 635-node paragraph: 102 breakings, 101 steps, no flips.

    Skipped by default for cost and **run when written** (2026-10-06): 0 of 101
    at 420 pt in about 80 s. A test that is normally skipped is one nobody is
    running, so this is recorded as a measurement taken once rather than as a
    standing guard; the default-suite test above is the standing guard, over the
    first 45 words.
    """
    width = sp_from_pt(width_pt)
    flips, steps, most = _flips(_without_shrink(paragraph), width, _ragged(PROSE_BREAKING))

    assert steps == 101
    assert most >= 8
    assert not flips, f"{len(flips)} of {steps}; first after word {flips[0].words}"


def test_a_wide_word_that_opens_the_paragraph_disturbs_nothing(bundled_fonts: Path) -> None:
    """
    The one position where the over-wide word is harmless: nothing precedes it.

    Here the active list really does hold a single node when §854 fires, so the
    last-resort break is taken from the right place. Kept beside the failing
    case because it narrows the defect: it is not "overfull lines are unstable",
    it is "what stands before an overfull line is re-broken".
    """
    nodes = _without_shrink(_material(f"{_WIDE_WORD} four five six"))

    flips, steps, most = _flips(nodes, sp_from_pt(420.0), _ragged(PROSE_BREAKING))

    assert (steps, most) == (3, 2)
    assert not flips
    lines = _lines(nodes, sp_from_pt(420.0), _ragged(PROSE_BREAKING))
    assert [_text(line) for line in lines] == [_WIDE_WORD, "four five six"]
    assert lines[0].fitness is PackFitness.OVERFULL


@pytest.mark.parametrize(
    ("params", "which"),
    [(PROSE_BREAKING, BreakPass.EMERGENCY), (LineBreakParams(), BreakPass.SECOND)],
    ids=["prose", "plain"],
)
@pytest.mark.parametrize("shrink", [False, True], ids=["shrink-zeroed", "normal-glue"])
def test_the_counterexample_is_exactly_this(
    bundled_fonts: Path, params: LineBreakParams, which: BreakPass, shrink: bool
) -> None:
    """
    The failing case, pinned as it stands so it can be read without running it.

    Twenty short words set as two lines at 420 pt. Append a word wider than the
    measure and all twenty come back on a line each: 2 lines become 21. **The
    damage reaches back to the start of the paragraph, not to the start of the
    line** -- "the line before an overfull line is re-broken" would be a much
    smaller defect than this one, which is why the counterexample is not the
    three-word one.

    **This asserts the defect, on purpose, and should be deleted when the
    `xfail` below starts passing.** Until then it does two jobs. It is the
    exact counterexample the task asks to be kept. And it is the proof that
    `_flips` can report a flip at all -- without a case where it does, every
    "no flips" in this file could be a detector that never fires.

    Exactly one flip, at the wide word. The two words after it change nothing,
    because by then the one-word lines *are* the settled lines: the property is
    restored around the damage rather than the damage being repaired.

    Four variants, all identical in outcome: with and without the shrink, and
    under both parameter sets, whose *final* pass differs (the emergency pass
    for `PROSE_BREAKING`, the second for plain TeX's defaults). So the cause is
    §854's last-resort break as implemented, not `\\emergencystretch` and not
    the zeroed shrink.
    """
    nodes = _material(_COUNTEREXAMPLE)
    if not shrink:
        nodes = _without_shrink(nodes)
    width = sp_from_pt(420.0)
    assert _widest_word(nodes) > width

    flips, steps, _ = _flips(nodes, width, _ragged(params))

    assert steps == len(_SHORT_WORDS) + 2
    assert [flip.words for flip in flips] == [len(_SHORT_WORDS)]
    (flip,) = flips
    assert len(flip.before) == 2
    assert " ".join(flip.before) == " ".join(_SHORT_WORDS)
    assert flip.after == (*_SHORT_WORDS, _WIDE_WORD)

    whole = break_paragraph(
        nodes, ParShape.uniform(width), _ragged(params), measure=char_measure(fontlib_metrics)
    )
    assert whole.pass_used is which
    assert [_text(line) for line in whole.lines] == [*_SHORT_WORDS, _WIDE_WORD, "four five"]


def test_the_line_being_written_is_split_the_same_way(bundled_fonts: Path) -> None:
    """
    The three-word case: not a flip by this file's definition, and the same defect.

    `one two three` is one line; with the wide word after it, it is three. No
    *settled* line changed, because the only line there was is the one being
    written and the property under test exempts it. `_flips` therefore reports
    nothing here, correctly. It is pinned anyway because a streaming view will
    show it: the reader sees one line become three and then, had the word been
    a few characters shorter, stay one.

    Also asserts the defect; delete with the test above.
    """
    nodes = _without_shrink(_material(f"one two three {_WIDE_WORD}"))
    width = sp_from_pt(420.0)

    flips, _, _ = _flips(nodes, width, _ragged(PROSE_BREAKING))
    lines = _lines(nodes, width, _ragged(PROSE_BREAKING))

    assert not flips
    assert [_text(line) for line in lines] == ["one", "two", "three", _WIDE_WORD]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "§854's last-resort break is taken from the active node with the highest line "
        "number, which without easy_line is the one-word-per-line chain; see the module "
        "docstring, finding 2, and .concerns/A7-stable--builder--result.md"
    ),
)
@pytest.mark.parametrize("params", [PROSE_BREAKING, LineBreakParams()], ids=["prose", "plain"])
@pytest.mark.parametrize(
    ("case", "width_pt", "words"),
    [
        ("synthetic", 420.0, None),
        ("sample", 200.0, 20),
    ],
)
def test_a_word_wider_than_the_measure_does_not_disturb_settled_lines(
    bundled_fonts: Path, case: str, width_pt: float, words: int | None, params: LineBreakParams
) -> None:
    """
    The property the live block needs, in the case where it does not hold today.

    Two paragraphs. The synthetic one is the counterexample pinned above. The
    other is the plan's own paragraph at 200 pt, where its 253.8 pt word
    overflows -- included so nobody reads the synthetic `WWWW...` as a contrived
    input.

    `strict=True`: when the breaker (or whatever the live block uses instead)
    is changed so this holds, the unexpected pass fails the suite and the two
    tests above that assert the defect must go. `linebreak.py` was deliberately
    not edited to make this pass; the task says the result decides that.
    """
    width = sp_from_pt(width_pt)
    nodes = _material(_COUNTEREXAMPLE) if case == "synthetic" else _sample_paragraph()
    assert _widest_word(nodes) > width, "nothing overflows, so this is not the emergency case"

    flips, steps, _ = _flips(_without_shrink(nodes), width, _ragged(params), words=words)

    assert steps >= 5
    assert not flips, f"after word {flips[0].words}: {flips[0].before} -> {flips[0].after}"


def _report() -> None:
    """
    The measurement run: flips per measure, with the shrink zeroed and with it left in.

    Not a test. The normal-glue column is the count the task asks for, and a
    count is not an assertion; the zeroed column is here beside it so the two
    are taken on the same machine in the same run. `full` is the time of one
    breaking of the whole paragraph, which is finding 4.
    """
    paragraph = _sample_paragraph()
    print(f"{len(paragraph)} nodes, {len(_word_prefixes(paragraph))} word-prefixes")
    print(f"widest word {pt_from_sp(_widest_word(paragraph)):.1f} pt")
    print("measure  glue           flips/steps  lines  full-break  sweep")
    for width_pt in (200.0, 270.0, 330.0, 420.0, 520.0):
        width = sp_from_pt(width_pt)
        for label, nodes, params in (
            ("ragged, no shrink", _without_shrink(paragraph), _ragged(PROSE_BREAKING)),
            ("ragged, normal", paragraph, _ragged(PROSE_BREAKING)),
            ("justified", paragraph, PROSE_BREAKING),
        ):
            began = time.perf_counter()
            _lines(nodes, width, params)
            once = time.perf_counter() - began
            began = time.perf_counter()
            flips, steps, most = _flips(nodes, width, params)
            sweep = time.perf_counter() - began
            print(
                f"{width_pt:5.0f} pt  {label:<18} {len(flips):3d}/{steps}  {most:5d}"
                f"  {once * 1000:8.1f} ms  {sweep:6.1f} s",
                flush=True,
            )


if __name__ == "__main__":
    _report()

r"""
Total-fit line breaking: choosing the breakpoints that make the whole paragraph best.

A greedy filler decides each line in turn and never looks back, so a bad break
on line four is paid for by line four. This optimises the paragraph: every legal
breakpoint is scored, breaks that could still lead somewhere are kept active,
and the winner is the chain of breaks with the fewest total demerits. Loosening
line two to rescue line four is a move only this algorithm can make, and it is
the whole visible difference between TeX's output and a word processor's.

**Demerits, not badness.** Badness says how hard one line had to stretch.
Demerits (§859) is `(line_penalty + badness)²`, plus the square of any penalty at
the break, plus `adj_demerits` when two adjacent lines differ by more than one
fitness class. That last term is why a tight line never sits next to a loose one:
it is not that either line is bad, it is that the *transition* is. Squaring is
what makes one terrible line cost more than several mediocre ones.

**Every candidate line is evaluated by `hpack`.** Not by a private copy of the
glue arithmetic. The breaker asks the packer "what would this line be like?" and
reads the badness and the order off the `PackResult`. That costs a `Box` per
candidate and it buys the property that the line the breaker scored and the line
the packer emits cannot disagree -- a class of bug that otherwise shows up as
"the output does not match what the algorithm said it chose".

**Deliberately absent, each for a reason:**

- **Hyphenation.** `docs/decisions.md` puts it out of scope: the full
  implementation is roughly a thousand lines and contains TeX's worst
  interaction, ligature reconstruction across a break (§915-§916). What TeX
  calls the second pass is implemented here as *the same pass at a looser
  tolerance* with no hyphenation attempted. The `Disc` machinery is complete, so
  a caller that builds discretionaries by hand -- a compound word's existing
  hyphen, for instance -- gets them broken correctly. This is absent, not
  forgotten.
- **Delta nodes.** `docs/decisions.md` again. They are a 1982 optimisation that
  maintains `active_width` incrementally through a linked list of differences,
  and they are where the subtle bugs live. Here each candidate line is measured
  by re-walking the node list, which is O(n·k) instead of O(n) and is free at
  paragraph sizes. If profiling ever says otherwise, that is a later problem and
  a contained one, because the re-walk is a single function.
- **`easy_line`** (§848, §850), the optimisation that merges all active nodes
  whose line numbers are past the last specially-shaped line into one
  equivalence class. Dropping it keeps *more* candidates alive, never fewer, so
  it cannot change which breaking is optimal -- only how many active nodes are
  carried. Same trade as the delta nodes.
- **`\looseness`** (§875), which asks for a paragraph one line longer or shorter
  than optimal. It is a second optimisation pass over the finished active list
  and nothing in this project's litmus tests needs it.
- **Club, widow, broken and interline penalties** (§890). Those are appended
  *between* lines in the enclosing vertical list, which is the vertical
  builder's job -- this returns lines, not a vlist. Naming them here and putting
  them somewhere else would be worse than leaving them to their owner.

**Infinite shrink is made finite before breaking starts**, exactly as §825-§826
do it, which is why the active state carries four stretch registers and only one
for shrink. A paragraph containing `\hskip 0pt minus 1fil` would otherwise have
a line that can shrink without limit, and no line would ever be overfull.

**There is also a first-fit breaker here, and it is the opposite algorithm on
purpose.** `LineBreakParams.first_fit` selects it; it is off by default and
nothing above changes when it is off. It fills each line until the next legal
breakpoint would overfull it and never looks back -- the "greedy filler" of the
first paragraph. It exists for three callers that total-fit serves badly, all
of them ragged: a paragraph that is still arriving (a line the reader has seen
must not move when a word is appended, and first-fit decides a line from the
material up to its end and nothing after), wrapped table cells, and ragged
monospace body text. The reasons are measured, not argued (2026-10-06,
`tests/test_firstfit.py` and `.concerns/A7-greedy--builder--result.md`):

- Ragged-right is a `\rightskip` of `fil`, which makes every line that fits
  cost the same. With `easy_line` absent, the active list then carries a node
  for every line count a position can be reached in, and the 635-node paragraph
  of `demo/sample.md` takes seconds where justified takes tens of milliseconds.
- §854's last-resort break is taken from the active node with the highest line
  number, which under those conditions is the chain that put every earlier word
  on its own line: one over-wide word re-breaks the paragraph back to its start
  (`tests/test_stream_stability.py` pins that).

First-fit has neither problem by construction, and it shares `_breakpoints`,
`_line_nodes` and `hpack` with the optimiser, so what is a legal break, what is
discarded after one and whether a line fits are the same three answers in both.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import Final

from imscribe.badness import INF_BAD
from imscribe.nodes import (
    EJECT_PENALTY,
    INF_PENALTY,
    Box,
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
    Rule,
    permits_break_at_following_glue,
)
from imscribe.pack import CharMeasure, PackFitness, PackMode, PackResult, hpack
from imscribe.units import GlueOrder, Scaled

__all__ = [
    "AWFUL_BAD",
    "BreakPass",
    "Fitness",
    "LineSpec",
    "LineBreakParams",
    "ParShape",
    "Paragraph",
    "break_paragraph",
]

AWFUL_BAD: Final = (1 << 30) - 1
"""
"More than a billion demerits" -- TeX's `@d awful_bad == @'7777777777` (§833).

The initial value of every demerit accumulator, so that the first real candidate
always improves on it. It is deliberately far above any reachable demerit total:
the worst a single line can contribute is 10^8 from the saturated squaring in
§859, so a paragraph would need ten lines at the absolute worst to approach it.
"""

_SATURATED_DEMERITS: Final = 100_000_000
"""
What `(line_penalty + badness)²` becomes when the sum reaches 10000 (§859).

**Replaced, not clamped.** The source is `if abs(d)>=10000 then d:=100000000
else d:=d*d`, and 10000² is exactly 10^8, so this is the value the squaring
would have produced at the boundary. Writing it as a clamp on `d*d` would be the
same number here and a different one for larger `d`, which is the sort of
"equivalent" rewrite that is not.
"""


class Fitness(enum.IntEnum):
    """
    How a line was set, in the four classes §817 defines.

    An `IntEnum` because the values are arithmetic: §859 charges `adj_demerits`
    when `abs(fit_class - fitness(r)) > 1`, so the *distance* between two classes
    is what the formula uses, and the ordering from very loose through decent to
    tight is what makes that distance mean "how different did these two lines
    look". The numbers are the source's.

    There is no "very tight". Stretch is unbounded, so a line can stretch past
    everything it has; shrink is bounded, and once a line needs more shrink than
    exists it is overfull rather than merely tight.
    """

    VERY_LOOSE = 0
    LOOSE = 1
    DECENT = 2
    TIGHT = 3


class BreakPass(enum.Enum):
    """
    Which of the passes produced the paragraph, which is worth reporting.

    `FIRST` means the paragraph broke within `pretolerance` and is the good case.
    `SECOND` means it needed the looser `tolerance` -- in TeX this is also the
    pass that hyphenates, and here it does not (see the module docstring), so the
    distinction is only the threshold. `EMERGENCY` means even that failed and
    `emergency_stretch` had to be added to every line's stretchability to find
    any breaking at all; lines from that pass are genuinely underfull and a
    caller that cares should look at each `PackResult`.

    `FIRST_FIT` is none of the three: `LineBreakParams.first_fit` was set and
    the optimiser did not run at all. It is a member here rather than a second
    field on `Paragraph` so that a caller asking "how was this broken" has one
    place to look, and so that no first-fit paragraph can be mistaken for one
    that passed at `pretolerance`.
    """

    FIRST = enum.auto()
    SECOND = enum.auto()
    EMERGENCY = enum.auto()
    FIRST_FIT = enum.auto()


class _BreakKind(enum.Enum):
    """
    What sort of node a break happened at, which decides how the line ends.

    §881 treats each differently: glue at the break *becomes* the `\\rightskip`,
    a discretionary contributes its pre-break text and sets `disc_break`, a math
    or kern node stays with its width zeroed, and a penalty stays as it is.
    """

    GLUE = enum.auto()
    PENALTY = enum.auto()
    KERN = enum.auto()
    MATH = enum.auto()
    DISC = enum.auto()
    PARAGRAPH_END = enum.auto()


@dataclass(frozen=True, slots=True)
class LineSpec:
    """
    The width available to one line, and how far it is indented from the left.

    `indent` becomes the line box's `shift_amount` in the enclosing vertical
    list (§889), which moves it right. It is not glue: a hanging indent must not
    stretch, and expressing it as a shift keeps it out of the justification
    entirely.
    """

    width: Scaled
    indent: Scaled = 0


@dataclass(frozen=True, slots=True)
class ParShape:
    """
    Per-line widths, because one width per paragraph cannot express a hanging indent.

    §847: the record gives a left margin and a length for each of the first `n`
    lines, and "the specifications for line `n` apply to all subsequent lines".
    So the last entry is not just the last line's -- it is every line from there
    on, and that is what makes a two-entry shape describe a bulleted item of any
    length.

    A single width is `ParShape.uniform(...)`. It is a classmethod rather than an
    overload on the constructor so that the per-line case stays the obvious one
    at the call site.
    """

    lines: tuple[LineSpec, ...]

    def __post_init__(self) -> None:
        """
        A shape with no lines has no width to offer and would silently overfull.
        """
        if not self.lines:
            raise ValueError("a ParShape needs at least one LineSpec")

    @classmethod
    def uniform(cls, width: Scaled, indent: Scaled = 0) -> ParShape:
        """
        The same width for every line.
        """
        return cls((LineSpec(width, indent),))

    @classmethod
    def hanging(cls, width: Scaled, indent: Scaled, after: int = 1) -> ParShape:
        """
        Full width for the first `after` lines, then indented by `indent` (§849).

        This is `\\hangindent` with a non-negative `\\hangafter`, and it is the
        shape a bulleted list item wants: the marker sits in the space the first
        line gives up, and every continuation line is indented past it.
        """
        if after < 0:
            raise ValueError("negative hang_after indents the *first* lines; pass a shape instead")
        full = LineSpec(width, 0)
        return cls((*[full] * after, LineSpec(width - abs(indent), max(indent, 0))))

    def for_line(self, line: int) -> LineSpec:
        """
        The spec for line `line`, counting from 1. Past the end, the last one repeats.
        """
        return self.lines[min(line, len(self.lines)) - 1]


@dataclass(frozen=True, slots=True)
class LineBreakParams:
    """
    The knobs §236 and §247 expose, under TeX's names.

    **The defaults are `plain.tex`'s, not IniTeX's**, and that distinction
    matters for anyone checking these against the source. `tex.web` initialises
    almost every one of these to zero (§240), which would make the demerits
    formula degenerate: with `line_penalty = 0` and `adj_demerits = 0`, demerits
    reduce to badness squared and the algorithm stops caring about transitions
    between lines. The familiar values below come from `plain.tex`, which is a
    separate file and is not in `tex.web` -- so they are conventional rather
    than transcribed, and a caller who wants IniTeX behaviour should say so.

    `pretolerance` negative skips the first pass entirely (§863).

    **`first_fit` is not TeX's and switches the algorithm.** When it is set,
    `break_paragraph` fills each line greedily (see `_first_fit`) and every
    field above `left_skip` is unread: there are no demerits, so there is
    nothing for a tolerance, a line penalty or an emergency stretch to act on.
    The three skips are honoured exactly as before. It is off by default, and
    with it off this class and the breaker behave as they did before the field
    existed.
    """

    pretolerance: int = 100
    tolerance: int = 200
    line_penalty: int = 10
    adj_demerits: int = 10000
    double_hyphen_demerits: int = 10000
    final_hyphen_demerits: int = 5000
    hyphen_penalty: int = 50
    ex_hyphen_penalty: int = 50
    emergency_stretch: Scaled = 0
    left_skip: GlueSpec = GlueSpec()
    right_skip: GlueSpec = GlueSpec()
    par_fill_skip: GlueSpec = field(
        default_factory=lambda: GlueSpec(stretch=1, stretch_order=GlueOrder.FIL)
    )
    first_fit: bool = False


@dataclass(frozen=True, slots=True)
class Paragraph:
    """
    A broken paragraph: one packed line per line, and how it went.

    Each line is a `PackResult`, not a bare `Box`, for the same reason `hpack`
    returns one: an overfull line is a thing the caller has to be able to see,
    there is no terminal to print it to, and a global would be shared across two
    backends and a test suite. `boxes` is there for callers that only want the
    geometry.

    `total_demerits` is the score of the chosen breaking. It is the number the
    algorithm minimised, so it is also the only way to state the total-fit
    property as an assertion rather than as an anecdote. A first-fit paragraph
    (`pass_used is BreakPass.FIRST_FIT`) minimised nothing and reports 0, which
    is a statement that no score exists and not that the breaking is perfect.

    **`line.fitness` is a `PackFitness`, not the `Fitness` class the breaker
    used**, and the two are different questions that share a word. `PackFitness`
    is the packer's diagnostic -- `TIGHT` there means only "this shrank at all".
    `Fitness.TIGHT` means "shrank badly enough to score above 12", which is what
    §859 charges `adj_demerits` against. A line can be `PackFitness.TIGHT` and
    `Fitness.DECENT` at the same time and usually is. The breaking class is not
    surfaced because nothing downstream needs it; the demerits already contain
    it.
    """

    lines: tuple[PackResult, ...]
    total_demerits: int
    pass_used: BreakPass

    @property
    def boxes(self) -> tuple[Box, ...]:
        """
        Just the line boxes, each with its `shift_amount` already set to its indent.
        """
        return tuple(line.box for line in self.lines)


@dataclass(frozen=True, slots=True)
class _Passive:
    """
    A chosen breakpoint and the one before it: TeX's passive node (§821).

    The chain is what survives; the active nodes that built it are thrown away
    at the end of each pass. `previous` being `None` means the paragraph's
    beginning, which is not itself a break.
    """

    position: int
    kind: _BreakKind
    previous: _Passive | None


@dataclass(frozen=True, slots=True)
class _Active:
    """
    A breakpoint that could still begin a line: TeX's active node (§819).

    `line_number` is the line that *starts* here, so the paragraph's opening
    active node carries 1. `fitness` and `hyphenated` describe the line that
    *ended* here, because §859 charges for the relationship between consecutive
    lines and needs to remember what the previous one was like.
    """

    passive: _Passive | None
    line_number: int
    fitness: Fitness
    hyphenated: bool
    total_demerits: int


def _finite_shrink(spec: GlueSpec) -> GlueSpec:
    """
    Force a glue spec's shrinkability to be finite (§825, §826).

    TeX reports this as an error and rewrites the spec, and then relies on the
    result: the active state keeps four registers for stretch and one for
    shrink, which is only sound because no shrink is infinite. Silently allowing
    infinite shrink would mean no line could ever be overfull, and every break
    would look feasible.
    """
    if spec.shrink_order is GlueOrder.NORMAL:
        return spec
    return replace(spec, shrink_order=GlueOrder.NORMAL)


def _prepare(nodes: Sequence[Node], params: LineBreakParams) -> list[Node]:
    """
    §816's preamble: end the paragraph so that the last line can be filled.

    Two steps, and the order matters. A trailing glue node is *replaced* by an
    infinite penalty rather than left in place -- otherwise the space the author
    typed before the end of the paragraph would be a legal breakpoint that
    produces an empty last line. Anything else gets the penalty appended. Then
    `\\parfillskip` goes on the end, and because the infinite penalty sits
    immediately before it, that glue is never itself a breakpoint.

    `\\parfillskip` is what makes the last line short: it is infinitely
    stretchable, so the last line's glue order is `fil`, its badness is zero by
    §852, and the interword spaces stay at their natural width instead of being
    spread across a half-empty line.
    """
    body = [
        replace(node, spec=_finite_shrink(node.spec)) if isinstance(node, Glue) else node
        for node in nodes
    ]
    if body and isinstance(body[-1], Glue):
        body[-1] = Penalty(INF_PENALTY)
    else:
        body.append(Penalty(INF_PENALTY))
    body.append(Glue(params.par_fill_skip))
    return body


def _is_prunable(node: Node) -> bool:
    """
    Whether this node is discarded from the start of a line after a break (§879).

    Glue, penalties, math nodes and *explicit* kerns go. A font kern does not:
    §837 says so in as many words -- "Kern nodes do not disappear at a line break
    unless they are `explicit`" -- and it is why this is not simply
    `is_discardable`.
    """
    if isinstance(node, Kern):
        return node.kind is KernKind.EXPLICIT
    return isinstance(node, Glue | Penalty | MathOn | MathOff)


def _line_nodes(
    body: Sequence[Node],
    previous: _Passive | None,
    current: _Passive,
    params: LineBreakParams,
) -> list[Node]:
    """
    The horizontal list for the line running from one breakpoint to the next (§881).

    Both ends need care and they need different care.

    At the **start**: a discretionary's post-break text is prepended and the
    nodes it replaces are skipped, then leading discardables are pruned. Pruning
    stops at the next breakpoint so that a line is never pruned out of existence.

    At the **end**, §881's four cases. Glue at the break *becomes* the
    `\\rightskip` rather than sitting before it -- so the space the line broke at
    is the space that justifies it, and the line does not end with two glues. A
    discretionary contributes its pre-break text, which is where a hyphen would
    come from. A math or kern node keeps its place with its width zeroed, so
    `\\mathsurround` does not push the last word off the end. A penalty stays and
    occupies nothing.
    """
    out: list[Node] = []
    start = 0
    if previous is not None:
        if previous.kind is _BreakKind.DISC:
            disc = body[previous.position]
            assert isinstance(disc, Disc)
            out.extend(disc.post_break)
            start = previous.position + 1 + disc.replace_count
        else:
            start = previous.position + 1
        while start < current.position and _is_prunable(body[start]):
            start += 1

    out.extend(body[start : current.position])

    match current.kind:
        case _BreakKind.GLUE:
            out.append(Glue(params.right_skip))
        case _BreakKind.DISC:
            disc = body[current.position]
            assert isinstance(disc, Disc)
            out.extend(disc.pre_break)
            out.append(Glue(params.right_skip))
        case _BreakKind.KERN | _BreakKind.MATH:
            broken = body[current.position]
            assert isinstance(broken, Kern | MathOn | MathOff)
            out.append(replace(broken, width=0))
            out.append(Glue(params.right_skip))
        case _BreakKind.PENALTY:
            out.append(body[current.position])
            out.append(Glue(params.right_skip))
        case _BreakKind.PARAGRAPH_END:
            out.append(Glue(params.right_skip))

    if params.left_skip != GlueSpec():
        out.insert(0, Glue(params.left_skip))
    return out


def _classify(result: PackResult) -> tuple[int, Fitness]:
    """
    Turn a packed candidate line into §851-§853's badness and fitness class.

    The three cases are the source's, read off a `PackResult` instead of off the
    six-element `cur_active_width` array:

    - **Infinite stretch** (§852) is badness 0 and decent, whatever the numbers
      say. A line ending in `\\parfillskip` is the usual one, and it is why the
      last line of a paragraph is never reported as underfull.
    - **Stretching finitely**: `b > 99` is very loose, `b > 12` is loose, the
      rest decent. Those thresholds are calibrated against the exact integers
      `imscribe.badness` returns -- 12 is half the available stretch and 100 is
      all of it -- which is why that function may not be "simplified".
    - **Shrinking**: `b > 12` is tight and there is nothing worse. A line that
      needs more shrink than exists gets `inf_bad + 1` (§853), one past the
      largest feasible badness, which is what forces its active node to be
      deactivated rather than merely skipped.

    §852 also guards `shortfall > 7230584` with `cur_active_width[2] < 1663497`
    to avoid a 32-bit overflow. That guard is redundant here and is deliberately
    not reproduced: `badness` already returns `inf_bad` for exactly those inputs,
    and Python integers do not overflow, so writing it out would be a branch
    that can never change an answer.
    """
    if result.excess > 0:
        if result.box.glue_order is not GlueOrder.NORMAL:
            return 0, Fitness.DECENT
        how_bad = result.badness
        if how_bad > 99:
            return how_bad, Fitness.VERY_LOOSE
        if how_bad > 12:
            return how_bad, Fitness.LOOSE
        return how_bad, Fitness.DECENT
    if result.fitness is PackFitness.OVERFULL:
        return INF_BAD + 1, Fitness.TIGHT
    how_bad = result.badness
    return how_bad, (Fitness.TIGHT if how_bad > 12 else Fitness.DECENT)


@dataclass(slots=True)
class _Breaker:
    """
    One pass of the algorithm over one paragraph.

    Mutable and short-lived on purpose: the active list is the state the
    algorithm is *about*, and threading it through a pure function would mean
    returning it from every call for no gain. The paragraph, the shape and the
    parameters it reads are all immutable, so nothing outside this object
    changes while it runs.
    """

    body: Sequence[Node]
    shape: ParShape
    params: LineBreakParams
    threshold: int
    extra_stretch: Scaled
    final_pass: bool
    measure: CharMeasure | None
    active: list[_Active] = field(default_factory=list)

    def _evaluate(self, previous: _Passive | None, current: _Passive, line: int) -> PackResult:
        """
        Pack the candidate line from `previous` to `current` to its target width.

        `extra_stretch` is `\\emergencystretch`, which §863 adds to the
        *background* on the final pass. It is added here, where it can change
        which breaks look feasible, and **not** when the chosen lines are packed
        for real -- so an emergency paragraph's lines come out honestly
        underfull rather than pretending the extra stretch existed.
        """
        nodes = _line_nodes(self.body, previous, current, self.params)
        if self.extra_stretch > 0:
            nodes.append(Glue(GlueSpec(stretch=self.extra_stretch)))
        width = self.shape.for_line(line).width
        return hpack(nodes, width, PackMode.EXACTLY, measure=self.measure)

    def _demerits(
        self,
        how_bad: int,
        penalty: int,
        hyphenated: bool,
        at_end: bool,
        fit: Fitness,
        previous: _Active,
    ) -> int:
        """
        §859, transcribed. The sign convention on the penalty term is the trap.

        A **positive** penalty adds its square: breaking here is discouraged. A
        **negative** one subtracts its square: breaking here is rewarded, which
        is how `\\penalty-50` before a heading pulls a break towards itself. A
        penalty of exactly `eject_penalty` contributes **nothing at all** -- the
        source's guard is `else if pi>eject_penalty`, which excludes -10000
        precisely, because a forced break is not a choice and charging or
        crediting it would distort every total it appears in.
        """
        d = self.params.line_penalty + how_bad
        d = _SATURATED_DEMERITS if abs(d) >= 10000 else d * d
        if penalty > 0:
            d += penalty * penalty
        elif EJECT_PENALTY < penalty < 0:
            d -= penalty * penalty
        if hyphenated and previous.hyphenated:
            d += self.params.final_hyphen_demerits if at_end else self.params.double_hyphen_demerits
        if abs(fit - previous.fitness) > 1:
            d += self.params.adj_demerits
        return d

    def _try_break(self, penalty: int, hyphenated: bool, position: int, kind: _BreakKind) -> None:
        """
        Score a breakpoint against every active node, then replace the active list (§829).

        §831's clamp first: a penalty of `inf_penalty` or more inhibits the
        break entirely, and anything at or below `eject_penalty` is normalised
        to `eject_penalty` so that the "forced" test downstream is an equality.

        Active nodes are processed in **groups sharing a line number**, because
        the new node created from a group inherits `line_number + 1` and that
        decides which `LineSpec` the *next* line is measured against. Merging
        two groups would silently measure one of them against the wrong width.
        """
        if abs(penalty) >= INF_PENALTY:
            if penalty > 0:
                return
            penalty = EJECT_PENALTY

        at_end = kind is _BreakKind.PARAGRAPH_END
        ordered = sorted(self.active, key=lambda a: a.line_number)
        survivors: list[_Active] = []
        created: list[_Active] = []

        index = 0
        while index < len(ordered):
            line = ordered[index].line_number
            group_end = index
            while group_end < len(ordered) and ordered[group_end].line_number == line:
                group_end += 1

            best_demerits: dict[Fitness, int] = dict.fromkeys(Fitness, AWFUL_BAD)
            best_place: dict[Fitness, _Passive | None] = {}
            minimum = AWFUL_BAD

            for position_in_list in range(index, group_end):
                r = ordered[position_in_list]
                result = self._evaluate(r.passive, _Passive(position, kind, r.passive), line)
                how_bad, fit = _classify(result)

                forced = penalty == EJECT_PENALTY
                artificial = False
                if how_bad > INF_BAD or forced:
                    # §854. The last resort: on the final pass, if this is the
                    # only active node left and nothing feasible has been found,
                    # break here for free rather than leave the paragraph with
                    # no breaking at all. Overfull output beats no output.
                    alone = not survivors and not created and position_in_list == len(ordered) - 1
                    if self.final_pass and minimum == AWFUL_BAD and alone:
                        artificial = True
                    elif how_bad > self.threshold:
                        continue
                    stays_active = False
                else:
                    if how_bad > self.threshold:
                        survivors.append(r)
                        continue
                    stays_active = True

                d = (
                    0
                    if artificial
                    else self._demerits(how_bad, penalty, hyphenated, at_end, fit, r)
                )
                d += r.total_demerits
                # §855 uses `<=`, so a later break with equal demerits wins.
                if d <= best_demerits[fit]:
                    best_demerits[fit] = d
                    best_place[fit] = r.passive
                    minimum = min(minimum, d)
                if stays_active:
                    survivors.append(r)

            if minimum < AWFUL_BAD:
                # §836: a new active node whose demerits already exceed the best
                # found plus the worst adjacency charge can never win, so it is
                # not worth carrying.
                limit = (
                    AWFUL_BAD - 1
                    if abs(self.params.adj_demerits) >= AWFUL_BAD - minimum
                    else minimum + abs(self.params.adj_demerits)
                )
                for fit, demerits in best_demerits.items():
                    if demerits <= limit:
                        created.append(
                            _Active(
                                passive=_Passive(position, kind, best_place[fit]),
                                line_number=line + 1,
                                fitness=fit,
                                hyphenated=hyphenated,
                                total_demerits=demerits,
                            )
                        )
            index = group_end

        self.active = survivors + created

    def run(self) -> _Active | None:
        """
        Scan the paragraph, offering every legal breakpoint, and return the winner.

        `None` means this pass failed: the active list emptied before the end,
        so no chain of breakpoints within `threshold` reaches the paragraph's
        end and the caller should try a looser pass.

        Which positions are legal is `_breakpoints`'s business, shared with
        the first-fit breaker.
        """
        self.active = [
            _Active(
                passive=None,
                line_number=1,
                fitness=Fitness.DECENT,
                hyphenated=False,
                total_demerits=0,
            )
        ]
        for penalty, hyphenated, position, kind in _breakpoints(self.body, self.params):
            if not self.active:
                return None
            self._try_break(penalty, hyphenated, position, kind)
        if not self.active:
            return None
        return min(self.active, key=lambda a: a.total_demerits)


def _followed_by_glue(body: Sequence[Node], index: int) -> bool:
    """
    §866's `kern_break`: a kern or math node breaks only if glue comes next.
    """
    return index + 1 < len(body) and isinstance(body[index + 1], Glue)


def _breakpoints(
    body: Sequence[Node], params: LineBreakParams
) -> Iterator[tuple[int, bool, int, _BreakKind]]:
    """
    Every legal breakpoint of a prepared paragraph, in order: §866, and then §873.

    Yields `(penalty, hyphenated, position, kind)`, which are `_try_break`'s
    arguments, and ends with the paragraph's own end at `len(body)`. One
    function because there are two breakers and "where may a line end" must not
    be a question they can answer differently.

    The legality rules are §866's, and the one that is easy to get wrong is
    `auto_breaking`. It is switched **off** at a `MathOn` and back on at a
    `MathOff`, so glue inside a formula is never a breakpoint -- a formula
    is not allowed to be split across lines by the spaces inside it.

    A penalty is yielded whatever its value. §831's clamp -- `inf_penalty`
    inhibits, `eject_penalty` or below forces -- belongs to whoever takes the
    break, because the two breakers do different things with a value in between.
    """
    auto_breaking = True
    # §863: `prev_p := cur_p` before the loop, so glue in the very first
    # position sees itself as its predecessor and is not a breakpoint.
    previous_index = 0
    index = 0
    while index < len(body):
        node = body[index]
        match node:
            case Glue():
                if auto_breaking and permits_break_at_following_glue(body[previous_index]):
                    yield 0, False, index, _BreakKind.GLUE
            case Kern():
                if (
                    node.kind is KernKind.EXPLICIT
                    and auto_breaking
                    and _followed_by_glue(body, index)
                ):
                    yield 0, False, index, _BreakKind.KERN
            case MathOn() | MathOff():
                auto_breaking = isinstance(node, MathOff)
                if auto_breaking and _followed_by_glue(body, index):
                    yield 0, False, index, _BreakKind.MATH
            case Penalty():
                yield node.value, False, index, _BreakKind.PENALTY
            case Disc():
                charge = params.hyphen_penalty if node.pre_break else params.ex_hyphen_penalty
                yield charge, True, index, _BreakKind.DISC
                previous_index = index
                index += 1 + node.replace_count
                continue
            case CharNode() | Box() | Rule():
                pass
        previous_index = index
        index += 1

    # §873. The end of a paragraph is a forced break, and counts as
    # hyphenated so that `final_hyphen_demerits` can be charged.
    yield EJECT_PENALTY, True, len(body), _BreakKind.PARAGRAPH_END


def _first_fit(
    body: Sequence[Node],
    shape: ParShape,
    params: LineBreakParams,
    measure: CharMeasure | None,
) -> list[_Passive]:
    """
    Choose breaks greedily: fill each line until the next breakpoint would overfull it.

    The rule, whole. Walk the legal breakpoints in order, remembering the latest
    one at which the line so far **fits** (`fit`). At each breakpoint:

    - the line from the current start to here fits: remember it, and if the
      break is forced, take it;
    - it does not fit and there is a remembered one: take the remembered one,
      then look at this breakpoint again from the new start;
    - it does not fit and nothing is remembered: take it anyway. That is a word
      wider than its line, set alone and overfull -- the same "a paragraph
      always produces lines" §854 is for, reached without an active list.

    **"Fits" is `hpack`'s verdict, not a width comparison**: the line is packed
    to its `LineSpec` width and fits unless the result is `OVERFULL`. So
    whatever shrink the material carries is used, exactly as the optimiser
    would use it, and a caller that wants no line squeezed gives its glue no
    shrink. Nothing here knows which alignment is being set; with no
    `right_skip` this is a word processor's justification.

    **Why a finished line never changes when material is appended.** A line is
    taken at the first breakpoint past it that does not fit (or at a forced
    break), and both that test and the line itself read only the nodes up to
    that breakpoint. The one case that looks like an exception is the
    paragraph's end, which is not a breakpoint of the longer paragraph -- but
    `_prepare` puts only an infinite penalty and a zero-width `\\parfillskip`
    there, so a line that overflows at the end overflows by the same amount at
    the interword glue that replaces it. The last line itself does change, and
    must: it ends in `\\parfillskip` until it is no longer last.

    **What is not honoured, because there is nothing to honour it with.** A
    penalty strictly between the two infinities is a legal breakpoint and its
    value is ignored: discouraging or rewarding a break needs a cost to add it
    to. `inf_penalty` still inhibits and `eject_penalty` still forces (§831).
    A discretionary's charge is read only for that same inhibition.

    **Cost.** One `hpack` per breakpoint, plus one per line for the re-look, each
    over one line's nodes: linear in the paragraph at a given measure, where the
    optimiser is linear in the paragraph *times its active list*.
    """
    breaks: list[_Passive] = []
    start: _Passive | None = None
    fit: _Passive | None = None
    line = 1

    def fits(candidate: _Passive) -> bool:
        nodes = _line_nodes(body, start, candidate, params)
        packed = hpack(nodes, shape.for_line(line).width, PackMode.EXACTLY, measure=measure)
        return packed.fitness is not PackFitness.OVERFULL

    for penalty, _, position, kind in _breakpoints(body, params):
        if penalty >= INF_PENALTY:
            continue
        forced = penalty <= EJECT_PENALTY
        candidate = _Passive(position, kind, start)
        room = fits(candidate)
        if not room and fit is not None:
            breaks.append(fit)
            start, fit, line = fit, None, line + 1
            candidate = _Passive(position, kind, start)
            room = fits(candidate)
        if forced or not room:
            breaks.append(candidate)
            start, fit, line = candidate, None, line + 1
        else:
            fit = candidate
    return breaks


def _chain(winner: _Active) -> list[_Passive]:
    """
    Walk a winning active node's passive chain back to the paragraph's start.
    """
    breaks: list[_Passive] = []
    node = winner.passive
    while node is not None:
        breaks.append(node)
        node = node.previous
    breaks.reverse()
    return breaks


def break_paragraph(
    nodes: Sequence[Node],
    shape: ParShape,
    params: LineBreakParams | None = None,
    *,
    measure: CharMeasure | None = None,
) -> Paragraph:
    """
    Break a horizontal list into justified lines, optimising the whole paragraph.

    `shape` carries a width **per line**, not one width for the paragraph, which
    is what `\\parshape` and `\\hangindent` are for and what makes a hanging
    bullet work: line one is narrower and offset, the rest are not. Each line's
    indent arrives as its box's `shift_amount`.

    Up to three passes (§863), stopping at the first that succeeds:

    1. `pretolerance`. Skipped entirely when it is negative.
    2. `tolerance`, which is looser. In TeX this is also where hyphenation
       happens; here it does not, for the reason in the module docstring.
    3. Only if `emergency_stretch` is positive: the same threshold with that
       much extra stretchability granted to every line, plus §854's escape that
       lets a break be taken for free rather than leaving the paragraph
       unbreakable. **A paragraph always produces lines.** A word wider than its
       line comes back as one overfull line rather than as an exception -- the
       `PackResult` says so, and a caller that wants to complain has what it
       needs.

    With `params.first_fit` none of the passes runs: the lines are filled
    greedily by `_first_fit` and come back with `pass_used` of
    `BreakPass.FIRST_FIT` and `total_demerits` of 0. Same preamble, same
    per-line shape, same treatment of both ends of every line.

    `measure` is needed only if the list contains `CharNode`s.
    """
    params = params or LineBreakParams()
    body = _prepare(nodes, params)

    if params.first_fit:
        chosen = _first_fit(body, shape, params, measure)
        return _assemble(body, chosen, shape, params, measure, 0, BreakPass.FIRST_FIT)

    attempts: list[tuple[int, Scaled, bool, BreakPass]] = []
    if params.pretolerance >= 0:
        attempts.append((min(params.pretolerance, INF_BAD), 0, False, BreakPass.FIRST))
    attempts.append(
        (min(params.tolerance, INF_BAD), 0, params.emergency_stretch <= 0, BreakPass.SECOND)
    )
    if params.emergency_stretch > 0:
        attempts.append(
            (min(params.tolerance, INF_BAD), params.emergency_stretch, True, BreakPass.EMERGENCY)
        )

    for threshold, extra, final, which in attempts:
        breaker = _Breaker(
            body=body,
            shape=shape,
            params=params,
            threshold=threshold,
            extra_stretch=extra,
            final_pass=final,
            measure=measure,
        )
        winner = breaker.run()
        if winner is None:
            continue
        return _assemble(body, _chain(winner), shape, params, measure, winner.total_demerits, which)

    raise AssertionError(
        "no pass produced a breaking, which §854's last-resort escape is supposed to prevent; "
        "this is a defect in the breaker rather than in the paragraph"
    )


def _assemble(
    body: Sequence[Node],
    breaks: Sequence[_Passive],
    shape: ParShape,
    params: LineBreakParams,
    measure: CharMeasure | None,
    total_demerits: int,
    which: BreakPass,
) -> Paragraph:
    """
    Pack each chosen line to its own width and shift it to its own indent (§889).

    Packed **without** `emergency_stretch`, deliberately: the extra
    stretchability existed to let the breaker accept a breaking it would
    otherwise have rejected, and pretending it exists here would hide the
    underfull lines that acceptance produced.
    """
    lines: list[PackResult] = []
    previous: _Passive | None = None
    for line_number, current in enumerate(breaks, start=1):
        spec = shape.for_line(line_number)
        packed = hpack(
            _line_nodes(body, previous, current, params),
            spec.width,
            PackMode.EXACTLY,
            measure=measure,
        )
        if spec.indent:
            packed = replace(packed, box=replace(packed.box, shift_amount=spec.indent))
        lines.append(packed)
        previous = current
    return Paragraph(lines=tuple(lines), total_demerits=total_demerits, pass_used=which)

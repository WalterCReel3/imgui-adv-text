r"""
The demo documents as executable claims about themselves.

`tests/test_litmus.py` guards `demo/sample.md` as *evidence for the engine* --
every justified line on the margin, one bar down the quote, the table's rule
reaching the same number the prose does. This file guards the two demo
documents as *content*: that they still exercise the features the demo says
they exercise, and that `demo/columns.md` is still shaped so it can be flowed
into newspaper columns.

## What "shaped so it can be flowed" means, and which half of it matters

Two independent properties, and the interesting thing is that **the obvious one
turned out not to matter and the other one does**. Both are measured here
rather than argued, because both were argued first and one of the arguments was
wrong.

**Vertical: how tall an indivisible slab the document contains.** Measured
against this tree: `advtext.ui._stacked` joins two *lines of one paragraph* with
interline glue and joins two *blocks* -- two paragraphs, two items of a list, a
heading and the text under it -- with a rigid `Kern`. `docs/tex-notes.md` §5
makes a break at glue legal only after a non-discardable node and makes a break
at a `NORMAL` kern illegal outright, so the only legal place to cut this
engine's vertical list is inside a paragraph. A barred quote is one box
whatever its length, because `_barred` packs it whole.

That reads like a disaster and is not one. `SLAB_BOUND` records the measurement
that settled it: making every one of those kerns breakable produces an
*identical* three-column split. The bound below is a guardrail against a future
edit dropping a very tall quotation into the middle, not a constraint the prose
had to be written around.

**Horizontal: whether any glyph is shipped past the column edge.** This is the
one that bites. At three columns `demo/sample.md` puts 71 glyphs outside the
measure, worst by 135.5 pt, because a long hyphenated compound is a single
unbreakable token here -- nothing generates a `Disc` node at an existing hyphen
-- and because fenced code and table cells do not wrap at all. Raising
`emergency_stretch` plateaus and does not fix it. `demo/columns.md` is written
to ship zero, and `test_no_glyph_of_the_column_document_is_shipped_past_the_
column_edge` is what keeps it that way.

Every measurement above has a control beside it, because each of these checks
is a function that could quietly stop finding anything: `_slabs` would pass
every document if it cut at every node, `_overfull` and `_past_the_measure`
would pass every document if they returned nothing. The controls feed each one
an input it must fail on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from advtext.markdown import build_document
from advtext.nodes import Box, Glue, Kern, Node
from advtext.pack import PackFitness
from advtext.shipout import Glyph, Line, Point, ship
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import PROSE_BREAKING, _shape, _skips, _stacked, compose
from advtext.units import Scaled, pt_from_sp, sp_from_pt

DEMO = Path(__file__).resolve().parent.parent / "demo"

COLUMN_MEASURE = sp_from_pt(200.0)
"""
A deliberately punishing column measure: narrower than three columns of the
demo window, so a document that survives this survives the tab.

`scripts/render_litmus.py` sets the single-column page at 420 pt. Three columns
of a 1100 px window are nearer 320 pt each; 200 pt is well inside that, and the
narrower the measure the fewer interword spaces there are to absorb a bad line.
"""

SLAB_BOUND = sp_from_pt(196.0)
"""
The tallest indivisible run `demo/columns.md` is allowed at `COLUMN_MEASURE`.

**Not a taste judgement -- the largest slab that has been measured not to
matter.** `demo/sample.md`'s tallest is 195.9 pt at a 262 pt measure, and
splitting that document into three columns fills them to 524, 513 and 520 pt of
527: a worst hole of 14 pt, under 3% of a column. Substituting `Glue` for every
block-boundary `Kern`, so that those slabs become cuttable, takes the legal
breakpoint count from 74 to 96 and produces an **identical** split. So a slab of
this size buys a reader nothing and costs them nothing.

Measured by the `advtext.columns` builder and reproduced here independently
before the number was written down; `demo/sample.md @ 262pt` reports 90 legal
breakpoints and a 195.9 pt tallest slab on this tree today.

The bound therefore reads "no worse than the document we already ship and have
already looked at". A document that trips it is not necessarily wrong, but
somebody should look at a screenshot of it before raising this.
"""


@pytest.fixture(scope="session")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="session")
def sample(bundled_fonts: Path) -> str:
    return (DEMO / "sample.md").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def columns(bundled_fonts: Path) -> str:
    return (DEMO / "columns.md").read_text(encoding="utf-8")


def _overfull(source: str, theme: Theme, width: Scaled) -> list[tuple[str, float]]:
    """
    Every line of `source` that sits in or past the right margin at `width`.

    The same walk `test_litmus.py::test_no_line_in_the_document_is_overfull`
    does, at an arbitrary measure rather than the page's.
    """
    from advtext.linebreak import break_paragraph
    from advtext.markdown import TextBlock

    measure = char_measure(fontlib_metrics)
    document = build_document(source, theme, fontlib_metrics)
    offenders: list[tuple[str, float]] = []
    for block in document.blocks:
        if not isinstance(block, TextBlock):
            continue
        paragraph = break_paragraph(
            block.material,
            _shape(block, width),
            _skips(block.style.align, PROSE_BREAKING),
            measure=measure,
        )
        offenders.extend(
            (block.kind.name, pt_from_sp(line.overfull_by))
            for line in paragraph.lines
            if line.fitness is PackFitness.OVERFULL
        )
    return offenders


def _slabs(vlist: list[Node]) -> list[Scaled]:
    """
    The heights of the indivisible runs of a vertical list.

    A column splitter may cut at glue whose predecessor is a box, and nowhere
    else (`docs/tex-notes.md` §5): a `NORMAL` kern is not a legal breakpoint and
    neither is glue that follows one. Everything between two such positions has
    to travel together, so these heights are exactly the sizes a column has to
    be able to swallow whole.
    """
    slabs: list[Scaled] = []
    height: Scaled = 0
    for index, node in enumerate(vlist):
        if isinstance(node, Glue) and index and isinstance(vlist[index - 1], Box):
            slabs.append(height)
            height = 0
        if isinstance(node, Box):
            height += node.height + node.depth
        elif isinstance(node, Kern):
            height += node.width
        elif isinstance(node, Glue):
            height += node.spec.width
    slabs.append(height)
    return slabs


def _vlist(source: str, theme: Theme, width: Scaled) -> list[Node]:
    document = build_document(source, theme, fontlib_metrics)
    return _stacked(
        document.blocks,
        theme,
        width,
        char_measure(fontlib_metrics),
        PROSE_BREAKING,
        depth=0,
        memo=None,
    )


# --------------------------------------------------------------------------
# demo/columns.md is fit to be flowed into columns
# --------------------------------------------------------------------------


def test_no_line_of_the_column_document_is_overfull_at_a_three_column_measure(
    columns: str, theme: Theme
) -> None:
    # Justified setting with no hyphenation gets harder as the measure narrows,
    # because there are fewer interword spaces left to absorb the error. The
    # single-column litmus document is only ever checked at 420 pt; this
    # document is meant to be read at less than half that.
    assert _overfull(columns, theme, COLUMN_MEASURE) == []


def test_the_overfull_check_can_actually_fail_at_this_measure(theme: Theme) -> None:
    # The control for the test above, and the reason to trust it. Without
    # hyphenation a word wider than the measure has nowhere to break, so it
    # must come back overfull -- and if it does not, `_overfull` is looking at
    # the wrong thing and the green above means nothing.
    long_word = "unsplittable" * 4
    offenders = _overfull(
        f"A paragraph containing {long_word} and no way out.\n", theme, COLUMN_MEASURE
    )
    assert offenders, "a word wider than the measure must overfull, or _overfull is vacuous"


def _past_the_measure(source: str, theme: Theme, width: Scaled) -> list[Scaled]:
    """
    How far each shipped glyph's right edge overhangs `width`, for those that do.

    Stronger than `_overfull`, and the two are not redundant. `_overfull` asks
    the *line breaker* for its verdict, and the breaker never sees a fenced code
    block (never wrapped, by design) or a table cell (does not wrap;
    `docs/status.md` section 4). This asks the page, after ship-out, and so
    covers every block kind.
    """
    measure = char_measure(fontlib_metrics)
    box = compose(build_document(source, theme, fontlib_metrics), theme, width, measure)
    from advtext.nodes import CharNode

    overhangs = []
    for cmd in ship(box, Point(0, box.height), measure=measure):
        if not isinstance(cmd, Glyph):
            continue
        right = cmd.x + measure(CharNode(cmd.font, cmd.codepoint)).width
        if right > width:
            overhangs.append(right - width)
    return overhangs


def test_no_glyph_of_the_column_document_is_shipped_past_the_column_edge(
    columns: str, theme: Theme
) -> None:
    # **The constraint that actually decides whether a document can be set in
    # columns**, measured rather than assumed: at three columns
    # `demo/sample.md` ships 71 glyphs outside the measure, the worst by 135.5
    # pt, and one and two columns ship none. The causes are horizontal tokens
    # with no legal break in them at a narrow measure -- a long hyphenated
    # compound (nothing generates `Disc` nodes at an existing hyphen), a fenced
    # code block, a table. Raising `emergency_stretch` does not help: a sweep at
    # 20/40/60/80 pt gives 64/61/44/44 glyphs and plateaus.
    #
    # So this is a property of the *prose*, which is why it is asserted here and
    # not in the engine's suite. `demo/columns.md` must ship zero, and does.
    overhangs = _past_the_measure(columns, theme, COLUMN_MEASURE)
    assert overhangs == [], (
        f"{len(overhangs)} glyphs outside a {pt_from_sp(COLUMN_MEASURE):.0f} pt column, "
        f"worst by {pt_from_sp(max(overhangs)):.1f} pt -- look for a long hyphenated "
        f"compound, a URL, a wide inline-code span, fenced code or a table"
    )


def test_a_token_wider_than_the_column_really_does_ship_past_its_edge(theme: Theme) -> None:
    # The control. Without it the test above is a green light from a function
    # that might simply never find anything. There is no hyphenation here, so a
    # single token wider than the measure has nowhere to break and must hang
    # off the edge -- and if it does not, `_past_the_measure` is wrong.
    unbreakable = "extraordinarily-" * 4 + "long"
    overhangs = _past_the_measure(
        f"A paragraph about {unbreakable} words.\n", theme, COLUMN_MEASURE
    )
    assert overhangs, "an unbreakable token wider than the measure must overhang it"


def test_the_column_document_contains_no_slab_too_tall_to_fit_a_column(
    columns: str, theme: Theme
) -> None:
    # The property that makes a document *column-worthy* rather than merely
    # long. A run of blocks with no glue between them cannot be cut, so it
    # either fits in what is left of a column or leaves that much white behind.
    slabs = _slabs(_vlist(columns, theme, COLUMN_MEASURE))
    tallest = max(slabs)
    assert tallest <= SLAB_BOUND, (
        f"tallest indivisible run is {pt_from_sp(tallest):.1f} pt against a "
        f"{pt_from_sp(SLAB_BOUND):.1f} pt bound; shorten a quotation or a run of list items"
    )


def test_the_slab_measurement_finds_a_real_slab_and_not_a_line(theme: Theme) -> None:
    # The fixture attack. If `_slabs` cut at every node it would report one line
    # height per slab, every document would pass `SLAB_BOUND`, and the test
    # above would be decoration. So: forty one-line list items, which this
    # engine joins with rigid kerns and no glue, must come back as **one** slab
    # far taller than the bound -- while forty lines of one paragraph, joined by
    # interline glue, must come back as forty.
    items = "".join(f"- item number {n}\n" for n in range(40))
    prose = " ".join(f"word{n} and more filler text here" for n in range(80)) + "\n"

    item_slabs = [height for height in _slabs(_vlist(items, theme, COLUMN_MEASURE)) if height]
    prose_slabs = [height for height in _slabs(_vlist(prose, theme, COLUMN_MEASURE)) if height]

    assert len(item_slabs) == 1, "a run of list items has no legal breakpoint in it"
    assert item_slabs[0] > SLAB_BOUND, "and the control has to actually exceed the bound"
    assert len(prose_slabs) > 20, "a long paragraph is cuttable between every pair of its lines"
    assert max(prose_slabs) < SLAB_BOUND


# --------------------------------------------------------------------------
# Between them, the two documents exercise what the demo claims to show
# --------------------------------------------------------------------------


def _faces(source: str, theme: Theme, width: Scaled) -> set[str]:
    """
    The font keys that actually reach ship-out, without their sizes.
    """
    measure = char_measure(fontlib_metrics)
    box = compose(build_document(source, theme, fontlib_metrics), theme, width, measure)
    cmds = ship(box, Point(0, box.height), measure=measure)
    return {cmd.font.split("@")[0] for cmd in cmds if isinstance(cmd, Glyph)}


def test_the_two_demo_documents_between_them_ship_every_prose_face(
    sample: str, columns: str, theme: Theme
) -> None:
    # An unexercised feature reads as an absent one. Bold-italic in particular
    # was absent from the demo until this batch: the markdown for it is
    # `***three asterisks***`, it is easy to leave out, and nothing else in the
    # suite would notice. Asserting on the *shipped* font rather than on the
    # source is what makes this a claim about rendering; grepping for asterisks
    # would pass on a document whose emphasis never reached a face.
    shipped = _faces(sample, theme, sp_from_pt(420.0)) | _faces(columns, theme, COLUMN_MEASURE)
    assert {"prose", "prose-bold", "prose-italic", "prose-bold-italic", "code"} <= shipped


def test_the_sample_document_still_carries_a_two_digit_ordered_marker(
    sample: str, theme: Theme
) -> None:
    # `docs/status.md` section 4 records that widening `list_indent` to 1.9 em,
    # so "10." clears its own text, cost every list item 0.4 em of measure. The
    # engine-level guarantee is pinned by
    # `test_litmus.py::test_a_two_digit_ordered_marker_keeps_the_full_gap_before_its_own_text`
    # against a synthetic list. This asserts the *demo* pays for what it bought:
    # that a reader looking at the real document can see a two-digit marker at
    # all, and that its text lines up with the one-digit ones.
    #
    # The existence assertion is load-bearing, not throat-clearing. The
    # alignment assertion alone is vacuously true of a document with no ordered
    # list in it, which is exactly what a careless edit to `demo/sample.md`
    # would produce.
    measure = char_measure(fontlib_metrics)
    box = compose(build_document(sample, theme, fontlib_metrics), theme, sp_from_pt(420.0), measure)
    cmds = ship(box, Point(0, box.height), measure=measure)
    glyphs = [cmd for cmd in cmds if isinstance(cmd, Glyph)]

    starts: dict[str, set[Scaled]] = {}
    for line in (cmd for cmd in cmds if isinstance(cmd, Line)):
        run = [glyph for glyph in glyphs if line.start <= glyph.index < line.end]
        text = "".join(chr(glyph.codepoint) for glyph in run)
        marker, _, _ = text.partition(".")
        if not marker.isdigit() or len(marker) > 2 or len(run) <= len(marker) + 1:
            continue
        starts.setdefault(marker, set()).add(run[len(marker) + 1].x)

    two_digit = {marker for marker in starts if len(marker) == 2}
    assert two_digit, "demo/sample.md no longer sets any ordered item past nine"
    # Every item's text begins at the gutter, one and two digits alike: the
    # marker hangs in the margin rather than pushing its own first line right.
    assert len({x for xs in starts.values() for x in xs}) == 1

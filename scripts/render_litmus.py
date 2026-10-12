r"""
Render the two litmus tests to SVG, and assemble the document layer that joins the parts.

Everything below `imscribe.markdown` produces *blocks*; everything below
`imscribe.linebreak` produces *lines*. Nothing in the tree turns a document into
a single vertical list, because that is the one piece of the pipeline that is
policy rather than typesetting -- how much air goes above a heading, where a
list marker hangs, how a table's columns are apportioned. That policy lives
here, next to the artifacts it produces, so `docs/litmus.md` can say exactly
what was decided and what it decided wrongly.

Run it with `make svg`, or:

    python scripts/render_litmus.py --out artifacts

**What this proves and what it does not.** The SVG backend exercises the layout
engine end to end with real font metrics, real kerning and real `MATH` table
data, and the artifacts are the evidence. It says **nothing** about the ImGui
backend, which is a separate consumer of the same `DrawCmd` list and is
evidenced separately -- by `tests/test_imgui_draw.py`, which runs a real ImGui
frame with no display and asserts on the vertex buffer it produces. Neither
proves the other, and `docs/imgui-risks.md` is where that boundary is kept.

**This paragraph used to say "no window can open in this environment", and that
stopped being true of the tree.** `make shot` runs the real app through
`immapp.run` and photographs it, and `docs/imgui-risks.md` records all five tabs
the app then had composited that way (it has fourteen pages now, in a sidebar).
What is still true is narrower and is about this script:
*it* opens no window and needs no display, so what it writes is evidence for the
layout and for the SVG backend only. Whether a display is reachable is a fact
about the machine and the session rather than about the code -- it has been
recorded both ways in this tree -- so ask `make shot`, not this docstring.

**The document policy is not here.** It was, once, and `docs/litmus.md` still
records the period when this script and `imscribe.ui.compose` were two
implementations of the same step that disagreed with each other. There is one
now and it is `imscribe.ui.compose`, which this script calls: how much air goes
above a heading, where a list marker hangs, how a table's columns are
apportioned and where a block quote's bar is drawn are all decided there. What
is left here is the page -- margins, which artifacts exist, and the two formulas
that have no document around them.

Deliberately simple, and named here so the write-up does not have to guess:

- **A table cell that does not fit its column overflows rather than wrapping.**
  Breaking text inside a cell means running the line breaker per cell against a
  width that depends on the breaking, which is `\halign`'s real problem and out
  of scope (`docs/decisions.md`).
- **No page breaking.** One tall page, as `docs/decisions.md` scopes it.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from imscribe import fontlib
from imscribe.backends.svg import render
from imscribe.fontmetrics import MathFontMetrics
from imscribe.markdown import (
    build_document,
)
from imscribe.math.atoms import Style, group, op, ord_, rel
from imscribe.math.mlist import math_fonts, mlist_to_hlist
from imscribe.nodes import Box, GlueSpec, Node
from imscribe.pack import (
    IGNORE_DEPTH,
    CharMeasure,
    InterlineSkip,
    append_to_vlist,
    hpack,
    vpack,
)
from imscribe.selection import Granularity, SelectionModel
from imscribe.shipout import DrawCmd, Point, ship
from imscribe.style import (
    BlockKind,
    Theme,
    char_measure,
    fontlib_metrics,
)
from imscribe.ui import compose
from imscribe.units import Scaled, sp_from_pt

__all__ = ["Rendered", "main", "render_markdown", "render_sigma"]

MEASURE = sp_from_pt(420.0)
"""
The text measure: 420 points, a little under six inches.

Chosen so that a paragraph of this prose breaks into four or five lines at the
16px body size. A narrower measure makes justification look worse and a wider
one hides it, and a litmus test that flatters itself is not one.
"""

MARGIN = sp_from_pt(36.0)
"""
Half an inch of air around the page, so the debug overlay's boxes are not clipped.
"""


@dataclass(frozen=True, slots=True)
class Rendered:
    """
    A laid-out page: the box it came from, the commands, and the canvas size.
    """

    box: Box
    cmds: list[DrawCmd]
    width: Scaled
    height: Scaled


def _page(box: Box, width: Scaled, measure: CharMeasure) -> Rendered:
    """
    Place a packed vbox on a margined page and ship it.
    """
    cmds = ship(box, Point(MARGIN, MARGIN + box.height), measure=measure)
    return Rendered(
        box=box,
        cmds=cmds,
        width=width + 2 * MARGIN,
        height=box.height + box.depth + 2 * MARGIN,
    )


def render_markdown(source: str, theme: Theme | None = None) -> Rendered:
    """
    Lay out a markdown document with real fonts and ship it.
    """
    theme = theme or Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document(source, theme, fontlib_metrics)
    return _page(compose(document, theme, MEASURE, measure), MEASURE, measure)


def _sigma(style: Style, size: Scaled) -> Box:
    r"""
    `\sum_{i=1}^{n} i^2` at one style, packed.

    The subscript is built as three atoms rather than as a string so that the
    `=` is a *relation* and gets §764's spacing. Building it with `text("i=1")`
    would make everything ordinary and the limit would read as a variable name.
    """
    fonts = math_fonts(size, _math_resolver)
    items = [
        op(chr(0x2211), sub=group(ord_("i"), rel("="), ord_("1")), sup=ord_("n")),
        ord_("i", sup=ord_("2")),
    ]
    return hpack(mlist_to_hlist(items, style, fonts), measure=fonts.measure).box


def _math_resolver(size: Scaled) -> MathFontMetrics:
    """
    The math face at a size in scaled points.
    """
    return fontlib.math_metrics(float(size))


def render_sigma(size: Scaled, style: Style = Style.DISPLAY) -> Rendered:
    """
    One formula on its own page.
    """
    measure = char_measure(fontlib_metrics)
    box = _sigma(style, size)
    return _page(vpack([box]).box, box.width, measure)


def render_sigma_comparison(size: Scaled) -> Rendered:
    """
    The same formula in display and text style, one above the other.

    Side by side would be prettier and this is more legible: the claim being
    demonstrated is that the display operator is a *taller glyph* and not the
    body one scaled, so the two want a shared left edge to be compared against.
    """
    measure = char_measure(fontlib_metrics)
    leading = InterlineSkip(
        baselineskip=GlueSpec(width=4 * size), lineskip=GlueSpec(width=size), lineskiplimit=0
    )
    display = _sigma(Style.DISPLAY, size)
    inline = _sigma(Style.TEXT, size)
    vlist: list[Node] = []
    prev_depth: Scaled = IGNORE_DEPTH
    for box in (display, inline):
        prev_depth = append_to_vlist(vlist, box, prev_depth, leading)
    packed = vpack(vlist).box
    return _page(packed, max(display.width, inline.width), measure)


def _selection_points(rendered: Rendered) -> tuple[Point, Point]:
    """
    Two points that drag across several lines of the first long paragraph.

    Derived from the shipped lines rather than typed in, so the artifact keeps
    covering a multi-line range when the document or the measure changes. The
    point of the picture is that the rects are coherent across lines with
    different descenders, which needs a selection that actually spans some.
    """
    model = SelectionModel.from_commands(rendered.cmds)
    lines = [fragment.line for fragment in model.fragments if fragment.end > fragment.start]
    first = lines[min(3, len(lines) - 1)]
    last = lines[min(7, len(lines) - 1)]
    return (
        Point(first.x + first.width // 4, first.y),
        Point(last.x + 3 * last.width // 4, last.y),
    )


def render_selection(rendered: Rendered) -> tuple[str, str]:
    """
    The document with a multi-line selection highlighted, and the selected text.
    """
    model = SelectionModel.from_commands(rendered.cmds)
    anchor, active = _selection_points(rendered)
    selection = model.select_at(anchor, active, Granularity.WORD)
    document = render(
        rendered.cmds,
        rendered.width,
        rendered.height,
        highlights=model.rects(selection),
    )
    return document, model.text(selection)


def main(argv: list[str] | None = None) -> int:
    """
    Render every artifact into `--out`, printing what was written.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parent.parent / "demo" / "sample.md"
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    theme = Theme.build()
    body = theme.style(BlockKind.PARAGRAPH).font.size
    page = render_markdown(args.source.read_text(encoding="utf-8"), theme)

    written: list[tuple[Path, int]] = []

    def write(name: str, text: str) -> None:
        target = args.out / name
        target.write_text(text, encoding="utf-8")
        written.append((target, len(text)))

    write("markdown.svg", render(page.cmds, page.width, page.height))
    write("markdown-debug.svg", render(page.cmds, page.width, page.height, debug=True))

    sigma = render_sigma(body)
    write("sigma.svg", render(sigma.cmds, sigma.width, sigma.height))
    comparison = render_sigma_comparison(body)
    write("sigma-compare.svg", render(comparison.cmds, comparison.width, comparison.height))

    highlighted, selected = render_selection(page)
    write("selection.svg", highlighted)

    for target, size in written:
        print(f"{target}  {size:>8} bytes")
    print(f"\nselected text ({len(selected)} chars):\n  {selected[:160]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

r"""
SVG backend: real glyph outlines, no GPU, no display, no ImGui.

This is how the litmus tests are *shown* to have worked rather than merely
asserted. There is no display in this environment and no X server can be
started, so the ImGui backend cannot be executed at all; this one can, and it
produces a file anybody can open. It is not a fallback. A layout that two
unrelated backends render identically has genuinely had its geometry separated
from its drawing, and that separation is what made selection tractable in the
first place.

**Outlines, not `<text>`.** A `<text>` element hands positioning back to the SVG
renderer's own font machinery: it would pick its own advances, apply its own
kerning, and the picture would show *its* layout rather than ours. Since showing
our layout is the entire purpose of the artifact, every glyph is emitted as a
`<path>` pulled from the font with `SVGPathPen` and placed by an explicit
transform. If the output is wrong, it is wrong because we computed it wrong.

**The coordinate system is scaled points, and that is what keeps it exact.**
The root element carries `width`/`height` in **points**, so the file displays at
its true physical size in any viewer, and a `viewBox` in **scaled points**, so
every coordinate inside the document is the integer `imscribe.shipout` produced.
Nothing is converted, so nothing is rounded, so a golden artifact diffs
byte-for-byte against the numbers the layout actually computed. The alternative
-- converting each coordinate to points or pixels on the way out -- would put a
float formatting decision between the layout and the evidence for it.

`imscribe.units.round_to_px` is deliberately *not* used. SVG is a continuous
device; the round-once-at-ship-out discipline exists for a raster one, and
rounding here would discard precision to satisfy a rule that does not apply.

**The y flip is the sign error to watch for.** Glyph outlines are in font units
with y increasing *up* from the baseline. SVG, like `imscribe.shipout`, has y
increasing *down*. So each glyph's transform is
`translate(x, baseline) scale(k, -k)` -- the negative y scale is the flip, and
the translate puts the origin on the baseline rather than at the top of the
glyph. `tests/test_svg.py` asserts explicitly that a glyph with positive ascent
lands *above* its baseline, because this is the error that produces output which
looks plausible and is upside down.

**Debug mode is the most useful tool this project has.** A layout bug is almost
always obvious the instant the boxes are drawn and almost never obvious from the
numbers. The overlay shows each line's box and baseline, and every interword
glue coloured by whether it was stretched or shrunk -- so justification and
interline glue are *seen* working rather than trusted. `SetGlue` carries both its
set and its natural width, which is the only place in a rendered document where
the line breaker's decision appears as a quantity.

Deliberately out of scope:

- **Anything that is not a `DrawCmd`.** No text flow, no CSS, no `<use>`
  deduplication of repeated glyphs. Deduplicating would shrink the file and make
  it much harder to read next to the command list it came from.
- **Colour as a document property.** `imscribe.shipout` carries none, for the
  reason its docstring gives, so colours are render-time arguments with plain
  defaults. This backend takes no per-glyph inks, so links are not tinted
  here. Where a link's glyphs are among the shipped commands is no longer the
  caller's to work out by hand: `imscribe.spans.decorate` turns a block's
  `LinkSpan`s into shipped index ranges and rectangles, which is what the
  ImGui views draw from.
- **Font embedding.** The outlines are already in the file; there is nothing
  left for a font to contribute.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Final, assert_never
from xml.sax.saxutils import quoteattr

from imscribe.fontmetrics import Face
from imscribe.selection import Rect
from imscribe.shipout import DrawCmd, Glyph, Line, RuleRect, SetGlue
from imscribe.style import parse_font_key
from imscribe.units import UNITY, Scaled

__all__ = ["Palette", "glyph_outline", "render"]

_SVG_NS: Final = "http://www.w3.org/2000/svg"

_HAIRLINE: Final = UNITY // 4
"""
Stroke width for the debug overlay, in scaled points: a quarter of a point.

Thin enough that a box outline does not obscure the glyph it encloses, and thick
enough to survive being rasterised at a normal zoom. It is a fixed length rather
than a fraction of anything because the overlay is an instrument and should not
change weight when the document does.
"""


@dataclass(frozen=True, slots=True)
class Palette:
    """
    Every colour the renderer can emit, so none of them is buried in a format string.

    Defaults are a light page with near-black text: the artifacts are meant to
    be looked at and diffed, not themed. The debug colours are chosen to be
    distinguishable from each other rather than to be pretty -- stretched glue
    reads cool and shrunk glue reads warm, which is the one association worth
    having, because an overfull line is the failure you want to spot across a
    page.
    """

    background: str | None = "#ffffff"
    ink: str = "#111111"
    rule: str = "#111111"
    highlight: str = "#3b82f6"
    highlight_opacity: float = 0.3
    debug_box: str = "#22c55e"
    debug_baseline: str = "#ef4444"
    debug_stretched: str = "#3b82f6"
    debug_shrunk: str = "#f97316"
    debug_natural: str = "#94a3b8"


def _face_outlines(face: Face) -> tuple[Any, int]:
    """
    The glyph set and units-per-em for a face.

    A thin forward to `imscribe.fontlib.glyph_set`, which is where the one parse of
    a font file lives. This backend opens nothing: it holds no fontTools import at
    module level and names no font file, so `fontlib` remains the only module that
    knows either. That is also why this is not itself cached -- `fontlib` already
    parses each face once per process, and a second cache in front of it would only
    duplicate a dict lookup.
    """
    from imscribe import fontlib

    # `glyph_outline` below is keyed by face, so it has to be dropped when a host
    # registers a different file for one. Asked for here, on a cache miss, rather
    # than at import: this module names `fontlib` nowhere at module level, and
    # registering the same callable again is a no-op.
    fontlib.on_registry_change(glyph_outline.cache_clear)
    return fontlib.glyph_set(face)


@cache
def glyph_outline(face: Face, name: str) -> str:
    """
    SVG path data for one glyph, in font units with y up, memoised per face and name.

    Memoised because a page of prose repeats a few dozen glyphs thousands of
    times and re-running the pen for each occurrence is pure waste. The cache is
    keyed on the glyph *name* rather than on a codepoint on purpose: a display
    -size operator selected from the `MATH` variant chain has no codepoint in the
    font at all, and `imscribe.fontlib.glyph_name` is the only route to it.

    Returns `""` for a glyph with no contours -- a space, or a `.notdef` that the
    face draws as nothing. Callers skip those rather than emitting an empty path.
    """
    from fontTools.pens.svgPathPen import SVGPathPen

    glyph_set, _ = _face_outlines(face)
    pen = SVGPathPen(glyph_set)
    glyph_set[name].draw(pen)
    return str(pen.getCommands())


def _num(value: float) -> str:
    """
    Format a number for an attribute: exact for integers, trimmed otherwise.

    Ten decimal places because the one non-integer quantity in the output is a
    glyph's scale factor, `size / units_per_em`, and at a thousand font units of
    ascent a relative error of 1e-7 is already a visible tenth of a scaled point.
    Integers -- which is every coordinate -- go out unchanged, so the common case
    is exact and the file stays readable.
    """
    if isinstance(value, int) or value == int(value):
        return str(int(value))
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _attrs(**attributes: object) -> str:
    """
    Render XML attributes, skipping any whose value is `None`.
    """
    parts: list[str] = []
    for name, value in attributes.items():
        if value is None:
            continue
        text = _num(value) if isinstance(value, int | float) else str(value)
        parts.append(f"{name.replace('_', '-')}={quoteattr(text)}")
    return " ".join(parts)


def _glyph_path(cmd: Glyph, palette: Palette) -> str | None:
    """
    One glyph as a placed `<path>`, or `None` if the face draws it as nothing.

    The transform is the whole of the coordinate handling: `translate` puts the
    glyph's origin on its baseline at its left edge, and `scale(k, -k)` both
    converts font units to scaled points and flips y from the font's up to SVG's
    down. Doing it as a transform rather than by transforming the path data keeps
    the outline cacheable across every size and position it appears at.
    """
    spec = parse_font_key(cmd.font)
    name = _glyph_name(spec.face, cmd.codepoint)
    outline = glyph_outline(spec.face, name)
    if not outline:
        return None
    _, units_per_em = _face_outlines(spec.face)
    scale = spec.size / units_per_em
    transform = f"translate({_num(cmd.x)} {_num(cmd.y)}) scale({_num(scale)} {_num(-scale)})"
    return "<path " + _attrs(d=outline, fill=palette.ink, transform=transform) + "/>"


def _glyph_name(face: Face, codepoint: int) -> str:
    """
    Indirection so the font library is imported lazily, like everything else here.
    """
    from imscribe import fontlib

    return fontlib.glyph_name(face, codepoint)


def _rule_rect(cmd: RuleRect, palette: Palette) -> str:
    """
    A rule as a filled rectangle. `y` is already the top edge (§624).
    """
    return (
        "<rect "
        + _attrs(x=cmd.x, y=cmd.y, width=cmd.width, height=cmd.height, fill=palette.rule)
        + "/>"
    )


def _highlight_rect(rect: Rect, palette: Palette) -> str:
    """
    One selection fragment, drawn under the text so the glyphs stay legible.
    """
    return (
        "<rect "
        + _attrs(
            x=rect.x,
            y=rect.y,
            width=rect.width,
            height=rect.height,
            fill=palette.highlight,
            fill_opacity=palette.highlight_opacity,
        )
        + "/>"
    )


def _debug_line(cmd: Line, palette: Palette) -> Iterable[str]:
    """
    A line's box and its baseline.

    The box spans `[y - height, y + depth)` because `y` is the baseline and not
    the top edge -- the same convention as everywhere else, and drawing it makes
    the distinction impossible to get wrong by accident for anyone looking at the
    picture.
    """
    yield "<rect " + _attrs(
        x=cmd.x,
        y=cmd.y - cmd.height,
        width=cmd.width,
        height=cmd.height + cmd.depth,
        fill="none",
        stroke=palette.debug_box,
        stroke_width=_HAIRLINE,
    ) + "/>"
    yield "<line " + _attrs(
        x1=cmd.x,
        y1=cmd.y,
        x2=cmd.x + cmd.width,
        y2=cmd.y,
        stroke=palette.debug_baseline,
        stroke_width=_HAIRLINE,
    ) + "/>"


def _debug_glue(cmd: SetGlue, palette: Palette) -> Iterable[str]:
    """
    One interword space, coloured by what justification did to it.

    Cool where the glue was stretched, warm where it was shrunk, grey where it
    kept its natural width. The natural width is marked with a tick, so the
    amount of stretch is a visible distance rather than a colour alone -- which
    is what makes the difference between a loose line and a very loose one
    legible at a glance.
    """
    if cmd.width > cmd.natural:
        colour = palette.debug_stretched
    elif cmd.width < cmd.natural:
        colour = palette.debug_shrunk
    else:
        colour = palette.debug_natural
    yield "<rect " + _attrs(
        x=cmd.x,
        y=cmd.y - cmd.height,
        width=cmd.width,
        height=cmd.height + cmd.depth,
        fill=colour,
        fill_opacity=0.35,
    ) + "/>"
    yield "<line " + _attrs(
        x1=cmd.x + cmd.natural,
        y1=cmd.y - cmd.height,
        x2=cmd.x + cmd.natural,
        y2=cmd.y + cmd.depth,
        stroke=colour,
        stroke_width=_HAIRLINE,
    ) + "/>"


def render(
    cmds: Sequence[DrawCmd],
    width: Scaled,
    height: Scaled,
    *,
    debug: bool = False,
    highlights: Sequence[Rect] = (),
    palette: Palette | None = None,
) -> str:
    """
    Render a shipped command list as a standalone SVG document.

    `width` and `height` are the page's, in scaled points. They become the
    `viewBox`, so every coordinate in `cmds` is used as it is, and the root
    element's `width`/`height` are the same measurement expressed in points so
    that the file opens at its true size.

    `highlights` are `imscribe.selection` rectangles and are drawn **under**
    everything else, which is what keeps selected text readable. Rules go next,
    glyphs on top, and the debug overlay above all of it.

    `debug` adds one box and baseline per line and one coloured rect per
    interword space. Nothing else about the output changes, so a debug render and
    a plain render of the same commands agree glyph for glyph and can be diffed.
    """
    palette = palette or Palette()
    body: list[str] = []

    if palette.background is not None:
        body.append(
            "<rect " + _attrs(x=0, y=0, width=width, height=height, fill=palette.background) + "/>"
        )
    body.extend(_highlight_rect(rect, palette) for rect in highlights)

    glyphs: list[str] = []
    rules: list[str] = []
    overlay: list[str] = []
    for cmd in cmds:
        match cmd:
            case Glyph():
                path = _glyph_path(cmd, palette)
                if path is not None:
                    glyphs.append(path)
            case RuleRect():
                rules.append(_rule_rect(cmd, palette))
            case Line():
                if debug:
                    overlay.extend(_debug_line(cmd, palette))
            case SetGlue():
                if debug:
                    overlay.extend(_debug_glue(cmd, palette))
            case _ as unreachable:
                assert_never(unreachable)

    body.extend(rules)
    body.extend(glyphs)
    # The overlay goes last so it is never hidden by the material it describes.
    body.extend(overlay)

    header = (
        "<svg "
        + _attrs(
            xmlns=_SVG_NS,
            width=f"{_num(width / UNITY)}pt",
            height=f"{_num(height / UNITY)}pt",
            viewBox=f"0 0 {_num(width)} {_num(height)}",
        )
        + ">"
    )
    return "\n".join([header, *body, "</svg>", ""])

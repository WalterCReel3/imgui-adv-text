r"""
The ImDrawList backend: the same draw commands the SVG backend takes, issued to ImGui.

**What has been executed, stated precisely, because the distinction is the whole
point.** `draw` runs here, inside a real `imgui.new_frame()`/`imgui.render()`
pair, and emits real geometry: `tests/test_imgui_draw.py` ships the litmus
formula through this module and asserts on the vertex buffer it produces.

This module's docstring used to end there, saying "no GPU is reachable" and "a
display is still unreachable and Xvfb still cannot start". **That was not true
of the session that corrected it**, and it was load-bearing enough to correct
in place: `DISPLAY=:1` was live, `advtext.ui.app`'s `immapp.run` window opened
in well under a second with no Xvfb, and `make shot` (`scripts/shot.py`)
photographed any tab of the real demo to a PNG. (Whether a display answers is a
fact about a session, not about this module: in the sandboxed session of
2026-10-06 `DISPLAY=:1` was set and unreachable, and the same script ran on an
Xvfb in a user namespace instead -- see the `Makefile` header.) The defect
`docs/subpixel.md` records was found that way
and could not have been found any other way: it was invisible in every assertion
in `tests/test_imgui_draw.py` at the time, because a resampled quad is still a
quad. `docs/imgui-risks.md` remains the list of what is open.

The tests still assert **draw geometry, not pixels**, and that has not changed:
nothing under `tests/` composites a framebuffer, because a frame needs no display
and a window does. The honest claim is now "correct draw geometry, verified by
test; composited pixels, verified by looking".

## Every glyph one texel to one pixel

`docs/subpixel.md` is the write-up; this is the part a reader of this file needs.

ImGui 1.92 quantises the baked size to `floor(size + 0.5)` and then draws the
baked bitmap scaled by `size / baked_size`. Since `baked_size_px` below returns a
fractional size for five of the six faces, that scale used to be a few tenths of
a percent off 1 for every glyph in the document -- which put every quad corner
off the pixel grid and made every quad a non-integer number of texels wide, so
the GPU resampled a bitmap that was already exactly right. Measured: 1734 of 1734
glyph quads in `demo/sample.md`.

Two things fix it and both are draw-time only, in device space, because
`tests/test_litmus.py`'s zero-residue claim belongs to layout space and a
renderer may not touch it. `_baked` asks ImGui for the size it was going to bake
at anyway, which selects the same raster and draws it 1:1. `snap_px` puts the pen
on the nearest pixel rather than leaving it to ImGui's `IM_TRUNC`, which is
biased half a pixel left. Both snap *absolute* coordinates and never advances;
`snap_px` says what goes wrong otherwise.

One glyph quad is still exactly as many pixels across as it is texels across
after everything below -- that property belongs to the *size*, not the position,
and `test_no_glyph_of_the_demo_document_is_resampled` is one-sided about it.

## The pen is snapped relative to the rigid span it is in

A third change, and it is a **taste trade the user made**, not a correctness
fix: `_RigidSpan`. Snapping each glyph's absolute position independently makes
the gaps *inside* a word depend on where the word happens to fall, so the same
word sets at two different shapes in two different places -- measured on
`demo/sample.md`, 67 of 496 distinct spans. Anchoring the span and snapping each
glyph's offset *from the anchor* takes that to 0 of 496, because the offsets are
differences of scaled points and a rigid span has no elastic node in it.

It costs rendered rag: the worst glyph departure from its computed position goes
from 0.50 px to 1.00 px, and the last glyph of a justified line lands up to
0.86 px from the right margin instead of 0.48. The user was asked and chose it:
"I think I would take a little more rag on the right justification line if the
text looks better." Layout space is untouched -- `tests/test_litmus.py` still
asserts zero residue in scaled points and still passes. `docs/subpixel.md` §6.1.

## Inside that span the *gaps* are rounded, not the positions

The fourth change, and the one that made the third's trade unnecessary.
`docs/advance-rule.md` is the write-up.

Rounding each glyph's offset from the anchor independently -- which is what this
module did, first to a whole pixel and then to a half -- means an inter-letter
gap is `round(next) - round(this)` and can be a **whole pixel** away from the gap
the designer drew. Measured on `demo/sample.md`: 478 of 3453 adjacent pairs.
That is the defect behind "people" at gaps of 1, 2, 2 px and behind the heading
"What the difference looks like" closing the gap in `iffe` entirely.

`_RigidSpan.pen` instead rounds each *gap* to a whole pixel and accumulates from
the anchor, which is what ImGui's own `ImFont::RenderText` does -- verified by
reading the vertex buffer, `scripts/pen_rules.py --native`. Every gap is then
within half a pixel of the design, **and** every glyph lands on the pixel grid,
so nothing is resampled. The half-pixel rule could not hold both: it bought the
gaps by putting 1444 of 4329 glyphs at a fractional pen.

The cost is that a word's total width drifts -- mean 0.40 px, worst 2.09 px --
and the next span starts from its own snapped anchor, so the error lands in the
word space and cannot accumulate toward the margin. `scripts/verify_advances.py`
measured 42 px of drift over a *line*, which is why accumulated advances were
refused before; confined to a span it is a different quantity.

`draw` still sets `ImDrawListFlags_TextNoPixelSnap`, now only so that ImGui does
not re-round pens this module has already placed exactly.

Two things had to be true for a frame to run with no backend attached, and both
are easy to hit and unobvious:

- `io.backend_flags` must carry `renderer_has_textures`, or the first `add_text`
  aborts with `IM_ASSERT(atlas->TexIsBuilt)`. It is an abort with a good message
  rather than a crash, which is the merciful case.
- A draw list must come from a live frame. Constructing a bare `ImDrawList` from
  `get_draw_list_shared_data()` outside one **dumps core** rather than raising,
  so do not reach for it as a shortcut.

## One glyph at a time, and the measurement that now backs it

`scripts/verify_advances.py` has been run. ImGui's advances disagree with
fontTools' by enough to matter -- at a nominal 16 px, drift over a 44-character
line reaches 42 px -- so handing `add_text` a whole string would push a word off
the right margin. Every glyph is therefore positioned at the x
`advtext.shipout` computed, one call each. That is now a measurement rather than
a hedge, and the measured residual after the size correction below is about
1 px per 44 characters, which is the floor per-glyph positioning exists to
absorb. Batching whole runs is not available and the numbers say why.

## The size ImGui is asked for is not the size we laid out with

The defect `verify_advances.py` found, and the reason `baked_size_px` exists.
"Size" names two different lengths: `advtext.fontlib` scales a face by
`size / unitsPerEm`, so a size of 16 makes the *em* 16 px, while stb_truetype
scales by pixel *height*, roughly `size / (hhea.ascender - hhea.descender)`. For
Roboto those denominators are 2048 and 2400, so passing our size straight through
bakes every glyph about 12.4% too small.

So the size handed to `add_text` is `size * (ascent + descent) / em`, which is
that denominator expressed in the units the metrics object already carries. This
is the seam to look at first if the text is the wrong size; it is one
multiplication and it is deliberately not folded into anything else.

## The baseline, and the conversion that turned out to be right

`Glyph.y` is **on the baseline**. ImGui's `add_text` takes a **top-left** corner.
The difference is the font's ascent *as ImGui bakes it*, which is why the ascent
comes from `font.get_font_baked(size).ascent` and not from our own metrics.

That was an argument and it is now a measurement. `scripts/verify_ascent.py`
checks the identity `glyph.y0 == baked.ascent - ink_top` against ImGui's own
glyph boxes and finds it holds to 1.6007 px worst case over 90 boxes -- every
face at every size the demo uses -- which is ImGui's whole-pixel quantisation of
a glyph box and not a disagreement. Subtracting the baked ascent is correct, and
substituting
`fontlib`'s ascent -- which differs by up to 4.4 px at 36 px -- would be wrong.
The conversion is self-consistent by construction: a larger baked ascent raises
the top-left and lowers `glyph.y0` by the same amount.

## The synthetic codepoints, and why they now draw

`advtext.fontlib` mints private-use codepoints for glyphs a font leaves
unencoded, which is how the display-size summation (`summation.v1`, a glyph with
no codepoint at all) is named. ImGui rasterises by Unicode codepoint through the
font's own cmap and knows nothing of that minting, so for a while these glyphs
did not draw here at all and `DrawStats.missing` counted them.

`advtext.fontlib.imgui_font_file` closes that gap: it writes our mappings into a
copy of the font's format-12 cmap subtables, and ImGui's own lookup then finds
the glyph unaided. A caller that loads faces through `font_file` rather than
`imgui_font_file` gets the old behaviour, so `DrawStats.missing` stays as the
report rather than becoming dead code -- it is also the honest answer for a font
with no format-12 subtable, which cannot express a plane-15 codepoint at all.

## What is constant across a font key is computed once per call

`docs/guide/future.md` item 2 measured the frame as mostly this module's own
Python re-deriving, for every glyph, things that depend only on the glyph's font
key. `_Preambles` memoises them for the length of one `draw` and no longer: the
lifetime is the invalidation rule, so reloaded fonts, a rebuilt atlas, a changed
density or a different `metrics` are all honoured on the next call with nothing
to flush. It changes no geometry -- the same floats reach the same `add_text`
calls in the same order -- and `_Preambles` says how that was checked.

Deliberately out of scope: clipping (the caller's child window does it), text
shaping, colour per run (the node model carries none), and any caching of draw
lists between frames. The memo above is not that: it holds no draw list, no
vertex and no `ImFontBaked`, and nothing of it survives the call.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, TypeAlias, assert_never

from advtext.fontmetrics import Face
from advtext.nodes import FontKey
from advtext.selection import Rect
from advtext.shipout import DrawCmd, Glyph, Line, RuleRect, SetGlue
from advtext.style import BlockKind, FontSpec, MetricsResolver, fontlib_metrics, parse_font_key
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imgui_bundle import imgui

__all__ = [
    "DrawStats",
    "FaceFont",
    "DARK_DIFF_PALETTE",
    "DARK_PALETTE",
    "DEFAULT_DIFF_PALETTE",
    "DEFAULT_PALETTE",
    "DiffPalette",
    "Palette",
    "baked_size_px",
    "draw",
    "draw_runs",
    "rgba",
    "snap_px",
]


def snap_px(value: float) -> float:
    """
    A device-space coordinate placed on the pixel grid, rounding half up.

    **This does not introduce a quantisation that was not already there.** ImGui
    quantises the pen position itself: `ImFont::RenderText` opens with
    `IM_TRUNC(pos.x)` / `IM_TRUNC(pos.y)` under the comment "Align to be pixel
    perfect", so a fractional pen position is *truncated* before a single quad is
    emitted. Measured here: sweeping a glyph's requested x from 100.0 to 100.99
    in nine steps emits byte-identical vertices every time.

    It can be turned off -- `ImDrawListFlags_TextNoPixelSnap`, new in 1.92.9 --
    and `draw` turns it off. That is now a belt-and-braces measure rather than a
    trade: under `_RigidSpan.pen` every pen this module emits is already a whole
    number of pixels, so `IM_TRUNC` would find nothing to truncate. The flag
    stays because the invariant is worth asserting at the boundary rather than
    trusting, and because a future rule that did place a fractional pen would
    otherwise be silently rounded away with no symptom.

    **The flag has no effect on ImGui's own text path**, which never generates a
    fractional inner position: `scripts/pen_rules.py --native` reads the vertex
    buffer and finds every quad edge on a whole pixel with the flag set or clear.
    `docs/subpixel.md` §4.2 and `docs/advance-rule.md` §2.

    This function places a span's anchor and both edges of an area.

    What this changes is *which* pixel. Truncation is biased half a pixel left
    and up -- every glyph in the document lands on `floor`, never on `ceil` --
    and rounding is the unbiased choice, halving the worst-case departure from
    the position `advtext.shipout` computed from 1.0 px to 0.5 px.

    Half up rather than `round`, which rounds halves to even: ImGui's own
    `IM_ROUND` is `floor(x + 0.5)`, and agreeing with ImGui about which pixel a
    coordinate is on matters more here than agreeing with Python.

    **What is snapped here is accumulated, and the bound on it is a span.** This
    docstring used to say "nothing snapped here is ever accumulated", and that
    stopped being true when `_RigidSpan.pen` began rounding gaps rather than
    offsets. The correctness argument is now about *where* accumulation stops,
    not about whether it happens.

    `pen` adds one rounded gap to the pen the previous glyph actually got, so
    error does accumulate -- but only along a rigid span, and the next span
    starts from its own anchor, snapped from the position `advtext.shipout`
    computed. A span's departure is therefore one whole-pixel rounding of the
    anchor plus the accumulated gap residue of that span alone: measured over
    `demo/sample.md`, a word's width moves by 0.40 px mean and 2.09 px worst, and
    it does not grow with the length of the *line*.

    That distinction is the whole reason this is safe, and the measurement that
    refused accumulation before is still valid on its own terms: rounding each
    advance and summing **across a line** has no bound -- 9.9 px worst and 2.7 px
    median over 70 lines on `demo/sample.md`, which walks the end of a justified
    line nearly two characters past the margin that `tests/test_litmus.py`
    asserts is exact.
    `test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin`
    builds that line-wide implementation and asserts it fails. It must keep
    failing: it is what stops the span-local rule below from being widened to a
    line by someone who reads the two as the same idea.
    """
    return math.floor(value + 0.5)


def baked_size_px(size_px: float, ascent: float, descent: float, em: float) -> float:
    """
    The size to ask ImGui for so its baked glyphs match the em our layout used.

    `ascent`, `descent` and `em` may be in any unit as long as it is the same
    one: only their ratio is used, so a `FontMetrics` at any size answers
    correctly and no scaled-point conversion is needed.

    Pure, and separated from every ImGui call on purpose -- it is the arithmetic
    the module docstring calls the seam to look at first when the text is the
    wrong size, and this is the form in which a test can reach it.

    An `em` of zero yields `size_px` unchanged. That is the degenerate case of a
    metrics object built at size zero; scaling by it would be a division by zero
    and refusing to draw would be worse than drawing at the nominal size.
    """
    if em <= 0.0:
        return size_px
    return size_px * (ascent + descent) / em


def rgba(red: int, green: int, blue: int, alpha: int = 255) -> int:
    """
    Pack a colour the way `IM_COL32` does: alpha, blue, green, red, low byte first.

    Written out rather than taken from ImGui so this module's colours can be
    stated at import time without a live context, and so a test could check them.
    The byte order is ImGui's and is not RGBA despite the name of the macro.
    """
    return (alpha << 24) | (blue << 16) | (green << 8) | red


@dataclass(frozen=True, slots=True)
class DiffPalette:
    """
    The colours of a diff: what `advtext.ui.diff_view.DiffView` draws in.

    Here, beside `Palette` and reached through `Palette.diff`, so that a host
    still states its whole theme in one object and a view still reads no colour
    from anywhere else. Nothing in this module draws a diff; the roles are data.

    **Colour is never the only channel.** An added and a removed line differ in
    ink and in fill, and both of those are hue. What tells them apart without
    it is the `+` or `-` the view always draws in the gutter, in `gutter` ink,
    which is the same in both: pptmstr keeps the marker for exactly this reason
    (its design section 6.1). So nothing here has to survive a greyscale
    conversion, and no claim is made that it does.

    - `add`, `remove`, `context`, `meta`: ink for the text of a line of that
      kind. `meta` is the "no newline at end of file" marker line.
    - `add_fill`, `remove_fill`: the band behind a whole added or removed
      line. Translucent in the defaults, so they tint whatever the host's
      background is rather than replacing it.
    - `add_emphasis`, `remove_emphasis`: the mark behind the part of a line
      that changed, drawn over the fill.
    - `gutter`: line numbers and the `+`/`-` marker.
    - `header`, `header_fill`: a file's or a hunk's header line and the band
      behind it; a collapsed-context line uses them too.
    - `warning`: the "will not apply" label and the other warnings on a file
      header, and the placeholder drawn for a character that cannot be drawn
      as itself -- which can stand anywhere a character can, an emphasis mark
      included.
    - `current`: the bar beside the hunk `next_hunk`/`previous_hunk` is on.

    The defaults are for the light page `Palette()` assumes. The values are
    stated, not recommended: nobody has judged how they look. **One thing
    about them is measured**: in both shipped palettes every ink is at least
    4.5 to 1 (WCAG 2's ratio) against every ground the view draws it on --
    the page, a band over the page, an emphasis mark over its band
    (`tests/test_imgui_draw.py` computes it from the palette; the table of
    which ink meets which ground is there). Until review 3 the gutter's
    marker was 3.91 on the light removed band and the warning ink 2.24 on a
    light emphasis mark. A host that changes a fill should run the same
    arithmetic. Added and removed lines are still nearly the same grey as
    each other, which is the first paragraph's point and is unchanged.
    """

    add: int = rgba(0x11, 0x4B, 0x1F)
    remove: int = rgba(0x7A, 0x12, 0x12)
    context: int = rgba(0x11, 0x11, 0x11)
    meta: int = rgba(0x5E, 0x5E, 0x5E)
    add_fill: int = rgba(0x2E, 0xA0, 0x43, 0x30)
    remove_fill: int = rgba(0xD7, 0x3A, 0x49, 0x30)
    add_emphasis: int = rgba(0x2E, 0xA0, 0x43, 0x66)
    remove_emphasis: int = rgba(0xD7, 0x3A, 0x49, 0x66)
    gutter: int = rgba(0x5E, 0x5E, 0x5E)
    header: int = rgba(0x1D, 0x4E, 0xD8)
    header_fill: int = rgba(0x3B, 0x82, 0xF6, 0x1F)
    warning: int = rgba(0x66, 0x2E, 0x05)
    current: int = rgba(0x3B, 0x82, 0xF6)


DEFAULT_DIFF_PALETTE = DiffPalette()
"""
The diff colours for a light page. A named constant for the reason
`DEFAULT_PALETTE` is one.
"""


DARK_DIFF_PALETTE = DiffPalette(
    add=rgba(0xAF, 0xF5, 0xB4),
    remove=rgba(0xFF, 0xD3, 0xCE),
    context=rgba(0xE6, 0xE6, 0xE6),
    meta=rgba(0xA2, 0xA2, 0xA2),
    add_fill=rgba(0x2E, 0xA0, 0x43, 0x38),
    remove_fill=rgba(0xF8, 0x51, 0x49, 0x38),
    add_emphasis=rgba(0x2E, 0xA0, 0x43, 0x80),
    remove_emphasis=rgba(0xF8, 0x51, 0x49, 0x80),
    gutter=rgba(0xA2, 0xA2, 0xA2),
    header=rgba(0x8A, 0xB4, 0xF8),
    header_fill=rgba(0x3B, 0x82, 0xF6, 0x2E),
    warning=rgba(0xFA, 0xDA, 0xAA),
    current=rgba(0x8A, 0xB4, 0xF8),
)
"""
The diff colours for a dark background: light inks, the same translucent fills
a little stronger. `DARK_PALETTE.diff` is this.
"""


@dataclass(frozen=True, slots=True)
class Palette:
    """
    Every colour this backend can emit, so none of them is buried in a call.

    **`ink` is dark because `page` is light, and a caller that draws the glyphs
    without also drawing the page gets black text on whatever was behind it.**
    ImGui's default theme is dark, so that failure is invisible text rather than
    an error. The pair is the unit; overriding one without the other is the bug
    it is easiest to write here. `advtext.ui.bare_view.BareView` paints no page
    at all, so a host using it supplies ink for *its* background: `DARK_PALETTE`
    is one such, and `Palette(ink=..., rule=..., highlight=...)` is the general
    form.

    The defaults are paper rather than the surrounding chrome being made light.
    That keeps the demo matching the SVG artifacts exactly -- the same ink on
    the same white, so a screenshot and an artifact can be compared -- and it
    is what a document viewer looks like: dark chrome around a light page.

    ## Ink per block role

    `ink` is what every glyph is drawn in unless its block's role says
    otherwise. `roles` holds the otherwise: one colour per `BlockKind` -- each
    heading level, a quote, code, a table, a list item -- for the kinds a host
    wants to differ. Build it with `with_roles`; read it with `ink_for`.

    **The role is the block's, and the colour is applied by the caller of
    `draw_runs`, not carried on a glyph.** `advtext.shipout.Glyph` has no colour
    and gains none: a view that lays a document out as per-block units
    (`advtext.ui.units`) already knows which commands are which block's, and
    hands each run of them over with its ink. So a role's ink covers a whole
    unit. A block quote is one unit however many paragraphs it holds, and takes
    the ink of its first block.

    `rule` colours every rule: a thematic break, the bar down a quote, the line
    under a table's header. `highlight` is the selection. `link` is the ink for
    link text, which nothing in this module draws yet -- it is here so that a
    host states its whole theme in one place and the view that draws links
    reads it from the same one.

    Stored as a tuple of pairs rather than a dict so that a `Palette` stays
    hashable and cannot be edited behind a view that holds it.

    The debug colours carry the same association the SVG backend uses: stretched
    glue reads cool and shrunk glue reads warm, so an overfull line is spottable
    across a page rather than only in a number.
    """

    page: int = rgba(0xFA, 0xFA, 0xF8)
    ink: int = rgba(0x11, 0x11, 0x11)
    rule: int = rgba(0x11, 0x11, 0x11)
    highlight: int = rgba(0x3B, 0x82, 0xF6, 0x4D)
    debug_box: int = rgba(0x22, 0xC5, 0x5E, 0x80)
    debug_baseline: int = rgba(0xEF, 0x44, 0x44, 0x80)
    debug_stretched: int = rgba(0x3B, 0x82, 0xF6, 0x66)
    debug_shrunk: int = rgba(0xF9, 0x73, 0x16, 0x66)
    link: int = rgba(0x1D, 0x4E, 0xD8)
    roles: tuple[tuple[BlockKind, int], ...] = ()
    # The colours of a diff, for `advtext.ui.diff_view.DiffView`; see
    # `DiffPalette`. Like `ink` it is one half of a pair with the background,
    # so a palette for a dark pane names `DARK_DIFF_PALETTE` (or its own).
    diff: DiffPalette = DEFAULT_DIFF_PALETTE

    def ink_for(self, kind: BlockKind) -> int:
        """
        The ink for a block of this kind: its role's if one was given, else `ink`.
        """
        for role, colour in self.roles:
            if role is kind:
                return colour
        return self.ink

    def with_roles(self, roles: Mapping[BlockKind, int]) -> Palette:
        """
        This palette with the given kinds drawn in the given inks.

        Added to whatever roles it already has, the new ones winning. A kind
        not named keeps `ink`. `BlockKind.RULE` is refused rather than ignored:
        a thematic break has no glyphs, its colour is `rule`, and a role that
        silently did nothing is how a host ends up with a black line on a dark
        pane.
        """
        if BlockKind.RULE in roles:
            raise ValueError("a rule has no ink; set `rule` to colour thematic breaks and bars")
        merged = dict(self.roles)
        merged.update(roles)
        ordered = tuple(sorted(merged.items(), key=lambda item: item[0].value))
        return replace(self, roles=ordered)


DEFAULT_PALETTE = Palette()
"""
The palette a caller gets by omitting one.

A module constant rather than a default argument of `Palette()`: an instance
built in a signature is built once at import and shared, which is harmless for a
frozen value and is exactly the pattern `B008` exists to stop people relying on.
Naming it says the sharing is deliberate.
"""


DARK_PALETTE = Palette(
    page=rgba(0x1E, 0x1E, 0x1E),
    ink=rgba(0xE6, 0xE6, 0xE6),
    rule=rgba(0x8A, 0x8A, 0x8A),
    highlight=rgba(0x3B, 0x82, 0xF6, 0x66),
    link=rgba(0x8A, 0xB4, 0xF8),
    diff=DARK_DIFF_PALETTE,
)
"""
Light ink for a dark background, with no role inks.

The counterpart of `DEFAULT_PALETTE` for a host whose pane is dark, and the
palette the tests draw with to show that nothing in the draw path assumes a
light page: every colour `draw_runs` emits is read from the palette it is given.
`page` is what `DocumentView` would fill its sheet with; `BareView` never reads
it. The values are stated, not recommended -- which dark theme a host wants is
the host's to say, and it says it by building its own `Palette`.
"""


FaceFont: TypeAlias = "Callable[[Face], imgui.ImFont | None]"
"""
How a typographic role becomes a loaded ImGui face.

`None` is a usable answer and not an error: ImGui's four-argument `add_text`
draws in whatever face is currently bound, so a missing face degrades to the
default one at the right size and position rather than crashing. pptmstr's
`theme.face` makes the same choice for the same reason.
"""


@dataclass(frozen=True, slots=True)
class DrawStats:
    """
    What one `draw` call managed, so a caller can say what it could not do.

    `missing` counts glyphs the bound face has no raster for, which in this
    project means the synthetic codepoints from a `MATH` variant chain. Counting
    them is the difference between a demo that admits the display sigma is absent
    and one that quietly shows a gap.
    """

    glyphs: int = 0
    missing: int = 0
    rules: int = 0


def draw(
    draw_list: imgui.ImDrawList,
    cmds: Sequence[DrawCmd],
    origin: imgui.ImVec2,
    *,
    fonts: FaceFont,
    palette: Palette = DEFAULT_PALETTE,
    highlights: Sequence[Rect] = (),
    px_per_inch: float = DEFAULT_PX_PER_INCH,
    metrics: MetricsResolver = fontlib_metrics,
    debug: bool = False,
) -> DrawStats:
    """
    Issue a shipped command list to a draw list, anchored at a screen position.

    `origin` is where the document's coordinate (0, 0) goes, in screen pixels.
    Ship with `Point(0, box.height)` so that (0, 0) is the document's top-left
    and every coordinate that arrives here is positive and downward.

    `metrics` must resolve the **same** measurements the packing used, for the
    same reason `advtext.shipout.ship` must -- it is what `baked_size_px` reads
    the em from, so a mismatch draws every glyph at the wrong size. It is
    injected rather than imported so a test can supply round numbers, and it
    defaults to the production resolver.

    Highlights are drawn **first**, so selected text stays readable; rules next,
    glyphs last. The debug overlay goes above everything, exactly as the SVG
    backend orders it, so the two pictures can be compared.
    """
    return draw_runs(
        draw_list,
        ((cmds, palette.ink),),
        origin,
        fonts=fonts,
        palette=palette,
        highlights=highlights,
        px_per_inch=px_per_inch,
        metrics=metrics,
        debug=debug,
    )


def draw_runs(
    draw_list: imgui.ImDrawList,
    runs: Iterable[tuple[Sequence[DrawCmd], int]],
    origin: imgui.ImVec2,
    *,
    fonts: FaceFont,
    palette: Palette = DEFAULT_PALETTE,
    highlights: Sequence[Rect] = (),
    px_per_inch: float = DEFAULT_PX_PER_INCH,
    metrics: MetricsResolver = fontlib_metrics,
    debug: bool = False,
    inks: Sequence[tuple[int, int, int]] = (),
    fills: Sequence[tuple[Rect, int]] = (),
) -> DrawStats:
    """
    `draw`, over several command lists that each have an ink of their own.

    Each run is `(commands, ink)`: the commands are drawn exactly as `draw`
    would draw them, with their glyphs in that colour. Everything else comes
    from `palette` -- rules, the selection highlight, the debug overlay -- and
    `palette.ink` itself is not read here. `draw` is this function with one
    run in `palette.ink`, so the two cannot drift.

    This is how ink per block role reaches the screen without a colour on
    `Glyph`: a view that knows which commands belong to which block passes
    them as runs (`Palette.ink_for` has the role lookup).

    One call rather than one `draw` per run, for two reasons. The highlights
    are drawn once, under everything. And the per-font-key memo (`_Preambles`)
    lives for one call, so a document of forty blocks drawn as forty calls
    would resolve every face forty times.

    A rigid span never crosses from one run into the next, which changes
    nothing in practice: a run begins with the `Line` that introduces its
    first glyphs, and a `Line` ends a span anyway.

    ## Colour finer than a run

    `inks` is the per-run colour channel: `(start, end, colour)` over the
    glyphs' reading-order **indices**, half-open, sorted by `start` and not
    overlapping. A glyph whose index falls in one is drawn in that colour
    instead of its run's ink. This is how a link, a syntax token or one word
    is coloured without `Glyph` carrying a colour: the index is already on the
    command, and the ranges arrive beside the commands
    (`advtext.spans.decorate` builds them). The colour changes nothing about
    where the glyph goes -- the same quad, a different vertex colour.

    `fills` are extra filled rectangles, each with its own colour: the mark
    behind a find-in-document hit, the underline of a link. They are drawn
    **first**, under the selection highlight and under the glyphs, and snapped
    to the pixel grid the way a rule is, so a one-pixel underline keeps its
    pixel.
    """
    from imgui_bundle import imgui

    def at(x: Scaled, y: Scaled) -> imgui.ImVec2:
        """
        A document coordinate as an exact screen position, unrounded.

        **This used to claim "ship-out did the accumulation and rounded once, so
        rounding again would gain nothing". Both halves were false** and the
        comment was load-bearing, so it is worth saying what is actually true.
        `advtext.shipout.ship` takes no `px_per_inch` and performs no pixel
        rounding at all -- it works in scaled points and returns exact
        coordinates -- and ImGui would not do sub-pixel placement unasked:
        `ImFont::RenderText` truncates the pen position to a whole pixel unless
        `ImDrawListFlags_TextNoPixelSnap` is set, which `draw` sets so that
        `_RigidSpan.pen` rather than `IM_TRUNC` decides. See `docs/subpixel.md`
        and `docs/advance-rule.md`.

        Rounding still does not belong *here*, for a different reason. This
        converts corners of areas as well as pen positions, and snapping the two
        edges of a thin rule independently can round them onto the same pixel
        and erase it. So `at` stays exact and each caller snaps in the way its
        own primitive needs: `snap_px` for a pen position, `_snap_span` for an
        area that must keep its ink.
        """
        return imgui.ImVec2(
            origin.x + px_from_sp(x, px_per_inch),
            origin.y + px_from_sp(y, px_per_inch),
        )

    def area(
        x: Scaled, y: Scaled, width: Scaled, height: Scaled
    ) -> tuple[imgui.ImVec2, imgui.ImVec2]:
        """
        The two corners of a filled area, snapped so its edges are pixel edges.

        An area whose corners are fractional is filled with partial coverage
        along every side, so a 1 px rule drawn from y = 10.6 to y = 11.6 comes
        out as two rows of grey instead of one row of black. That is the same
        defect as the glyph one and it is fixed the same way.
        """
        near, far = at(x, y), at(x + width, y + height)
        left, right = _snap_span(near.x, far.x)
        top, bottom = _snap_span(near.y, far.y)
        return imgui.ImVec2(left, top), imgui.ImVec2(right, bottom)

    for rect, colour in fills:
        near, far = area(rect.x, rect.y, rect.width, rect.height)
        draw_list.add_rect_filled(near, far, colour)

    for rect in highlights:
        near, far = area(rect.x, rect.y, rect.width, rect.height)
        draw_list.add_rect_filled(near, far, palette.highlight)

    ink_starts = [start for start, _, _ in inks]

    restore = draw_list.flags
    # `ImFont::RenderText` opens with `IM_TRUNC(pos.x)` under the comment "Align
    # to be pixel perfect", so without this flag every half-pixel `_RigidSpan`
    # computes is rounded back to a whole one underneath us and the change is a
    # no-op with no symptom. Measured on this build: a glyph asked for at
    # x = 100.5 emits its quad at 101.0 with the flag clear and at 101.5 with it
    # set. Set here rather than by the caller because the quantisation it serves
    # is this module's, and a caller that forgot would silently get the old
    # behaviour.
    #
    # Restored rather than left on: the flags belong to a draw list this
    # function borrowed, and ImGui reuses one list for a whole window.
    draw_list.flags = restore | int(imgui.ImDrawListFlags_.text_no_pixel_snap)
    try:
        stats = DrawStats()
        span: _RigidSpan | None = None
        # One memo per call, and it dies with the call: see `_Preambles` for why
        # that lifetime is the invalidation rule and not a missed optimisation.
        preambles = _Preambles(fonts=fonts, metrics=metrics, px_per_inch=px_per_inch)
        # Looked up once here and handed to `_glyph`, which used to import
        # `imgui` for it on every glyph.
        vec2 = imgui.ImVec2
        for cmds, ink in runs:
            span = None
            for cmd in cmds:
                match cmd:
                    case Glyph():
                        colour = ink
                        if ink_starts:
                            # The last range starting at or before this glyph;
                            # the ranges do not overlap, so it is the only
                            # one that can contain it.
                            found = bisect_right(ink_starts, cmd.index) - 1
                            if found >= 0 and cmd.index < inks[found][1]:
                                colour = inks[found][2]
                        stats, span = _glyph(
                            draw_list, cmd, span, at, preambles, colour, px_per_inch, stats, vec2
                        )
                    case RuleRect():
                        span = None
                        near, far = area(cmd.x, cmd.y, cmd.width, cmd.height)
                        draw_list.add_rect_filled(near, far, palette.rule)
                        stats = _with_rule(stats)
                    case SetGlue():
                        span = None
                        if debug:
                            _debug_glue(draw_list, cmd, area, palette)
                    case Line():
                        span = None
                        if debug:
                            _debug_line(draw_list, cmd, area, palette)
                    case _:
                        assert_never(cmd)
    finally:
        draw_list.flags = restore
    return stats


def _snap_span(near: float, far: float) -> tuple[float, float]:
    """
    One axis of an area, snapped to pixel edges without ever losing its ink.

    Both edges round half up, which keeps abutting areas abutting: two rects
    that shared an exact edge still share the snapped one, so a snapped table
    gains no seams and a snapped run of selection rects gains no gaps.

    The exception is the whole reason this is not just two `snap_px` calls. A
    span thinner than a pixel can put both edges on the same pixel boundary, and
    an area of zero extent draws nothing -- so a hairline rule would vanish
    rather than merely thicken. Any span with real extent is therefore widened
    to the one pixel it needs. TeX will happily ask for a rule of 0.4 px at a
    small size; the honest answer on a pixel grid is the thinnest mark the grid
    has, not no mark at all.

    A span of no extent stays empty. That is not a rule too thin to see, it is
    the absence of one, and inventing a pixel for it would draw ink the document
    does not contain.
    """
    lo, hi = snap_px(near), snap_px(far)
    if hi <= lo and far > near:
        return lo, lo + 1.0
    return lo, hi


def _with_rule(stats: DrawStats) -> DrawStats:
    return DrawStats(glyphs=stats.glyphs, missing=stats.missing, rules=stats.rules + 1)


@dataclass(frozen=True, slots=True)
class _RigidSpan:
    r"""
    The anchor a run of glyphs is snapped relative to, and why the run is the unit.

    **The unit is the maximal rigid span, not the word.** `draw` opens one of
    these at a `Glyph` that follows something other than a `Glyph`, and drops it
    at the next `SetGlue`, `Line` or `RuleRect`. That is not a rename of "word":
    measured on `demo/sample.md`, 4 of the 876 spans contain literal space
    characters -- the indentation inside a fenced code block, where a space is a
    rigid `CharNode` and not glue -- and 20 span more than one face, because
    `**bold**text` abutted with no space is one run. Splitting a string on
    spaces would get both of those wrong.

    Rigid is what makes the arithmetic sound, and it is TeX's own structure
    rather than an observation about this document. In `hlist_out` a char node
    advances the pen by `cur_h:=cur_h+char_width(f)(char_info(f)(c))` and by
    nothing else -- §620, `tex.web` line 12375 -- while the *only* place set glue
    enters is `cur_g:=round(glue_temp)` under `Move right or output leaders`,
    which is reached for a glue node and no other -- §625, `tex.web` lines
    12431-12459. Both section numbers were checked against `docs/tex.web` by
    content and by the counting method `docs/tex-notes.md` records, because that
    file warns its numbering was only spot-checked.

    So the scaled-point difference between two glyphs of one span is a function
    of the characters, their kerns and their sizes -- of content -- and of
    nothing about where the line broke or how far it was stretched. Snapping
    that difference therefore yields the same pixel offsets every time the same
    span is set, which is the entire claim.

    **How `pen` relates to TeX's own rounding, which is not "the same principle
    one layer down".** This docstring used to claim that, and it is worth being
    exact instead, because the rule below is a deliberate departure.

    TeX does not round a character advance at all: `hlist_out` does
    `cur_h:=cur_h+char_width(f)(char_info(f)(c))` in scaled points -- `tex.web`
    line 12375 -- and leaves every pixel decision to the DVI driver, which at
    1200 dpi and up is a rounding nobody sees. At 96 dpi somebody has to, and
    that is this module.

    Where TeX *does* quantise a sequence -- set glue, `tex.web` lines 12437-12455
    -- it uses **error diffusion, not summed increments**. It keeps `cur_glue` as
    the exact running total, sets `cur_g:=round(glue_temp)` from that total, and
    spends `width(g) - cur_g_old + cur_g_new`. Each increment is therefore the
    difference of two *rounded running totals*, so increments are whole units and
    the cumulative position never drifts.

    Applied to a span, that technique is exactly `anchor + round(offset)` -- the
    whole-pixel rule this class used to implement. `pen` does the other thing:
    it sums rounded increments, which is what TeX's structure specifically
    avoids. The trade is deliberate and the objectives differ. TeX is protecting
    a *total*, because a line must end on the margin. Inside a rigid span the
    total is absorbed by the following glue, and what the eye reads is the
    *rhythm*, so the gap is the quantity worth keeping honest.
    `docs/advance-rule.md` has the measurements on both sides.

    `x`, `y` and `ascent` are the anchor glyph's exact inputs. `left` and `top`
    are the one snapped screen position in the span, and every other glyph is
    placed by whole-pixel steps from it -- so the whole span moves as a unit and
    nothing inside it can shift by a fraction relative to the rest.

    `prev_x` and `prev_pen` carry the running state: the exact x of the glyph
    placed most recently in this span, and the screen x it was placed at. They
    are the anchor's own values until the second glyph arrives, so a one-glyph
    span never consults them.
    """

    x: Scaled
    y: Scaled
    ascent: float
    left: float
    top: float
    prev_x: Scaled
    prev_pen: float

    def pen(self, cmd: Glyph, ascent: float, px_per_inch: float) -> tuple[float, float, _RigidSpan]:
        """
        Where one glyph of this span goes: the anchor plus a snapped offset.

        The offset is taken in **scaled points** and converted once, rather than
        converted twice and subtracted. `Scaled` is an `int`, so `cmd.x - self.x`
        is exact; `px_from_sp(a) - px_from_sp(b)` is two roundings of a float
        multiply and is not guaranteed to give the same answer for the same
        difference at two different origins. That would be a one-ulp difference
        landing either side of a `.5` boundary, which is exactly the
        inconsistency this class exists to remove, so it is worth the care.

        `origin` cancels out of the offset entirely and only reaches the anchor,
        which is why a window scrolled to a fractional position cannot reshape a
        word.

        The vertical is done the same way, and has to be: `add_text` takes a top
        left corner, so a face change inside a span moves the corner by the
        difference of the two baked ascents. Taking that difference here keeps
        the two halves of `**bold**text` locked together.

        **The two axes are treated differently and that is deliberate.** The
        horizontal accumulates rounded gaps, because the defect the user reported
        is horizontal: inter-letter gaps measured 1, 2, 2 px inside "people" and
        1-4 px inside the heading "What the difference looks like", where `iffe`
        fused into a single 31 px ink run. The vertical is snapped absolutely,
        against the span's own anchor, and never accumulates.

        Nothing asks for the horizontal treatment vertically, and something
        argues against it: `dy` is exactly zero for every glyph of a single-face
        span, so accumulating it would change nothing at all in body text and
        would only ever fire where a span crosses a face -- 20 of
        `demo/sample.md`'s 876 spans -- or at a math script. There it would let a
        superscript's row drift away from the run it belongs to for no gap it
        closes, and a vertical gap between letters is not a thing the eye reads
        as rhythm in the first place.

        It is also, today, a choice with no observable consequence: measured
        over `demo/sample.md`, **3486 of 3486** within-span vertical offsets are
        already a whole number of pixels, and 2 of 2 in the litmus formula. The
        two rules cannot disagree on anything the demo contains, which is why
        the test that pins this is a synthetic raised glyph --
        `test_a_vertical_offset_inside_a_span_stays_on_a_whole_row` -- and not
        the document. If a vertical case ever turns up, this is the one line to
        change and that test is what will go red.

        **The returned span is the one the caller must carry forward.** Under
        `"half"` it is this span unchanged; under `"advance"` it carries the
        running state on. Returning it rather than mutating keeps the class frozen,
        which matters because the span is the thing whose identity guarantees a
        word is drawn the same way twice.
        """
        dy = px_from_sp(cmd.y - self.y, px_per_inch) - (ascent - self.ascent)
        top = self.top + snap_px(dy)

        # The gap from the previously placed glyph, rounded once, added to where
        # that glyph actually went. Every gap is therefore a whole number of
        # pixels and every pen lands on the grid -- the two properties the
        # superseded half-pixel rule could not hold at the same time.
        #
        # Taken in scaled points and converted once, for the reason the paragraph
        # above gives about `cmd.x - self.x`: the difference is exact and a float
        # subtraction of two conversions is not.
        #
        # The anchor itself takes this path with `cmd.x == self.prev_x`, so the
        # step is zero and it lands on `left`. No special case.
        step = px_from_sp(cmd.x - self.prev_x, px_per_inch)
        pen_x = self.prev_pen + snap_px(step)
        #
        # The successor is built by naming every field rather than with
        # `dataclasses.replace`, which did the same thing through a generic
        # field walk and was, once the preamble was memoised, the largest single
        # cost left in a frame: 4362 calls a draw of `demo/sample.md`.
        return (
            pen_x,
            top,
            _RigidSpan(
                x=self.x,
                y=self.y,
                ascent=self.ascent,
                left=self.left,
                top=self.top,
                prev_x=cmd.x,
                prev_pen=pen_x,
            ),
        )


@dataclass(slots=True)
class _Preamble:
    """
    What `_glyph` needs to know about one font key, resolved once per `draw`.

    `font` and `spec` are filled when the key is first seen. `size` and `ascent`
    are ImGui's baked numbers and are filled only when the key first has a glyph
    to *draw* -- `size is None` until then -- because the unmemoised `_glyph`
    returned on a missing glyph before it consulted `metrics` or asked ImGui to
    bake anything, and a face none of whose glyphs can be drawn should still not
    cost an `ImFontBaked` nobody uses.

    `characters` answers `is_glyph_in_font` and `chr` together: the string to
    hand `add_text` for a codepoint, or `None` for one the face has no raster
    for. Keyed by codepoint inside a key, not by `ImFont`, which costs one
    duplicate probe per size a face is used at and saves a second lookup on
    every glyph.

    **The baked numbers are held as floats and the `ImFontBaked` is not held at
    all.** `tests/test_imgui_draw.py`'s `imgui_context` fixture records that an
    `ImFontBaked` is only good for the current frame; two floats copied out of
    one have no lifetime to get wrong.
    """

    font: imgui.ImFont | None
    spec: FontSpec
    size: float | None = None
    ascent: float = 0.0
    characters: dict[int, str | None] = field(default_factory=dict)


@dataclass(slots=True)
class _Preambles:
    """
    The per-glyph preamble, memoised by font key for the length of one `draw`.

    `docs/guide/future.md` item 2 is the case for it: `_glyph` used to re-derive
    for every glyph four things that are constant across every glyph of a font
    key -- `parse_font_key` on the same string, `fonts` on the same face,
    `metrics` and `baked_size_px` on the same key, and `get_font_baked` for the
    same size -- and a fifth, `is_glyph_in_font`, that is constant per
    (key, codepoint). At the measure `tests/test_imgui_draw.py` sets it,
    `demo/sample.md` ships 4362 glyphs over 8 keys.

    **It changes no geometry, and that is measured rather than argued.** Every
    value cached here is one the unmemoised code computed from the key alone, so
    the same floats reach the same `add_text` calls in the same order. The module
    as it stood before was kept beside this one and both were given the same
    command lists -- `demo/sample.md` at four origins, two of them fractional,
    with and without the debug overlay, at 96 and 120 px per inch, with no faces
    bound, and the litmus formula. The `add_text` and rectangle calls compared
    equal argument for argument through a recording draw list, and the vertex
    and index buffers of a real frame compared equal element for element.
    `.concerns/A4-draw--builder--result.md` has the figures and what the
    comparison could not see.

    ## The lifetime is one call, and that is the invalidation rule

    Nothing here outlives the `draw` that built it. That is deliberate and it is
    the whole answer to "what if the fonts are reloaded": a host that rebuilds
    its atlas, swaps the `ImFont` a face maps to, changes `px_per_inch` on a DPI
    move or passes a different `metrics` gets a memo built from the new values
    on the very next call, because there is no older memo to be wrong.

    A memo held across frames would be faster by the cost of resolving eight
    keys -- microseconds against a frame of milliseconds -- and would need to
    know every one of those events. ImGui 1.92 bakes glyphs on demand and
    discards an `ImFontBaked` nobody has used for a while, and an `ImFont` is a
    pointer into an atlas a host is free to clear; a stale entry there is at
    best a wrong ascent and at worst a freed pointer handed to `add_text`.
    Nothing in this project can observe those events, so the cache is scoped to
    the one interval in which none of them can happen: the borrowed draw list's
    own frame. The module docstring's "no caching of draw lists between frames"
    still stands and this does not weaken it.

    What a call does assume is that its *own* arguments are stable while it
    runs: `fonts(face)` answers the same for a face each time it is asked,
    `metrics(key)` likewise, and a face does not gain or lose a glyph between
    two commands of one list. The unmemoised code asked each question once per
    glyph and would have drawn one word in two faces had the answer changed
    mid-list, which no caller wants either.
    """

    fonts: FaceFont
    metrics: MetricsResolver
    px_per_inch: float
    _by_key: dict[FontKey, _Preamble] = field(default_factory=dict)

    def of(self, key: FontKey) -> _Preamble:
        """
        The preamble for a key, resolving its face on first sight.
        """
        try:
            return self._by_key[key]
        except KeyError:
            spec = parse_font_key(key)
            found = self._by_key[key] = _Preamble(font=self.fonts(spec.face), spec=spec)
            return found

    def character(self, preamble: _Preamble, codepoint: int) -> str | None:
        """
        The string to draw for a codepoint, or `None` if the face cannot raster it.

        With no bound face there is nothing to ask, and the glyph is drawn in
        whatever face is current -- see `FaceFont`.
        """
        try:
            return preamble.characters[codepoint]
        except KeyError:
            font = preamble.font
            absent = font is not None and not font.is_glyph_in_font(codepoint)
            found = preamble.characters[codepoint] = None if absent else chr(codepoint)
            return found

    def bake(self, key: FontKey, preamble: _Preamble) -> tuple[float, float]:
        """
        ImGui's baked size and ascent for a key, asked for once.

        The arithmetic is the module docstring's "seam to look at first" and it
        is unchanged: our em size, corrected to stb_truetype's pixel height by
        `baked_size_px`, then quantised by ImGui itself in `_baked`.
        """
        size = preamble.size
        if size is None:
            ours = self.metrics(key)
            size_px = baked_size_px(
                px_from_sp(preamble.spec.size, self.px_per_inch),
                ours.ascent,
                ours.descent,
                ours.em,
            )
            baked = _baked(preamble.font, size_px)
            size = preamble.size = baked.size
            preamble.ascent = baked.ascent
        return size, preamble.ascent


def _glyph(
    draw_list: imgui.ImDrawList,
    cmd: Glyph,
    span: _RigidSpan | None,
    at: Callable[[Scaled, Scaled], imgui.ImVec2],
    preambles: _Preambles,
    ink: int,
    px_per_inch: float,
    stats: DrawStats,
    vec2: Callable[[float, float], imgui.ImVec2],
) -> tuple[DrawStats, _RigidSpan | None]:
    """
    One glyph, placed relative to the rigid span it belongs to.

    `span` is the run this glyph continues, or `None` if it opens one; the
    returned span is what the next glyph continues. A glyph the face cannot
    raster neither opens a span nor closes one -- it draws nothing, so it has no
    anchor to offer, and it is not a glue node so the run is still rigid across
    it.

    Everything that depends only on the glyph's font key comes from `preambles`
    and is computed once per `draw`; what is left here is what depends on *this*
    glyph -- where it is and which span it is in.

    `vec2` is `imgui.ImVec2`, passed in. This function ran `from imgui_bundle
    import imgui` to reach it, which is a dictionary lookup and a call into
    the import machinery per glyph: 21,895 `_handle_fromlist` calls for five
    draws of `demo/sample.md` under cProfile (review 5, item 6). The module
    cannot import ImGui at the top -- it has to be importable without it --
    so the one caller, which has it already, hands the constructor over.
    """
    preamble = preambles.of(cmd.font)
    character = preambles.character(preamble, cmd.codepoint)

    if character is None:
        # A codepoint the bound face has no raster for. It is counted rather than
        # drawn, and the count is the report: see the module docstring on
        # `advtext.fontlib.imgui_font_file`, which is what stops a synthetic
        # codepoint from a MATH variant chain arriving here in the first place.
        return DrawStats(glyphs=stats.glyphs, missing=stats.missing + 1, rules=stats.rules), span

    size, ascent = preambles.bake(cmd.font, preamble)
    if span is None:
        baseline = at(cmd.x, cmd.y)
        span = _RigidSpan(
            x=cmd.x,
            y=cmd.y,
            ascent=ascent,
            left=snap_px(baseline.x),
            top=snap_px(baseline.y - ascent),
            prev_x=cmd.x,
            prev_pen=snap_px(baseline.x),
        )
    pen_x, pen_y, span = span.pen(cmd, ascent, px_per_inch)
    position = vec2(pen_x, pen_y)
    font = preamble.font
    if font is None:
        draw_list.add_text(position, ink, character)
    else:
        # The five-argument overload, which is the only one that takes a size,
        # and the baked size rather than the one `baked_size_px` computed is the
        # fix described on `_baked`.
        draw_list.add_text(font, size, position, ink, character)
    return DrawStats(glyphs=stats.glyphs + 1, missing=stats.missing, rules=stats.rules), span


def _baked(font: imgui.ImFont | None, size_px: float) -> imgui.ImFontBaked:
    """
    ImGui's own baked face at a size. Two numbers come from here, for two reasons.

    **The ascent**, because `add_text` takes a top-left corner and measures down
    from the ascent *it* baked. `advtext.fontmetrics` may disagree, and for
    positioning against ImGui's convention ImGui's number is correct by
    definition. `scripts/verify_ascent.py` measures the two agreeing to 1.6 px
    worst case over 90 boxes.

    **The size**, and this is the fix for the resampling defect `docs/subpixel.md`
    records. ImGui 1.92 does not bake at an arbitrary float: `GetFontBaked`
    quantises to `floor(size + 0.5)`, measured here across every size this demo
    asks for, from 13.637 up to 42.1875. It then draws that baked bitmap scaled
    by `size / baked.size`. Ask for 18.75 and you get the 19 px raster squashed
    to 98.68%, which puts every quad corner off the pixel grid *and* makes the
    quad a non-integer number of texels wide, so the GPU resamples a bitmap that
    was already exactly the right shape. Measured before this change: a glyph
    asked for at (100.0, 300.0) emitted a quad at (100.976562, 306.835938).

    Asking for `baked.size` selects **the same raster** -- it is the same
    `ImFontBaked`, same atlas coordinates, same ascent -- and draws it one texel
    to one pixel. The cost is that the em is up to half a pixel from the size
    `baked_size_px` computed. That is a real loss and it is the smaller one: the
    half pixel was never being honoured anyway, it was being approximated by
    blurring a raster that had already been rounded to the same whole number.
    """
    from imgui_bundle import imgui

    if font is None:
        # No bound face to interrogate; the current one is what will be drawn.
        return imgui.get_font_baked()
    return font.get_font_baked(size_px)


Area: TypeAlias = "Callable[[Scaled, Scaled, Scaled, Scaled], tuple[imgui.ImVec2, imgui.ImVec2]]"
"""
A document rectangle as its two snapped screen corners: `draw`'s local `area`.

Passed in rather than rebuilt so the overlay lands on exactly the pixels the ink
it annotates landed on. An overlay a pixel off its own baseline would be read as
the layout bug it exists to reveal.
"""


def _debug_line(
    draw_list: imgui.ImDrawList,
    cmd: Line,
    area: Area,
    palette: Palette,
) -> None:
    """
    One line's box and its baseline: the fastest way to see a layout bug.
    """
    top_left, bottom_right = area(cmd.x, cmd.y - cmd.height, cmd.width, cmd.height + cmd.depth)
    draw_list.add_rect(top_left, bottom_right, palette.debug_box)
    start, end = area(cmd.x, cmd.y, cmd.width, 0)
    draw_list.add_line(start, end, palette.debug_baseline, 1.0)


def _debug_glue(
    draw_list: imgui.ImDrawList,
    cmd: SetGlue,
    area: Area,
    palette: Palette,
) -> None:
    """
    An interword space, coloured by whether it was stretched or squeezed.

    This is the only place in a rendered document where the line breaker's
    decision is visible as a picture rather than as a number.
    """
    if cmd.width == cmd.natural:
        return
    colour = palette.debug_stretched if cmd.width > cmd.natural else palette.debug_shrunk
    top_left, bottom_right = area(cmd.x, cmd.y - cmd.height, cmd.width, cmd.height + cmd.depth)
    draw_list.add_rect_filled(top_left, bottom_right, colour)

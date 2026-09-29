# Rendering, and where it departs from both parents

Layout knows nothing about pixels. Everything here happens in
`advtext/backends/imgui_draw.py`, in device space, after `ship()` has produced
exact scaled-point coordinates.

There are four decisions and they compose. Each was forced by a measurement, and
each is reproducible: `scripts/pen_rules.py`, `scripts/verify_advances.py`,
`scripts/verify_ascent.py`, `scripts/visual_diff.py`.

## 1. Ask ImGui for the size it is going to bake anyway

"Size" names two different lengths. `advtext.fontlib` scales a face by
`size / unitsPerEm`, so a size of 16 makes the *em* 16 px. stb_truetype scales by
pixel *height*, roughly `size / (ascender - descender)`. For Roboto those
denominators are 2048 and 2400, so passing our size straight through baked every
glyph about **12.4% too small**.

`baked_size_px` converts between them. Without it every quad was a non-integer
number of texels wide and the GPU resampled a bitmap that was already exactly
right — measured at **1734 of 1734** glyph quads in `demo/sample.md`. This is the
seam to check first if text is the wrong size.

## 2. Round the pen, rather than letting ImGui truncate it

`ImFont::RenderText` opens with `IM_TRUNC(pos.x)`, which is biased half a pixel
left: every glyph lands on `floor`, never on `ceil`. `snap_px` rounds half-up
instead, matching ImGui's own `IM_ROUND` so the two agree about which pixel a
coordinate is on. Half-up and not Python's `round`, which is banker's.

## 3. Snap the span, not the glyph

A **rigid span** is a run of glyphs with no glue in it — a word, near enough, but
defined structurally rather than by splitting on spaces (4 of 876 spans in
`demo/sample.md` contain literal space characters inside fenced code, and 20 span
more than one face because `**bold**text` abuts with no space).

Snapping each glyph's absolute position independently makes the gaps *inside* a
word depend on where the word happens to fall, so the same word sets at two
different shapes in two different places — **67 of 496** distinct spans. Anchoring
the span and placing every glyph relative to that one snapped point takes it to
**0 of 496**, because within a rigid span the scaled-point offsets are a function
of the characters and their kerns and of nothing about where the line broke.

This was a taste trade and the user made it, accepting more rendered rag:
*"I think I would take a little more rag on the right justification line if the
text looks better."*

## 4. Round the gaps, not the positions

`docs/advance-rule.md` is the write-up. This is the most recent decision and the
one with the most surprising provenance.

Rounding each glyph's *offset from the anchor* independently means an inter-letter
gap is `round(next) − round(this)`, which can be a **whole pixel** from the gap
the designer drew — **478 of 3453** adjacent pairs. That is the defect behind
"people" setting at gaps of 1, 2, 2 px, and behind `iffe` in a heading fusing into
a single 31 px ink run.

`_RigidSpan.pen` rounds each *gap* to a whole pixel and accumulates from the
anchor. Result: every gap within half a pixel of the design, **and** every glyph
on the pixel grid, so nothing is resampled. Measured: **0 of 4329** fractional
pens, **0 of 3453** gaps past half a pixel, **0 of 496** spans at two shapes.

The cost is that a word's total width drifts — mean 0.40 px, worst 2.09 px — and
a glyph's worst departure from its computed position goes from 0.99 px to
**2.74 px**. The error cannot cross a glue node, because every span restarts from
its own anchor snapped straight from ship-out's coordinate.

---

## Divergence 1: from TeX

**TeX never rounds a character advance.** `hlist_out` does
`cur_h := cur_h + char_width(f)(char_info(f)(c))` in exact scaled points
(`tex.web` line 12375) and leaves every pixel decision to the DVI driver.

**Where TeX does quantise a sequence — set glue — it uses error diffusion, not
summed increments** (`tex.web` lines 12437-12455):

    rule_wd := width(g) - cur_g;        { subtract the previous rounded total }
    cur_glue := cur_glue + stretch(g);  { exact running total }
    cur_g := round(glue_temp);          { round the TOTAL, not the increment }
    rule_wd := rule_wd + cur_g;

Each increment is the difference of two *rounded running totals*, so increments
stay whole and the cumulative position never drifts.

Applied to a span, that technique is exactly `anchor + round(offset)` — decision 3
above, without decision 4. **So the rule that ships is a deliberate departure
from TeX**, not an approach to it.

The justification is that the objectives differ. TeX is protecting a **total**,
because a line must land on its margin. Inside a rigid span the total is absorbed
by the following glue, while the **rhythm** is what the eye reads. Different
objective, different optimal rounding. Knuth's technique is still the right answer
at the glue node, and that is where this project also uses it: the span anchor is
`snap_px` of the exact position, which is a rounded total.

## Divergence 2: from ImGui

ImGui was measured rather than assumed — imgui_bundle ships no headers, so
`scripts/pen_rules.py --native` reads `ImDrawList.vtx_buffer` directly.

- **ImGui rounds advances and accumulates.** Every inner glyph position it emits
  is a whole pixel, flag set or clear. A claim in this project's own docstrings
  that it accumulated *unrounded* advances was wrong, twice.
- **ImGui applies no kerning at all.** We read GPOS pair kerns in `fontlib`. That
  is a real difference in the designed positions, not just in their rounding.
- **ImGui's advances disagree with fontTools'.** Drift over a 44-character line
  reaches **42 px** at a nominal 16 px, which is why every glyph is positioned
  individually rather than handed to `add_text` as a string. After the size
  correction the residual is about 1 px per 44 characters — the floor that
  per-glyph positioning exists to absorb.
- **`ImDrawListFlags_TextNoPixelSnap` is set** by `draw`, and restored, because
  the flags belong to a draw list ImGui reuses for a whole window. Under the
  current rule every pen is already an integer, so this is defensive rather than
  load-bearing — it stops a future fractional pen being silently rounded away
  with no symptom.

## The thing that makes the whole trade disappear

None of the above is needed if the font's advances already land on the pixel grid.

`scripts/font_grid.py` measures this. Times and Helvetica metrics are laid out on
an **18-unit em**, so at 18 px one design unit is exactly one pixel. Liberation
Serif at 18 px renders identically under whole-pixel and half-pixel rules, because
there is nothing left to correct; Roboto at 16 px does not, and no proportional
face at 16 px is meaningfully better than another.

Kerning is the catch and it picks the winner: Nimbus Roman has the same advances
but kerns 780 pairs and loses most of the advantage, where Liberation kerns 58 and
keeps it.

The property holds at whole multiples of 18. The current 1.25 type scale puts
headings at 22.5 / 28.1 / 35.2 px, which are off it — which is exactly where
grid-related defects still show. A ladder on multiples of 9 would hold it.

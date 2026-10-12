# Rounding the gaps instead of the positions

> **2026-10-12:** the package this document calls `advtext` was renamed `imscribe` (`advtext/…` is `imscribe/…`, `import advtext` is `import imscribe`). Nothing below was changed for it.

**Status: this is what the tree draws.** The half-pixel rule it replaced is
`docs/subpixel.md` §6.3, which remains the record of why that rule was taken and
is superseded rather than deleted.

Every number below comes from `scripts/pen_rules.py` against the working tree.
Re-run it rather than trusting this file — `docs/status.md` Provenance is the
standard, and the most common defect this project has had is a confident figure
nobody could re-derive:

    .venv/bin/python scripts/pen_rules.py
    .venv/bin/python scripts/pen_rules.py --native

---

## 1. Summary

ImGui and this project both place glyphs on whole pixels, and they are **not
doing the same thing**. The difference explains a defect that had been attributed
to the wrong cause for the whole of the sub-pixel investigation.

| | what is rounded | a gap's error | total width |
|---|---|---|---|
| ours (`whole`) | each **position**, from the span anchor | up to a **full pixel** | correct |
| ImGui | each **advance**, accumulated | at most **half** a pixel | drifts |

Rounding positions independently means an inter-letter gap is
`round(oᵢ₊₁) − round(oᵢ)`, which can be a whole pixel away from the gap the
designer drew. On `demo/sample.md` that happens to **478 of 3453** adjacent
pairs. Rounding each advance instead bounds every gap error at half a pixel and
puts every glyph on the grid — at the cost of the word's total width drifting.

Confining that drift to a **span** rather than a line is what makes it affordable,
and section 4 is why.

## 2. What ImGui actually does, read from the vertex buffer

This was twice asserted from this project's own docstrings — that
`ImFont::RenderText` truncates the origin once and then accumulates *unrounded*
advances — and it was wrong both times. imgui_bundle ships no headers, so it was
measured: one `add_text` of a whole word, then the quad geometry read straight out
of `ImDrawList.vtx_buffer`, which is upstream of any rasterisation.

At 16 px Roboto with the origin at x = 100.0, the quad left edges are

    people      [100, 108, 115, 123, 132, 134]                       fractional: 0 of 6
    counting    [100, 107, 115, 123, 131, 136, 139, 147]             fractional: 0 of 8
    difference  [100, 108, 111, 116, 121, 128, 133, 140, 148, 155]   fractional: 0 of 10

**Every inner glyph position is a whole pixel**, identically so whether
`ImDrawListFlags_TextNoPixelSnap` is set or clear. ImGui rounds each advance and
accumulates; it does no sub-pixel intra-word placement at all.

Two consequences worth stating, because both correct something believed earlier:

- ImGui's UI text is not even-spaced because it declines to quantise. It
  quantises thoroughly. Whatever makes it read well is not the absence of
  rounding.
- The flag this project sets in `draw` has **no effect on ImGui's own text path**.
  It matters only because *we* hand `add_text` fractional positions; ImGui never
  generates one itself.

## 3. The four rules

Defined in `scripts/pen_rules.py`. All four place glyphs relative to a span anchor
that `snap_px` has already put on a whole pixel.

    whole     each glyph's offset from the anchor, rounded to 1 px
    half      each offset rounded to 0.5 px          (superseded; §6.3)
    advance   each gap rounded to 1 px, accumulated from the anchor  (ships)
    exact     no rounding of the offset at all

Only `advance` exists in `advtext.backends.imgui_draw`. The other three live in
`scripts/pen_rules.py` alone, because a comparison that can only see the rule
that won cannot show why it won.

**Snapping the anchor first is load-bearing and is not a detail.** It is what
prevents a word landing on two sub-pixel phases in two places. A harness that
skipped it made all four rules appear to phase across sub-pixel origins, and the
defect read as a property of the rules rather than of the harness. Anyone building
a placement experiment should check this first.

## 4. Why ImGui's drift objection does not apply inside a word

`scripts/verify_advances.py` measured **42 px** of accumulated error over a
44-character line, and that measurement is why this project refused accumulated
advances in the first place. It remains correct.

**It was measured over a line.** A rigid span is a *word*. Under `advance`, rounded
advances accumulate only within a span, and the next span begins at its own
independently snapped anchor — so error cannot cross a glue node and cannot reach
the margin. What was an unbounded drift over a line becomes a bounded error over a
word, and the inter-word space absorbs it.

Measured: a word's total width moves by mean **0.3984 px**, worst **2.0938 px**,
with **66 of 824** words off by at least a pixel.

## 5. The four axes

Reducing these to a single score is exactly how a rule that fixes one axis and
wrecks another gets adopted, so the tool prints all four and this table keeps them
apart.

| rule | spans at 2 shapes | fractional pens | gap err mean | gap err max | gaps off by >½ px | phases |
|---|---|---|---|---|---|---|
| whole | 0 of 496 | **0 of 4329** | 0.2517 px | 0.9766 px | **478 of 3453** | 1 |
| half | 0 of 496 | 1444 of 4329 | 0.1433 px | 0.4766 px | 0 of 3453 | 2 |
| **advance** | **0 of 496** | **0 of 4329** | 0.2018 px | **0.4982 px** | **0 of 3453** | **1** |
| exact | 0 of 496 | 3456 of 4329 | 0.0000 px | 0.0000 px | 0 of 3453 | **1303** |

Three readings, and the first is the one that changes how the rest of this
document should be understood:

- **Consistency is free, and is not what any of this buys.** All four rules draw
  every span key at exactly one shape. That property comes from the whole-pixel
  anchor plus offsets being a function of characters and kerns alone — not from
  the quantum. No rule here puts it at risk, and arguments that defend a quantum
  on consistency grounds are defending something already guaranteed.
- **`advance` is not a compromise between `whole` and `half`.** It matches `whole`
  on the unfuzzed axis exactly — zero fractional pens, one phase, every glyph
  drawn at the phase it was baked at — while matching `half` on gap evenness, with
  zero gaps more than half a pixel from the design.
- **`exact` is disqualified on the unfuzzed axis**, at **1303** distinct phases:
  very nearly every glyph at its own. Its perfect gap fidelity is real and is not
  worth that. This is recorded because `exact` was proposed as "best of both" on
  the strength of the fidelity column alone.

## 6. The appearance judgement, which is the user's

Roboto at 16 px, typeset four ways in one frame, one atlas, one whole-pixel
origin, magnified 6×, rows ordered `native, whole, half, advance`. Shown to the
user, whose call this is under `docs/visual-review.md`:

> "out of the four different techniques the 'advance' looks absolutely the best
> with all problem words and even, in my reading, better than native."

And earlier, on the shipped half-pixel rule:

> "between the trade-off of slight fuzziness and well placed type setting
> (distance), I prefer the half step rendering."

The stated ordering is therefore **advance > half > whole**, with `advance` also
placed above ImGui's own rendering. No measurement in this document is offered as
evidence for that ordering. A metric establishes change; it never establishes
quality.

## 7. What is not established

- **Ragged right: measured, and milder than feared. The premise of the fear was
  wrong.** The worry was that a word's width error, which justification hides in
  stretching glue, would stand out against ragged right's uniform space rhythm.
  Ragged right has no such rhythm to disturb: word spaces measured within a
  single render already vary with **sd 1.51 px** over 283 spaces before this rule
  touches them, from anchor rounding of a nominally constant ~4.5 px space.
  `advance` takes that to **sd 1.59** over 284, with a heavier tail at 7 px (6
  occurrences to 18). Justified moves 2.00 to 2.07 over the same document.

  **A caveat this method cannot measure away.** `advance` is sharper, so its ink
  is narrower, so every gap reads slightly wider at an ink threshold. Some of the
  mean shift (4.97 to 5.11 px) and some of the sd change is antialiasing rather
  than geometry, and a threshold-based measurement cannot separate the two. A
  geometric measurement taken from the layout rather than from pixels would, and
  has not been done.
- **An unexplained anomaly: ImGui's own text measures softer than `whole` or
  `advance`.** On the same face, atlas and frame, "people" reads solid 8.1% /
  midtone 84.9% under ImGui's path against 18.4% / 72.3% under both `whole` and
  `advance` — yet section 2 shows ImGui's pens are all integers, which should make
  it exactly as sharp. Candidates not yet tested: a baked-size mismatch between
  `add_font_from_file_ttf` and `add_text`, or differing atlas UVs between the two
  paths. **Until this is explained, ImGui's rendering must not be used as the
  reference point for sharpness.**
- **Letter fusion: checked, and it goes the other way.** An earlier count in a
  synthetic harness suggested `advance` merged one more adjacent pair than
  `whole` on "difference". That harness was the one with the unsnapped-anchor bug
  in §3. Re-measured on the real render of the heading "What the difference looks
  like", `advance` yields **15** ink clusters against `half`'s 14 — letters come
  apart rather than together, in the word whose `iffe` originally fused into a
  single 31 px run. The cross-render cluster count is still an ink-threshold
  statistic taken across an antialiasing change, so it establishes direction and
  not magnitude.
- **Error diffusion is unmeasured.** Carrying the residual and flipping a rounding
  when the accumulated position strays past half a pixel should cut the 2.09 px
  worst case while keeping every gap an integer. Nobody has tried it.
- **Nothing was measured on an on-grid face.** At Liberation Serif 18 px, `whole`
  and `half` already render byte-identically because the design puts every offset
  on a whole pixel, so `advance` should be a no-op there. Untested.
- **Scope.** One face, one size, three words, one document. No digits,
  punctuation, ligatures, math, or headings.

## 8. Board history

`advance` is option **B1** of T20-letterfit, "error-diffused rounding within the
span", which was investigated and then deliberately left unimplemented when the
user chose half-pixel quantisation instead. That closure recorded the condition
for reopening it: that half-pixel should prove insufficient, and that B1 be
boarded fresh with its own measurements rather than inherited. Sections 5 and 6
are those measurements.

It is a **draw-time rule**. It needs nothing from `advtext/style.py` — which is
what mis-scoped T20, putting a decided piece of work behind a file it never had to
touch.

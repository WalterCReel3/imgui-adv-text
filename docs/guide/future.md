# Future work

Ordered by what a measurement says, not by appetite. `docs/status.md` section 6
is the older version of this list; where the two disagree, the numbers here were
taken more recently.

## 1. Hyphenation

The largest visible defect with a measured price, and the one whose absence is
now costing something.

Raising `\tolerance` was the workaround for having no hyphenation. Lowering it
again without hyphenation brings back seven overfull lines; leaving it raised
buys loose lines that have been reviewed and called unacceptable. So the decision
to scope hyphenation out is the decision currently being paid for.

Roughly 1000 lines, with the worst interaction in TeX: ligature reconstruction,
§915-916. `docs/tex-notes.md` flags the trap and `docs/decisions.md` records why
it was refused. Nothing about the refusal was wrong at the time; the cost simply
became visible.

## 2. Memoise the per-glyph preamble in `imgui_draw._glyph`

The cheapest large win available, and it changes no geometry.

Drawing `demo/sample.md` costs **26 ms per frame against a 16.7 ms budget** at
best, and 39-45 ms on a loaded machine, with layout fully cached.
`scripts/bench_draw.py` decomposes it: **ImGui's own work is 1.3-2.2 ms**. The
rest is our Python re-deriving, per glyph, values constant across the document's
71 runs — `parse_font_key` re-parsing the same string, `fontlib_metrics`
re-resolving the same face, `baked_size_px` recomputing the same ratio.

Batching glyphs into fewer `add_text` calls is the intuitive fix and the benchmark
prices it at **0.05 ms against 1.3 ms** — it can only reclaim what ImGui was
already doing cheaply, and it would cost the per-glyph positioning that the
measured advance disagreement exists to absorb. Culling is already done and holds
a frame at 9.4 ms however long the document gets, but 9.4 ms of a 16.7 ms budget
is still worth reclaiming.

## 3. Error diffusion for the advance rule

The one refinement with a named precedent rather than a guess, and it comes from
TeX itself.

The shipped rule accumulates rounded gaps within a span, so a word's total width
drifts — 2.09 px worst, and a glyph's worst departure from its computed position
is 2.74 px. TeX's own technique for quantising a sequence (`tex.web` lines
12437-12455) carries the exact running total and rounds *that*, so increments stay
whole while the cumulative position never drifts.

A hybrid — round gaps, but carry the residual and flip a rounding when the
accumulated position strays past half a pixel — should bound **both** quantities.
It is the other half of what was boarded as option B1 and never built.
`scripts/pen_rules.py` already has the harness to measure it against the other
four rules.

## 4. Give the column splitter something to cut inside a block

The one structural limit on the capability the columns work added: no block
boundary is a legal break, so a list or a table taller than a column overhangs
it. This is a change to how `advtext.ui` composes rather than to
`advtext/columns.py`.

## 5. The font-grid question, which is really a decision

`scripts/font_grid.py` establishes that the pixel-grid trade disappears entirely
on a face whose advances are whole pixels at the rendering size. Liberation Serif
at 18 px is such a face and renders identically under every placement rule tested.

What stands between that and shipping:

- **It is an appearance decision and nobody has chosen.** Whether this demo should
  wear a Times-metric serif is not a question a metric answers.
- **Licensing.** `fonts-liberation2` is SIL OFL 1.1 and bundleable; `fonts-liberation`
  (v1) is GPLv2 with a font exception. Both are installed on the development
  machine under the same family name with identical advances, which is a trap.
  The Croscore faces (Tinos, Arimo, Cousine — Apache 2.0, Times/Arial/Courier
  metrics) are the strongest untested candidates; Liberation 2.x derives from
  them. Microsoft's core fonts permit redistribution only as the unmodified
  original archive, so they can be an install-time fetch and never a bundle —
  verify against the actual EULA before depending on it.
- **The heading ladder.** The property holds at whole multiples of 18, and the
  current 1.25 type scale puts headings at 22.5 / 28.1 / 35.2 px, which are off
  it. A ladder on multiples of 9 would hold it, but that is a type-scale change
  and nobody has looked at whether it reads as one.

## 6. FreeType hinting

The strategy this project does not have and has never tested.

Every placement rule here moves glyphs; none reshapes a stem onto the grid.
Grid-fitting is what gets sharp stems *and* designed spacing simultaneously on an
off-grid face, it is what Metafont did for TeX, and stb_truetype does none of it.
ImGui can be built against `imgui_freetype`, which supports light hinting. Whether
imgui_bundle exposes it is unknown; no attribute search found one.

## 7. Delta nodes in `try_break`

The fix for the 82% of composition that `hpack` re-walking accounts for, and the
one change that would silently alter *which* breakpoints win rather than failing
loudly. If it is ever taken, the brute-force optimality test is what must guard
it. Only worth doing if performance still matters after item 2.

---

## A direction rather than a work item

**Porting to a C++ ImGui extension.** `docs/cpp-extension.md` is the design note.
The short version: the argument that survives scrutiny is not performance but a
capability — ImGui 1.92's pluggable font loader is reachable from C++ and not from
the Python binding, and implementing one would delete the synthetic-codepoint
machinery in `fontlib.py` entirely and open the seam where FreeType hinting
attaches. Nothing is decided and nothing is implemented.

## Open questions, not work items

- **The softness anomaly.** ImGui's own text measures solid 8.1% where our
  whole-pixel and advance rules both measure 18.4%, on the same face, atlas and
  frame — despite its pens being integers, which should make it exactly as sharp.
  Until this is explained, ImGui's rendering cannot serve as the sharpness
  reference. Candidates: a baked-size mismatch between `add_font_from_file_ttf`
  and `add_text`, or differing atlas UVs between the two paths.
- **Word-space spread under ragged right needs a geometric measurement.** The
  current figure is threshold-based and taken across an antialiasing change, so
  it cannot separate geometry from ink width. Measuring from the layout rather
  than from pixels would.
- **96 px/inch is an assumption.** The display has now been seen but not
  measured. `docs/imgui-risks.md` item 11.

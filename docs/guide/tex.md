# TeX, and which parts of it are here

`docs/tex-notes.md` is the transcription and the reference. This is the map: what
was taken, where it lives, and what the resulting control surface is.

**Two warnings before you implement from either file.** `docs/tex-notes.md` opens
with a CORRECTIONS section listing five transcriptions that are wrong — read it
first. And its *section numbers* were only spot-checked, so a load-bearing
citation must be verified against `tex.web` by content, not by number. That file
is `docs/tex.web`, gitignored because it is a 1 MB verbatim copy of someone
else's work under its own licence; fetch it from CTAN or any TeX Live source
tree.

## The model

Everything below stands on TeX's node list: **boxes, glue, penalties, kerns**.
`advtext/nodes.py` has them. A box has width, height and depth measured from a
baseline; glue has a natural size plus stretch and shrink at an *order*
(`normal`, `fil`, `fill`, `filll`), where a higher order absorbs everything below
it; a penalty is a numeric cost attached to a potential breakpoint.

That is the whole vocabulary. Justification, centring, ragged-right, vertical
rhythm, page breaking and math spacing are all expressed in it, which is why
taking the model rather than the features is what made the rest tractable.

## What is implemented, and where

| TeX | here | notes |
|---|---|---|
| `hpack` / `vpack` (§649, §668) | `advtext/pack.py` | sets glue, reports badness |
| badness (§108) | `advtext/badness.py` | the cube-root approximation, exactly |
| `line_break` / `try_break` (§813 on) | `advtext/linebreak.py` | total-fit, demerits §859 |
| `hlist_out` (§619-§625) | `advtext/shipout.py` | flattens to draw commands |
| `append_to_vlist` (§679) | `advtext/blocklayout.py` | interline glue — the vertical rhythm |
| `vert_break`, `prune_page_top`, `vsplit` | `advtext/columns.py` | cutting a vertical list |
| `mlist_to_hlist` (§726 on) | `advtext/math/mlist.py` | math list to horizontal list |
| `make_op`, `make_fraction`, `make_scripts` | `advtext/math/atoms.py` | §749-§751, §757-§758 |
| font metric parameters (§700 on) | `advtext/fontmetrics.py` | the math axis, x-height, quad |
| space factor (§1042, §1044) | `advtext/style.py` | inter-word glue scaling |

The one algorithm worth naming on its own is **total-fit line breaking**. A
greedy filler commits to line one before it has seen line four; TeX considers
every legal breaking of the paragraph and picks the set of breakpoints with the
fewest demerits overall, so an early line can be loosened by a hair to rescue a
later one. `demo/sample.md` is written to show the difference, and the test suite
pins it by enumerating every possible breaking of a short paragraph and checking
the chosen one scores lowest — a brute-force oracle, which is the only kind that
cannot agree with the implementation's own bug.

## The control surface

What you actually turn, and where:

- **The measure** — the line width. Everything in `linebreak` is relative to it.
- **`tolerance`** — how bad a line is allowed to be before the breaker refuses
  the breaking. Raising it buys fewer overfull lines and costs loose ones. It is
  currently doing the job hyphenation would do; see `docs/guide/future.md`.
- **The type scale** — `advtext/style.py` generates sizes from one body size and
  one ratio rather than listing them, so a heading cannot drift out of the scale.
- **Spacing** — French spacing (a single space after a sentence) versus extra
  space, via the space factor.
- **Alignment** — justify or ragged right, per block kind.
- **Interline glue** — from the leading ratio, per `append_to_vlist`.

## What is deliberately not TeX

From `docs/decisions.md`, each with a reason recorded there:

- **Hyphenation.** Roughly 1000 lines, with the worst interaction in TeX
  (ligature reconstruction, §915-916). The breaker runs its first and emergency
  passes and skips the hyphenation pass. This one now has a measured price.
- **Delta nodes in `try_break`.** A 1982 performance optimisation where the
  subtle bugs live. `active_width` is recomputed by re-walking instead; at
  paragraph sizes the difference is affordable.
- **`ext_tag` extensible assembly.** The variant chain gives a real display
  glyph, and TeX's own sanctioned fallback is the largest available variant.
- **The page builder proper** — `\output`, insertions, marks, a page cost
  function (§1005-§1010). Note that `\vsplit` and `vert_break` *are* in;
  "page breaking is out" is narrower than it sounds.
- **`\mathchoice`, `\halign`, full ligature reconstruction.**
- **Bidi, complex shaping, CJK line breaking.** Left-to-right only.

## The part of TeX this project does not have, and should be honest about

TeX's answer to low-resolution output was not in `tex.web` at all — it was
**Metafont**, which generated hinted bitmap fonts per size and per device, with
pen strokes explicitly fitted to the pixel grid.

This project has TeX's layout half and none of its rasterisation half. It uses
stb_truetype through ImGui, which does no hinting whatsoever. So the question
"are we being too faithful to TeX?" has an answer, and it is the opposite of what
it sounds like: we took the device-independent half and substituted a draw-time
rounding rule for the device-dependent half that Knuth actually wrote.
`docs/guide/rendering.md` is that rounding rule, and
`docs/guide/future.md` is what closing the gap would take.

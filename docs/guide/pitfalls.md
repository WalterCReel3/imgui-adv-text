# Pitfalls

Most of these are here because somebody walked into them. Several are here
because a confident claim did not survive a measurement, and one of those claims
was repeated twice before anybody checked.

## Tests that cannot fail

`docs/status.md` section 5 catalogues **five families** of vacuous test found in
this tree. The shapes recur, so they are worth recognising:

- **An assertion satisfied by the thing it replaced.** "A multiple of 0.5" is
  satisfied by every integer, so a half-pixel assertion passed unchanged against
  the whole-pixel implementation it was written to replace.
- **A measurement that folds the defect away.** A departure test took the nearest
  of many candidate pens and then subtracted `round(quad − pen)`, so a true
  departure of 0.9 px was reported as 0.1. It was measuring "is this quad an
  integer distance from *some* pen", which every integral position satisfies.
- **A hand-written list feeding `parametrize`.** Delete an entry and the suite
  reports one fewer passing test and no failure. `tests/test_docs.py` now checks
  its own list against the filesystem in both directions.
- **A screenshot target that skips a tab and exits 0.**
- **A control assertion that cannot fail by construction** — `assert "PHONY" not
  in targets` against a pattern anchored at `^[a-z]`.

**The defence is ablation.** Break the implementation on purpose and check the
test goes red. Both tests pinning the placement rule were checked that way, and
the numbers they produced under ablation matched the model's predictions to four
decimals. A test nobody has seen fail is a hypothesis.

## Measurement traps

- **Ink-threshold gap measurements are not comparable across renders with
  different antialiasing.** A softer render reads as wider letters and narrower
  gaps with nothing having moved. `scripts/visual_diff.py` *refuses* a gap table
  when the solid or midtone share has moved, and the refusal is correct — work
  around it and you are measuring antialiasing. Gaps within one render are fair.
- **A metric establishes change, never quality.** `docs/visual-review.md` records
  four appearance calls that were wrong, including reading the destruction of
  antialiasing as an improvement. Report which glyphs differ, by how much, in
  which direction; the judgement is the user's.
- **Crops land in the wrong place silently.** Locate a region by its *content* and
  fail loudly when it is not found. `visual_diff.py` has no way to name a raw
  pixel rectangle, on purpose.
- **Two screenshots from different builds look comparable and are not.**
  `visual_diff.py` stamps each PNG with a digest of the working tree and refuses
  a cross-build comparison unless you say you meant it.
- **Magnification clarifies; it does not exaggerate.** At 1:1 you perceive *that*
  something is wrong, at 6-14× you identify *what*. Use both, and do not
  "correct" for the magnification.

## Harness traps specific to glyph placement

- **Snap the anchor before applying any placement rule.** `_RigidSpan` snaps the
  span anchor with `snap_px` first, and a test harness that passes a fractional
  origin straight into a rule is feeding it the one input the design exists to
  prevent. Every rule then appears to phase across sub-pixel origins, and the
  defect reads as a property of the rule. This happened.
- **A quad's left edge is not the pen.** It is the pen plus that glyph's own ink
  offset `x0`. Differencing quad edges measures the ink between two glyphs, not
  the gap the rule produced. Subtract `x0` first.
- **Sweeping sub-pixel origins proves less than it looks.** Eight origins that
  truncate to the same integer produce identical output whether the inner glyph
  positions are integers or not. That test can show an origin is snapped; it
  cannot show what happens inside the string.

## Environment

- **Use `.venv/bin/python`.** The system interpreter has no numpy and test
  collection fails on `tests/test_visual_diff.py`.
- **Screenshots need a display and one app lifetime each.**
  `final_app_window_screenshot` returns the last frame of an app that has
  *exited*, so two shots cannot share a process. `make shot` is one process per
  photograph for that reason, and a loop inside the script would be wrong.
- **`artifacts/` and `.concerns/` are gitignored.** A document citing a script in
  `artifacts/` cites nothing; commit the instrument. Conclusions belong in
  `docs/`.
- **`visual_diff.build_id` hashes `advtext/`, `scripts/` and `demo/` — not
  `docs/`.** Editing documentation does not invalidate a screenshot comparison,
  which is usually what you want and is occasionally surprising.

## Code traps

- **A frame is not a window.** `draw` runs inside a real
  `new_frame()`/`render()` pair with no display at all, which is why the tests
  can assert on real vertex buffers. But `io.backend_flags` must carry
  `renderer_has_textures` or the first `add_text` aborts, and constructing a bare
  `ImDrawList` outside a live frame **dumps core** rather than raising.
- **`draw` must be given the same metrics the packing used.** Nothing enforces
  it, and a mismatch draws every glyph at the wrong size. `docs/imgui-risks.md`
  item 7.
- **`_FACES` is a module global and `run` can be called twice.**
- **Draw list flags are borrowed.** ImGui reuses one draw list for a whole
  window, so a flag left set leaks into every widget drawn afterwards — a defect
  that surfaces somewhere else entirely.
- **A missing glyph is only counted when a face was bound**, so a zero in
  `DrawStats.missing` is not by itself proof that nothing was dropped.
- **Snapping both edges of a thin rule independently can round them onto each
  other and erase it.** An area of zero extent appends no vertices at all, so
  this deletes the rule silently. `_snap_span` exists for that.
- **`tex-notes.md` section numbers were only spot-checked.** Verify a
  load-bearing citation against `docs/tex.web` by content.

## Provenance

Numbers decay. During one review, four figures in circulation could not be
reproduced against the tree: two sets of pen statistics, a kern-pair count that
re-ran deterministically as a different number, and a ladder of ink shares whose
absolutes did not reproduce although its direction did. In that last case the
likely cause was that the original harness patched `snap_px` globally, so its
finer rows also quantised the anchor — a variant later rejected.

The rule that follows: **quote the command, not the number you remember.** Where
a figure cannot be reproduced, say so and give the method for its replacement
rather than quietly restating it.

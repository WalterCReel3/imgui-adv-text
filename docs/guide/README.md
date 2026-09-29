# The guide

Five documents for somebody arriving at this repository. They are orientation,
not reference: each one explains a shape and then points at the document that
carries the measurements.

1. **[The idea](idea.md)** — what this is, the one invariant everything rests
   on, and the map of the code.
2. **[TeX, and which parts of it are here](tex.md)** — the algorithms taken from
   `tex.web`, where each one lives, and what the control surface actually is.
3. **[Rendering, and where it departs from both parents](rendering.md)** — the
   device-space decisions, why each was taken, and the two places this project
   deliberately disagrees with TeX and with ImGui.
4. **[Pitfalls](pitfalls.md)** — the traps. Most of these are written down
   because somebody walked into them, and several because a confident claim did
   not survive a measurement.
5. **[Future work](future.md)** — what is worth doing next, with the cost of
   each where it has been measured.

## The rule that governs all of them

Every number in this project must be re-derivable by running something. The most
common defect its history records is a confident figure nobody could reproduce,
so where these documents quote a measurement they name the command. Re-run it
rather than trusting the file. `docs/status.md`'s Provenance section is the
standard.

The second rule, from `docs/visual-review.md`: **a metric establishes change, it
never establishes quality.** Nothing in here says a rendering looks good.
Appearance judgements belong to the user and are quoted as theirs where they
appear.

## The deep documents these route to

| document | what it holds |
|---|---|
| `docs/status.md` | what is true today, and the provenance standard |
| `docs/decisions.md` | the interpreter, fonts, two-backend split, scope boundaries |
| `docs/tex-notes.md` | transcription of the relevant parts of `tex.web` |
| `docs/subpixel.md` | the sub-pixel investigation, including superseded rules |
| `docs/advance-rule.md` | the placement rule that ships, and its costs |
| `docs/imgui-risks.md` | open risks in the ImGui backend, in working order |
| `docs/litmus.md` | the two litmus tests and what their artifacts show |
| `docs/visual-review.md` | how to make a visual claim without being wrong |

Two of those carry a **CORRECTIONS** section that is newer than the body:
`docs/decisions.md` withdraws a premise several tasks were built on, and
`docs/tex-notes.md` lists five transcriptions that are wrong. Read both before
implementing from either.

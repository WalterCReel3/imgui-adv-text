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
| `docs/adoption-plan.md` | the plan for adopting advtext in `../pptmstr`, and what was built against it |
| `docs/postmortem-2026-10-adoption-and-demo.md` | how the two builds of 2026-10 went: what the plan got wrong, what went wrong, what is unknown |

Two of those carry a **CORRECTIONS** section that is newer than the body:
`docs/decisions.md` withdraws a premise several tasks were built on, and
`docs/tex-notes.md` lists five transcriptions that are wrong. Read both before
implementing from either.

**`docs/adoption-plan.md` is newer than every document in this guide, and where
they disagree it is the current one.** The plan was implemented on 2026-10-06
and 07 by an unattended team of agents: an import surface on `advtext` itself,
an embeddable view, per-role and per-run colour, live links, wrapping tables,
structured copy, and a streaming document and view. Its first section, "Read
this first", says what changed in behaviour that had already shipped, what was
run in a window and what nobody has looked at, and what is open. These five
guide documents were written before that and describe the layout engine and the
demo; they were not rewritten. Three things in them are now incomplete rather
than wrong: text that is not justified is no longer broken by the total-fit
breaker (`advtext.linebreak`, `LineBreakParams.first_fit`); the demo's
`DocumentView` is one of three views, the others being
`advtext.ui.bare_view.BareView` and `advtext.ui.stream_view.StreamView`; and
`future.md` item 2 is built.

**And a second build followed that one, the same day.** Its account is the
section of `docs/adoption-plan.md` headed "Second build", which comes before
"Read this first" and is the place to start. For a reader of this guide, four
things in it are new ground rather than corrections:

- **The demo is a sidebar of fourteen pages**, each a module under
  `advtext/ui/pages/` found by scanning the package. `idea.md`'s map of the
  code and every "tab" in these documents predate that; the five original
  tabs are the first five pages, unchanged in what they draw.
  `make run ARGS="--tab diff"` opens on a page.
- **A diff is not a document.** `advtext/diff.py` is a pure model (files,
  hunks, rows, intra-line spans, side-by-side pairing) built from before and
  after text or parsed from unified text, and `advtext/ui/diff_view.py` draws
  it on its own pixel grid, monospace and never justified, because laying a
  5,000-line diff out as paragraphs cost over a second before anything was
  drawn. None of TeX's machinery is in that path.
- **Mathematics in running text.** The engine `tex.md` describes grew
  radicals, sized delimiters, explicit spaces and words in a formula. It still
  has no parser: `advtext/mathtext.py` is an extension above it that reads a
  `$...$` subset into the engine's atoms and refuses the rest. A formula in a
  paragraph is one box on the baseline, broken only as a unit, selected as one
  item and copied as its source. Matrices are left out for now.
- **A block a host draws.** A view can reserve a rectangle for a block and
  hand it to a widget; a fenced `diff` becomes a `DiffView` that way, in a
  finished document or a streaming one.

`pitfalls.md` has no entry for this build yet, and the one it would open with
is in the plan: a host that holds the before and after text must build its
diff from them and never from its own unified string.

To see the library used rather than described, `examples/minimal.py` is 18
imports from `advtext` and nothing else; `examples/theme_gallery.py`,
`examples/stream_replay.py` and `examples/chat_transcript.py` are the embed
surface, colour, links and streaming, and `examples/diff_minimal.py` is a diff
from two texts in either layout.

# Postmortem: the adoption build and the demo build, 2026-10-06 to 2026-10-07

**Written by the session's lead agent, immediately after the merge (`32e3953`).**
It is an account of how the work went, not a description of the code; for the
code read `docs/adoption-plan.md` (its first two sections) and
`docs/decisions.md`.

**Provenance.** Figures quoted here were measured during the session, by a
builder or by the lead, and each says which. Nothing here was re-measured for
this document. Nothing in it is a claim about how anything looks: no agent
judged a rendered frame at any point in either build, and that is the largest
single caveat on everything below.

The working record — every task result, the ten review reports, the snippets
the lead ran, and the lead's decision files — is in `.concerns/`. That directory
is gitignored, so it exists only on the machine the session ran on. This
document is the part of it that is committed.

## What was asked

1. **"Read the implementation plan in `docs/adoption-plan.md` and implement
   the plan."** Seven phases to make advtext adoptable by `../pptmstr`: an
   embed surface, per-block layout, colour and links, draw cost, tables, copy,
   and streaming. The session ran unattended.
2. After that finished, in conversation: **a comprehensive demo** (a sidebar of
   pages), **a feature-rich diff display** in unified and side-by-side layouts
   because pptmstr would use it, **inline formulas from a `$...$` subset** as
   an extension over the engine, and **a canned chat page**. The user's words
   are quoted in `docs/decisions.md`.
3. Commit and merge locally.

## What was delivered

One commit (`fa7681d`), merged to `main`: 141 files, +77,589 / −1,827 lines, of
which `advtext/` is +30,390 and `tests/` is +38,749. The gate at the merge:
`make check` — 4,893 passed, 7 skipped, 4 xfailed in about 300 s, ruff, black
and mypy clean. It was 909 passed (4 red) in 40 s when the session began.

- **First build:** a lazy facade on `advtext`; host font setup; themes that
  take faces, size and alignment; `BareView`; per-block layout units; ink per
  role and a dark palette; colour spans and links; first-fit breaking for
  non-justified text; wrapping tables; structure-aware copy; `StreamDocument`
  and `StreamView`.
- **Second build:** `advtext/diff.py` and `DiffView`; `advtext/mathtext.py`
  and inline/display math in documents and streams; a math engine with
  radicals, sized delimiters, spaces and text; hosted blocks; a view API; a
  demo of 14 discovered pages.

## How the work was organised

A lead that planned and integrated but did not implement; builders that
claimed tasks from a shared board, one task at a time; reviewers that could
read but not run or write. About 60 board tasks, 58 builder result files, and
ten review rounds: a plan review and five code reviews in the first build, a
plan review and three code reviews in the second.

Three mechanisms carried most of the weight:

- **`touches` on every task.** The board serialised any two tasks that named
  the same file. No two agents wrote the same file at once in either build.
- **`.concerns/` as the record.** Board notes were truncated at a few hundred
  characters, so every task wrote a result file, and every decision the lead
  took went into a dated file with its reason. Later tasks read files instead
  of asking.
- **Reviewer writes a snippet, lead runs it, then it becomes a task.**
  Reviewers could not execute anything. Each finding came with a
  self-contained script and a stated criterion; the lead ran every one and
  recorded the output next to the finding before any builder acted on it.

## What the plan got wrong

The plan described itself as read-derived, and it was. The claims that did not
survive:

| Plan said | What was measured |
|---|---|
| The existing breaker is first-fit under a ragged right skip, so streaming needs no change to `linebreak.py` | Ragged total-fit cost 78–339× justified (2.5–9.3 s for the sample paragraph) and set one word per line ahead of an over-wide word. A first-fit mode was added: 5–9 ms |
| Commit every top-level block before the last | `para\n#` then `#tag` un-commits a paragraph. Commits are decided on complete lines only |
| Whole-document ship and index is the streaming cost to remove | That, and then four more: long lists and quotes (56.9 → 0.36 ms per piece), open code blocks (106.8 → 3.2 ms per line at 600 lines), live tables (10.0 → 0.8 ms per row at 30 rows) |
| No window can open in this environment | Half true. `DISPLAY=:1` was unreachable; an Xvfb in a user namespace over TCP worked, and from then on examples, pages and the mouse probe ran in a real window inside the suite |
| `fontTools` can load only when math is set | It is needed for every face; only the math-font patching could be made lazy |

The second build's plan, written by the lead after reading little of the code,
had the same disease and was caught the same way: the math engine had no
radical, no `\left…\right`, no explicit spaces and no text, so the requested
subset was not buildable on it as planned; and laying a 5,000-line diff out
through the code-block path took 1,159 ms before drawing anything.

## What went well

- **Reviewing the plan before building on it.** In both builds the first agent
  started was a reviewer checking the plan's claims against the tree. Both
  times it redirected tasks that were already in flight, cheaply.
- **Reviews found real defects, repeatedly, in code whose tests were green.**
  A sample: a NUL byte hid an entire diff from the reader; pptmstr's joined
  multi-edit text filed one edit under another; `{x^2}^3` set as x²³;
  select-all on a reply ending in a diff copied none of the diff; a table that
  committed in the burst that finished it froze at 25 px columns; copying a
  table produced tripled spaces; a list's marker leaked onto the next
  paragraph. Every one came with a script and was reproduced before a fix was
  specified.
- **Property and battery tests were worth more than case tests.** Streamed
  parse equals whole parse after every piece, over adversarial sources, held
  through four rewrites of the stream. In the last fix task, "no input line is
  ever dropped" found five shapes nobody had listed, and a fuzz of an
  incremental algorithm against its from-scratch version caught two defects
  its own author had introduced.
- **Builders measured their neighbours.** The Stream page's near-black text on
  a near-black background, the screenshot fixture deleting other runs' files,
  and a wrong rule the lead had relayed were all found by builders working on
  something else.
- **Byte-identity as the gate for refactors.** Justified breaking was checked
  identical to the committed breaker over 310 block/width settings; the demo's
  screenshots were byte-identical before and after the first build; the nine
  original formula plates stayed byte-identical through the engine work.

## What went wrong

### The lead's own errors

Each of these is recorded where it happened, and withdrawn there.

- **"No window can open."** Stated as measured after one failed attempt on one
  display. A builder disproved it within the hour.
- **"Refuted" a reviewer's cost claim with a broken fixture.** The lead's test
  list was one markdown-it splits into separate lists at item 10, so it never
  tested a long list. The reviewer was right: 2 → 43 ms per piece.
- **"Not reproduced" on a real defect**, twice: a hard-break alignment check
  that compared glyph x positions where right edges were the criterion, and a
  drag/relayout check whose fixture never moved the indices. Both defects were
  real.
- **Declined to schedule the live-table cost** on the 600-row figure alone. A
  builder then measured 10 ms per row at 30 rows.
- **Decision 7 (held table widths) was specified without being run** and
  overflowed the pane by more than 100 px.
- **A rule the lead wrote made a new defect.** "A `---`/`+++`/`@@` sequence
  always starts a file" fixed a mis-attribution and caused another, in honest
  `-U0` diffs. The final review caught it; the hunk's own counts now decide.
- **A check that could not tell.** The lead's snippet for "an unclosed `$$`
  shows closing dollars that have not arrived" counted refusal state, not
  displayed text. A later task checked the text; there was no defect.

The pattern: the lead's confident statements were wrong about as often as the
plan's, and they were wrong in the same way — a conclusion drawn from one run
whose fixture was not shown to test the thing. The process survived because
workers were told that only output tied to a script counted as measured, and
because refusing the lead was explicitly allowed.

### Fixes that broke things

Several fixes introduced something the next review found (nobody counted the
rate): the drag-anchor fix made drags started on blank space die at the next relayout
(198 of 500 press positions); the glyph-fallback fix made unrenderable
characters copy as the replacement mark; the contrast fix to the dark palette
moved add and remove inks closer together in greyscale (1.22 → 1.07). Review
after fix tasks was not optional, and the final fix task of each build still
went unreviewed.

### Process failures

- **Nothing was committed until the very end.** About 77,000 lines sat
  uncommitted across two days and some sixty agent tasks, with 38 untracked
  files at the end that had no revert path at all. Builders were forbidden git
  writes to protect each other's work; several ran `git add` anyway. No file
  was lost. That was luck plus the `touches` rule, not a safeguard.
- **A whole-suite run meant little while others were writing.** Builders saw
  1, 5, 35 and 55 unrelated failures in successive runs from half-saved
  files. One strict test (every page module must import) made everyone's
  suite hostage to any page being mid-write.
- **Shared test infrastructure collided.** The window fixture named its output
  directory by process id, which is the same in every sandbox, so concurrent
  runs deleted each other's screenshots. Its display port is still shared.
- **Dependencies could not be amended on a declared task.** Closing tasks
  became claimable before late fix tasks existed. The lead worked around it by
  claiming the closing task itself and holding it, which is a workaround, not
  a design.
- **Builders ran out of room mid-chain.** Three released or declined a task
  for capacity. That was the right call each time; the instruction to hand
  over a clean prefix was only written after the first one.
- **One builder delegated to sub-agents** and verified their work by
  re-running snippets rather than reading it. Later prompts forbade it.
- **A stray process.** A scratch script run from a shared temp directory
  imported another session's stale `bisect.py` and ran headless Firefox for
  about two minutes. Nothing in the repository was touched. Scratch scripts
  were moved to private directories and `python -P` afterwards.
- **Suite time went from 40 s to 300 s.** Most of the last doubling is page
  tests that open a real window.

### Scope that grew without the user

The user was not answering during either build. Decisions that changed shipped
behaviour, or that the user would plausibly have wanted a say in, were taken
by the lead and recorded as awaiting them: first-fit for ragged text;
highlights that stop at the text; growing the math engine; `$$` fence
semantics; inline-math guards that favour shell text over the `$n$th` idiom;
every diff-parsing rule; six palette values. `docs/adoption-plan.md` lists them
with measurements and how to undo each. They were reported as they happened,
but reporting is not consent.

## What is still unknown

- **Appearance, everywhere.** Pages, the diff view, formulas in text, both
  dark palettes, link underlines, the adjusted diff inks. Counts of glyphs
  drawn and none missing are not a judgement.
- **Code no reviewer read:** the final fix task of each build, the facade
  work, the view API, every demo page except Stress, and all the closing
  documentation.
- **Input beyond injected events.** Mouse and keyboard were driven at ImGui's
  IO layer under a software-rendered virtual display with no window manager.
- **Not exercised at all:** the wheel over a height-capped diff; scrollbar-drag
  jitter under scroll compensation; `scroll_to` in a real window; the
  direct-display branch of the window fixture.
- **pptmstr itself.** Nothing in it was changed, by the plan's own scope. The
  claim that advtext is adoptable is untested against the one consumer it was
  built for.

## Lessons, for whoever does this next

1. **Commit early, per task, on a branch.** One agent owning commits after each
   task completes would have cost little and removed the largest risk the
   session carried.
2. **Start with a reviewer on the plan.** It paid for itself twice.
3. **A finding is a script with a stated criterion, run by someone other than
   its author.** This held for reviewers. It should have been applied to the
   lead's own claims from the start; most of the lead's errors were snippets
   whose fixture was never shown to be valid.
4. **Prefer invariants to examples** when the code is a parser or an
   incremental algorithm: equals-the-whole, round-trips, never-drops-input,
   incremental-equals-from-scratch.
5. **Budget a review after every fix task, including the last.** Fixes are
   where regressions came from.
6. **Give shared test fixtures unique resources** before running agents in
   parallel, and do not make one module's half-written state fail everyone.
7. **Name the non-negotiable property of a feature in one sentence** and hand
   it to both builder and reviewer. For the diff view it was: never show less
   than the change, never attribute it to the wrong file, never copy text that
   exists on neither side without saying so. Most of the diff findings were
   violations of that sentence, and it made them easy to rank.
8. **Have a person look at the output before calling it done.** Everything
   above is evidence about structure, text and cost. None of it is evidence
   that the thing looks right, and typography was the point.

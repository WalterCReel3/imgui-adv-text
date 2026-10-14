# Plan: from 0.2.0b1 to 0.2.0

Written 2026-10-13 by the session's lead agent at the owner's request, as the
starting point for a new session. It says where things stand, what a proper
release needs, and in what order. For how the code is built read
`docs/status.md` (section 0i is the newest) and `docs/decisions.md`; for the
other two projects read `HANDOFF-imtypeset.md` and `HANDOFF-pptmstr.md`; for
what only the owner can do read `ASSIGNMENTS.md`.

## Where things stand

- **Released:** `imscribe 0.2.0b1` is on PyPI (tag `v0.2.0b1`, commit
  `b98de08`). It requires `imgui-bundle==1.92.900` and, on Linux x86-64 and
  macOS 14+ arm64 with CPython 3.11 to 3.14, `imtypeset==0.4.1.192900`.
  A beta: pip takes it only with `--pre` or the exact version.
- **Branch:** `experimental/imtypeset-adoption`, pushed. Not merged to
  `main`; the owner has said no merging while it is work in progress.
- **Evidence, and who has it:**
  - `release.yml` ran once and published (GitHub run 38497674627).
  - The lead installed `imscribe==0.2.0b1` from PyPI into a new virtualenv
    on Linux; `python -m imscribe.typesetter` exited 0 (ready).
  - Local gates on `b98de08`, quiet tree: `make check` 4301 passed;
    `IMSCRIBE_NO_TYPESET=1 make check` 3645 passed; sidecar
    `make check TYPESET=1` 4309 passed (pair built from imtypeset `cf7466e`,
    one commit short of `v0.4.1`).
  - CI on GitHub for `b98de08` is RED (run 38497533497): 1 failure of 3645
    without the library, 2 of 4301 with it. The log lines read show the
    mouse probe's own Xvfb failing ("Cannot establish any listening
    sockets"). Not investigated; the second failure in the with-library job
    was not identified.
- **Never run:** anything of imscribe on macOS (`macos.yml` starts by hand);
  a framebuffer scale other than 1; pptmstr against this release.
- **Nobody has judged a frame.** Agents measure positions and widths. The
  owner looked at the demo once, on 2026-10-11, before the monospace change.

## What 0.2.0 needs

### A. Work for this repository's session (builders)

In this order. A1 to A4 are independent except where files overlap.

1. **CI green on GitHub.** Find why the mouse probe's Xvfb cannot listen on
   the runner and name every failing test (`gh run view 38497533497
   --log-failed`). Related debt: two sessions' Xvfb servers share one port
   in `tests/conftest.py`. Done when a push shows both `ci.yml` jobs green.
2. **`README.md` level with the release.** It still says imscribe is not on
   PyPI, that `release.yml` has never run, and that no CI job has run.
3. **The diff view counts a borrowed letter as one column.** imtypeset 0.4
   sets a Greek or Cyrillic letter in the code face two cells wide;
   `TypesetDiffView` counts one, so `content_width`, the scroll range and
   the side-by-side panes are a cell short per letter (measured headless by
   ADOPT-API's builder, its result file section 6.1). Reproduce first.
4. **The missing-library sentence.** With no wheel, `typesetter.reason()` is
   "IMTYPESET_LIBRARY is not set", a developer variable, and it is the first
   thing a pip user on an unsupported platform sees. Proposed: "imtypeset is
   not installed (pip installs it where it has a wheel) and
   IMTYPESET_LIBRARY is not set". Asserted in about 33 test files; a
   mechanical change, verified by the no-library gate.
5. **Fractional framebuffer scale.** Measure the diff grid and a fenced
   block at 1.5; the view rounds to whole units, which are not whole
   framebuffer pixels there. A measurement first, a fix only if it shows
   pens off the grid.
6. **The user's real route in the suite.** With-library tests run with
   `IMTYPESET_LIBRARY` set and `IMSCRIBE_NO_TYPESET=1`, a state no user's
   process is in; the nothing-set route rests on two tests. Add a small set
   of windowed tests that run with nothing set.
7. **A read-only review of the view code.** No reviewer has read
   `imscribe/ui/typeset_diff_view.py`, `typeset_hosts.py` or
   `typeset_view.py` since before the pixel cell, the rename and the 0.4.1
   adoption. The release-day review covered packaging only.
8. **`.gitignore` in the sdist.** hatchling force-includes it; its comments
   mention the agent sandbox and `.concerns/`. Clean the comments or keep it
   out of the export.
9. **Rebuild the sidecar from `v0.4.1`** (`make typeset-lib
   IMTYPESET_COMMIT=v0.4.1`, never run in that form) so the developer route
   is level with the wheel.

### B. The owner's

1. **Look at it in a window:** `make run`; the Diff page, a fenced code
   block, a long streamed reply on the Chat page.
2. **Start `macos.yml` by hand** on GitHub and pass back what it says.
3. **Which Macs.** The wheels are Apple Silicon, macOS 14 or later, only.
   If that is the target, say so and the README states it.
4. **The SVG litmus chain** (`make svg`): twenty-two modules of the old core
   stay in the package only for it. The lead recommends removing them before
   0.2.0. Keep, or let go?
5. **`cell=`:** removed at 0.2.0, or one version later?
6. Older open items in `ASSIGNMENTS.md` section 7 (the upstream Dear ImGui
   report; the smaller reversible defaults).

7. **P46: an install where imtypeset has no wheel.** pptmstr measured with
   pip's resolver: the marker is true on macOS 13 arm64 and on Linux with
   glibc before 2.28, imtypeset has no wheel or sdist there, so
   `pip install imscribe` fails with "no matching distribution". Two shapes:
   make imtypeset an extra (`imscribe[typeset]`; plain `imscribe` installs
   everywhere and draws nothing without it, pptmstr asks for the extra), or
   ask imtypeset for an sdist that fails with a sentence. The lead leans to
   the extra: imscribe already degrades with a sentence when the library is
   absent, and an install that succeeds is easier to explain than one that
   fails well. It reverses decision 1 of release day (hard dependency).

### C. The other two sessions'

- **pptmstr:** move its pins to `imscribe==0.2.0b1`, drop `cell="pixel"` at
  `diffs.diff()` and `gate._measured_columns` (A6 in `HANDOFF-pptmstr.md`),
  rerun its own column gate against the new default, and say whether
  Cyrillic in a diff matters to it (A7). Its real use is the best test this
  package has had.
- **imtypeset:** H49 to H51 in `HANDOFF-imtypeset.md` (the device advance is
  within 1e-5 of a whole pixel and not on it; a borrowed letter takes two
  cells; `caret_rect` at a code line's end).

### D. pptmstr's open requests (P37 to P47)

Read from pptmstr's `HANDOFF-advtext.md` at `72e6a60`; the first reading of
whose each is, and which hold 0.2.0, is the table at the end of
`HANDOFF-pptmstr.md` ("Received: P37 to P47"). Reproduce each before acting.
Those that hold 0.2.0: P38 and P41 (a lone surrogate raises out of `draw`;
a substituted U+FFFD is not said), P39 (with A3), P43 (= A4), P46 (= B7),
P47 (with A5: the size a theme expects under ImGui's display scale on
Windows and Linux; pptmstr works round it).

## Done when

`0.2.0` is tagged when A1 to A4 are done; A5 is measured; B1 and B2 have
happened and what they found is fixed; pptmstr runs on the beta and its gate
passes; B3 to B5 and B7 are answered; and the D items marked as holding 0.2.0 are done. A6 to A9 should be done and need not hold
the tag.

## How to run the next session

- Start from this file, then `docs/status.md` 0i and the two handoff files'
  newest dated sections.
- Rules that matter anywhere: each session writes only in its own
  repository; no attribution lines in commits; a finding from reading is
  reproduced before it is fixed; a number passed to another session has a
  run behind it or says it was read.
- What went wrong on release day, to avoid repeating: a builder sat idle for
  an hour with nobody noticing; a builder missed its lead's notes because
  the board cut them off; and three sets of documents repeated "no workflow
  has ever run" without anyone running `gh run list`. Check the cheap fact
  first, and keep the last task of a round to gates only.

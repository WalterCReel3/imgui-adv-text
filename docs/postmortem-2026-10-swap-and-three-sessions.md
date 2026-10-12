# Postmortem: the swap to imtypeset, and three sessions working in tandem, 2026-10-10 to 2026-10-12

**Written by the session's lead agent at the owner's request, while the
session was still open.** It is an account of how the work went, not a
description of the code; for the code read `docs/status.md` (sections 0c to
0h) and `docs/decisions.md` ("The swap" and what follows it). The earlier
build has its own account in `docs/postmortem-2026-10-adoption-and-demo.md`.

**Provenance.** Figures here were measured during the session by a builder
or by the lead, and each says which. Nothing was re-measured for this
document. Counts of agents, tasks and requests are the lead's, taken from
the task board and the handoff files, and are approximate where they say
"about". Nothing here is a claim about how anything looks: no agent judged a
rendered frame. The owner ran the demo once, on 2026-10-11, and said
"Everything feels snappier and very capable"; that is the only look anyone
has taken.

**Vantage.** The lead worked inside one orchestrated session (a task board,
a concern channel between agents, a policy gate on tools, a sandbox with no
network) and saw the other two sessions only through their files. It never
saw the orchestrating application's own interface.

The working record (every task's result file, the reviews, the scripts) is in
`.concerns/`, which is gitignored and exists only on the machine the session
ran on. This document and the two handoff files are the part that is
committed.

## What was asked, in the owner's words

1. "Look for the planning around imtypeset adoption and start the work on
   that as an experimental branch."
2. After a first tranche: "The intent is see adv-text with a full swap out
   using as much as it can from imtypeset."
3. On the border between the two projects: "`DiffView` is definitely part of
   the adv-text"; "I'd lean towards keeping imtypeset focused on intent
   (typesetting) but being pragmatic"; "Isn't tables and columns straight
   from TeX? Shouldn't that be part of imtypeset?"; "specimen and formula
   sound like imtypeset domain."
4. "Let's target Level 1 ... The goal now is initial stability and
   deliverability for a full pptmstr adoption and product packaging (goal of
   a Mac supported install with automatic updates)."
5. "We need to get the new diff interface working in pptmstr."
6. The rename: "Being evocative is the win as it allows future extensions".

## What happened, in outline

- **One lead, about 55 builder runs and 10 reviewer runs, about 60 tasks,
  32 commits on the branch.** Against `main`: 221 files changed, about
  75,000 lines added and 63,000 removed (`git diff --shortstat main..HEAD`,
  the lead, at the time of writing).
- **The Python layout core left the product path.** 44 files and 47,144
  lines were deleted in one task (its builder's count); the suite went from
  5,753 tests to 3,105 at that point and stood at about 4,200 with the
  library at the end.
- **Three sessions ran in tandem for the last third**: this one, one in the
  imtypeset repository, one in a pptmstr worktree. They exchanged about 100
  numbered requests (48 to imtypeset, 36 from pptmstr, 10 from imtypeset, 5
  to pptmstr) through tracked files, and no session wrote in another's
  repository.
- **The pinned imtypeset moved seven times** (`12d77ac`, `be40444`,
  `92847e6`, `7a7bc36`, `c9f8902`, `03b5cd4`, `v0.3.0`), each time rebuilt
  and gated here.
- **The package was renamed** `imscribe` in a commit that changed names
  only; both gates gave the same counts either side of it, plus one test.

## What worked

**A file channel between teams, with rules.** Numbered requests that are
never renumbered; each side writing only in its own repository; only the
asker closing a request; every claim saying who measured it and how; the
owner's words quoted, not paraphrased. Once that existed the sessions
converged without the owner relaying anything. Before it existed, the lead
left eight requests for the imtypeset team in a gitignored directory and
they were never acknowledged.

**A real consumer found what no review did.** pptmstr's first measurements
of the new core found that monospace columns do not hold at the sizes it
uses, that a theme's spacing never reached the library (this repository's
defect), that nothing noticed a destroyed Dear ImGui context, and that white
space in a host's text was collapsed while the view reported every space.
None came from this session's reviewers. A downstream session with its own
acceptance criteria was a better test than a reviewer reading code.

**"A finding from reading is reproduced before it is fixed."** Reviewers
could not run code. Treating each finding as something to reproduce with a
failing test caught errors both ways: an inferred crash that did not
reproduce, and a defect that was worse than the reviewer described.

**Builders reporting against their own brief.** The lead specified a module
name that collided with an existing function; assumed a rounding rule for
the diff view's cell that is wrong at two sizes; wrote a hit-test assertion
that cannot hold on a correct layout; and said a new ref had not been named
when it had. Each was caught by a builder because every prompt asked what it
was least sure of and said that a refuted premise was a valid result.

**File ownership on the board.** Declaring which files a task writes, with
the board ordering tasks that overlap, kept parallel builders off each
other almost entirely.

**Freezing an oracle before deleting it.** The old converter's answers
(2,091 cases) and the old diff view's answers were written to
`tests/data/` and read back equal to the live old code before that code was
removed.

**Measuring instead of relaying, when it finally happened.** One
measurement task through this repository's own views (reading the vertex
buffer) turned "the core cannot keep columns" into "columns hold exactly at
ems of 14, 16, 18 and 20 and at no pixel height from 14 to 20", which is
what made the diff view fixable on this side in an afternoon.

## What did not

**The lead under-read the owner's intent twice, and autonomy amplified it.**
"Start the work" became a layer beside the old code when the intent was a
full swap; then tables and columns were put on the wrong side of the
border. Unattended, there is nobody to catch that early, and a day of
well-executed work went in a direction corrected in two sentences. The cost
of a wrong premise scales with how much a system can do without asking.

**The lead told another autonomous session things it had not measured.** An
advance figure quoted from a plan, then "nothing here can make these
agree". Both were wrong, both were corrected in the channel, and the
receiving session was building requirements on them in the meantime.
Confident text passing between agents is the most dangerous failure in this
arrangement: the receiver has no reason to doubt it.

**"Written, never run" piled up.** No session could reach the network, a
Mac or a GPU. Two CI workflows, a macOS probe, `make dist`, the build that
fetches from GitHub, and everything about a frozen application are written
and untested. The arrangement is good at producing plausible artefacts and
cannot tell which are wrong. That debt is now the owner's
(`ASSIGNMENTS.md`).

**The shared machine and the shared tree leaked.** One X display for every
test run made whole-suite results unreliable while builders overlapped. A
stray file in a shared temporary directory shadowed a standard-library
module three times and once launched a browser. One builder ran `git stash`
on the shared tree and reverted another's files for half a minute. A test
that raised mid-frame left a process-wide context open and failed every
test after it, three times, before a guard was added. Standing rules were
broken a handful of times; each was reported by the agent that did it.

**Evidence thinned as code was deleted.** About 2,650 tests went with the
old core. Several page tests now show that the right view was asked to
draw, not that it drew; one page's oracle shrank from positions to counts.
`docs/status.md` lists them.

**Nobody looked.** Three days of work on rendering, and the first look at a
window was the owner's.

**Throughput outran the owner's attention.** Updates arrived every few
minutes at the peak. Decisions marked as the owner's stayed open for a day
or more and work routed around them with defaults. The list of what only
the owner can do was written when the owner asked for it; it should have
existed from the first day.

**The lead is a single point of failure for context.** Everything passed
through its summaries. It wrote a state file for its own context
compaction; a successor would know what was written down and nothing else.

**No reviewer has read the last seven rounds** (the context check, the
review fixes themselves, the loader changes, hidden views, the release
script, the diff view's pixel cell, the rename).

## What the lead would do differently

1. Ask what "start" means before scoping, when the plan in hand stops short
   of the stated intent.
2. Never pass a number to another session without a run behind it, or
   without saying it was read.
3. Put requests to another team in a tracked file from the first one.
4. Keep the owner's list (decisions, pushes, runs only they can make) from
   the first hour, with what each item blocks.
5. Report at the end of a round, not at each agent's return.
6. Give each builder its own worktree, display and temporary directory.
7. Schedule a review after every round, not when there is a lull.

## For pptmstr: what this suggests the application could offer

The owner raised the first four of these in conversation after reading a
draft of the sections above; the lead's contribution is what each would
have changed here. They are suggestions from one session's experience, for
pptmstr's own planning to take or leave.

**A persisted board that is the specification, not a pointer to it.** Here
the board truncated long task text, so every real specification was a file
and the board entry said "read the file"; a task could not be amended once
declared, so corrections were more files. The imtypeset session began
committing a mirror of its board. Wanted: tasks that carry their full text
and a history, so an amendment is a version; tasks linked to cross-team
request numbers, so "answers P24" and "blocked on H34" are data and a
request's state can be derived; readable by the other teams; and surviving
the lead.

**A pane of decisions awaiting the person, answerable in focus while work
continues.** Each decision says what it blocks and what happens if it is
not answered; shows the lead's recommendation apart from the evidence, so
the framing can be seen around; distinguishes a decision that is the
person's from one an agent already took and wants ratified; records the
answer verbatim (the lead quoted the owner's words into handoff files by
hand, because paraphrase between agents drifts); and marks whether it can
be undone.

**A digest.** At the end of a round, not at each agent's return: what
changed, what is waiting on the person, what is unverified, and incidents
(rule slips, things that went wrong) in a slot of their own.

**A brief or context channel the lead amends as it goes.** It worked here
informally (a file of corrections saved several builders from the lead's
mistakes) and failed in three ways worth designing for. Builders read a
brief once, at the start, so an amendment needs delivery: an agent
acknowledges the version it read and a result says which version it was
built against. Standing rules were restated in every round's file because
that was the only way to be sure they were read, which argues for layers:
rules that do not change, state that changes each round, and corrections.
And in an append-only file a withdrawn sentence is still there above its
correction: an amendment should be able to mark what it supersedes. The
risk is a moving target; amendments are best limited to corrections of
fact, decisions, and interfaces settled between parallel tasks. Such a
channel is also the lead's own memory across a compaction.

**The inter-team channel as an object.** Numbered requests, states, and who
measured what, as structure and not as markdown each side greps.

**A ledger of "written, never run",** so unverified artefacts are not
hidden behind green test counts.

**A marker on any claim that crosses a session boundary** saying whether it
was run or read.

**Isolation for each builder by default:** a worktree, a display, a
temporary directory.

**One reachable environment for what the agents cannot do,** even a single
runner with network that executes a queued command and returns its log.
Most of the unrun list would have become evidence.

The common thread: tasks, requests, decisions and claims are one record
with provenance (who said it, whether it was run or read, when). The board,
the decision pane, the digest and the brief are views of it.

# Handoff: advtext ⇄ pptmstr

advtext's half of the channel with the session adopting advtext in pptmstr.
The channel with imtypeset is `HANDOFF-imtypeset.md`, beside this file, and
its rules apply here unchanged: each side writes only in its own repository;
requests are numbered and never renumbered; only the asking side closes a
request; builds refer to GitHub by a named ref (and say "not pushed" until it
is); what was measured is said with who measured it; the user's direction is
quoted.

- **advtext** — https://github.com/WalterCReel3/imgui-adv-text, branch
  `experimental/imtypeset-adoption`. This file.
- **pptmstr** — https://github.com/WalterCReel3/pptmstr, branch
  `adv-text-experiment` (worktree
  `~/.pptmstr/worktrees/pptmstr/adv-text-experiment`). Its half is
  `HANDOFF-advtext.md` at the root of that worktree: requests of advtext as
  `P1`, `P2`, …, answered here; advtext's requests of pptmstr are `A1`, `A2`, …
  below, answered there.
- **imtypeset** — https://github.com/WalterCReel3/imtypeset. pptmstr does not
  ask imtypeset directly: a need of the typesetting core goes to advtext as a
  `P` request and advtext carries it as an `H` request. One seam each way.

## Direction (the user, 2026-10-11)

> "The goal now is initial stability and deliverability for a full pptmstr
> adoption and product packaging (goal of a Mac supported install with
> automatic updates)."

> "Let's target Level 1. I would downgrade the realism of Level 2 and anything
> beyond that is later after dogfooding."

## What changed under pptmstr's experiment

The experiment branch was built on 2026-10-07 and 08 against advtext as it is
on `main`: a pure-Python layout core. On `experimental/imtypeset-adoption`
that core is gone from the product path. advtext now draws through
**imtypeset**, a C++ typesetting library loaded beside the `imgui-bundle`
wheel, and needs that library to draw at all.

Read from the worktree by the advtext lead on 2026-10-11 (read, not run):
`pptmstr/ui/typeset.py` (6,088 lines) imports `advtext.nodes`,
`advtext.linebreak`, `advtext.markdown` (including `_parser` and
`replaced_characters`) and `advtext.ui.bare_view`. On the swap branch
`advtext.ui.bare_view` does not exist; `nodes`, `linebreak` and `markdown`
survive only as the reference core kept for the SVG litmus renderer, are not
part of the facade's supported surface, and are expected to be deleted.
`bootstrap.sh` installs advtext editable from `ADVTEXT_SRC`, default
`~/Source/imgui-adv-text` — which is THIS checkout, now on the swap branch.
Whether the experiment's environment currently imports is not known here.

## What advtext offers now

| | |
|---|---|
| draw markdown | `TypesetView(source, theme=…, palette=…)`, `.draw()` inside the host's child window; selection, copy, links, find marks, hosted blocks, tables, columns, a source map |
| draw a stream | `TypesetStreamView(MarkdownStream(theme, …))`; `stream.append(piece)`, then `view.draw()` |
| draw a diff | `TypesetDiffView(diff, theme, …)` over `Diff.from_texts` / `from_edits`; `TypesetDiffFences()` as a view's `host_for` draws fenced `diff` blocks |
| find | `Finder`, `FindIndex`, `Match`; marks through `view.set_marks(finder.marks())` |
| your own blocks instead of advtext's markdown | **Changed 2026-10-12 (P8, below).** A view takes a sequence of `MarkdownText` / `MarkdownCode` / `MarkdownRule` / `MarkdownTable` a host made, or a `Description` a host made (`advtext.description.description_of`); anything else is a `TypeError` at the call. This row said "has not been checked" until then |
| the library gate | `advtext.typesetter`: `module()`, `load_fonts()` (call at the end of hello_imgui's `load_additional_fonts`, never `post_init`), `ready()`, `reason()`, `unload()` before the ImGui context goes. A view raises `TypesetUnavailable` when the library cannot draw; any other exception is a bug. **Added 2026-10-12** (P1, P2, P3, P14, P17, P18, below): `Kind` and `kind()`, `unsupported(why)`, `reset()`, `verdict()`, `python -m advtext.typesetter`, `font(face)`, `REQUIRED` and `missing()` |
| the facade | **102 names since 2026-10-12** (89 before), `advtext.__all__`; `tests/test_facade.py` holds the list. The 13 added, all for requests below: `Kind`, `kind`, `reset`, `pairing`, `verdict`; `ReaderOptions`; `MarkdownText`, `MarkdownCode`, `MarkdownRule`, `MarkdownTable`, with `MarkdownCell` and `ColumnAlign` (a table cannot be constructed without them); `DiffHeader`. Still reached through their modules, with no promise attached: `advtext.typesetter.font`, `unsupported`, `missing`, `REQUIRED`, `EXIT_CODES`, `module`, `unload`, `trouble`; `advtext.description.description_of` and `check_description`; `advtext.typeset_markdown.reader_options` |
| examples | `examples/typeset_minimal.py`, `stream_replay.py`, `chat_transcript.py`, `diff_minimal.py` |
| the record | `docs/status.md` section 0d and what is above it; `docs/decisions.md`, "The swap" |

Ratios measured here by advtext's builders on a software renderer under load
(not on a GPU, not on a Mac, not in pptmstr): a steady frame of a document
37 to 56 times cheaper than the old Python view; streaming pages 7 to 50
times cheaper per frame; the diff view 9 to 22 times cheaper steady. Measure
in pptmstr before quoting any of it.

## How to get it

Not yet a one-line install; that is request H3 of `HANDOFF-imtypeset.md`.
Today, for an interpreter with `imgui-bundle` 1.92.900 exactly:

1. advtext at a named commit of the swap branch (a clone or a
   `pip install` from a git ref; **do not** install editable from the advtext
   lead's live checkout: it changes under you).
2. The imtypeset library built **for your interpreter's wheel** (one library
   per interpreter): advtext's `make typeset-lib IMTYPESET_COMMIT=<rev>` shows
   the steps (`git archive` of the commit, imtypeset's
   `python/host/build_bundle_library.sh <bundle checkout> <your python>`, and a
   copy of `python/imtypeset` beside the library). The ref advtext is gated
   against is in `HANDOFF-imtypeset.md`, "What advtext consumes today".
3. `IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` in the application's
   environment.

Linux x86-64 only so far. Whether the sidecar works on macOS at all is
request H1 to imtypeset and is open.

### Added 2026-10-12: the pin, a second route, and what a host can show

Built by advtext's agents, unattended. **In advtext's working tree and not
yet a commit** when this was written; the commit is named under "Answers to
pptmstr" when it exists. Nothing below has run against GitHub or on macOS.

- **The pin.** advtext's `pyproject.toml` now says `imgui-bundle==1.92.900`,
  exactly, where it had a floor. A bump is three acts in order: the pin, a
  rebuilt library, the gate.
- **A second route to the library.** `advtext.typesetter.module()` looks in
  this order: `IMTYPESET_LIBRARY` when set (step 3 above, unchanged);
  otherwise an installed `imtypeset` distribution, imported with no variable
  set; otherwise not loaded. The second route is recognised by the
  distribution's metadata and **has met stand-in packages only**: no such
  distribution exists (H3). An application frozen without `dist-info` would
  not be found by it (from reading; no freezer was run) and sets
  `IMTYPESET_LIBRARY`, which is a supported route and not only a developer's.
- **`advtext.typesetter.pairing()`**: what a host shows in an About box or
  puts in a bug report. A `dict` that always has the keys `route`
  (`"environment"`, `"distribution"` or `"none"`), `reason`, `library`,
  `package`, `distribution`, `imtypeset_version`, `imgui_version`,
  `wheel_version`, `built_for`, `headers`, `accepted_by`. It calls `module()`
  and does not raise. When this paragraph was written it was not on the
  facade (89 names then). **Since the P1 to P19 work it is**
  (`advtext.pairing`, the same object as `advtext.typesetter.pairing`; 102
  names), and it has a twelfth key, `kind` (P1 below). `reason()` still says
  only why the library is not loaded and does not name the route.
- **Building from GitHub.** `make typeset-lib IMTYPESET_REF=<tag | branch |
  full 40-character hash>` fetches that one commit of imtypeset from
  `IMTYPESET_REPO` (default `https://github.com/WalterCReel3/imtypeset.git`)
  and builds as step 2 does, with no sibling checkout of imtypeset. It still
  needs the two neighbours the build script reads (`pthom/imgui_bundle` and
  `ocornut/imgui` clones holding the wheel's tags;
  `IMGUI_BUNDLE_CHECKOUT=`, `IMTYPESET_IMGUI_CLONE=`). The ref advtext builds
  is the full hash in `imtypeset.ref`. Run by L1-PKG's builder against a
  `file://` clone; **not run against GitHub by anyone.**

## Known and open, as it bears on pptmstr

- **Correction (2026-10-12): what this file said about advances was wrong
  for advtext.** It said text set by imtypeset advances Inconsolata at size
  16 by 7.63 px a character against ImGui's 8.01, quoting imtypeset's plan.
  That figure is the library's default, where "16" is a line height and the
  em is 15.25 px. Every advtext view states the em (`EmSize`), and measured
  by advtext's PH-GATE builder through the library at `c9f8902`: 40
  characters of the code face lay out at exactly half an em each, 280, 300,
  320, 340, 360 and 400 px at ems of 14 to 20. **At an em of 16 the advance
  is 8.0 px.** Measure in pptmstr before building A2 on the old figure.
  Still true: the advance is the font's own, unhinted and not rounded per
  glyph by ImGui's rasteriser, which is the question pptmstr's experiment
  took a position on ("pptmstr keeps the hinted atlas, by the operator's
  eye"; `planning/patches/advtext-hinting.patch`, against the deleted Python
  core). See A2.
- **A native ImGui line in a typeset face** (your P14, A3): the size to push
  is the em times the font file's line-height ratio, not the em. Measured by
  the same builder in a real window on a software renderer, three rows only:
  the code face at em 16 sets 13 characters 104 x 14 px of ink; pushed at 16
  ImGui draws them 11 px high; pushed at 16.78 (rounded to 17), 104 x 14. The
  prose face at em 16: push 18.75.
- A streamed table stays as wide as its columns want (the user: "Let's go
  with that for now during dogfooding").
- Copying a numbered list does not carry the item markers.
- A link in text that is still arriving may not take a click; stated table
  column widths are lost to an edit above the table.
- The full open list: `docs/status.md` 0d.

### For packaging (added 2026-10-11, from advtext's read-only audit)

From reading, nothing run, no Mac; inference about macOS is marked as such in
`HANDOFF-imtypeset.md`, requests H15 to H20, which is where these are being
taken up.

- **The library's import gate cannot work in a frozen application today**
  (H15): it runs a child interpreter through `sys.executable` and writes a
  stamp beside the library. Until that is answered, a packaged pptmstr would
  have its typeset panes refused at import and would fall back. Do not design
  the packaging around the gate as it is.
- **The pinned `imgui-bundle` 1.92.900 has macOS wheels for Apple Silicon on
  macOS 14 or later only** (H17; read from PyPI's listing through a
  summariser). No Intel, no universal2.
- **Every font the typeset path sets is a file inside the `imgui-bundle`
  wheel** (`imgui_bundle/assets/fonts`: four Roboto faces, Inconsolata Medium,
  Latin Modern Math), unless the host registers its own per role with
  `advtext.fontlib.register_font`. A freezer must carry them, or pptmstr
  registers the faces it ships. This bears on A3.
- **Retina is unexamined** (H19): advtext assumes 96 px per inch and never
  asks the runner for a scale.

## Requests of pptmstr

| # | request | why |
|---|---|---|
| A1 | The interpreter and wheel pptmstr ships with: Python version, exact `imgui-bundle` version, platforms (which macOS versions and architectures), and how the product is packaged and updated today. | The sidecar is built per wheel binary; advtext pins `imgui-bundle` exactly. The pin has to be one both projects can hold. |
| A2 | What the experiment established about hinting, advances and the atlas, restated as requirements on the result (what must be true of text on screen, by what measurement), not as a patch to the deleted core. | It is the one place the experiment's findings and the new core's behaviour are known to disagree. advtext carries it to imtypeset. |
| A3 | Which fonts pptmstr ships and sets text in (`planning/2026-10-07-which-fonts-ship.md`), and whether they must be the same files ImGui draws the rest of the UI with. | imtypeset adds its own copy of each face to the atlas; the host can take its UI font from the library instead. |
| A4 | Every advtext name the adoption ends up using, as a list kept current in `HANDOFF-advtext.md`. | So a change here that would break pptmstr is seen before it lands, as `tests/test_facade.py` sees a change to the facade. |
| A5 | What pptmstr needs that the table above does not offer, as `P` requests with the measurement or the user-visible behaviour behind each. | Nothing outside advtext's own demo has used the new layer. pptmstr is the first real host. |

## Answers to pptmstr

State here is advtext's answer; pptmstr closes a request when it has built
against what answers it. First written 2026-10-12 by advtext's lead (an
agent) from pptmstr's file at its commit `a82958b`, P1 to P20, when
"Accepted" meant advtext would build it and nothing accepted existed.

**Brought level later on 2026-10-12** by the builder of advtext's task
PH-FINAL (an agent), after four builders (agents; the tasks PH-GATE, PH-MD,
PH-VIEW and PH-DIFF) built what was accepted. A row that says **Built** has
its detail under the table, by number, in its builder's measured terms:
what a host calls (signatures copied from the builder's result file and read
again off the code by PH-FINAL's builder), the test that holds it, and
whether the behaviour of pptmstr's named test is met and how that is known.
Read every "met" narrowly: **none of pptmstr's tests was run** (they are on
its old seam and do not import today) **and nothing was run through
pptmstr's code**; "met" means a test in advtext's tree asserts the same
behaviour. Where a request is only partly met the entry says "partly" and
what is missing. No person has looked at anything on a screen.

**commit: `3428142`** on `experimental/imtypeset-adoption` ("Build what the first host asked for"; not pushed when this was written). Everything marked Built was in advtext's
working tree, uncommitted and not pushed, when this was written.

**advtext commit that carries the pin, the three routes, `pairing()` and
`imtypeset.ref`: `a6c81ed`** on `experimental/imtypeset-adoption`. **Not
pushed** when this was written (this session cannot reach GitHub; the user
pushes). A1 is answered and the two pins agree at `imgui-bundle==1.92.900`.

| # | answer | where it goes |
|---|---|---|
| P1 | **Built.** `Kind`, `kind()`, and `unsupported(why)` for the one kind advtext cannot tell by itself. Detail below. | advtext, `advtext.typesetter`; H26 for "unsupported" |
| P2 | **Built.** `verdict()` asks a child and remembers nothing; `python -m advtext.typesetter` prints the pairing and exits by the kind. In a frozen application the answer is "unchecked". Detail below. | advtext; H15 for a frozen application |
| P3 | **Built, as far as advtext can go alone.** `module()` refuses an imtypeset that lacks a name or field advtext calls, with a sentence naming up to five. What is not checked is listed below. A version rule is still imtypeset's H4. | advtext; H4 for the rule |
| P4 | **Confirmed: the installed distribution is the route to rely on**; the environment variables stay as the development override. It is in commit `a6c81ed`, tested with stand-in packages only, because no distribution exists: imtypeset's H3 is queued behind its macOS probe. **When a prebuilt macOS arm64 distribution can exist is not known to anyone**: it waits on H1's run, which waits on the user's push (imtypeset's `sidecar-probe.yml` is written and has never run). One caveat for a frozen bundle: advtext recognises the distribution by its metadata, which freezers drop unless told to keep it; that is with imtypeset under H3. | H1, H3, H5 |
| P5 | **Carried as H19**, queued at imtypeset (task `hidpi`: what the library does at a framebuffer scale of 2, by a run on Linux; a person at a Mac for the rest). On advtext's side: it assumes 96 px per inch in five places and never asks the runner for a scale. advtext will take a density from the host (a parameter, default as today) once H19 says what the library does with one; not before, so as not to guess twice. | H19, then advtext |
| P6 | **Agreed as sequencing, and adopted here too**: advtext does not ask pptmstr to delete a renderer, and the handoff to imtypeset now says H1 comes before anything is built for macOS and H15, H18, H20 before a frozen bundle. Your point that the gate's child would be pptmstr itself relaunched with `-P -B -c`, which its argument parser rejects, is carried to H15 in your words. | H1, H15, H18, H20 |
| P7 | **Built.** `ReaderOptions`, four fields, the same object for a parse, a view and a stream. Two of the four do less, or other, than their names suggest: read the detail. | advtext, `advtext.typeset_markdown` |
| P8 | **Built, both halves, with one way in left open on purpose.** A view takes blocks a host made and a `Description` a host made; every way in through a view refuses an unknown object. `MarkdownConverter.describe` called directly still makes the empty Host block. Detail below. | advtext, views and `advtext.description` |
| P9 | **Carried as H22** (new): the library knows which characters it set from another face or as U+FFFD; advtext cannot count them from outside. advtext will expose the count on a view when the library answers it. | H22 |
| P10 | **Carried as H23** (new). Not checked here whether the library already breaks an unbreakable run at the measure; imtypeset's plan says "a word is never split mid-row", which reads as no. The copy-without-the-breaks half follows from positions being into the text. | H23 |
| P11 | **Built.** Two theme fields, not one size step, and the formula pptmstr needs to set them. Detail below. | advtext, `advtext.theme` and `typeset_markdown` |
| P12 | **Built: wrap, clip, grow per view, with `content_width`.** Under clip the content's width cannot be reported (H30); grow together with columns is not measured; the first frame under grow costs one geometry call a code block. Detail below. | advtext, views; H29, H30 |
| P13 | **Partly met.** One pitch per block is built and met for one block. pptmstr's capped view of many paragraphs is NOT built. A block holding a display formula is not given the pitch. Detail below. | advtext, views |
| P14 | **Built.** `advtext.typesetter.font(face)`. The size to push for a native line is not the em. Detail below. | advtext, `advtext.typesetter` |
| P15 | **Carried**: a rule under every row as H24 (new); the header rule's height is H8, in progress there. | H8, H24 |
| P16 | **Built.** `TypesetDiffView.headers()` and `DiffHeader`. `fits` has no margin where pptmstr's seam counted a spare cell, and an answer asked before a draw does not allow for a capped view's scrollbar. Detail below. | advtext, `TypesetDiffView` |
| P17 | **Answered by a run, and the promise is in `load_fonts`'s docstring.** The atlas takes the fonts after start-up; an open view redraws without being told; **every load leaves seven more fonts on the atlas and nothing takes them off** (H25). pptmstr's sharpened request, a reload that does not grow the atlas, is NOT built. Detail below. | advtext; H25 |
| P18 | **Built.** `reset()`, then `load_fonts()` again. What it does not undo is listed below. | advtext, `advtext.typesetter` |
| P19 | **Partly met.** `table_widths="natural"` is built and met for pptmstr's table to 0.001 px; NOT in general: a stream whose cell was wider while it was written ends wider than the settled view. A host closes it with `set_table_columns`. Detail below. | advtext, views; H31, H32 |
| P20 | **Done in `a6c81ed`.** `imtypeset.ref` at the repository root is tracked: comment lines, then the full hash on the first line that is neither blank nor a `#` comment. It is the one place advtext's CI reads the ref from, and the place to read it from. | done; not pushed |

### What exists, request by request

Names are given as a host reaches them. Thirteen are on the facade
(`from advtext import ...`; listed in "What advtext offers now"); the rest
are reached through the module named and carry no promise yet. Test files
are in advtext's `tests/`.

#### P1: the kind beside the sentence (PH-GATE's builder)

    class Kind(enum.Enum):
        READY = "ready"; NOT_INSTALLED = "not-installed"; REFUSED = "refused"
        FAILED = "failed"; UNSUPPORTED = "unsupported"; UNCHECKED = "unchecked"
    typesetter.kind() -> Kind
    typesetter.unsupported(why: str) -> None
    typesetter.pairing()["kind"]            # the member's string

`Kind`, `kind` and `pairing` are facade names; `unsupported` is
`advtext.typesetter.unsupported`.

- `kind()` asks `module()` first (so it may import, as `pairing()` does),
  then is `Kind.READY` exactly when `module()` is not `None`. **READY says
  nothing of fonts**; `ready()` does. The two words clash and the docstrings
  say so.
- NOT_INSTALLED: no variable and no distribution. REFUSED: something was
  found and cannot be used (the import raised, or names are lacking: P3).
  FAILED: `disable()` was called (a font refused in `load_fonts`, or a draw).
  UNCHECKED is `verdict()`'s only (P2).
- **UNSUPPORTED is the host's to say.** advtext cannot tell it from
  NOT_INSTALLED by itself and does not guess from `sys.platform`: no
  imtypeset distribution exists, so nothing can say "no library for this
  platform" (carried as H26). The host says it:
  `typesetter.unsupported("pptmstr ships no library for Intel Macs")`. Then,
  **only when nothing is found**, `kind()` is UNSUPPORTED and `reason()` is
  the host's sentence, which is the answer to "`IMTYPESET_LIBRARY is not
  set` reads as a broken install". When a library is named or a distribution
  installed, the host's sentence is not used. `""` takes it back; `reset()`
  keeps it.
- `reason()`'s existing sentences are unchanged.
- **Where pptmstr's own code is wrong today** (read by the builder, not
  run): `pptmstr/ui/typeset/gate.py` tells "refused" from "not installed" by
  looking in `os.environ` for the variable, which is wrong on the
  distribution route. `kind()` replaces that.

Tests, `test_typesetter_kinds.py`:
`test_the_kinds_are_these_six_and_their_values_are_strings`,
`test_nothing_to_find_is_not_installed_and_the_sentence_is_the_old_one`,
`test_a_library_that_is_named_and_does_not_load_is_refused`,
`test_an_installed_distribution_that_does_not_load_is_refused_and_named`,
`test_a_package_that_answers_is_ready_and_ready_says_nothing_of_fonts`,
`test_a_disable_is_failed_whatever_it_was_before`, and four `unsupported`
tests. pptmstr named no test for P1.

#### P2: a verdict without loading, and a command line (PH-GATE's builder)

    typesetter.verdict(library=None, python_path=None, *, timeout=120.0) -> dict[str, str | None]
    typesetter.EXIT_CODES: dict[Kind, int]   # READY 0, NOT_INSTALLED 3, REFUSED 4, FAILED 5, UNSUPPORTED 6, UNCHECKED 7
    python -m advtext.typesetter             # one line of JSON: pairing(); exits by the kind

`verdict` is a facade name; `EXIT_CODES` is `advtext.typesetter.EXIT_CODES`.

- `verdict` runs `sys.executable -P -B -c ...`, which performs `pairing()`
  and prints it; the answer has `pairing()`'s twelve keys. It reads and
  writes none of the module's state and imports nothing of imtypeset into
  the asker (held with a stand-in and with the pinned pair).
- `library` / `python_path` are `IMTYPESET_LIBRARY` / `IMTYPESET_PYTHON` for
  the child: `None` inherits, `""` removes (so `verdict("")` asks about the
  installed distribution alone). Not a path: `TypeError` at the call.
- **`"unchecked"`**: `sys.frozen` is set (no child is started: in a frozen
  application `sys.executable` is the application, your P6); `sys.executable`
  is empty; the child did not start, timed out, or exited without an
  answer. **`"refused"`** also when the child was killed by a signal before
  answering (the builder's decision: a library that kills what loads it must
  not read as "not known"). `sys.frozen` was simulated by setting the
  attribute; nothing was run frozen.
- **Another interpreter is asked with the command line, not with
  `verdict`**: an updater testing a new environment runs that environment's
  `python -m advtext.typesetter` and reads the exit code and the JSON. The
  signature has no `executable=`, and the command line takes no arguments.
- Measured by the builder, five runs each, load 5.8 to 7.6: the command line
  takes 91 to 151 ms with nothing to find and 286 to 319 ms with the pinned
  pair (imgui_bundle is imported by the library's own gate; no window, no
  ImGui context).
- What it does not do: load fonts or draw. And the library's gate writes
  its stamp beside the library file from the child, as it would from the
  application.

Tests: `test_the_command_line_prints_the_pairing_and_exits_by_its_kind`,
`test_a_verdict_is_a_childs_answer_and_leaves_the_asking_process_as_it_was`,
`test_a_verdict_names_the_library_for_the_child_and_an_empty_one_takes_it_out`,
`test_in_a_frozen_application_the_verdict_is_unchecked_and_no_child_is_started`,
`test_a_child_that_cannot_be_asked_is_unchecked_and_one_that_is_killed_is_refused`,
and with the library
`test_the_verdict_on_the_pinned_pair_is_ready_and_loads_nothing_into_the_asker`,
`test_the_command_line_on_the_pinned_pair_exits_zero_and_on_a_bad_library_four`.
pptmstr named no test.

#### P3: the imtypeset found has the names this advtext calls (PH-GATE's builder)

    typesetter.REQUIRED: dict[str, tuple[str, ...]]     # the one place
    typesetter.missing(package) -> list[str]            # "Owner.name"; [] when whole

Both through the module. `module()` calls `missing` on what it imported. A
miss is `Kind.REFUSED` and `reason()` is

    the imtypeset at <package dir> lacks N name(s) this advtext calls: A, B, C, D, E and K more; the two were not installed together

(five named at most). Views then raise `TypesetUnavailable`, as for any
refusal, so a partial update falls back and does not reach a draw.
`pairing()` still reports the refused package's `route`, `package`,
`library` and versions, on purpose: a bug report must say which imtypeset
was refused.

**What is checked:** 25 names of the package; 29 members of `Document`; the
fields advtext sets of `BlockStyle`, `Style`, `DocumentOptions`, `Columns`;
the members advtext names of seven enums; that `Block`, `Run`, `Cell` and
`TableColumn` BEGIN with advtext's fields in advtext's order (the package
reads the description's tuples by position); and that `imtypeset.demo` can
be found (it is not imported, and its members are not checked).

**What is NOT checked:** the fields of what the library answers
(`DocumentHit`, `BlockGeometry`, ...); the keywords of its functions;
enumerator VALUES; `Document.edit_error` (set in `__init__`, so not on the
class: H28); and a name that is there and means something else. So this
answers "new advtext, old imtypeset" for names that are missing, and not
for names whose meaning changed.

Two things the builder is least sure of, which bear on you: one missing
name refuses the WHOLE library, including a name only a gallery page of
advtext's demo uses; and in a run without the library the test that keeps
the list complete knows a library document by its variable's name.

Tests: `test_a_package_that_lacks_a_name_is_refused_with_a_sentence_that_names_it`,
`test_the_sentence_names_five_and_counts_the_rest`,
`test_a_tuple_the_library_reads_by_position_must_begin_with_advtexts_fields`,
`test_every_name_of_the_package_advtext_uses_is_on_the_list`,
`test_every_document_method_advtext_calls_is_on_the_list`, and with the
library `test_the_pinned_library_has_every_name_on_the_list`,
`test_no_document_method_is_used_under_a_name_the_reader_does_not_know`.
pptmstr's reading was right: nothing gated this pair before.

#### P7: reader options (PH-MD's builder)

    from advtext import ReaderOptions

    @dataclass(frozen=True, slots=True)
    class ReaderOptions:
        html_as_text: bool = False
        images_as_text: bool = False
        keep_glob_stars: bool = False
        show_link_destinations: bool = False

    parse_markdown(source, theme, *, references=True, math=False,
                   more_may_follow=False, refuses=None,
                   converter_spaces=False, reader=None) -> MarkdownDocument
    describe_markdown(source, theme, *, link_color=0, references=True,
                      math=False, more_may_follow=False, refuses=None,
                      converter_spaces=False, reader=None) -> Description
    MarkdownStream(theme, *, math=False, refuses=None, live_theme=None,
                   converter_spaces=False, reader=None)
    MarkdownStream.reader -> ReaderOptions            (read-only property)
    TypesetView(..., reader=None);  TypesetView.set_document(document, *, reader=<not given>)

Those four fields and no fifth. A `TypesetStreamView`'s reader is its
stream's. All four off is today's reading: the same parser objects, the
same blocks. `reader=` that is neither `None` nor a `ReaderOptions` is a
`TypeError` naming the type, at the call; a field that is not a `bool` is a
`TypeError` from `ReaderOptions(...)`. No host needs
`markdown_rules._parser`.

What each does, precisely:

- **`html_as_text`**: the `html_block` and `html_inline` rules are not run.
  `<div>block</div>`, `<!-- note` and `List<String>` are the characters
  written. An autolink `<https://...>` is still a link; an entity is still
  one character.
- **`images_as_text` is pptmstr's seam's behaviour and not quite its
  name.** The `image` rule is not run. `![alt](address)` is then an
  exclamation mark and a LINK whose text is `alt` and whose target is the
  address: `!alt`. The brackets and parentheses are not set, and **alone,
  the address stays hidden**: it is on screen only with
  `show_link_destinations` too (`!alt (address)`). A linked image,
  `[![build](badge.svg)](run/7)`, comes out as `[!build](run/7)` with the
  INNER address as the link, because markdown lets no link hold another. If
  pptmstr wants the literal `![alt](address)`, that is a different
  implementation and not a tweak (the builder's words): ask.
- **`keep_glob_stars` is pptmstr's own rule** (`_written_stars`), taken
  unchanged, pinned by a test, **and wrong in both directions.** A run of
  stars is text when (a) a `/` is immediately before or after it; or (b) a
  `.` is immediately after it and the character after that `.` is not white
  space or the end; or (c) a letter or digit is immediately before AND
  after it. `**bold**`, `*em*`, `**and/or**`, `**src/x.py**`,
  `**Ends in a stop.**` meet none and stay emphasis. The cases the builder
  lists as wrong: `rm *tmp and old* now` still loses its stars (pptmstr
  pins the same); `**/usr/bin**` and `foo*bar*baz` keep theirs and are not
  emphasis.
- **`show_link_destinations`**: `text (destination)`, or with a title
  `text (destination "title")`, written inside the link; the link's range
  covers text and destination to the closing parenthesis, so it is
  clickable (a hit on a character of the destination answers the link's
  tag, through the library). The destination is markdown-it's normalised
  href. Left unsaid only when the text IS the destination character for
  character, give or take a supplied scheme and one closing `/`; always
  said when there is a title. The same in table cells.

pptmstr's named tests (the builder: "I did not run pptmstr's tests"; its
tests read the blocks and descriptions the views are handed, and the library
where it matters, where pptmstr's read a view):

| pptmstr's test | met? | how it is known |
|---|---|---|
| `test_html_in_a_document_is_shown_and_not_dropped` | yes | `test_reader_options.py`, test of the same name: same source, same five texts, settled and streamed a character at a time; the library copies them back. Its `HIDING` table, 13 rows: `test_text_a_markdown_reader_would_hide_is_set_settled_and_streamed` |
| `test_the_stars_of_a_glob_are_set_and_emphasis_is_still_emphasis` | yes | test of the same name: its `STARS` table, 11 rows, same expectations (text with spaces removed), settled and streamed |
| `test_a_links_destination_is_on_screen_settled_and_streamed` | yes | test of the same name: same source, same four assertions, streamed in fives; and through the library `test_a_shown_destination_is_set_by_the_library_and_a_hit_on_it_is_the_link` |

Settled equals streamed is held after EVERY piece, under each option
(`test_reader_options.py`); the builder's fuzz outside the suite, 6000
generated sources and about 1.36 million pieces, had 0 failures (load 8).

**On pptmstr's reading**: "a view's `str` and a stream use different cached
parsers" is true, and the reason is that a view's string is parsed with
`references=True` and a stream with `references=False`: two parser objects.
With `reader=` both get the option whatever `references` is.

Not in these options, because pptmstr's old seam did them outside the
parser: showing a fence's whole info string (it is `MarkdownCode.language`,
the host's to draw), and breaking an unbreakable word (P10, H23).

#### P8: blocks a host made, and no silent gap (PH-VIEW's builder)

    from advtext import MarkdownText, MarkdownCode, MarkdownRule, MarkdownTable, MarkdownCell, ColumnAlign

    TypesetView(document=None, *, theme=None, palette=None, on_link=None, hand_cursor=True,
                copy_as=None, style_links=None, separator="\n\n", math=None, references=True,
                host_for=None, reader=None, code_overflow="wrap", fixed_line_height=False,
                table_widths="fitted")
    TypesetView.set_document(document, *, reader=<not given>) -> bool

    advtext.description.description_of(blocks, styles, links=()) -> Description
    advtext.description.check_description(description) -> None    # TypeError / ValueError

`set_document` and the constructor take, beside a markdown `str`: a
sequence of `MarkdownText` / `MarkdownCode` / `MarkdownRule` /
`MarkdownTable` (a host's own or `parse_markdown`'s, mixed freely), or
anything with one as `.blocks`; or an `advtext.description.Description`,
used as given. A block's `style` is `theme.style(BlockKind.PARAGRAPH)` and
so on; the constructors' fields are the dataclasses' and were not changed.
Anything else is a `TypeError` at the call naming the type and the block's
number (`block 1 is a Odd, which is not a block a view shows: ...`), and
the view is as it was. Host-made blocks are also checked field by field at
that call (a style that is no `BlockStyle`, runs out of order or past the
text, a link outside the text).

**pptmstr's reading was right, with one detail**: `describe` counts the
block it did not know in `Description.misfits`, which no view ever read.

**Every way in through a view refuses an unknown object:**

| way in | closed by |
|---|---|
| `set_document(sequence)`, the constructor, `set_theme(theme, document)` | a check in `set_document` and again where the blocks are set |
| an object with `.blocks` | the same |
| a `TypesetStreamView`'s stream (a duck-typed one could hold anything) | `TypeError` at the `sync` that meets it |
| a `Description` made by a converter that misfit | `check_description` refuses a non-empty `misfits` |
| **`MarkdownConverter.describe` called directly** | **NOT closed.** It still stands an empty Host block in and counts it; two existing tests (in `test_typeset_markdown.py` and `test_typeset.py`) assert that behaviour. A host that calls `describe` itself reads `misfits` |

A Host block still exists where it is asked for: a block `host_for` answers
for, and a `KIND_HOST` block of a host's own description. A foreign object
is refused even when a `host_for` would have taken it: a host that wants a
widget in a place uses a `MarkdownCode` and answers for it in `host_for`.

For a `Description` the view still owns: the document's own text, highlight,
rule ink, table padding and rule; selection, copy, marks, inks, hit tests,
`scroll_to`, columns, `host_for`; `links` / `hovered_link` / `on_link` from
its `LinkRow`s. It cannot give: the source map (`source` None, `source_of`
None, `selected_source` ""), `Palette.roles` (a style keeps the `Color` it
states), `Palette.link` / `style_links`, a re-reading by `set_theme`.

Not done, said by the builder: `set_theme(theme, document)` with a document
that is refused has already forgotten the old one when it raises (the view
is empty, not "as it was"); a stream's blocks are checked by type only. And
its least sure: that the field check refuses nothing a host legitimately
builds. It is held against advtext's own converter on every demo document
**and against nothing a real host made**; a face must be 0..7 and a
description needs at least one style, which is stricter than the library.

Tests, `test_typeset_host_blocks.py`:
`test_blocks_a_host_made_are_shown_as_their_text_and_not_read_as_markdown`,
`test_host_blocks_are_edited_as_any_blocks_and_mix_with_parsed_ones`,
`test_what_is_no_block_is_refused_at_the_call_naming_its_type_and_number`
(17 cases), `test_every_way_in_refuses_it_and_no_host_block_appears_unasked`,
`test_a_description_a_host_made_is_used_as_it_is_given`,
`test_a_description_that_cannot_be_shown_is_refused_at_the_call`, and with
the library `test_a_host_s_blocks_are_drawn_and_copied_as_they_were_written`,
`test_a_host_s_description_is_drawn_with_its_styles_links_and_table`; and
`test_facade.py::test_a_host_makes_every_block_and_asks_the_kind_through_the_surface`
(all four block types built from facade names, PH-FINAL's builder).
pptmstr names no test for P8. The behaviour behind it ("tool output,
arguments and literal tails are not markdown and must not be read as it")
is met: a `MarkdownCode` of ``$ rm **/*.py\n<div> `not code` [not](a link)``
is described with that text and no run, and a copy of the drawn view gives
it back to the character. Known by those tests.

#### P11: a size for inline code (PH-MD's builder)

    Theme.inline_code_scale: float = 0.0     # multiple of the block's size; 0 is 1
    Theme.inline_code_step: Scaled = 0       # scaled points added to that
    Theme.inline_code_run_scale(kind: BlockKind) -> float

Set with `dataclasses.replace(theme, inline_code_scale=..., inline_code_step=...)`.
Both default, nothing changes. On a monospace base the scale is 0 whatever
they say.

**Two fields and not one size step, because pptmstr's test needs both**: a
code span as TALL as its prose is a ratio, and the role's "-2" is a length,
and a length is a different multiple of a heading than of a paragraph.
**The formula pptmstr needs**, with `p` and `c` the prose and code faces'
(ascent + descent) / em, for a span `d` px taller than its block's text:

    inline_code_scale = p / c
    inline_code_step  = sp_from_px(d / c)

A value that is no size (negative, nan, a step that leaves any block's span
at or below zero) is a `TypeError` / `ValueError` from `Theme(...)` or
`replace(theme, ...)`. A formula shown as its source in the code face takes
the span's scale too. A scaled span can raise its line: see the note under
H33 in `HANDOFF-imtypeset.md`; a host that sizes spans up wants P13's flag
to keep one pitch.

pptmstr's `test_inline_code_is_the_chromes_height_inside_prose_of_the_same_height`:
**met, by the host setting the two fields.** Known by
`test_reader_options.py::test_inline_code_is_the_proses_height_inside_prose_of_that_height`
(with the library): `Theme.at_pixel_height(16)`, `inline_code_scale = p / c`:
the span measures 16.0 px tall in a paragraph (14.3 unscaled, pptmstr's own
number) and the heading's height in a heading; with
`inline_code_step = sp_from_px(-2 / c)`, 14.0. The span's height is read
from the measured advance of a monospace character, not from a style.
pptmstr's reading ("a run carries a face and never a scale") was right at
`38f5fac`; a run carries one now.

#### P12: code overflow per view, with the content's width (PH-VIEW's builder)

    TypesetView(..., code_overflow="wrap")      # "wrap" | "clip" | "grow"
    TypesetView.code_overflow -> str            # property; set_code_overflow(overflow: str) -> bool
    TypesetView.content_width -> float          # property
    TypesetStreamView(stream, *, ..., code_overflow="wrap", fixed_line_height=False)

`"wrap"` is the default and today's. Under grow the prose is still broken
at the pane, the view claims `content_width`, and a child window of the
host's with `WindowFlags_.horizontal_scrollbar` scrolls by itself.

Measured by the builder (headless frames, 444 px pane, a 400-character code
line):

| | code lines | content_width | scroll_max_x | library `size().x` | code block `max.x` |
|---|---|---|---|---|---|
| wrap | 10 | 444.0 | 0 | 444.0 | 440.0 |
| clip | 2 | 444.0 | 0 | 444.0 | 444.0 |
| grow | 2 | 3215.995 | 2771 | **444.0** | 3215.995 |

What is not there:

- **Under clip the content's width cannot be reported**: nothing in the
  library says a line was cut or how long it was. Carried as H30.
- **Grow together with `set_columns` is not measured** (nor clip with
  columns). In columns `content_width` is the page's width as before.
- **The first frame under grow costs one geometry call per code block**,
  because the library's size does not say how far a grown block reaches
  (H29): 128 ms against 12 ms for the first frame of a document with 500
  code blocks of 20 lines (the builder's measurement, load 11.9). Every
  steady frame is exactly LayoutDocument, DrawDocument, GetDocumentSize
  under all three; a steady frame under grow was 66 us against 48 us, which
  the builder measured and did not explain.
- No sideways follow-the-tail in a stream view whose code grows.

Scrolled 1,000 px sideways, the hit test, a drag selection, a mark and
`scroll_to(block, offset)` are where the text is (headless, and the press
and drag again in a real window on Xvfb).

pptmstr's tests: `test_a_code_line_wider_than_the_window_can_be_scrolled_to`:
**met**, known by the test of the same name in
`test_typeset_host_blocks.py` (same assertion: `scroll_max_x > 400 * cell -
window`, and prose still broken to the window) and by the windowed test.
`test_a_wide_line_in_a_fenced_diff_is_the_diff_views_to_scroll`: **met**,
known by `test_a_wide_line_in_a_fenced_diff_is_the_diff_view_s_to_scroll`:
a hosted `TypesetDiffFences` block with a 400-character line leaves the
view's `content_width` at the measure (444.0) and the pane's `scroll_max_x`
at 0, while the hosted view's own content is 3280 px wide.

#### P13: one pitch per block. Partly met (PH-VIEW's builder)

    TypesetView(..., fixed_line_height=False)
    TypesetView.fixed_line_height -> bool       # property; set_fixed_line_height(fixed: bool) -> bool

`fixed_line_height=True` sets the library's `FixedLineHeight` on
paragraphs, headings, list items and code. **Not** on tables, hosted
blocks, **or a block holding a DISPLAY formula** (the builder's decision,
kept by advtext's lead: with the flag a `$$` block is one line height and
its formula is set over the blocks above and below). Inline formulas take
the pitch.

Line tops, with and without (444 px pane, stock theme, a code block of
`├── a` / `│   └── b` / `École Ångström` / `plain` / `█▀▄ blocks` / `last`):

| | tops | line heights |
|---|---|---|
| without | 0, 24, 48, 68, 89.6, 113.6 | 22.4, 22.4, 20, 20, 22.4, 20 |
| with | 0, 20, 40, 60, 80, 100 | 20 x 6 |

**A correction to the request's wording, by that measurement**: at
`c9f8902` and the stock sizes **an accented capital does NOT make a line
taller**, in either face (the `École Ångström` code line is 20.0 px, the
prose 21.6). **Box-drawing and block glyphs in a code block do** (22.4
against 20.0). The paragraph and the list item holding `École`, `Ångström`,
`│`, `├──`, `█` are 21.6 px a line either way. So the hazard is real for
`tree` output and not, here, for accents. The other team's caveat stands:
with the flag, ink overhanging more than 2 px can go undrawn where its line
is just outside the clip.

pptmstr's tests:

- `test_every_line_of_a_block_is_one_pitch_under_the_last_whatever_is_in_it`:
  **met for code and for prose**, known by the test of the same name in
  `test_typeset_host_blocks.py`.
- `test_a_capped_view_ends_on_a_whole_line`: **met for a view of ONE block
  only** (`test_a_view_of_one_block_capped_at_n_pitches_ends_on_a_whole_line`:
  feet at 20, 40, ... 120, so a cap of N pitches is a foot for every N;
  without the option the feet are 22.4, 46.4, 68, 88, 112, 133.6). **NOT
  built for pptmstr's actual case, 30 paragraphs under a cap in pixels**:
  blocks have space between them, so no pitch answers it. A host reads
  `set_lines()` for the feet (one call a block and one a line, once per
  layout). No "foot of the last line under y" helper was added; the builder
  thinks it is about 15 lines and worth asking pptmstr about. Say if you
  want it.

#### P14: the `ImFont` of a face (PH-GATE's builder)

    typesetter.font(face: advtext.Face) -> imgui.ImFont | None

Through the module. It is the library's own entry in the atlas for the
role; `None` when not `ready()`, when the role has no font, and (with a
`trouble()`) when the library raises. Not a `Face`: `TypeError`. After a
later `load_fonts()` the old `ImFont` stays valid and stale: ask again.

pptmstr's `test_a_native_line_in_a_typeset_face_is_the_texts_size`: **met,
with a correction a host must know.** A pushed size is the size. But
advtext sets text by its EM and Dear ImGui's font size is a LINE height, so
**the size to push for a native line is the em times the file's line-height
ratio**, `em * (hhea ascent - descent) / unitsPerEm` of the role's file,
which Dear ImGui then rounds to a whole pixel. The three measured rows are
in this file under "Known and open, as it bears on pptmstr" ("A native
ImGui line in a typeset face"): the builder's, in a real window on a
software renderer, three sizes only. The ratios it used: 1.049 for the code
face and 1.1719 for the prose face. So the same ink at the right size, and
the same ADVANCES only where the file's advance is a whole pixel. No
conversion helper was added. Known by
`test_a_native_line_in_a_typeset_face_is_the_texts_size_at_its_line_height_not_its_em`
(with the library, in a window).

#### P16: whether a diff's file header fit, and its text (PH-DIFF's builder)

    from advtext import DiffHeader

    TypesetDiffView.headers(width_px: float | None = None) -> tuple[DiffHeader, ...]
    DiffRows.headers() -> tuple[DiffHeader, ...]            # pure: texts only
    HostedDiff.headers(width_px: float | None = None) -> tuple[Any, ...]   # the view's
    TypesetDiffView.headers_measured: int                   # times the library measured

    @dataclass(frozen=True, slots=True)
    class DiffHeader:
        file: int                      # index into diff.files
        row: int                       # display row of the header
        text: str                      # label, counts, state: "src/a.py  +1 -1  (new file)"
        warning: str                   # "! <will_not_apply>  ! 2 lines not read ..." or ""
        width_px: float | None         # left edge of view to end of the whole line
        text_width_px: float | None    # ... to the end of `text`
        available_px: float | None     # the width the line is cut at
        line -> str                    # property: text, two spaces, warning
        fits -> bool | None            # property: width_px <= available_px
        text_fits -> bool | None       # property: text_width_px <= available_px

One per file, in the order drawn. `text` and `warning` are AS DRAWN (a
control character of a label is the placeholder); `warning` has its parts
in the order the row has them, the host's `will_not_apply` first.

- `headers()`: `available_px` is the width the header was cut at AT THE
  LAST DRAW; before a first draw it is `None` and so are `fits` /
  `text_fits`.
- `headers(width_px)`: the answer for that width as `draw(width_px=...)`
  would take it, without drawing. Added because pptmstr's seam says the cut
  part ABOVE the view, before it draws the view.
- Library not ready: the texts are answered, every width and `fits` is
  `None`, nothing is raised.
- `width_px` not a number: `TypeError`; nan, inf, negative: `ValueError`.

**Two differences a host must know:**

- **`fits` has no margin.** pptmstr's seam counted a header as cut when
  `(len + 2) * cell > wide`, a spare cell on the right. Here `fits` is the
  set width against the clip. A header within one cell of the edge "fits"
  here and was "cut" there. pptmstr's test is not near that boundary.
- **`headers(width_px)` before a draw does not allow for a capped view's
  vertical scrollbar** (`height_cap`): a 416 px header "fits" 420 asked,
  and is cut at the child's inner width once drawn (tested and documented).
  A host that caps and says headers above asks again after the draw, or
  leaves margin.

Cost: a frame that draws and then asks `headers()` makes exactly the
frame's calls. The widths are the library's, measured in a scratch document
on the FIRST asking and not again for the same lines at the same size;
measured headless by the builder, load 6.1: 59 us (1 file), 0.21 ms (10),
1.65 ms (100). A header whose text changes is measured again, and the
counts are in the header, so a growing diff measures once per arriving line
if the host asks.

pptmstr's `test_a_diff_header_too_long_for_its_view_is_said_above_it_warning_first`
cannot run here. What it needs, run here with its own labels, verdict and
width in a real window, both layouts:

| case (420 px) | pptmstr says above | `headers(420.0)` here |
|---|---|---|
| "src/short.py" + verdict | the warning only | fits False, text_fits True |
| LONG_LABEL + verdict | the warning, then the path | fits False, text_fits False |
| "x.py" + "no" (wide enough) | nothing | fits True |

and `warning == "! may not apply: anchor not found in file"`,
`text == f"{label}  +1 -1"`: the strings its test asserts. So a host loop
`for h in view.headers(wide): if h.fits is False: say h.warning if
h.warning; say h.text if not h.text_fits` reproduces the test's three
outcomes. **Met by construction and by that run; NOT run through pptmstr's
own code.** Held by
`test_typeset_diff_view.py::test_in_a_window_a_header_longer_than_a_narrow_view_did_not_fit_and_fits_a_wide_one`
and its neighbours. pptmstr's reading of the tree for P16 is right.

#### P17: `load_fonts()` after start-up, by a run (PH-GATE's builder)

Real window (Xvfb, software renderer), hello_imgui's runner, imgui-bundle
1.92.900, imtypeset `c9f8902`, one `TypesetView` open from frame 0,
`load_fonts()` called from `pre_new_frame`:

| call | frame | answer | atlas fonts before -> after |
|---|---|---|---|
| start-up (`load_additional_fonts`) | 0 | True | 1 -> 8 |
| again, same files | 5 | True | 8 -> 15 |
| after `disable` (frame 8) and `reset()` | 9 | True | 15 -> 22 |
| `Face.PROSE` registered as DroidSans | 12 | True | 22 -> 29 |
| `unload()` | 15 | | 29 -> 29 |
| after the unload | 17 | True | 29 -> 36 |

**The measured promise**, which is what `load_fonts`'s docstring now states:

- **The atlas takes the fonts**, every time; `font(Face.PROSE)` is a new
  entry each time and after frame 12 it is `DroidSans.ttf`.
- **The view redraws without being told**: 152 vertices on every frame it
  drew, before and after each call; its library document is a new object
  on frames 5, 9, 12, 17 and on no other.
- **Nothing is ever taken off the atlas**: 7 more fonts per call, and
  `unload()` removes none. The old `ImFont` stays valid and stale.
- Called between frames (`pre_new_frame`).

**What is NOT promised**: that the atlas does not grow; a call inside a
frame; a second live ImGui context; a GPU; a display scale other than 1;
macOS. Times are scratch runs, not held by a test: 24.8 to 36 ms at
start-up, 14.8 to 20.9 ms later.

This agrees with pptmstr's own run (8, 15, 22, 29). **pptmstr's sharpened
request, "a reload that does not grow the atlas", is NOT built**:
`load_fonts()` does not remove the previous context's fonts. In a scratch
run only, `imtypeset.remove_font` for each role before the reload took the
atlas from 8 fonts to 1 and the load made 8; neither that nor a call inside
a frame is promised. Whether the library should remove what its context
added is H25 in `HANDOFF-imtypeset.md`.

Two sentences the run corrected: this file's "a run nobody here has made"
(made; the atlas does take them), and `unload()`'s docstring, which said it
gives back "its fonts' share of the atlas" (29 before, 29 after).

Tests (with the library, in a window):
`test_after_start_up_the_atlas_takes_the_fonts_every_time`,
`test_nothing_is_taken_off_the_atlas_by_a_later_load_or_by_unload`,
`test_an_open_view_draws_the_frame_after_as_it_did_the_frame_before`,
`test_a_native_line_is_set_in_the_roles_new_file_after_a_later_load`.

#### P18: the way back (PH-GATE's builder)

    typesetter.reset() -> None        # also `from advtext import reset`

Forgets a `disable` or a refusal; the next `module()` looks for the
variable and the distribution again (one installed since is found),
imports, and checks the names. **`ready()` is false until `load_fonts()` is
called again**: the way back in a running application is `reset()` then
`load_fonts()`, between frames. That sequence was run in a real window
(P17's table: switched off before frame 8, back before frame 9, the view
drew 152 vertices again). It costs 7 more atlas fonts each time (P17).

**What `reset()` does not undo:** the shared object stays mapped and the
package imported (after a `disable`, "asks again" takes the same package
from `sys.modules`, and the library's own gate does not run twice); a
library replaced on disk is not picked up; the library's context, documents
and atlas fonts are untouched; `trouble()`, the host's `unsupported()`
sentence and which package `pairing()` describes are kept.

The private `_forget()` is not an alias and still exists for advtext's
tests ("back to the state at import").

Tests: `test_reset_after_a_disable_asks_again_and_fonts_are_to_be_loaded_again`,
`test_reset_after_a_refusal_imports_again`,
`test_reset_finds_a_distribution_installed_since`,
`test_what_reset_keeps_and_what_it_lets_be_said_again`, and with the
library `test_the_way_back_with_real_fonts_sets_text_again`. pptmstr named
no test; its behaviour ("one provoked failure switches the library off for
the rest of a test process") is met: the last test provokes one, resets,
loads fonts and lays a document out.

#### P19: a settled table at its natural widths. Partly met (PH-VIEW's builder)

    TypesetView(..., table_widths="fitted")     # "fitted" | "natural"
    TypesetView.table_widths -> str             # property; set_table_widths(widths: str) -> bool
    TypesetView.set_table_columns(block, columns) -> bool

`table_widths="natural"` holds every table whose columns nobody states at
the widths its cells want, as a stream holds one. The default is unchanged.
A `TypesetStreamView` refuses `set_table_widths` (`TypeError`): its tables
are its stream's policy.

pptmstr's `test_a_table_that_fits_keeps_its_natural_widths_settled_as_it_had_streamed`:
**met for pptmstr's table, to 0.001 px, and NOT in general.**

- Met: `test_a_settled_table_at_its_natural_widths_is_where_its_stream_held_it`
  (pptmstr's own table, and a table after prose): a stream view given the
  source whole and three characters a frame, then a
  `TypesetView(source, table_widths="natural")`: every column edge equal to
  0.001 px. `test_a_table_too_wide_for_the_measure_is_fitted_under_both` is
  the other half.
- **Not in general**
  (`test_a_cell_wider_while_it_was_written_leaves_the_stream_s_column_wider`):
  a held column is the widest its cells have EVER wanted, and
  `**bold words**` arriving three characters a frame is for some frames the
  literal `**bold wor`. That stream ends with columns **4.93 and 2.43 px
  wider** than the same table given whole (95.031 -> 99.961, 53.516 ->
  55.945).
- **What closes it today is the host's**: state the stream's widths on the
  settled view, `settled.set_table_columns(at, [c.max - c.min, ...])` from
  the stream's columns; tested to 0.001 px. It gives up the refit when the
  pane is later too narrow. (Under `"natural"` a table whose columns are
  stated is not held, because the library ignores stated widths on a held
  table: H31.)

**Withdrawn**: the earlier wording of this row, that the option lets "a
stream and the settled view that replaces it agree", and any reading of it
as "a replacement moves no column". That holds only when no cell was ever
wider than it ended, or when the host states the widths. A table that could
be seeded with widths would close it in the library: H32.

### What remains unbuilt, of P1 to P20

History: the lead's first answer listed an order of building (P8, P7, P1
and P18, P12 and P13, then P3, P2, P11, P14, P16, P19, P17's run). All of
those are built as far as the entries above say. What is left:

- **P13**: a capped view of many blocks ending on a whole line (a host
  reads `set_lines()`); a display formula's block has no fixed pitch.
- **P19**: a stream whose cell was wider while written; closed only by the
  host stating widths (H31, H32).
- **P17**: a reload that does not grow the atlas (H25).
- **P12**: the content's width under clip (H30); a cheap content width
  under grow (H29); grow or clip with columns, unmeasured.
- **P8**: `MarkdownConverter.describe` called directly still makes the Host
  block.
- **P1**: "unsupported" from the library itself (H26). **P2**: anything in
  a truly frozen application (H15). **P3**: a version rule (H4).
- **P5, P9, P10, P15**: carried to imtypeset and waiting there (H19, H22,
  H23, H24, H8). **P4**: no distribution exists (H1, H3, H5).
- Nothing was run on macOS, on a GPU, at a display scale other than 1, or
  frozen; nothing was run through pptmstr's code; nobody looked at a
  screen.

### P21 to P24 (read at pptmstr's commit `e73f087`; answered 2026-10-12 by advtext's lead, an agent)

None of these is built. Each is being measured on this side first, because
what advtext said earlier about advances was wrong once already.

| # | answer | where it goes |
|---|---|---|
| P21 | **Taken as the most important open request, and it is the typesetting core's.** Your R1 to R6 describe one thing: layout from the rasteriser's baked, whole-pixel advances, so that what is drawn is what was laid out and N monospace characters are N times one constant that ImGui also uses. The library lays out from the font file (7.63 px at a 16 px pixel height) and snaps when it draws; nothing in advtext can make those agree. Carried to imtypeset as **H34**, with R1 to R6 and your figures. Two facts to hold beside it, the first measured here and the second not: at an **em** of 16 (not a pixel height of 16) the file's advance for the code face is exactly 8.0 px (advtext's PH-GATE builder: 40 characters lay out at half an em each at ems of 14 to 20), so columns would hold at that size, with glyphs about 5 % larger than ImGui's at pixel height 16 and a line 16.78 px tall; **nobody has run your probe at an em of 16**. advtext is now reproducing your P21 and P22 measurements through its own views at both sizes, and will put the numbers here. Your decision to keep code, diffs and tool output on your own renderers until this is answered is the right one, and this file's "Built" for P12, P13 and P16 should be read with it: built, and not yet usable by you for code. | H34; measurement in hand here |
| P22 | **Carried as H35.** A glyph drawn up to 16.9 px from where layout and `span_rects` put it means selection, marks and hit tests are over the wrong characters; that is not something a view can paper over. Being reproduced here with P21. | H35; measurement in hand here |
| P23 | **Being investigated here; it may be advtext's.** Either the theme's `Spacing.FRENCH` does not reach the library through the description, or a sentence space survives it. Not yet known which. | advtext first, then the core if it is the core's |
| P24 | **Accepted, advtext's.** `ready()` must be false and a view must raise `TypesetUnavailable` once the ImGui context the fonts were loaded in is gone, with or without `unload()`. The other team's rule (their answer (c)) is that the library cannot always tell either: a new ImGui context at the old one's address is taken for the old one. advtext will record which ImGui context the load was made in and compare, as your gate now does. | advtext, `advtext.typesetter` and the views |

A note on **R7** ("by the operator's eye", your commit `a0ce752`): the user
chose hinted advances for prose from three pictures drawn by the old rule.
That choice is quoted to imtypeset with H34 as the user's recorded
preference; it is the user's to restate for the new core, and nobody here
will infer it.

### P21 to P23, measured (2026-10-12)

Measured by advtext's Q-MONO builder, an agent, through `advtext.TypesetView`
in a real hello_imgui window on imtypeset `c9f8902`; imgui-bundle 1.92.900,
FreeType, loader flags 0, density 1, Xvfb; one-minute load average 2.2 to
3.7; runs repeated and identical. The vertex buffer was read and no pixel;
nobody looked at a picture. Scripts and every number are on disk in the
advtext checkout under `.concerns/Q-MONO-scripts/` and
`.concerns/Q-MONO--builder--result.md` (untracked).

**P21. Your figures reproduce exactly** at mono, pixel height 16: advance
laid out 7.6263, the ruler drawn as fifteen steps of 7 then twenty-four of 8,
the 40th character at 297 against ImGui's 312, rows 13 px apart at one column
over your seven rows.

**Monospace columns hold at an EM of 14, 16, 18 and 20** (`Theme.build(16,
...)`, not `Theme.at_pixel_height(16, ...)`): one step (7, 8, 9, 10 px) in
170 of 170, 0 px between rows, characters 1, 10, 20, 30, 40 and 74 drawn on N
times the advance and on ImGui's pen in the same font, 0.00 px between a
glyph and its rectangle. **They do not hold at an em of 15 or 17, nor at any
pixel height from 14 to 20**, in an all-mono theme or the default one.

| size | laid-out advance | ImGui's baked advance | ruler's steps in order | 40th character: drawn / laid out / ImGui | worst between rows, px |
|---|---|---|---|---|---|
| em 14 | 7.0000 | 7 | 7 x39 | 273 / 273.00 / 273 | 0 |
| em 15 | 7.5000 | 8 | 8 x19, 7 x20 | 292 / 292.50 / 312 | 17 |
| em 16 | 8.0000 | 8 | 8 x39 | 312 / 312.00 / 312 | 0 |
| em 17 | 8.5000 | 9 | 9 x19, 8 x20 | 331 / 331.50 / 351 | 17 |
| em 18 | 9.0000 | 9 | 9 x39 | 351 / 351.00 / 351 | 0 |
| em 20 | 10.0000 | 10 | 10 x39 | 390 / 390.00 / 390 | 0 |
| px 14 | 6.6730 | 7 | 6 x13, 7 x26 | 260 / 260.25 / 273 | 15 |
| px 15 | 7.1497 | 7 | 8 x6, 7 x33 | 279 / 278.84 / 273 | 8 |
| px 16 | 7.6263 | 8 | 7 x15, 8 x24 | 297 / 297.43 / 312 | 16 |
| px 17 | 8.1030 | 8 | 9 x4, 8 x35 | 316 / 316.02 / 312 | 6 |
| px 18 | 8.5796 | 9 | 8 x16, 9 x23 | 335 / 334.60 / 351 | 15 |
| px 19 | 9.0562 | 9 | 10 x2, 9 x37 | 353 / 353.19 / 351 | 3 |
| px 20 | 9.5329 | 10 | 9 x18, 10 x21 | 372 / 371.78 / 390 | 16 |

("Worst between rows" is over the builder's eight rows; over your seven it is
13, 13, 15, 16 at pixel heights 14, 16, 18, 20, your four figures.)

At an em of 16 the glyphs are from ImGui's 17 px raster (the library asks for
16.78 and ImGui bakes whole sizes) on 8 px pens; ImGui's own advance for
Inconsolata is 8 px at a pixel height of 16 and of 17, so a native line at
either stands on the same pens. Typeset em 16 beside ImGui at 16 on one page
was not run; em 16 against 17, and ImGui at 16 on another page, were, and
both put the 40th character at 312.

**What this means for you, and a sentence of this file withdrawn.** The
answer to P21 above says "nothing in advtext can make those agree". That is
wrong as written: the host chooses the em, and at an em whose half is a whole
pixel (14, 16, 18, 20 for this face) drawn, laid out and ImGui agree to 0.00
px **today, with no change to the library**. `Theme.at_pixel_height`, the
route your seam uses, is the one route on which columns never hold. So a
monospace theme stated as an em of 16 gives you R4 and R5 now, at the cost
that the glyphs are the 17 px raster (about 5 % larger than at a pixel height
of 16) and the line is taller. Whether that is acceptable is yours and the
operator's; H34 stays open with imtypeset for every other size. advtext has
NOT built a rule that gives code blocks such an em by itself (an agent's
decision, the lead's: it would silently change sizes a host stated).

**Correction to P14 / A3:** push the size with `imgui.push_font(font, em x
ratio)`, which makes it a whole number of pixels. `ImDrawList.add_text(font,
em x ratio, ...)` does not: at em 16 it draws the 17 px raster scaled by
0.987 and its 40th character is 3.96 px short of the typeset one.

**P22. Selection, carets and `span_rects` follow LAYOUT.** The fill the
library draws for characters 21 to 40 of the 74-character row at mono pixel
height 16 is at x 176 to 328 (`span_rects`: 175.78 to 328.30); the pen of
character 21 is at 163 and of character 41 at 316. So the highlight is 13 px
right of the first glyph it is for, where a character is 7.63 px. 75 carets
of that row are each exactly at its rectangle's left edge. Worst glyph
against its rectangle: 18.2 px left (default faces, pixel height 20), 18.0 px
right (em 15 and 17); **0.00 at ems 14, 16, 18, 20**. A row's first glyph and
its whole width are within 0.5 px of layout at every size. Your 16.9 px is
the builder's -17.16 at pixel height 16 counted from the row's first glyph.
In prose: -3.2 to +2.5 px over 286 glyphs at 26 sizes; a 40-digit number in
Roboto, up to 9.8 px. Hit tests were not measured.

**P23. advtext's defect, fixed** (commit named below).
`typesetter.base_style` never told the library the theme's spacing, so every
document was laid out under the library's default, which is what advtext's
default means and is why nothing showed until you asked for `FRENCH`. The
wide space was the one after `waffle.` (a full stop after a lower-case
letter; at 18 px it ends a line, which is why you saw none there). With the
fix your 52 spaces are 52 at 7.626. `tests/test_typeset_spacing.py`. A fenced
block's spaces were one width before and are after. `NONFRENCH` now reaches
the library too (its `TeX` rule, where it had `Sentence`); a justified
`NONFRENCH` line was not measured.

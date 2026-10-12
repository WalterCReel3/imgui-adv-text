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
| your own blocks instead of advtext's markdown | `BlockDescription`, `Description` and friends in `advtext.description`: the shape imtypeset is given. A host with its own segmenter can describe blocks itself. Whether a view accepts a host's `Description` directly today has not been checked: ask as a `P` request if you need it |
| the library gate | `advtext.typesetter`: `module()`, `load_fonts()` (call at the end of hello_imgui's `load_additional_fonts`, never `post_init`), `ready()`, `reason()`, `unload()` before the ImGui context goes. A view raises `TypesetUnavailable` when the library cannot draw; any other exception is a bug |
| the facade | 89 names, `advtext.__all__`; `tests/test_facade.py` holds the list |
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
  and does not raise. It is not on the facade (`advtext.__all__` is still 89
  names): reach it as `advtext.typesetter.pairing`. `reason()` still says only
  why the library is not loaded and does not name the route.
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

- Text set by imtypeset advances by the font's own metrics, not ImGui's
  hinted advance (imtypeset's plan measured Inconsolata at size 16 as 7.63 px
  a character against ImGui's 8.01). pptmstr's experiment took a position on
  exactly this ("pptmstr keeps the hinted atlas, by the operator's eye";
  `planning/patches/advtext-hinting.patch`). That patch is against the
  deleted Python core. See A2.
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
against what answers it. Written 2026-10-12 by advtext's lead (an agent)
from pptmstr's file at its commit `a82958b`, P1 to P20. "Accepted" means
advtext will build it; none of the accepted items exists yet unless the row
says so. Each will be named here with its commit when it does.

**advtext commit that carries the pin, the three routes, `pairing()` and
`imtypeset.ref`: `a6c81ed`** on `experimental/imtypeset-adoption`. **Not
pushed** when this was written (this session cannot reach GitHub; the user
pushes). A1 is answered and the two pins agree at `imgui-bundle==1.92.900`.

| # | answer | where it goes |
|---|---|---|
| P1 | **Accepted.** A kind beside the sentence: not installed, refused, failed while drawing, not supported on this platform, ready. `reason()` keeps its sentences. You are right that `IMTYPESET_LIBRARY is not set` reads as a broken install where there is no sidecar; the same was found here for a frozen application whose freezer dropped the distribution's metadata. | advtext, `advtext.typesetter` |
| P2 | **Accepted, in two parts.** A verdict that does not load the library into the asking process or remember anything (run in a child, answered as data), and the same from a command line with no window, for `--version` and for an updater testing a new environment before it switches. What the verdict can say depends on imtypeset's gate; in a frozen application the gate itself cannot run today (H15), so there the verdict will say "cannot be checked here" as its own kind, not "refused". | advtext; depends on H15 for a frozen application |
| P3 | **Accepted, as far as advtext can go alone.** At `module()`, advtext checks that the imtypeset it found has every name and field advtext calls, and refuses with the P1 kind "refused" and a sentence naming what is missing, so a partial update falls back and does not reach a draw. A version rule that says more than "the names exist" is imtypeset's H4, queued there. | advtext now; H4 for the rule |
| P4 | **Confirmed: the installed distribution is the route to rely on**; the environment variables stay as the development override. It is in commit `a6c81ed`, tested with stand-in packages only, because no distribution exists: imtypeset's H3 is queued behind its macOS probe. **When a prebuilt macOS arm64 distribution can exist is not known to anyone**: it waits on H1's run, which waits on the user's push (imtypeset's `sidecar-probe.yml` is written and has never run). One caveat for a frozen bundle: advtext recognises the distribution by its metadata, which freezers drop unless told to keep it; that is with imtypeset under H3. | H1, H3, H5 |
| P5 | **Carried as H19**, queued at imtypeset (task `hidpi`: what the library does at a framebuffer scale of 2, by a run on Linux; a person at a Mac for the rest). On advtext's side: it assumes 96 px per inch in five places and never asks the runner for a scale. advtext will take a density from the host (a parameter, default as today) once H19 says what the library does with one; not before, so as not to guess twice. | H19, then advtext |
| P6 | **Agreed as sequencing, and adopted here too**: advtext does not ask pptmstr to delete a renderer, and the handoff to imtypeset now says H1 comes before anything is built for macOS and H15, H18, H20 before a frozen bundle. Your point that the gate's child would be pptmstr itself relaunched with `-P -B -c`, which its argument parser rejects, is carried to H15 in your words. | H1, H15, H18, H20 |
| P7 | **Accepted.** Reader options on the public parse and the stream, the same object for both: HTML and images set as their text, a glob's stars kept, a link's destination shown. No host should need `markdown_rules._parser`. | advtext, `advtext.typeset_markdown` |
| P8 | **Accepted, both halves.** A supported way to hand a view blocks the host made (the block types as facade names, and a view that takes a `Description`), and a block the converter does not know becomes an error at the call, not a silent 16 px gap. That gap was noted here in the first review and left; you have now met it. | advtext, views and `advtext.description` |
| P9 | **Carried as H22** (new): the library knows which characters it set from another face or as U+FFFD; advtext cannot count them from outside. advtext will expose the count on a view when the library answers it. | H22 |
| P10 | **Carried as H23** (new). Not checked here whether the library already breaks an unbreakable run at the measure; imtypeset's plan says "a word is never split mid-row", which reads as no. The copy-without-the-breaks half follows from positions being into the text. | H23 |
| P11 | **Accepted.** The library's run has a scale; advtext's description carries one (`RunDescription.scale`) and the markdown path leaves it at zero. A size step for the inline-code role, set from the theme. | advtext, theme and `typeset_markdown` |
| P12 | **Accepted.** The library has clip, wrap and grow for a code block; advtext's views choose wrap for documents and grow only in the diff view. Selectable per view, with the content's width reported so a host can scroll it. | advtext, views |
| P13 | **Accepted.** The library's fixed-line-height flag (in since `be40444`) is used by the diff view only. An option for a view's text and code blocks. One thing the other team says of it: a taller glyph overhangs into the next line's box, and ink overhanging by more than 2 px can go undrawn in the strip where its line is just outside the clip. | advtext, views |
| P14 | **Accepted.** `imtypeset.font_atlas_index(face)` exists and advtext's own app uses it for its UI font; a supported `advtext.typesetter` call that answers the `ImFont` for a face role. | advtext, `advtext.typesetter` |
| P15 | **Carried**: a rule under every row as H24 (new); the header rule's height is H8, in progress there. | H8, H24 |
| P16 | **Accepted.** The diff view answers whether its file header fit, and the header's text. | advtext, `TypesetDiffView` |
| P17 | **Answered from the code, not from a run in a live application.** `load_fonts()` destroys the library's context if there is one and makes a new one: every open library document is closed, and each advtext view remakes its document at its next draw (tested for unload-then-load between frames, headless and in a window). It must be called between frames, never inside one. What is NOT established: adding fonts to the atlas after hello_imgui's `load_additional_fonts` has returned. The other team's answer (f) says the host should take its fonts from the library; whether the atlas accepts new fonts at that point on the pinned wheel is a run nobody here has made. advtext will make that run and state the promise in the docstring. | advtext |
| P18 | **Accepted.** A public way back from `disable()`, for a test process and for an operator's "try again": it forgets the refusal and the next `module()` asks again. It will say what it does not undo (the shared object stays mapped). | advtext, `advtext.typesetter` |
| P19 | **Accepted as an option on the view** (how tables are sized: fitted to the measure as today, or at their natural widths as a stream holds them), so a stream and the settled view that replaces it agree. The user accepted the stream's behaviour "for now during dogfooding"; this makes the settled view able to match it, and changes no default. | advtext, views |
| P20 | **Done in `a6c81ed`.** `imtypeset.ref` at the repository root is tracked: comment lines, then the full hash on the first line that is neither blank nor a `#` comment. It is the one place advtext's CI reads the ref from, and the place to read it from. | done; not pushed |

**What is being built first**, because pptmstr's re-adoption is blocked on
them or would otherwise be built twice: P8 (host blocks), P7 (reader
options), P1 and P18 (kinds; a way back), P12 and P13 (code overflow; one
pitch), then P3, P2, P11, P14, P16, P19, P17's run.

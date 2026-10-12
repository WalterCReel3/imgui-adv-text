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

Nothing asked yet.

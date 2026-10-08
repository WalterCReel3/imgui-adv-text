# advtext

Text layout for Dear ImGui built on TeX's model: a document is a tree of
**boxes**, **glue**, **kerns** and **penalties**, packed by `hpack`/`vpack`,
broken into lines by a total-fit pass over badness and demerits, and shipped out
as absolute glyph positions.

Owning every glyph position is the point. ImGui text is not selectable because
the widget owns the layout; once the layout is ours, hit testing is arithmetic
over numbers we already computed.

**New here? Read [`docs/status.md`](docs/status.md).** It is the honest account
of what works, what is unverified, and what is wrong — written last, after the
gate, and it is shorter than this repository is.

**Came back after 2026-10-06? Read the first section of
[`docs/adoption-plan.md`](docs/adoption-plan.md) before anything else.** That
plan — make this a library another application embeds — was implemented in one
unattended session by a team of agents. The section lists every change to
behaviour that had already shipped, each with its measurement and none of them
looked at by a person; what ran in a window; and what is open. Since then
"total-fit" in the paragraph above is true of justified text only: text that is
not justified is filled first-fit at its natural spacing.

**And a second build followed the same day, 2026-10-07:** the demo is now a
sidebar of fourteen pages, and the library has a diff view, inline mathematics
from a `$...$` subset, blocks a host widget draws, and more calls on a view.
Its account is the first section of that same document, "Second build", and it
opens with the changes made without anybody seeing them and the choices left
for a person. No agent judged how any of it looks, and nothing here says.

## Thirty seconds

    make run        # the ImGui demo: a sidebar of fourteen pages
    make shot       # one page of it as a PNG, ~2.3s, without watching a window open
    make svg        # the same layout with no GPU, no display and no ImGui
    make check      # ruff + black --check, mypy --strict, pytest
    make help       # every target, and which interpreter it will use

`make shot` is the one to reach for when you want to *see* something and cannot
sit in front of a window — it drives the real app through the real `immapp.run`,
counts frames, and grabs the framebuffer:

    make shot ARGS="--tab columns:3 --width 1400 --out artifacts/columns-3.png"
    make shot-all   # every page in each state it names for itself: 26 PNGs

It needs a display and numpy. `make shot-headless` is the Xvfb fallback for a
machine with neither.

`make svg` writes five files into `artifacts/` (gitignored — they are outputs;
the script that makes them is what is version-controlled):

| file | what it shows |
|---|---|
| `markdown.svg` | the sample document, every glyph a real outline |
| `markdown-debug.svg` | the same, with line boxes, baselines and glue overlaid |
| `selection.svg` | a multi-line drag, highlighted by `advtext.selection` |
| `sigma.svg` | the display-size summation |
| `sigma-compare.svg` | display against text style, to show the operator is a *different glyph* |

Open `markdown-debug.svg` first. It is the one that shows the machinery.

## Embedding it

The demo is no longer the smallest consumer. `advtext` itself is an import
surface (`advtext.__all__`, 94 names since the second build and 58 before it,
resolved lazily: `import advtext` loads neither ImGui nor fontTools), and five
examples use nothing else of the package:

    python examples/minimal.py           # a markdown string in a plain ImGui window
    python examples/theme_gallery.py     # one document, four schemes: light, dark, all-mono, swapped italics
    python examples/stream_replay.py     # demo/stream.md arriving in pieces; a commit-policy toggle
    python examples/chat_transcript.py   # three finished messages and one streaming, monospace, ragged
    python examples/diff_minimal.py      # a diff from before/after text; --side-by-side, --edits

Each takes `--frames N` to draw N frames and exit, which is how the tests run
them. What a host calls, in the order it calls it:

| step | names |
|---|---|
| fonts | `register_font`, `load_faces` → `LoadedFaces`, `em_size_for_pixel_height` |
| theme | `Theme.build(faces=, align=)`, `Theme.at_pixel_height`, `Faces`, `Faces.mono()`, `Align` |
| blocks | `build_document`, or `text_block` / `code_block` for text that is not markdown |
| a settled document in a pane | `BareView`: fills the pane, paints no background, selectable, culled |
| colour | `Palette.with_roles`, `DARK_PALETTE`, `ColourSpan`, `find_spans`, `BareView.set_colours` |
| links, copy, context menu | `BareView(on_link=, copy_as=)`, `selected_source`, `under_mouse` |
| tables | cells wrap; `with_columns`, `table_columns` to supply widths |
| a document that arrives in pieces | `StreamDocument`, `CommitPolicy`, `StreamView` |
| a diff | `Diff.from_texts`, `Diff.from_edits` (several edits), `Diff.from_unified` (text that arrives as a diff), `UnifiedDiffStream`; `DiffView`, `DiffLayout`, `DiffPalette` |
| a fenced `diff` drawn as one, or any widget in a block's place | `host_for=DiffFences(...)` on a view; `HostFor`, `Hosted`, `HostBlock`, `HostedDiff` |
| `$...$` and `$$` | `build_document(..., math=markdown_math())`, off unless asked for; `formula_spans`, `FormulaSpan`; `typeset`, `supported_commands` |
| where things are, and what a layout cost | `BareView.block_rect`, `span_rects`, `to_screen`, `scroll_to`, `layout_stats` → `LayoutStats`; `FindIndex`, `TextMatch`; `table_column_limits` → `ColumnLimits` |

**A host that holds the before and after text must build its diff from them**
(`from_texts`, `from_edits`) and not from a unified string of its own making:
`difflib` over texts with no closing newline writes a removed and an added line
as one physical line, which no parser can take apart. `docs/adoption-plan.md`
has the measurement. The math subset has no matrices (left out for now, by the
user's decision), no accents, no `\dfrac`; what it cannot set it shows as source.

`DocumentView`, the page with its sheet and capped measure, is the demo's
presentation and is not in that surface.

**Nobody has looked at any of the five examples.** Each has been opened in a
real window on Xvfb by its tests and drew every glyph it shipped; that is a
statement about counts. The dark palette, the link underline, a stream at
reading speed and monospace set ragged are all there to be judged and have not
been.

## The two litmus tests

1. **Multi-type markdown** — headings, paragraphs with bold/italic/code, lists,
   block quotes, fenced code, a rule and a table, laid out as one document and
   selectable with the mouse.
2. **A sigma summation** — `\sum_{i=1}^{n}` with limits above and below a
   display-size operator, from the real `MATH` table in Latin Modern Math. The
   big sigma is a genuine larger glyph off the variant chain
   (`summation.v1`, which has **no codepoint at all** in the font), not the body
   glyph scaled up.

Both pass. [`docs/litmus.md`](docs/litmus.md) is the write-up, including what is
still wrong with the output.

## `make run` needs a display, and on this machine there is one

The ImGui demo is real, `make run` launches it, and **it has been run and
photographed**. Since 2026-10-07 it is one window, 1300x800 by default, with a
sidebar list on the left and the chosen page on the right. The pages are
modules under `advtext/ui/pages/`, found by scanning the package; adding one
edits no list anywhere. To open on a page, or to photograph every one:

    make run ARGS="--tab diff"
    make run ARGS="--tab stream:table,done"
    make shot-all

A name after `--tab` is a page's name in lower case, optionally with option
words of its own after a colon; `python scripts/shot.py --list` prints the 26
requests `make shot-all` photographs.

| group | page (`--tab`) | what it is, in one line |
|---|---|---|
| Typesetting | Document (`document`) | the markdown litmus test, justified on a page sheet and selectable with the mouse |
| | Columns (`columns:1`..`3`) | the same material flowed into one, two or three newspaper columns by `advtext.columns` |
| | Specimen (`specimen`) | the six faces side by side, a size ladder, and a kerning demonstration |
| | Formula (`formula`) | eleven hand-built formulae, each the only witness to one rule of TeX's math mode |
| | Blocks (`blocks`) | `advtext.blocklayout`'s toolbar at three widths |
| | Math in text (`math`) | `$...$` and `$$` formulas in paragraphs, a heading, a list, a table; a source box; a stream; what is refused and why |
| Embedding | Themes (`themes`) | one document under four palettes, three face sets and any pixel size, optionally split in two |
| | Tables (`tables`) | drag a column edge and the cells re-wrap |
| | Find (`find`) | a search box over a long document: every match marked, next and previous |
| | Inspector (`inspector`) | point at a block: its source, role, indices, unit, and what the last relayout reused |
| Streaming | Stream (`stream`) | one source replayed as tokens under both commit policies, with counters |
| | Chat (`chat`) | a canned conversation, no network: streaming replies with code, a diff, a table, math, one selection |
| Diff | Diff (`diff`) | unified, side by side or both, on eighteen cases a coding agent's host is handed, nine of them hard |
| Performance | Stress (`stress`) | 1 to 16 panes at once, finished or streaming, with the library's per-frame cost |

The first five are the tabs the demo had before, moved without change to what
they draw. **The other nine have each run in a real window on Xvfb and been
photographed there, and no person and no agent has looked at any of them.**

Without a display it refuses rather than hanging: `scripts/run_demo.py` exits 2
in 0.04s and prints the `make shot` recipes instead. The hang belonged to Xvfb
alone, and `make shot-headless` is where that path lives now.

**What that does and does not leave unverified.** ImGui's context, font atlas and
vertex buffers all run headless — *a window needs a display, a frame does not* —
so glyph rasterisation, advances, the ascent conversion and `draw`'s output are
asserted on with no display at all. Compositing is no longer on the unverified
list, and since 2026-10-06 neither is selection with the mouse, up to a line
that is drawn here exactly.

**"On this machine there is one" is a statement about the machine, not about
every session on it.** From the sandbox the adoption session ran in,
`DISPLAY=:1` was set and unreachable (`socket(AF_UNIX)` refused), and every
window that session opened was on an Xvfb in a user namespace over TCP —
`scripts/mouse_probe.py`'s `xvfb_command` builds that shell. The photographs
this section describes were taken earlier, on the GPU.

**What has been exercised.** `scripts/mouse_probe.py` runs the real app in a real
GLFW window and posts mouse and key events to ImGui's input queue over glyph
positions read back from the view: a drag in each direction, a drag across three
lines, a double click, a triple click, Ctrl+C read back from the clipboard, a
wheel scroll followed by a drag on a line that had been below the fold, and a
drag that ends on a line beneath the bottom of the window and is then copied.
Eighteen checks on the selected range and the selected or copied text, all
passing, with expectations built from the shipped glyphs and the markdown source
rather than from the selection code:

    python scripts/mouse_probe.py --xvfb        # 18 of 18, about 3.5 s
    python scripts/mouse_probe.py --no-window   # the same script, bare ImGui context

`tests/test_mouse_probe.py` runs both, and shows the probe going red against a
view that hit-tests from the wrong origin and against one that never copies.

**What has not.** The events enter at `ImGuiIO`, not at the X server: no pointer
has been moved on a screen and no physical button pressed, so GLFW's cursor and
button callbacks and a window manager's part in focus and capture are untested.
The window was on an Xvfb with Mesa's software rasteriser, not on a GPU, and
there was no window manager. No person has dragged a selection in this demo and
said what it was like. And the earlier caveat stands: the photographs are from
**one GPU on one machine.** `docs/status.md` section 2 and
[`docs/imgui-risks.md`](docs/imgui-risks.md) now say the same thing this section
does.

The **SVG backend** is not a fallback for that. It emits real glyph outlines
through fontTools and needs no GPU and no ImGui at all, and a layout that two
unrelated backends can render has had its geometry separated from its drawing —
which is the property that made selection tractable.

## Interpreter

    make bootstrap  # builds ./.venv and every target picks it up, no edit needed

Until that runs there is no interpreter: every target that needs one stops and
names `make bootstrap`. `make venv-info` says what the others will use.
`pyproject.toml` states genuine dependency floors and is installable normally;
the one that matters is `imgui-bundle>=1.92.900`, the first release with the
draw-list flag the backend sets.

This used to say `make` drove a **borrowed** interpreter from a sibling project,
`../pptmstr`. That fallback was removed on 2026-10-06: the sibling is the
application meant to depend on this library, and a build that reaches back into
its consumer cannot be depended on. The sandbox this was first built in reached
only one host, so `pip install` could not run in it, and the borrowed venv was
how the project existed at all; `docs/decisions.md` keeps that history.

## Measuring it

    python scripts/bench_reflow.py     # compose / ship / selection index
    python scripts/bench_draw.py       # the per-frame ImGui draw cost
    python scripts/verify_advances.py  # ImGui's advances against fontTools'
    python scripts/verify_ascent.py    # ImGui's baked ascent against ours

All four run here with no display. Every performance claim in this tree came out
of one of them, and each prints the table its own docstring quotes — so a number
you read in a docstring can be re-derived rather than trusted.

## Where the reasoning lives

**New here? [`docs/guide/`](docs/guide/README.md)** — five short documents
covering the idea, which parts of TeX are implemented, the rendering decisions
and where they depart from TeX and from ImGui, the pitfalls, and the future work.
They are orientation and route into the documents below, which carry the
measurements.

- [`docs/status.md`](docs/status.md) — what is true today. Start here.
- [`docs/adoption-plan.md`](docs/adoption-plan.md) — the plan to embed this in
  another application, what was built against each phase, and, first, what
  changed and what nobody has looked at.
- [`docs/decisions.md`](docs/decisions.md) — the interpreter, the fonts, the
  two-backend split, the style rules and the scope boundaries, each with the
  constraint that forced it. **Read the CORRECTION at the top first**; it is
  newer than most of the file and withdraws a premise several tasks were built
  on.
- [`docs/imgui-risks.md`](docs/imgui-risks.md) — the list for the first person
  with a display, in the order worth working through.
- [`docs/litmus.md`](docs/litmus.md) — the two litmus tests, what the artifacts
  show, and the defects.
- [`docs/tex-notes.md`](docs/tex-notes.md) — a transcription of the relevant
  parts of Knuth's `tex.web`. **Read its CORRECTIONS section before implementing
  from any section below it**; five transcriptions there are wrong and the
  section says which.

- [`docs/subpixel.md`](docs/subpixel.md) — why the text looked crowded, what
  the field does about it, the four options rejected and the one taken.

Out of scope on purpose: hyphenation, extensible glyph assembly, delta nodes,
TeX's page builder, bidi, complex shaping, CJK line breaking, and a LaTeX
parser (the `$...$` subset is an extension above the engine and refuses what
it does not know; matrices are left out for now).
`docs/decisions.md` says why for each. They are decisions, not omissions — but
two of them now have a price somebody has looked at. Hyphenation's is measured
and stated in `docs/status.md`, and a human has since said the loose lines it
costs are not acceptable. And "page breaking" is narrower than it was:
`\vsplit`, `vert_break` and `prune_page_top` are implemented in
`advtext/columns.py`, which is what the Columns tab flows through; what remains
out is the page builder proper — `\output`, insertions, marks and a page cost
function.

# advtext

Markdown, streams and diffs as selectable text in a Dear ImGui pane. The text
is set and drawn by a sibling library, `../imtypeset`, a typesetter on TeX's
model: a document is **boxes**, **glue**, **kerns** and **penalties**, broken
into lines over badness and demerits, with every glyph at a position the
typesetter worked out. advtext is what stands in front of it: a markdown
reader, a reader for markdown that is still arriving, a diff model, themes and
palettes as data, find, and three views a host calls `draw()` on.

Owning every glyph position is the point. ImGui text is not selectable because
the widget owns the layout; once a typesetter owns it, hit testing is
arithmetic over numbers already computed.

**Until 2026-10-11 that typesetter was advtext's own, in Python**, and this
file opened by describing it. On the branch this file is on, it is deleted
except for what the SVG renderer imports. The dated paragraphs below were
written while it was the product and are left as they were.

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

**On the branch `experimental/imtypeset-adoption` (2026-10-10) there is a
fifteenth page and a second way to draw a document**, through the sibling
library `../imtypeset`, off unless asked for. [`docs/status.md`](docs/status.md)
section 0c is its account. Agents built it unattended; no person has looked at
it in a window, and its review was by reading only.

**On 2026-10-11, on that branch, the swap was carried through: advtext draws
through imtypeset and through nothing else.** The user asked for "a full swap
out using as much as it can from imtypeset"; a team of agents did the rest
unattended, in a day. The old views, the old ImGui draw backend, five modules
of the layout core, the Blocks page, the bench and verify scripts and their
tests are deleted: 46 files and 48,788 lines against `main`. Without the
library every page draws one line saying so. What is left of the Python core
is the 17 modules `make svg` needs, kept until the user says whether the SVG
renderer stays. [`docs/status.md`](docs/status.md) section 0d is the account;
[`docs/decisions.md`](docs/decisions.md), "The swap", keeps the user's five
sentences apart from every agent's decision. **Nothing is committed. No
person has looked at any page in a window. Every review was by reading.**
Everything below this paragraph was brought level with that tree by the last
task's builder, an agent; the paragraphs above it are records.

## Thirty seconds

    make typeset-lib IMTYPESET_COMMIT=7a7bc36   # once: build the library the text is set by
    make run TYPESET=1      # the ImGui demo: a sidebar of fourteen pages
    make shot TYPESET=1     # one page of it as a PNG, without watching a window open
    make check TYPESET=1    # ruff + black --check, mypy --strict, pytest with the library
    make check              # the same without it: green, and the tests that need it skip
    make svg                # the reference layout with no GPU, no display and no ImGui
    make help               # every target, and which interpreter it will use

**`TYPESET=1` is not optional if you want to see text.** `make typeset-lib`
needs the sibling checkouts `../imtypeset` and `../imgui_bundle` and builds
into `build/imtypeset-bundle/`; `7a7bc36` is the commit this tree was built
and tested against (`docs/status.md` section 0d says where the other team
names it, and that they now name a later one). Without `TYPESET=1` the demo
opens and every page is one line: `imtypeset is not drawing: ` and the reason.

`make shot` is the one to reach for when you want to *see* something and cannot
sit in front of a window — it drives the real app through the real `immapp.run`,
counts frames, and grabs the framebuffer:

    make shot TYPESET=1 ARGS="--tab columns:3 --width 1400 --out artifacts/columns-3.png"
    make shot-all TYPESET=1   # every page in each state it names for itself: 25 PNGs

It needs a display and numpy. `make shot-headless` is the Xvfb fallback for a
machine with neither. With the library asked for and not drawing when the
window closes (refused at import, no fonts, a failure mid-run) a shot exits 3
and writes no PNG, so a photograph of the one line cannot be filed under a
page's name.

`make svg` is the one thing here that does not go through imtypeset. It runs
advtext's own Python layout core, which is kept for it and called the
reference core, and writes five files into `artifacts/` (gitignored — they
are outputs; the script that makes them is what is version-controlled):

| file | what it shows |
|---|---|
| `markdown.svg` | the sample document, every glyph a real outline |
| `markdown-debug.svg` | the same, with line boxes, baselines and glue overlaid |
| `selection.svg` | a multi-line drag, highlighted by `advtext.selection` |
| `sigma.svg` | the display-size summation |
| `sigma-compare.svg` | display against text style, to show the operator is a *different glyph* |

Open `markdown-debug.svg` first. It is the one that shows the machinery.

## Embedding it

`advtext` itself is an import surface (`advtext.__all__`, 89 names since
2026-10-11 and 94 before, resolved lazily: `import advtext` loads neither
ImGui nor fontTools nor imtypeset), and four examples use nothing else of the
package except the module `advtext.typesetter`:

    python examples/typeset_minimal.py   # a markdown string in a plain ImGui window
    python examples/stream_replay.py     # demo/stream.md arriving in pieces
    python examples/chat_transcript.py   # finished messages and one streaming
    python examples/diff_minimal.py      # a diff from before/after text; --side-by-side, --edits

Each needs `IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` in the environment (what
`make ... TYPESET=1` sets; `build/imtypeset-bundle/libimtypeset_bundle.so` and
`build/imtypeset-bundle/pysnap`). Without them an example says why on
standard error and exits 1 before any window opens. Each takes `--frames N`
to draw N frames and exit, which is how the tests run them. What a host
calls, in the order it calls it:

| step | names |
|---|---|
| the library | `load_fonts()` at the end of hello_imgui's `load_additional_fonts`, never in `post_init`; `ready()`, `reason()`; `advtext.typesetter.unload()` before the ImGui context goes |
| font files | `register_font` for a host's own file under a role (`Face`); the library is handed the same file |
| theme | `Theme.build(faces=, align=)`, `Theme.at_pixel_height`, `Faces`, `Align`, `Spacing`, `BlockKind` |
| a settled document in a pane | `TypesetView(markdown, theme=, palette=)`, then `draw()` inside the host's own window: fills the pane, paints no background, selectable, culled by the library |
| when it cannot draw | `TypesetUnavailable`, from the constructor with no library and from `draw()` when it is not ready or the library failed; the message is the reason. There is nothing else to draw with |
| colour | `Palette`, `DARK_PALETTE`, `Palette.with_roles`; `TypesetView.set_colours` for inks over ranges |
| links, copy, where the mouse is | `TypesetView(on_link=, copy_as=)`, `selected_source`, `under_mouse`, `block_under_mouse` |
| tables | blocks of the library's document: cells wrap, select, copy and are searched; `set_table_columns` to state widths |
| columns | `TypesetView.set_columns(3, height=...)` or `(3, balance=True)` |
| a document that arrives in pieces | `MarkdownStream`, `TypesetStreamView` |
| find | `MarkdownConverter(theme).describe(blocks)` → `Description`; `FindIndex.of`, `Finder`, `Match`; `view.set_marks(finder.marks())`, `view.scroll_to` |
| a diff | `Diff.from_texts`, `Diff.from_edits` (several edits), `Diff.from_unified` (text that arrives as a diff), `UnifiedDiffStream`; `TypesetDiffView`, `DiffLayout`, `DiffPalette` |
| a fenced `diff` drawn as one, or any widget in a block's place | `host_for=TypesetDiffFences(...)` on a view; `HostFor`, `Hosted`, `HostedDiff` |
| `$...$` and `$$` | `TypesetView(markdown, math=True)`: the library sets the formula, and shows what it refuses as its source |

**A host that holds the before and after text must build its diff from them**
(`from_texts`, `from_edits`) and not from a unified string of its own making:
`difflib` over texts with no closing newline writes a removed and an added line
as one physical line, which no parser can take apart. `docs/adoption-plan.md`
has the measurement.

**Eight names mean something else than they did on `main`**: `HostFor`,
`SetLine`, `Hosted`, `DiffLayout`, `SyntaxColour`, `language_for`,
`HostedDiff` and `FindIndex` are the typeset layer's, with other signatures,
and importing one raises nothing. Twenty-one are gone (`BareView`,
`StreamView`, `DiffView`, `StreamDocument`, `draw`, `markdown_math` and the
rest: `docs/status.md` section 0d has the list). Twenty-nine names are on
the surface only because `make svg`'s modules are in the tree
(`build_document`, `compose`, `ship` and so on): they are the reference core
and nothing of theirs reaches a window.

**Nobody has looked at any of the four examples.** Each has been opened in a
real window on Xvfb by its tests, which count vertices, calls and texts. The
dark palette, a stream at reading speed and a diff side by side are all there
to be judged and have not been.

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

**These are tests of the reference core, rendered by `make svg`**, and since
2026-10-11 they are all that core is kept for. What the demo's window shows is
imtypeset's setting of the same kinds of material, which has its own tests in
`../imtypeset` and, here, tests that count what reaches a draw list.

## `make run` needs a display, and the library

The ImGui demo is real and `make run TYPESET=1` launches it: one window,
1300x800 by default, with a sidebar list on the left and the chosen page on
the right. The pages are modules under `advtext/ui/pages/`, found by scanning
the package; adding one edits no list anywhere. To open on a page, or to
photograph every one:

    make run TYPESET=1 ARGS="--tab diff"
    make run TYPESET=1 ARGS="--tab stream:table,done"
    make shot-all TYPESET=1

A name after `--tab` is a page's name in lower case, optionally with option
words of its own after a colon; `python scripts/shot.py --list` prints the 25
requests `make shot-all` photographs.

| group | page (`--tab`) | what it is, in one line |
|---|---|---|
| Typesetting | Document (`document`) | `demo/sample.md`, justified on a page sheet and selectable with the mouse |
| | Columns (`columns:1`..`3`, `balance`) | one document cut into newspaper columns by the library, filled in order or balanced |
| | Specimen (`specimen`) | imtypeset's own specimen section: every face at one size, one face at every size, and the kerning |
| | Formula (`formula`) | imtypeset's own gallery of TeX math-mode rules |
| | Math in text (`math`) | imtypeset's own section of `$...$` and `$$` in running text |
| Embedding | Themes (`themes`) | one document under four palettes, three face sets and any pixel size, optionally split in two |
| | Tables (`tables`) | drag a column edge and the cells re-wrap |
| | Find (`find`) | a search box over a long document: every match marked, next and previous |
| | Inspector (`inspector`) | point at a block: its source, role, lines and rectangle, and a copy menu |
| Streaming | Stream (`stream`) | one source replayed as tokens under both commit policies, with counters |
| | Chat (`chat`) | a canned conversation, no network: streaming replies with code, a diff, a table, math, one selection |
| Diff | Diff (`diff`) | unified, side by side or both, on the diffs a coding agent's host is handed |
| Performance | Stress (`stress`) | 1 to 16 panes at once, finished or streaming, with the per-frame cost |
| Experimental | Typeset (`typeset`) | the sample document with a find box; the first page that drew through imtypeset |

Fourteen pages. The fifteenth, Blocks, showed the old core's boxes and was
deleted on 2026-10-11. **Every page has run in a real window on Xvfb with the
library, in the suite, and no person and no agent has looked at any of them.**

Without a display `scripts/run_demo.py` refuses rather than hanging: it exits
2 at once and prints the `make shot` recipes instead. Without the library it
says so on stderr and opens the window of one-line pages all the same; with
the library asked for and not drawing, it says why when the window closes.

**"There is a display" is a statement about a session, not about a machine.**
From the sandbox these sessions ran in, `DISPLAY=:1` was set and unreachable
(`socket(AF_UNIX)` refused), and every window was on an Xvfb in a user
namespace over TCP with a software rasteriser — `scripts/mouse_probe.py`'s
`xvfb_command` builds that shell, and `tests/conftest.py`'s `window` fixture
uses it. No window of this branch has been opened on a GPU.

**What a test can and cannot say here.** A frame needs no window: a Dear
ImGui context with no backend runs frames, and the library writes vertices
into its draw lists. So the suite counts vertices, reads back texts, counts
the library's calls and compares rectangles, with no display at all; and in a
real window on Xvfb it reads each page's frame for ink that cannot be told
from its ground. It does not see a pixel. Whether a line is well broken, a
table well ruled or a formula well set is not asserted anywhere in this tree.

**What has been exercised with a mouse.** `scripts/mouse_probe.py` runs the
real app in a real GLFW window and posts mouse and key events to ImGui's
input queue over positions read back from the view: a drag in each direction,
a drag across three lines, a double click, a triple click, Ctrl+C read back
from the clipboard, a wheel scroll followed by a drag on a line that had been
below the fold, and a drag that ends on a line beneath the bottom of the
window and is then copied. Eighteen checks, with expectations built from the
texts described to the library and the markdown source:

    IMTYPESET_LIBRARY=... IMTYPESET_PYTHON=... python scripts/mouse_probe.py --xvfb

`tests/test_mouse_probe.py` runs it under `make check TYPESET=1`. **Its
limit, in its own words**: where a character is on screen is asked of the same
library that then hit-tests the click, so a defect the two share is not seen.

**What has not.** The events enter at `ImGuiIO`, not at the X server: no
pointer has been moved on a screen and no physical button pressed, so GLFW's
cursor and button callbacks and a window manager's part in focus and capture
are untested. No person has dragged a selection in this demo and said what it
was like.

The **SVG backend** is not a fallback for any of that. It emits real glyph
outlines through fontTools from the reference core's layout and needs no GPU,
no ImGui and no imtypeset. It is a second, independent setting of the same
markdown, not a picture of what the window shows.

## Interpreter

    make bootstrap  # builds ./.venv and every target picks it up, no edit needed

Until that runs there is no interpreter: every target that needs one stops and
names `make bootstrap`. `make venv-info` says what the others will use.
`pyproject.toml` states genuine dependency floors and is installable normally;
the one that matters is `imgui-bundle>=1.92.900`. The imtypeset library is
built for ONE installed imgui-bundle wheel and checks at import that it is
the one running; a new wheel means `make typeset-lib` again.

This used to say `make` drove a **borrowed** interpreter from a sibling project,
`../pptmstr`. That fallback was removed on 2026-10-06: the sibling is the
application meant to depend on this library, and a build that reaches back into
its consumer cannot be depended on. The sandbox this was first built in reached
only one host, so `pip install` could not run in it, and the borrowed venv was
how the project existed at all; `docs/decisions.md` keeps that history.

## Measuring it

The four scripts this section listed (`bench_reflow.py`, `bench_draw.py`,
`verify_advances.py`, `verify_ascent.py`) measured the old ImGui draw backend
and went with it. They are in `main`. What measures the tree now:

    make check TYPESET=1                      # the suite prints the Stress page's own per-frame figures
    make run TYPESET=1 ARGS="--tab stress"    # the same figures, live
    python scripts/visual_diff.py --help      # compare two shots of a page region by region

No test asserts a time. Every figure in `docs/status.md` section 0d names who
measured it and at what load average, and the comparisons against the old
views there were made while both existed: they cannot be re-run on this
branch.

## Where the reasoning lives

**New here? [`docs/guide/`](docs/guide/README.md)** — five short documents
covering the idea, which parts of TeX are implemented, the rendering decisions
and where they depart from TeX and from ImGui, the pitfalls, and the future work.
They are orientation and route into the documents below, which carry the
measurements.

- [`docs/status.md`](docs/status.md) — what is true today. Start here, at
  section 0d: the swap of 2026-10-11, what was deleted, what remains of the
  old core and why, what was measured and what is open. Section 0c is the day
  before, when the new layer stood beside the old. Sections 1 to 6 describe
  `main`. [`docs/decisions.md`](docs/decisions.md), "The swap" and "imtypeset
  adoption, experimental branch", keep the user's sentences apart from every
  agent's decision.
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
costs are not acceptable. **That list was written about advtext's own core.**
What sets the text now is imtypeset, whose scope is its own tree's to state
(`../imtypeset/docs/`); the list still describes the reference core `make svg`
runs. The column split it used to mention (`\vsplit`, in `advtext/columns.py`)
is deleted here: the Columns page is cut by the library.

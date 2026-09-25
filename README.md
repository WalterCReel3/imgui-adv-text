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

## Thirty seconds

    make run        # the ImGui demo: five tabs, selectable prose, newspaper columns
    make shot       # one tab of it as a PNG, ~2.3s, without watching a window open
    make svg        # the same layout with no GPU, no display and no ImGui
    make check      # ruff + black --check, mypy --strict, pytest
    make help       # every target, and which interpreter it will use

`make shot` is the one to reach for when you want to *see* something and cannot
sit in front of a window — it drives the real app through the real `immapp.run`,
counts frames, and grabs the framebuffer:

    make shot ARGS="--tab columns:3 --width 1400 --out artifacts/columns-3.png"
    make shot-all   # every tab, plus the debug overlay and 1/2/3 columns

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
photographed**. Five tabs:

| tab | what it shows |
|---|---|
| Document | the markdown litmus test, set on a page and selectable with the mouse |
| Columns | the same material flowed into 1, 2 or 3 newspaper columns by `advtext.columns`, text continuing from the foot of one to the head of the next |
| Specimen | the six faces compared side by side, a size ladder, and a kerning demonstration |
| Formula | the sigma in display and text style, so the big operator is visible as a *different glyph* |
| Blocks | `advtext.blocklayout`'s toolbar at three widths |

Without a display it refuses rather than hanging: `scripts/run_demo.py` exits 2
in 0.04s and prints the `make shot` recipes instead. The hang belonged to Xvfb
alone, and `make shot-headless` is where that path lives now.

**What that does and does not leave unverified.** ImGui's context, font atlas and
vertex buffers all run headless — *a window needs a display, a frame does not* —
so glyph rasterisation, advances, the ascent conversion and `draw`'s output are
asserted on with no display at all. Compositing is no longer on the unverified
list. **What is: no mouse click has ever reached a real frame, and this is one
GPU on one machine.** `docs/status.md` section 2 and
[`docs/imgui-risks.md`](docs/imgui-risks.md) draw the line precisely.

The **SVG backend** is not a fallback for that. It emits real glyph outlines
through fontTools and needs no GPU and no ImGui at all, and a layout that two
unrelated backends can render has had its geometry separated from its drawing —
which is the property that made selection tractable.

## Interpreter

    make bootstrap  # builds ./.venv and every target picks it up, no edit needed

Until that runs, `make` drives a **borrowed** interpreter from a sibling project,
read-only. The sandbox this was built in reaches only one host, so `pip install`
could not run in it and the borrowed venv is the reason the project exists at
all. `make venv-info` says which one you are on. `pyproject.toml` states genuine
dependency floors and is installable normally.

## Measuring it

    python scripts/bench_reflow.py     # compose / ship / selection index
    python scripts/bench_draw.py       # the per-frame ImGui draw cost
    python scripts/verify_advances.py  # ImGui's advances against fontTools'
    python scripts/verify_ascent.py    # ImGui's baked ascent against ours

All four run here with no display. Every performance claim in this tree came out
of one of them, and each prints the table its own docstring quotes — so a number
you read in a docstring can be re-derived rather than trusted.

## Where the reasoning lives

- [`docs/status.md`](docs/status.md) — what is true today. Start here.
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
TeX's page builder, bidi, complex shaping and CJK line breaking.
`docs/decisions.md` says why for each. They are decisions, not omissions — but
two of them now have a price somebody has looked at. Hyphenation's is measured
and stated in `docs/status.md`, and a human has since said the loose lines it
costs are not acceptable. And "page breaking" is narrower than it was:
`\vsplit`, `vert_break` and `prune_page_top` are implemented in
`advtext/columns.py`, which is what the Columns tab flows through; what remains
out is the page builder proper — `\output`, insertions, marks and a page cost
function.

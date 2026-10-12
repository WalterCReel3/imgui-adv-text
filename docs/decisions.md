# Decisions

This session runs unattended. Every question that would normally have gone to a
person was settled here, with the reason, so the next reader meets the reasoning
rather than the conclusion alone.

Read this before claiming a task. Where this file and a task's `detail` disagree,
this file is the older document and the task is the newer one — say so on the
board rather than guessing.

---

## What is being built

A text layout and rendering system for Dear ImGui that borrows TeX's model:
a document is a tree of **boxes**, **glue**, **kerns** and **penalties**, packed
by `hpack`/`vpack`, broken into lines by a total-fit algorithm over badness and
demerits, and shipped out as absolute glyph positions.

Two litmus tests, both required:

1. **Multi-type markdown** — headings, paragraphs with bold/italic/code,
   lists, block quotes, fenced code, a rule, a table — laid out as one document
   and **selectable** with the mouse.
2. **A sigma summation formula** — `\sum_{i=1}^{n}` with limits above and below
   a display-size operator, rendered from real math font metrics.

Stretch: the same box/glue machinery applied to UI block layout.

**Selection is the point.** pptmstr records that ImGui text is not selectable
and treats that as a real gap rather than a workaround failing
(`pptmstr/ui/transcript_pane.py:14-16, 26-29`). It is a gap only because the
widget owns the layout. Once we compute every glyph position ourselves, hit
testing is arithmetic we already have the inputs for. That is the return on
doing layout from scratch, and it is why selection is not an afterthought here.

---

## Environment constraints, and what they forced

> ## CORRECTION — "ImGui is unverifiable here" was wrong, and it was my error
>
> Everything in section 1 below about *windows* is true and was verified. The
> conclusion I drew from it — that nothing about the ImGui backend could be
> checked — is **false**, and it shaped several task specifications before a
> builder refused the framing and measured instead.
>
> **A window needs a display; a frame does not.** `create_context()` allocates
> memory, `ImFontAtlas` bakes glyphs on the CPU through stb_truetype, and
> `new_frame`/`render` build vertex buffers in RAM. None of that touches GLFW or
> GL. The no-display finding reaches `immapp.run`, and stops there.
>
> The trap is real and is why the wrong conclusion was plausible: pptmstr's
> `scripts/verify_fonts.py` — the idiom several task details told builders to
> copy — ends in `immapp.run` and **would** have hung. `verify_advances.py` is
> the right idiom.
>
> **Two real defects were found by measuring what I had written off as
> unmeasurable:**
>
> - **The backend asked ImGui for the wrong size.** "Size" means the em to
>   `fontlib` and the pixel height to stb_truetype. Every glyph baked about
>   12.4% too small, drifting 42 px over a 44-character line. Fixed via
>   `baked_size_px`.
> - **The display sigma now draws through ImGui.** `fontlib.imgui_font_file`
>   writes the 227 synthetic variant mappings into a copy of the font's format-12
>   cmap subtables. This only works because `ImWchar` is 32-bit in this build
>   (checked: `is_glyph_in_font(0x12211)` returns False rather than truncating to
>   U+2211 and returning True) and because Latin Modern Math carries format-12
>   subtables, the only format that can hold a plane-15 codepoint. A 16-bit build
>   makes the approach impossible. `add_remap_char` is a dead end — it maps
>   codepoint to codepoint and cannot reach a glyph with no codepoint.
>
> **The advance disagreement is now measured rather than hedged against.** At
> 16px, 26 of 44 glyphs disagree, worst single glyph 0.45 px, accumulating to
> about 6 px across the sample. So the per-glyph positioning decision recorded
> further down this file is vindicated by measurement: handing whole strings to
> `add_text` really would drift.
>
> **The ascent worry was the wrong thing to watch.** `glyph.y0 == baked.ascent -
> ink_top` holds to 1.6 px over 90 boxes, which is pixel quantisation. The
> ascents differ by up to 4.4 px between ImGui and `fontlib`, but that cannot
> displace a line, because `_glyph` subtracts whatever ascent the same baked font
> reports — a larger ascent raises the top-left and lowers `y0` equally. The
> delta was a *symptom* of the size bug, not a risk.
>
> **The surviving claim, stated precisely, because both halves matter:** ImGui
> draw geometry is verified — glyph rasterisation, advances, ascent conversion,
> and vertex-buffer output.
>
> **`advtext/ui/document_view.py` runs under the suite** — traced call by call.
> Only `DocumentView.draw` and the mouse handlers are unreached, so the module
> named in several task details as never-executed is not. Only
> `advtext/ui/app.py` and `scripts/run_demo.py` are genuinely untouched by tests.
> *(Both sentences have since moved again: `DocumentView.draw` and the mouse
> handlers are covered now, and so is `scripts/run_demo.py`. See the SECOND
> CORRECTION below and `docs/status.md` section 2 for the current trace.)*
>
> Compositing is a separate question from execution, and the honest answer moved
> once: the demo has now been run on a machine with a display, which is what
> found the two defects below that nothing here could reach — an `ImGuiIO`
> ndarray field that needs numpy and raises only on the first *click*, and dark
> ink drawn with no page behind it, which on ImGui's dark theme is invisible
> text rather than an error. Neither was reachable from any test in this tree at
> the time, and both are now guarded.
>
> `docs/litmus.md` and the `status-gate` task's own detail still assert the old,
> wrong version — that nothing has been rendered by ImGui and that the advance
> disagreement is unmeasured. **Both must be corrected rather than propagated.**

> ## SECOND CORRECTION — section 1's heading is false on this machine, and §5 was aspirational
>
> Later than the correction above, and narrower. Four things, each measured.
>
> **1. "GUI rendering is BLOCKED" is a fact about a sandbox, not about this
> repository.** On this machine `DISPLAY=:1` is live — X.Org 1.22.1.9, direct
> rendering on an AMD Radeon (renoir) through Mesa 22.3.6, so real hardware and
> not a software rasteriser. A window opens in about half a second, `make shot`
> photographs any tab in 2.3-3.8s, and all five tabs have been looked at.
> Section 1 below is kept as written because its two failures were real where
> they were observed and the reasoning they forced — *no code on the critical
> path may require ImGui to compute a layout* — is still the right architecture
> for an unrelated reason. **But its instruction to label anything that draws as
> unverified no longer applies.** `docs/status.md` section 2 has the
> per-function trace of what has and has not run: **every function in this tree
> has now been executed**, by the suite or by a real window or by both, and the
> only call the suite does not make is `advtext.ui.app.run` itself — deliberately,
> because `tests/conftest.py` forbids this suite from opening a window. What is
> left unverified is input: no mouse click has ever reached a real frame.
>
> *(2026-10-07: that last sentence stopped being true on 2026-10-06.
> `scripts/mouse_probe.py` posts mouse and key events into the real app in a
> real window and its eighteen checks pass. And "on this machine `DISPLAY=:1`
> is live" turned out, once more, to be a fact about a session: the agents'
> sandbox that day could not reach it and used an Xvfb in a user namespace.
> See the THIRD CORRECTION at "Adoption" below, and `docs/adoption-plan.md`
> section B.)*
>
> **2. Xvfb is no longer the fallback of record.** `make shot` is; `make
> shot-headless` keeps the Xvfb path because it is still right on a machine with
> no display. The `XVFB_RUN` block several documents told you to uncomment does
> not exist any more.
>
> **3. §5's "rounding to the pixel grid happens exactly once" was a rule nobody
> implemented.** `advtext.shipout.ship` takes no `px_per_inch` and rounded
> **zero** times; ImGui then truncated the pen position once, inside itself,
> where our layout could not see it. The sentence is true now — `snap_px` in
> `advtext.backends.imgui_draw` rounds each absolute coordinate once, at draw
> time — and `docs/subpixel.md` §5.3 is the argument for why it must be the
> absolute position and never an advance: rounding advances and summing them
> walks a line up to 9.9 px off the margin that `tests/test_litmus.py` asserts is
> exact. That is TeX's `dvi_h:=cur_h` (§616, `tex.web` line 12276) restated for a
> raster device.
>
> **4. The scope boundary below moved, and only partly.** "No `vsplit` and no
> page cost function" is half wrong: `advtext/columns.py` implements §970-§976
> `vert_break`, §968-§969 `prune_page_top` and §977 `vsplit`. TeX's page builder
> — §980, the part titled "The page builder", with `\output`, insertions, marks
> and §1005's page cost — is still out, and so is column balancing.
>
> Every section number in this block was verified against `docs/tex.web` by
> content, not taken from `docs/tex-notes.md`, which warns that its own numbers
> were only spot-checked. Counting `@*` / `@ ` / bare `@` starts: §616 is the
> `synch_h` macro at line 12276; §968 opens "A subroutine called |prune_page_top|"
> at 18857; §970 opens "The next subroutine finds the best place to break a given
> vertical list" at 18896; §977 opens "Now we are ready to consider |vsplit|" at
> 19032; §980 is `@* \[45] The page builder.` at 19105.

### 1. No display, and no X server can be started — GUI rendering is BLOCKED

Two independent failures, both verified this session:

- The host display is unreachable from the sandbox:
  `Glfw Error 65550: X11: Failed to open display :1`, then
  `IM_ASSERT( glfwInitSuccess )` at `runner_glfw3.cpp:67`.
- `Xvfb` cannot start, because it creates its lock file in `/tmp` and the
  sandbox write allowlist covers `/tmp/claude` and `$TMPDIR` but not `/tmp`:
  `(EE) Fatal server error: Could not create lock file in /tmp/.tX77-lock`.

pptmstr's headless recipe (`Makefile:6-24`, `xvfb-run -a --server-args=-screen 0
1600x1000x24`) is correct and is the right thing to copy, but it cannot run
**in this session**. It hangs rather than failing, which is worth knowing:
`timeout` reports 143, not an error message.

**Consequence, and it is the central architectural decision:** no code on the
critical path may require ImGui to compute a layout. See "Two backends" below.

**What is therefore unverified and must be labelled as such in every report:**
anything that draws. The ImGui backend and the demo app will be written and
statically checked, and they will not have been run. Do not claim otherwise.

### 2. No network — the interpreter is borrowed, not built

> **Superseded 2026-10-06. History from here to the end of this section.**
> There is no borrowed interpreter. The project has its own `.venv`
> (`make bootstrap`), the `Makefile`'s fallback to pptmstr's was removed along
> with the one in `scripts/shot.sh`, and with no `.venv` a target stops and says
> so. The reason is the adoption goal: pptmstr is to depend on this library, and
> a build that reaches back into its consumer cannot be depended on. The `PY :=`
> line below no longer exists. The installed versions are now imgui-bundle
> 1.92.900, markdown-it-py 4.2.0, fontTools 4.66.0; the floor in
> `pyproject.toml` is `imgui-bundle>=1.92.900`. What is **not** superseded is the
> last paragraph: never write under `../pptmstr`.

Only `api.anthropic.com` is reachable, so `pip install` cannot run and a
virtualenv cannot be created. We use pptmstr's, read-only:

    PY := /home/wreel/Source/pptmstr/.venv/bin/python

Verified present there: Python 3.11.2, imgui-bundle 1.92.801 (Dear ImGui 1.92.8),
markdown-it-py 4.2.0, fontTools 4.63.0, pytest 9.1.1, black, mypy, ruff.

This is a borrowed interpreter and not a dependency declaration.
`pyproject.toml` states real floors so the project is installable normally
later; the `Makefile` variable is the seam to change when it is.

**Never write to anything under `/home/wreel/Source/pptmstr`.** It is a separate
project with uncommitted changes in its working tree. It is a reference and a
source of an interpreter, nothing else.

### 3. Fonts come from the bundle's assets — nothing is downloaded

All under
`/home/wreel/Source/pptmstr/.venv/lib/python3.11/site-packages/imgui_bundle/assets/fonts/`:

| Role | File | Why |
|---|---|---|
| Prose | `Roboto/Roboto-{Regular,Bold,RegularItalic,BoldItalic}.ttf` | Four real faces. pptmstr's Inconsolata has no italic upstream and forces emphasis to be a colour shift (`pptmstr/ui/theme.py:791-802`); a typography demo needs a true italic. |
| Math | `latex/latinmodern-math.otf` | See below. |
| Code | `Inconsolata-Medium.ttf` | Monospace, already vendored. |

**Latin Modern Math carries a real OpenType `MATH` table.** Verified with
fontTools: `unitsPerEm` 1000, `AxisHeight` 250, `ScriptPercentScaleDown` 70,
`ScriptScriptPercentScaleDown` 50, `FractionRuleThickness` 40, and 94 vertical
glyph constructions.

This matters more than anything else in this file. `docs/tex-notes.md` §8
describes `make_op` selecting a display-size operator by following a `list_tag`
successor chain, and §10 flags that an ordinary TrueType font has no such data,
so the parameters would have to be synthesised from fractions of the em. **That
caveat does not apply to us.** The chain is present and populated:

    U+2211 → variants: [('summation', 1001), ('summation.v1', 1401)]

So the display-style big sigma is a real larger glyph selected from real font
data, exactly as §749 describes, rather than the body glyph scaled up. The
litmus test is the honest version of itself. The OpenType `MATH` table is the
modern spelling of TeX's sigma/xi `\fontdimen` params — `MathConstants` maps
onto them nearly one-for-one — so §10's parameter list is a *lookup key list*
here, not a list of things to invent.

### 4. Metrics come from fontTools, not from ImGui

Forced by #1 — `imgui.calc_text_size` needs a live context — but correct
independently:

- TeX packs in scaled points and rounds once, at ship-out (`docs/tex-notes.md`
  §2, the `vet_glue` discussion). ImGui's baked advances are already
  pixel-rounded, so measuring through ImGui rounds twice and the error
  accumulates along a line.
- Kerning lives in the font's `GPOS`, which fontTools reads and ImGui does not
  expose at all.
- `MATH` is unavailable through ImGui by any route.

**Known risk, unverified, and it must stay labelled that way:** ImGui's
`add_text` advances a string using ImGui's own per-glyph advances, which may
disagree with the ones we lay out with. The ImGui backend therefore positions
**one glyph at a time** at our computed x rather than handing whole strings to
`add_text`. That is slower and it is the only way the two agree by construction.
A verify script must measure the disagreement when a display exists; until it
runs, the per-glyph decision is a hedge and not a measurement.

### 5. Device coordinates are pixels; the layout core works in scaled points

Settled after the `nodes` task raised it, because it is a seam that would be wrong by
exactly 1.33× and nothing in the tree recorded which side was which.

The layout core carries dimensions as **integer scaled points** (2^-16 pt), faithfully to
TeX, which is what makes its rounding reproducible. Device space — what both backends
consume — is **pixels**, with `px_per_inch = 96.0` as an explicit parameter rather than a
module global.

A **font size given as "16" means 16 device pixels**, not 16 points. That matches ImGui's
own convention, where a pushed font size is in pixels, and it is the number a reader will
recognise from the demo. At 96 px/inch it is 12.045 pt internally.

Consequences worth stating, because they are the parts that go quietly wrong:

- `pt` and `bp` are not the same unit (72.27 vs 72 per inch). TeX's `pt` is the one the
  layout uses.
- Rounding to the pixel grid happens **exactly once**, on a final absolute coordinate,
  never on a width. Rounding widths accumulates error along a line.
- That pixel rounding is **not** the same operation as §625's glue rounding, which is
  sp→sp inside the layout core and must be Pascal's half-away-from-zero. See correction
  C3 at the top of `docs/tex-notes.md`.

96 px/inch is an assumption about a display nothing in this session can observe. If the
ImGui backend turns out to treat its coordinates as points, this is the seam that is
wrong, and it will be wrong by 1.33× — large enough to see immediately, which is the one
mercy.

---

## Two backends, one layout

The layout core imports **no ImGui and no fontTools**. It consumes a metrics
interface and produces a box tree; ship-out flattens that to absolute-positioned
draw commands. Two backends consume those commands:

- **SVG** (`advtext/backends/svg.py`) — emits real glyph outlines via
  fontTools' `SVGPathPen`. Verified working this session. It needs no GPU, no
  display and no ImGui, so it is how the litmus tests are *shown* to have
  worked, and it doubles as a golden-artifact format.
- **ImDrawList** (`advtext/backends/imgui_draw.py`) — the real target. Written,
  statically checked, **not run**.

The SVG backend is not a toy or a fallback. A layout that can be rendered by two
unrelated backends has had its geometry separated from its drawing, which is the
property that made selection tractable in the first place.

This follows the split pptmstr already validated — `span_layout.py` is pure and
takes injected measure functions, `rich_pane.py` is the only module that touches
ImGui — and pushes it further: there, ImGui was injected into layout; here,
layout does not know ImGui exists.

---

## Contracts between modules

Things one task settled that another task must honour. They are here rather than in a
module docstring because the task that needs them is not the task that owns the file.

### `ship()` requires the same metrics the packing used

`advtext.shipout.ship` must be handed the **same** measure the packing pass used. A
`CharNode` carries no dimensions — faithfully to TeX's one-word char node — so ship-out
re-asks the metrics layer for every advance. Pack with one metrics implementation and ship
with another and the glyph positions silently disagree with the box widths.

This is documented and **unenforced**. Nothing raises. If it is ever violated the symptom
is text that overflows its box by a little, everywhere, with no error.

### `selection.text()` takes an explicit `hard_breaks` set

Serialising a selection has to distinguish a line break the *layout* introduced from one
the *source* contained: a wrapped paragraph is one logical paragraph and must copy as
running text, while a newline inside a fenced code block is real and must survive.

Nothing in the draw-command stream distinguishes them, so the **caller supplies the set**.
Whoever renders a document — `litmus`, and the ImGui `document_view` — must pass it.
Omit it and the sample document's code block copies as one long line, which is precisely
the failure `docs/decisions.md` says this project exists to beat.

*(2026-10-07.)* `document_view` never did pass it: Ctrl+C in the demo copied a code
block as one line, exactly as this section warns, until a failing test showed it. The
contract was the weak point, so the views no longer rely on it. `text()` keeps the
`hard_breaks` argument and its flat meaning, and gained `separators`, a mapping from a
boundary to the string that belongs before it, which can say "blank line" where a set
cannot. A view calls `UnitModel.copy_text`, which builds that mapping from the blocks
it laid out. A caller of `selection.text()` directly still supplies its own.

### Only `fontlib` may import fontTools — restored

The `metrics` task declared fontTools exclusive to `advtext/fontlib.py`, so that the layout
core is testable against a fake and font access lives in one place.

It was violated for a while: `advtext/backends/svg.py` opened font files itself, because
`fontlib` exposed no glyph set and no `unitsPerEm` and the backend needs outlines. That is
fixed. `fontlib.glyph_set(face)` returns both, `svg.py` parses nothing, and its only
remaining fontTools reference is a local `SVGPathPen` import — a pen is a drawing tool, not
font access, and it holds no file.

The fix had to be the accessor. Making the duplicated parse merely *cheaper* would have
left two modules opening fonts, which is the thing the contract exists to prevent.

### The leaked font descriptors cannot be pinned by "the suite emits no ResourceWarning"

The descriptors are really leaked — `_face_data` builds `TTFont(path, lazy=True)` with no
close and no finalizer, and an in-process run ends with the cache holding open faces.

But an earlier version of this file, and the `fontlib-followup` task detail, argued that
one of these surfacing mid-test would become a failure against an unrelated test under
`filterwarnings = ["error"]`. **That argument is wrong and was refuted by checking it.**
The warning is emitted from `_io.BufferedReader.__del__`, and CPython swallows exceptions
raised in finalizers — they print as `Exception ignored in:` and never fail a test. Plain
`pytest`, `PYTHONWARNINGS=always::ResourceWarning` and `python -X dev -m pytest` all give a
clean, silent run.

The consequence is what matters: **a regression test phrased as "the suite raises no
ResourceWarning" passes identically with and without the fix.** It would look like
protection and be a no-op. The fix is still right, because a descriptor held for process
life is a real defect; it has to be pinned by asserting the file object is closed.

### The math API is built by hand, and `fonts.measure` is the one to use

The formula is constructed, not parsed — a LaTeX parser is out of scope. The shape, from
the task that wrote it:

    fonts = math_fonts(sp_from_px(32.0), lambda s: fontlib.math_metrics(float(s)))
    formula = [op("∑", sup="n", sub=group("i", rel("="), "1"))]
    nodes = mlist_to_hlist(formula, Style.DISPLAY, fonts)
    box = hpack(nodes, measure=fonts.measure).box

**`fonts.measure` is the `CharMeasure` that `hpack` needs. Do not build another one.** It
is memoised and it is the only place float metrics become scaled points.

`hpack` returns a `PackResult`, not a `Box`; `break_paragraph` returns a `Paragraph`, not
a `list[Box]`. Both differ from the earlier task specs.

### Where to look when the rendered formula is subtly wrong

Two places carry known, untestable-in-numbers risk:

- **`_rebox` (§715)**, which re-centres the operator and its limits to a common width.
  If the limits sit very slightly off-centre under the sigma, look there and **not** at
  the limit-stacking code.
- **Four spacing values are `plain.tex`'s, not `tex.web`'s** — `\thinmuskip` 3mu,
  `\medmuskip` 4mu plus 2mu minus 4mu, `\thickmuskip` 5mu plus 5mu, `\scriptspace` 0.5pt.
  `tex.web` defines the parameters and leaves them zero, so these are the numbers a reader
  would actually recognise the output of. If a formula looks airy or tight, move these;
  they are in one place.

### A glyph draw command carries no colour and no size

Colour belongs to the backend and is decided by `style.py`. A `FontKey` *is* a face at a
size, so a separate `size` field would let one command name two different sizes. Both were
in an earlier draft of the `shipout` spec and both were correctly refused.

*(2026-10-07: still true, and it held under pressure.)* Ink per block role, per-run
colour for syntax and search hits, and link colour were all added without a field on
`Glyph`. Colour travels beside the commands: a view hands the backend runs of commands
with an ink each, and ranges of reading-order indices with a colour each
(`advtext.backends.imgui_draw.draw_runs`), and `advtext/spans.py` is what turns a
position in a block's material into those indices.

---

## What a frame actually costs, and where the lead's profile was wrong

The lead profiled `compose` / `ship` / `SelectionModel.from_commands` and boarded
the reflow work from those numbers. That profile was **incomplete in the way that
mattered**: it never timed the ImGui `draw` call, because it was taken while
"ImGui is unverifiable here" was still believed. See the CORRECTION at the top.

**`draw` costs about 30 ms per frame** on the sample document with the layout
fully cached and nothing recomputed — over a 16 ms budget on its own, every
frame, not only on resize. Culling ship-out and the selection index would have
saved 6.5 ms on a width change and **nothing at all on any other frame**.

Culling the draw call instead makes a frame a function of the window rather than
of the document: 5,378 commands 30.3 → 10.5 ms; 21,512 commands 114.5 → 10.4 ms.
Flat as the file grows, which is the property worth having.

(This decision was first recorded as `21 ms`, `4,226 commands 20.7 → 9.4` and
`16,904 commands 82.1 → 9.3`. The figures above are the same measurement re-run
after `demo/sample.md` grew from 23 blocks to 37; the *decision* is unchanged and
the flatness is if anything more pronounced. `tests/test_bench_numbers.py` now
re-derives the command counts, so the next such drift is a red test.)

The circularity warning in the `viewport-culling` task — that you cannot know a
block's height without breaking it — is true of *breaking* and does not reach
*drawing*. By the time a command list exists every coordinate is absolute.

**Three further corrections from measurement, recorded so they are not
re-derived:**

- **Per-paragraph cost is strongly superlinear.** One paragraph of
  `demo/sample.md` is 38% of the whole reflow: 635 nodes cost 26-32 ms where 427
  cost 11 ms. "23 blocks at ~4 ms each" is a misleading model, and it raises what
  delta nodes are worth rather than lowering it.
- **The per-block cache does nothing for a resize drag** — zero hits across
  consecutive 1 pt widths, measured and pinned by a test so the cache is never
  mistaken for a resize fix. It earns its place on a *partly changed* document:
  `DocumentView.layout_for` drops the whole layout on `invalidate()`, so editing
  one paragraph used to re-break all of them. With the cache that is 220 hits to
  33 misses, ~85 ms down to ~30 ms.
- **A `RuleBlock` does depend on the width** (`_rule_box` draws to
  `width - left_indent`). A task detail claimed otherwise. Only the code block is
  width-independent, and it is worth 0.11 ms of 84 ms.

**Method worth repeating:** the cache key was validated by dropping each of its
five components and re-running. The first attempt showed **three of the five
tests were vacuous** — a fresh `char_measure` closure per call was silently
discriminating every key, so the tests passed no matter what the key contained.
That is the third family of can't-fail tests found in this project, and the only
one found by the builder who wrote it rather than by a reviewer.

---

## Shape of the code

Style follows pptmstr's `CLAUDE.md` and `STYLE.md`, which were read this
session. Load-bearing points:

- `from __future__ import annotations` in every module; full annotations
  including `-> None`; PEP 604 unions and builtin generics.
- Frozen slotted dataclasses for values, plain dataclasses for mutable state,
  `enum.Enum` for closed sets, `match` + `assert_never` for tagged unions.
- **Docstring triple quotes on their own line.** Personal style rule, stated in
  `CLAUDE.md`, no exceptions in the tree.
- Module docstrings are design essays naming what is deliberately out of scope.
- Comments state live constraints, never history. No defect archaeology.
- Test names are claims:
  `test_badness_returns_inf_bad_when_there_is_no_stretch`, not `test_badness_2`.
- black (line length 100) owns formatting; ruff is lint-only, `E,F,I,UP,B`;
  mypy strict.
- **No `Co-Authored-By` trailers and no tool attribution**, per `CLAUDE.md`.

---

## Scope boundaries, decided rather than discovered

Out, with reasons, so nobody spends a task on them:

- **Hyphenation.** `docs/tex-notes.md` flags the full implementation as a trap —
  roughly 1000 lines, with the worst interaction in TeX (ligature
  reconstruction, §915-916). Line breaking runs its first and emergency passes
  and skips the hyphenation pass. Say so where it would otherwise look like a
  bug.
- **`ext_tag` extensible assembly** (building an arbitrarily tall glyph from
  pieces). Not needed: the summation variant chain gives a real display glyph,
  and TeX's own sanctioned fallback is to take the largest available variant.
  *(2026-10-07: still out, and it now has a visible edge. Sized delimiters and
  radicals exist and choose among ready-made outlines; a `\left` pair takes
  the largest when it covers 75% of what TeX's rule asks, the lead's number,
  and a formula is refused below that.)*
- **Delta nodes in `try_break`.** A 1982 performance optimisation where the
  subtle bugs live. Recompute `active_width` by re-walking; at paragraph sizes
  the difference is free. This was the researching agent's recommendation rather
  than Knuth's, and it is adopted deliberately.
- **`\mathchoice`, `\halign`, full ligature reconstruction, TeX's page builder.**
  This entry used to read "page breaking ... no `vsplit` and no page cost
  function" and the SECOND CORRECTION at the top narrows it: `advtext/columns.py`
  implements `vert_break`, `prune_page_top` and `vsplit`, so a vertical list can
  be cut at a legal break. What is still out is §1005-§1010 — no `\output`
  routine, no insertions, no marks, no page cost function — and column
  balancing, which `columns.py`'s docstring prices at a few milliseconds and
  records as dropped for scope rather than for cost. The interline-glue rule
  (`docs/tex-notes.md` §6, `append_to_vlist`, §679) **is** in scope — it is what
  makes vertical rhythm look right.
- **Bidi, complex shaping, CJK line breaking.** Left-to-right only.

---

## Adoption: the goal, and the one decision here that it reverses

Added 2026-10-06. Everything above was written while this project was a
typography demo with no consumer. It has one now, and that changes what two
statements in this tree mean.

**The goal is full adoption: advtext replaces pptmstr's text rendering.** That
is the user's decision, not an agent's, and `docs/adoption-plan.md` records the
ground it was taken on — the typography is the point. The plan also records
that an earlier draft concluded only narrow adoption was justified, and that
the conclusion was rejected: it valued kerning, total-fit breaking and
proportional faces at nothing because pptmstr sets ragged Inconsolata today,
which assumes the answer in order to reach it. Do not re-derive it. The gaps
between this library and that host are a work list.

Three things follow, and they are stated here so a later reader does not take
the older sections above as still bounding the work:

- **The demo stays what it is.** Justified Roboto on a page sheet is the demo's
  presentation and the headline claim (`.concerns/lead--user-decisions.md`:
  justification "was the point", ragged is additive). What adoption needs — a
  host's faces and size, ragged setting, a view with no page sheet, colour,
  links, streaming — is added beside it, not swapped in for it.
- **The pptmstr-side changes are out of scope here**, and "never write to
  anything under `/home/wreel/Source/pptmstr`" above still holds without
  exception. The plan's milestones describe what pptmstr would do; nothing in
  this tree does it.
- **No LaTeX parser.** Unchanged by adoption, for the reason already recorded:
  a parser becomes the thing being demonstrated instead of the typesetting.
  *(2026-10-07, second build: still none in the engine. By the user's later
  decision a `$...$` subset is read by an extension above it,
  `advtext/mathtext.py`; see "Second build" below.)*

### Reversed: "a streaming segmenter is the wrong answer to ours"

`advtext/markdown.py`'s module docstring said, of pptmstr's hand-written block
segmenter: *"A streaming segmenter is the right answer to that problem and the
wrong one to ours: we are handed a whole file."* It was a reason for not copying
pptmstr's cursor machinery, and for a program that opens a file it was a good
one.

**It is withdrawn as a statement about the project, and kept as a statement
about one function.** A host whose text arrives from a model a few characters
at a time is not handed a whole file, and that host is now the goal. So:

- `build_document` still takes a complete source and is still not incremental.
  That remains true and is not a defect; the docstring now says exactly that
  and no more.
- A streaming document — committed blocks that are never revised, and a live
  tail that is re-parsed — is to be built **beside** it, deciding which
  top-level blocks are settled and handing their source to the same converter.
  The plan's phase 7 names `advtext/stream.py` for it. **That module did not
  exist when this entry was written**; this records the decision to build it,
  not that it works. *(2026-10-07: it exists. `StreamDocument` is compared with
  one whole parse after every appended piece over 51 adversarial sources, five
  ways of cutting them and both commit policies, `tests/test_stream.py`. That
  is evidence that it agrees with `build_document`, and nobody has watched a
  stream. See the next section.)*
- What is *not* reversed is the refusal to copy pptmstr's parser. The commit
  boundary is to come from markdown-it's own block tokens, not from a second
  hand-written scanner for blank lines and fences: the plan's example is a
  numbered item followed by an indented fence, which parses on its own as a
  paragraph or indented code. That claim is the plan's and is read-derived;
  phase 7's property test is what would confirm it. *(Confirmed, with an
  amendment the plan did not have: the boundary must be decided on complete
  lines only. `para\n#` parses as a paragraph and an empty heading, and
  `para\n#tag` as one paragraph.)*

Why this is recorded rather than simply done: the docstring was the only place
the original decision lived, and a decision that exists only in a docstring is
reversed silently by whoever edits the file next. Phase 0 of the plan asks for
the revision before anything is built past it, and this is that.

---

## Agent decisions taken while the plan was built — awaiting the user

Added 2026-10-07 by the agent that closed the adoption session.

**None of these is the user's.** The session that implemented
`docs/adoption-plan.md` ran unattended: a lead agent, builders, and a reviewer
with no shell. Where the plan was silent the lead decided, and where a builder
met something the lead had not foreseen the builder decided and the lead
accepted or amended it. The user's standing instruction is that decisions from
autonomous mode are to be "treated as light": read every row below as a
description of what is currently implemented and why, **not as a boundary**.
Each says how it is undone. The numbers are the lead's
(`.concerns/lead--adoption-tasks.md`, which is not version-controlled).

The user's own decisions that bound this work, for contrast, were three: full
adoption is the goal; justification stays the headline and ragged is additive;
no LaTeX parser.

### THIRD CORRECTION: "no window can open" was the lead's, and wrong

The lead opened the session by measuring that `DISPLAY=:1` was unreachable from
its sandbox and told every task that no window could open. That is the fourth
belief this file records about displays. A builder told to work around it
found that `unshare -rm`, a tmpfs over `/tmp`, and `Xvfb -listen tcp -nolisten
unix` give a server on `127.0.0.1`, and that the real app opens on it under
llvmpipe. Every "blocked on display" in a task then meant "run it that way".
The lesson is the old one: it was a fact about one route to a display.

### Decisions that held

| # | decision | reason given | undo |
|---|---|---|---|
| 1 | The build uses its own `.venv` only; no fallback to `../pptmstr/.venv` | pptmstr cannot depend on a project whose build reaches back into pptmstr | restore the `BORROWED` lines in the `Makefile` and `scripts/shot.sh` |
| 2 | `imgui-bundle>=1.92.900`, and no upper bound | first release with the flag the backend sets, by changelog; verified present in the installed one. A cap on a rumoured 1.93 rename would block a release that may be fine | `pyproject.toml` |
| 4 | `demo/sample.md` is not edited; the construct phase 7 needs is in a new `demo/stream.md` | the benchmarks and `tests/test_demo_content.py` are pinned to the sample | n/a |
| 5 | The demos are `examples/*.py`, not new tabs of the app | the tab list is pinned by tests; and an example that does not import `advtext.ui.app` is itself the proof of the embed surface | n/a |
| 6 | Re-set on commit is a flag: `CommitPolicy.KEEP_STREAMED` (default) and `RESET` | the plan asked for a flag. KEEP is the default because it moves nothing, which is a statement about change and not about which looks better | pass the other policy |
| 7 | While a table is live each column is held at the widest *natural* cell it has had; at commit `RESET` apportions normally and `KEEP_STREAMED` keeps the held widths, measured once more at the commit | the lead's first rule (running maximum of *apportioned* widths) overflowed the pane by over 100 px when run. The commit-time measure makes the result independent of how the text arrived | `StreamView._layout_blocks` |
| 8 | After any relayout a selection denotes the same text or is cleared, never other text. Each end is restated by glyph within its unit | the lead's first form clamped or cleared in more cases; the builder's mechanism keeps a selection through a re-break and through a commit, and the lead had invited better | `advtext.ui.units.carry_selection` |
| 9 | "We are handed a whole file" stays true of `build_document`; a streaming segmenter is built beside it | the section above | n/a |
| 10 | No LaTeX parser | the user's, held unchanged | n/a |
| 11 | Run batching for code blocks: check only, build nothing | the check came back conditional: monospace advances are exact at even pixel sizes and half a pixel off per character at odd ones | n/a |
| 12 | h4 to h6 are their own kinds: 16 px bold, bold italic, italic | the 1.25 scale's next steps (12.8, 10.24 px) are smaller than the text they would head, so they differ by face. h1 to h3 unchanged. The sizes are the builder's | one line each in `Theme.build` |
| 13 | Text that is not justified is broken first-fit, at natural width (no shrink) | measured: total-fit ragged costs 78 to 339 times justified and sets one word per line ahead of an over-wide word. With shrink left in, first-fit differed from total-fit ragged on 11 of 34 blocks at 420 pt, and with it removed on none; and a ragged line set compressed defeats the point of ragged. **Changes existing `Align.LEFT` output**: measured for the comparison the decision asked for, shipped output before against after, 2 of 34 blocks at 420 pt (4 of 34 at 300 pt, 9 of 34 at 467 px, 2 of 34 at 800 pt; builder-6). The lead's own record of this decision still quotes the 11, which is the other comparison | `PROSE_BREAKING_TOTAL_FIT_RAGGED`; `advtext.ui._text_boxes` |
| 14 | Whoever lands a public view adds its names to `advtext.__all__` | the examples were specified as facade-only | n/a |
| 15 | A selection highlight does not cover blank fill at a line's ends | a highlight over fill selects nothing a copy would return. Asked for at the left of right-aligned cells; the builder applied it to both ends of every line and the lead accepted that. **Changes the shipped demo** | two loops in `FragmentQueries.rects` |
| 16 | A press on a live link never starts a selection; links are styled only when the view has `on_link` | the alternative (drag selects, no movement clicks) makes every click a one-frame selection. Styling only live links leaves the demo page as it was | `BareView.style_links` |
| 17 | A wrapped table header puts its rule a full leading below its last baseline | the same rule an unwrapped header follows | `_WrappedRow.resumed_depth` |
| 18 | (a) a table arriving in one burst under `KEEP_STREAMED` is set at natural widths; (b) a fence or second paragraph in a list item copies with single newlines, and a trailing separator is dropped; (c) `DocumentView` snaps its cursor only, the other views their origin; (d) `SetLine` and `BareView.set_lines` are public | (a) timing-independence; (b) follows from "one block to a line inside a list"; (c) rounding the page's text origin would move every glyph of the shipped demo by up to half a pixel, which nobody asked for; (d) the examples were reaching into layout internals | each in `docs/adoption-plan.md` section A |

Also decided, without a number:

- **A table wider than its measure keeps each column at least as wide as its
  longest word** (builder's rule, `advtext.ui._squeezed`; accepted because a
  column narrower than its word is overfull by construction). It departs from
  "the current apportioning as default" where a table does not fit.
- **A table copies as tabs between cells and newlines between rows**; the items
  of one list as single newlines, a nested item indented two spaces a level.
- **One selection is current per process**, held in a module-level counter,
  because a view that submits no ImGui item never has keyboard focus to test.
  Two ImGui contexts in one process would share it.
- **`Face.CODE_BOLD`, unregistered, is backed by Roboto Bold.** It is what bold
  on a code base already was, so it changes nothing. Its builder is least sure
  of it; the lead left it open.
- **Which faces are monospace is declared on `Faces`**, not read from the font:
  `advtext/style.py` opens no font file, and a role can be registered any file.
- **The draw backend's memo lives for one `draw` call.** Nothing to invalidate;
  it cannot hold a pointer into a rebuilt atlas.
- **A view snaps its origin to whole pixels** although ImGui handed it a whole
  origin on every frame measured, on the user's standing rule that no fix
  accepts blur.
- **`StreamDocument.append` is safe from one producer thread**; everything else
  stays on the drawing thread.
- **The stream decides commits on complete lines only**, and a followed
  top-level fence commits when its closing line ends rather than a line later.
  A followed top-level table commits on the first complete line that is not a
  row of it (the blank line after it, nearly always), for the same reason:
  otherwise the whole table is read again for every piece of the sentence
  after it. That one is its builder's decision, taken in the last task and
  read by no reviewer; it rests on a reading of markdown-it's table rule, and
  if the reading is wrong a committed table is wrong.
- **A workaround for a crash in markdown-it-py 4.2.0 is kept**, on the ground
  that a crash on model output is worse than carrying a workaround.
- **The cost of a long live table: first not scheduled, then scheduled and
  built.** The lead's reason for leaving it was that a 600-row table is not a
  common shape. The cost at 20 rows (6.4 ms a row, measured afterwards) was not
  known when that was decided; when it was, the lead withdrew the decision and
  the last task built it (the stream follows a top-level table row by row, a
  `StreamView` lays it out in pieces of four rows). Its builder's figures: a
  row costs 0.8 to 1.2 ms from 10 to 200 rows where the table fits its pane,
  where it cost 3.0 to 64 ms. Not flat, by the same builder: a cell that
  widens a column sets every piece again, a table wrapped to a narrow pane is
  about 2.5 ms a row, and a table inside a list item or quote is not followed.
  No reviewer read it.
- **The anchor of a drag in progress is carried by its own rule**
  (`advtext.ui.units.carry_caret`, the last task but one, unreviewed). A caret
  put down on fill is restated after the last glyph before it when its unit is
  set again with the same characters up to it; the alternative was the drag
  ending at the next relayout, which in a stream is the next token. A drag
  from such a caret can begin with a space it would not have begun with
  before: the builder's reading, not measured.

### Decisions that did not hold

- **3, the mouse path "blocked on a display".** See the correction above. The
  path was exercised in a real window.
- **7 as first written, 13 as first written ("glue as emitted"), 8's "cleared
  on `RESET`"**: each replaced the same day by the form in the table, the first
  two because running them showed the problem. The lead's file amended 7 and
  13 and never 8: it still says a selection touching a block re-set by `RESET`
  is cleared. The tree does not always clear it. A selection is carried by
  glyph through any relayout, a `RESET` commit included, when its units set
  the same characters, and cleared only when they do not; row 8 above is the
  as-built form.
- **A lead's reading in review 3**, that a long list commits item by item: the
  lead's own snippet built a list markdown-it splits at item ten. The reviewer
  had been right, and a real one-block list cost 2 rising to 43 ms a piece
  until it was fixed.

---

## Second build (2026-10-07): the user's decisions, and everybody else's

Added 2026-10-07 by the agent that closed the second build's gate.

After the adoption plan was built the user asked, in conversation with the lead
agent, for a second build: a comprehensive demo, a diff view, inline
mathematics. The session's premises file names only the first build, so that
conversation is the only source for what follows, and the lead recorded the
user's words (`.concerns/lead--demo-tasks.md`, not version-controlled). They
are kept apart here from everything an agent decided, because the two were
easy to confuse while the work ran: the user was not answering questions.

### The user's decisions, in the user's words

| on | the user said | what was built from it |
|---|---|---|
| the math subset | "I would go with a subset as well. Just enough to be useful without having to dive into a parser. I would consider that an extension that sites on top of this engine, no?" | `advtext/mathtext.py`, outside `advtext/math/`; the engine has no parser |
| chat replies | "Canned." | the Chat page replays `demo/chat/script.md` through a stream; no network |
| the diff display | "This one is important enough to be feature rich. Especially if pptmstr is going to be using it." | `advtext/diff.py`, `advtext/ui/diff_view.py` |
| tabs or examples | "The demo should be comprehensive." | one app, fourteen pages |
| matrices | "Leave out for now but note it." | refused by the subset with that reason; noted in `README.md`, `docs/status.md`, `docs/adoption-plan.md` and on the Math page |
| long diff lines | "Definitely scrolling long lines" | a diff line never wraps; one horizontal offset, shared by both sides in side by side |
| a diff tab or a diff inside chat | "Both" | the Diff page, and a fenced `diff` in a document drawn by a `DiffView` |
| navigation | "Sidebar list now" | the tab bar became a sidebar list |
| then | "Please demonstrate both side-by-side and unified. Go straight to building." | both layouts, switchable at run time |

That is all of it. **The user has not seen or approved anything below this
line**: not the growth of the math engine, not `$$`'s semantics, not math
being off by default, not the sidebar's grouping, not a single diff rule, and
no choice a builder recorded in a result file.

### The lead's decisions — awaiting the user

Each with the reason the lead gave. "Light", as before: a description of what
is implemented and why, not a boundary. D1 to D6 are the lead's numbers
(`.concerns/lead--demo-review0-findings.md`).

| # | decision | reason given |
|---|---|---|
| D1 | The math engine grows a radical, sized delimiters, explicit spaces and text in math, all from ready-made outlines; glyph assembly and accents stay out | the subset the user asked for is not useful without them, and the extension cannot honestly fake them. The engine still has no parser |
| D1, amended | Delimiters follow TeX's rule as written (factor 901, shortfall 5 pt absolute); when no outline satisfies it the largest is set if it covers 75% of what the rule asks, and the formula is refused below that. Radicals keep the refusal | as first built, ordinary formulas were refused for being 3 to 5% taller than the largest parenthesis. **The 75% is the lead's number, not TeX's.** A surd that does not reach its rule is broken, not short |
| D2 | `$$` has fence semantics in a stream: a `$$` line opens a display block that runs to the next one or the end of input | any rule that needs its closer lets a later line change a block already committed |
| D2, amended | An unclosed `$$` block is shown as its source and set once when it closes | measured: one live formula changed between set and refused three times |
| D3 | An inline formula is one indexed item: one selection unit, copied as its `$...$` source | measured: a nested box shipped its own line, was culled while on screen and copied out of reading order |
| D4 | `DiffView` lays rows out on its own pixel grid, not through the document layout | measured: 1159 ms to lay out a 5,000-line diff as code before anything is drawn |
| D5, D6 | which files a task may edit; pages use public routes and report what was missing | board mechanics; the missing calls became one task, the view API |
| — | Math is off by default in `build_document` and `StreamDocument` | a host turns it on; text with dollars in it is otherwise unchanged |
| — | Two inline guards beyond pandoc's: an opening `$` not after a letter or digit, a closing `$` not before one | `set $PATH=$HOME/bin` set `PATH=` in math italic. pptmstr's transcripts are about code. Costs `$n$th` |
| — | In a stream, a `$` that is the last character received closes nothing yet | a streamed shell line showed a set formula for one piece |
| — | A character the bound face lacks is borrowed from the prose, math or code face, else set as U+FFFD and counted | it was drawn as nothing, anywhere |
| — | Two diff inputs, one model: texts are primary, a unified-diff parser is second. Monospace, never justified | texts are what pptmstr has, and what make intra-line emphasis and expandable context possible |
| — | The standard for the diff: never show less than the change, never attribute a change to the wrong file, never put text on the clipboard that exists on neither side without saying so | the view is where an operator approves a pending write |
| — | A control character never hides content: it is diffed and drawn as a placeholder with a header warning; "binary" is a status only the host or git's own line sets. The same for invisible and bidirectional control characters | one NUL made a whole change show as `+0 -0`; a right-to-left override is text that reads differently from what it is |
| — | A `---` / `+++` / `@@` run inside a hunk is rows when the hunk's counts are owed exactly one removal and one addition, and a file header otherwise | first "always a header" (pptmstr's lying counts), which then hid a change in an honest zero-context diff; counts decide |
| — | `Diff.from_edits`, and the statement that a host holding the texts must not use `from_unified` | a physical line `-foo+bar` cannot be repaired from text |
| — | A lone `--- X` opens a file only when the next line is `+++`; no input line is ever dropped | a test log in a `diff` fence lost lines. Costs sloppy model diffs their file name |
| — | A mail is recognised only by git's mbox line | a fragment starting with the word `From` was read as "not a diff" |
| — | Combined diffs and text that is not a diff are shown raw under a header saying so | one marker column cannot read a combined diff; an empty view is worse than raw text |
| — | Rows that differ only in line ending carry a mark; a file that differs only so says so and is folded | such a change showed identical `-` and `+` lines |
| — | A copy never joins non-adjacent pieces silently: `…` on its own line between them | select-all on a two-hunk diff put line 24 beside line 58 |
| — | Removed lines copy only when they are all that is selected (the builder's rule, kept); Ctrl+C with nothing to copy leaves the clipboard alone | whether they copied had depended on whether the context line above was blank |
| — | A hosted block at a document's edge is taken only by the select-all gesture, carried as state | inferring it from the range got both cases wrong when measured |
| — | NUL goes to the clipboard as U+2400 | the clipboard is a C string and cut the text there |
| — | Every diff ink is at least 4.5:1 on every ground it is drawn on | the `+` / `-` marker, the decided non-hue channel, was 3.91 to 4.46. A number, not a claim about looks |
| — | Added and removed stay nearly identical in greyscale | pptmstr's own rule is that the marker is the channel. **Reported to the user as an open choice** |
| — | The sidebar's five groups and each page's order are fixed in one table (`.concerns/lead--demo-page-order.md`, pinned in `tests/test_pages.py`); a page that raises is caught and shown | so no page picks a number inside another group's range; an exception in a page killed the app |

### Builders' decisions — awaiting the user

Accepted by the lead or never ruled on. The builder is named as its result
file names it.

- **Window 1300x800; the page drawn in a group, not a child; `name` one word,
  `title` the label** (builder-17, C-shell). The body keeps its 1068 px width
  and gains the tab bar's 36 px of height rather than the window shrinking to
  hide that.
- **`run()` raises `PageError` after the window closes** (C-pagefix): so a
  script that photographs the app still exits non-zero instead of
  photographing an error message. Its builder: "a choice nobody asked for".
- **Ink and ground come from one palette** on every page (C-pagefix); two
  pages had been drawing ink 1.02:1 on their ground.
- **`{` and `(` after a closing `$` also stop a formula** (builder-26), for
  `${HOME}/bin:${PATH}` and `$(a)$(b)`.
- **`\frac` is an Inner atom; integrals take no limits by default; function
  names, `\mathbb`, `\overline` and a symbol typed as itself are in the
  subset** (C-mathtext). `\binom`, `\ ` and `~` were added later (builder-26);
  `\quad` is 18 mu of the math face, not 1 em of the prose face.
- **`SPACE` is an atom type, not a third kind of math item** (builder-20), to
  keep another task's file type-correct. Its builder is least happy with it.
- **A formula is an `Atom`, a subclass of `SetGlue`, marked inside its box**
  (C-mathinline), so neither backend had to change.
- **A replaced character carries its original on the node** (`ReplacedChar`,
  C-facade), not in a per-block map as first sketched, because a stream cuts
  blocks into pieces.
- **Diff pairing and its bounds** (C-diffmodel): similarity floor 0.5, 256
  cells of alignment, lines over 500 characters not tokenised, 400,000
  characters of comparison a hunk. "A choice, not a measurement."
- **The diff copy rule, Ctrl+A in `DiffView`, switching layout clears the
  selection, click expands 20 lines and Shift+click from the bottom, the
  view's own horizontal scrollbar, every `DiffPalette` value** (C-diffview).
- **The placeholder is U+FFFD in the warning ink** (builder-27): Inconsolata
  has none of the control pictures. DEL counts as a control character. The
  end-of-line mark is ASCII. Raw lines cannot be selected. Seven hard cases on
  the Diff page, then nine.
- **A selection spanning text and a hosted diff copies the fence's body
  verbatim**; a press inside a hosted rectangle is the widget's; a diff line
  is shown when its newline arrives; the diff is parsed from the markdown
  source (C-hostdiff).
- **Ctrl+A in `BareView`** (builder-29): the lead named the gesture and the
  view had no such key. **The six new palette values** are its arithmetic.
  It left review 3 item 1(b), placeholders in markdown text, undone and said
  why.
- **What the facade leaves out** (C-facade): `SELECTION_OWNERSHIP`,
  `PageError`, `advtext.mathtext.parse`, the diff's tuning constants, the
  engine's atoms.
- **Decided not to build** (C-viewapi): marking a table cell.
- **Page choices**: the Tables drag rule and 720 px opening measure; the Find
  page's five copies, 600 px measure, mark colours and Enter rule; the Chat
  page opening on a finished exchange and its buttons over a block's corner;
  the Diff page's 40/60 split and 900 px threshold; the Stress page's three
  figures and stagger; the Themes page's half-pixel size stops.
- **By the gate closer**: the Chat page's copy buttons go through the same
  clipboard helper as the views (the one unowned item of review 3); the
  section order and wording of the second build's documents.

### Decisions of this build that did not hold

- **D1 as first written**, "refuse when the content is taller than the largest
  variant": amended as above after it was measured against ordinary formulas.
  **The em-relative shortfall** builder-20 chose so that refusal would not
  depend on pixel size: replaced by TeX's absolute 5 pt, so whether a formula
  takes one outline or the next now does depend on the host's pixel size.
- **"The parser has no lookahead"** (C-diffmodel, for an exact streaming
  invariant): replaced by one line of lookahead and then by the counts rule.
  A stream snapshot can now show a file header and take it back.
- **"A NUL in either text makes the file BINARY"** (C-diffmodel): withdrawn.
- **The triple rule as "always"** (review 1): replaced in review 3.
- **The edge-copy rule as inferred from the range** (C-hostfix): replaced in
  review 3 by the gesture.
- **"`\ ` and `~` stay refused"** (builder-23): added by builder-26.
- **Row 5 of the first build's table above, "the demos are `examples/*.py`,
  not new tabs"**: both now. The user asked for a comprehensive demo; the
  examples remain the facade-only proof.
- **"No LaTeX parser" stands**, and reads differently: the engine has none,
  and a subset reader sits above it by the user's decision.

---

## imtypeset adoption, experimental branch (2026-10-10)

Added 2026-10-10 by the builder of the session's documentation task (IT-DOCS),
before the review-fix task and the terminal gate ran. What those two did was
added the same day by the terminal gate's builder (IT-GATE2): this paragraph,
the four rows of the builders' table that name IT-GATE, and the second paragraph of "What
review was, and what it found". Nothing else in the section was changed.

This is the branch `experimental/imtypeset-adoption`, cut from `main` at
30496e1. Nothing on it is committed. `docs/status.md` section 0c says what
exists, what was measured and what is open; this section keeps who decided
what.

### What the user asked, in the user's words

The session's premises file is the whole of it, two sentences:

> [imtypeset adoption] Look for the planning around imtypeset adoption and
> start the work on that as an experimental branch.
>
> You make research `../imtypeset` for documents related to it's scope for
> answers to questions.

**That is all the user said, and the session ran unattended: nobody answered a
question.** The user decided two things: that the work starts, and that it is
an experimental branch. The user has not seen or approved anything below this
line. As in the two builds before, read each row as a description of what is
currently implemented and why, not as a boundary.

### Where the plan is

`../imtypeset/docs/advtext-rework-plan.md`, section 6.3, steps A0 to A6
(section 4.3 has its measurements, 5.2 the behaviour changes, 7 its open
items). It is in the sibling checkout, not in this tree, and it is itself an
agent's document: written from a spike, `../imtypeset/python/spike_advtext/`,
and calling itself measured, not verified by a person. Its recommendation, "a
new thin layer beside the present views, not a retrofit of the 94-name facade",
is the one design decision this branch inherits rather than takes.

The lead's rule for it, which this section follows: where the plan disagrees
with the tree, the tree is the evidence, and no figure of the plan's is copied
into this tree as fact.

### The lead's decisions — agent decisions, awaiting the user

Each with the reason the lead gave (`.concerns/lead--imtypeset-adoption-brief.md`
and the four `lead--` files after it, not version-controlled).

| decision | reason given |
|---|---|
| The A0 tag `advtext-reference` is at 32e3953, not the plan's a3c589a. Local, not pushed | a3c589a predates a history rewrite and is on no branch; 32e3953 is the rewritten merge with the byte-identical tree (both `^{tree}` are 7a591a48), and `advtext/` is unchanged from there to `HEAD` |
| The other half of A0 is recorded as blocked, not attempted | the oracle scripts that would refuse an untagged tree live in `../imtypeset`, and this session could write only inside this directory |
| The library is built into `build/imtypeset-bundle` (gitignored) by `../imtypeset`'s own script, from that checkout's working tree as it stood | it builds from inside this repository and passes its import gate. The lead said in the same breath that the working tree had uncommitted changes and agents editing it, so a later build may differ |
| A new layer beside the old: new files only, `advtext/__init__.py` and the existing views untouched | the plan's recommendation; `__all__` is tested at 94 names |
| Without `IMTYPESET_LIBRARY`, or when the gate refuses, nothing of imtypeset is imported; tests that need the library skip with the reason, and the gate must be green both ways | advtext without the library is to be exactly what it is on `main` |
| No figure from the plan is copied; every figure names who measured it and at what load, read as a ratio | the plan's numbers were not verified by the lead |
| One new demo page; no existing page is converted | the plan says "demo pages opt in one at a time" |
| A5 (tables) is not in this session; in the typeset path a table draws nothing and the page says so | a start on an experimental branch; the alternative in the plan is to wait for tables in the core |
| The demo app's font hook became its own task | IT-A1's builder found that no task's files included `advtext/ui/app.py` |
| A view checks `ready()`, not only `module()` | a Document with no fonts fails softly and draws nothing |
| In a stream, a selection is kept across an `append_text` and may be dropped across a real replace | the append is the common streaming case; carrying across arbitrary replaces is machinery the migration map lists as not surviving. (The builder went a little wider; below) |
| Marks go to a view as plain tuples, `view.set_marks(finder.marks())`, with `finder.set_index` after every edit | a packed object holds byte offsets and goes stale when the document is edited in place |
| The review findings are fixed in the task that was to be the gate, and a second task is the terminal gate | board mechanics: a separate fix task would have been ordered after the gate |

### Builders' decisions — agent decisions, awaiting the user

Accepted by the lead or never ruled on. Each builder is named as the board
names it; the reasons are from its result file.

| who | decision | reason given |
|---|---|---|
| IT-A1's builder | The module is `advtext/typesetter.py`, not the plan's and the board's `advtext/typeset.py` | `advtext.typeset` is already a facade function (formulas), and importing a submodule of that name replaces it: measured, `type(advtext.typeset)` became `module` |
| | The package is located by its own variable, `IMTYPESET_PYTHON`, appended to the end of `sys.path` inside `module()` | the tests' `window` fixture replaces `PYTHONPATH` in its child, so a windowed test would have kept the library, lost the package, fallen back to the old view and passed |
| | `module()` imports lazily and `ready()` is a separate question; a failed import is remembered and not retried | a context needs a Dear ImGui context, so being available and being ready are two moments |
| | All seven `Face` roles are registered, CodeBold included, each from `advtext.fontlib.font_file` | the spike left CodeBold out, and bold inline code would then be the prose bold; a host's `register_font` applies |
| | Six departures from the spike's converter: runs ascending and never overlapping, so a link over styled text keeps its tag; `Run.scale` relative to the block; a replaced character in code described as written; link tags owned by the converter for its life; a style's own indent not counted as a misfit; `MarkerGap` from the theme | each from the first reviewer's reading, confirmed by the builder in the spike or the library's header. On the six demo files the port and the spike agree on every block |
| | `pyproject.toml` is unchanged: imtypeset is imported by name through `importlib` and held as `Any` | mypy never looks for it, so nothing was loosened |
| | `TYPESET=1`, or an `IMTYPESET_LIBRARY` already set, turns the make targets on; a library asked for and absent stops with a line naming `make typeset-lib` | default recipes stay character for character what they were (tested); a suite that silently skips is not a run |
| | The library tests run in a child interpreter; a library that is set and refuses is a failure, not a skip | the pytest process never loads the library |
| builder-2 (IT-A4) | Formula source is not searched; `casefold()` with a length guard, not the spike's `lower()`; a space matches a hard break in prose and not in code | `advtext.spans.FindIndex` behaves so, and a reader does not see a formula's source |
| | At most 4000 marks, the current match always among them | from the spike; the library's header says each mark costs a comparison per draw. **The number is not measured** |
| | The class is named `FindIndex`, like the one in `advtext.spans` it mirrors; the two are not interchangeable | its matches are `str` offsets, not material indices |
| builder-3 (IT-A2) | `TypesetUnavailable` from the constructor when the library is absent, and from `draw` when it is not ready or the library raised; a library raise calls `typesetter.disable`, a host callback's exception does not | the host can draw `BareView` at the same cursor in the same frame |
| | Nothing is drawn where a table is | a placeholder needs a geometry call per table per frame, which breaks the three-call budget |
| | The copy test asserts what the library does, not what the board said | measured on three demo files: the non-empty texts joined by the separator |
| | A drag is anchored to text; no item while idle and a button only during a press; selection ownership and the text-input check are `BareView`'s, imported | the first reviewer's reading of where the spike departed from `BareView`'s contract |
| | `scroll_to` is looked at on four consecutive draws | layout is lazy, so a block's place is an estimate until what is above it is laid out; settling everything costs a full layout. A reader who scrolls within those frames is brought back |
| | Per-role inks and `page` are not applied; live links are coloured and not underlined; `fonts=` is accepted and ignored | the first two are in the description or have no counterpart; the last so a call site can swap views |
| builder-4 (IT-APP) | The font hook is a wrapper `run` hands the runner, not the end of `app.load_fonts` as the task said | `load_fonts` is public and a test calls it in the pytest process, where the hook would import the library. From reading, not from a run of the other variant |
| | `before_exit` unloads the library | the app had no exit hook; without it a second `run` in one process had the library refuse, in the builder's probe |
| builder-5 (IT-A3) | Descriptions are compared before the edit, and leading blocks whose description is unchanged are skipped; not the plan's and the board's "the first block that is not the same object starts one `replace_blocks`" | a stream makes every block of its unfinished tail anew at each change. Built as written, `math.md` gave 6 appends and 231 replaces; as built, 179 and 55 (the builder's replays) |
| | "One edit per sync" is at most one, and none when no description changed | a line end arriving changes the revision and no description |
| | `append_text` only to a block that holds text, whose new text extends the old with every other field equal and no new style | appending to a Host block raises, which would switch the library off |
| | A selection is kept when it still names the same text, across an append and across a replace; dropped whole otherwise | the rule is about text, not about which call was made. Wider than the lead decided; `StreamView` cuts back instead |
| | `set_document` on a stream view raises `TypeError`; `sync` returns False once the library is off | the next sync would overwrite it in silence; the second is a guard around a defect in the base view, left for the fix task |
| builder-6 (IT-PAGE) | The page asks `typesetter.ready()` and never `module()`, so in a headless frame it is always the `BareView` path, with or without the variable | pages are built in the pytest process by `tests/test_pages.py`, and two earlier decisions keep the library out of it. **Its builder's least sure decision** |
| | The renderer is chosen once, when the page is built; a view that fails later is replaced by `BareView` for good | fonts are loaded before the first frame, and `disable` is not undone by anything |
| | Under `BareView` the find box counts and does not mark | a match here is a range of a described `str` and does not convert to a range of material |
| | A new sidebar group, `Experimental`, order 510 | the heading is the only thing in the sidebar that can say the page is not like the others |
| | No `on_link` on the page: links are neither coloured nor clickable under either renderer | not asked for |
| the review-fix task's builder (IT-GATE) | The guard for a library that is off is in `TypesetView._set_blocks`, the one caller of `_edit`; `advtext/ui/typeset_stream_view.py` is not edited | the third reviewer's trap: the stream view's `_edit` trusts state that exists only while `_set_blocks` runs, so a second call site could skip an edit the library needed. The stream view gets the fix through its base |
| | When the library is off the view lets go of the library's document: it neither keeps it nor closes it | kept, it would be behind the description if the library ever came back; closing is a call into a library that has just failed. Letting go leaves the release to the package's own guarded `__del__` |
| | A malformed mark is `TypeError` from `set_marks`, whatever is wrong with it; shape and field types are checked, positions are not | one type for a host to catch; the view already leaves out or clips a position that is not there |
| | The stream view's own guard in `sync` is left | harmless, as the lead asked; it also keeps a view that cannot draw from reading the stream |
| this section's writer (IT-DOCS) | `docs/status.md`'s section is 0c and is placed above section 0; `README.md`'s present-tense page and shot counts are updated and its dated paragraphs are not; the stale count in `scripts/run_demo.py` is left for the fix task | the task asked for the top; the counts were checked against `scripts/shot.py --list` (27); the script is in no documentation task's files |

### What review was, and what it found

Three review tasks, each by an agent with no shell: **every finding is from
reading, and nothing was run by a reviewer.** The first read the plan's
premises against both trees before anything was built; the builders' rows
above say which of its readings they confirmed. The other two tried to break
what was built. Two findings in `advtext/ui/typeset_view.py` and one docstring
in `advtext/typeset_find.py` were queued for the next task, to be reproduced
with a failing test before anything is changed; the rest were recorded as
open. Both lists are in `docs/status.md` section 0c, "Open". The third
reviewer found nothing it called must-fix in the stream view or the page, and
said what it was least sure of: what the library holds besides text.

**What became of the queued findings** (added by the terminal gate's builder).
All three reproduced: the review-fix task's builder wrote a test for each
first and saw it fail, two of them also against the library itself, and then
made the changes in the table above and in `docs/status.md` section 0c,
"Open". The findings recorded as open were not run by that task and are
still readings. The stale page count in
`scripts/run_demo.py` was confirmed by a search and corrected in the same
task. The terminal gate then ran `make check` without and with the library on
the finished tree: 5006 passed, 49 skipped, 4 xfailed, and 5048 passed, 7
skipped, 4 xfailed, with no failure either way (the loads are in
`docs/status.md`). The terminal gate changed no source file: nothing was red.

### Premises of this session that did not hold

- **The plan's commit for the tag**, a3c589a: on no branch since a history
  rewrite. Above.
- **The board's module name**, `advtext/typeset.py`: the lead's, taken from
  the plan, and wrong for this tree. Above.
- **The lead's brief, "use it with `PYTHONPATH`"**: replaced by
  `IMTYPESET_PYTHON` the same day, for the reason in the table.
- **The board's copy rule for the view**, "select-all-and-copy equals the
  described texts joined by the separator": the lead's, and false wherever a
  block has no text. The first reviewer suspected it; builder-3 measured it.
- **The board's "edit count per sync is 1"**, and the lead's correction of it
  to "1 when the revision changed": both false for white space arriving,
  measured by builder-5.
- **"At the end of `load_fonts`"** for the app's hook: the task's wording.
  Above.
- **The spike's test for "nothing changed"** (`blocks is seen`), which the
  plan's stream figures were measured through: `StreamDocument.blocks` is a
  new tuple on every read while a block is live, so it never held. The first
  reviewer's reading, confirmed in source; the view keys on `stream.revision`.
- **A sentence in IT-A1's result file** about how a refused formula is
  described was contradicted by the second reviewer from the source and is not
  repeated in these documents.

---

## The swap (2026-10-10 and 11)

Added 2026-10-11 by the builder of the session's last task (T5-FINAL), an
agent, after the deletion and before the terminal gate; the gate's counts
were written in afterwards. The section above this one is the first day of
the same branch and is not changed. `docs/status.md` section 0d says what
exists, what was deleted, what was measured and what is open; this section
keeps who decided what.

Still the branch `experimental/imtypeset-adoption`, cut from `main` at
30496e1, and still nothing committed.

### What the user said, in the user's words

After the first day's work (the section above) the user gave direction four
times. These are all of the user's words that reached the session, in order,
as the lead recorded them (`.concerns/lead--full-swap-direction.md`, not
version-controlled). Everything not inside quotation marks in this section is
an agent's.

> "The intent is see adv-text with a full swap out using as much as it can
> from imtypeset."

> "`DiffView` is definitely part of the adv-text but I'd say that we start
> seeing a fuzzed border for some of the other features. I'd lean towards
> keeping imtypeset focused on intent (typesetting) but being pragmatic about
> what it can optimize for advanced text render and features."

> "Isn't tables and columns straight from TeX? Shouldn't that be part of
> imtypeset?"

> "specimen and formula sound like imtypeset domain"

> "Give me a prompt for the imtypeset team to continue work. I already have
> them tee'd up. Then continue with the swap out as far as you can reach as
> the two efforts meet in the middle."

**What the user decided, read narrowly:** that the end is a full swap and
not a second renderer beside the first; that the diff view is advtext's;
that imtypeset stays a typesetter; that a second team works in `../imtypeset`
at the same time. The third and fourth quotations are a question and an
impression. The lead took each as direction (tables and columns, then the
specimen and formula galleries, are the other tree's to build) and said at
the time that this was its reading.

**What the user was asked and has not answered:** whether the SVG litmus
renderer leaves advtext. It is why 17 modules of the old layout core are
still here (below).

**The user has not seen or approved anything below this line.** The session
ran unattended after those sentences. As in the builds before, read each row
as a description of what is implemented and why, not as a boundary.

### The lead's decisions — agent decisions, awaiting the user

Each with the reason the lead gave, from the `lead--` files of
`.concerns/` (not version-controlled): `swap-build-plan`,
`library-refreshed-and-pinned`, `tranche-3`, `tranche-4`, `tranche-5`,
`tranche-5-phase-B`, `tranche-5-final`.

| decision | reason given |
|---|---|
| **The border.** imtypeset: everything TeX does (line breaking, packing, math, alignment and so tables, splitting a vertical list into columns), plus fonts, selection and drawing what it set. advtext: content and application features (markdown, streaming, the diff view, find, themes, the views' interaction, hosted blocks) | the lead's reading of the first three quotations; called "still an agent's reading" where it was written |
| The old layout core is REPLACED, not kept beside the new layer. The first day's "new layer beside the old" was the transition | "a full swap out" |
| Nothing is written in `../imtypeset`. A need for a change there is recorded as a request with the measurement behind it, and is not worked around by keeping a copy of the old core alive without saying so | the session can write only in this tree; the other team reads `.concerns/lead--for-imtypeset-team.md` and answers in its own `docs/advtext-swap-status.md` |
| **The end state needs the library to draw.** Tests that need it skip without it; `make check TYPESET=1` is the gate that means something; plain `make check` must still pass | a suite that is green on a machine without the library is worth keeping, and about two fifths of the tests are model and plumbing tests |
| While both existed, a moved page fell back to the old view when the library was not ready. Phase A of tranche 5 removed every fallback: a page then draws one line saying why | the suite stayed green at every step while the other team's half was in flight; a fallback is the transition, not the end |
| An exception out of a draw that is `TypesetUnavailable` is shown as that one line; any other exception is a bug and propagates | a fallback that swallowed bugs would have hidden them behind the old view |
| Tables: a stopgap first (cells set by the library inside a rectangle advtext measured), then the core's own table blocks at `be40444`, with the stopgap deleted. Where a listed defect of the core's tables bites, it is stated and not worked around | the third quotation; the stopgap had no cell selection or find by design, because the core's tables were to replace it |
| Columns: no stopgap. The Columns page stayed on the old core until the core had columns (`0b21807`), then moved onto `Document.set_columns`, and `advtext/columns.py` went | the same quotation |
| The Specimen and Formula pages become thin pages over imtypeset's demo sections. **Including the Math page is the lead's extension**: the other team built for it, and the user was told and has not objected | the fourth quotation names two pages, not three |
| The Blocks page is deleted with its tests | it demonstrated the old core's `hpack` and `vpack`, which the border puts in imtypeset, and imtypeset exposes no boxes. It is in `main` if wanted back |
| **The SVG litmus chain is not touched**, in any tranche, and every module it imports stays, with that module's own unit tests | the user has been asked and has not answered. "A kept module with no tests is worse than a kept module" |
| The deletion rule: everything that exists only for the old views or the old core goes, EXCEPT that chain's import closure, which is MEASURED first (by `ast` and by running the chain) | so that what stays is a list with a reason and not a judgement call per file |
| Where a typeset test used the old code as its oracle, the oracle's answers are frozen as data BEFORE the oracle is deleted. A typeset-path test is not deleted because its oracle is going, and not weakened to make a deletion easier | deleting the old core would otherwise have deleted the evidence that the new path agrees with it |
| Fonts: `Theme.at_pixel_height` and `typesetter.load_fonts` keep reaching the old font reader, lazily, until imtypeset answers a face's metrics | the other team has been asked (item 5 of the note to them); there is no other font reader on this side |
| The app stops adding its own copies of the faces and takes them from the library; without the library it loads one UI font so the "why not" line can be read | the other team's answer (f) |
| The facade: a name survives if and only if its home module survives. Names of deleted things are removed, not aliased. Names that survive only through the SVG closure are kept, grouped and commented as "the reference core, kept for the litmus renderer" | an alias to something similar would promise behaviour the new object does not have |
| **The library is built from a commit the other team names, not from its working tree**, and the Python package is snapshotted beside it. In order: `12d77ac`, `be40444`, `92847e6`, `7a7bc36` | the first day's library was built from a working tree with uncommitted changes and went stale overnight when the other team's package began calling a function it did not export (found by a builder's run) |
| The git index is the checkpoint: the lead stages each finished tranche, nobody else touches the index, and nothing is committed | a deleted file can be read back from the index; a commit on an experimental branch was not asked for |
| A reviewer's finding is from reading. It is reproduced with a failing test before any code changes; if it does not reproduce, that is said with the evidence and nothing changes | reviewers had no shell |
| Scratch scripts run from the repository, never from the shared temporary directory | a stray module there shadowed the standard library twice in one night and once launched a browser |

### Builders' decisions — agent decisions, awaiting the user

Accepted by the lead or never ruled on. **This is not every decision in
every result file**: the files are `.concerns/<task>--builder--result.md`,
each has a section of its own decisions, and the rows here are the ones that
still shape the tree. Many decisions of tranches 2 to 4 were about code that
tranche 5 deleted (the table stopgap, the fallbacks, the old examples) and
are not repeated.

| who | decision | reason given |
|---|---|---|
| SW-0, T3-D (the Makefile) | `make typeset-lib` replaces the whole bundle directory at the end of a successful build, copies the package BEFORE building, and gates the install on an import of the copy against the new library. `IMTYPESET_COMMIT=<rev>` builds an archive of that commit. A library that is not the one `BUILT-FROM` describes is refused by a prerequisite, not by a line in each recipe | the failure being fixed was a library and a package from different moments; recipes stay what the tests pin |
| SW-1, T3-A1, T5-B2 (the theme and the package) | `advtext/theme.py`, then `advtext/primitives.py`, as core-free homes; `advtext.ui` forwards the old compositor's names lazily; `BlockStyle` carries `leading` as a number and answers the old `interline` triple as a property | so that importing the typeset layer, and building a theme, loads none of the reference core. Measured empty over 37 rows |
| SW-2 (markdown to a description, no node material) | **White space is put in the run of the text beside it, which differs from what the old path described**: of 8,000 interword spaces in the demos, none is then in a face whose space differs from the glue the old core set; with the old path's runs 96 were | the builder's measurement, offered as "my decision; you may reverse it" |
| | A refused formula goes to the library as it is: drawn as its source without dollars in the paragraph's face, and `draw()` answers False while it is in view | the library and the old builder agreed on all 22 formulas tried; "a sample, not a proof" |
| T3-A2 | `load_fonts` destroys any imtypeset context it finds before making one. `disable()` releases nothing; `unload()` does, also after a `disable` | the other team's rule (do not reuse a context you find); `disable` is called from inside a draw with documents in use up the stack |
| | The stream reader's resume helpers were COPIED from the old markdown module, with a test holding the source text of each equal | the old module imports the layout core |
| | Following a fence inside a list item or a quote is NOT built for the new stream | about 300 lines; cost measured in the result file |
| SW-3, T3-C, T4-DIFF (the diff view) | Two documents a pane on a fixed line pitch, tall rows equalised across documents; selection kept as model positions and drawn as marks; no placeholder is substituted for a character no face has; `off_grid` removed in favour of `code_face_lacks` | each from a probe; the last two because they would change what a reader sees and nobody asked |
| | The old view's answers are a frozen file (`tests/data/diff_view_answers.json`) and the tests read the file | one comparison path, so the tests that survive the deletion are the ones that were already running |
| T3-B (the views) | The view culls marks to the window itself, at two hit tests a frame | a 600-line code block with 1,881 ink marks went from 48 to 2,515 microseconds a frame when every mark was handed over (the builder's run, load 3 to 12). A request to the other team |
| T4-TABLES | A table's stated columns live in the description, so they survive the document being made again and are dropped by an edit that replaces the block. Under "keep", every table of a stream is held, committed ones too. Keep or reset is read from `live_theme is theme` | the last is recorded as open: it is wrong for a theme that is already ragged |
| | The header rule's height is not worked around | the tranche's rule: state a defect of the core, do not hide it |
| T4-GALLERY | The gallery pages push the theme's body size, 16 px, not the 19 px of the other team's pictures | body size is what every other page sets running text at. Asked of the other team (item 6) |
| T4-PAGES-B | No test asserts that `KEEP_STREAMED` moves zero lines through imtypeset | "a red that means the library breaks lines otherwise would be noise in others' gates". Recorded as open by the reviewer |
| T4-GATE | A hosted block is asked about again when where it came from changed and the block did not | a fenced diff at the end of a streamed reply was one line short. **Its builder's least sure decision** |
| T5-COLUMNS | `count` is how many columns stand across the width in both fills; `set_columns` asks the library nothing until the next layout; neither fill, both fills, or balance with one column is a `ValueError`; pages are a sideways scroll of ONE drawn document | one meaning for a width; a malformed argument cannot reach the region where a failure switches the library off; one draw keeps a frame at three calls and lets a selection run through every page |
| | The page offers balanced columns, which the old core never had | the library has them. The page says "new" |
| T5-FB-A, B, C (the fallbacks) | One sentence format tree-wide, `imtypeset is not drawing: <reason>`. An example says it on standard error and exits 1 BEFORE opening a window. A page that gave up does not come back when the library is ready again. `renderer` reads `none` | a host that cannot draw should not open a window to say so; a library that failed mid-run is off for the run anyway |
| | Without the library the pages keep their state logic (a search, a theme chosen, a replay's clock) and the plain gate tests that through stand-in views | phase A's rule 3. **T5-FB-B's builder was least sure of the stand-ins** |
| T5-APP | The role the app draws its own text in is `PROSE`, named as the default font at 16 px. After a failed library load the app's font is NAMED the default | measured: the library's fonts stay in the atlas after its context is destroyed, so being loaded is not being first |
| | `scripts/run_demo.py` and `scripts/shot.py` note a missing library on stderr and carry on | a refusal would have broken every caller that photographs the one-line state on purpose. (Narrowed by T5-FINAL, below) |
| | The contrast test reads a frame's vertices in a real window | the test it replaced wrapped the deleted backend. **Its builder's least sure decision: a wider net than the one it replaced** |
| T5-B1 (the deletion) | `advtext/mathtext.py` is deleted though the lead's list did not name it | it is outside the closure and nothing of the typeset layer imports it; 603 tests went with it |
| | `advtext/ui/fonts.py` is NOT deleted though it is outside the closure | the app still calls it for the one UI font. Left as "the lead's call" |
| | `examples/theme_gallery.py` is deleted and not ported; `demo/math.md` is kept though no page reads it | a port would be a new 500-line example; four test files use the demo file as a corpus |
| | The window fixture waits for its Xvfb's port to be free before starting one | three unrelated window tests failed in one whole run with "server already running" |
| | A caveat about a caret in columns was removed from the view, and `scroll_to` no longer asks `column_count` first | measured the same with and without at `7a7bc36` |
| T5-B2 (the facade) | `Hosted` on the facade is the typeset view's protocol, though the old one's module survives in the closure | one name can mean one thing, and a host's widget is drawn by a `TypesetView`. **The one departure from the facade rule** |
| | `advtext.style` gained one function (`interline_skip`) though closure modules were otherwise not to be edited | the task asked for it; the chain's artifacts are byte for byte the same |
| | The examples import from the package root and from nowhere else in the package, except the module `advtext.typesetter` | they imported submodules by path because the typeset layer was "beside the facade" |
| T5-FINAL (the last task) | **`TypesetView`, `TypesetStreamView` and `TypesetDiffView` share one rule for whose a failure is**: an exception the `imtypeset` package defines switches the library off; anything else is raised as itself. Two existing tests that stood a built-in `OSError` in for a library failure now raise a subclass of the package's own `Error` | the lead's instruction (make the view agree with the diff view). The tests' input changed because the rule did; what they assert did not |
| | `scripts/shot.py` exits 3 and writes NO PNG when the library was asked for and was not drawing; `scripts/run_demo.py` says so at exit and still exits 0 | the lead asked for non-zero from the first and "prints the reason" from the second. Exit 3 so that it is not 2 (no display) or 1 (a page raised). No PNG because the file would carry a page's name |
| | What the pages were saying is read in the app's `before_exit`, before the library is unloaded (`advtext.ui.app.not_drawing_at_exit`) | after the unload `ready()` is false for a library that drew to the last frame too |
| | A page states the most its launch integer may be (`PageSpec.max_count`); the count is not capped for every page | the same integer is a rate on Stream and a number of panes on Stress |
| | Chat, Stream and Stress CLOSE their views when they give up and KEEP them | `report()` reads the page's state; the Diff page drops its views and has nothing to report from them |
| | Every frame helper in the tests ends its window in an inner `finally` (23 sites), though the lead asked only for the child scripts' | a test now holds the shape for all of them with no exceptions to list; the in-process ones were also failing with Dear ImGui's message in place of the page's exception |
| | In the tour, the Stream page's replay is fed whole before it is judged | four frames at its own rate were 8 glyphs of its own text, measured |
| | `advtext.ui.app.DEFAULT_MARKDOWN`, the document an installed wheel shows, was reworded | it said the Python pipeline sets the text. T5-APP left it for the docs pass |
| | `README.md`'s present-tense sections were rewritten where they named deleted things; its dated paragraphs, and every older section of `docs/status.md` and of this file, were not | a README that tells a reader to run a deleted script is a defect; a dated paragraph is a record |
| T6-SIZE (after the user ran the demo and asked for a larger or selectable Math page) | The three gallery pages have a *text size* combo of 14, 16, 19, 23 and 28 px and open at 23, where T4-GALLERY's row above says 16. `--tab math:19` opens at 19; an integer not in the set is the nearest that is; above 28 is refused. The section's own sliders are not touched | from the font files: the pushed size is a line height, and a formula's x-height at 16 is 5.89 px, at 19 is 6.99 px and at 23 is 8.46 px against 8.45 px for the Document page's running text; 23 is the smallest whole size that reaches it. In a 1300 x 800 window no section is wider than its pane at any of the five. A combo and not a slider: a change of size is 37 layouts on Specimen, 12 on Formula and 257 on Math, measured |

### What review was, and what it found

Three more review tasks (the board's SW-R1, T4-R and T5-R), each by an
agent with no shell: **every finding is from reading, and nothing was run by
a reviewer.** Each
tranche's findings went to the next tranche's builders as "reproduce with a
failing test first". Most reproduced. The ones that did not are said in the
result file of the task that tried (`T3-C`: a suspected hole in the diff
view's tall-row net did not reproduce on the bundled faces, and its builder
changed the code anyway and said so).

The review of phase A found that the library had been rebuilt, to `7a7bc36`,
AFTER every phase A gate had run against `92847e6`: the evidence was of
another library. The lead ran the suite again on the new pin (4 failures, all
then assigned and fixed in phase B). It also found the three fix-now items
and five smaller ones that the last task ran: all eight are in
`docs/status.md` section 0d, "Open", with what became of each. Six
reproduced as defects and were fixed. The other two were about tests that
assert too little (the tour's contrast bound, and Chat's "finished messages
are not laid out again"): each was shown to assert too little and was
strengthened, and neither had a defect of a page behind it.

**The last task changed source after the deletion**, so what the two phase B
gates measured is not quite the tree that stands. The terminal gate ran on
the tree that stands: `make check`, 2875 passed, 262 skipped, 4 xfailed;
`make check TYPESET=1`, 3129 passed, 8 skipped, 4 xfailed; no failure either
way (the loads are in `docs/status.md`). Run by the last task's builder, an
agent, alone on the tree.

### Premises of these two days that did not hold

- **"The library in `build/` is the one the tests ran against."** False for
  one night (the other team's package moved past it) and once more in
  tranche 5 (above). Hence the pin, the snapshot and the checksum.
- **The diff spike's "cannot be worked around through the API"** (FS-S1),
  about rows of unequal height in a side-by-side diff. SW-3's builder
  disagreed, from probes, and built it.
- **The first reading of the border**, "advtext keeps the table logic,
  imtypeset sets each cell": the lead's, withdrawn the same day when the user
  asked the third quotation.
- **"A draw that raises leaves the frame closed because the helper renders
  in a `finally`"**: the shape of 23 test helpers. Rendering a frame whose
  window was not ended raises out of `render` and leaves the context
  mid-frame. Three builders met the cascade before anyone named the cause.
- **"`OSError` stands in for a library failure"** in two view tests: true
  only while every exception was taken for the library's.
- **The task text for the last task** said five child scripts and ten
  in-process helpers; the reader written for it found 23 of that shape, and
  it said 94 facade names where the tree had 89 by then (the lead's own
  correction, sent with the task).
- **The contrast test's lower bound**, "more glyphs than the chrome": every
  page met it with the library drawing nothing (219 to 885 glyphs against a
  bound of 212).

---

## Correcting the brief

The research brief asked for "the 4/5 and 1/5 x-height clamps" in
`make_scripts`. The source has **4/5 and 1/4** (§757, §758); there is no 1/5 in
§756-§759. The brief was wrong and `docs/tex-notes.md` records the code.

`\vbadness` does not enter the page cost function (§1005, §1007); it gates
diagnostics in `vpack` only (§674, §677, §678).

Both corrections are noted because a wrong premise stated confidently is the
expensive kind, and the brief was mine.

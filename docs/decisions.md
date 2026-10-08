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

## Correcting the brief

The research brief asked for "the 4/5 and 1/5 x-height clamps" in
`make_scripts`. The source has **4/5 and 1/4** (§757, §758); there is no 1/5 in
§756-§759. The brief was wrong and `docs/tex-notes.md` records the code.

`\vbadness` does not enter the page cost function (§1005, §1007); it gates
diagnostics in `vpack` only (§674, §677, §678).

Both corrections are noted because a wrong premise stated confidently is the
expensive kind, and the brief was mine.

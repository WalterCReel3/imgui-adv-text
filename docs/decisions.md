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

## Correcting the brief

The research brief asked for "the 4/5 and 1/5 x-height clamps" in
`make_scripts`. The source has **4/5 and 1/4** (§757, §758); there is no 1/5 in
§756-§759. The brief was wrong and `docs/tex-notes.md` records the code.

`\vbadness` does not enter the page cost function (§1005, §1007); it gates
diagnostics in `vpack` only (§674, §677, §678).

Both corrections are noted because a wrong premise stated confidently is the
expensive kind, and the brief was mine.

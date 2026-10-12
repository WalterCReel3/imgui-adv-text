# ImGui risks, in the order worth working through

> **2026-10-12:** the package this document calls `advtext` was renamed `imscribe` (`advtext/…` is `imscribe/…`, `import advtext` is `import imscribe`). Nothing below was changed for it.

This was "the list for the first person who opens this on a machine with a
display". That person has been. Two of the items below are settled and say so;
the rest are the ones a display did not answer.

Read `docs/decisions.md` first. This file is narrower: it is only about the layer
that touches Dear ImGui, and only about what is still capable of being wrong.

## What changed, twice

**First, and this is the older correction: a window needs a display, a frame
does not.** `imgui.create_context()` allocates plain memory, `ImFontAtlas` bakes
glyphs on the CPU through stb_truetype, and `new_frame`/`render` build vertex
buffers in RAM. A GPU is needed only to *composite* those buffers onto a screen.
So the atlas, the metrics and `advtext.backends.imgui_draw.draw` were all
reachable from a sandbox with no display, and they were reached.

**Second, and it is new: there is a display here, and the demo has run on it.**
`DISPLAY=:1`, X.Org 1.22.1.9, direct rendering on an AMD Radeon (renoir) through
Mesa 22.3.6 — real hardware, not a software rasteriser. `make shot` opens the
real window through `immapp.run`, runs it for N frames and grabs the framebuffer.
`docs/status.md` section 2 has the per-function trace of what that executed.

| Thing | State |
|---|---|
| `advtext.backends.imgui_draw.draw` | Executed, in a real frame, asserted on, and **composited**. `tests/test_imgui_draw.py`, then `make shot` |
| `scripts/verify_advances.py` | Executed. Its docstring table is its own output |
| `scripts/verify_ascent.py` | Executed. Its docstring table is its own output |
| `advtext.fontlib.imgui_font_file` | Executed, pinned by two tests, and the display sigma has been photographed |
| `advtext.ui.app`, `advtext.ui.document_view` | Executed. `run`, `gui`, `load_fonts`, `apply_style` and `DocumentView.draw` all run in a real window |
| `scripts/run_demo.py` | Executed, and **tested**: `tests/test_run_demo.py` covers `main` and the `DISPLAY` guard. It stubs out `app.run`, because `tests/conftest.py` forbids this suite from opening a window |
| **A mouse click** | **Performed by a script, never by a hand.** This row read "Never happened" until 2026-10-06. `scripts/mouse_probe.py` posts eight gestures into the real app in a real GLFW window and its 18 checks pass. The events enter at `ImGuiIO`, not at the X server, and the window was on Xvfb with llvmpipe |
| `BareView`, `StreamView`, `draw_runs`, live links, the four `examples/` | Executed in real frames with no display by their tests; each example's `main()` opened a real window on Xvfb and drew with nothing missing. **Never on a GPU, never looked at** |

The boundary this file used to police was *compositing*. The boundary now is
**input**, and one machine's worth of driver.

**Third, 2026-10-07: "there is a display here" is true of the machine and was
not true of every session on it.** The adoption session's sandbox had
`DISPLAY=:1` set and unreachable. Everything it ran in a window, it ran on an
Xvfb in a user namespace over TCP with Mesa's software rasteriser, which is
exactly the configuration the paragraph above says behaves differently for
texture formats and premultiplied alpha. So the work of that session
(`docs/adoption-plan.md`) has been composited by llvmpipe only. Its per-role
ink, per-run colour, link underlines and selection fills all go through the
same `add_text`, `add_rect_filled` and `add_line` calls the photographed demo
uses, which is an argument and not a photograph.

Three risks that session added, in working order:

- **`ImDrawListFlags_.text_no_pixel_snap` may be renamed in Dear ImGui 1.93.**
  The backend sets it; the dependency floor is now `imgui-bundle>=1.92.900`,
  the first release that has it. A search summary of ocornut/imgui#9504 said
  the flag folds into `ImDrawFlags`; the issue was not read. **Symptom:**
  `AttributeError` on the first `draw`. **Where to look:**
  `advtext.backends.imgui_draw.draw`, `scripts/pen_rules.py`, and the floor
  test in `tests/test_makefile_env.py`, which goes red first.
  *Note of 2026-10-12, by an agent, on the branch
  `experimental/imtypeset-adoption`:* the sentence above is left as it was
  written and is no longer true there. The dependency is the exact pin
  `imgui-bundle==1.92.900`, not a floor; the backend that set the flag,
  `scripts/pen_rules.py` and the floor test are deleted, and nothing under
  `advtext/` names the flag (L1-PKG's builder's grep). The test in that file
  now holds the pin. `docs/status.md` section 0e.
- **`BareView` leans on two ImGui behaviours nothing documents.** It submits an
  `invisible_button` only from the frame a press lands, and needs ImGui to make
  a button first submitted on that frame the active item; and it asks
  `imgui.internal.get_hovered_id()` because the public hover call is also true
  for the previous frame's item. Both held in 1.92.900, headless and on Xvfb.
  **Symptom if the first stops holding:** selection still works and the host
  window drags with it.
- **A fractional origin moves line gaps.** Each line's top is snapped on its
  own and the body leading is 21.6 px: moving a view's origin by 0.25 / 0.5 /
  0.75 px changed 21 / 43 / 44 of 54 gaps. ImGui 1.92.900 handed a view a
  whole-pixel origin on all 417 frames measured, and `BareView` now rounds its
  cursor regardless. `DocumentView` rounds the cursor and not the page's text
  origin, which was always fractional. **Where to look:**
  `BareView._cursor_origin`.

Two things to know before running anything, both learned by hitting them:

- `io.backend_flags` must carry `renderer_has_textures` before the first
  `add_text`, or ImGui aborts on `IM_ASSERT(atlas->TexIsBuilt)`.
- Building a bare `ImDrawList` from `get_draw_list_shared_data()` outside a
  frame **dumps core**. Do not reach for it as a shortcut; use a real frame.

---

## 1. Compositing — SETTLED, on one machine

**This item used to read "Nothing has been composited to a screen."** It has
been. All five tabs are photographed at 1400×900 by `make shot-all` (*the
five the app had then, on a GPU; since 2026-10-07 it has fourteen pages in a
sidebar, photographed at 1300×800 on Xvfb only and looked at by nobody, see
`docs/status.md` section 0b*), and the
things a shader, a texture format, a premultiplied-alpha convention or a wrong
`ImTextureID` would have broken are visibly not broken: the Document tab shows
prose on a page, the Formula tab shows a sigma noticeably larger in the left
copy than the right, the Columns tab shows text continuing from the foot of one
column to the head of the next, and `document:debug` shows `_debug_line` and
`_debug_glue` drawing line boxes and per-glue rectangles.

**Command:**

```
make shot ARGS="--tab formula --width 1400 --out artifacts/formula.png"
make shot-all
```

**What is left.** One GPU vendor, one Mesa version, one X server. A window
manager here silently clamps a window to 1920 px, so two shots requested above
that width are the same shot. And the Xvfb path is still the right answer on a
machine with no display: `make shot-headless`, 22s per tab against 2.3s.

---

## 2. The fractional origin — REFUTED, and the real defect was one layer down

**Both halves of this item were wrong, and it was the item this file said to
look at first.** It claimed `advtext.shipout` rounds to the pixel grid and that
`draw` then adds a fractional `origin` from `get_cursor_screen_pos()`, defeating
it.

- `advtext.shipout.ship` takes no `px_per_inch` and performed **no** pixel
  rounding at all. There was nothing for a fractional origin to defeat. The
  comment in `draw`'s `at()` closure that said ship-out "rounded once" was
  load-bearing and false.
- The pen position never blurred anything either. ImGui 1.92's
  `ImFont::RenderText` opens with `float x = IM_TRUNC(pos.x)`, and sweeping one
  glyph's requested x from 100.0 to 100.99 emits byte-identical vertices.

**The text was soft, and the mechanism is the baked size.**
`ImFont::GetFontBaked(size)` bakes at `floor(size + 0.5)` and then draws the
baked bitmap scaled by `size / baked_size`. `baked_size_px` asks for a fractional
size for five of the six faces — only Latin Modern Math, whose
`(ascent + descent) / em` is exactly 1.0, was ever crisp. So every quad was a
non-integer number of pixels across: **1734 of 1734 glyph quads in
`demo/sample.md` were resampled**, at a fixed phase per glyph rather than a
random one per instance.

**Fixed.** Ask ImGui for the size it was going to bake at anyway, and round the
pen ourselves instead of letting ImGui truncate it. 0 of 1734 quads resampled
after; solid-ink pixels in a band of body text 413 → 686.

**What is still true and is the residue:** interletter gaps and
baseline-to-baseline distances are quantised to whole pixels, which is intrinsic
to integer snapping. The two remedies are per-phase bitmaps, which ImGui's bake
key `(font, size, density)` has nowhere to store, and fractional placement via
`ImDrawListFlags_TextNoPixelSnap`, which is one line and is exactly the blur the
user excluded.

**And a third remedy exists and is being taken.** Snapping each *word's* origin
rather than each glyph's makes every instance of a word render identically —
66 of 496 word keys drawn at more than one shape, down to 0 — at the price of
0.99 px worst-case glyph displacement instead of 0.50, and 0.79 px of rendered
rag on a justified right edge instead of 0.49. The user accepted that trade
explicitly. Re-derive those four numbers before quoting them.

**Where to look:** `snap_px` and `_snap_span` in
`advtext.backends.imgui_draw`. **`docs/subpixel.md` is the full write-up**,
including the four options rejected, the `tex.web` §616 `dvi_h:=cur_h` rule that
makes snapping absolute positions safe where snapping advances is not, and
commands for every number.

---

## 3. The advance residual, which per-glyph positioning exists to absorb

**Settled, with numbers, and the numbers are not zero.**
`scripts/verify_advances.py` found ImGui's advances disagree with fontTools' by
enough to matter: at a nominal 16 px, drift over a 44-character line reaches
42 px. The cause is a size-denominator mismatch, now corrected (item 4). After
correction the residual is about **1 px per 44 characters** and no simple
rounding rule reproduces it.

That residual is why `advtext.backends.imgui_draw` positions **one glyph at a
time** rather than handing `add_text` a whole string. That decision is now a
measurement and not a hedge, and it should not be reversed for performance
without re-running the script.

**Symptom you would notice:** if someone batches runs into single `add_text`
calls, words drifting rightward along a line and the last word of a long line
overhanging the right margin.

**Where to look:** `advtext.backends.imgui_draw._glyph`, which is one call per
glyph on purpose.

**Command:**

```
/home/wreel/Source/pptmstr/.venv/bin/python scripts/verify_advances.py
```

Needs no display. Runs today.

---

## 4. The size handed to ImGui is not the size we laid out with

**Found by measurement, and fixed.** "Size" names two different lengths:
`advtext.fontlib` scales a face by `size / unitsPerEm`, so a size of 16 makes the
*em* 16 px; stb_truetype scales by pixel *height*, roughly
`size / (hhea.ascender - hhea.descender)`. For Roboto those denominators are 2048
and 2400, so passing our size straight through bakes every glyph **about 12.4%
too small**.

`advtext.backends.imgui_draw.baked_size_px` applies the correction. Latin Modern
Math needs none — its ascender and descender sum to exactly its 1000-unit em, so
its corrected size equals its nominal one, which is a useful control.

**Symptom you would notice:** prose noticeably smaller than the SVG artifacts of
the same document, with the gap widening at heading sizes.

**Where to look:** `advtext.backends.imgui_draw.baked_size_px` and its one caller
in `_glyph`. It is one multiplication and it is deliberately not folded into
anything else.

**Command:** `make svg`, then open `artifacts/markdown.svg` beside the demo's
Document tab. They should be the same size; the SVG is the reference.

---

## 5. The ascent conversion — settled, and where to look anyway

`advtext.backends.imgui_draw._glyph` converts our baseline to ImGui's top-left
origin using **ImGui's** ascent, not `fontlib`'s. That was an argument and it is
now a measurement: `scripts/verify_ascent.py` checks the identity
`glyph.y0 == baked.ascent - ink_top` against ImGui's own glyph boxes and finds it
holds to **1.6007 px worst case over 90 boxes**, which is ImGui's whole-pixel
quantisation of a glyph box and not a disagreement.

The two ascents *do* differ, by up to 4.4 px at 36 px, and that difference does
not displace anything: `_glyph` subtracts whatever ascent the same baked font
reports, so a larger baked ascent raises the top-left and lowers `glyph.y0` by
the same amount. Substituting `fontlib`'s ascent would break that and is the
change not to make.

**Symptom you would notice:** every line in the document sitting a constant
amount too high or too low — constant is the tell, because a layout bug varies
with content and this would not.

**Where to look:** `advtext.backends.imgui_draw._ascent`. If lines are off by
roughly a whole ascent rather than a pixel or two, the baseline is being passed
through unconverted somewhere.

**Command:**

```
/home/wreel/Source/pptmstr/.venv/bin/python scripts/verify_ascent.py
```

Needs no display. Runs today. The last line prints a verdict.

---

## 6. The synthetic codepoints — solved, and the fallback still matters

`advtext.fontlib` mints private-use codepoints in plane 15 so `summation.v1` — a
real unencoded display variant — can be named. That minting is what makes the
sigma litmus test honest rather than a scaled-up U+2211. ImGui rasterises by
Unicode codepoint through the font's own cmap and knew nothing of it, so for a
while the project's headline claim was demonstrable in the SVG backend and not
this one, for a mechanical reason rather than a layout failure.

`advtext.fontlib.imgui_font_file` closes it: our mappings are written into a copy
of the font's **format-12** cmap subtables and ImGui's own lookup finds the glyph
unaided. Two facts make it work, both measured rather than assumed:

- imgui-bundle 1.92.801 is built with a **32-bit `ImWchar`**, so a plane-15
  codepoint survives the binding. The discriminating test is that
  `is_glyph_in_font(0x12211)` returns False rather than truncating to U+2211 and
  returning True. **A 16-bit build makes this whole approach impossible** — check
  it first if this ever stops working on another build.
- Latin Modern Math carries two format-12 subtables. Format 12 is the only cmap
  format that can express a codepoint above U+FFFF.

`imgui_font_file` **degrades rather than raises**: a font with no format-12
subtable gets the original file back, and `DrawStats.missing` counts what cannot
be drawn. That path is the reason `DrawStats.missing` is not dead code, and it is
untested — no bundled font exercises it.

**Symptom you would notice:** the Formula tab showing two sigmas of the same
size, or printing a non-zero missing count. Either means the patched file is not
being loaded.

**It does not.** `make shot ARGS="--tab formula"` photographs the two side by
side: the left operator is large with its limits stacked over and under it, the
right is small with its limits beside it as ordinary scripts. So the claim this
project is most likely to be doubted on now holds through ImGui, on a screen,
and not only in the SVG backend.

**Where to look:** `advtext.ui.app.load_fonts`, which must call
`fontlib.imgui_font_file` and **not** `fontlib.font_file`. That one-word
difference is the whole of it.

**Command:**

```
/home/wreel/Source/pptmstr/.venv/bin/python -m pytest tests/test_imgui_draw.py -q
```

Needs no display. Runs today.

---

## 7. `draw` needs the same metrics the packing used, and nothing enforces it

`draw` takes a `metrics: MetricsResolver` because `baked_size_px` has to read the
face's em from somewhere. This is the same unenforced contract
`docs/decisions.md` already records for `advtext.shipout.ship`, and it now has a
second instance.

**Symptom you would notice:** text at the wrong size, everywhere, with no error —
the same silent failure mode as the `ship` contract, which is what makes it worth
naming twice.

**Where to look:** the `metrics` parameter of `advtext.backends.imgui_draw.draw`.
It defaults to `advtext.style.fontlib_metrics`, so the failure only arrives if a
caller overrides it.

---

## 8. A missing glyph is only counted when a face was bound

`_glyph` calls `font.is_glyph_in_font(...)` and counts a miss — but only when
`fonts(face)` returned an `ImFont`. When it returns `None`, `draw` falls through
to the three-argument `add_text` on whatever face is currently bound and **never
checks coverage at all**, so a missing glyph there is silently absent and
`DrawStats.missing` stays zero.

`None` is a deliberate, documented answer — pptmstr's `theme.face` makes the same
choice — so this is not a bug so much as a hole in the reporting.

**Symptom you would notice:** blank space where text should be, with the demo
insisting nothing is missing.

**Where to look:** the `font is None` branches in
`advtext.backends.imgui_draw._glyph` and `_baked`.

This item used to end "This path has never been executed: every test binds a
real face." **That is no longer true** — `tests/test_document_view.py` and
`tests/test_bench_draw.py` both call `draw(..., fonts=lambda face: None)`
deliberately, so the branch runs. What has not changed is the defect: those
tests are about layout and scroll geometry, and none of them asserts anything
about `DrawStats.missing`, so the reporting hole is executed and unexamined
rather than unexecuted.

---

## 9. `_FACES` is a module global and `run` can be called twice

*(2026-10-06: `load_fonts` now calls `_FACES.clear()` first, and loads through
`advtext.ui.fonts.load_faces`. Still a module global; still nothing calls `run`
twice, so the clearing is read and not exercised. A host does not use this
module: it holds its own `LoadedFaces`.)*

`advtext.ui.app._FACES` is populated by `load_fonts`, a hello_imgui callback.
Nothing clears it. A second `run` in the same process repopulates it against a
new context, and any entry surviving from the first holds an `ImFont` belonging
to a destroyed atlas.

**Symptom you would notice:** garbage glyphs or a crash on the second window,
never the first. Only reachable from a script or a test that opens two windows;
`scripts/run_demo.py` opens one.

**Where to look:** `advtext.ui.app._FACES` and `advtext.ui.app.load_fonts`.

---

## 10. Atlas growth across sizes

Since 1.92 a face bakes on demand at whatever size is pushed, and this project
pushes several: `Theme.build` generates five from one body size, and the formula
adds a sixth. Six faces times six sizes, plus 227 extra reachable math glyphs in
the patched file, is a larger atlas than anything in pptmstr.

Nothing here has hit a limit, and nothing here could — no texture is ever
uploaded, so the maximum texture size that would bound it is never consulted.

**Symptom you would notice:** missing glyphs appearing only at one size, or an
atlas-too-large warning on a machine with a small `GL_MAX_TEXTURE_SIZE`.

**Where to look:** `advtext.style.Theme.build` for the size set, and
`advtext.ui.app.load_fonts` for the faces.

---

## 11. 96 px/inch is an assumption, and the display has now been seen but not measured

`docs/decisions.md` §5 settles that device coordinates are pixels and that
`px_per_inch = 96.0` is an explicit parameter rather than a module global. If
ImGui turns out to treat its coordinates as points, this seam is wrong by
**1.333×** — 96/72.

That is large enough to see immediately, which is the one mercy, and it has now
been looked at: the demo photographs at a plausible size beside the SVG of the
same document, and nothing in the shots is a third too large. **That is
eyeballing, not measurement.** Nothing in this tree compares a rendered em
against a physical inch, and the honest statement is that the 1.333× version of
this bug is ruled out and a small error in `px_per_inch` is not.

It stays last because every measurement above was taken in ImGui's own units and
came back consistent, and because `scripts/verify_advances.uniform_ratio` already
exists to catch the large version: a uniform ratio near 1.333 across every glyph
is that bug announcing itself rather than a rounding difference.

**Symptom you would notice:** everything a third too large or a quarter too
small, uniformly.

**Where to look:** `advtext.units.DEFAULT_PX_PER_INCH`, and the `px_per_inch`
argument threaded through `advtext.backends.imgui_draw.draw`.

**Command:**

```
/home/wreel/Source/pptmstr/.venv/bin/python scripts/verify_advances.py
```

Look for the `uniform ratio detected` line.

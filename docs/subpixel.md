# Sub-pixel glyph phase

The user looked at the demo and reported that glyphs appeared touching or crowded, and
guessed this was an old, well-studied problem. It is. This document is the research they
asked for, the measurement, the option chosen, and the four options rejected.

**Everything numeric here is reproducible.** Section 8 gives the commands. Where a claim
is a reading rather than a measurement it says so, and two of the claims this work started
from turned out to be wrong — see section 7.

---

## 1. Summary

| | |
|---|---|
| **Defect** | Every glyph in the document was drawn through a bilinear texture resample. 1734 of 1734 glyph quads in `demo/sample.md`, 100%. |
| **Cause** | Not the fractional pen position. ImGui 1.92 quantises the *baked size* to `floor(size + 0.5)`, then draws the baked bitmap scaled by `size / baked_size`. `advtext` asks for 18.75 px; ImGui bakes 19 px and squashes it to 98.68%. |
| **Fix** | Ask ImGui for the size it was going to bake at anyway, and round the pen to the nearest pixel instead of letting ImGui truncate it. Draw time only; no layout-space geometry changed. |
| **Result** | 0 of 1734 quads resampled. Solid-ink pixels in a band of body text rose from 413 to 686; the ratio of midtone to solid ink fell from 4.23 to 2.20. |
| **Cost** | The em is now up to half a pixel from the size `baked_size_px` computed. Section 5 argues that cost was already being paid. |
| **Then** | Section 6.1's remaining option was put to the user and **taken**: the pen is snapped relative to the rigid span it is in, so every instance of a word is drawn pixel-identically. Section 5.5. |
| **Its cost** | Worst glyph departure 0.50 → 0.99 px, rendered right edge of a justified line 0.48 → 0.86 px. *Rendered* rag only; `tests/test_litmus.py`'s zero residue is in scaled points and is untouched. |
| **Then again** | Section 6.3, also the user's call after seeing a rendered ladder: the offset *inside* a span is quantised to half a pixel rather than a whole one, `PEN_QUANTUM_PX = 0.5`, with `ImDrawListFlags_TextNoPixelSnap` set so ImGui does not undo it. Anchors and the vertical axis stay whole. Mean error on a rendered inter-letter gap 0.2517 → 0.1433 px. |
| **Its cost** | A letter can now be rasterised at two phases instead of one, and the sheet's midtone-to-solid ink ratio goes 3.03 → 4.40. Worst glyph departure comes *back* from 0.997 to 0.737 px, bound 0.75. |

---

## 2. What was measured, before anything was changed

### 2.1 Layout coordinates are fractional in pixels

`advtext.shipout.ship` takes no `px_per_inch` and performs no pixel rounding: it works in
scaled points and returns exact coordinates. Converted to pixels at 96 dpi, glyph x
positions in `demo/sample.md` have arbitrary fractional parts. This is correct and is not
the defect; it is the input to the defect.

### 2.2 ImGui truncates the pen position, so the fractional part is discarded

Sweeping one glyph's requested x from 100.0 to 100.99 in nine steps emits byte-identical
vertices every time — same position, same UVs. The pen is quantised by ImGui itself, and
at 1.92.0 it was not optional:

```cpp
// Align to be pixel perfect
begin:
    float x = IM_TRUNC(pos.x);
    float y = IM_TRUNC(pos.y);
```

— `ImFont::RenderText`, [imgui_draw.cpp L5526-5532 @ v1.92.0](https://github.com/ocornut/imgui/blob/v1.92.0/imgui_draw.cpp#L5526-L5532).

**So the text was never blurred by the pen position.** That was the hypothesis this task
started from and it is refuted. But the text *was* blurred, which is section 2.3.

### 2.3 The real mechanism: ImGui bakes at a whole number of pixels

`ImFont::GetFontBaked(size)` does not bake at an arbitrary float. Measured across every
size this demo asks for, from 13.637 to 42.1875, the baked size is exactly
`floor(size + 0.5)`:

| asked for | baked at | scale applied |
|---:|---:|---:|
| 15.23438 | 15 | 1.01563 |
| 17.57812 | 18 | 0.97656 |
| 18.75000 | 19 | 0.98684 |
| 21.09375 | 21 | 1.00446 |
| 32.81250 | 33 | 0.99432 |

The bake key confirms there is no phase in it — `(font, size, density)`, three fields:

```cpp
ImGuiID ImFontAtlasBakedGetId(ImGuiID font_id, float baked_size, float rasterizer_density)
{
    struct { ImGuiID FontId; float BakedSize; float RasterizerDensity; } hashed_data;
```

— [imgui_draw.cpp L5215-5222 @ v1.92.0](https://github.com/ocornut/imgui/blob/v1.92.0/imgui_draw.cpp#L5215-L5222).

`RenderText` then places the quad at `x + glyph->X0 * scale` with width
`(X1 - X0) * scale`. With `scale != 1` both are fractional, so the quad is neither on the
pixel grid nor a whole number of texels wide, and the GPU interpolates between texels to
fill it. Measured on a single glyph: asked for at `(100.0, 300.0)` at size 17.578125, the
quad came out at `(100.976562, 306.835938)`.

This is why **every** glyph was soft: not a random phase per instance, a fixed non-zero
phase per glyph. Across `demo/sample.md`, 0 of 143 distinct (face, codepoint) pairs landed
on the pixel grid.

`advtext` asks for a fractional size for five of the six faces, because `baked_size_px`
multiplies by `(ascent + descent) / em` — 1.171875 for Roboto, 1.049 for Inconsolata.
Only MATH, whose ratio is exactly 1.0, was ever crisp.

### 2.4 Why it reads as crowding rather than as blur

Two separate things, and only the first is fixed here.

**Resampling.** A 1 px stem drawn across a 0.98 px span is spread over two pixel columns at
partial coverage. Adjacent stems each bleed toward each other, which closes up the
counters and the gaps. Different letters have different `X0`, so they got different
phases, so stems of different letters carried visibly different weight.

**Quantised gaps.** With the pen on a whole pixel, the gap between two glyphs is a whole
number of pixels. At 15 px body text an interletter gap is 1-3 px, so a half-pixel of
layout difference becomes a whole pixel of rendered difference — a 50% change in a visible
gap. This is intrinsic to integer positioning and is *not* fixed here; see section 6.
Microsoft states the same thing about the pre-ClearType renderer:

> Before these ClearType enhancements, text with a 'reading' size of 10 or 12 points was
> difficult to display: we could place either 1 pixel in between letters, which was often
> too little, or 2 pixels, which was often too much.

— [Introducing DirectWrite](https://learn.microsoft.com/en-us/windows/win32/directwrite/introducing-directwrite)

---

## 3. What the field does

Four families. They genuinely disagree, and the disagreement is aesthetic as much as
technical.

### 3.1 Sub-pixel positioning with N phases

Rasterise the glyph separately at each of N horizontal offsets and pick the nearest.
Spacing is preserved to 1/N px; the atlas costs N times as much.

**Skia** uses 2 bits of sub-pixel x and 2 of y — four phases per axis:

```cpp
// A combination of SkGlyphID and sub-pixel position information.
struct SkPackedGlyphID {
    enum { kGlyphIDLen = 16u, kSubPixelPosLen = 2u, ... };
```

— [SkGlyph.h L44-70](https://github.com/google/skia/blob/7f7ba7e2700802e6e0362bc12c8e25ad2e671ee7/src/core/SkGlyph.h#L44-L70).
The cost is stated in Skia's own reference: "Internally, the glyph cache may store multiple
copies of the same glyph with different sub-pixel positions, requiring more memory."
([SkFont_Reference.md](https://skia.googlesource.com/skia/+/dfec731dbfcf2565007ca94d85f7297f4f468aee/site/user/api/SkFont_Reference.md))

**Qt** also uses four, and — importantly for us — gates them on hinting being off:

```cpp
bool supportsHorizontalSubPixelPositions() const override
{ return default_hint_style == HintLight || default_hint_style == HintNone; }
```

— [qfontengine_ft_p.h](https://code.qt.io/cgit/qt/qtbase.git/tree/src/gui/text/freetype/qfontengine_ft_p.h?h=dev);
the count itself is `m_subPixelPositionCount = 4;` in `qfontengine_ft.cpp`.

**FreeType** has no "sub-pixel positioning mode" — note that its page titled *Subpixel
Rendering* is about LCD stripe filtering, a different subject. Positional work is the
caller's, at 1/64 px, and FreeType documents the idiom:

```c
FT_Outline_Translate( slot->outline, origin_x & 63, 0 );
```

— [FT_GlyphSlotRec docs](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html)

**DirectWrite** is not an N-phase quantiser; it documents continuous fractional placement
("individual glyphs can be positioned to a fraction of a pixel"), which belongs in 3.3.

### 3.2 Integer position snapping

Round each glyph to a whole pixel. Crisp, cheap, one bitmap per glyph; spacing quantises.
This is what X11 core fonts did structurally — the protocol's `CHARINFO` carries
`character-width: INT16`, so a fractional advance is not representable
([X11 protocol](https://www.x.org/releases/X11R7.7/doc/xproto/x11protocol.html)) — and what
`DWRITE_MEASURING_MODE_GDI_CLASSIC` still offers for compatibility
([DWRITE_MEASURING_MODE](https://learn.microsoft.com/en-us/windows/win32/api/dcommon/ne-dcommon-dwrite_measuring_mode)).

**It is also what this codebase's ancestor did.** TeX does not rasterise, but it is
scrupulous about the one thing that makes integer snapping safe, and the rule is worth
stating in its own terms because it is the rule section 4.2 implements.

TeX keeps two positions: `cur_h`, the exact accumulated coordinate, and `dvi_h`, where the
output device currently is. The device is *synchronised to* the exact position — never
advanced by a device-space delta of its own:

```
@d synch_h==if cur_h<>dvi_h then
    begin movement(cur_h-dvi_h,right1); dvi_h:=cur_h;
    end
```

— `tex.web` §616, line 12276 (prose at 12261). The assignment `dvi_h:=cur_h` is the whole
point: whatever the device did, its position is reset to the exact one, so error cannot
accumulate down a line. Knuth's reason is given two paragraphs up: "Coordinate changes will
accumulate in `cur_h` and `cur_v` without being reflected in the output, until such a
change becomes necessary or desirable" (§616, line 12265).

Section numbers here were computed by counting `@*` / `@ ` / bare `@` section starts, the
method `docs/tex-notes.md` records, and validated against five citations already in this
tree: §100 `half`, §101 `scaled`, §108 `badness`, §749 `make_op`, §859 demerits. All five
land on the right text, so §616 can be relied on.

### 3.3 Fractional advances, hinting off — the Quartz choice

Place the glyph wherever the layout says and accept the softness. Apple exposes the switch
explicitly: "When enabled, the graphics context may position glyphs on nonintegral pixel
boundaries. When disabled, the position of glyphs are always forced to integral pixel
boundaries."
([CGContext.setShouldSubpixelPositionFonts](https://developer.apple.com/documentation/coregraphics/cgcontext/setshouldsubpixelpositionfonts(_:)))
WebKit turns it on unconditionally for CoreText drawing.

The trade is the one Spolsky described, and it is the clearest statement of why this is a
taste question and not an engineering one:

> Apple generally believes that the goal of the algorithm should be to preserve the design
> of the typeface as much as possible, even at the cost of a little bit of blurriness.
> Microsoft generally believes that the shape of each letter should be hammered into pixel
> boundaries to prevent blur and improve readability, even at the cost of not being true to
> the typeface.

— [Joel Spolsky, *Font smoothing, anti-aliasing, and sub-pixel rendering*, 2007](https://www.joelonsoftware.com/2007/06/12/font-smoothing-anti-aliasing-and-sub-pixel-rendering/)

Note that Microsoft's own documentation argues the *opposite* direction from Spolsky's
framing of it: fractional positioning is what "improves the evenness and symmetry of the
entire page". Both are right about different failure modes. The sources do not settle this
and this document does not pretend they do.

### 3.4 Pango's answer: make it the caller's decision

GTK/Pango rounds by default and lets you turn it off:

> Sets whether font rendering with this context should round glyph positions and widths to
> integral positions, in device units. ... The default value is to round glyph positions.

— [pango_context_set_round_glyph_positions](https://docs.gtk.org/Pango/method.Context.set_round_glyph_positions.html)

---

## 4. What stb_truetype and ImGui actually offer

### 4.1 stb_truetype has the machinery; ImGui does not use it

`stbtt_MakeGlyphBitmapSubpixel`, `stbtt_GetGlyphBitmapSubpixel`,
`stbtt_GetCodepointBitmapBoxSubpixel` and friends all exist and all take `float shift_x,
float shift_y`, applied after scaling, in pixel space:

```c
if (ix0) *ix0 = STBTT_ifloor( x0 * scale_x + shift_x);
```

— [stb_truetype.h L2732](https://github.com/nothings/stb/blob/2c980bb59875b0d32144a71867fbdebb2f77cd20/stb_truetype.h),
and the advice at L231-236: *"Use the functions with Subpixel at the end to allow your
characters to have subpixel positioning. Since the font is anti-aliased, not hinted, this
is very import for quality. **(This is not possible with baked fonts.)**"*

That parenthetical is the answer for us. ImGui **calls the subpixel variant and hardcodes
the shift to zero**:

```cpp
stbtt_MakeGlyphBitmapSubpixel(&bd_font_data->FontInfo, bitmap_pixels, ..., 0, 0, glyph_index);
```

— [imgui_draw.cpp L4641-4642 @ v1.92.0](https://github.com/ocornut/imgui/blob/v1.92.0/imgui_draw.cpp). What
it does instead is stb's oversampling prefilter, which is a phase-*tolerant* blur, not a
set of per-phase bitmaps. **No version of ImGui bakes per-phase glyph bitmaps**, and
because the bake key has no phase field (2.3) there is nowhere to put them without
patching ImGui.

### 4.2 1.92.9 can turn snapping off, and that is the option the user ruled out

This matters because 1.92.9 is the version installed here. The changelog:

> Added `ImDrawListFlags_TextNoPixelSnap` to disable snapping of AddText() coordinates for a
> given scope. (#3437, #9417, #2291)

Verified live in this build — `imgui.ImDrawListFlags_.text_no_pixel_snap` is `1 << 4`, and
with it set, a glyph asked for at x = 100.7 comes out at 100.7 instead of 100.0.

That is option 3.3, available in one line. **It was rejected because it is exactly what the
user excluded**: fractional placement of a bitmap baked at one phase is resolved by the
renderer's bilinear filter, i.e. by blur. ocornut's own framing of the underlying problem,
from [#9417](https://github.com/ocornut/imgui/pull/9417), is about composability rather
than quality — rendering "foo" then "bar" not matching "foobar" — and this project already
draws one glyph per call for the reasons in `imgui_draw.py`'s docstring, so that particular
inconsistency never applied to us.

**Amended by 6.3, and the amendment is narrow.** `draw` now sets that flag. What 6.3 does
with it is *not* option 3.3: a glyph's offset inside its rigid span is quantised to half a
pixel, so the pen is still on a grid and the departure from the computed position is still
bounded, at 0.75 px. The paragraph above argues against an **unbounded** fractional pen and
that argument still stands; the user has since looked at a rendered ladder of quanta and
chosen a bounded middle. Anything in this section that reads as "snapping may never be
turned off" should be read as "the pen may never be left unquantised".

### 4.3 ImGui rounds advances only on request

`ImFontConfig::PixelSnapH` opts into `advance_x = IM_ROUND(advance_x)` at bake time
([imgui_draw.cpp L5093-5104](https://github.com/ocornut/imgui/blob/v1.92.0/imgui_draw.cpp#L5093-L5104)).
It is off by default and this project must never turn it on: it would quantise advances,
which is the accumulating failure section 5.3 exists to prevent — and it would do so
*inside* ImGui, where our layout cannot see it. We do not use ImGui's advances at all.

---

## 5. What was done

Three changes, all in `advtext/backends/imgui_draw.py`, all at draw time in device space.
No file in `pack`, `linebreak` or `shipout` was touched, and
`tests/test_litmus.py`'s zero-residue assertion is unaffected by construction.

### 5.1 Ask for the size ImGui is going to bake at

`_baked` now returns the `ImFontBaked`, and `add_text` is handed `baked.size` rather than
the fractional `baked_size_px`. This makes `scale` exactly 1.

**It selects the same raster.** `GetFontBaked(18.75)` and `GetFontBaked(19.0)` return the
same `ImFontBaked` with the same atlas coordinates and the same ascent — asserted in
`test_asking_for_the_rounded_size_selects_the_same_raster`. The only thing that changes is
the scale the identical bitmap is drawn at.

So the cost — the em is now up to 0.5 px from what `baked_size_px` computed — is smaller
than it looks. That half pixel was never being honoured. It was being *approximated by
blurring a raster that had already been rounded to the same whole number*, which is worse
than not honouring it. This is the trade in 3.1-vs-3.2 terms: we accept a ≤ 2.8% size
quantisation at 13 px body text to get a 1:1 texel-to-pixel draw, and the 12.4% error that
`baked_size_px` exists to correct is still corrected.

### 5.2 Round the pen instead of letting ImGui truncate it

`snap_px(value) = floor(value + 0.5)`, applied to the absolute screen position of each
glyph. ImGui would otherwise truncate (2.2), which biases every glyph in the document half
a pixel left and up and never right. Rounding halves the worst-case departure from the
position ship-out computed, from 1.0 px to 0.5 px. Measured over every glyph of
`demo/sample.md`: worst departure 0.499996 px.

Half up rather than Python's `round`, which rounds halves to even and disagrees with
ImGui's `IM_ROUND` at 60.5.

### 5.3 Absolute positions only — the rule that makes 5.2 safe

This is TeX's `dvi_h:=cur_h` (3.2) restated for a raster device. Every snap is applied to a
coordinate `shipout` already accumulated exactly. Nothing snaps an *advance* and sums it.

The distinction is not academic and it is not small. Measured on `demo/sample.md` at a
700 px measure, over the 70 lines of 20 or more glyphs:

| | worst | median |
|---|---:|---:|
| snapping absolute positions | 0.500 px | — |
| rounding advances and summing | **9.922 px** | 2.670 px |

52 of those 70 lines would end more than a pixel from where the line breaker put them, and
the worst is nearly two characters past the right margin — the residue
`tests/test_litmus.py` asserts is zero. An advance-rounding implementation produces
integer positions for every glyph, so it passes any "are the positions integral" check.
`tests/test_imgui_draw.py::test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin`
builds that implementation and asserts it fails, which is what stops the integrality tests
next to it from being the vacuous assertion `docs/status.md` section 5 warns about.

### 5.4 Areas, not just pens

Rules, selection highlights and the debug overlay are snapped too, by `_snap_span`, because
a filled rect with fractional corners has partial coverage on every side — a 1 px rule from
y = 10.6 to 11.6 comes out as two rows of grey. Both edges round the same way so abutting
areas stay abutting.

The one special case: a span thinner than a pixel can round both edges onto the same
boundary, and a zero-extent rect appends no vertices, so a hairline would **vanish** rather
than thicken. Any span with real extent is widened to one pixel. A span of genuinely zero
extent stays empty, because `Theme.table_rule_thickness` documents zero as meaning *no
line* and inventing a pixel there would draw ink the document does not contain.

**A concern against this, measured and refuted.** T11 flagged against itself, and T7-look
agreed, that widening a sub-pixel hairline to a full pixel would visibly thicken blockquote
bars and table rules at small sizes, and offered to revert `area()` and its three call
sites. Shot and magnified rather than reasoned about — a page with a blockquote, a table
and a thematic break, magnified 10x, and `demo/sample.md`'s own blockquote at 1100x1600:

| | asked for | drawn |
|---|---:|---:|
| blockquote bar | 2.40 px | **2 px** — *thinner*, not thicker |
| table rule | 0.96 px | 1 px |
| thematic break | 0.96 px | 1 px |

Neither is a hairline. `Theme.build` derives these from the type size and at the demo's
size the rule comes out at 0.96 px, so the widen-to-a-pixel branch only decides the answer
for the 4% of vertical phases where `snap_px` would take both edges to the same boundary,
and it gives the same 1 px the other 96% give. The bar reads no heavier than the stem of a
capital beside it. `area()` stays.

---

### 5.5 The pen is snapped relative to its rigid span

This is section 6.1's option, taken. It was a taste decision and the user made
it; the whole of 6.1 is the costing they were given, and 6.2 is what shipped.

`_RigidSpan` anchors a run of glyphs at its first glyph's snapped position and
places every later glyph in the run at `anchor + snap_px(offset)`. The offset is
taken in **scaled points** — `Scaled` is an `int`, so the difference is exact —
and converted to pixels once, rather than converting both coordinates and
subtracting, which is two float roundings and could disagree with itself either
side of a `.5` boundary. `origin` cancels out of the offset entirely, so a window
scrolled to a fractional position cannot reshape a word.

**The unit is the maximal rigid span, not the word**, and that is not a rename.
Measured on `demo/sample.md`: 876 spans, of which **4 contain literal space
characters** — the indentation inside a fenced code block, where a space is a
rigid `CharNode` rather than glue — and **20 span more than one face**, because
`**bold**text` abutted with no space is one run. Splitting a string on spaces
gets both wrong. The span is opened at a `Glyph` that follows something other
than a `Glyph` and dropped at the next `SetGlue`, `Line` or `RuleRect`.

Rigid is TeX's own structure rather than an observation about this document. In
`hlist_out` a char node advances the pen by nothing but its width —

```
cur_h:=cur_h+char_width(f)(char_info(f)(c));
```

— §620, `tex.web` line 12375 — while the only place set glue enters the pen is

```
      cur_glue:=cur_glue+stretch(g);
      vet_glue(float(glue_set(this_box))*cur_glue);
      cur_g:=round(glue_temp);
```

under `Move right or output leaders`, reached for a glue node and no other —
§625, `tex.web` lines 12431-12459. So the scaled-point difference between two
glyphs of one span is a function of the characters, their kerns and their sizes,
and of nothing about where the line broke.

Both section numbers were checked against `docs/tex.web` by content and by the
`@*` / `@ ` / bare `@` counting method `docs/tex-notes.md` records, because that
file warns its numbering was only spot-checked; the same count reproduces §616
for `synch_h` (3.2) and §108 for `badness`. `docs/tex-notes.md` C3 concerns the
rounding *inside* §625 and is the same principle one layer down: TeX rounds at
glue nodes. Per-glyph rounding rounds at nodes TeX treats as rigid, and this
does not.

**Two roundings, and two is the bound.** The anchor is snapped once and the
offset once, so the worst departure is under 1 px and — this is the part that
matters — it does not grow with the length of the span or of the line. That is
what separates it from rounding advances and summing them, which is unbounded
(5.3). `snap_px`'s docstring used to say "absolute positions only"; the true
rule is *nothing snapped is ever accumulated*, which is narrower and is what
5.3's measurement actually shows.

---

## 6. What this does not fix

**Interletter gaps are still quantised to whole pixels.** That is inherent to 3.2 and is the
price of the choice. Fixing it needs per-phase bitmaps, which ImGui cannot store (4.1), or
fractional placement, which the user excluded (4.2). If the demo is ever run on a
high-density display the problem shrinks proportionally and none of this matters.

> **Superseded by 6.3: gaps are quantised to *half* pixels now, not whole ones.** The
> mechanism stated above is right and the remedies listed are still unavailable — there are
> still no per-phase bitmaps and the pen is still on a grid — but the grid is finer. The
> mean error between a rendered inter-letter gap and the gap the design asks for is 0.1433
> px where this paragraph was written against 0.2517 px. 6.3 has the measurement and the
> cost.

**The user's "crowded" complaint is at least partly a different bug.** T14-tolerance
measured the two words the user pointed at — "people" and "counting" — and found they sit
on lines with `glue_set` 3.103 and 1.993, i.e. interword glue stretched to three times its
natural stretch limit, with 39 of 144 lines past natural stretch. Its holder measured no
ink difference on those words at all. **Those words look wrong because the spaces around
them are enormous, not because the glyphs are.** This document fixes the rendering; it does
not fix the breaking tolerance, and if the demo still reads badly after both land, the
tolerance is the place to look.

**Nothing here improves vertical rhythm.** Baselines are snapped, which means the space
between two baselines can differ by a pixel between lines. The same argument as for
interletter gaps applies and the same remedies are unavailable.

### 6.1 The one remaining option, costed — the decision, and who made it

**This section is the costing. Section 6.2 is what the user decided and what it measured
at once implemented; read them together.** It is kept in its original form because a
decision is only as good as the numbers it was made on, and those numbers are here.

The lead proposed, and measured the premise for, a variant worth recording precisely
because it is the only thing left that would help and it is a **taste trade rather than a
correctness one**. Their premise checks out: a word is rigid in layout space — TeX makes
glue the only elastic node and it sits *between* words — so quantisation error could be
pushed into interword space, which is already absorbing justification stretch anyway.

Concretely: snap the word's origin, then snap each glyph's offset *from that origin*
rather than its absolute position. The gap sequence inside a word then depends only on
the letters, never on where the word happens to fall, so every instance of a word is
pixel-identical.

Measured over `demo/sample.md` at a 700 px measure — 876 words, 496 distinct
(word, face) keys:

| | what shipped (round absolute) | word-relative |
|---|---:|---:|
| worst glyph displacement | 0.500 px | **0.986 px** |
| word keys drawn at more than one shape | **66 of 496** | 0 of 496 |
| worst error on the last glyph of a line | 0.489 px | **0.791 px** |

So it works — 66 word keys currently render at two or more distinct shapes and that goes
to zero — and it costs a doubling of worst-case glyph displacement, and it moves the
*rendered* right edge of a justified line from within half a pixel of the computed one to
within eight tenths.

**It was not taken in that pass.** `docs/status.md` section 1 makes the exact right margin
this project's flagship evidence, and trading fidelity to it for intra-word consistency is
precisely the kind of decision `docs/status.md` section 4 says an agent should not make
alone. The numbers above are what that decision needed; the change would live in `draw`'s
command loop, which would have to become word-aware — a run of `Glyph` uninterrupted by
`SetGlue` or `Line` is already exactly a word.

Note also what it does **not** buy: the gaps are still quantised to whole pixels. It makes
the quantisation *consistent*, which is the evenness argument in 3.1 and section 6's
citation of Larson, not *finer*. The same word set twice at different origins goes from
two spellings to one; it does not get its 1.4 px gap back. That is still true.

### 6.2 Taken — the decision, and the numbers once it was implemented

The lead put 6.1 to the user. Their answer, verbatim:

> "I think I would take a little more rag on the right justification line if the text
> looks better."

So it shipped, as `_RigidSpan` (5.5). Everything below was re-measured against the
implementation rather than carried over from the projection.

| | absolute (5.2) | span-relative (5.5) | 6.1 projected |
|---|---:|---:|---:|
| worst glyph departure, over 4329 drawn glyphs | 0.500 px | **0.986 px** | 0.986 px |
| spans drawn at more than one shape | **67 of 496** | 0 of 496 | 66 of 496 |
| worst departure on the last glyph of a line | 0.484 px | **0.859 px** | 0.791 px |
| glyphs displaced more than half a pixel | 0 | 800 of 4329 | — |

The two disagreements with 6.1 are small and are recorded rather than smoothed over: 67
against 66 two-shaped spans, and 0.859 against 0.791 px on the line-end. Both are
sensitive to the screen origin the measurement is taken at, which 6.1 does not state; the
876 spans and 496 distinct keys reproduce exactly. The worst glyph departure of 0.986 px
reproduces to three decimal places, which is the number the trade was made on.

**The null result in 6.1 is now overturned, and it is the whole point.** "The same word
rendered at several x positions produces identical pixel runs" was false before and is
true now. Four distinct inter-letter gap sequences for "line" across sixteen sub-pixel
origins — `(3,4,7)`, `(4,3,7)`, `(4,3,8)`, `(4,4,7)` — became one, which
`test_a_span_moved_by_a_fraction_of_a_pixel_keeps_its_shape` asserts.

**Confirmed in composited pixels, not only in the vertex buffer.** Two screenshots of the
Document tab at 1400x900, segmenting the sheet into words by ink columns and tight-cropping
each to its own ink box:

| | absolute | span-relative |
|---|---:|---:|
| words with a byte-identical twin elsewhere on the page | 111 | **145** |
| distinct renderings among same-sized words | 148 | **120** |

`artifacts/t19-word-compare.png` is the picture: "breaking", magnified 8x, at two shapes
on the left and three identical instances on the right. The `make shot` reproduction is in
section 8.

**What the accepted rag actually costs on screen, which is less than the trade implied.**
The Columns tab at 1400x900, two columns, shot with and without 5.5, taking the rightmost
ink column of every line of the first column: the right edge moves by **exactly ±1 px on
7 of 30 lines** and the total spread over the 25 justified lines is **2 px either way,
unchanged**. The user was told they were buying intra-word consistency with visible rag;
on this page they are getting the consistency and paying nothing visible for it. That is
one page and not a proof, and the pen-position numbers in the table above are the durable
claim — but it is worth recording that 0.86 px of pen error is not 0.86 px of ragged edge,
because the last glyph's own right side bearing already quantises the ink.

**T11's own result is not regressed.** Over the whole sheet rather than 5.2's one band:
solid ink 7035 → 14711 and midtone-to-solid 7.46 → 3.03 at the resampling fix, and
14711 / 3.03 unchanged after this change. Span snapping moves glyphs; it does not resample
them.

### 6.3 Taken again — the offset inside a span is quantised to half a pixel

6.2 made every instance of a word identical. It did not make any *gap* finer: the offsets
inside a span were still whole pixels, so a designed gap of 5.30 px was still drawn at
5 or 6 and the first paragraph of section 6 still stood. This is the change that halves
that error, and it is the second taste trade the user made on this subject.

#### What changed, and the one line that makes the rest of it real

Three things in `advtext/backends/imgui_draw.py`, all at draw time:

| | |
|---|---|
| `PEN_QUANTUM_PX = 0.5` | the grid a glyph's offset *inside* its rigid span is taken to |
| `snap_offset_px(v)` | `snap_px` generalised to that quantum, same half-up rule, so at a quantum of 1.0 it *is* `snap_px` |
| `ImDrawListFlags_TextNoPixelSnap` | set by `draw` around its command loop and restored after |

`_RigidSpan.pen` now returns `self.left + snap_offset_px(dx), self.top + snap_px(dy)`. The
anchor is unchanged, `_snap_span` is unchanged, and no file outside this module was
touched.

**The flag is load-bearing and its absence has no symptom.** `ImFont::RenderText` opens
with `IM_TRUNC(pos.x)` (2.2), so without it every half-pixel computed here is rounded back
to a whole one inside ImGui: positions stay integral, one texel still maps to one pixel,
spans still draw at one shape, and the change is a silent no-op that looks exactly like a
revert. Measured on this build, a glyph asked for at x = 100.5 emits its quad at 101.0 with
the flag clear and 101.5 with it set;
`test_a_half_pixel_pen_survives_into_the_vertex_buffer` asserts both halves, and
`test_every_glyph_of_the_demo_document_lands_on_the_half_pixel_grid` carries a control
requiring a real share of the document to be at the *half* phase, because "a multiple of
0.5" is satisfied by every integer and would otherwise pass on a revert.

#### Who decided, on what evidence

The user, twice, with output in front of them.

**The quantum.** The lead rendered a ladder — 1/1, 1/2, 1/3, 1/4 — on the Columns tab and
put it up; `.concerns/T20-letterfit--lead--half-pixel-decided.md` §3 is that ladder.
**1/2 and 1/4 were indistinguishable to the eye**, and over the word "counting" the lead
measured `o`, `u` and `i` byte-identical between them, with only `n`, `t`, `n` differing
and in no consistent direction. **1/2 was chosen at equal appearance as the coarser of the
two**, because a coarser grid admits fewer distinct rasterisations of a letter. 1/3 was
rejected as worse on letter spacing at 16 px. Skia's 1/4 (3.1) is a *cache* bound and is
not authority for a number this project did not take.

**The shape of the implementation.** `artifacts/letterfit/INDEX.md` is the sample set the
user judged: five tabs, full pages at 1:1 plus paired strips at 2x and 6x, A = whole-pixel
above, B = half-offsets below, shot from one verified build. That sample set is exactly
reproducible from the working tree — section 8 gives the two commands and the two md5s —
which is unusual enough in this tree to be worth stating.

#### Why the offset and not the anchor

An earlier trial quantised the span **anchor** to halves as well. The user rejected it on
sight:

> "it really breaks with the 'W' being completely fuzzed while the 'h' looks pixel perfect"

The leading glyph of every word was landing on a coin-flip between two phases, which is
where the eye is best able to see it. Keeping the anchor on a whole pixel means the first
glyph of every word is drawn exactly where 6.2 drew it, at exactly one phase, and only the
letters behind it can move by a half. Measured over `demo/sample.md` at a 700 px measure:
**873 anchors drawn, 0 at a fractional x**, against **1444 of 3456 non-anchor glyphs at the
half phase**. `test_the_first_glyph_of_every_span_is_drawn_on_a_whole_pixel` asserts both
sides, the second being the control that distinguishes a whole *anchor* from a whole
*everything*.

This is also why the lead's own trial must not be copied: it patched `snap_px` globally,
which quantises the anchor and unsnaps rules and highlights too. 5.4 and T19 are why that
is wrong for an area, and the quote above is why it is wrong for an anchor.

#### Why horizontal only

The defect the user reported and judged is horizontal. Inter-letter gaps inside "people"
measured 1, 2, 2 px — `.concerns/lead--visual-standard.md`, **not re-derived here**, because
"people" occurs in `demo/columns.md` and not in `demo/sample.md`, which is the fixture every
pen figure in this section is taken on. The heading case is re-derived below: in "What the
difference looks like", `iffe` fused into a single 31 px ink run, in a row whose other runs
measure 3 to 21 px.

**Nothing comparable was ever reported vertically, and today the choice has no observable
consequence at all.** Measured over `demo/sample.md`: **3486 of 3486** within-span vertical
offsets are already a whole number of pixels, and 2 of 2 in the litmus formula — so the two
rules cannot disagree on anything the demo contains. 54 of those 3486 are non-zero, so this
is not the trivial claim that `dy` is always 0; it is that a mixed-face span and a math
script both happen to land on whole rows. The test that pins the axis asymmetry is
therefore a synthetic raised glyph,
`test_a_vertical_offset_inside_a_span_stays_on_a_whole_row`, and not the document: swapping
`snap_px` for `snap_offset_px` on the vertical leaves every document-driven assertion in
the file green.

#### What it buys, in offsets

Both rules applied to the same exact pen positions, in one process, over the 3453 adjacent
within-span glyph pairs of `demo/sample.md` at a 700 px measure:

| rendered gap against the gap the design asks for | whole (6.2) | half (6.3) |
|---|---:|---:|
| mean absolute error | 0.2517 px | **0.1433 px** |
| worst absolute error | 0.9766 px | **0.4766 px** |

1571 of the 3453 gaps change: 754 get wider, 817 get narrower. Of those, **1247 land nearer
the designed gap and 324 land further from it** — a quantiser applied to two positions and
then differenced is not monotone in the gap, so "further" is a real case and not a rounding
artefact.

The heading word the user named, in full. The distance from each glyph's pen to the next
one's, in pixels:

| | d→i | i→f | f→f | f→e | e→r | r→e | e→n | n→c | c→e |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| designed | 11.270 | 5.302 | 7.168 | 6.934 | 10.810 | 7.110 | 10.810 | 11.201 | 10.430 |
| whole | 11 | 6 | 7 | 7 | 10 | 8 | 10 | 12 | 10 |
| half | 11.5 | 5.0 | 7.0 | 7.0 | 11.0 | 7.0 | 11.0 | 11.0 | 10.5 |

Nearer in seven of the nine, identical in the other two, worse in none. The four that
whole-pixel snapping put more than three quarters of a pixel wrong — `e→r` and `e→n`, both
10.810 drawn at 10; `r→e`, 7.110 drawn at 8; `n→c`, 11.201 drawn at 12 — are all within
0.21 px of the designed distance under the half-pixel rule. This is the arithmetic only;
what the row looks like is the next part, and it is less tidy.

#### What it buys, in composited pixels — and the trap in measuring it

The heading band, located by content (`visual_diff.py crop --region "text:What the
difference looks like" --face prose-bold --size 20`), thresholding a pixel as ink below a
grey level and reading off the widths of the resulting ink runs:

| ink threshold | whole: runs, widest | half: runs, widest |
|---|---|---|
| grey < 200 | 18, **31 px** | 18, **24 px** |
| grey < 170 | 23, 19 px | 22, **24 px** |

The first row reproduces the lead's sequence exactly — `[17, 9, 17, 7, 9, 11, 10, 3, 31,
20, 21, …]`, the 31 px run — so threshold 200 is the one their measurement was taken at,
and at that threshold the widest run falls to 24 px.

**The second row is the important one and it points the other way.** At a tighter
threshold the half-pixel render has the *wider* widest run and one fewer run, because half
the glyphs are now resolved by the renderer's bilinear filter and the midtones between two
letters cross a tight threshold that they did not cross before.
`.concerns/lead--visual-standard.md` names this trap in so many words — "ink-threshold gap
measurements are not comparable across renders with different antialiasing" — and this is
it, measured, on the exact case the change was justified by. **No claim is made here that
the fusion is fixed.** What is established is that the ink in that row is differently
distributed and that a run-width metric on it is threshold-dependent; whether the heading
reads better is the user's call and nobody else's.

#### What it costs

**A letter can now have two rasterisations.** Whole-pixel snapping made every instance of a
letter byte-identical, which is not obvious and was rendered rather than argued:
`artifacts/gridfont/INDEX.md`, re-derived here by
`scripts/render_grid_compare.py --report`, finds **zero** letters with more than one
rendering in *any* whole-pixel case, and at 1/2 exactly two phases, 0 and ½:

| case | letters with more than one rendering, over three samples |
|---|---:|
| Roboto 16 px (ships today), half | 7 |
| Roboto 18 px, half | 7 |
| Liberation Serif 18 px, half | 2 |
| Nimbus Roman 18 px, half | 3 (`INDEX.md` says 7 — see below) |
| Inconsolata 16 px (on-grid control), half | 0 |
| any face, whole | 0 |

**Softness, over the whole sheet.** The Document tab at 1400x1000, 6.2's band
`y = 92..888, x = 346..1043`, section 8's ink statistic:

| | whole | half |
|---|---:|---:|
| solid ink px | **14711** | 11792 |
| midtone px | 44530 | 51883 |
| midtone-to-solid | **3.03** | **4.40** |
| solid share of inked px | 22.9% | 17.3% |

The 14711 and the 3.03 are 6.2's own figures, reproduced to the pixel, so the two columns
are the same statistic. 31591 of the 1400000 pixels on the page differ at all between the
two renders and 21685 differ by more than 32 grey levels — 2.3% and 1.5% of the page. Which
direction that is an improvement in is not a question this document answers; 3.1 and 3.3
are the two schools and they disagree.

#### The error bound, checked

`snap_px`'s docstring now argues one whole-pixel rounding of the anchor plus one
half-pixel rounding of the offset, 0.75 px worst, not growing with the span or the line.
**The arithmetic holds**: the anchor rounding is bounded by 0.5 px and the offset rounding
by `PEN_QUANTUM_PX / 2` = 0.25 px, and the two simply add, because the offset is taken
against the anchor's exact scaled-point position and not against the snapped one — so the
anchor's error is carried into the result once and is never itself re-rounded. Measured
over the 4329 drawn glyphs of `demo/sample.md`, worst departure **0.736979 px**, which is
under the bound and close enough to it that the bound is not slack:

| | absolute (5.2) | span-relative, whole (6.2) | span-relative, half (6.3) |
|---|---:|---:|---:|
| bound | 0.5 px | 1.0 px | **0.75 px** |
| worst departure, 4329 glyphs | 0.499997 px | 0.997569 px | **0.736979 px** |
| glyphs displaced more than half a pixel | 0 | 840 | **454** |
| worst on the last glyph of a line, 73 lines | 0.488261 px | 0.986182 px | **0.599980 px** |
| span keys drawn at more than one shape | 70 of 496 | 0 of 496 | **0 of 496** |

**All three columns were re-derived here, in one process, from the same exact pen
positions**, which is why this table disagrees in the third decimal with 6.2's and in whole
counts with 6.1's: 70 two-shaped spans where 6.2 recorded 67 and 6.1 projected 66, and 840
glyphs past half a pixel where 6.2 recorded 800. Only the half-pixel column can be checked
against the live vertex buffer, and it is — 0.736979 to six decimals. The other two are
simulations of rules no longer in the tree, and the last part of this section says what that
does and does not license.

So 6.3 gives back a quarter of a pixel of the fidelity 6.2 spent, and halves the number of
glyphs that move more than half a pixel, while keeping 6.2's whole point: 876 spans, 496
distinct keys, none drawn at two shapes.

#### Two figures in 6.2 that no longer reproduce, and one in `artifacts/`

Recorded rather than smoothed over, because `docs/status.md` Provenance treats an
unre-derivable number as this project's most common defect.

- **6.2's 0.986 px worst departure, 0.859 px line-end, 800 displaced glyphs and 67
  two-shaped spans.** Re-running those rules against today's `demo/sample.md` gives
  **0.997569**, **0.986182**, **840** and **70**. The method is in section 8 and it is
  validated where it can be: the same code path reproduces the *half*-pixel figure to six
  decimals against the live vertex buffer, and the 876 spans and 496 distinct keys
  reproduce exactly. The likely cause is that the document has grown since 6.2 was
  measured — 6.2 itself warns its figures are sensitive to the screen origin, and
  `ORIGIN_X` is now pinned at 40.25 where 6.2 does not say what it used. 6.2's numbers are
  left as written because they are what that decision was made on; the table above is a
  re-derivation and is the one to quote.
  `tests/test_imgui_draw.py::test_no_glyph_of_the_demo_document_is_drawn_more_than_a_pixel_from_its_position`
  still says "Measured: 0.9862 px worst" in its docstring and now measures 0.737; that file
  is not this one's to edit and the lead has been told.
- **`artifacts/gridfont/INDEX.md`'s Nimbus Roman row.** It records 7 letters with more than
  one rendering at half-pixel; re-running its own generator gives **3** (`'e'` and `'s'` in
  "counting the spaces", `'e'` in "people of difference"). The run is deterministic —
  two invocations produced identical reports — so the disagreement is with the recorded
  figure and not with the harness. Every other row of that table reproduces exactly. The
  claim the table is quoted for here is the whole-pixel row, which is 0 everywhere, and
  that reproduces.
- **The ladder's absolute ink shares.** The concern's 1/1 row reads 47.3% solid / 41.3%
  midtone; re-shooting the Columns tab at four quanta and measuring the same line with
  section 8's statistic gives 16.3% / 76.4% at 1/1, 12.1% / 82.2% at 1/2, 10.9% / 83.3% at
  1/3 and 10.3% / 83.9% at 1/4. The *direction* reproduces and is monotone in the quantum;
  the absolute values do not, and two reasons are visible without guessing: the concern
  does not state its region or its normalisation, and its trial patched `snap_px` globally,
  so its 1/2, 1/3 and 1/4 rows were rendered by an implementation that also quantised the
  anchor — the variant the user went on to reject. **The ladder is therefore evidence about
  what the user was shown, not a measurement of what shipped.** What shipped was judged on
  `artifacts/letterfit`, which does reproduce.

---

## 7. Two claims this work started from that are wrong

Recorded because `docs/status.md`'s Provenance section treats an unre-derivable figure as
this project's most common defect, and a refuted premise left standing is worse.

**"Stem weights vary between instances of the same letter."** Refuted. The phase a glyph is
drawn at is a deterministic function of its `X0` and the scale, both constant for a given
(face, size, codepoint). Measured across `demo/sample.md`, all 143 distinct (font key,
codepoint) pairs drew at exactly **one** phase each, before the fix as well as after. The
two `t`s in "test" were byte-identical. What does vary is the phase *between different
letters*, which makes one letter's stems heavier than another's — a real defect, and not
the one that was described.

**"The text is already crisp, because RenderText truncates the pen position."** Half right.
The truncation is real (2.2) and it does mean the pen contributes no blur. The conclusion
does not follow, because the size quantisation (2.3) reintroduces a fractional quad
position and a fractional quad *size*, and 100% of glyph quads were resampled. The
before/after crops in `artifacts/` show the difference plainly.

Two further corrections belong to files this task does not own and have been sent to the
lead: `docs/imgui-risks.md` item 2 blames the fractional `origin` from
`get_cursor_screen_pos()`, which is not the mechanism; and `docs/decisions.md` section 5
says "Rounding to the pixel grid happens **exactly once**, on a final absolute coordinate",
which before this change happened **zero** times in our code and once, by truncation,
inside ImGui. After this change the sentence is true.

---

## 8. Reproducing every number here

```sh
# Screenshots, before and after any change to advtext/backends/imgui_draw.py
make shot ARGS="--tab document --width 1400 --height 900 --out artifacts/doc.png"

# 5.4's rules. Tall enough to reach demo/sample.md's blockquote bar and its
# thematic break; the window manager clamps the height, and says so.
make shot ARGS="--tab document --width 1100 --height 1600 --out artifacts/rules.png"

# The quad measurements, the phase census, the drift table and 5.5's span claims
.venv/bin/python -m pytest tests/test_imgui_draw.py -q

# 6.3's A/B pair. The first is the shipped build; the second is the same build
# with the quantum forced back to a whole pixel, which needs no edit to
# advtext/ because `snap_offset_px` reads PEN_QUANTUM_PX on every call.
make shot ARGS="--tab document --width 1400 --height 1000 --out artifacts/doc-half.png"
PYTHONPATH=. .venv/bin/python -c "import runpy, sys; \
from advtext.backends import imgui_draw; imgui_draw.PEN_QUANTUM_PX = 1.0; \
sys.argv = ['shot.py', '--tab', 'document', '--width', '1400', '--height', '1000', \
'--out', 'artifacts/doc-whole.png']; \
runpy.run_path('scripts/shot.py', run_name='__main__')"

# 6.3's cost table. Re-renders artifacts/gridfont and reprints its identity report.
.venv/bin/python scripts/render_grid_compare.py --zoom 6 --report

# 6.3's heading band, located by content rather than by coordinate
.venv/bin/python scripts/visual_diff.py crop artifacts/doc-half.png \
  --region "text:What the difference looks like" --face prose-bold --size 20 \
  --out artifacts/heading.png --zoom 6
```

**Those two shots are byte-identical to `artifacts/letterfit`'s** — md5
`cff5cd513abcb283eede5db5c5f74641` for B/half and `3656d37bc8f7e67145b24254f3d31184` for
A/whole, against `document--B-variant-halfoffsets.png` and
`document--A-current-wholepixel.png`. That is the check worth doing first if any 6.3 number
disagrees, because it establishes that the sample set the user judged and the working tree
are the same thing. `--height 1600` is clamped by the window manager to 1007 on this
machine and says so, so 1000 is the honest number to ask for.

6.3's pen, offset, phase and gap figures — 876 spans, 4329 drawn glyphs, 0.736979 px worst,
873 whole anchors, 1444 half-phase glyphs, 3486 of 3486 whole vertical offsets, the two
simulated columns of its bound table and the 3453 gap errors — all come out of one script
that drives `tests/test_imgui_draw.py`'s own `_drawn`, `_spans`, `_visible` and `_anchor_of`
helpers rather than reimplementing them, so a change of unit inside `_RigidSpan` shows up as
a disagreement. It is reproduced in full in this section's appendix below.

The assertions in `tests/test_imgui_draw.py` carry the measurements:

| number in this document | test that pins it |
|---|---|
| 0 quads off the half-pixel grid | `test_every_glyph_of_the_demo_document_lands_on_the_half_pixel_grid` |
| 0 quads resampled | `test_no_glyph_of_the_demo_document_is_resampled` |
| `floor(size + 0.5)` bake rule | `test_the_size_imgui_is_asked_for_is_the_size_it_would_have_baked` |
| same raster at 18.75 and 19.0 | `test_asking_for_the_rounded_size_selects_the_same_raster` |
| 0.5 px worst departure | `test_snapping_an_absolute_position_can_never_be_more_than_half_a_pixel_out` |
| 9.9 px advance-rounding drift | `test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin` |
| truncation bias, both axes | `test_a_glyph_goes_to_the_nearer_pixel_and_not_always_the_one_below` |
| hairline survives snapping | `test_a_rule_too_thin_for_the_pixel_grid_keeps_a_pixel` |
| 0.986 px worst departure under 5.5 | `test_no_glyph_of_the_demo_document_is_drawn_more_than_a_pixel_from_its_position` |
| 0 of 496 spans at two shapes, against 67 | `test_every_instance_of_a_rigid_span_is_drawn_at_the_same_shape` |
| one gap sequence for "line" across a pixel | `test_a_span_moved_by_a_fraction_of_a_pixel_keeps_its_shape` |
| the unit is the rigid span, not the word | `test_a_space_inside_a_run_does_not_end_the_span` |
| glue, `Line` and `RuleRect` each end it | `test_anything_that_is_not_a_glyph_ends_the_span` |
| a glyph with no raster does not | `test_a_glyph_the_face_cannot_raster_does_not_end_the_span` |
| 6.3: `snap_offset_px` agrees with `snap_px` on boundaries | `test_snap_offset_px_is_snap_px_on_a_finer_grid` |
| 6.3: the flag is what lets a half reach the buffer | `test_a_half_pixel_pen_survives_into_the_vertex_buffer` |
| 6.3: 0 of 873 span anchors at a fractional x | `test_the_first_glyph_of_every_span_is_drawn_on_a_whole_pixel` |
| 6.3: the quantum is horizontal only | `test_a_vertical_offset_inside_a_span_stays_on_a_whole_row` |
| 6.3: every vertical quad edge on a whole row | `test_a_glyph_sits_on_a_whole_pixel_row` |

Four of those are new with 5.5 and the two-shapes one carries its own control: it builds
the absolute-snapping implementation alongside and asserts that *it* produces more than
thirty two-shaped spans on the same fixture, so the claim cannot pass on a document where
no span occurs twice. Reverting 5.5 in full turns eight tests in the file red.

**Five more are new with 6.3, and three of them are controls rather than assertions**,
because a finer grid is a *weaker* predicate than a coarser one and every 6.3 test had to be
written against that. "A multiple of 0.5" is true of every integer, "y is a whole number" is
true when the horizontal quantum has been dropped altogether, and "no anchor is fractional"
is true when nothing at all is fractional. Each of those three is paired with an assertion
that some real share of the same buffer *is* at the half phase. Dropping
`ImDrawListFlags_TextNoPixelSnap` from `draw` leaves the naive half of each green and turns
the controls red, which is the failure mode 6.3 exists to keep visible.

**The measurement `_drawn` performs is the load-bearing part and it is easy to get wrong.**
It draws one shipped line per `draw` call, each at a y inside the viewport, because the
background draw list clips to `io.display_size` and a clipped glyph appends no vertices:
drawing the whole document in one call pairs the first 1589 quads with the right commands
and then silently runs out. Splitting at `Line` changes no geometry, since `draw` drops its
span there anyway.

The ink counts in section 1 come from two screenshots of the Document tab at 1400x900,
taking the band `y = 163..183, x = 459..930`, normalising coverage against the
95th-percentile paper value, and counting pixels above 0.9 coverage (solid) against those
between 0.15 and 0.85 (midtone). 6.2's are the same statistic over the whole sheet,
`y = 92..888, x = 346..1043`, because that band happens to contain no glyph 5.5 moved —
a reminder that a band chosen once is not a sample. They are not asserted in a test: a
framebuffer composite needs a display, and `tests/` must run without one.

**6.3's are the same statistic again, and it is now implemented once rather than described
three times.** `scripts/visual_diff.py`'s `ink_profile` takes its definition from this
section verbatim, so `from visual_diff import read_png, ink_profile` reproduces 6.3's
solid/midtone table over any band — and reproduces 6.2's own 14711 solid px and 3.03
midtone-to-solid on the whole-pixel page to the pixel, which is what licenses putting the
two columns beside each other. 6.3's heading run-widths are a different and cruder statistic
on purpose: threshold the located band at a grey level, take the widths of the maximal runs
of inked columns. 6.3 reports it at two thresholds because it reverses between them, and
that reversal is the finding rather than a footnote to it.

6.2's word-duplication counts come from the same two shots: threshold the sheet at grey
170, split each row of ink into words at gaps wider than 2 px, crop each word tight to its
own ink box so a one-pixel baseline shift does not count as a difference, and compare the
byte strings. The tight crop is what makes it a claim about the *shape* of a word rather
than about where it landed.

`artifacts/` is gitignored, so the before-and-after crops are not in the repository and
the "before" one cannot be retaken without reverting section 5's two changes. The
vertex-buffer numbers are the durable evidence and they are all in the tests above; the
pictures were how the defect was *found*, which is a different job from proving it. If
you want to see it again, revert `_baked` to pass `size_px` instead of `baked.size`,
shoot the Document tab, restore, shoot again, and magnify the same band of both with
nearest-neighbour upscaling — the stems go from two-pixel grey smears to single solid
columns.

### 8.1 The script that produces 6.3's pen figures

Run from the repository root. It needs no display: a frame is not a window (the head of
`tests/test_imgui_draw.py` says why). It prints every number in 6.3 that is not a
screenshot statistic, and it takes about as long as composing the demo document once.

```sh
.venv/bin/python - <<'PY'
import sys
sys.path[:0] = [".", "tests"]
from imgui_bundle import imgui
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1024.0, 768.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

import test_imgui_draw as T
from advtext import fontlib
from advtext.fontmetrics import Face
from advtext.style import parse_font_key
from advtext.units import px_from_sp
from advtext.backends.imgui_draw import baked_size_px, snap_px, snap_offset_px

faces = {f: io.fonts.add_font_from_file_ttf(str(fontlib.imgui_font_file(f)), T.DISPLAY_SIZE_PX)
         for f in Face}
imgui.new_frame()
frame = imgui.get_background_draw_list()
cmds = T._demo_commands()
spans = T._spans(cmds)
print("spans", len(spans))


def ascent(cmd):
    """ImGui's baked ascent for a command, or None if the face cannot raster it."""
    spec = parse_font_key(cmd.font)
    font = faces[spec.face]
    if not font.is_glyph_in_font(cmd.codepoint):
        return None
    ours = fontlib.metrics(spec.face, 16.0)
    size = baked_size_px(px_from_sp(spec.size), ours.ascent, ours.descent, ours.em)
    return font.get_font_baked(size).ascent


# 1. what the shipped code puts in the vertex buffer
paired = T._drawn(frame, faces.get, cmds)
dep = [abs((qx - T._visible(faces.get, c)[1].x0) - (T.ORIGIN_X + px_from_sp(c.x)))
       for c, _oy, qx, _qy in paired]
print("drawn %d  worst %.6f px  over half a pixel %d"
      % (len(dep), max(dep), sum(d > 0.5 for d in dep)))
pen = {id(c): qx - T._visible(faces.get, c)[1].x0 for c, _oy, qx, _qy in paired}
anchors, inside = [], []
for span in spans:
    a = T._anchor_of(faces.get, span)
    for c in span:
        if id(c) in pen:
            (anchors if c is a else inside).append(pen[id(c)])
print("anchors %d, fractional %d | inside %d, at the half phase %d"
      % (len(anchors), sum(p != int(p) for p in anchors),
         len(inside), sum(p != int(p) for p in inside)))

# 2. the vertical axis, over every glyph the face can raster
whole_rows = rows = 0
for span in spans:
    anchor = None
    for cmd in span:
        asc = ascent(cmd)
        if asc is None:
            continue
        if anchor is None:
            anchor = (cmd.y, asc)
            continue
        dy = px_from_sp(cmd.y - anchor[0]) - (asc - anchor[1])
        rows += 1
        whole_rows += dy == int(dy)
print("within-span vertical offsets on a whole row: %d of %d" % (whole_rows, rows))

# 3. the two quanta on the same pens, which is the only honest before/after now
worst = {"whole": [], "half": []}
shapes = {"whole": {}, "half": {}}
gaps = {"whole": [], "half": [], "exact": []}
for span in spans:
    vis = [c for c in span if T._visible(faces.get, c) is not None]
    anchor = T._anchor_of(faces.get, span)
    if not vis or anchor is None:
        continue
    left = snap_px(T.ORIGIN_X + px_from_sp(anchor.x))
    key = ("".join(chr(c.codepoint) for c in span), tuple(c.font for c in span))
    for name, rule in (("whole", snap_px), ("half", snap_offset_px)):
        at = [left + rule(px_from_sp(c.x - anchor.x)) for c in vis]
        worst[name] += [abs(p - (T.ORIGIN_X + px_from_sp(c.x))) for p, c in zip(at, vis)]
        shapes[name].setdefault(key, set()).add(tuple(round(p - left, 6) for p in at))
        gaps[name] += [b - a for a, b in zip(at, at[1:])]
    exact = [T.ORIGIN_X + px_from_sp(c.x) for c in vis]
    gaps["exact"] += [b - a for a, b in zip(exact, exact[1:])]
for name in ("whole", "half"):
    print("%-5s glyphs %d  worst %.6f px  span keys %d  drawn at two shapes %d"
          % (name, len(worst[name]), max(worst[name]), len(shapes[name]),
             sum(len(v) > 1 for v in shapes[name].values())))
ew = [abs(w - e) for w, e in zip(gaps["whole"], gaps["exact"])]
eh = [abs(h - e) for h, e in zip(gaps["half"], gaps["exact"])]
print("adjacent pairs %d | rendered gap vs designed gap, mean error: whole %.4f, half %.4f"
      % (len(ew), sum(ew) / len(ew), sum(eh) / len(eh)))
print("                | worst error: whole %.4f, half %.4f" % (max(ew), max(eh)))
print("gaps that changed %d | half nearer the design %d | whole nearer %d"
      % (sum(w != h for w, h in zip(gaps["whole"], gaps["half"])),
         sum(b < a - 1e-12 for a, b in zip(ew, eh)),
         sum(a < b - 1e-12 for a, b in zip(ew, eh))))
imgui.render()
PY
```

It printed, on the working tree this was written against:

```
spans 876
drawn 4329  worst 0.736979 px  over half a pixel 454
anchors 873, fractional 0 | inside 3456, at the half phase 1444
within-span vertical offsets on a whole row: 3486 of 3486
whole glyphs 4329  worst 0.997569 px  span keys 496  drawn at two shapes 0
half  glyphs 4329  worst 0.736979 px  span keys 496  drawn at two shapes 0
adjacent pairs 3453 | rendered gap vs designed gap, mean error: whole 0.2517, half 0.1433
                | worst error: whole 0.9766, half 0.4766
gaps that changed 1571 | half nearer the design 1247 | whole nearer 324
```

**`half ... worst 0.736979` and the vertex-buffer line above it agree to six decimals, and
that agreement is the point of printing both.** The `whole` row of the same table is a
simulation of a rule that is no longer in the tree; the only reason to believe it is that
the identical code path, fed the other quantum, reproduces what the live buffer contains.
The absolute-snapping figures in 6.3's bound table (0.499997 px, 70 of 496) come from the
same script with `left` replaced by `snap_px(T.ORIGIN_X + px_from_sp(c.x))` per glyph, which
is 5.2's rule and is also what
`test_every_instance_of_a_rigid_span_is_drawn_at_the_same_shape` builds as its control.

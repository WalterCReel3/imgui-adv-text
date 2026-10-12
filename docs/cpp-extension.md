# A C++ ImGui extension: notes

> **2026-10-12:** the package this document calls `advtext` was renamed `imscribe` (`advtext/…` is `imscribe/…`, `import advtext` is `import imscribe`). Nothing below was changed for it.

**Status: a design note from a conversation. Nothing is committed, nothing is
implemented, and no decision has been taken.** It is written down because the
reasoning turned on one verifiable finding that would otherwise be re-derived
from scratch next time, and because two of the conclusions reverse what seemed
obvious at the start.

**Revised 2026-10-08**, against the tree after the adoption-and-demo merge
(`32e3953`) and against ImGui's own source, which the first version did not
have. The conclusion did not move. What did: the probe in §2 looked in the wrong
namespace, the rasteriser this build uses is FreeType and not stb_truetype, the
timings in §3 predate the memo they recommend, and §4 never said where the port
stops. Where a sentence below says *read*, it was read from
`ocornut/imgui` at tag `v1.92.9` (the ImGui inside imgui-bundle 1.92.900) or at
`master` on that date; where it says *measured*, it was run here against the
installed binding.

## 1. The scope, which is narrower than it first sounds

Not a general-purpose text engine. **An extension that ties into ImGui
specifically, with language bindings layered on top of ImGui only** — the
`implot` shape: C++ over ImGui, then bindings. Not over `imgui.h` alone, though:
the font loader §2 turns on is declared in `imgui_internal.h`, and §8 is about
what that costs.

That narrowing is load-bearing and it resolves the strongest objection to the
whole idea. This project's most valuable content is not the TeX algorithms, which
are published and studied. It is the device-space decisions in
`advtext/backends/imgui_draw.py`, and every one of them is specific to ImGui's
rasteriser: `baked_size_px` exists because ImGui's font loader sizes a face by
pixel height and not by its em, `snap_px` matches `IM_ROUND` so we agree with
ImGui about which pixel a coordinate is on, and the advance rule
(`docs/advance-rule.md`) was chosen against ImGui's own behaviour read out of its
vertex buffer.

**Which rasteriser that is was assumed and is now measured.** This note and
several docstrings say stb_truetype. In a bare context with this build,
`io.fonts.font_loader_name` reads `FreeType (2.13.3; 2.13.3)` after the first
frame, and `ImFontAtlasBuildInit` selects FreeType whenever it is compiled in
(read). It was not checked under the demo's own runner. Nothing measured in this
project is invalidated by that — the measurements were of whatever was active —
but every *explanation* that names stb_truetype is naming the loader that is
not running.

A renderer-agnostic port either abstracts those away and loses the precision, or
re-derives them per backend. An ImGui-only extension **carries all of them across
intact and still load-bearing**. Those are different products and only the second
one inherits the work.

## 2. The finding that actually decides it

Not performance. A capability that is structurally unreachable from Python.

ImGui 1.92 has a pluggable font loader. The Python binding exposes the setter and
the type, and **none of the type's hooks**:

    .venv/bin/python -c "
    from imgui_bundle import imgui
    a = imgui.ImFontAtlas()
    print('atlas loader API :', sorted(n for n in dir(a) if 'loader' in n))
    print('in imgui         :', [n for n in dir(imgui) if 'FontLoader' in n] or 'NOT EXPOSED')
    print('in imgui.internal:', [n for n in dir(imgui.internal) if 'FontLoader' in n] or 'NOT EXPOSED')
    print('ImFontLoader     :', sorted(n for n in dir(imgui.internal.ImFontLoader) if not n.startswith('_')))
    print('ImFont glyph API :', sorted(n for n in dir(imgui.ImFont) if 'glyph' in n.lower()))
    print('memory-font API  :', sorted(n for n in dir(a) if 'memory' in n) or 'NOT EXPOSED')
    "

prints, on imgui-bundle 1.92.900,

    atlas loader API : ['font_loader_data', 'font_loader_flags', 'font_loader_name', 'set_font_loader']
    in imgui         : NOT EXPOSED
    in imgui.internal: ['ImFontLoader']
    ImFontLoader     : ['font_baked_src_loader_data_size', 'name']
    ImFont glyph API : ['is_glyph_in_font', 'is_glyph_range_unused']
    memory-font API  : NOT EXPOSED

The first version of this note searched `dir(imgui)` only, printed `NOT EXPOSED`
and concluded the type was missing. It is not missing; it is in `imgui.internal`
with two data members. The conclusion survives the correction and is now better
founded: a loader *is* its function pointers, and the binding has none of them.

**What is measured**: that binding surface. **What is read**, from
`imgui_internal.h` at `v1.92.9`: the struct exists and is

    struct ImFontLoader
    {
        const char* Name;
        bool (*LoaderInit)(ImFontAtlas* atlas);
        void (*LoaderShutdown)(ImFontAtlas* atlas);
        bool (*FontSrcInit)(ImFontAtlas* atlas, ImFontConfig* src);
        void (*FontSrcDestroy)(ImFontAtlas* atlas, ImFontConfig* src);
        bool (*FontSrcContainsGlyph)(ImFontAtlas* atlas, ImFontConfig* src, ImWchar codepoint);
        bool (*FontBakedInit)(...);
        void (*FontBakedDestroy)(...);
        bool (*FontBakedLoadGlyph)(..., ImWchar codepoint, ImFontGlyph* out_glyph, float* out_advance_x);
        size_t FontBakedSrcLoaderDataSize;
    };

So the inference the first version asked to have confirmed is confirmed, with
one consequence it did not expect: **at the installed version the loader is asked
for a codepoint, not a glyph index.**

### What it would delete

`advtext/fontlib.py` (1137 lines) **rewrites font files on disk** — see
`imgui_font_file` and `_patched_font_directory`. It reads the font, writes our
synthetic private-use codepoints into every format-12 cmap subtable, and saves
the result into a temp directory that is deliberately never cleaned up, with a
documented silent-degradation path for fonts that have no format-12 subtable.

That exists for exactly one reason: **ImGui rasterises by codepoint, and math
variant glyphs often have no cmap entry.** `ImFont` gives Python
`is_glyph_in_font` and nothing that reaches a glyph index.

A custom `ImFontLoader` answers `FontBakedLoadGlyph` itself, so it can map our
private-use codepoint to a glyph index without the font file saying so. What
goes away is **the file rewriting and everything built around its cost**: the
cmap patch, the temp directory, the degradation path, and the lazy math-face
loading in `advtext/ui/fonts.py`, which exists because that one call costs about
a second (`docs/adoption-plan.md` records 1.06 s and 0.81 s) and since the merge
can be paid by a document with no formula in it.

What does **not** go away, at least while Python sits on top (§9 step 2): the
minting of synthetic codepoints. `fontlib.py` says why under "Synthetic
codepoints" — `CharNode`, `shipout.Glyph` and `FontMetrics` name a glyph by
codepoint and by nothing else, the SVG backend relies on it too, and the loader
hook is itself entered with a codepoint. The first version of this note said the
entire mechanism goes away, minting included. A full port could carry a glyph id
through its own node types and drop the minting; that is a property of step 3,
not of the loader.

That is still not a speedup. It is the removal of a workaround whose core — the
cmap rewrite — has no Python route. One part of it may have one: the temp
directory is there because `AddFontFromMemoryTTF` is unbound, and
`ImFontConfig.font_data` is bound. Whether bytes can be handed through it has not
been tried (§11).

### The hinting half is already reachable from Python

The first version called the loader "the same seam where FreeType hinting would
attach". With FreeType already the active loader (§1), that half of the argument
is gone: `ImFontConfig.font_loader_flags` is bound and takes
`ImGuiFreeTypeLoaderFlags_` values as plain integers. Measured, Roboto at 16 px
in a bare context, the width `calc_text_size` reports for *people*, *counting*
and *difference*:

    flags 0 (default hinting)   41, 55, 62
    flags 1 (NoHinting)         41, 53, 62
    flags 8 (LightHinting)      41, 54, 62

The flag changes what is baked. That is all this says; what any of the three
looks like, and whether one gives sharp stems and designed spacing together, is
`docs/guide/future.md` item 6 and is a question for an eye, not for this table.
It needs no C++.

## 3. Performance: real, measured, and not the reason

From the docstring of `scripts/bench_draw.py`, re-derivable by running the
benchmark. None of these was re-taken for this revision, and that docstring says
to read its milliseconds as an order of magnitude: the same code spread 22%
across four runs in twenty minutes.

- When this note was written, `demo/sample.md` cost **26 ms per frame against a
  16.7 ms budget** at best, with layout fully cached, and a culled frame 9.4 ms.
- The cheap fix this section used to recommend trying first — memoising the
  per-glyph preamble, item 2 in `docs/guide/future.md` — **was built on
  2026-10-06**. A full draw is now recorded at **15.9 ms, and 13.7 ms** on one
  later run; a culled draw at **5.9 and 5.1 ms**, flat however long the document
  gets.
- **ImGui's own work in that frame is 0.7–1.3 ms.** The rest is still Python,
  per glyph: `_glyph`, `_RigidSpan.pen`, the `draw_runs` loop, `snap_px`.
- Batching into fewer `add_text` calls prices at **0.03 ms against 1.3 ms** — it
  can only reclaim what ImGui was already doing cheaply.

So the honest test was run, and its answer is in between. The memo roughly
halved the frame. It did not make drawing in Python cheap: a full draw sits at
the budget rather than inside it, and nine tenths of what is left is the same
per-glyph loop. Whether that is enough depends on whose budget it is — one
document in one pane is comfortable when culled, and the one consumer
`docs/adoption-plan.md` names treats 1.7 ms a frame as too much for a live block
before any drawing.

**The structural point is that cost and complexity live in different places.**
The complex code — `linebreak.py` at 1004 lines, the math list, the column
splitter — runs once per reflow and is cached. The simple code, walking a flat
command list and emitting one quad per glyph, runs every frame across every
glyph on screen. So the case for native code is concentrated in the *least*
algorithmically risky part of the tree.

**Streaming is the exception, and it arrived after this was written.** A
`StreamView` parses, composes, ships and indexes as text arrives, so there the
complex code *is* on the per-frame path: `docs/adoption-plan.md` records about
1.4 to 2.2 ms per frame per view, not counting the draw. The same document
records costs that are neither per-frame nor cached and that a narrow draw port
would not touch: a find at 10 to 22 ms a keystroke, and a 50,000-line diff at
seconds, all of it `difflib`.

That still argues for a narrow port. It no longer argues that the narrow port
is the whole of the performance question.

## 4. Architecture: return vertices, not commands

`shipout.ship()` already produces a flat list of POD commands — `Glyph`,
`RuleRect`, `SetGlue`, `Line`. No pointers, no Python semantics. One subclass
since the merge: `Atom(SetGlue)`, which adds no field and is told apart by type,
so a C ABI wants it as a tag. That is still a clean boundary, and it fell out of
following TeX's `hlist_out` rather than from designing for one.

**There is a trap in the obvious design.** A C ABI that *returns a command list*
is maximally portable across bindings — and puts the per-glyph loop straight back
into the host language, so the Python binding would be no faster than today.

The resolution is to return **vertex data**. The extension does font binding,
placement and snapping, and hands back a filled vertex/index buffer, so a host
does one reserve and one copy instead of one interpreted iteration per glyph.
Portable *and* fast, and the device-space decisions stay on the native side
where they were measured.

Two things the first version did not know about that:

- **From Python the copy is not one copy.** The binding has `prim_reserve`,
  `prim_write_vtx`, `prim_write_idx` and `prim_vtx` (measured), each taking one
  vertex or one index. There is no bulk entry, so a Python host filling a draw
  list from a returned buffer is back to a loop. For a Python host the extension
  has to write into the `ImDrawList` itself, which a litgen binding (§6) allows
  and a plain C ABI to a non-C++ host does not.
- **The input is no longer just a command list.** The draw entry point is
  `draw_runs`, and besides commands it takes a per-run ink, fills, highlight
  rectangles and a palette; `draw` is a wrapper over it. Pen snapping depends on
  the screen origin and the views cull per frame, so a vertex buffer is good for
  one origin and one viewport.

### Where the port stops is not decided

This note describes two shapes and never chooses. §1 says "the `implot` shape",
which is widget calls. This section says a buffer of vertices. Before the merge
the difference was small, because there was one view. Now the public surface
(`advtext/__init__.py`) is `BareView.draw`, `DiffView.draw` and
`StreamView.draw` — cursor, mouse, clip rectangles, child windows, selection,
find — and `draw_runs` is explicitly not promised to a host.

The narrow reading, and the one §3 supports, is that the port is `draw_runs`
and the font loader, with every view left in Python above it. Then a port moves
the per-glyph loop and nothing else, and streaming, diffing and find cost what
they cost today. The wide reading ports the views and is a different, much
larger project that this note does not argue for. **Choose before step 1 of §9**,
because the differential harness in §7 can only compare what is on the native
side of the line.

## 5. Dependencies: a subset reader, not HarfBuzz

`fontlib` uses fontTools to read a small, deliberate subset: `cmap`, `hmtx`,
GPOS **pair** kerns only — the module docstring says so and names the
simplification it accepts — and the MATH table, plus `head`, `hhea` and `OS/2`
for vertical metrics and the glyph outlines for ink bounds. The first version of
this note said "exactly four things" and left the last two groups out. The math
face is a `.otf`, so its outlines are CFF.

The first version put that at roughly 1,000–1,500 lines of self-contained C++
OpenType reading. Nothing in the tree supports or refutes the figure and it
should be read as a guess. It keeps the extension dependency-free, which matches
the norm `implot` and its neighbours set, and pulling in HarfBuzz for a GPOS
subset that has already been scoped would be the wrong trade.

Two things have changed under that judgement:

- **The font set is no longer closed.** `fontlib.register_font` is public since
  the merge, so the kerning simplification that was justified for each bundled
  face now meets whatever a host registers.
- **Some of the reader may not need writing.** ImGui vendors
  `imstb_truetype.h`, and it reads `cmap`, `hmtx`, glyph boxes and — contrary to
  what this section used to say — GPOS pair kerning
  (`stbtt__GetGlyphGPOSInfoAdvance`, read; its own notes call it "basic").
  Whether its GPOS coverage matches the lookups `fontlib` reads, and whether its
  glyph box is right for a CFF face, were not checked.

Above the layout core there are two more dependencies this section never
counted, because the narrow port leaves them in Python: `markdown-it-py`, whose
block-rule internals `advtext/markdown.py` imports, and `difflib`. The wide
reading in §4 would have to replace both.

Worth knowing if that judgement is ever revisited: **math support is what
constrains the font stack.** stb_truetype has no MATH; FreeType does not expose
MATH well; HarfBuzz's `hb_ot_math_*` is the only mainstream option that covers
it properly.

## 6. The ecosystem gap is specific

`imgui_md` already renders markdown in ImGui — as styled text runs. No
justification and no paragraph-level line breaking; that much is this note's
original claim and was not re-checked against the current `imgui_md`. "No math",
which it also said, is wrong as of the installed bundle: `MarkdownOptions` has a
`with_latex` switch, off by default, that hands `$...$` to a vendored MicroTeX.
The stub describes formulas rendered to textures and placed as images, which is
math beside the text rather than math set in the paragraph with it. So the
ecosystem has established that markdown in ImGui is wanted, and that math in it
is wanted, and the *typesetting* half is still the part nobody has filled.

The distribution path is the `implot` one, and imgui_bundle already vendors
`implot`, `imgui-node-editor`, `ImGuiColorTextEdit` and `imgui_md`, generating
Python bindings with litgen. The loop closes: the extension lands in the bundle
and this repository's own Python demo consumes it back through the dependency it
already has.

One design constraint that is far cheaper to accept on day one than to retrofit:
litgen generates from declarations, so the public header wants to stay narrow and
POD-ish.

## 7. What makes a port cheaper here than it usually is

The asset is not the core algorithm. It is the tests, several of which exist
because a specific wrong belief got caught.

A port does not have to re-derive them. `ship()` produces POD commands and
`draw_runs` produces a vertex buffer, and both are directly comparable across
languages. A differential harness that runs one document through both
implementations and diffs command lists and vertex buffers replaces most of the
re-testing — and it is only available *because* a trusted reference
implementation exists.

Build that first, not last. No such harness exists yet.

**How much of the suite that covers has changed.** The first version counted
about 8,500 lines of core and 16,300 of tests. On 2026-10-08 `advtext/` is
44,179 lines, 20,801 of them outside `advtext/ui/`, and `tests/` is 54,837 lines
in 63 files. Most of the growth is views, pages, streaming and diffing, and a
test of a view's mouse handling or a page's layout is not something a diff of
vertex buffers stands in for. Under the narrow reading in §4 that is as it
should be — those tests keep guarding Python that stays Python — but the
sentence "replaces most of the re-testing" is true of the port's side of the
line and not of the suite.

## 8. The risk that replaces the one the narrowing removed

**ImGui font-API churn.** `implot` draws primitives and is insulated from this.
This extension would sit directly on font internals — literally, on
`imgui_internal.h` — and 1.92 has just rewritten that area: the dynamic per-size
atlas and the new loader. Implementing a custom loader *increases* that exposure
rather than reducing it.

**It has already moved once since this note was written.** Read on 2026-10-08,
`master` is `1.93.0 WIP` and the struct in §2 is a different struct:

    int  (*FontSrcGetGlyphIndexFromCodepoint)(ImFontAtlas*, ImFontConfig*, ImWchar codepoint); // Required
    bool (*FontSrcContainsGlyph)(ImFontAtlas*, ImFontConfig*, int glyph_index);
    bool (*FontBakedLoadGlyph)(..., int glyph_index, ImFontGlyph* out_glyph, float* out_advance_x); // Required

A new required hook, and two existing hooks that take a glyph index where they
took a codepoint. A loader written against the installed release does not
compile against the next one. The change happens to run in this project's
favour — entry is still by codepoint, but the mapping is now a hook of its own,
which is exactly the place a private-use codepoint wants to be resolved — and
that is luck, not a promise. `docs/imgui-risks.md` and the version floor in
`pyproject.toml` record the couplings the Python side already carries.

The first version cited, as a finding recorded in this project, that
`oversample_h` and `pixel_snap_h` became no-ops. No document here records that,
and as a statement about 1.92 it is wrong: the stb_truetype loader reads both
(`imgui_draw.cpp` at `v1.92.9`, read). What is true is narrower and is a
consequence of §1: **the FreeType loader reads neither** — `imgui_freetype.cpp`
says oversampling is not supported and never mentions `PixelSnapH` — and FreeType
is the loader this build runs. That was read, not measured.

That is a permanent maintenance cost the comparable extensions do not carry, and
it should be priced in deliberately rather than discovered.

## 9. Suggested staging, if it is ever taken

0. Decide where the port stops (§4), and try the two things in §11 that might
   shrink step 2 from Python.
1. The differential harness, against the Python reference.
2. The OpenType subset reader and a custom `ImFontLoader`, behind the existing
   Python — proving the font-file rewriting can die. The synthetic codepoints
   themselves stay at this step (§2).
3. The draw loop, and then whatever of the core the decision in step 0 put on
   the native side.

That order front-loads the thing only C++ can do, so a stall still leaves
something real behind.

## 10. Naming

The house style is `im` + a short lowercase noun — `implot`, `imnodes`, `imcmd`,
`imspinner`. The `ImGuiCamelCase` form (`ImGuizmo`, `ImGuiFileDialog`) is older and
reads heavier.

Shortlist:

| name | for | against |
|---|---|---|
| **`imtypeset`** | *Typesetting* is the exact craft term for what `ImGui::Text` does not do | slightly long |
| **`imprint`** | literally `im` + `print`; an imprint is a publisher's mark and *to imprint* is to press type | evocative rather than literal |
| **`improse`** | warm, readable, says it sets prose | undersells the math engine |
| **`imscribe`** | distinctive without being obscure | less literal |
| **`imjustify`** | names the one thing ImGui genuinely cannot do | names one feature of several |

Craft wildcards, lovely to insiders and opaque otherwise: `imgalley` (the tray of
composed type), `imfolio` (a leaf), `imslug` (a Linotype slug is a whole cast
*line*, which is thematically perfect for a line breaker, and the word carries
unhelpful connotations).

**Avoid, with reasons:**

- `imlayout` — actively harmful here. "Layout" in ImGui already means cursor,
  columns and tables; this would name a text engine after a different subsystem.
- `imtex` — overclaims. TeX's convention is that derivatives rename (LaTeX,
  XeTeX, LuaTeX) and all of those genuinely *are* TeX engines. This borrowed the
  algorithms; it has no macro language and no `.tex` compatibility.
- `imglue` — perfect to anyone who has read `tex.web`, and to everyone else it
  reads as an adhesive or a binding layer.
- `impress` — the pun works and LibreOffice Impress owns the search results.
- `imlinotype`, `immonotype` — live trademarks.
- `imtext`, `imdoc` — too generic to be findable; `imtext` invites confusion with
  `ImGui::Text`.

Leaning `imtypeset`, because the pitch is *"ImGui draws text; this typesets it"*
and the name should carry that distinction when the neighbour on the shelf is
`imgui_md`. `imprint` is the better name in isolation and would suit the demo app
or the document format.

**No name has been checked against existing projects, crates or packages.** Do
that before getting attached to one.

## 11. What is not established

Three of the first version's four items are now answered, and are kept here
with their answers because each was a thing this note asked somebody to check.

- ~~The `ImFontLoader` inference in §2.~~ **Confirmed** against ImGui's source at
  `v1.92.9`; the struct is quoted in §2 and its successor in §8.
- ~~Whether memoising the per-glyph preamble closes the frame budget on its
  own.~~ **Built; it halves the frame and does not close the question** (§3).
  The first version said that if it did, only the capability argument would
  remain. It half did, and the capability argument is still the one this note
  rests on.
- ~~Whether `ImDrawList::PrimReserve`/`PrimWrite` is reachable from the binding
  layers.~~ **Bound in Python, one vertex at a time** (§4). Not checked for any
  other binding.
- All line counts and timings here are from one machine and one document, and
  no timing was re-taken for the 2026-10-08 revision. `scripts/bench_draw.py`
  records a 22% spread between runs of unchanged code.

What is open now:

- **Where the port stops** (§4). A decision, not a measurement.
- **Whether font bytes can be passed through `ImFontConfig.font_data`.** It is
  bound; `AddFontFromMemoryTTF` is not. If it works, the temp directory goes
  without any C++, and §2's list of what only a loader can delete is one item
  shorter.
- **What the FreeType loader flags do to this project's text.** §2 measures that
  they change advances. Nobody has looked at a page under any of them, and the
  placement rules in `docs/advance-rule.md` were chosen against the default.
- **Whether the demo's runner uses the same loader as a bare context.** §1's
  FreeType finding was taken without `hello_imgui`.
- **Which docstrings explain a measurement by stb_truetype's behaviour.**
  `advtext/backends/imgui_draw.py`, `advtext/fontlib.py` and
  `scripts/bench_draw.py` all name it. The FreeType loader requests a size by
  real dimension and looks a glyph up with `FT_Get_Char_Index` (read), so the
  size correction and the cmap argument plausibly carry over unchanged; nobody
  has gone through them one by one.
- **Whether stb_truetype's GPOS and glyph-box readers are enough** to replace
  part of the reader in §5.
- **The reader's size.** Still a guess.

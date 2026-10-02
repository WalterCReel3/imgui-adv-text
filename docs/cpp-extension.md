# A C++ ImGui extension: notes

**Status: a design note from a conversation. Nothing is committed, nothing is
implemented, and no decision has been taken.** It is written down because the
reasoning turned on one verifiable finding that would otherwise be re-derived
from scratch next time, and because two of the conclusions reverse what seemed
obvious at the start.

## 1. The scope, which is narrower than it first sounds

Not a general-purpose text engine. **An extension that ties into ImGui
specifically, with language bindings layered on top of ImGui only** — the
`implot` shape: C++ over `imgui.h`, then bindings.

That narrowing is load-bearing and it resolves the strongest objection to the
whole idea. This project's most valuable content is not the TeX algorithms, which
are published and studied. It is the device-space decisions in
`advtext/backends/imgui_draw.py`, and every one of them is specific to ImGui's
rasteriser: `baked_size_px` exists because of stb_truetype's size convention,
`snap_px` matches `IM_ROUND` so we agree with ImGui about which pixel a
coordinate is on, and the advance rule (`docs/advance-rule.md`) was chosen
against ImGui's own behaviour read out of its vertex buffer.

A renderer-agnostic port either abstracts those away and loses the precision, or
re-derives them per backend. An ImGui-only extension **carries all of them across
intact and still load-bearing**. Those are different products and only the second
one inherits the work.

## 2. The finding that actually decides it

Not performance. A capability that is structurally unreachable from Python.

ImGui 1.92 has a pluggable font loader. The Python binding exposes the setter and
**not the type you would pass to it**:

    .venv/bin/python -c "
    from imgui_bundle import imgui
    a = imgui.ImFontAtlas()
    print('atlas loader API :', sorted(n for n in dir(a) if 'loader' in n))
    print('ImFontLoader type:', [n for n in dir(imgui) if 'FontLoader' in n] or 'NOT EXPOSED')
    print('ImFont glyph API :', sorted(n for n in dir(imgui.ImFont) if 'glyph' in n.lower()))
    "

prints

    atlas loader API : ['font_loader_data', 'font_loader_flags', 'font_loader_name', 'set_font_loader']
    ImFontLoader type: NOT EXPOSED
    ImFont glyph API : ['is_glyph_in_font', 'is_glyph_range_unused']

**What is verified**: that asymmetry in the binding surface. **What is inferred**:
that the C++ side has an `ImFontLoader` struct worth implementing. imgui_bundle
ships no headers, so the C++ API could not be read directly and that inference
has not been confirmed. Confirm it against ImGui's own source before building
anything on it.

### What it would delete

`advtext/fontlib.py` (907 lines) **rewrites font files on disk** — see
`imgui_font_file` and `_patched_font_directory`. It reads the font, writes our
synthetic private-use codepoints into every format-12 cmap subtable, and saves
the result into a temp directory that is deliberately never cleaned up, with a
documented silent-degradation path for fonts that have no format-12 subtable.

That exists for exactly one reason: **ImGui rasterises by codepoint, and math
variant glyphs often have no cmap entry.** `ImFont` gives Python
`is_glyph_in_font` and nothing that reaches a glyph index.

A custom `ImFontLoader` rasterises by glyph index and the entire mechanism goes
away — the minting, the temp directory, the degradation path, and the class of
bugs that lives in them. That is not a speedup. It is the removal of a workaround
that cannot be removed from Python at any level of effort.

It is also the same seam where FreeType hinting would attach, which is the one
strategy in `docs/guide/future.md` that could give sharp stems *and* designed
spacing on a face whose advances are off the pixel grid.

## 3. Performance: real, measured, and not the reason

From `docs/status.md` and `scripts/bench_draw.py`, re-derivable by running the
benchmark:

- `demo/sample.md` costs **26 ms per frame against a 16.7 ms budget** at best,
  39–45 ms on a loaded machine, with layout fully cached.
- **ImGui's own work in that frame is 1.3–2.2 ms.** Nearly all the rest is Python
  re-deriving, per glyph, values constant across the document.
- Batching into fewer `add_text` calls prices at **0.05 ms against 1.3 ms** — it
  can only reclaim what ImGui was already doing cheaply.
- Culling is in and holds a frame at 9.4 ms however long the document gets.

**The structural point is that cost and complexity live in different places.**
The complex code — `linebreak.py` at 859 lines, the math list, the column
splitter — runs once per reflow and is cached. The simple code, walking a flat
command list and emitting one quad per glyph, runs every frame across 4329
glyphs. So the case for native code is concentrated in the *least* algorithmically
risky part of the tree.

That argues for a narrow port, and it argues for trying the cheap fix first:
memoising the per-glyph preamble is item 2 in `docs/guide/future.md`, changes no
geometry, and is the honest test of whether performance justifies anything at all.

## 4. Architecture: return vertices, not commands

`shipout.ship()` already produces a flat list of POD commands — `Glyph`,
`RuleRect`, `SetGlue`, `Line`. No inheritance, no pointers, no Python semantics.
That is already a clean C ABI boundary, and it fell out of following TeX's
`hlist_out` rather than from designing for one.

**There is a trap in the obvious design.** A C ABI that *returns a command list*
is maximally portable across bindings — and puts the per-glyph loop straight back
into the host language, so the Python binding would be no faster than today.

The resolution is to return **vertex data**. The extension does font binding,
placement and snapping, and hands back a filled vertex/index buffer;
`ImDrawList::PrimReserve`/`PrimWrite` takes bulk vertices, so a host does one
reserve and one copy instead of 4329 interpreted iterations. Portable *and* fast,
and the device-space decisions stay on the native side where they were measured.

## 5. Dependencies: a subset reader, not HarfBuzz

`fontlib` uses fontTools to read exactly four things: `cmap`, `hmtx`, GPOS **pair**
kerns only — a deliberate subset, and the module docstring says so and names the
simplification it accepts — and the MATH table.

That is roughly 1,000–1,500 lines of self-contained C++ OpenType reading. It keeps
the extension dependency-free, which matches the norm `implot` and its neighbours
set, and pulling in HarfBuzz for a GPOS subset that has already been scoped would
be the wrong trade.

Worth knowing if that judgement is ever revisited: **math support is what
constrains the font stack.** stb_truetype has no GPOS and no MATH; FreeType does
not expose MATH well; HarfBuzz's `hb_ot_math_*` is the only mainstream option that
covers it properly.

## 6. The ecosystem gap is specific

`imgui_md` already renders markdown in ImGui — as styled text runs. No
justification, no paragraph-level line breaking, no math. So the ecosystem has
established that markdown in ImGui is wanted, and simultaneously shows that the
*typesetting* half is the part nobody has filled.

The distribution path is the `implot` one, and imgui_bundle already vendors
`implot`, `imgui-node-editor`, `ImGuiColorTextEdit` and `imgui_md`, generating
Python bindings with litgen. The loop closes: the extension lands in the bundle
and this repository's own Python demo consumes it back through the dependency it
already has.

One design constraint that is far cheaper to accept on day one than to retrofit:
litgen generates from declarations, so the public header wants to stay narrow and
POD-ish.

## 7. What makes a port cheaper here than it usually is

The asset is not the ~8,500 lines of core algorithm. It is the **16,300 lines of
tests**, several of which exist because a specific wrong belief got caught.

A port does not have to re-derive them. `ship()` produces POD commands and `draw`
produces a vertex buffer, and both are directly comparable across languages. A
differential harness that runs one document through both implementations and
diffs command lists and vertex buffers replaces most of the re-testing — and it is
only available *because* a trusted reference implementation exists.

Build that first, not last.

## 8. The risk that replaces the one the narrowing removed

**ImGui font-API churn.** `implot` draws primitives and is insulated from this.
This extension would sit directly on font internals, and 1.92 has just rewritten
that area: the dynamic per-size atlas, the new loader, and the finding recorded
in this project that `oversample_h` and `pixel_snap_h` became no-ops. Implementing
a custom loader *increases* that exposure rather than reducing it.

That is a permanent maintenance cost the comparable extensions do not carry, and
it should be priced in deliberately rather than discovered.

## 9. Suggested staging, if it is ever taken

1. The differential harness, against the Python reference.
2. The OpenType subset reader and a custom `ImFontLoader`, behind the existing
   Python — proving the synthetic-codepoint hack can die.
3. The core algorithms.

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

- The `ImFontLoader` inference in §2. Verified only from the Python binding's
  shape; confirm against ImGui's source.
- Whether memoising the per-glyph preamble closes the frame budget on its own. If
  it does, the performance argument for a port evaporates and only the capability
  argument in §2 remains.
- Whether `ImDrawList::PrimReserve`/`PrimWrite` is reachable from the binding
  layers that would consume this. §4's whole design rests on it.
- All line counts and timings here are from one machine and one document. The
  timings in particular were taken on a loaded box and varied by up to 1.7×
  between runs; `docs/status.md` says so where it quotes them.

# Status

The honest account of what this repository is, as of the last gate. Read it
before `README.md` if you are deciding whether to trust anything here.

It is written to be useful rather than flattering. Section 4 is the longest on
purpose.

## 0. Revision of 2026-10-07: the adoption plan was built, and this file was not rewritten

**Read `docs/adoption-plan.md`'s first section before the rest of this file.**
On 2026-10-06 and 07 an unattended team of agents implemented that plan: an
import surface, an embeddable view, colour, links, wrapping tables, structured
copy, and a streaming document and view. No person reviewed it or looked at it.
What follows from section 1 on is the account of the layout engine and the demo
as they stood before, with dated corrections where a sentence became false. It
is still the account to read for the engine. It is not the account of the
embedding or the streaming, which is the plan's.

What this file said that is no longer true, each corrected in place below:

| it said | now |
|---|---|
| the suite runs under two interpreters, one borrowed | there is one; the fallback to `../pptmstr/.venv` was removed |
| no click has ever happened | `scripts/mouse_probe.py`: 18 of 18 checks in a real window on Xvfb |
| copying joins lines with spaces; the caller supplies the hard-break set | a view's copy reads structure from the blocks; nobody supplies anything |
| table cells do not wrap | they do, where the table is wider than its measure |
| links render as ordinary prose, and nothing consumes `LinkSpan` | a view given `on_link` draws and follows them; the demo page, given none, draws them as before |
| item 2 of "what to do next": memoise the per-glyph preamble | built; a culled draw is 5.1 ms where this file says 9.4 (5.9 ms from the memo, the rest from hoisting a per-glyph import) |
| ragged-right goes through the optimiser | text that is not justified is filled first-fit at natural spacing |

**The gate.** `make check` on the final tree, run by the agent that closed the
session's gate: ruff, black and mypy clean, and `pytest` over the whole suite,
nothing ignored: **2897 passed, 7 skipped, 4 xfailed in 150 s**. The three tests that photograph a real window
(`tests/test_shot.py`, two in `tests/test_visual_diff.py`) were red at the
session's baseline because `DISPLAY=:1` was not reachable from its sandbox and
they were gated on `DISPLAY` being set. They now ask whether the display
accepts a connection and otherwise run on an Xvfb in a user namespace
(`tests/conftest.py`, `window`), which is where they ran and passed here. "No
test is skipped or marked `xfail`" below is no longer true: the four `xfail`s
are strict and assert a known defect of the total-fit breaker set ragged
(`tests/test_stream_stability.py`), and the seven skips are an 88 s
whole-paragraph run and six tests that compare two clock readings, all behind
`ADVTEXT_SLOW=1`; each of the six has a count test beside it holding the same
claim without a clock.

What works that this file does not otherwise mention, each with its test file
as the evidence and none of it looked at: `BareView` (`tests/test_bare_view.py`),
per-unit layout (`tests/test_units_layout.py`), the material-to-shipped index
map behind links and colour (`tests/test_spans.py`), wrapping tables
(`tests/test_tables.py`), first-fit breaking (`tests/test_firstfit.py`), the
streaming document compared with a whole parse after every piece
(`tests/test_stream.py`), and `StreamView` (`tests/test_stream_view.py`).
## 0b. Revision of 2026-10-07, later the same day: a second build

**Read the first section of `docs/adoption-plan.md`, "Second build", before
this.** After the adoption plan was built the user asked for more and a second
unattended team built it: the demo is a sidebar of fourteen pages where it was
five tabs; there is a diff model and a `DiffView`, unified and side by side;
inline and display mathematics from a `$...$` subset; blocks of a document that
a host widget draws; and more calls on a view. That section lists what changed
without anybody seeing it, the choices left for a person, what ran in a window,
what no reviewer read, what things cost, and the known limits. `docs/decisions.md`,
"Second build", keeps the user's nine decisions, quoted, apart from the agents'.

**No agent judged how any of it looks, and nothing in this file says.**

What this file says below that is no longer true, each corrected in place or
here:

| it says | now |
|---|---|
| five tabs; `make shot-all` photographs eight shots | fourteen pages in a sidebar, found by scanning `advtext/ui/pages/`; 26 shots, listed by `scripts/shot.py --list` |
| the demo window is 1100x800 and its content region 1070 px | 1300x800; the body right of the sidebar is 1068 x 776 px (builder-17, measured on Xvfb) |
| radicals are absent; sized delimiters are absent | both are built, from the font's ready-made outlines only (section 3) |
| "A LaTeX parser" is deliberately absent | still true of the engine. `advtext/mathtext.py` reads a subset above it, by the user's decision; matrices are left out for now, also the user's |
| the Formula tab is one summation being widened | the Formula page holds eleven hand-built formulae; the first nine are set byte-identically to before the engine grew (pinned by a test) |
| a glyph the bound face lacks is drawn as nothing | borrowed from another of the theme's faces, else U+FFFD and counted; copy and Find return what was written |
| the facade is 58 names | 94 |

**What works that this file does not otherwise mention**, each with its test
file as the evidence and none of it looked at: the diff model and its parser
(`tests/test_diff.py`), `DiffView` (`tests/test_diff_view.py`), a fenced diff
hosted in a document or stream (`tests/test_hostdiff.py`), the math subset
(`tests/test_mathtext.py`), formulas in documents and streams
(`tests/test_mathinline.py`), the view API (`tests/test_viewapi.py`), the page
scan and the shell (`tests/test_pages.py`), and one test file per new page
(`tests/test_page_*.py`).

**The gate.** `make check` on the final tree, from clean caches, run by the
agent that closed this build's gate:

ruff, black (131 files) and mypy (50 source files) clean, and `pytest` over
the whole suite, nothing ignored: **4893 passed, 7 skipped, 4 xfailed**, in
277 s on the run whose per-test times are below. Nothing was red at any point
of the gate and nothing was skipped, xfailed or weakened by the gate closer.
The seven skips and the four strict xfails are the first build's, described in
section 0. The 4893 are the 4892 of the last builder's run and one test added
at the gate (a NUL in a message copied from the Chat page's buttons). The
verbatim tail of the final run is in `.concerns/CZ-gate--builder--result.md`
(not version-controlled).

**Suite time, and where it grew.** 150 s at the end of the first build, 277 s now
(293 s on the last builder's run, on a busier machine). `--durations`, summed
by file over every phase of 5 ms or more (269.7 s in 52 files): the nine page
test files and `tests/test_pages.py` are 92.4 s between them
(`test_page_stream.py` 19.8, `test_page_stress.py` 16.4, `test_page_chat.py`
13.7, `test_page_math.py` 11.6, `test_page_inspector.py` 8.0, `test_pages.py`
7.9, `test_page_find.py` 6.4, `test_page_tables.py` 4.6, the rest under 4),
which is most of the growth; the math and diff test files are fast for their
size (`test_mathtext.py` 4.1 s, `test_mathinline.py` 3.5, `test_diff.py`,
`test_diff_view.py` and `test_hostdiff.py` under 3 each). The four files that
led the first build's list are where they were: `test_stream.py` 29.0,
`test_stream_view.py` 25.5, `test_units_layout.py` 19.1,
`test_stream_stability.py` 13.7. No single file dominates. The slowest test
is new: `tests/test_page_stress.py::test_the_page_reports_its_figures_at_1_4_and_16_panes_in_a_real_window`,
12.0 s, which runs the real app for 90 frames at each of three pane counts on
a software rasteriser; that is what the test is, and nothing was cut. The
next nine are 3.8 to 6.2 s each, seven of them a page in a real window or a
page's stream run to its end.

**`make shot-all`, after the last code change**, on Xvfb in a user namespace
(llvmpipe). Every PNG is 1300x800. "Body" is the region right of the sidebar
(x 216 to 1284, y 12 to 788). "Background" is the single most frequent colour
there, and the last column is the share of body pixels that are any other
colour: it says a page is not blank, and it does not say how much ink there is
(on a page with a light sheet on the dark surround, whichever of the two is
smaller counts as not background). Nobody looked at a PNG.

| request | file | bytes | size | most common body colour | body pixels not that colour |
|---|---|---|---|---|---|
| `document` | `demo-document.png` | 113345 | 1300x800 | (250,250,248) | 46.4% |
| `document:debug` | `demo-document-debug.png` | 123918 | 1300x800 | (250,250,248) | 56.6% |
| `columns:1` | `demo-columns-1.png` | 106801 | 1300x800 | (250,250,248) | 45.8% |
| `columns:2` | `demo-columns-2.png` | 149760 | 1300x800 | (250,250,248) | 21.9% |
| `columns:3` | `demo-columns-3.png` | 154445 | 1300x800 | (250,250,248) | 22.4% |
| `specimen` | `demo-specimen.png` | 115151 | 1300x800 | (250,250,248) | 34.3% |
| `formula` | `demo-formula.png` | 87494 | 1300x800 | (250,250,248) | 42.7% |
| `blocks` | `demo-blocks.png` | 29672 | 1300x800 | (14,14,16) | 24.9% |
| `math` | `demo-math.png` | 127487 | 1300x800 | (14,14,16) | 28.7% |
| `math:done` | `demo-math-done.png` | 136023 | 1300x800 | (14,14,16) | 29.8% |
| `themes` | `demo-themes.png` | 101815 | 1300x800 | (250,250,248) | 25.0% |
| `themes:split` | `demo-themes-split.png` | 163910 | 1300x800 | (30,30,30) | 66.0% |
| `tables` | `demo-tables.png` | 85525 | 1300x800 | (14,14,16) | 24.2% |
| `tables:floors` | `demo-tables-floors.png` | 77610 | 1300x800 | (14,14,16) | 22.9% |
| `find` | `demo-find.png` | 116471 | 1300x800 | (14,14,16) | 21.5% |
| `inspector` | `demo-inspector.png` | 146368 | 1300x800 | (14,14,16) | 22.1% |
| `stream:400` | `demo-stream-400.png` | 124981 | 1300x800 | (14,14,16) | 34.2% |
| `stream:table,done` | `demo-stream-table-done.png` | 110307 | 1300x800 | (14,14,16) | 31.2% |
| `chat:all` | `demo-chat-all.png` | 119684 | 1300x800 | (14,14,16) | 25.8% |
| `chat:roboto,all` | `demo-chat-roboto-all.png` | 131369 | 1300x800 | (14,14,16) | 27.1% |
| `diff` | `demo-diff.png` | 89615 | 1300x800 | (250,250,248) | 45.1% |
| `diff:git,side` | `demo-diff-git-side.png` | 96629 | 1300x800 | (250,250,248) | 68.5% |
| `diff:wide,unified,dark` | `demo-diff-wide-unified-dark.png` | 135794 | 1300x800 | (26,26,29) | 79.9% |
| `diff:long,both` | `demo-diff-long-both.png` | 143685 | 1300x800 | (250,250,248) | 63.4% |
| `stress:4` | `demo-stress-4.png` | 113001 | 1300x800 | (14,14,16) | 40.1% |
| `stress:16,streaming` | `demo-stress-16-streaming.png` | 161473 | 1300x800 | (14,14,16) | 42.2% |

26 PNGs for 14 pages, exit 0, 74 s. **No page is blank**: the lowest share is
21.5% (Find). Against the builder's run of the morning, 11 of the 26 files
differ in size: the four Diff shots (taken then before the palette change),
and the Chat, Stream, Stress and Inspector shots, which photograph a clock or
a timing readout; the other 15 are the same size to the byte. The Blocks
shot is the outlier by size (29,672 bytes, 175 colours where the others have
570 or more), as its builder also reported; it is a toolbar at three widths
on the dark surround. Reported, not judged.

---

**The gate.** These figures were taken while this document was being written and
the tree was **not** settled — other work was landing in `tests/` during the run,
and a suite read mid-save fails for reasons that recover on a second run. The
terminal gate is the authority for the final counts; the test *count* below in
particular went 702 → 705 → 733 → 803 over the hours this revision took.
Everything else in this file is a measurement of behaviour rather than of the
board, and does not move that fast.

The figures below are `T9-gate`'s, and **they are a snapshot of a tree that was
still being written.** They are a real green rather than a mid-write one: the
suite, both linters and both type checkers were re-run three times over the same
settled state. But T9's own premise — "everything else has finished writing" —
was false when it ran. `T14-tolerance` and `T16-formulas` held files throughout,
and `T17-spacing` and `T18-colmargin` began writing `advtext/style.py` and
`advtext/ui/app.py` within the hour, after which three consecutive runs failed in
three *different* files.

**`T12-final-gate` is the authority over this count, not this table.** Do not
read the number below as terminal; read it as the last point at which the tree
was known green.

| | |
|---|---|
| `make test` | **803 passed, 0 failed, 0 skipped, 0 xfailed** |
| `make lint` | clean — ruff (`E,F,I,UP,B`) and `black --check` over `advtext tests scripts` |
| `make typecheck` | clean — `mypy` strict |
| `make svg` | writes all five artifacts |
| `make shot` | writes a PNG of a real window, 2.3-3.8s per tab |

No test is skipped, marked `xfail`, or disabled, and nothing was weakened to get
that. Run twice, under **both** interpreters the `Makefile` can select — the
project's own `.venv` and the borrowed one — because they carry different tool
versions (ruff 0.16.8 against 0.16.2, mypy 2.3.1 against 2.3.0) and the
`Makefile` warns in its own header that the two may disagree.

*(2026-10-07: there is no borrowed interpreter any more. `make` uses `.venv`
or stops and names `make bootstrap`. The comparison below is history, kept
because it is why the fallback was a hazard: it hid a real difference.)*

**They still agree on lint and types. They no longer agree on the suite**, and
the reason is `make shot`:

| | own `.venv` | borrowed |
|---|---|---|
| `make test` | 803 passed, 0 skipped | 802 passed, **1 skipped** |
| `make lint` | clean | clean |
| `make typecheck` | clean | clean |
| `make shot` | writes the PNG | **fails** |

The skip is `tests/test_shot.py`, on `numpy is not installed, so hello_imgui
cannot export the framebuffer`, and it is the honest thing for that test to do:
the borrowed tree is read-only (`docs/decisions.md` §2) so numpy cannot be put
in it, and `hello_imgui.final_app_window_screenshot()` returns a
`nanobind::ndarray` that has nowhere to go without it. The same shortfall makes
`make shot` itself fail there, with a `TypeError` rather than an `ImportError`
— the failure mode `advtext/ui/document_view.py` already documents for a
different call. **So "0 skipped under both interpreters" is a bar this tree no
longer clears, and the way to clear it is `make bootstrap`,** which installs
`.[dev]` and with it numpy.

---

## 1. What works, and the evidence

"733 tests pass" is not evidence. These are.

### The rounding discipline, demonstrated end to end

TeX's §625 sets glue by accumulating the total natural stretch, multiplying by
the box's ratio **once**, rounding *that*, and taking a difference against the
previous rounded total. Round each space independently instead and the right edge
wavers by a scaled point or two per line, which reads as a bug in the line
breaker — where nobody will look for it.

**Every justified line in `demo/sample.md` ends exactly on the right margin.** Not
approximately: zero residue.
`tests/test_litmus.py::test_every_justified_line_ends_exactly_on_the_right_margin`
asserts it through four modules — `pack`, `linebreak`, `shipout`, `ui` — against
real font files with real `GPOS` kerning.

The rounding is Pascal's (half away from zero), not Python's (half to even),
because the algorithm takes *differences* of successive rounded values and a 1 sp
divergence at glue node *k* shifts everything from *k* onward. That is correction
C3 in `docs/tex-notes.md`, and it is pinned at an exact half.

### The line breaker is optimal, by enumeration rather than by assertion

`tests/test_linebreak.py` brute-forces **all 2^8 breakings** of a test paragraph
and checks the total-fit pass finds the minimum-demerit one. On its own that
proves less than it looks, so it is paired with
`test_greedy_first_fit_picks_a_different_and_worse_breaking_for_the_same_paragraph`
— a greedy control on the same input, which must come out *different* and
*worse*. Without the control the optimality test would pass for a greedy
implementation.

### The display sigma is a different glyph, not a bigger size

This is the claim most likely to be doubted and the one most easily faked. Latin
Modern Math's vertical variant chain for U+2211 is `[summation, summation.v1]`,
and **`summation.v1` has no codepoint in the font at all** — 227 of that font's
vertical variants are unencoded and it uses no Private Use Area. So the
dishonest implementation is easy to reach by accident: look the operator up by
codepoint, find no variant, set U+2211 larger. It looks almost right.

`tests/test_litmus.py::test_the_display_sigma_is_a_larger_glyph_and_not_the_body_one_scaled`
rules that out. It resolves each rendering's operator back through
`fontlib.glyph_name` to the name the *font* gave it, and asserts display reached
`summation.v1` while text reached `summation` — **at an identical shipped font
size**, so a scaled-up body glyph fails even though its rendered height would
pass a naive height comparison. Measured extents at 32 px: 32.032 against 44.832,
a real 40% taller glyph.

### The ImGui backend's geometry is verified

**A window needs a display; a frame does not.** `create_context()` allocates
plain memory, `ImFontAtlas` bakes glyphs on the CPU through stb_truetype, and
`new_frame`/`render` build vertex buffers in RAM. So the backend runs here, and
`tests/test_imgui_draw.py` ships the litmus formula through it in a real frame
and asserts **one textured quad per glyph** reaches the vertex buffer — including
the display summation, reached through synthetic plane-15 codepoints written into
a copy of the font's format-12 cmap.

That test carries a negative control:
`test_an_unpatched_font_cannot_see_the_display_summation` asserts the glyph is
*absent* through the unpatched file, so the patch cannot look unnecessary.

### And it has now been composited to a screen, and photographed

This is new, and it is the sentence this document said for most of its life that
it could not say. `make shot` opens a real window through the real `immapp.run`,
runs it for N frames, and grabs the framebuffer with
`hello_imgui.final_app_window_screenshot()`. Five tabs, 1400×900, 2.3-3.8s each.
Section 2 has what that did and did not settle.

Three defects were found by looking at the resulting PNGs and were reachable
from nothing else in this tree: an `ImGuiIO` ndarray field that needs numpy and
raises only on the first *click*; dark ink drawn with no page behind it, which on
ImGui's dark theme is invisible text rather than an error; and the body text
being set to the full width of the window, which at 1100 px is 145 to 156
characters a line.

### The column flow is `\vsplit`, not a height accumulator

`advtext/columns.py` implements §970-§976 `vert_break`, §968-§969
`prune_page_top` and §977 `vsplit` as `docs/tex-notes.md` §6.2-§6.4 transcribes
them, and the module docstring argues each of the three things a hand-rolled
splitter gets wrong. The one worth repeating here is the head of column 2: cut a
vertical list between two lines and the interline glue that separated them
becomes the first thing in the next column, so every column but the first starts
one `\baselineskip` low — and by an amount that varies with whichever line
landed there, so they are not even *consistently* wrong. `tests/test_columns.py`
pins the fix by comparing columns against each other rather than against a
number.

**It is cheap, and the number is the reason balance was left out rather than
feared.** Splitting `demo/sample.md`'s 253 composed nodes three ways at a 262 pt
measure costs **0.64 ms**, best of five; `demo/columns.md`'s 387 nodes cost
0.77 ms. Composing the same document at that measure costs **541 ms** in the
same process. The split is a thousandth of the work that produced the material
it splits.

### The specimen's kerning section is falsifiable to the scaled point

`advtext/ui/specimen.py` sets each kern pair twice, once with the font's `GPOS`
value applied and once with it dropped, and `tests/test_specimen.py` asserts the
difference between the two boxes **equals** that value rather than merely being
non-zero. `rt` is in the pair list because Roboto kerns it *positive* (+24/1000
em), so a reader is not left with the rule "kerning pulls letters together".
Only the four Roboto faces carry a `kern` feature at all; Inconsolata is
monospaced and Latin Modern Math spaces through its `MATH` table, so a specimen
showing a kern for either would be showing a bug.

Two real defects were found by measuring what had been written off as
unmeasurable:

- **The backend asked ImGui for the wrong size.** "Size" means the em to
  `fontlib` and the pixel height to stb_truetype; every glyph baked about 12.4%
  too small, drifting 42 px over a 44-character line. Fixed by `baked_size_px`.
- **The synthetic codepoints did not draw at all**, so the project's headline
  claim held in the SVG backend and not this one, for a mechanical reason.

### Selection works, and copies as prose

A drag across five lines highlights edge to edge, including a heading at its own
larger line height, and **every body-line fragment has the same height** whether
or not its glyphs have descenders — because the rect is sized to the line box.
Copying joins wrapped lines with **spaces, not newlines**: a paragraph wrapped
into five lines is one paragraph. A newline inside a fenced code block survives,
because the caller supplies the hard-break set.

*(2026-10-07.)* That last clause described `selection.text(hard_breaks=...)`,
and the only callers that passed the set were tests: Ctrl+C in the demo joined
a code block's lines with spaces, which `docs/adoption-plan.md` inferred and a
failing test then confirmed. A view's copy now goes through
`UnitModel.copy_text`, which reads the separators off the blocks: a blank line
between blocks, a newline between code lines and list items, a tab between
table cells. A wrapped line is still a space. The highlight changed too: it no
longer covers blank fill at a line's ends, so "edge to edge" above is true of
full lines and not of a paragraph's last line or of ragged text. Both are in
the plan's list of visible changes, with measurements.

### The performance numbers are all re-runnable

Every performance claim in this tree came out of a script that is in this tree
and prints the table its own docstring quotes:

| | |
|---|---|
| `scripts/bench_reflow.py` | compose / ship / selection index, across widths |
| `scripts/bench_draw.py` | the per-frame ImGui draw cost |
| `scripts/verify_advances.py` | ImGui's advances against fontTools' |
| `scripts/verify_ascent.py` | ImGui's baked ascent against ours |

All four run here with no display. This matters more than the numbers: a figure
in a docstring that came from a throwaway script is a figure a later reader
cannot check, and this project twice caught itself doing that.

---

## 2. What has and has not been executed

**This section used to open "Nothing in this repository has ever been composited
to a screen." That is no longer true here, and this is the fourth revision of a
belief the file itself calls the single most corrected one in the project.** The
three earlier versions were: *nothing about ImGui can be checked* (wrong — a
window needs a display, a frame does not); *ImGui geometry is checked but nothing
is composited* (true at the time); and *no display is reachable and Xvfb cannot
start* (true of the sandbox this was built in, false of this machine). Getting it
wrong in a *new* direction now would be the poor outcome, so what follows is what
was run, where, and when, and nothing beyond it.

### The display, described rather than assumed

Observed on 2026-09-23 on this machine:

| | |
|---|---|
| `DISPLAY` | `:1`, with `/tmp/.X11-unix/X0` and `X1` both present |
| `XDG_SESSION_TYPE` | `wayland` — the X server at `:1` is what the ImGui demo talks to |
| server | X.Org 1.22.1.9, `xdpyinfo` |
| GL | **direct rendering, on real hardware.** AMD Radeon (renoir) through Mesa 22.3.6, core profile 4.6, 512 MB video memory |
| Xvfb | still cannot create its lock file under `/tmp`. Unchanged, and now irrelevant |

**This is not a software rasteriser**, which matters because the two remaining
compositing risks — texture formats and premultiplied alpha — behave differently
on llvmpipe than on a driver. It is also one GPU, one driver and one X server.
Nothing here says anything about a second machine.

### What runs under the suite, traced call by call

Function-level, by `sys.settrace` over a full suite run, counting `call` events
against the functions each file defines:

| | reached | unreached |
|---|---|---|
| `advtext/backends/imgui_draw.py` | **12 of 12** | — |
| `advtext/columns.py` | **9 of 9** | — |
| `advtext/ui/specimen.py` | **23 of 23** | — |
| `scripts/run_demo.py` | **2 of 2** | — |
| `advtext/ui/document_view.py` | 17 of 18 | `selection` |
| `advtext/ui/app.py` | 14 of 35 | everything that needs a frame: `run`, `gui`, `load_fonts`, `apply_style`, the five `_*_tab` functions, `_paint_sheet`, `_draw_at`, `_face_font` |
| `scripts/shot.py` | 7 of 10 | `main`, `_grab`, `patched_run` |

`scripts/run_demo.py` is a *function*-level entry and it flatters the file
slightly: `tests/test_run_demo.py` covers `main` and `_no_window` including all
three cells of the `DISPLAY` guard, `--tab` in nine spellings and `--source`,
but it replaces `advtext.ui.app.run` with a recorder, because `tests/conftest.py`
forbids this suite from opening a window. So what the suite does not execute is
the `run(...)` call itself, and `advtext/ui/app.py` is alone on that list now.

Three entries have moved and are worth naming because earlier revisions of this
file got them wrong in both directions:

- **`_debug_line` and `_debug_glue` are no longer unreached.** This file recorded
  them as the only two unexecuted functions in `imgui_draw.py`. They are covered
  by the suite *and* they have now drawn on a screen — `make shot ARGS="--tab
  document:debug"` photographs the line boxes and the per-glue rectangles.
- **`DocumentView.draw`, `_handle_mouse`, `_handle_copy` and `_document_point`
  all run under the suite now.** They were on the unreached list. What is still
  untouched is `DocumentView.selection`.
- **`scripts/run_demo.py` is no longer on the list at all.** It was on it for
  most of this project's life, in this file and in three others.

### What runs in a real window, traced the same way

Seven `scripts/shot.py` runs at 1400×900 — `document`, `document:debug`,
`columns:1`, `columns:3`, `specimen`, `formula`, `blocks` — unioned, under the
same tracer:

| | reached | unreached |
|---|---|---|
| `advtext/ui/app.py` | **35 of 35** | — |
| `advtext/backends/imgui_draw.py` | **13 of 13** | — |
| `advtext/ui/specimen.py` | **23 of 23** | — |
| `scripts/shot.py` | **10 of 10** | — |
| `advtext/ui/document_view.py` | 13 of 18 | `cmds`, `invalidate`, `selected_text`, `selection`, `_granularity_for` — all input-driven |
| `advtext/columns.py` | 6 of 9 | `columns`, `fits`, `compose_into_columns` — the app caches, so it calls the split directly |

**Both traces are needed and neither is sufficient.** `app.py` is 14 of 35 under
the suite and 35 of 35 in a window; `document_view.py` is 17 of 18 under the
suite and 13 of 18 in a window, and the five it misses in a window are exactly
the ones a mouse would reach. Union them and **the only function in this tree
that has never run is `DocumentView.selection`**, a one-line property returning
`self._selection` that no caller in the tree asks for.

`run_demo.py` with `DISPLAY` unset refuses in 0.04s with exit 2 — the guard sits
above the `advtext` import on purpose and a test pins that ordering — and with
`DISPLAY` set it opens a window that was still up when a 10s timeout killed it.

One measurement caveat, because it cost time: **running seven shots
back-to-back in one shell loop failed four of them** and each succeeded on its
own. The X server or the window manager does not like a new window every two
seconds. A `make shot-all` that exits non-zero is worth re-running before it is
believed.

### What is still genuinely unverified

Shorter than it was, and it is not empty.

- **No person has clicked.** This bullet read "No click has ever happened"
  until 2026-10-06. `scripts/mouse_probe.py` now runs the real app in a real
  GLFW window and posts mouse, wheel and key events to ImGui's input queue over
  glyph positions read back from the view: eight gestures, eighteen checks on
  the selected range, the selected text and the clipboard, all passing
  (`python scripts/mouse_probe.py --xvfb`, about 3.5 s, re-run 2026-10-07). So
  selection has been *performed*, by a script. What is left: the events enter
  at `ImGuiIO` and not at the X server, so GLFW's callbacks and a window
  manager's focus and capture are untested; the window was on Xvfb with a
  software rasteriser; and nobody has dragged a selection and said what it was
  like. `App.open_tab` and the `--tab columns:3,debug` grammar were built when
  nothing could click, and are still how a screenshot picks a tab.
- **Everything the adoption plan built is unseen.** Four examples open real
  windows inside their tests and draw every glyph they ship. No frame of a dark
  palette, a link underline, a stream or a wrapped table has been judged by
  anyone. `docs/adoption-plan.md` section B is the list.
- **One machine.** One GPU vendor, one Mesa version, one X server, one 1920 px
  window-manager clamp.
- **Font atlas limits.** Still nothing here has hit one; see
  `docs/imgui-risks.md` item 10.

### What `make run` actually does here

Re-measured, and the middle row of the old table is gone because the display is
reachable now:

| situation | what happens | elapsed |
|---|---|---|
| `DISPLAY` unset | `run_demo.py` refuses, prints `make run` and `make shot` recipes; exit 2 | 0.04s |
| `DISPLAY=:1`, this machine | a window opens and stays up | — |
| `DISPLAY=:1` set but unreachable (an agent sandbox, 2026-10-06: `socket(AF_UNIX)` refused) | GLFW aborts on `IM_ASSERT( glfwInitSuccess )` | about 0.6s |
| the same sandbox, Xvfb in a user namespace over TCP | a window opens; `scripts/mouse_probe.py --xvfb` and `scripts/shot.py` both ran this way | 3.5s and 6.4s whole command |
| no display at all | `make shot-headless` — Xvfb in a user namespace, 22s per tab | — |

The `XVFB_RUN` block this section used to tell you to uncomment **no longer
exists**; the `Makefile` header records all three beliefs it has held about
running a window and which one was measured. `docs/imgui-risks.md` is still the
ordered list of what to look at, and item 2 on it has been settled since.

---

## 3. What is deliberately absent

These are decisions with reasons recorded, not omissions. `docs/decisions.md`
gives the reasoning for each; this list exists so nobody spends a day discovering
one.

*(2026-10-07.)* Two things this list never named, because they were assumed,
are no longer absent: a document that arrives a piece at a time
(`advtext/stream.py`), and a view that is not the demo's page
(`advtext/ui/bare_view.py`). And the first sentence of the project, "a total-fit
line breaker", is now true of justified text only.

- **Hyphenation** — roughly 1000 lines with the worst interaction in TeX
  (ligature reconstruction, §915-916). The first and emergency passes run; the
  hyphenation pass does not. **This one has a measured price**; see section 4.
- **`ext_tag` extensible glyph assembly** — not needed, because the summation
  variant chain gives a real display glyph, and TeX's own sanctioned fallback is
  the largest available variant. *(2026-10-07: that fallback is now taken for
  real, by sized delimiters; see the last item of this list.)*
- **Delta nodes in `try_break`** — a 1982 performance optimisation where the
  subtle bugs live. **The correctness half of that argument still stands; the
  performance half turned out to be wrong**, and section 5 says what it costs.
- **`\halign`, `\mathchoice`, full ligature reconstruction** — still out, for
  the reasons `docs/decisions.md` gives.
- **Page breaking — partly in now, and the part that is in is named.** This entry
  used to read "no `vsplit`, no page cost function" and half of it has changed.
  `advtext/columns.py` implements §970-§976 `vert_break`, §968-§969
  `prune_page_top` and §977 `vsplit`, which is what the Columns tab flows through.
  Still absent, deliberately: **§980's part 45, "The page builder"** (`tex.web`
  line 19105) — no `\output` routine, no §1005 page cost, no
  `\topskip`/`\maxdepth` page state, no marks and no inserts. And **no
  balancing**: columns fill in order and
  the last one is as short as it turns out to be. `columns.py`'s docstring costs
  balance out at a few milliseconds and records that it was dropped for scope
  rather than for cost. The interline-glue rule (§679) *is* in scope and is what
  makes the vertical rhythm look right.
- **Bidi, complex shaping, CJK line breaking** — left-to-right only.
- **A LaTeX parser** — the formulas are constructed by hand through
  `advtext.math`'s API, which was always the scope. What *is* in that API has
  grown: fractions, big operators with limits, scripts and the atom classes.
  Radicals and accents were on this list as out of scope and have been put back
  on the table, because that exclusion was an agent's decision rather than a
  requirement. The Formula tab was one summation when this revision started and
  is being widened to a gallery; whatever it holds when you read this, the
  claim it exists to prove is still the one in section 1 — the display operator
  is a different glyph, not a scaled one.
  *(2026-10-07, second build.)* The engine now also sets radicals, `\left` ...
  `\right` delimiters sized to their content, explicit spaces and words in a
  formula; accents are still out. It still has no parser. Above it,
  `advtext/mathtext.py` reads a fixed subset of `$...$` source into those
  atoms and refuses the rest with a reason, and a document sets formulas only
  when built with `math=markdown_math()`. **Matrices are left out for now, by
  the user's decision.** Also out: accents, `\dfrac` / `\tfrac`, `\sqrt[n]`,
  and anything taller than the largest ready-made outline (a `\left` pair
  takes the largest when it covers 75% of what TeX's rule asks; the 75% is the
  lead agent's number, not TeX's).

---

## 4. What is wrong or incomplete

The part a flattering write-up would leave out.

**Five items below were open tasks when this was written**, so the numbers in
them are the defect as measured and not the defect as it will stand: the breaking
tolerance, the sentence space, the three-column measure, the formula gallery, and
word-origin snapping in the renderer. Each says so in place. The rule that
applies to them is the one in Provenance — re-measure rather than trust — and it
applies more sharply here than anywhere else in this file.

### The breaking tolerance has now been reviewed, and the answer was no

**`advtext.ui.PROSE_BREAKING` is being changed while this is written and the
table below names the values it was measured at rather than saying "as
shipped".** At the moment of measuring it was `\tolerance=1000` with
`\emergencystretch=20pt`; it read `\tolerance=6000` with no emergency stretch an
hour later. Read the constant, not this paragraph.

**It settled back where the table was measured** (read 2026-10-06):
`PROSE_BREAKING = LineBreakParams(tolerance=1000, emergency_stretch=20 * UNITY)`
in `advtext/ui/__init__.py`. The 6000-with-no-emergency-stretch setting did not
ship as the default; it survives as `PROSE_BREAKING_BOUNDED`, and
`PROSE_BREAKING`'s docstring gives what each costs. So the sentence above
describes an hour, not the tree, and the table's second row is the shipped
value. Its counts were not re-run when this note was added.

At plain TeX's defaults `demo/sample.md` produces **seven overfull lines, the
worst by 180.9 pt** — text sitting in and past the margin. At 1000+20 there are
none, and the price is 10 underfull lines of 75.

|                              | lines | overfull | worst    | underfull | loose | tight |
|------------------------------|------:|---------:|---------:|----------:|------:|------:|
| plain TeX defaults           |    72 |        7 | 180.9 pt |         3 |    13 |    17 |
| `\tolerance=1000` + 20 pt    |    75 |        0 |     0 pt |        10 |    20 |    12 |

`TextBlock` lines only, at the 420 pt measure, by `line.fitness` — the same
method `tests/test_litmus.py::test_no_line_in_the_document_is_overfull` uses, so
the table and the assertion cannot drift apart. (Re-measured after `demo/sample.md`
grew. The previous revision recorded 55/6/180.9/2/12 against 58/0/0/8/19; the
shape of the finding is unchanged and the counts are not.)

**This paragraph used to end "nobody with authority over how the document should
look has been asked". They have now been asked, and they said the loose lines
are not acceptable.** The user looked at a render of the Columns document and
named two words, "people" and "counting", both first-word-of-line. So this is no
longer a decision waiting for a reviewer; it is a defect with an owner, and
`PROSE_BREAKING` is expected to move. **Every number in the table above is
measured against the current value and will need re-deriving when it does.**
Ragged-right is now a live option too, for the same reason radicals are: the
user has said they will trade rag for text that looks better.

Two cautions for whoever does that, both from re-measuring rather than from the
report:

- **A last line stretched by `\parfillskip` has `glue_order == FIL` and a
  `glue_set` around 2.8e7.** Count "lines past natural stretch" without
  excluding those and the number is meaningless. Counting only boxes with
  `glue_sign == STRETCHING` *and* `glue_order == NORMAL`, `demo/columns.md` at a
  468 pt measure has **8 of 58** such lines past natural stretch, worst
  `glue_set` 1.661.
- **The measure the decision is made at matters more than the tolerance.** The
  same document at a 262 pt measure — roughly what the three-column layout sets
  at, which is what the user was looking at — has **61 of 130**, worst 4.662.
  Raising the tolerance is not what made those lines loose; a 262 pt measure has
  about four interword spaces to absorb whatever the line fell short by.

### Links render as ordinary prose

*(2026-10-07: true of the demo page and of the SVG artifacts, no longer true of
the library.)* `advtext/spans.py` maps a `LinkSpan`'s material indices to
shipped indices, and a `BareView` or `StreamView` constructed with `on_link`
underlines its links, colours them `Palette.link`, shows a hand cursor and
calls back on a press and release over the same link. The demo's `DocumentView`
is given no callback and draws links as it always did, which is deliberate: the
shipped page was not to change. The underline's offset and thickness are a
builder's choice that nobody has looked at. The paragraph below is the entry as
it stood.

`advtext.markdown.LinkSpan` records where every link is, in reading-order
indices, and **nothing consumes it** — outside `markdown.py` the only mentions in
the tree are two docstrings describing what a consumer would do. This is by
construction: `advtext.shipout` deliberately carries no colour, because colour
belongs to the backend. The consequence is that the document's links are
invisible. Closing it means matching `LinkSpan` ranges against command indices the
way selection highlighting already does.

### The list gutter cost the document a line

Widening `list_indent` from 1.5 em to 1.9 em, so a two-digit ordered marker stops
colliding with its own text, took **0.4 em off the measure of every list item**.
One item of `demo/sample.md` that used to fit on one line now breaks, and its
first line is set noticeably loose. Rasterised and looked at.

The builder reported this against their own work and named the better option they
did not take: sizing each list's gutter from its own widest marker, which would
give the sample's short list a *narrower* gutter than it started with and let the
item fit with room over. Better typography, more work, still open.

### The softness was real, the diagnosis in this file was wrong, and it is fixed

This entry used to say ship-out rounds to the pixel grid and then `draw` adds a
fractional `origin` from `get_cursor_screen_pos()`, defeating it. **Both halves
are wrong** and `docs/subpixel.md` is the measurement:

- `advtext.shipout.ship` takes no `px_per_inch` and did **no** pixel rounding at
  all, so there was nothing for a fractional origin to defeat. The comment in
  the `at()` closure that said ship-out had already rounded was load-bearing and
  false.
- The pen position never blurred anything either, because ImGui 1.92's
  `ImFont::RenderText` truncates it: `float x = IM_TRUNC(pos.x)`.

The real mechanism is one layer down. `ImFont::GetFontBaked(size)` bakes at
`floor(size + 0.5)` and then draws the baked bitmap scaled by
`size / baked_size`, and `baked_size_px` asks for a fractional size for five of
the six faces. So every quad was a non-integer number of pixels across —
**1734 of 1734 glyph quads in `demo/sample.md` were resampled between texels**,
a fixed non-zero phase per glyph rather than a random one per instance. Fixed by
asking ImGui for the size it was going to bake at anyway and rounding the pen
ourselves: 0 of 1734 after, solid-ink pixels in a band of body text 413 → 686.

What it did **not** fix is in `docs/subpixel.md` §6 and belongs here: interletter
gaps are quantised to whole pixels, which is intrinsic to integer snapping, and
so is the baseline-to-baseline distance. At 15 px body text a gap is 1-3 px, so
half a pixel of layout difference becomes a whole pixel of rendered difference.
The remedies are per-phase bitmaps, which ImGui cannot store, and fractional
placement, which the user excluded because it is blur.

**A third remedy was costed and is being taken as this is written.** Snapping
each *word's* origin rather than each glyph's takes word keys drawn at more than
one shape from 66 of 496 to 0, at the price of doubling worst-case glyph
displacement from 0.50 to 0.99 px and moving the rendered right edge of a
justified line from 0.49 to 0.79 px. That trades against this project's flagship
zero-residue margin claim, so it was left as a taste call; the user took it —
"I would take a little more rag on the right justification line if the text
looks better." **So the 0.50 px and 0.49 px figures above are the ones to
re-derive first**: `docs/subpixel.md` §6.1 is where they live.

### Per-paragraph reflow cost is strongly superlinear, and has got worse

Re-measured after `demo/sample.md` grew from 23 blocks to 37. A cold reflow at
420 pt costs **98.3 ms to compose, 7.1 ms to ship and 1.8 ms to index** —
107.1 ms against a 16.7 ms frame budget (`scripts/bench_reflow.py`, best of 5).
The previous figures were 82.9 / 5.4 / 1.3 for 89.7 ms. Composition is still the
whole problem.

**Read every timing in this section as ±60%.** This machine was running four
other jobs while these were taken (loadavg 4.15) and the same benchmark varied
between 25.9 ms and 45.1 ms across four runs of the identical measurement. The
figures quoted are the best observed, which is the right statistic for a
best-of-N benchmark and is still not a quiet machine. Re-run before you act on
one.

And the cost is not spread evenly: the largest paragraph is 635 nodes costing
26.4 ms at a 300 pt measure where 463 nodes cost 13.1 ms and 371 cost 11.8 ms.
"N blocks at ~4 ms each" is a misleading model. `break_paragraph` dominates
because `_evaluate` re-packs a trial line from scratch for every (breakpoint,
active node) pair. Delta nodes are the real fix and were deliberately not
implemented; this raises what they are worth rather than lowering it.

The per-block cache does **nothing** for a resize drag — zero hits across 185
consecutive 1 pt widths, measured and pinned by a test so the cache is never
mistaken for a resize fix. It earns its place on a partly-changed document: an
edit to one paragraph is 360 hits to 47 misses and 30.5 ms instead of 144 ms.

### Two consumers at two measures used to evict each other completely

`LayoutCache.rotate()` fired on every `compose_blocks` call and, by its own
docstring, "one pass that does not use it drops it". With a Document tab and a
Columns tab live at two different measures — or one routine composing at the
2-column then the 3-column measure inside one frame — every lookup missed and
every frame was a full reflow. Against a 107 ms cold reflow that is not slow,
it is unusable.

`rotate()` is gone; `begin_pass(key)` replaced it, and a cache constructed
`LayoutCache(resident_passes=3)` keeps three passes resident, which is what the
Columns tab wants. The residency number is a parameter rather than a constant
because the right value is "how many measures are live at once", and that is a
property of the caller.

### The sentence space is what the user pointed at, and it grows with the tolerance

`advtext.style.space_factor_after` implements TeX's `\sfcode`, so the space after
a full stop is wider than an interword space. That is correct and it is what TeX
does. What was not noticed is that **it is wider in the stretch as well as in the
natural width, and by a larger factor**. Measured on `demo/columns.md` at a
468 pt measure:

| | natural | stretch |
|---|---:|---:|
| word space | 3.96 px | 1.98 px |
| space after a full stop | 5.28 px (1.33×) | **5.94 px (3.00×)** |

So the rendered ratio is `(5.28 + 5.94g) / (3.96 + 1.98g)` at glue set `g`: it is
1.33× on a line that needs no stretch and tends to **3.00×** as the line gets
looser. On the line the user actually complained about it sets 2.35× wider than
its neighbours. On a line at glue set 0.89 it is 10.57 px against 5.73 px, 1.84×
— measured, not interpolated.

This is why **lowering the breaking tolerance does not fix what the user saw**.
The tolerance decides `g`; the sentence space then amplifies whatever `g` is by
up to three. A task is boarded for it and it is a one-line change in `style.py`,
but the change is a house-style decision — French spacing — and not a bug fix.

### The three-column measure is short, and how short depends on the window

The project's own floor, from Bringhurst by way of `page_for`, is **2.00
alphabets** (53-62 characters); the single column is set at 2.25. Measured
through `column_page` with the real theme, one alphabet being 207.55 px:

| available | 1 column | 2 columns | 3 columns |
|---|---|---|---|
| 1920 px (the WM clamp) | 2.25 | 2.25 | **1.99** |
| 1400 px | 2.25 | 2.20 | **1.43** |
| 1100 px | 2.25 | **1.71** | **1.11** |

So three columns is at the floor on a maximised window and well under it on
anything smaller, and **two columns breaks the floor too** below about 1300 px.
The demo's own default window is not 1920 px, so the case a reader sees first is
the bad one. (A boarded task records this as "1.51 alphabets at the clamp"; that
figure does not reproduce here and the table above is what does. The defect is
real and the single number was not.)

### No block boundary in this engine is a legal column break

Measured, not inferred, and it is the sharpest constraint on the Columns tab.
`vert_break` can only cut where §973 says it may, and the interline glue
`append_to_vlist` puts between two boxes is preceded by a box — which is legal —
but the material *inside* a block is a single vpacked box that the splitter
cannot enter. So a block is an atom: a long list, a table or a code fence taller
than a column cannot be split and will overhang.

The practical consequence is that a column-worthy document has to be written as
sustained paragraphs, which is what `demo/columns.md` is. `demo/sample.md` in
three columns puts glyphs outside the column for exactly this reason. Fixing it
properly means composing block interiors into the outer vertical list rather
than packing them first, which is a change to `advtext.ui` and not to
`advtext.columns`.

### One call has never been made by the suite, and the usual list is wrong four ways

`advtext.ui.app.run`, because `tests/conftest.py` forbids this suite from opening
a window and `tests/test_run_demo.py` therefore replaces `run` with a recorder.
That is the whole of it. Section 2 has the trace and the corrections to the
commonly-repeated version of this list, which has at different times wrongly
named `advtext/ui/document_view.py`, `DocumentView.draw` and the mouse handlers,
`imgui_draw`'s two debug functions, and `scripts/run_demo.py`.

The thing worth taking from four wrong versions of one list: **it was wrong every
time in the direction of claiming less coverage than existed**, and every
correction came from tracing rather than from reading. A "never executed" note in
a docstring ages badly and nothing makes a liar of it.

### Smaller, and real

- **A missing glyph is only counted when a face was bound.** When `fonts(face)`
  returns `None`, `draw` falls through to the three-argument `add_text` and never
  checks coverage, so a missing glyph is silently absent and `DrawStats.missing`
  stays zero. `None` is a deliberate, documented answer, so this is a hole in the
  reporting rather than a crash. The branch *is* executed —
  `tests/test_document_view.py` and `tests/test_bench_draw.py` pass
  `fonts=lambda face: None` on purpose — and no test asserts on `missing` while
  it is taken, so it is exercised and unexamined rather than unreached.
- **`advtext.ui.app._FACES` is a module global and `run` can be called twice.**
  This entry used to say nothing clears it, so a second `run` in one process
  would hold `ImFont`s belonging to a destroyed atlas. **`load_fonts` now clears
  it first** (`_FACES.clear()`, checked by reading 2026-10-06), so that hazard is
  closed on the path `run` takes. What is left is smaller: it is still a module
  global, nothing in the tree calls `run` twice, and no test does either, so the
  clearing is read rather than exercised.
- **Two unenforced contracts with silent failure modes.** `shipout.ship` and
  `imgui_draw.draw` must each be handed the *same* metrics the packing used.
  Nothing raises. The symptom is text at the wrong size, everywhere, with no
  error.
- **Table cells do not wrap.** A cell wider than its share overflows. That is
  `\halign`'s real problem and out of scope; the sample table is narrow enough
  that it does not bite. *(2026-10-07: they wrap now. A table wider than its
  measure breaks each cell as a paragraph at its column's width, first-fit,
  and a column keeps at least its longest word. It is not `\halign`: widths
  are apportioned from natural widths, then cells are broken, once. The sample
  table is 461.7 px naturally and fits the 467 px page measure, so the demo
  shows no wrapped cell until the window is narrowed. `tests/test_tables.py`.)*
- **`docs/decisions.md` records the "only `fontlib` may import fontTools"
  contract as currently violated. It is not — that was fixed and the note is
  stale.** `fontlib.glyph_set` is the public accessor the note asks for, and
  `backends/svg.py` forwards to it, opens no file and names no font. Its one
  remaining fontTools reference is a function-local import of `SVGPathPen`, a pen
  class rather than a parser. Checked by grepping the package: `fontlib.py` is
  the only module that imports fontTools for parsing.
- **The artifacts are large** — `markdown.svg` is 1.55 MB and
  `markdown-debug.svg` 1.76 MB, because every occurrence of every glyph carries
  its own outline. Deduplicating with `<use>` would cut it tenfold and make it
  much harder to read beside the command list that produced it.
- **96 px/inch is an assumption, and the display it is about has now been
  seen.** It has not been *measured* — nothing compares a rendered em against a
  physical inch. What can be said is that the document photographs at a
  plausible size beside the SVG of the same document, and that
  `verify_advances.uniform_ratio` reports no uniform 1.333× ratio, which is the
  form this bug would take.
- **The window manager silently clamps a screenshot to 1920 px.** Ask
  `make shot` for `--width 2400` and you get a 1920 px PNG with no warning from
  the WM; `scripts/shot.py` prints one. A comparison of two widths where both
  were above the clamp would be a comparison of one width with itself.
- **Nothing renders the column layout to SVG through `make svg`.**
  `artifacts/columns-2.svg` and `columns-3.svg` exist because somebody made them
  by hand; `scripts/render_litmus.py` writes five files and none of them is a
  column. So the newest capability in the tree is the one with no
  display-independent artifact.

---

## 5. Three families of tests that could not fail

This is the most transferable thing in the repository, so it gets its own
section. **Three separate families of vacuous tests have been found here** — two
by reviewers and one by the builder who wrote them. In every case the test looked
like protection and protected nothing, and in every case what caught it was the
same move.

**Attack the fixture, not the assertion.**

### 1. A uniform fake measure made "line height, not ink" unfalsifiable

*Found by a reviewer, by reading the fixture instead of the assertion.*

`tests/test_selection.py::test_every_rect_is_full_line_height_rather_than_the_ink_of_its_glyphs`
and its twin in `test_shipout.py` compared a line of lowercase against a line
with descenders, and asserted the two highlight to the same height. But the fake
measure gave **every codepoint identical extents**, so `_document("acem",
"gjpqy")` was geometrically identical to `_document("aaaa", "aaaaa")`. The
descender contrast was decorative. Under such a measure the box height *is* the
ink extent, so the two quantities the test existed to separate were the same
number.

Worse, the claim was false: a line really did take the ink of its tallest glyph,
while three separate docstrings said it did not. The fix was a discriminating
fixture with real ink classes, plus a strut, plus a **meta-test** —
`test_the_ink_fixture_gives_the_two_lines_genuinely_different_extents` — whose
comment reads "a fixture that quietly went uniform would leave it passing and
covering nothing. That happened here once already."

### 2. "The suite emits no `ResourceWarning`" would have passed either way

*Found by a reviewer, by running the claim three ways instead of reasoning about
it.*

The font descriptors really were leaked. The proposed regression test was that
`filterwarnings = ["error"]` would turn a stray `ResourceWarning` into a failure.
It would not: the warning fires from `_io.BufferedReader.__del__`, and **CPython
swallows exceptions raised in finalizers** — they print as `Exception ignored
in:` and never fail a test. Plain `pytest`, `PYTHONWARNINGS=always::ResourceWarning`
and `python -X dev -m pytest` all gave a clean silent run *with and without the
fix*.

The defect was real and the proposed pin was a no-op. What shipped instead
asserts the file object is closed, in a subprocess, because the warning arrives
after pytest has stopped converting warnings to errors:
`tests/test_fontmetrics.py::test_reading_metrics_and_outlines_leaves_no_unclosed_file_at_interpreter_exit`.

### 3. Three of five cache-key tests passed no matter what the key contained

*Found by the builder who wrote them, by ablation on its own key — the only one
of the three not caught by a reviewer.*

`LayoutCache`'s key carries five components. The builder dropped each one in turn
and re-ran, expecting a red test for each. **Three of the five stayed green.** The
shared test helper built a fresh `char_measure` closure per call, and
`LayoutCache` keys the measure by *identity* — so every lookup missed, the cache
never served anything, the "cached" and "uncached" results agreed trivially, and
the tests passed regardless of the key.

The helper now takes `measure` as a parameter, and its docstring says that is
load-bearing rather than tidy.

### A fourth, and the house habit it produced

`tests/test_badness.py::test_badness_divides_before_multiplying_once_t_is_too_large_to_scale`
used inputs both code paths agree on, so it held whether or not the divide-first
branch existed. The guard beside it derives the maximally separating input
(`s = 1663793`, `t = 7230891`), where TeX's path gives infinite badness and
multiply-first gives 8189 — infinite against finite, the largest disagreement
available, and the one that decides feasibility in `try_break`.

The habit shows up throughout now, and it is worth keeping: the SVG outline cache
asserts `first is second` because equality would also pass uncached; the culling
fixture is four sections long because at one section every cull is a no-op; the
sigma test compares glyph *names* because a scaled-up glyph passes a height
comparison; the 32-bit-`ImWchar` check asserts `is_glyph_in_font(0x12211)` is
**False**, because True would be indistinguishable from success.

### The newest instance, and the clearest

`tests/test_imgui_draw.py::test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin`
**builds the wrong implementation on purpose and asserts that it fails.** The
tests beside it check that every glyph lands on the pixel grid; an
advance-rounding renderer — round each advance, then sum — produces integer
positions for every glyph and passes all of them, while walking the end of a
line up to 9.9 px off its margin. So the integrality tests on their own could
not tell the right implementation from the worst plausible wrong one, and the
control is what makes them mean something.

`tests/test_shot_all.py` is the same move applied to a `Makefile` variable:
`SHOT_TABS` named three tabs for a whole batch after the app grew to five, so
`make shot-all` exited 0 having silently skipped the two tabs the batch existed
to demonstrate. The test compares the list against the tab names
`App.gui` actually draws. A screenshot target that skips a tab and reports
success is a can't-fail test wearing different clothes.

---

## 6. The first three things to do next

**0. Before any of these, take the two cheap ones.** French spacing is one line
in `style.py` and removes the largest visible defect anyone has named. Raising
the three-column measure is arithmetic in `column_page`. Both are in section 4
with measurements, both are boarded, and neither needs any of the work below.

**1. Implement hyphenation.** This was item 3 and it is item 1 now, because the
thing that gated it has happened: the breaking tolerance has been reviewed and
the answer was that the loose lines are not acceptable. Raising `\tolerance`
was the workaround for having no hyphenation, and lowering it again without
hyphenation brings back seven overfull lines. So the decision to scope
hyphenation out is the decision that is now costing something visible, and
section 4 has the numbers at both the one-column and three-column measure.
Roughly 1000 lines with the worst interaction in TeX; `docs/tex-notes.md` flags
the trap and `docs/decisions.md` records why it was refused.

*(2026-10-07: item 2 is built. `python scripts/bench_draw.py --copies 1,2,4
--repeat 7` on a quiet machine gave a full draw of 15.9 ms and a culled draw
of 5.9 ms, and 13.7 and 5.1 ms on one later run, after a per-glyph import was
also hoisted out of `_glyph`; the text below is the item as it stood, with the
unmemoised figures. Item 1 is untouched. Before either, read `docs/adoption-plan.md`
section C, which is a longer and newer list of what is open.)*

**2. Memoise the per-glyph preamble in `imgui_draw._glyph`.** Drawing
`demo/sample.md` costs **26 ms per frame against a 16.7 ms budget** at best, and
39-45 ms on a loaded machine, with the layout fully cached and nothing
recomputed — so the widget misses 60fps sitting still. `scripts/bench_draw.py`
decomposes it: **ImGui's own work is 1.3-2.2 ms**, and the rest is our own
Python re-deriving, per glyph, values that are constant across the 71 runs the
document contains — `parse_font_key` re-parsing the same string,
`fontlib_metrics` re-resolving the same face, `baked_size_px` recomputing the
same ratio. This is the cheapest large win available and it changes no geometry.

Batching glyphs into fewer `add_text` calls is the intuitive fix and the
benchmark prices it at **0.05 ms against 1.3 ms** — i.e. it can only reclaim the
part ImGui was already doing cheaply, and it would cost the per-glyph
positioning that the measured advance disagreement exists to absorb. Culling is
already done and holds the frame at 9.4 ms however long the document gets — but
a 768 px window still costs 9.4 ms of a 16.7 ms budget, so the preamble is worth
fixing even with culling in place.

**3. Give the column splitter something to cut inside a block.** Section 4
records that no block boundary is a legal break, so a list or a table taller
than a column overhangs it. That is the one structural limit on the capability
this batch added, and it is a change to how `advtext.ui` composes rather than to
`advtext.columns`.

**Not on this list any more:** "run it on a machine with a display". It has been
run, `make shot` is how, and `docs/imgui-risks.md` item 2 — the item that was
*the* reason to want a display — turned out to have the wrong mechanism and has
been settled by measurement rather than by looking.

**Then, if performance still matters:** delta nodes in `try_break`, with the
brute-force optimality test watching. They are the fix for the 82% of composition
that `hpack` re-walking accounts for, and they are also the one change that would
silently alter *which* breakpoints win rather than failing loudly — which is
exactly why the enumeration test must be the thing that guards them.

---

## Provenance

*(2026-10-07.)* Section 0 and the dated notes were added by an agent closing
the adoption session. Of their figures, the suite count, the two draw timings
and the probe's 18 of 18 were re-run by that agent on the final tree; the rest
are quoted from `docs/adoption-plan.md`, which names who measured each. Nothing
else in this file was re-measured for that revision, and the sections it did
not touch are of their original date.

Every number in this document was re-measured against the working tree during the
gate that produced it, not copied from an earlier write-up. Where an earlier
figure could not be reproduced, `docs/litmus.md` says so and gives the method for
the replacement. This paragraph is here because the single most common defect
found in this project was a confident number nobody could re-derive.

Two things about this revision specifically:

- **The timings were taken on a loaded machine** and the same measurement varied
  by up to 1.7× between runs. Section 4 says so where it quotes one. A figure
  here is the best of N on a busy box, not a quiet-machine number.
- **One figure in circulation could not be reproduced and is not repeated.** A
  task specification recorded "39 of 144 lines past natural stretch" for
  `demo/columns.md` at a 468 pt measure. Counting `TextBlock` lines with
  `glue_sign == STRETCHING` and `glue_order == NORMAL`, the working tree gives
  8 of 58 at that measure and 61 of 130 at 262 pt. Neither the numerator nor the
  denominator matches, `demo/columns.md` was edited in the interval, and the
  method the original used is not recorded. The replacement figures and their
  method are in section 4.

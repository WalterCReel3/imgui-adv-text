# Status

The honest account of what this repository is, as of the last gate. Read it
before `README.md` if you are deciding whether to trust anything here.

It is written to be useful rather than flattering. Section 4 is the longest on
purpose.

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

- **No click has ever happened.** `_handle_mouse` and `_handle_copy` run sixty
  times a second inside a real window with `is_mouse_clicked` false, and the
  suite drives their geometry directly, but nothing in this environment
  synthesises a mouse event into a real frame. So selection has been *computed*
  on real data and *drawn* on a screen, and never *performed*. That is why
  `App.open_tab` and the `--tab columns:3,debug` grammar exist at all.
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

- **Hyphenation** — roughly 1000 lines with the worst interaction in TeX
  (ligature reconstruction, §915-916). The first and emergency passes run; the
  hyphenation pass does not. **This one has a measured price**; see section 4.
- **`ext_tag` extensible glyph assembly** — not needed, because the summation
  variant chain gives a real display glyph, and TeX's own sanctioned fallback is
  the largest available variant.
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
  Nothing clears it; a second `run` in one process would hold `ImFont`s belonging
  to a destroyed atlas.
- **Two unenforced contracts with silent failure modes.** `shipout.ship` and
  `imgui_draw.draw` must each be handed the *same* metrics the packing used.
  Nothing raises. The symptom is text at the wrong size, everywhere, with no
  error.
- **Table cells do not wrap.** A cell wider than its share overflows. That is
  `\halign`'s real problem and out of scope; the sample table is narrow enough
  that it does not bite.
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

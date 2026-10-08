# Adoption plan: advtext in `../pptmstr`

**Status (2026-10-07): built in this repository, phases 0 to 7, by an unattended
team of agents in one session. Nothing is committed. No person has looked at any
of it in a window, and no person took any of the decisions marked "agent
decision" below.** The pptmstr side is untouched and was never in scope.

**A second build followed the same day** (a sidebar demo of fourteen pages, a
diff view, inline mathematics, hosted blocks). Its section comes first, under
"Second build", and is the newest thing in this file.

The line this replaces read: *"Status: a plan, written 2026-10-06. Nothing in it
is implemented."* The plan's own text is kept below, unedited, from "The goal"
on. What was built against each phase is in the blocks marked **As built**, set
as quotations so the two cannot be confused. Where the plan was wrong the block
says so; the plan called itself read-derived and asked to be checked.

**How to read the figures.** Each one names who measured it. "Re-run by the
closer" means the agent that wrote this section ran the command on 2026-10-07
on the final tree. Everything else is quoted from a builder's result file in
`.concerns/` (gitignored, on this machine only), taken while other agents were
loading the machine: read ratios, not absolutes. Milliseconds are never
asserted by a test here except where a ratio is, and since the last two tasks
every such test in the two streaming test files runs only with
`ADVTEXT_SLOW=1`; "Open" lists them.

**Second pass, by the gate closer (2026-10-07).** This section and the As-built
blocks were written before the last two tasks, AF-final and AF-livetable,
landed. They have been brought level with those two by the agent that ran the
terminal gate, which is a different agent from "the closer" above; its figures
are marked "re-run by the gate closer". Both tasks are **unreviewed by any
reviewer**; section C says what evidence there is instead.

## Second build (2026-10-07): read this before "Read this first"

**Status: built in this repository after the plan below, the same day, by the
same kind of unattended team. Nothing is committed. No person has looked at any
of it in a window.** You asked for it in conversation with the lead after the
first build finished; your words are quoted in `docs/decisions.md`, "Second
build", and everything there that is not in quotation marks was decided by an
agent. You were not answering questions while it ran.

What it is: the demo's tab bar became a sidebar with nine new pages; a diff
model and a `DiffView`; inline and display mathematics from a `$...$` subset;
blocks of a document that a host widget draws (a fenced `diff` becomes a
`DiffView`); and the calls on a view the new pages had to work around until
they existed. `advtext.__all__` is 94 names (58 after the first build).

**How to read the figures**, as above: each names who measured it. "Re-run by
the gate closer" means the agent that wrote this section ran the command on
2026-10-07 on the final tree, once, at a load average of about 1.7. Everything
else is a builder's, from its result file in `.concerns/` (gitignored, this
machine only), often taken while other agents were loading the machine. Read
ratios, not absolutes.

### What it adds for pptmstr

Public names only; every one imports from `advtext`.

- **The diff of a pending write, from the texts.** pptmstr has the whole before
  and after text in hand when it renders an approval. Hand them over:
  `Diff.from_texts(before, after, label)` for a `Write` or an `Edit`
  (`before=None` is a new file, `after=None` a deleted one), and
  `Diff.from_edits([(before, after, label), ...])` for a `MultiEdit`. Then
  `DiffView(diff, theme, layout=DiffLayout.UNIFIED)` and `view.draw(fonts=...,
  palette=...)` each frame; `DiffLayout.SIDE_BY_SIDE` is the other layout and
  `set_layout` switches at run time. From texts the view has intra-line
  emphasis on paired lines, collapsed context that a click expands, and exact
  line numbers; `next_hunk()` / `previous_hunk()` are for the host's own keys,
  `height_cap=` and `height_for(width)` are for an approval row with a capped
  height, `syntax=` takes a host callable (the library ships no tokeniser), and
  an anchor that was not found is a label the host sets:
  `from_texts(..., will_not_apply="anchor not found in file")`.
  `examples/diff_minimal.py` is the smallest program that does this.
- **pptmstr must not feed its own unified string to `Diff.from_unified`.**
  Measured by the lead and by builder-27: when the old or new text of an edit
  has no closing newline, which is the normal case for an `Edit`,
  `difflib.unified_diff` over `keepends` lines emits the removed and the added
  line as ONE physical line, `-foo+bar`. No parser can take that apart, so the
  view would show one removed line reading `foo+bar` and no added line: less
  than the change, in the place an operator approves from. The joined
  `MultiEdit` string has the same defect once per fragment. `from_unified` is
  for text that arrives as a diff and nothing else: a fenced `diff` block in a
  transcript, `git` output. Its docstring says so with this example.
- **Inline mathematics.** `build_document(source, theme, resolve,
  math=markdown_math())` and `StreamDocument(theme, resolve,
  math=markdown_math())`. Off unless asked for. Keep one `markdown_math()` per
  view (it memoises set formulas). A formula that is outside the subset, or
  cannot be set, is shown as its source in the code face and
  `formula_spans(block)` gives each one's source, reason and position
  (`FormulaSpan`). Load the math face up front when math is on:
  `load_faces(ALL_FACES)`; (e) has what the first formula costs otherwise.
- **Hosted blocks.** `BareView(..., host_for=DiffFences(source=markdown))` and
  `StreamView(stream, measure, host_for=DiffFences())` draw every fenced `diff`
  or `patch` block as a `DiffView` in place, growing line by line in a stream.
  `host_for` is any `HostFor` callable returning a `Hosted` widget
  (`height_for`, `draw`, `text`), so a block can be any widget of the host's.
  pptmstr's transcript shows no diffs today; this is what would.
- **The view API.** On `BareView` and `StreamView`: `block_rect(block)`,
  `span_rects(block, start, end, cell=)`, `to_screen(rect)`, `scroll_to(rect,
  align=)`, `viewport`, `next_origin()`, `layout_stats` (a `LayoutStats`:
  which units a layout built and what it cost). `FindIndex.of(blocks).find(
  needle)` returns `TextMatch`es, table cells included, without rebuilding
  each block's text per keystroke. `table_column_limits(block, theme, measure)`
  returns `ColumnLimits` (floor and natural width per column) for a host that
  lets columns be dragged.

### (a) Visible and behaviour changes made without you seeing them

Each is a change with its measurement. None is claimed to be an improvement.
Where a line says "the lead" or names a builder, that agent decided it.

1. **The demo's window is 1300x800 by default and its navigation is a sidebar**
   (yours: "Sidebar list now"; the size is builder-17's). It was 1100x800 with
   a tab bar. The sidebar is 188 px plus 12 px of spacing; the page body is
   1068 x 776 px, where it was 1068 x 740: the same width, 36 px taller.
   Measured by builder-17 on Xvfb: at the same body size (a 1300x764 window)
   the five original pages are pixel-identical to the old tabs outside the
   navigation and a two-row seam at the window's mid-height that moves with
   the window's height. At the default height the Columns page's columns are
   36 px taller, so they hold more and break elsewhere.
2. **Ctrl+A selects everything in a `BareView`** (builder-29, C-fix3; the lead
   named the gesture, the view had no such key). Only for the view that owns
   the selection, and not while a text input is active. Headless frames only.
3. **`run()` raises `PageError` after the window closes if a page raised**
   (builder of C-pagefix). A page that raises no longer kills the demo: the
   traceback is shown in the page's body with a Retry button, printed to
   stderr once, and after the window closes the process exits with it. The
   recovery ran in headless frames with eight kinds of thing left open; it has
   never run in a real window.
4. **The math engine grew four things** (the lead's D1; you asked for a subset
   "that sits on top of this engine", and the lead judged the subset not
   useful without them): a radical, `\left...\right` delimiters sized to their
   content, explicit spaces, and words in a formula (`\text{}`). All from the
   font's ready-made outlines; nothing is assembled from pieces. The nine
   formulae the Formula page had are set byte-identically (builder-20:
   `sha256` of 46 box reprs before and after; pinned by a test). The page now
   shows eleven.
5. **The delimiter rule** (the lead's amendment, review 2 item 9; builder-26).
   TeX's rule as written: the delimiter must cover 901/1000 of the content
   about the axis and fall short by at most 5 pt, absolute. The smallest
   outline that satisfies it is set. When none does, the LARGEST is set
   anyway, as TeX does with a font that has no extensible recipe, provided it
   covers at least **75%** of what the rule asks; below that the formula is
   refused and shown as source. **The 75% is the lead's number, not TeX's.**
   The largest parenthesis is 2.99 em (47.9 px at 16 px, builder-23). At 16 px
   (builder-26): a continued fraction in `\left( \right)` sets four deep and
   is refused five deep; a three-deep display fraction of fractions sets. A
   radical keeps the strict rule: a surd that does not reach is refused.
6. **`$$` has fence semantics** (the lead's D2). A line that is exactly `$$`
   opens a display block that runs to the next `$$` line or the end of the
   input, as an unclosed code fence does. **An unclosed `$$` block is shown as
   its source so far in the code face**, and is set once when its closing line
   arrives (review 2 item 3: before that, one streamed formula changed between
   set and refused three times, measured by the lead).
7. **Math is off by default** (the lead). `build_document` and
   `StreamDocument` set no formula unless given `math=`. With it off, nothing
   about a document changes: builder of C-mathinline, 1371 existing tests and
   two batteries (0 mismatches in 180 and in 72 runs).
8. **The inline-math guards, and what they give up** (pandoc's three; two more
   from the lead in review 2; `{` and `(` added by builder-26 on its own
   judgement). An opening `$` must not follow a letter or digit or precede
   white space; a closing `$` must not follow white space or precede a letter,
   a digit, `{` or `(`. So `$5 and $10`, `set $PATH=$HOME/bin`, `US$5` and
   `${HOME}/bin:${PATH}` are text. Given up, knowingly:
   - **`$n$th` is text**, dollars showing, and so are `2$x$` and every part of
     `$x$y$`. `$n$-th` and `$n$ th` are formulas.
   - **`${A}${B}` and `$(a)$(b)` are text.**
   - **`$20/hr, or 15$/hr` sets `20/hr, or 15` as a formula** (the closer is
     followed by `/`).
   - **The regular expression `^a+$|^b+$` sets `|^b+` as a formula.**
   - In a stream, a `$` that is the last character received closes nothing
     until the next character arrives (review 3 item 3).
   The last two shapes are pinned as known limits in `_math_inline`'s
   docstring. A host whose text is code should leave math off.
9. **A character the bound face lacks is borrowed from another face, or set
   as U+FFFD** (the lead, review 2 item 5b; builder-26). Before, it was drawn
   as nothing: Inconsolata has no Greek, so `π` in inline code was a gap.
   Now the theme's prose face is tried, then the math face, then the code
   face; if none has it, the prose face's U+FFFD is set and counted
   (`advtext.markdown.replaced_characters`). Copy and Find return the
   character that was written (C-facade). Characters the bound face has give
   byte-identical material (pinned on `demo/sample.md`). In a real window
   (builder-26): rule off `glyphs=23 missing=8`, rule on `glyphs=31
   missing=0`. Costs: a borrowed character in a code block has the other
   face's advance and shifts the columns after it; and a document with no
   formula can now need the math face (for a `→`).
10. **Every diff decision.** The lead's standard: a diff must never show less
    than the change, attribute a change to the wrong file, or put text on the
    clipboard that exists on neither side without saying so.
    - **Control and invisible characters are drawn as placeholders, with a
      warning in the file header.** A NUL no longer makes a file "binary" with
      no rows (review 1 item 1); C0, C1, DEL, and every format, line-separator
      and bidirectional control character (review 3 item 1) is drawn as U+FFFD
      in the warning ink, and the header says `contains control characters`
      or `contains invisible or bidirectional control characters`. Copy
      returns the real characters.
    - **Counts decide between rows and a file header.** Inside a hunk's
      declared lengths, `--- x` / `+++ y` / `@@` are a removed row, an added
      row and the next hunk when the hunk is owed exactly one of each;
      otherwise they are a file header (review 3 item 2). Property test: 400
      text pairs at three context sizes in the suite; 76,232 diffs in a
      one-off run by builder-29, 0 failures.
    - **A lone `--- X` opens no file** (review 3 item 6). **A sloppy
      model-written diff loses its file name:** `--- a/x.py` with no `+++`
      line used to be a file named `x.py` and is now an unnamed fragment
      whose first row is the removal of `-- a/x.py`. More than the change is
      shown, never less. No input line is ever dropped (property test, 600
      texts whole and a character at a time).
    - **A mail is recognised only by git's mbox line** (`From <40 or 64 hex>
      ...`), not by the word `From` (review 3 item 5).
    - **Not-a-diff and combined diffs are shown raw**: `diff --cc` / `@@@`
      input, and text in which nothing is a diff, are drawn as their lines
      under a header saying which, never as rows and never as empty.
    - **`…` between non-adjacent copied pieces**: a copy that crosses a
      collapsed gap or a hunk boundary has a line holding only U+2026 between
      the pieces, and the next file's label between files.
    - **Removed lines are copied only when they are all that is selected**
      (unified layout; builder of C-diffview, kept by the lead). Side by side
      copies the side the press began on.
    - **A hosted diff at the edge of a document is taken only by select-all**
      (review 3 item 4): Ctrl+A or `select_all()`, never a drag that reaches
      the last character.
    - **NUL goes to the clipboard as U+2400** from `DiffView`, `BareView` and
      the Chat page's buttons; `selected_text()` keeps the real character.
      Before, the clipboard held the text up to the first NUL and nothing
      after it.
    - **Six palette values changed for contrast** (review 3 item 7,
      builder-29). Light: `gutter`, `meta` 6B6B6B to 5E5E5E; `warning` B45309
      to 662E05. Dark: `gutter`, `meta` 9A9A9A to A2A2A2; `remove` FFC1BA to
      FFD3CE; `warning` F5B04C to FADAAA. Every diff ink is now at least
      4.5:1 on every ground it is drawn on, 19 pairs a palette, pinned by a
      test. **Worst ratio 4.68** (dark, warning ink on an added emphasis
      mark; light worst 4.76, the gutter on a removed band; re-run by the gate
      closer; it was 2.24). These are numbers. Nobody has seen the colours.

### (b) Open choices for you

1. **Added and removed are nearly identical in greyscale.** WCAG contrast of
   one against the other, 1.00 being identical, re-computed by the gate closer
   on the final palette with the lead's arithmetic: **fills 1.06 light, 1.02
   dark; inks 1.07 light, 1.07 dark.** Before the contrast change the dark
   inks were 1.22: making the dark `remove` ink clear 4.5 on its own ground
   brought it closer to the `add` ink. In unified layout the `+` / `-` marker
   is the only channel that does not depend on hue. The lead left it, because
   pptmstr's own design says the marker is that channel.
2. **Shell text against the `$n$th` idiom.** The guards in (a) 8 keep
   `$PATH=$HOME` as text at the price of "the $n$th term". The lead chose
   code, because pptmstr's transcripts are about code. It is one condition in
   `advtext.markdown._math_inline`.
3. **Matrices are left out for now, by your decision** ("Leave out for now
   but note it"). Also out, by agents and for want of an engine rule: accents
   (`\hat`, `\vec`, `\bar`), `\dfrac` / `\tfrac` and `\displaystyle`,
   `\sqrt[n]{}`, and extensible delimiters (anything taller than the largest
   ready-made outline, subject to (a) 5). Builder-23's reading, with no corpus
   measured: `\dfrac` and accents are common in model output.
4. **Invisible and bidirectional control characters are placeholders in
   `DiffView` and NOT in markdown text or `BareView`.** Review 3 item 1(b)
   said to do the same there "if cheap"; builder-29 did not. A right-to-left
   override in markdown prose is still drawn as nothing. Two things to decide:
   which characters (all format characters would break emoji sequences, which
   use a zero-width joiner; the nine bidirectional controls would not), and
   where a document view shows the warning, since it has no file header.
5. **A find match inside a table cell is found and located, not highlighted.**
   `FindIndex` returns it and `span_rects(..., cell=)` says where it is; the
   decoration path cannot mark a cell (builder of C-viewapi judged that a
   redesign). The Find page counts such matches and says so.
6. **`SELECTION_OWNERSHIP` is not in the facade** (builder of C-facade). Only
   a host writing a selectable widget of its own needs it, to share the
   one-selection-at-a-time rule; it is importable from
   `advtext.ui.bare_view`. Its builder expects it to be the first omission a
   host asks about.

Smaller, each its builder's choice and each a judgement nobody has made by
eye: a column drag trades width between neighbours (Tables); the Chat page's
copy and layout buttons sit over the top-right corner of a block and cover
text there; the Find page's two mark colours are constants, the palette having
no find role; a selection spanning text and a hosted diff copies the fence's
body verbatim, markers included.

### (c) What ran in an Xvfb window, and what nobody has looked at

**No agent judged any frame of any page, the diff view, a formula in text, the
dark palettes or the changed diff inks. No claim about appearance is made
anywhere in this document, in the other documents, or in the result files.**

"A real window" means what it meant in B below: GLFW and OpenGL on Xvfb,
llvmpipe, a user namespace, no window manager, events posted to `ImGuiIO`.
What was checked is in the right-hand column and is all that was checked.

| what | who | what was checked |
|---|---|---|
| every discovered page, four frames each, in the real app | a test, in every whole-suite run (builder-17's) | no page raised |
| `make shot-all`, 26 requests | builder of C-pagefix twice; the gate closer after the last code change | exit 0; 26 PNGs of 1300x800; share of non-background pixels in the body, no page blank (table in `docs/status.md`, section 0b) |
| the five original pages, old against new | builder-17 | pixels equal at equal body size, outside the navigation and a mid-height seam |
| `scripts/mouse_probe.py --xvfb` after the sidebar | builder-17, and a test | 18 of 18 (16 of 18 until the probe's own aim was fixed) |
| Formula page, eleven plates | builder-23 | `glyphs=2931 missing=0 rules=15` |
| Math page, scrolled end to end | builder-23, before review 2's fixes | `set=70 refused=17 atoms=70`; `glyphs=10796 missing=0` over 14 steps |
| a document with seven inline formulas, 8 frames | builder of C-mathinline | `atoms=7 glyphs=117 missing=0 rules=3`, the same on frame 1 and 8 |
| face fallback, one paragraph and one fence | builder-26 | off `glyphs=23 missing=8`; on `glyphs=31 missing=0` |
| Themes, and Themes split | builder-20 | `glyphs 1356, rules 2, links 3`; each split pane 1233; palette change re-ships 0 of 15 units |
| Tables: a handle hovered, pressed, moved ten times, released | builder-21 | `moved_px=120.0 reshipped=1 selected=0 glyphs=909 missing=0` |
| Find, twenty copies of the sample: 24 searches, 30 Next, 1 Previous | builder of C-page-find | `composed=0 shipped=0`; last match on screen two frames after Previous |
| Inspector: hover, two relayouts | builder of C-page-inspector | `glyphs=1418 missing=0`; 37 units built, then 37 reused |
| Stream, the mixed source at 120 tokens a second | builder-17 | 200 frames, 681 of 681 pieces; settled lines moved 4 (KEEP_STREAMED) and 29 (RESET) |
| Chat, every canned reply to its end | builder of C-page-chat | five replies, 157 to 2288 pieces, `missing=0`; later (C-facade) 24, 37, 57 layouts for 157, 242, 374 pieces |
| `DiffView` alone, 12 frames, both layouts | builder of C-diffview | `glyphs=417 missing=0 rows=22`; `glyphs=561 missing=0 rows=21` |
| Diff page, eight runs of 30 frames | builder-20 | exit 0, `missing=0`, `syntax_errors=0` |
| Diff page, the nine hard cases, both layouts | builder-27 (seven), builder-29 (two) | exit 0, `missing=0` in all eighteen |
| a 23-line diff fence fed a line a frame into a `StreamView` | builder of C-hostdiff | `rows=22 missing=0 moved=0`; a press in the diff is the diff's, a drag across it is the document's |
| `examples/diff_minimal.py`, three ways | builder of C-facade, and a test | `missing=0`; 330, 389, 221 glyphs |
| Stress, 1 / 4 / 16 finished panes | builder of C-pagefix | 8.51 / 2.64 / 0.62 ms per view |

**Ran in headless ImGui frames only, never in a window:** the recovery from a
page that raises; `scroll_to`; Ctrl+A in `BareView`; `DocumentView` drawing a
hosted block; text held in place when a hosted diff above the window grows;
Ctrl+C answered by a diff that has scrolled out of view; the edge-copy rule.

**What nobody has looked at: all of it.** In particular, each of these exists
only to be judged by eye: every one of the nine new pages; the sidebar; the
`DiffView` in either layout, its row bands, emphasis marks, gutter, folded
rows, end-of-line marks and placeholders; `DiffPalette`, light and dark, all
of whose values are an agent's and six of which were then changed by
arithmetic (the light `warning` ink is now a dark brown, 662E05); a formula in
a line of text, the line gap it opens, a surd against its rule, a sized
parenthesis that falls short by the 75% rule; a borrowed glyph beside the face
it was borrowed into; the selection wash over a hosted diff; the Chat page's
role inks, bar and indent; the Tables handles (their hover line is now under
the glyphs); the Inspector's outline. And, as before: anything on a GPU, on a
HiDPI display, under a window manager, or with a hand on a mouse.

### (d) What no reviewer read

The reviewer had no shell and ran nothing; the lead ran its snippets. Review 0
was of the plan, before there was code. Collected from the three reviews of
code (`.concerns/lead--demo-review1..3-findings.md`), not looked at by any
reviewer:

- **Any pixel.** Wide or zero-width glyph cells in the diff view, the sticky
  horizontal scrollbar, embed-mode geometry, advances at odd pixel sizes.
- **Most test bodies of this build**, for vacuity; the names only were read
  for `tests/test_hostdiff.py`.
- **Every page module except `stress.py`.**
- **The whole view API** (C-viewapi): `scroll_to`, block and span rectangles
  for quote, code, table and hosted units, per-layout stats after a re-parse.
- `draw_runs` internals; `bare_view.py` (in review 1).
- Math: `fontlib._encode_variants` and the variant-chain data; the delimiter
  rule's cover numbers at 16 and 34 px; `spans.py` with formulas;
  `CommandIndex`; `svg.py` with formulas; link hit rectangles around a
  formula; formulas in headings or in list-marker position; cache keys with
  formulas and with borrowed faces; whether a borrowed glyph changes line
  height or baseline; the second pass of `mathtext.py`.
- pptmstr's `inbox.py`.

**Unreviewed altogether:** C-fix3 (builder-29: the eleven items of review 3,
two property tests, Ctrl+A in `BareView`, the palette values), C-facade (the 94
names and what was left out, `ReplacedChar`, `examples/diff_minimal.py`, the
Chat window test's new bound), and this gate closer's work (one clipboard
route, docstrings, these documents). C-fix3's builder mutated its own tests
and ran three fuzzes; that is the evidence there is instead.

### (e) Measured costs a host should know

- **`Diff.from_texts` is 4.2 s at 50,000 lines with scattered edits** (builder
  of C-diffview: every seventh line edited, so nothing to trim; it is
  `difflib.SequenceMatcher`). **Re-run by the gate closer: 3.8 s; 62 ms at
  5,000 lines; 0.3 ms at 50.** Run it off the UI thread for a large file, and
  **hold the `Diff` object across frames**: a fresh one per frame re-indexes
  everything and loses the selection and the expansions. A 5,000-line `Write`
  (all added) is 6.8 ms (builder of C-diffmodel).
- **`DiffView` steady frames: 4.7 to 9.4 ms** (same builder, headless, ImGui's
  default face, 900x700, 35 rows drawn; re-run by the gate closer: 4.3 to 8.3
  ms). It follows the glyphs on screen, about 3.3 us each, not the rows in the
  diff: 50 rows and 50,000 cost the same. The first frame at 50,000 rows is
  0.1 to 0.3 s (0.19 and 0.46 s re-run): every row's width is measured once.
- **A streaming view is about 2 ms per frame per view** (the lead's run:
  `sync` and layout, one piece a frame, 1.8 to 2.2 ms whether 1 or 16 views
  run and at any width; nothing is shared between views). **Re-run by the gate
  closer on a quieter machine: 1.35 to 1.54 ms**, and 2.2 ms at twelve pieces
  a frame. pptmstr's line is 1.7 ms. The lead's figure is above it and the
  re-run is below it; neither includes the draw. Nobody rules on it here.
- **The Stress page's figures and what they include.** Per pane per frame:
  layout is `sync` plus `layout_for`; draw is the whole of `draw` (culling,
  draw-list calls, highlight, hit test). Not included: ImGui's own render and
  swap, the child windows, the readout. It reports a total, a figure per view,
  and a figure per piece of text, with streaming panes staggered. On Xvfb
  (llvmpipe; builder of C-pagefix): finished panes 8.51 / 2.64 / 0.62 ms per
  view at 1 / 4 / 16 panes of 1056 / 516 / 246 px, which is draw cost falling
  with pane area. Its builder did not re-measure the lead's streaming figure
  through the page.
- **An inline formula taller than the text opens the line gaps beside it**
  (builder of C-mathinline; pinned by a test, so re-run in every suite): at
  16 px body, 21.6 px leading, 420 px measure, `$x^2$` adds 0;
  **`$\frac{a}{b}$` adds 1.84 px**; `$\sum_{i=1}^n i$` 2.56 px; a fraction of
  fractions 7.93 px. Only the gaps touching the formula's line move.
- **The first math frame for a host that did not load the math face.** The
  first formula is drawn in whatever face is bound, and the `load_pending()`
  that follows reads the font, mints its synthetic codepoints and writes a
  patched copy: about 1.06 s (the lead, review 0); **0.81 s re-run by the gate
  closer, three fresh processes, with a loader that does no atlas work**.
  Since (a) 9 a document with no formula can pay it too, on its first `→`.
  `load_faces(ALL_FACES)` up front avoids both.
- A hosted diff in a stream costs about 0.21 to 0.24 ms per appended line from
  50 to 2,000 lines, against 0.83 to 1.5 ms for the same fence as a code block
  (builder of C-hostdiff, no window).
- Find: `FindIndex.of` 13 ms for 740 blocks, then 0.25 to 1.9 ms a search;
  `find_spans` over the same blocks is 10 to 12 ms a search (builder of
  C-viewapi). A one-letter needle with ten thousand matches is about 22 ms a
  keystroke on the Find page (its builder).

### (f) Known limits, pinned by tests

- **A physical `-foo+bar` line from pptmstr's unified string** is one removed
  row reading `foo+bar`. Unrepairable from text; `Diff.from_edits` is the
  route (see above).
- **A file line that is exactly `…`** is indistinguishable, in a copy, from
  the separator between non-adjacent pieces.
- **A header-less fragment is shown raw**, under "not a diff", until its first
  `+` or `-` line arrives, and then its lines become context rows: the
  display changes mid-stream.
- **A `diff` fence is drawn as a code block for a frame or two** while its
  info string is still `di` or `dif`.
- **Scrollbar-drag jitter is unprobed**: when a hosted diff above the window
  changes height the text is held in place (headless test, within 1 px), and
  whether that jitters a frame during a scrollbar drag nobody tested.
- **The wheel over a height-capped diff at its scroll limits is unexercised**
  (it needs a real window with wheel events).
- **A character no face has, inside a list marker or a formula**, is outside
  the copy-as-itself rule of (a) 9.
- Raw lines (a combined diff, not-a-diff) cannot be selected or copied from
  inside the view. `Diff.from_edits` numbers lines from 1 in each fragment and
  has no per-edit "will not apply" (`mark_will_not_apply(label, file=i)`).
- One cell per character in the diff view: CJK, emoji and combining marks are
  not measured and not handled. Find does not search formulas. A display
  formula wider than the measure overhangs. `$|x|$` in a table cell is cut by
  the table rule; `\vert` is the way.
- A live `$$ x = 1 $$` typed on one line changes kind twice while it arrives.
  An inline formula can be unmade by the one character after its closer.

**The gate, at the end of this build** (gate closer, 2026-10-07): the tail is
in `docs/status.md`, section 0b, with the suite's time and where it grew.

---

## Read this first

Four things, in the order they matter to somebody deciding whether to keep
this: what changed in behaviour you had already seen; what has and has not been
looked at; what is open; and what pptmstr has to do.

### A. Visible changes to shipped behaviour, made without a human

Every item is a *change*, with its measurement. None of them is claimed to be
an improvement. Each was accepted by the lead agent, not by you, and each says
how to undo it.

**What did not change, measured.** The demo's eight tabs, photographed in a
real GLFW window under Xvfb at the default 1100x800 from commit `cb7bebf` and
from the working tree: **all eight PNGs are byte-identical** (sha256), and the
working tree photographed twice is identical to itself, so the comparison is
not passing on noise. Re-run by the closer;
`.concerns/AZ-docs-scripts/shot-compare.sh.txt` is the script (it needs HEAD's
`advtext`, `scripts` and `demo` extracted beside it). That covers the first
screenful of each tab, unscrolled, with no selection and at one window size. It
does not cover a narrower window, a scrolled page, or a selection, which is
where the items below show.

1. **Text that is not justified is now broken first-fit, at its natural
   spacing** (lead's decision 13). It used to go through the total-fit breaker
   under an infinitely stretchable right skip, which also set some ragged lines
   with their spaces compressed. In the **default theme** the only
   non-justified text blocks are the six headings of `demo/sample.md`, each one
   line at 300pt, 420pt, 467px and 800pt: 0 blocks differ, and the shipped
   commands are asserted identical at 467 and 558 px
   (`tests/test_compose.py::test_the_default_themes_demo_document_did_not_move`).
   A heading narrow enough to wrap can now break differently. With **every
   block set `Align.LEFT`**, old against new on the sample's 34 text blocks
   (builder-6, `.concerns/A5-tables--builder--result.md`):

   | width | blocks differing | lines differing | lines before / after | lines set compressed before / after |
   |---|---|---|---|---|
   | 300pt | 4 of 34 | 24 | 111 / 112 | 4 / 0 |
   | 420pt | 2 of 34 | 4 | 76 / 76 | 2 / 0 |
   | 467px | 9 of 34 | 21 | 92 / 95 | 6 / 0 |
   | 800pt | 2 of 34 | 6 | 50 / 50 | 2 / 0 |

   Your standing decision was that ragged-right is *additive* beside
   justification. Justified setting is untouched as far as anyone measured:
   the breaker's refactor left total-fit lines, demerits and pass identical
   over 310 settings (run by the lead), that a justified block never reaches
   the new path was read by a reviewer, and the eight identical screenshots
   agree for the demo. What changed is the output of the ragged mode that
   already existed. Undo, per call:
   `compose(..., PROSE_BREAKING_TOTAL_FIT_RAGGED)` or
   `ComposeParams(ragged_total_fit=True)`; wholesale, `advtext.ui._text_boxes`.
   Why it was done is under phase 7: the old path cost 78 to 339 times a
   justified break and set one word per line ahead of an over-wide word.

   **A figure to correct in the lead's record.** The lead's decision 13
   (`.concerns/lead--adoption-tasks.md`) says this change makes "11 of 34
   sample blocks" break differently at 420 pt. That is another comparison:
   first-fit against total-fit ragged *with the glue as emitted*, taken before
   the decision was amended to natural width (builder-7). For the comparison
   the decision asked for, the shipped `Align.LEFT` output before against
   after, the measured figure is the table's: **2 of 34 blocks at 420 pt**
   (4 lines), builder-6.

2. **A selection's highlight no longer covers blank fill at either end of a
   line** (decision 15). Select-all on `demo/sample.md` at 467 px: 50 of 100
   line highlights are narrower (median 100 px, at most 406 px) and 18 of those
   also start further right, at list items (builder-6,
   `.concerns/A6-copy--builder--result.md`). Asked for by the lead for
   right-aligned and centred table cells; the builder applied it to every
   line. Undo: two `while` loops in `advtext.selection.FragmentQueries.rects`.

3. **What Ctrl+C puts on the clipboard changed**, in the shipped demo too.
   Copy used to join every line with a space. It now reads structure: a blank
   line between blocks, a newline between code lines and at a hard break and
   between the items of one list, a tab between table cells and a newline
   between rows, a list item with its marker and one space (`• one`,
   `1. first`), a nested item indented two spaces a level. A line holding only
   a rule no longer contributes a newline. Before, a fenced block
   `line one / line two / (blank) / line four` copied as
   `'line one line two\nline four'` (builder-6's failing test, run before the
   fix). Later, in decision 18: a fence or second paragraph inside a list item
   copies with single newlines around it, and a trailing separator that no
   selected character follows is dropped. The exact strings are pinned in
   `tests/test_units_layout.py` (`AS_COPIED`, and
   `test_a_list_copies_one_block_to_a_line_indented_two_spaces_a_level`).
   The flat `text()` keeps its old meaning; the structure is `copy_text()`.

4. **A table too wide for its measure now wraps its cells, and its columns are
   apportioned by a different rule there** (phase 5; the rule is builder-6's,
   accepted by the lead in review 2). A table that fits is set exactly as
   before: the demo's table is 461.7 px wide naturally, fits the 467 px page
   measure, and its boxes equal a transcription of the old code at 467, 558 and
   1070 px. Below that the demo's table changes: at 400 px the columns are
   `[88.0, 202.7, 109.3]` where the old rule gave `[76.2, 215.8, 108.0]`, and
   at 200 px the table is 248.6 px, wider than the measure, because each column
   keeps its longest word. Undo the column rule alone: `advtext.ui._squeezed`.

5. **A wrapped table header puts its rule a full leading below its last
   baseline** (decision 17), as an unwrapped one does. Whole-document height of
   `demo/sample.md`: 5565.38 to 5571.05 px at 200 px, 3786.14 to 3791.80 at
   300 px, 3057.18 to 3069.26 at 400 px; identical boxes at 467, 558 and
   1070 px, where nothing wraps (builder-13,
   `.concerns/AF-tables--builder--result.md`). A wrapped body row followed by
   another row loses 1.6 px. This corrected a step of 1.074 leadings after a
   wrapped row and 1.369 after a wrapped header, both of which first existed in
   this session.

6. **Headings of level four to six are their own styles** (decision 12); they
   used to be set as level three (20 px bold). Now: h4 16 px bold, h5 16 px
   bold italic, h6 16 px italic, space above 0.7 / 0.6 / 0.5 em and below
   0.25 / 0.20 / 0.15 em, continuing h1 to h3's arithmetic. h1 to h3 are equal
   to a transcription of the old theme. `demo/*.md` contains no `####`, so the
   demo does not show it. The sizes are builder-5's choice; in an all-mono
   theme h6 has no italic to differ by. Undo: one line each in `Theme.build`.

7. **A space before a backslash hard break no longer sets an empty line.** It
   did, at a window of measures about one space wide, in total-fit and
   first-fit alike (lead's box-level reproduction: lines `[[40, 54], [], [10]]`).
   `advtext.markdown._unskip` drops the glue. No demo file has a backslash
   break.

8. **Right-aligned and centred text moved**, none of it in the default theme.
   The line before a hard break was off its alignment by half the slack (first
   glyphs at 103.1, 102.8 and 206.9 pt at a 225.8 pt measure; after, 206.19,
   205.57, 206.93: builder-10). The last line of every such block ended a few
   hundred scaled points short of the margin; `demo/sample.md` set whole in
   `Align.RIGHT` moves 554 to 1451 glyphs by at most 0.010 px, `Align.CENTER`
   by at most 0.0025 px, `JUSTIFY` and `LEFT` ship identical commands
   (builder-13).

9. **A whole-file parse no longer hangs a list marker on the paragraph after
   the list** when the list's last item is empty or starts with a fence
   (`- a\n-\n\npara\n`). That was a defect in `build_document` found by
   comparing it with the stream.

10. **A selection survives a re-break as the same text, or is cleared.** It
    used to be raw indices, so resizing the demo from 500 to 400 px slid the
    selected text (lead's measurement, review 3 item 3). It is now restated by
    glyph within its unit after every relayout
    (`advtext.ui.units.carry_selection`). A space at the very edge of a
    selection is not carried.

    **A drag in progress, the drag-anchor rule** (AF-final, after the last
    review; `advtext.ui.units.carry_caret`). The anchor of a drag with the
    button still down is a caret, not a range, and is carried by the first of
    three rules that applies: a unit beside it was not shipped again, and it
    keeps its place in that unit; the glyph before it (else after it) is still
    there, and it stays beside that glyph; it sits on fill in a unit set again
    with the same characters up to it, and it is restated **after the last
    glyph before it**. Otherwise the drag ends. Before this a press on fill
    (right of a paragraph's last line, a list gutter, a table cell's fill) lost
    its drag at the next relayout: 198 of 500 press positions on blocks that
    had not changed, by the reviewer's snippet run by the lead, and 0 of 500
    after (builder-15). The third rule moves the caret across the glue it was
    put down on, so a selection dragged from there can begin with a space it
    would not have begun with before the relayout. That consequence is the
    builder's reading, **not measured**, and nobody but the builder has read
    the rule.

11. **One selection is current across all views in a process**, and Ctrl+C is
    answered only by the view that owns it and only while no text input wants
    the keyboard. With one view, as in the demo, the second half is the visible
    part: Ctrl+C in a focused `input_text` elsewhere no longer copies the
    document's selection.

12. **A click is hit-tested in x as well as y**, which only shows where lines
    sit side by side (wrapped table cells). A drag whose release the view never
    saw now ends when the button is up.

13. **`DocumentView` snaps its cursor to whole pixels** (decision 18c), not the
    page's text origin, which is cursor plus margins plus a 21.6 px head and
    was always fractional. The eight identical screenshots above are the
    evidence that this moved nothing at the default window. `BareView` and
    `StreamView` snap their origin.

14. **Housekeeping a user of the tree will meet.** `make` no longer falls back
    to `../pptmstr/.venv`; with no `.venv` every target that needs one stops
    and names `make bootstrap`. `imgui-bundle>=1.92.900` (was `>=1.92`).
    `build_document` no longer raises `IndexError` on a quoted table followed
    by an unended `>` (a workaround for markdown-it 4.2.0; see "Open").
    `Layout.index` is gone and `Layout.model` is a `UnitModel`, for anything
    outside the tree that read them.

Not changes to shipped behaviour, though they are new and visible where used:
links are underlined and coloured only in a view given an `on_link` callback,
so the demo page draws them as before (decision 16); a table that arrives in
one burst under `CommitPolicy.KEEP_STREAMED` is set at natural widths rather
than filling the measure (decision 18a), which is what makes a committed table
independent of how its text arrived.

### B. What ran in a window, and what nobody has looked at

**No claim about appearance is made anywhere in this document or in the result
files it quotes.** `docs/visual-review.md` is the standard: a measurement
establishes change, never quality.

"A real window" below means one thing: a GLFW window with an OpenGL context on
**Xvfb, software-rendered by llvmpipe, in a user namespace, with no window
manager and no pointer**. Input was posted to `ImGuiIO`, not to the X server.
`DISPLAY=:1`, the display this project's older documents describe, is set and
**not reachable** from the session's sandbox (`socket(AF_UNIX)` is `EPERM`,
builder-3). So nothing below was composited by a GPU, and whether llvmpipe's
pixels equal the GPU's is unmeasured.

| what | in a real window | what was checked |
|---|---|---|
| demo, 8 tabs, HEAD against tree | yes, re-run by the closer | PNG bytes equal |
| `scripts/mouse_probe.py --xvfb`, 8 gestures on `DocumentView` | yes; 18 of 18, re-run by the closer and after eight tasks | selection range, text, clipboard |
| `examples/minimal.py --frames 5` | yes, and it is a test | `glyphs=674 missing=0 rules=2` |
| `examples/theme_gallery.py --frames 30` | yes; `--frames 6` is a test | per pane: 712 to 793 glyphs, 0 missing, 3 links, 0 unmapped |
| `examples/stream_replay.py`, `examples/chat_transcript.py` | yes, `main()` inside tests | all pieces fed in 90 frames, 0 missing, pane following; four messages drawn |
| `BareView` press, drag, release, Ctrl+C | once, throwaway script | text selected, window not dragged, clipboard equal |
| a link hovered, pressed, released; a table-cell link | once, throwaway script | callback called once, selection empty |
| `StreamView` following and releasing the tail | once, throwaway script | 110 layouts in 112 frames; scroll at end, released on wheel-up, re-engaged |
| a wrapped three-column table at 420 px | once | drew without error |
| `examples/stream_replay.py` on a 60-row table with links, both policies (AF-livetable) | once, by its builder | ran to `done=1 missing=0 committed=4`; 124 and 114 layouts |
| `scripts/shot.py`, one shot of the Document tab at 700x500; `scripts/visual_diff.py shoot --spec columns:2` | yes, and they are tests again (gate closer) | a 700x500 PNG with more than 100 colours; two column bands found, a phrase located to within 3 px |
| the four examples and the probe, once each on the final tree | yes, re-run by the gate closer | exit status and printed counts, in `.concerns/AZ-gate--builder--result.md` |

Every other test of a view runs real ImGui frames with **no display at all**
(`imgui.create_context()`, vertex buffers in RAM), or fakes.

**What an agent read as an image:** the probe's last frame (a highlight is
present where the gesture put it) and one frame of `examples/minimal.py`
(heading, paragraph, list, quote, code block and table are present in light
ink on a dark window). Both are statements that things are there.

**What no person has looked at: all of it.** In particular, and each of these
exists only to be judged by eye:

- the dark palette (`DARK_PALETTE`), and every colour value in
  `examples/theme_gallery.py`. Tests say which colours reach the vertex buffer.
- link underlines: `2 x theme.table_rule_thickness` below the baseline, one
  thick. A builder's choice, not read from the font's underline metrics.
- both streaming examples. Whether forty tokens a second is comfortable,
  whether a paragraph re-set on commit under `CommitPolicy.RESET` is
  acceptable, and how ragged monospace looks beside a terminal are what they
  were built to let you judge.
- the gallery's four panes side by side, each about 325 px at the example's
  1360 px window, which is a narrow measure for justified 16 px Roboto. Its
  builder's own doubt: loose lines there are a property of the width and may
  be held against the palettes.
- h4 to h6, and h6 in a monospace theme, where it is regular weight at body
  size and differs from a paragraph by spacing alone.
- narrowed highlights (A2), wrapped tables (A4, A5), first-fit ragged text
  (A1).
- anything on a GPU, on a HiDPI display, under a window manager, or with a
  hand on a mouse.

### C. Open

Not scheduled, not owned, or not verified. Grouped; the order within a group
is roughly cost to the adopter.

**Cost.**

- **A long live table, top level: no longer linear (AF-livetable, unreviewed).**
  When this section was first written a table still streaming was re-parsed
  and re-laid-out whole for every piece, and the closer measured it
  (`.concerns/AZ-docs-scripts/live-table.py.txt`: three columns, 560 px, one
  row per append, median of five). The lead had left it unscheduled on a
  600-row figure alone and withdrew that when the 20-row one was known. It
  was then built, on both sides: the stream follows a top-level table row by
  row (`advtext.stream._LiveTable`), a table's natural and default column
  widths are measured once per row (`advtext.ui.TableMeasure`), and a
  `StreamView` lays a table of more than four rows out as pieces of four rows
  at the whole table's column widths (`layout_units(..., table_rows=4)`).
  The same script before and after, builder-15:

  | rows | parse | layout | first `visible()` | total before | total after |
  |---|---|---|---|---|---|
  | 10 | 0.98 ms | 1.70 ms | 0.30 ms | 2.99 ms | 1.13 ms |
  | 30 | 3.20 ms | 5.71 ms | 1.13 ms | 10.04 ms | 0.83 ms |
  | 50 | 5.49 ms | 9.65 ms | 1.90 ms | 17.04 ms | 0.86 ms |
  | 100 | 10.45 ms | 20.18 ms | 1.32 ms | 31.95 ms | 1.13 ms |
  | 200 | 21.32 ms | 41.59 ms | 1.50 ms | 64.41 ms | 1.21 ms |

  The three middle columns are the parts of "before". The closer's own
  "before" was 3.0 / 6.4 / 10.0 / 16.9 / 31.7 ms at 10 / 20 / 30 / 50 / 100
  rows, and builder-13's 13 + 25 ms at 100 rows, 42 + 80 at 300 and
  138 + 162 at 600. pptmstr treats 1.7 ms a frame as too much.

  **What is still not flat** (builder-15's figures, nobody else's):

  - **A cell that widens a column sets every piece again.** On a 30-row,
    four-column table fed four characters at a time (647 pieces), 26 layouts
    changed a width at 900 px and 29 at 420 px; 8 of them came after the
    table was longer than one piece, costing up to 9.5 ms at 900 px and 22 ms
    at 420 px. On the synthetic table it is the row whose name is first three
    digits long: 20 ms at 560 px, 57 ms at 260 px.
  - **A table wrapped to a narrow pane is about 2.5 ms a row** (2.3 to 2.8 ms
    at 260 px against 0.95 to 1.2 ms at 560 px), because the last piece, up
    to four rows, is set again for every piece of a row and a wrapped row
    costs a line break per cell. So the 1.7 ms is met at the median where the
    table fits and not where it wraps.
  - **A table inside a list item or a quote is not followed** and stays
    linear in its rows. Not measured.
  - `BareView` has table pieces off (`_TABLE_ROWS = 0`), as it has code
    pieces off.
  - A followed table **commits on the first complete line that is not one of
    its rows**. That rests on a claim its builder argued from reading
    markdown-it's table rule and holds over 32 sources and two batteries; if
    it is wrong somewhere, a *committed* table is wrong.
- **Code pieces are off for `BareView`.** `StreamView` lays a long open fence
  out sixteen lines at a time (106.8 ms a line at 600 lines before, 1.9 to
  3.2 ms after: builder-13). `BareView` and `DocumentView` do not, and the
  switch is a class constant, `_CODE_LINES`. A host that streams by replacing
  a long code block in a `BareView` pays the linear cost. `StreamView` is the
  supported path.
- **One very long paragraph, table or heading as the last child of a list or
  quote** is re-read whole per piece, as a top-level paragraph is. One
  paragraph of a list item fed a sentence at a time: 78 ms parse and 650 ms
  layout at 600 sentences (builder-13). Not a shape a model writes.
- **A long live list is 6 ms an item at 600 items** on the view side, part of
  it `_Shelf.find` comparing the live item by value with every stored unit of
  the same shape; the synthetic items all shared one. A real list was not
  measured.
- **`LayoutCache` retires entries that the previous pass did not touch**, and
  under units a pass touches only what missed. Edit a quote, edit an unrelated
  paragraph, edit the quote again: its other blocks are re-broken. Read-derived
  (review 1 item 5); single-block runs no longer go through that cache
  (builder-6), quote runs do. A streaming last block is unaffected.
- **`StreamView.sync()` forces `stream.sources`** on every change: 346 µs at
  640 live list items against 433 µs for the parse. Measured, not fixed.
- **`_glyph` executed `from imgui_bundle import imgui` once per glyph: fixed
  (AF-final, unreviewed).** The closer saw it in one `cProfile` run of `draw`
  (21,895 import-machinery calls in five draws of 4,362 glyphs). `draw_runs`
  now hands `_glyph` the `ImVec2` constructor: 0 such calls, a full draw 15.92
  to 14.31 ms, and the arguments of all 4,362 `add_text` calls for
  `demo/sample.md` at 420 px hash the same before and after (builder-15). A
  test counts import statements per glyph.
- **Suite time.** The whole suite, nothing ignored, re-run by the gate closer
  on the final tree: **2897 passed, 7 skipped, 4 xfailed in 150 s**. The closer's figure before the last two
  tasks was 2229 passed in 127 s without the three display-bound files; the
  session's baseline was 909 tests in about 40 s. So the suite is about three
  times the tests and three to four times the time, and the time is spread
  thin: the slowest single test is under 6 s and the slowest ten together
  are about 32 s. Where it grew, by file, from one run with every duration
  listed: `tests/test_stream.py` 27 s, `tests/test_stream_view.py` 24 s,
  `tests/test_units_layout.py` 18 s and `tests/test_stream_stability.py`
  13 s, four files that did not exist at the baseline and are 82 of the
  roughly 150 s. The "nine minutes" in the lead's notes was a loaded
  machine. Off by default: one 88 s whole-paragraph run and six clock-ratio
  tests behind `ADVTEXT_SLOW=1`, and a generated-document fuzz behind
  `ADVTEXT_STREAM_FUZZ=N`, so nobody runs them unasked.

**Behaviour a host will meet.**

- **`Face.CODE_BOLD` with nothing registered is Roboto Bold.** No bold
  monospace file is bundled. So plain `Faces.mono()` sets headings and bold
  runs in a proportional face, and every all-mono theme in the examples passes
  `Faces.mono(bold=Face.CODE)` instead, which is monospace and not bold. The
  alternative stand-in, the regular monospace file, is one line in
  `fontlib._STAND_INS` and would change the demo wherever bold sits in code.
  No real bold monospace was ever loaded: the test registers a copy of
  Inconsolata Medium under the role.
- **An unclosed `<!--`, `<pre>` or `<script>` swallows the rest of a stream.**
  Nothing after it is shown, in a whole parse and in a stream alike; it is
  what the source means. A stray `<!--` from a model blanks the rest of the
  answer unless the host escapes it. Cost while swallowed: 0.15 rising to
  about 2 ms a piece by 600 lines.
- **Reference-style links render literally in a stream** (`[text][1]`, and
  the `[1]: url` line as a paragraph), because definitions change earlier
  blocks retroactively and the streaming parser has them off
  (`build_document(..., references=False)` is the same parse for a finished
  message).
- **A block commits when the first line of the next block ends**, not at the
  blank line. Under `RESET` the re-set is therefore later than the paragraph
  visibly finished. Two exceptions: a followed top-level fence commits when
  its closing line ends, and a followed top-level table commits on the first
  complete line that is not a row of it, which is nearly always the blank
  line after it (AF-livetable).
- **Markup that closes late moves text already shown** (`**`, a backtick,
  `[text](`). First-fit does not protect against it. On `demo/stream.md` at
  520 px under `KEEP_STREAMED`: 4 settled lines in 3 steps.
- **Recorded and left as found:** an item that starts with a fence hangs its
  number on the paragraph after it; `- - b` drops the outer bullet; a table
  inside a quote interrupts the quote's bar; bold inside a code span keeps its
  weight on a monospace base and drops it on a proportional one.
- **Not built:** autoscroll while dragging past a pane's edge; a newline for a
  hard break inside a table cell on copy; colour spans on a table; matches
  inside table cells in `find_spans`; copy-as-markdown finer than whole
  blocks.

**Dependencies.**

- **Dear ImGui 1.93 may rename `ImDrawListFlags_.text_no_pixel_snap`.** A
  search summary of ocornut/imgui#9504 said it folds into `ImDrawFlags`; the
  issue itself was not read. No upper bound was set. The floor test in
  `tests/test_makefile_env.py` goes red on the first bundle without the
  attribute. The floor itself is the minimum by changelog and the verified
  version by measurement: 1.92.801 was never installed and seen to lack it.
- **A workaround for markdown-it-py 4.2.0** is carried in
  `advtext.markdown._parse`: the library raises `IndexError` on
  `"> a|b\n>-|-\n>"`. A test uses the library itself as the control, so an
  upgrade that fixes it says so.
- **The stream's resumption forges a line of markdown** to re-open containers
  (`advtext.markdown._resume_point`). A generated-document fuzz found it wrong
  twice during the build; after the fixes, over two million compared pieces
  with no mismatch. A markdown-it upgrade should be met with
  `ADVTEXT_STREAM_FUZZ=2000 .venv/bin/python -m pytest tests/test_stream.py -k generated`.
  The fence path infers "closed" from `token.map`, which is not a documented
  interface; 14 cases pin it.
- **`BareView` uses one internal ImGui call**, `imgui.internal.get_hovered_id`,
  and depends on ImGui activating a button first submitted on the frame of
  the click. True in 1.92.900; if it stops, selection still works and the
  host window drags with it.

**Tests that may flake, and tests that are weak.**

- **Clock ratios in the two streaming test files now run only with
  `ADVTEXT_SLOW=1`** (AF-final). `test_the_cost_of_a_line_does_not_grow...`
  in `tests/test_stream_view.py` is itself a count test now (code lines
  shipped over two windows of one open fence: 272 and 272 in pieces, 1552 and
  9744 whole), and the stream cost tests in `tests/test_stream.py` each had a
  count test above them making the same claim. Six clock tests are skipped by
  default for that reason; with the 88 s run that is the suite's seven skips.
  What a count cannot see, a cost linear in something nobody counted, only
  the opt-in clock tests would. A search of `tests/` by the gate closer for
  clock reads found no other test asserting on one: the rest are in report
  functions that are not tests.
- A real two-thread run in `tests/test_stream.py` (8 trials). A deterministic
  stand-in lock beside it is the real guard.
- Five tests open an Xvfb window (displays 93, 95, 96, 97 and 99) and skip if
  `Xvfb` or `unshare -rm` is absent. One waits for the server rather than
  sleeping, after passing three times of three without the wait.
- **The three display-bound tests run again** (`tests/test_shot.py` real shot,
  two in `tests/test_visual_diff.py`). They were red at baseline because
  `DISPLAY=:1` is unreachable here and they were gated on `DISPLAY` being
  set. They now take a `window` fixture (`tests/conftest.py`) that asks
  whether the session's display accepts a connection, runs the shot there if
  it does, on an Xvfb in a user namespace (display 94) if it does not, and
  skips only if neither can be had. In this session they ran on Xvfb and
  passed. That reverses a position `tests/test_shot.py` used to argue, that a
  set-but-broken display should go red; and on Xvfb the pixels are
  llvmpipe's. The fixture writes its PNGs under `artifacts/` and removes
  them, because the recipe's tmpfs hides `$TMPDIR`.
- `tests/test_stream_stability.py` keeps four strict `xfail`s that assert the
  total-fit breaker's ragged defect. They are meaningful only while that path
  stays reachable.

**The index and the tree.**

- **Nothing is committed.** The lead's rule was no git writes. Several
  builders staged files anyway, following a line in their own prompt, and said
  so. As `git status --short` reads now: staged at some point (`A`, `AM`,
  `MM`, `M `) are `advtext/ui/bare_view.py`, `fonts.py`, `stream_view.py`,
  `units.py`, the three `examples/` files other than the gallery,
  `scripts/bench_draw.py`, `scripts/bench_reflow.py`, `scripts/mouse_probe.py`
  and eleven test files; `tests/test_stream_stability.py` is intent-to-add.
  The staged content is older than the working tree for every `AM` and `MM`
  entry. **Untracked, with no revert path if overwritten:** `advtext/spans.py`,
  `advtext/stream.py`, `demo/stream.md`, this file,
  `examples/theme_gallery.py`, and `tests/test_example_gallery.py`,
  `test_firstfit.py`, `test_makefile_env.py`, `test_mouse_probe.py`,
  `test_spans.py`, `test_stream.py`.
- `artifacts/` held three throwaway probes (`a2_bare_probe.py`,
  `a3_runs_probe.py`, `a7_view_probe.py`), which are the only record of the
  "once, throwaway script" rows in section B. The gate closer removed them
  from `artifacts/` and kept byte-identical copies in
  `.concerns/AZ-gate-scripts/` (gitignored, like the rest of `.concerns/`).
  The closer's twenty-four comparison PNGs are still in `artifacts/az-cmp/`.
  Gitignored; safe to delete.
- **Stale text the closer listed as not its to write: corrected by the gate
  closer**, comments and docstrings only. The `Makefile` header,
  `scripts/run_demo.py`, `scripts/shot.py` and
  `advtext/backends/imgui_draw.py` said `DISPLAY=:1` is live; they now say it
  was live in the session that wrote them and unreachable in this one.
  `tests/conftest.py` no longer describes a borrowed interpreter as current;
  `advtext/fontlib.py` cites the tests that exist; `advtext/backends/svg.py`
  points at `advtext.spans.decorate`; `advtext/ui/__init__.py`'s
  `LayoutCache` and `CommandIndex` docstrings say who calls them now;
  `tests/test_style.py` no longer says `scripts/bench_draw.py` builds its
  mono theme by hand. `tests/test_run_demo.py` pinned the old wording of one
  retraction and was moved with it.
- **Two records in the lead's own file are wrong as they stand**, and the
  right form is stated here because that file is not version-controlled.
  *Decision 13* quotes 11 of 34 blocks differing at 420 pt; for the
  comparison it describes the measured figure is 2 of 34 (section A item 1).
  *Decision 8* still reads "a selection touching a block re-set by `RESET`
  is cleared". The tree does not always clear it: after any relayout,
  `RESET` included, a selection is carried by glyph when its units set the
  same characters and cleared only when they do not (section A item 10;
  `docs/decisions.md` has the as-built row).
- **The lead's own notes list a task, `AD-chat`, that was never on the board.**
  `examples/chat_transcript.py` was built under the stream-replay task.

**What no reviewer read.** Four reviews ran, by an agent with no shell; the
lead ran its snippets. Never reviewed: `examples/theme_gallery.py`;
`advtext/backends/imgui_draw.py`'s `draw_runs` and how `inks` and `fills` are
consumed; `advtext/ui/document_view.py`; the facade; `scripts/bench_reflow.py`;
the bodies of `tests/test_spans.py`, `tests/test_tables.py` and most of
`tests/test_bare_view.py`; `advtext/stream.py`'s restart and nested-fence
machinery; `selection.py`, `app.py`, `style.py`, `shipout.py` (review 1's
list); any real backend. **Landed after the last review and read by nobody
but their builder:** the table rhythm and validation fixes, the stream
resumption (`_resume_point`, the opener), code pieces, and all of review 4's
fixes, of which seven items were written by sub-agents whose diffs their own
builder did not read line by line: among them the drag anchor and the
selection carry that decision 8 rests on. Nor has anyone reviewed the
closer's own edits: this document, the other documents, and the removal of
`_MonoTheme` and three table rows from `scripts/bench_draw.py`.

**The fifth review, and the two tasks after it.** A fifth review read
AF-streamcost, AF-codeunits, AF-review4 and AF-tables and produced six items
(`.concerns/lead--review5-findings.md`); **AF-final** fixed them: the drag
anchor (section A item 10), a slice memo that `under_mouse()` overwrote every
frame (871 commands moved per frame, 0 after), an unclosed fence in a list
item re-read per piece of an outdented line (7339 characters handed to the
parser for one, 70 after), the clock tests, and `_glyph`'s import.
**AF-livetable** then built the live table above, and edited
`advtext/ui/bare_view.py` outside its listed files. **Neither task was read
by any reviewer.** The only evidence about them that did not come from their
own builder is two batteries the lead ran against the tree after both landed:
`.concerns/review5-snippets/D.py.txt`, 0 mismatches in 180 runs of 45
sources, and `.concerns/review5-snippets/T-lead-table-battery.py.txt`, 0
mismatches in 72 runs of 18 top-level table sources. Both compare a stream
with one whole parse and **say nothing else**: the view-side table pieces,
`TableMeasure`, the drag-anchor rule, the slice memo and the `bare_view.py`
edits have had no second reader. The builder's own mutation run on the table
work killed 14 of 15 mutants and the builder believes the survivor
equivalent. The gate closer's edits (the `window` fixture, three tests moved
onto it, the docstrings above, this pass) are unreviewed too.

### D. What pptmstr does on its side

Pointers to public names only. Every name is importable from `advtext`
(`advtext.__all__`, 58 names when this was written; 94 since the second build,
whose own pointers are at the top of this document). The changes themselves
are out of scope here.

- **Depend on it.** `imgui-bundle>=1.92.900`. advtext opens font files at run
  time through fontTools the first time a face is measured, which is the
  pptmstr policy the plan says this reverses.
- **Fonts.** `register_font(Face.CODE_BOLD, path)` for the vendored
  Inconsolata-Bold, *before* any document is built. Then `load_faces()` once
  the ImGui context exists; the `LoadedFaces` it returns is the `fonts`
  argument everywhere, and `load_pending()` before `new_frame` loads a face a
  draw asked for and did not have. `examples/minimal.py` shows the order
  against a host's own default font.
- **Theme.** `Theme.at_pixel_height(16.0, faces=Faces.mono(), align=Align.LEFT)`
  is pptmstr's present look in one call; without a registered bold, pass
  `Faces.mono(bold=Face.CODE)`. `em_size_for_pixel_height` is the conversion
  alone.
- **DETAIL panes.** `build_document(source, theme, fontlib_metrics)`, then a
  `BareView(document=..., theme=..., measure=char_measure(fontlib_metrics))`
  and `view.draw(fonts=fonts, palette=palette)` inside a child window. The
  view paints no background and submits no item except while a drag is on:
  push the child's background, and use `always_vertical_scrollbar` or pass
  `width_px`, or the measure changes when the scrollbar appears.
  `examples/theme_gallery.py` does all three.
- **Colour that carries meaning.** `DARK_PALETTE.with_roles({BlockKind.HEADING_1: ..., BlockKind.QUOTE: ..., BlockKind.CODE: ...})`
  for palette roles; `view.set_colours(block, [ColourSpan(...)])` with
  `code_position` or `colour_text` for runs; `find_spans(block, needle, mark=...)`
  for search hits, which is what lets search stay in rich mode.
- **Segments that are not markdown.** `text_block(...)` and `code_block(...)`
  build blocks from plain text; `Document(blocks=...)` takes them.
- **Copy, and the block under the mouse.** `view.selected_text()`,
  `view.selected_source(source)` and `copy_as=` for verbatim-source copy;
  `view.under_mouse()` for a context menu the host opens itself with
  `begin_popup_context_item` straight after `draw`; `view.block_source(...)`
  and `Document.sources` for the block-to-source map.
- **Tables.** Nothing to do for wrapping. `table_columns` and `with_columns`
  if columns are to be dragged.
- **Links.** `BareView(..., on_link=callback)`.
- **The transcript.** `StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.KEEP_STREAMED)`;
  `append(piece)` as tokens arrive, from the producer thread if there is one
  (`append` is the one call that is safe off the drawing thread, and it raises
  after `close()`); `close()` at the end of a message. `StreamView(stream, measure)`
  and one `draw` a frame in a scrolling child; it follows the tail until the
  reader scrolls up, and `follow_tail()` re-engages. `examples/chat_transcript.py`
  is that pane in miniature: finished messages as `BareView`s, one
  `StreamView`. Build finished messages with `references=False` so a message
  reads the same finished as it did streaming.
- **Before that exists**, the plan's bridge still stands: `BlockCursor`'s
  finalised blocks through `compose_blocks` one at a time.
- **To decide, not to code:** `KEEP_STREAMED` or `RESET`; whether a stray
  `<!--` is escaped before `append`; whether inline mathematics from a model
  matters, since no LaTeX parser exists here and one was refused.
  *(2026-10-07, second build: there is still no LaTeX parser, and there is a
  `$...$` subset above the engine, off by default. See the top of this
  document.)*

### Where the plan was wrong

The plan asked for this. Each is stated in full in the block of its phase.

| the plan said | the tree showed |
|---|---|
| ragged text through the total-fit breaker with shrink zeroed is first-fit and prefix-stable | only when no word overflows; ahead of an over-wide word it sets one word per line; and it costs 78 to 339 times a justified break |
| "If it passes, the live block needs no change to `linebreak.py`" | it passes where the proof covers and the conclusion does not follow; `linebreak.py` gained `LineBreakParams.first_fit` |
| commit every top-level block before the last | true only when the boundary is decided on complete lines; four constructs fail otherwise |
| `Theme.face_for` returns `PROSE_BOLD` for bold on a `CODE` base | true, and it also returned `Face.PROSE` for unemphasised text there; neither was reachable from the default theme |
| fontTools and the math patching load only when math is set | every face is measured through fontTools; what could be made lazy was the import (now at first measure) and the math font's patch-and-save (1062 ms, now only if the face is loaded) |
| hold a streaming table's widths (the lead's decision 7: a running maximum of apportioned widths) | that overflows the pane by more than 100 px; each live column is held at its widest natural cell instead |
| `Makefile:22-23` borrows pptmstr's venv | a dead fallback: `.venv` existed and was what ran; `scripts/shot.sh` had the same one |
| `README.md` says no click has reached a real frame | it did, and was stale already: `tests/test_document_view.py` had played a press and a drag into a bare-context frame |
| culled draw is about 10 ms a view | the figure it quoted was 10.5 ms; 13.2 to 13.9 ms was measured before the memo on a loaded machine, and 5.9 ms after it, re-run by the closer (5.1 ms once the per-glyph import was hoisted, one run by the gate closer) |
| there is no current figure for parse cost | one was printed, and it was the first parse in the process: 354 to 611 ms, mostly opening fonts. A re-parse is 10.7 to 12.5 ms |
| `docs/status.md` describes `PROSE_BREAKING` as tolerance 6000 | it said the constant was changing and to read the code; the shipped value was the one in its table |
| break each cell at its apportioned width | the apportioning had to change too: scaled down by one factor, a column of one-word labels is narrower than its word and wrapping cannot help |
| monospace advances may make batching lossless for code | exact at 12, 14, 16, 18, 20 px; all 94 characters off by half a pixel at 13, 15, 17 px |

And one that was the lead's, not the plan's: "no window can open in this
session". True of `DISPLAY=:1`, false of an Xvfb in a user namespace over TCP,
found by the builder told to work around it.

---

*The plan as written on 2026-10-06 follows. Its opening status line is quoted
above; the rest is unedited apart from the* **As built** *blocks.*

**Provenance: read-derived throughout.** It comes from an investigation in which
six agents read this tree and `../pptmstr`; none of them ran anything. Every cost
figure is quoted from this repo's own docstrings and docs, which call themselves
±60% and partly of a stale vintage (the sample was 23 blocks then, 37 now), and
all were taken on justified Roboto — nobody has measured the code face set
ragged. Claims marked *inferred* are deductions from the code that no test or
run has confirmed. Each phase therefore opens with the check that could change
it.

## The goal

**Full adoption: advtext replaces pptmstr's text rendering.** That is the
user's decision, taken on the grounds that the typography is the point. An
earlier draft of this investigation concluded that only narrow adoption was
justified; that conclusion was rejected and should not be re-derived. It scored
kerning, total-fit breaking and proportional faces as worth nothing because
pptmstr sets ragged Inconsolata today, which assumes non-adoption in order to
argue against it.

So the gaps below are a work list, not a case against. None of them is a design
dead end.

Two things this reverses, both on the pptmstr side and both the user's to
reverse: its recorded decisions "Copy-block replaces text selection" and
"Hand-rolled rendering" (`../pptmstr/planning/archive/2026-08-10-transcript-markdown.md`),
and its policy that "nothing at runtime opens a font file"
(`../pptmstr/pyproject.toml`).

One thing it reverses here: the `advtext/markdown.py` module docstring records a
streaming segmenter as "the wrong [answer] to ours: we are handed a whole file".
Phase 7 builds one. Phase 0 revises the docstring rather than building past it.

## What pptmstr has today

Its own renderer, in `../pptmstr/pptmstr/ui/`: `blocks.py` (a streaming block
segmenter, `BlockCursor`, whose invariant is "finalised blocks are never
revised"), `inline.py` (markdown-it for inline parsing only), `span_layout.py`
(greedy ragged wrap) and `rich_pane.py` (the only module touching ImGui; one
`add_text` per styled run). Inconsolata Medium and a vendored Bold at 16 px, no
italic. Colour carries meaning: palette roles for headings, quotes and segment
kinds, across several switchable themes. Tables are native `begin_table` with
wrapping cells. Copy is verbatim source per block. History is windowed to 400
lines. It treats about 1.7 ms per frame as too much for the live block.

It has three consumers of that renderer: the transcript pane (streaming) and two
DETAIL views (settled, one-shot documents). The DETAIL views are the natural
first landing — see Milestones.

## The plan

Per-block layout sits early (phase 2) because colour by block role, block
hit-testing, source copy and streaming all build on it.

### Phase 0 — housekeeping and baselines

- **Own environment.** `Makefile:22-23` borrows pptmstr's venv. Invert it, so
  pptmstr can depend on advtext.
- **ImGui floor.** The backend sets `text_no_pixel_snap`, which its own
  docstring dates to 1.92.9, while `pyproject.toml` says `>=1.92`. Find which
  `imgui-bundle` release first exposes the flag and set that.
- **Benchmarks.** Add a streaming row to `scripts/bench_reflow.py`: parse +
  compose + ship + index per appended word. The existing `_after_an_edit` starts
  its timer after `build_document` and excludes ship and index, and there is no
  current figure for parse cost. Add a `scripts/bench_draw.py` run for
  `Face.CODE` set ragged.
- **Mouse path.** `README.md` says no mouse click has ever reached a real frame.
  Exercise selection in a live window before anything depends on it.
- **Recorded decisions.** Revise the `advtext/markdown.py` docstring; add the
  adoption goal and the streaming reversal to `docs/decisions.md`.
- **Stale statements found on the way** (the tree is the evidence):
  - `docs/status.md` says `_FACES` is never cleared; `load_fonts` now clears it.
  - `docs/status.md` describes `PROSE_BREAKING` as tolerance 6000 with no
    emergency stretch; the code has `tolerance=1000, emergency_stretch=20 * UNITY`.
  - `scripts/render_litmus.py`'s docstring still says no window can open here.
  - `App.columns`'s docstring says a 980 px default window; `run` sets 1100.

> **As built (2026-10-07): done.**
>
> - **Own environment.** The `BORROWED` fallback is gone from the `Makefile`
>   and from `scripts/shot.sh`, which the plan did not name. With no `.venv`,
>   nine targets exit 2 naming `make bootstrap`
>   (`tests/test_makefile_env.py`, 17 tests). The plan's "borrows pptmstr's
>   venv" was a dead fallback here: `.venv` existed and ran. `make bootstrap`
>   itself was not run (no package index is reachable).
> - **ImGui floor.** `imgui-bundle>=1.92.900`. Read, through a summarising
>   fetch: Dear ImGui's changelog adds `ImDrawListFlags_TextNoPixelSnap` under
>   1.92.9; imgui-bundle 1.92.900 is "Dear ImGui v1.92.9b". Measured: the flag
>   exists in the installed 1.92.900. Not done: installing 1.92.801 and seeing
>   it absent. The 1.93 rename risk is under "Open".
> - **Benchmarks.** `scripts/bench_reflow.py` has the streaming row
>   (`time_stream_append`) and, since phase 7, the same word through
>   `StreamDocument` + `StreamView` beside it. Re-run by the closer,
>   `.venv/bin/python scripts/bench_reflow.py --widths 420 --repeat 5`, 420pt:
>
>   | word | whole document re-done: parse / compose / ship / index / total | through the stream: parse / layout / frame / total |
>   |---|---|---|
>   | 241 of 963 | 2.53 / 1.08 / 1.70 / 0.55 / 5.85 ms | 0.28 / 0.62 / 0.12 / 1.02 ms |
>   | 482 | 5.06 / 4.98 / 3.28 / 1.04 / 14.36 ms | 0.59 / 2.66 / 0.44 / 3.69 ms |
>   | 722 | 8.02 / 2.11 / 5.07 / 1.59 / 16.79 ms | 1.86 / 0.50 / 0.10 / 2.47 ms |
>   | 963 | 11.06 / 35.69 / 7.02 / 2.18 / 55.95 ms | 1.31 / 5.99 / 0.82 / 8.12 ms |
>
>   The plan's "`_after_an_edit` starts its timer after `build_document`" was
>   true and is now pinned by a test. Its "no current figure for parse cost"
>   was half true: the figure printed was the first parse in the process, 354
>   to 611 ms, mostly opening fonts. `scripts/bench_draw.py` has the
>   `Face.CODE` ragged run; per-glyph draw cost is the same as the default
>   theme's to within noise (3.61 against 3.62 µs, re-run by the closer).
>   `demo/sample.md` has no mathematics, so no bench says anything about
>   `Face.MATH`.
> - **Mouse path.** `scripts/mouse_probe.py` drives the real app through the
>   real `immapp.run`: eight gestures, 18 checks, in a real window under Xvfb
>   and in a bare context. 18 of 18 both ways, re-run by the closer. No defect
>   was found in the selection path. What "exercised" means is in section B:
>   events enter at `ImGuiIO`, no X pointer moved, no person dragged anything.
> - **Recorded decisions**, and the four stale statements: done. Each of the
>   four was confirmed stale by reading. The plan's wording on
>   `PROSE_BREAKING` was slightly off (see "Where the plan was wrong").

### Phase 1 — embed surface and fonts

Today the only ways in are the demo's `DocumentView` and private internals; the
smallest consumer is the 1413-line `advtext/ui/app.py`.

- **Font setup a host can call.** `load_fonts` lives in the demo module as a
  `hello_imgui` callback. Move it into the library as a function that registers
  faces on the host's atlas and returns the `FaceFont` callable.
- **Face registry.** `fontlib._FONT_FILES` is a closed table. Make it a
  role-to-path registry so a host can supply its own files (pptmstr's vendored
  Inconsolata-Bold).
- **Mono-bold face.** `Theme.face_for` (`advtext/style.py`) returns
  `PROSE_BOLD`, with Roboto metrics, for bold on a `CODE` base.
- **Size helper.** advtext draws at `size * (ascent + descent) / em`
  (`baked_size_px`); ImGui sizes are pixel height. One function converting a host
  ImGui size to advtext's em size, so text at "16" matches the surrounding UI.
- **Theme builder.** `Theme.build` hardcodes `Face.PROSE` and justified body.
  Let it take faces, size and alignment. (`Theme` is already a constructible
  dataclass; this is convenience, not capability.)
- **Block builders.** Blocks are built only inside the private `_Converter`.
  Add public constructors for prose and code blocks so a host can pass
  non-markdown content. Headings past h3 currently collapse.
- **Lazy math.** `fonttools` and the math-font patching load only when math is
  set.
- **Facade.** `advtext/__init__.py` has `__all__ = []`. Add a small stable
  import surface over `compose_blocks`, `ship` and `draw`.
- **`examples/minimal.py`.**

*Done when* the example renders a markdown string in a plain ImGui window without
importing `advtext.ui.app`.

> **As built: done. The "done when" was met and run in a real window**
> (`examples/minimal.py --frames 5` printed `frames=5 layouts=1 glyphs=674
> missing=0 rules=2`; it is a test). A fresh interpreter that loads the example
> has no `advtext.ui.app`, `hello_imgui` or `immapp` in `sys.modules`.
>
> - **Font setup:** `advtext.ui.fonts.load_faces()` returns a `LoadedFaces`,
>   which is the `FaceFont`. The demo's `load_fonts` is a thin caller; the five
>   tabs photographed with the old loader and the new had equal PNG hashes
>   (builder-5). A reload after re-registering a role left the stand-in role on
>   the old font; found by the lead running a reviewer's snippet, fixed.
> - **Face registry:** `register_font`, `unregister_font`, `registered_fonts`.
>   Registration clears every font cache and **cannot repair a document already
>   built** (kerns are in the material): register first.
> - **Mono-bold:** `Face.CODE_BOLD`, a seventh `Face`. Unregistered it is
>   backed by Roboto Bold, which is what bold on a code base was before. See
>   "Open". The plan's reading of `face_for` was true and incomplete:
>   unemphasised text on a `CODE` base came back `Face.PROSE` too. Neither case
>   was reachable from the default theme, so the demo's glyphs by face are
>   unchanged (3,811 / 310 / 206 / 24 / 11).
> - **Size helper:** `em_size_for_pixel_height(face, px)`. It needs the face:
>   a 16 px height is an em of 13.653 px in Roboto and 15.253 px in
>   Inconsolata.
> - **Theme builder:** `Theme.build(faces=, align=)`, `Faces`, `Faces.mono()`,
>   and `Theme.at_pixel_height(...)`, which also measures the list gutter in
>   the theme's own face: "10." in Inconsolata is 1.5 em against the 1.4 em
>   box measured on Roboto (confirmed, as the reviewer predicted). Which faces
>   count as monospace is a declared field, `Faces.monospace`, after review 2
>   found it inferred wrongly.
> - **Block builders:** `text_block`, `code_block`, sharing the converter's
>   code path. One emphasis per block; mixed-face runs from non-markdown input
>   are not offered. Headings: section A item 6.
> - **Lazy math:** not possible as the plan wrote it. Built instead: no
>   `fontTools` in `sys.modules` after importing the whole package (it loads at
>   the first measure), and `load_faces()` defaults to every face but
>   `Face.MATH`, whose patch-and-save measured 1062 ms cold. The demo still
>   loads all seven.
> - **Facade:** `advtext.__all__`, 58 names, resolved lazily. `import advtext`
>   loads exactly one module (`tests/test_facade.py`, fresh interpreter). The
>   plan asked for "a small stable surface over `compose_blocks`, `ship` and
>   `draw`"; it grew as each view landed (lead's decision 14) and whether 58 is
>   small is its builder's stated doubt.
> - Not built from the demo table: "bring your own fonts" as a demo. There is
>   no third font family in the tree to load.

### Phase 2 — per-block layout units

- **Check first:** selection indices must stay continuous across blocks. The
  existing selection tests are the gate.
- **Change.** `DocumentView.layout_for` re-ships and rebuilds `CommandIndex` and
  `SelectionModel` for the whole document on any change. Ship and index each
  block separately and stack by offset.
- **Bare view.** `DocumentView.draw` paints a light page sheet, caps and centres
  the measure at 2.25 alphabets, and claims the whole document with one
  `invisible_button`. Add a view that fills the pane width, paints no
  background, and leaves hover and context menus to the caller. The page sheet
  stays as the demo's presentation.
- **Adds.** A point-to-block hit test, and a block-to-source map.

> **As built: done.** The unit is not a block: it is a run of blocks that
> cannot be laid out apart, so a block quote's paragraphs are one unit.
>
> - **The gate held.** `UnitLayout.cmds == ship(compose(...))` command for
>   command on `demo/sample.md` at 300pt, 420pt and 467px, and every selection
>   query equals the flat model's over more than 500 points and 100 ranges
>   (`tests/test_units_layout.py`). `tests/test_selection.py` passed unedited.
> - **Measured** (builder-6, median of 30, 467 px, a script not kept): a
>   one-block edit to the last short paragraph went from 2.3 + 8.5 + 3.1 ms
>   (re-compose, ship, two indexes) to 0.37 ms; to the 635-node paragraph, from
>   11.3 + 8.8 + 3.2 ms to 11.1 ms, which is the line breaker. Steady-state
>   culling 0.218 to 0.045 ms a frame.
> - **Bare view:** `advtext.ui.bare_view.BareView`; `DocumentView` is now a
>   subclass that adds the page. Over the text it submits no item, so the
>   host's hover and context menus work; during a drag it submits an
>   `invisible_button`, because a `dummy`-only view lets a press on the text
>   drag the host's window (not in the plan; found by a control test).
> - **Adds:** `block_at` / `block_under_mouse`; `Document.sources`
>   (`BlockSource`, `SourceSpan`), kept beside the blocks so an edit that only
>   moves text leaves every cache hitting. Whole lines only.
> - Caller-visible: `Layout.index` is gone; `Layout.model` is a `UnitModel`.

### Phase 3 — colour and links

Independent of phases 4 and 5 once phase 2 lands.

- **Per-role ink.** `Palette` has one `ink`. Accept ink per block role (heading,
  quote, code) from the host's theme. With per-block units this needs no change
  to `Glyph`. It covers dark themes.
- **Per-run colour.** `Glyph` carries no colour, and `advtext/markdown.py`
  keeps colour out of the layout core on principle. The channel belongs beside
  the nodes, at draw time.
- **Design spike first:** `LinkSpan` indices point into a block's `material`
  tuple, which includes kerns, penalties and glue the breaker discards; shipped
  indices are dense over what was set. `shipout.py` says a backend can match
  the two and no code does. Per-run colour and links both need that map.
- **Links.** `LinkSpan` is produced and nothing consumes it. Underline, hover,
  click callback.

> **As built: done. Nobody has looked at a colour or an underline.**
>
> - **Design spike:** `advtext/spans.py`. The plan's claim was true: nothing
>   consumed `LinkSpan`. The map equals an oracle read off the breaker by
>   object identity on 324 block settings (builder; 36,922 mapped nodes
>   compared). It is coupled to `linebreak._line_nodes` building each line as
>   one contiguous slice; the oracle test goes red if that changes.
> - **Per-role ink:** `Palette.with_roles({BlockKind: colour})`,
>   `Palette.ink_for`, `DARK_PALETTE`, `draw_runs`. No change to `Glyph`, as
>   the plan expected. Each block of a multi-block unit takes its own role's
>   ink. `BlockKind.RULE` cannot have a role: rules take `Palette.rule`.
> - **Per-run colour:** `ColourSpan`, `colour_text`, `find_spans`,
>   `code_position`, `BareView.set_colours`. Material coordinates; for a code
>   block, columns after tab expansion. Prose has no source offsets, so
>   "source-text coordinates" exist for code only. Spans are keyed by block
>   number and are not moved when the document changes.
> - **Links:** live when the view has `on_link`; a press on a live link never
>   starts a selection (decision 16); a link across lines is one area; table
>   cells too. Styled only when live, which is how the demo page is unchanged.
> - Demos from the table: the gallery covers palettes, syntax colour and
>   clickable links. Not built: a table of contents that jumps to headings; a
>   find-in-document demo (the function exists).

### Phase 4 — draw cost

- **Change.** Memoise the per-glyph preamble in `imgui_draw._glyph`
  (`docs/guide/future.md` item 2). Culled draw is quoted at about 10 ms per view
  (`scripts/bench_draw.py`), nearly all per-glyph Python, and pptmstr shows
  several panes at once.
- **Check:** run `scripts/verify_advances.py` on `Face.CODE` at the intended
  size. If monospace advances are exact, run batching may be lossless for code
  blocks. The tree's standing conclusion is that batching is the wrong thing to
  build in general; this would be a narrow exception, and it is unverified.

> **As built: done.** The memo is per font key and lives for one `draw` call,
> so there is nothing to invalidate when an atlas is rebuilt.
>
> - **Measured, before and after** (builder-5, loaded machine,
>   `scripts/bench_draw.py --copies 1,2,4 --repeat 7`): full draw 37.99 to
>   16.22 ms at one copy, culled draw 13.86 to 5.99 ms. Interleaved in one
>   process, old module against new: ratio 0.415 to 0.421. **Re-run by the
>   closer, quiet machine: full 15.94 ms, culled 5.90 ms** for one copy,
>   culled 5.80 and 5.82 ms at two and four. That was before AF-final hoisted
>   a per-glyph import out of `_glyph` (section C). **Re-run by the gate
>   closer on the final tree, one run, load average 0.3: full 13.68 ms,
>   culled 5.12 ms** for one copy, culled 5.09 and 5.08 ms at two and four;
>   its builder's own run read 14.25 and 5.30 ms.
> - **Output identity:** old `draw` against new over 12 cases, 0 mismatches in
>   recorded calls and in vertex and index buffers (builder-5). Not a claim
>   about a screen.
> - **Check:** `scripts/verify_advances.py --size 16` on `Face.CODE`: 0 of 94
>   printable ASCII disagree. But it is exact because 16 is even, not because
>   the face is monospace: at 13, 15 and 17 px all 94 disagree by half a pixel.
>   Nothing was built (lead's decision 11).
> - `scripts/bench_draw.py`'s tables were re-taken by the closer and its three
>   reconstruction rows retired; `docs/guide/future.md` item 2 is marked built.
> - Not built: the many-panes stress tab.

### Phase 5 — tables

- **Change.** Cells do not wrap and columns cannot be resized (`_table_boxes`,
  `advtext/ui/__init__.py`). Break each cell as a paragraph at its apportioned
  width.
- Tables weigh more for pptmstr than their position here suggests: they were
  the deciding factor in its rejection of `imgui_md`.

> **As built: done, with a rule the plan did not ask for.** Section A items 4
> and 5 are the visible changes.
>
> - Cells wrap first-fit at natural spacing, ragged on the side the column's
>   alignment leaves free; a row is as tall as its tallest cell; cells hang
>   from a common first baseline. Every baseline of a wrapped table is on one
>   grid after a review found it was not.
> - **Column widths, three regimes** (`advtext.ui._column_widths`): the table
>   fits, and is apportioned exactly as before; too wide but the longest words
>   fit, and each column keeps at least its longest word; the longest words
>   alone exceed the measure, and the table is wider than the measure.
> - **The resize hook:** `with_columns(block, widths=... | fractions=...)`
>   returns a `SizedTable`; `table_columns(...)` says what composition would
>   use. Validated at the call. No demo drags a column.
> - Cost of the demo table: 0.56 ms fitting, 4.1 ms wrapped at 300 px
>   (builder-6, best of 20).
> - Reading order over wrapped cells is row by row, cell by cell.

### Phase 6 — copy and interaction

- **Failing test first.** `DocumentView._handle_copy` passes no `hard_breaks`,
  and the only callers that do are tests, so Ctrl+C over a fenced code block
  should join its lines with spaces. *Inferred*, and a defect in the shipped
  demo regardless of pptmstr.
- **Focus.** `_handle_copy` checks only the key and a non-empty selection; two
  views would both copy on one keypress. *Inferred.*
- **Host hooks.** Verbatim-source copy per block from the phase 2 source map,
  and a caller-owned context menu.

> **As built: done. Both inferred defects were real**: each test was written
> first and failed (a fenced block copied as `'line one line two\nline four'`;
> two views both wrote the clipboard on one keypress). A third prediction, that
> two views in one window collide on a fixed button ID, did not reproduce and
> is pinned as not reproducing.
>
> - Copy: section A item 3. Focus: section A item 11, by ownership of the
>   selection, because a view that submits no item never has ImGui's keyboard
>   focus.
> - **Host hooks** on `BareView`: `copy_as`, `selected_source(source)` for
>   copy-as-markdown (whole blocks: nothing maps a rendered character to a
>   markdown offset), `block_source`, `under_mouse()` / `pointed()` for a
>   caller-owned context menu. The view opens nothing itself.
> - No real window ran a `BareView` copy; `DocumentView`'s Ctrl+C in a real
>   window is the probe's.

### Phase 7 — streaming

The pipeline today: `build_document` parses the whole source; line breaking is
whole-paragraph (`_Breaker.run` picks the winner only at the paragraph end);
`_stacked`, `ship`, `SelectionModel` and `CommandIndex` are whole-document on
every change. `LayoutCache` is keyed on the block by value, so finished blocks
already hit it after a naive re-parse.

- **Stability test first.** For every word-prefix of the 635-node sample
  paragraph, break with `right_skip=RAGGED_RIGHT` and interword shrink zeroed,
  and assert all lines but the last are unchanged from prefix *k* to *k*+1.
  The claim that the existing breaker is then first-fit and prefix-stable is a
  paper proof about tie-breaking (`linebreak.py:640-643`), not an observation;
  the emergency pass, for a word wider than the measure, is where it could
  fail. Run it again with normal glue to count how often shrink flips a line.
  If it passes, the live block needs no change to `linebreak.py`.
- **`advtext/stream.py`.** A streaming document with `append(text)`, committed
  blocks (append-only, frozen) and a live tail.
- **Commit boundary from markdown-it.** Re-parse from the start of the last
  top-level block and commit every top-level block before it. Do not use a
  "blank line + fence state" scanner: a numbered item followed by an indented
  paragraph or fence parses, alone, as a top-level paragraph or indented code,
  and that is the most common shape in model output. `demo/sample.md` has no
  such construct, so a demo built on it would hide the failure — add one.
- **Disable link reference definitions** in the streaming parser; they
  retroactively change earlier blocks.
- **Incremental tail.** Only the live block is re-shipped and re-indexed. At
  about 9 ms per 37 blocks and growing linearly, whole-document ship and index
  outweigh everything else on a long transcript.
- **One relayout per frame**, however many tokens arrived.
- **Follow-tail scrolling.** Check for a vertical snapping hazard: each line's
  top is snapped separately and the leading is not a whole number of pixels, so
  a fractional or changing scroll origin could alternate 21/22 px gaps between
  settled lines.
- **Bridge, if wanted sooner.** pptmstr's `BlockCursor` already has the
  never-revise invariant; its finalised blocks can go through `compose_blocks`
  one at a time before `advtext/stream.py` exists.

> **As built: done, on a different breaker than the plan expected. Two shapes
> of input are still linear: a long paragraph inside a list item or quote, and
> a table inside a list item or quote ("Open").** A long top-level live table
> was a third until the last task; see the bullet on it below.
>
> - **Stability test first:** `tests/test_stream_stability.py`. On the 635-node
>   paragraph (498 characters, 101 glue, 36 kerns, no penalties; 101 steps),
>   ragged with shrink zeroed: **0 of 101 flips at 270, 330, 420 and 520 pt**,
>   so the paper proof holds where it applies. **It fails where a word is wider
>   than the measure**: twenty words in two lines become twenty one-word lines
>   when a 60-character token arrives, and the plan's own paragraph does it
>   below 253.8 pt (its thirteenth word is that wide). With normal glue the
>   count the plan asked for: 16, 2, 0 and 6 flips of 101 at 270, 330, 420 and
>   520 pt. And one ragged break of that paragraph took 2.2 to 9.4 s against
>   27 to 42 ms justified (two builders, independently:
>   `.venv/bin/python scripts/bench_reflow.py --ragged`).
> - **So `linebreak.py` did change:** `LineBreakParams.first_fit`. Same legal
>   breakpoints, same line assembly, no look-back. 0 of 101 flips at five
>   widths including the over-wide case; 5.5 to 9.0 ms where total-fit ragged
>   took 2.5 to 9.3 s; equal to total-fit ragged on all 34 sample blocks once
>   shrink is zeroed, and different on 11 of 34 with glue as emitted, which is
>   why non-justified text is also set at natural width (section A item 1).
>   That 11 is first-fit against total-fit ragged; against the shipped
>   `Align.LEFT` output the change is 2 of 34 blocks at 420 pt.
>   A penalty strictly between the infinities is ignored in this mode.
> - **`advtext/stream.py`:** `StreamDocument.append / close / committed / live
>   / blocks / sources / revision`. Parsing is deferred to the first read, so
>   one relayout a frame costs one parse however many pieces arrived.
> - **Commit boundary:** from markdown-it, **on complete lines only**. Without
>   that amendment four constructs fail (`para\n#` then `tag`; a fence opener
>   then a backtick; `<p` then `ath`; a half-typed table delimiter row). The
>   stream is compared with one whole parse after every piece: 51 adversarial
>   sources x 5 chunkings x 2 policies. It rests on four claims about
>   CommonMark's block structure that are argued and tested, not proved.
>   `demo/stream.md` has the numbered-item-plus-fence construct;
>   `demo/sample.md` was not edited because the benchmarks are pinned to it.
>   Two kinds of block commit earlier than "when the next block's first line
>   ends": a followed top-level fence when its closing line ends, and a
>   followed top-level table on the first complete line that is not a row.
> - **Reference definitions** are off in the stream, through a second parser.
> - **Cost inside one long container** (not in the plan; found by a reviewer):
>   a 300-item list cost 2 rising to 43 ms a piece, a 600-line open fence 1.4
>   rising to 32 ms. After: 0.34 / 0.36 ms and 0.06 / 0.07 ms, first and last
>   tenth (builders 11 and 12). View side, an open fence at 600 lines: 106.8 ms
>   a line to 1.9 ms (builder-13).
> - **A long live table** (not in the plan; measured by the closer, then
>   built): a row appended to a top-level table cost 3.0 ms at 10 rows and
>   64 ms at 200; after, 0.8 to 1.2 ms from 10 to 200 rows where the table
>   fits its pane (builder-15). Section C has the table and what is still not
>   flat. Unreviewed.
> - **Incremental tail:** `advtext.ui.stream_view.StreamView`. Per append, at
>   most one ship and one index, asserted by counting over a 440-piece replay.
>   The plan's "about 9 ms per 37 blocks" for ship and index was right: 7.02 +
>   2.18 ms at the last word in the table under phase 0.
> - **One relayout per frame:** 60, 1 and 139 pieces between layouts gave one
>   layout each.
> - **Follow-tail and snapping:** follows while at the bottom, releases on
>   scroll-up. The hazard is real for a fractional origin: moving it by 0.25 /
>   0.5 / 0.75 px changes 21 / 43 / 44 of 54 line gaps. ImGui 1.92.900 handed
>   the view a whole-pixel origin on every one of 417 frames. The lead then
>   decided the view snaps its own origin anyway, since a host can set a
>   fractional cursor.
> - **`append` from a producer thread** lost a piece in 3 of 30 two-thread
>   trials before a lock was added and 0 of 30 after.
> - **Bridge:** not needed here and not built; it is pptmstr-side.

Open, and not settled by this plan:

- **Re-set on commit, or keep streamed breaks.** A finished paragraph can be
  re-set justified (one visible jump per paragraph) or keep its ragged streamed
  breaks (no jump). A taste call; make it a flag and look at both.
- **Table jitter.** `_apportioned` rescales every column as any natural width
  changes, so a streaming table moves every earlier row on each token. Needs a
  policy for holding widths until commit.
- **Selection across a re-break.** A change in line count renumbers reading-order
  indices after it, so a selection reaching into the live block, or past a block
  re-set on commit, probably does not survive. *Inferred.*

> **As built: all three settled, by agents. Each is an agent decision awaiting
> yours** (`docs/decisions.md`, "Agent decisions taken while the plan was
> built").
>
> - **Re-set on commit:** a flag, as asked. `CommitPolicy.KEEP_STREAMED`
>   (default) commits the ragged block exactly as last shown;
>   `CommitPolicy.RESET` commits the block built with the host's theme. The
>   default is KEEP because it moves nothing, which is a statement about
>   change. Measured on three paragraphs of plain prose: 0 settled lines moved
>   under KEEP at two widths and two rates; under RESET, movement at exactly
>   the three commits. **Nobody has looked at both**, which is what the plan
>   asked for. `examples/stream_replay.py` has the toggle and the counter.
> - **Table jitter:** while a table is live each column is held at the widest
>   *natural* cell it has had, for as long as that fits the measure; then the
>   default apportioning takes over. At commit: `RESET` apportions once,
>   normally; `KEEP_STREAMED` keeps the held widths and measures once more at
>   the commit, so the result does not depend on how the text arrived. The
>   lead's first rule (a running maximum of apportioned widths) overflowed the
>   pane by more than 100 px when run.
> - **Selection across a re-break:** survives as the same text, or is cleared;
>   never silently other text. Each end is restated as the n-th glyph of its
>   unit and carried if the units set the same characters. A selection reaching
>   into the live tail is kept through further text and through the commit;
>   markup closing late under it cuts it back to what still carries. The
>   plan's inference was right: raw indices did not survive (500 to 400 px
>   changed the index count from 5286 to 5295 and slid the text). This is not
>   the lead's decision 8 as its file still words it ("cleared on `RESET`"):
>   a selection is carried through a `RESET` commit when the characters are
>   the same. The anchor of a drag still in progress has its own rule
>   (`carry_caret`, section A item 10), added after the last review.

## Milestones in pptmstr

- **DETAIL panes after phases 1–5.** They are settled documents, which is the
  whole-file model, so streaming does not block them. pptmstr's `_deliverable`
  promises "not tailed and not clipped" while `rich_pane.draw` windows to 400
  lines; advtext's culling removes that limit.
- **Transcript pane after phases 6–7.**

The pptmstr-side changes are outside this repo and not planned here.

> **As built:** nothing on the pptmstr side, by design. Section D lists the
> public names each milestone uses. The 400-line window is not needed: a view
> culls to what is visible (culled draw is flat from one to four copies of the
> sample, phase 4).

## Demos this unlocks

Demos already buildable today, independent of this plan, are not listed.

| Phase | Demo |
|---|---|
| 1 | Minimal embed example |
| 1 | "Bring your own fonts": one document in several face sets |
| 2 | Block inspector: hover a block for its source, cache hit and layout time |
| 3 | Theme gallery: one document in several palettes, including dark |
| 3 | Syntax-highlighted code blocks |
| 3 | Clickable links; a table of contents that jumps to headings |
| 3 | Find-in-document with highlighted matches |
| 4 | Many-panes stress tab with a per-frame cost readout |
| 5 | Resizable table tab showing cells re-wrapping |
| 6 | Select across blocks, copy as rendered text or as markdown source |
| 7 | Stream replay: tokens-per-second knob, commit-policy toggle, a counter of lines that moved |
| 7 | Mock chat transcript: several messages, one streaming |

Build first: the minimal embed example, the theme gallery, and stream replay.
The mock chat transcript is the most valuable later one — it is pptmstr's
transcript pane in miniature, and lets the typography be judged before pptmstr
is touched. Stream replay's counters report change, not quality
(`docs/visual-review.md`).

Find-in-document matters for pptmstr too: its search currently demotes rich
mode to raw lines.

> **As built:** `examples/minimal.py`, `examples/theme_gallery.py` (four
> schemes: page, dark, terminal, notes; live links; a syntax-coloured fence),
> `examples/stream_replay.py` and `examples/chat_transcript.py`. They are
> examples and not tabs of the demo app (lead's decision 5), and each imports
> the library from `advtext` only. Run one with
> `.venv/bin/python examples/theme_gallery.py`. Not built: bring-your-own-fonts,
> block inspector, table of contents, find-in-document, many-panes stress tab,
> resizable table tab, and a select-and-copy demo as such.

Not unlocked: inline math from model output. It needs a LaTeX parser, which
this repo has refused (`advtext/ui/formulas.py`, `advtext/math/atoms.py`).

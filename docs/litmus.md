# The litmus tests

> **2026-10-12:** the package this document calls `advtext` was renamed `imscribe` (`advtext/…` is `imscribe/…`, `import advtext` is `import imscribe`). Nothing below was changed for it.

`docs/decisions.md` names two tests the project either passes or does not. This
is what happened when both were run, what the artifacts show, and what is still
wrong. It was written after looking at the rendered output rather than at the
test summary, and the section at the end lists the defects rather than the
achievements, because a write-up with no defects in it has not looked.

Reproduce everything with:

    make svg        # writes artifacts/ -- no GPU, no display, no ImGui
    make check      # the assertions, including tests/test_litmus.py
    make shot-all   # the same claims photographed out of a real window

`artifacts/` is gitignored on purpose: these are outputs, and the script that
makes them is the thing under version control.

---

## First, the boundary of the claim

> **This section has now been wrong twice in the same direction.** It once said
> "Nothing in this repository has been rendered by ImGui" and that the advance
> disagreement was unmeasured; both were false, and the correction at the top of
> `docs/decisions.md` is the authority for that one. It then said "Nothing has
> ever been composited to a screen", which was true of the sandbox this project
> was built in and is **false here**. This is the twice-corrected version.

**A window needs a display. A frame does not.** `imgui.create_context()`
allocates plain memory, `ImFontAtlas` bakes glyphs on the CPU through
stb_truetype, and `new_frame`/`render` build vertex buffers in RAM. Only
compositing those buffers onto a screen needs a GPU. So the ImGui backend was
reachable even from a sandbox with no display, and it was reached:
`tests/test_imgui_draw.py` ships the litmus formula through
`advtext.backends.imgui_draw.draw` inside a real frame and asserts on the vertex
buffer it produces.

**And it has since been composited.** `DISPLAY=:1` is live on this machine —
X.Org 1.22.1.9, direct rendering on an AMD Radeon through Mesa 22.3.6 — and
`make shot` runs `advtext.ui.app.run` through the real `immapp.run` and grabs
the framebuffer. Both litmus tests have been photographed as well as asserted:
the Document tab shows the markdown set on a page, and the Formula tab shows the
display sigma large with stacked limits beside the text-style one with scripts
at its side.

**What that leaves:** this sentence used to begin "no click has ever reached a
real frame". Since 2026-10-06 one has, from a script: `scripts/mouse_probe.py`
posts eight gestures into the real app in a real window on Xvfb and all
eighteen of its checks on the selection and the clipboard pass. No person has
dragged a selection, the events enter at ImGui's input queue rather than at the
X server, and the photographs are still of one GPU, one driver and one X
server. `docs/imgui-risks.md` is the ordered
list, and its item 1 — compositing — is now marked settled rather than open.

What the artifacts below demonstrate is the **layout engine**: the box-and-glue
model, the line breaker, the math list translator, ship-out, the selection model
and the SVG backend, exercised end to end with real font files, real `GPOS`
kerning and real OpenType `MATH` data. The ImGui backend consumes exactly the
same `DrawCmd` list, and that list is now known to survive the crossing.

The advance disagreement is **measured, not hedged against**:
`scripts/verify_advances.py` finds 26 of 44 glyphs disagreeing at 16px, worst
single glyph 0.45px, about 6px accumulated across the sample. That is why the
backend positions one glyph at a time, and it is now a number rather than an
argument. `docs/imgui-risks.md` is the list of what remains open, in order.

---

## Litmus test 1 — multi-type markdown, laid out and selectable

**Claimed:** headings, paragraphs with bold/italic/code, lists, a block quote,
fenced code, a rule and a table, laid out as one document and selectable with
the mouse.

**Artifacts:** `markdown.svg`, `markdown-debug.svg`, `selection.svg`.
`demo/sample.md` is the source and is about this project, so the line breaking
is exercised on real word-length distributions rather than on lorem ipsum.

The page comes out 492 × 1789 pt — a 420pt measure inside a 36pt margin — and
ships **5378 draw commands**: 4362 glyphs, 89 lines, 924 interword glues and 3
rules. Every one of those glyphs is a separate `<path>` with its own outline data
and its own transform; no `<text>` element appears anywhere, which is the whole
point. If a glyph is in the wrong place, it is there because we put it there.

(Those counts were re-measured for this revision and the document has grown
twice. The revision before last recorded 4215 commands, 68 lines, 702 glues and
**2** rules; the last recorded 4226 / 72 / 708 / 3 at a height of 1459 pt. The
strut accounts for the first jump and the third rule is the block-quote bar. The
second jump is content: `demo/sample.md` went from 23 blocks to 37 so the demo
would have something worth reading in it, which is also why every timing in
`docs/status.md` section 4 is larger than it was.)

### What the output shows, looked at rather than asserted

**Justification is genuinely flush.** Every justified line ends exactly on the
right margin. Not approximately: the last item on a full-measure line lands on
the margin with **zero** residue, and no glyph in the document crosses it. That
is §625's discipline working through four modules — accumulate the total natural
stretch, multiply by the box's ratio once, round *that*, take a difference
against the previous rounded total. Rounding each space independently instead
makes the right edge waver by a scaled point or two per line, which reads as a
bug in the line breaker, where nobody will find it. `markdown-debug.svg` shows
this directly: the blue and orange rectangles are the interword spaces, coloured
by whether justification stretched or shrank them, with a tick at the width they
would have had on their own.

**Interline glue works and is the reason the prose looks set rather than
stacked.** Within a paragraph, consecutive baselines sit exactly one
`\baselineskip` apart whatever the ascenders and descenders on each line — the
commonest baseline-to-baseline distance in the document is the body
`\baselineskip` to the scaled point. The red lines in the debug overlay are the
baselines and they are evenly spaced; the green boxes around them are not,
because line boxes vary with their contents and baselines do not.

**Emphasis is real faces, not a colour shift.** Roboto ships Regular, Bold,
Italic and Bold-Italic, so **bold**, *italic* and inline `code` are four
different files rather than one file and a heuristic. pptmstr has to fall back
on a colour shift because Inconsolata has no italic upstream
(`pptmstr/ui/theme.py:791-802`); this document does not.

**Kerning is present and is a thing ImGui cannot give us.** The pair kerns come
out of `GPOS`: `To` is −0.48 pt at 10 pt, `AV` −0.42 pt, `Wa` −0.16 pt. ImGui
exposes no route to those numbers at all.

**Lists hang correctly.** A marker is packed at its natural width and the whole
first line is re-packed as `[marker, gap, line]`, so the box starts to the left
of the text's indent and every continuation line still lines up. That is TeX's
`\item`, and the alternative — an indent plus a prefix — makes a two-digit
ordered marker push its own first line out of alignment with the rest of the
item.

**Ragged-right needed no new machinery.** Headings and list markers are set with
`\rightskip = 0pt plus 1fil` and nothing else. Because the `fil` outranks every
finite stretch on the line, the interword spaces are never asked to move, which
is why ragged text has even colour and justified text does not. Centring is the
same trick with a `fil` at each end. There is no alignment enumeration anywhere
in the renderer.

**A rule suppresses interline glue on both sides of itself**, which the audit
caught as correction C2 and which is visible here. The thematic break and the
table's header rule both needed explicit vertical skips around them, because
§679 gives them none. Implemented the other way, every rule in the document
would have had a full `\baselineskip`-derived gap under it and none above it,
and it would have read as "my rules are inconsistently spaced" rather than as a
bug.

### Selection

`selection.svg` shows a drag from a quarter of the way along one line to
three-quarters of the way along a line five lines later, at word granularity.
The range is driven through `advtext.selection` with two points; no rectangle
was drawn by hand.

The highlight starts mid-line, covers every intervening line edge to edge —
including a heading, at the heading's own larger line height — and ends mid-line.
**Every body-line fragment has exactly the same height**, whether or not the
glyphs on it happen to have descenders, because the rect is sized to the line
box rather than to the ink. A selection sized to the ink makes a line of
lowercase text visibly shorter than the one above it, and that is the detail
that makes hand-rolled selection look wrong without anyone being able to say
why.

Copying the selection joins the wrapped lines with **spaces, not newlines**: a
paragraph wrapped into five lines is one paragraph, and freezing this column's
width into the clipboard would show the wrap points as ragged hard breaks
anywhere they were pasted.

*(2026-10-07.)* That is still how a wrapped line copies. What changed is
everything that is not a wrap: a view's copy now puts a blank line between
blocks, a newline between code lines and between the items of a list, and a tab
between table cells, read from the blocks rather than supplied by a caller.
And a highlight no longer covers the blank fill at the ends of a line, so in a
view "edge to edge" holds for full lines only. `selection.svg` is drawn by
`advtext.selection` directly and its artifact was not re-examined.
`docs/adoption-plan.md` section A has both changes with their measurements.

---

## Litmus test 2 — a display-size summation

**Claimed:** `\sum_{i=1}^{n}` with limits above and below a display-size
operator, rendered from real math font metrics — "a real larger glyph selected
from real font data, rather than the body glyph scaled up"
(`docs/decisions.md`).

**Artifacts:** `sigma.svg`, `sigma-compare.svg`.

`sigma-compare.svg` is the one that settles it, and it is a separate file
because this is the claim most likely to be doubted. It shows the same formula
twice: display style above, text style below. In display style the operator is
large and the limits are stacked over and under it; in text style the operator
is small and the limits sit beside it as ordinary scripts. That is `\limits`
versus `\nolimits` falling out of the style, with no flag passed.

**The display operator is a different glyph, not a bigger size.** Latin Modern
Math's vertical variant chain for U+2211 is `[summation, summation.v1]`, and
`summation.v1` **has no codepoint in the font at all** — 227 of that font's
vertical variants are unencoded and it uses no Private Use Area. So the
dishonest implementation is easy to reach by accident: look the operator up by
codepoint, fail to find a variant, and set U+2211 at a larger size. It looks
almost right.

`tests/test_litmus.py::test_the_display_sigma_is_a_larger_glyph_and_not_the_body_one_scaled`
rules that out precisely. It finds the operator glyph in each rendering,
resolves it back through `advtext.fontlib.glyph_name` to the name the *font*
gave it, and asserts that display reached `summation.v1` while text reached
`summation` — and that both were shipped at the same size, so the height
difference is the glyph and not the scale. A scaled-up body glyph fails that
test even though its rendered height would pass a naive height comparison. The
variant is 1401 font units tall against the body glyph's 1001, and the shipped
ink is about 40% taller.

**The limits are centred on the operator, not left-aligned with it.** "n" and
"i=1" are very different widths, so a stack that shared a left edge would be
obvious; the test asserts the two limit groups share a centre line with each
other and with the operator's own advance centre, to within a point. Looking at
`sigma-compare.svg`, they do.

**The whole formula is tall and narrow in display style and short and wide in
text style** — the packed `hpack` box at the body size (12.045 pt) is **17 pt
wide by 33 pt tall** in display style against **26 pt by 15 pt** in text style.
That shape difference is the stacking, measured. An earlier revision of this file
quoted the widths as 27 and 36; those could not be reproduced and have been
replaced with the box dimensions, which can — the height figures were already
right and are unchanged.

---

## What is still wrong

**Three findings that were in this list have since been fixed**, and they are
recorded at the end rather than deleted — a defect list that silently loses
entries cannot be told from one nobody re-checked.

### 1. `\tolerance=200` is unreachable without hyphenation, and the cost is real

This is the largest finding and it is a direct consequence of a scope decision.

Set with `plain.tex`'s parameters — `\pretolerance=100`, `\tolerance=200` — this
document produces **seven overfull lines, the worst by 180.9 pt**, which is text
sitting in and past the margin. The cause is not a bug in the breaker: for
several paragraphs *no* breaking exists in which every line's badness stays
under 200, because without hyphenation the breaker cannot cut inside a word.
When no feasible breaking exists, §854's last-resort escape forces a break
wherever the scan happens to be standing, and the result is worse than a loose
line.

The artifacts are rendered with `\tolerance=1000` and `\emergencystretch=20pt`,
which removes **every** overfull line. That is exactly what a plain TeX user
does when hyphenation is off, and the price is visible: 10 of 75 lines come back
loose enough to count as underfull, against 3 at the tighter setting. Compare
the first paragraph of `markdown.svg` — its first line has noticeably wide word
spacing — with what the same paragraph would look like hyphenated.

|                              | lines | overfull | worst    | underfull | loose | tight |
|------------------------------|------:|---------:|---------:|----------:|------:|------:|
| plain TeX defaults           |    72 |        7 | 180.9 pt |         3 |    13 |    17 |
| as rendered (1000 + 20 pt)   |    75 |        0 |     0 pt |        10 |    20 |    12 |

Counted over `TextBlock`s only, by `line.fitness`, at the 420 pt measure — the
same method `tests/test_litmus.py::test_no_line_in_the_document_is_overfull`
uses, so the table and the assertion cannot drift apart. (Two earlier revisions
recorded 5 overfull / 181 pt / 7 underfull, then 6 / 180.9 / 8. The strut, the
wider list gutter and then a much longer `demo/sample.md` changed the document;
the shape of the finding did not.)

**This is the honest price of `docs/decisions.md` scoping hyphenation out**, and
it is worth stating plainly rather than burying: the output is *good*, and it is
not as good as TeX's, and the gap is one feature wide.

**And that has stopped being a hypothetical.** `\tolerance=1000` with 20 pt of
emergency stretch was a taste decision an agent made, and the sentence that used
to close this item was "no human has reviewed it". One has now, and said the
loose lines are not acceptable — they pointed at two first-words-of-line in the
Columns document. So the price above is a price somebody has now refused to pay,
`advtext.ui.PROSE_BREAKING` is expected to change, and **every figure in the
table above will need re-deriving when it does**. `docs/status.md` section 4 has
the follow-up measurements, including the one that matters most: at the
three-column measure the loose lines are far worse than at the one-column
measure, so the tolerance is not the only thing in question.

### 2. Links are not visually distinguished

*(2026-10-07: still true of `markdown.svg` and of the demo page; no longer
true of the library. A view constructed with an `on_link` callback underlines
and colours its links and follows a click, through `advtext/spans.py`. The SVG
backend does not consume it. Nobody has looked at the underline.)*

`advtext.markdown.LinkSpan` records where every link is, in reading-order
indices. **Nothing consumes it** — grep the tree and the only mentions outside
`markdown.py` are two docstrings describing what a consumer would do.
`[the line breaker](advtext/linebreak.py)` renders as ordinary prose in
`markdown.svg`. This is by construction rather than by oversight —
`advtext.shipout` carries no colour, for the reason its docstring gives — but the
consequence is that the document's links are invisible, and closing it means the
renderer matching `LinkSpan` ranges against command indices the way selection
highlighting already does.

### 3. A list item that used to fit now breaks, and the gutter is why

Widening `list_indent` from 1.5 em to 1.9 em — to clear a two-digit ordered
marker, which used to collide with its own text — took **0.4 em off the measure
of every list item in the document**. The marker now clears the gap exactly,
pinned at the scaled point by
`tests/test_litmus.py::test_a_two_digit_ordered_marker_keeps_the_full_gap_before_its_own_text`.
Item 2 of the ordered list used to fit on one line and now breaks,
with its first line set noticeably loose. Rasterised and looked at, not inferred.

The builder who made the change reported it against their own work, and named
the alternative they did not take: sizing each list's gutter from its own widest
marker would give the sample's short list a *narrower* gutter than it started
with and the item would fit with room over. That is better typography and more
work, and it is a live option rather than a closed question.

### 4. Cells do not wrap

*(2026-10-07: they do now, where a table is wider than its measure. The sample
table fits its measure in both artifacts and in the demo at its default width,
so nothing here shows a wrapped cell. The entry below is as it stood.)*

A table cell wider than its share overflows rather than wrapping, because
breaking text inside a cell means running the line breaker per cell against a
width that depends on the breaking — which is `\halign`'s real problem and out of
scope. The sample table was written narrow enough that this does not bite; a
wider one would.

### 5. The artifacts are large

`markdown.svg` is 1.55 MB and `markdown-debug.svg` 1.76 MB, because every
occurrence of every glyph carries its own full outline. Deduplicating with
`<use>` and a `<defs>` block would cut it by an order of magnitude and would make
the file much harder to read next to the command list that produced it. The trade
is recorded in the backend's docstring; it is worth revisiting only if somebody
starts diffing artifacts routinely.

### 7. The column layout has no artifact

`make svg` writes five files and none of them is a column. The newest capability
in the tree — `advtext/columns.py`, which is what the Columns tab flows through
— is therefore the one with no display-independent evidence in `artifacts/`,
where every other claim in this document has one. `scripts/render_litmus.py` is
where a `columns-2.svg` and `columns-3.svg` would be added, and it is a small
change: `compose_into_columns` already returns packed boxes and the SVG backend
already consumes what `ship` makes of them. (Files by those names may be sitting
in `artifacts/` — they were made by hand and `make svg` does not reproduce them,
which is precisely the problem.)

### 6. Sentence spacing is assertive, and it is the defect the user actually saw

The space after a full stop is noticeably wider than an interword space, because
`advtext.style.space_factor_after` implements TeX's `\sfcode` behaviour. It is
correct, it is what TeX does, and it is a house-style choice a modern reader may
not want. It is a one-line change in `style.py`.

This item used to end "and nobody has been asked". Somebody has now looked at
the output and called two words "pretty bad", and the sentence space is why:
it carries 1.33× the natural width of a word space and **3.00× the stretch**, so
on a stretched line it sets up to three times wider than its neighbours rather
than one and a third. `docs/status.md` section 4 has the measurement. The
consequence worth stating here is that it was mistaken for a line-breaking
problem, and lowering the tolerance would have reported success while the gap
stayed on screen.

---

## Fixed since this file was first written

Kept rather than deleted, because a defect list that loses entries silently
cannot be distinguished from one nobody re-checked. Each was in the numbered list
above and is not any more.

**`advtext.ui.compose` rendered text in the margin.** It used
`LineBreakParams()`'s plain-TeX defaults and put 40-odd glyphs past the right
edge of `demo/sample.md`, so the ImGui demo would have laid the document out
worse than the SVG artifacts did. `compose` now defaults to `PROSE_BREAKING` and
`tests/test_litmus.py::test_no_line_in_the_document_is_overfull` holds it there.

**There were two document composers.** `advtext.ui.compose` and a
`layout_document` inside `scripts/render_litmus.py` both turned a `Document` into
a packed vertical box and disagreed about tolerance, table column widths and the
air around a header rule — so the demo and the artifacts were laid out by
different code, which is exactly what the two-backend architecture exists to
avoid. The script now calls `advtext.ui.compose` and the duplicate is gone.

**Block quotes were indented and not barred.** `Theme.quote_rule_thickness`
existed and was unused, because drawing the rule needs the quote's total height
and so needs a second pass. The pass exists now: the quote in `markdown.svg`
carries a 1.81 pt bar 65 pt tall down its left edge, which is the third of the
three `RuleRect`s the document ships.

**Tables stopped short of the measure.** Columns were apportioned by natural
width and scaled *down* only, so the table ended about 150 pt inside the margin
the prose ran to. Measured now, the table's header rule is 420.00 pt wide against
a 420 pt measure — it fills it exactly. (The *other* half of that finding, cells
not wrapping, is not fixed and is item 4 above.)

**A line's height was the ink of its tallest glyph, not the line box**, while
three separate docstrings claimed the opposite and the test named for it could
not fail. A strut now sets every line. That fix turned up a second defect nobody
had named: block separation was being eaten by the missing strut, so two
consecutive paragraphs sat *closer together* than two lines of the same
paragraph, and by an amount that varied with whether the last line happened to
end in a descender. Both are why the document is 8.8% taller than the counts at
the top of this file used to say.

---

## What the assertions cover

`tests/test_litmus.py` runs the whole pipeline against real fonts and pins:

- the display sigma resolving to `summation.v1` and text to `summation`, at the
  same size, with a real height ratio;
- the limits centred over and under the operator rather than left-aligned;
- the sample document containing every block kind the litmus test names — so the
  document cannot quietly stop being multi-type;
- **no overfull line anywhere in the document**, which is the assertion that
  keeps finding 1 from regressing silently;
- every full-measure line's set glue landing inside its right edge;
- the commonest baseline-to-baseline distance being the body `\baselineskip`;
- all five artifacts parsing as XML, containing real outline paths and no
  `<text>` element;
- the debug overlay adding structure and leaving the glyphs byte-identical;
- selection rects spanning several lines at a consistent height, and copied text
  containing no newline.

They cover the ImGui backend's geometry too: `tests/test_imgui_draw.py` runs
`draw` in a real headless frame and asserts one textured quad reaches the vertex
buffer per glyph, including the display summation, and — since the sub-pixel
work — that no quad corner is fractional and no quad is resampled, with a
deliberately wrong advance-rounding implementation next to it asserted to fail.
An earlier revision of this line said the suite could not cover anything ImGui
draws at all, and that was wrong.

What they barely cover is the screen. `tests/test_shot.py::test_a_real_shot_of_the_real_app_is_a_valid_non_blank_png`
opens a real window and asserts the PNG has more than 100 distinct colours,
which catches a window that composited nothing and a window that drew text in
the background colour — the two failures that actually happened. It catches
nothing finer. **No test asserts that anything is in the right place on a
screen**, and every visual claim in this document was made by a reader looking
at an image. That is the right way to judge typography and it is not a
regression test: a change that moved the whole page thirty pixels left, or set
it in the wrong face, would pass the entire suite.

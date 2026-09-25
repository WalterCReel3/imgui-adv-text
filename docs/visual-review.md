# Visual review

`docs/status.md` section 5 is about tests that could not fail. This file is its
sibling for appearance: **claims about how the output looks that could not have
been wrong, and were.**

It exists because visual self-assessment failed four times in this project, three
of them by the lead, and each failure was published as a finding before anyone
noticed. The rules below are short because they are all reactions to a specific
incident, and each one names it.

---

## The standard

**1. A metric establishes *change*. It never establishes *quality*.**
Report which glyphs differ, by how many levels, in which direction. "Looks
better" is not a result. Judgement of appearance belongs to the user, who has
overruled a measured claim from an agent every time they have been shown one.

**2. A visual claim must be accompanied by the artifacts it is made from, and
those artifacts must name their build.** `scripts/visual_diff.py` stamps the
build, the tab spec, and the requested and captured sizes into every PNG it
writes, and `compare` refuses an unstamped file.

**3. A reviewer of appearance must have a shell and must render its own
artifacts.** Reviewing PNGs somebody else left in `artifacts/` is reviewing an
unknown build.

**4. Locate a crop by content and fail loudly when it is absent.** Never by
pixel coordinate. `visual_diff.py` has no syntax for a raw rectangle, on
purpose.

**5. Look at the picture.** Read the PNG, slice the band, magnify it with
`numpy.repeat` for nearest-neighbour, and *look*. The measurement says where to
look; it does not replace looking.

---

## The four failures

**1. "Clean and evenly spaced."** The lead said this of the word "people" from a
4x crop. The inter-letter gaps, measured minutes later, were 1, 2, 2 / 2, 1, 1,
2 px — a 2x variation, in the image, unseen. *Rule 1 and rule 5.* A crop was
looked at and an adjective came out; the numbers were never taken.

**2. "No blur difference": 36.2% against 36.8% solid ink.** The method compared
the first word of a line against the rest of *the same line*. Both halves were
equally resampled and there was no sharp reference anywhere in the frame, so the
statistic could not have come out any other way. T11 then measured **1734 of
1734 glyph quads** being resampled. *The metric was incapable of detecting the
defect it was used to rule out* — which is exactly the shape of a vacuous test,
in a measurement rather than in an assertion.

**3. `rasterizer_density=3` called "crisp".** The user called the same frame
aliased — "90's X11 text" — on sight. The number was on screen at the time: the
midtone share had collapsed from 41.2% to **11.2%**. The lead read the
destruction of antialiasing as an improvement. *Rule 1.* A number moved a long
way and was interpreted in the direction the reader was hoping for.

**4. The visual review ran without a renderer.** T7-look — the one task whose
job was "is this beautiful" — was dispatched to an agent with no shell. It could
not run `make shot`. It reviewed PNGs other agents had left behind, correctly
proved they were not all from one build, and said so. *Rule 3.*

Two more, both about reviewing the wrong thing with complete confidence:

- **T2-specimen found, only by looking, that the widest label ended exactly
  where its pangram began.** Every arithmetic assertion in the file passed.
- **T15 measured that a misspelt tab name yields a byte-identical photograph of
  the Document tab**, exit 0, no warning. A review of `columns.png` that is
  actually a picture of the Document tab is unfalsifiable from inside the
  review.

---

## Two measurement traps

**Ink-threshold gaps are not comparable across renders with different
antialiasing.** A softer render puts more coverage into the pixels at the edge
of each stem, so more of them cross the ink threshold, so every letter reads as
wider and every gap between letters reads as narrower — with nothing having
moved. The lead published such a comparison before noticing.
`visual_diff.py`'s `gaps_comparable` refuses the pair when the solid or midtone
share has moved more than five points.

**A crop lands in the wrong place silently.** The lead's crops hit whitespace
twice and were one line off once. Nothing reported it; each was found by reading
the image. So every region in `visual_diff.py` is found by content — the sheet
as the largest near-white block, a text row as a run of ink, a named line by
matching the engine's own advance widths — and every one of them raises rather
than returning blank paper.

---

## The midtone calibration, and why it is a flag and not a score

The user has labelled four renders of 16 px body text:

| midtone share | the user's verdict |
|---:|---|
| 11.2% | "aliased", "90's X11 text" |
| 26.2% | "awful" — glyph instances visibly differing |
| ~41% | the shipped baseline at the time, acceptable |
| 47.2% | "soft", but subjectively preferred |

Read this as **landmarks, not a scale.** The user rejected output at both ends
and preferred a *softer* render to the baseline, so there is no direction that
is safe to call good, and there is no target number. A large move in either
direction means the antialiasing has changed and somebody should look at a crop.

`visual_diff.py` prints this table whenever it flags a move, and explicitly
declines to say which side is better. It declines because the lead did not: the
11.2% figure was on screen when the lead called that render crisp.

**Do not compare a number from this tool against the table without re-measuring
both sides on one build.** The definition is
`docs/subpixel.md`'s — normalise coverage against the region's 95th-percentile
paper value, count coverage above 0.9 as solid and 0.15–0.85 as midtone, both as
shares of the inked pixels — but the table's numbers were taken on builds that no
longer exist by a method whose crop is not recorded. Measured on
`artifacts/demo-columns-2.png`, a shipped body line gives **≈16% solid, ≈76%
midtone**, nowhere near the table's "shipped baseline ≈41%". Either the earlier
figures predate T19-wordsnap or they were cropped differently; both are reasons
the table is a set of landmarks rather than a scale.

---

## How to run it

```sh
# One stamped shot.
.venv/bin/python scripts/visual_diff.py shoot --spec columns:2 --out artifacts/a.png

# What the finder can see in it — check a region name before trusting it.
.venv/bin/python scripts/visual_diff.py regions artifacts/a.png

# Magnify a named region and look at it. This is rule 5.
.venv/bin/python scripts/visual_diff.py crop artifacts/a.png \
    --region 'text:A column is not/words:2-2' --zoom 8 --pad 2 --out artifacts/word.png

# Two states, rendered in one invocation, so they cannot be different builds.
.venv/bin/python scripts/visual_diff.py pair --spec-a columns:2 --spec-b columns:3 \
    --region sheet --region 'text:A column is not' --crops artifacts/crops

# Before and after a source change: shoot, edit, shoot, and say out loud that
# the two sides are different trees.
.venv/bin/python scripts/visual_diff.py compare before.png after.png \
    --region 'text:A column is not' --allow-cross-build --gaps
```

Region names: `sheet`, `column:N`, `column:N/row:M`, `row:M`,
`text:<two or more words>`, `text:<...>/words:A-B`.

`text:` models one face at one size, so a phrase spanning a **bold or italic
run** will not match — pick the plain words around it. It needs two words: one
word is matched on its ink width alone, and at 16 px many words share a width to
within 2 px.

---

## What the harness does not prove

- **It cannot tell you whether something is beautiful.** No part of it tries.
- **`text:` can fail to find a line that is there** — reflow, emphasis, a
  different size. It raises, and raising is the designed behaviour; it is not
  evidence the line is absent.
- **Ink runs are glyph *clusters*, not glyphs.** Two letters whose ink touches
  are one run. That is itself a finding — the lead measured a 31 px run in the
  heading "What the difference looks like", where `iffe` in "difference" had
  fused and a letter is 9–11 px — but it means a per-run table is not a
  per-letter table.
- **Sheet finding assumes a light page on a dark window.** The Blocks tab has no
  sheet and `find_sheet` refuses it, correctly and unhelpfully.

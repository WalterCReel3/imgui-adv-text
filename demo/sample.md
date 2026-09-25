# Boxes, Glue and Penalties

This document is the first litmus test. Everything you can see below was
positioned by code in this repository: every glyph, every space between words,
every gap between lines. Nothing was handed to a text widget and nothing was
measured by one.

## Why do layout from scratch

Dear ImGui draws text very well and will not tell you where it put it. That is
a reasonable trade for a debug interface and a poor one for a document, because
the moment you want to select a phrase with the mouse you need to know which
glyph is under the pointer, and the widget that drew it has already forgotten.
Once the layout is ours, hit testing stops being a missing feature and becomes
arithmetic over numbers we already computed.

The model is Knuth's. A document is a list of **boxes**, **glue**, **kerns** and
**penalties**. A box has a fixed size, glue has a natural size plus a
stretchability and a shrinkability, a kern is rigid space, and a penalty is the
cost of breaking a line at that point. The function `hpack` measures a list and
records how far its glue had to stretch; the line breaker then chooses the set
of breakpoints with the fewest *demerits* over the whole paragraph rather than
filling each line greedily and hoping.

### What the difference looks like

A greedy filler commits to line one before it has seen line four. Total-fit
breaking will loosen an early line by a hair to rescue a later one, and the
suite pins that behaviour by enumerating every possible breaking of a short
paragraph and checking that the chosen one has the lowest score. See
[the line breaker](advtext/linebreak.py) for the demerits formula, which is
§859 of `tex.web` transcribed rather than paraphrased.

> Badness says how hard one line had to work. Demerits squares it, adds the
> square of any penalty at the break, and charges extra when two adjacent lines
> are set very differently — which is why a tight line never sits next to a
> loose one in well set text.

---

## The pieces, and who owns what

| Module | Owns | Imports a font? |
| --- | --- | --- |
| `units` | Scaled points, glue orders | no |
| `nodes` | Boxes, glue, kerns, penalties | no |
| `pack` | `hpack`, `vpack`, interline glue | no |
| `linebreak` | Total-fit breaking | no |
| `shipout` | Absolute glyph positions | no |
| `fontlib` | Advances, kerns, the MATH table | yes |

The layout core knows nothing about fonts. It consumes a small measuring
interface and produces a tree of boxes, and a separate step flattens that tree
into a flat list of draw commands with absolute coordinates. Two unrelated
backends consume those commands, which is the property that proves the geometry
really was separated from the drawing.

1. The SVG backend emits real glyph outlines and needs no GPU at all.
2. The ImDrawList backend issues immediate-mode calls and needs a window.
3. Neither one imports the other, and neither knows what a penalty is.

### Twelve steps, in order

Everything between the source file and the screen, with nothing left out and
nothing done twice. The tenth, eleventh and twelfth markers are here on
purpose: a list's gutter is sized so that a two-digit number still clears its
own text, and a demo that stopped at nine would never show it.

1. `markdown` turns the source into blocks and keeps its hands off the page.
2. Each run of text becomes characters, pair kerns and interword glue.
3. `style` resolves a face and a size into one font key per run.
4. `fontlib` reads the advance and the `GPOS` kern of every pair.
5. `linebreak` offers a breakpoint at each position the rules allow.
6. `badness` scores how hard every trial line would have to work.
7. The total-fit pass keeps the cheapest whole set of breaks.
8. `pack` sets the glue in the chosen lines and rounds once, at the end.
9. Interline glue puts consecutive baselines a constant distance apart.
10. `vpack` stacks lines and blocks into one tall vertical box.
11. `shipout` walks that box and emits absolute glyph coordinates.
12. A backend draws them, and knows nothing whatever about steps 1 to 11.

Some of it is deliberately missing, and each omission has a reason written
down next to it:

- **Hyphenation**, because the full implementation is about a thousand lines
  and contains the worst interaction in all of TeX, which is reconstructing
  ligatures across a break.
- **Page breaking**, because this is one continuous column and there is no
  page cost function to minimise.
- **Bidirectional text and complex shaping**, because one direction is enough
  to make the argument and two is a different project.

Here is the whole of the interface the layout core is allowed to see:

```python
class FontMetrics(Protocol):
    def advance(self, codepoint: int) -> float: ...
    def bbox(self, codepoint: int) -> GlyphBBox: ...
    def kern(self, codepoint: int, following: int) -> float: ...
```

## Rounding, once

TeX carries every length as an integer number of *scaled points*, one
sixty-five-thousand-five-hundred-and-thirty-sixth of a point, and rounds
***exactly once*** — at ship-out, on a final absolute coordinate. The glue
renderer keeps a
running total of the stretch it has handed out, multiplies the whole total by
the box's ratio, rounds *that*, and takes a difference against the previous
rounded total. Round each space independently instead and the error walks along
the line, so the last word misses the right margin by a point or two. It looks
like a bug in the breaker, and it is a bug in the arithmetic.

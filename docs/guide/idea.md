# The idea

## What this is

**TeX's layout algorithms, in Python, drawn through Dear ImGui.**

ImGui renders text well and gives you almost no control over it. There is no
justification, no paragraph-level line breaking, no inter-word glue, no math
setting, no control over where a glyph lands beyond what its own advance
dictates. `ImGui::Text` draws a string; it does not typeset one.

TeX does all of that and has since 1982, with algorithms that are published,
finished and studied. The bet of this repository is that those algorithms can be
lifted out of a batch document processor and put behind an immediate-mode widget
that reflows every frame — and that the result is better text than an immediate
mode GUI normally gets.

## The one invariant everything rests on

**Layout works in scaled points and performs no pixel rounding. Rounding happens
once, at draw time, inside a backend.**

A scaled point is 1/65536 of a printer's point, and it is an *integer*. TeX uses
it so that every length in a document is exact and every comparison is total: no
accumulated float error, no two boxes that should be equal and are not. This
project keeps that. `advtext/units.py` owns the type, and the rule is that
nothing between the markdown parser and `advtext/shipout.py` may convert to
pixels.

That is why `tests/test_litmus.py` asserts **zero residue in scaled points** on
the litmus documents — a justified line's glue must sum to exactly the measure,
not to within a tolerance. It is a real assertion because the arithmetic is
exact, and it is what lets a device-space bug be recognised as a device-space bug
rather than blamed on layout.

Everything a backend does to make text land on a pixel grid is therefore
*downstream* of a layout that does not know pixels exist. `docs/guide/rendering.md`
is about what happens in that last step, and why it is harder than it sounds.

## Two backends, one layout

`advtext/backends/svg.py` and `advtext/backends/imgui_draw.py` consume the same
command list from `ship()`. SVG is device-independent and is the reference; ImGui
is the real target and the one with a pixel grid to fight.

The pair is itself a test. A defect that appears in one and not the other is
localised by that fact alone — and the sub-pixel investigation began exactly that
way, with geometry that was provably correct in scaled points and wrong on screen.

## The map

    advtext/
      units.py          scaled points, and the one place px<->sp conversion lives
      nodes.py          the box/glue/penalty node model
      badness.py        TeX's badness function
      pack.py           hpack / vpack
      linebreak.py      total-fit line breaking with demerits
      style.py          the type scale, faces, spacing; markdown kind -> style
      markdown.py       markdown -> a block list
      blocklayout.py    blocks -> a vertical list
      columns.py        vert_break / prune_page_top / vsplit
      shipout.py        a packed box -> a flat list of draw commands
      selection.py      hit testing and text extraction over shipped output
      fontlib.py        font files, metrics, GPOS kerns. The only fontTools importer
      fontmetrics.py    the metrics value types
      math/             mlist_to_hlist, atoms, the math axis
      backends/
        svg.py          the device-independent reference renderer
        imgui_draw.py   the ImDrawList renderer, and all the pixel-grid decisions
      ui/               the demo app: tabs, document view, specimen, formulas

That map is the engine and was drawn before two builds added to it. Since
2026-10-07, beside what it shows: `stream.py` (a document that arrives in
pieces), `spans.py` (links, colour, find), `diff.py` (a diff as a pure model),
`mathtext.py` (a `$...$` subset read into `math/`'s atoms); and under `ui/`,
`bare_view.py`, `stream_view.py` and `diff_view.py` (the views a host embeds),
`units.py` (per-block layout), and `pages/`, one module per page of the demo's
sidebar, which is what "tabs" became.

The direction of dependency is strictly downward. `fontlib` is the only module
permitted to import fontTools, so a font question has one place to be answered.

## The two litmus tests

`docs/litmus.md` is the write-up. They exist because "the text looks right" is
not a test, and this project needed something that could fail:

- a **paragraph** whose justified lines must consume their glue exactly, and
- a **formula**, which exercises the math list machinery, the font metric
  parameters, and the vertical assembly that nothing else reaches.

`make svg` renders both to `artifacts/`, and the verify scripts assert on
geometry rather than on bytes.

## Where this fits

It is a widget, not a document processor. There is no `\output` routine, no
insertions, no marks, no page cost function. What there *is* is a text engine
good enough that a justified, hyphenation-free, math-capable paragraph reflows
inside an immediate-mode frame and lands every glyph on a pixel deliberately.

`docs/decisions.md` has the scope boundaries with the reason for each.

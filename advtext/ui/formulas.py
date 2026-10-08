r"""
A gallery of formulae, each one chosen for a rule of TeX's math mode it makes visible.

The material for the Formula tab, as boxes and numbers. Nothing here draws and
nothing here imports ImGui, matching `advtext.ui.specimen`: a formula is arithmetic
over font metrics and the result is a packed `advtext.nodes.Box` that
`advtext.shipout.ship` turns into commands for whichever backend is asking.

**Every formula is written out by hand from the atom vocabulary.** There is no
LaTeX parser in this project and there should not be -- `advtext.math.atoms` says
why, and it is the right call: a parser would become the thing being demonstrated
instead of the typesetting. (The engine still has none; `advtext.mathtext` is an
extension above it that reads a `$...$` subset into these same atoms, and
`tests/test_mathtext.py` writes every entry here as such a source and holds it to the
box the hand-built entry sets.) The cost is that `ENTRIES` below is verbose. The
benefit is that each entry names the atom *classes* explicitly, which is precisely
the input the spacing rules consume, so a reader of this file can see what is being
claimed.

## Why these nine and not nine pretty equations

A gallery whose entries all exercise the same code path is decoration. Each entry
here is the only one that reaches some rule:

| entry | the rule it is the only witness to | `tex.web` |
|---|---|---|
| `operator-style` | the display glyph swap: a *different outline*, not a scaled one | 14688, §749 |
| `euler` | nothing -- it is the control, and the contrast is the point | -- |
| `schrodinger` | a `Bin` demoted to `Ord` mid-expression, in a real formula | 14322, §727 |
| `basel` | the `limits` default: stacked in display, beside it inline | 14684, §749 |
| `cauchy` | `Limits.NO_LIMITS` overriding that default in display style | 14417, §749 |
| `continued-fraction` | the four styles, and `num_style` as a no-op at the floor | 13858, §702 |
| `script-towers` | `sub_style` always cramps and `sup_style` does not | 13856-13857, §702 |
| `atom-classes` | the spacing table: the same glyphs, classified and not | 15064, §764 |
| `binary-or-not` | the reclassification, isolated to one glyph | 14297, 14348, §727 |

Every line number in that table was read out of `docs/tex.web` in this tree.
`docs/tex-notes.md` warns that the *section* numbers in this project were only
spot-checked, so the line number is the load-bearing half of each citation and the
section number is there for anyone reading a printed `TeX: The Program`.

The first entry is the demonstration this tab has always carried and it is still
the sharpest evidence in the project, so it is kept and it is kept first.

## The captions are short on purpose

A caption here is one or two sentences saying **what the entry demonstrates**, not
what the formula means. That is a deliberate correction: the first draft of this
module gave every entry a full paragraph with the `tex.web` citation inline, and
the screenshot showed a tab that was four parts prose to one part mathematics --
an essay with formulae in it rather than a specimen of a math typesetter. The
argument goes in this docstring, where a reader who wants it will look; the page
gets the sentence that tells them where to point their eye.

## Comparisons, not single specimens

Five of the nine set the *same* material twice under different rules and show both.
That is the same argument `advtext.ui.specimen` makes for putting six faces on one
page: a reader compares two things side by side far faster than they compare a
picture with a memory, and "the left one is wider" is an observation where "this
looks about right" is not. `Panel` exists for that -- an entry is one or more
panels, and a one-panel entry is simply the degenerate case.

**Panels of one entry share a baseline and a column grid.** The formulae go in one
hbox, so `hpack` aligns their baselines; the labels go in a second hbox using the
same column widths, so a label sits under the panel it names however tall or deep
that panel turned out to be. Building each panel as its own vbox instead puts the
two labels at different heights whenever the two panels have different depths,
which is exactly the case for `operator-style` -- the display sigma has its lower
limit hanging below the baseline and the text one does not.

## Glyph coverage is checked here, not discovered in a screenshot

Latin Modern Math carries every codepoint these formulae name -- `hbar`, `∂`, `∇`,
`ψ`, `∮`, `∞`, `γ`, `φ` and `π` all resolve to real glyph names, checked by
`tests/test_formulas.py` against the font itself. Two near neighbours do **not**:
`U+0127 LATIN SMALL LETTER H WITH STROKE` and `U+203E OVERLINE` both come back
`.notdef`, so `ℏ` here is `U+210F PLANCK CONSTANT OVER TWO PI` and there is no
overline anywhere. `Entry.missing` reports any codepoint whose glyph is absent, so
a font swap produces a labelled gap rather than a silent blank.

That check is against the *font*, through `advtext.fontlib.glyph_name`. Whether
ImGui managed to rasterise the glyph is a separate question that only a screenshot
answers, and `advtext.backends.imgui_draw.DrawStats.missing` is what answers it.
Both are reported by the tab, because they fail independently.

**A caption cannot quote every symbol its own formula sets**, and this was found by
looking: the first draft of `cauchy` wrote the contour-integral sign into its
caption and the tab reported one glyph with no raster, because a caption is prose
and neither Roboto nor Inconsolata carries `U+222E`. Inconsolata has no `π`
either. `missing_codepoints` above does **not** cover this -- it asks about the
math face, and caption text is set in the prose and code faces -- so the rule is
simply that caption prose names a symbol in words. `tests/test_formulas.py` pins
it for every caption in `ENTRIES` at once, which is the check that scales.

## What is not here, and why

**No accents and nothing assembled from pieces.** `advtext.math` declares an Accent
atom so the spacing map is total and raises on it rather than pretending. So: no
`x̄` and no vector arrows.

Fixed-size parentheses work and the nine entries use only those -- `open_("(")` and
`close_(")")` are ordinary atoms carrying the Open and Close spacing classes, and
they set at the size of the style they are in. `cauchy` and `euler` both rely on
that, and `cauchy`'s parens sit around `z` and around `a`, never around the
quotient.

## Two more plates, after the nine

`SIZED_ENTRIES` holds a radical and a `\left`...`\right` pair, which the engine
has set since the second build. Each is the only witness to its rule, by the
standard of the table above:

| entry | the rule it is the only witness to | `tex.web` |
|---|---|---|
| `radical` | the surd is *chosen* from the font's chain to cover its radicand | 14476, §737 |
| `sized-delimiters` | a left-right pair is sized to the list between it | 15017, §762 |

Both are a choice among the outlines the font carries -- five surds, eight
parentheses -- and never a stretch. A radicand taller than the last surd is refused
(`advtext.math.DelimiterTooSmallError`). A `\left`...`\right` pair is refused the same
way only when the largest outline covers less than three quarters of what TeX's rule
asks of it (`advtext.math.mlist.LARGEST_VARIANT_MUST_COVER`, the lead's number and not
TeX's, review 2 item 9); between that and the rule the largest is set and falls short.
Neither entry asks for either.

**They are the tenth and eleventh of `ENTRIES`**, which is `CLASSIC_ENTRIES` (the
nine) followed by these two. They were held apart for a morning, because
`tests/test_mathtext.py` writes every entry as a `$...$` source and its parser
did not yet read `\sqrt` or `\left`; it does now, and the two are folded in.
`tests/test_formulas.py` holds them to every standard the nine are held to, and
holds the nine to the boxes they set before the engine grew.

Also absent: colour (the node model carries none), and any notion of which faces
ImGui loaded. This module takes `advtext.ui.app.load_fonts`'s posture one layer up.

## Variables are italic, and one letter is not where Unicode says it is

`MathChar` carries a codepoint and no family byte, so nothing below this module can
decide that an `Ord` holding `x` is a *variable* and should be slanted -- TeX makes
that call from the `\fam` of the character it read, and here the caller makes it.
Written as `ord_("x")` a formula gets the **upright** `x`, which is the shape
reserved for an operator name like `sin`, and a page of upright variables does not
read as mathematics. So every variable in `ENTRIES` goes through `italic` and every
digit, delimiter and operator does not.

The trap in that mapping is worth stating: **`U+1D455`, where the math-italic `h`
would fall, does not exist.** Unicode left the hole because `U+210E PLANCK CONSTANT`
already carried the glyph. Straight arithmetic lands there, Latin Modern Math
returns `.notdef`, and the symptom is one invisible letter in one formula with
nothing raised. `_ITALIC_EXCEPTIONS` is that hole and the italic partial
differential; `tests/test_formulas.py` pins both, and separately pins that no ASCII
letter survives into any panel.

## Cost

**45 ms at a 468 px measure, warm, best of three**, against a 16.7 ms frame budget,
of which the great majority is the captions going through `break_paragraph` (measured
when there were nine entries; not re-taken for eleven).
The mlist conversions are a few milliseconds -- nothing in a formula is line-broken.
The first call in a process additionally pays the font open, which dominates
everything else. Build once per measure and keep it; `advtext.ui.app.App.gallery`
does, and that is not optional at this cost.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from advtext.fontmetrics import Face, FontMetrics, MathFontMetrics
from advtext.markdown import build_document
from advtext.math import (
    Atom,
    AtomType,
    Field,
    Fraction,
    Limits,
    MathChar,
    MathFonts,
    MathItem,
    MathResolver,
    Style,
    SubList,
    bin_,
    close_,
    delimited,
    frac,
    group,
    inner,
    math_fonts,
    mlist_to_hlist,
    op,
    open_,
    ord_,
    radical,
    rel,
)
from advtext.math.atoms import Buildable
from advtext.math.mlist import SURD
from advtext.nodes import Box, CharNode, FontKey, Glue, GlueSpec, Kern, Node
from advtext.pack import (
    IGNORE_DEPTH,
    CharMeasure,
    InterlineSkip,
    PackMode,
    append_to_vlist,
    hpack,
    vpack,
)
from advtext.style import (
    BlockKind,
    MetricsResolver,
    Theme,
    char_measure,
    font_key,
    interword_glue,
)
from advtext.ui import HSS, compose_blocks
from advtext.units import Scaled, sp_from_px

__all__ = [
    "CLASSIC_ENTRIES",
    "ENTRIES",
    "FORMULA_PX",
    "LABEL_PX",
    "SIZED_ENTRIES",
    "SUMMATION",
    "Entry",
    "EntryDef",
    "Gallery",
    "Panel",
    "PanelDef",
    "build_gallery",
    "char_fonts",
    "codepoints",
    "fontlib_math_metrics",
    "italic",
    "missing_codepoints",
    "missing_glyphs",
    "var",
]


FORMULA_PX = 34.0
"""
The size every formula in the gallery is set at.

Large enough that a scriptscript-level glyph -- 0.5 of this by Latin Modern Math's
own `ScriptScriptPercentScaleDown`, so 18 px -- is still legible, and small enough
that the widest entry stays inside the page the rest of the demo sets. The widest
is `schrodinger` at about 357 px natural, measured; the narrowest page this demo
draws is wider than that.
"""

LABEL_PX = 12.0
"""
The size of the panel labels, set in `Face.CODE`.

The same size and face `advtext.ui.specimen` labels its gutter with, so a reader
moving between the two tabs sees one caption style rather than two.
"""

_PANEL_GAP_EMS = 1.0
"""
The gap between two panels of one entry, as a multiple of the formula size.

The same `Kern(width=size)` the Formula tab used when it held a single pair, so the
kept sigma comparison is spaced exactly as it was before this gallery existed.
"""

_ENTRY_GAP_LEADINGS = 1.5
"""
The air between one entry and the next, in body leadings.

More than the gap between a caption and its own formula (one leading), so the page
groups as caption-with-formula rather than as an undifferentiated column. This is
the only number in this module chosen by eye rather than measured, and it was
chosen by looking at a screenshot.
"""


# --------------------------------------------------------------------------------
# The formulae
#
# Written out rather than parsed. Each definition names the atom class of every
# piece, because the class is what the spacing rules read -- `bin_("+")` and
# `ord_("+")` are the same glyph and set differently, and `atom-classes` below
# exists to make that visible.
# --------------------------------------------------------------------------------


_ITALIC_RANGES: tuple[tuple[int, int, int], ...] = (
    (ord("a"), ord("z"), 0x1D44E),
    (ord("A"), ord("Z"), 0x1D434),
    (0x03B1, 0x03C9, 0x1D6FC),
)
"""
Where Unicode keeps the math-italic forms of the letters a variable is set in.

Lower-case Latin, upper-case Latin, lower-case Greek, each a contiguous block.
Upper-case Greek is deliberately absent: TeX sets it **upright** (`\\Sigma` comes
from the roman family, `\\sigma` from math italic), so mapping it would be a change
of convention rather than a correction.
"""

_ITALIC_EXCEPTIONS: dict[int, int] = {
    ord("h"): 0x210E,
    0x2202: 0x1D715,
}
r"""
The two letters whose italic form is not where the arithmetic says it is.

`U+1D455`, where the italic `h` would fall, **does not exist** -- Unicode left the
hole because `U+210E PLANCK CONSTANT` was already encoded and unifying them was the
whole point of the Letterlike Symbols block. Latin Modern Math returns `.notdef`
for `U+1D455`, so an unconditional `0x1D44E + (c - 'a')` puts a missing glyph in
any formula with an `h` in it and nothing raises. `tests/test_formulas.py` pins
both halves of that.

`U+2202` is here because the partial-differential sign has an italic form of its
own at `U+1D715`, and `∂ψ/∂t` set with the upright one reads as a different
operator sitting next to an italic variable.
"""


def italic(text: str) -> str:
    r"""
    The math-italic form of every letter in `text`, leaving everything else alone.

    **Why this is needed at all.** `advtext.math.MathChar` carries a codepoint and
    nothing else -- there is no family byte, so nothing downstream can decide that
    an `Ord` holding `x` is a variable and should be slanted. TeX makes that
    decision in the `\\fam` of the character it read; here the caller makes it, and
    the caller is this module. Written out as `ord_("x")` a formula sets the
    **upright** `x`, which is the form reserved for an operator name like `sin` --
    so every variable in `ENTRIES` goes through here and every digit does not.

    Digits, `∇`, `∑`, `∮`, `∞` and the parentheses pass through unchanged, which is
    correct: TeX sets all of them upright too.

    **The `d` of `dz` is italic here**, which is a choice and not an oversight. It
    is what plain TeX and LaTeX give for `\int f(z)\,dz`; ISO 80000-2 wants it
    upright and LaTeX spells that `\mathrm{d}`. Either is defensible and the
    deciding argument is local: every other letter on this page is slanted, so a
    lone upright `d` beside an italic `z` would read as a defect rather than as a
    convention. `tests/test_formulas.py` asserts no ASCII letter survives into any
    panel, which is the form that keeps the choice from drifting by accident.
    """
    return "".join(chr(_italic_codepoint(ord(character))) for character in text)


def _italic_codepoint(codepoint: int) -> int:
    if codepoint in _ITALIC_EXCEPTIONS:
        return _ITALIC_EXCEPTIONS[codepoint]
    for first, last, target in _ITALIC_RANGES:
        if first <= codepoint <= last:
            return target + codepoint - first
    return codepoint


def var(nucleus: str, *, sup: Buildable = None, sub: Buildable = None) -> Atom:
    """
    An ordinary atom holding a variable: `ord_`, with the letters set in math italic.

    A string passed as a script is italicised too, because a letter in a script is
    still a variable -- and a digit in one is still a digit, since `italic` leaves
    digits alone. Anything richer than a string is passed through untouched and the
    caller is expected to have used `var` inside it.
    """
    return ord_(
        italic(nucleus),
        sup=italic(sup) if isinstance(sup, str) else sup,
        sub=italic(sub) if isinstance(sub, str) else sub,
    )


SUMMATION = op("∑", sup=italic("n"), sub=group(italic("i"), rel("="), "1"))
r"""
The summation the Formula tab has always shown.

Kept here rather than in `advtext.ui.app` so that the tab and this gallery name one
object. `tests/test_app.py` pins `App.formula_box`, which still builds it directly;
`tests/test_litmus.py` and `scripts/verify_ascent.py` build their own and compare.
"""


@dataclass(frozen=True, slots=True)
class PanelDef:
    """
    One setting of one math list: what to set, at which style, and what to call it.

    `label` is empty for an entry with a single panel, where there is nothing to
    distinguish and a label under one formula reads as a title it does not need.
    """

    items: tuple[MathItem, ...]
    style: Style = Style.DISPLAY
    label: str = ""


@dataclass(frozen=True, slots=True)
class EntryDef:
    """
    One plate of the gallery before anything has been measured.

    `caption` is markdown and is composed through the same `build_document` /
    `compose_blocks` path as any paragraph in the Document tab, so a caption here is
    set with the document's own faces, leading and breaking. It says **what the
    entry demonstrates** rather than what the formula means: a reader looking at
    this tab should come away knowing something about the typesetter.

    `key` is stable and is what a test names an entry by. Titles are prose and may
    be reworded; keys are an interface.
    """

    key: str
    title: str
    caption: str
    panels: tuple[PanelDef, ...]


def _tower(script: str, letters: str = "xyzw") -> Atom:
    """
    The first letter with the rest hung off it as nested super- or subscripts.

    `_tower("sup")` is `x^{y^{z^{w}}}` and `_tower("sub")` is `x_{y_{z_{w}}}`.
    Built rather than written out so the two towers in `script-towers` are
    provably the same shape in the two directions -- typing them out separately
    would let one of them drift and the comparison would quietly stop being one.

    Four letters, which is one more than it takes to reach the scriptscript floor:
    `w` is set at the same size as `z`, and that is the clamp being demonstrated.
    """
    atom = var(letters[-1])
    for letter in reversed(letters[:-1]):
        atom = var(letter, **{script: atom})
    return atom


def _continued_fraction(depth: int = 4) -> Fraction:
    """
    `1/(1 + 1/(1 + ...))`, `depth` bars deep.

    Four is not arbitrary: §702's `num_style` takes display to text to script to
    scriptscript in three steps and is the identity thereafter (`docs/tex.web`
    line 13858, `#+2-2*(# div 6)`). A three-deep fraction reaches the floor; a
    four-deep one reaches it and then demonstrates that it *stays* there, which is
    the part an unclamped implementation would get wrong while still looking
    plausible.
    """
    inner_field: MathItem = ord_("1")
    for _ in range(depth):
        inner_field = frac("1", group(ord_("1"), bin_("+"), inner(inner_field)))
    assert isinstance(inner_field, Fraction)
    return inner_field


CLASSIC_ENTRIES: tuple[EntryDef, ...] = (
    EntryDef(
        key="operator-style",
        title="A big operator, twice",
        caption=(
            "**A big operator, twice.** The large sigma is a *different outline*, not "
            "the small one scaled up -- a glyph Latin Modern Math leaves unencoded, "
            "reached through the variant chain that display style follows. The limits "
            "move with it: stacked in display, set to the right inline."
        ),
        panels=(
            PanelDef((SUMMATION,), Style.DISPLAY, "display style"),
            PanelDef((SUMMATION,), Style.TEXT, "text style"),
        ),
    ),
    EntryDef(
        key="euler",
        title="Euler's identity",
        caption=(
            "**Euler's identity.** The control: five atoms, one superscript, nothing "
            "nested. No space was typed into it, and the gap at the equals sign is "
            "wider than the one at the plus because a relation is not a binary operator."
        ),
        panels=(
            PanelDef(
                (
                    var("e", sup=group(var("i"), var("π"))),
                    bin_("+"),
                    ord_("1"),
                    rel("="),
                    ord_("0"),
                ),
            ),
        ),
    ),
    EntryDef(
        key="schrodinger",
        title="Schrödinger's equation",
        caption=(
            "**Schrödinger's equation**, time-dependent. Two fractions inside one "
            "expression, and a reclassification in the middle: the minus after the "
            "equals sign is written as a binary operator, and §727 demotes it to an "
            "ordinary one because nothing on its left is there to bind. It hugs the "
            "fraction. The later plus, which really is binary, keeps its space."
        ),
        panels=(
            PanelDef(
                (
                    var("i"),
                    ord_("ℏ"),
                    inner(frac(group(var("∂ψ")), group(var("∂t")))),
                    rel("="),
                    bin_("−"),
                    inner(frac(group(ord_("ℏ", sup="2")), group(ord_("2"), var("m")))),
                    ord_("∇", sup="2"),
                    var("ψ"),
                    bin_("+"),
                    var("V"),
                    var("ψ"),
                ),
            ),
        ),
    ),
    EntryDef(
        key="basel",
        title="The Basel problem",
        caption=(
            "**The Basel problem.** Both limits stacked over the operator, because the "
            "style is display and §749 makes that the default there -- which is why the "
            "text-style sigma above sets its bounds to the right instead."
        ),
        panels=(
            PanelDef(
                (
                    op("∑", sup=ord_("∞"), sub=group(var("n"), rel("="), ord_("1"))),
                    inner(frac("1", group(var("n", sup="2")))),
                    rel("="),
                    inner(frac(group(var("π", sup="2")), "6")),
                ),
            ),
        ),
    ),
    EntryDef(
        key="cauchy",
        title="Cauchy's integral formula",
        caption=(
            "**Cauchy's integral formula.** The previous entry's default, overridden: "
            "`Limits.NO_LIMITS` keeps the contour beside the integral sign in display "
            "style rather than under it. The parentheses are fixed-size Open and Close "
            "atoms; nothing here stretches, so none of them is asked to grow."
        ),
        panels=(
            PanelDef(
                (
                    var("f"),
                    open_("("),
                    var("a"),
                    close_(")"),
                    rel("="),
                    inner(frac("1", group(ord_("2"), var("π"), var("i")))),
                    op("∮", sub=var("γ"), limits=Limits.NO_LIMITS),
                    inner(
                        frac(
                            group(var("f"), open_("("), var("z"), close_(")")),
                            group(var("z"), bin_("−"), var("a")),
                        )
                    ),
                    var("d"),
                    var("z"),
                ),
            ),
        ),
    ),
    EntryDef(
        key="continued-fraction",
        title="A continued fraction, four deep",
        caption=(
            "**A continued fraction, four bars deep** -- the golden ratio, and the only "
            "thing here that shows all four math styles at once. Each bar drops one "
            "step: display, text, script, scriptscript. Then it **stops**, so the "
            "fourth bar is set at exactly the size of the third and three font sizes "
            "serve any depth. Watch the plus signs as well: below script size §764 "
            "drops the space around a binary operator, so the deep ones close up."
        ),
        panels=(
            PanelDef(
                (
                    var("φ"),
                    rel("="),
                    ord_("1"),
                    bin_("+"),
                    inner(_continued_fraction()),
                ),
            ),
        ),
    ),
    EntryDef(
        key="script-towers",
        title="Scripts stack, and subscripts are cramped",
        caption=(
            "**Scripts stack, and the two directions are not mirror images.** The same "
            "four letters, hung upward and downward. A subscript is always cramped and a "
            "superscript is not, and a cramped style holds its own scripts down -- so "
            "the left tower rises further than the right one drops. Both reach the "
            "scriptscript floor at the third letter."
        ),
        panels=(
            PanelDef((_tower("sup"),), Style.DISPLAY, "superscripts"),
            PanelDef((_tower("sub"),), Style.DISPLAY, "subscripts"),
        ),
    ),
    EntryDef(
        key="atom-classes",
        title="The spacing table, on and off",
        caption=(
            "**The spacing table, on and off.** The same five glyphs, set twice. On the "
            "left the plus is a `Bin` and the equals a `Rel`, so §764's table asks for a "
            "medium space around one and a thick space around the other. On the right "
            "all five are `Ord` and the table asks for nothing. Neither side contains a "
            "typed space."
        ),
        panels=(
            PanelDef(
                (var("a"), bin_("+"), var("b"), rel("="), var("c")),
                Style.DISPLAY,
                "classified",
            ),
            PanelDef(
                (var("a"), ord_("+"), var("b"), ord_("="), var("c")),
                Style.DISPLAY,
                "all ordinary",
            ),
        ),
    ),
    EntryDef(
        key="binary-or-not",
        title="A minus is only binary in context",
        caption=(
            "**A minus sign is only binary in context.** Both sides are written with "
            "`bin_`. On the right something precedes it, so it stays binary and takes a "
            "medium space on each side. On the left nothing does, §727 rewrites it as "
            "ordinary, and the space is not narrowed -- it is never asked for."
        ),
        panels=(
            PanelDef(
                (bin_("−"), var("x")),
                Style.DISPLAY,
                "nothing before it",
            ),
            PanelDef(
                (var("a"), bin_("−"), var("x")),
                Style.DISPLAY,
                "something before it",
            ),
        ),
    ),
)
"""
The first nine plates of the gallery, in the order they are set.

The module docstring has the table of what each one is the only witness to; if
an entry is ever added that duplicates a row of it, that entry is decoration and
should be cut instead. Kept under a name of its own because
`tests/test_formulas.py` holds these nine to a digest taken before the engine
grew, and `ENTRIES` below is longer.
"""


_QUOTIENT = frac(
    group(var("a", sup="2"), bin_("+"), var("b", sup="2")),
    group(var("c", sup="2")),
)
"""
The tall thing both of `SIZED_ENTRIES` are built around: one display fraction.

Shared so the radical and the parentheses are measured against the same content.
Measured at the gallery's size, in display style: it reaches 1.26 em above the
axis and 0.95 em below, so `make_left_right` asks for 2.26 em and gets
`parenleft.v6`, 2.39 em and the seventh of the eight parentheses Latin Modern Math
carries; set cramped under a rule it takes `radical.v3`, 2.4 em and the fourth of
five surds. The one-line radicand beside it takes `radical.v1`. Neither is at the
end of its chain, so neither plate is one font tweak away from a refusal.
"""

SIZED_ENTRIES: tuple[EntryDef, ...] = (
    EntryDef(
        key="radical",
        title="A radical, sized to its radicand",
        caption=(
            "**A radical, twice.** The root sign is chosen, never stretched: the font "
            "carries five of them, and the smallest that covers the radicand, the "
            "clearance above it and the rule is the one set. So the two signs here are "
            "*different outlines*, and the rule meets each at the top of its stroke."
        ),
        panels=(
            PanelDef(
                (radical(group(var("a", sup="2"), bin_("+"), var("b", sup="2"))),),
                Style.DISPLAY,
                "one line",
            ),
            PanelDef((radical(_QUOTIENT),), Style.DISPLAY, "a fraction"),
        ),
    ),
    EntryDef(
        key="sized-delimiters",
        title="Parentheses, fixed and fitted",
        caption=(
            "**Parentheses, fixed and fitted.** The same fraction between the same two "
            "characters. On the left they are ordinary Open and Close atoms and stay "
            "the size of the type. On the right they are a left-right pair: §762 "
            "measures what stands between them and takes the smallest parenthesis in "
            "the font that covers it, centred on the axis."
        ),
        panels=(
            PanelDef(
                (open_("("), inner(_QUOTIENT), close_(")")),
                Style.DISPLAY,
                "fixed",
            ),
            PanelDef((delimited("(", _QUOTIENT, ")"),), Style.DISPLAY, "fitted"),
        ),
    ),
)
"""
The two plates the second build added: a radical, and a sized delimiter pair.

The module docstring has the rule each is the only witness to.
"""

ENTRIES: tuple[EntryDef, ...] = (*CLASSIC_ENTRIES, *SIZED_ENTRIES)
"""
The gallery, in the order it is set: the nine, then the two.

What `build_gallery` sets by default and so what the Formula page shows.
`tests/test_mathtext.py` writes every panel of every entry as a `$...$` source
and holds it to the box the hand-built entry sets.
"""


# --------------------------------------------------------------------------------
# Walking a formula: codepoints, and the fonts a packed box actually used
# --------------------------------------------------------------------------------


def codepoints(items: Iterable[MathItem]) -> tuple[int, ...]:
    """
    Every codepoint a math list names, in order, including inside scripts.

    Public because the coverage check needs it and because a test that wants to
    assert a formula is the formula it claims to be -- rather than an empty box
    that happens to pack -- has no other route to the characters. Duplicates are
    kept: a list that names `ψ` twice reports it twice, and collapsing them here
    would make "how many glyphs is this" unanswerable from the outside.

    **These are the math face's characters, as the formula names them.** A radical
    names its surd, though no field holds it. A sized delimiter is reported as the
    character that was asked for, not as whichever variant was set -- the count
    still agrees with the glyphs shipped, and the variant's codepoint is minted
    and means nothing outside the face. Prose in a `MathText` is not reported at
    all: it is set in another face, and every caller of this asks about this one.
    """
    out: list[int] = []
    for item in items:
        if isinstance(item, Fraction):
            _field_codepoints(item.numerator, out)
            _field_codepoints(item.denominator, out)
            continue
        if item.kind is AtomType.RADICAL:
            out.append(SURD)
        _field_codepoints(item.nucleus, out)
        _field_codepoints(item.sup, out)
        _field_codepoints(item.sub, out)
    return tuple(out)


def _field_codepoints(field_value: Field, out: list[int]) -> None:
    """
    Accumulate one field's codepoints. A `SubBox` carries none -- it is already set
    -- and neither does a space or a run of prose.
    """
    match field_value:
        case MathChar(codepoint):
            out.append(codepoint)
        case SubList(items):
            out.extend(codepoints(items))
        case _:
            return


def fontlib_math_metrics(size: Scaled) -> MathFontMetrics:
    """
    The production math resolver: the real Latin Modern Math file at one size.

    A separate resolver from `advtext.style.fontlib_metrics` because
    `advtext.math.MathResolver` is keyed by a *size* and promises the `MATH` table
    back, where a `MetricsResolver` is keyed by a font key and promises only
    advances. Narrowing the second into the first needs a cast that would be
    unchecked, so the seam is two functions instead.

    Imported lazily for the reason `advtext.style.fontlib_metrics` is: this module
    is meant to be usable against a fake resolver with round numbers, and a
    top-level import of `advtext.fontlib` would open a font to find that out.
    """
    from advtext import fontlib

    return fontlib.math_metrics(float(size))


def _fontlib_glyph_name(codepoint: int) -> str:
    """
    Latin Modern Math's own name for a codepoint, or `.notdef` if it has none.
    """
    from advtext import fontlib

    return fontlib.glyph_name(Face.MATH, codepoint)


def missing_codepoints(
    items: Iterable[MathItem], glyph_name: Callable[[int], str] | None = None
) -> tuple[int, ...]:
    """
    The codepoints in a math list that the math face has no glyph for, deduplicated.

    **This is a question about the font file, not about the renderer.** A codepoint
    that passes here can still fail to reach the screen if ImGui did not rasterise
    it, which is a different failure with a different report --
    `advtext.backends.imgui_draw.DrawStats.missing`. Both are shown by the tab
    because either can happen alone.

    Deduplicated where `codepoints` is not, because this is a list of things to fix
    and a character named four times is one thing to fix.
    """
    resolve = _fontlib_glyph_name if glyph_name is None else glyph_name
    seen: dict[int, None] = {}
    for codepoint in codepoints(items):
        if codepoint not in seen and resolve(codepoint) == ".notdef":
            seen[codepoint] = None
    return tuple(seen)


def missing_glyphs(
    entries: Sequence[EntryDef] = ENTRIES, glyph_name: Callable[[int], str] | None = None
) -> tuple[int, ...]:
    """
    Every codepoint across `entries` that the math face has no glyph for.

    The static form of `Gallery.missing`, answerable without building anything.
    The Formula tab asks it this way so the warning is right on the first frame
    rather than one frame behind the gallery it would otherwise have to read it
    from -- a distinction that matters here because `scripts/shot.py` photographs
    an app that has run a fixed number of frames.
    """
    seen: dict[int, None] = {}
    for entry in entries:
        for panel in entry.panels:
            for codepoint in missing_codepoints(panel.items, glyph_name):
                seen[codepoint] = None
    return tuple(seen)


def char_fonts(box: Box) -> tuple[FontKey, ...]:
    """
    Every distinct font key a packed box sets a character in, in first-seen order.

    The observable behind the scriptscript clamp. "The continued fraction is four
    deep and uses three font sizes" is a claim about the shipped result, and an
    implementation that kept shrinking would still produce a plausible-looking
    fraction while failing it. Reading the keys is the only way to ask.

    Walks boxes recursively, so it sees through the vboxes `_make_fraction` builds
    and the hboxes inside them.
    """
    out: dict[FontKey, None] = {}
    _collect_fonts(box, out)
    return tuple(out)


def _collect_fonts(box: Box, out: dict[FontKey, None]) -> None:
    for node in box.contents:
        if isinstance(node, CharNode):
            out[node.font] = None
        elif isinstance(node, Box):
            _collect_fonts(node, out)


# --------------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Panel:
    """
    One setting of one math list, measured.

    `box` is the formula at its natural width, before it is placed in a column, so
    `box.width` is the number a comparison is read off. `column` is the width of the
    grid column it was placed in -- the wider of the formula and its own label --
    and is what makes the label line up underneath.

    `label_width` is the label's own set width. It is here for the reason
    `advtext.ui.specimen.SpecimenRow.label_width` is: "the column was measured and
    the label fits it" should be checkable without reaching into the builder, and
    **the case that needs checking is real** -- `operator-style`'s "display style"
    label is 90 px against a 49 px display sigma, so the label is what decides that
    column. A column sized from the formula alone would spill it.
    """

    label: str
    style: Style
    items: tuple[MathItem, ...]
    box: Box
    column: Scaled
    label_width: Scaled


@dataclass(frozen=True, slots=True)
class Entry:
    """
    One plate: a composed caption, a row of panels, and their labels.

    `box` is the whole plate, packed to the gallery's content width. `note` is the
    composed caption on its own, exposed separately so that "the formulae survived a
    font swap and the prose did not" is observable rather than a claim -- the same
    split `advtext.ui.specimen.SpecimenSection` makes and for the same reason.

    `missing` lists codepoints with no glyph in the math face, across every panel.
    Empty with the bundled font.

    `formulae` and `labels` are the two rows, before they were centred on the page.
    Each is an hbox of one column box per panel with a kern between, and the two
    are built from the **same** column widths -- that sharing is what puts a label
    under the panel it names, and it is the whole of the claim. They are public so
    that claim is checkable from outside: reading `Panel.column` back instead would
    pass for a build that computed the grid correctly and then ignored it. `labels`
    is `None` for an entry whose panels carry no labels.
    """

    key: str
    title: str
    caption: str
    panels: tuple[Panel, ...]
    box: Box
    note: Box
    formulae: Box
    labels: Box | None
    missing: tuple[int, ...]

    def grid(self, row: Box) -> tuple[Scaled, ...]:
        """
        The column widths of one of this entry's rows, left to right.

        `entry.grid(entry.formulae) == entry.grid(entry.labels)` is the invariant,
        and it is not the same statement as "`Panel.column` was computed correctly".
        """
        return tuple(node.width for node in row.contents if isinstance(node, Box))


@dataclass(frozen=True, slots=True)
class Gallery:
    """
    The whole gallery, ready to ship.

    `box`'s reference point is the baseline of its first line, like every box in
    this project, so `ship(gallery.box, Point(0, gallery.box.height))` puts its
    top-left at the origin.

    `width` is the measure the captions were broken to. `box.width` may be **larger**
    -- it is `max(width, widest panel row)` -- and a caller sizing a sheet should use
    `box.width`, exactly as the Specimen tab does. When the two differ, a formula was
    wider than the prose measure and the page grew to hold it rather than clipping
    it.

    `fonts` is the three-size math face the panels were set from. It carries the
    `CharMeasure` those boxes must be shipped with, and is exposed so a caller
    checking `sizes` does not have to rebuild it.
    """

    entries: tuple[Entry, ...]
    box: Box
    width: Scaled
    fonts: MathFonts
    missing: tuple[int, ...]

    def entry(self, key: str) -> Entry:
        """
        One plate by its stable key. Raises `KeyError` for a key that is not in it.
        """
        for found in self.entries:
            if found.key == key:
                return found
        raise KeyError(key)


@dataclass(slots=True)
class _Stack:
    r"""
    A vertical list under construction, with §679's `prev_depth` threaded through.

    The same two moves `advtext.ui.specimen._Stack` makes, and made the same way: a
    box joins with its interline glue, and an explicit gap is a kern that also resets
    `prev_depth` to `IGNORE_DEPTH`. Leaving `prev_depth` alone across a kern adds a
    `\baselineskip`-derived gap on top of the requested one.
    """

    vlist: list[Node] = field(default_factory=list)
    prev_depth: Scaled = IGNORE_DEPTH

    def gap(self, amount: Scaled) -> None:
        if self.vlist and amount:
            self.vlist.append(Kern(width=amount))
        self.prev_depth = IGNORE_DEPTH

    def add(self, box: Box, skip: InterlineSkip) -> None:
        self.prev_depth = append_to_vlist(self.vlist, box, self.prev_depth, skip)

    def packed(self) -> Box:
        return vpack(self.vlist).box


def _skip(size: Scaled) -> InterlineSkip:
    """
    The interline triple for a row set at `size`, at the gallery's own leading.

    Looser than prose (1.5 against 1.35) for `advtext.ui.specimen._skip`'s reason:
    these rows are looked at rather than read, and a formula with a lower limit is
    much deeper than a line of text, so the rhythm needs the slack.
    """
    return InterlineSkip(
        baselineskip=GlueSpec(width=size * 3 // 2),
        lineskip=GlueSpec(width=size // 5),
        lineskiplimit=0,
    )


def _centred(box: Box, width: Scaled, measure: CharMeasure) -> Box:
    """
    `box` centred in a column exactly `width` wide, by two `hss` glues.

    The same construction `advtext.ui.app.App.formula_box` uses, and the reason is
    the same: `hss` stretches and shrinks without bound, so two of them split any
    surplus evenly and a formula *wider* than the column overfulls symmetrically
    rather than being pushed off one edge.
    """
    return hpack([Glue(HSS), box, Glue(HSS)], width, PackMode.EXACTLY, measure=measure).box


def _label_box(text: str, size: Scaled, metrics: FontMetrics | None, measure: CharMeasure) -> Box:
    """
    One panel label, set in the code face at the label size.

    Returns an empty box when the label face did not resolve, for the reason
    `advtext.ui.specimen._Labels` does the same: an unlabelled comparison is a poor
    comparison and an exception raised in a frame callback takes the window with it.
    """
    if not text or metrics is None:
        return hpack([]).box
    key = font_key(Face.CODE, size)
    space = round(metrics.space_width)
    nodes: list[Node] = []
    for character in text:
        nodes.append(
            Glue(interword_glue(space)) if character == " " else CharNode(key, ord(character))
        )
    return hpack(nodes, measure=measure).box


def _prose(
    source: str, theme: Theme, width: Scaled, resolve: MetricsResolver, measure: CharMeasure
) -> Box:
    """
    A caption, composed to `width` through the document's own markdown path.

    Through `build_document` and `compose_blocks` rather than hand-packed, so a
    caption here is broken and set exactly as a paragraph in the Document tab is.
    Returns an empty box rather than raising when a face is missing, matching
    `advtext.ui.specimen._prose`: the formulae are the gallery, and losing the prose
    should cost the prose.
    """
    try:
        document = build_document(source, theme, resolve)
    except Exception:
        return vpack([]).box
    return compose_blocks(document.blocks, theme, width, measure)


def build_gallery(
    theme: Theme,
    width: Scaled,
    resolve: MetricsResolver,
    *,
    math_resolve: MathResolver | None = None,
    measure: CharMeasure | None = None,
    formula_px: float = FORMULA_PX,
    entries: Sequence[EntryDef] = ENTRIES,
) -> Gallery:
    """
    Build the whole gallery: every entry, composed, measured and packed.

    `width` is the measure the *captions* are broken to. It is not a bound on the
    formulae -- a panel row wider than it makes `Gallery.box` wider than it, and the
    caller grows the sheet. See `Gallery.width`.

    `resolve` is the `advtext.style.MetricsResolver` the prose and the labels come
    from; `math_resolve` is the separate `advtext.math.MathResolver` the formulae
    come from and defaults to the real font. `measure` defaults to
    `char_measure(resolve)` and must be the one the caller later hands
    `advtext.shipout.ship` -- `docs/status.md` §4 records that handing ship a
    different metrics than the packing used is an unenforced contract whose only
    symptom is text at the wrong size with nothing raised.

    **The measure must resolve the math keys as well as the prose ones.**
    `char_measure(advtext.style.fontlib_metrics)` does, because a math font key
    round-trips through `parse_font_key` like any other. A caller passing a fake
    resolver that only knows about prose faces will get a `KeyError` from inside
    `hpack`, not a blank formula.
    """
    math_size = sp_from_px(formula_px, theme.px_per_inch)
    label_size = sp_from_px(LABEL_PX, theme.px_per_inch)
    fonts = math_fonts(
        math_size,
        fontlib_math_metrics if math_resolve is None else math_resolve,
        # So a formula holding prose packs: the prose keys go where the captions'
        # do. Nothing in `ENTRIES` holds any, and `fonts.measure` is otherwise the
        # function it was.
        text=resolve,
    )
    resolved = char_measure(resolve) if measure is None else measure

    try:
        label_metrics: FontMetrics | None = resolve(font_key(Face.CODE, label_size))
    except Exception:
        label_metrics = None

    # Pass one: set every panel at its natural width and decide the columns. The
    # content width cannot be known until every row has been measured, and every
    # row has to be packed to the same content width or the plates will not share a
    # left edge, so the two passes are not avoidable by reordering.
    panel_gap = round(math_size * _PANEL_GAP_EMS)
    built: list[tuple[EntryDef, list[Panel], list[Box]]] = []
    content = width
    for entry_def in entries:
        panels: list[Panel] = []
        labels: list[Box] = []
        for panel_def in entry_def.panels:
            box = hpack(
                mlist_to_hlist(list(panel_def.items), panel_def.style, fonts),
                measure=fonts.measure,
            ).box
            label = _label_box(panel_def.label, label_size, label_metrics, resolved)
            column = max(box.width, label.width)
            panels.append(
                Panel(
                    label=panel_def.label,
                    style=panel_def.style,
                    items=panel_def.items,
                    box=box,
                    column=column,
                    label_width=label.width,
                )
            )
            labels.append(label)
        row_width = sum(panel.column for panel in panels) + panel_gap * (len(panels) - 1)
        content = max(content, row_width)
        built.append((entry_def, panels, labels))

    leading = theme.style(BlockKind.PARAGRAPH).interline.baselineskip.width
    stack = _Stack()
    entries_out: list[Entry] = []
    for index, (entry_def, panels, labels) in enumerate(built):
        note = _prose(entry_def.caption, theme, width, resolve, resolved)
        formulae = _columns([panel.box for panel in panels], panels, panel_gap, resolved)
        label_row = (
            _columns(labels, panels, panel_gap, resolved)
            if any(panel.label for panel in panels)
            else None
        )
        plate = _Stack()
        plate.add(note, _skip(theme.style(BlockKind.PARAGRAPH).font.size))
        plate.gap(leading)
        plate.add(_centred(formulae, content, resolved), _skip(math_size))
        if label_row is not None:
            plate.gap(leading // 2)
            plate.add(_centred(label_row, content, resolved), _skip(label_size))
        missing: dict[int, None] = {}
        for panel in panels:
            for codepoint in missing_codepoints(panel.items):
                missing[codepoint] = None
        packed = plate.packed()
        entries_out.append(
            Entry(
                key=entry_def.key,
                title=entry_def.title,
                caption=entry_def.caption,
                panels=tuple(panels),
                box=packed,
                note=note,
                formulae=formulae,
                labels=label_row,
                missing=tuple(missing),
            )
        )
        if index:
            stack.gap(round(leading * _ENTRY_GAP_LEADINGS))
        stack.add(packed, _skip(theme.style(BlockKind.PARAGRAPH).font.size))

    return Gallery(
        entries=tuple(entries_out),
        box=stack.packed(),
        width=width,
        fonts=fonts,
        missing=missing_glyphs(entries),
    )


def _columns(
    boxes: Sequence[Box], panels: Sequence[Panel], gap: Scaled, measure: CharMeasure
) -> Box:
    """
    One row of a plate: each box centred in its panel's column, gaps between.

    The formulae and the labels go through this with the same `panels`, which is what
    puts a label under the panel it names. Centred rather than left-aligned because a
    label is usually narrower than the formula it sits under and a left-aligned label
    reads as belonging to whatever is to its left.
    """
    row: list[Node] = []
    for index, (box, panel) in enumerate(zip(boxes, panels, strict=True)):
        if index:
            row.append(Kern(width=gap))
        row.append(_centred(box, panel.column, measure))
    return hpack(row, measure=measure).box

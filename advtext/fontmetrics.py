"""
What layout is allowed to know about a font.

This module is the seam between typesetting and typography. Everything above it --
`pack`, `linebreak`, `mlist_to_hlist` -- asks questions of a `FontMetrics` and never
learns that fontTools, or a file, or an OpenType table exists. `advtext.fontlib` is
the only module in the tree that answers those questions from a real font, and the
test suite answers them from a hand-written fake with round numbers, which is the
whole reason the interface is here rather than inlined.

**Protocols, not ABCs.** There is no implementation to inherit: every method here is
"look something up in a font", and the two implementations share no code at all. An
ABC would buy `isinstance` checks we do not want and would oblige the test fake to
import this module at runtime to subclass it. Structural typing costs nothing and
lets a fake be a plain class with the right attributes. pptmstr injects two bare
callables for the same reason (`pptmstr/ui/span_layout.py:37-39`); there are ten
operations here rather than two, so a named protocol beats ten callables.

**Units, and why there is no unit type here.** A `FontMetrics` is bound to one face
*at one size*, and every length it returns is a float in whatever unit that size was
given in. Ask for a 16.0 face and advances come back in the same 16.0-per-em unit;
ask for a 16.0 * 65536 face and they come back in scaled points. Nothing is rounded,
because a metric is a ratio of the em and rounding is the caller's decision -- TeX
rounds once, at ship-out (`docs/tex-notes.md` §2), and a metrics layer that rounded
would make that discipline unreachable. This module therefore does not import
`advtext.units`: the conversion belongs at the one boundary that performs it.

`advtext.units` settles on integer scaled points, so the idiom for a caller building
nodes is to construct the face at a size already in scaled points and `round()` each
length on the way into a node. That does not compromise the round-once discipline: a
TFM `char_width` is itself an integer number of scaled points, so a glyph advance is
*already* rounded in TeX, and the accumulation §2 exists to protect is the glue's
rather than the glyphs'.

**Faces are named by role, not by file.** Layout asks for `Face.PROSE_BOLD`, not for
Roboto-Bold.ttf. `advtext.fontlib` owns the mapping, so swapping the prose family is
one table there rather than a grep across the tree. `docs/decisions.md` records why
these particular files were chosen.

Deliberately out of scope here:

- **Shaping.** No ligatures, no contextual substitution, no `GSUB` at all. Kerning is
  the one `GPOS` feature exposed, because it is the one with a visible effect on
  advance widths and the one ImGui cannot give us at all.
- **Bidi, vertical writing, complex scripts.** Left to right, one direction, per
  `docs/decisions.md`.
- **Variable-font axes, colour glyphs, hinting.** A glyph is an outline and an
  advance.
- **Anything that names a file or a path.** That is `fontlib`'s alone.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol


class Face(enum.Enum):
    """
    The typographic roles this project renders, named by role rather than by family.

    `CODE_BOLD` is the one role with no file behind it in the fonts imgui-bundle
    ships: the bundle has a single Inconsolata weight. It exists so that a host
    with a bold monospace of its own has a role to register it under
    (`advtext.fontlib.register_font`); until one is registered `advtext.fontlib`
    backs it with `PROSE_BOLD`'s file, which is what bold inside code was set in
    before this member existed. So iterating `Face` now visits a role that may
    share a file with another -- a caller that wants one entry per *file* asks
    `advtext.fontlib.backing_face`.
    """

    PROSE = "prose"
    PROSE_BOLD = "prose-bold"
    PROSE_ITALIC = "prose-italic"
    PROSE_BOLD_ITALIC = "prose-bold-italic"
    CODE = "code"
    CODE_BOLD = "code-bold"
    MATH = "math"


@dataclass(frozen=True, slots=True)
class GlyphBBox:
    """
    The ink extent of one glyph, measured from its origin on the baseline, y up.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def height(self) -> float:
        """
        TeX's `height`: how far the ink reaches *above* the baseline.

        Negative for a glyph that lies entirely below the baseline. Not clamped to
        zero, because the caller packing it into a box is the one that knows whether
        a negative height is a bug or a subscript.
        """
        return self.y_max

    @property
    def depth(self) -> float:
        """
        TeX's `depth`: how far the ink reaches *below* the baseline, positive down.

        `height` and `depth` are both measured from the baseline and are not the two
        halves of a bounding box with a top-left origin. Confusing them is the most
        common porting error in this whole model; `docs/tex-notes.md` §1 defines both.
        """
        return -self.y_min

    @property
    def width(self) -> float:
        """
        Ink width, which is not the advance -- a glyph may overhang either side.
        """
        return self.x_max - self.x_min


@dataclass(frozen=True, slots=True)
class GlyphVariant:
    """
    One link in a chain of ascending-size variants of a glyph.

    `extent` is the variant's size along the axis it grows on -- for the vertical
    chain that `make_op` follows, height plus depth. OpenType calls the field
    `AdvanceMeasurement`; the name is a misnomer for vertical constructions, where it
    has nothing to do with the horizontal advance, so it is not reused here.

    The chain is in ascending order and its first entry is the base glyph itself.

    **`codepoint` may be synthetic, and that is the whole reason this field exists.**
    Latin Modern Math leaves most of its variants unencoded -- `summation.v1`, the
    display-size sigma the litmus test turns on, has no codepoint in the font at all
    -- so the implementation mints one in a private-use plane and adds it to that
    face's own cmap. A `CharNode` can then carry it and every existing lookup works.
    A synthetic codepoint **is not Unicode**: it is meaningful only to the face that
    issued it, it will differ between fonts, and anything that serialises a range to
    text must map it back through the layout rather than emitting it. `advtext.
    selection` is the module that has to care.
    """

    name: str
    codepoint: int
    extent: float


@dataclass(frozen=True, slots=True)
class MathParams:
    """
    TeX's math font parameters, under TeX's names, at one size.

    `docs/tex-notes.md` §10 lists these as family-2 ("sigma", σ1-σ22) and family-3
    ("xi", ξ1-ξ13) `\\fontdimen`s and observes that a plain TrueType font has none of
    them. A font with an OpenType `MATH` table does, under different names and with
    two of TeX's distinctions collapsed. `advtext.fontlib`'s module docstring carries
    the field-by-field mapping, including which values are the font's and which were
    synthesised and from what.

    Names are TeX's rather than OpenType's on purpose: `advtext.math` is a port of
    `mlist_to_hlist`, and a reader checking it against §749 should be able to match
    identifiers by eye.

    All lengths are in the size unit of the `FontMetrics` that produced them. The two
    scale factors are dimensionless.
    """

    # σ5, σ6. Reused text parameters; the math ones start at σ8.
    math_x_height: float
    math_quad: float
    # σ8-σ10, numerator shift-up: display, non-display with rule, non-display \atop.
    num1: float
    num2: float
    num3: float
    # σ11, σ12, denominator shift-down: display, non-display.
    denom1: float
    denom2: float
    # σ13-σ15, superscript shift-up: display, non-display, cramped.
    sup1: float
    sup2: float
    sup3: float
    # σ16, σ17, subscript shift-down: alone, and with a superscript present.
    sub1: float
    sub2: float
    # σ18, σ19. Script baseline relative to the top/bottom of the nucleus box.
    sup_drop: float
    sub_drop: float
    # σ20, σ21. \atopwithdelims delimiter size: display, non-display.
    delim1: float
    delim2: float
    # σ22. Where a fraction bar sits, and what make_op centres the operator on.
    axis_height: float
    # ξ8. Fraction bars, \overline, and §759's 4 * default_rule_thickness clearance.
    default_rule_thickness: float
    # ξ9-ξ13, in §751's roles: 1 and 2 are minimum *gaps* above and below the
    # operator, 3 and 4 are minimum *baseline distances*, and 5 is unconditional
    # padding outside the limits.
    big_op_spacing1: float
    big_op_spacing2: float
    big_op_spacing3: float
    big_op_spacing4: float
    big_op_spacing5: float
    # No TeX parameter, because TeX reads all three off other things: the rule
    # over a radicand is as thick as the surd glyph is *tall* (a TFM convention,
    # make_radical at tex.web:14476), and the clearance under it is computed from
    # ξ8 and σ5. OpenType states the three outright. For Latin Modern Math they
    # are TeX's formula evaluated, which tests/test_fontmetrics.py pins.
    radical_rule_thickness: float
    radical_vertical_gap: float
    radical_display_style_vertical_gap: float
    # Dimensionless. TeX takes the script sizes from \scriptfont and \scriptscriptfont
    # and has no parameter for the ratio; OpenType states it, so we use it.
    script_scale: float
    script_script_scale: float
    # No TeX counterpart. OpenType's rule for picking a display-size operator is
    # "the first variant at least this tall" where TeX's is "one step along the
    # chain". They agree for Latin Modern Math's summation; see fontlib.
    display_operator_min_height: float


class FontMetrics(Protocol):
    """
    One face at one size: everything horizontal layout needs to place a glyph.
    """

    @property
    def face(self) -> Face:
        """
        Which role this is, so a draw command can record it without a back-reference.
        """

    @property
    def size(self) -> float:
        """
        The em size every other length here is expressed against.
        """

    @property
    def ascent(self) -> float:
        """
        Face ascent, positive up from the baseline.
        """

    @property
    def descent(self) -> float:
        """
        Face descent, positive *down* from the baseline, matching TeX's `depth`.
        """

    @property
    def x_height(self) -> float:
        """
        Height of a lowercase x; TeX's σ5 and the unit `\\ex` is measured in.
        """

    @property
    def em(self) -> float:
        """
        One em, which is the size. Present so `em` reads as a length at a call site.
        """

    @property
    def space_width(self) -> float:
        """
        Advance of U+0020, the natural width of an interword glue.
        """

    def has(self, codepoint: int) -> bool:
        """
        Whether the font maps this codepoint to a real glyph.
        """

    def advance(self, codepoint: int) -> float:
        """
        How far the pen moves after setting this codepoint, kerning excluded.
        """

    def bbox(self, codepoint: int) -> GlyphBBox:
        """
        The glyph's ink extent, from which TeX's char height and depth are read.
        """

    def kern(self, codepoint: int, following: int) -> float:
        """
        The `GPOS` kern between an adjacent pair, usually negative or zero.
        """


class MathFontMetrics(FontMetrics, Protocol):
    """
    A face that also carries an OpenType `MATH` table.

    Separate from `FontMetrics` so that the type system, rather than a runtime check,
    stops `mlist_to_hlist` being handed a prose face -- Roboto has no `MATH` table and
    every parameter it would need would have to be invented.
    """

    @property
    def math(self) -> MathParams:
        """
        TeX's σ and ξ parameters for this face at this size.
        """

    def italic_correction(self, codepoint: int) -> float:
        """
        TeX's `char_italic`: the lean to add after a glyph, `delta` in §749.
        """

    def vertical_variants(self, codepoint: int) -> tuple[GlyphVariant, ...]:
        """
        The ascending-size chain TeX reaches through `list_tag`, or `()` if there is
        none. Ascending, and the first entry is the base glyph.
        """

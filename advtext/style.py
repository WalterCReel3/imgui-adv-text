r"""
Everything the look of the document is made of, in one place.

`advtext.markdown` decides what a piece of text *is* -- a level-two heading, a
list item, an emphasised run -- and this module decides what that looks like:
which face, at what size, on what leading, with how much air above and below.
The converter names semantics and never a number, so the whole appearance can be
changed here without touching a line of it. That split is the point; a converter
that reached for `sp_from_px(25.0)` inline would put the type scale in twenty
places.

This is also where the two halves of the project meet. `advtext.nodes` keeps a
`FontKey` opaque so the layout core never learns what a font is, and
`advtext.fontmetrics` hands out faces resolved at a size. The encoding between
them is `font_key`/`parse_font_key` here, and `char_measure` is the adapter
`hpack` takes: it is the one place floats from the metrics layer become the
scaled-point integers everything downstream adds up.

## The type scale, and the decisions inside it

**A modular scale of 1.25 (a major third) from a 16 px body.** Sizes are 16,
20, 25 and 31.25 px for body, h3, h2 and h1. A ratio rather than a hand-picked
set because the relationships are then visible in the output -- a reader cannot
say why an arbitrary 22 px heading looks wrong, only that it does -- and 1.25
rather than something larger because four steps of 1.5 would put h1 at 54 px in
a document whose longest heading is a sentence.

**Code is set at the body size, not smaller.** The instinct is to shrink
monospace, and here it would be backwards: Inconsolata's x-height is 0.457 of
its em where Roboto's is 0.528, so at equal em sizes the code already reads
about 13 per cent smaller. Matching x-heights exactly would mean setting code at
18.5 px, which is too loud next to prose. Equal em sizes is the compromise and
this is the note that stops someone "fixing" it downward.

**The list gutter is sized from the widest marker the theme promises, not from
a round number.** `list_indent` is what a list adds to everything inside it, and
it is also the width of the box a hanging marker is right-aligned in, less
`marker_gap`. So the gutter has to hold the *marker*, and a gutter picked as a
round 1.5 em holds "1." and not "10.": Roboto's digits are tabular at 0.5615 em
with a 0.2632 em period, so a one-digit marker is 0.8247 em and a two-digit one
is **1.3862 em** -- and 1.5 em less a 0.5 em gap leaves 1.0 em. The marker then
overfulls its box, eats the gap and touches its own text. `WIDEST_MARKER_EM` is
that measurement rounded up, and the gutter is it plus the gap, which is 1.9 em.

Sizing it per list from the actual markers would be better typography and is a
different change: the gutter is also the `ParShape` indent every *continuation*
line of the item is broken to, so it is decided in `advtext.markdown` before
anything has been packed, and moving it means the converter measures. One number
for every list in the document is also what makes a bullet list and an ordered
list line up with each other, which is worth something on its own.

**Three digits still overfull**, deliberately. "100." is 1.9478 em and would want
a 2.45 em gutter -- a sixth of the measure given over to margin on the chance
that a list runs past ninety-nine. `advtext.ui` packs the marker with stretch-only
glue so the failure stays inside the gutter rather than hanging off the left edge
of the page, and that is the case this theme chooses to lose.

**Paragraph spacing, and no first-line indent.** Both exist to mark where one
paragraph ends and the next begins, and using both says it twice. Print sets
`\parindent` and no `\parskip`; screens with a wide measure read better with the
space. We take the space.

**Headings are ragged right, body text is justified.** Justification needs
enough words per line to hide the stretched spaces, and a three-word heading at
31 px has nowhere to hide them.

## The strut, and why a line's height is not the ink on it

`hpack` takes the **maximum** over its contents, and a `CharNode`'s contribution
is its glyph's *ink* bounding box. So an hbox of `xxx` really does have x-height
and zero depth, faithfully to TeX -- and a line of `acem` is then visibly
shorter than the line of `gjpqy` under it. Nothing about the geometry is wrong;
what is wrong is everything that treats a line box as a line. A selection
highlight is drawn from the line box, so its bottom edge jumps by a descender
between one line and the next and its top edge jumps by an ascender, and a
highlight whose height flickers with which letters happened to land on a line
reads as broken even though each rectangle is individually correct.

TeX's answer is `\strut`: an invisible zero-width box with fixed height and
depth, dropped into a line so the line cannot be shorter than it. `Strut` here
is that, as data, and `BlockStyle.strut` is the one each of a block's lines
gets. **Two decisions inside it:**

- **The strut fills the block's own `\baselineskip` exactly**, which is
  plain.tex's: `\strutbox` is 8.5pt over 3.5pt with `\baselineskip=12pt`, so the
  strut *is* the baseline-to-baseline distance. Nothing here is free to pick a
  different total. A strut taller than the leading makes §679 fall through to
  `\lineskip` on every line and quietly loosens the whole document; a shorter
  one leaves a seam between adjacent highlights. At exactly the leading, §679's
  interline glue comes out at zero and successive line boxes tile.
- **Three quarters of it above the baseline and one quarter below.** plain.tex's
  own split is 8.5:3.5, and this is the nearest coarser one that clears every
  ASCII glyph in all five bundled faces at the *tightest* leading this theme
  generates -- the h1's 1.15 em, where three quarters is 0.8625 em against a
  worst ASCII ink height of 0.8271 em (bold `[`) and a worst depth of 0.2568 em.
  plain.tex's ratio itself does not clear it, by 0.013 em. Measured, not assumed.

It is derived from the leading rather than from the face's ascent and descent,
which is the other obvious source and is worse in two ways: a line mixing prose
with inline code would take whichever face was taller and stop matching the line
above it, and `hhea` ascent plus descent is not the leading, so lines would tile
with a gap or an overlap that no parameter controls.

**A strut is a floor and not a clamp**, which is the part to keep in mind. It is
applied as `hpack`'s own maximum, so anything genuinely taller still raises the
line -- a display formula, and also `Ẳ` at 1.03 em or a box-drawing `│` at 1.0
em over 0.4 em. §679 then moves that line down, which is exactly what
`\lineskip` is for. What the strut removes is the variation that carries no
information: whether this line happened to contain a `g`.

**Block spacing does not stretch.** `space_above` and `space_below` are rigid
glue on purpose: nothing in this project packs a page to a fixed height --
page breaking is out of scope (`docs/decisions.md`) -- so stretch on block
spacing would be a parameter with no reader. Interword glue *is* stretchable,
because that is what `advtext.linebreak` justifies with.

## Interword glue, and the fractions behind it

A space is `Glue`, never a `CharNode` of U+0020. That is the whole reason this
project exists: a fixed advance cannot be justified.

TeX takes a space's natural width, stretch and shrink from `\fontdimen` 2, 3 and
4 (`docs/tex-notes.md` §10.2), which a TrueType font does not carry, so the last
two are synthesised as fractions of the first: **stretch = 1/2 space, shrink =
1/3 space, extra_space = 1/3 space**. Those are not invented -- they are
cmr10's own ratios. cmr10 has space = 0.333334 em, space_stretch = 0.166667 em
and space_shrink = 0.111112 em, which are exactly one half and one third of the
space, and extra_space = 0.111112 em, another third.

**The space factor is implemented, in the one form that shows.** §1034's rule
gives a sentence-ending period a space factor of 3000, which widens the
following space by `extra_space`, triples its stretch and divides its shrink by
three (§1044). That is the difference between the classic look and the flat one.
The rule that makes it usable is also §1034's: an uppercase letter sets the
factor to 999, and a punctuation mark after a low factor raises it only to 1000
-- so "the NASA. budget" gets an ordinary space while "the end. Next" gets the
wide one. Abbreviations like "e.g." still fool it, exactly as they fool TeX,
which is why TeX has `\@`.

**How much of §1044 to apply is a taste decision, and `Spacing` is where it is
made.** The transcription above is plain TeX's `\nonfrenchspacing` and it is
faithful; what it is not is automatically right for this demo. The stretch
tripling is the part that shows: because the sentence space carries three times
the elasticity of the spaces around it, it takes three times the share of
whatever a justified line was short by, and the gap grows *with* the stretch
rather than staying a fixed fraction wider. Measured on `demo/columns.md` at a
468 px measure, the space after "people guess." set to **23.72 px** against
**10.11 px** either side of it -- 2.35x, on a line whose natural ratio is 1.33x.
`Spacing` offers the three answers: keep §1044 whole, drop it entirely
(`\frenchspacing`), or keep the wider natural width and drop only the elasticity
scaling. The theme picks one; nothing else does.

Deliberately out of scope here: colour (nothing in the node model carries one
yet), per-block background fills, and the full `\sfcode` table -- only the four
classes §1034 distinguishes are implemented, not an assignable code per
character.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeAlias

from advtext.fontmetrics import Face, FontMetrics
from advtext.nodes import Box, CharNode, FontKey, GlueSpec
from advtext.pack import CharDimens, CharMeasure, InterlineSkip
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, sp_from_px

__all__ = [
    "Align",
    "BlockKind",
    "BlockStyle",
    "Emphasis",
    "FontSpec",
    "NEUTRAL_SPACE_FACTOR",
    "MARKER_GAP_EM",
    "MetricsResolver",
    "QUOTE_INDENT_EM",
    "STRUT_HEIGHT_FRACTION",
    "WIDEST_MARKER_EM",
    "Spacing",
    "Strut",
    "Theme",
    "char_measure",
    "font_key",
    "fontlib_metrics",
    "interword_glue",
    "parse_font_key",
    "space_factor_after",
]

# The modular scale's ratio, and the body size it is measured from. Together they
# generate every prose size in the document; nothing else picks a size by hand.
TYPE_SCALE_RATIO = 1.25
BODY_SIZE_PX = 16.0

# TeX's \fontdimen 3, 4 and 7 as fractions of \fontdimen 2, which is what cmr10's
# own values come to. See the module docstring.
SPACE_STRETCH_FRACTION = 0.5
SPACE_SHRINK_FRACTION = 1.0 / 3.0
EXTRA_SPACE_FRACTION = 1.0 / 3.0

# §1034's four space-factor classes. The neutral one is the implicit default and
# is public because `advtext.markdown` has to start a run of text at it.
NEUTRAL_SPACE_FACTOR = 1000
_SF_UPPERCASE = 999
_SF_SENTENCE_END = 3000
_SF_TRANSPARENT = 0

_SENTENCE_ENDING = ".?!"
# Closing marks are transparent: they leave the factor as the character before
# them set it, so `end."` still earns the wide space that `end.` did.
_TRANSPARENT = ")]'”’\""

# The factor at or above which §1044 adds extra_space rather than only rescaling.
_EXTRA_SPACE_THRESHOLD = 2000

# The list gutter, in ems of the body size, and what it is made of. See the
# module docstring: `WIDEST_MARKER_EM` is a measurement of this theme's own prose
# face and not a guess, and the two are added rather than one being a fraction of
# the other because they are a marker and a gap and neither scales with the other.
MARKER_GAP_EM = 0.5
WIDEST_MARKER_EM = 1.4
QUOTE_INDENT_EM = 1.5

STRUT_HEIGHT_FRACTION = 0.75
"""
How much of a strut sits above the baseline; the rest sits below it.

The module docstring argues the number. It is public because a caller building a
`Strut` by hand -- a test, or a theme that generates its own leading -- needs the
same split the theme uses, and copying `0.75` is how two of them drift apart.
"""


class Spacing(enum.Enum):
    """
    How much of §1044's sentence-space rule a document applies. A taste decision.

    §1044 (`docs/tex.web:20373-20375`) does three things to the glue after a
    space factor of 3000 or more: adds `extra_space` to its natural width,
    multiplies its stretch by the factor, and divides its shrink by it. The
    three members here are "all of that", "none of it" and "the width only".

    Which one a page wants is not derivable from the source, because the source
    only says what `\\nonfrenchspacing` *does*. Plain TeX defaults to it for
    historical American practice and offers `\\frenchspacing` -- a macro that
    sets every `\\sfcode` to 1000, so §1034's neutral branch always fires and
    §1044 is never reached at all (§1030, `docs/tex.web:20052`, only calls
    `app_space` when the factor is not 1000). Most contemporary typography takes
    the French side.
    """

    NONFRENCH = enum.auto()
    """Plain TeX's default: §1044 entire. The faithful transcription."""

    FRENCH = enum.auto()
    """`\\frenchspacing`: every interword space identical, whatever precedes it."""

    EXTRA_SPACE_ONLY = enum.auto()
    """
    §1044's `extra_space` widening, without its stretch and shrink scaling.

    A sentence space is a third wider than a word space at natural width and
    stays a third wider however hard the line is stretched, because it now
    carries the same elasticity as its neighbours and so takes the same share of
    the slack. This has no `tex.web` counterpart; it is this project's answer to
    a defect §1044 produces at narrow measures, and it is the theme default.
    """


class Align(enum.Enum):
    """
    How a line's slack is disposed of once the breaker has chosen where to cut.
    """

    JUSTIFY = enum.auto()
    LEFT = enum.auto()
    CENTER = enum.auto()
    RIGHT = enum.auto()


class BlockKind(enum.Enum):
    """
    The document semantics this project renders, which is the litmus test's list.

    `docs/decisions.md` states the requirement: headings, paragraphs with
    emphasis, both list kinds, a quote, fenced code, a rule and a table, laid out
    as one document. Anything markdown offers beyond this set is not rendered, so
    adding a member here without adding a `BlockStyle` for it is a `KeyError` at
    the first document that uses it rather than a silent default.
    """

    HEADING_1 = enum.auto()
    HEADING_2 = enum.auto()
    HEADING_3 = enum.auto()
    PARAGRAPH = enum.auto()
    BULLET_ITEM = enum.auto()
    ORDERED_ITEM = enum.auto()
    QUOTE = enum.auto()
    CODE = enum.auto()
    RULE = enum.auto()
    TABLE = enum.auto()


@dataclass(frozen=True, slots=True)
class Emphasis:
    """
    The inline styling in force at a point in the text, as flags rather than a face.

    Kept separate from `Face` because the same emphasis means a different face in
    a heading than in a paragraph -- bold inside an already-bold heading is not a
    fifth Roboto weight. `Theme.face_for` performs that resolution.
    """

    bold: bool = False
    italic: bool = False
    code: bool = False

    def with_(self, *, bold: bool | None = None, italic: bool | None = None) -> Emphasis:
        """
        The same emphasis with one flag changed.
        """
        return Emphasis(
            bold=self.bold if bold is None else bold,
            italic=self.italic if italic is None else italic,
            code=self.code,
        )


@dataclass(frozen=True, slots=True)
class FontSpec:
    """
    A face resolved at a size: what a `FontKey` names.
    """

    face: Face
    size: Scaled

    @property
    def key(self) -> FontKey:
        """
        The opaque string `advtext.nodes.CharNode` carries.
        """
        return font_key(self.face, self.size)


def font_key(face: Face, size: Scaled) -> FontKey:
    """
    Encode a face and a size as the opaque key the layout core passes around.

    Readable on purpose -- a `CharNode` in a failing test prints as
    `CharNode(font='prose-bold@1972352', codepoint=84)` and the reader can see
    which face went wrong without a lookup table.
    """
    return f"{face.value}@{size}"


def parse_font_key(key: FontKey) -> FontSpec:
    """
    The inverse of `font_key`. Raises `ValueError` on anything it did not write.
    """
    name, _, size = key.rpartition("@")
    if not name or not size:
        raise ValueError(f"{key!r} is not a font key; expected 'face@size'")
    return FontSpec(face=Face(name), size=int(size))


MetricsResolver: TypeAlias = Callable[[FontKey], FontMetrics]
"""
How a key becomes measurable.

Injected rather than imported so that a test can supply a fake with round
numbers and never open a font: `advtext.markdown`'s tests compute expected widths
by hand, which is only possible if the widths are chosen rather than measured.
`fontlib_metrics` is the real one.
"""


def fontlib_metrics(key: FontKey) -> FontMetrics:
    """
    The production resolver: a key, a real font file, real advances and kerns.

    The size in the key is in scaled points and is handed to `advtext.fontlib` as
    the em size, so every length that comes back is already in scaled points --
    as a float, because a metric is a ratio of the em and rounding is this
    module's decision, made once in `char_measure`.
    """
    from advtext import fontlib

    spec = parse_font_key(key)
    return fontlib.metrics(spec.face, float(spec.size))


def char_measure(resolve: MetricsResolver) -> CharMeasure:
    """
    The `hpack` adapter: a `CharNode` in, scaled-point dimensions out.

    This is the one rounding between the metrics layer and the layout core, and
    it is faithful rather than a concession. A TFM `char_width` is itself an
    integer number of scaled points (`docs/tex-notes.md` §10.1), so a glyph
    advance is *already* rounded in TeX; the accumulation §2 protects against is
    the glue's, at ship-out, and that stays exact.

    Memoised per (key, codepoint) because `hpack` measures every character on
    every pass and the line breaker packs a paragraph many times over.
    """
    cache: dict[tuple[FontKey, int], CharDimens] = {}

    def measure(node: CharNode) -> CharDimens:
        cached = cache.get((node.font, node.codepoint))
        if cached is not None:
            return cached
        metrics = resolve(node.font)
        box = metrics.bbox(node.codepoint)
        dimens = CharDimens(
            width=round(metrics.advance(node.codepoint)),
            height=round(box.height),
            depth=round(box.depth),
        )
        cache[(node.font, node.codepoint)] = dimens
        return dimens

    return measure


def space_factor_after(character: str, current: int = NEUTRAL_SPACE_FACTOR) -> int:
    """
    TeX's space factor after setting one character (§1034), transcribed.

    The four branches are the source's, in its order, and the third is the one
    worth keeping: a sentence-ending mark raises the factor to 3000 only when the
    factor was not already below 1000. An uppercase letter puts it at 999, so the
    period ending "...at NASA." leaves an ordinary space behind it.
    """
    code = _sf_code(character)
    if code == NEUTRAL_SPACE_FACTOR:
        return NEUTRAL_SPACE_FACTOR
    if code < NEUTRAL_SPACE_FACTOR:
        return code if code > _SF_TRANSPARENT else current
    if current < NEUTRAL_SPACE_FACTOR:
        return NEUTRAL_SPACE_FACTOR
    return code


def _sf_code(character: str) -> int:
    """
    The `\\sfcode` of one character, in the four classes this project distinguishes.
    """
    if character in _SENTENCE_ENDING:
        return _SF_SENTENCE_END
    if character in _TRANSPARENT:
        return _SF_TRANSPARENT
    if character.isupper():
        return _SF_UPPERCASE
    return NEUTRAL_SPACE_FACTOR


def interword_glue(
    space_width: Scaled,
    space_factor: int = NEUTRAL_SPACE_FACTOR,
    spacing: Spacing = Spacing.NONFRENCH,
) -> GlueSpec:
    """
    The glue between two words, scaled by the space factor (§1042, §1044).

    `space_width` is the face's advance for U+0020; the stretch and shrink are
    the em fractions the module docstring justifies. A factor of 1000 is the
    ordinary case and costs nothing.

    `spacing` says how much of §1044 to apply; see `Spacing`. It defaults to the
    faithful `NONFRENCH` so that a caller with no opinion -- a test of the
    transcription, a fragment builder with no theme to hand -- gets plain TeX.
    A caller that renders a *document* takes it from `Theme.spacing` instead,
    which defaults the other way.
    """
    stretch = round(space_width * SPACE_STRETCH_FRACTION)
    shrink = round(space_width * SPACE_SHRINK_FRACTION)
    width = space_width
    if spacing is not Spacing.FRENCH and space_factor != NEUTRAL_SPACE_FACTOR:
        if space_factor >= _EXTRA_SPACE_THRESHOLD:
            width += round(space_width * EXTRA_SPACE_FRACTION)
        if spacing is Spacing.NONFRENCH:
            stretch = round(stretch * space_factor / NEUTRAL_SPACE_FACTOR)
            shrink = round(shrink * NEUTRAL_SPACE_FACTOR / space_factor)
    return GlueSpec(width=width, stretch=stretch, shrink=shrink)


@dataclass(frozen=True, slots=True)
class Strut:
    """
    TeX's `\\strut` as data: the height and depth no line of a block may fall below.

    Why a line needs one at all is the module docstring's argument. What this
    type is for is that the answer has to be the *same* for every line of a
    block, and a height and a depth that travel separately are how two lines end
    up with one each.

    `height` and `depth` are measured from the baseline, upward and downward, as
    everywhere else in this project.
    """

    height: Scaled
    depth: Scaled

    @classmethod
    def filling(cls, leading: Scaled) -> Strut:
        """
        The strut that exactly fills one baseline-to-baseline distance.

        The depth is the remainder rather than a second rounding, so
        `height + depth` is `leading` to the scaled point and §679's interline
        glue between two strutted lines is exactly zero rather than off by one.
        """
        height = round(leading * STRUT_HEIGHT_FRACTION)
        return cls(height=height, depth=leading - height)

    @property
    def total(self) -> Scaled:
        """
        The whole vertical extent, which is what a selection highlight comes to.
        """
        return self.height + self.depth

    def applied_to(self, box: Box) -> Box:
        """
        `box` with the strut in it: its own dimensions, floored at the strut's.

        Identical to packing a zero-width strut box into the list -- `hpack`
        takes the maximum of its items' heights and of their depths, and a strut
        of no width changes nothing else -- and it is written as the maximum
        rather than as a repack because repacking a line the breaker has already
        set to an exact width means recomputing a `glue_set` that is already
        correct, once per line of the document, to reach the same two numbers.

        A maximum and not an assignment: see the module docstring on a strut
        being a floor. Clamping instead would let a display formula's box hang
        outside the line that contains it, and the overlap would land in the line
        above rather than anywhere near the cause.
        """
        return replace(
            box,
            height=max(box.height, self.height),
            depth=max(box.depth, self.depth),
        )


@dataclass(frozen=True, slots=True)
class BlockStyle:
    """
    Every typographic parameter one kind of block is set with.

    `interline` is the triple §679 consults between the lines of this block, and
    it belongs to the block rather than to the document because a heading wants
    tighter leading than a paragraph and passing three loose lengths around is
    how two of them end up from different blocks.
    """

    font: FontSpec
    interline: InterlineSkip
    align: Align = Align.JUSTIFY
    space_above: Scaled = 0
    space_below: Scaled = 0
    left_indent: Scaled = 0
    first_line_indent: Scaled = 0

    @property
    def strut(self) -> Strut:
        """
        The strut every line of this block is set on.

        Derived from `interline` rather than stored beside it, because the two
        have to agree -- a strut that is not the block's own leading is the one
        way to get interline glue that is not zero -- and a field would let a
        caller set them apart.
        """
        return Strut.filling(self.interline.baselineskip.width)


def _px(pixels: float, px_per_inch: float) -> Scaled:
    """
    A length given in device pixels, in scaled points.
    """
    return sp_from_px(pixels, px_per_inch)


def _leading(size: Scaled, ratio: float) -> InterlineSkip:
    """
    The interline triple for one size: a baseline distance, and a floor under it.

    `lineskip` is the fallback §679 uses when a tall line would otherwise collide
    with the one above; `lineskiplimit` of zero means "never let the boxes touch",
    which is TeX's plain default and the only value with an obvious meaning.
    """
    return InterlineSkip(
        baselineskip=GlueSpec(width=round(size * ratio)),
        lineskip=GlueSpec(width=round(size * 0.1)),
        lineskiplimit=0,
    )


@dataclass(frozen=True, slots=True)
class Theme:
    """
    The whole appearance of a document, as data.

    Built by `Theme.build`, which generates the type scale rather than listing
    it. Every consumer reads `blocks[kind]`; nothing computes a size.
    """

    blocks: dict[BlockKind, BlockStyle]
    px_per_inch: float
    # Hung to the left of a list item's text, with this much air between.
    marker_gap: Scaled
    # What a container adds to the left indent of everything inside it. These
    # live on the theme rather than on a `BlockStyle` because they are properties
    # of the *nesting*, and a nested list must add one per level; `BlockStyle`'s
    # own `left_indent` is what a block adds to itself on top of its containers.
    list_indent: Scaled
    quote_indent: Scaled
    # A thematic break, and the bar down the left of a block quote.
    rule_thickness: Scaled
    quote_rule_thickness: Scaled
    # Air inside a table cell, left and right of its content.
    cell_padding: Scaled
    # Thickness of the line under a table's header row. Zero means no line.
    table_rule_thickness: Scaled
    # How much of §1044's sentence-space rule the document's prose applies. See
    # `Spacing`; it lives on the theme because it is an appearance decision about
    # a whole document and not a property of any one block.
    spacing: Spacing = Spacing.EXTRA_SPACE_ONLY

    @classmethod
    def build(
        cls,
        base_px: float = BODY_SIZE_PX,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        *,
        spacing: Spacing = Spacing.EXTRA_SPACE_ONLY,
    ) -> Theme:
        """
        The default look, generated from one body size and one ratio.
        """
        r = TYPE_SCALE_RATIO
        body = _px(base_px, px_per_inch)
        h3 = _px(base_px * r, px_per_inch)
        h2 = _px(base_px * r * r, px_per_inch)
        h1 = _px(base_px * r * r * r, px_per_inch)

        def heading(size: Scaled, above: float, below: float) -> BlockStyle:
            return BlockStyle(
                font=FontSpec(Face.PROSE_BOLD, size),
                # Large type wants proportionally less leading: what the eye
                # tracks is the ratio of the gap to the x-height, and the
                # x-height has grown with the size while the gap need not.
                interline=_leading(size, 1.15),
                align=Align.LEFT,
                space_above=round(size * above),
                space_below=round(size * below),
            )

        body_leading = _leading(body, 1.35)
        styles: dict[BlockKind, BlockStyle] = {
            BlockKind.HEADING_1: heading(h1, 1.0, 0.4),
            BlockKind.HEADING_2: heading(h2, 0.9, 0.35),
            BlockKind.HEADING_3: heading(h3, 0.8, 0.3),
            BlockKind.PARAGRAPH: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.JUSTIFY,
                space_below=round(body * 0.55),
            ),
            BlockKind.BULLET_ITEM: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.JUSTIFY,
                space_below=round(body * 0.2),
            ),
            BlockKind.ORDERED_ITEM: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.JUSTIFY,
                space_below=round(body * 0.2),
            ),
            BlockKind.QUOTE: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.JUSTIFY,
                space_above=round(body * 0.5),
                space_below=round(body * 0.5),
            ),
            BlockKind.CODE: BlockStyle(
                # Code is not line-broken: a fenced block's line endings are
                # content, so every line is set ragged and long lines overflow
                # rather than wrap somewhere the author did not choose.
                font=FontSpec(Face.CODE, body),
                interline=_leading(body, 1.25),
                align=Align.LEFT,
                space_above=round(body * 0.6),
                space_below=round(body * 0.6),
                left_indent=round(body * 1.0),
            ),
            BlockKind.RULE: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.LEFT,
                space_above=body,
                space_below=body,
            ),
            BlockKind.TABLE: BlockStyle(
                font=FontSpec(Face.PROSE, body),
                interline=body_leading,
                align=Align.LEFT,
                space_above=round(body * 0.7),
                space_below=round(body * 0.7),
            ),
        }
        return cls(
            blocks=styles,
            px_per_inch=px_per_inch,
            marker_gap=round(body * MARKER_GAP_EM),
            list_indent=round(body * (WIDEST_MARKER_EM + MARKER_GAP_EM)),
            quote_indent=round(body * QUOTE_INDENT_EM),
            rule_thickness=max(1, round(body * 0.06)),
            quote_rule_thickness=max(1, round(body * 0.15)),
            cell_padding=round(body * 0.5),
            table_rule_thickness=max(1, round(body * 0.06)),
            spacing=spacing,
        )

    def style(self, kind: BlockKind) -> BlockStyle:
        """
        The parameters one block kind is set with.
        """
        return self.blocks[kind]

    def face_for(self, kind: BlockKind, emphasis: Emphasis) -> Face:
        """
        Which of the six faces a run of text in this context is set in.

        Inline code wins over everything: there is one monospace face and a bold
        run inside a code span has no bolder one to reach for. Otherwise the
        block's own face supplies the baseline weight, so italic inside a heading
        is bold-italic rather than a sudden drop to the regular weight -- Roboto
        ships all four as real faces, which is why this is a lookup and not the
        colour shift pptmstr has to fall back on (`docs/decisions.md`).
        """
        if emphasis.code:
            return Face.CODE
        base = self.style(kind).font.face
        bold = emphasis.bold or base in (Face.PROSE_BOLD, Face.PROSE_BOLD_ITALIC)
        italic = emphasis.italic or base in (Face.PROSE_ITALIC, Face.PROSE_BOLD_ITALIC)
        if bold and italic:
            return Face.PROSE_BOLD_ITALIC
        if bold:
            return Face.PROSE_BOLD
        if italic:
            return Face.PROSE_ITALIC
        return Face.PROSE

    def font_for(self, kind: BlockKind, emphasis: Emphasis) -> FontSpec:
        """
        `face_for` at the block's own size.
        """
        return FontSpec(self.face_for(kind, emphasis), self.style(kind).font.size)

r"""
The look of a document, as data: the theme, its block styles and the roles they name.

`imscribe.markdown` decides what a piece of text *is* -- a level-two heading, a
list item, an emphasised run -- and this module decides what that looks like:
which face, at what size, on what leading, with how much air above and below.
The converter names semantics and never a number, so the whole appearance can be
changed here without touching a line of it. That split is the point; a converter
that reached for `sp_from_px(25.0)` inline would put the type scale in twenty
places.

## Why this is its own module, and what it loads

Until 2026-10-11 everything here was in `imscribe.style`, in one file with the
adapters that *measure* -- `char_measure`, `interword_glue`, the space factor
-- and those need the layout core's node and packing types. So anything that
wanted to know what a heading looks like loaded `imscribe.nodes`,
`imscribe.pack` and `imscribe.badness`, the modules that set text through
imtypeset and never build a node included. The data half is here now and the
measuring half stayed. **`imscribe.style` imports every name of this module
back**: `from imscribe.style import Theme` is this module's `Theme`, the same
object, and no caller had to change.

What importing this module loads of imscribe, exactly
(`tests/test_typeset_closure.py` holds it): `imscribe.primitives`, for `Scaled`,
the pixel conversion `Theme.build` sizes everything with, and the `Face` enum.
That module imports nothing of imscribe, so **importing this one, and building
a theme with `Theme.build`, loads no module of the reference layout core**
(what is left of the Python core, kept for the SVG litmus renderer). Until
2026-10-11 it loaded two at import (`imscribe.units`, `imscribe.fontmetrics`,
where those names were defined) and three more at the first `Theme.build`
(`nodes`, `pack`, `badness`), because a `BlockStyle` held its leading as the
core's `InterlineSkip`.

**A block's leading is a number now: `BlockStyle.leading`**, the
baseline-to-baseline distance in scaled points. That is what a caller that
sets text through imtypeset reads. Two things here still reach the reference
core, **when called and not when imported**:

- **`BlockStyle.interline`**, a property, answers the triple §679 consults
  (`imscribe.pack.InterlineSkip`), built from `leading` and the block's size
  by `imscribe.style.interline_skip`. Only the reference compositor
  (`imscribe.ui.composition`) reads it, and that has loaded `imscribe.style`
  already. It is the value `Theme.build` used to store, field for field
  (`tests/test_style.py` holds it).
- **`Theme.at_pixel_height` with no resolver, while the library has no
  fonts** (`imscribe.typesetter.ready()` is false), asks
  `imscribe.style.fontlib_metrics`, which opens a font file through
  `imscribe.fontlib`. Once `typesetter.load_fonts()` has succeeded the
  library answers and nothing of the reference core is loaded
  (`imscribe.typeset_metrics` has the order a host follows and why a theme
  sized early is not refused). `Theme.build` opens nothing.

`Strut.applied_to` takes an `imscribe.nodes.Box` and needs the class only as an
annotation. `font_key` and `parse_font_key` write and read the opaque string
`imscribe.nodes` calls a `FontKey`, which is a `str`.

## The type scale, and the decisions inside it

**A modular scale of 1.25 (a major third) from a 16 px body.** Sizes are 16,
20, 25 and 31.25 px for body, h3, h2 and h1. A ratio rather than a hand-picked
set because the relationships are then visible in the output -- a reader cannot
say why an arbitrary 22 px heading looks wrong, only that it does -- and 1.25
rather than something larger because four steps of 1.5 would put h1 at 54 px in
a document whose longest heading is a sentence.

**Below h3 the scale stops and the face takes over.** The next step down the
scale is ratio to the power zero, which is the body size, and h4 takes it: a
level-four heading is body-size bold. The steps after that are 12.8 and 10.24
px -- smaller than the text they would be heading -- so h5 and h6 do not take
them. They stay at the body size and are told apart the way a book tells apart
its lowest heads, by face: h4 bold, h5 bold italic, h6 italic. The air around
them continues the arithmetic the first three already follow, a tenth of an em
less above and a twentieth less below per level, so h4 to h6 sit under 0.7, 0.6
and 0.5 em and over 0.25, 0.2 and 0.15.

Before this, levels four to six were set as level three. That kept them
visibly headings, and it erased the difference between a section and its
sub-sub-section. The h6 is the weakest of the new three and in an all-monospace
theme it is weaker still: `Faces.mono()` has no italic, so there h6 differs
from a paragraph only by its spacing, its tighter leading and being ragged. That
is recorded rather than solved; a host that leans on six levels in monospace
gives h6 its own `BlockStyle`.

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
line of the item is broken to, so it is decided in `imscribe.markdown` before
anything has been packed, and moving it means the converter measures. One number
for every list in the document is also what makes a bullet list and an ordered
list line up with each other, which is worth something on its own.

**Three digits still overfull**, deliberately. "100." is 1.9478 em and would want
a 2.45 em gutter -- a sixth of the measure given over to margin on the chance
that a list runs past ninety-nine. `imscribe.ui` packs the marker with stretch-only
glue so the failure stays inside the gutter rather than hanging off the left edge
of the page, and that is the case this theme chooses to lose.

**Paragraph spacing, and no first-line indent.** Both exist to mark where one
paragraph ends and the next begins, and using both says it twice. Print sets
`\parindent` and no `\parskip`; screens with a wide measure read better with the
space. We take the space.

**Headings are ragged right, body text is justified.** Justification needs
enough words per line to hide the stretched spaces, and a three-word heading at
31 px has nowhere to hide them.

## What a host can change without writing a theme

Everything above is the *default*, and it is what `Theme.build()` with no
arguments returns, field for field, as it always has. A host embedding this in
an application whose own text is one monospace family set ragged cannot use
that default and should not have to construct ten `BlockStyle`s to say so.
`Theme.build` therefore takes the three decisions that differ between hosts:

- **`faces`** -- a `Faces` table: which `Face` each of the six *typographic*
  roles is set in. The default is the four Roboto weights and Inconsolata.
  `Faces.mono()` is every role in the monospace pair. Which faces count as
  monospace is the table's own `monospace` field, declared and not inferred.
- **the body size** -- `base_px`, an em size, as before. A host that has an
  ImGui font size has a pixel *height* instead, which is a different length
  (`imscribe.typeset_metrics.em_size_for_pixel_height`); `Theme.at_pixel_height` takes
  that and converts.
- **`align`** -- what the running text is set as: paragraphs, list items and
  quotes. Headings, code, rules and tables are ragged in every theme and do not
  follow it.

So the all-mono ragged theme at a host's size is one call:
`Theme.at_pixel_height(16.0, faces=Faces.mono(), align=Align.LEFT)`.

## Which size a theme expects, under Dear ImGui's scales

**Every length in a theme is in Dear ImGui's units**, the coordinates a
window and a cursor are in, and a view sets its text at exactly those
sizes. Two scales act on Dear ImGui's own text, and only one of them on a
theme's:

- **`io.display_framebuffer_scale`** (a Retina display: 2) is the library's
  business. A unit is that many framebuffer pixels; imtypeset rasterises and
  places at the framebuffer's size, as Dear ImGui does. Nothing to do.
- **`style.font_scale_main` and `style.font_scale_dpi`** (hello_imgui sets
  the second from the monitor on Windows and Linux: 1.25 at 125 %; it is 1
  on macOS) make Dear ImGui's own text larger IN UNITS. **A theme does not
  follow them**: the library leaves that scaling to the host
  (`imtypeset.h`, "DISPLAY DENSITY"), and so does this package. A theme
  built once at 16 stays 16 whatever they are.

So a host whose typeset text should stand as tall as its own labels gives
`at_pixel_height` the size Dear ImGui DRAWS its text at, not the base size,
and builds the theme again when that changes:

- inside a frame (after `imgui.new_frame()`), `imgui.get_font_size()`;
- between frames, where `get_font_size()` answers the base size alone,
  `style.font_size_base * style.font_scale_main * style.font_scale_dpi`,
  rounded as Dear ImGui rounds it (in single precision, to the nearest whole
  unit, half up: `GetRoundedFontSize`);
- **before Dear ImGui's first frame `get_font_size()` answers 0**, which no
  theme can be built at: `build` and `at_pixel_height` refuse a size that is
  not a positive number with a `ValueError` here, rather than a view failing
  on it later.

Measured headless on Dear ImGui 1.92.9 with the base at 16 (R2-SCALE): the
drawn size is 18, 20 and 24 at a dpi scale of 1.1, 1.25 and 1.5, and 16
between frames at each; a view on `Theme.build()` sets its prose at a
pixel height of 18.75 at all four.

What that call does **not** do is make ragged text cheap to break.
`imscribe.linebreak`'s total-fit breaker was measured at 80 to 300 times its
justified cost on ragged material (`scripts/bench_reflow.py --ragged`); how a
ragged block is broken is the caller's `LineBreakParams`, not this module's.

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
because that is what `imscribe.linebreak` justifies with.

Deliberately out of scope here: colour (nothing in the node model carries one
yet; `imscribe.ui.palette` is where a view's inks are) and per-block background
fills.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from imscribe.primitives import DEFAULT_PX_PER_INCH, Face, Scaled, sp_from_px

if TYPE_CHECKING:  # pragma: no cover - annotations only; see the module docstring
    from imscribe.fontmetrics import FontMetrics
    from imscribe.nodes import Box, FontKey
    from imscribe.pack import InterlineSkip
    from imscribe.style import MetricsResolver

__all__ = [
    "Align",
    "BODY_SIZE_PX",
    "BlockKind",
    "BlockStyle",
    "DEFAULT_FACES",
    "Emphasis",
    "Faces",
    "FontSpec",
    "MARKER_GAP_EM",
    "QUOTE_INDENT_EM",
    "STRUT_HEIGHT_FRACTION",
    "WIDEST_MARKER_EM",
    "Spacing",
    "Strut",
    "Theme",
    "font_key",
    "parse_font_key",
]

# The modular scale's ratio, and the body size it is measured from. Together they
# generate every prose size in the document; nothing else picks a size by hand.
TYPE_SCALE_RATIO = 1.25
BODY_SIZE_PX = 16.0

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
    HEADING_4 = enum.auto()
    HEADING_5 = enum.auto()
    HEADING_6 = enum.auto()
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
class Faces:
    """
    Which `Face` each typographic role of a theme is set in.

    Two vocabularies meet here and it is worth keeping them apart. A `Face` is
    a role *a font file is registered under* -- `imscribe.fontlib` maps each to a
    file. The fields below are roles *in a document*: the running text, its bold,
    its italic, a code span. The default maps one onto the other by name, which
    is why nobody needed this table while there was one theme. A theme that sets
    everything in one monospace family maps four document roles onto two faces,
    and that is not expressible by renaming files.

    `code_bold` is what bold comes to on a monospace base. It defaults to
    `Face.CODE_BOLD`, which has no file of its own in the fonts imgui-bundle
    ships and is backed by the bold *prose* file until a host registers a bold
    monospace (`imscribe.fontlib.register_font`). So with nothing registered a
    bold run in an all-mono theme is set in Roboto Bold -- proportional, and it
    breaks the columns. That is the same glyphs `Theme.face_for` produced for
    that case before this table existed, it is not hidden, and the remedy is the
    one registration; `imscribe.fontlib.backing_face(Face.CODE_BOLD)` tells a
    host which state it is in.

    There is no monospace italic in either vocabulary, so `Faces.mono()` sets
    italic upright. An emphasised run in an all-mono theme is then
    indistinguishable from the text around it unless the host colours it, which
    is what terminals do and is `imscribe.spans`' business rather than a face's.

    `monospace` is the set of faces this table **declares** to be a monospace
    base, and `Theme.face_for` asks nothing else. It is a field and not
    something worked out from the six above because it used to be worked out --
    as `{code, code_bold}` -- and that was wrong whenever a host put a
    proportional face in either role: `Faces(code=Face.PROSE)`, a table with no
    second family, made the *paragraph* a monospace base and its italic came
    out upright (measured; `tests/test_style.py`). Which role a face is assigned
    to says where it is used, not what it is. The default is `Face.CODE` and
    `Face.CODE_BOLD`, the two roles a monospace file is registered under,
    whatever the other fields say; `Faces.mono(regular, bold)` declares the
    pair it is given. Nothing here opens a font file to find out, so a host that
    registers a proportional file under `Face.CODE`, or a monospace one under
    `Face.PROSE` without going through `mono`, says so with this field.
    """

    regular: Face = Face.PROSE
    bold: Face = Face.PROSE_BOLD
    italic: Face = Face.PROSE_ITALIC
    bold_italic: Face = Face.PROSE_BOLD_ITALIC
    code: Face = Face.CODE
    code_bold: Face = Face.CODE_BOLD
    monospace: frozenset[Face] = frozenset((Face.CODE, Face.CODE_BOLD))

    @classmethod
    def mono(cls, regular: Face = Face.CODE, bold: Face = Face.CODE_BOLD) -> Faces:
        """
        Every role in one monospace pair: a regular weight and a bold one.

        Pass `bold=Face.CODE` for a host with no bold monospace that would
        rather lose the weight than the columns.
        """
        return cls(
            regular=regular,
            bold=bold,
            italic=regular,
            bold_italic=bold,
            code=regular,
            code_bold=bold,
            monospace=frozenset((regular, bold)),
        )


DEFAULT_FACES = Faces()
"""
The table a theme gets by naming none: four Roboto weights and Inconsolata.

A module constant for the reason `imscribe.backends.imgui_draw.DEFAULT_PALETTE`
is one: a default argument built in a signature is built once and shared, and
naming it says the sharing is deliberate.
"""


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
        The opaque string `imscribe.nodes.CharNode` carries.
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

    `leading` is the distance from one baseline of this block to the next, in
    scaled points. It belongs to the block rather than to the document because
    a heading wants tighter leading than a paragraph. It is a plain number and
    not the triple §679 consults (which it was, as `interline`, until
    2026-10-11) so that a style can be made without the reference core's
    classes: see the module docstring. `interline` is still answered, from it.
    """

    font: FontSpec
    leading: Scaled
    align: Align = Align.JUSTIFY
    space_above: Scaled = 0
    space_below: Scaled = 0
    left_indent: Scaled = 0
    first_line_indent: Scaled = 0

    @property
    def strut(self) -> Strut:
        """
        The strut every line of this block is set on.

        Derived from `leading` rather than stored beside it, because the two
        have to agree -- a strut that is not the block's own leading is the one
        way to get interline glue that is not zero -- and a field would let a
        caller set them apart.
        """
        return Strut.filling(self.leading)

    @property
    def interline(self) -> InterlineSkip:
        """
        The triple §679 consults between the lines of this block, for the reference core.

        `\\baselineskip` is `leading`; `\\lineskip`, the fallback when a tall
        line would otherwise collide with the one above, is a tenth of the
        block's size; `\\lineskiplimit` is zero ("never let the boxes touch",
        TeX's plain default). Rigid, all three.

        This is the one place a style reaches the reference layout core, and
        it does so when asked: `imscribe.style.interline_skip` makes the value
        (and keeps one per leading and size, so the compositor asking once
        per line is a dictionary read). Nothing that sets text through
        imtypeset asks.
        """
        from imscribe.style import interline_skip

        return interline_skip(self.leading, self.font.size)


def _px(pixels: float, px_per_inch: float) -> Scaled:
    """
    A length given in device pixels, in scaled points.
    """
    return sp_from_px(pixels, px_per_inch)


# The size `Theme.at_pixel_height` asks a resolver for when all it wants is a
# ratio. Any size would do; a large one keeps a resolver that rounds honest.
_PROBE_SIZE: Scaled = sp_from_px(1024.0)


def _positive(size: float, name: str) -> float:
    """
    `size` if it is a finite number above zero; a `ValueError` naming `name` if not.

    A theme at 0 was accepted and failed later, inside the view that read
    it, as a `ZeroDivisionError` (`TypesetView(source,
    theme=Theme.at_pixel_height(imgui.get_font_size()))` before Dear ImGui's
    first frame; measured 2026-10-14, R2-SCALE).
    """
    try:
        value = float(size)
    except (TypeError, ValueError):
        value = math.nan
    if math.isfinite(value) and value > 0:
        return size
    hint = " (Dear ImGui's get_font_size() is 0 before its first frame)" if value == 0 else ""
    raise ValueError(f"{name} is {size!r}: a theme's size is a positive number of pixels{hint}")


def _widest_marker_em(metrics: FontMetrics) -> float:
    """
    The widest two-digit list marker in a face, in ems, rounded up to a tenth.

    The module docstring's argument for `WIDEST_MARKER_EM`, as arithmetic rather
    than as a constant: two of the widest digit and a period. Rounded *up*, and
    to a tenth, because that is how 1.3862 em became the constant's 1.4 -- so
    for the face the constant was measured on this returns the constant.
    """
    if metrics.em <= 0:
        return WIDEST_MARKER_EM
    digit = max(metrics.advance(ord(character)) for character in "0123456789")
    marker = (2 * digit + metrics.advance(ord("."))) / metrics.em
    # The small subtraction is for a marker that is exactly a tenth already --
    # 1.5 em in a half-em monospace -- which float division can leave a hair
    # above the tenth and `ceil` would then round to the next one.
    return math.ceil(marker * 10.0 - 1e-6) / 10.0


def _leading(size: Scaled, ratio: float) -> Scaled:
    """
    The baseline-to-baseline distance for one size, rounded once.
    """
    return round(size * ratio)


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
    # Which face each typographic role is set in. `face_for` reads it; a theme
    # constructed by hand without one gets the default table, which is what
    # every theme had before the field existed.
    faces: Faces = DEFAULT_FACES
    # The size of a code span beside the size of the block it is in: the
    # block's size times `inline_code_scale` (0 is 1, the library's own
    # convention for a run's scale), plus `inline_code_step` scaled points.
    # Both at their defaults is a span at its block's size, which is what
    # every theme gave before the fields existed. `inline_code_run_scale` has
    # the arithmetic and says why there are two numbers.
    inline_code_scale: float = 0.0
    inline_code_step: Scaled = 0
    # The space below the LAST item of a list, in scaled points, in place of
    # the item style's own `space_below`; `None` leaves the item's, which is
    # what every theme gave before the field existed (2026-10-12; pptmstr's
    # P26). The gap between two blocks is the upper one's space below plus
    # the lower one's space above, and a list item's space below is the gap
    # between two ITEMS (0.2 of the body), so by default whatever follows a
    # list sits that close under it where a paragraph would have left its own
    # 0.55. `dataclasses.replace(theme, space_after_list=theme.style(
    # BlockKind.PARAGRAPH).space_below)` is "a paragraph's gap after a list".
    # It is the outermost list's last item that takes it: a nested list
    # ending inside an item is followed at the item gap, as before.
    # `imscribe.typeset_markdown` reads it (`_Reader._end_list`).
    space_after_list: Scaled | None = None

    def __post_init__(self) -> None:
        """
        Refuse an inline-code size no block could be set at, where the theme is made.

        A theme is a host's input, and the two fields are read while a
        document is being parsed, which for a stream is inside a draw. So a
        value that cannot be a size is an error here, at `Theme(...)` or
        `dataclasses.replace(theme, ...)`, and never there. With both fields
        at their defaults nothing is looked at. `space_after_list` is held
        the same way: `None`, or whole scaled points that are not negative.
        """
        after = self.space_after_list
        if after is not None:
            if isinstance(after, bool) or not isinstance(after, int):
                raise TypeError(
                    "space_after_list is whole scaled points (an int) or None, "
                    f"not {type(after).__name__}"
                )
            if after < 0:
                raise ValueError(f"space_after_list is {after!r}: it is 0 or more scaled points")
        scale, step = self.inline_code_scale, self.inline_code_step
        if scale == 0 and step == 0 and type(scale) is float and type(step) is int:
            return
        if isinstance(scale, bool) or not isinstance(scale, int | float):
            raise TypeError(f"inline_code_scale is a number (0 for 1), not {type(scale).__name__}")
        if isinstance(step, bool) or not isinstance(step, int):
            raise TypeError(
                f"inline_code_step is whole scaled points (an int), not {type(step).__name__}"
            )
        if not math.isfinite(scale) or scale < 0:
            raise ValueError(
                f"inline_code_scale is {scale!r}: it is 0 (for 1) or a positive number"
            )
        for kind, style in self.blocks.items():
            if style.font.size * (scale or 1.0) + step <= 0:
                raise ValueError(
                    f"inline_code_scale {scale!r} and inline_code_step {step!r} leave a code "
                    f"span in a {kind.name} block of size {style.font.size} no size at all"
                )

    @classmethod
    def build(
        cls,
        base_px: float = BODY_SIZE_PX,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        *,
        spacing: Spacing = Spacing.EXTRA_SPACE_ONLY,
        faces: Faces = DEFAULT_FACES,
        align: Align = Align.JUSTIFY,
        widest_marker_em: float = WIDEST_MARKER_EM,
    ) -> Theme:
        """
        A look generated from one body size and one ratio; the default one by default.

        With no arguments this is the theme the module docstring argues for, and
        `tests/test_style.py` holds it equal, field for field, to what this
        function returned before it took `faces` and `align`.

        `base_px` is the body's **em** size in device pixels. A host holding an
        ImGui font size has a pixel height instead; use `at_pixel_height`.

        `faces` says which face each role is set in (`Faces`). Headings take its
        `bold`, running text its `regular`, a fenced block its `code`.

        `align` is how the running text is set -- paragraphs, both kinds of list
        item, and quotes. `Align.LEFT` is ragged right. It does not reach
        headings, code, rules or tables, which are ragged in every theme for the
        reasons the module docstring gives for headings and the comment below
        gives for code.

        `widest_marker_em` is the widest list marker the gutter must hold, in
        ems of the body. The default is a measurement of Roboto and is wrong for
        another family: "10." is 1.386 em in Roboto, 1.5 em in Inconsolata and
        about 1.8 em in the common monospace faces whose advance is 0.6 em. This
        function opens no font and so cannot measure; `at_pixel_height` does,
        and a caller of `build` with its own `faces` passes the number.

        `base_px` is in Dear ImGui's units and is not multiplied by its font
        scales (the module docstring, "Which size a theme expects"). A size
        that is not a positive number, or one too small to be a scaled point,
        is a `ValueError`.
        """
        r = TYPE_SCALE_RATIO
        body = _px(_positive(base_px, "base_px"), px_per_inch)
        if body <= 0:
            raise ValueError(f"base_px is {base_px!r}: too small to set text at")
        h3 = _px(base_px * r, px_per_inch)
        h2 = _px(base_px * r * r, px_per_inch)
        h1 = _px(base_px * r * r * r, px_per_inch)

        def heading(
            size: Scaled, above: float, below: float, face: Face = faces.bold
        ) -> BlockStyle:
            return BlockStyle(
                font=FontSpec(face, size),
                # Large type wants proportionally less leading: what the eye
                # tracks is the ratio of the gap to the x-height, and the
                # x-height has grown with the size while the gap need not.
                leading=_leading(size, 1.15),
                align=Align.LEFT,
                space_above=round(size * above),
                space_below=round(size * below),
            )

        body_leading = _leading(body, 1.35)
        styles: dict[BlockKind, BlockStyle] = {
            BlockKind.HEADING_1: heading(h1, 1.0, 0.4),
            BlockKind.HEADING_2: heading(h2, 0.9, 0.35),
            BlockKind.HEADING_3: heading(h3, 0.8, 0.3),
            # The scale's next step is the body size, and below that it would
            # go under the text it heads; see the module docstring. From here
            # down the levels are told apart by face and by a little less air.
            BlockKind.HEADING_4: heading(body, 0.7, 0.25),
            BlockKind.HEADING_5: heading(body, 0.6, 0.2, faces.bold_italic),
            BlockKind.HEADING_6: heading(body, 0.5, 0.15, faces.italic),
            BlockKind.PARAGRAPH: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=align,
                space_below=round(body * 0.55),
            ),
            BlockKind.BULLET_ITEM: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=align,
                space_below=round(body * 0.2),
            ),
            BlockKind.ORDERED_ITEM: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=align,
                space_below=round(body * 0.2),
            ),
            BlockKind.QUOTE: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=align,
                space_above=round(body * 0.5),
                space_below=round(body * 0.5),
            ),
            BlockKind.CODE: BlockStyle(
                # Code is not line-broken: a fenced block's line endings are
                # content, so every line is set ragged and long lines overflow
                # rather than wrap somewhere the author did not choose.
                font=FontSpec(faces.code, body),
                leading=_leading(body, 1.25),
                align=Align.LEFT,
                space_above=round(body * 0.6),
                space_below=round(body * 0.6),
                left_indent=round(body * 1.0),
            ),
            BlockKind.RULE: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=Align.LEFT,
                space_above=body,
                space_below=body,
            ),
            BlockKind.TABLE: BlockStyle(
                font=FontSpec(faces.regular, body),
                leading=body_leading,
                align=Align.LEFT,
                space_above=round(body * 0.7),
                space_below=round(body * 0.7),
            ),
        }
        return cls(
            blocks=styles,
            px_per_inch=px_per_inch,
            marker_gap=round(body * MARKER_GAP_EM),
            list_indent=round(body * (widest_marker_em + MARKER_GAP_EM)),
            quote_indent=round(body * QUOTE_INDENT_EM),
            rule_thickness=max(1, round(body * 0.06)),
            quote_rule_thickness=max(1, round(body * 0.15)),
            cell_padding=round(body * 0.5),
            table_rule_thickness=max(1, round(body * 0.06)),
            spacing=spacing,
            faces=faces,
        )

    @classmethod
    def at_pixel_height(
        cls,
        height_px: float,
        px_per_inch: float = DEFAULT_PX_PER_INCH,
        *,
        spacing: Spacing = Spacing.EXTRA_SPACE_ONLY,
        faces: Faces = DEFAULT_FACES,
        align: Align = Align.JUSTIFY,
        metrics: MetricsResolver | None = None,
    ) -> Theme:
        """
        `build`, sized so the running text comes out `height_px` tall as ImGui means it.

        For a host whose own UI font is "16": pass 16 and the body is drawn from
        the same 16 px raster the host's labels are, rather than at an em of 16
        that ImGui would bake at 18.75. The two lengths and the conversion are
        `imscribe.typeset_metrics.em_size_for_pixel_height`'s subject; this applies it to
        `faces.regular`.

        **Only the running text's face lands on the height asked for.** Every
        block is sized in ems of the body, and a face's pixel height per em is
        its own, so in a theme mixing families the code face comes out a
        different height at the same em -- which is the module docstring's
        "code is set at the body size" decision and not something this undoes.
        In an all-mono theme there is one family and everything at body size
        matches.

        It also measures what `build` cannot: the gutter is sized from the
        widest two-digit marker *in `faces.regular`*, rounded up to a tenth of an
        em, instead of from Roboto's. For the default faces that is the same 1.4
        em `build` uses, so `at_pixel_height` and `build` agree about everything
        but the size.

        `metrics` is the resolver that measures the face, and defaults to
        `imscribe.typeset_metrics.face_metrics`: **imtypeset, once
        `imscribe.typesetter.load_fonts()` has succeeded** (no font file is
        opened here and no kerning read), and the old reader
        `imscribe.style.fontlib_metrics` before that and without the library.
        The two give the same theme; the first is some hundreds of times
        cheaper, so a host sizes its themes after it loads its fonts. It is
        asked for `faces.regular` once, at a probe size; only ratios are
        read: the ascent, the descent, the em, and the advances of the ten
        digits and the period.

        `height_px` is the size Dear ImGui DRAWS its text at, in its units:
        `imgui.get_font_size()` inside a frame, which includes
        `style.font_scale_main` and `style.font_scale_dpi` (the module
        docstring, "Which size a theme expects"). A height that is not a
        positive number is a `ValueError`, before any face is measured:
        `get_font_size()` answers 0 before Dear ImGui's first frame.
        """
        _positive(height_px, "height_px")
        if metrics is None:
            # Read from there at the call, so that a caller who replaces the
            # name (or `imscribe.style.fontlib_metrics`, which it falls back
            # to) is still the one asked.
            from imscribe import typeset_metrics

            metrics = typeset_metrics.face_metrics
        probe = metrics(font_key(faces.regular, _PROBE_SIZE))
        extent = probe.ascent + probe.descent
        em_px = height_px * probe.em / extent if extent > 0 and probe.em > 0 else height_px
        return cls.build(
            em_px,
            px_per_inch,
            spacing=spacing,
            faces=faces,
            align=align,
            widest_marker_em=_widest_marker_em(probe),
        )

    def style(self, kind: BlockKind) -> BlockStyle:
        """
        The parameters one block kind is set with.
        """
        return self.blocks[kind]

    def face_for(self, kind: BlockKind, emphasis: Emphasis) -> Face:
        """
        Which face a run of text in this context is set in, from `self.faces`.

        The block's own face supplies the baseline: its family, and its weight.
        So italic inside a heading is bold-italic rather than a sudden drop to
        the regular weight -- Roboto ships all four as real faces, which is why
        this is a lookup and not the colour shift pptmstr has to fall back on
        (`docs/decisions.md`).

        **On a proportional base, inline code wins over everything** and is set
        in `faces.code` whatever the emphasis around it: a code span inside a
        bold heading is the regular monospace. That is unchanged.

        **On a monospace base the family is kept and only the weight moves.**
        This is the case that used to be wrong. The function answered from the
        four prose faces for anything that was not a code span, consulting the
        block's face only for its weight -- so a block whose style said
        `Face.CODE` set its text in Roboto, and bold on it was Roboto Bold.
        Nothing in the default theme reaches that: its only monospace block is
        the fenced one, whose text is not emphasised. A theme that sets
        *everything* in monospace reached nothing else. Now a base in
        `faces.monospace` answers `faces.code_bold` when the run or the block is
        bold and `faces.code` otherwise; italic has no monospace face and stays
        upright; and a code span keeps the weight of the block it is in, because
        in a one-family theme there is no second family for it to switch to.

        What makes a base monospace is `faces.monospace`, which the table
        declares. It is not whether the base happens to be the face assigned to
        `faces.code`: see `Faces` for the italic that inference cost a table
        with a proportional face in that role.
        """
        faces = self.faces
        base = self.style(kind).font.face
        if base in faces.monospace:
            return faces.code_bold if emphasis.bold or base is faces.code_bold else faces.code
        if emphasis.code:
            return faces.code
        bold = emphasis.bold or base in (faces.bold, faces.bold_italic)
        italic = emphasis.italic or base in (faces.italic, faces.bold_italic)
        if bold and italic:
            return faces.bold_italic
        if bold:
            return faces.bold
        if italic:
            return faces.italic
        return faces.regular

    def font_for(self, kind: BlockKind, emphasis: Emphasis) -> FontSpec:
        """
        `face_for` at the block's own size.

        The block's own size whatever `inline_code_scale` and
        `inline_code_step` say: those are read by `inline_code_run_scale`,
        which is what a caller setting text through imtypeset asks. The
        reference core, which asks here, sets a code span at its block's size.
        """
        return FontSpec(self.face_for(kind, emphasis), self.style(kind).font.size)

    def inline_code_run_scale(self, kind: BlockKind) -> float:
        """
        What a code span in a `kind` block is given as its run's scale: 0.0 for "the block's size".

        The library reads a run's scale as a multiple of the size of the
        block the run is in, and 0 as 1 (`imtypeset.h`, `ImTypesetRun::Scale`:
        "Size, as a multiple of the paragraph's. 0 is 1."; measured, not
        only read: `tests/test_reader_options.py`). So this is

            (size * (inline_code_scale or 1) + inline_code_step) / size

        with `size` the block's own, and exactly `0.0` when both fields are
        at their defaults, so that a theme which says nothing describes its
        code spans as it always did.

        **Why two numbers.** One is not enough for either thing a host wants.
        A host that wants a code span to stand as TALL as the prose it is in
        needs a ratio: a face's pixel height per em is its own (Inconsolata is
        about 14.3 px tall at the em at which Roboto is 16), so the span's em
        is the block's times `prose height per em / code height per em`,
        whatever the block's size. A host that gives inline code a size of
        its own, some pixels more or less than the prose, needs a difference,
        and a difference is not a ratio: two pixels less is a different
        fraction of a paragraph than of a heading. Together they are linear
        in the block's size, which is all either case needs. For a code span
        `d` pixels taller than its block's text, with `p` and `c` the two
        faces' (ascent + descent) / em: `inline_code_scale = p / c` and
        `inline_code_step = sp_from_px(d / c)`.

        **On a monospace base the answer is 0.0**, whatever the fields say: a
        code span in a block whose own face is one of `faces.monospace` is
        that block's face (`face_for`), there is no second family for it to
        be sized against, and it is set at the block's size.
        """
        scale, step = self.inline_code_scale, self.inline_code_step
        if not scale and not step:
            return 0.0
        font = self.style(kind).font
        if font.face in self.faces.monospace:
            return 0.0
        return (font.size * (scale or 1.0) + step) / font.size

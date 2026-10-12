r"""
Where a theme meets the layout core: the adapters that measure, and the space between words.

**The look itself -- `Theme`, `BlockStyle`, `Faces`, `BlockKind`, `Emphasis`,
`Align`, `Spacing`, `FontSpec`, `Strut` and the type scale's constants -- is
`imscribe.theme`'s since 2026-10-11**, and that module's docstring has the
argument for every number in it. Every one of those names is imported here
and is the same object under either path (`tests/test_typeset_closure.py`
holds the identity), so `from imscribe.style import Theme` means what it always
did. They were split because this half needs the layout core's types at
import and that half does not: a module that sets its text through imtypeset
takes a theme from `imscribe.theme` and loads none of `imscribe.nodes`,
`imscribe.pack` or `imscribe.badness` by doing so.

What is left here is where the two halves of the project meet. `imscribe.nodes`
keeps a `FontKey` opaque so the layout core never learns what a font is, and
`imscribe.fontmetrics` hands out faces resolved at a size. The encoding between
them is `imscribe.theme`'s `font_key`/`parse_font_key`; `fontlib_metrics` here
turns a key into something measurable, and `char_measure` is the adapter
`hpack` takes: it is the one place floats from the metrics layer become the
scaled-point integers everything downstream adds up.

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

Deliberately out of scope here: the full `\sfcode` table -- only the four
classes §1034 distinguishes are implemented, not an assignable code per
character.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import TypeAlias

from imscribe.fontmetrics import Face as Face
from imscribe.fontmetrics import FontMetrics
from imscribe.nodes import Box as Box
from imscribe.nodes import CharNode, FontKey, GlueSpec
from imscribe.pack import CharDimens, CharMeasure
from imscribe.pack import InterlineSkip as InterlineSkip
from imscribe.theme import (
    BODY_SIZE_PX,
    DEFAULT_FACES,
    MARKER_GAP_EM,
    QUOTE_INDENT_EM,
    STRUT_HEIGHT_FRACTION,
    WIDEST_MARKER_EM,
    Align,
    BlockKind,
    BlockStyle,
    Emphasis,
    Faces,
    FontSpec,
    Spacing,
    Strut,
    Theme,
    font_key,
    parse_font_key,
)
from imscribe.theme import (
    TYPE_SCALE_RATIO as TYPE_SCALE_RATIO,
)
from imscribe.units import DEFAULT_PX_PER_INCH as DEFAULT_PX_PER_INCH
from imscribe.units import Scaled
from imscribe.units import sp_from_px as sp_from_px

# The imports written `X as X` above are names this module no longer uses and
# still has. They were its own imports while `Theme` was defined here, they
# were never in `__all__`, and code reads them from here all the same
# (`from imscribe.style import Face` in `tests/test_page_math.py`,
# `TYPE_SCALE_RATIO` in `imscribe.ui.specimen`). The `as` marks a re-export.

__all__ = [
    "Align",
    "BODY_SIZE_PX",
    "BlockKind",
    "BlockStyle",
    "DEFAULT_FACES",
    "Emphasis",
    "Faces",
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
    "interline_skip",
    "interword_glue",
    "parse_font_key",
    "space_factor_after",
]

# TeX's \fontdimen 3, 4 and 7 as fractions of \fontdimen 2, which is what cmr10's
# own values come to. See the module docstring.
SPACE_STRETCH_FRACTION = 0.5
SPACE_SHRINK_FRACTION = 1.0 / 3.0
EXTRA_SPACE_FRACTION = 1.0 / 3.0

# §1034's four space-factor classes. The neutral one is the implicit default and
# is public because `imscribe.markdown` has to start a run of text at it.
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

MetricsResolver: TypeAlias = Callable[[FontKey], FontMetrics]
"""
How a key becomes measurable.

Injected rather than imported so that a test can supply a fake with round
numbers and never open a font: `imscribe.markdown`'s tests compute expected widths
by hand, which is only possible if the widths are chosen rather than measured.
`fontlib_metrics` is the real one.
"""


def fontlib_metrics(key: FontKey) -> FontMetrics:
    """
    The production resolver: a key, a real font file, real advances and kerns.

    The size in the key is in scaled points and is handed to `imscribe.fontlib` as
    the em size, so every length that comes back is already in scaled points --
    as a float, because a metric is a ratio of the em and rounding is this
    module's decision, made once in `char_measure`.
    """
    from imscribe import fontlib

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


@lru_cache(maxsize=256)
def interline_skip(leading: Scaled, size: Scaled) -> InterlineSkip:
    """
    The interline triple for a block: a baseline distance, and a floor under it.

    What `BlockStyle.interline` answers. `imscribe.theme` held this triple in
    every style until 2026-10-11 and built it in `Theme.build`; a style holds
    the one number `leading` now, and the triple is made here, where the
    layout core's classes already are, when the compositor asks for it.

    `lineskip` is the fallback §679 uses when a tall line would otherwise collide
    with the one above, a tenth of the block's size; `lineskiplimit` of zero
    means "never let the boxes touch", which is TeX's plain default and the
    only value with an obvious meaning.

    Kept per `(leading, size)`: the compositor asks once per line, a theme
    has a handful of distinct answers, and the value is frozen.
    """
    return InterlineSkip(
        baselineskip=GlueSpec(width=leading),
        lineskip=GlueSpec(width=round(size * 0.1)),
        lineskiplimit=0,
    )


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

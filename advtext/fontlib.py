r"""
The only module in this project that imports fontTools, and the only one that opens
a font file to read it.

**fontTools is imported when a font is first opened, not when this module is.**
The three functions that need it -- `_face_data`, `_FaceData.glyph_bounds` and
`imgui_font_file` -- import it themselves. A host that imports `advtext` to find
out what is in it, or that only ever lays out with its own `MetricsResolver`,
therefore pays for no fontTools at all, and `tests/test_fonts_setup.py` runs a
fresh interpreter to hold that. What cannot be deferred is fontTools for a face
that *is* measured: every face is a `TTFont`, prose as much as math. The math
face's own cost -- reading its `MATH` table, minting codepoints, and
`imgui_font_file` writing a patched copy -- is paid only when `Face.MATH` is
asked for, which nothing does until mathematics is set.

## The files are a registry a host can write to, and it is `advtext.fontfiles`'

Which file backs which role (`font_file`, `backing_face`, `font_directory`),
a host's own file for a role (`register_font`, `unregister_font`,
`registered_fonts`), `on_registry_change` and `MissingFontError` are defined
in `advtext.fontfiles` since 2026-10-12 and imported here: the same objects
under either path, and still names of this module. That module's docstring
has the registry's rules. They moved because finding a file needs no
fontTools and none of the reference core, and the typeset layer finds files.

**Registration must precede building.** `register_font` clears every cache this
module holds (this module is the registry's first listener), so the next
measurement reads the new file. It cannot reach what
was already made from the old one: a document's kerns are baked into its
material, `advtext.style.char_measure` memoises widths in a closure this module
never sees, and a layout cache is keyed by content and not by font file. A host
registers its fonts once, at start-up, before the first `Theme` measures
anything; one that re-registers later rebuilds its documents and its measure.

`docs/decisions.md` records why metrics come from here rather than from ImGui: ImGui's
baked advances are already pixel-rounded, so measuring through it rounds twice and the
error accumulates along a line; its `GPOS` kerning is not exposed at all; and its
`MATH` table access does not exist. Reading the font directly also means layout runs
with no display, no GL context and no ImGui frame, which in this environment is the
difference between a testable system and an untestable one.

Fonts are resolved by importing `imgui_bundle` and walking from its `__file__`, never
by a hard-coded path. The one hard-coded path in this project is the `PY` line in the
Makefile, which is where that seam belongs -- a venv under somebody's home directory
is not a fact about this code.

Everything here is cached. Opening a `TTFont` costs milliseconds and a paragraph asks
for thousands of advances, so faces, kern tables and `MATH` data are loaded once per
process and every per-glyph answer is memoised on the face.

**A face stays lazy, and its file is closed before `_face_data` returns.** Those two
look contradictory and are not, which is why the reasoning is here rather than in a
comment -- the next reader will otherwise "fix" one of them.

Leaving the file open is not an option. This cache lives for the life of the process,
so an open descriptor is one held forever and a `ResourceWarning` at interpreter
shutdown for every face touched. Those warnings do not fail the suite only because
they fire after pytest has stopped converting warnings to errors; `pyproject.toml`
sets `filterwarnings = ["error"]`, so anything that surfaces one *during* a test
becomes a failure pointing at whatever test happened to trigger the open. Closing at
exit instead would trade that for an object whose behaviour depends on whether the
interpreter has begun shutting down.

Closing early is safe because fontTools' laziness is not what it sounds like. A lazy
table still reads its *bytes* from the file when the table is first asked for; what it
defers is decompiling those bytes into objects. `font.getGlyphSet()` below asks for
the outline table, so by the time the file closes every glyph's data is already in
memory and only its parsing is outstanding. Verified rather than assumed: all 7058
glyphs of Roboto, Inconsolata and Latin Modern Math -- `glyf` and CFF, simple and
composite -- draw correctly after the close, and `tests/test_fontmetrics.py` pins
representatives of each.

`lazy=False` would also work and is measurably worse. Best of five per face on this
machine: opening a face costs 2.9ms lazily against 23.7ms eagerly for Roboto, and
9.0ms against 24.1ms for Latin Modern Math, for about 1.3MB and 2.0MB more resident
data. Eager decompilation repays that only across a great many glyphs -- drawing
Roboto's entire 1294 takes 84ms eagerly against 109ms lazily -- and a document draws
a hundred distinct glyphs, not a thousand. Almost every workload here is metrics-only
and never draws at all.

Deliberately out of scope: shaping, ligature substitution, `GSUB`, vertical writing,
variable-font axes, and the `ext_tag` extensible assembly that `docs/decisions.md`
rules out. Also out of scope: any notion of a layout unit. See
`advtext.fontmetrics` -- a metrics object returns floats in the unit its size was
given in, and rounds nothing.

---

## TeX's math font parameters, and where each one comes from

`docs/tex-notes.md` §10 lists TeX's family-2 ("sigma", σ) and family-3 ("xi", ξ)
`\fontdimen`s and says a plain TrueType font has none of them, so they must be
synthesised from fractions of the em. **That caveat does not apply to Latin Modern
Math**, which carries a real OpenType `MATH` table whose `MathConstants` map onto
TeX's parameters nearly one for one. The exceptions are listed, because "nearly" is
doing work.

| TeX | source | note |
|---|---|---|
| σ5 `math_x_height` | `OS/2.sxHeight` | not a `MATH` field; `AccentBaseHeight` differs |
| σ6 `math_quad` | 1 em | §547, "the size of one em"; drives `cur_mu = quad/18` |
| σ8 `num1` | `FractionNumeratorDisplayStyleShiftUp` | |
| σ9 `num2` | `FractionNumeratorShiftUp` | |
| σ10 `num3` | `StackTopShiftUp` | OpenType's "stack" is TeX's `\atop`: no rule |
| σ11 `denom1` | `FractionDenominatorDisplayStyleShiftDown` | |
| σ12 `denom2` | `FractionDenominatorShiftDown` | |
| σ13 `sup1` | `SuperscriptShiftUp` | **collapsed**, see below |
| σ14 `sup2` | `SuperscriptShiftUp` | |
| σ15 `sup3` | `SuperscriptShiftUpCramped` | |
| σ16 `sub1` | `SubscriptShiftDown` | **collapsed**, see below |
| σ17 `sub2` | `SubscriptShiftDown` | |
| σ18 `sup_drop` | `SuperscriptBaselineDropMax` | |
| σ19 `sub_drop` | `SubscriptBaselineDropMin` | |
| σ20 `delim1` | **synthesised** 2.4 em | no counterpart; cmsy10 has 2.39 em |
| σ21 `delim2` | **synthesised** 1.0 em | no counterpart; cmsy10 has 1.01 em |
| σ22 `axis_height` | `AxisHeight` | the one that makes a Σ look centred |
| ξ8 `default_rule_thickness` | `FractionRuleThickness` | |
| ξ9 `big_op_spacing1` | `UpperLimitGapMin` | |
| ξ10 `big_op_spacing2` | `LowerLimitGapMin` | |
| ξ11 `big_op_spacing3` | `UpperLimitBaselineRiseMin` | |
| ξ12 `big_op_spacing4` | `LowerLimitBaselineDropMin` | |
| ξ13 `big_op_spacing5` | **synthesised** 0.1 em | no counterpart; cmex10's value |
| -- `radical_rule_thickness` | `RadicalRuleThickness` | TeX: the surd's TFM height |
| -- `radical_vertical_gap` | `RadicalVerticalGap` | TeX: ξ8 + ξ8/4 |
| -- `radical_display_style_vertical_gap` | `RadicalDisplayStyleVerticalGap` | TeX: ξ8 + σ5/4 |

**The three radical rows have no TeX parameter because TeX computes them.**
`make_radical` (`docs/tex.web` line 14476) takes the rule's thickness from the
*height of the surd glyph* -- a TFM convention under which the glyph's baseline is
the underside of its own top stroke -- and the clearance from `default_rule_thickness`
and the x-height. An OpenType surd is an ordinary outline with no such convention
(Latin Modern Math's base `radical` happens to keep it, at height 40; its four
larger variants do not, and sit astride the axis instead), so the font states the
three numbers and `advtext.math.mlist` uses them and hangs the glyph from its ink
top. For this font they are exactly TeX's formulas evaluated -- 40, 40 + 40/4 = 50
and 40 + 431/4 = 148 -- which `tests/test_fontmetrics.py` pins, so following the
font here is following TeX. `RadicalExtraAscender` (also 40) is not read: TeX's
`overbar` puts one rule thickness of air above the rule, and that is what is done.

**The rule applied, stated once:** prefer the font's own field wherever OpenType has
one; synthesise only where it has none; and where OpenType folds two of TeX's
parameters into one field, use that field for both and say so here. Guessing a second
number from a fraction of the em when the font has stated a first one is how a
carefully drawn face ends up looking like nothing in particular.

**The two collapses, and what they cost.** TeX distinguishes a display-style
superscript (σ13) from a non-display one (σ14), and a lone subscript (σ16) from one
accompanied by a superscript (σ17). OpenType has a single `SuperscriptShiftUp` and a
single `SubscriptShiftDown`. Against cmsy10, `SuperscriptShiftUp` (0.363 em in Latin
Modern) matches σ14 (0.362892) rather than σ13 (0.412892), and `SubscriptShiftDown`
(0.247) matches σ17 (0.247217) rather than σ16 (0.15). So a display superscript sits
about 0.05 em lower than TeX would put it and a lone subscript about 0.1 em lower.
Neither is on the sigma litmus test's path -- `\sum_{i=1}^{n}` in display style goes
through `make_op`'s limits branch (§750, §751), which uses ξ9-ξ13 and no σ13-σ17 at
all. `MathParams` is a frozen dataclass, so a caller that wants TeX's split can
`dataclasses.replace` it rather than argue with this module.

**One mapping worth doubting, recorded rather than smoothed over.** ξ9/ξ10 are
minimum *gaps* and ξ11/ξ12 are minimum *baseline distances* (§701, and §751 computes
`shift_up = max(ξ11 - depth(upper), ξ9)`, which only makes sense on that reading).
The OpenType fields named `...GapMin` and `...BaselineRiseMin`/`...BaselineDropMin`
carry exactly those two meanings, so the mapping above is by definition. But Latin
Modern Math's *values* are the transpose of cmex10's: it has `UpperLimitGapMin` 0.200
and `UpperLimitBaselineRiseMin` 0.111 where cmex10 has ξ9 = 0.111 and ξ11 = 0.200.
We follow the OpenType definitions rather than the numeric coincidence. It changes
nothing for a limit box of small depth, since §751 takes a `max` either way, and it
is the reading to revisit first if stacked limits ever look wrong.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, TypeAlias, assert_never

# Which file backs which role, and a host's own files in front of the bundle's,
# are `advtext.fontfiles`' since 2026-10-12 and are imported back: the same
# functions and the same dictionaries under either path. They moved so that
# `advtext.typesetter.load_fonts` and a host's `register_font` find a file
# without loading this module, which reads fonts and is the reference core's.
from advtext.fontfiles import _FONT_FILES as _FONT_FILES
from advtext.fontfiles import _LISTENERS as _LISTENERS
from advtext.fontfiles import _REGISTERED as _REGISTERED
from advtext.fontfiles import _STAND_INS as _STAND_INS
from advtext.fontfiles import (
    MissingFontError,
    backing_face,
    font_directory,
    font_file,
    on_registry_change,
    register_font,
    registered_fonts,
    unregister_font,
)
from advtext.fontmetrics import (
    Face,
    FontMetrics,
    GlyphBBox,
    GlyphVariant,
    MathFontMetrics,
    MathParams,
)

__all__ = [
    "SYNTHETIC_FIRST",
    "SYNTHETIC_LAST",
    "GlyphSet",
    "MissingFontError",
    "backing_face",
    "em_size_for_pixel_height",
    "font_directory",
    "font_file",
    "glyph_name",
    "glyph_set",
    "imgui_font_file",
    "math_metrics",
    "metrics",
    "on_registry_change",
    "register_font",
    "registered_fonts",
    "synthetic_codepoints",
    "unregister_font",
]

GlyphSet: TypeAlias = Mapping[str, Any]
"""
What a pen draws from: glyph name to a drawable object, and `in` to test membership.

fontTools ships no type information, so the drawable is `Any` and this alias exists to
say what the mapping *is* rather than to constrain it. `_TTGlyphSet` really is a
`Mapping`, so the two operations named above are the honest contract.
"""

# Substituted for any codepoint the font does not map. Returning a zero advance
# instead would make missing text vanish silently, which reads as a layout bug
# rather than as a missing glyph.
_NOTDEF = ".notdef"

# Used only when OS/2 omits sxHeight (version 0 and 1 tables do). None of the
# bundled faces need it; it exists so a font swap degrades rather than crashes.
_X_HEIGHT_FALLBACK = 0.45


def _registry_changed() -> None:
    """
    Drop everything this module derived from a font file.

    What `advtext.fontfiles` calls, first of its listeners, whenever a role's
    file changes. All of it and not just the changed role's:
    `functools.cache` cannot evict by argument, and a stand-in role shares
    another role's file so the dependency is not one-to-one.
    """
    _face_data.cache_clear()
    _prose_metrics.cache_clear()
    math_metrics.cache_clear()
    imgui_font_file.cache_clear()


on_registry_change(_registry_changed)


# --------------------------------------------------------------------------------
# GPOS pair kerning
#
# The one GPOS feature read here. ImGui exposes no kerning at all, and the
# difference is visible on "To", "AV" and "Wa" at any size a heading is set in.
# Of the bundled faces only the four Roboto ones carry a `kern` feature:
# Inconsolata is monospaced and Latin Modern Math spaces by the MATH table, so
# both genuinely have none and a zero from them is a fact rather than a stub.
#
# One simplification, stated because it is invisible in these faces and would not
# be in others: OpenType applies every lookup in a feature in turn and accumulates
# their adjustments, whereas the search below stops at the first subtable that
# covers the pair, across all lookups. Each bundled face reaches `kern` through
# exactly one lookup, so the two agree here. A font with two kern lookups would
# need the accumulation, and this is the place to add it.
# --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _PairKerns:
    """
    A `PairPos` format 1 subtable: explicit values for named glyph pairs.
    """

    pairs: dict[tuple[str, str], int]


@dataclass(frozen=True, slots=True)
class _ClassKerns:
    """
    A `PairPos` format 2 subtable: a class-by-class matrix, the bulk of the data.
    """

    coverage: frozenset[str]
    first_classes: dict[str, int]
    second_classes: dict[str, int]
    values: tuple[tuple[int, ...], ...]


_KernSubtable = _PairKerns | _ClassKerns


def _subtable_kern(subtable: _KernSubtable, left: str, right: str) -> int | None:
    """
    This subtable's value for a pair, or `None` if it does not cover it.

    `None` and `0` are different answers: OpenType stops at the first subtable that
    covers the first glyph, so a covered pair with a zero value suppresses any later
    subtable that would have kerned it. Collapsing the two would resurrect exactly
    the exceptions a font ships a format 1 subtable to express.
    """
    match subtable:
        case _PairKerns(pairs):
            return pairs.get((left, right))
        case _ClassKerns(coverage, first_classes, second_classes, values):
            if left not in coverage:
                return None
            row = values[first_classes.get(left, 0)]
            column = second_classes.get(right, 0)
            return row[column] if column < len(row) else 0
    assert_never(subtable)


def _x_advance(record: Any) -> int:
    """
    The horizontal advance adjustment of a `ValueRecord`, which may omit the field.
    """
    if record is None:
        return 0
    return int(getattr(record, "XAdvance", 0) or 0)


def _read_pair_kerns(subtable: Any) -> _KernSubtable | None:
    """
    One `PairPos` subtable in the form `_subtable_kern` reads, or `None` if unusable.
    """
    if subtable.Format == 1:
        pairs: dict[tuple[str, str], int] = {}
        for first, pair_set in zip(subtable.Coverage.glyphs, subtable.PairSet, strict=True):
            for record in pair_set.PairValueRecord:
                pairs[(str(first), str(record.SecondGlyph))] = _x_advance(record.Value1)
        return _PairKerns(pairs)
    if subtable.Format == 2:
        values = tuple(
            tuple(_x_advance(second.Value1) for second in first.Class2Record)
            for first in subtable.Class1Record
        )
        return _ClassKerns(
            coverage=frozenset(str(name) for name in subtable.Coverage.glyphs),
            first_classes={str(k): int(v) for k, v in subtable.ClassDef1.classDefs.items()},
            second_classes={str(k): int(v) for k, v in subtable.ClassDef2.classDefs.items()},
            values=values,
        )
    return None  # pragma: no cover - formats 1 and 2 are the only ones defined


def _read_kern_feature(font: Any) -> tuple[_KernSubtable, ...]:
    """
    Every `PairPos` subtable reachable from the `kern` feature, in application order.
    """
    if "GPOS" not in font:
        return ()
    gpos = font["GPOS"].table
    if gpos.FeatureList is None or gpos.LookupList is None:
        return ()
    indices: list[int] = []
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == "kern":
            indices.extend(int(i) for i in record.Feature.LookupListIndex)

    subtables: list[_KernSubtable] = []
    for index in sorted(set(indices)):
        lookup = gpos.LookupList.Lookup[index]
        for raw in lookup.SubTable:
            # Type 9 wraps another lookup so a large font can exceed a 16-bit offset.
            # None of the bundled faces use it; unwrapping it is two lines and stops
            # a font swap from silently losing every kern.
            inner = raw.ExtSubTable if lookup.LookupType == 9 else raw
            inner_type = inner.LookupType if lookup.LookupType == 9 else lookup.LookupType
            if inner_type != 2:
                continue
            parsed = _read_pair_kerns(inner)
            if parsed is not None:
                subtables.append(parsed)
    return tuple(subtables)


# --------------------------------------------------------------------------------
# The OpenType MATH table
# --------------------------------------------------------------------------------


def _math_value(value: Any) -> int:
    """
    A `MathConstants` entry as a number: dimensions are records, percentages are ints.
    """
    return int(getattr(value, "Value", value))


@dataclass(frozen=True, slots=True)
class _MathData:
    """
    Everything read out of the `MATH` table, in font units, before any scaling.
    """

    constants: dict[str, int]
    italic_corrections: dict[str, int]
    vertical_variants: dict[str, tuple[tuple[str, int], ...]]


def _read_math_table(font: Any) -> _MathData | None:
    """
    The `MATH` table's contents, or `None` for a face that has no such table.
    """
    if "MATH" not in font:
        return None
    table = font["MATH"].table

    raw = table.MathConstants
    raw.ensureDecompiled()
    constants = {name: _math_value(value) for name, value in vars(raw).items()}

    italic: dict[str, int] = {}
    glyph_info = table.MathGlyphInfo
    if glyph_info is not None and glyph_info.MathItalicsCorrectionInfo is not None:
        info = glyph_info.MathItalicsCorrectionInfo
        for name, value in zip(info.Coverage.glyphs, info.ItalicsCorrection, strict=True):
            italic[str(name)] = _math_value(value)

    variants: dict[str, tuple[tuple[str, int], ...]] = {}
    math_variants = table.MathVariants
    if math_variants is not None and math_variants.VertGlyphCoverage is not None:
        for name, construction in zip(
            math_variants.VertGlyphCoverage.glyphs,
            math_variants.VertGlyphConstruction,
            strict=True,
        ):
            records = construction.MathGlyphVariantRecord
            if not records:
                continue
            variants[str(name)] = tuple(
                (str(r.VariantGlyph), int(r.AdvanceMeasurement)) for r in records
            )

    return _MathData(constants=constants, italic_corrections=italic, vertical_variants=variants)


# --------------------------------------------------------------------------------
# Synthetic codepoints for glyphs the font does not encode
#
# Latin Modern Math leaves 227 of its vertical variants unencoded, and the
# display-size summation is one of them: the chain is
# `U+2211 -> [('summation', 1001), ('summation.v1', 1401)]` and `summation.v1`
# has no codepoint at all. Everything downstream names a glyph by codepoint and
# by nothing else -- `advtext.nodes.CharNode`, `advtext.shipout.Glyph`, and every
# method on `FontMetrics` -- so without this the display-style big sigma cannot
# be expressed, and `docs/decisions.md` rules out the alternative of scaling the
# body glyph up.
#
# The fix is confined here on purpose. Widening `CharNode` with a glyph name
# would put a font-library concept in the hottest value of the layout core and
# oblige ship-out, both backends and selection to carry it. Minting a codepoint
# instead leaves every existing path working unchanged.
# --------------------------------------------------------------------------------

# Plane 15, the Supplementary Private Use Area. Assigned downward from the top.
# The BMP private-use block is avoided because real fonts do use it; verified
# this session that Latin Modern Math maps nothing in either range.
SYNTHETIC_FIRST = 0xFFFFD
SYNTHETIC_LAST = 0xF0000


def _encode_variants(face: Face, cmap: dict[int, str], math: _MathData | None) -> dict[str, int]:
    """
    A codepoint for every glyph a variant chain can reach, minting where needed.

    Mutates `cmap` so that the synthetic codepoints resolve through exactly the
    same lookup a real one does. Assignment is over a sorted glyph order, so the
    same font yields the same codepoints on every run -- a golden SVG artifact
    containing one has to be reproducible.
    """
    by_name: dict[str, int] = {}
    for codepoint, name in sorted(cmap.items()):
        by_name.setdefault(name, codepoint)
    if math is None:
        return by_name

    reachable = {name for chain in math.vertical_variants.values() for name, _ in chain}
    unencoded = sorted(reachable - set(by_name))
    for offset, name in enumerate(unencoded):
        codepoint = SYNTHETIC_FIRST - offset
        if codepoint < SYNTHETIC_LAST:
            raise MissingFontError(
                f"{face.value} needs {len(unencoded)} synthetic codepoints and "
                f"U+{SYNTHETIC_LAST:X}-U+{SYNTHETIC_FIRST:X} holds fewer"
            )
        if codepoint in cmap:
            # Overwriting would make a real glyph unreachable, and it would do it
            # silently: nothing downstream can tell a synthetic codepoint from a
            # font's own private-use one.
            raise MissingFontError(
                f"{face.value} already maps U+{codepoint:X} to {cmap[codepoint]!r}, "
                f"so it cannot be minted for {name!r}"
            )
        cmap[codepoint] = name
        by_name[name] = codepoint
    return by_name


# --------------------------------------------------------------------------------
# Faces
# --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _FaceData:
    """
    One font file, parsed once per process and shared by every size of that face.

    The caches are mutable dicts on a frozen record: the identity of the record is
    what is immutable, and a memo table is not part of its value.

    No `TTFont` is kept. Every table this project reads has been copied out into a
    plain dict by the time the record exists, and the glyph set draws from memory --
    so holding the font would only be holding a closed file. See the module docstring.
    """

    face: Face
    glyph_set: GlyphSet
    # Includes the synthetic codepoints `_encode_variants` minted, so nothing
    # downstream needs a second lookup path for a glyph the font does not encode.
    cmap: dict[int, str]
    # The inverse, restricted to glyphs a variant chain can reach.
    codepoints: dict[str, int]
    advances: dict[str, int]
    units_per_em: int
    ascent: int
    descent: int
    x_height: int
    kern_subtables: tuple[_KernSubtable, ...]
    math: _MathData | None
    bounds: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    kerns: dict[tuple[str, str], int] = field(default_factory=dict)

    def glyph(self, codepoint: int) -> str:
        """
        The glyph name for a codepoint, falling back to `.notdef`.
        """
        return self.cmap.get(codepoint, _NOTDEF)

    def glyph_bounds(self, name: str) -> tuple[float, float, float, float]:
        """
        Ink bounds in font units, memoised. A blank glyph has all-zero bounds.
        """
        cached = self.bounds.get(name)
        if cached is not None:
            return cached
        from fontTools.pens.boundsPen import BoundsPen

        pen = BoundsPen(self.glyph_set)
        if name in self.glyph_set:
            self.glyph_set[name].draw(pen)
        raw = pen.bounds
        result: tuple[float, float, float, float] = (
            (0.0, 0.0, 0.0, 0.0)
            if raw is None
            else (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        )
        self.bounds[name] = result
        return result

    def pair_kern(self, left: str, right: str) -> int:
        """
        Kern in font units for an adjacent pair, memoised, zero when uncovered.
        """
        cached = self.kerns.get((left, right))
        if cached is not None:
            return cached
        value = 0
        for subtable in self.kern_subtables:
            found = _subtable_kern(subtable, left, right)
            if found is not None:
                value = found
                break
        self.kerns[(left, right)] = value
        return value


@cache
def _face_data(face: Face) -> _FaceData:
    """
    Open and parse one face. Called once per face per process.

    Every table the rest of the module can ever need is asked for here, because the
    file is closed before this returns and a table never asked for is unreachable
    afterwards. The module docstring says why the close is not negotiable and why it
    does not conflict with `lazy=True`.
    """
    from fontTools.ttLib import TTFont

    path = font_file(face)
    # lazy=True defers decompiling a table, not reading it. See the module docstring:
    # that is what lets this stay cheap for a metrics-only workload and still close.
    font = TTFont(path, lazy=True)
    head = font["head"]
    # hhea rather than OS/2 sTypo: stb_truetype -- and so Dear ImGui, which bakes
    # through it -- reads vertical metrics from hhea, and a face whose ascent differs
    # between our layout and ImGui's atlas would put every baseline in the wrong
    # place in the one backend we cannot run to check.
    hhea = font["hhea"]
    os2 = font["OS/2"] if "OS/2" in font else None
    units_per_em = int(head.unitsPerEm)
    raw_x_height = int(getattr(os2, "sxHeight", 0) or 0) if os2 is not None else 0
    cmap = {int(k): str(v) for k, v in font.getBestCmap().items()}
    math = _read_math_table(font)
    codepoints = _encode_variants(face, cmap, math)
    data = _FaceData(
        face=face,
        # Built before the close, and load-bearing for it: this is what pulls the
        # outline table's bytes into memory and binds the horizontal metrics the
        # glyph set reads per glyph.
        glyph_set=font.getGlyphSet(),
        cmap=cmap,
        codepoints=codepoints,
        advances={str(name): int(metric[0]) for name, metric in font["hmtx"].metrics.items()},
        units_per_em=units_per_em,
        ascent=int(hhea.ascender),
        descent=-int(hhea.descender),
        x_height=raw_x_height or round(_X_HEIGHT_FALLBACK * units_per_em),
        kern_subtables=_read_kern_feature(font),
        math=math,
    )
    font.close()
    return data


class FaceMetrics:
    """
    `FontMetrics` over a real font file: one face at one size.
    """

    __slots__ = ("_data", "_scale", "_size")

    def __init__(self, data: _FaceData, size: float) -> None:
        self._data = data
        self._size = size
        self._scale = size / data.units_per_em

    @property
    def face(self) -> Face:
        return self._data.face

    @property
    def size(self) -> float:
        return self._size

    @property
    def ascent(self) -> float:
        return self._data.ascent * self._scale

    @property
    def descent(self) -> float:
        return self._data.descent * self._scale

    @property
    def x_height(self) -> float:
        return self._data.x_height * self._scale

    @property
    def em(self) -> float:
        return self._size

    @property
    def space_width(self) -> float:
        return self.advance(0x20)

    def has(self, codepoint: int) -> bool:
        return codepoint in self._data.cmap

    def advance(self, codepoint: int) -> float:
        name = self._data.glyph(codepoint)
        return self._data.advances.get(name, 0) * self._scale

    def bbox(self, codepoint: int) -> GlyphBBox:
        x_min, y_min, x_max, y_max = self._data.glyph_bounds(self._data.glyph(codepoint))
        return GlyphBBox(
            x_min=x_min * self._scale,
            y_min=y_min * self._scale,
            x_max=x_max * self._scale,
            y_max=y_max * self._scale,
        )

    def kern(self, codepoint: int, following: int) -> float:
        left = self._data.glyph(codepoint)
        right = self._data.glyph(following)
        return self._data.pair_kern(left, right) * self._scale

    def __repr__(self) -> str:
        return f"FaceMetrics({self._data.face.value!r}, size={self._size!r})"


class MathFaceMetrics(FaceMetrics):
    """
    `MathFontMetrics` over a face carrying an OpenType `MATH` table.

    The module docstring's table is the specification for `math`; this class only
    performs the arithmetic it describes.
    """

    __slots__ = ("_math", "_params")

    def __init__(self, data: _FaceData, size: float) -> None:
        super().__init__(data, size)
        if data.math is None:
            raise MissingFontError(
                f"{data.face.value} maps to {font_file(data.face).name}, which has no MATH table"
            )
        self._math = data.math
        self._params = self._build_params(data.math.constants)

    def _build_params(self, c: dict[str, int]) -> MathParams:
        """
        Scale the `MATH` constants into TeX's parameter names at this size.
        """
        scale = self._size / self._data.units_per_em
        em = self._size

        def dimen(name: str) -> float:
            return c[name] * scale

        return MathParams(
            math_x_height=self.x_height,
            math_quad=em,
            num1=dimen("FractionNumeratorDisplayStyleShiftUp"),
            num2=dimen("FractionNumeratorShiftUp"),
            num3=dimen("StackTopShiftUp"),
            denom1=dimen("FractionDenominatorDisplayStyleShiftDown"),
            denom2=dimen("FractionDenominatorShiftDown"),
            sup1=dimen("SuperscriptShiftUp"),
            sup2=dimen("SuperscriptShiftUp"),
            sup3=dimen("SuperscriptShiftUpCramped"),
            sub1=dimen("SubscriptShiftDown"),
            sub2=dimen("SubscriptShiftDown"),
            sup_drop=dimen("SuperscriptBaselineDropMax"),
            sub_drop=dimen("SubscriptBaselineDropMin"),
            delim1=2.4 * em,
            delim2=1.0 * em,
            axis_height=dimen("AxisHeight"),
            default_rule_thickness=dimen("FractionRuleThickness"),
            big_op_spacing1=dimen("UpperLimitGapMin"),
            big_op_spacing2=dimen("LowerLimitGapMin"),
            big_op_spacing3=dimen("UpperLimitBaselineRiseMin"),
            big_op_spacing4=dimen("LowerLimitBaselineDropMin"),
            big_op_spacing5=0.1 * em,
            radical_rule_thickness=dimen("RadicalRuleThickness"),
            radical_vertical_gap=dimen("RadicalVerticalGap"),
            radical_display_style_vertical_gap=dimen("RadicalDisplayStyleVerticalGap"),
            script_scale=c["ScriptPercentScaleDown"] / 100.0,
            script_script_scale=c["ScriptScriptPercentScaleDown"] / 100.0,
            display_operator_min_height=dimen("DisplayOperatorMinHeight"),
        )

    @property
    def math(self) -> MathParams:
        return self._params

    def italic_correction(self, codepoint: int) -> float:
        name = self._data.glyph(codepoint)
        return self._math.italic_corrections.get(name, 0) * self._scale

    def vertical_variants(self, codepoint: int) -> tuple[GlyphVariant, ...]:
        name = self._data.glyph(codepoint)
        chain = self._math.vertical_variants.get(name, ())
        return tuple(
            GlyphVariant(
                name=n,
                codepoint=self._data.codepoints[n],
                extent=extent * self._scale,
            )
            for n, extent in chain
        )

    def __repr__(self) -> str:
        return f"MathFaceMetrics({self._data.face.value!r}, size={self._size!r})"


@cache
def math_metrics(size: float) -> MathFontMetrics:
    """
    The math face at one size. Identical arguments return the identical object.
    """
    return MathFaceMetrics(_face_data(Face.MATH), size)


@cache
def _prose_metrics(face: Face, size: float) -> FontMetrics:
    """
    A non-math face at one size, cached separately so `metrics` can stay total.
    """
    return FaceMetrics(_face_data(face), size)


def metrics(face: Face, size: float) -> FontMetrics:
    """
    Any face at one size. Identical arguments return the identical object, so a
    caller may use the result as a dict key without paying to re-open a font.
    """
    if face is Face.MATH:
        return math_metrics(size)
    return _prose_metrics(face, size)


def em_size_for_pixel_height(face: Face, pixel_height: float) -> float:
    """
    The em size at which this face comes out `pixel_height` tall, as ImGui means it.

    **"Size" names two lengths and a host has the other one.** ImGui sizes a
    font by pixel *height* -- stb_truetype scales by `hhea` ascender minus
    descender -- while this project sizes a face by its *em*, which is what
    `metrics` takes and what a `Theme` is built from. `advtext.backends.
    imgui_draw.baked_size_px` converts em to height on the way out, as
    `size * (ascent + descent) / em`; this is its inverse on the way in. A host
    whose UI font is "16" passes 16 here, builds its theme at the answer, and
    the text is drawn at ImGui's 16 -- the same raster, not one resampled from a
    neighbouring size.

    It needs the face because the ratio is the face's: measured on the bundled
    files, a 16 px height is an em of 13.653 px in Roboto and 15.253 px in
    Inconsolata. One number for both would be wrong for one of them.

    The answer is in the unit `pixel_height` was given in and is not rounded.
    Convert it to scaled points with `advtext.units.sp_from_px` on the way into
    a `FontSpec`; that rounding is why the round trip through `baked_size_px`
    lands within a few millionths of a pixel of the height asked for rather than
    on it, and ImGui's own `floor(size + 0.5)` then selects the size meant.
    """
    data = _face_data(face)
    extent = data.ascent + data.descent
    if extent <= 0:
        # A face whose hhea states no vertical extent. `baked_size_px` leaves the
        # size alone in its own degenerate case and this is the same answer.
        return pixel_height
    return pixel_height * data.units_per_em / extent


def glyph_name(face: Face, codepoint: int) -> str:
    """
    The font's own name for a glyph, which is what an outline is pulled by.

    Size-independent, so it does not hang off `FontMetrics`. The SVG backend
    needs it -- `SVGPathPen` draws from `glyph_set(face)[name]`, and a synthetic
    codepoint from a variant chain resolves through no other route. Returns
    `.notdef` for a codepoint this face does not map.
    """
    return _face_data(face).glyph(codepoint)


def glyph_set(face: Face) -> tuple[GlyphSet, int]:
    """
    A face's drawable glyphs and its em size in font units, from the one open.

    Size-independent for the same reason `glyph_name` is: an outline is in font units
    and a pen scales it, so nothing here depends on a point size. The em size comes
    back with it because it is the only number needed to scale what the pen produced,
    and asking for it separately would tempt a caller into a second parse.

    This is the whole of what a renderer needs from a font file, so no backend has any
    reason to open one. Outlines are drawn from memory -- the file behind this face is
    already closed, and the module docstring says why.
    """
    data = _face_data(face)
    return data.glyph_set, data.units_per_em


# --------------------------------------------------------------------------------
# A font file ImGui can rasterise every glyph this project names
#
# The synthetic codepoints above exist so `summation.v1` can be named. They are
# ours, so the font's own cmap does not contain them, and ImGui rasterises by
# Unicode codepoint through that cmap -- it looks the glyph up with
# stb_truetype's `FindGlyphIndex` and knows nothing of our minting. The SVG
# backend is unaffected because it resolves by glyph *name*.
#
# So the display sigma draws in one backend and not the other, for a mechanical
# reason and not a layout failure. The fix is to write our mappings into a copy
# of the font and hand ImGui that: its own lookup then finds the glyph with no
# further help, and it bakes the real outline at the real size rather than a
# scaled-up body glyph.
#
# Two facts make this work, both measured rather than assumed:
#
# - imgui-bundle 1.92.801 is built with a **32-bit** `ImWchar`, so a plane-15
#   codepoint survives the binding. The discriminating test is that
#   `is_glyph_in_font(0x12211)` returns False rather than truncating to U+2211
#   and returning True. A 16-bit build would make this whole approach impossible
#   and there would be nothing to do but report it.
# - Latin Modern Math carries two format-12 cmap subtables, which are the only
#   format that can express a codepoint above U+FFFF. Every codepoint minted
#   above is in plane 15 by construction, so format 12 is the only one that ever
#   needs touching.
#
# A file rather than a buffer because imgui-bundle does not bind
# `AddFontFromMemoryTTF` -- it appears only in a comment in the stubs. If that
# binding ever lands, this should hand over bytes and the temporary directory
# should go.
# --------------------------------------------------------------------------------


def synthetic_codepoints(face: Face) -> Mapping[int, str]:
    """
    Every codepoint `_encode_variants` minted for a face, to the glyph it names.

    Empty for every face with no `MATH` table, and for a math face whose variant
    chains happen to reach only encoded glyphs. Latin Modern Math leaves 227
    vertical variants unencoded, so it is the one face that returns anything.

    Public because it is the whole input to `imgui_font_file` and because a test
    that wants to pin the minting needs to see it without reaching into `_FaceData`.
    """
    data = _face_data(face)
    return {
        codepoint: name
        for codepoint, name in data.cmap.items()
        if SYNTHETIC_LAST <= codepoint <= SYNTHETIC_FIRST
    }


@cache
def _patched_font_directory() -> Path:
    """
    A per-process scratch directory for fonts with our codepoints written in.

    Not cleaned up. ImGui keeps no copy of the file it was handed -- it reads it
    during `add_font_from_file_ttf` -- but a caller may bake lazily at a new size
    later, and deleting the file underneath that is a crash rather than a missing
    glyph. A handful of kilobytes in the system temporary directory is the
    cheaper failure.
    """
    return Path(tempfile.mkdtemp(prefix="advtext-fonts-"))


@cache
def imgui_font_file(face: Face) -> Path:
    """
    A file for this face that ImGui can rasterise every glyph this project names.

    Returns `font_file(face)` unchanged whenever nothing was minted, which is
    every face but the math one -- so the common path copies nothing and the
    caller needs no conditional.

    For the math face, the font is read, our synthetic mappings are written into
    every format-12 cmap subtable, and the result is saved under a temporary
    directory, in a file named for the role and for the source file's full path
    (a digest of it), so re-registering the role to another file never writes
    over the copy made for the first. The same source is still saved to the same
    name each time the registry changes -- same bytes, unless the host replaced
    the file in place, which nothing here detects. Nothing else about the font
    is touched: the outlines, the `MATH` table and the horizontal metrics are the
    file's own, which is what makes the glyph ImGui bakes the same glyph the SVG
    backend draws.

    **Degrades rather than raises.** A font with no format-12 subtable cannot
    express a plane-15 codepoint at all, and the honest answer there is the
    original file plus a count from `advtext.backends.imgui_draw.DrawStats.missing`
    -- the behaviour this project had before this function existed. Raising would
    turn a font swap into a crash in the one layer that cannot be tested by
    opening it.

    Verified in `tests/test_imgui_draw.py`
    (`test_the_display_summation_is_a_bigger_glyph_than_the_body_one` and the
    test above it), which add the result to a real atlas and assert that the
    display-size summation is present and larger than U+2211. Those tests need
    no display; see that file for why. (This used to cite a
    `tests/test_imgui_atlas.py`, which does not exist.)
    """
    path = font_file(face)
    minted = synthetic_codepoints(face)
    if not minted:
        return path

    from fontTools.ttLib import TTFont

    font = TTFont(path)
    try:
        wide = [table for table in font["cmap"].tables if table.format == 12]
        if not wide:
            return path
        for table in wide:
            table.cmap.update(minted)
        # Named for the source's whole path, not just its file name: two
        # registered files called the same thing in two directories would
        # otherwise be saved over one another, and the first is the file an
        # `ImFont` already in a host's atlas was loaded from.
        digest = hashlib.sha256(os.fsencode(path)).hexdigest()[:12]
        destination = _patched_font_directory() / f"{face.value}-{digest}-{path.name}"
        font.save(destination)
    finally:
        font.close()
    return destination

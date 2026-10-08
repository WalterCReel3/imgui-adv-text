r"""
The formula gallery, tested against the real fonts and against the real rules.

**There is no fake measure in this file, and that is deliberate.** `docs/status.md`
§5 names a uniform fake as the first of three families of vacuous tests found in
this tree. Every claim below is about a *difference* -- a display glyph against a
text one, a classified formula against an unclassified one, a style that shrinks
against a style that has stopped shrinking -- and a fake that flattened the font
would not weaken these tests, it would invert them into tautologies. The fonts are
present, `bundled_fonts` skips when they are not.

## What a test in this file has to survive

Asserting that a formula "packs without raising" is worthless: it holds for a
gallery of empty boxes. So does asserting a box is non-zero: it holds for a gallery
that set every formula in the same size and never shrank anything. Each test here
is paired with the wrong implementation it is meant to catch, and several of the
pairs are written out as controls:

- `test_the_nesting_really_does_get_deeper_at_each_step` is the fixture check
  behind the scriptscript clamp. "Three font sizes however deep you go" is only
  interesting if the depth is really increasing, and it would pass for a builder
  that ignored its `depth` argument.
- `test_the_two_towers_are_the_same_four_letters` is the fixture check behind the
  cramping asymmetry: "up goes further than down" would hold trivially if the two
  towers had different content, and `_tower` builds them so they cannot.
- `test_a_codepoint_the_math_face_lacks_is_reported` stops "no entry is missing a
  glyph" from passing for a coverage check that always returns nothing. `U+0127`
  is a real hole in Latin Modern Math, found by looking.
- `test_the_spacing_between_two_atoms_is_exactly_the_tables_mu_glue` asserts an
  *equality* against `MATH_SPACING` and the font's own math quad, not an
  inequality. A renderer that inserted some arbitrary constant space would pass
  "bin is wider than ord" and fail this.

The caption coverage test earned its place the hard way: the first draft of the
`cauchy` caption quoted the contour-integral sign, the tab reported one glyph with
no raster, and nothing in the suite noticed. Neither Roboto nor Inconsolata has
`U+222E`. That test now checks every character of every caption against the face
markdown actually sets it in.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from advtext import fontlib
from advtext.fontmetrics import Face
from advtext.markdown import build_document
from advtext.math import (
    Atom,
    AtomType,
    Limits,
    MathFonts,
    MathItem,
    Style,
    bin_,
    frac,
    group,
    math_fonts,
    mlist_to_hlist,
    op,
    ord_,
    rel,
)
from advtext.math.mlist import MATH_SPACING
from advtext.nodes import Box, CharNode
from advtext.pack import CharMeasure, hpack
from advtext.shipout import Glyph, Point, RuleRect, ship
from advtext.style import (
    Theme,
    char_measure,
    fontlib_metrics,
    parse_font_key,
)
from advtext.ui import compose_blocks
from advtext.ui.formulas import (
    CLASSIC_ENTRIES,
    ENTRIES,
    FORMULA_PX,
    SIZED_ENTRIES,
    Gallery,
    _continued_fraction,
    _tower,
    build_gallery,
    char_fonts,
    codepoints,
    fontlib_math_metrics,
    italic,
    missing_codepoints,
    missing_glyphs,
    var,
)
from advtext.units import Scaled, sp_from_px

MEASURE = sp_from_px(468.0)
"""
The prose measure the gallery is built at here.

The one the Formula tab actually sets at the demo's default window, so the
captions break the way they break on screen rather than at a width chosen to make
an assertion come out.
"""

HBAR_WITH_STROKE = 0x0127
"""
`LATIN SMALL LETTER H WITH STROKE`, which Latin Modern Math genuinely does not have.

The near neighbour of `U+210F PLANCK CONSTANT OVER TWO PI`, which it does. Used as
the control for the coverage check: without a codepoint that really is absent,
"every entry is fully covered" would pass for a check that never reports anything.
"""

CONTOUR_INTEGRAL = 0x222E
"""
The sign neither prose face carries, and the reason the caption test exists.
"""


@pytest.fixture(scope="session")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="session")
def gallery(bundled_fonts: Path, theme: Theme) -> Gallery:
    """
    The nine `CLASSIC_ENTRIES`, built once: every test below reads the same one.

    The nine and not all of `ENTRIES`, because most of this file is claims about
    those nine plates (and one digest of them taken before the engine grew).
    `eleven` is the gallery as it ships.
    """
    return build_gallery(theme, MEASURE, fontlib_metrics, entries=CLASSIC_ENTRIES)


@pytest.fixture(scope="session")
def fonts(bundled_fonts: Path, theme: Theme) -> MathFonts:
    """
    The three math sizes the gallery sets its formulae from.
    """
    return math_fonts(sp_from_px(FORMULA_PX, theme.px_per_inch), fontlib_math_metrics)


@pytest.fixture(scope="session")
def eleven(bundled_fonts: Path, theme: Theme) -> Gallery:
    """
    The gallery as it ships, by `build_gallery`'s default: the nine and then the two.
    """
    return build_gallery(theme, MEASURE, fontlib_metrics)


def _set(items: Sequence[MathItem], fonts: MathFonts, style: Style = Style.DISPLAY) -> Box:
    """
    One math list, converted and packed at its natural width.
    """
    return hpack(mlist_to_hlist(list(items), style, fonts), measure=fonts.measure).box


def _glyphs(box: Box, measure: CharMeasure) -> tuple[Glyph, ...]:
    return tuple(
        command
        for command in ship(box, Point(0, box.height), measure=measure)
        if isinstance(command, Glyph)
    )


def _rules(box: Box, measure: CharMeasure) -> tuple[RuleRect, ...]:
    return tuple(
        command
        for command in ship(box, Point(0, box.height), measure=measure)
        if isinstance(command, RuleRect)
    )


# ----------------------------------------------------------------------
# The gallery holds what it says it holds
# ----------------------------------------------------------------------


def test_every_entry_key_is_unique_and_survives_into_the_built_gallery(gallery: Gallery) -> None:
    """
    Keys are the interface a test names an entry by, so two entries may not share one.
    """
    keys = [entry.key for entry in gallery.entries]
    assert len(keys) == len(set(keys))
    assert keys == [entry.key for entry in CLASSIC_ENTRIES]


def test_every_panel_sets_every_glyph_its_formula_names(gallery: Gallery, theme: Theme) -> None:
    """
    The anti-vacuity test for the whole gallery.

    A panel that packed to an empty box would pass any check on the gallery's
    height, its width, or its entry count -- the caption alone would keep all
    three plausible. This ships each panel and counts the glyphs that came out,
    against the count the definition asked for. They must agree exactly: a formula
    names N characters and sets N of them, no more and none dropped.
    """
    measure = char_measure(fontlib_metrics)
    for entry in gallery.entries:
        for panel in entry.panels:
            wanted = codepoints(panel.items)
            drawn = _glyphs(panel.box, measure)
            assert len(drawn) == len(wanted), f"{entry.key}: {len(drawn)} glyphs for {wanted!r}"
            assert wanted, f"{entry.key} names no characters at all"


def test_a_panels_glyphs_are_set_in_the_math_face_at_one_of_three_sizes(
    gallery: Gallery, fonts: MathFonts
) -> None:
    """
    Every character of every formula comes from `Face.MATH`, at a size `math_fonts`
    minted. A formula that fell back to the prose face would still look like a
    formula in a thumbnail.
    """
    allowed = set(fonts.keys.values())
    for entry in gallery.entries:
        for panel in entry.panels:
            for key in char_fonts(panel.box):
                assert parse_font_key(key).face is Face.MATH
                assert key in allowed, f"{entry.key} set a glyph at {key}, not one of {allowed}"


# ----------------------------------------------------------------------
# The four styles, and where they stop
# ----------------------------------------------------------------------


def test_a_four_deep_continued_fraction_uses_exactly_three_font_sizes(fonts: MathFonts) -> None:
    """
    §702's `num_style` is `#+2-2*(# div 6)` (`docs/tex.web` line 13858), the identity
    at scriptscript. So however deep the nesting goes, only three sizes are ever set.

    Asserted as a set equality against `MathFonts.keys` rather than as a count, so a
    clamp that stopped at the *wrong* size -- script, say, never reaching
    scriptscript -- also fails.
    """
    box = _set([_continued_fraction(4)], fonts)
    assert set(char_fonts(box)) == set(fonts.keys.values())


@pytest.mark.parametrize("depth", [3, 4, 5, 6, 8])
def test_the_clamp_holds_however_deep_the_fraction_goes(fonts: MathFonts, depth: int) -> None:
    """
    The clamp, from the direction an unclamped implementation fails.

    An implementation that kept applying `num_style` without §702's `div 6` term
    would mint a fourth, fifth and sixth size and still produce a fraction that
    looked plausible. It would fail here at `depth=5`.
    """
    box = _set([_continued_fraction(depth)], fonts)
    assert len(set(char_fonts(box))) == 3


def test_the_nesting_really_does_get_deeper_at_each_step(fonts: MathFonts) -> None:
    """
    The fixture check behind the two tests above.

    "Three sizes however deep" is only a claim if the depth is really increasing.
    A `_continued_fraction` that ignored its argument would leave both of them
    green while covering nothing -- `docs/status.md` §5's third family, exactly.
    Each step must add height, and the glyph count must grow by the three
    characters one more level costs.
    """
    measure = char_measure(fontlib_metrics)
    previous_height = 0
    previous_glyphs = 0
    for depth in range(1, 7):
        box = _set([_continued_fraction(depth)], fonts)
        total = box.height + box.depth
        assert total > previous_height, f"depth {depth} is no taller than depth {depth - 1}"
        count = len(_glyphs(box, measure))
        assert count == previous_glyphs + 3 if depth > 1 else count > 0
        previous_height, previous_glyphs = total, count


def test_a_tower_of_scripts_reaches_scriptscript_and_stops(fonts: MathFonts) -> None:
    """
    The same clamp from the script side: `x^{y^{z^{w}}}` sets `w` at `z`'s size.

    Read off the shipped glyphs rather than off `char_fonts`, because the claim is
    about the last *two* letters specifically and a set would not distinguish "w is
    the same size as z" from "w is the same size as x".
    """
    measure = char_measure(fontlib_metrics)
    drawn = _glyphs(_set([_tower("sup")], fonts), measure)
    assert [chr(glyph.codepoint) for glyph in drawn] == list(italic("xyzw"))
    assert drawn[0].font != drawn[1].font != drawn[2].font
    assert drawn[2].font == drawn[3].font
    assert drawn[3].font == fonts.keys[max(fonts.keys)]


def test_a_superscript_tower_rises_further_than_a_subscript_tower_drops(gallery: Gallery) -> None:
    """
    §702: `sup_style` keeps the cramping it inherited, `sub_style` always adds it
    (`docs/tex.web` lines 13856-13857). A cramped style holds its own scripts down.

    Read off the **gallery's own panels**, not off a fresh `_tower` call. That is
    not incidental: an earlier draft of this test and the one below both built
    their towers directly, so swapping the letters in the `script-towers` entry
    left every assertion in this file green while the tab showed a comparison of
    two different things. Ablation caught it; `docs/status.md` §5 is about exactly
    this and it happened here anyway.
    """
    up, down = gallery.entry("script-towers").panels
    assert up.box.height > down.box.depth


def test_the_two_towers_in_the_gallery_are_the_same_four_letters(gallery: Gallery) -> None:
    """
    The fixture check behind the asymmetry, on the entry that is actually shown.

    "Up goes further than down" is a fact about cramping only if the two towers are
    otherwise identical. Two towers built from different letters would separate for
    a reason that has nothing to do with §702.
    """
    measure = char_measure(fontlib_metrics)
    up, down = gallery.entry("script-towers").panels
    assert [glyph.codepoint for glyph in _glyphs(up.box, measure)] == [
        glyph.codepoint for glyph in _glyphs(down.box, measure)
    ]
    assert [glyph.font for glyph in _glyphs(up.box, measure)] == [
        glyph.font for glyph in _glyphs(down.box, measure)
    ]
    assert up.box.width == down.box.width
    assert up.style is down.style


def test_the_tower_builder_hangs_the_letters_it_was_given(fonts: MathFonts) -> None:
    """
    `_tower` itself: the first letter carries the rest, innermost last, both ways.

    Separate from the gallery tests above because it is a different claim -- that
    the builder does what its name says -- and because the two towers being equal
    would also hold for a builder that returned a bare `x` in both directions.
    """
    measure = char_measure(fontlib_metrics)
    for script in ("sup", "sub"):
        drawn = _glyphs(_set([_tower(script, "pqrs")], fonts), measure)
        assert [chr(glyph.codepoint) for glyph in drawn] == list(italic("pqrs"))


# ----------------------------------------------------------------------
# Fractions
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("numerator", "denominator"), [("1", "1000"), ("1000", "1"), ("1000", "1000")]
)
def test_a_fraction_bar_spans_the_wider_of_its_two_halves(
    fonts: MathFonts, numerator: str, denominator: str
) -> None:
    """
    §746's `fraction_rule` has running width, so it takes the enclosing vbox's.

    Both orders, because an implementation that sized the rule from the *numerator*
    alone passes `1000/1` and fails `1/1000`, and one that sized it from the
    denominator fails the other way. One case on its own cannot tell the three
    apart.
    """
    box = _set([frac(numerator, denominator)], fonts)
    rules = _rules(box, fonts.measure)
    assert len(rules) == 1
    assert rules[0].width == box.width
    wider = _set([ord_(max((numerator, denominator), key=len))], fonts)
    assert rules[0].width >= wider.width


def test_the_two_bar_widths_agree_when_the_halves_are_merely_swapped(fonts: MathFonts) -> None:
    """
    `1/1000` and `1000/1` get the same bar. The sharpest form of the test above.
    """
    narrow_over_wide = _rules(_set([frac("1", "1000")], fonts), fonts.measure)[0]
    wide_over_narrow = _rules(_set([frac("1000", "1")], fonts), fonts.measure)[0]
    assert narrow_over_wide.width == wide_over_narrow.width


# ----------------------------------------------------------------------
# The inter-atom spacing table
# ----------------------------------------------------------------------


def _mu_width(code: str, fonts: MathFonts, style: Style = Style.DISPLAY) -> Scaled:
    """
    What §764's table code costs in scaled points at this style.

    Three, four and five math units for thin, medium and thick, each a
    eighteenth of the font's own math quad -- not a number chosen here.
    """
    mu = fonts.mu(style)
    widths: dict[str, Scaled] = {"0": 0, "1": 3 * mu, "2": 3 * mu, "3": 4 * mu, "4": 5 * mu}
    return widths[code]


@pytest.mark.parametrize(
    ("middle", "code"),
    [(ord_("+"), "0"), (bin_("+"), "3"), (rel("+"), "4")],
)
def test_the_spacing_between_two_atoms_is_exactly_the_tables_mu_glue(
    fonts: MathFonts, middle: Atom, code: str
) -> None:
    r"""
    The same glyph, classified three ways, spaced by §764's string and nothing else.

    An **equality**, not an ordering. "A binary operator is wider than an ordinary
    one" would pass for a renderer that inserted any constant it liked; this pins
    the width to `\medmuskip` and `\thickmuskip` scaled by the font's own math
    quad, twice over because the class contributes on both sides.

    `MATH_SPACING` is read here rather than the codes being typed out, so the
    parametrisation and the implementation cannot drift into agreement over a wrong
    table.
    """
    plain = _set([ord_("a"), ord_("+"), ord_("b")], fonts)
    spaced = _set([ord_("a"), middle, ord_("b")], fonts)
    expected = 2 * _mu_width(code, fonts)
    assert spaced.width - plain.width == expected
    # And the code really is the one the table gives for this pair, both joins.
    left = MATH_SPACING[8 * 0 + middle.kind.spacing_class]
    right = MATH_SPACING[8 * middle.kind.spacing_class + 0]
    assert left == right == code


def test_classifying_five_atoms_is_the_whole_difference_between_the_two_panels(
    gallery: Gallery, fonts: MathFonts
) -> None:
    """
    The `atom-classes` entry: same glyphs, one classified and one not.

    The difference must be exactly one medium space plus one thick space, both
    doubled, and nothing else -- so the two panels must also set the identical
    sequence of codepoints at the identical sizes.
    """
    classified, ordinary = gallery.entry("atom-classes").panels
    measure = char_measure(fontlib_metrics)
    assert [glyph.codepoint for glyph in _glyphs(classified.box, measure)] == [
        glyph.codepoint for glyph in _glyphs(ordinary.box, measure)
    ]
    expected = 2 * _mu_width("3", fonts) + 2 * _mu_width("4", fonts)
    assert classified.box.width - ordinary.box.width == expected


def test_a_leading_minus_is_reclassified_and_costs_no_space_at_all(
    gallery: Gallery, fonts: MathFonts
) -> None:
    """
    §727: the scan starts with `r_type:=op_noad` (`docs/tex.web` line 14297), so the
    first atom of a list falls into the case that rewrites a `Bin` as an `Ord`.

    Asserted as "the panel is exactly the sum of its two glyphs", which is the
    strongest available form: it rules out a shrunken space as well as a full one.
    """
    alone, preceded = gallery.entry("binary-or-not").panels
    natural = _set([ord_("−")], fonts).width + _set([var("x")], fonts).width
    assert alone.box.width == natural
    # The same glyph *is* binary once something precedes it, and then it costs the
    # medium space on both sides. Without this half the test above would also pass
    # for an engine that had no spacing table at all.
    assert preceded.box.width == natural + _set([var("a")], fonts).width + 2 * _mu_width("3", fonts)


def test_both_halves_of_the_reclassification_entry_really_are_written_as_binary(
    gallery: Gallery,
) -> None:
    """
    The one claim in this file that **cannot** be checked geometrically, and why.

    The caption says both panels are written with `bin_`. If the left one were
    written `ord_` instead the rendering would be byte-identical -- that is the
    whole content of §727 -- so no measurement can tell the two apart, and
    ablating the definition to `ord_` left every other test here green. The entry
    would then be demonstrating nothing while looking exactly the same, which is
    the worst available failure: a caption that lies with a picture that agrees
    with it.

    So this reads the definition. It is the only structural assertion in the file
    and it is here because the alternative is no assertion at all.
    """
    alone, preceded = gallery.entry("binary-or-not").panels
    assert bin_("−") in alone.items, "the left panel stopped being a written Bin"
    assert bin_("−") in preceded.items

    # And the two are the same atom, so the entry is one glyph in two contexts
    # rather than two glyphs.
    def binaries(items: Sequence[MathItem]) -> list[Atom]:
        return [item for item in items if isinstance(item, Atom) and item.kind is AtomType.BIN]

    assert binaries(alone.items) == binaries(preceded.items)


def test_schrodingers_minus_is_demoted_by_the_equals_sign_before_it(
    gallery: Gallery, fonts: MathFonts
) -> None:
    """
    §727 inside a real formula, not a two-atom fixture.

    The minus after `=` is written `bin_("−")` and must set with no space, exactly
    as the isolated case does. Measured by rebuilding the formula with that atom
    written as an ordinary one and requiring the two to be the *same width*: if the
    demotion did not happen the binary version would be a medium space wider on
    each side.
    """
    written_as_binary = gallery.entry("schrodinger").panels[0]
    items = list(written_as_binary.items)
    index = next(i for i, item in enumerate(items) if item == bin_("−"))
    items[index] = ord_("−")
    assert _set(items, fonts).width == written_as_binary.box.width


# ----------------------------------------------------------------------
# Big operators
# ----------------------------------------------------------------------


def test_the_display_summation_is_a_different_glyph_from_the_text_one(gallery: Gallery) -> None:
    """
    The tab's oldest claim, kept: display follows the `list_tag` variant chain
    (`docs/tex.web` line 14688) to a larger *outline*, not to a scaled copy.

    Compared by glyph **name**, because a scaled-up glyph passes a height
    comparison -- `docs/status.md` §5 lists that as the house habit and this is
    where it came from.
    """
    measure = char_measure(fontlib_metrics)
    display, text = gallery.entry("operator-style").panels
    names = []
    for panel in (display, text):
        sigma = _glyphs(panel.box, measure)[0]
        names.append(fontlib.glyph_name(Face.MATH, sigma.codepoint))
    assert names[0] != names[1]
    assert names[1] == fontlib.glyph_name(Face.MATH, ord("∑"))


def test_limits_stack_by_default_in_display_and_sit_beside_the_operator_otherwise(
    fonts: MathFonts,
) -> None:
    """
    §749: `if (subtype(q)=normal)and(cur_style<text_style) then subtype(q):=limits`
    (`docs/tex.web` line 14684). One line, two visibly different settings.

    The stacked one is taller and narrower than the one set to the right. Both
    halves are asserted: taller alone would also hold for a display operator whose
    scripts were simply bigger.
    """
    summation = op("∑", sup=ord_("∞"), sub=group(ord_("n"), rel("="), ord_("1")))
    stacked = _set([summation], fonts, Style.DISPLAY)
    beside = _set([summation], fonts, Style.TEXT)
    assert stacked.height + stacked.depth > beside.height + beside.depth
    assert stacked.width < beside.width


def test_no_limits_overrides_that_default_even_in_display_style(fonts: MathFonts) -> None:
    """
    What `cauchy` demonstrates, isolated: the same operator with the same script,
    at the same style, differing only in the `Limits` flag.

    Asserted on the shipped *position* of the script rather than on the width of
    the box, and that is not fussiness -- the first draft of this test claimed the
    beside form was the wider one and went red. It is not. §750 pads a stacked
    limit box by half the operator's italic correction on each side, and the
    contour integral's italic correction is large enough that **stacking makes it
    5.5 px wider, not narrower**. The summation in the entry above goes the other
    way. So box width does not discriminate here at all, and where the script
    landed does: under the operator and far down, or out to its right and back up.
    """
    default = _set([op("∮", sub=ord_("γ"))], fonts, Style.DISPLAY)
    overridden = _set([op("∮", sub=ord_("γ"), limits=Limits.NO_LIMITS)], fonts, Style.DISPLAY)
    stacked_op, stacked_script = _glyphs(default, fonts.measure)
    beside_op, beside_script = _glyphs(overridden, fonts.measure)
    # Only the script moved: same operator glyph, same size, same origin.
    assert (stacked_op.codepoint, stacked_op.font, stacked_op.x, stacked_op.y) == (
        beside_op.codepoint,
        beside_op.font,
        beside_op.x,
        beside_op.y,
    )
    assert beside_script.x > stacked_script.x
    assert beside_script.y < stacked_script.y
    assert overridden.depth < default.depth


def test_the_cauchy_entry_is_the_one_that_carries_the_override(
    gallery: Gallery, fonts: MathFonts
) -> None:
    """
    The rule above, checked on the entry that claims it, not on a fresh fixture.

    The isolated test proves the flag has a visible effect. It does **not** prove
    the shipped formula uses it: removing `Limits.NO_LIMITS` from the `cauchy`
    definition left every other test in this file green, which is the same family
    of hole ablation found in the towers. So this rebuilds the entry's own items
    with the flag dropped and requires the shipped panel to differ from that and
    to match the overridden one -- geometrically, through the box, so it is not
    satisfied by a field that merely says `NO_LIMITS`.
    """
    panel = gallery.entry("cauchy").panels[0]
    without = [
        (
            replace(item, limits=Limits.DEFAULT)
            if isinstance(item, Atom) and item.limits is Limits.NO_LIMITS
            else item
        )
        for item in panel.items
    ]
    assert without != list(panel.items), "the cauchy entry no longer sets NO_LIMITS"
    relaxed = _set(without, fonts)
    assert relaxed.depth > panel.box.depth
    assert _set(list(panel.items), fonts).depth == panel.box.depth


# ----------------------------------------------------------------------
# Glyph coverage, in both faces
# ----------------------------------------------------------------------


def test_no_entry_names_a_codepoint_the_math_face_lacks(bundled_fonts: Path) -> None:
    """
    Every formula in `ENTRIES` is fully covered by Latin Modern Math.
    """
    assert missing_glyphs() == ()


def test_a_codepoint_the_math_face_lacks_is_reported(bundled_fonts: Path) -> None:
    """
    The control for the test above, and the reason it is not vacuous.

    Without it, "nothing is missing" would pass for a coverage check that always
    returned an empty tuple. `U+0127` is a real hole in this font -- the near
    neighbour of the `U+210F` that `schrodinger` uses, which is why the formula
    uses the one it does.
    """
    assert fontlib.glyph_name(Face.MATH, HBAR_WITH_STROKE) == ".notdef"
    assert missing_codepoints([ord_(chr(HBAR_WITH_STROKE))]) == (HBAR_WITH_STROKE,)
    assert missing_codepoints([ord_("ℏ")]) == ()


def test_every_caption_is_set_only_in_glyphs_its_own_faces_have(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    A caption is prose, and the prose faces are not the math face.

    This is the test that would have caught the defect it was written for: the
    first `cauchy` caption quoted the contour-integral sign in a code span, so the
    tab drew every formula correctly and reported one glyph with no raster from a
    *caption*. Nothing else in the suite looked there.

    Composed through the real markdown path and walked for `CharNode`s, so it sees
    the face each run was actually assigned -- checking the source string against
    one face would miss exactly the code-span case that broke.
    """
    measure = char_measure(fontlib_metrics)
    absent: list[tuple[str, str, str]] = []
    for entry in ENTRIES:
        document = build_document(entry.caption, theme, fontlib_metrics)
        box = compose_blocks(document.blocks, theme, MEASURE, measure)
        for node in _chars(box):
            face = parse_font_key(node.font).face
            if fontlib.glyph_name(face, node.codepoint) == ".notdef":
                absent.append((entry.key, face.value, chr(node.codepoint)))
    assert absent == []


def test_a_caption_quoting_the_contour_integral_would_be_caught(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    The control for the caption test: the exact prose that broke, still broken.

    Both prose faces genuinely lack `U+222E`, so the check above is looking at
    something. Without this, a caption test whose face lookup silently succeeded
    for everything would read as a pass.
    """
    assert fontlib.glyph_name(Face.PROSE, CONTOUR_INTEGRAL) == ".notdef"
    assert fontlib.glyph_name(Face.CODE, CONTOUR_INTEGRAL) == ".notdef"
    measure = char_measure(fontlib_metrics)
    document = build_document("keeps the contour beside the ∮ in display", theme, fontlib_metrics)
    box = compose_blocks(document.blocks, theme, MEASURE, measure)
    assert any(node.codepoint == CONTOUR_INTEGRAL for node in _chars(box))


def _chars(box: Box) -> list[CharNode]:
    """
    Every `CharNode` in a packed box, recursively.
    """
    found: list[CharNode] = []
    for node in box.contents:
        if isinstance(node, CharNode):
            found.append(node)
        elif isinstance(node, Box):
            found.extend(_chars(node))
    return found


# ----------------------------------------------------------------------
# The built page
# ----------------------------------------------------------------------


def test_a_label_row_uses_the_same_column_grid_as_its_formula_row(gallery: Gallery) -> None:
    """
    The claim `Panel.column` exists to make true, checked on the packed rows.

    Not asserted by reading `Panel.column` back: that would pass for a build which
    computed the grid correctly and then ignored it when packing, and that is
    exactly the mistake available here -- `_columns` takes the boxes and the panels
    as two arguments and could quietly use the boxes' natural widths instead. So
    this compares the two rows to **each other**. If they agree column for column,
    a label is over the panel it names, whatever the grid was.

    `Entry.grid` walks the row's own children, so the two sides of the equality
    come from two separately packed hboxes rather than from one shared number.
    """
    checked = 0
    for entry in gallery.entries:
        if entry.labels is None:
            continue
        formulae = entry.grid(entry.formulae)
        labels = entry.grid(entry.labels)
        assert len(formulae) == len(entry.panels), entry.key
        assert formulae == labels, entry.key
        assert entry.formulae.width == entry.labels.width
        checked += 1
    assert checked >= 4, "the comparison entries stopped carrying labels"


def test_a_column_is_wide_enough_for_both_the_formula_and_its_label(gallery: Gallery) -> None:
    """
    The grid is the wider of the two, so neither row overfulls its own column.

    Without this the test above is satisfied by any grid the two rows happen to
    share, including one narrower than the formulae in it -- **and by one sized
    from the formulae alone, which is the mistake that was actually available.**
    A column taken as `box.width` keeps both rows on the same grid and simply
    spills every label that is wider than the formula it names. Ablation caught
    that; the `label_width` half of the assertion below is what closes it.
    """
    for entry in gallery.entries:
        if entry.labels is None:
            continue
        for column, panel, label in zip(
            entry.grid(entry.formulae),
            entry.panels,
            entry.grid(entry.labels),
            strict=True,
        ):
            assert column >= panel.box.width, entry.key
            assert column >= panel.label_width, entry.key
            assert column == label


def test_at_least_one_label_is_wider_than_the_formula_it_names(gallery: Gallery) -> None:
    """
    The fixture check behind the `label_width` half of the test above.

    If every label were narrower than its formula the `max` in the column would
    never be exercised and the assertion would hold for a builder that ignored the
    label entirely. `operator-style` is the case: "display style" sets at about
    90 px and the display sigma is about 49 px wide.
    """
    wider = [
        (entry.key, panel.label)
        for entry in gallery.entries
        for panel in entry.panels
        if panel.label_width > panel.box.width
    ]
    assert wider, "no label is wider than its formula, so the column max is untested"


def test_the_two_halves_of_the_first_entry_are_different_widths(gallery: Gallery) -> None:
    """
    The fixture check behind the test above.

    Centring a label under a panel is only a claim when the panels differ in width;
    two equal-width panels would agree under any packing at all. They differ here
    by 24 px in the very first entry, which is why that one is the discriminating
    case and why the test above would be worth little without this one.
    """
    display, text = gallery.entry("operator-style").panels
    assert display.box.width != text.box.width
    for panel in gallery.entry("operator-style").panels:
        assert panel.column >= panel.box.width


def test_the_gallery_is_packed_to_the_measure_it_was_asked_for(gallery: Gallery) -> None:
    """
    Every plate shares a left edge, and the page is as wide as the prose measure.

    `Gallery.box.width` may exceed `width` when a formula is wider than the prose
    -- the tab grows the sheet for that -- and with the shipped entries at
    `FORMULA_PX` it does not, at the measure the demo actually sets.
    """
    assert gallery.width == MEASURE
    assert gallery.box.width == MEASURE
    for entry in gallery.entries:
        assert entry.box.width == MEASURE


def test_rebuilding_at_a_narrower_measure_still_covers_every_formula(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    At a measure narrower than the widest formula the sheet grows rather than clips.

    250 px is narrower than `schrodinger` at 357 px, so this exercises the branch
    the default never reaches. `hpack`'s two `hss` glues make an over-wide formula
    overfull symmetrically, and `Gallery.box.width` reports it so the caller can
    widen the page.
    """
    narrow = build_gallery(theme, sp_from_px(250.0), fontlib_metrics)
    assert narrow.box.width > narrow.width
    widest = max(panel.box.width for entry in narrow.entries for panel in entry.panels)
    assert narrow.box.width >= widest


def test_a_row_of_panels_is_centred_on_the_page_and_in_its_column(gallery: Gallery) -> None:
    """
    Both centrings at once, to the scaled point, and neither is otherwise checked.

    `_centred` is used twice per row -- once to put the row on the page and once to
    put each panel in its column -- and an earlier draft of this file could not see
    either. Replacing both `hss` pairs with a single trailing one left every other
    test in the file green while every formula slid to the left margin. Found by
    ablation, which is the only thing that would have found it.

    The expected x is arithmetic, not a fitted constant: half the page surplus,
    plus half the column surplus, plus wherever the first glyph sits inside its own
    panel box. Two scaled points of slack, and two only -- one per `_centred` call
    in the chain, because `hpack` sets two `hss` glues from a surplus that is
    sometimes odd. That is 2/65536 of a point, against a left-aligned row which
    misses by half the page.
    """
    measure = char_measure(fontlib_metrics)
    for entry in gallery.entries:
        drawn = _glyphs(entry.box, measure)
        leftmost = min(glyph.x for glyph in drawn if parse_font_key(glyph.font).face is Face.MATH)
        first = entry.panels[0]
        inside = min(glyph.x for glyph in _glyphs(first.box, measure))
        page_surplus = (entry.box.width - entry.formulae.width) // 2
        column_surplus = (first.column - first.box.width) // 2
        assert abs(leftmost - (page_surplus + column_surplus + inside)) <= 2, entry.key
        assert page_surplus > 0, f"{entry.key} fills the page, so centring is untested here"


# ----------------------------------------------------------------------
# Variables are set in math italic, and one letter is not where it should be
# ----------------------------------------------------------------------


ITALIC_H_HOLE = 0x1D455
"""
Where the math-italic `h` would be if Unicode had put it there. It is unassigned.
"""


def test_the_unassigned_italic_h_is_really_unassigned_in_this_font(
    bundled_fonts: Path,
) -> None:
    """
    The control for `italic`'s exception table, and the reason that table exists.

    `U+1D455` is the hole Unicode left in the Mathematical Italic block because
    `U+210E PLANCK CONSTANT` already carried the italic `h`. Arithmetic alone --
    `0x1D44E + (c - 'a')` -- lands there and Latin Modern Math has nothing at it.
    Without this test `italic` could lose the exception and only a formula
    containing an `h` would notice, silently, on screen.
    """
    assert fontlib.glyph_name(Face.MATH, ITALIC_H_HOLE) == ".notdef"
    assert fontlib.glyph_name(Face.MATH, 0x210E) != ".notdef"
    assert italic("h") == "ℎ"
    assert ord(italic("g")) == 0x1D454
    assert ord(italic("i")) == 0x1D456


def test_italic_maps_letters_and_leaves_everything_else_alone(bundled_fonts: Path) -> None:
    """
    Letters slant, digits and operators do not, and nothing maps to a hole.

    The second half is what makes the first half safe: a mapping that produced a
    codepoint this font lacks would put an invisible glyph in a formula, which is
    the failure this whole exception table exists to prevent.
    """
    assert italic("2") == "2"
    assert italic("∇∑∮∞()=+") == "∇∑∮∞()=+"
    # The partial-differential sign has an italic form of its own and takes it;
    # nabla does not and keeps the upright one. Both are in the exception table's
    # blast radius and neither is a letter, so nothing else here covers them.
    assert ord(italic("∂")) == 0x1D715
    assert ord(italic("∇")) == 0x2207
    # Upper-case Greek is upright in TeX, so it is deliberately not mapped.
    assert italic("Σ") == "Σ"
    assert italic("σ") != "σ"
    for character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
        mapped = italic(character)
        assert mapped != character, character
        assert fontlib.glyph_name(Face.MATH, ord(mapped)) != ".notdef", character
    for character in "αβγδεζηθικλμνξοπρστυφχψω":
        assert fontlib.glyph_name(Face.MATH, ord(italic(character))) != ".notdef", character


def test_every_letter_in_every_formula_is_set_in_math_italic(gallery: Gallery) -> None:
    """
    No variable anywhere in the gallery is left upright.

    Upright is not a neutral default here -- it is the form TeX reserves for an
    operator name, so an upright `x` beside an italic one reads as two different
    things. The only ASCII letters allowed through are the ones inside an operator
    glyph, and there are none: every letter in these nine formulae is a variable.

    Written as "no plain ASCII letter reaches a panel", which is falsifiable by a
    single `ord_("x")` slipping back into `ENTRIES`.
    """
    upright = {
        (entry.key, chr(code))
        for entry in gallery.entries
        for panel in entry.panels
        for code in codepoints(panel.items)
        if (chr(code).isalpha() and code < 0x2000) or code == 0x2202
    }
    assert upright == set()


# ----------------------------------------------------------------------
# The second build: nine unchanged, and two more held to the same standard
# ----------------------------------------------------------------------

NINE_PANELS_BEFORE_THE_SECOND_BUILD = {
    ("operator-style", 0): "1b6c2ddeac0c4e03",
    ("operator-style", 1): "72714c302ec47da3",
    ("euler", 0): "7177cd1c70d5279d",
    ("schrodinger", 0): "f451e1a3c66288fd",
    ("basel", 0): "ee80c8a651fcce9d",
    ("cauchy", 0): "ea41e046a8e3ebc1",
    ("continued-fraction", 0): "89f72ebca1be29bc",
    ("script-towers", 0): "5f71271f69e6cbf3",
    ("script-towers", 1): "7b961fa297fd225d",
    ("atom-classes", 0): "f81f846340201f6a",
    ("atom-classes", 1): "922350c653e07bea",
    ("binary-or-not", 0): "bab29b3f3937136b",
    ("binary-or-not", 1): "f99fc9f331679cb1",
}
"""
The first sixteen hex digits of `sha256(repr(panel.box))` for every panel of the
nine, taken from the tree **before** the math engine gained radicals, sized
delimiters, spaces and prose.

A digest of a `repr` is a blunt instrument and is meant to be. The engine's first
pass, its second pass and `math_fonts` were all rewritten to carry the new items,
and "the existing formulae set byte for byte as they did" is a claim about every
node of every box, not about a width. Anything that moves one node of one of these
thirteen boxes fails here. If the move is intended, regenerate the table and say
why in the commit; if it is not, this is the only test that would have noticed.
"""


def _digest(box: Box) -> str:
    return hashlib.sha256(repr(box).encode()).hexdigest()[:16]


def test_the_nine_set_exactly_as_they_did_before_the_engine_grew(gallery: Gallery) -> None:
    now = {
        (entry.key, index): _digest(panel.box)
        for entry in gallery.entries
        for index, panel in enumerate(entry.panels)
    }
    assert now == NINE_PANELS_BEFORE_THE_SECOND_BUILD


def test_the_digest_is_looking_at_something(fonts: MathFonts) -> None:
    """
    The control: one scaled point of difference in one node changes the digest.
    """
    box = _set([var("a"), bin_("+"), var("b")], fonts)
    assert _digest(box) == _digest(_set([var("a"), bin_("+"), var("b")], fonts))
    assert _digest(box) != _digest(replace(box, width=box.width + 1))


def test_entries_is_the_nine_and_then_the_sized_two() -> None:
    r"""
    `ENTRIES` is what ships: `CLASSIC_ENTRIES`, then `SIZED_ENTRIES`, and nothing else.

    The two were held beside `ENTRIES` until `advtext.mathtext` could read
    `\sqrt` and `\left` (`tests/test_mathtext.py` writes every entry as a
    source). They are folded in now, and the default gallery has eleven plates.
    """
    assert [entry.key for entry in CLASSIC_ENTRIES] == [
        "operator-style",
        "euler",
        "schrodinger",
        "basel",
        "cauchy",
        "continued-fraction",
        "script-towers",
        "atom-classes",
        "binary-or-not",
    ]
    assert [entry.key for entry in SIZED_ENTRIES] == ["radical", "sized-delimiters"]
    assert ENTRIES == (*CLASSIC_ENTRIES, *SIZED_ENTRIES)
    assert len({entry.key for entry in ENTRIES}) == 11


def test_the_eleven_build_as_one_gallery_and_every_panel_sets_what_it_names(
    eleven: Gallery,
) -> None:
    """
    The anti-vacuity test again, over the two new plates as well.

    A radical names one character no field holds -- its surd -- and a sized
    delimiter is set as a variant of the one that was asked for, so this is also
    the check that `codepoints` counts both.
    """
    measure = char_measure(fontlib_metrics)
    assert [entry.key for entry in eleven.entries][-2:] == ["radical", "sized-delimiters"]
    assert len(eleven.entries) == 11
    assert eleven.missing == ()
    for entry in eleven.entries[-2:]:
        assert entry.missing == ()
        for panel in entry.panels:
            wanted = codepoints(panel.items)
            drawn = _glyphs(panel.box, measure)
            assert len(drawn) == len(wanted) > 0, entry.key
            assert all(parse_font_key(key).face is Face.MATH for key in char_fonts(panel.box))


def test_the_two_new_plates_do_not_move_the_nine_above_them(
    gallery: Gallery, eleven: Gallery
) -> None:
    for before, after in zip(gallery.entries, eleven.entries, strict=False):
        assert before.box == after.box
    assert eleven.box.width == gallery.box.width


def test_the_two_radicals_are_set_with_different_outlines(eleven: Gallery) -> None:
    """
    The claim the `radical` plate makes: chosen from the font, not stretched.
    """
    one_line, fraction = eleven.entry("radical").panels
    surds = [
        fontlib.glyph_name(Face.MATH, _chars(panel.box)[0].codepoint)
        for panel in (one_line, fraction)
    ]
    assert surds == ["radical.v1", "radical.v3"]
    # One rule over one line; over a fraction two, the vinculum and the bar, and
    # they are the same width because the radicand is the fraction and nothing else.
    measure = char_measure(fontlib_metrics)
    assert len(_rules(one_line.box, measure)) == 1
    over, bar = sorted(_rules(fraction.box, measure), key=lambda rule: rule.y)
    assert over.width == bar.width > 0
    # The vinculum starts where the surd's advance ends, and the surd is first.
    surd = _glyphs(fraction.box, measure)[0]
    assert surd.x == 0 and over.x == round(
        fontlib.math_metrics(float(sp_from_px(FORMULA_PX))).advance(surd.codepoint)
    )


def test_the_fitted_parentheses_are_one_larger_outline_on_both_sides(eleven: Gallery) -> None:
    """
    The claim the `sized-delimiters` plate makes, and its control beside it.
    """
    fixed, fitted = eleven.entry("sized-delimiters").panels
    names = [fontlib.glyph_name(Face.MATH, node.codepoint) for node in _chars(fixed.box)]
    assert (names[0], names[-1]) == ("parenleft", "parenright")
    names = [fontlib.glyph_name(Face.MATH, node.codepoint) for node in _chars(fitted.box)]
    assert (names[0], names[-1]) == ("parenleft.v6", "parenright.v6")
    # Same fraction between them: the middles are the same characters.
    assert [n.codepoint for n in _chars(fixed.box)[1:-1]] == [
        n.codepoint for n in _chars(fitted.box)[1:-1]
    ]
    assert fitted.box.depth > fixed.box.depth
    assert fitted.box.width > fixed.box.width


def test_the_two_new_captions_are_set_only_in_glyphs_their_faces_have(
    bundled_fonts: Path, theme: Theme
) -> None:
    measure = char_measure(fontlib_metrics)
    for entry in SIZED_ENTRIES:
        document = build_document(entry.caption, theme, fontlib_metrics)
        box = compose_blocks(document.blocks, theme, MEASURE, measure)
        nodes = _chars(box)
        assert nodes
        for node in nodes:
            face = parse_font_key(node.font).face
            assert fontlib.glyph_name(face, node.codepoint) != ".notdef", (entry.key, node)


def test_every_letter_in_the_two_new_plates_is_math_italic_too(eleven: Gallery) -> None:
    upright = {
        (entry.key, chr(code))
        for entry in eleven.entries[-2:]
        for panel in entry.panels
        for code in codepoints(panel.items)
        if (chr(code).isalpha() and code < 0x2000) or code == 0x2202
    }
    assert upright == set()


def test_codepoints_names_a_surd_and_a_delimiter_and_no_prose_or_space() -> None:
    from advtext.math import THIN_SPACE, delimited, prose_text, radical

    items = [radical("x"), THIN_SPACE, delimited("(", "y", None), prose_text("if")]
    assert [chr(code) for code in codepoints(items)] == ["√", "x", "(", "y"]

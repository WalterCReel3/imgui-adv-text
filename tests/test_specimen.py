r"""
The font specimen, tested against the real fonts rather than against a fake.

**There is no fake measure in this file, and that is the design.** `docs/status.md`
§5 names a uniform fake as the first of three families of vacuous tests found in
this tree: a fixture that gave every codepoint identical extents made "line height,
not ink" unfalsifiable, because under such a measure the two quantities the test
separated were the same number. A specimen is *entirely* a claim that six faces
differ, so a fake that made them agree would not weaken these tests -- it would
invert every one of them into a tautology. The fonts are present, the rest of the
suite uses them, and `bundled_fonts` skips when they are not.

The two places a stub appears are `_raising_for`, which wraps the **real** resolver
and makes exactly one face fail, so the degradation tests still run against real
metrics for every other face.

Three tests here are controls rather than assertions about the code, and they are
the ones to keep if this file is ever trimmed:

- `test_a_shorter_specimen_line_would_not_separate_the_faces` sets the same six
  faces in a phrase that leaves the regular face and the bold italic a tenth of a
  pixel apart. It exists because the discriminating power of
  `test_the_six_faces_come_out_six_distinguishable_widths` is a property of
  `PANGRAM`, not of `build_specimen`, and a later edit to that constant could
  quietly remove it.
- `test_the_code_and_math_faces_kern_nothing_at_all` is why `KERN_FACE` is a prose
  face. Without it, "the kerning section demonstrates kerning" would hold for a
  section whose two columns were identical.
- `test_a_positive_kern_is_in_the_demonstration` rules out the reading a reader
  would otherwise take away, which is that kerning only tightens.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest

from advtext import fontlib
from advtext.fontmetrics import Face, FontMetrics
from advtext.nodes import Box, CharNode, FontKey, Node
from advtext.pack import CharMeasure
from advtext.shipout import Glyph, Point, ship
from advtext.style import (
    BODY_SIZE_PX,
    TYPE_SCALE_RATIO,
    BlockKind,
    MetricsResolver,
    Theme,
    char_measure,
    font_key,
    fontlib_metrics,
    parse_font_key,
)
from advtext.ui.specimen import (
    FACE_LABELS,
    KERN_FACE,
    KERN_PAIRS,
    KERN_PX,
    LABEL_PX,
    PANGRAM,
    SPECIMEN_PX,
    Specimen,
    SpecimenRow,
    _set,
    build_specimen,
    ladder_sizes_px,
)
from advtext.units import Scaled, px_from_sp, sp_from_px

# Wide enough that every note breaks over two or three lines and no specimen row
# overflows: the widest row is the monospace one at 590 px including the gutter.
MEASURE = sp_from_px(760.0)

# A phrase short enough that the six faces nearly agree. The control below turns
# that into a measurement rather than leaving it as a remark in a docstring.
SHORT_LINE = "Sphinx of black quartz, judge my vow."


@pytest.fixture(scope="session")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="session")
def specimen(bundled_fonts: Path, theme: Theme) -> Specimen:
    """
    The real specimen, built once: every test below reads the same one.
    """
    return build_specimen(theme, MEASURE, fontlib_metrics)


def _rows(specimen: Specimen, title_starts: str) -> tuple[SpecimenRow, ...]:
    """
    One section's rows, found by the start of its title.
    """
    for section in specimen.sections:
        if section.title.startswith(title_starts):
            return section.rows
    raise AssertionError(f"no section titled {title_starts!r} in {[s.title for s in specimen]}")


def _chars(node: Node) -> Iterator[CharNode]:
    """
    Every `CharNode` in a packed tree, in reading order.
    """
    if isinstance(node, CharNode):
        yield node
    elif isinstance(node, Box):
        for child in node.contents:
            yield from _chars(child)


def _widths(text: str, size: Scaled, measure: CharMeasure) -> dict[Face, Scaled]:
    """
    One line's set width in each of the six faces, kerning included.
    """
    return {
        face: _set(text, face, size, fontlib.metrics(face, float(size)), measure).width
        for face in FACE_LABELS
    }


def _closest(widths: dict[Face, Scaled]) -> Scaled:
    """
    The smallest gap between any two of the six set widths.
    """
    ordered = sorted(widths.values())
    return min(b - a for a, b in pairwise(ordered))


def _raising_for(absent: Face) -> MetricsResolver:
    """
    The real resolver, except that one face raises.

    A wrapper rather than a fake so that every *other* face still comes back with
    real metrics: a degradation test whose surviving rows were measured by a stub
    would prove that the stub survived.
    """

    def resolve(key: FontKey) -> FontMetrics:
        if parse_font_key(key).face is absent:
            raise fontlib.MissingFontError(f"pretending {absent.value} is not installed")
        return fontlib_metrics(key)

    return resolve


# ----------------------------------------------------------------------
# The six faces, and whether they are actually six


def test_the_six_faces_come_out_six_distinguishable_widths(specimen: Specimen) -> None:
    """
    The whole specimen rests on this. Six rows, six widths, none of them a near-tie.

    A near-tie is the failure worth naming: if two `Face` members resolved to the
    same file -- a plausible typo in `advtext.fontlib._FONT_FILES` -- the rows would
    still render, still look like a specimen, and still pass a test that only
    counted them. The threshold is a whole pixel, which is what a reader can see.
    """
    rows = _rows(specimen, "The six faces")
    assert len(rows) == len(FACE_LABELS) == 6
    assert [row.face for row in rows] == list(FACE_LABELS)

    widths = {row.face: row.set_width for row in rows}
    assert len(set(widths.values())) == 6
    assert px_from_sp(_closest(widths)) > 1.0


def test_every_section_carries_a_heading_a_composed_note_and_its_rows(
    specimen: Specimen,
) -> None:
    """
    The healthy case, against which the degradation tests below mean something.

    Three sections, each with prose that actually broke to more than one line at
    this measure, and only the kerning section with a column header. Without this
    the "the note came back empty" assertion further down would also pass for a
    build whose notes were never composed at all.
    """
    assert [section.title for section in specimen.sections] == [
        "The six faces",
        "A size ladder",
        "Kerning, which the widget underneath cannot do",
    ]
    for section in specimen.sections:
        assert section.rows
        assert section.note.height + section.note.depth > 0
    assert [section.header is not None for section in specimen.sections] == [False, False, True]


def test_a_shorter_specimen_line_would_not_separate_the_faces(bundled_fonts: Path) -> None:
    """
    The control: `PANGRAM`'s discriminating power is a property of the string.

    Set the same six faces in a shorter phrase and the closest two come within a
    tenth of a pixel -- so the test above would pass for a build in which two faces
    had silently collapsed onto one file. This is here so that shortening `PANGRAM`
    for looks breaks a test rather than quietly disarming one.
    """
    size = sp_from_px(SPECIMEN_PX)
    measure = char_measure(fontlib_metrics)
    assert px_from_sp(_closest(_widths(SHORT_LINE, size, measure))) < 0.2
    assert px_from_sp(_closest(_widths(PANGRAM, size, measure))) > 1.0


def test_bold_is_wider_than_regular_and_italic_is_narrower(specimen: Specimen) -> None:
    """
    The specific difference the specimen claims for the four Roboto faces.

    Not merely "they differ": a test that only asserted difference would pass with
    the four faces shuffled. Weight adds width and the italic takes it away, in both
    weights, which is a statement about Roboto that a wrong mapping violates.
    """
    width = {row.face: row.set_width for row in _rows(specimen, "The six faces")}
    assert width[Face.PROSE_BOLD] > width[Face.PROSE]
    assert width[Face.PROSE_ITALIC] < width[Face.PROSE]
    assert width[Face.PROSE_BOLD_ITALIC] > width[Face.PROSE_ITALIC]
    assert width[Face.PROSE_BOLD_ITALIC] < width[Face.PROSE_BOLD]


def test_the_four_roboto_faces_share_an_x_height_so_set_width_is_what_separates_them(
    bundled_fonts: Path,
) -> None:
    """
    Why the claim above is about *width* and not about x-height.

    The module docstring says the four share an x-height, an ascent and a descent to
    the font unit. If that ever stopped being true the specimen would be separating
    them on something it does not say it separates them on, and the note under the
    section heading would be wrong.
    """
    size = sp_from_px(SPECIMEN_PX)
    roboto = (Face.PROSE, Face.PROSE_BOLD, Face.PROSE_ITALIC, Face.PROSE_BOLD_ITALIC)
    metrics = {face: fontlib.metrics(face, float(size)) for face in Face}
    assert len({metrics[face].x_height for face in roboto}) == 1
    assert len({metrics[face].ascent for face in roboto}) == 1
    assert len({metrics[face].descent for face in roboto}) == 1

    # And the two non-Roboto faces do separate on x-height, which is the figure
    # `advtext.style`'s docstring quotes to argue code is set at the body size.
    em = metrics[Face.PROSE].em
    assert metrics[Face.PROSE].x_height / em == pytest.approx(0.528, abs=0.001)
    assert metrics[Face.CODE].x_height / em == pytest.approx(0.457, abs=0.001)
    assert metrics[Face.MATH].x_height / em == pytest.approx(0.431, abs=0.001)


def test_the_monospace_row_is_the_only_one_set_on_a_single_advance(bundled_fonts: Path) -> None:
    """
    A face-specific property the specimen shows and no width comparison can fake.

    Every glyph of the pangram has one advance in Inconsolata and several in every
    other face. A row that looked monospaced because it happened to be wider would
    fail this; a row that really is Inconsolata cannot.
    """
    size = sp_from_px(SPECIMEN_PX)
    letters = {ord(character) for character in PANGRAM if character != " "}
    advances = {
        face: {fontlib.metrics(face, float(size)).advance(cp) for cp in letters} for face in Face
    }
    assert len(advances[Face.CODE]) == 1
    for face in Face:
        if face is not Face.CODE:
            assert len(advances[face]) > 1


def test_every_row_of_a_section_tiles_on_one_baseline_rhythm(specimen: Specimen) -> None:
    """
    The strut does its job: rows of one size occupy identical bands.

    `advtext.style.Strut` exists so a line's height is its leading rather than the
    ink that happened to land on it. The pangram has ascenders in every face and
    descenders in every face, so without the strut the six rows would come out with
    six slightly different heights and the gaps between them would waver.
    """
    for title in ("The six faces", "Kerning"):
        rows = _rows(specimen, title)
        assert len({row.box.height for row in rows}) == 1
        assert len({row.box.depth for row in rows}) == 1


# ----------------------------------------------------------------------
# Kerning


def test_every_kerned_pair_is_its_unkerned_setting_plus_exactly_its_kern(
    specimen: Specimen,
) -> None:
    """
    The demonstration, as an equality rather than as an inequality.

    `kerned == unkerned + kern`, to the scaled point, for all seven pairs. An
    inequality (`kerned < unkerned`) would also pass for a build that dropped the
    kern nodes and shrank a glue instead, which is a different thing entirely and
    would move the glyphs to the wrong places.
    """
    rows = _rows(specimen, "Kerning")
    assert len(rows) == len(KERN_PAIRS)
    for row in rows:
        pair = row.pair
        assert pair is not None
        assert pair.kern != 0
        assert pair.kerned == pair.unkerned + pair.kern


def test_both_kerning_columns_start_at_the_same_x_on_every_row(specimen: Specimen) -> None:
    """
    The comparison is only a comparison if the two settings share a left edge.

    A row is a gutter, then the kerned setting in a column of one fixed width, then
    the unkerned setting. So `box.width - unkerned` is the same constant on all
    seven rows, and it stops being constant the moment the kerned setting is packed
    at its natural width instead -- at which point the right-hand column staggers
    down the page by the kern of each pair and the reader is comparing the wrong
    two things.
    """
    offsets = set()
    for row in _rows(specimen, "Kerning"):
        assert row.pair is not None
        offsets.add(row.box.width - row.pair.unkerned)
    assert len(offsets) == 1
    assert offsets.pop() > specimen.gutter


def test_a_positive_kern_is_in_the_demonstration(specimen: Specimen) -> None:
    """
    `rt` is why "kerning pulls letters together" is not the lesson on offer.

    Six of the seven pairs tighten and exactly one loosens. Both counts are asserted:
    a list of all-negative kerns would teach the wrong rule, and a list of mostly
    positive ones would not look like kerning at all.
    """
    pairs = [row.pair for row in _rows(specimen, "Kerning")]
    assert all(pair is not None for pair in pairs)
    positive = [pair for pair in pairs if pair is not None and pair.kern > 0]
    negative = [pair for pair in pairs if pair is not None and pair.kern < 0]
    assert [(pair.left, pair.right) for pair in positive] == [("r", "t")]
    assert len(negative) == len(KERN_PAIRS) - 1
    # And the loosening is visible rather than notional at the size it is set at.
    assert px_from_sp(positive[0].kern) > 1.0


def test_the_code_and_math_faces_kern_nothing_at_all(bundled_fonts: Path) -> None:
    """
    Why `KERN_FACE` is a prose face, and why the section drops rather than degrades.

    Of the six faces only the four Roboto ones carry a `kern` feature --
    `advtext.fontlib` says so in a comment and this is the measurement behind it.
    Setting the demonstration in Inconsolata or Latin Modern Math would produce two
    identical columns, which reads as a broken demonstration rather than as a fact
    about those faces.
    """
    size = sp_from_px(KERN_PX)
    for face in Face:
        kerns = {
            round(fontlib.metrics(face, float(size)).kern(ord(left), ord(right)))
            for left, right in KERN_PAIRS
        }
        if face in (Face.CODE, Face.MATH):
            assert kerns == {0}
        else:
            assert 0 not in kerns
    assert KERN_FACE not in (Face.CODE, Face.MATH)


# ----------------------------------------------------------------------
# The gutter, the ladder, and what the boxes actually contain


def test_the_gutter_is_measured_from_the_widest_label_and_every_label_fits(
    specimen: Specimen, theme: Theme
) -> None:
    """
    `advtext.style`'s `WIDEST_MARKER_EM` argument, applied to this document.

    Two halves and both matter. Every label plus its gap fits the gutter, so no
    label overfulls into the sample it names; and the gutter is *exactly* the widest
    label plus the gap, so it was measured rather than padded to a round number that
    the next label happens to fit under.
    """
    labels = [row.label_width for section in specimen.sections for row in section.rows]
    assert labels
    for width in labels:
        assert width + theme.marker_gap <= specimen.gutter
    assert max(labels) + theme.marker_gap == specimen.gutter


def test_the_widest_label_does_not_touch_the_sample_it_names(
    specimen: Specimen, theme: Theme
) -> None:
    """
    A measured gutter is not enough: the gap has to be *inside* it.

    This is a real defect that shipped in the first draft and that the test above
    could not see. The gutter really was the widest label plus `marker_gap`, and
    the label really did fit -- but the label was right-aligned against the
    gutter's right edge, so the widest one ended exactly where its pangram began.
    Every arithmetic assertion passed and a screenshot showed "Bold Italic" welded
    to its own specimen line.

    So this one ships the row and measures the ink: the right-hand edge of the last
    label glyph, advance included, against the point the sample starts at.
    """
    row = max(
        (r for section in specimen.sections for r in section.rows), key=lambda r: r.label_width
    )
    label_key = font_key(Face.CODE, sp_from_px(LABEL_PX, theme.px_per_inch))
    cmds = ship(row.box, Point(0, row.box.height), measure=char_measure(fontlib_metrics))

    def right_edge(glyph: Glyph) -> float:
        spec = parse_font_key(glyph.font)
        return glyph.x + fontlib.metrics(spec.face, float(spec.size)).advance(glyph.codepoint)

    labels = [cmd for cmd in cmds if isinstance(cmd, Glyph) and cmd.font == label_key]
    assert labels, "the widest-labelled row is not carrying its label"
    assert max(right_edge(glyph) for glyph in labels) <= specimen.gutter - theme.marker_gap


def test_the_size_ladder_is_the_theme_s_own_modular_scale(theme: Theme) -> None:
    """
    The rungs are generated from `TYPE_SCALE_RATIO`, not listed.

    So the top rung is the size a level-one heading is set at and the third is the
    body size. A hand-picked ladder would drift from the document the moment the
    ratio changed, and the section's note claims it does not.
    """
    ladder = ladder_sizes_px(BODY_SIZE_PX)
    for lower, upper in pairwise(ladder):
        assert upper / lower == pytest.approx(TYPE_SCALE_RATIO)
    assert BODY_SIZE_PX in ladder
    assert sp_from_px(ladder[-1], theme.px_per_inch) == theme.style(BlockKind.HEADING_1).font.size


def test_every_character_in_a_row_is_set_in_that_row_s_face_or_in_the_label_face(
    specimen: Specimen, theme: Theme
) -> None:
    """
    A row is not merely *labelled* with a face; it is set in one.

    The gutter label is the one exception and it is a fixed face at a fixed size, so
    the two sets are disjoint and this stays a real constraint. Without it a builder
    that set all six rows in `Face.PROSE` and varied only the label would produce a
    specimen that is wrong in exactly the way a specimen must not be.
    """
    label_size = sp_from_px(LABEL_PX, theme.px_per_inch)
    for section in specimen.sections:
        for row in section.rows:
            expected = {font_key(row.face, row.size), font_key(Face.CODE, label_size)}
            found = {char.font for char in _chars(row.box)}
            assert found
            assert found <= expected
            # The sample itself is present, not only the label.
            assert font_key(row.face, row.size) in found


def test_no_character_the_specimen_sets_is_missing_from_the_face_it_is_set_in(
    specimen: Specimen,
) -> None:
    """
    Every glyph is real, including in Latin Modern Math.

    `advtext.fontlib` substitutes `.notdef` for a codepoint a face does not map, and
    it does it silently -- returning a zero advance instead would make missing text
    vanish, so the choice is deliberate and the cost is that a specimen can be full
    of tofu with nothing raised. The math face is the live risk: it is the only one
    of the six not designed for prose.
    """
    for section in specimen.sections:
        for row in section.rows:
            for char in _chars(row.box):
                spec = parse_font_key(char.font)
                metrics = fontlib.metrics(spec.face, float(spec.size))
                assert metrics.has(
                    char.codepoint
                ), f"{chr(char.codepoint)!r} is absent from {spec.face.value}"


def test_the_specimen_ships_with_every_glyph_inside_its_own_box(specimen: Specimen) -> None:
    """
    The packed box really contains what it says it contains.

    Shipping is what a backend does, and a glyph outside the box's extent is a
    negative kern or a shift that went the wrong way -- invisible to a width
    assertion, and on screen it is text sitting on top of the heading above it.
    """
    box = specimen.box
    cmds = ship(box, Point(0, box.height), measure=char_measure(fontlib_metrics))
    glyphs = [cmd for cmd in cmds if isinstance(cmd, Glyph)]
    assert len(glyphs) > 500
    for glyph in glyphs:
        assert 0 <= glyph.x <= box.width
        assert 0 <= glyph.y <= box.height + box.depth


# ----------------------------------------------------------------------
# Degrading when a face is not there


def test_a_face_that_does_not_resolve_costs_its_own_rows_and_nothing_else(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    `load_fonts`'s posture, one layer up: a font swap costs a row, not the tab.

    The bold face is dropped and everything else must survive -- including the
    kerning section, which is set in a face that is still there.
    """
    resolve = _raising_for(Face.PROSE_BOLD)
    built = build_specimen(theme, MEASURE, resolve)

    assert built.absent == (Face.PROSE_BOLD,)
    faces = [row.face for row in _rows(built, "The six faces")]
    assert Face.PROSE_BOLD not in faces
    assert len(faces) == 5
    assert len(_rows(built, "Kerning")) == len(KERN_PAIRS)
    assert len(_rows(built, "A size ladder")) == len(ladder_sizes_px(BODY_SIZE_PX))
    assert built.box.height + built.box.depth > 0

    # The captions go and the specimens stay, which is the right way round: every
    # section note is set with a bold heading over it, so losing the bold face
    # empties the prose of all three. This is the observable half of `_prose`'s
    # decision to return an empty box rather than let the exception out.
    assert all(section.note.height + section.note.depth == 0 for section in built.sections)


def test_losing_the_kerning_face_drops_the_kerning_section_rather_than_faking_it(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    No section at all, rather than two identical columns.

    Dropping `Face.PROSE` also empties the size ladder, which is set in it. The
    faces section keeps the other five, so the specimen is still a specimen.
    """
    resolve = _raising_for(Face.PROSE)
    built = build_specimen(theme, MEASURE, resolve)

    assert built.absent == (Face.PROSE,)
    assert not any(section.title.startswith("Kerning") for section in built.sections)
    assert _rows(built, "A size ladder") == ()
    assert len(_rows(built, "The six faces")) == 5


def test_a_specimen_with_no_fonts_at_all_is_empty_rather_than_a_traceback(
    bundled_fonts: Path, theme: Theme
) -> None:
    """
    The limit of the degradation: every face absent still returns a `Specimen`.

    Not a useful one -- there is nothing to show -- but a tab that renders an empty
    page beats a tab that raises during a frame, which in an immediate-mode UI takes
    the window with it.
    """

    def resolve(key: FontKey) -> FontMetrics:
        raise fontlib.MissingFontError("no fonts at all")

    built = build_specimen(theme, MEASURE, resolve)
    assert set(built.absent) == set(FACE_LABELS)
    assert all(section.rows == () for section in built.sections)

r"""
`Theme.build`'s parameters, the `Faces` table, and `Theme.face_for` on a monospace base.

Two kinds of claim are made here and they need different evidence.

**"The default did not move."** `Theme.build()` with no arguments must be the
theme it was before it took `faces` and `align`, and `Theme.face_for` must answer
as it did for every case the default theme can reach. Both are held against a
*transcription of the old code kept in this file* -- `_build_as_it_was` and
`_face_as_it_was` -- because a test that compared `Theme.build()` with
`Theme.build()` would pass whatever either returned. The transcriptions were
copied from `advtext/style.py` as it stood at commit `27b3b73`; if they are ever
"tidied" to call the new code they stop testing anything.

**"A host can now say what it could not."** An all-monospace ragged theme at a
host's font size is one call, and the document it sets contains no proportional
glyph. That is checked on *shipped material from real markdown* and not on the
theme's fields: `tests/test_bench_numbers.py` records that a theme whose every
`BlockStyle` said `Face.CODE` used to set Roboto anyway, so the fields were
never the evidence.

What nothing here can say is how any of it looks. The fonts imgui-bundle ships
include no bold monospace, so the "host's bold" in these tests is a copy of the
one Inconsolata weight under another name: it proves which file is read and that
the columns hold, and nothing about a real bold.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import fields, replace
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from advtext import fontlib
from advtext.backends.imgui_draw import baked_size_px
from advtext.fontmetrics import Face
from advtext.markdown import build_document
from advtext.nodes import CharNode, GlueSpec
from advtext.pack import InterlineSkip
from advtext.style import (
    BODY_SIZE_PX,
    DEFAULT_FACES,
    MARKER_GAP_EM,
    QUOTE_INDENT_EM,
    WIDEST_MARKER_EM,
    Align,
    BlockKind,
    BlockStyle,
    Emphasis,
    Faces,
    FontSpec,
    Spacing,
    Theme,
    font_key,
    fontlib_metrics,
    parse_font_key,
)
from advtext.units import DEFAULT_PX_PER_INCH, Scaled, px_from_sp, sp_from_px

EVERY_EMPHASIS = [
    Emphasis(bold=bold, italic=italic, code=code)
    for bold, italic, code in product((False, True), repeat=3)
]

RUNNING_TEXT = (
    BlockKind.PARAGRAPH,
    BlockKind.BULLET_ITEM,
    BlockKind.ORDERED_ITEM,
    BlockKind.QUOTE,
)
"""
The kinds `align` reaches. Everything else is ragged in every theme.
"""

MARKDOWN = """\
# A heading with `code` in it

Plain text, **bold text**, *italic text*, ***both at once*** and `a code span`,
then enough further words that the paragraph has to break onto a second line.

1. first item
2. second item with **bold**

> A quoted paragraph.

```
fenced = code
```

| a | b |
|---|---|
| 1 | **2** |
"""


# ----------------------------------------------------------------------
# The old code, transcribed. See the module docstring before editing.


def _leading_as_it_was(size: Scaled, ratio: float) -> InterlineSkip:
    return InterlineSkip(
        baselineskip=GlueSpec(width=round(size * ratio)),
        lineskip=GlueSpec(width=round(size * 0.1)),
        lineskiplimit=0,
    )


def _build_as_it_was(
    base_px: float = 16.0,
    px_per_inch: float = DEFAULT_PX_PER_INCH,
    spacing: Spacing = Spacing.EXTRA_SPACE_ONLY,
) -> Theme:
    """
    `Theme.build` at commit `27b3b73`, with its constants written out as numbers.

    The constants are literals on purpose -- 1.25, 0.5, 1.4, 1.5 -- so that a
    change to `TYPE_SCALE_RATIO` or `WIDEST_MARKER_EM` shows up here as a moved
    default rather than moving both sides together.
    """
    r = 1.25
    body = sp_from_px(base_px, px_per_inch)
    h3 = sp_from_px(base_px * r, px_per_inch)
    h2 = sp_from_px(base_px * r * r, px_per_inch)
    h1 = sp_from_px(base_px * r * r * r, px_per_inch)

    def heading(size: Scaled, above: float, below: float) -> BlockStyle:
        return BlockStyle(
            font=FontSpec(Face.PROSE_BOLD, size),
            interline=_leading_as_it_was(size, 1.15),
            align=Align.LEFT,
            space_above=round(size * above),
            space_below=round(size * below),
        )

    body_leading = _leading_as_it_was(body, 1.35)
    prose = FontSpec(Face.PROSE, body)
    styles = {
        BlockKind.HEADING_1: heading(h1, 1.0, 0.4),
        BlockKind.HEADING_2: heading(h2, 0.9, 0.35),
        BlockKind.HEADING_3: heading(h3, 0.8, 0.3),
        BlockKind.PARAGRAPH: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.JUSTIFY,
            space_below=round(body * 0.55),
        ),
        BlockKind.BULLET_ITEM: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.JUSTIFY,
            space_below=round(body * 0.2),
        ),
        BlockKind.ORDERED_ITEM: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.JUSTIFY,
            space_below=round(body * 0.2),
        ),
        BlockKind.QUOTE: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.JUSTIFY,
            space_above=round(body * 0.5),
            space_below=round(body * 0.5),
        ),
        BlockKind.CODE: BlockStyle(
            font=FontSpec(Face.CODE, body),
            interline=_leading_as_it_was(body, 1.25),
            align=Align.LEFT,
            space_above=round(body * 0.6),
            space_below=round(body * 0.6),
            left_indent=round(body * 1.0),
        ),
        BlockKind.RULE: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.LEFT,
            space_above=body,
            space_below=body,
        ),
        BlockKind.TABLE: BlockStyle(
            font=prose,
            interline=body_leading,
            align=Align.LEFT,
            space_above=round(body * 0.7),
            space_below=round(body * 0.7),
        ),
    }
    return Theme(
        blocks=styles,
        px_per_inch=px_per_inch,
        marker_gap=round(body * 0.5),
        list_indent=round(body * (1.4 + 0.5)),
        quote_indent=round(body * 1.5),
        rule_thickness=max(1, round(body * 0.06)),
        quote_rule_thickness=max(1, round(body * 0.15)),
        cell_padding=round(body * 0.5),
        table_rule_thickness=max(1, round(body * 0.06)),
        spacing=spacing,
    )


def _face_as_it_was(theme: Theme, kind: BlockKind, emphasis: Emphasis) -> Face:
    """
    `Theme.face_for` at commit `27b3b73`.
    """
    if emphasis.code:
        return Face.CODE
    base = theme.style(kind).font.face
    bold = emphasis.bold or base in (Face.PROSE_BOLD, Face.PROSE_BOLD_ITALIC)
    italic = emphasis.italic or base in (Face.PROSE_ITALIC, Face.PROSE_BOLD_ITALIC)
    if bold and italic:
        return Face.PROSE_BOLD_ITALIC
    if bold:
        return Face.PROSE_BOLD
    if italic:
        return Face.PROSE_ITALIC
    return Face.PROSE


# ----------------------------------------------------------------------
# The default did not move


@pytest.mark.parametrize(
    ("base_px", "px_per_inch", "spacing"),
    [
        (16.0, 96.0, Spacing.EXTRA_SPACE_ONLY),
        (16.0, 96.0, Spacing.NONFRENCH),
        (13.0, 96.0, Spacing.FRENCH),
        (16.0, 120.0, Spacing.EXTRA_SPACE_ONLY),
        (13.653333333333334, 96.0, Spacing.EXTRA_SPACE_ONLY),
    ],
)
def test_the_default_theme_is_field_for_field_the_theme_it_was(
    base_px: float, px_per_inch: float, spacing: Spacing
) -> None:
    """
    `Theme.build` with no new argument returns what it returned before it had any.

    Compared as whole dataclasses, so a field this test did not think of is
    still compared. The old theme was constructed without a `faces` field at
    all; that it equals the new one is also the statement that a `Theme` built
    by hand gets the default table. (`scripts/bench_draw.py` built its mono
    theme that way when this was written; it now calls `Theme.build` with
    `Faces.mono(...)`.)

    **Block kinds are compared over the ten that existed**, and the theme is
    then compared whole with those ten put in place of its own. A kind added
    later -- headings past the third are planned -- is a new key and not a
    moved default, and this test should not go red for it; any change to one of
    the ten, or to any other field, still does.
    """
    built = Theme.build(base_px, px_per_inch, spacing=spacing)
    was = _build_as_it_was(base_px, px_per_inch, spacing)
    assert len(was.blocks) == 10
    assert {kind: built.blocks[kind] for kind in was.blocks} == was.blocks
    assert replace(built, blocks=was.blocks) == was
    assert built.faces is DEFAULT_FACES


def test_the_constants_the_transcription_writes_out_are_still_the_module_s() -> None:
    """
    The literals in `_build_as_it_was` and the named constants are the same numbers.

    If one of these fails the default has been changed on purpose somewhere, and
    the test above is then failing for a reason worth reading rather than fixing.
    """
    assert (BODY_SIZE_PX, MARKER_GAP_EM, WIDEST_MARKER_EM, QUOTE_INDENT_EM) == (16.0, 0.5, 1.4, 1.5)


def test_every_face_the_default_theme_can_ask_for_is_the_face_it_asked_for_before() -> None:
    """
    `face_for` is unchanged wherever the default theme's own converter can reach.

    `advtext.markdown` calls `font_for` with the kind of a block of *text* --
    never `BlockKind.CODE`, whose lines are set from the style's font directly --
    so the reachable cases are the kinds whose base face is proportional, under
    every emphasis. That is every kind but the fenced block, by eight emphases.

    The one kind left out is the one that changed, and the next test is about it.
    """
    theme = Theme.build()
    compared = 0
    for kind, emphasis in product(BlockKind, EVERY_EMPHASIS):
        if theme.style(kind).font.face in theme.faces.monospace:
            continue
        assert theme.face_for(kind, emphasis) is _face_as_it_was(theme, kind, emphasis), (
            kind,
            emphasis,
        )
        compared += 1
    assert compared == (len(BlockKind) - 1) * 8 >= 9 * 8


# ----------------------------------------------------------------------
# What changed on a monospace base


def test_text_on_a_monospace_base_is_set_in_monospace_and_bold_is_the_mono_bold() -> None:
    """
    The defect, stated as the old answer beside the new one.

    Before: a block whose style said `Face.CODE` set its unemphasised text in
    `Face.PROSE` and its bold in `Face.PROSE_BOLD`, because `face_for` chose
    among the four prose faces for anything that was not a code span. The plan
    names the bold half; the regular half was the reviewer's reading
    (`.concerns/lead--reviewer-findings-on-plan.md`) and is confirmed here by
    the transcription's own answers.
    """
    theme = Theme.build()
    assert theme.style(BlockKind.CODE).font.face is Face.CODE

    assert _face_as_it_was(theme, BlockKind.CODE, Emphasis()) is Face.PROSE
    assert _face_as_it_was(theme, BlockKind.CODE, Emphasis(bold=True)) is Face.PROSE_BOLD

    assert theme.face_for(BlockKind.CODE, Emphasis()) is Face.CODE
    assert theme.face_for(BlockKind.CODE, Emphasis(bold=True)) is Face.CODE_BOLD
    assert theme.face_for(BlockKind.CODE, Emphasis(italic=True)) is Face.CODE
    assert theme.face_for(BlockKind.CODE, Emphasis(bold=True, italic=True)) is Face.CODE_BOLD
    assert theme.face_for(BlockKind.CODE, Emphasis(code=True)) is Face.CODE


def test_a_code_span_drops_the_weight_on_a_proportional_base_and_keeps_it_on_a_mono_one() -> None:
    """
    The asymmetry in `face_for`, pinned from both sides so neither is "fixed".

    In the default theme a code span inside a bold heading is the regular
    monospace -- `tests/test_markdown.py` pins that too, and the demo's first
    heading depends on it. In a one-family theme there is no second family for
    the span to switch to, so switching *weight* would be the only visible
    effect of the backticks, and a heading would thin out in the middle.
    """
    default = Theme.build()
    assert default.face_for(BlockKind.HEADING_2, Emphasis(code=True)) is Face.CODE
    assert default.face_for(BlockKind.HEADING_2, Emphasis(bold=True, code=True)) is Face.CODE

    mono = Theme.build(faces=Faces.mono())
    assert mono.face_for(BlockKind.HEADING_2, Emphasis(code=True)) is Face.CODE_BOLD
    assert mono.face_for(BlockKind.PARAGRAPH, Emphasis(code=True)) is Face.CODE
    assert mono.face_for(BlockKind.PARAGRAPH, Emphasis(bold=True, code=True)) is Face.CODE_BOLD


def test_which_faces_are_monospace_is_declared_and_not_read_off_the_code_role() -> None:
    """
    Assigning a face to `code` or `code_bold` does not make it a monospace base.

    The defect, measured before the fix (review 2, item 7): `Faces.monospace`
    was computed as `{code, code_bold}`, so a table that put a proportional face
    in either role turned every block set in that face into a "monospace base",
    where italic is dropped and the weight is the only thing that moves.

    - `Faces(code=Face.PROSE)` -- a host that wants no second family -- answered
      `Face.PROSE` for an italic run in a paragraph. The first assertion failed
      with exactly that.
    - `Faces(code_bold=Face.PROSE_BOLD)` -- a host asking for the answer bold
      code had before `Face.CODE_BOLD` existed -- made every *heading* a
      monospace base, since headings are set in the bold prose face, and an
      italic run in a heading lost its slant the same way. Nobody reported that
      one; it is the same inference from the other field.

    Both tables are compared with the default's answers on every block whose
    base is proportional and every emphasis without a code span, which is where
    the two tables say the same thing as the default and so must answer alike.
    """
    default = Theme.build()

    no_second_family = Theme.build(faces=Faces(code=Face.PROSE))
    assert no_second_family.face_for(BlockKind.PARAGRAPH, Emphasis(italic=True)) is (
        Face.PROSE_ITALIC
    )
    assert no_second_family.face_for(BlockKind.PARAGRAPH, Emphasis(code=True)) is Face.PROSE

    old_bold_code = Theme.build(faces=Faces(code_bold=Face.PROSE_BOLD))
    assert old_bold_code.face_for(BlockKind.HEADING_2, Emphasis(italic=True)) is (
        Face.PROSE_BOLD_ITALIC
    )
    # Still what the field says it is: bold on the block that *is* monospace.
    assert old_bold_code.face_for(BlockKind.CODE, Emphasis(bold=True)) is Face.PROSE_BOLD

    compared = 0
    for theme in (no_second_family, old_bold_code):
        for kind, emphasis in product(BlockKind, EVERY_EMPHASIS):
            if kind is BlockKind.CODE or emphasis.code:
                continue
            assert theme.face_for(kind, emphasis) is default.face_for(kind, emphasis), (
                theme.faces,
                kind,
                emphasis,
            )
            compared += 1
    assert compared == 2 * (len(BlockKind) - 1) * 4


def test_the_declared_monospace_set_is_the_code_pair_by_default_and_mono_s_pair_in_mono() -> None:
    """
    What the declaration is for each table a host can reach without writing one.

    `Face.CODE` and `Face.CODE_BOLD` are the roles a monospace file is
    registered under, so they are the default whatever the six fields say.
    `Faces.mono(regular, bold)` declares the pair it was given -- that call *is*
    the statement that those two faces are monospace -- and the last case is the
    declaration doing something the old inference also did, so that it is pinned
    as deliberate: a host that registered its monospace files under the prose
    roles gets upright italic on them.
    """
    code_pair = frozenset((Face.CODE, Face.CODE_BOLD))
    assert DEFAULT_FACES.monospace == code_pair
    assert Faces(code=Face.PROSE).monospace == code_pair
    assert Faces.mono().monospace == code_pair
    assert Faces.mono(bold=Face.CODE).monospace == frozenset((Face.CODE,))

    under_prose_roles = Faces.mono(regular=Face.PROSE, bold=Face.PROSE_BOLD)
    assert under_prose_roles.monospace == frozenset((Face.PROSE, Face.PROSE_BOLD))
    theme = Theme.build(faces=under_prose_roles)
    assert theme.face_for(BlockKind.PARAGRAPH, Emphasis(italic=True)) is Face.PROSE
    assert theme.face_for(BlockKind.PARAGRAPH, Emphasis(bold=True, italic=True)) is Face.PROSE_BOLD

    # A table that is equal field for field but declares otherwise is another
    # table: the declaration is part of the value, and so of every cache key
    # a theme is in.
    assert replace(DEFAULT_FACES, monospace=frozenset()) != DEFAULT_FACES
    undeclared = Theme.build(faces=replace(Faces.mono(), monospace=frozenset()))
    assert undeclared.face_for(BlockKind.PARAGRAPH, Emphasis(code=True)) is Face.CODE
    assert undeclared.face_for(BlockKind.HEADING_2, Emphasis(code=True)) is Face.CODE


# ----------------------------------------------------------------------
# Headings four to six


LOW_HEADINGS = (BlockKind.HEADING_4, BlockKind.HEADING_5, BlockKind.HEADING_6)


def test_headings_four_to_six_are_body_size_and_told_apart_by_face() -> None:
    """
    The sizes and faces the lead's decision 12 left to the builder, pinned.

    The scale is 1.25 from the body: h1 to h3 are the third, second and first
    powers, so h4 is the zeroth -- the body size. The powers after that are
    below the body size, so h5 and h6 stay at it and differ by face instead.
    Recorded in `advtext.style`'s docstring; this is the test that makes the
    record binding.
    """
    theme = Theme.build()
    body = theme.style(BlockKind.PARAGRAPH).font.size

    assert [theme.style(kind).font for kind in LOW_HEADINGS] == [
        FontSpec(Face.PROSE_BOLD, body),
        FontSpec(Face.PROSE_BOLD_ITALIC, body),
        FontSpec(Face.PROSE_ITALIC, body),
    ]
    sizes = [
        px_from_sp(theme.style(kind).font.size)
        for kind in (BlockKind.HEADING_1, BlockKind.HEADING_2, BlockKind.HEADING_3)
    ]
    assert sizes == pytest.approx([31.25, 25.0, 20.0], abs=1e-3), "h1 to h3 moved"
    assert px_from_sp(body) == pytest.approx(16.0, abs=1e-3)
    assert len({theme.style(kind) for kind in BlockKind if kind.name.startswith("HEADING")}) == 6


def test_the_air_around_a_heading_shrinks_by_the_same_step_at_every_level() -> None:
    """
    A tenth of an em less above and a twentieth less below, from h1 to h6.

    The first three levels already followed this -- 1.0/0.4, 0.9/0.35, 0.8/0.3 --
    and the new three continue it rather than introducing a second rule. Stated
    in ems of each heading's own size, which is how `build` computes it.
    """
    theme = Theme.build()
    headings = [kind for kind in BlockKind if kind.name.startswith("HEADING")]
    assert len(headings) == 6
    for level, kind in enumerate(headings):
        style = theme.style(kind)
        assert style.space_above / style.font.size == pytest.approx(1.0 - 0.1 * level, abs=1e-4)
        assert style.space_below / style.font.size == pytest.approx(0.4 - 0.05 * level, abs=1e-4)
        assert style.align is Align.LEFT
        assert style.interline.baselineskip.width == round(style.font.size * 1.15)


def test_emphasis_inside_a_low_heading_keeps_the_heading_s_own_weight_and_slant() -> None:
    """
    `face_for` reads a heading's base face, so the new bases have to be ones it knows.

    h5 is already bold italic, so no emphasis changes it. h6 is italic, so bold
    inside it is bold italic and italic inside it is still italic. A code span
    in any of them is the regular monospace, as in h1 to h3.
    """
    theme = Theme.build()
    for emphasis in EVERY_EMPHASIS:
        if not emphasis.code:
            assert theme.face_for(BlockKind.HEADING_5, emphasis) is Face.PROSE_BOLD_ITALIC
    assert theme.face_for(BlockKind.HEADING_4, Emphasis(italic=True)) is Face.PROSE_BOLD_ITALIC
    assert theme.face_for(BlockKind.HEADING_6, Emphasis()) is Face.PROSE_ITALIC
    assert theme.face_for(BlockKind.HEADING_6, Emphasis(bold=True)) is Face.PROSE_BOLD_ITALIC
    for kind in LOW_HEADINGS:
        assert theme.face_for(kind, Emphasis(code=True)) is Face.CODE


# ----------------------------------------------------------------------
# `faces` and `align`, each changing what it says and nothing else


def test_faces_changes_which_face_a_block_is_in_and_nothing_about_its_measurements() -> None:
    """
    A different `Faces` is the same theme with other faces in it.

    Checked by putting the default faces back and comparing whole styles, so a
    size, a leading or an indent that had come to depend on the face would show.
    """
    default = Theme.build()
    mono = Theme.build(faces=Faces.mono())

    assert mono.faces == Faces.mono() != DEFAULT_FACES
    # What each default face becomes in the mono table. Headings four to six are
    # set in bold, bold italic and italic; with no monospace italic the last of
    # those is the regular weight, which is the weakness `advtext.style`'s
    # docstring records for h6 in an all-mono theme.
    becomes = {
        Face.PROSE: Face.CODE,
        Face.PROSE_BOLD: Face.CODE_BOLD,
        Face.PROSE_ITALIC: Face.CODE,
        Face.PROSE_BOLD_ITALIC: Face.CODE_BOLD,
        Face.CODE: Face.CODE,
    }
    for kind in BlockKind:
        assert mono.style(kind).font.face is becomes[default.style(kind).font.face], kind
        restored = replace(mono.style(kind), font=default.style(kind).font)
        assert restored == default.style(kind), kind

    scalars = [spec.name for spec in fields(Theme) if spec.name not in ("blocks", "faces")]
    assert [getattr(mono, name) for name in scalars] == [getattr(default, name) for name in scalars]


def test_a_mono_table_can_give_up_the_weight_instead_of_the_columns() -> None:
    """
    `Faces.mono(bold=Face.CODE)` names no face that is not the one monospace file.

    For a host with no bold monospace to register: `Face.CODE_BOLD` would be
    backed by the bold *prose* file, which is proportional, and this is the
    table that never asks for it.
    """
    theme = Theme.build(faces=Faces.mono(bold=Face.CODE))
    asked = {theme.face_for(kind, emphasis) for kind in BlockKind for emphasis in EVERY_EMPHASIS}
    assert asked == {Face.CODE}
    assert {style.font.face for style in theme.blocks.values()} == {Face.CODE}


@pytest.mark.parametrize("align", [Align.LEFT, Align.CENTER, Align.RIGHT])
def test_align_reaches_the_running_text_and_only_the_running_text(align: Align) -> None:
    """
    Paragraphs, list items and quotes follow `align`; nothing else does or changes.

    Headings, code, rules and tables are `Align.LEFT` in the default theme and
    stay so under every `align`, including the ones that are not `LEFT`: a
    centred theme does not centre a fenced block.
    """
    default = Theme.build()
    built = Theme.build(align=align)

    for kind in BlockKind:
        if kind in RUNNING_TEXT:
            assert default.style(kind).align is Align.JUSTIFY
            assert built.style(kind) == replace(default.style(kind), align=align), kind
        else:
            assert built.style(kind) == default.style(kind), kind
            assert built.style(kind).align is Align.LEFT, kind
    assert replace(built, blocks=default.blocks) == default


# ----------------------------------------------------------------------
# The host's size


@pytest.mark.parametrize("faces", [DEFAULT_FACES, Faces.mono()], ids=["default", "mono"])
@pytest.mark.parametrize("height_px", [13.0, 16.0, 18.0])
def test_a_theme_at_a_host_s_pixel_height_is_drawn_at_that_height(
    faces: Faces, height_px: float
) -> None:
    """
    The body of `Theme.at_pixel_height(h)` is asked of ImGui at `h`, not at its em.

    `baked_size_px` is the arithmetic `advtext.backends.imgui_draw.draw` applies
    to a font key on the way out. Applied to the body's key it must give back
    the height the host named, to within the rounding to scaled points, and
    ImGui's own `floor(size + 0.5)` must then select exactly that size.

    The em itself is checked against `advtext.fontlib.em_size_for_pixel_height`,
    so the theme and the standalone helper cannot come to disagree.
    """
    theme = Theme.at_pixel_height(height_px, faces=faces)
    body = theme.style(BlockKind.PARAGRAPH).font

    assert body.face is faces.regular
    assert body.size == sp_from_px(fontlib.em_size_for_pixel_height(faces.regular, height_px))

    ours = fontlib_metrics(body.key)
    asked = baked_size_px(px_from_sp(body.size), ours.ascent, ours.descent, ours.em)
    assert asked == pytest.approx(height_px, abs=1e-3)
    assert float(int(asked + 0.5)) == height_px


def test_at_pixel_height_differs_from_build_only_in_the_size_for_the_default_faces() -> None:
    """
    For the faces `WIDEST_MARKER_EM` was measured on, measuring gives the constant.

    So `at_pixel_height` is `build` at the converted em and nothing more: the
    gutter it measures from Roboto's digits, rounded up to a tenth of an em, is
    the 1.4 em `build` assumes.
    """
    em_px = fontlib.em_size_for_pixel_height(Face.PROSE, 16.0)
    assert Theme.at_pixel_height(16.0) == Theme.build(em_px)
    assert Theme.at_pixel_height(16.0, align=Align.LEFT, spacing=Spacing.FRENCH) == Theme.build(
        em_px, align=Align.LEFT, spacing=Spacing.FRENCH
    )


def _marker_width(theme: Theme, text: str) -> float:
    """
    A list marker's set width in the theme's body face, in scaled points.
    """
    font = theme.style(BlockKind.ORDERED_ITEM).font
    metrics = fontlib_metrics(font.key)
    return sum(metrics.advance(ord(character)) for character in text)


def test_the_gutter_of_a_mono_theme_holds_a_two_digit_marker_and_build_s_default_would_not() -> (
    None
):
    """
    The reviewer's predicted overfull, measured, and what `at_pixel_height` does about it.

    `WIDEST_MARKER_EM` is 1.4 because "10." is 1.386 em in Roboto. In Inconsolata
    every advance is half an em, so "10." is 1.5 em: wider than the box a marker
    is right-aligned in, by a tenth of an em, which comes out of the gap between
    the marker and its text. `build` opens no font and keeps 1.4 unless told;
    `at_pixel_height` measures the face it was given.
    """
    assumed = Theme.build(faces=Faces.mono())
    box = assumed.list_indent - assumed.marker_gap
    assert _marker_width(assumed, "10.") > box, "the predicted overfull does not occur"
    assert (_marker_width(assumed, "10.") - box) / assumed.style(
        BlockKind.PARAGRAPH
    ).font.size == pytest.approx(0.1, abs=1e-3)

    measured = Theme.at_pixel_height(16.0, faces=Faces.mono())
    body = measured.style(BlockKind.PARAGRAPH).font.size
    assert measured.list_indent == round(body * (1.5 + MARKER_GAP_EM))
    assert _marker_width(measured, "10.") <= measured.list_indent - measured.marker_gap
    assert _marker_width(measured, "99.") <= measured.list_indent - measured.marker_gap

    told = Theme.build(faces=Faces.mono(), widest_marker_em=1.5)
    assert _marker_width(told, "10.") <= told.list_indent - told.marker_gap


def test_at_pixel_height_reads_the_resolver_it_is_given() -> None:
    """
    The conversion comes from `metrics`, so a host's own resolver decides it.

    A fake face 1.25 em tall with digits 0.7 em wide and a 0.3 em period: a
    20 px height is a 16 px em, and the widest two-digit marker is 1.7 em.
    """

    class Tall:
        def __init__(self, size: float) -> None:
            self.em = size
            self.ascent = size
            self.descent = size * 0.25

        def advance(self, codepoint: int) -> float:
            return self.em * (0.3 if chr(codepoint) == "." else 0.7)

    asked: list[str] = []

    def resolve(key: str) -> Any:
        asked.append(key)
        return Tall(float(parse_font_key(key).size))

    theme = Theme.at_pixel_height(20.0, metrics=resolve)

    body = theme.style(BlockKind.PARAGRAPH).font.size
    assert body == sp_from_px(16.0)
    assert theme.list_indent == round(body * (1.7 + MARKER_GAP_EM))
    assert len(asked) == 1 and parse_font_key(asked[0]).face is Face.PROSE


# ----------------------------------------------------------------------
# One call, and the document it sets


@pytest.fixture
def host_mono_bold(tmp_path: Path) -> Iterator[Path]:
    """
    A host's bold monospace, registered for the test and withdrawn after it.

    A copy of the bundle's one Inconsolata weight; see the module docstring for
    what that can and cannot show.
    """
    destination = tmp_path / "Host-Mono-Bold.ttf"
    shutil.copyfile(fontlib.font_file(Face.CODE), destination)
    fontlib.register_font(Face.CODE_BOLD, destination)
    try:
        yield destination
    finally:
        fontlib.unregister_font(Face.CODE_BOLD)


def _characters(document: Any) -> list[CharNode]:
    """
    Every `CharNode` anywhere in a built document, by walking it rather than naming fields.

    A walk and not a list of attributes because the block types are
    `advtext.markdown`'s and are about to gain members; a test that named
    `material`, `lines` and `cells` would silently stop looking inside whatever
    is added next.
    """
    found: list[CharNode] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, CharNode):
            found.append(value)
        elif isinstance(value, str | bytes | int | float | type(None)):
            return
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, tuple | list | frozenset | set):
            for item in value:
                walk(item)
        elif hasattr(value, "__dataclass_fields__") and id(value) not in seen:
            seen.add(id(value))
            for name in value.__dataclass_fields__:
                if name not in ("style", "theme"):
                    walk(getattr(value, name))

    walk(document.blocks)
    return found


def test_an_all_mono_ragged_theme_at_a_host_size_is_one_call(host_mono_bold: Path) -> None:
    """
    The plan's sentence, executed: one call, then a document with no proportional glyph.

    Real markdown with a heading, bold, italic, both, a code span, a list, a
    quote, a fenced block and a table goes through `build_document` under the
    theme. Every character that comes out is in one of the two monospace faces,
    both weights are present, every one of them advances by exactly half an em
    of its own size -- so the columns hold across weights -- and no block is
    justified.

    The old `face_for` fails the first assertion on the first word.
    """
    theme = Theme.at_pixel_height(16.0, faces=Faces.mono(), align=Align.LEFT)

    document = build_document(MARKDOWN, theme, fontlib_metrics)
    characters = _characters(document)

    assert len(characters) > 150, "the walk found almost nothing, so this proves nothing"
    faces = {parse_font_key(node.font).face for node in characters}
    assert faces == {Face.CODE, Face.CODE_BOLD}

    for node in characters:
        spec = parse_font_key(node.font)
        assert fontlib_metrics(node.font).advance(node.codepoint) == spec.size / 2, node

    assert {style.align for style in theme.blocks.values()} == {Align.LEFT}
    assert all(block.style.align is Align.LEFT for block in document.blocks)


def test_without_a_registered_bold_the_mono_theme_s_bold_is_the_stand_in_and_is_not_mono() -> None:
    """
    The same call with nothing registered, so the limitation is on the record.

    Bold is still keyed `Face.CODE_BOLD`, and `advtext.fontlib` backs that role
    with the bold prose file -- so bold runs are proportional and do break the
    columns. That is the glyphs the old `face_for` produced for this case; it is
    stated here as a test so that nobody reads the test above as saying an
    unconfigured host gets a bold monospace. `Faces.mono(bold=Face.CODE)` is the
    table for a host that would rather lose the weight.
    """
    assert fontlib.backing_face(Face.CODE_BOLD) is Face.PROSE_BOLD
    theme = Theme.at_pixel_height(16.0, faces=Faces.mono(), align=Align.LEFT)
    bold = [
        node
        for node in _characters(build_document(MARKDOWN, theme, fontlib_metrics))
        if parse_font_key(node.font).face is Face.CODE_BOLD
    ]
    assert bold
    widths = {
        fontlib_metrics(node.font).advance(node.codepoint) / parse_font_key(node.font).size
        for node in bold
    }
    assert len(widths) > 1, "the stand-in bold came out monospaced"

    plain = Theme.at_pixel_height(16.0, faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)
    only = {
        parse_font_key(node.font).face
        for node in _characters(build_document(MARKDOWN, plain, fontlib_metrics))
    }
    assert only == {Face.CODE}


def test_the_key_helpers_used_above_round_trip() -> None:
    """
    `font_key` and `parse_font_key` agree for the role this task leans on.
    """
    spec = parse_font_key(font_key(Face.CODE_BOLD, sp_from_px(16.0)))
    assert spec == FontSpec(Face.CODE_BOLD, sp_from_px(16.0))

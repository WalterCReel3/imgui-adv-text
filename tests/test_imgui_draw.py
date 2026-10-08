r"""
The ImGui backend, executed.

`docs/decisions.md` says nothing in this suite may open a window, and nothing
here does. A window needs a display; a *frame* does not. `imgui.create_context()`
allocates plain memory, `ImFontAtlas` bakes glyphs on the CPU through
stb_truetype, and `new_frame`/`render` build vertex buffers in RAM. A GPU is
needed to composite those buffers onto a screen, which is the step these tests
skip and the reason they can run at all.

So what is asserted here is **draw geometry, not pixels**. A glyph that reaches
the vertex buffer has been found in the atlas, rasterised, and positioned; it has
not been shown to anybody. That is a weaker claim than "it looks right" and a far
stronger one than "it compiles", and it is the strongest claim this environment
supports.

Two setup facts, both learned by hitting them:

- `io.backend_flags` must carry `renderer_has_textures`. Without it the first
  `add_text` aborts inside `imgui_draw.cpp` on `IM_ASSERT(atlas->TexIsBuilt)`.
- The draw list must come from a live frame. Building a bare `ImDrawList` from
  `get_draw_list_shared_data()` outside one **dumps core**, so the fixture below
  wraps every test in a real frame rather than taking that shortcut.

The headline test is `test_the_display_summation_reaches_the_vertex_buffer`.
`docs/decisions.md` calls the display sigma the project's strongest claim and
notes it is a glyph with no codepoint at all, reachable only through the
synthetic codepoints `advtext.fontlib` mints. Until `imgui_font_file` existed it
was demonstrable in the SVG backend and not this one, for a mechanical reason.
That asymmetry is what these tests exist to close, and
`test_an_unpatched_font_cannot_see_the_display_summation` keeps the reason for it
visible rather than letting the fix look like it was never needed.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from advtext import fontlib
from advtext.backends.imgui_draw import (
    DARK_PALETTE,
    DEFAULT_PALETTE,
    Palette,
    baked_size_px,
    draw,
    snap_px,
)
from advtext.fontmetrics import Face
from advtext.math import Style, group, math_fonts, mlist_to_hlist, op, rel
from advtext.nodes import Node
from advtext.pack import hpack
from advtext.shipout import Glyph, Line, Point, RuleRect, SetGlue, ship
from advtext.style import char_measure, font_key, fontlib_metrics, parse_font_key
from advtext.units import DEFAULT_PX_PER_INCH, px_from_sp, sp_from_px

imgui_bundle = pytest.importorskip("imgui_bundle")

DISPLAY_SIZE_PX = 36.0
"""
The size `advtext.ui.app` sets the formula at, so the geometry under test is the
geometry the demo would produce rather than a size chosen to make a test pass.
"""


@pytest.fixture(scope="session")
def imgui_context() -> Any:
    """
    One ImGui context for the session, with textures declared backend-managed.

    Session-scoped because a context is process-global in ImGui and creating a
    second while one is current is undefined. Never destroyed: `ImFontBaked`
    pointers are valid only for the current frame anyway, so tearing the atlas
    down would buy nothing and risks freeing something a later test holds.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    return imgui


@pytest.fixture
def frame(imgui_context: Any) -> Iterator[Any]:
    """
    A live frame, yielding the viewport-wide background draw list.

    The background list rather than a window's: a window clips to its own rect
    and a clipped glyph appends no vertices, which would make every assertion
    below pass or fail for a reason that has nothing to do with the backend.

    `render` runs in the teardown whatever the test did, because leaving a frame
    open leaks into the next test and the failure surfaces somewhere else.
    """
    imgui = imgui_context
    imgui.new_frame()
    try:
        yield imgui.get_background_draw_list()
    finally:
        imgui.render()


@pytest.fixture(scope="session")
def math_font(imgui_context: Any) -> Any:
    """
    The math face as ImGui sees it, loaded through the patched file.
    """
    imgui = imgui_context
    return imgui.get_io().fonts.add_font_from_file_ttf(
        str(fontlib.imgui_font_file(Face.MATH)), DISPLAY_SIZE_PX
    )


def _summation_commands() -> tuple[Any, ...]:
    """
    The litmus formula, shipped: the same construction `advtext.ui.app` performs.

    `ship` is handed `fonts.measure`, the measure the packing used, because
    `docs/decisions.md` records that shipping with a different one makes the
    glyph positions disagree with the box widths and nothing raises.
    """
    size = sp_from_px(DISPLAY_SIZE_PX, DEFAULT_PX_PER_INCH)
    fonts = math_fonts(size, lambda at: fontlib.math_metrics(float(at)))
    nodes: list[Node] = mlist_to_hlist(
        [op("∑", sup="n", sub=group("i", rel("="), "1"))], Style.DISPLAY, fonts
    )
    box = hpack(nodes, measure=fonts.measure).box
    return tuple(ship(box, Point(0, box.height), measure=fonts.measure))


def test_the_display_summation_reaches_the_vertex_buffer(frame: Any, math_font: Any) -> None:
    """
    The one glyph with no codepoint of its own draws through ImGui, not just SVG.
    """
    from imgui_bundle import imgui

    metrics = fontlib.math_metrics(DISPLAY_SIZE_PX)
    variants = metrics.vertical_variants(0x2211)
    display = variants[-1]
    assert display.name == "summation.v1", "the variant chain no longer ends where it did"
    assert display.codepoint >= fontlib.SYNTHETIC_LAST, "summation.v1 gained a real codepoint"

    before = frame.vtx_buffer.size()
    frame.add_text(
        math_font,
        DISPLAY_SIZE_PX,
        imgui.ImVec2(100.0, 200.0),
        0xFF111111,
        chr(display.codepoint),
    )
    assert (
        frame.vtx_buffer.size() - before == 4
    ), "the display summation appended no textured quad, so ImGui could not find it"


def test_an_unpatched_font_cannot_see_the_display_summation(imgui_context: Any) -> None:
    """
    Without the cmap patch the glyph is absent, which is why the patch exists.
    """
    imgui = imgui_context
    display = fontlib.math_metrics(DISPLAY_SIZE_PX).vertical_variants(0x2211)[-1]

    raw = imgui.get_io().fonts.add_font_from_file_ttf(
        str(fontlib.font_file(Face.MATH)), DISPLAY_SIZE_PX
    )
    patched = imgui.get_io().fonts.add_font_from_file_ttf(
        str(fontlib.imgui_font_file(Face.MATH)), DISPLAY_SIZE_PX
    )

    assert not raw.is_glyph_in_font(display.codepoint)
    assert patched.is_glyph_in_font(display.codepoint)
    # The patch must add and never remove: a real codepoint staying reachable is
    # what distinguishes editing the cmap from replacing it.
    assert raw.is_glyph_in_font(0x2211) and patched.is_glyph_in_font(0x2211)


def test_the_display_summation_is_a_bigger_glyph_than_the_body_one(
    imgui_context: Any, math_font: Any
) -> None:
    """
    ImGui bakes the display variant, not U+2211 scaled up -- the litmus claim.
    """
    display = fontlib.math_metrics(DISPLAY_SIZE_PX).vertical_variants(0x2211)[-1]
    baked = math_font.get_font_baked(DISPLAY_SIZE_PX)

    big = baked.find_glyph_no_fallback(display.codepoint)
    body = baked.find_glyph_no_fallback(0x2211)
    assert big is not None and body is not None

    assert big.advance_x > body.advance_x, "the display variant is no wider than the body glyph"
    assert (big.y1 - big.y0) > (
        body.y1 - body.y0
    ), "the display variant is no taller than the body glyph, so it is the same raster"


def test_drawing_the_shipped_formula_leaves_no_glyph_missing(frame: Any, math_font: Any) -> None:
    """
    Every glyph of the litmus formula is found in the atlas and drawn.
    """
    from imgui_bundle import imgui

    stats = draw(
        frame,
        _summation_commands(),
        imgui.ImVec2(50.0, 400.0),
        fonts=lambda _face: math_font,
    )
    assert stats.glyphs > 0, "the formula shipped no glyphs at all"
    assert (
        stats.missing == 0
    ), f"{stats.missing} glyph(s) of the formula have no raster in ImGui's atlas"


def test_drawing_the_shipped_formula_emits_one_quad_per_glyph(frame: Any, math_font: Any) -> None:
    """
    The backend's glyph count and ImGui's vertex count agree, so nothing was silently dropped.
    """
    from imgui_bundle import imgui

    before = frame.vtx_buffer.size()
    stats = draw(
        frame,
        _summation_commands(),
        imgui.ImVec2(50.0, 400.0),
        fonts=lambda _face: math_font,
    )
    appended = frame.vtx_buffer.size() - before
    assert appended == 4 * stats.glyphs, (
        f"{stats.glyphs} glyphs reported but {appended} vertices appended; "
        "a glyph ImGui declined to draw is counted as drawn"
    )


def test_a_glyph_absent_from_the_face_is_counted_rather_than_drawn(
    frame: Any, math_font: Any
) -> None:
    """
    `DrawStats.missing` is the report, and it is still reachable.
    """
    from imgui_bundle import imgui

    absent = fontlib.SYNTHETIC_LAST  # minted downward from SYNTHETIC_FIRST, so this end is free
    assert not math_font.is_glyph_in_font(absent)

    cmd = Glyph(font=font_key(Face.MATH, sp_from_px(16.0)), codepoint=absent, x=0, y=0, index=0)
    stats = draw(frame, [cmd], imgui.ImVec2(0.0, 0.0), fonts=lambda _face: math_font)
    assert stats.missing == 1 and stats.glyphs == 0


def test_the_baked_size_correction_is_the_ratio_of_pixel_height_to_em() -> None:
    """
    `baked_size_px` asks ImGui for the size whose pixel height equals our em.
    """
    # Roboto's numbers: unitsPerEm 2048, hhea ascender 1900, descender -500.
    metrics = fontlib.metrics(Face.PROSE, 16.0)
    requested = baked_size_px(16.0, metrics.ascent, metrics.descent, metrics.em)
    assert requested == pytest.approx(16.0 * 2400.0 / 2048.0)
    assert requested == pytest.approx(18.75)


def test_the_baked_size_correction_is_scale_free() -> None:
    """
    Only the ratio matters, so the unit the metrics arrive in cannot change the answer.
    """
    assert baked_size_px(16.0, 19.0, 5.0, 20.48) == pytest.approx(
        baked_size_px(16.0, 1900.0, 500.0, 2048.0)
    )


def test_a_degenerate_em_leaves_the_size_alone() -> None:
    """
    A metrics object built at size zero must not divide by it.
    """
    assert baked_size_px(16.0, 0.0, 0.0, 0.0) == 16.0


def _channels(colour: int) -> tuple[int, int, int]:
    """
    The red, green and blue of a packed ABGR colour, as `rgba` builds them.
    """
    return colour & 0xFF, (colour >> 8) & 0xFF, (colour >> 16) & 0xFF


def _contrast(one: int, other: int) -> float:
    """
    The WCAG contrast ratio between two packed colours, from 1.0 to 21.0.
    """

    def luminance(colour: int) -> float:
        parts = []
        for value in _channels(colour):
            fraction = value / 255.0
            parts.append(
                fraction / 12.92 if fraction <= 0.03928 else ((fraction + 0.055) / 1.055) ** 2.4
            )
        red, green, blue = parts
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter, darker = sorted((luminance(one), luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_ink_is_readable_against_the_page_it_is_drawn_on() -> None:
    """
    `ink` and `page` are a pair, and the pairing is what makes the text visible.

    The failure this pins is not a wrong colour, it is an *invisible* one: ImGui's
    default theme is dark, so ink chosen for paper and drawn without the paper
    disappears rather than looking wrong, and no exception is raised. Anyone
    changing one of these two has to keep them legible together.

    4.5:1 is WCAG AA for body text. The default pair is far above it; the
    threshold exists to catch a later edit, not to grade this one.
    """
    assert _contrast(DEFAULT_PALETTE.ink, DEFAULT_PALETTE.page) >= 4.5
    assert _contrast(DEFAULT_PALETTE.rule, DEFAULT_PALETTE.page) >= 4.5


def test_a_palette_with_ink_and_page_the_same_is_rejected_by_the_contrast_rule() -> None:
    """
    The guard above can fail, which is the only reason it is worth having.
    """
    invisible = Palette(page=DEFAULT_PALETTE.ink)
    assert _contrast(invisible.ink, invisible.page) < 4.5


# ---------------------------------------------------------------------------
# Sub-pixel phase.  `docs/subpixel.md` is the write-up; these are its evidence.
#
# The property under test is **one texel to one pixel**.  Before the fix these
# assertions failed for 1734 of 1734 glyph quads in the demo document, which is
# the fixture attack `docs/status.md` section 5 asks for: the suite is run
# against the real `demo/sample.md` at a real measure through the real `draw`,
# not against a hand-built command that could be chosen to land on the grid.
# ---------------------------------------------------------------------------

DEMO_SOURCE = Path(__file__).resolve().parent.parent / "demo" / "sample.md"
"""
The same file `tests/test_litmus.py` measures, so the two agree about the document.
"""

DEMO_WIDTH_PX = 700.0
"""
A measure close to the demo's own, and deliberately not a round number of
points. A width that happened to put every glyph on an integer would make every
assertion below pass for a reason that has nothing to do with the backend.
"""


def _demo_commands() -> tuple[Any, ...]:
    """
    The real demo document, composed and shipped: the fixture these tests attack.
    """
    from advtext.markdown import build_document
    from advtext.shipout import Point, ship
    from advtext.style import Theme, char_measure, fontlib_metrics
    from advtext.ui import compose

    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document(DEMO_SOURCE.read_text(encoding="utf-8"), theme, fontlib_metrics)
    box = compose(document, theme, sp_from_px(DEMO_WIDTH_PX), measure)
    return tuple(ship(box, Point(0, box.height), measure=measure))


@pytest.fixture(scope="session")
def demo_commands() -> tuple[Any, ...]:
    """
    Composed once: this is the most expensive thing in the file by two orders.
    """
    return _demo_commands()


@pytest.fixture(scope="session")
def every_face(imgui_context: Any) -> Any:
    """
    All six faces loaded through the patched files, as `advtext.ui.app` loads them.
    """
    imgui = imgui_context
    loaded = {
        face: imgui.get_io().fonts.add_font_from_file_ttf(
            str(fontlib.imgui_font_file(face)), DISPLAY_SIZE_PX
        )
        for face in Face
    }
    return lambda face: loaded[face]


def _glyph_quads(draw_list: Any, first: int) -> Iterator[tuple[Any, Any]]:
    """
    The opposite corners of every *textured* quad appended from `first` onward.

    Rule rectangles are filled with the atlas's white pixel, so their two corners
    carry the same `uv`. They are excluded here because "one texel to one pixel"
    is meaningless for a quad that samples a single texel on purpose; rules get
    their own assertion below.
    """
    buffer = draw_list.vtx_buffer
    for index in range(first, buffer.size(), 4):
        near, far = buffer[index], buffer[index + 2]
        if near.uv.x != far.uv.x and near.uv.y != far.uv.y:
            yield near, far


def test_every_glyph_of_the_demo_document_lands_on_a_whole_pixel(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    Every glyph quad's horizontal corners are integers. Nothing is resampled.

    This is half of what pins the advance rule and **it is deliberately not the
    whole of it**, because it does not distinguish that rule from the whole-pixel
    one it replaced: both put every pen on an integer, and a revert to
    `anchor + round(offset)` leaves this green.
    `test_the_gap_between_two_glyphs_is_within_half_a_pixel_of_the_design` is the
    other half, and it is the one a revert fails. Neither is worth much alone.

    What this one does catch, and catches alone: the half-pixel rule this
    replaced (it left 1444 of 4329 pens at a fractional phase), and any future
    change that reintroduces a fractional pen for any reason. A fractional pen is
    resolved by the renderer's bilinear filter, which is the fuzz the user ruled
    out on sight.
    """
    from imgui_bundle import imgui

    first = frame.vtx_buffer.size()
    stats = draw(frame, demo_commands, imgui.ImVec2(40.0, 30.0), fonts=every_face)
    assert stats.glyphs > 1000, "the demo document shipped almost nothing, so this proves nothing"

    edges = [value for near, far in _glyph_quads(frame, first) for value in (near.pos.x, far.pos.x)]
    assert len(edges) > 2000, f"only {len(edges)} quad edges, so this fixture proves nothing"

    fractional = [value for value in edges if value != int(value)]
    assert not fractional, (
        f"{len(fractional)} of {len(edges)} glyph quad edges are off the pixel grid and will "
        f"be resampled: {fractional[:4]}"
    )


def test_the_gap_between_two_glyphs_is_within_half_a_pixel_of_the_design(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    The half a revert fails, and the reason the advance rule exists.

    Rounding each glyph's *position* independently makes a gap the difference of
    two roundings, so it can be a full pixel from the gap the designer drew --
    measured on this document, 478 of 3453 adjacent pairs were more than half a
    pixel out under that rule. Rounding each *gap* instead bounds every one of
    them at half a pixel by construction.

    The bound is `<= 0.5` and not `< 0.5`: `snap_px` is half-up, so a designed
    gap of exactly n + 0.5 px rounds to n + 1 and is exactly half a pixel out.
    That is the equality case and it is legitimate; anything past it is not.

    Asserted against `advtext.shipout`'s own scaled-point coordinates rather than
    against a second implementation of the rule, so this cannot pass by agreeing
    with a bug it shares.
    """
    drawn = _drawn(frame, every_face, demo_commands)
    assert len(drawn) > 1000, f"only {len(drawn)} glyphs drawn, so this proves nothing"

    # The quad's left edge is the pen plus that glyph's own ink offset, and the
    # two glyphs of a pair have different offsets -- so differencing quad edges
    # measures the ink between them, not the gap the pen rule produced. `x0` has
    # to come back off before anything here is about placement.
    pens = {id(cmd): qx - _visible(every_face, cmd)[1].x0 for cmd, _oy, qx, _qy in drawn}
    worst = 0.0
    pairs = 0
    for span in _spans(demo_commands):
        visible = [cmd for cmd in span if id(cmd) in pens]
        for before, after in zip(visible, visible[1:], strict=False):
            designed = px_from_sp(after.x - before.x)
            rendered = pens[id(after)] - pens[id(before)]
            worst = max(worst, abs(rendered - designed))
            pairs += 1

    assert pairs > 1000, f"only {pairs} adjacent pairs inside spans, so this proves nothing"
    assert worst <= 0.5 + 1e-9, (
        f"the worst inter-glyph gap is {worst:.4f} px from the designed gap, over {pairs} "
        "pairs. Rounding positions rather than gaps is what produces this; see "
        "docs/advance-rule.md"
    )


def test_a_glyph_sits_on_a_whole_pixel_row(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    No glyph sits between two pixel rows, from an origin that is not on one.

    **The control is the origin, and it used to be the horizontal axis.** While
    the pen was quantised to half a pixel, this test proved the vertical was
    whole by pointing at fractional x values in the same buffer: the fixture
    demonstrably *could* emit a fraction, and no y was one. Under the advance
    rule no coordinate on either axis is fractional, so that control is gone and
    would now fail rather than mislead.

    What replaces it is `30.25`. The document is drawn from an origin a quarter
    of a pixel down, so every baseline arrives here fractional and something has
    to have rounded it. Remove `snap_px` from the vertical in `_RigidSpan.pen`
    and every value below lands on `.25`.

    **What this still does not establish.** It does not pin the axis asymmetry.
    Every within-span vertical offset in this document is already a whole number
    of pixels -- measured, 3486 of 3486, and 2 of 2 in the litmus formula -- so
    a rule change on the vertical cannot disagree with this content.
    `test_a_vertical_offset_inside_a_span_stays_on_a_whole_row` builds content
    where it can; that is the test that pins the choice.
    """
    from imgui_bundle import imgui

    first = frame.vtx_buffer.size()
    draw(frame, demo_commands, imgui.ImVec2(40.0, 30.25), fonts=every_face)

    quads = list(_glyph_quads(frame, first))
    assert len(quads) > 1000, "the demo document drew almost nothing, so this proves nothing"

    rows = [
        value for near, far in quads for value in (near.pos.y, far.pos.y) if value != int(value)
    ]
    assert not rows, f"{len(rows)} glyph quad edges sit between two pixel rows: {rows[:4]}"
    assert 30.25 != int(30.25), (
        "the origin this test draws from is a whole number, so nothing had to round the "
        "vertical and the assertion above is free"
    )


def test_a_vertical_offset_inside_a_span_stays_on_a_whole_row(frame: Any, every_face: Any) -> None:
    """
    The two axes are treated differently, on content that can tell them apart.

    `_RigidSpan.pen` accumulates rounded *gaps* horizontally and snaps the
    vertical absolutely against the span anchor. The reason is that the defect
    the user reported and judged is horizontal -- inter-letter gaps of 1, 2, 2 px
    in "people", `iffe` fused in a heading -- while an accumulating baseline
    would let a superscript drift away from the run it belongs to for no gap it
    closes.

    A raised glyph inside a rigid span is a math script, and `ship` really does
    emit one with no glue before it. The fixture is that arrangement with the
    vertical offset chosen so the two rules would disagree: -5.4 px snaps to
    -5.0, and any rule that quantised it more finely would not.

    The horizontal is asserted beside it from the same pair, because a test that
    only said "y is whole" would pass just as well on a fixture where nothing
    moved horizontally at all. `GAP_PX` is 9.4, so the rendered gap is
    `snap_px(9.4) == 9.0` -- a designed gap that is not already an integer, which
    is what makes the assertion mean something.
    """
    from imgui_bundle import imgui

    key = font_key(Face.PROSE, sp_from_px(16.0))
    raised = [
        Glyph(font=key, codepoint=ord("n"), x=0, y=0, index=0),
        Glyph(font=key, codepoint=ord("n"), x=sp_from_px(GAP_PX), y=sp_from_px(-5.4), index=1),
    ]
    assert snap_px(-5.4) == -5.0 and -5.4 != int(-5.4), "the fixture lost its point"

    first = frame.vtx_buffer.size()
    draw(frame, raised, imgui.ImVec2(100.0, 200.0), fonts=every_face)
    quads = [(near.pos.x, near.pos.y) for near, _far in _glyph_quads(frame, first)]
    assert len(quads) == 2, f"{len(quads)} quads for a two-glyph fixture"

    assert quads[1][1] - quads[0][1] == -5.0, (
        f"the raised glyph came out {quads[1][1] - quads[0][1]} px above its span anchor "
        "rather than 5, so a vertical offset is being quantised to halves"
    )
    assert quads[1][0] - quads[0][0] == 9.0, (
        f"the same pair is {quads[1][0] - quads[0][0]} px apart horizontally rather than "
        f"9.0, so snap_px is not reaching this fixture's {GAP_PX} px gap at all"
    )


def test_no_glyph_of_the_demo_document_is_resampled(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    Every glyph quad is exactly as many pixels across as it is texels across.

    This is the assertion that integer *corners* alone cannot make. A quad can
    sit on the grid and still be the wrong size -- 19 texels drawn into 18.75
    pixels lands both corners on integers at one particular origin and resamples
    anyway -- so the corner test above and this one are not the same test twice.
    """
    from imgui_bundle import imgui

    texture = imgui.get_io().fonts.tex_data
    first = frame.vtx_buffer.size()
    draw(frame, demo_commands, imgui.ImVec2(40.0, 30.0), fonts=every_face)

    worst = 0.0
    for near, far in _glyph_quads(frame, first):
        worst = max(
            worst,
            abs((far.pos.x - near.pos.x) - (far.uv.x - near.uv.x) * texture.width),
            abs((far.pos.y - near.pos.y) - (far.uv.y - near.uv.y) * texture.height),
        )
    assert worst == 0.0, (
        f"a glyph is drawn {worst:.4f} px away from its own texel size, so the GPU "
        "must interpolate between texels to fill it"
    )


def test_a_glyph_is_drawn_where_ship_out_put_it(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    The control on the two tests above: they also pass if every glyph is at the origin.

    Snapping is only allowed to move a glyph to the nearest pixel. Here the pen
    positions ImGui was handed are recomputed from the commands and compared
    with the positions the quads came out at, which is what stops "make the
    numbers integral" from being satisfied by throwing the numbers away.
    """
    from imgui_bundle import imgui

    origin = imgui.ImVec2(40.0, 30.0)
    wanted = sorted(origin.x + px_from_sp(cmd.x) for cmd in demo_commands if isinstance(cmd, Glyph))

    first = frame.vtx_buffer.size()
    draw(frame, demo_commands, origin, fonts=every_face)
    # A quad's left edge is the pen plus the glyph's own left bearing, which is a
    # whole number of texels and is not always zero -- so the pen is recovered by
    # matching each quad to the nearest wanted pen, and the match must be close.
    got = sorted(near.pos.x for near, _far in _glyph_quads(frame, first))
    assert len(got) <= len(wanted)

    strays = 0
    for edge in got:
        nearest = min(wanted, key=lambda pen: abs(pen - edge))
        # Half a pixel of snapping, plus the left bearing, which for these faces
        # at these sizes never exceeds a couple of pixels.
        if abs(nearest - edge) > 3.0:
            strays += 1
    assert strays == 0, f"{strays} glyphs are more than 3 px from any position ship-out computed"


def test_the_size_imgui_is_asked_for_is_the_size_it_would_have_baked(
    imgui_context: Any, every_face: Any
) -> None:
    """
    The mechanism, stated as an assertion: `GetFontBaked` quantises, and we match it.

    Every face at every size the demo uses. `baked_size_px` returns a fractional
    size for five of the six faces -- 18.75 for PROSE at 16 px -- and ImGui bakes
    at `floor(size + 0.5)`. If a future ImGui bakes at the exact size asked for,
    this test goes red and the whole fix becomes unnecessary rather than wrong,
    which is the reason to pin the assumption here rather than only in prose.
    """
    demo_sizes = (13.0, 14.0, 15.0, 16.0, 18.0, 20.0, 22.0, 24.0, 28.0, 36.0)
    fractional = 0
    for face in Face:
        ours = fontlib.metrics(face, 16.0)
        for size_px in demo_sizes:
            wanted = baked_size_px(size_px, ours.ascent, ours.descent, ours.em)
            fractional += wanted != int(wanted)
            baked = every_face(face).get_font_baked(wanted)
            assert baked.size == snap_px(wanted), (
                f"{face.name} at {size_px} px: asked for {wanted}, ImGui baked "
                f"{baked.size}, snap_px says {snap_px(wanted)}"
            )
    assert fractional > 30, (
        "no size in this sweep was fractional, so the test would pass with the "
        "quantisation removed and proves nothing"
    )


def test_asking_for_the_rounded_size_selects_the_same_raster(every_face: Any) -> None:
    """
    Rounding the size costs no sharpness of its own: it is the identical bitmap.

    The fix would be a bad trade if it picked a different, smaller raster. It
    does not -- `GetFontBaked(18.75)` and `GetFontBaked(19.0)` are the same
    `ImFontBaked`, so the only thing that changes is the scale it is drawn at.
    """
    font = every_face(Face.PROSE)
    ours = fontlib.metrics(Face.PROSE, 16.0)
    wanted = baked_size_px(16.0, ours.ascent, ours.descent, ours.em)
    assert wanted != int(wanted), "PROSE at 16 px no longer asks for a fractional size"

    asked, rounded = font.get_font_baked(wanted), font.get_font_baked(snap_px(wanted))
    letter, same = asked.find_glyph(ord("n")), rounded.find_glyph(ord("n"))
    assert asked.size == rounded.size and asked.ascent == rounded.ascent
    assert (letter.u0, letter.v0, letter.u1, letter.v1) == (same.u0, same.v0, same.u1, same.v1)


def test_snapping_an_absolute_position_can_never_be_more_than_half_a_pixel_out() -> None:
    """
    Over every glyph of the demo document, not over a chosen line.
    """
    positions = [px_from_sp(cmd.x) for cmd in _demo_commands() if isinstance(cmd, Glyph)]
    assert len(positions) > 1000
    worst = max(abs(snap_px(x) - x) for x in positions)
    assert worst <= 0.5, f"a glyph moved {worst} px, which is more than snapping to the nearest"


def test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin() -> None:
    """
    The failure mode the test above exists to exclude, shown failing on real text.

    A snapping implementation that rounds each *advance* and sums them passes a
    per-glyph integrality check -- every position it produces is a whole number
    -- and is still wrong, because the errors accumulate in one direction. On
    `demo/sample.md` at this measure it puts the end of a line **9.9 px** past
    where the line breaker placed it, which is more than a character width and
    is exactly the residue `tests/test_litmus.py` asserts is zero.

    Without this, "positions are integers" is the vacuous assertion
    `docs/status.md` section 5 warns about: `int(x)` satisfies it too.
    """
    by_line: dict[Any, list[float]] = {}
    for cmd in _demo_commands():
        if isinstance(cmd, Glyph):
            by_line.setdefault(cmd.y, []).append(px_from_sp(cmd.x))

    long_lines = [sorted(xs) for xs in by_line.values() if len(xs) >= 20]
    assert len(long_lines) > 50, "too few long lines in the demo document to say anything"

    def by_advance(exact: list[float]) -> list[float]:
        walked = [snap_px(exact[0])]
        for previous, current in zip(exact, exact[1:], strict=False):
            walked.append(walked[-1] + snap_px(current - previous))
        return walked

    drifts = [abs(by_advance(line)[-1] - line[-1]) for line in long_lines]
    assert all(
        position == int(position) for line in long_lines for position in by_advance(line)
    ), "the control is not a control: its positions are not integral, so it fails the naive check"
    assert max(drifts) > 5.0, (
        f"rounding advances only drifts {max(drifts):.2f} px here, so this document no "
        "longer demonstrates the failure and the test above is no longer guarded"
    )
    assert max(abs(snap_px(x) - x) for line in long_lines for x in line) <= 0.5


def test_snap_px_rounds_halves_up_the_way_imgui_does() -> None:
    """
    Not `round`, which rounds halves to even and would disagree with ImGui at 60.5.
    """
    assert [snap_px(v) for v in (0.0, 0.4, 0.5, 0.6, 1.5, 2.5, 60.5)] == [0, 0, 1, 1, 2, 3, 61]
    assert snap_px(-0.5) == 0.0 and snap_px(-0.6) == -1.0
    assert round(2.5) == 2 and snap_px(2.5) == 3.0, "Python's round is still banker's rounding"


def test_draw_restores_the_no_pixel_snap_flag_it_borrowed(frame: Any, every_face: Any) -> None:
    """
    `draw` sets `ImDrawListFlags_TextNoPixelSnap` and must put it back.

    **This test used to assert the flag was load-bearing, and it is not any
    more.** While the pen was quantised to half a pixel, clearing the flag let
    `IM_TRUNC` round every half back to a whole underneath us with no symptom of
    its own. Under the advance rule every pen is already an integer, so ImGui
    would find nothing to truncate and the flag changes no output this module
    produces today. Asserting that it does would be a test that cannot fail.

    What is still worth pinning is the borrowing. ImGui reuses one draw list for
    a whole window, so a flag left on leaks into every widget drawn after this
    one -- a defect that shows up somewhere else entirely and looks like nothing
    to do with text.

    The second assertion keeps the *reason* the flag is set from quietly
    expiring: it drives `add_text` directly with a fractional pen and checks this
    build still truncates. If that ever stops being true, the flag is dead code
    and this docstring is wrong; if a future rule emits a fractional pen again,
    the flag is load-bearing once more and the test above it should be restored.
    """
    from imgui_bundle import imgui

    left, right = _pair(sp_from_px(GAP_PX))
    first = frame.vtx_buffer.size()
    draw(frame, [left, right], imgui.ImVec2(100.0, 200.0), fonts=every_face)
    quads = [near.pos.x for near, _far in _glyph_quads(frame, first)]
    assert len(quads) == 2, f"{len(quads)} quads for a two-glyph fixture"

    assert (
        frame.flags & int(imgui.ImDrawListFlags_.text_no_pixel_snap) == 0
    ), "`draw` left the no-snap flag on a draw list it borrowed"

    font = every_face(parse_font_key(left.font).face)
    before = frame.vtx_buffer.size()
    frame.add_text(font, 16.0, imgui.ImVec2(quads[0] + 9.5, 200.0), 0xFF111111, "n")
    truncated = frame.vtx_buffer[before].pos.x
    assert truncated == int(truncated), (
        "this ImGui build no longer truncates a fractional pen, so the flag `draw` sets "
        "is defending against nothing and its docstring should be corrected"
    )


def test_a_rule_too_thin_for_the_pixel_grid_keeps_a_pixel(frame: Any, every_face: Any) -> None:
    """
    Snapping both edges of a hairline must not round them onto each other.

    A `\\hrule` of 0.3 px is a real thing for TeX to ask for and this project
    asks for one: `Theme.build` derives rule thicknesses from the type size. An
    area of zero extent appends no vertices at all, so getting this wrong deletes
    the rule rather than misdrawing it -- silent, and invisible in every other
    assertion in this file.
    """
    from imgui_bundle import imgui

    hairline = RuleRect(
        x=sp_from_px(10.6), y=sp_from_px(10.6), width=sp_from_px(40.0), height=sp_from_px(0.3)
    )
    first = frame.vtx_buffer.size()
    stats = draw(frame, [hairline], imgui.ImVec2(0.0, 0.0), fonts=every_face)
    assert stats.rules == 1
    assert frame.vtx_buffer.size() - first == 4, "the hairline rule appended no geometry"

    near, far = frame.vtx_buffer[first], frame.vtx_buffer[first + 2]
    assert far.pos.y - near.pos.y == 1.0, "a rule thinner than a pixel came out other than 1 px"
    assert (near.pos.x, near.pos.y) == (int(near.pos.x), int(near.pos.y))


def test_an_empty_rule_is_still_empty_after_snapping(frame: Any, every_face: Any) -> None:
    """
    The other side of it: a rule of no thickness must not acquire a pixel.

    `Theme.table_rule_thickness` documents zero as meaning *no line*, so widening
    every degenerate span to a pixel would draw a table rule the theme turned off.
    """
    from imgui_bundle import imgui

    nothing = RuleRect(x=sp_from_px(10.6), y=sp_from_px(10.6), width=sp_from_px(40.0), height=0)
    first = frame.vtx_buffer.size()
    draw(frame, [nothing], imgui.ImVec2(0.0, 0.0), fonts=every_face)
    if frame.vtx_buffer.size() - first == 4:
        near, far = frame.vtx_buffer[first], frame.vtx_buffer[first + 2]
        assert far.pos.y == near.pos.y, "a rule of zero thickness was widened into visible ink"


def test_areas_that_abut_still_abut_once_snapped(frame: Any, every_face: Any) -> None:
    """
    Two rules sharing an edge must not gain a seam or an overlap from snapping.

    Both edges round the same way by construction, so this holds for any shared
    coordinate; the table in `demo/sample.md` is the case that would show it.
    """
    from imgui_bundle import imgui

    seam = sp_from_px(30.7)
    left = RuleRect(
        x=sp_from_px(10.4), y=sp_from_px(5.0), width=seam - sp_from_px(10.4), height=sp_from_px(4.0)
    )
    right = RuleRect(x=seam, y=sp_from_px(5.0), width=sp_from_px(20.0), height=sp_from_px(4.0))

    first = frame.vtx_buffer.size()
    draw(frame, [left, right], imgui.ImVec2(0.0, 0.0), fonts=every_face)
    assert frame.vtx_buffer.size() - first == 8
    left_far = frame.vtx_buffer[first + 2]
    right_near = frame.vtx_buffer[first + 4]
    assert left_far.pos.x == right_near.pos.x, "snapping opened a seam between two abutting rules"


def _quad_corner(frame: Any, every_face: Any, origin: tuple[float, float]) -> tuple[float, float]:
    """
    Where one prose glyph's quad lands for a given screen origin.
    """
    from imgui_bundle import imgui

    cmd = Glyph(font=font_key(Face.PROSE, sp_from_px(16.0)), codepoint=ord("n"), x=0, y=0, index=0)
    first = frame.vtx_buffer.size()
    draw(frame, [cmd], imgui.ImVec2(*origin), fonts=every_face)
    assert frame.vtx_buffer.size() - first == 4
    near = frame.vtx_buffer[first]
    return near.pos.x, near.pos.y


def test_a_glyph_goes_to_the_nearer_pixel_and_not_always_the_one_below(
    frame: Any, every_face: Any
) -> None:
    """
    Snapping the pen is a *round*, and ImGui on its own would only ever *truncate*.

    `ImFont::RenderText` opens with `IM_TRUNC(pos.x)`, so a document coordinate
    of 100.6 is drawn at 100 -- every glyph in the document biased 0.6 px left of
    where the line breaker put it, and never right. That bias is invisible to
    every other assertion in this file, because a truncated coordinate is still
    an integer and still one texel to one pixel. It is visible here: the
    coordinate is swept across a pixel boundary and the quad has to move with it.

    Both axes, because the baseline is truncated the same way and a run of
    glyphs whose ascent lands on .5 would sit a pixel high for the same reason.
    """
    base = _quad_corner(frame, every_face, (100.0, 200.0))
    assert _quad_corner(frame, every_face, (100.4, 200.4)) == base
    assert _quad_corner(frame, every_face, (100.6, 200.6)) == (base[0] + 1.0, base[1] + 1.0), (
        "a glyph asked for at x+0.6 was drawn at x, so the pen is being truncated "
        "rather than rounded and the whole document sits half a pixel to the left"
    )
    assert _quad_corner(frame, every_face, (101.0, 201.0)) == (base[0] + 1.0, base[1] + 1.0)


ORIGIN_X = 40.25
"""
A screen origin deliberately off the pixel grid, because the window's own is.

`get_cursor_screen_pos` returns whatever ImGui's layout arrived at, and an
integral origin would make every span anchor land on a pixel by accident --
which is precisely the condition under which span-relative and absolute snapping
agree, so the tests below would stop telling them apart.
"""


def _spans(commands: Sequence[Any]) -> list[tuple[Any, ...]]:
    """
    The maximal runs of `Glyph`, which is the unit `draw` anchors on.

    Computed here from the command list rather than imported from the backend,
    so a change of unit inside `_RigidSpan` shows up as a disagreement instead
    of being mirrored silently into the expectation.
    """
    runs: list[tuple[Any, ...]] = []
    current: list[Any] = []
    for cmd in commands:
        if isinstance(cmd, Glyph):
            current.append(cmd)
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return runs


def _visible(every_face: Any, cmd: Any) -> Any:
    """
    The baked face and glyph a command will draw, or `None` if it appends no geometry.

    Two ways to append nothing and both occur in `demo/sample.md`: a codepoint
    the face has no raster for, and a space, whose `ImFontGlyph` is not visible.
    Skipping exactly these is what lets a quad be paired with the command that
    emitted it by position in the buffer.

    The baked face comes back with the glyph because the vertical needs it:
    `add_text` takes a top-left corner measured down from *ImGui's* ascent, so
    the position ship-out computed cannot be recovered from the quad without it.
    """
    spec = parse_font_key(cmd.font)
    font = every_face(spec.face)
    if not font.is_glyph_in_font(cmd.codepoint):
        return None
    ours = fontlib.metrics(spec.face, 16.0)
    size_px = baked_size_px(px_from_sp(spec.size), ours.ascent, ours.descent, ours.em)
    baked = font.get_font_baked(size_px)
    glyph = baked.find_glyph(cmd.codepoint)
    return (baked, glyph) if glyph.is_visible() else None


def _drawn(
    frame: Any, every_face: Any, commands: Sequence[Any]
) -> list[tuple[Any, float, float, float]]:
    """
    Every visible glyph of a document paired with the corner its quad came out at.

    **One shipped line per `draw` call, each placed at a y inside the viewport.**
    The background draw list clips to `io.display_size`, the demo document is
    several times taller than that, and a clipped glyph appends no vertices --
    so drawing it in one call pairs the first 1589 quads correctly and then runs
    out, which is the kind of quiet misalignment that makes a measurement mean
    nothing. Splitting at `Line` changes no geometry: `draw` drops its span at a
    `Line` command anyway, and only `origin.y` differs between the calls while
    every assertion below is about x.

    The pairing is checked rather than assumed -- a group whose quad count
    disagrees with its visible-glyph count raises.
    """
    from imgui_bundle import imgui

    groups: list[list[Any]] = []
    for cmd in commands:
        if isinstance(cmd, Line) or not groups:
            groups.append([])
        groups[-1].append(cmd)

    paired: list[tuple[Any, float, float, float]] = []
    for shipped_line in groups:
        glyphs = [cmd for cmd in shipped_line if isinstance(cmd, Glyph)]
        if not glyphs:
            continue
        origin = imgui.ImVec2(ORIGIN_X, 300.0 - px_from_sp(min(cmd.y for cmd in glyphs)))
        first = frame.vtx_buffer.size()
        draw(frame, shipped_line, origin, fonts=every_face)
        quads = [(near.pos.x, near.pos.y) for near, _far in _glyph_quads(frame, first)]
        drawn = [cmd for cmd in glyphs if _visible(every_face, cmd) is not None]
        assert len(quads) == len(drawn), (
            f"{len(quads)} quads for {len(drawn)} visible glyphs: the pairing this "
            "measurement depends on is broken, so nothing below means anything"
        )
        paired.extend(
            (cmd, origin.y, corner[0], corner[1]) for cmd, corner in zip(drawn, quads, strict=True)
        )
    return paired


def test_no_glyph_of_the_demo_document_is_drawn_more_than_a_pixel_from_its_position(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    A glyph's departure is bounded by its **span**, and the anchor resets it.

    A glyph's quad is its pen plus a left bearing of a whole number of texels, so
    `quad_left - x0` recovers the pen exactly and the distance from the position
    ship-out computed is how far the glyph moved.

    **This bound is no longer a constant and that is the cost of the advance
    rule.** While offsets were rounded against the anchor the answer was two
    roundings, 0.9862 px worst, however long the word. Accumulating rounded gaps
    instead means the residue of a span adds up along it, so the bound is a
    function of the longest word in the document rather than a property of the
    rule: measured here, **2.7359 px** worst over 4329 glyphs.

    That is a real regression on this axis and it was accepted for what it buys
    -- every gap within half a pixel of the design, every glyph on the pixel grid
    -- after the user compared the two rendered. `docs/advance-rule.md` has both
    sides.

    **The safety property is the second assertion, not the first.** A number
    measured off one document is a regression alarm, not a proof; what makes the
    rule safe is that the error cannot cross a glue node, because every span
    starts again from an anchor snapped straight from ship-out's own coordinate.
    So anchors are asserted against the tight half-pixel bound separately below,
    and that is the assertion that would catch the rule being widened from a span
    to a line.

    **This test used to assert 0.5 px and it kept passing when the bound became
    1 px.** It took the nearest of 4362 candidate pens and then subtracted
    `round(quad - pen)`, which folds any residue over a half into the other side
    of the pixel: a true departure of 0.9 was reported as 0.1. It was measuring
    "is the quad an integer distance from *some* pen", which every integral
    position satisfies. The pairing in `_drawn` is exact instead.
    """
    departures = []
    vertical = []
    by_cmd: dict[int, float] = {}
    for cmd, origin_y, quad_x, quad_y in _drawn(frame, every_face, demo_commands):
        baked, glyph = _visible(every_face, cmd)
        departures.append(abs((quad_x - glyph.x0) - (ORIGIN_X + px_from_sp(cmd.x))))
        by_cmd[id(cmd)] = departures[-1]
        # `add_text` measures its top-left down from ImGui's own ascent, so the
        # baseline a command asked for is the quad top, less the glyph's top
        # bearing, plus that ascent. Included because the horizontal assertion
        # cannot see a vertical defect at all: dropping the baked-ascent
        # difference from `_RigidSpan.pen` moves a glyph 2 px down inside a
        # mixed-face span and leaves every x-only assertion in this file green.
        vertical.append(abs((quad_y - glyph.y0 + baked.ascent) - (origin_y + px_from_sp(cmd.y))))
    assert len(departures) > 4000, "the demo document drew almost nothing, so this proves nothing"

    worst = max(departures)
    assert worst <= 3.0, (
        f"a glyph is drawn {worst:.4f} px from the position ship-out computed. The advance "
        "rule's accumulated residue is bounded by the longest span, and 3 px is well past "
        "what this document's longest word can produce -- so this is the error escaping a "
        "span, not a longer word"
    )
    worst_down = max(vertical)
    assert (
        worst_down <= 1.0
    ), f"a glyph's baseline is {worst_down:.4f} px below the one ship-out computed"

    # The safety property -- that the residue resets at every anchor -- is
    # `test_the_first_glyph_of_every_span_is_drawn_on_a_whole_pixel`, not here.
    # This test measures the magnitude; that one measures the independence, and
    # that one is what fails if the rule is ever widened from a span to a line.

    # The other side of it: the cost the user accepted is really being paid here,
    # so a silent revert to absolute snapping does not leave this test green.
    past_half = sum(1 for value in departures if value > 0.5 + 1e-9)
    assert past_half > 100, (
        f"only {past_half} glyphs are past half a pixel, so this document is no longer "
        "exercising span-relative placement and the bound above is not being tested"
    )


def _anchor_of(every_face: Any, span: Sequence[Any]) -> Any:
    """
    The command `draw` anchors a span on: its first glyph the bound face can raster.

    Not simply `span[0]`. A glyph with no raster draws nothing and so opens no
    anchor -- `test_a_glyph_the_face_cannot_raster_does_not_end_the_span` is the
    other half of that rule -- so the anchor can be the second command or later.
    Computed here rather than imported, so a change inside `_glyph` shows up as
    a disagreement instead of being mirrored into the expectation.
    """
    for cmd in span:
        if every_face(parse_font_key(cmd.font).face).is_glyph_in_font(cmd.codepoint):
            return cmd
    return None


def test_the_first_glyph_of_every_span_is_drawn_on_a_whole_pixel(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    The anchor stays whole. This is the assertion the user's rejection is written in.

    An earlier trial quantised the span *anchor* to halves as well as the
    offsets inside it, and the user threw it out on sight: "it really breaks
    with the 'W' being completely fuzzed while the 'h' looks pixel perfect". The
    leading glyph of every word was landing on one of two phases depending on
    where the word fell, which is exactly where the eye is best able to see it.
    So the leading glyph of every word must be drawn where whole-pixel snapping
    drew it, at one phase, and only the letters behind it may move by a half.

    `ORIGIN_X` is deliberately 40.25, off the grid, because at an integral origin
    every anchor is integral for a reason that has nothing to do with the code.
    That is asserted at the end rather than assumed.

    **The control used to be the glyphs inside the spans**, which sat at the half
    phase while the offset was quantised to halves. Under the advance rule
    nothing is fractional anywhere, so that control is gone and the test would be
    subsumed by `test_every_glyph_of_the_demo_document_lands_on_a_whole_pixel` if
    it stopped here. What keeps it distinct is the second assertion: an anchor is
    within half a pixel of the coordinate ship-out computed for it, which is a
    statement about *independence* from the preceding word rather than about the
    grid.

    A quad's left edge is the pen plus a left bearing of a whole number of
    texels, so subtracting `glyph.x0` recovers the pen exactly.
    """
    paired = _drawn(frame, every_face, demo_commands)
    drawn = {cmd: quad_x for cmd, _origin_y, quad_x, _quad_y in paired}
    assert len(drawn) == len(paired), "the command-to-quad mapping lost entries"

    anchors: list[float] = []
    anchor_exact: list[float] = []
    for span in _spans(demo_commands):
        anchor = _anchor_of(every_face, span)
        if anchor is None or anchor not in drawn:
            continue
        anchors.append(drawn[anchor] - _visible(every_face, anchor)[1].x0)
        anchor_exact.append(ORIGIN_X + px_from_sp(anchor.x))

    assert (
        len(anchors) > 300
    ), f"only {len(anchors)} spans drew their anchor, so this proves nothing"
    fuzzed = [pen for pen in anchors if pen != int(pen)]
    assert not fuzzed, (
        f"{len(fuzzed)} of {len(anchors)} span anchors are at a fractional x, e.g. "
        f"{fuzzed[:4]} -- this is the variant the user rejected on sight"
    )

    # The reset, which is the property this test now exists for. Each anchor is
    # snapped straight from ship-out's own coordinate, so it is within half a
    # pixel of it no matter how much residue the previous word accumulated.
    # Widen the advance rule from a span to a line and the residue carries across
    # glue nodes, anchors drift past half a pixel, and this is what says so --
    # the departure bound elsewhere would simply grow and keep passing.
    worst = max(abs(pen - exact) for pen, exact in zip(anchors, anchor_exact, strict=True))
    assert worst <= 0.5 + 1e-9, (
        f"a span anchor is {worst:.4f} px from the coordinate ship-out computed, so the "
        "accumulated residue of one word is reaching the next and the rule has escaped "
        "its span"
    )
    assert ORIGIN_X != int(ORIGIN_X), (
        f"ORIGIN_X is {ORIGIN_X}, a whole pixel, so every anchor would be integral for a "
        "reason that has nothing to do with _RigidSpan and the assertions above are free"
    )


def test_every_instance_of_a_rigid_span_is_drawn_at_the_same_shape(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    The claim the whole change exists for, against the implementation it replaced.

    A rigid span -- a run of glyphs with no glue in it -- has scaled-point
    offsets that depend only on its characters, their kerns and their sizes.
    Anchoring the span and snapping those offsets therefore yields the same
    pixel offsets wherever the span falls, so every instance of a word renders
    identically. Snapping each glyph's absolute position instead makes the
    offsets depend on the anchor's sub-pixel phase, and the same word sets at two
    shapes in two places.

    **The control is the old implementation, built here and asserted to fail**,
    which is the move `docs/status.md` section 5 records. Without it "every
    instance has one shape" would also pass on a document where no span occurs
    twice, or at an origin that happened to put every anchor on a pixel. The
    control says: on this fixture, at this origin, absolute snapping really does
    produce 67 two-shaped keys, and the shipped geometry produces none.
    """
    paired = _drawn(frame, every_face, demo_commands)
    drawn = {cmd: (quad_x, quad_y) for cmd, _origin_y, quad_x, quad_y in paired}
    assert len(drawn) == len(paired), (
        "two glyph commands compared equal, so the mapping from command to quad lost "
        "entries and the shapes below are not the ones that were drawn"
    )

    shapes: dict[Any, set[tuple[tuple[float, float], ...]]] = {}
    control: dict[Any, set[tuple[float, ...]]] = {}
    for span in _spans(demo_commands):
        visible = [cmd for cmd in span if cmd in drawn]
        if len(visible) < 2:
            continue
        key = (tuple(cmd.codepoint for cmd in span), tuple(cmd.font for cmd in span))
        left, top = drawn[visible[0]]
        shapes.setdefault(key, set()).add(
            tuple((drawn[cmd][0] - left, drawn[cmd][1] - top) for cmd in visible)
        )
        absolute = [snap_px(ORIGIN_X + px_from_sp(cmd.x)) for cmd in visible]
        control.setdefault(key, set()).add(tuple(pen - absolute[0] for pen in absolute))

    assert len(shapes) > 300, "too few distinct spans in the fixture to say anything"
    two_shaped = {key: value for key, value in control.items() if len(value) > 1}
    assert len(two_shaped) > 30, (
        f"absolute snapping gives {len(two_shaped)} two-shaped spans on this fixture, so "
        "it no longer distinguishes the two implementations and the assertion below is free"
    )

    inconsistent = {key: value for key, value in shapes.items() if len(value) > 1}
    assert not inconsistent, (
        f"{len(inconsistent)} spans render at more than one shape, e.g. "
        f"{''.join(chr(c) for c in next(iter(inconsistent))[0])!r} at "
        f"{sorted(next(iter(inconsistent.values())))}"
    )


def test_a_span_moved_by_a_fraction_of_a_pixel_keeps_its_shape(frame: Any, every_face: Any) -> None:
    """
    The same claim on one span, swept across a pixel, with nothing else in the way.

    Sixteen sub-pixel origins. The span's own position moves -- it must, it is
    being asked for somewhere else -- but the offsets *inside* it may not change
    at all. `docs/subpixel.md` §6.1 records this exact test failing before the
    change, with four distinct gap sequences for "line": `(3,4,7)`, `(4,3,7)`,
    `(4,3,8)`, `(4,4,7)`.

    Deliberately not the demo document: this one fails for a single obvious
    reason if it fails at all.
    """
    from imgui_bundle import imgui

    from advtext.nodes import CharNode

    key = font_key(Face.PROSE, sp_from_px(16.0))
    measure = char_measure(fontlib_metrics)
    word = hpack([CharNode(font=key, codepoint=ord(letter)) for letter in "line"], measure=measure)
    span = [cmd for cmd in ship(word.box, Point(0, 0), measure=measure) if isinstance(cmd, Glyph)]
    assert len(span) == 4, "the word did not ship as four glyphs"

    shapes = set()
    for step in range(16):
        first = frame.vtx_buffer.size()
        draw(frame, span, imgui.ImVec2(100.0 + step / 16.0, 200.0), fonts=every_face)
        quads = [near.pos.x for near, _far in _glyph_quads(frame, first)]
        assert len(quads) == len(span)
        shapes.add(tuple(quad - quads[0] for quad in quads))
    assert len(shapes) == 1, f"'line' set at {len(shapes)} distinct shapes across a pixel: {shapes}"


GAP_PX = 9.4
"""
A gap whose pixel width is nowhere near a whole number, in either direction.

At 9.4 px the second glyph of the pair below snaps to a different pixel at an
origin of 100.4 than at 100.9, which is what makes "did the anchor survive?" an
observable question rather than a coincidence.
"""


def _pair_shape(frame: Any, every_face: Any, cmds: Sequence[Any], origin_x: float) -> float:
    """
    The pixel distance between two drawn glyphs, at a given fractional origin.
    """
    from imgui_bundle import imgui

    first = frame.vtx_buffer.size()
    draw(frame, cmds, imgui.ImVec2(origin_x, 200.0), fonts=every_face)
    quads = [near.pos.x for near, _far in _glyph_quads(frame, first)]
    assert len(quads) == 2, f"{len(quads)} quads for a two-glyph fixture"
    return float(quads[1]) - float(quads[0])


def _pair(gap: int) -> tuple[Any, Any]:
    key = font_key(Face.PROSE, sp_from_px(16.0))
    return (
        Glyph(font=key, codepoint=ord("n"), x=0, y=0, index=0),
        Glyph(font=key, codepoint=ord("n"), x=gap, y=0, index=1),
    )


def test_a_space_inside_a_run_does_not_end_the_span(frame: Any, every_face: Any) -> None:
    """
    The unit is the rigid span, and "split the string on spaces" gets it wrong.

    `demo/sample.md` contains four spans with literal space *characters* in them
    -- the indentation of a fenced code block, where a space is a rigid
    `CharNode` carrying no stretch. Those are one rigid span each and the backend
    may not break them, because the offset across such a space is content: it is
    the space glyph's advance, the same everywhere the line appears.

    A word-based implementation splits exactly here, which is why the docstring
    on `_RigidSpan` says what the unit is and this says why it matters.
    """
    key = font_key(Face.PROSE, sp_from_px(16.0))
    with_space = [
        Glyph(font=key, codepoint=ord("n"), x=0, y=0, index=0),
        Glyph(font=key, codepoint=ord(" "), x=sp_from_px(4.7), y=0, index=1),
        Glyph(font=key, codepoint=ord("n"), x=sp_from_px(GAP_PX), y=0, index=2),
    ]
    shapes = {_pair_shape(frame, every_face, with_space, origin) for origin in (100.4, 100.9)}
    assert len(shapes) == 1, (
        f"a run containing a literal space character set at two widths {shapes} across a "
        "pixel boundary, so the space broke the span"
    )


@pytest.mark.parametrize(
    "separator",
    [
        pytest.param(
            SetGlue(
                x=0,
                y=0,
                width=sp_from_px(GAP_PX),
                natural=sp_from_px(GAP_PX),
                height=0,
                depth=0,
                index=0,
            ),
            id="glue",
        ),
        pytest.param(
            Line(x=0, y=0, width=sp_from_px(GAP_PX), height=0, depth=0, start=0, end=2),
            id="line",
        ),
        pytest.param(
            RuleRect(x=0, y=0, width=sp_from_px(GAP_PX), height=sp_from_px(1.0)),
            id="rule",
        ),
    ],
)
def test_anything_that_is_not_a_glyph_ends_the_span(
    frame: Any, every_face: Any, separator: Any
) -> None:
    """
    Three commands, three reasons, one rule: a span is a *maximal run* of glyphs.

    **Glue** must end it because glue is elastic -- its width is a justification
    decision rather than content, so an offset taken across it would depend on
    how far the line was stretched, which is the whole defect this change
    removes.

    **`Line`** must end it because a span that crossed one would anchor the first
    word of a line to the last word of the one above, and the distance between
    those is whatever the line breaker chose. This one is not hypothetical: the
    `Line` reset was ablated and the document-wide shape test above stayed green,
    because that test draws one shipped line per `draw` call and so cannot see a
    span crossing a line at all. This can.

    **`RuleRect`** is the weakest of the three -- a fraction bar between two math
    glyphs really is rigid -- and it ends the span anyway, so that the rule is
    one sentence rather than a list of exceptions. The cost is that the two
    halves of a fraction snap independently, which is half a pixel on a glyph
    that is already stacked rather than set in a line.
    """
    left, right = _pair(sp_from_px(GAP_PX))
    shapes = {
        _pair_shape(frame, every_face, [left, separator, right], origin)
        for origin in (100.4, 100.9)
    }
    assert len(shapes) == 2, (
        f"the anchor survived a {type(separator).__name__}: the pair set at one width "
        f"{shapes} either side of a pixel boundary"
    )
    # The control. Without it the assertion above passes on any fixture whose
    # two origins happen to snap apart for some unrelated reason.
    rigid = {_pair_shape(frame, every_face, [left, right], origin) for origin in (100.4, 100.9)}
    assert (
        len(rigid) == 1
    ), f"the same pair with nothing between them also set at two widths {rigid}"


def test_a_glyph_the_face_cannot_raster_does_not_end_the_span(frame: Any, every_face: Any) -> None:
    """
    A counted-and-not-drawn glyph is still rigid material, so the anchor outlives it.

    `DrawStats.missing` exists because `advtext.fontlib` mints private-use
    codepoints a face may have no raster for. Such a glyph draws nothing, which
    means it has no anchor of its own to offer -- but it is not a glue node, the
    run either side of it is one rigid span, and dropping the anchor there would
    make the glyph after it snap absolutely and set at two shapes.

    This path is not reachable from `demo/sample.md`, where every face is loaded
    through `imgui_font_file` and nothing is missing, so ablating it left the
    whole file green. It is reachable here.
    """
    from imgui_bundle import imgui

    key = font_key(Face.PROSE, sp_from_px(16.0))
    absent = 0xF0000
    assert not every_face(Face.PROSE).is_glyph_in_font(absent), "0xF0000 is in the prose face now"

    cmds = [
        Glyph(font=key, codepoint=ord("n"), x=0, y=0, index=0),
        Glyph(font=key, codepoint=absent, x=sp_from_px(4.7), y=0, index=1),
        Glyph(font=key, codepoint=ord("n"), x=sp_from_px(GAP_PX), y=0, index=2),
    ]
    stats = draw(frame, cmds, imgui.ImVec2(100.4, 200.0), fonts=every_face)
    assert stats.missing == 1 and stats.glyphs == 2, f"the fixture drew {stats}"

    shapes = {_pair_shape(frame, every_face, cmds, origin) for origin in (100.4, 100.9)}
    assert len(shapes) == 1, (
        f"a glyph with no raster ended the span: the pair either side of it set at two "
        f"widths {shapes} across a pixel boundary"
    )


def test_the_debug_overlay_lands_on_the_pixel_grid(frame: Any, every_face: Any) -> None:
    """
    `_debug_line` and `_debug_glue` run, and their geometry is snapped like the ink.

    `docs/status.md` section 5 records these two as the only functions in this
    module never reached by anything. Snapping changed both, so leaving them
    unreached would be a change nothing executes -- and an overlay a pixel off the
    baseline it annotates is read as the layout bug it exists to reveal, which is
    the one failure mode that makes the overlay worse than nothing.

    The origin is 0.35 and the coordinates are chosen so that every edge lands on
    a fraction: without snapping not one of the numbers below is an integer.
    """
    from imgui_bundle import imgui

    origin = imgui.ImVec2(0.35, 0.35)
    glue = SetGlue(
        x=sp_from_px(10.3),
        y=sp_from_px(50.4),
        width=sp_from_px(8.6),
        natural=sp_from_px(5.0),
        height=sp_from_px(12.2),
        depth=sp_from_px(3.3),
        index=0,
    )
    line = Line(
        x=sp_from_px(10.3),
        y=sp_from_px(100.4),
        width=sp_from_px(200.6),
        height=sp_from_px(12.2),
        depth=sp_from_px(3.3),
        start=0,
        end=1,
    )

    # Anti-aliasing off: `add_line` and `add_rect` widen an outline into a fringe
    # whose vertices sit at offsets of ImGui's choosing, which would hide the
    # coordinates under test behind ImGui's geometry rather than reveal anything.
    was = frame.flags
    frame.flags &= ~(
        imgui.ImDrawListFlags_.anti_aliased_lines.value
        | imgui.ImDrawListFlags_.anti_aliased_lines_use_tex.value
        | imgui.ImDrawListFlags_.anti_aliased_fill.value
    )
    try:
        first = frame.vtx_buffer.size()
        draw(frame, [glue], origin, fonts=every_face, debug=True)
        glue_box = _bounds(frame, first)

        first = frame.vtx_buffer.size()
        draw(frame, [line], origin, fonts=every_face, debug=True)
        line_box = _bounds(frame, first)
    finally:
        frame.flags = was

    # `_debug_glue` is a filled rect, so its four vertices *are* the snapped span.
    # 0.35 + 10.3 = 10.65 -> 11; + 8.6 = 19.25 -> 19; 0.35 + 50.4 - 12.2 = 38.55 -> 39;
    # 0.35 + 50.4 + 3.3 = 54.05 -> 54. Worked by hand rather than by calling `snap_px`,
    # which would make the assertion a restatement of the implementation.
    assert glue_box == (11.0, 19.0, 39.0, 54.0), f"the glue overlay is at {glue_box}"

    # `_debug_line` strokes an outline one pixel wide, so its bounds are the
    # snapped box give or take the half pixel the stroke is centred by.
    # 10.65 -> 11; 0.35 + 210.9 = 211.25 -> 211; 88.55 -> 89; 104.05 -> 104.
    for got, wanted in zip(line_box, (11.0, 211.0, 89.0, 104.0), strict=True):
        assert abs(got - wanted) <= 0.51, f"the line overlay is at {line_box}, wanted {wanted}"


def test_the_debug_overlay_draws_nothing_for_glue_at_its_natural_width(
    frame: Any, every_face: Any
) -> None:
    """
    The overlay's whole point is that a *stretched* space is the one you can see.
    """
    from imgui_bundle import imgui

    natural = SetGlue(
        x=sp_from_px(10.0),
        y=sp_from_px(50.0),
        width=sp_from_px(5.0),
        natural=sp_from_px(5.0),
        height=sp_from_px(12.0),
        depth=sp_from_px(3.0),
        index=0,
    )
    first = frame.vtx_buffer.size()
    draw(frame, [natural], imgui.ImVec2(0.0, 0.0), fonts=every_face, debug=True)
    assert frame.vtx_buffer.size() == first, "an unstretched space was painted"


def test_the_debug_overlay_is_off_unless_it_is_asked_for(frame: Any, every_face: Any) -> None:
    """
    The control: the assertions above would also pass if `debug` did nothing.
    """
    from imgui_bundle import imgui

    line = Line(
        x=sp_from_px(10.3),
        y=sp_from_px(100.4),
        width=sp_from_px(200.6),
        height=sp_from_px(12.2),
        depth=sp_from_px(3.3),
        start=0,
        end=1,
    )
    first = frame.vtx_buffer.size()
    draw(frame, [line], imgui.ImVec2(0.35, 0.35), fonts=every_face)
    assert frame.vtx_buffer.size() == first, "the overlay drew without being asked for"


def _bounds(draw_list: Any, first: int) -> tuple[float, float, float, float]:
    """
    The bounding box of every vertex appended from `first` onward.
    """
    xs = [draw_list.vtx_buffer[i].pos.x for i in range(first, draw_list.vtx_buffer.size())]
    ys = [draw_list.vtx_buffer[i].pos.y for i in range(first, draw_list.vtx_buffer.size())]
    assert xs, "nothing was appended at all"
    return min(xs), max(xs), min(ys), max(ys)


# --------------------------------------------------------------------------------
# The per-draw memo of the per-glyph preamble (`_Preambles`).
#
# These use fakes for the fonts and the draw list, and that is the right
# fidelity for what they ask. The *geometry* the memo must not change is pinned
# by every test above, which runs the memoised path through real ImGui and would
# go red on a moved vertex. What those tests cannot see is **how often** a
# question was asked or **whose** answer was used, because a real `ImFont`
# cannot be counted or swapped for one with a different ascent. Fakes can.
# --------------------------------------------------------------------------------


class _CountedBaked:
    """
    The two numbers `_baked` reads off an `ImFontBaked`.
    """

    def __init__(self, size: float, ascent: float) -> None:
        self.size = size
        self.ascent = ascent


class _CountedFont:
    """
    A stand-in `ImFont` that records every question `draw` asks of it.

    `rounding` mimics the one thing ImGui does to a requested size that matters
    here -- `GetFontBaked` quantises it -- so two keys at two sizes come back
    with two different baked sizes and a memo keyed too coarsely is caught.
    `ascent_per_px` is a plain multiplier so an expected `top` can be computed
    by hand.
    """

    def __init__(self, ascent_per_px: float = 0.75, absent: frozenset[int] = frozenset()) -> None:
        self.ascent_per_px = ascent_per_px
        self.absent = set(absent)
        self.bakes: list[float] = []
        self.probes: list[int] = []

    def is_glyph_in_font(self, codepoint: int) -> bool:
        self.probes.append(codepoint)
        return codepoint not in self.absent

    def get_font_baked(self, size_px: float) -> _CountedBaked:
        self.bakes.append(size_px)
        size = float(int(size_px + 0.5))
        return _CountedBaked(size=size, ascent=size * self.ascent_per_px)


class _RecordingDrawList:
    """
    A draw list that keeps the arguments of every `add_text` instead of drawing.

    `flags` is here because `draw` borrows and restores it; nothing else of an
    `ImDrawList` is reached by a list of glyphs.
    """

    def __init__(self) -> None:
        self.flags = 0
        self.texts: list[tuple[Any, float, float, float, str]] = []

    def add_text(self, font: Any, size: float, position: Any, _colour: int, text: str) -> None:
        self.texts.append((font, size, position.x, position.y, text))


class _SquareMetrics:
    """
    Metrics whose ascent plus descent equals the em, so `baked_size_px` is the identity.

    That makes the size ImGui is asked for the key's own size in pixels, which is
    what lets the assertions below state sizes outright.
    """

    ascent = 0.8
    descent = 0.2
    em = 1.0


def _counting_metrics() -> tuple[Any, list[str]]:
    """
    A `MetricsResolver` and the list of keys it has been asked for.
    """
    asked: list[str] = []

    def resolve(key: str) -> Any:
        asked.append(key)
        return _SquareMetrics()

    return resolve, asked


def _word(face: Face, size_px: float, text: str, *, x_px: float = 0.0, index: int = 0) -> list[Any]:
    """
    Abutting glyphs of one key, 10 px apart, on a baseline at y = 100 px.
    """
    key = font_key(face, sp_from_px(size_px))
    return [
        Glyph(
            font=key,
            codepoint=ord(character),
            x=sp_from_px(x_px + 10.0 * offset),
            y=sp_from_px(100.0),
            index=index + offset,
        )
        for offset, character in enumerate(text)
    ]


def test_the_preamble_is_resolved_once_per_font_key_and_not_once_per_glyph() -> None:
    """
    The memo exists: forty glyphs of two keys ask each constant question twice.

    Before `_Preambles`, `fonts` was called 40 times here, `metrics` 40 times and
    `get_font_baked` 40 times, and that re-derivation was most of a frame
    (`docs/guide/future.md` item 2). The counts below are the whole claim; a
    revert to the unmemoised `_glyph` fails every one of them.

    `is_glyph_in_font` is constant per (key, codepoint) rather than per key, so
    it is asked once per distinct character: "minimum" has four.
    """
    from imgui_bundle import imgui

    prose, code = _CountedFont(), _CountedFont()
    asked_faces: list[Face] = []

    def fonts(face: Face) -> Any:
        asked_faces.append(face)
        return {Face.PROSE: prose, Face.CODE: code}[face]

    metrics, asked_keys = _counting_metrics()
    cmds = [
        *(_word(Face.PROSE, 16.0, "minimum" * 4)),
        SetGlue(x=0, y=0, width=1, natural=1, height=1, depth=0, index=99),
        *(_word(Face.CODE, 14.0, "minimum" + "nnnnn", x_px=400.0, index=28)),
    ]
    draw_list = _RecordingDrawList()

    stats = draw(draw_list, cmds, imgui.ImVec2(0.0, 0.0), fonts=fonts, metrics=metrics)

    assert stats.glyphs == 40 and len(draw_list.texts) == 40
    assert asked_faces == [Face.PROSE, Face.CODE]
    assert asked_keys == [
        font_key(Face.PROSE, sp_from_px(16.0)),
        font_key(Face.CODE, sp_from_px(14.0)),
    ]
    assert prose.bakes == pytest.approx([16.0]) and code.bakes == pytest.approx([14.0])
    assert sorted(prose.probes) == sorted(map(ord, "minu"))
    assert sorted(code.probes) == sorted(map(ord, "minu"))


def test_drawing_runs_no_import_statement_per_glyph(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    How many `import` statements a draw executes does not depend on how many glyphs it draws.

    Review 5, item 6. `_glyph` reached `imgui.ImVec2` through `from
    imgui_bundle import imgui` in its own body, so every glyph went through
    `builtins.__import__` and the import machinery's `_handle_fromlist`:
    21,895 of those for five draws of `demo/sample.md` under cProfile, and
    15.9 ms a draw against 14.3 with the constructor handed in (one run of
    each, twenty draws, this machine). The count is what is pinned: 40 glyphs
    and 400 run the same imports, the ones `draw` itself makes once a call.
    """
    import builtins

    from imgui_bundle import imgui

    metrics, _ = _counting_metrics()
    imports: list[str] = []
    real = builtins.__import__

    def counting(name: str, *args: Any, **kwargs: Any) -> Any:
        imports.append(name)
        return real(name, *args, **kwargs)

    def drawn(repeats: int) -> tuple[int, list[Any]]:
        cmds = _word(Face.PROSE, 16.0, "minimum" * repeats)
        draw_list = _RecordingDrawList()
        font = _CountedFont()
        imports.clear()
        with monkeypatch.context() as patch:
            patch.setattr(builtins, "__import__", counting)
            stats = draw(
                draw_list, cmds, imgui.ImVec2(0.0, 0.0), fonts=lambda face: font, metrics=metrics
            )
        assert stats.glyphs == 7 * repeats
        return len(imports), draw_list.texts

    few, texts = drawn(4)
    many, _ = drawn(60)
    assert few == many, f"{few} imports for 28 glyphs and {many} for 420"
    assert many < 10
    assert [text[4] for text in texts] == list("minimum" * 4)


def test_two_sizes_of_one_face_do_not_share_a_preamble() -> None:
    """
    The memo is keyed by font key, not by face: a heading is not set at body size.

    This is the mistake a memo here is most likely to make, because `fonts` is
    asked by face and it is tempting to cache at the same grain. Both keys below
    resolve to the *same* `ImFont`; what differs is the size, and with it the
    baked ascent that places the top-left corner.
    """
    from imgui_bundle import imgui

    font = _CountedFont(ascent_per_px=0.75)
    metrics, _ = _counting_metrics()
    cmds = [
        *(_word(Face.PROSE, 16.0, "ab")),
        SetGlue(x=0, y=0, width=1, natural=1, height=1, depth=0, index=99),
        *(_word(Face.PROSE, 36.0, "ab", x_px=200.0, index=2)),
    ]
    draw_list = _RecordingDrawList()

    draw(draw_list, cmds, imgui.ImVec2(0.0, 0.0), fonts=lambda _face: font, metrics=metrics)

    assert [(size, top) for _font, size, _x, top, _text in draw_list.texts] == [
        (16.0, 88.0),
        (16.0, 88.0),
        (36.0, 73.0),
        (36.0, 73.0),
    ], "the baseline is at 100 px and the top-left is one baked ascent above it"
    assert font.bakes == pytest.approx([16.0, 36.0])


def test_nothing_about_the_fonts_survives_from_one_draw_to_the_next() -> None:
    """
    Reloading the fonts needs no invalidation call, because there is no memo to invalidate.

    Three things a host can do between two frames, each of which a memo held
    across frames would get wrong and each of which is silent when it is wrong:

    1. **Map the face to a different `ImFont`** -- an atlas cleared and rebuilt
       hands back new objects, and the old ones are freed.
    2. **Rebuild the same `ImFont` in place** so that it bakes a different
       ascent for the same size.
    3. **Change what the face can raster**, as loading through `imgui_font_file`
       instead of `font_file` does.

    The second draw must reflect all three with nothing called in between. The
    key and the commands are identical in both draws, so nothing but the
    lifetime of the memo can make this pass.
    """
    from imgui_bundle import imgui

    cmds = _word(Face.PROSE, 16.0, "ab")
    metrics, _ = _counting_metrics()
    origin = imgui.ImVec2(0.0, 0.0)

    before = _CountedFont(ascent_per_px=0.75)
    first = _RecordingDrawList()
    draw(first, cmds, origin, fonts=lambda _face: before, metrics=metrics)
    assert [(font, top, text) for font, _size, _x, top, text in first.texts] == [
        (before, 88.0, "a"),
        (before, 88.0, "b"),
    ]

    # 1. A new object for the same face.
    after = _CountedFont(ascent_per_px=0.5)
    second = _RecordingDrawList()
    draw(second, cmds, origin, fonts=lambda _face: after, metrics=metrics)
    assert [(font, top, text) for font, _size, _x, top, text in second.texts] == [
        (after, 92.0, "a"),
        (after, 92.0, "b"),
    ], "the second draw used a font or an ascent left over from the first"
    assert before.bakes == pytest.approx([16.0]), "the font that was replaced was asked again"

    # 2. The same object, baking differently.
    after.ascent_per_px = 0.25
    third = _RecordingDrawList()
    draw(third, cmds, origin, fonts=lambda _face: after, metrics=metrics)
    assert [top for _font, _size, _x, top, _text in third.texts] == [96.0, 96.0]

    # 3. The same object, now without one of the glyphs.
    after.absent.add(ord("a"))
    fourth = _RecordingDrawList()
    stats = draw(fourth, cmds, origin, fonts=lambda _face: after, metrics=metrics)
    assert (stats.glyphs, stats.missing) == (1, 1)
    assert [text for *_rest, text in fourth.texts] == ["b"]


def test_the_next_draw_honours_a_different_resolver_and_a_different_density() -> None:
    """
    `metrics` and `px_per_inch` are arguments of a call, so the memo is too.

    A window dragged to a display of another density changes `px_per_inch`
    between two frames with the same commands and the same fonts. The size asked
    of ImGui is `px_from_sp(size) * (ascent + descent) / em`, so both arguments
    reach it, and a memo that outlived the call would keep the old size.
    """
    from imgui_bundle import imgui

    class Tall:
        ascent, descent, em = 1.0, 0.5, 1.0

    font = _CountedFont()
    cmds = _word(Face.PROSE, 16.0, "a")
    origin = imgui.ImVec2(0.0, 0.0)
    square, _ = _counting_metrics()

    draw(_RecordingDrawList(), cmds, origin, fonts=lambda _face: font, metrics=square)
    draw(_RecordingDrawList(), cmds, origin, fonts=lambda _face: font, metrics=lambda _key: Tall())
    draw(
        _RecordingDrawList(),
        cmds,
        origin,
        fonts=lambda _face: font,
        metrics=square,
        px_per_inch=2 * DEFAULT_PX_PER_INCH,
    )

    assert font.bakes == pytest.approx([16.0, 24.0, 32.0])


def test_a_face_that_can_draw_nothing_is_never_measured_or_baked() -> None:
    """
    The memo is no more eager than the code it replaced.

    The unmemoised `_glyph` returned on a missing glyph *before* it consulted
    `metrics` or asked ImGui for an `ImFontBaked`. Resolving the whole preamble
    on first sight of a key would have been simpler and would have changed that:
    a face whose every glyph is missing would bake a size into the atlas that
    nothing draws, and a resolver that cannot measure the key would raise where
    it used not to be asked. The missing glyphs are still counted, once each,
    though the face is probed only once per codepoint.
    """
    from imgui_bundle import imgui

    font = _CountedFont(absent=frozenset(map(ord, "ab")))

    def unmeasurable(key: str) -> Any:
        raise AssertionError(f"{key!r} was measured though nothing of it can be drawn")

    draw_list = _RecordingDrawList()
    stats = draw(
        draw_list,
        _word(Face.PROSE, 16.0, "abab"),
        imgui.ImVec2(0.0, 0.0),
        fonts=lambda _face: font,
        metrics=unmeasurable,
    )

    assert (stats.glyphs, stats.missing) == (0, 4)
    assert font.bakes == [] and draw_list.texts == []
    assert font.probes == [ord("a"), ord("b")]


def test_a_face_reloaded_into_the_atlas_is_drawn_from_its_new_raster(
    frame: Any, imgui_context: Any
) -> None:
    """
    The same claim as the fakes make, once, against a real atlas.

    The same file is added to the atlas twice, which is what a host reloading
    its fonts does, and the same glyph is drawn at the same place through each
    in turn. The two `ImFont`s rasterise into different atlas rectangles, so the
    texture coordinates say which one a quad was drawn from: a memo that kept
    the first font would emit the second quad with the first one's `uv`.

    Positions are compared as well, and must agree -- same file, same size, same
    ascent -- so this also says the reload moved nothing.
    """
    imgui = imgui_context
    atlas = imgui.get_io().fonts
    path = str(fontlib.imgui_font_file(Face.PROSE))
    loaded = atlas.add_font_from_file_ttf(path, DISPLAY_SIZE_PX)
    reloaded = atlas.add_font_from_file_ttf(path, DISPLAY_SIZE_PX)
    cmds = _word(Face.PROSE, 16.0, "g")
    origin = imgui.ImVec2(20.0, 20.0)

    quads = []
    for font in (loaded, reloaded, loaded):
        first = frame.vtx_buffer.size()
        stats = draw(frame, cmds, origin, fonts=lambda _face, font=font: font)
        assert stats.glyphs == 1
        ((near, far),) = _glyph_quads(frame, first)
        quads.append(((near.pos.x, near.pos.y, far.pos.x, far.pos.y), (near.uv.x, near.uv.y)))

    (place_a, uv_a), (place_b, uv_b), (place_c, uv_c) = quads
    assert place_a == place_b == place_c
    assert uv_a != uv_b, "the reloaded face was drawn from the first face's raster"
    assert uv_c == uv_a, "going back to the first face did not go back to its raster"


# --------------------------------------------------------------------------------
# Ink per block role, and a palette that is not the light one.
#
# Two claims. A run of commands is drawn in the ink it is handed, with the
# geometry `draw` would have given it; and **every** colour that reaches the
# draw list was read from the palette, so a dark palette needs nothing but
# itself. The second is checked by recording colours rather than by reading the
# source for literals, which a later edit could add back.
# --------------------------------------------------------------------------------


class _ColouredDrawList(_RecordingDrawList):
    """
    `_RecordingDrawList`, also keeping the colour of everything it is asked to draw.
    """

    def __init__(self) -> None:
        super().__init__()
        self.inks: list[int] = []
        self.fills: list[int] = []
        self.strokes: list[int] = []

    def add_text(self, font: Any, size: float, position: Any, colour: int, text: str) -> None:
        super().add_text(font, size, position, colour, text)
        self.inks.append(colour)

    def add_rect_filled(self, _near: Any, _far: Any, colour: int) -> None:
        self.fills.append(colour)

    def add_rect(self, _near: Any, _far: Any, colour: int) -> None:
        self.strokes.append(colour)

    def add_line(self, _start: Any, _end: Any, colour: int, _thickness: float) -> None:
        self.strokes.append(colour)


def _drawn_runs(
    runs: Sequence[tuple[Sequence[Any], int]], palette: Palette, **kwargs: Any
) -> _ColouredDrawList:
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import draw_runs

    font = _CountedFont()
    resolve, _ = _counting_metrics()
    recorded = _ColouredDrawList()
    draw_runs(
        recorded,  # type: ignore[arg-type]
        runs,
        imgui.ImVec2(0.0, 0.0),
        fonts=lambda face: font,  # type: ignore[arg-type, return-value]
        palette=palette,
        metrics=resolve,
        **kwargs,
    )
    return recorded


def test_the_default_palette_names_no_roles_and_inks_every_kind_alike() -> None:
    from advtext.style import BlockKind

    assert DEFAULT_PALETTE.roles == ()
    assert {DEFAULT_PALETTE.ink_for(kind) for kind in BlockKind} == {DEFAULT_PALETTE.ink}
    # And it is still a value: hashable, comparable, safe to share.
    assert hash(DEFAULT_PALETTE) == hash(Palette())


def test_a_role_ink_applies_to_its_kind_and_to_no_other() -> None:
    from advtext.style import BlockKind

    red, green, blue = 0xFF0000FF, 0xFF00FF00, 0xFFFF0000
    palette = DEFAULT_PALETTE.with_roles({BlockKind.HEADING_1: red, BlockKind.CODE: green})
    assert palette.ink_for(BlockKind.HEADING_1) == red
    assert palette.ink_for(BlockKind.CODE) == green
    for kind in (BlockKind.HEADING_2, BlockKind.PARAGRAPH, BlockKind.QUOTE, BlockKind.TABLE):
        assert palette.ink_for(kind) == palette.ink
    # Adding roles keeps the ones already there, and a later one wins.
    more = palette.with_roles({BlockKind.CODE: blue, BlockKind.QUOTE: red})
    assert more.ink_for(BlockKind.HEADING_1) == red
    assert more.ink_for(BlockKind.CODE) == blue
    assert more.ink_for(BlockKind.QUOTE) == red
    # The order roles were given in is not part of the value.
    assert DEFAULT_PALETTE.with_roles(
        {BlockKind.CODE: green, BlockKind.HEADING_1: red}
    ) == DEFAULT_PALETTE.with_roles({BlockKind.HEADING_1: red, BlockKind.CODE: green})
    assert DEFAULT_PALETTE.roles == (), "with_roles returned a new palette"


def test_a_rule_cannot_be_given_a_role_ink_because_it_has_no_glyphs() -> None:
    from advtext.style import BlockKind

    with pytest.raises(ValueError, match="rule"):
        DEFAULT_PALETTE.with_roles({BlockKind.RULE: 0xFF0000FF})


def test_each_run_is_drawn_in_its_own_ink_at_the_geometry_draw_gives_it() -> None:
    red, green = 0xFF0000FF, 0xFF00FF00
    heading = [*_word(Face.PROSE_BOLD, 24.0, "Head")]
    body = [*_word(Face.PROSE, 16.0, "body", x_px=80.0, index=4)]
    split = _drawn_runs([(heading, red), (body, green)], DEFAULT_PALETTE)
    assert split.inks == [red] * 4 + [green] * 4

    # Splitting into runs moved nothing: same faces, sizes, positions, text as
    # one `draw` of the concatenated list -- which is one run in `palette.ink`.
    whole = _drawn_runs([([*heading, *body], DEFAULT_PALETTE.ink)], DEFAULT_PALETTE)
    assert [text[1:] for text in split.texts] == [text[1:] for text in whole.texts]
    assert whole.inks == [DEFAULT_PALETTE.ink] * 8


def test_draw_is_one_run_in_the_palettes_ink() -> None:
    from imgui_bundle import imgui

    font = _CountedFont()
    resolve, _ = _counting_metrics()
    word = _word(Face.PROSE, 16.0, "same")
    plain, as_run = _ColouredDrawList(), _ColouredDrawList()
    palette = Palette(ink=0xFF123456)
    draw(
        plain,  # type: ignore[arg-type]
        word,
        imgui.ImVec2(3.0, 4.0),
        fonts=lambda face: font,  # type: ignore[arg-type, return-value]
        palette=palette,
        metrics=resolve,
    )
    from advtext.backends.imgui_draw import draw_runs

    draw_runs(
        as_run,  # type: ignore[arg-type]
        [(word, palette.ink)],
        imgui.ImVec2(3.0, 4.0),
        fonts=lambda face: font,  # type: ignore[arg-type, return-value]
        palette=palette,
        metrics=resolve,
    )
    assert plain.texts == as_run.texts
    assert plain.inks == as_run.inks == [0xFF123456] * 4


def test_the_font_preamble_is_shared_by_every_run_of_one_call() -> None:
    # The reason there is one `draw_runs` and not a `draw` per block: forty
    # blocks in one face ask for that face once.
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import draw_runs

    font = _CountedFont()
    asked: list[Face] = []

    def fonts(face: Face) -> Any:
        asked.append(face)
        return font

    resolve, keys = _counting_metrics()
    runs = [
        (_word(Face.PROSE, 16.0, "word", x_px=50.0 * n, index=4 * n), 0xFF000000 + n)
        for n in range(40)
    ]
    recorded = _ColouredDrawList()
    draw_runs(
        recorded,  # type: ignore[arg-type]
        runs,
        imgui.ImVec2(0.0, 0.0),
        fonts=fonts,
        metrics=resolve,
    )
    assert len(recorded.texts) == 160
    assert asked == [Face.PROSE]
    assert len(keys) == 1
    assert len(font.bakes) == 1


def test_every_colour_drawn_comes_from_the_palette_it_was_given() -> None:
    # A palette of colours that appear nowhere else, the debug overlay on, a
    # highlight, a rule and glyphs: whatever reaches the draw list must be one
    # of them. A literal colour anywhere in the draw path fails this.
    from advtext.selection import Rect

    palette = Palette(
        page=0xA0000001,
        ink=0xA0000002,
        rule=0xA0000003,
        highlight=0xA0000004,
        debug_box=0xA0000005,
        debug_baseline=0xA0000006,
        debug_stretched=0xA0000007,
        debug_shrunk=0xA0000008,
        link=0xA0000009,
    )
    px = sp_from_px
    cmds: list[Any] = [
        Line(x=0, y=px(100.0), width=px(300.0), height=px(12.0), depth=px(4.0), start=0, end=6),
        *_word(Face.PROSE, 16.0, "ab"),
        SetGlue(
            x=px(20.0), y=px(100.0), width=px(9.0), natural=px(6.0), height=0, depth=0, index=2
        ),
        *_word(Face.PROSE, 16.0, "cd", x_px=30.0, index=3),
        SetGlue(
            x=px(50.0), y=px(100.0), width=px(3.0), natural=px(6.0), height=0, depth=0, index=5
        ),
        RuleRect(x=0, y=px(120.0), width=px(300.0), height=px(1.0)),
    ]
    highlight = Rect(x=0, y=px(88.0), width=px(40.0), height=px(16.0))
    recorded = _drawn_runs([(cmds, 0xA000000A)], palette, highlights=[highlight], debug=True)

    assert set(recorded.inks) == {0xA000000A}, "glyphs take the run's ink, not the palette's"
    assert recorded.fills.count(palette.highlight) == 1
    assert recorded.fills.count(palette.rule) == 1
    assert set(recorded.fills) == {
        palette.highlight,
        palette.rule,
        palette.debug_stretched,
        palette.debug_shrunk,
    }
    assert set(recorded.strokes) == {palette.debug_box, palette.debug_baseline}


def test_the_dark_palette_is_legible_on_its_own_page_and_is_not_the_light_one() -> None:
    from advtext.backends.imgui_draw import DARK_PALETTE

    assert _contrast(DARK_PALETTE.ink, DARK_PALETTE.page) >= 4.5
    assert _contrast(DARK_PALETTE.link, DARK_PALETTE.page) >= 4.5
    assert _contrast(DARK_PALETTE.rule, DARK_PALETTE.page) >= 3.0
    # The light ink on the dark page is the failure `Palette` warns about.
    assert _contrast(DEFAULT_PALETTE.ink, DARK_PALETTE.page) < 4.5
    assert DARK_PALETTE.roles == ()


# --------------------------------------------------------------------------------
# Colour finer than a run: ink ranges over glyph indices, and extra fills.
# --------------------------------------------------------------------------------


class _OrderedDrawList(_ColouredDrawList):
    """
    `_ColouredDrawList`, also keeping the order fills and glyphs arrived in.
    """

    def __init__(self) -> None:
        super().__init__()
        self.order: list[tuple[str, int]] = []

    def add_text(self, font: Any, size: float, position: Any, colour: int, text: str) -> None:
        super().add_text(font, size, position, colour, text)
        self.order.append(("text", colour))

    def add_rect_filled(self, near: Any, far: Any, colour: int) -> None:
        super().add_rect_filled(near, far, colour)
        self.order.append(("fill", colour))
        self.rects = [*getattr(self, "rects", []), (near.x, near.y, far.x, far.y)]


def _drawn_with(recorded: Any, runs: Sequence[tuple[Sequence[Any], int]], **kwargs: Any) -> Any:
    from imgui_bundle import imgui

    from advtext.backends.imgui_draw import draw_runs

    font = _CountedFont()
    resolve, _ = _counting_metrics()
    draw_runs(
        recorded,
        runs,
        imgui.ImVec2(0.0, 0.0),
        fonts=lambda face: font,  # type: ignore[arg-type, return-value]
        metrics=resolve,
        **kwargs,
    )
    return recorded


def test_an_ink_range_recolours_exactly_the_glyphs_whose_index_is_in_it() -> None:
    red, green, body = 0xFF0000FF, 0xFF00FF00, 0xFF101010
    word = _word(Face.PROSE, 16.0, "abcdefgh")
    recorded = _drawn_with(_ColouredDrawList(), [(word, body)], inks=[(1, 3, red), (5, 6, green)])
    assert recorded.inks == [body, red, red, body, body, green, body, body]
    # Half-open, like every other range here: index 3 and index 6 are not in.
    # And nothing moved: the same calls as with no ranges at all.
    plain = _drawn_with(_ColouredDrawList(), [(word, body)])
    assert [text[1:] for text in recorded.texts] == [text[1:] for text in plain.texts]
    assert plain.inks == [body] * 8


def test_ink_ranges_are_by_index_whichever_run_the_glyph_is_in() -> None:
    red = 0xFF0000FF
    first = _word(Face.PROSE, 16.0, "abcd")
    second = _word(Face.PROSE, 16.0, "efgh", x_px=60.0, index=4)
    recorded = _drawn_with(
        _ColouredDrawList(), [(first, 0xFF000001), (second, 0xFF000002)], inks=[(3, 5, red)]
    )
    assert recorded.inks == [0xFF000001] * 3 + [red, red] + [0xFF000002] * 3


def test_extra_fills_go_under_the_selection_and_under_the_glyphs_in_their_own_colours() -> None:
    from advtext.selection import Rect

    px = sp_from_px
    mark, underline, body = 0xFF00BFFF, 0xFFFF0000, 0xFF101010
    word = _word(Face.PROSE, 16.0, "ab")
    fills = [
        (Rect(x=0, y=px(88.0), width=px(20.0), height=px(16.0)), mark),
        (Rect(x=0, y=px(102.3), width=px(20.0), height=px(0.6)), underline),
    ]
    selection = Rect(x=0, y=px(88.0), width=px(10.0), height=px(16.0))
    recorded = _drawn_with(_OrderedDrawList(), [(word, body)], fills=fills, highlights=[selection])
    assert recorded.order == [
        ("fill", mark),
        ("fill", underline),
        ("fill", DEFAULT_PALETTE.highlight),
        ("text", body),
        ("text", body),
    ]
    # The underline is thinner than a pixel and off the grid. It keeps a whole
    # pixel, on the grid, as a rule would.
    left, top, right, bottom = recorded.rects[1]
    assert (left, right) == (0.0, 20.0)
    assert bottom - top == 1.0 and top == float(int(top))


# -- the diff roles -----------------------------------------------------------


def test_a_palette_carries_the_diff_roles_and_a_dark_one_carries_dark_ones() -> None:
    from dataclasses import fields, replace

    from advtext.backends.imgui_draw import (
        DARK_DIFF_PALETTE,
        DARK_PALETTE,
        DEFAULT_DIFF_PALETTE,
        DiffPalette,
    )

    assert DEFAULT_PALETTE.diff is DEFAULT_DIFF_PALETTE == DiffPalette()
    assert DARK_PALETTE.diff is DARK_DIFF_PALETTE != DEFAULT_DIFF_PALETTE
    # The roles C-diffview was asked for, by name: four inks, two bands, the
    # intra-line marks, the gutter and the headers.
    names = {field.name for field in fields(DiffPalette)}
    assert names >= {
        "add",
        "remove",
        "context",
        "meta",
        "add_fill",
        "remove_fill",
        "add_emphasis",
        "remove_emphasis",
        "gutter",
        "header",
    }
    # A value like the rest of the palette: hashable, and a host replaces one
    # role without restating the others.
    mine = replace(DEFAULT_PALETTE, diff=replace(DEFAULT_DIFF_PALETTE, add=0xFF00FF00))
    assert hash(mine) != hash(DEFAULT_PALETTE) and mine.diff.remove == DEFAULT_DIFF_PALETTE.remove
    assert mine.ink == DEFAULT_PALETTE.ink


def test_added_and_removed_are_told_apart_by_more_than_one_role_in_both_defaults() -> None:
    """
    What is checked is that the roles differ, light and dark: ink, band and
    mark each. Whether they can be told apart *by eye* is not checked and is
    not the point -- the view draws `+` and `-` for that, and
    `tests/test_diff_view.py` holds it to them.
    """
    from advtext.backends.imgui_draw import DARK_DIFF_PALETTE, DEFAULT_DIFF_PALETTE

    for colours in (DEFAULT_DIFF_PALETTE, DARK_DIFF_PALETTE):
        assert colours.add != colours.remove
        assert colours.add_fill != colours.remove_fill
        assert colours.add_emphasis != colours.remove_emphasis
        # A band is translucent, so it tints the host's background, and the
        # mark over it is stronger than the band.
        for band, mark in (
            (colours.add_fill, colours.add_emphasis),
            (colours.remove_fill, colours.remove_emphasis),
        ):
            assert (band >> 24) < 0xFF and (mark >> 24) > (band >> 24)


# ---------------------------------------------------------------------------
# Review 3, item 7: every diff ink on every ground it is drawn on
# ---------------------------------------------------------------------------

DIFF_INK_GROUNDS = {
    # ink: the grounds `advtext.ui.diff_view.DiffView.frame_plan` draws it on.
    "gutter": ("page", "add_fill", "remove_fill"),  # line numbers and the +/- marker
    "add": ("add_fill", "add_emphasis"),
    "remove": ("remove_fill", "remove_emphasis"),
    "context": ("page",),
    # The no-newline row; a collapsed-context and a folded row (on the header
    # band); the end-of-line mark, which is on added and removed rows.
    "meta": ("page", "header_fill", "add_fill", "remove_fill"),
    "header": ("header_fill",),
    # The header's warnings, and a placeholder wherever a character can be.
    "warning": (
        "page",
        "header_fill",
        "add_fill",
        "remove_fill",
        "add_emphasis",
        "remove_emphasis",
    ),
}


def _rgba_parts(colour: int) -> tuple[int, int, int, int]:
    return colour & 255, colour >> 8 & 255, colour >> 16 & 255, colour >> 24 & 255


def _over(colour: int, ground: tuple[float, ...]) -> tuple[float, ...]:
    red, green, blue, alpha = _rgba_parts(colour)
    t = alpha / 255
    return tuple(t * c + (1 - t) * g for c, g in zip((red, green, blue), ground, strict=True))


def _luminance(rgb: tuple[float, ...]) -> float:
    def linear(value: float) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])


def ratio_of(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """WCAG 2 contrast ratio of two opaque colours."""
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def diff_contrasts(palette: Palette) -> dict[tuple[str, str], float]:
    """
    The contrast of each diff ink on each ground it is drawn on, the fills
    composited as the view draws them: a band over the page, an emphasis
    mark over its band.
    """
    page = tuple(float(c) for c in _rgba_parts(palette.page)[:3])
    colours = palette.diff
    grounds = {
        "page": page,
        "header_fill": _over(colours.header_fill, page),
        "add_fill": _over(colours.add_fill, page),
        "remove_fill": _over(colours.remove_fill, page),
    }
    grounds["add_emphasis"] = _over(colours.add_emphasis, grounds["add_fill"])
    grounds["remove_emphasis"] = _over(colours.remove_emphasis, grounds["remove_fill"])
    return {
        (ink, ground): ratio_of(
            tuple(float(c) for c in _rgba_parts(getattr(colours, ink))[:3]), grounds[ground]
        )
        for ink, on in DIFF_INK_GROUNDS.items()
        for ground in on
    }


@pytest.mark.parametrize("palette", [DEFAULT_PALETTE, DARK_PALETTE], ids=["light", "dark"])
def test_every_diff_ink_is_at_least_4_5_to_1_on_every_ground_it_is_drawn_on(
    palette: Palette,
) -> None:
    """
    A number, not a statement about how anything looks. The `+`/`-` marker
    is the channel that does not depend on hue, and it was 4.17 and 3.91 to
    1 on the light bands (4.36 and 4.46 on the dark); the warning ink was
    under on the header band and far under on an emphasis mark, which is
    exactly where the placeholder for an added invisible character is drawn.
    """
    found = diff_contrasts(palette)
    assert len(found) == 19
    low = {pair: round(ratio, 2) for pair, ratio in found.items() if ratio < 4.5}
    assert low == {}


def test_the_contrast_arithmetic_is_the_standard_one() -> None:
    assert round(ratio_of((0.0, 0.0, 0.0), (255.0, 255.0, 255.0)), 2) == 21.0
    assert round(ratio_of((119.0, 119.0, 119.0), (255.0, 255.0, 255.0)), 2) == 4.48  # #777 fails
    assert _over(0x80FFFFFF, (0.0, 0.0, 0.0))[0] == pytest.approx(128.0)

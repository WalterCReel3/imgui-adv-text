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
    DEFAULT_PALETTE,
    PEN_QUANTUM_PX,
    Palette,
    baked_size_px,
    draw,
    snap_offset_px,
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


def test_every_glyph_of_the_demo_document_lands_on_the_half_pixel_grid(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    Every glyph quad's horizontal corners are exact multiples of `PEN_QUANTUM_PX`.

    **This test used to assert integers, and the control below is the reason it
    is not simply a loosened version of that.** "A multiple of 0.5" is satisfied
    by every integer, so on its own this assertion passes unchanged for the
    whole-pixel implementation it replaces -- it would go green on a revert and
    say nothing. The second half asserts that a real share of the document is at
    the *half* phase, which only the shipped rule can produce, and which also
    fails if `ImDrawListFlags_TextNoPixelSnap` is ever dropped: ImGui's
    `IM_TRUNC` would round every half back to a whole underneath us and leave
    the first assertion green.

    The exactness matters as much as the quantum. `snap_offset_px` multiplies by
    a power of two, so its output is exactly representable and `x * 2 ==
    int(x * 2)` is not a tolerance dressed up as an equality.
    """
    from imgui_bundle import imgui

    first = frame.vtx_buffer.size()
    stats = draw(frame, demo_commands, imgui.ImVec2(40.0, 30.0), fonts=every_face)
    assert stats.glyphs > 1000, "the demo document shipped almost nothing, so this proves nothing"

    edges = [value for near, far in _glyph_quads(frame, first) for value in (near.pos.x, far.pos.x)]
    assert len(edges) > 2000, f"only {len(edges)} quad edges, so this fixture proves nothing"

    off_grid = [value for value in edges if value * 2.0 != int(value * 2.0)]
    assert not off_grid, (
        f"{len(off_grid)} glyph quad edges are off the {PEN_QUANTUM_PX} px grid: " f"{off_grid[:4]}"
    )

    on_a_half = [value for value in edges if value != int(value)]
    assert len(on_a_half) > 200, (
        f"only {len(on_a_half)} of {len(edges)} quad edges are at the half phase, so this "
        "document is being drawn at whole pixels and the assertion above is free"
    )


def test_a_glyph_sits_on_a_whole_pixel_row(
    frame: Any, every_face: Any, demo_commands: tuple[Any, ...]
) -> None:
    """
    Half a pixel got into the document horizontally and nowhere else.

    The horizontal control in the same buffer is what makes this worth
    asserting: the fixture demonstrably *can* produce a fractional coordinate
    here, and every vertical one is still whole.

    **What this test does not establish, stated because it was written believing
    it did.** It does not pin the axis asymmetry in `_RigidSpan.pen`. Swapping
    `snap_px` for `snap_offset_px` on the vertical leaves it green, because
    every within-span vertical offset in this document is already a whole number
    of pixels -- measured, 3486 of 3486, and 2 of 2 in the litmus formula -- so
    the two rules cannot disagree on any content the demo contains.
    `test_a_vertical_offset_inside_a_span_stays_on_a_whole_row` builds content
    where they do disagree; that is the test that pins the choice.
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
    assert any(
        near.pos.x != int(near.pos.x) for near, _far in quads
    ), "not one glyph is at a fractional x here, so the vertical assertion above is free"


def test_a_vertical_offset_inside_a_span_stays_on_a_whole_row(frame: Any, every_face: Any) -> None:
    """
    The quantum is horizontal only, on content that can tell the two apart.

    `_RigidSpan.pen` halves the horizontal offset and leaves the vertical whole.
    The reason is that the defect the user reported and judged is horizontal --
    inter-letter gaps of 1, 2, 2 px in "people", `iffe` fused in a heading -- and
    a half-pixel baseline would put a stem's horizontal edges between two rows
    for no gap it closes. Nobody has looked at that trade, so it is not taken.

    A raised glyph inside a rigid span is a math script, and `ship` really does
    emit one with no glue before it. The fixture is that arrangement with the
    offset chosen to land between two rows: 5.4 px goes to 5.0 under whole-pixel
    snapping and to 5.5 under the half-pixel rule, so this is one assertion and
    not two.

    The horizontal is asserted beside it from the same pair, because a test that
    only said "y is whole" would also pass if the quantum had been dropped
    altogether.
    """
    from imgui_bundle import imgui

    key = font_key(Face.PROSE, sp_from_px(16.0))
    raised = [
        Glyph(font=key, codepoint=ord("n"), x=0, y=0, index=0),
        Glyph(font=key, codepoint=ord("n"), x=sp_from_px(GAP_PX), y=sp_from_px(-5.4), index=1),
    ]
    assert snap_px(-5.4) == -5.0 and snap_offset_px(-5.4) == -5.5, "the fixture lost its point"

    first = frame.vtx_buffer.size()
    draw(frame, raised, imgui.ImVec2(100.0, 200.0), fonts=every_face)
    quads = [(near.pos.x, near.pos.y) for near, _far in _glyph_quads(frame, first)]
    assert len(quads) == 2, f"{len(quads)} quads for a two-glyph fixture"

    assert quads[1][1] - quads[0][1] == -5.0, (
        f"the raised glyph came out {quads[1][1] - quads[0][1]} px above its span anchor "
        "rather than 5, so a vertical offset is being quantised to halves"
    )
    assert quads[1][0] - quads[0][0] == 9.5, (
        f"the same pair is {quads[1][0] - quads[0][0]} px apart horizontally rather than "
        "9.5, so the half-pixel quantum is not reaching this fixture at all"
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


def test_snap_offset_px_is_snap_px_on_a_finer_grid() -> None:
    """
    The same half-up rule, so the two agree about which side of a boundary a value is on.

    The last line is the one that would catch a re-implementation as
    `round(v * 2) / 2`: Python's `round` is banker's and sends 0.25 to 0.0 where
    half-up sends it to 0.5.
    """
    assert PEN_QUANTUM_PX == 0.5, "the quantum changed; every number below is about 0.5"
    assert [snap_offset_px(v) for v in (0.0, 0.2, 0.25, 0.3, 0.74, 0.75, 9.4)] == [
        0.0,
        0.0,
        0.5,
        0.5,
        0.5,
        1.0,
        9.5,
    ]
    assert snap_offset_px(-0.25) == 0.0 and snap_offset_px(-0.26) == -0.5
    # Exactly representable, so the grid assertions elsewhere are equalities and
    # not tolerances: a multiple of a power of two survives a float multiply.
    assert all(
        snap_offset_px(v / 64.0) * 2.0 == int(snap_offset_px(v / 64.0) * 2.0) for v in range(400)
    )
    assert round(0.25 * 2) / 2 == 0.0 and snap_offset_px(0.25) == 0.5


def test_a_half_pixel_pen_survives_into_the_vertex_buffer(frame: Any, every_face: Any) -> None:
    """
    `draw` sets `ImDrawListFlags_TextNoPixelSnap`, and without it the change is a no-op.

    `ImFont::RenderText` opens with `IM_TRUNC(pos.x)`, so a pen at x + 0.5 emits
    its quad at x unless the flag is set. That failure has no symptom of its own
    -- every position is still an integer, still one texel to one pixel, still
    the same shape wherever the word falls -- so it would look exactly like a
    revert to whole-pixel snapping with all the code still in place.

    The control is the same draw list with the flag cleared, driven through
    `add_text` directly: it shows this build really does truncate, so the
    assertion above is about the flag and not about a coincidence.
    """
    from imgui_bundle import imgui

    left, right = _pair(sp_from_px(GAP_PX))
    assert snap_offset_px(GAP_PX) == 9.5, "the fixture no longer lands on a half"

    first = frame.vtx_buffer.size()
    draw(frame, [left, right], imgui.ImVec2(100.0, 200.0), fonts=every_face)
    quads = [near.pos.x for near, _far in _glyph_quads(frame, first)]
    assert len(quads) == 2, f"{len(quads)} quads for a two-glyph fixture"
    assert quads[1] - quads[0] == 9.5, (
        f"the two glyphs came out {quads[1] - quads[0]} px apart rather than 9.5, so the "
        "half-pixel offset was re-rounded before it reached the buffer"
    )

    assert (
        frame.flags & int(imgui.ImDrawListFlags_.text_no_pixel_snap) == 0
    ), "`draw` left the no-snap flag on a draw list it borrowed"
    font = every_face(parse_font_key(left.font).face)
    before = frame.vtx_buffer.size()
    frame.add_text(font, 16.0, imgui.ImVec2(quads[0] + 9.5, 200.0), 0xFF111111, "n")
    truncated = frame.vtx_buffer[before].pos.x
    assert truncated == int(truncated), (
        "this ImGui build no longer truncates a fractional pen, so the flag `draw` sets "
        "is no longer load-bearing and the assertion above proves nothing"
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
    Span-relative snapping costs two roundings, and two roundings is the whole cost.

    A glyph's quad is its pen plus a left bearing of a whole number of texels,
    so `quad_left - x0` recovers the pen exactly and the distance from the
    position ship-out computed is how far the glyph moved. Anchoring a span and
    snapping an offset from it rounds twice, so the bound is 1 px rather than the
    0.5 px absolute snapping gives. Measured: **0.9862 px** worst over 4329
    glyphs, which is T11's predicted 0.986 and not a pixel more. It does not grow
    with the length of the span or the line, which is what separates this from
    rounding advances and summing them.

    **This test used to assert 0.5 px and it kept passing when the bound became
    1 px.** It took the nearest of 4362 candidate pens and then subtracted
    `round(quad - pen)`, which folds any residue over a half into the other side
    of the pixel: a true departure of 0.9 was reported as 0.1. It was measuring
    "is the quad an integer distance from *some* pen", which every integral
    position satisfies. The pairing in `_drawn` is exact instead, and the
    assertion below is one-sided against the real bound.
    """
    departures = []
    vertical = []
    for cmd, origin_y, quad_x, quad_y in _drawn(frame, every_face, demo_commands):
        baked, glyph = _visible(every_face, cmd)
        departures.append(abs((quad_x - glyph.x0) - (ORIGIN_X + px_from_sp(cmd.x))))
        # `add_text` measures its top-left down from ImGui's own ascent, so the
        # baseline a command asked for is the quad top, less the glyph's top
        # bearing, plus that ascent. Included because the horizontal assertion
        # cannot see a vertical defect at all: dropping the baked-ascent
        # difference from `_RigidSpan.pen` moves a glyph 2 px down inside a
        # mixed-face span and leaves every x-only assertion in this file green.
        vertical.append(abs((quad_y - glyph.y0 + baked.ascent) - (origin_y + px_from_sp(cmd.y))))
    assert len(departures) > 4000, "the demo document drew almost nothing, so this proves nothing"

    worst = max(departures)
    assert worst <= 1.0, (
        f"a glyph is drawn {worst:.4f} px from the position ship-out computed, which is "
        "more than the two roundings span-relative snapping is allowed"
    )
    worst_down = max(vertical)
    assert (
        worst_down <= 1.0
    ), f"a glyph's baseline is {worst_down:.4f} px below the one ship-out computed"
    # The other side of it, and the reason the assertion above is not the old one
    # with a looser number: the cost the user accepted is really being paid here,
    # so a silent revert to absolute snapping does not leave this test green.
    past_half = sum(1 for value in departures if value > 0.5 + 1e-9)
    assert past_half > 100, (
        f"only {past_half} glyphs are past half a pixel, so this document is no longer "
        "exercising span-relative snapping and the bound above is not being tested"
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

    `ORIGIN_X` is deliberately 40.25, off the grid, because at an integral
    origin every anchor is integral for a reason that has nothing to do with the
    code. The control is the other list: the glyphs *inside* the spans, in the
    same buffer at the same origin, really are at the half phase -- so "no
    anchor is fractional" is a property of `_RigidSpan` and not of this fixture.

    A quad's left edge is the pen plus a left bearing of a whole number of
    texels, so subtracting `glyph.x0` recovers the pen exactly.
    """
    paired = _drawn(frame, every_face, demo_commands)
    drawn = {cmd: quad_x for cmd, _origin_y, quad_x, _quad_y in paired}
    assert len(drawn) == len(paired), "the command-to-quad mapping lost entries"

    anchors: list[float] = []
    inside: list[float] = []
    for span in _spans(demo_commands):
        anchor = _anchor_of(every_face, span)
        for cmd in span:
            if cmd not in drawn:
                continue
            pen = drawn[cmd] - _visible(every_face, cmd)[1].x0
            (anchors if cmd is anchor else inside).append(pen)

    assert (
        len(anchors) > 300
    ), f"only {len(anchors)} spans drew their anchor, so this proves nothing"
    fuzzed = [pen for pen in anchors if pen != int(pen)]
    assert not fuzzed, (
        f"{len(fuzzed)} of {len(anchors)} span anchors are at a fractional x, e.g. "
        f"{fuzzed[:4]} -- this is the variant the user rejected on sight"
    )

    halved = [pen for pen in inside if pen != int(pen)]
    assert len(halved) > 100, (
        f"only {len(halved)} of {len(inside)} non-anchor glyphs are at the half phase, so "
        "nothing here distinguishes a whole anchor from a whole everything"
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

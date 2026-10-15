r"""
Typeset text under Dear ImGui's two kinds of display scaling (pptmstr's P47, the plan's A5).

**The size a theme is asked at (P47).** pptmstr measured that Dear ImGui's
`get_font_size()` read BETWEEN frames leaves out `style.font_scale_main` and
`style.font_scale_dpi` (16 there, 18 inside a frame at a dpi scale of 1.1),
so a host that sized its themes from it set typeset text smaller than its
own labels at 110 to 150 % on Windows and Linux. Measured here, headless:
the same, and a theme does not follow either scale: it is in Dear ImGui's
units and is set at exactly its size (`imscribe.theme`, "Which size a theme
expects"). What is held:

- the recipe the theme module gives: inside a frame `get_font_size()` is
  `round_half_up(base * main * dpi)`, between frames it is the base, and
  before the first frame it is 0;
- a theme sized with `at_pixel_height` at the size drawn sets its prose's
  capital H exactly as tall as Dear ImGui's own label in the same face, at
  every scale; a theme built once does not move;
- a size of 0 (or anything not a positive number) is a `ValueError` at the
  theme. It was a `ZeroDivisionError` out of `TypesetView` before.

**A fractional framebuffer scale (A5).** The views round their origin, a
diff's panes and a code block's indent to whole UNITS; at
`io.display_framebuffer_scale` 1.5 a whole unit is not a whole framebuffer
pixel. Measured headless at 1, 1.5 and 2, for the diff view unified and side
by side and for a fenced block: every pen is on the framebuffer's grid,
every step along a row is the cell, and every column holds. What 1.5 does
cost: where the code's left edge is an odd unit (x.5 framebuffer pixels) the
library draws the whole block, glyphs and selection alike, half a
framebuffer pixel right of where its rectangles and hit tests say; at 1 and
2 they agree to 0.004. Held as measured, not mended: the plan's criterion
was pens on the grid and columns holding, and both do.

The numbers are in `.concerns/R2-SCALE--builder--result.md`. The tests that
draw need the library; the theme's refusals do not.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter
from imscribe.theme import Theme

_ROOT = Path(__file__).resolve().parent.parent

SCALES = ((1.0, 1.0), (1.0, 1.1), (1.0, 1.25), (1.0, 1.5), (1.25, 1.0), (1.25, 1.2))
"""(`style.font_scale_main`, `style.font_scale_dpi`): hello_imgui's 110 to 150 %, and a zoom."""

DENSITIES = (1.0, 1.5, 2.0)
PIXEL_HEIGHTS = (13, 16, 20)


# -- the theme's refusals: no library ---------------------------------------------------------


@pytest.mark.parametrize("size", [0, 0.0, -16.0, math.nan, math.inf, 1e-12])
def test_a_theme_at_no_size_is_a_value_error_at_the_theme(size: float) -> None:
    with pytest.raises(ValueError, match="base_px"):
        Theme.build(size)


@pytest.mark.parametrize("size", [0.0, -1.0, math.nan])
def test_at_pixel_height_refuses_no_size_before_measuring_a_face(size: float) -> None:
    asked: list[str] = []

    def metrics(key: str) -> Any:
        asked.append(key)
        raise AssertionError("no face is measured for a size that is refused")

    with pytest.raises(ValueError, match="height_px") as caught:
        Theme.at_pixel_height(size, metrics=metrics)
    assert asked == []
    if size == 0.0:
        assert "before its first frame" in str(caught.value)


def test_the_default_theme_is_the_theme_at_sixteen() -> None:
    assert Theme.build() == Theme.build(16.0)


# -- headless, with the library ---------------------------------------------------------------

_CHILD = r"""
import json, math, string, sys
from collections import defaultdict
from dataclasses import replace

from imgui_bundle import imgui

from imscribe import (
    DARK_PALETTE, Align, BlockKind, Diff, Face, Faces, Spacing, Theme, TypesetView,
    em_size_for_pixel_height, px_from_sp, sp_from_px, typesetter,
)
from imscribe.ui.typeset_diff_view import DiffLayout, TypesetDiffView

SCALES, DENSITIES, HEIGHTS = json.loads(sys.argv[1])
report = {"module": typesetter.module() is not None, "reason": typesetter.reason()}
if not report["module"]:
    print(json.dumps(report))
    sys.exit(0)
imgui.create_context()
io = imgui.get_io()
WINDOW = (2500.0, 1000.0)
io.display_size = imgui.ImVec2(*WINDOW)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
io.set_ini_filename("")
report["before_first_frame"] = imgui.get_font_size()
report["load"] = bool(typesetter.load_fonts())
prose, code = typesetter.font(Face.PROSE), typesetter.font(Face.CODE)
io.font_default = prose
style = imgui.get_style()
style.font_size_base = 16.0

def quads(dl, start, white, plain=False):
    buf = dl.vtx_buffer
    pts = []
    for i in range(start, buf.size()):
        v = buf[i]
        textured = abs(v.uv.x - white.x) > 1e-9 or abs(v.uv.y - white.y) > 1e-9
        if textured != plain:
            pts.append((v.pos.x, v.pos.y, v.uv.x, v.uv.y))
    out = []
    for at in range(0, len(pts) - len(pts) % 4, 4):
        xs, ys, us, vs = zip(*pts[at:at + 4])
        out.append((min(xs), min(ys), max(xs), max(ys), min(us), min(vs), max(us), max(vs)))
    return out

# ---- P47 -------------------------------------------------------------------------------------
SOURCE = "H\n\n```\nH\n```"
fixed = TypesetView(SOURCE)
p47 = []
for main, dpi in SCALES:
    style.font_scale_main, style.font_scale_dpi = main, dpi
    row = {"main": main, "dpi": dpi, "between": imgui.get_font_size()}
    sized = None
    for frame in range(3):
        imgui.new_frame()
        white = imgui.get_font_tex_uv_white_pixel()
        drawn = imgui.get_font_size()
        if sized is None:
            sized = TypesetView(SOURCE, theme=Theme.at_pixel_height(drawn))
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(900.0, 700.0))
        imgui.begin("p47")
        dl = imgui.get_window_draw_list()
        s = dl.vtx_buffer.size(); imgui.text("H"); chrome = quads(dl, s, white)
        s = dl.vtx_buffer.size(); sized.draw(width_px=600.0); followed = quads(dl, s, white)
        s = dl.vtx_buffer.size(); fixed.draw(width_px=600.0); unmoved = quads(dl, s, white)
        imgui.end()
        imgui.render()
    row.update(
        drawn=drawn,
        chrome_h=[q[3] - q[1] for q in chrome],
        sized_h=[q[3] - q[1] for q in followed],
        fixed_h=[q[3] - q[1] for q in unmoved],
        fixed_body=fixed.theme.style(BlockKind.PARAGRAPH).font.size,
    )
    sized.close()
    p47.append(row)
fixed.close()
style.font_scale_main = style.font_scale_dpi = 1.0
report["p47"] = p47

# ---- A5 --------------------------------------------------------------------------------------
RULER = "1234567890" * 4
LONG = "total = float(baked.get_char_advance(code)) + kern_px  # 40th is in 'kern'"
ASCII = "".join(c for c in string.printable if c.isprintable() and not c.isspace())
ROWS = ("name       size  kind", "beta_long    42  dir", "iiii|llll|mmmm|WWWW|",
        "0000|1111|8888|....|", RULER, LONG, ASCII)
after = "\n".join(ROWS) + "\n"
diff = Diff.from_texts(after.replace("42", "41"), after, "probe.txt", context=10**6)
fence = "```\n" + "\n".join(ROWS) + "\n```"

def seam_theme(px):
    # tests/test_mono_acceptance.py's: pptmstr's diff theme.
    base = Theme.at_pixel_height(float(px), align=Align.LEFT, spacing=Spacing.FRENCH)
    pitch = max(1.0, math.floor(px * 18.0 / 16.0 + 0.5))
    style_ = base.blocks[BlockKind.CODE]
    lead = sp_from_px(pitch)
    while px_from_sp(lead) > pitch:
        lead -= 1
    blocks = dict(base.blocks)
    blocks[BlockKind.CODE] = replace(style_, font=replace(
        style_.font, face=Face.CODE, size=sp_from_px(em_size_for_pixel_height(Face.CODE, px))),
        leading=lead)
    return replace(base, blocks=blocks)

def baked_for(rows, d, px):
    for size in sorted({round(px * d) + k for k in range(-4, 5)}, key=lambda s: abs(s - px * d)):
        baked = code.get_font_baked(float(size), 1.0)
        def fits(text, index, q):
            c = ord(text[index])
            if not baked.is_glyph_loaded(c):
                return False
            g = baked.find_glyph(c)
            return all(abs(a - b) <= 1e-7 for a, b in zip((g.u0, g.v0, g.u1, g.v1), q[4:]))
        if all(fits(t, i, q) for t, placed in rows for i, q in placed):
            return baked
    raise AssertionError(("no bake accounts for the quads", d, px))

def pane(rows, d, px, cell, left, rect_left):
    baked = baked_for(rows, d, px)
    off = lambda v: abs(v * d - round(v * d))
    pens_off = 0
    steps, from_grid, from_rect = set(), [], []
    for r, (text, placed) in enumerate(rows):
        pens = {}
        for index, q in placed:
            pen = q[0] - float(baked.find_glyph(ord(text[index])).x0) / d
            pens[index] = pen
            pens_off += off(pen) > 1e-3
            from_grid.append((pen - (left + index * cell)) * d)
            from_rect.append((pen - rect_left(r, index)) * d)
        steps |= {round((pens[a + 1] - pens[a]) * d, 3) for a in pens if a + 1 in pens}
    return {"glyphs": sum(len(p) for _, p in rows), "pens_off": pens_off,
            "steps": sorted(steps), "cell_fb": cell * d,
            "grid": [min(from_grid), max(from_grid)],
            "rect": max(abs(v) for v in from_rect), "left_off": off(left)}

def read_diff(view, span_start, white, d, px):
    ox, oy = view.origin
    grid = view.grid
    by_row = defaultdict(list)
    for q in quads(imgui.get_window_draw_list(), span_start, white):
        by_row[int(((q[1] + q[3]) / 2.0 - oy) // grid.row)].append(q)
    out = []
    for p, pn in enumerate(view._panes(view._width, grid.cell)):
        doc = view.native_documents[2 * p + 1]
        left = ox + pn.code - view.scroll_x
        rows, starts = [], []
        for row in range(view.row_count):
            info = view.row_info(row)
            at = info.left if pn.side in (None, 0) else info.right
            if info.kind != "row" or at is None:
                continue
            text = view.diff.files[info.file].hunks[info.hunk].rows[at].text
            inked = [i for i, c in enumerate(text) if not c.isspace()]
            mine = sorted(q for q in by_row.get(row, [])
                          if ox + pn.x0 - 1.0 <= q[0] < ox + pn.x1)[-len(inked):]
            assert len(mine) == len(inked), (row, len(mine), len(inked))
            rows.append((text, list(zip(inked, mine))))
            base = doc.hit_test((0.5, (row + 0.5) * grid.row)).position
            starts.append((int(base[0]), int(base[1])))
        def rect_left(r, i, doc=doc, left=left, starts=starts):
            b, s = starts[r]
            return left + float(doc.range_rects(((b, s + i), (b, s + i + 1)))[0][0])
        out.append(pane(rows, d, px, grid.cell, left, rect_left))
    return out

def read_fence(view, span_start, white, d, px):
    ox, oy = view.origin
    text = view.texts[0]
    inked = [i for i, c in enumerate(text) if not c.isspace()]
    glyphs = quads(imgui.get_window_draw_list(), span_start, white)
    assert len(glyphs) == len(inked), (len(glyphs), len(inked))
    at_ = dict(zip(inked, glyphs))
    rows, starts, at = [], [], 0
    for line in text.split("\n"):
        rows.append((line, [(i - at, at_[i]) for i in range(at, at + len(line)) if i in at_]))
        starts.append(at)
        at += len(line) + 1
    ten = view.span_rects(0, 0, 10)[0]
    cell = round((ten[2] - ten[0]) / 10.0 * d) / d
    left = ox + float(view.span_rects(0, 0, 1)[0][0])
    rect_left = lambda r, i: ox + float(view.span_rects(0, starts[r] + i, starts[r] + i + 1)[0][0])
    return [pane(rows, d, px, cell, left, rect_left)]

a5 = []
for d in DENSITIES:
    io.display_framebuffer_scale = imgui.ImVec2(d, d)
    for px in HEIGHTS:
        for shift in (0.0, 1.0):
            for kind in ("unified", "side-by-side", "fence"):
                if kind == "fence":
                    view = TypesetView(fence, theme=Theme.at_pixel_height(
                        float(px), faces=Faces.mono(), align=Align.LEFT, spacing=Spacing.FRENCH))
                else:
                    layout = DiffLayout.UNIFIED if kind == "unified" else DiffLayout.SIDE_BY_SIDE
                    view = TypesetDiffView(diff, seam_theme(px), layout=layout)
                for frame in range(4):
                    imgui.new_frame()
                    white = imgui.get_font_tex_uv_white_pixel()
                    imgui.set_next_window_pos(imgui.ImVec2(shift, 0.0))
                    imgui.set_next_window_size(imgui.ImVec2(*WINDOW))
                    imgui.begin("a5", None, imgui.WindowFlags_.no_decoration.value)
                    dl = imgui.get_window_draw_list()
                    dl.push_clip_rect(imgui.ImVec2(0.0, 0.0), imgui.ImVec2(*WINDOW), False)
                    start = dl.vtx_buffer.size()
                    width = 1500.0 if kind == "fence" else math.ceil(view.content_width) + 40.0
                    view.draw(palette=DARK_PALETTE, width_px=float(width))
                    dl.pop_clip_rect()
                    if frame == 3:
                        read = read_fence if kind == "fence" else read_diff
                        a5.append({"d": d, "px": px, "shift": shift, "kind": kind,
                                   "panes": read(view, start, white, d, px)})
                    imgui.end()
                    imgui.render()
                view.close()
report["a5"] = a5
report["ready_at_end"] = typesetter.ready()
typesetter.unload()
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def measured() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, json.dumps([SCALES, DENSITIES, PIXEL_HEIGHTS])],
        capture_output=True,
        text=True,
        timeout=600.0,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-5000:]
    got: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    assert got["module"] is True, "the child did not get imtypeset: " + str(got.get("reason"))
    assert got["load"] is True and got["ready_at_end"] is True
    return got


def _half_up(value: float) -> float:
    return float(math.floor(value + 0.5))


def test_dear_imgui_draws_at_base_times_both_scales_and_answers_the_base_between_frames(
    measured: dict[str, Any],
) -> None:
    """
    The recipe `imscribe.theme` gives a host: inside a frame `get_font_size()`
    is 16 x main x dpi rounded half up (18, 20, 24 at a dpi scale of 1.1,
    1.25, 1.5); between frames it is 16 whatever the scales; before the first
    frame it is 0.
    """
    assert measured["before_first_frame"] == 0.0
    # The first row's "between" is read before any frame, the rest after one.
    assert measured["p47"][0]["between"] == 0.0
    for row in measured["p47"]:
        assert row["drawn"] == _half_up(16.0 * row["main"] * row["dpi"]), row
    for row in measured["p47"][1:]:
        assert row["between"] == 16.0, row
    assert [row["drawn"] for row in measured["p47"]][:4] == [16.0, 18.0, 20.0, 24.0]


def test_a_theme_at_the_size_drawn_is_as_tall_as_the_label_and_a_built_theme_does_not_move(
    measured: dict[str, Any],
) -> None:
    """
    `Theme.at_pixel_height(get_font_size())` read inside a frame: the prose's
    capital H is exactly as tall as `imgui.text("H")` in the same face, at
    every scale. A view on `Theme.build()` is set at the same size at every
    scale (its body is 16 px of em, 18.75 of pixel height): the scales are
    the host's to follow.
    """
    first = measured["p47"][0]
    for row in measured["p47"]:
        (chrome,) = row["chrome_h"]
        assert row["sized_h"][0] == chrome, row
        assert row["fixed_h"] == first["fixed_h"], row
        assert row["fixed_body"] == first["fixed_body"], row
    # The scale reached Dear ImGui's label: it is not the same height throughout.
    assert measured["p47"][3]["chrome_h"][0] > first["chrome_h"][0]


def test_at_every_framebuffer_scale_pens_are_on_the_framebuffer_grid_and_columns_hold(
    measured: dict[str, Any],
) -> None:
    """
    The diff view, unified and side by side, and a fenced block, at
    framebuffer scales 1, 1.5 and 2, pixel heights 13, 16 and 20, the view at
    an even and an odd unit: no pen off the framebuffer's grid, one step along
    every row and it is the cell (a whole number of framebuffer pixels), and
    every pen at the same distance from where its column begins.
    """
    assert len(measured["a5"]) == len(DENSITIES) * len(PIXEL_HEIGHTS) * 2 * 3
    for page in measured["a5"]:
        for pane in page["panes"]:
            where = (page, pane)
            assert pane["glyphs"] > 200, where
            assert pane["pens_off"] == 0, where
            assert pane["steps"] == [round(pane["cell_fb"], 3)], where
            assert pane["cell_fb"] == pytest.approx(round(pane["cell_fb"]), abs=1e-3), where
            low, high = pane["grid"]
            assert high - low < 0.01, where


def test_the_drawn_block_is_within_half_a_framebuffer_pixel_of_its_rectangles(
    measured: dict[str, Any],
) -> None:
    """
    What a whole UNIT costs at 1.5: where the code's left edge is a whole
    framebuffer pixel the pens are on the library's rectangles (to 0.01), and
    where it is half of one (an odd unit) the whole block is drawn half a
    framebuffer pixel from them. At 1 and 2 every unit is whole and nothing
    moves. Held so that a change in either direction shows.
    """
    halves = 0
    for page in measured["a5"]:
        for pane in page["panes"]:
            where = (page, pane)
            if pane["left_off"] < 1e-3:
                assert pane["rect"] < 0.01, where
            else:
                assert page["d"] == 1.5, where
                assert pane["left_off"] == pytest.approx(0.5, abs=1e-3), where
                assert pane["rect"] == pytest.approx(0.5, abs=0.01), where
                halves += 1
    assert halves > 0, "no page at 1.5 had its code at an odd unit: the case is not measured"

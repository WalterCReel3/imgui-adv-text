r"""
Monospace on the pixel grid: what "fixed" means, for the diff view and for code in a document.

pptmstr, the first host, measured it (its `HANDOFF-advtext.md`, A2: R1 to R6,
and requests P21 and P22; `scripts/measure_typeset_diff.py` is its probe): at
the pixel heights a host sets text at, imtypeset 0.3 laid the code face out at
the font file's advance (7.626 px at a 16 px height), drew on whole pixels,
and so a row was a mix of 7 and 8 px steps, the 40th character was 15 px from
where Dear ImGui puts it, and a point on a drawn glyph was answered as a
neighbouring character. The typesetting core's answer was its H34 and H35
(`HANDOFF-imtypeset.md`), done in imtypeset 0.4. This file is the acceptance
test for both sides, **and since imtypeset 0.4.1 every page of it passes**.

**What is asserted, of every page** (a page is one view at one pixel height;
everything is read from the window's vertex buffer and the library's own
answers, in a real window, and no pixel is read):

- **R4** one distinct step between adjacent columns over every row, and 0 px
  between rows at any one column;
- **R5** characters 1, 10, 20, 30, 40 and 74 of a row on the pens Dear ImGui's
  own `ImDrawList.add_text` gives the same string from the same x, in the
  library's own atlas entry for the code face and in a `hello_imgui`-loaded
  copy of the same file, both at the page's pixel height;
- **R1 / P22** every glyph's pen within 0.5 px of the left edge of the
  rectangle the library answers for that character (`range_rects`);
- **hit** a `hit_test` a quarter of a cell right of a drawn glyph's pen
  answers the caret before it and three quarters the caret after (the
  library answers the nearest caret);
- **selection** the fill drawn for characters 21 to 40 of the 74-character
  row has its edges on the pens of characters 21 and 41;
- **R6** no pen and no quad corner off the pixel grid, no bitmap resampled.

**Two kinds of page**, each at pixel heights 12 to 24:

1. `TypesetDiffView` as a host gets it -- nothing passed for the cell --
   unified and side by side, built as pptmstr builds its diff (a theme whose
   code style is sized by pixel height with a pitch of its own); and at 13,
   16 and 22 in a view too narrow for its longest row, scrolled sideways,
   pressed and dragged.
2. A fenced code block in a `TypesetView` at a pixel height.

**The history, because the tests' names changed with it.** On imtypeset
v0.3.0 only a third kind passed: the diff view with `cell="pixel"`, an option
that drew the face at another em so that its advance was a whole pixel
(`test_pixel_cell_*`, 26 pages). The diff view's default cell and the fence
were 105 strict xfails at 14 to 20 (`test_core_*`: five assertions on 21
pages), written to go red the day a library that mended H34 and H35 was
pinned. On 2026-10-13, on imtypeset 0.4.1, all 105 XPASSed. The marks came
off, the option was deprecated (it is accepted and ignored: the tests at the
end of this file), the two kinds are held to the same assertions at 12 to 24,
and the tests are named for what they assert.

The numbers behind every sentence here are in
`.concerns/D-CELL--builder--result.md` (v0.3.0) and
`.concerns/ADOPT-API--builder--result.md` (0.4.1). They need the library:
an installed imtypeset, or `make test TYPESET=1`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent

PIXEL_HEIGHTS = tuple(range(12, 25))
"""The pixel heights every page is held at: 12 to 24 (pptmstr's own are 14 to 20)."""

ACT_HEIGHTS = (13, 16, 22)
"""
The pixel heights a scroll, a press and a drag are run at: one where the
file's advance is above the cell, one where it is below, one where the cell
is not the file's advance rounded.
"""

LAYOUTS = ("unified", "side-by-side")
MARKS = (1, 10, 20, 30, 40, 74)


def pages() -> list[dict[str, Any]]:
    """Every page the driver draws, in order: the three kinds of the module docstring."""
    out: list[dict[str, Any]] = []
    for px in PIXEL_HEIGHTS:
        for layout in LAYOUTS:
            out.append({"kind": "diff", "px": px, "layout": layout})
    for px in PIXEL_HEIGHTS:
        out.append({"kind": "fence", "px": px})
    for px in ACT_HEIGHTS:
        for layout in LAYOUTS:
            out.append({"kind": "act", "px": px, "layout": layout})
    return out


def page_name(page: dict[str, Any]) -> str:
    if page["kind"] == "fence":
        return f"fence px{page['px']}"
    if page["kind"] == "act":
        return f"act px{page['px']} {page['layout']}"
    extra = "".join(f" {key}={page[key]}" for key in ("build", "model", "leading") if key in page)
    return f"diff px{page['px']} {page['layout']}{extra}"


DRIVER = r"""
import json, math, string, sys
from collections import Counter
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import (
    DARK_PALETTE, Align, BlockKind, Diff, Face, Faces, Spacing, Theme, TypesetView,
    em_size_for_pixel_height, px_from_sp, sp_from_px, typesetter,
)
from imscribe.ui.typeset_diff_view import DiffLayout, TypesetDiffView, code_size

PAGES = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[2])

RULER = "1234567890" * 4
LONG = "total = float(baked.get_char_advance(code)) + kern_px  # 40th is in 'kern'"
ASCII = "".join(c for c in string.printable if c.isprintable() and not c.isspace())
# pptmstr's seven rows (its scripts/measure_typeset_diff.py), then every printable ASCII
# character on one row, for the tallest ink.
PPTMSTR_ROWS = (
    "name       size  kind",
    "alpha         1  file",
    "beta_long    42  dir",
    "iiii|llll|mmmm|WWWW|",
    "0000|1111|8888|....|",
    RULER,
    LONG,
)
ROWS = PPTMSTR_ROWS + (ASCII,)
# U+2502, the tallest glyph of the bundled code face that imscribe's docs name.
TALL = "\u2502 box \u2502"
MARKS = (1, 10, 20, 30, 40, 74)
SELECTED = (20, 40)   # characters 21 to 40, counted from 1
SETTLE = 4
WINDOW = (2500.0, 980.0)
NATIVE_INK = 0x30FFFFFF

def loadavg():
    return open("/proc/loadavg").read().split()[:3]

def half_up(value):
    return float(math.floor(value + 0.5))

def seam_theme(px, faces=None, leading=18.0 / 16.0):
    # As pptmstr's themes.diff_theme(): a document theme at the body's pixel height, its code
    # style set in Face.CODE at the diff role's pixel height, on the role's pitch (18/16 of it,
    # a whole pixel), the leading brought back under the pixel it came from.
    base = Theme.at_pixel_height(
        float(px), faces=faces or Faces(), align=Align.LEFT, spacing=Spacing.FRENCH)
    pitch = max(1.0, half_up(px * leading))
    code = base.blocks[BlockKind.CODE]
    size = sp_from_px(em_size_for_pixel_height(Face.CODE, float(px)))
    leading = sp_from_px(pitch)
    while px_from_sp(leading) > pitch:
        leading -= 1
    blocks = dict(base.blocks)
    blocks[BlockKind.CODE] = replace(
        code, font=replace(code.font, face=Face.CODE, size=size), leading=leading)
    return replace(base, blocks=blocks), pitch

def quads_of(draw_list, start, stop, white):
    # (textured quads, white-texel quads) among vertices [start, stop).
    buffer = draw_list.vtx_buffer
    textured, plain = [], []
    for i in range(start, stop):
        v = buffer[i]
        if abs(v.uv.x - white.x) > 1e-9 or abs(v.uv.y - white.y) > 1e-9:
            textured.append((v.pos.x, v.pos.y, v.uv.x, v.uv.y))
        else:
            plain.append((v.pos.x, v.pos.y, int(v.col)))
    assert len(textured) % 4 == 0, len(textured)
    glyphs = []
    for at in range(0, len(textured), 4):
        xs, ys, us, vs = zip(*textured[at:at + 4], strict=True)
        glyphs.append((min(xs), min(ys), max(xs), max(ys), min(us), min(vs), max(us), max(vs)))
    fills = []
    if len(plain) % 4 == 0:
        for at in range(0, len(plain), 4):
            xs, ys, cols = zip(*plain[at:at + 4], strict=True)
            fills.append((min(xs), min(ys), max(xs), max(ys), cols[0]))
    return glyphs, fills

def baked_for(font, px, rows):
    # The baked size of `font` whose glyphs' uv rectangles every quad of `rows` carries.
    # rows: [(text, [(index, quad), ...])].
    for size in (px, px + 1.0, px - 1.0, px + 2.0, px - 2.0):
        baked = font.get_font_baked(float(size))
        whole = True
        for text, placed in rows:
            for index, quad in placed:
                code = ord(text[index])
                if not baked.is_glyph_loaded(code):
                    whole = False
                    break
                g = baked.find_glyph(code)
                uv = (g.u0, g.v0, g.u1, g.v1)
                if any(abs(a - b) > 1e-7 for a, b in zip(uv, quad[4:], strict=True)):
                    whole = False
                    break
            if not whole:
                break
        if whole:
            return baked
    raise AssertionError("no baked size of the library's code entry accounts for every quad")

def native_pens(draw_list, font, px, x, y, text, white):
    # Each inked character's pen through ImDrawList.add_text in `font` at `px` from `x`,
    # read back from the vertices it added.
    baked = font.get_font_baked(float(px))
    start = draw_list.vtx_buffer.size()
    # Dear ImGui leaves out the glyphs right of the clip rectangle: opened, as for the view.
    draw_list.push_clip_rect(imgui.ImVec2(0.0, 0.0), imgui.ImVec2(*WINDOW), False)
    draw_list.add_text(font, float(px), imgui.ImVec2(x, y), NATIVE_INK, text)
    draw_list.pop_clip_rect()
    glyphs, _ = quads_of(draw_list, start, draw_list.vtx_buffer.size(), white)
    inked = [i for i, c in enumerate(text) if not c.isspace()]
    assert len(glyphs) == len(inked), (len(glyphs), len(inked), y)
    return {i: q[0] - float(baked.find_glyph(ord(text[i])).x0)
            for i, q in zip(inked, glyphs, strict=True)}

def off_grid(value):
    return abs(value - round(value)) > 1e-4

def summarise(rows, cell, px, own, chrome, draw_list, white, native_y, rect_left, hit, tops):
    # rows: [(text, [(index, quad), ...])] of one column of code, top to bottom.
    # rect_left(row, index): the left edge, on screen, of the rectangle the library answers.
    # hit(row, x, y): the index along the row that a point on screen is answered as.
    # tops: [(top, bottom)] of each row's line on screen.
    baked = baked_for(own, px, rows)
    pens = []
    fractional = corners = resampled = glyphs = 0
    above = below = tallest = 0.0
    ink_top, ink_bottom = 1e9, -1e9
    by_row = []
    for (text, placed), (top, bottom) in zip(rows, tops, strict=True):
        mine = {}
        by_row.append([text[:6], min(q[1] for _, q in placed) - top,
                       max(q[3] for _, q in placed) - top])
        for index, quad in placed:
            g = baked.find_glyph(ord(text[index]))
            pen = quad[0] - float(g.x0)
            mine[index] = pen
            glyphs += 1
            fractional += off_grid(pen)
            corners += any(off_grid(v) for v in quad[:4])
            resampled += (abs((quad[2] - quad[0]) - (float(g.x1) - float(g.x0))) > 1e-4
                          or abs((quad[3] - quad[1]) - (float(g.y1) - float(g.y0))) > 1e-4)
            above = max(above, top - quad[1])
            below = max(below, quad[3] - bottom)
            tallest = max(tallest, quad[3] - quad[1])
            ink_top = min(ink_top, quad[1] - top)
            ink_bottom = max(ink_bottom, quad[3] - top)
        pens.append(mine)
    steps = Counter()
    for mine in pens:
        for a, b in pairwise(sorted(mine)):
            if b == a + 1:
                steps[round(mine[b] - mine[a], 3)] += 1
    columns = {}
    for mine in pens:
        for index, pen in mine.items():
            columns.setdefault(index, []).append(pen)
    drift = {column: max(at) - min(at) for column, at in columns.items()}
    where = max(drift, key=lambda column: (drift[column], -column))
    out = {
        "baked": float(baked.size),
        "baked_advance": float(baked.get_char_advance(ord("0"))),
        "own_advance_at_px": float(own.get_font_baked(float(px)).get_char_advance(ord("0"))),
        "chrome_advance_at_px": float(chrome.get_font_baked(float(px)).get_char_advance(ord("0"))),
        "glyphs": glyphs,
        "steps": sorted(steps.items()),
        "drift": [drift[where], where + 1],
        "firsts": sorted({round(mine[0], 3) for mine in pens if 0 in mine}),
        "fractional": [int(fractional), int(corners), int(resampled)],
        "ink_above": above, "ink_below": below,
        "ink_tallest": tallest, "ink_span": [ink_top, ink_bottom], "ink_by_row": by_row,
        "rows": {},
    }
    line = 0
    worst_rect = [0.0, 0, ""]
    wrong_all = of_all = carets_all = 0
    for r, ((text, placed), (top, bottom)) in enumerate(zip(rows, tops, strict=True)):
        mine = pens[r]
        offs = {index: pen - rect_left(r, index) for index, pen in mine.items()}
        far = max(offs, key=lambda index: abs(offs[index]))
        if abs(offs[far]) > abs(worst_rect[0]):
            worst_rect = [offs[far], far + 1, text]
        wrong, carets = [], []
        middle = (top + bottom) / 2.0
        for index, quad in placed:
            # pptmstr's reading: the centre of the glyph's quad against the glyph's own index.
            answered = hit(r, (quad[0] + quad[2]) / 2.0, middle)
            if answered != index:
                wrong.append((index + 1, answered + 1))
            # The library answers the NEAREST CARET: a quarter of a cell right of the pen is
            # the caret before this glyph, three quarters the caret after it.
            before = hit(r, mine[index] + 0.25 * cell, middle)
            after = hit(r, mine[index] + 0.75 * cell, middle)
            # (The caret after a line's last character is answered as the start of the next
            # line where the block has one: one further, and the same place on screen.)
            ends = (index + 1, index + 2) if index + 1 == len(text) else (index + 1,)
            if before != index or after not in ends:
                carets.append((index + 1, before + 1, after + 1))
        wrong_all += len(wrong)
        carets_all += len(carets)
        of_all += len(placed)
        if text not in (RULER, LONG):
            continue
        entry = {"length": len(text), "first_pen": mine[0],
                 "last_from_first": mine[max(mine)] - mine[0]}
        natives = {}
        for name, font in (("own", own), ("chrome", chrome)):
            natives[name] = native_pens(
                draw_list, font, px, mine[0], native_y + line * 30.0, text, white)
            line += 1
        marks = [k for k in MARKS if k <= len(text)]
        entry["marks"] = marks
        entry["pen"] = [mine[k - 1] - mine[0] for k in marks]
        entry["own"] = [natives["own"][k - 1] - mine[0] for k in marks]
        entry["chrome"] = [natives["chrome"][k - 1] - mine[0] for k in marks]
        entry["less_own_all"] = [min(mine[i] - natives["own"][i] for i in mine),
                                 max(mine[i] - natives["own"][i] for i in mine)]
        entry["less_chrome_all"] = [min(mine[i] - natives["chrome"][i] for i in mine),
                                    max(mine[i] - natives["chrome"][i] for i in mine)]
        entry["less_rect"] = [min(offs.values()), max(offs.values())]
        on_cell = [pen - (mine[0] + index * cell) for index, pen in mine.items()]
        entry["less_cell"] = [min(on_cell), max(on_cell)]
        entry["hits_wrong"] = [len(wrong), len(placed)]
        entry["hit_worst"] = max(wrong, key=lambda pair: abs(pair[1] - pair[0]), default=None)
        entry["carets_wrong"] = [len(carets), len(placed)]
        entry["caret_worst"] = max(
            carets, key=lambda t: max(abs(t[1] - t[0]), abs(t[2] - t[0] - 1)), default=None)
        if text == LONG:
            entry["pens_selected"] = [mine[SELECTED[0]], mine[SELECTED[1]]]
        out["rows"]["ruler" if text == RULER else "long"] = entry
    out["less_rect_worst"] = worst_rect
    out["hits_wrong_all"] = [wrong_all, of_all]
    out["carets_wrong_all"] = [carets_all, of_all]
    return out, line

def new_fills(before, after, top, bottom):
    # The white-texel quads of `after` that are not in `before` and lie on the row [top, bottom).
    seen = Counter(before)
    out = []
    for fill in after:
        if seen[fill] > 0:
            seen[fill] -= 1
        elif fill[1] < bottom and fill[3] > top:
            out.append(fill)
    return out

# ---- a diff page ---------------------------------------------------------------------------

def diff_model(page):
    if page.get("model") == "pptmstr":
        # pptmstr's probe: one file whose every row is added.
        return Diff.from_texts("", "\n".join(PPTMSTR_ROWS) + "\n", "probe.txt")
    # Rows in both panes side by side: all context but one changed row.
    rows = ROWS + (TALL,) if page.get("model") == "tall" else ROWS
    after = "\n".join(rows) + "\n"
    before = after.replace("beta_long    42  dir", "beta_long    41  dir")
    return Diff.from_texts(before, after, "probe.txt", context=10**6)

def make_diff(page):
    px = float(page["px"])
    layout = DiffLayout.SIDE_BY_SIDE if page["layout"] == "side-by-side" else DiffLayout.UNIFIED
    kwargs = {"layout": layout, "palette": DARK_PALETTE}
    if page.get("build") == "probe":
        # As pptmstr's scripts/measure_typeset_diff.py builds its view.
        theme = Theme.at_pixel_height(px, faces=Faces.mono(), align=Align.LEFT)
        return TypesetDiffView(diff_model(page), theme, pixel_height=px, **kwargs), None
    theme, pitch = seam_theme(px, leading=page.get("leading", 18.0 / 16.0))
    return TypesetDiffView(diff_model(page), theme, **kwargs), pitch

def side_line(view, row, side):
    info = view.row_info(row)
    at = info.left if side in (None, 0) else info.right
    if at is None:
        return None
    return view.diff.files[info.file].hunks[info.hunk].rows[at].text, (info.file, info.hunk, at)

def read_diff(page, view, pitch_asked, draw_list, span, white, own, chrome):
    px = float(page["px"])
    ox, oy = view.origin
    grid = view.grid
    glyphs, fills = quads_of(draw_list, *span, white)
    by_row = {}
    for quad in glyphs:
        by_row.setdefault(int(((quad[1] + quad[3]) / 2.0 - oy) // grid.row), []).append(quad)
    panes = view._panes(view._width, grid.cell)
    asked = code_size(view.theme, view.pixel_height, view.px_per_inch)
    out = {
        "cell": grid.cell, "row": grid.row, "pitch_asked": pitch_asked,
        "em_drawn": grid.em * grid.scale, "em_asked": asked[0], "row_asked": asked[1],
        "option": view.cell, "rows": view.row_count, "content_height": view.content_height,
        "content_width": view.content_width, "width": view._width,
        "height_for": view.height_for(view._width),
        "headers": [[h.width_px, h.text_width_px, len(h.line), len(h.text)]
                    for h in view.headers()],
        "pane_edges": [[p.x0, p.x1, p.code] for p in panes],
        "panes": {}, "fills": fills,
    }
    native_y = oy + view.content_height + 40.0
    state["selections"] = []
    for p, pane in enumerate(panes):
        code = view.native_documents[2 * p + 1]
        left = ox + pane.code - view.scroll_x
        rows, tops, starts, numbers = [], [], [], []
        for row in range(view.row_count):
            if view.row_info(row).kind != "row":
                continue
            found = side_line(view, row, pane.side)
            if found is None:
                continue
            text, where = found
            inked = [i for i, c in enumerate(text) if not c.isspace()]
            mine = sorted(q for q in by_row.get(row, [])
                          if ox + pane.x0 - 1.0 <= q[0] < ox + pane.x1)[-len(inked):]
            assert len(mine) == len(inked), (page, row, len(mine), len(inked))
            rows.append((text, list(zip(inked, mine, strict=True))))
            tops.append((oy + row * grid.row, oy + (row + 1) * grid.row))
            middle = (row + 0.5) * grid.row
            base = code.hit_test((0.5, middle)).position
            starts.append((int(base[0]), int(base[1])))
            numbers.append((row, where))

        def rect_left(r, index, code=code, left=left, starts=starts):
            block, start = starts[r]
            rects = code.range_rects(((block, start + index), (block, start + index + 1)))
            return left + float(rects[0][0])

        def hit(r, x, y, code=code, left=left, starts=starts):
            block, start = starts[r]
            answered = code.hit_test((x - left, y - oy)).position
            if int(answered[0]) != block:
                return -10**6
            return int(answered[1]) - start

        entry, used = summarise(
            rows, grid.cell, px, own, chrome, draw_list, white, native_y, rect_left, hit, tops)
        native_y += used * 30.0
        entry["code_left"] = left
        entry["first_pen_less_code_left"] = sorted(
            {round(pen - left, 3) for pen in entry["firsts"]})
        r = next(n for n, (text, _) in enumerate(rows) if text == LONG)
        row, where = numbers[r]
        state["selections"].append((str(p), pane.side, where, tops[r]))
        out["panes"][str(p)] = entry
    return out

# ---- a fenced code block in a TypesetView -----------------------------------------------------

def make_fence(page):
    theme = Theme.at_pixel_height(
        float(page["px"]), faces=Faces.mono(), align=Align.LEFT, spacing=Spacing.FRENCH)
    source = "```\n" + "\n".join(ROWS) + "\n```"
    return TypesetView(source, theme=theme, palette=DARK_PALETTE)

def read_fence(page, view, draw_list, span, white, own, chrome):
    px = float(page["px"])
    ox, oy = view.origin
    glyphs, fills = quads_of(draw_list, *span, white)
    text = view.texts[0]
    inked = [i for i, c in enumerate(text) if not c.isspace()]
    assert len(glyphs) == len(inked), (page, len(glyphs), len(inked))
    quad_at = dict(zip(inked, glyphs, strict=True))
    doc = view.native_document
    rows, tops, starts = [], [], []
    at = 0
    for line in text.split("\n"):
        placed = [(i - at, quad_at[i]) for i in range(at, at + len(line)) if i in quad_at]
        rect = view.span_rects(0, at, at + 1)[0]
        rows.append((line, placed))
        tops.append((oy + rect[1], oy + rect[3]))
        starts.append(at)
        at += len(line) + 1
    assert [line for line, _ in rows] == list(ROWS), "the fence's text is not the rows handed in"

    def rect_left(r, index):
        return ox + float(view.span_rects(0, starts[r] + index, starts[r] + index + 1)[0][0])

    def hit(r, x, y):
        answered = doc.hit_test((x - ox, y - oy)).position
        if int(answered[0]) != 0:
            return -10**6
        return int(answered[1]) - starts[r]

    code = view.theme.style(BlockKind.CODE)
    advance = (view.span_rects(0, 0, 10)[0][2] - view.span_rects(0, 0, 10)[0][0]) / 10.0
    native_y = oy + view.height + 40.0
    entry, _ = summarise(
        rows, advance, px, own, chrome, draw_list, white, native_y, rect_left, hit, tops)
    r = list(ROWS).index(LONG)
    state["selections"] = [("0", None, starts[r], tops[r])]
    return {
        "cell": advance, "row": tops[1][0] - tops[0][0],
        "em_drawn": float(px_from_sp(code.font.size, view.theme.px_per_inch)),
        "panes": {"0": entry}, "fills": fills,
    }

# ---- a narrow diff: the scrollbar, a scroll, a press and a drag ------------------------------

ACT_CELLS = 40        # the view's width, in cells: too narrow for the 74-character row
SCROLL_CELLS = 10
# (press on the character at this index, release on that one, how far into the cell): the
# second press is far enough from the first not to be a double click.
DRAGS = ((12, 20, 0.25), (15, 22, 0.75))
PARKED = (5.0, 960.0)

def long_row(view, pane):
    for row in range(view.row_count):
        if view.row_info(row).kind == "row":
            found = side_line(view, row, pane.side)
            if found is not None and found[0] == LONG:
                return row, found[1]
    raise AssertionError("the 74-character row is not on this side")

def row_on_grid(view, pane, row, px, own, white):
    # The quads of the 74-character row that are inside the pane's code, and how many of them
    # stand where a character of the row would with the code scrolled as it is.
    ox, oy = view.origin
    grid = view.grid
    left = ox + pane.code - view.scroll_x
    glyphs, _ = quads_of(state["draw_list"], *state["span"], white)
    mine = sorted(q[0] for q in glyphs
                  if int(((q[1] + q[3]) / 2.0 - oy) // grid.row) == row
                  and ox + pane.code <= q[0] < ox + pane.x1)
    best = 0
    for size in (px, px + 1.0, px - 1.0, px + 2.0, px - 2.0):
        baked = own.get_font_baked(float(size))
        wanted = {round(left + i * grid.cell + float(baked.find_glyph(ord(c)).x0), 3)
                  for i, c in enumerate(LONG) if not c.isspace()}
        best = max(best, sum(round(x, 3) in wanted for x in mine))
    return {"scroll_x": view.scroll_x, "glyphs": len(mine), "on_grid": best,
            "whole": sum(not off_grid(x) for x in mine), "code_left": left}

def act_flow(page, view, own, white):
    px = float(page["px"])
    for _ in range(SETTLE):
        yield
    grid = view.grid
    cell = grid.cell
    panes = view._panes(view._width, cell)
    pane = panes[-1]          # the only pane unified; the new side, side by side
    row, where = long_row(view, pane)
    out = {"cell": cell, "width": view._width, "where": list(where),
           "bar": view.height_for(view._width) - view.content_height,
           "content_width": view.content_width}
    out["before"] = row_on_grid(view, pane, row, px, own, white)
    view.scroll_x = SCROLL_CELLS * cell
    yield
    yield
    out["after"] = row_on_grid(view, pane, row, px, own, white)
    ox, oy = view.origin
    left = ox + pane.code - view.scroll_x
    y = oy + (row + 0.5) * grid.row
    out["drags"] = []
    for first, last, part in DRAGS:
        a, b = (left + (index + part) * cell for index in (first, last))
        for event in (
            lambda io, a=a: io.add_mouse_pos_event(float(a), float(y)),
            lambda io: io.add_mouse_button_event(0, True),
            lambda io, b=b: io.add_mouse_pos_event(float(b), float(y)),
            lambda io: io.add_mouse_button_event(0, False),
        ):
            events.append(event)
            yield
            yield
        out["drags"].append({
            "part": part, "selection": view.selection, "text": view.selected_text(),
            "scroll_x": view.scroll_x})
        events.append(lambda io: io.add_mouse_pos_event(*PARKED))
        yield
        yield
        view.clear_selection()
    return out

# ---- the frames ----------------------------------------------------------------------------

report = {"pages": {}, "failed": [], "facts": {}}
state = {"page": 0, "shown": 0, "view": None, "selections": [], "n": 0}
events = []

def pre_new_frame():
    io = imgui.get_io()
    while events:
        events.pop(0)(io)

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    state["chrome"] = hello_imgui.load_font("fonts/Inconsolata-Medium.ttf", 16.0)
    report["load_fonts"] = bool(typesetter.load_fonts())

def name_of(page):
    if page["kind"] == "fence":
        return f"fence px{page['px']}"
    if page["kind"] == "act":
        return f"act px{page['px']} {page['layout']}"
    extra = "".join(f" {key}={page[key]}" for key in ("build", "model", "leading") if key in page)
    return f"diff px{page['px']} {page['layout']}{extra}"

def gui():
    state["n"] += 1
    if state["n"] == 1:
        report["module"] = typesetter.module() is not None
        report["ready"] = typesetter.ready()
        report["reason"] = typesetter.reason()
        report["load_start"] = loadavg()
    stop = not report["module"] or not report["ready"] or report["failed"]
    if stop or state["page"] >= len(PAGES):
        hello_imgui.get_runner_params().app_shall_exit = True
        return
    page = PAGES[state["page"]]
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(*WINDOW))
    imgui.begin("mono acceptance", None,
                imgui.WindowFlags_.no_decoration.value | imgui.WindowFlags_.no_saved_settings.value)
    try:
        assert typesetter.module() is not None and typesetter.ready(), typesetter.trouble()
        if state["view"] is None:
            if page["kind"] in ("diff", "act"):
                state["view"], state["pitch"] = make_diff(page)
            else:
                state["view"], state["pitch"] = make_fence(page), None
            state["shown"] = 0
            state["data"] = None
            state["flow"] = None
        view = state["view"]
        draw_list = imgui.get_window_draw_list()
        white = imgui.get_font_tex_uv_white_pixel()
        start = draw_list.vtx_buffer.size()
        # The screen under Xvfb is 1400 px wide and two columns of a 74-character row at a
        # 24 px height are 1900: the clip is opened to the window's own width, so that the
        # library emits the quads of glyphs right of the screen's edge. Vertices are read,
        # and nothing here depends on a pixel being put on screen.
        if page["kind"] == "act":
            # As a host draws it: no clip opened, a width too narrow for the row.
            view.draw(palette=DARK_PALETTE, width_px=ACT_CELLS * view.grid.cell)
            state["draw_list"], state["span"] = draw_list, (start, draw_list.vtx_buffer.size())
            if state["flow"] is None:
                state["flow"] = act_flow(page, view, typesetter.font(Face.CODE), white)
            try:
                next(state["flow"])
            except StopIteration as done:
                report["pages"][name_of(page)] = done.value
                view.close()
                state["view"] = None
                state["page"] += 1
            return
        draw_list.push_clip_rect(imgui.ImVec2(0.0, 0.0), imgui.ImVec2(*WINDOW), False)
        try:
            if page["kind"] == "diff":
                width = page.get("width") or math.ceil(view.content_width) + 40.0
                view.draw(palette=DARK_PALETTE, width_px=float(width))
            else:
                view.draw(palette=DARK_PALETTE, width_px=1500.0)
        finally:
            draw_list.pop_clip_rect()
        span = (start, draw_list.vtx_buffer.size())
        state["shown"] += 1
        shown = state["shown"]
        if shown < SETTLE:
            return
        own = typesetter.font(Face.CODE)
        if shown == SETTLE:
            if page["kind"] == "diff":
                data = read_diff(
                    page, view, state["pitch"], draw_list, span, white, own, state["chrome"])
            else:
                data = read_fence(page, view, draw_list, span, white, own, state["chrome"])
            data["selection"] = {}
            state["data"] = data
            state["pending"] = list(state["selections"])
        data = state["data"]
        if shown > SETTLE:
            # The frame after a selection was made: its fill is what is new on the row.
            key, side, where, (top, bottom) = state["made"]
            _, fills = quads_of(draw_list, *span, white)
            fresh = new_fills(data["fills"], fills, top, bottom)
            data["selection"][key] = {
                "fills": [[f[0], f[2]] for f in fresh],
                "pens": data["panes"][key]["rows"]["long"]["pens_selected"],
            }
            view.clear_selection()
        if state["pending"]:
            state["made"] = made = state["pending"].pop(0)
            key, side, where, _ = made
            if page["kind"] == "diff":
                view.select((*where, SELECTED[0]), (*where, SELECTED[1]), side)
            else:
                view.select(((0, where + SELECTED[0]), (0, where + SELECTED[1])))
            return
        del data["fills"]
        report["pages"][name_of(page)] = data
        view.close()
        state["view"] = None
        state["page"] += 1
    except Exception as exc:  # a page not read is said, and the run stops
        import traceback
        report["failed"].append(
            f"{name_of(page)}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    finally:
        imgui.end()

def before_exit():
    report["module_at_end"] = typesetter.module() is not None
    report["ready_at_end"] = typesetter.ready()
    report["trouble"] = typesetter.trouble()
    io = imgui.get_io()
    own = typesetter.font(Face.CODE)
    if own is not None:
        source = own.sources[0]
        report["facts"].update(
            loader=str(io.fonts.font_loader_name), atlas_flags=int(io.fonts.font_loader_flags),
            own_flags=int(source.font_loader_flags), pixel_snap_h=bool(source.pixel_snap_h),
            density=float(source.rasterizer_density),
            framebuffer_scale=float(io.display_framebuffer_scale.x),
            display=[float(io.display_size.x), float(io.display_size.y)],
            imgui=imgui.get_version(), atlas_entries=len(io.fonts.fonts))
    ts = typesetter.module()
    if ts is not None:
        report["facts"]["imtypeset"] = str(ts.build_info().version)
    report["load_end"] = loadavg()
    typesetter.unload()

params = hello_imgui.RunnerParams()
params.app_window_params.window_title = "monospace acceptance"
params.app_window_params.window_geometry.size = (int(WINDOW[0]), int(WINDOW[1]))
params.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
params.ini_disable = True
params.fps_idling.enable_idling = False
params.callbacks.load_additional_fonts = load_fonts
params.callbacks.show_gui = gui
params.callbacks.pre_new_frame = pre_new_frame
params.callbacks.before_exit = before_exit
immapp.run(params)
report["finished"] = state["page"] >= len(PAGES)
report["frames"] = state["n"]
OUT.write_text(json.dumps(report), encoding="utf-8")
print("REPORT pages", len(report["pages"]), "of", len(PAGES), "failed", len(report["failed"]))
for reason in report["failed"]:
    print("NOT READ:", reason, file=sys.stderr)
"""


def run_driver(window: Any, wanted: list[dict[str, Any]], name: str = "mono") -> dict[str, Any]:
    """Draw `wanted` in a real window and answer the driver's report; asserts the library drew."""
    script = window.out / f"{name}_acceptance_driver.py"
    spec = window.out / f"{name}_acceptance_pages.json"
    out = window.out / f"{name}_acceptance_report.json"
    script.write_text(DRIVER, encoding="utf-8")
    spec.write_text(json.dumps(wanted), encoding="utf-8")
    out.unlink(missing_ok=True)
    done = window.run([str(script), str(spec), str(out)], timeout=420.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-6000:]
    assert out.exists(), done.stdout[-4000:] + done.stderr[-6000:]
    got: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    # In the child, before and after: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + str(got.get("reason"))
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason")
    assert got["module_at_end"] is True and got["ready_at_end"] is True, got.get("trouble")
    assert not got["failed"], got["failed"][0]
    assert got["finished"] is True, "the driver did not reach its last page"
    return got


@pytest.fixture(scope="module")
def report(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    got = run_driver(window, pages())
    assert set(got["pages"]) == {page_name(page) for page in pages()}
    keep = os.environ.get("IMSCRIBE_MONO_REPORT")
    if keep:
        # For the record of a run: the window's own directory is removed at teardown.
        Path(keep).write_text(json.dumps(got), encoding="utf-8")
    return got


def _panes(report: dict[str, Any], name: str) -> list[dict[str, Any]]:
    page = report["pages"][name]
    return [page["panes"][key] for key in sorted(page["panes"])]


# -- what each requirement asserts of one page ---------------------------------------------


def holds_r4(report: dict[str, Any], name: str) -> None:
    for pane in _panes(report, name):
        assert len(pane["steps"]) == 1, f"{name}: steps {pane['steps']}"
        assert pane["drift"][0] == 0, f"{name}: rows {pane['drift'][0]} px apart at one column"


def holds_r5(report: dict[str, Any], name: str) -> None:
    for pane in _panes(report, name):
        for row in pane["rows"].values():
            assert row["pen"] == row["own"], f"{name}: {row['pen']} against ImGui's {row['own']}"
            assert row["pen"] == row["chrome"], f"{name}: {row['pen']} against {row['chrome']}"
            assert row["less_own_all"] == [0, 0] == row["less_chrome_all"], name


def holds_r1(report: dict[str, Any], name: str) -> None:
    for pane in _panes(report, name):
        worst = pane["less_rect_worst"]
        assert abs(worst[0]) <= 0.5, f"{name}: character {worst[1]} is {worst[0]:+.2f} px"


def holds_hit(report: dict[str, Any], name: str) -> None:
    for pane in _panes(report, name):
        wrong, of = pane["carets_wrong_all"]
        assert of > 250 and wrong == 0, f"{name}: {wrong} of {of} glyphs answer another caret"


def holds_selection(report: dict[str, Any], name: str) -> None:
    selections = report["pages"][name]["selection"]
    assert len(selections) == len(report["pages"][name]["panes"])
    for found in selections.values():
        assert len(found["fills"]) == 1, f"{name}: {found['fills']}"
        assert found["fills"][0] == found["pens"], f"{name}: fill {found['fills'][0]}"


def holds_r6(report: dict[str, Any], name: str) -> None:
    for pane in _panes(report, name):
        assert pane["glyphs"] > 250 and pane["fractional"] == [0, 0, 0], name


_DIFF = [
    page_name({"kind": "diff", "px": px, "layout": layout})
    for px in PIXEL_HEIGHTS
    for layout in LAYOUTS
]
_FENCE = [page_name({"kind": "fence", "px": px}) for px in PIXEL_HEIGHTS]
_ALL = _DIFF + _FENCE

BAKED_ADVANCE = dict(zip(PIXEL_HEIGHTS, (6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12), strict=True))
"""
Dear ImGui's baked advance of the bundled code face at each pixel height,
measured on 2026-10-12 (`.concerns/D-CELL--builder--result.md`, section 2) and
again on 2026-10-13: not the file's advance rounded (10.49 at 22 is 11).
"""


def _px(name: str) -> int:
    return int(name.split("px")[1].split()[0])


# -- every page: the diff view as a host gets it, and a fenced block ------------------------
#
# Until imtypeset 0.4 these were two sets. The diff view passed only with
# `cell="pixel"` (26 pages, 12 to 24), which drew the face at another em; the
# view with its default cell and the fence (21 pages, 14 to 20) were 105 strict
# xfails, `test_core_*`, naming imtypeset's H34 and H35. On imtypeset 0.4.1 all
# 105 passed (2026-10-13, `build/adopt-api-run1.log`: 105 XPASS(strict)), the
# marks came off, the option went, and the fence is held at 12 to 24 as well.


@pytest.mark.parametrize("name", _ALL)
def test_r4_one_step_on_every_row_and_rows_agree(report: dict[str, Any], name: str) -> None:
    """
    On imtypeset v0.3.0, at every pixel height from 14 to 20: two step sizes
    (7 px 101 times and 8 px 150 times over eight rows at 16), and rows 4 to
    23 px apart at one column.
    """
    holds_r4(report, name)


@pytest.mark.parametrize("name", _ALL)
def test_r5_characters_are_on_dear_imgui_s_pens(report: dict[str, Any], name: str) -> None:
    """
    On v0.3.0 at 16: characters 10, 20, 30, 40 and 74 of the 74-character row
    were 9, 19, 27, 27 and 27 px left of Dear ImGui's; at 17, 8 px right.
    """
    holds_r5(report, name)
    px = _px(name)
    page = report["pages"][name]
    for pane in _panes(report, name):
        # The cell is the advance Dear ImGui has baked for the face at the host's height.
        cell = BAKED_ADVANCE[px]
        assert cell == pane["own_advance_at_px"] == pane["chrome_advance_at_px"], (name, px)
        if name in _FENCE:
            # A fence's "cell" here is the library's own layout (a tenth of ten characters'
            # rectangle), which is the whole pixel to C-float arithmetic and not exactly
            # (measured 2026-10-13: 6.0000013 at 12, 8.0000092 at 16). The pens are exact.
            assert page["cell"] == pytest.approx(cell, abs=1e-4), name
        else:
            assert page["cell"] == cell, name
        assert pane["rows"]["ruler"]["pen"][-1] == 39 * cell
        assert pane["rows"]["long"]["pen"][-1] == 73 * cell
        # The glyphs come from the raster of the size asked for. (`cell="pixel"`
        # drew an even pixel height from the raster one pixel larger.)
        assert pane["baked"] == px, (name, pane["baked"])


@pytest.mark.parametrize("name", _ALL)
def test_r1_a_glyph_is_drawn_where_it_was_laid_out(report: dict[str, Any], name: str) -> None:
    """
    On v0.3.0 the worst glyph of a page was 4.6 (at 19) to 23.0 px (at 20)
    from the rectangle the library answers for it; 21.9 px at 16.

    R1 as pptmstr wrote it is half a pixel. Held tighter here, because it is
    measured tighter and the difference is one this package makes: on 0.4.1
    the worst glyph of any page is 0.0015 px from its rectangle, PROVIDED
    the block's indent is a whole pixel. A fenced block's was not (the
    theme's 11.44 px at a 12 px height) and its glyphs stood 0.44 px from
    their rectangles until `TypesetView` put a code block's indent on a
    whole pixel (`imscribe.ui.typeset_view._code_on_a_pixel`).
    """
    holds_r1(report, name)
    for pane in _panes(report, name):
        assert abs(pane["less_rect_worst"][0]) <= 0.01, (name, pane["less_rect_worst"])


@pytest.mark.parametrize("name", _ALL)
def test_a_hit_on_a_drawn_glyph_answers_the_carets_either_side_of_it(
    report: dict[str, Any], name: str
) -> None:
    """
    The library's `hit_test` answers the nearest CARET, so what is asked of a
    drawn glyph is: a quarter of a cell right of its pen is the caret before
    it, three quarters the caret after. On v0.3.0, 68 (fence, 19) to 225
    (fence, 14) of 274 glyphs answered otherwise; 54 of the 64 of the
    74-character row in the diff view at 16.

    (pptmstr's first reading -- the centre of the glyph's quad against the
    glyph's own index -- is not this and cannot be the test: where a glyph is
    drawn exactly on its rectangle the centre of its ink is in the right half
    of the cell at most sizes, and the nearest caret is the next one.)
    """
    holds_hit(report, name)


@pytest.mark.parametrize("name", _ALL)
def test_a_selection_s_fill_has_its_edges_on_the_glyph_pens(
    report: dict[str, Any], name: str
) -> None:
    """
    On v0.3.0, characters 21 to 40 of the 74-character row: the fill was 3 px
    left (at 19) to 14 px right (fence, 14) of the first glyph selected; 13 px
    right at 16.
    """
    holds_selection(report, name)


@pytest.mark.parametrize("name", _ALL)
def test_r6_nothing_is_off_the_pixel_grid(report: dict[str, Any], name: str) -> None:
    holds_r6(report, name)


@pytest.mark.parametrize("name", _DIFF)
def test_the_view_keeps_the_size_the_pitch_and_the_rows_the_host_asked_for(
    report: dict[str, Any], name: str
) -> None:
    """
    The row is the pitch the theme asked for, the height is rows times it,
    the cell is a whole pixel, the panes and the code start on it, and a
    header's width is a whole number of cells.

    **Restated on imtypeset 0.4.1.** This was
    `test_pixel_cell_keeps_the_pitch_and_the_rows_the_host_asked_for` and
    asserted `em_drawn != em_asked`: `cell="pixel"` got its whole cell by
    drawing the face at another em (16.000 for the 15.253 of a 16 px height).
    The library now puts the face on the device's cell at the em asked for,
    so the em drawn IS the em asked, and that is what is asserted. Nothing
    else here changed.
    """
    page = report["pages"][name]
    assert page["option"] == "pixel"
    assert page["row"] == page["row_asked"] == page["pitch_asked"]
    assert page["content_height"] == page["rows"] * page["row"]
    assert page["cell"] == int(page["cell"]) >= 1
    assert page["em_drawn"] == pytest.approx(page["em_asked"], abs=1e-6)
    for edges in page["pane_edges"]:
        assert all(edge % page["cell"] == 0 for edge in (edges[0], edges[2])), edges
    for pane in _panes(report, name):
        assert pane["first_pen_less_code_left"] == [0.0], name
    for width, text_width, line, text in page["headers"]:
        assert width == pytest.approx((1 + line) * page["cell"], abs=1e-2)
        assert text_width == pytest.approx((1 + text) * page["cell"], abs=1e-2)


# -- `cell=`: deprecated, accepted, ignored --------------------------------------------------


def test_cell_is_deprecated_and_a_wrong_name_is_still_the_host_s_mistake() -> None:
    """
    `cell=` no longer chooses anything: the default of the view and of the
    fences is `None`, a host that passes `"pixel"` (pptmstr was told to, at
    two places) or `"font"` gets a `DeprecationWarning` at its own line that
    says what the view does now, and a name that is not one of the two is
    still a `ValueError`, something that is no name a `TypeError` -- with or
    without the library, so before the constructor says the library is not
    there.

    **Restated on imtypeset 0.4.1.** Was
    `test_the_default_is_the_font_s_cell_and_a_wrong_name_is_the_host_s_mistake`:
    the defaults were `"font"`, and `TypesetDiffFences(cell="pixel").cell`
    was `"pixel"` with no warning. The option was a bridge until the library
    laid code out on the device's grid; it does, so there is nothing to choose.
    """
    import inspect
    import warnings

    from imscribe import Diff, Theme
    from imscribe.ui.typeset_diff_view import CELLS, TypesetDiffView
    from imscribe.ui.typeset_hosts import TypesetDiffFences
    from imscribe.ui.typeset_view import TypesetUnavailable

    assert CELLS == ("font", "pixel")
    assert inspect.signature(TypesetDiffView).parameters["cell"].default is None
    assert inspect.signature(TypesetDiffFences).parameters["cell"].default is None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert TypesetDiffFences().cell == "pixel"
    theme = Theme.build()

    def view_with(value: Any) -> Any:
        try:
            return TypesetDiffView(Diff(), theme, cell=value)
        except TypesetUnavailable:  # no library in this run: said after the warning
            return None

    for make, where in ((view_with, "TypesetDiffView"), (_fences_with, "TypesetDiffFences")):
        with pytest.warns(DeprecationWarning, match=r"cell=\"pixel\"\) is deprecated") as caught:
            made = make("pixel")
        assert where in str(caught[0].message) and "by default" in str(caught[0].message)
        assert caught[0].filename == __file__, "the warning is not at the host's call"
        assert made is None or made.cell == "pixel"
        with pytest.warns(DeprecationWarning, match=r"cell=\"font\"\) is deprecated"):
            made = make("font")
        assert made is None or made.cell == "pixel"
        with pytest.raises(ValueError, match="cell="):
            make("whole")
        with pytest.raises(TypeError, match="cell="):
            make(8)


def _fences_with(value: Any) -> Any:
    from imscribe.ui.typeset_hosts import TypesetDiffFences

    return TypesetDiffFences(cell=value)


_OPTION = r"""
import json
import sys
import warnings

from imgui_bundle import imgui

from imscribe import Diff, Theme, TypesetDiffFences, TypesetView, typesetter
from imscribe.ui.typeset_diff_view import TypesetDiffView, code_size
from imscribe.ui.typeset_view import TypesetUnavailable

report = {"module": typesetter.module() is not None, "reason": typesetter.reason()}
if not report["module"]:
    print("REPORT " + json.dumps(report))
    sys.exit(0)
imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
theme = Theme.build()
diff = Diff.from_texts("a\nb\n", "a\nc\n", "x.py")

# Before the fonts: the size asked for is what it is after them, and the grid cannot be
# answered.
early = TypesetDiffView(diff, theme, pixel_height=16.0)
report["early_size"] = list(code_size(theme, 16.0)[:2])
report["early_rows"] = [early.row_count, early.row_px, early.content_height]
try:
    early.grid
    report["early_grid"] = "answered"
except TypesetUnavailable as exc:
    report["early_grid"] = str(exc)
report["early_headers"] = [h.width_px for h in early.headers()]

report["ready"] = bool(typesetter.load_fonts()) and typesetter.ready()
report["size_ready"] = list(code_size(theme, 16.0)[:2])
ts = typesetter.module()
base = typesetter.base_style(theme, 0)
sizes = {}
for px in (None, 13.0, 14.0, 16.0, 21.0):
    row = {}
    for cell in (None, "font", "pixel"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            view = TypesetDiffView(diff, theme, pixel_height=px, cell=cell)
        grid = view.grid
        row[str(cell)] = {
            "cell": grid.cell, "row": grid.row, "em": grid.em * grid.scale,
            "asked": code_size(theme, px)[0], "content_height": view.content_height,
            "content_width": view.content_width, "height_for": view.height_for(300.0),
            "warned": [w.category.__name__ for w in caught], "option": view.cell,
            "library": ts.device_glyph_advance(int(ts.Face.Code), "0", base, grid.scale),
        }
        view.close()
    sizes[str(px)] = row
report["sizes"] = sizes

# On a living view: setting the option warns and moves nothing.
live = TypesetDiffView(diff, theme, pixel_height=16.0)
before = live.grid
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    live.cell = "font"
    live.cell = "pixel"
report["switched"] = [before.cell, live.grid.cell, live.grid is before, live.cell]
report["switched_warned"] = [w.category.__name__ for w in caught]
try:
    live.cell = "whole"
    report["switched_wrong"] = "taken"
except ValueError as exc:
    report["switched_wrong"] = str(exc)

# Through the fences: each diff a document hosts is on the device's cell, asked or not.
source = "```diff\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n```\n"
for name in (None, "font", "pixel"):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fences = TypesetDiffFences(cell=name, pixel_height=16.0)
        document = TypesetView(source, theme=theme, host_for=fences)
        (at,) = document.hosts
        hosted = fences.view_of(document, at)
    report["fenced_" + str(name)] = [
        hosted.cell, hosted.grid.cell, hosted.grid.row, [w.category.__name__ for w in caught]]
    document.close()
report["ready_at_end"] = typesetter.ready()
typesetter.unload()
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def option() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    done = subprocess.run(
        [sys.executable, "-c", _OPTION],
        capture_output=True,
        text=True,
        timeout=120.0,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-5000:]
    line = next(row for row in done.stdout.splitlines() if row.startswith("REPORT "))
    got: dict[str, Any] = json.loads(line.removeprefix("REPORT "))
    assert got["module"] is True, "the child did not get imtypeset: " + str(got.get("reason"))
    assert got["ready"] is True and got["ready_at_end"] is True
    return got


def test_before_the_fonts_a_view_is_made_and_its_grid_is_not_answered(
    option: dict[str, Any],
) -> None:
    """
    A view may be made before `typesetter.load_fonts()`: `code_size` answers
    the size asked for and the pitch, as it does once the fonts are in; the
    rows are counted; `grid` raises `TypesetUnavailable` as it always has
    there; `headers` answers the texts without widths.
    """
    assert option["early_size"] == pytest.approx(option["size_ready"], abs=1e-6)
    assert option["early_size"][0] == pytest.approx(15.2526, abs=1e-3)
    assert option["early_rows"][0] > 0
    assert option["early_rows"][2] == option["early_rows"][0] * option["early_rows"][1]
    assert option["early_grid"].startswith("imtypeset cannot draw")
    assert option["early_headers"] == [None]


def test_the_cell_is_the_device_s_whole_pixel_at_the_em_asked_for_whatever_cell_says(
    option: dict[str, Any],
) -> None:
    """
    With no window, at the theme's own size and at the pixel heights the
    frozen answers of the old `DiffView` were taken at: the cell is 8, 6, 7,
    8 and 10 px -- Dear ImGui's baked advance of the face -- exactly, and the
    em drawn is the em asked for; and the same with `cell="font"` and with
    `cell="pixel"`, each of which is one `DeprecationWarning`.

    **Restated on imtypeset 0.4.1.** Was
    `test_the_pixel_cell_is_dear_imgui_s_advance_and_only_the_em_moves`: the
    default's cell was the FILE's advance (8.000, 6.196, 6.673, 7.626,
    10.010) and `cell="pixel"` got 8, 6, 7, 8, 10 at an em of twice the cell
    (16.000 for 15.253). The library lays the code face out on the device's
    advances now, so the default is those whole pixels and no em moves.

    The library's own answer (`device_glyph_advance`) is within 2e-5 px of
    the whole pixel and not on it (8.000008583 at 16; float arithmetic on an
    em that is a rounded number): the view takes the whole pixel. Both are
    asserted, so a library that answers 8.0 exactly, or drifts further, shows.
    """
    wanted = {"None": 8.0, "13.0": 6.0, "14.0": 7.0, "16.0": 8.0, "21.0": 10.0}
    assert option["sizes"].keys() == wanted.keys()
    for px, row in option["sizes"].items():
        for name, warned in (
            ("None", []),
            ("font", ["DeprecationWarning"]),
            ("pixel", ["DeprecationWarning"]),
        ):
            got = row[name]
            assert got["cell"] == wanted[px], (px, name)
            assert got["warned"] == warned, (px, name)
            assert got["option"] == "pixel"
            assert got["em"] == pytest.approx(got["asked"], abs=1e-6), (px, name)
            assert got["library"] == pytest.approx(wanted[px], abs=1e-4), (px, name)
            for key in ("row", "content_height", "content_width", "height_for", "asked"):
                assert got[key] == row["None"][key], (px, name, key)


def test_at_13_px_the_cell_is_the_cell_the_old_diff_view_drew_on(
    option: dict[str, Any],
) -> None:
    """
    `tests/data/diff_view_answers.json` holds what `DiffView` answered at a
    13 px pixel height: a cell of 6 px for an advance of 6.196. The view's
    cell is the 6. (Until imtypeset 0.4 its default was the 6.196 and only
    `cell="pixel"` gave the 6.)
    """
    frozen = json.loads((_ROOT / "tests" / "data" / "diff_view_answers.json").read_text("utf-8"))
    small = frozen["window"]["small"]
    assert small["cell"] == 6 and small["advance"] == pytest.approx(6.196368, abs=1e-5)
    at_13 = option["sizes"]["13.0"]["None"]
    assert at_13["cell"] == small["cell"]
    assert at_13["row"] == small["row"]


def test_setting_cell_on_a_living_view_warns_and_moves_nothing_and_a_fenced_diff_is_the_same(
    option: dict[str, Any],
) -> None:
    """
    **Restated on imtypeset 0.4.1.** Was
    `test_the_option_can_be_changed_on_a_living_view_and_reaches_a_fenced_diff`:
    `view.cell = "pixel"` moved the grid from 7.626 to 8.0 and back, and a
    fence made with `cell="font"` hosted a 7.626 px cell. There is one cell
    now: 8.0 at 16 px, before and after, through the fences too.
    """
    before, after, same, name = option["switched"]
    assert before == after == 8.0 and same is True and name == "pixel"
    assert option["switched_warned"] == ["DeprecationWarning", "DeprecationWarning"]
    assert "cell=" in option["switched_wrong"]
    for given, warned in (
        ("None", []),
        ("font", ["DeprecationWarning"]),
        ("pixel", ["DeprecationWarning"]),
    ):
        got = option["fenced_" + given]
        assert got[:2] == ["pixel", 8.0] and got[3] == warned, given
        assert got[2] == option["fenced_None"][2]


_ACT = [
    page_name({"kind": "act", "px": px, "layout": layout})
    for px in ACT_HEIGHTS
    for layout in LAYOUTS
]
_LONG = "total = float(baked.get_char_advance(code)) + kern_px  # 40th is in 'kern'"


@pytest.mark.parametrize("name", _ACT)
def test_scrolled_sideways_the_row_stays_on_the_grid(report: dict[str, Any], name: str) -> None:
    """
    In a view forty cells wide the 74-character row does not fit: the view
    claims its scrollbar's height, and with the code scrolled ten cells every
    glyph of the row still inside the pane stands a whole number of cells
    from where the code begins, on a whole pixel, as it did before.
    """
    page = report["pages"][name]
    assert page["bar"] > 0 and page["content_width"] > page["width"]
    assert page["before"]["scroll_x"] == 0
    assert page["after"]["scroll_x"] == 10 * page["cell"]
    for moment in ("before", "after"):
        seen = page[moment]
        assert seen["glyphs"] >= 8, (name, moment, seen)
        assert seen["on_grid"] == seen["whole"] == seen["glyphs"], (name, moment, seen)


@pytest.mark.parametrize("name", _ACT)
def test_a_press_and_a_drag_select_the_characters_under_the_pointer(
    report: dict[str, Any], name: str
) -> None:
    """
    With the code scrolled, by the mouse: a press a quarter of a cell into
    the 13th character and a release a quarter into the 21st select
    characters 13 to 20 and copy as them; three quarters into the 16th and
    the 23rd select 17 to 23 (the nearest caret is the one after).
    """
    page = report["pages"][name]
    where = page["where"]
    first, second = page["drags"]
    assert first["selection"] == [[*where, 12], [*where, 20]], name
    assert first["text"] == _LONG[12:20] == "t(baked."
    assert second["selection"] == [[*where, 16], [*where, 23]], name
    assert second["text"] == _LONG[16:23] == "ked.get"
    assert first["scroll_x"] == second["scroll_x"] == 10 * page["cell"]


# -- the two small rules of this package's own, with no library -----------------------------


def test_the_cell_is_the_library_s_answer_on_the_whole_framebuffer_pixel_it_is_beside() -> None:
    """
    `_device_cell` with a stand-in for the library: an answer within 0.001
    px of a whole FRAMEBUFFER pixel is that pixel (8.000008583 is 8 at a
    density of 1; 7.500004 is 7.5 at 2), any other answer is left as it came,
    the role and the character asked are the code face's `0` at the scale
    given, and where the library itself refuses (its own error: no atlas to
    ask) the cell is the advance it lays ten characters out at. An error that
    is not the library's is raised as it is.
    """
    from types import SimpleNamespace

    from imscribe.ui import typeset_diff_view as module

    asked: list[tuple[Any, ...]] = []

    def library(answer: Any) -> Any:
        def device_glyph_advance(face: int, char: str, style: Any, scale: float) -> float:
            asked.append((face, char, style, scale))
            if isinstance(answer, BaseException):
                raise answer
            return float(answer)

        return SimpleNamespace(
            Face=SimpleNamespace(Code=7), device_glyph_advance=device_glyph_advance
        )

    base = object()
    assert module._device_cell(library(8.000008583068848), base, 0.95, 18, 1.0) == 8.0
    assert asked == [(7, "0", base, 0.95)]
    assert module._device_cell(library(7.500004), base, 1.0, 18, 2.0) == 7.5
    assert module._device_cell(library(7.500004), base, 1.0, 18, 1.0) == 7.500004
    assert module._device_cell(library(7.626), base, 1.0, 18, 1.0) == 7.626
    assert module._device_cell(library(0.0), base, 1.0, 18, 1.0) == 0.0

    refusal = type("Error", (Exception,), {"__module__": "imtypeset"})("no atlas")
    laid: list[tuple[Any, ...]] = []
    kept = module._advance_at
    module._advance_at = lambda ts, style, scale, row: laid.append((style, scale, row)) or 7.626  # type: ignore[assignment]
    try:
        assert module._device_cell(library(refusal), base, 0.5, 18, 1.0) == 7.626
        assert laid == [(base, 0.5, 18)]
        with pytest.raises(ZeroDivisionError):
            module._device_cell(library(ZeroDivisionError("ours")), base, 0.5, 18, 1.0)
        assert len(laid) == 1
    finally:
        module._advance_at = kept


def test_a_code_block_s_indent_is_put_on_a_whole_pixel_and_no_other_block_s_is() -> None:
    from imscribe.description import KIND_CODE, KIND_PARAGRAPH, BlockDescription
    from imscribe.ui.typeset_view import _code_on_a_pixel

    for given, whole in ((11.4395, 11.0), (15.999998, 16.0), (45.6, 46.0), (0.5, 1.0), (0.0, 0.0)):
        code = BlockDescription(kind=KIND_CODE, text="x", left_indent=given)
        assert _code_on_a_pixel(code).left_indent == whole
        assert _code_on_a_pixel(code)._replace(left_indent=given) == code  # nothing else moved
        prose = BlockDescription(kind=KIND_PARAGRAPH, text="x", left_indent=given)
        assert _code_on_a_pixel(prose) is prose
    already = BlockDescription(kind=KIND_CODE, text="x", left_indent=16.0)
    assert _code_on_a_pixel(already) is already

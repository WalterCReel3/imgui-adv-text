#!/usr/bin/env python3
"""
Where each glyph lands under four placement rules, and what ImGui itself does.

`docs/advance-rule.md` is the write-up. This is the instrument, committed so that
every number in that document can be re-derived rather than believed --
`docs/status.md` Provenance is the standard and the single most common defect in
this project was a confident figure nobody could reproduce.

## The four rules

A rigid span is a run of glyphs with no glue in it -- a word. Its anchor is
snapped to a whole pixel by `advtext.backends.imgui_draw.snap_px` and every rule
below places the rest of the span relative to that snapped anchor. **Snapping the
anchor first is not optional and is not a detail**: it is what stops a word
landing on two different sub-pixel phases in two places, and a harness that skips
it makes every rule appear to phase. One did, and the defect looked like a
property of the rules rather than of the harness.

    whole     each glyph's offset from the anchor, rounded to 1 px
    half      each offset rounded to 0.5 px   (what the tree ships; PEN_QUANTUM_PX)
    advance   each *gap* rounded to 1 px, accumulated from the anchor
    exact     no rounding of the offset at all

`whole` and `half` round **positions**. `advance` rounds **advances**, which is
what ImGui does -- see `--native`. The two are not the same algorithm and they
fail differently: rounding positions keeps a word's total width honest and lets an
individual gap be a whole pixel wrong; rounding advances keeps every gap within
half a pixel and lets the total width drift.

## The four axes, and why all four

    consistency    distinct shapes per span key. Zero is the property the whole
                   rigid-span design exists to provide, and it is the one the
                   user has called foundational.
    unfuzzed       glyphs whose pen is not on a whole pixel. Such a glyph is
                   resolved by the renderer's bilinear filter, which is the fuzz.
                   Counting pens is an upper bound on what a screenshot shows: it
                   says how many glyphs are EXPOSED to resampling, not how visible
                   the result is. Only a render answers that.
    gap fidelity   rendered inter-letter gap against the designed one.
    width cost     how far a word's total width moves, since under `advance` that
                   is what the inter-word space has to absorb.

A rule that improves one axis while quietly wrecking another is the failure this
script exists to make impossible to miss, which is why it prints all four and
refuses to reduce them to a score.

## Running it

    .venv/bin/python scripts/pen_rules.py            # the four axes
    .venv/bin/python scripts/pen_rules.py --native   # what ImGui does, from the
                                                     # vertex buffer

Needs no display: a frame is not a window. The head of `tests/test_imgui_draw.py`
says why, and `--native` reads `ImDrawList.vtx_buffer` directly, which is the
ground truth for placement and is upstream of any rasterisation.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NATIVE_WORDS = ("people", "counting", "difference")
"""
The three words the user reported defects in, kept rather than generalised.

"people" and "counting" are the inter-letter gap complaints; "difference" is the
one whose `iffe` fused into a single ink run, and it is also the word
`scripts/font_grid.py` found the kern table breaks the grid property on.
"""


def _frame():
    """
    A live ImGui frame with no window, and the faces this project ships.

    A draw list must come from a live frame -- constructing a bare `ImDrawList`
    outside one dumps core rather than raising.
    """
    from imgui_bundle import imgui

    imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    return imgui, io


def place_whole(left: float, offsets: list[float]) -> list[float]:
    return [left + math.floor(o + 0.5) for o in offsets]


def place_half(left: float, offsets: list[float]) -> list[float]:
    from advtext.backends.imgui_draw import snap_offset_px

    return [left + snap_offset_px(o) for o in offsets]


def place_advance(left: float, offsets: list[float]) -> list[float]:
    """
    ImGui's rule, confined to a span: round each gap, accumulate from the anchor.

    The first glyph sits exactly on the anchor, so a word still begins on a whole
    pixel and the span-identity property is untouched. The accumulated error
    cannot cross a glue node, because the next span starts from its own
    independently snapped anchor -- which is why the 42 px per 44 characters that
    `scripts/verify_advances.py` measured over a *line* does not apply here.
    """
    out = [left]
    # strict=False: pairing a list with its own tail is deliberately ragged.
    for a, b in zip(offsets, offsets[1:], strict=False):
        out.append(out[-1] + math.floor((b - a) + 0.5))
    return out


def place_exact(left: float, offsets: list[float]) -> list[float]:
    return [left + o for o in offsets]


RULES = (
    ("whole", place_whole),
    ("half", place_half),
    ("advance", place_advance),
    ("exact", place_exact),
)


def axes() -> int:
    """Measure the four rules on the demo document and print the four axes."""
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    imgui, io = _frame()

    import test_imgui_draw as T

    from advtext import fontlib
    from advtext.backends.imgui_draw import snap_px
    from advtext.fontmetrics import Face
    from advtext.units import px_from_sp

    faces = {
        f: io.fonts.add_font_from_file_ttf(str(fontlib.imgui_font_file(f)), T.DISPLAY_SIZE_PX)
        for f in Face
    }
    imgui.new_frame()
    spans = T._spans(T._demo_commands())

    shapes: dict[str, dict] = {n: {} for n, _ in RULES}
    pens: dict[str, list[float]] = {n: [] for n, _ in RULES}
    gap_err: dict[str, list[float]] = {n: [] for n, _ in RULES}
    width_err: dict[str, list[float]] = {n: [] for n, _ in RULES}

    for span in spans:
        vis = [c for c in span if T._visible(faces.get, c) is not None]
        anchor = T._anchor_of(faces.get, span)
        if not vis or anchor is None:
            continue
        left = snap_px(T.ORIGIN_X + px_from_sp(anchor.x))
        offsets = [px_from_sp(c.x - anchor.x) for c in vis]
        designed = [left + o for o in offsets]
        dgaps = [b - a for a, b in zip(designed, designed[1:], strict=False)]
        key = ("".join(chr(c.codepoint) for c in span), tuple(c.font for c in span))
        for name, place in RULES:
            at = place(left, offsets)
            shapes[name].setdefault(key, set()).add(tuple(round(p - left, 6) for p in at))
            pens[name] += at
            # strict=True on the outer zip: a rule that returned the wrong number
            # of positions would otherwise be measured against a truncated
            # designed-gap list and score well for the wrong reason.
            rendered = [b - a for a, b in zip(at, at[1:], strict=False)]
            gap_err[name] += [abs(g - d) for g, d in zip(rendered, dgaps, strict=True)]
            if len(at) > 1:
                width_err[name].append(abs((at[-1] - at[0]) - (designed[-1] - designed[0])))

    print(f"spans {len(spans)}\n")
    print(f"{'rule':<8} {'2 shapes':>9} {'fractional pens':>18} {'gap mean':>9} {'gap max':>8}")
    for name, _ in RULES:
        frac = sum(1 for p in pens[name] if p != int(p))
        total = len(pens[name])
        print(
            f"{name:<8} {sum(len(v) > 1 for v in shapes[name].values()):>9} "
            f"{f'{frac} of {total}':>18} "
            f"{sum(gap_err[name]) / len(gap_err[name]):>9.4f} {max(gap_err[name]):>8.4f}"
        )

    print("\ngaps off by more than half a pixel (the uneven-rhythm defect):")
    for name, _ in RULES:
        n = sum(1 for e in gap_err[name] if e > 0.5)
        print(f"  {name:<8} {n:>5} of {len(gap_err[name])}")

    print("\nword width moved -- what the inter-word space must absorb:")
    for name, _ in RULES:
        w = width_err[name]
        print(
            f"  {name:<8} mean {sum(w) / len(w):.4f} px   worst {max(w):.4f} px   "
            f"words off by >=1 px: {sum(1 for e in w if e >= 1.0)} of {len(w)}"
        )

    print("\ndistinct sub-pixel phases a glyph can be drawn at:")
    for name, _ in RULES:
        print(f"  {name:<8} {len(sorted({round(p % 1.0, 6) for p in pens[name]}))}")
    imgui.render()
    return 0


def native() -> int:
    """
    Read ImGui's own glyph placement out of the vertex buffer.

    This settles by measurement a claim that was twice asserted from this
    project's docstrings and was wrong both times: that `ImFont::RenderText`
    truncates the origin once and then accumulates *unrounded* advances. It does
    not. imgui_bundle ships no headers, so there is nothing to read but pixels
    and vertices.
    """
    sys.path[:0] = [str(ROOT)]
    imgui, io = _frame()

    from advtext import fontlib
    from advtext.fontmetrics import Face

    size = 16.0
    font = io.fonts.add_font_from_file_ttf(str(fontlib.imgui_font_file(Face.PROSE)), size)
    imgui.new_frame()
    draw_list = imgui.get_background_draw_list()

    for label, flag_on in (("flag CLEAR (ImGui default)", False), ("flag SET", True)):
        restore = draw_list.flags
        if flag_on:
            draw_list.flags = restore | int(imgui.ImDrawListFlags_.text_no_pixel_snap)
        print(f"\n=== {label} ===")
        for word in NATIVE_WORDS:
            start = len(draw_list.vtx_buffer)
            draw_list.add_text(font, size, imgui.ImVec2(100.0, 50.0), 0xFFFFFFFF, word)
            buf = draw_list.vtx_buffer
            xs = [buf[i].pos.x for i in range(start, len(buf))]
            # ImGui emits four vertices per glyph; the minimum x of each group of
            # four is the quad's left edge without assuming their order.
            lefts = [min(xs[i : i + 4]) for i in range(0, len(xs) - 3, 4)]
            if not lefts:
                print(f"  {word:<11} NO QUADS -- nothing measured")
                continue
            frac = [x for x in lefts if x != int(x)]
            print(f"  {word:<11} {[round(x, 4) for x in lefts]}")
            print(f"  {'':<11} fractional: {len(frac)} of {len(lefts)}")
        draw_list.flags = restore
    imgui.render()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--native",
        action="store_true",
        help="read ImGui's own glyph placement from the vertex buffer instead",
    )
    args = parser.parse_args(argv)
    return native() if args.native else axes()


if __name__ == "__main__":
    raise SystemExit(main())

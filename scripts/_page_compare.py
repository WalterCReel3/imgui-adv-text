"""
Set a page of real demo prose in each candidate face and write the PNGs.

Word crops answer "which glyph pair moved". They do not answer "does this read
better as a page", which is the question a face change actually turns on. So
this sets several paragraphs of `demo/columns.md` at one measure in each face
and writes them at 1:1 and at 3x.

Run: .venv/bin/python scripts/_page_compare.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from font_grid import Metrics, _pair_kerns, resolve  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402


def read_wide_metrics(name: str, path: Path, chars: str) -> Metrics | None:
    """
    `font_grid.read_metrics`, but over an arbitrary character set.

    The original reads a-z and A-Z only, which is right for its alphabet table
    and useless for real prose -- the first full stop raises `KeyError`. This is
    a local widening rather than a change to `font_grid.py`, because
    `D2-gridfont` holds that file on the board and two agents in one file is the
    thing the board exists to prevent.
    """
    if not path.is_file():
        return None
    font = TTFont(path, lazy=True)
    try:
        upm = int(font["head"].unitsPerEm)
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        advances: dict[str, int] = {}
        glyphs: dict[str, str] = {}
        for letter in sorted(set(chars)):
            glyph = cmap.get(ord(letter))
            if glyph is None or glyph not in hmtx.metrics:
                continue
            advances[letter] = int(hmtx[glyph][0])
            glyphs[letter] = glyph
        return Metrics(
            name=name, path=path, upm=upm, advances=advances, kerns=_pair_kerns(font, glyphs)
        )
    finally:
        font.close()


from render_grid_compare import (  # noqa: E402
    _assert_has_ink,
    bake,
    draw_page,
    magnify,
    wrap_justified,
    write_png,
)

# One measure for both faces, in pixels. A column is a physical width, so
# holding the pixels fixed and letting the character count fall out is the
# honest comparison -- it is what the reader's eye actually traverses. The
# characters-a-line each face achieves at this measure is reported, because
# that is the number Bringhurst's 45-75 band is stated in.
MEASURE_PX = 460.0

CASES = (
    ("Roboto 16px (ships today)", "@bundle:Roboto/Roboto-Regular.ttf", 16.0, 20.0),
    (
        "Liberation Serif 18px",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        18.0,
        23.0,
    ),
)


def prose_words(limit: int = 150) -> tuple[str, list[str]]:
    """Real body text out of demo/columns.md, with markdown emphasis stripped."""
    text = Path("demo/columns.md").read_text(encoding="utf-8")
    body = text.split("# The Measure", 1)[1]
    paragraphs = [
        p.strip().replace("\n", " ")
        for p in body.split("\n\n")
        if p.strip() and not p.lstrip().startswith("#")
    ]
    prose = re.sub(r"[*_`]", "", " ".join(paragraphs[:5]))
    return prose, prose.split()[:limit]


def main() -> int:
    prose, words = prose_words()
    out = Path("artifacts/gridfont")
    out.mkdir(parents=True, exist_ok=True)
    letters = "".join(sorted(set(prose)))

    pages: dict[str, np.ndarray] = {}
    for label, spec, size, leading in CASES:
        path = resolve(spec)
        metrics = read_wide_metrics(label, path, letters + " ")
        if metrics is None:
            print(f"skipped {label}: {path} missing", file=sys.stderr)
            continue
        baked = bake(path, size, letters)
        # Whole-pixel only. That is what ships, and it is the setting the user
        # observed even spacing under for the non-Roboto faces.
        canvas = draw_page(baked, metrics, words, size, MEASURE_PX, 1.0, leading)
        _assert_has_ink(canvas, label, "page")
        pages[label] = canvas

        lines = wrap_justified(metrics, words, size, MEASURE_PX)
        counts = [sum(len(w) for w in line) + len(line) - 1 for line, _ in lines]
        print(
            f"{label:<28} {len(lines):>2} lines, "
            f"mean {np.mean(counts):.1f} characters a line, canvas {canvas.shape}"
        )
        slug = label.lower().replace(" ", "-").replace("(", "").replace(")", "")
        write_png(out / f"page-{slug}.png", canvas, f"{label} whole-pixel, greedy-justified")
        write_png(out / f"page-{slug}-3x.png", magnify(canvas, 3), f"{label} 3x")

    if len(pages) < 2:
        print("need both faces for a comparison", file=sys.stderr)
        return 1

    gap = 28
    height = max(c.shape[0] for c in pages.values())
    width = sum(c.shape[1] + gap for c in pages.values())
    sheet = np.zeros((height, width), dtype=np.uint8)
    x = 0
    for canvas in pages.values():
        sheet[: canvas.shape[0], x : x + canvas.shape[1]] = canvas
        x += canvas.shape[1] + gap
    write_png(out / "page-side-by-side.png", sheet, " | ".join(pages))
    print("wrote page-side-by-side.png (left: Roboto 16, right: Liberation Serif 18)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

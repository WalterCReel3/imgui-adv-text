#!/usr/bin/env python3
"""
Same-build, content-located, change-reporting comparison of two renders.

**Why this exists, stated bluntly, because the reason is the specification.**
Visual self-assessment failed four times in this project's history, three of
them by the lead, and every failure had the same shape: a confident sentence
about *quality* resting on a measurement that could not have detected the
defect it was used to rule out. The four are written up in
`docs/visual-review.md` and summarised here because they map one-to-one onto
what this module refuses to do:

  1. "clean and evenly spaced", from a 4x crop of the word "people". Measured
     immediately afterwards: inter-letter gaps 1, 2, 2 / 2, 1, 1, 2 px.
     -> This module reports gaps as numbers and never as an adjective.
  2. "no blur difference", from 36.2% against 36.8% solid ink -- comparing the
     first word of a line against the rest of *the same line*, both equally
     resampled, no sharp reference anywhere in the frame. T11 then measured
     1734 of 1734 glyph quads being resampled.
     -> This module compares two *renders*, region by named region, and says
        which glyphs moved and by how much.
  3. `rasterizer_density=3` called "crisp" while the midtone share on screen
     had collapsed from 41.2% to 11.2%. The destruction of antialiasing was
     read as an improvement.
     -> `midtone_flags` warns on a large move in **either** direction and
        explicitly declines to say which direction is better.
  4. The visual review was dispatched to an agent with no shell, which could
     only read PNGs other agents had left behind, from builds it could not
     identify.
     -> Every PNG this module writes carries the build that produced it inside
        the file, and `compare` refuses an unstamped one.

Two further incidents shape the region finder. T2-specimen found, only by
looking, that the widest label ended exactly where its pangram began -- every
arithmetic assertion passed. T15 measured that a **misspelt tab name yields a
byte-identical photograph of the Document tab**, exit 0, no warning. Both are
ways to produce a confident review of the wrong thing, so `shoot` validates the
tab name against the tabs the app actually draws and refuses a name it cannot
find, and every region is located by content with a loud failure when it is
absent.

## What it does not do

It does not score. There is no "better", no pass mark and no threshold that
means "good". A metric here establishes **change**; whether the change is an
improvement is the user's call, and this module's output is deliberately
awkward to quote as if it were a verdict.

## Subcommands

    shoot    render one tab/state and write a stamped PNG
    pair     render two in one invocation, then compare -- same build by
             construction, which is the only way to be sure of it
    compare  diff two already-stamped PNGs (refuses across builds unless told)
    regions  print what the region finder sees in a PNG, so a name can be
             checked before it is trusted
    crop     write a magnified crop of a named region, for a human to look at

Regions are addressed by name, not by pixel coordinate:

    sheet                       the white page rect
    column:2                    the second column band of text on the sheet
    column:2/row:7              the seventh text row in it
    text:A column is not        the text row beginning with those words,
                                located by matching real font advances
    text:A column is not/words:1-2   just the first two of them

`text:` is the interesting one and the one that answers "the counting line".
It has no OCR in it: it takes the advance width of each word from
`advtext.fontlib`, then looks for a row of ink whose runs group into that
sequence of widths with a real word space before each group. On
`artifacts/demo-columns-2.png` the phrase "is shorter than most people guess."
matches exactly one of the 55 text rows on that page; with the word-space
constraint switched off (`min_space=0`) it matches two, and on a fresh
`columns:2` shot "A column is not" matches one against three. The constraint is
what makes the finder a finder rather than a plausible-looking guess.

Nothing in here needs a display except `shoot` and `pair`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parent.parent

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(ROOT))


Grey = NDArray[np.float64]
Rgb = NDArray[np.uint8]


class RegionNotFound(Exception):
    """
    A named region is not in this image.

    Raised rather than returning an empty or approximate rectangle **because
    two of the four incidents this module exists for were crops that landed in
    the wrong place and said nothing**. The lead's crops hit whitespace twice
    and were one line off once, and each mistake stayed invisible until
    somebody read the image. A blank crop is a successful-looking failure.
    """


class AmbiguousRegion(RegionNotFound):
    """
    More than one region in this image answers to the name, so none is returned.

    Subclasses `RegionNotFound` so a caller that only wants "I did not get a
    trustworthy rectangle" can catch one exception, while a caller that wants
    to say *why* can separate them.
    """


class NotStamped(Exception):
    """
    A PNG with no build stamp was handed to a comparison.

    This is the T7-look failure made impossible instead of discouraged: that
    review could not tell which build any of its artifacts came from, correctly
    said so, and had nothing else to review.
    """


# ----------------------------------------------------------------------
# PNG in and out, including the stamp.
#
# `scripts/shot.py` already has an encoder; this is a decoder plus a chunk
# rewriter, and it deliberately does not import that module. Loading a sibling
# script would put `scripts/` on `sys.path`, which `tests/test_shot.py` and
# three other test modules go out of their way to avoid.


_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_STAMP_KEY = b"advtext-shot"


def _iter_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """
    Split a PNG into `(tag, payload)`, checking only what must be true to parse.

    CRCs are not verified. A corrupt chunk is not a failure mode this tool has
    ever seen, and zlib will complain about a damaged IDAT anyway.
    """
    if data[:8] != _SIGNATURE:
        raise ValueError("not a PNG: the eight-byte signature is wrong")
    out: list[tuple[bytes, bytes]] = []
    i = 8
    while i + 8 <= len(data):
        (length,) = struct.unpack(">I", data[i : i + 4])
        tag = data[i + 4 : i + 8]
        out.append((tag, data[i + 8 : i + 8 + length]))
        i += 8 + length + 4
    return out


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def read_png(path: Path) -> tuple[Rgb, dict[str, str]]:
    """
    Decode a truecolour 8-bit PNG to `(H, W, 3)` uint8, with its `tEXt` entries.

    Only what `scripts/shot.py` writes is supported: bit depth 8, colour type 2
    or 6, no interlace. Filter type 0 -- which is all that encoder emits -- takes
    a vectorised path; the other four are unfiltered row by row in Python and
    are slow enough on a 1920-wide frame to be worth the branch. Anything else
    raises, rather than being decoded approximately.
    """
    data = path.read_bytes()
    width = height = colour_type = 0
    depth = interlace = 0
    idat = bytearray()
    text: dict[str, str] = {}
    for tag, payload in _iter_chunks(data):
        if tag == b"IHDR":
            width, height, depth, colour_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"tEXt":
            key, _, value = payload.partition(b"\x00")
            text[key.decode("latin-1")] = value.decode("latin-1")
    if depth != 8 or colour_type not in (2, 6) or interlace != 0:
        raise ValueError(
            f"{path}: only 8-bit truecolour non-interlaced PNGs are supported here "
            f"(depth={depth}, colour_type={colour_type}, interlace={interlace})"
        )

    channels = 3 if colour_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = (stride + 1) * height
    if len(raw) != expected:
        raise ValueError(f"{path}: decompressed to {len(raw)} bytes, expected {expected}")

    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, stride + 1)
    if int(rows[:, 0].max(initial=0)) == 0:
        pixels = rows[:, 1:].reshape(height, width, channels)
    else:  # pragma: no cover - shot.py never emits a non-zero filter
        pixels = _unfilter(rows, channels)
    return np.ascontiguousarray(pixels[:, :, :3]), text


def _unfilter(rows: NDArray[np.uint8], channels: int) -> NDArray[np.uint8]:  # pragma: no cover
    """
    The general PNG unfilter, for files this project did not write.

    Kept correct rather than kept fast: every filter type has a left-neighbour
    dependency except 0 and 2, so this is a Python loop and a 1920x1080 frame
    takes seconds. `read_png` only reaches it when a row says it needs it.
    """
    height, stride1 = rows.shape
    stride = stride1 - 1
    out = np.zeros((height, stride), dtype=np.uint8)
    prior = bytearray(stride)
    for y in range(height):
        filt = int(rows[y, 0])
        line = bytearray(rows[y, 1:].tobytes())
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prior[x]
            c = prior[x - channels] if x >= channels else 0
            if filt == 0:
                value = line[x]
            elif filt == 1:
                value = line[x] + a
            elif filt == 2:
                value = line[x] + b
            elif filt == 3:
                value = line[x] + (a + b) // 2
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                value = line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)
            else:
                raise ValueError(f"row {y}: unknown PNG filter type {filt}")
            line[x] = value & 0xFF
        out[y] = np.frombuffer(bytes(line), dtype=np.uint8)
        prior = line
    return out


def encode_png(rgb: Rgb, text: dict[str, str] | None = None) -> bytes:
    """
    Encode `(H, W, 3)` uint8 as a truecolour PNG, with optional `tEXt` chunks.

    Row 0 is written first, which is PNG's own order and the order
    `hello_imgui.final_app_window_screenshot` hands rows back in, so nothing is
    reversed here. `scripts/shot.py::_grab` records how that was checked -- by
    reading the image, because a vertical flip is invisible to every cheap
    assertion.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected (H, W, 3) uint8, got {rgb.shape!r}")
    height, width = int(rgb.shape[0]), int(rgb.shape[1])
    flat = np.ascontiguousarray(rgb, dtype=np.uint8).reshape(height, width * 3)
    raw = b"".join(b"\x00" + flat[y].tobytes() for y in range(height))
    body = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    for key, value in (text or {}).items():
        body += _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1"))
    body += _chunk(b"IDAT", zlib.compress(raw, 6))
    return _SIGNATURE + body + _chunk(b"IEND", b"")


def stamp_png_bytes(data: bytes, entries: dict[str, str]) -> bytes:
    """
    Insert `tEXt` chunks into an existing PNG without re-encoding its pixels.

    Re-encoding would be simpler to write and worse: it would put this module's
    compression settings between `shot.py`'s output and the file on disk, so a
    byte comparison of two shots would be comparing this module instead of the
    app. T15 proved a byte comparison is load-bearing here -- that is how the
    misspelt-tab bug was pinned down -- so the pixels are passed through
    untouched.
    """
    chunks = _iter_chunks(data)
    out = bytearray(_SIGNATURE)
    inserted = False
    for tag, payload in chunks:
        if tag == b"tEXt" and payload.split(b"\x00", 1)[0] == _STAMP_KEY:
            continue
        out += _chunk(tag, payload)
        if tag == b"IHDR" and not inserted:
            for key, value in entries.items():
                out += _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1"))
            inserted = True
    return bytes(out)


# ----------------------------------------------------------------------
# Build identity


def build_id(root: Path = ROOT) -> str:
    """
    A string that changes whenever anything the render depends on changes.

    A git revision alone is not enough and in this tree it is not even
    available: **the repository has no commits**, so `git rev-parse HEAD` exits
    128. Every source file is staged and unversioned. A rev would also be
    useless during a session like this one, where a dozen agents write between
    two shots without committing.

    So the identity is the revision *and* a digest of the working tree: every
    file git knows about under `advtext/`, `scripts/` and `demo/`, tracked or
    merely untracked-and-not-ignored, hashed by path and content. Two shots
    with the same id were taken from the same source; two with different ids
    were not, and `compare` will say so.

    Falls back to `unknown+<digest>` where git is not usable at all. The digest
    is the part that matters and it does not need git to be a repository.
    """
    try:
        rev = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        head = rev.stdout.strip() if rev.returncode == 0 else "no-commit"
    except OSError:  # pragma: no cover - git absent
        head = "unknown"

    digest = hashlib.sha256()
    for path in _source_files(root):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"{head}+{digest.hexdigest()[:12]}"


def _source_files(root: Path) -> list[Path]:
    """
    Everything the render could depend on, in a stable order.

    `git ls-files -c -o --exclude-standard` covers both the index and untracked
    files while honouring `.gitignore`, which matters because `artifacts/` is
    ignored and hashing it would make every build id differ from every other.
    Falls back to a glob when git cannot answer.
    """
    wanted = ("advtext", "scripts", "demo")
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-c", "-o", "--exclude-standard", "--", *wanted],
            capture_output=True,
            text=True,
            check=False,
        )
        names = listed.stdout.split("\n") if listed.returncode == 0 else []
    except OSError:  # pragma: no cover - git absent
        names = []
    if not any(names):
        names = [
            str(p.relative_to(root))
            for base in wanted
            for p in sorted((root / base).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        ]
    paths = sorted({root / name for name in names if name})
    return [p for p in paths if p.is_file() and "__pycache__" not in p.parts]


# ----------------------------------------------------------------------
# Shooting, with the tab name checked


def known_tabs() -> tuple[str, ...]:
    """
    The tab names `advtext.ui.app.App.gui` actually draws.

    **This is a defence against a measured trap, not a tidiness check.** T15
    shot `--tab colums` and got a byte-identical photograph of the Document
    tab, exit 0, no warning: `App.gui` compares `open_tab` against each name it
    draws and simply never matches, so an unknown name selects nothing and the
    default tab is photographed under the wrong filename. A visual review of
    that file is a confident review of the wrong picture.

    `advtext.ui.app.TAB_NAMES` is the single source, so there is no second
    list here that could drift. That export landed with T18-colmargin; before
    it, three separate files had independently copied the tab list and two of
    them had gone stale. Since the demo's tab bar became a sidebar of
    discovered pages (2026-10-07) the name is no longer a literal: it is a
    module `__getattr__` returning `advtext.ui.app.page_names()`, the scan of
    `advtext/ui/pages/`, so "tab" throughout this file means a page.
    """
    from advtext.ui.app import TAB_NAMES

    return tuple(str(name) for name in TAB_NAMES)


def check_tab_spec(spec: str | None) -> str:
    """
    Reject a tab request the app would silently ignore; return it normalised.

    `None` and the empty string mean "whatever opens by default" and are
    allowed through as `default`, because that is a thing somebody may
    legitimately want to photograph.

    The grammar and the name are both checked by
    `advtext.ui.app.parse_tab_request`, which T18-colmargin taught to refuse an
    unknown name rather than ignore it. This calls it rather than
    re-implementing it, and turns its `ValueError` into a `SystemExit` so the
    message reaches the operator before the app is launched -- `shoot` costs
    2.3 s and a window, and neither is worth spending on a name that cannot
    work. Kept even though `parse_tab_request` now validates: this is the point
    where the tool promises the stamp tells the truth about what was
    photographed, and that promise should not silently become someone else's.
    """
    from advtext.ui.app import parse_tab_request

    if not spec:
        return "default"
    try:
        parse_tab_request(spec)
    except ValueError as error:
        raise SystemExit(
            f"{error}\nT15 measured that `--tab colums` is byte-identical to "
            "`--tab document`, exit 0, with no warning. Refused here before the app opens."
        ) from error
    return spec


def shoot(
    spec: str | None,
    out: Path,
    *,
    width: int = 1400,
    height: int = 900,
    frames: int = 30,
    python: str | None = None,
    root: Path = ROOT,
) -> dict[str, str]:
    """
    Run `scripts/shot.py` for one tab/state and write a stamped PNG.

    One app lifetime per photograph, as a subprocess, for the reason the
    `Makefile` gives at the `shot` target: `final_app_window_screenshot` returns
    the last frame of an app that has *exited*, so two shots cannot share a
    process. Running the real script rather than re-implementing it also means
    this harness photographs the same app `make shot` does; a second launcher
    that merely resembled the first is exactly the mistake `scripts/shot.py`'s
    own docstring warns about.

    Returns the stamp that was written.
    """
    spec = check_tab_spec(spec)
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        python or sys.executable,
        str(root / "scripts" / "shot.py"),
        "--width",
        str(width),
        "--height",
        str(height),
        "--frames",
        str(frames),
        "--out",
        str(out),
    ]
    if spec != "default":
        command += ["--tab", spec]
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(root))
    if result.returncode != 0:
        raise SystemExit(
            f"shot.py failed for {spec!r} ({result.returncode}):\n{result.stderr.strip()}"
        )

    data = out.read_bytes()
    captured = _png_size(data)
    stamp = {
        _STAMP_KEY.decode(): json.dumps(
            {
                "build": build_id(root),
                "spec": spec,
                "requested": [width, height],
                "captured": list(captured),
                "taken": datetime.now(UTC).isoformat(timespec="seconds"),
                "shot_stderr": result.stderr.strip(),
            },
            sort_keys=True,
        )
    }
    out.write_bytes(stamp_png_bytes(data, stamp))
    return stamp


def _png_size(data: bytes) -> tuple[int, int]:
    for tag, payload in _iter_chunks(data):
        if tag == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
            return int(width), int(height)
    raise ValueError("no IHDR")  # pragma: no cover - not reachable for a real PNG


def read_stamp(path: Path, text: dict[str, str]) -> dict[str, Any]:
    """
    Pull the stamp out of a PNG's text chunks, or refuse.
    """
    raw = text.get(_STAMP_KEY.decode())
    if raw is None:
        raise NotStamped(
            f"{path} carries no build stamp, so there is no way to know what produced it.\n"
            "Re-shoot it with `scripts/visual_diff.py shoot` (or `pair`, which shoots both "
            "sides in one invocation and cannot be cross-build)."
        )
    loaded: dict[str, Any] = json.loads(raw)
    return loaded


# ----------------------------------------------------------------------
# Geometry and ink


@dataclass(frozen=True)
class Rect:
    """A half-open pixel rectangle: `x <= column < x + w`, `y <= row < y + h`."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def slice(self, image: NDArray[Any]) -> NDArray[Any]:
        return image[self.y : self.bottom, self.x : self.right]

    def shifted(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def __str__(self) -> str:
        return f"({self.x},{self.y}) {self.w}x{self.h}"


def grey_of(rgb: Rgb) -> Grey:
    """
    Channel mean, as float.

    Not a luminance weighting. The text here is drawn in a near-neutral grey on
    near-white paper, so the three channels move together, and an unweighted
    mean keeps the number the same one `docs/subpixel.md` quotes.
    """
    return np.asarray(rgb, dtype=np.float64).mean(axis=2)


def _runs(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Half-open `[start, stop)` spans of consecutive `True`."""
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2], strict=True)]


def _close(mask: NDArray[np.bool_], gap: int) -> NDArray[np.bool_]:
    """
    Fill interior `False` runs of `gap` pixels or fewer.

    Needed because the Columns tab draws a **one-pixel vertical rule** down the
    gutter at two columns, and a single dark column splits the sheet's
    near-white span in half. Measured on `artifacts/demo-columns-2.png`: without
    this, the sheet is found as x 16..544 instead of x 16..1072, and every
    region below it is then resolved inside the left half of the page.
    """
    out = mask.copy()
    for a, b in _runs(~mask):
        if a > 0 and b < len(mask) and b - a <= gap:
            out[a:b] = True
    return out


def _longest(mask: NDArray[np.bool_]) -> tuple[int, int] | None:
    spans = _runs(mask)
    return max(spans, key=lambda s: s[1] - s[0]) if spans else None


@dataclass(frozen=True)
class InkProfile:
    """
    How the ink in a region is distributed between solid, midtone and paper.

    The definition is **taken from `docs/subpixel.md`** rather than invented
    here, so the numbers are comparable with the ones already in that file:
    normalise coverage against the 95th-percentile paper value of the region,
    call coverage above 0.9 solid and coverage in 0.15..0.85 midtone, and take
    both as shares of the inked pixels (coverage above 0.15).

    `midtone_share` is the statistic the user's calibration table is written in.
    See `midtone_flags` for what may and may not be concluded from it -- the
    short version is that it detects a *change in antialiasing* and says nothing
    whatever about whether the change is welcome.
    """

    inked: int
    total: int
    solid_share: float
    midtone_share: float
    paper_level: float

    def __str__(self) -> str:
        return (
            f"{self.inked} inked px of {self.total}, "
            f"solid {self.solid_share * 100:.1f}%, midtone {self.midtone_share * 100:.1f}%"
        )


def coverage(region: Grey) -> Grey:
    """
    Ink coverage in 0..1, normalised against the region's own paper.

    Paper is the 95th percentile of the greys present, not 255, because the
    sheet is not pure white and a window at another brightness would otherwise
    read as inkier. That is `docs/subpixel.md`'s convention.
    """
    paper = float(np.percentile(region, 95)) if region.size else 255.0
    return (paper - region) / max(paper, 1.0)


def ink_profile(region: Grey) -> InkProfile:
    if region.size == 0:
        return InkProfile(0, 0, 0.0, 0.0, 255.0)
    cov = coverage(region)
    inked = int((cov > 0.15).sum())
    if inked == 0:
        return InkProfile(0, int(region.size), 0.0, 0.0, float(np.percentile(region, 95)))
    solid = int((cov > 0.9).sum())
    mid = int(((cov > 0.15) & (cov <= 0.85)).sum())
    return InkProfile(
        inked=inked,
        total=int(region.size),
        solid_share=solid / inked,
        midtone_share=mid / inked,
        paper_level=float(np.percentile(region, 95)),
    )


CALIBRATION = (
    (0.112, 'the user called this "aliased", "90\'s X11 text"'),
    (0.262, 'the user called this "awful" -- glyph instances visibly differing'),
    (0.412, "the shipped baseline at the time, called acceptable"),
    (0.472, 'the user called this "soft", but subjectively preferred it'),
)
"""
Midtone shares the user has labelled, for 16 px body text.

**These are landmarks, not a scale, and this module never interpolates between
them.** They were measured on builds that are not this one, by a method whose
exact crop is not recorded, so a number from `ink_profile` that lands near one
of them is a coincidence until somebody re-measures both sides of the same
build. They are here because the *direction* of a move is worth flagging: the
lead read a collapse from 41.2% to 11.2% as an improvement and shipped the
opinion. See `midtone_flags`.
"""


def midtone_flags(before: InkProfile, after: InkProfile, *, threshold: float = 0.05) -> list[str]:
    """
    Warn about a large move in the midtone share, in **either** direction.

    Returns warning lines, never a judgement, and the wording is chosen so that
    no line of it can be quoted as approval. A fall means antialiasing has been
    destroyed -- edges are snapping to hard black and white. A rise means the
    render has softened -- more of each stem is being spread across two pixels.
    The user has rejected output at both extremes, and has also preferred a
    softer render to the baseline, so neither direction is safe to call good.

    `threshold` is five percentage points, which is smaller than every labelled
    step in `CALIBRATION` and larger than the drift seen between two shots of
    the same build (measured: identical builds give an identical share, because
    the render is deterministic).
    """
    move = after.midtone_share - before.midtone_share
    if abs(move) < threshold:
        return []
    direction = (
        "FELL -- antialiasing has been reduced; edges are harder"
        if move < 0
        else "ROSE -- the render has softened; more of each stem is spread across pixels"
    )
    lines = [
        f"midtone share {direction}: "
        f"{before.midtone_share * 100:.1f}% -> {after.midtone_share * 100:.1f}% "
        f"({move * 100:+.1f} points)",
        "  This flags a CHANGE IN ANTIALIASING. It does not say which side is better, and "
        "no threshold here means 'good'.",
        "  The user has rejected output at both extremes. Labelled points, for context only:",
    ]
    lines += [f"    {share * 100:5.1f}%  {label}" for share, label in CALIBRATION]
    lines.append(
        "  Those were measured on other builds by an unrecorded method. Do not read this "
        "run's number off that table -- look at the crop."
    )
    return lines


# ----------------------------------------------------------------------
# Finding things by content


def find_sheet(grey: Grey, *, paper_level: float = 235.0, gap_close: int = 8) -> Rect:
    """
    The white page rectangle, found as the largest band of near-white.

    Columns first, then rows within those columns, because the window's
    background is dark and a row crossing a 700 px sheet in an 1100 px window
    is less than 50% white before any text is drawn -- a whole-row threshold
    measured against the image width finds nothing. Small interior gaps are
    closed first; see `_close` for the one-pixel gutter rule that made this
    necessary.

    Raises `RegionNotFound` when no plausible sheet is present, which is the
    honest answer on the Blocks tab: it draws a debug overlay on the window
    background and has no sheet at all. A tool that returned "the whole window"
    there would send every downstream measurement into the chrome.
    """
    height, width = grey.shape
    paper = grey > paper_level
    columns = _longest(_close(paper.sum(axis=0) > 0.5 * height, gap_close))
    if columns is None:
        raise RegionNotFound(
            "no sheet: no column of this image is more than half near-white "
            f"(brightest column is {int(paper.sum(axis=0).max(initial=0))} of {height} px). "
            "The Blocks tab genuinely has no sheet."
        )
    x0, x1 = columns
    rows = _longest(_close(paper[:, x0:x1].sum(axis=1) > 0.3 * (x1 - x0), gap_close))
    if rows is None:
        raise RegionNotFound(f"no sheet: columns {x0}..{x1} are near-white but no rows are")
    y0, y1 = rows
    sheet = Rect(x0, y0, x1 - x0, y1 - y0)
    if sheet.w < 100 or sheet.h < 100:
        raise RegionNotFound(f"no sheet: the largest near-white block is only {sheet}")
    return sheet


def find_columns(
    grey: Grey,
    sheet: Rect,
    *,
    min_gutter: int = 15,
    min_column: int = 40,
    rule_width: int = 3,
) -> list[Rect]:
    """
    The text columns on a sheet, as vertical bands of ink separated by gutters.

    Two measured details. A vertical **rule** is drawn in the gutter at two
    columns and is one pixel wide with ink down its whole height, so ink runs
    no wider than `rule_width` are discarded before the bands are merged --
    otherwise the rule joins the two columns into one and every row inside it
    spans both. And the gutter really is about 21 px on
    `artifacts/demo-columns-2.png` and `-3.png`, against inter-word gaps of
    4..12 px in the same render, so `min_gutter` of 15 separates them; the
    *union* over a whole column of a word gap is filled in by the other rows,
    which is what makes the separation clean at all.
    """
    body = sheet.slice(grey)
    ink = coverage(body) > 0.15
    spans = [s for s in _runs(ink.sum(axis=0) > 0) if s[1] - s[0] > rule_width]
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] < min_gutter:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    bands = [Rect(sheet.x + a, sheet.y, b - a, sheet.h) for a, b in merged if b - a >= min_column]
    if not bands:
        raise RegionNotFound(f"no text columns found on the sheet at {sheet}")
    return bands


def find_text_rows(grey: Grey, band: Rect) -> list[Rect]:
    """
    Rows of ink in a column band, top to bottom.

    A "row" is a maximal run of image rows containing any ink, so ascenders and
    descenders that touch across a line merge into one -- at 16 px on 20 px
    leading they do not, measured: the Document tab gives 26 rows, which is the
    number of set lines on it.
    """
    body = band.slice(grey)
    ink = coverage(body) > 0.15
    rows = [Rect(band.x, band.y + a, band.w, b - a) for a, b in _runs(ink.sum(axis=1) > 0)]
    if not rows:
        raise RegionNotFound(f"no rows of ink in the band at {band}")
    return rows


def find_ink_runs(grey: Grey, rect: Rect) -> list[Rect]:
    """
    Maximal runs of ink-bearing columns inside `rect` -- glyph clusters.

    **These are clusters, not glyphs, and the difference is not pedantic.** Two
    letters whose ink touches are one run: the lead measured a 31 px run in the
    heading "What the difference looks like" where a letter is 9..11 px, because
    `iffe` in "difference" had fused. Anything reported per-run is therefore
    per-cluster, and a report that says "18 runs" where the text has 20 letters
    is telling you something real about the render rather than about the tool.
    """
    body = rect.slice(grey)
    ink = coverage(body) > 0.15
    return [Rect(rect.x + a, rect.y, b - a, rect.h) for a, b in _runs(ink.sum(axis=0) > 0)]


@dataclass(frozen=True)
class WordSpan:
    """One matched word: where its ink is, and how wide it was expected to be."""

    text: str
    rect: Rect
    observed: float
    expected: float


@dataclass(frozen=True)
class LineMatch:
    """A text row that matched a phrase, with the per-word evidence."""

    rect: Rect
    column: int
    row: int
    words: tuple[WordSpan, ...]
    error: float

    @property
    def span(self) -> Rect:
        first, last = self.words[0].rect, self.words[-1].rect
        return Rect(first.x, self.rect.y, last.right - first.x, self.rect.h)


def expected_widths(words: list[str], face_name: str = "prose", size: float = 16.0) -> list[float]:
    """
    The ink width each word should have, from the project's own font metrics.

    Advances and kerns come from `advtext.fontlib`, which is where every other
    number in this project comes from, so this is not a second opinion about the
    font. The advance sum is then reduced by half the left side bearing of the
    first glyph and half the right of the last -- estimated as half the
    difference between advance and ink width, since `FaceMetrics.bbox` gives the
    ink width but not the two bearings separately. Ink is what a screenshot
    shows; the advance overshoots it by a pixel or two at 16 px, consistently,
    and correcting for it is what lets the tolerance be tight enough to be
    discriminating.
    """
    from advtext.fontlib import metrics
    from advtext.fontmetrics import Face

    face = Face(face_name)
    m = metrics(face, size)
    out: list[float] = []
    for word in words:
        total = 0.0
        for i, ch in enumerate(word):
            total += m.advance(ord(ch))
            if i + 1 < len(word):
                total += m.kern(ord(ch), ord(word[i + 1]))
        for ch in (word[0], word[-1]):
            total -= max(0.0, m.advance(ord(ch)) - m.bbox(ord(ch)).width) / 2.0
        out.append(total)
    return out


def match_line(
    grey: Grey,
    row: Rect,
    words: list[str],
    expected: list[float],
    *,
    tolerance: float = 2.5,
    relative: float = 0.06,
    min_space: int = 3,
) -> tuple[float, tuple[WordSpan, ...]] | None:
    """
    Try to read `words` off the start of one text row. `None` if it does not fit.

    The algorithm groups the row's ink runs greedily into words: take runs until
    the group is at least as wide as the word should be, then require the group
    to be within tolerance. That on its own is far too permissive -- measured on
    a fresh `columns:2` shot at 1100x800, "A column is not" grouped successfully
    on **three** of the 55 text rows, because a greedy accumulator can always
    find some set of letters adding up to the right width.

    What makes it discriminating is the space test: the gap before each word
    must be at least `min_space` px **and wider than the widest gap inside the
    word that follows it**. That is the definition of a word space in a
    typeset line, and with it the same phrase matches exactly one row.

    `min_space=0` switches the space test off entirely. It exists so the test
    suite can ablate it and show the false matches come back --
    `tests/test_visual_diff.py::test_the_word_space_test_is_what_makes_a_match_unique`
    does exactly that on a real screenshot.
    """
    runs = find_ink_runs(grey, row)
    if len(runs) < len(words):
        return None
    j = 0
    spans: list[WordSpan] = []
    error = 0.0
    for word, want in zip(words, expected, strict=True):
        if j >= len(runs):
            return None
        k = j
        while k + 1 < len(runs) and (runs[k].right - runs[j].x) < want - tolerance:
            k += 1
        observed = float(runs[k].right - runs[j].x)
        if abs(observed - want) > max(tolerance, relative * want):
            return None
        inside = max((runs[t + 1].x - runs[t].right for t in range(j, k)), default=0)
        if spans and min_space > 0:
            before = runs[j].x - spans[-1].rect.right
            if before < min_space or before <= inside:
                return None
        spans.append(
            WordSpan(word, Rect(runs[j].x, row.y, runs[k].right - runs[j].x, row.h), observed, want)
        )
        error += abs(observed - want)
        j = k + 1
    return error, tuple(spans)


def locate_lines(
    grey: Grey,
    text: str,
    *,
    face: str = "prose",
    size: float = 16.0,
    sheet: Rect | None = None,
    min_space: int = 3,
) -> list[LineMatch]:
    """
    Every text row that `text` fits, best fit first. Possibly none.

    `locate_line` is the one to call; this is exposed because "how many rows
    match" is the quantity an ablation of the matcher needs, and a test that can
    only see the winner cannot show that the losers were rejected for a reason.
    """
    words = text.split()
    if len(words) < 2:
        raise RegionNotFound(
            f"{text!r}: give at least two words. A single word is matched on its ink width "
            "alone, and at 16 px dozens of words on a page share a width to within 2 px."
        )
    sheet = sheet if sheet is not None else find_sheet(grey)
    expected = expected_widths(words, face, size)
    found: list[LineMatch] = []
    for c, band in enumerate(find_columns(grey, sheet), start=1):
        for r, row in enumerate(find_text_rows(grey, band), start=1):
            hit = match_line(grey, row, words, expected, min_space=min_space)
            if hit is not None:
                found.append(LineMatch(row, c, r, hit[1], hit[0]))
    found.sort(key=lambda m: m.error)
    return found


def locate_line(
    grey: Grey,
    text: str,
    *,
    face: str = "prose",
    size: float = 16.0,
    sheet: Rect | None = None,
    margin: float = 3.0,
    min_space: int = 3,
) -> LineMatch:
    """
    Find the one text row that begins with `text`, or refuse.

    Content addressing, so a region survives the page reflowing under it -- the
    thing hard-coded y coordinates do not. `text` is a *prefix*: give the first
    few words of a line and they will be found wherever that line ended up.

    Refuses in two distinguishable ways, and both matter.
    `RegionNotFound` means the phrase is not on the page: it is what you get
    when a crop would have landed on blank paper. `AmbiguousRegion` means two
    rows fit within `margin` px of each other and the tool will not pick one --
    the lead's crop was one line off once, and silently choosing the better of
    two near-ties is how that happens.

    **Known limits, because they are how this returns a wrong answer rather
    than no answer.** Only one face and size are modelled, so a phrase spanning
    a bold or italic run will not match -- "Bringhurst gives **sixty-six
    characters**" is not addressable this way, and the plain words around it
    are. Two or more words are required: one word matches on width alone and
    the space test has nothing to constrain.
    """
    found = locate_lines(grey, text, face=face, size=size, sheet=sheet, min_space=min_space)
    if not found:
        raise RegionNotFound(
            f"{text!r} is not on this page as a line prefix in {face} at {size} px. "
            "Nothing was cropped. Run `visual_diff.py regions` to see what is there, and "
            "remember that a phrase crossing a bold or italic run cannot match."
        )
    if len(found) > 1 and found[1].error - found[0].error < margin:
        where = ", ".join(f"column {m.column} row {m.row} (error {m.error:.1f} px)" for m in found)
        raise AmbiguousRegion(
            f"{text!r} matches more than one row and none is clearly best: {where}"
        )
    return found[0]


_WORDS_RE = re.compile(r"^words:(\d+)-(\d+)$")


def resolve_region(grey: Grey, spec: str, *, face: str = "prose", size: float = 16.0) -> Rect:
    """
    Turn a region name into a rectangle in this image, or raise.

    The grammar, `/`-separated:

        sheet
        column:N                      1-based, left to right
        column:N/row:M                1-based, top to bottom
        row:M                         short for column:1/row:M
        text:<two or more words>      the line beginning with them
        text:<...>/words:A-B          words A..B of that line, 1-based inclusive

    There is deliberately **no** way to name a raw pixel rectangle. Every
    incident this module exists for involved a coordinate that was right once
    and wrong later, and offering the escape hatch would make the safe path the
    longer one.
    """
    parts = spec.split("/")
    head = parts[0].strip()
    sheet = find_sheet(grey)

    if head == "sheet":
        rect = sheet
        rest = parts[1:]
    elif head.startswith("text:"):
        match = locate_line(grey, head[len("text:") :].strip(), face=face, size=size, sheet=sheet)
        rect = match.span
        rest = parts[1:]
        for piece in rest:
            slice_match = _WORDS_RE.match(piece.strip())
            if slice_match is None:
                raise RegionNotFound(f"{piece!r} is not understood after a text: region")
            a, b = int(slice_match.group(1)), int(slice_match.group(2))
            if not 1 <= a <= b <= len(match.words):
                raise RegionNotFound(
                    f"words:{a}-{b} is outside the {len(match.words)} words that matched"
                )
            first, last = match.words[a - 1].rect, match.words[b - 1].rect
            rect = Rect(first.x, rect.y, last.right - first.x, rect.h)
        return rect
    elif head.startswith("column:") or head.startswith("row:"):
        bands = find_columns(grey, sheet)
        if head.startswith("column:"):
            index = int(head.split(":", 1)[1])
            rest = parts[1:]
        else:
            index, rest = 1, parts
        if not 1 <= index <= len(bands):
            raise RegionNotFound(f"column:{index} but this page has {len(bands)} column(s)")
        rect = bands[index - 1]
    else:
        raise RegionNotFound(f"{spec!r}: unknown region. Try sheet, column:N, row:M or text:...")

    for piece in rest:
        piece = piece.strip()
        if not piece.startswith("row:"):
            raise RegionNotFound(f"{piece!r} is not understood after a column region")
        rows = find_text_rows(grey, rect)
        index = int(piece.split(":", 1)[1])
        if not 1 <= index <= len(rows):
            raise RegionNotFound(f"{piece} but that column has {len(rows)} row(s) of ink")
        rect = rows[index - 1]
    return rect


# ----------------------------------------------------------------------
# Comparing


@dataclass(frozen=True)
class RunDiff:
    """
    One glyph cluster's worth of change, with shape separated from position.

    `changed` and `max_delta` compare the two clusters **aligned to their own
    left edges**, so they are a statement about *shape* only. `dx` and
    `centroid_shift` carry the position. Keeping them apart is what lets the
    report distinguish "the same glyph drawn somewhere else" from "a different
    glyph", and that distinction is the whole subject of `docs/subpixel.md`:
    T19-wordsnap's claim is precisely that a word is drawn at one shape wherever
    it lands, and a differ that mixed the two could neither confirm nor refute
    it.
    """

    index: int
    rect: Rect
    changed: int
    max_delta: int
    mean_signed: float
    centroid_shift: float
    dx: int

    @property
    def moved(self) -> bool:
        return bool(self.changed) or self.dx != 0 or abs(self.centroid_shift) > 0.005


@dataclass
class RegionDiff:
    """
    What changed inside one named region, and nothing about whether it is better.
    """

    name: str
    rect_a: Rect
    rect_b: Rect
    compared: Rect
    pixels: int
    changed: int
    max_delta: int
    mean_abs: float
    darker: int
    lighter: int
    profile_a: InkProfile
    profile_b: InkProfile
    runs_a: int
    runs_b: int
    runs: list[RunDiff] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return self.changed == 0


def diff_region(
    grey_a: Grey,
    grey_b: Grey,
    rect_a: Rect,
    rect_b: Rect,
    *,
    name: str = "region",
    level: int = 1,
) -> RegionDiff:
    """
    Compare two regions pixel for pixel, then cluster by cluster.

    `level` is the grey-level difference at which a pixel counts as changed.
    One, not zero, only because a zero would count nothing differently -- the
    default is exact. **A run of this on two identical renders reports zero
    changed pixels, zero changed runs and no warnings**, which is the property
    `tests/test_visual_diff.py` pins first, because a differ that always finds
    differences is the single most obvious way this tool could be useless while
    looking busy.

    When the two named regions come out different sizes -- which happens when a
    change reflows the line the region was located by -- the overlap is
    compared, both rectangles are reported, and a warning says so. Silently
    padding would invent pixels; silently refusing would make the tool useless
    for exactly the changes it is for.
    """
    warnings: list[str] = []
    w, h = min(rect_a.w, rect_b.w), min(rect_a.h, rect_b.h)
    if (rect_a.w, rect_a.h) != (rect_b.w, rect_b.h):
        warnings.append(
            f"the region resolved to different sizes: A {rect_a}, B {rect_b}. "
            f"Only the top-left {w}x{h} overlap is compared, and a size change is itself "
            "a result -- the line reflowed."
        )
    crop_a = Rect(rect_a.x, rect_a.y, w, h)
    crop_b = Rect(rect_b.x, rect_b.y, w, h)
    a = crop_a.slice(grey_a)
    b = crop_b.slice(grey_b)
    delta = b - a
    changed_mask = np.abs(delta) >= level

    profile_a, profile_b = ink_profile(a), ink_profile(b)
    runs_a = find_ink_runs(grey_a, crop_a)
    runs_b = find_ink_runs(grey_b, crop_b)
    if len(runs_a) != len(runs_b):
        warnings.append(
            f"ink runs: {len(runs_a)} in A, {len(runs_b)} in B. Runs are glyph *clusters*, "
            "so a change in the count means letters fused or came apart -- the per-run table "
            "below pairs them in order and that pairing is no longer reliable."
        )

    runs: list[RunDiff] = []
    for i, (ra, rb) in enumerate(zip(runs_a, runs_b, strict=False), start=1):
        width = min(ra.w, rb.w)
        sub_a = Rect(ra.x, crop_a.y, width, h).slice(grey_a)
        sub_b = Rect(rb.x, crop_b.y, width, h).slice(grey_b)
        d = sub_b - sub_a
        # Displacement is measured inside the region, not in the image: the two
        # regions may sit at different absolute x (a different window width puts
        # the same sheet somewhere else) and that offset is not a glyph moving.
        dx = (rb.x - crop_b.x) - (ra.x - crop_a.x)
        runs.append(
            RunDiff(
                index=i,
                rect=Rect(ra.x - crop_a.x, 0, ra.w, ra.h),
                changed=int((np.abs(d) >= level).sum()),
                max_delta=int(np.abs(d).max()) if d.size else 0,
                mean_signed=float(d.mean()) if d.size else 0.0,
                centroid_shift=_centroid(sub_b) - _centroid(sub_a) + float(dx),
                dx=dx,
            )
        )

    return RegionDiff(
        name=name,
        rect_a=rect_a,
        rect_b=rect_b,
        compared=Rect(0, 0, w, h),
        pixels=int(a.size),
        changed=int(changed_mask.sum()),
        max_delta=int(np.abs(delta).max()) if delta.size else 0,
        mean_abs=float(np.abs(delta).mean()) if delta.size else 0.0,
        darker=int((delta <= -level).sum()),
        lighter=int((delta >= level).sum()),
        profile_a=profile_a,
        profile_b=profile_b,
        runs_a=len(runs_a),
        runs_b=len(runs_b),
        runs=runs,
        warnings=warnings,
    )


def _centroid(region: Grey) -> float:
    """
    Horizontal centre of mass of the ink, in pixels from the region's left edge.

    Sub-pixel by construction, which is the point: a glyph that moved by a third
    of a pixel changes no ink run's integer bounds and does change this. Returns
    0.0 for a region with no ink, which `diff_region` only ever compares against
    another such region.
    """
    cov = np.clip(coverage(region), 0.0, None)
    weight = cov.sum(axis=0)
    total = float(weight.sum())
    if total <= 0.0:
        return 0.0
    return float((weight * np.arange(weight.size)).sum() / total)


def letter_gaps(grey: Grey, rect: Rect) -> list[int]:
    """
    Widths of the blank runs between ink clusters, left to right.

    This is the measurement the user used to catch the letter-fit defect --
    "people" gave 1, 2, 2 / 2, 1, 1, 2 px -- so it is worth having. It is also
    the measurement the lead published across two renders with different
    antialiasing, which is invalid; `gaps_comparable` is the guard and
    `compare --gaps` will not print a pair of these without consulting it.
    """
    runs = find_ink_runs(grey, rect)
    return [runs[i + 1].x - runs[i].right for i in range(len(runs) - 1)]


def gaps_comparable(a: InkProfile, b: InkProfile, *, tolerance: float = 0.05) -> str | None:
    """
    Refuse a gap comparison between renders whose ink distributions differ.

    Returns the reason, or `None` when the comparison is sound.

    **The mechanism, which is not obvious and is why this exists.** A gap is
    measured between ink thresholded at a fixed coverage. A softer render puts
    more coverage into the pixels at the edge of each stem, so more pixels cross
    the threshold, so every letter reads as wider and every gap between letters
    reads as narrower -- with no letter having moved at all. Comparing gaps
    across an antialiasing change therefore measures the antialiasing and
    reports it as letter fit. The lead published such a comparison before
    noticing.
    """
    for label, x, y in (
        ("solid", a.solid_share, b.solid_share),
        ("midtone", a.midtone_share, b.midtone_share),
    ):
        if abs(x - y) > tolerance:
            return (
                f"gap measurements are NOT comparable here: the {label} share moved "
                f"{x * 100:.1f}% -> {y * 100:.1f}%. A softer render reads as wider letters and "
                "narrower gaps with nothing having moved, so a gap table across this pair "
                "would be measuring antialiasing. Compare gaps only within one render, or "
                "fix the antialiasing change first."
            )
    return None


# ----------------------------------------------------------------------
# Reporting and crops


def format_diff(diff: RegionDiff, *, top: int = 12) -> str:
    lines = [
        f"region {diff.name!r}",
        f"  A at {diff.rect_a}   B at {diff.rect_b}   compared {diff.compared.w}x{diff.compared.h}",
    ]
    for warning in diff.warnings:
        lines.append(f"  WARNING: {warning}")
    if diff.identical:
        lines.append("  IDENTICAL: 0 pixels differ by 1 level or more.")
    else:
        lines.append(
            f"  {diff.changed} of {diff.pixels} px differ "
            f"({100 * diff.changed / max(diff.pixels, 1):.2f}%); "
            f"max {diff.max_delta} levels, mean |delta| {diff.mean_abs:.2f}; "
            f"{diff.darker} px darker in B, {diff.lighter} lighter"
        )
    lines.append(f"  ink A: {diff.profile_a}")
    lines.append(f"  ink B: {diff.profile_b}")
    for warning in midtone_flags(diff.profile_a, diff.profile_b):
        lines.append(f"  {warning}")
    if diff.runs:
        moved = [r for r in diff.runs if r.moved]
        reshaped = sum(1 for r in diff.runs if r.changed)
        lines.append(
            f"  glyph clusters: {diff.runs_a} in A, {diff.runs_b} in B; "
            f"{reshaped} differ in shape, {len(moved) - reshaped} are the same shape at a "
            "different place. Clusters are compared aligned to their own left edges, so "
            "'shape' and 'position' are separate columns below:"
        )
        for run in sorted(moved, key=lambda r: (-r.changed, -abs(r.dx)))[:top]:
            lines.append(
                f"    #{run.index:<3} x={run.rect.x:<4} w={run.rect.w:<3} "
                f"{run.changed:>5} px changed, max {run.max_delta:>3} levels, "
                f"mean {run.mean_signed:+6.2f}, dx {run.dx:+3d} px, "
                f"ink centre {run.centroid_shift:+.3f} px"
            )
        if not moved:
            lines.append("    (none)")
    lines.append(
        "  This is a statement about CHANGE. It is not a statement about quality; look at "
        "the crops."
    )
    return "\n".join(lines)


def upscale(rgb: Rgb, factor: int) -> Rgb:
    """Nearest-neighbour magnification, so no new grey level is invented."""
    return np.repeat(np.repeat(rgb, factor, axis=0), factor, axis=1)


def difference_image(a: Rgb, b: Rgb, *, gain: int = 8) -> Rgb:
    """
    `|B - A|` amplified and inverted, so an unchanged pixel is white.

    Amplified because the differences that matter here are a few grey levels on
    a glyph edge and would be invisible at unit gain; inverted because a mostly
    white picture with dark marks where the change is reads the way a page does.
    `gain` is on the label of every image this writes.
    """
    delta = np.abs(a.astype(np.int32) - b.astype(np.int32)) * gain
    return (255 - np.clip(delta, 0, 255)).astype(np.uint8)


# ----------------------------------------------------------------------
# CLI


def _load(path: Path, *, require_stamp: bool) -> tuple[Rgb, Grey, dict[str, Any]]:
    """
    Read a PNG and its stamp. `require_stamp` decides whether a missing one raises.

    The stamp is read either way. An earlier version read it only when it was
    required, so `regions` printed "(none)" for a properly stamped file -- a
    tool whose whole argument is that a picture must say which build it came
    from, reporting that it did not know. Caught by running it, not by a test;
    `test_regions_prints_the_stamp_of_a_stamped_file` is the test that was
    missing.
    """
    rgb, text = read_png(path)
    stamp: dict[str, Any] = {}
    try:
        stamp = read_stamp(path, text)
    except NotStamped:
        if require_stamp:
            raise
    return rgb, grey_of(rgb), stamp


def _cmd_shoot(args: argparse.Namespace) -> int:
    stamp = shoot(args.spec, args.out, width=args.width, height=args.height, frames=args.frames)
    print(f"wrote {args.out}")
    print("  " + stamp[_STAMP_KEY.decode()])
    return 0


def _cmd_regions(args: argparse.Namespace) -> int:
    rgb, grey, stamp = _load(args.png, require_stamp=False)
    print(f"{args.png}  {rgb.shape[1]}x{rgb.shape[0]}")
    print(f"  stamp: {stamp or '(none -- compare will refuse this file)'}")
    sheet = find_sheet(grey)
    print(f"  sheet    {sheet}")
    for c, band in enumerate(find_columns(grey, sheet), start=1):
        rows = find_text_rows(grey, band)
        print(f"  column:{c} {band}   {len(rows)} rows of ink")
        for r, row in enumerate(rows, start=1):
            runs = find_ink_runs(grey, row)
            print(f"    row:{r:<3} {row}  {len(runs)} ink runs  {ink_profile(row.slice(grey))}")
    return 0


def _cmd_crop(args: argparse.Namespace) -> int:
    rgb, grey, _ = _load(args.png, require_stamp=False)
    rect = resolve_region(grey, args.region, face=args.face, size=args.size)
    pad = args.pad
    padded = Rect(
        max(0, rect.x - pad),
        max(0, rect.y - pad),
        min(rgb.shape[1], rect.right + pad) - max(0, rect.x - pad),
        min(rgb.shape[0], rect.bottom + pad) - max(0, rect.y - pad),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(encode_png(upscale(padded.slice(rgb), args.zoom)))
    print(f"wrote {args.out}: {args.region!r} at {rect}, padded {pad} px, {args.zoom}x")
    return 0


def _compare(
    a_path: Path, b_path: Path, args: argparse.Namespace, *, require_stamp: bool = True
) -> int:
    rgb_a, grey_a, stamp_a = _load(a_path, require_stamp=require_stamp)
    rgb_b, grey_b, stamp_b = _load(b_path, require_stamp=require_stamp)
    print(f"A {a_path}  {stamp_a.get('spec', '?')}  build {stamp_a.get('build', '?')}")
    print(f"B {b_path}  {stamp_b.get('spec', '?')}  build {stamp_b.get('build', '?')}")
    if stamp_a.get("build") != stamp_b.get("build"):
        if not args.allow_cross_build:
            print(
                "\nREFUSED: these two PNGs came from different builds of the tree.\n"
                "  Shoot both from one tree with `pair`, which cannot be cross-build, or pass\n"
                "  --allow-cross-build if a before/after across a source change is what you\n"
                "  mean. T7-look reviewed artifacts from mixed builds and could not tell.",
                file=sys.stderr,
            )
            return 2
        print("\n*** CROSS-BUILD COMPARISON: the two sides are not the same tree. ***")

    for name in args.region:
        try:
            rect_a = resolve_region(grey_a, name, face=args.face, size=args.size)
            rect_b = resolve_region(grey_b, name, face=args.face, size=args.size)
        except RegionNotFound as error:
            print(f"\nregion {name!r}: NOT FOUND -- {error}", file=sys.stderr)
            return 3
        diff = diff_region(grey_a, grey_b, rect_a, rect_b, name=name, level=args.level)
        print()
        print(format_diff(diff))
        if args.gaps:
            refusal = gaps_comparable(diff.profile_a, diff.profile_b)
            if refusal:
                print(f"  {refusal}")
            else:
                print(f"  gaps A: {letter_gaps(grey_a, rect_a)}")
                print(f"  gaps B: {letter_gaps(grey_b, rect_b)}")
        if args.crops:
            args.crops.mkdir(parents=True, exist_ok=True)
            tag = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]
            crop_a = upscale(rect_a.slice(rgb_a), args.zoom)
            crop_b = upscale(rect_b.slice(rgb_b), args.zoom)
            (args.crops / f"{tag}-a.png").write_bytes(encode_png(crop_a))
            (args.crops / f"{tag}-b.png").write_bytes(encode_png(crop_b))
            w = min(crop_a.shape[1], crop_b.shape[1])
            h = min(crop_a.shape[0], crop_b.shape[0])
            (args.crops / f"{tag}-diff.png").write_bytes(
                encode_png(difference_image(crop_a[:h, :w], crop_b[:h, :w]))
            )
            print(f"  crops in {args.crops}/{tag}-{{a,b,diff}}.png at {args.zoom}x (diff gain 8)")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    return _compare(args.a, args.b, args)


def _cmd_pair(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    a = args.out_dir / "pair-a.png"
    b = args.out_dir / "pair-b.png"
    shoot(args.spec_a, a, width=args.width, height=args.height, frames=args.frames)
    shoot(args.spec_b, b, width=args.width_b or args.width, height=args.height, frames=args.frames)
    args.allow_cross_build = False
    return _compare(a, b, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_region_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--face", default="prose", help="face for text: regions (default prose)")
        p.add_argument("--size", type=float, default=16.0, help="px size for text: regions")

    def add_compare_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--region", action="append", required=True, help="repeatable region name")
        p.add_argument("--level", type=int, default=1, help="grey levels that count as a change")
        p.add_argument("--gaps", action="store_true", help="also measure inter-cluster gaps")
        p.add_argument("--crops", type=Path, default=None, help="write magnified crops here")
        p.add_argument("--zoom", type=int, default=6)
        add_region_flags(p)

    p_shoot = sub.add_parser("shoot", help="render one tab/state to a stamped PNG")
    p_shoot.add_argument("--spec", default=None, help="tab request, e.g. columns:2,debug")
    p_shoot.add_argument("--out", type=Path, required=True)
    p_shoot.add_argument("--width", type=int, default=1400)
    p_shoot.add_argument("--height", type=int, default=900)
    p_shoot.add_argument("--frames", type=int, default=30)
    p_shoot.set_defaults(func=_cmd_shoot)

    p_regions = sub.add_parser("regions", help="print what the finder sees")
    p_regions.add_argument("png", type=Path)
    p_regions.set_defaults(func=_cmd_regions)

    p_crop = sub.add_parser("crop", help="write a magnified crop of a named region")
    p_crop.add_argument("png", type=Path)
    p_crop.add_argument("--region", required=True)
    p_crop.add_argument("--out", type=Path, required=True)
    p_crop.add_argument("--zoom", type=int, default=6)
    p_crop.add_argument("--pad", type=int, default=0)
    add_region_flags(p_crop)
    p_crop.set_defaults(func=_cmd_crop)

    p_compare = sub.add_parser("compare", help="diff two stamped PNGs")
    p_compare.add_argument("a", type=Path)
    p_compare.add_argument("b", type=Path)
    p_compare.add_argument("--allow-cross-build", action="store_true")
    add_compare_flags(p_compare)
    p_compare.set_defaults(func=_cmd_compare)

    p_pair = sub.add_parser("pair", help="shoot two states in one invocation, then diff")
    p_pair.add_argument("--spec-a", default=None)
    p_pair.add_argument("--spec-b", default=None)
    p_pair.add_argument("--width", type=int, default=1400)
    p_pair.add_argument("--width-b", type=int, default=None)
    p_pair.add_argument("--height", type=int, default=900)
    p_pair.add_argument("--frames", type=int, default=30)
    p_pair.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "visual-diff")
    add_compare_flags(p_pair)
    p_pair.set_defaults(func=_cmd_pair)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
    except (RegionNotFound, NotStamped) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 3
    return result


if __name__ == "__main__":
    raise SystemExit(main())

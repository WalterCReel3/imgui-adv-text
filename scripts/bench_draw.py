r"""
Time an ImGui frame, so the per-frame draw cost is a number anybody can re-run.

`scripts/bench_reflow.py` times a **reflow** -- composition, ship-out and the
selection index -- and says in its own docstring that timing the ImGui backend is
out of its scope. This script is the other half. It times
`advtext.backends.imgui_draw.draw`, which turned out to be the largest per-frame
cost in the project and the one nothing measured: a reflow happens when the
window changes width, and a draw happens on **every** frame whether anything
changed or not.

**It opens no window, and that is the fact the whole script rests on.** A window
needs a display; a frame does not. `imgui.create_context()` allocates plain
memory, `ImFontAtlas` bakes glyphs on the CPU through stb_truetype, and
`new_frame`/`render` build vertex buffers in RAM. Only compositing those buffers
onto a screen needs a GPU, and nothing here does that. `immapp.run` is not
reached from here, which keeps this script runnable on a machine with no
display. It was once claimed that `immapp.run` *hangs* here; that is no longer
true and `scripts/shot.py` drives it in about 2.3s. The reason this script
avoids it is portability, not breakage. See the CORRECTION at the top of
`docs/decisions.md`.

Run it with:

    python scripts/bench_draw.py --copies 1,2,4 --repeat 5

**Best of N, not the mean**, for the reason `scripts/bench_reflow.py` gives: the
noise floor is one-sided, so the minimum is the closest available estimate of the
real cost and the mean measures the machine's other tenants. That defends against
noise *within* a run and not against a machine that is loaded for all of it; see
the spread recorded under "What it found" before comparing two days' numbers.

## What the tables say

1. **Whole document versus viewport** -- `draw` over every command the document
   ships, against `draw` over `CommandIndex.visible(...)` for one 768px window.
   The full column grows with the file and the culled column does not, which is
   the claim `advtext.ui.CommandIndex` makes and this table is where it comes
   from.
2. **Culled draw by scroll offset** -- the same window at several positions down
   the document. A single offset could land in whitespace and flatter the result;
   the spread is what says the number is about the window and not about where the
   window happens to be.
3. **Where a frame's time goes** -- `draw` decomposed, to answer whether the cost
   is our per-glyph Python work or ImGui's per-call work. Read the
   `_anatomy` docstring before drawing a conclusion from it, because two of its
   rows are timing probes that do not draw correct geometry.

## What it found, and the answer is not the one that was expected

### Read the counts as fact and the milliseconds as an order of magnitude

The counts in the tables below are **deterministic**: they are a function of
`demo/sample.md` and the engine, they reproduce exactly run to run, and
`tests/test_bench_numbers.py` re-derives every one of them so that the next time
the sample changes this docstring goes red instead of quietly stale. It already
went stale once -- these tables read `4,226 commands / 49 runs / 3,443 glyphs`
for a whole batch after `demo/sample.md` grew, and nothing anywhere reported it.

**The milliseconds are not deterministic and should not be quoted as if they
were.** Best-of-N defends against the one-sided noise *inside* one run; it does
not defend against a machine that is busy for the whole run, because a sustained
background load moves the floor itself. Four runs of this script taken within
twenty minutes on this machine, over the identical 5,378 commands, gave a full
draw of **28.0, 30.3, 33.9 and 34.1 ms** -- a 22% spread with no code change.
Compare *ratios* between rows of one run, which is what the conclusions below
rest on; do not compare an absolute against a different day's absolute.

The tables are one run, `--copies 1,2,4 --repeat 7`:

    | copies | commands | full draw | visible | culled draw |
    |      1 |    5,378 |   30.32ms |   1,952 |     10.46ms |
    |      2 |   10,756 |   59.86ms |   1,952 |     11.00ms |
    |      4 |   21,512 |  114.52ms |   1,952 |     10.35ms |

**The per-frame cost is our Python, not ImGui's drawing.** The `bench-draw` task
asked whether the per-frame cost is Python call overhead or ImGui's per-call
work, on the grounds that if it is the former a batched path for agreeing runs
might be worth building. The anatomy table says it is overwhelmingly the former,
and it says the batched path is the wrong thing to build:

    | 1. `draw`, as shipped                            | 29.36ms |
    | 2. the real `draw`, into a draw list that discards| 28.47ms |
    | 3. per-glyph `add_text` alone, precomputed        |  1.38ms |
    | 4. batched `add_text` over 71 runs                |  0.03ms |
    | 5. a reconstruction of that loop                  | 20.49ms |
    | 6. ...minus `is_glyph_in_font` and `get_font_baked`| 18.78ms |
    | 7. ...minus our own arithmetic                    |  1.95ms |

ImGui's share is `1 - 2` = **0.9ms**, and row 3 agrees at 1.4ms measuring the
same thing from the other end. So **batching every glyph in the document into 71
`add_text` calls would save about 1ms of 29**, or 3%, and it would have to give
up the per-glyph positioning `docs/imgui-risks.md` item 3 exists to defend. That
share was 5% when these tables were first taken and it has only got smaller,
because the sample grew and the saving did not.

Where the rest goes, from the reconstruction: **16.8ms** (`6 - 7`) is our own
per-glyph arithmetic -- `parse_font_key` re-parsing the same key string,
`fontlib_metrics` re-resolving the same face, `baked_size_px` recomputing the
same ratio, two `px_from_sp` calls and two `ImVec2` constructions. **8.0ms**
(`2 - 5`) is Python dispatch `draw` performs and the reconstruction does not: the
per-command `match`, the `_glyph` call and the `at` closure. **2.0ms** (row 7) is
the bare loop and the `DrawStats` rebuild, which is one frozen dataclass per
glyph.

Every one of those is a value that is constant across the run of glyphs sharing a
`FontKey`, and there are 71 such runs in 4,362 glyphs. **Memoising the preamble
per key is worth an order of magnitude more than batching the draw, and it costs
no geometry at all.** That is a real optimisation and it is out of scope here;
saying which one is worth doing was in scope, and this is the answer.

## Two things that quietly ruin these numbers

- **Load faces through `fontlib.imgui_font_file`, not `fontlib.font_file`.** The
  math face's synthetic codepoints are absent from the unpatched file, so `draw`
  returns them in `DrawStats.missing` without issuing a call, and the timing is
  then of a shorter list than the command count suggests. Every table below
  prints `missing` so a reader can see it is zero.
- **The font atlas is process-global.** Faces are added once here, for the whole
  run. That is fine in a script; a *test* that adds faces beside
  `tests/test_imgui_draw.py` is asking for an ordering failure, which is why the
  culling test in `tests/test_document_view.py` passes `fonts=lambda face: None`.

Deliberately out of scope: timing composition and ship-out, which
`scripts/bench_reflow.py` owns; anything about how the result *looks*, which
needs a display; and implementing the batched draw path table 3 measures the
headroom for.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

if __package__ in (None, ""):  # pragma: no cover - import shim for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advtext import fontlib
from advtext.backends.imgui_draw import DEFAULT_PALETTE, DrawStats, baked_size_px, draw
from advtext.fontmetrics import Face
from advtext.markdown import build_document
from advtext.shipout import DrawCmd, Glyph, Point, ship
from advtext.style import Theme, char_measure, fontlib_metrics, parse_font_key
from advtext.ui import CommandIndex, Viewport, compose
from advtext.units import DEFAULT_PX_PER_INCH, px_from_sp, sp_from_pt

__all__ = [
    "DEFAULT_COPIES",
    "DEFAULT_OFFSETS",
    "DEFAULT_WIDTH_PT",
    "DEFAULT_WINDOW_PX",
    "DrawTiming",
    "main",
    "shipped_commands",
]

DEFAULT_WIDTH_PT = 420.0
"""
The measure `scripts/render_litmus.py` sets its artifacts at.

Shared with `scripts/bench_reflow.py`'s middle column on purpose, so a draw cost
and a reflow cost quoted together describe the same page.
"""

DEFAULT_WINDOW_PX = 768.0
"""
The visible height of the document pane, in device pixels.

768 is the height `tests/test_document_view.py` and `advtext.ui.CommandIndex`
both use, and it is the number the culling claim is stated against. Changing it
changes every culled figure below, which is the point of `--window`.
"""

DEFAULT_COPIES = "1,2,4"
"""
How many times the sample is concatenated, giving three document lengths.

Concatenation rather than three different documents: the point of the scaling
table is that the *only* thing changing is length, and a longer document with a
different word-length distribution would confound that.
"""

DEFAULT_OFFSETS = "0.0,0.25,0.5,0.75"
"""
Scroll positions, as a fraction of the document's own height.

Fractions rather than pixels so one set of offsets is meaningful at every
document length in the scaling table.
"""

ATLAS_SIZE_PX = 16.0
"""
The size each face is added to the atlas at.

Since Dear ImGui 1.92 a face bakes on demand at whatever size is pushed, so this
is only the face's default size and not the set of sizes that will be rasterised.
`draw` asks for a size per glyph through `baked_size_px`, and the document uses
five of them.
"""

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DrawTiming:
    """
    One `draw` call's cost and what it managed, in milliseconds.

    `missing` is carried beside the timing rather than checked and dropped,
    because a non-zero count means the timing is of a shorter list than `commands`
    claims -- a glyph the bound face cannot raster costs a coverage check and no
    `add_text` at all.
    """

    commands: int
    glyphs: int
    missing: int
    draw_ms: float

    @property
    def budget_fraction(self) -> float:
        """
        This draw as a fraction of a 16.67ms frame at 60fps.
        """
        return self.draw_ms / (1000.0 / 60.0)


@contextmanager
def _frame(imgui: Any) -> Iterator[Any]:
    """
    A live frame, yielding the viewport-wide background draw list.

    The background list rather than a window's, for the reason
    `tests/test_imgui_draw.py` gives: a window clips to its own rect and a clipped
    glyph appends no vertices, so a timing taken inside one would measure the
    clip rather than the draw. `render` runs in the teardown whatever happened,
    because an open frame leaks into the next one.
    """
    imgui.new_frame()
    try:
        yield imgui.get_background_draw_list()
    finally:
        imgui.render()


def _best_frame(imgui: Any, repeat: int, work: Callable[[Any], T]) -> tuple[float, T]:
    """
    Milliseconds for the fastest of `repeat` runs, each in its own frame.

    One frame per run, not one frame around the loop: a draw list accumulates
    vertices until `render`, so N draws into one frame would time a buffer that
    grows under the measurement.

    The untimed first call is load-bearing here in a way it is not in
    `scripts/bench_reflow.py`. It bakes every glyph the list names into the atlas
    at every size it names, and that rasterisation is a once-per-process cost
    that would otherwise land entirely on the first timed run.
    """
    best = float("inf")
    with _frame(imgui) as draw_list:
        result = work(draw_list)
    for _ in range(repeat):
        with _frame(imgui) as draw_list:
            start = time.perf_counter()
            result = work(draw_list)
            best = min(best, time.perf_counter() - start)
    return best * 1000.0, result


def shipped_commands(source: str, copies: int, width_pt: float) -> tuple[DrawCmd, ...]:
    """
    Compose and ship `copies` concatenations of `source` at a measure.

    Composition is not timed and is not in any table: `scripts/bench_reflow.py`
    owns that number, and quoting it twice in two scripts is how two numbers
    start disagreeing.
    """
    theme = Theme.build()
    measure = char_measure(fontlib_metrics)
    document = build_document("\n\n".join([source.strip()] * copies), theme, fontlib_metrics)
    box = compose(document, theme, sp_from_pt(width_pt), measure)
    return tuple(ship(box, Point(0, box.height), measure=measure))


def _faces(imgui: Any) -> Callable[[Face], Any]:
    """
    Every face loaded into the process-global atlas, as the `FaceFont` `draw` wants.

    `imgui_font_file` and not `font_file`: see the module docstring. A face that
    fails to load would be an outright error here rather than the degradation
    `advtext.ui.app.load_fonts` allows, because a benchmark that silently timed
    four faces instead of six would be worse than one that stopped.
    """
    atlas = imgui.get_io().fonts
    loaded = {
        face: atlas.add_font_from_file_ttf(str(fontlib.imgui_font_file(face)), ATLAS_SIZE_PX)
        for face in Face
    }
    return lambda face: loaded[face]


def _time_draw(
    imgui: Any,
    cmds: Sequence[DrawCmd],
    fonts: Callable[[Face], Any],
    repeat: int,
    px_per_inch: float,
) -> DrawTiming:
    """
    Time one `draw` over one command list, best of `repeat`.
    """
    origin = imgui.ImVec2(0.0, 0.0)

    def work(draw_list: Any) -> Any:
        return draw(
            draw_list,
            cmds,
            origin,
            fonts=fonts,
            palette=DEFAULT_PALETTE,
            px_per_inch=px_per_inch,
        )

    ms, stats = _best_frame(imgui, repeat, work)
    return DrawTiming(
        commands=len(cmds),
        glyphs=stats.glyphs,
        missing=stats.missing,
        draw_ms=ms,
    )


# --------------------------------------------------------------------------------
# Table 3: what a per-glyph draw is actually made of.
# --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Call:
    """
    One fully resolved `add_text` call: everything `_glyph` computes, precomputed.
    """

    font: Any
    size_px: float
    x: float
    y: float
    character: str


def _resolved_calls(
    imgui: Any, cmds: Sequence[DrawCmd], fonts: Callable[[Face], Any], px_per_inch: float
) -> list[_Call]:
    """
    Every `add_text` `draw` would issue, with its arguments worked out in advance.

    This is the same arithmetic `advtext.backends.imgui_draw._glyph` performs,
    repeated here rather than imported because the point is to move it *out* of
    the timed region. If `_glyph` changes, this goes stale and the anatomy table
    becomes wrong while the first two tables stay right -- which is why it is a
    private helper of one table and not a general facility.
    """
    calls: list[_Call] = []
    for cmd in cmds:
        if not isinstance(cmd, Glyph):
            continue
        spec = parse_font_key(cmd.font)
        font = fonts(spec.face)
        if not font.is_glyph_in_font(cmd.codepoint):
            continue
        ours = fontlib_metrics(cmd.font)
        size_px = baked_size_px(
            px_from_sp(spec.size, px_per_inch), ours.ascent, ours.descent, ours.em
        )
        ascent = font.get_font_baked(size_px).ascent
        calls.append(
            _Call(
                font=font,
                size_px=size_px,
                x=px_from_sp(cmd.x, px_per_inch),
                y=px_from_sp(cmd.y, px_per_inch) - ascent,
                character=chr(cmd.codepoint),
            )
        )
    return calls


class _Discarding:
    """
    A draw list that accepts everything `draw` issues and keeps none of it.

    The point of the anatomy table: `draw` can be timed *exactly*, over the real
    command list, with ImGui's rasterisation and vertex-buffer work subtracted and
    nothing else changed. Every other way of getting that number reconstructs
    `draw`'s loop and then measures the reconstruction.

    It is not free -- a Python method call is not nothing -- so the difference it
    yields slightly **understates** ImGui's share. At the measured scale that bias
    is a few tenths of a millisecond against a figure of about one, which is why
    the table carries an independent second estimate of the same quantity beside
    it rather than resting on this one.

    `draw` type-annotates its first parameter as `imgui.ImDrawList` and this is
    not one. That is deliberate and is confined to this script: `make typecheck`
    runs over `advtext` only, and widening the backend's signature to admit a
    duck-typed stand-in would weaken a real type for a benchmark's convenience.
    """

    def add_text(self, *_args: Any) -> None:
        return None

    def add_rect_filled(self, *_args: Any) -> None:
        return None

    def add_rect(self, *_args: Any) -> None:
        return None

    def add_line(self, *_args: Any) -> None:
        return None


def _runs(calls: Sequence[_Call]) -> list[tuple[_Call, str]]:
    """
    Consecutive calls sharing a face and a size, joined into one string each.

    **This is a timing probe and not a proposal.** Handing a whole run to
    `add_text` lets ImGui advance the pen with *its* advances, which
    `scripts/verify_advances.py` measured as disagreeing with ours by about 1px
    per 44 characters after the size correction -- and by 42px before it. A real
    batched path would have to restrict itself to runs whose advances agree, and
    that is a smaller set than this. The row exists to bound what such a path
    could be worth, and it draws the document slightly wrong on purpose.
    """
    grouped: list[tuple[_Call, str]] = []
    for call in calls:
        if grouped:
            head, text = grouped[-1]
            if head.font is call.font and head.size_px == call.size_px:
                grouped[-1] = (head, text + call.character)
                continue
        grouped.append((call, call.character))
    return grouped


def _anatomy(
    imgui: Any,
    cmds: Sequence[DrawCmd],
    fonts: Callable[[Face], Any],
    repeat: int,
    px_per_inch: float,
) -> list[tuple[str, int, float]]:
    r"""
    `draw`, peeled one layer at a time, to say where a frame's milliseconds are.

    The question this exists to answer is the one the `bench-draw` task asked: is
    the 21ms ImGui's per-call work, in which case batching runs of glyphs into one
    `add_text` is worth pursuing, or is it our own Python, in which case it is
    not.

    **Rows 1 to 4 settle that, and they are exact.** Row 2 is the *real* `draw`,
    over the *real* command list, handed a `_Discarding` draw list instead of
    ImGui's -- so `1 - 2` is everything ImGui does with a glyph once it has been
    asked for it, and no part of `draw` has been reconstructed to get the number.
    Row 3 measures the same quantity from the other end and must agree with
    `1 - 2`; two independent estimates of one number are worth more than one.
    Row 4 is the floor a batched path could aim at.

    **Rows 5 to 7 attribute what is left, and they are a reconstruction rather
    than a measurement of `draw` itself.** They are hand-written copies of
    `advtext.backends.imgui_draw._glyph`'s body with one layer dropped at each
    step, because there is no way to remove a statement from a function from the
    outside. Row 5 is the full reconstruction: **the gap between row 5 and row 2
    is the reconstruction's own error**, and it is printed rather than hidden,
    because it is the per-command `match`, the `_glyph` call and the `at` closure
    that row 5 does not have. Subtract rows 6 and 7 from row 5, not from row 2.

    That reconstruction goes stale silently if `_glyph` changes. It is the part of
    this script to distrust first after a backend edit; tables 1 and 2 call the
    real `draw` and are unaffected.
    """
    calls = _resolved_calls(imgui, cmds, fonts, px_per_inch)
    runs = _runs(calls)
    rows: list[tuple[str, int, float]] = []
    ink = DEFAULT_PALETTE.ink

    real = _time_draw(imgui, cmds, fonts, repeat, px_per_inch)
    rows.append(("1. `draw`, as shipped", real.glyphs, real.draw_ms))

    origin = imgui.ImVec2(0.0, 0.0)

    def discarded(_draw_list: Any) -> Any:
        return draw(
            _Discarding(),
            cmds,
            origin,
            fonts=fonts,
            palette=DEFAULT_PALETTE,
            px_per_inch=px_per_inch,
        )

    ms, _ = _best_frame(imgui, repeat, discarded)
    rows.append(("2. the real `draw`, into a draw list that discards", len(calls), ms))

    def per_glyph(draw_list: Any) -> int:
        for call in calls:
            draw_list.add_text(
                call.font, call.size_px, imgui.ImVec2(call.x, call.y), ink, call.character
            )
        return len(calls)

    ms, _ = _best_frame(imgui, repeat, per_glyph)
    rows.append(("3. per-glyph `add_text` alone, arguments precomputed", len(calls), ms))

    def batched(draw_list: Any) -> int:
        for head, text in runs:
            draw_list.add_text(head.font, head.size_px, imgui.ImVec2(head.x, head.y), ink, text)
        return len(runs)

    ms, _ = _best_frame(imgui, repeat, batched)
    rows.append((f"4. batched `add_text` over {len(runs)} runs (WRONG geometry)", len(calls), ms))

    def reconstruction(_draw_list: Any) -> int:
        stats = DrawStats()
        for cmd in cmds:
            if not isinstance(cmd, Glyph):
                continue
            spec = parse_font_key(cmd.font)
            font = fonts(spec.face)
            if not font.is_glyph_in_font(cmd.codepoint):
                stats = DrawStats(stats.glyphs, stats.missing + 1, stats.rules)
                continue
            ours = fontlib_metrics(cmd.font)
            size_px = baked_size_px(
                px_from_sp(spec.size, px_per_inch), ours.ascent, ours.descent, ours.em
            )
            baseline = imgui.ImVec2(px_from_sp(cmd.x, px_per_inch), px_from_sp(cmd.y, px_per_inch))
            ascent = font.get_font_baked(size_px).ascent
            imgui.ImVec2(baseline.x, baseline.y - ascent)
            chr(cmd.codepoint)
            stats = DrawStats(stats.glyphs + 1, stats.missing, stats.rules)
        return stats.glyphs

    ms, _ = _best_frame(imgui, repeat, reconstruction)
    rows.append(("5. a reconstruction of that loop, for 6 and 7 to subtract from", len(calls), ms))

    def without_imgui_metrics(_draw_list: Any) -> int:
        stats = DrawStats()
        for cmd in cmds:
            if not isinstance(cmd, Glyph):
                continue
            spec = parse_font_key(cmd.font)
            fonts(spec.face)
            ours = fontlib_metrics(cmd.font)
            baked_size_px(px_from_sp(spec.size, px_per_inch), ours.ascent, ours.descent, ours.em)
            baseline = imgui.ImVec2(px_from_sp(cmd.x, px_per_inch), px_from_sp(cmd.y, px_per_inch))
            imgui.ImVec2(baseline.x, baseline.y)
            chr(cmd.codepoint)
            stats = DrawStats(stats.glyphs + 1, stats.missing, stats.rules)
        return stats.glyphs

    ms, _ = _best_frame(imgui, repeat, without_imgui_metrics)
    rows.append(("6. ...minus `is_glyph_in_font` and `get_font_baked`", len(calls), ms))

    def loop_only(_draw_list: Any) -> int:
        stats = DrawStats()
        for cmd in cmds:
            if not isinstance(cmd, Glyph):
                continue
            stats = DrawStats(stats.glyphs + 1, stats.missing, stats.rules)
        return stats.glyphs

    ms, _ = _best_frame(imgui, repeat, loop_only)
    rows.append(("7. ...minus our own arithmetic: the loop and `DrawStats`", len(calls), ms))
    return rows


# --------------------------------------------------------------------------------


def _copies(count: int) -> str:
    """
    "1 copy" or "4 copies", so a table heading reads as English.
    """
    return "1 copy" if count == 1 else f"{count} copies"


def main(argv: list[str] | None = None) -> int:
    """
    Ship the sample at several lengths and time drawing all of it and part of it.
    """
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.strip().splitlines()[0])
    parser.add_argument(
        "--copies",
        default=DEFAULT_COPIES,
        help=f"comma-separated concatenation counts (default {DEFAULT_COPIES})",
    )
    parser.add_argument(
        "--offsets",
        default=DEFAULT_OFFSETS,
        help=f"scroll positions as fractions of document height (default {DEFAULT_OFFSETS})",
    )
    parser.add_argument("--repeat", type=int, default=5, help="frames per row; the best is kept")
    parser.add_argument("--width", type=float, default=DEFAULT_WIDTH_PT, help="measure, in points")
    parser.add_argument(
        "--window", type=float, default=DEFAULT_WINDOW_PX, help="viewport height, in pixels"
    )
    parser.add_argument("--px-per-inch", type=float, default=DEFAULT_PX_PER_INCH)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parent.parent / "demo" / "sample.md"
    )
    args = parser.parse_args(argv)

    copies = [int(part) for part in args.copies.split(",") if part.strip()]
    offsets = [float(part) for part in args.offsets.split(",") if part.strip()]
    if not copies or not offsets:
        parser.error("--copies and --offsets must each name at least one value")

    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, args.window)
    io.delta_time = 1.0 / 60.0
    # Without this the first add_text aborts on IM_ASSERT(atlas->TexIsBuilt).
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    fonts = _faces(imgui)

    source = args.source.read_text(encoding="utf-8")
    print(f"source:     {args.source}")
    print(f"measure:    {args.width:g}pt")
    print(f"window:     {args.window:g}px tall")
    print(f"repeat:     best of {args.repeat}")
    print("budget:     16.67ms per frame at 60fps")
    print("display:    none. A frame is built in RAM and composited nowhere.")
    print()

    indexes: dict[int, CommandIndex] = {}

    print("### Whole document versus one viewport\n")
    print(
        "`draw` over every command the document ships, against `draw` over the\n"
        "commands one window's worth of scroll intersects. The full column is a\n"
        "function of the file and the culled column is a function of the window.\n"
    )
    print("| copies | commands | full draw | % budget | visible | culled draw | % budget |")
    print("|---|---|---|---|---|---|---|")
    for count in copies:
        cmds = shipped_commands(source, count, args.width)
        index = CommandIndex.of(cmds)
        indexes[count] = index
        full = _time_draw(imgui, cmds, fonts, args.repeat, args.px_per_inch)
        visible = index.visible(Viewport.of_pixels(0.0, args.window, args.px_per_inch))
        culled = _time_draw(imgui, visible, fonts, args.repeat, args.px_per_inch)
        print(
            f"| {count} | {full.commands} | {full.draw_ms:.2f}ms "
            f"| {full.budget_fraction * 100:.0f}% | {culled.commands} "
            f"| {culled.draw_ms:.2f}ms | {culled.budget_fraction * 100:.0f}% |"
        )
        if full.missing or culled.missing:
            print(
                f"| | **{full.missing} / {culled.missing} glyphs missing -- "
                "faces are not loading through `imgui_font_file`** | | | | | |"
            )
    print()

    tallest = max(copies)
    index = indexes[tallest]
    height_px = px_from_sp(max(index.bottoms), args.px_per_inch)
    print(f"### Culled draw by scroll offset, {_copies(tallest)} ({height_px:.0f}px tall)\n")
    print(
        "One offset could land in whitespace and flatter the result. The spread is\n"
        "what says the cost is about the window rather than about where it sits.\n"
    )
    print("| scroll | top | visible | draw | % budget |")
    print("|---|---|---|---|---|")
    for fraction in offsets:
        top_px = height_px * fraction
        visible = index.visible(Viewport.of_pixels(top_px, args.window, args.px_per_inch))
        row = _time_draw(imgui, visible, fonts, args.repeat, args.px_per_inch)
        print(
            f"| {fraction:.2f} | {top_px:.0f}px | {row.commands} "
            f"| {row.draw_ms:.2f}ms | {row.budget_fraction * 100:.0f}% |"
        )
    print()

    print(f"### Where a frame's time goes, {_copies(copies[0])}\n")
    print(
        "Rows 1-4 are exact and settle whether batching runs of glyphs is worth\n"
        "anything: row 1 minus row 2 is ImGui's own work, row 3 measures the same\n"
        "quantity independently, and row 4 is the floor. Rows 5-7 attribute the\n"
        "remainder and are a reconstruction of `draw`'s loop, so subtract them\n"
        "from row 5 and read the 5-to-2 gap as the reconstruction's own error.\n"
        "Only row 1 draws the document correctly. See `_anatomy`.\n"
    )
    print("| what | glyphs | best |")
    print("|---|---|---|")
    for what, glyphs, ms in _anatomy(
        imgui, indexes[copies[0]].cmds, fonts, args.repeat, args.px_per_inch
    ):
        print(f"| {what} | {glyphs} | {ms:.2f}ms |")
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

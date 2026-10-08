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
3. **Where a frame's time goes** -- `draw` against ImGui's share of it, to
   answer whether the cost is our per-glyph Python work or ImGui's per-call
   work. Four rows, all of them timings of real calls. Read the `_anatomy`
   docstring before drawing a conclusion from it, because two of its rows are
   timing probes that do not draw correct geometry. It had seven rows until
   2026-10-07; "Rows 5 to 7, retired" below says what they were and why they
   went.
4. **`Face.CODE` set ragged, against the default theme** -- the same source and
   measure through `mono_ragged_theme`, which is what a host with an all-mono,
   ragged-right transcript would draw. See "The mono ragged run" below.

## What it found

**Every millisecond in this section was re-taken on 2026-10-07**, one run of
`python scripts/bench_draw.py --copies 1,2,4 --repeat 7` on this machine with a
load average of 0.4, after the per-key memo this section used to recommend had
been built (`advtext.backends.imgui_draw._Preambles`, 2026-10-06). The figures
it replaces are kept under "Before the memo" because they are the measurement
that justified the change.

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
twenty minutes on this machine, over the identical 5,378 commands and before the
memo, gave a full draw of **28.0, 30.3, 33.9 and 34.1 ms** -- a 22% spread with
no code change. Compare *ratios* between rows of one run, which is what the
conclusions below rest on; do not compare an absolute against a different day's
absolute.

The tables are one run, `--copies 1,2,4 --repeat 7`:

    | copies | commands | full draw | visible | culled draw |
    |      1 |    5,378 |   15.94ms |   1,952 |      5.90ms |
    |      2 |   10,756 |   30.82ms |   1,952 |      5.80ms |
    |      4 |   21,512 |   62.51ms |   1,952 |      5.82ms |

The full column doubles with the file and the culled column does not move. A
culled draw is about a third of a 16.67ms frame; before the memo it was about
two thirds (10.5ms in the table under "Before the memo", and 13.2 to 13.9ms in
the before-and-after its builder took on a loaded machine,
`.concerns/A4-draw--builder--result.md`).

**The per-frame cost is still our Python, not ImGui's drawing.** The `bench-draw`
task asked whether the per-frame cost is Python call overhead or ImGui's
per-call work, on the grounds that if it is the former a batched path for
agreeing runs might be worth building. The anatomy table said it was
overwhelmingly the former before the memo and says the same after it:

    | 1. `draw`, as shipped                            | 15.77ms |
    | 2. the real `draw`, into a draw list that discards| 15.09ms |
    | 3. per-glyph `add_text` alone, precomputed        |  1.27ms |
    | 4. batched `add_text` over 71 runs                |  0.03ms |

ImGui's share is `1 - 2` = **0.7ms**, and row 3 reads 1.3ms measuring the same
thing from the other end (`_Discarding` says why the first understates). So
**batching every
glyph in the document into 71 `add_text` calls would save about 1ms of 16**, and
it would have to give up the per-glyph positioning `docs/imgui-risks.md` item 3
exists to defend. As a share that is larger than it was (about 6% against 3%),
because the memo took 13ms out of the denominator and nothing out of ImGui's
millisecond; as an amount it is what it always was.

What the other 15ms is made of is **not decomposed by this script any more**
(see the next section). One `cProfile` run over five draws on 2026-10-07, which
inflates call-heavy code and is good for an order and no better, put the
internal time in this order: `_glyph` itself, `_RigidSpan.pen`, the `draw_runs`
loop, `snap_px`, and a function-local `from imgui_bundle import imgui` that
`_glyph` executed once per glyph. Each is per-glyph Python. None of that is
this script's to change.

The last of those has since been removed (later on 2026-10-07: `draw_runs`
hands `_glyph` the `ImVec2` constructor, and
`tests/test_imgui_draw.py::test_drawing_runs_no_import_statement_per_glyph`
counts imports). The tables in this docstring were taken before that and are
left as taken; one run afterwards, same command, quiet machine, read 13.68 /
27.05 / 54.04 ms full and 5.12 / 5.09 / 5.08 ms culled at one, two and four
copies, anatomy rows 1 to 4 at 13.88 / 13.13 / 1.26 / 0.03 ms. The profile
order above was not re-taken.

### Rows 5 to 7, retired

The anatomy table used to go on for three more rows: a hand-written copy of
`advtext.backends.imgui_draw._glyph`'s body, then the same with ImGui's metric
calls dropped, then the bare loop. They attributed the cost *inside* `_glyph`
by subtraction, and they are how the per-key memo was found. Their own
docstring said they would go stale silently if `_glyph` changed, and it did:
they went on timing a per-glyph `parse_font_key`, `fontlib_metrics`,
`baked_size_px` and `get_font_baked` that `draw` now does once per key. On the
last run that had them (2026-10-07, minutes before the run above) the
reconstruction read **19.5ms against the 15.8ms of the `draw` it claimed to
reconstruct** -- slower than the real thing, so the "reconstruction's
own error" the table told a reader to subtract was negative.

They are deleted rather than rewritten against the memoised `_glyph`. A
reconstruction of the new body would be stale at the next backend edit in the
same way, and what is left to attribute is spread over five small things (the
profile above) rather than concentrated in one that a subtraction can isolate.
Rows 1 to 4 call the real `draw` and real `add_text` and cannot go stale that
way.

### Before the memo

One run from before 2026-10-06, `--copies 1,2,4 --repeat 7`, of the backend as
it was at commit `cb7bebf`. Kept as history; the counts are the same counts.

    copies 1 / 2 / 4:   full draw 30.32 / 59.86 / 114.52 ms,  culled 10.46 / 11.00 / 10.35 ms

    row 1  `draw`, as shipped                                 29.36 ms
    row 2  the real `draw`, into a draw list that discards    28.47 ms
    row 3  per-glyph `add_text` alone, precomputed             1.38 ms
    row 4  batched `add_text` over the same runs               0.03 ms
    row 5  a reconstruction of that loop                      20.49 ms
    row 6  ...minus `is_glyph_in_font` and `get_font_baked`   18.78 ms
    row 7  ...minus our own arithmetic                         1.95 ms

What was read off it then: ImGui's share `1 - 2` = 0.9ms; **16.8ms** (`6 - 7`)
our own per-glyph arithmetic -- `parse_font_key` re-parsing the same key string,
`fontlib_metrics` re-resolving the same face, `baked_size_px` recomputing the
same ratio, two `px_from_sp` calls and two `ImVec2` constructions; 8.0ms
(`2 - 5`) Python dispatch the reconstruction did not have; 2.0ms the bare loop
and the `DrawStats` rebuild.

Every one of those was a value constant across the run of glyphs sharing a
`FontKey`, and there are 71 such runs in 4,362 glyphs. The conclusion drawn was
that memoising the preamble per key was worth an order of magnitude more than
batching the draw and cost no geometry. It was built, per *key* rather than per
run (8 keys in this document), and the first table above is the result: a full
draw of 16ms where this one reads 30.

## The mono ragged run

Added 2026-10-06 for `docs/adoption-plan.md` phase 0. Every figure above is for
justified Roboto, and the adopting host sets everything in one monospace face,
ragged right. Nothing had drawn that through this backend and timed it.

The same run as the tables above (2026-10-07), 420pt, a 768px window:

    | theme       | commands | glyphs | spans | runs | full draw | visible | culled draw |
    | default     |    5,378 |  4,362 |   876 |   71 |   15.76ms |   1,952 |      5.84ms |
    | mono ragged |    5,392 |  4,362 |   876 |   12 |   15.81ms |   1,763 |      5.27ms |

**The mono ragged row's counts are of first-fit breaking.** Since 2026-10-06
composition breaks a non-justified block first-fit at natural spacing
(`advtext.ui._text_boxes`). When this table was first taken the ragged lines
came from the total-fit breaker, which set some of them with their spaces
compressed and so broke them in other places, and the row read 5,387 commands
and 1,831 visible. Glyphs, spans and runs are the same under both, and the
default row's counts did not move.

**The theme is one call now.** `mono_ragged_theme` is
`Theme.build(faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)`. Until
2026-10-07 it was a private `Theme` subclass overriding `face_for`, because
`Theme.build` took neither faces nor an alignment. Checked before the subclass
was deleted: the two themes have equal `blocks`, and `demo/sample.md` ships
equal command tuples under both at one, two and four copies (5,392 commands at
one). `bold=Face.CODE` because this tree bundles no bold monospace file and the
unregistered `Face.CODE_BOLD` stands in Roboto Bold (`advtext.fontlib`); a host
that registers one draws two faces and more runs than this row.

The counts are exact and `tests/test_bench_numbers.py` re-derives them. What
they say, and it is about counts and not about appearance:

- **Every glyph is `Face.CODE`**: the default theme sets the same 4,362 glyphs
  in five faces (3,811 prose, 310 code, 206 bold, 24 italic, 11 bold italic).
  `demo/sample.md` contains no mathematics, so this run says nothing about
  `Face.MATH`, which a theme does not choose.
- **Per-glyph cost is the same to within the run's noise**, 3.61 against
  3.62 microseconds: a monospace glyph goes through the same `_glyph` as a
  proportional one.
- **The glyph count and the rigid-span count do not move** (4,362 and 876 under
  both). Fourteen more commands ship and 189 fewer are visible in the first window,
  because the lines break in different places and the page is a different
  height; that is a difference in the layout and not in the cost of drawing it.
- **`runs` falls from 71 to 12** because there is one face left to change to and
  only sizes still differ. That is the count a batched path would issue calls
  for; it is a bound, and nothing here builds a batched path.

Whether a monospace run's advances agree with ImGui's closely enough to batch is
`scripts/verify_advances.py`'s question. It was asked on 2026-10-06
(`.concerns/A4-draw--builder--result.md`): at 12, 14, 16, 18 and 20 px, 0 of 94
printable ASCII characters disagree; at 13, 15 and 17 px all 94 do, by half a
pixel each, because Inconsolata's advance is half an em and ImGui quantises an
advance to a whole pixel. Nothing was built on it.

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
needs a display; implementing the batched draw path table 3 measures the
headroom for; and attributing the Python inside `draw`, which rows 5 to 7 once
did and a profiler now does better.
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
from advtext.backends.imgui_draw import DEFAULT_PALETTE, baked_size_px, draw
from advtext.fontmetrics import Face
from advtext.markdown import build_document
from advtext.shipout import DrawCmd, Glyph, Point, ship
from advtext.style import (
    Align,
    Faces,
    Theme,
    char_measure,
    fontlib_metrics,
    parse_font_key,
)
from advtext.ui import CommandIndex, Viewport, compose
from advtext.units import DEFAULT_PX_PER_INCH, px_from_sp, sp_from_pt

__all__ = [
    "DEFAULT_COPIES",
    "DEFAULT_OFFSETS",
    "DEFAULT_WIDTH_PT",
    "DEFAULT_WINDOW_PX",
    "DrawTiming",
    "glyphs_by_face",
    "main",
    "mono_ragged_theme",
    "rigid_spans",
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


def mono_ragged_theme() -> Theme:
    """
    The default theme with every block in `Face.CODE` and set ragged right.

    Sizes, leading, indents and spacing are the default theme's, so the type
    scale still has four sizes and the only things that differ from the other
    tables' input are the two the name says: the face, and `Align.LEFT` where
    the default has `Align.JUSTIFY`. Headings, code blocks, rules and tables are
    already `Align.LEFT` in the default theme.

    **One call to `Theme.build`.** This used to return a private `_MonoTheme`
    subclass that overrode `face_for`, because `Theme.face_for` chose a run's
    face without consulting the block's and `Theme.build` took no faces. Both
    changed on 2026-10-06 (`advtext.style.Faces`), and the subclass was deleted
    on 2026-10-07 after checking that the two themes have equal `blocks` and
    ship `demo/sample.md` to equal command tuples at one, two and four copies.

    `bold=Face.CODE` and not the default `Face.CODE_BOLD`: no bold monospace
    file is bundled, and the unregistered `CODE_BOLD` role is backed by Roboto
    Bold, which would put a proportional face in the headings. Bold and italic
    therefore collapse to the one monospace face, as they did in the subclass.
    A host that registers a bold monospace will draw two faces, and so more
    runs, than this benchmark's figure.

    What it does **not** change is mathematics. A formula's glyphs are
    `Face.MATH`, chosen by `advtext.mathlist` and not by the theme, and they
    stay that way; the table prints glyphs by face so a reader can see how many.
    """
    return Theme.build(faces=Faces.mono(bold=Face.CODE), align=Align.LEFT)


def rigid_spans(cmds: Sequence[DrawCmd]) -> int:
    """
    How many maximal runs of consecutive `Glyph` commands a list holds.

    This is the unit `advtext.backends.imgui_draw.draw` snaps as one piece: it
    opens a span at a `Glyph` that follows anything else and drops it at the
    next `SetGlue`, `Line` or `RuleRect`. Counted from the command list alone,
    the way `draw` delimits them, so it needs no atlas.

    Measured on `demo/sample.md` at 420pt it is 876 under the default theme and
    876 under `mono_ragged_theme`: a ragged setting moves the slack to the end
    of the line and leaves the same glue between the same words.
    """
    count = 0
    inside = False
    for cmd in cmds:
        if isinstance(cmd, Glyph):
            if not inside:
                count += 1
            inside = True
        else:
            inside = False
    return count


def glyphs_by_face(cmds: Sequence[DrawCmd]) -> dict[Face, int]:
    """
    How many glyphs of a command list are set in each face, most numerous first.
    """
    counts: dict[Face, int] = {}
    for cmd in cmds:
        if isinstance(cmd, Glyph):
            face = parse_font_key(cmd.font).face
            counts[face] = counts.get(face, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def shipped_commands(
    source: str, copies: int, width_pt: float, theme: Theme | None = None
) -> tuple[DrawCmd, ...]:
    """
    Compose and ship `copies` concatenations of `source` at a measure.

    Composition is not timed and is not in any table: `scripts/bench_reflow.py`
    owns that number, and quoting it twice in two scripts is how two numbers
    start disagreeing.

    `theme` defaults to `Theme.build()`, which is what every table but the last
    is taken with; `mono_ragged_theme()` is the other one this script passes.
    """
    if theme is None:
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
    One fully resolved `add_text` call: its font, size, position and character.
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

    The font, the size and the character are the ones
    `advtext.backends.imgui_draw.draw` arrives at, worked out here rather than
    imported because the point is to move that work *out* of the timed region.
    The positions are the shipped ones, unsnapped: `draw` moves each rigid span
    by under a pixel before it issues the call, and this does not, which changes
    where a glyph lands and not what an `add_text` costs. Rows 3 and 4 of the
    anatomy table are timing probes and say so. If the backend changes which
    font or size a glyph is drawn at, this goes stale and those two rows with
    it, while every row that calls the real `draw` stays right -- which is why
    it is a private helper of one table and not a general facility.
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

    flags: int = 0
    """
    Read, set and restored by `draw` around its loop, so it must exist.

    `draw` sets `ImDrawListFlags_.text_no_pixel_snap` on the list it is handed
    and puts the old value back. This stand-in predates that, and without the
    attribute row 2 of the anatomy table raised `AttributeError` and the script
    died after printing two tables -- found 2026-10-06 by running it.
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
    `draw` against ImGui's share of it, to say whose milliseconds a frame's are.

    The question this exists to answer is the one the `bench-draw` task asked: is
    the cost ImGui's per-call work, in which case batching runs of glyphs into
    one `add_text` is worth pursuing, or is it our own Python, in which case it
    is not.

    **Four rows, and every one is a timing of real calls.** Row 2 is the *real*
    `draw`, over the *real* command list, handed a `_Discarding` draw list
    instead of ImGui's -- so `1 - 2` is everything ImGui does with a glyph once
    it has been asked for it, and no part of `draw` has been reconstructed to
    get the number. Row 3 measures the same quantity from the other end and must
    roughly agree with `1 - 2`; two independent estimates of one number are
    worth more than one. Row 4 is the floor a batched path could aim at. Rows 3
    and 4 do not draw the document correctly (unsnapped positions; ImGui's own
    advances inside a run) and are not meant to.

    **There were three more rows until 2026-10-07**, a hand-written copy of
    `_glyph`'s body with one layer dropped at each step. `_glyph` was memoised
    per font key on 2026-10-06 and the copy was not, so it timed work `draw` no
    longer did and came out slower than the function it reconstructed. Retired;
    the module docstring keeps their last honest figures and says what they
    found.
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
        "Whether batching runs of glyphs is worth anything: row 1 minus row 2 is\n"
        "ImGui's own work, row 3 measures the same quantity independently, and\n"
        "row 4 is the floor. Everything else in row 1 is this project's Python.\n"
        "Only row 1 draws the document correctly. See `_anatomy`.\n"
    )
    print("| what | glyphs | best |")
    print("|---|---|---|")
    for what, glyphs, ms in _anatomy(
        imgui, indexes[copies[0]].cmds, fonts, args.repeat, args.px_per_inch
    ):
        print(f"| {what} | {glyphs} | {ms:.2f}ms |")
    print()

    print(f"### `Face.CODE` set ragged against the default theme, {_copies(copies[0])}\n")
    print(
        "The same source at the same measure through two themes. `spans` is the\n"
        "rigid spans `draw` snaps as a unit and `runs` is consecutive glyphs sharing\n"
        "a face and a size. Mathematics stays in its own face under either theme.\n"
        "Compare the two rows with each other; see the module docstring.\n"
    )
    print(
        "| theme | commands | glyphs | by face | spans | runs "
        "| full draw | µs/glyph | visible | culled draw |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, theme in (("default", None), ("mono ragged", mono_ragged_theme())):
        cmds = shipped_commands(source, copies[0], args.width, theme)
        by_face = ", ".join(f"{face.value} {n}" for face, n in glyphs_by_face(cmds).items())
        runs = len(_runs(_resolved_calls(imgui, cmds, fonts, args.px_per_inch)))
        full = _time_draw(imgui, cmds, fonts, args.repeat, args.px_per_inch)
        visible = CommandIndex.of(cmds).visible(
            Viewport.of_pixels(0.0, args.window, args.px_per_inch)
        )
        culled = _time_draw(imgui, visible, fonts, args.repeat, args.px_per_inch)
        per_glyph = full.draw_ms * 1000.0 / full.glyphs if full.glyphs else 0.0
        print(
            f"| {name} | {full.commands} | {full.glyphs} | {by_face} | {rigid_spans(cmds)} "
            f"| {runs} | {full.draw_ms:.2f}ms | {per_glyph:.2f} | {culled.commands} "
            f"| {culled.draw_ms:.2f}ms |"
        )
        if full.missing or culled.missing:
            print(f"| | **{full.missing} / {culled.missing} glyphs missing** | | | | | | | | |")
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

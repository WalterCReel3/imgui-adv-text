"""
The Stress page: its arithmetic, that its panes follow its controls, the one
line it draws without the library, that its counters count what they say, and
a run in a real window at 1, 4 and 16 panes.

**The figures the page shows are wall-clock times and no test asserts one.** A
test that a draw takes under some number of milliseconds is a test of the
machine. What is asserted is the bookkeeping: that a sample is taken per pane
per frame, that `sync` and `draw` are timed apart, that the vertex and block
counts agree with what the views themselves report, and that the totals are
the sums they claim to be. The timer in the frame tests is a fake that ticks
one millisecond a reading, so those figures are exact.

**Where each thing runs.** A pane is a view and a view needs the imtypeset
library, which the pytest process never has ready (also under
`make test TYPESET=1`). So:

- with no library, in the pytest process: the arithmetic; the controls'
  values; the panes following the controls and the clock, over `_View`, a
  stand-in that holds what it was given and draws nothing; and the page
  itself, which is one line saying why not;
- with the library, in children that say THERE whether `typesetter.module()`
  and `ready()` held, before the body and after it: real ImGui frames with no
  window (`_HEADLESS`), and the tour in a real window, finished and streaming.
  Skipped, with the reason, when `IMTYPESET_LIBRARY` is not set.

The window tests print the page's own report at each pane count and check the
counts in it. Its milliseconds are **software-rendered Xvfb figures** wherever
the `window` fixture had to fall back to one, and they are printed, not judged.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownDocument, MarkdownStream
from imscribe.ui import pages
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import stress as page
from imscribe.ui.pages.stress import (
    LENGTHS,
    MAX_PANES,
    REFERENCE_MS,
    Rolling,
    Stress,
    grid_shape,
    readouts,
    repeated,
)
from imscribe.ui.pages.typeset import why_not

if TYPE_CHECKING:
    from conftest import Window

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_SKIP = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)

SMALL = (
    "# A heading\n\n"
    "A paragraph long enough to be broken onto more than one line in a narrow pane, "
    "so that a pane holds several blocks and several lines of text.\n\n"
    "- one item\n- another item\n\n"
    "A closing paragraph.\n"
)


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


class _View:
    """
    What stands where `TypesetView` does in the tests of what `Stress` does with its panes.

    It keeps what it was made over and whether it was closed. It holds no
    document in any library and draws nothing; no test that uses it asserts
    anything about a view.
    """

    made: list[_View] = []

    def __init__(self, shown: object, **settings: object) -> None:
        self.shown = shown
        self.settings = settings
        self.closed = False
        self.cleared = 0
        _View.made.append(self)

    def close(self) -> None:
        self.closed = True

    def clear_selection(self) -> None:
        self.cleared += 1


class _StreamView(_View):
    """
    The same, where `TypesetStreamView` stands: `shown` is the stream.
    """


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch) -> type[_View]:
    """
    The two stand-ins under the page module's names for the views, for one test.
    """
    monkeypatch.setattr(page, "TypesetView", _View)
    monkeypatch.setattr(page, "TypesetStreamView", _StreamView)
    monkeypatch.setattr(_View, "made", [])
    return _View


def _stress(theme: Theme, **fields: Any) -> Stress:
    """
    A `Stress` over `SMALL` with its panes made (over whatever stands for the views).
    """
    fields.setdefault("source", SMALL)
    stress = Stress(theme=theme, **fields)
    stress.configure()
    return stress


# ----------------------------------------------------------------------
# Arithmetic
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("panes", "shape"),
    [(1, (1, 1)), (2, (2, 1)), (3, (2, 2)), (4, (2, 2)), (5, (3, 2)), (9, (3, 3)), (16, (4, 4))],
)
def test_the_grid_is_as_near_square_as_it_goes(panes: int, shape: tuple[int, int]) -> None:
    assert grid_shape(panes) == shape


@pytest.mark.parametrize("panes", range(1, MAX_PANES + 1))
def test_the_grid_holds_every_pane_and_has_no_empty_row(panes: int) -> None:
    columns, rows = grid_shape(panes)
    assert columns * rows >= panes > columns * (rows - 1)


def test_a_rolling_median_forgets_what_left_its_window() -> None:
    rolling = Rolling(size=3)
    assert (rolling.median_ms, rolling.last_ms, rolling.worst_ms) == (0.0, 0.0, 0.0)
    for seconds in (0.100, 0.001, 0.002, 0.003):
        rolling.add(seconds)
    # The 100 ms sample is gone: the window is 1, 2, 3.
    assert rolling.median_ms == pytest.approx(2.0)
    assert rolling.worst_ms == pytest.approx(3.0)
    assert rolling.last_ms == pytest.approx(3.0)
    rolling.clear()
    assert rolling.median_ms == 0.0


def test_one_slow_frame_does_not_move_the_median() -> None:
    """
    Why the page shows a median: a first layout of 200 ms among 59 frames of
    1 ms is a 4.3 ms mean and a 1 ms median.
    """
    rolling = Rolling()
    rolling.add(0.200)
    for _ in range(59):
        rolling.add(0.001)
    assert rolling.median_ms == pytest.approx(1.0)


def test_a_longer_document_is_the_source_repeated_and_is_parsed_once(theme: Theme) -> None:
    """
    No library and no pane: the text and its parse are the page's own.
    """
    assert repeated("a\n", 1) == "a\n"
    assert repeated("a\n", 3) == "a\n\na\n\na\n"
    stress = Stress(theme=theme, source=SMALL)
    one, five = stress.document(1), stress.document(5)
    assert isinstance(one, MarkdownDocument) and len(one.blocks) > 3
    assert len(five.blocks) == 5 * len(one.blocks)
    assert stress.document(5) is five, "the document was parsed again"
    assert stress.text(5) == repeated(SMALL, 5)


# ----------------------------------------------------------------------
# The controls' values, with no library and no pane
# ----------------------------------------------------------------------


def test_a_stress_holds_the_controls_and_makes_no_pane_until_it_is_configured(
    theme: Theme,
) -> None:
    """
    Made in the pytest process, where no view can be: the values are there,
    clamped as the controls clamp them, and there are no panes. The figures of
    no panes are zeros and the report is a line of them.
    """
    stress = Stress(theme=theme, source=SMALL, count=99, length=7, streaming=True)
    assert (stress.count, stress.length, stress.streaming, stress.select_all) == (
        MAX_PANES,
        LENGTHS[0],
        True,
        False,
    )
    assert stress.panes == []
    assert Stress(theme=theme, source=SMALL, count=0).count == 1
    assert (stress.total_ms, stress.per_view_ms, stress.per_piece_ms) == (0.0, 0.0, None)
    assert (stress.vertices, stress.blocks_drawn, stress.blocks_not_drawn) == (0, 0, 0)
    assert stress.pane_px == 0.0 and stress.pieces_per_frame == 0.0 and stress.feed(1.0) == 0
    line = page.report(stress)
    assert line.startswith("panes=0 streaming=1 length=1 samples=0 sync_ms=0.000 draw_ms=0.000 ")
    assert "glyphs" not in line and "units" not in line
    assert Stress(theme=theme).source == pages.demo_text("sample.md")


def _context(name: str, *options: str, count: int | None = None) -> PageContext:
    """
    A context as `--tab NAME:options,count` gives one, without the app's parser.
    """
    return PageContext.build(request_page=name, request_options=options, request_count=count)


def test_the_launch_options_set_the_controls() -> None:
    def made(*options: str, count: int | None = None) -> Stress:
        return page.StressPage(_context("stress", *options, count=count)).stress

    plain = made()
    assert (plain.count, plain.length, plain.streaming, plain.select_all) == (4, 1, False, False)
    assert plain.panes == []
    busy = made("streaming", "selected", "x5", count=16)
    assert (busy.count, busy.length, busy.streaming, busy.select_all) == (16, 5, True, True)
    assert made(count=99).count == MAX_PANES
    assert made("x20").length == 20
    other = page.StressPage(_context("document", "streaming", count=9)).stress
    assert (other.count, other.streaming) == (4, False)


def test_the_page_is_discovered_and_its_shots_parse() -> None:
    from imscribe.ui.app import parse_tab_request

    found = pages.require()
    spec = found.find("stress")
    assert spec is page.PAGE
    for request in spec.shot_specs():
        assert parse_tab_request(request, found).tab == "stress"


# ----------------------------------------------------------------------
# Panes follow the controls: over the stand-in views
# ----------------------------------------------------------------------


def test_the_pane_count_is_clamped_and_followed(theme: Theme, stand_in: type[_View]) -> None:
    stress = _stress(theme, count=4)
    assert len(stress.panes) == 4
    for count, expected in ((0, 1), (7, 7), (99, MAX_PANES)):
        stress.count = count
        stress.configure()
        assert (stress.count, len(stress.panes)) == (expected, expected)


def test_changing_only_the_count_keeps_the_panes_there_were_and_closes_the_rest(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    A pane that leaves gives its document back to the library (`close`); the
    panes that stay are the same panes, with their views and their medians.
    """
    stress = _stress(theme, count=3)
    kept = list(stress.panes)
    stress.count = 5
    stress.configure()
    assert len(stress.panes) == 5
    assert all(a is b for a, b in zip(stress.panes[:3], kept, strict=True))
    extra = stress.panes[3:]
    stress.count = 2
    stress.configure()
    assert all(a is b for a, b in zip(stress.panes, kept[:2], strict=True))
    gone = [*extra, kept[2]]
    assert all(pane.view.closed for pane in gone)  # type: ignore[attr-defined]
    assert not any(pane.view.closed for pane in stress.panes)  # type: ignore[attr-defined]
    stress.configure()
    assert len(stand_in.made) == 5, "configuring with nothing changed made a view"


def test_each_finished_pane_has_a_view_of_its_own_over_the_one_parse(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    What the page says about sharing: one parsed document for all finished
    panes, and a view (a document in the library) each.
    """
    stress = _stress(theme, count=3)
    views = [pane.view for pane in stress.panes]
    assert len({id(view) for view in views}) == 3
    assert all(type(view) is _View for view in views)
    assert all(view.shown is stress.document(1) for view in views)  # type: ignore[attr-defined]
    assert all(pane.stream is None and pane.pieces == [] for pane in stress.panes)
    assert views[0].settings["theme"] is theme  # type: ignore[attr-defined]


def test_all_streaming_gives_every_pane_a_stream_of_its_own_read_ragged(
    theme: Theme, stand_in: type[_View]
) -> None:
    stress = _stress(theme, count=3)
    finished = list(stress.panes)
    stress.streaming = True
    stress.configure()
    assert all(type(pane.view) is _StreamView for pane in stress.panes)
    assert all(type(pane.stream) is MarkdownStream for pane in stress.panes)
    assert len({id(pane.stream) for pane in stress.panes}) == 3
    assert all(pane.view.shown is pane.stream for pane in stress.panes)  # type: ignore[attr-defined]
    assert not any(pane in finished for pane in stress.panes)
    assert all(pane.view.closed for pane in finished)  # type: ignore[attr-defined]
    assert all("".join(pane.pieces) == stress.text(1) for pane in stress.panes)
    ragged = page.ragged(theme)
    for pane in stress.panes:
        assert pane.stream is not None
        assert pane.stream.theme == ragged and pane.stream.live_theme == ragged


def test_a_change_of_length_rebuilds_the_panes_over_the_longer_document(
    theme: Theme, stand_in: type[_View]
) -> None:
    stress = _stress(theme, count=2)
    before = list(stress.panes)
    stress.length = 5
    stress.configure()
    assert all(pane.view.shown is stress.document(5) for pane in stress.panes)  # type: ignore[attr-defined]
    assert all(pane.view.closed for pane in before)  # type: ignore[attr-defined]
    stress.length = 7  # not one of the three the control offers
    stress.configure()
    assert stress.length == LENGTHS[0]


def test_streaming_panes_are_fed_by_the_clock_and_start_again_when_done(
    theme: Theme, stand_in: type[_View]
) -> None:
    stress = _stress(theme, count=2, streaming=True)
    total = len(stress.panes[0].pieces)
    starts = [pane.fed for pane in stress.panes]
    assert stress.feed(1.0) == 2 * 40, "forty pieces a second, each pane"
    assert [pane.fed - start for pane, start in zip(stress.panes, starts, strict=True)] == [40, 40]
    assert [pane.took for pane in stress.panes] == [40, 40]
    assert stress.panes[0].stream is not None and stress.panes[0].stream.source != ""

    first = stress.panes[0]
    stress.feed(1000.0)
    assert stress.panes[0] is first and first.fed == total
    assert first.stream is not None and first.stream.source == stress.text(1)
    stress.feed(0.5)
    again = stress.panes[0]
    assert again is not first and again.laps == 1 and again.fed == 20
    assert again.per_piece is first.per_piece
    assert again.sync is first.sync, "the medians were thrown away at the restart"
    assert first.view.closed, "the pane that left kept its document"  # type: ignore[attr-defined]
    assert not again.view.closed  # type: ignore[attr-defined]

    finished = _stress(theme, count=2)
    assert finished.feed(1.0) == 0


def test_streaming_panes_are_staggered_in_place_and_in_time(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    Sixteen panes that all start at the first character and all take their
    pieces on the same frames measure one event sixteen times: every pane
    reaches the long table on the same frame. Each pane starts at another
    place in the document, and takes its pieces on other frames.
    """
    stress = _stress(theme, count=4, streaming=True)
    starts = [pane.fed for pane in stress.panes]
    assert starts[0] == 0 and starts == sorted(set(starts)), starts
    total = len(stress.panes[0].pieces)
    assert starts[-1] < total
    for pane, start in zip(stress.panes, starts, strict=True):
        assert pane.stream is not None
        assert pane.stream.source == "".join(pane.pieces[:start])

    # At 40 pieces a second and 60 frames a second a pane takes a piece on two
    # frames of three. Which two differs from pane to pane.
    taken = []
    for _ in range(6):
        stress.feed(1.0 / 60.0)
        taken.append(tuple(pane.took for pane in stress.panes))
    patterns = list(zip(*taken, strict=True))
    assert all(sum(pattern) == 4 for pattern in patterns), patterns
    assert len(set(patterns)) > 1, f"every pane took its pieces on the same frames: {patterns}"

    # A pane that starts again starts at the beginning; it is out of step already.
    stress.feed(10_000.0)
    stress.feed(0.0)
    assert [pane.fed for pane in stress.panes] == [0, 0, 0, 0]


def test_a_frames_cost_is_also_kept_per_piece_of_text_it_took(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    A frame that took three pieces is one sample of a third of its cost per
    piece; a frame that took none is no sample of that at all.
    """
    stress = _stress(theme, count=1, streaming=True)
    (pane,) = stress.panes
    pane.took = 3
    pane.sample(0.001, 0.002)
    assert pane.sync.median_ms == pytest.approx(1.0) and pane.draw.median_ms == pytest.approx(2.0)
    assert pane.per_piece.median_ms == pytest.approx(1.0)
    pane.took = 0
    pane.sample(0.5, 0.5)
    assert len(pane.per_piece.samples) == 1 and len(pane.sync.samples) == 2
    assert stress.per_piece_ms == pytest.approx(1.0)
    assert stress.pieces_per_frame == pytest.approx(1.5)
    stress.forget()
    assert (len(pane.sync.samples), len(pane.draw.samples), len(pane.taken)) == (0, 0, 0)
    assert stress.per_piece_ms is None

    finished = _stress(theme, count=2)
    assert finished.per_piece_ms is None and finished.pieces_per_frame == 0.0
    for each in finished.panes:
        each.sample(0.001, 0.003)
    assert finished.sync_ms == pytest.approx(2.0) and finished.draw_ms == pytest.approx(6.0)
    assert finished.total_ms == pytest.approx(8.0)
    assert finished.per_view_ms == pytest.approx(4.0)


def test_the_readout_shows_the_reference_line_and_does_not_rule_on_it(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    The total, the 1.7 ms line and their ratio are on the page. Whether the
    line is met is not -- at a total under it or at one over it. The samples
    are put in by hand so that both sides of the line are certainly reached.
    """

    def lines(count: int, seconds: float) -> tuple[str, ...]:
        stress = _stress(theme, count=count)
        for pane in stress.panes:
            pane.sync.add(seconds)
            pane.draw.add(seconds)
        return readouts(stress)

    under, over = lines(1, 0.0005), lines(16, 0.001)
    assert 1.0 < REFERENCE_MS < 32.0, "the two cases no longer straddle the reference"
    assert "1 panes (TypesetView, finished)" in under[0] and "16 panes" in over[0]
    assert "parse and edit 0.50 ms  +  layout and draw 0.50 ms  =  1.00 ms" in under[0]
    assert "parse and edit 16.00 ms  +  layout and draw 16.00 ms  =  32.00 ms" in over[0]
    assert f"reference line {REFERENCE_MS:.1f} ms" in under[1]
    assert f"{1.0 / REFERENCE_MS:.2f} x" in under[1] and f"{32.0 / REFERENCE_MS:.2f} x" in over[1]
    assert under[2] == "vertices submitted 0  ·  blocks drawn 0, not drawn 0"
    assert "not timed: ImGui's render" in under[3]
    assert "its own document in the library" in under[3]
    # Per view, which is what can be compared across pane counts: the total
    # over the panes, with its own ratio to the line.
    assert "per view 1.00 ms a frame" in under[4] and "per view 2.00 ms a frame" in over[4]
    assert f"{1.0 / REFERENCE_MS:.2f} x" in under[4] and f"{2.0 / REFERENCE_MS:.2f} x" in over[4]
    assert "per piece of text: none taken" in under[4]
    assert "pane measure" in under[4]
    assert "nothing is shared between views" in under[5] and "staggered" in under[5]
    assert len(under) == len(over) == 6
    streaming = readouts(_stress(theme, count=2, streaming=True))
    assert "2 panes (TypesetStreamView, text arriving)" in streaming[0]
    verdicts = ("within", "exceed", "budget", "meets", "fails", "slow", "fast", "good", "bad")
    for shown in (under, over, streaming, (page.RENDERER_LINE,)):
        text = " ".join(shown).lower()
        for word in verdicts:
            assert word not in text, f"the readout says {word!r}"


# ----------------------------------------------------------------------
# The page with no library: one line, and nothing else
# ----------------------------------------------------------------------


def _frames(draw: Any, count: int, seconds: float = 1.0 / 60.0) -> Any:
    """
    `count` real frames of `draw` in a window that fills the display. Returns ImGui.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1300.0, 800.0)
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    for _ in range(count):
        io.delta_time = seconds
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(1300.0, 800.0))
            imgui.begin("##imscribe-stress-page-test", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                draw()
            finally:
                imgui.end()
        finally:
            imgui.render()
    return imgui


def test_without_the_library_the_page_draws_one_line_saying_why_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Real ImGui frames in the pytest process, where `ready()` is false. Each
    frame is one call of `say_why_not` with `why_not()`'s sentence and no call
    of anything else the page draws with; no pane is made and nothing is fed.
    Then the same frames with nothing patched, so the line itself reaches ImGui.
    """
    assert not typesetter.ready()
    made = page.StressPage(_context("stress", "streaming", count=16))
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the page drew, or built, more than the one line")

    monkeypatch.setattr(page, "caption", never)
    monkeypatch.setattr(page.StressPage, "_controls", never)
    monkeypatch.setattr(Stress, "configure", never)
    monkeypatch.setattr(Stress, "frame", never)
    _frames(made.draw, 4)
    assert said == [why_not()] * 4 and said[0]
    assert made.frames == 4 and made.failed == "" and made.reason == why_not()
    assert made.renderer == "none" and made.stress.panes == []
    report = made.report()
    assert report.startswith("frames=4 panes=0 streaming=1 ") and report.endswith(" renderer=none")

    monkeypatch.undo()
    imgui = _frames(made.draw, 2)
    assert made.frames == 6 and imgui.get_current_context() is not None


@pytest.mark.parametrize("how", ["raised in a frame", "not ready any more"])
def test_a_page_that_gives_up_closes_its_views_and_keeps_its_panes(
    how: str, monkeypatch: pytest.MonkeyPatch, stand_in: type[_View]
) -> None:
    """
    B3 (T5-R #3). Until T5-FINAL only the Diff page closed its views when it
    gave up; this page kept every view, and with it the document each holds
    in the library, for as long as the page object lived. Both ways of giving
    up are held here: `TypesetUnavailable` out of a frame, and a library that
    stopped being ready between frames (another page's view switched it off).
    The page's own state is kept either way: it is what `report()` prints.
    """
    ready = {"reason": ""}
    monkeypatch.setattr(page, "why_not", lambda: ready["reason"])
    monkeypatch.setattr(page, "say_why_not", lambda reason: None)
    made = page.StressPage(_context("stress", count=4))
    made.stress.configure()
    views = [pane.view for pane in made.stress.panes]
    assert len(views) == 4 and not any(view.closed for view in views)

    if how == "raised in a frame":

        def unavailable(self: Stress, pane: Any, imgui: Any) -> bool:
            raise page.TypesetUnavailable("switched off under the frame")

        monkeypatch.setattr(Stress, "frame", unavailable)
    else:
        ready["reason"] = "switched off by another page"
    _frames(made.draw, 1)

    assert made.renderer == "none"
    assert [view.closed for view in views] == [True] * 4
    assert [pane.view for pane in made.stress.panes] == views
    assert "renderer=none" in made.report()


def test_a_typeset_unavailable_out_of_a_frame_stays_in_the_page_and_anything_else_leaves(
    monkeypatch: pytest.MonkeyPatch, stand_in: type[_View]
) -> None:
    """
    The page's handler, with the library's readiness stood in for and the
    views stood in for. `TypesetUnavailable` out of the first pane's frame:
    the child window it was in is ended (ImGui accepts the frame), the reason
    is kept, no later pane is tried, and the frames after it are the one line.
    Any other exception is a bug and is not caught.
    """
    made = page.StressPage(_context("stress", count=4))
    monkeypatch.setattr(page, "why_not", lambda: "")
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)
    tried: list[int] = []

    def unavailable(self: Stress, pane: Any, imgui: Any) -> bool:
        tried.append(self.panes.index(pane))
        raise page.TypesetUnavailable("switched off under the frame")

    monkeypatch.setattr(Stress, "frame", unavailable)
    _frames(made.draw, 3)
    assert tried == [0], "panes were tried after the library had failed"
    assert made.failed == "switched off under the frame" and said == [made.failed] * 2
    assert made.frames == 3 and made.renderer == "none" and len(made.stress.panes) == 4

    def broken(self: Stress, pane: Any, imgui: Any) -> bool:
        raise ZeroDivisionError("a bug")

    other = page.StressPage(_context("stress", count=1))
    monkeypatch.setattr(Stress, "frame", broken)
    imgui = pytest.importorskip("imgui_bundle").imgui
    io = imgui.get_io()
    io.delta_time = 1.0 / 60.0
    imgui.new_frame()
    try:
        imgui.begin("##imscribe-stress-page-bug", None, 0)
        try:
            with pytest.raises(ZeroDivisionError):
                other.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    assert other.failed == ""


def test_unticking_select_all_clears_the_selection_in_every_pane(
    monkeypatch: pytest.MonkeyPatch, stand_in: type[_View]
) -> None:
    """
    The one thing `_controls` does to a view, over the stand-ins: the frame on
    which the box is found unticked clears each pane's selection once.
    """
    made = page.StressPage(_context("stress", "selected", count=3))
    made.stress.configure()
    monkeypatch.setattr(page, "why_not", lambda: "")
    monkeypatch.setattr(Stress, "frame", lambda self, pane, imgui: True)
    imgui = pytest.importorskip("imgui_bundle").imgui
    real = imgui.checkbox
    answers = iter([False])

    def checkbox(label: str, value: bool) -> tuple[bool, bool]:
        if label.startswith("select all"):
            return True, next(answers, False)
        return real(label, value)  # type: ignore[no-any-return]

    monkeypatch.setattr(imgui, "checkbox", checkbox)
    _frames(made.draw, 2)
    assert made.failed == "" and made.stress.select_all is False
    assert [pane.view.cleared for pane in made.stress.panes] == [1, 1, 1]  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# What the module imports, at import and ever
# ----------------------------------------------------------------------


def test_the_page_imports_nothing_of_the_old_core_or_the_old_views_even_lazily() -> None:
    """
    Read from the source, so an import inside a function counts.
    """
    from test_page_stream import OLD_MODULES, imports_of

    found = imports_of(_ROOT / "imscribe" / "ui" / "pages" / "stress.py")
    assert "imscribe.ui.typeset_view" in found and "imscribe.typeset_markdown" in found
    for name in found:
        for old in OLD_MODULES:
            assert name != old and not name.startswith(old + "."), name
    tree = ast.parse((_ROOT / "imscribe" / "ui" / "pages" / "stress.py").read_text("utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "DrawStats"]


_CLOSURE = r"""
import json, sys
import imscribe.ui.pages.stress
print("REPORT " + json.dumps(sorted(name for name in sys.modules if name.startswith("imscribe"))))
"""


def test_importing_the_page_loads_none_of_the_old_core() -> None:
    from test_typeset_closure import OLD_CORE, THEME

    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CLOSURE],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    loaded = set(json.loads(done.stdout.split("REPORT ", 1)[1]))
    assert "imscribe.ui.pages.stress" in loaded and "imscribe.ui.typeset_view" in loaded
    assert loaded & OLD_CORE == THEME, sorted(loaded & OLD_CORE)
    for name in ("imscribe.stream", "imscribe.markdown", "imscribe.style"):
        assert name not in loaded, name


# ----------------------------------------------------------------------
# A real window at 1, 4 and 16 panes
# ----------------------------------------------------------------------

TOUR = """
import sys

from imgui_bundle import hello_imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app
from imscribe.ui.pages import stress as stress_page

WANT_LIBRARY = sys.argv[1] == "with"
SPEC = sys.argv[2]
FRAMES = 90
COUNTS = (1, 4, 16)
state = {"frame": 0}
real_gui = imscribe_app.App.gui


def last_line(made):
    # After the body: what was true when the last frame had been drawn.
    panes = made.stress.panes
    print(
        "child imported=%d module=%d ready=%d page_frames=%d panes=%d stream_views=%d "
        "appends=%d laps=%d"
        % (
            "imtypeset" in sys.modules,
            WANT_LIBRARY and typesetter.module() is not None,
            typesetter.ready(),
            made.frames,
            len(panes),
            sum(type(pane.view).__name__ == "TypesetStreamView" for pane in panes),
            sum(pane.view.edits["append"] for pane in panes),
            sum(pane.laps for pane in panes),
        )
    )
    print("page " + made.report())
    print("why " + made.reason)


def touring_gui(self):
    if state["frame"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    made = self.page("stress")
    if not WANT_LIBRARY:
        real_gui(self)
        state["frame"] += 1
        if state["frame"] >= 8:
            last_line(made)
            hello_imgui.get_runner_params().app_shall_exit = True
        return
    if state["frame"] == 2:
        # In the child, so that this cannot pass with nothing drawn.
        assert typesetter.module() is not None, "not in use: " + typesetter.reason()
        assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
    index, within = divmod(state["frame"], FRAMES)
    if index >= len(COUNTS):
        last_line(made)
        hello_imgui.get_runner_params().app_shall_exit = True
        return real_gui(self)
    if within == 0:
        made.stress.count = COUNTS[index]
    if within == FRAMES - stress_page.WINDOW:
        # The medians are of the last WINDOW frames at this count, with the
        # cold frames after the change of count already behind them.
        made.stress.forget()
    real_gui(self)
    if within == FRAMES - 1:
        print(stress_page.report(made.stress))
    state["frame"] += 1


imscribe_app.App.gui = touring_gui
imscribe_app.run(tab=SPEC)
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def _tour(
    window: Window, how: str, monkeypatch: pytest.MonkeyPatch, spec: str = "stress:1"
) -> tuple[list[dict[str, str]], dict[str, str], dict[str, str], str, list[str]]:
    """
    The tour with or without the library.

    Each report's fields, the child's last line, the page's own report, the
    page's reason, and the report lines as printed.
    """
    script = window.out / "stress_page_tour.py"
    script.write_text(textwrap.dedent(TOUR), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how, spec])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    printed = done.stdout.splitlines()
    lines = [line for line in printed if line.startswith("panes=")]
    child = [line for line in printed if line.startswith("child ")]
    paged = [line[5:] for line in printed if line.startswith("page ")]
    why = [line[4:] for line in printed if line.startswith("why ")]
    assert len(child) == 1 and len(paged) == 1 and len(why) == 1, done.stdout
    return [_fields(line) for line in lines], _fields(child[0]), _fields(paged[0]), why[0], lines


def test_without_the_library_the_page_says_why_not_in_a_real_window(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app on `--tab stress:16,streaming` with the library's variables
    removed for the child: eight frames, in each of which the page drew (the
    app did not replace it by its traceback page), no pane was made, nothing
    of imtypeset was imported, and the page's reason is the sentence about
    the variable.
    """
    told, child, paged, why, _ = _tour(window, "without", monkeypatch, "stress:16,streaming")
    assert told == []
    assert child["imported"] == "0" and child["ready"] == "0" and child["panes"] == "0"
    assert int(child["page_frames"]) >= 8 and paged["frames"] == child["page_frames"]
    assert paged["renderer"] == "none" and paged["panes"] == "0" and paged["samples"] == "0"
    assert typesetter.LIBRARY_VARIABLE in why


def test_with_the_library_the_tour_is_drawn_by_imtypeset_in_a_real_window(
    window: Window, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app on `--tab stress`, ninety frames at each of 1, 4 and 16 panes,
    printing `report` after each: the median of the last sixty. The child
    asserts `typesetter.module()` and `ready()` itself on its third frame and
    reports both again after its last.

    Asserted: the counts. A full window of samples at each pane count, vertices
    submitted, and for every pane the same number of blocks, most of them not
    drawn (the sample is longer than a pane). (Vertices do not rise with the
    number of panes and nothing says they should: sixteen small panes show
    about as much text as four large ones.) **Not asserted: any time.** The
    milliseconds are echoed to the test's output, labelled with where the
    window was, so a run with `-s` shows them; on an Xvfb they are figures
    from a software rasteriser on a loaded machine.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    told, child, paged, why, lines = _tour(window, "with", monkeypatch)
    assert child["imported"] == "1" and child["module"] == "1" and child["ready"] == "1"
    assert why == "" and paged["renderer"] == "TypesetView"
    assert child["panes"] == "16" and child["stream_views"] == "0" and child["appends"] == "0"
    assert [fields["panes"] for fields in told] == ["1", "4", "16"], lines
    blocks = []
    for fields in told:
        panes = int(fields["panes"])
        assert fields["streaming"] == "0" and "glyphs" not in fields
        assert fields["samples"] == str(page.WINDOW)
        assert int(fields["vertices"]) > 0
        assert int(fields["blocks_drawn"]) >= panes, "a pane drew no block at all"
        assert float(fields["total_ms"]) > 0.0
        blocks.append((int(fields["blocks_drawn"]) + int(fields["blocks_not_drawn"])) // panes)
        assert int(fields["blocks_not_drawn"]) > int(fields["blocks_drawn"])
        assert fields["per_piece_ms"] == "-1.000"
    # Every pane holds the same document, so each has the same blocks.
    assert len(set(blocks)) == 1 and blocks[0] > 10, blocks
    with capsys.disabled():
        label = "software-rendered Xvfb" if window.where == "xvfb" else "the session's display"
        print(f"\nstress page through imtypeset, {label} figures (median of {page.WINDOW} frames):")
        for line in lines:
            print("  " + line)


def test_with_the_library_the_tour_streams_through_imtypeset_in_a_real_window(
    window: Window, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The same tour on `--tab stress:1,streaming`: every pane a
    `TypesetStreamView` whose text arrives on the real clock at forty pieces a
    second while it is drawn.

    Asserted: the counts. A full window of samples at each pane count; text
    taken in the window (a cost per piece exists, and pieces a frame is above
    zero); vertices submitted; at least one block drawn in every pane; and,
    from the views themselves after the last frame, sixteen stream views that
    made appends in the library, which is what tells a stream that streamed
    from one that was handed over whole. **Not asserted: any time**, and not
    how many pieces a frame, which is the machine's frame rate.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    told, child, paged, why, lines = _tour(window, "with", monkeypatch, "stress:1,streaming")
    assert child["imported"] == "1" and child["module"] == "1" and child["ready"] == "1"
    assert why == "" and paged["renderer"] == "TypesetView"
    assert child["panes"] == child["stream_views"] == "16"
    assert int(child["appends"]) > 16, "the streams did not arrive by appends"
    assert [fields["panes"] for fields in told] == ["1", "4", "16"], lines
    for fields in told:
        panes = int(fields["panes"])
        assert fields["streaming"] == "1"
        assert fields["samples"] == str(page.WINDOW)
        assert int(fields["vertices"]) > 0
        assert int(fields["blocks_drawn"]) >= panes, "a pane drew no block at all"
        assert float(fields["per_piece_ms"]) > 0.0 and float(fields["pieces_per_frame"]) > 0.0
        assert float(fields["total_ms"]) > 0.0
    with capsys.disabled():
        label = "software-rendered Xvfb" if window.where == "xvfb" else "the session's display"
        print(f"\nstress page streaming through imtypeset, {label} figures:")
        for line in lines:
            print("  " + line)


# ----------------------------------------------------------------------
# Through imtypeset: real frames, no window, in a child that has the library
# ----------------------------------------------------------------------

_HEADLESS = r"""
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.ui.app import App
from imscribe.ui.pages import stress as page

ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 800.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()

class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        self.now += 0.001
        return self.now

def frames(app, count, seconds=1.0 / 60.0):
    for _ in range(count):
        io.delta_time = seconds
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(1300.0, 800.0))
            imgui.begin("##imscribe-stress-page-test", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                app.gui()
            finally:
                imgui.end()
        finally:
            imgui.render()

def opened(spec, clock=True, source=None):
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    made = app.page("stress")
    if source is not None:
        made.stress.source = source
    if clock:
        made.stress.timer = Clock()
    return app, made

def pane_of(pane):
    view = pane.view
    ready = typesetter.ready()
    return {
        "view": type(view).__name__, "stream": type(pane.stream).__name__,
        "sync": len(pane.sync.samples), "draw": len(pane.draw.samples),
        "sync_ms": pane.sync.median_ms, "draw_ms": pane.draw.median_ms,
        "vertices": pane.vertices, "total": pane.blocks_total,
        "drawn": pane.blocks_drawn, "not_drawn": pane.blocks_not_drawn, "fed": pane.fed,
        "laps": pane.laps, "width": pane.width_px,
        "edits": dict(view.edits), "blocks": len(view.blocks),
        "owns": view.owns_selection, "selected": len(view.selected_text()) if ready else -1,
        "document": view.native_document is not None,
    }

def told(made):
    stress = made.stress
    return {
        "renderer": made.renderer, "reason": made.reason, "failed": made.failed,
        "frames": made.frames, "panes": [pane_of(pane) for pane in stress.panes],
        "sync_ms": stress.sync_ms, "draw_ms": stress.draw_ms, "total_ms": stress.total_ms,
        "vertices": stress.vertices, "drawn": stress.blocks_drawn,
        "not_drawn": stress.blocks_not_drawn,
        "readouts": list(page.readouts(stress)), "report": made.report(),
    }

# 1. Four finished panes, five frames, on the fake timer. No pane before the first frame.
app, made = opened("stress:4")
report["unmade"] = len(made.stress.panes)
frames(app, 5)
report["four"] = told(made)
report["shared"] = len({id(pane.view.blocks[0]) for pane in made.stress.panes})

# 2. One copy against twenty: what a pane draws does not grow with the document.
app, made = opened("stress:4,x20")
frames(app, 2)
report["twenty"] = told(made)
# And a document that fits is all drawn.
app, made = opened("stress:1", source="One line.\n")
frames(app, 2)
report["short"] = told(made)

# 3. Streaming, a twentieth of a second a frame: text arrives on every frame.
app, made = opened("stress:2,streaming")
frames(app, 10, seconds=0.05)
report["streaming"] = told(made)
# The count changed alone keeps the panes there were; then a pane run past its
# end starts again.
first = made.stress.panes[0].view
made.stress.count = 3
frames(app, 1, seconds=0.05)
report["grown"] = [len(made.stress.panes), made.stress.panes[0].view is first]
pane = made.stress.panes[0]
pane.stream.append("".join(pane.pieces[pane.fed:]))
pane.fed = len(pane.pieces)
frames(app, 2, seconds=0.05)
again = made.stress.panes[0]
report["lapped"] = {"laps": again.laps, "fresh": again.view is not first,
                    "closed": first.native_document is None, "fed": again.fed,
                    "kept_medians": again.draw is pane.draw}
# Fewer panes, then another kind of pane: each view that leaves gives its document back.
views = [each.view for each in made.stress.panes]
made.stress.count = 1
frames(app, 1, seconds=0.05)
dropped = [view.native_document is None for view in views]
made.stress.streaming = False
frames(app, 1, seconds=0.05)
report["dropped"] = {"fewer": dropped, "rebuilt": views[0].native_document is None,
                     "now": [type(each.view).__name__ for each in made.stress.panes]}

# 4. Select all in every pane.
app, made = opened("stress:3,selected")
frames(app, 3)
report["selected"] = told(made)
made.stress.select_all = False
for pane in made.stress.panes:
    pane.view.clear_selection()
frames(app, 1)
report["cleared"] = [len(pane.view.selected_text()) for pane in made.stress.panes]

# After the body that needs the library, and before the two sections that take it away.
report["after"] = {"module": typesetter.module() is not None, "ready": typesetter.ready(),
                   "reason": typesetter.reason()}

# 5. A draw that raises with the library still ready: the page keeps the sentence, finishes
# the frame without an error, and is the one line from the next frame on.
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView
real_draw = TypesetView.draw
def failing(self, **kwargs):
    raise TypesetUnavailable("raised by the test")
app, made = opened("stress:4")
frames(app, 3)
TypesetView.draw = failing
frames(app, 1)
TypesetView.draw = real_draw
at_once = told(made)
shown = []
real_say = page.say_why_not
def saying(reason):
    shown.append(reason)
    real_say(reason)
page.say_why_not = saying
frames(app, 4)
page.say_why_not = real_say
report["middraw"] = {"at_once": at_once, "later": told(made), "shown": shown,
                     "ready": typesetter.ready(), "current": type(app.page("stress")).__name__}

# 6. Last, because it is for the rest of the process: the library switched off.
app, made = opened("stress:4,streaming")
frames(app, 6, seconds=0.05)
before = told(made)
fed = [pane.fed for pane in made.stress.panes]
typesetter.disable("switched off by the test")
frames(app, 1, seconds=0.05)
after = told(made)
frames(app, 4, seconds=0.05)
report["off"] = {"before": before, "after": after, "later": told(made),
                 "fed": [fed, [pane.fed for pane in made.stress.panes]],
                 "ready": typesetter.ready()}
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    """
    `_HEADLESS` run once in a child that has the library; skipped without the variable.

    The child says whether the library was in use and ready before its body
    and again after the part of it that draws.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    done = subprocess.run(
        [sys.executable, "-B", "-c", _HEADLESS],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout + done.stderr
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    assert report["module"], f"imtypeset is not in use in the child: {report['reason']}"
    assert report["load_fonts"] and report["ready"], report
    after = report["after"]
    assert after["module"] and after["ready"], f"the library was lost under the body: {after}"
    return report


def test_every_pane_is_sampled_once_a_frame_in_two_parts(typeset: dict[str, Any]) -> None:
    """
    The fake timer is read three times a pane a frame -- before the sync,
    between the two, after the draw -- so each sample is exactly 1 ms of `sync`
    and 1 ms of `draw`, and the totals are those times the number of panes.
    Four `TypesetView`s over ONE parse of the sample, each with a document of
    its own, handed to the library once and not again; none of them existed
    before the first frame.
    """
    four = typeset["four"]
    assert typeset["unmade"] == 0
    assert four["renderer"] == "TypesetView" and four["reason"] == "" and four["failed"] == ""
    assert len(four["panes"]) == 4 and typeset["shared"] == 1
    for pane in four["panes"]:
        assert pane["view"] == "TypesetView" and pane["stream"] == "NoneType"
        assert pane["sync"] == pane["draw"] == 5 and pane["document"] is True
        assert pane["sync_ms"] == pytest.approx(1.0) and pane["draw_ms"] == pytest.approx(1.0)
        assert pane["edits"] == {"set": 1, "replace": 0, "append": 0}
    assert four["sync_ms"] == pytest.approx(4.0) and four["draw_ms"] == pytest.approx(4.0)
    assert four["total_ms"] == pytest.approx(8.0)
    # The words: what is timed, and vertices and blocks.
    lines = four["readouts"]
    assert "4 panes (TypesetView, finished)" in lines[0]
    assert "parse and edit 4.00 ms  +  layout and draw 4.00 ms  =  8.00 ms" in lines[0]
    assert lines[2].startswith("vertices submitted ") and "blocks drawn " in lines[2]
    assert "each pane has its own document in the library" in lines[3]
    assert four["report"].startswith("frames=5 panes=4 streaming=0 length=1 samples=5 ")
    assert four["report"].endswith(" renderer=TypesetView") and "glyphs=" not in four["report"]


def test_the_vertex_and_block_counts_are_the_views_own(typeset: dict[str, Any]) -> None:
    """
    For every pane, drawn plus not drawn is the document's blocks; at twenty
    copies most are not drawn -- which is the case that shows the counter is
    not simply reporting everything as drawn -- and what a pane submits does
    not grow with the document (a count, and the reason the length control
    exists). A document that fits its pane is all drawn.
    """
    one, twenty = typeset["four"], typeset["twenty"]
    for told in (one, twenty):
        assert told["vertices"] == sum(pane["vertices"] for pane in told["panes"]) > 0
        assert told["drawn"] == sum(pane["drawn"] for pane in told["panes"])
        assert told["not_drawn"] == sum(pane["not_drawn"] for pane in told["panes"])
        for pane in told["panes"]:
            assert pane["total"] == pane["blocks"] == pane["drawn"] + pane["not_drawn"]
            assert pane["drawn"] > 0
    assert all(pane["total"] > 500 for pane in twenty["panes"])
    assert all(0 < pane["drawn"] < pane["total"] / 4 for pane in twenty["panes"])
    assert twenty["vertices"] < 2 * one["vertices"]
    assert twenty["not_drawn"] > 10 * max(1, one["not_drawn"])
    (short,) = typeset["short"]["panes"]
    assert (short["total"], short["drawn"], short["not_drawn"]) == (1, 1, 0)


def test_streaming_panes_take_an_edit_a_frame_start_again_and_let_go(
    typeset: dict[str, Any],
) -> None:
    """
    A pane that starts again, a pane dropped by the count, and every pane
    replaced by a change of kind: each view that left closed its document.
    """
    streaming = typeset["streaming"]
    assert "2 panes (TypesetStreamView, text arriving)" in streaming["readouts"][0]
    for pane in streaming["panes"]:
        assert pane["view"] == "TypesetStreamView" and pane["stream"] == "MarkdownStream"
        # Two pieces a frame for ten frames; an edit on each frame a block changed.
        assert sum(pane["edits"].values()) >= 9 and pane["edits"]["set"] == 1
        assert pane["fed"] > 0 and pane["vertices"] > 0 and pane["sync"] == 10
    assert "per piece of text: none taken" not in " ".join(streaming["readouts"])
    assert typeset["grown"] == [3, True]
    lapped = typeset["lapped"]
    assert lapped["laps"] == 1 and lapped["fresh"] is True and lapped["kept_medians"] is True
    assert lapped["closed"] is True, "the pane that left kept its document in the library"
    dropped = typeset["dropped"]
    assert dropped["fewer"] == [False, True, True] and dropped["rebuilt"] is True
    assert dropped["now"] == ["TypesetView"]


def test_select_all_selects_every_pane(typeset: dict[str, Any]) -> None:
    """
    A selection belongs to one view at a time, so after a frame only the last
    pane drawn owns one; that every pane drew one is in the vertices, which a
    selection adds to, because the page selects each again just before its draw.
    """
    selected, plain = typeset["selected"], typeset["four"]
    panes = selected["panes"]
    assert panes[-1]["owns"] is True and panes[-1]["selected"] > 1000
    assert all(pane["vertices"] > plain["panes"][0]["vertices"] for pane in panes)
    assert typeset["cleared"] == [0, 0, 0]


def test_when_a_draw_raises_the_page_is_the_one_line_from_the_next_frame_on(
    typeset: dict[str, Any],
) -> None:
    """
    `TypesetView.draw` made to raise `TypesetUnavailable` for one frame, with
    the library ready throughout. The first pane's draw raised having sampled
    nothing; that frame ended without an error; the four frames after it are
    `say_why_not` with what was raised, although the library could draw again,
    and no pane is sampled in them. The page is still the page.
    """
    told = typeset["middraw"]
    at_once, later = told["at_once"], told["later"]
    assert told["ready"] is True and told["current"] == "StressPage"
    assert at_once["failed"] == "raised by the test" == at_once["reason"]
    assert at_once["renderer"] == "none" and at_once["frames"] == 4
    assert [pane["draw"] for pane in at_once["panes"]] == [3, 3, 3, 3]
    assert told["shown"] == ["raised by the test"] * 4
    assert later["frames"] == 8 and [pane["draw"] for pane in later["panes"]] == [3, 3, 3, 3]
    assert later["report"].endswith(" renderer=none")


def test_when_the_library_is_switched_off_the_page_is_the_one_line(
    typeset: dict[str, Any],
) -> None:
    """
    `typesetter.disable` between two frames with four panes streaming. The
    next frame is the line with the reason; nothing is fed or sampled, then or
    later, and the page raised nothing.
    """
    off = typeset["off"]
    before, after, later = off["before"], off["after"], off["later"]
    assert off["ready"] is False
    assert before["renderer"] == "TypesetView" and len(before["panes"]) == 4
    assert after["renderer"] == "none" and "switched off by the test" in after["reason"]
    assert after["failed"] == "", "nothing was raised: the page asked `ready()` first"
    assert off["fed"][0] == off["fed"][1]
    assert [pane["draw"] for pane in later["panes"]] == [6, 6, 6, 6]
    assert later["frames"] == before["frames"] + 5
    assert later["report"].endswith(" renderer=none")

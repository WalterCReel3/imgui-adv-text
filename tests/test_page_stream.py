"""
The Stream page: its replay logic on a clock advanced by hand, the one line it
draws without the library, and the page itself in frames and in a window.

**Four levels, stated so nobody reads more into a green run than is there.**

1. `Session` and `Lane` with no ImGui and no library: the pieces, the clock,
   the controls, the readouts' words. Time is whatever the test passes in. A
   lane's bookkeeping around its view (when a sample is taken, what a restart
   lets go of) is run over a stand-in for the view, `_View`, which is honest
   about being one: it answers `sync` from the stream's revision and draws
   nothing.
2. The page with no library, in frames of a real `ImGuiContext` with no
   backend and once in a real window: it draws one line saying why not, and
   nothing else. This is all the pytest process can draw:
   `advtext.typesetter.ready()` is never true there, also under
   `make test TYPESET=1`.
3. The page as imtypeset draws it, in one child of real ImGui frames with no
   window (`_HEADLESS`): the session alone, for what it loads; the page
   through `App.gui`, streaming, to the end, idle, restarted, at another
   width; a draw made to raise; and last, the library switched off in the
   middle of a replay. The child says whether `typesetter.module()` and
   `ready()` held THERE, before the body and after it.
4. The real app in a real window (`tests/conftest.py::window`) with the
   library, at a token rate slow enough that the stream spans many edits.

Levels 3 and 4 are skipped, with the reason, when `IMTYPESET_LIBRARY` is not
set.

**Nothing here judges how a stream looks.** The counters report change and
cost (`docs/visual-review.md`), and one test holds the page's own wording to
that.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from advtext import typesetter
from advtext.theme import Theme
from advtext.typeset_markdown import (
    MarkdownCode,
    MarkdownConverter,
    MarkdownStream,
    MarkdownTable,
    MarkdownText,
    parse_markdown,
)
from advtext.ui import pages
from advtext.ui.pages import PageContext
from advtext.ui.pages import stream as page
from advtext.ui.pages.stream import SOURCES, Cost, Lane, Session, readouts, tokens
from advtext.ui.pages.typeset import NOT_DRAWING, why_not

if TYPE_CHECKING:
    from conftest import Window

KEEP, RESET = page.POLICIES
FRAME = 1.0 / 60.0

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_SKIP = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)

PROSE = (
    "\n\n".join(
        f"Paragraph {n} is plain prose and long enough to be broken onto several lines at "
        f"the widths used here, which is the only way a settled line exists to be watched "
        f"while later words arrive after it. It says nothing else of any interest and it "
        f"has no markup of any kind in it, so every one of its lines is filled "
        f"and left alone. Sentence {n} ends here."
        for n in range(1, 6)
    )
    + "\n"
)
"""
Five paragraphs, about 320 pieces. No blank line after the last, so it commits at the close.
"""


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


def _source(key: str) -> page.Source:
    return next(entry for entry in SOURCES if entry.key == key)


def _session(theme: Theme, text: str | None = PROSE, **fields: Any) -> Session:
    return Session(theme=theme, text=text, **fields)


class _Clock:
    """
    A timer that advances one millisecond every time it is read.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


class _View:
    """
    What stands where `TypesetStreamView` does in the tests of a lane's own bookkeeping.

    It reads the stream as the real view's `sync` does (by `revision`), holds
    no document and draws nothing. Nothing it answers is a fact about the
    library; the tests that use it assert only what `Lane` does around it.
    """

    made: list[_View] = []

    def __init__(self, stream: MarkdownStream, *, palette: object = None) -> None:
        self.stream = stream
        self.edits = {"set": 0, "replace": 0, "append": 0}
        self.origin = None
        self.closed = False
        self._revision: int | None = None
        self.sync()
        _View.made.append(self)

    @property
    def blocks(self) -> tuple[object, ...]:
        return tuple(self.stream.blocks)

    def sync(self) -> bool:
        revision = self.stream.revision
        changed = revision != self._revision
        self._revision = revision
        return changed

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch) -> type[_View]:
    """
    `_View` in the page module's name for the view, for one test.
    """
    monkeypatch.setattr(page, "TypesetStreamView", _View)
    monkeypatch.setattr(_View, "made", [])
    return _View


# ----------------------------------------------------------------------
# The sources
# ----------------------------------------------------------------------


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.key)
def test_every_source_is_a_file_and_its_pieces_join_back_to_it(source: page.Source) -> None:
    """
    A missing file would silently replay `FALLBACK` under the source's label.
    """
    text = pages.demo_text(source.path)
    assert text is not None, f"demo/{source.path} is missing"
    assert source.text() == text != page.FALLBACK
    pieces = tokens(text)
    assert "".join(pieces) == text
    assert max(len(piece.strip()) for piece in pieces) <= 4
    assert len(pieces) > 100


def test_the_sources_are_the_cases_their_labels_say(theme: Theme) -> None:
    """
    Each hard case is in its file, counted from the parsed document (the
    direct path's blocks, which is what the page's streams make) and not from
    the file's own prose about itself.
    """

    def blocks(key: str) -> tuple[Any, ...]:
        return parse_markdown(_source(key).text(), theme).blocks

    tables = [block for block in blocks("table") if isinstance(block, MarkdownTable)]
    assert [len(table.rows) for table in tables] == [30]

    fences = [block for block in blocks("code") if isinstance(block, MarkdownCode)]
    assert [len(fence.text.splitlines()) for fence in fences] == [600]

    assert all(isinstance(block, MarkdownText) for block in blocks("prose"))
    text = _source("prose").text()
    assert not re.search(r"[*_`\[\]#|]", text), "the plain prose has markup in it"

    steps = blocks("steps")
    indented = [b for b in steps if isinstance(b, MarkdownCode) and b.left_indent > 0]
    assert len(indented) >= 3, "the steps have no fences under their numbers"
    assert re.search(r"^\d+\. .*\n\n   \S", _source("steps").text(), re.MULTILINE)

    links = _source("links").text()
    longest = max(links.split(), key=len)
    assert longest.startswith("https://")
    assert re.search(r"^\[\w+\]: https://", links, re.MULTILINE), "no reference definitions"
    assert re.search(r"\]\[\w+\]", links), "no reference-style link"


def test_reference_links_are_shown_as_typed_while_streaming(theme: Theme) -> None:
    """
    The property the links source is there to show, checked on the finished
    streams with no library: the bracketed words are still in the text each
    block is described with, which is what the library is given to set.
    """
    session = _session(theme, text=None, source=_source("links"))
    session.finish()
    for lane in session.lanes:
        described = MarkdownConverter(lane.stream.theme).describe(lane.stream.blocks)
        text = " ".join(" ".join(described.texts).split())
        assert "[the changelog][changes]" in text, lane.name
        assert "[the issue tracker][issues]" in text, lane.name
        # The inline link beside them is a link: its address is not set as text.
        assert "the project page" in text and "(https://example.org/project)" not in text


# ----------------------------------------------------------------------
# The clock and the controls: no library, no ImGui
# ----------------------------------------------------------------------


def test_a_session_needs_no_library_and_its_lanes_are_the_two_policies(theme: Theme) -> None:
    """
    Built in the pytest process, where the library is not loaded: two lanes,
    each a `MarkdownStream` and no view. `KEEP_STREAMED` has one theme, ragged;
    `RESET` reads its tail in that ragged theme and its commits in the page's.
    """
    session = _session(theme)
    assert [lane.name for lane in session.lanes] == [KEEP, RESET]
    assert session.lane(KEEP) is session.lanes[0] and session.lane(RESET) is session.lanes[1]
    with pytest.raises(KeyError):
        session.lane("NEITHER")
    with pytest.raises(ValueError, match="NEITHER"):
        Lane("NEITHER", theme)
    ragged = page.ragged(theme)
    assert ragged is not theme and page.ragged(ragged) is ragged
    keep, reset = session.lanes
    assert all(type(lane.stream) is MarkdownStream and lane.view is None for lane in session.lanes)
    assert keep.stream.theme == ragged and keep.stream.live_theme == ragged
    assert reset.stream.theme is theme and reset.stream.live_theme == ragged
    assert all(lane.edits == {"set": 0, "replace": 0, "append": 0} for lane in session.lanes)
    assert "imtypeset" not in sys.modules or not typesetter.ready()


def test_the_clock_decides_how_many_pieces_arrive_and_fractions_are_carried(
    theme: Theme,
) -> None:
    session = _session(theme, tokens_per_second=40.0)
    fed = [session.advance(FRAME) for _ in range(60)]
    assert sum(fed) == 40, "sixty sixtieths of a second at forty a second is forty pieces"
    assert set(fed) == {0, 1}, "pieces arrived in bursts although the rate is under one a frame"
    assert session.fed == 40


def test_both_lanes_are_fed_the_same_pieces_at_every_step(theme: Theme) -> None:
    session = _session(theme, tokens_per_second=600.0)
    seen = 0
    while not session.done:
        session.tick(FRAME)
        keep, reset = session.lane(KEEP), session.lane(RESET)
        assert keep.stream.source == reset.stream.source == "".join(session.pieces[: session.fed])
        assert keep.taken == reset.taken == session.fed
        seen += 1
    assert seen > 5
    assert all(lane.stream.closed for lane in session.lanes)
    assert session.lane(KEEP).stream.source == PROSE
    # No view was made by ticking, so nothing was counted: a count needs a draw.
    assert all(lane.view is None and lane.moved == 0 for lane in session.lanes)
    assert all(lane.parse.count == 0 for lane in session.lanes)


def test_the_fixture_is_long_enough_for_the_tests_that_stop_part_way() -> None:
    """
    Several tests tick a fixed number of frames and expect to be mid-stream.
    """
    assert len(tokens(PROSE)) > 300


def test_pausing_stops_the_clock_and_a_step_feeds_exactly_one_piece(theme: Theme) -> None:
    session = _session(theme, tokens_per_second=600.0)
    session.advance(FRAME)
    assert session.fed == 10
    session.paused = True
    assert session.advance(10.0) == 0 and session.fed == 10

    assert session.step() == 1 and session.fed == 11
    assert session.step(3) == 3 and session.fed == 14
    assert session.paused

    session.paused = False
    # Nothing was owed for the ten seconds spent paused.
    assert session.advance(FRAME) == 10 and session.fed == 24


def test_a_step_from_running_pauses(theme: Theme) -> None:
    session = _session(theme)
    assert not session.paused
    session.step()
    assert session.paused and session.fed == 1


def test_stepping_past_the_end_closes_the_streams_and_feeds_no_more(theme: Theme) -> None:
    session = _session(theme)
    total = len(session.pieces)
    assert session.step(total + 50) == total
    assert session.done
    assert session.step() == 0 and session.advance(1.0) == 0
    # Five paragraphs, all committed at the close, under either policy.
    for lane in session.lanes:
        assert len(lane.stream.committed) == len(lane.stream.blocks) == 5


def test_restart_begins_the_same_source_again_with_every_count_at_zero(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    The counts a restart puts back, and what it lets go of: each lane's view
    is closed (its document goes back to the library) and dropped, and the
    stream is a new one. Over the stand-in view; the real one is restarted in
    the child (`test_on_the_typeset_page_a_width_is_not_a_move_and_the_buttons_work`).
    """
    session = _session(theme, tokens_per_second=900.0, timer=_Clock())
    while not session.done:
        session.advance(FRAME)
        for lane in session.lanes:
            lane.sync(make=True)
    reset = session.lane(RESET)
    assert reset.parse.count > 5 and reset.taken == len(session.pieces)
    old_view, old_stream = reset.view, reset.stream
    assert isinstance(old_view, _View) and not old_view.closed

    session.restart()
    assert (session.fed, session.done) == (0, False)
    for lane in session.lanes:
        assert (lane.moved, lane.moves, lane.taken, lane.vertices) == (0, [], 0, 0)
        assert (lane.parse.count, lane.draw.count) == (0, 0)
        assert lane.stream.source == "" and lane.view is None
    assert old_view.closed and reset.stream is not old_stream
    assert all(view.closed for view in stand_in.made)
    assert session.tokens_per_second == 900.0
    while not session.done:
        session.tick(FRAME)
    assert session.lane(KEEP).stream.source == PROSE


def test_choosing_a_source_replays_that_one_from_the_start(theme: Theme) -> None:
    session = _session(theme)
    session.step(20)
    session.choose(_source("prose"))
    assert session.fed == 0 and session.source.key == "prose"
    assert "".join(session.pieces) == _source("prose").text()
    assert all(lane.stream.source == "" for lane in session.lanes)


# ----------------------------------------------------------------------
# The counter and the cost split
# ----------------------------------------------------------------------


def test_the_counter_never_counts_the_line_being_written() -> None:
    a, b, c = ("a", 0), ("b", 1), ("c", 2)
    grown = ("c and more", 2)
    assert page.changed_lines([a, b, c], [a, b, grown]) == []
    assert page.changed_lines([a, b, c], [a, ("b moved", 1), grown]) == [b]
    assert page.changed_lines([], [a]) == []


def test_cost_keeps_the_latest_the_mean_and_the_largest() -> None:
    cost = Cost()
    assert (cost.last_ms, cost.mean_ms, cost.worst_ms, cost.count) == (0.0, 0.0, 0.0, 0)
    for seconds in (0.002, 0.006, 0.001):
        cost.add(seconds)
    assert cost.count == 3
    assert cost.last_ms == pytest.approx(1.0)
    assert cost.mean_ms == pytest.approx(3.0)
    assert cost.worst_ms == pytest.approx(6.0)


def test_a_sync_that_took_text_is_one_sample_and_an_idle_one_is_none(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    The fake timer ticks a millisecond a reading and `Lane.sync` reads it
    twice when a block changed, so each sample is exactly one millisecond.
    Making the view is the first sync, and is a sample only if there was text.
    Nothing is recorded as drawn, because nothing was.
    """
    lane = Lane(KEEP, theme, timer=_Clock())
    assert lane.sync() is False and lane.view is None, "a sync made a view without being asked"

    lane.take(["Some ", "text"])
    assert lane.sync(make=True) is True and isinstance(lane.view, _View)
    assert lane.parse.count == 1 and lane.parse.last_ms == pytest.approx(1.0)

    assert lane.sync() is False and lane.sync(make=True) is False
    assert lane.parse.count == 1

    lane.take([" and", " more"])
    assert lane.sync() is True
    assert lane.parse.count == 2 and lane.parse.mean_ms == pytest.approx(1.0)
    assert lane.draw.count == 0, "nothing was drawn, so nothing may be recorded as drawn"
    # No draw, so no origin, so nothing to count and no mark.
    assert lane.observe() == 0 and lane.moved == 0

    empty = Lane(RESET, theme, timer=_Clock())
    assert empty.sync(make=True) is False and empty.parse.count == 0


def test_several_pieces_in_one_frame_are_one_sample(theme: Theme, stand_in: type[_View]) -> None:
    session = _session(theme, tokens_per_second=1200.0, timer=_Clock())
    for lane in session.lanes:
        lane.sync(make=True)
    session.tick(FRAME)
    assert session.fed == 20
    for lane in session.lanes:
        assert lane.parse.count == 1 and lane.taken == 20


# ----------------------------------------------------------------------
# The words on the page
# ----------------------------------------------------------------------


def test_the_readout_counts_committed_and_live_blocks(theme: Theme) -> None:
    session = _session(theme, tokens_per_second=600.0)
    while len(session.lane(KEEP).stream.committed) < 1:
        session.tick(FRAME)
    keep = session.lane(KEEP)
    committed = len(keep.stream.committed)
    live = len(keep.stream.blocks) - committed
    assert committed >= 1 and live >= 1 and not session.done
    counts, _ = keep.describe()
    assert f"blocks: {committed} committed, {live} live" in counts
    session.finish()
    counts, _ = keep.describe()
    assert "blocks: 5 committed, 0 live" in counts


def test_the_readouts_state_counts_and_costs_and_no_judgement(
    theme: Theme, stand_in: type[_View]
) -> None:
    """
    `docs/visual-review.md`, rule 1, applied to the page's own words: a counter
    may say what changed and what it cost and may not say whether that is good.
    """
    session = _session(theme, tokens_per_second=600.0, timer=_Clock())
    for lane in session.lanes:
        lane.sync(make=True)
    while not session.done:
        session.tick(FRAME)
    lines = readouts(session)
    assert len(lines) == 1 + 2 * len(session.lanes)
    assert f"piece {len(session.pieces)} of {len(session.pieces)}" in lines[0]
    assert "finished" in lines[0]
    assert lines[1].startswith("KEEP_STREAMED") and lines[3].startswith("RESET")
    assert "settled lines moved: 0 (in 0 of 0 edits)" in lines[1]
    assert "parse and edit 1.00 / 1.00 / 1.00" in lines[2]
    assert "layout and draw 0.00 / 0.00 / 0.00" in lines[2]
    text = " ".join((*lines, page.RENDERER_LINE)).lower()
    for word in ("better", "worse", "good", "bad", "smooth", "jank", "clean", "crisp", "stable"):
        assert word not in text, f"a readout says {word!r}"


def test_the_report_is_counts(theme: Theme) -> None:
    session = _session(theme, tokens_per_second=600.0)
    session.finish()
    lines = page.report(session, 7)
    assert lines[0].startswith("frames=7 fed=") and "done=1" in lines[0]
    assert lines[1].startswith("KEEP_STREAMED edits=0 set=0 append=0 replace=0 moved=0 ")
    assert lines[2].startswith("RESET edits=0 ")
    assert all(" blocks=5 committed=5 vertices=0 whole=1" in line for line in lines[1:])


# ----------------------------------------------------------------------
# The page with no library: one line, and nothing else
# ----------------------------------------------------------------------


def test_the_page_is_discovered_after_the_original_five() -> None:
    from advtext.ui.app import parse_tab_request

    found = pages.require()
    names = [entry.name for entry in found.pages]
    assert "Stream" in names and names.index("Stream") >= 5
    spec = found.find("stream")
    assert spec is page.PAGE
    for request in spec.shot_specs():
        assert parse_tab_request(request, found).tab == "stream"


def _context(name: str, *options: str, count: int | None = None) -> PageContext:
    """
    A context as `--tab NAME:options,count` gives one, without the app's parser.
    """
    return PageContext.build(request_page=name, request_options=options, request_count=count)


def test_the_launch_options_pick_the_source_the_rate_and_the_finished_state() -> None:
    plain = page.StreamPage(_context("stream"))
    assert plain.session.source is SOURCES[0]
    assert plain.session.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND
    assert plain.session.fed == 0

    made = page.StreamPage(_context("stream", "table", count=250))
    assert made.session.source.key == "table" and made.session.tokens_per_second == 250.0

    done = page.StreamPage(_context("stream", "prose", "done"))
    assert done.session.done and done.session.fed == len(done.session.pieces)

    other = page.StreamPage(_context("document", count=7))
    assert other.session.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND


def _frames(draw: Any, count: int, seconds: float = FRAME) -> Any:
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
            imgui.begin("##advtext-stream-page-test", None, imgui.WindowFlags_.no_title_bar.value)
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
    of anything else the page draws with: no control, no caption, no pane. The
    clock does not run and no view is made. Then the same frames with nothing
    patched, so the line itself reaches ImGui.
    """
    assert not typesetter.ready()
    made = page.StreamPage(_context("stream", "prose", count=600))
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the page drew more than the one line")

    monkeypatch.setattr(page, "caption", never)
    monkeypatch.setattr(page.StreamPage, "_controls", never)
    monkeypatch.setattr(Lane, "show", never)
    _frames(made.draw, 4)
    assert said == [why_not()] * 4 and said[0]
    assert made.frames == 4 and made.failed == "" and made.reason == why_not()
    assert made.renderer == "none"
    assert made.session.fed == 0, "the clock ran with nothing drawing"
    assert all(lane.view is None for lane in made.session.lanes)
    report = made.report()
    assert report[0].endswith(" renderer=none") and "fed=0 " in report[0]

    monkeypatch.undo()
    imgui = _frames(made.draw, 2)
    assert made.frames == 6 and imgui.get_current_context() is not None


def test_the_line_names_imtypeset_and_the_reason() -> None:
    """
    What `say_why_not` is given becomes "imtypeset is not drawing: <reason>":
    the page's own `reason`, which without the library is `why_not()`'s
    sentence and after a failure is what the failure said, for good.
    """
    from advtext.ui.pages.typeset import not_drawing

    made = page.StreamPage(_context("stream"))
    assert not_drawing(made.reason).startswith(NOT_DRAWING + ": ")
    made.failed = "the library went away"
    assert made.reason == "the library went away" and made.renderer == "none"


@pytest.mark.parametrize("how", ["raised in a frame", "not ready any more"])
def test_a_page_that_gives_up_closes_its_views_and_keeps_its_session(
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
    made = page.StreamPage(_context("stream"))
    made.session.step(3)
    for lane in made.session.lanes:
        lane.sync(make=True)
    views = [lane.view for lane in made.session.lanes]
    assert len(views) == 2 and not any(view.closed for view in views)
    fed = made.session.fed

    if how == "raised in a frame":

        def unavailable(self: page.StreamPage, imgui: Any) -> None:
            raise page.TypesetUnavailable("switched off under the frame")

        monkeypatch.setattr(page.StreamPage, "_frame", unavailable)
    else:
        ready["reason"] = "switched off by another page"
    _frames(made.draw, 1)

    assert made.renderer == "none"
    assert [view.closed for view in views] == [True, True]
    assert [lane.view for lane in made.session.lanes] == views and made.session.fed == fed
    assert "renderer=none" in made.report()[0]


def test_a_typeset_unavailable_out_of_a_frame_stays_in_the_page_and_anything_else_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The page's handler, with the library's readiness and the frame both
    stood in for: `TypesetUnavailable` out of the frame is kept as the reason
    and the next frame is the one line; any other exception is a bug and is
    not caught.
    """
    made = page.StreamPage(_context("stream"))
    monkeypatch.setattr(page, "why_not", lambda: "")
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)
    calls: list[str] = []

    def unavailable(self: page.StreamPage, imgui: Any) -> None:
        calls.append("frame")
        raise page.TypesetUnavailable("switched off under the frame")

    monkeypatch.setattr(page.StreamPage, "_frame", unavailable)
    _frames(made.draw, 3)
    assert calls == ["frame"], "the frame was tried again after the library had failed"
    assert made.failed == "switched off under the frame" and said == [made.failed] * 2
    assert made.frames == 3 and made.renderer == "none"

    def broken(self: page.StreamPage, imgui: Any) -> None:
        raise ZeroDivisionError("a bug")

    other = page.StreamPage(_context("stream"))
    monkeypatch.setattr(page.StreamPage, "_frame", broken)
    imgui = pytest.importorskip("imgui_bundle").imgui
    with pytest.raises(ZeroDivisionError):
        other.draw()
    assert other.failed == "" and imgui is not None


# ----------------------------------------------------------------------
# What the module imports, at import and ever
# ----------------------------------------------------------------------

OLD_MODULES = (
    "advtext.stream",
    "advtext.markdown",
    "advtext.mathtext",
    "advtext.style",
    "advtext.spans",
    "advtext.fontlib",
    "advtext.units",
    "advtext.backends",
    "advtext.ui.bare_view",
    "advtext.ui.stream_view",
    "advtext.ui.document_view",
    "advtext.ui.diff_view",
    "advtext.ui.units",
    "advtext.ui.composition",
)
"""
What a page of this task may not import anywhere in its source, a function's
body included: the old stream, the old converter, the old views, the old draw
backend, and the core modules they stand on.
"""


def imports_of(path: Path) -> set[str]:
    """
    Every module `path` imports, at any depth of its source: `import a.b` and `from a.b import c`.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_the_page_imports_nothing_of_the_old_core_or_the_old_views_even_lazily() -> None:
    """
    Read from the source, so an import inside a function counts.
    """
    found = imports_of(_ROOT / "advtext" / "ui" / "pages" / "stream.py")
    assert "advtext.ui.typeset_stream_view" in found and "advtext.typeset_markdown" in found
    for name in found:
        for old in OLD_MODULES:
            assert name != old and not name.startswith(old + "."), name


_CLOSURE = r"""
import json, sys
import advtext.ui.pages.stream
print("REPORT " + json.dumps(sorted(name for name in sys.modules if name.startswith("advtext"))))
"""


def test_importing_the_page_loads_none_of_the_old_core() -> None:
    """
    None of it: `advtext.units` and `advtext.fontmetrics` were the floor of
    everything that names a `Theme` until T5-B2
    (`tests/test_typeset_closure.py`, whose list of the old core this reads).
    """
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
    assert "advtext.ui.pages.stream" in loaded and "advtext.ui.typeset_stream_view" in loaded
    assert loaded & OLD_CORE == THEME, sorted(loaded & OLD_CORE)
    for name in ("advtext.stream", "advtext.markdown", "advtext.style"):
        assert name not in loaded, name


# ----------------------------------------------------------------------
# A real window
# ----------------------------------------------------------------------

SLOW = """
import sys
import time

from imgui_bundle import hello_imgui

from advtext import typesetter
from advtext.ui import app as advtext_app

WANT_LIBRARY = sys.argv[1] == "with"
state = {"frames": 0, "streaming": 0, "spent": 0.0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        # No operator will wake an idling app, and at the idle frame rate a
        # frame's worth of tokens is most of a paragraph.
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    began = time.perf_counter()
    real_gui(self)
    spent = time.perf_counter() - began
    state["frames"] += 1
    made = self.page("stream")
    if state["frames"] == 2 and WANT_LIBRARY:
        # In the child, so that this cannot pass with nothing drawn.
        assert typesetter.module() is not None, "imtypeset is not in use: " + typesetter.reason()
        assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
    if not made.session.done:
        state["streaming"] += 1
        state["spent"] += spent
    over = made.session.done if WANT_LIBRARY else state["frames"] >= 8
    if over or state["frames"] >= 20000:
        # A few frames more, so the last layout is drawn before the report.
        state.setdefault("left", 3)
        state["left"] -= 1
        if state["left"] <= 0:
            for line in made.report():
                print(line)
            # After the body: what was true when the last frame had been drawn.
            print(
                "child imported=%d module=%d ready=%d page_frames=%d streaming_frames=%d "
                "gui_ms=%.3f views=%d"
                % (
                    "imtypeset" in sys.modules,
                    WANT_LIBRARY and typesetter.module() is not None,
                    typesetter.ready(),
                    made.frames,
                    state["streaming"],
                    1000.0 * state["spent"] / max(1, state["streaming"]),
                    sum(lane.view is not None for lane in made.session.lanes),
                )
            )
            print("why " + made.reason)
            hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="stream:prose,120")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def _slow(
    window: Window, how: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str], str, str]:
    """
    The real app, `--tab stream:prose,120`, with or without the library.

    The three lines of the page's report and the child's own line, as fields;
    the page's reason; and everything the child printed.
    """
    script = window.out / "stream_page_slow.py"
    script.write_text(textwrap.dedent(SLOW), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if "=" in line and line[:4] != "why "]
    why = [line[4:] for line in done.stdout.splitlines() if line.startswith("why ")]
    assert len(lines) == 4 and lines[3].startswith("child ") and len(why) == 1, done.stdout
    print(how, window.where, done.stdout)  # shown by pytest -s, and when the test fails
    total, keep, reset, child = (_fields(line) for line in lines)
    return total, keep, reset, child, why[0], done.stdout


def test_without_the_library_the_page_says_why_not_in_a_real_window(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app, `--tab stream:prose,120`, with the library's variables
    removed for the child: ten frames, in each of which the page drew (the
    app did not replace it by its traceback page), no piece was fed, no view
    was made, nothing of imtypeset was imported, and the page's reason is the
    sentence about the variable.
    """
    total, keep, reset, child, why, stdout = _slow(window, "without", monkeypatch)
    assert child["imported"] == "0" and child["ready"] == "0" and child["views"] == "0"
    assert total["renderer"] == "none" and total["fed"] == "0" and total["done"] == "0", stdout
    assert int(child["page_frames"]) >= 8 and total["frames"] == child["page_frames"]
    assert typesetter.LIBRARY_VARIABLE in why, stdout
    for lane in (keep, reset):
        assert lane["edits"] == "0" and lane["vertices"] == "0" and lane["blocks"] == "0"


def test_with_the_library_the_page_streams_through_imtypeset_in_a_real_window(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The same app with the library, until the replay finishes: the child
    asserts `typesetter.module()` and `ready()` itself on its second frame and
    reports both again after its last, and the page's own report says the
    typeset path drew.

    At 120 tokens a second the 372 pieces of `demo/stream/prose.md` take three
    seconds of real time, so text arrives over many frames. Counts. More than
    twenty edits in each pane, a sample for every frame that changed a block,
    vertices on the pane's draw list, everything set as asked, every block
    committed. `RESET` moved lines, on four draws: the four paragraphs, each
    handed over again when it committed. `KEEP_STREAMED`'s count is printed
    and not asserted: how the library breaks a ragged paragraph is the
    library's (measured 2026-10-11 against be40444: 0).
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    total, keep, reset, child, why, stdout = _slow(window, "with", monkeypatch)
    assert child["imported"] == "1" and child["module"] == "1" and child["ready"] == "1", stdout
    assert why == "" and child["views"] == "2"
    assert total["renderer"] == "TypesetStreamView", stdout
    assert total["done"] == "1" and total["fed"] == total["pieces"] == "372", stdout
    assert int(total["frames"]) < 20000
    for lane in (keep, reset):
        assert int(lane["edits"]) > 20, f"the stream did not span many edits: {stdout}"
        assert lane["set"] == "1" and int(lane["append"]) > 10
        assert int(lane["edits"]) == sum(int(lane[kind]) for kind in ("set", "append", "replace"))
        assert int(lane["samples"]) >= int(lane["edits"]) - 1
        assert int(lane["vertices"]) > 1000 and lane["whole"] == "1"
        assert lane["blocks"] == lane["committed"] == "4"
    # Nothing but the commits is handed over again under KEEP_STREAMED; RESET
    # also replaces each paragraph when it commits.
    assert int(reset["replace"]) > int(keep["replace"])
    assert int(reset["moved"]) > 0 and reset["layouts_that_moved"] == "4"


# ----------------------------------------------------------------------
# Through imtypeset: real frames, no window, in a child that has the library
# ----------------------------------------------------------------------

_HEADLESS = r"""
import json, sys
from imgui_bundle import imgui
from advtext import typesetter
from advtext.theme import Theme
from advtext.ui.pages import stream as page

OLD = json.loads(sys.argv[1])
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

def frames(draw, count, seconds=1.0 / 60.0, width=1300.0):
    for _ in range(count):
        io.delta_time = seconds
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(width, 800.0))
            imgui.begin("##advtext-stream-page-test", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                draw()
            finally:
                imgui.end()
        finally:
            imgui.render()

def lane_of(lane):
    view = lane.view
    return {
        "name": lane.name, "lane": type(lane).__name__, "stream": type(lane.stream).__name__,
        "view": type(view).__name__, "edits": lane.edits,
        "parse": lane.parse.count, "draw": lane.draw.count, "moved": lane.moved,
        "moves": [list(move) for move in lane.moves], "taken": lane.taken,
        "vertices": lane.vertices, "whole": lane.whole,
        # Asking the library where a block is raises once it is switched off.
        "span": lane.live_span() if view is not None and typesetter.ready() else None,
        "origin": None if view is None else view.origin, "blocks": len(lane.stream.blocks),
        "committed": len(lane.stream.committed), "width": lane.width_px,
        "document": view is not None and view.native_document is not None,
    }

def told(made):
    session = made.session
    return {
        "renderer": made.renderer, "reason": made.reason, "failed": made.failed,
        "fed": session.fed, "pieces": len(session.pieces), "done": session.done,
        "frames": made.frames, "lanes": [lane_of(lane) for lane in session.lanes],
        "readouts": list(page.readouts(session)), "report": made.report(),
    }

# 1. The session alone, before anything else of advtext is imported: what the page's path loads.
session = page.Session(theme=Theme.build(), tokens_per_second=600.0,
                       source=next(s for s in page.SOURCES if s.key == "prose"))
unmade = [lane.view is None for lane in session.lanes]
def alone():
    session.advance(io.delta_time)
    for index, lane in enumerate(session.lanes):
        if index:
            imgui.same_line()
        imgui.begin_child("##lane-" + lane.name, imgui.ImVec2(600.0, 0.0), 0,
                          imgui.WindowFlags_.always_vertical_scrollbar.value)
        lane.show(imgui)
        imgui.end_child()
frames(alone, 20)
report["alone"] = {
    "old": sorted(name for name in sys.modules if name in OLD),
    "advtext": sorted(name for name in sys.modules if name.startswith("advtext")),
    "unmade": unmade, "fed": session.fed, "lanes": [lane_of(lane) for lane in session.lanes],
}
# A tick with no frame feeds and parses, and counts nothing that a draw did not show.
before = [lane.moved for lane in session.lanes]
samples = [lane.parse.count for lane in session.lanes]
session.tick(1.0 / 60.0)
report["alone"]["tick"] = [session.fed, [lane.moved for lane in session.lanes] == before,
                           [lane.parse.count - was for lane, was in zip(session.lanes, samples)]]

from advtext.ui.app import App

def app_of(spec):
    return App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)

# 2. The page through the shell: thirty frames of ten pieces, then to the end, then idle.
app = app_of("stream:prose,600")
made = app.page("stream")
commits = []
reset = made.session.lane("RESET")
settled = 0
def one_frame():
    # Each frame, and which of them found another block of RESET's committed.
    global settled
    frames(app.gui, 1)
    if len(reset.stream.committed) > settled:
        settled = len(reset.stream.committed)
        commits.append(reset.taken)
for _ in range(30):
    one_frame()
report["streaming"] = told(made)
count = 0
while not made.session.done and count < 2000:
    one_frame()
    count += 1
frames(app.gui, 3)
report["finished"] = told(made)
report["commits"] = commits
frames(app.gui, 5)
report["idle"] = told(made)

# 3. A change of width is not a move; the step and restart buttons.
app = app_of("stream:prose,600")
made = app.page("stream")
frames(app.gui, 20)
moved = [lane.moved for lane in made.session.lanes]
made.session.paused = True
frames(app.gui, 2, width=900.0)
report["resized"] = {"before": moved, "after": [lane.moved for lane in made.session.lanes],
                     "widths": [lane.width_px for lane in made.session.lanes]}
fed = made.session.fed
made.session.step()
frames(app.gui, 1, width=900.0)
report["stepped"] = [made.session.fed - fed, made.session.paused]
views = [lane.view for lane in made.session.lanes]
made.session.restart()
report["restarted"] = dict(told(made), closed=[view.native_document is None for view in views])
made.session.paused = False
frames(app.gui, 5, width=900.0)
report["again"] = dict(told(made),
                       fresh=[lane.view is not was for lane, was in zip(made.session.lanes, views)])

# 4. `done`: everything on the first frame, in one edit.
app = app_of("stream:table,done")
frames(app.gui, 3)
report["whole"] = told(app.page("stream"))

# After the body that needs the library, and before the two sections that take it away.
report["after"] = {"module": typesetter.module() is not None, "ready": typesetter.ready(),
                   "reason": typesetter.reason()}

# 5. A draw that raises with the library still ready: the page keeps the sentence, finishes
# the frame without an error, and is the one line from the next frame on.
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView
real_draw = TypesetView.draw
def failing(self, **kwargs):
    raise TypesetUnavailable("raised by the test")
app = app_of("stream:prose,600")
made = app.page("stream")
frames(app.gui, 10)
TypesetView.draw = failing
frames(app.gui, 1)
TypesetView.draw = real_draw
# B3: the page gave back what its views held in the library when it gave up.
released = [lane.view.native_document is None for lane in made.session.lanes]
at_once = told(made)
# `told` asks each lane where its live block is (the library is still ready
# here), and a closed view makes its document again to answer: one more
# `set`, made by this script's question and not by the page. So what the
# four frames below must leave alone is read after the question.
asked = [dict(lane.edits) for lane in made.session.lanes]
shown = []
real_say = page.say_why_not
def saying(reason):
    shown.append(reason)
    real_say(reason)
page.say_why_not = saying
frames(app.gui, 4)
page.say_why_not = real_say
report["middraw"] = {"at_once": at_once, "later": told(made), "shown": shown,
                     "released": released, "asked": asked,
                     "ready": typesetter.ready(),
                     "current": type(app.page("stream")).__name__}

# 6. Last, because it is for the rest of the process: the library switched off mid-replay.
app = app_of("stream:prose,600")
made = app.page("stream")
frames(app.gui, 10)
before = told(made)
typesetter.disable("switched off by the test")
frames(app.gui, 1)
after = told(made)
frames(app.gui, 5)
report["off"] = {"before": before, "after": after, "later": told(made),
                 "ready": typesetter.ready()}
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    """
    `_HEADLESS` run once in a child that has the library; skipped without the variable.

    The child says whether the library was in use and ready before its body
    and again after the part of it that draws: a body that had quietly lost
    the library would otherwise be read as one that drew.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    from test_typeset_closure import OLD_CORE

    done = subprocess.run(
        [sys.executable, "-B", "-c", _HEADLESS, json.dumps(sorted(OLD_CORE))],
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


def test_the_session_loads_no_old_view_and_no_old_stream(typeset: dict[str, Any]) -> None:
    """
    Twenty frames of both lanes, drawn, in a process that had imported the page
    and a theme and nothing else of advtext: NOTHING is loaded of the old
    core. Until 2026-10-12 it was `advtext.fontlib`, which
    `typesetter.load_fonts` asked where the font files are, and the
    `advtext.fontmetrics` it imports; the files are `advtext.fontfiles`'
    now. Building a theme loads none of it since T5-B2. Neither
    `advtext.stream` nor `advtext.markdown`, and no view of the old core. The
    lanes had no view until their first `show`.
    """
    alone = typeset["alone"]
    assert set(alone["old"]) == set(), alone["old"]
    for name in ("advtext.stream", "advtext.markdown", "advtext.style", "advtext.mathtext"):
        assert name not in alone["advtext"], name
    assert alone["unmade"] == [True, True]
    assert alone["fed"] == 200
    for lane in alone["lanes"]:
        assert (lane["lane"], lane["stream"], lane["view"]) == (
            "Lane",
            "MarkdownStream",
            "TypesetStreamView",
        )
        assert lane["vertices"] > 500 and lane["whole"] is True and lane["document"] is True
    # A tick with no frame: ten more pieces, taken in (a sample each), and no line counted.
    assert alone["tick"] == [210, True, [1, 1]]


def test_the_page_streams_frame_by_frame_through_the_shell(typeset: dict[str, Any]) -> None:
    """
    Thirty frames of a sixtieth of a second at 600 tokens a second: ten pieces
    a frame. An edit a frame in each pane (the first is the `set_blocks`), a
    parse sample and a draw sample for each, vertices in both, a live span in
    both, side by side at one width.
    """
    told = typeset["streaming"]
    assert told["renderer"] == "TypesetStreamView"
    assert told["reason"] == "" and told["failed"] == ""
    assert told["fed"] == 300 and told["done"] is False and told["frames"] == 30
    keep, reset = told["lanes"]
    assert (keep["name"], reset["name"]) == ("KEEP_STREAMED", "RESET")
    for lane in (keep, reset):
        assert lane["edits"]["set"] == 1 and sum(lane["edits"].values()) == 30
        assert (lane["parse"], lane["draw"]) == (30, 30)
        assert lane["vertices"] > 500 and lane["whole"] is True
        assert lane["span"] is not None and lane["span"][0] < lane["span"][1]
        assert lane["committed"] < lane["blocks"]
    assert keep["origin"][0] < reset["origin"][0] and keep["origin"][1] == reset["origin"][1]
    assert keep["width"] == reset["width"]
    # The readouts name edits, and the two parts the cost has.
    assert len(told["readouts"]) == 5
    assert "settled lines moved:" in told["readouts"][1] and "of 30 edits)" in told["readouts"][1]
    assert "parse and edit" in told["readouts"][2] and "layout and draw" in told["readouts"][2]
    assert told["report"][0].endswith("renderer=TypesetStreamView")
    assert told["report"][1].startswith("KEEP_STREAMED edits=30 set=1 ")


def test_the_page_finishes_commits_everything_and_then_idles(typeset: dict[str, Any]) -> None:
    """
    To the end: every piece fed, four blocks committed, no live span. `RESET`
    handed four more blocks over than `KEEP_STREAMED` (each paragraph again at
    its commit) and moved lines on exactly those four draws: every draw that
    moved a line under `RESET` is one on which a block had committed. Five
    idle frames after that add no edit and no sample.
    """
    done, idle = typeset["finished"], typeset["idle"]
    assert done["done"] is True and done["fed"] == done["pieces"] == 372
    keep, reset = done["lanes"]
    for lane in (keep, reset):
        assert lane["blocks"] == lane["committed"] == 4 and lane["span"] is None
        assert lane["parse"] == lane["draw"] == sum(lane["edits"].values())
    assert reset["edits"]["replace"] == keep["edits"]["replace"] + 4
    assert reset["moved"] > 0 and len(reset["moves"]) == 4
    assert reset["moved"] == sum(count for _, count in reset["moves"])
    assert [taken for taken, _ in reset["moves"]] == typeset["commits"]
    for was, now in zip(done["lanes"], idle["lanes"], strict=True):
        assert now["edits"] == was["edits"]
        assert (now["parse"], now["draw"], now["moved"]) == (
            was["parse"],
            was["draw"],
            was["moved"],
        )
    assert idle["frames"] == done["frames"] + 5


def test_on_the_page_a_width_is_not_a_move_and_the_buttons_work(typeset: dict[str, Any]) -> None:
    """
    A restart closes each lane's document in the library and drops the view;
    the next frame makes a new one.
    """
    resized = typeset["resized"]
    assert resized["after"] == resized["before"], "a change of width was counted as lines moving"
    assert resized["widths"][0] == resized["widths"][1] < 500.0
    assert typeset["stepped"] == [1, True]
    restarted = typeset["restarted"]
    assert restarted["fed"] == 0 and restarted["renderer"] == "TypesetStreamView"
    assert restarted["closed"] == [True, True], "a view that was replaced kept its document"
    for lane in restarted["lanes"]:
        assert lane["view"] == "NoneType" and lane["document"] is False
        assert lane["edits"] == {"set": 0, "replace": 0, "append": 0}
        assert (lane["parse"], lane["draw"], lane["moved"], lane["taken"]) == (0, 0, 0, 0)
    again = typeset["again"]
    assert again["fed"] == 50 and again["fresh"] == [True, True]
    for lane in again["lanes"]:
        assert lane["view"] == "TypesetStreamView"
        assert sum(lane["edits"].values()) == 5 and lane["vertices"] > 0


def test_the_page_fed_whole_makes_one_edit(typeset: dict[str, Any]) -> None:
    """
    `done`: the view is made on the first frame over a stream that already
    holds everything. One `set_blocks`, and one sample of each cost.
    """
    whole = typeset["whole"]
    assert whole["done"] is True and whole["renderer"] == "TypesetStreamView"
    for lane in whole["lanes"]:
        assert lane["edits"] == {"set": 1, "replace": 0, "append": 0}
        assert (lane["parse"], lane["draw"]) == (1, 1) and lane["vertices"] > 500


def test_when_a_draw_raises_the_page_is_the_one_line_from_the_next_frame_on(
    typeset: dict[str, Any],
) -> None:
    """
    `TypesetView.draw` made to raise `TypesetUnavailable` for one frame, with
    the library ready throughout. That frame ends without an error (the
    child's ImGui would have refused an unbalanced stack) and the page holds
    what was said; the four frames after it are `say_why_not` with that
    sentence, although the library could draw again: the clock stands, the
    page is still the page and not the app's traceback, and no pane is drawn.
    """
    told = typeset["middraw"]
    at_once, later = told["at_once"], told["later"]
    assert told["ready"] is True and told["current"] == "StreamPage"
    assert at_once["failed"] == "raised by the test" == at_once["reason"]
    assert at_once["renderer"] == "none" and at_once["frames"] == 11
    # That frame's ten pieces had been fed before the first pane's draw raised.
    assert at_once["fed"] == 110
    assert told["shown"] == ["raised by the test"] * 4
    assert later["frames"] == 15 and later["fed"] == 110 and later["failed"] == at_once["failed"]
    # B3 (T5-FINAL): giving up closed both views' documents in the library.
    assert told["released"] == [True, True]
    for was, asked, now in zip(at_once["lanes"], told["asked"], later["lanes"], strict=True):
        # The edits are compared with what they were AFTER this script's own
        # question about the live block, which made the closed document again
        # (one `set`: see the script). The four frames added none. Until
        # T5-FINAL the views were not closed and `was["edits"]` stood here.
        assert asked == {**was["edits"], "set": was["edits"]["set"] + 1}
        assert (now["draw"], now["parse"], now["edits"]) == (was["draw"], was["parse"], asked)
    assert later["report"][0].endswith("renderer=none")


def test_when_the_library_is_switched_off_the_page_is_the_one_line(
    typeset: dict[str, Any],
) -> None:
    """
    `typesetter.disable` between two frames of a replay. The next frame is the
    line with the reason and nothing is fed, then or later; the page raised
    nothing.
    """
    off = typeset["off"]
    before, after, later = off["before"], off["after"], off["later"]
    assert off["ready"] is False
    assert before["renderer"] == "TypesetStreamView" and before["fed"] == 100
    assert after["renderer"] == "none" and "switched off by the test" in after["reason"]
    assert after["failed"] == "", "nothing was raised: the page asked `ready()` first"
    assert after["fed"] == 100 and after["frames"] == before["frames"] + 1
    assert later["fed"] == 100 and later["frames"] == after["frames"] + 5
    for was, now in zip(before["lanes"], later["lanes"], strict=True):
        assert (now["draw"], now["parse"], now["edits"]) == (
            was["draw"],
            was["parse"],
            was["edits"],
        )
    assert later["report"][0].endswith("renderer=none")

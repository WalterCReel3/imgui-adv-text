"""
The Stream page: its replay logic on a clock advanced by hand, its counters held
to what can be predicted, and the page itself in frames and in a window.

**Three levels, stated so nobody reads more into a green run than is there.**

1. `Session` and `Lane` with no ImGui at all. Time is whatever the test passes
   in, and the timer that splits an append's cost is a fake that ticks one
   millisecond a reading, so the figures asserted are exact.
2. The page through `App.gui` in frames of a real `ImGuiContext` with no
   backend: real child windows, real `StreamView.draw`, no fonts and no pixels.
3. The real app in a real window (`tests/conftest.py::window`: the session's
   display, or an Xvfb), at a token rate slow enough that the stream spans many
   layouts. An earlier unattended run of a streaming demo fed everything before
   the first layout and so exercised no streaming at all; the assertion on the
   number of layouts is there so that cannot pass again.

**Nothing here judges how a stream looks.** The counters report change and
cost (`docs/visual-review.md`), and one test holds the page's own wording to
that.
"""

from __future__ import annotations

import re
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from advtext.markdown import CodeBlock, TableBlock, TextBlock, build_document
from advtext.stream import CommitPolicy
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import pages
from advtext.ui.app import App, parse_tab_request
from advtext.ui.pages import PageContext
from advtext.ui.pages import stream as page
from advtext.ui.pages.stream import SOURCES, Cost, Lane, Session, live_span, readouts, tokens
from advtext.units import Scaled, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

KEEP = CommitPolicy.KEEP_STREAMED
RESET = CommitPolicy.RESET
FRAME = 1.0 / 60.0

PROSE = (
    "\n\n".join(
        f"Paragraph {n} is plain prose and long enough to be broken onto several lines at "
        f"the widths used here, which is the only way a settled line exists to be watched "
        f"while later words arrive after it. It says nothing else of any interest and it "
        f"has no markup of any kind in it, so every one of its lines is filled first-fit "
        f"and left alone. Sentence {n} ends here."
        for n in range(1, 6)
    )
    + "\n"
)
"""
Five paragraphs, about 330 pieces. No blank line after the last, so it commits at the close.
"""


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure() -> Any:
    return char_measure(fontlib_metrics)


def _source(key: str) -> page.Source:
    return next(entry for entry in SOURCES if entry.key == key)


def _session(theme: Theme, measure: Any, text: str | None = PROSE, **fields: Any) -> Session:
    return Session(theme=theme, measure=measure, text=text, **fields)


def _run(session: Session, width: Scaled, seconds: float = FRAME) -> int:
    """
    Tick to the end. Returns the number of ticks, and fails if the replay never ends.
    """
    ticks = 0
    while not session.done:
        session.tick(seconds, width)
        ticks += 1
        assert ticks < 100_000, "the replay did not finish"
    return ticks


class _Clock:
    """
    A timer that advances one millisecond every time it is read.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


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


def test_the_sources_are_the_cases_their_labels_say(theme: Theme, measure: Any) -> None:
    """
    Each hard case is in its file, counted from the parsed document and not from
    the file's own prose about itself.
    """

    def blocks(key: str) -> tuple[Any, ...]:
        return build_document(_source(key).text(), theme, fontlib_metrics).blocks

    tables = [block for block in blocks("table") if isinstance(block, TableBlock)]
    assert [len(table.rows) for table in tables] == [30]

    fences = [block for block in blocks("code") if isinstance(block, CodeBlock)]
    assert [len(fence.lines) for fence in fences] == [600]

    assert all(isinstance(block, TextBlock) for block in blocks("prose"))
    text = _source("prose").text()
    assert not re.search(r"[*_`\[\]#|]", text), "the plain prose has markup in it"

    steps = blocks("steps")
    indented = [block for block in steps if isinstance(block, CodeBlock) and block.left_indent > 0]
    assert len(indented) >= 3, "the steps have no fences under their numbers"
    assert re.search(r"^\d+\. .*\n\n   \S", _source("steps").text(), re.MULTILINE)

    links = _source("links").text()
    longest = max(links.split(), key=len)
    assert longest.startswith("https://")
    assert re.search(r"^\[\w+\]: https://", links, re.MULTILINE), "no reference definitions"
    assert re.search(r"\]\[\w+\]", links), "no reference-style link"


def test_the_address_is_wider_than_the_widest_pane_the_page_has(theme: Theme, measure: Any) -> None:
    """
    Measured from the layout: at the full body width (1068 px, wider than
    either pane can be) a set line still ends past the measure.
    """
    session = _session(theme, measure, text=None, source=_source("links"))
    session.finish()
    width = sp_from_px(1068.0)
    session.settle(width)
    for lane in session.lanes:
        furthest = max(x for line in lane.view.set_lines() for _, x in line.glyphs)
        assert furthest > width, lane.policy


def test_reference_links_are_shown_as_typed_while_streaming(theme: Theme, measure: Any) -> None:
    """
    The property the links source is there to show, checked on the finished
    stream: the bracketed words are still in the set text.
    """
    session = _session(theme, measure, text=None, source=_source("links"))
    session.finish()
    session.settle(sp_from_px(500.0))
    for lane in session.lanes:
        lane.view.select_all()
        text = " ".join(lane.view.selected_text().split())
        assert "[the changelog][changes]" in text, lane.policy
        assert "[the issue tracker][issues]" in text, lane.policy
        # The inline link beside them is a link: its address is not set as text.
        assert "the project page" in text and "(https://example.org/project)" not in text


# ----------------------------------------------------------------------
# The clock and the controls
# ----------------------------------------------------------------------


def test_the_clock_decides_how_many_pieces_arrive_and_fractions_are_carried(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure, tokens_per_second=40.0)
    fed = [session.advance(FRAME) for _ in range(60)]
    assert sum(fed) == 40, "sixty sixtieths of a second at forty a second is forty pieces"
    assert set(fed) == {0, 1}, "pieces arrived in bursts although the rate is under one a frame"
    assert session.fed == 40


def test_both_lanes_are_fed_the_same_pieces_at_every_step(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
    width = sp_from_px(420.0)
    seen = 0
    while not session.done:
        session.tick(FRAME, width)
        keep, reset = session.lane(KEEP), session.lane(RESET)
        assert keep.stream.source == reset.stream.source == "".join(session.pieces[: session.fed])
        assert keep.taken == reset.taken == session.fed
        seen += 1
    assert seen > 5
    assert all(lane.stream.closed for lane in session.lanes)
    assert session.lane(KEEP).stream.source == PROSE


def test_the_fixture_is_long_enough_for_the_tests_that_stop_part_way(
    theme: Theme, measure: Any
) -> None:
    """
    Several tests tick a fixed number of frames and expect to be mid-stream.
    """
    assert len(tokens(PROSE)) > 300


def test_pausing_stops_the_clock_and_a_step_feeds_exactly_one_piece(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
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


def test_a_step_from_running_pauses(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure)
    assert not session.paused
    session.step()
    assert session.paused and session.fed == 1


def test_stepping_past_the_end_closes_the_streams_and_feeds_no_more(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure)
    total = len(session.pieces)
    assert session.step(total + 50) == total
    assert session.done
    assert session.step() == 0 and session.advance(1.0) == 0


def test_restart_begins_the_same_source_again_with_every_count_at_zero(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure, tokens_per_second=900.0)
    _run(session, sp_from_px(360.0))
    reset = session.lane(RESET)
    assert reset.moved > 0 and reset.layout.count > 0
    old_view = reset.view

    session.restart()
    assert (session.fed, session.done) == (0, False)
    for lane in session.lanes:
        assert (lane.moved, lane.moves, lane.taken) == (0, [], 0)
        assert (lane.parse.count, lane.layout.count, lane.draw.count) == (0, 0, 0)
        assert lane.stream.source == "" and lane.view.relayouts == 0
    assert reset.view is not old_view
    assert session.tokens_per_second == 900.0
    _run(session, sp_from_px(360.0))
    assert session.lane(KEEP).stream.source == PROSE


def test_choosing_a_source_replays_that_one_from_the_start(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure)
    session.step(20)
    session.choose(_source("prose"))
    assert session.fed == 0 and session.source.key == "prose"
    assert "".join(session.pieces) == _source("prose").text()
    assert all(lane.stream.source == "" for lane in session.lanes)


# ----------------------------------------------------------------------
# Settled lines moved
# ----------------------------------------------------------------------


@pytest.mark.parametrize("width_px", [360.0, 560.0])
@pytest.mark.parametrize("rate", [40.0, 700.0])
def test_plain_prose_kept_as_streamed_moves_no_settled_line(
    width_px: float, rate: float, theme: Theme, measure: Any
) -> None:
    """
    First-fit at natural spacing: a line depends only on the text up to its own
    end. Guarded against vacuity by the lane beside it, which sees the same
    pieces through the same counter and does count moves.
    """
    session = _session(theme, measure, tokens_per_second=rate)
    _run(session, sp_from_px(width_px))
    keep, reset = session.lane(KEEP), session.lane(RESET)
    assert keep.moved == 0 and keep.moves == []
    assert reset.moved > 0, "the counter counted nothing under RESET either; it may be blind"
    assert keep.view.relayouts > 5


def test_resetting_moves_lines_only_on_the_layouts_where_a_block_committed(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure, tokens_per_second=60.0)
    width = sp_from_px(360.0)
    reset = session.lane(RESET)
    commits: list[int] = []
    before = 0
    while not session.done:
        session.tick(FRAME, width)
        now = len(reset.stream.committed)
        if now > before:
            commits.append(reset.taken)
        before = now
    # A paragraph commits when the stream can be sure it is over, which is
    # not on its own last character; how many commits land on one layout is
    # the stream's business. What is held here is that lines moved on those
    # layouts and on no others.
    assert len(commits) >= 3, f"commits at {commits}"
    assert len(reset.stream.committed) == len(reset.stream.blocks) == 5
    assert [fed for fed, _ in reset.moves] == commits
    assert reset.moved == sum(count for _, count in reset.moves)


def test_the_file_of_plain_prose_holds_to_the_same_two_counts(theme: Theme, measure: Any) -> None:
    """
    `demo/stream/prose.md` is the source the page offers for exactly this, so it
    is held to it: zero under one policy, one burst a paragraph under the other.
    """
    session = _session(theme, measure, text=None, source=_source("prose"), tokens_per_second=240.0)
    _run(session, sp_from_px(500.0))
    assert session.lane(KEEP).moved == 0
    paragraphs = len(session.lane(RESET).stream.blocks)
    assert len(session.lane(RESET).moves) == paragraphs == 4


def test_a_change_of_width_is_not_counted_as_a_move(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
    for _ in range(12):
        session.tick(FRAME, sp_from_px(400.0))
    keep = session.lane(KEEP)
    assert not session.done and keep.moved == 0
    lines_before = keep.view.set_lines()

    session.paused = True
    session.settle(sp_from_px(300.0))
    assert keep.view.set_lines() != lines_before, "the resize moved nothing; the test is vacuous"
    assert keep.moved == 0 and session.lane(RESET).moved == 0

    session.paused = False
    _run(session, sp_from_px(300.0))
    assert keep.moved == 0, "the layout after the resize was compared with one before it"


def test_the_counter_never_counts_the_line_being_written() -> None:
    a, b, c = ("a", 0), ("b", 1), ("c", 2)
    grown = ("c and more", 2)
    assert page.changed_lines([a, b, c], [a, b, grown]) == []  # type: ignore[list-item]
    assert page.changed_lines([a, b, c], [a, ("b moved", 1), grown]) == [b]  # type: ignore[list-item]
    assert page.changed_lines([], [a]) == []  # type: ignore[list-item]


# ----------------------------------------------------------------------
# The cost split
# ----------------------------------------------------------------------


def test_cost_keeps_the_latest_the_mean_and_the_largest() -> None:
    cost = Cost()
    assert (cost.last_ms, cost.mean_ms, cost.worst_ms, cost.count) == (0.0, 0.0, 0.0, 0)
    for seconds in (0.002, 0.006, 0.001):
        cost.add(seconds)
    assert cost.count == 3
    assert cost.last_ms == pytest.approx(1.0)
    assert cost.mean_ms == pytest.approx(3.0)
    assert cost.worst_ms == pytest.approx(6.0)


def test_an_append_is_timed_in_two_parts_and_an_idle_frame_is_not(
    theme: Theme, measure: Any
) -> None:
    """
    The fake timer ticks a millisecond a reading and `lay_out` reads it three
    times, so each sample is exactly one millisecond of parse and one of layout.
    """
    lane = Lane(KEEP, theme, measure, timer=_Clock())
    width = sp_from_px(400.0)

    lane.take(["Some ", "text"])
    assert lane.lay_out(width) is True
    assert (lane.parse.count, lane.layout.count) == (1, 1)
    assert lane.parse.last_ms == pytest.approx(1.0) and lane.layout.last_ms == pytest.approx(1.0)

    assert lane.lay_out(width) is False
    assert lane.lay_out(sp_from_px(300.0)) is False, "a resize was counted as an append"
    assert (lane.parse.count, lane.layout.count) == (1, 1)

    lane.take([" and", " more"])
    assert lane.lay_out(sp_from_px(300.0)) is True
    assert (lane.parse.count, lane.layout.count) == (2, 2)
    assert lane.draw.count == 0, "nothing was drawn, so nothing may be recorded as drawn"


def test_several_pieces_in_one_frame_are_one_layout_and_one_sample(
    theme: Theme, measure: Any
) -> None:
    session = _session(theme, measure, tokens_per_second=1200.0, timer=_Clock())
    session.tick(FRAME, sp_from_px(400.0))
    assert session.fed == 20
    for lane in session.lanes:
        assert lane.view.relayouts == 1 and lane.layout.count == 1


# ----------------------------------------------------------------------
# Committed, live, and the mark between them
# ----------------------------------------------------------------------


def test_the_live_span_starts_where_the_committed_blocks_end(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
    width = sp_from_px(400.0)
    keep = session.lane(KEEP)
    assert live_span(keep.view) is None, "no layout yet"

    starts: set[int] = set()
    while not session.done:
        session.tick(FRAME, width)
        span = live_span(keep.view)
        layout = keep.view.layout
        assert layout is not None
        settled = len(keep.stream.committed)
        if settled == len(keep.stream.blocks):
            assert span is None
            continue
        assert span is not None
        top, bottom = span
        first_live = layout.unit_of_block(settled)
        assert first_live is not None and top == first_live.y
        assert bottom == layout.placed[-1].bottom
        if settled:
            above = layout.unit_of_block(settled - 1)
            assert above is not None and above.bottom <= top
        starts.add(settled)
    assert len(starts) >= 3 and 0 in starts, f"the boundary was seen at {sorted(starts)}"
    assert live_span(keep.view) is None, "the stream is closed and something is still marked live"


def test_the_readout_counts_committed_and_live_blocks(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
    width = sp_from_px(400.0)
    while len(session.lane(KEEP).stream.committed) < 1:
        session.tick(FRAME, width)
    keep = session.lane(KEEP)
    committed = len(keep.stream.committed)
    live = len(keep.stream.blocks) - committed
    assert committed >= 1 and live >= 1 and not session.done
    counts, _ = keep.describe()
    assert f"blocks: {committed} committed, {live} live" in counts
    _run(session, width)
    counts, _ = keep.describe()
    assert "blocks: 5 committed, 0 live" in counts


def test_the_readouts_state_counts_and_costs_and_no_judgement(theme: Theme, measure: Any) -> None:
    """
    `docs/visual-review.md`, rule 1, applied to the page's own words: a counter
    may say what changed and what it cost and may not say whether that is good.
    """
    session = _session(theme, measure, tokens_per_second=600.0, timer=_Clock())
    _run(session, sp_from_px(400.0))
    lines = readouts(session)
    assert len(lines) == 1 + 2 * len(session.lanes)
    assert f"piece {len(session.pieces)} of {len(session.pieces)}" in lines[0]
    assert "finished" in lines[0]
    assert lines[1].startswith("KEEP_STREAMED") and lines[3].startswith("RESET")
    assert "settled lines moved: 0 (in 0 of" in lines[1]
    assert "parse 1.00 / 1.00 / 1.00" in lines[2] and "layout 1.00 / 1.00 / 1.00" in lines[2]
    text = " ".join(lines).lower()
    for word in ("better", "worse", "good", "bad", "smooth", "jank", "clean", "crisp", "stable"):
        assert word not in text, f"a readout says {word!r}"


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


def test_the_page_is_discovered_after_the_original_five() -> None:
    found = pages.require()
    names = [entry.name for entry in found.pages]
    assert "Stream" in names and names.index("Stream") >= 5
    spec = found.find("stream")
    assert spec is page.PAGE
    for request in spec.shot_specs():
        assert parse_tab_request(request, found).tab == "stream"


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


def test_the_launch_options_pick_the_source_the_rate_and_the_finished_state() -> None:
    plain = page.StreamPage(_context("stream"))
    assert plain.session.source is SOURCES[0]
    assert plain.session.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND
    assert plain.session.fed == 0

    made = page.StreamPage(_context("stream:table,250"))
    assert made.session.source.key == "table" and made.session.tokens_per_second == 250.0

    done = page.StreamPage(_context("stream:prose,done"))
    assert done.session.done and done.session.fed == len(done.session.pieces)

    other = page.StreamPage(_context("document:7"))
    assert other.session.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND


def _frames(app: App, count: int, seconds: float = FRAME) -> None:
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
            app.gui()
            imgui.end()
        finally:
            imgui.render()


def test_the_page_streams_frame_by_frame_through_the_shell() -> None:
    """
    Thirty frames of a sixtieth of a second at 600 tokens a second: ten pieces a
    frame, a layout a frame in each pane, a draw sample for each, and something
    drawn in both.
    """
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="stream:prose,600")
    _frames(app, 30)
    made = app.page("stream")
    assert isinstance(made, page.StreamPage) and made.frames == 30
    session = made.session
    assert session.fed == 300 and not session.done
    for lane in session.lanes:
        assert lane.view.relayouts == 30
        assert (lane.parse.count, lane.layout.count, lane.draw.count) == (30, 30, 30)
        assert lane.stats is not None and lane.stats.glyphs > 0
        assert live_span(lane.view) is not None
        assert lane.view.origin is not None
    keep, reset = session.lane(KEEP), session.lane(RESET)
    # Side by side and equally wide: same measure, so the same text is laid
    # out at the same width under both policies.
    assert keep.view.layout is not None and reset.view.layout is not None
    assert keep.view.layout.width == reset.view.layout.width
    assert keep.view.origin[0] < reset.view.origin[0]  # type: ignore[index]
    assert keep.view.origin[1] == reset.view.origin[1]  # type: ignore[index]
    assert keep.moved == 0


def test_an_idle_frame_of_the_page_adds_no_sample_and_no_layout() -> None:
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="stream:prose,done")
    _frames(app, 3)
    made = app.page("stream")
    assert isinstance(made, page.StreamPage)
    for lane in made.session.lanes:
        assert lane.view.relayouts == 1
        assert (lane.layout.count, lane.draw.count) == (1, 1)
        assert live_span(lane.view) is None


def test_the_report_is_counts(theme: Theme, measure: Any) -> None:
    session = _session(theme, measure, tokens_per_second=600.0)
    _run(session, sp_from_px(400.0))
    lines = page.report(session, 7)
    assert lines[0].startswith("frames=7 fed=") and "done=1" in lines[0]
    assert lines[1].startswith("KEEP_STREAMED layouts=") and "moved=0 " in lines[1]
    assert lines[2].startswith("RESET layouts=")


# ----------------------------------------------------------------------
# A real window, slowly
# ----------------------------------------------------------------------

SLOW = """
from imgui_bundle import hello_imgui

from advtext.ui import app as advtext_app

state = {"frames": 0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        # No operator will wake an idling app, and at the idle frame rate a
        # frame's worth of tokens is most of a paragraph.
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    real_gui(self)
    state["frames"] += 1
    made = self.page("stream")
    if made.session.done or state["frames"] >= 20000:
        # A few frames more, so the last layout is drawn before the report.
        state.setdefault("left", 3)
        state["left"] -= 1
        if state["left"] <= 0:
            for line in made.report():
                print(line)
            hello_imgui.get_runner_params().app_shall_exit = True


advtext_app.App.gui = watched_gui
advtext_app.run(tab="stream:prose,120")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_the_page_streams_over_many_layouts_in_a_real_window(window: Window) -> None:
    """
    The real app, `--tab stream:prose,120`, until the replay finishes.

    At 120 tokens a second the 372 pieces of `demo/stream/prose.md` take three
    seconds of real time. Measured on Xvfb with the software rasteriser, this
    page runs at about twenty frames a second, so that is about sixty frames
    with text arriving in each; at 300 a second it was 24 layouts, too close to
    the bound below to leave there. The assertions are counts: every piece fed,
    the streams closed, more than twenty layouts in each pane, glyphs drawn
    with none missing, and the two counters where first-fit says they must be.
    """
    script = window.out / "stream_page_slow.py"
    script.write_text(textwrap.dedent(SLOW), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\\n{done.stdout}\\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if "=" in line]
    assert len(lines) == 3, done.stdout
    total, keep, reset = (_fields(line) for line in lines)
    assert total["done"] == "1" and total["fed"] == total["pieces"] == "372", done.stdout
    assert int(total["frames"]) < 20000
    for lane in (keep, reset):
        assert int(lane["layouts"]) > 20, f"the stream did not span many layouts: {done.stdout}"
        # A first frame on which no time had passed lays out the empty
        # document, which is a layout and not an append.
        assert int(lane["layouts"]) - int(lane["samples"]) in (0, 1)
        assert int(lane["glyphs"]) > 0 and lane["missing"] == "0"
        assert lane["blocks"] == lane["committed"] == "4"
    assert keep["moved"] == "0"
    assert int(reset["moved"]) > 0 and reset["layouts_that_moved"] == "4"

"""
The Stress page: its arithmetic, that its counters count what they say, and a
run in a real window at 1, 4 and 16 panes.

**The figures the page shows are wall-clock times and no test asserts one.** A
test that a draw takes under some number of milliseconds is a test of the
machine. What is asserted is the bookkeeping: that a sample is taken per pane
per frame, that layout and draw are timed apart, that the glyph and unit counts
agree with what the view and the layout themselves report, and that the totals
are the sums they claim to be. The timer in the frame tests is a fake that
ticks one millisecond a reading, so those figures are exact.

The window test prints the page's own report at each pane count and checks the
counts in it. Its milliseconds are **software-rendered Xvfb figures** wherever
the `window` fixture had to fall back to one, and they are printed, not judged.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from advtext.selection import Selection
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import pages
from advtext.ui.app import App, parse_tab_request
from advtext.ui.bare_view import BareView
from advtext.ui.pages import PageContext
from advtext.ui.pages import stress as page
from advtext.ui.pages.stress import (
    LENGTHS,
    MAX_PANES,
    REFERENCE_MS,
    Rolling,
    Stress,
    grid_shape,
    readouts,
    repeated,
)
from advtext.ui.stream_view import StreamView

if TYPE_CHECKING:
    from conftest import Window

SMALL = (
    "# A heading\n\n"
    "A paragraph long enough to be broken onto more than one line in a narrow pane, "
    "so that a pane holds several units and several lines of glyphs.\n\n"
    "- one item\n- another item\n\n"
    "A closing paragraph.\n"
)


class _Clock:
    """
    A timer that advances one millisecond every time it is read.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure() -> Any:
    return char_measure(fontlib_metrics)


def _stress(theme: Theme, measure: Any, **fields: Any) -> Stress:
    fields.setdefault("source", SMALL)
    return Stress(theme=theme, measure=measure, **fields)


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


def test_a_longer_document_is_the_source_repeated(theme: Theme, measure: Any) -> None:
    assert repeated("a\n", 1) == "a\n"
    assert repeated("a\n", 3) == "a\n\na\n\na\n"
    stress = _stress(theme, measure)
    one, five = stress.document(1), stress.document(5)
    assert len(five.blocks) == 5 * len(one.blocks)
    assert stress.document(5) is five, "the document was parsed again"


# ----------------------------------------------------------------------
# Panes follow the controls
# ----------------------------------------------------------------------


def test_the_pane_count_is_clamped_and_followed(theme: Theme, measure: Any) -> None:
    stress = _stress(theme, measure, count=4)
    assert len(stress.panes) == 4
    for count, expected in ((0, 1), (7, 7), (99, MAX_PANES)):
        stress.count = count
        stress.configure()
        assert (stress.count, len(stress.panes)) == (expected, expected)


def test_changing_only_the_count_keeps_the_panes_there_were(theme: Theme, measure: Any) -> None:
    stress = _stress(theme, measure, count=3)
    kept = list(stress.panes)
    stress.count = 5
    stress.configure()
    assert len(stress.panes) == 5
    assert all(a is b for a, b in zip(stress.panes[:3], kept, strict=True))
    stress.count = 2
    stress.configure()
    assert all(a is b for a, b in zip(stress.panes, kept[:2], strict=True))


def test_each_pane_has_a_view_of_its_own_and_caches_of_its_own(theme: Theme, measure: Any) -> None:
    """
    What the page says about sharing, held to the tree: one parsed document for
    all finished panes, and nothing derived from it shared between two views.

    The caches are private fields of `BareView`; they are read here, in the
    test, to keep the page's sentence true -- the page itself does not touch
    them.
    """
    stress = _stress(theme, measure, count=3)
    views = [pane.view for pane in stress.panes]
    assert len({id(view) for view in views}) == 3
    assert all(type(view) is BareView for view in views)
    assert all(view.document is stress.document(1) for view in views)
    assert len({id(view._blocks) for view in views}) == 3
    assert len({id(view._units) for view in views}) == 3


def test_all_streaming_gives_every_pane_a_stream_of_its_own(theme: Theme, measure: Any) -> None:
    stress = _stress(theme, measure, count=3)
    finished = list(stress.panes)
    stress.streaming = True
    stress.configure()
    assert all(isinstance(pane.view, StreamView) for pane in stress.panes)
    assert len({id(pane.stream) for pane in stress.panes}) == 3
    assert not any(pane in finished for pane in stress.panes)
    assert all("".join(pane.pieces) == stress.text(1) for pane in stress.panes)


def test_a_change_of_length_rebuilds_the_panes_over_the_longer_document(
    theme: Theme, measure: Any
) -> None:
    stress = _stress(theme, measure, count=2)
    stress.length = 5
    stress.configure()
    assert all(pane.view.document is stress.document(5) for pane in stress.panes)
    stress.length = 7  # not one of the three the control offers
    stress.configure()
    assert stress.length == LENGTHS[0]


def test_streaming_panes_are_fed_by_the_clock_and_start_again_when_done(
    theme: Theme, measure: Any
) -> None:
    stress = _stress(theme, measure, count=2, streaming=True)
    total = len(stress.panes[0].pieces)
    starts = [pane.fed for pane in stress.panes]
    assert stress.feed(1.0) == 2 * 40, "forty pieces a second, each pane"
    assert [pane.fed - start for pane, start in zip(stress.panes, starts, strict=True)] == [40, 40]
    assert [pane.took for pane in stress.panes] == [40, 40]
    assert stress.panes[0].stream is not None and stress.panes[0].stream.source != ""

    first = stress.panes[0]
    stress.feed(1000.0)
    assert stress.panes[0] is first and first.fed == total
    stress.feed(0.5)
    again = stress.panes[0]
    assert again is not first and again.laps == 1 and again.fed == 20
    assert again.per_piece is first.per_piece
    assert again.layout is first.layout, "the medians were thrown away at the restart"

    finished = _stress(theme, measure, count=2)
    assert finished.feed(1.0) == 0


def test_streaming_panes_are_staggered_in_place_and_in_time(theme: Theme, measure: Any) -> None:
    """
    Sixteen panes that all start at the first character and all take their
    pieces on the same frames measure one event sixteen times: every pane
    reaches the long table on the same frame. Each pane starts at another
    place in the document, and takes its pieces on other frames.
    """
    stress = _stress(theme, measure, count=4, streaming=True)
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


def test_a_frames_cost_is_also_kept_per_piece_of_text_it_took(theme: Theme, measure: Any) -> None:
    """
    A frame that took three pieces is one sample of a third of its cost per
    piece; a frame that took none is no sample of that at all.
    """
    stress = _stress(theme, measure, count=1, streaming=True)
    (pane,) = stress.panes
    pane.took = 3
    pane.sample(0.001, 0.002)
    assert pane.layout.median_ms == pytest.approx(1.0) and pane.draw.median_ms == pytest.approx(2.0)
    assert pane.per_piece.median_ms == pytest.approx(1.0)
    pane.took = 0
    pane.sample(0.5, 0.5)
    assert len(pane.per_piece.samples) == 1 and len(pane.layout.samples) == 2
    assert stress.per_piece_ms == pytest.approx(1.0)
    assert stress.pieces_per_frame == pytest.approx(1.5)

    finished = _stress(theme, measure, count=2)
    assert finished.per_piece_ms is None and finished.pieces_per_frame == 0.0
    for each in finished.panes:
        each.sample(0.001, 0.003)
    assert finished.total_ms == pytest.approx(8.0)
    assert finished.per_view_ms == pytest.approx(4.0)


# ----------------------------------------------------------------------
# The counters, in real frames
# ----------------------------------------------------------------------


def _frames(app: App, count: int, seconds: float = 1.0 / 60.0) -> None:
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
            imgui.begin("##advtext-stress-page-test", None, imgui.WindowFlags_.no_title_bar.value)
            app.gui()
            imgui.end()
        finally:
            imgui.render()


def _page(spec: str) -> tuple[App, page.StressPage]:
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    made = app.page("stress")
    assert isinstance(made, page.StressPage)
    made.stress.timer = _Clock()
    return app, made


def test_every_pane_is_sampled_once_a_frame_with_layout_and_draw_apart() -> None:
    """
    The fake timer is read three times a pane a frame -- before the layout,
    between the two, after the draw -- so each sample is exactly 1 ms of layout
    and 1 ms of draw, and the totals are those times the number of panes.
    """
    app, made = _page("stress:4")
    _frames(app, 5)
    stress = made.stress
    assert len(stress.panes) == 4
    for pane in stress.panes:
        assert len(pane.layout.samples) == len(pane.draw.samples) == 5
        assert pane.layout.median_ms == pytest.approx(1.0)
        assert pane.draw.median_ms == pytest.approx(1.0)
    assert stress.layout_ms == pytest.approx(4.0) and stress.draw_ms == pytest.approx(4.0)
    assert stress.total_ms == pytest.approx(8.0)


def test_the_glyph_and_unit_counts_are_the_views_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Glyphs: what each `draw` returned, summed. Units: for every pane, drawn
    plus culled is the layout's unit count, and at twenty copies in a pane a
    few hundred pixels tall most of them are culled -- which is the case that
    shows the counter is not simply reporting everything as drawn.
    """
    returned: list[int] = []
    real = BareView.draw

    def recording(self: BareView, **kwargs: Any) -> Any:
        stats = real(self, **kwargs)
        returned.append(stats.glyphs)
        return stats

    monkeypatch.setattr(BareView, "draw", recording)
    app, made = _page("stress:4,x20")
    _frames(app, 2)
    stress = made.stress
    assert stress.glyphs == sum(returned[-4:]) > 0
    for pane in stress.panes:
        layout = pane.view.layout
        assert layout is not None
        assert pane.units_total == len(layout.placed) > 100
        assert pane.units_drawn + pane.units_culled == pane.units_total
        assert 0 < pane.units_drawn < pane.units_total / 4
    assert stress.units_drawn == sum(pane.units_drawn for pane in stress.panes)
    assert stress.units_culled == sum(pane.units_culled for pane in stress.panes)


def test_a_short_document_that_fits_is_all_drawn_and_none_culled() -> None:
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="stress:1")
    made = app.page("stress")
    assert isinstance(made, page.StressPage)
    made.stress = Stress(theme=app.theme, measure=app.measure, source="One line.\n", count=1)
    _frames(app, 2)
    pane = made.stress.panes[0]
    assert (pane.units_total, pane.units_drawn, pane.units_culled) == (1, 1, 0)


def test_culling_keeps_the_glyphs_submitted_flat_as_the_document_grows() -> None:
    """
    The same panes over one copy and over twenty submit a comparable number of
    glyphs: a pane draws a screenful. A count, and the reason the length
    control exists; no time is compared.
    """
    app_one, one = _page("stress:4")
    _frames(app_one, 2)
    app_twenty, twenty = _page("stress:4,x20")
    _frames(app_twenty, 2)
    assert one.stress.glyphs > 0
    assert twenty.stress.glyphs < 2 * one.stress.glyphs
    assert twenty.stress.units_culled > 10 * max(1, one.stress.units_culled)


def test_select_all_selects_every_pane_on_every_frame() -> None:
    """
    A selection belongs to one view at a time, and a view that finds it has
    lost ownership drops its selection. So after a frame only the last pane
    drawn still holds one -- and yet each pane drew its highlight, because the
    page selects each again just before drawing it. Both halves are checked:
    the selection each view had when it drew, and what is left afterwards.
    """
    app, made = _page("stress:3,selected")
    held: list[tuple[bool, bool]] = []
    real = BareView.draw

    def recording(self: BareView, **kwargs: Any) -> Any:
        held.append((self.owns_selection, self.selection != Selection(0, 0)))
        return real(self, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(BareView, "draw", recording)
        _frames(app, 3)
    # The first frame has no layout to select yet; from the second, all do.
    assert held[3:] == [(True, True)] * 6
    panes = made.stress.panes
    assert panes[-1].view.owns_selection
    assert panes[-1].view.selected_text() != ""

    made.stress.select_all = False
    for pane in panes:
        pane.view.clear_selection()
    _frames(app, 1)
    assert all(pane.view.selected_text() == "" for pane in panes)


def test_streaming_panes_lay_out_every_frame_and_finished_ones_do_not() -> None:
    """
    Counted by the views: a `StreamView` with text arriving builds a layout a
    frame; a `BareView` over a finished document builds one and reuses it.
    """
    app, made = _page("stress:2,streaming")
    # A twentieth of a second a frame: two pieces at forty a second, so text
    # arrives on every frame. At a sixtieth it arrives on two frames in three.
    _frames(app, 10, seconds=0.05)
    for pane in made.stress.panes:
        assert isinstance(pane.view, StreamView)
        assert pane.view.relayouts >= 9
        assert pane.fed > 0 and pane.glyphs > 0

    app, made = _page("stress:2")
    _frames(app, 10)
    layouts = [pane.view.layout for pane in made.stress.panes]
    _frames(app, 5)
    now = [pane.view.layout for pane in made.stress.panes]
    assert all(a is b for a, b in zip(now, layouts, strict=True))


# ----------------------------------------------------------------------
# The words on the page
# ----------------------------------------------------------------------


def test_the_readout_shows_the_reference_line_and_does_not_rule_on_it(
    theme: Theme, measure: Any
) -> None:
    """
    The total, the 1.7 ms line and their ratio are on the page. Whether the
    line is met is not -- at a total under it or at one over it. The samples
    are put in by hand so that both sides of the line are certainly reached.
    """

    def lines(count: int, seconds: float) -> tuple[str, ...]:
        stress = _stress(theme, measure, count=count)
        for pane in stress.panes:
            pane.layout.add(seconds)
            pane.draw.add(seconds)
        return readouts(stress)

    under, over = lines(1, 0.0005), lines(16, 0.001)
    assert 1.0 < REFERENCE_MS < 32.0, "the two cases no longer straddle the reference"
    assert "1 panes" in under[0] and "16 panes" in over[0]
    assert "layout 0.50 ms  +  draw 0.50 ms  =  1.00 ms" in under[0]
    assert "layout 16.00 ms  +  draw 16.00 ms  =  32.00 ms" in over[0]
    assert f"reference line {REFERENCE_MS:.1f} ms" in under[1]
    assert f"{1.0 / REFERENCE_MS:.2f} x" in under[1] and f"{32.0 / REFERENCE_MS:.2f} x" in over[1]
    assert "not timed: ImGui's render" in under[3]
    assert "its own layout caches" in under[3]
    # Per view, which is what can be compared across pane counts: the total
    # over the panes, with its own ratio to the line.
    assert "per view 1.00 ms a frame" in under[4] and "per view 2.00 ms a frame" in over[4]
    assert f"{1.0 / REFERENCE_MS:.2f} x" in under[4] and f"{2.0 / REFERENCE_MS:.2f} x" in over[4]
    assert "per piece of text: none taken" in under[4]
    assert "pane measure" in under[4]
    assert "nothing is shared between views" in under[5] and "staggered" in under[5]
    assert len(under) == len(over) == 6
    verdicts = ("within", "exceed", "budget", "meets", "fails", "slow", "fast", "good", "bad")
    for shown in (under, over):
        text = " ".join(shown).lower()
        for word in verdicts:
            assert word not in text, f"the readout says {word!r}"


def test_the_launch_options_set_the_controls() -> None:
    def made(spec: str) -> Stress:
        request = parse_tab_request(spec)
        context = PageContext.build(
            request_page=request.tab,
            request_options=request.options,
            request_count=request.columns,
        )
        return page.StressPage(context).stress

    plain = made("stress")
    assert (len(plain.panes), plain.length, plain.streaming, plain.select_all) == (
        4,
        1,
        False,
        False,
    )
    busy = made("stress:16,streaming,selected,x5")
    assert (len(busy.panes), busy.length, busy.streaming, busy.select_all) == (16, 5, True, True)
    assert made("stress:99").count == MAX_PANES
    assert made("stress:x20").length == 20


def test_the_page_is_discovered_and_its_shots_parse() -> None:
    found = pages.require()
    spec = found.find("stress")
    assert spec is page.PAGE
    for request in spec.shot_specs():
        assert parse_tab_request(request, found).tab == "stress"


# ----------------------------------------------------------------------
# A real window at 1, 4 and 16 panes
# ----------------------------------------------------------------------

TOUR = """
from imgui_bundle import hello_imgui

from advtext.ui import app as advtext_app
from advtext.ui.pages import stress as stress_page

FRAMES = 90
COUNTS = (1, 4, 16)
state = {"frame": 0}
real_gui = advtext_app.App.gui


def touring_gui(self):
    if state["frame"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    made = self.page("stress")
    index, within = divmod(state["frame"], FRAMES)
    if index >= len(COUNTS):
        hello_imgui.get_runner_params().app_shall_exit = True
        return real_gui(self)
    if within == 0:
        made.stress.count = COUNTS[index]
        made.stress.configure()
    if within == FRAMES - stress_page.WINDOW:
        # The medians are of the last WINDOW frames at this count, with the
        # cold frames after the change of count already behind them.
        made.stress.forget()
    real_gui(self)
    if within == FRAMES - 1:
        print(stress_page.report(made.stress))
    state["frame"] += 1


advtext_app.App.gui = touring_gui
advtext_app.run(tab="stress:1")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_the_page_reports_its_figures_at_1_4_and_16_panes_in_a_real_window(
    window: Window, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    The real app on `--tab stress`, ninety frames at each of 1, 4 and 16 panes,
    printing `report` after each: the median of the last sixty.

    Asserted: the counts. A full window of samples at each pane count, glyphs
    submitted, at least one unit drawn in every pane, and the same number of
    units per pane at every count. (Glyphs do not rise with the number of
    panes and nothing says they should: sixteen small panes show about as much
    text as four large ones.) **Not asserted: any time.** The milliseconds are
    echoed to the test's output, labelled with
    where the window was, so a run with `-s` shows them; on an Xvfb they are
    figures from a software rasteriser on a loaded machine.
    """
    script = window.out / "stress_page_tour.py"
    script.write_text(textwrap.dedent(TOUR), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\\n{done.stdout}\\n{done.stderr}"
    lines = [line for line in done.stdout.splitlines() if line.startswith("panes=")]
    assert [_fields(line)["panes"] for line in lines] == ["1", "4", "16"], done.stdout
    units = []
    for line in lines:
        fields = _fields(line)
        panes = int(fields["panes"])
        assert fields["samples"] == str(page.WINDOW)
        assert int(fields["glyphs"]) > 0
        assert int(fields["units_drawn"]) >= panes, "a pane drew no unit at all"
        assert float(fields["total_ms"]) > 0.0
        units.append((int(fields["units_drawn"]) + int(fields["units_culled"])) // panes)
    # Every pane lays out the same document, so each has the same units.
    assert len(set(units)) == 1 and units[0] > 10, units
    with capsys.disabled():
        label = "software-rendered Xvfb" if window.where == "xvfb" else "the session's display"
        print(f"\\nstress page, {label} figures (median of {page.WINDOW} frames):")
        for line in lines:
            print("  " + line)

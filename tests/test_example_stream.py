r"""
The two streaming examples: `examples/stream_replay.py` and `examples/chat_transcript.py`.

Each test says at what fidelity it runs, as `tests/test_examples.py` does:

- **the source text** -- the examples import the library only from the package
  root;
- **plain objects, a clock advanced by hand** -- a whole replay, with the
  moved-lines counter held to what first-fit breaking predicts;
- **real ImGui frames with no display** -- `show`, the controls, the scrolling;
- **a real window** -- `main`, on an Xvfb in a user namespace where one can be
  started.

**What the counter is held to.** `tests/test_stream_stability.py` and
`tests/test_firstfit.py` established that a first-fit line depends only on the
text up to its own end. From that: plain prose streamed under
`KEEP_STREAMED` moves no settled line, at any measure, however the stream is
cut; and where lines do move there is a cause that can be named -- markup that
closed late, a table whose column grew, or a `RESET` at a commit. Each of those
is a test here, and the first is the one the plan asked for.

Nothing in this file says how any of it looks. Nobody has watched it.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import advtext
from advtext import (
    Align,
    BareView,
    CodeBlock,
    CommitPolicy,
    Face,
    StreamView,
    TableBlock,
    TextBlock,
    Theme,
    build_document,
    char_measure,
    fontlib_metrics,
    sp_from_px,
)
from advtext.nodes import CharNode
from advtext.selection import Selection
from advtext.style import parse_font_key

_ROOT = Path(__file__).resolve().parent.parent
_REPLAY = _ROOT / "examples" / "stream_replay.py"
_CHAT = _ROOT / "examples" / "chat_transcript.py"
_PROBE = _ROOT / "scripts" / "mouse_probe.py"

XVFB_REPLAY, XVFB_CHAT = 95, 93
"""
One TCP display each, and neither is 99 (the probe), 97 (`tests/test_examples.py`)
or 96 (`tests/test_example_gallery.py`): the servers share a network namespace.
"""

PROSE = (
    "The first paragraph of plain prose, with no markup in it at all, written over\n"
    "several source lines so that it settles before the one after it is finished,\n"
    "and long enough to be set on four or five lines at the width the test uses.\n"
    "\n"
    "A second paragraph follows it, equally plain, so that there is a block that\n"
    "commits while another is still arriving, and then a third to end on, each of\n"
    "them carrying enough words to wrap more than once.\n"
    "\n"
    "The third and last paragraph is here so that the second one commits before\n"
    "the stream closes, and it too runs on for a few lines before it stops.\n"
)
"""
Three paragraphs with nothing in them that could change a character already shown.
"""


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        pytest.fail(f"{path} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def replay_module(bundled_fonts: Any) -> ModuleType:
    return _load(_REPLAY, "advtext_example_stream_replay")


@pytest.fixture(scope="module")
def chat_module(bundled_fonts: Any) -> ModuleType:
    return _load(_CHAT, "advtext_example_chat_transcript")


# ----------------------------------------------------------------------
# the source text


@pytest.mark.parametrize("path", [_REPLAY, _CHAT], ids=["stream_replay", "chat_transcript"])
def test_the_examples_import_advtext_only_from_the_package_root(path: Path) -> None:
    """
    Fidelity: the source text. "Public facade only", held by reading the imports.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    from_root: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("advtext"), f"import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("advtext."), f"from {module} import ..."
            if module == "advtext":
                from_root.extend(alias.name for alias in node.names)
    assert {"StreamView", "StreamDocument"} <= set(from_root)
    assert set(from_root) <= set(advtext.__all__)


@pytest.mark.parametrize("path", [_REPLAY, _CHAT], ids=["stream_replay", "chat_transcript"])
def test_loading_an_example_loads_neither_the_demo_app_nor_a_window_runner(path: Path) -> None:
    """
    Fidelity: a fresh interpreter, by import graph.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("example", {str(path)!r})
                example = importlib.util.module_from_spec(spec)
                sys.modules["example"] = example
                spec.loader.exec_module(example)
                names = ("advtext.ui.app", "imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                print([name for name in names if name in sys.modules])
                made = example.replay() if hasattr(example, "replay") else example.Transcript()
                made.advance(1.0)
                print("advtext.ui.app" in sys.modules)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    assert result.returncode == 0, result.stderr
    # Loading the file loads no window runner. Building what it shows reads
    # font files, which the library finds through `imgui_bundle`; the demo
    # application is still not involved.
    assert result.stdout.splitlines() == ["[]", "False"]


# ----------------------------------------------------------------------
# the replay, with a clock advanced by hand


def run_to_the_end(playing: Any, width_px: float, *, step: float = 1.0 / 60.0) -> int:
    """
    Tick a replay at sixty frames a second of pretend time until it is done. Returns the frames.
    """
    frames = 0
    width = sp_from_px(width_px)
    while not playing.done:
        playing.tick(step, width)
        frames += 1
        assert frames < 200_000, "the replay never finished"
    playing.tick(step, width)
    return frames + 1


def test_tokens_cut_the_source_into_small_pieces_that_join_back_to_it(
    replay_module: ModuleType,
) -> None:
    source = replay_module.SOURCE.read_text(encoding="utf-8")
    pieces = replay_module.tokens(source)
    assert "".join(pieces) == source
    assert len(pieces) > 500
    assert max(len(piece.strip()) for piece in pieces) <= 4
    # The cut is arbitrary on purpose: some markup arrives split.
    assert any(piece.strip() == "*" or piece.strip().endswith("*") for piece in pieces)


def test_the_clock_decides_how_many_pieces_arrive_and_fractions_are_carried(
    replay_module: ModuleType,
) -> None:
    """
    Fidelity: plain objects. Forty a second for a second is forty, whatever the frame time.
    """
    playing = replay_module.replay(PROSE, tokens_per_second=40.0)
    assert playing.advance(0.0) == 0
    fed = sum(playing.advance(1.0 / 60.0) for _ in range(60))
    assert fed == 40 == playing.fed
    # A frame too short for a whole piece still counts towards the next one.
    playing.tokens_per_second = 30.0
    assert [playing.advance(1.0 / 60.0) for _ in range(4)] == [0, 1, 0, 1]
    # Nothing arrives at rate zero, and the stream is not closed early.
    playing.tokens_per_second = 0.0
    assert playing.advance(10.0) == 0 and not playing.done

    playing.tokens_per_second = 1e9
    assert playing.advance(1.0) == len(playing.pieces) - 42
    assert playing.done and playing.stream.closed
    assert playing.advance(1.0) == 0


@pytest.mark.parametrize("width_px", [360.0, 560.0])
@pytest.mark.parametrize("rate", [40.0, 700.0])
def test_plain_prose_streamed_and_kept_moves_no_settled_line(
    replay_module: ModuleType, width_px: float, rate: float
) -> None:
    """
    Fidelity: a whole replay, plain objects. **The prediction the plan asked to be held.**

    First-fit at natural spacing sets each line from the text up to its own
    end, so nothing arriving later can move it; `KEEP_STREAMED` commits the
    block as it was. Two measures and two rates -- one piece every frame or
    two, and a dozen pieces a frame -- because the count must not depend on
    how the stream happened to be cut into frames.
    """
    playing = replay_module.replay(PROSE, tokens_per_second=rate)
    frames = run_to_the_end(playing, width_px)
    assert playing.done and frames > 10
    assert playing.moved == 0 and playing.moves == []
    # And there were settled lines to move: the paragraphs wrapped.
    assert len(replay_module.lines_of(playing.view)) >= 8
    assert playing.view.relayouts >= frames // 4


def test_resetting_on_commit_moves_lines_and_only_when_a_block_commits(
    replay_module: ModuleType,
) -> None:
    """
    Fidelity: a whole replay. The other policy: lines move, at commits and nowhere else.
    """
    playing = replay_module.replay(PROSE, policy=CommitPolicy.RESET, tokens_per_second=60.0)
    width = sp_from_px(360.0)
    moved_at_a_commit: list[int] = []
    while not playing.done:
        settled = len(playing.stream.committed) if playing.fed else 0
        moved = playing.tick(1.0 / 60.0, width)
        committed = len(playing.stream.committed) > settled
        if moved:
            assert committed, f"{moved} lines moved at piece {playing.fed} with nothing committing"
            moved_at_a_commit.append(moved)
    # Three paragraphs, each of several lines, each set again once.
    assert len(moved_at_a_commit) == 3
    assert all(count >= 2 for count in moved_at_a_commit)
    assert playing.moved == sum(moved_at_a_commit)
    assert [count for _, count in playing.moves] == moved_at_a_commit


def _extends(before: Any, after: Any) -> bool:
    """
    Whether block `after` is block `before` with more text on the end and nothing else changed.
    """
    if isinstance(before, TextBlock) and isinstance(after, TextBlock):
        return (
            before.kind is after.kind
            and after.material[: len(before.material)] == before.material
            and before.marker == after.marker
        )
    if isinstance(before, CodeBlock) and isinstance(after, CodeBlock):
        # Every line but the last, which is the one being typed.
        return after.lines[: len(before.lines) - 1] == before.lines[:-1]
    return before == after


def test_on_the_demo_document_every_line_that_moves_has_a_cause_that_can_be_named(
    replay_module: ModuleType,
) -> None:
    """
    Fidelity: a whole replay of `demo/stream.md`, kept. Not zero, and never without a reason.

    The document was written to change its mind: emphasis that opens long
    before it closes, a code span, a table. A settled line may move for two
    reasons and no other, and both are read off the blocks, not guessed from
    the characters that happened to arrive (the test this replaces called a
    step explained if its pieces contained an asterisk, a backtick or a bar,
    which most steps of this document do):

    - **the text before it changed** -- some block at or above the line's own,
      among those not yet committed, is no longer its old self with more on
      the end: an asterisk that turned out to be markup, a paragraph that
      became a heading, a block that split;
    - **a table moved it** -- the line is a table's, or a table above it grew.

    A line that moved in a block that only gained text, under nothing that
    changed, is the failure first-fit breaking exists to rule out, and is
    reported with the line and the step.
    """
    playing = replay_module.replay(tokens_per_second=60.0)
    width = sp_from_px(520.0)
    causes: list[str] = []
    while not playing.done:
        before = playing.stream.blocks
        settled = len(playing.stream.committed)
        fed = playing.fed
        if not playing.tick(1.0 / 60.0, width):
            continue
        after = playing.stream.blocks
        for line in playing.changed:
            above = range(settled, line.block + 1)
            if any(isinstance(before[index], TableBlock) for index in above):
                causes.append("table")
            elif any(
                index >= len(after) or not _extends(before[index], after[index]) for index in above
            ):
                causes.append("text changed")
            else:
                arrived = "".join(playing.pieces[fed : playing.fed])
                causes.append(f"unexplained: block {line.block} after {arrived!r}")
    assert causes, "nothing moved; the document no longer changes its mind"
    assert set(causes) == {"text changed", "table"}, sorted(set(causes))
    assert len(causes) == playing.moved
    # The counter is small against the document: tens of settled lines, a
    # handful moved. (A count, quoted so a change in it is seen; not a grade.)
    assert playing.moved < len(replay_module.lines_of(playing.view)) // 2


def test_a_line_that_moves_for_no_reason_would_be_called_unexplained() -> None:
    """
    The control for the test above: its two reasons do not cover everything.

    A paragraph that only gained words is its old self extended, so a line of
    it that moved has no cause the test accepts; the same paragraph with its
    opening asterisks turned into bold is not.
    """
    theme = Theme.build()
    short = build_document("Some plain words", theme, fontlib_metrics).blocks[0]
    longer = build_document("Some plain words and more", theme, fontlib_metrics).blocks[0]
    literal = build_document("Some **plain words", theme, fontlib_metrics).blocks[0]
    bold = build_document("Some **plain words**", theme, fontlib_metrics).blocks[0]
    assert _extends(short, longer)
    assert not _extends(literal, bold)
    assert not _extends(longer, short)


def test_a_finished_replay_reads_as_the_document_does(replay_module: ModuleType) -> None:
    """
    Fidelity: plain objects. Streaming is a way of arriving, not a different document.
    """
    source = replay_module.SOURCE.read_text(encoding="utf-8")
    playing = replay_module.replay(policy=CommitPolicy.RESET, tokens_per_second=5000.0)
    run_to_the_end(playing, 560.0)
    view = playing.view
    view.select_all()

    plain = BareView(
        document=build_document(source, playing.theme, fontlib_metrics, references=False),
        theme=playing.theme,
        measure=char_measure(fontlib_metrics),
    )
    plain.layout_for(sp_from_px(560.0))
    plain.select_all()
    assert view.selected_text() == plain.selected_text()
    assert len(view.selected_text()) > 1500


def test_restarting_under_the_other_policy_starts_the_count_again(
    replay_module: ModuleType,
) -> None:
    playing = replay_module.replay(PROSE, policy=CommitPolicy.RESET, tokens_per_second=5000.0)
    run_to_the_end(playing, 560.0)
    assert playing.moved > 0 and playing.done
    first_view = playing.view
    playing.restart(CommitPolicy.KEEP_STREAMED)
    assert (playing.fed, playing.moved, playing.moves) == (0, 0, [])
    assert playing.view is not first_view and not playing.done
    assert playing.policy is CommitPolicy.KEEP_STREAMED
    run_to_the_end(playing, 560.0)
    assert playing.moved == 0


def test_a_change_of_width_is_not_counted_as_the_stream_moving_lines(
    replay_module: ModuleType,
) -> None:
    """
    Review 4, item 7 (measured: a finished replay narrowed from 560 to 400 px counted 4).

    The counter is of lines moved *by text arriving*. A resize sets every
    line again and says nothing about the stream, so a layout at a new width
    starts the comparison over. The control is that the count still works
    after one: the same replay under `RESET`, resized half way, goes on to
    count the lines its commits move.
    """
    playing = replay_module.replay(PROSE, tokens_per_second=1e9)
    playing.tick(1.0, replay_module.page_width(560.0))
    playing.tick(0.0, replay_module.page_width(560.0))
    assert playing.done and playing.moved == 0
    assert playing.tick(0.0, replay_module.page_width(400.0)) == 0
    assert playing.tick(0.0, replay_module.page_width(560.0)) == 0
    assert playing.moved == 0 and playing.moves == []

    resized = replay_module.replay(PROSE, policy=CommitPolicy.RESET, tokens_per_second=600.0)
    wide, narrow = replay_module.page_width(560.0), replay_module.page_width(400.0)
    while resized.fed < len(resized.pieces) // 3:
        resized.tick(1.0 / 60.0, wide)
    assert resized.moved == 0, "nothing has committed yet in the first third"
    assert resized.tick(0.0, narrow) == 0, "the resize itself was counted"
    while not resized.done:
        resized.tick(1.0 / 60.0, narrow)
    assert resized.moved > 0, "the counter stopped counting after a resize"


def test_moved_lines_counts_what_changed_and_never_the_line_being_written(
    replay_module: ModuleType,
) -> None:
    """
    Fidelity: the function, on lines written out by hand.
    """
    moved = replay_module.moved_lines
    a = (((65, 0), (66, 10)), 100)
    b = (((67, 0), (68, 10)), 120)
    growing = (((69, 0),), 140)
    grown = (((69, 0), (70, 10)), 140)
    assert moved([a, b, growing], [a, b, grown]) == 0
    assert moved([a, b, growing], [a, b, grown, (((71, 0),), 160)]) == 0
    # The same glyphs one unit to the right is a line that moved.
    shifted = (((67, 1), (68, 11)), 120)
    assert moved([a, b, growing], [a, shifted, grown]) == 1
    # So is the same line one unit down.
    lower = (((67, 0), (68, 10)), 121)
    assert moved([a, b, growing], [a, lower, grown]) == 1
    assert moved([], [a]) == 0 and moved([a], []) == 0
    assert moved([a, b], []) == 1


# ----------------------------------------------------------------------
# real frames, no display


def _frame(module: ModuleType, made: Any, seconds: float, *, wheel: float | None = None) -> Any:
    """
    One real frame with an example's `show` in a window that fills the display.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(900.0, 500.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.add_mouse_pos_event(450.0, 300.0)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(900.0, 500.0))
        flags = imgui.WindowFlags_.no_decoration.value | imgui.WindowFlags_.no_move.value
        imgui.begin(f"##advtext-{module.__name__}", None, flags)
        result = module.show(made, lambda face: None, imgui, seconds)
        imgui.end()
    finally:
        imgui.render()
    return result


def test_the_replay_window_feeds_draws_and_counts_frame_by_frame(
    replay_module: ModuleType,
) -> None:
    """
    Fidelity: real ImGui frames, no display. `show` end to end, with the time passed in.
    """
    playing = replay_module.replay(tokens_per_second=600.0)
    frames = 0
    while not playing.done and frames < 400:
        stats = _frame(replay_module, playing, 1.0 / 60.0)
        frames += 1
    assert playing.done and 30 < frames < 200
    for _ in range(3):
        stats = _frame(replay_module, playing, 1.0 / 60.0)
    assert stats.glyphs > 100
    # One layout a frame at the most, though ten pieces arrived in each.
    assert playing.view.relayouts <= frames + 3
    assert playing.fed == len(playing.pieces) > 10 * playing.view.relayouts // 2
    # The pane followed the text down, and the status line says what happened.
    assert playing.view.following
    status = playing.status()
    assert f"{playing.fed} of {len(playing.pieces)} pieces" in status
    assert f"settled lines moved: {playing.moved}" in status and "following the end" in status
    assert playing.moved > 0

    # Wheel up: the pane lets go, and says so.
    _frame(replay_module, playing, 1.0 / 60.0, wheel=4.0)
    _frame(replay_module, playing, 1.0 / 60.0)
    assert not playing.view.following
    assert "scrolled away from the end" in playing.status()
    report = replay_module.report(playing, frames)
    assert report[0].startswith(f"frames={frames} fed={playing.fed} ")
    assert "done=1 policy=KEEP_STREAMED" in report[0]


# ----------------------------------------------------------------------
# the chat transcript


def _faces(document: Any) -> set[Face]:
    faces: set[Face] = set()
    for block in document.blocks:
        nodes: list[Any] = []
        if isinstance(block, TextBlock):
            nodes = [*block.material, *block.marker]
        elif hasattr(block, "lines"):
            nodes = [node for line in block.lines for node in line]
        elif isinstance(block, TableBlock):
            nodes = [
                n for row in (block.header, *block.rows) for cell in row for n in cell.material
            ]
        faces.update(parse_font_key(n.font).face for n in nodes if isinstance(n, CharNode))
    return faces


def test_the_transcript_is_one_monospace_face_set_ragged(chat_module: ModuleType) -> None:
    """
    Fidelity: plain objects. "Mono ragged" checked on the blocks, not taken from the call.
    """
    transcript = chat_module.Transcript()
    transcript.advance(1e9)
    transcript.live.sync()
    assert transcript.done and len(transcript.messages) == 4
    assert [message.role for message in transcript.messages] == [
        "you",
        "assistant",
        "you",
        "assistant",
    ]
    for message in transcript.messages:
        document = message.view.document
        assert _faces(document) == {Face.CODE}, message.role
        aligns = {block.style.align for block in document.blocks if isinstance(block, TextBlock)}
        assert aligns == {Align.LEFT}
    # The streaming message really is the kind of thing a model writes.
    kinds = {type(block).__name__ for block in transcript.live.document.blocks}
    assert {"TextBlock", "CodeBlock", "TableBlock"} <= kinds
    assert isinstance(transcript.live, StreamView)
    assert all(not isinstance(m.view, StreamView) for m in transcript.messages[:-1])


def test_a_message_reads_the_same_finished_as_it_did_while_it_streamed(
    chat_module: ModuleType,
) -> None:
    """
    One setting for link reference definitions, in both kinds of message (review 4, item 7).

    A stream cannot read `[1]: url` definitions -- one may arrive last and
    change every `[1]` before it -- so a streamed message sets them as text.
    Finished messages used to be built with definitions on, and the same text
    was a link there: a host that swapped a finished stream for a document
    built this way would see the message change under the reader. Both are
    read with definitions off now. The control is the library's default,
    which does make the link.
    """
    text = "See [the notes][1] for more.\n\n[1]: https://example.org/notes\n"
    transcript = chat_module.Transcript(finished=(("you", text),), streaming=("model", text))
    while not transcript.done:
        transcript.advance(1.0)
    transcript.stream.close()
    finished = transcript.messages[0].view.document.blocks
    streamed = transcript.stream.blocks
    assert len(finished) == len(streamed) == 2
    assert [getattr(block, "links", ()) for block in finished] == [(), ()]
    assert [block.material for block in finished] == [block.material for block in streamed]

    from advtext import build_document

    default = build_document(text, transcript.theme, transcript.metrics)
    assert len(default.blocks) == 1 and default.blocks[0].links  # type: ignore[union-attr]


def test_text_arriving_in_the_last_message_costs_the_finished_ones_nothing(
    chat_module: ModuleType,
) -> None:
    """
    Fidelity: real ImGui frames, no display. Counted, not timed.

    While the last message streams, each finished message's view builds no
    layout and ships no unit: its caches are exactly as the first frames left
    them.
    """
    transcript = chat_module.Transcript(tokens_per_second=600.0)
    _frame(chat_module, transcript, 0.0)
    _frame(chat_module, transcript, 0.0)
    finished = transcript.messages[:-1]
    layouts = [message.view.layout for message in finished]
    shipped = [message.view._units.stats().misses for message in finished]
    assert all(layout is not None for layout in layouts)

    frames = 0
    while not transcript.done and frames < 300:
        _frame(chat_module, transcript, 1.0 / 60.0)
        frames += 1
    stats = _frame(chat_module, transcript, 1.0 / 60.0)
    assert transcript.done and frames > 5
    assert [message.view.layout for message in finished] == layouts
    assert all(a is b for a, b in zip((m.view.layout for m in finished), layouts, strict=True))
    assert [message.view._units.stats().misses for message in finished] == shipped
    assert transcript.live.relayouts >= frames // 2
    # The pane has followed the last message down, so the first one is off
    # screen by now and draws nothing: culled, not laid out again.
    assert len(stats) == 4 and stats[-1].glyphs > 100
    assert sum(one.glyphs for one in stats) > 300
    assert "last one finished" in transcript.status()


def test_one_selection_across_the_transcript_and_the_copy_is_the_last_ones(
    chat_module: ModuleType,
) -> None:
    """
    Fidelity: real ImGui frames, no display.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    transcript = chat_module.Transcript(tokens_per_second=1e9)
    _frame(chat_module, transcript, 1.0)
    _frame(chat_module, transcript, 0.0)
    first, last = transcript.messages[1].view, transcript.live
    first.select_all()
    _frame(chat_module, transcript, 0.0)
    assert first.owns_selection and first.selected_text().startswith("Hang the marker")
    # The numbered list keeps its numbers and its lines.
    assert "\n1. Break the item" in first.selected_text()

    last.select(Selection(0, 12))
    _frame(chat_module, transcript, 0.0)
    assert last.owns_selection and first.selection.is_empty
    imgui.set_clipboard_text("SENTINEL")
    io = imgui.get_io()
    for down in (True, False):
        io.add_key_event(imgui.Key.mod_ctrl, down)
        io.add_key_event(imgui.Key.c, down)
        _frame(chat_module, transcript, 0.0)
    assert imgui.get_clipboard_text() == last.selected_text() != ""


def test_the_transcript_follows_its_last_message_down(chat_module: ModuleType) -> None:
    """
    Fidelity: real ImGui frames, no display. One scrollbar, moved by the streaming view.
    """
    transcript = chat_module.Transcript(tokens_per_second=300.0)
    frames = 0
    while not transcript.done and frames < 300:
        _frame(chat_module, transcript, 1.0 / 60.0)
        frames += 1
    for _ in range(3):
        _frame(chat_module, transcript, 0.0)
    assert transcript.live.following
    assert transcript.live.origin is not None
    # The last message began below where the pane began: the conversation is
    # taller than the window and the pane has scrolled to keep its end in view.
    first_origin = transcript.messages[0].view.origin
    assert first_origin is not None and first_origin[1] < 0.0


# ----------------------------------------------------------------------
# a real window


def _can_make_a_namespace() -> bool:
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-rm", "true"], capture_output=True, check=False)
    return done.returncode == 0


def _run_main(path: Path, display: int, *arguments: str) -> list[dict[str, str]]:
    """
    An example's `main` in a GLFW window on an Xvfb, and the lines it printed as dicts.
    """
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which the Xvfb recipe needs")
    probe = _load(_PROBE, f"advtext_mouse_probe_for_{path.stem}")
    inner = textwrap.dedent(f"""
        import os, runpy, sys
        sys.path.insert(0, {str(_PROBE.parent)!r})
        from mouse_probe import wait_for_tcp_display
        if not wait_for_tcp_display(os.environ["DISPLAY"], timeout=30.0):
            raise SystemExit("the Xvfb never accepted a connection")
        sys.argv = [{str(path)!r}, *{list(arguments)!r}]
        runpy.run_path({str(path)!r}, run_name="__main__")
        """)
    command = probe.xvfb_command([sys.executable, "-c", inner], display=display)
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=180, check=False, cwd=_ROOT
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = [
        line
        for line in done.stdout.splitlines()
        if re.match(r"^(frames|layouts|glyphs|message)=", line)
    ]
    assert lines, done.stdout + done.stderr
    return [dict(part.split("=", 1) for part in line.split()) for line in lines]


def test_the_replay_runs_to_the_end_in_a_real_window() -> None:
    """
    Fidelity: `main()` itself, in a GLFW window with an OpenGL context, on Xvfb.

    A rate high enough to feed the whole document well inside the frames
    asked for, so the report is of a finished replay: every piece fed, the
    stream closed, glyphs drawn with none missing, the pane at the end.

    Software rendering and no window manager: a real window, not a desktop.
    Nobody looked at it.
    """
    first, second, third = _run_main(
        _REPLAY, XVFB_REPLAY, "--frames", "90", "--tps", "100000", "--policy", "RESET"
    )
    assert first["frames"] == "90" and first["done"] == "1" and first["policy"] == "RESET"
    assert first["fed"] == first["pieces"] and int(first["pieces"]) > 500
    assert int(second["layouts"]) >= 1 and second["following"] == "1"
    assert int(third["glyphs"]) > 100 and third["missing"] == "0"
    assert third["blocks"] == third["committed"]


def test_the_transcript_runs_in_a_real_window() -> None:
    """
    Fidelity: `main()` itself, in a GLFW window on Xvfb. Four messages drawn, the last one fed.
    """
    *messages, total = _run_main(_CHAT, XVFB_CHAT, "--frames", "60", "--tps", "100000")
    assert [message["role"] for message in messages] == ["you", "assistant", "you", "assistant"]
    assert all(int(message["glyphs"]) > 20 for message in messages)
    assert all(message["missing"] == "0" for message in messages)
    assert total["messages"] == "4" and total["done"] == "1" and total["frames"] == "60"

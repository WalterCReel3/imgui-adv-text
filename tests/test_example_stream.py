r"""
The two streaming examples: `examples/stream_replay.py` and `examples/chat_transcript.py`.

Both draw through the imtypeset library and through nothing else. Each test
says at what fidelity it runs, as `tests/test_examples.py` does:

- **the source text** -- what the examples import, anywhere in the file;
- **a fresh interpreter** -- what loading one loads;
- **plain objects, no library** -- the pieces, the clock, the counter's
  arithmetic, the transcript's theme: what an example is before it is shown;
- **`main` with no library** -- it says why on standard error and returns
  `NO_LIBRARY` without opening a window;
- **real ImGui frames with no display, the library loaded** -- `show`, the
  controls, the scrolling, in one child (`_HEADLESS`) that says whether
  `typesetter.module()` and `ready()` held THERE, before its body and after;
- **a real window** -- `main`, on an Xvfb in a user namespace where one can be
  started, with the library.

The last two are skipped, with the reason, when `IMTYPESET_LIBRARY` is not
set. The pytest process never has the library ready (also under
`make test TYPESET=1`), so nothing here draws in it.

**What the counter is held to.** `RESET` moves lines, and only on a draw that
found a block committed; a change of width is not a move; nothing is counted
without a draw. How many settled lines `KEEP_STREAMED` moves is the library's
line breaking and is reported, not asserted.

Nothing in this file says how any of it looks. Nobody has watched it.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import imscribe
from imscribe import Align, Face, typesetter
from imscribe.description import FACE_DEFAULT, FACE_ROLES
from imscribe.typeset_markdown import (
    MarkdownCode,
    MarkdownConverter,
    MarkdownStream,
    MarkdownTable,
    MarkdownText,
    parse_markdown,
)

_ROOT = Path(__file__).resolve().parent.parent
_REPLAY = _ROOT / "examples" / "stream_replay.py"
_CHAT = _ROOT / "examples" / "chat_transcript.py"
_PROBE = _ROOT / "scripts" / "mouse_probe.py"
_BOTH = pytest.mark.parametrize("path", [_REPLAY, _CHAT], ids=["stream_replay", "chat_transcript"])

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


_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_SKIP = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)

TYPESET_LAYER: set[str] = set()
"""
The modules of the typeset layer an example may import by their own path:
none, since T5-B2 put the layer's names on the facade. Until then it was
`imscribe.typeset_markdown`, `imscribe.ui.typeset_view` and
`imscribe.ui.typeset_stream_view`.
"""

OLD_NAMES = {
    "BareView",
    "DocumentView",
    "StreamView",
    "StreamDocument",
    "CommitPolicy",
    "DiffView",
    "DiffFences",
    "build_document",
    "live_theme",
    "char_measure",
    "fontlib_metrics",
    "load_faces",
    "markdown_math",
    "draw_document",
}
"""
Names of the old views, the old stream, the old converter and the old draw
backend. Most are gone from the facade (T5-B2); `build_document`,
`char_measure`, `fontlib_metrics` and `load_faces` are still on it, for the
reference core and the no-library UI font. An example imports none.
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
    return _load(_REPLAY, "imscribe_example_stream_replay")


@pytest.fixture(scope="module")
def chat_module(bundled_fonts: Any) -> ModuleType:
    return _load(_CHAT, "imscribe_example_chat_transcript")


# ----------------------------------------------------------------------
# the source text


@_BOTH
def test_the_examples_import_the_facade_and_the_typeset_layer_and_nothing_old(path: Path) -> None:
    """
    Fidelity: the source text, every import in the file, a function's body included.

    From the package root, names in `imscribe.__all__` and the module
    `typesetter`; no submodule of imscribe by its own path (`TYPESET_LAYER`,
    which is empty). No old view, old stream, old converter or old font
    loader by any route: not from the root (`OLD_NAMES`) and not by module.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    from_root: list[str] = []
    by_name: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("imscribe"), f"import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("imscribe."):
                by_name.add(module)
            if module == "imscribe":
                from_root.extend(alias.name for alias in node.names)
    assert by_name <= TYPESET_LAYER, sorted(by_name - TYPESET_LAYER)
    assert {"TypesetStreamView", "MarkdownStream", "TypesetUnavailable"} <= set(from_root)
    assert "typesetter" in from_root and "Theme" in from_root
    assert set(from_root) - {"typesetter"} <= set(imscribe.__all__)
    assert not set(from_root) & OLD_NAMES, sorted(set(from_root) & OLD_NAMES)
    # And no attribute of the package root reached without an import.
    reached = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "imscribe"
    }
    assert not reached, sorted(reached)


@_BOTH
def test_importing_an_example_loads_none_of_the_old_core(path: Path) -> None:
    """
    Fidelity: a fresh interpreter, by import graph.

    None of it (`tests/test_typeset_closure.py`, whose list of the old core
    this reads; `imscribe.units` and `imscribe.fontmetrics` were the floor of
    everything that names a `Theme` until T5-B2), and none of `imscribe.style`,
    `imscribe.stream`, `imscribe.markdown`.
    """
    from test_typeset_closure import OLD_CORE, THEME

    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            textwrap.dedent(f"""
                import importlib.util, json, sys
                spec = importlib.util.spec_from_file_location("example", {str(path)!r})
                example = importlib.util.module_from_spec(spec)
                sys.modules["example"] = example
                spec.loader.exec_module(example)
                print(json.dumps(sorted(n for n in sys.modules if n.startswith("imscribe"))))
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env={**env, "PYTHONPATH": str(_ROOT)},
    )
    assert result.returncode == 0, result.stderr
    loaded = set(json.loads(result.stdout))
    assert "imscribe.ui.typeset_stream_view" in loaded
    assert loaded & OLD_CORE == THEME, sorted(loaded & OLD_CORE)
    for name in ("imscribe.stream", "imscribe.markdown", "imscribe.style", "imscribe.ui.fonts"):
        assert name not in loaded, name


@_BOTH
def test_loading_an_example_loads_neither_the_demo_app_nor_a_window_runner(path: Path) -> None:
    """
    Fidelity: a fresh interpreter, by import graph. And what an example is
    before it is shown needs no library: it is made, and its clock advanced,
    with the library's variables removed.
    """
    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
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
                names = ("imscribe.ui.app", "imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                print([name for name in names if name in sys.modules])
                made = example.replay() if hasattr(example, "replay") else example.Transcript()
                print(made.advance(1.0), "imtypeset" in sys.modules)
                print("imscribe.ui.app" in sys.modules)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env={**env, "PYTHONPATH": str(_ROOT)},
    )
    assert result.returncode == 0, result.stderr
    # Loading the file loads no window runner. Forty pieces in the first
    # second, with nothing of the library imported; the demo application is
    # still not involved.
    assert result.stdout.splitlines() == ["[]", "40 False", "False"]


# ----------------------------------------------------------------------
# the replay: plain objects, no library


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
    assert playing.stream.source == PROSE


def test_a_replay_is_a_stream_and_no_view_until_it_is_shown(replay_module: ModuleType) -> None:
    """
    Fidelity: plain objects, in a process where the library is not ready. The
    two policies are one theme or two; a tick feeds and counts nothing, and
    the status line and the report are made without a view.
    """
    keep = replay_module.replay(PROSE, tokens_per_second=600.0)
    reset = replay_module.replay(PROSE, policy="RESET", tokens_per_second=600.0)
    ragged = replay_module.ragged(keep.theme)
    assert ragged != keep.theme and replay_module.ragged(ragged) is ragged
    assert type(keep.stream) is MarkdownStream and keep.view is None and reset.view is None
    assert keep.stream.theme == ragged and keep.stream.live_theme == ragged
    assert reset.stream.theme is reset.theme and reset.stream.live_theme == ragged
    assert all(
        block.style.align is Align.LEFT
        for block in parse_markdown(PROSE, ragged).blocks
        if isinstance(block, MarkdownText)
    )

    assert keep.tick(1.0 / 60.0) == 0 and keep.fed == 10 and keep.view is None
    assert keep.observe() == 0 and keep.edits == {"set": 0, "replace": 0, "append": 0}
    status = keep.status()
    assert f"10 of {len(keep.pieces)} pieces at 600/s" in status and "KEEP_STREAMED" in status
    assert "settled lines moved: 0 (in 0 of 0 edits)" in status and "following the end" in status
    first, second, third = replay_module.report(keep, 7)
    assert first.startswith("frames=7 fed=10 ") and "done=0 policy=KEEP_STREAMED" in first
    assert first.endswith("renderer=TypesetStreamView ready=0")
    assert second.startswith("edits=0 appends=0 replaces=0 moved=0 ")
    assert third.startswith("vertices=0 whole=1 blocks=")


def test_restarting_under_the_other_policy_starts_the_count_again(
    replay_module: ModuleType,
) -> None:
    playing = replay_module.replay(PROSE, policy="RESET", tokens_per_second=5000.0)
    while not playing.done:
        playing.tick(1.0 / 60.0)
    first_stream = playing.stream
    playing.moved, playing.moves = 3, [(10, 3)]
    playing.restart("KEEP_STREAMED")
    assert (playing.fed, playing.moved, playing.moves) == (0, 0, [])
    assert playing.stream is not first_stream and not playing.done
    assert playing.policy == "KEEP_STREAMED" and playing.stream.source == ""
    assert playing.stream.live_theme == playing.stream.theme
    with pytest.raises(ValueError, match="SOMETIMES"):
        playing.restart("SOMETIMES")


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
# the chat transcript: plain objects, no library


def test_the_transcript_is_one_monospace_face_set_ragged(chat_module: ModuleType) -> None:
    """
    Fidelity: plain objects. "Mono ragged" checked on the blocks each message
    is read into and on what they are described with for the library, not
    taken from the call: every style and every run is the code face (or the
    block's own, which is), and every block of text is ragged.
    """
    transcript = chat_module.Transcript()
    assert transcript.advance(1e9) == len(transcript.pieces)
    assert transcript.done and len(transcript.messages) == 4
    assert [message.role for message in transcript.messages] == [
        "you",
        "assistant",
        "you",
        "assistant",
    ]
    assert all(message.view is None for message in transcript.messages)
    assert transcript.live is None and "following the end" in transcript.status()
    faces = transcript.theme.faces
    assert {faces.regular, faces.bold, faces.italic, faces.bold_italic, faces.code} == {Face.CODE}
    mono = {FACE_DEFAULT, FACE_ROLES["CODE"], FACE_ROLES["CODE_BOLD"]}
    read = [
        parse_markdown(message.markdown, transcript.theme, references=False).blocks
        for message in transcript.messages[:-1]
    ]
    read.append(tuple(transcript.stream.blocks))
    for blocks in read:
        described = MarkdownConverter(transcript.theme).describe(blocks)
        assert {style.Face for style in described.styles} <= mono - {FACE_DEFAULT}
        assert {run.face for block in described.blocks for run in block.runs} <= mono
        aligns = {block.style.align for block in blocks if isinstance(block, MarkdownText)}
        assert aligns == {Align.LEFT}
    # The streaming message really is the kind of thing a model writes.
    kinds = {type(block) for block in transcript.stream.blocks}
    assert {MarkdownText, MarkdownCode, MarkdownTable} <= kinds
    assert transcript.messages[-1].markdown == transcript.stream.source


def test_the_transcript_reports_before_it_is_shown(chat_module: ModuleType) -> None:
    transcript = chat_module.Transcript(tokens_per_second=60.0)
    assert transcript.advance(1.0) == 60 and not transcript.done
    assert f"writing, 60 of {len(transcript.pieces)} pieces" in transcript.status()
    *messages, total = chat_module.report(transcript, 3)
    assert len(messages) == 4
    assert messages[0] == "message=0 role=you vertices=0 whole=1 blocks=0"
    assert total == ("frames=3 messages=4 fed=60 done=0 following=0 renderer=TypesetView ready=0")


# ----------------------------------------------------------------------
# `main` with no library: it says why and opens nothing


@_BOTH
def test_without_the_library_main_says_why_and_opens_no_window(path: Path) -> None:
    """
    Fidelity: `main()` itself in a fresh interpreter, with the library's
    variables and every display removed. It returns `NO_LIBRARY` (1), prints
    nothing on standard output and one line on standard error naming the
    variable, and never imports a window runner: there was no window to fail
    to open.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in (*_VARIABLES, "DISPLAY", "WAYLAND_DISPLAY")
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("example", {str(path)!r})
                example = importlib.util.module_from_spec(spec)
                sys.modules["example"] = example
                spec.loader.exec_module(example)
                code = example.main(["--frames", "5"])
                runners = [n for n in ("imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                           if n in sys.modules]
                print("code=%d no_library=%d runners=%r" % (code, example.NO_LIBRARY, runners),
                      file=sys.stderr)
                raise SystemExit(code)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env={**env, "PYTHONPATH": str(_ROOT)},
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout == ""
    said, told = result.stderr.strip().splitlines()[-2:]
    assert said == f"imtypeset is not drawing: {typesetter.LIBRARY_VARIABLE} is not set"
    assert told == "code=1 no_library=1 runners=[]"
    assert "Traceback" not in result.stderr


# ----------------------------------------------------------------------
# a real window


def _can_make_a_namespace() -> bool:
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-rm", "true"], capture_output=True, check=False)
    return done.returncode == 0


def _run_main(
    path: Path, display: int, *arguments: str, prelude: str = "", expect: int = 0
) -> tuple[list[dict[str, str]], str]:
    """
    An example's `main` with the library, in a GLFW window on an Xvfb.

    The report lines it printed, as dicts, and its standard error. `prelude`
    is run in the child before the example; `expect` is the exit status.
    Skipped unless `IMTYPESET_LIBRARY` is set and an Xvfb can be started.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which the Xvfb recipe needs")
    probe = _load(_PROBE, f"imscribe_mouse_probe_for_{path.stem}")
    inner = (
        textwrap.dedent(f"""
        import os, runpy, sys
        sys.path.insert(0, {str(_PROBE.parent)!r})
        from mouse_probe import wait_for_tcp_display
        if not wait_for_tcp_display(os.environ["DISPLAY"], timeout=30.0):
            raise SystemExit("the Xvfb never accepted a connection")
        """)
        + textwrap.dedent(prelude)
        + textwrap.dedent(f"""
        sys.argv = [{str(path)!r}, *{list(arguments)!r}]
        runpy.run_path({str(path)!r}, run_name="__main__")
        """)
    )
    command = probe.xvfb_command([sys.executable, "-c", inner], display=display)
    done = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=_ROOT,
        env=dict(os.environ),
    )
    assert done.returncode == expect, done.stdout + done.stderr
    lines = [
        line
        for line in done.stdout.splitlines()
        if re.match(r"^(frames|message|edits|vertices)=", line)
    ]
    return [dict(part.split("=", 1) for part in line.split()) for line in lines], done.stderr


def test_with_the_library_the_replay_runs_through_imtypeset_in_a_real_window() -> None:
    """
    Fidelity: `main()` itself with the library, in a GLFW window with an OpenGL
    context, on Xvfb. The report is made in the child on its last frame and
    says there that `typesetter.ready()` held and which view drew.

    Three hundred pieces a second for 240 frames: the document arrives over
    many frames, so appends are made and not only the first `set_blocks`.

    Software rendering and no window manager: a real window, not a desktop.
    Nobody looked at it.
    """
    (first, second, third), _ = _run_main(
        _REPLAY, XVFB_REPLAY, "--frames", "240", "--tps", "300", "--policy", "RESET"
    )
    assert first["renderer"] == "TypesetStreamView" and first["ready"] == "1"
    assert first["frames"] == "240" and first["policy"] == "RESET"
    assert int(first["fed"]) > 100
    assert int(second["edits"]) > 20 and int(second["appends"]) > 10
    assert int(second["replaces"]) >= 1 and second["following"] == "1"
    assert int(third["vertices"]) > 100 and third["whole"] == "1"
    assert int(third["blocks"]) >= int(third["committed"]) >= 1


def test_with_the_library_the_transcript_runs_through_imtypeset_in_a_real_window() -> None:
    """
    Fidelity: `main()` itself with the library, on Xvfb. Four messages, the last one fed.
    """
    (*messages, total), _ = _run_main(_CHAT, XVFB_CHAT, "--frames", "60", "--tps", "100000")
    assert [message["role"] for message in messages] == ["you", "assistant", "you", "assistant"]
    assert all(message["whole"] == "1" for message in messages)
    assert sum(int(message["vertices"]) for message in messages) > 1000
    assert all(int(message["blocks"]) >= 1 for message in messages)
    assert total["messages"] == "4" and total["done"] == "1" and total["frames"] == "60"
    assert total["renderer"] == "TypesetView" and total["ready"] == "1"


def test_with_the_library_the_replay_runs_to_the_end_in_a_real_window() -> None:
    """
    Fidelity: `main()` itself with the library, on Xvfb. A rate high enough to
    feed the whole document well inside the frames asked for, so the report is
    of a finished replay: every piece fed, the stream closed and every block
    committed, vertices drawn with everything set as asked, the pane at the
    end.
    """
    (first, second, third), _ = _run_main(
        _REPLAY, XVFB_REPLAY, "--frames", "90", "--tps", "100000", "--policy", "RESET"
    )
    assert first["frames"] == "90" and first["done"] == "1" and first["policy"] == "RESET"
    assert first["renderer"] == "TypesetStreamView" and first["ready"] == "1"
    assert first["fed"] == first["pieces"] and int(first["pieces"]) > 500
    assert int(second["edits"]) >= 1 and second["following"] == "1"
    assert int(third["vertices"]) > 100 and third["whole"] == "1"
    assert third["blocks"] == third["committed"] and int(third["blocks"]) > 10


_FAILING_DRAW = """
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView
state = {"draws": 0}
real_draw = TypesetView.draw
def failing(self, **kwargs):
    state["draws"] += 1
    if state["draws"] > 6:
        raise TypesetUnavailable("raised by the test")
    return real_draw(self, **kwargs)
TypesetView.draw = failing
"""


@pytest.mark.parametrize(
    ("path", "display"),
    # In this order: the test before these ran on the replay's display, and a
    # display's port is not always free the moment its server has gone.
    [(_CHAT, XVFB_CHAT), (_REPLAY, XVFB_REPLAY)],
    ids=["chat_transcript", "stream_replay"],
)
def test_when_a_draw_raises_in_the_window_main_says_why_and_returns_no_library(
    path: Path, display: int
) -> None:
    """
    Fidelity: `main()` itself with the library, on Xvfb, with `TypesetView.draw`
    made to raise `TypesetUnavailable` from its seventh call on. The window
    closes by itself well before the 600 frames asked for (the run would
    otherwise time out), `main` returns `NO_LIBRARY` (1), prints the reason on
    standard error and no report: a report would say a renderer drew.
    """
    lines, stderr = _run_main(path, display, "--frames", "600", prelude=_FAILING_DRAW, expect=1)
    assert lines == []
    assert "imtypeset is not drawing: raised by the test" in stderr
    assert "Traceback" not in stderr


# ----------------------------------------------------------------------
# through imtypeset: real frames, no window, in a child that has the library

_HEADLESS = r"""
import importlib.util, json, sys
from imgui_bundle import imgui
from imscribe import typesetter

ROOT, PROSE = sys.argv[1], sys.argv[2]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT + "/examples/" + name + ".py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 500.0)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
replay, chat = load("stream_replay"), load("chat_transcript")

def frame(module, made, seconds=1.0 / 60.0, wheel=None, width=900.0, keys=()):
    io.delta_time = 1.0 / 60.0
    io.add_mouse_pos_event(450.0, 300.0)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    for key, down in keys:
        io.add_key_event(key, down)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(width, 500.0))
        flags = imgui.WindowFlags_.no_decoration.value | imgui.WindowFlags_.no_move.value
        imgui.begin("##imscribe-" + module.__name__, None, flags)
        try:
            result = module.show(made, imgui, seconds)
        finally:
            imgui.end()
    finally:
        imgui.render()
    return result

def told(playing, frames):
    view = playing.view
    return {
        "done": playing.done, "fed": playing.fed, "pieces": len(playing.pieces),
        "frames": frames, "moved": playing.moved, "moves": [list(m) for m in playing.moves],
        "stream": type(playing.stream).__name__, "view": type(view).__name__,
        "edits": playing.edits, "following": view is not None and view.following,
        "status": playing.status(), "report": replay.report(playing, frames),
        "blocks": len(playing.stream.blocks), "committed": len(playing.stream.committed),
        "whole": playing.whole,
    }

# 1. The replay of `demo/stream.md`, under each policy, to its end; then the wheel.
unmade = []
for policy in replay.POLICIES:
    playing = replay.replay(tokens_per_second=600.0, policy=policy)
    unmade.append(playing.view is None)
    frames, last = 0, None
    while not playing.done and frames < 400:
        last = frame(replay, playing)
        frames += 1
    for _ in range(3):
        last = frame(replay, playing)
    report[policy] = dict(told(playing, frames), last=last)
report["unmade"] = unmade
# The finished replay reads as the document does: streaming is a way of arriving.
from imscribe.ui.typeset_view import TypesetView
source = replay.SOURCE.read_text(encoding="utf-8")
whole = TypesetView(source, theme=playing.theme, references=False)
playing.view.select_all()
frame(replay, playing)
streamed_copy = playing.view.selected_text()
report["reads_whole"] = {
    "texts": list(playing.view.texts) == list(whole.texts), "count": len(whole.texts),
    "blocks": tuple(playing.view.blocks) == tuple(whole.blocks),
    "copied": len(streamed_copy),
    "source_words": [word in streamed_copy for word in ("renderer", "table")],
}
whole.close()
playing.view.clear_selection()
frame(replay, playing, wheel=4.0)
frame(replay, playing)
report["wheel"] = [playing.view.following, playing.status()]

# Plain prose under each policy, a piece a frame and ten a frame: where RESET moves lines.
prose = {}
for rate in (60.0, 600.0):
    for policy in replay.POLICIES:
        playing = replay.replay(PROSE, tokens_per_second=rate, policy=policy)
        commits, settled, frames = [], 0, 0
        while not playing.done and frames < 2000:
            frame(replay, playing)
            frames += 1
            if len(playing.stream.committed) > settled:
                settled = len(playing.stream.committed)
                commits.append(playing.fed)
        frame(replay, playing)
        prose[policy + "@" + str(int(rate))] = {
            "moves": [list(m) for m in playing.moves], "commits": commits,
            "moved": playing.moved, "frames": frames, "edits": playing.edits,
            "lines": len(replay.lines_of(playing.view)),
        }
        playing.view.close()
report["prose"] = prose

# A change of width is not the stream moving anything; a tick without a window counts nothing.
playing = replay.replay(tokens_per_second=600.0)
for _ in range(30):
    frame(replay, playing)
moved = playing.moved
lines_before = replay.lines_of(playing.view)
playing.tokens_per_second = 0.0
frame(replay, playing, width=700.0)
report["resized"] = [moved, playing.moved, replay.lines_of(playing.view) != lines_before]
playing.tokens_per_second = 600.0
before = playing.fed
ticked = playing.tick(1.0 / 60.0)
report["tick"] = [playing.fed - before, ticked]
old_view = playing.view
playing.restart("RESET")
report["restarted"] = [playing.view is None, playing.fed, playing.moved, playing.policy,
                       playing.edits, old_view.native_document is None]
frame(replay, playing)
report["shown_again"] = [type(playing.view).__name__, playing.view is not old_view, playing.fed]

# 2. The transcript: four messages, the last one written while it is drawn.
transcript = chat.Transcript(tokens_per_second=600.0)
before_open = [m.view is None for m in transcript.messages]
frame(chat, transcript, seconds=0.0)
shapes = [type(m.view).__name__ for m in transcript.messages]
revisions = [m.view.revision for m in transcript.messages[:-1]]
frames = 0
while not transcript.done and frames < 300:
    frame(chat, transcript)
    frames += 1
drawn = frame(chat, transcript)
for _ in range(3):
    frame(chat, transcript, seconds=0.0)
report["transcript"] = {
    "before_open": before_open, "shapes": shapes, "frames": frames, "drawn": list(drawn),
    "stream": type(transcript.stream).__name__,
    "finished_edits": [dict(m.view.edits) for m in transcript.messages[:-1]],
    "untouched": [m.view.revision for m in transcript.messages[:-1]] == revisions,
    "live_edits": dict(transcript.live.edits), "following": transcript.live.following,
    "vertices": [m.vertices for m in transcript.messages],
    "status": transcript.status(), "report": chat.report(transcript, frames),
    "aligns": sorted({b.style.align.name for m in transcript.messages for b in m.view.blocks
                      if hasattr(b, "runs")}),
    "links": sum(len(m.view.links) for m in transcript.messages),
    "first_origin": transcript.messages[0].view.origin,
    "live_origin": transcript.live.origin,
}
first, last = transcript.messages[1].view, transcript.live
first.select_all()
frame(chat, transcript)
copied = first.selected_text()
one = [first.owns_selection, copied[:15], "\n\nBreak the item to the measure" in copied,
       "1. Break" in copied]
last.select(((0, 0), (0, 12)))
frame(chat, transcript)
two = [last.owns_selection, first.selection, last.selected_text()]
imgui.set_clipboard_text("SENTINEL")
for down in (True, False):
    frame(chat, transcript, keys=((imgui.Key.mod_ctrl, down), (imgui.Key.c, down)))
report["selection"] = [one, two, imgui.get_clipboard_text()]
# One setting for reference definitions, in both kinds of message.
text = "See [the notes][1] for more.\n\n[1]: https://example.org/notes\n"
both = chat.Transcript(finished=(("you", text),), streaming=("model", text), tokens_per_second=1e9)
frame(chat, both)
frame(chat, both)
finished, streamed = both.messages[0].view, both.live
default = TypesetView(text, theme=both.theme)
report["references"] = {
    "done": both.done, "blocks": [len(finished.blocks), len(streamed.blocks)],
    "links": [len(finished.links), len(streamed.links)],
    "same": list(finished.texts) == list(streamed.texts),
    "default": [len(default.blocks), len(default.links)],
}
default.close()

# After the body that needs the library, and before the two sections that take it away.
report["after"] = {"module": typesetter.module() is not None, "ready": typesetter.ready(),
                   "reason": typesetter.reason()}

# 3. A draw that raises with the library still ready: `show` lets it out, with ImGui's
# stack as it found it (the frame after is drawn).
from imscribe.ui.typeset_view import TypesetUnavailable
real_draw = TypesetView.draw
def failing(self, **kwargs):
    raise TypesetUnavailable("raised by the test")
playing = replay.replay(tokens_per_second=600.0)
transcript = chat.Transcript(tokens_per_second=600.0)
for _ in range(10):
    frame(replay, playing)
    frame(chat, transcript)
TypesetView.draw = failing
raised = []
for module, made in ((replay, playing), (chat, transcript)):
    try:
        frame(module, made)
        raised.append(None)
    except TypesetUnavailable as exc:
        raised.append(str(exc))
TypesetView.draw = real_draw
again = [frame(replay, playing), list(frame(chat, transcript))]
report["middraw"] = {"ready": typesetter.ready(), "raised": raised, "again": again,
                     "fed": [playing.fed, transcript.fed]}

# 4. Last, because it is for the rest of the process: the library switched off.
playing = replay.replay(tokens_per_second=600.0)
for _ in range(10):
    frame(replay, playing)
transcript = chat.Transcript(tokens_per_second=600.0)
for _ in range(5):
    frame(chat, transcript)
typesetter.disable("switched off by the test")
raised = []
for module, made in ((replay, playing), (chat, transcript)):
    try:
        frame(module, made)
        raised.append(None)
    except TypesetUnavailable as exc:
        raised.append(str(exc))
fresh = []
for module, made in ((replay, replay.replay(PROSE)), (chat, chat.Transcript())):
    try:
        frame(module, made)
        fresh.append(None)
    except TypesetUnavailable as exc:
        fresh.append(str(exc))
report["off"] = {"ready": typesetter.ready(), "raised": raised, "fresh": fresh}
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
        [sys.executable, "-B", "-c", _HEADLESS, str(_ROOT), PROSE],
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
    print("observed (not asserted): lines KEEP_STREAMED moved:", json.dumps(report["prose"]))
    return report


def test_the_replay_feeds_draws_and_counts_frame_by_frame(typeset: dict[str, Any]) -> None:
    """
    Fidelity: real ImGui frames, no display, the library loaded. `show` end to
    end under each policy, on `demo/stream.md`.

    Counts: no view before the first frame; every piece fed, at most one edit
    a frame, appends made, the pane at the end. `RESET` hands more blocks over
    again than `KEEP_STREAMED` (a block is read in the theme when it commits)
    and moves lines. How many lines `KEEP_STREAMED` moves on this document is
    the library's line breaking and markup that closes late; it is reported
    and not asserted.
    """
    assert typeset["unmade"] == [True, True]
    keep, reset = typeset["KEEP_STREAMED"], typeset["RESET"]
    for told in (keep, reset):
        assert told["done"] is True and told["whole"] is True
        assert (told["stream"], told["view"]) == ("MarkdownStream", "TypesetStreamView")
        assert told["fed"] == told["pieces"] > 500 and 30 < told["frames"] < 200
        edits = told["edits"]
        assert edits["set"] == 1 and edits["append"] > 10
        assert sum(edits.values()) <= told["frames"] + 3
        assert told["last"] is True and told["following"] is True
        assert told["blocks"] == told["committed"] > 10
        assert f"settled lines moved: {told['moved']}" in told["status"]
        assert f"of {sum(edits.values())} edits)" in told["status"]
        assert told["report"][0].endswith("renderer=TypesetStreamView ready=1")
        assert told["report"][1].startswith("edits=") and told["report"][2].startswith("vertices=")
    assert "policy=KEEP_STREAMED" in keep["report"][0] and "policy=RESET" in reset["report"][0]
    assert reset["edits"]["replace"] > keep["edits"]["replace"]
    assert reset["moved"] > keep["moved"] >= 0
    following, status = typeset["wheel"]
    assert following is False and "scrolled away from the end" in status


def test_a_finished_replay_reads_as_the_document_does(typeset: dict[str, Any]) -> None:
    """
    Streaming is a way of arriving, not a different document: the finished
    `RESET` replay of `demo/stream.md` holds the blocks, and the texts the
    library was given, that a `TypesetView` of the whole file holds (read, as
    a stream is, with reference definitions off).
    """
    whole = typeset["reads_whole"]
    assert whole["blocks"] is True and whole["texts"] is True and whole["count"] > 20
    assert whole["copied"] > 1500 and all(whole["source_words"])


@pytest.mark.parametrize("rate", [60, 600])
def test_resetting_on_commit_moves_lines_and_only_when_a_block_commits(
    typeset: dict[str, Any], rate: int
) -> None:
    """
    Three plain paragraphs under `RESET`, a piece a frame and ten a frame:
    lines moved on exactly the draws that found another block committed --
    three of them -- and on no other. The lane beside it, the same pieces
    under `KEEP_STREAMED`, went through the same counter with as many edits.
    """
    reset, keep = typeset["prose"][f"RESET@{rate}"], typeset["prose"][f"KEEP_STREAMED@{rate}"]
    assert len(reset["commits"]) == 3 and reset["lines"] >= 4
    assert [fed for fed, _ in reset["moves"]] == reset["commits"]
    assert all(count >= 1 for _, count in reset["moves"])
    assert reset["moved"] == sum(count for _, count in reset["moves"])
    assert reset["edits"]["replace"] >= keep["edits"]["replace"] + 3
    assert keep["frames"] == reset["frames"] and keep["lines"] == reset["lines"]


def test_a_width_is_not_a_move_a_tick_counts_no_lines_and_a_restart_lets_go(
    typeset: dict[str, Any],
) -> None:
    before, after, relaid = typeset["resized"]
    assert relaid is True, "the resize moved nothing; the test is vacuous"
    assert after == before, "a change of width was counted as lines moving"
    assert typeset["tick"] == [10, 0]
    # A restart closes the view's document and drops the view; the next frame makes another.
    assert typeset["restarted"] == [
        True,
        0,
        0,
        "RESET",
        {"set": 0, "replace": 0, "append": 0},
        True,
    ]
    assert typeset["shown_again"] == ["TypesetStreamView", True, 10]


def test_the_transcript_is_four_messages_and_only_the_last_is_edited(
    typeset: dict[str, Any],
) -> None:
    """
    No view before the first frame. The finished messages are each handed to
    the library once and never again while the last one streams; the last one
    is appended to; everything is ragged; the pane followed the last message
    down (the first message's top is above the pane's). One selection is
    current across the transcript, and Ctrl+C copies the one last selected in.
    """
    told = typeset["transcript"]
    assert told["before_open"] == [True] * 4 and told["stream"] == "MarkdownStream"
    assert told["shapes"] == ["TypesetView"] * 3 + ["TypesetStreamView"]
    assert told["frames"] > 5 and told["drawn"] == [True] * 4
    assert told["finished_edits"] == [{"set": 1, "replace": 0, "append": 0}] * 3
    assert told["untouched"] is True
    assert told["live_edits"]["set"] == 1 and told["live_edits"]["append"] > 5
    assert told["following"] is True and sum(told["vertices"]) > 300
    assert told["first_origin"][1] < 0.0 < told["live_origin"][1]
    assert "last one finished" in told["status"]
    assert told["report"][-1].endswith("renderer=TypesetView ready=1")
    assert all(line.startswith("message=") and " vertices=" in line for line in told["report"][:4])
    assert "JUSTIFY" not in told["aligns"] and told["links"] == 0
    one, two, clipboard = typeset["selection"]
    # The numbered list keeps its items as blocks of their own. (Whether a copy
    # carries an item's number is the view's: `one[3]`, printed and not asserted.)
    assert one[:3] == [True, "Hang the marker", True]
    print("observed (not asserted): a copied list item carries its marker:", one[3])
    assert two[0] is True and two[1] is None and len(two[2]) == 12
    assert clipboard == two[2] != "SENTINEL"


def test_a_message_reads_the_same_finished_as_it_did_while_it_streamed(
    typeset: dict[str, Any],
) -> None:
    """
    One setting for link reference definitions, in both kinds of message (review 4, item 7).

    A stream cannot read `[1]: url` definitions -- one may arrive last and
    change every `[1]` before it -- so a streamed message sets them as text.
    A finished message is read the same way: two blocks, no link, the same
    texts as the streamed one. The control is the view's default, which does
    make the link.
    """
    told = typeset["references"]
    assert told["done"] is True and told["blocks"] == [2, 2] and told["links"] == [0, 0]
    assert told["same"] is True
    assert told["default"] == [1, 1]


def test_when_a_draw_raises_show_lets_it_out_and_leaves_the_frame_whole(
    typeset: dict[str, Any],
) -> None:
    """
    `TypesetView.draw` made to raise `TypesetUnavailable` for one frame, with
    the library ready throughout: `show` of each example raises it to its
    caller (`main` then closes the window and says why), having ended its
    child window -- the child's ImGui accepted that frame and drew the next,
    in which both examples are set whole again.
    """
    told = typeset["middraw"]
    assert told["ready"] is True
    assert told["raised"] == ["raised by the test", "raised by the test"]
    assert told["again"] == [True, [True] * 4]
    assert told["fed"] == [120, 120]


def test_when_the_library_is_switched_off_show_raises_and_says_why(
    typeset: dict[str, Any],
) -> None:
    """
    `typesetter.disable` between two frames: the next `show` of an example
    that was drawing raises `TypesetUnavailable` naming the reason, and so
    does the first `show` of one made afterwards. Neither draws by another
    route.
    """
    off = typeset["off"]
    assert off["ready"] is False
    for said in (*off["raised"], *off["fresh"]):
        assert said is not None and "switched off by the test" in said

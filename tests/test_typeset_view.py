r"""
`imscribe.ui.typeset_view.TypesetView` and `examples/typeset_minimal.py`.

Which tests run depends on how the suite was started (`make test`, or `make
test TYPESET=1`), as in `tests/test_typeset.py`:

1.  **Without the library.** Each runs in an environment with the two
    variables removed, so they hold in both runs: the constructor refuses with
    the reason, the module imports nothing of imtypeset or of Dear ImGui, and
    the example says why on standard error and exits 1 without a window.
2.  **With it.** Skipped, with the reason, when `IMTYPESET_LIBRARY` is not set.
    ONE run of `_DRIVER` in a real window (the `window` fixture) through
    `hello_imgui`, with the mouse and the keys queued through
    `io.add_*_event`; it prints a report and each test below reads its part.
    The driver says in the report whether `typesetter.module()` and `ready()`
    held IN THE CHILD, and the fixture fails when they did not: a child that
    lost the library would otherwise fall back and pass.

The driver counts calls into the library by standing in front of
`imtypeset._lib`, the ctypes library object every call goes through. That is a
private name of a package this tree does not own; if it moves, the fixture
fails saying so, it does not pass.

Times are in the report and are NOT asserted: the driver measures the view's
own `draw` on `demo/sample.md`. (Until tranche 5 it timed `BareView.draw`
beside it; `.concerns/IT-A2--builder--result.md` has what was read off one
run of both and at what load.)

**What the view is given is markdown source, or `parse_markdown`'s blocks.**
Until tranche 5 most of the children here handed it the old core's blocks
(`imscribe.build_document`), which `imscribe.typesetter.Converter` described;
that path is deleted. Where the old core was the ORACLE (what a document
comes to, a table's column widths and row heights), its answers were frozen
first: `tests/data/material_descriptions.json` (through
`tests/material_frozen.py`) and `tests/data/material_tables.json`.
`.concerns/T5-B1--builder--result.md` says which tests went and which were
restated.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE = _ROOT / "examples" / "typeset_minimal.py"
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)

_LAYOUT, _DRAW, _SIZE = "LayoutDocument", "DrawDocument", "GetDocumentSize"
_FRAME = [_LAYOUT, _DRAW, _SIZE]
"""The three calls of a frame, in the order they must be made."""

_PARAGRAPH_CALLS = frozenset(
    {
        "CreateParagraph",
        "SetParagraphText",
        "LayoutParagraph",
        "GetParagraphLineCount",
        "GetParagraphLine",
        "DrawParagraph",
        "HitTestParagraph",
        "DestroyParagraph",
        "SetDocumentBlockExtent",
    }
)
"""
What the table stopgap asked of the library (a paragraph a cell, a height a table).

Tables are blocks of the library's document since tranche 4, and no view
makes any of these calls for one: the tests below hold that.
"""


def _report_of(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    return report


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------

_WITHOUT = r"""
import json, sys
import imscribe.ui.typeset_view as module
from imscribe import typesetter

loaded = sorted(name for name in sys.modules if name.split(".")[0] in ("imtypeset", "imgui_bundle"))
try:
    module.TypesetView("# A heading\n")
    refused = None
except module.TypesetUnavailable as exc:
    refused = [str(exc), isinstance(exc, RuntimeError)]
print("REPORT " + json.dumps({"loaded": loaded, "refused": refused, "reason": typesetter.reason()}))
"""


def test_without_the_library_the_constructor_refuses_and_names_the_reason() -> None:
    """
    The caller chooses the old view; the class never draws nothing in silence.
    """
    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _WITHOUT],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(done.stdout)
    # Importing the view brought in neither the library's package nor Dear ImGui.
    assert report["loaded"] == []
    message, is_runtime_error = report["refused"]
    assert is_runtime_error
    assert report["reason"] == "IMTYPESET_LIBRARY is not set"
    assert report["reason"] in message


def test_without_the_library_the_example_says_why_and_draws_nothing() -> None:
    """
    There is no other renderer (tranche 5): with the two variables removed
    the example prints one line to standard error naming the reason, exits
    with status 1, and reports no frame. It is run with no display in its
    environment, so it cannot have opened a window to say so.

    Restated from the test that held the `BareView` fallback this example
    had until tranche 5 ("...; drawing with BareView", `renderer=BareView`).
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in (*_VARIABLES, "DISPLAY", "WAYLAND_DISPLAY")
    }
    done = subprocess.run(
        [sys.executable, "-B", str(_EXAMPLE), "--frames", "5"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "imtypeset is not drawing: IMTYPESET_LIBRARY is not set" in done.stderr
    assert "BareView" not in done.stdout + done.stderr
    assert not [line for line in done.stdout.splitlines() if line.startswith("frames=")]


# ---------------------------------------------------------------------------
# 2. With the library, in a real window
# ---------------------------------------------------------------------------

_DRIVER = r"""
import json, os, statistics, sys, time
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import parse_markdown
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

ROOT = Path(sys.argv[1])
PARKED = (300.0, 700.0)   # in the application's window, below the ImGui one
OVER = (300.0, 200.0)     # on the text

def loadavg():
    return ["%.2f" % x for x in __import__("os").getloadavg()]

class Counting:
    # Stands in front of the ctypes library and writes down each call made through it.
    def __init__(self, target, log):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        log = self._log

        def call(*args, **kwargs):
            log.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)

        return call

source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
theme = Theme.build()
# The blocks, made once and handed over as blocks: what a host that parses for itself does.
document = parse_markdown(source, theme, math=True)
report = {"load_start": loadavg(), "frames": {}, "scroll": [], "timing": {}}
frames = report["frames"]
calls = []
clicked = []
state = {"n": 0, "width": 700.0, "view": None, "ts": None, "real": None}
times = {"typeset": []}

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    report["load_fonts"] = typesetter.load_fonts()

def pre_new_frame():
    n = state["n"] + 1
    io = imgui.get_io()
    if n == 1:
        io.add_mouse_pos_event(*PARKED)
    elif n == 20:
        io.add_mouse_pos_event(*OVER)
    elif n == 40:
        io.add_mouse_button_event(0, True)
    elif 42 <= n <= 55:
        io.add_mouse_pos_event(OVER[0] + 10.0 * (n - 41), OVER[1] + 10.0 * (n - 41))
    elif n == 58:
        io.add_mouse_button_event(0, False)
    elif n == 62:
        io.add_mouse_pos_event(*PARKED)
    elif n == 66:
        io.add_key_event(imgui.Key.mod_ctrl, True)
        io.add_key_event(imgui.Key.c, True)
    elif n == 67:
        io.add_key_event(imgui.Key.c, False)
        io.add_key_event(imgui.Key.mod_ctrl, False)
    elif n == 113 and "link_at" in state:
        io.add_mouse_pos_event(*state["link_at"])
    elif n == 117:
        io.add_mouse_button_event(0, True)
    elif n == 119:
        io.add_mouse_button_event(0, False)
    elif n == 123:
        io.add_mouse_pos_event(*PARKED)

def before_draw(n, view):
    ts = state["ts"]
    if n == 64:
        view.select_all()
        report["all_selected"] = view.selection
        report["selected_text"] = view.selected_text()
    elif n == 70:
        report["clipboard"] = imgui.get_clipboard_text()
        report["expected_copy"] = view.separator.join(text for text in view.texts if text)
        report["every_text_joined"] = view.separator.join(view.texts)
        view.clear_selection()
    elif n == 74:
        report["height_before_scroll"] = view.height
        report["scroll_before"] = imgui.get_scroll_y()
        view.scroll_to(36)
    elif n == 85:
        left, top, right, bottom = view.block_rect(36)
        window_top = imgui.get_window_pos().y
        report["last_block"] = {
            "top": top, "bottom": bottom, "window_top": window_top,
            "window_bottom": window_top + imgui.get_window_size().y,
            "scroll_y": imgui.get_scroll_y(), "scroll_max": imgui.get_scroll_max_y(),
        }
        report["height_after_scroll"] = view.height
        view.scroll_to(0, align=0.0, always=True)
    elif n == 96:
        report["before_resize"] = {"size": list(view.native_document.size())}
    elif n == 105:
        report["after_resize"] = {"size": list(view.native_document.size())}
        row = view.links[0]
        report["link_row"] = list(row)
        view.scroll_to(row.block, row.start)
    elif n == 112:
        row = view.links[0]
        doc = view.native_document
        x0, y0, _, y1 = doc.caret_rect((row.block, row.start + 2))
        x1 = doc.caret_rect((row.block, row.start + 3))[0]
        ox, oy = view.origin
        state["link_at"] = (ox + (x0 + x1) / 2.0, oy + (y0 + y1) / 2.0)
    elif n == 116:
        report["under_mouse_block"] = view.under_mouse.position.block if view.under_mouse else None
        report["selection_before_click"] = view.selection
    elif n == 122:
        report["clicked"] = list(clicked)
        report["selection_after_click"] = view.selection
    elif n == 125:
        before = (view.revision, dict(view.edits))
        same = [view.set_document(document), view.set_document(document.blocks)]
        report["same_blocks"] = {"changed": same, "revision": view.revision - before[0],
                                 "edits": view.edits == before[1]}
        calls.clear()
        cut = view.set_document(document.blocks[:30])
        doc = view.native_document
        report["cut"] = {"changed": cut, "calls": list(calls), "blocks": len(doc),
                         "texts": len(view.texts), "library_blocks": doc.block_count}
    elif n == 127:
        calls.clear()
        grown = view.set_document(document.blocks)
        doc = view.native_document
        report["grown"] = {
            "changed": grown, "calls": list(calls), "blocks": len(doc),
            "edits": dict(view.edits), "edit_error": doc.edit_error.code,
            "texts_match": [
                doc.range_text(((i, 0), (i, len(t)))) == t for i, t in enumerate(view.texts)
            ],
            "tables": list(view.tables),
        }
        # Other block objects that are equal to the ones on show: parsed again.
        report["rebuilt"] = view.set_document(parse_markdown(source, theme, math=True).blocks)
        view.scroll_to(0, align=0.0, always=True)
    elif n == 129:
        text = [view.set_document(source), view.set_document(source)]
        # The string the blocks on show were parsed from: read again, it comes to equal
        # blocks, so nothing changes and the library's document stands. The view has the
        # string from now on.
        report["by_source"] = {"changed": text, "blocks": len(view.texts),
                               "same_texts": list(view.texts) == report_texts,
                               "converter": type(view.converter).__name__,
                               "closed": view.native_document is None,
                               "source": view.source == source,
                               "sources": view.source_of(36) is not None}
    elif n == 136:
        view.set_marks([ts.Mark(((1, 0), (1, 20)), 0x8000FFFF, ts.MarkPlace.Behind),
                        ts.Mark(((999, 0), (999, 5)), 0x8000FFFF, ts.MarkPlace.Behind)])
    elif n == 138:
        doc = view.native_document
        mark = ts.Mark(((1, 0), (1, 20)), 0x8000FFFF, ts.MarkPlace.Behind)
        view.set_marks(doc.pack_marks([mark]))
    elif n == 140:
        view.set_document(source + "\n\nOne more paragraph.\n")   # an edit drops packed marks
    elif n == 142:
        view.set_marks(None)
        view.set_document(document)
        state["width"] = 700.0
    elif n == 145:
        ts._lib = state["real"]   # nothing in front of the library while it is timed
        report["load_before_timing"] = loadavg()

report_texts = None

def gui():
    global report_texts
    state["n"] += 1
    n = state["n"]
    if n == 1:
        ts = state["ts"] = typesetter.module()
        report["module"] = ts is not None
        report["ready"] = typesetter.ready()
        report["reason"] = typesetter.reason()
        if ts is None or not typesetter.ready():
            hello_imgui.get_runner_params().app_shall_exit = True
            return
        state["real"] = ts._lib
        ts._lib = Counting(ts._lib, calls)
        began = time.perf_counter()
        state["view"] = TypesetView(
            document, theme=theme, palette=DARK_PALETTE, on_link=clicked.append
        )
        report["timing"]["typeset_describe_us"] = round((time.perf_counter() - began) * 1e6, 1)
        report_texts = list(state["view"].texts)
    view = state["view"]
    if view is None:
        return
    if n == 97:
        state["width"] = 520.0
    imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
    imgui.set_next_window_size(imgui.ImVec2(state["width"], 600.0))
    flags = imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value
    imgui.begin("host", None, flags)
    imgui.begin_child(
        "##text", imgui.ImVec2(0.0, 0.0), imgui.ChildFlags_.always_use_window_padding.value,
        imgui.WindowFlags_.always_vertical_scrollbar.value,
    )
    try:
        before_draw(n, view)
        draw_list = imgui.get_window_draw_list()
        vertices = draw_list.vtx_buffer.size()
        calls.clear()
        began = time.perf_counter()
        answered = view.draw(palette=DARK_PALETTE)
        spent = time.perf_counter() - began
        if 150 <= n < 250:
            times["typeset"].append(spent)
        if n == 1:
            report["timing"]["typeset_first_frame_us"] = round(spent * 1e6, 1)
        if n < 150:
            frames[n] = {
                "calls": list(calls),
                "vertices": draw_list.vtx_buffer.size() - vertices,
                "answered": answered,
                "item_hovered": imgui.is_item_hovered(),
                "item_active": imgui.is_item_active(),
                "any_item_hovered": imgui.is_any_item_hovered(),
                "selection": view.selection,
                "scroll_y": imgui.get_scroll_y(),
                "scrolled": view.scrolled,
                "height": view.height,
                "width": imgui.get_item_rect_size().x,
                "item_height": imgui.get_item_rect_size().y,
                "owns": view.owns_selection,
                "hovered_link": view.hovered_link,
                "hand": imgui.get_mouse_cursor() == imgui.MouseCursor_.hand,
            }
    finally:
        imgui.end_child()
        imgui.end()
    if n >= 250:
        hello_imgui.get_runner_params().app_shall_exit = True

def before_exit():
    view = state["view"]
    if view is not None:
        doc = view.native_document
        report["stats"] = doc.stats()._asdict()
        report["edits"] = dict(view.edits)
        report["trouble"] = typesetter.trouble()
        typesetter.unload()
        report["closed_by_unload"] = view.native_document is None
        try:
            view.draw()
            report["draw_after_unload"] = "drew"
        except TypesetUnavailable as exc:
            report["draw_after_unload"] = str(exc)
        report["module_after_unload"] = typesetter.module() is not None

runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "TypesetView under test"
runner.app_window_params.window_geometry.size = (800, 760)
runner.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
runner.ini_disable = True
runner.fps_idling.enable_idling = False
runner.callbacks.load_additional_fonts = load_fonts
runner.callbacks.show_gui = gui
runner.callbacks.pre_new_frame = pre_new_frame
runner.callbacks.before_exit = before_exit
immapp.run(runner)

def middle(values):
    return round(statistics.median(values) * 1e6, 1) if values else None

timing = report["timing"]
timing["typeset_steady_median_us"] = middle(times["typeset"][30:])
timing["frames_timed"] = len(times["typeset"][30:])
report["load_end"] = loadavg()
report["frame_count"] = state["n"]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def report(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    script = window.out / "typeset_view_driver.py"
    script.write_text(_DRIVER, encoding="utf-8")
    done = window.run([str(script), str(_ROOT)], timeout=300.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    # In the child, not here: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert got["frame_count"] == 250
    got["frames"] = {int(n): frame for n, frame in got["frames"].items()}
    return got


def test_every_frame_puts_vertices_on_the_window_s_draw_list(report: dict[str, Any]) -> None:
    """
    A document with no font fails softly and draws nothing, so "no exception"
    is not the test: vertices are, and the library answering that everything
    in view was set as asked.
    """
    frames = report["frames"]
    assert sorted(frames) == list(range(1, 150))
    for n, frame in frames.items():
        assert frame["vertices"] > 1000, n
        assert frame["answered"] is True, n
    assert report["trouble"] == ""


def test_a_frame_is_three_library_calls_and_one_more_under_the_mouse(
    report: dict[str, Any],
) -> None:
    """
    The budget, counted at the ctypes library: layout, draw, size, in that
    order; a hit test while the mouse is over the text; a `select_range` in
    its place on each frame of a drag; both on the frame of the press. These
    are ALL the calls of each frame: the one table of this document is a
    block of it and adds none (the next test).
    """
    frames = report["frames"]
    # The first frame also makes the document and sets its options.
    assert frames[1]["calls"] == [
        "GetCurrentContext",
        "CreateDocument",
        "SetDocumentBlocks",
        "SetDocumentOptions",
        *_FRAME,
    ]
    for n in range(2, 20):  # the mouse is off the view
        assert frames[n]["calls"] == _FRAME, n
    for n in range(23, 40):  # the mouse rests on the text
        assert frames[n]["calls"] == [*_FRAME, "HitTestDocument"], n
    press = [n for n in range(40, 44) if "SelectDocumentRange" in frames[n]["calls"]][0]
    assert frames[press]["calls"] == [*_FRAME, "HitTestDocument", "SelectDocumentRange"]
    released = [n for n in range(56, 62) if frames[n]["calls"] == [*_FRAME, "HitTestDocument"]][0]
    for n in range(press + 1, released):
        assert frames[n]["calls"] == [*_FRAME, "SelectDocumentRange"], n
    # Parked again, selected, resized: still three. Ctrl+C is one `range_text`,
    # on the one frame the key goes down.
    copies = [n for n in range(65, 70) if frames[n]["calls"] != _FRAME]
    assert len(copies) == 1
    assert frames[copies[0]]["calls"] == [*_FRAME, "AppendDocumentRangeText"]
    for n in (*range(70, 74), *range(96, 105)):
        assert frames[n]["calls"] == _FRAME, n
    # A `scroll_to` is one geometry question on each of four draws.
    for n in range(74, 78):
        assert frames[n]["calls"] == [_LAYOUT, "GetDocumentBlockGeometry", _DRAW, _SIZE], n
    for n in range(78, 85):
        assert frames[n]["calls"] == _FRAME, n


def test_a_table_is_the_library_s_block_and_costs_no_call_of_its_own(
    report: dict[str, Any],
) -> None:
    """
    `demo/sample.md` has one table. It is one block of the document: no frame
    of this run makes a paragraph for a cell or gives a block a height, which
    is what the stopgap did (21 paragraphs on the first frame). What a table
    IN view costs (nothing either) is counted on `demo/tables.md` further
    down.
    """
    frames = report["frames"]
    for n, frame in frames.items():
        assert not _PARAGRAPH_CALLS.intersection(frame["calls"]), (n, frame["calls"])
    assert not _PARAGRAPH_CALLS.intersection(report["cut"]["calls"] + report["grown"]["calls"])
    # The whole document given again (a `scroll_to` is being carried out on these frames).
    assert frames[127]["calls"] == [_LAYOUT, "GetDocumentBlockGeometry", _DRAW, _SIZE]
    assert frames[128]["calls"][:1] == [_LAYOUT] and _DRAW in frames[128]["calls"]


def test_the_view_is_no_item_until_a_press_and_one_until_the_release(
    report: dict[str, Any],
) -> None:
    frames = report["frames"]
    for n in range(23, 40):
        # The dummy: the mouse is over the document, and no item is hovered.
        assert frames[n]["item_hovered"] is True, n
        assert frames[n]["any_item_hovered"] is False, n
        assert frames[n]["item_active"] is False, n
    press = [n for n in range(40, 44) if "SelectDocumentRange" in frames[n]["calls"]][0]
    for n in range(press, 56):
        assert frames[n]["item_active"] is True, n
    assert frames[61]["item_active"] is False
    # Whichever item it is, it claims the same rectangle.
    assert {frames[n]["item_height"] == frames[n]["height"] for n in range(2, 62)} == {True}
    assert {frames[n]["width"] for n in range(2, 62)} == {frames[2]["width"]}


def test_a_drag_selects_from_the_text_under_the_press(report: dict[str, Any]) -> None:
    frames = report["frames"]
    press = [n for n in range(40, 44) if "SelectDocumentRange" in frames[n]["calls"]][0]
    assert frames[press]["selection"] is None  # a caret selects nothing
    assert frames[press]["owns"] is True
    grown = [frames[n]["selection"] for n in range(press + 1, 62) if frames[n]["selection"]]
    assert len(grown) > 10
    # The fixed end is the same text on every frame, and the other end only moves on.
    assert {tuple(selection[0]) for selection in grown} == {tuple(grown[0][0])}
    ends = [tuple(selection[1]) for selection in grown]
    assert ends == sorted(ends) and ends[-1] > ends[0]
    assert ends[-1][0] > grown[0][0][0], "the drag ran down the page and stayed in one block"
    # The release leaves it as it was.
    assert frames[61]["selection"] == grown[-1] == frames[63]["selection"]


def test_select_all_and_ctrl_c_copy_every_block_that_has_text(report: dict[str, Any]) -> None:
    """
    The rule that was observed, not the one the task supposed: a block with no
    text (a rule) gives nothing AND no separator, so the copy is the
    non-empty described texts joined, which is two characters short of all of
    them joined on this document. The table is in it whole, a tab between
    the cells of a row and a newline between rows: what the library copies
    for a table block, and what `texts` holds for it.
    """
    assert report["all_selected"] == [[0, 0], [36, 599]]
    assert report["clipboard"] == report["selected_text"] == report["expected_copy"]
    assert len(report["every_text_joined"]) - len(report["expected_copy"]) == 2
    assert "\n\nModule\tOwns\tImports a font?\nunits\tScaled points, glue orders\tno\n" in (
        report["clipboard"]
    )
    assert "the first litmus test" in report["clipboard"]


def test_scroll_to_brings_a_block_into_view_and_back(report: dict[str, Any]) -> None:
    frames = report["frames"]
    assert report["scroll_before"] == 0.0
    assert frames[74]["scrolled"] is True
    # It moved once and was then in place, which the later looks found.
    assert [frames[n]["scrolled"] for n in range(75, 85)] == [False] * 10
    last = report["last_block"]
    assert last["scroll_y"] > 500.0
    # In the window, with the margin `scroll_to` keeps by default.
    assert last["window_top"] <= last["top"] and last["bottom"] <= last["window_bottom"]
    # Back to the first block's top at the window's top edge: the scroll is
    # the window's padding above the document and no more, as `BareView`'s is.
    assert 0.0 <= frames[95]["scroll_y"] <= 16.0
    assert frames[95]["scrolled"] is False


def test_a_narrower_pane_is_laid_out_again(report: dict[str, Any]) -> None:
    frames = report["frames"]
    wide, narrow = report["before_resize"]["size"], report["after_resize"]["size"]
    assert narrow[0] == wide[0] - 180.0
    # Taller by what the blocks in the window gained: the ones below it keep
    # the height they had at the old width until they are seen.
    assert narrow[1] > wide[1]
    assert frames[104]["width"] == narrow[0] and frames[104]["item_height"] == narrow[1]


def test_a_link_is_hovered_and_clicked_and_selects_nothing(report: dict[str, Any]) -> None:
    row = report["link_row"]
    frames = report["frames"]
    assert row[4] == "advtext/linebreak.py"
    assert frames[116]["hovered_link"] == row[4] and frames[116]["hand"] is True
    assert frames[110]["hovered_link"] is None and frames[110]["hand"] is False
    assert report["under_mouse_block"] == row[0]
    assert report["clicked"] == ["advtext/linebreak.py"]
    assert report["selection_before_click"] is None and report["selection_after_click"] is None
    assert any(frames[n]["item_active"] for n in range(117, 121)), "a held link is an item"


def test_only_what_changed_is_described_again(report: dict[str, Any]) -> None:
    same = report["same_blocks"]
    assert same == {"changed": [False, False], "revision": 0, "edits": True}
    cut = report["cut"]
    # One edit. (The package then asks how long the new last block is, for
    # its own bookkeeping, when a removal reaches the end of the document.)
    assert cut["changed"] is True
    assert cut["calls"] == ["ReplaceDocumentBlocks", "GetDocumentBlockTextSize"]
    assert cut["blocks"] == cut["texts"] == cut["library_blocks"] == 30
    grown = report["grown"]
    assert grown["changed"] is True and grown["calls"] == ["ReplaceDocumentBlocks"]
    assert grown["blocks"] == 37 and grown["edit_error"] == 0
    assert grown["edits"] == {"set": 1, "replace": 2, "append": 0}
    assert all(grown["texts_match"]) and grown["tables"] == [10]
    # The same markdown as a string: parsed again it is equal blocks, so nothing
    # changes, the library's document stands (no `SetDocumentBlocks` on frame
    # 129), and the view has the string and its source map.
    #
    # RESTATED in tranche 5. The view held the old core's blocks here, a string
    # went through the other converter, and so this read `"changed": [True,
    # False]`, `"closed": True`, a new document on frame 129, and `rebuilt`
    # true (the old core's blocks were compared by identity alone). With one
    # kind of block, compared by value, each of those is the other answer.
    assert report["by_source"] == {
        "changed": [False, False],
        "blocks": 37,
        "same_texts": True,
        "converter": "MarkdownConverter",
        "closed": False,
        "source": True,
        "sources": True,
    }
    assert report["rebuilt"] is False
    assert "SetDocumentBlocks" not in report["frames"][129]["calls"]


def test_marks_reach_the_draw_list_and_packed_ones_go_at_an_edit(
    report: dict[str, Any],
) -> None:
    frames = report["frames"]
    plain = frames[135]["vertices"]
    assert frames[134]["vertices"] == plain
    # Marks as given (one of them names a block that is not there), then packed.
    assert frames[136]["vertices"] > plain and frames[137]["vertices"] == frames[136]["vertices"]
    assert frames[138]["vertices"] == frames[136]["vertices"]
    assert frames[139]["vertices"] == frames[136]["vertices"]
    # The edit added a paragraph below the window and dropped the packed marks.
    assert frames[140]["vertices"] == plain


def test_unload_closes_the_document_and_a_draw_then_says_so(report: dict[str, Any]) -> None:
    assert report["closed_by_unload"] is True
    assert "load_fonts" in report["draw_after_unload"]
    # Not being ready is no failure of the library: it is not switched off.
    assert report["module_after_unload"] is True
    # The first draw, and nothing else, made a document: every change after it
    # was an edit of that one. (Three until tranche 5: a string and the old
    # core's blocks wanted different converters, and each swap made a new one.)
    assert report["edits"]["set"] == 1


def test_the_times_are_reported_and_not_judged(report: dict[str, Any]) -> None:
    timing = report["timing"]
    assert timing["frames_timed"] == 70
    assert timing["typeset_steady_median_us"] > 0


@pytest.mark.parametrize("which", ["TypesetView", "TypesetStreamView", "TypesetDiffView"])
def test_only_the_library_s_own_failure_switches_the_library_off(
    which: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A2 (T5-R #2; open since the first review). `TypesetView._failed` turned
    ANY exception raised under one of its thirteen handlers into
    `typesetter.disable()` and `TypesetUnavailable`, so a slip in the view's
    own Python switched the library off for the process and every page became
    its one line. `TypesetDiffView` sorted by whose the exception is; the
    three views now share that rule (`imscribe.ui.typeset_view.library_failed`):

    - an exception the `imtypeset` package defines (or a subclass of one)
      switches the library off and is told as `TypesetUnavailable`;
    - anything else is raised as it is and switches nothing off;
    - a `TypesetUnavailable` is passed on as it is.

    No library is needed: `_failed` is called on a view that was never built.
    """
    import importlib

    from imscribe.ui import typeset_view
    from imscribe.ui.typeset_view import TypesetUnavailable

    home = {
        "TypesetView": "imscribe.ui.typeset_view",
        "TypesetStreamView": "imscribe.ui.typeset_stream_view",
        "TypesetDiffView": "imscribe.ui.typeset_diff_view",
    }[which]
    kind = getattr(importlib.import_module(home), which)

    class Error(Exception):
        pass

    class Deeper(Error):
        pass

    Error.__module__ = "imtypeset"
    Deeper.__module__ = "somewhere.else"  # a subclass of the library's is the library's
    assert typeset_view.library_failed(Error("x")) and typeset_view.library_failed(Deeper("x"))
    for mine in (IndexError("x"), KeyError("x"), TypeError("x"), OSError("x"), ValueError()):
        assert not typeset_view.library_failed(mine)

    said: list[str] = []
    monkeypatch.setattr(typesetter, "disable", said.append)
    view = object.__new__(kind)
    for mine in (IndexError("a slip"), KeyError("a slip"), AttributeError("a slip"), OSError()):
        with pytest.raises(type(mine)) as caught:
            view._failed(mine)
        assert caught.value is mine
    assert said == [], "a slip of the view's own switched the library off"
    refusal = TypesetUnavailable("imtypeset cannot draw: not ready")
    with pytest.raises(TypesetUnavailable) as again:
        view._failed(refusal)
    assert again.value is refusal and said == []
    with pytest.raises(TypesetUnavailable, match="switched off"):
        view._failed(Deeper("Document.draw: the library said no"))
    assert said == ["Deeper: Document.draw: the library said no"]


_HEADLESS = r"""
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import parse_markdown
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

report = {"module": typesetter.module() is not None}
context = imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
# No renderer: saying the backend takes textures is enough for the library to draw.
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

def frame(view, **more):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        before = imgui.get_window_draw_list().vtx_buffer.size()
        view.draw(**more)
        return imgui.get_window_draw_list().vtx_buffer.size() - before
    finally:
        imgui.end()
        imgui.render()

theme = Theme.build()
blocks = parse_markdown("# One\n\nTwo words.\n\nThree more words.\n", theme).blocks
view = TypesetView(blocks, theme=theme)
try:
    frame(view)
    report["before_fonts"] = "drew"
except TypesetUnavailable as exc:
    report["before_fonts"] = str(exc)
report["module_before_fonts"] = typesetter.module() is not None

report["load_fonts"] = typesetter.load_fonts()
report["vertices"] = frame(view)

# A selection that reaches a replaced block goes; one before it stays; all stays all.
view.select(((0, 0), (0, 3)))
view.set_document(blocks[:2])
report["kept"] = view.selection
view.select(((0, 0), (1, 3)))
view.set_document(blocks[:1])
report["dropped"] = view.selection
view.select_all()
view.set_document(blocks)
report["all"] = view.selection
report["all_text"] = view.selected_text()
view.select(((2, 5), (0, 1)))
report["ordered"] = view.selection
view.clear_selection()

# The context goes and comes back: the document is made again, from the description.
typesetter.unload()
report["load_again"] = typesetter.load_fonts()
report["vertices_again"] = frame(view)
report["edits"] = dict(view.edits)

# Another link ink is another description: one more document, the same texts.
texts = list(view.texts)
view.style_links = True
palette = view.palette
import dataclasses
frame(view, palette=dataclasses.replace(palette, link=0xFF00FF00))
report["after_palette"] = [dict(view.edits), list(view.texts) == texts]

# What a host's own callback raises is the host's: the library stays in use.
def broken(_view):
    raise KeyError("the host's")
view.copy_as = broken
view.select_all()
try:
    view.copy()
    report["host_error"] = "none"
except KeyError:
    report["host_error"] = "KeyError"
report["module_after_host_error"] = typesetter.module() is not None
view.copy_as = None

# A2 (T5-R): what is raised under `draw` that the imtypeset package does not
# define -- a slip in the view's own Python, here an IndexError and a KeyError
# out of the first thing a draw asks of its document -- leaves as ITSELF, and
# the library stays in use. The real document is put back and draws again.
ts = typesetter.module()
report["vertices_before_slips"] = frame(view)
real = view._doc
class Slips:
    closed = False
    def __init__(self, kind):
        self.kind = kind
    def __getattr__(self, name):
        def call(*args, **kwargs):
            raise self.kind("a slip of the view's own in " + name)
        return call
slips = {}
for kind in (IndexError, KeyError, OSError):
    view._doc = Slips(kind)
    try:
        frame(view)
        outcome = "drew"
    except TypesetUnavailable as exc:
        outcome = "TypesetUnavailable: " + str(exc)
    except Exception as exc:
        outcome = type(exc).__name__
    slips[kind.__name__] = [outcome, typesetter.module() is not None, typesetter.ready()]
report["slips"] = slips
view._doc = real
report["vertices_after_slips"] = frame(view)

# What the LIBRARY raises switches it off and is told as TypesetUnavailable.
# `Fell` is a subclass of the package's own `Error`, which is how the views
# know whose a failure is.
class Fell(ts.Error):
    def __init__(self, message):
        Exception.__init__(self, message)
class Broken:
    closed = False
    def __getattr__(self, name):
        def call(*args, **kwargs):
            raise Fell("the library fell over in " + name)
        return call
view._doc = Broken()
try:
    frame(view)
    report["library_error"] = "drew"
except TypesetUnavailable as exc:
    report["library_error"] = str(exc)
report["module_after_library_error"] = typesetter.module() is not None
report["reason"] = typesetter.reason()
# The frame was ended in `frame`'s finally with nothing left open: a second one runs.
imgui.new_frame(); imgui.begin("host"); imgui.end(); imgui.render()
try:
    TypesetView(blocks, theme=theme)
    report["constructor_after"] = "made"
except TypesetUnavailable as exc:
    report["constructor_after"] = str(exc)
print("REPORT " + json.dumps(report))
"""


def test_refusals_edits_and_failures_without_a_window() -> None:
    """
    Real ImGui frames with no window (measured: the library draws into a
    window's draw list once the io says the backend takes textures), in a
    child, for what needs no pointer.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _HEADLESS],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    # Not ready is said, draws nothing, and switches nothing off.
    assert "load_fonts" in got["before_fonts"] and got["module_before_fonts"] is True
    assert got["load_fonts"] is True and got["vertices"] > 100
    assert got["kept"] == [[0, 0], [0, 3]]
    assert got["dropped"] is None
    assert got["all"] == [[0, 0], [2, 17]]
    assert got["all_text"] == "One\n\nTwo words.\n\nThree more words."
    assert got["ordered"] == [[0, 1], [2, 5]]
    assert got["load_again"] is True and got["vertices_again"] == got["vertices"]
    assert got["edits"] == {"set": 2, "replace": 3, "append": 0}
    assert got["after_palette"] == [{"set": 3, "replace": 3, "append": 0}, True]
    assert got["host_error"] == "KeyError" and got["module_after_host_error"] is True
    # A2: each slip is raised as itself, the library is on and ready after it,
    # and the frame after them draws what the frame before them drew.
    assert got["slips"] == {
        name: [name, True, True] for name in ("IndexError", "KeyError", "OSError")
    }
    assert got["vertices_after_slips"] == got["vertices_before_slips"] > 100
    assert "switched off" in got["library_error"] and "fell over" in got["library_error"]
    assert got["module_after_library_error"] is False
    assert "fell over" in got["reason"]
    assert got["reason"] in got["constructor_after"]


def test_with_the_library_the_example_draws_with_typesetview(window: Any) -> None:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = window.run([str(_EXAMPLE), "--frames", "5"])
    assert done.returncode == 0, done.stdout + done.stderr
    assert "drawing with BareView" not in done.stdout
    (last,) = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
    fields = dict(part.split("=") for part in last.split())
    assert fields == {"frames": "5", "renderer": "TypesetView", "blocks": "37"}


# ---------------------------------------------------------------------------
# 3. A host's mistakes, and a library that is already off (review findings F1, F2)
# ---------------------------------------------------------------------------

_HOST = r"""
import json, sys
from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import parse_markdown
from imscribe.typeset_find import Match, marks_for
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

# Stands for the imported package: nothing below reaches the library, and the
# report says whether anything of it was imported.
typesetter._ts, typesetter._tried = object(), True

class Doc:
    closed = False
    def __init__(self):
        self.calls = []
    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            return True
        return call

theme = Theme.build()
blocks = parse_markdown("# One\n\nTwo words.\n\nThree more words.\n", theme).blocks
view = TypesetView(blocks, theme=theme)
report = {}

matches = (Match(0, 0, 3), Match(1, 0, 3))
good = marks_for(matches, 0)
wrong = {
    "matches": matches,
    "one_position": [((0, 0), 255)],
    "no_color": [(((0, 0), (0, 3)),)],
    "float_offset": [(((0, 0.5), (0, 3)), 255)],
    "text": ["ab"],
    "six_fields": [(((0, 0), (0, 3)), 255, 1, 0.0, 0.0, 0.0)],
    "second_is_wrong": [good[0], Match(1, 0, 3)],
}
view.set_marks(good)
for name, marks in wrong.items():
    try:
        view.set_marks(marks)
        report[name] = "accepted"
    except (TypeError, ValueError) as exc:
        report[name] = type(exc).__name__
# A refused call changed nothing.
report["kept"] = view._marks == list(good)
report["message"] = ""
try:
    view.set_marks(matches)
except (TypeError, ValueError) as exc:
    report["message"] = str(exc)
accepted = []
plain, lists = [(((0, 0), (0, 3)), 255)], [[[[0, 0], [0, 3]], 255, 1, 1.5, 2]]
for marks in (good, plain, lists, iter(good), [], None):
    view.set_marks(marks)
    accepted.append(view._marks is not None)
report["accepted"] = accepted

# F1: the library was switched off by something else after this view drew.
doc = view._doc = Doc()
why = "OSError: the library fell over"
typesetter.disable(why)
outcomes = []
for cut in (2, 1, 3):
    try:
        outcomes.append(view.set_document(blocks[:cut]))
    except TypesetUnavailable:
        outcomes.append("raised")
    outcomes.append(typesetter.reason() == why)
report["outcomes"] = outcomes
report["texts"] = list(view.texts)
report["library_calls"] = doc.calls
report["native"] = view.native_document is None
report["loaded"] = sorted(name for name in sys.modules if name.split(".")[0] == "imtypeset")
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def host() -> dict[str, Any]:
    """
    `_HOST` in a child with the two variables removed, so it holds in both runs.

    `typesetter._ts` is given a stand-in there: what is under test is what the
    VIEW does before any call into the library.
    """
    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _HOST],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    got = _report_of(done.stdout)
    assert got["loaded"] == []
    return got


@pytest.mark.parametrize(
    "case",
    [
        "matches",
        "one_position",
        "no_color",
        "float_offset",
        "text",
        "six_fields",
        "second_is_wrong",
    ],
)
def test_a_malformed_mark_is_refused_where_it_is_handed_over(
    host: dict[str, Any], case: str
) -> None:
    """
    F2. `set_marks(finder.matches)` for `finder.marks()` used to be found out
    inside `draw`, where everything raised is the library's and switches it
    off for the process.
    """
    assert host[case] == "TypeError"


def test_a_refused_mark_changes_nothing_and_well_formed_ones_are_taken(
    host: dict[str, Any],
) -> None:
    assert host["kept"] is True
    assert "mark 0" in host["message"] and "Finder.marks()" in host["message"]
    # Tuples, plain ones, lists, an iterator; then an empty sequence and None for none.
    assert host["accepted"] == [True, True, True, True, False, False]


def test_set_document_does_not_raise_once_the_library_is_off(host: dict[str, Any]) -> None:
    """
    F1. Each edit went to the library through `typesetter.block_styles`, which
    raises once the library is off, and the view then switched it off AGAIN
    with that message as the reason, a longer one at every call.
    """
    # Three edits, each made (True) and the reason each time what it was.
    assert host["outcomes"] == [True, True, True, True, True, True]
    assert host["texts"] == ["One", "Two words.", "Three more words."]
    # The document the library held is not edited and is not kept: a later
    # draw that finds the library on describes everything to a new one.
    assert host["library_calls"] == []
    assert host["native"] is True


_OFF = r"""
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import parse_markdown
from imscribe.typeset_find import Match
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

report = {"module": typesetter.module() is not None}
context = imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value

def frame(*views):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        before = imgui.get_window_draw_list().vtx_buffer.size()
        for view in views:
            view.draw()
        return imgui.get_window_draw_list().vtx_buffer.size() - before
    finally:
        imgui.end()
        imgui.render()

theme = Theme.build()
blocks = parse_markdown("# One\n\nTwo words.\n\nThree more words.\n", theme).blocks
first, second = TypesetView(blocks, theme=theme), TypesetView(blocks, theme=theme)
report["ready"] = typesetter.load_fonts()
report["vertices"] = frame(first, second)

# F2: the host's mistake is the host's, and the library goes on drawing.
try:
    first.set_marks((Match(0, 0, 3),))
    report["marks"] = "accepted"
except (TypeError, ValueError) as exc:
    report["marks"] = type(exc).__name__
try:
    report["vertices_after_marks"] = frame(first, second)
except TypesetUnavailable as exc:
    report["vertices_after_marks"] = str(exc)
report["module_after_marks"] = typesetter.module() is not None

# F1: the library raises in ONE view's draw; the host then edits the other.
# (Its own `Error`: since T5-FINAL an `OSError` would leave the draw as itself.)
class Fell(typesetter.module().Error):
    def __init__(self, message):
        Exception.__init__(self, message)
class Broken:
    closed = False
    def __getattr__(self, name):
        def call(*args, **kwargs):
            raise Fell("the library fell over in " + name)
        return call
second._doc = Broken()
try:
    frame(second)
    report["failure"] = "drew"
except TypesetUnavailable as exc:
    report["failure"] = str(exc)
why = typesetter.reason()
report["why"] = why
edits = []
for cut in (2, 1):
    for view in (first, second):
        try:
            edits.append(view.set_document(blocks[:cut]))
        except TypesetUnavailable:
            edits.append("raised")
report["edits"] = edits
report["reason_is_what_it_was"] = typesetter.reason() == why
try:
    frame(first)
    report["draw"] = "drew"
except TypesetUnavailable as exc:
    report["draw"] = str(exc)
report["reason_after_draw"] = typesetter.reason() == why
report["texts"] = list(first.texts)
print("REPORT " + json.dumps(report))
"""


def test_with_the_library_a_bad_mark_and_an_edit_after_a_failure() -> None:
    """
    F2 and F1 against the library itself, in real ImGui frames with no window.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _OFF],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["ready"] is True and got["vertices"] > 100
    assert got["marks"] == "TypeError"
    assert got["vertices_after_marks"] == got["vertices"]
    assert got["module_after_marks"] is True
    assert "fell over" in got["failure"] and "fell over" in got["why"]
    assert got["edits"] == [True, True, True, True]
    assert got["reason_is_what_it_was"] is True
    # The next draw is where the host is told, as documented, and by the same reason.
    assert got["why"] in got["draw"]
    assert got["reason_after_draw"] is True
    assert got["texts"] == ["One"]


# ---------------------------------------------------------------------------
# 3. With the library, real frames, no window: markdown source in, and the members
#    the demo pages read (tranche 3)
# ---------------------------------------------------------------------------

_MEMBERS = r"""
import collections, dataclasses, json, statistics, struct, sys, time
from pathlib import Path
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.description import cell_spans
from imscribe.theme import BlockKind, Theme
from imscribe.typeset_markdown import parse_markdown
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import TypesetView

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "tests"))
import material_frozen
report = {"module": typesetter.module() is not None,
          "load_start": ["%.2f" % x for x in __import__("os").getloadavg()]}
context = imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
ts = typesetter.module()
calls = []

class Counting:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)
    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            calls.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)
        return call

real = ts._lib
ts._lib = Counting(real)

def frame(view, at=None, **more):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        if at is not None:
            imgui.set_cursor_screen_pos(imgui.ImVec2(*at))
        calls.clear()
        answered = view.draw(**more)
        size = imgui.get_item_rect_size()
        return {"answered": answered, "calls": list(calls), "item": [size.x, size.y],
                "origin": list(view.origin), "vertices": view.stats.vertices}
    finally:
        imgui.end()
        imgui.render()

def colours(view):
    # Every vertex colour the whole document would emit: ImDrawVert is two floats of
    # position, two of texture, and the packed colour. (This lays everything out; a
    # frame settles before anything is counted.)
    doc = view.native_document
    vertices, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, 700.0, 100000.0), marks=view._marks_for(doc)
    )
    frame(view)
    return sorted(
        {struct.unpack_from("<I", vertices, at + 16)[0] for at in range(0, len(vertices), 20)}
    )

def runs_off_white_space(view):
    # Each block's runs as what they say about every character that is not white space.
    # A table's are its cells' runs, each at its cell's place in the table's text.
    out = []
    for block in view._described:
        said = {}
        held = [(0, block.text, block.runs)]
        for row, spans in zip(block.rows, cell_spans(block.rows)):
            held += [(start, cell.text, cell.runs) for cell, (start, _) in zip(row, spans)]
        for base, text, runs in held:
            for run in runs:
                for at in range(run.start, run.end):
                    if not text[at].isspace():
                        said[base + at] = [run.face, run.scale, run.flags, run.tag]
        out.append(sorted(said.items()))
    return out

theme = Theme.build()

class Material:
    # What a `TypesetView` given the old core's blocks held, frozen: the description
    # `imscribe.typesetter.Converter` made of `build_document`'s blocks.
    # `.concerns/T5-B1-scripts/freeze_views.py` checked, with both still there, that such a
    # view's texts, described blocks, style table, links and tables were exactly that
    # description's, for every file below.
    def __init__(self, described):
        self.texts = described.texts
        self._described = described.blocks
        self._styles = described.styles
        self.links = described.links
        self.tables = described.tables

# 1. Markdown source through the view, against what the old core's blocks came to.
demos = {}
for path in sorted((ROOT / "demo").rglob("*.md")):
    source = path.read_text(encoding="utf-8")
    direct = TypesetView(source, theme=theme, math=True)
    material = Material(material_frozen.description(source))
    differing = [n for n, (a, b) in enumerate(zip(direct.texts, material.texts)) if a != b]
    # A code block's indent is compared as the whole pixel the view puts it on (KIND_CODE is 3;
    # `imscribe.ui.typeset_view._code_on_a_pixel`); what the view moved is in "code_indents".
    shape = lambda view: [  # noqa: E731
        (b.kind, b.marker,
         float(int(b.left_indent + 0.5)) if b.kind == 3 else round(b.left_indent, 3),
         b.quote_depth, b.flags, b.level, b.extent,
         b.columns, [[cell.text for cell in row] for row in b.rows])
        for b in view._described
    ]
    demos[str(path.relative_to(ROOT))] = {
        "blocks": [len(direct.texts), len(material.texts)],
        "differing_texts": differing,
        "differing_in_tables": [n for n in differing if n in direct.tables],
        "dollars_only": all(
            direct.texts[n] == material.texts[n].replace("$", "") for n in differing
        ),
        "same_shape": shape(direct) == shape(material),
        "code_indents": [[a.left_indent, b.left_indent]
                         for a, b in zip(direct._described, material._described) if a.kind == 3],
        "same_styles": direct._styles == material._styles,
        "same_links": list(direct.links) == list(material.links),
        "same_tables": list(direct.tables) == list(material.tables),
        "runs_differing_off_white_space": [
            n for n, (a, b) in enumerate(
                zip(runs_off_white_space(direct), runs_off_white_space(material))
            )
            if a != b and n not in differing
        ],
        "runs_differ": sum(
            (a.runs, a.rows) != (b.runs, b.rows)
            for a, b in zip(direct._described, material._described)
        ),
        "kinds": sorted({b.kind for b in direct._described}),
        "converter": type(direct.converter).__name__,
    }
    direct.close()
report["demos"] = demos

# 2. The source map, and an edit of a string.
source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8")
view = TypesetView(source, theme=theme, palette=DARK_PALETTE, math=True)
first = frame(view)
steady = [frame(view) for _ in range(3)][-1]
report["first_frame"] = first
report["steady_frame"] = steady
parsed = parse_markdown(source, theme, math=True)
report["sources"] = {
    "held": view.source == source,
    "all": all(view.source_of(n) == parsed.sources[n] for n in range(len(parsed.blocks))),
    "out_of_range": [view.source_of(-1), view.source_of(999), view.block_source(999)],
    "block_source": [view.block_source(0), view.block_source(1)[:40]],
    "top": view.block_source(5, top=True) == parsed.sources[5].top.of(source),
    "block_text": [view.block_text(0), view.block_text(999)],
    "roles": [view.block_role(n) for n in (0, 1, 999)]
             + sorted({view.block_role(n) for n in range(len(view.texts))}),
}
view.select(((0, 2), (2, 5)))
report["selected"] = {
    "blocks": list(view.selected_blocks()),
    "source": view.selected_source(),
    "expected": source[parsed.sources[0].span.start : parsed.sources[2].span.end],
}
view.select(((0, len(view.texts[0])), (2, 0)))
report["selected_edges"] = list(view.selected_blocks())
view.select(((3, 1), (3, 4)))
report["selected_one"] = [list(view.selected_blocks()),
                          view.selected_source() == view.block_source(3)]
view.clear_selection()
report["selected_none"] = [list(view.selected_blocks()), view.selected_source()]

calls.clear()
before = dict(view.edits)
changed = view.set_document(source + "\nOne more paragraph at the end.\n")
report["string_edit"] = {
    "changed": changed, "calls": list(calls), "blocks": len(view.texts),
    "kept": all(a is b for a, b in zip(view.blocks, parsed.blocks)) is False
            and view.blocks[0] == parsed.blocks[0],
    "edits": {k: view.edits[k] - before[k] for k in before},
    "last": view.texts[-1],
    "library_blocks": view.native_document.block_count,
}
frame(view)
view.set_document(source)
frame(view)

# 3. Lines, rectangles, the layout before the draw, statistics, the overlay.
lines = view.set_lines(1, 3)
doc = view.native_document
report["lines"] = {
    "count": len(lines), "blocks": sorted({line.block for line in lines}),
    "geometry_lines": [doc.block_geometry(1).line_count, doc.block_geometry(2).line_count],
    "covers": [[line.start, line.end] for line in lines if line.block == 1],
    "text_length": len(view.texts[1]),
    "ascending": all(a.bottom <= b.bottom for a, b in zip(lines, lines[1:])),
    "hashable": len(set(lines)) == len(lines),
    "table": len(view.set_lines(view.tables[0], view.tables[0] + 1)),
    "table_geometry_lines": doc.block_geometry(view.tables[0]).line_count,
    "table_rows": view.table_geometry(view.tables[0]).row_count,
}
rects = view.span_rects(1, 0, len(view.texts[1]))
report["rects"] = {"count": len(rects), "first": list(rects[0]),
                   "line": [lines[0].left, lines[0].top], "none": view.span_rects(999, 0, 1)}
# (Asking for the table's lines laid the table out, which the window had not reached:
# its height is no longer the library's estimate, and a draw takes the new one in.)
frame(view)
calls.clear()
height = view.layout_for(steady["item"][0])
report["layout_for"] = {"height": height, "calls": list(calls), "view_height": view.height}
stats = view.stats
report["stats"] = stats._asdict()
plain = frame(view)["vertices"]
view.debug = True
report["debug_vertices"] = [plain, frame(view)["vertices"]]
view.debug = False
frame(view)

# 4. Inks per role, and what a change of palette costs.
def changed_by(action):
    calls.clear()
    before = (dict(view.edits), view.revision, list(view.texts), list(view.links))
    began = time.perf_counter()
    action()
    spent = time.perf_counter() - began
    at_once = list(calls)
    out = frame(view)
    return {
        "ms": round(spent * 1e3, 3), "calls_at_once": at_once, "frame_calls": out["calls"],
        "edits": {k: view.edits[k] - before[0][k] for k in before[0]},
        "revision": view.revision - before[1],
        "same_texts": list(view.texts) == before[2], "same_links": list(view.links) == before[3],
    }

report["colours_before"] = colours(view)
heading, code = 0xFF00FFFF, 0xFF00FF01
roles = DARK_PALETTE.with_roles({BlockKind.HEADING_1: heading, BlockKind.CODE: code})
tabled = roles.with_roles({BlockKind.TABLE: 0xFF0102FF})
palette = {}
palette["equal"] = changed_by(lambda: view.set_palette(dataclasses.replace(DARK_PALETTE)))
palette["roles"] = changed_by(lambda: view.set_palette(roles))
report["colours_roles"] = colours(view)
report["role_inks"] = [heading, code]
palette["roles_again"] = changed_by(lambda: view.set_palette(dataclasses.replace(roles)))
palette["table_role"] = changed_by(lambda: view.set_palette(tabled))
report["colours_tabled"] = colours(view)
palette["table_role_off"] = changed_by(lambda: view.set_palette(roles))
palette["ink"] = changed_by(lambda: view.set_palette(dataclasses.replace(roles, ink=0xFFCCCCCC)))
palette["rule"] = changed_by(
    lambda: view.set_palette(dataclasses.replace(roles, ink=0xFFCCCCCC, rule=0xFF336699))
)
view.set_colours(0, [(0, 3, 0xFF0000FE)])
view.select(((1, 2), (1, 9)))
view.style_links = True
palette["link"] = changed_by(
    lambda: view.set_palette(dataclasses.replace(roles, link=0xFF11EE11))
)
report["kept_over_a_link_ink"] = [view.selection, sorted(view._colours)]
view.style_links = None
view.clear_selection()
view.clear_colours()
palette["back"] = changed_by(lambda: view.set_palette(DARK_PALETTE))
report["palette"] = palette
report["colours_after"] = colours(view)

# 5. Another theme, the same view.
wide = dataclasses.replace(theme, px_per_inch=theme.px_per_inch * 1.25)
height = view.height
report["theme"] = changed_by(lambda: view.set_theme(wide))
frame(view)
report["theme"]["heights"] = [height, view.height]
report["theme"]["source_kept"] = view.source == source
blocks_view = TypesetView(parsed, theme=theme)
frame(blocks_view)
report["theme_blocks"] = {
    "sources": blocks_view.source_of(3) == parsed.sources[3],
    "source": blocks_view.source,
    "block_source": blocks_view.block_source(3, source) == view.block_source(3),
    "changed": blocks_view.set_theme(wide, parse_markdown(source, wide, math=True)),
    "texts": list(blocks_view.texts) == list(view.texts),
}
frame(blocks_view)
report["theme_blocks"]["height"] = [blocks_view.height, view.height]
blocks_view.close()
view.set_theme(theme)
frame(view)

# 6. Inks over ranges, beside marks handed over packed.
code_block = next(
    n for n, block in enumerate(view.blocks) if type(block).__name__ == "MarkdownCode"
)
report["code_block"] = code_block
view.scroll_to(code_block, align=0.0, always=True)
ink, behind = 0xFF0000FE, 0x8000FFFD
view.set_colours(code_block, [(0, 6, ink)])
view.set_colours(0, [(0, 3, ink)])
doc = view.native_document
view.set_marks(doc.pack_marks([ts.Mark(((1, 0), (1, 8)), behind, ts.MarkPlace.Behind)]))
frame(view)
seen = colours(view)
report["inks"] = {
    "ink": ink in seen, "behind": behind in seen, "packed_count": view._marks_for(doc).count,
    "module": typesetter.module() is not None,
}
for _ in range(6):  # the `scroll_to` above is looked at again for a few frames
    report["inks"]["frame_calls"] = frame(view)["calls"]

# Only the inks of the text in view are handed to the library, and what is drawn with those
# is, vertex for vertex, what is drawn with every one of them.
import re
long_code = TypesetView((ROOT / "demo" / "stream" / "code.md").read_text(encoding="utf-8"),
                        theme=theme)
at = max(range(len(long_code.texts)), key=lambda n: len(long_code.texts[n]))
words = list(re.finditer(r"\w+", long_code.texts[at]))
long_code.set_colours(at, [(m.start(), m.end(), 0xFF00FF00 + n % 7) for n, m in enumerate(words)])
long_code.set_colours(0, [(0, 2, 0xFF0000FE)])
frame(long_code)
doc = long_code.native_document
height = doc.size()[1]
culled = {"spans": len(words), "handed": [], "same": [], "inked": []}
for top in (0.0, 150.0, 1000.0, height / 2.0, height - 400.0, height + 50.0):
    clip = (0.0, top, 700.0, top + 400.0)
    some = long_code._marks_for(doc, (top, top + 400.0, 700.0))
    drawn = doc.draw_to_buffers((0.0, 0.0), clip, marks=some)
    handed = some.count if some else 0
    every = long_code._marks_for(doc)
    culled["handed"].append(handed)
    culled["same"].append(drawn == doc.draw_to_buffers((0.0, 0.0), clip, marks=every))
    culled["inked"].append(drawn != doc.draw_to_buffers((0.0, 0.0), clip))
    culled["every"] = every.count
report["culled"] = culled
long_code.close()

view.set_document(source + "\nA paragraph after everything.\n")
frame(view)
doc = view.native_document
report["inks"]["after_an_edit_at_the_end"] = [sorted(view._colours), view._marks_for(doc).count]
view.set_document("# Another\n\nDocument.\n")
frame(view)
report["inks"]["after_another_document"] = sorted(view._colours)
view.set_colours(0, [(0, 3, ink)])
view.clear_colours()
report["inks"]["cleared"] = sorted(view._colours)
view.set_document(source)
frame(view)

# 7. A sheet: the Document page's justified page of a fixed measure with margins.
MEASURE, MARGIN = 480.0, 36.0
sheet = TypesetView(source, theme=theme, math=True)
out = frame(sheet, at=(40.0 + MARGIN, 60.0 + MARGIN), width_px=MEASURE)
out = frame(sheet, at=(40.0 + MARGIN, 60.0 + MARGIN), width_px=MEASURE)
report["sheet"] = {
    "origin": out["origin"], "item": out["item"], "height": sheet.height,
    "right_edges": sorted({round(line.right, 2) for line in sheet.set_lines(1, 2)[:-1]}),
    "measure": MEASURE,
}
sheet.close()

# 8. What it costs from source to a first frame (reported, not asserted).
ts._lib = real
long = "\n\n".join([source] * 10)
def timed(make, repeat=5):
    spent = []
    for _ in range(repeat):
        began = time.perf_counter()
        made = make()
        spent.append(time.perf_counter() - began)
        made.close()
    return round(statistics.median(spent) * 1e3, 2)
report["timing"] = {
    "blocks": len(parse_markdown(long, theme, math=True).blocks),
    "direct_ms": timed(lambda: TypesetView(long, theme=theme, math=True)),
}
big = TypesetView(long, theme=theme, palette=DARK_PALETTE, math=True)
frame(big); frame(big)
def switch(action, repeat=5):
    spent = []
    for n in range(repeat):
        began = time.perf_counter()
        action(n)
        spent.append(time.perf_counter() - began)
        began = time.perf_counter()
        frame(big)
        spent[-1] = (spent[-1], time.perf_counter() - began)
    return [round(statistics.median(s[0] for s in spent) * 1e3, 3),
            round(statistics.median(s[1] for s in spent) * 1e3, 3)]
report["timing"]["steady_frame_ms"] = switch(lambda n: None)[1]
report["timing"]["roles_switch_ms_then_frame_ms"] = switch(
    lambda n: big.set_palette(DARK_PALETTE.with_roles({BlockKind.CODE: 0xFF00FF00 + n})))
big.style_links = True
report["timing"]["link_switch_ms_then_frame_ms"] = switch(
    lambda n: big.set_palette(dataclasses.replace(DARK_PALETTE, link=0xFF11EE11 + n)))
report["timing"]["theme_switch_ms_then_frame_ms"] = switch(
    lambda n: big.set_theme(dataclasses.replace(theme, px_per_inch=96.0 + n)))
def another(n):
    global big
    big = TypesetView(long, theme=theme, palette=DARK_PALETTE, math=True)
report["timing"]["new_view_ms_then_frame_ms"] = switch(another)
report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def members() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _MEMBERS, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert got["module_at_end"] is True and got["trouble"] == ""
    return got


def test_markdown_source_and_the_old_core_s_blocks_come_to_the_same_document(
    members: dict[str, Any],
) -> None:
    """
    Every markdown file under `demo/`, given to a view as a string (read by
    `imscribe.typeset_markdown`, no node material), against what a view given
    the blocks `build_document` made held (described by
    `imscribe.typesetter.Converter`). The second is FROZEN: the old path is
    deleted, and `tests/data/material_descriptions.json` has what it described.

    Equal: every block's text, its kind, marker, indent, quote depth, flags,
    level and extent, a table's columns and its cells' texts, the style
    table, the links (a table's cells' too) and the tables.

    **Restated on imtypeset 0.4.1: a code block's indent is the frozen one on
    the nearest whole pixel.** Until then every indent was compared to three
    decimals and a code block's was the theme's length as it came (15.999998
    px, and 45.6 px inside a list item). The library now sets a code face on
    the device's whole-pixel grid, and the view gives a code block a whole
    indent so that its glyphs stand on the rectangles the library answers for
    them (`_code_on_a_pixel`; `tests/test_mono_acceptance.py` measures it).
    Asserted below: every code block's indent in the view is whole and within
    half a pixel of the frozen one, and some did move.

    **The one difference allowed, and it is there** (`.concerns/SW-2--builder--
    result.md`, "The space beside a run"): which run a WHITE-SPACE character is
    in. The direct path sets a space in the face of the text it was written
    in, and a hard break's newline in no run; `Converter` reads glue, which has
    no face, and lets the run before it reach over it. So the runs are
    compared for what they say of every character that is not white space,
    and those are equal everywhere.
    """
    demos = members["demos"]
    assert len(demos) == 13
    for name, told in demos.items():
        assert told["converter"] == "MarkdownConverter", name
        assert told["blocks"][0] == told["blocks"][1] > 0, name
        assert told["differing_texts"] == [], name
        assert told["same_shape"] and told["same_styles"], name
        assert told["same_links"] and told["same_tables"], name
        assert told["runs_differing_off_white_space"] == [], name
        for ours, frozen in told["code_indents"]:
            assert ours == int(ours) and abs(ours - frozen) <= 0.5, (name, ours, frozen)
    moved = [pair for told in demos.values() for pair in told["code_indents"] if pair[0] != pair[1]]
    assert len(moved) > 5, moved
    # The difference is real: a test that compared nothing would pass without it.
    assert sum(told["runs_differ"] for told in demos.values()) > 20
    assert demos["demo/sample.md"]["runs_differ"] > 0
    # A table is a table block (6), in both: no Host block (5) stands for one.
    assert 6 in demos["demo/tables.md"]["kinds"] and 5 not in demos["demo/tables.md"]["kinds"]


def test_a_view_given_a_string_keeps_it_and_answers_where_each_block_came_from(
    members: dict[str, Any],
) -> None:
    sources = members["sources"]
    assert sources["held"] is True and sources["all"] is True
    assert sources["out_of_range"] == [None, None, None]
    assert sources["block_source"][0] == "# Boxes, Glue and Penalties\n"
    assert sources["block_source"][1].startswith("This document is the first litmus test.")
    assert sources["top"] is True
    assert sources["block_text"] == ["Boxes, Glue and Penalties", ""]
    assert sources["roles"][:3] == ["HEADING_1", "PARAGRAPH", ""]
    assert {"CODE", "TABLE", "QUOTE", "BULLET_ITEM", "ORDERED_ITEM", ""} <= set(sources["roles"])
    # "Copy as markdown": whole blocks, verbatim, the blank lines between them as written.
    selected = members["selected"]
    assert selected["blocks"] == [0, 1, 2] and selected["source"] == selected["expected"]
    # A block the selection only touches the edge of is not one of them.
    assert members["selected_edges"] == [1]
    assert members["selected_one"] == [[3], True]
    assert members["selected_none"] == [[], ""]
    # Blocks handed over with their sources (a `MarkdownDocument`): the map is there,
    # the string is not, and `block_source` takes it as an argument.
    told = members["theme_blocks"]
    assert told["sources"] is True and told["source"] is None and told["block_source"] is True


def test_a_string_that_changed_at_its_end_is_one_edit_of_its_last_blocks(
    members: dict[str, Any],
) -> None:
    """
    `parse_markdown` makes new objects at every call, and they are frozen
    values: the blocks before the first that is not EQUAL are kept, so an edit
    at the end of a source is not the whole document described again.
    """
    edit = members["string_edit"]
    assert edit["changed"] is True and edit["kept"] is True
    assert edit["calls"] == ["ReplaceDocumentBlocks"]
    assert edit["edits"] == {"set": 0, "replace": 1, "append": 0}
    assert edit["blocks"] == edit["library_blocks"] == 38
    assert edit["last"] == "One more paragraph at the end."


def test_a_frame_of_the_direct_path_is_the_same_three_calls(members: dict[str, Any]) -> None:
    """
    Drawn through `Document.draw(None, pos)`, the current window's draw list:
    `typesetter.window_draw_list()` is not asked.
    """
    assert members["steady_frame"]["calls"] == _FRAME
    assert members["steady_frame"]["answered"] is True
    assert members["steady_frame"]["vertices"] > 1000
    assert "SetDocumentBlocks" in members["first_frame"]["calls"]


def test_lines_rectangles_and_the_layout_before_the_draw(members: dict[str, Any]) -> None:
    lines = members["lines"]
    assert lines["blocks"] == [1, 2] and lines["count"] == sum(lines["geometry_lines"])
    covers = lines["covers"]
    assert covers[0][0] == 0 and covers[-1][1] == lines["text_length"]
    assert all(a[1] == b[0] for a, b in zip(covers, covers[1:], strict=False))
    assert lines["ascending"] is True and lines["hashable"] is True
    # A table answers what the library counts as its lines: here one a row
    # and one for the rule under the header (`table_row` is what places rows).
    assert lines["table"] == lines["table_geometry_lines"] == lines["table_rows"] + 1
    rects = members["rects"]
    assert rects["count"] == len(covers) and rects["none"] == []
    assert rects["first"][:2] == pytest.approx(rects["line"], abs=0.01)
    told = members["layout_for"]
    # At the width the frame uses nothing is laid out again: the library is asked and answers.
    assert told["calls"] == ["LayoutDocument", "GetDocumentSize"]
    assert told["height"] == told["view_height"]


def test_stats_are_the_draw_s_own_count_and_the_library_s_counters(
    members: dict[str, Any],
) -> None:
    """
    `draw` still returns a bool; `stats` is read when a page wants more, and is
    one library call then and none otherwise (the steady frame above is three).
    """
    stats = members["stats"]
    assert stats["whole"] is True and stats["vertices"] == members["steady_frame"]["vertices"]
    assert stats["blocks"] == 37 and stats["blocks_laid_out"] > 0 and stats["blocks_drawn"] > 0
    assert (stats["tables"], stats["cells"], stats["hosts"]) == (0, 0, 0)
    plain, overlaid = members["debug_vertices"]
    assert overlaid > plain


def test_what_each_part_of_a_palette_costs_to_change(members: dict[str, Any]) -> None:
    """
    Counted at the ctypes library. `calls_at_once` are the calls `set_palette`
    itself made and `frame_calls` those of the draw after it.

    - An equal palette, another object: NOTHING (review SW-R1, finding R2: it
      used to lay every cell of every table out again).
    - Role inks, a table's among them (a table is a block and its ink is its
      style's): one `set_blocks` and no parse, no describe (`revision` does
      not move); the frame after is the three calls.
    - `ink`: no call at once, and the three of the frame.
    - `rule`: one `set_options`.
    - `link`, with links styled: every block described again, a new document.
    """
    palette = members["palette"]
    for name in ("equal", "roles_again"):
        told = palette[name]
        assert told["calls_at_once"] == [] and told["frame_calls"] == _FRAME, name
        assert told["edits"] == {"set": 0, "replace": 0, "append": 0} and told["revision"] == 0
    for name in ("roles", "table_role", "table_role_off", "back"):
        told = palette[name]
        assert told["calls_at_once"] == ["SetDocumentBlocks"], name
        assert told["frame_calls"] == _FRAME, name
        assert told["edits"] == {"set": 1, "replace": 0, "append": 0} and told["revision"] == 0
        assert told["same_texts"] and told["same_links"]
    assert palette["ink"]["calls_at_once"] == [] and palette["ink"]["edits"]["set"] == 0
    assert palette["ink"]["frame_calls"] == _FRAME and palette["ink"]["revision"] == 0
    assert palette["rule"]["frame_calls"] == ["SetDocumentOptions", *_FRAME]
    link = palette["link"]
    assert link["edits"] == {"set": 1, "replace": 0, "append": 0} and link["revision"] == 1
    assert "CreateDocument" in link["frame_calls"] and link["same_texts"] and link["same_links"]
    # The same characters, so what named ranges of them was kept across it.
    assert members["kept_over_a_link_ink"] == [[[1, 2], [1, 9]], [0]]


def test_a_role_s_ink_reaches_the_vertices_of_its_blocks(members: dict[str, Any]) -> None:
    heading, code = members["role_inks"]
    assert heading not in members["colours_before"] and code not in members["colours_before"]
    assert heading in members["colours_roles"] and code in members["colours_roles"]
    assert heading not in members["colours_after"] and code not in members["colours_after"]
    # A table's role inks its cells: the ink is the table block's style's.
    assert 0xFF0102FF not in members["colours_roles"]
    assert 0xFF0102FF in members["colours_tabled"]


def test_another_theme_is_taken_by_the_same_view(members: dict[str, Any]) -> None:
    """
    A view holding the string reads it again; one holding blocks is given the
    blocks built with the new theme. One new library document either way.
    """
    theme = members["theme"]
    assert theme["edits"] == {"set": 1, "replace": 0, "append": 0}
    assert theme["same_texts"] and theme["same_links"] and theme["source_kept"]
    before, after = theme["heights"]
    assert after > before * 1.2  # set a quarter larger, at the same width
    blocks = members["theme_blocks"]
    assert blocks["changed"] is True and blocks["texts"] is True
    assert blocks["height"][0] == blocks["height"][1]


def test_inks_over_ranges_are_drawn_beside_marks_handed_over_packed(
    members: dict[str, Any],
) -> None:
    """
    `set_colours` (syntax colour) and `set_marks` with what `pack_marks`
    returned (find) on the same frame: the library's draw takes one array, and
    `_joined` makes it from the two. If the package's packed type changes shape
    this is where it shows.
    """
    inks = members["inks"]
    assert inks["ink"] is True and inks["behind"] is True and inks["module"] is True
    assert inks["packed_count"] == 3
    # While inks are set a frame asks which text the window shows: two hit tests.
    assert inks["frame_calls"] == [
        "LayoutDocument",
        "HitTestDocument",
        "HitTestDocument",
        "DrawDocument",
        "GetDocumentSize",
    ]
    # A 600-line code block with an ink on every word: a window of 400 px is handed the
    # inks of the lines it shows, not the block's, and draws exactly what all of them draw.
    culled = members["culled"]
    assert culled["every"] == culled["spans"] + 1 > 1500
    assert all(culled["same"]), culled
    assert max(culled["handed"]) < culled["every"] / 5
    assert culled["inked"][:5] == [True] * 5 and culled["handed"][5] <= 10
    # An edit at the end: the inks of blocks it left alone stay; packed marks go, as before.
    assert inks["after_an_edit_at_the_end"][0] == [0, members["code_block"]]
    assert inks["after_an_edit_at_the_end"][1] == 2
    assert inks["after_another_document"] == [] and inks["cleared"] == []


def test_a_sheet_of_a_fixed_measure_is_the_view_drawn_at_a_width(members: dict[str, Any]) -> None:
    """
    What replaces `DocumentView.page()` for the Document page: the host draws
    its sheet, puts the cursor a margin in, and gives `draw` the measure. The
    view starts at the cursor, claims exactly the measure, and a justified
    paragraph's lines (all but its last) end at it.
    """
    sheet = members["sheet"]
    assert sheet["origin"] == [76, 96]
    assert sheet["item"] == [sheet["measure"], sheet["height"]]
    assert sheet["right_edges"] == [pytest.approx(sheet["measure"], abs=0.01)]


def test_the_costs_are_reported_and_not_judged(members: dict[str, Any]) -> None:
    timing = members["timing"]
    assert timing["blocks"] == 370
    for name in ("direct_ms", "steady_frame_ms"):
        assert timing[name] > 0
    for name in ("roles_switch", "link_switch", "theme_switch", "new_view"):
        assert len(timing[f"{name}_ms_then_frame_ms"]) == 2


# ---------------------------------------------------------------------------
# 5. Tables: the library's block, against the old core's table arithmetic (frozen)
# ---------------------------------------------------------------------------

_TABLES = r"""
import dataclasses, json, struct, sys
from pathlib import Path

from imgui_bundle import imgui

from imscribe import typesetter
from imscribe.description import ColumnDescription, cell_spans
from imscribe.theme import BlockKind, Theme
from imscribe.typeset_find import Finder, FindIndex
from imscribe.typeset_markdown import MarkdownTable, parse_markdown
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView
from imscribe.units import px_from_sp, sp_from_px

ROOT = Path(sys.argv[1])
WIDTH = 684.0
report = {"module": typesetter.module() is not None,
          "load_start": ["%.2f" % x for x in __import__("os").getloadavg()]}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
ts = typesetter.module()
calls = []

class Counting:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)
    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            calls.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)
        return call

ts._lib = Counting(ts._lib)

def frame(view, *, mouse=None, button=None, width=WIDTH, scroll=None, **more):
    # One frame of the view in a scrolling child, `width` wide whatever the pane.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(760.0, 640.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##text")
        try:
            if scroll is not None:
                imgui.set_scroll_y(scroll)
            calls.clear()
            answered = view.draw(width_px=width, **more)
            return {"answered": answered, "calls": list(calls), "vertices": view.stats.vertices,
                    "hovered": view.hovered_link,
                    "hand": imgui.get_mouse_cursor() == imgui.MouseCursor_.hand,
                    "selection": view.selection}
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()

def colours(view):
    doc = view.native_document
    vertices, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, WIDTH, 100000.0), marks=view._marks_for(doc)
    )
    return sorted(
        {struct.unpack_from("<I", vertices, at + 16)[0] for at in range(0, len(vertices), 20)}
    )

def columns_of(view, at):
    count = view.table_geometry(at).column_count
    return [view.table_column(at, column) for column in range(count)]

def rows_of(view, at):
    count = view.table_geometry(at).row_count
    return [view.table_row(at, row) for row in range(count)]

def on_screen(view, position):
    # The middle of the character at `position`, on screen.
    doc = view.native_document
    x0, y0, _, y1 = doc.caret_rect(position)
    x1 = doc.caret_rect((position[0], position[1] + 1))[0]
    ox, oy = view.origin
    return (ox + (x0 + x1) / 2.0, oy + (y0 + y1) / 2.0)

theme = Theme.build()
ppi = theme.px_per_inch
source = (ROOT / "demo" / "tables.md").read_text(encoding="utf-8")
# What the old core's own table layout answered for these tables at this width, in pixels
# (`imscribe.ui.table_columns`, `table_column_limits`, `composition._table_boxes`), frozen by
# `.concerns/T5-B1-scripts/freeze_views.py`. Until tranche 5 it was asked here.
frozen = json.loads((ROOT / "tests" / "data" / "material_tables.json").read_text(encoding="utf-8"))
assert frozen["width_px"] == WIDTH
old = {table["block"]: table for table in frozen["tables"]}

# 1. demo/tables.md, against the old core's own table arithmetic.
compared = {}
for name, document in (("direct", source),):
    view = TypesetView(document, theme=theme, palette=DARK_PALETTE, math=True)
    before = [view.table_geometry(at) for at in view.tables]
    first = frame(view)
    steady = [frame(view)["calls"] for _ in range(3)]
    scrolled = [frame(view, scroll=400.0), frame(view), frame(view)]
    tables = []
    assert sorted(old) == list(view.tables), "the frozen tables are not this document's"
    for at in view.tables:
        block = old[at]
        geometry = view.table_geometry(at)
        columns, rows = columns_of(view, at), rows_of(view, at)
        tables.append({
            "block": at, "header": block["header"],
            "shape": [geometry.row_count, geometry.column_count, geometry.cell_count],
            "old_shape": block["old_shape"],
            "stated": geometry.stated, "laid_out": geometry.laid_out,
            "width": [[c.max - c.min for c in columns], block["width"]],
            "natural": [[c.natural for c in columns], block["natural"]],
            "floor": [[c.floor for c in columns], block["floor"]],
            # The old core's boxes are the header, its rule, then the rows.
            "row_heights": [[r.max - r.min for r in rows], block["row_heights"]],
            "row_tops": [r.min - rows[0].min for r in rows],
            "wrapped": [r.wrapped for r in rows],
            "edges": [geometry.min[0], geometry.max[0], columns[0].min, columns[-1].max],
            "block_rect_height": view.block_rect(at)[3] - view.block_rect(at)[1],
        })
    compared[name] = {
        "before_a_draw": before, "first": first["calls"], "steady": steady,
        "scrolled": [one["calls"] for one in scrolled],
        "vertices": [first["vertices"], scrolled[-1]["vertices"]],
        "answered": [first["answered"], scrolled[-1]["answered"]],
        "tables": tables, "table_blocks": list(view.tables),
        "not_a_table": [view.table_geometry(0), view.table_column(0, 0), view.table_row(0, 0)],
        "stats": [view.stats.tables, view.stats.cells],
    }
    view.close()
report["compared"] = compared

# 2. One small table: selection and copy in cells, a link in a cell, marks and inks in cells.
SMALL = (
    "Before the table.\n\n"
    "| name | where it goes |\n|:--|--:|\n"
    "| alpha glue | [a link](https://cell.example) |\n"
    "| beta | gamma glue |\n\n"
    "After the table, glue.\n"
)
clicked = []
view = TypesetView(SMALL, theme=theme, palette=DARK_PALETTE, on_link=clicked.append)
# (The pane is the one the documents above were scrolled in: back to its top first.)
frame(view, mouse=(740.0, 620.0), scroll=0.0)
frame(view)
table = view.tables[0]
text = view.texts[table]
spans = cell_spans(view._described[table].rows)
report["small"] = small = {"text": text, "table": table, "spans": spans,
                           "links": [list(row) for row in view.links]}
# From inside one cell to inside a cell of the next row.
start, end = spans[1][0][0] + 6, spans[2][1][0] + 5
view.select(((table, start), (table, end)))
small["across_cells"] = [view.selected_text(), text[start:end]]
view.select(((table, spans[1][0][0] + 1), (table, spans[1][0][0] + 5)))
small["in_a_cell"] = view.selected_text()
view.select(((0, 7), (table, spans[0][1][0] + 5)))
small["from_before"] = view.selected_text()
view.select(((table, spans[2][0][0]), (2, 5)))
small["to_after"] = view.selected_text()
view.select_all()
small["everything"] = [view.selected_text(), view.separator.join(view.texts)]
view.clear_selection()
doc = view.native_document
position = doc.table_position(table, 2, 1, 3)
small["positions"] = [list(position), list(doc.table_cell((table, spans[2][1][0] + 3)))]

# The link in a cell: hovered, the hand, a click follows it and selects nothing.
row = view.links[0]
at = on_screen(view, (row.block, row.start + 2))
idle = frame(view)
over = [frame(view, mouse=at), frame(view)]
frame(view, button=True)
frame(view)
frame(view, button=False)
after = frame(view)
away = [frame(view, mouse=(740.0, 620.0)), frame(view)]
small["link"] = {
    "row": list(row), "target": row.target,
    "idle": [idle["hovered"], idle["hand"], idle["calls"]],
    "over": [over[1]["hovered"], over[1]["hand"], over[1]["calls"]],
    "clicked": list(clicked), "selection": after["selection"],
    "away": [away[1]["hovered"], away[1]["hand"], away[1]["calls"]],
}

# A drag from one cell into another selects, in reading order, through the library.
a = on_screen(view, (table, spans[1][0][0] + 2))
b = on_screen(view, (table, spans[2][1][0] + 4))
frame(view, mouse=a)
frame(view)
frame(view, button=True)
frame(view)
dragged = [frame(view, mouse=b), frame(view)]
frame(view, button=False)
released = frame(view)
small["drag"] = {"selection": released["selection"], "text": view.selected_text(),
                 "calls": dragged[1]["calls"]}
view.clear_selection()
frame(view, mouse=(740.0, 620.0))

# Find: the cells are searched, and their marks reach the draw list.
finder = Finder(FindIndex.of(view._described))
finder.search("glue")
plain = frame(view)["vertices"]
view.set_marks(finder.marks())
marked = frame(view)
in_table = [m for m in finder.matches if m.block == table]
view.set_marks([mark for mark in finder.marks() if mark.range[0][0] != table])
outside = frame(view)["vertices"]
view.set_marks(None)
small["find"] = {"matches": [list(m) for m in finder.matches], "in_table": len(in_table),
                 "found": [view.texts[m.block][m.start:m.end] for m in finder.matches],
                 "vertices": [plain, marked["vertices"], outside], "calls": marked["calls"]}
# An ink over part of a cell.
ink = 0xFF0103FE
before = colours(view)
view.set_colours(table, [(spans[2][0][0], spans[2][0][1], ink)])
frame(view)
small["ink"] = [ink in before, ink in colours(view), frame(view)["calls"]]
view.clear_colours()
frame(view)

# 3. Columns a host states.
auto = [(c.min, c.max) for c in columns_of(view, table)]
naturals = [c.natural for c in columns_of(view, table)]
described = view._described[table].columns
calls.clear()
changed = view.set_table_columns(table, [(1, 200.0, 0.0), ColumnDescription(3, 150.0)])
at_once = list(calls)
out = frame(view)
stated = view.table_geometry(table)
columns = {"auto": auto, "changed": changed, "at_once": at_once, "frame": out["calls"],
           "stated": [stated.stated, stated.min[0], stated.max[0]],
           "edges": [(c.min, c.max) for c in columns_of(view, table)],
           "naturals": [naturals, [c.natural for c in columns_of(view, table)]],
           "described": [list(c) for c in view._described[table].columns]}
calls.clear()
columns["same_again"] = [view.set_table_columns(table, [(1, 200.0, 0.0), (3, 150.0, 0.0)]),
                         list(calls)]
# The document handed to the library again (a role's ink) keeps them.
view.set_palette(DARK_PALETTE.with_roles({BlockKind.TABLE: 0xFF0102FF}))
frame(view)
columns["after_roles"] = [(c.min, c.max) for c in columns_of(view, table)]
# So does a closed document.
view.close()
frame(view)
columns["after_close"] = [(c.min, c.max) for c in columns_of(view, table)]
columns["shares"] = view.set_table_columns(table, [(1, 0.0, 1.0), (3, 0.0, 3.0)])
frame(view)
columns["shared"] = [(c.min, c.max) for c in columns_of(view, table)]
calls.clear()
columns["back"] = [view.set_table_columns(table, None), list(calls)]
frame(view)
columns["after_back"] = [(c.min, c.max) for c in columns_of(view, table)]
columns["described_back"] = view._described[table].columns == described
columns["back_again"] = view.set_table_columns(table, None)
try:
    view.set_table_columns(0, [(1, 10.0, 0.0)])
    columns["not_a_table"] = "taken"
except ValueError as exc:
    columns["not_a_table"] = str(exc)
# A column that is no column is the host's mistake: refused at the call, with
# the table as it was and no call made, and the library goes on drawing.
refused = {}
for name, bad in (
    ("text_width", [(1, "wide")]),
    ("text_share", [(1, 0.0, "half"), (3, 0.0, 1.0)]),
    ("text_align", [("left", 100.0), (3, 150.0)]),
    ("made_with_text", [ColumnDescription(1, "wide"), ColumnDescription(3, 150.0)]),
    ("a_word", ["wide", "narrow"]),
    ("nothing", [None, 150.0]),
    ("too_long", [(1, 100.0, 0.0, 9), (3, 150.0)]),
    ("second_of_two", [120.0, (3, "narrow")]),
):
    calls.clear()
    try:
        view.set_table_columns(table, bad)
        outcome = "taken"
    except TypesetUnavailable as exc:
        outcome = "switched off: " + str(exc)
    except TypeError as exc:
        ours = "set_table_columns: column" in str(exc)
        outcome = "TypeError" if ours else "TypeError " + str(exc)
    refused[name] = [outcome, list(calls), typesetter.module() is not None,
                     view._described[table].columns == described]
columns["refused"] = refused
try:
    frame(view)
    columns["after_refused"] = [(c.min, c.max) for c in columns_of(view, table)]
except TypesetUnavailable as exc:
    columns["after_refused"] = str(exc)
# An edit that replaces the block drops what was stated.
view.set_table_columns(table, [(1, 200.0, 0.0), (3, 150.0, 0.0)])
frame(view)
view.set_document(SMALL.replace("| beta |", "| beta beta |"))
frame(view)
columns["after_an_edit"] = [view.table_geometry(table).stated,
                            [(c.min, c.max) for c in columns_of(view, table)]]
report["columns"] = columns
view.close()

# 4. A table that states its columns in the description: a MarkdownTable with widths.
#    And a table in a list item.
SIZED = "| a | b |\n|---|---|\n| one | two |\n"
widths = (sp_from_px(120.0, ppi), sp_from_px(90.0, ppi))
(parsed,) = parse_markdown(SIZED, theme).blocks
direct = TypesetView([dataclasses.replace(parsed, widths=widths)], theme=theme)
frame(direct)
report["sized"] = {
    "direct": [direct.table_geometry(0).stated, [(c.min, c.max) for c in columns_of(direct, 0)]],
    "wanted": [px_from_sp(w, ppi) for w in widths],
}
direct.close()
INDENTED = "- An item, and under it:\n\n  | a | b |\n  |---|---|\n  | one | two |\n"
inner = TypesetView(INDENTED, theme=theme)
frame(inner)
at = inner.tables[0]
geometry = inner.table_geometry(at)
report["indented"] = {"indent": inner._described[at].left_indent,
                      "edges": [geometry.min[0], geometry.max[0]], "width": WIDTH}
inner.close()

# 5. A point in a cell's rectangle answers THAT cell: on its text, on the blank after it,
#    on the padding of a row's last cell. (At be40444 the blank answered the next cell; the
#    other team's 7a7bc36 fixed it, their D60.)
view = TypesetView(SMALL, theme=theme)
frame(view)
doc = view.native_document
first, second = columns_of(view, table)
row1 = rows_of(view, table)[1]
y = (row1.min + row1.max) / 2.0
hits = {}
for name, x in (("on_text", first.min + 12.0), ("blank_of_the_first", first.max - 3.0),
                ("padding_after_the_last", second.max - 2.0)):
    hit = doc.hit_test((x, y))
    hits[name] = [hit.row, hit.column, hit.position.block, hit.in_block]
report["blank_cell_hits"] = hits

# 6. The context goes: the geometry is unknown until a draw makes the document again.
typesetter.unload()
report["unloaded"] = [view.table_geometry(table), typesetter.load_fonts()]
frame(view)
report["reloaded"] = view.table_geometry(table).row_count
report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def tables() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _TABLES, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got["reason"]
    assert got["trouble"] == "" and got["module_at_end"] is True
    return got


_LINE_PX = 21.6
"""A line of the stock table style, in pixels: what a one-line row is tall."""


@pytest.mark.parametrize("name", ["direct"])
def test_the_five_tables_have_imscribe_s_columns(tables: dict[str, Any], name: str) -> None:
    """
    `demo/tables.md` at 684 px: every column of every table is as wide as
    `imscribe.ui.table_columns` made it, and wants (`natural`) and can be
    squeezed to (`floor`) what `table_column_limits` said (the old core's
    answers, frozen in `tests/data/material_tables.json`), to a thousandth
    of a pixel. Two of the five are scaled up to the
    measure and three are squeezed and wrapped, so both of the old core's
    regimes are in it. Each table fills the measure from its left edge.
    """
    told = tables["compared"][name]
    assert told["table_blocks"] == [4, 7, 10, 13, 16]
    wrapped = 0
    for table in told["tables"]:
        assert table["shape"][:2] == table["old_shape"], table["block"]
        assert table["shape"][2] == table["shape"][0] * table["shape"][1]
        assert table["stated"] is False and table["laid_out"] is True
        for what in ("width", "natural", "floor"):
            ours, theirs = table[what]
            assert ours == pytest.approx(theirs, abs=0.001), (table["block"], what)
        assert table["edges"] == pytest.approx([0.0, 684.0, 0.0, 684.0], abs=0.001)
        wrapped += any(table["wrapped"])
    assert wrapped == 3


@pytest.mark.parametrize("name", ["direct"])
def test_every_row_is_as_tall_as_imscribe_makes_it_and_the_rule_takes_a_line(
    tables: dict[str, Any], name: str
) -> None:
    """
    Row for row the height `imscribe.ui.composition._table_boxes` gave it
    (one line, or as many as its tallest cell wraps to; frozen).

    **The difference, measured and not hidden**: the old core's boxes are
    the header, a rule 0.96 px thick, then the rows. The library's rows do
    not tile the table either, but the space between the header and the
    first row is a whole line (21.6 px) whatever `TableRuleThickness` is, so
    a table with a header is 20.64 px taller than the old core's.
    """
    for table in tables["compared"][name]["tables"]:
        assert table["header"] is True
        ours, theirs = table["row_heights"]
        header, rule, *rows = theirs
        assert rule == pytest.approx(0.96, abs=0.001)
        assert ours == pytest.approx([header, *rows], abs=0.001), table["block"]
        tops = table["row_tops"]
        assert tops[1] - (tops[0] + ours[0]) == pytest.approx(_LINE_PX, abs=0.001)
        # After the header's line the rows do tile.
        for at in range(1, len(ours) - 1):
            assert tops[at + 1] == pytest.approx(tops[at] + ours[at], abs=0.001)
        height = tops[-1] + ours[-1]
        assert height == pytest.approx(sum(theirs) - rule + _LINE_PX, abs=0.001)
        assert table["block_rect_height"] >= height - 0.001


@pytest.mark.parametrize("name", ["direct"])
def test_a_frame_with_tables_in_view_is_the_same_three_calls(
    tables: dict[str, Any], name: str
) -> None:
    """
    The budget is back to three: a table is a block of the document, drawn by
    the document's one draw call, here with two tables in the window and then,
    scrolled, with others. No paragraph is made for a cell and no block is
    given a height. (The stopgap this replaced made 3 + a call a table in
    view + two a cell in view: 37 for the same first window.)
    """
    told = tables["compared"][name]
    assert told["first"] == [
        "GetCurrentContext",
        "CreateDocument",
        "SetDocumentBlocks",
        "SetDocumentOptions",
        *_FRAME,
    ]
    assert told["steady"] == [_FRAME] * 3 and told["scrolled"] == [_FRAME] * 3
    assert told["answered"] == [True, True] and min(told["vertices"]) > 1000
    # Nothing is known of a table before the first draw, nor of a block that is none.
    assert told["before_a_draw"] == [None] * 5 and told["not_a_table"] == [None] * 3
    assert told["stats"] == [0, 0]


def test_a_selection_and_a_copy_go_through_cells(tables: dict[str, Any]) -> None:
    """
    Positions in a table are offsets into its text (`texts[n]`: a tab between
    the cells of a row, a newline between rows), so a selection from one cell
    into another copies exactly that stretch of the text, and one that runs
    in from the paragraph before or out into the one after has the block
    separator between the table and its neighbour.
    """
    small = tables["small"]
    assert small["text"] == "name\twhere it goes\nalpha glue\ta link\nbeta\tgamma glue"
    copied, stretch = small["across_cells"]
    assert copied == stretch == "glue\ta link\nbeta\tgamma"
    assert small["in_a_cell"] == "lpha"
    assert small["from_before"] == "the table.\n\nname\twhere"
    assert small["to_after"] == "beta\tgamma glue\n\nAfter"
    everything, joined = small["everything"]
    assert everything == joined
    # (block, offset) to (row, column, cell, offset in the cell) and back.
    assert small["positions"] == [[1, small["spans"][2][1][0] + 3], [2, 1, 5, 3]]
    # A drag from a cell to a cell of the next row: one `select_range` a frame.
    drag = small["drag"]
    (block, start), (_, end) = drag["selection"]
    assert block == small["table"] and drag["text"] == small["text"][start:end]
    assert "\t" in drag["text"] and "\n" in drag["text"]
    assert drag["calls"] == [*_FRAME, "SelectDocumentRange"]


def test_a_link_in_a_cell_is_hovered_and_followed(tables: dict[str, Any]) -> None:
    """
    The tag is in the cell's runs and the document's own hit test answers it:
    one call under the mouse, as for a link anywhere else.
    """
    small = tables["small"]
    assert small["links"] == [[1, 30, 36, 1, "https://cell.example"]]
    assert small["text"][30:36] == "a link"
    link = small["link"]
    assert link["idle"] == [None, False, _FRAME]
    assert link["over"] == ["https://cell.example", True, [*_FRAME, "HitTestDocument"]]
    assert link["clicked"] == ["https://cell.example"] and link["selection"] is None
    assert link["away"] == [None, False, _FRAME]


def test_find_marks_and_inks_are_drawn_in_cells(tables: dict[str, Any]) -> None:
    small = tables["small"]
    find = small["find"]
    assert find["found"] == ["glue"] * 3 and find["in_table"] == 2
    plain, marked, outside = find["vertices"]
    # A rectangle (four vertices) behind each match: three, of which two in cells.
    assert marked == plain + 12 and outside == plain + 4
    assert find["calls"] == _FRAME
    was_there, is_there, calls = small["ink"]
    assert was_there is False and is_there is True
    assert calls == [_LAYOUT, "HitTestDocument", "HitTestDocument", _DRAW, _SIZE]


def test_columns_a_host_states_are_one_call_and_are_kept(tables: dict[str, Any]) -> None:
    """
    `set_table_columns`: what a drag of a column's edge does each frame.
    """
    columns = tables["columns"]
    auto = columns["auto"]
    assert auto[0][0] == 0.0 and auto[1][1] == pytest.approx(684.0, abs=0.001)
    assert columns["changed"] is True and columns["at_once"] == ["SetDocumentTableColumns"]
    assert columns["frame"] == _FRAME
    # Exactly the widths stated, whatever the pane's; the alignments given too.
    assert columns["stated"] == [True, 0.0, 350.0]
    assert columns["edges"] == [[0.0, 200.0], [200.0, 350.0]]
    assert columns["described"] == [[1, 200.0, 0.0], [3, 150.0, 0.0]]
    # What the cells want does not depend on what they are given.
    assert columns["naturals"][0] == columns["naturals"][1]
    assert columns["same_again"] == [False, []]
    # Kept across the document being handed over again, and across a closed one.
    assert columns["after_roles"] == columns["edges"] == columns["after_close"]
    # Shares of the pane: a quarter and three quarters.
    assert columns["shares"] is True
    assert columns["shared"] == [[0.0, 171.0], [171.0, 684.0]]
    assert columns["back"] == [True, ["SetDocumentTableColumns"]]
    assert columns["after_back"] == auto and columns["described_back"] is True
    assert columns["back_again"] is False
    assert columns["not_a_table"] == "block 0 is not a table"
    # A malformed column is refused where it is given (`TypeError`, as
    # `set_marks` refuses a mark): no call, nothing kept of it, and the
    # library is not switched off for the host's mistake.
    assert columns["refused"] == {
        name: ["TypeError", [], True, True]
        for name in (
            "text_width",
            "text_share",
            "text_align",
            "made_with_text",
            "a_word",
            "nothing",
            "too_long",
            "second_of_two",
        )
    }
    assert columns["after_refused"] == auto
    # An edit that replaces the block: the table is the library's to fit again.
    stated, edges = columns["after_an_edit"]
    assert stated is False and edges[1][1] == pytest.approx(684.0, abs=0.001)


def test_a_table_that_states_its_columns_and_one_in_a_list_item(tables: dict[str, Any]) -> None:
    """
    A `MarkdownTable` with `widths` is drawn at those widths, in pixels. A
    table inside a list item starts at its indent and shares what is left.
    (The old core's `SizedTable`, `with_columns`, was the other half of this
    until tranche 5: the view no longer takes the old core's blocks.)
    """
    sized = tables["sized"]
    first, second = sized["wanted"]
    for name in ("direct",):
        stated, edges = sized[name]
        assert stated is True, name
        flat = [edge for column in edges for edge in column]
        assert flat == pytest.approx([0.0, first, first, first + second], abs=0.001), name
    indented = tables["indented"]
    assert indented["indent"] > 20.0
    assert indented["edges"] == pytest.approx([indented["indent"], indented["width"]], abs=0.001)


def test_a_point_in_a_cell_answers_that_cell_on_its_text_its_blank_and_its_padding(
    tables: dict[str, Any],
) -> None:
    """
    The row and the column of a hit are those of the cell whose rectangle
    holds the point: on the text, on the blank after left-aligned text, and
    on the padding after a row's last cell. The block is right in every case.

    This replaces a test that PINNED A DEFECT of the library at `be40444`
    (`test_a_point_on_the_blank_of_a_cell_answers_the_next_cell_as_the_other_
    team_lists`: the blank answered column 1, and the padding after the last
    cell the next row's first) and said to delete it when it began to fail.
    It began to fail at the other team's `7a7bc36`
    (`../imtypeset/docs/advtext-swap-status.md`, "which cell a point is in",
    their D60), which is the library this tree pins.
    """
    hits = tables["blank_cell_hits"]
    assert hits["on_text"] == [1, 0, 1, True]
    assert hits["blank_of_the_first"] == [1, 0, 1, True]
    assert hits["padding_after_the_last"] == [1, 1, 1, True]


def test_unload_forgets_the_geometry_and_a_draw_has_it_again(tables: dict[str, Any]) -> None:
    assert tables["unloaded"] == [None, True]
    assert tables["reloaded"] == 3


# ----------------------------------------------------------------------
# Columns (tranche 5): `set_columns`, `column_count`, `column`, `column_pos`
# ----------------------------------------------------------------------

_COLUMNS = r"""
import json, math, struct, sys
from pathlib import Path

from imgui_bundle import imgui

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownCode, MarkdownStream
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import MAX_COLUMNS, TypesetUnavailable, TypesetView

ROOT = Path(sys.argv[1])
WIDTH = 900.0
PANE = (1240.0, 640.0)
report = {"module": typesetter.module() is not None,
          "load_start": ["%.2f" % x for x in __import__("os").getloadavg()]}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1300.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
ts = typesetter.module()
calls = []

class Counting:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)
    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            calls.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)
        return call

ts._lib = Counting(ts._lib)
PARKED = (1280.0, 690.0)

def frame(view, *, mouse=None, button=None, width=WIDTH, sideways=False, name="##text", **more):
    # One frame of the view in a child, `width` wide whatever the pane.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(1260.0, 680.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        flags = imgui.WindowFlags_.horizontal_scrollbar.value if sideways else 0
        imgui.begin_child(name, imgui.ImVec2(*PANE), 0, flags)
        try:
            calls.clear()
            answered = view.draw(width_px=width, **more)
            return {"answered": answered, "calls": list(calls), "vertices": view.stats.vertices,
                    "selection": view.selection,
                    "scroll": [imgui.get_scroll_x(), imgui.get_scroll_y()],
                    "scrolled": view.scrolled, "item": [imgui.get_item_rect_size().x,
                                                        imgui.get_item_rect_size().y]}
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()

def colours(view):
    # Every ink among the vertices of the whole page, with the view's marks and inks.
    doc = view.native_document
    vertices, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, 100000.0, 100000.0), marks=view._marks_for(doc)
    )
    return {struct.unpack_from("<I", vertices, at + 16)[0] for at in range(0, len(vertices), 20)}

def every_column(view):
    # Every column there is, in order. Cuts them all.
    found, k = [], 0
    while True:
        one = view.column(k)
        if not one.exists:
            return found
        found.append(one)
        k += 1

def told(column):
    return {"min": list(column.min), "max": list(column.max),
            "content_min": list(column.content_min), "content_max": list(column.content_max),
            "start": list(column.start), "end": list(column.end),
            "uncut_top": column.uncut_top, "overfull": column.overfull}

def on_screen(view, position):
    # The middle of the character at `position`, on screen.
    doc = view.native_document
    x0, y0, _, y1 = doc.caret_rect(position)
    x1 = doc.caret_rect((position[0], position[1] + 1))[0]
    ox, oy = view.origin
    return (ox + (x0 + x1) / 2.0, oy + (y0 + y1) / 2.0)

def between(view, start, end):
    # What a copy of [start, end) gives, worked out from `texts` alone.
    (b0, o0), (b1, o1) = start, end
    texts = view.texts
    if b0 == b1:
        return texts[b0][o0:o1]
    parts = [texts[b0][o0:], *texts[b0 + 1:b1], texts[b1][:o1]]
    return view.separator.join(part for part in parts if part)

theme = Theme.build()
source = (ROOT / "demo" / "columns.md").read_text(encoding="utf-8")

# 1. demo/columns.md in three columns filled in order.
view = TypesetView(source, theme=theme, palette=DARK_PALETTE)
before = {"count": view.column_count(), "column": view.column(0), "columns": view.columns,
          "pos": list(view.column_pos((3.0, 4.0))), "width": view.width,
          "column_width": view.column_width}
uncut_first = frame(view, mouse=PARKED)
uncut = [frame(view)["calls"] for _ in range(2)]
last = len(view.texts) - 1
everything = ((0, 0), (last, len(view.texts[last])))
view.select(everything)
uncut_text = view.selected_text()
view.clear_selection()
one = told(view.column(0))
uncut_width = view.width
changed = [view.set_columns(3, height=500.0), view.set_columns(3, height=500.0)]
calls.clear()
nothing_asked = list(calls)
first = frame(view)
steady = [frame(view)["calls"] for _ in range(3)]
laid_lazily = view.stats.blocks_deferred
gutter = view.columns.gutter
columns = every_column(view)
after_all = frame(view)
view.select(everything)
in_columns_text = view.selected_text()
view.clear_selection()
report["in_order"] = {
    "before": before, "uncut_first": uncut_first["calls"], "uncut": uncut, "one": one,
    "uncut_width": uncut_width,
    "changed": changed, "nothing_asked": nothing_asked, "first": first["calls"], "steady": steady,
    "deferred_after_three_frames": laid_lazily, "blocks": len(view.texts),
    "columns_property": list(view.columns), "gutter": gutter,
    "column_width": view.column_width, "width": view.width, "height": view.height,
    "item": after_all["item"], "count": view.column_count(),
    "columns": [told(c) for c in columns], "everything": list(map(list, everything)),
    "past": view.column(len(columns)).exists, "overflow": view.column(3).exists,
    "texts_equal": [uncut_text == in_columns_text,
                    uncut_text == view.separator.join(t for t in view.texts if t)],
    "vertices": [uncut_first["vertices"], first["vertices"]],
    "answered": [uncut_first["answered"], first["answered"]],
}

# 2. A range across the cut between column 0 and column 1: its text, a drag, a drag backwards.
cut = tuple(columns[0].end)
a = (cut[0] - 1, 4) if cut[1] < 12 else (cut[0], cut[1] - 12)
b = (cut[0], cut[1] + 14)
assert tuple(columns[0].start) <= a < cut < b < tuple(columns[1].end), (a, cut, b)
view.select((a, b))
across = [view.selected_text(), between(view, a, b)]
view.clear_selection()
pa, pb = on_screen(view, a), on_screen(view, b)
frame(view, mouse=pa); frame(view)
frame(view, button=True); frame(view)
dragging = [frame(view, mouse=pb), frame(view)]
frame(view, button=False)
released = frame(view)
forward = {"selection": released["selection"], "text": view.selected_text(),
           "calls": dragging[1]["calls"], "points": [list(pa), list(pb)]}
view.clear_selection()
frame(view, mouse=pb); frame(view)
frame(view, button=True); frame(view)
frame(view, mouse=pa); frame(view)
frame(view, button=False)
released = frame(view)
backward = {"selection": released["selection"], "text": view.selected_text()}
view.clear_selection()
frame(view, mouse=PARKED); frame(view)
report["across"] = {"a": list(a), "b": list(b), "cut": list(cut), "text": across,
                    "forward": forward, "backward": backward,
                    "column_of": [math.floor((p[0] - view.origin[0]) / (view.column_width + gutter))
                                  for p in (pa, pb)]}

# 3. Marks and inks across the cut; a selection kept through a change of columns.
plain = frame(view)["vertices"]
view.set_marks([((a, b), 0x80FFFF00, int(ts.MarkPlace.Behind))])
marked = frame(view)
view.set_marks(None)
ink_at = (b[0], b[1] + 1, b[1] + 9)
view.set_colours(ink_at[0], [(ink_at[1], ink_at[2], 0xFF0000FF)])
inked = [frame(view), frame(view)]
inks_drawn = 0xFF0000FF in colours(view)
view.clear_colours()
inks_gone = 0xFF0000FF in colours(view)
view.select((a, b))
kept = [view.set_columns(None), view.selection, frame(view)["calls"], view.column_count(),
        view.selected_text() == across[1], view.width]
again = [view.set_columns(2, height=400.0, gutter=0), frame(view)["calls"], view.selection,
         view.column(1).min[0] - view.column(0).max[0], view.column_width]
wide = [view.set_columns(2, height=400.0, gutter=30.0), frame(view)["calls"],
        view.column(1).min[0] - view.column(0).max[0], view.column_width]
view.clear_selection()
report["marks"] = {"plain": plain, "marked": marked["vertices"], "marked_calls": marked["calls"],
                   "inked": [one["calls"] for one in inked],
                   "inks": [inks_drawn, inks_gone], "kept": kept, "again": again,
                   "wide": wide}

# 4. Balanced.
balanced_set = view.set_columns(3, balance=True)
balanced_first = frame(view)
balanced_steady = frame(view)["calls"]
balanced = every_column(view)
view.select(everything)
report["balanced"] = {"set": balanced_set, "first": balanced_first["calls"],
                      "steady": balanced_steady,
                      "count": view.column_count(), "columns": [told(c) for c in balanced],
                      "height": view.height, "width": view.width,
                      "text_equal": view.selected_text() == uncut_text,
                      "uncut_height": one["max"][1]}
view.clear_selection()

# 5. Arguments refused at the call: the view and the library are as they were.
view.set_columns(3, height=500.0)
frame(view)
held = view.columns
refused = {}
for name, args, kwargs in (
    ("count a float", (2.0,), {"height": 300.0}),
    ("count a bool", (True,), {"height": 300.0}),
    ("count a str", ("3",), {"height": 300.0}),
    ("count zero", (0,), {"height": 300.0}),
    ("count negative", (-2,), {"height": 300.0}),
    ("count too many", (MAX_COLUMNS + 1,), {"height": 300.0}),
    ("height a str", (2,), {"height": "tall"}),
    ("height nan", (2,), {"height": math.nan}),
    ("height infinite", (2,), {"height": math.inf}),
    ("height negative", (2,), {"height": -1.0}),
    ("gutter a str", (2,), {"height": 300.0, "gutter": "wide"}),
    ("gutter negative", (2,), {"height": 300.0, "gutter": -4.0}),
    ("gutter nan", (2,), {"height": 300.0, "gutter": math.nan}),
    ("balance a number", (2,), {"balance": 1}),
    ("neither fill", (2,), {}),
    ("both fills", (2,), {"height": 300.0, "balance": True}),
    ("balance one column", (1,), {"balance": True}),
    # With no count there are no columns to fill: said, and not silently "uncut".
    ("height with no count", (), {"height": 500.0}),
    ("balance with no count", (), {"balance": True}),
    ("gutter with no count", (None,), {"gutter": 10.0}),
    # Finite in Python and not as the C float the library takes: infinity, or zero.
    ("height past a C float", (2,), {"height": 1e39}),
    ("height under a C float", (2,), {"height": 1e-46}),
    ("gutter past a C float", (2,), {"height": 300.0, "gutter": 1e39}),
    ("gutter under a C float", (2,), {"height": 300.0, "gutter": 1e-46}),
):
    try:
        view.set_columns(*args, **kwargs)
        refused[name] = "taken"
    except (TypeError, ValueError) as exc:
        refused[name] = [type(exc).__name__, str(exc).startswith("set_columns: "),
                         view.columns == held, typesetter.module() is not None]
queries = {}
for name, ask in (("column a str", lambda: view.column("1")),
                  ("column a float", lambda: view.column(1.0)),
                  ("pos a str", lambda: view.column_pos("ab")),
                  ("pos one number", lambda: view.column_pos((1.0,))),
                  ("pos nan", lambda: view.column_pos((math.nan, 0.0))),
                  ("pos none", lambda: view.column_pos(None))):
    try:
        ask()
        queries[name] = "taken"
    except TypeError:
        queries[name] = ["TypeError", typesetter.module() is not None]
still = frame(view)
report["refused"] = {"set": refused, "queries": queries, "still_draws": still["calls"],
                     "far": view.column(10**6).exists, "negative": view.column(-1).exists}
view.close()

# 6. A hosted block in a later column, and a table: the uncut answers taken to the page.
class Widget:
    text = "hosted"
    def __init__(self):
        self.drawn = []
    def height_for(self, width_px):
        self.asked = width_px
        return 60.0
    def draw(self, *, palette=None, width_px=None):
        cursor = imgui.get_cursor_screen_pos()
        self.drawn.append([cursor.x, cursor.y, width_px])

widget = Widget()
paragraph = "A paragraph of words to fill a column with, and then some more of them. " * 3
HOSTED = "\n\n".join([paragraph] * 6 + ["```\nhosted\n```"] + [paragraph] * 6) + "\n"
def host_for(view, at, block):
    return widget if isinstance(block, MarkdownCode) else None

host = TypesetView(HOSTED, theme=theme, palette=DARK_PALETTE, host_for=host_for)
at = host.hosts[0]
frame(host, name="##hosted")
uncut_draw = widget.drawn[-1]
uncut_rect = host.block_rect(at)
host.set_columns(3, height=260.0)
host_first = frame(host, name="##hosted")
host_steady = [frame(host, name="##hosted")["calls"] for _ in range(2)]
doc = host.native_document
geometry = doc.block_geometry(at)
on_page = host.column_pos((geometry.min[0], geometry.min[1]))
host_columns = every_column(host)
holder = [k for k, c in enumerate(host_columns) if tuple(c.start) <= (at, 0) < tuple(c.end)]
report["hosted"] = {
    "block": at, "uncut_draw": uncut_draw, "uncut_rect": list(uncut_rect),
    "first": host_first["calls"], "steady": host_steady, "drawn": widget.drawn[-1],
    "origin": list(host.origin), "on_page": list(on_page), "uncut": list(geometry.min),
    "holder": holder, "columns": [told(c) for c in host_columns],
    "column_width": host.column_width, "asked": widget.asked, "hosts_drawn": host.hosts_drawn,
}
# The mouse over the widget is the widget's: no hit test, as when uncut.
over_widget = [frame(host, name="##hosted", mouse=(widget.drawn[-1][0] + 20.0,
                                                    widget.drawn[-1][1] + 20.0)),
               frame(host, name="##hosted")]
report["hosted"]["over_widget"] = over_widget[1]["calls"]
frame(host, name="##hosted", mouse=PARKED)
host.close()

tables_source = (ROOT / "demo" / "tables.md").read_text(encoding="utf-8")
tabled = TypesetView(tables_source, theme=theme, palette=DARK_PALETTE)
tabled.set_columns(2, height=420.0)
frame(tabled, name="##tabled"); frame(tabled, name="##tabled")
tabled_columns = every_column(tabled)
found = []
for table in tabled.tables:
    geometry = tabled.table_geometry(table)
    row = tabled.table_row(table, 0)
    corner = tabled.column_pos((geometry.min[0], row.min))
    holder = [k for k, c in enumerate(tabled_columns)
              if tuple(c.start) <= (table, 0) < tuple(c.end)]
    found.append({"table": table, "uncut": [geometry.min[0], row.min], "page": list(corner),
                  "holder": holder,
                  "rect": [told(tabled_columns[k]) for k in holder]})
tabled.select(((0, 0), (len(tabled.texts) - 1, len(tabled.texts[-1]))))
report["tabled"] = {"tables": found, "count": len(tabled_columns),
                    "text_equal": tabled.selected_text()
                    == tabled.separator.join(t for t in tabled.texts if t),
                    "steady": frame(tabled, name="##tabled")["calls"]}
tabled.close()

# 7. A long document: three frames of three columns lay out what they show; scroll_to goes sideways.
LONG = "\n\n".join(f"Paragraph {n}. " + paragraph for n in range(400)) + "\n"
long = TypesetView(LONG, theme=theme, palette=DARK_PALETTE)
long.set_columns(3, height=500.0)
for _ in range(3):
    lazy = frame(long, name="##long", sideways=True)
lazy_stats = long.stats
long.set_colours(1, [(0, 30, 0xFF0000FF)])
inked_long = [frame(long, name="##long", sideways=True) for _ in range(2)]
inked_stats = long.stats
long.clear_colours()
long.scroll_to(60, 5)
moved = [frame(long, name="##long", sideways=True) for _ in range(6)]
caret = long.native_document.caret_rect((60, 5))
pitch = long.column_width + long.columns.gutter
long.scroll_to(0)
back = [frame(long, name="##long", sideways=True) for _ in range(6)]
report["long"] = {
    "blocks": len(long.texts), "lazy_calls": lazy["calls"],
    "deferred": [lazy_stats.blocks_deferred, inked_stats.blocks_deferred],
    "laid_out": [lazy_stats.blocks_laid_out, inked_stats.blocks_laid_out],
    "inked_calls": inked_long[1]["calls"],
    "scrolled": [one["scrolled"] for one in moved], "scroll": moved[-1]["scroll"],
    "moved_calls": [one["calls"] for one in moved],
    "caret": list(caret), "pitch": pitch, "back": back[-1]["scroll"],
}
long.close()

# 8. A stream: columns filled in order are taken, balanced ones refused at the call.
stream = MarkdownStream(theme)
stream.append(source[:1500])
streamed = TypesetStreamView(stream, palette=DARK_PALETTE, follow=False)
try:
    streamed.set_columns(2, balance=True)
    refusal = "taken"
except ValueError as exc:
    refusal = str(exc)
taken = streamed.set_columns(2, height=300.0)
stream_first = frame(streamed, name="##stream")
stream.append(source[1500:4000])
stream_more = frame(streamed, name="##stream")
stream_columns = every_column(streamed)
last = len(streamed.texts) - 1
report["stream"] = {
    "refusal": refusal, "columns_after_refusal_and_set": list(streamed.columns), "taken": taken,
    "first": stream_first["calls"], "more": stream_more["calls"],
    "ranges": [[list(c.start), list(c.end)] for c in stream_columns],
    "end": [last, len(streamed.texts[last])],
    "module": typesetter.module() is not None,
}
streamed.close()

report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def columns() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _COLUMNS, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got["reason"]
    assert got["trouble"] == "" and got["module_at_end"] is True
    return got


def _positions(pairs: Any) -> list[tuple[int, int]]:
    return [(int(block), int(offset)) for block, offset in pairs]


def test_before_a_draw_a_view_is_one_column_and_knows_nothing_of_the_page(
    columns: dict[str, Any],
) -> None:
    """
    No library document yet: `column_count` is 1, `column` is `None`,
    `column_pos` is the point given, and nothing is asked of the library.
    """
    before = columns["in_order"]["before"]
    assert before == {
        "count": 1,
        "column": None,
        "columns": None,
        "pos": [3.0, 4.0],
        "width": 0.0,
        "column_width": 0.0,
    }


def test_columns_cost_one_call_when_they_change_and_none_in_a_frame(
    columns: dict[str, Any],
) -> None:
    """
    **The budget.** `set_columns` asks the library nothing; the next draw
    tells it, once (`SetDocumentColumns`), before the layout; and from then
    on a frame of a document in columns is the same three calls as uncut,
    filled in order or balanced. Saying the same columns again is nothing.
    """
    told = columns["in_order"]
    assert told["uncut"] == [_FRAME] * 2
    assert told["changed"] == [True, False] and told["nothing_asked"] == []
    assert told["first"] == ["SetDocumentColumns", *_FRAME]
    assert told["steady"] == [_FRAME] * 3
    assert told["answered"] == [True, True] and min(told["vertices"]) > 1000
    assert columns["balanced"]["first"] == ["SetDocumentColumns", *_FRAME]
    assert columns["balanced"]["steady"] == _FRAME
    assert columns["marks"]["kept"][2] == ["SetDocumentColumns", *_FRAME]
    assert columns["tabled"]["steady"] == _FRAME


def test_the_layout_width_is_one_column_s_and_the_gutter_is_a_line(
    columns: dict[str, Any],
) -> None:
    """
    Three columns across 900 px: one is `(900 - 2 gutters) / 3` wide, the
    default gutter is a line of the paragraph style (21.6 px at the stock
    sizes), and column `k` stands at `k * (width + gutter)`. A stated gutter
    is the distance between two columns, and 0 is none.
    """
    told = columns["in_order"]
    gutter = told["gutter"]
    assert gutter == pytest.approx(21.6, abs=0.001)
    assert told["columns_property"] == [3, 500.0, gutter, False]
    width = told["column_width"]
    assert width == pytest.approx((900.0 - 2.0 * gutter) / 3.0, abs=0.001)
    for k, column in enumerate(told["columns"]):
        assert column["min"] == pytest.approx([k * (width + gutter), 0.0], abs=0.01)
        assert column["max"] == pytest.approx([k * (width + gutter) + width, 500.0], abs=0.01)
    # The third column ends where the width given to `draw` does.
    assert told["columns"][2]["max"][0] == pytest.approx(900.0, abs=0.01)
    marks = columns["marks"]
    assert marks["again"][3:] == pytest.approx([0.0, 450.0], abs=0.01)
    assert marks["wide"][2:] == pytest.approx([30.0, 435.0], abs=0.01)


def test_the_columns_hold_the_document_exactly_once(columns: dict[str, Any]) -> None:
    """
    The union of the columns' `[start, end)` is the whole document: the
    first starts at the document's start, each starts where the one before
    ended, none is empty, and the last ends at the document's end. Filled in
    order, balanced, and on a stream that grew by a chunk.
    """
    told = columns["in_order"]
    end = tuple(told["everything"][1])
    both = (("in order", told["columns"]), ("balanced", columns["balanced"]["columns"]))
    for name, found in both:
        starts = _positions(column["start"] for column in found)
        ends = _positions(column["end"] for column in found)
        assert starts[0] == (0, 0), name
        assert starts[1:] == ends[:-1], name
        assert all(start < stop for start, stop in zip(starts, ends, strict=True)), name
        assert ends[-1] == end, name
    stream = columns["stream"]
    starts = _positions(one[0] for one in stream["ranges"])
    ends = _positions(one[1] for one in stream["ranges"])
    assert starts[0] == (0, 0) and starts[1:] == ends[:-1]
    assert ends[-1] == tuple(stream["end"])


def test_columns_filled_in_order_run_past_the_count_and_the_view_claims_the_page(
    columns: dict[str, Any],
) -> None:
    """
    `count` is how many columns stand across the width; filled in order
    there are as many as the document needs (12 here), `column(count).exists`
    is the overflow, a column past the last does not exist, and the item the
    view leaves is the page: every column and gutter wide, a column tall.
    """
    told = columns["in_order"]
    found = told["columns"]
    assert told["count"] == len(found) == 12
    assert told["overflow"] is True and told["past"] is False
    assert told["uncut_width"] == 900.0
    assert told["width"] == pytest.approx(found[-1]["max"][0], abs=1.0)
    assert told["height"] == 500.0
    assert told["item"] == [told["width"], told["height"]]
    # Each column starts, in the uncut column, below where the one before did.
    tops = [column["uncut_top"] for column in found]
    assert tops[0] == 0.0 and tops == sorted(set(tops))
    refused = columns["refused"]
    assert refused["far"] is False and refused["negative"] is False


def test_the_text_of_a_range_is_what_it_was_uncut(columns: dict[str, Any]) -> None:
    """
    `range_text` is unchanged by columns: everything, copied from the
    document in twelve columns, is to the character what it was uncut, and a
    range that crosses a cut is that stretch of `texts` with nothing added.
    Balanced and with tables in it too.
    """
    assert columns["in_order"]["texts_equal"] == [True, True]
    across = columns["across"]
    assert tuple(across["a"]) < tuple(across["cut"]) < tuple(across["b"])
    assert across["text"][0] == across["text"][1] != ""
    assert columns["balanced"]["text_equal"] is True
    assert columns["tabled"]["text_equal"] is True


def test_a_drag_across_columns_selects_in_reading_order(columns: dict[str, Any]) -> None:
    """
    A press near the foot of column 0 and a release near the head of
    column 1 (up and to the right on screen) select from the first position
    to the second, through the cut; the same drag backwards selects the
    same. One `SelectDocumentRange` on a frame of the drag, as uncut.
    """
    across = columns["across"]
    wanted = [across["a"], across["b"]]
    assert across["column_of"] == [0, 1]
    (ax, ay), (bx, by) = across["forward"]["points"]
    assert bx > ax and by < ay, "the second point is in the next column, higher up"
    assert across["forward"]["selection"] == wanted
    assert across["forward"]["text"] == across["text"][1]
    assert across["forward"]["calls"] == [*_FRAME, "SelectDocumentRange"]
    assert across["backward"]["selection"] == wanted
    assert across["backward"]["text"] == across["text"][1]


def test_marks_inks_and_the_selection_stand_through_columns(columns: dict[str, Any]) -> None:
    """
    A mark behind a range that crosses a cut adds vertices; an ink laid on a
    block is among the page's vertices and costs the two hit tests it costs
    uncut; a selection is the same positions and the same text after the
    document is shown uncut again and then in two columns.
    """
    marks = columns["marks"]
    assert marks["marked"] > marks["plain"]
    assert marks["marked_calls"] == _FRAME
    assert marks["inked"] == [[_LAYOUT, "HitTestDocument", "HitTestDocument", _DRAW, _SIZE]] * 2
    assert marks["inks"] == [True, False]
    wanted = [columns["across"]["a"], columns["across"]["b"]]
    changed, selection, _calls, count, same_text, width = marks["kept"]
    assert (changed, selection, count, same_text, width) == (True, wanted, 1, True, 900.0)
    assert marks["again"][0] is True and marks["again"][2] == wanted


def test_balanced_columns_are_of_one_height_less_than_the_uncut_column(
    columns: dict[str, Any],
) -> None:
    """
    `balance=True`: exactly `count` columns, one height, the page as wide as
    the width given. **Not the reference's**: the old core never balanced.
    """
    told = columns["balanced"]
    found = told["columns"]
    assert told["set"] is True and told["count"] == len(found) == 3
    heights = {column["max"][1] for column in found}
    assert len(heights) == 1
    height = heights.pop()
    assert told["uncut_height"] / 3.0 <= height < told["uncut_height"]
    assert told["height"] == pytest.approx(height, abs=1.0)
    assert told["width"] == pytest.approx(900.0, abs=1.0)
    assert not any(column["overfull"] for column in found)


def test_a_malformed_argument_is_refused_at_the_call_and_the_library_stays_on(
    columns: dict[str, Any],
) -> None:
    """
    Each is raised by `set_columns`, `column` or `column_pos` itself, as a
    `TypeError` or a `ValueError` that names the call; the view's columns
    are what they were, the library is still in use, and the next frame is
    the three calls. None reaches the guarded part of `draw`, where the
    library's refusal would be taken for its failure and switch it off.
    """
    refused = columns["refused"]
    kinds = {name: got[0] for name, got in refused["set"].items()}
    assert kinds == {
        "count a float": "TypeError",
        "count a bool": "TypeError",
        "count a str": "TypeError",
        "count zero": "ValueError",
        "count negative": "ValueError",
        "count too many": "ValueError",
        "height a str": "TypeError",
        "height nan": "ValueError",
        "height infinite": "ValueError",
        "height negative": "ValueError",
        "gutter a str": "TypeError",
        "gutter negative": "ValueError",
        "gutter nan": "ValueError",
        "balance a number": "TypeError",
        "neither fill": "ValueError",
        "both fills": "ValueError",
        "balance one column": "ValueError",
        "height with no count": "ValueError",
        "balance with no count": "ValueError",
        "gutter with no count": "ValueError",
        "height past a C float": "ValueError",
        "height under a C float": "ValueError",
        "gutter past a C float": "ValueError",
        "gutter under a C float": "ValueError",
    }
    assert all(got[1:] == [True, True, True] for got in refused["set"].values())
    assert set(refused["queries"]) == {
        "column a str",
        "column a float",
        "pos a str",
        "pos one number",
        "pos nan",
        "pos none",
    }
    assert all(got == ["TypeError", True] for got in refused["queries"].values())
    assert refused["still_draws"] == _FRAME


def test_a_hosted_block_is_drawn_where_its_corner_is_on_the_page(columns: dict[str, Any]) -> None:
    """
    The library answers for a hosted block in the UNCUT column; the view
    takes the corner to the page with `column_pos` and hands the widget a
    rectangle one column wide, less the block's indent. Here the block is
    in the fourth column, which is not where it is uncut.

    **The budget with hosted blocks in columns**: the three calls, two
    `GetDocumentColumn` (the first and last column under the clip
    rectangle), then a `GetDocumentBlockGeometry` and a
    `GetDocumentColumnPos` for each hosted block those columns hold. The
    mouse over the widget is the widget's: no hit test.
    """
    told = columns["hosted"]
    frame = [
        *_FRAME,
        "GetDocumentColumn",
        "GetDocumentColumn",
        "GetDocumentBlockGeometry",
        "GetDocumentColumnPos",
    ]
    assert told["first"] == ["SetDocumentColumns", *frame]
    assert told["steady"] == [frame] * 2 and told["over_widget"] == frame
    assert told["hosts_drawn"] == 1
    ox, oy = told["origin"]
    px, py = told["on_page"]
    x, y, width = told["drawn"]
    assert (x, y) == pytest.approx((ox + px, oy + py), abs=0.01)
    assert told["holder"] == [3]
    column = told["columns"][3]
    indent = told["uncut"][0]
    assert px == pytest.approx(column["min"][0] + indent, abs=0.01)
    assert 0.0 <= py and py + 60.0 <= column["max"][1]
    assert width == pytest.approx(told["column_width"] - indent, abs=0.01)
    assert told["asked"] == pytest.approx(width, abs=0.01)
    # Uncut it was drawn where `block_rect` says, further down and at the left.
    assert told["uncut_draw"][:2] == pytest.approx(told["uncut_rect"][:2], abs=0.01)
    assert told["uncut_draw"][0] < x and told["uncut_draw"][1] > y


def test_a_table_s_uncut_corner_is_taken_into_the_column_that_holds_it(
    columns: dict[str, Any],
) -> None:
    """
    `table_geometry` and `table_row` go on answering for the uncut column;
    `column_pos` of a table's first row's corner is inside the rectangle of
    the column whose range holds the table's first position.
    """
    told = columns["tabled"]
    assert [one["table"] for one in told["tables"]] == [4, 7, 10, 13, 16]
    assert told["count"] > 2
    moved = 0
    for one in told["tables"]:
        assert len(one["holder"]) == 1, one["table"]
        rect = one["rect"][0]
        x, y = one["page"]
        assert rect["min"][0] - 0.01 <= x < rect["max"][0], one["table"]
        assert rect["min"][1] - 0.01 <= y < rect["max"][1], one["table"]
        assert y == pytest.approx(
            one["uncut"][1] - rect["uncut_top"] + rect["content_min"][1], abs=0.01
        )
        moved += one["holder"][0] > 0
    assert moved >= 3


def test_columns_filled_in_order_lay_out_what_is_shown_and_scroll_to_goes_sideways(
    columns: dict[str, Any],
) -> None:
    """
    400 paragraphs in columns 500 px tall: three frames lay out the blocks
    of the columns under the clip rectangle and no more, with inks set too
    (their two hit tests are made inside the clip rectangle: one at the
    page's far edge would cut every column). `scroll_to` a position in a
    late column moves the pane SIDEWAYS, to that column's left edge, and
    back: one caret rectangle a look, and nothing else.

    Until the library was 7a7bc36 the view asked `GetDocumentColumnCount`
    before the caret, the other team's remedy for a caret asked for before
    its column was cut, and this test held that call in the budget. They
    fixed the defect in that commit; measured here on 2026-10-11
    (`.concerns/T5-B1-scripts/probe_caret_columns.py`: three carets in
    `demo/columns.md`, in a document drawn once and in one only laid out,
    the same rectangle with and without the call), and the call is gone.
    """
    told = columns["long"]
    assert told["blocks"] == 400
    assert told["lazy_calls"] == _FRAME
    assert 0 < told["laid_out"][0] < 40 and told["deferred"][0] > 360
    assert told["laid_out"][1] == told["laid_out"][0]
    assert told["inked_calls"] == [_LAYOUT, "HitTestDocument", "HitTestDocument", _DRAW, _SIZE]
    assert told["scrolled"][0] is True and told["scrolled"][-1] is False
    assert told["moved_calls"][0] == [_LAYOUT, "GetDocumentCaretRect", _DRAW, _SIZE]
    assert told["moved_calls"][-1] == _FRAME
    column = math.floor(told["caret"][0] / told["pitch"])
    assert column > 4
    assert told["scroll"][0] == pytest.approx(column * told["pitch"], abs=1.0)
    assert told["scroll"][1] == 0.0
    assert told["back"] == [0.0, 0.0]


def test_a_stream_view_takes_columns_in_order_and_refuses_to_balance(
    columns: dict[str, Any],
) -> None:
    """
    `TypesetStreamView.set_columns(balance=True)` is a `ValueError` that
    says why (every edit would search for the height again over every
    block), raised at the call with the library left on. Columns filled in
    order are taken, and a chunk arriving is still one edit and three calls.
    """
    told = columns["stream"]
    assert "does not balance" in told["refusal"] and "height=" in told["refusal"]
    assert told["taken"] is True and told["module"] is True
    assert told["columns_after_refusal_and_set"][:2] == [2, 300.0]
    assert told["columns_after_refusal_and_set"][3] is False
    assert "SetDocumentColumns" in told["first"] and told["first"][-3:] == _FRAME
    assert told["more"] == ["ReplaceDocumentBlocks", *_FRAME]

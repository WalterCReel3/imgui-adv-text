r"""
A view out of sight rests (pptmstr's P30): `imscribe.ui.typeset_view.TypesetView.draw`.

A log is a view for each markdown run, four hundred of them in one scrolling
child and thirty in sight. Until 2026-10-12 every one made its three library
calls a frame. Now a view whose rectangle is wholly outside the clip
rectangle claims the rectangle its last draw measured and calls nothing.

One child process, **with the library** (skipped without `IMTYPESET_LIBRARY`),
real ImGui frames and no window; the library's calls are counted by standing
in front of its ctypes object, as `tests/test_typeset_view.py` does. What is
held:

1.  the calls of a frame for a view out of sight (none), for one half in
    sight and one wholly in sight (the three there always were), and for a
    view never drawn before (the three, once: what it claims is the
    library's own size);
2.  the rectangle a resting view claims: the library's, to the pixel;
3.  everything that must still work for a view out of sight, each by name:
    a document that changed, a width that changed, each `set_...`, a
    `scroll_to`, a selection and its keys, a drag that began in sight, marks
    and inks, hosted blocks, columns, a question a host asked, and the
    library gone;
4.  a stream view: nothing arriving, text arriving, its tail followed;
5.  four hundred views in one child: the calls of a frame are three for
    each view in sight and none for the rest, at every scroll position.

`TypesetDiffView` is not changed and not tested here: its height is rows
times a pitch and was never asked of the library
(`.concerns/O-HOST3--builder--result.md` has what it costs out of sight).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]
_OPTIONS = ["SetDocumentOptions"]
_MADE = ["GetCurrentContext", "CreateDocument", "SetDocumentBlocks", *_OPTIONS]
"""A view's first draw, and its first after `close`: the library's document is made."""

_CHILD = r"""
import json, sys

from imgui_bundle import imgui

from imscribe import typesetter
from imscribe.theme import BlockKind, Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView

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

real = ts._lib
ts._lib = Counting(real)
theme = Theme.build()
FAR = 3000.0          # a spacer this tall puts what follows below the pane
FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]
PANE = 700.0
TEXT = (
    "A first paragraph with a [link](http://example.org/x) and enough words to take a "
    "second line at the width of this pane, which is nine hundred pixels less its padding.\n\n"
    "- an item\n- another\n\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
    "```\ncode of one line\n```\n"
)

def size_of(view):
    # The library's own answer, asked around the counter and around the view.
    doc = view._doc
    ts._lib = real
    try:
        return [float(value) for value in doc.size()]
    finally:
        ts._lib = Counting(real)

BAR = imgui.WindowFlags_.always_vertical_scrollbar.value   # so the width never changes

def frame(views, name, *, spacer=0.0, scroll=None, after=0.0, width=None, mouse=None,
          button=None, keys=(), reader=None):
    # One frame: a spacer, then each view in turn, then another spacer, in one child.
    # `scroll` is asked for inside the frame, as a host's code would (it takes effect on
    # the next); `reader` is where the pane already is when the frame begins, as after
    # a wheel.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    for key, down in keys:
        io.add_key_event(key, down)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(900.0, PANE))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        if reader is not None:
            imgui.set_next_window_scroll(imgui.ImVec2(0.0, reader))
        imgui.begin_child(name, imgui.ImVec2(0.0, 0.0), 0, BAR)
        try:
            if scroll is not None:
                imgui.set_scroll_y(scroll)
            native = imgui.get_window_draw_list()
            low, high = native.get_clip_rect_min(), native.get_clip_rect_max()
            if spacer:
                imgui.dummy(imgui.ImVec2(10.0, spacer))
            rows = []
            for view in views:
                calls.clear()
                vertices = native.vtx_buffer.size()
                answered = view.draw(width_px=width)
                made = list(calls)
                item_min, item = imgui.get_item_rect_min(), imgui.get_item_rect_size()
                rows.append({
                    "calls": made, "answered": answered,
                    "vertices": native.vtx_buffer.size() - vertices,
                    "item": [item.x, item.y], "item_top": item_min.y,
                    "height": view.height, "width": view.width, "origin": list(view.origin),
                    "in_sight": not (view.origin[1] >= high.y
                                     or view.origin[1] + view.height <= low.y),
                    "hit": view.under_mouse is not None, "hovered": view.hovered_link,
                    "scrolled": view.scrolled, "selection": view.selection,
                    "size": size_of(view),
                })
            if after:
                imgui.dummy(imgui.ImVec2(10.0, after))
            calls.clear()
            return {"rows": rows, "scroll": imgui.get_scroll_y(),
                    "scroll_max": imgui.get_scroll_max_y(), "clip": [low.y, high.y]}
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()

def one(view, name, **more):
    got = frame([view], name, **more)
    return {**got["rows"][0], "scroll": got["scroll"], "scroll_max": got["scroll_max"]}

# ---- 1, 2: out of sight, half in sight, in sight, never seen -------------------------------
view = TypesetView(TEXT, theme=theme)
below = [one(view, "##below", spacer=FAR) for _ in range(4)]
half = [one(view, "##half", spacer=PANE - 60.0) for _ in range(3)]
whole = [one(view, "##whole") for _ in range(3)]
again = [one(view, "##below", spacer=FAR) for _ in range(3)]
above = [one(view, "##above", after=FAR, scroll=2000.0) for _ in range(4)]
report["sight"] = {"below": below, "half": half, "whole": whole, "again": again, "above": above}
empty = TypesetView("", theme=theme)
report["empty"] = {
    "below": [one(empty, "##empty", spacer=FAR) for _ in range(3)],
    "in_sight": [one(empty, "##empty2", spacer=100.0) for _ in range(3)],
}
# Touching the pane's lower edge exactly: no pixel of it is inside.
edge = TypesetView("Touching.", theme=theme)
start = one(edge, "##edge")
clip_bottom = frame([edge], "##edge")["clip"][1]
# A spacer this tall, and the item spacing after it, put the view's top on the clip's edge.
gap = clip_bottom - start["origin"][1] - imgui.get_style().item_spacing.y
report["edge"] = {
    "touching": [one(edge, "##edge", spacer=gap) for _ in range(3)],
    "one_pixel_in": [one(edge, "##edge", spacer=gap - 1.0) for _ in range(3)],
    "clip_bottom": clip_bottom,
}

# ---- 3: what must still work out of sight ----------------------------------------------------
def woken(name, change, *, settle=3, **more):
    # A view at rest below the pane; `change`; then the frames after it.
    view = TypesetView(TEXT, theme=theme, **more)
    child = "##wake-" + name
    before = [one(view, child, spacer=FAR) for _ in range(3)]
    calls.clear()
    said = change(view)
    at_change = list(calls)
    frames = [one(view, child, spacer=FAR) for _ in range(settle)]
    return {"before": before[-1], "at_change": at_change, "frames": frames,
            "said": said if isinstance(said, (bool, int, float, str, type(None))) else str(said)}

wakes = {}
wakes["set_document"] = woken("doc", lambda v: v.set_document(TEXT + "\nOne more paragraph.\n"))
wakes["set_document_same"] = woken("same", lambda v: v.set_document(TEXT))
wakes["set_palette"] = woken("palette", lambda v: v.set_palette(DARK_PALETTE))
wakes["set_palette_roles"] = woken(
    "roles", lambda v: v.set_palette(DARK_PALETTE.with_roles({BlockKind.PARAGRAPH: 0xFF00FFFF})))
wakes["set_theme"] = woken("theme", lambda v: v.set_theme(Theme.build(22.0)))
wakes["set_code_overflow"] = woken("overflow", lambda v: v.set_code_overflow("grow"))
wakes["set_fixed_line_height"] = woken("fixed", lambda v: v.set_fixed_line_height(True))
wakes["set_table_widths"] = woken("widths", lambda v: v.set_table_widths("natural"))
wakes["set_table_columns"] = woken(
    "columns", lambda v: v.set_table_columns(v.tables[0], [120.0, 200.0]))
wakes["set_columns"] = woken("cut", lambda v: v.set_columns(2, height=120.0))
wakes["close"] = woken("close", lambda v: v.close())
wakes["layout_for"] = woken("layout", lambda v: v.layout_for(400.0))
wakes["block_rect"] = woken("rect", lambda v: v.block_rect(0))
wakes["span_rects"] = woken("spans", lambda v: len(v.span_rects(0, 0, 5)))
wakes["set_lines"] = woken("lines", lambda v: len(v.set_lines()))
wakes["native_document"] = woken("native", lambda v: v.native_document is not None)
# These change nothing a view out of sight would show, and wake nothing.
wakes["stats"] = woken("stats", lambda v: v.stats.blocks)
wakes["set_marks"] = woken(
    "marks", lambda v: v.set_marks([ts.Mark(((0, 0), (0, 5)), 0x8000FFFF, ts.MarkPlace.Behind)]))
wakes["set_colours"] = woken("inks", lambda v: v.set_colours(0, [(0, 5, 0xFF0000FF)]))
wakes["select"] = woken("select", lambda v: v.select(((0, 0), (0, 7))))
wakes["debug"] = woken("debug", lambda v: setattr(v, "debug", True))
report["wakes"] = wakes

# The width: one draw at the new width, then at rest at it.
view = TypesetView(TEXT, theme=theme)
narrow = [one(view, "##width", spacer=FAR) for _ in range(3)]
narrow += [one(view, "##width", spacer=FAR, width=300.0) for _ in range(3)]
narrow += [one(view, "##width", spacer=FAR) for _ in range(3)]
report["width"] = narrow

# A palette given out of sight is the one the view is drawn in when it comes into sight.
view = TypesetView(TEXT, theme=theme)
for _ in range(3):
    one(view, "##ink", spacer=FAR)
view.set_palette(DARK_PALETTE)
report["palette"] = {"hidden": one(view, "##ink", spacer=FAR)["calls"],
                     "shown": one(view, "##ink2")["calls"]}

# Marks and inks set while out of sight are drawn when the view comes into sight.
plain = TypesetView(TEXT, theme=theme)
marked = TypesetView(TEXT, theme=theme)
for _ in range(3):
    frame([plain, marked], "##marked", spacer=FAR)
marked.set_marks([ts.Mark(((0, 0), (0, 20)), 0x8000FFFF, ts.MarkPlace.Behind)])
hidden = frame([plain, marked], "##marked", spacer=FAR)["rows"]
shown = frame([plain, marked], "##marked2")["rows"]
report["marks"] = {"hidden": [row["calls"] for row in hidden],
                   "vertices": [row["vertices"] for row in shown]}

# scroll_to: the request is carried out, and the view comes into sight.
view = TypesetView(TEXT, theme=theme)
for _ in range(3):
    one(view, "##scroll", spacer=FAR, after=FAR)
view.scroll_to(2)
report["scroll_to"] = [one(view, "##scroll", spacer=FAR, after=FAR) for _ in range(8)]

# A selection out of sight: its keys still work, and it is given up to another view's.
front = TypesetView("The view in sight.", theme=theme)
back = TypesetView("Scrolled away, and selected.", theme=theme)
def two_apart(**more):
    # `front` at the top, `back` below the pane.
    io = imgui.get_io()
    for key, down in more.pop("keys", ()):
        io.add_key_event(key, down)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(900.0, PANE))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##keys", imgui.ImVec2(0.0, 0.0), 0, BAR)
        try:
            calls.clear()
            front.draw()
            first = list(calls)
            imgui.dummy(imgui.ImVec2(10.0, FAR))
            calls.clear()
            back.draw()
            second = list(calls)
            calls.clear()
            return [first, second]
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()
for _ in range(3):
    two_apart()
back.select_all()
keys = {"owning": [two_apart() for _ in range(2)]}
imgui.set_clipboard_text("")
keys["copy"] = two_apart(keys=[(imgui.Key.mod_ctrl, True), (imgui.Key.c, True)])
keys["clipboard"] = imgui.get_clipboard_text()
two_apart(keys=[(imgui.Key.c, False), (imgui.Key.mod_ctrl, False)])
keys["selection_kept"] = back.selection is not None and back.owns_selection
front.select(((0, 0), (0, 3)))
keys["after_other"] = two_apart()
keys["given_up"] = [back.selection, back.owns_selection, front.owns_selection]
report["keys"] = keys

# A drag that began in sight goes on when the text is scrolled out of sight.
view = TypesetView(TEXT, theme=theme)
drag = []
start = one(view, "##drag", after=FAR, mouse=(880.0, 690.0))
ox, oy = start["origin"]
point = (ox + 40.0, oy + 30.0)
drag.append(one(view, "##drag", after=FAR, mouse=point))
drag.append(one(view, "##drag", after=FAR, button=True))
drag.append(one(view, "##drag", after=FAR, mouse=(point[0] + 60.0, point[1])))
for _ in range(3):
    drag.append(one(view, "##drag", after=FAR, scroll=1500.0))
drag.append(one(view, "##drag", after=FAR, scroll=1500.0, button=False))
for _ in range(3):
    drag.append(one(view, "##drag", after=FAR, scroll=1500.0))
report["drag"] = drag
one(view, "##drag", after=FAR, mouse=(5000.0, 5000.0))   # parked, for everything after

# Hosted blocks: a view that holds one never rests (its widget's height and keys are asked).
class Box:
    def __init__(self):
        self.text = "BOX"
        self.keys = 0
        self.asked = 0
    def height_for(self, width_px):
        self.asked += 1
        return 80.0
    def draw(self, *, palette=None, width_px=None):
        imgui.dummy(imgui.ImVec2(width_px, 80.0))
    def handle_keys(self):
        self.keys += 1
box = Box()
def host_for(view, number, block):
    return box if getattr(block, "text", "").startswith("code") else None
hosting = TypesetView(TEXT, theme=theme, host_for=host_for)
hosted = [one(hosting, "##hosted", spacer=FAR) for _ in range(5)]
report["hosted"] = {"frames": hosted, "hosts": list(hosting.hosts), "keys": box.keys,
                    "asked": box.asked}

# Columns: the page is what rests.
cut = TypesetView(TEXT + "\n" + TEXT, theme=theme)
cut.set_columns(2, height=120.0)
report["columns"] = {
    "below": [one(cut, "##cut", spacer=FAR) for _ in range(4)],
    "in_sight": [one(cut, "##cut2") for _ in range(2)],
    "columns": cut.column_count(),
}

# ---- 4: a stream view ------------------------------------------------------------------------
stream = MarkdownStream(theme)
stream.append("# A reply\n\nSome text that has arrived.\n")
quiet = TypesetStreamView(stream, follow=False)
streamed = {"quiet": [one(quiet, "##stream", spacer=FAR) for _ in range(4)]}
stream.append("\nAnd a second paragraph, ")
streamed["arrived"] = [one(quiet, "##stream", spacer=FAR) for _ in range(3)]
stream.append("which goes on.")
streamed["appended"] = [one(quiet, "##stream", spacer=FAR) for _ in range(3)]
streamed["edits"] = dict(quiet.edits)
report["stream"] = streamed

tail = MarkdownStream(theme)
tail.append("# Following\n\nThe end of this is kept in sight.\n")
follower = TypesetStreamView(tail)
followed = {"start": [one(follower, "##follow", spacer=FAR) for _ in range(4)]}
followed["following"] = follower.following
# The reader scrolls to the top: the view is out of sight and no longer following.
followed["away"] = [one(follower, "##follow", spacer=FAR, reader=0.0) for _ in range(4)]
followed["following_away"] = follower.following
tail.append("\nMore arrives while the reader is elsewhere.\n")
followed["arrived"] = [one(follower, "##follow", spacer=FAR) for _ in range(3)]
follower.follow_tail()
followed["called_back"] = [one(follower, "##follow", spacer=FAR) for _ in range(4)]
followed["following_again"] = follower.following
report["follow"] = followed

# ---- 5: four hundred views in one child ----------------------------------------------------
RUNS = [
    "A model said **this** and then `that`, over a line or two of ordinary prose.",
    "Reasoning: first the *premise*, then what follows.\n\n- one\n- two\n",
    "Short.",
    "A longer run with a [link](http://example.org/x) and some more words so that it takes "
    "three lines at the width of the pane, which is about nine hundred pixels in this test, "
    "and then a few more words to be sure that it does.",
]
log = [TypesetView(RUNS[n % len(RUNS)] + f" ({n})", theme=theme) for n in range(400)]
scene = {"frames": []}
position = None
for step in range(40):
    got = frame(log, "##log", scroll=position)
    rows = got["rows"]
    scene["frames"].append({
        "calls": sum(len(row["calls"]) for row in rows),
        "in_sight": sum(row["in_sight"] for row in rows),
        "wrong": [n for n, row in enumerate(rows)
                  if row["calls"] != (FRAME if row["in_sight"] else [])],
        "claimed": sum(row["item"][1] for row in rows),
        "sizes": sum(row["size"][1] for row in rows),
        "scroll": got["scroll"], "scroll_max": got["scroll_max"],
    })
    if step >= 4:
        # Down the log in strides, to its end, and back to the top.
        strides = [0.0, 333.0, 1200.0, 5000.0, 9000.0, 1e9, 12000.0, 7001.0, 450.0, 0.0]
        position = min(strides[(step - 4) % len(strides)], got["scroll_max"])
report["scene"] = scene

# ---- the library gone: a view out of sight says so as one in sight does ---------------------
view = TypesetView(TEXT, theme=theme)
for _ in range(3):
    one(view, "##gone", spacer=FAR)
report["module_at_end"] = typesetter.module() is not None
report["ready_at_end"] = typesetter.ready()
report["trouble"] = typesetter.trouble()
typesetter.unload()
try:
    one(view, "##gone", spacer=FAR)
    report["gone"] = "drew"
except TypesetUnavailable as exc:
    report["gone"] = "TypesetUnavailable"
report["load_end"] = ["%.2f" % x for x in __import__("os").getloadavg()]
print("REPORT " + json.dumps(report))
"""


def _report_of(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    return report


@pytest.fixture(scope="module")
def drawn() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, str(_ROOT)],
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
    assert got["trouble"] == "" and got["module_at_end"] is True and got["ready_at_end"] is True
    return got


def _calls(frames: list[dict[str, Any]]) -> list[list[str]]:
    return [frame["calls"] for frame in frames]


# ---------------------------------------------------------------------------
# 1. The calls of a frame
# ---------------------------------------------------------------------------


def test_a_view_out_of_sight_makes_no_call_after_its_first_draw(drawn: dict[str, Any]) -> None:
    """
    Never drawn before, a view makes the three calls once wherever it is:
    what it claims from then on is the library's own size, an estimate and
    all, and not a guess of this module's. Then nothing.
    """
    sight = drawn["sight"]
    first = sight["below"][0]["calls"]
    # The library's document is made at the first draw, as ever, and then the three.
    assert first == [*_MADE, *_FRAME]
    assert _calls(sight["below"][1:]) == [[], [], []]
    assert [frame["in_sight"] for frame in sight["below"]] == [False] * 4
    assert [frame["vertices"] for frame in sight["below"]] == [0] * 4
    # Above the pane as below it, and again after it has been in sight.
    assert _calls(sight["again"]) == [[], [], []]
    assert _calls(sight["above"])[1:] == [[], [], []]
    assert [frame["in_sight"] for frame in sight["above"]] == [True, False, False, False]


def test_a_view_half_in_sight_or_wholly_in_sight_is_drawn_as_it_always_was(
    drawn: dict[str, Any],
) -> None:
    sight = drawn["sight"]
    for name in ("half", "whole"):
        assert _calls(sight[name]) == [_FRAME] * 3, name
        assert all(frame["in_sight"] and frame["vertices"] > 0 for frame in sight[name]), name
    # Half in sight draws fewer vertices than all of it: the library culls, as before.
    assert sight["half"][-1]["vertices"] < sight["whole"][-1]["vertices"]


def test_touching_the_clip_rectangle_is_out_of_sight_and_one_pixel_inside_is_not(
    drawn: dict[str, Any],
) -> None:
    edge = drawn["edge"]
    assert all(frame["origin"][1] == edge["clip_bottom"] for frame in edge["touching"])
    assert _calls(edge["touching"]) == [[], [], []]
    assert all(frame["origin"][1] == edge["clip_bottom"] - 1.0 for frame in edge["one_pixel_in"])
    assert _calls(edge["one_pixel_in"]) == [_FRAME] * 3


def test_an_empty_view_rests_out_of_sight_and_is_drawn_in_it(drawn: dict[str, Any]) -> None:
    """
    A rectangle of no height inside the clip rectangle is in sight by the
    rule (it is on neither side of it), so nothing special is said for it.
    """
    assert _calls(drawn["empty"]["below"]) == [[*_MADE, *_FRAME], [], []]
    assert _calls(drawn["empty"]["in_sight"]) == [_FRAME] * 3
    assert drawn["empty"]["in_sight"][-1]["item"][1] == 0.0


# ---------------------------------------------------------------------------
# 2. What a resting view claims
# ---------------------------------------------------------------------------


def test_a_resting_view_claims_the_rectangle_the_library_measured(drawn: dict[str, Any]) -> None:
    """
    The item ImGui is left with is the view's rectangle, as it is in sight:
    the scroll range is made of these. The height is the library's `size()`
    to the pixel, and for this document (short, every block laid out by its
    first draw) the same out of sight as in it.
    """
    sight = drawn["sight"]
    in_sight = sight["whole"][-1]
    assert in_sight["item"][1] == in_sight["size"][1] == in_sight["height"] > 100.0
    for name in ("below", "again", "above"):
        for frame in sight[name]:
            assert frame["item"] == [frame["width"], frame["height"]], name
            assert frame["item"][1] == frame["size"][1] == in_sight["item"][1], name
            # The answer is the last draw's, and the item is where the view is.
            assert frame["answered"] is True and frame["item_top"] == pytest.approx(
                frame["origin"][1], abs=0.5
            )
            assert frame["hit"] is False and frame["hovered"] is None


# ---------------------------------------------------------------------------
# 3. What must still work out of sight
# ---------------------------------------------------------------------------

_WAKING = [
    "set_document",
    "set_palette_roles",
    "set_theme",
    "set_code_overflow",
    "set_fixed_line_height",
    "set_table_widths",
    "set_table_columns",
    "set_columns",
    "close",
    "layout_for",
    "block_rect",
    "span_rects",
    "set_lines",
    "native_document",
]
_NOT_WAKING = [
    "set_document_same",
    "set_palette",
    "stats",
    "set_marks",
    "set_colours",
    "select",
    "debug",
]


def test_every_change_and_every_question_is_named_here(drawn: dict[str, Any]) -> None:
    assert sorted(drawn["wakes"]) == sorted(_WAKING + _NOT_WAKING)


@pytest.mark.parametrize("name", _WAKING)
def test_a_change_out_of_sight_is_one_draw_and_then_rest_again(
    drawn: dict[str, Any], name: str
) -> None:
    """
    Each of these may move the document's height, or lets a host move it
    (`native_document`). The draw after it reaches the library, the item it
    leaves is the library's new size, and the draw after that rests on it.
    """
    wake = drawn["wakes"][name]
    assert wake["before"]["calls"] == [], name
    first, second, third = wake["frames"]
    # The three, in their order, among whatever else the change costs.
    assert [call for call in first["calls"] if call in _FRAME] == _FRAME, (name, first["calls"])
    assert second["calls"] == third["calls"] == [], (name, second["calls"])
    for frame in wake["frames"]:
        assert frame["in_sight"] is False
        assert frame["item"][1] == frame["size"][1] == frame["height"], name


def test_the_changes_that_move_the_height_are_seen_to_move_it(drawn: dict[str, Any]) -> None:
    """
    So that the test above is not passing on changes that changed nothing:
    the claimed height after each of these is another height.
    """
    wakes = drawn["wakes"]
    for name in ("set_document", "set_theme", "set_columns"):
        wake = wakes[name]
        assert wake["frames"][-1]["item"][1] != wake["before"]["item"][1], name
    assert wakes["set_document"]["said"] is True and wakes["set_theme"]["said"] is True


@pytest.mark.parametrize("name", _NOT_WAKING)
def test_what_changes_nothing_out_of_sight_wakes_nothing(drawn: dict[str, Any], name: str) -> None:
    """
    The same document again; the library's counters; a palette's inks, marks,
    a host's inks and a selection, which are drawn and lay out nothing (the
    palette is told to the library by the next draw that reaches it); the
    debug overlay.
    """
    wake = drawn["wakes"][name]
    assert wake["before"]["calls"] == []
    assert _calls(wake["frames"]) == [[], [], []], name
    assert wake["frames"][-1]["item"] == wake["before"]["item"]


def test_reading_stats_is_one_call_and_not_a_draw(drawn: dict[str, Any]) -> None:
    assert drawn["wakes"]["stats"]["at_change"] == ["GetDocumentStats"]
    assert drawn["wakes"]["stats"]["said"] >= 4


def test_a_palette_given_out_of_sight_is_told_when_the_view_comes_into_sight(
    drawn: dict[str, Any],
) -> None:
    assert drawn["palette"] == {"hidden": [], "shown": [*_OPTIONS, *_FRAME]}


def test_another_width_is_one_draw_at_it_and_then_rest(drawn: dict[str, Any]) -> None:
    frames = drawn["width"]
    assert _calls(frames) == [[*_MADE, *_FRAME], [], [], _FRAME, [], [], _FRAME, [], []]
    assert frames[3]["item"][0] == 300.0 and frames[3]["item"][1] > frames[2]["item"][1]
    assert frames[8]["item"] == frames[2]["item"]


def test_marks_set_out_of_sight_are_drawn_when_the_view_comes_into_sight(
    drawn: dict[str, Any],
) -> None:
    marks = drawn["marks"]
    assert marks["hidden"] == [[], []]
    plain, marked = marks["vertices"]
    assert plain > 0 and marked > plain


def test_a_scroll_to_into_a_view_out_of_sight_is_carried_out(drawn: dict[str, Any]) -> None:
    frames = drawn["scroll_to"]
    assert "GetDocumentBlockGeometry" in frames[0]["calls"] and frames[0]["scrolled"] is True
    assert frames[0]["in_sight"] is False
    # ImGui applies the scroll on the frame after, and the view is then in sight.
    assert all(frame["in_sight"] for frame in frames[1:])
    assert frames[-1]["scroll"] > 2000.0
    assert frames[-1]["calls"] == _FRAME


def test_the_keys_of_a_selection_scrolled_away_still_work(drawn: dict[str, Any]) -> None:
    """
    pptmstr's seam special-cased this: a view that owns the selection is
    still copied by Ctrl+C when it is out of sight, in one call, and rests
    otherwise. When another view takes the selection it is given up there.
    """
    keys = drawn["keys"]
    assert keys["owning"] == [[_FRAME, []], [_FRAME, []]]
    assert keys["copy"] == [_FRAME, ["AppendDocumentRangeText"]]
    assert keys["clipboard"] == "Scrolled away, and selected."
    assert keys["selection_kept"] is True
    assert keys["after_other"][1] == []
    assert keys["given_up"] == [None, False, True]


def test_a_drag_that_began_in_sight_goes_on_out_of_sight(drawn: dict[str, Any]) -> None:
    drag = drawn["drag"]
    assert "SelectDocumentRange" in drag[1]["calls"], drag[1]["calls"]
    # Scrolled away with the button down: still drawn, still asked where the mouse is.
    for frame in drag[4:6]:
        assert frame["in_sight"] is False
        assert frame["calls"] == [*_FRAME, "SelectDocumentRange"], frame["calls"]
    # Released: the view rests from the frame after.
    assert _calls(drag[-2:]) == [[], []]
    assert drag[-1]["selection"] is not None


def test_a_view_that_hosts_a_widget_never_rests(drawn: dict[str, Any]) -> None:
    """
    Its widget's height is the host's to change at any frame and its keys
    are the widget's own: both are asked at every draw, as they were.
    """
    hosted = drawn["hosted"]
    assert len(hosted["hosts"]) == 1
    for frame in hosted["frames"]:
        assert frame["in_sight"] is False
        assert [call for call in frame["calls"] if call in _FRAME] == _FRAME
    assert hosted["keys"] == 5 and hosted["asked"] >= 5


def test_a_page_of_columns_rests_as_one_rectangle(drawn: dict[str, Any]) -> None:
    columns = drawn["columns"]
    assert columns["columns"] >= 2
    below = columns["below"]
    assert below[0]["calls"] == [*_MADE, "SetDocumentColumns", *_FRAME]
    assert _calls(below[1:]) == [[], [], []]
    for frame in below[1:]:
        assert frame["item"] == [frame["width"], frame["height"]] == frame["size"]
    assert _calls(columns["in_sight"]) == [_FRAME, _FRAME]
    assert columns["in_sight"][-1]["item"] == below[-1]["item"]


def test_a_view_out_of_sight_says_the_library_is_gone_as_one_in_sight_does(
    drawn: dict[str, Any],
) -> None:
    assert drawn["gone"] == "TypesetUnavailable"


# ---------------------------------------------------------------------------
# 4. A stream view
# ---------------------------------------------------------------------------


def test_a_stream_view_out_of_sight_with_nothing_arriving_makes_no_call(
    drawn: dict[str, Any],
) -> None:
    assert _calls(drawn["stream"]["quiet"]) == [[*_MADE, *_FRAME], [], [], []]


def test_text_arriving_out_of_sight_is_one_edit_and_one_draw(drawn: dict[str, Any]) -> None:
    stream = drawn["stream"]
    arrived, appended = stream["arrived"], stream["appended"]
    assert arrived[0]["calls"] == ["ReplaceDocumentBlocks", *_FRAME]
    assert appended[0]["calls"] == ["AppendDocumentText", *_FRAME]
    assert _calls(arrived[1:]) == _calls(appended[1:]) == [[], []]
    assert arrived[0]["item"][1] > stream["quiet"][-1]["item"][1]
    for frame in arrived + appended:
        assert frame["in_sight"] is False and frame["item"][1] == frame["size"][1]
    assert stream["edits"] == {"set": 1, "replace": 1, "append": 1}


def test_a_stream_view_follows_its_tail_and_rests_when_the_reader_leaves(
    drawn: dict[str, Any],
) -> None:
    """
    Following keeps the end in sight, so a view that follows is drawn. A
    reader who scrolls away leaves it out of sight and at rest; text that
    arrives then is one draw and moves nothing; `follow_tail` brings the end
    back.
    """
    follow = drawn["follow"]
    assert follow["following"] is True and follow["start"][-1]["in_sight"] is True
    assert follow["start"][-1]["calls"] == _FRAME
    assert follow["start"][-1]["scroll"] == follow["start"][-1]["scroll_max"] > 0.0
    away = follow["away"]
    assert follow["following_away"] is False
    assert _calls(away[-2:]) == [[], []] and away[-1]["scroll"] == 0.0
    arrived = follow["arrived"]
    assert arrived[0]["calls"][-3:] == _FRAME and _calls(arrived[1:]) == [[], []]
    assert arrived[-1]["scroll"] == 0.0 and arrived[-1]["in_sight"] is False
    back = follow["called_back"]
    assert follow["following_again"] is True
    assert back[-1]["in_sight"] is True and back[-1]["calls"] == _FRAME
    assert back[-1]["scroll"] == back[-1]["scroll_max"] > 0.0


# ---------------------------------------------------------------------------
# 5. Four hundred views in one child
# ---------------------------------------------------------------------------


def test_four_hundred_views_cost_three_calls_for_each_one_in_sight(drawn: dict[str, Any]) -> None:
    """
    The first frame makes and draws every view (2,800 calls: none has a size yet).
    From then on, at rest and at every stride down the log and back, a frame
    is three calls for each view in sight and none for any other, and what
    the views claim is what the library says they measure.
    """
    frames = drawn["scene"]["frames"]
    assert frames[0]["calls"] == 400 * len([*_MADE, *_FRAME]) == 2800
    seen = set()
    for number, frame in enumerate(frames[1:], start=1):
        assert frame["wrong"] == [], (number, frame["wrong"][:5])
        assert frame["calls"] == 3 * frame["in_sight"], number
        assert 5 <= frame["in_sight"] <= 60, (number, frame["in_sight"])
        assert frame["claimed"] == pytest.approx(frame["sizes"], abs=0.01), number
        seen.add(round(frame["scroll"]))
    # It did go down the log and come back, and the range never moved under it.
    assert len(seen) >= 8 and max(seen) == round(frames[-1]["scroll_max"])
    assert len({frame["scroll_max"] for frame in frames[2:]}) == 1
    places = [round(frame["scroll"]) for frame in frames]
    assert 0 in places[places.index(max(seen)) :]

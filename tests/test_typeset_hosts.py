r"""
`imscribe.ui.typeset_hosts`, and the host protocol of `imscribe.ui.typeset_view.TypesetView`.

Three groups, the first two as in `tests/test_typeset_view.py`:

1.  **Without the library**, in both runs of the suite: what the module loads,
    and `TypesetDiffFences` reading a fence out of the markdown -- whole, a
    piece at a time, and from the block's own lines when there is no source --
    against a stand-in for the view and for the diff view, so that nothing of
    imtypeset or of Dear ImGui is needed to say which lines a fence holds.
2.  **With it, real frames, no window** (`_HEADLESS`, one child): a stand-in
    widget, for the calls of a frame counted at the ctypes library, its
    rectangle, its height changing, the mouse over it, a copy through it and
    what it raises; then the real thing, the fenced diff of
    `demo/chat/script.md` drawn by a `TypesetDiffView`, whole and as a stream.
    Skipped, with the reason, when `IMTYPESET_LIBRARY` is not set; the child
    says whether `typesetter.module()` and `ready()` held THERE and the
    fixture fails when they did not.
3.  **With it, in a real window** (`_WINDOW`, the `window` fixture; T4-DIFF):
    `TypesetDiffFences` as the `host_for` of a real `TypesetStreamView` fed a
    reply of `demo/chat/script.md` 61 characters a frame, with the mouse and
    the keys queued through `io.add_*_event` -- the fence arriving, a drag in
    the hosted diff, Ctrl+C with the diff in view and with it scrolled out
    (`HostedDiff.handle_keys`), and side by side.
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
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream, parse_markdown
from imscribe.ui.typeset_hosts import HostedDiff, TypesetDiffFences

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_SKIP = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)
_FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]


def _report_of(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    return report


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------

_CLOSURE = r"""
import json, sys
import imscribe.ui.typeset_hosts
print("REPORT " + json.dumps(sorted(
    name for name in sys.modules
    if name.split(".")[0] in ("imscribe", "imtypeset", "imgui_bundle")
)))
"""


def test_the_module_loads_neither_the_diff_view_nor_imgui_nor_the_old_views() -> None:
    """
    `imscribe.ui.typeset_diff_view` is imported when the first fence is met. What
    the import of this module brings in is the typeset view and what that
    stands on; the names below are the ones that must NOT be among them.
    (`tests/test_typeset_closure.py` is where the whole closure is held.)
    """
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
    assert "imscribe.ui.typeset_view" in loaded and "imscribe.diff" in loaded
    for name in (
        "imscribe.ui.typeset_diff_view",
        "imscribe.ui.diff_view",
        "imscribe.ui.bare_view",
        "imscribe.ui.composition",
        "imscribe.markdown",
        "imscribe.stream",
        "imscribe.shipout",
        "imscribe.linebreak",
        "imscribe.selection",
        "imscribe.backends.imgui_draw",
    ):
        assert name not in loaded, name
    assert not [name for name in loaded if name.split(".")[0] in ("imtypeset", "imgui_bundle")]


_SOURCE = (
    "Before.\n\n"
    "```diff\n"
    "--- a/one.py\n"
    "+++ b/one.py\n"
    "@@ -1,2 +1,2 @@\n"
    " kept\n"
    "-old\n"
    "+new\n"
    "```\n\n"
    "Between.\n\n"
    "```python\nprint(1)\n```\n"
)
_BODY = "--- a/one.py\n+++ b/one.py\n@@ -1,2 +1,2 @@\n kept\n-old\n+new\n"


class _DiffView:
    """Stands for a `TypesetDiffView`: it is only ever handed the diff."""

    def __init__(self) -> None:
        self.diffs: list[Any] = []
        self.layouts: list[Any] = []

    def set_diff(self, diff: Any) -> None:
        self.diffs.append(diff)

    def set_layout(self, layout: Any) -> None:
        self.layouts.append(layout)


class _Fences(TypesetDiffFences):
    """`TypesetDiffFences` making stand-ins, so that no library is needed."""

    def _hosted(self, view: Any) -> HostedDiff:
        return HostedDiff(_DiffView())


class _View:
    """What a `host_for` reads of a view: its source, its source map, its widgets, a text."""

    def __init__(self, source: str | None, sources: Any, texts: list[str]) -> None:
        self.source = source
        self.sources = sources
        self.texts = texts
        self.held: dict[int, Any] = {}

    def source_of(self, block: int) -> Any:
        return self.sources[block] if 0 <= block < len(self.sources) else None

    def hosted(self, block: int) -> Any:
        return self.held.get(block)

    def block_text(self, block: int) -> str:
        return self.texts[block]


def _ask(fences: TypesetDiffFences, view: Any, blocks: Any) -> dict[int, Any]:
    held = {}
    for number, block in enumerate(blocks):
        hosted = fences(view, number, block)
        if hosted is not None:
            held[number] = hosted
    view.held = held
    return held


def test_a_fenced_diff_is_taken_and_a_fence_of_anything_else_is_not() -> None:
    theme = Theme.build()
    parsed = parse_markdown(_SOURCE, theme)
    fences = _Fences()
    assert [fences.accepts(block) for block in parsed.blocks] == [False, True, False, False]
    view = _View(_SOURCE, parsed.sources, [])
    held = _ask(fences, view, parsed.blocks)
    assert list(held) == [1]
    hosted = held[1]
    assert isinstance(hosted, HostedDiff)
    assert hosted.text == _BODY
    assert fences.fed_lines == 6 and fences.restarts == 0 and fences.live == 1
    assert fences.view_of(view, 1) is hosted.view and fences.view_of(view, 0) is None
    # The diff the view was handed last is the stream's, and it has the file.
    (file,) = hosted.view.diffs[-1].files
    assert file.new_path == "b/one.py"
    # Asked again about the same fence: the same widget, and nothing read twice.
    again = _ask(fences, view, parsed.blocks)
    assert again[1] is hosted and fences.fed_lines == 6 and fences.restarts == 0
    fences.set_layout("side")
    assert hosted.view.layouts == ["side"]


@pytest.mark.parametrize("chunk", [1, 7, 24])
def test_a_fence_still_being_written_is_fed_a_whole_line_at_a_time(chunk: int) -> None:
    """
    Over an `imscribe.typeset_markdown.MarkdownStream`: at every read the diff
    holds whole lines of the fence's body and nothing else, it only ever
    grows, the widget is the same one throughout, and at the end it is the
    body. No line is read twice (`fed_lines`) and no fence is begun again.
    """
    stream = MarkdownStream(Theme.build())
    fences = _Fences()
    view = _View("", (), [])
    view.stream = stream  # type: ignore[attr-defined]
    widgets = set()
    seen = ""
    for at in range(0, len(_SOURCE), chunk):
        stream.append(_SOURCE[at : at + chunk])
        view.source, view.sources = stream.source, stream.sources
        held = _ask(fences, view, stream.blocks)
        for hosted in held.values():
            widgets.add(id(hosted))
            text = hosted.text
            assert _BODY.startswith(text), (at, text)
            assert text.startswith(seen) and (not text or text.endswith("\n"))
            seen = text
    stream.close()
    view.source, view.sources = stream.source, stream.sources
    held = _ask(fences, view, stream.blocks)
    assert list(held) == [1] and held[1].text == _BODY
    assert len(widgets) == 1
    assert fences.fed_lines == 6 and fences.restarts == 0


def test_with_no_source_the_fence_is_read_from_the_block_s_own_lines() -> None:
    theme = Theme.build()
    parsed = parse_markdown(_SOURCE, theme)
    fences = _Fences()
    texts = [getattr(block, "text", "") for block in parsed.blocks]
    view = _View(None, (), texts)
    held = _ask(fences, view, parsed.blocks)
    assert list(held) == [1] and held[1].text == _BODY
    # The source may be the fences' to give instead, as a string or as a callable.
    for given in (_SOURCE, lambda: _SOURCE):
        other = _Fences(source=given)
        view = _View(None, parsed.sources, texts)
        assert _ask(other, view, parsed.blocks)[1].text == _BODY


# ---------------------------------------------------------------------------
# 2. With the library, real frames, no window
# ---------------------------------------------------------------------------

_HEADLESS = r"""
import json, sys
from pathlib import Path
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_hosts import HostedDiff, TypesetDiffFences
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import TypesetView

ROOT = Path(sys.argv[1])
ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1200.0, 800.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
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
theme = Theme.build()

def frame(view, *, mouse=None, button=None):
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
        imgui.set_next_window_size(imgui.ImVec2(700.0, 400.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##text")
        try:
            del calls[:]
            out = {"answered": view.draw(palette=DARK_PALETTE)}
            out["calls"] = list(calls)
            out["item"] = [imgui.get_item_rect_size().x, imgui.get_item_rect_size().y]
            out["hosts_drawn"] = view.hosts_drawn
            out["selection"] = view.selection
            out["under"] = view.block_under_mouse()
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()
    return out

# -- a stand-in widget ---------------------------------------------------

class Box:
    def __init__(self):
        self.height = 120.0
        self.text = "BOX line one\nBOX line two\n"
        self.drawn = []
        self.asked = []
        self.keys = 0
        self.fail = None
    def height_for(self, width_px):
        self.asked.append(width_px)
        return self.height
    def draw(self, *, palette=None, width_px=None):
        if self.fail is not None:
            raise self.fail
        cursor = imgui.get_cursor_screen_pos()
        self.drawn.append([cursor.x, cursor.y, width_px, palette is DARK_PALETTE])
        imgui.dummy(imgui.ImVec2(width_px, self.height))
    def handle_keys(self):
        self.keys += 1

box = Box()
asked_about = []

def host_for(view, number, block):
    asked_about.append(number)
    if getattr(block, "language", None) == "box":
        return box
    return None

tail = "\n\n".join(
    f"Paragraph {n} of the tail, long enough to be a line of its own." for n in range(40)
)
source = (
    "# A heading\n\nBefore the box.\n\n- item\n\n  ```box\n  not shown\n  ```\n\n"
    "After the box.\n\n" + tail + "\n"
)
view = TypesetView(source, theme=theme, host_for=host_for)
stand = report["stand_in"] = {
    "hosts": list(view.hosts), "hosted": view.hosted(3) is box, "not_hosted": view.hosted(1),
    "asked_about": list(asked_about), "text": view.texts[3], "block_text": view.block_text(3),
    "source": view.block_source(3), "tables": list(view.tables),
}
first = frame(view)
steady = [frame(view) for _ in range(3)][-1]
rect = view.block_rect(3)
geometry = view.native_document.block_geometry(3)
stand["first_calls"] = first["calls"]
stand["steady"] = steady
stand["rect"] = [geometry.min[0] + view.origin[0], geometry.min[1] + view.origin[1],
                 geometry.max[1] - geometry.min[1]]
stand["drawn_at"] = box.drawn[-1]
stand["asked_width"] = box.asked[-1]
stand["view_width"] = steady["item"][0]
stand["asked_once_per_object"] = list(asked_about)

# The same string again, and one that changes only the tail: the box is not asked about again.
view.set_document(source)
view.set_document(source + "\nOne more.\n")
stand["asked_after_a_tail_edit"] = list(asked_about)
frame(view)

# Taller, then nothing at all.
box.height = 200.0
taller = frame(view)
geometry = view.native_document.block_geometry(3)
stand["taller"] = {"calls": taller["calls"], "height": geometry.max[1] - geometry.min[1]}
stand["after_taller"] = frame(view)["calls"]
box.height = 0.0
flat = frame(view)
geometry = view.native_document.block_geometry(3)
stand["flat"] = {"answered": flat["answered"], "height": geometry.max[1] - geometry.min[1],
                 "module": typesetter.module() is not None}
box.height = 120.0
frame(view); frame(view)

# A copy through it has its text, once, a blank line from the text either side.
view.select_all()
stand["copy"] = {"text": view.selected_text(),
                 "expected": view.separator.join(text for text in view.texts if text)}
view.clear_selection()

# The mouse over it is its own; over the text it is the view's.
left, top, right, bottom = view.block_rect(3)
geometry = view.native_document.block_geometry(3)
inside = (view.origin[0] + geometry.min[0] + 30.0, view.origin[1] + geometry.min[1] + 40.0)
frame(view, mouse=inside)
over = frame(view)
frame(view, button=True)
pressed = frame(view)
frame(view, button=False)
released = frame(view)
stand["mouse_on_the_box"] = {
    "calls": over["calls"], "under": over["under"],
    "selection": [pressed["selection"], released["selection"]],
    "dragging": view._dragging, "owns": view.owns_selection,
}
x0, y0, _, y1 = view.native_document.caret_rect((1, 2))
x1 = view.native_document.caret_rect((1, 9))[0]
on_text = (view.origin[0] + x0, view.origin[1] + (y0 + y1) / 2.0)
frame(view, mouse=on_text)
over = frame(view)
frame(view, button=True)
frame(view, mouse=(view.origin[0] + x1, on_text[1]))
dragged = frame(view)
# Across the box and out below it: the drag goes on, and takes the box.
below = view.native_document.caret_rect((4, 3))
frame(view, mouse=(view.origin[0] + below[0], view.origin[1] + (below[1] + below[3]) / 2.0))
across = frame(view)
frame(view, button=False)
frame(view, mouse=(900.0, 700.0))
stand["mouse_on_the_text"] = {
    "under": over["under"], "hit_tested": "HitTestDocument" in over["calls"],
    "dragged": dragged["selection"], "across": across["selection"],
    "across_text": view.selected_text(),
}
view.clear_selection()
frame(view)

# Out of the window it is not drawn, and is asked for its keys.
drawn, keys = len(box.drawn), box.keys
view.scroll_to(len(view.texts) - 1, align=0.0, always=True)
for _ in range(6):
    away = frame(view)
stand["away"] = {"calls": away["calls"], "hosts_drawn": away["hosts_drawn"],
                 "drawn": len(box.drawn) - drawn <= 1, "keys": box.keys - keys}
view.scroll_to(0, align=0.0, always=True)
for _ in range(6):
    back = frame(view)
stand["back"] = {"calls": back["calls"], "hosts_drawn": back["hosts_drawn"]}

# What the widget raises is the widget's: it leaves `draw` as itself and switches nothing off.
box.fail = KeyError("the widget's own")
try:
    frame(view)
    stand["draw_error"] = "none"
except KeyError as exc:
    stand["draw_error"] = "KeyError"
box.fail = None
stand["after_draw_error"] = {"module": typesetter.module() is not None,
                             "calls": frame(view)["calls"] and frame(view)["calls"]}

def refusing(view, number, block):
    raise LookupError("the host's own")
other = TypesetView("One.\n", theme=theme)
frame(other)
other.host_for = refusing
try:
    other.set_document("One.\n\nTwo.\n")
    stand["host_for_error"] = "none"
except LookupError:
    stand["host_for_error"] = "LookupError"
other.host_for = None
out = frame(other)
stand["after_host_for_error"] = {
    "module": typesetter.module() is not None, "answered": out["answered"],
    "texts": list(other.texts), "library_blocks": other.native_document.block_count,
}
other.close()
view.close()

# -- the real thing: a fenced diff ------------------------------------------

loaded_before = "imscribe.ui.typeset_diff_view" in sys.modules
script = (ROOT / "demo" / "chat" / "script.md").read_text(encoding="utf-8")
fences = TypesetDiffFences()
plain = TypesetView(script, theme=theme, math=True)
whole = TypesetView(script, theme=theme, math=True, host_for=fences)
(at,) = whole.hosts
hosted = whole.hosted(at)
frame(whole)
whole.scroll_to(at, align=0.0, always=True)
for _ in range(6):
    shown = frame(whole)
geometry = whole.native_document.block_geometry(at)
diff = report["diff"] = {
    "loaded_before": loaded_before,
    "loaded_after": "imscribe.ui.typeset_diff_view" in sys.modules,
    "hosted": isinstance(hosted, HostedDiff), "view_of": fences.view_of(whole, at) is hosted.view,
    "language": whole.blocks[at].language,
    "text": whole.texts[at] + "\n" == hosted.text,
    "body": whole.block_source(at).split("\n", 1)[1].rsplit("```", 1)[0] == hosted.text,
    "others_same": [a == b for n, (a, b) in enumerate(zip(whole.texts, plain.texts)) if n != at],
    "plain_is_code": plain.texts[at] == whole.texts[at],
    "hosts_drawn": shown["hosts_drawn"], "answered": shown["answered"],
    "origin": list(hosted.view.origin),
    "expected_origin": [whole.origin[0] + geometry.min[0], whole.origin[1] + geometry.min[1]],
    "height": [geometry.max[1] - geometry.min[1],
               hosted.height_for(shown["item"][0] - geometry.min[0])],
    "rows": hosted.view.row_count, "fed_lines": fences.fed_lines, "restarts": fences.restarts,
    "live": fences.live,
}
whole.select_all()
diff["copy"] = hosted.text.removesuffix("\n") in whole.selected_text()
whole.clear_selection()

stream = MarkdownStream(theme, math=True)
live = TypesetStreamView(stream, host_for=fences)
fed, widgets, most, grew = fences.fed_lines, set(), 0, True
EDITS = ("SetDocumentBlocks", "ReplaceDocumentBlocks", "AppendDocumentText")
length = 0
for start in range(0, len(script), 24):
    stream.append(script[start:start + 24])
    out = frame(live)
    # The hosted diff's own documents are edited too; the view's is the one counted.
    for number in live.hosts:
        widget = live.hosted(number)
        widgets.add(id(widget))
        grew = grew and len(widget.text) >= length
        length = len(widget.text)
stream.close()
for _ in range(3):
    frame(live)
diff["stream"] = {
    "texts": list(live.texts) == list(whole.texts), "hosts": list(live.hosts) == [at],
    "widgets": len(widgets), "grew": grew, "fed_lines": fences.fed_lines - fed,
    "restarts": fences.restarts, "edits": dict(live.edits),
    "edit_error": live.native_document.edit_error.code,
    "source": live.source == stream.source,
    "block_source": live.block_source(at) == whole.block_source(at),
}

# A fenced diff that ENDS what is written. The newline that ends its last line
# arrives in the same piece as the closing fence, or never arrives: the code
# block's value is then what it already was, and only where it came from in
# the source, or the stream having finished, says there is a line more.
HEAD = "A reply.\n\n```diff\n--- a/one.py\n+++ b/one.py\n@@ -1,2 +1,2 @@\n kept\n-old\n"
BODY = HEAD.split("```diff\n")[1] + "+new\n"
ends = diff["ends"] = {}
for name, pieces in (
    ("fence_with_the_newline", [HEAD, "+new", "\n```\n"]),
    ("fence_and_no_last_newline", [HEAD, "+new", "\n```"]),
    ("never_closed", [HEAD, "+new"]),
    ("a_character_at_a_time", [*(HEAD + "+new\n```\n")]),
):
    ending = TypesetDiffFences()
    stream = MarkdownStream(theme)
    live = TypesetStreamView(stream, host_for=ending)
    widgets = set()
    for piece in pieces:
        stream.append(piece)
        frame(live)
        widgets.update(id(live.hosted(number)) for number in live.hosts)
    stream.close()
    frame(live)
    frame(live)
    given_whole = TypesetView(stream.source, theme=theme, host_for=TypesetDiffFences())
    (number,) = live.hosts
    live.select_all()
    ends[name] = {
        "widget_text": live.hosted(number).text,
        "library_text": live.texts[number] == BODY.removesuffix("\n"),
        "as_given_whole": list(live.texts) == list(given_whole.texts),
        "copied_last_line": "+new" in live.selected_text(),
        "fed_lines": ending.fed_lines, "restarts": ending.restarts, "widgets": len(widgets),
        "edit_error": live.native_document.edit_error.code,
    }
    live.close()
    given_whole.close()

# The same in a view that is given strings: a fence that is closed by an edit
# which leaves the code block's value alone.
edited = TypesetDiffFences()
view = TypesetView(HEAD + "+new", theme=theme, host_for=edited)
frame(view)
(number,) = view.hosts
first_widget = view.hosted(number)
unclosed = first_widget.text
view.set_document(HEAD + "+new\n```\n\nAfter it.\n")
frame(view)
ends["edited"] = {
    "unclosed": unclosed == BODY.removesuffix("\n"), "closed": view.hosted(number).text == BODY,
    "same_widget": view.hosted(number) is first_widget, "restarts": edited.restarts,
    "texts": list(view.texts),
}
view.close()

report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def headless() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    done = subprocess.run(
        [sys.executable, "-B", "-c", _HEADLESS, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert (
        got["module"] is True
    ), "IMTYPESET_LIBRARY is set and imtypeset is not in use: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True
    assert got["module_at_end"] is True and got["trouble"] == ""
    return got


def test_a_block_the_host_takes_is_a_host_block_holding_the_widget_s_text(
    headless: dict[str, Any],
) -> None:
    stand = headless["stand_in"]
    assert stand["hosts"] == [3] and stand["hosted"] is True and stand["not_hosted"] is None
    assert stand["tables"] == []
    # Its text is the widget's, less the last newline; its source is still the fence.
    assert stand["text"] == stand["block_text"] == "BOX line one\nBOX line two"
    assert stand["source"] == "  ```box\n  not shown\n  ```\n"
    # Asked about each block once, in order, and never again about one that was kept.
    assert stand["asked_about"] == list(range(45))
    assert stand["asked_once_per_object"] == list(range(45))
    assert stand["asked_after_a_tail_edit"] == [*range(45), 45]


def test_a_frame_with_a_hosted_block_in_view_is_one_call_more(headless: dict[str, Any]) -> None:
    """
    Three calls for the document and one asking where the hosted block is: the
    budget is `3 + tables in view + hosted blocks in view + 2 x cells in view`.
    Its height is asked of the WIDGET every frame and given to the library only
    when it changed.
    """
    stand = headless["stand_in"]
    assert stand["first_calls"].count("SetDocumentBlockExtent") == 1
    assert stand["steady"]["calls"] == [*_FRAME, "GetDocumentBlockGeometry"]
    assert stand["steady"]["hosts_drawn"] == 1 and stand["steady"]["answered"] is True
    taller = stand["taller"]
    assert taller["calls"].count("SetDocumentBlockExtent") == 1
    assert taller["height"] == pytest.approx(200.0, abs=0.01)
    assert stand["after_taller"] == [*_FRAME, "GetDocumentBlockGeometry"]
    # No height at all is a height: nothing fails and nothing is switched off.
    assert stand["flat"] == {
        "answered": True,
        "height": pytest.approx(0.0, abs=0.01),
        "module": True,
    }


def test_the_widget_is_handed_its_rectangle_and_the_view_s_palette(
    headless: dict[str, Any],
) -> None:
    stand = headless["stand_in"]
    left, top, height = stand["rect"]
    x, y, width, same_palette = stand["drawn_at"]
    assert (x, y) == (pytest.approx(left, abs=0.01), pytest.approx(top, abs=0.01))
    assert height == pytest.approx(120.0, abs=0.01)
    assert width == pytest.approx(stand["asked_width"], abs=0.01) and same_palette is True
    # In a list item: the rectangle begins at the item's indent and is that much narrower.
    assert 0.0 < stand["view_width"] - width < 100.0
    # The view's own item is still its whole rectangle.
    assert stand["steady"]["item"][0] == stand["view_width"]


def test_a_copy_through_a_hosted_block_has_its_text(headless: dict[str, Any]) -> None:
    copy = headless["stand_in"]["copy"]
    assert copy["text"] == copy["expected"]
    assert "\n\nBOX line one\nBOX line two\n\nAfter the box." in copy["text"]


def test_the_mouse_over_a_hosted_block_is_the_widget_s(headless: dict[str, Any]) -> None:
    stand = headless["stand_in"]
    on_box = stand["mouse_on_the_box"]
    # No hit test, nothing under the mouse, and a press there begins nothing.
    assert on_box["calls"] == [*_FRAME, "GetDocumentBlockGeometry"]
    assert on_box["under"] is None
    assert on_box["selection"] == [None, None] and on_box["dragging"] is False
    on_text = stand["mouse_on_the_text"]
    assert on_text["under"] == 1 and on_text["hit_tested"] is True
    assert on_text["dragged"] == [[1, 2], [1, 9]]
    # A drag begun in the text goes on across the widget, which it takes whole.
    start, end = on_text["across"]
    assert start == [1, 2] and end[0] == 4
    assert "BOX line one\nBOX line two" in on_text["across_text"]


def test_out_of_the_window_it_is_not_drawn_and_is_asked_for_its_keys(
    headless: dict[str, Any],
) -> None:
    stand = headless["stand_in"]
    assert stand["away"]["hosts_drawn"] == 0 and stand["away"]["calls"] == _FRAME
    assert stand["away"]["drawn"] is True and stand["away"]["keys"] >= 5
    assert stand["back"] == {"calls": [*_FRAME, "GetDocumentBlockGeometry"], "hosts_drawn": 1}


def test_what_a_widget_or_a_host_for_raises_is_theirs_and_switches_nothing_off(
    headless: dict[str, Any],
) -> None:
    """
    The view's own `except` turns what the LIBRARY raises into
    `typesetter.disable()`. A hosted widget's `draw`, its `height_for` and the
    `host_for` are the host's code and run outside it.
    """
    stand = headless["stand_in"]
    assert stand["draw_error"] == "KeyError"
    assert stand["after_draw_error"]["module"] is True
    assert stand["after_draw_error"]["calls"] == [*_FRAME, "GetDocumentBlockGeometry"]
    assert stand["host_for_error"] == "LookupError"
    # The view is as the edit left it described, and the library's document was made again.
    assert stand["after_host_for_error"] == {
        "module": True,
        "answered": True,
        "texts": ["One.", "Two."],
        "library_blocks": 2,
    }


def test_a_fenced_diff_is_drawn_by_a_typeset_diff_view_in_its_block_s_rectangle(
    headless: dict[str, Any],
) -> None:
    diff = headless["diff"]
    # Imported when the first fence is met and not before.
    assert diff["loaded_before"] is False and diff["loaded_after"] is True
    assert diff["hosted"] is True and diff["view_of"] is True
    assert diff["language"].split()[0] == "diff"
    # The fence's body, verbatim from the source, is the diff's text and the block's.
    assert diff["text"] is True and diff["body"] is True
    # Nothing else about the document changed, and unhosted it is a code block of the same text.
    assert all(diff["others_same"]) and diff["plain_is_code"] is True
    assert diff["hosts_drawn"] == 1 and diff["answered"] is True
    assert diff["origin"] == pytest.approx(diff["expected_origin"], abs=0.51)
    assert diff["height"][0] == pytest.approx(diff["height"][1], abs=0.01)
    assert diff["rows"] > 5 and diff["fed_lines"] > 5
    assert diff["restarts"] == 0 and diff["live"] == 1
    assert diff["copy"] is True


def test_a_fenced_diff_written_a_piece_at_a_time_ends_as_the_one_given_whole(
    headless: dict[str, Any],
) -> None:
    stream = headless["diff"]["stream"]
    assert stream["texts"] is True and stream["hosts"] is True
    # One widget for the fence from its first line to its last, only ever growing.
    assert stream["widgets"] == 1 and stream["grew"] is True
    assert stream["fed_lines"] == headless["diff"]["fed_lines"] and stream["restarts"] == 0
    assert stream["edits"]["set"] == 1 and stream["edit_error"] == 0
    assert stream["source"] is True and stream["block_source"] is True


@pytest.mark.parametrize(
    "ending",
    [
        "fence_with_the_newline",
        "fence_and_no_last_newline",
        "never_closed",
        "a_character_at_a_time",
    ],
)
def test_a_fenced_diff_that_ends_the_stream_has_its_last_line(
    headless: dict[str, Any], ending: str
) -> None:
    """
    A hosted block is asked about again when where it came from changed.

    `host_for` is asked once per block object, and a block that is kept is
    not asked about again. But the last line of a fenced diff can arrive
    without changing the code block at all: its characters are already there,
    and what arrives is its newline together with the closing fence (or the
    end of the stream, with no newline ever). The widget, which reads whole
    lines from the SOURCE, was never shown that line: 5 lines of 6 here, 14 of
    15 in the Chat page's script, where it was found and worked round
    (`Conversation._reask`, since removed). So the view asks again about a
    hosted block whose source span moved or which the stream has since
    committed, and hands the library the widget's text as it then is: the
    widget's text, the text a selection across it copies, and the view given
    the same source whole all agree.
    """
    got = headless["diff"]["ends"][ending]
    body = "--- a/one.py\n+++ b/one.py\n@@ -1,2 +1,2 @@\n kept\n-old\n+new"
    # Six lines. The last has its newline unless the source never had one.
    assert got["widget_text"] == (body if ending == "never_closed" else body + "\n")
    assert got["library_text"] is True and got["copied_last_line"] is True
    assert got["as_given_whole"] is True
    # Read on from where it had got to: no line twice, the one widget throughout.
    assert got["fed_lines"] == 6 and got["restarts"] == 0 and got["widgets"] == 1
    assert got["edit_error"] == 0


def test_an_edit_that_closes_a_fence_and_leaves_its_code_alone_reaches_the_widget(
    headless: dict[str, Any],
) -> None:
    """
    The same rule in a view given strings: the unclosed fence's last line has
    no newline, the edit adds the newline, the closing fence and a paragraph.
    """
    got = headless["diff"]["ends"]["edited"]
    assert got["unclosed"] is True and got["closed"] is True
    assert got["same_widget"] is True and got["restarts"] == 0
    assert got["texts"][0] == "A reply." and got["texts"][2] == "After it."
    assert got["texts"][1].endswith("+new")


def test_a_hosted_diff_answers_its_view_s_headers() -> None:
    """
    PH-DIFF (pptmstr's P16): whether a file's header fit is asked of the
    hosted widget as it is of a `TypesetDiffView`, the width passed on.
    """

    class Headed(_DiffView):
        def headers(self, width_px: float | None = None) -> list[Any]:
            return [("one.py  +1 -1", width_px)]

    hosted = HostedDiff(Headed())
    assert hosted.headers() == (("one.py  +1 -1", None),)
    assert hosted.headers(300.0) == (("one.py  +1 -1", 300.0),)


def test_a_hosted_diff_passes_the_keys_on_to_its_view() -> None:
    """
    T4-DIFF. `Hosted` says a widget with a `handle_keys()` is called through it
    on a frame it is not drawn. `HostedDiff` had none, so Ctrl+C on a selection
    made in a diff that was then scrolled out of the window did nothing.
    """

    class Keys(_DiffView):
        asked = 0

        def handle_keys(self) -> None:
            self.asked += 1

    view = Keys()
    hosted = HostedDiff(view)
    hosted.handle_keys()
    hosted.handle_keys()
    assert view.asked == 2


# ---------------------------------------------------------------------------
# 3. With the library, in a real window: a fenced diff in a REAL stream view
# ---------------------------------------------------------------------------

_WINDOW = r"""
import json, sys
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_hosts import HostedDiff, TypesetDiffFences
from imscribe.ui.typeset_stream_view import TypesetStreamView

ROOT = Path(sys.argv[1])
PARKED = (5.0, 695.0)
theme = Theme.build()
report = {}
events = []
state = {"n": 0, "view": None, "last": None, "done": False}

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    report["load_fonts"] = typesetter.load_fonts()

def pre_new_frame():
    io = imgui.get_io()
    io.mouse_single_click_delay = 31.0
    io.mouse_double_click_time = 30.0
    while events:
        events.pop(0)(io)

def wait(frames=1):
    for _ in range(frames):
        yield

def do(*queued):
    events.extend(queued)
    yield
    yield

def move(x, y):
    return do(lambda io: io.add_mouse_pos_event(float(x), float(y)))

def button(down):
    return do(lambda io: io.add_mouse_button_event(0, down))

def key(name, down):
    return lambda io: io.add_key_event(getattr(imgui.Key, name), down)

def ctrl(letter):
    yield from do(key("mod_ctrl", True), key(letter, True))
    yield from do(key(letter, False), key("mod_ctrl", False))

def point(diff, row, column):
    # A point on display row `row` of a hosted diff, just right of the left edge of a cell.
    ox, oy = diff.origin
    pane = diff._panes(diff._width, diff.grid.cell)[0]
    return (ox + pane.code - diff.scroll_x + column * diff.grid.cell + 1.0,
            oy + diff.row_top(row) + diff.row_px / 2.0)

def script():
    ts = typesetter.module()
    report["module"] = ts is not None
    report["ready"] = typesetter.ready()
    report["reason"] = typesetter.reason()
    if ts is None or not typesetter.ready():
        return
    text = (ROOT / "demo" / "chat" / "script.md").read_text(encoding="utf-8")
    # The turn with the diff in it, and enough after it that the diff can leave the window.
    source = text[text.index("One argument and one changed line."):]
    stream = MarkdownStream(theme, math=True)
    fences = TypesetDiffFences()
    view = state["view"] = TypesetStreamView(stream, host_for=fences)
    yield from move(*PARKED)

    # ---- the fence arrives 61 characters a frame, drawn every frame ----------------------
    widgets, rows, answered, drawn = [], [], [], 0
    for start in range(0, len(source), 61):
        stream.append(source[start:start + 61])
        yield from wait(1)
        answered.append(state["last"]["answered"])
        drawn = max(drawn, state["last"]["hosts_drawn"])
        for number in view.hosts:
            hosted = view.hosted(number)
            if not any(hosted is seen for seen in widgets):
                widgets.append(hosted)
            rows.append(hosted.view.row_count)
    stream.close()
    yield from wait(3)
    (at,) = view.hosts
    hosted = view.hosted(at)
    diff = hosted.view
    body = source.split("```diff\n", 1)[1].split("```", 1)[0]
    report["arrival"] = {
        "widgets": len(widgets), "is_hosted_diff": isinstance(hosted, HostedDiff),
        "rows_only_grew": rows == sorted(rows), "rows": diff.row_count,
        "answered": all(answered), "drawn_while_arriving": drawn,
        "text_is_the_fence_s_body": hosted.text == body,
        "fed_lines": [fences.fed_lines, body.count("\n")], "restarts": fences.restarts,
        "view_of": fences.view_of(view, at) is diff, "live": fences.live,
        "edits": dict(view.edits), "diff_edits": dict(diff.edits),
        "edit_error": view.native_document.edit_error.code,
    }

    # ---- shown: the diff is drawn in its block's rectangle, in the view's window ----------
    view.scroll_to(at, align=0.0, always=True)
    yield from wait(6)
    geometry = view.native_document.block_geometry(at)
    shown = dict(state["last"])
    report["shown"] = {
        "hosts_drawn": shown["hosts_drawn"], "answered": shown["answered"],
        "vertices": shown["vertices"],
        "origin": list(diff.origin),
        "expected_origin": [view.origin[0] + geometry.min[0], view.origin[1] + geometry.min[1]],
        "height": [geometry.max[1] - geometry.min[1], diff.content_height,
                   diff.row_count * diff.row_px],
        "visible_rows": [diff.visible_rows.start, diff.visible_rows.stop],
        "diff_documents": len(diff.native_documents),
        # P16: whether the fence's file header fit is asked of the hosted widget.
        "headers": [[h.text, h.warning, h.width_px, h.available_px, h.fits]
                    for h in hosted.headers()],
        "narrow": [[h.available_px, h.fits] for h in hosted.headers(40.0)],
        "block_width": geometry.max[0] - geometry.min[0],
    }

    # ---- the mouse over it is the diff's: a drag selects in the diff, not in the document ----
    hunk = diff.diff.files[0].hunks[0]
    code = [r for r in range(diff.row_count) if diff.row_info(r).kind == "row"
            and len(hunk.rows[diff.row_info(r).left].text) > 12]
    a_row, b_row = code[1], code[4]
    yield from move(*point(diff, a_row, 2))
    yield from button(True)
    yield from move(*point(diff, b_row, 9))
    yield from wait(2)
    yield from button(False)
    yield from move(*PARKED)
    yield from wait(2)
    imgui.set_clipboard_text("untouched")
    yield from ctrl("c")
    in_view = imgui.get_clipboard_text()
    selected = diff.selected_text()
    report["drag"] = {
        "diff_selection": diff.selection, "outer_selection": view.selection,
        "owns": [diff.owns_selection, view.owns_selection],
        "text": selected, "clipboard": in_view,
        "info": [[diff.row_info(r).left for r in (a_row, b_row)]],
    }

    # ---- scrolled out of the window: not drawn, and Ctrl+C still copies ITS selection --------
    view.scroll_to(len(view.texts) - 1, align=0.0, always=True)
    yield from wait(6)
    away = dict(state["last"])
    imgui.set_clipboard_text("untouched")
    yield from ctrl("c")
    report["away"] = {
        "hosts_drawn": away["hosts_drawn"], "clipboard": imgui.get_clipboard_text(),
        "text": selected, "still_selected": diff.selection is not None,
        "scroll_y": away["scroll_y"],
        "block_is_above_the_window": view.block_rect(at)[3] < 10.0,
    }

    # ---- back, side by side: every fence made so far switches -------------------------------
    fences.set_layout("side-by-side")
    view.scroll_to(at, align=0.0, always=True)
    yield from wait(6)
    back = dict(state["last"])
    report["side"] = {
        "layout": diff.layout.value, "hosts_drawn": back["hosts_drawn"],
        "answered": back["answered"], "documents": len(diff.native_documents),
        "vertices": back["vertices"],
    }
    report["trouble"] = typesetter.trouble()
    report["module_at_end"] = typesetter.module() is not None

def gui():
    state["n"] += 1
    if not state["done"]:
        try:
            next(state["script"])
        except StopIteration:
            state["done"] = True
    if state["done"]:
        hello_imgui.get_runner_params().app_shall_exit = True
        return
    view = state["view"]
    if view is None:
        return
    flags = (imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value
             | imgui.WindowFlags_.no_saved_settings.value)
    imgui.set_next_window_pos(imgui.ImVec2(10.0, 10.0))
    imgui.set_next_window_size(imgui.ImVec2(860.0, 660.0))
    imgui.begin("document", None, flags)
    try:
        draw_list = imgui.get_window_draw_list()
        vertices = draw_list.vtx_buffer.size()
        answered = view.draw(palette=DARK_PALETTE)
        state["last"] = {
            "answered": answered, "hosts_drawn": view.hosts_drawn,
            "vertices": draw_list.vtx_buffer.size() - vertices,
            "scroll_y": imgui.get_scroll_y(),
        }
    finally:
        imgui.end()

state["script"] = script()
runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "a fenced diff in a stream view, under test"
runner.app_window_params.window_geometry.size = (900, 700)
runner.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
runner.ini_disable = True
runner.fps_idling.enable_idling = False
runner.callbacks.load_additional_fonts = load_fonts
runner.callbacks.show_gui = gui
runner.callbacks.pre_new_frame = pre_new_frame
runner.callbacks.before_exit = typesetter.unload
immapp.run(runner)
report["frame_count"] = state["n"]
report["finished"] = state["done"]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def windowed(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    script = window.out / "typeset_hosts_driver.py"
    script.write_text(_WINDOW, encoding="utf-8")
    done = window.run([str(script), str(_ROOT)], timeout=300.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-6000:]
    got = _report_of(done.stdout)
    # In the child, not here: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert got["finished"] is True and "side" in got, "the driver's script did not reach its end"
    assert got["module_at_end"] is True and got["trouble"] == ""
    return got


def test_in_a_window_a_fence_arriving_in_a_stream_view_is_one_diff_that_only_grows(
    windowed: dict[str, Any],
) -> None:
    """
    T4-DIFF: `TypesetDiffFences` as the `host_for` of a real `TypesetStreamView`
    in a real window (tranche 3 ran it in headless frames, and T3-C's reader
    against a stand-in). The reply of `demo/chat/script.md` with the diff in
    it, 61 characters a frame, drawn every frame: one widget from the fence's
    first line to its last, its rows only ever growing, every line of the body
    read once, every frame answered, and the document set once.
    """
    arrival = windowed["arrival"]
    assert arrival["widgets"] == 1 and arrival["is_hosted_diff"] is True
    assert arrival["rows_only_grew"] is True and arrival["rows"] > 10
    assert arrival["answered"] is True and arrival["drawn_while_arriving"] == 1
    assert arrival["text_is_the_fence_s_body"] is True
    fed, lines = arrival["fed_lines"]
    assert fed == lines > 10 and arrival["restarts"] == 0
    assert arrival["view_of"] is True and arrival["live"] == 1
    assert arrival["edits"]["set"] == 1 and arrival["edit_error"] == 0
    # The diff's own two documents: set once each, then replaced as lines arrived.
    assert arrival["diff_edits"]["set"] == 2 and arrival["diff_edits"]["replace"] >= 2


def test_in_a_window_the_hosted_diff_is_drawn_in_its_block_s_rectangle(
    windowed: dict[str, Any],
) -> None:
    shown = windowed["shown"]
    assert shown["hosts_drawn"] == 1 and shown["answered"] is True
    assert shown["vertices"] > 100 and shown["diff_documents"] == 2
    assert shown["origin"] == pytest.approx(shown["expected_origin"], abs=0.51)
    block, content, rows = shown["height"]
    assert block == pytest.approx(content, abs=0.01) and content == rows
    first, stop = shown["visible_rows"]
    assert first == 0 and stop > 10
    # P16: the fence's one file header, and that it fit the block it was drawn in.
    ((text, warning, width, available, fits),) = shown["headers"]
    assert text.startswith("replay.py  +")
    assert warning == "" and 0.0 < width <= available and fits is True
    assert available == pytest.approx(shown["block_width"], abs=1.0)
    # Eight cells is the least a view is drawn at, in whole pixels. Restated on imtypeset
    # 0.4.1: this was `[[63.0, False]]`, because the cell was the face's own advance
    # (7.99999 px: eight of them are 63.99991, cut to whole pixels). The cell is the
    # device's whole pixel now, 8.0 exactly, and eight of them are 64.
    assert shown["narrow"] == [[64.0, False]]
    side = windowed["side"]
    assert side["layout"] == "side-by-side" and side["documents"] == 4
    assert side["hosts_drawn"] == 1 and side["answered"] is True and side["vertices"] > 100


def test_in_a_window_a_drag_in_the_hosted_diff_is_the_diff_s_and_ctrl_c_copies_it(
    windowed: dict[str, Any],
) -> None:
    """
    The mouse over a hosted block is the widget's: the drag selects in the
    diff (positions in its model) and nothing in the document, the diff owns
    the process's one selection, and Ctrl+C puts the diff's text -- code, no
    markers, no line numbers -- on the clipboard.
    """
    drag = windowed["drag"]
    start, end = drag["diff_selection"]
    assert start[:2] == end[:2] == [0, 0] and start[2] < end[2]
    assert start[3] == 2 and drag["outer_selection"] is None
    assert drag["owns"] == [True, False]
    assert drag["text"] and drag["clipboard"] == drag["text"]
    assert not any(line.startswith(("+", "-")) for line in drag["text"].split("\n"))


def test_in_a_window_a_hosted_diff_out_of_view_still_answers_ctrl_c(
    windowed: dict[str, Any],
) -> None:
    """
    `HostedDiff.handle_keys` (new at T4-DIFF): scrolled out of the window the
    diff is not drawn, the stream view calls its `handle_keys`, and Ctrl+C
    copies the selection made in it. Without the method the clipboard stayed
    as it was.
    """
    away = windowed["away"]
    assert away["hosts_drawn"] == 0 and away["block_is_above_the_window"] is True
    assert away["scroll_y"] > 660.0
    assert away["still_selected"] is True
    assert away["clipboard"] == away["text"] != "untouched"

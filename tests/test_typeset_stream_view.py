r"""
`imscribe.ui.typeset_stream_view.TypesetStreamView`.

Which tests run depends on how the suite was started (`make test`, or `make
test TYPESET=1`), as in `tests/test_typeset_view.py`:

1.  **Without the library.** `appended` (which edit a grown tail gets) is plain
    data and is tested here in this process; the constructor's refusal runs in
    a child with the two variables removed, so it holds in both runs.
2.  **With it, no window.** Skipped, with the reason, when `IMTYPESET_LIBRARY`
    is not set. ONE run of `_HEADLESS` in a child: real ImGui frames in a
    scrolling child window with no display, calls into the library counted in
    front of `imtypeset._lib` (a private name of a package this tree does not
    own; if it moves the fixture fails, it does not pass).
3.  **With it, in a real window** (the `window` fixture): `_DRIVER` streams
    `demo/sample.md` through `TypesetStreamView` and reports what each `draw`
    took. The child says whether `typesetter.module()` and `ready()` held
    there.

The stream is an `imscribe.typeset_markdown.MarkdownStream` everywhere. Until
tranche 5 half of the replays fed the view an `imscribe.stream.StreamDocument`
and the window run timed `imscribe.ui.stream_view.StreamView` beside it; both
are deleted, and those cases went with them
(`.concerns/T5-B1--builder--result.md` counts them). Where a replay was held
against the old core's description of the whole document, it is held against
that description frozen (`tests/material_frozen.py`), laid out by the library
in the child.

Times are in the report and are NOT asserted;
`.concerns/IT-A3--builder--result.md` has what was read off and at what load.
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
from imscribe.description import (
    BLOCK_TABLE_HEADER,
    BLOCK_TABLE_HELD,
    KIND_TABLE,
    CellDescription,
    ColumnDescription,
    table_text,
)
from imscribe.typesetter import (
    KIND_CODE,
    KIND_HOST,
    KIND_RULE,
    BlockDescription,
    RunDescription,
)
from imscribe.ui.typeset_stream_view import appended, appended_cell_text, appended_rows

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


def test_a_tail_whose_text_only_grew_is_the_new_characters_and_the_new_runs() -> None:
    bold = RunDescription(5, 9, 2)
    before = BlockDescription(text="some bold", runs=(bold,), marker="1.", left_indent=12.0)
    later = RunDescription(14, 18, 3)
    after = before._replace(text="some bold and more", runs=(bold, later))
    assert appended(before, after) == (" and more", (later,))
    assert appended(before, before._replace(text="some bold!")) == ("!", ())
    # A block with no text yet is appended to like any other.
    empty = BlockDescription(kind=KIND_CODE)
    assert appended(empty, empty._replace(text="line")) == ("line", ())


@pytest.mark.parametrize(
    "change",
    [
        {"text": "some bold"},  # nothing arrived
        {"text": "some"},  # shorter
        {"text": "Some bold and more"},  # not the same beginning
        {"text": "some bold more", "runs": (RunDescription(5, 14, 2),)},  # a held run grew
        {"text": "some bold more", "runs": ()},  # a held run went
        {"text": "some bold more", "style": 3},
        {"text": "some bold more", "flags": 1},  # a hard break arrived
        {"text": "some bold more", "marker": "2."},
        {"text": "some bold more", "left_indent": 4.0},
        {"text": "some bold more", "kind": KIND_CODE},
    ],
)
def test_anything_else_is_not_an_append(change: dict[str, Any]) -> None:
    before = BlockDescription(text="some bold", runs=(RunDescription(5, 9, 2),), marker="1.")
    assert appended(before, before._replace(**{"runs": before.runs, **change})) is None


def _table(*rows: tuple[CellDescription, ...], **more: Any) -> BlockDescription:
    return BlockDescription(
        kind=KIND_TABLE,
        text=table_text([cell.text for cell in row] for row in rows),
        flags=BLOCK_TABLE_HEADER | BLOCK_TABLE_HELD,
        rows=rows,
        columns=(ColumnDescription(1), ColumnDescription(3)),
        **more,
    )


def test_a_table_with_more_rows_is_the_new_rows_and_one_with_more_text_in_its_last_cell() -> None:
    """
    The two things the library can append to a table: rows after the ones it
    has, and text to its LAST cell, whose runs are then ranges of the BLOCK's
    text (the cell's own offsets moved by where the cell starts).
    """
    head = (CellDescription("a"), CellDescription("b"))
    one = (CellDescription("1"), CellDescription("2"))
    two = (CellDescription("3"), CellDescription(""))
    before = _table(head, one)
    assert appended_rows(before, _table(head, one, two)) == (two,)
    assert appended_rows(_table(head), _table(head, one, two)) == (one, two)
    assert appended_rows(before, before) is None
    assert appended_rows(before, _table(head, two)) is None  # a row it had changed
    assert appended_rows(before, _table(head, one, two, style=2)) is None
    held = before._replace(flags=BLOCK_TABLE_HEADER)
    assert appended_rows(held, _table(head, one, two)) is None  # the flag is not an append
    wider = before._replace(columns=(ColumnDescription(1), ColumnDescription(2)))
    assert appended_rows(wider, _table(head, one, two)) is None
    assert appended_rows(BlockDescription(text="a"), _table(head)) is None
    # A paragraph's append is not a table's, and the other way about.
    assert appended(before, _table(head, one, two)) is None
    assert appended(_table(head, two), _table(head, (two[0], CellDescription("4")))) is None

    bold = RunDescription(0, 2, 2)
    later = RunDescription(3, 5, 3)
    grown = (CellDescription("3"), CellDescription("xy z", (bold, later)))
    start = _table(head, one, (CellDescription("3"), CellDescription("xy", (bold,))))
    after = _table(head, one, grown)
    # "a\tb\n1\t2\n3\t" is ten characters: the last cell starts at 10.
    assert after.text.index("xy z") == 10
    assert appended_cell_text(start, after) == (" z", (RunDescription(13, 15, 3),))
    assert appended_cell_text(_table(head, two), _table(head, (two[0], CellDescription("4")))) == (
        "4",
        (),
    )
    assert appended_cell_text(start, start) is None
    assert appended_cell_text(before, _table(head, one, two)) is None  # a new row
    # Another cell than the last grew, a held run changed, a cell was added to the row.
    first_grew = _table(head, (CellDescription("10"), one[1]))
    assert appended_cell_text(_table(head, one), first_grew) is None
    moved = _table(head, one, (CellDescription("3"), CellDescription("xy z", (later,))))
    assert appended_cell_text(start, moved) is None
    longer = _table(head, (*one, CellDescription("x")))
    assert appended_cell_text(before, longer) is None and appended_rows(before, longer) is None
    assert appended_cell_text(BlockDescription(text="a"), BlockDescription(text="ab")) is None


@pytest.mark.parametrize("kind", [KIND_HOST, KIND_RULE])
def test_a_block_that_holds_no_text_is_never_appended_to(kind: int) -> None:
    """
    The library raises for one (`.concerns/IT-A3-scripts/probe_append.py`), and
    what it raises switches it off for the run.
    """
    before = BlockDescription(kind=kind, extent=24.0)
    assert appended(before, before._replace(text="text")) is None


_WITHOUT = r"""
import json, sys
import imscribe.ui.typeset_stream_view as module
from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream

loaded = sorted(name for name in sys.modules if name.split(".")[0] in ("imtypeset", "imgui_bundle"))
try:
    module.TypesetStreamView(MarkdownStream(Theme.build()))
    refused = None
except module.TypesetUnavailable as exc:
    refused = str(exc)
print("REPORT " + json.dumps({"loaded": loaded, "refused": refused, "reason": typesetter.reason()}))
"""


def test_without_the_library_the_constructor_refuses_and_names_the_reason() -> None:
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
    assert report["reason"] == typesetter.SWITCHED_OFF_REASON
    assert report["reason"] in report["refused"]


# ---------------------------------------------------------------------------
# 2. With the library, real frames, no window
# ---------------------------------------------------------------------------

_COUNTING = r"""
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
"""

_HEADLESS = (
    r"""
import dataclasses, json, sys
from pathlib import Path
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.description import BLOCK_TABLE_HELD
from imscribe.theme import Align, Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import TypesetView

def live_theme(theme):
    # The theme a stream's unfinished tail is built with under "reset": justified blocks set
    # ragged. (`imscribe.stream.live_theme`, deleted with that module; the Stream page has it
    # as `ragged`.)
    ragged = lambda style: (  # noqa: E731
        dataclasses.replace(style, align=Align.LEFT) if style.align is Align.JUSTIFY else style
    )
    return dataclasses.replace(
        theme, blocks={kind: ragged(style) for kind, style in theme.blocks.items()}
    )
"""
    + _COUNTING
    + r"""
ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "tests"))
import material_frozen
ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1200.0, 800.0)
io.delta_time = 1.0 / 60.0
# No renderer: saying the backend takes textures is enough for the library to draw.
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
calls = []
ts._lib = Counting(ts._lib, calls)
EDITS = ("SetDocumentBlocks", "ReplaceDocumentBlocks", "AppendDocumentText",
         "AppendDocumentTableCells")
FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]
theme = Theme.build()

def frame(view, *, wheel=None, mouse=None):
    # One frame of the view in a scrolling child. The scroll is read where the view reads it.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
        imgui.set_next_window_size(imgui.ImVec2(700.0, 400.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##text")
        try:
            out = {"scroll": imgui.get_scroll_y(), "limit": imgui.get_scroll_max_y()}
            draw_list = imgui.get_window_draw_list()
            before = draw_list.vtx_buffer.size()
            del calls[:]
            out["answered"] = view.draw()
            out["calls"] = list(calls)
            out["vertices"] = draw_list.vtx_buffer.size() - before
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()
    return out

def everything(view):
    doc = view.native_document
    last = len(view.texts) - 1
    return doc.range_text(((0, 0), (last, len(view.texts[last]))), "\n\n")

def columns_of(view, at):
    # Each column of a table as [width, natural width], in pixels.
    count = view.table_geometry(at).column_count
    columns = [view.table_column(at, column) for column in range(count)]
    return [[round(c.max - c.min, 3), round(c.natural, 3)] for c in columns]

def replay(name, chunk, reset=False):
    # `reset` gives the stream a theme of its own for its unfinished tail, which is what
    # makes a block be set again when it commits.
    source = (ROOT / "demo" / name).read_text(encoding="utf-8")
    if reset:
        stream = MarkdownStream(theme, math=True, live_theme=live_theme(theme))
    else:
        stream = MarkdownStream(theme, math=True)
    view = TypesetStreamView(stream)
    frame(view, mouse=(1000.0, 700.0))   # off the view: no hit test
    seen = stream.revision
    told = {"stream_changes": 0, "view_changes": 0, "broken": [], "other_calls": [],
            "live_table_syncs": 0, "short_of_the_end": 0, "frames": 0, "no_vertices": 0,
            "most_edits_in_a_sync": 0, "edit_calls": 0}
    pieces = [source[at:at + chunk] for at in range(0, len(source), chunk)]
    for piece in [*pieces, None, False]:   # then the close, then a frame with nothing new
        if piece is None:
            stream.close()
        elif piece is not False:
            stream.append(piece)
        moved = stream.revision != seen
        seen = stream.revision
        revision, edits = view.revision, sum(view.edits.values())
        out = frame(view)
        told["frames"] += 1
        made = [call for call in out["calls"] if call in EDITS]
        rest = [call for call in out["calls"] if call not in EDITS]
        changed = view.revision - revision
        told["stream_changes"] += moved
        told["view_changes"] += changed
        told["most_edits_in_a_sync"] = max(told["most_edits_in_a_sync"], len(made))
        counted = sum(view.edits.values()) - edits
        told["edit_calls"] += len(made)
        # At most one edit, and only when the blocks changed; never a change of
        # the blocks without a change of the stream's revision; and the view's
        # own count is the count of calls.
        if len(made) > changed or changed > moved or counted != len(made):
            told["broken"].append([told["frames"], moved, changed, out["calls"]])
        if rest not in told["other_calls"]:
            told["other_calls"].append(rest)
        if stream.live and view.tables and view.tables[-1] == len(view.texts) - 1:
            told["live_table_syncs"] += changed
        if out["limit"] > 0.0 and out["scroll"] < out["limit"]:
            told["short_of_the_end"] += 1
        told["no_vertices"] += out["vertices"] <= 0 and bool(view.texts)
    last = frame(view)
    told["idle_calls"] = last["calls"]
    told["at_the_end"] = [last["scroll"], last["limit"], view.following]
    told["edits"] = dict(view.edits)
    told["blocks"] = len(view.texts)
    told["tables"] = list(view.tables)
    told["held"] = [bool(view._described[at].flags & BLOCK_TABLE_HELD) for at in view.tables]
    told["stated"] = [view.table_geometry(at).stated for at in view.tables]
    doc = view.native_document
    told["library_blocks"] = doc.block_count
    told["edit_error"] = doc.edit_error.code
    told["block_texts"] = all(
        doc.range_text(((i, 0), (i, len(text)))) == text for i, text in enumerate(view.texts)
    )
    # The whole source two ways. Given whole to a `TypesetView`; and as the OLD CORE described
    # it (frozen: `Converter` over `build_document`'s blocks), handed to a document of the
    # library's here and copied back. Until tranche 5 the second was a `TypesetView` given
    # the old core's blocks.
    whole = TypesetView(source, theme=theme, math=True)
    frame(whole)
    frozen = material_frozen.description(source)
    material = ts.Document.from_blocks(frozen.blocks, typesetter.block_styles(frozen.styles))
    material.layout(600.0, typesetter.base_style(theme, 0xFFFFFFFF))
    material.layout_window(0.0, 1.0e9)
    last = len(frozen.texts) - 1
    at_once = material.range_text(((0, 0), (last, len(frozen.texts[last]))), "\n\n")
    told["material_edit_error"] = material.edit_error.code
    material.close()
    told["whole_stated"] = [whole.table_geometry(at).stated for at in whole.tables]
    told["columns"] = [columns_of(view, at) for at in view.tables]
    told["whole_columns"] = [columns_of(whole, at) for at in whole.tables]
    told["converter"] = type(view.converter).__name__
    told["source"] = view.source == stream.source
    told["sources"] = [view.source_of(n) == stream.sources[n] for n in range(len(view.texts))]
    told["same_texts"] = frozen.texts == list(view.texts)
    copied = everything(view)
    told["same_copy"] = copied == at_once
    told["copy_length"] = [len(copied), len(at_once)]
    told["same_as_whole"] = [list(whole.texts) == list(view.texts), copied == everything(whole)]
    told["trouble"] = typesetter.trouble()
    whole.close()
    view.close()
    return told

report["replays"] = {
    "sample 24 direct": replay("sample.md", 24),
    "sample 5 direct": replay("sample.md", 5),
    "tables 24 direct": replay("tables.md", 24),
    "math 24 direct": replay("math.md", 24),
    "sample 5 direct reset": replay("sample.md", 5, reset=True),
}

def fresh(text="", **more):
    stream = MarkdownStream(theme)
    view = TypesetStreamView(stream, **more)
    if text:
        stream.append(text)
    return stream, view, frame(view, mouse=(300.0, 200.0))

# Nothing arriving is three calls and no edit; several pieces between two frames are one edit.
stream, view, first = fresh("Some words here")
idle = [frame(view)["calls"] for _ in range(3)]
for piece in (" and", " some", " more", " of them"):
    stream.append(piece)
burst = frame(view)["calls"]
report["idle"] = {"first": first["calls"], "idle": idle, "burst": burst, "edits": dict(view.edits)}
# The end of the line arrives: the stream's revision moves and its blocks are what they were.
seen, revision = stream.revision, view.revision
stream.append("\n")
moved = stream.revision != seen
made = frame(view)["calls"]
report["idle"]["white_space"] = [moved, view.revision - revision, made]

# A selection in the block being written, while words arrive after it.
view.select(((0, 5), (0, 10)))
stream.append(" and yet more")
frame(view)
report["selection_kept"] = [view.selection, view.selected_text(), dict(view.edits)]
# A second paragraph begins: the first commits, and both are replaced.
stream.append("\n\nAnother paragraph")
frame(view)
report["selection_over_a_commit"] = [view.selection, view.selected_text(), dict(view.edits)]
view.select_all()
stream.append(" grows")
frame(view)
report["all"] = [view.selection, len(view.texts[-1])]
try:
    view.set_document("# Not the stream's\n")
    report["set_document"] = "taken"
except TypeError as exc:
    report["set_document"] = str(exc)
try:
    view.set_theme(theme)
    report["set_theme"] = "taken"
except TypeError as exc:
    report["set_theme"] = str(exc)
view.close()

# Markup that closes late: the characters before the selection's end are other characters.
stream, view, _ = fresh("A **bol")
report["unclosed"] = list(view.texts)
view.select(((0, 0), (0, 5)))
stream.append("d** end")
frame(view)
report["reinterpreted"] = [list(view.texts), view.selection, dict(view.edits)]
view.close()
stream, view, _ = fresh("A **bol")
view.select(((0, 0), (0, 2)))
stream.append("d** end")
frame(view)
report["before_the_markup"] = [view.selection, view.selected_text()]
view.close()

# A table as the block being written, a row at a time; then a rule; then text again.
# Two streams: with and without a theme of its own for the tail (which is what "reset" is).
TABLE_LINES = ("| a | b |\n", "|---|---|\n", "| 1 | 2 |\n", "| 3 | 4 |\n", "| 5 ", "| 6 |\n",
               "| a much longer cell | 7 |\n", "| 8 | 9 |\n",
               "\n", "---\n", "\n", "After", " it.")

def table_stream(kind):
    if kind == "direct keep":
        return MarkdownStream(theme)
    return MarkdownStream(theme, live_theme=live_theme(theme))

def table_case(kind):
    stream = table_stream(kind)
    view = TypesetStreamView(stream)
    stream.append("Before.\n\n")
    frame(view, mouse=(300.0, 390.0))
    rows = []
    for line in TABLE_LINES:
        stream.append(line)
        out = frame(view)
        made = [call for call in out["calls"] if call in EDITS]
        row = {"made": made, "tables": list(view.tables), "blocks": len(view.texts),
               "live": len(stream.live), "committed": len(stream.committed)}
        if view.tables:
            at = view.tables[0]
            geometry = view.table_geometry(at)
            row.update(
                held=bool(view._described[at].flags & BLOCK_TABLE_HELD),
                stated=geometry.stated, rows=geometry.row_count,
                width=round(geometry.max[0] - geometry.min[0], 3),
                columns=columns_of(view, at),
            )
        rows.append(row)
    stream.close()
    frame(view)
    whole = TypesetView(stream.source, theme=theme)
    frame(whole)
    at = view.tables[0]
    told = {"rows": rows, "edits": dict(view.edits), "texts": list(view.texts),
            "keeps": view.keeps_streamed(),
            "reason": typesetter.reason(), "module": typesetter.module() is not None,
            "error": view.native_document.edit_error.code,
            "same_copy": everything(view) == everything(whole),
            "same_texts": list(view.texts) == list(whole.texts),
            "final": {"held": bool(view._described[at].flags & BLOCK_TABLE_HELD),
                      "stated": view.table_geometry(at).stated,
                      "columns": columns_of(view, at),
                      "row_tops": [round(view.table_row(at, r).min, 3) for r in range(6)]},
            "whole": {"stated": whole.table_geometry(at).stated, "columns": columns_of(whole, at),
                      "row_tops": [round(whole.table_row(at, r).min, 3) for r in range(6)],
                      "pane": round(whole.table_geometry(at).max[0], 3)},
            "trouble": typesetter.trouble()}
    whole.close()
    view.close()
    return told

report["table"] = {kind: table_case(kind) for kind in ("direct keep", "direct reset")}

# The tail: followed, let go by the wheel, kept where the reader left it, taken again.
def fed(stream, view, words, start=0):
    for number in range(start, start + words):
        stream.append(f"word{number} ")
        if number % 40 == 39:
            stream.append("\n\n")
        if number % 10 == 9:
            frame(view)
    frame(view)

stream, view, _ = fresh()
fed(stream, view, 600)
frame(view)
at = frame(view)
tail = report["tail"] = {"followed": [at["scroll"], at["limit"], view.following]}
frame(view, wheel=3.0)
at = frame(view)
tail["wheeled_up"] = [at["scroll"], at["limit"], view.following]
parked = at["scroll"]
fed(stream, view, 200, start=600)
at = frame(view)
tail["left_alone"] = [at["scroll"] == parked, at["limit"], view.following]
view.follow_tail()
frame(view)
at = frame(view)
tail["follow_tail"] = [at["scroll"], at["limit"], view.following]
frame(view, wheel=3.0)
frame(view)
for _ in range(40):
    frame(view, wheel=-5.0)
at = frame(view)
tail["wheeled_back"] = [at["scroll"], at["limit"], view.following]
view.scroll_to(0, align=0.0, always=True)
for _ in range(6):
    frame(view)
at = frame(view)
tail["scroll_to"] = [at["scroll"], at["limit"], view.following]
view.close()
stream, view, _ = fresh(follow=False)
fed(stream, view, 300)
at = frame(view)
tail["follow_off"] = [at["scroll"], at["limit"] > 100.0, view.following]
view.close()

# Not ready: the draw refuses, the stream is left for whoever draws instead, and
# when the fonts are back the view catches up.
stream, view, _ = fresh("One paragraph.")
typesetter.unload()
stream.append(" More of it.\n\nAnd another.")
try:
    frame(view)
    after = "drew"
except Exception as exc:
    after = type(exc).__name__
report["unloaded"] = [after, list(view.texts), typesetter.module() is not None]
report["load_again"] = typesetter.load_fonts()
out = frame(view)
made = [call for call in out["calls"] if call in EDITS]
report["caught_up"] = [list(view.texts), made, out["vertices"] > 0]

# Switched off for the run, with a document open (LAST: there is no way back): a sync
# is nothing and raises nothing, and the draw says to use the old view.
stream, view, _ = fresh("One paragraph.")
typesetter.disable("switched off by the test")
why = typesetter.reason()
stream.append("\n\nAnother one.")
try:
    synced = view.sync()
except Exception as exc:
    synced = type(exc).__name__
try:
    frame(view)
    drew = "drew"
except Exception as exc:
    drew = type(exc).__name__
report["switched_off"] = [synced, drew, list(view.texts), typesetter.reason() == why]
print("REPORT " + json.dumps(report))
"""
)


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
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use: " + str(
        got["reason"]
    )
    assert got["load_fonts"] is True and got["ready"] is True
    return got


_REPLAYS = [
    # Over an `imscribe.typeset_markdown.MarkdownStream`: no old-core object on the way.
    "sample 24 direct",
    "sample 5 direct",
    "tables 24 direct",
    "math 24 direct",
    # The same with a theme of its own for the unfinished tail: a block is set again at
    # its commit. (Added in tranche 5, when the old stream's `RESET` replay went.)
    "sample 5 direct reset",
]


@pytest.mark.parametrize("name", _REPLAYS)
def test_a_document_fed_in_pieces_ends_as_the_one_given_whole(
    headless: dict[str, Any], name: str
) -> None:
    """
    What the library copies for everything is what it copies for the whole
    document as the old core described it (frozen, and laid out by the
    library in the child), and for a `TypesetView` given the whole source at
    once; and each block in the library holds the text the view says it does.
    """
    told = headless["replays"][name]
    assert told["converter"] == "MarkdownConverter"
    assert told["material_edit_error"] == 0 and told["same_as_whole"] == [True, True]
    assert told["source"] is True and all(told["sources"])
    assert told["same_copy"] is True, told["copy_length"]
    assert told["copy_length"][0] > 1000
    assert told["same_texts"] is True and told["block_texts"] is True
    assert told["blocks"] == told["library_blocks"] > 10
    assert told["edit_error"] == 0 and told["trouble"] == ""
    assert told["no_vertices"] == 0


@pytest.mark.parametrize("name", _REPLAYS)
def test_a_change_of_the_stream_is_one_edit_and_no_change_is_none(
    headless: dict[str, Any], name: str
) -> None:
    """
    Counted at the ctypes library on every frame of the replay: at most one of
    `SetDocumentBlocks`, `ReplaceDocumentBlocks`, `AppendDocumentText`,
    `AppendDocumentTableCells` when the stream's revision changed, none when
    it did not, and the view's own `edits` agreeing with the calls. (No edit
    at all on a change where every new block describes as the old one did.)
    """
    told = headless["replays"][name]
    assert told["broken"] == []
    assert told["most_edits_in_a_sync"] == 1
    assert 0 < told["view_changes"] <= told["stream_changes"]
    edits = told["edits"]
    assert edits["set"] == 1  # the first draw; everything after is an edit
    assert edits["append"] + edits["replace"] == told["edit_calls"] <= told["view_changes"]
    assert edits["append"] > 0 and edits["replace"] > 0
    # Apart from the edit a frame is the three calls. (After a replace that
    # reaches the end the package asks how long the last block is, for its
    # own bookkeeping, as `tests/test_typeset_view.py` found.)
    # A table is a block of the document and asks nothing of its own.
    assert told["idle_calls"] == _FRAME
    for rest in told["other_calls"]:
        assert [call for call in rest if call != "GetDocumentBlockTextSize"] in (
            _FRAME,
            ["GetCurrentContext", "CreateDocument", "SetDocumentOptions", *_FRAME],
        ), rest


_TABLE_STREAMS = ["direct keep", "direct reset"]


@pytest.mark.parametrize("kind", _TABLE_STREAMS)
def test_a_table_being_written_is_appended_to_and_ends_as_the_one_given_whole(
    headless: dict[str, Any], kind: str
) -> None:
    """
    A table is a block of the library's, and a table that grows is appended
    to: a row that arrived whole is `AppendDocumentTableCells`, text that
    arrived in the last cell is `AppendDocumentText`, and anything else (a
    cell added to an unfinished row, the commit under reset) is one
    `ReplaceDocumentBlocks`. Never more than one edit a change, the library
    never switched off, and what is copied at the end is what the same
    source given whole copies.
    """
    assert headless["replays"]["sample 24 direct"]["live_table_syncs"] > 3
    assert headless["replays"]["tables 24 direct"]["live_table_syncs"] > 20
    table = headless["table"][kind]
    assert table["module"] is True and table["reason"] == "" and table["error"] == 0
    assert table["trouble"] == ""
    edits = (
        ["ReplaceDocumentBlocks"],
        ["AppendDocumentText"],
        ["AppendDocumentTableCells"],
    )
    for row in table["rows"]:
        assert row["made"] == [] or row["made"] in edits, row
    made = [row["made"] for row in table["rows"]]
    # The header and its delimiter make the table; each whole row after is an append of cells.
    assert made[1] == ["ReplaceDocumentBlocks"]
    assert made[2] == made[3] == ["AppendDocumentTableCells"] == made[6] == made[7]
    # `| 5 ` is a row of one cell and an empty one; `| 6 |` is text in that last cell.
    assert made[4] == ["AppendDocumentTableCells"] and made[5] == ["AppendDocumentText"]
    assert [row["rows"] for row in table["rows"][1:8]] == [1, 2, 3, 4, 4, 5, 6]
    assert table["texts"] == [
        "Before.",
        "a\tb\n1\t2\n3\t4\n5\t6\na much longer cell\t7\n8\t9",
        "",
        "After it.",
    ]
    assert table["same_texts"] is True and table["same_copy"] is True


@pytest.mark.parametrize("kind", _TABLE_STREAMS)
def test_a_live_table_holds_its_columns_and_the_policy_decides_at_the_commit(
    headless: dict[str, Any], kind: str
) -> None:
    """
    `StreamView`'s rule, which is the library's `TableHeld` flag: while the
    table is being written no column narrows, a column is as wide as the
    widest cell it has had (its natural width) and the table as wide as its
    columns, not the pane. At the commit a stream that keeps what it showed
    leaves the flag on for good; one that resets replaces the table once,
    without it, and the table is then the one a whole document has, column
    for column and row for row.
    """
    table = headless["table"][kind]
    keeps = kind.endswith("keep")
    assert table["keeps"] is keeps
    live = [row for row in table["rows"] if row.get("held")]
    assert len(live) >= 7
    for row in live:
        assert row["stated"] is True, row
        for width, natural in row["columns"]:
            assert width == pytest.approx(natural, abs=0.01), row
        assert row["width"] == pytest.approx(sum(w for w, _ in row["columns"]), abs=0.01)
    for before, after in zip(live, live[1:], strict=False):
        for (was, _), (now, _) in zip(before["columns"], after["columns"], strict=True):
            assert now >= was - 0.001, (before, after)
    # The long cell moved its own column and not the other.
    short, long = live[4]["columns"], live[5]["columns"]
    assert long[0][0] > short[0][0] + 50.0 and long[1][0] == pytest.approx(short[1][0], abs=0.01)
    final, whole = table["final"], table["whole"]
    assert whole["stated"] is False
    assert sum(width for width, _ in whole["columns"]) == pytest.approx(whole["pane"], abs=0.01)
    if keeps:
        assert final["held"] is True and final["stated"] is True
        assert final["columns"] == live[-1]["columns"]
        assert sum(width for width, _ in final["columns"]) < whole["pane"] / 2
    else:
        assert final["held"] is False and final["stated"] is False
        assert final["columns"] == whole["columns"] and final["row_tops"] == whole["row_tops"]
        # One replace took the flag off, on the frame the table committed.
        committed = [row for row in table["rows"] if "held" in row and not row["held"]]
        assert committed and committed[0]["made"] == ["ReplaceDocumentBlocks"]


@pytest.mark.parametrize("name", _REPLAYS)
def test_every_table_of_a_stream_is_held_under_keep_and_none_once_committed_under_reset(
    headless: dict[str, Any], name: str
) -> None:
    """
    Over whole demos. Under keep every table has the flag, however the stream
    was cut into frames (one that arrived and committed between two draws
    too), so a committed table is as wide as its columns want whenever that
    fits. Under reset none has it once the stream has closed, and each table
    is the whole document's, column for column.
    """
    told = headless["replays"][name]
    if not told["tables"]:
        return
    keeps = "reset" not in name
    assert told["held"] == [keeps] * len(told["tables"])
    assert told["whole_stated"] == [False] * len(told["tables"])
    if keeps:
        # Held, except where the held widths do not fit the pane: there the
        # library fits the table as any other (`stated` is then false).
        assert any(told["stated"])
        for stated, columns in zip(told["stated"], told["columns"], strict=True):
            if stated:
                assert all(width == pytest.approx(natural, abs=0.01) for width, natural in columns)
    else:
        assert told["stated"] == [False] * len(told["tables"])
        assert told["columns"] == told["whole_columns"]


def test_idle_frames_make_no_edit_and_a_burst_of_pieces_makes_one(
    headless: dict[str, Any],
) -> None:
    idle = headless["idle"]
    assert idle["first"][-3:] == _FRAME and "SetDocumentBlocks" in idle["first"]
    assert idle["idle"] == [_FRAME] * 3
    assert idle["burst"] == ["AppendDocumentText", *_FRAME]
    assert idle["edits"] == {"set": 1, "replace": 0, "append": 1}
    # The end of the line arrived: the stream's revision moved, and nothing else did. A
    # `MarkdownStream` hands back the very block it had when white space changed nothing
    # of it, so the view sees no change (0) and makes no call but the frame's three.
    # (Restated in tranche 5: the old `StreamDocument` built new block objects here, which
    # the view counted as a change of its blocks, 1, and then described as the same.)
    assert idle["white_space"] == [True, 0, _FRAME]


def test_a_selection_in_the_live_block_survives_text_arriving_after_it(
    headless: dict[str, Any],
) -> None:
    """
    The decision in `.concerns/lead--after-A2-decisions.md` item 1, and a
    little more: the same text is kept across a `replace_blocks` too.
    """
    selection, text, edits = headless["selection_kept"]
    assert selection == [[0, 5], [0, 10]] and text == "words"
    assert edits == {"set": 1, "replace": 0, "append": 2}
    selection, text, edits = headless["selection_over_a_commit"]
    assert selection == [[0, 5], [0, 10]] and text == "words"
    assert edits["replace"] == 1
    everything, length = headless["all"]
    assert everything == [[0, 0], [1, length]]
    assert "append to the stream" in headless["set_document"]
    assert "stream's theme" in headless["set_theme"]


def test_a_selection_whose_text_was_reinterpreted_is_dropped_whole(
    headless: dict[str, Any],
) -> None:
    """
    `StreamView` cuts such a selection back to the last unchanged block; this
    view drops it. One that ends before the markup is the same text and stays.
    """
    assert headless["unclosed"] == ["A **bol"]
    texts, selection, edits = headless["reinterpreted"]
    assert texts == ["A bold end"] and selection is None
    assert edits == {"set": 1, "replace": 1, "append": 0}
    assert headless["before_the_markup"] == [[[0, 0], [0, 2]], "A "]


def test_the_pane_follows_the_end_until_the_reader_scrolls_away(
    headless: dict[str, Any],
) -> None:
    tail = headless["tail"]
    scroll, limit, following = tail["followed"]
    assert limit > 400.0, "the document must have outgrown the window"
    assert scroll == limit and following is True
    scroll, limit, following = tail["wheeled_up"]
    assert scroll < limit - 50.0 and following is False
    stayed, limit_later, following = tail["left_alone"]
    assert stayed is True and limit_later > limit and following is False
    scroll, limit, following = tail["follow_tail"]
    assert scroll == limit and following is True
    scroll, limit, following = tail["wheeled_back"]
    assert scroll == limit and following is True
    # A `scroll_to` carried out on a frame is not overwritten by the tail.
    scroll, limit, following = tail["scroll_to"]
    assert scroll < 20.0 < limit and following is False
    scroll, outgrew, following = tail["follow_off"]
    assert scroll == 0.0 and outgrew is True and following is False
    for name in _REPLAYS:
        told = headless["replays"][name]
        scroll, limit, following = told["at_the_end"]
        assert scroll == limit > 0.0 and following is True, name


def test_while_the_library_is_not_ready_the_stream_is_not_read_and_then_it_catches_up(
    headless: dict[str, Any],
) -> None:
    refused, texts, module = headless["unloaded"]
    assert refused == "TypesetUnavailable" and module is True
    assert texts == ["One paragraph."]
    assert headless["load_again"] is True
    texts, made, drew = headless["caught_up"]
    assert texts == ["One paragraph. More of it.", "And another."]
    assert made == ["SetDocumentBlocks"] and drew is True


def test_once_the_library_is_switched_off_a_sync_is_nothing_and_raises_nothing(
    headless: dict[str, Any],
) -> None:
    """
    Found by the reviewer reading `TypesetView` (IT-R1 #1): an edit made after
    `typesetter.disable()` on a view with an open document raises
    `TypesetUnavailable` and rewrites the reason. `sync` is public, so it must
    not get there.
    """
    assert headless["switched_off"] == [False, "TypesetUnavailable", ["One paragraph."], True]


# ---------------------------------------------------------------------------
# 3. With the library, in a real window: vertices, and the times
# ---------------------------------------------------------------------------

_DRIVER = (
    r"""
import json, statistics, sys, time
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_stream_view import TypesetStreamView
"""
    + _COUNTING
    + r"""
ROOT = Path(sys.argv[1])
CHUNK = int(sys.argv[2])
REPEAT = int(sys.argv[3])

def loadavg():
    return ["%.2f" % x for x in __import__("os").getloadavg()]

source = (ROOT / "demo" / "sample.md").read_text(encoding="utf-8") * REPEAT
pieces = [source[at:at + CHUNK] for at in range(0, len(source), CHUNK)]
theme = Theme.build()
report = {"load_start": loadavg(), "pieces": len(pieces), "chunk": CHUNK, "repeat": REPEAT}
state = {"n": 0, "phase": 0, "at": 0, "stream": None, "view": None}
rows = {"typeset": []}

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    report["load_fonts"] = typesetter.load_fonts()

def pre_new_frame():
    if state["n"] == 0:
        imgui.get_io().add_mouse_pos_event(300.0, 740.0)   # off the view

def begin(phase):
    stream = MarkdownStream(theme, math=True)
    view = TypesetStreamView(stream, palette=DARK_PALETTE)
    state.update(stream=stream, view=view, at=0, phase=phase)

def finish(phase):
    stream, view = state["stream"], state["view"]
    told = report[phase] = {"blocks": len(stream.blocks), "following": view.following,
                            "scroll": [imgui.get_scroll_y(), imgui.get_scroll_max_y()]}
    told["edits"] = dict(view.edits)
    told["library_blocks"] = view.native_document.block_count
    told["trouble"] = typesetter.trouble()
    view.close()

def gui():
    state["n"] += 1
    if state["n"] == 1:
        ts = typesetter.module()
        report["module"] = ts is not None
        report["ready"] = typesetter.ready()
        report["reason"] = typesetter.reason()
        if ts is None or not typesetter.ready():
            hello_imgui.get_runner_params().app_shall_exit = True
            return
        report["load_before"] = loadavg()
        begin("typeset")
    phase = state["phase"]
    stream, view = state["stream"], state["view"]
    imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    flags = imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value
    imgui.begin("host", None, flags)
    # One child per phase, so the second starts at the top as the first did.
    imgui.begin_child(
        "##text-" + phase, imgui.ImVec2(0.0, 0.0),
        imgui.ChildFlags_.always_use_window_padding.value,
        imgui.WindowFlags_.always_vertical_scrollbar.value,
    )
    try:
        at = state["at"]
        new = at < len(pieces)
        if new:
            stream.append(pieces[at])
        elif at == len(pieces):
            stream.close()
        state["at"] = at + 1
        draw_list = imgui.get_window_draw_list()
        vertices = draw_list.vtx_buffer.size()
        began = time.perf_counter()
        _ = stream.revision          # the parse, timed apart from the draw
        parsed = time.perf_counter()
        view.draw(palette=DARK_PALETTE)
        drawn = time.perf_counter()
        rows[phase].append((new, parsed - began, drawn - parsed,
                            draw_list.vtx_buffer.size() - vertices))
        done = state["at"] >= len(pieces) + 40     # forty frames with nothing arriving
        if done:
            finish(phase)
    finally:
        imgui.end_child()
        imgui.end()
    if done:
        hello_imgui.get_runner_params().app_shall_exit = True

def before_exit():
    typesetter.unload()

runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "TypesetStreamView under test"
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

def us(values):
    return round(statistics.median(values) * 1e6, 1) if values else None

def worst(values):
    return round(max(values) * 1e6, 1) if values else None

timing = report["timing"] = {}
for phase, kept in rows.items():
    arriving = [row for row in kept if row[0]]
    idle = [row for row in kept if not row[0]][5:]
    # The later half as well: what a piece costs once the document is long.
    late = arriving[len(arriving) // 2:]
    timing[phase] = {
        "frames_with_new_text": len(arriving),
        "parse_median_us": us([row[1] for row in arriving]),
        "draw_median_us": us([row[2] for row in arriving]),
        "draw_late_half_median_us": us([row[2] for row in late]),
        "draw_max_us": worst([row[2] for row in arriving]),
        "draw_total_ms": round(sum(row[2] for row in arriving) * 1e3, 1),
        "idle_draw_median_us": us([row[2] for row in idle]),
        "frames_without_vertices": sum(1 for row in arriving[3:] if row[3] <= 0),
    }
report["load_end"] = loadavg()
print("REPORT " + json.dumps(report))
"""
)


@pytest.fixture(scope="module")
def windowed(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    script = window.out / "typeset_stream_view_driver.py"
    script.write_text(_DRIVER, encoding="utf-8")
    done = window.run([str(script), str(_ROOT), "24", "1"], timeout=300.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    # In the child, not here: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    return got


def test_in_a_real_window_the_stream_is_drawn_and_followed_to_its_end(
    windowed: dict[str, Any],
) -> None:
    """
    Vertices on the window's draw list on every frame that brought text (a
    Document with no font draws nothing and raises nothing), the 37 blocks
    of `demo/sample.md` in the stream and in the library, and the pane at
    its end.
    """
    typeset = windowed["typeset"]
    assert typeset["blocks"] == typeset["library_blocks"] == 37
    assert typeset["trouble"] == ""
    assert typeset["following"] is True and typeset["scroll"][0] == typeset["scroll"][1] > 500.0
    assert typeset["edits"]["set"] == 1
    assert typeset["edits"]["append"] > 0 and typeset["edits"]["replace"] > 0
    assert windowed["timing"]["typeset"]["frames_without_vertices"] == 0


def test_the_times_are_reported_and_not_judged(
    windowed: dict[str, Any],
) -> None:
    """Until tranche 5 `StreamView` was timed beside it over the same pieces; it is deleted."""
    timing = windowed["timing"]
    assert set(timing) == {"typeset"}
    assert timing["typeset"]["frames_with_new_text"] == windowed["pieces"]
    assert timing["typeset"]["draw_median_us"] > 0

r"""
A host's mistake is an error at the host's call: what a review of the host-request tranche found.

The principle (`.concerns/lead--PH-FIX.md`): a host's mistake is a
`TypeError` or a `ValueError` at the host's call, with the view unchanged.
It never leaves a view on a library document that does not match what the
view believes it holds, and it never switches the library off.

Each test here failed on the tree at `37c0a50`; `.concerns/PH-FIX-scripts/`
has the runs that showed how (`repro1.py`, `repro2.py`).

- **F1** a call into the library that raises something that is not the
  library's leaves no document, where it left an EMPTY one that drew blank
  under `texts` that still said there was text (and an edit left the old one
  under the new record).
- **F2** the description checks hold a value to what the package can pack;
  lists a host still holds are copied; `formulas` are checked; a table's
  columns, marks and inks are checked where they are handed over.
- **Surrogates** (the decision): text UTF-8 cannot hold is SET, each
  surrogate code point as U+FFFD, one for one, by every way into a view.
- **F3** `load_fonts` with what is no `Face` is a `TypeError` before anything
  is touched.
- **D1** a missing `imtypeset.demo` does not refuse the library.
- **S1** a stream's refused block raises at every `sync`, not once.

The first part needs no library. The children need it: `make test TYPESET=1`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from advtext import typesetter
from advtext.description import (
    FLOAT_MAX,
    INT_MAX,
    KIND_LIST_ITEM,
    KIND_TABLE,
    REPLACEMENT,
    BlockDescription,
    CellDescription,
    ColumnDescription,
    LinkRow,
    RunDescription,
    StyleDescription,
    check_description,
    check_runs,
    description_of,
    encodable,
    settled,
)
from advtext.typesetter import Kind

_ROOT = Path(__file__).resolve().parent.parent
_STYLE = StyleDescription()

# ---------------------------------------------------------------------------
# F2, without the library: what the package's pack cannot take is refused by the check
# ---------------------------------------------------------------------------


def _block(**fields: Any) -> BlockDescription:
    return BlockDescription(text="abc", **fields)


def _run(**fields: Any) -> BlockDescription:
    return _block(runs=(RunDescription(0, 1, **fields),))


def _table(column: ColumnDescription) -> BlockDescription:
    return BlockDescription(
        kind=KIND_TABLE, text="a", rows=((CellDescription("a"),),), columns=(column,)
    )


_UNPACKABLE: list[tuple[str, BlockDescription, StyleDescription]] = [
    ("run tag 2**31", _run(tag=2**31), _STYLE),
    ("run flags 2**31", _run(flags=2**31), _STYLE),
    ("run scale 1e39", _run(scale=1e39), _STYLE),
    ("run scale 10**400", _run(scale=10**400), _STYLE),
    ("block quote_depth 2**31", _block(quote_depth=2**31), _STYLE),
    ("block container 2**31", _block(container=2**31), _STYLE),
    ("block item 2**31", _block(item=2**31), _STYLE),
    ("block level 2**31", _block(level=2**31), _STYLE),
    ("block flags 2**31", _block(flags=2**31), _STYLE),
    ("block left_indent 1e39", _block(left_indent=1e39), _STYLE),
    ("block left_indent 10**400", _block(left_indent=10**400), _STYLE),
    ("block extent 1e39", _block(extent=1e39), _STYLE),
    ("column width 1e39", _table(ColumnDescription(1, 1e39)), _STYLE),
    ("column share 10**400", _table(ColumnDescription(1, 0.0, 10**400)), _STYLE),
    ("style Scale 1e39", _block(), StyleDescription(Scale=1e39)),
    ("style LineHeight 1e39", _block(), StyleDescription(LineHeight=1e39)),
    ("style FirstLineIndent -1e39", _block(), StyleDescription(FirstLineIndent=-1e39)),
    ("style SpaceAbove 10**400", _block(), StyleDescription(SpaceAbove=10**400)),
    ("style SpaceBelow 1e39", _block(), StyleDescription(SpaceBelow=1e39)),
    ("style MarkerGap 1e39", _block(), StyleDescription(MarkerGap=1e39)),
]


@pytest.mark.parametrize(("block", "style"), [row[1:] for row in _UNPACKABLE], ids=lambda v: None)
def test_a_value_the_package_cannot_pack_is_refused_by_the_check(
    block: BlockDescription, style: StyleDescription
) -> None:
    with pytest.raises((TypeError, ValueError)) as told:
        description_of([block], [style])
    assert len(str(told.value)) < 400, "a number of 400 digits was written out"


def test_the_most_each_field_holds_is_still_taken() -> None:
    block = BlockDescription(
        text="abc",
        runs=(RunDescription(0, 1, scale=FLOAT_MAX, color=0xFFFFFFFF, flags=INT_MAX, tag=INT_MAX),),
        left_indent=FLOAT_MAX,
        quote_depth=INT_MAX,
        container=INT_MAX,
        item=INT_MAX,
        extent=FLOAT_MAX,
        flags=INT_MAX,
        level=INT_MAX,
    )
    style = StyleDescription(Scale=FLOAT_MAX, SpaceAbove=FLOAT_MAX, FirstLineIndent=-FLOAT_MAX)
    made = description_of([block], [style], [LinkRow(0, 0, 1, INT_MAX, "u")])
    assert made.blocks == [block]
    with pytest.raises(ValueError, match="tag"):
        description_of([block], [style], [LinkRow(0, 0, 1, INT_MAX + 1, "u")])
    with pytest.raises(ValueError, match="at most"):
        check_runs((RunDescription(0, 1, tag=INT_MAX + 1),), 3, "here")


def test_text_utf8_cannot_hold_passes_the_check_and_is_made_encodable() -> None:
    """The decision: a view sets it as U+FFFD; the check does not refuse it."""
    block = BlockDescription(kind=KIND_LIST_ITEM, text="ab\udc80c", marker="\ud800")
    table = BlockDescription(
        kind=KIND_TABLE, text="\udcff\tb", rows=[[CellDescription("\udcff"), CellDescription("b")]]
    )
    check_description(description_of([block, table], [_STYLE]))
    assert encodable("plain") == "plain"
    text = "café → ok"
    assert encodable(text) is text, "nothing to replace: the same object"
    assert encodable("a\udc80b\udfff") == f"a{REPLACEMENT}b{REPLACEMENT}"
    for one in (settled(block), settled(table)):
        for text in (one.text, one.marker, *(cell.text for row in one.rows for cell in row)):
            text.encode("utf-8")
    assert settled(block).text == f"ab{REPLACEMENT}c" and len(settled(block).text) == 4
    assert settled(table).text == f"{REPLACEMENT}\tb", "a table's text is still its cells'"


def test_settled_copies_what_a_host_may_still_hold_and_nothing_else() -> None:
    plain = BlockDescription(text="abc", runs=(RunDescription(0, 1),))
    assert settled(plain) is plain
    table = BlockDescription(
        kind=KIND_TABLE,
        text="a\tb",
        rows=((CellDescription("a"), CellDescription("b")),),
        columns=(ColumnDescription(),),
    )
    assert settled(table) is table
    runs, cell_runs = [RunDescription(0, 1)], [RunDescription(0, 1)]
    rows = [[CellDescription("a", cell_runs)]]
    columns = [ColumnDescription()]
    held = BlockDescription(kind=KIND_TABLE, text="a", runs=runs, rows=rows, columns=columns)
    kept = settled(held)
    for mutable in (runs, cell_runs, columns):
        mutable.append(mutable[0])
    rows.append([])
    assert kept.runs == (RunDescription(0, 1),)
    assert kept.rows == ((CellDescription("a", (RunDescription(0, 1),)),),)
    assert kept.columns == (ColumnDescription(),)


# ---------------------------------------------------------------------------
# F3, D1, S3, without the library
# ---------------------------------------------------------------------------

_STATE = ("_ts", "_package", "_tried", "_reason", "_why", "_disabled", "_ready", "_home")


@pytest.fixture
def untouched(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A library that fails the test when anything is asked of it, in use and ready."""

    class Library:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"the library was asked for {name}")

    kept = {name: getattr(typesetter, name) for name in _STATE}
    library = Library()
    typesetter._ts, typesetter._ready, typesetter._reason = library, True, ""
    typesetter._home, typesetter._disabled = None, False
    yield library
    for name, value in kept.items():
        setattr(typesetter, name, value)


@pytest.mark.parametrize(
    "faces", [["prose"], "prose", ("PROSE", 1), [None], 5], ids=lambda value: repr(value)
)
def test_load_fonts_with_what_is_no_face_is_a_type_error_and_touches_nothing(
    untouched: Any, faces: Any
) -> None:
    with pytest.raises(TypeError, match="Face"):
        typesetter.load_fonts(faces)
    assert typesetter.ready(), "ready() was cleared for a typo"
    assert typesetter.module() is untouched and typesetter.kind() is Kind.READY


def test_one_face_is_not_an_iterable_of_faces(untouched: Any) -> None:
    from advtext import Face

    with pytest.raises(TypeError, match="iterable"):
        typesetter.load_fonts(Face.PROSE)  # type: ignore[arg-type]
    assert typesetter.ready()


def test_a_package_without_its_demo_is_not_refused() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import test_typesetter_pairing as pairing
    finally:
        sys.path.pop(0)
    package = types.ModuleType("imtypeset_without_a_demo")
    package.__file__ = "/somewhere/site/imtypeset/__init__.py"
    exec(pairing.standin(), package.__dict__)  # noqa: S102
    assert not hasattr(package, "demo")
    assert typesetter.missing(package) == []


def test_the_selection_colour_is_a_field_the_gate_asks_for() -> None:
    assert "SelectionColor" in typesetter.REQUIRED["Style"]
    package = types.ModuleType("imtypeset_old_style")

    class Style:
        EmSize = PixelsPerInch = Color = Spacing = 0

    package.Style = Style  # type: ignore[attr-defined]
    assert "Style.SelectionColor" in typesetter.missing(package)


def test_verdict_reads_its_answer_under_whatever_is_written_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shared library's C stdio is flushed at exit, after Python's line, when it is a pipe."""
    answer = dict.fromkeys(typesetter._PAIRING_KEYS)
    answer.update(route="environment", reason="", kind="ready", library="/x/lib.so")
    out = "a line before\n" + json.dumps(answer) + "\nlibrary: 3 documents freed\n{not json\n"

    def run(*args: Any, **kwargs: Any) -> Any:
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    said = typesetter.verdict()
    assert said["kind"] == "ready" and said["library"] == "/x/lib.so"


def test_the_clipboard_is_never_handed_a_surrogate() -> None:
    from advtext.ui.ownership import clipboard_text

    assert clipboard_text("a\udc80b") == f"a{REPLACEMENT}b"
    clipboard_text("a\udc80b").encode("utf-8")
    same = "plain → text"
    assert clipboard_text(same) is same


def test_the_diff_view_shows_a_surrogate_as_its_placeholder() -> None:
    from advtext.ui.typeset_diff_view import CONTROL_PLACEHOLDER, _shown

    shown, marked = _shown("two \udc80 bytes")
    assert shown == f"two {CONTROL_PLACEHOLDER} bytes" and marked == (4,)
    shown.encode("utf-8")


# ---------------------------------------------------------------------------
# With the library
# ---------------------------------------------------------------------------

_CHILD = r"""
import dataclasses, json, struct, sys
from imgui_bundle import imgui
from advtext import Face, typesetter
from advtext.description import (
    KIND_LIST_ITEM, KIND_TABLE, BlockDescription, CellDescription, ColumnDescription,
    Description, RunDescription, StyleDescription, description_of,
)
from advtext.diff import Diff
from advtext.theme import BlockKind, Theme
from advtext.typeset_markdown import (
    FormulaRange, MarkdownCell, MarkdownCode, MarkdownRule, MarkdownStream, MarkdownTable,
    MarkdownText, parse_markdown,
)
from advtext.ui.typeset_diff_view import TypesetDiffView
from advtext.ui.typeset_stream_view import TypesetStreamView
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView
import collections

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)
report = {"module": True}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
io.set_ini_filename("")
report["load"] = typesetter.load_fonts()
theme = Theme.build()
para, code = theme.style(BlockKind.PARAGRAPH), theme.style(BlockKind.CODE)
STYLE = StyleDescription()
REPLACEMENT = "�"

def frame(view, **more):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        before = imgui.get_window_draw_list().vtx_buffer.size()
        view.draw(**more)
        return imgui.get_window_draw_list().vtx_buffer.size() - before
    except Exception as exc:
        return type(exc).__name__
    finally:
        imgui.end()
        imgui.render()

def attempt(call):
    try:
        call()
        return "accepted"
    except Exception as exc:
        return type(exc).__name__

def state():
    return [typesetter.kind().value, typesetter.ready(), typesetter.reason()]

def held(view):
    # Whether the library's document holds what the view says it does.
    doc = view.native_document
    if doc is None:
        return None
    texts = list(view.texts)
    return len(doc) == len(texts) and all(
        doc.range_text(((at, 0), (at, len(text)))) == text.rstrip("\r\n")
        for at, text in enumerate(texts) if at not in view.tables and at not in view.hosts)

GOOD = "Good words here.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"

def shown(document=GOOD, **more):
    view = TypesetView(document, theme=theme, **more)
    return view, frame(view)

class Raising:
    # A method of the package's Document that raises a built-in error while it is in place.
    def __init__(self, name, exc):
        self.name, self.exc, self.real = name, exc, getattr(ts.Document, name)
    def __enter__(self):
        exc = self.exc
        def raises(*args, **kwargs):
            raise exc
        setattr(ts.Document, self.name, raises)
    def __exit__(self, *rest):
        setattr(ts.Document, self.name, self.real)

# -- F1: the document is made whole or not kept --------------------------------
view = TypesetView(GOOD, theme=theme)
with Raising("set_blocks", OverflowError("float too large to pack with f format")):
    first = frame(view)
    native = view.native_document is None
    second = frame(view)
third = frame(view)
report["made"] = {"first": first, "no_document": native, "second": second, "third": third,
                  "held": held(view), "texts": list(view.texts), "state": state(),
                  "edits": dict(view.edits)}

view, drew = shown()
with Raising("replace_blocks", struct.error("'i' format requires -2147483648 <= number")):
    said = attempt(lambda: view.set_document("Other words now.\n\nAnd a second paragraph.\n"))
    native = view.native_document is None
after = frame(view)
report["edited"] = {"drew": drew, "said": said, "no_document": native, "after": after,
                    "held": held(view), "texts": list(view.texts), "state": state()}

view, drew = shown()
roles = dataclasses.replace(view.palette, roles=((BlockKind.PARAGRAPH, 0xFF00FF00),))
with Raising("set_blocks", UnicodeEncodeError("utf-8", "\udc80", 0, 1, "surrogates not allowed")):
    said = attempt(lambda: view.set_palette(roles))
    native = view.native_document is None
after = frame(view)
report["recoloured"] = {"drew": drew, "said": said, "no_document": native, "after": after,
                        "held": held(view), "state": state()}

stream = MarkdownStream(theme)
stream.append("A first paragraph that is being written")
live = TypesetStreamView(stream)
drew = frame(live)
stream.append(" and goes on")
with Raising("append_text", OverflowError("simulated")):
    said = attempt(live.sync)
    native = live.native_document is None
stream.append(" and on.")
after = frame(live)
report["streamed"] = {"drew": drew, "said": said, "no_document": native, "after": after,
                      "held": held(live), "texts": list(live.texts), "state": state()}

# -- F2: a description that cannot be packed is refused at the call, the view as it was --
def raw(blocks, styles=(STYLE,)):
    blocks = list(blocks)
    return Description(blocks, list(styles), [],
                       [at for at, b in enumerate(blocks) if b.kind == KIND_TABLE],
                       [b.text for b in blocks], collections.Counter(), collections.Counter())

def block(**fields):
    return BlockDescription(text="abc", **fields)

def table(column):
    return BlockDescription(kind=KIND_TABLE, text="a", rows=((CellDescription("a"),),),
                            columns=(column,))

BAD = {
    "run tag 2**31": raw([block(runs=(RunDescription(0, 1, tag=2**31),))]),
    "run flags 2**31": raw([block(runs=(RunDescription(0, 1, flags=2**31),))]),
    "run scale 1e39": raw([block(runs=(RunDescription(0, 1, scale=1e39),))]),
    "quote_depth 2**31": raw([block(quote_depth=2**31)]),
    "container 2**31": raw([block(container=2**31)]),
    "item 2**31": raw([block(item=2**31)]),
    "level 2**31": raw([block(level=2**31)]),
    "flags 2**31": raw([block(flags=2**31)]),
    "left_indent 1e39": raw([block(left_indent=1e39)]),
    "left_indent 10**400": raw([block(left_indent=10**400)]),
    "extent 1e39": raw([block(extent=1e39)]),
    "column width 1e39": raw([table(ColumnDescription(1, 1e39))]),
    "style Scale 1e39": raw([block()], [StyleDescription(Scale=1e39)]),
    "style SpaceAbove 10**400": raw([block()], [StyleDescription(SpaceAbove=10**400)]),
}
report["descriptions"] = {}
for label, description in BAD.items():
    view, drew = shown()
    texts = list(view.texts)
    said = attempt(lambda: view.set_document(description))
    report["descriptions"][label] = [said, list(view.texts) == texts, frame(view) == drew,
                                     held(view), state()]

# -- Surrogates: set as U+FFFD by every way in ---------------------------------
BYTES = "tool \udc80 output"
class Box:
    text = "a widget \udcff says"
    def height_for(self, width_px):
        return 40.0
    def draw(self, *, palette=None, width_px=None):
        imgui.dummy(imgui.ImVec2(width_px or 10.0, 40.0))

ways = {
    "str": lambda: TypesetView(BYTES, theme=theme),
    "MarkdownText": lambda: TypesetView(
        [MarkdownText(BlockKind.PARAGRAPH, para, BYTES)], theme=theme),
    "MarkdownCode": lambda: TypesetView([MarkdownCode(code, BYTES)], theme=theme),
    "marker": lambda: TypesetView(
        [MarkdownText(BlockKind.BULLET_ITEM, theme.style(BlockKind.BULLET_ITEM), BYTES,
                      marker="\ud800")],
        theme=theme),
    "table": lambda: TypesetView(
        [MarkdownTable(para, (), ((MarkdownCell(BYTES), MarkdownCell("b")),), ())], theme=theme),
    "Description": lambda: TypesetView(
        raw([BlockDescription(text=BYTES),
             BlockDescription(kind=KIND_TABLE, text="\udc80\tb",
                              rows=((CellDescription("\udc80"), CellDescription("b")),))]),
        theme=theme),
    "hosted": lambda: TypesetView([MarkdownCode(code, "x")], theme=theme,
                                  host_for=lambda view, at, block: Box()),
}
report["surrogates"] = {}
for label, make in ways.items():
    try:
        view = make()
    except Exception as exc:
        report["surrogates"][label] = [type(exc).__name__ + ": " + str(exc)[:200]]
        continue
    first = frame(view)
    view.select_all()
    copied = attempt(view.copy)
    text = view.selected_text()
    report["surrogates"][label] = [
        first, frame(view), list(view.texts), held(view),
        REPLACEMENT in text, any("\ud800" <= ch <= "\udfff" for ch in text), copied, state()]
view = TypesetView(BYTES, theme=theme)
report["source_kept"] = view.source == BYTES
frame(view)
report["edited_to_bytes"] = [attempt(lambda: view.set_document("now \udc81 other bytes")),
                             frame(view), list(view.texts), held(view)]
stream = MarkdownStream(theme)
live = TypesetStreamView(stream)
stream.append("streamed \udc80")
first = frame(live)
stream.append(" bytes \udc81 arrive")
report["stream_bytes"] = [first, frame(live), list(live.texts), held(live), dict(live.edits)]

# -- A list a host goes on appending to ---------------------------------------
runs = [RunDescription(0, 1)]
view = TypesetView(description_of([BlockDescription(text="abc", runs=runs)], [STYLE]), theme=theme)
first = frame(view)
runs.append(RunDescription(1, 2, tag=2**40))
view.close()
report["kept_list"] = [first, frame(view), held(view), state()]

# -- formulas ------------------------------------------------------------------
report["formulas"] = {}
cases = {
    "text str": [MarkdownText(BlockKind.PARAGRAPH, para, "abc", formulas=("x",))],
    "text not a tuple": [MarkdownText(BlockKind.PARAGRAPH, para, "abc", formulas=5)],
    "text outside": [MarkdownText(BlockKind.PARAGRAPH, para, "abc",
                                  formulas=(FormulaRange(0, 9, "x"),))],
    "cell str": [MarkdownTable(para, (), ((MarkdownCell("a", formulas=("x",)),),), ())],
}
for label, document in cases.items():
    view, drew = shown()
    said = attempt(lambda: view.set_document(document))
    report["formulas"][label] = [said, view.source == GOOD, frame(view) == drew, held(view)]
view, drew = shown()
fine = [MarkdownText(BlockKind.PARAGRAPH, para, "a x b", formulas=(FormulaRange(2, 3, "x"),))]
report["formula_taken"] = [attempt(lambda: view.set_document(fine)), frame(view)]

# -- a table's columns ---------------------------------------------------------
report["columns"] = {}
columns = {"nan": [float("nan"), 80.0], "inf": [float("inf"), 80.0], "1e39": [1e39, 80.0],
           "-5": [-5.0, 80.0], "10**400": [10**400, 80], "True": [True, 80.0],
           "align 99": [(99, 50.0, 0.0), (1, 50.0, 0.0)], "share nan": [(1, 0.0, float("nan"))] * 2,
           "words": [(1, "wide")]}
for label, given in columns.items():
    view, drew = shown()
    said = attempt(lambda: view.set_table_columns(1, given))
    now = frame(view)
    view.close()
    report["columns"][label] = [said, now == drew, frame(view) == drew, held(view), state()]
view, drew = shown()
report["columns_taken"] = [view.set_table_columns(1, [120, 80.0]), frame(view),
                           view.set_table_columns(1, [(1, 0.0, 2), (3, 0.0, 1)]), frame(view),
                           held(view)]

# -- marks and inks ------------------------------------------------------------
report["marks"] = {}
marks = {"colour -1": [(((0, 0), (0, 3)), -1)], "colour 2**32": [(((0, 0), (0, 3)), 2**32)],
         "place 2**31": [(((0, 0), (0, 3)), 1, 2**31)],
         "thickness 1e39": [(((0, 0), (0, 3)), 1, 0, 1e39)],
         "offset nan": [(((0, 0), (0, 3)), 1, 0, 1.0, float("nan"))],
         "block 2**31": [(((2**31, 0), (0, 3)), 1)]}
good_mark = [(((0, 0), (0, 4)), 0xFF00FFFF)]
for label, given in marks.items():
    view, drew = shown()
    view.set_marks(good_mark)
    marked = frame(view)
    said = attempt(lambda: view.set_marks(given))
    report["marks"][label] = [said, isinstance(marked, int), frame(view) == marked, state()]
report["inks"] = {}
for label, given in {"colour -1": [(0, 3, -1)], "colour 2**32": [(0, 3, 2**32)]}.items():
    view, drew = shown()
    view.set_colours(0, [(0, 4, 0xFF00FFFF)])
    inked = frame(view)
    said = attempt(lambda: view.set_colours(0, given))
    report["inks"][label] = [said, isinstance(inked, int), frame(view) == inked, state()]
view, drew = shown()
full = [(((0, 0), (0, 3)), 0xFFFFFFFF, 0, 1.0, 0.0)]
report["marks_taken"] = [attempt(lambda: view.set_marks(full)),
                         attempt(lambda: view.set_marks([(((9, 0), (9, 3)), 1)])),
                         attempt(lambda: view.set_colours(0, [(0, 3, 0xFFFFFFFF), (-5, 2, 0)])),
                         isinstance(frame(view), int)]

# -- F3: load_fonts with what is no Face ---------------------------------------
view, drew = shown()
open_before = view.native_document is not None
said = attempt(lambda: typesetter.load_fonts(["prose"]))
report["load_fonts"] = [said, state(), open_before, view.native_document is not None,
                        frame(view) == drew, dict(view.edits)]

# -- S1: a stream's refused block ----------------------------------------------
class Stream:
    revision = 1
    def __init__(self):
        self.theme = theme
        self.blocks = tuple(parse_markdown("One.\n\nTwo.", theme).blocks)
        self.committed = self.blocks
stream = Stream()
live = TypesetStreamView(stream)
drew = frame(live)
good = stream.blocks
stream.blocks, stream.revision = good + ("junk",), 2
said = [attempt(live.sync), attempt(live.sync), frame(live)]
stream.blocks, stream.revision = good + (MarkdownCode(code, "three"),), 3
report["sync"] = [said, attempt(live.sync), frame(live), list(live.texts), held(live), state()]

# -- the diff view --------------------------------------------------------------
texts = ("one\ntwo \udc80 bytes\n", "one\ntwo bytes\n")
diff = TypesetDiffView(Diff.from_texts(*texts, "f.py"), theme)
named = TypesetDiffView(Diff.from_texts("one\ntwo\n", "one\n2\n", "f\udc80.py"), theme)
report["diff"] = [frame(diff), frame(diff), attempt(diff.headers),
                  frame(named), attempt(named.headers), state()]

# -- every field of a block a host makes, given something it is not ------------
ODD = ["x", None, -1, 2**31, 1e39, float("nan"), float("inf"), 10**400, True, (), [1], b"b", 3.5,
       "\udc80", ("x",), (1, 2, 3), object]
parsed = parse_markdown("words\n\n---\n\n| h |\n|---|\n| a |\n", theme).blocks
made = {
    "MarkdownText": MarkdownText(BlockKind.PARAGRAPH, para, "abc def"),
    "MarkdownCode": MarkdownCode(code, "abc def"),
    "MarkdownRule": parsed[1],
    "MarkdownTable": parsed[2],
    "MarkdownCell": MarkdownCell("a"),
}
assert [type(one).__name__ for one in parsed[1:]] == ["MarkdownRule", "MarkdownTable"]
fuzz = {"tried": 0, "accepted": 0, "refused": 0, "wrong": []}
for name, good in made.items():
    for field in dataclasses.fields(good):
        for odd in ODD:
            try:
                bad = dataclasses.replace(good, **{field.name: odd})
            except Exception:
                continue
            document = [bad] if name != "MarkdownCell" else [MarkdownTable(para, (), ((bad,),), ())]
            view, drew = shown()
            texts = list(view.texts)
            fuzz["tried"] += 1
            try:
                view.set_document(document)
                called = "accepted"
            except (TypeError, ValueError):
                called = "refused"
            except Exception as exc:
                called = type(exc).__name__
            frames = [frame(view), frame(view)]
            ok = (called == "refused" and list(view.texts) == texts and frames == [drew, drew]) or (
                called == "accepted" and all(isinstance(one, int) for one in frames)
                and held(view) is True)
            if ok and state() == ["ready", True, ""]:
                fuzz[called] += 1
            else:
                fuzz["wrong"].append([name, field.name, repr(odd)[:30], called, frames, state()])
                typesetter.reset()
                typesetter.load_fonts()
report["fuzz"] = fuzz
report["end"] = state()
typesetter.unload()
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def told() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    pytest.importorskip("imgui_bundle")
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr[-4000:]}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["module"] is True and report["load"] is True, report.get("reason")
    return report


_READY = ["ready", True, ""]


def test_a_document_that_did_not_take_its_blocks_is_not_kept(told: dict[str, Any]) -> None:
    """F1. It was kept, empty: frame 2 drew nothing under `texts` that said there was text."""
    made = told["made"]
    assert made["first"] == "OverflowError" and made["no_document"] is True
    assert made["second"] == "OverflowError", "the second frame drew a blank document"
    assert isinstance(made["third"], int) and made["third"] > 0
    assert made["held"] is True and len(made["texts"]) == 2
    assert made["state"] == _READY and made["edits"]["set"] == 1


def test_an_edit_that_raises_leaves_no_document_behind_the_record(told: dict[str, Any]) -> None:
    """F1, the edit path: the old document stayed under the new `texts`."""
    edited = told["edited"]
    assert edited["said"] == "error", "struct.error, as itself"
    assert edited["no_document"] is True
    assert isinstance(edited["after"], int) and edited["after"] > 0
    assert edited["held"] is True
    assert edited["texts"] == ["Other words now.", "And a second paragraph."]
    assert edited["state"] == _READY


def test_a_palette_s_roles_and_a_stream_s_append_likewise(told: dict[str, Any]) -> None:
    for name, raised in (("recoloured", "UnicodeEncodeError"), ("streamed", "OverflowError")):
        got = told[name]
        assert got["said"] == raised and got["no_document"] is True, name
        assert isinstance(got["after"], int) and got["after"] > 0, name
        assert got["held"] is True and got["state"] == _READY, name
    assert told["streamed"]["texts"] == [
        "A first paragraph that is being written and goes on and on."
    ]


def test_a_description_the_package_cannot_pack_is_refused_at_the_call(
    told: dict[str, Any],
) -> None:
    """F2. Each of these passed `check_description` and raised from the first draw."""
    assert len(told["descriptions"]) == 14
    for label, (said, same_texts, same_frame, held, state) in told["descriptions"].items():
        assert said in ("TypeError", "ValueError"), (label, said)
        assert same_texts and same_frame and held is True, label
        assert state == _READY, label


def test_text_utf8_cannot_hold_is_set_as_the_replacement_character(told: dict[str, Any]) -> None:
    """
    The decision on lone surrogates. Each way in raised `UnicodeEncodeError`:
    at the call for a view with a document, at every draw for one without.
    """
    assert sorted(told["surrogates"]) == sorted(
        ["str", "MarkdownText", "MarkdownCode", "marker", "table", "Description", "hosted"]
    )
    for label, got in told["surrogates"].items():
        assert len(got) == 8, (label, got)
        first, second, texts, held, replaced, surrogate, copied, state = got
        assert isinstance(first, int) and isinstance(second, int), (label, got)
        assert first > 0 or label == "hosted", "a hosted block's text is the widget's to draw"
        assert not any("\ud800" <= ch <= "\udfff" for text in texts for ch in text), label
        assert held is True and state == _READY, label
        assert not surrogate and copied == "accepted", label
        if label != "marker":
            assert any(REPLACEMENT in text for text in texts), label
    assert told["surrogates"]["str"][2] == [f"tool {REPLACEMENT} output"], "one for one"
    assert told["source_kept"] is True, "the host's source is its own"
    said, drew, texts, held = told["edited_to_bytes"]
    assert said == "accepted" and isinstance(drew, int) and held is True
    assert texts == [f"now {REPLACEMENT} other bytes"]
    first, second, texts, held, edits = told["stream_bytes"]
    assert isinstance(first, int) and isinstance(second, int) and held is True
    assert texts == [f"streamed {REPLACEMENT} bytes {REPLACEMENT} arrive"]
    assert edits["append"] == 1, "a stream of such text is still appended to"


def test_a_list_the_host_goes_on_appending_to_does_not_change_the_view(
    told: dict[str, Any],
) -> None:
    first, again, held, state = told["kept_list"]
    assert isinstance(first, int) and again == first and held is True and state == _READY


def test_formulas_are_checked_before_the_view_is_touched(told: dict[str, Any]) -> None:
    assert told["formulas"]["text str"][0] == "TypeError", "AttributeError out of the converter"
    assert told["formulas"]["text not a tuple"][0] == "TypeError"
    assert told["formulas"]["text outside"][0] == "ValueError"
    assert told["formulas"]["cell str"][0] == "TypeError"
    for label, (_said, source_kept, same_frame, held) in told["formulas"].items():
        assert source_kept and same_frame and held is True, label
    assert told["formula_taken"][0] == "accepted" and isinstance(told["formula_taken"][1], int)


def test_a_table_s_columns_are_checked_where_they_are_handed_over(told: dict[str, Any]) -> None:
    """`1e39` was kept in the description and raised from every later rebuild."""
    wrong_type = {"True", "words"}
    assert len(told["columns"]) == 9
    for label, (said, same, same_after_close, held, state) in told["columns"].items():
        assert said == ("TypeError" if label in wrong_type else "ValueError"), (label, said)
        assert same and same_after_close and held is True and state == _READY, label
    widths, drew, shares, drew_shares, held = told["columns_taken"]
    assert widths is True and shares is True and held is True
    assert isinstance(drew, int) and isinstance(drew_shares, int)


def test_marks_and_inks_the_struct_cannot_hold_are_refused_at_the_call(
    told: dict[str, Any],
) -> None:
    """A colour of -1 was kept and raised `struct.error` from every draw."""
    assert len(told["marks"]) == 6 and len(told["inks"]) == 2
    for name in ("marks", "inks"):
        for label, (said, drew, same, state) in told[name].items():
            assert said == "ValueError", (name, label, said)
            assert drew and same and state == _READY, (name, label)
    assert told["marks_taken"] == ["accepted", "accepted", "accepted", True]


def test_load_fonts_with_a_typo_closes_nothing_and_switches_nothing_off(
    told: dict[str, Any],
) -> None:
    """F3. It closed every document and left `kind()` FAILED."""
    said, state, open_before, open_after, same, edits = told["load_fonts"]
    assert said == "TypeError" and state == _READY
    assert open_before and open_after and same and edits["set"] == 1


def test_a_stream_s_refused_block_is_said_at_every_sync(told: dict[str, Any]) -> None:
    """S1. It raised once; every later sync answered False over the older blocks."""
    (first, again, drawn), then, frame, texts, held, state = told["sync"]
    assert first == "TypeError" and again == "TypeError" and drawn == "TypeError"
    assert then == "accepted" and isinstance(frame, int)
    assert texts == ["One.", "Two.", "three"] and held is True and state == _READY


def test_the_diff_view_draws_a_line_and_a_name_with_undecodable_bytes(
    told: dict[str, Any],
) -> None:
    first, second, headers, named, named_headers, state = told["diff"]
    assert isinstance(first, int) and first == second and first > 0
    assert headers == "accepted" and named_headers == "accepted"
    assert isinstance(named, int) and named > 0 and state == _READY


def test_no_field_of_a_host_s_block_can_be_given_what_breaks_the_view(
    told: dict[str, Any],
) -> None:
    """
    Every field of the four blocks and of a cell, given seventeen things it is
    not: refused with `TypeError` or `ValueError` and the view as it was, or
    taken and drawn with the library's document holding the view's texts.
    Never another exception, a blank view, or a library switched off.
    """
    fuzz = told["fuzz"]
    assert fuzz["wrong"] == [], fuzz["wrong"][:12]
    assert fuzz["tried"] == fuzz["accepted"] + fuzz["refused"] and fuzz["refused"] > 100
    assert told["end"] == _READY

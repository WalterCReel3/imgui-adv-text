r"""
A lone surrogate never raises out of a view's `draw`; a host can read that one was set (P38, P41).

pptmstr's P38: `json.loads('"\\udc80"')` is a `str` holding a surrogate code
point, which UTF-8 cannot hold; it reported `UnicodeEncodeError` out of
`TypesetView.draw` and `TypesetDiffView.draw`. A review found, by reading,
that every way to the library goes through `imscribe.description.settled`
(the text views), `_shown_slowly` (the diff view) or `clipboard_text` (a
copy). R3-TEXT ran it: on `35b7f77` nothing here raised, so these tests are
what shows P38 closed.

P41: a host could not tell that a character had been set as U+FFFD.
`TypesetView.replaced_characters` (and so `TypesetStreamView`'s) counts the
characters of the document on show that were; `TypesetDiffView` has the same
name over its diff.

The first part needs no library. The child needs it: `make test TYPESET=1`,
or an installed imtypeset. No window: frames are made in a bare context.
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
    KIND_TABLE,
    BlockDescription,
    CellDescription,
    unencodable_count,
)

_ROOT = Path(__file__).resolve().parent.parent

LONE = json.loads('"\\udc80"')


def test_json_gives_a_lone_surrogate() -> None:
    """The premise of P38, as pptmstr met it."""
    assert LONE == "\udc80"
    with pytest.raises(UnicodeEncodeError):
        LONE.encode("utf-8")


def test_unencodable_count_counts_every_text_of_a_block() -> None:
    block = BlockDescription(
        kind=KIND_TABLE,
        text="a\udc80\tb",
        marker="\ud800",
        rows=((CellDescription("a\udc80"), CellDescription("\udfff\udfff")),),
    )
    assert unencodable_count(block) == 1 + 1 + 2, "a table's text is its cells: counted once"
    assert unencodable_count(BlockDescription(text="a\udc80b\ud800", marker="\udc81")) == 3
    assert (
        unencodable_count(BlockDescription(text="plain � text")) == 0
    ), "a U+FFFD the host wrote is not one the view set"


_CHILD = r"""
import json, random, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.diff import Diff, UnifiedDiffStream
from imscribe.theme import Theme
from imscribe.typeset_markdown import MarkdownStream
from imscribe.ui.typeset_diff_view import TypesetDiffView
from imscribe.ui.typeset_hosts import TypesetDiffFences
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import TypesetView

if typesetter.module() is None:
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

def frame(view):
    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
    imgui.set_next_window_size(imgui.ImVec2(700.0, 600.0))
    imgui.begin("host")
    try:
        before = imgui.get_window_draw_list().vtx_buffer.size()
        view.draw()
        return imgui.get_window_draw_list().vtx_buffer.size() - before
    except Exception as exc:
        return type(exc).__name__ + ": " + str(exc)[:160]
    finally:
        imgui.end()
        imgui.render()

def surrogates(text):
    return sum(1 for ch in text if "\ud800" <= ch <= "\udfff")

def copied(view):
    # What a copy of everything puts on the clipboard, and whether UTF-8 holds it.
    imgui.set_clipboard_text("before")
    try:
        view.select_all()
        view.copy()
    except Exception as exc:
        return [type(exc).__name__, False, 0]
    got = imgui.get_clipboard_text() or ""
    try:
        got.encode("utf-8")
        ok = True
    except UnicodeEncodeError:
        ok = False
    return [got != "before", ok, got.count("�")]

S = json.loads('"\\udc80"')
HI, LO = json.loads('"\\ud83d"'), json.loads('"\\ude00"')
DOC = (
    f"# A heading {S} here\n\n"
    f"Prose with {S} a lone one, `code {S}` and *emphasis {S}*, a link [to {S}](http://x/{S}).\n\n"
    f"- a list item {S}\n- {HI}\n\n"
    f"> quoted {S}\n\n"
    f"```python\nprint('{S}')\n```\n\n"
    f"| head {S} | b |\n|---|---|\n| cell {S} | {LO} |\n\n"
    f"```diff\n--- a/f{S}.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n one\n-two {S}\n+two\n```\n\n"
    f"Math $a{S}b$ and the end.\n"
)
report["doc_surrogates"] = surrogates(DOC)

# -- TypesetView: plain, with math, with fences hosted ------------------------
report["view"] = {}
for label, more in {"plain": {}, "math": {"math": True},
                    "fences": {"host_for": TypesetDiffFences()}}.items():
    view = TypesetView(DOC, theme=theme, **more)
    frames = [frame(view), frame(view)]
    texts = list(view.texts)
    report["view"][label] = {
        "frames": frames,
        "texts_surrogates": sum(surrogates(t) for t in texts),
        "copied": copied(view),
        "after_copy": frame(view),
        "replaced": getattr(view, "replaced_characters", None),
        "hosts": list(view.hosts),
    }
    view.set_document("clean now")
    report["view"][label]["clean"] = [frame(view), getattr(view, "replaced_characters", None)]

# -- TypesetStreamView, fed in chunks; a boundary inside a surrogate pair ------
report["stream"] = {}
SPLIT = "smile " + HI + LO + " here, and json halves: " + HI
for label, size in {"by 1": 1, "by 7": 7, "by 61": 61}.items():
    for fenced in (False, True):
        stream = MarkdownStream(theme)
        more = {"host_for": TypesetDiffFences()} if fenced else {}
        live = TypesetStreamView(stream, **more)
        whole = DOC + "\n" + SPLIT
        frames = []
        for at in range(0, len(whole), size):
            stream.append(whole[at:at + size])
            got = frame(live)
            if not isinstance(got, int):
                frames.append([at, got])
        # The exact case: a chunk ending on the high half, the next starting on the low.
        stream.append(" end " + HI)
        frames.append(frame(live))
        stream.append(LO + " after")
        frames.append(frame(live))
        stream.close()
        frames.append(frame(live))
        report["stream"][f"{label}{' fenced' if fenced else ''}"] = {
            "raised": [f for f in frames if not isinstance(f, int)],
            "texts_surrogates": sum(surrogates(t) for t in live.texts),
            "copied": copied(live),
            "replaced": getattr(live, "replaced_characters", None),
        }

# -- TypesetDiffView ------------------------------------------------------------
report["diff"] = {}
before = f"one\ntwo {S}\nthree\n{HI}\n"
after = f"one\ntwo\nthree {S}{S}\n{LO}\n"
unified = (
    f"From me {S}\nSubject: bytes\n\n"
    f"diff --git a/x{S} b/x{S}\n--- a/x{S}\n+++ b/x{S}\n"
    f"@@ -1,3 +1,3 @@ def f{S}():\n ctx {S}\n-old {S}\n+new {HI}\n prose under it {S}\n"
)
diffs = {
    "from_texts": Diff.from_texts(before, after, f"f{S}.py"),
    "from_unified": Diff.from_unified(unified),
}
s = UnifiedDiffStream()
for at in range(0, len(unified), 5):
    s.feed(unified[at:at + 5])
diffs["streamed open"] = s.diff
for label, diff in diffs.items():
    for layout in ("unified", "split"):
        from imscribe.ui.typeset_diff_view import DiffLayout
        view = TypesetDiffView(diff, theme, layout=DiffLayout.UNIFIED if layout == "unified"
                               else DiffLayout.SIDE_BY_SIDE)
        frames = [frame(view), frame(view)]
        try:
            view.headers()
            headers = "accepted"
        except Exception as exc:
            headers = type(exc).__name__
        report["diff"][f"{label} {layout}"] = {
            "frames": frames, "headers": headers, "copied": copied(view),
            "after_copy": frame(view),
            "replaced": getattr(view, "replaced_characters", None),
        }
view = TypesetDiffView(Diff.from_texts("a\n", "b\n", "f.py"), theme)
frame(view)
view.set_diff(Diff.from_texts(before, after, f"f{S}.py"))
report["diff_set"] = [frame(view), getattr(view, "replaced_characters", None)]

# -- No str raises out of draw: a seeded fuzz of awkward characters ------------
ALPHABET = (
    [S, HI, LO, "\ud800", "\udfff", "\x00", "\x07", "\x1b", "\x7f", "\x85", " ", " ",
     "​", "‍", "﻿", "‮", "́", "�", "￿", "￾", "",
     "\U0010ffff", "\U0001f600", "\t", "\r", "\n", "\r\n", " ", "|", "`", "```", "$", "*", "#",
     "-", ">", "[", "]", "(", ")", "\\", "a", "word", "א", "一"]
)
rng = random.Random(41)
fuzz = {"tried": 0, "raised": []}
for _ in range(120):
    text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 80)))
    for more in ({}, {"math": True}):
        fuzz["tried"] += 1
        try:
            view = TypesetView(text, theme=theme, **more)
        except Exception as exc:
            fuzz["raised"].append(["init", repr(text)[:120], type(exc).__name__])
            continue
        got = frame(view)
        if not isinstance(got, int):
            fuzz["raised"].append(["draw", repr(text)[:120], got])
        try:
            view.select_all()
            view.copy()
            imgui.get_clipboard_text().encode("utf-8")
        except Exception as exc:
            fuzz["raised"].append(["copy", repr(text)[:120], type(exc).__name__])
    fuzz["tried"] += 1
    try:
        view = TypesetDiffView(Diff.from_texts(text, text[::-1] + "\n", text[:9]), theme)
        got = frame(view)
        if not isinstance(got, int):
            fuzz["raised"].append(["diff draw", repr(text)[:120], got])
    except Exception as exc:
        fuzz["raised"].append(["diff", repr(text)[:120], type(exc).__name__])
report["fuzz"] = fuzz
report["state"] = [typesetter.kind().value, typesetter.ready(), typesetter.reason()]
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


def test_a_text_view_draws_and_copies_lone_surrogates(told: dict[str, Any]) -> None:
    """Prose, code, a heading, a table, a list, a quote, a link, a formula and a fence."""
    assert told["doc_surrogates"] >= 15
    assert sorted(told["view"]) == ["fences", "math", "plain"]
    for label, got in told["view"].items():
        assert all(isinstance(f, int) and f > 0 for f in got["frames"]), (label, got["frames"])
        assert isinstance(got["after_copy"], int), label
        assert got["texts_surrogates"] == 0, label
        assert got["copied"][:2] == [True, True], (label, got["copied"])
        assert isinstance(got["clean"][0], int), label
    assert told["view"]["fences"]["hosts"], "the diff fence was hosted"


def test_a_stream_view_fed_in_chunks_never_raises(told: dict[str, Any]) -> None:
    """Including a chunk that ends on a high surrogate and one that starts on the low."""
    assert len(told["stream"]) == 6
    for label, got in told["stream"].items():
        assert got["raised"] == [], (label, got["raised"])
        assert got["texts_surrogates"] == 0, label
        assert got["copied"][:2] == [True, True], (label, got["copied"])


def test_a_diff_view_draws_and_copies_lone_surrogates(told: dict[str, Any]) -> None:
    """Rows, a label, header lines, a hunk's heading, unread prose; whole and streamed."""
    assert len(told["diff"]) == 6
    for label, got in told["diff"].items():
        assert all(isinstance(f, int) and f > 0 for f in got["frames"]), (label, got["frames"])
        assert got["headers"] == "accepted" and isinstance(got["after_copy"], int), label
        assert got["copied"][:2] == [True, True], (label, got["copied"])
    assert isinstance(told["diff_set"][0], int)


def test_no_str_raises_out_of_draw(told: dict[str, Any]) -> None:
    fuzz = told["fuzz"]
    assert fuzz["tried"] == 360
    assert fuzz["raised"] == []
    assert told["state"] == ["ready", True, ""], "nothing switched the library off"


def test_a_host_can_read_how_many_characters_were_replaced(told: dict[str, Any]) -> None:
    """P41: `replaced_characters`, on the text views and on the diff view."""
    for label, got in told["view"].items():
        # Every surrogate of the source is in some block's text (link targets aside: the
        # one in `http://x/...` is not text on show), so each is one U+FFFD.
        assert got["replaced"] == told["doc_surrogates"] - 1, (label, got["replaced"])
        assert got["copied"][2] == got["replaced"], (label, "a copy of all has each U+FFFD")
        assert got["clean"][1] == 0, (label, "a new document starts the count again")
    for label, got in told["stream"].items():
        # DOC's, SPLIT's three halves, and the pair split across two appends: two more.
        assert got["replaced"] == told["doc_surrogates"] - 1 + 3 + 2, (label, got["replaced"])
        assert got["copied"][2] == got["replaced"], label
    for label, got in told["diff"].items():
        assert got["replaced"] > 0, label
    # The label; the rows `two S`, `three SS`, a high half and a low half.
    assert told["diff"]["from_texts unified"]["replaced"] == 1 + 1 + 2 + 1 + 1
    # The label; the hunk's section; four rows. The mail's `From me S` and the
    # header lines are not drawn, and are not counted.
    for layout in ("unified", "split"):
        assert told["diff"][f"from_unified {layout}"]["replaced"] == 1 + 1 + 4
    assert told["diff_set"][1] == 6, "a new diff counts again"

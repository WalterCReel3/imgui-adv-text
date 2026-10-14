r"""
`imscribe.ui.typeset_diff_view`: `DiffRows` and `TypesetDiffView`.

Which tests run depends on how the suite was started, as in
`tests/test_typeset_view.py`:

1.  **Without the library** (always): the refusal, what importing the module
    loads, and `DiffRows` -- the pure half -- held to what `DiffView` answers
    on the same diffs: the same rows, the same row for a `RowInfo`, the same
    hunks, the same rows after an expansion, and the same text copied for the
    same selection in both layouts.
2.  **With it.** Skipped, with the reason, when `IMTYPESET_LIBRARY` is not
    set. ONE run of `_DRIVER` in a real window (the `window` fixture) through
    `hello_imgui`, the mouse and the keys queued through `io.add_*_event`; it
    prints a report and each test reads its part. The driver says whether
    `typesetter.module()` and `ready()` held IN THE CHILD, and the fixture
    fails when they did not.

## What `DiffView` answers is frozen (T4-DIFF)

`imscribe.ui.diff_view.DiffView` is what this view is held against, and it is
to be deleted. So what it answers for these cases is data,
`tests/data/diff_view_answers.json`, written by
`.concerns/T4-DIFF-scripts/freeze_diff_view.py` from the two functions here
that ask it (`diff_view_answers`, and the driver's `oracle`). Every comparison
is against that file. **While `DiffView` can still be imported**, two tests
also ask it again and hold the file to what it says now
(`test_the_frozen_answers_are_what_diff_view_answers_now`, and
`test_the_frozen_window_answers_are_what_diff_view_answered_in_this_run`), and
a handful of tests that are about the two classes together run; when it is
gone those skip, saying so, and the file is all that is left of it.

The corpus is fixed too: the files under `demo/diff/` and `fixed_long_texts`,
which is generated here. (It was `imscribe.ui.pages.diff.long_texts`, this
package's own sources end to end, which moved whenever a module was edited and
would have moved a great deal when the old core is deleted.) `inputs` in the
file is a fingerprint of every diff, so a changed corpus is said to be that
and not a wrong answer.

The driver counts calls into the library by standing in front of
`imtypeset._lib` (a private name of a package this tree does not own: if it
moves, the fixture fails saying so).

Times are in the report and are NOT asserted; the result files of SW-3, T3-C
and T4-DIFF under `.concerns/` have what was read off runs and at what load.
(`.concerns/T4-DIFF-scripts/run_driver.py` runs the driver alone and keeps its
report.)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter
from imscribe.diff import Diff, RowKind
from imscribe.theme import Theme
from imscribe.ui import typeset_diff_view as module
from imscribe.ui.typeset_diff_view import (
    CHUNK,
    CONTROL_PLACEHOLDER,
    DiffLayout,
    DiffRows,
    code_size,
)

_ROOT = Path(__file__).resolve().parent.parent
_DEMO = _ROOT / "demo" / "diff"
_ANSWERS = _ROOT / "tests" / "data" / "diff_view_answers.json"
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)

UNIFIED, SIDE = DiffLayout.UNIFIED, DiffLayout.SIDE_BY_SIDE
_LAYOUTS = ("unified", "side-by-side")
_HEIGHTS = (None, 13.0, 14.0, 16.0, 21.0)


def _report_of(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    return report


def _read(name: str) -> str:
    # newline="": a diff's line endings are part of it.
    with open(_DEMO / name, encoding="utf-8", newline="") as handle:
        return handle.read()


class _Sequence:
    """
    A fixed sequence of numbers (Knuth's 64-bit linear congruence), so that
    the corpus and the selections are the same in every interpreter: what
    `random.Random` gives for a seed is not promised across versions.
    """

    def __init__(self, seed: int) -> None:
        self._state = seed & (2**64 - 1)

    def below(self, limit: int) -> int:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) % 2**64
        return (self._state >> 33) % max(1, limit)


def fixed_long_texts(lines: int = 4000) -> tuple[str, str]:
    """
    A file of `lines` lines of made-up Python and a rewrite of it: the long
    diff. Generated, the same every time, and read from nowhere.

    No two lines of a function are the same text and every function is named
    by its number, because a text that repeats itself gives a line-matching
    diff a thousand equally good wrong alignments. About one line in
    twenty-five holds a character outside ASCII: U+2192 and U+2502, which the
    bundled code face has, and U+03C0, which it lacks. One line in a hundred
    is 150 columns or more.

    The rewrite is `imscribe.ui.pages.diff.long_texts`'s: one line touched in
    every ninety-seven, a block of forty dropped a third of the way down and
    twenty-five inserted two thirds of the way down.
    """
    words = ("alpha", "beta", "gamma", "delta", "width", "height", "total", "scale", "items")
    pick = _Sequence(4000)
    before: list[str] = []
    number = 0
    while len(before) < lines:
        number += 1
        word = words[pick.below(len(words))]
        other = words[pick.below(len(words))]
        mark = ("→", "│", "π")[number % 3]
        body = [
            f"def step_{number}({word}, {other}_limit={number % 7}):",
            (
                f'    """Step {number}: {word} {mark} {other}, scaled."""'
                if number % 2 == 0
                else f'    """Step {number}: {word} to {other}, scaled."""'
            ),
            f"    {word}_{number} = compute({word}, {number}) * {other}_limit",
            f"    if {word}_{number} > {pick.below(900) + 100}:",
            f"        {word}_{number} -= adjust({other}_limit, by={pick.below(50)})",
            f"    for index_{number} in range({pick.below(40) + 2}):",
            f"        {word}_{number} += index_{number} % {pick.below(9) + 2}",
            (
                f"    settings_{number} = dict("
                + ", ".join(f"field_{number}_{n}={pick.below(97)}" for n in range(9))
                + ")"
                if number % 9 == 0
                else f"    settings_{number} = dict(kind={word!r}, other={other!r})"
            ),
            f"    record({number}, {word}_{number}, settings_{number})",
            f"    return {word}_{number}",
            "",
            "",
        ]
        before.extend(body)
    del before[lines:]
    after: list[str] = []
    cut = len(before) // 3
    add = 2 * len(before) // 3
    for at, line in enumerate(before):
        if cut <= at < cut + 40:
            continue
        if at == add:
            after.extend(f"# inserted line {extra + 1} of 25" for extra in range(25))
        if at % 97 == 50 and line.strip():
            line = f"{line}  # touched"
        after.append(line)
    return "\n".join(before) + "\n", "\n".join(after) + "\n"


def _diffs() -> dict[str, Diff]:
    """The diffs the pure half is held to `DiffView`'s answers on."""
    before, after = fixed_long_texts()
    numbered = "".join(f"line {i}\n" for i in range(1, 101))
    edited = (
        numbered.replace("line 20\n", "line 20 changed\n")
        .replace("line 21\n", "")
        .replace("line 60\n", "line 60\nan added line\n")
    )
    return {
        "demo": Diff.from_texts(_read("edit.before.py"), _read("edit.after.py"), "edit.py"),
        "numbered": Diff.from_texts(numbered, edited, "notes.py"),
        "tokens": Diff.from_texts(_read("tokens.before.py"), _read("tokens.after.py"), "t.py"),
        "git": Diff.from_unified(_read("git.diff")),
        "multiedit": Diff.from_unified(_read("multiedit.diff")),
        "combined": Diff.from_unified(_read("combined.diff")),
        "unmarked": Diff.from_unified(_read("unmarked.diff")),
        "line endings": Diff.from_texts("a\r\nb\r\nc\r\n", "a\nb\nc\n", "eol.txt"),
        "odd": Diff.from_texts("a\n中 b\nc\n│ d\ne\n", "a\n中 B\nc\n│ d\nE\n", "o.py"),
        "control": Diff.from_texts("a\x00b\n\tc\n", "a\x00b\n\tc‮d\n", "ctl.py"),
        "long": Diff.from_texts(before, after, "long.py", context=3),
    }


@pytest.fixture(scope="module")
def diffs() -> dict[str, Diff]:
    return _diffs()


@pytest.fixture(scope="module")
def frozen() -> dict[str, Any]:
    """What `DiffView` answered when `.concerns/T4-DIFF-scripts/freeze_diff_view.py` was run."""
    found: dict[str, Any] = json.loads(_ANSWERS.read_text(encoding="utf-8"))
    return found


def _old() -> Any:
    """`imscribe.ui.diff_view`, or a skip that says the oracle is the file now."""
    try:
        from imscribe.ui import diff_view
    except ImportError as exc:
        pytest.skip(
            f"imscribe.ui.diff_view cannot be imported ({exc}): DiffView's answers are "
            f"{_ANSWERS.relative_to(_ROOT)} now, and this test was about the class itself"
        )
    return diff_view


# ---------------------------------------------------------------------------
# What is asked of a view, of either class, as data
# ---------------------------------------------------------------------------


def _fields(info: Any) -> list[Any]:
    return [info.kind, info.file, info.hunk, info.left, info.right]


def _digest(text: str) -> list[Any]:
    """A text as its length and a hash: enough to say two copies are the same text."""
    return [len(text), hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:20]]


def fingerprint(diff: Diff) -> str:
    """Every label, header, row and ending of a diff, as one hash: is it the same corpus?"""
    said = repr(
        [
            (
                file.label,
                file.dialect,
                list(file.raw),
                [
                    (hunk.header, [(row.kind.value, row.text, row.eol) for row in hunk.rows])
                    for hunk in file.hunks
                ],
            )
            for file in diff.files
        ]
    )
    return hashlib.sha256(said.encode("utf-8", "surrogatepass")).hexdigest()[:20]


def _positions(diff: Diff, pick: _Sequence, count: int) -> list[list[int]]:
    """Positions in the model, some at the edges of their lines."""
    places = [
        (f, h, r, len(row.text))
        for f, file in enumerate(diff.files)
        for h, hunk in enumerate(file.hunks)
        for r, row in enumerate(hunk.rows)
    ]
    out = []
    for _ in range(count):
        f, h, r, size = places[pick.below(len(places))]
        out.append([f, h, r, (0, size, pick.below(size + 1))[pick.below(3)]])
    return out


_COPY_CASES: tuple[tuple[str, int | None, bool], ...] = (
    ("unified", None, False),
    ("unified", None, True),
    ("side-by-side", 0, False),
    ("side-by-side", 1, False),
)


def view_answers(make: Callable[..., Any], diffs: dict[str, Diff]) -> dict[str, Any]:
    """
    What a diff view answers about `diffs`, as JSON: asked the same way of
    `DiffView` (which is what the file holds) and of `DiffRows`.
    `make(diff, layout_value, copy_removed_lines=False)` makes the view.
    """
    rows: dict[str, Any] = {}
    for name, diff in diffs.items():
        for layout in _LAYOUTS:
            view = make(diff, layout)
            count = view.row_count
            infos = [view.row_info(row) for row in range(count)]
            entry = {
                "infos": [_fields(info) for info in infos],
                "row_of": [view.row_of(info) for info in infos],
                "hunk_rows": [
                    view.row_of_hunk(file, hunk)
                    for file, held in enumerate(diff.files)
                    for hunk in range(len(held.hunks))
                ],
            }
            # Hunk to hunk, forwards to the end and one more, then back.
            steps = []
            for _ in range(4):
                steps.append([view.next_hunk(), view._scroll_to])
            steps.append([view.previous_hunk(), view._scroll_to])
            entry["steps"] = [[list(at) if at else at, to] for at, to in steps]
            entry["current"] = list(view.current_hunk) if view.current_hunk else None
            rows[f"{name} {layout}"] = entry

    expanded: dict[str, Any] = {}
    for name in ("demo", "numbered", "long"):
        for layout in _LAYOUTS:
            view = make(diffs[name], layout)
            view.next_hunk()
            steps = []
            for gap, lines, edge in ((0, None, "top"), (1, 7, "bottom"), (1, 10**6, "top")):
                view.expand(0, gap, lines, edge)
                steps.append(
                    {
                        "infos": [_fields(view.row_info(row)) for row in range(view.row_count)],
                        # The hunk `next_hunk` was on is followed through the renumbering.
                        "current": list(view.current_hunk) if view.current_hunk else None,
                    }
                )
            expanded[f"{name} {layout}"] = steps

    copies: dict[str, Any] = {}
    for number, (name, diff) in enumerate(diffs.items()):
        if not any(hunk.rows for file in diff.files for hunk in file.hunks):
            continue
        for case, (layout, side, removed) in enumerate(_COPY_CASES):
            view = make(diff, layout, copy_removed_lines=removed)
            points = _positions(diff, _Sequence(20261011 + 100 * number + case), 40)
            picked = []
            for start, end in zip(points[::2], points[1::2], strict=True):
                view.select(tuple(start), tuple(end), side)
                picked.append(
                    [
                        start,
                        end,
                        [list(at) for at in view.selection] if view.selection else None,
                        view.selection_side,
                        *_digest(view.selected_text()),
                        module.COPY_GAP in view.selected_text(),
                    ]
                )
            view.select_all(side)
            everything = [
                [list(at) for at in view.selection] if view.selection else None,
                *_digest(view.selected_text()),
            ]
            copies[f"{name} {layout} side={side} removed={removed}"] = {
                "picked": picked,
                "all": everything,
            }
    return {"rows": rows, "expanded": expanded, "copies": copies}


def _mine(diff: Diff, layout: str, copy_removed_lines: bool = False) -> DiffRows:
    return DiffRows(diff, layout=layout, copy_removed_lines=copy_removed_lines)


def _header_cases(diffs: dict[str, Diff]) -> dict[str, Diff]:
    cases = dict(diffs)
    cases["refused"] = diffs["demo"].mark_will_not_apply("will not apply: line 34 moved")
    return cases


_LABELS = ("a/b.py", "Makefile", "x.TSX", "noext", "Dockerfile", "a.b.yml")
_TABBED = ("", "abc", "\tx", "a\tb\tc", "ab\t\tc", "中\tz")
_LENGTHS = (0, 1, 655360, 786432, 1234567)


def lifted_answers(source: Any, columns: Any, width: Any, px: Any, tab: int) -> dict[str, Any]:
    """The constants and small functions this module copied, as the module `source` has them."""
    return {
        "CONTROL_PLACEHOLDER": source.CONTROL_PLACEHOLDER,
        "COPY_GAP": source.COPY_GAP,
        "SYNTAX_CHUNK": source.SYNTAX_CHUNK,
        "TAB_WIDTH": tab,
        "EOL_MARKS": dict(source._EOL_MARKS),
        "LANGUAGES": dict(source._LANGUAGES),
        "layouts": [member.value for member in source.DiffLayout],
        "row_info": list(source.RowInfo.__slots__),
        "language_for": [source.language_for(label) for label in _LABELS],
        "columns": [columns(text) for text in _TABBED],
        "width": [width(text) for text in _TABBED],
        "px": [[px(length, ppi) for ppi in (96.0, 144.0)] for length in _LENGTHS],
    }


def text_answers(
    header: Callable[[Diff, Any], tuple[str, str]],
    gap: Callable[[Diff, Any, int], str],
    fold: Callable[[Diff, Any], str],
    diffs: dict[str, Diff],
) -> dict[str, Any]:
    """What a file's header, a collapsed-context row and a fold row say."""
    return {
        "headers": {
            name: [list(header(diff, file)) for file in diff.files]
            for name, diff in _header_cases(diffs).items()
        },
        "gap": gap(diffs["demo"], diffs["demo"].files[0], 0),
        "fold": fold(diffs["line endings"], diffs["line endings"].files[0]),
    }


def diff_view_answers(diffs: dict[str, Diff]) -> dict[str, Any]:
    """
    Everything the pure half is held to, asked of `DiffView`: what
    `.concerns/T4-DIFF-scripts/freeze_diff_view.py` writes under `"pure"`. Needs
    `imscribe.ui.diff_view` and the bundled fonts (for the code face's metrics).
    """
    from imscribe import markdown, units
    from imscribe.ui import diff_view

    theme = Theme.build()

    def make(diff: Diff, layout: str, copy_removed_lines: bool = False) -> Any:
        return diff_view.DiffView(
            diff,
            theme,
            layout=diff_view.DiffLayout(layout),
            copy_removed_lines=copy_removed_lines,
        )

    out = view_answers(make, diffs)
    out["lifted"] = lifted_answers(
        diff_view,
        lambda text: diff_view._columns(text, markdown.TAB_WIDTH),
        lambda text: diff_view._width(text, markdown.TAB_WIDTH),
        units.px_from_sp,
        markdown.TAB_WIDTH,
    )
    out["texts"] = text_answers(
        lambda diff, file: make(diff, "unified")._file_header(file),
        lambda diff, file, at: make(diff, "unified")._gap_text(file, at),
        lambda diff, file: make(diff, "unified")._fold_text(file),
        diffs,
    )
    sizes = []
    for height in _HEIGHTS:
        metrics = diff_view.DiffView(diffs["demo"], theme, pixel_height=height).metrics_px
        sizes.append([height, units.px_from_sp(metrics.font.size, theme.px_per_inch), metrics.row])
    out["sizes"] = sizes
    out["content_height"] = {
        f"{name} {layout}": make(diff, layout).content_height
        for name, diff in diffs.items()
        for layout in _LAYOUTS
    }
    return out


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------

_WITHOUT = r"""
import json, sys
import imscribe.ui.typeset_diff_view as module
from imscribe import typesetter
from imscribe.diff import Diff
from imscribe.theme import Theme
from imscribe.ui.typeset_view import TypesetUnavailable

mine = sorted(name for name in sys.modules if name.split(".")[0] == "imscribe")
other = sorted(name for name in sys.modules if name.split(".")[0] in ("imtypeset", "imgui_bundle"))
diff = Diff.from_texts("a\nb\n", "a\nB\n", "x.py")
try:
    module.TypesetDiffView(diff, Theme.build())
    refused = None
except TypesetUnavailable as exc:
    refused = [str(exc), isinstance(exc, RuntimeError)]
try:
    lacks = [list(module.code_face_lacks("plain ascii")), module.code_face_lacks("a π")]
except TypesetUnavailable as exc:
    lacks = str(exc)
rows = module.DiffRows(diff)
rows.select((0, 0, 0, 0), (0, 0, 2, 1))
print("REPORT " + json.dumps({
    "imscribe": mine, "other": other, "refused": refused, "reason": typesetter.reason(),
    "rows": rows.row_count, "copied": rows.selected_text(), "lacks": lacks,
    "ascii_lacks": list(module.code_face_lacks("plain ascii")),
    "height": [rows.content_height, rows.row_px, rows.row_top(3)],
    "after": sorted(n for n in sys.modules if n.split(".")[0] in ("imtypeset", "imgui_bundle")),
}))
"""

_CLOSURE = r"""
import importlib, json, sys
importlib.import_module(sys.argv[1])
print("REPORT " + json.dumps(sorted(m for m in sys.modules if m.split(".")[0] == "imscribe")))
"""

# What `imscribe.ui.diff_view` needs of the layout core that this module must
# not: the reason its pure parts were lifted here and not imported.
_NOT_LOADED = {
    "imscribe.backends.imgui_draw",
    "imscribe.linebreak",
    "imscribe.selection",
    "imscribe.spans",
    "imscribe.fontlib",
    "imscribe.mathtext",
    "imscribe.columns",
    "imscribe.blocklayout",
    "imscribe.ui.bare_view",
    "imscribe.ui.diff_view",
    "imscribe.ui.units",
    "imscribe.ui.composition",
}


def _child(script: str, *argv: str) -> Any:
    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", script, *argv],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return _report_of(done.stdout)


def test_without_the_library_the_constructor_refuses_and_the_rows_still_work() -> None:
    """The caller chooses `DiffView`; the pure half needs neither the library nor Dear ImGui."""
    report = _child(_WITHOUT)
    assert report["other"] == [] and report["after"] == []
    message, is_runtime_error = report["refused"]
    assert is_runtime_error
    assert report["reason"] == "IMTYPESET_LIBRARY is not set"
    assert report["reason"] in message
    assert report["rows"] == 5  # the file's header, the hunk's, and three lines
    assert report["copied"] == "a\nB"
    # Height is rows times the pitch, with nothing asked of anything.
    assert report["height"] == [100.0, 20, 60.0]
    # Which characters the code face lacks cannot be asked without it; ASCII needs no asking.
    assert report["ascii_lacks"] == []
    assert isinstance(report["lacks"], str) and "imtypeset cannot be asked" in report["lacks"]


def test_importing_the_module_loads_no_more_of_the_core_than_the_typeset_view_does() -> None:
    """
    Measured, in fresh interpreters: this module adds `imscribe.diff` and itself
    to what `imscribe.ui.typeset_view` loads, and none of what `DiffView` needs
    of the layout core.
    """
    mine = set(_child(_CLOSURE, "imscribe.ui.typeset_diff_view"))
    base = set(_child(_CLOSURE, "imscribe.ui.typeset_view"))
    assert mine - base == {"imscribe.diff", "imscribe.ui.typeset_diff_view"}
    assert not mine & _NOT_LOADED


def test_importing_diff_view_would_have_loaded_the_layout_core() -> None:
    """The reason for the lift, while there is a `DiffView` to import."""
    _old()
    old = set(_child(_CLOSURE, "imscribe.ui.diff_view"))
    assert {"imscribe.backends.imgui_draw", "imscribe.selection", "imscribe.linebreak"} <= old


def test_the_corpus_is_the_one_the_answers_were_frozen_for(
    diffs: dict[str, Diff], frozen: dict[str, Any]
) -> None:
    """
    Before any answer is compared: the diffs are the diffs. A difference here
    is a changed file under `demo/diff/`, a changed `fixed_long_texts`, or a
    changed `imscribe.diff` -- not a wrong row -- and the answers can be frozen
    again only while `DiffView` exists to give them.
    """
    assert {name: fingerprint(diff) for name, diff in diffs.items()} == frozen["inputs"]
    before, after = fixed_long_texts()
    assert before.count("\n") == 4000 and len(diffs["long"].files[0].hunks) > 30
    assert not before.isascii() and max(len(line) for line in before.split("\n")) >= 150


def test_the_frozen_answers_are_what_diff_view_answers_now(
    diffs: dict[str, Diff], frozen: dict[str, Any], bundled_fonts: Any
) -> None:
    """
    While `DiffView` exists: asked again, it says what the file says. (So the
    file is not a second opinion that has drifted from the first.) JSON has
    no tuples: both sides go through it.
    """
    _old()
    live = json.loads(json.dumps(diff_view_answers(diffs)))
    for section, expected in frozen["pure"].items():
        if isinstance(expected, dict):
            for key, value in expected.items():
                assert live[section][key] == value, (section, key)
        assert live[section] == expected, section
    assert live.keys() == frozen["pure"].keys()


def test_what_was_lifted_is_what_diff_view_has(frozen: dict[str, Any]) -> None:
    """Constants and small functions copied from `imscribe.ui.diff_view`, held to it."""
    mine = lifted_answers(module, module._columns, module._width, module._px, module.TAB_WIDTH)
    assert json.loads(json.dumps(mine)) == frozen["pure"]["lifted"]


def test_a_layout_of_either_enum_is_taken(diffs: dict[str, Diff]) -> None:
    rows = DiffRows(diffs["demo"], layout="side-by-side")
    assert rows.layout is SIDE
    rows.set_layout("unified")
    assert rows.layout is UNIFIED
    diff_view = _old()
    rows = DiffRows(diffs["demo"], layout=diff_view.DiffLayout.SIDE_BY_SIDE)
    assert rows.layout is SIDE
    rows.set_layout(diff_view.DiffLayout.UNIFIED)
    assert rows.layout is UNIFIED


def test_the_pitch_and_the_size_are_what_diff_view_reads_from_the_theme(
    bundled_fonts: Any, frozen: dict[str, Any]
) -> None:
    """`code_size` against `DiffView.metrics_px`, at the theme's size and at ImGui heights."""
    theme = Theme.build()
    assert [height for height, _, _ in frozen["pure"]["sizes"]] == list(_HEIGHTS)
    for height, old_size, old_row in frozen["pure"]["sizes"]:
        size, row, _ = code_size(theme, height)
        assert row == old_row, height
        assert size == pytest.approx(old_size, abs=1e-9)


def test_the_rows_the_expansions_and_the_copies_are_diff_view_s(
    diffs: dict[str, Diff], frozen: dict[str, Any]
) -> None:
    """
    The acceptance test of the lift. Every row of every diff in both layouts
    (its `RowInfo`, and the row found again from it), every hunk's row, hunk
    to hunk forwards and back with where each step scrolls to; the rows after
    three expansions, with the current hunk followed through the renumbering;
    and for the same selection -- unified with and without
    `copy_removed_lines`, and on each side -- the selection as it was taken
    and the text copied, character for character (the gap marks between hunks
    and the label between files included): `DiffView`'s, from the file.
    """
    mine = json.loads(json.dumps(view_answers(_mine, diffs)))
    theirs = frozen["pure"]
    for section in ("rows", "expanded", "copies"):
        assert mine[section].keys() == theirs[section].keys(), section
        for key, expected in theirs[section].items():
            assert mine[section][key] == expected, (section, key)
    # The comparison ran: over every layout, over hundreds of selections, and across hunks.
    assert len(theirs["rows"]) == 2 * len(diffs) and len(theirs["expanded"]) == 6
    picked = [pick for entry in theirs["copies"].values() for pick in entry["picked"]]
    assert len(picked) >= 600 and sum(pick[-1] for pick in picked) > 50
    assert sum(len(entry["infos"]) for entry in theirs["rows"].values()) > 1000
    for name, diff in diffs.items():
        for layout in (UNIFIED, SIDE):
            rows = DiffRows(diff, layout=layout)
            assert rows.content_height == theirs["content_height"][f"{name} {layout.value}"]
    # `set_diff` with the object last given does nothing, an expansion or not.
    rows = DiffRows(diffs["demo"])
    rows.expand(0, 0)
    assert rows.diff is not diffs["demo"]
    rows.set_diff(diffs["demo"])
    assert rows.diff is not diffs["demo"]


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_a_row_info_of_either_class_finds_its_row_in_either_view(
    diffs: dict[str, Diff], layout: DiffLayout
) -> None:
    """The two `RowInfo` classes are interchangeable, which the Diff page's `follow` relies on."""
    diff_view = _old()
    theme = Theme.build()
    for name, diff in diffs.items():
        old = diff_view.DiffView(diff, theme, layout=diff_view.DiffLayout(layout.value))
        new = DiffRows(diff, layout=layout)
        for row in range(0, new.row_count, max(1, new.row_count // 300)):
            theirs, ours = old.row_info(row), new.row_info(row)
            assert new.row_of(ours) == old.row_of(theirs) == new.row_of(theirs), (name, row)
            assert old.row_of(ours) == old.row_of(theirs), (name, row)


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_a_layout_switch_leaves_the_same_rows_as_a_view_made_in_it(
    diffs: dict[str, Diff], layout: DiffLayout
) -> None:
    other = SIDE if layout is UNIFIED else UNIFIED
    for name, diff in diffs.items():
        switched = DiffRows(diff, layout=other)
        switched.select_all()
        switched.set_layout(layout)
        made = DiffRows(diff, layout=layout)
        assert switched.selection is None  # a layout switch clears it
        assert [switched.row_info(r) for r in range(switched.row_count)] == [
            made.row_info(r) for r in range(made.row_count)
        ], name


def test_one_selection_is_current_across_views(diffs: dict[str, Diff]) -> None:
    """The counter is `DiffView`'s and `BareView`'s: a selection in one ends the other's turn."""
    first = DiffRows(diffs["demo"])
    second = DiffRows(diffs["demo"], layout=SIDE)
    first.select((0, 0, 0, 0), (0, 0, 1, 2))
    assert first.owns_selection
    second.select((0, 0, 0, 0), (0, 0, 1, 2))
    assert second.owns_selection and not first.owns_selection
    diff_view = _old()
    old = diff_view.DiffView(diffs["demo"], Theme.build())
    old.select((0, 0, 0, 0), (0, 0, 1, 2))
    assert old.owns_selection and not second.owns_selection
    first.select_all()
    assert first.owns_selection and not old.owns_selection


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_the_description_is_the_rows_in_blocks_of_at_most_64(
    diffs: dict[str, Diff], layout: DiffLayout
) -> None:
    """
    Every document has the same blocks with the same lines, one line a row; a
    row's place in the code document is where its text is; and a block's style
    is its role, one of four.
    """
    for name, diff in diffs.items():
        rows = DiffRows(diff, layout=layout)
        sheet = rows._described(whole=True)
        assert not sheet.lazy
        panes = 1 if layout is UNIFIED else 2
        assert sheet.panes == panes and len(sheet.texts) == 2 * panes
        counts = [[text.count("\n") + 1 for text in texts] for texts in sheet.texts]
        assert all(count == counts[0] for count in counts), name
        assert sum(counts[0]) == rows.row_count == len(sheet.row_block), name
        assert max(counts[0], default=0) <= CHUNK
        assert sheet.blocks == len(sheet.first_row) == len(counts[0])
        # No line is empty: a Code block drops blank lines at its end.
        assert all(line for texts in sheet.texts for text in texts for line in text.split("\n"))
        assert {role for styles in sheet.styles for role in styles} <= {0, 1, 2, 3}, name
        assert all(len(styles) == sheet.blocks for styles in sheet.styles)
        at = 0
        for block, count in enumerate(counts[0]):
            assert sheet.first_row[block] == at
            assert sheet.row_block[at : at + count] == [block] * count
            at += count
        for row in range(0, rows.row_count, max(1, rows.row_count // 200)):
            info = rows.row_info(row)
            if info.kind != "row":
                continue
            hunk = diff.files[info.file].hunks[info.hunk]  # type: ignore[index]
            for pane in range(panes):
                at_row = info.left if (panes == 1 or pane == 0) else info.right
                block, start = rows._place(sheet, pane, row)
                line = sheet.texts[2 * pane + 1][block][start:].split("\n", 1)[0]
                if at_row is None:
                    assert line == " "
                else:
                    shown = module._code_line(hunk, at_row)[0]
                    assert line == (shown or " "), (name, row)
                    assert len(module._shown(hunk.rows[at_row].text)[0]) == len(
                        hunk.rows[at_row].text
                    )
    long = DiffRows(diffs["long"], layout=layout)._described()
    assert max(text.count("\n") + 1 for text in long.texts[1]) > 1  # rows do share blocks


def test_a_line_with_a_tall_or_a_borrowed_glyph_is_a_row_like_any_other(
    diffs: dict[str, Diff],
) -> None:
    """
    T4-DIFF. With `BlockFlags.FixedLineHeight` every line is its pitch, so
    nothing here measures a line, sets one apart in a block of its own or
    keeps a table of tall rows: the lines holding U+2502 and U+4E2D share a
    block with their neighbours, the height is rows times the pitch, and row
    `n` is `n` pitches down. (Until the library had the flag each such line
    was alone in a block and its row a whole pixel taller: `extra_height`.)
    """
    for layout in (UNIFIED, SIDE):
        rows = DiffRows(diffs["odd"], layout=layout, row=20)
        sheet = rows._described(whole=True)
        code = sheet.texts[1]
        (block,) = [text for text in code if "│ d" in text]
        assert "中 b" in block and block.count("\n") >= 4
        assert rows.content_height == rows.row_count * 20.0
        assert [rows.row_top(row) for row in (0, 1, 7)] == [0.0, 20.0, 140.0]
    for gone in ("extra_height", "off_grid", "placeholder_off_grid", "lines_measured"):
        assert not hasattr(module.TypesetDiffView, gone), gone
    assert not hasattr(module, "_Pitch") and not hasattr(module, "OffGrid")
    assert "SpaceBelow" not in Path(module.__file__).read_text(encoding="utf-8").split('"""', 2)[2]


def _tall_far_down(lines: int = 3000) -> Diff:
    """A whole file of `lines` lines whose line 1500 holds U+2502, and one edit near the top."""
    before = "".join(f"line {i} = value\n" for i in range(lines))
    after = before.replace("line 1500 = value\n", "line 1500 │ changed\n").replace(
        "line 10 =", "line 10 =="
    )
    return Diff.from_texts(before, after, "tall.py", context=10**9)


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_the_text_of_a_block_is_made_when_its_rows_are_asked_for_and_not_before(
    diffs: dict[str, Diff], layout: DiffLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    T3-C. Describing a diff says which rows are in which block and makes the
    text of the header rows; a block of hunk rows is a stand-in of the same
    number of lines until rows of it are asked for. The count of lines turned
    into text is held here, on a 3,000-line file: none to describe it, and the
    two blocks a window of forty rows meets.
    """
    made: list[int] = []
    real = module._code_line

    def counted(hunk: Any, at: int) -> Any:
        made.append(at)
        return real(hunk, at)

    monkeypatch.setattr(module, "_code_line", counted)
    diff = _tall_far_down()
    rows = DiffRows(diff, layout=layout)
    sheet = rows._described()
    total = rows.row_count
    assert total > 3000 and len(sheet.row_block) == total
    # No line is made into text to describe the diff: not even the one holding U+2502.
    assert made == [] and len(sheet.lazy) == sheet.blocks - 2 >= total // CHUNK
    for number, (_, _, _, begun, end) in sheet.lazy.items():
        for texts in sheet.texts:
            assert texts[number] == "\n".join([" "] * (end - begun))
        assert all(starts[number] is None for starts in sheet.starts)
    assert sheet.dirty
    sheet.dirty = False
    # Asking for rows that are text already makes nothing.
    assert rows._realise(sheet, 0, 2) is False and not sheet.dirty
    before = len(made)
    assert rows._realise(sheet, 100, 140) is True and sheet.dirty
    wanted = set(range(sheet.row_block[100], sheet.row_block[139] + 1))
    assert 1 <= len(wanted) <= 2 and not wanted & set(sheet.lazy)
    assert len(made) - before <= 2 * CHUNK * sheet.panes
    assert rows._realise(sheet, 100, 140) is False
    # What was made is what the whole description has there, and the rest is unchanged.
    whole = DiffRows(diff, layout=layout)._described(whole=True)
    assert whole.first_row == sheet.first_row and whole.row_block == sheet.row_block
    assert whole.styles == sheet.styles
    for number in range(sheet.blocks):
        for d in range(2 * sheet.panes):
            if number in sheet.lazy:
                assert sheet.texts[d][number].count("\n") == whole.texts[d][number].count("\n")
            else:
                assert sheet.texts[d][number] == whole.texts[d][number]
        if number not in sheet.lazy:
            assert [s[number] for s in sheet.starts] == [s[number] for s in whole.starts]
    # A row's place is asked for a row whose block is not text yet: it is made.
    row = total - 5
    assert sheet.row_block[row] in sheet.lazy
    block, start = rows._place(sheet, 0, row)
    assert block not in sheet.lazy
    assert (block, start) == DiffRows(diff, layout=layout)._place(whole, 0, row)
    # Every one of the small diffs: made a part at a time, the same texts as made whole.
    for name, small in diffs.items():
        part = DiffRows(small, layout=layout)
        piecewise = part._described()
        for first in range(0, part.row_count, 7):
            part._realise(piecewise, first, first + 7)
        assert not piecewise.lazy, name
        assert piecewise.texts == DiffRows(small, layout=layout)._described(whole=True).texts, name


def _same_description(mine: Any, fresh: Any) -> None:
    """Two sheets say the same thing (every block of both made into text first)."""
    assert mine.texts == fresh.texts and mine.styles == fresh.styles
    assert mine.first_row == fresh.first_row and mine.row_block == fresh.row_block
    assert mine.starts == fresh.starts
    assert mine.header_inks == fresh.header_inks and mine.blocks == fresh.blocks
    assert mine.segment_blocks == fresh.segment_blocks and not mine.lazy and not fresh.lazy


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_a_diff_described_again_after_an_edit_is_what_a_fresh_view_describes(
    diffs: dict[str, Diff], layout: DiffLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    T3-C. After `expand`, and after each line of a stream, the hunks that are
    the same objects keep their blocks (and whatever text they had) and only
    the rest is described: held here to the description a view made for the
    new diff from nothing, and -- for the stream -- to how many lines were
    turned into text on the way, which must not grow with the diff.
    """
    lines = [f"line {i} = value\n" for i in range(3000)]
    lines[1001] = "line 1001 │ odd\n"  # context beside an edit: in both sides, in a hunk
    before_text = "".join(lines)
    for at in range(200, 3000, 200):
        lines[at] = f"line {at} = changed\n"
    rows = DiffRows(
        Diff.from_texts(before_text, "".join(lines), "many.py", context=3), layout=layout
    )
    rows._realise(rows._described(), 0, 160)
    gaps = [r for r in range(rows.row_count) if rows.row_info(r).kind == "gap"]
    assert len(gaps) > 8
    for gap in (gaps[7], gaps[1]):
        info = rows.row_info(gap)
        before = rows._described()
        rows.expand(info.file, info.hunk)  # type: ignore[arg-type]
        after = rows._described()
        assert after is not before
        # Hunks away from the gap are the same objects: their text was kept -- above the gap
        # where they were, below it twenty rows further on.
        was = {text for text in before.texts[1] if text.startswith("line ")}
        now = {text for text in after.texts[1] if text.startswith("line ")}
        assert len(was & now) >= 5
        fresh = DiffRows(rows.diff, layout=layout)
        _same_description(rows._described(whole=True), fresh._described(whole=True))
        fresh_rows = [fresh.row_info(r) for r in range(fresh.row_count)]
        assert [rows.row_info(r) for r in range(rows.row_count)] == fresh_rows

    # A stream: a git diff, a line at a time, with U+2502 and a tab in it.
    text = _read("git.diff").replace("import", "import │", 1)
    from imscribe.diff import UnifiedDiffStream

    stream = UnifiedDiffStream()
    view = DiffRows(stream.diff, layout=layout)
    made: list[int] = []
    real = module._code_line

    def counted(hunk: Any, at: int) -> Any:
        made.append(at)
        return real(hunk, at)

    monkeypatch.setattr(module, "_code_line", counted)
    per_step = []
    fed = text.splitlines(keepends=True)
    for line in [*fed, None]:
        if line is None:
            stream.close()
        else:
            stream.feed(line)
        view.set_diff(stream.diff)
        before_count = len(made)
        sheet = view._described()
        view._realise(sheet, 0, 12)  # a window at the top
        per_step.append(len(made) - before_count)
        if len(per_step) % 9 == 0 or line is None:
            fresh = DiffRows(stream.diff, layout=layout)
            mine = view._described()
            for other in (mine, fresh._described()):
                fresh._realise(other, 0, 10**9)
            _same_description(mine, fresh._described())
            # The hunk records, read a row at a time, are what a first reading gives.
            fresh._indexed()
            assert view._infos.keys() == fresh._infos.keys()
            for key, info in view._infos.items():
                other_info = fresh._infos[key]
                assert (info.columns, info.old, info.new, info.place, info.count) == (
                    other_info.columns,
                    other_info.old,
                    other_info.new,
                    other_info.place,
                    other_info.count,
                ), key
            view = DiffRows(stream.diff, layout=layout)  # the realised-all sheet is not the case
    assert len(per_step) > 30
    # Lines made into text for one arriving line: the open hunk's, in the window; not the diff's.
    assert max(per_step[len(per_step) // 2 :]) <= 2 * 12 * (1 if layout is UNIFIED else 2) + 4


def test_only_the_library_s_own_failure_switches_the_library_off(
    diffs: dict[str, Diff], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    R9c (SW-R1). What is raised while a frame is drawn is sorted by whose it
    is: an exception the `imtypeset` package defines switches the library off
    and becomes `TypesetUnavailable`; an `IndexError` of this module's own, a
    model's `KeyError` or a `TypeError` leaves as itself and switches nothing.
    """
    from imscribe.ui.typeset_view import TypesetUnavailable

    class Error(Exception):
        pass

    class Deeper(Error):
        pass

    Error.__module__ = "imtypeset"
    Deeper.__module__ = "somewhere.else"  # a subclass of the library's is the library's
    assert module._library_failed(Error("x")) and module._library_failed(Deeper("x"))
    for mine in (IndexError("x"), KeyError("x"), TypeError("x"), RuntimeError("x"), ValueError()):
        assert not module._library_failed(mine)
    said: list[str] = []
    monkeypatch.setattr(typesetter, "disable", said.append)
    view = object.__new__(module.TypesetDiffView)
    for mine in (IndexError("a slip"), KeyError("the model's"), ZeroDivisionError()):
        with pytest.raises(type(mine)) as caught:
            view._failed(mine)
        assert caught.value is mine
    assert said == []
    refusal = TypesetUnavailable("imtypeset cannot draw: not ready")
    with pytest.raises(TypesetUnavailable) as again:
        view._failed(refusal)
    assert again.value is refusal and said == []
    with pytest.raises(TypesetUnavailable, match="switched off"):
        view._failed(Error("Document.draw: the library said no"))
    assert said == ["Error: Document.draw: the library said no"]


def test_the_view_does_not_look_for_the_draw_list_itself() -> None:
    """`Document.draw(None, pos)` draws into the current window: no mangled symbol is needed."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "typesetter.window_draw_list" not in source


def test_there_is_one_reader_of_fenced_diffs_and_it_is_not_here() -> None:
    """
    The lead's decision 4 of tranche 4: `imscribe.ui.typeset_hosts` has the one
    reader of fenced `diff` blocks for the typeset views; T3-C's second copy
    (`FencedDiffs`, `HostedTypesetDiff`) is gone from this module.
    """
    for gone in ("FencedDiffs", "HostedTypesetDiff", "FENCE_LANGUAGES", "_Fence"):
        assert not hasattr(module, gone), gone
    from imscribe.ui import typeset_hosts

    assert typeset_hosts.FENCE_LANGUAGES == ("diff", "patch")
    assert callable(typeset_hosts.HostedDiff.handle_keys)


def test_a_control_character_is_a_placeholder_and_a_tab_stays_a_tab(diffs: dict[str, Diff]) -> None:
    assert module._shown("a\x00b\x1b") == (f"a{CONTROL_PLACEHOLDER}b{CONTROL_PLACEHOLDER}", (1, 3))
    assert module._shown("\tx = 1") == ("\tx = 1", ())
    assert module._shown("a‮b\rc") == (
        f"a{CONTROL_PLACEHOLDER}b{CONTROL_PLACEHOLDER}c",
        (1, 3),
    )
    assert module._shown("中 §") == ("中 §", ())
    rows = DiffRows(diffs["control"])
    sheet = rows._described(whole=True)
    code = "\n".join(sheet.texts[1])
    assert "\x00" not in code and "‮" not in code and "\t" in code
    assert code.count(CONTROL_PLACEHOLDER) == 2  # the NUL, and the override
    # The header says so, and that part of it is in the warning ink.
    (header,) = [text for text in sheet.texts[0] if "contains" in text]
    ((start, end),) = sheet.header_inks[0]
    assert header[start:end].startswith("  ! contains control characters")
    # The copy is the real characters.
    rows.select_all()
    assert "\x00" in rows.selected_text() and "‮" in rows.selected_text()


def test_a_file_s_header_says_what_diff_view_s_says_and_the_warning_is_marked(
    diffs: dict[str, Diff], frozen: dict[str, Any]
) -> None:
    """The host's verdict, unread lines and the file's state: `DiffView._file_header`'s text."""
    mine = text_answers(
        lambda diff, file: module._file_header(file),
        lambda diff, file, at: module._gap_text(file, at),
        lambda diff, file: module._fold_text(file),
        diffs,
    )
    # A gap and a fold say what `DiffView` says, the invitation to click included.
    assert json.loads(json.dumps(mine)) == frozen["pure"]["texts"]
    for name, diff in _header_cases(diffs).items():
        rows = DiffRows(diff)
        sheet = rows._described()
        headers = [row for row in range(rows.row_count) if rows.row_info(row).kind == "file"]
        assert len(headers) == len(diff.files)
        said = frozen["pure"]["texts"]["headers"][name]
        for row, (text, warning) in zip(headers, said, strict=True):
            line = sheet.texts[0][sheet.row_block[row]]
            assert line == " " + module._shown(text + warning)[0], name
            inks = sheet.header_inks.get(row, ())
            if warning:
                assert (1 + len(text), 1 + len(text) + len(warning)) in inks, name
            else:
                assert all(end - start == 1 for start, end in inks), name  # placeholders only
    refused = DiffRows(_header_cases(diffs)["refused"])._described()
    assert "  ! will not apply: line 34 moved" in refused.texts[0][0]


def test_a_row_kind_s_marker_is_in_the_gutter_text(diffs: dict[str, Diff]) -> None:
    """The `+` and `-` are text of the gutter document: the channel that is not hue."""
    rows = DiffRows(diffs["numbered"])
    sheet = rows._described(whole=True)
    gutter = "\n".join(sheet.texts[0]).split("\n")
    for row in range(rows.row_count):
        info = rows.row_info(row)
        if info.kind != "row":
            continue
        line = diffs["numbered"].files[0].hunks[info.hunk].rows[info.left]  # type: ignore[index]
        assert gutter[row].rstrip(" ").endswith(line.kind.value.strip() or str(line.new_no)), row
        if line.kind is RowKind.ADD:
            assert gutter[row].split() == [str(line.new_no), "+"]
        if line.kind is RowKind.REMOVE:
            assert gutter[row].split() == [str(line.old_no), "-"]


# ---------------------------------------------------------------------------
# 2. With the library, in a real window
# ---------------------------------------------------------------------------

_DRIVER = r"""
import json, statistics, sys, time
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.diff import Diff, UnifiedDiffStream, tokenize
from imscribe.theme import Theme
from imscribe.ui.pages._syntax import line_colours
from imscribe.ui.pages.themes import COLOURS
from imscribe.ui.palette import DARK_PALETTE, DEFAULT_PALETTE
from imscribe.ui.typeset_diff_view import DiffLayout, TypesetDiffView, code_face_lacks
from imscribe.ui.typeset_view import TypesetUnavailable

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "tests"))
from test_typeset_diff_view import fixed_long_texts

# `DiffView` is what this view is held against, while there is one. When it is gone its
# answers are the file's (`oracle`), its fonts are not loaded and it is not drawn or timed.
try:
    from imscribe.ui.diff_view import DiffLayout as OldLayout, DiffView
    from imscribe.ui.fonts import load_faces
except ImportError:
    DiffView = None
try:
    FROZEN = json.loads(
        (ROOT / "tests" / "data" / "diff_view_answers.json").read_text(encoding="utf-8")
    ).get("window", {})
except OSError:
    FROZEN = {}
POS = (10.0, 10.0)
H = 660.0
PARKED = (5.0, 695.0)
UNIFIED, SIDE = DiffLayout.UNIFIED, DiffLayout.SIDE_BY_SIDE

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

def read(name):
    with open(ROOT / "demo" / "diff" / name, encoding="utf-8", newline="") as handle:
        return handle.read()

theme = Theme.build()
syntax = line_colours(COLOURS[1].syntax)
report = {"load_start": loadavg(), "timing": {}, "oracle": {},
          "oracle_is": "DiffView" if DiffView is not None else "the frozen answers"}

def oracle(key, ask):
    # What `DiffView` answers for `key`: asked of it while it exists, and written down so that
    # the file can be held to it; read from the file when it does not.
    if DiffView is None:
        return FROZEN.get(key, "NOT FROZEN: " + key)
    value = report["oracle"][key] = json.loads(json.dumps(ask()))
    return value

def old_view(diff, layout=None, **kwargs):
    if DiffView is None:
        return None
    return DiffView(diff, theme, layout=OldLayout((layout or DiffLayout.UNIFIED).value), **kwargs)
calls, events, loaded, log = [], [], [], []
state = {"n": 0, "scene": None, "last": None, "ts": None, "real": None, "done": False}

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    loaded.append(load_faces() if DiffView is not None else None)
    report["load_fonts"] = typesetter.load_fonts()

def pre_new_frame():
    io = imgui.get_io()
    # A loaded machine must not turn two clicks into one each. (Dear ImGui asserts that the
    # delay is the longer of the two.)
    io.mouse_single_click_delay = 31.0
    io.mouse_double_click_time = 30.0
    while events:
        events.pop(0)(io)

def show(*windows, width=860.0, scroll=None, height=H):
    # windows: (name, view) pairs drawn in this order, all in the same rectangle.
    state["scene"] = {"windows": [w for w in windows if w[1] is not None], "width": width,
                      "scroll": scroll, "height": height}

def wait(frames=1):
    for _ in range(frames):
        yield

def do(*queued):
    # Queue events for the next frame, and come back when that frame has been drawn:
    # `state["last"]` is then what it did.
    events.extend(queued)
    yield
    yield

def move(x, y):
    return do(lambda io: io.add_mouse_pos_event(float(x), float(y)))

def button(down):
    return do(lambda io: io.add_mouse_button_event(0, down))

def key(name, down):
    return lambda io: io.add_key_event(getattr(imgui.Key, name), down)

def last(name="new"):
    return state["last"][name]

def point(view, row, column, pane=0, dx=1.0):
    # A point on display row `row`, just right of the left edge of cell `column` of a pane's code.
    ox, oy = view.origin
    panes = view._panes(view._width, view.grid.cell)
    return (ox + panes[pane].code - view.scroll_x + column * view.grid.cell + dx,
            oy + view.row_top(row) + view.row_px / 2.0)

def rows_of(view, kind="row"):
    return [r for r in range(view.row_count) if view.row_info(r).kind == kind]

def line_of(view, row, side=None):
    info = view.row_info(row)
    at = info.left if side in (None, 0) else info.right
    return view.diff.files[info.file].hunks[info.hunk].rows[at], (info.file, info.hunk, at)

def at(view, row, column, side=None):
    # The model position a point on display row `row`, cell `column` is: no further than its end.
    line, where = line_of(view, row, side)
    return [*where, min(column, len(line.text))]

def to_top():
    # A window keeps its scroll from the view shown in it before: back to the top.
    state["scene"]["scroll"] = 0.0
    yield from wait(2)
    state["scene"]["scroll"] = None
    yield from wait(2)

def old_copy(name, diff, layout, selection, side):
    # The selection is part of the key: frozen answers are for the positions the mouse had then.
    def ask():
        old = old_view(diff, layout)
        old.select(tuple(selection[0]), tuple(selection[1]), side)
        return old.selected_text()
    return oracle(f"copy/{name} {layout.value} {side} {json.dumps(selection)}", ask)

def lefts(view):
    return [view.row_info(r).left for r in range(view.row_count)]

def visible(view):
    return [view.visible_rows.start, view.visible_rows.stop]

def worst_top_error(view):
    # How far any block of any document is from where the view's row table puts its first row.
    sheet = view._described()
    worst = 0.0
    for doc in view.native_documents:
        for b in range(len(doc)):
            top = doc.block_geometry(b).full_min[1]
            worst = max(worst, abs(top - view.row_top(sheet.first_row[b])))
    return worst

def last_block_errors(view):
    # Where the library has the LAST block of each document, asked before any block above it
    # is asked about, against the view's row table. (Asking about a block lays it out.)
    sheet = view._described()
    at = sheet.blocks - 1
    return [doc.block_geometry(at).full_min[1] - view.row_top(sheet.first_row[at])
            for doc in view.native_documents]

def tall_far_down(lines=3000):
    before = "".join(f"line {i} = value\n" for i in range(lines))
    after = before.replace("line 1500 = value\n", "line 1500 │ changed\n").replace(
        "line 10 =", "line 10 ==")
    return Diff.from_texts(before, after, "tall.py", context=10**9)

def drag(view, a, b, pane=0):
    # Press at `a`, move to `b`, release: (frame of the press, frame of the move, after release).
    out = {}
    yield from move(*a)
    out["hover"] = dict(last())
    yield from button(True)
    out["press"] = dict(last())
    yield from move(*b)
    out["drag"] = dict(last())
    yield from wait(2)
    out["held"] = dict(last())
    yield from button(False)
    out["release"] = dict(last())
    yield from move(*PARKED)
    yield from wait(2)
    out["after"] = dict(last())
    return out

def script():
    ts = state["ts"] = typesetter.module()
    report["module"] = ts is not None
    report["ready"] = typesetter.ready()
    report["reason"] = typesetter.reason()
    if ts is None or not typesetter.ready():
        return
    info = ts.build_info()
    report["library"] = {"version": info.version, "imgui": info.imgui_version}
    state["real"] = ts._lib
    ts._lib = Counting(ts._lib, calls)
    demo = Diff.from_texts(read("edit.before.py"), read("edit.after.py"), "edit.py", context=3)
    lb, la = fixed_long_texts()
    long3 = Diff.from_texts(lb, la, "long.py", context=3)
    whole = Diff.from_texts(lb, la, "long.py", context=10**9)
    odd = Diff.from_texts("a\n中 b\nc\n│ d\ne\nf\ng\n", "a\n中 B\nc\n│ d\nE\nf\ng\n", "odd.py")
    yield from move(*PARKED)

    # ---- 1. sizes against DiffView, every case, both layouts ---------------------------
    sizes = report["sizes"] = {}
    for name, diff in (("demo", demo), ("long", long3), ("whole", whole), ("odd", odd)):
        for layout in (UNIFIED, SIDE):
            old = old_view(diff, layout, syntax=syntax)
            widths = (300.0, 860.0, 3000.0)
            hunks = range(min(5, len(diff.files[0].hunks)))
            theirs = oracle(f"sizes/{name} {layout.value}", lambda: {
                "rows": old.row_count, "content_height": old.content_height,
                "row": old.metrics_px.row, "cell": old.metrics_px.cell,
                "content_width": old.content_width,
                "height_for": [old.height_for(w) for w in widths],
                "hunk_rows": [old.row_of_hunk(0, h) for h in hunks],
            })
            began = time.perf_counter()
            new = TypesetDiffView(diff, theme, layout=layout, syntax=syntax)
            made = time.perf_counter() - began
            before_draw = new.content_height
            show(("new", new))
            yield from wait(1)
            first = {key: last()[key] for key in ("calls", "us", "vertices")}
            yield from wait(3)
            sheet = new._described()
            worst = worst_top_error(new)
            calls.clear()
            yield from wait(2)
            sizes[f"{name} {layout.value}"] = {
                "rows": [theirs["rows"], new.row_count],
                "content_height": [theirs["content_height"], new.content_height],
                "height_before_first_draw": before_draw,
                "row": [theirs["row"], new.grid.row, new.row_px],
                "cell": [theirs["cell"], new.grid.cell],
                "content_width": [theirs["content_width"], new.content_width],
                "height_for": [
                    [a, new.height_for(w)] for a, w in zip(theirs["height_for"], widths)
                ],
                "first": first, "steady": dict(last()), "construct_us": round(made * 1e6, 1),
                "blocks": [len(doc) for doc in new.native_documents],
                "most_lines_in_a_block": max(t.count("\n") + 1 for t in sheet.texts[1]),
                "worst_block_top_error_px": worst,
                "edits": dict(new.edits), "marks_built": new.marks_built,
                "lazy": [len(sheet.lazy), sheet.blocks],
                "syntax": [new.syntax_calls, new.syntax_errors],
                "hunk_rows": [
                    [a, new.row_of_hunk(0, h)] for a, h in zip(theirs["hunk_rows"], hunks)
                ],
            }

    # ---- 2. the demo diff, unified: hover, drag, copy, clicks ---------------------------
    view = TypesetDiffView(demo, theme, syntax=syntax)
    show(("new", view))
    yield from wait(4)
    rows = rows_of(view)
    a_row, b_row = rows[1], rows[6]
    a, b = point(view, a_row, 4), point(view, b_row, 9)
    got = yield from drag(view, a, b)
    unified = report["unified"] = {
        "frames": got, "selection": view.selection, "side": view.selection_side,
    }
    unified["expected"] = [at(view, a_row, 4), at(view, b_row, 9)]
    unified["kinds"] = [line_of(view, r)[0].kind.value for r in range(a_row, b_row + 1)]
    unified["text"] = view.selected_text()
    imgui.set_clipboard_text("untouched")
    yield from do(key("mod_ctrl", True), key("c", True))
    unified["copy_frame"] = dict(last())
    yield from do(key("c", False), key("mod_ctrl", False))
    unified["clipboard"] = imgui.get_clipboard_text()
    # After the copy: a selection made in another view takes the turn from this one.
    unified["old_text"] = old_copy("demo", demo, UNIFIED, view.selection, None)
    if DiffView is not None:
        # One selection is current in the process: `DiffView` selecting ends this view's turn.
        other = old_view(demo)
        other.select((0, 0, 0, 0), (0, 0, 1, 2))
    else:
        TypesetDiffView(demo, theme).select((0, 0, 0, 0), (0, 0, 1, 2))
    yield from wait(2)
    unified["after_another_view_selected"] = [view.selection, view.owns_selection]
    unified["marks_built_during"] = view.marks_built
    # A press on the gutter is the start of the line; past the end of a line is its end.
    ox, oy = view.origin
    yield from move(ox + 12.0, a[1])
    yield from button(True)
    unified["gutter_press"] = view.selection
    yield from button(False)
    text = line_of(view, a_row)[0].text
    yield from move(ox + 840.0, a[1])
    yield from button(True)
    unified["past_end_press"] = [view.selection, len(text)]
    yield from button(False)
    # Two clicks: the word under the mouse. A third: the line.
    target = point(view, a_row, len(text) - len(text.lstrip()) + 1)
    column = len(text) - len(text.lstrip()) + 1
    yield from move(*target)
    yield from button(True)
    yield from button(False)
    yield from button(True)
    token = [list(s) for s in tokenize(text) if s[0] <= column < s[1]]
    unified["double"] = [view.selection, token, text]
    yield from button(False)
    yield from button(True)
    unified["triple"] = [view.selection, len(text)]
    yield from button(False)
    yield from move(*PARKED)
    yield from do(key("mod_ctrl", True), key("a", True))
    yield from do(key("a", False), key("mod_ctrl", False))
    def everything():
        old = old_view(demo)
        old.select_all()
        return {"selection": old.selection, "text": old.selected_text()}
    theirs = oracle("select_all/demo unified", everything)
    unified["all"] = [view.selection, theirs["selection"],
                      view.selected_text() == theirs["text"]]
    # A press on a header row begins at the nearest line below it.
    yield from move(*point(view, rows[0] - 1, 3))
    yield from button(True)
    unified["header_press"] = [view.selection, [*line_of(view, rows[0])[1], 0]]
    yield from button(False)
    yield from move(*PARKED)

    # ---- 3. the same view switched to side by side: one side at a time ------------------
    view.set_layout(SIDE)
    yield from wait(4)
    side = report["side"] = {"rows": view.row_count, "steady": dict(last())}
    infos = {r: view.row_info(r) for r in rows_of(view)}
    pairs = [r for r, info in infos.items() if None not in (info.left, info.right)]
    for pane in (0, 1):
        a_row, b_row = pairs[0], pairs[-1]
        got = yield from drag(view, point(view, a_row, 2, pane), point(view, b_row, 7, pane), pane)
        side[str(pane)] = {
            "frames": got, "selection": view.selection, "side": view.selection_side,
            "expected": [at(view, a_row, 2, pane), at(view, b_row, 7, pane)],
            "text": view.selected_text(),
        }
        imgui.set_clipboard_text("untouched")
        yield from do(key("mod_ctrl", True), key("c", True))
        yield from do(key("c", False), key("mod_ctrl", False))
        side[str(pane)]["clipboard"] = imgui.get_clipboard_text()
        side[str(pane)]["old_text"] = old_copy("demo", demo, SIDE, view.selection, pane)

    # ---- 4. collapsed context: a click expands as DiffView.expand does ------------------
    for layout in (UNIFIED, SIDE):
        view = TypesetDiffView(long3, theme, layout=layout, syntax=syntax)
        old = old_view(long3, layout)
        show(("new", view))
        yield from to_top()
        gap = rows_of(view, "gap")[0]
        info = view.row_info(gap)
        before = view.row_count
        edits = dict(view.edits)
        yield from move(*point(view, gap, 5))
        hover = dict(last())
        yield from button(True)
        click = dict(last())
        yield from wait(1)
        after_click = dict(last())
        yield from button(False)
        def expanded(*how):
            old.expand(*how)
            return {"rows": old.row_count, "lefts": lefts(old),
                    "content_height": old.content_height}
        theirs = oracle(f"expand/{layout.value}", lambda: expanded(info.file, info.hunk))
        entry = {"gap_row": gap, "before": before, "after": [theirs["rows"], view.row_count],
                 "hover": hover, "click": click, "next_frame": after_click,
                 "edits": [edits, dict(view.edits)], "selection": view.selection,
                 "same_rows": lefts(view) == theirs["lefts"],
                 "content_height": [theirs["content_height"], view.content_height]}
        # Shift: from the bottom of the gap.
        gap2 = rows_of(view, "gap")[1]
        info2 = view.row_info(gap2)
        view.scroll_to_row(max(0, gap2 - 3))
        yield from wait(3)
        yield from move(*point(view, gap2, 5))
        yield from do(key("mod_shift", True))
        yield from button(True)
        yield from button(False)
        yield from do(key("mod_shift", False))
        theirs = oracle(f"expand/{layout.value}/shift",
                        lambda: expanded(info2.file, info2.hunk, None, "bottom"))
        entry["shift"] = {"after": [theirs["rows"], view.row_count],
                          "same_rows": lefts(view) == theirs["lefts"]}
        yield from move(*PARKED)
        report.setdefault("expand", {})[layout.value] = entry

        # ---- 5. hunk to hunk, and the top row across a layout switch -------------------
        view.scroll_to_row(0)
        yield from wait(3)
        steps = []
        for step in range(3):
            current = view.next_hunk()
            was = view.marks_built
            yield from wait(3)
            theirs = oracle(f"hunks/{layout.value}/{step}", lambda: old.next_hunk())
            steps.append({"current": current, "old": theirs, "top_row": view.top_row,
                          "row_of_hunk": view.row_of_hunk(*current), "visible": visible(view),
                          "marks_built": view.marks_built - was, "calls": list(last()["calls"])})
        top = view.row_info(view.top_row)
        other = SIDE if layout is UNIFIED else UNIFIED
        view.set_layout(other)
        yield from wait(3)
        now = view.row_info(view.top_row)
        report.setdefault("hunks", {})[layout.value] = {
            "steps": steps,
            "kept_top": [[top.kind, top.file, top.hunk], [now.kind, now.file, now.hunk]],
            "scroll_y": last()["scroll_y"]}

    # ---- 6. a pane too narrow: the scrollbar, Shift+wheel, a press while scrolled -------
    view = TypesetDiffView(demo, theme, syntax=syntax)
    show(("new", view), width=420.0)
    yield from to_top()
    bar = report["scrollbar"] = {
        "item": last()["item_size"], "content_height": view.content_height,
        "max": view._max_scroll_x, "content_width": view.content_width, "width": view._width,
    }
    ox, oy = view.origin
    y = oy + view.content_height + 5.0
    yield from move(ox + view._width - 4.0, y)
    yield from button(True)
    bar["track_press"] = view.scroll_x
    yield from move(ox + view._width - 64.0, y)
    bar["dragged"] = view.scroll_x
    yield from button(False)
    bar["selection_after_bar"] = view.selection
    view.scroll_x = 80
    rows = rows_of(view)
    yield from move(*point(view, rows[1], 12))
    yield from do(key("mod_shift", True))
    yield from do(lambda io: io.add_mouse_wheel_event(0.0, -1.0))
    bar["wheel"] = view.scroll_x
    yield from do(key("mod_shift", False))
    view.scroll_x = 80
    yield from wait(1)
    yield from move(*point(view, rows[1], 12))
    yield from button(True)
    bar["press_scrolled"] = [view.selection, [*line_of(view, rows[1])[1], 12], view.scroll_x]
    yield from button(False)
    yield from move(*PARKED)

    # ---- 7. height_cap: a child window that scrolls the rows ---------------------------
    view = TypesetDiffView(long3, theme, syntax=syntax, height_cap=200.0)
    show(("new", view))
    yield from wait(4)
    cap = report["cap"] = {"item": last()["item_size"], "height_for": view.height_for(860.0),
                           "visible": visible(view), "steady": dict(last()),
                           "window_scroll": last()["scroll_y"]}
    current = view.next_hunk()
    current = view.next_hunk()
    yield from wait(3)
    cap["hunk"] = [view.top_row, view.row_of_hunk(*current), visible(view)]
    target = [r for r in rows_of(view) if r > view.top_row][0]
    got = yield from drag(view, point(view, target, 2), point(view, target + 2, 6))
    cap["frames"] = got
    cap["selection"] = [view.selection, at(view, target, 2), at(view, target + 2, 6)]
    cap["owns"] = view.owns_selection
    cap["realised"] = view.blocks_realised
    sheet = view._described()
    cap["visible_are_text"] = all(sheet.row_block[r] not in sheet.lazy for r in view.visible_rows)
    cap["worst"] = worst_top_error(view)

    # ---- 8. glyphs taller than the pitch or not the code face's: every row on the pitch -----
    report["lacks"] = {"odd": list(code_face_lacks("a \u4e2d \u2502 \u03c0 \ufffd b")),
                       "ascii": list(code_face_lacks("plain")),
                       "control": list(code_face_lacks("a\x00b"))}
    for layout in (UNIFIED, SIDE):
        old = old_view(odd, layout)
        theirs = oracle(f"odd/{layout.value}", lambda: {
            "rows": old.row_count, "content_height": old.content_height})
        view = TypesetDiffView(odd, theme, layout=layout)
        show(("new", view))
        yield from wait(4)
        sheet = view._described()
        tops = [
            [doc.block_geometry(b).full_min[1] for b in range(len(doc))]
            for doc in view.native_documents
        ]
        # Each line of the block of hunk rows, in every document: where the library has it.
        rows_block = max(range(sheet.blocks), key=lambda b: sheet.texts[1][b].count("\n"))
        lines = [
            [doc.block_line(rows_block, n).min[1] + doc.block_geometry(rows_block).full_min[1]
             for n in range(sheet.texts[1][rows_block].count("\n") + 1)]
            for doc in view.native_documents
        ]
        heights = [
            [doc.block_line(rows_block, n).max[1] - doc.block_line(rows_block, n).min[1]
             for n in range(sheet.texts[1][rows_block].count("\n") + 1)]
            for doc in view.native_documents
        ]
        rows = rows_of(view)
        entry = {"tops": tops,
                 "row_tops": [view.row_top(sheet.first_row[b]) for b in range(sheet.blocks)],
                 "line_tops": lines, "line_heights": heights,
                 "line_row_tops": [view.row_top(sheet.first_row[rows_block] + n)
                                   for n in range(len(lines[0]))],
                 "block_texts": sheet.texts[1][rows_block],
                 "content_height": [theirs["content_height"], view.content_height],
                 "rows": [theirs["rows"], view.row_count], "item": last()["item_size"],
                 "calls": list(last()["calls"]), "edits": dict(view.edits)}
        # A press on the last row, below every tall glyph, lands on that row.
        yield from move(*point(view, rows[-1], 1))
        yield from button(True)
        entry["press_last"] = [view.selection, [*line_of(view, rows[-1], 0)[1], 1]]
        yield from button(False)
        yield from move(*PARKED)
        report.setdefault("odd", {})[layout.value] = entry

    # ---- 9. a palette change sets the blocks again; nothing else does ------------------
    view = TypesetDiffView(demo, theme)
    show(("new", view))
    yield from wait(3)
    edits = dict(view.edits)
    view.set_palette(DARK_PALETTE)
    yield from wait(2)
    same = dict(view.edits)
    state["scene"]["palette"] = DEFAULT_PALETTE
    yield from wait(2)
    report["palette"] = {"before": edits, "same_palette": same, "other_palette": dict(view.edits)}

    # ---- 10. a stream: a line at a time, from an empty diff ----------------------------
    lines = read("git.diff").splitlines(keepends=True)
    stream = UnifiedDiffStream()
    view = TypesetDiffView(stream.diff, theme, syntax=syntax)
    old = old_view(stream.diff)
    show(("new", view))
    yield from to_top()
    empty = {"rows": view.row_count, "item": last()["item_size"], "calls": list(last()["calls"]),
             "answered": last()["answered"], "edits": dict(view.edits)}
    steps = []
    def fed(snapshot):
        old.set_diff(snapshot)
        return [old.row_count, old.content_height, lefts(old)]
    for number, line in enumerate(lines):
        stream.feed(line)
        view.set_diff(stream.diff)
        theirs = oracle(f"stream/{number}", lambda: fed(stream.diff)[:2])
        sets = view.edits["set"]
        yield from wait(1)
        steps.append([theirs[0], view.row_count, theirs[1], view.content_height,
                      last()["answered"], view.edits["set"] - sets,
                      last()["calls"].count("SetDocumentBlocks")])
    stream.close()
    view.set_diff(stream.diff)
    theirs = oracle("stream/final", lambda: fed(stream.diff))
    yield from wait(2)
    report["stream"] = {"empty": empty, "steps": steps, "lines": len(lines),
                        "edits": dict(view.edits), "final": [theirs[0], view.row_count],
                        "same_rows": lefts(view) == theirs[2], "worst": worst_top_error(view),
                        "steady": dict(last())}

    # ---- 11. a file shown as written, and one that differs only in line endings --------
    others = (("combined", Diff.from_unified(read("combined.diff"))),
              ("eol", Diff.from_texts("a\r\nb\r\nc\r\n", "a\nb\nc\n", "eol.txt")))
    for name, diff in others:
        for layout in (UNIFIED, SIDE):
            view = TypesetDiffView(diff, theme, layout=layout)
            old = old_view(diff, layout)
            theirs = oracle(f"kinds/{name} {layout.value}", lambda: {
                "rows": old.row_count, "content_height": old.content_height})
            show(("new", view))
            yield from to_top()
            entry = {"rows": [theirs["rows"], view.row_count], "steady": dict(last()),
                     "kinds": sorted({view.row_info(r).kind for r in range(view.row_count)}),
                     "content_height": [theirs["content_height"], view.content_height]}
            folds = rows_of(view, "fold")
            if folds:
                yield from move(*point(view, folds[0], 3))
                hand = last()["hand"]
                yield from button(True)
                yield from button(False)
                yield from move(*PARKED)
                def unfolded():
                    old.show_line_endings(0)
                    return old.row_count
                theirs = oracle(f"kinds/{name} {layout.value}/unfolded", unfolded)
                # Every pane's code document: side by side each has one side's endings.
                code = "\n".join(t for texts in view._described().texts[1::2] for t in texts)
                entry["unfolded"] = {
                    "hand": hand, "rows": [theirs, view.row_count],
                    "shown": view.line_endings_shown(0), "steady": dict(last()),
                    "marks": [code.count("\\r\\n"), code.count("\\n")],
                    "selection": view.selection,
                }
            report.setdefault("kinds", {})[f"{name} {layout.value}"] = entry

    # ---- 12. an odd size: the cell is the face's advance, not a whole pixel -------------
    old = old_view(demo, pixel_height=13.0)
    theirs = oracle("small", lambda: {
        "rows": old.row_count, "content_height": old.content_height, "row": old.metrics_px.row,
        "cell": old.metrics_px.cell, "advance": old.metrics_px.advance})
    view = TypesetDiffView(demo, theme, pixel_height=13.0)
    show(("new", view))
    yield from to_top()
    rows = rows_of(view)
    yield from move(*point(view, rows[1], 14))
    yield from button(True)
    small = report["small"] = {
        "rows": [theirs["rows"], view.row_count],
        "content_height": [theirs["content_height"], view.content_height],
        "row": [theirs["row"], view.grid.row],
        "cell": [theirs["cell"], theirs["advance"], view.grid.cell],
        "press": [view.selection, at(view, rows[1], 14)],
        "steady": dict(last()),
    }
    yield from button(False)
    yield from move(*PARKED)
    small["worst"] = worst_top_error(view)

    # ---- 12a. a tall glyph far below the window: nothing below it drifts, seen or not ----
    far = tall_far_down()
    for layout in (UNIFIED, SIDE):
        old = old_view(far, layout)
        theirs = oracle(f"far/{layout.value}", lambda: {
            "rows": old.row_count, "content_height": old.content_height})
        view = TypesetDiffView(far, theme, layout=layout)
        show(("new", view))
        yield from to_top()
        sheet = view._described()
        entry = {"rows": [theirs["rows"], view.row_count],
                 "content_height": [theirs["content_height"], view.content_height],
                 "errors_unseen": last_block_errors(view),
                 "lazy_at_top": [len(sheet.lazy), sheet.blocks],
                 "edits_at_top": dict(view.edits)}
        # A jump past the tall row, which has never been in the window.
        target = view.row_count - 200
        view.scroll_to_row(target)
        yield from wait(1)
        entry["jump_frame"] = list(last()["calls"])     # the scroll is asked for: nothing new shown
        yield from wait(1)
        entry["arrive_frame"] = list(last()["calls"])   # the rows are new: their blocks are made
        yield from wait(2)
        entry["settled"] = list(last()["calls"])
        sheet = view._described()
        shown = sorted({sheet.row_block[r] for r in view.visible_rows})
        whole_sheet = TypesetDiffView(far, theme, layout=layout)._described(whole=True)
        entry["jump"] = {
            "top_row": view.top_row, "target": target, "visible": visible(view),
            "shown_blocks_are_text": all(b not in sheet.lazy for b in shown),
            "texts_are_the_whole_description_s": all(
                sheet.texts[d][b] == whole_sheet.texts[d][b]
                for b in shown for d in range(len(sheet.texts))),
            "lazy": [len(sheet.lazy), sheet.blocks], "edits": dict(view.edits),
            "errors": last_block_errors(view), "worst": worst_top_error(view),
            "answered": last()["answered"], "vertices": last()["vertices"],
        }
        # A press on a row down there finds that row and its column.
        row = view.top_row + 5
        yield from move(*point(view, row, 6))
        yield from button(True)
        entry["press"] = [view.selection, at(view, row, 6, 0)]
        yield from button(False)
        yield from move(*PARKED)
        # Back to the top: those blocks are text already, nothing is handed over.
        was = dict(view.edits)
        yield from to_top()
        entry["back"] = {"edits": [was, dict(view.edits)], "calls": list(last()["calls"])}
        report.setdefault("far", {})[layout.value] = entry

    # ---- 12b. control characters: placeholders, on the rows like anything else ---------------
    ctl = Diff.from_texts("a\x00b\n\tc\nd\n", "a\x00b\n\tc\u202ed\nD\n", "ctl.py")
    old = old_view(ctl)
    theirs = oracle("placeholder", lambda: old.content_height)
    view = TypesetDiffView(ctl, theme)
    show(("new", view))
    yield from to_top()
    sheet = view._described()
    report["placeholder"] = {
        "content_height": [theirs, view.content_height],
        "worst": worst_top_error(view), "errors": last_block_errors(view),
        "code": "\n".join(sheet.texts[1]), "answered": last()["answered"],
        "calls": list(last()["calls"]),
    }

    # ---- 12c. a slip in the view's own Python is itself; the library stays in use ----------
    view = TypesetDiffView(demo, theme)
    show(("new", view))
    yield from wait(3)
    slip = report["slip"] = {"before": dict(last())}
    state["scene"] = None
    yield from wait(1)

    def attempt(view, patch):
        # One draw, in a window of its own, with one method of the view standing in.
        name, stand_in = patch
        real = getattr(view, name)
        setattr(view, name, stand_in)
        imgui.set_next_window_pos(imgui.ImVec2(*POS))
        imgui.set_next_window_size(imgui.ImVec2(860.0, H))
        imgui.begin("slip")
        try:
            view.draw(palette=DARK_PALETTE)
            raised = None
        except Exception as exc:
            raised = [type(exc).__name__, str(exc)]
        finally:
            imgui.end()
            setattr(view, name, real)
        return {"raised": raised, "module": typesetter.module() is not None,
                "ready": typesetter.ready(), "reason": typesetter.reason()}

    def bands(*args, **kwargs):
        raise IndexError("a slip of the view's own")

    def marks(*args, **kwargs):
        raise KeyError("the model's")

    slip["bands"] = attempt(view, ("_bands", bands))
    yield from wait(1)
    slip["marks"] = attempt(view, ("_marks_for", marks))
    yield from wait(1)
    capped = TypesetDiffView(long3, theme, height_cap=200.0)
    slip["capped"] = attempt(capped, ("_bands", bands))
    yield from wait(1)
    show(("new", view))
    yield from wait(3)
    slip["after"] = dict(last())
    slip["trouble"] = typesetter.trouble()

    # ---- 13. times: both views in the same frames, nothing in front of the library -----
    ts._lib = state["real"]
    report["load_before_timing"] = loadavg()
    for name, diff in (("demo", demo), ("long", long3), ("whole", whole)):
        for layout in (UNIFIED, SIDE):
            old = old_view(diff, layout, syntax=syntax)
            new = TypesetDiffView(diff, theme, layout=layout, syntax=syntax)
            entry = {"load": loadavg()}
            which_views = ("old", "new") if old is not None else ("new",)
            show(("old", old), ("new", new), scroll=0.0)
            yield from wait(1)
            entry["first_frame_us"] = [last(w)["us"] for w in which_views]
            yield from wait(6)
            got = {w: [] for w in which_views}
            for _ in range(30):
                yield from wait(1)
                for which in got:
                    got[which].append(last(which)["us"])
            entry["steady_us"] = [statistics.median(got[w]) for w in which_views]
            # Vertices, twice. As the window is, its bottom edge cuts a row: `DiffView` emits
            # the glyphs of that row that are wholly below the edge and the library, since
            # be40444, does not. Then with the window ending on a row's edge, where neither has
            # anything to leave out.
            asked = f"vertices/{name} {layout.value}"
            theirs = oracle(asked + "/cut", lambda: last("old")["vertices"])
            entry["vertices_with_a_cut_row"] = [theirs, last("new")["vertices"]]
            inside = new.origin[1] - POS[1]
            whole_rows = int((H - inside) // new.row_px)
            state["scene"]["height"] = inside + whole_rows * new.row_px
            yield from wait(3)
            theirs = oracle(asked, lambda: last("old")["vertices"])
            entry["vertices"] = [theirs, last("new")["vertices"]]
            entry["whole_rows"] = [whole_rows, list(new.visible_rows)[-1] + 1]
            state["scene"]["height"] = H
            yield from wait(2)
            limit = max(0.0, new.content_height - H)
            got = {w: [] for w in which_views}
            for k in range(30):
                state["scene"]["scroll"] = min(limit, float((k + 1) * 3 * new.row_px))
                yield from wait(1)
                for which in got:
                    got[which].append(last(which)["us"])
            entry["scrolling_us"] = [statistics.median(got[w]) for w in which_views]
            entry["scrolled_to"] = [last(w)["scroll_y"] for w in which_views]
            report["timing"][f"{name} {layout.value}"] = entry

    # ---- 13b. times: a diff that grows a line at a time, `set_diff` each frame --------------
    # The whole-file diff as unified text, fed to a stream: most of it at once, then a line a
    # frame. What a view spends on a frame whose diff is new is its `set_diff` and its `draw`.
    text = whole.to_unified()
    lines = text.splitlines(keepends=True)
    head = len(lines) - 150
    for layout in (UNIFIED, SIDE):
        for where in ("top", "end"):
            stream = UnifiedDiffStream()
            stream.feed("".join(lines[:head]))
            old = old_view(stream.diff, layout, syntax=syntax)
            new = TypesetDiffView(stream.diff, theme, layout=layout, syntax=syntax)
            views = [(w, v) for w, v in (("old", old), ("new", new)) if v is not None]
            show(("old", old), ("new", new), scroll=0.0 if where == "top" else 1e9)
            yield from wait(8)
            asked = f"growing/{layout.value} {where}"
            theirs = oracle(asked + "/before", lambda: old.row_count)
            entry = {"load": loadavg(), "rows_before": [theirs, new.row_count]}
            got = {"old": [], "new": [], "model": []}
            edits = dict(new.edits)
            for line in lines[head:head + 120]:
                began = time.perf_counter()
                stream.feed(line)
                snapshot = stream.diff
                got["model"].append((time.perf_counter() - began) * 1e6)
                spent = {}
                for which, view in views:
                    began = time.perf_counter()
                    view.set_diff(snapshot)
                    spent[which] = (time.perf_counter() - began) * 1e6
                yield from wait(1)
                for which, _ in views:
                    got[which].append(spent[which] + last(which)["us"])
            entry["set_diff_frame_us"] = [statistics.median(got[w]) for w, _ in views]
            entry["model_us"] = statistics.median(got["model"])
            theirs = oracle(asked + "/after", lambda: [old.row_count, old.content_height])
            entry["rows_after"] = [theirs[0], new.row_count]
            entry["heights"] = [theirs[1], new.content_height]
            entry["edits"] = [edits, dict(new.edits)]
            sheet = new._described()
            entry["lazy"] = [len(sheet.lazy), sheet.blocks]
            yield from wait(6)
            got = {w: [] for w, _ in views}
            for _ in range(20):
                yield from wait(1)
                for which in got:
                    got[which].append(last(which)["us"])
            entry["steady_us"] = [statistics.median(got[w]) for w, _ in views]
            report.setdefault("growing", {})[f"{layout.value} {where}"] = entry
    report["load_end"] = loadavg()
    state["final"] = new

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
    scene = state["scene"]
    if scene is None:
        return
    flags = (imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value
             | imgui.WindowFlags_.no_saved_settings.value)
    record = {}
    for name, view in scene["windows"]:
        imgui.set_next_window_pos(imgui.ImVec2(*POS))
        imgui.set_next_window_size(imgui.ImVec2(scene["width"], scene.get("height", H)))
        imgui.begin(name, None, flags)
        try:
            if scene["scroll"] is not None:
                imgui.set_scroll_y(scene["scroll"])
            draw_list = imgui.get_window_draw_list()
            vertices = draw_list.vtx_buffer.size()
            calls.clear()
            began = time.perf_counter()
            answered = view.draw(fonts=loaded[-1], palette=scene.get("palette", DARK_PALETTE))
            spent = time.perf_counter() - began
            size = imgui.get_item_rect_size()
            entry = {
                "calls": list(calls), "us": round(spent * 1e6, 1),
                "vertices": draw_list.vtx_buffer.size() - vertices,
                "item_size": [size.x, size.y],
                "item_hovered": imgui.is_item_hovered(), "item_active": imgui.is_item_active(),
                "any_item_hovered": imgui.is_any_item_hovered(),
                "hand": imgui.get_mouse_cursor() == imgui.MouseCursor_.hand,
                "scroll_y": imgui.get_scroll_y(), "frame": state["n"],
            }
            if name == "new":
                entry.update(answered=answered, selection=view.selection, owns=view.owns_selection,
                             scroll_x=view.scroll_x, marks_built=view.marks_built)
            record[name] = entry
        finally:
            imgui.end()
    state["last"] = record

def before_exit():
    view = state.get("final")
    if view is not None:
        report["trouble"] = typesetter.trouble()
        report["documents_before_unload"] = len(view.native_documents)
        typesetter.unload()
        report["documents_after_unload"] = len(view.native_documents)
        for name, call in (("draw", lambda: view.draw()),
                           ("height_for", lambda: view.height_for(500.0)),
                           ("content_width", lambda: view.content_width)):
            try:
                call()
                report[name + "_after_unload"] = "answered"
            except TypesetUnavailable as exc:
                report[name + "_after_unload"] = str(exc)
        report["rows_after_unload"] = view.row_count
        report["module_after_unload"] = typesetter.module() is not None

state["script"] = script()
runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "TypesetDiffView under test"
runner.app_window_params.window_geometry.size = (900, 700)
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
report["frame_count"] = state["n"]
report["finished"] = state["done"]
print("REPORT " + json.dumps(report))
"""

_L, _D, _HIT = "LayoutDocument", "DrawDocument", "HitTestDocument"
_UNIFIED_FRAME = [_L, _D, _L, _D]
_SIDE_FRAME = _UNIFIED_FRAME * 2


@pytest.fixture(scope="module")
def report(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    script = window.out / "typeset_diff_view_driver.py"
    script.write_text(_DRIVER, encoding="utf-8")
    done = window.run([str(script), str(_ROOT)], timeout=420.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-6000:]
    got = _report_of(done.stdout)
    # In the child, not here: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert (
        got["finished"] is True and "load_end" in got
    ), "the driver's script did not reach its end"
    missing = [str(v) for v in _walk(got) if isinstance(v, str) and v.startswith("NOT FROZEN: ")]
    assert not missing, f"DiffView is gone and {_ANSWERS.name} has no answer for: {missing[:5]}"
    return got


def _walk(value: Any) -> Any:
    if isinstance(value, dict):
        for inner in value.values():
            yield from _walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner)
    else:
        yield value


def test_the_frozen_window_answers_are_what_diff_view_answered_in_this_run(
    report: dict[str, Any], frozen: dict[str, Any]
) -> None:
    """
    While `DiffView` exists the driver asks IT (sizes, copies, expansions,
    hunks, a stream's rows, vertex counts) and writes down what it said; this
    holds the file to that. When it is gone the driver reads the file, and
    this says so and skips.
    """
    if report["oracle_is"] != "DiffView":
        pytest.skip(f"DiffView is gone: the window half was held to {_ANSWERS.name}")
    assert report["oracle"].keys() == frozen["window"].keys()
    for key, value in frozen["window"].items():
        assert report["oracle"][key] == value, key
    assert len(frozen["window"]) > 60


def _frame_of(layout: str) -> list[str]:
    return _UNIFIED_FRAME if layout == "unified" else _SIDE_FRAME


def test_rows_and_heights_are_diff_view_s_in_every_case(
    report: dict[str, Any],
) -> None:
    """
    Row count and content height equal `DiffView`'s in all eight -- the made-up
    diff with U+4E2D and U+2502 and the whole-file diff with its hundred and
    sixty lines outside ASCII included: with `BlockFlags.FixedLineHeight` no
    row is taller than the pitch, and there is no `extra_height` to add.
    """
    sizes = report["sizes"]
    assert len(sizes) == 8
    for name, entry in sizes.items():
        old_rows, new_rows = entry["rows"]
        assert old_rows == new_rows > 0, name
        old_height, new_height = entry["content_height"]
        assert new_height == old_height == new_rows * entry["row"][0], name
        assert entry["height_before_first_draw"] == old_height, name
        assert entry["row"][0] == entry["row"][1] == entry["row"][2], name
        for theirs, ours in entry["hunk_rows"]:
            assert theirs == ours, name


def test_widths_follow_the_library_s_cell_and_the_scrollbar_s_room_is_the_same(
    report: dict[str, Any],
) -> None:
    """
    The cell is the device's whole pixel, which at the theme's size is
    DiffView's 8 px exactly, so widths agree exactly and so does `height_for`
    (which adds the scrollbar exactly when a line is too long).

    **Tightened on imtypeset 0.4.1.** Until then the cell was the face's own
    advance, DiffView's 8 px "to a few millionths" (7.999988555908203), and
    this asserted `approx(old_cell, abs=1e-3)` and widths to a hundredth of a
    pixel (695.9990 for 696). The grid now takes the cell from
    `device_glyph_advance` on the whole pixel it is within 2e-5 of.
    """
    for name, entry in report["sizes"].items():
        old_cell, new_cell = entry["cell"]
        assert new_cell == old_cell == 8, name
        old_width, new_width = entry["content_width"]
        assert new_width == old_width, name
        for theirs, ours in entry["height_for"]:
            assert ours == theirs, name


def test_a_frame_is_two_calls_a_document_and_a_hit_test_only_while_pressing(
    report: dict[str, Any],
) -> None:
    """
    The budget, counted at the ctypes library: `layout` and `draw` for each
    document -- 4 unified, 8 side by side -- whatever the diff's length; one
    `hit_test` on the frame of a press and on each frame of a drag; nothing
    for a hover, a release, a copy, or holding still.
    """
    for name, entry in report["sizes"].items():
        frame = _frame_of(name.split(" ", 1)[1])
        assert entry["steady"]["calls"] == frame, name
        assert entry["steady"]["vertices"] > 100 and entry["steady"]["answered"] is True, name
        # The first frame makes the documents and measures a cell; it is not the budget.
        assert entry["first"]["calls"][-len(frame) :] == frame, name
        assert entry["first"]["calls"].count("SetDocumentBlocks") >= len(frame) // 2, name
        assert entry["most_lines_in_a_block"] <= CHUNK, name
    frames = report["unified"]["frames"]
    assert frames["hover"]["calls"] == _UNIFIED_FRAME
    assert frames["press"]["calls"] == [*_UNIFIED_FRAME, _HIT]
    assert frames["drag"]["calls"] == [*_UNIFIED_FRAME, _HIT]
    assert frames["held"]["calls"] == [*_UNIFIED_FRAME, _HIT]
    assert frames["release"]["calls"] == [*_UNIFIED_FRAME, _HIT]  # the frame the button comes up
    assert frames["after"]["calls"] == _UNIFIED_FRAME
    assert report["unified"]["copy_frame"]["calls"] == _UNIFIED_FRAME
    for pane in ("0", "1"):
        frames = report["side"][pane]["frames"]
        assert frames["hover"]["calls"] == _SIDE_FRAME
        assert frames["press"]["calls"] == [*_SIDE_FRAME, _HIT]
        assert frames["drag"]["calls"] == [*_SIDE_FRAME, _HIT]
        assert frames["after"]["calls"] == _SIDE_FRAME
    assert report["cap"]["steady"]["calls"] == _UNIFIED_FRAME


def test_the_whole_file_diff_is_in_blocks_and_its_documents_are_on_the_rows(
    report: dict[str, Any],
) -> None:
    """Thousands of rows: block tops are where the row table says, in every document."""
    for name, entry in report["sizes"].items():
        assert entry["worst_block_top_error_px"] < 0.1, name
        assert len(set(entry["blocks"])) == 1, name
    whole = report["sizes"]["whole unified"]
    assert whole["rows"][1] > 4000 and whole["blocks"][0] > whole["rows"][1] // CHUNK
    assert whole["syntax"][1] == 0 and whole["syntax"][0] > 0


def test_the_view_is_no_item_until_a_press_and_one_until_the_release(
    report: dict[str, Any],
) -> None:
    frames = report["unified"]["frames"]
    assert frames["hover"]["item_hovered"] is True
    assert frames["hover"]["any_item_hovered"] is False
    assert frames["hover"]["item_active"] is False
    for name in ("press", "drag", "held"):
        assert frames[name]["item_active"] is True, name
    assert frames["after"]["item_active"] is False
    # Whichever item it is, it claims the same rectangle: the rows, and no more.
    sizes = {tuple(frames[name]["item_size"]) for name in frames}
    assert len(sizes) == 1
    demo = report["sizes"]["demo unified"]
    assert frames["hover"]["item_size"][1] == demo["content_height"][1]
    # The selection is drawn: more goes to the draw list once there is one.
    assert frames["after"]["vertices"] > frames["hover"]["vertices"]


def test_a_drag_selects_model_positions_and_the_copy_is_diff_view_s(
    report: dict[str, Any],
) -> None:
    """
    Unified, across a removed and two added lines: the positions are the rows
    and the columns pressed and released on, the text is what `DiffView`
    copies for that selection (the removed line left out), and Ctrl+C puts
    exactly that on the clipboard.
    """
    unified = report["unified"]
    frames = unified["frames"]
    assert frames["press"]["owns"] is True
    start, end = frames["press"]["selection"]
    assert start == end == unified["expected"][0]  # a caret
    assert unified["selection"] == unified["expected"]
    assert frames["drag"]["selection"] == frames["after"]["selection"] == unified["expected"]
    assert unified["side"] is None
    assert "-" in unified["kinds"] and "+" in unified["kinds"]
    assert unified["text"] == unified["old_text"] != ""
    assert unified["text"].count("\n") == len(unified["kinds"]) - 1 - unified["kinds"].count("-")
    assert unified["clipboard"] == unified["text"]
    # One selection is current in the process: `DiffView` selecting ended this view's.
    assert unified["after_another_view_selected"] == [None, False]


def test_a_press_on_the_gutter_past_a_line_s_end_and_on_a_header(report: dict[str, Any]) -> None:
    unified = report["unified"]
    line = unified["expected"][0][:3]
    assert unified["gutter_press"] == [[*line, 0], [*line, 0]]
    selection, size = unified["past_end_press"]
    assert selection == [[*line, size], [*line, size]]
    selection, first_line = unified["header_press"]
    assert selection == [first_line, first_line]


def test_two_clicks_select_a_word_three_the_line_and_ctrl_a_everything(
    report: dict[str, Any],
) -> None:
    unified = report["unified"]
    line = unified["expected"][0][:3]
    selection, token, text = unified["double"]
    ((start, end),) = token
    assert selection == [[*line, start], [*line, end]] and end - start > 1, text
    selection, size = unified["triple"]
    assert selection == [[*line, 0], [*line, size]]
    ours, theirs, same_text = unified["all"]
    assert ours == theirs and ours is not None and same_text is True


def test_side_by_side_selects_one_side_and_copies_what_diff_view_copies(
    report: dict[str, Any],
) -> None:
    side = report["side"]
    assert side["rows"] == report["sizes"]["demo side-by-side"]["rows"][1]
    assert side["steady"]["calls"] == _SIDE_FRAME
    for pane in (0, 1):
        entry = side[str(pane)]
        assert entry["side"] == pane
        assert entry["selection"] == entry["expected"], pane
        assert entry["text"] == entry["old_text"] != "", pane
        assert entry["clipboard"] == entry["text"], pane
    # The two sides are different texts: the edit is between them.
    assert side["0"]["text"] != side["1"]["text"]


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_a_click_on_collapsed_context_expands_as_diff_view_does(
    report: dict[str, Any], layout: str
) -> None:
    """
    The hand over the row, no selection begun, the rows `DiffView.expand`
    gives; and the edit is ONE `replace_blocks` per document, on the next
    frame, with nothing set again.
    """
    entry = report["expand"][layout]
    frame = _frame_of(layout)
    assert entry["hover"]["hand"] is True
    assert entry["hover"]["calls"] == frame
    assert entry["click"]["calls"] == frame  # no hit test: the press began no selection
    assert entry["selection"] is None
    old_rows, new_rows = entry["after"]
    assert old_rows == new_rows == entry["before"] + 20
    assert entry["same_rows"] is True
    assert entry["content_height"][0] == entry["content_height"][1]
    replaced = [call for call in entry["next_frame"]["calls"] if call == "ReplaceDocumentBlocks"]
    assert len(replaced) == len(frame) // 2
    # Nothing is set again, and no document is made: nothing is measured any more.
    assert entry["next_frame"]["calls"] == ["ReplaceDocumentBlocks"] * len(replaced) + frame
    before, after = entry["edits"]
    assert after["set"] == before["set"] and after["replace"] == before["replace"] + len(frame) // 2
    old_rows, new_rows = entry["shift"]["after"]
    assert old_rows == new_rows > entry["after"][1] and entry["shift"]["same_rows"] is True


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_next_hunk_scrolls_its_header_to_the_top_and_a_layout_switch_keeps_the_top(
    report: dict[str, Any], layout: str
) -> None:
    entry = report["hunks"][layout]
    frame = _frame_of(layout)
    seen = []
    for step in entry["steps"]:
        assert step["current"] == step["old"]
        assert step["top_row"] == step["row_of_hunk"]
        first, stop = step["visible"]
        assert first <= step["top_row"] < stop and stop - first <= 40
        assert step["calls"] == frame  # settled: nothing but the frame
        assert 1 <= step["marks_built"] <= 3  # rebuilt for the new rows, not every frame
        seen.append(tuple(step["current"]))
    assert len(set(seen)) == 3
    before, after = entry["kept_top"]
    assert before == after and entry["scroll_y"] > 0.0


def test_a_narrow_pane_gets_the_scrollbar_and_the_code_scrolls_under_the_gutter(
    report: dict[str, Any],
) -> None:
    bar = report["scrollbar"]
    assert bar["content_width"] > bar["width"] and bar["max"] > 0
    assert bar["item"][1] == bar["content_height"] + 10.0  # half a row, as DiffView's
    assert bar["track_press"] == bar["max"]  # a press at the far end of the track
    assert 0 < bar["dragged"] < bar["track_press"]
    assert bar["selection_after_bar"] is None  # the bar is an item: no selection began
    assert bar["wheel"] == 80 + 32  # Shift+wheel: four cells
    selection, expected, scroll_x = bar["press_scrolled"]
    assert scroll_x == 80 and selection == [expected, expected]


def test_height_cap_is_a_child_that_scrolls_and_selects(report: dict[str, Any]) -> None:
    cap = report["cap"]
    assert cap["item"][1] == cap["height_for"] == 200.0
    first, stop = cap["visible"]
    assert first == 0 and stop <= 12  # culled to the child, not to the diff
    assert cap["window_scroll"] == 0.0
    top_row, hunk_row, (first, stop) = cap["hunk"]
    assert top_row == hunk_row > 0 and first <= top_row < stop
    selection, start, end = cap["selection"]
    assert selection == [start, end] and cap["owns"] is True
    assert cap["frames"]["press"]["calls"] == [*_UNIFIED_FRAME, _HIT]
    # The child's scroll is not known before it is begun: the rows it turned out to show
    # were made into text all the same, and every block is where the row table has it.
    assert cap["realised"] >= 1 and cap["visible_are_text"] is True and cap["worst"] < 0.1


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_a_glyph_taller_than_the_pitch_or_borrowed_moves_no_row_in_any_document(
    report: dict[str, Any], layout: str
) -> None:
    """
    FS-S1's hole, closed by the library's `FixedLineHeight` and measured in
    the window: U+4E2D and U+2502 are set 21.9 and 22.4 px tall and their
    lines are 20 px all the same. Every document's blocks, and every LINE of
    the block holding them, are on the view's rows to a hundredth of a pixel;
    the height is `DiffView`'s; a frame is the budget and nothing was measured
    to get there; and a press below them finds its row.
    """
    entry = report["odd"][layout]
    frame = _frame_of(layout)
    assert len(entry["tops"]) == len(frame) // 2
    for tops in entry["tops"]:
        assert len(tops) == len(entry["row_tops"])
        for top, expected in zip(tops, entry["row_tops"], strict=True):
            assert abs(top - expected) < 0.01
    assert "│ d" in entry["block_texts"] and "中" in entry["block_texts"]
    assert len(entry["line_row_tops"]) >= 5
    for document, tops in enumerate(entry["line_tops"]):
        for top, expected in zip(tops, entry["line_row_tops"], strict=True):
            assert abs(top - expected) < 0.01, document
    for heights in entry["line_heights"]:
        assert all(abs(height - 20.0) < 0.01 for height in heights)
    assert entry["rows"][0] == entry["rows"][1]
    assert entry["content_height"][0] == entry["content_height"][1] == entry["rows"][1] * 20.0
    assert entry["item"][1] == entry["content_height"][1]
    assert entry["calls"] == frame and entry["edits"] == {"set": len(frame) // 2, "replace": 0}
    selection, expected = entry["press_last"]
    assert selection == [expected, expected]


def test_which_characters_the_code_face_lacks_is_the_library_s_answer(
    report: dict[str, Any],
) -> None:
    """
    `code_face_lacks`, in the window with the bundled faces: U+4E2D and U+03C0
    are not in the code face (the library sets them from another, at that
    face's advance); U+2502 -- taller than the pitch -- and the placeholder
    U+FFFD ARE in it. A control character is asked about as its placeholder.
    """
    lacks = report["lacks"]
    assert lacks["odd"] == ["中", "π"] and lacks["ascii"] == [] and lacks["control"] == []


def test_a_stream_is_drawn_from_empty_a_line_at_a_time_by_replacing_the_tail(
    report: dict[str, Any],
) -> None:
    """
    `set_diff` per line of a git diff: at every step the rows and the height
    `DiffView` has for the same snapshot, everything in view set as asked,
    and the blocks never set again -- an edit is `replace_blocks` from the
    first block that differs. An empty diff draws nothing and claims nothing.
    """
    stream = report["stream"]
    empty = stream["empty"]
    assert empty["rows"] == 0 and empty["item"][1] == 0.0 and empty["answered"] is True
    assert empty["calls"] == [] and empty["edits"] == {"set": 2, "replace": 0}
    assert len(stream["steps"]) == stream["lines"] > 20
    for old_rows, new_rows, old_height, new_height, answered, sets, library in stream["steps"]:
        assert old_rows == new_rows and old_height == new_height
        # Nothing is set again, by the view or by anything on its behalf (a line used to be
        # measured in a scratch document when it might hold a borrowed glyph).
        assert answered is True and sets == 0 and library == 0
    assert stream["steps"][-1][1] > 20
    assert stream["final"][0] == stream["final"][1] and stream["same_rows"] is True
    assert stream["edits"]["set"] == 2
    assert 2 <= stream["edits"]["replace"] <= 2 * (stream["lines"] + 1)
    assert stream["worst"] < 0.1 and stream["steady"]["calls"] == _UNIFIED_FRAME


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_a_raw_file_and_a_folded_one_are_drawn_and_the_fold_opens_on_a_click(
    report: dict[str, Any], layout: str
) -> None:
    kinds = report["kinds"]
    frame = _frame_of(layout)
    raw = kinds[f"combined {layout}"]
    assert raw["rows"][0] == raw["rows"][1] and "raw" in raw["kinds"]
    assert raw["content_height"][0] == raw["content_height"][1]
    assert raw["steady"]["calls"] == frame and raw["steady"]["answered"] is True
    assert raw["steady"]["vertices"] > 100
    folded = kinds[f"eol {layout}"]
    assert folded["rows"] == [2, 2] and folded["kinds"] == ["file", "fold"]
    opened = folded["unfolded"]
    assert opened["hand"] is True and opened["shown"] is True
    assert opened["rows"][0] == opened["rows"][1] > 2
    assert opened["selection"] is None  # the click opened the fold and began no selection
    assert opened["steady"]["calls"] == frame
    # The ending that is the change is said after each line, as `DiffView` says it.
    with_cr, with_lf = opened["marks"]
    assert with_cr == 3 and with_lf == 6


def test_at_an_odd_size_the_cell_is_diff_view_s_whole_pixel_and_a_press_still_finds_its_column(
    report: dict[str, Any],
) -> None:
    """
    At `pixel_height=13` the code face's advance in the font file is 6.196
    px; `DiffView` drew on a 6 px pitch (its rounded cell), and so does this
    view: 6.0 exactly. Rows and heights are the same; the column under a
    press is the library's.

    **Restated on imtypeset 0.4.1.** This was
    `test_at_an_odd_size_the_cell_is_the_face_s_advance_and_a_press_still_finds_its_column`
    and asserted the DIFFERENCE: `new_cell == approx(old_advance)` (6.196)
    and `abs(new_cell - old_cell) > 0.1`, "the library sets the face at its
    own advance ... cell 14 is 2.7 px further right here than in `DiffView`".
    The library now lays the code face out on the advance the rasteriser
    bakes (imtypeset's H34), which at 13 px is `DiffView`'s 6, so the stated
    difference is gone and the equality is what is held.
    """
    small = report["small"]
    assert small["rows"][0] == small["rows"][1]
    assert small["content_height"][0] == small["content_height"][1]
    assert small["row"][0] == small["row"][1]
    old_cell, old_advance, new_cell = small["cell"]
    assert old_advance == pytest.approx(6.196368, abs=1e-5)
    assert old_cell == round(old_advance) == 6
    assert new_cell == old_cell
    selection, expected = small["press"]
    assert selection == [expected, expected] and expected[3] == 14
    assert small["steady"]["answered"] is True and small["steady"]["vertices"] > 100
    assert small["worst"] < 0.05


def test_only_a_change_of_the_diff_inks_sets_the_blocks_again(report: dict[str, Any]) -> None:
    palette = report["palette"]
    assert palette["same_palette"] == palette["before"]
    assert palette["other_palette"]["set"] == palette["before"]["set"] + 2


def test_after_unload_the_view_refuses_and_keeps_its_rows(report: dict[str, Any]) -> None:
    """`typesetter.unload()` closes the documents; what needs the library says so."""
    assert report["trouble"] == ""
    assert report["documents_before_unload"] in (2, 4)
    assert report["documents_after_unload"] == 0
    for name in ("draw", "height_for", "content_width"):
        assert report[name + "_after_unload"].startswith("imtypeset cannot draw"), name
    assert report["rows_after_unload"] > 0
    assert report["module_after_unload"] is True


def test_the_times_were_taken(report: dict[str, Any]) -> None:
    """
    Read, not asserted: the result file has the ratios and the load they were
    taken at. Two times a case while `DiffView` is there to be timed beside
    this view, one when it is not.
    """
    timing = report["timing"]
    assert len(timing) == 6
    views = 2 if report["oracle_is"] == "DiffView" else 1
    for name, entry in timing.items():
        assert len(entry["steady_us"]) == len(entry["scrolling_us"]) == views, name
        assert all(value > 0 for value in entry["steady_us"] + entry["scrolling_us"]), name
        assert entry["vertices"][1] > 100, name
        if not name.startswith("demo"):
            assert len(set(entry["scrolled_to"])) == 1 and entry["scrolled_to"][0] > 0.0, name


def test_the_same_number_of_vertices_reach_the_draw_list_as_diff_view_s(
    report: dict[str, Any],
) -> None:
    """
    Both views at the top of the same diff, in the same rectangle with the
    same highlighter: a quad a glyph and a quad a band in both, so the counts
    are equal when nothing is missing and nothing is extra. A count, not a
    statement about where anything is or how it looks.

    **Restated at T4-DIFF, with the reason.** The count is taken with the
    window ending on a row's edge. As the driver's window is (660 px), its
    bottom edge cuts row 31 in half, and the two views then differ by what
    is wholly BELOW that edge: `DiffView` hands Dear ImGui every glyph of a
    row any of which is in the window, and the library, since its commit
    `be40444`, does not emit a glyph whose quad is wholly outside the clip
    rectangle (`../imtypeset/docs/advtext-swap-status.md`, "slices of a
    document under clips that meet"). Measured before the restatement, on
    `long_texts()`: 4,720 against 4,732 -- the three full stops of
    `... N unchanged lines`, whose quads are at y 672 to 675 under a clip
    ending at 670 (`.concerns/T4-DIFF-scripts/probe_vertices.out.json`).
    Nothing that could be seen differs. So: equal on whole rows, and with the
    cut row never MORE than `DiffView`'s.
    """
    for name, entry in report["timing"].items():
        theirs, ours = entry["vertices"]
        assert ours == theirs, name
        theirs, ours = entry["vertices_with_a_cut_row"]
        assert ours <= theirs, name
        if not name.startswith("demo"):
            # The window was full of rows, so the cut row was there to be cut.
            assert entry["whole_rows"][0] == entry["whole_rows"][1] > 20, name


# ---------------------------------------------------------------------------
# 3. T3-C: the lazy description, the review's findings
# ---------------------------------------------------------------------------


def test_a_long_diff_s_first_frame_makes_text_only_for_the_blocks_it_shows(
    report: dict[str, Any],
) -> None:
    """
    On the whole-file diff (thousands of rows, one hunk) the first frame hands
    over every block -- so every row is where it will be -- and the text of
    the ones the window meets; the rest are stand-ins. ONE `set_blocks` a
    document, and nothing else: no line is measured first.
    """
    for name, entry in report["sizes"].items():
        frame = _frame_of(name.split(" ", 1)[1])
        assert entry["edits"] == {"set": len(frame) // 2, "replace": 0}, name
        # The documents, and the one-block document a cell is measured in (once per size).
        made = entry["first"]["calls"].count("CreateDocument")
        assert len(frame) // 2 <= made <= len(frame) // 2 + 1, name
        assert entry["first"]["calls"].count("SetDocumentBlocks") == made, name
        assert "GetDocumentBlockGeometry" not in entry["first"]["calls"], name
    for name in ("whole unified", "whole side-by-side"):
        lazy, blocks = report["sizes"][name]["lazy"]
        # 64 rows a block and nothing alone in a block of its own: 4,000 rows are 63 blocks or
        # so, where the 160 lines outside ASCII used to make it some 380.
        rows = report["sizes"][name]["rows"][1]
        assert rows // CHUNK < blocks <= rows // CHUNK + 4 and lazy >= blocks - 4, name
        # 660 px of 20 px rows: no more than a block or two of hunk rows are text.
        assert report["sizes"][name]["rows"][1] > 3000
    lazy, _ = report["sizes"]["demo unified"]["lazy"]
    assert lazy == 0  # all of a short diff is in the window


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_rows_below_a_tall_glyph_that_was_never_in_the_window_are_on_the_rows(
    report: dict[str, Any], layout: str
) -> None:
    """
    T3-C found, by a run, that the library took a block it had not laid out to
    be as tall as its lines' pitch, so a line with a taller glyph that had
    never been in the window left every row below it 2.4 px too high in the
    ONE document that held it; it laid each such block out at hand-over. With
    `FixedLineHeight` the block IS its lines' pitch, laid out or not, and that
    is gone. Asked here before anything above the last block is asked: every
    document has it where its row is, and the height is `DiffView`'s. Then
    the jump: one `replace_blocks` a document on the frame the rows arrive,
    the text is the whole description's, a press finds its row, and coming
    back hands over nothing.
    """
    entry = report["far"][layout]
    frame = _frame_of(layout)
    documents = len(frame) // 2
    assert entry["rows"][0] == entry["rows"][1] > 3000
    assert entry["content_height"][1] == entry["content_height"][0]
    assert len(entry["errors_unseen"]) == documents
    assert all(abs(error) < 0.1 for error in entry["errors_unseen"]), entry["errors_unseen"]
    lazy, blocks = entry["lazy_at_top"]
    assert lazy >= blocks - 4 and entry["edits_at_top"] == {"set": documents, "replace": 0}
    assert entry["jump_frame"] == frame
    assert entry["arrive_frame"] == ["ReplaceDocumentBlocks"] * documents + frame
    assert entry["settled"] == frame
    jump = entry["jump"]
    assert jump["top_row"] == jump["target"]
    assert jump["shown_blocks_are_text"] and jump["texts_are_the_whole_description_s"]
    assert jump["edits"] == {"set": documents, "replace": documents}
    assert all(abs(error) < 0.1 for error in jump["errors"]) and jump["worst"] < 0.1
    assert jump["answered"] is True and jump["vertices"] > 100
    selection, expected = entry["press"]
    assert selection == [expected, expected] and expected[3] == 6
    before, after = entry["back"]["edits"]
    assert before == after and entry["back"]["calls"] == frame


def test_a_line_of_placeholders_is_on_the_rows(report: dict[str, Any]) -> None:
    """
    R9d (SW-R1) asked whether a line holding U+FFFD could be taller than the
    pitch and move the rows below; T3-C measured one per size to find out.
    With `FixedLineHeight` the question cannot arise and nothing is measured:
    the height is `DiffView`'s and every block is on its row.
    """
    entry = report["placeholder"]
    assert CONTROL_PLACEHOLDER in entry["code"] and "\x00" not in entry["code"]
    assert entry["content_height"][0] == entry["content_height"][1]
    assert entry["worst"] < 0.05 and all(abs(error) < 0.05 for error in entry["errors"])
    assert entry["answered"] is True and entry["calls"] == _UNIFIED_FRAME


def test_a_slip_in_the_view_s_own_python_is_raised_as_itself_and_the_library_stays_on(
    report: dict[str, Any],
) -> None:
    """
    R9c (SW-R1), in a window: an `IndexError` from the view's band drawing and
    a `KeyError` from under its marks leave `draw` as themselves, with and
    without `height_cap`; `typesetter.module()` is still there, `ready()`
    still true, and the next frames draw what the frames before did.
    """
    slip = report["slip"]
    assert slip["bands"]["raised"] == ["IndexError", "a slip of the view's own"]
    assert slip["marks"]["raised"][0] == "KeyError"
    assert slip["capped"]["raised"] == ["IndexError", "a slip of the view's own"]
    for name in ("bands", "marks", "capped"):
        assert slip[name]["module"] is True and slip[name]["ready"] is True, name
        assert slip[name]["reason"] == "", name
    assert slip["trouble"] == ""
    assert slip["after"]["answered"] is True
    assert slip["after"]["calls"] == _UNIFIED_FRAME == slip["before"]["calls"]
    assert slip["after"]["vertices"] == slip["before"]["vertices"] > 100


def test_the_times_of_a_growing_diff_were_taken(report: dict[str, Any]) -> None:
    """
    Read, not asserted, as the other times: the result files under `.concerns/`
    have the ratios. What IS held: at every step both views have the same rows,
    and a line that arrives is one `replace_blocks` a document at most.
    """
    growing = report["growing"]
    assert len(growing) == 4
    for name, entry in growing.items():
        documents = 2 if name.startswith("unified") else 4
        assert entry["rows_before"][0] == entry["rows_before"][1] > 2000, name
        assert entry["rows_after"][0] == entry["rows_after"][1] > entry["rows_before"][1], name
        assert entry["heights"][1] == entry["heights"][0], name
        before, after = entry["edits"]
        assert after["set"] == before["set"], name
        assert 0 < after["replace"] - before["replace"] <= 120 * documents, name
        assert all(value > 0 for value in entry["set_diff_frame_us"] + entry["steady_us"]), name


# ---------------------------------------------------------------------------
# 3. Whether a file's header fit (`headers`, pptmstr's P16)
# ---------------------------------------------------------------------------

_LONG_LABEL = "a/very/long/" + "deep/" * 18 + "file.py"
_VERDICT = "may not apply: anchor not found in file"


@pytest.mark.parametrize("layout", [UNIFIED, SIDE])
def test_headers_are_each_file_s_text_and_warning_in_the_order_drawn(
    diffs: dict[str, Diff], frozen: dict[str, Any], layout: str
) -> None:
    """
    Without the library: a `DiffHeader` a file, in file order, at the file's
    header row, saying what the row says -- `DiffView`'s wording, frozen --
    with the warning apart from the text and no width guessed.
    """
    for name, diff in _header_cases(diffs).items():
        rows = _mine(diff, layout)
        headers = rows.headers()
        assert [header.file for header in headers] == list(range(len(diff.files))), name
        assert [header.row for header in headers] == [
            row for row in range(rows.row_count) if rows.row_info(row).kind == "file"
        ], name
        sheet = rows._described()
        said = frozen["pure"]["texts"]["headers"][name]
        for header, (text, warning) in zip(headers, said, strict=True):
            assert header.text == module._shown(text)[0], name
            assert header.warning == module._shown(warning)[0].removeprefix("  "), name
            assert not header.warning or header.warning.startswith("! "), name
            # What the row's own line is, after the cell it is set in from.
            assert sheet.texts[0][sheet.row_block[header.row]] == " " + header.line, name
            assert header.width_px is None and header.text_width_px is None, name
            assert header.available_px is None, name
            assert header.fits is None and header.text_fits is None, name
        assert rows.headers() == headers, name


def test_a_header_s_warnings_are_in_the_order_drawn_and_a_control_is_as_shown() -> None:
    """
    pptmstr's case (`test_a_diff_header_too_long_for_its_view_is_said_above_it_
    warning_first`): the text is the path and its counts, the warning is the
    host's verdict behind `! `. Two files are two headers; what else the view
    warns of follows the verdict; a control character of a label is the
    placeholder the row shows, not the character.
    """
    one = Diff.from_texts("a\n", "b\n", _LONG_LABEL, will_not_apply=_VERDICT)
    (header,) = DiffRows(one).headers()
    assert (header.file, header.row) == (0, 0)
    assert header.text == f"{_LONG_LABEL}  +1 -1"
    assert header.warning == f"! {_VERDICT}"
    assert header.line == f"{_LONG_LABEL}  +1 -1  ! {_VERDICT}"

    plain = Diff.from_texts("a\n", "b\n", "x.py")
    (header,) = DiffRows(plain).headers()
    assert (header.text, header.warning, header.line) == ("x.py  +1 -1", "", "x.py  +1 -1")

    odd = Diff.from_texts("a\x00b\n", "a\x00c\n", "ctl\x07.py", will_not_apply="no")
    two = Diff((*plain.files, *odd.files))
    first, second = DiffRows(two).headers()
    assert (first.file, first.row, second.file) == (0, 0, 1)
    assert second.row == DiffRows(plain).row_count
    assert second.text == f"ctl{CONTROL_PLACEHOLDER}.py  +1 -1"
    assert second.warning == "! no  ! contains control characters"
    assert DiffRows(Diff(())).headers() == ()


def test_a_header_fits_when_its_width_is_inside_what_it_was_cut_at_and_none_is_not_a_guess() -> (
    None
):
    header = module.DiffHeader(file=0, row=0, text="x.py  +1 -1", warning="! no")
    assert header.fits is None and header.text_fits is None
    measured = module.DiffHeader(0, 0, "x.py  +1 -1", "! no", width_px=144.0, text_width_px=96.0)
    assert measured.fits is None and measured.text_fits is None  # never drawn: no width to fit

    def at(available: float) -> Any:
        return module.DiffHeader(0, 0, "x.py  +1 -1", "! no", 144.0, 96.0, available)

    assert (at(144.0).fits, at(144.0).text_fits) == (True, True)
    assert (at(143.0).fits, at(143.0).text_fits) == (False, True)  # only the warning is cut
    assert (at(95.0).fits, at(95.0).text_fits) == (False, False)
    with pytest.raises(AttributeError):
        measured.text = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("width", "error"),
    [("420", TypeError), (True, TypeError), ([420.0], TypeError)]
    + [(value, ValueError) for value in (float("nan"), float("inf"), -1.0)],
)
def test_a_width_that_is_not_one_is_refused_at_the_call(width: Any, error: type) -> None:
    """
    A host's mistake is raised where it was made, before anything is asked of
    the library. (The check is the first thing `headers` does, so a view that
    was never constructed -- there is no library here -- shows it; the window
    half asks a real view.)
    """
    view = object.__new__(module.TypesetDiffView)
    with pytest.raises(error, match=r"headers\(width_px=\.\.\.\)"):
        view.headers(width)


_HEADERS = r"""
import json, sys
from pathlib import Path

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.diff import Diff
from imscribe.theme import Theme
from imscribe.ui.typeset_diff_view import DiffLayout, DiffRows, TypesetDiffView
from imscribe.ui.typeset_hosts import HostedDiff

LONG, VERDICT = sys.argv[1], sys.argv[2]
POS = (10.0, 10.0)
report = {"load": ["%.2f" % x for x in __import__("os").getloadavg()]}
calls = []
state = {"n": 0, "scene": None, "last": None, "done": False, "final": None}

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

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    report["load_fonts"] = typesetter.load_fonts()

def dump(headers):
    return [{"file": h.file, "row": h.row, "text": h.text, "warning": h.warning, "line": h.line,
             "width_px": h.width_px, "text_width_px": h.text_width_px,
             "available_px": h.available_px, "fits": h.fits, "text_fits": h.text_fits}
            for h in headers]

def asked(call):
    calls.clear()
    got = call()
    return got, list(calls)

def padded(length, **kwargs):
    # A diff of sixty lines whose header LINE is `length` characters.
    body = "".join(f"line {n}\n" for n in range(60))
    label = "p.py"
    for _ in range(3):
        diff = Diff.from_texts(body, body.replace("line 9\n", "LINE\n"), label, **kwargs)
        line = DiffRows(diff).headers()[0].line
        label = "p" * (len(label) - 3 + length - len(line)) + ".py"
    assert len(line) == length, (len(line), length)
    return diff

def script():
    ts = typesetter.module()
    report["module"] = ts is not None
    report["ready"] = typesetter.ready()
    report["reason"] = typesetter.reason()
    if ts is None or not typesetter.ready():
        return
    ts._lib = Counting(ts._lib, calls)
    theme = Theme.build()
    cases = {
        "short": Diff.from_texts("a\n", "b\n", "src/short.py", will_not_apply=VERDICT),
        "long": Diff.from_texts("a\n", "b\n", LONG, will_not_apply=VERDICT),
        "small": Diff.from_texts("a\n", "b\n", "x.py", will_not_apply="no"),
    }
    out = report["cases"] = {}
    for name, diff in cases.items():
        for layout in (DiffLayout.UNIFIED, DiffLayout.SIDE_BY_SIDE):
            view = TypesetDiffView(diff, theme, layout=layout)
            entry = out[f"{name} {layout.value}"] = {"cell": view.grid.cell}
            got, made = asked(lambda: view.headers())
            entry["before"], entry["before_calls"] = dump(got), made
            got, made = asked(lambda: view.headers(420.0))
            entry["asked"], entry["asked_calls"] = dump(got), made
            for width in (420.0, 1400.0):
                state["scene"] = {"view": view, "width": width}
                yield
                yield
                yield
                entry[str(int(width))] = state["last"]
            entry["measured"] = view.headers_measured

    # ---- height_cap: the line is cut at the width INSIDE the child ---------------------
    # 52 cells: inside 420 px, and not inside 420 less a vertical scrollbar.
    view = TypesetDiffView(padded(51), theme, height_cap=100.0)
    state["scene"] = {"view": view, "width": 420.0}
    yield
    yield
    yield
    report["cap"] = {"drawn": state["last"], "asked": dump(view.headers(420.0)),
                     "inner": view._width, "rows": view.row_count}

    # ---- a header that changes is measured once more; one that does not, never ----------
    view = TypesetDiffView(cases["short"], theme)
    state["scene"] = {"view": view, "width": 420.0}
    yield
    yield
    first = view.headers_measured
    grown = Diff.from_texts("a\n", "b\nc\n", "src/short.py", will_not_apply=VERDICT)
    view.set_diff(grown)
    got, made = asked(lambda: view.headers())
    again, made_again = asked(lambda: view.headers())
    view.set_layout(DiffLayout.SIDE_BY_SIDE)
    switched, made_switched = asked(lambda: view.headers())
    report["changed"] = {"measured": [first, view.headers_measured], "calls": made,
                         "again_calls": made_again, "text": got[0].text,
                         "same": dump(again) == dump(got),
                         "switch_calls": made_switched, "switched": dump(switched) == dump(got)}

    # ---- a host's mistake is the host's: raised at the call, nothing switched off -------
    refused = {}
    for name, value in (("str", "420"), ("bool", True), ("nan", float("nan")), ("negative", -1.0)):
        try:
            view.headers(value)
            refused[name] = "answered"
        except (TypeError, ValueError) as exc:
            refused[name] = [type(exc).__name__, str(exc)]
    report["refused"] = refused
    report["hosted"] = dump(HostedDiff(view).headers(300.0)) == dump(view.headers(300.0))
    report["module_at_end"] = typesetter.module() is not None
    report["ready_at_end"] = typesetter.ready()
    report["trouble"] = typesetter.trouble()
    state["final"] = view

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
    scene = state["scene"]
    if scene is None:
        return
    view, width = scene["view"], scene["width"]
    pad = imgui.get_style().window_padding.x
    flags = (imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value
             | imgui.WindowFlags_.no_saved_settings.value | imgui.WindowFlags_.no_scrollbar.value)
    imgui.set_next_window_pos(imgui.ImVec2(*POS))
    imgui.set_next_window_size(imgui.ImVec2(width + 2 * pad, 600.0))
    imgui.begin("headers", None, flags)
    try:
        avail = imgui.get_content_region_avail().x
        draw_list = imgui.get_window_draw_list()
        before = draw_list.vtx_buffer.size()
        calls.clear()
        answered = view.draw()
        headers = view.headers()
        frame = list(calls)
        after = draw_list.vtx_buffer.size()
        ox, oy = view.origin
        sheet = view._described()
        document = view.native_documents[0]
        ink, ends = [], []
        for h in headers:
            top = oy + h.row * view.row_px
            xs = [draw_list.vtx_buffer[i].pos.x - ox for i in range(before, after)
                  if top - 3 <= draw_list.vtx_buffer[i].pos.y < top + view.row_px + 2]
            ink.append(max(xs) if xs else None)
            # The row's own line in the view's own document: where the library ends it.
            ends.append(document.caret_rect((sheet.row_block[h.row], 1 + len(h.line)))[0])
        state["last"] = {"avail": avail, "answered": answered, "calls": frame,
                         "headers": dump(headers), "rightmost_vertex": ink, "line_ends": ends,
                         "visible": [view.visible_rows.start, view.visible_rows.stop]}
    finally:
        imgui.end()

def before_exit():
    view = state["final"]
    if view is not None:
        typesetter.unload()
        try:
            report["after_unload"] = dump(view.headers(420.0))
        except Exception as exc:
            report["after_unload"] = [type(exc).__name__, str(exc)]

state["script"] = script()
runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "TypesetDiffView headers under test"
runner.app_window_params.window_geometry.size = (1500, 700)
runner.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
runner.ini_disable = True
runner.fps_idling.enable_idling = False
runner.callbacks.load_additional_fonts = load_fonts
runner.callbacks.show_gui = gui
runner.callbacks.before_exit = before_exit
immapp.run(runner)
report["frame_count"] = state["n"]
report["finished"] = state["done"]
print("REPORT " + json.dumps(report))
"""

# What measuring a set of header lines costs, counted at the ctypes library: a
# document made, its options, its blocks, one layout, two carets a file, closed.
_MEASURE = ["CreateDocument", "SetDocumentOptions", "SetDocumentBlocks", _L]
_CARET = "GetDocumentCaretRect"


@pytest.fixture(scope="module")
def header_report(window: Any) -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    script = window.out / "typeset_diff_view_headers_driver.py"
    script.write_text(_HEADERS, encoding="utf-8")
    done = window.run([str(script), _LONG_LABEL, _VERDICT], timeout=180.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-6000:]
    got = _report_of(done.stdout)
    # In the child, not here: `window.run` gives it a PYTHONPATH of its own.
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert got["finished"] is True and "refused" in got, "the driver did not reach its end"
    # And after: nothing here switched the library off.
    assert got["module_at_end"] is True and got["ready_at_end"] is True
    assert got["trouble"] == ""
    return got


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_in_a_window_a_header_longer_than_a_narrow_view_did_not_fit_and_fits_a_wide_one(
    header_report: dict[str, Any], layout: str
) -> None:
    """
    pptmstr's P16, on the behaviour of its
    `test_a_diff_header_too_long_for_its_view_is_said_above_it_warning_first`:
    at 420 px a short path with a verdict has only the verdict cut, a long one
    has the path cut too, and a view wide enough has nothing cut. Before a
    first draw nothing is said about fitting; asked about a width, the answer
    is the one the draw at that width then gives.

    Held to two things that are not `headers`' own arithmetic: the end of the
    row's line in the view's own gutter document, and the quads the frame put
    on the draw list (the library emits none wholly right of the clip, so ink
    past the edge shows as a quad that straddles it, and ink inside as none).
    """
    expected = {  # (fits, text_fits) at 420 and at 1400
        "short": ((False, True), (True, True)),
        "long": ((False, False), (True, True)),
        "small": ((True, True), (True, True)),
    }
    labels = {"short": "src/short.py", "long": _LONG_LABEL, "small": "x.py"}
    for name, (narrow, wide) in expected.items():
        entry = header_report["cases"][f"{name} {layout}"]
        (before,) = entry["before"]
        assert before["text"] == f"{labels[name]}  +1 -1", name
        assert before["warning"] == ("! no" if name == "small" else f"! {_VERDICT}"), name
        assert before["available_px"] is None, name
        assert before["fits"] is None and before["text_fits"] is None, name
        cell = entry["cell"]
        assert before["width_px"] == pytest.approx((1 + len(before["line"])) * cell, abs=0.01)
        assert before["text_width_px"] == pytest.approx((1 + len(before["text"])) * cell, abs=0.01)

        (asked,) = entry["asked"]
        assert asked["available_px"] == 420.0, name
        assert (asked["fits"], asked["text_fits"]) == narrow, name
        for width, want in (("420", narrow), ("1400", wide)):
            drawn = entry[width]
            assert drawn["answered"] is True, name
            (header,) = drawn["headers"]
            assert header["available_px"] == drawn["avail"] == float(width), name
            assert (header["fits"], header["text_fits"]) == want, (name, width)
            assert header["width_px"] == drawn["line_ends"][0] == before["width_px"], name
            (rightmost,) = drawn["rightmost_vertex"]
            if header["fits"]:
                assert rightmost <= header["available_px"], (name, width)
            else:
                assert header["available_px"] < rightmost < header["available_px"] + 2 * cell
        assert entry["420"]["headers"] == [asked], name


def test_in_a_window_asking_about_the_headers_every_frame_adds_no_call_to_a_frame(
    header_report: dict[str, Any],
) -> None:
    """
    The budget stays exact: a frame that draws AND asks is `layout` and `draw`
    a document, as one that only draws. The widths are measured on the first
    asking -- a document, its options, its blocks, a layout, two carets a file
    -- and never again for the same lines at the same size: not for another
    width, not after a draw, not after a layout switch.
    """
    for name, entry in header_report["cases"].items():
        made = [call for call in entry["before_calls"] if call != "GetCurrentContext"]
        assert made == [*_MEASURE, _CARET, _CARET, "DestroyDocument"], name
        assert entry["asked_calls"] == [], name
        frame = _frame_of(name.split(" ", 1)[1])
        assert entry["420"]["calls"] == frame and entry["1400"]["calls"] == frame, name
        assert entry["measured"] == 1, name
    changed = header_report["changed"]
    # A header whose text changed (a line arrived: the counts are in it) is measured again.
    assert changed["text"] == "src/short.py  +2 -1"
    assert changed["measured"] == [1, 2]
    assert changed["calls"].count("CreateDocument") == 1 and changed["calls"].count(_CARET) == 2
    assert changed["again_calls"] == [] and changed["same"] is True
    assert changed["switch_calls"] == [] and changed["switched"] is True


def test_in_a_window_a_capped_view_s_header_is_cut_inside_the_child(
    header_report: dict[str, Any],
) -> None:
    """
    With `height_cap` the rows are in a child window, and a vertical scrollbar
    takes room from the line: `headers()` after a draw answers for the width
    inside the child, which `headers(width_px)` cannot know before one. A
    header of 52 cells is inside 420 px and is cut inside the child.
    """
    cap = header_report["cap"]
    (drawn,) = cap["drawn"]["headers"]
    (asked,) = cap["asked"]
    assert cap["rows"] * 20 > 100.0  # taller than its cap: the child scrolls
    assert drawn["available_px"] == float(int(cap["inner"])) < 420.0 == asked["available_px"]
    assert drawn["width_px"] == asked["width_px"] == pytest.approx(416.0, abs=0.01)
    assert asked["fits"] is True and drawn["fits"] is False
    assert cap["drawn"]["calls"] == _UNIFIED_FRAME


def test_in_a_window_a_host_s_mistake_is_raised_at_the_call_and_unloading_leaves_the_texts(
    header_report: dict[str, Any],
) -> None:
    refused = header_report["refused"]
    assert [refused[name][0] for name in ("str", "bool", "nan", "negative")] == [
        "TypeError",
        "TypeError",
        "ValueError",
        "ValueError",
    ]
    assert "not str" in refused["str"][1]
    # `HostedDiff.headers` is the view's.
    assert header_report["hosted"] is True
    # After `typesetter.unload()` the library cannot be asked: the texts are still answered,
    # no width is, and nothing is raised.
    (after,) = header_report["after_unload"]
    assert after["text"] == "src/short.py  +2 -1" and after["warning"] == f"! {_VERDICT}"
    assert after["width_px"] is None and after["available_px"] is None and after["fits"] is None

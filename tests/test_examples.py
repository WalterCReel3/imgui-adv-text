r"""
`examples/diff_minimal.py`: that it needs only the facade and the typeset layer, and draws.

Four fidelities, lowest first, and each test says which it is: reading the
file (its imports are parsed, not trusted); a fresh interpreter; the two
ways in to a diff, with no ImGui; and real ImGui frames and a real window
through imtypeset (skipped without the library).

Until tranche 5 this file began with seven tests of `examples/minimal.py`,
the old core's five-step pipeline (parse, theme, compose, ship, draw through
`advtext.backends.imgui_draw`). That backend is deleted and the example with
it; `examples/typeset_minimal.py` is the smallest example now and
`tests/test_typeset_view.py` runs it.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from advtext import typesetter

_ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path, name: str) -> ModuleType:
    """
    A file outside any package, imported under a name of this module's choosing.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        pytest.fail(f"{path} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------
# `examples/diff_minimal.py`: a diff from before and after text, the same four fidelities

_DIFF_EXAMPLE = _ROOT / "examples" / "diff_minimal.py"

_NO_LIBRARY = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)


@pytest.fixture(scope="module")
def diff_minimal() -> ModuleType:
    return _load(_DIFF_EXAMPLE, "advtext_example_diff_minimal")


def test_the_diff_example_imports_the_facade_and_the_typeset_layer_and_nothing_old() -> None:
    """
    Fidelity: the source text, every import in the file.

    Everything comes from the package root: `Diff`, a dark palette, a theme,
    and since T5-B2 the view (`TypesetDiffView`, `DiffLayout`,
    `TypesetUnavailable`), which are in `advtext.__all__` for as long as this
    passes; and the `typesetter` module, which is a submodule taken from the
    root. No submodule of advtext is imported by its own path (until T5-B2
    the view's two were: the typeset layer was beside the facade). Nothing of
    the old view or the old font loader is imported by any route.
    """
    typeset_layer: set[str] = set()
    tree = ast.parse(_DIFF_EXAMPLE.read_text(encoding="utf-8"))
    from_root: list[str] = []
    by_name: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("advtext"), f"import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("advtext."):
                by_name.add(module)
            if module == "advtext":
                from_root.extend(alias.name for alias in node.names)

    import advtext

    assert by_name == typeset_layer, sorted(by_name ^ typeset_layer)
    assert set(from_root) - {"typesetter"} <= set(advtext.__all__)
    assert {"Diff", "DARK_PALETTE", "Theme", "typesetter"} <= set(from_root)
    assert {"TypesetDiffView", "DiffLayout", "TypesetUnavailable"} <= set(from_root)
    old = {"DiffView", "DiffFences", "BareView", "load_faces", "fontlib_metrics", "char_measure"}
    assert not set(from_root) & old, sorted(set(from_root) & old)


def test_loading_the_diff_example_and_making_its_diffs_loads_no_imgui() -> None:
    """
    Fidelity: a fresh interpreter, by import graph.

    The model is pure, so a host can make a diff where it has no window: after
    loading the example and building both of its diffs, neither ImGui nor the
    demo application has been imported.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("dm", {str(_DIFF_EXAMPLE)!r})
                example = importlib.util.module_from_spec(spec)
                sys.modules["dm"] = example
                spec.loader.exec_module(example)
                one, several = example.text_diff(), example.edits_diff()
                print(len(one.files), len(several.files))
                print([n for n in sys.modules if n.split(".")[0] == "imgui_bundle"][:1])
                print("advtext.ui.app" in sys.modules)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["1 3", "[]", "False"]


def test_the_two_ways_in_give_the_diffs_the_example_says_they_do(
    diff_minimal: ModuleType,
) -> None:
    """
    Fidelity: the model alone. `from_texts` for a whole file, `from_edits` for several edits.

    The whole-file diff applies: its `after` is recovered from its `before`,
    so the rows are a description of the change and not merely plausible. The
    edits come out as a file each, labelled as given, +1 -1 each -- including
    the third, neither side of which ends in a newline, which is the case a
    host joining `difflib.unified_diff` output gets wrong (`Diff.from_unified`'s
    docstring) and the reason the example calls `from_edits`.

    A side that is `None` is a file that is not there, and the status says so.
    """
    from advtext import FileStatus, RowKind

    one = diff_minimal.text_diff()
    (file,) = one.files
    assert (file.label, one.added, one.removed) == (diff_minimal.LABEL, 4, 2)
    assert file.apply(diff_minimal.BEFORE) == diff_minimal.AFTER

    several = diff_minimal.edits_diff()
    assert [f.label for f in several.files] == ["edit 1", "edit 2", "edit 3"]
    assert [(f.added, f.removed) for f in several.files] == [(1, 1)] * 3
    last_rows = [(row.kind, row.text) for hunk in several.files[2].hunks for row in hunk.rows]
    assert [text for kind, text in last_rows if kind is not RowKind.META] == [
        "    return 0",
        "    return 0  # always",
    ]
    assert sum(kind is RowKind.META for kind, _text in last_rows) == 2, "one note per side"

    assert diff_minimal.text_diff(None, "new\n", "n.txt").files[0].status is FileStatus.NEW
    assert diff_minimal.text_diff("old\n", None, "o.txt").files[0].status is FileStatus.DELETED


_DIFF_HEADLESS = r"""
import importlib.util, json, sys
from imgui_bundle import imgui
from advtext import typesetter

spec = importlib.util.spec_from_file_location("dm", sys.argv[1])
example = importlib.util.module_from_spec(spec)
sys.modules["dm"] = example
spec.loader.exec_module(example)

ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1024.0, 768.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["old"] = sorted(
    n for n in sys.modules
    if n in ("advtext.ui.diff_view", "advtext.ui.bare_view", "advtext.backends.imgui_draw",
             "advtext.ui.fonts", "advtext.markdown", "advtext.style")
)

for name, side_by_side in (("unified", False), ("side-by-side", True)):
    view = example.make_view(example.text_diff(), side_by_side=side_by_side)
    for _frame in range(2):
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(10.0, 10.0))
            imgui.set_next_window_size(imgui.ImVec2(900.0, 700.0))
            imgui.begin("advtext diff example under test")
            try:
                before = imgui.get_window_draw_list().vtx_buffer.size()
                top = imgui.get_cursor_screen_pos().y
                width = imgui.get_content_region_avail().x
                answered = example.show(view)
                after = imgui.get_window_draw_list().vtx_buffer.size()
                moved = imgui.get_cursor_screen_pos().y - top
            finally:
                imgui.end()
        finally:
            imgui.render()
    view.select_all(side=1 if side_by_side else None)
    report[name] = {
        "view": type(view).__name__, "layout": view.layout.name, "answered": answered,
        "vertices": after - before, "moved": moved, "height": view.height_for(width),
        "rows": view.row_count, "copied": view.selected_text().splitlines(),
    }
    view.close()
report["after"] = {"module": typesetter.module() is not None, "ready": typesetter.ready()}
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def diff_drawn() -> dict[str, Any]:
    """
    `_DIFF_HEADLESS` run once in a child that has the library; skipped without the variable.

    The child says whether the library was in use and ready before it drew
    and again after: the pytest process never has it ready.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_NO_LIBRARY)
    done = subprocess.run(
        [sys.executable, "-B", "-c", _DIFF_HEADLESS, str(_DIFF_EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=300,
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
    assert report["after"] == {"module": True, "ready": True}, report["after"]
    return report


@pytest.mark.parametrize("layout", ["unified", "side-by-side"])
def test_the_diff_example_draws_in_a_real_imgui_window_through_imtypeset(
    diff_drawn: dict[str, Any], layout: str
) -> None:
    """
    Fidelity: a real frame and a real `imgui.begin` window, the library loaded;
    no backend, no display.

    `show` is the example's whole per-frame code. Rows reach the window's draw
    list with everything set as asked, the view claims height (the cursor
    moves down by at least what `height_for` says), and what the view then
    copies for "everything" has the changed line in it and no gutter marker in
    front of it. Nothing of the old diff view, its backend or its fonts was
    loaded to do it.
    """
    told = diff_drawn[layout]
    assert told["view"] == "TypesetDiffView" and told["answered"] is True
    assert told["layout"] == ("SIDE_BY_SIDE" if layout == "side-by-side" else "UNIFIED")
    assert told["vertices"] > 800, "next to nothing reached the window's draw list"
    assert told["moved"] >= told["height"] > 0.0
    assert told["rows"] > 10
    copied = told["copied"]
    assert '    print(f"{greeting}, {name}!")' in copied
    assert not any(line.startswith(("+ ", "- ", "+\t", "-\t")) for line in copied)
    assert diff_drawn["old"] == []


_DIFF_FLAGS = {
    (): ("UNIFIED", "1", "4", "2"),
    ("--side-by-side",): ("SIDE_BY_SIDE", "1", "4", "2"),
    ("--edits",): ("UNIFIED", "3", "3", "3"),
}


@pytest.mark.parametrize("flags", list(_DIFF_FLAGS), ids=["unified", "side-by-side", "edits"])
def test_without_the_library_the_diff_example_says_why_and_opens_no_window(
    flags: tuple[str, ...],
) -> None:
    """
    Fidelity: `main()` itself in a fresh interpreter, with the library's
    variables and every display removed. It returns 1, prints nothing on
    standard output, says why on standard error, and never imports a window
    runner: there was no window to fail to open.
    """
    variables = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in (*variables, "DISPLAY", "WAYLAND_DISPLAY")
    }
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("dm", {str(_DIFF_EXAMPLE)!r})
                example = importlib.util.module_from_spec(spec)
                sys.modules["dm"] = example
                spec.loader.exec_module(example)
                code = example.main(["--frames", "5", *{list(flags)!r}])
                runners = [n for n in ("imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                           if n in sys.modules]
                print("code=%d runners=%r" % (code, runners), file=sys.stderr)
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
    assert result.stdout == "" and "Traceback" not in result.stderr
    said, told = result.stderr.strip().splitlines()[-2:]
    assert said == f"imtypeset is not drawing: {typesetter.LIBRARY_VARIABLE} is not set"
    assert told == "code=1 runners=[]"


def test_with_the_library_the_diff_example_s_main_runs_in_a_real_window(window: Any) -> None:
    """
    Fidelity: `main()` itself with the imtypeset library, in a GLFW window with
    an OpenGL context. Skipped, with the reason, when `IMTYPESET_LIBRARY` is
    not set.

    Three runs through the `window` fixture (this machine's display, or an
    Xvfb in a user namespace; it skips with the reason where neither can be
    had): the whole-file diff unified and side by side, and the edits. Each
    closes itself after five frames and prints what the last one drew. The
    counts are the model's, seen from inside the window; the example's own
    report names `TypesetDiffView` and says the library set everything as
    asked, and nothing is said on standard error.

    Software rendering and no window manager under Xvfb: a real window, not a
    desktop. Nobody looked at it.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_NO_LIBRARY)
    for flags, (layout, files, added, removed) in _DIFF_FLAGS.items():
        done = window.run([str(_DIFF_EXAMPLE), "--frames", "5", *flags])
        assert done.returncode == 0, done.stdout + done.stderr
        report = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
        assert len(report) == 1, done.stdout + done.stderr
        fields = dict(part.split("=") for part in report[0].split())
        assert fields["frames"] == "5" and fields["layout"] == layout
        assert (fields["files"], fields["added"], fields["removed"]) == (files, added, removed)
        assert int(fields["rows"]) > 10
        # The library counts no glyphs; `answered` is its "all set as asked".
        assert fields["renderer"] == "TypesetDiffView" and fields["answered"] == "1"
        assert "glyphs" not in fields and "not drawing" not in done.stderr

r"""
`examples/minimal.py`: that it needs only the facade, and that it draws.

Four fidelities, lowest first, and each test says which it is.

1. **Reading the file.** Its imports are parsed, not trusted: every `advtext`
   import is from the package root.
2. **A fresh interpreter.** Loading the example pulls in neither the demo
   application nor a window runner.
3. **Fakes.** `MarkdownPane` and `show` with a recording ImGui, for the
   bookkeeping a real frame cannot be asked about -- how often a layout was
   composed, what size was claimed, which ink was used.
4. **Real ImGui.** `show` inside a real frame with the real fonts, asserting on
   the vertex buffer; and `main()` in a real window on an Xvfb started in a user
   namespace, asserting on what the example reports. The last skips only where
   that cannot be set up, by the same capability probe `tests/test_mouse_probe.py`
   uses. Xvfb with a software rasteriser and no window manager is a real window
   and a real GL context and is not a desktop: nothing here says how it looks.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from advtext import DEFAULT_PALETTE, Face, Theme, load_faces, text_block
from advtext.shipout import Glyph, RuleRect

_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE = _ROOT / "examples" / "minimal.py"
_PROBE = _ROOT / "scripts" / "mouse_probe.py"

XVFB_DISPLAY = 97
"""
Not 99, which `scripts/mouse_probe.py` uses. The server is in its own mount and
user namespace but shares the network one, so two test files starting an Xvfb on
the same TCP port at the same time would collide.
"""


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


@pytest.fixture(scope="module")
def minimal() -> ModuleType:
    return _load(_EXAMPLE, "advtext_example_minimal")


# ----------------------------------------------------------------------
# 1 and 2: what the example imports


def test_the_example_imports_advtext_only_from_the_package_root() -> None:
    """
    Fidelity: the source text. Every import in the file, wherever it sits.

    `from advtext import ...` is allowed; `import advtext.x` and
    `from advtext.x import ...` are not, at module level or inside a function.
    This is the test that makes "the facade is enough to embed" a checked
    statement: the moment the example needs a name the facade lacks, it fails
    here and the choice is to add the name or admit the gap.
    """
    tree = ast.parse(_EXAMPLE.read_text(encoding="utf-8"))
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

    import advtext

    assert len(from_root) > 10, "the example imports almost nothing from advtext"
    assert set(from_root) <= set(advtext.__all__)


def test_loading_the_example_loads_neither_the_demo_app_nor_a_window_runner() -> None:
    """
    Fidelity: a fresh interpreter, by import graph.

    `advtext.ui.app` is the demo; the plan's "done when" for this phase is that
    the example renders without it. ImGui itself is also absent until `main`
    runs, so the example's pane can be built and laid out by a program that
    never opens a window -- the second line is that, done.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("minimal", {str(_EXAMPLE)!r})
                minimal = importlib.util.module_from_spec(spec)
                sys.modules["minimal"] = minimal
                spec.loader.exec_module(minimal)
                names = ("advtext.ui.app", "imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                print([name for name in names if name in sys.modules])
                layout = minimal.MarkdownPane(minimal.MARKDOWN).layout(480.0)
                print(len(layout.commands) > 500, "advtext.ui.app" in sys.modules)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["[]", "True False"]


# ----------------------------------------------------------------------
# 3: the pane and `show`, with a recording ImGui


def _text(commands: Any) -> str:
    return "".join(chr(cmd.codepoint) for cmd in commands if isinstance(cmd, Glyph))


def test_the_pane_lays_the_document_out_and_only_again_when_the_width_changes(
    minimal: ModuleType,
) -> None:
    """
    Fidelity: real fonts, real composition, no ImGui.

    One compose per distinct whole-pixel width, however many frames ask. The
    narrower layout is the taller one, and both set every character of the
    source that is not markup or space -- so the second layout is a re-break of
    the same text and not a different document.
    """
    pane = minimal.MarkdownPane("# Title\n\n" + "Some words to break. " * 12 + "\n\n---\n")

    wide = pane.layout(480.0)
    assert pane.layouts == 1
    assert pane.layout(480.0) is wide and pane.layout(480.4) is wide
    assert pane.layouts == 1, "a frame at an unchanged width composed again"

    narrow = pane.layout(240.0)
    assert pane.layouts == 2
    assert narrow.height_px > wide.height_px > 0.0
    assert (wide.width_px, narrow.width_px) == (480.0, 240.0)
    assert _text(wide.commands) == _text(narrow.commands) == "Title" + "Somewordstobreak." * 12
    assert sum(isinstance(cmd, RuleRect) for cmd in wide.commands) == 1


class _Vec:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _RecordingDrawList:
    """
    A draw list that keeps what it was asked to draw. `flags` is what `draw` borrows.
    """

    def __init__(self) -> None:
        self.flags = 0
        self.texts: list[tuple[float, float, int, str]] = []
        self.rects: list[int] = []

    def add_text(self, _font: Any, _size: float, position: Any, colour: int, text: str) -> None:
        self.texts.append((position.x, position.y, colour, text))

    def add_rect_filled(self, _near: Any, _far: Any, colour: int) -> None:
        self.rects.append(colour)


class _FakeImGui:
    """
    The six things `show` asks of ImGui, answered from fields and recorded.

    `ImVec2` and the flag enum are the real ones -- `draw` constructs positions
    and reads `ImDrawListFlags_` itself, from `imgui_bundle`, and neither needs
    a context -- so this stands in only for the *window*: its width, its cursor,
    its draw list, its text colour and the dummy that claims space.
    """

    HOST_TEXT = 0xFF_AB_CD_EF

    class Col_:  # noqa: N801 - mirrors `imgui.Col_`
        text = "text"

    def __init__(self, width: float, cursor: tuple[float, float]) -> None:
        from imgui_bundle import imgui

        self.ImVec2 = imgui.ImVec2
        self._width = width
        self._cursor = cursor
        self.draw_list = _RecordingDrawList()
        self.dummies: list[tuple[float, float]] = []
        self.colours_asked: list[Any] = []

    def get_content_region_avail(self) -> _Vec:
        return _Vec(self._width, 0.0)

    def get_cursor_screen_pos(self) -> Any:
        return self.ImVec2(*self._cursor)

    def get_window_draw_list(self) -> _RecordingDrawList:
        return self.draw_list

    def get_color_u32(self, which: Any) -> int:
        self.colours_asked.append(which)
        return self.HOST_TEXT

    def dummy(self, size: Any) -> None:
        self.dummies.append((size.x, size.y))


class _FakeFont:
    """
    An `ImFont` stand-in with every glyph, baking at the size asked for.
    """

    class _Baked:
        def __init__(self, size: float) -> None:
            self.size = float(int(size + 0.5))
            self.ascent = self.size * 0.75

    def is_glyph_in_font(self, _codepoint: int) -> bool:
        return True

    def get_font_baked(self, size: float) -> Any:
        return self._Baked(size)


def test_show_draws_at_the_cursor_in_the_host_s_ink_and_claims_the_space(
    minimal: ModuleType,
) -> None:
    """
    Fidelity: a recording ImGui, for the three things `show` owes its window.

    - It lays out to the window's content width.
    - It draws at the cursor, in the host's text colour and not the default
      palette's -- which is dark ink for a light page and would be invisible in
      a dark window. Every glyph and every rule carries the host's colour.
    - It submits one dummy the size of the layout, which is what gives the
      window a content height to scroll.
    """
    pane = minimal.MarkdownPane("Two words.\n\n---\n\nMore.\n")
    imgui = _FakeImGui(width=300.0, cursor=(50.0, 70.0))
    font = _FakeFont()

    stats = minimal.show(pane, lambda _face: font, imgui)

    layout = pane.layout(300.0)
    assert pane.layouts == 1, "show laid out at some width other than the content region's"
    # `ImVec2` holds single-precision floats, so the height comes back rounded.
    assert imgui.dummies == [pytest.approx((layout.width_px, layout.height_px), rel=1e-6)]
    assert imgui.colours_asked == ["text"]

    drawn = imgui.draw_list
    assert (stats.glyphs, stats.missing, stats.rules) == (len(drawn.texts), 0, 1)
    assert "".join(text for *_rest, text in drawn.texts) == "Twowords.More."
    assert {colour for _x, _y, colour, _text in drawn.texts} == {_FakeImGui.HOST_TEXT}
    assert drawn.rects == [_FakeImGui.HOST_TEXT]
    assert _FakeImGui.HOST_TEXT not in (DEFAULT_PALETTE.ink, DEFAULT_PALETTE.rule)
    assert min(x for x, *_rest in drawn.texts) >= 50.0
    assert min(y for _x, y, *_rest in drawn.texts) >= 70.0


def test_the_pane_takes_a_theme_and_blocks_that_were_never_markdown(minimal: ModuleType) -> None:
    """
    Fidelity: real fonts, no ImGui. The pane is not tied to its sample or its theme.

    A host swaps the theme through the constructor and may replace the document
    with blocks it built itself; the layout follows both.
    """
    pane = minimal.MarkdownPane("ignored", theme=Theme.build(20.0))
    assert (
        pane.theme.style(pane.document.blocks[0].kind).font.size
        == pane.theme.blocks[pane.document.blocks[0].kind].font.size
    )

    block = text_block("**not** markdown", pane.theme, pane.metrics)
    pane.document = type(pane.document)(blocks=(block,))
    assert _text(pane.layout(400.0).commands) == "**not**markdown"


# ----------------------------------------------------------------------
# 4: real ImGui


@pytest.fixture(scope="module")
def imgui_context() -> Any:
    """
    The process's ImGui context, made if no other test module has made one.

    The recipe `tests/test_imgui_draw.py` gives, for its reasons: no backend, no
    window, textures declared backend-managed so a frame can run.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1024.0, 768.0)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    return imgui


def test_show_runs_inside_a_real_imgui_window_with_the_real_fonts(
    minimal: ModuleType, imgui_context: Any
) -> None:
    """
    Fidelity: a real frame and a real `imgui.begin` window; no backend, no display.

    The fonts come from `load_faces()` on the real atlas and `show` is handed the
    real `imgui` module, so this is the example's own code path with nothing
    faked except that the frame is never composited. Every glyph the layout
    names is drawn and none is missing; the window's draw list gains vertices;
    and the window's cursor has moved down by the height the dummy claimed.
    """
    imgui = imgui_context
    fonts = load_faces()
    assert fonts(Face.PROSE) is not None
    pane = minimal.MarkdownPane(minimal.MARKDOWN)

    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(10.0, 10.0))
        imgui.set_next_window_size(imgui.ImVec2(560.0, 620.0))
        imgui.begin("advtext example under test")
        before = imgui.get_window_draw_list().vtx_buffer.size()
        top = imgui.get_cursor_screen_pos().y
        width = imgui.get_content_region_avail().x
        stats = minimal.show(pane, fonts, imgui)
        after = imgui.get_window_draw_list().vtx_buffer.size()
        moved = imgui.get_cursor_screen_pos().y - top
        imgui.end()
    finally:
        imgui.render()

    assert 400.0 < width < 560.0, "the window's content region is not the size it was given"
    layout = pane.layout(width)
    assert pane.layouts == 1, "show laid out at some width other than the content region's"
    glyphs = sum(isinstance(cmd, Glyph) for cmd in layout.commands)
    assert glyphs > 500
    assert (stats.glyphs, stats.missing) == (glyphs, 0)
    assert stats.rules == sum(isinstance(cmd, RuleRect) for cmd in layout.commands) > 0
    assert after > before, "nothing reached the window's draw list"
    assert moved >= layout.height_px


def _can_make_a_namespace() -> bool:
    """
    Whether `unshare -rm` works here, which the Xvfb recipe needs.
    """
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-rm", "true"], capture_output=True, check=False)
    return done.returncode == 0


def test_main_opens_a_real_window_and_draws_the_document_in_it() -> None:
    """
    Fidelity: `main()` itself, in a GLFW window with an OpenGL context, on Xvfb.

    A subprocess, because a process gets one GLFW lifetime and the server lives
    in a namespace this one is not in. `--frames 5` makes the example close
    itself and print what its last frame drew; the assertion is on that line.
    One layout for five frames is the caching claim holding in a live loop, and
    `missing=0` is the faces having loaded through the runner's font callback.

    Skips only where the window cannot be set up at all -- no Xvfb, or no user
    namespaces -- and says which.
    """
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which the Xvfb recipe needs")

    probe = _load(_PROBE, "advtext_mouse_probe_for_examples")
    # The server is started in the background a moment before the inner command,
    # so the inner command waits for it to accept a connection before it runs
    # the example. Without the wait this passed here every time and would not
    # under load: the example would reach GLFW before the display existed.
    inner = textwrap.dedent(f"""
        import os, runpy, sys
        sys.path.insert(0, {str(_PROBE.parent)!r})
        from mouse_probe import wait_for_tcp_display
        if not wait_for_tcp_display(os.environ["DISPLAY"], timeout=30.0):
            raise SystemExit("the Xvfb never accepted a connection")
        sys.argv = [{str(_EXAMPLE)!r}, "--frames", "5"]
        runpy.run_path({str(_EXAMPLE)!r}, run_name="__main__")
        """)
    command = probe.xvfb_command([sys.executable, "-c", inner], display=XVFB_DISPLAY)
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False, cwd=_ROOT
    )
    assert done.returncode == 0, done.stdout + done.stderr
    report = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
    assert len(report) == 1, done.stdout + done.stderr
    fields = dict(part.split("=") for part in report[0].split())
    assert fields["frames"] == "5" and fields["layouts"] == "1"
    assert int(fields["glyphs"]) > 500 and fields["missing"] == "0"
    assert int(fields["rules"]) >= 1


# ----------------------------------------------------------------------
# `examples/diff_minimal.py`: a diff from before and after text, the same four fidelities

_DIFF_EXAMPLE = _ROOT / "examples" / "diff_minimal.py"


@pytest.fixture(scope="module")
def diff_minimal() -> ModuleType:
    return _load(_DIFF_EXAMPLE, "advtext_example_diff_minimal")


def test_the_diff_example_imports_advtext_only_from_the_package_root() -> None:
    """
    Fidelity: the source text. The facade is enough to show a diff.

    The same reading as for `minimal.py`, and with the same purpose: the names
    a host needs for a diff view are in `advtext.__all__` for as long as this
    passes, and `DiffView`, `Diff` and a dark palette are among the ones used.
    """
    tree = ast.parse(_DIFF_EXAMPLE.read_text(encoding="utf-8"))
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

    import advtext

    assert set(from_root) <= set(advtext.__all__)
    assert {"Diff", "DiffView", "DiffLayout", "DARK_PALETTE", "load_faces"} <= set(from_root)


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


@pytest.mark.parametrize("side_by_side", [False, True], ids=["unified", "side-by-side"])
def test_the_diff_example_draws_in_a_real_imgui_window_with_the_real_fonts(
    diff_minimal: ModuleType, imgui_context: Any, side_by_side: bool
) -> None:
    """
    Fidelity: a real frame and a real `imgui.begin` window; no backend, no display.

    `show` is the example's whole per-frame code. Rows reach the window's draw
    list with no glyph missing from the loaded code face, the view claims
    height (the cursor moves down by at least what `height_for` says), and
    what the view then copies for "everything" has the changed line in it and
    no gutter marker in front of it.
    """
    imgui = imgui_context
    fonts = load_faces()
    view = diff_minimal.make_view(diff_minimal.text_diff(), side_by_side=side_by_side)

    stats = None
    for _frame in range(2):
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(10.0, 10.0))
            imgui.set_next_window_size(imgui.ImVec2(900.0, 700.0))
            imgui.begin("advtext diff example under test")
            before = imgui.get_window_draw_list().vtx_buffer.size()
            top = imgui.get_cursor_screen_pos().y
            width = imgui.get_content_region_avail().x
            stats = diff_minimal.show(view, fonts)
            after = imgui.get_window_draw_list().vtx_buffer.size()
            moved = imgui.get_cursor_screen_pos().y - top
            imgui.end()
        finally:
            imgui.render()

    assert stats is not None and stats.glyphs > 200 and stats.missing == 0
    assert after > before, "nothing reached the window's draw list"
    assert moved >= view.height_for(width) > 0.0
    assert view.row_count > 10

    view.select_all(side=1 if side_by_side else None)
    copied = view.selected_text().splitlines()
    assert '    print(f"{greeting}, {name}!")' in copied
    assert not any(line.startswith(("+ ", "- ", "+\t", "-\t")) for line in copied)


def test_the_diff_example_s_main_runs_in_a_real_window(window: Any) -> None:
    """
    Fidelity: `main()` itself, in a GLFW window with an OpenGL context.

    Three runs through the `window` fixture (this machine's display, or an
    Xvfb in a user namespace; it skips with the reason where neither can be
    had): the whole-file diff unified and side by side, and the edits. Each
    closes itself after five frames and prints what the last one drew. The
    counts are the model's, seen from inside the window; `missing=0` is the
    code face having loaded through the runner's font callback.

    Software rendering and no window manager under Xvfb: a real window, not a
    desktop. Nobody looked at it.
    """
    expected = {
        (): ("UNIFIED", "1", "4", "2"),
        ("--side-by-side",): ("SIDE_BY_SIDE", "1", "4", "2"),
        ("--edits",): ("UNIFIED", "3", "3", "3"),
    }
    for flags, (layout, files, added, removed) in expected.items():
        done = window.run([str(_DIFF_EXAMPLE), "--frames", "5", *flags])
        assert done.returncode == 0, done.stdout + done.stderr
        report = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
        assert len(report) == 1, done.stdout + done.stderr
        fields = dict(part.split("=") for part in report[0].split())
        assert fields["frames"] == "5" and fields["layout"] == layout
        assert (fields["files"], fields["added"], fields["removed"]) == (files, added, removed)
        assert int(fields["rows"]) > 10 and int(fields["glyphs"]) > 150
        assert fields["missing"] == "0"

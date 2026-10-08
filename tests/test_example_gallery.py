r"""
`examples/theme_gallery.py`: what its schemes are, and which colours reach which characters.

**Nothing here says how any scheme looks.** Every assertion is about change or
identity: this colour is among the vertices of that pane, these characters are
the ones a span covers, the ink is lighter than the ground or it is not. A
palette can pass every test in this file and be unreadable; that judgement is a
person's (`.concerns/lead--visual-standard.md`).

Fidelities, lowest first, as in `tests/test_examples.py`:

1. **Reading the file**: every `advtext` import is from the package root.
2. **A fresh interpreter**: loading it pulls in neither the demo application
   nor a window runner.
3. **Plain functions, real fonts, no ImGui**: the schemes, the documents built
   from them, the highlighter.
4. **Real ImGui frames, no backend**: `show` with the real module and the real
   fonts, colours read back from each pane's vertex buffer, and a link clicked
   with injected mouse events.
5. **A real window**: `main()` on an Xvfb in a user namespace, asserting on the
   counts it prints. Skips only where that cannot be set up.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import advtext
from advtext import DEFAULT_PALETTE, Align, BlockKind, CodeBlock, Face, TextBlock, load_faces
from advtext.nodes import CharNode
from advtext.spans import material_text
from advtext.style import parse_font_key
from advtext.units import px_from_sp

_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE = _ROOT / "examples" / "theme_gallery.py"
_PROBE = _ROOT / "scripts" / "mouse_probe.py"

XVFB_DISPLAY = 96
"""
Not 99 (`scripts/mouse_probe.py`) and not 97 (`tests/test_examples.py`): the
servers share a network namespace, so each test file that starts one needs its
own TCP port.
"""

DISPLAY = (1500.0, 1300.0)
"""
The headless frames' display. Tall enough that every pane shows its whole
document, so "this role's colour was drawn" is not at the mercy of culling.
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
def example() -> ModuleType:
    return _load(_EXAMPLE, "advtext_example_theme_gallery")


@pytest.fixture(scope="module")
def gallery(example: ModuleType) -> Any:
    """
    One gallery for the tests that only read it. Tests that click build their own.
    """
    return example.Gallery()


# ----------------------------------------------------------------------
# 1 and 2: what the example imports


def test_the_gallery_imports_advtext_only_from_the_package_root() -> None:
    """
    Fidelity: the source text. The task's "public facade only", held by reading the imports.

    `BareView`, the palettes, the colour-span helpers and the theme builder all
    have to be in `advtext.__all__` for this to pass, which is decision 14
    doing its job: the moment the gallery needs a name the facade lacks, this
    fails and the choice is to add the name or admit the gap.
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
    assert {"BareView", "Palette", "DARK_PALETTE", "ColourSpan", "Faces", "Theme"} <= set(from_root)
    assert set(from_root) <= set(advtext.__all__)


def test_loading_the_gallery_loads_neither_the_demo_app_nor_a_window_runner() -> None:
    """
    Fidelity: a fresh interpreter, by import graph.

    Building the gallery -- four themes, four documents, four views with their
    colour spans -- needs no window and none of the demo application.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("gallery", {str(_EXAMPLE)!r})
                gallery = importlib.util.module_from_spec(spec)
                sys.modules["gallery"] = gallery
                spec.loader.exec_module(gallery)
                names = ("advtext.ui.app", "imgui_bundle.hello_imgui", "imgui_bundle.immapp")
                print([name for name in names if name in sys.modules])
                made = gallery.Gallery()
                print(len(made.panes), "advtext.ui.app" in sys.modules)
                """),
        ],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["[]", "4 False"]


# ----------------------------------------------------------------------
# 3: the schemes, the documents, the highlighter


def _faces_set(document: Any) -> set[Face]:
    """
    Every face a document's text and code is set in, read from its nodes' font keys.
    """
    faces: set[Face] = set()
    for block in document.blocks:
        runs: list[Any] = []
        if isinstance(block, TextBlock):
            runs = [block.material, block.marker]
        elif isinstance(block, CodeBlock):
            runs = list(block.lines)
        elif hasattr(block, "rows"):
            runs = [cell.material for row in (block.header, *block.rows) for cell in row]
        for run in runs:
            faces.update(
                parse_font_key(node.font).face for node in run if isinstance(node, CharNode)
            )
    return faces


def test_there_are_several_palettes_light_and_dark_and_several_face_sets(gallery: Any) -> None:
    """
    The task's inventory, as facts about the data: what differs between the panes.

    "Dark" is the ink being lighter than the ground it is drawn on, by
    `luminance`; it is an ordering and not a claim of contrast.
    """
    schemes = [pane.scheme for pane in gallery.panes]
    assert [scheme.name for scheme in schemes] == ["page", "dark", "terminal", "notes"]
    assert [scheme.dark for scheme in schemes] == [False, True, True, False]
    assert len({scheme.palette for scheme in schemes}) == 4
    assert len({scheme.background for scheme in schemes}) == 4
    assert len({scheme.theme.faces for scheme in schemes}) == 3
    # Every palette says something about a role, which is what a gallery of
    # one-ink palettes would not show.
    assert all(scheme.palette.roles for scheme in schemes)
    # And a dark scheme's link and rule are not the light default's.
    for scheme in schemes:
        if scheme.dark:
            assert scheme.palette.link != DEFAULT_PALETTE.link
            assert scheme.palette.rule != DEFAULT_PALETTE.rule


def test_the_terminal_scheme_is_all_monospace_and_ragged(gallery: Any) -> None:
    """
    The pptmstr-like one: one face for everything, ragged right, on a pixel height.

    Checked on the document and not on the theme's table, because the table is
    an intention and the nodes are what is drawn: every character of every
    paragraph, heading, list marker, table cell and code line carries
    `Face.CODE`. The control is the page scheme, which uses five faces.

    `Faces.mono()` alone would not pass: with no bold monospace file
    registered, the bold role stands in the proportional bold, and the headings
    would be Roboto. The example passes `bold=Face.CODE` and says why.
    """
    terminal = gallery.pane("terminal")
    assert _faces_set(terminal.document) == {Face.CODE}
    assert len(_faces_set(gallery.pane("page").document)) >= 4

    theme = terminal.scheme.theme
    for kind in (BlockKind.PARAGRAPH, BlockKind.BULLET_ITEM, BlockKind.ORDERED_ITEM):
        assert theme.style(kind).align is Align.LEFT
    assert gallery.pane("page").scheme.theme.style(BlockKind.PARAGRAPH).align is Align.JUSTIFY


def _text(document: Any) -> list[str]:
    return [
        material_text(block).text
        for block in document.blocks
        if isinstance(block, (TextBlock, CodeBlock))
    ]


def test_every_pane_holds_the_same_text(gallery: Any) -> None:
    """
    "One document": the panes differ in theme and palette and in nothing a reader reads.
    """
    first = _text(gallery.panes[0].document)
    assert len(first) > 8 and any("same markdown" in text for text in first)
    for pane in gallery.panes[1:]:
        assert _text(pane.document) == first
        assert len(pane.document.blocks) == len(gallery.panes[0].document.blocks)
    # Not the same objects, though: a block bakes in its theme's fonts.
    assert gallery.panes[0].document != gallery.pane("terminal").document


def _code(document: Any) -> tuple[int, CodeBlock]:
    return next(
        (number, block)
        for number, block in enumerate(document.blocks)
        if isinstance(block, CodeBlock)
    )


def test_the_highlighter_colours_the_words_it_says_it_does(example: ModuleType) -> None:
    """
    Fidelity: the spans read back as text. Which characters get which ink.

    A span is a range of the block's characters; cut out of the block's text
    (newlines aside, which are not characters of the block) each must be
    exactly a token of its kind. The control is that `block`, `token` and
    `span` -- words, not keywords -- are in no span at all.
    """
    made = example.Gallery()
    pane = made.pane("terminal")
    _number, block = _code(pane.document)
    inks = pane.scheme.syntax
    flat = material_text(block).text.replace("\n", "")

    by_ink: dict[int, list[str]] = {}
    for span in example.highlight(block, inks):
        assert span.mark is None
        by_ink.setdefault(span.ink, []).append(flat[span.start : span.end])

    assert by_ink[inks.keyword] == ["def", "for", "in", "if", "yield", "return"]
    assert by_ink[inks.comment] == ["# ranges of characters, each with an ink"]
    assert by_ink[inks.string] == ['"keyword"', '"done"']
    assert by_ink[inks.number] == ["42"]
    assert set(by_ink) == {inks.keyword, inks.comment, inks.string, inks.number}
    coloured = " ".join(text for texts in by_ink.values() for text in texts)
    assert "block" not in coloured and "token" not in coloured and "span" not in coloured


def test_a_colour_packs_the_way_imgui_reads_it(example: ModuleType) -> None:
    """
    `rgb` against the library's own packed default, and against its inverse.
    """
    assert example.rgb(0x11, 0x11, 0x11) == DEFAULT_PALETTE.ink
    assert example.channels(example.rgb(1, 2, 3, 4)) == (1, 2, 3, 4)
    assert example.luminance(example.rgb(255, 255, 255)) == pytest.approx(1.0)
    assert example.luminance(example.rgb(0, 0, 0)) == 0.0


# ----------------------------------------------------------------------
# 4: real ImGui frames


class _Spy:
    """
    The real `imgui` module, except that each child's vertex colours are kept as it ends.

    `show` takes its ImGui as an argument, so the test can stand between the
    two without patching anything. A child's draw list is only reachable while
    the child is current, which is why this has to be done from inside.
    """

    def __init__(self, imgui: Any) -> None:
        self._imgui = imgui
        self.colours: list[set[int]] = []
        self.backgrounds: list[int] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._imgui, name)

    def end_child(self) -> None:
        buffer = self._imgui.get_window_draw_list().vtx_buffer
        self.colours.append({int(buffer[index].col) for index in range(buffer.size())})
        self.backgrounds.append(int(self._imgui.get_color_u32(self._imgui.Col_.child_bg)))
        self._imgui.end_child()


def _frame(
    example: ModuleType,
    made: Any,
    fonts: Any,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
) -> _Spy:
    """
    One real frame with the gallery in a window that fills the display.
    """
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*DISPLAY)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    spy = _Spy(imgui)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*DISPLAY))
        imgui.begin("##advtext-gallery-test", None, imgui.WindowFlags_.no_decoration.value)
        example.show(made, fonts, spy)
        imgui.end()
    finally:
        imgui.render()
    return spy


@pytest.fixture(scope="module")
def fonts(bundled_fonts: Path) -> Any:
    from imgui_bundle import imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    return load_faces()


@pytest.fixture
def drawn(example: ModuleType, fonts: Any) -> Iterator[tuple[Any, _Spy]]:
    """
    A fresh gallery after two settling frames, mouse parked off the panes and up.
    """
    made = example.Gallery()
    parked = (DISPLAY[0] - 2.0, 2.0)
    _frame(example, made, fonts, mouse=parked, left=False)
    spy = _frame(example, made, fonts, mouse=parked)
    yield made, spy
    _frame(example, made, fonts, mouse=parked, left=False)


def test_every_pane_draws_its_whole_document_with_nothing_missing(
    drawn: tuple[Any, _Spy],
) -> None:
    """
    Fidelity: real frames, real fonts, no backend. Counts from each view.

    Every pane draws glyphs and rules, the loaded faces raster all of them
    (including the monospace pane's, which asks for one face at a size nothing
    else uses), the three links are on screen in each, and no block failed to
    take its colour spans or its links.
    """
    made, _spy = drawn
    for pane in made.panes:
        assert pane.stats is not None, pane.scheme.name
        assert pane.stats.glyphs > 500 and pane.stats.missing == 0, pane.scheme.name
        assert pane.stats.rules >= 3, pane.scheme.name
        assert [link.target for link in pane.view.visible_links] == [
            "https://example.org/window",
            "https://example.org/links",
            "https://example.org/palette",
        ], pane.scheme.name
        assert pane.view.unmapped_blocks == 0
    # The panes share the window: four of them, each narrower than a third of it.
    widths = {round(px_from_sp(pane.view.layout.width)) for pane in made.panes}
    assert len(widths) == 1 and 200 < widths.pop() < DISPLAY[0] / 3


def test_each_pane_is_drawn_in_its_own_scheme_s_colours(drawn: tuple[Any, _Spy]) -> None:
    """
    Fidelity: the vertex buffer of each pane's child window, in a real frame.

    For every pane: its body ink, its rule colour, its link ink, each of its
    role inks and all four of its syntax inks are among the colours of the
    vertices drawn in it, and the background the child was given is the
    scheme's. That is "the palette reached the draw list", per pane.

    And nothing leaked between them, which is the control: the inks that are
    unique to one scheme appear in that pane only. In particular the default
    palette's dark ink -- the colour a draw path with a light page assumed
    somewhere would fall back to -- is in the page pane and in neither dark
    one.
    """
    made, spy = drawn
    assert len(spy.colours) == len(made.panes)
    own: list[set[int]] = []
    for pane, colours, background in zip(made.panes, spy.colours, spy.backgrounds, strict=True):
        scheme = pane.scheme
        palette, syntax = scheme.palette, scheme.syntax
        wanted = {palette.ink, palette.rule, palette.link}
        wanted |= {ink for _kind, ink in palette.roles}
        wanted |= {syntax.keyword, syntax.string, syntax.comment, syntax.number}
        assert wanted <= colours, f"{scheme.name}: {sorted(wanted - colours)} never drawn"
        assert background == scheme.background
        own.append(wanted)

    for index, pane in enumerate(made.panes):
        elsewhere = set().union(*(other for number, other in enumerate(own) if number != index))
        for number, colours in enumerate(spy.colours):
            if number != index:
                leaked = (own[index] - elsewhere) & colours
                assert not leaked, f"{pane.scheme.name}'s colours in pane {number}"

    by_name = {
        pane.scheme.name: colours for pane, colours in zip(made.panes, spy.colours, strict=True)
    }
    assert DEFAULT_PALETTE.ink in by_name["page"]
    assert DEFAULT_PALETTE.ink not in by_name["dark"]
    assert DEFAULT_PALETTE.ink not in by_name["terminal"]
    assert DEFAULT_PALETTE.link not in by_name["dark"] | by_name["terminal"] | by_name["notes"]


def _middle_of(view: Any, link: Any) -> tuple[float, float]:
    """
    The screen position of the middle of a link's first rectangle.
    """
    rect = link.rects[0]
    assert view.origin is not None
    return (
        view.origin[0] + px_from_sp(rect.x + rect.width // 2, view.px_per_inch),
        view.origin[1] + px_from_sp(rect.y + rect.height // 2, view.px_per_inch),
    )


def test_a_click_on_a_link_is_recorded_and_selects_nothing(
    example: ModuleType, fonts: Any, drawn: tuple[Any, _Spy]
) -> None:
    """
    Fidelity: real frames with injected mouse events. "Links clickable".

    Move onto the second link of the dark pane, press, release: the gallery
    has that link's target and nothing else, the status line says so, and no
    pane has a selection -- a press on a live link is the link's. Then the
    same in another pane for another link, so `followed` is an ordered record
    and not a last-value. The control is a press and release on plain text
    beside a link, which follows nothing and does select.
    """
    made, _spy = drawn
    assert made.followed == [] and "Click a link" in made.status()

    dark = made.pane("dark")
    target = _middle_of(dark.view, dark.view.visible_links[1])
    _frame(example, made, fonts, mouse=target)
    assert dark.view.hovered_link == "https://example.org/links"
    assert all(pane.view.hovered_link is None for pane in made.panes if pane is not dark)
    _frame(example, made, fonts, left=True)
    _frame(example, made, fonts, left=False)
    assert made.followed == ["https://example.org/links"]
    assert made.status() == "Link 1: https://example.org/links"
    assert all(pane.view.selection.is_empty for pane in made.panes)

    notes = made.pane("notes")
    _frame(example, made, fonts, mouse=_middle_of(notes.view, notes.view.visible_links[0]))
    _frame(example, made, fonts, left=True)
    _frame(example, made, fonts, left=False)
    assert made.followed == ["https://example.org/links", "https://example.org/window"]

    # The control: the first glyph of the terminal pane's heading is not a link.
    terminal = made.pane("terminal")
    assert terminal.view.origin is not None
    beside = (terminal.view.origin[0] + 3.0, terminal.view.origin[1] + 12.0)
    _frame(example, made, fonts, mouse=beside)
    assert terminal.view.hovered_link is None
    _frame(example, made, fonts, left=True)
    _frame(example, made, fonts, mouse=(beside[0] + 60.0, beside[1]))
    _frame(example, made, fonts, left=False)
    assert len(made.followed) == 2
    assert not terminal.view.selection.is_empty
    assert terminal.view.selected_text() and terminal.view.selected_text() in "One document, four"


def test_a_host_callback_is_called_as_well_as_the_record(example: ModuleType, fonts: Any) -> None:
    """
    `Gallery(on_link=...)` is how a host would open a browser; it gets the same target.
    """
    opened: list[str] = []
    made = example.Gallery(on_link=opened.append)
    parked = (DISPLAY[0] - 2.0, 2.0)
    _frame(example, made, fonts, mouse=parked, left=False)
    _frame(example, made, fonts, mouse=parked)
    page = made.pane("page")
    _frame(example, made, fonts, mouse=_middle_of(page.view, page.view.visible_links[2]))
    _frame(example, made, fonts, left=True)
    _frame(example, made, fonts, left=False)
    _frame(example, made, fonts, mouse=parked)
    assert opened == made.followed == ["https://example.org/palette"]


# ----------------------------------------------------------------------
# 5: a real window


def _can_make_a_namespace() -> bool:
    if shutil.which("unshare") is None:
        return False
    done = subprocess.run(["unshare", "-rm", "true"], capture_output=True, check=False)
    return done.returncode == 0


def test_main_opens_a_real_window_and_draws_every_pane_in_it() -> None:
    """
    Fidelity: `main()` itself, in a GLFW window with an OpenGL context, on Xvfb.

    `--frames 6` makes the example close itself and print one line per pane.
    The assertions are on those counts: four panes, glyphs in each, none
    missing -- the faces loaded through the runner's font callback, at the two
    extra sizes the terminal and notes themes ask for -- and no block unmapped.

    A software rasteriser with no window manager is a real window and not a
    desktop. Nobody looked at it and nothing here says how it looks.

    Skips only where the window cannot be set up at all, and says which.
    """
    if shutil.which("Xvfb") is None:
        pytest.skip("Xvfb is not installed, so there is no server to open the window on")
    if not _can_make_a_namespace():
        pytest.skip("`unshare -rm` cannot make a user namespace here, which the Xvfb recipe needs")

    probe = _load(_PROBE, "advtext_mouse_probe_for_gallery")
    inner = textwrap.dedent(f"""
        import os, runpy, sys
        sys.path.insert(0, {str(_PROBE.parent)!r})
        from mouse_probe import wait_for_tcp_display
        if not wait_for_tcp_display(os.environ["DISPLAY"], timeout=30.0):
            raise SystemExit("the Xvfb never accepted a connection")
        sys.argv = [{str(_EXAMPLE)!r}, "--frames", "6"]
        runpy.run_path({str(_EXAMPLE)!r}, run_name="__main__")
        """)
    command = probe.xvfb_command([sys.executable, "-c", inner], display=XVFB_DISPLAY)
    done = subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False, cwd=_ROOT
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = [line for line in done.stdout.splitlines() if line.startswith(("scheme=", "frames="))]
    panes = [dict(part.split("=") for part in line.split()) for line in lines[:-1]]
    total = dict(part.split("=") for part in lines[-1].split())
    assert total == {"frames": "6", "panes": "4", "followed": "0"}, done.stdout + done.stderr
    assert [pane["scheme"] for pane in panes] == ["page", "dark", "terminal", "notes"]
    assert [pane["dark"] for pane in panes] == ["0", "1", "1", "0"]
    for pane in panes:
        assert int(pane["glyphs"]) > 300, pane
        assert pane["missing"] == "0" and pane["unmapped"] == "0", pane
        assert int(pane["rules"]) >= 1 and int(pane["links"]) >= 1, pane

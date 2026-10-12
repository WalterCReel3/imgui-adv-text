"""
The Themes page and the demo's tokeniser: what a change does, counted.

Five kinds of test, and which is which matters when one goes red:

- **plain functions** -- `advtext.ui.pages._syntax` on strings, the schemes and
  face sets as data, `snap_height`. No ImGui, no library.
- **the page's state without a frame** -- the four setters, the markdown
  parsed. No library: the page has its state whether or not anything draws.
- **real ImGui frames with no backend**, in this process. The library is never
  ready here, so the page is ONE LINE saying why. Fake views show what this
  process can see of the rest: the bills, what a setter hands a view, the
  scroll position two panes share, and a view that fails mid-run leaving the
  page alive.
- **with the library, real frames, no window**
  (`test_page_document.typeset_child`; skipped with the reason when
  `IMTYPESET_LIBRARY` is not set).
- **the real app in a real window**, with the library (asserting in the child
  that it is imported and ready) and without it (the one line, no traceback
  page).

Nothing here says how a scheme looks. The colour assertions are "this ink
reached the vertex buffer", per scheme.

**One thing of the old core is used here on purpose**: `advtext.fontlib`, as
the independent measure in `test_the_running_text_is_set_at_the_pixel_height_asked_for`.
`Theme.at_pixel_height` measures a face with it (`.concerns/lead--tranche-5.md`,
decision 5), and that test checks the claim against the font file rather than
against the theme's own arithmetic. It is imported inside the test.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_page_document import (
    VARIABLES,
    WATCH_WITHOUT,
    says_only_why_not,
    typeset_child,
    unasked,
    windowed_typeset,
)

from advtext.description import FACE_ROLES
from advtext.theme import Align, BlockKind, Theme
from advtext.typeset_markdown import MarkdownCode, MarkdownConverter, parse_markdown
from advtext.ui.pages import PageContext, demo_text, discover, face_metrics
from advtext.ui.pages import _syntax as syntax
from advtext.ui.pages.themes import (
    COLOURS,
    FACE_SETS,
    FALLBACK_MARKDOWN,
    MAX_HEIGHT_PX,
    MIN_HEIGHT_PX,
    PAGE,
    Retypeset,
    ThemesPage,
    snap_height,
)
from advtext.ui.typeset_view import TypesetUnavailable
from advtext.units import px_from_sp

assert unasked  # the fixture, imported: `typesetter.module()` fails the test if asked

DISPLAY = (1100.0, 800.0)
PARKED = (DISPLAY[0] - 2.0, 2.0)

PYTHON = '''\
def spans(block, inks):
    """Ranges, each
    with an ink."""
    for start in tokens(block):  # a comment, with a "quote"
        if start == 0x2A or define_class:
            yield start, 1_000.5, 'it is # not a comment'
    return None
'''


# ----------------------------------------------------------------------
# The tokenisers
# ----------------------------------------------------------------------


def _kinds(text: str, language: str) -> list[tuple[str, str]]:
    return [(text[start:end], kind) for start, end, kind in syntax.tokens(text, language)]


def test_python_is_recognised_by_the_first_word_of_the_info_string() -> None:
    assert syntax.is_python("python")
    assert syntax.is_python("  Py title=x ")
    assert syntax.is_python("python3")
    assert not syntax.is_python("")
    assert not syntax.is_python("sh python")
    assert not syntax.is_python("pythonic")


def test_python_tokens_are_the_four_kinds_and_nothing_else() -> None:
    found = _kinds(PYTHON, "python")
    assert ("def", "keyword") in found
    assert ("for", "keyword") in found and ("in", "keyword") in found
    assert ("None", "keyword") in found and ("yield", "keyword") in found
    assert ("0x2A", "number") in found and ("1_000.5", "number") in found
    assert ('# a comment, with a "quote"', "comment") in found
    assert ("'it is # not a comment'", "string") in found
    assert ('"""Ranges, each\n    with an ink."""', "string") in found
    assert {kind for _, kind in found} == set(syntax.KINDS)
    # A keyword inside a name is part of the name: `define_class` holds two.
    words = [text for text, kind in found if kind == "keyword"]
    assert words.count("def") == 1 and "class" not in words
    # And the digits of a name are not a number.
    assert _kinds("x1 = y_2", "python") == []


def test_tokens_are_in_order_and_never_overlap() -> None:
    for language in ("python", "", "sh"):
        for text in (PYTHON, FALLBACK_MARKDOWN, "a = 'x' # y\n/* z\n */ 3", "", "'''"):
            end = 0
            for start, stop, kind in syntax.tokens(text, language):
                assert end <= start < stop <= len(text)
                assert kind in syntax.KINDS
                end = stop


def test_a_string_prefix_is_part_of_the_string_and_a_word_before_a_quote_is_not() -> None:
    assert _kinds("rb\"x\" f'y'", "python") == [('rb"x"', "string"), ("f'y'", "string")]
    assert _kinds('bar"x"', "python") == [('"x"', "string")]


def test_an_unclosed_string_runs_to_the_end_of_its_line_and_no_further() -> None:
    assert _kinds("a = 'half\nb = 1", "python") == [("'half", "string"), ("1", "number")]
    # A triple quote has no line to stop at: it takes the rest.
    assert _kinds('"""doc\nmore', "python") == [('"""doc\nmore', "string")]


def test_the_fallback_has_comments_strings_and_numbers_and_no_keywords() -> None:
    text = 'for x in 3: return "s" // c\n# d\n/* e\nf */ 0x1F'
    assert _kinds(text, "") == [
        ("3", "number"),
        ('"s"', "string"),
        ("// c", "comment"),
        ("# d", "comment"),
        ("/* e\nf */", "comment"),
        ("0x1F", "number"),
    ]
    # The same text as Python does have keywords, which is the whole difference.
    assert ("for", "keyword") in _kinds(text, "python")


def test_the_two_slashes_of_a_url_are_not_a_comment() -> None:
    assert _kinds("see http://example.org/a//b now", "sh") == [("//b now", "comment")]
    assert _kinds("see http://example.org/a now", "sh") == []


def test_line_tokens_cuts_a_multi_line_token_at_every_line_end() -> None:
    lines = PYTHON.splitlines()
    per_line = syntax.line_tokens(lines, "python")
    assert len(per_line) == len(lines)
    # The docstring opens on line 1 and closes on line 2: a string on both.
    assert [(lines[1][a:b], kind) for a, b, kind in per_line[1]] == [('"""Ranges, each', "string")]
    assert [(lines[2][a:b], kind) for a, b, kind in per_line[2]] == [
        ('    with an ink."""', "string")
    ]
    # Every piece is inside its own line, and the pieces say what `tokens` said.
    rebuilt = []
    for line, found in zip(lines, per_line, strict=True):
        for start, end, kind in found:
            assert 0 <= start < end <= len(line)
            rebuilt.append((line[start:end], kind))
    whole = [
        (piece, kind)
        for text, kind in _kinds("\n".join(lines), "python")
        for piece in text.split("\n")
        if piece
    ]
    assert rebuilt == whole


def test_line_tokens_keeps_empty_lines_and_an_empty_input() -> None:
    assert syntax.line_tokens([], "python") == ()
    assert syntax.line_tokens(["", "x = 1", ""], "python") == ((), ((4, 5, "number"),), ())
    # Tokenised one at a time the second line would be code, not a comment.
    assert syntax.line_tokens(["/* a", "b */"], "c") == (
        ((0, 4, "comment"),),
        ((0, 4, "comment"),),
    )


INKS = syntax.SyntaxInks(keyword=1, string=2, comment=3, number=4)


def test_an_ink_is_looked_up_by_kind_and_an_unknown_kind_is_an_error() -> None:
    assert [INKS.ink(kind) for kind in syntax.KINDS] == [3, 2, 4, 1]
    with pytest.raises(KeyError):
        INKS.ink("name")


def test_line_colours_is_the_shape_a_diff_view_takes() -> None:
    colour = syntax.line_colours(INKS)
    assert colour(["x = 1  # c", "return 'a'"], "python") == (
        ((4, 5, 4), (7, 10, 3)),
        ((0, 6, 1), (7, 10, 2)),
    )
    assert colour(["return 1"], "") == (((7, 8, 4),),)


PYTHON_FENCE = "```python\n" + PYTHON + "```\n"


def _code(source: str) -> MarkdownCode:
    (block,) = (
        block
        for block in parse_markdown(source, Theme.build()).blocks
        if isinstance(block, MarkdownCode)
    )
    return block


def test_plain_spans_are_the_tokens_with_their_inks_in_plain_offsets() -> None:
    """
    The form a `TypesetView` takes: offsets into the text given, which for a
    `MarkdownCode` is the text the view holds for the block.
    """
    block = _code("```python\ndef f():\n\treturn 'a'  # b\n```\n")
    assert "\t" not in block.text and block.language == "python"
    spans = syntax.plain_spans(block.text, INKS, block.language)
    assert spans == [
        (start, end, INKS.ink(kind)) for start, end, kind in syntax.tokens(block.text, "python")
    ]
    assert [(block.text[start:end], ink) for start, end, ink in spans] == [
        ("def", 1),
        ("return", 1),
        ("'a'", 2),
        ("# b", 3),
    ]
    assert syntax.plain_spans(block.text, INKS) == [
        (start, end, ink) for start, end, ink in spans if ink != 1
    ]
    assert syntax.plain_spans("", INKS, "python") == []


# What the OLD core's form inked (`_syntax.colour_spans`, since removed, over a `CodeBlock`,
# counting in `advtext.spans.material_text(block).text`), frozen on 2026-10-11
# while both forms existed (`.concerns/T5-FB-A-scripts/spans_frozen.py`): for
# each fence, the text the old core set the block as (tabs expanded) and the
# ink of each span in order. `plain_spans` over the direct path's block must
# read the same text and ink the same tokens: that the swap changed no
# colour of a code block is otherwise nowhere held.
OLD_SPANS = (
    (
        PYTHON_FENCE,
        PYTHON.rstrip("\n"),
        [1, 2, 1, 1, 3, 1, 4, 1, 1, 4, 2, 1, 1],
    ),
    (
        '```sh\nfor x in 1  # c\n\techo "a"\n```\n',
        'for x in 1  # c\n    echo "a"',
        [4, 3, 2],
    ),
    (
        "```python\ndef f():\n\treturn 'a'  # b\n```\n",
        "def f():\n    return 'a'  # b",
        [1, 1, 2, 3],
    ),
    ("```sh\nfor x in 1\n```\n", "for x in 1", [4]),
)


def test_plain_spans_ink_what_the_old_cores_colour_spans_inked() -> None:
    for source, text, inks in OLD_SPANS:
        block = _code(source)
        assert block.text == text, source
        assert [ink for _, _, ink in syntax.plain_spans(block.text, INKS, block.language)] == inks
    # The fence's own language unless told another: `sh` has no keywords, Python has.
    block = _code(OLD_SPANS[3][0])
    assert block.language == "sh"
    assert [ink for _, _, ink in syntax.plain_spans(block.text, INKS, "python")] == [1, 1, 4]


def test_the_old_cores_form_is_gone_with_its_last_caller() -> None:
    """
    `colour_spans` coloured an old-core `CodeBlock` through `advtext.spans`.
    Nothing calls it any more, and the module names no old-core module at all.
    """
    assert not hasattr(syntax, "colour_spans") and "colour_spans" not in syntax.__all__
    source = Path(syntax.__file__).read_text(encoding="utf-8")
    imports = [
        line for line in source.splitlines() if line.lstrip().startswith(("from ", "import "))
    ]
    assert not [line for line in imports if "advtext" in line], imports


def test_the_page_scan_does_not_take_the_tokeniser_for_a_page() -> None:
    found = discover()
    assert all("_syntax" not in failure.module for failure in found.failures)
    assert found.find("Themes") is PAGE
    assert found.find("_syntax") is None


# ----------------------------------------------------------------------
# Schemes and face sets, as data
# ----------------------------------------------------------------------


def test_there_are_four_schemes_and_two_of_them_are_dark() -> None:
    assert [colours.name for colours in COLOURS] == ["page", "dark", "terminal", "notes"]
    assert [colours.dark for colours in COLOURS] == [False, True, True, False]
    # Colours only: every one of the sixteen syntax inks is opaque and distinct
    # within its scheme.
    for colours in COLOURS:
        inks = [colours.syntax.ink(kind) for kind in syntax.KINDS]
        assert len(set(inks)) == 4 and all(ink >> 24 == 0xFF for ink in inks)


def _roles_of(theme: Theme, source: str) -> list[set[str]]:
    """
    For each block of `source` under `theme`: the face roles its description names.

    The block's own style's face and every run's. What the library is handed,
    read with no library: `MarkdownConverter.describe` needs none.
    """
    described = MarkdownConverter(theme).describe(parse_markdown(source, theme).blocks)
    names = {value: name for name, value in FACE_ROLES.items()}
    out = []
    for block in described.blocks:
        roles = {names[described.styles[block.style].Face]}
        roles.update(names[run.face] for run in block.runs if run.face)
        out.append(roles)
    return out


SMALL = "# Heading\n\nBody with **bold** and *italic* words.\n"


def test_the_three_face_sets_put_the_faces_where_their_labels_say(bundled_fonts: Path) -> None:
    roboto, mono, mixed = (face_set.theme(16.0, 96.0, face_metrics) for face_set in FACE_SETS)
    assert [face_set.name for face_set in FACE_SETS] == ["roboto", "mono", "mixed"]
    assert [face_set.align for face_set in FACE_SETS] == [Align.JUSTIFY, Align.LEFT, Align.LEFT]

    heading, paragraph = _roles_of(roboto, SMALL)
    assert heading == {"PROSE_BOLD"}
    assert paragraph == {"PROSE", "PROSE_BOLD", "PROSE_ITALIC"}

    # AD-gallery's finding, held: `Faces.mono()` alone would give Roboto Bold here.
    heading, paragraph = _roles_of(mono, SMALL)
    assert heading == {"CODE"} and paragraph == {"CODE"}

    # And the mix is that other answer, on purpose.
    heading, paragraph = _roles_of(mixed, SMALL)
    assert heading == {"PROSE_BOLD"} and paragraph == {"CODE", "PROSE_BOLD"}


@pytest.mark.parametrize("height", [10.0, 13.5, 16.0, 28.0])
@pytest.mark.parametrize("face_set", FACE_SETS, ids=lambda face_set: face_set.name)
def test_the_running_text_is_set_at_the_pixel_height_asked_for(
    bundled_fonts: Path, face_set: Any, height: float
) -> None:
    """
    The claim behind the reference line: ascent plus descent of the body, in pixels.

    Checked against `advtext.fontlib` directly rather than against
    `Theme.at_pixel_height`'s own arithmetic (the module docstring: this is
    the one use of the old core this file keeps, and why).
    """
    from advtext import fontlib

    theme = face_set.theme(height, 96.0, face_metrics)
    size = theme.style(BlockKind.PARAGRAPH).font.size
    metrics = fontlib.metrics(face_set.faces.regular, float(size))
    drawn = px_from_sp(round(metrics.ascent + metrics.descent), 96.0)
    assert drawn == pytest.approx(height, abs=0.01)


def test_a_slider_value_is_clamped_and_lands_on_a_half_pixel() -> None:
    assert snap_height(16.24) == 16.0
    assert snap_height(16.26) == 16.5
    assert snap_height(1.0) == MIN_HEIGHT_PX
    assert snap_height(99.0) == MAX_HEIGHT_PX


def test_the_demo_document_has_what_the_page_says_it_shows() -> None:
    source = demo_text("themes.md")
    assert source is not None
    codes = [
        block
        for block in parse_markdown(source, Theme.build()).blocks
        if isinstance(block, MarkdownCode)
    ]
    assert [block.language for block in codes] == ["python", "sh"]
    # Both tokenisers have something to colour, in all four kinds between them.
    kinds = {kind for block in codes for _, _, kind in syntax.tokens(block.text, block.language)}
    assert kinds == set(syntax.KINDS)
    assert source.count("](https://example.org/") == 3


def test_the_schemes_roles_are_the_palettes_own_merge() -> None:
    """
    The four schemes are made with `Palette.with_roles`. The page carried a
    copy of that merge (`_roled`) while the method read `BlockKind` from
    `advtext.style`, so that importing the page did not load the measuring
    half; the method reads `advtext.theme` now and the copy is gone
    (`tests/test_typeset_closure.py` holds what importing the page loads).
    """
    from advtext.ui.pages import themes

    assert not hasattr(themes, "_roled")
    assert all(colours.palette.roles for colours in COLOURS)
    for colours in COLOURS:
        bare = replace(colours.palette, roles=())
        assert bare.with_roles(dict(colours.palette.roles)) == colours.palette
        kinds = [kind.value for kind, _ in colours.palette.roles]
        assert kinds == sorted(kinds)


# ----------------------------------------------------------------------
# The page's state, without a frame and without the library
# ----------------------------------------------------------------------


@pytest.fixture
def page(bundled_fonts: Path, unasked: None) -> ThemesPage:
    made = PAGE.factory(PageContext.build())
    assert isinstance(made, ThemesPage)
    return made


def test_the_page_opens_on_one_pane_one_parse_and_the_first_of_everything(
    page: ThemesPage,
) -> None:
    assert page.documents_built == 1 and len(page.parsed.blocks) > 10
    assert not page.split and len(page.shown) == 1
    assert page.face_set is FACE_SETS[0] and page.height_px == 16.0
    assert [pane.colours.name for pane in page.panes] == ["page", "dark"]
    assert page.status().startswith("Click a link")
    assert page.last is None
    # No library in this process: the state is all there, and no view.
    assert [pane.view for pane in page.panes] == [None, None]
    assert not page.typeset and page.renderer == "none" and page.reason


def test_the_launch_option_opens_it_split(bundled_fonts: Path, unasked: None) -> None:
    context = PageContext.build(request_page="themes", request_options=("split",))
    made = ThemesPage(context)
    assert made.split and len(made.shown) == 2
    other = PageContext.build(request_page="stream", request_options=("split",))
    assert not ThemesPage(other).split
    assert PAGE.accepts("split") and PAGE.shot_specs() == ("themes", "themes:split")


def test_a_palette_change_parses_nothing(page: ThemesPage) -> None:
    parsed, theme = page.parsed, page.theme
    page.set_colours(0, COLOURS[2])
    assert page.documents_built == 1 and page.parsed is parsed and page.theme is theme
    assert page.panes[0].colours is COLOURS[2]
    # The other pane keeps its own scheme.
    assert page.panes[1].colours is COLOURS[1]


def test_a_theme_change_parses_exactly_once_for_both_panes(page: ThemesPage) -> None:
    parsed, theme = page.parsed, page.theme
    page.set_face_set(FACE_SETS[1])
    assert page.documents_built == 2
    assert page.parsed is not parsed and page.theme is not theme
    assert page.theme.style(BlockKind.PARAGRAPH).align is Align.LEFT
    page.set_height(20.2)
    assert page.height_px == 20.0 and page.documents_built == 3


def test_a_change_to_what_is_already_so_does_nothing(page: ThemesPage) -> None:
    parsed, theme = page.parsed, page.theme
    page.set_colours(0, COLOURS[0])
    page.set_face_set(FACE_SETS[0])
    page.set_height(16.1)
    page.set_split(False)
    assert page.documents_built == 1 and page.parsed is parsed and page.theme is theme
    # With no view nothing is laid out, so nothing is billed.
    assert page.account() is None and page.last is None


def test_without_the_demo_file_the_page_still_has_a_document(
    bundled_fonts: Path, unasked: None
) -> None:
    made = ThemesPage(PageContext.build(), source=FALLBACK_MARKDOWN)
    assert any(isinstance(block, MarkdownCode) for block in made.parsed.blocks)
    assert made.panes[0].colour_code() == 0, "no view to hand an ink to"


def test_the_reference_line_states_the_size_the_slider_is_at(page: ThemesPage) -> None:
    page.set_height(13.26)
    assert page.sample().startswith("imgui.text at 13.5 px")
    assert page.sample_font() is None, "no atlas here, and the library is not asked for one"


# ----------------------------------------------------------------------
# Real frames, no library: one line saying why; the rest over fake views
# ----------------------------------------------------------------------


def _frame(
    page: ThemesPage,
    *,
    mouse: tuple[float, float] | None = None,
    left: bool | None = None,
    wheel: float | None = None,
    size: tuple[float, float] = DISPLAY,
    draw: Any = None,
) -> int:
    """
    One frame of the page in a window filling the display. Returns the vertex count.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui

    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*size)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if left is not None:
        io.add_mouse_button_event(0, left)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*size))
        imgui.begin("##advtext-themes-test", None, imgui.WindowFlags_.no_decoration.value)
        try:
            (page.draw if draw is None else draw)()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def test_without_the_library_the_page_is_one_line_saying_why(
    monkeypatch: pytest.MonkeyPatch, unasked: None, bundled_fonts: Path
) -> None:
    """
    `set` is `make test TYPESET=1`'s case in this process: the variable is
    there, no fonts were loaded, and the page must not import the library to
    find that out. No controls, no panes: the line and nothing else.
    """
    for variable in ("unset", "set"):
        for name in VARIABLES:
            monkeypatch.delenv(name, raising=False)
        if variable == "set":
            monkeypatch.setenv(VARIABLES[0], "/somewhere/lib.so")
        made = ThemesPage(PageContext.build(request_page="themes", request_options=("split",)))
        assert not made.typeset and made.renderer == "none" and made.reason
        assert [pane.view for pane in made.panes] == [None, None]
        says_only_why_not(made.draw, made.reason)
        assert made.last is None and made.bills == {}


class _FakeView:
    """
    What the page reads of a `TypesetView`: a tall item, and a record of what it was told.

    `fail` names the call that raises (`"draw"` or `"stats"`) and `fail_at`
    the draw from which it does.
    """

    def __init__(
        self,
        parsed: Any,
        fail_at: int = 10**9,
        fail: str = "draw",
        error: Exception | None = None,
    ) -> None:
        self.blocks = tuple(parsed.blocks)
        self.texts = tuple("x" for _ in self.blocks)
        self.fail_at = fail_at
        self.fail = fail
        self.error = error or TypesetUnavailable("imtypeset failed and is switched off: Error: no")
        self.debug = False
        self.draws = 0
        self.origin: tuple[float, float] | None = None
        self.native_document = object()
        self.edits = {"set": 1}
        self.palettes: list[Any] = []
        self.themes: list[tuple[Any, Any]] = []
        self.inks: dict[int, list[tuple[int, int, int]]] = {}

    def clear_colours(self) -> None:
        self.inks = {}

    def set_colours(self, block: int, spans: Any) -> None:
        self.inks[block] = list(spans)

    def set_palette(self, palette: Any) -> None:
        self.palettes.append(palette)
        self.native_document = object()
        self.edits["set"] += 1

    def set_theme(self, theme: Any, parsed: Any) -> None:
        self.themes.append((theme, parsed))
        self.blocks = tuple(parsed.blocks)
        self.native_document = object()
        self.edits["set"] += 1
        self.inks = {}

    @property
    def stats(self) -> Any:
        if self.fail == "stats" and self.draws >= self.fail_at:
            raise self.error
        return SimpleNamespace(blocks_laid_out=min(self.draws, 3))

    def draw(self, **kwargs: Any) -> bool:
        from imgui_bundle import imgui

        self.draws += 1
        if self.fail == "draw" and self.draws >= self.fail_at:
            raise self.error
        at = imgui.get_cursor_screen_pos()
        self.origin = (float(at.x), float(at.y))
        imgui.dummy(imgui.ImVec2(40.0, 3000.0))
        return True


def _on_fake_views(spec: tuple[str, ...] = (), **failing: Any) -> ThemesPage:
    """
    The page as it is built with the library, over views that draw one tall item each.

    `failing` is `_FakeView`'s `fail_at` / `fail` / `error`, given to the
    SECOND pane's view when `spec` has `"split"` and to the first otherwise:
    the pane drawn last is the one whose failure has the most to undo.
    """
    made = ThemesPage(PageContext.build(request_page="themes", request_options=spec))
    last = len(made.shown) - 1
    for number, pane in enumerate(made.panes):
        pane.view = _FakeView(made.parsed, **(failing if number == last else {}))
        pane.colour_code()
    made.reason = ""
    # The reference line's font is the library's, and the library is not in
    # this process to be asked.
    made.sample_font = lambda: None  # type: ignore[method-assign]
    assert made.typeset and made.renderer == "TypesetView"
    return made


@pytest.fixture
def shown(bundled_fonts: Path, unasked: None) -> ThemesPage:
    """
    The page over fake views after two settling frames, mouse parked and up.
    """
    made = _on_fake_views()
    _frame(made, mouse=PARKED, left=False)
    _frame(made, mouse=PARKED)
    return made


def _code_inks(made: ThemesPage, pane: int) -> dict[int, list[tuple[int, int, int]]]:
    colours = made.panes[pane].colours
    return {
        number: syntax.plain_spans(block.text, colours.syntax, block.language)
        for number, block in enumerate(made.parsed.blocks)
        if isinstance(block, MarkdownCode)
    }


def test_the_first_frame_bills_the_opening_and_the_second_nothing(
    bundled_fonts: Path, unasked: None
) -> None:
    made = _on_fake_views()
    _frame(made, mouse=PARKED, left=False)
    opened = made.last
    assert isinstance(opened, Retypeset) and opened.cause == "open"
    assert (opened.documents, opened.handed) == (1, 1)
    assert opened.blocks == len(made.parsed.blocks) > 10
    assert opened.line() == (
        "last change: open -- markdown parsed 1, documents handed to the library 1, "
        f"blocks laid out in that frame {opened.laid_out} of {opened.blocks}"
    )
    _frame(made, mouse=PARKED)
    assert made.last is opened
    first, second = (pane.view for pane in made.panes)
    assert first.draws == 2 and second.draws == 0, "the hidden pane is never drawn"
    # Every code block was inked when the view was made, in its pane's scheme.
    assert first.inks == _code_inks(made, 0) and len(first.inks) == 2
    assert second.inks == _code_inks(made, 1) != first.inks


def test_a_palette_change_gives_the_view_the_palette_and_new_inks(shown: ThemesPage) -> None:
    view = shown.panes[0].view
    before = dict(view.inks)
    shown.set_colours(0, COLOURS[2])
    assert view.palettes == [COLOURS[2].palette] and shown.panes[1].view.palettes == []
    assert view.inks == _code_inks(shown, 0) != before
    _frame(shown)
    bill = shown.last
    assert bill is not None and (bill.cause, bill.documents, bill.handed) == ("palette", 0, 1)
    assert bill.line().startswith("last change: palette -- markdown parsed 0, ")
    _frame(shown)
    assert shown.last is bill


@pytest.mark.parametrize("change", ["faces", "size"])
def test_a_theme_change_gives_both_views_the_one_new_parse(shown: ThemesPage, change: str) -> None:
    if change == "faces":
        shown.set_face_set(FACE_SETS[1])
    else:
        shown.set_height(21.0)
    for pane in shown.panes:
        # The hidden pane too: it would otherwise open on a document the page no longer has.
        assert pane.view.themes == [(shown.theme, shown.parsed)]
        assert pane.view.inks == _code_inks(shown, shown.panes.index(pane))
    _frame(shown)
    bill = shown.last
    assert bill is not None and (bill.cause, bill.documents, bill.handed) == (change, 1, 1)
    _frame(shown)
    assert shown.last is bill


def test_the_split_is_billed_and_a_resize_nobody_asked_for_is_billed_as_width(
    shown: ThemesPage,
) -> None:
    single = shown.last
    assert single is not None
    wide = shown.panes[0].width
    shown.set_split(True)
    _frame(shown)
    both = shown.last
    assert both is not None and (both.cause, both.documents) == ("split", 0)
    assert both.blocks == 2 * single.blocks
    assert shown.panes[0].width == shown.panes[1].width < wide / 2
    shown.set_split(False)
    _frame(shown)
    back = shown.last
    assert (
        back is not None
        and back is not both
        and (back.cause, back.blocks)
        == (
            "split",
            single.blocks,
        )
    )
    _frame(shown, size=(900.0, 800.0))
    resized = shown.last
    assert resized is not None and (resized.cause, resized.documents) == ("width", 0)
    assert shown.bills.keys() == {"open", "split", "width"}


def test_the_two_panes_of_a_split_stay_at_one_scroll_position(shown: ThemesPage) -> None:
    """
    Wheel over either pane, and both documents' tops are at the same screen row.

    A view's `origin` is where the document's top was drawn, so equal `y` in
    two panes of one row is equal scroll. Each pane leads in each direction,
    since the pane drawn second takes the lead a frame later than the first
    does -- and an earlier draft of the page handed the lead straight back to
    whichever pane had *not* moved, which this is the test for.

    The scrolling is ImGui's and the page's, not the view's: the fake views
    are one tall item each.
    """
    short = (DISPLAY[0], 420.0)
    parked = (short[0] - 2.0, 2.0)
    shown.set_split(True)
    for _ in range(6):
        _frame(shown, mouse=parked, size=short)
    first, second = (pane.view for pane in shown.panes)
    assert first.origin is not None and second.origin is not None
    top = first.origin[1]
    assert second.origin[1] == top

    for over, wheel in ((first, -2.0), (second, -1.0), (second, 1.0), (first, 1.0)):
        before = first.origin[1]
        _frame(shown, mouse=(over.origin[0] + 20.0, 300.0), wheel=wheel, size=short)
        for _ in range(6):
            _frame(shown, size=short)
        assert first.origin[1] == second.origin[1]
        if wheel < 0:
            assert first.origin[1] < before
        else:
            assert first.origin[1] > before
    assert first.origin[1] < top


def test_a_pane_opened_by_the_split_arrives_where_the_first_already_is(
    shown: ThemesPage,
) -> None:
    short = (DISPLAY[0], 420.0)
    parked = (short[0] - 2.0, 2.0)
    for _ in range(3):
        _frame(shown, mouse=parked, size=short)
    view = shown.panes[0].view
    assert view.origin is not None
    top = view.origin[1]
    _frame(shown, mouse=(view.origin[0] + 20.0, 300.0), wheel=-4.0, size=short)
    for _ in range(3):
        _frame(shown, size=short)
    assert view.origin[1] < top
    shown.set_split(True)
    for _ in range(8):
        _frame(shown, mouse=parked, size=short)
    other = shown.panes[1].view
    assert other.origin is not None
    # The second pane's child window had never been drawn and opens at the top.
    # What is held: it was brought to the first, and the first was not taken
    # back to the top by it.
    assert other.origin[1] == view.origin[1] < top


def test_the_debug_overlay_is_the_shared_flag(shown: ThemesPage) -> None:
    shown.context.debug = True
    _frame(shown)
    assert shown.panes[0].view.debug is True
    shown.context.debug = False
    _frame(shown)
    assert shown.panes[0].view.debug is False


@pytest.mark.parametrize("split", [False, True], ids=["one pane", "the second pane"])
@pytest.mark.parametrize("call", ["draw", "stats"])
def test_a_view_that_fails_mid_run_leaves_the_page_alive_and_saying_why(
    call: str, split: bool, unasked: None, bundled_fonts: Path
) -> None:
    """
    `TypesetUnavailable` out of a view call of a frame does not leave `draw`
    (so it cannot reach the app's traceback page): BOTH panes lose their
    views, also when it was the second pane that failed after the first had
    drawn, and from the next frame on the page is the one line. The page's
    state is what it was.
    """
    made = _on_fake_views(("split",) if split else (), fail_at=2, fail=call)
    scheme = [pane.colours for pane in made.panes]
    views = [pane.view for pane in made.panes]
    _frame(made, mouse=PARKED, left=False)
    assert made.typeset and made.last is not None and made.last.cause == "open"
    _frame(made, mouse=PARKED)
    assert not made.typeset and made.renderer == "none"
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    assert [pane.view for pane in made.panes] == [None, None]
    assert [pane.colours for pane in made.panes] == scheme and made.split is split
    draws = [view.draws for view in views]
    says_only_why_not(made.draw, made.reason)
    assert [view.draws for view in views] == draws
    # The setters still work on the state, and reach no view.
    built = made.documents_built
    made.set_colours(0, COLOURS[3])
    made.set_face_set(FACE_SETS[2])
    assert made.documents_built == built + 1 and made.panes[0].colours is COLOURS[3]
    assert made.account() is None


def test_an_exception_that_is_not_the_librarys_is_a_bug_and_propagates(
    unasked: None, bundled_fonts: Path
) -> None:
    made = _on_fake_views(("split",), fail_at=2, error=ZeroDivisionError("a bug in the page"))
    _frame(made, mouse=PARKED, left=False)
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    _frame(made, draw=draw)  # the frame still closes: the pane and its colour were popped
    assert len(raised) == 1 and made.typeset and made.renderer == "TypesetView"


# ----------------------------------------------------------------------
# With the library, real frames, no window
# ----------------------------------------------------------------------

_TYPESET = r"""
import dataclasses, statistics
from advtext.description import FACE_ROLES
from advtext.typeset_markdown import MarkdownCode, MarkdownConverter
from advtext.ui.pages import _syntax as syntax
from advtext.ui.pages import themes as page
from advtext.ui.pages.themes import COLOURS, FACE_SETS, ThemesPage
from advtext.theme import BlockKind

PARKED = (SIZE[0] - 2.0, 2.0)
made = ThemesPage(context("themes"))
ts = typesetter.module()


def step(count=1, size=SIZE, at=None, left=None, wheel=None, collect=True):
    # Frames of the page alone; returns every vertex colour of the last one.
    if at is not None:
        io.add_mouse_pos_event(*at)
    if left is not None:
        io.add_mouse_button_event(0, left)
    if wheel is not None:
        io.add_mouse_wheel_event(0.0, wheel)
    for _ in range(count):
        io.display_size = imgui.ImVec2(*size)
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(*size))
            imgui.begin("##advtext-themes-child", None, imgui.WindowFlags_.no_decoration.value)
            try:
                made.draw()
            finally:
                imgui.end()
        finally:
            imgui.render()
    colours = set()
    if not collect:
        return colours
    for draw_list in imgui.get_draw_data().cmd_lists:
        buffer = draw_list.vtx_buffer
        colours.update(int(buffer[index].col) for index in range(buffer.size()))
    return colours


def bill():
    return None if made.last is None else dataclasses.asdict(made.last)


report["built"] = [made.renderer, made.typeset, made.documents_built, made.reason,
                   [type(pane.view).__name__ for pane in made.panes],
                   made.panes[0].view.blocks == made.panes[1].view.blocks == made.parsed.blocks]
step(at=PARKED, left=False)
opened = made.last
report["open"] = bill()
report["open_line"] = opened.line()
step()
report["second_frame_bills_nothing"] = made.last is opened
report["hidden_pane"] = [made.panes[1].view.native_document is None, made.panes[1].whole]
report["code_blocks"] = sum(isinstance(b, MarkdownCode) for b in made.panes[0].view.blocks)
report["inked_blocks"] = len(made.panes[0].view._colours)

# Every scheme: body ink, link ink, the four syntax inks, the ground and a heading's role ink.
schemes = []
previous = set()
for colours in (COLOURS[1], COLOURS[2], COLOURS[3], COLOURS[0]):
    made.set_colours(0, colours)
    drawn = step()
    wanted = {colours.palette.ink, colours.palette.link, colours.background,
              *(colours.syntax.ink(kind) for kind in syntax.KINDS)}
    role = dict(colours.palette.roles).get(BlockKind.HEADING_1)
    schemes.append({"name": colours.name, "missing": sorted(wanted - drawn),
                    "left_over": sorted((previous - wanted) & drawn),
                    "role_drawn": None if role is None else role in drawn, "bill": bill()})
    previous = {colours.syntax.ink(kind) for kind in syntax.KINDS}
report["schemes"] = schemes
report["palette_line"] = made.last.line()

# The face sets: which roles the description names, per set.
def roles_named():
    described = MarkdownConverter(made.theme).describe(made.parsed.blocks)
    names = {value: name for name, value in FACE_ROLES.items()}
    faces = {names[style.Face] for style in described.styles}
    for block in described.blocks:
        faces.update(names[run.face] for run in block.runs if run.face)
    return sorted(faces)

faces = {FACE_SETS[0].name: {"roles": roles_named()}}
for face_set in (FACE_SETS[1], FACE_SETS[2], FACE_SETS[0]):
    view = made.panes[0].view
    made.set_face_set(face_set)
    drawn = step()
    inks = {made.panes[0].colours.syntax.ink(kind) for kind in syntax.KINDS}
    faces[face_set.name + ("" if face_set is not FACE_SETS[0] else " again")] = {
        "roles": roles_named(), "bill": bill(), "same_view": made.panes[0].view is view,
        "inks_drawn": inks <= drawn, "whole": made.panes[0].whole,
        "themes": [pane.view.theme is made.theme for pane in made.panes],
    }
report["faces"] = faces
report["documents_built"] = made.documents_built

# The size: the lines of the first paragraph grow with it.
def paragraph():
    view = made.panes[0].view
    number = next(n for n in range(len(view.texts)) if view.block_role(n) == "PARAGRAPH")
    lines = view.set_lines(number, number + 1)
    return lines[0].bottom - lines[0].top

before = paragraph()
made.set_height(20.2)
step()
report["size"] = {"height": made.height_px, "bill": bill(), "line_before": before,
                  "line_after": paragraph()}

# The reference line: the library's own font for the regular role, and the width
# it gives a string against the width the library sets that string to.
font = made.sample_font()
index = ts.font_atlas_index(FACE_ROLES[made.face_set.faces.regular.name])
fonts = imgui.get_io().fonts.fonts
alphabet = "abcdefghijklmnopqrstuvwxyz"
imgui.new_frame()
imgui.push_font(font, made.height_px)
reference = imgui.calc_text_size(alphabet).x
imgui.pop_font()
imgui.render()
report["sample"] = {"index": index, "fonts": len(fonts), "is_library_font": font is not None,
                    "reference_width": reference,
                    "library_width": ts.calc_text_size(
                        alphabet, style=typesetter.base_style(made.theme))[0],
                    "text": made.sample()}
made.set_height(16.0)
step()

# The split: both panes drawn, at one scroll position.
first_width = made.panes[0].width
made.set_split(True)
step()
report["split"] = {"bill": bill(),
                   "widths": [made.panes[0].width, made.panes[1].width, first_width],
                   "second_drawn": made.panes[1].view.native_document is not None}
step(count=4)
origin = made.panes[0].view.origin
step(at=(origin[0] + 40.0, 400.0))
step(wheel=-6.0)
step(count=8)
report["scroll"] = [pane.scroll for pane in made.panes]
report["scroll_origins"] = [pane.view.origin[1] for pane in made.panes]
step(at=PARKED)
made.set_split(False)
step()
report["unsplit"] = bill()

# A resize nobody asked for is billed as width.
step(size=(900.0, 800.0))
report["width"] = bill()
step(size=SIZE, count=2)

# A clicked link is shown on the status line and opens nothing.
view = made.panes[0].view
made.set_split(False)
step(count=2)
link = view.links[0]
view.scroll_to(link.block, link.start, align=0.3)
step(count=6)
left, top, right, bottom = view.span_rects(link.block, link.start, link.end)[0]
point = (view.origin[0] + (left + right) / 2, view.origin[1] + (top + bottom) / 2)
step(at=point, count=2)
hovered = view.hovered_link
step(left=True)
step(left=False)
step()
report["link"] = [link.target, hovered, list(made.followed), made.status()]
step(at=PARKED, count=2)

# What a switch costs here, in milliseconds, beside a frame that changes nothing.
# The change and the frame after it; median of seven. Read as ratios: the load is in the report.
def timed(change, repeat=7):
    took = []
    for n in range(repeat):
        began = time.perf_counter()
        change(n)
        step(collect=False)
        took.append((time.perf_counter() - began) * 1000.0)
    return round(statistics.median(took), 3)

def another(n):
    global made
    made = ThemesPage(context("themes"))

report["timing_ms"] = {
    "steady_frame": timed(lambda n: None, 15),
    "palette": timed(lambda n: made.set_colours(0, COLOURS[(n + 1) % 4])),
    "faces": timed(lambda n: made.set_face_set(FACE_SETS[(n + 1) % 3])),
    "size": timed(lambda n: made.set_height(14.0 + n)),
    "new_page": timed(another),
    "blocks": len(made.panes[0].view.texts),
}

# The debug overlay is the shared flag.
made.context.debug = True
step()
report["debug"] = made.panes[0].view.debug
made.context.debug = False

# The library switched off under the page, split, so that both panes are in the
# frame: it stays alive, no pane has a view, and it is one line saying why.
made.set_split(True)
step(count=2)
held = [made.face_set.name, made.height_px, [pane.colours.name for pane in made.panes],
        made.documents_built]
switch_off("switched off by the test")
raised = None
try:
    step()
except Exception as exc:
    raised = repr(exc)
report["after"] = [made.renderer, made.reason, made.typeset, [pane.view for pane in made.panes],
                   raised, [made.face_set.name, made.height_px,
                            [pane.colours.name for pane in made.panes],
                            made.documents_built] == held, made.split]
step(count=2)
report["later"] = [made.renderer, only_the_line(made.draw, made.reason)]
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    return typeset_child(_TYPESET)


def test_with_the_library_the_page_opens_on_typeset_views_over_one_parse(
    typeset: dict[str, Any],
) -> None:
    renderer, on, built, reason, panes, shared = typeset["built"]
    assert (renderer, on, built, reason) == ("TypesetView", True, 1, "")
    assert panes == ["TypesetView", "TypesetView"]
    assert shared is True, "one parse_markdown serves both views"
    opened = typeset["open"]
    assert (opened["cause"], opened["documents"], opened["handed"]) == ("open", 1, 1)
    # The library lays out what the window shows, which is most of this short document.
    assert 0 < opened["laid_out"] <= opened["blocks"] and opened["blocks"] > 10
    assert typeset["open_line"] == (
        "last change: open -- markdown parsed 1, documents handed to the library 1, "
        f"blocks laid out in that frame {opened['laid_out']} of {opened['blocks']}"
    )
    assert typeset["second_frame_bills_nothing"] is True
    # The hidden pane has no library document at all.
    assert typeset["hidden_pane"] == [True, True]
    assert typeset["code_blocks"] == typeset["inked_blocks"] >= 1


def test_with_the_library_every_scheme_reaches_the_vertex_buffer_and_the_last_leaves_it(
    typeset: dict[str, Any],
) -> None:
    """
    Per scheme: body ink, link ink, all four syntax inks (`plain_spans` through
    `set_colours`) and the ground are drawn, a heading is in its role's ink,
    and the syntax inks of the scheme just left are gone.

    **What a palette change costs here**: the link ink is in the runs, so the
    document is described again and handed to the library whole (`handed` 1),
    and the window's blocks are laid out again. Nothing is parsed.
    """
    assert [scheme["name"] for scheme in typeset["schemes"]] == [
        "dark",
        "terminal",
        "notes",
        "page",
    ]
    for scheme in typeset["schemes"]:
        assert scheme["missing"] == [] and scheme["left_over"] == [], scheme["name"]
        assert scheme["role_drawn"] in (True, None), scheme["name"]
        bill = scheme["bill"]
        assert (bill["cause"], bill["documents"], bill["handed"]) == ("palette", 0, 1)
        assert 0 < bill["laid_out"] <= bill["blocks"]
    assert sum(scheme["role_drawn"] is True for scheme in typeset["schemes"]) == 3


def test_with_the_library_a_face_set_is_roles_rearranged_and_one_parse_for_both_panes(
    typeset: dict[str, Any],
) -> None:
    faces = typeset["faces"]
    assert faces["roboto"]["roles"] == ["CODE", "PROSE", "PROSE_BOLD", "PROSE_ITALIC"]
    # Everything in the code role; and the mixed set keeps the proportional bold.
    assert faces["mono"]["roles"] == ["CODE"]
    assert faces["mixed"]["roles"] == ["CODE", "PROSE_BOLD"]
    assert faces["roboto again"]["roles"] == faces["roboto"]["roles"]
    for name in ("mono", "mixed", "roboto again"):
        got = faces[name]
        bill = got["bill"]
        # One parse; the one pane drawn hands the library one new document.
        assert (bill["cause"], bill["documents"], bill["handed"]) == ("faces", 1, 1), name
        assert 0 < bill["laid_out"] <= bill["blocks"]
        assert got["same_view"] is True and got["themes"] == [True, True]
        assert got["inks_drawn"] is True and got["whole"] is True, name
    assert typeset["documents_built"] == 4


def test_with_the_library_the_size_sets_the_text_and_the_reference_line_together(
    typeset: dict[str, Any],
) -> None:
    """
    The slider's claim on this path, measured: the reference line is pushed in
    the library's own font for the regular role at the slider's height, and
    ImGui gives the lowercase alphabet in it the width the library sets the
    same string to in the theme's body style.
    """
    size = typeset["size"]
    assert size["height"] == 20.0
    assert (size["bill"]["cause"], size["bill"]["documents"]) == ("size", 1)
    assert size["line_after"] / size["line_before"] == pytest.approx(20.0 / 16.0, rel=0.01)
    sample = typeset["sample"]
    assert sample["index"] is not None and 0 <= sample["index"] < sample["fonts"]
    assert sample["is_library_font"] is True
    assert sample["reference_width"] == pytest.approx(sample["library_width"], abs=1.0)
    assert sample["text"].startswith("imgui.text at 20.0 px")


def test_with_the_library_the_split_draws_both_panes_at_one_scroll_position(
    typeset: dict[str, Any],
) -> None:
    split = typeset["split"]
    bill = split["bill"]
    # The second view's first draw is its first document.
    assert (bill["cause"], bill["documents"], bill["handed"]) == ("split", 0, 1)
    assert bill["blocks"] == 2 * typeset["open"]["blocks"] and split["second_drawn"] is True
    left, right, single = split["widths"]
    assert left == right < single / 2
    first, second = typeset["scroll"]
    assert first == second > 0.0
    assert typeset["scroll_origins"][0] == typeset["scroll_origins"][1]
    off = typeset["unsplit"]
    assert (off["cause"], off["documents"], off["handed"]) == ("split", 0, 0)
    assert off["blocks"] == typeset["open"]["blocks"] and off["laid_out"] > 0
    wide = typeset["width"]
    assert (wide["cause"], wide["documents"], wide["handed"]) == ("width", 0, 0)
    assert wide["laid_out"] > 0


def test_with_the_library_a_link_the_debug_flag_and_the_switch_off(
    typeset: dict[str, Any],
) -> None:
    target, hovered, followed, status = typeset["link"]
    assert hovered == target and followed == [target] and status == f"link 1: {target}"
    assert typeset["debug"] is True
    renderer, reason, on, views, raised, kept, split = typeset["after"]
    assert (renderer, on, views, raised) == ("none", False, [None, None], None)
    assert "switched off by the test" in reason
    assert kept is True and split is True, "the page's state is what it was"
    renderer, (drawn, line) = typeset["later"]
    assert renderer == "none" and drawn == line > 0, "the page is the one line and nothing else"


def test_with_the_library_what_a_switch_costs_is_reported(typeset: dict[str, Any]) -> None:
    """
    Not a bound: the numbers go to the result file with the load beside them.
    Held here only as far as a count can be: each is a positive time.
    """
    timing = typeset["timing_ms"]
    print("themes timing (ms)", timing, "load", typeset["load_start"], typeset["load_end"])
    assert all(
        timing[name] > 0.0 for name in ("steady_frame", "palette", "faces", "size", "new_page")
    )


_WATCH = r"""
def watch(app, made, frame):
    if frame == 6:
        report["opened"] = [made.renderer, made.typeset, made.split, made.last.cause]
    elif frame == 8:
        made.set_colours(0, made.panes[1].colours)
    elif frame == 10:
        report["palette"] = made.last.line()
        from advtext.ui.pages.themes import FACE_SETS
        made.set_face_set(FACE_SETS[1])
    elif frame == 14:
        report["faces"] = made.last.line()
        report["panes"] = [[type(pane.view).__name__, pane.whole, pane.view.stats.vertices,
                            pane.view.native_document is not None] for pane in made.panes]
        report["sample_font"] = made.sample_font() is not None
        report["renderer"] = made.renderer
        finish()
"""


def test_in_a_real_window_with_the_library_both_panes_are_typeset_views(
    window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = windowed_typeset(window, monkeypatch, "themes:split", _WATCH)
    assert report["current"] == "Themes" and report["reason"] == "" and report["trouble"] == ""
    assert report["opened"] == ["TypesetView", True, True, "open"]
    assert report["renderer"] == "TypesetView"
    assert report["palette"].startswith("last change: palette -- markdown parsed 0, ")
    assert report["faces"].startswith("last change: faces -- markdown parsed 1, ")
    for view, whole, vertices, has_document in report["panes"]:
        assert view == "TypesetView" and whole is True and has_document is True
        assert vertices > 1000
    assert report["sample_font"] is True


def test_in_a_real_window_without_the_library_the_page_says_why_and_stays_up(
    window: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The plain gate's window: no views and a reason, the library never
    imported, nothing on the traceback page. The page has no `report()`.
    """
    watch = WATCH_WITHOUT.replace("made.typeset is None", "not made.typeset").replace(
        'report["text"] = made.report()', 'report["split"] = made.split'
    )
    report = windowed_typeset(window, monkeypatch, "themes:split", watch, how="without")
    assert report["current"] == "Themes" and report["reason"]
    assert report["renderer"] == "none" and report["typeset"] is True and report["split"] is True

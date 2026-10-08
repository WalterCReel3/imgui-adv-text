"""
A block the host draws, and the diff that was the reason for it: `BareView.host_for`,
`advtext.ui.HostBlock`, `advtext.ui.diff_view.DiffFences`.

**Four levels, so nobody reads more into a green run than is there.**

1. The layout with no ImGui: the stand-in's unit, what a copy across it writes,
   what the hook is asked and how often.
2. `DiffFences` reading a fence: from the source and from the code block,
   whole and a line at a time, with the work counted rather than timed.
3. Real ImGui frames with no backend: where the embedded view is drawn, which
   view a press belongs to, who answers Ctrl+C, what is culled.
4. One real window (`tests/conftest.py::window`): a stream with a diff in it,
   drawn as it arrives, reporting counts.

**Nothing here says how an embedded diff looks.**
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

import advtext.ui
import advtext.ui.units
from advtext.backends.imgui_draw import DARK_PALETTE, DrawStats
from advtext.diff import Diff, UnifiedDiffStream
from advtext.markdown import Block, CodeBlock, Document, TextBlock, build_document
from advtext.selection import Selection
from advtext.stream import StreamDocument
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui import HostBlock
from advtext.ui.bare_view import BareView
from advtext.ui.diff_view import DiffFences, DiffLayout, DiffView, HostedDiff
from advtext.ui.stream_view import StreamView
from advtext.ui.units import layout_units
from advtext.units import px_from_sp, sp_from_px

if TYPE_CHECKING:
    from conftest import Window

BODY = (
    "--- a/f.py\n"
    "+++ b/f.py\n"
    "@@ -1,4 +1,4 @@\n"
    " keep\n"
    "-old\tline\n"
    "+new\tline\n"
    " \n"
    " tail\n"
)
"""
A diff with a tab in it and a blank context line: the two things a code block loses.
"""

ABOVE = "The paragraph above the diff, long enough to be a line of text.\n"
BELOW = "The paragraph below the diff, which is where a selection across it ends.\n"
SOURCE = f"{ABOVE}\n```diff\n{BODY}```\n\n{BELOW}"
WIDTH = sp_from_px(640.0)


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


@pytest.fixture(scope="module")
def measure() -> Any:
    return char_measure(fontlib_metrics)


def _doc(theme: Theme, source: str = SOURCE) -> Document:
    return build_document(source, theme, fontlib_metrics)


class Widget:
    """
    The least thing that can be hosted: a height, a text, and a count of what it was asked.
    """

    def __init__(self, height: float = 100.0, text: str = "WIDGET\n") -> None:
        self.height = height
        self.text = text
        self.drawn: list[tuple[float, float, float]] = []
        self.asked = 0

    def height_for(self, width_px: float) -> float:
        self.asked += 1
        return self.height

    def draw(self, *, fonts: Any, palette: Any = None, width_px: float | None = None) -> object:
        from imgui_bundle import imgui

        at = imgui.get_cursor_screen_pos()
        self.drawn.append((at.x, at.y, float(width_px or 0.0)))
        imgui.dummy(imgui.ImVec2(float(width_px or 0.0), self.height))
        return DrawStats(glyphs=7)


class Hook:
    """
    A `host_for` that hosts the blocks of chosen numbers and records every question.
    """

    def __init__(self, **widgets: Widget) -> None:
        self.widgets = {int(number[1:]): widget for number, widget in widgets.items()}
        self.asked: list[tuple[int, Block]] = []

    def __call__(self, view: BareView, number: int, block: Block) -> Widget | None:
        self.asked.append((number, block))
        return self.widgets.get(number)


def _bare(theme: Theme, measure: Any, host_for: Any, source: str = SOURCE) -> BareView:
    return BareView(document=_doc(theme, source), theme=theme, measure=measure, host_for=host_for)


# ----------------------------------------------------------------------
# 1. The layout
# ----------------------------------------------------------------------


def test_with_no_hook_nothing_is_asked_and_the_fence_is_a_code_block(
    theme: Theme, measure: Any
) -> None:
    """
    Opt-in: an existing view over an existing document is laid out as it was.
    """
    document = _doc(theme)
    view = BareView(document=document, theme=theme, measure=measure)
    layout = view.layout_for(WIDTH)
    assert tuple(unit.blocks[0] for unit in layout.placed) == document.blocks
    assert view.hosted(1) is None
    reference = layout_units(document.blocks, theme, WIDTH, measure)
    assert [(u.y, u.base, u.unit.cmds) for u in layout.placed] == [
        (u.y, u.base, u.unit.cmds) for u in reference.placed
    ]


def test_a_hosted_block_is_a_unit_of_its_widgets_height_with_nothing_in_it(
    theme: Theme, measure: Any
) -> None:
    widget = Widget(height=137.0)
    view = _bare(theme, measure, Hook(b1=widget))
    layout = view.layout_for(WIDTH)
    plain = BareView(document=view.document, theme=theme, measure=measure).layout_for(WIDTH)

    above, hosted, below = layout.placed
    assert isinstance(hosted.blocks[0], HostBlock) and hosted.blocks[0].host is widget
    assert hosted.height == sp_from_px(137.0)
    assert hosted.unit.cmds == () and hosted.unit.count == 0 and hosted.unit.lines == 0
    assert view.hosted(1) is widget and view.hosted(0) is None

    # The text either side is the text of the plain layout: same commands,
    # same gaps, and everything below moved by the difference in height.
    assert above.unit.cmds == plain.placed[0].unit.cmds and above.y == plain.placed[0].y == 0
    assert below.unit.cmds == plain.placed[2].unit.cmds
    assert hosted.y == plain.placed[1].y
    assert below.y - plain.placed[2].y == hosted.height - plain.placed[1].height
    assert below.base == hosted.base == above.unit.count
    # The document is the one the markdown made.
    assert isinstance(view.document.blocks[1], CodeBlock)
    assert not isinstance(view.document.blocks[1], HostBlock)


def test_the_hook_is_asked_once_per_block_object_and_a_stand_in_is_kept(
    theme: Theme, measure: Any
) -> None:
    widget = Widget()
    hook = Hook(b1=widget)
    view = _bare(theme, measure, hook)
    first = view.layout_for(WIDTH)
    assert [number for number, _ in hook.asked] == [0, 1, 2]
    view.invalidate()
    second = view.layout_for(WIDTH)
    view.layout_for(WIDTH // 2)
    assert len(hook.asked) == 3, "the same blocks were asked about again"
    assert second.placed[1].unit is first.placed[1].unit

    # A document parsed again is new objects: asked again, once each.
    view.document = _doc(theme)
    view.invalidate()
    view.layout_for(WIDTH)
    assert [number for number, _ in hook.asked[3:]] == [0, 1, 2]


def test_a_widget_that_changes_height_is_laid_out_again_and_only_it_is_shipped(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    widget = Widget(height=100.0)
    view = _bare(theme, measure, Hook(b1=widget))
    before = view.layout_for(WIDTH)
    shipped: list[tuple[Block, ...]] = []
    ship = advtext.ui.units.ship_unit

    def counted(composed: Any, measure: Any) -> Any:
        shipped.append(composed.blocks)
        return ship(composed, measure)

    monkeypatch.setattr(advtext.ui.units, "ship_unit", counted)
    assert not view._hosts_resized()
    widget.height = 160.0
    assert view._hosts_resized()
    view.invalidate()
    after = view.layout_for(WIDTH)
    assert len(shipped) == 1 and isinstance(shipped[0][0], HostBlock)
    assert after.placed[0] is before.placed[0]
    assert after.placed[1].height - before.placed[1].height == sp_from_px(60.0)
    assert after.placed[2].y - before.placed[2].y == sp_from_px(60.0)
    assert after.placed[2].unit is before.placed[2].unit


def test_any_block_can_be_hosted_not_only_a_fence(theme: Theme, measure: Any) -> None:
    """
    The hook is general: here a paragraph is replaced. Nothing in the view knows what a diff is.
    """
    widget = Widget(height=50.0, text="instead of the paragraph")
    view = _bare(theme, measure, Hook(b2=widget))
    layout = view.layout_for(WIDTH)
    assert isinstance(layout.placed[2].blocks[0], HostBlock)
    assert isinstance(view.document.blocks[2], TextBlock)
    assert layout.placed[2].height == sp_from_px(50.0)
    assert view.block_text(2) == "instead of the paragraph"


def _last_character(layout: Any, base: int) -> int:
    """
    The index of the last character before `base`.

    Not `base - 1`: a paragraph ends in fill (its `\\parfillskip`, a ragged
    line's `\\rightskip`), which takes indices and is nobody's character.
    """
    for index in range(base - 1, -1, -1):
        if layout.model.copy_text(Selection(index, base)):
            return index
    raise AssertionError("no character before the hosted block")


def test_a_selection_across_a_hosted_block_copies_its_text_in_place(
    theme: Theme, measure: Any
) -> None:
    """
    The decision, held: text, the widget's text on its own lines, text.
    """
    view = _bare(theme, measure, Hook(b1=Widget(text="line one\nline two\n")))
    layout = view.layout_for(WIDTH)
    base = layout.placed[1].base
    assert layout.model.copy_text(Selection(0, layout.length)) == (
        ABOVE.strip() + "\n\nline one\nline two\n\n" + BELOW.strip()
    )
    # One character either side is enough to be "across" -- a character,
    # not an index: from the paragraph's trailing fill there is no text
    # before the widget, and so nothing for it to be between.
    last = _last_character(layout, base)
    assert layout.model.copy_text(Selection(last, base + 1)) == ".\n\nline one\nline two\n\nT"
    assert last + 1 < base
    assert layout.model.copy_text(Selection(last + 1, base + 1)) == "T"


def test_a_selection_that_stops_at_either_edge_of_a_hosted_block_copies_none_of_it(
    theme: Theme, measure: Any
) -> None:
    view = _bare(theme, measure, Hook(b1=Widget(text="NEVER\n")))
    layout = view.layout_for(WIDTH)
    base = layout.placed[1].base
    assert layout.model.copy_text(Selection(0, base)) == ABOVE.strip()
    assert layout.model.copy_text(Selection(base, layout.length)) == BELOW.strip()
    last = _last_character(layout, base)
    assert layout.model.copy_text(Selection(last - 2, base)) == "xt."


def test_a_widget_with_no_text_copies_as_nothing_and_two_in_a_row_both_copy(
    theme: Theme, measure: Any
) -> None:
    source = "One.\n\n```diff\n-a\n```\n\n```diff\n-b\n```\n\n---\n\nTwo.\n"
    silent = _bare(theme, measure, Hook(b1=Widget(text=""), b2=Widget(text="")), source)
    layout = silent.layout_for(WIDTH)
    assert layout.model.copy_text(Selection(0, layout.length)) == "One.\n\nTwo."

    # Two widgets and then a rule, which has no item either: neither is lost.
    both = _bare(theme, measure, Hook(b1=Widget(text="first\n"), b2=Widget(text="second")), source)
    layout = both.layout_for(WIDTH)
    assert layout.model.copy_text(Selection(0, layout.length)) == (
        "One.\n\nfirst\n\nsecond\n\nTwo."
    )


def test_in_a_list_item_the_widgets_text_is_a_line_of_the_item_as_a_fence_is(
    theme: Theme, measure: Any
) -> None:
    source = "1. first item\n\n   ```diff\n   -x\n   +y\n   ```\n\n2. second item\n"
    plain = BareView(document=_doc(theme, source), theme=theme, measure=measure)
    expected = plain.layout_for(WIDTH).model.copy_text(Selection(0, 10_000))
    assert expected == "1. first item\n-x\n+y\n2. second item"
    view = _bare(theme, measure, Hook(b1=Widget(text="-x\n+y\n")), source)
    layout = view.layout_for(WIDTH)
    assert layout.model.copy_text(Selection(0, layout.length)) == expected


def test_the_selected_blocks_and_the_markdown_copy_name_the_fence(
    theme: Theme, measure: Any
) -> None:
    """
    Copy-as-markdown returns the fence verbatim when the selection runs across it.
    """
    view = _bare(theme, measure, DiffFences(source=SOURCE))
    layout = view.layout_for(WIDTH)
    base = layout.placed[1].base
    last = _last_character(layout, base)
    view.select(Selection(last - 3, base + 4))
    assert view.selected_blocks() == (0, 1, 2)
    assert view.selected_source(SOURCE) == SOURCE
    assert view.block_source(1, SOURCE) == f"```diff\n{BODY}```\n"
    assert view.selected_text() == "ext.\n\n" + BODY + "\nThe "

    view.select(Selection(base - 4, base))
    assert view.selected_blocks() == (0,)
    view.select(Selection(base, base + 4))
    assert view.selected_blocks() == (2,)


# ----------------------------------------------------------------------
# 2. Reading a fence
# ----------------------------------------------------------------------


def _fenced(theme: Theme, measure: Any, source: str, **options: Any) -> tuple[BareView, DiffFences]:
    fences = DiffFences(source=source, **options)
    view = _bare(theme, measure, fences, source)
    view.layout_for(WIDTH)
    return view, fences


def _hosted(view: BareView, number: int) -> HostedDiff:
    hosted = view.hosted(number)
    assert isinstance(hosted, HostedDiff)
    return hosted


def test_the_diff_is_read_from_the_source_tabs_and_blank_lines_intact(
    theme: Theme, measure: Any
) -> None:
    view, fences = _fenced(theme, measure, SOURCE)
    hosted = _hosted(view, 1)
    assert hosted.text == BODY and "\t" in hosted.text
    assert fences.fed_lines == BODY.count("\n") and fences.restarts == 0
    assert hosted.view.diff == Diff.from_unified(BODY)
    assert fences.view_of(view, 1) is hosted.view and fences.view_of(view, 0) is None
    (file,) = hosted.view.diff.files
    assert (file.added, file.removed) == (1, 1)
    assert [row.text for row in file.hunks[0].rows] == [
        "keep",
        "old\tline",
        "new\tline",
        "",
        "tail",
    ]
    # What the code block has instead, which is why it is not what is read.
    block = view.document.blocks[1]
    assert isinstance(block, CodeBlock)
    assert "\t" not in "".join(chr(n.codepoint) for line in block.lines for n in line)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("opening", "closing", "hosted"),
    [
        ("```diff", "```", True),
        ("```patch", "```", True),
        ("~~~diff", "~~~", True),
        ("````diff", "````", True),
        ("```diff a/f.py", "```", True),
        ("```DIFF", "```", True),
        ("```python", "```", False),
        ("```", "```", False),
        ("```differ", "```", False),
    ],
)
def test_which_fences_are_diffs(
    theme: Theme, measure: Any, opening: str, closing: str, hosted: bool
) -> None:
    source = f"Before.\n\n{opening}\n{BODY}{closing}\n\nAfter.\n"
    view, _ = _fenced(theme, measure, source)
    if not hosted:
        assert view.hosted(1) is None
        assert isinstance(view.layout_for(WIDTH).placed[1].blocks[0], CodeBlock)
        assert not isinstance(view.layout_for(WIDTH).placed[1].blocks[0], HostBlock)
        return
    assert _hosted(view, 1).text == BODY


def test_a_longer_fence_keeps_a_shorter_run_of_backticks_as_a_line(
    theme: Theme, measure: Any
) -> None:
    body = "@@ -1 +1 @@\n-```\n+~~~\n"
    view, _ = _fenced(theme, measure, f"````diff\n{body}````\n\nAfter.\n")
    assert _hosted(view, 0).text == body


def test_an_unclosed_fence_at_the_end_of_a_document_is_read_to_its_last_character(
    theme: Theme, measure: Any
) -> None:
    view, _ = _fenced(theme, measure, "```diff\n@@ -1 +1 @@\n-a\n+b")
    assert _hosted(view, 0).text == "@@ -1 +1 @@\n-a\n+b"
    (file,) = _hosted(view, 0).view.diff.files
    assert (file.added, file.removed) == (1, 1)


def test_an_indented_fence_loses_its_indentation_and_one_on_a_marker_line_falls_back(
    theme: Theme, measure: Any
) -> None:
    body = "@@ -1 +1 @@\n-\told\n+\tnew\n"
    indented = "1. item\n\n" + textwrap.indent(f"```diff\n{body}```\n", "   ") + "\n2. next\n"
    view, _ = _fenced(theme, measure, indented)
    assert _hosted(view, 1).text == body

    # The fence shares its first line with the list marker: read from the
    # code block, where a tab is spaces. Stated, not hidden.
    marked = "1. ```diff\n" + textwrap.indent(f"{body}```\n", "   ") + "\n2. next\n"
    view, fences = _fenced(theme, measure, marked)
    number = next(n for n, b in enumerate(view.document.blocks) if isinstance(b, CodeBlock))
    text = _hosted(view, number).text
    assert text.splitlines()[0] == "@@ -1 +1 @@" and "\t" not in text
    assert text.splitlines()[1].startswith("-") and text.splitlines()[1].endswith("old")
    (file,) = _hosted(view, number).view.diff.files
    assert (file.added, file.removed) == (1, 1)


def test_with_no_source_the_code_blocks_lines_are_read(theme: Theme, measure: Any) -> None:
    fences = DiffFences()
    view = _bare(theme, measure, fences)
    view.layout_for(WIDTH)
    text = _hosted(view, 1).text
    assert "\t" not in text and text.startswith("--- a/f.py\n+++ b/f.py\n@@ -1,4 +1,4 @@\n keep\n")
    (file,) = _hosted(view, 1).view.diff.files
    assert (file.added, file.removed) == (1, 1)
    # A callable is asked each time, for a host whose text is somewhere else.
    view, _ = _fenced(theme, measure, SOURCE)
    lazy = _bare(theme, measure, DiffFences(source=lambda: SOURCE))
    lazy.layout_for(WIDTH)
    assert _hosted(lazy, 1).text == _hosted(view, 1).text == BODY


def test_the_layout_of_every_embedded_diff_can_be_switched(theme: Theme, measure: Any) -> None:
    source = SOURCE + "\n```diff\n@@ -1 +1 @@\n-a\n+b\n```\n"
    view, fences = _fenced(theme, measure, source, height_cap=90.0)
    first, second = _hosted(view, 1).view, _hosted(view, 3).view
    assert first.layout is second.layout is DiffLayout.UNIFIED
    assert first.height_cap == 90.0
    fences.set_layout(DiffLayout.SIDE_BY_SIDE)
    assert first.layout is second.layout is DiffLayout.SIDE_BY_SIDE
    assert view._hosts_resized(), "side by side is fewer rows; the reserved height is stale"


# -- a stream ---------------------------------------------------------------


class Work:
    """
    Counts the calls that compose a run, ship a unit and read one line of a diff.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.composed = self.shipped = self.diff_lines = 0
        compose = advtext.ui.RunComposer.compose
        ship = advtext.ui.units.ship_unit
        line = UnifiedDiffStream._line

        def counted_compose(composer: Any, run: Any) -> Any:
            self.composed += 1
            return compose(composer, run)

        def counted_ship(composed: Any, measure: Any) -> Any:
            self.shipped += 1
            return ship(composed, measure)

        def counted_line(stream: Any, raw: str) -> None:
            self.diff_lines += 1
            line(stream, raw)

        monkeypatch.setattr(advtext.ui.RunComposer, "compose", counted_compose)
        monkeypatch.setattr(advtext.ui.units, "ship_unit", counted_ship)
        monkeypatch.setattr(UnifiedDiffStream, "_line", counted_line)

    def taken(self) -> tuple[int, int, int]:
        out = (self.composed, self.shipped, self.diff_lines)
        self.composed = self.shipped = self.diff_lines = 0
        return out


def _stream(
    theme: Theme, measure: Any, **options: Any
) -> tuple[StreamDocument, StreamView, DiffFences]:
    stream = StreamDocument(theme, fontlib_metrics)
    fences = DiffFences(**options)
    return stream, StreamView(stream, measure, host_for=fences), fences


def _diff_lines(count: int) -> list[str]:
    lines = ["--- a/big.py\n", "+++ b/big.py\n", f"@@ -1,{count} +1,{count} @@\n"]
    for number in range(count):
        lines.append(f"{' -+'[number % 3]}line number {number} of the diff\n")
    return lines


def test_a_live_diff_grows_a_line_at_a_time_and_the_text_above_does_not_move(
    theme: Theme, measure: Any
) -> None:
    stream, view, fences = _stream(theme, measure)
    stream.append(ABOVE + "\n```diff\n")
    view.sync()
    view.layout_for(WIDTH)
    settled = view.set_lines(0, 1)
    assert settled
    hosted = _hosted(view, 1)
    row = hosted.view.metrics_px.row
    heights = []
    for number, line in enumerate(_diff_lines(12)):
        stream.append(line)
        assert view.sync()
        layout = view.layout_for(WIDTH)
        assert view.hosted(1) is hosted, "the diff view was replaced under the reader"
        assert fences.fed_lines == number + 1
        assert view.set_lines(0, 1) == settled
        assert layout.placed[0] is not None and layout.placed[0].y == 0
        heights.append(px_from_sp(layout.placed[1].height))
    assert fences.restarts == 0
    grown = [round(b - a, 3) for a, b in zip(heights, heights[1:], strict=False)]
    # A row a line, after the three header lines have made the file and hunk rows.
    assert grown[3:] == [float(row)] * len(grown[3:])
    assert hosted.text == "".join(_diff_lines(12))


def test_a_line_is_a_diff_line_only_once_its_newline_has_arrived(
    theme: Theme, measure: Any
) -> None:
    """
    Which is also what keeps a half-typed closing fence from being drawn as a row.
    """
    stream, view, fences = _stream(theme, measure)
    stream.append("```diff\n@@ -1 +1 @@\n-a\n")
    view.sync()
    view.layout_for(WIDTH)
    hosted = _hosted(view, 0)
    for piece, lines in [("+", 2), ("b", 2), ("\n", 3), ("`", 3), ("``", 3), ("\n", 3)]:
        stream.append(piece)
        view.sync()
        view.layout_for(WIDTH)
        assert fences.fed_lines == lines, piece
    assert hosted.text == "@@ -1 +1 @@\n-a\n+b\n"
    stream.append("\nAfter the diff.\n")
    stream.close()
    view.sync()
    layout = view.layout_for(WIDTH)
    assert view.hosted(0) is hosted and fences.restarts == 0
    assert hosted.text == "@@ -1 +1 @@\n-a\n+b\n"
    # Everything is the diff and then the text (it pinned the text alone:
    # review 2's item 2, a leading diff left out of a copy of everything).
    assert layout.model.copy_text(Selection(0, layout.length), everything=True) == (
        "@@ -1 +1 @@\n-a\n+b\n\nAfter the diff."
    )
    # ... when everything is asked for; a range alone is the text (review 3, item 4).
    assert layout.model.copy_text(Selection(0, layout.length)) == "After the diff."
    assert layout.model.copy_text(Selection(1, layout.length)) == "fter the diff."


def test_a_stream_closed_inside_a_fence_reads_its_last_unfinished_line(
    theme: Theme, measure: Any
) -> None:
    stream, view, fences = _stream(theme, measure)
    stream.append("```diff\n@@ -1 +1 @@\n-a\n+b")
    view.sync()
    view.layout_for(WIDTH)
    assert fences.fed_lines == 2
    stream.close()
    view.sync()
    view.layout_for(WIDTH)
    assert _hosted(view, 0).text == "@@ -1 +1 @@\n-a\n+b"


@pytest.mark.parametrize("pieces", [1, 3, 7])
def test_however_the_stream_is_cut_the_diff_is_the_one_the_whole_document_gives(
    theme: Theme, measure: Any, pieces: int
) -> None:
    whole, _ = _fenced(theme, measure, SOURCE)
    stream, view, fences = _stream(theme, measure)
    for start in range(0, len(SOURCE), pieces):
        stream.append(SOURCE[start : start + pieces])
        view.sync()
        view.layout_for(WIDTH)
    stream.close()
    view.sync()
    layout = view.layout_for(WIDTH)
    assert _hosted(view, 1).text == _hosted(whole, 1).text == BODY
    assert _hosted(view, 1).view.diff == _hosted(whole, 1).view.diff
    assert fences.restarts == 0
    reference = whole.layout_for(WIDTH)
    assert [(u.y, u.height, u.base) for u in layout.placed] == [
        (u.y, u.height, u.base) for u in reference.placed
    ]


def test_the_cost_of_a_line_does_not_grow_with_the_diff(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Counted, not timed: what one more line costs after 50 lines and after 500.

    Per line: one diff line read, one row measured by the `DiffView`, one unit
    composed and shipped (the stand-in, which is one kern), and the hook asked
    about one block. Laid out as code the same fence is cut into pieces
    (`AF-codeunits`); here it is never a code block at all.
    """
    stream, view, fences = _stream(theme, measure)
    stream.append(ABOVE + "\n```diff\n")
    view.sync()
    view.layout_for(WIDTH)
    hosted = _hosted(view, 1)
    asked: list[int] = []
    inner = fences.__call__

    def counting(outer: BareView, number: int, block: Block) -> Any:
        asked.append(number)
        return inner(outer, number, block)

    view.host_for = counting
    lines = _diff_lines(520)
    work = Work(monkeypatch)
    costs: dict[int, tuple[tuple[int, int, int], int, int, int]] = {}
    for number, line in enumerate(lines):
        measured, fed = hosted.view.measured_rows, fences.fed_lines
        asked.clear()
        work.taken()
        stream.append(line)
        view.sync()
        view.layout_for(WIDTH)
        hosted.view.height_for(600.0)
        costs[number] = (
            work.taken(),
            hosted.view.measured_rows - measured,
            fences.fed_lines - fed,
            len(asked),
        )
    assert view.hosted(1) is hosted and fences.restarts == 0
    assert costs[50] == costs[500] == ((1, 1, 1), 1, 1, 1)
    assert {costs[number] for number in range(10, 520)} == {((1, 1, 1), 1, 1, 1)}
    assert len(view.layout_for(WIDTH).placed) == 2, "the fence was cut into pieces"


TRICKY = (
    "--- a/one.sql\n+++ b/one.sql\n"
    "@@ -1,3 +1,3 @@ section\n keep\n--- was a comment\n+++ is a comment\n last\n"
    "\\ No newline at end of file\n"
    "@@ -10,2 +10,3 @@\n a\n+b\n c\n+past the count\n"
    "@@ -0,0 +1,2 @@\n+new one\n+new two\n"
    "diff --git a/two b/two\n--- a/two\n+++ b/two\n@@\n-no ranges\n+at all\n unfinished"
)
"""
Every shape the stream's hunk counting has to survive: a section, removals that
look like headers, the no-newline marker, a hunk longer than its header says, an
empty old side, a hunk with no ranges, and a last line with no newline.
"""


@pytest.mark.parametrize("step", [1, 2, 5, 64])
def test_the_counts_a_streamed_hunk_is_handed_are_the_counts_of_its_rows(step: int) -> None:
    """
    `UnifiedDiffStream` now tells an open hunk its `old_count` and `new_count`
    rather than leaving them to be summed (that sum was the one cost of an
    appended line that grew with the diff). Held to a recount at every cut.
    """
    from advtext.diff import RowKind

    stream = UnifiedDiffStream()
    checked = 0
    for start in range(0, len(TRICKY), step):
        stream.feed(TRICKY[start : start + step])
        for file in stream.diff.files:
            for hunk in file.hunks:
                old = sum(1 for row in hunk.rows if row.kind in (RowKind.CONTEXT, RowKind.REMOVE))
                new = sum(1 for row in hunk.rows if row.kind in (RowKind.CONTEXT, RowKind.ADD))
                assert (hunk.old_count, hunk.new_count) == (old, new), (start, hunk.header)
                checked += 1
            assert len(file.gaps) in (0, len(file.hunks) + 1)
    stream.close()  # `from_unified` reads a complete text: its last line is a line (C-difffix)
    assert stream.diff == Diff.from_unified(TRICKY)
    assert checked >= 10


def test_a_capped_diff_stops_growing_and_then_nothing_is_shipped_for_a_line(
    theme: Theme, measure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream, view, fences = _stream(theme, measure, height_cap=100.0)
    stream.append(ABOVE + "\n```diff\n")
    for line in _diff_lines(30):
        stream.append(line)
    view.sync()
    layout = view.layout_for(WIDTH)
    assert layout.placed[1].height == sp_from_px(100.0)
    stand_in = layout.placed[1].blocks[0]
    work = Work(monkeypatch)
    stream.append(" one more line\n")
    view.sync()
    after = view.layout_for(WIDTH)
    assert work.taken() == (0, 0, 1)
    assert after.placed[1].blocks[0] is stand_in
    assert _hosted(view, 1).text.endswith(" one more line\n")


def test_the_text_after_a_live_diff_arrives_below_it_and_the_diff_commits_unmoved(
    theme: Theme, measure: Any
) -> None:
    stream, view, fences = _stream(theme, measure)
    stream.append(ABOVE + "\n```diff\n" + BODY)
    view.sync()
    live = view.layout_for(WIDTH)
    stream.append("```\n\n" + BELOW)
    stream.close()
    view.sync()
    done = view.layout_for(WIDTH)
    assert done.placed[1].unit is live.placed[1].unit
    assert (done.placed[1].y, done.placed[1].height) == (live.placed[1].y, live.placed[1].height)
    assert done.placed[2].y > done.placed[1].bottom
    assert done.model.copy_text(Selection(0, done.length)) == (
        ABOVE.strip() + "\n\n" + BODY + "\n" + BELOW.strip()
    )


# ----------------------------------------------------------------------
# 3. Frames
# ----------------------------------------------------------------------

SIZE = (900.0, 700.0)


@pytest.fixture
def imgui() -> Iterator[Any]:
    """
    ImGui with a context of this test's own, so no item, focus or clipboard is inherited.
    """
    module = pytest.importorskip("imgui_bundle").imgui
    before = module.get_current_context()
    context = module.create_context()
    module.set_current_context(context)
    try:
        yield module
    finally:
        module.destroy_context(context)
        if before is not None:
            module.set_current_context(before)


class Frames:
    """
    Frames of one window holding a scrolling child that holds the views.
    """

    def __init__(self, imgui: Any, *views: Any, height: float = SIZE[1]) -> None:
        self.imgui = imgui
        self.views = views
        self.height = height
        self.stats: list[Any] = []
        self.after = (0.0, 0.0)
        self.scroll: float | None = None
        self.vertices = 0

    def __call__(
        self,
        *,
        mouse: tuple[float, float] | None = None,
        left: bool | None = None,
        keys: tuple[Any, ...] = (),
        release: tuple[Any, ...] = (),
    ) -> None:
        imgui = self.imgui
        io = imgui.get_io()
        io.display_size = imgui.ImVec2(*SIZE)
        io.delta_time = 1.0 / 60.0
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
        if mouse is not None:
            io.add_mouse_pos_event(*mouse)
        if left is not None:
            io.add_mouse_button_event(0, left)
        for key in keys:
            io.add_key_event(key, True)
        for key in release:
            io.add_key_event(key, False)
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(SIZE[0], self.height))
            imgui.begin("##hostdiff", None, imgui.WindowFlags_.no_title_bar.value)
            imgui.begin_child("##pane", imgui.ImVec2(0.0, 0.0))
            if self.scroll is not None:
                imgui.set_scroll_y(self.scroll)
                self.scroll = None
            self.stats = [
                view.draw(fonts=lambda face: None, palette=DARK_PALETTE) for view in self.views
            ]
            at = imgui.get_cursor_screen_pos()
            self.after = (at.x, at.y)
            imgui.end_child()
            imgui.end()
        finally:
            imgui.render()
        self.vertices = int(imgui.get_draw_data().total_vtx_count)

    def copy(self) -> str:
        """
        Ctrl+C, two frames, and what is then on the clipboard.
        """
        imgui = self.imgui
        imgui.set_clipboard_text("")
        self(keys=(imgui.Key.mod_ctrl, imgui.Key.c))
        self(release=(imgui.Key.c, imgui.Key.mod_ctrl))
        return str(imgui.get_clipboard_text())


def _glyph_at(view: BareView, block: int, position: int = 2) -> tuple[float, float]:
    """
    The screen position of a point inside the `position`-th glyph of a block's first line.
    """
    origin = view.origin
    assert origin is not None
    line = view.set_lines(block, block + 1)[0]
    x = px_from_sp(line.glyphs[position][1]) + 2.0
    return origin[0] + x, origin[1] + px_from_sp(line.baseline) - 4.0


def _diff_point(inner: DiffView, row: int, column: int = 2) -> tuple[float, float]:
    """
    A point on `column` of the code of a display row of a unified diff.

    The gutter of a diff whose line numbers have up to two digits is nine
    cells: a pad, the old number, a pad, the new number, a pad, the marker,
    two more. The press test below holds that to the characters it selects.
    """
    origin, metrics = inner.origin, inner.metrics_px
    assert origin is not None
    return (
        origin[0] + (9 + column) * metrics.cell + 1.0,
        origin[1] + (row + 0.5) * metrics.row,
    )


def test_the_widget_is_drawn_in_the_rectangle_the_layout_reserved(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    widget = Widget(height=120.0)
    view = _bare(theme, measure, Hook(b1=widget))
    plain = BareView(document=view.document, theme=theme, measure=measure)
    frames = Frames(imgui, view)
    frames()
    frames()
    layout, origin = view.layout, view.origin
    assert layout is not None and origin is not None
    x, y, width = widget.drawn[-1]
    assert x == origin[0]
    assert y == pytest.approx(origin[1] + px_from_sp(layout.placed[1].y), abs=1e-3)
    assert width == pytest.approx(px_from_sp(layout.width))
    assert frames.stats[0].glyphs == 7 + sum(
        1 for unit in layout.placed for cmd in unit.unit.cmds if type(cmd).__name__ == "Glyph"
    )

    # What comes after the view is where it would be with nothing hosted:
    # the view's own height below its origin, in both cases.
    after_hosted = frames.after[1] - origin[1] - px_from_sp(layout.height)
    other = Frames(imgui, plain)
    other()
    assert plain.layout is not None and plain.origin is not None
    after_plain = other.after[1] - plain.origin[1] - px_from_sp(plain.layout.height)
    assert after_hosted == pytest.approx(after_plain, abs=1e-3)
    assert frames.after[0] == other.after[0]


def test_a_fence_in_a_list_item_is_drawn_at_the_items_text_and_one_at_the_top_at_the_margin(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    source = "1. first item\n\n   ```diff\n   -x\n   ```\n\nThen.\n\n```diff\n-y\n```\n"
    inner, outer = Widget(), Widget()
    view = _bare(theme, measure, Hook(b1=inner, b3=outer), source)
    Frames(imgui, view)()
    origin, layout = view.origin, view.layout
    assert origin is not None and layout is not None
    item = view.document.blocks[0]
    assert outer.drawn[-1][0] == origin[0]
    assert inner.drawn[-1][0] == pytest.approx(origin[0] + px_from_sp(item.left_indent), abs=1e-3)
    assert inner.drawn[-1][2] == pytest.approx(
        px_from_sp(layout.width - item.left_indent), abs=1e-3
    )


def test_a_widget_out_of_the_window_is_not_drawn(imgui: Any, theme: Theme, measure: Any) -> None:
    filler = "".join(f"Paragraph {number} of the filler.\n\n" for number in range(60))
    widget = Widget(height=80.0)
    view = _bare(theme, measure, Hook(b60=widget), filler + "```diff\n-x\n```\n\nEnd.\n")
    frames = Frames(imgui, view)
    frames()
    frames()
    assert widget.drawn == [], "drawn while below the fold"
    layout = view.layout
    assert layout is not None
    frames.scroll = px_from_sp(layout.placed[60].y) - 100.0
    frames()
    frames()
    assert len(widget.drawn) == 1
    frames.scroll = 0.0
    frames()
    frames()
    assert len(widget.drawn) == 2, "the frame that asked to scroll still shows the old place"


def test_a_widget_that_grew_is_given_its_room_on_the_frame_it_says_so(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    widget = Widget(height=60.0)
    view = _bare(theme, measure, Hook(b1=widget))
    frames = Frames(imgui, view)
    frames()
    first = view.layout
    assert first is not None
    frames()
    assert view.layout is first, "an idle frame rebuilt the layout"
    widget.height = 95.0
    frames()
    second = view.layout
    assert second is not None and second is not first
    assert second.placed[1].height == sp_from_px(95.0)
    assert second.placed[0] is first.placed[0]
    assert second.placed[2].y - first.placed[2].y == sp_from_px(35.0)


def test_the_embedded_diff_is_drawn_inside_the_document(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    view, fences = _fenced(theme, measure, SOURCE)
    plain = BareView(document=view.document, theme=theme, measure=measure)
    frames = Frames(imgui, view)
    frames()
    frames()
    inner = _hosted(view, 1).view
    layout, origin = view.layout, view.origin
    assert layout is not None and origin is not None and inner.origin is not None
    assert inner.origin[0] == origin[0]
    assert abs(inner.origin[1] - (origin[1] + px_from_sp(layout.placed[1].y))) <= 0.5
    assert inner.visible_rows == range(inner.row_count) and inner.row_count == 7
    assert px_from_sp(layout.placed[1].height) == pytest.approx(inner.height_for(600.0))
    # More glyphs than the text alone: the diff's rows were issued too.
    other = Frames(imgui, plain)
    other()
    text_only = sum(
        1
        for unit in (layout.placed[0], layout.placed[2])
        for cmd in unit.unit.cmds
        if type(cmd).__name__ == "Glyph"
    )
    assert frames.stats[0].glyphs > text_only + 40
    assert frames.stats[0].missing == 0


def test_a_press_on_the_embedded_diff_is_the_diffs_and_one_on_the_text_is_the_documents(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    Review 0's least-sure item ("by reading, both views begin a selection on
    one press"), settled in frames: they do not. Measured, and not for the
    reason first assumed -- with the outer view's `_over_host` test taken out
    this still passes, because the widget is drawn *before* the outer view
    judges the press, the `DiffView` submits its drag button on the frame of
    the press, and that button is then "an item in front" to the outer view.
    `_over_host` is for a widget that submits nothing, and the next test is
    the one that needs it.
    """
    view, _ = _fenced(theme, measure, SOURCE)
    inner = _hosted(view, 1).view
    frames = Frames(imgui, view)
    frames()
    frames()

    # From the `w` of "new\tline" on display row 4 to the `i` of "tail" on row 6.
    start, end = _diff_point(inner, 4, 2), _diff_point(inner, 6, 2)
    frames(mouse=start)
    frames(left=True)
    assert inner.owns_selection and not view.owns_selection
    assert view.selection.is_empty and not view._dragging
    frames(mouse=end)
    frames(left=False)
    assert inner.selection is not None and inner.selected_text()
    assert view.selection.is_empty
    copied = frames.copy()
    assert copied == inner.selected_text() == "w\tline\n\nta"

    # Now the text: the document takes the selection and the diff drops its own.
    above = _glyph_at(view, 0, 4)
    frames(mouse=above)
    frames(left=True)
    frames(mouse=(above[0] + 120.0, above[1]))
    frames(left=False)
    assert view.owns_selection and not inner.owns_selection
    assert not view.selection.is_empty and inner.selection is None
    assert frames.copy() == view.selected_text() != ""


def test_a_press_on_a_widget_that_submits_no_item_still_selects_nothing_in_the_document(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    The rule is the rectangle's, not the widget's: `Widget` claims its room with a dummy.
    """
    widget = Widget(height=120.0)
    view = _bare(theme, measure, Hook(b1=widget))
    frames = Frames(imgui, view)
    frames()
    x, y, width = widget.drawn[-1]
    inside = (x + width / 2, y + 60.0)
    frames(mouse=inside)
    frames(left=True)
    assert not view._dragging and view.selection.is_empty and not view.owns_selection
    frames(mouse=(inside[0] + 80.0, inside[1] + 20.0))
    frames(left=False)
    assert view.selection.is_empty

    # One pixel above the rectangle is the document's again.
    frames(mouse=(inside[0], y - 1.0))
    frames(left=True)
    assert view._dragging and view.owns_selection
    frames(left=False)


def test_a_drag_from_the_text_across_the_diff_selects_through_it_and_copies_its_body(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    view, _ = _fenced(theme, measure, SOURCE)
    inner = _hosted(view, 1).view
    frames = Frames(imgui, view)
    frames()
    frames()
    start, end = _glyph_at(view, 0, 10), _glyph_at(view, 2, 10)
    middle = _diff_point(inner, 3)
    frames(mouse=start)
    frames(left=True)
    frames(mouse=middle)
    # Over the diff, mid-drag: the drag is still the document's, and the
    # diff has begun nothing of its own.
    assert view._dragging and inner.selection is None and not inner.owns_selection
    frames(mouse=end)
    frames(left=False)
    assert view.owns_selection and inner.selection is None
    assert view.selected_blocks() == (0, 1, 2)
    text = view.selected_text()
    head, _, tail = text.partition(f"\n\n{BODY}\n")
    assert head and tail, "the diff's body is not between the two pieces of text"
    assert ABOVE.strip().endswith(head) and BELOW.startswith(tail)
    assert frames.copy() == text


def test_a_selection_across_a_widget_washes_its_rectangle_and_one_beside_it_does_not(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    Read off the vertex count: a filled rectangle is four vertices, and one more
    selected character is one more highlight.
    """
    view = _bare(theme, measure, Hook(b1=Widget()))
    frames = Frames(imgui, view)
    frames()
    layout = view.layout
    assert layout is not None
    base = layout.placed[1].base
    last = _last_character(layout, base)
    view.select(Selection(last, base))
    frames()
    beside = frames.vertices
    view.select(Selection(last, base + 1))
    frames()
    across = frames.vertices
    assert across - beside == 8, "one highlight for the new character, one wash for the widget"
    view.select(Selection(base, base + 1))
    frames()
    assert frames.vertices == beside, "a selection that begins below the widget washed it"


def test_the_block_under_the_mouse_over_an_embedded_diff_is_the_fence(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    view, _ = _fenced(theme, measure, SOURCE)
    frames = Frames(imgui, view)
    frames()
    frames()
    x, y = _diff_point(_hosted(view, 1).view, 3)
    frames(mouse=(x, y))
    frames()
    pointed = view.pointed(x, y)
    assert pointed.block == 1 and not pointed.selected
    assert view.block_at(x, y) == 1
    where = view.source_of(1)
    assert where is not None and where.span.of(SOURCE) == f"```diff\n{BODY}```\n"
    assert view.block_text(1) == BODY.removesuffix("\n")


def test_a_capped_diff_scrolls_in_its_own_child_and_still_takes_its_own_press(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    body = "".join(_diff_lines(40))
    source = f"{ABOVE}\n```diff\n{body}```\n\n{BELOW}"
    view, _ = _fenced(theme, measure, source, height_cap=120.0)
    inner = _hosted(view, 1).view
    frames = Frames(imgui, view)
    frames()
    frames()
    layout = view.layout
    assert layout is not None
    assert layout.placed[1].height == sp_from_px(120.0)
    assert len(inner.visible_rows) < inner.row_count
    point = _diff_point(inner, 3)
    frames(mouse=point)
    frames(left=True)
    frames(mouse=(point[0] + 60.0, point[1]))
    frames(left=False)
    assert inner.owns_selection and inner.selection is not None
    assert view.selection.is_empty


def test_a_stream_view_draws_a_diff_as_it_arrives(imgui: Any, theme: Theme, measure: Any) -> None:
    stream, view, fences = _stream(theme, measure)
    frames = Frames(imgui, view)
    stream.append(ABOVE + "\n```diff\n")
    frames()
    hosted = _hosted(view, 1)
    origin = view.origin
    settled = view.set_lines(0, 1)
    rows = []
    for line in _diff_lines(9):
        stream.append(line)
        frames()
        rows.append(hosted.view.row_count)
        assert view.set_lines(0, 1) == settled and view.origin == origin
    assert rows == sorted(rows) and rows[-1] - rows[2] == 9
    # One layout for the frame the fence opened on and one for each line.
    assert view.relayouts == 1 + len(_diff_lines(9))
    frames()
    assert view.relayouts == 1 + len(_diff_lines(9)), "an idle frame laid out again"
    assert frames.stats[0].glyphs > 9 * 20 and frames.stats[0].missing == 0


# ----------------------------------------------------------------------
# 4. A real window
# ----------------------------------------------------------------------

WINDOWED = """
from imgui_bundle import hello_imgui, imgui, immapp

from advtext.backends.imgui_draw import DARK_PALETTE
from advtext.stream import StreamDocument
from advtext.style import Theme, char_measure, fontlib_metrics
from advtext.ui.diff_view import DiffFences
from advtext.ui.fonts import load_faces
from advtext.ui.stream_view import StreamView

ABOVE = "The paragraph above the diff, long enough to be a line of text.\\n\\n"
LINES = ["```diff\\n", "--- a/f.py\\n", "+++ b/f.py\\n", "@@ -1,30 +1,30 @@\\n"]
LINES += [" -+"[n % 3] + f"line number {n} of the diff\\n" for n in range(40)]
LINES += ["```\\n", "\\n", "The paragraph below the diff.\\n"]

theme = Theme.build()
stream = StreamDocument(theme, fontlib_metrics)
fences = DiffFences()
view = StreamView(stream, char_measure(fontlib_metrics), host_for=fences)
loaded = []
state = {"frames": 0, "glyphs": 0, "missing": 0, "moved": 0, "settled": None}
stream.append(ABOVE)


def gui():
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    frame = state["frames"]
    if frame >= 3 and frame - 3 < len(LINES):
        stream.append(LINES[frame - 3])
    if frame - 3 == len(LINES):
        stream.close()
    imgui.begin_child("##pane", imgui.ImVec2(0.0, 0.0))
    stats = view.draw(fonts=loaded[0], palette=DARK_PALETTE)
    imgui.end_child()
    state["glyphs"] = max(state["glyphs"], stats.glyphs)
    state["missing"] += stats.missing
    lines = view.set_lines(0, 1)
    if state["settled"] is None:
        state["settled"] = lines
    elif lines != state["settled"]:
        state["moved"] += 1
    state["frames"] += 1
    if frame - 3 == len(LINES) + 3:
        inner = fences.view_of(view, 1)
        layout = view.layout
        print(
            f"frames={state['frames']} relayouts={view.relayouts} fed={fences.fed_lines} "
            f"restarts={fences.restarts} rows={inner.row_count} units={len(layout.placed)} "
            f"blocks={len(view.document.blocks)} glyphs={state['glyphs']} "
            f"missing={state['missing']} moved={state['moved']} "
            f"diff_height={inner.height_for(600.0):.0f} "
            f"added={inner.diff.added} removed={inner.diff.removed}"
        )
        hello_imgui.get_runner_params().app_shall_exit = True


params = hello_imgui.RunnerParams()
params.app_window_params.window_geometry.size = (900, 700)
params.callbacks.show_gui = gui
params.callbacks.load_additional_fonts = lambda: loaded.append(load_faces())
immapp.run(params)
"""


def test_a_diff_streams_into_a_document_in_a_real_window(window: Window) -> None:
    """
    A paragraph, a fenced diff of 43 lines fed one line a frame, a paragraph.

    Counts: every line read once and none twice, one row a line plus the two
    header rows, three blocks in three units (the fence never cut into
    pieces), the paragraph above set identically on every frame, glyphs
    drawn with none missing.
    """
    script = window.out / "hostdiff_stream.py"
    script.write_text(textwrap.dedent(WINDOWED), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    (line,) = [line for line in done.stdout.splitlines() if line.startswith("frames=")]
    got = dict(part.split("=", 1) for part in line.split())
    assert got["fed"] == "43" and got["restarts"] == "0", line
    assert got["rows"] == "42", line  # a file row, a hunk row, forty lines
    assert got["blocks"] == got["units"] == "3", line
    assert got["moved"] == "0" and got["missing"] == "0", line
    assert int(got["glyphs"]) > 300, line
    assert (got["added"], got["removed"]) == ("13", "13"), line
    assert int(got["relayouts"]) <= int(got["frames"]), line


# ----------------------------------------------------------------------
# 7. Review 2 (C-hostfix): hosted blocks at the edges of a document
# ----------------------------------------------------------------------

FENCE = "```diff\n@@ -1 +1 @@\n-old\n+new\n```\n"
FENCE_BODY = "@@ -1 +1 @@\n-old\n+new"
OTHER = "```diff\n@@ -2 +2 @@\n-was\n+is\n```\n"
OTHER_BODY = "@@ -2 +2 @@\n-was\n+is"

SHAPES = {
    "between": ("Above.\n\n" + FENCE + "\nBelow.\n", f"Above.\n\n{FENCE_BODY}\n\nBelow."),
    "last": ("Here is the patch:\n\n" + FENCE, f"Here is the patch:\n\n{FENCE_BODY}"),
    "first": (FENCE + "\nThat was it.\n", f"{FENCE_BODY}\n\nThat was it."),
    "only": (FENCE, FENCE_BODY),
    "two adjacent, last": (
        "See:\n\n" + FENCE + "\n" + OTHER,
        f"See:\n\n{FENCE_BODY}\n\n{OTHER_BODY}",
    ),
    "two adjacent, first": (
        FENCE + "\n" + OTHER + "\nDone.\n",
        f"{FENCE_BODY}\n\n{OTHER_BODY}\n\nDone.",
    ),
    "two, only": (FENCE + "\n" + OTHER, f"{FENCE_BODY}\n\n{OTHER_BODY}"),
    "first and last": (
        FENCE + "\nBetween.\n\n" + OTHER,
        f"{FENCE_BODY}\n\nBetween.\n\n{OTHER_BODY}",
    ),
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_select_all_copies_a_hosted_block_wherever_it_sits(
    theme: Theme, measure: Any, shape: str
) -> None:
    """
    A reply that ends in a diff fence is the common shape, and a copy of
    everything left the diff out: a hosted block holds no index, its text
    was written into the separator *after* it, and a separator is written
    only between two pieces of selected text.
    """
    source, expected = SHAPES[shape]
    view = _bare(theme, measure, DiffFences(source=source), source)
    layout = view.layout_for(WIDTH)
    assert layout.model.copy_text(layout.model.select(0, 10**9), everything=True) == expected
    view.select_all()
    assert view.selected_text() == expected
    # Copy and copy-as-markdown agree on what "everything" holds.
    assert view.selected_blocks() == tuple(range(len(view.document.blocks)))
    assert view.selected_source(source) == source
    # As plain code blocks (no hook) the same documents copy the same text.
    plain = BareView(document=_doc(theme, source), theme=theme, measure=measure)
    plain.layout_for(WIDTH)
    plain.select_all()
    assert plain.selected_text() == expected


def test_a_selection_short_of_everything_copies_no_hosted_block_at_an_edge(
    theme: Theme, measure: Any
) -> None:
    """
    The other half of the rule. A hosted block has no index of its own, so
    the boundary after a document's last character is also the boundary
    after the diff under it: only a selection of *everything* takes the
    diff with it, and one that merely reaches the last character does not.
    """
    source, _ = SHAPES["first and last"]
    view = _bare(theme, measure, DiffFences(source=source), source)
    layout = view.layout_for(WIDTH)
    assert layout.length > 4
    assert layout.model.copy_text(Selection(1, layout.length)) == "etween."
    assert layout.model.copy_text(Selection(0, layout.length - 1)).startswith("Between")
    assert "+new" not in layout.model.copy_text(Selection(0, layout.length - 1))
    view.select(Selection(1, layout.length))
    assert view.selected_blocks() == (1,)
    # With nothing selected nothing is copied, in a document that is only a diff too.
    only = _bare(theme, measure, DiffFences(source=FENCE), FENCE)
    only.layout_for(WIDTH)
    assert only.selected_text() == "" and only.selected_blocks() == ()
    only.select_all()
    assert only.selected_text() == FENCE_BODY
    only.clear_selection()
    assert only.selected_text() == ""


def test_a_hosted_block_last_in_a_list_item_or_a_quote_is_copied_with_everything(
    theme: Theme, measure: Any
) -> None:
    for source in (
        "1. first item\n\n   ```diff\n   -x\n   +y\n   ```\n",
        "> quoted\n>\n> ```diff\n> -x\n> +y\n> ```\n",
        "- ```diff\n  -x\n  +y\n  ```\n",
    ):
        plain = BareView(document=_doc(theme, source), theme=theme, measure=measure)
        plain.layout_for(WIDTH)
        plain.select_all()
        expected = plain.selected_text()
        assert "-x" in expected and "+y" in expected
        view = _bare(theme, measure, DiffFences(source=source), source)
        view.layout_for(WIDTH)
        view.select_all()
        assert view.selected_text() == expected, source


def test_a_whole_selection_washes_a_widget_at_the_edge_and_ctrl_c_copies_it(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    source = "The text before it.\n\n```diff\n-x\n```\n"
    view = _bare(theme, measure, Hook(b1=Widget(text="TRAILING\n")), source)
    frames = Frames(imgui, view)
    frames()
    layout = view.layout
    assert layout is not None
    view.select(Selection(1, layout.length))  # to the last character: not everything
    frames()
    short = frames.vertices
    assert frames.copy() == "he text before it."
    view.select_all()
    frames()
    # (The first character joins a highlight that was already there: the
    # four vertices are the widget's wash.)
    assert frames.vertices - short == 4, "the widget at the edge was not washed"
    assert frames.copy() == "The text before it.\n\nTRAILING"
    # A document that is only a widget: all of it is the empty range, and still copies.
    only = _bare(theme, measure, Hook(b0=Widget(text="ALONE\n")), "```diff\n-x\n```\n")
    alone = Frames(imgui, only)
    alone()
    assert alone.copy() == ""  # nothing selected: the clipboard is not written
    only.select_all()
    alone()
    assert alone.copy() == "ALONE"


def _page_view(theme: Theme, measure: Any, host_for: Any, source: str = SOURCE) -> Any:
    from advtext.ui.document_view import DocumentView

    return DocumentView(
        document=_doc(theme, source), theme=theme, measure=measure, host_for=host_for
    )


def test_a_document_view_draws_what_it_hosts(imgui: Any, theme: Theme, measure: Any) -> None:
    """
    Review 2, item 6: given `host_for` it reserved the rectangle and drew
    nothing in it -- its `draw` is its own and never reached `_draw_hosts`.
    """
    widget = Widget(height=120.0)
    view = _page_view(theme, measure, Hook(b1=widget))
    frames = Frames(imgui, view)
    frames()
    frames()
    layout, origin = view.layout, view.origin
    assert layout is not None and origin is not None
    assert len(widget.drawn) == 2, "the widget was not drawn"
    x, y, width = widget.drawn[-1]
    assert x == pytest.approx(origin[0], abs=1e-3)
    assert y == pytest.approx(origin[1] + px_from_sp(layout.placed[1].y), abs=1e-3)
    assert width == pytest.approx(px_from_sp(layout.width), abs=1e-3)
    # The view still claims its sheet and nothing more: what follows it is
    # where it is with nothing hosted and a code block of the same height.
    assert frames.stats[0].glyphs >= 7
    # A widget that changes height is given its room, as in a bare view.
    before = layout.placed[2].y
    widget.height = 200.0
    frames()
    assert view.layout is not None and view.layout.placed[2].y - before == sp_from_px(80.0)


def test_in_a_document_view_a_press_on_a_widget_is_not_a_selection_of_the_document(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    widget = Widget(height=120.0)
    view = _page_view(theme, measure, Hook(b1=widget))
    frames = Frames(imgui, view)
    frames()
    frames()
    x, y, _ = widget.drawn[-1]
    inside = (x + 30.0, y + 60.0)
    frames(mouse=inside)
    frames(mouse=inside, left=True)
    frames(mouse=(inside[0] + 40.0, inside[1] + 10.0))
    frames(left=False)
    assert view.selection.is_empty and not view._dragging
    # ... and one on the text still is.
    start = _glyph_at(view, 0, 2)
    frames(mouse=start)
    frames(mouse=start, left=True)
    frames(mouse=(start[0] + 60.0, start[1]))
    frames(left=False)
    assert not view.selection.is_empty


def test_an_embedded_diff_in_a_document_view_is_drawn_and_takes_its_own_press(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    fences = DiffFences(source=SOURCE)
    view = _page_view(theme, measure, fences)
    frames = Frames(imgui, view)
    frames()
    frames()
    inner = fences.view_of(view, 1)
    assert inner is not None and inner.origin is not None and len(inner.visible_rows) > 2
    row = next(r for r in range(inner.row_count) if inner.row_info(r).kind == "row")
    start, end = _diff_point(inner, row, 0), _diff_point(inner, row, 6)
    frames(mouse=start)
    frames(mouse=start, left=True)
    frames(mouse=end)
    frames(left=False)
    frames(mouse=(SIZE[0] - 3.0, 3.0))
    assert view.selection.is_empty, "the page began a selection under the diff"
    assert inner.selection is not None and inner.owns_selection
    info = inner.row_info(row)
    line = inner.diff.files[info.file].hunks[info.hunk or 0].rows[info.left or 0].text
    assert inner.selected_text() == line[:6] != ""


def test_the_owner_of_the_selection_answers_ctrl_c_when_it_has_scrolled_out_of_view(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    Review 2, item 7: a culled widget is not drawn, and a `DiffView` handles
    its keys in `draw`. The diff still owns the selection -- nothing else
    took it -- so Ctrl+C did nothing at all.
    """
    filler = "".join(f"Paragraph {number} of the filler.\n\n" for number in range(60))
    source = "```diff\n@@ -1 +1 @@\n-old line\n+new line\n```\n\n" + filler
    fences = DiffFences(source=source)
    view = _bare(theme, measure, fences, source)
    frames = Frames(imgui, view)
    frames()
    frames()
    inner = fences.view_of(view, 0)
    assert inner is not None
    inner.select((0, 0, 1, 0), (0, 0, 1, 8))
    assert inner.selected_text() == "new line" and inner.owns_selection
    frames()
    assert frames.copy() == "new line"  # on screen: it always did
    layout = view.layout
    assert layout is not None
    frames.scroll = px_from_sp(layout.placed[30].y)
    frames()
    frames()
    drawn = inner._drawn_frame
    frames()
    assert (
        inner._drawn_frame == drawn
    ), "the diff is still being drawn: the test is not of a culled one"
    assert inner.owns_selection
    assert frames.copy() == "new line"
    # With a text input active the key is the input's, on screen or off.
    # And once the document's own text is selected, the diff no longer answers.
    view.select(Selection(0, 5))
    frames()
    assert frames.copy() == view.selected_text() != "new line"


def test_text_in_view_does_not_move_when_a_hosted_block_above_the_window_grows(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    Unchecked by anyone until review 2 asked. A widget above the viewport
    that changes height moves everything under it in the document; whether
    what the reader is looking at moves on screen is the question.
    """
    filler = "".join(f"Paragraph {number} of the filler.\n\n" for number in range(60))
    widget = Widget(height=80.0)
    source = "Top.\n\n```diff\n-x\n```\n\n" + filler
    view = _bare(theme, measure, Hook(b1=widget), source)
    frames = Frames(imgui, view)
    frames()
    layout = view.layout
    assert layout is not None
    frames.scroll = px_from_sp(layout.placed[30].y)
    frames()
    frames()
    assert widget.drawn and view.origin is not None
    seen = len(widget.drawn)

    def on_screen(block: int) -> float:
        assert view.layout is not None and view.origin is not None
        return view.origin[1] + px_from_sp(view.layout.placed[block].y)

    before = on_screen(40)
    assert 0.0 < before < frames.height
    widget.height = 230.0
    for _ in range(4):
        frames()
    assert (
        len(widget.drawn) == seen
    ), "the widget came on screen: the test is not of one above the window"
    assert on_screen(40) == pytest.approx(before, abs=1.0)


# ----------------------------------------------------------------------
# 8. Review 2's read-derived minors on reading a fence
# ----------------------------------------------------------------------


def test_a_fence_line_is_cut_at_a_newline_and_nowhere_else(theme: Theme, measure: Any) -> None:
    """`str.splitlines` also cuts at a form feed and at U+2028; `advtext.diff` does not."""
    body = "@@ -1 +1 @@\n-a\x0cb\n+a b\x1cc\n"
    source = f"Above.\n\n```diff\n{body}```\n\nBelow.\n"
    view, fences = _fenced(theme, measure, source)
    hosted = _hosted(view, 1)
    assert hosted.text == body and fences.fed_lines == 3
    assert [row.text for _, _, row in hosted.view.diff.rows()] == ["a\x0cb", "a b\x1cc"]


def test_only_the_last_line_of_a_fence_can_close_it(theme: Theme, measure: Any) -> None:
    """
    An opener indented two spaces let a run of backticks indented five close
    the fence here, where markdown stops at three: the lines after it, still
    inside the code block as markdown read it, were dropped from the diff.
    The parser has already said where the block ends, so that is what is
    asked: a closing line is the last line of the block's source.
    """
    source = "Above.\n\n  ```diff\n  @@ -1,2 +1,2 @@\n  -a\n     ```\n  +b\n  ```\n\nBelow.\n"
    document = _doc(theme, source)
    assert [type(block).__name__ for block in document.blocks] == [
        "TextBlock",
        "CodeBlock",
        "TextBlock",
    ]
    view, _ = _fenced(theme, measure, source)
    hosted = _hosted(view, 1)
    assert hosted.text == "@@ -1,2 +1,2 @@\n-a\n   ```\n+b\n"
    assert [row.text for _, _, row in hosted.view.diff.rows()] == ["a", "  ```", "b"]
    # Streamed a character at a time it is the same diff, and the candidate
    # closing line is never shown as a row while it is the last one read.
    stream, live, fences = _stream(theme, measure)
    for character in source:
        stream.append(character)
        live.sync()
        live.layout_for(WIDTH)
        shown = live.hosted(1)
        if shown is not None and stream.source.endswith("     ```\n"):
            # The last line read looks like a closing fence: not a row yet.
            assert [row.text for _, _, row in shown.view.diff.rows()] == ["a"]
    stream.close()
    live.sync()
    live.layout_for(WIDTH)
    assert _hosted(live, 1).text == hosted.text and fences.restarts == 0


def test_a_view_that_is_gone_leaves_nothing_behind_in_the_fences(
    theme: Theme, measure: Any
) -> None:
    import gc

    fences = DiffFences(source=SOURCE)
    views = [_bare(theme, measure, fences) for _ in range(5)]
    for view in views:
        view.layout_for(WIDTH)
    assert all(fences.view_of(view, 1) is not None for view in views)
    assert len({id(fences.view_of(view, 1)) for view in views}) == 5
    assert fences.live == 5
    fences.set_layout(DiffLayout.SIDE_BY_SIDE)
    assert all(fences.view_of(view, 1).layout is DiffLayout.SIDE_BY_SIDE for view in views)  # type: ignore[union-attr]
    kept = views[0]
    del views, view
    gc.collect()
    assert fences.live == 1 and fences.view_of(kept, 1) is not None
    assert fences.view_of(kept, 0) is None


# ---------------------------------------------------------------------------
# Review 3, item 4: an edge block is taken by the select-all gesture only
# ---------------------------------------------------------------------------
#
# C-hostfix inferred "everything" from the range: a selection from the first
# boundary to the last took the hosted blocks at the document's edges with
# it. Both ways that is wrong. A reply of one sentence and a diff: selecting
# the sentence IS first-to-last, and copied the diff. A longer reply dragged
# from its second letter to its end is not, and select-all made while the
# reply was still arriving stopped being "everything" the moment it grew.

SENTENCE = "Here is the patch:"


def test_review3_item_4_a_range_never_takes_an_edge_block_however_far_it_reaches(
    theme: Theme, measure: Any
) -> None:
    source = SENTENCE + "\n\n" + FENCE
    view = _bare(theme, measure, DiffFences(source=source), source)
    layout = view.layout_for(WIDTH)
    whole = layout.model.select(0, layout.model.length)
    assert layout.model.covers_everything(whole)  # first boundary to last, and still:
    assert layout.model.copy_text(whole) == SENTENCE
    view.select(whole)
    assert view.selected_text() == SENTENCE
    assert view.selected_blocks() == (0,)
    assert view.selected_source(source).strip() == SENTENCE
    # The gesture is what takes it,
    view.select_all()
    assert view.selected_text() == f"{SENTENCE}\n\n{FENCE_BODY}"
    assert view.selected_blocks() == (0, 1)
    # ... and a selection made afterwards is a selection again.
    view.select(whole)
    assert view.selected_text() == SENTENCE
    # A longer reply, from its second letter to its end: the same answer.
    longer = "Intro.\n\n" + source
    other = _bare(theme, measure, DiffFences(source=longer), longer)
    layout = other.layout_for(WIDTH)
    other.select(layout.model.select(1, layout.model.length))
    assert other.selected_text() == f"ntro.\n\n{SENTENCE}"
    assert layout.model.copy_text(whole, everything=True).endswith(FENCE_BODY)


def test_review3_item_4_a_drag_over_all_the_text_copies_no_diff_and_ctrl_a_copies_it(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    source = SENTENCE + "\n\n" + FENCE
    view = _bare(theme, measure, DiffFences(source=source), source)
    frames = Frames(imgui, view)
    frames()
    frames()
    start = _glyph_at(view, 0, 0)
    frames(mouse=(start[0] - 2.0, start[1]))
    frames(left=True)
    frames(mouse=(SIZE[0] - 40.0, start[1]))  # along the line, past its last letter
    frames(left=False)
    layout = view.layout
    assert layout is not None and view.owns_selection
    assert view.selection.start == 0 and view.selected_text() == SENTENCE  # all of the text
    short = frames.vertices
    assert frames.copy() == SENTENCE
    assert view.selected_blocks() == (0,)
    # Ctrl+A, with this view the owner of the selection: everything, the diff included.
    frames(keys=(imgui.Key.mod_ctrl, imgui.Key.a))
    frames(release=(imgui.Key.a, imgui.Key.mod_ctrl))
    assert view.selected_blocks() == (0, 1)
    assert frames.vertices > short, "the diff at the edge was not washed"
    assert frames.copy() == f"{SENTENCE}\n\n{FENCE_BODY}"
    # A press afterwards is a new selection (here a word: it comes soon
    # enough after the last press to be a double click), and not everything.
    frames(mouse=start)
    frames(left=True)
    frames(left=False)
    assert 1 not in view.selected_blocks() and "+new" not in frames.copy()


def test_review3_item_4_select_all_stays_select_all_while_a_stream_grows(
    theme: Theme, measure: Any
) -> None:
    stream, view, _ = _stream(theme, measure)
    stream.append("Here is ")
    view.sync()
    view.layout_for(WIDTH)
    view.select_all()
    assert view.selected_text() == "Here is"
    pieces = ["the patch:\n\n", "```diff\n", "@@ -1 +1 @@\n", "-old\n", "+new\n", "```\n"]
    expected = [
        "Here is the patch:",
        "Here is the patch:",
        "Here is the patch:\n\n@@ -1 +1 @@\n",
        "Here is the patch:\n\n@@ -1 +1 @@\n-old\n",
        "Here is the patch:\n\n@@ -1 +1 @@\n-old\n+new\n",
        "Here is the patch:\n\n@@ -1 +1 @@\n-old\n+new\n",
    ]
    for piece, wanted in zip(pieces, expected, strict=True):
        stream.append(piece)
        view.sync()
        view.layout_for(WIDTH)
        assert view.selected_text() == wanted.rstrip("\n"), piece
    stream.append("\nAnd a line after it.\n")
    stream.close()
    view.sync()
    layout = view.layout_for(WIDTH)
    assert view.selected_text() == f"{SENTENCE}\n\n{FENCE_BODY}\n\nAnd a line after it."
    assert (view.selection.start, view.selection.end) == (0, layout.length)
    assert view.selected_blocks() == (0, 1, 2)
    # A selection made by range while it grows is carried as that text, and no more.
    stream2, view2, _ = _stream(theme, measure)
    stream2.append("Here is the patch:\n\n```diff\n@@ -1 +1 @@\n")
    view2.sync()
    layout = view2.layout_for(WIDTH)
    view2.select(Selection(0, layout.length))
    stream2.append("-old\n+new\n```\n")
    view2.sync()
    view2.layout_for(WIDTH)
    assert view2.selected_text() == SENTENCE


def test_review3_item_9_a_nul_in_what_a_document_copies_does_not_cut_the_clipboard_short(
    imgui: Any, theme: Theme, measure: Any
) -> None:
    """
    Markdown has no NUL (the parser replaces it), but what a hosted block
    copies as is its widget's text, and a diff fence's body is the source as
    written. Ctrl+C and `copy()` hand the clipboard U+2400 for it;
    `selected_text` is the text.
    """
    from advtext.ui.bare_view import CLIPBOARD_NUL

    source = "Before.\n\n```diff\n-x\n```\n\nAfter.\n"
    view = _bare(theme, measure, Hook(b1=Widget(text="key = 'ab\0cd'\nnext\n")), source)
    frames = Frames(imgui, view)
    frames()
    view.select_all()
    frames()
    assert view.selected_text() == "Before.\n\nkey = 'ab\0cd'\nnext\n\nAfter."
    wanted = f"Before.\n\nkey = 'ab{CLIPBOARD_NUL}cd'\nnext\n\nAfter."
    assert frames.copy() == wanted
    imgui.set_clipboard_text("")
    view.copy()
    assert imgui.get_clipboard_text() == wanted
    view.copy("a\0b")
    assert imgui.get_clipboard_text() == f"a{CLIPBOARD_NUL}b"

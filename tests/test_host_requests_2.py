r"""
What pptmstr, the first host, asked next (its P26 to P29), each reproduced first.

- **P26** a paragraph after a list sits at the list's ITEM gap. It is how the
  theme describes a list item (`space_below`), the library adding the upper
  block's space below to the lower one's space above; the old core set the
  same. `Theme.space_after_list` is the option; `None` is as ever.
- **P27** a fence's info string is drawn nowhere.
  `ReaderOptions.show_fence_info` sets it as a text block before the code.
- **P28** a `MarkdownText` a host made with `a   b    c` is drawn and copied
  as `a b c` while `texts` showed every space. The library sets white space
  one way and has no flag that keeps it (the typesetting core's to offer);
  the view now records the text as it is set
  (`advtext.typeset_markdown.text_as_set`).
- **P29** a tab in a fenced block was expanded to spaces before the library
  saw it, so a copy had spaces. The library's stops are the ones the spaces
  went to, measured here, so the tab is handed through.

Two parts. The first needs no library: what is read and described. The
second is a child with the library and real ImGui frames (no window): where
blocks and characters are put, and what a copy gives. It says whether
`typesetter.module()` and `ready()` held in the child at its start and at
its end, and the fixture fails when they did not.

The measurements behind each were made first with
`.concerns/N-HOST2-scripts/` (`p26_gaps.py`, `p28_spaces.py`,
`p28_details.py`, `p29_tabs.py`, `p29_sanity.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import material_frozen
import pytest

from advtext import typesetter
from advtext.description import KIND_CODE, KIND_LIST_ITEM, KIND_PARAGRAPH, RUN_FORMULA
from advtext.markdown_rules import TAB_WIDTH
from advtext.theme import BlockKind, Theme
from advtext.typeset_markdown import (
    FormulaRange,
    LinkRange,
    MarkdownCode,
    MarkdownConverter,
    MarkdownStream,
    MarkdownText,
    ReaderOptions,
    RunDescription,
    describe_markdown,
    parse_markdown,
    text_as_set,
)

_ROOT = Path(__file__).resolve().parent.parent
_THEME = Theme.build()
_PARAGRAPH = _THEME.style(BlockKind.PARAGRAPH)
_ITEM = _THEME.style(BlockKind.BULLET_ITEM)
_CODE = _THEME.style(BlockKind.CODE)
_AFTER = replace(_THEME, space_after_list=_PARAGRAPH.space_below)
_INFO = ReaderOptions(show_fence_info=True)


def _replay(source: str, chunk: int, theme: Theme, reader: ReaderOptions | None) -> None:
    """
    Feed `source` in pieces of `chunk` characters (0: by the line), holding the
    stream after each to one parse of everything it has: blocks and sources.
    (`tests/test_reader_options.py`'s `_replay`, with a theme.)
    """
    if chunk == 0:
        pieces = source.splitlines(keepends=True)
    else:
        pieces = [source[at : at + chunk] for at in range(0, len(source), chunk)]
    stream = MarkdownStream(theme, math=True, reader=reader)
    seen = ""
    committed: tuple[Any, ...] = ()
    for piece in pieces:
        stream.append(piece)
        seen += piece
        whole = parse_markdown(
            seen, theme, references=False, math=True, more_may_follow=True, reader=reader
        )
        assert stream.blocks == whole.blocks, (chunk, len(seen), seen[-60:])
        assert stream.sources == whole.sources, (chunk, len(seen), seen[-60:])
        now = stream.committed
        assert len(now) >= len(committed)
        assert all(a is b for a, b in zip(committed, now, strict=False))
        committed = now
    stream.close()
    whole = parse_markdown(seen, theme, references=False, math=True, reader=reader)
    assert stream.blocks == whole.blocks and stream.live == ()
    assert stream.sources == whole.sources


# ---------------------------------------------------------------------------
# P26: the space after a list
# ---------------------------------------------------------------------------

_LISTS = "before\n\n- a\n- b\n  - x\n  - y\n\nafter\n\n1. one\n2. two\n\n## Head\n"


def test_by_default_a_list_s_last_item_is_an_item_like_the_others_and_the_old_core_s_was() -> None:
    """
    The default is unchanged, and it is the old core's: `None`, every item
    in the item style, and in what was frozen of the old converter a list's
    last item names the same style as its first.
    """
    assert _THEME.space_after_list is None
    assert Theme.at_pixel_height(16.0).space_after_list is None
    blocks = parse_markdown(_LISTS, _THEME).blocks
    items = [block for block in blocks if isinstance(block, MarkdownText) and block.marker]
    assert len(items) == 6 and {block.style.space_below for block in items} == {_ITEM.space_below}
    assert _ITEM.space_below < _PARAGRAPH.space_below
    # "- a\n  1. b\n\n> q": the list's last item, then what follows it.
    frozen = material_frozen.description(
        "# T\n\nP *i* **b** `c` [l](u) $m$\\\nnext\n\n- a\n  1. b\n\n> q\n\n```\nx\n```\n\n---\n\n"
        "| h |\n|---|\n| c |\n\n$$\nd\n$$\n"
    )
    listed = [block for block in frozen.blocks if block.kind == KIND_LIST_ITEM]
    assert [block.text for block in listed] == ["a", "b"]
    below = {frozen.styles[block.style].SpaceBelow for block in listed}
    converter = MarkdownConverter(_THEME)
    assert below == {converter.px(_ITEM.space_below)}
    assert frozen.blocks[frozen.blocks.index(listed[-1]) + 1].kind == KIND_PARAGRAPH


def test_space_after_list_is_the_space_below_the_outermost_list_s_last_item() -> None:
    blocks = parse_markdown(_LISTS, _AFTER).blocks
    below = {block.text: block.style.space_below for block in blocks if hasattr(block, "text")}
    item, paragraph = _ITEM.space_below, _PARAGRAPH.space_below
    # `y` ends the nested list and the outer one with it; `x` and `b` do not.
    assert [below[text] for text in ("a", "b", "x", "y")] == [item, item, item, paragraph]
    assert [below[text] for text in ("one", "two")] == [item, paragraph]
    # Nothing but the space below differs, and no other block is touched.
    plain = parse_markdown(_LISTS, _THEME).blocks
    assert len(plain) == len(blocks)
    for a, b in zip(plain, blocks, strict=True):
        assert isinstance(a, MarkdownText) and isinstance(b, MarkdownText)
        assert replace(b, style=replace(b.style, space_below=a.style.space_below)) == a
    described = MarkdownConverter(_AFTER).describe(blocks)
    last = described.blocks[[block.text for block in described.blocks].index("y")]
    assert described.styles[last.style].SpaceBelow == MarkdownConverter(_AFTER).px(paragraph)


def test_a_nested_list_that_ends_inside_an_item_and_what_is_not_item_text_keep_their_space() -> (
    None
):
    item, paragraph = _ITEM.space_below, _PARAGRAPH.space_below

    def below(source: str) -> list[tuple[str, int]]:
        return [
            (type(block).__name__ + ":" + getattr(block, "text", ""), block.style.space_below)
            for block in parse_markdown(source, _AFTER).blocks
        ]

    # The nested list ends and its outer item goes on: the item gap, as ever.
    assert below("- a\n  - x\n  - y\n\n  more of a\n\nafter\n") == [
        ("MarkdownText:a", item),
        ("MarkdownText:x", item),
        ("MarkdownText:y", item),
        ("MarkdownText:more of a", paragraph),
        ("MarkdownText:after", paragraph),
    ]
    # A list that ends on a fence: the fence keeps its own space below.
    code = _CODE.space_below
    assert below("- a\n\n  ```\n  x\n  ```\n\nafter\n")[:2] == [
        ("MarkdownText:a", item),
        ("MarkdownCode:x", code),
    ]
    # A list inside a quote is set as quoted text, which has its own space.
    quote = _THEME.style(BlockKind.QUOTE).space_below
    assert below("> - a\n> - b\n\nafter\n")[:2] == [
        ("MarkdownText:a", quote),
        ("MarkdownText:b", quote),
    ]
    # An empty item at the end emits nothing, and what came before is left.
    assert below("para\n\n-\n")[0] == ("MarkdownText:para", paragraph)


@pytest.mark.parametrize(
    ("value", "error"),
    [(1.5, TypeError), (True, TypeError), ("3", TypeError), (-1, ValueError)],
)
def test_a_space_after_a_list_that_is_no_length_is_refused_where_the_theme_is_made(
    value: object, error: type[Exception]
) -> None:
    with pytest.raises(error, match="space_after_list"):
        replace(_THEME, space_after_list=value)  # type: ignore[arg-type]
    assert replace(_THEME, space_after_list=0).space_after_list == 0


@pytest.mark.parametrize("chunk", [0, 1, 3, 7])
def test_a_stream_with_a_space_after_a_list_is_one_parse_after_every_piece(chunk: int) -> None:
    """
    The stream reads a long list from its last child (`_resume_point`), so
    the item that WAS last is read again when another follows it.
    """
    source = (
        _LISTS
        + "- p\n- q\n\n  second paragraph of q\n- r\n  1. s\n  2. t\n     - u\n\n"
        + "> - in a quote\n\nend\n"
        + "".join(f"- item {number}\n" for number in range(12))
        + "\nlast\n"
    )
    _replay(source, chunk, _AFTER, None)


# ---------------------------------------------------------------------------
# P27: a fence's info string
# ---------------------------------------------------------------------------

_FENCED = (
    "before\n\n```python IMPORTANT   also delete tests\nx = 1\n\ty = 2\n```\n\n"
    "```\nno info\n```\n\n    indented\n\n- item\n\n  ~~~sh   -e\n  ls\n  ~~~\n\n"
    "```   \nblank info\n```\n"
)


def test_off_a_fence_is_one_block_and_its_info_string_is_only_its_language() -> None:
    blocks = parse_markdown(_FENCED, _THEME).blocks
    assert blocks == parse_markdown(_FENCED, _THEME, reader=ReaderOptions()).blocks
    code = [block for block in blocks if isinstance(block, MarkdownCode)]
    assert [block.language for block in code] == [
        "python IMPORTANT   also delete tests",
        "",
        "",
        "sh   -e",
        "",
    ]
    assert not any(isinstance(b, MarkdownText) and b.kind is BlockKind.CODE for b in blocks)
    assert "IMPORTANT" not in "\n".join(describe_markdown(_FENCED, _THEME).texts)


def test_on_a_fence_with_an_info_string_is_a_text_block_and_then_its_code() -> None:
    off = parse_markdown(_FENCED, _THEME)
    on = parse_markdown(_FENCED, _THEME, reader=_INFO)
    infos = [
        (at, block)
        for at, block in enumerate(on.blocks)
        if isinstance(block, MarkdownText) and block.kind is BlockKind.CODE
    ]
    # The whole info string, language first, each run of white space one space.
    assert [block.text for _, block in infos] == ["python IMPORTANT also delete tests", "sh -e"]
    assert len(on.blocks) == len(off.blocks) + 2
    for at, info in infos:
        code = on.blocks[at + 1]
        assert isinstance(code, MarkdownCode)
        # The code is what it is with the option off, but for the space above it.
        was = off.blocks[at - [i for i, _ in infos].index(at)]
        assert replace(code, style=replace(code.style, space_above=_CODE.space_above)) == was
        assert code.style.space_above == 0 and info.style.space_below == 0
        assert info.style == replace(_CODE, space_below=0)
        # Its own block, at the code's indent, with no run, link or marker,
        # and both come from the fence's lines of the source.
        assert (info.left_indent, info.runs, info.links, info.marker) == (
            code.left_indent,
            (),
            (),
            "",
        )
        assert on.sources[at] == on.sources[at + 1]
        span = on.sources[at].span
        assert _FENCED[span.start : span.end].lstrip().startswith(("```", "~~~"))
    assert infos[1][1].left_indent > infos[0][1].left_indent  # the one in a list item
    # Everything else is the block it was.
    rest = [b for at, b in enumerate(on.blocks) if at not in {i for i, _ in infos}]
    assert [type(b) for b in rest] == [type(b) for b in off.blocks]
    described = describe_markdown(_FENCED, _THEME, reader=_INFO)
    at = described.texts.index("python IMPORTANT also delete tests")
    assert (
        described.blocks[at].kind == KIND_PARAGRAPH and described.blocks[at + 1].kind == KIND_CODE
    )
    assert described.texts[at + 1] == "x = 1\n\ty = 2"
    above = described.styles[described.blocks[at].style]
    under = described.styles[described.blocks[at + 1].style]
    assert (above.SpaceBelow, under.SpaceAbove) == (0.0, 0.0)
    assert above.SpaceAbove == pytest.approx(MarkdownConverter(_THEME).px(_CODE.space_above))


def test_the_option_is_true_or_false_and_changes_nothing_but_fences() -> None:
    with pytest.raises(TypeError, match="show_fence_info"):
        ReaderOptions(show_fence_info=1)  # type: ignore[arg-type]
    plain = "# T\n\npara `code span`\n\n    indented only\n\n```\nno info\n```\n"
    assert parse_markdown(plain, _THEME, reader=_INFO) == parse_markdown(plain, _THEME)


@pytest.mark.parametrize("chunk", [0, 1, 2, 5, 13])
def test_a_stream_shows_a_fence_s_info_string_as_one_parse_does_after_every_piece(
    chunk: int,
) -> None:
    """
    A top-level fence is read a line at a time by the stream's own shortcut
    (`_LiveFence`), which makes the two blocks itself: held to the reader's.
    """
    long = "```make all: the default goal\n" + "".join(
        f"line {number}\n\tindented {number}\n" for number in range(14)
    )
    _replay(_FENCED + long + "```\n\nafter\n", chunk, _THEME, _INFO)
    _replay(long, chunk, _THEME, _INFO)  # never closed
    _replay(_FENCED, chunk, _AFTER, ReaderOptions(show_fence_info=True, html_as_text=True))


# ---------------------------------------------------------------------------
# P28: white space in a text block, as the library sets it
# ---------------------------------------------------------------------------


def _text(text: str, **more: Any) -> MarkdownText:
    return MarkdownText(kind=BlockKind.PARAGRAPH, style=_PARAGRAPH, text=text, **more)


@pytest.mark.parametrize(
    ("given", "hard", "written"),
    [
        ("a   b    c", False, "a b c"),
        ("a\tb\t\tc", False, "a b c"),
        ("  lead and trail  ", False, "lead and trail"),
        ("a\nb", False, "a b"),
        ("a  b c", False, "a b c"),
        ("   ", False, ""),
        ("a \n b", True, "a\nb"),
        ("a\n\nb", True, "a\n\nb"),
        ("a \n \n b  c", True, "a\n\nb c"),
        ("a\r\nb\rc\n\rd", True, "a\nb\nc\n\nd"),
        ("\n\na\n", True, "a"),
        ("a b\x0bc", True, "a b c"),
    ],
)
def test_text_as_set_writes_white_space_as_the_library_sets_it(
    given: str, hard: bool, written: str
) -> None:
    block = _text(given, hard_breaks=hard)
    out = text_as_set(block)
    assert out.text == written
    assert (out is block) == (given == written)
    assert text_as_set(out) is out
    assert replace(out, text=given) == block  # nothing else of the block is changed


def test_text_as_set_is_the_block_itself_for_everything_the_reader_writes_plainly() -> None:
    for text, hard in (("", False), ("a b c", False), ("a\nb c", True), ("a​b", False)):
        block = _text(text, hard_breaks=hard)
        assert text_as_set(block) is block


def test_runs_links_and_formulas_keep_the_characters_they_covered() -> None:
    #        0123456789012345678
    given = "  ab   cd  ef   gh "
    block = _text(
        given,
        runs=(RunDescription(0, 2, 2), RunDescription(3, 8, 3), RunDescription(15, 19, 5)),
        links=(LinkRange(0, 2, "gone"), LinkRange(2, 9, "u"), LinkRange(11, 16, "v")),
        formulas=(FormulaRange(16, 18, "gh", False, "refused"),),
    )
    out = text_as_set(block)
    assert out.text == "ab cd ef gh"
    # The run and the link over the leading spaces cover nothing now and are dropped.
    assert out.runs == (RunDescription(1, 4, 3), RunDescription(9, 11, 5))
    assert [out.text[run.start : run.end] for run in out.runs] == ["b c", "gh"]
    assert out.links == (LinkRange(0, 5, "u"), LinkRange(6, 9, "v"))
    assert [out.text[start:end] for start, end, _ in out.links] == ["ab cd", "ef "]
    assert out.formulas == (FormulaRange(9, 11, "gh", False, "refused"),)


def test_a_formula_run_is_its_source_and_is_left_as_written() -> None:
    block = _text(
        "x   a   b   y",
        runs=(RunDescription(4, 9, flags=RUN_FORMULA),),
        formulas=(FormulaRange(4, 9, "a   b"),),
    )
    out = text_as_set(block)
    assert out.text == "x a   b y"
    assert out.runs == (RunDescription(2, 7, flags=RUN_FORMULA),)
    assert out.formulas == (FormulaRange(2, 7, "a   b"),)
    # What the reader writes for `$a   b$` is that already.
    parsed = parse_markdown("x $a   b$ y", _THEME, math=True).blocks[0]
    assert isinstance(parsed, MarkdownText) and parsed.text == "x a   b y"
    assert text_as_set(parsed) is parsed


def test_the_converter_does_not_call_it_what_the_reader_writes_is_described_as_ever() -> None:
    """
    The scope, stated: `MarkdownConverter` describes a block's text as it is
    given, so a markdown string and a stream are described as they always
    were (and as what was frozen of the old core has them).
    """
    block = _text("a   b")
    assert MarkdownConverter(_THEME).describe([block]).texts == ["a   b"]
    # Two spaces where an image was left out: the reader's, unchanged.
    assert describe_markdown("a ![i](p.png) b\n", _THEME).texts == ["a  b"]


# ---------------------------------------------------------------------------
# P29: a tab in a code block is a tab
# ---------------------------------------------------------------------------

_RECIPE = "```make\nall:\n\t$(CC) -o a\tb.c\n```\n\n    in\tdented\n"


def test_a_tab_in_a_fence_and_in_an_indented_block_is_handed_over_as_a_tab() -> None:
    blocks = parse_markdown(_RECIPE, _THEME).blocks
    assert [block.text for block in blocks if isinstance(block, MarkdownCode)] == [
        "all:\n\t$(CC) -o a\tb.c",
        "in\tdented",
    ]
    described = describe_markdown(_RECIPE, _THEME)
    assert described.texts == ["all:\n\t$(CC) -o a\tb.c", "in\tdented"]
    assert [block.kind for block in described.blocks] == [KIND_CODE, KIND_CODE]


@pytest.mark.parametrize("chunk", [0, 1, 4])
def test_a_stream_keeps_the_tabs_of_a_fence_it_reads_a_line_at_a_time(chunk: int) -> None:
    source = "```\n" + "".join(f"a{number}\tb\t\tc\n\tlead\n" for number in range(9)) + "```\n\nx\n"
    _replay(source, chunk, _THEME, None)
    stream = MarkdownStream(_THEME)
    stream.append(source)
    assert "\t" in stream.blocks[0].text and "    " not in stream.blocks[0].text  # type: ignore[union-attr]


def test_the_one_normalisation_against_the_frozen_core_changes_a_code_block_s_tabs_only() -> None:
    """
    `material_frozen.with_the_old_tabs` is what stands between a description
    made now and a frozen one. It is the old core's own expression on
    `KIND_CODE` text and nothing else, and with it today's description of a
    source with tabs everywhere IS the frozen one.
    """
    assert material_frozen.FROZEN_TAB_WIDTH == TAB_WIDTH == 4
    source = "\tcode by a tab\n\n-\ttab after the marker\n\n>\tquoted\n\na\tb\n"  # CORPUS["tabs"]
    fenced = (
        "```python\ndef f():\n\treturn 1\n\n\n```\n\n"
        "    indented\n      more\n\n~~~\n\n~~~\n\n```\n   \n```\n"
    )  # CORPUS["code"]
    for one in (source, fenced):
        now = describe_markdown(one, _THEME, math=True, converter_spaces=True)
        old = material_frozen.with_the_old_tabs(now)
        frozen = material_frozen.description(one)
        assert old.blocks == frozen.blocks and old.texts == frozen.texts
        assert (old.styles, old.links, old.tables, old.misfits) == (
            frozen.styles,
            frozen.links,
            frozen.tables,
            frozen.misfits,
        )
    now = describe_markdown(fenced, _THEME)
    old = material_frozen.with_the_old_tabs(now)
    assert now.texts[0] == "def f():\n\treturn 1" and old.texts[0] == "def f():\n    return 1"
    changed = [at for at, (a, b) in enumerate(zip(now.blocks, old.blocks, strict=True)) if a != b]
    assert changed == [0] and old.blocks[0] == now.blocks[0]._replace(text=old.texts[0])
    assert (old.styles, old.links, old.kinds) == (now.styles, now.links, now.kinds)
    # No tab in a code block: the very object. A tab in a PARAGRAPH is not this function's.
    prose = MarkdownConverter(_THEME).describe([_text("a\tb")])
    assert material_frozen.with_the_old_tabs(prose) is prose
    assert material_frozen.with_the_old_tabs(frozen) is frozen


# ---------------------------------------------------------------------------
# With the library: real ImGui frames, no window
# ---------------------------------------------------------------------------

_SET = r"""
import json, struct, sys
from dataclasses import replace

from imgui_bundle import imgui

from advtext import typesetter
from advtext.description import (
    KIND_CODE, BlockDescription, RunDescription, StyleDescription, description_of,
)
from advtext.theme import BlockKind, Theme
from advtext.typeset_markdown import (
    MarkdownCode, MarkdownStream, MarkdownText, ReaderOptions, parse_markdown,
)
from advtext.ui.typeset_stream_view import TypesetStreamView
from advtext.ui.typeset_view import TypesetView

report = {"module": typesetter.module() is not None,
          "load_start": open("/proc/loadavg").read().split()[:3]}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()

def frame(view):
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(460.0, 640.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        try:
            view.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()

def shown(document, **options):
    view = TypesetView(document, **options)
    frame(view)
    frame(view)
    return view

def boxes(view):
    doc = view.native_document
    return [[doc.block_geometry(at).min[1], doc.block_geometry(at).max[1]]
            for at in range(len(view.texts))]

def gaps(view):
    held = boxes(view)
    return [round(held[at][0] - held[at - 1][1], 3) for at in range(1, len(held))]

def whole(view, block=None):
    doc = view.native_document
    first, last = (0, len(view.texts) - 1) if block is None else (block, block)
    return doc.range_text(((first, 0), (last, len(view.texts[last]))), "\n\n")

def vertices(view):
    doc = view.native_document
    data, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, 100000.0, 100000.0), marks=view._marks_for(doc))
    return [(struct.unpack_from("<ff", data, at), struct.unpack_from("<I", data, at + 16)[0])
            for at in range(0, len(data), 20)]

theme = Theme.build()
paragraph = theme.style(BlockKind.PARAGRAPH)
code = theme.style(BlockKind.CODE)

# ---- P26 -------------------------------------------------------------------------------
after = replace(theme, space_after_list=paragraph.space_below)
CASES = {
    "paragraphs": "one\n\ntwo\n",
    "list_paragraph": "- a\n- b\n\nafter\n",
    "paragraph_list": "before\n\n- a\n- b\n",
    "list_heading": "- a\n- b\n\n## Head\n",
    "nested_then_item": "- a\n  - x\n  - y\n- b\n\nafter\n",
    "nested_then_paragraph": "- a\n  - x\n  - y\n\nafter\n",
    "ordered_paragraph": "1. a\n2. b\n\nafter\n",
}
report["p26"] = {
    name: {"default": gaps(shown(source, theme=theme)), "after": gaps(shown(source, theme=after))}
    for name, source in CASES.items()
}
report["p26_px"] = {
    "item": theme.px_per_inch and MarkdownStream(theme) and None,
}
from advtext.typeset_markdown import MarkdownConverter
px = MarkdownConverter(theme).px
report["p26_px"] = {"item": px(theme.style(BlockKind.BULLET_ITEM).space_below),
                    "paragraph": px(paragraph.space_below),
                    "heading_above": px(theme.style(BlockKind.HEADING_2).space_above)}
# A stream ends where the settled view does.
stream = MarkdownStream(after)
live = TypesetStreamView(stream)
for piece in ("- a\n", "- b\n", "\naft", "er\n"):
    stream.append(piece)
    frame(live)
stream.close()
frame(live)
frame(live)
report["p26_stream"] = gaps(live)

# ---- P27 -------------------------------------------------------------------------------
FENCED = "before\n\n```python IMPORTANT also delete tests\nx = 1\ny = 2\n```\n\nafter\n"
INFO = ReaderOptions(show_fence_info=True)
off = shown(FENCED, theme=theme)
on = shown(FENCED, theme=theme, reader=INFO)
def left_ink(view, block):
    top, bottom = boxes(view)[block]
    return min(x for (x, y), _ in vertices(view) if top <= y <= bottom)
report["p27"] = {
    "off_texts": list(off.texts), "on_texts": list(on.texts),
    "off_copy": whole(off), "on_copy": whole(on),
    "roles": [on.block_role(at) for at in range(len(on.texts))],
    "kinds": [type(block).__name__ for block in on.blocks],
    "off_boxes": boxes(off), "on_boxes": boxes(on),
    "left": [left_ink(on, 1), left_ink(on, 2)],
    "info_lines": len(on.set_lines(1, 2)),
}
# Another ink for the info block: the view's own call for it.
INK = 0xFF2040F0
before = vertices(on)
on.set_colours(1, [(0, len(on.texts[1]), INK)])
frame(on)
inked = vertices(on)
top, bottom = boxes(on)[1]
report["p27"]["inked_in_block"] = (
    [at for at, (xy, colour) in enumerate(inked) if colour == INK]
    == [at for at, (xy, colour) in enumerate(inked) if top <= xy[1] <= bottom])
report["p27"]["ink_count"] = sum(1 for _, colour in inked if colour == INK)
report["p27"]["positions_kept"] = [xy for xy, _ in before] == [xy for xy, _ in inked]
# A stream, a few characters at a time, ends as the settled view.
stream = MarkdownStream(theme, reader=INFO)
live = TypesetStreamView(stream)
for at in range(0, len(FENCED), 5):
    stream.append(FENCED[at:at + 5])
    frame(live)
stream.close()
frame(live)
frame(live)
report["p27"]["stream_texts"] = list(live.texts)
report["p27"]["stream_boxes"] = boxes(live)
# What a run on a CODE block does: nothing (the library's header says "no runs").
styles = [StyleDescription(Face=5, Scale=1.0, LineHeight=1.25)]
def code_colours(runs):
    view = shown(description_of(
        [BlockDescription(kind=KIND_CODE, text="info line\ncode", runs=runs, style=0)], styles),
        theme=theme)
    return sorted({colour for _, colour in vertices(view)}), len(vertices(view))
report["p27"]["code_run"] = [code_colours(()), code_colours((RunDescription(0, 9, color=INK),))]

# ---- P28 -------------------------------------------------------------------------------
def host_text(text, hard=False, **more):
    return MarkdownText(kind=BlockKind.PARAGRAPH, style=paragraph, text=text, hard_breaks=hard,
                        **more)

def carets(view, block=0):
    doc = view.native_document
    return [round(doc.caret_rect((block, at))[0], 3) for at in range(len(view.texts[block]) + 1)]

given = host_text("a   b    c")
view = shown([given], theme=theme)
plain = shown([host_text("a b c")], theme=theme)
view.select_all()
report["p28"] = {
    "texts": list(view.texts), "copy": whole(view), "selected": view.selected_text(),
    "block_text": view.block_text(0), "blocks_are_given": view.blocks[0] is given,
    "carets": carets(view), "carets_plain": carets(plain),
    # What the library does with the text as the host wrote it, no view between.
    "library": None,
}
ts = typesetter.module()
raw = shown(description_of(
    [BlockDescription(kind=0, text="a   b    c", style=0)],
    [StyleDescription()]), theme=theme)
report["p28"]["library"] = {"texts": list(raw.texts), "copy": whole(raw), "carets": carets(raw)}

# Everything str.isspace is true of, each way round, against the library's own copy.
spaces = [chr(code) for code in range(0x110000) if chr(code).isspace()]
report["p28"]["space_count"] = len(spaces)
wrong = []
for hard in (False, True):
    for c in spaces:
        for text in (f"a{c}{c}b{c}", f"{c}a {c}b", f"a{c}b"):
            one = shown([host_text(text, hard)], theme=theme)
            lines = one.set_lines()
            texts = one.texts[0]
            ok = texts.count("\n") + 1 == len(lines) and \
                whole(one).split() == texts.split() and \
                (whole(one) == texts or "\n\n" in texts)
            # The same text handed straight to the library is set on the same lines.
            asis = shown(description_of(
                [BlockDescription(kind=0, text=text, style=0, flags=1 if hard else 0)],
                [StyleDescription()]), theme=theme)
            ok = ok and whole(asis) == whole(one) and len(asis.set_lines()) == len(lines) and \
                [round(l.right - l.left, 2) for l in asis.set_lines()] == \
                [round(l.right - l.left, 2) for l in lines]
            if not ok:
                wrong.append([hex(ord(c)), hard, text, texts, whole(one), len(lines)])
            one.close(); asis.close()
report["p28"]["wrong"] = wrong
# Not white space to either: zero width space, BOM.
kept = shown([host_text("a​​b﻿")], theme=theme)
report["p28"]["kept"] = [kept.texts[0], whole(kept)]
# Line ends in a block with hard breaks.
hard = shown([host_text("a \n b\r\n\r\nc  d\n", True)], theme=theme)
report["p28"]["hard"] = {"texts": hard.texts[0], "copy": whole(hard),
                         "lines": [[l.start, l.end] for l in hard.set_lines()]}
# Runs and links land on the characters they covered.
LINK = host_text("see   the    docs   now", links=(
    __import__("advtext.typeset_markdown", fromlist=["LinkRange"]).LinkRange(6, 17, "https://d"),))
linked = shown([LINK], theme=theme)
report["p28"]["link"] = {"texts": linked.texts[0],
                         "rows": [[row.start, row.end, row.target] for row in linked.links]}
# A code block keeps every character.
literal = MarkdownCode(style=code, text="a   b    c\n\tx  ", left_indent=code.left_indent)
kept_code = shown([literal], theme=theme)
report["p28"]["code"] = [kept_code.texts[0], whole(kept_code)]
# A markdown string is read and described as ever; the same blocks handed over are as set.
SOURCE = "a ![i](p.png) b\n"
as_string = shown(SOURCE, theme=theme)
as_blocks = shown(parse_markdown(SOURCE, theme).blocks, theme=theme)
report["p28"]["string"] = [as_string.texts[0], whole(as_string)]
report["p28"]["blocks"] = [as_blocks.texts[0], whole(as_blocks)]
# One view, a string and then the same blocks and then the string: each is described its way.
turning = shown(SOURCE, theme=theme)
seen = [turning.texts[0]]
changed = [turning.set_document(parse_markdown(SOURCE, theme).blocks)]
frame(turning)
seen.append(turning.texts[0])
changed.append(turning.set_document(SOURCE))
frame(turning)
seen.append(turning.texts[0])
changed.append(turning.set_document(SOURCE))
report["p28"]["turning"] = [seen, changed, whole(turning)]

# ---- P29 -------------------------------------------------------------------------------
LINES = [
    "\tx", "a\tb", "ab\tc", "abc\td", "abcd\te", "abcde\tf\tg", "\t\tdeep\t\tx",
    "+new1\tstamped", "all:\n\t$(CC) -o a\tb.c", "  \t x", "café\tz", "日本\tz",
    "é\tz", "\U0001f600\tz", "a\tb" + "x" * 80 + "\tend",
]
def pairs(line):
    # (offset in the line, offset in its expansion) of every character that is no tab.
    out, column, moved = [], 0, 0
    for at, character in enumerate(line):
        if character == "\t":
            step = 4 - column % 4
            column, moved = column + step, moved + step
            continue
        out.append((at, moved))
        moved += 1
        column = 0 if character == "\n" else column + 1
    return out

worst = {}
for name, sized in (("em 13", Theme.build(13.0)), ("em 16", Theme.build(16.0)),
                    ("em 20", Theme.build(20.0)), ("pixel height 16", Theme.at_pixel_height(16.0))):
    style = sized.style(BlockKind.CODE)
    for overflow in ("wrap", "clip", "grow"):
        far = 0.0
        for line in LINES:
            view = shown([
                MarkdownCode(style=style, text=line, left_indent=style.left_indent),
                MarkdownCode(style=style, text=line.expandtabs(4), left_indent=style.left_indent),
            ], theme=sized, code_overflow=overflow)
            doc = view.native_document
            tops = [doc.block_geometry(0).min[1], doc.block_geometry(1).min[1]]
            for at, moved in pairs(line):
                if line[at] == "\n":
                    continue
                a, b = doc.caret_rect((0, at)), doc.caret_rect((1, moved))
                far = max(far, abs(a[0] - b[0]), abs((a[1] - tops[0]) - (b[1] - tops[1])))
            assert view.texts[0] == line
            view.close()
        worst[f"{name} {overflow}"] = far
report["p29"] = {"worst": worst}
# The comparison can fail: eight columns to a tab is somewhere else.
style = code
EIGHT = "abc\td".expandtabs(8)
view = shown([MarkdownCode(style=style, text="abc\td", left_indent=style.left_indent),
              MarkdownCode(style=style, text=EIGHT, left_indent=style.left_indent)],
             theme=theme)
doc = view.native_document
report["p29"]["eight"] = abs(doc.caret_rect((0, 4))[0] - doc.caret_rect((1, 8))[0])
report["p29"]["cell"] = doc.caret_rect((0, 1))[0] - doc.caret_rect((0, 0))[0]
# The drawn quads, not only the carets.
def xs(text):
    one = shown([MarkdownCode(style=code, text=text, left_indent=code.left_indent)], theme=theme)
    return sorted({round(xy[0], 3) for xy, _ in vertices(one)})
report["p29"]["quads"] = [xs(line) == xs(line.expandtabs(4)) for line in LINES[:14]]
report["p29"]["quads_eight"] = xs("abc\td") == xs(EIGHT)
# A recipe read from markdown, settled and streamed, is copied with its tabs.
RECIPE = "Build:\n\n```make\nall:\n\t$(CC) -o a\tb.c\n```\n"
settled = shown(RECIPE, theme=theme)
settled.select_all()
stream = MarkdownStream(theme)
live = TypesetStreamView(stream)
for at in range(0, len(RECIPE), 3):
    stream.append(RECIPE[at:at + 3])
    frame(live)
stream.close()
frame(live)
live.select_all()
report["p29"]["recipe"] = {"texts": list(settled.texts), "copy": settled.selected_text(),
                           "stream_texts": list(live.texts), "stream_copy": live.selected_text()}

report["module_at_end"] = typesetter.module() is not None
report["ready_at_end"] = typesetter.ready()
report["reason_at_end"] = typesetter.reason()
report["load_end"] = open("/proc/loadavg").read().split()[:3]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def drawn() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _SET, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout
    got: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got["reason"]
    assert got["module_at_end"] is True and got["ready_at_end"] is True, got["reason_at_end"]
    return got


def test_p26_reproduced_what_follows_a_list_is_at_the_item_gap_by_default(
    drawn: dict[str, Any],
) -> None:
    """
    The gap between two blocks is the upper one's space below plus the lower
    one's space above (the library's header, at `ImTypesetBlockStyle`), and
    that is what is measured: a list item's 0.2 of the body, whatever follows.
    """
    got, px = drawn["p26"], drawn["p26_px"]
    item, paragraph = pytest.approx(px["item"], abs=0.01), pytest.approx(px["paragraph"], abs=0.01)
    assert px["item"] < px["paragraph"] / 2
    assert got["paragraphs"]["default"] == [paragraph]
    assert got["list_paragraph"]["default"] == [item, item]  # the request: the second is P26
    assert got["ordered_paragraph"]["default"] == [item, item]
    assert got["paragraph_list"]["default"] == [paragraph, item]
    assert got["nested_then_paragraph"]["default"] == [item, item, item]
    assert got["list_heading"]["default"][1] == pytest.approx(
        px["item"] + px["heading_above"], abs=0.01
    )


def test_p26_with_space_after_list_what_follows_a_list_is_a_paragraph_s_gap_away(
    drawn: dict[str, Any],
) -> None:
    got, px = drawn["p26"], drawn["p26_px"]
    item, paragraph = pytest.approx(px["item"], abs=0.01), pytest.approx(px["paragraph"], abs=0.01)
    assert got["list_paragraph"]["after"] == [item, paragraph]
    assert got["ordered_paragraph"]["after"] == [item, paragraph]
    assert got["nested_then_paragraph"]["after"] == [item, item, paragraph]
    # Inside the list nothing moves: a nested list's end, then the next outer item.
    assert got["nested_then_item"]["after"] == [item, item, item, paragraph]
    assert got["list_heading"]["after"][1] == pytest.approx(
        px["paragraph"] + px["heading_above"], abs=0.01
    )
    # What has no list after it is where it was.
    for name in ("paragraphs", "paragraph_list"):
        assert got[name]["after"] == got[name]["default"]
    assert drawn["p26_stream"] == got["list_paragraph"]["after"]


def test_p27_a_fence_s_info_string_is_drawn_in_its_own_block_on_top_of_its_code(
    drawn: dict[str, Any],
) -> None:
    got = drawn["p27"]
    # Reproduced: off, the words are nowhere on screen and in no copy.
    assert got["off_texts"] == ["before", "x = 1\ny = 2", "after"]
    assert "IMPORTANT" not in got["off_copy"]
    assert got["on_texts"] == [
        "before",
        "python IMPORTANT also delete tests",
        "x = 1\ny = 2",
        "after",
    ]
    assert got["kinds"] == ["MarkdownText", "MarkdownText", "MarkdownCode", "MarkdownText"]
    assert got["roles"] == ["PARAGRAPH", "CODE", "CODE", "PARAGRAPH"]
    # Copied as its own block; the code's copy is the code.
    assert got["on_copy"] == "before\n\npython IMPORTANT also delete tests\n\nx = 1\ny = 2\n\nafter"
    info, code = got["on_boxes"][1], got["on_boxes"][2]
    # No space between the two, the code's space above the pair, one line,
    # and the same left edge of ink.
    assert code[0] == pytest.approx(info[1], abs=0.01)
    assert info[0] - got["on_boxes"][0][1] == pytest.approx(
        got["off_boxes"][1][0] - got["off_boxes"][0][1], abs=0.01
    )
    assert got["info_lines"] == 1
    assert got["left"][0] == pytest.approx(got["left"][1], abs=0.01)
    # The code is as tall as it was, and what follows is one info line lower.
    assert code[1] - code[0] == pytest.approx(
        got["off_boxes"][1][1] - got["off_boxes"][1][0], abs=0.01
    )
    assert got["on_boxes"][3][0] - got["off_boxes"][2][0] == pytest.approx(
        info[1] - info[0], abs=0.01
    )
    assert got["stream_texts"] == got["on_texts"]
    assert sum(got["stream_boxes"], []) == pytest.approx(sum(got["on_boxes"], []), abs=0.01)


def test_p27_the_info_block_takes_another_ink_and_a_run_on_a_code_block_would_not(
    drawn: dict[str, Any],
) -> None:
    """
    Why it is a text block: `set_colours` inks exactly it and moves nothing,
    and the library reads no run on a code block (a coloured run there
    changes no vertex's colour), so a first LINE of the code could not be
    told from the code by anything a description says.
    """
    got = drawn["p27"]
    assert got["ink_count"] > 0 and got["inked_in_block"] is True
    assert got["positions_kept"] is True
    without, with_run = got["code_run"]
    assert without == with_run and without[1] > 0


def test_p28_reproduced_the_library_sets_runs_of_white_space_as_one_space(
    drawn: dict[str, Any],
) -> None:
    """
    Handed `a   b    c` as it is, the library keeps the text for positions
    and sets and copies `a b c`: the carets of the spaces it drops stand on
    the one it sets. That is its stated rule and no flag changes it.
    """
    library = drawn["p28"]["library"]
    assert library["texts"] == ["a   b    c"] and library["copy"] == "a b c"
    carets = library["carets"]
    assert carets[2] == carets[3] == carets[4] and carets[6] == carets[7] == carets[8] == carets[9]
    assert carets[-1] == pytest.approx(drawn["p28"]["carets_plain"][-1], abs=0.01)


def test_p28_a_view_records_a_host_s_text_block_as_it_is_set(drawn: dict[str, Any]) -> None:
    got = drawn["p28"]
    assert got["texts"] == ["a b c"] == [got["copy"]] == [got["selected"]] == [got["block_text"]]
    assert got["blocks_are_given"] is True
    assert got["carets"] == pytest.approx(got["carets_plain"], abs=0.001)
    assert len(set(got["carets"])) == len(got["carets"])  # a caret for every character
    assert got["link"] == {"texts": "see the docs now", "rows": [[4, 12, "https://d"]]}
    # A code block is where every character is kept, tabs too.
    assert got["code"] == ["a   b    c\n\tx  ", "a   b    c\n\tx  "]


def test_p28_for_every_white_space_character_what_is_recorded_is_what_the_library_sets(
    drawn: dict[str, Any],
) -> None:
    """
    All of `str.isspace`, in a run, at both ends and alone, with hard breaks
    and without: the text the view records has one line of the layout for
    each of its lines, the library's copy of it is the same words (the same
    text, but where the block has a blank line: see the next test), and the
    text handed over as the host wrote it is set on the same lines.
    """
    got = drawn["p28"]
    assert got["space_count"] >= 25
    assert got["wrong"] == []
    assert got["kept"] == ["a​​b﻿", "a​​b﻿"]


def test_p28_with_hard_breaks_a_blank_line_is_recorded_and_set_and_the_copy_has_one_line_end(
    drawn: dict[str, Any],
) -> None:
    """
    The one place `texts` and a copy still differ, and it is the library's:
    two line ends together are two lines on screen (an empty one between)
    and ONE newline in a copy. `texts` says what is on screen.
    """
    hard = drawn["p28"]["hard"]
    assert hard["texts"] == "a\nb\n\nc d"
    assert len(hard["lines"]) == 4 and hard["lines"][2][0] == hard["lines"][2][1]
    assert hard["copy"] == "a\nb\nc d"


def test_p28_a_markdown_string_is_described_as_ever_and_the_same_blocks_handed_over_as_set(
    drawn: dict[str, Any],
) -> None:
    """
    What is NOT changed, and still open: the reader writes two spaces where
    an image was left out and the library sets one, so for a markdown string
    `texts` has a space the screen has not. Blocks handed over are as set.
    """
    got = drawn["p28"]
    assert got["string"] == ["a  b", "a b"]
    assert got["blocks"] == ["a b", "a b"]
    seen, changed, copy = got["turning"]
    assert seen == ["a  b", "a b", "a  b"] and changed == [True, True, False] and copy == "a b"


def test_p29_a_tab_is_set_where_the_spaces_it_was_expanded_to_were(drawn: dict[str, Any]) -> None:
    """
    Fifteen awkward lines, four sizes, three overflows: every character
    after a tab at the same place as after `expandtabs(4)`, to a thousandth
    of a pixel, by caret and by drawn quad. And the comparison can fail:
    against eight columns it is four cells out.
    """
    got = drawn["p29"]
    assert len(got["worst"]) == 12
    assert max(got["worst"].values()) < 0.001, got["worst"]
    assert got["eight"] == pytest.approx(4 * got["cell"], abs=0.01) and got["cell"] > 5.0
    assert got["quads"] == [True] * 14 and got["quads_eight"] is False


def test_p29_a_recipe_copied_out_of_a_view_has_its_tabs(drawn: dict[str, Any]) -> None:
    recipe = drawn["p29"]["recipe"]
    assert recipe["texts"] == ["Build:", "all:\n\t$(CC) -o a\tb.c"]
    assert recipe["copy"] == "Build:\n\nall:\n\t$(CC) -o a\tb.c"
    assert recipe["stream_texts"] == recipe["texts"] and recipe["stream_copy"] == recipe["copy"]

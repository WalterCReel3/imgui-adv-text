"""
`imscribe.typesetter`: the gate around imtypeset, and a document as it wants one.

Three groups, and which of them run depends on the environment the suite was
started in (`make test`, or `make test TYPESET=1`):

1.  **The gate, without the library.** Each runs in a fresh interpreter whose
    environment has the two variables removed, so they hold in both runs.
2.  **The description.** Needs no library: the description is plain tuples.
    These run in both runs too. Until tranche 5 they described the old core's
    node material with `imscribe.typesetter.Converter`; that walk is deleted,
    and they describe markdown with `imscribe.typeset_markdown`, which is what
    every view does. The tests whose subject was the walk itself went with it
    (`.concerns/T5-B1--builder--result.md` names them).
3.  **The library.** Skipped, with the reason, when `IMTYPESET_LIBRARY` is not
    set. When it IS set and `module()` still answers `None`, that is a failure
    and not a skip: the caller asked for the library and did not get it.

Group 3 runs in a child interpreter with a Dear ImGui context of its own and
no window -- measured: a bare `imgui.create_context()` is enough for
`set_blocks`, layout and `draw_to_buffers` once the io announces
`renderer_has_textures` -- so the pytest process never loads the library and no
other test meets its context.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import material_frozen
import pytest
from conftest import HIDE_INSTALLED

from imscribe import typesetter
from imscribe.theme import Align, BlockKind, Theme
from imscribe.typeset_markdown import (
    MarkdownCode,
    MarkdownConverter,
    MarkdownRule,
    MarkdownTable,
    MarkdownText,
    parse_markdown,
)
from imscribe.typesetter import (
    BLOCK_TABLE_HEADER,
    KIND_CODE,
    KIND_HEADING,
    KIND_HOST,
    KIND_LIST_ITEM,
    KIND_PARAGRAPH,
    KIND_RULE,
    KIND_TABLE,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    BlockDescription,
    CellDescription,
    ColumnDescription,
    Description,
    RunDescription,
    _with_tags,
    cell_spans,
    table_text,
)

_ROOT = Path(__file__).resolve().parent.parent
_DEMOS = sorted((_ROOT / "demo").glob("*.md"))
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)


def _child(code: str, env: dict[str, str], *args: str) -> dict[str, Any]:
    """
    Run `code` in a fresh interpreter and read the one JSON object it prints last.
    """
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        # The second directory: a child that names a library that is not
        # there is not handed an installed imtypeset in its place
        # (`tests/conftest.py`, "An installed imtypeset is hidden").
        env={**env, "PYTHONPATH": os.pathsep.join([str(_ROOT), str(HIDE_INSTALLED)])},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return report


def _without() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name not in _VARIABLES}


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


def _described(
    source: str, theme: Theme, *, link_color: int = 0
) -> tuple[MarkdownConverter, Description]:
    """A markdown source described as the views describe it, formulas on, and its converter."""
    document = parse_markdown(source, theme, math=True)
    converter = MarkdownConverter(theme, link_color=link_color)
    return converter, converter.describe(document.blocks)


# ---------------------------------------------------------------------------
# 1. The gate, without the library
# ---------------------------------------------------------------------------

_GATE_CLOSED = """
import json, sys
import imscribe
from imscribe import typesetter
import imscribe.typesetter
loaded = typesetter.module()
fonts = typesetter.load_fonts()
try:
    typesetter.block_styles([])
    raised = ""
except RuntimeError as exc:
    raised = str(exc)
print(json.dumps({
    "module": loaded is None,
    "reason": typesetter.reason(),
    "load_fonts": fonts,
    "ready": typesetter.ready(),
    "raised": raised,
    "imtypeset": sorted(n for n in sys.modules if n == "imtypeset" or n.startswith("imtypeset.")),
    "imgui": "imgui_bundle" in sys.modules,
    "path": [p for p in sys.path if "imtypeset" in p],
}))
"""


def test_without_the_variable_nothing_of_imtypeset_is_imported() -> None:
    report = _child(_GATE_CLOSED, _without())
    assert report["module"] is True, "module() answered something with no library named"
    assert report["reason"] == typesetter.SWITCHED_OFF_REASON
    assert report["load_fonts"] is False and report["ready"] is False
    assert report["imtypeset"] == [], "something of imtypeset was imported"
    assert report["path"] == [], "sys.path was touched with no library named"
    # The module is the description too, and a description needs no ImGui.
    assert report["imgui"] is False, "importing imscribe.typesetter imported imgui_bundle"
    assert typesetter.SWITCHED_OFF_REASON in report["raised"]


def test_a_library_that_cannot_be_loaded_is_a_reason_and_not_an_exception(tmp_path: Path) -> None:
    """
    The variable names a file that is not a library. Whatever the import says
    -- no package on the path, or the package refusing the file -- it is kept
    as a sentence, `module()` is `None`, and nothing raises.
    """
    env = _without()
    env[typesetter.LIBRARY_VARIABLE] = str(tmp_path / "not-a-library.so")
    package = os.environ.get(typesetter.PACKAGE_VARIABLE)
    if package:
        env[typesetter.PACKAGE_VARIABLE] = package
    report = _child(_GATE_CLOSED, env)
    assert report["module"] is True
    assert report["reason"] and report["reason"] != typesetter.SWITCHED_OFF_REASON
    assert "Error" in report["reason"], report["reason"]
    assert report["load_fonts"] is False and report["ready"] is False
    assert report["reason"] in report["raised"]


def test_in_this_process_the_refusal_is_remembered_and_forgotten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    `module()` tries once. Without that a view asking every frame would
    re-run a failing import every frame.
    """
    monkeypatch.setenv(typesetter.LIBRARY_VARIABLE, str(tmp_path / "absent.so"))
    monkeypatch.delenv(typesetter.PACKAGE_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "imtypeset" not in p])
    monkeypatch.delitem(sys.modules, "imtypeset", raising=False)
    typesetter._forget()
    try:
        assert typesetter.module() is None
        first = typesetter.reason()
        assert "imtypeset" in first
        monkeypatch.setattr(
            typesetter.importlib, "import_module", lambda name: pytest.fail("imported twice")
        )
        assert typesetter.module() is None
        assert typesetter.reason() == first
        typesetter.disable("a view's draw raised")
        assert typesetter.reason() == "a view's draw raised"
        assert typesetter.module() is None and not typesetter.ready()
    finally:
        typesetter._forget()
    assert typesetter.reason() == typesetter.SWITCHED_OFF_REASON


# ---------------------------------------------------------------------------
# 2. The description
# ---------------------------------------------------------------------------


def _check_runs(block: BlockDescription) -> None:
    """
    What imtypeset.h requires of a block's runs: in bounds, ascending, not overlapping.
    """
    reached = 0
    for run in block.runs:
        assert 0 <= run.start < run.end <= len(block.text), (run, len(block.text))
        assert run.start >= reached, f"{run} starts before {reached}, where the last one ended"
        reached = run.end


def _tags(block: BlockDescription) -> list[int]:
    """
    The tag on each character of a block's text.
    """
    tags = [0] * len(block.text)
    for run in block.runs:
        for index in range(run.start, run.end):
            tags[index] = run.tag
    return tags


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: p.name)
def test_a_demo_document_is_described_block_for_block_and_nothing_misfits(
    path: Path, theme: Theme
) -> None:
    """
    The plan's check for step A1 reported only tables as misfits. A table is
    a block of the library's now (imtypeset `be40444`), so nothing misfits.

    Restated in tranche 5 on the path the views take. It used to describe
    the old core's blocks with `Converter` and check each text against
    `imscribe.spans.material_text`; both are deleted. The description is made
    from the markdown, held block for block to the blocks it was made from,
    and its texts to the ones the old converter gave (frozen), with the old
    math core's refusals handed in so that the comparison is of everything.
    """
    source = path.read_text(encoding="utf-8")
    document = parse_markdown(source, theme, math=True, refuses=material_frozen.refuses)
    converter = MarkdownConverter(theme)
    described = converter.describe(document.blocks)
    assert len(described.blocks) == len(document.blocks) == len(described.texts)
    assert not described.misfits, dict(described.misfits)
    tables = [i for i, block in enumerate(document.blocks) if isinstance(block, MarkdownTable)]
    assert described.tables == tables
    assert described.kinds["TableBlock"] == len(tables)
    assert described.texts == material_frozen.description(source).texts
    compared = 0
    for block, description, text in zip(
        document.blocks, described.blocks, described.texts, strict=True
    ):
        assert description.text == text
        assert 0 <= description.style < len(described.styles)
        _check_runs(description)
        if isinstance(block, MarkdownText):
            expected = {KIND_PARAGRAPH, KIND_HEADING, KIND_LIST_ITEM}
            assert description.kind in expected
            assert text == block.text
            compared += 1
        elif isinstance(block, MarkdownCode):
            assert description.kind == KIND_CODE
            assert text == block.text
            compared += 1
        elif isinstance(block, MarkdownTable):
            # One block: its text is its cells' with tabs and newlines
            # between, its runs are the cells' own, a column an alignment.
            assert description.kind == KIND_TABLE and description.runs == ()
            assert description.flags == (BLOCK_TABLE_HEADER if block.header else 0)
            rows = [block.header, *block.rows] if block.header else list(block.rows)
            assert text == table_text([cell.text for cell in row] for row in description.rows)
            assert len(description.columns) == len(block.aligns)
            assert all(column.width == 0.0 == column.share for column in description.columns)
            spans = cell_spans(description.rows)
            for row, described_row, row_spans in zip(rows, description.rows, spans, strict=True):
                for cell, one, (start, end) in zip(row, described_row, row_spans, strict=True):
                    assert text[start:end] == one.text == cell.text
                    _check_runs(BlockDescription(text=one.text, runs=one.runs))
                    compared += 1
        else:
            assert isinstance(block, MarkdownRule)
            assert description.kind == KIND_RULE and description.extent >= 1.0
    assert compared, "no block's text was compared with the block it was made from"


def test_a_table_is_one_block_of_rows_of_cells_with_their_runs_and_links(theme: Theme) -> None:
    """
    A table block's text is what a copy of the table gives, a tab between
    the cells of a row and a newline between rows, the header first; each
    cell has its own runs, indexing the CELL's text, with the link tags laid
    over them; and a cell's link is a row of `links` as a range of the
    BLOCK's text.
    """
    source = (
        "| name | where |\n|:--|--:|\n| **bold** one | [a link](https://t.example) |\n"
        "| $x^2$ |\n\nAfter [it](https://after.example).\n"
    )
    document = parse_markdown(source, theme, math=True)
    converter, described = _described(source, theme, link_color=7)
    table, after = described.blocks
    assert table.kind == KIND_TABLE and table.runs == () and table.flags == BLOCK_TABLE_HEADER
    assert table.text == "name\twhere\nbold one\ta link\nx^2\t" == described.texts[0]
    assert described.tables == [0] and not described.misfits
    assert table.columns == (
        ColumnDescription(typesetter.ALIGN[Align.LEFT]),
        ColumnDescription(typesetter.ALIGN[Align.RIGHT]),
    )
    # In reading order: the table's link has the first tag.
    assert [(row.block, row.tag, row.target) for row in described.links] == [
        (0, 1, "https://t.example"),
        (1, 2, "https://after.example"),
    ]
    in_table = described.links[0]
    assert table.text[in_table.start : in_table.end] == "a link"
    header, (first, second), (formula, empty) = table.rows
    assert [cell.text for cell in header] == ["name", "where"]
    assert first.text == "bold one"
    (bold,) = [run for run in first.runs if run.face]
    assert first.text[bold.start : bold.end].strip() == "bold"
    (link,) = second.runs
    assert (link.start, link.end, link.color, link.tag) == (0, 6, 7, 1)
    assert converter.link_target(link.tag) == "https://t.example"
    (run,) = formula.runs
    assert formula.text == "x^2" and run.flags == RUN_FORMULA
    # A short row is padded by the parser: every row has the header's cells.
    assert empty == CellDescription("")
    assert cell_spans(table.rows) == [[(0, 4), (5, 10)], [(11, 19), (20, 26)], [(27, 30), (31, 31)]]
    # Described again, the same block and the same tags.
    assert converter.describe(document.blocks).blocks == described.blocks


def test_what_the_demos_hold_is_what_the_plan_counted(theme: Theme) -> None:
    """
    9 tables and 129 cells over `demo/*.md`, as plan section 2.2 has it, and
    the formulas and links that make the walk worth checking are really there.
    """
    total: dict[str, int] = {}
    for path in _DEMOS:
        _, described = _described(path.read_text(encoding="utf-8"), theme)
        for counter in (described.misfits, described.kinds):
            for name, count in counter.items():
                total[name] = total.get(name, 0) + count
    assert total["TableBlock"] == 9
    assert total["table cells"] == 129
    assert total["formulas set (an explicit Formula run)"] > 0
    assert total["links (Run.tag into a host table)"] > 0
    assert total["list markers"] > 0


def test_a_formula_is_an_explicit_run_holding_its_source(theme: Theme) -> None:
    _, described = _described("Mass is $E = mc^2$ here.\n\n$$\\frac{a}{b}$$\n", theme)
    inline, display = described.blocks
    (run,) = inline.runs
    assert inline.text[run.start : run.end] == "E = mc^2" and run.flags == RUN_FORMULA
    assert "$" not in inline.text
    (run,) = display.runs
    assert display.text[run.start : run.end] == "\\frac{a}{b}"
    assert run.flags == RUN_DISPLAY_FORMULA


def test_a_hard_break_is_a_newline_and_the_block_says_so(theme: Theme) -> None:
    _, described = _described("one two\\\nthree four\n\nplain\n", theme)
    broken, plain = described.blocks
    assert broken.text == "one two\nthree four"
    assert broken.flags == typesetter.BLOCK_HARD_BREAKS
    assert plain.flags == 0


def test_kinds_markers_levels_and_quotes(theme: Theme) -> None:
    source = "## Two\n\n- item\n\n12. twelfth\n\n> quoted\n\n---\n\n```py\nx = 1\n  y\n```\n"
    _, described = _described(source, theme)
    heading, bullet, ordered, quote, rule, code = described.blocks
    assert (heading.kind, heading.level, heading.text) == (KIND_HEADING, 2, "Two")
    assert bullet.kind == KIND_LIST_ITEM and bullet.marker and bullet.text == "item"
    assert ordered.kind == KIND_LIST_ITEM and ordered.marker == "12."
    assert ordered.left_indent > 0
    assert quote.kind == KIND_PARAGRAPH and quote.quote_depth == 1
    assert rule.kind == KIND_RULE
    assert code.kind == KIND_CODE and code.text == "x = 1\n  y" and code.runs == ()
    # One style for one BlockStyle: the two list items share theirs.
    assert bullet.style == ordered.style != heading.style
    code_style = described.styles[code.style]
    assert code_style.Face == typesetter.FACE_ROLE[theme.faces.code]


@pytest.mark.parametrize(
    ("source", "linked"),
    [
        ("see [a link](u) and then **bold**", "a link"),
        ("[**bold**](u) after", "bold"),
        ("[`code`](u)", "code"),
        ("[text with *one* italic word](u) and more", "text with one italic word"),
        ("before **bold [inside](u) bold** after", "inside"),
        ("a [link with $x^2$ in it](u).", "link with x^2 in it"),
    ],
)
def test_a_link_keeps_its_tag_whatever_it_is_set_in(source: str, linked: str, theme: Theme) -> None:
    """
    The spike dropped the tag of any link that overlapped a styled run, and
    appended link runs after the styled ones, out of order. The library takes
    one run for a character, in ascending order.
    """
    converter, described = _described(source, theme)
    (block,) = described.blocks
    _check_runs(block)
    (row,) = described.links
    assert block.text[row.start : row.end] == linked
    assert converter.link_target(row.tag) == "u"
    tags = _tags(block)
    assert tags == [row.tag if row.start <= i < row.end else 0 for i in range(len(tags))]
    # The styling under the link is still there: something in the block is
    # set in another face, or is a formula, unless the source has neither.
    if "*" in source or "`" in source or "$" in source:
        assert any(run.face or run.flags for run in block.runs)
    for run in block.runs:
        if run.flags & RUN_FORMULA:
            assert block.text[run.start : run.end] == "x^2", "a formula's run was cut"


def test_with_tags_cuts_runs_at_link_edges_and_nowhere_else() -> None:
    bold = RunDescription(2, 8, face=2)
    formula = RunDescription(10, 14, flags=RUN_FORMULA)
    merged = _with_tags([bold, formula], [(0, 4, 1), (6, 12, 2)], color=7)
    assert merged == [
        RunDescription(0, 2, color=7, tag=1),
        RunDescription(2, 4, face=2, color=7, tag=1),
        RunDescription(4, 6, face=2),
        RunDescription(6, 8, face=2, color=7, tag=2),
        RunDescription(8, 10, color=7, tag=2),
        # Kept whole, tagged by the link at its start, and not coloured.
        RunDescription(10, 14, flags=RUN_FORMULA, tag=2),
    ]
    # Two links claiming a character: the earlier keeps it.
    assert _with_tags([], [(0, 5, 1), (3, 9, 2)], color=0) == [
        RunDescription(0, 5, tag=1),
        RunDescription(5, 9, tag=2),
    ]


def test_a_tag_means_the_same_url_after_the_tail_is_described_again(theme: Theme) -> None:
    """
    A stream re-describes from the first changed block. The spike numbered
    tags from 1 in each call, so a tag in the new tail named a row of the
    kept head. Here the converter owns the table.
    """
    source = "First [one](https://one.example).\n\nThen [two](https://two.example).\n"
    document = parse_markdown(source, theme)
    converter = MarkdownConverter(theme)
    whole = converter.describe(document.blocks)
    styles = len(converter.styles)
    tail = converter.describe(document.blocks[1:], base=1)
    (row,) = tail.links
    assert row.block == 1
    assert converter.link_target(row.tag) == "https://two.example"
    assert row == whole.links[1]
    assert converter.link_target(whole.links[0].tag) == "https://one.example"
    assert converter.link_target(0) is None and converter.link_target(99) is None
    # And a style index once given is not given again: nothing was added.
    assert len(converter.styles) == styles
    assert tail.blocks[0] == whole.blocks[1]


def test_something_that_is_no_block_is_a_host_block_and_a_misfit(theme: Theme) -> None:
    described = MarkdownConverter(theme).describe([object()])
    (block,) = described.blocks
    assert block.kind == KIND_HOST and block.extent > 0
    assert described.misfits == {"block type object": 1}


def test_a_block_of_no_known_type_described_first_names_a_style_that_exists(theme: Theme) -> None:
    """
    It named style 0, and described first that was style 0 of an empty table:
    the library cuts a block whose style index names nothing. It names the
    paragraph's now, which is added for it and shared with a real paragraph.
    """
    converter = MarkdownConverter(theme)
    first = converter.describe([object()])
    assert len(first.styles) == 1 and first.blocks[0].style == 0
    assert first.styles[0].Face == typesetter.FACE_ROLE[theme.style(BlockKind.PARAGRAPH).font.face]
    document = parse_markdown("# Head\n\nA paragraph.\n", theme)
    described = MarkdownConverter(theme).describe([*document.blocks, object()])
    heading, paragraph, unknown = described.blocks
    assert unknown.style == paragraph.style != heading.style
    assert all(0 <= block.style < len(described.styles) for block in described.blocks)


# ---------------------------------------------------------------------------
# 3. The library
# ---------------------------------------------------------------------------

_WITH_LIBRARY = r"""
import json, sys
from pathlib import Path
from imscribe import description, typesetter

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)

from imgui_bundle import imgui
from imscribe.fontmetrics import Face
from imscribe.theme import Align, Theme
from imscribe.typeset_markdown import MarkdownConverter, parse_markdown

report = {"module": True, "host": ts.host_info().get("host"), "files": {}}
report["enumerators"] = [
    [typesetter.KIND_PARAGRAPH, int(ts.BlockKind.Paragraph)],
    [typesetter.KIND_HEADING, int(ts.BlockKind.Heading)],
    [typesetter.KIND_LIST_ITEM, int(ts.BlockKind.ListItem)],
    [typesetter.KIND_CODE, int(ts.BlockKind.Code)],
    [typesetter.KIND_RULE, int(ts.BlockKind.Rule)],
    [typesetter.KIND_HOST, int(ts.BlockKind.Host)],
    [typesetter.KIND_TABLE, int(ts.BlockKind.Table)],
    [typesetter.FACE_DEFAULT, int(ts.Face.Default)],
    [typesetter.FACE_ROLE[Face.PROSE], int(ts.Face.Regular)],
    [typesetter.FACE_ROLE[Face.PROSE_BOLD], int(ts.Face.Bold)],
    [typesetter.FACE_ROLE[Face.PROSE_ITALIC], int(ts.Face.Italic)],
    [typesetter.FACE_ROLE[Face.PROSE_BOLD_ITALIC], int(ts.Face.BoldItalic)],
    [typesetter.FACE_ROLE[Face.CODE], int(ts.Face.Code)],
    [typesetter.FACE_ROLE[Face.CODE_BOLD], int(ts.Face.CodeBold)],
    [typesetter.FACE_ROLE[Face.MATH], int(ts.Face.Math)],
    [typesetter.ALIGN[Align.JUSTIFY], int(ts.Align.Justify)],
    [typesetter.ALIGN[Align.LEFT], int(ts.Align.Left)],
    [typesetter.ALIGN[Align.CENTER], int(ts.Align.Center)],
    [typesetter.ALIGN[Align.RIGHT], int(ts.Align.Right)],
    [typesetter.RUN_NO_BREAK, int(ts.RunFlags.NoBreak)],
    [typesetter.RUN_FORMULA, int(ts.RunFlags.Formula)],
    [typesetter.RUN_DISPLAY_FORMULA, int(ts.RunFlags.DisplayFormula)],
    [typesetter.BLOCK_HARD_BREAKS, int(ts.BlockFlags.HardBreaks)],
    [description.BLOCK_MATH, int(ts.BlockFlags.Math)],
    [description.BLOCK_FIXED_LINE_HEIGHT, int(ts.BlockFlags.FixedLineHeight)],
    [typesetter.BLOCK_TABLE_HEADER, int(ts.BlockFlags.TableHeader)],
    [description.BLOCK_TABLE_HELD, int(ts.BlockFlags.TableHeld)],
]
# Every member the library's two enums of a block have is one of the above:
# a new enumerator over there turns this red rather than passing unseen.
report["kinds_and_flags"] = [
    sorted(int(kind) for kind in ts.BlockKind),
    sorted(int(flag) for flag in ts.BlockFlags if int(flag)),
]
report["fields"] = [
    list(typesetter.BlockDescription._fields) == list(ts.Block._fields),
    list(typesetter.RunDescription._fields) == list(ts.Run._fields),
    all(hasattr(ts.BlockStyle, name) for name in typesetter.StyleDescription._fields),
    list(description.CellDescription._fields) == list(ts.Cell._fields),
    list(description.ColumnDescription._fields) == list(ts.TableColumn._fields),
    description.ColumnDescription() == tuple(ts.TableColumn()),
]
# The text the package makes of a table's rows is `table_text` of them.
rows = [["a", description.CellDescription("b c")], [], ["", "d"], ["e"]]
joined, _, _ = ts._table_rows(rows)
report["table_text"] = joined == description.table_text(
    [cell if isinstance(cell, str) else cell.text for cell in row] for row in rows
)

report["load_fonts_with_no_imgui_context"] = typesetter.load_fonts()
context = imgui.create_context()
# No renderer here. The library draws only where the backend says it can take
# textures as glyphs are baked; for draw_to_buffers saying so is enough.
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
report["fonts"] = [ts.get_font(role) is not None for role in typesetter.FACE_ROLE.values()]

theme = Theme.build()
for path in sorted(Path(sys.argv[1]).glob("*.md")):
    document = parse_markdown(path.read_text(encoding="utf-8"), theme, math=True)
    described = MarkdownConverter(theme).describe(document.blocks)
    doc = ts.Document()
    whole = doc.set_blocks(described.blocks, typesetter.block_styles(described.styles))
    edit = doc.edit_error.code
    laid = doc.layout(600.0, typesetter.base_style(theme, 0xFFFFFFFF))
    everything = doc.layout_window(0.0, 1.0e9)
    vertices, _ = doc.draw_to_buffers((0.0, 0.0), (0.0, 0.0, 600.0, 1.0e9))
    errors = [[i, doc.block_error(i).code, doc.block_error(i).message] for i in range(len(doc))]
    report["files"][path.name] = {
        "blocks": len(document.blocks),
        "document_blocks": len(doc),
        "styles": [len(described.styles), doc.style_count],
        "set_blocks": whole,
        "edit_error": edit,
        "layout": laid,
        "layout_window": everything,
        "height": doc.size()[1],
        "block_errors": [row for row in errors if row[1]],
        "laid_out": doc.stats().BlocksLaidOut,
        "vertex_bytes": len(vertices),
        "texts": [
            doc.range_text(((i, 0), (i, len(text)))) == text
            for i, text in enumerate(described.texts)
        ],
    }
    doc.close()

# A link's tag comes back from a hit test: the round trip the view depends on.
converter = MarkdownConverter(theme)
source = "Plain words, then [**a bold link**](https://example.org) and a tail."
described = converter.describe(parse_markdown(source, theme).blocks)
doc = ts.Document.from_blocks(described.blocks, typesetter.block_styles(described.styles))
report["link_edit_error"] = doc.edit_error.code
doc.layout(2000.0, typesetter.base_style(theme))
doc.layout_window(0.0, 1.0e9)
row = described.links[0]
hits = []
for offset in (row.start + 2, 2):
    x0, y0, x1, y1 = doc.caret_rect((0, offset))
    x2 = doc.caret_rect((0, offset + 1))[0]
    # A quarter of the way into the character: nearer its own caret than the next.
    hit = doc.hit_test((x0 + (x2 - x0) / 4.0, (y0 + y1) / 2.0))
    hits.append([hit.tag, converter.link_target(hit.tag), hit.position.offset - offset])
report["hits"] = hits
doc.close()

# The context goes with the ImGui context, and a second one can be made.
typesetter.unload()
report["ready_after_unload"] = typesetter.ready()
imgui.destroy_context(context)
context = imgui.create_context()
report["second_load"] = typesetter.load_fonts()
doc = ts.Document.from_blocks(described.blocks, typesetter.block_styles(described.styles))
doc.layout(300.0, typesetter.base_style(theme))
doc.layout_window(0.0, 1.0e9)
report["second_height"] = doc.size()[1]
report["second_block_errors"] = [doc.block_error(i).code for i in range(len(doc))]
typesetter.unload()
try:
    doc.size()
    report["closed_by_unload"] = False
except ValueError:
    report["closed_by_unload"] = True
imgui.destroy_context(context)
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def library_report() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    pytest.importorskip("imgui_bundle")
    report = _child(_WITH_LIBRARY, dict(os.environ), str(_ROOT / "demo"))
    assert (
        report["module"] is True
    ), "IMTYPESET_LIBRARY is set and imtypeset is not in use: " + report.get("reason", "")
    return report


def test_the_integers_here_are_the_librarys_enumerators(library_report: dict[str, Any]) -> None:
    assert library_report["host"] == "imgui_bundle"
    for ours, theirs in library_report["enumerators"]:
        assert ours == theirs
    assert len(library_report["enumerators"]) == 27
    assert library_report["kinds_and_flags"] == [[0, 1, 2, 3, 4, 5, 6], [1, 4, 8, 16, 32]]
    assert library_report["fields"] == [True] * 6
    assert library_report["table_text"] is True


def test_load_fonts_gives_every_role_a_font_and_needs_an_imgui_context(
    library_report: dict[str, Any],
) -> None:
    assert library_report["load_fonts_with_no_imgui_context"] is False
    assert library_report["load_fonts"] is True
    assert library_report["ready"] is True and library_report["reason"] == ""
    assert library_report["fonts"] == [True] * 7


def test_a_document_accepts_every_demo_description_whole(library_report: dict[str, Any]) -> None:
    """
    `set_blocks` answering False is the library saying it CUT something (a run
    out of order, a style index naming nothing) and raising nothing, so True
    is asserted and so is a clean `edit_error`. A block the library laid out
    with something wrong -- no font, a formula it refused -- is in
    `block_errors`; there is none, which for the formulas means the library
    set every one the demos hold.
    """
    files = library_report["files"]
    assert sorted(files) == [path.name for path in _DEMOS]
    for name, got in files.items():
        assert got["set_blocks"] is True and got["edit_error"] == 0, (name, got)
        assert got["document_blocks"] == got["blocks"] > 0, name
        assert got["styles"][0] == got["styles"][1] > 0, name
        assert got["layout"] is True and got["layout_window"] is True, name
        assert got["block_errors"] == [], (name, got["block_errors"])
        assert got["laid_out"] == got["blocks"], name
        assert got["height"] > 0, name
        assert got["vertex_bytes"] > 0, f"{name}: nothing was drawn"
        # Each block's text comes back as it was described: the offsets a
        # host computes in `Description.texts` are offsets in the document.
        assert all(got["texts"]), (name, [i for i, same in enumerate(got["texts"]) if not same])


def test_a_hit_on_a_link_answers_the_tag_the_converter_resolves(
    library_report: dict[str, Any],
) -> None:
    assert library_report["link_edit_error"] == 0
    on_link, off_link = library_report["hits"]
    assert on_link[0] > 0 and on_link[1] == "https://example.org"
    assert off_link[:2] == [0, None]
    # Both hits landed on the character aimed at, so the tag read is that
    # character's and not a neighbour's.
    assert on_link[2] == 0 and off_link[2] == 0


def test_unload_closes_the_documents_and_a_second_context_loads(
    library_report: dict[str, Any],
) -> None:
    assert library_report["ready_after_unload"] is False
    assert library_report["second_load"] is True
    assert library_report["second_height"] > 0
    assert library_report["second_block_errors"] == [0]
    assert library_report["closed_by_unload"] is True


_CONTEXTS = r"""
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)
report = {"module": True}

def context():
    made = imgui.create_context()
    imgui.set_current_context(made)
    io = imgui.get_io()
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.display_size = (800.0, 600.0)
    io.delta_time = 1.0 / 60.0
    io.set_ini_filename("")
    return made

def sets_text():
    doc = ts.Document.from_blocks([ts.Block(text="Some words to set.")], [ts.BlockStyle()])
    doc.layout(300.0, ts.Style(EmSize=16.0))
    doc.layout_window(0.0, 1.0e9)
    answer = [doc.size()[1] > 0, doc.block_error(0).code]
    return doc, answer

try:
    typesetter.window_draw_list()
    report["draw_list_before_load"] = "answered"
except RuntimeError:
    report["draw_list_before_load"] = "RuntimeError"

# 1. A second ImGui context while the first is alive, and no unload() between.
first = context()
report["first_load"] = typesetter.load_fonts()
serial = ts.get_context_serial()
kept, _ = sets_text()
second = context()
report["second_load"] = typesetter.load_fonts()
report["second_ready"] = typesetter.ready()
report["second_reason"] = typesetter.reason()
report["second_is_new"] = ts.get_context_serial() != serial
report["second_fonts"] = [ts.get_font(role) is not None for role in typesetter.FACE_ROLE.values()]
doc, report["second_sets"] = sets_text()
try:
    kept.size()
    report["kept_document_closed"] = False
except ValueError:
    report["kept_document_closed"] = True

# 2. What a draw list of None is: the current window's.
frames = []
size = ts.build_info().sizeof_imdrawvert
for _ in range(2):
    imgui.new_frame()
    imgui.set_next_window_pos((0.0, 0.0))
    imgui.set_next_window_size((400.0, 400.0))
    imgui.begin("probe")
    native = imgui.get_window_draw_list()
    x, y = imgui.get_cursor_screen_pos()
    before = native.vtx_buffer.size()
    address = typesetter.window_draw_list()
    drew = doc.draw(address, (x, y))
    gained = native.vtx_buffer.size() - before
    low, high = native.get_clip_rect_min(), native.get_clip_rect_max()
    vertices, _ = doc.draw_to_buffers((x, y), (low.x, low.y, high.x, high.y))
    imgui.end()
    imgui.end_frame()
    imgui.render()
    frames.append([address, drew, gained, len(vertices) // size])
report["frames"] = frames
doc.close()

# 3. The first ImGui context destroyed first, and again no unload() between.
imgui.destroy_context(second)
imgui.set_current_context(first)
report["back_on_first"] = typesetter.load_fonts()
imgui.destroy_context(first)
third = context()
report["third_load"] = typesetter.load_fonts()
report["third_ready"] = typesetter.ready()
doc, report["third_sets"] = sets_text()

# 4. disable() releases nothing; unload() after it still destroys the context.
typesetter.disable("a view's draw raised")
report["disabled"] = [typesetter.module() is None, typesetter.ready(), typesetter.reason()]
report["context_after_disable"] = ts.current_context() is not None
typesetter.unload()
report["context_after_unload"] = ts.current_context() is not None
try:
    doc.size()
    report["closed_by_unload_after_disable"] = False
except ValueError:
    report["closed_by_unload_after_disable"] = True
report["load_after_disable"] = typesetter.load_fonts()
imgui.destroy_context(third)
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def contexts_report() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: run `make test TYPESET=1`")
    pytest.importorskip("imgui_bundle")
    report = _child(_CONTEXTS, dict(os.environ))
    assert (
        report["module"] is True
    ), "IMTYPESET_LIBRARY is set and imtypeset is not in use: " + report.get("reason", "")
    return report


def test_load_fonts_in_a_second_imgui_context_without_unload_leaves_it_ready(
    contexts_report: dict[str, Any],
) -> None:
    """
    The stale-context case nobody had run. `load_fonts` reused the context it
    found; with the first Dear ImGui context still alive and a second one
    current, `add_font` was refused ("the ImGui context this ImTypeset
    context was created in is not the current one") and the library was
    switched off for the process. It makes a new context every time now, the
    imtypeset team's rule (`advtext-swap-status.md`, answer (c)).

    Both orders: the first ImGui context kept, and destroyed first. The
    second passed before the change too, on this machine, because the new
    ImGui context was given the old one's address; it is here so that it
    goes on passing where the allocator does otherwise.
    """
    report = contexts_report
    assert report["first_load"] is True
    assert report["second_load"] is True and report["second_ready"] is True
    assert report["second_reason"] == ""
    assert report["second_is_new"] is True, "the context of the first ImGui context was reused"
    assert report["second_fonts"] == [True] * 7
    assert report["second_sets"] == [True, 0]
    # What it costs, as after unload(): a document of the old context is closed.
    assert report["kept_document_closed"] is True
    assert report["back_on_first"] is True
    assert report["third_load"] is True and report["third_ready"] is True
    assert report["third_sets"] == [True, 0]


def test_no_draw_list_is_the_current_windows_and_no_symbol_is_looked_up(
    contexts_report: dict[str, Any],
) -> None:
    """
    `window_draw_list()` found Dear ImGui's `GetWindowDrawList` by its mangled
    name in the wheel's binary. `Document.draw(None, pos)` needs no address:
    what it puts in the window's own draw list is what `draw_to_buffers`
    emits for the same clip rectangle, vertex for vertex in number.
    """
    assert contexts_report["draw_list_before_load"] == "RuntimeError"
    for address, drew, gained, expected in contexts_report["frames"]:
        assert address is None and drew is True
        assert gained == expected > 0
    assert not hasattr(typesetter, "_window_draw_list")
    assert "ctypes" not in vars(typesetter)


def test_unload_after_disable_still_destroys_the_context(contexts_report: dict[str, Any]) -> None:
    """
    `disable` dropped the package and `unload` returned at once when there was
    none, so a library switched off mid-run kept its context and its fonts
    until the process ended. `disable` still releases nothing itself -- it is
    called from inside a draw -- and `unload` does.
    """
    report = contexts_report
    assert report["disabled"] == [True, False, "a view's draw raised"]
    assert report["context_after_disable"] is True
    assert report["context_after_unload"] is False
    assert report["closed_by_unload_after_disable"] is True
    # Nothing re-enables it.
    assert report["load_after_disable"] is False


def test_importing_the_module_loads_the_description_and_nothing_else_of_imscribe() -> None:
    """
    The gate, the description types and `block_styles` need no layout core.
    (The material walk that did, `Converter`, is deleted.)
    (`tests/test_typeset_closure.py` holds the layer's closures; this is the
    module's own, with the moment the rest arrives.)
    """
    code = """
import json, sys
def loaded():
    return sorted(n for n in sys.modules if n.startswith("imscribe."))
import imscribe.typesetter as typesetter
at_import = loaded()
typesetter.block_styles
described = typesetter.BlockDescription(text="x")
after_types = loaded()
roles = typesetter.FACE_ROLE
after_roles = loaded()
aligns = typesetter.ALIGN
from imscribe.theme import Theme
print(json.dumps({"at_import": at_import, "after_types": after_types, "after_roles": after_roles,
                  "roles": sorted(roles.values()), "aligns": sorted(aligns.values()),
                  "same": typesetter.FACE_ROLE is roles and typesetter.ALIGN is aligns}))
"""
    report = _child(code, _without())
    assert report["at_import"] == ["imscribe.description", "imscribe.typesetter"]
    assert report["after_types"] == report["at_import"]
    assert report["after_roles"] == [
        "imscribe.description",
        "imscribe.primitives",
        "imscribe.typesetter",
    ]
    assert report["roles"] == [1, 2, 3, 4, 5, 6, 7] and report["aligns"] == [0, 1, 2, 3]
    assert report["same"] is True

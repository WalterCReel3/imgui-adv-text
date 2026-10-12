"""
`advtext.typeset_find`: find over a document described for imtypeset.

Two groups, as in `tests/test_typeset.py`:

1.  **The index, the marks and the `Finder`.** No library: descriptions are
    plain tuples and so are the marks. These run in every run of the suite.
2.  **The library.** Skipped, with the reason, when `IMTYPESET_LIBRARY` is not
    set; a failure, not a skip, when it is set and imtypeset is not in use.
    Runs in a child interpreter with a Dear ImGui context of its own and no
    window, so the pytest process never loads the library.
"""

from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import material_frozen
import pytest

from advtext import typesetter
from advtext.description import cell_spans
from advtext.theme import Theme
from advtext.typeset_find import (
    CURRENT_COLOR,
    HIT_COLOR,
    MARK_BEHIND,
    Finder,
    FindIndex,
    MarkDescription,
    Match,
    marks_for,
)
from advtext.typeset_markdown import describe_markdown
from advtext.typesetter import (
    KIND_CODE,
    KIND_HOST,
    KIND_TABLE,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    BlockDescription,
    Description,
    RunDescription,
)

_ROOT = Path(__file__).resolve().parent.parent
_DEMOS = sorted((_ROOT / "demo").glob("*.md"))
_NEEDLES = ("glue", "the", "e", "a b", " ", "TeX", "of the", "1", "\\", "é", "Glue\nand", "zzzz")


@pytest.fixture(scope="module")
def theme() -> Theme:
    return Theme.build()


def _described(source: str, theme: Theme) -> Description:
    """
    A markdown source as the views describe it: `advtext.typeset_markdown`, formulas on.

    Until tranche 5 this was the old core's blocks walked by
    `advtext.typesetter.Converter`. The tests that use it name short sources
    for which the two said the same thing; the demos, where the old path's
    answer is the oracle, are read from the frozen file (`_frozen`).
    """
    return describe_markdown(source, theme, math=True)


def _frozen(path: Path) -> Description:
    """What the old core's material path described a demo as (`tests/material_frozen.py`)."""
    return material_frozen.description(path.read_text(encoding="utf-8"))


def _naive(blocks: list[BlockDescription], needle: str, ignore_case: bool) -> list[Match]:
    """
    The search written another way: formula source blanked out, then a regular expression.

    U+0000 stands where a formula's source was: no needle here holds one, the
    text keeps its length, and so every offset is the block's own. A Host
    block is not searched. A table's text is its cells with ONE character
    between each two (a tab or a newline), so U+0000 stands there too and no
    needle matches across two cells.
    """
    found: list[Match] = []
    for number, block in enumerate(blocks):
        if block.kind == KIND_HOST:
            continue
        runs = list(block.runs)
        if block.kind == KIND_TABLE:
            cells = [cell for row in block.rows for cell in row]
            characters = list("\0".join(cell.text for cell in cells))
            assert len(characters) == len(block.text)
            at = 0
            for cell in cells:
                runs += [run._replace(start=run.start + at, end=run.end + at) for run in cell.runs]
                at += len(cell.text) + 1
        else:
            characters = list(block.text)
        for run in runs:
            if run.flags & (RUN_FORMULA | RUN_DISPLAY_FORMULA):
                characters[run.start : run.end] = "\0" * (run.end - run.start)
        prose = block.kind != KIND_CODE
        wanted = needle.replace("\n", " ") if prose else needle
        for piece in re.finditer("[^\0]+", "".join(characters)):
            haystack = piece.group().replace("\n", " ") if prose else piece.group()
            folded = haystack.casefold()
            pattern = wanted
            if ignore_case and len(folded) == len(haystack):
                haystack, pattern = folded, wanted.casefold()
            for hit in re.finditer(re.escape(pattern), haystack):
                found.append(Match(number, piece.start() + hit.start(), piece.start() + hit.end()))
    return found


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _DEMOS, ids=lambda path: path.name)
@pytest.mark.parametrize("ignore_case", [False, True])
@pytest.mark.parametrize("how", ["direct", "material"])
def test_matches_over_a_demo_document_equal_a_naive_search(
    path: Path, ignore_case: bool, how: str, theme: Theme
) -> None:
    """
    Over the description the views make of the demo (`direct`), and over the
    one the old core's material path made of it (`material`, frozen), which
    is the input this test had until tranche 5.
    """
    if how == "direct":
        described = _described(path.read_text(encoding="utf-8"), theme)
    else:
        described = _frozen(path)
    index = FindIndex.of(described.blocks)
    assert index.blocks == len(described.blocks)
    total = 0
    for needle in _NEEDLES:
        matches = index.find(needle, ignore_case=ignore_case)
        assert list(matches) == _naive(described.blocks, needle, ignore_case), needle
        for match in matches:
            # What a match names IS the needle, in the text the document is given.
            text = described.texts[match.block][match.start : match.end]
            wanted = needle
            if described.blocks[match.block].kind != KIND_CODE:
                text, wanted = text.replace("\n", " "), wanted.replace("\n", " ")
            assert text == wanted or (ignore_case and text.casefold() == wanted.casefold())
            if described.blocks[match.block].kind == KIND_TABLE:
                # Inside ONE cell: no match holds the tab or the newline between two.
                spans = [s for row in cell_spans(described.blocks[match.block].rows) for s in row]
                assert any(start <= match.start and match.end <= end for start, end in spans)
        total += len(matches)
    assert total > 0, "no needle found anything: the comparison compared nothing"


@pytest.mark.parametrize("path", _DEMOS, ids=lambda path: path.name)
def test_it_finds_in_each_block_what_the_material_index_finds_table_cells_included(
    path: Path, theme: Theme
) -> None:
    """
    Block by block, as many matches as `advtext.spans.FindIndex` found, a table's cells included.

    Counts and not offsets: that index answered material indices, this one
    `str` indices. A needle of one word cannot run across a formula's box, so
    the one rule that differs (the module's docstring) does not come into it.

    `advtext.spans` is deleted (tranche 5). What its index found in the old
    core's blocks of each demo is frozen, by block, and this index is run
    over the description the old converter made of those same blocks.
    """
    described = _frozen(path)
    here = FindIndex.of(described.blocks)
    there = material_frozen.demo(path.name)["find"]
    compared = in_cells = 0
    for needle in ("glue", "the", "e", " ", "TeX", "of the", "1", "\\", "x"):
        for ignore_case in (False, True):
            mine = collections.Counter(m.block for m in here.find(needle, ignore_case=ignore_case))
            theirs = collections.Counter(
                {block: count for block, count in there[f"{int(ignore_case)}|{needle}"]}
            )
            assert mine == theirs, (needle, ignore_case)
            compared += sum(mine.values())
            in_cells += sum(count for block, count in mine.items() if block in described.tables)
    assert compared > 0
    if described.tables:
        assert in_cells > 0, "the document has a table and no needle was found in one"


def test_an_empty_needle_finds_nothing_and_matches_do_not_overlap() -> None:
    index = FindIndex.of([BlockDescription(text="aaaaa")])
    assert index.find("") == ()
    assert index.find("aa") == (Match(0, 0, 2), Match(0, 2, 4))


def test_case_is_folded_and_a_stretch_whose_folding_changes_length_is_searched_as_it_stands() -> (
    None
):
    """
    `advtext.spans.FindIndex`'s rule. `lower()`, which the spike used, shifts later offsets.
    """
    plain = "Glue and GLUE"
    sharp = "Straße, then Glue and GLUE"  # casefold() makes the sharp s two letters
    dotted = "İstanbul, then Glue and GLUE"  # and the dotted capital I two code points
    assert len(sharp.casefold()) != len(sharp) and len(dotted.lower()) != len(dotted)
    index = FindIndex.of([BlockDescription(text=text) for text in (plain, sharp, dotted)])
    found = index.find("glue", ignore_case=True)
    # Folded where that is safe: both spellings. As it stands elsewhere: neither.
    assert found == (Match(0, 0, 4), Match(0, 9, 13))
    exact = index.find("Glue", ignore_case=True)
    texts = (plain, sharp, dotted)
    assert [(m.block, texts[m.block][m.start : m.end]) for m in exact] == [
        (0, "Glue"),
        (0, "GLUE"),
        (1, "Glue"),
        (2, "Glue"),
    ]
    assert exact[2] == Match(1, sharp.index("Glue"), sharp.index("Glue") + 4)
    assert exact[3] == Match(2, dotted.index("Glue"), dotted.index("Glue") + 4)
    assert index.find("glue") == ()


def test_a_space_matches_a_hard_break_in_prose_and_not_in_code(theme: Theme) -> None:
    described = _described("one two\\\nthree four\n\n```\none two\nthree four\n```\n", theme)
    prose, code = described.texts
    assert "two\nthree" in prose and "two\nthree" in code
    index = FindIndex.of(described.blocks)
    at = prose.index("two")
    assert index.find("two three") == (Match(0, at, at + 9),)
    at_code = code.index("two")
    assert index.find("two\nthree") == (Match(0, at, at + 9), Match(1, at_code, at_code + 9))


def test_a_formulas_source_is_not_searched_and_the_text_around_it_is(theme: Theme) -> None:
    described = _described("Let alpha be $\\alpha + x$ and x the rest.\n", theme)
    (block,) = described.blocks
    (formula,) = [run for run in block.runs if run.flags & RUN_FORMULA]
    assert "alpha" in block.text[formula.start : formula.end]
    index = FindIndex.of(described.blocks)
    assert index.find("alpha") == (Match(0, 4, 9),)
    after = block.text.index("x", formula.end)
    assert index.find("x") == (Match(0, after, after + 1),)
    # The one rule that differs from the material index: nothing matches across the formula.
    assert index.find("be  and") == ()
    assert index.find("be ") and index.find(" and")


def test_offsets_after_a_formula_are_the_blocks_own() -> None:
    text = "ab FORMULA cd ab"
    block = BlockDescription(text=text, runs=(RunDescription(3, 10, flags=RUN_DISPLAY_FORMULA),))
    index = FindIndex.of([block], base=7)
    assert index.find("ab") == (Match(7, 0, 2), Match(7, 14, 16))
    assert index.find("FORMULA") == ()
    assert index.find("ORM") == ()


def test_a_table_is_searched_cell_by_cell_at_offsets_into_its_text(theme: Theme) -> None:
    source = (
        "| head | ab |\n|---|---|\n| needle $needle$ | cd needle |\n| e | f |\n\n"
        "A needle outside.\n"
    )
    described = _described(source, theme)
    table = described.blocks[0]
    assert described.tables == [0] and table.kind == KIND_TABLE
    assert table.text == "head\tab\nneedle needle\tcd needle\ne\tf" == described.texts[0]
    index = FindIndex.of(described.blocks)
    assert index.blocks == 2
    here = index.find("needle")
    # The cell's own text, not its formula's source; then the next cell; then the paragraph.
    assert here == (Match(0, 8, 14), Match(0, 25, 31), Match(1, 2, 8))
    assert all(described.texts[m.block][m.start : m.end] == "needle" for m in here)
    # Where `advtext.spans.FindIndex` found it in the old core's blocks (frozen): the same
    # three places, as (block, (row, column)).
    assert material_frozen.needle_cells() == [(0, (1, 0)), (0, (1, 1)), (1, None)]
    assert [m.block for m in here] == [block for block, _ in material_frozen.needle_cells()]
    # Never across two cells: not across the tab of a row, not across a row's newline.
    assert index.find("ab needle") == () == index.find("head\tab")
    assert index.find("needle e") == () == index.find("needle\ne")
    assert index.find("ab\nneedle") == () == index.find("needle cd")
    # A cell is prose: a space in the needle is a space in the cell.
    assert index.find("cd needle") == (Match(0, 22, 31),)
    # The marks are ranges of the table's text, which is what the library takes.
    marks = marks_for(here, 1)
    assert [mark.range for mark in marks] == [
        ((0, 8), (0, 14)),
        ((1, 2), (1, 8)),
        ((0, 25), (0, 31)),
    ]


def test_a_host_block_is_counted_and_not_searched_whatever_it_holds() -> None:
    """
    A hosted widget's block, whatever it holds. A mark in one draws nothing, so a
    match there would be a match the reader cannot be shown.
    """
    blocks = [
        BlockDescription(text="one needle"),
        BlockDescription(kind=KIND_HOST, text="a needle\tin a host block", extent=10.0),
        BlockDescription(kind=KIND_CODE, text="needle = 1"),
    ]
    index = FindIndex.of(blocks, base=3)
    assert index.blocks == 3
    assert index.find("needle") == (Match(3, 4, 10), Match(5, 0, 6))


def test_marks_are_behind_each_match_with_the_current_one_last() -> None:
    matches = (Match(0, 1, 3), Match(0, 5, 7), Match(2, 0, 2))
    assert marks_for(()) == ()
    assert marks_for(matches) == tuple(
        MarkDescription(((m.block, m.start), (m.block, m.end)), HIT_COLOR, MARK_BEHIND)
        for m in matches
    )
    marks = marks_for(matches, 1, color=1, current_color=2)
    assert [(mark.range[0], mark.color) for mark in marks] == [
        ((0, 1), 1),
        ((2, 0), 1),
        ((0, 5), 2),
    ]
    assert all(mark.place == MARK_BEHIND for mark in marks)
    # Out of range is no current match, not an exception.
    assert marks_for(matches, 3) == marks_for(matches)


def test_the_limit_keeps_the_first_matches_and_always_the_current_one() -> None:
    matches = tuple(Match(0, n, n + 1) for n in range(10))
    assert [mark.range[0][1] for mark in marks_for(matches, limit=4)] == [0, 1, 2, 3]
    late = marks_for(matches, 8, limit=4)
    assert [mark.range[0][1] for mark in late] == [0, 1, 2, 8]
    assert late[-1].color == CURRENT_COLOR
    early = marks_for(matches, 1, limit=4)
    assert [mark.range[0][1] for mark in early] == [0, 2, 3, 1]
    assert marks_for(matches, 8, limit=0) == ()


class _Packer:
    """
    Stands where an `imtypeset.Document` would: counts `pack_marks` and keeps what it was given.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[MarkDescription, ...]] = []

    def pack_marks(self, marks: tuple[MarkDescription, ...]) -> object:
        self.calls.append(marks)
        return ("packed", len(self.calls))


def _index(*texts: str) -> FindIndex:
    return FindIndex.of([BlockDescription(text=text) for text in texts])


def test_the_finder_steps_through_the_matches_and_wraps() -> None:
    finder = Finder(_index("glue one", "no", "Glue two glue"))
    assert finder.match is None and finder.status() == "" and finder.next() is None
    assert finder.search("glue") == (Match(0, 0, 4), Match(2, 0, 4), Match(2, 9, 13))
    assert finder.ignore_case is True
    assert (finder.current, finder.match, finder.status()) == (0, Match(0, 0, 4), "1 of 3")
    assert finder.next() == Match(2, 0, 4)
    assert finder.next() == Match(2, 9, 13)
    assert finder.next() == Match(0, 0, 4)
    assert finder.previous() == Match(2, 9, 13)
    assert finder.status() == "3 of 3"
    assert finder.search("glue", ignore_case=False) == (Match(0, 0, 4), Match(2, 9, 13))
    assert finder.search("absent") == () and finder.match is None and finder.step(1) is None


def test_the_current_match_stays_near_where_it_was() -> None:
    finder = Finder(_index("glue", "glue and glued", "glue"))
    finder.search("glue")
    finder.step(2)
    assert finder.match == Match(1, 9, 13)
    # Another letter typed: the first match at or after where the current one began.
    finder.search("glued")
    assert finder.match == Match(1, 9, 14)
    # The document grew in front of it and behind it.
    finder.search("glue")
    assert finder.current == 2
    finder.set_index(_index("glue", "glue and glued", "glue", "glue"))
    assert finder.match == Match(1, 9, 13) and len(finder.matches) == 5
    # Nothing at or after it any more: the first.
    finder.set_index(_index("glue"))
    assert finder.match == Match(0, 0, 4)


def test_marks_are_packed_once_per_needle_document_or_current_match() -> None:
    document = _Packer()
    finder = Finder(_index("glue one", "glue two"))
    assert finder.packed(document) is None and document.calls == []
    finder.search("glue")
    first = finder.packed(document)
    for _frame in range(5):
        assert finder.packed(document) is first
    assert len(document.calls) == 1
    assert document.calls[0] == finder.marks() == marks_for(finder.matches, 0)

    revision = finder.revision
    finder.search("glue")  # the same needle: nothing changed
    assert finder.revision == revision and finder.packed(document) is first

    finder.next()
    assert finder.revision == revision + 1
    assert finder.packed(document) is not first and len(document.calls) == 2
    assert document.calls[1][-1] == MarkDescription(((1, 0), (1, 4)), CURRENT_COLOR, MARK_BEHIND)

    # An edit: a new index, even one that says the same, drops the pack.
    finder.set_index(_index("glue one", "glue two"))
    finder.packed(document)
    assert len(document.calls) == 3

    # Another document object is packed for itself.
    other = _Packer()
    finder.packed(other)
    assert len(other.calls) == 1 and len(document.calls) == 3

    finder.search("absent")
    assert finder.packed(document) is None and len(document.calls) == 3


def test_a_single_match_stepped_onto_itself_is_not_packed_again() -> None:
    document = _Packer()
    finder = Finder(_index("one glue"))
    finder.search("glue")
    finder.packed(document)
    assert finder.next() == Match(0, 4, 8)
    finder.packed(document)
    assert len(document.calls) == 1


_ALONE = """
import json, sys
import advtext.typeset_find
print(json.dumps(sorted(
    name for name in sys.modules
    if name == "imtypeset" or name.startswith(("imtypeset.", "advtext.ui", "imgui_bundle"))
)))
"""


def _child(code: str, env: dict[str, str], *args: str) -> Any:
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_module_imports_no_library_and_no_ui() -> None:
    """
    With the variables set or not: the search is pure Python, and so is importing it.
    """
    assert _child(_ALONE, dict(os.environ)) == []


# ---------------------------------------------------------------------------
# 2. The library
# ---------------------------------------------------------------------------

_WITH_LIBRARY = r"""
import json, sys
from pathlib import Path
from advtext import typesetter, typeset_find

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)

from imgui_bundle import imgui
from advtext.theme import Theme
from advtext.typeset_markdown import describe_markdown

report = {"module": True}
report["enumerators"] = [
    [typeset_find.MARK_INK, int(ts.MarkPlace.Ink)],
    [typeset_find.MARK_BEHIND, int(ts.MarkPlace.Behind)],
    [typeset_find.MARK_UNDER, int(ts.MarkPlace.Under)],
]
report["fields"] = list(typeset_find.MarkDescription._fields) == list(ts.Mark._fields)
report["defaults"] = list(typeset_find.MarkDescription(((0, 0), (0, 0)), 0)) == list(
    ts.Mark(((0, 0), (0, 0)), 0)
)

context = imgui.create_context()
imgui.get_io().backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["ready"] = typesetter.load_fonts() and typesetter.ready()
theme = Theme.build()
clip = (0.0, 0.0, 600.0, 1.0e9)


def document_of(source):
    described = describe_markdown(source, theme, math=True)
    doc = ts.Document()
    accepted = doc.set_blocks(described.blocks, typesetter.block_styles(described.styles))
    assert accepted is True and doc.edit_error.code == 0
    doc.layout(600.0, typesetter.base_style(theme, 0xFFFFFFFF))
    doc.layout_window(0.0, 1.0e9)
    return described, doc


# The unit. Characters of two, three and four UTF-8 bytes in front of a match:
# a mark takes str indices and the package makes them bytes.
described, doc = document_of(sys.argv[2])
text = described.texts[0]
finder = typeset_find.Finder(typeset_find.FindIndex.of(described.blocks))
matches = finder.search("glue", ignore_case=True)
packed = finder.packed(doc)
report["unit"] = {
    "text": text,
    "matches": [list(match) for match in matches],
    "count": packed.count,
    "marks": [list(mark.range[0]) + list(mark.range[1]) for mark in finder.marks()],
    "packed": [
        [r.Start.Block, r.Start.Offset, r.End.Block, r.End.Offset]
        for r in (slot.Range for slot in packed.array[: packed.count])
    ],
    "expected_bytes": [
        [m.range[0][0], len(text[: m.range[0][1]].encode("utf-8")),
         m.range[1][0], len(text[: m.range[1][1]].encode("utf-8"))]
        for m in finder.marks()
    ],
    "range_text": [doc.range_text(((m.block, m.start), (m.block, m.end))) for m in matches],
    "same_object": finder.packed(doc) is packed,
}
doc.close()

# A demo document: what every match names in the DOCUMENT is the needle, and
# the marks draw.
described, doc = document_of(Path(sys.argv[1]).read_text(encoding="utf-8"))
finder = typeset_find.Finder(typeset_find.FindIndex.of(described.blocks))
rows = {}
for needle in ("glue", "the", "TeX", "e"):
    matches = finder.search(needle, ignore_case=True)
    finder.step(len(matches) // 2)
    named = [doc.range_text(((m.block, m.start), (m.block, m.end))) for m in matches]
    bare, _ = doc.draw_to_buffers((0.0, 0.0), clip)
    with_packed, _ = doc.draw_to_buffers((0.0, 0.0), clip, marks=finder.packed(doc))
    with_tuples, _ = doc.draw_to_buffers((0.0, 0.0), clip, marks=finder.marks())
    rows[needle] = {
        "matches": len(matches),
        "marks": len(finder.marks()),
        "packed_count": finder.packed(doc).count,
        "wrong": [t for t in named if t.replace("\n", " ").casefold() != needle.casefold()][:5],
        "bare": len(bare),
        "packed": len(with_packed),
        "tuples": len(with_tuples),
        "same_bytes": with_packed == with_tuples,
    }
report["demo"] = rows
doc.close()
typesetter.unload()
imgui.destroy_context(context)
print(json.dumps(report))
"""

_MIXED = "Élan, a 10 € note and a 😀 before the glue, and GLUE after it.\n"


@pytest.fixture(scope="module")
def library_report() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(
            "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
            "for the tests that need the imtypeset library"
        )
    pytest.importorskip("imgui_bundle")
    report: dict[str, Any] = _child(
        _WITH_LIBRARY, dict(os.environ), str(_ROOT / "demo" / "sample.md"), _MIXED
    )
    assert (
        report["module"] is True
    ), "IMTYPESET_LIBRARY is set and imtypeset is not in use: " + report.get("reason", "")
    assert report["ready"] is True
    return report


def test_the_mark_here_is_the_librarys_mark(library_report: dict[str, Any]) -> None:
    for here, there in library_report["enumerators"]:
        assert here == there
    assert library_report["fields"] is True
    assert library_report["defaults"] is True


def test_a_mark_takes_str_indices_and_the_package_packs_bytes(
    library_report: dict[str, Any],
) -> None:
    unit = library_report["unit"]
    text = unit["text"]
    at, shout = text.index("glue"), text.index("GLUE")
    assert unit["matches"] == [[0, at, at + 4], [0, shout, shout + 4]]
    # The marks hold str indices, and the current match's is last.
    assert unit["marks"] == [[0, shout, 0, shout + 4], [0, at, 0, at + 4]]
    # What the library was handed is bytes, and they are other numbers here.
    assert unit["count"] == 2
    assert unit["packed"] == unit["expected_bytes"]
    assert unit["packed"] != unit["marks"]
    assert unit["packed"][1][1] == len(text[:at].encode("utf-8")) > at
    assert unit["range_text"] == ["glue", "GLUE"]
    assert unit["same_object"] is True


def test_packed_marks_are_drawn_over_a_demo_document(library_report: dict[str, Any]) -> None:
    rows = library_report["demo"]
    assert rows["glue"]["matches"] > 0 and rows["e"]["matches"] > rows["the"]["matches"] > 0
    for needle, row in rows.items():
        assert row["wrong"] == [], needle
        assert row["marks"] == row["packed_count"] == min(row["matches"], 4000), needle
        # A mark behind text is at least one rectangle: more vertices than without.
        assert row["packed"] > row["bare"] > 0, needle
        # Packed or as plain tuples, the library draws the same.
        assert row["same_bytes"] is True, needle


def test_the_usage_in_finder_s_docstring_hands_a_view_plain_marks() -> None:
    """
    F3. A view drops marks handed over packed at its next edit and repacks
    plain ones itself, so the wiring decided on
    (`.concerns/lead--after-A2-decisions.md` item 2) is `finder.marks()`, with
    `set_index` after an edit. The docstring used to show `finder.packed(document)`
    going to `view.set_marks` every frame.
    """
    usage = Finder.__doc__ or ""
    handed = [line for line in usage.splitlines() if "view.set_marks(" in line]
    assert handed, "the docstring no longer shows a view being given marks"
    for line in handed:
        assert "finder.marks()" in line and "packed" not in line, line
    assert "finder.set_index(" in usage

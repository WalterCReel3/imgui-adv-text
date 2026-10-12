"""
`imscribe.description`: one definition of the description types, with nothing behind it.

Until tranche 3 `imscribe.typesetter` and `imscribe.typeset_markdown` each
defined `BlockDescription` and the rest (finding R8 of the SW-R1 review): equal
field for field, and two classes. What is held here:

1.  the module imports nothing of imscribe, and nothing beyond the standard
    library;
2.  every description name of the two converter modules and of
    `imscribe.typeset_find` IS this module's object;
3.  the tables keyed by NAME agree with the enums they stand for, member for
    member, so a face or an alignment added to one and not the other fails
    here and not in a drawing;
4.  the small things both converters do through it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from imscribe import description, typeset_find, typeset_markdown, typesetter
from imscribe.description import (
    ALIGNS,
    FACE_ROLES,
    KIND_HOST,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    BlockDescription,
    RunDescription,
    align_code,
    column_aligns,
    face_role,
    table_text,
    with_tags,
)
from imscribe.fontmetrics import Face
from imscribe.markdown_rules import ColumnAlign
from imscribe.theme import Align, Theme

_ROOT = Path(__file__).resolve().parent.parent

_SHARED = (
    "BLOCK_HARD_BREAKS",
    "BLOCK_TABLE_HEADER",
    "BlockDescription",
    "CellDescription",
    "ColumnDescription",
    "Description",
    "FACE_DEFAULT",
    "KIND_CODE",
    "KIND_HEADING",
    "KIND_HOST",
    "KIND_LIST_ITEM",
    "KIND_PARAGRAPH",
    "KIND_RULE",
    "KIND_TABLE",
    "LinkRow",
    "RUN_DISPLAY_FORMULA",
    "RUN_FORMULA",
    "RUN_NO_BREAK",
    "RunDescription",
    "StyleDescription",
    "table_text",
)


def test_the_module_imports_the_standard_library_and_nothing_else() -> None:
    code = """
import json, sys
before = set(sys.modules)
import imscribe.description
new = set(sys.modules) - before
print(json.dumps({
    "imscribe": sorted(n for n in new if n.startswith("imscribe")),
    "foreign": sorted(
        n for n in new
        if n.split(".")[0] in ("imgui_bundle", "imtypeset", "markdown_it", "fontTools", "numpy")
    ),
}))
"""
    done = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={"PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["imscribe"] == ["imscribe", "imscribe.description"]
    assert report["foreign"] == []


@pytest.mark.parametrize("name", _SHARED)
def test_both_converter_modules_have_the_very_same_objects(name: str) -> None:
    """
    R8. Identity and not equality: `isinstance(x, typesetter.BlockDescription)`
    is true of a block `imscribe.typeset_markdown` described.
    """
    one = getattr(description, name)
    assert getattr(typesetter, name) is one
    assert getattr(typeset_markdown, name) is one


def test_the_private_names_callers_still_use_are_the_same_function() -> None:
    assert typesetter._with_tags is with_tags
    assert typeset_markdown._with_tags is with_tags
    assert typeset_find.BlockDescription is BlockDescription
    assert typeset_find.KIND_HOST == KIND_HOST


def test_a_description_from_either_converter_is_of_one_class() -> None:
    theme = Theme.build()
    described = typeset_markdown.describe_markdown("A paragraph with `code`.\n", theme)
    (block,) = described.blocks
    assert type(block) is typesetter.BlockDescription
    assert type(block.runs[0]) is typesetter.RunDescription
    assert type(described) is typesetter.Description
    assert type(described.styles[0]) is typesetter.StyleDescription


def test_the_tables_by_name_cover_the_enums_member_for_member() -> None:
    assert set(FACE_ROLES) == {face.name for face in Face}
    assert sorted(FACE_ROLES.values()) == list(range(1, len(Face) + 1))
    assert set(ALIGNS) == {align.name for align in Align}
    assert sorted(ALIGNS.values()) == list(range(len(Align)))
    for face in Face:
        assert face_role(face) == FACE_ROLES[face.name] == typesetter.FACE_ROLE[face]
    for align in Align:
        assert align_code(align) == ALIGNS[align.name] == typesetter.ALIGN[align]
    with pytest.raises(KeyError):
        face_role(ColumnAlign.LEFT)


def test_a_column_is_left_centred_or_right_and_never_justified() -> None:
    aligns = column_aligns([ColumnAlign.LEFT, ColumnAlign.CENTER, ColumnAlign.RIGHT])
    assert aligns == (ALIGNS["LEFT"], ALIGNS["CENTER"], ALIGNS["RIGHT"])
    # Anything that is not left or centre is right, an `Align` member too.
    assert column_aligns([Align.JUSTIFY, Align.LEFT]) == (ALIGNS["RIGHT"], ALIGNS["LEFT"])
    assert column_aligns([]) == ()


def test_a_tables_text_is_tabs_between_cells_and_newlines_between_rows() -> None:
    assert table_text([["a", "b"], ["1", "2"], ["", "x\ny"]]) == "a\tb\n1\t2\n\tx\ny"
    assert table_text([]) == ""
    assert table_text(iter([iter(["only"])])) == "only"


def test_with_tags_keeps_runs_ascending_and_whole_formulas() -> None:
    """
    The rule the library needs (runs ascending, none overlapping), over inputs
    made to cross every edge: a link inside a run, across two, over a
    formula, and two links that claim the same characters.
    """
    runs = [
        RunDescription(2, 6, face=2),
        RunDescription(6, 9, flags=RUN_FORMULA),
        RunDescription(12, 15, face=5),
        RunDescription(15, 18, flags=RUN_DISPLAY_FORMULA),
    ]
    for tagged in (
        [(0, 20, 1)],
        [(3, 4, 1)],
        [(4, 13, 1)],
        [(7, 8, 1)],
        [(0, 5, 1), (3, 16, 2)],
        [(16, 20, 1), (0, 1, 2)],
        [],
    ):
        out = with_tags(runs, tagged, color=9)
        reached = 0
        for run in out:
            assert run.start >= reached and run.end > run.start
            reached = run.end
        formulas = [run for run in out if run.flags & (RUN_FORMULA | RUN_DISPLAY_FORMULA)]
        assert [(run.start, run.end) for run in formulas] == [(6, 9), (15, 18)]
        assert all(run.color == 0 for run in formulas), "a formula's ink is the builder's"
        # Every character a link covers carries its tag, unless a formula it
        # only enters part-way holds it.
        tags = [0] * 20
        for run in out:
            tags[run.start : run.end] = [run.tag] * (run.end - run.start)
        claimed = 0
        for start, end, tag in sorted(tagged):
            start = max(start, claimed)
            for index in range(start, end):
                inside = any(run.start < index < run.end for run in formulas)
                if not inside:
                    assert tags[index] == tag, (tagged, index)
            claimed = max(claimed, end)
    assert with_tags(runs, [], color=9) == runs


# ---- a description a host made: `description_of` and `check_description` ----


def _described() -> description.Description:
    from imscribe.description import (
        KIND_CODE,
        KIND_TABLE,
        CellDescription,
        ColumnDescription,
        LinkRow,
        StyleDescription,
        description_of,
    )

    rows = (
        (CellDescription("a"), CellDescription("bb", (RunDescription(0, 2, 2),))),
        (CellDescription("c"), CellDescription("d")),
    )
    return description_of(
        [
            BlockDescription(text="see the link here", runs=(RunDescription(8, 12, tag=7),)),
            BlockDescription(kind=KIND_CODE, text="x = 1", style=1),
            BlockDescription(
                kind=KIND_TABLE,
                text=table_text([["a", "bb"], ["c", "d"]]),
                rows=rows,
                columns=(ColumnDescription(1), ColumnDescription(3)),
            ),
            BlockDescription(kind=KIND_HOST, text="a widget", extent=40.0),
        ],
        [StyleDescription(), StyleDescription(Face=5, Scale=0.9, Color=0xFF112233)],
        [LinkRow(0, 8, 12, 7, "https://host.example")],
    )


def test_description_of_fills_in_what_is_read_off_the_blocks() -> None:
    """
    A host states blocks, styles and links; `tables` and `texts` are read off
    the blocks and nothing misfits. The result passes `check_description`,
    which answers `None`.
    """
    made = _described()
    assert made.tables == [2]
    assert made.texts == ["see the link here", "x = 1", "a\tbb\nc\td", "a widget"]
    assert not made.misfits and not made.kinds
    assert description.check_description(made) is None


def test_every_demo_document_s_own_description_passes_the_check() -> None:
    """
    The check is not stricter than this tree's own converter: what
    `MarkdownConverter` describes of every markdown file under `demo/`, with
    math on, is a description a view would take.
    """
    theme = Theme.build()
    checked = 0
    for path in sorted((_ROOT / "demo").rglob("*.md")):
        source = path.read_text(encoding="utf-8")
        made = typeset_markdown.describe_markdown(source, theme, math=True, link_color=0xFF00FF00)
        description.check_description(made)
        checked += len(made.blocks)
    assert checked > 150


def _but(at: int, **fields: object) -> description.Description:
    made = _described()
    blocks = list(made.blocks)
    blocks[at] = blocks[at]._replace(**fields)
    return made._replace(blocks=blocks, texts=[block.text for block in blocks])


_WRONG = {
    "not_a_description": (lambda: [BlockDescription()], TypeError, "list is not"),
    "a_block_is_a_tuple": (
        lambda: _described()._replace(blocks=[(0, "x")], texts=["x"], tables=[], links=[]),
        TypeError,
        "block 0 is a tuple",
    ),
    "kind_out_of_range": (lambda: _but(0, kind=9), ValueError, "block 0: kind is 9"),
    "kind_is_a_bool": (lambda: _but(0, kind=True), TypeError, "block 0: kind is True"),
    "text_is_bytes": (lambda: _but(1, text=b"x"), TypeError, "block 1: text is b'x'"),
    "style_names_nothing": (lambda: _but(1, style=2), ValueError, "block 1: style is 2"),
    "negative_indent": (lambda: _but(1, left_indent=-1.0), ValueError, "left_indent is -1.0"),
    "extent_is_nan": (lambda: _but(3, extent=float("nan")), TypeError, "block 3: extent"),
    "extent_is_infinite": (lambda: _but(3, extent=float("inf")), TypeError, "block 3: extent"),
    "run_past_the_text": (
        lambda: _but(0, runs=(RunDescription(8, 99),)),
        ValueError,
        "block 0: run 0 is [8, 99)",
    ),
    "runs_out_of_order": (
        lambda: _but(0, runs=(RunDescription(8, 12), RunDescription(2, 4))),
        ValueError,
        "block 0: run 1 starts at 2",
    ),
    "run_backwards": (lambda: _but(0, runs=(RunDescription(5, 2),)), ValueError, "run 0 is [5, 2)"),
    "run_is_a_plain_tuple": (lambda: _but(0, runs=((0, 2),)), TypeError, "run 0 is a tuple"),
    "run_face_unknown": (lambda: _but(0, runs=(RunDescription(0, 2, 8),)), ValueError, "face is 8"),
    "run_scale_is_text": (
        lambda: _but(0, runs=(RunDescription(0, 2, 1, "big"),)),
        TypeError,
        "scale is 'big'",
    ),
    "rows_on_a_paragraph": (
        lambda: _but(0, rows=((description.CellDescription("x"),),)),
        ValueError,
        "rows and columns are a KIND_TABLE block's",
    ),
    "table_text_is_not_its_cells": (
        lambda: _but(2, text="a bb c d"),
        ValueError,
        "a table's text is table_text of its cells",
    ),
    "a_cell_is_a_str": (lambda: _but(2, rows=(("a", "bb"), ("c", "d"))), TypeError, "cell 0 is a"),
    "a_cell_s_run_past_it": (
        lambda: _but(
            2,
            rows=(
                (description.CellDescription("a", (RunDescription(0, 5),)),),
                (description.CellDescription("c"),),
            ),
            text="a\nc",
        ),
        ValueError,
        "row 0, cell 0: run 0 is [0, 5)",
    ),
    "a_column_of_text": (
        lambda: _but(2, columns=(description.ColumnDescription(1, "wide"),)),
        TypeError,
        "column 0",
    ),
    "a_style_is_a_tuple": (
        lambda: _described()._replace(styles=[(0, 1.0)]),
        TypeError,
        "style 0 is a tuple",
    ),
    "a_style_of_text": (
        lambda: _described()._replace(
            styles=[description.StyleDescription(Scale="big"), description.StyleDescription()]
        ),
        TypeError,
        "style 0: Scale is 'big'",
    ),
    "a_link_to_no_block": (
        lambda: _described()._replace(links=[description.LinkRow(9, 0, 1, 1, "u")]),
        ValueError,
        "link 0 names block 9",
    ),
    "a_link_with_no_tag": (
        lambda: _described()._replace(links=[description.LinkRow(0, 0, 1, 0, "u")]),
        ValueError,
        "a tag above zero",
    ),
    "texts_are_other_texts": (
        lambda: _described()._replace(texts=["a", "b", "c", "d"]),
        ValueError,
        "Description.texts",
    ),
    "tables_are_other_blocks": (
        lambda: _described()._replace(tables=[0]),
        ValueError,
        "Description.tables",
    ),
}


@pytest.mark.parametrize("name", sorted(_WRONG))
def test_a_description_a_view_could_not_show_is_refused_naming_what_is_wrong(name: str) -> None:
    """
    Each is a mistake a host can make describing its own blocks. The check
    says which block (and run, cell, column, style or link) by number, with
    `TypeError` for a wrong type and `ValueError` for a wrong value, and it
    does so with no library loaded.
    """
    make, error, says = _WRONG[name]
    with pytest.raises(error) as raised:
        description.check_description(make())
    assert says in str(raised.value), str(raised.value)


def test_a_description_with_a_misfit_is_refused() -> None:
    """
    `MarkdownConverter.describe` still stands an empty Host block in for an
    object it does not know and counts it in `misfits`; such a description
    does not pass, so the gap cannot reach a view by this door.
    """
    made = typeset_markdown.MarkdownConverter(Theme.build()).describe([object()])
    assert made.blocks[0].kind == KIND_HOST and made.misfits
    with pytest.raises(ValueError, match="block type object"):
        description.check_description(made)

"""
`advtext.description`: one definition of the description types, with nothing behind it.

Until tranche 3 `advtext.typesetter` and `advtext.typeset_markdown` each
defined `BlockDescription` and the rest (finding R8 of the SW-R1 review): equal
field for field, and two classes. What is held here:

1.  the module imports nothing of advtext, and nothing beyond the standard
    library;
2.  every description name of the two converter modules and of
    `advtext.typeset_find` IS this module's object;
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

from advtext import description, typeset_find, typeset_markdown, typesetter
from advtext.description import (
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
from advtext.fontmetrics import Face
from advtext.markdown_rules import ColumnAlign
from advtext.theme import Align, Theme

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
import advtext.description
new = set(sys.modules) - before
print(json.dumps({
    "advtext": sorted(n for n in new if n.startswith("advtext")),
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
    assert report["advtext"] == ["advtext", "advtext.description"]
    assert report["foreign"] == []


@pytest.mark.parametrize("name", _SHARED)
def test_both_converter_modules_have_the_very_same_objects(name: str) -> None:
    """
    R8. Identity and not equality: `isinstance(x, typesetter.BlockDescription)`
    is true of a block `advtext.typeset_markdown` described.
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

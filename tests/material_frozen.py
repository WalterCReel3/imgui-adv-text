"""
What the old core answered, read back from `tests/data/`: the typeset tests' oracle.

Until tranche 5 the typeset layer's tests asked the old core as they ran:
`advtext.typesetter.Converter(theme).describe(build_document(source, ...).blocks)`
was "the material path", and a description made straight from markdown
(`advtext.typeset_markdown`) was held equal to it. `Converter`,
`advtext.mathtext` (whose builder decided which formulas the material path
refused), `advtext.spans` and `advtext.stream` are deleted. What they answered
on the tree of 2026-10-11 was written down first, by
`.concerns/T5-B1-scripts/freeze_descriptions.py`, and this module is how a
test reads it: "new equals old" became "new equals frozen".

**A case that was not frozen is a `KeyError` naming it, never a pass.** The
file holds every case the tests asked on that day (2091 of them: each demo
four ways, the 48 awkward sources in four themes and eight settings, the 500
generated sources, four that single tests name); a test that asks about a
source nobody froze has no oracle, and says so.

Not a test module (no `test_` prefix), so pytest collects nothing here. It
imports `advtext.description` and nothing else of advtext, and a child
interpreter can use it with `tests/` on its path.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from advtext.description import (
    BlockDescription,
    CellDescription,
    ColumnDescription,
    Description,
    LinkRow,
    RunDescription,
    StyleDescription,
)

_DATA = Path(__file__).resolve().parent / "data"
DESCRIPTIONS = _DATA / "material_descriptions.json"
CORPORA = _DATA / "stream_corpora.json"


@cache
def _frozen() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    return loaded


@cache
def corpora() -> dict[str, Any]:
    """
    The sources `tests/test_stream.py` held the old stream to, by its names for them.

    `ADVERSARIAL`, `DOCUMENTS`, `REVIEW_5` and `TABLES` are name -> source;
    `LONG` is name -> [head, unit] and `LEAVING` name -> [head, unit, after].
    Sources only: nothing the old stream answered is in the file.
    """
    loaded: dict[str, Any] = json.loads(CORPORA.read_text(encoding="utf-8"))
    return loaded


def tokens(source: str) -> list[str]:
    """
    Pieces of at most four characters that never split a run of letters shorter than that.

    `tests/test_stream.py`'s `_tokens`, moved here with its corpora: a
    stand-in for a model's tokens. White space arrives attached to the front
    of the word after it, punctuation alone or in short runs, and a newline
    is as likely to be in the middle of a piece as at its end.
    """
    return re.findall(r"\s*\w{1,4}|\s*[^\w\s]{1,2}|\s+", source)


def _key(
    source: str, theme: str, references: bool, math: bool, more_may_follow: bool, link_color: int
) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
    return f"{theme}|{int(references)}{int(math)}{int(more_may_follow)}|{link_color:x}|{digest}"


def _answer(
    source: str, theme: str, references: bool, math: bool, more_may_follow: bool, link_color: int
) -> dict[str, Any]:
    key = _key(source, theme, references, math, more_may_follow, link_color)
    frozen = _frozen()
    at = frozen["descriptions"].get(key)
    if at is None:
        raise KeyError(
            f"the material path's answer for this case was never frozen ({key}; the source "
            f"begins {source[:60]!r}): {DESCRIPTIONS.name} holds what the old core said on "
            "2026-10-11 and the old core is gone"
        )
    answer: dict[str, Any] = frozen["answers"][at]
    return answer


def _runs(runs: list[list[Any]]) -> tuple[RunDescription, ...]:
    return tuple(RunDescription(*run) for run in runs)


def _block(fields: list[Any]) -> BlockDescription:
    block = BlockDescription(*fields)
    return block._replace(
        runs=_runs(list(block.runs)),
        rows=tuple(
            # A cell's trailing defaults were dropped too: an empty cell is `[]`.
            tuple(
                CellDescription(cell[0] if cell else "", _runs(cell[1] if len(cell) > 1 else []))
                for cell in row
            )
            for row in block.rows
        ),
        columns=tuple(ColumnDescription(*column) for column in block.columns),
    )


def description(
    source: str,
    theme: str = "default",
    *,
    references: bool = True,
    math: bool = True,
    more_may_follow: bool = False,
    link_color: int = 0,
) -> Description:
    """
    What `Converter(theme, link_color=...).describe(build_document(source, ...).blocks)` answered.

    `theme` is a name of `tests/test_typeset_markdown.py`'s `THEMES`; `math`
    true meant `math=advtext.mathtext.markdown_math()`. Raises `KeyError` for
    a case that was not frozen.
    """
    answer = _answer(source, theme, references, math, more_may_follow, link_color)
    blocks = [_block(fields) for fields in answer["blocks"]]
    return Description(
        blocks,
        [StyleDescription(*style) for style in answer["styles"]],
        [LinkRow(*row) for row in answer["links"]],
        list(answer["tables"]),
        [block.text for block in blocks],
        collections.Counter(answer["misfits"]),
        collections.Counter(answer["kinds"]),
    )


def targets(
    source: str,
    theme: str = "default",
    *,
    references: bool = True,
    math: bool = True,
    more_may_follow: bool = False,
    link_color: int = 0,
) -> list[str]:
    """
    `Converter.targets` after that describe: the URL each link tag stands for, tag 1 first.
    """
    answer = _answer(source, theme, references, math, more_may_follow, link_color)
    return list(answer["targets"])


def refuses(source: str, display: bool, size: int) -> bool:
    """
    Whether `advtext.mathtext.markdown_math()` refused this formula: the old math core's decision.

    The value for `describe_markdown(..., refuses=)` that makes the direct
    description say what the material path said. `size` is not looked at:
    the freeze asserted that no decision it recorded depended on it. A
    formula the old builder was never asked about is a `KeyError`.
    """
    key = f"{int(display)}|{source}"
    decided = _frozen()["refusals"].get(key)
    if decided is None:
        raise KeyError(
            f"the old math core was never asked about the formula {source!r} "
            f"(display={display}): {DESCRIPTIONS.name} holds its decisions and it is gone"
        )
    return bool(decided)


def generated() -> list[tuple[str, str, bool, bool, bool]]:
    """
    The 500 generated cases as they were drawn: (source, theme name, references, math, more).
    """
    return [(s, t, bool(r), bool(m), bool(f)) for s, t, r, m, f in _frozen()["generated"]]


def demo(name: str) -> dict[str, Any]:
    """
    What else of a demo's node material the tests read (default theme, math on).

    `name` is the path under `demo/`. Keys: `sources` (`build_document`'s
    source map, eight integers a block: `source_row` below makes the same of
    a `BlockSource`);
    `tables` (each table's `aligns`, `left_indent`, `header` and `rows`
    counts, and `cells`: `[text, runs, hard, link ranges, is a header]` as
    `Converter._text_of` read each cell); `glue` (the natural width of every
    interword glue, one list a text block or table cell, in order); `find`
    (`"<ignore case>|<needle>"` -> `[block, matches]` pairs:
    `advtext.spans.FindIndex`).
    """
    held: dict[str, Any] = _frozen()["demos"][name]
    return held


def source_row(where: Any) -> list[int]:
    """
    A `BlockSource` as the eight integers the file holds: its span's four fields, then its top's.

    (`line_start`, `line_end`, `start`, `end`, twice.)
    """
    return [*dataclasses.astuple(where.span), *dataclasses.astuple(where.top)]


def corpus_sources(name: str) -> list[list[int]]:
    """`build_document`'s source map for one of the 48 awkward sources, as `demo()["sources"]`."""
    held: list[list[int]] = _frozen()["corpus_sources"][name]
    return held


def space_widths(face_role: int, size: int) -> set[int]:
    """
    The widths the old core gave an interword glue in a face: plain, and after a sentence.
    """
    return set(_frozen()["space_widths"][f"{face_role}|{size}"])


def needle_cells() -> list[tuple[int, tuple[int, int] | None]]:
    """(block, cell) of each match `advtext.spans.FindIndex` found for the table-search test."""
    held = _frozen()["needle_cells"]
    return [(block, (cell[0], cell[1]) if cell is not None else None) for block, cell in held]


def stream_pattern(name: str) -> str:
    """The pattern of `advtext.stream._FENCE_OPENER` or `_TABLE_DELIMITER`, as it was."""
    held: str = _frozen()["stream_patterns"][name]
    return held

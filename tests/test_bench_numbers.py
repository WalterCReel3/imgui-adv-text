"""
The figures the benchmark docstrings quote, re-derived from the engine.

**This file exists because the numbers went stale silently and nothing caught
it.** `scripts/bench_draw.py`'s tables read `4,226 commands`, `49 runs` and
`3,443 glyphs` for an entire batch after `demo/sample.md` grew from 23 blocks to
37; the real figures were `5,378`, `71` and `4,362`. `tests/test_bench_draw.py`
repeated `3,443 glyphs make 49 runs` in a docstring of its own, and
`docs/decisions.md` carried `4,226 commands 20.7 -> 9.4 ms`. Four files, one
wrong number, no test anywhere. `docs/status.md`'s Provenance section names "a
confident number nobody can re-derive" as the single most common defect in this
project, and this is that defect.

## Why these tests parse the prose instead of asserting a constant

The obvious test is `assert len(shipped_commands(...)) == 5378`. **It would not
have caught this defect.** The engine was right the whole time; the *docstring*
was wrong. A constant-versus-engine test pins the engine to a number and leaves
the prose free to drift, which is exactly what happened.

So every test here reads the number **out of the docstring it is defending** and
compares it against a live re-derivation. The docstring is the thing under test.
Change `demo/sample.md` without updating the table and this goes red; edit the
table to a number the engine does not produce and this goes red; and there is no
third place to put a number where the two could agree with each other while both
being wrong.

## The trap that would make this file vacuous, and the guard against it

A regex that matches nothing makes every loop over its results pass. That is not
hypothetical here -- the tables are indented code blocks inside a docstring, the
counts carry thousands separators in one table and not in the other, and any of
those could be reformatted by a later edit into something the pattern misses.
`test_the_table_parser_finds_every_row_and_rejects_a_table_it_should_not_match`
is the meta-test, and it is the load-bearing one: it pins the row *count* and
feeds the parser a near-miss table it must refuse. Section 5 of `docs/status.md`
is a list of three occasions on which this project shipped a test that could not
fail, and all three were fixture defects rather than assertion defects.

## What is deliberately not here

**No timing is asserted.** `tests/test_bench_draw.py` already says why -- a test
that a draw takes 20ms measures the machine -- and this batch produced the
evidence: four runs of `bench_draw` within twenty minutes, over byte-identical
input, gave a full draw of 28.0, 30.3, 33.9 and 34.1 ms. Best-of-N flattens the
noise inside one run and does nothing about a machine that is loaded for all of
it. The counts are exact and the milliseconds are an order of magnitude, and
only the first kind is testable.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from advtext.markdown import TextBlock, build_document
from advtext.shipout import Glyph
from advtext.style import Theme, fontlib_metrics

_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE = _ROOT / "demo" / "sample.md"

# The measure and window the tables are taken at. `bench_draw`'s own defaults;
# a table taken at a different measure would be a different table.
_WIDTH_PT = 420.0


def _load(name: str) -> ModuleType:
    """
    Load a script as a module without putting `scripts/` on `sys.path`.

    The same shim `tests/test_bench_draw.py` and `tests/test_verify_advances.py`
    use, and for the same reason: no test may import a script by accident and
    make the suite depend on collection order.
    """
    path = _ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{path} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bench_draw = _load("bench_draw")
bench_reflow = _load("bench_reflow")


# One row of the "whole document versus viewport" table, as the docstring writes
# it: copies, commands, a time, the visible count, a time. The counts may carry
# thousands separators and the times always end in `ms`, and both of those are
# required rather than optional -- a pattern loose enough to match a row of the
# anatomy table as well would silently conflate two tables.
_TABLE_ROW = re.compile(
    r"^\s*\|\s*(\d+)\s*\|\s*([\d,]+)\s*\|\s*[\d.]+ms\s*\|\s*([\d,]+)\s*\|\s*[\d.]+ms\s*\|\s*$",
    re.MULTILINE,
)


def _parse_table(text: str) -> dict[int, tuple[int, int]]:
    """
    `{copies: (commands, visible)}` from the docstring's first table.
    """
    return {
        int(copies): (int(commands.replace(",", "")), int(visible.replace(",", "")))
        for copies, commands, visible in _TABLE_ROW.findall(text)
    }


def _docstring(module: ModuleType) -> str:
    doc = module.__doc__
    assert doc is not None, f"{module.__name__} lost its module docstring"
    return doc


def _sample() -> str:
    return _SAMPLE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The meta-test. Everything below it is worthless if this one does not hold.
# --------------------------------------------------------------------------


def test_the_table_parser_finds_every_row_and_rejects_a_table_it_should_not_match() -> None:
    """
    The guard that stops this file passing vacuously.

    Every other test here loops over `_parse_table`'s result. A regex that
    matched nothing would make all of them pass while defending nothing, and the
    table is an indented code block inside a docstring -- reflow it, drop the
    thousands separators, add a column, and the pattern misses. So the row count
    is pinned, and a near-miss table is fed in and must be refused.

    The near-miss matters more than the positive case. `| 1 | 5378 | 30.32 |
    1952 | 10.46 |` is the same table with the `ms` suffixes gone, and a pattern
    lax enough to accept it would also accept rows of the *anatomy* table, whose
    first column is a step number and not a copy count. Conflating the two would
    compare `1. draw, as shipped` against a command count and still pass, because
    both are integers.
    """
    parsed = _parse_table(_docstring(bench_draw))
    assert sorted(parsed) == [1, 2, 4], (
        "bench_draw's docstring no longer has a three-row `| copies | commands | "
        f"... |` table the parser can read; it found {parsed!r}"
    )

    no_units = "| 1 | 5378 | 30.32 | 1952 | 10.46 |"
    assert _parse_table(no_units) == {}, "the parser accepted a table with no `ms` units"

    anatomy = "    | 1. `draw`, as shipped | 4362 | 29.36ms |"
    assert _parse_table(anatomy) == {}, "the parser matched a row of the anatomy table"


# --------------------------------------------------------------------------
# bench_draw
# --------------------------------------------------------------------------


def test_every_command_count_in_bench_draws_table_is_what_the_engine_ships() -> None:
    """
    The number that went stale, tied to the engine that produces it.

    `shipped_commands` is the script's own function and needs no ImGui context:
    composition and ship-out are pure. So the docstring's claim can be checked
    exactly, for every row, without an atlas.

    All three rows are checked rather than the first, because the table's *point*
    is that the full column grows with the file while the culled column does not.
    Checking one row would leave the proportionality -- 2x and 4x the source for
    2x and 4x the commands -- unasserted, and that proportionality is the claim
    `advtext.ui.CommandIndex` rests on.
    """
    source = _sample()
    for copies, (quoted, _visible) in sorted(_parse_table(_docstring(bench_draw)).items()):
        shipped = len(bench_draw.shipped_commands(source, copies, _WIDTH_PT))
        assert shipped == quoted, (
            f"bench_draw's docstring says {copies} copies of demo/sample.md ship "
            f"{quoted} commands; the engine ships {shipped}. Re-run "
            "`python scripts/bench_draw.py --copies 1,2,4` and update the table."
        )


def test_the_visible_count_in_bench_draws_table_is_what_the_index_culls_to() -> None:
    """
    The culled column, which is the whole reason the table exists.

    The claim is that it is a function of the window and not of the document, so
    it must be the *same* number on all three rows -- and that is asserted here
    rather than left to a reader noticing three equal numbers. A regression that
    made culling leak commands proportionally to document length would leave
    every individual row self-consistent.
    """
    source = _sample()
    quoted = _parse_table(_docstring(bench_draw))
    assert len({visible for _commands, visible in quoted.values()}) == 1, (
        "the docstring's three rows no longer quote one visible count, so the "
        "table no longer says the culled cost is a function of the window"
    )
    for copies, (_commands, visible) in sorted(quoted.items()):
        cmds = bench_draw.shipped_commands(source, copies, _WIDTH_PT)
        index = bench_draw.CommandIndex.of(cmds)
        window = bench_draw.Viewport.of_pixels(0.0, bench_draw.DEFAULT_WINDOW_PX, 96.0)
        culled = len(index.visible(window))
        assert culled == visible, (
            f"bench_draw's docstring says one 768px window sees {visible} commands "
            f"at {copies} copies; the index culls to {culled}."
        )


def test_the_glyph_and_run_counts_in_bench_draws_prose_are_what_the_grouper_produces() -> None:
    """
    `there are 71 such runs in 4,362 glyphs`, and the batched row's `over 71 runs`.

    Two numbers in two places, and the conclusion of the whole script -- that
    batching is worth about 3% -- is computed from them. They were `49` and
    `3,443`.

    **The faces are stubs and that is load-bearing, not a shortcut.** This file
    may not touch the font atlas: it is process-global, and adding the six faces
    would collide with `tests/test_imgui_draw.py`'s session-scoped context in
    whichever order pytest picked, surfacing the failure in the other file.
    `tests/test_bench_draw.py`'s own docstring says so at length. `_runs` groups
    on `font is font` and `size_px ==`, so one stub instance per face reproduces
    the grouping exactly -- the identity is what matters and a stub has one.

    The one thing the stub cannot see is a glyph missing from a real face:
    `is_glyph_in_font` is answered `True` here unconditionally, where the script
    would drop it. The script prints `missing` in every table for exactly that
    reason and it is zero, which is what makes the two counts equal.
    """
    doc = _docstring(bench_draw)
    prose = re.search(r"there are ([\d,]+) such runs in ([\d,]+) glyphs", doc)
    assert prose is not None, "bench_draw's docstring no longer states its run and glyph counts"
    quoted_runs = int(prose.group(1).replace(",", ""))
    quoted_glyphs = int(prose.group(2).replace(",", ""))

    batched = re.search(r"batched `add_text` over ([\d,]+) runs", doc)
    assert batched is not None, "the anatomy table no longer names a run count"
    assert (
        int(batched.group(1).replace(",", "")) == quoted_runs
    ), "the anatomy table and the prose below it quote different run counts"

    cmds = bench_draw.shipped_commands(_sample(), 1, _WIDTH_PT)
    glyphs = sum(1 for cmd in cmds if isinstance(cmd, Glyph))
    assert (
        glyphs == quoted_glyphs
    ), f"bench_draw's docstring says the sample ships {quoted_glyphs} glyphs; it ships {glyphs}."

    calls = bench_draw._resolved_calls(None, cmds, _StubFaces(), 96.0)
    runs = len(bench_draw._runs(calls))
    assert runs == quoted_runs, (
        f"bench_draw's docstring says those glyphs group into {quoted_runs} runs; "
        f"they group into {runs}."
    )


class _StubBaked:
    ascent = 0.0


class _StubFace:
    """
    One face, with the two methods `_resolved_calls` asks of a real `FaceFont`.

    Identity is the only property `_runs` reads, so a bare object per face is a
    faithful stand-in for grouping purposes. `ascent` only shifts `y`, which
    grouping ignores.
    """

    def is_glyph_in_font(self, _codepoint: int) -> bool:
        return True

    def get_font_baked(self, _size_px: float) -> _StubBaked:
        return _StubBaked()


class _StubFaces:
    """
    A `Callable[[Face], Any]` handing back one stable stub per face.

    Stable is the point: a fresh object per call would give every glyph a
    different `font`, `_runs` would group nothing, and the run count would come
    out equal to the glyph count. That is the identity-keyed fixture defect
    `docs/status.md` section 5 item 3 records, which made three of five
    cache-key tests pass no matter what the key contained.
    """

    def __init__(self) -> None:
        self._faces: dict[Any, _StubFace] = {}

    def __call__(self, face: Any) -> _StubFace:
        return self._faces.setdefault(face, _StubFace())


def test_the_stub_faces_group_rather_than_handing_back_a_fresh_object_each_time() -> None:
    """
    The fixture check for the test above, and the reason it is a separate test.

    If `_StubFaces` returned a new `_StubFace` per call, the run count would
    equal the glyph count, the assertion would compare 4362 against a docstring
    saying 71 and fail loudly -- so this is not defending against silence. What
    it defends against is the *repair*: someone seeing that failure and editing
    the docstring to 4362 instead of the fixture. This test names which of the
    two is wrong.
    """
    faces = _StubFaces()
    assert faces("prose") is faces("prose")
    assert faces("prose") is not faces("code")


# --------------------------------------------------------------------------
# bench_reflow
# --------------------------------------------------------------------------


def test_the_edit_benchmark_still_lands_on_the_samples_largest_block() -> None:
    """
    `_after_an_edit`'s docstring calls itself the pessimistic end, and this is why.

    It appends a word to `source.rstrip()`, so the edit lands on the **last**
    block; it claims that block is the document's most expensive. If someone
    appends a short closing paragraph to `demo/sample.md` that claim silently
    inverts -- the benchmark keeps running, keeps reporting, and quietly becomes
    the *optimistic* end while its docstring still says pessimistic.

    Size stands in for cost, and deliberately: composing each of 37 blocks
    five times to rank them by milliseconds would put a slow, load-sensitive
    benchmark in the suite to check a structural fact. `advtext.ui` records that
    breaking is strongly superlinear in length, and the margin here is not
    marginal -- the last block carries 635 nodes against 517 for the runner-up.
    """
    document = build_document(_sample(), Theme.build(), fontlib_metrics)
    sizes = [
        (index, len(block.material))
        for index, block in enumerate(document.blocks)
        if isinstance(block, TextBlock)
    ]
    assert sizes, "demo/sample.md has no text blocks"

    last_index = max(index for index, _size in sizes)
    assert last_index == len(document.blocks) - 1, (
        "the last block of demo/sample.md is no longer a TextBlock, so the edit "
        "`_after_an_edit` makes no longer changes exactly one paragraph"
    )

    biggest_index, biggest = max(sizes, key=lambda row: row[1])
    assert biggest_index == last_index, (
        f"`_after_an_edit` edits block {last_index} and calls it the document's most "
        f"expensive, but block {biggest_index} is larger ({biggest} nodes). The "
        "benchmark is now the optimistic end and its docstring says otherwise."
    )


def test_bench_reflow_no_longer_quotes_the_whole_document_total_it_outgrew() -> None:
    """
    The specific stale figure, pinned so the repair is not undone.

    `_after_an_edit` read `31.9ms of 84.4ms at 420pt`. The 31.9 is still right -- that
    paragraph did not change -- and the 84.4 was the whole-document compose total
    before `demo/sample.md` grew, now around 97ms. A half-stale line is worse
    than a wholly stale one, because the accurate half lends the other its
    credibility.

    This asserts the withdrawn number is gone rather than asserting the new one,
    because the new one is a timing and timings are not assertable here. What can
    be pinned is that the line no longer claims a total the document passed years
    of commits ago.

    It matches the *claim sentence* rather than searching the whole docstring for
    the string `84.4ms`. The first draft did the latter and went red on the
    paragraph immediately below the claim, which explains what 84.4ms was and why
    it went -- a test that forbids naming a retracted number would forbid
    documenting the retraction.
    """
    doc = bench_reflow._after_an_edit.__doc__
    assert doc is not None
    claim = re.search(r"single most expensive block, ([\d.]+)ms of ([\d.]+)ms at 420pt", doc)
    assert claim is not None, (
        "`_after_an_edit` no longer states the heaviest block against the document "
        "total, which is the comparison that makes it the pessimistic end"
    )
    assert claim.group(2) != "84.4", (
        "`_after_an_edit` quotes 84.4ms again as the 420pt whole-document compose "
        "total. That figure predates demo/sample.md growing to 37 blocks."
    )
    heaviest, total = float(claim.group(1)), float(claim.group(2))
    assert heaviest < total, (
        f"the claim reads {heaviest}ms of {total}ms -- a block cannot cost more "
        "than the document that contains it, so one of the two is mistyped"
    )

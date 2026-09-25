"""
Tests for the parts of `scripts/bench_draw.py` that do not need an ImGui context.

Loaded by path rather than imported, for the reason `tests/test_verify_advances.py`
gives at length: `scripts/` must stay off `sys.path` so no test can import a
script by accident and make the suite depend on collection order.

**Nothing here creates an ImGui context or adds a face to the atlas**, and that
is the point rather than a limitation. The atlas is process-global. A test that
added the six faces `bench_draw` loads would collide with
`tests/test_imgui_draw.py`'s session-scoped context in whichever order pytest
happened to pick, and the failure would surface in the other file. The same
reasoning is why `tests/test_document_view.py`'s culling test passes
`fonts=lambda face: None`.

So what is covered is the arithmetic a wrong benchmark would get wrong quietly:
the run grouping that bounds the batched row, the command list the tables are
built over, and the budget fraction every percentage in the output is computed
from. What the script claims about ImGui's timings belongs in its report, which
is regenerated on demand, and not in an assertion -- a test asserting that a draw
takes 20ms would fail on a faster machine and would be measuring the machine.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from advtext.shipout import Glyph

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bench_draw.py"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.
    """
    spec = importlib.util.spec_from_file_location("_bench_draw_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bench = _load()


def _call(font: object, size_px: float, character: str) -> object:
    """
    One resolved `add_text` call, with the coordinates that do not affect grouping.

    The coordinates are zero throughout because `_runs` must group on face and
    size **only**. Grouping on position as well would be a different and wrong
    rule -- it would split a run wherever justification set a wide space, and the
    batched row would then understate what batching could reach.
    """
    return bench._Call(font=font, size_px=size_px, x=0.0, y=0.0, character=character)


def test_consecutive_glyphs_sharing_a_face_and_size_become_one_run() -> None:
    """
    The batched row's run count is what bounds the saving, so the grouping must be real.
    """
    face = object()
    calls = [_call(face, 16.0, character) for character in "word"]
    runs = bench._runs(calls)
    assert len(runs) == 1
    assert runs[0][1] == "word"


def test_a_size_change_starts_a_new_run_even_within_one_face() -> None:
    """
    A heading and the prose after it share a file and cannot share an `add_text`.
    """
    face = object()
    calls = [
        _call(face, 32.0, "H"),
        _call(face, 16.0, "a"),
        _call(face, 16.0, "b"),
    ]
    runs = bench._runs(calls)
    assert [text for _head, text in runs] == ["H", "ab"]


def test_a_face_change_starts_a_new_run() -> None:
    """
    Bold inside a sentence breaks the run, which is why 4,362 glyphs make 71 runs.

    Those two counts are re-derived in `tests/test_bench_numbers.py` rather than
    trusted here; this docstring carried `3,443 glyphs make 49 runs` for a whole
    batch after `demo/sample.md` grew under it.
    """
    regular, bold = object(), object()
    calls = [
        _call(regular, 16.0, "a"),
        _call(bold, 16.0, "B"),
        _call(regular, 16.0, "c"),
    ]
    assert [text for _head, text in bench._runs(calls)] == ["a", "B", "c"]


def test_every_glyph_survives_the_run_grouping() -> None:
    """
    A run count is only a bound on batching if nothing was dropped on the way to it.

    Without this the grouping could silently lose a glyph and the batched row
    would read as faster for the wrong reason -- fewer calls carrying less text.
    """
    regular, bold = object(), object()
    calls = [
        _call(regular, 16.0, "a"),
        _call(regular, 16.0, "b"),
        _call(bold, 16.0, "C"),
        _call(regular, 32.0, "d"),
        _call(regular, 32.0, "e"),
    ]
    runs = bench._runs(calls)
    assert "".join(text for _head, text in runs) == "abCde"
    assert sum(len(text) for _head, text in runs) == len(calls)


def test_an_empty_command_list_groups_into_no_runs() -> None:
    """
    A viewport scrolled past the end of the document ships nothing, and that is legal.
    """
    assert bench._runs([]) == []


def test_a_discarding_draw_list_accepts_every_call_the_backend_makes() -> None:
    """
    The anatomy table's row 2 is only exact if the stub never makes `draw` take a branch.

    `draw` issues exactly these four, and a stub missing one would raise inside
    the timed region rather than measuring it.
    """
    discarding = bench._Discarding()
    assert discarding.add_text(None, 16.0, None, 0, "x") is None
    assert discarding.add_rect_filled(None, None, 0) is None
    assert discarding.add_rect(None, None, 0) is None
    assert discarding.add_line(None, None, 0, 1.0) is None


def test_the_budget_fraction_is_against_a_sixty_hertz_frame() -> None:
    """
    Every percentage in the output comes from here, so the denominator is pinned.
    """
    timing = bench.DrawTiming(commands=0, glyphs=0, missing=0, draw_ms=1000.0 / 60.0)
    assert timing.budget_fraction == pytest.approx(1.0)
    doubled = bench.DrawTiming(commands=0, glyphs=0, missing=0, draw_ms=100.0 / 3.0)
    assert doubled.budget_fraction == pytest.approx(2.0)


def test_concatenating_the_sample_ships_proportionally_more_glyphs(
    bundled_fonts: Path,
) -> None:
    """
    The scaling table's x-axis is real: two copies ship about twice the glyphs.

    The concatenation joins two copies with a blank line, so the second copy is a
    fresh set of blocks broken to the same measure rather than a continuation of
    the first. Two copies therefore ship at least twice the glyphs, and the
    assertion is `>=` rather than `==` because the join can add a block boundary.

    Without this the length axis of the scaling table could be an artefact: a
    concatenation that silently produced one document's worth of commands would
    show a flat "full draw" column and look like culling was not needed.
    """
    assert bundled_fonts.is_dir()
    source = (Path(__file__).resolve().parent.parent / "demo" / "sample.md").read_text(
        encoding="utf-8"
    )
    one = bench.shipped_commands(source, 1, bench.DEFAULT_WIDTH_PT)
    two = bench.shipped_commands(source, 2, bench.DEFAULT_WIDTH_PT)

    glyphs_one = sum(1 for cmd in one if isinstance(cmd, Glyph))
    glyphs_two = sum(1 for cmd in two if isinstance(cmd, Glyph))
    assert glyphs_one > 0
    assert glyphs_two >= glyphs_one * 2
    # And the second copy really is below the first rather than on top of it,
    # which is what makes a scroll offset mean anything in the second table.
    assert max(cmd.y for cmd in two if isinstance(cmd, Glyph)) > max(
        cmd.y for cmd in one if isinstance(cmd, Glyph)
    )

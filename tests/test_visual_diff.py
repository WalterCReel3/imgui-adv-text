"""
Tests for `scripts/visual_diff.py`.

**The trap this file is written against is obvious and it is the one that would
land.** A test that asserts "the differ reports a difference" passes for a
differ that reports a difference between two identical images, which is the
useless implementation. `docs/status.md` section 5 catalogues five families of
tests in this repository that could not fail, so the house move is applied here
from the start: every claim about detection is paired with a control that is
supposed to come back *negative*, and every fixture is attacked as well as every
assertion.

Concretely:

  * `test_two_identical_renders_report_zero_change` is the control for every
    positive detection test below it, and
    `test_a_single_grey_level_on_a_single_pixel_is_detected` is the control for
    *it* -- a differ that reported zero for everything would satisfy the first
    and fail the second.
  * The region finder is ablated: pointed at a page with no sheet, at a phrase
    that is not on the page, and at a page carrying the phrase twice. All three
    must raise. Returning blank paper is the failure that produced two of the
    four visual incidents this harness exists for.
  * The line matcher is ablated **on real pixels** by switching off the one
    constraint that makes it discriminating, and the false matches must come
    back. A synthetic fixture cannot prove that on its own, because it is built
    from the same font metrics the matcher consults.

The module is loaded by path, never imported, for the reason
`tests/test_shot.py` and three others give: `scripts/` must stay off
`sys.path`. Unlike those, this one registers the module in `sys.modules` first
-- `@dataclass` resolves `cls.__module__` through `sys.modules` and raises
`AttributeError: 'NoneType' object has no attribute '__dict__'` without it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from conftest import Window

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "visual_diff.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_visual_diff_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vd = _load()


# ----------------------------------------------------------------------
# A synthetic page.
#
# Dark window, white sheet, rows of bars standing in for words. Built from the
# project's own advance widths so `locate_line` can be exercised with no
# display -- and *because* of that it can only ever prove the matcher agrees
# with itself, which is why the real-screenshot tests at the bottom exist.


_PAPER = 250
_WINDOW = 30
_INK = 40


def _blank_page(width: int = 420, height: int = 300) -> np.ndarray:
    page = np.full((height, width, 3), _WINDOW, dtype=np.uint8)
    page[40:270, 50:390] = _PAPER
    return page


def _draw_word(page: np.ndarray, x: int, y: int, width: int, letters: int, gap: int) -> int:
    """
    Draw one word as `letters` bars filling exactly `width` px, and return its right edge.

    The bars are the fixture's stand-in for glyphs. Their *count* is what makes
    the gap structure realistic; their total extent is what the matcher reads.
    """
    ink = width - (letters - 1) * gap
    step = ink / letters
    cursor = float(x)
    for i in range(letters):
        start = int(round(cursor))
        stop = start + max(1, int(round(step)))
        if i == letters - 1:
            stop = x + width
        page[y : y + 12, start:stop] = _INK
        cursor = stop + gap
    return x + width


def _draw_row(
    page: np.ndarray, y: int, words: list[str], x: int = 70, space: int = 7, gap: int = 2
) -> list[tuple[int, int]]:
    """Draw a row of words at their real ink widths. Returns each word's `(x, right)`."""
    widths = vd.expected_widths(words)
    placed: list[tuple[int, int]] = []
    cursor = x
    for word, want in zip(words, widths, strict=True):
        width = int(round(want))
        right = _draw_word(page, cursor, y, width, max(2, len(word)), gap)
        placed.append((cursor, right))
        cursor = right + space
    return placed


_PHRASE = "is shorter than most"
_OTHER = "column of the page"


@pytest.fixture
def page() -> np.ndarray:
    """A page with `_PHRASE` on row 2 and unrelated text on rows 1, 3 and 4."""
    img = _blank_page()
    _draw_row(img, 60, _OTHER.split())
    _draw_row(img, 90, _PHRASE.split())
    _draw_row(img, 120, ["paper", "arrives", "in", "sheets"])
    _draw_row(img, 150, ["and", "screens", "arrive", "in"])
    return img


def test_the_fixture_is_a_page_the_finder_can_read_at_all(page: np.ndarray) -> None:
    """
    Meta-test on the fixture, in the spirit of `docs/status.md` section 5.

    Every ablation below asserts the finder *fails* on a mutated page. That is
    worthless if the finder fails on the unmutated one too, so the fixture's
    own legibility is pinned here and the ablations can be read as differences.
    """
    grey = vd.grey_of(page)
    sheet = vd.find_sheet(grey)
    assert (sheet.w, sheet.h) == (340, 230), sheet
    bands = vd.find_columns(grey, sheet)
    assert len(bands) == 1
    rows = vd.find_text_rows(grey, bands[0])
    assert len(rows) == 4, [str(r) for r in rows]


def test_the_fixture_words_are_genuinely_different_widths(page: np.ndarray) -> None:
    """
    The fixture must not go uniform, which is exactly how family 1 in
    `docs/status.md` section 5 went vacuous: a fake measure gave every codepoint
    identical extents and the test that separated two quantities was comparing a
    number with itself. If every word here were the same width the matcher would
    have nothing to discriminate on and every ambiguity test would pass for the
    wrong reason.
    """
    widths = [round(w) for w in vd.expected_widths(_PHRASE.split())]
    assert len(set(widths)) == len(widths), widths
    assert max(widths) - min(widths) > 20, widths


# ----------------------------------------------------------------------
# Change detection: the control first, then the thing it controls for


def test_two_identical_renders_report_zero_change(page: np.ndarray) -> None:
    """
    **The load-bearing test in this file.** A differ that always finds something
    is worse than no differ, because its output reads like evidence.
    """
    grey = vd.grey_of(page)
    rect = vd.find_sheet(grey)
    diff = vd.diff_region(grey, grey.copy(), rect, rect)
    assert diff.identical
    assert diff.changed == 0
    assert diff.max_delta == 0
    assert diff.darker == 0 and diff.lighter == 0
    assert all(run.changed == 0 for run in diff.runs)
    assert all(run.centroid_shift == pytest.approx(0.0, abs=1e-9) for run in diff.runs)
    assert diff.warnings == []
    assert vd.midtone_flags(diff.profile_a, diff.profile_b) == []


def test_a_single_grey_level_on_a_single_pixel_is_detected(page: np.ndarray) -> None:
    """
    The control for the control. Without this, a differ hard-wired to report
    zero would pass the test above and nothing else here would catch it.
    """
    grey_a = vd.grey_of(page)
    grey_b = grey_a.copy()
    grey_b[95, 100] += 1.0
    rect = vd.find_sheet(grey_a)
    diff = vd.diff_region(grey_a, grey_b, rect, rect)
    assert diff.changed == 1
    assert diff.max_delta == 1
    assert diff.lighter == 1 and diff.darker == 0
    assert not diff.identical


def test_a_one_pixel_shift_is_localised_to_the_word_that_moved(page: np.ndarray) -> None:
    """
    Move one word one pixel right; every other word must report zero.

    This is the "localises exactly that" requirement. `centroid_shift` is the
    per-cluster number and it reads +1.0 px for the moved clusters -- it is a
    centre of mass, so it would read +0.33 px for a third-of-a-pixel move that
    changed no integer bound at all.
    """
    before = page.copy()
    after = page.copy()
    row = slice(90, 102)
    word = slice(70, 390)
    after[row, word] = np.roll(after[row, word], 1, axis=1)

    grey_a, grey_b = vd.grey_of(before), vd.grey_of(after)
    sheet = vd.find_sheet(grey_a)
    rows_a = vd.find_text_rows(grey_a, vd.find_columns(grey_a, sheet)[0])

    moved = vd.diff_region(grey_a, grey_b, rows_a[1], rows_a[1], name="moved row")
    assert moved.changed > 0
    assert moved.runs, "the moved row has no ink clusters to report"
    assert all(run.centroid_shift == pytest.approx(1.0, abs=0.05) for run in moved.runs), [
        run.centroid_shift for run in moved.runs
    ]

    for index in (0, 2, 3):
        still = vd.diff_region(grey_a, grey_b, rows_a[index], rows_a[index], name="untouched")
        assert still.identical, f"row {index} changed and nothing there moved"


def test_the_same_line_at_two_places_on_the_page_reports_no_cluster_movement() -> None:
    """
    Displacement is measured **inside the region**, not in the image.

    Found by ablation: replacing `dx = (rb.x - crop_b.x) - (ra.x - crop_a.x)`
    with `dx = rb.x - ra.x` left the whole suite green, because every other
    fixture here resolves both regions at the same absolute x. It is wrong on
    the case the tool is actually for -- a shot at another window width puts the
    same sheet somewhere else, and reporting that whole offset as "every glyph
    moved 135 px" buries the sub-pixel movement that was the question.

    Measured on the real thing after this test was added: two `columns:2` shots
    at 1100 and 1400 px give "0 differ in shape, 9 are the same shape at a
    different place", with dx of -1 and -2 px -- the set measure changing, not
    the window origin.
    """
    left, right = _blank_page(), _blank_page()
    _draw_row(left, 90, _PHRASE.split(), x=70)
    _draw_row(right, 90, _PHRASE.split(), x=110)

    grey_a, grey_b = vd.grey_of(left), vd.grey_of(right)
    rect_a = vd.resolve_region(grey_a, f"text:{_PHRASE}")
    rect_b = vd.resolve_region(grey_b, f"text:{_PHRASE}")
    assert rect_b.x - rect_a.x == 40, (str(rect_a), str(rect_b))

    diff = vd.diff_region(grey_a, grey_b, rect_a, rect_b, name="same line, moved 40 px")
    assert diff.runs, "no clusters to compare"
    assert all(run.dx == 0 for run in diff.runs), [run.dx for run in diff.runs]
    assert all(run.changed == 0 for run in diff.runs), [run.changed for run in diff.runs]
    assert not any(run.moved for run in diff.runs)


def test_a_change_in_cluster_count_is_warned_about(page: np.ndarray) -> None:
    """
    Two letters fusing is the defect the lead measured in a heading -- `iffe` in
    "difference" became one 31 px run where a letter is 9..11 px. The per-run
    table pairs A and B in order, so when the counts differ that pairing is
    wrong and the report has to say so out loud rather than quietly
    mis-attributing every row below the fusion.
    """
    grey_a = vd.grey_of(page)
    fused = page.copy()
    fused[90:102, 70:200] = _INK
    grey_b = vd.grey_of(fused)
    rows = vd.find_text_rows(grey_a, vd.find_columns(grey_a, vd.find_sheet(grey_a))[0])
    diff = vd.diff_region(grey_a, grey_b, rows[1], rows[1], name="fused")
    assert diff.runs_a != diff.runs_b
    assert any("ink runs" in w for w in diff.warnings), diff.warnings


# ----------------------------------------------------------------------
# Ablating the region finder


def test_find_sheet_refuses_a_page_that_has_no_sheet() -> None:
    """
    The Blocks tab really was like this (an overlay on the window background with
    no white page anywhere), and since tranche 5 the Columns page is.
    Returning "the whole window" would put every downstream measurement in the
    chrome and report it as body text.
    """
    dark = np.full((200, 300, 3), _WINDOW, dtype=np.uint8)
    with pytest.raises(vd.RegionNotFound, match="no sheet"):
        vd.find_sheet(vd.grey_of(dark))


def test_locate_line_refuses_text_that_is_not_on_the_page(page: np.ndarray) -> None:
    """
    The whole point. A crop that lands on blank paper looks like a successful
    crop, and twice in this project it was one.
    """
    with pytest.raises(vd.RegionNotFound, match="not on this page"):
        vd.locate_line(vd.grey_of(page), "zzqq wwxx vvkk")


def test_resolve_region_refuses_a_row_index_past_the_end(page: np.ndarray) -> None:
    with pytest.raises(vd.RegionNotFound, match="that column has 4 row"):
        vd.resolve_region(vd.grey_of(page), "column:1/row:99")


def test_locate_line_refuses_a_single_word() -> None:
    page = _blank_page()
    _draw_row(page, 90, ["people"])
    with pytest.raises(vd.RegionNotFound, match="at least two words"):
        vd.locate_line(vd.grey_of(page), "people")


def test_locate_line_refuses_when_two_rows_fit_equally_well() -> None:
    """
    A near-tie must raise, not be resolved. The lead's crop was one line off
    once; picking the better of two indistinguishable candidates is how that
    happens silently.
    """
    page = _blank_page()
    _draw_row(page, 60, _PHRASE.split())
    _draw_row(page, 120, _PHRASE.split())
    with pytest.raises(vd.AmbiguousRegion, match="more than one row"):
        vd.locate_line(vd.grey_of(page), _PHRASE)


def test_locate_line_finds_the_phrase_and_the_word_slice_lands_on_the_word(
    page: np.ndarray,
) -> None:
    grey = vd.grey_of(page)
    placed = _draw_row(_blank_page(), 90, _PHRASE.split())
    match = vd.locate_line(grey, _PHRASE)
    assert match.row == 2
    assert [w.text for w in match.words] == _PHRASE.split()
    assert match.rect.y == 90
    third = vd.resolve_region(grey, f"text:{_PHRASE}/words:3-3")
    assert (third.x, third.right) == placed[2], (str(third), placed[2])


def test_the_word_space_test_is_what_rejects_a_row_of_evenly_spaced_ink() -> None:
    """
    Ablation of the matcher's one discriminating constraint.

    The decoy row has the right ink widths in the right order and no word
    structure: every gap in it is the same, so nothing in it is a word space.
    Greedy width matching alone accepts it. The space test -- a gap before each
    word that is at least 3 px *and wider than the widest gap inside the word* --
    rejects it. `min_space=0` turns that test off, and the decoy comes back.
    """
    page = _blank_page()
    _draw_row(page, 90, _PHRASE.split(), space=3, gap=3)
    grey = vd.grey_of(page)

    assert vd.locate_lines(grey, _PHRASE, min_space=0), "the decoy should match on widths alone"
    assert vd.locate_lines(grey, _PHRASE) == [], "the space test failed to reject the decoy"


# ----------------------------------------------------------------------
# Midtones: a flag, never a score


def _profile(midtone_share: float) -> vd.InkProfile:
    return vd.InkProfile(
        inked=1000,
        total=4000,
        solid_share=1.0 - midtone_share,
        midtone_share=midtone_share,
        paper_level=250.0,
    )


@pytest.mark.parametrize("before,after", [(0.41, 0.11), (0.41, 0.60)])
def test_midtone_flags_fires_in_both_directions(before: float, after: float) -> None:
    lines = vd.midtone_flags(_profile(before), _profile(after))
    assert lines, f"{before} -> {after} was not flagged"
    assert "CHANGE IN ANTIALIASING" in " ".join(lines)


def test_midtone_flags_is_silent_when_nothing_moved() -> None:
    assert vd.midtone_flags(_profile(0.41), _profile(0.42)) == []


def test_midtone_flags_never_says_which_direction_is_better() -> None:
    """
    Incident 3: the lead read a collapse from 41.2% to 11.2% -- the destruction
    of antialiasing -- as an improvement and shipped the opinion. The user
    called the same frame "90's X11 text" on sight. So the warning text is
    forbidden from carrying a verdict in either direction, and the calibration
    landmarks must travel with it so nobody has to remember them.
    """
    for pair in ((0.41, 0.11), (0.41, 0.60)):
        text = " ".join(vd.midtone_flags(_profile(pair[0]), _profile(pair[1]))).lower()
        for banned in ("looks better", "improve", "crisp", "regression", "worse", "pass"):
            assert banned not in text, f"{banned!r} appeared in a midtone warning"
        assert text.count("better") == 1, "the only 'better' allowed is the refusal to rank"
        assert "does not say which side is better" in text
        assert "90's x11 text" in text


def test_gap_measurement_refuses_across_an_antialiasing_change() -> None:
    """
    Incident 2's cousin: the lead published a gap comparison between two renders
    with different ink distributions. A softer render reads as wider letters and
    narrower gaps with nothing having moved.
    """
    assert vd.gaps_comparable(_profile(0.41), _profile(0.42)) is None
    refusal = vd.gaps_comparable(_profile(0.41), _profile(0.70))
    assert refusal is not None and "NOT comparable" in refusal


# ----------------------------------------------------------------------
# Build identity and the stamp


def test_build_id_changes_when_a_source_file_changes(tmp_path: Path) -> None:
    (tmp_path / "imscribe").mkdir()
    target = tmp_path / "imscribe" / "thing.py"
    target.write_text("x = 1\n", encoding="utf-8")
    first = vd.build_id(tmp_path)
    target.write_text("x = 2\n", encoding="utf-8")
    assert vd.build_id(tmp_path) != first
    target.write_text("x = 1\n", encoding="utf-8")
    assert vd.build_id(tmp_path) == first, "the id must depend on content, not on mtime"


def test_build_id_survives_a_tree_with_no_commits() -> None:
    """
    This repository has none: `git rev-parse HEAD` exits 128 here. A harness
    that stamped the rev and nothing else would stamp every shot identically --
    or crash -- for the whole of a session like this one.
    """
    value = vd.build_id(_ROOT)
    head, _, digest = value.partition("+")
    assert len(digest) == 12 and digest.isalnum(), value
    assert head, value


def test_stamping_a_png_leaves_every_pixel_byte_identical(tmp_path: Path) -> None:
    """
    The stamp is a chunk insertion, not a re-encode. T15 pinned the
    misspelt-tab bug with a byte comparison of two PNGs; re-encoding here would
    put this module's zlib settings between the app and that comparison.
    """
    original = vd.encode_png(_blank_page())
    stamped = vd.stamp_png_bytes(original, {"imscribe-shot": '{"build": "x"}'})
    assert stamped != original
    idat = lambda data: [p for t, p in vd._iter_chunks(data) if t == b"IDAT"]  # noqa: E731
    assert idat(stamped) == idat(original)
    path = tmp_path / "s.png"
    path.write_bytes(stamped)
    pixels, text = vd.read_png(path)
    assert np.array_equal(pixels, _blank_page())
    assert json.loads(text["imscribe-shot"])["build"] == "x"


def _stamped(path: Path, page: np.ndarray, build: str, spec: str = "document") -> None:
    data = vd.encode_png(page)
    stamp = json.dumps({"build": build, "spec": spec}, sort_keys=True)
    path.write_bytes(vd.stamp_png_bytes(data, {"imscribe-shot": stamp}))


def test_compare_refuses_a_png_with_no_stamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good, bare = tmp_path / "a.png", tmp_path / "b.png"
    _stamped(good, _blank_page(), "build-1")
    bare.write_bytes(vd.encode_png(_blank_page()))
    code = vd.main(["compare", str(good), str(bare), "--region", "sheet"])
    assert code == 3
    assert "carries no build stamp" in capsys.readouterr().err


def test_compare_refuses_across_builds_unless_told(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Incident 4 made impossible rather than discouraged. T7-look reviewed PNGs
    from builds it could not identify, correctly said so, and had no way to fix
    it -- the artifacts were all it had.
    """
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    _stamped(a, _blank_page(), "build-1")
    _stamped(b, _blank_page(), "build-2")
    assert vd.main(["compare", str(a), str(b), "--region", "sheet"]) == 2
    assert "different builds" in capsys.readouterr().err
    assert vd.main(["compare", str(a), str(b), "--region", "sheet", "--allow-cross-build"]) == 0
    assert "CROSS-BUILD COMPARISON" in capsys.readouterr().out


def test_compare_of_one_file_against_itself_reports_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], page: np.ndarray
) -> None:
    a = tmp_path / "a.png"
    _stamped(a, page, "build-1")
    assert vd.main(["compare", str(a), str(a), "--region", "sheet", "--gaps"]) == 0
    out = capsys.readouterr().out
    assert "IDENTICAL: 0 pixels differ" in out
    assert "gaps A:" in out and "gaps B:" in out


def test_compare_exits_nonzero_when_the_region_is_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], page: np.ndarray
) -> None:
    a = tmp_path / "a.png"
    _stamped(a, page, "build-1")
    code = vd.main(["compare", str(a), str(a), "--region", "text:zzqq wwxx vvkk"])
    assert code == 3
    assert "NOT FOUND" in capsys.readouterr().err


# ----------------------------------------------------------------------
# The misspelt-tab trap


def test_the_app_tab_names_can_still_be_read() -> None:
    names = vd.known_tabs()
    assert len(names) >= 3, names
    assert "Document" in names, names


def test_a_misspelt_tab_name_is_refused_before_anything_is_photographed() -> None:
    """
    T15 measured that `--tab colums` produces a **byte-identical** photograph of
    the Document tab, exit 0, no warning. Every frame of a review built on that
    file is a review of the wrong picture, and nothing anywhere reports it.
    """
    with pytest.raises(SystemExit, match="is not a tab"):
        vd.check_tab_spec("colums")
    assert vd.check_tab_spec("columns:3") == "columns:3"
    assert vd.check_tab_spec(None) == "default"


# ----------------------------------------------------------------------
# Real pixels.
#
# Everything above runs with no display. These three do not, and they are the only
# tests here that can show the matcher works on a real render rather than on a
# fixture built from the same metrics it consults. Gated exactly as
# `tests/test_shot.py` gates its one real shot: by the `window` fixture in
# `tests/conftest.py`, which runs them on the session's display if that accepts
# a connection, on an Xvfb in a user namespace if it does not, and skips only
# when neither can be had. (They used to be gated on DISPLAY being *set* and
# were red in every session where it was set and unreachable.)
#
# What the Xvfb changes, stated rather than hidden: the rasteriser is llvmpipe,
# so the pixels are not the GPU's. The tests assert on where ink is, to within
# 3 px, and on counts of matching rows -- not on colours or on bytes.
#
# **Which page, and why it changed (tranche 5).** Until then the two tests of
# content addressing photographed `columns:2`: the old Columns page set its
# columns on a white sheet with imscribe's own layout. That page is gone. The
# Columns page is the library's columns in the pane, light ink on the window's
# dark ground, and paints no sheet; every region this tool resolves begins at the
# sheet, so on that page it resolves none, and says so (the third test below
# holds that it REFUSES rather than measuring the chrome). The Document page
# still paints a sheet and sets `demo/sample.md` on it through imtypeset, so the
# two content tests photograph that: what they show now is that the finder
# locates lines the LIBRARY set, by the same font's advance widths
# (`imscribe.fontlib`), to the same 3 px. They need the library: without it a
# page draws one line saying so and no sheet, and they skip with the reason.
# Making the finder work on a sheet-less dark page would be a new region finder
# (light ink, a pane boundary to keep the sidebar and the controls out); it was
# not built, and `.concerns/T5-B1--builder--result.md` says so.

_NEEDS_LIBRARY = (
    "IMTYPESET_LIBRARY is not set: without the library a page draws one line saying so "
    "and nothing to locate; run `make test TYPESET=1` (after `make typeset-lib`)"
)


def _shot(window: Window, spec: str, name: str) -> Path:
    if not os.environ.get("IMTYPESET_LIBRARY"):
        pytest.skip(_NEEDS_LIBRARY)
    out = window.out / name
    result = window.run(
        [
            str(_SCRIPT),
            "shoot",
            "--spec",
            spec,
            # 1300x764: a 200 px sidebar and a 1068x740 px body, the window the
            # shots here have been taken at since the tab bar became a sidebar
            # (C-shell, 2026-10-07).
            "--width",
            "1300",
            "--height",
            "764",
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 0, f"on {window.where}:\n{result.stdout}\n{result.stderr}"
    return out


@pytest.fixture(scope="module")
def real_document_shot(window: Window) -> Path:
    return _shot(window, "document", "visual-diff-document.png")


@pytest.fixture(scope="module")
def real_columns_shot(window: Window) -> Path:
    return _shot(window, "columns:2", "visual-diff-columns.png")


_REAL_PHRASE = "This document is the first"
"""
The opening of `demo/sample.md`'s first paragraph, which starts a line whatever
the measure does, and is deliberately free of emphasis: `locate_line` models one
face at one size and a bold run inside the phrase would defeat it.
"""


def test_a_real_shot_of_a_page_on_a_sheet_is_addressable_by_content(
    real_document_shot: Path,
) -> None:
    """
    End to end on real pixels: the sheet, its one column, and a phrase located
    by the font's own advance widths, in text the library set.

    Measured once before it was asserted (2026-10-11, Xvfb, library 7a7bc36):
    sheet (393,57) 702x695; one column of 26 rows; the phrase on row 2 with
    its five words 30, 72, 11, 22 and 28 px wide against 29.4, 70.6, 10.3,
    21.6 and 27.8 expected. Only the 3 px bound is asserted.
    """
    rgb, text = vd.read_png(real_document_shot)
    grey = vd.grey_of(rgb)
    stamp = json.loads(text["imscribe-shot"])
    assert stamp["spec"] == "document"
    assert stamp["build"] == vd.build_id(_ROOT)

    sheet = vd.find_sheet(grey)
    bands = vd.find_columns(grey, sheet)
    assert len(bands) == 1, [str(b) for b in bands]

    match = vd.locate_line(grey, _REAL_PHRASE)
    assert [w.text for w in match.words] == _REAL_PHRASE.split()
    assert match.rect.y > sheet.y and match.rect.bottom < sheet.bottom
    for word in match.words:
        assert abs(word.observed - word.expected) < 3.0, word

    with pytest.raises(vd.RegionNotFound):
        vd.locate_line(grey, "zzqq wwxx vvkk")


def test_the_word_space_test_is_what_makes_a_match_unique(real_document_shot: Path) -> None:
    """
    The ablation that a synthetic fixture cannot do honestly.

    With the word-space test off, the phrase groups successfully on more than
    one text row, because a greedy width accumulator can always find some run
    of letters that adds up; with it on, exactly one row survives. Measured
    on this shot on 2026-10-11: rows 2 and 12 without, row 2 with. (On the old
    Columns page, where this test was first written, "A column is not" gave
    three rows against one.) If this ever stops holding, `locate_line` has
    become a coin toss that still returns a rectangle.
    """
    grey = vd.grey_of(vd.read_png(real_document_shot)[0])
    without = vd.locate_lines(grey, _REAL_PHRASE, min_space=0)
    with_test = vd.locate_lines(grey, _REAL_PHRASE)
    assert len(with_test) == 1, [(m.column, m.row) for m in with_test]
    assert len(without) > 1, "the ablation found no false matches, so it proves nothing"
    assert (with_test[0].column, with_test[0].row) in [(m.column, m.row) for m in without]


def test_a_real_shot_of_a_page_with_no_sheet_is_refused_and_not_measured(
    real_columns_shot: Path,
) -> None:
    """
    What the Columns page draws now: columns in the pane and no sheet. The shot
    is taken and stamped as any other (the page name is validated, the build
    is in the file), and every region is REFUSED with `RegionNotFound`: the
    sheet, a column, a line by its words. Not one of them falls back to the
    whole window, which would send a measurement into the sidebar.

    This is the tool's own rule (`find_sheet`), met on a real page for the
    first time since the Blocks page, which was its example, was deleted.
    """
    rgb, text = vd.read_png(real_columns_shot)
    grey = vd.grey_of(rgb)
    stamp = json.loads(text["imscribe-shot"])
    assert stamp["spec"] == "columns:2" and stamp["build"] == vd.build_id(_ROOT)
    # Something was drawn: the page is not blank, it is light ink on a dark ground.
    assert float((grey > 140.0).mean()) > 0.01 and float((grey > 235.0).mean()) < 0.01
    with pytest.raises(vd.RegionNotFound, match="no sheet"):
        vd.find_sheet(grey)
    for region in ("sheet", "column:1", "row:1", "text:A column is not"):
        with pytest.raises(vd.RegionNotFound, match="no sheet"):
            vd.resolve_region(grey, region)

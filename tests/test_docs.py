r"""
The documentation, held to the one claim about it that a machine can check.

`docs/status.md` section 5 is about tests that cannot fail, and most of what the
documentation in this tree asserts is exactly that: prose about how a page looks,
or a measurement whose only guard is that somebody re-ran it. Nothing here
pretends otherwise.

**One class of documentation defect is mechanically checkable, and it is the one
that keeps happening.** Three separate documents spent a batch telling the reader
to "uncomment the `XVFB_RUN` block at the top of the `Makefile`" after that block
had been deleted, and `scripts/run_demo.py` said the same thing in its refusal
message. `tests/test_run_demo.py` now pins the script's copy of that advice. This
file pins the documentation's, by the same means and deliberately not by sharing
code with it -- a helper imported from another test module makes one regex the
single point of failure for both, and these two files are meant to fail
independently.

What is checked: **every `make <target>` the documentation names in a code span
or a code block is a target the `Makefile` actually defines.** Prose is excluded
on purpose, because "make it clear" and "make the page" are English.

What is not checked, and is left to a reader: whether the target does what the
surrounding sentence says it does, and every number in the files. `docs/status.md`
Provenance is the standard for those and it is a human one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MAKEFILE = _ROOT / "Makefile"

DOCS: tuple[Path, ...] = (
    _ROOT / "README.md",
    _ROOT / "docs" / "status.md",
    _ROOT / "docs" / "decisions.md",
    _ROOT / "docs" / "imgui-risks.md",
    _ROOT / "docs" / "litmus.md",
    _ROOT / "docs" / "subpixel.md",
    _ROOT / "docs" / "advance-rule.md",
    _ROOT / "docs" / "visual-review.md",
    _ROOT / "docs" / "tex-notes.md",
)
"""
Every markdown file under version control that gives instructions.

Listed rather than globbed so that a new document is a deliberate addition to
this check, and so that `docs/tex.web` -- a gitignored 1 MB verbatim copy of
Knuth's source -- cannot wander in.
"""

_TARGET = re.compile(r"^([a-z][a-z0-9-]*):(?!=)", re.MULTILINE)
"""
A `Makefile` rule. The `(?!=)` rejects `VAR:=value`, which otherwise matches.
"""

_INVOCATION = re.compile(
    r"""
    (?: ` \s* make \s+ ([a-z][a-z0-9-]*)   # `make svg`, a code span
      | ^ [ ]{4,} make \s+ ([a-z][a-z0-9-]*)  # an indented code block line
    )
    """,
    re.MULTILINE | re.VERBOSE,
)
r"""
`make <target>` where the *document* marked it as code, and nowhere else.

The exclusion is the whole point. A bare `\bmake (\w+)` over this tree's prose
also collects "make it", "make the", "make up", "make new" and "make line",
so the check would be measuring English rather than advice.
"""


def _targets_in(text: str) -> set[str]:
    """
    Every target a `Makefile`-shaped string defines.

    Split out from `_makefile_targets` so the meta-test below can hand it a
    string it controls. Applying the pattern only to the real `Makefile` makes
    the "does it reject a non-target" question unanswerable, because the real
    file may happen not to contain the thing being rejected.
    """
    return set(_TARGET.findall(text))


def _makefile_targets() -> set[str]:
    """
    Every target the `Makefile` defines, by parsing it rather than by listing it.
    """
    return _targets_in(_MAKEFILE.read_text(encoding="utf-8"))


def _invocations(text: str) -> set[str]:
    """
    Every `make <target>` a document presents as a command.
    """
    return {name for pair in _INVOCATION.findall(text) for name in pair if name}


def test_the_two_regexes_find_what_they_are_supposed_to_and_reject_what_they_are_not() -> None:
    """
    Meta-test: the check below is vacuous if either side quietly matches nothing.

    `named <= targets` is true of the empty set, so an `_INVOCATION` that matched
    nothing would make the real test pass over any documentation at all,
    including documentation that named a target which had never existed. That is
    the third family in `docs/status.md` section 5 and it is the reason this
    function is here.

    The prose cases are the discriminating half: they are real phrases from these
    files, and a naive `make (\\w+)` matches every one of them.

    `_TARGET` is checked against a `Makefile` fragment written here rather than
    against the real file, and that is load-bearing. The real assertion is
    `named <= targets`, so a *looser* target pattern can only ever make it pass;
    an ablation that widened `_TARGET` to swallow `VAR:=value` left every test in
    this file green. Only a fixture containing the things the pattern must
    reject can fail on that, and `assert "PHONY" not in targets` cannot -- no
    pattern anchored at `^[a-z]` can match a line beginning with a dot, so that
    assertion was true by construction.
    """
    targets = _makefile_targets()
    assert {
        "run",
        "svg",
        "shot",
        "shot-all",
        "shot-headless",
        "bootstrap",
    } <= targets, f"the Makefile parse missed targets that plainly exist: got {sorted(targets)}"

    fragment = "\n".join(
        (
            ".PHONY: help svg",
            "VENV ?= .venv",
            "PY := $(shell echo python)",
            "SRC = advtext tests",
            "svg:               ## render the litmus artifacts",
            "\tsomething",
            "shot-all:",
            "\tsomething else",
            "\tcd x && make svg",
        )
    )
    assert _targets_in(fragment) == {"svg", "shot-all"}, (
        "the target pattern does not separate a rule from a variable assignment, "
        "a .PHONY line, or a recipe body -- and a pattern that is too generous "
        f"cannot fail the real test: got {sorted(_targets_in(fragment))}"
    )

    assert _invocations("run `make svg` first") == {"svg"}, "a code span was not seen"

    # Not at the start of the string, on purpose. `^` matches position zero with
    # or without `re.MULTILINE`, so a fixture whose code block is the first line
    # passes whether the flag is set or not -- an ablation that dropped
    # `re.MULTILINE` left this file green until this line began with prose.
    assert _invocations("Reproduce with:\n\n    make shot-all\n") == {
        "shot-all"
    }, "a code block line below the first line was not seen"

    for prose in (
        "this would make it clear",
        "enough to make the page look set",
        "that would make up the difference",
        "make line breaking visible",
    ):
        assert _invocations(prose) == set(), f"the parse matched prose: {prose!r}"

    corpus = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
    assert len(_invocations(corpus)) >= 5, (
        "the documentation names almost no make targets, so this whole file is "
        "checking nothing -- the code-span pattern has probably stopped matching"
    )


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_every_make_target_the_documentation_names_is_a_real_target(path: Path) -> None:
    """
    Advice that points at something that does not exist is the defect here.

    Parametrised per file so a failure names the document rather than the set,
    because the reader who has to fix it is reading one file.
    """
    named = _invocations(path.read_text(encoding="utf-8"))
    missing = sorted(named - _makefile_targets())
    assert not missing, (
        f"{path.relative_to(_ROOT)} tells the reader to run "
        f"{', '.join('`make ' + name + '`' for name in missing)}, "
        f"and the Makefile has no such target"
    )


def test_docs_names_every_markdown_document_in_the_tree_and_no_absent_one() -> None:
    """
    The coverage guard, and it fails in both directions on purpose.

    `DOCS` is a hand-written list feeding a `parametrize`, which is a shape that
    shrinks silently: delete an entry and the suite reports one fewer passing
    test and no failure at all. An ablation that dropped `docs/imgui-risks.md`
    from the list did exactly that, so the list needs something checking it.

    Against the filesystem rather than against a second hand-written list, for
    the reason `docs/status.md` section 5 gives. A **new** document therefore
    fails this until it is added to `DOCS`, which is the intended cost: a
    document nothing checks is the thing this file exists to prevent.
    """
    absent = [path.name for path in DOCS if not path.is_file()]
    assert not absent, f"documents named in DOCS do not exist: {absent}"

    on_disk = {_ROOT / "README.md", *(_ROOT / "docs").glob("*.md")}
    unchecked = sorted(path.name for path in on_disk - set(DOCS))
    assert not unchecked, (
        f"markdown in the tree that no test reads: {unchecked}. "
        f"Add it to DOCS in {Path(__file__).name}."
    )

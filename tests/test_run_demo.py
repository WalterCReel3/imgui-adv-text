"""
Tests for `scripts/run_demo.py`: the guard, the advice it prints, and `--tab`.

`docs/status.md` section 2 listed this script as never executed by the suite, and
that was true -- there were no tests for it at all. The three defects that
produced this file are what an untested refusal path accumulates:

  * `_no_window` told the reader to "uncomment the XVFB_RUN block at the top of
    the Makefile", and no such block exists.
  * `--tab` carried `choices=("document", "formula", "blocks")`, so after the
    demo grew Columns and Specimen tabs, `make run ARGS="--tab columns"` was
    refused outright and `--tab columns:3` was rejected before the parser that
    understands colons ever saw it.
  * `BLOCKED` advertised `make run ARGS="--source demo/sample.md"`, and
    `--source` was not an argument this script had.

Every one of the three is *advice pointing at something that does not exist*, so
the tests here are mostly of that shape: not "does the string contain a word"
but "does the thing this string names actually exist". See
`test_every_make_target_the_script_names_is_a_real_target`, which parses the
`Makefile` rather than trusting a substring.

Loaded by path rather than imported, for the reason `tests/test_shot.py`,
`tests/test_bench_draw.py` and `tests/test_verify_advances.py` all give:
`scripts/` must stay off `sys.path` so no test can import a script by accident
and make the suite depend on collection order.

**Nothing here opens a window**, which `tests/conftest.py` forbids. The two tests
that run past the DISPLAY guard set `DISPLAY` to a value that is never dialled,
because `imscribe.ui.app.run` is replaced with a recorder first.

The *tab names* this file's cases use are coupled to the pages the app actually
draws by `test_the_tab_names_in_the_help_are_the_tabs_the_app_draws`. That test
used to read `App.gui`'s source, "a coupling of last resort" kept only until
`imscribe.ui.app` exported a list. It compares against `page_names()` now: the
demo's pages are discovered from `imscribe/ui/pages/` and that function is the
list the sidebar is drawn from.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "run_demo.py"
_MAKEFILE = _ROOT / "Makefile"


def _load() -> ModuleType:
    """
    Load the script as a module without putting `scripts/` on `sys.path`.
    """
    spec = importlib.util.spec_from_file_location("_run_demo_under_test", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{_SCRIPT} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_demo = _load()


@pytest.fixture
def stub_run(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str | None, str | None]]:
    """
    Replace `imscribe.ui.app.run` with a recorder and pretend a display exists.

    `main` does `from imscribe.ui.app import parse_tab_request, run` *inside* the
    function, after the guard, so the name is looked up on the module at call
    time and patching the attribute is enough. Patching it is also what makes
    the `DISPLAY` below harmless: nothing reaches GLFW, so the value never has
    to name a real server.
    """
    app = pytest.importorskip("imscribe.ui.app")
    calls: list[tuple[str | None, str | None]] = []

    def recorder(source: str | None = None, **kwargs: Any) -> None:
        calls.append((source, kwargs.get("tab")))

    monkeypatch.setattr(app, "run", recorder)
    monkeypatch.setenv("DISPLAY", ":0-not-dialled")
    return calls


# ----------------------------------------------------------------------
# The guard


def test_the_guard_refuses_without_a_display_and_stands_down_for_a_display_or_force(
    monkeypatch: pytest.MonkeyPatch,
    stub_run: list[tuple[str | None, str | None]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    All three cells of the guard, because two of them pass no matter what it says.

    A guard written `if not os.environ.get("DISPLAY")` -- dropping the `and not
    args.force` -- still refuses with no display and still stands down with one.
    Only the third row separates it from the real thing, and the same goes for a
    guard that refused unconditionally: it would pass the first row alone.
    """
    monkeypatch.delenv("DISPLAY", raising=False)
    assert run_demo.main([]) == 2, "no display and no --force must refuse"
    assert not stub_run, "the window was opened anyway"
    assert "No DISPLAY is set" in capsys.readouterr().err

    assert run_demo.main(["--force"]) == 0, "--force must override the guard"
    assert len(stub_run) == 1

    monkeypatch.setenv("DISPLAY", ":0-not-dialled")
    assert run_demo.main([]) == 0, "a display present must not be refused"
    assert len(stub_run) == 2


def test_the_guard_answers_before_imscribe_is_imported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    The refusal must cost nothing but an `os.environ` lookup.

    `README.md` and `docs/status.md` both quote 0.03-0.06s for this path, and
    importing `imscribe.ui.app` costs about 0.13s on this machine -- so moving
    the import above the guard would quietly multiply the measured figure in two
    documents by five, with every test still green.

    Timing cannot assert that on a shared machine, so the import is *broken*
    instead: `None` in `sys.modules` makes `import imscribe.ui.app` raise
    `ImportError: ... halted; None in sys.modules`. A guard that imports first
    therefore raises here, and one that answers first returns 2. The ablation is
    exact and takes no wall clock.
    """
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "imscribe.ui.app", None)

    assert run_demo.main([]) == 2
    assert "No DISPLAY is set" in capsys.readouterr().err


def test_no_window_names_the_display_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `DISPLAY=:1` unreachable and `DISPLAY` unset are different faults.

    The message is the only thing that tells them apart -- both arrive at the
    same `IM_ASSERT` -- so the two must not read alike.
    """
    unset = run_demo._no_window(None)
    named = run_demo._no_window(":7")
    assert "no DISPLAY set" in unset and ":7" not in unset
    assert "DISPLAY=:7" in named


# ----------------------------------------------------------------------
# Advice that points at something real


def _makefile_targets() -> set[str]:
    """
    Every target the `Makefile` defines, by parsing it.

    Not a hard-coded list: a hard-coded list of things that exist elsewhere is
    the defect this whole file is about.
    """
    text = _MAKEFILE.read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z][a-z0-9-]*):(?!=)", text, flags=re.MULTILINE))


def _make_invocations(text: str) -> set[str]:
    """Every `make <target>` named in a block of advice."""
    return set(re.findall(r"\bmake ([a-z][a-z0-9-]*)", text))


def test_the_makefile_parse_finds_the_targets_it_is_supposed_to() -> None:
    """
    Meta-test: the test below is worthless if either regex quietly matches nothing.

    Both sides are checked, because an empty set on either one makes
    `named <= targets` vacuously true. `docs/status.md` section 5 is four worked
    examples of exactly this shape of pass. The named targets are spot-checked
    against the ones this file cares about rather than counted, so adding a
    target to the `Makefile` does not fail this.
    """
    targets = _makefile_targets()
    assert {
        "run",
        "svg",
        "shot",
        "shot-all",
        "shot-headless",
    } <= targets, f"the Makefile parse missed targets that plainly exist: got {sorted(targets)}"
    assert "PHONY" not in targets, "the parse picked up the .PHONY line as a target"

    advice = run_demo.BLOCKED + run_demo._no_window(None)
    assert len(_make_invocations(advice)) >= 3, "the `make X` parse found almost nothing"
    assert _make_invocations("nothing to see here") == set(), "the parse matches anything"


def test_every_make_target_the_script_names_is_a_real_target() -> None:
    """
    The defect that boarded this task, generalised into something that recurs.

    `_no_window` used to end "Install xvfb, then uncomment the XVFB_RUN block at
    the top of the Makefile". The Makefile's display handling has been rewritten
    twice since and there is no such block; `make shot-headless` is what
    replaced it. Nothing caught that, because nothing here had ever read the
    Makefile.
    """
    targets = _makefile_targets()
    for text, where in ((run_demo.BLOCKED, "BLOCKED"), (run_demo._no_window(":1"), "_no_window")):
        missing = _make_invocations(text) - targets
        assert not missing, f"{where} tells the reader to run targets that do not exist: {missing}"


def test_the_vanished_xvfb_block_is_not_advertised_anywhere() -> None:
    """
    The specific stale sentence, pinned so it cannot come back by copy-paste.

    Weaker than the test above and kept anyway: that one catches a dead `make`
    target, and this one catches a dead *instruction*, which is the form the
    original defect actually took. Checked against the Makefile too, so if a
    future editor reintroduces an `XVFB_RUN` block the advice becomes legal
    again rather than being banned forever by a test.
    """
    advice = run_demo.BLOCKED + run_demo._no_window(None) + (run_demo.main.__doc__ or "")
    if "XVFB_RUN" not in _MAKEFILE.read_text(encoding="utf-8"):
        assert "XVFB_RUN" not in advice
        assert "uncomment" not in advice.lower()


def test_the_script_no_longer_claims_it_cannot_run_here() -> None:
    """
    The module docstring said "Never executed" and "this cannot run in the
    development sandbox". A window opened in about 0.4s in the session this
    test was written in, and this script was run to a live window then.

    The retraction's wording was "false in this environment" until 2026-10-07,
    when the docstring was revised to say reachability is a fact about a
    session (a later sandboxed session could not reach the same display); the
    phrase pinned below followed it. The shape of the check is unchanged.

    Not a `not in` check, and the first draft of this test was one and was wrong:
    the docstring *quotes* both stale sentences, because a correction that does
    not say what it is correcting leaves the next reader to find the old claim in
    `git log`. So what is asserted is that the retraction exists and that neither
    stale phrase appears after it -- restore the old docstring and the retraction
    is gone, which is red.

    The positive half matters more than the negative in any case: a docstring
    that merely deleted the sentence would pass a `not in` check while telling
    the reader nothing about the guard that is still the point of the file.
    """
    doc = run_demo.__doc__ or ""
    correction = doc.find("were false in it")
    assert correction > 0, "the docstring retracts nothing; the stale claim may simply be back"
    for stale in ("Never executed", "cannot run in the development sandbox"):
        where = doc.find(stale)
        assert where < correction, f"{stale!r} is stated rather than quoted-and-retracted"
    assert "make shot" in doc, "the docstring must say how to see the UI without a window"
    assert "--force" in doc, "the docstring must still explain the guard it is guarding with"


# ----------------------------------------------------------------------
# --tab: the grammar, and the absence of a copy of the tab list


_TAB_SPECS = [
    "document",
    "columns",
    "specimen",
    "formula",
    "typeset",
    "Columns",
    "columns:3",
    "columns:3,debug",
    "document:debug",
]


@pytest.mark.parametrize("spec", _TAB_SPECS)
def test_every_tab_and_option_reaches_the_app_verbatim(
    spec: str, stub_run: list[tuple[str | None, str | None]]
) -> None:
    """
    `--tab columns` and `--tab columns:3` were both refused by argparse before this.

    Verbatim matters as much as accepted: this script must not normalise the
    spec, because `imscribe.ui.app.parse_tab_request` owns the grammar and a
    second, partial implementation here is how the `choices=` list went stale in
    the first place. `Columns` is in the list because the app matches names
    case-insensitively and a script that lower-cased on the way through would
    be making a decision that is not its to make.
    """
    assert run_demo.main(["--tab", spec]) == 0, f"--tab {spec} was refused"
    assert stub_run == [(None, spec)]


def test_a_misspelt_tab_option_is_refused_before_the_window_opens(
    stub_run: list[tuple[str | None, str | None]], capsys: pytest.CaptureFixture[str]
) -> None:
    """
    The discriminating half of the test above, and it is what keeps it honest.

    With `run` stubbed, "the spec was accepted" would also be the result of a
    `--tab` that accepted literally anything -- which is very nearly what
    passing a free string through does. So the pair is the test: this one shows
    the harness can still go red, and shows the refusal happens *here* rather
    than as a `ValueError` traceback three frames inside `App.__post_init__`.
    """
    assert run_demo.main(["--tab", "columns:tree"]) == 2
    assert not stub_run, "the window was opened on a spec that does not parse"

    message = capsys.readouterr().err
    assert "'tree' is not a tab option" in message
    assert "columns:3,debug" in message, "the refusal does not show a spec that would work"


def test_the_tab_argument_keeps_no_copy_of_the_tab_list() -> None:
    """
    Structural, and aimed straight at the regression: `choices=` must stay absent.

    A behavioural test cannot see this. `--tab specimen` passing today is also
    what a `choices=` list containing today's five names looks like; the two
    diverge only when the sixth tab is added, which is the moment this test
    exists for. `scripts/shot.py` makes the same argument in a comment; here it
    is enforced.
    """
    parser = _build_parser()
    tab = _action(parser, "--tab")
    assert tab.choices is None, (
        "--tab has a choices= list again. It went stale last time within one batch: "
        "a list of tab names here is a second source of truth for something "
        "imscribe.ui.app.gui already owns."
    )
    assert tab.type is None, "--tab must pass the raw string through, colons and all"


def test_the_tab_names_in_the_help_are_the_tabs_the_app_draws() -> None:
    """
    Couple the names this file tests to the names the app actually renders.

    This used to scrape `App.gui`'s source for string literals, "a coupling of
    last resort" whose own docstring said: if app.py ever exports the names,
    delete this and compare against the export. It does now -- the pages are
    discovered from `imscribe/ui/pages/` and `imscribe.ui.app.page_names()` is
    the list the sidebar draws -- and `gui` no longer contains a name to
    scrape, so this compares against that. (Changed by C-shell, 2026-10-07.)

    Without it, `_TAB_SPECS` is a list this file made up: renaming Specimen to
    Sample would leave every test above green while `make run ARGS="--tab
    specimen"` was refused, or before names were validated silently opened the
    Document tab -- the same class of wrong-picture-under-a-confident-filename
    that `parse_tab_request` refuses misspelt options to avoid.
    """
    app = pytest.importorskip("imscribe.ui.app")
    drawn = {name.lower() for name in app.page_names()}
    assert drawn, "the app reports no pages; this comparison would pass against nothing"
    for spec in _TAB_SPECS:
        name = spec.partition(":")[0].lower()
        assert name in drawn, (
            f"{name!r} is not a page imscribe.ui.app.App.gui draws; "
            "this file's list of tab names has gone stale"
        )


# ----------------------------------------------------------------------
# --source, which the script advertised and did not have


def _build_parser() -> Any:
    """
    The parser `main` builds, obtained by letting `main` build it and stopping.

    Rebuilding it here would be a copy that could not go stale in the useful
    direction -- it would agree with itself.
    """
    import argparse

    captured: list[Any] = []
    original = argparse.ArgumentParser.parse_args

    def intercept(self: Any, *args: Any, **kwargs: Any) -> Any:
        captured.append(self)
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = intercept  # type: ignore[method-assign]
    try:
        with pytest.raises(SystemExit):
            run_demo.main([])
    finally:
        argparse.ArgumentParser.parse_args = original  # type: ignore[method-assign]
    assert captured, "main did not build a parser"
    return captured[0]


def _action(parser: Any, flag: str) -> Any:
    for action in parser._actions:
        if flag in action.option_strings:
            return action
    raise AssertionError(f"{flag} is not an argument of this parser")


def test_the_markdown_file_can_be_given_as_a_flag_or_as_a_positional(
    tmp_path: Path, stub_run: list[tuple[str | None, str | None]]
) -> None:
    """
    `make run ARGS="--source demo/sample.md"` is advertised in three places and
    failed with `unrecognized arguments: --source` until now.

    The flag case is the one that catches the trap the code comment describes:
    giving `--source` the *same* `dest` as the optional positional looks right
    and silently loses the value, because the positional's own default is
    written afterwards. Under that spelling this test sees `None` here.
    """
    page = tmp_path / "page.md"
    page.write_text("# from the flag\n", encoding="utf-8")

    assert run_demo.main(["--source", str(page)]) == 0
    assert stub_run == [("# from the flag\n", None)], "--source did not reach the app"

    assert run_demo.main([str(page)]) == 0
    assert stub_run[-1] == ("# from the flag\n", None), "the positional stopped working"

    assert run_demo.main([]) == 0
    assert stub_run[-1] == (None, None), "no file must mean 'let the app pick the default'"


def test_giving_the_file_twice_is_refused_rather_than_silently_preferring_one(
    tmp_path: Path,
    stub_run: list[tuple[str | None, str | None]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Two files named and one rendered is a wrong picture under a confident command
    line. Refusing costs one line and says which argument to drop.
    """
    one, two = tmp_path / "one.md", tmp_path / "two.md"
    one.write_text("one\n", encoding="utf-8")
    two.write_text("two\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        run_demo.main([str(one), "--source", str(two)])

    assert exit_info.value.code == 2
    assert not stub_run
    assert "not both" in capsys.readouterr().err


def test_the_page_count_in_the_docstring_is_the_count_of_pages() -> None:
    """
    The docstring spells out how many pages the sidebar has, and a page was
    added (2026-10-10) without it: "fourteen" for fifteen.
    """
    app = pytest.importorskip("imscribe.ui.app")
    words = "zero one two three four five six seven eight nine ten eleven twelve".split()
    words += "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    said = re.search(r"page of the sidebar since 2026-10-07: (\w+) of them", run_demo.__doc__)
    assert said is not None, "the docstring no longer counts the pages"
    assert said.group(1) == words[len(app.page_names())]


# ----------------------------------------------------------------------
# No library asked for: said, and the window still opens


def test_without_the_library_the_launcher_says_so_and_still_runs(
    monkeypatch: pytest.MonkeyPatch,
    stub_run: list[tuple[str | None, str | None]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Since tranche 5 no page falls back to imscribe's own layout, so a demo
    opened with no `IMTYPESET_LIBRARY` shows one line a page. That is said on
    stderr before the window opens, with the command that has the text, and
    the app is run all the same: exit 0, one call. With the variable set
    nothing is said.

    What is read is `typesetter.kind()` and not the variable (2026-10-13): an
    installed imtypeset is found with nothing set, and the note was printed
    over a demo that drew every page. `kind` is replaced here, so that
    nothing is imported into this process for the question.
    """
    typesetter = pytest.importorskip("imscribe.typesetter")
    kinds = typesetter.Kind
    monkeypatch.delenv("IMTYPESET_LIBRARY", raising=False)
    monkeypatch.setattr(typesetter, "kind", lambda: kinds.NOT_INSTALLED)
    assert run_demo.main(["--tab", "document"]) == 0
    said = capsys.readouterr().err
    assert said.strip() == run_demo.NO_LIBRARY.strip()
    assert "make run TYPESET=1" in said and "make typeset-lib" in said
    assert stub_run == [(None, "document")]

    # Found, and still no variable: the installed wheel.
    monkeypatch.setattr(typesetter, "kind", lambda: kinds.READY)
    assert run_demo.main(["--tab", "document"]) == 0
    assert capsys.readouterr().err == ""
    assert len(stub_run) == 2

    assert run_demo.NOT_INSTALLED == kinds.NOT_INSTALLED.value
    assert run_demo.library_note(run_demo.NOT_INSTALLED) == run_demo.NO_LIBRARY
    for kind in kinds:
        if kind is not kinds.NOT_INSTALLED:
            assert run_demo.library_note(kind.value) is None, kind


def test_a_library_that_was_asked_for_and_was_not_drawing_is_said_at_exit(
    monkeypatch: pytest.MonkeyPatch,
    stub_run: list[tuple[str | None, str | None]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    A1 (T5-R #2). With `IMTYPESET_LIBRARY` set the launcher said nothing at
    all, whether or not the library then drew: a library that was refused, or
    that failed in the middle of the run, was told only by the one line on
    each page. It is now said on stderr when the window has closed, with the
    reason the pages showed (`imscribe.ui.app.not_drawing_at_exit`). The exit
    status stays 0: the window was opened and was looked at, which is what
    this script is for; `scripts/shot.py` is the one that fails.

    With no library found nothing more is said than before, whatever the app
    reports: one-line pages are what was asked for. "Found" is
    `typesetter.kind()` (replaced here) and not the variable: an installed
    imtypeset that failed was not remarked on until 2026-10-13.
    """
    app = pytest.importorskip("imscribe.ui.app")
    typesetter = pytest.importorskip("imscribe.typesetter")
    kinds = typesetter.Kind
    monkeypatch.setattr(app, "not_drawing_at_exit", lambda: "Error: add_font: no such file")

    monkeypatch.setenv("IMTYPESET_LIBRARY", "/some/where/libimtypeset.so")
    monkeypatch.setattr(typesetter, "kind", lambda: kinds.FAILED)
    assert run_demo.main(["--tab", "document"]) == 0
    said = capsys.readouterr().err
    assert "Error: add_font: no such file" in said
    assert "/some/where/libimtypeset.so" in said and "was not drawing" in said

    # The installed wheel, failed: no variable, and it is said all the same.
    monkeypatch.delenv("IMTYPESET_LIBRARY")
    assert run_demo.main(["--tab", "document"]) == 0
    said = capsys.readouterr().err
    assert "Error: add_font: no such file" in said and "failed, installed" in said
    assert run_demo.NO_LIBRARY.strip() not in said

    monkeypatch.setattr(typesetter, "kind", lambda: kinds.NOT_INSTALLED)
    assert run_demo.main(["--tab", "document"]) == 0
    assert capsys.readouterr().err.strip() == run_demo.NO_LIBRARY.strip()

    monkeypatch.setattr(typesetter, "kind", lambda: kinds.READY)
    monkeypatch.setattr(app, "not_drawing_at_exit", lambda: "")
    assert run_demo.main(["--tab", "document"]) == 0
    assert capsys.readouterr().err == "", "a library that drew is not remarked on"
    assert len(stub_run) == 4

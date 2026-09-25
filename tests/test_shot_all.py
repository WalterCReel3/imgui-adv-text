"""
`make shot-all` must shoot every tab the app draws, and say what it shot.

The defect this file exists for was silent. `SHOT_TABS` named three tabs for a
whole batch after `advtext.ui.app.App.gui` grew to five; `make shot-all` exited
0, wrote three PNGs, and reported nothing missing. The reviewer whose task said
to use that target would have reviewed three tabs, concluded the demo was fine,
and never seen the two tabs the batch existed to demonstrate. A wrong picture
under a confident filename is the failure mode here, and so is a complete
absence under no filename at all.

Two couplings, and they point in opposite directions on purpose:

  * `SHOT_TABS` must not *miss* a tab the app draws -- the stale-list defect.
  * `SHOT_TABS` must not *name* a tab the app does not draw -- the renamed-tab
    defect, which `scripts/shot.py` cannot catch because `--tab` deliberately
    keeps no list of names and `App.gui` silently opens the default tab when the
    name matches nothing.

Set equality catches both, which a subset check in either direction would not.

**Everything here is derived from the recipe as `make` actually expands it**, not
from a regular expression over the `SHOT_TABS` line. `PY=echo` replaces the
interpreter with `echo`, so the loop prints the exact argument vector it would
have run and no window opens. A test that re-read the variable could agree with a
recipe that never used it.
"""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# What the recipe does


def _shot_all_invocations(
    shot_tabs: str | None = None, *, from_environment: bool = False
) -> list[list[str]]:
    """
    The argument vectors `make shot-all` would run, obtained by running it.

    `PY=echo` is an override on the command line, which beats the `:=` in the
    Makefile, so the recipe executes in full and each `scripts/shot.py ...` line
    is echoed instead of launched. Nothing opens a window and no display is
    needed, yet what is checked is the real loop -- including the filename
    derivation, which lives in shell and is reachable no other way.

    `from_environment` decides where `shot_tabs` is set, and the distinction is
    not cosmetic: make ranks a command-line assignment above every assignment in
    the makefile, `?=` or not, but ranks an environment variable *below* a plain
    `=` and above nothing at all. So only the environment path can tell `?=` from
    `=`. An earlier version of this file claimed to pin `?=` from the command
    line; it passed with `?=` changed to `=`.

    `MAKEFLAGS` and `MFLAGS` are stripped because the suite may itself be running
    under `make test`; inherited flags would otherwise leak into this sub-make
    and could turn its output into something else.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS")}
    command = ["make", "-C", str(ROOT), "-s", "shot-all", "PY=echo"]
    if shot_tabs is not None:
        if from_environment:
            env["SHOT_TABS"] = shot_tabs
        else:
            command.append(f"SHOT_TABS={shot_tabs}")
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, f"make shot-all failed:\n{result.stdout}\n{result.stderr}"
    return [line.split() for line in result.stdout.splitlines() if line.strip()]


def _flag(argv: list[str], name: str) -> str:
    assert name in argv, f"{name} is not in {argv!r}"
    return argv[argv.index(name) + 1]


@pytest.fixture(scope="module")
def invocations() -> list[list[str]]:
    return _shot_all_invocations()


def test_the_harness_sees_the_recipe_at_all(invocations: list[list[str]]) -> None:
    """
    Guard the fixture before anything trusts it.

    Every assertion below is over a list this fixture produced, and an empty
    list would satisfy several of them vacuously -- "no invocation writes a
    colon" is true of no invocations. So the shape of the capture is pinned
    first: if `PY=echo` ever stops reaching the recipe, or the loop stops
    echoing, this is the test that says so rather than a green suite over
    nothing.
    """
    assert invocations, "make shot-all printed nothing; PY=echo no longer reaches the recipe"
    for argv in invocations:
        assert argv[0].endswith("shot.py"), f"not a shot.py invocation: {argv!r}"
        assert "--tab" in argv and "--out" in argv, f"missing --tab/--out: {argv!r}"


# ----------------------------------------------------------------------
# What the app draws


def _tab_names_the_app_draws() -> tuple[str, ...]:
    """
    The tab names `App.gui` draws, read from `advtext.ui.app.TAB_NAMES`.

    **This used to parse `App.gui`'s source with `ast`, and said so: "a coupling
    of last resort ... if app.py grows a `TAB_NAMES` export, delete this and
    compare against it."** T18-colmargin added that export, `App.gui` now
    iterates it directly, and `parse_tab_request` refuses a name that is not in
    it -- so this reads the same object the app does and there is no second list
    left to drift.

    The scraper earned its retirement rather than merely outliving its use. When
    `gui`'s loop changed shape it returned an empty tuple, and
    `test_the_tab_names_can_still_be_read_out_of_the_app` failed loudly with the
    message its author wrote for exactly this moment. It did not quietly agree
    with an empty `SHOT_TABS`, which is the failure it was guarding.
    """
    from advtext.ui.app import TAB_NAMES

    return tuple(str(name) for name in TAB_NAMES)


def test_the_tab_names_can_still_be_read_out_of_the_app() -> None:
    """
    The other fixture guard: an extractor that found nothing must not read as
    "the app draws no tabs", which would make the set comparison below pass by
    agreeing with an empty `SHOT_TABS`.
    """
    names = _tab_names_the_app_draws()
    assert len(names) >= 3, (
        f"only {names!r} came back from advtext.ui.app.TAB_NAMES. An empty or "
        "near-empty export would make the set comparison below pass by agreeing "
        "with an empty SHOT_TABS, which is the failure this guard exists for."
    )
    assert "Document" in names
    # And the export is what `gui` actually iterates, not a list beside it.
    # `tests/test_app.py::test_the_tab_bar_draws_exactly_the_tabs_tab_names_lists`
    # is the assertion; this is the pointer to it.
    assert len(set(names)) == len(names), f"TAB_NAMES has a duplicate: {names!r}"


# ----------------------------------------------------------------------
# The coupling


def test_shot_all_covers_exactly_the_tabs_the_app_draws(invocations: list[list[str]]) -> None:
    """
    Set equality, both directions, because the two drifts are different bugs.

    A tab in the app and not in `SHOT_TABS` is the omission that started this
    file. A tab in `SHOT_TABS` and not in the app is a shot of the *default* tab
    filed under the missing tab's name, because `App.gui` matches `open_tab`
    against its own names and simply never matches.
    """
    shot = {_flag(argv, "--tab").partition(":")[0].lower() for argv in invocations}
    drawn = {name.lower() for name in _tab_names_the_app_draws()}
    assert shot == drawn, (
        f"make shot-all covers {sorted(shot)} but the app draws {sorted(drawn)}. "
        f"Missing from SHOT_TABS: {sorted(drawn - shot)}. "
        f"In SHOT_TABS but not a tab: {sorted(shot - drawn)}."
    )


def test_every_entry_is_a_request_the_app_would_accept(invocations: list[list[str]]) -> None:
    """
    `SHOT_TABS` entries carry options -- `columns:3`, `document:debug` -- and a
    misspelt one raises in `parse_tab_request` before the window opens. That
    protects a human typing `make shot ARGS=...`; it does not protect the list in
    the Makefile, which nobody types. Parse them here so a typo in the default
    list is a red test rather than eight seconds of window and a traceback.
    """
    app = importlib.import_module("advtext.ui.app")
    for argv in invocations:
        spec = _flag(argv, "--tab")
        request = app.parse_tab_request(spec)
        assert request.tab, f"{spec!r} names no tab"
        if request.columns is not None:
            assert request.columns >= 1


def test_each_entry_gets_its_own_plain_output_filename(invocations: list[list[str]]) -> None:
    """
    The options are what make two entries share a tab name, so the filename has
    to carry them -- otherwise `columns:1`, `columns:2` and `columns:3` all write
    `demo-columns.png` and the last one wins, which is a silent two-thirds loss
    of exactly the comparison the Columns tab exists to show.

    The colon is flattened rather than kept: it is legal in a path here and a
    nuisance in most things that will later handle these files.
    """
    outputs = [_flag(argv, "--out") for argv in invocations]
    assert len(set(outputs)) == len(outputs), f"two entries write the same PNG: {outputs}"
    for argv, out in zip(invocations, outputs, strict=True):
        spec = _flag(argv, "--tab")
        assert ":" not in out and "," not in out, f"{spec!r} produced an awkward filename {out!r}"
        assert out.startswith("artifacts/") and out.endswith(".png"), out
        expected = "artifacts/demo-" + spec.replace(":", "-").replace(",", "-") + ".png"
        assert out == expected, f"{spec!r} should write {expected!r}, not {out!r}"


def test_an_override_still_selects_a_subset() -> None:
    """
    `make shot-all SHOT_TABS=blocks` is the documented way to shoot one tab, and
    every test above runs the default list, so nothing else here would notice it
    breaking.

    Note what this does *not* establish, because the first version of this test
    got it wrong and said so in its own docstring: a command-line assignment
    outranks any makefile assignment, so this passes whether `SHOT_TABS` is `?=`
    or `=`. The test below is the one that pins `?=`.
    """
    invocations = _shot_all_invocations("blocks")
    assert [_flag(argv, "--tab") for argv in invocations] == ["blocks"]
    assert _flag(invocations[0], "--out") == "artifacts/demo-blocks.png"


def test_the_environment_can_override_the_list_too() -> None:
    """
    This is what `?=` buys, and the only thing that can tell it from `=`.

    An exported `SHOT_TABS` is how a shell session, a CI job or a wrapper script
    narrows the target without editing the recipe or restating the variable on
    every invocation. `?=` honours it; `=` silently ignores it and shoots all
    eight, which is the quiet kind of wrong -- the caller gets PNGs, just not the
    ones they asked for.
    """
    invocations = _shot_all_invocations("blocks", from_environment=True)
    assert [_flag(argv, "--tab") for argv in invocations] == ["blocks"], (
        "an exported SHOT_TABS did not reach the recipe; the Makefile has "
        "probably gone from '?=' to '='"
    )

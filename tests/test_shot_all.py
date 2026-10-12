"""
`make shot-all` must shoot every page the app has, and stop when it cannot tell.

The defect this file exists for was silent. A `SHOT_TABS` list in the Makefile
named three tabs for a whole batch after the app grew to five; `make shot-all`
exited 0, wrote three PNGs, and reported nothing missing. The reviewer whose
task said to use that target would have reviewed three tabs, concluded the demo
was fine, and never seen the two the batch existed to demonstrate.

**The list is gone, so what is guarded changed.** The app's pages are modules
found by scanning `imscribe/ui/pages/`; `scripts/shot.py --list` prints the
requests to photograph from that scan, and the recipe loops over what it
prints. There is no second copy to compare against the first. What can still go
wrong is a link in that chain, so each link is pinned here:

  1. `--list` prints exactly the scan's `shot_specs()` -- every page, in every
     state its own `PAGE.shots` names -- and every page is among them;
  2. the recipe runs one `scripts/shot.py --tab` per line of that output,
     verbatim and in order, whatever the lines are;
  3. when the scan finds a module it cannot load, `--list` exits non-zero with
     nothing on stdout, and the recipe then stops before the first window. A
     broken page is a failed target, never a shorter batch;
  4. an empty list is refused too, because "no pages" and "the lister printed
     nothing" look the same from a shell loop and the second is the old defect.

(That the scan itself turns a module that fails to import into a named failure
is `tests/test_pages.py`'s, with a package built for the purpose.)

**Everything here is derived from the recipe as `make` actually runs it.** `PY`
is pointed at a stub interpreter that hands `--list` to the real one and echoes
every other argument vector instead of executing it, so the loop prints exactly
what it would have launched and no window opens. The old form of this file used
`PY=echo`, which was enough while the list was a make variable; now the recipe
*asks the interpreter* for the list, and an `echo` would answer with its own
arguments.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from imscribe.ui import pages

ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = ROOT / "scripts" / "shot.py"


def _load() -> ModuleType:
    """
    `scripts/shot.py` as a module, without putting `scripts/` on `sys.path`.
    """
    spec = importlib.util.spec_from_file_location("_shot_for_shot_all", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shot = _load()


# ----------------------------------------------------------------------
# What the recipe does


def _stub(tmp_path: Path, on_list: str) -> Path:
    """
    An interpreter stand-in: `on_list` runs for `--list`, anything else is echoed.

    `on_list` is a line of shell with `"$@"` available. The real answer is
    `exec <python> "$@"`; the failure cases substitute `exit 1` or `true`.
    """
    path = tmp_path / "py-stub"
    path.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        f'  if [ "$arg" = "--list" ]; then {on_list}; exit $?; fi\n'
        "done\n"
        'echo "$@"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _make_shot_all(
    stub: Path, shot_tabs: str | None = None, *, from_environment: bool = False
) -> subprocess.CompletedProcess[str]:
    """
    Run `make shot-all` with the stub as `PY`.

    `from_environment` decides where `shot_tabs` is set, and the distinction is
    not cosmetic: make ranks a command-line assignment above every assignment in
    the makefile, `?=` or not, but ranks an environment variable *below* a plain
    `=` and above nothing at all. So only the environment path can tell `?=` from
    `=`.

    `MAKEFLAGS` and `MFLAGS` are stripped because the suite may itself be running
    under `make test`; inherited flags would otherwise leak into this sub-make.
    `SHOT_TABS` is stripped for the same reason unless this call sets it.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "SHOT_TABS")}
    command = ["make", "-C", str(ROOT), "-s", "shot-all", f"PY={stub}"]
    if shot_tabs is not None:
        if from_environment:
            env["SHOT_TABS"] = shot_tabs
        else:
            command.append(f"SHOT_TABS={shot_tabs}")
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)


def _invocations(result: subprocess.CompletedProcess[str]) -> list[list[str]]:
    assert result.returncode == 0, f"make shot-all failed:\n{result.stdout}\n{result.stderr}"
    return [line.split() for line in result.stdout.splitlines() if line.strip()]


def _flag(argv: list[str], name: str) -> str:
    assert name in argv, f"{name} is not in {argv!r}"
    return argv[argv.index(name) + 1]


@pytest.fixture(scope="module")
def real_stub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    The stub whose `--list` is the real `scripts/shot.py --list`.
    """
    return _stub(tmp_path_factory.mktemp("stub"), f'exec "{sys.executable}" "$@"')


@pytest.fixture(scope="module")
def invocations(real_stub: Path) -> list[list[str]]:
    return _invocations(_make_shot_all(real_stub))


def test_the_harness_sees_the_recipe_at_all(invocations: list[list[str]]) -> None:
    """
    Guard the fixture before anything trusts it.

    Every assertion below is over a list this fixture produced, and an empty
    list would satisfy several of them vacuously -- "no invocation writes a
    colon" is true of no invocations. So the shape of the capture is pinned
    first: if the stub ever stops reaching the recipe, or the loop stops
    echoing, this is the test that says so rather than a green suite over
    nothing.
    """
    assert invocations, "make shot-all printed nothing; the stub no longer reaches the recipe"
    for argv in invocations:
        assert argv[0].endswith("shot.py"), f"not a shot.py invocation: {argv!r}"
        assert "--tab" in argv and "--out" in argv, f"missing --tab/--out: {argv!r}"
        assert "--list" not in argv, f"the lister's own call leaked into the loop: {argv!r}"


# ----------------------------------------------------------------------
# What the app has


@pytest.fixture(scope="module")
def found() -> pages.Discovery:
    """
    The scan, strict: a module that cannot be loaded fails every test that uses this.
    """
    return pages.require()


def test_the_scan_finds_the_pages_at_all(found: pages.Discovery) -> None:
    """
    The other fixture guard: a scan that found nothing must not read as "the
    app has no pages", which would make the comparisons below pass by agreeing
    with an empty batch.
    """
    names = [page.name for page in found.pages]
    assert len(names) >= 4, f"only {names!r} came back from imscribe.ui.pages"
    for original in ("Document", "Columns", "Specimen", "Formula"):
        assert original in names, f"{original} is no longer a page: {names!r}"
    # Blocks was the fifth. It showed the old core's hpack and vpack and was
    # deleted in tranche 5 (`.concerns/lead--tranche-5.md`, decision 3).
    assert "Blocks" not in names


def test_the_sidebar_and_the_batch_are_one_scan(found: pages.Discovery) -> None:
    """
    The app draws its navigation from the same scan the batch is listed from.

    Without this the two could each be right about a different list. `App` keeps
    the `Discovery` it was built with and `sidebar_rows` is everything
    `App._sidebar` draws, so the pages a person can click are compared here
    with the pages `--list` photographs.
    """
    app = importlib.import_module("imscribe.ui.app")
    made = app.App(source="# t\n\nx\n", columns_source="x\n")
    clickable = [row.page.name for row in app.sidebar_rows(made.discovery) if row.page]
    assert clickable == [page.name for page in found.pages]
    assert tuple(app.TAB_NAMES) == tuple(clickable), "TAB_NAMES is no longer a view of the scan"


# ----------------------------------------------------------------------
# Link 1: --list is the scan


def test_list_prints_exactly_the_scans_shot_specs(
    found: pages.Discovery, capsys: pytest.CaptureFixture[str]
) -> None:
    assert shot.main(["--list"]) == 0
    printed = capsys.readouterr().out.split()
    assert printed == list(found.shot_specs())


def test_every_discovered_page_is_shot(found: pages.Discovery) -> None:
    """
    Set equality, both directions, because the two drifts are different bugs.

    A page that is in the app and not in the batch is the omission that started
    this file. A name in the batch that is not a page is a request the app
    refuses -- it used to be a photograph of the *default* tab filed under the
    missing tab's name.
    """
    shot_pages = {spec.partition(":")[0] for spec in found.shot_specs()}
    drawn = {page.name.lower() for page in found.pages}
    assert shot_pages == drawn, (
        f"the batch covers {sorted(shot_pages)} but the app has {sorted(drawn)}. "
        f"Never photographed: {sorted(drawn - shot_pages)}. "
        f"Photographed but not a page: {sorted(shot_pages - drawn)}."
    )


def test_a_page_cannot_opt_out_of_the_batch() -> None:
    """
    `test_every_discovered_page_is_shot` passes today because every page lists a
    shot. This is why it will keep passing: an empty `shots` is refused where
    the page is defined, so it surfaces as a failed module, not a missing PNG.
    """
    with pytest.raises(ValueError, match="shots"):
        pages.PageSpec(name="Quiet", order=1, factory=lambda context: None, shots=())  # type: ignore[arg-type,return-value]


def test_the_original_batch_is_still_in_it(found: pages.Discovery) -> None:
    """
    The photographs the Makefile's list used to name, in its order.

    The pages moved from a tab bar to modules; what `make shot-all` writes for
    them must not have changed name or number on the way. Later pages may add
    to the batch, hence a prefix-insensitive check and not equality. There
    were eight: `blocks` went with its page in tranche 5.
    """
    was = [
        "document",
        "document:debug",
        "columns:1",
        "columns:2",
        "columns:3",
        "specimen",
        "formula",
    ]
    assert "blocks" not in found.shot_specs()
    now = [spec for spec in found.shot_specs() if spec in was]
    assert now == was


def test_every_entry_is_a_request_the_app_would_accept(found: pages.Discovery) -> None:
    """
    Entries carry options -- `columns:3`, `document:debug` -- and a misspelt one
    raises in `parse_tab_request` before the window opens. That protects a human
    typing `make shot ARGS=...`; it does not protect a page's own `shots`, which
    nobody types. Parse them here so a typo is a red test rather than eight
    seconds of window and a traceback.
    """
    app = importlib.import_module("imscribe.ui.app")
    for spec in found.shot_specs():
        request = app.parse_tab_request(spec)
        assert request.tab, f"{spec!r} names no page"
        if request.columns is not None:
            assert request.columns >= 1


def test_a_broken_page_makes_list_fail_and_print_no_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], found: pages.Discovery
) -> None:
    """
    Link 3, first half. One module that would not load, beside pages that did.

    The partial list is the dangerous output: it is plausible, and a caller that
    captured it would photograph everything else and report nothing missing. So
    stdout must be empty, the status non-zero, and the module named on stderr.
    """
    broken = pages.Discovery(
        found.pages, (pages.Failure("imscribe.ui.pages.halfwritten", "SyntaxError: invalid"),)
    )
    monkeypatch.setattr(pages, "discover", lambda: broken)
    assert shot.main(["--list"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "", f"a partial list was printed:\n{captured.out}"
    assert "imscribe.ui.pages.halfwritten" in captured.err
    assert "SyntaxError: invalid" in captured.err


# ----------------------------------------------------------------------
# Link 2: the recipe runs what --list printed


def test_the_recipe_shoots_what_list_printed_in_order(
    invocations: list[list[str]], found: pages.Discovery
) -> None:
    assert [_flag(argv, "--tab") for argv in invocations] == list(found.shot_specs())


def test_the_recipe_keeps_no_list_of_its_own(tmp_path: Path) -> None:
    """
    Two names that are no page of this app, and the recipe shoots exactly those.

    This is what "adding a page touches no shared file" comes down to on the
    Makefile's side: nothing in the recipe knows a page name, so nothing in it
    can disagree with the app about one.
    """
    stub = _stub(tmp_path, "printf '%s\\n' alpha beta:2,debug")
    invocations = _invocations(_make_shot_all(stub))
    assert [_flag(argv, "--tab") for argv in invocations] == ["alpha", "beta:2,debug"]
    assert [_flag(argv, "--out") for argv in invocations] == [
        "artifacts/demo-alpha.png",
        "artifacts/demo-beta-2-debug.png",
    ]


def test_each_entry_gets_its_own_plain_output_filename(invocations: list[list[str]]) -> None:
    """
    The options are what make two entries share a page name, so the filename has
    to carry them -- otherwise `columns:1`, `columns:2` and `columns:3` all write
    `demo-columns.png` and the last one wins, which is a silent two-thirds loss
    of exactly the comparison the Columns page exists to show.

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


# ----------------------------------------------------------------------
# Links 3 and 4: the recipe stops when the list cannot be trusted


def test_the_recipe_stops_when_list_fails(tmp_path: Path) -> None:
    """
    Link 3, second half: `--list` exited non-zero, as it does for a broken page.

    The stub prints two plausible names before failing, which is worse than the
    real script does, to show the recipe goes by the status and not by whether
    it was handed something to loop over.
    """
    result = _make_shot_all(_stub(tmp_path, "echo document; echo columns:2; exit 1"))
    assert result.returncode != 0, "make shot-all succeeded although --list failed"
    assert "--tab" not in result.stdout, f"something was shot anyway:\n{result.stdout}"
    assert "--list failed" in result.stderr


def test_the_recipe_refuses_an_empty_list(tmp_path: Path) -> None:
    result = _make_shot_all(_stub(tmp_path, "true"))
    assert result.returncode != 0, "make shot-all succeeded having photographed nothing"
    assert "named no page" in result.stderr


# ----------------------------------------------------------------------
# The override


def test_an_override_still_selects_a_subset(tmp_path: Path) -> None:
    """
    `make shot-all SHOT_TABS=blocks` is the documented way to shoot one page.

    The stub fails `--list`, so this also shows an override does not consult the
    scan at all: one page can be photographed while another's module is broken.

    Note what this does *not* establish: a command-line assignment outranks any
    makefile assignment, so this passes whether `SHOT_TABS` is `?=` or `=`. The
    test below is the one that pins `?=`.
    """
    invocations = _invocations(_make_shot_all(_stub(tmp_path, "exit 1"), "blocks"))
    assert [_flag(argv, "--tab") for argv in invocations] == ["blocks"]
    assert _flag(invocations[0], "--out") == "artifacts/demo-blocks.png"


def test_the_environment_can_override_the_list_too(tmp_path: Path) -> None:
    """
    This is what `?=` buys, and the only thing that can tell it from `=`.

    An exported `SHOT_TABS` is how a shell session, a CI job or a wrapper script
    narrows the target without editing the recipe or restating the variable on
    every invocation. `?=` honours it; `=` silently ignores it and shoots the
    whole batch, which is the quiet kind of wrong -- the caller gets PNGs, just
    not the ones they asked for.
    """
    result = _make_shot_all(_stub(tmp_path, "exit 1"), "blocks", from_environment=True)
    invocations = _invocations(result)
    assert [_flag(argv, "--tab") for argv in invocations] == ["blocks"], (
        "an exported SHOT_TABS did not reach the recipe; the Makefile has "
        "probably gone from '?=' to '='"
    )

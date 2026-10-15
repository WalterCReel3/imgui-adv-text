# Assignments for the owner

Things only you can do, in the order I would do them. First written
2026-10-12 by the imscribe session's lead (an agent); **sections 1 to 6
rewritten 2026-10-13** by the builder of the task ADOPT-FINAL (an agent) to
what is true that day, after imtypeset went to PyPI. The agent sessions do
not push, do not upload, cannot run anything on a Mac, and do not make the
decisions at the end.

Tick a box, or tell the session, when one is done; several unblock work on
the other side.

**Where things stand (2026-10-13).** Your words that day: "I'm happy to
announce that imtypeset is available on PyPI." imscribe now depends on it
(`imtypeset==0.4.1.192900`), is version `0.2.0b1`, and has a release
workflow.

**Later the same day: imscribe 0.2.0b1 IS on PyPI.** As `git`, `gh` and
PyPI answered at about 22:05 local: the work is commit `b98de08`, the
branch and the tag `v0.2.0b1` are pushed, the `release` workflow ran once
for the tag and succeeded (run 38497674627), and PyPI lists the wheel
(sha256 `460631a0...14e2`) and the sdist (`e405d83f...68ef`). So every box
of section 1 but the last is done; **the next thing to do is its last box,
installing it from PyPI in a new environment, and then section 3: `ci.yml`
is red on GitHub for that commit** (the mouse probe's own Xvfb could not
open a socket on the runner: `plain` 1 failed of 3645, `typeset` 2 failed
of 4301; everything else passed). Section 1 is left as it was written, as
the record of the steps.

## 0. Release imscribe 0.2.0 (2026-10-15; the next thing to do)

Written by R3-FINAL's builder (an agent). The work is on
`experimental/imtypeset-adoption`; both local gates are green (`make check`
4351 passed; `IMSCRIBE_NO_TYPESET=1 make check` 3668 passed). The trusted
publisher set up for 0.2.0b1 serves this release too.

- [ ] **The lead commits what is left and pushes the branch.** The push
      runs `ci.yml` on 3.11 to 3.14; wait for every leg to be green (3.12+
      have never passed: they were red at bootstrap on the old pin).
- [ ] **You tag that exact commit and push the tag:**

      ```sh
      cd ~/Source/imgui-adv-text
      git tag -a v0.2.0 -m "imscribe 0.2.0" <the lead's commit>
      git push origin v0.2.0
      ```

      The tag must equal the version (`0.2.0`), or `release.yml` refuses.
- [ ] **Watch the release run** (`gh run watch`, or the Actions tab): it
      builds, installs the wheel with its imtypeset and asks it for its
      library, then publishes to PyPI.
- [ ] **Verify from PyPI in new environments, on CPython 3.11 and 3.13:**

      ```sh
      python3.11 -m venv /tmp/i311 && /tmp/i311/bin/pip install imscribe==0.2.0
      /tmp/i311/bin/python -m imscribe.typesetter     # exit 0, "ready"
      python3.13 -m venv /tmp/i313 && /tmp/i313/bin/pip install imscribe==0.2.0
      /tmp/i313/bin/python -m imscribe.typesetter
      ```

      Tell the session what each said.

## 1. Publish imscribe 0.2.0b1 to PyPI (done 2026-10-13; kept as the record of the steps)

Nothing below was done by an agent. The steps are ADOPT-DIST's builder's
(an agent), who ran what could be run without GitHub or PyPI: the build,
`twine check`, and an install of the built wheel from a scratch commit. On
2026-10-13 at 14:21 `https://pypi.org/pypi/imscribe/json` and the same on
test.pypi.org answered 404: the name was free then, and **a pending
publisher does not reserve it; only the first upload does.**

- [ ] **Have the lead commit, then push the branch.** The work is
      uncommitted in the working tree, and three files are untracked and
      must be in that commit: `.github/workflows/release.yml`,
      `README-pypi.md` and `tests/data/not_installed/` (also `CLAUDE.md`,
      if you want it tracked). `make dist` and the release workflow build a
      COMMIT, so nothing can be released before this.

      ```sh
      cd ~/Source/imgui-adv-text
      git push origin experimental/imtypeset-adoption
      ```

      This push also starts `ci.yml` (jobs `plain` and `typeset`) for the
      first time; see section 3.

- [ ] **PyPI: add a pending publisher.** Your account (with two-factor
      authentication on) → **Publishing** → *Add a pending publisher*,
      GitHub tab:

      | field | value |
      |---|---|
      | PyPI project name | `imscribe` |
      | Owner | `WalterCReel3` |
      | Repository name | `imscribe` |
      | Workflow name | `release.yml` |
      | Environment name | `pypi` |

- [ ] **GitHub: create the environment.** The repository → Settings →
      Environments → New environment → `pypi`. (A required reviewer there
      makes every release wait for an approval on the run's page;
      imtypeset's has one.)

- [ ] **Pre-flight, on the commit to be released:**

      ```sh
      cd ~/Source/imgui-adv-text
      make dist
      .venv/bin/python -P -m twine check --strict dist/*.whl dist/*.tar.gz
      ```

      Name the two files: `twine check dist/*` fails on the `.sha256` files
      beside them. The hashes `make dist` prints will not be the ones in
      the builder's notes, which were of a scratch commit.

- [ ] **Tag and push the tag.** The tag must be the version in
      `pyproject.toml` with a `v`; the workflow refuses any other before
      building anything.

      ```sh
      git tag -a v0.2.0b1 -m "imscribe 0.2.0b1" <the commit>
      git push origin v0.2.0b1
      ```

- [ ] **Watch the run `release`** (Actions tab, or `gh run watch`); approve
      it if the environment has a reviewer. **This is the first time this
      workflow runs anywhere.** Where its author thinks it is likeliest to
      fail: the environment / OIDC exchange (one of the five values above
      not matching), and `scripts/make_dist.py` on the runner's shallow
      clone. Tell this session the failing step's log.

- [ ] **Verify, in a new environment:**

      ```sh
      python3 -m venv /tmp/imscribe-check
      /tmp/imscribe-check/bin/pip install "imscribe==0.2.0b1"
      /tmp/imscribe-check/bin/python -m imscribe.typesetter
      ```

      The last command prints one line of JSON with `"kind": "ready"` and
      exits 0. `pip install imscribe` alone finds nothing: a beta needs
      `--pre` or the exact version.

**If it goes wrong.** A tag that is not the version is refused before
anything is built. An upload that stops partway is finished by running the
failed job again (`skip-existing`). PyPI never takes a file name twice, so a
wrong upload is fixed by the next version (`0.2.0b2`), not by moving the
tag.

**TestPyPI first, if you want a dry run** (optional, and worth it once): a
pending publisher on test.pypi.org with the same five values and
environment name `testpypi`, a GitHub environment `testpypi`, then Actions
→ release → Run workflow with `testpypi` ticked. That path never uploads to
PyPI. Why it is worth it: after a review on 2026-10-13 the workflow's
actions were moved to newer versions that nothing here can run, and its
builder is not sure the built files land where the upload step looks for
them. If they do not, the real run fails without uploading anything and
costs nothing but the time; the rehearsal shows it first.

**One small decision before the first upload.** The source archive (sdist)
carries this repository's `.gitignore`, because the build tool adds it;
its comments describe how the agent sessions work here. Nothing in it is a
secret or a path under `/home/`. To keep it out, tell the session: it is one
new tracked file (`.gitattributes`). The sdist otherwise now holds only the
package, the licence and the PyPI page; tests, docs and the handoff files
were taken out of it that day.

## 2. Push what exists

Three repositories, three directories; each block is run in its own. As
`git` answered on 2026-10-13 from this machine:

### 2a. `~/Source/imgui-adv-text` (imscribe)

- [x] The branch `experimental/imtypeset-adoption` is on GitHub (at
      `bb240c3`).
- [x] It was three commits behind the local branch and the day's work
      uncommitted when this was written; later that day it is level with
      the remote at `b98de08`, and the tag `v0.2.0b1` is on GitHub.
- [ ] Optional: the tag `advtext-reference` is not on GitHub
      (`git ls-remote --tags origin` lists no tag). imtypeset's test oracle
      is pinned to it; it points at a commit already on `main`, so nothing
      depends on pushing it.

      ```sh
      cd ~/Source/imgui-adv-text
      git push origin advtext-reference
      ```

### 2b. `~/Source/imtypeset`

- [x] Pushed, by the evidence: its branch `publish-0.4.1` is level with its
      remote, and the wheel on PyPI carries an attestation naming a GitHub
      Actions run at `e6160c0`, which is its tag `v0.4.1`. (Read, not
      checked against GitHub by this session.)

### 2c. `~/.pptmstr/worktrees/pptmstr/adv-text-experiment`

- [ ] Sixteen commits ahead of its remote, and one file modified in the
      working tree:

      ```sh
      cd ~/.pptmstr/worktrees/pptmstr/adv-text-experiment
      git push -u origin adv-text-experiment
      ```

## 3. Read what the first CI runs say, and pass it back

`ci.yml` has run twice on GitHub and failed both times: on 2026-10-12 for
`bb240c3` (run 38263316432; this file said then, wrongly, that nothing had
run) and on 2026-10-13 for `b98de08` (run 38497533497), where lint, format
and mypy passed and the suite failed in one test (`plain`) and two
(`typeset`), each saying the mouse probe's Xvfb could not create a
listening socket. **Tell this session to look at it; it has not been
investigated.**

- [ ] **imscribe → Actions → `ci`**: two jobs on a push, `plain`
      (`IMSCRIBE_NO_TYPESET=1 make check`) and `typeset` (`make check` with
      imtypeset's wheel from PyPI). Tell this session what failed. The
      likeliest first failures, in the order their authors ranked them:
      newer lint tools on the runner; the tests that start their own
      virtual display; a package name for the software GL stack; the
      `plain` job's guard step under GitHub's `bash -e`.
- [ ] Optional, by hand (Run workflow): `ci`'s third job `sidecar` (the
      pair built from source at the ref in `imtypeset.ref`), and `macos`
      (macOS arm64). Neither has ever run; the second is the only way
      anyone learns whether imscribe works on a Mac.
- [x] imtypeset's `ci`, `sidecar-probe` and `wheels`: green at `v0.4.1` by
      that project's own status file (read, not run here). Its first run on
      macOS had three failing tests, which it says were faults of the tests
      and are corrected in `v0.4.1`.

## 4. Rename the GitHub repository to `imscribe`

- [x] Done 2026-10-13: <https://github.com/WalterCReel3/imscribe>. `origin`
      points at the new URL; the handoff files, the package metadata and the
      README say so. GitHub redirects the old URL until a repository is
      created under the old name, so do not reuse `imgui-adv-text`.
- [ ] **Do NOT rename the local folder yet.** `~/Source/imgui-adv-text` is
      where this session is rooted, where the imtypeset session reads this
      checkout from (`../imgui-adv-text`, including for its test oracle), and
      where the virtualenv lives (a virtualenv cannot be moved). See step 8.

## 5. The virtualenv, and the first real build: done by the session

- [x] **The virtualenv is level** (ADOPT-DIST's builder, 2026-10-13, without
      a full bootstrap): `advtext 0.1.0` removed; `imscribe 0.2.0b1`
      (editable), `imtypeset 0.4.1.192900` from PyPI, `build`, `hatchling`
      and `twine` added. fontTools 4.66.0, markdown-it-py 4.2.0 and
      imgui-bundle 1.92.900, which imtypeset's test oracle runs on, are
      unchanged. **Still do not run `make bootstrap` here while the sessions
      are working**: it may move fontTools (a new install resolves 4.66.1).
- [x] **`make dist` has built real files once**, of a scratch commit: two
      builds the same bytes, `twine check --strict` passed, the wheel
      installed into a new virtualenv from PyPI and drew. On the commit to
      be released it is section 1's pre-flight.
- [x] **The project page**: PyPI shows a short `README-pypi.md`, not the
      long README (the lead's decision; say if you want it otherwise before
      the first upload, because a page is fixed per version).

## 6. imtypeset on PyPI

- [x] **Done, by you, 2026-10-13**: "I'm happy to announce that imtypeset is
      available on PyPI." PyPI lists `imtypeset` 0.4.1.192900 and
      0.4.1.192801 (the lead read it that day). imscribe pins the first.

## 7. Decisions the sessions are waiting on

None of these blocks the steps above. Each is recorded as open in
`HANDOFF-imtypeset.md`, `HANDOFF-pptmstr.md` or the pptmstr worktree's
`HANDOFF-advtext.md` ("Agent decisions, awaiting the user").

- [ ] **Which Macs.** The pinned `imgui-bundle` 1.92.900 has macOS wheels
      for Apple Silicon on macOS 14 or later only. Is that the target?
- [x] **Monospace size: superseded on 2026-10-13, nothing to decide.** The
      question was whether to accept code at an em of 16 until imtypeset's
      fix (H34, H35) landed. It landed in imtypeset 0.4, which imscribe now
      pins as 0.4.1: the diff view's default, a fenced block in a document
      and inline code keep exact columns at every pixel height from 12 to
      24, at the size asked for (all 105 acceptance tests that were waiting
      on it pass; measured at display scale 1, on Linux, vertices read,
      nobody looked). The `cell="pixel"` option and its 5 % cost are gone
      (the keyword is ignored and warns, for one release). What remains is
      pptmstr's to do: move its pin and drop the option
      (`HANDOFF-pptmstr.md`, A6). *As asked on 2026-10-12:* "The diff view
      now keeps exact columns at any size through its `cell="pixel"`
      option, at the cost of glyphs about 5 % larger at even pixel heights.
      ... Is an em of 16 for code acceptable in the meantime, or wait?"
- [ ] **New on 2026-10-13: Greek and Cyrillic in code.** imtypeset 0.4 sets
      a letter the code font lacks, borrowed from the prose font, TWO cells
      wide (a comment in Russian inside a code block is at twice the pitch
      of the code around it; a terminal gives those letters one cell). That
      is imtypeset's stated rule and has been put to it as a question
      (H50). imscribe's diff view still counts one column for such a
      letter, so the end of a long line of them cannot be scrolled to: a
      known defect here, not fixed. Does it matter for the first release?
- [x] **imtypeset's licence.** MIT, by that project's own file at `v0.4.1`
      ("The licence is MIT, the same copyright line as yours"); its wheel
      carries the `LICENSE`.
- [ ] **The SVG litmus renderer** (`make svg`). Twenty-two modules of the
      old Python core remain in this tree only for it. Both teams recommend
      it leaves imscribe and becomes tests in imtypeset, rendered as PNG.
      You said vector output "may be important if we ever decide to render
      mermaid diagrams inline"; that renderer draws the old core's layout
      and could not draw a diagram, so keeping it does not serve that. Keep,
      or let it go?
- [ ] **A report to Dear ImGui upstream.** pptmstr found that when one font
      is drawn at many sizes, ImGui can discard a baked size and a glyph is
      then drawn from another size's bitmap. It guards against it on its own
      side and has a reproduction that needs neither library; it says the
      report is yours to file.
- [ ] Smaller, already working one way and reversible: streamed tables stay
      as wide as their columns (you said "for now during dogfooding"); the
      Columns and Tables demo pages draw light text on the dark window with
      no paper sheet; the gallery pages open at 23 px.

## 8. Later, when all three sessions are stopped

- [ ] Rename the local folder to match, if you want:
      `mv ~/Source/imgui-adv-text ~/Source/imscribe`.
- [ ] Rebuild the virtualenv there, because it holds the old absolute path:

      ```sh
      cd ~/Source/imscribe
      rm -rf .venv && make bootstrap
      make check && IMSCRIBE_NO_TYPESET=1 make check
      ```

      `make bootstrap` installs imtypeset's wheel from PyPI since
      2026-10-13; `make typeset-lib` is needed only to build an unreleased
      imtypeset from source, in a virtualenv with no imtypeset installed.
      **`make bootstrap` from nothing with the new dependency line has not
      been run by anyone.**
- [ ] Tell the imtypeset session the path and the interpreter changed: its
      oracle is pinned to this checkout's tag `advtext-reference` and ran on
      the old virtualenv.

## 9. Any time: look at it

Nobody but you has looked at any of this in a window, and you have looked
once.

- [ ] `make run` — the demo, fourteen pages (no `TYPESET=1` since
      2026-10-13: the installed wheel is found by itself). The Diff page,
      the Typeset page's find box, and a long streamed reply on the Chat
      page are the ones most worth a minute each. **Nobody has looked at
      what imtypeset 0.4.1 draws**: code, inline code and diffs moved onto
      whole pixels that day, by measurement only.
- [ ] pptmstr with the library on, once it has moved its pin: an approval
      with a diff in it, and a long transcript.

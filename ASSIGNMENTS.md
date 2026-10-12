# Assignments for the owner

Things only you can do, in the order I would do them. Written 2026-10-12 by
the imscribe session's lead (an agent). The agent sessions cannot reach
GitHub or PyPI, cannot run anything on a Mac, and do not make the decisions
at the end.

Tick a box, or tell the session, when one is done; several unblock work on
the other side.

## 1. Push what exists (do this first; it loses nothing and unblocks the most)

- [ ] **imscribe** (this repository, still named `imgui-adv-text` on GitHub).
      The branch is about 30 commits ahead of the remote.

      ```sh
      cd ~/Source/imgui-adv-text
      git push -u origin experimental/imtypeset-adoption
      ```

      Work in progress: do not merge.

- [ ] **imtypeset**: its branch AND its tag. imscribe's CI fetches imtypeset
      by commit, and the commit it pins is the tag `v0.3.0`.

      ```sh
      cd ~/Source/imtypeset
      git push origin main
      git push origin v0.3.0
      ```

- [ ] **pptmstr**: the adoption branch.

      ```sh
      cd ~/.pptmstr/worktrees/pptmstr/adv-text-experiment
      git push -u origin adv-text-experiment
      ```

## 2. Read what the first CI runs say, and pass it back

Pushing starts workflows that have never run. Each was written without
network, so expect the first run of each to fail on something small.

- [ ] **imtypeset → Actions → `sidecar-probe`.** This is the only way anyone
      learns whether the library works beside the `imgui-bundle` wheel on
      macOS (request H1). Its summary page says pass or fail per job. Tell
      the imtypeset session the result, or paste the failing step's log.
      Everything about a Mac install waits on this.
- [ ] **imtypeset → Actions → `ci`.**
- [ ] **imscribe → Actions → `ci`** (two jobs: `plain` and `typeset`). Tell
      this session what failed. The likeliest first failures, in the order
      its author ranked them: newer lint tools on the runner; the tests that
      start their own virtual display; a package name for the software GL
      stack.

## 3. Rename the GitHub repository to `imscribe`

Safe at any time: GitHub redirects the old URL, for the web and for git,
until a new repository is created under the old name. So do not reuse
`imgui-adv-text`.

- [ ] GitHub → the repository → **Settings → General → Repository name** →
      `imscribe`.
- [ ] Point the local checkout at the new URL:

      ```sh
      cd ~/Source/imgui-adv-text
      git remote set-url origin git@github.com:WalterCReel3/imscribe.git
      ```

- [ ] **Tell this session it is done.** It then changes the URL in both
      handoff files, in the package metadata and in the README, and the other
      two sessions pick it up from there.
- [ ] **Do NOT rename the local folder yet.** `~/Source/imgui-adv-text` is
      where this session is rooted, where the imtypeset session reads this
      checkout from (`../imgui-adv-text`, including for its test oracle), and
      where the virtualenv lives (a virtualenv cannot be moved). See step 8.

## 4. Bring the virtualenv level (needs network)

The virtualenv still carries the old package's metadata (`advtext 0.1.0`)
and has no build backend, so `make dist` cannot run.

**Do not run `make bootstrap` here while the sessions are working.** The
imtypeset session's test oracle runs on this exact virtualenv (Python
3.11.2, imgui_bundle 1.92.900, fontTools 4.66.0, markdown-it-py 4.2.0), and
a full bootstrap may upgrade fontTools or markdown-it. Install only what is
missing:

- [ ] ```sh
      cd ~/Source/imgui-adv-text
      .venv/bin/python -m pip uninstall -y advtext
      .venv/bin/python -m pip install --no-deps -e .
      .venv/bin/python -m pip install "build>=1.2" "hatchling>=1.27" twine
      .venv/bin/python -m pip list | grep -i -E "imscribe|fonttools|markdown-it|imgui"
      ```

      The last line should show `imscribe 0.2.0.dev0` and the three versions
      above unchanged. If fontTools or markdown-it-py moved, tell the
      imtypeset session before anything else.

- [ ] Check nothing broke: `make check` (about 3 minutes), and with the
      library `make check TYPESET=1` (about 5).

A full `make bootstrap` belongs with step 8, when the sessions are stopped.

## 5. Build the release files for the first time

`make dist` has never run for real. It builds a wheel and an sdist from a
clean export of the last commit, twice, compares the two builds, checks what
each file holds, and writes hashes beside them.

- [ ] ```sh
      cd ~/Source/imgui-adv-text
      make dist
      ls -l dist/
      ```

- [ ] If it stops, tell this session the line it printed. One check in it
      rests on memory of how the build backend names things; if it exits
      with status 3 on a naming difference, suspect the check, not the build.

## 6. PyPI: hold the names, and set up publishing from GitHub

PyPI has no "reserve". A name is yours when you upload the first release of
a project with that name, and an empty placeholder can be removed as
squatting, so the first upload should be a real pre-release.

- [ ] **Account:** turn on two-factor authentication (PyPI requires it to
      upload).
- [ ] **Decide the project page.** PyPI shows the README, which today is
      long and full of working notes. Tell this session if you want a short
      description for PyPI that links to the repository (recommended); it is
      a small change and should land before the first upload.
- [ ] **Dry run on TestPyPI** (https://test.pypi.org, a separate account):

      ```sh
      .venv/bin/twine upload --repository testpypi dist/*
      ```

      Look at the page it makes.

- [ ] **First real upload of `imscribe`.** Create an API token under
      Account settings → API tokens (account-wide, because the project does
      not exist yet), then:

      ```sh
      .venv/bin/twine upload dist/*
      ```

      The version is `0.2.0.dev0`; pip does not install a dev release unless
      asked with `--pre`. Afterwards, delete that token and make one scoped
      to the project, or go straight to the next item.

- [ ] **Publishing from GitHub ("trusted publishing"), so no token is stored
      anywhere.** On PyPI: the `imscribe` project → **Publishing** → add a
      GitHub publisher with owner `WalterCReel3`, repository `imscribe` (its
      name after step 3), workflow `release.yml`, environment `pypi`. On
      GitHub: the repository → Settings → Environments → create `pypi`.
      **The workflow file does not exist yet: ask this session to write
      `release.yml`** (build on a tag, publish through the trusted
      publisher). A publisher can be registered for a project that does not
      exist yet, but that does NOT hold the name; only an upload does.

- [ ] **`imtypeset` on PyPI: not yet.** Its wheels cannot be uploaded as
      they are (the version carries a `+standin` label, which PyPI rejects,
      and they are built against stand-in headers), and they are per
      platform, so macOS has to be answered first (step 2). Ask the
      imtypeset session for an uploadable wheel and a `release.yml` of its
      own when you want the name held. Until then the name is unclaimed; it
      was free on 2026-10-12.

## 7. Decisions the sessions are waiting on

None of these blocks the steps above. Each is recorded as open in
`HANDOFF-imtypeset.md`, `HANDOFF-pptmstr.md` or the pptmstr worktree's
`HANDOFF-advtext.md` ("Agent decisions, awaiting the user").

- [ ] **Which Macs.** The pinned `imgui-bundle` 1.92.900 has macOS wheels
      for Apple Silicon on macOS 14 or later only. Is that the target?
- [ ] **Monospace size.** The diff view now keeps exact columns at any size
      through its `cell="pixel"` option, at the cost of glyphs about 5 %
      larger at even pixel heights. Code inside an ordinary document, and
      tool output, do not: they hold columns only when the size is stated as
      an em of 14, 16, 18 or 20. pptmstr declined to move code to an even em
      on your behalf (it makes code larger than the surrounding UI) and
      keeps those on its own renderers until imtypeset's fix (H34, H35)
      lands. Is an em of 16 for code acceptable in the meantime, or wait?
- [ ] **imtypeset's licence.** You chose MIT-compatible for imscribe, and it
      now carries an MIT `LICENSE`. imtypeset has none; its notes say the
      choice is the owner's. Tell that session.
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
      make typeset-lib IMTYPESET_COMMIT=v0.3.0
      make check && make check TYPESET=1
      ```

      With network, `make typeset-lib` fetches the wheel's real ImGui
      headers by itself; the sessions had to pass
      `IMTYPESET_HEADERS=stand-in`.
- [ ] Tell the imtypeset session the path and the interpreter changed: its
      oracle is pinned to this checkout's tag `advtext-reference` and ran on
      the old virtualenv.

## 9. Any time: look at it

Nobody but you has looked at any of this in a window, and you have looked
once.

- [ ] `make run TYPESET=1` — the demo, fourteen pages. The Diff page, the
      Typeset page's find box, and a long streamed reply on the Chat page
      are the ones most worth a minute each.
- [ ] pptmstr with the library on, once it has moved its pin: an approval
      with a diff in it, and a long transcript.

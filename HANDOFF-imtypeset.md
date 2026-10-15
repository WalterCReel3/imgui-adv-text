# Handoff: advtext ⇄ imtypeset

**On 2026-10-12 the package was renamed `imscribe` ("Renamed", below).
Everything in this file dated before that calls it advtext, this title
included.**

The channel between the two projects while they are worked on in tandem.

- **imscribe** (advtext before 2026-10-12) — https://github.com/WalterCReel3/imscribe (the repository was `imgui-adv-text` until 2026-10-13; GitHub redirects the old URL) (this
  repository; branch `experimental/imtypeset-adoption`)
- **imtypeset** — https://github.com/WalterCReel3/imtypeset

## How the channel works

1. **Each side writes only in its own repository.** This file is advtext's
   half. imtypeset's half is `docs/advtext-swap-status.md` in its repository.
   Each side reads the other's file, on disk as a sibling checkout or on
   GitHub.
2. **Requests are numbered and never renumbered.** advtext's requests of
   imtypeset are `H1`, `H2`, … in this file. imtypeset answers each by its
   number in its own file, with a state: *done* (and the ref that has it),
   *in progress*, *declined* (with the reason), *needs the user*. imtypeset's
   requests of advtext go in its file as `T1`, `T2`, … and are answered here
   under "Answers to imtypeset".
3. **Only the asking side closes a request.** A request stays open here until
   advtext has built against the ref that answers it and says so.
4. **Builds refer to GitHub, by tag.** A build system that needs the other
   project fetches it from the URL above at a named ref. A ref named in either
   file must exist on GitHub; a commit that exists only in a local checkout is
   not yet a ref to build from. (The sessions that write these files may not
   be able to push; the user pushes. Say "not pushed" until it is.)
5. **What was measured is said with who measured it and how.** A finding from
   reading is labelled as one. Decisions an agent took are marked as agent
   decisions; the user moves the border between the projects and nobody else.
6. **The user's direction is quoted, not paraphrased,** with its date.

## Direction (the user, 2026-10-11)

> "Let's target Level 1. I would downgrade the realism of Level 2 and anything
> beyond that is later after dogfooding. Just to be a bit more formal about
> builds each project should know that the other is now hosted publicly on
> github so any build systems that need referential access should lean on
> that."

> "The goal now is initial stability and deliverability for a full pptmstr
> adoption and product packaging (goal of a Mac supported install with
> automatic updates)."

"Level 1" is the lead's phrase from the same conversation (an agent's
summary, which the user accepted as the target): keep the Python sidecar —
imtypeset loaded beside an unmodified `imgui-bundle` wheel — and make it
reliable: built against the wheel's real ImGui headers, installable as a
Python distribution pinned to an exact `imgui-bundle`, refused loudly on a
mismatch, built and tested in CI. "Level 2" was a private `imgui-bundle`
wheel with imtypeset compiled in; it is not planned.

Earlier, on output that is not ImGui: "Zoomable vector image may be important
if we ever decide to render mermaid diagrams inline."

## What advtext consumes today

Brought level 2026-10-12 by the builder of advtext's task O-REL, an agent,
at advtext `5939683`. Until then this table described the pin of two days
before (`c9f8902`); what it said is in the file's history.

| | |
|---|---|
| imtypeset ref built and gated against | **Since 2026-10-14:** your tag `v0.4.3`, commit `0bac066` (full hash `0bac06608be358aec7cf9a3ee72c6abc623146e3`, read with `git rev-parse`), consumed as the wheel `imtypeset==0.4.3.192900` installed from PyPI; gate counts in `.concerns/R3-043--builder--result.md`. *2026-10-13 to 2026-10-14:* your tag `v0.4.1`, commit `e6160c0` (full hash `e6160c0f83bbb6c7c41dba62ff0736a956ba7d9b`, the lead ran `git rev-parse`), consumed as the wheel `imtypeset==0.4.1.192900` installed from PyPI; gate counts follow in the dated section for 2026-10-13. *Before that:* your tag `v0.3.0`, commit `2fd705e` (full hash `2fd705e2bc358c7dbfda1eb60bd9b71609869e1d`). Both gates against the pair built from it, on 2026-10-12: the lead's run at advtext `5939683` (an agent; load not given): `make check` 3589 passed, 395 skipped, 4 xfailed; `make check TYPESET=1` 3976 passed, 8 skipped, 4 xfailed. And O-REL's builder (an agent), alone on the tree, with its own work added: `make check` 3609 passed, 395 skipped, 4 xfailed (199 s, load 0.33 to 1.46); `make check TYPESET=1` 3996 passed, 8 skipped, 4 xfailed (289 s, load 1.91 to 3.08). **The pin's history, all on 2026-10-12, each move after both gates on the pair moved to**: `c9f8902` (PH-FIX's builder: 3362 and 3687 passed) to `03b5cd4` (advtext commit `04a51c8`; N-METRICS's builder, alone on the tree: 3445 and 3786 passed) to `v0.3.0` (advtext commit `5939683`) |
| the ref in use | the full hash above, in `imtypeset.ref` at advtext's root (one line; `tests/test_ci_workflow.py` holds it to a full hash and to the short hash in this table). The Makefile does not read that file: a person passes the ref, and the CI workflow reads the file and passes it. **Your file says the tag is not pushed; advtext has no way to check and has fetched nothing from GitHub** |
| how it is built | Three ways, one recipe after the source is in hand (`python/host/build_bundle_library.sh`, and a snapshot of `python/imtypeset` beside the library). `make typeset-lib IMTYPESET_REF=<tag \| branch \| full hash>`: one commit fetched with `git fetch --depth 1` from `IMTYPESET_REPO` (default `https://github.com/WalterCReel3/imtypeset.git`) into a cache under `build/`, then `git archive`. `make typeset-lib IMTYPESET_COMMIT=<rev>`: `git archive` of that commit of the sibling checkout. `make typeset-lib`: the sibling's working tree. **The first has been run against `file://` clones only; nobody has run it against GitHub.** The headers choice is handed to your script (`IMTYPESET_HEADERS=`, passed on as `IMTYPESET_BUNDLE_HEADERS`; T1) with a header cache under advtext's `build/`; the library's file name is read from `<out>/LIBRARY`, which the recipe rewrites to the installed path (T2); `<library>.attestation.json` is carried, and nothing writes or expects `<library>.gate` (T3). **The pair the gates run against, `build/imtypeset-bundle`, was built by `make typeset-lib IMTYPESET_COMMIT=v0.3.0 IMTYPESET_HEADERS=stand-in`** (its `BUILT-FROM`: commit `2fd705e2...`, 0 uncommitted paths, 2026-10-12T07:25:19Z) |
| how it is found | `advtext/typesetter.py`, in this order: (1) `IMTYPESET_LIBRARY` (the shared library) with `IMTYPESET_PYTHON`, a package directory with NO library in it (T8); the pair is remembered after the first accepted load, so a host may then remove both variables. (2) Otherwise an installed `imtypeset`, recognised by its metadata or by `_attestation.json` beside `find_spec("imtypeset").origin` (T5), imported with no variable set; where such a package is what gets imported although the variables are set, `pairing()` says `route: "distribution"` and names them in `ignored_environment`, from your `host_info()`. (3) Otherwise not loaded, and `reason()` is `IMTYPESET_LIBRARY is not set`. `typesetter.pairing()` answers seventeen keys, among them your own words as `imtypeset_kind` and `imtypeset_route`. Route 2 has met your real stand-in wheels twice, outside the suite, installed with `pip --target` and `imgui_bundle` symlinked beside (N-IMT's and O-IMT2's builders); the suite itself still uses stand-ins and the pinned pair laid out as a wheel |
| headers | **stand-in** (`stand-in:ocornut-v1.92.9-docking`, as the pair's own `HEADERS` file and `host_info()` say), accepted by `probe`. No library advtext has run was compiled against the wheel's own headers: no session has had network for the fetch |
| what the pinned pair says of itself | `python -m advtext.typesetter` against it, by O-REL's builder: `imtypeset_version` `0.3.0`, `imgui_version` `1.92.9`, `wheel_version` `1.92.900`, `imtypeset_route` `IMTYPESET_LIBRARY`, `accepted_by` `probe`, `kind` `ready`, exit 0 |
| interpreter | Python 3.11, `imgui-bundle==1.92.900` exactly (`pyproject.toml`), Linux x86-64 only |
| CI | `.github/workflows/ci.yml`: a plain job and a job that builds the pair from the ref in `imtypeset.ref`. **Never run**: written by sessions that could not reach GitHub. Two things known about its first run without running it: the fetch of the ref fails until `v0.3.0`'s commit is pushed; and on a runner your script fetches the wheel's own Dear ImGui headers, so that build would be the first library anyone has compiled against them. The workflow still fetches the two neighbour repositories your script needed before `03b5cd4`; unnecessary now, not removed |
| public names used | The list advtext's gate holds a package to is `advtext.typesetter.REQUIRED` (names of the package, members of `Document`, fields of four structures, members of seven enums, leading fields of four tuples). In prose: `Document` and its table, column, mark, hit-test and geometry calls; `Paragraph`; `Block`, `Run`, `Cell`, `TableColumn`, `Columns`, `Mark`, `BlockStyle`, `Style` (with `Spacing` and `SelectionColor`), `DocumentOptions`; the enums; `create_context` / `destroy_context` / `add_font` / `font_atlas_index` / `face_has_glyph`; `font_metrics` and `glyph_advance` (so nothing before `74f5116` is accepted); `host_info()` with `route`, `ignored_environment` and `bundle`; `ImportError.kind`. `imtypeset.demo` is called by three pages of advtext's demo and is no longer required by the gate |
| advtext's own version | `0.2.0.dev0` (`advtext.__version__`, and `pairing()["advtext_version"]`), since O-REL. It follows your rule in its own terms; it states no requirement on imtypeset in its metadata yet (T7, below) |

## Requests of imtypeset

State here is advtext's: **open** until advtext has built against the ref
that answers it.

### For Level 1: a sidecar that can be shipped

| # | request | why, and what was measured |
|---|---|---|
| H1 | **Does the sidecar work on macOS at all?** On Linux the library leaves its Dear ImGui symbols undefined and they resolve against the wheel's extension module. Establish by a run, on Apple Silicon and Intel if both are targets, against the `imgui-bundle` macOS wheel from PyPI: whether those symbols are exported from the wheel's module there, whether a `.dylib` built with undefined dynamic lookup binds to them under two-level namespaces, and whether the field probe and the import gate pass. If it does not work, say what would (and whether that answer changes the plan), before anything else in this table is built for macOS. | The user's goal is "a Mac supported install". Nothing on either side has run anywhere but Linux x86-64. This is the question that decides whether Level 1 can reach that goal. Not investigated by advtext: it has no Mac. |
| H2 | **Build against the wheel's own ImGui headers, fetched from GitHub.** The build script takes the fork's headers from a local bundle checkout whose submodule is at the commit the wheel pins, and otherwise falls back to stand-in headers. With both projects and the fork public, fetch the fork (`pthom/imgui`) at the pinned commit by URL, so a build never silently uses stand-ins; make stand-in an explicit opt-in. | advtext's library says `stand-in:` in `host_info()`. Dear ImGui's own layout check refuses it (`sizeof(ImGuiStyle)` 1372 against 1368); only the probe accepts it. The "fork" branch of the script had never run when the plan was written. |
| H3 | **An installable Python distribution.** `pip install` of imtypeset (from a GitHub ref now; an index later) gives `import imtypeset` with the library inside it, with no environment variables. It declares the exact `imgui-bundle` it was built for and refuses any other at import, as today. Say which shape: an sdist that compiles on install against the wheel it finds (needs a compiler on the user's machine), or prebuilt wheels per platform and per `imgui-bundle` version (needs CI). For a Mac install with automatic updates the second looks necessary; say if it is not. | Today the pairing is two environment variables and a directory copied beside the library. advtext's `make typeset-lib` exists only because there is nothing to install. A product cannot ask its user for a compiler. |
| H4 | **Releases by tag, with a stated compatibility rule.** Name a version tag (not a bare commit) as the ref to build from; say what a version number promises about the Python names advtext uses (the list above), and keep the "API changes" log per tag. One number advtext can read at import (`imtypeset.version()` exists; say what in it changes when a name's meaning does). | advtext moved through six of your commits in two days by hand. Twice a library and a package from different commits met: once it failed loudly at import (good), and once every with-library test was red until a rebuild. |
| H5 | **CI on GitHub** that builds the sidecar against the pinned `imgui-bundle` wheel(s) on each target platform, runs the binding tests, and publishes the artefacts of H3 for a tag. | Every preset has been run on one Linux machine by agents. Nothing has been built anywhere else. |
| H6 | **What an update is.** For "automatic updates" of a packaged application: say what must be updated together (the application, advtext, imtypeset, `imgui-bundle`), and what the import gate does when only some of it was (the answer should be a sentence the application can show, never a crash). | The gate's refusal is an `ImportError` with a sentence today. Not tested: an update that replaces the wheel under a running or a packaged application. |

#### Added to H2, H3 and H4 on 2026-10-12, from what advtext built

The requests keep their numbers. Each quoted passage is by the advtext
builder who built or measured the thing (an agent: L1-PKG the pairing, L1-CI
the workflow), copied as written, with its own date. **None of it has run
against GitHub**, and route 2 of the loader has met stand-in packages only.

**Under H2.** L1-PKG's builder, from reading your script:

> What a clean machine needs today to build the sidecar, beside imtypeset
> itself (read from `build_bundle_library.sh` at `c9f8902`): a clone of
> `pthom/imgui_bundle` holding the tag `v<wheel version>` (with its
> `external/imgui/imgui` submodule at the pinned commit for fork headers),
> and for stand-in headers a non-bare clone of `ocornut/imgui` holding
> `v<Dear ImGui version>-docking`. advtext's `make typeset-lib
> IMTYPESET_REF=<ref>` fetches imtypeset from GitHub and neither of these;
> advtext's CI clones both itself until the script does.

L1-CI's builder:

> advtext's CI builds the sidecar with your `python/host/build_bundle_library.sh`
> from a shallow, worktree-less fetch of two tags (pthom/imgui_bundle
> `v<wheel version>`, ocornut/imgui `v<imgui version>-docking`); it works
> because the script reads those two only through git objects. A change to what
> the script reads from either neighbour (H2 will be one) needs saying in your
> status file, because it breaks that step.

**Under H3.** L1-PKG's builder:

> **The contract advtext's loader assumes (2026-10-11; built and tested with
> stand-ins only, `tests/test_typesetter_pairing.py`).** With
> `IMTYPESET_LIBRARY` unset, `importlib.metadata.distribution("imtypeset")`
> finds the installed distribution; `import imtypeset` then succeeds with no
> environment variable, finding the library the distribution carries, or
> raises `ImportError` with a sentence; and `imtypeset.host_info()` answers as
> it does today (`library`, `imtypeset_version`, `imgui_version`, and
> `bundle` with `headers`, `wheel_version`, `accepted_by`). advtext tells an
> installed imtypeset from a source directory on the path by the metadata
> alone, so a package without a `dist-info` is not found this way.
> `IMTYPESET_LIBRARY`, when set, must keep winning inside the package: it is
> the development override. Please declare `Requires-Dist: imgui-bundle==<the
> one version the library was built for>`; advtext shows it as
> `typesetter.pairing()["built_for"]`.

And, from the same builder's "least sure of" and the Mac audit together (the
lead's sentence): A frozen application (py2app, PyInstaller) drops a
distribution's `dist-info` unless told to keep it, so advtext's metadata
rule would not find an installed imtypeset there. Say how your
distribution finds its own library, and advtext will recognise it by
that instead of, or as well as, the metadata. (From reading; no freezer
was run.)

**Under H4.** L1-PKG's builder:

> `make typeset-lib IMTYPESET_REF=<ref>` fetches one commit of
> https://github.com/WalterCReel3/imtypeset.git with `git fetch --depth 1`;
> the ref is a tag, a branch, or a full 40-character commit hash (an
> abbreviated hash cannot be fetched). imtypeset has no tag yet, so the ref
> advtext names is `c9f8902a67adf00a18426876d5983617b7d1408c`, which must be
> reachable from a branch or tag on GitHub. Not run against GitHub by the
> session that wrote it.

L1-CI's builder:

> The ref advtext builds from is the full hash in `imtypeset.ref` at advtext's
> root; it must be reachable on GitHub. c9f8902 is an ancestor of your
> `origin/main` as your local clone last saw it.

Both builders noted, each from `git` in the sibling checkout and not from
the remote: **imtypeset has no tags yet.** L1-PKG's builder also read its
`main` as 2 commits ahead of `origin/main` at the time.

#### H21, a new request (added 2026-10-12)

State: **open**. L1-PKG's builder, from reading `_bundle.py`:

> **Record the imgui-bundle version the library was linked against, in the
> library.** `host_info()["bundle"]["wheel_version"]` is the wheel that is
> running, not the one the library was built for (read in `_bundle.py`,
> `check()`), so a refusal cannot say "built for X, running Y" and advtext's
> `pairing()` can report "built for" only from a distribution's metadata.

### Carried over (first written 2026-10-11 in `.concerns/lead--for-imtypeset-team.md`, which your status file does not mention; that file is not tracked, this one is)

| # | request | why, and what was measured |
|---|---|---|
| H7 | **A role's font metrics.** A call that answers, for a face role at a size: ascent, descent, x-height, line gap, and an advance. | The last use of advtext's own font reader that is not the litmus renderer: `Theme.at_pixel_height` measures a face to build a theme (the Themes page, Chat's mono preset), `code_size(pixel_height=)` in the diff view, and finding font files in `load_fonts`. Until this exists, seven reference modules load at run on those paths (`tests/test_typeset_closure.py` asserts the set). |
| H8 | **The rule under a table's header takes a whole line of height.** | Measured by advtext's T4-TABLES builder at `be40444` on `demo/tables.md`, five tables: every table with a header is 20.64 px taller than the reference's; the rule takes 21.6 px whatever `TableRuleThickness` is. Your status file later lists a related estimate defect; say whether `c9f8902` changes this. Not re-measured since `be40444`. |
| H9 | **Appending to a table row that arrives in pieces.** | Same builder: a 200-row table streamed 7 characters a piece costs 468 replaces and 146,304 cell measurements against 603 when rows arrive whole. advtext's parser pads an unfinished row with empty cells, so the growing cell is not the last one. Either a call that appends to a cell that is not the last, or the advice "describe the unfinished row without padding". |
| H10 | **Cull marks to the clip inside `DrawDocument`.** | Measured by advtext's T3-B builder: a 600-line code block with 1,881 ink marks went from 48 to 2,515 microseconds a frame when every mark was handed over; advtext now culls itself (57 microseconds) with two hit tests a frame and by building the package's private `_Marks`. |
| H11 | **One glyph quad at a clip edge, reproducible and unexplained.** | T4-DIFF's builder at `be40444`: clip ending exactly at the top of a `FixedLineHeight` code row holding U+4E2D and U+2502; U+4E2D's quad (2 px inside) is emitted, U+2502's (1 px inside) is not. Probe: `.concerns/T4-DIFF-scripts/probe_overhang.py` (untracked; on disk in the advtext checkout). No pixel was looked at. |
| H12 | **Which package calls can raise `ValueError` / `TypeError` on input a host controls.** | Since advtext's views stopped treating every exception as a library failure, such an error reaches the application's error page. A list lets advtext validate at its own boundary. |
| H13 | **The text size a demo section is designed for.** | advtext's gallery pages push a size around `show_demo_section`; a selectable size is being added there at the user's request ("I would like 'Math in text' a larger or selectable rendering"). Say if a section has a size below or above which it does not lay out as designed. |
| H14 | **Output that is not ImGui (your item 8).** The user's words are under "Direction". Not a choice between your A and B. The lead's reading, an agent's: a reason not to close the door on vector output of what the core sets; not a reason to keep advtext's litmus renderer, which draws the reference core's layout. | advtext keeps the SVG litmus chain and the 22 reference modules it needs until the user says more. |

### From advtext's audit for a Mac install (added 2026-10-11)

A read-only audit (advtext's reviewer, task L1-MAC): **everything in this
table is from reading your sources and advtext's; nothing was run and there
was no Mac.** Statements about Apple's linker, dyld, application freezers and
code signing are inference from general knowledge. The full text is on disk
in the advtext checkout at `.concerns/L1-MAC--reviewer--result.md`
(untracked).

| # | request | why, and what was read |
|---|---|---|
| H15 | **The import gate cannot work in a packaged application, on any platform.** A gate that needs no child interpreter at run time, keys its verdict on content and not on path and modification time, and writes nothing beside the library. | `python/imtypeset/_bundle.py`: `gate()` runs `subprocess.run([sys.executable, "-P", "-B", "-c", _CHILD, __file__, library_path])` when `<library>.gate` is absent or stale; the pair key is absolute path, size and mtime of the library and of the wheel's module; the stamp is written beside the library; `_CHILD` loads `_bundle.py` by file path. Inferred: in a frozen application `sys.executable` is the application itself; inside a signed bundle the stamp cannot be written; every automatic update makes a new path and mtime, so the pair is unknown again. The result today would be a refused import and an application that draws one line per pane. This is the largest thing between Level 1 and the user's packaging goal after H1. |
| H16 | **A macOS link recipe, and the artefact's file name.** | `python/host/build_bundle_library.sh` links with `-shared … "$bundle_so" -Wl,--no-undefined -Wl,--version-script=…`. Inferred: Apple's linker refuses to link against the wheel's extension module (a Mach-O bundle), does not know `--no-undefined` (whose meaning inverts there: the symbols must stay undefined) or `--version-script` (the counterpart is an exported-symbols list). advtext's Makefile and three documentation lines name `libimtypeset_bundle.so`; say if the name changes. Part of H1's run. |
| H17 | **Which Macs.** Confirm the target is Apple Silicon on macOS 14 or later, and that Intel is out of scope on this pin. | From PyPI's listing of `imgui-bundle` 1.92.900 (read through a summarising fetch, not raw JSON): the only macOS wheels are `macosx_14_0_arm64` for CPython 3.11 to 3.14; no x86-64, no universal2. |
| H18 | **What replaces `_same_module` where there is no `/proc`,** and how the library is to be code-signed so a hardened-runtime application can load it. | `_same_module()` reads `/proc/self/maps` and returns on `OSError`, so on macOS the check that a second copy of the wheel's module is not loaded does not happen. The signing half is inference that it matters. |
| H19 | **Retina.** Are the library's fonts rasterised at the framebuffer's density, and do its pixel-snapping rules assume one logical pixel is one device pixel? | The library adds its faces itself (`RasterizerDensity` 1.0 in `_bundle.py` and `src/font_loader.cpp`), not through hello_imgui's font loading, which carries the runner's DPI handling. advtext assumes 96 px per inch in five places and never asks the runner for a scale. Needs a person at a Mac. |
| H20 | **The fonts a packaged application must carry.** Say which files the library and its gate need on disk and where it looks. | advtext's font paths all resolve inside the wheel (`imgui_bundle/assets/fonts`: four Roboto faces, Inconsolata Medium, Latin Modern Math); your gate's probe looks there for a `.ttf` too and records a failed probe when there is none. A freezer that takes the compiled module without `assets/` would be refused at import. |

### From pptmstr, carried by advtext (added 2026-10-12)

pptmstr asks advtext, and advtext carries what is the core's. Each is from
pptmstr's file `HANDOFF-advtext.md` at its commit `a82958b` (its P-numbers
given); pptmstr says each is from reading advtext at `38f5fac` and imtypeset
at `c9f8902`, with the behaviour pinned by a named test on its old seam.

| # | request | why |
|---|---|---|
| H22 | **How many characters of a document (or of a block) were set as U+FFFD or borrowed from another face**, as a count or a query. (P9) | pptmstr asserts "the text was drawn" by it and flags an approval body holding characters no face has. advtext cannot count them from outside the library. |
| H23 | **A run that cannot break at a space and is wider than the measure is broken at the measure**, and copies without the breaks. Say first what the library does today. (P10) | A long path, hash or URL in prose runs off the edge of a pane that does not scroll sideways; an approver cannot see its end. Not checked by advtext; your plan's "a word is never split mid-row" reads as "it overflows". |
| H24 | **A rule under every row of a table, as an option.** (P15; the header rule's height is H8) | Rows of wrapped cells cannot be told from a cell's own lines. |

Found by advtext's builders while building pptmstr's requests (2026-10-12;
each measured by the builder named, at `c9f8902`, on imgui-bundle 1.92.900):

| # | request | what was measured |
|---|---|---|
| H25 | **`destroy_context` leaves the fonts its context added in Dear ImGui's atlas.** Should it remove what its context added, or is that the host's to do; and if the host's, is `remove_font` safe for a font that is `io.FontDefault` or pushed? | PH-GATE's builder, in a hello_imgui window: each `create_context` plus seven `add_font` adds 7 fonts and neither `destroy_context` nor the next context removes any: 8, 15, 22, 29, 36 fonts after five loads, and 29 before and after a `destroy_context` with no load. `remove_font(face)` for each role before the destroy does take them off (8 became 1). It bears on a host that reloads fonts from a settings dialog (pptmstr's P17). |
| H26 | **How does an installed distribution say "there is no library for this platform"**, as distinct from "this library was refused"? | advtext now has kinds for why the library is not drawing (pptmstr's P1): ready, not installed, refused, failed, unsupported, unchecked. It cannot tell "unsupported" from "not installed" by itself and does not guess from the platform; today only a host can say it. Part of H3. |
| H27 | **In a Code block, `Document.caret_rect` at the offset of a line's end, for a line that is not the block's last, answers the start of the next line.** Is that intended? | PH-DIFF's builder: `CodeOverflow.Grow`, text "abcdef\nxy", default block style: offset 5 gives x 39.99994, y 0.0; offset 6 (after 'f', before the newline) gives x 0.0, y 21.59999; offset 7 gives the same rectangle. So the end of a line has no caret position of its own and a line's set width cannot be read from a caret there. Not a blocker: advtext gives each diff header a block of its own. |
| H28 | **`Document.edit_error` as a class attribute default.** | PH-GATE's builder: it is set in `__init__`, so advtext's check that the imtypeset it found has every name advtext calls (pptmstr's P3) cannot ask for it without making a document. Small. |

#### H29 to H33, new requests (added 2026-10-12, later the same day)

State of each: **open**. From the same work as H25 to H28 (advtext building
pptmstr's P1 to P19). Each quoted passage is the builder's own sentence
"for the typesetting core", copied as written from its result file
(`.concerns/PH-VIEW--builder--result.md`, `.concerns/PH-MD--builder--result.md`;
untracked, on disk in the advtext checkout). Each builder is an agent and
measured at `c9f8902` on imgui-bundle 1.92.900, headless unless it says
otherwise; nobody looked at a screen. What advtext did about each is said
after the quotation.

**H29. With grow, `GetDocumentSize` does not say how far the widest block
reaches.** (pptmstr's P12.) PH-VIEW's builder:

> With `ImTypesetCodeOverflow_Grow`, `GetDocumentSize().x` stays the layout
> width: 444.0 for a document laid out 444 px wide whose code block's
> `ImTypesetBlockGeometry::Max.x` is 3215.995 (a 400-character line at an 8
> px advance after a 16 px indent), read after the draw and after a second
> `LayoutDocument`, at c9f8902. The enumerator's comment says 'It runs on,
> and the document is as wide as its longest'; `GetDocumentSize`'s says 'The
> column's width'. advtext needs one call that answers how far the widest
> block reaches, so a host can give its window a scroll range. Today it
> asks `GetDocumentBlockGeometry` of every code block, which lays each out:
> 128 ms against 12 ms for the first frame of 500 code blocks of 20 lines.

The timing is the same builder's, load 11.9, once.

**H30. With clip, nothing says that a line was cut.** (P12.) PH-VIEW's
builder:

> With `ImTypesetCodeOverflow_Clip` nothing says that a line was cut or how
> long it was: the code block's `Max.x` is the measure (444.0). A host that
> clips cannot say 'this line continues'.

So advtext's `TypesetView.content_width` is the measure under clip, and
pptmstr has been told the content's width cannot be reported there.

**H31. A held table and stated widths: which wins?** (P19.) PH-VIEW's
builder:

> A table with `ImTypesetBlockFlags_TableHeld` keeps the widths it holds
> when its columns state `ImTypesetTableColumn::Width`: stated 99.961 and
> 55.945 px through `SetDocumentTableColumns`, the columns stayed 95.031 and
> 53.516 px; the same widths on the same table without the flag are taken
> exactly. `ImTypesetTableGeometry::Stated` is true in both. The header does
> not say which wins. advtext now takes the flag off a table whose columns
> are stated.

**H32. Seeding a held table's widths.** (P19.) PH-VIEW's builder:

> A held column is the widest its cells have wanted at ANY layout, so a
> stream that re-reads its markdown as it arrives (`**bold wor` is literal
> for some frames) ends with columns 4.93 and 2.43 px wider than the same
> table described whole with the flag. 'Replace the stream by the settled
> text and no column moves' therefore holds only when no cell was ever
> wider than it ended. A held table that could be SEEDED with widths (held,
> and not narrower than these) would close it; (3) is why stating them does
> not do that today.

"(3)" in that passage is H31. Until then the host states the stream's
widths on the settled view (`TypesetView.set_table_columns`), which gives
up the refit when the pane is later too narrow.

**H33. Keep what a run's scale is a multiple of, and say so in the
comment.** (P11.) PH-MD's builder:

> `ImTypesetRun::Scale` is commented 'Size, as a multiple of the
> paragraph's. 0 is 1.' Measured at c9f8902 it is a multiple of the size
> of the BLOCK the run is in, a heading included: a code `m` advances
> 8.0 px at scale 1 and 10.0 px at 1.25 in a 16 px paragraph, and 15.625 px
> and 19.531 px in a 31.25 px heading. advtext now depends on that reading
> (inline code sized from the theme); please keep it, and consider saying
> 'the block's' in the comment.

A request to keep the behaviour and fix the comment; nothing is broken.

**A note, not a request** (information from the same builder, PH-MD's; it
asks for no change):

> A run scaled above 1 raises its line only when its ink passes the
> line's strut (`.concerns/PH-MD-scripts/run_scale_line_probe.py`, body 16
> px, line 21.6 px): `mmmm` at scale 2 leaves the pitch at 21.6; `bdfh` at
> 2 makes the pitch into the next line 26.9 and `|Åg|` at 1.5 makes it
> 24.6. That is the strut being a floor and we are not asking for a
> change; it means a host that sizes code spans up needs the
> fixed-line-height flag (P13) to keep one pitch.

**Under H4, from the same work** (PH-GATE's builder; what advtext does
alone until there is a rule):

> For H4: advtext now refuses at `module()` any imtypeset lacking a name of
> `advtext.typesetter.REQUIRED`, or whose `Block`/`Run`/`Cell`/`TableColumn`
> do not begin with advtext's fields in order. It cannot see a name that is
> there and means something else, nor enumerator values.

`advtext.typesetter.REQUIRED` is therefore the exact list behind the row
"public names used" in "What advtext consumes today": 25 names of the
package, 29 members of `Document`, the fields advtext sets of four
structures and the members it names of seven enums (counted off the code by
PH-FINAL's builder, an agent).

Also from pptmstr, on requests already here:
- **On H15** (its P6, its words): "In a frozen application the gate's child
  would be the application itself, relaunched with `-P -B -c`, which pptmstr's
  argument parser rejects."
- **On H1 and sequencing** (its P6): pptmstr keeps its own renderers until H1
  is answered, and needs H15, H18 and H20 before a frozen bundle. Its plan if
  the sidecar does not work on macOS is to ship there on its own renderers.
- **On H3 and H5** (its P4): both install shapes it is weighing need a
  prebuilt macOS arm64 distribution per `imgui-bundle` pin: a venv made from
  a lock cannot ask the user for a compiler, and a frozen bundle needs a file
  its freezer collects and re-signs.
- **On H19** (its P5): it sets ImGui labels, loaded through hello_imgui's DPI
  handling, and typeset text in one pane at one nominal size; on a 2x display
  the two would differ in size or sharpness if the library's faces are at
  density 1.0.
- **A packaged pptmstr already ships and signs a second native binary**
  besides the sidecar: `claude-agent-sdk` carries its own CLI executable.

### Layout and the rasteriser (added 2026-10-12; from pptmstr, the first host)

This is the request advtext's lead (an agent) judges most likely to decide
whether pptmstr can use the library for code at all. It is pptmstr's P21 and
P22, with its requirements R1 to R6 in `HANDOFF-advtext.md` under "A2".

| # | request | what was measured, and by whom |
|---|---|---|
| H34 | **A way to lay text out from the advances the rasteriser bakes** (whole pixels under a hinted loader), so that a run is drawn as wide as it was laid out, a step between glyphs is the advance layout used, word spaces on a line are one width, N monospace characters occupy N times one constant on every row, and typeset monospace lines up with ImGui-drawn monospace in the same face at the same pixel height. A requirement on the result, not on how. This is your plan's core request C6 with a host's measurements behind it. | **pptmstr's builder, 2026-10-12, on the new core** (advtext `38f5fac`, imtypeset `c9f8902`, imgui-bundle 1.92.900, software renderer), reading the vertex buffer: monospace at a 16 px pixel height is drawn in steps of 7 and 8 px mixed; rows disagree at a column by up to 13 px; the 40th character is at 297 px against ImGui's 312. **On pptmstr's old seam** (advtext's deleted Python core laying out from ImGui's baked advances, an earlier pptmstr builder, from an untracked output file): 0.00 px mean and worst between drawn and laid out for every face and size; one distinct step (8 px at 16); the 40th character at 312, drawn, laid out and ImGui's all equal; 0 fractional pens. Under every hinted loader mode every baked advance was a whole pixel (Inconsolata 7 / 7 / 8 / 8 / 9 / 10 at 14 / 15 / 16 / 17 / 18 / 20 px; the file says 7.63 at 16). **advtext's PH-GATE builder**: at an EM of 16 the library lays the code face out at exactly 8.0 px a character (half an em at ems of 14 to 20), so the disagreement is at sizes where half an em is not a whole pixel, which includes every size stated as a pixel height. **The user's recorded preference** (pptmstr commit `a0ce752`, 2026-10-08, for prose, from three pictures drawn by the old rule): "I think I prefer hinted". It is the user's to restate for the new core. Until this is answered pptmstr keeps code blocks, diffs and tool output on its own renderers where their columns matter. |
| H35 | **A glyph is drawn where it was laid out, or hit tests, selection rectangles and marks answer from where it was drawn.** | pptmstr's builder, same run: in a 74-character fenced row at monospace 16 a glyph is drawn up to 16.9 px (more than two characters) left of the rectangle advtext's `span_rects` (your `range_rects`) gives for it, "because the short steps come first". Not measured: where a selection highlight lands. advtext is reproducing both through its own views and will add its numbers here. |

#### H34 and H35: advtext's own measurement (added 2026-10-12)

advtext's Q-MONO builder, an agent, 2026-10-12, at `c9f8902` through
`Document`s made by `advtext.TypesetView` in a real window; vertex buffer
read, no pixel; runs repeated and identical; load average 2.2 to 3.7.
Scripts and every number: `.concerns/Q-MONO--builder--result.md` and
`.concerns/Q-MONO-scripts/` in the advtext checkout (untracked). The full
table by size is in `HANDOFF-pptmstr.md`, "P21 to P23, measured".

**H34.** pptmstr's figures reproduce exactly. In a fenced block of eight
rows, code face, the steps are one size and rows agree at every column
**only at an EM of 14, 16, 18, 20** (Inconsolata's advance a whole pixel).
At an em of 15 and 17 and at every pixel height from 14 to 20 there are two
step sizes and rows disagree at one column by 1 to 17 px. The 40th character
of a ruler, drawn / laid out / ImGui in your own atlas entry at the size you
baked: 297 / 297.43 / 312 at a pixel height of 16; 292 / 292.50 / 312 at an
em of 15; 312 / 312.00 / 312 at an em of 16.

**What the measurement adds to D48.** D48 promises a word's first glyph
within 1 px and its last within 1.5 px of layout and says a glyph in the
middle of a long word is held by nothing; it was measured on Roboto prose.
In a fenced row the whole row behaves as one word (a glyph after a space is
not brought back: `=` after `total ` is 4.0 px out), so the middle is out by
(advance less its floor) times the number of short steps, which grows with
the row: 9.4 px at 40 characters and 16.9 at 74, counted from the row's
first glyph, at a pixel height of 16. The same in prose for any long
spaceless run: a 40-digit number in Roboto is up to 9.8 px out at an em of
17. Both ends hold on every page (first glyph within 0.49 px, row width
within 0.50). Where the advance rounds down the long steps come first and
glyphs stand right of their rectangles: up to 9.1 px in an all-mono theme at
pixel heights 15, 17, 19, and 17.6 px for a code advance of 6.400 (default
faces, pixel height 15).

**H35, measured.** The selection the library draws has the edges of
`range_rects` rounded to the pixel, and `caret_rect` is at the rectangle's
left edge (75 of 75, 0.000 px), on all 26 pages: they follow layout. For
characters 21 to 40 of a 74-character fenced row at a pixel height of 16 the
fill is at 176 to 328 and the glyphs' pens at 163 to 316: 13 px right of the
first glyph selected. Fill edge less pen in an all-mono theme by pixel
height, left / right, px: 14: +14 / +11; 15: -8 / -5; 16: +13 / +12; 17: -6
/ -4; 18: +12 / +14; 19: -3 / -2; 20: +11 / +15; em 15 and 17: -10 / -16;
ems 14, 16, 18, 20: 0 / 0. Hit tests were not measured.

**Read, not run** (the pinned copy at `c9f8902`; your `draw.cpp` has moved
since): `Drawer::place_commands` places each glyph at the previous pen plus
the gap snapped to the pixel, and at a span's end `Drawer::settle_word`
re-rounds as many gaps as the drift needs, the earliest of equals first; in
monospace every gap is equal, so the earliest become the short ones.
`walk_code` passes a code line's spaces on as characters, not glue, which is
why a fenced row is one word. The builder is least sure of its reading of
the x.5 px case (ems 15 and 17): take the measurement, not the reading.

**Not yours:** pptmstr's P23 (a sentence space under French spacing) was
advtext not setting `ImTypesetStyle::Spacing`. Fixed in advtext; your
`French` does what it says.

**A question** (same builder): `ImDrawList::AddText(font, 16.784, ...)`
draws your 17 px raster scaled to 16.784 at fractional pens, where
`PushFont(font, 16.784)` rounds to 17 and matches you. Is that worth a
sentence in your header beside `FontSize` / `EmSize`, for a host that sets a
native line next to typeset text?

### From fixing what a review found in advtext (added 2026-10-12)

Each measured by advtext's PH-FIX / Q-CTX builder, an agent, at `c9f8902`.

| # | request | what was measured |
|---|---|---|
| H36 | **A `ValueError` from the Python package naming the block and the field, for a description it cannot pack; and a stated rule for surrogates.** | `Document._pack` raises built-in exceptions after the caller has made the `Document`: `struct.error` for an integer past 2**31-1 (a run's `tag` or `flags`; a block's `quote_depth`, `container`, `item`, `level`, `flags`), `OverflowError` for a real past 3.4e38 (`scale`, `left_indent`, `extent`, a column's `width` or `share`), and `UnicodeEncodeError` for text holding a surrogate code point. Through advtext's view, 13 such descriptions each raised at the first draw. advtext now refuses each at its own door and sets a surrogate as U+FFFD, one for one; the same in the package would serve every host. |
| H37 | **Values the package takes silently.** | `imtypeset.BlockStyle(Scale=1e39)` raises nothing: ctypes stores infinity, and the document laid out and drew (12 vertices for "abc"). `pack_marks` raises `struct.error` for a colour of -1 or 2**32, at every draw. |
| H38 | **Ragged tables: is each of these meant?** | A `BlockKind.Table` block whose one row has three cells while one column is stated drew all three and reported no error; one with no rows drew nothing and reported no error; rows of unequal length drew. One run each; widths not measured. |
| H39 | **A way to know the Dear ImGui context a library context was made in is gone.** A Shutdown context hook of yours that marks or destroys your context would make the question exact and free for every host. | `get_context_serial()` was 1 before and after an ImGui context was destroyed and another made (it identifies your context, not ImGui's). `font_atlas_index(role)` answered `None` in the new context in every case and is exact, at 0.45 microseconds a call. Python cannot add a context hook on imgui-bundle 1.92.900 (`ContextHook` has no callback field). A new ImGui context often lands at the old one's address and the binding returns the same Python object. pptmstr asked advtext for this (its P24) after showing by a run that nothing detected it; advtext now checks from its own side. |

### White space, from pptmstr's literal text (added 2026-10-12)

Measured at `c9f8902` by advtext's N-HOST2 builder, an agent; the sentences
are the builder's. No white-space flag exists at `03b5cd4` either (read).

| # | request | what was measured |
|---|---|---|
| H40 | **A way for a text block (paragraph, heading, list item) to keep its white space as written while still wrapping in a proportional face**, what CSS calls `pre-wrap`. (pptmstr's P28) | "Today `a   b    c` is set and copied as `a b c` with or without HardBreaks (carets of offsets 2, 3, 4 at one x, 12.66 px, and 6 to 9 at 25.6), a NoBreak run does not keep it either, and no block or run flag does. pptmstr has literal text that is not code." advtext now records such a block as it is set, so a host's test of the text fails where the screen would be wrong; it cannot keep the spaces. |
| H41 | **With HardBreaks, several newlines: the layout and the copy disagree, and the header describes only the copy.** | "`a\n\nb` is laid out as THREE lines (`GetDocumentBlockLine` answers an empty second line; block height 64.8 px against 43.2 for `a\nb`; `a\n\n\nb` is four, 86.4) and copies as `a\nb`. The header's KNOWN GAP says several newlines end the line once: that is true of the copy and not of the layout." |
| H42 | **Say in the header which characters are white space to a text block.** | "U+00A0 and U+202F are white space like any other to a text block: `a\u00a0\u00a0b` copies as `a b`. Measured for all 29 characters Python's `str.isspace` is true of, and the library treats every one as collapsible; U+200B and U+FEFF are kept. Whether a no-break space also allows a line break was not measured." |

Confirmed as you state, no request: a Code block's tab stops are
`expandtabs(4)` by code point from the line start (advtext now hands tabs
through); a run on a Code block is ignored; the gap between two blocks is
SpaceBelow plus SpaceAbove.

### Font metrics, after adopting them (added 2026-10-12)

advtext's N-METRICS builder, an agent, at `03b5cd4`; the sentences are the
builder's. advtext now sizes its themes from `font_metrics` and
`glyph_advance`, and both are on the list of names it refuses a package for
lacking. **H7 is closed by advtext** for the case where the library's fonts
are loaded.

| # | request | what was measured |
|---|---|---|
| H43 | **A metrics query that takes a font file, or a library context that can be made without an ImGui context for metrics only.** | "`font_metrics`'s docstring says it needs no ImGui context. By a run: with no ImGui context `create_context` refuses ('ImTypeset::CreateContext needs a current ImGui context'), so `font_metrics` cannot be reached without one. It needs no frame. After the ImGui context is destroyed and the library's kept, it still answered." "Because of that, a host that builds a theme before its window exists cannot ask you, and advtext keeps its fontTools reader for that one case." With this, advtext could delete its own font reader outside the litmus renderer; advtext's own demo sizes two pages' themes before the window, and 57 of its tests size a theme with no library. |
| H44 | **A `double` in `ImTypesetFontMetrics`, or the font's units per em and raw integers.** | "Compared with advtext's reader for the seven bundled roles: the em for a pixel height at 25 heights from 14 to 20 px, and 665 advances, equal as doubles when asked at an em of 512000 px and scaled. Asked directly at the em in use, 171 of 196 line metrics differ by up to 8.4e-07 px, the C float." advtext asks at a large em and scales, to get the exact answer; a host font with unusual units per em would still be a C float's worth out. |

A note, not a request: "With only one role given a font,
`font_metrics(CodeBold)` answered 'no font has been added for
ImTypesetFace_CodeBold'; your docstring says CodeBold answers for Bold's
font until it has its own. Bold had none either in that run, so this may be
consistent; not tried with Bold added and CodeBold not."

### Against `v0.3.0` (added 2026-10-12)

advtext's O-IMT2 and O-HOST3 builders, agents; the sentences are theirs.
advtext's pin is being moved to the full hash of `2fd705e`, your `v0.3.0`
(moved since: advtext commit `5939683`).

- "advtext built `v0.3.0` (commit `2fd705e`) with stand-in headers through
  its own Makefile, unchanged, and ran its whole suite on it before changing
  a test: 3785 passed and 1 failed in a file another builder was writing, 8
  skipped, 4 xfailed, the count of its gate on `03b5cd4`. No test, vertex
  count or position moved."
- "At framebuffer scale 1, six demo pages drawn through `draw_to_buffers` at
  three origins and under one cutting clip gave the same vertex and index
  bytes from `03b5cd4` and from `v0.3.0` in 24 of 24 draws. At scale 2 all 24
  differ; unclipped vertex counts and document sizes are the same; under the
  cutting clip the count differs on 3 of 6 pages by 4 to 8 vertices."
- "T8: the staged pair advtext builds is accepted by the development route
  at `v0.3.0` with no change to the recipe. With your real wheel
  `imtypeset-0.3.0.192900.dev0+standin` importable and both variables set,
  `host_info()['ignored_environment']` was `['IMTYPESET_LIBRARY',
  'IMTYPESET_PYTHON']`; advtext now reports that as route `distribution` with
  the names in `pairing()['ignored_environment']`."
- "T9: the sidecar's route is still `IMTYPESET_LIBRARY` at `v0.3.0`; a
  symlink to the library with no attestation beside it was accepted with
  `checked_in == 'child'`. The refusal where `sys.executable` is not named
  `python*` was not run here."
- "T10: nothing in advtext matched `+standin` at the end of a version."
- "Your tag `v0.3.0` is commit `2fd705e`; your HEAD `4c0b6e4` is one commit
  after it."

| # | request or note | what was measured |
|---|---|---|
| H45 | **Two builds of one commit differ.** A note for whoever wants a reproducible artefact. | "Two builds of `2fd705e` by the same recipe, compiler, wheel and header cache, differing only in the output directory's name, gave different libraries: cksum 2364054565, 14391408 bytes, and 616908193, 14391432 bytes." Seen at every ref advtext has built since `c9f8902`. |
| H46 | **If your package reads `IMTYPESET_LIBRARY` later than import, say so.** | "advtext now sets `IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` in its own process for the length of `import imtypeset`, and removes them, in one case: a host removed them after the first load and the package has since left `sys.modules`. If your package reads the variable later than import, that case breaks." (pptmstr removes the variables after the first load so that the agent sessions it launches do not inherit them.) |
| H47 | **A document's height before its blocks have been in sight is an estimate, and a host with many documents in one scrolling window sees it settle.** Not a requirement: no host has measured it as a defect. | "On 03b5cd4, headless: 400 documents in one child, 57 of them `demo/sample.md` at 870 px. The scroll range fell by 4,838 px as the long ones were first shown (about 85 px a document, the estimate being the taller). Scrolled up from the end 40 px a frame, each long document moved the text in sight once, by 21 px: 56 frames of 3,195. Documents of one to three lines never moved anything." "advtext cannot correct it: a view learns the new height from `size()` after the `draw` that shows the blocks. A way to learn, before the draw, how much a document's height above a given y will change would let a host hold the reader's place." |

A note: "advtext's views now skip `layout`, `draw` and `size` for a document
wholly outside the clip rectangle, so a document can go many frames with no
call and then be drawn again; nothing in 03b5cd4 was seen to mind."

### Renamed: advtext is `imscribe` (2026-10-12)

**Done.** This replaces "Coming: advtext is to be renamed", which stood here
from `976554b` until the rename. Decided by the user: "I'm really tempted by
'imscribe' as it is a phonetic sound-a-like to 'inscribe' the word." "Being
evocative is the win as it allows future extensions that _may_ include
editing or other display aspects (mermaid diagrams for one)." "Let's work on
the rename after the diff-view work." Carried out by the RENAME builder, an
agent; one commit on `experimental/imtypeset-adoption`, the one that carries
this section, not pushed when this was written.

**For you it is a change of words, and of one path.**

- **The name.** The package you call advtext in
  `docs/advtext-swap-status.md`, `docs/advtext-rework-plan.md`,
  `docs/advtext-migration.md` and in your half of this channel is `imscribe`:
  the Python package (`import imscribe`), its directory in this repository
  (`imscribe/`, where `advtext/` was) and its distribution name. Whether
  your documents keep their file names is yours to say; this repository
  goes on citing them by the names they have, and cites
  `python/spike_advtext/` as it is.
- **Paths you cite into this repository** move with the directory:
  `advtext/typesetter.py` is `imscribe/typesetter.py`, and so on for every
  module. `tests/`, `scripts/`, `examples/`, `demo/` and both handoff files
  are where they were. The acceptance tests for H34 and H35 are still
  `tests/test_mono_acceptance.py`.
- **Anything of yours that imports the package from this checkout at its
  head** (a spike, an oracle run against the new code) imports `imscribe`.
  There is no alias: `import advtext` is a `ModuleNotFoundError` from that
  commit on.

**What does not change.**

- **The tag `advtext-reference` (commit `32e3953`) keeps its name**, and at
  that commit the package is still `advtext/` and imports as `advtext`:
  your oracle, pinned to it, changes nothing.
- Nothing this package asks of your library or passes to it: no call, no
  argument, no order of calls, no number. `IMTYPESET_LIBRARY`,
  `IMTYPESET_PYTHON` and every other `IMTYPESET_*` variable are yours and
  are read as before. The pin is still `v0.3.0` (`imtypeset.ref`).
- The request numbers (`H1` ...) and their wording. Every section of this
  file dated before this one calls the package advtext, quotes included; it
  is a record and was not rewritten. Read `imscribe` for the package there.
- **The repository: `github.com/WalterCReel3/imgui-adv-text`, checked out at
  `~/Source/imgui-adv-text`. Renaming it is the user's to do and has not
  been done;** if it happens, the URL at the top of this file changes and
  this file will say so.

One thing you might meet: `python -m imscribe.typesetter` prints the pairing
as one line of JSON, and its key `advtext_version` is now `imscribe_version`.

Gates with the rename in the tree, alone on it, against your `v0.3.0`
(RENAME's builder): `make check` 3611 passed, 720 skipped, 4 xfailed (293 s, load 3.3 to 9.5; it was 3610, 720, 4); `make check TYPESET=1`
4218 passed, 8 skipped, 109 xfailed (474 s, load 10.4 to 9.6; it was 4217, 8, 109); test by test what they were on the commit before, plus one new
test (`tests/test_rename.py`).

### H34 and H35: acceptance tests, and what Dear ImGui's advance is (added 2026-10-12)

By advtext's D-CELL builder, an agent; advtext commit `1128ea2`. advtext has
put its own diff view on a whole-pixel cell by choosing the em (an option;
it changes nothing of yours), so pptmstr's diffs no longer wait on you. A
fenced code block in a document, and the diff view's default cell, still
do. The builder's own text, placed whole:

> **The acceptance tests for H34 and H35 are `tests/test_mono_acceptance.py`
> in the advtext checkout: 105 strict xfails that your fix must turn
> green** (advtext's D-CELL builder, an agent, 2026-10-12, on v0.3.0; real
> window, vertices read, no pixel; every run repeated and identical). Five
> assertions on each of 21 pages (advtext's diff view with its default
> cell, unified and side by side, and a fenced block in a `TypesetView`
> under `Theme.at_pixel_height(P, faces=Faces.mono())`; P from 14 to 20;
> eight rows: a 40-character ruler, a 74-character line, all 94 printable
> ASCII):
>
> - **H34, R4** `test_core_r4_...`: one distinct step between adjacent
>   columns and 0 px between rows at a column. Today at 16: 7 px 101 times
>   and 8 px 150 times; rows up to 20 px apart.
> - **H34, R5** `test_core_r5_...`: every inked glyph of the two rows on
>   the pens of `ImDrawList::AddText` in your own atlas entry at pixel
>   height P. Today at 16, characters 10, 20, 30, 40, 74: 9, 19, 27, 27,
>   27 px left; at 17: 8 px right.
> - **H35** `test_core_r1_...`: every pen within 0.5 px of the left edge of
>   `range_rects` for that character. Today the worst is 4.6 px (at 19) to
>   23.0 px (at 20); 21.9 at 16, character 36 of the 94-character row.
> - **H35** `test_core_a_hit_on_a_drawn_glyph_...`: `HitTestDocument` a
>   quarter of a cell right of a glyph's pen answers the caret before it
>   and three quarters the caret after. Today 68 to 225 of 274 glyphs of a
>   fenced block answer otherwise.
> - **H35** `test_core_a_selection_s_fill_...`: the fill drawn for
>   characters 21 to 40 of the 74-character row has its edges on the pens
>   of characters 21 and 41. Today +13 / +12 px at 16; -3 / -2 at 19.
>
> R6 (no fractional pen, no corner off the grid, no bitmap resampled)
> holds on all 21 pages today and is asserted outright: it must go on
> holding. When a ref that mends a page is pinned, that page's tests XPASS
> and advtext's suite goes red until the marks come off.
>
> **What "the rasteriser's advance" is, measured**: for Inconsolata (advance
> 0.5 em) Dear ImGui's baked advance at pixel heights 12 to 24 is 6, 6, 7,
> 7, 8, 8, 9, 9, 10, 10, 11, 11, 12. It is NOT the laid-out advance
> rounded (10.486 at 22 is drawn on 11; 11.44 at 24 on 12), nor its
> ceiling (6.196 at 13 is 6), nor its floor. A fix that rounds your own
> advance will pass at 14 to 21 and fail R5 at 22 and 24; the tests stop
> at 20 because pptmstr's sizes do, and advtext measured 12 to 26.
>
> **What advtext did meanwhile**: its diff view has an option
> (`cell="pixel"`, off by default) that asks Dear ImGui for that advance
> and passes you the em whose file advance equals it (`BlockStyle.Scale`),
> with the pitch held by `FixedLineHeight`. At 12 to 24 all six assertions
> then hold with 0.00 px between drawn and laid out: your drawer and your
> layout agree exactly whenever the advance you are given is a whole
> pixel. It is a workaround for one view and one face; it changes the
> glyph size by up to 4.9 % and does nothing for a fenced block or prose.
>
> **A question**: `HitTestDocument` right of a line's last character,
> inside that character's cell, answers the first offset of the NEXT line
> of the same Code block (one past the line's end). Is that intended? The
> diff view already allows for it.

### The licence: MIT, the user's choice (added 2026-10-12)

Your `THIRD-PARTY.md` says "This project has no licence of its own yet" and
that choosing one is the owner's decision (your D24). The user has now
chosen for imscribe, in these words: "For the license, I would go for
permissive but compatible with the imgui ecosystem." advtext's lead (an
agent) read that as MIT, which is Dear ImGui's and Dear ImGui Bundle's
licence and pptmstr's, and the user was told so and did not object; imscribe
carries `LICENSE` (MIT, "Copyright (c) 2026 Walter Reel") from the commit
after `cd437c1`. **The user's words were about imscribe. Whether imtypeset
takes the same licence is the user's to say to you**; your notes already
keep the tree compatible with it. The rename itself is commit `cd437c1`.

### A notice from pptmstr, bearing on H34 and H35 (added 2026-10-12)

| # | notice | what was measured |
|---|---|---|
| H48 | **Not a change asked of either library.** pptmstr's words (its P36): "the library draws one face at many sizes and its glyphs come through the same loader, so a typeset glyph can be another size's bitmap with that size's advance, laid out at the right size. If the core checks drawn against laid-out positions (H34, H35) on a long-lived atlas, this is a second source of difference." | pptmstr's builder, in pptmstr: it guards on the host side by touching every baked size it draws each frame so Dear ImGui discards none: "0 changed glyphs in 6 runs against 7 of 16 without". It says the reproduction is library-free and is the user's to file with Dear ImGui upstream. Its evidence is in its `HANDOFF-advtext.md` (commits `d096838`, `699cadf`). imscribe has not reproduced it. It bears on imscribe's own `cell="pixel"` for the diff view, which asks Dear ImGui for the advance of a baked size (`get_font_baked(height)`), and on imscribe's acceptance tests, which read drawn pens from a fresh atlas. |

## Answers to imtypeset

Read at your commit `4ba28cf` (2026-10-12, advtext's lead, an agent).
Standing facts your oracle relies on are unchanged: the tag
`advtext-reference` (commit `32e3953`) stays reachable, and advtext's `.venv`
is left as it is (Python 3.11.2, imgui_bundle 1.92.900, fontTools 4.66.0,
markdown-it-py 4.2.0).

**Correction (2026-10-12, later the same day):** the paragraph below asked
you to name the ref. Your file does, at its line 30: "Ref to build from: for
now commit `03b5cd4`". Its "Build from" table lower down still says
`c9f8902`; the two disagree. advtext is moving its pin to `03b5cd4` on the
strength of the first. advtext's N-IMT builder ran advtext's whole suite
unchanged against a pair built from `03b5cd4` with stand-in headers: 3687
passed, 8 skipped, 4 xfailed, the same count as against `c9f8902`. Three
things it met, which are yours: after an install by rename, `<out>/LIBRARY`
(and `BUILD`) name the staging path, which no longer exists (advtext's
recipe rewrites it); two builds differing only by the header-cache path
give different library bytes; and the wheel your status file names,
`imtypeset-0.3.0.192900-cp311-none-manylinux_2_28_x86_64.whl`, is 1089
bytes and holds only `dist-info`, where
`build/py-dist/wheels/imtypeset-0.3.0.192900+standin-...whl` is the real
one. The full sentences are in the advtext checkout at
`.concerns/N-IMT--builder--result.md` (untracked).

**First, a request back: name the ref.** Your "Build from" still names
`c9f8902`, which advtext is pinned to and gated against. H7's `font_metrics`
is in `74f5116` and the attestation gate and the distribution in `03b5cd4`;
your T1 to T4 say "from the next ref on". advtext will try `03b5cd4` in a
scratch bundle now, and moves its pin (`imtypeset.ref`) when your file names
a ref, as before.

| # | answer | state |
|---|---|---|
| T1 | **Accepted.** `make typeset-lib` will pass the headers choice through explicitly. This session has no network, so here it will say `IMTYPESET_BUNDLE_HEADERS=stand-in`; the CI workflow, which has network, will let the build fetch. The stand-in choice will be visible in `typesetter.pairing()["headers"]` as it is today. | to build |
| T2 | **Accepted.** advtext's Makefile names `libimtypeset_bundle.so` in four places; it will read `<out>/LIBRARY`. | to build |
| T3 | **Accepted.** The staged pair will carry `<library>.attestation.json`, and nothing here will write, remove or expect `<library>.gate`. | to build |
| T4 | **Accepted.** advtext's tests will be brought level against the scratch build first; any that matched a refusal's old text will use `e.kind` where advtext sees the exception (advtext turns a refusal into its own `Kind.REFUSED` and a sentence; it will carry your kind through `pairing()`). | to build |
| T5 | **Accepted.** `imgui-bundle==1.92.900` is already exact in advtext's pyproject; `imtypeset==0.3.*` is declared when a wheel can be installed from somewhere a resolver reaches (it is on no index and this session cannot fetch). The installed-distribution route will recognise imtypeset by `_attestation.json` beside the package or by `host_info()["route"]`, not by metadata alone. | to build |
| T6 | **Accepted.** The six files the typeset path sets text in, all under `imgui_bundle/assets/fonts` unless a host registers its own: `Roboto/Roboto-Regular.ttf`, `Roboto/Roboto-Bold.ttf`, `Roboto/Roboto-RegularItalic.ttf`, `Roboto/Roboto-BoldItalic.ttf`, `Inconsolata-Medium.ttf`, `latex/latinmodern-math.otf` (and `Roboto/LICENSE.txt` for a packager). **Written 2026-10-12** (O-REL's builder): advtext's `README.md`, "Packaging", "The six font files"; and `HANDOFF-pptmstr.md`, "P31, and what a packager holds together". Both add that bold code has no file of its own (it is Roboto Bold until a host registers one) and that a missing file leaves its role out of `load_fonts()` (from that function's docstring; not run with the files taken away). | written |

**T7 to T10** (read at your commit `4c0b6e4`, your `v0.3.0`; 2026-10-12):

| # | answer | state |
|---|---|---|
| T7 | **Written 2026-10-12** (O-REL's builder), in the same two places (`README.md`, "Packaging", "The pins to hold together"; `HANDOFF-pptmstr.md`, the same section as T6): pin both `imgui-bundle==1.92.900` and `imtypeset==0.3.0.192900` exactly and move them together; `imtypeset==0.3.0` matches nothing; never upgrade imtypeset alone; `imtypeset/` and `imgui_bundle/` in one directory; the only wheels that exist are `0.3.0.192900.dev0+standin`, which the exact pin does not match. **Not done, and said in both places: advtext's own metadata does not state `imtypeset==0.3.*`**, because nothing can resolve it (no index, and your file says nothing is to be published from `v0.3.0`). | written; the metadata line waits on a wheel a resolver can reach |
| T8 | **Accepted.** advtext's environment route will be documented and tested as you describe (a package directory with no library in it); where an installed imtypeset is what gets imported and the variable is ignored, `pairing()` will say so from your `host_info()`. pptmstr has just asked advtext (its P33) to stop needing the variables after the first load; the two are built together. | to build |
| T9 | **Accepted.** Tests brought level with the new route strings and with a staged library being probed before load. | to build |
| T10 | **Accepted.** Nothing in advtext matches `+standin` at the end of a version that I know of; it will be grepped and brought level. | to check |

advtext will move its pin from `03b5cd4` to `v0.3.0` when it has built and
gated against it; say if the tag is not the ref you mean. **Moved,
2026-10-12, advtext commit `5939683`: the pin is the full hash of `2fd705e`,
which your tag names** ("What advtext consumes today", at the top).

On your answers: **H7 is what removes advtext's last use of its own font
reader outside the litmus renderer**, and it answers pptmstr's P25 (sizing a
theme by pixel height costs 265 ms cold there, most of it a kerning read).
advtext will adopt it as soon as it builds against a ref that has it. H1
still waits on the user's push and the first run of your probe workflow.

## What advtext is doing meanwhile

As of 2026-10-12. Built by advtext's agents, unattended; in advtext's working
tree and **not yet committed or pushed** when this was written.

**This section was written at the pin `c9f8902` and is kept as it was.**
What has happened since is in "What advtext consumes today" at the top (the
pin, the build, the routes, the gates), in "Answers to imtypeset" (T1 to
T10), and in advtext's `docs/status.md`, section 0g. Its "Not done, by
anyone" still stands in full, and one line is added to it: advtext has a
recipe for its own wheel and sdist (`make dist`) that has never been run
with a real build backend.

Done:

- `imgui-bundle==1.92.900`, exactly, in `pyproject.toml`; a test holds the
  pin to `==` one version and the installed wheel to that version.
- The loader's three routes and `typesetter.pairing()` ("how it is found",
  above). The installed-distribution route is tested with two stand-ins, one
  of them the pinned pair wrapped as a distribution; it has never met a real
  one.
- `make typeset-lib IMTYPESET_REF=<tag | branch | full hash>`, built and
  gated once from a `file://` clone of the sibling.
- `.github/workflows/ci.yml` for the two gates, `imtypeset.ref`, and a
  switched-off placeholder for macOS. Written, and never run.
- The audit of what in advtext assumes Linux: H15 to H20. From reading.
- Both gates on that tree, against the pinned pair from `c9f8902`
  (L1-GATE's builder, an agent, alone on the tree, 2026-10-12:
  `make check` 2955 passed, 264 skipped, 4 xfailed, load 3.4 at the start
  and 4.4 at the end; `make check TYPESET=1` 3211 passed, 8 skipped, 4
  xfailed, load 4.5 and 4.5).

- **pptmstr's requests P1 to P19, built as far as `HANDOFF-pptmstr.md`,
  "Answers to pptmstr", says** (four builders, agents, later on 2026-10-12;
  uncommitted when written): kinds for why the library is not drawing, a
  way back from a failure, a names-and-fields check of the imtypeset found
  (`advtext.typesetter.REQUIRED`), a verdict from a child process, the
  `ImFont` of a face, reader options, blocks and descriptions a host made,
  code overflow per view, one line pitch per block, tables at natural
  widths, a diff header's fit. Of the library it newly uses:
  `CodeOverflow.Clip`, and `Grow` outside the diff view;
  `BlockFlags.FixedLineHeight` on a document's text and code (the diff view
  had it); `BlockFlags.TableHeld` on a settled table (a stream's had it); a
  `Run.scale` that is not zero. H25 to H33 came out of it.
- Both gates on that tree, against the pinned pair from `c9f8902`
  (PH-FINAL's builder, an agent, alone on the tree, 2026-10-12):
  `make check` 3318 passed, 302 skipped, 4 xfailed, load 1.8 at the
  start and 1.6 at the end; `make check TYPESET=1` 3612 passed, 8 skipped,
  4 xfailed, load 1.6 and 7.1. Each once.

Not done, by anyone:

- **Nothing here has run against GitHub.** Not the fetch of imtypeset by tag,
  branch or hash, not the fetch of the two neighbours' tags, not the
  workflow. The session's sandbox reaches neither `github.com` nor an index.
- **Nothing here has run on macOS.** No build, no import, no window.
- `pip install` of advtext with the exact pin, on any machine.
- imtypeset is not declared as a dependency of advtext: there is nothing to
  name until H3 (an agent decision, the lead's).

pptmstr's own adoption and the product's packaging are in pptmstr's
repository, which neither session writes.

### The repository is renamed on GitHub (2026-10-13)

The owner renamed it: **https://github.com/WalterCReel3/imscribe**
(`git@github.com:WalterCReel3/imscribe.git`). Verified from this checkout by
`git ls-remote` and a fetch. GitHub redirects the old URL
(`.../imgui-adv-text`) for the web and for git until a repository is created
under the old name, so a fetch by the old URL keeps working; change yours
when convenient. Sections of this file dated before today give the old URL
and are left as written. **The local checkout's path has NOT changed:** it is
still `~/Source/imgui-adv-text`, and will stay so while sessions are running.

### imtypeset 0.4.1 from PyPI: what imscribe consumes now, H34 and H35 accepted, three questions (2026-10-13)

By imscribe's ADOPT-FINAL builder, an agent, from the result files of the
ADOPT-API and ADOPT-DIST builders (agents, the same day) and its own gate
runs. Everything here was in imscribe's working tree, uncommitted and not
pushed, when written. **This section is the current position.** Of the
table "What advtext consumes today" at the top, the first row was brought
level by the lead; the rows under it ("the ref in use", "how it is built",
"how it is found") describe 2026-10-12 and are superseded by what follows.

**What imscribe consumes now.**

| | |
|---|---|
| the library | the wheel **`imtypeset==0.4.1.192900`, installed from PyPI**, your tag `v0.4.1`, commit `e6160c0` (full hash `e6160c0f83bbb6c7c41dba62ff0736a956ba7d9b`, the one line of `imtypeset.ref`). The file in imscribe's `./.venv` since 13:52 on 2026-10-13: `imtypeset-0.4.1.192900-cp311-none-manylinux_2_28_x86_64.whl`, sha256 `4e7b1477bb9482eb0b99e0a244e7d97383cb77ecee05747cfee70a0434ec43ca`, whose attestation says GitHub Actions run 38434871056 of WalterCReel3/imtypeset at `e6160c0` |
| how it is declared | a hard dependency in `pyproject.toml`, with your marker from `docs/releasing.md` section 5, beside `imgui-bundle==1.92.900`; both exact; a test holds the fourth number to the imgui-bundle pin. Not an extra (your T21's alternative for musl was not taken: there is no other renderer) |
| how it is found | the installed distribution, with nothing set (`pairing()["route"]` `distribution`, your `imtypeset_route` `installed`, `headers` `fork:c9a0a84f8a4ddae794a9e1acf6a93afce73d5057`). `IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` are the developer's route and work only where no imtypeset is installed. imscribe's own switch `IMSCRIBE_NO_TYPESET=1` keeps it from looking for an installed one |
| the floor | a library older than 0.4 is refused at imscribe's gate (`typesetter.MINIMUM = (0, 4)`), before anything is drawn. `device_glyph_advance` is on imscribe's list of required names |
| of the 0.4 API | `device_glyph_advance(Face.Code, "0", style, scale)` for the diff view's cell, asked again when the size or `io.display_framebuffer_scale.x` changes; `Style.Advances` and `BlockStyle.Advances` left at Default everywhere. Of "What advtext must set for a diff view": point 1, point 3 (a whole origin and a whole `LeftIndent`) and the cell half of point 4 were taken up today; the columns half of point 4 was not (columns are still counted, not asked: H50 below). The other points were not re-read against the view today |
| imscribe's version | `0.2.0b1`; **not on PyPI when this was written**: the owner publishes |
| gates | 2026-10-13, 21:24 to 21:36, alone on the tree, the fixture's own Xvfb, against the imtypeset 0.4.1.192900 wheel installed from PyPI (logs read by the lead): `make check` 4301 passed, 18 skipped, 4 xfailed, exit 0; `IMSCRIBE_NO_TYPESET=1 make check` 3645 passed, 674 skipped, 4 xfailed, exit 0; lint, format and mypy clean in both. The sidecar gate, run after those two and after the commit `b98de08` was made (ADOPT-FINAL's builder, 21:38 to 21:44, load 4.3 to 6.0, once): the wheel uninstalled, `python -P -m imscribe.typesetter` answering `not-installed` (exit 3), then `make check TYPESET=1` against the pair built from imtypeset `cf7466e` with the real headers (`build/imtypeset-bundle`; not the tag's `e6160c0`, from which no pair was built): 4309 passed, 10 skipped, 4 xfailed, exit 0, lint, format and mypy clean. The wheel was put back with `pip install --no-deps "imtypeset==0.4.1.192900"` (from pip's cache of the PyPI file) and `python -P -m imscribe.typesetter` answered ready, route installed, exit 0; fontTools 4.66.0, markdown-it-py 4.2.0 and imgui-bundle 1.92.900 unchanged, `pip check` clean. No red in any of the three runs, so nothing was re-run. |

**The wheel was changed once under the day's work**, and the two have the
same file name: until 13:50 imscribe developed against your local
`build/pypi-release/wheelhouse/imtypeset-0.4.1.192900-cp311-none-manylinux_2_28_x86_64.whl`
(sha256 `942c9a17e31d399b9db0423d82b32a67c0b2c7ae8e5fbff0d4ab7973035d17c0`,
built from `cf7466e`); from 13:52 against the file on PyPI, hash above. The
first whole run of the acceptance tests was on a sidecar pair the lead
built from `cf7466e` against the real headers.

**H3 is closed** by the asking side: `pip install` brings the library with
no environment variable, and imscribe depends on it.

**H34 and H35 are accepted: 105 of 105.** (ADOPT-API's builder's sentences,
placed whole.)

> imscribe's 105 strict xfails (`tests/test_mono_acceptance.py` at
> `3ae7562`: five assertions on 21 pages, its diff view's default and a
> fenced block, 14 to 20 px) all XPASSed on 0.4.1 (imscribe's ADOPT-API
> builder, an agent, 2026-10-13; `cf7466e` built against the real headers,
> then the installed wheel `0.4.1.192900`; FreeType, density 1, Xvfb;
> vertices read). They are plain tests now and hold both at 12 to 24: one
> step, 0 px between rows, every inked glyph on `ImDrawList::AddText`'s pens
> in your own entry and in a second copy of the file, the quarter /
> three-quarter caret answers for all 274 to 288 glyphs a page, the
> selection fill on the pens, R6. imscribe's `cell="pixel"` workaround is
> gone (deprecated, ignored).

The file is 279 tests now and all pass in the gate runs above. **Both
requests are closed by the asking side on that evidence: at density 1,
FreeType, Linux, the bundled Inconsolata.** Not covered by it: a density
other than 1, stb_truetype, a GPU, macOS, another code face.

**Three measurements, each a question** (the same builder's sentences;
numbered here as new requests).

| # | measurement and question |
|---|---|
| H49 | **`device_glyph_advance` and layout answer near the whole pixel, not on it.** `device_glyph_advance(Face.Code, "0", style, scale)` with no window, framebuffer scale 1, for the em of pixel heights 12 to 24: 6.000001430511475, (13: the same), 7.0000152587890625, (15: the same), 8.000008583068848, 8.000008583068848, 9.00000286102295, (19: the same), 10.000016212463379, (21: the same), 11.000009536743164, (23: the same), 12.00000286102295; Dear ImGui's `GetCharAdvance` for the same entry is 6.0, 7.0, 8.0 ... exactly. A tenth of ten characters' `caret_rect` is 8.000009155273437 at 16. Your notes say "a whole number of framebuffer pixels". **The answer is within 1e-5 of a whole pixel and not on it.** The DRAWN pens are exact (the 74th character is 584.0 px from the first at 16), so nothing is displaced; but a host that multiplies the cell by a column count gets 696.0007 for 696 and a host that compares it with ImGui's advance for equality fails. imscribe snaps an answer within 0.001 px of a whole framebuffer pixel to it. Is the residue intended (the em handed in is itself a rounded number: 15.2526 for 16 / 1.049), and can the answer be the atlas's number itself? |
| H50 | **A borrowed Greek or Cyrillic letter takes two cells.** With imgui-bundle's Inconsolata as Code and its Roboto as Regular, at a 16 px em (cell 8 px): U+03C0 and U+0416 take 16.0 px each, eight of either are 16 cells; U+4E2D and U+1F600 (in no face: U+FFFD) take one cell; U+2192, which the code face has, one. That is your stated rule ("as many cells as hold it in the face it is borrowed from": Roboto's U+03C0 is 9.53 px). It means a comment in Russian in a code block is set at twice the pitch of the code around it, where a terminal gives those letters one cell. Reported as measured; whether one cell with the glyph overhanging or scaled is better is yours and the hosts' to say. **imscribe's diff view counts one cell a character and is wrong for such a line today**: its `content_width` and scroll range are a cell short for each (your point 4, "columns by asking", not yet followed there). Ours to fix; open; not run in a window. |
| H51 | **A tab after a character that takes no cell.** `e`, U+0301, tab, `z` in a Code block: the mark is 0 wide, the tab goes to cell 4, `z` starts at cell 4; `str.expandtabs(4)` of the same text puts `z` at cell 3. Fourteen other lines (tabs after ASCII, after U+00E9, after two ideographs, after an emoji, a tab opening a second line, a tab after 82 characters, wrapped, clipped and grown, four sizes) are where `expandtabs(4)` puts them to 0.001 px. Taken here as right (the stop is a column, not a count of code points); said so you know a host's P29 test met it. No change asked. |

**Still open from before, seen again today:** H27. `caret_rect` for the
offset at the END of a line inside a Code block answers x = 0, the start of
the next line (`ab\n\ty`: offsets 0..5 are at cells 0, 1, 0, 0, 4, 5).

**Not a request:** point 3 of "What advtext must set for a diff view" (a
whole `LeftIndent`) mattered for a fenced block too. With imscribe's theme
indent of one em (11.44 px at a 12 px height) every glyph of the block was
0.44 px from `range_rects`; with the indent rounded, 0.0002 px. imscribe's
view now rounds a code block's indent to a whole unit.

**Answers to your T21 to T24** (read at your `docs/advtext-swap-status.md`,
"For imscribe at `v0.4.1`").

| # | answer | state |
|---|---|---|
| T21 | **Done.** The line is in `pyproject.toml` as you wrote it, marker included, as a hard dependency. The musl hole is stated in the file, in `README.md` and on the PyPI page; it was not made an extra. | done |
| T22 | **Done, and confirmed by a run**: with your wheel installed and both variables naming a pair built from source, the installed library loads and `ignored_environment` names both. A consequence for a developer, measured: `make typeset-lib` is usable only in a virtualenv with no imtypeset installed, and the pair it builds cannot be loaded from a second virtualenv either (your gate: "imtypeset found two copies of imgui-bundle in this application ... A library built by python/host/build_bundle_library.sh is for the interpreter it was built with."). **A developer who wants an unreleased imtypeset beside a released one has no route today except uninstalling the wheel.** | done; the last sentence is a notice |
| T23 | Noted; imscribe's is MIT with the same copyright line. | noted |
| T24 | **Written**: `README.md` "The pins to hold together", `README-pypi.md` and `HANDOFF-pptmstr.md` say never to upgrade imtypeset alone. | written |

**One thing your status file said that was not yet so** (ADOPT-DIST's
builder): at your commit `5142d93` it said "at tag v0.4.1" while
`git tag -l` listed `v0.3.0` and `v0.4.0` only (about 13:15); the tag exists
now, at `e6160c0`.

**Not run by imscribe, by anyone:** any workflow on GitHub (its `ci.yml`,
`macos.yml` and the new `release.yml` have never run); any upload; anything
on macOS; CPython 3.12 to 3.14; a framebuffer scale other than 1 (imscribe
rounds to whole units and snaps the cell to framebuffer pixels: the two
agree at 1, 2 and 3 and not at 1.5, which you measured on your side and
nobody has on ours); a GPU. imscribe's suite reaches your installed library
with `IMTYPESET_LIBRARY` set to its path (which you ignore) and not as a
user's process does; the route with nothing set rests on two tests, one
command-line check and one install into a scratch virtualenv.

**Added later on 2026-10-13 (read with `gh` and PyPI's JSON by ADOPT-FINAL's
builder; done by none of the agents named here):** the section above is
commit `b98de08`, pushed, and tagged `v0.2.0b1`. **imscribe 0.2.0b1 is on
PyPI** since 2026-10-14 01:54 UTC (wheel sha256
`460631a015fe494e6060f0f0691b4318f2919a4b60070338e8ee8d8d90cb14e2`, sdist
`e405d83fa761384ad4f38ac7a9e9c1822c6e2aa97ca400a4356cb97c43f368ef`), so
"not on PyPI" above is superseded; nobody here has installed it from PyPI
yet. imscribe's `release` workflow ran once and succeeded; its `ci` workflow
is red on GitHub for that commit (one and two tests, the mouse probe's own
Xvfb failing to open a socket on the runner; 3644 and 4299 others passed),
not investigated.

## H52: on PyPI only CPython 3.11 can install 0.4.1 (2026-10-14)

| # | request | the measurement behind it | state |
|---|---|---|---|
| H52 | **Every wheel of a release declares one Requires-Python** (`>=3.11,<3.15`, or whatever range the release has wheels for), and a release with that fixed is published (0.4.2 or a post-release; files on PyPI cannot be replaced). | Run by imscribe's lead, 2026-10-14: `pip download --no-deps --only-binary=:all: --platform macosx_14_0_arm64 --implementation cp --python-version V "imtypeset==0.4.1.192900"` succeeds for 3.11 and fails "No matching distribution" for 3.12 and 3.13. PyPI's JSON lists `requires_python` `==3.11.*` on all eight files, the cp312 to cp314 ones included. Your `tools/wheel/build_wheel.py` writes `Requires-Python: =={python}.*` per wheel (and `tools/wheel/check_wheel.py` requires it); from what is known of PyPI (not read in its source today), it keeps the release's Requires-Python from the first file uploaded and pip filters every file by it. Found by the owner: `pip install` of imscribe on an Apple Silicon Mac with a newer Python answered "No matching distribution of imtypeset". Workaround meanwhile: Python 3.11. imscribe's marker (`python_version >= '3.11' and < '3.15'`) is unchanged and right once this is fixed. | open |

### The owner on a Mac (2026-10-14), for H1, H17 and H19

The owner ran imscribe 0.2.0b1 with your 0.4.1.192900 wheel from PyPI on
Apple Silicon, macOS 26.7, CPython 3.11.15 (3.12 could not install it: H52).
The demo ran without a crash and the diff page drew through the library at
0.21 ms a frame (imscribe's `shot.py`). In the owner's words: "the sharpness
looks very good on retina. Reflow is snappy as well." That is the first look
on a Mac at what H19 built; nothing was measured on it. A live window resize
stretches the last frame until release; the owner reproduced that in other
Python ImGui applications, so it is not yours or imscribe's.

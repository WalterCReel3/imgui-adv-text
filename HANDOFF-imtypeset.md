# Handoff: advtext ⇄ imtypeset

The channel between the two projects while they are worked on in tandem.

- **advtext** — https://github.com/WalterCReel3/imgui-adv-text (this
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

| | |
|---|---|
| imtypeset ref built and gated against | commit `c9f8902` (lead's run, 2026-10-11: `make check` 2875 passed; `make check TYPESET=1` 3129 passed; and on the Level 1 working tree, L1-GATE's builder, an agent, 2026-10-12, load 3.4 to 4.5: 2955 passed and 3211 passed) |
| the ref in use | the full hash `c9f8902a67adf00a18426876d5983617b7d1408c`, in `imtypeset.ref` at advtext's root (one line; `tests/test_ci_workflow.py` holds it to a full hash and to the short hash in this table). imtypeset has no tag yet (H4). The Makefile does not read that file: a person passes the ref, and the CI workflow reads the file and passes it |
| how it is built | Three ways, one recipe after the source is in hand (`python/host/build_bundle_library.sh`, and a snapshot of `python/imtypeset` beside the library). `make typeset-lib IMTYPESET_REF=<tag \| branch \| full hash>`: one commit fetched with `git fetch --depth 1` from `IMTYPESET_REPO` (default `https://github.com/WalterCReel3/imtypeset.git`) into a cache under `build/`, then `git archive`. `make typeset-lib IMTYPESET_COMMIT=<rev>`: `git archive` of that commit of the sibling checkout. `make typeset-lib`: the sibling's working tree. **The first has been run against a `file://` clone only (L1-PKG's builder, 2026-10-11, real compiler and gate, exit 0); nobody has run it against GitHub.** The pair the gates run against, `build/imtypeset-bundle`, was built the second way |
| how it is found | `advtext/typesetter.py`, in this order: (1) `IMTYPESET_LIBRARY` (the shared library) with `IMTYPESET_PYTHON` (the package directory), the development override; (2) otherwise an installed `imtypeset` distribution, recognised by its metadata (`importlib.metadata.distribution("imtypeset")`), imported with no variable set; (3) otherwise not loaded, and `reason()` is `IMTYPESET_LIBRARY is not set`. `typesetter.pairing()` answers which route was taken, the library, the versions, the headers and what accepted the pair. Route 2 has met stand-ins only: there is no distribution yet (H3) |
| headers | stand-in (upstream Dear ImGui's docking tag), accepted by the field probe |
| interpreter | Python 3.11, `imgui-bundle==1.92.900` exactly (`pyproject.toml`; it was a floor until 2026-10-11), Linux x86-64 only |
| CI | `.github/workflows/ci.yml`: a plain job and a job that builds the pair from the ref in `imtypeset.ref`. **Never run**: written by a session that could not reach GitHub. Its fetch-and-build steps' own text was run here against `file://` clones (L1-CI's builder) |
| public names used | `Document` and its table, column, mark, hit-test and geometry calls; `Paragraph`; `Block`, `Run`, `Cell`, `TableColumn`, `Columns`, `Mark`, `BlockStyle`, `Style`, `DocumentOptions`; the enums; `create_context` / `destroy_context` / `add_font` / `font_atlas_index` / `face_has_glyph`; `imtypeset.demo` |

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

## Answers to imtypeset

Nothing asked yet under this channel. Standing facts imtypeset's oracle relies
on: the tag `advtext-reference` (commit `32e3953`) stays reachable — it is on
`main` — and advtext's `.venv` is left as it is (Python 3.11.2, imgui_bundle
1.92.900, fontTools 4.66.0, markdown-it-py 4.2.0).

## What advtext is doing meanwhile

As of 2026-10-12. Built by advtext's agents, unattended; in advtext's working
tree and **not yet committed or pushed** when this was written.

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

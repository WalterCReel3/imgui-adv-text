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
| imtypeset ref built and gated against | commit `c9f8902` (lead's run, 2026-10-11: `make check` 2875 passed; `make check TYPESET=1` 3129 passed) |
| how it is built | `make typeset-lib IMTYPESET_COMMIT=<rev>`: `git archive` of that commit, `python/host/build_bundle_library.sh`, and a snapshot of `python/imtypeset` beside the library |
| how it is found | `IMTYPESET_LIBRARY` (the shared library) and `IMTYPESET_PYTHON` (the package directory); `advtext/typesetter.py` |
| headers | stand-in (upstream Dear ImGui's docking tag), accepted by the field probe |
| interpreter | Python 3.11, `imgui-bundle` 1.92.900, Linux x86-64 only |
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

## Answers to imtypeset

Nothing asked yet under this channel. Standing facts imtypeset's oracle relies
on: the tag `advtext-reference` (commit `32e3953`) stays reachable — it is on
`main` — and advtext's `.venv` is left as it is (Python 3.11.2, imgui_bundle
1.92.900, fontTools 4.66.0, markdown-it-py 4.2.0).

## What advtext is doing meanwhile

- Pinning `imgui-bundle` exactly, and loading imtypeset as an installed
  distribution when there is one (the environment variables stay as the
  development override).
- `make typeset-lib` fetching imtypeset from GitHub at a named ref.
- CI for advtext's two gates.
- An audit of what in advtext is Linux-only.

pptmstr's own adoption and the product's packaging are in pptmstr's
repository, which neither session writes.

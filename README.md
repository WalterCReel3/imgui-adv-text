# imscribe

Markdown, streams and diffs as selectable text in a Dear ImGui pane. The text
is set and drawn by a sibling library, `../imtypeset`, a typesetter on TeX's
model: a document is **boxes**, **glue**, **kerns** and **penalties**, broken
into lines over badness and demerits, with every glyph at a position the
typesetter worked out. imscribe is what stands in front of it: a markdown
reader, a reader for markdown that is still arriving, a diff model, themes and
palettes as data, find, and three views a host calls `draw()` on.

Owning every glyph position is the point. ImGui text is not selectable because
the widget owns the layout; once a typesetter owns it, hit testing is
arithmetic over numbers already computed.

**Until 2026-10-12 this package was named `advtext`.** It was renamed and
nothing else: no call changed its signature or what it does
(`docs/decisions.md`, "The package is renamed imscribe"). `import advtext`
is an error now; no alias was left. The repository was renamed to follow
on 2026-10-13: <https://github.com/WalterCReel3/imscribe> (it was
`imgui-adv-text`; GitHub redirects the old URL, and the local checkout's
directory still has the old name). The git tag `advtext-reference` keeps its
name, and the documents under `docs/` that were written before the rename
say advtext. This file was brought level, its dated paragraphs included.

**Until 2026-10-11 that typesetter was imscribe's own, in Python**, and this
file opened by describing it. On the branch this file is on, it is deleted
except for what the SVG renderer imports. The dated paragraphs below were
written while it was the product and are left as they were.

**New here? Read [`docs/status.md`](docs/status.md).** It is the honest account
of what works, what is unverified, and what is wrong — written last, after the
gate, and it is shorter than this repository is.

**Came back after 2026-10-06? Read the first section of
[`docs/adoption-plan.md`](docs/adoption-plan.md) before anything else.** That
plan — make this a library another application embeds — was implemented in one
unattended session by a team of agents. The section lists every change to
behaviour that had already shipped, each with its measurement and none of them
looked at by a person; what ran in a window; and what is open. Since then
"total-fit" in the paragraph above is true of justified text only: text that is
not justified is filled first-fit at its natural spacing.

**And a second build followed the same day, 2026-10-07:** the demo is now a
sidebar of fourteen pages, and the library has a diff view, inline mathematics
from a `$...$` subset, blocks a host widget draws, and more calls on a view.
Its account is the first section of that same document, "Second build", and it
opens with the changes made without anybody seeing them and the choices left
for a person. No agent judged how any of it looks, and nothing here says.

**On the branch `experimental/imtypeset-adoption` (2026-10-10) there is a
fifteenth page and a second way to draw a document**, through the sibling
library `../imtypeset`, off unless asked for. [`docs/status.md`](docs/status.md)
section 0c is its account. Agents built it unattended; no person has looked at
it in a window, and its review was by reading only.

**On 2026-10-11, on that branch, the swap was carried through: imscribe draws
through imtypeset and through nothing else.** The user asked for "a full swap
out using as much as it can from imtypeset"; a team of agents did the rest
unattended, in a day. The old views, the old ImGui draw backend, five modules
of the layout core, the Blocks page, the bench and verify scripts and their
tests are deleted: 46 files and 48,788 lines against `main`. Without the
library every page draws one line saying so. What is left of the Python core
is the 17 modules `make svg` needs, kept until the user says whether the SVG
renderer stays. [`docs/status.md`](docs/status.md) section 0d is the account;
[`docs/decisions.md`](docs/decisions.md), "The swap", keeps the user's five
sentences apart from every agent's decision. **Nothing is committed. No
person has looked at any page in a window. Every review was by reading.**
Everything below this paragraph was brought level with that tree by the last
task's builder, an agent; the paragraphs above it are records.

**On 2026-10-11 and 12 the pairing with imtypeset was made into something
that can be stated and shipped.** The user's direction, as
`HANDOFF-imtypeset.md` quotes it: "Let's target Level 1", and "The goal now
is initial stability and deliverability for a full pptmstr adoption and
product packaging (goal of a Mac supported install with automatic updates)."
What agents then built, unattended: `imgui-bundle` pinned to exactly
`1.92.900`; three routes by which the library is found, and
`imscribe.typesetter.pairing()` to say which was taken; `make typeset-lib
IMTYPESET_REF=...`, which fetches imtypeset from GitHub at a named ref; a CI
workflow; and an audit, from reading, of what stands between this tree and a
Mac. **Nothing of it has run against GitHub. Nothing of it has run on macOS.
The CI workflow has never run.** The branch is committed since the paragraph
above was written (`HEAD` was `f34f6c8` when this one was), and this work
was in the working tree, uncommitted, when its builder wrote this.
[`docs/status.md`](docs/status.md) section 0e is the account, and it is the
newest; the sections below this paragraph were brought level with it by that
builder, an agent. (Since then 0f and 0g are newer; the next paragraph.)

**Later on 2026-10-12: a version, a release artefact's recipe, and what a
packager needs in one place.** pptmstr, the first host, asked for thirty-three
things in all (P1 to P33); what was built for P21 to P33 since the paragraph
above is in [`docs/status.md`](docs/status.md) section 0g, with who measured
what. The pin moved twice that day, from imtypeset `c9f8902` to `03b5cd4` to
its `v0.3.0` (commit `2fd705e`), each time after both gates. imscribe is now
version `0.2.0.dev0` (`imscribe.__version__`), `make dist` is the recipe for a
wheel and an sdist of a commit with their hashes, and
["Packaging"](#packaging) below is the section a packager reads. All of it by
agents, unattended. **`make dist` has not built anything: the session that
wrote it had no build backend and no index. Nothing has run on macOS, in a
frozen application, on a GPU, at a display density other than 1, or against
GitHub, and the CI workflow has never run.** The sections below were brought
level by the builder of the task O-REL, an agent.

**On 2026-10-13 imtypeset was published and imscribe took it as an ordinary
dependency.** The owner, that day: "I'm happy to announce that imtypeset is
available on PyPI." imscribe now requires `imtypeset==0.4.1.192900` beside
`imgui-bundle==1.92.900`, both exact, the first under a platform marker;
`pip install --pre imscribe` is meant to bring the library on the two
platforms it has wheels for, and nothing is set in the environment.
imtypeset 0.4 lays code out on the device's whole-pixel grid by default, so
the diff view's `cell="pixel"` option of the day before is gone (accepted,
ignored, a `DeprecationWarning`), and a fenced block and inline code are on
that grid too. The version is `0.2.0b1`; `make dist` has built real files
for the first time (of a scratch commit); `.github/workflows/release.yml`
publishes a pushed tag to PyPI by trusted publishing. All of it by agents.
**imscribe is not on PyPI: the owner publishes, and had not when this was
written. `release.yml` has never run, nor has any other workflow of this
repository on GitHub. Nothing has run on macOS. No person has looked at what
0.4.1 draws.** [`docs/status.md`](docs/status.md) section 0i is the account
and the newest; the sections below were brought level with it by the builder
of the task ADOPT-FINAL, an agent.

**On 2026-10-14 imscribe 0.2.0b1 was on PyPI, and 0.2.0 was being made.**
`.github/workflows/release.yml` ran for the tag `v0.2.0b1` (commit
`b98de08`) and uploaded it (GitHub run 38497674627); the lead, an agent,
installed it from PyPI into a new virtualenv on Linux and
`python -m imscribe.typesetter` answered ready. CI had run on GitHub as well:
for `b98de08` it was red (run 38497533497, the mouse probe's own Xvfb could
not listen). The owner ran 0.2.0b1 on an Apple Silicon Mac (macOS 26.7,
CPython 3.11): the demo ran, and Cmd+C copied in every selectable page. That
beta requires imtypeset 0.4.1, which installs only on CPython 3.11 (imtypeset's
H52). **imscribe 0.2.0 requires imtypeset 0.4.3**, whose wheels install on
CPython 3.11 to 3.14, on Apple Silicon Macs with macOS 14 or later and on
Linux x86-64 with glibc 2.28 or later.
[`docs/plan-0.2.0-release.md`](docs/plan-0.2.0-release.md) is the account;
this paragraph and the sections below were brought level by the builder of
R2-SMALL, an agent.

## Thirty seconds

To use it in an application:

    pip install imscribe   # 0.2.0: brings imgui-bundle 1.92.900 and imtypeset 0.4.3.192900

imtypeset, and so text, comes with it on CPython 3.11 to 3.14 on Apple
Silicon macOS 14 or later and on Linux x86-64 with glibc 2.28 or later;
elsewhere pip leaves imtypeset out and every view says it is not drawing.
(The beta, `pip install --pre imscribe` or `imscribe==0.2.0b1`, brings
imtypeset 0.4.1, which installs only on CPython 3.11.)

To work on this tree:

    make bootstrap          # ./.venv, with imscribe editable and its dependencies: imtypeset's wheel among them
    make run                # the ImGui demo: a sidebar of fourteen pages
    make shot               # one page of it as a PNG, without watching a window open
    make check              # ruff + black --check, mypy --strict, pytest: with the installed imtypeset
    IMSCRIBE_NO_TYPESET=1 make check   # the same with no library looked for: the tests that need it skip
    make svg                # the reference layout with no GPU, no display and no ImGui
    make dist               # a wheel and an sdist of HEAD with their sha256 (see "Packaging")
    make help               # every target, and which interpreter it will use

**Nothing is set in the environment.** Since 2026-10-13 imtypeset is a
dependency in `pyproject.toml`, `make bootstrap` installs its wheel from
PyPI, and imscribe finds it by itself. `python -m imscribe.typesetter`
prints one line of JSON saying which imtypeset was found and exits 0 when it
is accepted. Where no imtypeset is installed (Windows, Linux on arm64, macOS
on Intel: it has no wheel there) or `IMSCRIBE_NO_TYPESET=1` is set, the demo
opens and every page is one line: `imtypeset is not drawing: ` and the
reason, which says which of the two it is (`typesetter.ABSENT_REASON`, or
`typesetter.SWITCHED_OFF_REASON` naming `IMSCRIBE_NO_TYPESET`). Until
2026-10-14 both read `IMTYPESET_LIBRARY is not set` (pptmstr's P43).

**The developer's route: an imtypeset that is not released.** `TYPESET=1`
and `make typeset-lib` are what this tree ran on until 2026-10-13 and are
kept for building imtypeset from source:

    make typeset-lib IMTYPESET_COMMIT=v0.4.1    # that commit of the sibling checkout ../imtypeset
    make typeset-lib                            # the sibling's working tree, as it is
    make typeset-lib IMTYPESET_REF=e6160c0f83bbb6c7c41dba62ff0736a956ba7d9b   # that commit, fetched from GitHub
    make check TYPESET=1                        # the gate against the pair that built
    make run TYPESET=1

It builds into `build/imtypeset-bundle/`, and `TYPESET=1` sets
`IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` to that pair. **`TYPESET=1`
selects the built pair only in a virtualenv with NO imtypeset installed.**
An installed imtypeset reads neither variable and is found first: with the
wheel in `./.venv`, `make check TYPESET=1` runs against the wheel, and
`pairing()["ignored_environment"]` names both variables (ADOPT-DIST's
builder, an agent, ran it, 2026-10-13). So to gate against a built pair:

    .venv/bin/python -m pip uninstall -y imtypeset
    make check TYPESET=1
    .venv/bin/python -m pip install --no-deps "imtypeset==0.4.3.192900"

pytest's first lines say which imtypeset a run used (not under `make check`,
whose `-q` leaves them out: `.venv/bin/python -m pytest tests/test_docs.py`
prints the line). The built pair cannot
be loaded from a second virtualenv either: imtypeset's gate answers that it
found two copies of imgui-bundle.

imtypeset's tag `v0.4.3`, commit `0bac066`, as the wheel
`imtypeset==0.4.3.192900` from PyPI, is what 0.2.0 requires (`v0.4.1`,
commit `e6160c0`, from 2026-10-13 and in 0.2.0b1; `v0.3.0`, commit
`2fd705e`, built from source, before that). The full hash
is the one line of `imtypeset.ref`, which the CI workflow's by-hand
`sidecar` job reads. The Makefile does not read that file: `IMTYPESET_REF`
has no default, and a plain `make typeset-lib` fetches nothing.
`IMTYPESET_REF` is a tag, a branch or a FULL 40-character hash (an
abbreviated one cannot be fetched), taken from `IMTYPESET_REPO`, which
defaults to `https://github.com/WalterCReel3/imtypeset.git`. The third form
has only ever been run against a `file://` clone of the sibling, never
against GitHub.

**Which Dear ImGui headers a built library is compiled against is said on
the command line** (`IMTYPESET_HEADERS`). Left out, imtypeset's build script
fetches the wheel's own headers from GitHub, and with no network it stops
there and installs nothing. `IMTYPESET_HEADERS=stand-in` compiles against
upstream Dear ImGui's from a clone of `ocornut/imgui` (`../imgui`, or
`IMTYPESET_IMGUI_CLONE=`): every library this tree ran before 2026-10-13 was
built that way, and `pairing()["headers"]` says `stand-in:...` of such a
one. The published wheel, and the pair the lead built from `cf7466e` that
day, are compiled against the wheel's own headers (`pairing()["headers"]`
begins `fork:`). A clone of `pthom/imgui_bundle` (`../imgui_bundle`, or
`IMGUI_BUNDLE_CHECKOUT=`) is read in place of one download when it is there.

`make shot` is the one to reach for when you want to *see* something and cannot
sit in front of a window — it drives the real app through the real `immapp.run`,
counts frames, and grabs the framebuffer:

    make shot ARGS="--tab columns:3 --width 1400 --out artifacts/columns-3.png"
    make shot-all             # every page in each state it names for itself: 25 PNGs

It needs a display and numpy. `make shot-headless` is the Xvfb fallback for a
machine with neither. With the library asked for and not drawing when the
window closes (refused at import, no fonts, a failure mid-run) a shot exits 3
and writes no PNG, so a photograph of the one line cannot be filed under a
page's name.

`make svg` is the one thing here that does not go through imtypeset. It runs
imscribe's own Python layout core, which is kept for it and called the
reference core, and writes five files into `artifacts/` (gitignored — they
are outputs; the script that makes them is what is version-controlled):

| file | what it shows |
|---|---|
| `markdown.svg` | the sample document, every glyph a real outline |
| `markdown-debug.svg` | the same, with line boxes, baselines and glue overlaid |
| `selection.svg` | a multi-line drag, highlighted by `imscribe.selection` |
| `sigma.svg` | the display-size summation |
| `sigma-compare.svg` | display against text style, to show the operator is a *different glyph* |

Open `markdown-debug.svg` first. It is the one that shows the machinery.

## Embedding it

`imscribe` itself is an import surface (`imscribe.__all__`, 102 names since
2026-10-12, 89 the day before and 94 before the swap, resolved lazily:
`import imscribe` loads neither ImGui nor fontTools nor imtypeset), and four
examples use nothing else of the package except the module
`imscribe.typesetter`:

    python examples/typeset_minimal.py   # a markdown string in a plain ImGui window
    python examples/stream_replay.py     # demo/stream.md arriving in pieces
    python examples/chat_transcript.py   # finished messages and one streaming
    python examples/diff_minimal.py      # a diff from before/after text; --side-by-side, --edits

Each needs imtypeset installed, which it is wherever imscribe was installed
on a platform imtypeset has a wheel for; nothing is set in the environment.
Without the library (none installed, or `IMSCRIBE_NO_TYPESET=1`) an example
says why on standard error and exits 1 before any window opens.

**How the library is found** (`imscribe.typesetter.module()`; the routes
since 2026-10-11, which of them is normal since 2026-10-13):

1. **An installed `imtypeset` distribution: the normal route.** Known by its
   metadata or by `imtypeset/_attestation.json` beside the package (so a
   freezer that drops `dist-info` does not hide it), imported with no
   variable set; `pairing()["route"]` is `"distribution"`. An installed
   imtypeset reads neither variable below: where both it and the variables
   are present it is the installed one that loads, and
   `pairing()["ignored_environment"]` names the variables. Run with the
   wheel from PyPI in `./.venv` and nothing set (ADOPT-DIST's builder, an
   agent, 2026-10-13, Linux x86-64): `kind` ready, `imtypeset_route`
   installed, `headers` `fork:c9a0a84f...`, exit 0. `IMSCRIBE_NO_TYPESET=1`
   (`imscribe.typesetter.DISABLE_VARIABLE`) stops this route being looked
   for and nothing else: a library the two variables name still loads.
2. `IMTYPESET_LIBRARY` set, with `IMTYPESET_PYTHON`, **where no imtypeset is
   installed**: the developer's route, for a pair `make typeset-lib` built.
   It works only when `IMTYPESET_PYTHON` names a package directory with NO
   library in it (what `make typeset-lib` stages). After a first load by
   this route a host may remove both variables: `reset()` and the next
   `module()` use the pair that was loaded (`pairing()["named_by"]` is then
   `"remembered"`; `imscribe.typesetter.forget_pair()` ends that).
3. Otherwise not loaded, `kind()` is `Kind.NOT_INSTALLED`, and `reason()`
   says what is missing: `typesetter.ABSENT_REASON` ("imtypeset is not
   installed: pip installs it with imscribe where imtypeset has a wheel
   ..."), or under `IMSCRIBE_NO_TYPESET` `typesetter.SWITCHED_OFF_REASON`
   ("IMSCRIBE_NO_TYPESET is set, so an installed imtypeset is not looked
   for, ..."). A library `IMTYPESET_LIBRARY` names with no imtypeset package
   to load it is `Kind.REFUSED`, and its sentence begins `IMTYPESET_LIBRARY
   names <path>`. (Until 2026-10-14 the first two read `IMTYPESET_LIBRARY is
   not set`.)

**A library older than 0.4 is refused** (`imscribe.typesetter.MINIMUM`),
before anything is drawn: `Kind.REFUSED`, "the imtypeset at <dir> is 0.3.0
and this imscribe needs 0.4 or later; the two were not installed together".

**The suite does not run the way a user's process does.** `tests/conftest.py`
sets `IMTYPESET_LIBRARY` to the installed library's path and
`IMSCRIBE_NO_TYPESET=1` for every test, so that the fifty files that ask
"is the library there" by the variable stay true; the installed package
ignores the variable. Route 1 with nothing set is run by two tests, one
command-line check and one install into a scratch virtualenv. If a view
behaved differently under it, most of the suite would not see it
(ADOPT-DIST's builder's own caution).

`imscribe.typesetter.pairing()` answers what a host puts in an About box or a
bug report, as a `dict` of strings and `None` with always the same seventeen
keys (twelve on 2026-10-11): `imscribe_version`; `route` (`"environment"`,
`"distribution"` or `"none"`), `named_by`, `ignored_environment`; `kind` and
`reason`; `library`, `package`, `distribution`; `imtypeset_version`,
`imgui_version`, `wheel_version`, `built_for`, `headers`, `accepted_by`; and
imtypeset's own words, `imtypeset_kind` and `imtypeset_route`. It is on the
facade (`imscribe.pairing`). `reason()` does not name the route. Each example takes `--frames N`
to draw N frames and exit, which is how the tests run them. What a host
calls, in the order it calls it:

| step | names |
|---|---|
| the library | `load_fonts()` at the end of hello_imgui's `load_additional_fonts`, never in `post_init`; `ready()`, `reason()`; `imscribe.typesetter.unload()` before the ImGui context goes |
| font files | `register_font` for a host's own file under a role (`Face`); the library is handed the same file |
| theme | `Theme.build(faces=, align=)`, `Theme.at_pixel_height`, `Faces`, `Align`, `Spacing`, `BlockKind` |
| a settled document in a pane | `TypesetView(markdown, theme=, palette=)`, then `draw()` inside the host's own window: fills the pane, paints no background, selectable, culled by the library |
| when it cannot draw | `TypesetUnavailable`, from the constructor with no library and from `draw()` when it is not ready or the library failed; the message is the reason. There is nothing else to draw with |
| colour | `Palette`, `DARK_PALETTE`, `Palette.with_roles`; `TypesetView.set_colours` for inks over ranges |
| links, copy, where the mouse is | `TypesetView(on_link=, copy_as=)`, `selected_source`, `under_mouse`, `block_under_mouse` |
| tables | blocks of the library's document: cells wrap, select, copy and are searched; `set_table_columns` to state widths |
| columns | `TypesetView.set_columns(3, height=...)` or `(3, balance=True)` |
| a document that arrives in pieces | `MarkdownStream`, `TypesetStreamView` |
| find | `MarkdownConverter(theme).describe(blocks)` → `Description`; `FindIndex.of`, `Finder`, `Match`; `view.set_marks(finder.marks())`, `view.scroll_to` |
| a diff | `Diff.from_texts`, `Diff.from_edits` (several edits), `Diff.from_unified` (text that arrives as a diff), `UnifiedDiffStream`; `TypesetDiffView`, `DiffLayout`, `DiffPalette`. Since 2026-10-13 its cell is the whole pixel the device draws the code face at, asked of the library; `cell=` is accepted, ignored and warns (`DeprecationWarning`), and goes in the release after |
| a fenced `diff` drawn as one, or any widget in a block's place | `host_for=TypesetDiffFences(...)` on a view; `HostFor`, `Hosted`, `HostedDiff` |
| `$...$` and `$$` | `TypesetView(markdown, math=True)`: the library sets the formula, and shows what it refuses as its source |

**What a host can ask for since 2026-10-12.** Built for the first real
host, pptmstr, whose requests P1 to P19 and imscribe's answers are in
`HANDOFF-pptmstr.md`, "Answers to pptmstr": read that for what each does not
do. Every option is off by default and the defaults draw what they drew.
Built by agents; **nobody has looked at any of it on a screen**, and nothing
was run through pptmstr's code.

| to | names |
|---|---|
| know why the library is not drawing, as a kind | `kind()` answers a `Kind`: ready, not installed, refused, failed, unsupported, unchecked. "Unsupported" is the host's to say (`imscribe.typesetter.unsupported(why)`): imscribe cannot tell it from "not installed" |
| come back from a failure | `reset()`, then `load_fonts()` again, between frames. Every load leaves seven more fonts on Dear ImGui's atlas and nothing takes them off (measured in a window by the builder of the task PH-GATE) |
| ask without loading anything | `verdict()` asks a child process and answers `pairing()`'s dict; `python -m imscribe.typesetter` prints it as JSON and exits by the kind (0 ready, 3 not installed, 4 refused, 5 failed, 6 unsupported, 7 unchecked). In a frozen application the answer is "unchecked" |
| be refused a mismatched imtypeset before a draw | `module()` checks the names and fields imscribe calls (`imscribe.typesetter.REQUIRED`, `missing`); not what a name means |
| draw a native ImGui line in a typeset face | `imscribe.typesetter.font(face)`; the size to push is the em times the file's line-height ratio, not the em |
| read markdown showing what was written | `ReaderOptions(html_as_text=, images_as_text=, keep_glob_stars=, show_link_destinations=, show_fence_info=, backslashes_as_written=)` as `reader=` to `parse_markdown`, `MarkdownStream` and `TypesetView`; one object for a settled document and a stream. Six fields (four until P27 and P32) |
| size inline code apart from its prose | `Theme.inline_code_scale` and `Theme.inline_code_step`, set with `dataclasses.replace` |
| show blocks that are not markdown | `TypesetView([MarkdownText(...), MarkdownCode(...), ...])` with `MarkdownRule`, `MarkdownTable`, `MarkdownCell`, `ColumnAlign`, a style from `theme.style(BlockKind...)`; or a `Description` from `imscribe.description.description_of`. Anything else is a `TypeError` at the call |
| scroll or clip wide code | `TypesetView(code_overflow="wrap" \| "clip" \| "grow")`, `content_width` for the host's scroll range |
| one line pitch for every line of a block | `TypesetView(fixed_line_height=True)`: text and code, not tables, not a block holding a display formula |
| a settled table as wide as a stream held it | `TypesetView(table_widths="natural")`; equal to a stream's only when no cell of the stream was ever wider than it ended |
| know whether a diff's file header fit | `TypesetDiffView.headers()` answers a `DiffHeader` a file: `text`, `warning`, `fits`, `text_fits` |

**And since later that day** (pptmstr's P23 to P33; `docs/status.md` section
0g has each with its measurement, and `HANDOFF-pptmstr.md` each in its
builder's sentences). Two of these changed a default, and both are said
there loudly: a tab in a fenced block is now a tab in `texts` and in a copy
(it was four-column spaces; nothing moves on screen), and a view wholly
outside the clip rectangle no longer calls the library.

| to | names |
|---|---|
| know the fonts' ImGui context is gone | `ready()` is false in any Dear ImGui context but the one `load_fonts()` succeeded in, and a view raises `TypesetUnavailable`; `imscribe.typesetter.why_not_ready()` is the sentence; `kind()` stays ready; `load_fonts()` in the new context is the way back |
| have `Spacing.FRENCH` reach the screen | nothing to call: the theme's `spacing` is now handed to the library (it was not, before 2026-10-12) |
| give a list's end a paragraph's gap | `dataclasses.replace(theme, space_after_list=theme.style(BlockKind.PARAGRAPH).space_below)` |
| see a fence's info string | `ReaderOptions(show_fence_info=True)`: a block of its own in front of the code |
| see backslashes as written (`C:\_work\*.log`) | `ReaderOptions(backslashes_as_written=True)`; not reached: a link's destination and title |
| size a theme without opening a font file | call `Theme.at_pixel_height`, `em_size_for_pixel_height` or `code_size(pixel_height=)` AFTER `load_fonts()` has succeeded: the library answers. Before it, or without the library, imscribe's own fontTools reader answers, at about a third of a second cold |
| keep hundreds of views in one scrolling pane | nothing to call: a `TypesetView` or `TypesetStreamView` out of sight rests on the size its last draw measured. `TypesetDiffView` does not rest |
| stop child processes inheriting the two variables | remove them after the first load (route 1 above) |

**A host that holds the before and after text must build its diff from them**
(`from_texts`, `from_edits`) and not from a unified string of its own making:
`difflib` over texts with no closing newline writes a removed and an added line
as one physical line, which no parser can take apart. `docs/adoption-plan.md`
has the measurement.

**Eight names mean something else than they did on `main`**: `HostFor`,
`SetLine`, `Hosted`, `DiffLayout`, `SyntaxColour`, `language_for`,
`HostedDiff` and `FindIndex` are the typeset layer's, with other signatures,
and importing one raises nothing. Twenty-one are gone (`BareView`,
`StreamView`, `DiffView`, `StreamDocument`, `draw`, `markdown_math` and the
rest: `docs/status.md` section 0d has the list). Twenty-nine names are on
the surface only because `make svg`'s modules are in the tree
(`build_document`, `compose`, `ship` and so on): they are the reference core
and nothing of theirs reaches a window.

**Nobody has looked at any of the four examples.** Each has been opened in a
real window on Xvfb by its tests, which count vertices, calls and texts. The
dark palette, a stream at reading speed and a diff side by side are all there
to be judged and have not been.

## The two litmus tests

1. **Multi-type markdown** — headings, paragraphs with bold/italic/code, lists,
   block quotes, fenced code, a rule and a table, laid out as one document and
   selectable with the mouse.
2. **A sigma summation** — `\sum_{i=1}^{n}` with limits above and below a
   display-size operator, from the real `MATH` table in Latin Modern Math. The
   big sigma is a genuine larger glyph off the variant chain
   (`summation.v1`, which has **no codepoint at all** in the font), not the body
   glyph scaled up.

Both pass. [`docs/litmus.md`](docs/litmus.md) is the write-up, including what is
still wrong with the output.

**These are tests of the reference core, rendered by `make svg`**, and since
2026-10-11 they are all that core is kept for. What the demo's window shows is
imtypeset's setting of the same kinds of material, which has its own tests in
`../imtypeset` and, here, tests that count what reaches a draw list.

## `make run` needs a display, and the library

The ImGui demo is real and `make run` launches it (with imtypeset's wheel
installed, which `make bootstrap` does; `make run TYPESET=1` is the
developer's route of "Thirty seconds"): one window,
1300x800 by default, with a sidebar list on the left and the chosen page on
the right. The pages are modules under `imscribe/ui/pages/`, found by scanning
the package; adding one edits no list anywhere. To open on a page, or to
photograph every one:

    make run ARGS="--tab diff"
    make run ARGS="--tab stream:table,done"
    make shot-all

A name after `--tab` is a page's name in lower case, optionally with option
words of its own after a colon; `python scripts/shot.py --list` prints the 25
requests `make shot-all` photographs.

| group | page (`--tab`) | what it is, in one line |
|---|---|---|
| Typesetting | Document (`document`) | `demo/sample.md`, justified on a page sheet and selectable with the mouse |
| | Columns (`columns:1`..`3`, `balance`) | one document cut into newspaper columns by the library, filled in order or balanced |
| | Specimen (`specimen`) | imtypeset's own specimen section: every face at one size, one face at every size, and the kerning |
| | Formula (`formula`) | imtypeset's own gallery of TeX math-mode rules |
| | Math in text (`math`) | imtypeset's own section of `$...$` and `$$` in running text |
| Embedding | Themes (`themes`) | one document under four palettes, three face sets and any pixel size, optionally split in two |
| | Tables (`tables`) | drag a column edge and the cells re-wrap |
| | Find (`find`) | a search box over a long document: every match marked, next and previous |
| | Inspector (`inspector`) | point at a block: its source, role, lines and rectangle, and a copy menu |
| Streaming | Stream (`stream`) | one source replayed as tokens under both commit policies, with counters |
| | Chat (`chat`) | a canned conversation, no network: streaming replies with code, a diff, a table, math, one selection |
| Diff | Diff (`diff`) | unified, side by side or both, on the diffs a coding agent's host is handed |
| Performance | Stress (`stress`) | 1 to 16 panes at once, finished or streaming, with the per-frame cost |
| Experimental | Typeset (`typeset`) | the sample document with a find box; the first page that drew through imtypeset |

Fourteen pages. Specimen, Formula and Math in text each have a *text size*
combo of 14, 16, 19, 23 and 28 px and open at 23 (since 2026-10-11, after
the user ran the demo; `--tab math:19` opens at 19). The fifteenth, Blocks,
showed the old core's boxes and was deleted on 2026-10-11. **Every page has run in a real window on Xvfb with the
library, in the suite, and no person and no agent has looked at any of them.**

Without a display `scripts/run_demo.py` refuses rather than hanging: it exits
2 at once and prints the `make shot` recipes instead. Without the library it
says so on stderr and opens the window of one-line pages all the same; with
the library asked for and not drawing, it says why when the window closes.

**"There is a display" is a statement about a session, not about a machine.**
From the sandbox these sessions ran in, `DISPLAY=:1` was set and unreachable
(`socket(AF_UNIX)` refused), and every window was on an Xvfb in a user
namespace over TCP with a software rasteriser — `scripts/mouse_probe.py`'s
`xvfb_command` builds that shell, and `tests/conftest.py`'s `window` fixture
uses it. No window of this branch has been opened on a GPU. Since
2026-10-13 the sandbox is off and `DISPLAY=:1` is the owner's real screen;
the `window` fixture starts its own Xvfb all the same, because a real
pointer moving over a test's window turned tests red that day (four in one
builder's run, seven in another's; each passed under Xvfb)
(`IMSCRIBE_TEST_DISPLAY=1` asks for the session's display instead).

**What a test can and cannot say here.** A frame needs no window: a Dear
ImGui context with no backend runs frames, and the library writes vertices
into its draw lists. So the suite counts vertices, reads back texts, counts
the library's calls and compares rectangles, with no display at all; and in a
real window on Xvfb it reads each page's frame for ink that cannot be told
from its ground. It does not see a pixel. Whether a line is well broken, a
table well ruled or a formula well set is not asserted anywhere in this tree.

**What has been exercised with a mouse.** `scripts/mouse_probe.py` runs the
real app in a real GLFW window and posts mouse and key events to ImGui's
input queue over positions read back from the view: a drag in each direction,
a drag across three lines, a double click, a triple click, Ctrl+C read back
from the clipboard, a wheel scroll followed by a drag on a line that had been
below the fold, and a drag that ends on a line beneath the bottom of the
window and is then copied. Eighteen checks, with expectations built from the
texts described to the library and the markdown source:

    python scripts/mouse_probe.py --xvfb

`tests/test_mouse_probe.py` runs it under `make check`. **Its
limit, in its own words**: where a character is on screen is asked of the same
library that then hit-tests the click, so a defect the two share is not seen.

**What has not.** The events enter at `ImGuiIO`, not at the X server: no
pointer has been moved on a screen and no physical button pressed, so GLFW's
cursor and button callbacks and a window manager's part in focus and capture
are untested. No person has dragged a selection in this demo and said what it
was like.

The **SVG backend** is not a fallback for any of that. It emits real glyph
outlines through fontTools from the reference core's layout and needs no GPU,
no ImGui and no imtypeset. It is a second, independent setting of the same
markdown, not a picture of what the window shows.

## Interpreter

    make bootstrap  # builds ./.venv and every target picks it up, no edit needed

Until that runs there is no interpreter: every target that needs one stops and
names `make bootstrap`. `make venv-info` says what the others will use.
`pyproject.toml` states floors for `markdown-it-py`, `fonttools` and the dev
tools, and **two exact pins that move together: `imgui-bundle==1.92.900`**
(since 2026-10-11; it was the floor `>=1.92.900` before) **and
`imtypeset==0.4.3.192900`** (at 0.2.0; `0.4.1.192900` from 2026-10-13; under a platform marker;
"Packaging" below). An imtypeset wheel is built for ONE imgui-bundle wheel,
says which in its fourth number, and checks at import that it is the one
running, so a range promised what the pairing cannot keep. An upgrade
changes both pins and runs `make check`. `./.venv` was brought level on
2026-10-13 by ADOPT-DIST's builder without a full bootstrap (imtypeset's
test oracle runs on this virtualenv and its fontTools 4.66.0, markdown-it-py
4.2.0 and imgui-bundle 1.92.900 are held): `pip list` there says
`imscribe 0.2.0b1` (editable) and `imtypeset 0.4.1.192900`. **`make
bootstrap` from nothing, with the new dependency line, has not been run**;
an install of the built wheel into a new virtualenv has (it resolved
fontTools 4.66.1, newer than what everything here was measured on).

## Packaging

For whoever packages an application that draws through imscribe. Written
2026-10-12 by the builder of the task O-REL, an agent, from this tree, from
imtypeset's `docs/sidecar.md` (sections 8, 10 and 11, at its `v0.3.0`) and
from the result files of the builders named. **Read it as a list of what is
known and by what means, not as a tested procedure: no application has been
packaged with any of this.** Brought level on 2026-10-13 by the builder of
ADOPT-FINAL, an agent, from ADOPT-DIST's and ADOPT-API's result files: the
version, the pins, what `make dist` did when it was run, and how a release
is published.

### The version, and a file to require

`imscribe.__version__` is `0.2.0` (`0.2.0b1` from 2026-10-13, `0.2.0.dev0`
the day before), the same string as `pyproject.toml`'s and as
`pairing()["imscribe_version"]`. `0.1.0` was imscribe with its own Python
layout core; `0.2` draws through imtypeset and nothing else. `0.2.0b1`, a
beta, was the first version on PyPI (2026-10-14); pip installs it only when
asked (`pip install --pre imscribe`, or `imscribe==0.2.0b1`). `0.2.0` is
the first release that is not a beta; from there the middle
number changes when a name in `imscribe.__all__` is removed or changes
meaning, or when the imgui-bundle pin or the imtypeset line changes. (Agents'
decisions; `docs/decisions.md`, "A release artefact" and "imtypeset 0.4.1
from PyPI".)

    make dist    # dist/imscribe-<version>-py3-none-any.whl, .tar.gz, <file>.sha256, BUILT-FROM

`make dist` (`scripts/make_dist.py`) builds **the commit `HEAD`, not the
working tree**: it exports the commit twice with `git archive`, builds each
export with `python -m build --no-isolation` under `SOURCE_DATE_EPOCH` = the
commit's time, and installs the two files into `dist/` only if the two
builds are byte for byte the same and the wheel holds `imscribe/` and its
metadata and nothing else. It then prints the requirement strings:

    imscribe @ git+https://github.com/WalterCReel3/imscribe.git@<full commit>
    imscribe @ https://github.com/WalterCReel3/imscribe/releases/download/v<version>/<wheel>#sha256=<hash>
    imscribe==<version> --hash=sha256:<wheel> --hash=sha256:<sdist>

(The script prints whatever `pyproject.toml`'s `Repository` URL is; it was
`imgui-adv-text` until 2026-10-13 and GitHub redirects the old one.) The
first works today for a commit that is on GitHub (pip clones and builds; it
needs network and `hatchling`). The second resolves only once somebody
publishes a release at that URL holding that file. The third is for a
directory or a mirror that holds the files, and for PyPI once the version is
there. `make dist` itself publishes nothing, tags nothing and reaches no
network.

**`make dist` has built real files once, of a scratch commit** (ADOPT-DIST's
builder, an agent, 2026-10-13, hatchling 1.32.4, build 1.6.1). It builds a
commit and a builder may not commit here, so the working tree was copied
into `build/adopt-dist-scratch/repo`, committed there, and
`scripts/make_dist.py --root` run on that. What that run showed: two builds
from two exports were the same bytes; the wheel holds `imscribe/` (54 files)
and `imscribe-0.2.0b1.dist-info/` (`METADATA`, `WHEEL`, `RECORD`,
`licenses/LICENSE`), `Metadata-Version: 2.5`; `twine check --strict` passed
on the two files (twine 7.0.0). **`twine check dist/*` fails** on
`dist/*.sha256` ("Unknown distribution format"): name the two files. The
wheel installed into a new virtualenv with everything else from PyPI
(imgui-bundle 1.92.900, imtypeset 0.4.1.192900, fontTools 4.66.1,
markdown-it-py 4.2.0; `pip check` clean), `python -P -m imscribe.typesetter`
answered ready by route distribution, and `examples/typeset_minimal.py
--frames 5` drew in a window. Run again later that day by REVIEW-FIX's
builder (an agent) after the sdist was narrowed, twice, with the same three
results; that wheel was not installed anew. **Not run: `make dist` on the
commit that will be released (its hashes will not be the scratch
commit's).** `tests/test_dist.py` still holds the script against a stand-in
builder.

**Publishing is `.github/workflows/release.yml`; it published `0.2.0b1`
from the tag `v0.2.0b1` on 2026-10-14 (GitHub run 38497674627).** A
pushed tag `v<version>` builds with `scripts/make_dist.py`, refuses a tag
that is not `pyproject.toml`'s version, installs the built wheel from the
index (after installing the two system libraries `import imgui_bundle`
needs on Linux and no wheel carries, libX11 and libXext) and asks it for its
library, and only then uploads the wheel and the
sdist to PyPI by trusted publishing (OIDC, no stored token) in the GitHub
environment `pypi`. A run started by hand with `testpypi` ticked uploads to
TestPyPI and never to PyPI. What it needs that only the owner can do, a
pending publisher on PyPI and the environment on GitHub, is in
`ASSIGNMENTS.md`. On 2026-10-13 at 14:21 `https://pypi.org/pypi/imscribe/json`
answered 404; the first upload, `0.2.0b1`, holds the name since.

What the wheel holds, by `pyproject.toml` and by those runs: the package
`imscribe` with `imscribe/py.typed`, and the licence (58 members); no
`tests/`, no `demo/`, no `examples/`, no `docs/`, no handoff files. **Since
later on 2026-10-13 the sdist holds none of those either** (they were in it
until a review that day: seven of its files named a `/home/` path, and the
working notes are not a release): it is `imscribe/`, `pyproject.toml`,
`LICENSE`, `README-pypi.md`, `PKG-INFO`, and `.gitignore`, 59 files, and
`make dist` refuses an sdist that holds anything else. `.gitignore` is
there because hatchling puts it there whatever the include list says; its
comments were made neutral on 2026-10-14, with every pattern kept. So the
suite cannot be run from the sdist; it is in the repository. The page PyPI
shows is `README-pypi.md`, not this file. The
demo application is inside the package (`imscribe.ui.app`,
`imscribe.ui.pages`) and its pages say so themselves when `demo/` is not
there.

### The pins to hold together

Three things are one compatible unit, and an update replaces all of them or
none (imtypeset's rule, its `docs/sidecar.md` section 11; imscribe's T7):

| what | pin | why exact |
|---|---|---|
| `imgui-bundle` | `==1.92.900` | the imtypeset library is linked against that wheel's extension module and refuses any other at import. imscribe's own metadata states this pin |
| `imtypeset` | `==0.4.3.192900` | the fourth number is the imgui-bundle line the wheel was built for (`1.92.900`), and that wheel itself requires `imgui-bundle==1.92.900`. `imtypeset==0.4.3` matches nothing. **Never upgrade imtypeset alone** (`pip install -U imtypeset`): the resolver takes the newest line and replaces the application's imgui-bundle. Move the two pins together. imscribe's own metadata states this pin since 2026-10-13, and refuses a library older than 0.4 at its gate |
| `imscribe` | `==0.2.0` | the beta `0.2.0b1` is on PyPI too, and pip takes it only with `--pre` or the exact version; it requires imtypeset 0.4.1, which installs only on CPython 3.11 |

imscribe's metadata lists imtypeset as a **hard dependency under a platform
marker** (since 2026-10-13; not an extra, because there is no other
renderer):

    imtypeset==0.4.3.192900; python_version >= '3.11' and python_version < '3.15' and ((sys_platform == 'linux' and platform_machine == 'x86_64') or (sys_platform == 'darwin' and platform_machine == 'arm64'))

The marker is where imtypeset has wheels, copied from its `docs/releasing.md`
section 5: CPython 3.11 to 3.14; Linux x86-64 with glibc 2.28 or later;
macOS 14 or later on arm64. Everywhere else it is false: pip leaves
imtypeset out, `pip install imscribe` still succeeds,
`imscribe.typesetter.kind()` is `Kind.NOT_INSTALLED` and a view says so and
draws nothing. What no marker can say: Linux with musl (Alpine) is Linux on
x86-64, has no wheel, and the install fails there at that line. The wheel on
PyPI is compiled against the imgui-bundle wheel's own Dear ImGui headers
(`pairing()["headers"]` begins `fork:`); 0.4.1's sha256 for CPython 3.11 on
Linux was `4e7b1477bb9482eb0b99e0a244e7d97383cb77ecee05747cfee70a0434ec43ca`
(ADOPT-DIST's builder read it on 2026-10-13, with its attestation: GitHub
Actions run 38434871056 of WalterCReel3/imtypeset at `e6160c0`). **Read, not
run by imscribe: every wheel but that one**, macOS's among them.

On Linux **`imtypeset/` and `imgui_bundle/` must be in one directory**: an
imtypeset wheel installed with `pip --target` into a directory of its own
was refused (`pairing()["imtypeset_kind"]` `layout`), and accepted with
`imgui_bundle` beside it (N-IMT's builder, a symlink, load 7). An updater
that copies files replaces `imtypeset/`, `imgui_bundle/` and
`imgui_bundle.libs/` in one step.

### The six font files

Every face the typeset path sets text in is a file inside the `imgui-bundle`
wheel, under `imgui_bundle/assets/fonts`, unless the host registers its own
file for the role with `imscribe.register_font`:

    Roboto/Roboto-Regular.ttf
    Roboto/Roboto-Bold.ttf
    Roboto/Roboto-RegularItalic.ttf
    Roboto/Roboto-BoldItalic.ttf
    Inconsolata-Medium.ttf
    latex/latinmodern-math.otf

(and `Roboto/LICENSE.txt` beside the first four). imtypeset itself looks for
no font: it opens what imscribe hands it, and since `03b5cd4` its installed
import gate reads none, so a freezer that drops `imgui_bundle/assets` does
not break the import. What it does to imscribe, by `load_fonts`'s docstring
and not by a run with the files taken away: a role whose file is missing is
left out and said in `imscribe.typesetter.trouble()`, and text in that role
is set in the document's face. Carry the six, or register a file for every
role you draw. Seven roles are loaded from the six files: bold code has no
file of its own and is Roboto Bold unless a host registers a bold monospace
face (`imscribe/fontfiles.py`).

### What a frozen application must carry

From imtypeset's `docs/sidecar.md` section 10 and imscribe's builders' result
files. **Nothing has been frozen by anyone**: the other team imitated a
frozen interpreter's properties (`sys.frozen` set, `sys.executable` not an
interpreter, process creation disabled, the package read-only) and imscribe
deleted a wheel's `dist-info` by hand; no PyInstaller, py2app, Briefcase or
Nuitka run exists.

- `imtypeset/`: its modules, the library (`libimtypeset_bundle.so`, or
  `.dylib` on macOS) and **`imtypeset/_attestation.json`**, all in the
  package's own directory. The last two are data files to a freezer and must
  be collected explicitly. `dist-info` is not needed when the attestation
  is there (N-IMT's builder: a real wheel with its `dist-info` deleted by
  hand was found, accepted, fonts loaded). With neither, imscribe answers
  `not-installed` and does not import the package.
- `imgui_bundle/` as the pinned wheel installed it, in the same directory,
  with the six font files above.
- of imscribe: the package. `import imscribe` imports nothing else: every
  name of the facade is resolved at first use by `importlib.import_module`
  of a module named in a string, which a freezer that follows `import`
  statements does not see (from reading `imscribe/__init__.py`; no freezer
  was run). So tell the freezer to take the whole package, or name the
  modules: **`imscribe.fontfiles`** and **`imscribe.typeset_metrics`**
  (N-METRICS's builder's sentence for a freezer), `imscribe.typesetter`,
  `imscribe.typeset_markdown`, `imscribe.description`, and the views you draw
  (`imscribe.ui.typeset_view`, `imscribe.ui.typeset_stream_view`,
  `imscribe.ui.typeset_diff_view`). **Optional**: the demo application
  (`imscribe.ui.app`, `imscribe.ui.pages`), the reference core and
  `imscribe.backends.svg`; and `imtypeset.demo`, which imscribe's gate no
  longer requires (only the three gallery pages of the demo call it).
- In a frozen application `verdict()` starts no child and answers
  `"unchecked"`; `kind()`, `module()` and every view constructor still run
  the library's own gate in the process.

### What `pairing()` gives an About box and an updater

- **An About box or a bug report**: `imscribe.pairing()`, the seventeen keys
  above. It may be the import; it never raises.
- **An updater, before it switches to a staged environment**: that
  environment's `python -m imscribe.typesetter`, which prints the same dict
  as one line of JSON and exits 0 ready, 3 not installed, 4 refused, 5
  failed, 6 unsupported, 7 unchecked; or `imscribe.verdict()` from the
  running application for its own interpreter (it blocks up to `timeout`
  seconds, 120 by default; call it off the UI thread). When a pair is
  refused, `imtypeset_kind` is imtypeset's word for which partial update it
  is (`bundle-mismatch`, `damaged`, `package-mismatch`, `layout`,
  `unchecked`, `wrong-platform`) and `reason` a sentence with no path in it.

### The order a host follows

1. a Dear ImGui context (hello_imgui has made it by `load_additional_fonts`);
2. `imscribe.register_font(...)` for the host's own files, if any;
3. `imscribe.load_fonts()`, at the end of `load_additional_fonts`, never in
   `post_init`;
4. then the themes: `Theme.at_pixel_height(...)`,
   `imscribe.em_size_for_pixel_height(...)`, `code_size(theme, pixel_height=)`.

In that order no font file is opened by imscribe and fontTools is not
imported (N-METRICS's builder: a document theme 0.22 ms cold against 373 ms
by imscribe's own reader, median of 9 fresh interpreters, load 3.5). A theme
sized before step 3 is the same theme at the old cost. A file registered
after step 3 is not what a theme is sized from until `load_fonts()` is
called again.

### What is not known

- **macOS, beyond one run.** The owner ran 0.2.0b1 from PyPI on one Apple
  Silicon Mac (2026-10-14, macOS 26.7, CPython 3.11): the demo ran, Cmd+C
  copied, the suite's 25 failures there were `/proc/loadavg` (since fixed,
  not yet rerun there). `macos.yml` has not run. The pinned imgui-bundle and
  imtypeset have macOS wheels for Apple Silicon on macOS 14 or later only.
- **A frozen application**, on any system; code signing; a hardened runtime.
- **A GPU.** Every window here was on Xvfb with a software rasteriser.
- **A display density other than 1.** imtypeset `v0.3.0` draws on the
  device's pixels at a framebuffer scale other than 1 (its H19 answer,
  measured there headless on Linux). imscribe's O-IMT2 builder measured that
  at scale 2 the vertex bytes of six demo pages differ from `03b5cd4`'s in
  24 of 24 draws and at scale 1 are the same in 24 of 24; no test of
  imscribe's sets a scale other than 1, imscribe still assumes 96 px per inch
  in five places (the Mac audit's count, by reading), and nobody has looked
  at either.
- **Some things against GitHub**: the fetch of imtypeset by tag or hash, a
  `pip install` of imscribe from a git reference. (`ci.yml` and
  `release.yml` have run there, and `0.2.0b1` was uploaded to PyPI, on
  2026-10-14.)
- **A display density that is not a whole number**, for the device grid of
  2026-10-13: the views round an origin, a pane and a code block's indent to
  whole units, the diff view snaps its cell to whole framebuffer pixels, and
  the two agree only at 1, 2 and 3. imtypeset measured its side at 1.5;
  nobody has measured imscribe's.
- **Whether two builds of the imtypeset library are the same bytes**: they
  are not (two builds of `2fd705e` differing only in the output directory's
  name gave different files; `HANDOFF-imtypeset.md`, H45), so a library is
  identified by its own checksum and its attestation, not by its commit.

**Continuous integration** is `.github/workflows/ci.yml`, three jobs since
2026-10-13: `plain` (`IMSCRIBE_NO_TYPESET=1 make check`, no library looked
for), `typeset` (`make check` with imtypeset's wheel installed from PyPI as
a dependency), and `sidecar`, started by hand only, which builds the pair
from the ref in `imtypeset.ref` and runs `make check TYPESET=1` with no
wheel installed. It has run on GitHub since 2026-10-14; for `b98de08` it was
red (run 38497533497: the mouse probe's own Xvfb could not listen).
`tests/test_ci_workflow.py` holds its text to the
Makefile's targets and variables; its files were read by this project's own
subset reader and by PyYAML, not by `actionlint`. `.github/workflows/macos.yml`
is a macOS arm64 job that starts by hand only and has never run.
`.github/workflows/release.yml` is above.

**A Mac.** The owner's one run of 0.2.0b1 is above. An audit by reading
(`docs/status.md` section 0e) found three things in the way of an install:
the other team's link line is GNU ld's and the pinned wheel has macOS builds
for Apple Silicon only; the library's import gate started a child interpreter
and wrote a stamp beside the library, which a packaged application cannot
do; and every font the text is set in is a file inside the `imgui-bundle`
wheel. `scripts/run_demo.py` and `scripts/shot.py` needed `--force` on a
Mac, which sets no `DISPLAY`, until 2026-10-14; they skip that check on
macOS now. The same reading said every real-window test would skip there;
not checked since. The questions are with the
other team as H1 and H15 to H20 of `HANDOFF-imtypeset.md`. **Since
`03b5cd4` the second is answered on Linux** (an installed imtypeset is
accepted by a shipped attestation, with no child and nothing written; the
macOS half of it has never run), and the other team has written a macOS
link recipe that has never run either. "Packaging" above has the rest.

This used to say `make` drove a **borrowed** interpreter from a sibling project,
`../pptmstr`. That fallback was removed on 2026-10-06: the sibling is the
application meant to depend on this library, and a build that reaches back into
its consumer cannot be depended on. The sandbox this was first built in reached
only one host, so `pip install` could not run in it, and the borrowed venv was
how the project existed at all; `docs/decisions.md` keeps that history.

## Measuring it

The four scripts this section listed (`bench_reflow.py`, `bench_draw.py`,
`verify_advances.py`, `verify_ascent.py`) measured the old ImGui draw backend
and went with it. They are in `main`. What measures the tree now:

    make check                      # the suite prints the Stress page's own per-frame figures
    make run ARGS="--tab stress"    # the same figures, live
    python scripts/visual_diff.py --help      # compare two shots of a page region by region

No test asserts a time. Every figure in `docs/status.md` section 0d names who
measured it and at what load average, and the comparisons against the old
views there were made while both existed: they cannot be re-run on this
branch.

## Where the reasoning lives

**New here? [`docs/guide/`](docs/guide/README.md)** — five short documents
covering the idea, which parts of TeX are implemented, the rendering decisions
and where they depart from TeX and from ImGui, the pitfalls, and the future work.
They are orientation and route into the documents below, which carry the
measurements.

- [`docs/status.md`](docs/status.md) — what is true today. Start here, at
  section 0i (2026-10-13: imtypeset 0.4.1 from PyPI as a dependency, code on
  the device grid, version `0.2.0b1`, what is written and never run), then
  0h (the rename), then section 0g (2026-10-12, later still: P21 to P33,
  imtypeset `v0.3.0`, the version and `make dist`), then section 0f (what the first host, pptmstr,
  asked for first and what of it was built), then section 0e (the pin, how the
  library is found and built, CI, the Mac audit), then section 0d: the swap
  of 2026-10-11, what was deleted,
  what remains of the old core and why, what was measured and what is open. Section 0c is the day
  before, when the new layer stood beside the old. Sections 1 to 6 describe
  `main`. [`docs/decisions.md`](docs/decisions.md), "The swap" and "imtypeset
  adoption, experimental branch", keep the user's sentences apart from every
  agent's decision.
- [`docs/adoption-plan.md`](docs/adoption-plan.md) — the plan to embed this in
  another application, what was built against each phase, and, first, what
  changed and what nobody has looked at.
- [`docs/decisions.md`](docs/decisions.md) — the interpreter, the fonts, the
  two-backend split, the style rules and the scope boundaries, each with the
  constraint that forced it. **Read the CORRECTION at the top first**; it is
  newer than most of the file and withdraws a premise several tasks were built
  on.
- [`docs/postmortem-2026-10-swap-and-three-sessions.md`](docs/postmortem-2026-10-swap-and-three-sessions.md)
  — how the swap to imtypeset went, written by the session's lead: what
  worked, what did not, and what three agent sessions working in tandem
  through handoff files suggest for the application that ran them.
- [`ASSIGNMENTS.md`](ASSIGNMENTS.md) — what only the owner can do, in order.
- [`docs/imgui-risks.md`](docs/imgui-risks.md) — the list for the first person
  with a display, in the order worth working through.
- [`docs/litmus.md`](docs/litmus.md) — the two litmus tests, what the artifacts
  show, and the defects.
- [`docs/tex-notes.md`](docs/tex-notes.md) — a transcription of the relevant
  parts of Knuth's `tex.web`. **Read its CORRECTIONS section before implementing
  from any section below it**; five transcriptions there are wrong and the
  section says which.

- [`docs/subpixel.md`](docs/subpixel.md) — why the text looked crowded, what
  the field does about it, the four options rejected and the one taken.

Out of scope on purpose: hyphenation, extensible glyph assembly, delta nodes,
TeX's page builder, bidi, complex shaping, CJK line breaking, and a LaTeX
parser (the `$...$` subset is an extension above the engine and refuses what
it does not know; matrices are left out for now).
`docs/decisions.md` says why for each. They are decisions, not omissions — but
two of them now have a price somebody has looked at. Hyphenation's is measured
and stated in `docs/status.md`, and a human has since said the loose lines it
costs are not acceptable. **That list was written about imscribe's own core.**
What sets the text now is imtypeset, whose scope is its own tree's to state
(`../imtypeset/docs/`); the list still describes the reference core `make svg`
runs. The column split it used to mention (`\vsplit`, in `imscribe/columns.py`)
is deleted here: the Columns page is cut by the library.

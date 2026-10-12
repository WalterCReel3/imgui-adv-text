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
is an error now; no alias was left. The repository and its URL are still
`imgui-adv-text`, the git tag `advtext-reference` keeps its name, and the
documents under `docs/` that were written before the rename say advtext.
This file was brought level, its dated paragraphs included.

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

## Thirty seconds

    make typeset-lib IMTYPESET_COMMIT=v0.3.0 IMTYPESET_HEADERS=stand-in   # once: build the library the text is set by
    make run TYPESET=1      # the ImGui demo: a sidebar of fourteen pages
    make shot TYPESET=1     # one page of it as a PNG, without watching a window open
    make check TYPESET=1    # ruff + black --check, mypy --strict, pytest with the library
    make check              # the same without it: green, and the tests that need it skip
    make svg                # the reference layout with no GPU, no display and no ImGui
    make dist               # a wheel and an sdist of HEAD with their sha256 (see "Packaging")
    make help               # every target, and which interpreter it will use

**`TYPESET=1` is not optional if you want to see text.** Without it the demo
opens and every page is one line: `imtypeset is not drawing: ` and the reason.

`make typeset-lib` builds into `build/imtypeset-bundle/`, and takes
imtypeset's source one of three ways:

    make typeset-lib IMTYPESET_COMMIT=v0.3.0 IMTYPESET_HEADERS=stand-in   # that commit of the sibling checkout ../imtypeset
    make typeset-lib                            # the sibling's working tree, as it is
    make typeset-lib IMTYPESET_REF=2fd705e2bc358c7dbfda1eb60bd9b71609869e1d   # that commit, fetched from GitHub

imtypeset's `v0.3.0`, commit `2fd705e`, is what this tree is built and gated
against (since 2026-10-12; `c9f8902` and then `03b5cd4` before it, the same
day). Its full hash is the one line of `imtypeset.ref`, which the CI workflow
reads. The Makefile does not read that file: `IMTYPESET_REF` has no default,
and a plain `make typeset-lib` fetches nothing. `IMTYPESET_REF` is a tag, a
branch or a FULL 40-character hash (an abbreviated one cannot be fetched),
taken from `IMTYPESET_REPO`, which defaults to
`https://github.com/WalterCReel3/imtypeset.git`. **The tag `v0.3.0` exists in
the sibling checkout and, by the other team's own file, is not pushed**; so
the third form cannot work until the user pushes it, and it has only ever
been run against a `file://` clone of the sibling, never against GitHub.

**Which Dear ImGui headers the library is compiled against is said on the
command line** (`IMTYPESET_HEADERS`). Left out, imtypeset's build script
fetches the wheel's own headers from GitHub, and with no network it stops
there and installs nothing. `IMTYPESET_HEADERS=stand-in` compiles against
upstream Dear ImGui's from a clone of `ocornut/imgui` (`../imgui`, or
`IMTYPESET_IMGUI_CLONE=`): **every library this tree has ever run was built
that way**, and `pairing()["headers"]` says `stand-in:...` of it. Nobody,
here or in imtypeset's sessions, has compiled the library against the
wheel's own headers. A clone of `pthom/imgui_bundle` (`../imgui_bundle`, or
`IMGUI_BUNDLE_CHECKOUT=`) is read in place of one download when it is there;
it has been there for every build made here, and a build without it and
without network was not tried.

`make shot` is the one to reach for when you want to *see* something and cannot
sit in front of a window — it drives the real app through the real `immapp.run`,
counts frames, and grabs the framebuffer:

    make shot TYPESET=1 ARGS="--tab columns:3 --width 1400 --out artifacts/columns-3.png"
    make shot-all TYPESET=1   # every page in each state it names for itself: 25 PNGs

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

Each needs `IMTYPESET_LIBRARY` and `IMTYPESET_PYTHON` in the environment (what
`make ... TYPESET=1` sets: the library `build/imtypeset-bundle/LIBRARY` names,
whose file name differs by platform, and `build/imtypeset-bundle/pysnap`;
`make typeset-lib` ends by printing both). Without them an example says why
on standard error and exits 1 before any window opens.

**How the library is found** (`imscribe.typesetter.module()`, since
2026-10-11), in this order:

1. `IMTYPESET_LIBRARY` set, with `IMTYPESET_PYTHON`: the development
   override, and the only route the suite or the demo has drawn through.
   It works only when `IMTYPESET_PYTHON` names a package directory with NO
   library in it (what `make typeset-lib` stages). After a first load by
   this route a host may remove both variables: `reset()` and the next
   `module()` use the pair that was loaded (`pairing()["named_by"]` is then
   `"remembered"`; `imscribe.typesetter.forget_pair()` ends that).
2. Otherwise an installed `imtypeset` distribution, known by its metadata or
   by `imtypeset/_attestation.json` beside the package (so a freezer that
   drops `dist-info` does not hide it), imported with no variable set.
   **From imtypeset `v0.3.0` on an installed imtypeset reads neither
   variable**: where both it and the variables are present it is the
   installed one that loads, `route` is `"distribution"`, and
   `pairing()["ignored_environment"]` names the variables. This route has
   met imtypeset's real wheel twice, outside the suite, on Linux x86-64,
   by imscribe's N-IMT and O-IMT2 builders (agents): a stand-in-headers wheel
   from the sibling's build directory, `pip install --no-index --no-deps
   --target`, with `imgui_bundle` symlinked beside it; accepted by its
   attestation, fonts loaded, nothing drawn. No such wheel is published.
3. Otherwise not loaded, and `reason()` is `IMTYPESET_LIBRARY is not set`.

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
| a diff | `Diff.from_texts`, `Diff.from_edits` (several edits), `Diff.from_unified` (text that arrives as a diff), `UnifiedDiffStream`; `TypesetDiffView`, `DiffLayout`, `DiffPalette` |
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

The ImGui demo is real and `make run TYPESET=1` launches it: one window,
1300x800 by default, with a sidebar list on the left and the chosen page on
the right. The pages are modules under `imscribe/ui/pages/`, found by scanning
the package; adding one edits no list anywhere. To open on a page, or to
photograph every one:

    make run TYPESET=1 ARGS="--tab diff"
    make run TYPESET=1 ARGS="--tab stream:table,done"
    make shot-all TYPESET=1

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
uses it. No window of this branch has been opened on a GPU.

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

    IMTYPESET_LIBRARY=... IMTYPESET_PYTHON=... python scripts/mouse_probe.py --xvfb

`tests/test_mouse_probe.py` runs it under `make check TYPESET=1`. **Its
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
tools, and **one exact pin, `imgui-bundle==1.92.900`** (since 2026-10-11; it
was the floor `>=1.92.900` before). The imtypeset library is built for ONE
installed imgui-bundle wheel and checks at import that it is the one
running, so a range promised what the pairing cannot keep. An upgrade is
three acts: change the pin, `make typeset-lib` against the new wheel,
`make check TYPESET=1`. imtypeset itself is not listed as a dependency: it
is on no index a resolver reaches, and a requirement that cannot be resolved
would break `pip install` for everyone ("Packaging" below says what to pin
beside imscribe instead). `pip install` with the pin has not been run on any
machine by the sessions that wrote it (no index was reachable), and
`./.venv`'s own editable install predates both the pin and the version: its
metadata still says `imscribe 0.1.0` and `imgui-bundle>=1.92`. Read
`imscribe.__version__`, not `importlib.metadata`, until `make bootstrap` is
run again.

## Packaging

For whoever packages an application that draws through imscribe. Written
2026-10-12 by the builder of the task O-REL, an agent, from this tree, from
imtypeset's `docs/sidecar.md` (sections 8, 10 and 11, at its `v0.3.0`) and
from the result files of the builders named. **Read it as a list of what is
known and by what means, not as a tested procedure: no application has been
packaged with any of this.**

### The version, and a file to require

`imscribe.__version__` is `0.2.0.dev0`, the same string as `pyproject.toml`'s
and as `pairing()["imscribe_version"]`. `0.1.0` was imscribe with its own
Python layout core; `0.2` draws through imtypeset and nothing else. `.devN`
means there is no release and **nothing is promised from one commit to the
next**, so a requirement names a commit or a file's hash, never the version
alone; N goes up when an artefact is cut for a host to pin. `0.2.0` without
`.dev` is for the first tagged release, which is the user's to make; from
there the middle number changes when a name in `imscribe.__all__` is removed
or changes meaning, or when the imgui-bundle pin or the imtypeset line
changes. (An agent's decision; `docs/decisions.md`, "A release artefact".)

    make dist    # dist/imscribe-<version>-py3-none-any.whl, .tar.gz, <file>.sha256, BUILT-FROM

`make dist` (`scripts/make_dist.py`) builds **the commit `HEAD`, not the
working tree**: it exports the commit twice with `git archive`, builds each
export with `python -m build --no-isolation` under `SOURCE_DATE_EPOCH` = the
commit's time, and installs the two files into `dist/` only if the two
builds are byte for byte the same and the wheel holds `imscribe/` and its
metadata and nothing else. It then prints the requirement strings:

    imscribe @ git+https://github.com/WalterCReel3/imgui-adv-text.git@<full commit>
    imscribe @ https://github.com/WalterCReel3/imgui-adv-text/releases/download/v<version>/<wheel>#sha256=<hash>
    imscribe==<version> --hash=sha256:<wheel> --hash=sha256:<sdist>

The first works today for a commit that is on GitHub (pip clones and builds;
it needs network and `hatchling`). The second resolves only once somebody
publishes a release at that URL holding that file. The third is for a
directory or a mirror that holds the files. It publishes nothing, tags
nothing and reaches no network.

**`make dist` has never built anything.** The session that wrote it had
neither `build` nor `hatchling` in `./.venv` and no index to fetch them
from; run there, it stops with exit 2 and one line, before writing anything.
Both tools are now in the `dev` extra, so `make bootstrap` on a machine with
network installs them. What is tested (`tests/test_dist.py`) is the script
against a stand-in builder: the commit and not the working tree, two builds
compared and a difference said and refused, contents checked, hashes
written, the strings. **Not known, because it was not run: whether
hatchling's two builds are in fact the same bytes; what exactly its wheel
holds; whether the sdist's own tests pass when unpacked** (`demo/` and
`HANDOFF-pptmstr.md` were added to the sdist's list on this day, by
reading). The name `imscribe` is not claimed on PyPI and nothing here claims
it; that, a tag and a GitHub release are the user's.

What the wheel is meant to hold, by `pyproject.toml`: the package `imscribe`
with `imscribe/py.typed`; no `tests/`, no `demo/`, no `examples/`, no
`docs/`, no handoff files (those are in the sdist only). The demo
application is inside the package (`imscribe.ui.app`, `imscribe.ui.pages`) and
its pages say so themselves when `demo/` is not there.

### The pins to hold together

Three things are one compatible unit, and an update replaces all of them or
none (imtypeset's rule, its `docs/sidecar.md` section 11; imscribe's T7):

| what | pin | why exact |
|---|---|---|
| `imgui-bundle` | `==1.92.900` | the imtypeset library is linked against that wheel's extension module and refuses any other at import. imscribe's own metadata states this pin |
| `imtypeset` | `==0.3.0.192900` | the fourth number is the imgui-bundle line the wheel was built for (`1.92.900`). `imtypeset==0.3.0` matches nothing. **Never upgrade imtypeset alone** (`pip install -U imtypeset`): the resolver takes the newest line and replaces the application's imgui-bundle. Move the two pins together |
| `imscribe` | a commit, or a file by its sha256 (above) | a `.dev` version names no one commit |

imscribe's metadata does **not** list imtypeset (it is on no index, and the
other team's file says no licence is chosen and nothing is to be published
from `v0.3.0`); when it can be resolved from somewhere, imscribe will state
`imtypeset==0.3.*` and the application keeps the exact pin. The wheels
imtypeset has built are **stand-in builds**, version
`0.3.0.192900.dev0+standin`: a development release, which `==0.3.0.192900`
does not match and `pip install --pre` takes by name. No wheel compiled
against the wheel's own Dear ImGui headers exists. What they are called per
platform, by the other team's file: `imtypeset-<version>-cp311-none-manylinux_2_28_x86_64.whl`
on this machine; one per platform, CPython version and imgui-bundle version.

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

- **macOS, at all.** Whether the sidecar can work there is imtypeset's H1,
  which waits on a run of a workflow that has never run, which waits on the
  user's push. No build, import or window of this tree has happened on a
  Mac. The pinned imgui-bundle has macOS wheels for Apple Silicon on macOS
  14 or later only (read from PyPI's listing through a summariser).
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
- **Anything against GitHub**: the fetch of imtypeset by tag or hash, a
  `pip install` of imscribe from a git reference, the CI workflow.
- **Whether two builds of the imtypeset library are the same bytes**: they
  are not (two builds of `2fd705e` differing only in the output directory's
  name gave different files; `HANDOFF-imtypeset.md`, H45), so a library is
  identified by its own checksum and its attestation, not by its commit.

**Continuous integration** is `.github/workflows/ci.yml`: a job for
`make check` with no imtypeset anywhere, and a job that builds the pair from
the ref in `imtypeset.ref` and runs `make check TYPESET=1`, both on Ubuntu
under `xvfb-run`. **It has never run.** It was written without network;
`tests/test_ci_workflow.py` holds its text to the Makefile's targets and
variables, and the text of its fetch-and-build steps was run here against
local clones. `.github/workflows/macos.yml` is a placeholder that cannot
start by itself.

**A Mac.** Nothing in this tree has run on macOS. An audit by reading
(`docs/status.md` section 0e) found three things in the way of an install:
the other team's link line is GNU ld's and the pinned wheel has macOS builds
for Apple Silicon only; the library's import gate started a child interpreter
and wrote a stamp beside the library, which a packaged application cannot
do; and every font the text is set in is a file inside the `imgui-bundle`
wheel. By the same reading `make run` on a Mac would need `ARGS=--force`,
and every real-window test would skip there. The questions are with the
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

    make check TYPESET=1                      # the suite prints the Stress page's own per-frame figures
    make run TYPESET=1 ARGS="--tab stress"    # the same figures, live
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
  section 0g (2026-10-12, later still: P21 to P33, imtypeset `v0.3.0`, the
  version and `make dist`), then section 0f (what the first host, pptmstr,
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

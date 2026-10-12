# Status

The honest account of what this repository is, as of the last gate. Read it
before `README.md` if you are deciding whether to trust anything here.

It is written to be useful rather than flattering. Section 4 is the longest on
purpose.

## 0f. Revision of 2026-10-12, later the same day: what the first host asked for. Thirteen of pptmstr's requests built, two of them only partly; nobody has looked at any of it

The newest revision, put first. Section 0e below was the newest when it was
written and says so; it is hours older and is not changed. **Where 0e says
the facade "is still 89 names" and that `pairing` "is not on the facade",
read this section**: it is 102 and `pairing` is one of them. **Where 0e says
pptmstr's file "has six requests of advtext, P1 to P6, read on 2026-10-12
and not answered"**: it had twenty by the time the lead answered them
(commit `4b84ec8`), and it has twenty-four now; P21 to P24 are not answered.
What this section describes was in the working tree, uncommitted, when its
writer (the builder of the task PH-FINAL, an agent) wrote it; `HEAD` was
`8c05c33`; the lead commits.

**Read every paragraph below with these in mind:**

- **Nobody has looked at anything.** Every claim is a number an agent read
  off a draw list, a layout or a return value. No pixel was read by anyone.
- **Nothing was run through pptmstr's code or its tests.** Its named tests
  are on its old seam and do not import. "Met" below means a test in this
  tree asserts the same behaviour, and `HANDOFF-pptmstr.md` says for each
  how that is known.
- **Nothing here has run on macOS, on a GPU, at a display scale other than
  1, or in a frozen application**, and 0e's three (GitHub, macOS, the CI
  workflow) still stand.
- **Every default is what it was.** Each thing below is an option, a new
  call, or a refusal of something that used to become an empty block.

### What the user asked

Nothing new. The direction is the one 0e quotes: "The goal now is initial
stability and deliverability for a full pptmstr adoption and product
packaging (goal of a Mac supported install with automatic updates)."
pptmstr's session, the first real host, wrote twenty requests (P1 to P20)
in its own repository's `HANDOFF-advtext.md`; advtext's lead (an agent)
accepted thirteen to build, carried four to imtypeset, and answered three
in words. Which were built, and how, are agents' decisions:
`docs/decisions.md`, "Host requests".

### What is true of the tree now

`HANDOFF-pptmstr.md`, "Answers to pptmstr", is the full account, request by
request, with signatures. In short, and with what each does NOT do:

**The library's gate (`advtext.typesetter`; the builder of PH-GATE).**
`kind()` answers a `Kind`: READY, NOT_INSTALLED, REFUSED, FAILED,
UNSUPPORTED, UNCHECKED. READY says nothing of fonts; `ready()` does.
UNSUPPORTED is never worked out: a host says it with `unsupported(why)`,
and it is used only when nothing is found. `reset()` forgets a `disable` or
a refusal, and `ready()` is then false until `load_fonts()` is called
again. `module()` now refuses an imtypeset that lacks a name or field
advtext calls (`REQUIRED`, `missing`): 25 names of the package, 29 members
of `Document`, fields of four structures, members of seven enums, and the
leading fields of four tuples; **not** the fields of what the library
answers, keywords, enumerator values, or what a name means. `verdict()`
asks a child process and leaves the asker as it was; `python -m
advtext.typesetter` prints `pairing()` as one line of JSON and exits 0, 3,
4, 5, 6 or 7 by the kind. In a frozen application the verdict is
"unchecked" and no child is started; `sys.frozen` was set by hand for the
test and nothing was frozen. `font(face)` answers the `ImFont` the library
draws a role with.

**`load_fonts()` after start-up** (the same builder, in a real window on
Xvfb with a software renderer, imgui-bundle 1.92.900, imtypeset `c9f8902`,
called from `pre_new_frame` with a view open): it answered true each time;
the atlas held 8, 15, 22, 29 and 36 fonts after five loads and 29 before
and after an `unload()`; the open view drew 152 vertices on every frame it
drew, before and after each call. **So the atlas takes fonts after
start-up, and nothing is ever taken off it**: seven more per load, for the
life of the ImGui context. `load_fonts`'s docstring says this and what is
not promised. pptmstr's own run found the same growth and asks for a reload
that does not grow the atlas; that is not built (H25 of
`HANDOFF-imtypeset.md`).

**Reading markdown (`advtext.typeset_markdown`; the builder of PH-MD).**
`ReaderOptions`, a frozen dataclass of four `bool`s, as `reader=` to
`parse_markdown`, `describe_markdown`, `MarkdownStream` and `TypesetView`:
`html_as_text`, `images_as_text`, `keep_glob_stars`,
`show_link_destinations`. All off is the same parser objects as before.
Equal options give a parse and a stream one parser object, and a stream is
held to one parse of its text so far after every piece. Two of the four are
less than their names: with `images_as_text` alone `![alt](addr)` is `!alt`
as a link and the address stays hidden; `keep_glob_stars` is pptmstr's own
heuristic, pinned, and wrong in both directions (`rm *tmp and old* now`
loses its stars; `foo*bar*baz` is not emphasis).

**Inline code's size (`advtext.theme`; the same builder).**
`Theme.inline_code_scale` and `Theme.inline_code_step`, both zero by
default, written into `RunDescription.scale` for runs in the code role.
Measured headless on the pinned library by that builder: a run's scale is a
multiple of the size of the block the run is in, a heading included (a code
`m` advances 8.0 px at scale 1 and 10.0 at 1.25 in a 16 px paragraph;
15.625 and 19.531 in a 31.25 px heading), where the library's header says
"the paragraph's".

**The views (`advtext.ui.typeset_view`, `typeset_stream_view`,
`advtext.description`; the builder of PH-VIEW).**

- *Blocks a host made.* `TypesetView` and `set_document` take a sequence of
  `MarkdownText` / `MarkdownCode` / `MarkdownRule` / `MarkdownTable`, or a
  `Description` (`description_of`, `check_description`). An object that is
  no block is a `TypeError` at the call, through every way into a view.
  **`MarkdownConverter.describe` called directly still stands an empty Host
  block in for an object it does not know** and counts it in `misfits`; two
  existing tests assert that.
- *Code overflow.* `code_overflow="wrap"` (default), `"clip"`, `"grow"`,
  with `content_width`. Measured headless at a 444 px pane with a
  400-character code line: under grow `content_width` is 3215.995 and the
  library's own `size().x` is still 444.0, so the view asks each code
  block's geometry once: 128 ms against 12 ms for the first frame of 500
  code blocks of 20 lines (once, load 11.9). Under clip nothing can say a
  line was cut. Grow or clip with columns: not measured.
- *One pitch.* `fixed_line_height=True`: paragraphs, headings, list items
  and code; not tables, hosted blocks, or a block holding a display
  formula. Measured: a code block of six lines has heights 22.4, 22.4, 20,
  20, 22.4, 20 without it and 20 x 6 with it. Box-drawing and block glyphs
  make a code line taller; **an accented capital does not**, at this pin
  and the stock sizes. **Not built**: a view of many blocks capped in
  pixels ending on a whole line (pptmstr's case); a host reads
  `set_lines()`.
- *Tables at natural widths.* `table_widths="natural"`. Equal to a keeping
  stream's columns to 0.001 px for pptmstr's table; **not in general**: a
  stream whose cell was wider while it was written (`**bold wor`) ended
  4.93 and 2.43 px wider than the same table given whole. The host closes
  it by stating the stream's widths with `set_table_columns` (tested to
  0.001 px).

**The diff view (`advtext.ui.typeset_diff_view`; the builder of PH-DIFF).**
`TypesetDiffView.headers(width_px=None)` answers a `DiffHeader` a file:
`text`, `warning`, the widths, `fits`, `text_fits`. Widths are the
library's, measured once per text and size (59 us for one file, 1.65 ms for
100, headless, load 6.1). `fits` has no margin, where pptmstr's seam
counted a spare cell; asked for a width before a draw it does not allow for
a capped view's scrollbar.

**The facade is 102 names; it was 89** (this section's writer). Thirteen
added, none removed, no module added as a home: `Kind`, `kind`, `reset`,
`pairing`, `verdict` (beside `load_fonts`, `ready`, `reason`);
`ReaderOptions`; `MarkdownText`, `MarkdownCode`, `MarkdownRule`,
`MarkdownTable`, and `MarkdownCell` and `ColumnAlign`, without which a
`MarkdownTable` cannot be constructed; `DiffHeader`. 65 of the typeset
layer, 8 for font files, 29 of the reference core. Left to their modules,
with no promise: `advtext.typesetter.font`, `unsupported`, `missing`,
`REQUIRED`, `EXIT_CODES`; `advtext.description.description_of`,
`check_description`, `check_runs`; `advtext.typeset_markdown.reader_options`.
`tests/test_facade.py` holds the list, and one new test builds each block
type and asks the kind from the package root in a fresh interpreter, with
no ImGui, fontTools or imtypeset loaded at the end of it.

**Nine requests and a note went to the other team**, H25 to H33, in
`HANDOFF-imtypeset.md`, each in its builder's sentence.

### What was measured, by whom, at what load

All on the one 16-core machine, by agents. No window was looked at. The
figures above are each from the result file of the builder named
(`.concerns/PH-GATE--builder--result.md`, `PH-MD`, `PH-VIEW`, `PH-DIFF`;
not version-controlled), measured while four builders shared the machine
(load 5.8 to 15).

- **The gate, on the tree as it stands, nothing else writing or testing in
  it** (this section's writer, PH-FINAL's builder, an agent, 2026-10-12,
  against the pinned pair from `c9f8902`). `make check`:
  **3318 passed, 302 skipped, 4 xfailed** in 159 s, load 1.81 at the start
  and 1.60 at the end. `make check TYPESET=1`, straight after: **3612
  passed, 8 skipped, 4 xfailed** in 257 s, load 1.55 and 7.09. Ruff and
  black clean (122 files), mypy clean over 51 files, both times. 3,624
  tests each way (3,223 in section 0e); no failure and no error. Each gate
  once. Nothing else was writing or testing in this tree; other sessions
  share the machine, and where the load at the end of the second run came
  from was not looked into. These counts were written into this paragraph
  after the runs; `tests/test_docs.py`, `tests/test_ci_workflow.py` and
  `tests/test_facade.py` were run again afterwards and passed.
- **The builders' own gates were on a moving tree and none was one green
  command from start to end**, except PH-VIEW's: its `make check` (3304
  passed, 302 skipped, 4 xfailed, load 12.3 to 14.2) started before its
  last two small edits, and its `make check TYPESET=1` (3598 passed, 8
  skipped, 4 xfailed, load 13.0 to 6.9) was on its final tree. The other
  three ran the stages apart because lint stopped on another builder's
  half-written file.
- **One test was red once for two builders in that moving tree**:
  `tests/test_typeset_markdown.py::test_the_resume_helpers_copied_from_markdown_have_not_drifted`.
  Run alone by this section's writer on the quiet tree before the gates: it
  passed (0.19 s); and it passed in both gates. It compares the source of
  five helpers in two modules; nothing was changed to make it pass, and
  why it was red then was not established (both builders who saw it
  supposed a file caught half-written).
- **A native line in a typeset face** (PH-GATE's builder, a real window,
  software renderer, three rows): the code face at em 16 sets 13 characters
  104 x 14 px of ink; pushed at 16 ImGui draws them 103 x 11; pushed at
  16.78, made 17, 104 x 14. The prose face at em 16: 116 x 15 typeset, 103
  x 13 pushed at 16, 116 x 15 pushed at 18.75, made 19. The code face at em
  21: 136 x 17 typeset (laid out 136.5), 142 x 17 pushed at 22.
- **Forty characters of the code face are half an em each** (the same
  builder, headless): 280, 300, 320, 340, 360 and 400 px at ems of 14, 15,
  16, 17, 18 and 20. So 8.0 px a character at an em of 16, and 7.63 at an
  em of 15.25, which is what a 16 px line height of that file is.
- **Settled equals streamed under reader options** (PH-MD's builder): in
  the suite after every piece; outside it, 6000 generated sources, about
  1.36 million pieces, 0 failures (137 s and 155 s, load 8).
- **The command line** (PH-GATE's builder, five runs each): 91 to 151 ms
  with nothing to find, 286 to 319 ms with the pinned pair.

### What nobody has looked at, or run

- Everything in 0e's and 0d's lists of the same name, still.
- Any of the above on a screen: code scrolled sideways, one pitch through
  `tree` output, a table at its natural widths, a shown link destination,
  inline code at another size, a diff header that did not fit.
- pptmstr's tests, or any of this from pptmstr's code.
- A frozen application; macOS; a GPU; a display scale of 2.
- `fixed_line_height` or `code_overflow` together with columns.
- The field check of host-made blocks against anything a real host made:
  it is held against this tree's own converter on every demo document.

### Open

- **pptmstr's P21 to P24**, written after the lead's answer and not
  answered: monospace columns and alignment with ImGui's text at the same
  pixel height (P21), a glyph drawn where it was laid out (P22), one word
  space under `Spacing.FRENCH` (P23), and `ready()` after the ImGui context
  is gone without `unload()` (P24). Its measurements for P21 to P23 size
  text with `Theme.at_pixel_height`, a line height; the half-em figures
  above are at an em.
- **A reload that does not grow the atlas** (P17, H25).
- **A capped view of many blocks ending on a whole line** (P13).
- **A stream's table against the settled one when a cell was wider while
  written** (P19, H31, H32).
- **The content's width under clip, and a cheap one under grow** (P12, H29,
  H30).
- **`MarkdownConverter.describe` and an object it does not know**: still an
  empty Host block when called directly.
- **`advtext/ui/app.py` has its own `_library_font`**, which
  `typesetter.font` now duplicates; not changed.
- **Whether refusing the whole library for one missing name is what a host
  wants**, when the name is used by one gallery page (PH-GATE's builder's
  question).
- **`description_of` and `check_description` are not facade names** (this
  section's writer's decision: a host that describes its own blocks imports
  `advtext.description` for the tuples and enumerators anyway, and no host
  has asked). One line to reverse.
- With HTML read as HTML (the default), a paragraph followed by an unclosed
  `<!--` stays live in a stream until the comment closes, and is re-read at
  every piece (PH-MD's builder; as it was before this work; pinned).
- **From a review of this revision's code** (2026-10-12, task PH-R, by
  reading; what it found wrong and was reproduced is fixed by PH-FIX and
  said in `HANDOFF-pptmstr.md`, P2, P3, P8 and P19). Recorded and not
  fixed:
  - `show_link_destinations`: the text compared with the destination is
    built from `text` and `code_inline` tokens only, so a link text broken
    across a line is shown without its destination; the destination is
    written into the block's text, so copy, `texts` and find hold
    characters the source does not (`selected_source()` does not); a
    settled view reads a `str` with `references=True` by default and a
    stream with `references=False`.
  - "A `Description` is used as it is given" is not quite true:
    `fixed_line_height` and `table_widths="natural"` lay flags over the
    host's blocks (and since PH-FIX a surrogate is U+FFFD and a list a
    tuple).
  - In a frozen application `verdict()` starts nothing, but `kind()`,
    `module()` and every view constructor still run the library's own gate.
  - A table row with more cells than columns, a `KIND_TABLE` block with no
    rows, and rows of unequal length pass the checks. One run each on the
    pinned library (PH-FIX's builder): each drew or drew nothing, none
    raised; the widths were not measured and no test holds it.
  - `math.isfinite` on a host's number raises `OverflowError` for an
    integer too large for a float (`set_columns`, `column_pos`,
    `TypesetDiffView.headers(width_px=...)`).
  - After a call into the library raises something that is not the
    library's, the view has NO document and its record is the new one (not
    "the view as it was"): the next draw makes the document again or raises
    the same error. The reviewer's "build then swap" is done for a new
    document; for an edit, restoring every field of the record was judged
    more likely to be wrong than closing the document
    (PH-FIX's builder's decision).

## 0e. Revision of 2026-10-12: Level 1. The pairing with imtypeset is pinned, found three ways, and buildable from GitHub; none of it has run there

The newest revision, put first. Section 0d below was the newest when it was
written and says so; it is one day older and is not changed. **Where 0d says
"nothing on it is committed" and "`HEAD` is still 30496e1", that was true
then**: the branch has five commits on `main` now and `HEAD` was `f34f6c8`
when this was written. **Where 0d says `make typeset-lib` "needs
`../imtypeset`" and names `7a7bc36`, read this section instead.** What this
section describes was in the working tree, uncommitted, when its writer (the
builder of the task L1-GATE, an agent) wrote it; the lead commits.

**Three things have not happened, and every paragraph below should be read
with them in mind:**

- **Nothing here has run against GitHub.** The sandbox these sessions ran in
  reaches neither `github.com` nor a package index. Every fetch below was run
  against a `file://` clone of a sibling checkout on this machine.
- **Nothing here has run on macOS.** The Mac audit below is from reading.
- **The CI workflow has never run.** GitHub has never loaded the file.

And, as in 0d: no person has looked at any page in a window because of this
work, and nothing below changes a pixel.

### What the user asked

The user's words are in `HANDOFF-imtypeset.md`, "Direction", quoted there in
full. The two that set this work: "Let's target Level 1", and "The goal now
is initial stability and deliverability for a full pptmstr adoption and
product packaging (goal of a Mac supported install with automatic updates)."
And on builds: "each project should know that the other is now hosted
publicly on github so any build systems that need referential access should
lean on that." "Level 1" is the lead's phrase, which the user took as the
target: keep imtypeset as a library loaded beside an unmodified
`imgui-bundle` wheel, and make that reliable. Everything else in this
section is an agent's decision or an agent's measurement, and
`docs/decisions.md`, "Level 1", marks each decision as one.

### What is true of the tree now

**`imgui-bundle` is pinned exactly: `imgui-bundle==1.92.900` in
`pyproject.toml`.** It was the floor `>=1.92.900`. 1.92.900 is the version
installed for every run this branch records. Why exact: the
library is linked against one wheel's extension module and its import gate
refuses any other, so a range promised versions the library was never built
for, and the failure would arrive as a page that draws one line, not at
install. An upgrade is three acts: the pin, `make typeset-lib` against the
new wheel, `make check TYPESET=1`.
`tests/test_makefile_env.py` holds the pin to `==` one version and the
installed wheel to that version. **`pip install` with the pin has not been
run by anyone**; what pip does on a machine holding another `imgui-bundle` is
in L1-PKG's result file as reasoning, not as a run. Whether a 1.92.900 wheel
exists for a given Mac and Python is part of the audit below.

**The imtypeset commit in use is `c9f8902`**, in full
`c9f8902a67adf00a18426876d5983617b7d1408c`, the one line of `imtypeset.ref`
at the root. `build/imtypeset-bundle/BUILT-FROM` says that commit (built
2026-10-11T13:01:08Z by `make typeset-lib IMTYPESET_COMMIT=c9f8902`, 0
uncommitted paths). imtypeset has no tags, so the ref is a hash; it must be
reachable from a branch on GitHub to be fetched, and that has been checked
only against what the sibling checkout last saw of its remote (L1-PKG's and
L1-CI's builders: an ancestor of `origin/main` there).

**The library is found by one of three routes, in this order**
(`advtext.typesetter.module()`, L1-PKG's builder):

1. `IMTYPESET_LIBRARY` set (with `IMTYPESET_PYTHON`): exactly as before. It
   is what `make ... TYPESET=1` sets, and the only route any page, example or
   gate has drawn through.
2. Otherwise an installed `imtypeset` distribution, when
   `importlib.metadata.distribution("imtypeset")` finds one: `import
   imtypeset` with no variable set. **There is no such distribution** (it is
   request H3 of `HANDOFF-imtypeset.md`). The route is tested with two
   stand-ins built in a temporary directory: a two-function package with a
   `dist-info`, and the pinned pair wrapped as a distribution, which went the
   whole way with neither variable set (import gate, `load_fonts()` True,
   `ready()` True; the builder's run).
3. Otherwise not loaded. `reason()` is `IMTYPESET_LIBRARY is not set`, to the
   character, as before.

`typesetter.pairing()` answers which route was taken and with what: a `dict`
with the keys `route` (`"environment"`, `"distribution"`, `"none"`),
`reason`, `library`, `package`, `distribution`, `imtypeset_version`,
`imgui_version`, `wheel_version`, `built_for`, `headers`, `accepted_by`. Run
by this section's writer against the pinned pair: `route` `environment`,
`imtypeset_version` `0.2.0`, `imgui_version` `1.92.9`, `wheel_version`
`1.92.900`, `headers` `stand-in:ocornut-v1.92.9-docking`, `accepted_by`
`probe`, `built_for` `None`; and with no variable set, `route` `none` and
every other key `None` but the reason. **`reason()` does not name the
route**, though the lead's decision asked for it there; `pairing()["route"]`
does. `pairing` is `advtext.typesetter.pairing` and is not on the facade,
which is still 89 names.

**To build the library:**

    make typeset-lib IMTYPESET_COMMIT=c9f8902   # that commit of the sibling ../imtypeset
    make typeset-lib                            # the sibling's working tree
    make typeset-lib IMTYPESET_REF=c9f8902a67adf00a18426876d5983617b7d1408c   # fetched from IMTYPESET_REPO

The first two are unchanged. The third is new: `IMTYPESET_REF` is a tag, a
branch or a full 40-character hash; one commit is fetched with `git fetch
--depth 1` from `IMTYPESET_REPO` (default
`https://github.com/WalterCReel3/imtypeset.git`) into a bare cache under
`build/`, and the build from there is `IMTYPESET_COMMIT`'s. No network, an
unknown ref, an abbreviated hash, or both variables given stop at the
recipe's first step with exit 2 and one line. **`IMTYPESET_REF` has no
default, and the Makefile does not read `imtypeset.ref`**: a plain `make
typeset-lib` builds the sibling's working tree as it always did. The lead's
decision 4 said the default source "becomes the GitHub URL at a named ref";
what was built is a default repository and no default ref
(`docs/decisions.md` says why it was left so). All three forms still need
the two neighbours the other team's build script reads, as clones on this
machine: `pthom/imgui_bundle` holding the tag `v1.92.900`, and for stand-in
headers `ocornut/imgui` holding `v1.92.9-docking`. Nothing in the Makefile
fetches those; the CI workflow fetches both itself.

**There is a CI workflow, and it has never run.**
`.github/workflows/ci.yml` (L1-CI's builder) has two jobs on `ubuntu-24.04`
with Python 3.11, each under `xvfb-run` with a software rasteriser: `plain`
fails if imtypeset is anywhere on the runner and then runs `make check`;
`typeset` reads the ref from `imtypeset.ref`, fetches the two neighbours'
tags, runs `make typeset-lib IMTYPESET_REF=...`, photographs one page as a
check that the library draws, and runs `make check TYPESET=1`.
`.github/workflows/macos.yml` is a placeholder that cannot start by itself.
`tests/test_ci_workflow.py` (40 tests) holds the files to the Makefile's
targets and variables, with a YAML reader of its own for a stated subset:
the virtualenv has no YAML parser. Its builder's list of 25 things not run,
each with the symptom that would show it wrong, is in
`.concerns/L1-CI--builder--result.md` (not version-controlled); its own
ranking of the likeliest first red is newer lint tools than the ones here
(the dev tools are floors, not pins), then the user-namespace Xvfb on a 24.04
runner, then the apt package list.

**The gallery pages' size control** (T6-SIZE, the commit `98d6526`) is in
section 0d's "What nobody has looked at" and in `docs/decisions.md`, "The
swap", last row: Specimen, Formula and Math in text have a combo of 14, 16,
19, 23 and 28 px and open at 23. Nothing about it changed here.

### What was measured, by whom, at what load

All on the one 16-core machine, by agents. No window was looked at.

- **The gate, on the tree as it stands, nothing else running** (this
  section's writer, L1-GATE's builder, an agent, 2026-10-12, against the
  pinned pair from `c9f8902`). `make check`:
  **2955 passed, 264 skipped, 4 xfailed** in 150 s, load 3.36 at the start
  and 4.40 at the end. `make check TYPESET=1`, straight after: **3211
  passed, 8 skipped, 4 xfailed** in 236 s, load 4.53 and 4.49. Ruff and
  black clean, mypy clean over 51 files, both times. 3,223 tests each way
  (3,141 in section 0d; of the 82 more, 66 are this work's and 16
  T6-SIZE's); no failure and no error. Each gate once. The load was not
  this tree's: nothing else was writing or testing in it, and other
  sessions share the machine. These counts were written into this paragraph
  after the runs; `tests/test_docs.py` was run again afterwards and passed.
- **The gate while the tree was in motion** (L1-PKG's builder, each once):
  `make check` 2955 passed, 264 skipped, 4 xfailed, load 14.1 at the start
  and 8.3 at the end; `make check TYPESET=1` 3211 passed, 8 skipped, 4
  xfailed, load 8.3 and 5.3. L1-CI's test file was being written under those
  runs.
- **`make typeset-lib IMTYPESET_REF=<the full hash>` from a `file://` clone
  of the sibling**, into a scratch bundle (L1-PKG's builder, load 2.7): exit
  0, 24 probes, 45 s; `diff -rq` of its `src` against the pinned bundle's
  prints nothing. With `IMTYPESET_REF=v9.9.9`, with the abbreviated
  `c9f8902`, and against the default GitHub URL (the real no-network case,
  `CONNECT tunnel failed, response 403`): exit 2 each, the one line, nothing
  created.
- **The workflow's own step texts, run here** (L1-CI's builder, load 3.1 to
  4.6): "What the pair is", "Fetch what the build script reads" and "make
  typeset-lib", through `bash -e -o pipefail -c`, with `file://` URLs of the
  three siblings: exit 0, each neighbour one shallow commit with no worktree,
  the pair gated by the probe. Then `make check TYPESET=1` against that pair
  with `PYTEST_ADDOPTS=-rs`: 3199 passed, 8 skipped, 4 xfailed in 332 s (load
  13.5 at the end, tree in motion); the 8 skips are one `ADVTEXT_SLOW` and
  seven "DiffView is gone", no window test among them. **`xvfb-run` itself
  did not start in the sandbox**, so nothing ran under it.
- **The same commit built twice is not the same bytes** (L1-CI's builder,
  measured and not investigated): the scratch library's cksum is `3759793072
  14151720`, the pinned one's `862594398 14151760`. Paths are embedded with
  `-g`.
- **Mutation tests** (L1-PKG's builder, on copies): 12 mutants of the
  Makefile's new recipe, 10 killed; 9 of `typesetter.py`, 9 killed after one
  test was added for the survivor. The two Makefile survivors are named in
  its result file with why each was left.

### The Mac audit, in summary. From reading; nothing was run and there was no Mac

By advtext's reviewer (the task L1-MAC, an agent with no shell), written down
by the lead in `.concerns/L1-MAC--reviewer--result.md` (not
version-controlled). **Every statement about Apple's linker, dyld, freezers
and code signing is inference from general knowledge.** One fact came from
outside the tree: PyPI's listing for `imgui-bundle` 1.92.900, read through a
fetch tool's summariser and not as raw data.

Blockers for a Mac install, in the reviewer's order:

1. **The library cannot be built on macOS as written, and the pinned wheel is
   Apple Silicon only.** The other team's link line (`-shared`, the wheel's
   module as an input, `-Wl,--no-undefined`, `-Wl,--version-script=`) is GNU
   ld's. advtext's Makefile names `libimtypeset_bundle.so` throughout;
   `advtext/typesetter.py` hard-codes no suffix and reads nothing
   Linux-specific. From PyPI: the only macOS wheels of 1.92.900 are
   `macosx_14_0_arm64` for CPython 3.11 to 3.14, so with an exact pin "Mac
   supported" means Apple Silicon on macOS 14 or later. Requests H1, H16, H17.
2. **The import gate cannot work in a packaged application, on any
   platform.** imtypeset's gate runs a child through `sys.executable` when
   its stamp is absent or stale, keys the verdict on absolute path, size and
   modification time, and writes the stamp beside the library. Inferred: in a
   frozen application `sys.executable` is the application; a signed bundle
   cannot be written into; every update is a new path. advtext would turn the
   refusal into `reason()`: nothing crashes and nothing draws. **advtext's
   suite cannot meet this**: the stand-in distribution it tests route 2 with
   has no gate. Request H15.
3. **Every font the text is set in is a file inside the `imgui-bundle`
   wheel** (`imgui_bundle/assets/fonts`: four Roboto faces, Inconsolata
   Medium, Latin Modern Math), unless a host registers its own per role.
   advtext ships no font; the gate's probe needs one there too. A freezer
   that takes the compiled module without `assets/` would be refused at
   import. Request H20.

Blocking only the test suite on a Mac: every real-window test skips there
(the `window` fixture knows a reachable `DISPLAY`, Xvfb, or `unshare -rm`),
so a macOS `make check` can be green having opened no window, and `make run`
needs `ARGS=--force`.

To verify at a Mac, not blockers: the copy shortcut reads `io.key_ctrl` and
the pages say "Ctrl+C"; 96 px per inch is assumed in five places and the app
never asks the runner for a scale; the library adds its faces at
`RasterizerDensity` 1.0, so what a retina screen shows is unknown (H19);
`DEMO_DIR` points outside the package in an installed wheel, and `pip
install advtext` installs the package and `py.typed` only.

### What nobody has looked at, or run

- Everything in 0d's list of the same name, still.
- `git fetch` of imtypeset from GitHub by tag, by branch, or by full hash;
  and whether `c9f8902` is on GitHub at all.
- The workflow, on a runner. Its expressions, its action versions, the apt
  package names on Ubuntu 24.04, a restored cache (the pair holds absolute
  paths), `xvfb-run`.
- Route 2 against a real distribution of imtypeset.
- `pip install -e .[dev]` with the exact pin.
- macOS: anything.
- An sdist. `pyproject.toml`'s sdist list gained `imtypeset.ref`, `.github`
  and `HANDOFF-imtypeset.md` (this section's writer; `tests/test_ci_workflow.py`
  reads all three), and nothing was built: the virtualenv has no `hatchling`.
  The list still has no `demo/`, which sixteen test files name, so the suite
  is not expected to pass from an unpacked sdist (from reading).

### Open

- **The freezer and the metadata rule.** Route 2 knows a distribution by its
  `dist-info`, and the common freezers drop that unless told to keep it. In
  such an application the page would say `IMTYPESET_LIBRARY is not set` and
  point its reader at the wrong thing. Either the product sets the variable,
  or the rule widens once the other team says how its distribution finds its
  library. **L1-PKG's builder's least sure decision.**
- **With the variable set AND a distribution installed, the installed
  package is imported and handed the variable's library** (`IMTYPESET_PYTHON`
  goes at the end of `sys.path`, as before). A test pins it;
  `pairing()["package"]` shows it.
- **`built_for` is `None` for every library `make typeset-lib` builds**: the
  library does not record the wheel it was linked against. Request H21.
- `pairing` is not on the facade. Nobody decided it should or should not be;
  the facade's file was outside the builder's task.
- The Makefile's default ref (above). The other team has named no tag (H4).
- The CI workflow builds with stand-in headers, as every build here has (H2).
- pptmstr's handoff file has six requests of advtext, P1 to P6, read on
  2026-10-12 and not answered. `HANDOFF-pptmstr.md` says so.
- Stale and left, because the documents are dated records: `docs/imgui-risks.md`
  has a dated note beside the sentence about the dependency floor and is
  otherwise as it was; 0d and 0c below name `7a7bc36` and the sibling as the
  only source.

## 0d. Revision of 2026-10-11: the swap. advtext draws through imtypeset and through nothing else

The newest revision, put first. Section 0c below was the newest when it was
written and says so; it is one day older and is not changed, and neither are
sections 0, 0b and 1 to 6. **Those sections describe `main`.** Wherever they
say `BareView`, `StreamView`, `DocumentView`, `DiffView`, the ImGui draw
backend, `advtext.columns`, `advtext.mathtext`, the Blocks page or one of the
bench and verify scripts, they describe something that is deleted on this
branch. It is all still in `main` (30496e1) and in the local tag
`advtext-reference`.

**This is the branch `experimental/imtypeset-adoption`, and nothing on it is
committed.** The work is staged in the git index as a checkpoint and the last
task's changes sit unstaged on top of it; `HEAD` is still 30496e1.

**No person has looked at any page of this demo in a window since the swap
began. Not one.** Every page, every example and every photograph was produced
and counted by agents; reviews were by reading (the reviewers had no shell
and ran nothing). The tests say that vertices reach a draw list, that texts
are equal, that a count is what it was. None says anything looks right.

### What the user asked

The user's words are quoted in full in `docs/decisions.md`, "The swap
(2026-10-10 and 11)". The one that set the direction: "The intent is see
adv-text with a full swap out using as much as it can from imtypeset." And,
when tables and columns came up: "Isn't tables and columns straight from TeX?
Shouldn't that be part of imtypeset?" Everything else in this section is an
agent's reading of those sentences or an agent's decision, and
`docs/decisions.md` marks each as one.

### What is true of the tree now

**advtext needs the imtypeset library to draw.** There is no second renderer.
With the library loaded, every page of the demo and all four examples set and
draw their text through `TypesetView`, `TypesetStreamView` or
`TypesetDiffView`, or (Specimen, Formula, Math) show a section of imtypeset's
own demo. Without it each page draws ONE wrapped line, "imtypeset is not
drawing: " and the reason, and each example says why on standard error and
exits 1. `make check` is green without the library and proves less: the
tests that need it skip.

**To build the library, pinned to a commit, and use it:**

    make typeset-lib IMTYPESET_COMMIT=7a7bc36   # once; needs ../imtypeset and ../imgui_bundle
    make check TYPESET=1                        # the gate that means something
    make run TYPESET=1                          # the demo with its text
    make shot-all TYPESET=1                     # 25 PNGs of 14 pages

`7a7bc36` is the commit in use: `build/imtypeset-bundle/BUILT-FROM` says so
(built 2026-10-11T10:28:22Z by that command, 0 uncommitted paths), and the
library and the Python package beside it (`pysnap/`) come from that one
commit; `make ... TYPESET=1` refuses a pair that does not match. The other
team names the commit to build from in
`../imtypeset/docs/advtext-swap-status.md`, "Build from". **That file now
names a later one, `c9f8902`** (it lists `7a7bc36` as the one before, and
one memory error fixed since). Everything measured in this section was
measured against `7a7bc36`. **After the last task finished, the lead rebuilt
the pair from `c9f8902`** (`make typeset-lib IMTYPESET_COMMIT=c9f8902`;
`BUILT-FROM` now says that commit) **and ran both gates once on the quiet
tree**: `make check` 2875 passed, 262 skipped, 4 xfailed (load 1.4);
`make check TYPESET=1` 3129 passed, 8 skipped, 4 xfailed (load 4.1). The same
counts as at `7a7bc36`; no figure above was re-measured on it.

Since this revision a library that was ASKED FOR and is not drawing is no
longer silent: `scripts/shot.py` exits 3 and writes no PNG, and
`scripts/run_demo.py` says why when the window closes. Without the variable
both behave as before (a deliberate one-line window, said on stderr).

### What was deleted

Counted against `HEAD` by this section's writer (`git diff HEAD
--diff-filter=D --numstat`): **46 files, 48,788 lines.** By the builder who
deleted most of them (T5-B1, its own tally against the index): 44 files and
47,144 lines, plus 545 lines of `advtext/typesetter.py`. The other two files
went a task earlier (the Blocks page and one test file).

| what | files | lines (T5-B1's tally) |
|---|---|---|
| the old views | `advtext/ui/bare_view.py` (2433), `stream_view.py` (599), `document_view.py` (600), `diff_view.py` (2659), `ui/units.py` (2489) | 8,780 |
| the old ImGui draw backend | `advtext/backends/imgui_draw.py` | 1,004 |
| old-core modules nothing else imports | `advtext/columns.py` (542), `blocklayout.py` (469), `spans.py` (1386), `stream.py` (1673), `mathtext.py` (1587) | 5,657 |
| the galleries, which are imtypeset's now | `advtext/ui/specimen.py` (891), `ui/formulas.py` (1230) | 2,121 |
| the Blocks page | `advtext/ui/pages/blocks.py` | 416 (this writer's count) |
| the old backend's instruments | `scripts/bench_draw.py`, `bench_reflow.py`, `verify_advances.py`, `verify_ascent.py`, `font_grid.py`, `pen_rules.py`, `render_grid_compare.py`, `_page_compare.py` | 4,009 |
| examples of the old pipeline | `examples/minimal.py`, `examples/theme_gallery.py` | 858 |
| tests whose subject is gone | 21 files (T5-B1), 2,626 tests | 24,715 |

Also gone inside files that stay: `typesetter.Converter` (the walk from node
material to a description) and the views' blocks-in path. The tests fell from
5,753 to 3,105 (T5-B1), and stand at 3,141 after the two tasks since.

**What the deleted tests compared against was frozen first.** Before the
first deletion T5-B1 wrote the old core's answers to
`tests/data/material_descriptions.json` (2,091 cases), `stream_corpora.json`
and `material_tables.json`, and read all 2,092 back equal against the live
old core. The typeset tests that said "new equals old" now say "new equals
frozen", and a case that was not frozen raises; it does not pass.

### What remains of the old core, and exactly why

Two things, each with a named reason and each waiting on somebody.

**1. The SVG litmus chain, and the 22 modules it imports. Waiting on the
user.** `make svg`, `scripts/render_litmus.py`, `advtext/backends/svg.py`,
`tests/test_litmus.py` and `tests/test_svg.py` were not touched. The user has
been asked whether the SVG renderer leaves advtext and has not answered, so
an agent (the lead) decided to keep it and everything it needs. The closure
was measured before anything was deleted (T5-B1, by `ast` and by running the
chain) and is held by a test (`tests/test_typeset_closure.py`):

    advtext  advtext.backends  advtext.backends.svg  advtext.badness
    advtext.fontlib  advtext.fontmetrics  advtext.linebreak  advtext.markdown
    advtext.markdown_rules  advtext.math  advtext.math.atoms  advtext.math.mlist
    advtext.nodes  advtext.pack  advtext.primitives  advtext.selection
    advtext.shipout  advtext.style  advtext.theme  advtext.ui
    advtext.ui.composition  advtext.units

Five of those are shared with the typeset layer and are not old core
(`advtext`, `advtext.ui`, `advtext.markdown_rules`, `advtext.theme`,
`advtext.primitives`); the other 17 are the "reference core". Their own unit
tests stay with them. The chain's five artifacts are byte for byte what they
were before the theme was changed under it (T5-B2, sha256 of each).

**2. The font reader, for metrics and for font files. Waiting on the other
team.** imtypeset cannot yet answer a face's ascent, x-height or advance, and
advtext still knows where the font files are. So four calls reach
`advtext.fontlib` when they are CALLED (never at import):
`typesetter.load_fonts()` (the files it hands the library),
`Theme.at_pixel_height()` and `pages.face_metrics()` (an em size from a
pixel height), and `typeset_diff_view.code_size(theme, pixel_height=...)`.
The request is item 5 of `.concerns/lead--for-imtypeset-team.md`.
`advtext/ui/fonts.py` also stays, outside both lists: the app loads ONE UI
font through it when the library is not drawing, so that the one line can
be read.

**Apart from those calls the typeset layer imports none of the reference
core**: at import and after `Theme.build()`, for `advtext`, the eight
typeset modules, the eight `advtext.ui` modules, the pages package and its
15 modules and the four examples, in both import forms, the set is empty
(T5-B2, 37 rows, each a fresh interpreter; the test holds it). To get there
`advtext/primitives.py` became the core-free home of the unit conversions
and the `Face` enum, and `BlockStyle` carries its leading as a number.

### The facade, before and after

`advtext.__all__` was 94 names and is **89** (T5-B2; `tests/test_facade.py`
holds the list). The rule: a name is there if and only if the module that
defines it is in the tree; a deleted thing is removed, not aliased.

- **Gone by name, 21:** `StreamDocument`, `CommitPolicy`, `live_theme`;
  `markdown_math`, `typeset`, `Typeset`, `Refusal`, `RefusalKind`,
  `supported_commands`; `draw`; `BareView`; `StreamView`; `LayoutStats`;
  `DiffView`, `DiffFences`; `ColourSpan`, `code_position`, `colour_text`,
  `find_spans`, `material_text`, `TextMatch`. `hasattr(advtext, "BareView")`
  is False.
- **The same name, now another object, 8:** `HostFor`, `SetLine`, `Hosted`,
  `DiffLayout`, `SyntaxColour`, `language_for`, `HostedDiff`, `FindIndex`
  are the typeset layer's. Their signatures differ from the old ones. A host
  that imported one expecting the old class gets no error at import.
- **New, 16:** `TypesetView`, `TypesetUnavailable`, `TypesetStreamView`,
  `TypesetDiffView`, `TypesetDiffFences`, `MarkdownStream`, `parse_markdown`,
  `MarkdownDocument`, `MarkdownConverter`, `Description`, `BlockDescription`,
  `Finder`, `Match`, `load_fonts`, `ready`, `reason`.
- **Kept, in three groups the file keeps apart:** the typeset layer (52),
  font files (8), and "the reference core, kept for the litmus renderer"
  (29), which are there because their modules are and for no other reason.

### What was measured, by whom, at what load

All on one 16-core machine. Every window was an Xvfb with a software
rasteriser. **Read the ratios; no test asserts a time.** The comparisons
against the old views were made while both existed and cannot be made again
on this branch: the old side is deleted.

- **The gate, on the tree as it stands, nothing else running** (T5-FINAL's
  builder, an agent, 2026-10-11). `make check`: **2875 passed, 262 skipped, 4 xfailed**, load
  0.43 at the start and 1.97 at the end. `make check TYPESET=1`, straight after:
  **3129 passed, 8 skipped, 4 xfailed**, load 1.97 and 4.47. Ruff and black clean, mypy
  clean over 51 files, both times. The windowed with-library files alone a
  second time, 23 files, twice: 908 passed and 7 skipped both times (load 4.5 to
  6.0, then 4.4 to 6.7). 3,141 tests each way; no failure and no error in any
  run. These counts were written into this paragraph
  after the runs; `tests/test_docs.py` was run again afterwards and passed.
- **A frame while text arrives, the pages' own Python and the library's
  calls** (T4-PAGES-B's builder, one round, load 11.4 to 13.6): Stream, both
  panes, 23.2 ms through the old views and 2.22 ms through imtypeset, ratio
  0.096; Chat's three replies 0.12 to 0.15; Stress streaming at 1, 4 and 16
  panes 0.058 to 0.13; Stress finished 0.022 to 0.045. An earlier pair at
  load 7 to 8 gave 0.085 for Stream: "the ratios hold, the milliseconds do
  not" (the builder's words). The frame counts of the two columns differ.
- **The diff view** (T4-DIFF's builder, three runs, load 11.2 to 13.0), old
  over new: a steady frame 8.9 to 21.6, scrolling 8.9 to 14.8; a FIRST frame
  1.1 to 4.8, and 1.4 to 1.9 for a whole 4,062-row file. One sample a run
  for the first frame.
- **Markdown source to a constructed view**, `sample.md` ten times over
  (T3-B's builder, median of 5): 33 ms against 181 ms at load 8, 85 against
  461 at load 12; ratio 5.4 to 5.5.
- **Columns, the library's cut against the old `advtext.columns`**
  (T5-COLUMNS's builder, load 2.0 to 3.2): the same number of columns in all
  eight cases tried; every column starting at the same letter in one case
  (the page's own geometry) and from 1 to 7 of them in the others. In six of
  the seven that differ the library's first different column starts at a
  block's start, which the other team's document says it may. **One is not
  explained.**
- **Tables, the library's widths against the old core's** (T4-TABLES's
  builder, `demo/tables.md`, 684 px, five tables): columns, natural widths,
  floors and row heights within 0.001 px; every table with a header 20.64 px
  taller. A 200-row table streamed seven characters at a time: 146,304 cell
  measurements against 603 when rows arrive whole (one run, load 12).
- **What the tour's contrast test judges** (T5-FINAL's builder, with the
  library, load 1.1 to 1.8): the glyphs judged on a page's fourth frame, and
  the same page with the library's draw calls answered and nothing drawn.
  The difference is the page's own text: from 603 (Chat) to 2,722 (Columns)
  glyphs. The frame with nothing drawn by the library still had 219 to 885
  glyphs on every page, more than the test's old lower bound of 212: that
  bound was met without any page's text. And the Stream page's own text was
  8 glyphs, because four frames of a replay is no text; the tour now feeds
  it whole (1,290). Least contrast on any page, T5-APP's builder: 4.63
  against a floor of 4.5.

### What nobody has looked at

Everything. Said as a list so that no line of it reads as checked:

- Any of the fourteen pages with the library drawing: the text, the
  selection highlight, links, rules, tables and their rules, formulas, the
  diff's bands and gutters, the columns, the marks of a search.
- The three gallery pages, which are imtypeset's demo sections shown at a size
  the reader picks (14, 16, 19, 23 or 28 px; 23 as they open, since T6-SIZE)
  where the other team's own pictures were taken at 19.
- The one line each page draws without the library, in the app's one font.
- Any of the four examples.
- Any PNG `make shot` or `make shot-all` writes. The tests read sizes and
  count colours.
- A real pointer or keyboard on any of it. Events are queued through
  `ImGuiIO`; no window manager, no GPU.
- The Columns page has no sheet behind it now and is light ink on a dark
  ground; `scripts/visual_diff.py` cannot find a region on it and says so
  (T5-B1).

### Open

**From the review of phase A (a reviewer's, from reading), then run by the
last task.** Each was reproduced by a test written first and seen to fail,
unless it says otherwise. No longer open:

- A library asked for and not drawing ended `scripts/shot.py` with a PNG and
  exit 0. Reproduced in a window; fixed (above).
- `TypesetView` took ANY exception under a call into the library for the
  library's and switched it off for the process, so a slip in the view's own
  Python turned every page into its one line. Reproduced with the library
  (an `IndexError` switched it off). The three views now share one rule:
  only an exception the `imtypeset` package defines switches the library
  off; anything else is raised as itself.
- The page tests' frame helpers rendered a frame whose window they had not
  ended when `draw` raised: the test then failed with Dear ImGui's "Missing
  End()" and the context was left mid-frame. Reproduced. The guard in
  `tests/conftest.py` already covered the in-process helpers (now shown by a
  test); 23 helpers, in-process and in child scripts, now end their window
  in an inner `finally`.
- `--tab columns:4097` was accepted and raised inside the page's first draw.
  Refused where the launch is parsed (`PageSpec.max_count`).
- A library with no font for the app's own role was unloaded and every page
  then said `load_fonts()` had not succeeded, of a call that had. The pages
  say which role had no font.
- Chat, Stream and Stress kept their views' documents in the library after
  giving up. They close them; the page's state stays, for `report()`.
- The tour's contrast test, and Chat's "finished messages are not laid out
  again": both strengthened (above, and the library's own layout counter).
  Neither found a defect in a page.

**Open, recorded and not scheduled. From the same review and not run by
anyone:**

- **Evidence that got thinner in phase A.** Find's 22-case oracle became
  nine needle counts with no positions. The count of lines moved under
  `KEEP_STREAMED` is not asserted on the typeset path. Diff's 54 "every case
  in every mode" page tests draw nothing: they run without the library.
- **The contrast reader skips translucent and rounded surfaces.** By the
  reviewer's arithmetic Find's current match is about 3.1 against the 4.5
  floor, and the test does not see it.
- **Suspected, not confirmed:** Chat with a hosted diff in view when the
  hosted widget fails; `scroll_to(block)` far down columns filled in order
  stopping short; `scripts/mouse_probe.py --xvfb` passing through the inner
  shell's status.

**Open from earlier tranches, still so:**

- Columns a host states for a table are lost to an edit above the table and
  to a change of theme or link ink.
- Keep or reset of a stream's held tables is inferred from `live_theme is
  theme`, which is the same object for a theme that is already ragged.
- A table row that arrives in pieces is replaced, not appended (the
  146,304 above). With the other team.
- The Stream page's `observe` makes about 600 library calls a frame on the
  code source, outside the parts it times.
- Fonts are measured through the old font reader (above).
- A numbered list is copied without its markers.
- The rule under a table's header takes a whole line of height. With the
  other team.

**Open from the deletion, by the builders who did it:**

- `Theme.at_pixel_height()` and `face_metrics()` load seven reference-core
  modules, not the one the plan named: both go through `advtext.style`. The
  Themes page and Chat's mono preset therefore still load node and packing
  classes when run. About ten lines to narrow; left because it would undo a
  seam another task tests. **T5-B2's builder's least sure decision.**
- `BlockStyle(interline=...)` is now a `TypeError` and a hand-built
  `BlockStyle` cannot carry an arbitrary interline triple. Nothing in the
  tree built one.
- `load_faces`, `LoadedFaces`, `TEXT_FACES` and `ALL_FACES` are still on the
  facade, by the rule, and load faces nothing sets text with. `ready` and
  `reason` are on it and no example uses them from there.
- `examples/theme_gallery.py` was deleted and not ported.
- Docstrings in kept files still describe themselves by comparison with
  deleted classes (about 110 mentions in the four largest typeset modules,
  T5-B1's count), and `pyproject.toml`
  has a mypy override naming `advtext.backends.imgui_draw`.
- The windowed tests share one Xvfb port. T5-B1 made the fixture wait for it
  to be free; six runs and the gates since passed, which is not a proof.

**Open from the last task (T5-FINAL), its own:**

- Built and gated once against `c9f8902` by the lead (above); nothing else was
  re-measured on it, and the texts that name `7a7bc36` (the Columns page's
  docstring among them) were not revisited.
- **Only `README.md`, this section and `docs/decisions.md` were brought level
  with the swap.** `docs/guide/`, `docs/adoption-plan.md`,
  `docs/imgui-risks.md`, `docs/litmus.md`, `docs/subpixel.md`,
  `docs/advance-rule.md`, `docs/visual-review.md` and `docs/cpp-extension.md`
  describe `main`: its views, its draw backend and its measurements. Of
  those only `docs/litmus.md` is about something this branch still runs
  (`make svg`).
- `scripts/run_demo.py` still exits 0 when the library was asked for and was
  not drawing; it only says so. An agent's choice: the window was opened to
  be looked at, and was.
- A helper's inner `finally` does not help when `draw` leaves a CHILD window
  open: Dear ImGui's complaint still replaces the exception. Only the
  conftest guard covers that, and only in-process.
- A view a page closed when it gave up makes its document again if anything
  asks it a question (measured: the Stream test's own readout did).
- The rule for whose a failure is turns on the exception's class. A
  `ValueError` or `TypeError` the Python package raises for a bad argument
  is now a bug that reaches the app's traceback page, where it used to
  switch the library off. That is the intent; nobody has listed which
  package calls can raise one on input a host controls.
- The tour silences the library through `imtypeset._lib`, a private name of
  a package this tree does not own. If it moves the test fails; it does not
  pass.

## 0c. Revision of 2026-10-10: an experimental branch draws through imtypeset

The newest revision, put first; sections 0 and 0b below are older and are not
changed by it. **This is the branch `experimental/imtypeset-adoption`, not
`main`, and nothing on it is committed.** The user asked for the work to be
started as an experimental branch (the words are quoted in `docs/decisions.md`,
"imtypeset adoption, experimental branch"); an unattended team of agents did
the rest, and every choice in it is an agent's.

**No person has looked at any of this in a window. Review was by reading only:
the three reviewers had no shell and ran nothing.** This section was written
before the review-fix task and the terminal gate ran, and was brought level
afterwards by the terminal gate's builder (IT-GATE2), who changed only the
sentences those two tasks made untrue: this paragraph, the A0 row, "The suite"
under "What was measured", and the first list under "Open".

**The gate, 2026-10-10, on the tree as it stands, nothing else of this session
running.** `make check` (ruff, black, mypy over 55 files, pytest): **5006
passed, 49 skipped, 4 xfailed**, load average 1.4 at the start and 2.1 at the
end. `make check TYPESET=1`, straight after: **5048 passed, 7 skipped, 4
xfailed**, load 1.9 and 1.7. No failure and no error either way; 5055 tests
each way, of which 42 need the library. Run by the terminal gate's builder, an
agent. A green suite says what the tests assert, and the list under "What
nobody has looked at" is what they do not.

imtypeset is a sibling checkout, `../imtypeset`: a C++ typesetter that keeps
one retained document and writes its own vertices. The plan this branch starts
on is that tree's `docs/advtext-rework-plan.md`, section 6.3, steps A0 to A6.
It was written by an agent from a spike and calls itself measured, not verified
by a person. **None of its figures is repeated here.**

**Without the library nothing changes.** With `IMTYPESET_LIBRARY` unset,
nothing of imtypeset is imported, the facade is the same 94 names, and no
existing view was edited. The new code is beside the old: `advtext/typesetter.py`,
`advtext/typeset_find.py`, `advtext/ui/typeset_view.py`,
`advtext/ui/typeset_stream_view.py`, `advtext/ui/pages/typeset.py`,
`examples/typeset_minimal.py`. The one existing source file touched is
`advtext/ui/app.py` (a font callback and an exit hook in `run`).

**To turn it on:**

    make typeset-lib                          # builds build/imtypeset-bundle/libimtypeset_bundle.so
    make check TYPESET=1                      # the suite with the library; its tests skip without it
    make run TYPESET=1 ARGS="--tab typeset"   # the one page that draws through it

`TYPESET=1` puts `IMTYPESET_LIBRARY` (the built file) and `IMTYPESET_PYTHON`
(`../imtypeset/python`, where the ctypes package is) in front of `test`, `run`,
`shot` and `shot-all`; setting `IMTYPESET_LIBRARY` yourself does the same with
another library. `make typeset-lib` needs `../imtypeset` and `../imgui_bundle`
beside this checkout (`IMTYPESET_ROOT`), and `make clean` removes the library
with the rest of `build/`. The first command and `make check TYPESET=1` were
run by IT-A1's builder; **`make run TYPESET=1` and `make shot TYPESET=1` have
not been run as make targets by anyone** (the page's two photographs were
taken by a script calling `scripts/shot.py`).

### What exists, step by step

| step | state | what there is | evidence, and whose |
|---|---|---|---|
| A0 freeze the oracle | half; the other half **blocked** | a local tag, `advtext-reference`, at 32e3953. Not pushed | the lead: the plan's a3c589a and 32e3953 have the same tree (7a591a48); checked again by this section's writer, with `advtext/` unchanged from the tag to `HEAD`. Blocked: the oracle scripts that refuse an untagged tree, and the dump of goldens, are writes in `../imtypeset`, which this session could only read. **The plan's order was not kept**: it wants imtypeset's goldens dumped before any file of advtext is edited; `advtext/ui/app.py` is edited on this branch and no golden was dumped. The tag still names the unedited tree, so the dump can still be made from it |
| A1 the description | built | `advtext/typesetter.py`: the gate, the font loader, a `Converter` from advtext's blocks to texts, runs and styles | IT-A1's builder: the plan's check (`census.py` reports only tables as misfits: 9 `TableBlock`s, 129 cells) passes, also run by the lead; over the six `demo/*.md` the port and the spike's converter describe 0 blocks differently; `tests/test_typeset.py` |
| A2 `TypesetView` | built; one page opted in | `advtext/ui/typeset_view.py`; `examples/typeset_minimal.py`; a fifteenth demo page, `Typeset`, in a new sidebar group `Experimental`. No existing page was converted | builder-3: 3 library calls on a steady frame, counted, +1 under the mouse; `tests/test_typeset_view.py`, `tests/test_page_typeset.py`. The plan's own check (`views.py --scenario ...`) is not reported as run by anyone |
| A3 streaming | built; on no page | `advtext/ui/typeset_stream_view.py`, over an unchanged `StreamDocument` | builder-5: four replays end with the text of a whole-source view; `tests/test_typeset_stream_view.py` |
| A4 find | built; wired on the `Typeset` page | `advtext/typeset_find.py` | builder-2: matches equal a search written another way over six demo files; `tests/test_typeset_find.py` |
| A5 tables | **not built** | a table is a Host block of a guessed height (24 px a row) that nothing draws: a blank gap. Its text is empty, so it copies as nothing and find does not see it. The page says so in one line | |
| A6 skip the material | **not built** | the description is still made by walking the material `build_document` produced | |

`make shot-all` now has 27 requests for 15 pages (`scripts/shot.py --list`,
counted by this section's writer); "fourteen pages" and "26 shots" in section
0b are the second build as it was.

### What was measured, by whom, at what load

Each is quoted from a result file in `.concerns/` (not version-controlled).
All on one 16-core machine while other agents ran suites on it; every window
was Xvfb with a software rasteriser. **Read the ratios.** No test asserts a
time.

- **A steady frame, `TypesetView.draw` against `BareView.draw`** (builder-3,
  IT-A2): the top of `demo/sample.md` at a 654 px measure, the call alone, the
  median of 70 frames each, four runs at load 5.8 to 9.0. Ratios 36.7, 43.6,
  56.2, 41.0; the builder's summary is "roughly 35 to 55 times less". BareView's
  own figure moved by 60% between runs. The first frame, same runs: 2.9 to
  3.5 ms plus 2.8 to 3.0 ms for the describe, against 182 to 348 ms for
  BareView's layout; both exclude `build_document`, which both need.
- **A frame that brings text, `TypesetStreamView.draw` against
  `StreamView.draw`** (builder-5, IT-A3): `demo/sample.md` at 24 characters a
  frame, five runs at load 4.5 to 8.5. Ratios 17.2 to 23.3 for the draw call.
  **That is not the cost of new text**, in the builder's own reading: most of
  it is the steady frame, and the parse, which both views pay and this work
  does not touch, is now the larger part. The whole frame, parse and draw, is
  "about 6 to 7 times" less.
- **Edits per stream** (builder-5, one run each, headless): `sample.md` at 24
  characters, 231 revisions made 170 `append_text`, 54 `replace_blocks` and 7
  with no edit; `tables.md` 67, 37 and 75; `math.md` 179, 55 and 3. Never more
  than one edit in a frame.
- **The page, both ways** (builder-6, IT-PAGE, one run each at load about
  3.2): searching "glue" finds 8 under either renderer; under `TypesetView` the
  frame has 16 more vertices with the needle than without, and under `BareView`
  none (it counts and does not mark). The two photographs are 1300x800,
  non-blank, and differ in 15.8% of their pixels, part of which is a caption
  line and not rendering. That figure says nothing about fidelity.
- **The suite.** The counts for the tree as it stands are in the gate
  paragraph at the top of this section (IT-GATE2's builder). The same two
  commands were run once before on the same tree by the review-fix task's
  builder (IT-GATE), with the same counts, at load 3.9 to 2.7. Before the
  fixes, the last whole runs were builder-6's and builder-5's: `make test`
  4995 passed, 47 skipped, 4 xfailed; `make test TYPESET=1` 5035 passed, 7
  skipped, 4 xfailed (load 3.0 to 6.9). The difference is the review-fix
  task's 12 tests (one of them library-only) and one test builder-5 added
  after its whole runs. The 7 skipped with the library are older tests that
  compare clock readings or take about 80 s, and run under `ADVTEXT_SLOW=1`.
- **The six failures.** Two builders each saw the same six failures once in
  `tests/test_typeset_view.py` under `TYPESET=1` while that file was being
  written. IT-GATE2's builder ran that file alone three times with the
  library, load 1.7 to 2.8: 26 passed, 26 passed, 26 passed; and it passed in
  both whole runs with the library above. They have not been seen on a
  finished file. **Why they happened then is still unexplained**: the second
  reviewer read the file and found no assertion that load could move, and
  named two things that could, neither tried: an earlier state of the test's
  driver, and the one display the windowed tests of every pytest process
  share.

### What nobody has looked at

Everything on screen. Stated as a list because each is something a test counts
and nobody saw: `TypesetView`'s text, selection highlight, rule and quote-bar
colours (vertices are emitted; that is all that is known); a streamed document
beside the whole one (compared by text only; the two views set the same pieces
3 px apart in height); the blank gap where a table is; the marks on the
`Typeset` page; the two photographs, which their builder opened to see the
pane was not empty and says nothing more about. Quotes share one bar and every
list is loose, by the library's header: not looked at either. Double and
triple click, Ctrl+A, a drag while text arrives, typing in the page's search
box with a real keyboard: code that mirrors `BareView`'s and has no test.

### Differences a host would meet

From the result files; each is as built, not as intended for good.

- `fonts=` is accepted and ignored: imtypeset draws from its own seven atlas
  fonts, loaded by `typesetter.load_fonts()` at the end of
  `load_additional_fonts`. `app.run` does that; a bare `app.load_fonts()` does
  not.
- Per-role palette inks and `page` are not applied. Live links are coloured
  and not underlined; changing the link ink describes the document again.
- Copying everything gives the non-empty block texts joined by the separator:
  no list markers, nothing for a rule or a table, a formula as its source.
- Find does not search table cells or formula source, and a match cannot span
  an inline formula.
- A selection that ends in a replaced block is dropped by `TypesetView`;
  `TypesetStreamView` keeps it while the characters it names are unchanged and
  drops it whole otherwise, where `StreamView` cuts it back.
- `DiffView`, columns, the specimen and the formula pages have no counterpart
  in the library and are not planned (the plan's own row).

### Open

**Found by review, from reading; then each reproduced by a test written first
and seen to fail, and fixed, by the review-fix task's builder (IT-GATE). No
longer open:**

- `TypesetView.set_document` raised `TypesetUnavailable` after any
  `typesetter.disable()`, and each call lengthened `reason()`: reproduced
  with a stand-in and with the library (four calls, four raises, the reason
  nested four deep). Now, when the library is off, the blocks are described
  and kept, no edit is tried, the view lets go of the library's document, and
  the next `draw` raises `TypesetUnavailable` with the reason unchanged.
- A malformed mark handed to `set_marks` raised inside `draw`'s guarded
  region and switched the library off for the whole process: reproduced with
  the library (`set_marks(finder.matches)`, then one frame). Now `set_marks`
  raises `TypeError` at the call, naming the mark, and keeps the marks it had.
  It checks the shape and the types of the fields, not that the positions
  exist.
- `Finder`'s docstring showed the `finder.packed(document)` wiring; it now
  shows `view.set_marks(finder.marks())` with `set_index` after every edit. A
  docstring only.
- `scripts/run_demo.py`'s docstring said fourteen pages; it says fifteen, and
  a test compares the word with the count of pages.

**Left by that task, and open:**

- The same family as the first item, not reached through `set_document`: a
  palette with another link ink makes the view close its library document
  (`_redescribe`), a call into the library whether or not it has been
  switched off. Not tested.
- Letting go of the library's document after a switch-off leaves its release
  to the library's Python package (`Document.__del__`, which makes the call
  inside its own `try`): one call into a library that has just failed.
- `TypesetStreamView.sync` still returns False once the library is off. It
  is harmless and no longer needed for safety; its docstring's reason is no
  longer true of the base view.
- `scripts/render_litmus.py`'s docstring still says fourteen pages.

**Open, recorded and not scheduled:**

- **A5 and A6**, above. **The other half of A0**, which needs a write in
  `../imtypeset`.
- **Stand-in headers.** The wheel ships none and its ImGui is a fork, so the
  library is compiled against upstream Dear ImGui of the same version and
  accepted by imtypeset's field probe (22 probes passed, the lead and IT-A1's
  builder), not by Dear ImGui's own check. The plan's section 3.2 has the two
  commands that would remove the caveat; they need the network and have never
  been run.
- **The library is built from `../imtypeset`'s working tree**, which had
  uncommitted changes and other agents editing it. Two builds of the same
  day differ (IT-A1's builder: different sha256, 16 bytes apart in size; not
  investigated, and the output path being embedded would also explain it). Every figure above is of the lead's build, which is not
  reproducible from a commit.
- **`typesetter.disable()` is for good and releases nothing**: the context,
  the seven fonts and open Documents stay, and `unload()` becomes a no-op. A
  gate that refuses still leaves `imtypeset._capi` imported and the shared
  object loaded.
- `draw()`'s "nothing drawn or claimed" on failure is false when the library
  raises after the text is on the draw list: a host's fallback then draws a
  second copy for one frame.
- `on_link` or `style_links` set after construction never recolour links.
- **In a stream**: a link in the part still being written cannot be clicked
  while text arrives; packed marks are dropped at every sync and plain marks
  sit on the wrong characters after a reinterpretation until the host searches
  again; a host must describe the whole document again each revision to
  rebuild its find index, because the view's descriptions are private.
- A list marker is described by code point, not as written; an unknown block
  type described first names a style that does not exist.
- **Not tested by anyone**: destroying the ImGui context without
  `typesetter.unload()` first, with a Document kept (IT-APP's builder saw the
  library refuse `add_font` on a stale context with an error and no crash;
  drawing a kept Document there was not tried); a real library failure
  anywhere but layout; a library that refuses, through the app's callback.
- **The tests' own limits**: the stream tests compare streamed and whole
  documents by text, so a wrong run or style after `append_text` would pass;
  the page test evidences marks by a vertex count, not a position; the
  `Typeset` page is always the `BareView` path in a headless frame, by its
  builder's decision, so `tests/test_pages.py` never sees the library draw;
  `tests/conftest.py`'s `window` shares one TCP display between every pytest
  process on the machine.
- The plan's own open items that bear here (its section 7) were not looked
  into: collapsed word gaps in justified text from the in-flight source, and
  scroll estimates that have never been scrolled with a real mouse. Its
  tab-in-code-block defect does not reach this converter by the reviewer's
  reading (`_code_lines` expands tabs).

## 0. Revision of 2026-10-07: the adoption plan was built, and this file was not rewritten

**Read `docs/adoption-plan.md`'s first section before the rest of this file.**
On 2026-10-06 and 07 an unattended team of agents implemented that plan: an
import surface, an embeddable view, colour, links, wrapping tables, structured
copy, and a streaming document and view. No person reviewed it or looked at it.
What follows from section 1 on is the account of the layout engine and the demo
as they stood before, with dated corrections where a sentence became false. It
is still the account to read for the engine. It is not the account of the
embedding or the streaming, which is the plan's.

What this file said that is no longer true, each corrected in place below:

| it said | now |
|---|---|
| the suite runs under two interpreters, one borrowed | there is one; the fallback to `../pptmstr/.venv` was removed |
| no click has ever happened | `scripts/mouse_probe.py`: 18 of 18 checks in a real window on Xvfb |
| copying joins lines with spaces; the caller supplies the hard-break set | a view's copy reads structure from the blocks; nobody supplies anything |
| table cells do not wrap | they do, where the table is wider than its measure |
| links render as ordinary prose, and nothing consumes `LinkSpan` | a view given `on_link` draws and follows them; the demo page, given none, draws them as before |
| item 2 of "what to do next": memoise the per-glyph preamble | built; a culled draw is 5.1 ms where this file says 9.4 (5.9 ms from the memo, the rest from hoisting a per-glyph import) |
| ragged-right goes through the optimiser | text that is not justified is filled first-fit at natural spacing |

**The gate.** `make check` on the final tree, run by the agent that closed the
session's gate: ruff, black and mypy clean, and `pytest` over the whole suite,
nothing ignored: **2897 passed, 7 skipped, 4 xfailed in 150 s**. The three tests that photograph a real window
(`tests/test_shot.py`, two in `tests/test_visual_diff.py`) were red at the
session's baseline because `DISPLAY=:1` was not reachable from its sandbox and
they were gated on `DISPLAY` being set. They now ask whether the display
accepts a connection and otherwise run on an Xvfb in a user namespace
(`tests/conftest.py`, `window`), which is where they ran and passed here. "No
test is skipped or marked `xfail`" below is no longer true: the four `xfail`s
are strict and assert a known defect of the total-fit breaker set ragged
(`tests/test_stream_stability.py`), and the seven skips are an 88 s
whole-paragraph run and six tests that compare two clock readings, all behind
`ADVTEXT_SLOW=1`; each of the six has a count test beside it holding the same
claim without a clock.

What works that this file does not otherwise mention, each with its test file
as the evidence and none of it looked at: `BareView` (`tests/test_bare_view.py`),
per-unit layout (`tests/test_units_layout.py`), the material-to-shipped index
map behind links and colour (`tests/test_spans.py`), wrapping tables
(`tests/test_tables.py`), first-fit breaking (`tests/test_firstfit.py`), the
streaming document compared with a whole parse after every piece
(`tests/test_stream.py`), and `StreamView` (`tests/test_stream_view.py`).
## 0b. Revision of 2026-10-07, later the same day: a second build

**Read the first section of `docs/adoption-plan.md`, "Second build", before
this.** After the adoption plan was built the user asked for more and a second
unattended team built it: the demo is a sidebar of fourteen pages where it was
five tabs; there is a diff model and a `DiffView`, unified and side by side;
inline and display mathematics from a `$...$` subset; blocks of a document that
a host widget draws; and more calls on a view. That section lists what changed
without anybody seeing it, the choices left for a person, what ran in a window,
what no reviewer read, what things cost, and the known limits. `docs/decisions.md`,
"Second build", keeps the user's nine decisions, quoted, apart from the agents'.

**No agent judged how any of it looks, and nothing in this file says.**

What this file says below that is no longer true, each corrected in place or
here:

| it says | now |
|---|---|
| five tabs; `make shot-all` photographs eight shots | fourteen pages in a sidebar, found by scanning `advtext/ui/pages/`; 26 shots, listed by `scripts/shot.py --list` |
| the demo window is 1100x800 and its content region 1070 px | 1300x800; the body right of the sidebar is 1068 x 776 px (builder-17, measured on Xvfb) |
| radicals are absent; sized delimiters are absent | both are built, from the font's ready-made outlines only (section 3) |
| "A LaTeX parser" is deliberately absent | still true of the engine. `advtext/mathtext.py` reads a subset above it, by the user's decision; matrices are left out for now, also the user's |
| the Formula tab is one summation being widened | the Formula page holds eleven hand-built formulae; the first nine are set byte-identically to before the engine grew (pinned by a test) |
| a glyph the bound face lacks is drawn as nothing | borrowed from another of the theme's faces, else U+FFFD and counted; copy and Find return what was written |
| the facade is 58 names | 94 |

**What works that this file does not otherwise mention**, each with its test
file as the evidence and none of it looked at: the diff model and its parser
(`tests/test_diff.py`), `DiffView` (`tests/test_diff_view.py`), a fenced diff
hosted in a document or stream (`tests/test_hostdiff.py`), the math subset
(`tests/test_mathtext.py`), formulas in documents and streams
(`tests/test_mathinline.py`), the view API (`tests/test_viewapi.py`), the page
scan and the shell (`tests/test_pages.py`), and one test file per new page
(`tests/test_page_*.py`).

**The gate.** `make check` on the final tree, from clean caches, run by the
agent that closed this build's gate:

ruff, black (131 files) and mypy (50 source files) clean, and `pytest` over
the whole suite, nothing ignored: **4893 passed, 7 skipped, 4 xfailed**, in
277 s on the run whose per-test times are below. Nothing was red at any point
of the gate and nothing was skipped, xfailed or weakened by the gate closer.
The seven skips and the four strict xfails are the first build's, described in
section 0. The 4893 are the 4892 of the last builder's run and one test added
at the gate (a NUL in a message copied from the Chat page's buttons). The
verbatim tail of the final run is in `.concerns/CZ-gate--builder--result.md`
(not version-controlled).

**Suite time, and where it grew.** 150 s at the end of the first build, 277 s now
(293 s on the last builder's run, on a busier machine). `--durations`, summed
by file over every phase of 5 ms or more (269.7 s in 52 files): the nine page
test files and `tests/test_pages.py` are 92.4 s between them
(`test_page_stream.py` 19.8, `test_page_stress.py` 16.4, `test_page_chat.py`
13.7, `test_page_math.py` 11.6, `test_page_inspector.py` 8.0, `test_pages.py`
7.9, `test_page_find.py` 6.4, `test_page_tables.py` 4.6, the rest under 4),
which is most of the growth; the math and diff test files are fast for their
size (`test_mathtext.py` 4.1 s, `test_mathinline.py` 3.5, `test_diff.py`,
`test_diff_view.py` and `test_hostdiff.py` under 3 each). The four files that
led the first build's list are where they were: `test_stream.py` 29.0,
`test_stream_view.py` 25.5, `test_units_layout.py` 19.1,
`test_stream_stability.py` 13.7. No single file dominates. The slowest test
is new: `tests/test_page_stress.py::test_the_page_reports_its_figures_at_1_4_and_16_panes_in_a_real_window`,
12.0 s, which runs the real app for 90 frames at each of three pane counts on
a software rasteriser; that is what the test is, and nothing was cut. The
next nine are 3.8 to 6.2 s each, seven of them a page in a real window or a
page's stream run to its end.

**`make shot-all`, after the last code change**, on Xvfb in a user namespace
(llvmpipe). Every PNG is 1300x800. "Body" is the region right of the sidebar
(x 216 to 1284, y 12 to 788). "Background" is the single most frequent colour
there, and the last column is the share of body pixels that are any other
colour: it says a page is not blank, and it does not say how much ink there is
(on a page with a light sheet on the dark surround, whichever of the two is
smaller counts as not background). Nobody looked at a PNG.

| request | file | bytes | size | most common body colour | body pixels not that colour |
|---|---|---|---|---|---|
| `document` | `demo-document.png` | 113345 | 1300x800 | (250,250,248) | 46.4% |
| `document:debug` | `demo-document-debug.png` | 123918 | 1300x800 | (250,250,248) | 56.6% |
| `columns:1` | `demo-columns-1.png` | 106801 | 1300x800 | (250,250,248) | 45.8% |
| `columns:2` | `demo-columns-2.png` | 149760 | 1300x800 | (250,250,248) | 21.9% |
| `columns:3` | `demo-columns-3.png` | 154445 | 1300x800 | (250,250,248) | 22.4% |
| `specimen` | `demo-specimen.png` | 115151 | 1300x800 | (250,250,248) | 34.3% |
| `formula` | `demo-formula.png` | 87494 | 1300x800 | (250,250,248) | 42.7% |
| `blocks` | `demo-blocks.png` | 29672 | 1300x800 | (14,14,16) | 24.9% |
| `math` | `demo-math.png` | 127487 | 1300x800 | (14,14,16) | 28.7% |
| `math:done` | `demo-math-done.png` | 136023 | 1300x800 | (14,14,16) | 29.8% |
| `themes` | `demo-themes.png` | 101815 | 1300x800 | (250,250,248) | 25.0% |
| `themes:split` | `demo-themes-split.png` | 163910 | 1300x800 | (30,30,30) | 66.0% |
| `tables` | `demo-tables.png` | 85525 | 1300x800 | (14,14,16) | 24.2% |
| `tables:floors` | `demo-tables-floors.png` | 77610 | 1300x800 | (14,14,16) | 22.9% |
| `find` | `demo-find.png` | 116471 | 1300x800 | (14,14,16) | 21.5% |
| `inspector` | `demo-inspector.png` | 146368 | 1300x800 | (14,14,16) | 22.1% |
| `stream:400` | `demo-stream-400.png` | 124981 | 1300x800 | (14,14,16) | 34.2% |
| `stream:table,done` | `demo-stream-table-done.png` | 110307 | 1300x800 | (14,14,16) | 31.2% |
| `chat:all` | `demo-chat-all.png` | 119684 | 1300x800 | (14,14,16) | 25.8% |
| `chat:roboto,all` | `demo-chat-roboto-all.png` | 131369 | 1300x800 | (14,14,16) | 27.1% |
| `diff` | `demo-diff.png` | 89615 | 1300x800 | (250,250,248) | 45.1% |
| `diff:git,side` | `demo-diff-git-side.png` | 96629 | 1300x800 | (250,250,248) | 68.5% |
| `diff:wide,unified,dark` | `demo-diff-wide-unified-dark.png` | 135794 | 1300x800 | (26,26,29) | 79.9% |
| `diff:long,both` | `demo-diff-long-both.png` | 143685 | 1300x800 | (250,250,248) | 63.4% |
| `stress:4` | `demo-stress-4.png` | 113001 | 1300x800 | (14,14,16) | 40.1% |
| `stress:16,streaming` | `demo-stress-16-streaming.png` | 161473 | 1300x800 | (14,14,16) | 42.2% |

26 PNGs for 14 pages, exit 0, 74 s. **No page is blank**: the lowest share is
21.5% (Find). Against the builder's run of the morning, 11 of the 26 files
differ in size: the four Diff shots (taken then before the palette change),
and the Chat, Stream, Stress and Inspector shots, which photograph a clock or
a timing readout; the other 15 are the same size to the byte. The Blocks
shot is the outlier by size (29,672 bytes, 175 colours where the others have
570 or more), as its builder also reported; it is a toolbar at three widths
on the dark surround. Reported, not judged.

---

**The gate.** These figures were taken while this document was being written and
the tree was **not** settled — other work was landing in `tests/` during the run,
and a suite read mid-save fails for reasons that recover on a second run. The
terminal gate is the authority for the final counts; the test *count* below in
particular went 702 → 705 → 733 → 803 over the hours this revision took.
Everything else in this file is a measurement of behaviour rather than of the
board, and does not move that fast.

The figures below are `T9-gate`'s, and **they are a snapshot of a tree that was
still being written.** They are a real green rather than a mid-write one: the
suite, both linters and both type checkers were re-run three times over the same
settled state. But T9's own premise — "everything else has finished writing" —
was false when it ran. `T14-tolerance` and `T16-formulas` held files throughout,
and `T17-spacing` and `T18-colmargin` began writing `advtext/style.py` and
`advtext/ui/app.py` within the hour, after which three consecutive runs failed in
three *different* files.

**`T12-final-gate` is the authority over this count, not this table.** Do not
read the number below as terminal; read it as the last point at which the tree
was known green.

| | |
|---|---|
| `make test` | **803 passed, 0 failed, 0 skipped, 0 xfailed** |
| `make lint` | clean — ruff (`E,F,I,UP,B`) and `black --check` over `advtext tests scripts` |
| `make typecheck` | clean — `mypy` strict |
| `make svg` | writes all five artifacts |
| `make shot` | writes a PNG of a real window, 2.3-3.8s per tab |

No test is skipped, marked `xfail`, or disabled, and nothing was weakened to get
that. Run twice, under **both** interpreters the `Makefile` can select — the
project's own `.venv` and the borrowed one — because they carry different tool
versions (ruff 0.16.8 against 0.16.2, mypy 2.3.1 against 2.3.0) and the
`Makefile` warns in its own header that the two may disagree.

*(2026-10-07: there is no borrowed interpreter any more. `make` uses `.venv`
or stops and names `make bootstrap`. The comparison below is history, kept
because it is why the fallback was a hazard: it hid a real difference.)*

**They still agree on lint and types. They no longer agree on the suite**, and
the reason is `make shot`:

| | own `.venv` | borrowed |
|---|---|---|
| `make test` | 803 passed, 0 skipped | 802 passed, **1 skipped** |
| `make lint` | clean | clean |
| `make typecheck` | clean | clean |
| `make shot` | writes the PNG | **fails** |

The skip is `tests/test_shot.py`, on `numpy is not installed, so hello_imgui
cannot export the framebuffer`, and it is the honest thing for that test to do:
the borrowed tree is read-only (`docs/decisions.md` §2) so numpy cannot be put
in it, and `hello_imgui.final_app_window_screenshot()` returns a
`nanobind::ndarray` that has nowhere to go without it. The same shortfall makes
`make shot` itself fail there, with a `TypeError` rather than an `ImportError`
— the failure mode `advtext/ui/document_view.py` already documents for a
different call. **So "0 skipped under both interpreters" is a bar this tree no
longer clears, and the way to clear it is `make bootstrap`,** which installs
`.[dev]` and with it numpy.

---

## 1. What works, and the evidence

"733 tests pass" is not evidence. These are.

### The rounding discipline, demonstrated end to end

TeX's §625 sets glue by accumulating the total natural stretch, multiplying by
the box's ratio **once**, rounding *that*, and taking a difference against the
previous rounded total. Round each space independently instead and the right edge
wavers by a scaled point or two per line, which reads as a bug in the line
breaker — where nobody will look for it.

**Every justified line in `demo/sample.md` ends exactly on the right margin.** Not
approximately: zero residue.
`tests/test_litmus.py::test_every_justified_line_ends_exactly_on_the_right_margin`
asserts it through four modules — `pack`, `linebreak`, `shipout`, `ui` — against
real font files with real `GPOS` kerning.

The rounding is Pascal's (half away from zero), not Python's (half to even),
because the algorithm takes *differences* of successive rounded values and a 1 sp
divergence at glue node *k* shifts everything from *k* onward. That is correction
C3 in `docs/tex-notes.md`, and it is pinned at an exact half.

### The line breaker is optimal, by enumeration rather than by assertion

`tests/test_linebreak.py` brute-forces **all 2^8 breakings** of a test paragraph
and checks the total-fit pass finds the minimum-demerit one. On its own that
proves less than it looks, so it is paired with
`test_greedy_first_fit_picks_a_different_and_worse_breaking_for_the_same_paragraph`
— a greedy control on the same input, which must come out *different* and
*worse*. Without the control the optimality test would pass for a greedy
implementation.

### The display sigma is a different glyph, not a bigger size

This is the claim most likely to be doubted and the one most easily faked. Latin
Modern Math's vertical variant chain for U+2211 is `[summation, summation.v1]`,
and **`summation.v1` has no codepoint in the font at all** — 227 of that font's
vertical variants are unencoded and it uses no Private Use Area. So the
dishonest implementation is easy to reach by accident: look the operator up by
codepoint, find no variant, set U+2211 larger. It looks almost right.

`tests/test_litmus.py::test_the_display_sigma_is_a_larger_glyph_and_not_the_body_one_scaled`
rules that out. It resolves each rendering's operator back through
`fontlib.glyph_name` to the name the *font* gave it, and asserts display reached
`summation.v1` while text reached `summation` — **at an identical shipped font
size**, so a scaled-up body glyph fails even though its rendered height would
pass a naive height comparison. Measured extents at 32 px: 32.032 against 44.832,
a real 40% taller glyph.

### The ImGui backend's geometry is verified

**A window needs a display; a frame does not.** `create_context()` allocates
plain memory, `ImFontAtlas` bakes glyphs on the CPU through stb_truetype, and
`new_frame`/`render` build vertex buffers in RAM. So the backend runs here, and
`tests/test_imgui_draw.py` ships the litmus formula through it in a real frame
and asserts **one textured quad per glyph** reaches the vertex buffer — including
the display summation, reached through synthetic plane-15 codepoints written into
a copy of the font's format-12 cmap.

That test carries a negative control:
`test_an_unpatched_font_cannot_see_the_display_summation` asserts the glyph is
*absent* through the unpatched file, so the patch cannot look unnecessary.

### And it has now been composited to a screen, and photographed

This is new, and it is the sentence this document said for most of its life that
it could not say. `make shot` opens a real window through the real `immapp.run`,
runs it for N frames, and grabs the framebuffer with
`hello_imgui.final_app_window_screenshot()`. Five tabs, 1400×900, 2.3-3.8s each.
Section 2 has what that did and did not settle.

Three defects were found by looking at the resulting PNGs and were reachable
from nothing else in this tree: an `ImGuiIO` ndarray field that needs numpy and
raises only on the first *click*; dark ink drawn with no page behind it, which on
ImGui's dark theme is invisible text rather than an error; and the body text
being set to the full width of the window, which at 1100 px is 145 to 156
characters a line.

### The column flow is `\vsplit`, not a height accumulator

`advtext/columns.py` implements §970-§976 `vert_break`, §968-§969
`prune_page_top` and §977 `vsplit` as `docs/tex-notes.md` §6.2-§6.4 transcribes
them, and the module docstring argues each of the three things a hand-rolled
splitter gets wrong. The one worth repeating here is the head of column 2: cut a
vertical list between two lines and the interline glue that separated them
becomes the first thing in the next column, so every column but the first starts
one `\baselineskip` low — and by an amount that varies with whichever line
landed there, so they are not even *consistently* wrong. `tests/test_columns.py`
pins the fix by comparing columns against each other rather than against a
number.

**It is cheap, and the number is the reason balance was left out rather than
feared.** Splitting `demo/sample.md`'s 253 composed nodes three ways at a 262 pt
measure costs **0.64 ms**, best of five; `demo/columns.md`'s 387 nodes cost
0.77 ms. Composing the same document at that measure costs **541 ms** in the
same process. The split is a thousandth of the work that produced the material
it splits.

### The specimen's kerning section is falsifiable to the scaled point

`advtext/ui/specimen.py` sets each kern pair twice, once with the font's `GPOS`
value applied and once with it dropped, and `tests/test_specimen.py` asserts the
difference between the two boxes **equals** that value rather than merely being
non-zero. `rt` is in the pair list because Roboto kerns it *positive* (+24/1000
em), so a reader is not left with the rule "kerning pulls letters together".
Only the four Roboto faces carry a `kern` feature at all; Inconsolata is
monospaced and Latin Modern Math spaces through its `MATH` table, so a specimen
showing a kern for either would be showing a bug.

Two real defects were found by measuring what had been written off as
unmeasurable:

- **The backend asked ImGui for the wrong size.** "Size" means the em to
  `fontlib` and the pixel height to stb_truetype; every glyph baked about 12.4%
  too small, drifting 42 px over a 44-character line. Fixed by `baked_size_px`.
- **The synthetic codepoints did not draw at all**, so the project's headline
  claim held in the SVG backend and not this one, for a mechanical reason.

### Selection works, and copies as prose

A drag across five lines highlights edge to edge, including a heading at its own
larger line height, and **every body-line fragment has the same height** whether
or not its glyphs have descenders — because the rect is sized to the line box.
Copying joins wrapped lines with **spaces, not newlines**: a paragraph wrapped
into five lines is one paragraph. A newline inside a fenced code block survives,
because the caller supplies the hard-break set.

*(2026-10-07.)* That last clause described `selection.text(hard_breaks=...)`,
and the only callers that passed the set were tests: Ctrl+C in the demo joined
a code block's lines with spaces, which `docs/adoption-plan.md` inferred and a
failing test then confirmed. A view's copy now goes through
`UnitModel.copy_text`, which reads the separators off the blocks: a blank line
between blocks, a newline between code lines and list items, a tab between
table cells. A wrapped line is still a space. The highlight changed too: it no
longer covers blank fill at a line's ends, so "edge to edge" above is true of
full lines and not of a paragraph's last line or of ragged text. Both are in
the plan's list of visible changes, with measurements.

### The performance numbers are all re-runnable

Every performance claim in this tree came out of a script that is in this tree
and prints the table its own docstring quotes:

| | |
|---|---|
| `scripts/bench_reflow.py` | compose / ship / selection index, across widths |
| `scripts/bench_draw.py` | the per-frame ImGui draw cost |
| `scripts/verify_advances.py` | ImGui's advances against fontTools' |
| `scripts/verify_ascent.py` | ImGui's baked ascent against ours |

All four run here with no display. This matters more than the numbers: a figure
in a docstring that came from a throwaway script is a figure a later reader
cannot check, and this project twice caught itself doing that.

---

## 2. What has and has not been executed

**This section used to open "Nothing in this repository has ever been composited
to a screen." That is no longer true here, and this is the fourth revision of a
belief the file itself calls the single most corrected one in the project.** The
three earlier versions were: *nothing about ImGui can be checked* (wrong — a
window needs a display, a frame does not); *ImGui geometry is checked but nothing
is composited* (true at the time); and *no display is reachable and Xvfb cannot
start* (true of the sandbox this was built in, false of this machine). Getting it
wrong in a *new* direction now would be the poor outcome, so what follows is what
was run, where, and when, and nothing beyond it.

### The display, described rather than assumed

Observed on 2026-09-23 on this machine:

| | |
|---|---|
| `DISPLAY` | `:1`, with `/tmp/.X11-unix/X0` and `X1` both present |
| `XDG_SESSION_TYPE` | `wayland` — the X server at `:1` is what the ImGui demo talks to |
| server | X.Org 1.22.1.9, `xdpyinfo` |
| GL | **direct rendering, on real hardware.** AMD Radeon (renoir) through Mesa 22.3.6, core profile 4.6, 512 MB video memory |
| Xvfb | still cannot create its lock file under `/tmp`. Unchanged, and now irrelevant |

**This is not a software rasteriser**, which matters because the two remaining
compositing risks — texture formats and premultiplied alpha — behave differently
on llvmpipe than on a driver. It is also one GPU, one driver and one X server.
Nothing here says anything about a second machine.

### What runs under the suite, traced call by call

Function-level, by `sys.settrace` over a full suite run, counting `call` events
against the functions each file defines:

| | reached | unreached |
|---|---|---|
| `advtext/backends/imgui_draw.py` | **12 of 12** | — |
| `advtext/columns.py` | **9 of 9** | — |
| `advtext/ui/specimen.py` | **23 of 23** | — |
| `scripts/run_demo.py` | **2 of 2** | — |
| `advtext/ui/document_view.py` | 17 of 18 | `selection` |
| `advtext/ui/app.py` | 14 of 35 | everything that needs a frame: `run`, `gui`, `load_fonts`, `apply_style`, the five `_*_tab` functions, `_paint_sheet`, `_draw_at`, `_face_font` |
| `scripts/shot.py` | 7 of 10 | `main`, `_grab`, `patched_run` |

`scripts/run_demo.py` is a *function*-level entry and it flatters the file
slightly: `tests/test_run_demo.py` covers `main` and `_no_window` including all
three cells of the `DISPLAY` guard, `--tab` in nine spellings and `--source`,
but it replaces `advtext.ui.app.run` with a recorder, because `tests/conftest.py`
forbids this suite from opening a window. So what the suite does not execute is
the `run(...)` call itself, and `advtext/ui/app.py` is alone on that list now.

Three entries have moved and are worth naming because earlier revisions of this
file got them wrong in both directions:

- **`_debug_line` and `_debug_glue` are no longer unreached.** This file recorded
  them as the only two unexecuted functions in `imgui_draw.py`. They are covered
  by the suite *and* they have now drawn on a screen — `make shot ARGS="--tab
  document:debug"` photographs the line boxes and the per-glue rectangles.
- **`DocumentView.draw`, `_handle_mouse`, `_handle_copy` and `_document_point`
  all run under the suite now.** They were on the unreached list. What is still
  untouched is `DocumentView.selection`.
- **`scripts/run_demo.py` is no longer on the list at all.** It was on it for
  most of this project's life, in this file and in three others.

### What runs in a real window, traced the same way

Seven `scripts/shot.py` runs at 1400×900 — `document`, `document:debug`,
`columns:1`, `columns:3`, `specimen`, `formula`, `blocks` — unioned, under the
same tracer:

| | reached | unreached |
|---|---|---|
| `advtext/ui/app.py` | **35 of 35** | — |
| `advtext/backends/imgui_draw.py` | **13 of 13** | — |
| `advtext/ui/specimen.py` | **23 of 23** | — |
| `scripts/shot.py` | **10 of 10** | — |
| `advtext/ui/document_view.py` | 13 of 18 | `cmds`, `invalidate`, `selected_text`, `selection`, `_granularity_for` — all input-driven |
| `advtext/columns.py` | 6 of 9 | `columns`, `fits`, `compose_into_columns` — the app caches, so it calls the split directly |

**Both traces are needed and neither is sufficient.** `app.py` is 14 of 35 under
the suite and 35 of 35 in a window; `document_view.py` is 17 of 18 under the
suite and 13 of 18 in a window, and the five it misses in a window are exactly
the ones a mouse would reach. Union them and **the only function in this tree
that has never run is `DocumentView.selection`**, a one-line property returning
`self._selection` that no caller in the tree asks for.

`run_demo.py` with `DISPLAY` unset refuses in 0.04s with exit 2 — the guard sits
above the `advtext` import on purpose and a test pins that ordering — and with
`DISPLAY` set it opens a window that was still up when a 10s timeout killed it.

One measurement caveat, because it cost time: **running seven shots
back-to-back in one shell loop failed four of them** and each succeeded on its
own. The X server or the window manager does not like a new window every two
seconds. A `make shot-all` that exits non-zero is worth re-running before it is
believed.

### What is still genuinely unverified

Shorter than it was, and it is not empty.

- **No person has clicked.** This bullet read "No click has ever happened"
  until 2026-10-06. `scripts/mouse_probe.py` now runs the real app in a real
  GLFW window and posts mouse, wheel and key events to ImGui's input queue over
  glyph positions read back from the view: eight gestures, eighteen checks on
  the selected range, the selected text and the clipboard, all passing
  (`python scripts/mouse_probe.py --xvfb`, about 3.5 s, re-run 2026-10-07). So
  selection has been *performed*, by a script. What is left: the events enter
  at `ImGuiIO` and not at the X server, so GLFW's callbacks and a window
  manager's focus and capture are untested; the window was on Xvfb with a
  software rasteriser; and nobody has dragged a selection and said what it was
  like. `App.open_tab` and the `--tab columns:3,debug` grammar were built when
  nothing could click, and are still how a screenshot picks a tab.
- **Everything the adoption plan built is unseen.** Four examples open real
  windows inside their tests and draw every glyph they ship. No frame of a dark
  palette, a link underline, a stream or a wrapped table has been judged by
  anyone. `docs/adoption-plan.md` section B is the list.
- **One machine.** One GPU vendor, one Mesa version, one X server, one 1920 px
  window-manager clamp.
- **Font atlas limits.** Still nothing here has hit one; see
  `docs/imgui-risks.md` item 10.

### What `make run` actually does here

Re-measured, and the middle row of the old table is gone because the display is
reachable now:

| situation | what happens | elapsed |
|---|---|---|
| `DISPLAY` unset | `run_demo.py` refuses, prints `make run` and `make shot` recipes; exit 2 | 0.04s |
| `DISPLAY=:1`, this machine | a window opens and stays up | — |
| `DISPLAY=:1` set but unreachable (an agent sandbox, 2026-10-06: `socket(AF_UNIX)` refused) | GLFW aborts on `IM_ASSERT( glfwInitSuccess )` | about 0.6s |
| the same sandbox, Xvfb in a user namespace over TCP | a window opens; `scripts/mouse_probe.py --xvfb` and `scripts/shot.py` both ran this way | 3.5s and 6.4s whole command |
| no display at all | `make shot-headless` — Xvfb in a user namespace, 22s per tab | — |

The `XVFB_RUN` block this section used to tell you to uncomment **no longer
exists**; the `Makefile` header records all three beliefs it has held about
running a window and which one was measured. `docs/imgui-risks.md` is still the
ordered list of what to look at, and item 2 on it has been settled since.

---

## 3. What is deliberately absent

These are decisions with reasons recorded, not omissions. `docs/decisions.md`
gives the reasoning for each; this list exists so nobody spends a day discovering
one.

*(2026-10-07.)* Two things this list never named, because they were assumed,
are no longer absent: a document that arrives a piece at a time
(`advtext/stream.py`), and a view that is not the demo's page
(`advtext/ui/bare_view.py`). And the first sentence of the project, "a total-fit
line breaker", is now true of justified text only.

- **Hyphenation** — roughly 1000 lines with the worst interaction in TeX
  (ligature reconstruction, §915-916). The first and emergency passes run; the
  hyphenation pass does not. **This one has a measured price**; see section 4.
- **`ext_tag` extensible glyph assembly** — not needed, because the summation
  variant chain gives a real display glyph, and TeX's own sanctioned fallback is
  the largest available variant. *(2026-10-07: that fallback is now taken for
  real, by sized delimiters; see the last item of this list.)*
- **Delta nodes in `try_break`** — a 1982 performance optimisation where the
  subtle bugs live. **The correctness half of that argument still stands; the
  performance half turned out to be wrong**, and section 5 says what it costs.
- **`\halign`, `\mathchoice`, full ligature reconstruction** — still out, for
  the reasons `docs/decisions.md` gives.
- **Page breaking — partly in now, and the part that is in is named.** This entry
  used to read "no `vsplit`, no page cost function" and half of it has changed.
  `advtext/columns.py` implements §970-§976 `vert_break`, §968-§969
  `prune_page_top` and §977 `vsplit`, which is what the Columns tab flows through.
  Still absent, deliberately: **§980's part 45, "The page builder"** (`tex.web`
  line 19105) — no `\output` routine, no §1005 page cost, no
  `\topskip`/`\maxdepth` page state, no marks and no inserts. And **no
  balancing**: columns fill in order and
  the last one is as short as it turns out to be. `columns.py`'s docstring costs
  balance out at a few milliseconds and records that it was dropped for scope
  rather than for cost. The interline-glue rule (§679) *is* in scope and is what
  makes the vertical rhythm look right.
- **Bidi, complex shaping, CJK line breaking** — left-to-right only.
- **A LaTeX parser** — the formulas are constructed by hand through
  `advtext.math`'s API, which was always the scope. What *is* in that API has
  grown: fractions, big operators with limits, scripts and the atom classes.
  Radicals and accents were on this list as out of scope and have been put back
  on the table, because that exclusion was an agent's decision rather than a
  requirement. The Formula tab was one summation when this revision started and
  is being widened to a gallery; whatever it holds when you read this, the
  claim it exists to prove is still the one in section 1 — the display operator
  is a different glyph, not a scaled one.
  *(2026-10-07, second build.)* The engine now also sets radicals, `\left` ...
  `\right` delimiters sized to their content, explicit spaces and words in a
  formula; accents are still out. It still has no parser. Above it,
  `advtext/mathtext.py` reads a fixed subset of `$...$` source into those
  atoms and refuses the rest with a reason, and a document sets formulas only
  when built with `math=markdown_math()`. **Matrices are left out for now, by
  the user's decision.** Also out: accents, `\dfrac` / `\tfrac`, `\sqrt[n]`,
  and anything taller than the largest ready-made outline (a `\left` pair
  takes the largest when it covers 75% of what TeX's rule asks; the 75% is the
  lead agent's number, not TeX's).

---

## 4. What is wrong or incomplete

The part a flattering write-up would leave out.

**Five items below were open tasks when this was written**, so the numbers in
them are the defect as measured and not the defect as it will stand: the breaking
tolerance, the sentence space, the three-column measure, the formula gallery, and
word-origin snapping in the renderer. Each says so in place. The rule that
applies to them is the one in Provenance — re-measure rather than trust — and it
applies more sharply here than anywhere else in this file.

### The breaking tolerance has now been reviewed, and the answer was no

**`advtext.ui.PROSE_BREAKING` is being changed while this is written and the
table below names the values it was measured at rather than saying "as
shipped".** At the moment of measuring it was `\tolerance=1000` with
`\emergencystretch=20pt`; it read `\tolerance=6000` with no emergency stretch an
hour later. Read the constant, not this paragraph.

**It settled back where the table was measured** (read 2026-10-06):
`PROSE_BREAKING = LineBreakParams(tolerance=1000, emergency_stretch=20 * UNITY)`
in `advtext/ui/__init__.py`. The 6000-with-no-emergency-stretch setting did not
ship as the default; it survives as `PROSE_BREAKING_BOUNDED`, and
`PROSE_BREAKING`'s docstring gives what each costs. So the sentence above
describes an hour, not the tree, and the table's second row is the shipped
value. Its counts were not re-run when this note was added.

At plain TeX's defaults `demo/sample.md` produces **seven overfull lines, the
worst by 180.9 pt** — text sitting in and past the margin. At 1000+20 there are
none, and the price is 10 underfull lines of 75.

|                              | lines | overfull | worst    | underfull | loose | tight |
|------------------------------|------:|---------:|---------:|----------:|------:|------:|
| plain TeX defaults           |    72 |        7 | 180.9 pt |         3 |    13 |    17 |
| `\tolerance=1000` + 20 pt    |    75 |        0 |     0 pt |        10 |    20 |    12 |

`TextBlock` lines only, at the 420 pt measure, by `line.fitness` — the same
method `tests/test_litmus.py::test_no_line_in_the_document_is_overfull` uses, so
the table and the assertion cannot drift apart. (Re-measured after `demo/sample.md`
grew. The previous revision recorded 55/6/180.9/2/12 against 58/0/0/8/19; the
shape of the finding is unchanged and the counts are not.)

**This paragraph used to end "nobody with authority over how the document should
look has been asked". They have now been asked, and they said the loose lines
are not acceptable.** The user looked at a render of the Columns document and
named two words, "people" and "counting", both first-word-of-line. So this is no
longer a decision waiting for a reviewer; it is a defect with an owner, and
`PROSE_BREAKING` is expected to move. **Every number in the table above is
measured against the current value and will need re-deriving when it does.**
Ragged-right is now a live option too, for the same reason radicals are: the
user has said they will trade rag for text that looks better.

Two cautions for whoever does that, both from re-measuring rather than from the
report:

- **A last line stretched by `\parfillskip` has `glue_order == FIL` and a
  `glue_set` around 2.8e7.** Count "lines past natural stretch" without
  excluding those and the number is meaningless. Counting only boxes with
  `glue_sign == STRETCHING` *and* `glue_order == NORMAL`, `demo/columns.md` at a
  468 pt measure has **8 of 58** such lines past natural stretch, worst
  `glue_set` 1.661.
- **The measure the decision is made at matters more than the tolerance.** The
  same document at a 262 pt measure — roughly what the three-column layout sets
  at, which is what the user was looking at — has **61 of 130**, worst 4.662.
  Raising the tolerance is not what made those lines loose; a 262 pt measure has
  about four interword spaces to absorb whatever the line fell short by.

### Links render as ordinary prose

*(2026-10-07: true of the demo page and of the SVG artifacts, no longer true of
the library.)* `advtext/spans.py` maps a `LinkSpan`'s material indices to
shipped indices, and a `BareView` or `StreamView` constructed with `on_link`
underlines its links, colours them `Palette.link`, shows a hand cursor and
calls back on a press and release over the same link. The demo's `DocumentView`
is given no callback and draws links as it always did, which is deliberate: the
shipped page was not to change. The underline's offset and thickness are a
builder's choice that nobody has looked at. The paragraph below is the entry as
it stood.

`advtext.markdown.LinkSpan` records where every link is, in reading-order
indices, and **nothing consumes it** — outside `markdown.py` the only mentions in
the tree are two docstrings describing what a consumer would do. This is by
construction: `advtext.shipout` deliberately carries no colour, because colour
belongs to the backend. The consequence is that the document's links are
invisible. Closing it means matching `LinkSpan` ranges against command indices the
way selection highlighting already does.

### The list gutter cost the document a line

Widening `list_indent` from 1.5 em to 1.9 em, so a two-digit ordered marker stops
colliding with its own text, took **0.4 em off the measure of every list item**.
One item of `demo/sample.md` that used to fit on one line now breaks, and its
first line is set noticeably loose. Rasterised and looked at.

The builder reported this against their own work and named the better option they
did not take: sizing each list's gutter from its own widest marker, which would
give the sample's short list a *narrower* gutter than it started with and let the
item fit with room over. Better typography, more work, still open.

### The softness was real, the diagnosis in this file was wrong, and it is fixed

This entry used to say ship-out rounds to the pixel grid and then `draw` adds a
fractional `origin` from `get_cursor_screen_pos()`, defeating it. **Both halves
are wrong** and `docs/subpixel.md` is the measurement:

- `advtext.shipout.ship` takes no `px_per_inch` and did **no** pixel rounding at
  all, so there was nothing for a fractional origin to defeat. The comment in
  the `at()` closure that said ship-out had already rounded was load-bearing and
  false.
- The pen position never blurred anything either, because ImGui 1.92's
  `ImFont::RenderText` truncates it: `float x = IM_TRUNC(pos.x)`.

The real mechanism is one layer down. `ImFont::GetFontBaked(size)` bakes at
`floor(size + 0.5)` and then draws the baked bitmap scaled by
`size / baked_size`, and `baked_size_px` asks for a fractional size for five of
the six faces. So every quad was a non-integer number of pixels across —
**1734 of 1734 glyph quads in `demo/sample.md` were resampled between texels**,
a fixed non-zero phase per glyph rather than a random one per instance. Fixed by
asking ImGui for the size it was going to bake at anyway and rounding the pen
ourselves: 0 of 1734 after, solid-ink pixels in a band of body text 413 → 686.

What it did **not** fix is in `docs/subpixel.md` §6 and belongs here: interletter
gaps are quantised to whole pixels, which is intrinsic to integer snapping, and
so is the baseline-to-baseline distance. At 15 px body text a gap is 1-3 px, so
half a pixel of layout difference becomes a whole pixel of rendered difference.
The remedies are per-phase bitmaps, which ImGui cannot store, and fractional
placement, which the user excluded because it is blur.

**A third remedy was costed and is being taken as this is written.** Snapping
each *word's* origin rather than each glyph's takes word keys drawn at more than
one shape from 66 of 496 to 0, at the price of doubling worst-case glyph
displacement from 0.50 to 0.99 px and moving the rendered right edge of a
justified line from 0.49 to 0.79 px. That trades against this project's flagship
zero-residue margin claim, so it was left as a taste call; the user took it —
"I would take a little more rag on the right justification line if the text
looks better." **So the 0.50 px and 0.49 px figures above are the ones to
re-derive first**: `docs/subpixel.md` §6.1 is where they live.

### Per-paragraph reflow cost is strongly superlinear, and has got worse

Re-measured after `demo/sample.md` grew from 23 blocks to 37. A cold reflow at
420 pt costs **98.3 ms to compose, 7.1 ms to ship and 1.8 ms to index** —
107.1 ms against a 16.7 ms frame budget (`scripts/bench_reflow.py`, best of 5).
The previous figures were 82.9 / 5.4 / 1.3 for 89.7 ms. Composition is still the
whole problem.

**Read every timing in this section as ±60%.** This machine was running four
other jobs while these were taken (loadavg 4.15) and the same benchmark varied
between 25.9 ms and 45.1 ms across four runs of the identical measurement. The
figures quoted are the best observed, which is the right statistic for a
best-of-N benchmark and is still not a quiet machine. Re-run before you act on
one.

And the cost is not spread evenly: the largest paragraph is 635 nodes costing
26.4 ms at a 300 pt measure where 463 nodes cost 13.1 ms and 371 cost 11.8 ms.
"N blocks at ~4 ms each" is a misleading model. `break_paragraph` dominates
because `_evaluate` re-packs a trial line from scratch for every (breakpoint,
active node) pair. Delta nodes are the real fix and were deliberately not
implemented; this raises what they are worth rather than lowering it.

The per-block cache does **nothing** for a resize drag — zero hits across 185
consecutive 1 pt widths, measured and pinned by a test so the cache is never
mistaken for a resize fix. It earns its place on a partly-changed document: an
edit to one paragraph is 360 hits to 47 misses and 30.5 ms instead of 144 ms.

### Two consumers at two measures used to evict each other completely

`LayoutCache.rotate()` fired on every `compose_blocks` call and, by its own
docstring, "one pass that does not use it drops it". With a Document tab and a
Columns tab live at two different measures — or one routine composing at the
2-column then the 3-column measure inside one frame — every lookup missed and
every frame was a full reflow. Against a 107 ms cold reflow that is not slow,
it is unusable.

`rotate()` is gone; `begin_pass(key)` replaced it, and a cache constructed
`LayoutCache(resident_passes=3)` keeps three passes resident, which is what the
Columns tab wants. The residency number is a parameter rather than a constant
because the right value is "how many measures are live at once", and that is a
property of the caller.

### The sentence space is what the user pointed at, and it grows with the tolerance

`advtext.style.space_factor_after` implements TeX's `\sfcode`, so the space after
a full stop is wider than an interword space. That is correct and it is what TeX
does. What was not noticed is that **it is wider in the stretch as well as in the
natural width, and by a larger factor**. Measured on `demo/columns.md` at a
468 pt measure:

| | natural | stretch |
|---|---:|---:|
| word space | 3.96 px | 1.98 px |
| space after a full stop | 5.28 px (1.33×) | **5.94 px (3.00×)** |

So the rendered ratio is `(5.28 + 5.94g) / (3.96 + 1.98g)` at glue set `g`: it is
1.33× on a line that needs no stretch and tends to **3.00×** as the line gets
looser. On the line the user actually complained about it sets 2.35× wider than
its neighbours. On a line at glue set 0.89 it is 10.57 px against 5.73 px, 1.84×
— measured, not interpolated.

This is why **lowering the breaking tolerance does not fix what the user saw**.
The tolerance decides `g`; the sentence space then amplifies whatever `g` is by
up to three. A task is boarded for it and it is a one-line change in `style.py`,
but the change is a house-style decision — French spacing — and not a bug fix.

### The three-column measure is short, and how short depends on the window

The project's own floor, from Bringhurst by way of `page_for`, is **2.00
alphabets** (53-62 characters); the single column is set at 2.25. Measured
through `column_page` with the real theme, one alphabet being 207.55 px:

| available | 1 column | 2 columns | 3 columns |
|---|---|---|---|
| 1920 px (the WM clamp) | 2.25 | 2.25 | **1.99** |
| 1400 px | 2.25 | 2.20 | **1.43** |
| 1100 px | 2.25 | **1.71** | **1.11** |

So three columns is at the floor on a maximised window and well under it on
anything smaller, and **two columns breaks the floor too** below about 1300 px.
The demo's own default window is not 1920 px, so the case a reader sees first is
the bad one. (A boarded task records this as "1.51 alphabets at the clamp"; that
figure does not reproduce here and the table above is what does. The defect is
real and the single number was not.)

### No block boundary in this engine is a legal column break

Measured, not inferred, and it is the sharpest constraint on the Columns tab.
`vert_break` can only cut where §973 says it may, and the interline glue
`append_to_vlist` puts between two boxes is preceded by a box — which is legal —
but the material *inside* a block is a single vpacked box that the splitter
cannot enter. So a block is an atom: a long list, a table or a code fence taller
than a column cannot be split and will overhang.

The practical consequence is that a column-worthy document has to be written as
sustained paragraphs, which is what `demo/columns.md` is. `demo/sample.md` in
three columns puts glyphs outside the column for exactly this reason. Fixing it
properly means composing block interiors into the outer vertical list rather
than packing them first, which is a change to `advtext.ui` and not to
`advtext.columns`.

### One call has never been made by the suite, and the usual list is wrong four ways

`advtext.ui.app.run`, because `tests/conftest.py` forbids this suite from opening
a window and `tests/test_run_demo.py` therefore replaces `run` with a recorder.
That is the whole of it. Section 2 has the trace and the corrections to the
commonly-repeated version of this list, which has at different times wrongly
named `advtext/ui/document_view.py`, `DocumentView.draw` and the mouse handlers,
`imgui_draw`'s two debug functions, and `scripts/run_demo.py`.

The thing worth taking from four wrong versions of one list: **it was wrong every
time in the direction of claiming less coverage than existed**, and every
correction came from tracing rather than from reading. A "never executed" note in
a docstring ages badly and nothing makes a liar of it.

### Smaller, and real

- **A missing glyph is only counted when a face was bound.** When `fonts(face)`
  returns `None`, `draw` falls through to the three-argument `add_text` and never
  checks coverage, so a missing glyph is silently absent and `DrawStats.missing`
  stays zero. `None` is a deliberate, documented answer, so this is a hole in the
  reporting rather than a crash. The branch *is* executed —
  `tests/test_document_view.py` and `tests/test_bench_draw.py` pass
  `fonts=lambda face: None` on purpose — and no test asserts on `missing` while
  it is taken, so it is exercised and unexamined rather than unreached.
- **`advtext.ui.app._FACES` is a module global and `run` can be called twice.**
  This entry used to say nothing clears it, so a second `run` in one process
  would hold `ImFont`s belonging to a destroyed atlas. **`load_fonts` now clears
  it first** (`_FACES.clear()`, checked by reading 2026-10-06), so that hazard is
  closed on the path `run` takes. What is left is smaller: it is still a module
  global, nothing in the tree calls `run` twice, and no test does either, so the
  clearing is read rather than exercised.
- **Two unenforced contracts with silent failure modes.** `shipout.ship` and
  `imgui_draw.draw` must each be handed the *same* metrics the packing used.
  Nothing raises. The symptom is text at the wrong size, everywhere, with no
  error.
- **Table cells do not wrap.** A cell wider than its share overflows. That is
  `\halign`'s real problem and out of scope; the sample table is narrow enough
  that it does not bite. *(2026-10-07: they wrap now. A table wider than its
  measure breaks each cell as a paragraph at its column's width, first-fit,
  and a column keeps at least its longest word. It is not `\halign`: widths
  are apportioned from natural widths, then cells are broken, once. The sample
  table is 461.7 px naturally and fits the 467 px page measure, so the demo
  shows no wrapped cell until the window is narrowed. `tests/test_tables.py`.)*
- **`docs/decisions.md` records the "only `fontlib` may import fontTools"
  contract as currently violated. It is not — that was fixed and the note is
  stale.** `fontlib.glyph_set` is the public accessor the note asks for, and
  `backends/svg.py` forwards to it, opens no file and names no font. Its one
  remaining fontTools reference is a function-local import of `SVGPathPen`, a pen
  class rather than a parser. Checked by grepping the package: `fontlib.py` is
  the only module that imports fontTools for parsing.
- **The artifacts are large** — `markdown.svg` is 1.55 MB and
  `markdown-debug.svg` 1.76 MB, because every occurrence of every glyph carries
  its own outline. Deduplicating with `<use>` would cut it tenfold and make it
  much harder to read beside the command list that produced it.
- **96 px/inch is an assumption, and the display it is about has now been
  seen.** It has not been *measured* — nothing compares a rendered em against a
  physical inch. What can be said is that the document photographs at a
  plausible size beside the SVG of the same document, and that
  `verify_advances.uniform_ratio` reports no uniform 1.333× ratio, which is the
  form this bug would take.
- **The window manager silently clamps a screenshot to 1920 px.** Ask
  `make shot` for `--width 2400` and you get a 1920 px PNG with no warning from
  the WM; `scripts/shot.py` prints one. A comparison of two widths where both
  were above the clamp would be a comparison of one width with itself.
- **Nothing renders the column layout to SVG through `make svg`.**
  `artifacts/columns-2.svg` and `columns-3.svg` exist because somebody made them
  by hand; `scripts/render_litmus.py` writes five files and none of them is a
  column. So the newest capability in the tree is the one with no
  display-independent artifact.

---

## 5. Three families of tests that could not fail

This is the most transferable thing in the repository, so it gets its own
section. **Three separate families of vacuous tests have been found here** — two
by reviewers and one by the builder who wrote them. In every case the test looked
like protection and protected nothing, and in every case what caught it was the
same move.

**Attack the fixture, not the assertion.**

### 1. A uniform fake measure made "line height, not ink" unfalsifiable

*Found by a reviewer, by reading the fixture instead of the assertion.*

`tests/test_selection.py::test_every_rect_is_full_line_height_rather_than_the_ink_of_its_glyphs`
and its twin in `test_shipout.py` compared a line of lowercase against a line
with descenders, and asserted the two highlight to the same height. But the fake
measure gave **every codepoint identical extents**, so `_document("acem",
"gjpqy")` was geometrically identical to `_document("aaaa", "aaaaa")`. The
descender contrast was decorative. Under such a measure the box height *is* the
ink extent, so the two quantities the test existed to separate were the same
number.

Worse, the claim was false: a line really did take the ink of its tallest glyph,
while three separate docstrings said it did not. The fix was a discriminating
fixture with real ink classes, plus a strut, plus a **meta-test** —
`test_the_ink_fixture_gives_the_two_lines_genuinely_different_extents` — whose
comment reads "a fixture that quietly went uniform would leave it passing and
covering nothing. That happened here once already."

### 2. "The suite emits no `ResourceWarning`" would have passed either way

*Found by a reviewer, by running the claim three ways instead of reasoning about
it.*

The font descriptors really were leaked. The proposed regression test was that
`filterwarnings = ["error"]` would turn a stray `ResourceWarning` into a failure.
It would not: the warning fires from `_io.BufferedReader.__del__`, and **CPython
swallows exceptions raised in finalizers** — they print as `Exception ignored
in:` and never fail a test. Plain `pytest`, `PYTHONWARNINGS=always::ResourceWarning`
and `python -X dev -m pytest` all gave a clean silent run *with and without the
fix*.

The defect was real and the proposed pin was a no-op. What shipped instead
asserts the file object is closed, in a subprocess, because the warning arrives
after pytest has stopped converting warnings to errors:
`tests/test_fontmetrics.py::test_reading_metrics_and_outlines_leaves_no_unclosed_file_at_interpreter_exit`.

### 3. Three of five cache-key tests passed no matter what the key contained

*Found by the builder who wrote them, by ablation on its own key — the only one
of the three not caught by a reviewer.*

`LayoutCache`'s key carries five components. The builder dropped each one in turn
and re-ran, expecting a red test for each. **Three of the five stayed green.** The
shared test helper built a fresh `char_measure` closure per call, and
`LayoutCache` keys the measure by *identity* — so every lookup missed, the cache
never served anything, the "cached" and "uncached" results agreed trivially, and
the tests passed regardless of the key.

The helper now takes `measure` as a parameter, and its docstring says that is
load-bearing rather than tidy.

### A fourth, and the house habit it produced

`tests/test_badness.py::test_badness_divides_before_multiplying_once_t_is_too_large_to_scale`
used inputs both code paths agree on, so it held whether or not the divide-first
branch existed. The guard beside it derives the maximally separating input
(`s = 1663793`, `t = 7230891`), where TeX's path gives infinite badness and
multiply-first gives 8189 — infinite against finite, the largest disagreement
available, and the one that decides feasibility in `try_break`.

The habit shows up throughout now, and it is worth keeping: the SVG outline cache
asserts `first is second` because equality would also pass uncached; the culling
fixture is four sections long because at one section every cull is a no-op; the
sigma test compares glyph *names* because a scaled-up glyph passes a height
comparison; the 32-bit-`ImWchar` check asserts `is_glyph_in_font(0x12211)` is
**False**, because True would be indistinguishable from success.

### The newest instance, and the clearest

`tests/test_imgui_draw.py::test_rounding_advances_instead_of_positions_walks_a_line_off_its_margin`
**builds the wrong implementation on purpose and asserts that it fails.** The
tests beside it check that every glyph lands on the pixel grid; an
advance-rounding renderer — round each advance, then sum — produces integer
positions for every glyph and passes all of them, while walking the end of a
line up to 9.9 px off its margin. So the integrality tests on their own could
not tell the right implementation from the worst plausible wrong one, and the
control is what makes them mean something.

`tests/test_shot_all.py` is the same move applied to a `Makefile` variable:
`SHOT_TABS` named three tabs for a whole batch after the app grew to five, so
`make shot-all` exited 0 having silently skipped the two tabs the batch existed
to demonstrate. The test compares the list against the tab names
`App.gui` actually draws. A screenshot target that skips a tab and reports
success is a can't-fail test wearing different clothes.

---

## 6. The first three things to do next

**0. Before any of these, take the two cheap ones.** French spacing is one line
in `style.py` and removes the largest visible defect anyone has named. Raising
the three-column measure is arithmetic in `column_page`. Both are in section 4
with measurements, both are boarded, and neither needs any of the work below.

**1. Implement hyphenation.** This was item 3 and it is item 1 now, because the
thing that gated it has happened: the breaking tolerance has been reviewed and
the answer was that the loose lines are not acceptable. Raising `\tolerance`
was the workaround for having no hyphenation, and lowering it again without
hyphenation brings back seven overfull lines. So the decision to scope
hyphenation out is the decision that is now costing something visible, and
section 4 has the numbers at both the one-column and three-column measure.
Roughly 1000 lines with the worst interaction in TeX; `docs/tex-notes.md` flags
the trap and `docs/decisions.md` records why it was refused.

*(2026-10-07: item 2 is built. `python scripts/bench_draw.py --copies 1,2,4
--repeat 7` on a quiet machine gave a full draw of 15.9 ms and a culled draw
of 5.9 ms, and 13.7 and 5.1 ms on one later run, after a per-glyph import was
also hoisted out of `_glyph`; the text below is the item as it stood, with the
unmemoised figures. Item 1 is untouched. Before either, read `docs/adoption-plan.md`
section C, which is a longer and newer list of what is open.)*

**2. Memoise the per-glyph preamble in `imgui_draw._glyph`.** Drawing
`demo/sample.md` costs **26 ms per frame against a 16.7 ms budget** at best, and
39-45 ms on a loaded machine, with the layout fully cached and nothing
recomputed — so the widget misses 60fps sitting still. `scripts/bench_draw.py`
decomposes it: **ImGui's own work is 1.3-2.2 ms**, and the rest is our own
Python re-deriving, per glyph, values that are constant across the 71 runs the
document contains — `parse_font_key` re-parsing the same string,
`fontlib_metrics` re-resolving the same face, `baked_size_px` recomputing the
same ratio. This is the cheapest large win available and it changes no geometry.

Batching glyphs into fewer `add_text` calls is the intuitive fix and the
benchmark prices it at **0.05 ms against 1.3 ms** — i.e. it can only reclaim the
part ImGui was already doing cheaply, and it would cost the per-glyph
positioning that the measured advance disagreement exists to absorb. Culling is
already done and holds the frame at 9.4 ms however long the document gets — but
a 768 px window still costs 9.4 ms of a 16.7 ms budget, so the preamble is worth
fixing even with culling in place.

**3. Give the column splitter something to cut inside a block.** Section 4
records that no block boundary is a legal break, so a list or a table taller
than a column overhangs it. That is the one structural limit on the capability
this batch added, and it is a change to how `advtext.ui` composes rather than to
`advtext.columns`.

**Not on this list any more:** "run it on a machine with a display". It has been
run, `make shot` is how, and `docs/imgui-risks.md` item 2 — the item that was
*the* reason to want a display — turned out to have the wrong mechanism and has
been settled by measurement rather than by looking.

**Then, if performance still matters:** delta nodes in `try_break`, with the
brute-force optimality test watching. They are the fix for the 82% of composition
that `hpack` re-walking accounts for, and they are also the one change that would
silently alter *which* breakpoints win rather than failing loudly — which is
exactly why the enumeration test must be the thing that guards them.

---

## Provenance

*(2026-10-07.)* Section 0 and the dated notes were added by an agent closing
the adoption session. Of their figures, the suite count, the two draw timings
and the probe's 18 of 18 were re-run by that agent on the final tree; the rest
are quoted from `docs/adoption-plan.md`, which names who measured each. Nothing
else in this file was re-measured for that revision, and the sections it did
not touch are of their original date.

Every number in this document was re-measured against the working tree during the
gate that produced it, not copied from an earlier write-up. Where an earlier
figure could not be reproduced, `docs/litmus.md` says so and gives the method for
the replacement. This paragraph is here because the single most common defect
found in this project was a confident number nobody could re-derive.

Two things about this revision specifically:

- **The timings were taken on a loaded machine** and the same measurement varied
  by up to 1.7× between runs. Section 4 says so where it quotes one. A figure
  here is the best of N on a busy box, not a quiet-machine number.
- **One figure in circulation could not be reproduced and is not repeated.** A
  task specification recorded "39 of 144 lines past natural stretch" for
  `demo/columns.md` at a 468 pt measure. Counting `TextBlock` lines with
  `glue_sign == STRETCHING` and `glue_order == NORMAL`, the working tree gives
  8 of 58 at that measure and 61 of 130 at 262 pt. Neither the numerator nor the
  denominator matches, `demo/columns.md` was edited in the interval, and the
  method the original used is not recorded. The replacement figures and their
  method are in section 4.

r"""
What pptmstr, the first host, asked of the views (its P8, P12, P13, P19):
`imscribe.ui.typeset_view`.

- **P8** blocks a host made (`MarkdownText`, `MarkdownCode`) and a
  `Description` a host made are shown as given, and what is no block is a
  `TypeError` where it is handed over, never an empty 16 px gap.
- **P12** `code_overflow`: wrap, clip or grow, with `content_width`.
- **P13** `fixed_line_height`: one pitch for every line of a block.
- **P19** `table_widths="natural"`: a settled table as a stream held it.

Three children, as in `tests/test_typeset_view.py`:

1.  `_PLAIN`, **without the library** (the two variables removed, and a
    stand-in for the imported package, so it holds in both runs): what is
    taken and refused, what is described, and that no option changes a
    description unless it is set.
2.  `_SET`, **with it**, real ImGui frames and no window: what the library
    makes of each option, counted and measured.
3.  `_WINDOW`, **with it, in a real window** through `hello_imgui`: a view
    whose code grows, scrolled sideways by its host's child window, with the
    mouse queued through `io.add_*_event`.

Each child with the library says in its report whether `typesetter.module()`
and `ready()` held IN THE CHILD, at its start and at its end, and the fixture
fails when they did not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from imscribe import typesetter

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_FRAME = ["LayoutDocument", "DrawDocument", "GetDocumentSize"]


def _report_of(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, stdout
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    return report


# ---------------------------------------------------------------------------
# 1. Without the library
# ---------------------------------------------------------------------------

_PLAIN = r"""
import collections, dataclasses, json, sys
from imscribe import typesetter
from imscribe.description import (
    BLOCK_FIXED_LINE_HEIGHT, BLOCK_TABLE_HELD, KIND_CODE, KIND_HOST, KIND_PARAGRAPH, KIND_TABLE,
    BlockDescription, CellDescription, ColumnDescription, Description, LinkRow, RunDescription,
    StyleDescription, description_of, table_text,
)
from imscribe.theme import BlockKind, Theme
from imscribe import typeset_markdown
from imscribe.typeset_markdown import (
    MarkdownCode, MarkdownConverter, MarkdownRule, MarkdownStream, MarkdownText, parse_markdown,
)
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import CODE_OVERFLOWS, TABLE_WIDTHS, TypesetView

# Stands for the imported package: nothing below reaches the library.
typesetter._ts, typesetter._tried = object(), True
theme = Theme.build()
report = {}

def outcome(action):
    try:
        action()
        return ["taken", ""]
    except (TypeError, ValueError) as exc:
        return [type(exc).__name__, str(exc)]

def state(view):
    return [list(view.texts), view.revision, [b.kind for b in view._described], view.source]

# ---- P8: blocks a host made -------------------------------------------------------------
LITERAL = "$ rm **/*.py\n<div> `not code` [not](a link)\n\ttabbed"
PROSE = "exit **status** 1, see <String> and _this_"
code = MarkdownCode(theme.style(BlockKind.CODE), LITERAL)
note = MarkdownText(BlockKind.PARAGRAPH, theme.style(BlockKind.PARAGRAPH), PROSE)
view = TypesetView([note, code], theme=theme)
as_markdown = TypesetView(PROSE + "\n\n```\n" + LITERAL + "\n```\n", theme=theme)
report["host_blocks"] = {
    "texts": list(view.texts), "given": [PROSE, LITERAL],
    "kinds": [b.kind for b in view._described], "runs": [list(b.runs) for b in view._described],
    "links": list(view.links), "source": view.source, "source_of": view.source_of(0),
    "roles": [view.block_role(0), view.block_role(1)],
    "read_as_markdown": list(as_markdown.texts),
    "same_again": view.set_document([note, code]),
    "equal_again": view.set_document(
        [dataclasses.replace(note), MarkdownCode(theme.style(BlockKind.CODE), LITERAL)]),
}
before = (view.revision, len(view._described))
grown = view.set_document([note, dataclasses.replace(code, text=LITERAL + "\nmore"), note])
report["host_blocks"]["grown"] = [grown, view.revision - before[0], list(view.texts)[1:]]
mixed = TypesetView(list(parse_markdown("# Title\n\nText.\n", theme).blocks) + [code], theme=theme)
report["host_blocks"]["mixed"] = list(mixed.texts)

# ---- P8: what is no block is refused, with the view as it was ----------------------------
class Odd:
    pass

described_one = BlockDescription(kind=KIND_PARAGRAPH, text="described")
view = TypesetView([note, code], theme=theme)
was = state(view)
refused = {}
for name, bad in (
    ("an_object", [note, Odd()]),
    ("a_str", [note, "text"]),
    ("none", [None]),
    ("a_number", 7),
    ("bytes", b"abc"),
    ("one_block", code),
    ("one_description_block", described_one),
    ("a_block_description_in_blocks", [note, described_one]),
    ("with_blocks_attribute", type("Holder", (), {"blocks": [note, Odd(), code]})()),
    ("style_is_a_kind", [MarkdownCode(BlockKind.CODE, "x")]),
    ("text_is_bytes", [MarkdownCode(theme.style(BlockKind.CODE), b"x")]),
    ("kind_is_a_str", [MarkdownText("PARAGRAPH", theme.style(BlockKind.PARAGRAPH), "x")]),
    ("run_past_the_text", [dataclasses.replace(note, runs=(RunDescription(0, 999, 2),))]),
    ("runs_overlap", [dataclasses.replace(
        note, runs=(RunDescription(0, 6, 2), RunDescription(4, 8, 3)))]),
    ("run_is_a_tuple", [dataclasses.replace(note, runs=((0, 4, 2),))]),
    ("link_past_the_text", [dataclasses.replace(note, links=((0, 999, "u"),))]),
    ("indent_is_text", [dataclasses.replace(code, left_indent="wide")]),
):
    got = outcome(lambda bad=bad: view.set_document(bad))
    refused[name] = got + [state(view) == was]
report["refused"] = refused
report["refused_in_constructor"] = outcome(lambda: TypesetView([note, Odd()], theme=theme))
report["refused_by_set_theme"] = outcome(lambda: view.set_theme(theme, [Odd()]))

class OddStream:
    theme = theme
    revision = 1
    closed = False
    committed = ()
    def __init__(self, blocks):
        self.blocks = tuple(blocks)

report["refused_from_a_stream"] = outcome(lambda: TypesetStreamView(OddStream([note, Odd()])))
taken = TypesetStreamView(OddStream([note, code]))
report["a_stream_of_host_blocks"] = list(taken.texts)

# Nothing a host hands over is described as a Host block it did not ask for.
hosts = []
for document in ([note, code], PROSE, parse_markdown("| a |\n|---|\n| b |\n", theme)):
    hosts.append([b.kind for b in TypesetView(document, theme=theme)._described].count(KIND_HOST))
report["silent_hosts"] = hosts

# ---- P8: a description a host made ---------------------------------------------------------
styles = [StyleDescription(),
          StyleDescription(Face=5, Scale=0.9, LineHeight=1.25, Color=0xFF112233)]
rows = ((CellDescription("a"), CellDescription("bb")), (CellDescription("c"), CellDescription("d")))
blocks = [
    BlockDescription(kind=KIND_PARAGRAPH, text="see the link here",
                     runs=(RunDescription(8, 12, tag=7),)),
    BlockDescription(kind=KIND_CODE, text="x = 1\ny = 2", style=1),
    BlockDescription(kind=KIND_TABLE, text=table_text([["a", "bb"], ["c", "d"]]), rows=rows,
                     columns=(ColumnDescription(1), ColumnDescription(3))),
    BlockDescription(kind=KIND_HOST, text="a widget", extent=40.0),
]
links = [LinkRow(0, 8, 12, 7, "https://host.example")]
described = description_of(blocks, styles, links)
view = TypesetView(described, theme=theme)
given = {
    "blocks_as_given": [list(b) for b in view._described] == [list(b) for b in blocks],
    "styles": [list(s) for s in view._styles] == [list(s) for s in styles],
    "texts": list(view.texts), "tables": list(view.tables), "links": [list(r) for r in view.links],
    "target": [view.converter.link_target(7), view.converter.link_target(1)],
    "source": [view.source, view.source_of(0), view.selected_source()],
    "roles": [view.block_role(n) for n in range(4)],
    "blocks_property": list(view.blocks) == blocks,
    "same_again": view.set_document(described),
    "revision": view.revision,
}
# More blocks, and one more style after the ones on show: an edit of the end.
more = description_of(blocks + [BlockDescription(text="one more", style=2)],
                      styles + [StyleDescription(Scale=1.5)], links)
given["grown"] = [view.set_document(more), view.revision, list(view.texts)[-1],
                  [list(s) for s in view._styles] == [list(s) for s in more.styles]]
# Another style table: everything again.
other = description_of(blocks, [StyleDescription(Scale=2.0), styles[1]], links)
given["restyled"] = [view.set_document(other), view._styles[0].Scale, len(view._described)]
# A palette's roles are not laid over a description: a style keeps the ink it states.
from imscribe.ui.palette import DARK_PALETTE
view.set_palette(
    DARK_PALETTE.with_roles({BlockKind.CODE: 0xFF0102FF, BlockKind.PARAGRAPH: 0xFF0000FF}))
given["inks_kept"] = sorted({s.Color for s in view._styles})
# To markdown and back: nothing of the one kind is kept for the other.
given["to_markdown"] = [view.set_document("# Title\n\nText.\n"), list(view.texts), view.source,
                        type(view.converter).__name__]
given["and_back"] = [view.set_document(described), list(view.texts), view.source]
given["host_for_is_asked"] = []
asked = TypesetView(described, theme=theme,
                    host_for=lambda v, at, block: given["host_for_is_asked"].append(
                        type(block).__name__))
# The same object, grown in the host's hands: compared like any other, not taken for unchanged.
mutable = description_of(blocks, styles, links)
grown_view = TypesetView(mutable, theme=theme)
mutable.blocks.append(BlockDescription(text="appended in place"))
mutable.texts.append("appended in place")
given["grown_in_place"] = [grown_view.set_document(mutable), list(grown_view.texts)[-1],
                           grown_view.revision, grown_view.set_document(mutable)]
# The view's own choices are laid over a description's flags as over any blocks'.
given["flags_under_options"] = [b.flags for b in TypesetView(
    described, theme=theme, fixed_line_height=True, table_widths="natural")._described]
report["description"] = given

view = TypesetView(described, theme=theme)
was = state(view)
misfit = MarkdownConverter(theme).describe([Odd()])
wrong = {
    "misfits": misfit,
    "style_out_of_range": Description([BlockDescription(text="x", style=3)], styles, [], [], ["x"],
                                      collections.Counter(), collections.Counter()),
    "no_styles": Description([BlockDescription(text="x")], [], [], [], ["x"],
                             collections.Counter(), collections.Counter()),
    "texts_differ": Description([BlockDescription(text="x")], styles, [], [], ["y"],
                                collections.Counter(), collections.Counter()),
    "a_markdown_block": Description([note], styles, [], [], [PROSE],
                                    collections.Counter(), collections.Counter()),
}
report["description_refused"] = {
    name: outcome(lambda bad=bad: view.set_document(bad)) + [state(view) == was]
    for name, bad in wrong.items()
}
report["misfit_is_a_host_block"] = [misfit.blocks[0].kind == KIND_HOST, dict(misfit.misfits)]

# ---- The options: checked at the call, and nothing changes unless one is set ------------
SOURCE = (
    "# Title\n\nA paragraph.\n\n- an item\n\n```\ncode\n```\n\n| a | b |\n|---|---|\n| c | d |\n\n"
    "---\n\n$$\nx^2\n$$\n\nAfter $y$ inline.\n"
)
converted = MarkdownConverter(theme).describe(parse_markdown(SOURCE, theme, math=True).blocks)
def flags(**options):
    return [b.flags for b in TypesetView(SOURCE, theme=theme, math=True, **options)._described]
plain = flags()
report["options"] = options = {
    "kinds": [b.kind for b in converted.blocks],
    "default_is_the_converter_s": plain == [b.flags for b in converted.blocks],
    "fixed": [a ^ b for a, b in zip(plain, flags(fixed_line_height=True))],
    "natural": [a ^ b for a, b in zip(plain, flags(table_widths="natural"))],
    "grow": [a ^ b for a, b in zip(plain, flags(code_overflow="grow"))],
    "bits": [BLOCK_FIXED_LINE_HEIGHT, BLOCK_TABLE_HELD],
    "names": [list(CODE_OVERFLOWS), list(TABLE_WIDTHS)],
}
view = TypesetView(SOURCE, theme=theme, math=True)
options["defaults"] = [view.code_overflow, view.fixed_line_height, view.table_widths,
                       view.reader, view.content_width]
revision = view.revision
options["setters"] = [
    view.set_code_overflow("wrap"), view.set_code_overflow("grow"), view.code_overflow,
    view.revision - revision,
    view.set_fixed_line_height(False), view.set_fixed_line_height(True), view.fixed_line_height,
    view.set_table_widths("fitted"), view.set_table_widths("natural"), view.table_widths,
]
options["set_later"] = [a ^ b for a, b in zip(plain, [b.flags for b in view._described])]
options["texts_kept"] = list(view.texts) == converted.texts
view.set_fixed_line_height(False)
view.set_table_widths("fitted")
options["set_back"] = [b.flags for b in view._described] == plain
wrong = {}
for name, action in (
    ("overflow_word", lambda: TypesetView(SOURCE, theme=theme, code_overflow="scroll")),
    ("overflow_number", lambda: TypesetView(SOURCE, theme=theme, code_overflow=2)),
    ("fixed_number", lambda: TypesetView(SOURCE, theme=theme, fixed_line_height=1)),
    ("widths_word", lambda: TypesetView(SOURCE, theme=theme, table_widths="held")),
    ("widths_none", lambda: TypesetView(SOURCE, theme=theme, table_widths=None)),
    ("reader_word", lambda: TypesetView(SOURCE, theme=theme, reader="html")),
    ("set_overflow", lambda: view.set_code_overflow("Grow")),
    ("set_fixed", lambda: view.set_fixed_line_height("yes")),
    ("set_widths", lambda: view.set_table_widths(1)),
    ("set_document_reader", lambda: view.set_document(SOURCE, reader={"html_as_text": True})),
    ("stream_overflow", lambda: TypesetStreamView(MarkdownStream(theme), code_overflow="x")),
    ("stream_widths", lambda: TypesetStreamView(MarkdownStream(theme)).set_table_widths("natural")),
):
    wrong[name] = outcome(action)
options["wrong"] = wrong
options["after_wrong"] = [view.code_overflow, view.fixed_line_height, view.table_widths]
stream = MarkdownStream(theme)
stream.append(SOURCE)
stream.close()
streamed = TypesetStreamView(stream, fixed_line_height=True, code_overflow="grow")
options["stream"] = [streamed.fixed_line_height, streamed.code_overflow,
                     [b.flags & BLOCK_FIXED_LINE_HEIGHT for b in streamed._described]]

# ---- The reader is handed to parse_markdown untouched --------------------------------------
HTML = "A List<String> and a <div>.\n\nrm **/*.py\n"
reading = {"has_reader_options": hasattr(typeset_markdown, "ReaderOptions")}
if reading["has_reader_options"]:
    reader = typeset_markdown.ReaderOptions(html_as_text=True)
    seen = []
    real = sys.modules["imscribe.ui.typeset_view"].parse_markdown
    def spy(source, theme, **more):
        seen.append(dict(more))
        return real(source, theme, **more)
    sys.modules["imscribe.ui.typeset_view"].parse_markdown = spy
    default = TypesetView(HTML, theme=theme)
    with_reader = TypesetView(HTML, theme=theme, reader=reader)
    reading["passed"] = ["reader" in seen[0], seen[1].get("reader") is reader]
    reading["texts"] = [list(default.texts), list(with_reader.texts),
                        [b.text for b in parse_markdown(HTML, theme, reader=reader).blocks]]
    reading["same_string_other_reader"] = [
        default.set_document(HTML), default.set_document(HTML, reader=reader),
        list(default.texts) == list(with_reader.texts), default.reader is reader,
        default.set_document(HTML, reader=reader),
        default.set_document(HTML, reader=typeset_markdown.ReaderOptions(html_as_text=True)),
        default.set_document(HTML, reader=None), default.reader, list(default.texts)[0],
    ]
    # One options object for a settled view and a stream.
    stream = MarkdownStream(theme, reader=reader)
    for piece in (HTML[:9], HTML[9:30], HTML[30:]):
        stream.append(piece)
    stream.close()
    reading["stream_ends_as_the_view"] = (
        list(TypesetStreamView(stream).texts) == list(with_reader.texts))
    # set_theme reads the source again with the same reader.
    with_reader.set_theme(theme)
    reading["after_set_theme"] = seen[-1].get("reader") is reader
report["reader"] = reading
report["loaded"] = sorted(name for name in sys.modules if name.split(".")[0] == "imtypeset")
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def plain() -> dict[str, Any]:
    """
    `_PLAIN` in a child with the two variables removed, so it holds in both runs.

    `typesetter._ts` is given a stand-in there: what is under test is what a
    view takes, refuses and describes, none of which reaches the library.
    """
    env = {key: value for key, value in os.environ.items() if key not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _PLAIN],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["loaded"] == [], "the child imported imtypeset"
    return got


def test_blocks_a_host_made_are_shown_as_their_text_and_not_read_as_markdown(
    plain: dict[str, Any],
) -> None:
    """
    pptmstr's P8: tool output and a literal tail are not markdown. A
    `MarkdownText` and a `MarkdownCode` a host built are described with the
    text they were given, to the character, and no run: the stars, the tag,
    the backticks and the brackets are all there. The same characters read
    as markdown lose them (the mutation: this is what a `str` would do).
    """
    told = plain["host_blocks"]
    assert told["texts"] == told["given"]
    assert told["kinds"] == [0, 3] and told["runs"] == [[], []] and told["links"] == []
    assert told["read_as_markdown"][0] == "exit status 1, see  and _this_"
    assert told["read_as_markdown"] != told["given"]
    # No source map for blocks nobody parsed; the roles are still the blocks' own.
    assert told["source"] is None and told["source_of"] is None
    assert told["roles"] == ["PARAGRAPH", "CODE"]


def test_host_blocks_are_edited_as_any_blocks_and_mix_with_parsed_ones(
    plain: dict[str, Any],
) -> None:
    """
    The same objects again are nothing, and so are equal ones made anew
    (they are frozen values); a list whose second block grew and that gained
    a third is ONE change. A host's blocks and `parse_markdown`'s are the
    same types and go in one sequence.
    """
    told = plain["host_blocks"]
    assert told["same_again"] is False and told["equal_again"] is False
    changed, revisions, texts = told["grown"]
    assert changed is True and revisions == 1
    assert texts[0].endswith("\nmore") and texts[1] == told["given"][0]
    assert told["mixed"] == ["Title", "Text.", told["given"][1]]


@pytest.mark.parametrize(
    ("name", "error", "says"),
    [
        ("an_object", "TypeError", "block 1 is a Odd"),
        ("a_str", "TypeError", "block 1 is a str"),
        ("none", "TypeError", "block 0 is a NoneType"),
        ("a_number", "TypeError", "not a int"),
        ("bytes", "TypeError", "not a bytes"),
        ("one_block", "TypeError", "one MarkdownCode is not a document"),
        ("one_description_block", "TypeError", "one BlockDescription is not a document"),
        ("a_block_description_in_blocks", "TypeError", "imscribe.description.Description"),
        ("with_blocks_attribute", "TypeError", "block 1 is a Odd"),
        ("style_is_a_kind", "TypeError", "block 0 (MarkdownCode): style is a BlockKind"),
        ("text_is_bytes", "TypeError", "block 0 (MarkdownCode): text is a bytes"),
        ("kind_is_a_str", "TypeError", "kind is 'PARAGRAPH'"),
        ("run_past_the_text", "ValueError", "run 0 is [0, 999)"),
        ("runs_overlap", "ValueError", "run 1 starts at 4"),
        ("run_is_a_tuple", "TypeError", "run 0 is a tuple"),
        ("link_past_the_text", "ValueError", "link 0 is [0, 999)"),
        ("indent_is_text", "TypeError", "left_indent is 'wide'"),
    ],
)
def test_what_is_no_block_is_refused_at_the_call_naming_its_type_and_number(
    plain: dict[str, Any], name: str, error: str, says: str
) -> None:
    """
    pptmstr's P8, the other half: until 2026-10-12 each of the first few was
    described as an EMPTY Host block 16 px tall and drawn as a gap without a
    word. Now `set_document` raises, the message names the type and the
    block's number, and the view is as it was (texts, revision, kinds,
    source). A block of the right type whose fields are wrong is refused the
    same way, before a converter or the library meets it.
    """
    raised, message, unchanged = plain["refused"][name]
    assert raised == error, message
    assert says in message, message
    assert unchanged is True


def test_every_way_in_refuses_it_and_no_host_block_appears_unasked(plain: dict[str, Any]) -> None:
    """
    The constructor, `set_theme(theme, document)` and a stream view's stream
    (at the `sync` its constructor makes) are held to the same rule. And of
    three documents a view accepts -- a host's blocks, a string, a parsed
    table -- none is described with a Host block in it.
    """
    for name in ("refused_in_constructor", "refused_by_set_theme", "refused_from_a_stream"):
        raised, message = plain[name]
        assert raised == "TypeError" and "is a Odd" in message, (name, message)
    assert plain["a_stream_of_host_blocks"] == plain["host_blocks"]["given"]
    assert plain["silent_hosts"] == [0, 0, 0]
    # What the converter itself still does with one, which a view refuses:
    assert plain["misfit_is_a_host_block"] == [True, {"block type Odd": 1}]


def test_a_description_a_host_made_is_used_as_it_is_given(plain: dict[str, Any]) -> None:
    """
    pptmstr's P8: a view that takes a `Description`. Its blocks reach the
    view's own record field for field (styles, a tagged run, a table with
    its columns, a `KIND_HOST` block it asked for), its style table is the
    view's, its links answer `links` and the tag's target, and its tables
    are known. What the view cannot do for it is said, not guessed: no
    source, no role.
    """
    told = plain["description"]
    assert told["blocks_as_given"] is True and told["styles"] is True
    assert told["blocks_property"] is True
    assert told["texts"] == ["see the link here", "x = 1\ny = 2", "a\tbb\nc\td", "a widget"]
    assert told["tables"] == [2]
    assert told["links"] == [[0, 8, 12, 7, "https://host.example"]]
    assert told["target"] == ["https://host.example", None]
    assert told["source"] == [None, None, ""]
    assert told["roles"] == ["", "", "", ""]
    assert told["same_again"] is False and told["revision"] == 1
    assert told["host_for_is_asked"] == ["BlockDescription"] * 4
    # Text and code take the pitch, the table is held, the Host block neither.
    assert told["flags_under_options"] == [8, 8, 32, 0]


def test_a_description_given_again_is_an_edit_or_a_new_document_by_its_styles(
    plain: dict[str, Any],
) -> None:
    """
    With more blocks and a style table that begins with the one on show, the
    description is an edit of what differs (one revision, the new style
    added); with another table everything is described again. A palette's
    role inks are not laid over it: the styles keep the two inks they state.
    And a view goes from a description to markdown and back, keeping nothing
    of the one for the other.
    """
    told = plain["description"]
    assert told["grown"] == [True, 2, "one more", True]
    assert told["grown_in_place"] == [True, "appended in place", 2, False]
    assert told["restyled"] == [True, 2.0, 4]
    assert told["inks_kept"] == [0, 0xFF112233]
    changed, texts, source, converter = told["to_markdown"]
    assert changed is True and texts == ["Title", "Text."] and source == "# Title\n\nText.\n"
    assert converter == "MarkdownConverter"
    changed, texts, source = told["and_back"]
    assert changed is True and texts[0] == "see the link here" and source is None


@pytest.mark.parametrize(
    ("name", "error", "says"),
    [
        ("misfits", "ValueError", "block type Odd"),
        ("style_out_of_range", "ValueError", "style is 3"),
        ("no_styles", "ValueError", "0 style(s)"),
        ("texts_differ", "ValueError", "Description.texts"),
        ("a_markdown_block", "TypeError", "block 0 is a MarkdownText"),
    ],
)
def test_a_description_that_cannot_be_shown_is_refused_at_the_call(
    plain: dict[str, Any], name: str, error: str, says: str
) -> None:
    """
    `check_description` runs where the description is handed over. One made
    by a converter that did not know a block (`misfits`) is refused: that is
    the silent gap, coming in by the other door.
    """
    raised, message, unchanged = plain["description_refused"][name]
    assert raised == error and says in message, message
    assert unchanged is True


def test_no_option_changes_a_description_unless_it_is_set(plain: dict[str, Any]) -> None:
    """
    Defaults do not change: a view with no option describes exactly what
    `MarkdownConverter` does. `fixed_line_height` adds the library's flag
    to the heading, the paragraphs, the list item and the code, and NOT to
    the table, the rule or the display formula; `table_widths="natural"`
    adds the held flag to the table alone; `code_overflow` is no flag at all.
    """
    told = plain["options"]
    assert told["default_is_the_converter_s"] is True
    fixed, held = told["bits"]
    assert (fixed, held) == (8, 32)
    #                     heading, paragraph, item, code, table, rule, $$, paragraph
    assert told["kinds"] == [1, 0, 2, 3, 6, 4, 0, 0]
    assert told["fixed"] == [fixed, fixed, fixed, fixed, 0, 0, 0, fixed]
    assert told["natural"] == [0, 0, 0, 0, held, 0, 0, 0]
    assert told["grow"] == [0] * 8
    assert told["names"] == [["wrap", "clip", "grow"], ["fitted", "natural"]]
    assert told["defaults"] == ["wrap", False, "fitted", None, 0.0]


def test_each_option_has_a_setter_and_is_checked_where_it_is_given(plain: dict[str, Any]) -> None:
    """
    A setter answers whether anything changed. The overflow describes
    nothing again (no revision); the two flags describe every block again,
    with the same texts. Each wrong value is a `ValueError` (a word that is
    not one of them) or a `TypeError` (anything else) at the call, in the
    constructor and the setter alike, in a stream view too, and leaves the
    view as it was. A stream view's tables are its stream's policy.
    """
    told = plain["options"]
    assert told["setters"] == [False, True, "grow", 0, False, True, True, False, True, "natural"]
    fixed, held = told["bits"]
    assert told["set_later"] == [fixed, fixed, fixed, fixed, held, 0, 0, fixed]
    assert told["texts_kept"] is True and told["set_back"] is True
    kinds = {name: got[0] for name, got in told["wrong"].items()}
    assert kinds == {
        "overflow_word": "ValueError",
        "overflow_number": "TypeError",
        "fixed_number": "TypeError",
        "widths_word": "ValueError",
        "widths_none": "TypeError",
        "reader_word": "TypeError",
        "set_overflow": "ValueError",
        "set_fixed": "TypeError",
        "set_widths": "TypeError",
        "set_document_reader": "TypeError",
        "stream_overflow": "ValueError",
        "stream_widths": "TypeError",
    }
    assert told["after_wrong"] == ["grow", False, "fitted"]
    assert told["stream"][:2] == [True, "grow"]
    assert told["stream"][2] == [fixed, fixed, fixed, fixed, 0, 0, fixed, fixed]


def test_the_reader_is_handed_to_parse_markdown_untouched(plain: dict[str, Any]) -> None:
    """
    Interface 1 of the tranche: one `ReaderOptions` for a settled view and a
    stream. A view with none names no `reader` to `parse_markdown` at all
    (the call it always made); one with some passes that very object, and
    reads what `parse_markdown` reads with it. The same string with other
    options is read again; with equal options, or the same, it is nothing;
    `reader=None` goes back to CommonMark's reading. A stream given the same
    options ends as the view's texts.
    """
    told = plain["reader"]
    if not told["has_reader_options"]:
        pytest.skip("imscribe.typeset_markdown has no ReaderOptions in this tree")
    assert told["passed"] == [False, True]
    default, with_reader, parsed = told["texts"]
    assert with_reader == parsed and default != with_reader
    assert "<String>" in with_reader[0] and "<String>" not in default[0]
    same, other, equal, kept, again, equal_options, back, reader, text = told[
        "same_string_other_reader"
    ]
    assert (same, other, equal, kept) == (False, True, True, True)
    assert (again, equal_options) == (False, False)
    assert back is True and reader is None and text == default[0]
    assert told["stream_ends_as_the_view"] is True and told["after_set_theme"] is True


# ---------------------------------------------------------------------------
# 2. With the library: real ImGui frames, no window
# ---------------------------------------------------------------------------

_SET = r"""
import json, struct, sys
from pathlib import Path

from imgui_bundle import imgui

from imscribe import typesetter
from imscribe.description import (
    BLOCK_FIXED_LINE_HEIGHT, BLOCK_TABLE_HELD, KIND_CODE, KIND_HOST, KIND_PARAGRAPH, KIND_TABLE,
    BlockDescription, CellDescription, ColumnDescription, LinkRow, RunDescription,
    StyleDescription, description_of, table_text,
)
from imscribe.theme import BlockKind, Theme
from imscribe.typeset_markdown import MarkdownCode, MarkdownStream, MarkdownText
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_hosts import TypesetDiffFences
from imscribe.ui.typeset_stream_view import TypesetStreamView
from imscribe.ui.typeset_view import CODE_OVERFLOWS, TypesetUnavailable, TypesetView

report = {"module": typesetter.module() is not None,
          "load_start": open("/proc/loadavg").read().split()[:3]}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(900.0, 700.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()
report["reason"] = typesetter.reason()
ts = typesetter.module()
calls = []

class Counting:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)
    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            calls.append(name.replace("ImTypeset_", ""))
            return attr(*args, **kwargs)
        return call

ts._lib = Counting(ts._lib)
PARKED = (880.0, 680.0)

def frame(view, *, mouse=None, button=None, scroll_x=None, scroll_y=None, name="##text",
          width=None):
    # One frame of the view in a child that scrolls both ways, as wide as the pane.
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(*mouse)
    if button is not None:
        io.add_mouse_button_event(0, button)
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(460.0, 640.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child(name, imgui.ImVec2(0.0, 0.0), 0,
                          imgui.WindowFlags_.horizontal_scrollbar.value)
        try:
            if scroll_x is not None:
                imgui.set_scroll_x(scroll_x)
            if scroll_y is not None:
                imgui.set_scroll_y(scroll_y)
            calls.clear()
            answered = view.draw(width_px=width)
            hit = view.under_mouse
            return {"answered": answered, "calls": list(calls), "vertices": view.stats.vertices,
                    "scroll_x": imgui.get_scroll_x(), "scroll_max_x": imgui.get_scroll_max_x(),
                    "origin": list(view.origin), "width": view.width,
                    "content_width": view.content_width, "column_width": view.column_width,
                    "item": [imgui.get_item_rect_size().x, imgui.get_item_rect_size().y],
                    "pane": [imgui.get_window_pos().x, imgui.get_window_size().x],
                    "selection": view.selection, "scrolled": view.scrolled,
                    "hit": None if hit is None else [int(hit.position[0]), int(hit.position[1])],
                    "hovered": view.hovered_link}
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()

def at_char(view, position):
    # Just inside the left edge of the character at `position`, on screen.
    x0, y0, _, y1 = view.native_document.caret_rect(position)
    ox, oy = view.origin
    return (ox + x0 + 1.5, oy + (y0 + y1) / 2.0)

def colours(view):
    doc = view.native_document
    vertices, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, 100000.0, 100000.0), marks=view._marks_for(doc))
    return sorted(
        {struct.unpack_from("<I", vertices, at + 16)[0] for at in range(0, len(vertices), 20)})

def xs_of(view, colour):
    # The x of every vertex drawn in `colour`, from the document's corner.
    doc = view.native_document
    vertices, _ = doc.draw_to_buffers(
        (0.0, 0.0), (0.0, 0.0, 100000.0, 100000.0), marks=view._marks_for(doc))
    return sorted(struct.unpack_from("<f", vertices, at)[0]
                  for at in range(0, len(vertices), 20)
                  if struct.unpack_from("<I", vertices, at + 16)[0] == colour)

def lines_of(view, block):
    return [line for line in view.set_lines(block, block + 1)]

theme = Theme.build()
report["enumerators"] = {
    "overflow": [int(ts.CodeOverflow.Wrap), int(ts.CodeOverflow.Clip), int(ts.CodeOverflow.Grow)],
    "names": list(CODE_OVERFLOWS),
    "flags": [[int(ts.BlockFlags.FixedLineHeight), BLOCK_FIXED_LINE_HEIGHT],
              [int(ts.BlockFlags.TableHeld), BLOCK_TABLE_HELD]],
}

# ---- P8: a host's blocks, and a host's description, drawn -----------------------------------
LITERAL = "$ rm **/*.py\n<div> `not code` [not](a link)"
PROSE = "exit **status** 1, see <String> and _this_"
view = TypesetView(
    [MarkdownText(BlockKind.PARAGRAPH, theme.style(BlockKind.PARAGRAPH), PROSE),
     MarkdownCode(theme.style(BlockKind.CODE), LITERAL)], theme=theme, palette=DARK_PALETTE)
frame(view, mouse=PARKED)
out = frame(view)
view.select_all()
report["host_blocks"] = {"answered": out["answered"], "vertices": out["vertices"],
                         "calls": out["calls"], "copied": view.selected_text(),
                         "expected": view.separator.join([PROSE, LITERAL]),
                         "lines": [len(lines_of(view, 0)), len(lines_of(view, 1))]}
view.close()

INK = 0xFF112233
styles = [StyleDescription(), StyleDescription(Face=5, Scale=0.9, LineHeight=1.25, Color=INK)]
rows = ((CellDescription("a"), CellDescription("bb")), (CellDescription("c"), CellDescription("d")))
blocks = [
    BlockDescription(kind=KIND_PARAGRAPH, text="see the link here",
                     runs=(RunDescription(8, 12, tag=7),)),
    BlockDescription(kind=KIND_CODE, text="x = 1\ny = 2", style=1),
    BlockDescription(kind=KIND_TABLE, text=table_text([["a", "bb"], ["c", "d"]]), rows=rows,
                     columns=(ColumnDescription(1), ColumnDescription(3))),
    BlockDescription(kind=KIND_HOST, text="a widget", extent=40.0),
]
clicked = []
view = TypesetView(description_of(blocks, styles, [LinkRow(0, 8, 12, 7, "https://host.example")]),
                   theme=theme, palette=DARK_PALETTE, on_link=clicked.append)
frame(view, mouse=PARKED)
first = frame(view)
over = [frame(view, mouse=at_char(view, (0, 9))), frame(view)]
frame(view, button=True)
frame(view)
frame(view, button=False)
frame(view)
frame(view, mouse=PARKED)
geometry = view.table_geometry(2)
host = view.block_rect(3)
view.select_all()
report["description"] = {
    "answered": first["answered"], "vertices": first["vertices"], "calls": first["calls"],
    "hovered": over[1]["hovered"], "clicked": list(clicked),
    "table": [geometry.row_count, geometry.column_count],
    "ink": INK in colours(view), "host_height": host[3] - host[1],
    "copied": view.selected_text(), "expected": view.separator.join(b.text for b in blocks),
    "edit_error": view.native_document.edit_error.code,
}
view.close()

# ---- P12: code overflow ------------------------------------------------------------------
PARAGRAPH = "some prose that is long enough to be broken into lines at the width of the pane\n\n"
LONG = "x" * 400
GROW = PARAGRAPH + "```\nshort\n" + LONG + "\n```\n\n" + PARAGRAPH
overflow = {}
for mode in CODE_OVERFLOWS:
    view = TypesetView(GROW, theme=theme, palette=DARK_PALETTE, code_overflow=mode)
    first = frame(view, mouse=PARKED, name="##" + mode)
    steady = [frame(view, name="##" + mode) for _ in range(3)]
    code = view.native_document.block_geometry(1)
    overflow[mode] = {
        "first": first["calls"], "steady": [one["calls"] for one in steady],
        "content_width": steady[-1]["content_width"], "width": steady[-1]["width"],
        "column_width": steady[-1]["column_width"], "item": steady[-1]["item"],
        "scroll_max_x": steady[-1]["scroll_max_x"], "pane": steady[-1]["pane"],
        "code_lines": len(lines_of(view, 1)), "prose_lines": len(lines_of(view, 0)),
        "code_right": code.max[0], "code_left": code.min[0],
        "document_size": list(view.native_document.size()),
        "answered": steady[-1]["answered"],
    }
    if mode != "grow":
        view.close()
report["overflow"] = overflow

# The view left open is the one that grows: drawn at a negative x under the pane's clip.
name = "##grow"
x0 = view.native_document.caret_rect((1, 6))[0]
cell = (view.native_document.caret_rect((1, 6 + 100))[0] - x0) / 100.0
still = frame(view, name=name)
frame(view, name=name, scroll_x=1000.0)
moved = frame(view, name=name)
frame(view, name=name, mouse=at_char(view, (1, 6 + 140)))
hover = frame(view, name=name)
frame(view, name=name, button=True)
frame(view, name=name)
frame(view, name=name, mouse=at_char(view, (1, 6 + 170)))
frame(view, name=name)
frame(view, name=name, button=False)
dragged = frame(view, name=name)
text = view.selected_text()
view.clear_selection()
frame(view, name=name, mouse=PARKED)
MARK = 0xFF0103FE
plain_vertices = frame(view, name=name)["vertices"]
view.set_marks([ts.Mark(((1, 6 + 150), (1, 6 + 160)), MARK, ts.MarkPlace.Behind)])
marked = frame(view, name=name)
rects = view.span_rects(1, 6 + 150, 6 + 160)
mark_xs = xs_of(view, MARK)
view.set_marks(None)
INKED = 0xFF0507FD
view.set_colours(1, [(6 + 390, 6 + 400, INKED)])
frame(view, name=name)
inked = frame(view, name=name)
ink_xs = xs_of(view, INKED)
ink_drawn = int(view._drawn_marks.count) if view._drawn_marks else 0
view.clear_colours()
# scroll_to an offset far along the line, from the left edge.
frame(view, name=name, scroll_x=0.0)
home = frame(view, name=name)
view.scroll_to(1, 6 + 395)
asked = frame(view, name=name)
for _ in range(5):
    arrived = frame(view, name=name)
caret = view.native_document.caret_rect((1, 6 + 395))[0] + arrived["origin"][0]
report["scrolled_sideways"] = {
    "cell": cell, "code_left": x0, "still": still, "moved": moved,
    "hover": hover["hit"], "hover_calls": hover["calls"], "wanted": [1, 6 + 140],
    "selection": dragged["selection"], "text": text,
    "vertices": [plain_vertices, marked["vertices"]], "mark_rects": rects,
    "mark_xs": [mark_xs[0], mark_xs[-1]] if mark_xs else [],
    "ink_xs": [ink_xs[0], ink_xs[-1]] if ink_xs else [], "ink_drawn": ink_drawn,
    "inked_calls": inked["calls"],
    "home": home["scroll_x"], "asked_scrolled": asked["scrolled"],
    "arrived": arrived["scroll_x"], "caret_on_screen": caret, "pane": arrived["pane"],
}
# Changed while it is on show: one set_options, and the code is wrapped again.
view.set_code_overflow("wrap")
frame(view, name=name, scroll_x=0.0)
change = frame(view, name=name)
wrapped = [change["content_width"], change["column_width"], len(lines_of(view, 1)),
           change["scroll_max_x"]]
view.set_code_overflow("grow")
back = frame(view, name=name)
report["overflow_changed"] = {
    "wrapped": wrapped, "wrap_calls": change["calls"],
    "back_calls": back["calls"], "back": [back["content_width"], len(lines_of(view, 1))],
}
view.close()

# A hosted diff with a long line is the diff view's to scroll: it adds nothing to the content.
HOSTED = PARAGRAPH + "```diff\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-" + LONG + "\n+y\n```\n"
view = TypesetView(HOSTED, theme=theme, palette=DARK_PALETTE, code_overflow="grow",
                   host_for=TypesetDiffFences())
frame(view, name="##hosted", mouse=PARKED)
for _ in range(3):
    out = frame(view, name="##hosted")
widget = view.hosted(1)
report["hosted"] = {
    "content_width": out["content_width"], "column_width": out["column_width"],
    "scroll_max_x": out["scroll_max_x"], "hosts": list(view.hosts), "drawn": view.hosts_drawn,
    "kind": view._described[1].kind, "widget": type(widget).__name__,
    "widget_content_width": float(getattr(getattr(widget, "view", widget), "content_width", 0.0)),
    "calls": out["calls"],
}
view.close()

# A stream whose code grows: the content follows it, one question a changed code block.
stream = MarkdownStream(theme)
view = TypesetStreamView(stream, palette=DARK_PALETTE, code_overflow="grow", follow=False)
stream.append(PARAGRAPH + "```\nshort\n")
frame(view, name="##stream", mouse=PARKED)
frame(view, name="##stream")
widths, asked = [], []
for piece in ("y" * 30, "y" * 60, "y" * 90 + "\n", "z" * 300 + "\n```\n\nafter\n"):
    stream.append(piece)
    out = frame(view, name="##stream")
    widths.append(out["content_width"])
    asked.append(out["calls"].count("GetDocumentBlockGeometry"))
steady = frame(view, name="##stream")
report["stream_grows"] = {"widths": widths, "asked": asked, "steady": steady["calls"],
                          "column_width": steady["column_width"], "edits": dict(view.edits)}
view.close()

# ---- P13: one pitch -------------------------------------------------------------------------
TREE = "├── a\n│   └── b\nÉcole Ångström\nplain\n█▀▄ blocks\nlast"
TALL = ("```\n" + TREE + "\n```\n\nA paragraph with École and │ a box rule in it, long enough to "
        "be broken into several lines so that the lines can be compared, Ångström │ ├── "
        "again and plain.\n\n- an item with █ in it that is long enough to be broken into two "
        "lines at this width\n")
pitch = {}
for name, fixed in (("natural", False), ("fixed", True)):
    view = TypesetView(TALL, theme=theme, palette=DARK_PALETTE, fixed_line_height=fixed)
    frame(view, name="##" + name, mouse=PARKED)
    out = frame(view, name="##" + name)
    per = []
    for block in range(len(view.texts)):
        lines = lines_of(view, block)
        per.append({"tops": [round(line.top - lines[0].top, 3) for line in lines],
                    "heights": [round(line.bottom - line.top, 3) for line in lines]})
    pitch[name] = {"blocks": per, "height": view.height, "answered": out["answered"],
                   "calls": out["calls"], "flags": [b.flags for b in view._described]}
    view.close()
report["pitch"] = pitch
# A view of one block a host made, capped at N pitches: does the cap fall on a line's foot?
capped = {}
for name, fixed in (("natural", False), ("fixed", True)):
    view = TypesetView([MarkdownCode(theme.style(BlockKind.CODE), TREE)], theme=theme,
                       fixed_line_height=fixed)
    frame(view, name="##cap" + name, mouse=PARKED)
    frame(view, name="##cap" + name)
    lines = lines_of(view, 0)
    capped[name] = {"top": lines[0].top, "feet": [line.bottom - lines[0].top for line in lines],
                    "line_height": view._styles[view._described[0].style].LineHeight,
                    "scale": view._styles[view._described[0].style].Scale}
    view.close()
report["capped"] = capped
report["em"] = float(typesetter.base_style(theme, 0).EmSize)

# ---- P19: a settled table as a stream held it ---------------------------------------------
def columns_of(view, at):
    geometry = view.table_geometry(at)
    return {"stated": geometry.stated,
            "edges": [[c.min, c.max] for c in
                      (view.table_column(at, n) for n in range(geometry.column_count))],
            "natural": [view.table_column(at, n).natural for n in range(geometry.column_count)],
            "table": [geometry.min[0], geometry.max[0]]}

def settled(source, **options):
    view = TypesetView(source, theme=theme, palette=DARK_PALETTE, **options)
    frame(view, name="##settled", mouse=PARKED)
    frame(view, name="##settled")
    got = columns_of(view, view.tables[0])
    got["flags"] = view._described[view.tables[0]].flags
    got["column_width"] = view.column_width
    view.close()
    return got

def streamed(source, step):
    stream = MarkdownStream(theme)
    view = TypesetStreamView(stream, palette=DARK_PALETTE, follow=False)
    frame(view, name="##streamed", mouse=PARKED)
    for at in range(0, len(source), step):
        stream.append(source[at:at + step])
        frame(view, name="##streamed")
    stream.close()
    frame(view, name="##streamed")
    frame(view, name="##streamed")
    got = columns_of(view, view.tables[0])
    got["keeps"] = view.keeps_streamed()
    got["source"] = stream.source == source
    view.close()
    return got

tables = {}
for name, source in (
    ("pptmstr", "| name | value |\n|---|---|\n| a | 1 |\n| bb | 22 |\n"),
    ("after_prose", PARAGRAPH + "| name | where it goes |\n|:--|--:|\n| alpha glue | gamma |\n"
                    "| beta | delta epsilon |\n\nAfter the table.\n"),
    ("markup_closing_late", "| name | value |\n|---|---|\n| **bold words** | `code` |\n"
                            "| b | 2 |\n"),
    ("too_wide", "| one | two |\n|---|---|\n| " + "many words in a cell " * 8 + "| "
                 + "and as many in the other " * 8 + "|\n"),
):
    tables[name] = {"whole": streamed(source, len(source)), "by_threes": streamed(source, 3),
                    "natural": settled(source, table_widths="natural"),
                    "fitted": settled(source)}
report["tables"] = tables
# Where a cell was wider while it was written than it ended, the stream's widths are stated.
late = tables["markup_closing_late"]
view = TypesetView("| name | value |\n|---|---|\n| **bold words** | `code` |\n| b | 2 |\n",
                   theme=theme, palette=DARK_PALETTE, table_widths="natural")
frame(view, name="##carried", mouse=PARKED)
calls.clear()
changed = view.set_table_columns(0, [right - left for left, right in late["by_threes"]["edges"]])
stated_calls = list(calls)
frame(view, name="##carried")
report["carried"] = columns_of(view, 0)
report["carried"].update(changed=changed, calls=stated_calls, flags=view._described[0].flags)
calls.clear()
view.set_table_columns(0, None)
back_calls = list(calls)
frame(view, name="##carried")
report["carried_back"] = columns_of(view, 0)
report["carried_back"].update(calls=back_calls, flags=view._described[0].flags)
view.close()
# A table DESCRIBED with widths is the host's too, and is never held.
import dataclasses
from imscribe.typeset_markdown import parse_markdown
from imscribe.primitives import sp_from_px
(parsed,) = parse_markdown("| a | b |\n|---|---|\n| one | two |\n", theme).blocks
sized = dataclasses.replace(parsed, widths=(sp_from_px(120.0, theme.px_per_inch),
                                            sp_from_px(90.0, theme.px_per_inch)))
view = TypesetView([sized], theme=theme, table_widths="natural")
frame(view, name="##sized", mouse=PARKED)
frame(view, name="##sized")
report["sized"] = columns_of(view, 0)
report["sized"]["flags"] = view._described[0].flags
view.close()

report["trouble"] = typesetter.trouble()
report["module_at_end"] = typesetter.module() is not None
report["ready_at_end"] = typesetter.ready()
report["load_end"] = open("/proc/loadavg").read().split()[:3]
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def drawn() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    done = subprocess.run(
        [sys.executable, "-B", "-c", _SET, str(_ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["module"] is True, "IMTYPESET_LIBRARY is set and imtypeset is not in use"
    assert got["load_fonts"] is True and got["ready"] is True, got["reason"]
    assert got["trouble"] == "" and got["module_at_end"] is True and got["ready_at_end"] is True
    return got


def test_the_view_s_words_are_the_library_s_enumerators(drawn: dict[str, Any]) -> None:
    """
    `CODE_OVERFLOWS` is handed to the library by position, and the two flags
    by value: each is held against the loaded package's own.
    """
    told = drawn["enumerators"]
    assert told["overflow"] == [0, 1, 2] and told["names"] == ["wrap", "clip", "grow"]
    for theirs, ours in told["flags"]:
        assert theirs == ours


def test_a_host_s_blocks_are_drawn_and_copied_as_they_were_written(drawn: dict[str, Any]) -> None:
    """
    P8 through the library: the frame is the usual three calls, vertices
    reach the draw list, everything in view was set as asked, and a copy of
    everything gives the two texts to the character (the stars and the tag
    included). The paragraph is one line and the code two.
    """
    told = drawn["host_blocks"]
    assert told["answered"] is True and told["vertices"] > 0
    assert told["calls"] == _FRAME
    assert told["copied"] == told["expected"]
    assert told["lines"] == [1, 2]


def test_a_host_s_description_is_drawn_with_its_styles_links_and_table(
    drawn: dict[str, Any],
) -> None:
    """
    A `Description` handed to the view is set by the library without an
    edit being cut (`edit_error` 0): its tagged run is the link under the
    mouse and a click follows it to the `LinkRow`'s target; its table has
    its rows and columns; the ink its second style states reaches the
    vertices; the `KIND_HOST` block it asked for is the 40 px it stated;
    and a copy gives each block's text.
    """
    told = drawn["description"]
    assert told["answered"] is True and told["vertices"] > 0 and told["calls"] == _FRAME
    assert told["edit_error"] == 0
    assert told["hovered"] == "https://host.example"
    assert told["clicked"] == ["https://host.example"]
    assert told["table"] == [2, 2] and told["ink"] is True
    assert told["host_height"] == pytest.approx(40.0, abs=0.01)
    assert told["copied"] == told["expected"]


def test_wrap_and_clip_keep_the_measure_and_grow_reports_how_far_the_code_reaches(
    drawn: dict[str, Any],
) -> None:
    """
    pptmstr's P12. One document, a 400-character code line in a 444 px pane:

    - `"wrap"` (the default) breaks the line into ten and claims the measure;
    - `"clip"` leaves it one line, cut at the measure, and claims the measure;
    - `"grow"` leaves it one line and claims the content's width, which is
      the code block's right edge: its 16 px indent and 400 cells.

    Under all three the prose is broken at the pane's width (two lines), and
    `column_width` says so. The library's own `size()` is the measure in all
    three, which is why the view asks the code block (the finding carried to
    the other team).
    """
    told = drawn["overflow"]
    cell = drawn["scrolled_sideways"]["cell"]
    assert cell == pytest.approx(8.0, abs=0.01)
    for mode in ("wrap", "clip", "grow"):
        one = told[mode]
        assert one["answered"] is True
        assert one["column_width"] == 444.0 and one["prose_lines"] == 2, mode
        assert one["document_size"][0] == 444.0, mode
        assert one["item"][0] == one["width"] == one["content_width"], mode
    assert told["wrap"]["code_lines"] == 10 and told["wrap"]["content_width"] == 444.0
    assert told["clip"]["code_lines"] == 2 and told["clip"]["content_width"] == 444.0
    assert told["wrap"]["scroll_max_x"] == told["clip"]["scroll_max_x"] == 0.0
    grow = told["grow"]
    assert grow["code_lines"] == 2
    assert grow["content_width"] == pytest.approx(16.0 + 400 * cell, abs=0.01)
    assert grow["content_width"] == grow["code_right"]
    # Clipped, the library does not say how long the line was.
    assert told["clip"]["code_right"] == 444.0


def test_a_code_line_wider_than_the_window_can_be_scrolled_to(drawn: dict[str, Any]) -> None:
    """
    pptmstr's test of that name, on this layer: under `"grow"` the host's
    child window (with a horizontal scrollbar) has a scroll range that
    reaches the end of the line, because the view claimed its content's
    width; and the prose is still broken to the window, only the scroll
    range is wider.
    """
    grow = drawn["overflow"]["grow"]
    cell = drawn["scrolled_sideways"]["cell"]
    pane = grow["pane"][1]
    assert grow["scroll_max_x"] > 400 * cell - pane
    assert grow["scroll_max_x"] == pytest.approx(grow["content_width"] - pane, abs=1.0)
    assert grow["column_width"] == pane < grow["content_width"]


def test_a_frame_is_three_calls_under_every_overflow_and_grow_asks_a_code_block_once(
    drawn: dict[str, Any],
) -> None:
    """
    The call budget. The first frame of a view makes its document (four
    calls) and then the three; under `"grow"` it asks the one code block
    where it ends, once. Every frame after is the three, exactly, under all
    three overflows.
    """
    told = drawn["overflow"]
    made = ["GetCurrentContext", "CreateDocument", "SetDocumentBlocks", "SetDocumentOptions"]
    for mode in ("wrap", "clip"):
        assert told[mode]["first"] == made + _FRAME, mode
    assert told["grow"]["first"] == made + _FRAME + ["GetDocumentBlockGeometry"]
    for mode in ("wrap", "clip", "grow"):
        assert told[mode]["steady"] == [_FRAME, _FRAME, _FRAME], mode


def test_scrolled_sideways_the_mouse_the_selection_and_the_marks_are_where_the_text_is(
    drawn: dict[str, Any],
) -> None:
    """
    The view drawn at a negative x under the pane's clip (the window scrolled
    1,000 px to the right): its origin moved by exactly the scroll and the
    measure did not; the character under the mouse is the one whose screen
    place was asked for (one hit test); a drag from character 140 of the
    long line to character 170 selects those thirty; a mark over characters
    150 to 160 adds a quad whose corners are where `span_rects` says, 1,216
    to 1,296 px from the document's corner; and an ink at the line's far
    end, 3,136 px along, is handed to the draw.
    """
    told = drawn["scrolled_sideways"]
    still, moved = told["still"], told["moved"]
    assert (still["scroll_x"], moved["scroll_x"]) == (0.0, 1000.0)
    assert moved["origin"] == [still["origin"][0] - 1000, still["origin"][1]]
    assert moved["column_width"] == still["column_width"] == 444.0
    assert moved["content_width"] == still["content_width"]
    assert moved["calls"] == _FRAME
    assert told["hover"] == told["wanted"] == [1, 146]
    assert told["hover_calls"] == [*_FRAME, "HitTestDocument"]
    assert told["selection"] == [[1, 146], [1, 176]] and told["text"] == "x" * 30
    plain, marked = told["vertices"]
    assert marked == plain + 4
    cell, left = told["cell"], told["code_left"]
    (rect,) = told["mark_rects"]
    assert rect[0] == pytest.approx(left + 150 * cell, abs=0.01)
    assert rect[2] == pytest.approx(left + 160 * cell, abs=0.01)
    assert told["mark_xs"] == pytest.approx([rect[0], rect[2]], abs=0.51)
    assert told["ink_drawn"] == 1
    assert told["ink_xs"][0] == pytest.approx(left + 390 * cell, abs=0.51)
    # While an ink is set a frame makes its two hit tests, as under wrap.
    assert told["inked_calls"] == [
        "LayoutDocument",
        "HitTestDocument",
        "HitTestDocument",
        "DrawDocument",
        "GetDocumentSize",
    ]


def test_scroll_to_an_offset_in_a_line_that_grew_goes_sideways(drawn: dict[str, Any]) -> None:
    """
    From the left edge, `scroll_to(block, offset)` for character 395 of the
    long line moves the pane sideways (`scrolled` on the frame it asks) and
    the caret ends inside the pane, its margin from the edge.
    """
    told = drawn["scrolled_sideways"]
    assert told["home"] == 0.0 and told["asked_scrolled"] is True
    assert told["arrived"] > 2000.0
    left, width = told["pane"]
    assert left + 24.0 <= told["caret_on_screen"] <= left + width - 24.0 + 1.0


def test_the_overflow_changes_on_a_view_that_is_on_show(drawn: dict[str, Any]) -> None:
    """
    `set_code_overflow` costs one `SetDocumentOptions` at the next frame and
    describes nothing: to `"wrap"`, the content is the measure again, the
    code two source lines in more than two, and the pane has nothing to
    scroll to; back to `"grow"`, the code block is asked where it ends once
    more and the content is as wide as it was.
    """
    told = drawn["overflow_changed"]
    content, measure, lines, reach = told["wrapped"]
    assert content == measure == 444.0 and lines == 10 and reach == 0.0
    assert told["back_calls"] == ["SetDocumentOptions", *_FRAME, "GetDocumentBlockGeometry"]
    assert told["back"] == [drawn["overflow"]["grow"]["content_width"], 2]


def test_a_wide_line_in_a_fenced_diff_is_the_diff_view_s_to_scroll(drawn: dict[str, Any]) -> None:
    """
    pptmstr's test of that name: a fenced diff with a 400-character line,
    hosted by `TypesetDiffFences` in a view whose code grows. The block is a
    Host block the view was asked for, the widget is drawn, and the view's
    content is the measure: the window gets no sideways range for a line
    the hosted view (whose own content IS wider) already scrolls.
    """
    told = drawn["hosted"]
    assert told["hosts"] == [1] and told["drawn"] == 1 and told["kind"] == 5
    assert told["widget"] == "HostedDiff"
    assert told["content_width"] == told["column_width"] == 444.0
    assert told["scroll_max_x"] == 0.0
    assert told["widget_content_width"] > 3000.0


def test_a_stream_s_content_width_follows_its_code_one_question_a_change(
    drawn: dict[str, Any],
) -> None:
    """
    A `TypesetStreamView` with `code_overflow="grow"`: as a code line
    arrives the content's width follows it (the measure while the line is
    shorter), each frame that took text in asks the code block once, and a
    frame with no new text is the three calls.
    """
    told = drawn["stream_grows"]
    widths = told["widths"]
    assert widths[0] == 444.0 and widths == sorted(widths) and widths[-1] > 2400.0
    assert told["asked"] == [1, 1, 1, 1]
    assert told["steady"] == _FRAME and told["column_width"] == 444.0


def test_every_line_of_a_block_is_one_pitch_under_the_last_whatever_is_in_it(
    drawn: dict[str, Any],
) -> None:
    """
    pptmstr's test of that name. A code block of six lines, three of which
    hold box-drawing glyphs (set from another face): without the option the
    lines are 22.4, 22.4, 20, 20, 22.4 and 20 px tall and the steps between
    their tops are 24, 24, 20, 21.6 and 24; with it every line is 20 px and
    every step 20. The paragraph and the list item (accented capitals and a
    box rule in the prose face) are one pitch either way, 21.6 px, and take
    the flag all the same. Reported as measured; nothing here says which
    reads better.
    """
    natural, fixed = drawn["pitch"]["natural"], drawn["pitch"]["fixed"]
    assert natural["flags"] == [0, 0, 0] and fixed["flags"] == [8, 8, 8]
    assert natural["answered"] is True and fixed["answered"] is True
    assert natural["calls"] == fixed["calls"] == _FRAME
    code = natural["blocks"][0]
    assert code["tops"] == pytest.approx([0.0, 24.0, 48.0, 68.0, 89.6, 113.6], abs=0.01)
    assert code["heights"] == pytest.approx([22.4, 22.4, 20.0, 20.0, 22.4, 20.0], abs=0.01)
    code = fixed["blocks"][0]
    assert code["tops"] == pytest.approx([20.0 * n for n in range(6)], abs=0.01)
    assert code["heights"] == pytest.approx([20.0] * 6, abs=0.01)
    for told in (natural, fixed):
        for block in told["blocks"][1:]:
            steps = [b - a for a, b in zip(block["tops"], block["tops"][1:], strict=False)]
            assert steps == pytest.approx([21.6] * len(steps), abs=0.01)
    # The whole view is shorter by what the three tall lines had added.
    assert natural["height"] - fixed["height"] == pytest.approx(13.6, abs=1.0)


def test_a_view_of_one_block_capped_at_n_pitches_ends_on_a_whole_line(
    drawn: dict[str, Any],
) -> None:
    """
    pptmstr's `test_a_capped_view_ends_on_a_whole_line`, for the case a
    pitch can answer: ONE block (tool output as a `MarkdownCode`). With the
    option the foot of line n is n pitches under the block's top, the pitch
    being the style's line height in ems of its size, so a cap of N pitches
    is a line's foot for every N. Without it (the mutation) the feet are
    not multiples of anything: a cap of two lines cuts through the second.
    """
    fixed, natural = drawn["capped"]["fixed"], drawn["capped"]["natural"]
    pitch = drawn["em"] * fixed["scale"] * fixed["line_height"]
    assert pitch == pytest.approx(20.0, abs=0.01)
    assert fixed["feet"] == pytest.approx([pitch * n for n in range(1, 7)], abs=0.01)
    assert natural["feet"][1] == pytest.approx(46.4, abs=0.01)
    assert not any(abs(foot - 2 * pitch) < 0.5 for foot in natural["feet"])


@pytest.mark.parametrize("name", ["pptmstr", "after_prose"])
def test_a_settled_table_at_its_natural_widths_is_where_its_stream_held_it(
    drawn: dict[str, Any], name: str
) -> None:
    """
    pptmstr's P19 and its test: a `TypesetStreamView` over a stream that
    keeps, given the source whole or three characters a frame, and then a
    `TypesetView` of the same source with `table_widths="natural"`. Every
    column's two edges are equal, to a thousandth of a pixel, so the frame
    that swaps one for the other moves no column. The default view
    (`"fitted"`) is the mutation: it scales the table up to the 444 px
    measure and every edge but the first is somewhere else.
    """
    told = drawn["tables"][name]
    natural = told["natural"]
    assert natural["stated"] is True and natural["flags"] & 32
    for stream in (told["whole"], told["by_threes"]):
        assert stream["keeps"] is True and stream["source"] is True
        assert stream["stated"] is True
        for theirs, ours in zip(stream["edges"], natural["edges"], strict=True):
            assert ours == pytest.approx(theirs, abs=0.001)
        assert natural["table"] == pytest.approx(stream["table"], abs=0.001)
    assert natural["table"][1] < 444.0
    fitted = told["fitted"]
    assert fitted["stated"] is False and fitted["flags"] & 32 == 0
    assert fitted["table"] == pytest.approx([0.0, 444.0], abs=0.01)
    assert fitted["edges"][0][1] > natural["edges"][0][1] + 50.0
    # What each column wants is the same number under both.
    assert fitted["natural"] == pytest.approx(natural["natural"], abs=0.001)


def test_a_table_too_wide_for_the_measure_is_fitted_under_both(drawn: dict[str, Any]) -> None:
    """
    The other half of pptmstr's test: columns that want more than the
    measure are the library's to squeeze, in a stream and settled, natural
    or fitted alike. All four agree, and none is "stated".
    """
    told = drawn["tables"]["too_wide"]
    for name in ("whole", "by_threes", "natural"):
        assert told[name]["stated"] is False
        for theirs, ours in zip(told[name]["edges"], told["fitted"]["edges"], strict=True):
            assert theirs == pytest.approx(ours, abs=0.001)
    assert told["fitted"]["table"] == pytest.approx([0.0, 444.0], abs=0.01)


def test_a_cell_wider_while_it_was_written_leaves_the_stream_s_column_wider(
    drawn: dict[str, Any],
) -> None:
    """
    Where the rule stops holding, measured and not hidden. `**bold words**`
    and a code span arriving three characters a frame are, for some frames,
    the literal characters `**bold wor` and a backtick, which are wider than
    what they end as; a held column is the widest its cells have EVER
    wanted, so the stream's columns end 4.93 and 2.43 px wider than the same
    table given whole. The stream given whole agrees with the settled view;
    the stream given in pieces does not.

    What closes it today is the host's: state the stream's widths on the
    settled view (`set_table_columns` with a width a column), which puts
    every edge where the stream had it.
    """
    told = drawn["tables"]["markup_closing_late"]
    natural = told["natural"]["edges"]
    for theirs, ours in zip(told["whole"]["edges"], natural, strict=True):
        assert ours == pytest.approx(theirs, abs=0.001)
    pieces = told["by_threes"]["edges"]
    assert pieces[0][1] - natural[0][1] == pytest.approx(4.93, abs=0.05)
    assert pieces[1][1] - natural[1][1] == pytest.approx(7.36, abs=0.05)
    carried = drawn["carried"]
    assert carried["stated"] is True and carried["changed"] is True
    for theirs, ours in zip(pieces, carried["edges"], strict=True):
        assert ours == pytest.approx(theirs, abs=0.001)
    # Stated, the table is not held (the library would keep the held widths):
    # the one block is handed over again without the flag, and with it again
    # when the columns are given back.
    assert carried["flags"] & 32 == 0 and carried["calls"] == ["ReplaceDocumentBlocks"]
    back = drawn["carried_back"]
    assert back["flags"] & 32 and back["calls"] == ["ReplaceDocumentBlocks"]
    for theirs, ours in zip(natural, back["edges"], strict=True):
        assert ours == pytest.approx(theirs, abs=0.001)
    sized = drawn["sized"]
    assert sized["flags"] & 32 == 0 and sized["stated"] is True
    assert [right - left for left, right in sized["edges"]] == pytest.approx(
        [120.0, 90.0], abs=0.01
    )


# ---------------------------------------------------------------------------
# 3. With the library, in a real window
# ---------------------------------------------------------------------------

_WINDOW = r"""
import json, sys

from imgui_bundle import hello_imgui, imgui, immapp

from imscribe import typesetter
from imscribe.theme import Theme
from imscribe.ui.palette import DARK_PALETTE
from imscribe.ui.typeset_view import TypesetView

PARKED = (700.0, 700.0)
PARAGRAPH = "some prose that is long enough to be broken into lines at the width of the pane\n\n"
SOURCE = PARAGRAPH + "```\nshort\n" + "x" * 400 + "\n```\n\n" + PARAGRAPH
theme = Theme.build()
report = {"frames": {}, "load_start": open("/proc/loadavg").read().split()[:3]}
state = {"n": 0, "view": None, "at": {}}

def load_fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    report["load_fonts"] = typesetter.load_fonts()

def at_char(view, position):
    x0, y0, _, y1 = view.native_document.caret_rect(position)
    ox, oy = view.origin
    return (ox + x0 + 1.5, oy + (y0 + y1) / 2.0)

def pre_new_frame():
    n = state["n"] + 1
    io = imgui.get_io()
    if n == 1:
        io.add_mouse_pos_event(*PARKED)
    elif n == 20:
        io.add_mouse_pos_event(*state["at"]["press"])
    elif n == 24:
        io.add_mouse_button_event(0, True)
    elif n == 28:
        io.add_mouse_pos_event(*state["at"]["release"])
    elif n == 32:
        io.add_mouse_button_event(0, False)
    elif n == 36:
        io.add_mouse_pos_event(*PARKED)

def gui():
    state["n"] += 1
    n = state["n"]
    if n == 1:
        report["module"] = typesetter.module() is not None
        report["ready"] = typesetter.ready()
        report["reason"] = typesetter.reason()
        if not (report["module"] and report["ready"]):
            hello_imgui.get_runner_params().app_shall_exit = True
            return
        state["view"] = TypesetView(SOURCE, theme=theme, palette=DARK_PALETTE, code_overflow="grow")
    view = state["view"]
    if view is None:
        return
    imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
    imgui.set_next_window_size(imgui.ImVec2(460.0, 500.0))
    imgui.begin("host", None,
                imgui.WindowFlags_.no_collapse.value | imgui.WindowFlags_.no_move.value)
    imgui.begin_child("##text", imgui.ImVec2(0.0, 0.0), 0,
                      imgui.WindowFlags_.horizontal_scrollbar.value)
    try:
        if n == 10:
            imgui.set_scroll_x(1000.0)
        draw_list = imgui.get_window_draw_list()
        vertices = draw_list.vtx_buffer.size()
        answered = view.draw()
        if n == 18:
            state["at"] = {"press": at_char(view, (1, 6 + 140)),
                           "release": at_char(view, (1, 6 + 170))}
        hit = view.under_mouse
        report["frames"][n] = {
            "answered": answered, "vertices": draw_list.vtx_buffer.size() - vertices,
            "scroll_x": imgui.get_scroll_x(), "scroll_max_x": imgui.get_scroll_max_x(),
            "origin": list(view.origin), "content_width": view.content_width,
            "column_width": view.column_width, "item": imgui.get_item_rect_size().x,
            "pane": [imgui.get_window_pos().x, imgui.get_window_size().x],
            "selection": view.selection,
            "hit": None if hit is None else [int(hit.position[0]), int(hit.position[1])],
        }
        if n == 38:
            report["text"] = view.selected_text()
    finally:
        imgui.end_child()
        imgui.end()
    if n >= 40:
        hello_imgui.get_runner_params().app_shall_exit = True

def before_exit():
    report["module_at_end"] = typesetter.module() is not None
    report["ready_at_end"] = typesetter.ready()
    report["trouble"] = typesetter.trouble()
    typesetter.unload()

runner = hello_imgui.RunnerParams()
runner.app_window_params.window_title = "TypesetView, code that grows, under test"
runner.app_window_params.window_geometry.size = (800, 760)
runner.imgui_window_params.default_imgui_window_type = (
    hello_imgui.DefaultImGuiWindowType.no_default_window
)
runner.ini_disable = True
runner.fps_idling.enable_idling = False
runner.callbacks.load_additional_fonts = load_fonts
runner.callbacks.show_gui = gui
runner.callbacks.pre_new_frame = pre_new_frame
runner.callbacks.before_exit = before_exit
immapp.run(runner)
report["frame_count"] = state["n"]
report["load_end"] = open("/proc/loadavg").read().split()[:3]
print("REPORT " + json.dumps(report))
"""


def test_in_a_real_window_a_view_that_grew_is_scrolled_and_selected_under_the_clip(
    window: Any,
) -> None:
    """
    The same thing through `hello_imgui` in a real window, the mouse queued
    through `io.add_*_event`: the child window's own scrollbar range is the
    content's width less the pane, a scroll of 1,000 px moves the view's
    origin by 1,000 and not its measure, vertices still reach the draw list
    there, the character under the mouse is the one aimed at, and a drag
    selects the thirty characters between the press and the release.
    `module()` and `ready()` are asserted in the child, before and after.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip("IMTYPESET_LIBRARY is not set: see `make test TYPESET=1`")
    script = window.out / "typeset_view_grow_driver.py"
    script.write_text(_WINDOW, encoding="utf-8")
    done = window.run([str(script), str(_ROOT)], timeout=300.0)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    got = _report_of(done.stdout)
    assert got["module"] is True, "the child did not get imtypeset: " + got.get("reason", "")
    assert got["load_fonts"] is True and got["ready"] is True, got.get("reason", "")
    assert got["module_at_end"] is True and got["ready_at_end"] is True and got["trouble"] == ""
    assert got["frame_count"] == 40
    frames = {int(n): one for n, one in got["frames"].items()}
    still, moved = frames[9], frames[16]
    pane = still["pane"][1]
    assert still["content_width"] == pytest.approx(16.0 + 400 * 8.0, abs=0.5)
    assert still["item"] == still["content_width"]
    assert still["scroll_max_x"] > 400 * 8.0 - pane
    assert (still["scroll_x"], moved["scroll_x"]) == (0.0, 1000.0)
    assert moved["origin"][0] == still["origin"][0] - 1000 and moved["origin"][0] < 0
    assert moved["column_width"] == still["column_width"] == pane < still["content_width"]
    assert moved["answered"] is True and moved["vertices"] > 0
    assert frames[23]["hit"] == [1, 146]
    assert frames[38]["selection"] == [[1, 146], [1, 176]]
    assert got["text"] == "x" * 30

r"""
A host's reader options (pptmstr's P7) and a size for inline code (its P11).

`advtext.typeset_markdown.ReaderOptions` says what of a source a CommonMark
reader hides and this host wants set; `Theme.inline_code_scale` and
`Theme.inline_code_step` say how big a code span is beside its block. Five
groups.

1.  **The options object**: its fields, that all off is the reading there
    always was (the same parser object, the same blocks on every demo), and
    that a mistake is refused at the call.
2.  **What each option shows**, on the inputs pptmstr's old seam was tested
    with (`tests/test_typeset.py` in its `adv-text-experiment` worktree:
    `test_html_in_a_document_is_shown_and_not_dropped`, the `HIDING` and
    `STARS` tables, `test_a_links_destination_is_on_screen_settled_and_streamed`,
    `LOOKALIKES`). The expectations are that file's, restated on blocks: a
    block's `text` where that file read a view's.
3.  **Settled and streamed are one reading.** A `MarkdownStream` given the
    options is held, after every piece, to one `parse_markdown` of what it
    has, under each option alone and all together: on those inputs, on a
    corpus written for raw HTML in every place the stream's commit rule and
    its three shortcuts could meet it, on the sources the stream was already
    held to, and on every demo.
4.  **Inline code's size.** What the reader writes into a run's `scale`, and
    (with the library; skipped without `IMTYPESET_LIBRARY`) that the library
    sets such a run at that multiple of ITS BLOCK's size, measured from the
    advance of a monospace character. The theme's two fields themselves are
    in `tests/test_style.py`.
5.  **Backslashes as written** (pptmstr's P32): what
    `ReaderOptions.backslashes_as_written` sets, what it leaves alone, and
    settled against streamed on a corpus of its own, alone and with each
    other option.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import re
import string
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import material_frozen
import pytest
import test_markdown as markdown_tests
from markdown_it.rules_inline.escape import escape as markdown_it_escape

from advtext import markdown_rules, typesetter
from advtext import typeset_markdown as direct
from advtext.description import RunDescription, face_role
from advtext.primitives import Face, sp_from_px
from advtext.theme import BlockKind, Faces, Theme
from advtext.typeset_markdown import (
    MarkdownCode,
    MarkdownConverter,
    MarkdownStream,
    MarkdownTable,
    MarkdownText,
    ReaderOptions,
    describe_markdown,
    parse_markdown,
    reader_options,
)

_ROOT = Path(__file__).resolve().parent.parent
_DEMOS = sorted((_ROOT / "demo").rglob("*.md"))
_THEME = Theme.build()

ALL = ReaderOptions(
    html_as_text=True, images_as_text=True, keep_glob_stars=True, show_link_destinations=True
)
OPTIONS: dict[str, ReaderOptions] = {
    "html": ReaderOptions(html_as_text=True),
    "images": ReaderOptions(images_as_text=True),
    "stars": ReaderOptions(keep_glob_stars=True),
    "destinations": ReaderOptions(show_link_destinations=True),
    "backslashes": ReaderOptions(backslashes_as_written=True),
    "all": ALL,
}
# `ALL` is the four options of P7, which the tables below were written for;
# this is every field there is (section 5).
EVERY = ReaderOptions(**{field.name: True for field in dataclasses.fields(ReaderOptions)})


def _shown(blocks: Any) -> str:
    """
    What a reader of these blocks sees, a block to a paragraph: markers, text, code, cells.
    """
    out: list[str] = []
    for block in blocks:
        if isinstance(block, MarkdownText):
            out.append(f"{block.marker} {block.text}" if block.marker else block.text)
        elif isinstance(block, MarkdownCode):
            out.append(block.text)
        elif isinstance(block, MarkdownTable):
            rows = [block.header, *block.rows] if block.header else list(block.rows)
            out.append("\n".join(" | ".join(cell.text for cell in row) for row in rows))
    return "\n\n".join(out)


def _rule(parser: Any, name: str) -> Any:
    """
    The function an inline rule of `parser` runs, by the rule's name.
    """
    (found,) = [rule.fn for rule in parser.inline.ruler.__rules__ if rule.name == name]
    return found


def _replay(
    source: str,
    chunk: int,
    reader: ReaderOptions | None,
    *,
    math: bool = True,
    theme: Theme = _THEME,
) -> MarkdownStream:
    """
    Feed `source` in pieces of `chunk` characters (0: by the line), holding the
    stream after each to one parse of everything it has, with the same options.
    """
    if chunk == 0:
        pieces = source.splitlines(keepends=True)
    else:
        pieces = [source[at : at + chunk] for at in range(0, len(source), chunk)]
    stream = MarkdownStream(theme, math=math, reader=reader)
    raw = seen = ""
    committed: tuple[Any, ...] = ()
    for piece in pieces:
        stream.append(piece)
        raw += piece
        # Line ends are normalised as text arrives, and a carriage return
        # that ends a piece is held until the next one.
        seen = (raw[:-1] if raw.endswith("\r") else raw).replace("\r\n", "\n").replace("\r", "\n")
        blocks = stream.blocks
        whole = parse_markdown(
            seen, theme, references=False, math=math, more_may_follow=True, reader=reader
        )
        assert blocks == whole.blocks, (chunk, len(seen), seen[-60:])
        assert stream.sources == whole.sources, (chunk, len(seen), seen[-60:])
        # What is committed never changes: the same objects, and more of them.
        now = stream.committed
        assert len(now) >= len(committed)
        assert all(a is b for a, b in zip(committed, now, strict=False))
        committed = now
    stream.close()
    seen = raw.replace("\r\n", "\n").replace("\r", "\n")
    whole = parse_markdown(seen, theme, references=False, math=math, reader=reader)
    assert stream.blocks == whole.blocks and stream.live == ()
    assert stream.sources == whole.sources
    assert all(a is b for a, b in zip(committed, stream.committed, strict=False))
    # And the description a view would hand the library is the whole source's.
    final = MarkdownConverter(theme).describe(stream.blocks)
    assert final == describe_markdown(seen, theme, references=False, math=math, reader=reader)
    return stream


# ---------------------------------------------------------------------------
# 1. The options object
# ---------------------------------------------------------------------------


def test_the_fields_and_their_defaults_are_exactly_these() -> None:
    """
    What PH-VIEW and pptmstr were told. A sixth field, or a default that is
    not off, is a change to a published interface and should fail here first.
    (The fifth, `show_fence_info`, is pptmstr's P27: `tests/test_host_requests_2.py`.)
    """
    assert [
        (field.name, field.type, field.default) for field in dataclasses.fields(ReaderOptions)
    ] == [
        ("html_as_text", "bool", False),
        ("images_as_text", "bool", False),
        ("keep_glob_stars", "bool", False),
        ("show_link_destinations", "bool", False),
        ("show_fence_info", "bool", False),
        ("backslashes_as_written", "bool", False),
    ]
    options = ReaderOptions()
    assert options == ReaderOptions(False, False, False, False, False, False)
    # A value: equal options are one key, and it cannot be changed under a stream.
    assert hash(ReaderOptions(html_as_text=True)) == hash(OPTIONS["html"])
    assert len({ReaderOptions(), ReaderOptions(), ALL, replace(ALL)}) == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.html_as_text = True  # type: ignore[misc]
    assert "ReaderOptions" in direct.__all__ and "reader_options" in direct.__all__


@pytest.mark.parametrize("references", [True, False])
@pytest.mark.parametrize("math", [True, False])
def test_all_off_is_the_parser_there_always_was(references: bool, math: bool) -> None:
    """
    Not an equal parser: the same object. Nothing a caller that states no
    option reads with was rebuilt for the options to exist.
    """
    plain = markdown_rules._parser(references, math)
    assert direct._parser_for(references, math, ReaderOptions()) is plain
    assert direct._parser_for(references, math, reader_options(None)) is plain
    # Showing a destination is the reader's doing and not a parser's.
    assert direct._parser_for(references, math, OPTIONS["destinations"]) is plain
    for name in ("html", "images", "stars", "backslashes", "all"):
        other = direct._parser_for(references, math, OPTIONS[name])
        assert other is not plain, name
        # One per combination, kept: a second asking is handed the same one.
        assert direct._parser_for(references, math, replace(OPTIONS[name])) is other, name
    # Six options, six parsers: the five that change the parse, and the plain one.
    assert len({id(direct._parser_for(references, math, each)) for each in OPTIONS.values()}) == 6
    if not math:
        singletons = (markdown_rules._PARSER, markdown_rules._PARSER_WITHOUT_REFERENCES)
        assert plain is singletons[0 if references else 1]


def test_the_shared_parsers_still_have_the_rules_an_option_switches_off() -> None:
    """
    `MarkdownIt.disable` mutates. An option that reached one of the shared
    parsers would change the reading of every caller in the process, which is
    what pptmstr's seam did on purpose and what these options must not do.
    """
    for name in OPTIONS:
        direct._parser_for(True, False, OPTIONS[name])
        direct._parser_for(False, True, OPTIONS[name])
    for parser in (markdown_rules._PARSER, markdown_rules._PARSER_WITHOUT_REFERENCES):
        assert "html_block" in parser.block.ruler.get_active_rules()
        inline = parser.inline.ruler.get_active_rules()
        assert {"html_inline", "image", "emphasis"} <= set(inline)
        assert "written_stars" not in parser.inline.ruler.get_all_rules()
        assert "written_cell_pipes" not in parser.core.ruler.get_all_rules()
        assert _rule(parser, "escape") is markdown_it_escape
    switched = direct._parser_for(True, False, ALL)
    assert "html_block" not in switched.block.ruler.get_active_rules()
    inline = switched.inline.ruler.get_active_rules()
    assert not {"html_inline", "image"} & set(inline)
    # In front of the emphasis rule, so it is asked about a star first.
    assert inline.index("written_stars") + 1 == inline.index("emphasis")


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_a_demo_read_with_the_default_options_is_the_demo_read_with_none(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for math in (True, False):
        plain = parse_markdown(source, _THEME, math=math)
        assert parse_markdown(source, _THEME, math=math, reader=ReaderOptions()) == plain
        assert describe_markdown(source, _THEME, math=math, reader=None) == describe_markdown(
            source, _THEME, math=math
        )


def test_a_stream_and_a_parse_given_equal_options_read_with_one_parser() -> None:
    """
    pptmstr's complaint in P7: through the private parser, a view's `str` and
    a stream read with different cached parsers.
    """
    for options in (None, *OPTIONS.values()):
        for math in (True, False):
            stream = MarkdownStream(_THEME, math=math, reader=options)
            assert stream.reader == reader_options(options)
            assert stream._parser is direct._parser_for(False, math, reader_options(options))
            assert stream._parser is direct._parser_for(False, math, replace(stream.reader))


@pytest.mark.parametrize("wrong", [True, "html", {"html_as_text": True}, ("html_as_text",), 1])
def test_something_that_is_not_options_is_refused_at_the_call(wrong: Any) -> None:
    """
    At the host's call, with the type named: a stream parses inside a draw,
    and a mistake must not be found there.
    """
    name = type(wrong).__name__
    with pytest.raises(TypeError, match=f"ReaderOptions or None, not {name}"):
        parse_markdown("text", _THEME, reader=wrong)
    with pytest.raises(TypeError, match=f"ReaderOptions or None, not {name}"):
        describe_markdown("text", _THEME, reader=wrong)
    with pytest.raises(TypeError, match=f"ReaderOptions or None, not {name}"):
        MarkdownStream(_THEME, reader=wrong)
    with pytest.raises(TypeError, match=f"ReaderOptions or None, not {name}"):
        reader_options(wrong)


@pytest.mark.parametrize("field", [field.name for field in dataclasses.fields(ReaderOptions)])
@pytest.mark.parametrize("wrong", [1, 0, None, "yes"])
def test_a_field_that_is_not_a_bool_is_refused_when_the_options_are_made(
    field: str, wrong: Any
) -> None:
    with pytest.raises(TypeError, match=f"ReaderOptions.{field} is True or False"):
        ReaderOptions(**{field: wrong})


# ---------------------------------------------------------------------------
# 2. What each option shows
# ---------------------------------------------------------------------------

_HTML = "List<String> here\n\n<div>block</div>\n\n`Vec<T>`\n\n<!-- note\n\nafter\n"


def test_html_in_a_document_is_shown_and_not_dropped() -> None:
    """
    pptmstr's test of that name. With no option the library, following
    CommonMark, shows none of the three: the block vanishes, `<String>`
    vanishes, and the comment opener swallows the rest. That reading is
    pinned too, because it is the default and must stay it.
    """
    expected = ["List<String> here", "<div>block</div>", "Vec<T>", "<!-- note", "after"]
    for options in (OPTIONS["html"], ALL):
        blocks = parse_markdown(_HTML, _THEME, reader=options).blocks
        assert [block.text for block in blocks] == expected
        assert [block.text for block in _replay(_HTML, 1, options).blocks] == expected
    assert [block.text for block in parse_markdown(_HTML, _THEME).blocks] == ["List here", "Vec<T>"]
    for name in ("images", "stars", "destinations"):
        hidden = parse_markdown(_HTML, _THEME, reader=OPTIONS[name]).blocks
        assert [block.text for block in hidden] == ["List here", "Vec<T>"], name


def test_an_unclosed_comment_takes_nothing_after_it() -> None:
    """
    The behaviour behind the request: "an unclosed `<!--` swallows the rest of
    an approval body". Everything written after it is on screen.
    """
    source = "Looks fine.\n\n<!--\nAlso delete tests/\n\n- and this\n\n```\nand this\n```\n"
    assert _shown(parse_markdown(source, _THEME).blocks) == "Looks fine."
    shown = _shown(parse_markdown(source, _THEME, reader=OPTIONS["html"]).blocks)
    assert shown == "Looks fine.\n\n<!-- Also delete tests/\n\n• and this\n\nand this"


# pptmstr's table (`HIDING`), row for row: what was written, what must be on
# screen. Read there with every one of its seam's changes on, so here with
# every option on.
HIDING = [
    ("ask <lead> for the rest", "ask <lead> for the rest"),
    (
        "an Optional<int> and a <system-reminder> tag",
        "an Optional<int> and a <system-reminder> tag",
    ),
    ("Looks fine.\n\n<!--\nAlso delete tests/", "Looks fine.\n\n<!-- Also delete tests/"),
    # An image is an exclamation mark and a link, destination shown.
    (
        "before ![the alt text](http://x/y.png) after",
        "before !the alt text (http://x/y.png) after",
    ),
    # A `<` the writer escaped is one `<` and stays escaped; a backslash they
    # escaped is a backslash and the tag after it is still text.
    ("a \\<div>x\\</div> b", "a <div>x</div> b"),
    ("two \\\\<div> here", "two \\<div> here"),
    # A backtick that closes nothing is a backtick. The tags after it, and a
    # comment opener starting a line of the same paragraph, are still text.
    (
        "a stray ` tick then <tag> more\n<!-- gone\nrest of it\n\nnext",
        "a stray ` tick then <tag> more <!-- gone rest of it\n\nnext",
    ),
    ("`open <b>\n\n<b> after", "`open <b>\n\n<b> after"),
    # Three backticks that open a line and are closed on it are a code span.
    ("```x``` then <tag> here", "x then <tag> here"),
    # A fence its container ends, with no closing line of its own.
    (
        "> ```\n> code\nafter <tag> text\n\npara <b>two</b> here",
        "code\n\nafter <tag> text\n\npara <b>two</b> here",
    ),
    (
        "- item\n\n  ```\n  code\nafter <tag> the list\n\nand <i>on</i>",
        "• item\n\ncode\n\nafter <tag> the list\n\nand <i>on</i>",
    ),
    ("code `Vec<T>` and ``a ` <b>`` stay code", "code Vec<T> and a ` <b> stay code"),
    ("an autolink <https://example.org/a> is one", "an autolink https://example.org/a is one"),
]


@pytest.mark.parametrize(("written", "expected"), HIDING)
def test_text_a_markdown_reader_would_hide_is_set_settled_and_streamed(
    written: str, expected: str
) -> None:
    assert _shown(parse_markdown(written, _THEME, references=False, reader=ALL).blocks) == expected
    for chunk in (1, 3):
        assert _shown(_replay(written, chunk, ALL, math=False).blocks) == expected
    # With no option something of every row is lost, but for three in which
    # the writer had already said it as markdown says it (an escaped `<`,
    # code, an autolink): those are in the table for a reader that escapes
    # the source instead of switching the rules off, and gets them wrong.
    plain = _shown(parse_markdown(written, _THEME, references=False).blocks)
    already = [HIDING[4][0], HIDING[-2][0], HIDING[-1][0]]
    assert (plain == expected) == (written in already), plain


def test_an_image_is_an_exclamation_mark_and_a_link_to_its_address() -> None:
    """
    What `images_as_text` is, exactly: the image rule is not run. The
    description is the text of a link to the image, and the address is on
    screen only when destinations are shown as well.
    """
    source = "before ![the alt text](http://x/y.png 'a title') after"
    # (Two spaces: the one before the image and the one after it.)
    assert parse_markdown(source, _THEME).blocks[0].text == "before  after"
    (block,) = parse_markdown(source, _THEME, reader=OPTIONS["images"]).blocks
    assert block.text == "before !the alt text after"
    assert [(block.text[a:b], target) for a, b, target in block.links] == [
        ("the alt text", "http://x/y.png")
    ]
    both = ReaderOptions(images_as_text=True, show_link_destinations=True)
    (block,) = parse_markdown(source, _THEME, reader=both).blocks
    assert block.text == 'before !the alt text (http://x/y.png "a title") after'
    # A linked image, the usual badge. With no option it is a link over
    # nothing and none of it is on screen. With the option the image is a
    # link, and markdown lets no link hold another: the inner one is the
    # link, and the outer one's brackets and destination are the characters
    # written. Clumsy, and everything that was written can be read.
    badge = "[![build](https://ci/badge.svg)](https://ci/run/7) passed"
    (block,) = parse_markdown(badge, _THEME).blocks
    assert (block.text, block.links) == ("passed", ())
    (block,) = parse_markdown(badge, _THEME, reader=OPTIONS["images"]).blocks
    assert block.text == "[!build](https://ci/run/7) passed"
    assert [(block.text[a:b], target) for a, b, target in block.links] == [
        ("build", "https://ci/badge.svg")
    ]
    (block,) = parse_markdown(badge, _THEME, reader=ALL).blocks
    assert block.text == "[!build (https://ci/badge.svg)](https://ci/run/7) passed"


# pptmstr's table (`STARS`), row for row. Its expectation is the glyphs a view
# set, and a space in prose is glue and no glyph: so the text with no spaces.
STARS = [
    ("delete **/*.py and tests/**/*.md", "delete**/*.pyandtests/**/*.md"),
    ("rm src/**/*.c lib/**/*.h", "rmsrc/**/*.clib/**/*.h"),
    ("glob **/* and **/*", "glob**/*and**/*"),
    ("/* a comment */ and /* another */", "/*acomment*/and/*another*/"),
    ("retry 2*3*4 times, a*b*c", "retry2*3*4times,a*b*c"),
    ("keep *.py and *.md", "keep*.pyand*.md"),
    ("lib/foo*.py and lib/foo*bar", "lib/foo*.pyandlib/foo*bar"),
    # Emphasis is still emphasis: its stars are not drawn.
    ("see **bold** and *em* here", "seeboldandemhere"),
    ("**Ends in a stop.** and *so does this.*", "Endsinastop.andsodoesthis."),
    ("**and/or** stays bold, **src/x.py** too", "and/orstaysbold,src/x.pytoo"),
    # In code a star was never anything else.
    ("`**/*.py` and then **/*.py", "**/*.pyandthen**/*.py"),
]


def _faces(block: Any) -> list[tuple[str, int]]:
    return [(block.text[run.start : run.end], run.face) for run in block.runs]


@pytest.mark.parametrize(("written", "expected"), STARS)
def test_the_stars_of_a_glob_are_set_and_emphasis_is_still_emphasis(
    written: str, expected: str
) -> None:
    for options in (OPTIONS["stars"], ALL):
        (block,) = parse_markdown(written, _THEME, reader=options).blocks
        assert block.text.replace(" ", "") == expected
        (streamed,) = _replay(written, 1, options).blocks
        assert streamed == block
    # Emphasis that is written as emphasis is read exactly as it was: the
    # same runs, in the same faces, as with no option at all.
    (plain,) = parse_markdown(written, _THEME).blocks
    (kept,) = parse_markdown(written, _THEME, reader=OPTIONS["stars"]).blocks
    if "*" not in expected or written.startswith("`"):
        assert [face for _, face in _faces(kept)] == [face for _, face in _faces(plain)]
    if "*" not in expected:
        assert kept == plain


def test_what_tells_a_written_star_from_emphasis_is_the_character_on_each_side() -> None:
    """
    The rule, one case to a condition, and the two directions it is known to
    get wrong (`advtext.markdown_rules._written_stars`). Pinned so that they
    are known and not found.
    """
    bold = face_role(Face.PROSE_BOLD)
    italic = face_role(Face.PROSE_ITALIC)

    def read(source: str) -> tuple[str, list[tuple[str, int]]]:
        (block,) = parse_markdown(source, _THEME, reader=OPTIONS["stars"]).blocks
        return block.text, _faces(block)

    # A slash immediately before the run, or immediately after it.
    assert read("a/**b** c") == ("a/**b** c", [])
    assert read("**/b** c") == ("**/b** c", [])
    # A stop after it and something after the stop; a stop and then a space is not that.
    assert read("*.py and *.md*") == ("*.py and *.md*", [])
    assert read("x *. y* z") == ("x . y z", [(". y", italic)])
    # A letter or a digit on both sides.
    assert read("2*3*4 and a**b**c") == ("2*3*4 and a**b**c", [])
    # None of the three: emphasis, as it was.
    assert read("**bold** and *em*") == ("bold and em", [("bold", bold), ("em", italic)])
    assert read("(**bold**)") == ("(bold)", [("bold", bold)])
    # Known, and left: a glob written exactly as emphasis is still emphasis
    # (pptmstr pins the same, `test_stars_written_exactly_as_emphasis_...`).
    assert read("rm *tmp and old* now") == ("rm tmp and old now", [("tmp and old", italic)])
    # Known, and left, the other way: emphasis hard against a slash or inside
    # a word keeps its stars and is not emphasis.
    assert read("**/usr/bin**") == ("**/usr/bin**", [])
    assert read("foo*bar*baz") == ("foo*bar*baz", [])
    (plain,) = parse_markdown("foo*bar*baz", _THEME).blocks
    assert plain.text == "foobarbaz" and _faces(plain) == [("bar", italic)]


_URL = "https://celestrak.org/NORAD/documentation/tle-fmt.php"
_LINKS = (
    f"See the [CelesTrak TLE documentation]({_URL}), or [the same]({_URL} 'a title'),\n"
    f"or <{_URL}> or [{_URL}]({_URL}).\n\n"
    "| a | b |\n|---|---|\n| [cell](http://in.table/x) | y |\n"
)


def test_a_links_destination_is_on_screen_settled_and_streamed() -> None:
    """
    pptmstr's test of that name, and the second half of the request: the
    link's range covers the destination, so it takes the tag and the click.
    """
    settled = parse_markdown(_LINKS, _THEME, references=False, reader=OPTIONS["destinations"])
    streamed = _replay(_LINKS, 5, OPTIONS["destinations"])
    assert streamed.blocks == settled.blocks
    first, table = settled.blocks
    assert isinstance(first, MarkdownText) and isinstance(table, MarkdownTable)
    assert first.text.startswith(
        f"See the CelesTrak TLE documentation ({_URL}), or the same ({_URL}"
    )
    assert '"a title")' in first.text
    # A link that is already its own destination is not said twice.
    assert first.text.count(_URL) == 4
    cell, _ = table.rows[0]
    assert cell.text == "cell (http://in.table/x)"

    # Every link's range is its text AND its destination, to the closing parenthesis.
    assert [first.text[a:b] for a, b, _ in first.links] == [
        f"CelesTrak TLE documentation ({_URL})",
        f'the same ({_URL} "a title")',
        _URL,
        _URL,
    ]
    assert {target for _, _, target in first.links} == {_URL}
    assert [(cell.text[a:b], target) for a, b, target in cell.links] == [
        ("cell (http://in.table/x)", "http://in.table/x")
    ]

    # And through the converter: one tag over the whole range, text and
    # destination alike, which is what a hit test answers and a click follows.
    converter = MarkdownConverter(_THEME, link_color=0xFF112233)
    described = converter.describe(settled.blocks)
    block = described.blocks[0]
    for row in [row for row in described.links if row.block == 0]:
        assert converter.link_target(row.tag) == _URL
        covered = sorted(
            (run.start, run.end)
            for run in block.runs
            if run.tag == row.tag and row.start <= run.start and run.end <= row.end
        )
        assert covered and covered[0][0] == row.start and covered[-1][1] == row.end
        assert all(a[1] == b[0] for a, b in zip(covered, covered[1:], strict=False))
    assert all(run.color == 0xFF112233 for run in block.runs if run.tag)
    assert [cell.tag for cell in described.blocks[1].rows[1][0].runs] == [2]

    # With no option a link is its text and nothing says where it goes.
    plain = parse_markdown(_LINKS, _THEME, references=False).blocks[0]
    assert plain.text.count(_URL) == 2 and "(" not in plain.text


# pptmstr's `LOOKALIKES`: a text that only NORMALISES to its destination.
@pytest.mark.parametrize(
    ("written", "destination"),
    [
        # A Cyrillic "а" in the text; the reader's own normalising makes it the host.
        ("[https://аpple.com](https://xn--pple-43d.com)", "xn--pple-43d.com"),
        ("<https://аpple.com/login>", "xn--pple-43d.com"),
        ("[https://example.com/a](https://example.com/a?next=evil)", "?next=evil"),
    ],
)
def test_a_link_whose_text_only_normalises_to_its_destination_shows_the_destination(
    written: str, destination: str
) -> None:
    (block,) = parse_markdown(written, _THEME, reader=OPTIONS["destinations"]).blocks
    assert destination in block.text
    assert _replay(written, 1, OPTIONS["destinations"]).blocks == (block,)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("<https://example.org/a>", "https://example.org/a"),
        ("<https://example.org/>", "https://example.org/"),
        ("<lead@example.org>", "lead@example.org"),
        ("[https://example.org](https://example.org/)", "https://example.org"),
        ("[example.org/a](https://example.org/a)", "example.org/a"),
    ],
)
def test_a_link_that_is_its_destination_to_the_character_says_it_once(
    written: str, expected: str
) -> None:
    (block,) = parse_markdown(written, _THEME, reader=OPTIONS["destinations"]).blocks
    assert block.text == expected


@pytest.mark.parametrize(
    ("written", "expected", "linked"),
    [
        # In the face the link's text ends in, inside the link.
        ("a [**b**](u) c", "a b (u) c", "b (u)"),
        ("**[b](u)** c", "b (u) c", "b (u)"),
        ("[`code`](u) c", "code (u) c", "code (u)"),
        # A link's text that ends in a space, or is nothing: one space, or none.
        ("[b ](u) c", "b (u) c", "b (u)"),
        ("[](u) c", "(u) c", "(u)"),
        # After a hard break the destination begins the line.
        ("[b\\\n](u) c", "b\n(u) c", "b\n(u)"),
        # A destination written in angle brackets is followed, and shown, without them.
        ("[t](<http://u/x y>)", "t (http://u/x%20y)", "t (http://u/x%20y)"),
        # A reference link is a link (references on: this is one whole parse).
        ("[t][r]\n\n[r]: http://r/ 'T'", 't (http://r/ "T")', 't (http://r/ "T")'),
    ],
)
def test_where_the_destination_is_written_and_what_the_link_covers(
    written: str, expected: str, linked: str
) -> None:
    (block,) = parse_markdown(written, _THEME, reader=OPTIONS["destinations"]).blocks
    assert block.text == expected
    ((start, end, _),) = block.links
    assert block.text[start:end] == linked
    # Runs are still ascending and never overlap, which the library requires.
    described = MarkdownConverter(_THEME).describe([block]).blocks[0]
    reached = 0
    for run in described.runs:
        assert reached <= run.start < run.end <= len(block.text)
        reached = run.end


def test_each_option_changes_its_own_thing_and_no_other() -> None:
    source = (
        "A <b>tag</b>, an ![image](http://i/x.png), a glob **/*.py and **/*.md, "
        "and a [link](http://l/y).\n"
    )
    read = {
        name: parse_markdown(source, _THEME, reader=options).blocks[0].text
        for name, options in OPTIONS.items()
    }
    plain = parse_markdown(source, _THEME).blocks[0].text
    # (CommonMark pairs the two single stars into emphasis and draws neither.)
    assert plain == "A tag, an , a glob **/.py and **/.md, and a link."
    assert read["html"] == "A <b>tag</b>, an , a glob **/.py and **/.md, and a link."
    assert read["images"] == "A tag, an !image, a glob **/.py and **/.md, and a link."
    assert read["stars"] == "A tag, an , a glob **/*.py and **/*.md, and a link."
    assert read["destinations"] == "A tag, an , a glob **/.py and **/.md, and a link (http://l/y)."
    assert read["backslashes"] == plain
    assert read["all"] == (
        "A <b>tag</b>, an !image (http://i/x.png), a glob **/*.py and **/*.md, "
        "and a link (http://l/y)."
    )


# ---------------------------------------------------------------------------
# 3. Settled and streamed are one reading
# ---------------------------------------------------------------------------

# Raw HTML wherever the stream's commit rule or one of its three shortcuts
# could meet it. With the HTML rules on, a line that opens an HTML block ends
# the paragraph, the table or the lazy continuation above it and starts a
# block of its own, some kinds of which run on over blank lines. With them
# off (`html_as_text`) the same line is a paragraph's, a table row's or a
# lazy line's. The stream must commit as one parse reads either way.
HTML_CORPUS: dict[str, str] = {
    # CommonMark's seven ways an HTML block starts.
    "1-script": "para\n<script>\nlet a = 1;\n\nlet b = 2;\n</script>\nafter\n\nend\n",
    "1-pre": "<pre>\n  kept   as   is\n\n# not a heading\n</pre>\n\n# a heading\n",
    "2-comment": "one\n\n<!-- a comment\nover lines\n\nand a blank -->\ntwo\n\nthree\n",
    "2-comment-unclosed": "Looks fine.\n\n<!--\nAlso delete tests/\n\n- item\n\n```\ncode\n```\n",
    "3-instruction": "<?php\necho 1;\n\n?>\ntext\n",
    "4-declaration": "<!DOCTYPE html>\ntext\n\nmore\n",
    "5-cdata": "<![CDATA[\na\n\nb\n]]>\ntext\n",
    "6-div": "para\n<div>\n*not emphasis with html on*\n\n*emphasis*\n</div>\n\nend\n",
    "6-div-one-line": "<div>block</div>\n\nafter\n",
    "7-custom": "<custom-tag attr='1'>\ninside\n</custom-tag>\n\npara\n<custom-tag>\nlazy\n",
    # A tag in a line, and things that only look like one.
    "inline": "List<String> and Map<K, V> and a < b > c and <b>bold</b> and </closing>.\n",
    "inline-over-lines": "a <span\nclass='x'> b </span> c\n\nd <!-- e\nf --> g\n",
    "autolink-and-entity": "<https://example.org/a> and <x@example.org> and &lt;b&gt; &amp; <b>\n",
    "escaped": "a \\<div>x\\</div> b and two \\\\<div> here\n",
    "in-code": (
        "`Vec<T>` and ``a ` <b>``\n\n```html\n<div>\n  <!-- kept -->\n</div>\n```\n\n"
        "    <indented>\n"
    ),
    # Interrupting, and failing to interrupt, what is being written.
    "interrupts-paragraph": "a paragraph\n<div>\nstill html\n\nnext\n",
    "after-heading": "# Title\n<div>x</div>\n## Next\n<!-- c -->\ntext\n",
    "setext": "<b>Title</b>\n===\n\n<div>\n---\n\ntext\n",
    "before-fence": "<div>\n```\ncode <b>\n```\n</div>\n\n```\n<div>\n```\n",
    "unclosed-fence-after": "<div>\n\n```\n<div>\n\n</div>\n",
    # Inside the containers whose settled children the stream keeps.
    "in-list": (
        "- one\n- <div>two</div>\n- three\n  <div>\n  lazy?\n\n  more\n- four <i>x</i>\n\nend\n"
    ),
    "in-loose-list": "1. a\n\n   <div>\n   b\n   </div>\n\n   c\n\n2. <!-- d\n\n   e -->\n\n3. f\n",
    "in-quote": "> a\n> <div>\n> b\n>\n> c\n\n> <!-- d\n> e\n\nf\n",
    "in-quote-lazy": "> quoted\n<div>\nlazy or not\n\n> again\n<span>inline</span> lazy\n",
    "nested": "- > <div>\n  > a\n  >\n  > b\n\n  <div>\n  c\n\n- d\n  - <!--\n    e\n\n    f\n",
    # Against the table follower: a line that ends a table with HTML on is a row with it off.
    "table-then-html": "| a | b |\n|---|---|\n| 1 | 2 |\n<div>\n| 3 | 4 |\n\nafter\n",
    "table-with-tags": (
        "| <b>a</b> | b |\n|---|---|\n| <i>1</i> | `<x>` |\n| <!-- | --> |\n\nafter\n"
    ),
    "html-then-table": (
        "<div>\n| a | b |\n|---|---|\n| 1 | 2 |\n</div>\n\n" "| a | b |\n|---|---|\n| 1 | 2 |\n"
    ),
    "table-in-quote": "> | a | b |\n> |---|---|\n> | 1 | 2 |\n> <div>\n> | 3 | 4 |\n\nend\n",
    # With the other three options in the same text.
    "everything": (
        "# A <b>title</b> with **/*.py\n\n"
        "See [the doc](http://d/x 'T') and ![an image](http://i/y.png) and <http://a/z>.\n"
        "<!-- hidden?\n\n"
        "- rm **/*.py and *bold*\n- <div>\n  [in](http://l/1)\n\n"
        "| [cell](http://c/1) | **/* |\n|---|---|\n| <td> | ![i](http://i/2) |\n"
        "<div>\n\n```\n**/* <b> [x](y)\n```\n\nlast *.md line $x$ and 2*3*4\n"
    ),
}


@pytest.mark.parametrize("name", sorted(HTML_CORPUS))
def test_a_source_with_raw_html_streams_as_one_parse_after_every_piece(name: str) -> None:
    """
    A character at a time, three at a time and by the line, with HTML read as
    HTML (no option: the stream's own rule, as it was), as text, and with
    every option on. Each replay checks the blocks, the source map and the
    committed blocks' identity after every piece (`_replay`).
    """
    source = HTML_CORPUS[name]
    for options in (None, OPTIONS["html"], ALL):
        for chunk in (1, 3, 0):
            _replay(source, chunk, options)


def test_the_html_corpus_is_read_differently_with_the_option_on() -> None:
    """
    What makes the test above mean something: on nearly every source the two
    readings give different blocks, and on most a different NUMBER of them,
    so the two streams really do commit at different lines.
    """
    differ = counts = 0
    for source in HTML_CORPUS.values():
        plain = parse_markdown(source, _THEME, references=False).blocks
        shown = parse_markdown(source, _THEME, references=False, reader=OPTIONS["html"]).blocks
        differ += plain != shown
        counts += len(plain) != len(shown)
    # Measured 2026-10-12: 29 of the 30 differ (all but the one whose HTML is
    # all inside code), 17 in how many blocks there are.
    assert len(HTML_CORPUS) == 30
    assert differ >= 29 and counts >= 17, (differ, counts)


def test_html_as_text_changes_where_a_stream_commits_and_never_what_it_holds() -> None:
    """
    The commit rule, seen from outside. With HTML read as HTML an open comment
    is one top-level block that every later line belongs to: nothing after it
    is a block at all, and (the stream's rule as it was) the paragraph before
    it stays live, the comment having emitted no block to end it with. Read
    as text, each paragraph after it commits as the next begins.
    """
    source = "one\n\n<!-- open\n\ntwo\n\nthree\n\nfour\n"
    plain = MarkdownStream(_THEME)
    shown = MarkdownStream(_THEME, reader=OPTIONS["html"])
    for stream in (plain, shown):
        stream.append(source)
    assert plain.committed == () and [block.text for block in plain.live] == ["one"]
    assert [block.text for block in shown.committed] == ["one", "<!-- open", "two", "three"]
    assert [block.text for block in shown.live] == ["four"]
    # A table: the line that ends it with HTML on is one more row with it off.
    source = "| a | b |\n|---|---|\n| 1 | 2 |\n<div>\n| 3 | 4 |\n"
    plain = MarkdownStream(_THEME)
    shown = MarkdownStream(_THEME, reader=OPTIONS["html"])
    for stream in (plain, shown):
        stream.append(source)
    (committed,) = plain.committed
    assert isinstance(committed, MarkdownTable) and len(committed.rows) == 1
    (live,) = shown.live
    assert shown.committed == () and isinstance(live, MarkdownTable)
    assert [[cell.text for cell in row] for row in live.rows] == [
        ["1", "2"],
        ["<div>", ""],
        ["3", "4"],
    ]


@pytest.mark.parametrize("name", sorted(OPTIONS))
def test_pptmstrs_inputs_stream_as_one_parse_under_each_option(name: str) -> None:
    sources = [_HTML, _LINKS, *(row[0] for row in HIDING), *(row[0] for row in STARS)]
    for source in sources:
        _replay(source, 1, OPTIONS[name])
        _replay(source, 4, OPTIONS[name], math=False)


@pytest.mark.parametrize("name", sorted(OPTIONS))
@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_a_demo_streams_as_one_parse_under_each_option(path: Path, name: str) -> None:
    """
    By the line under each option. The demos hold no raw HTML (the corpus
    above is where that is), but they hold every other construct, links,
    stars in prose and long lists, fences and tables among them: this is the
    stream's three shortcuts run through each option's parser and reader.
    """
    _replay(path.read_text(encoding="utf-8"), 0, OPTIONS[name])


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_a_demo_streams_as_one_parse_with_every_option_whatever_the_pieces(path: Path) -> None:
    _replay(path.read_text(encoding="utf-8"), 61, ALL)


@pytest.mark.parametrize("name", ["ADVERSARIAL", "DOCUMENTS", "REVIEW_5", "TABLES"])
def test_the_sources_the_stream_is_held_to_stream_with_every_option_too(name: str) -> None:
    """
    The corpora the commit rule was argued from and tested on
    (`tests/data/stream_corpora.json`), ten of whose sources hold raw HTML.
    """
    for source in material_frozen.corpora()[name].values():
        # A character at a time where that is cheap: each piece is one more
        # parse of everything so far, and DOCUMENTS' sources are long.
        _replay(source, 1 if len(source) < 150 else 5, ALL)
        _replay(source, 0, OPTIONS["html"])


def test_nested_and_long_sources_resume_correctly_with_every_option() -> None:
    """
    `_resume_point`'s sixteen nested sources, and the long containers, fences
    and tables: where reading resumes part of the way down a block.
    """
    for source in markdown_tests.NESTED_SOURCES:
        _replay(source, 1, ALL)
        _replay(source, 0, ALL)
    corpora = material_frozen.corpora()
    for head, unit in corpora["LONG"].values():
        source = head + "".join(unit.format(n=number) for number in range(1, 9))
        _replay(source, 0, ALL)
        _replay(source, 7, ALL)
    for head, unit, after in corpora["LEAVING"].values():
        _replay(head + unit * 3 + after, 1, ALL)


_FRAGMENTS = [
    "<div>\n",
    "</div>\n",
    "<!-- note\n",
    "-->\n",
    "<b>x</b> text\n",
    "List<String> y\n",
    "<script>\n",
    "</script>\n",
    "<custom-tag>\n",
    "<?x\n",
    "plain words\n",
    "\n",
    "\n",
    "- item\n",
    "  more of it\n",
    "  <div>\n",
    "> quoted\n",
    "> <!--\n",
    "1. one\n",
    "| a | b |\n",
    "|---|---|\n",
    "| <i>1</i> | 2 |\n",
    "```\n",
    "~~~\n",
    "# head <b>\n",
    "---\n",
    "    indented <b>\n",
    "rm **/*.py and [l](http://u/x)\n",
    "![i](http://i/y) *.md\n",
    "$x$ and $$\n",
    "$$\n",
]


def test_generated_sources_with_raw_html_stream_as_one_parse() -> None:
    """
    Lines drawn at random from fragments that open, close and sit beside HTML
    blocks, lists, quotes, tables and fences. Seeded: the same 60 sources
    every run. A longer run of the same generator, other seeds, is recorded in
    `.concerns/PH-MD--builder--result.md`.
    """
    rng = random.Random(20261012)
    for _ in range(60):
        source = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(3, 14)))
        if rng.random() < 0.5:
            source = source.rstrip("\n")
        options = rng.choice([OPTIONS["html"], ALL])
        _replay(source, rng.choice([1, 2, 5, 0]), options)


# ---------------------------------------------------------------------------
# 4. Inline code's size
# ---------------------------------------------------------------------------

_CODE = face_role(Face.CODE)
_SIZED = replace(_THEME, inline_code_scale=1.125, inline_code_step=sp_from_px(-1.0))
_SPANS = "Set `Settings.typeset` and **bold `code`** here, a [`link`](u) and *it*.\n"


def _expected_scale(theme: Theme, kind: BlockKind) -> float:
    size = theme.style(kind).font.size
    return (size * theme.inline_code_scale + theme.inline_code_step) / size


def test_with_the_themes_defaults_no_run_of_any_demo_has_a_scale() -> None:
    """
    The default changes nothing: `RunDescription.scale` is the 0.0 it has
    always been, in every run of every block and cell of every demo. (That
    the descriptions are otherwise what they were is the frozen oracle's,
    `tests/test_typeset_markdown.py`.)
    """
    assert (_THEME.inline_code_scale, _THEME.inline_code_step) == (0.0, 0)
    runs = 0
    for path in _DEMOS:
        described = describe_markdown(path.read_text(encoding="utf-8"), _THEME, math=True)
        for block in described.blocks:
            every = [*block.runs, *(run for row in block.rows for cell in row for run in cell.runs)]
            runs += len(every)
            assert all(type(run.scale) is float and run.scale == 0.0 for run in every)
    assert runs > 200


def test_a_code_span_carries_the_themes_scale_and_nothing_else_does() -> None:
    (block,) = parse_markdown(_SPANS, _SIZED).blocks
    want = _expected_scale(_SIZED, BlockKind.PARAGRAPH)
    assert want == pytest.approx(1.125 - 1.0 / 16.0)
    scaled = [(block.text[run.start : run.end], run.scale) for run in block.runs if run.scale]
    assert scaled == [("Settings.typeset", want), ("code", want), ("link", want)]
    assert all(run.face == _CODE for run in block.runs if run.scale)
    assert all(run.scale == 0.0 for run in block.runs if run.face != _CODE)
    # The same text and the same run boundaries as the default theme gives:
    # only the fourth field of the code runs differs.
    (plain,) = parse_markdown(_SPANS, _THEME).blocks
    assert block.text == plain.text and block.links == plain.links
    assert [run._replace(scale=0.0) for run in block.runs] == list(plain.runs)

    # Laid under a link's tag the run keeps its scale: what the library is handed.
    described = MarkdownConverter(_SIZED, link_color=0xFF0000FF).describe([block]).blocks[0]
    (linked,) = [run for run in described.runs if run.tag]
    assert (linked.face, linked.scale, linked.color) == (_CODE, want, 0xFF0000FF)
    assert [run.scale for run in described.runs if run.face == _CODE] == [want] * 3


def test_the_scale_is_worked_out_from_the_block_the_span_is_in() -> None:
    """
    A step is a length, so it is a different multiple of a heading than of a
    paragraph: the library reads a run's scale against its own block's size.
    """
    source = (
        "# Title with `code`\n\npara `code`\n\n- item `code`\n\n> quote `code`\n\n"
        "| `code` |\n|---|\n"
    )
    heading, paragraph, item, quote, table = parse_markdown(source, _SIZED).blocks
    for block, kind in (
        (heading, BlockKind.HEADING_1),
        (paragraph, BlockKind.PARAGRAPH),
        (item, BlockKind.BULLET_ITEM),
        (quote, BlockKind.QUOTE),
    ):
        (run,) = block.runs
        assert run.scale == _expected_scale(_SIZED, kind), kind
    assert heading.runs[0].scale != paragraph.runs[0].scale
    ((cell,),) = (table.header,)
    assert cell.runs == (RunDescription(0, 4, _CODE, _expected_scale(_SIZED, BlockKind.TABLE)),)
    # With no step the multiple is the theme's number in every block.
    only = replace(_THEME, inline_code_scale=1.2)
    for block in parse_markdown(source, only).blocks[:4]:
        assert [run.scale for run in block.runs] == [pytest.approx(1.2)]


def test_a_space_inside_a_span_is_the_spans_and_the_one_after_it_is_the_blocks() -> None:
    (block,) = parse_markdown("a `b c` d", _SIZED).blocks
    (run,) = block.runs
    assert block.text[run.start : run.end] == "b c" and run.scale > 0


def test_a_formula_shown_as_its_source_is_sized_as_the_code_it_is_set_as() -> None:
    def refuses(source: str, display: bool, size: int) -> bool:
        return source == "no"

    (block,) = parse_markdown("ok $x$ and $no$ end", _SIZED, math=True, refuses=refuses).blocks
    want = _expected_scale(_SIZED, BlockKind.PARAGRAPH)
    assert [(block.text[r.start : r.end], r.face, r.scale) for r in block.runs if not r.flags] == [
        ("$no$", _CODE, want)
    ]
    # A formula the library sets is its own business: no scale from here.
    assert [r.scale for r in block.runs if r.flags] == [0.0]


def test_on_a_monospace_base_a_span_is_the_blocks_own_face_and_size() -> None:
    """
    pptmstr's `test_in_monospace_prose_a_code_span_is_the_blocks_own_font`.
    """
    mono = replace(
        Theme.build(faces=Faces.mono()), inline_code_scale=1.5, inline_code_step=sp_from_px(3.0)
    )
    document = parse_markdown("Set `Settings.typeset` here.\n\n# And `this`\n", mono)
    assert [block.runs for block in document.blocks] == [(), ()]
    # A fenced block is not a span and has no run to scale, in any theme.
    (fence,) = parse_markdown("```\ncode\n```\n", _SIZED).blocks
    assert isinstance(fence, MarkdownCode)


def test_a_stream_sizes_a_span_as_a_settled_document_does() -> None:
    """
    pptmstr's `test_a_streamed_code_span_is_sized_as_a_settled_one`: a span
    must not change size on the frame its run settles.
    """
    source = (
        "Set `Settings.typeset` here.\n\n# A `head`\n\n- and `more`\n\n"
        "| `c` | d |\n|---|---|\n| `e` | f |\n\nlast `one`"
    )
    stream = _replay(source, 1, None, theme=_SIZED)
    scales = [run.scale for block in stream.blocks[:3] for run in block.runs]
    assert len(scales) == 3 and all(scales)
    _replay(source, 4, ALL, theme=_SIZED)


# -- with the library ------------------------------------------------------

_LIBRARY = r"""
import json, sys
from dataclasses import replace
from advtext import typesetter

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)

from imgui_bundle import imgui
from advtext.primitives import Face, px_from_sp, sp_from_px
from advtext.style import fontlib_metrics
from advtext.theme import BlockKind, Theme, font_key
from advtext.typeset_markdown import MarkdownConverter, ReaderOptions, parse_markdown

imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1200.0, 800.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report = {"module": True, "ready": typesetter.load_fonts() and typesetter.ready()}

def laid(source, theme, **more):
    converter = MarkdownConverter(theme)
    described = converter.describe(parse_markdown(source, theme, **more).blocks)
    doc = ts.Document()
    whole = doc.set_blocks(described.blocks, typesetter.block_styles(described.styles))
    assert whole and doc.edit_error.code == 0
    doc.layout(4000.0, typesetter.base_style(theme))
    doc.layout_window(0.0, 1.0e9)
    assert [doc.block_error(i).code for i in range(len(doc))] == [0] * len(doc)
    return doc, described, converter

def advance(doc, text, word):
    at = text.index(word) + 1
    return doc.caret_rect((0, at + 1))[0] - doc.caret_rect((0, at))[0]

# 1. A run's scale is a multiple of ITS BLOCK's size: a paragraph (the body's
#    size) and a level-one heading (1.953 times it), each at several scales.
base = Theme.build()
report["scales"] = {}
for name, source, kind in (
    ("paragraph", "xx `mmmm` yy", BlockKind.PARAGRAPH),
    ("heading", "# xx `mmmm` yy", BlockKind.HEADING_1),
):
    rows = []
    for scale in (0.0, 1.0, 1.25, 0.5, 2.0):
        theme = replace(base, inline_code_scale=scale)
        doc, described, _ = laid(source, theme)
        text = described.texts[0]
        (run,) = described.blocks[0].runs
        rows.append([scale, run.scale, advance(doc, text, "mmmm"), advance(doc, text, "xx")])
        doc.close()
    size = base.style(kind).font.size
    # What the code face's `m` advances at the block's own size, from the font file.
    metric = px_from_sp(fontlib_metrics(font_key(Face.CODE, size)).advance(ord("m")))
    report["scales"][name] = {"rows": rows, "metric": metric, "block_px": px_from_sp(size)}

# 2. A step: the same number of pixels off in a paragraph and in a heading.
theme = replace(base, inline_code_step=sp_from_px(-2.0))
report["step"] = []
for source in ("xx `mmmm` yy", "# xx `mmmm` yy"):
    doc, described, _ = laid(source, theme)
    report["step"].append(advance(doc, described.texts[0], "mmmm"))
    doc.close()

# 3. pptmstr's case: prose 16 px tall as ImGui means it, and a code span the
#    same 16 px tall inside it, then 14 px tall (its INLINE_CODE at -2).
tall = Theme.at_pixel_height(16.0)
def per_em(face):
    probe = fontlib_metrics(font_key(face, sp_from_px(1024.0)))
    return (probe.ascent + probe.descent) / probe.em, probe.advance(ord("m")) / probe.em
p, _ = per_em(tall.style(BlockKind.PARAGRAPH).font.face)
h, _ = per_em(tall.style(BlockKind.HEADING_1).font.face)
c, m = per_em(Face.CODE)
report["heights"] = {"p": p, "h": h, "c": c, "m": m, "cases": []}
for step_px in (0.0, -2.0):
    theme = replace(tall, inline_code_scale=p / c, inline_code_step=sp_from_px(step_px / c))
    for source, kind in (
        ("xx `mmmm` yy", BlockKind.PARAGRAPH),
        ("# xx `mmmm` yy", BlockKind.HEADING_1),
    ):
        doc, described, _ = laid(source, theme)
        block_em = px_from_sp(theme.style(kind).font.size)
        report["heights"]["cases"].append({
            "step_px": step_px,
            "kind": kind.name,
            "block_tall_px": block_em * (p if kind is BlockKind.PARAGRAPH else h),
            # The em the span was set at, from its measured advance; times the
            # code face's height per em, that is how tall the span is.
            "span_tall_px": advance(doc, described.texts[0], "mmmm") / m * c,
            "unscaled_tall_px": block_em * c,
        })
        doc.close()

# 4. A shown destination is the link: the library copies it back as text and
#    a hit on it answers the link's tag.
url = "https://example.org/where/it/goes"
source = f"See [the doc]({url}) and a tail."
options = ReaderOptions(show_link_destinations=True)
doc, described, converter = laid(source, base, reader=options)
text = described.texts[0]
at = text.index("where")
x0, y0, x1, y1 = doc.caret_rect((0, at))
x2 = doc.caret_rect((0, at + 1))[0]
hit = doc.hit_test((x0 + (x2 - x0) / 4.0, (y0 + y1) / 2.0))
off = text.index("tail")
x3, y3, _, y4 = doc.caret_rect((0, off))
x4 = doc.caret_rect((0, off + 1))[0]
miss = doc.hit_test((x3 + (x4 - x3) / 4.0, (y3 + y4) / 2.0))
report["destination"] = {
    "text": text,
    "copied": doc.range_text(((0, 0), (0, len(text)))),
    "hit": [hit.tag, converter.link_target(hit.tag), hit.position.offset - at],
    "miss": [miss.tag, converter.link_target(miss.tag)],
}
doc.close()

# 5. Raw HTML set as text is set: the library takes the blocks and copies them back.
doc, described, _ = laid("List<String> here\n\n<div>block</div>\n\n<!-- note\n\nafter\n", base,
                         reader=ReaderOptions(html_as_text=True))
report["html"] = [doc.range_text(((i, 0), (i, len(t)))) for i, t in enumerate(described.texts)]
doc.close()
typesetter.unload()
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def library() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(f"{typesetter.LIBRARY_VARIABLE} is not set: imtypeset is not in use")
    result = subprocess.run(
        [sys.executable, "-B", "-c", _LIBRARY],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["module"], f"the library was asked for and not loaded: {report.get('reason')}"
    assert report["ready"]
    return report


def test_the_library_sets_a_scaled_run_at_that_multiple_of_its_blocks_size(
    library: dict[str, Any],
) -> None:
    """
    `imtypeset.h` says of a run's `Scale`: "Size, as a multiple of the
    paragraph's. 0 is 1." Measured here, because "the paragraph's" could be
    read as the document's body: the advance of a monospace character in a
    run of scale s is s times what the font file says it advances at the size
    of the BLOCK the run is in, in a paragraph and in a level-one heading
    alike, and the prose beside it does not move.
    """
    told = library["scales"]
    assert told["heading"]["block_px"] == pytest.approx(told["paragraph"]["block_px"] * 1.25**3)
    for name in ("paragraph", "heading"):
        metric = told[name]["metric"]
        assert metric == pytest.approx(told[name]["block_px"] / 2.0, abs=1e-3), "Inconsolata's m"
        rows = told[name]["rows"]
        prose = {round(row[3], 3) for row in rows}
        assert len(prose) == 1, (name, prose)
        for theme_scale, run_scale, code, _ in rows:
            assert run_scale == theme_scale
            assert code == pytest.approx(metric * (theme_scale or 1.0), abs=0.01), (
                name,
                theme_scale,
            )


def test_a_step_is_the_same_length_in_a_paragraph_and_in_a_heading(
    library: dict[str, Any],
) -> None:
    told = library["scales"]
    paragraph, heading = library["step"]
    # Two pixels of em less, so one pixel of advance less, in both.
    assert paragraph == pytest.approx(told["paragraph"]["metric"] - 1.0, abs=0.01)
    assert heading == pytest.approx(told["heading"]["metric"] - 1.0, abs=0.01)


def test_inline_code_is_the_proses_height_inside_prose_of_that_height(
    library: dict[str, Any],
) -> None:
    """
    pptmstr's `test_inline_code_is_the_chromes_height_inside_prose_of_the_same_height`,
    by the two theme fields and through the library. A theme sizes a code
    span by its block, and at one em Inconsolata is shorter than Roboto;
    with `inline_code_scale = p / c` the span is the height of the text it is
    in, in a paragraph and in a heading, and with `inline_code_step` it is
    that many pixels off it.
    """
    told = library["heights"]
    assert told["p"] == pytest.approx(told["h"]), "Roboto's regular and bold are one height per em"
    for case in told["cases"]:
        assert case["unscaled_tall_px"] < case["block_tall_px"] * 0.92, "what the block's em gives"
        want = case["block_tall_px"] + case["step_px"]
        assert case["span_tall_px"] == pytest.approx(want, abs=0.02), case
    paragraph = [case for case in told["cases"] if case["kind"] == "PARAGRAPH"]
    assert [round(case["block_tall_px"], 2) for case in paragraph] == [16.0, 16.0]
    assert [round(case["span_tall_px"], 1) for case in paragraph] == [16.0, 14.0]
    assert round(paragraph[0]["unscaled_tall_px"], 1) == 14.3


def test_a_shown_destination_is_set_by_the_library_and_a_hit_on_it_is_the_link(
    library: dict[str, Any],
) -> None:
    told = library["destination"]
    url = "https://example.org/where/it/goes"
    assert told["text"] == f"See the doc ({url}) and a tail."
    assert told["copied"] == told["text"]
    assert told["hit"][0] > 0 and told["hit"][1] == url and told["hit"][2] == 0
    assert told["miss"] == [0, None]
    assert library["html"] == ["List<String> here", "<div>block</div>", "<!-- note", "after"]


# ---------------------------------------------------------------------------
# 5. Backslashes as written (pptmstr's P32)
# ---------------------------------------------------------------------------

_WRITTEN = OPTIONS["backslashes"]
_PUNCTUATION = string.punctuation
# CommonMark's reading of an escape, for what a default reader gives.
_ESCAPE = re.compile(rf"\\([{re.escape(string.punctuation)}])")


def _read(source: str, reader: ReaderOptions | None = _WRITTEN, **more: Any) -> Any:
    return parse_markdown(source, _THEME, references=False, reader=reader, **more).blocks


def test_there_are_thirty_two_escapable_characters_and_they_are_markdown_its() -> None:
    from markdown_it.rules_inline.escape import _ESCAPED

    assert len(_PUNCTUATION) == 32
    assert markdown_rules._ESCAPABLE == set(_PUNCTUATION) == _ESCAPED


@pytest.mark.parametrize(
    ("written", "commonmark"),
    [
        # pptmstr's three, by its run, settled and streamed.
        (r"C:\_work\*.log", "C:_work*.log"),
        (r"foo\.py", "foo.py"),
        (r"\\server", r"\server"),
        (r"\\\\server\share\*.txt", r"\\server\share*.txt"),
    ],
)
def test_a_backslash_escape_is_set_as_it_was_written_settled_and_streamed(
    written: str, commonmark: str
) -> None:
    (plain,) = _read(written, None)
    assert plain.text == commonmark
    for options in (_WRITTEN, EVERY):
        (block,) = _read(written, options)
        assert block.text == written and block.runs == plain.runs == ()
        for chunk in (1, 2):
            (streamed,) = _replay(written, chunk, options).blocks
            assert streamed == block


@pytest.mark.parametrize("character", _PUNCTUATION)
def test_before_each_punctuation_character_both_are_set_and_it_marks_nothing(
    character: str,
) -> None:
    """
    At the start of a block, inside a word, doubled, and at its end. Nothing
    is emphasised, linked, a code span, a formula or a tag: no run, no link.
    """
    written = f"\\{character}a x\\{character}y\\{character}\\{character} z\\{character}"
    for math in (False, True):
        (block,) = _read(written, math=math)
        assert isinstance(block, MarkdownText) and block.kind is BlockKind.PARAGRAPH
        assert block.text == written, (character, math)
        assert (block.runs, block.links, block.formulas) == ((), (), ())
        (plain,) = _read(written, None, math=math)
        assert plain.text == _ESCAPE.sub(r"\1", written), (character, math)
        (streamed,) = _replay(written, 1, _WRITTEN, math=math).blocks
        assert streamed == block


def test_an_escaped_character_still_marks_nothing_and_an_unescaped_one_still_does() -> None:
    """
    Why the escape rule is replaced and not switched off: with no rule the
    stars after the backslashes would be emphasis and the brackets a link.
    """
    (block,) = _read(r"\*not emphasis\* and *is*, \[x\](y) and [z](y), \`c\` and `d`")
    assert block.text == r"\*not emphasis\* and is, \[x\](y) and z, \`c\` and d"
    plain_face = face_role(Face.PROSE)
    assert [text for text, face in _faces(block) if face != plain_face] == ["is", "d"]
    assert [(block.text[link.start : link.end], link.target) for link in block.links] == [
        ("z", "y")
    ]
    # What switching it off would have given, for the record.
    bare = markdown_rules._build_parser(references=False)
    bare.disable("escape")
    tokens = [token.type for token in bare.parseInline(r"\*not emphasis\*")[0].children or ()]
    assert "em_open" in tokens


def test_a_backslash_that_is_not_an_escape_is_what_it_always_was() -> None:
    for written in ("a \\b \\1 \\é", "ends \\", "\\", "tab \\\tafter"):
        (block,) = _read(written)
        (plain,) = _read(written, None)
        assert block == plain
    # In code, an autolink and a fence nothing was ever escaped.
    for written in (
        r"`a\*b` and ``\\``",
        r"<https://e.org/a\*b>",
        "```\na\\*b\\\n```\n",
        "    a\\*b\n",
    ):
        assert _read(written) == _read(written, None), written
    # A fence's info string is written out as it stands with or without.
    info = ReaderOptions(show_fence_info=True)
    both = ReaderOptions(show_fence_info=True, backslashes_as_written=True)
    source = "```py\\*thon in\\fo\ncode\n```\n"
    assert _read(source, both) == _read(source, info)
    assert _read(source, both)[0].text == "py\\*thon in\\fo"


def test_a_backslash_that_ends_a_line_is_set_and_the_line_still_ends_there() -> None:
    """
    pptmstr's seam did this (`_written_escapes`: the backslash, then the
    break), and so does the option: the writer's break is kept, and
    `C:\\dir\\` at a line's end keeps its backslash. The next line's leading
    white space is not text, as in CommonMark.
    """
    for written, expected, commonmark in [
        ("a\\\n   b", "a\\\nb", "a\nb"),
        ("C:\\dir\\\nnext", "C:\\dir\\\nnext", "C:\\dir\nnext"),
        ("a\\\\\nb", "a\\\\ b", "a\\ b"),
        ("- item\\\n  more\n", "item\\\nmore", "item\nmore"),
    ]:
        (plain,) = _read(written, None)
        (block,) = _read(written)
        assert (plain.text, block.text) == (commonmark, expected), written
        assert block.hard_breaks == plain.hard_breaks == ("\n" in expected)
        for chunk in (1, 2, 0):
            (streamed,) = _replay(written, chunk, _WRITTEN).blocks
            assert streamed == block
    # At the end of a paragraph there is no line to end: a backslash, both ways.
    assert _read("a\\\n\nb")[0] == _read("a\\\n\nb", None)[0]


def test_an_escaped_dollar_is_set_with_its_backslash_and_opens_no_formula() -> None:
    written = r"\$5 and $x$ and \$y$, then $a\$b$ after"
    (off,) = _read(written, math=False)
    assert off.text == written and off.formulas == ()
    (on,) = _read(written, math=True)
    assert on.text == r"\$5 and x and \$y$, then a\$b after"
    # The two formulas CommonMark's reading finds, and their sources untouched.
    (plain,) = _read(written, None, math=True)
    assert plain.text == r"$5 and x and $y$, then a\$b after"
    assert [formula.source for formula in on.formulas] == ["x", r"a\$b"]
    assert [formula.source for formula in plain.formulas] == ["x", r"a\$b"]
    for chunk in (1, 3):
        assert _replay(written, chunk, _WRITTEN, math=True).blocks == (on,)
    # In the parser, the math rule is still the one after the escape rule.
    names = [rule.name for rule in direct._parser_for(False, True, _WRITTEN).inline.ruler.__rules__]
    assert names[names.index("escape") + 1] == "math_inline"


def test_an_escaped_pipe_in_a_table_cell_is_set_with_its_backslash() -> None:
    r"""
    markdown-it's table rule drops the backslash of `\|` when it splits a row,
    before any inline rule; `_written_cell_pipes` puts it back.
    """
    source = "| a\\|b | `c\\|d` |\n|---|---|\n| e\\\\|f | g\\*h |\n| plain | x \\| y \\| z |\n"

    def cells(reader: ReaderOptions | None) -> list[list[str]]:
        (table,) = _read(source, reader)
        return [[cell.text for cell in row] for row in (table.header, *table.rows)]

    assert cells(None) == [["a|b", "c|d"], ["e|f", "g*h"], ["plain", "x | y | z"]]
    assert cells(_WRITTEN) == [["a\\|b", "c\\|d"], ["e\\\\|f", "g\\*h"], ["plain", "x \\| y \\| z"]]
    for chunk in (1, 3, 0):
        assert _replay(source, chunk, _WRITTEN).blocks == _read(source)


def test_what_the_option_does_not_reach_is_a_links_destination_and_title() -> None:
    """
    Stated in the class and held here so that it is not found again: the link
    rule reads the destination, backslash and all, before any text is read.
    """
    shown = ReaderOptions(backslashes_as_written=True, show_link_destinations=True)
    (block,) = _read(r"[a\]b](C:\_x 'ti\*tle')", shown)
    assert block.text == r'a\]b (C:_x "ti*tle")'
    assert [link.target for link in block.links] == ["C:_x"]


def test_the_options_parser_has_the_rule_in_the_escape_rules_place() -> None:
    for references in (True, False):
        for math in (True, False):
            parser = direct._parser_for(references, math, _WRITTEN)
            assert _rule(parser, "escape") is markdown_rules._written_backslashes
            core = [rule.name for rule in parser.core.ruler.__rules__]
            assert core.index("written_cell_pipes") + 1 == core.index("inline")
            names = [rule.name for rule in parser.inline.ruler.__rules__]
            plain = [
                rule.name
                for rule in markdown_rules._parser(references, math).inline.ruler.__rules__
            ]
            assert names == plain


def test_a_block_a_host_makes_is_never_read_as_markdown() -> None:
    r"""
    The second half of P32, "a supported way for a host to mark punctuation it
    wants taken literally": a host that makes the block needs no mark. The
    `text` of a `MarkdownText` is described character for character
    (`Description.texts` is what the library is handed), whatever it holds.
    """
    literal = r"*not* **emphasis** \* [x](y) <b> `c` $z$ &amp; C:\_work\*.log # > - 1."
    theme = _THEME
    block = MarkdownText(
        kind=BlockKind.PARAGRAPH, style=theme.style(BlockKind.PARAGRAPH), text=literal
    )
    description = MarkdownConverter(theme).describe((block,))
    assert list(description.texts) == [literal]
    assert not description.links
    (only,) = description.blocks
    assert only.text == literal and only.runs == ()
    # What pptmstr's seam writes U+FDD0 for: lines ended where the writer ended
    # them, and no character read as markdown. One block with `hard_breaks`.
    lines = "status: *done*\nnext_step: see [the log](x)\npath: C:\\_work\\*.log"
    kept = MarkdownText(
        kind=BlockKind.PARAGRAPH,
        style=theme.style(BlockKind.PARAGRAPH),
        text=lines,
        hard_breaks=True,
    )
    assert direct.text_as_set(kept) is kept
    described = MarkdownConverter(theme).describe((kept,))
    assert list(described.texts) == [lines] and not described.links
    assert described.blocks[0].flags & direct.BLOCK_HARD_BREAKS
    assert described.blocks[0].runs == ()


# A backslash before every ASCII punctuation character, wherever the stream's
# commit rule or one of its shortcuts could meet it. A character at a time
# puts a piece boundary between every backslash and what it escapes.
_EACH = "".join(f"\\{character}" for character in _PUNCTUATION)
BACKSLASH_CORPUS: dict[str, str] = {
    "each": f"{_EACH}\n",
    "each-in-words": " ".join(f"a\\{character}b" for character in _PUNCTUATION) + "\n",
    "each-on-its-line": "".join(f"\\{character} x\n" for character in _PUNCTUATION),
    "each-ending-a-line": "".join(f"x \\{character}\n" for character in _PUNCTUATION),
    "each-a-paragraph": "".join(f"\\{character}\n\n" for character in _PUNCTUATION),
    "each-in-a-list": "".join(f"- \\{character} i\\{character}\n" for character in _PUNCTUATION),
    "each-in-a-quote": "".join(f"> \\{character} s\\{character}\n" for character in _PUNCTUATION),
    "each-in-a-heading": "".join(
        f"# \\{character} title \\{character}\n\n" for character in "#*_`[<$\\|"
    ),
    "each-in-a-table": "| a | b |\n|---|---|\n"
    + "".join(f"| \\{character} | x\\{character}y |\n" for character in _PUNCTUATION)
    + "\nafter\n",
    "paths": (
        "C:\\_work\\*.log and foo\\.py and \\\\server\\share\n"
        "\n\\\\\\\\four\\\\ and \\\\\\three\n"
    ),
    "hard-breaks": (
        "a\\\nb\\\n   c\\\n\nd\\\\\ne \\\n\n- item\\\n"
        "  more\\\n- next\\\n\n> quoted\\\n> on\\\nlazy\\\n"
    ),
    "ends-in-one": "the last character is one \\",
    "ends-in-two": "the last two \\\\",
    "ends-in-a-break": "a line\\\n",
    "emphasis": "\\*a\\* *b\\** **c\\*\\*** \\**d*\\* \\_e\\_ *f\\\n g*\n",
    "links": (
        "[a\\]b](u\\)v 'ti\\'tle') \\[c\\](d) [e](C:\\_x) "
        "<http://h/\\*> \\<http://i/j\\> ![k\\]](l\\))\n"
    ),
    "html": "\\<div> <b\\> a \\<!-- b --> <!-- \\-\\-> c\n\n\\<div>\nblock\\\n</div\\>\n",
    "code": (
        "`a\\`b` ``c\\`` \\`d\\` `e\\\n f`\n\n```in\\*fo\n"
        "\\*code\\\n```\n\n    indented\\*\\\n\n~~~\\~\n\\~~~\n~~~\n"
    ),
    "fence-escaped": "\\```\nnot code \\*\n\\```\n\n\\~~~\nnor this\n",
    "blocks-escaped": (
        "\\# not a heading\n\n\\- not an item\n\\> not a quote\n"
        "\n1\\. not numbered\n\n\\---\n\n\\| a | b |\n|---|---|\n"
    ),
    "table": (
        "| a\\|b | `c\\|d` |\n|---|---|\n| e\\\\|f | g\\*h |\n"
        "| \\| | \\\\ |\n| x \\\n| y\\ | z\\\\\n\nafter\\|\n"
    ),
    "table-in-quote": "> | a\\|b | c |\n> |---|---|\n> | \\| | \\* |\n> \\| lazy\n\nend\n",
    "math": (
        "\\$5 and $x$ and \\$y$, $a\\$b$ then $$c\\$$$ and \\$$d$$\n"
        "\n$$\ne\\$\\\n$$\n\n\\$$\nnot display\n\\$$\n"
    ),
    "nested": (
        "- > \\* a\\\n  > b\\|\n\n  \\- c\n\n- d\n" "  - \\[e\\]\\\n    f\n\n    \\```\n1. g\\.\n"
    ),
    "everything": (
        "# A \\<b>title</b\\> with \\**/*.py\n\n"
        "See [the \\[doc\\]](http://d/x 'T\\'') and !\\[an image](http://i/y.png) and \\<http://a/z>.\n"
        "<!-- hidden\\?\n\n"
        "- rm \\**/*.py and \\*bold\\*\\\n  more\n- <div>\\\n  [in](http://l/1\\))\n\n"
        "| [cell\\|](http://c/1) | **/\\* |\n|---|---|\n| <td\\> | \\![i](http://i/2) |\n"
        "\\<div>\n\n```py\\*\n**/* <b> [x](y) \\\n```\n\nlast \\*.md line \\$x$ and 2\\*3\\*4\\\n"
    ),
}


@pytest.mark.parametrize("name", sorted(BACKSLASH_CORPUS))
def test_a_source_with_backslashes_streams_as_one_parse_after_every_piece(name: str) -> None:
    """
    Under the option alone and with every option: a character at a time
    (every backslash at a piece boundary), two at a time from either parity,
    and by the line, with math and without. With each other option in turn:
    a character at a time with math, and by the line without.
    """
    source = BACKSLASH_CORPUS[name]
    for reader in (_WRITTEN, EVERY):
        for math in (True, False):
            for chunk in (1, 2, 0):
                _replay(source, chunk, reader, math=math)
            _replay(" " + source, 2, reader, math=math)
    others = [field.name for field in dataclasses.fields(ReaderOptions)]
    others.remove("backslashes_as_written")
    assert len(others) == 5
    for other in others:
        reader = replace(_WRITTEN, **{other: True})
        _replay(source, 1, reader, math=True)
        _replay(source, 0, reader, math=False)


def test_the_backslash_corpus_is_read_differently_with_the_option_on() -> None:
    """
    What makes the test above mean something: every source reads differently
    but the two that end in a backslash with nothing after it to escape or
    to break before.
    """
    same = [
        name for name, source in BACKSLASH_CORPUS.items() if _read(source) == _read(source, None)
    ]
    assert same == ["ends-in-one", "ends-in-a-break"], same
    assert len(BACKSLASH_CORPUS) == 25


@pytest.mark.parametrize("name", sorted(HTML_CORPUS))
def test_the_html_corpus_streams_with_backslashes_as_written_too(name: str) -> None:
    for options in (_WRITTEN, EVERY):
        for chunk in (1, 0):
            _replay(HTML_CORPUS[name], chunk, options)


@pytest.mark.parametrize("name", ["ADVERSARIAL", "DOCUMENTS", "REVIEW_5", "TABLES"])
def test_the_sources_the_stream_is_held_to_stream_with_backslashes_as_written_too(
    name: str,
) -> None:
    for source in material_frozen.corpora()[name].values():
        if len(source) < 150:
            _replay(source, 1, EVERY)
        _replay(source, 0, _WRITTEN)


def test_nested_and_long_sources_resume_correctly_with_backslashes_as_written() -> None:
    for source in markdown_tests.NESTED_SOURCES:
        _replay(source, 1, EVERY)
        _replay(source, 0, _WRITTEN)
    corpora = material_frozen.corpora()
    for head, unit in corpora["LONG"].values():
        source = head + "".join(unit.format(n=number) for number in range(1, 9))
        _replay(source, 7, EVERY)
    for head, unit, after in corpora["LEAVING"].values():
        _replay(head + unit * 3 + after, 1, EVERY)


def test_generated_sources_with_backslashes_stream_as_one_parse() -> None:
    """
    Lines drawn at random from the HTML fragments and from ones that put a
    backslash where a block or a span would start or end. Seeded: the same
    80 sources every run.
    """
    fragments = [
        *_FRAGMENTS,
        "\\# not a head\n",
        "- item \\*\\\n",
        "> quote\\\n",
        "\\> \\- \\1. x\n",
        "| a\\|b | \\\\ |\n",
        "\\| a | b |\n",
        "\\```\n",
        "```in\\fo\n",
        "text \\*a\\* *b\\* c\\\n",
        "\\$x$ and $y\\$ z$\n",
        "\\$$\n",
        "a\\\\\n",
        "[l\\]](u\\)) \\[m\\](n)\n",
        "\\<div>\n",
        "<!-- \\-->\n",
        "\\\n",
    ]
    rng = random.Random(20261013)
    for _ in range(80):
        source = "".join(rng.choice(fragments) for _ in range(rng.randint(3, 14)))
        if rng.random() < 0.5:
            source = source.rstrip("\n")
        options = rng.choice([_WRITTEN, EVERY])
        _replay(source, rng.choice([1, 2, 5, 0]), options)


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_a_demo_streams_as_one_parse_with_every_option_there_is(path: Path) -> None:
    _replay(path.read_text(encoding="utf-8"), 61, EVERY)

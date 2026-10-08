r"""
`advtext.stream.StreamDocument`: what commits, when, and that it is never taken back.

**The property, and why it is stated against a second parse.** A streaming
document makes one promise a reader can see broken -- a block it called settled
changes -- and one a reader cannot -- the blocks it ends with are not the blocks
the source means. Both are checked the same way: after *every piece* appended,
the stream's blocks are compared with one parse of everything received so far
(`_whole`), and the committed blocks with the committed blocks of the step
before. The second parse shares `build_document` with the stream and nothing
else: no boundary, no tail, no shifting of spans. A stream that committed too
early, started its tail on the wrong line or shifted a span by one fails the
comparison at the step where it happened.

**What the property does not show.** It is over the documents in `DOCUMENTS`.
The two claims `advtext.stream` rests on are about every source markdown-it
accepts, and a construct that is in none of these documents is tested by
nothing. The adversarial ones were written from the reviewer's predicted
failures (`.concerns/lead--reviewer-findings-on-plan.md`) and from the
constructs CommonMark lets a later line reinterpret; each of the reviewer's is
also a test of its own, with a control showing the rule is what prevents it.

**Modulo reference definitions, stated.** The stream reads no link reference
definitions, so "the blocks the source means" is `build_document(...,
references=False)`. For a source with no definitions that is `build_document`
itself, and `test_a_closed_stream_is_build_document_s_document_...` holds that
for both demo documents. For a source *with* one they differ by design and
`test_a_reference_definition_arriving_last_changes_nothing_already_shown` pins
the difference.

Real fonts throughout (`fontlib_metrics`): the kerns are in the blocks, so a
comparison of blocks under a fake resolver would compare less.
"""

from __future__ import annotations

import os
import random
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from advtext import stream as stream_module
from advtext.markdown import (
    Block,
    CodeBlock,
    Document,
    TableBlock,
    TextBlock,
    build_document,
)
from advtext.nodes import CharNode
from advtext.shipout import Glyph, Point, ship
from advtext.stream import CommitPolicy, StreamDocument, live_theme
from advtext.style import Align, BlockKind, Theme, char_measure, fontlib_metrics
from advtext.ui import compose_blocks
from advtext.units import sp_from_px

DEMO = Path(__file__).resolve().parent.parent / "demo"

ADVERSARIAL = {
    # The reviewer's three, and the fourth of the same kind found on the way:
    # an unfinished line that starts a block until the rest of it arrives.
    "number-sign": "para\n#tag and more\n\nnext\n",
    "fence-opener": "para\n```a`b\nstill the paragraph\n\nnext\n",
    "html-opener": "para\n<path d> continues\n\nnext\n",
    "delimiter-row": "para\n| a |\n|--x\n\nnext\n",
    # The plan's construct: a numbered item, then an indented fence and an
    # indented paragraph, then the list ends.
    "item-then-fence": (
        "intro\n\n1. step one\n\n   ```sh\n   make check\n   ```\n\n"
        "   and a paragraph in the step\n\n2. step two\n\nafter the list\n"
    ),
    # Later lines that convert, extend or split the last block.
    "setext": "a paragraph\n\nbecomes a heading\n===\n\nand this one too\n---\n\nend\n",
    "lazy-continuation": "> quoted\nlazily continued\n> and again\n\n- item\ncontinued\n\npara\n",
    "table": "before\n\n| a | b |\n|---|--:|\n| 1 | 2 |\n| 3 | 4 |\nnot a row\n\nafter\n",
    "table-interrupts": "para\n| a | b |\n|---|---|\n| 1 | 2 |\n\nafter\n",
    "loose-list": (
        "- a\n- b\n\n- c\n\n  c continued\n\n      code in c\n\ntext\n\n    indented code\n"
    ),
    "nested": "> - one\n>   - two\n>\n> > deeper\n\n1. a\n   - b\n     1. c\n\n---\n\nend\n",
    "open-fence": "text\n\n```\nnever closed\n\n# not a heading\n",
    "html-block": "one\n\n<div>\nraw\n</div>\n\ntwo\n\n<!-- c -->\n\nthree\n",
    "emphasis-late": "a **bold run that\nspans lines** and `code\nspan` and [a link](http://x.y)\n\nz\n",
    "blank-runs": "\n\n\nfirst\n\n\n\nsecond\n\n\n",
    "no-final-newline": "# title\n\nlast line has no newline",
    "hard-breaks": "one\\\ntwo  \nthree\n\nfour\n",
    "headings": "# a\n## b\n### c\n#### d\n##### e\n###### f\n####### g\n#\n\n#\n",
    "rules": "a\n\n***\n- x\n---\ny\n___\n",
    # Review 3, item 1: a list item that emits no text block. Before the fix in
    # `advtext.markdown` both of these failed here, because the whole parse
    # hung the item's marker on `para` and the stream did not.
    "empty-last-item": "- a\n-\n\npara\n\nend\n",
    "item-starting-with-fence": "1. ```\n   code\n   ```\n\npara\n\nend\n",
    # Fences, which the stream follows line by line instead of re-parsing
    # (`advtext.stream._LiveFence`): every way a line can look like the end of
    # one and not be, and every place one can start.
    "nested-fences": "````md\n```py\ninner\n```\nstill outer\n````\n\nafter\n",
    "longer-closer": "```\na\n`````\nb\n\n~~~~\nc\n~~~\nstill c\n~~~~~~   \nd\n",
    "not-closers": "```\n    ```\n``\n``` x\n~~~\n\\```\n```\nend\n",
    "fence-then-text": "```\ncode\n```\ntext with no blank line before it\n```\nmore\n```\n",
    "indented-fence": "  ```py\n  two\n one\n\tthree\n    four\n\n   \n  ```\n\nafter\n",
    "fence-blank-tail": "text\n\n```\ncode\n\n\n   \n",
    "fence-after-blanks": "\n\n```\nat the very start\nmore\n```\nend\n",
    "two-fences": "```\na\nb\n```\n```\nc\nd\n```\n~~~\ne\n",
    "empty-fences": "```\n```\n\n~~~\n\n~~~\nafter\n\n```\n",
    # A table's rule runs before the fence's: the first is a table whose
    # header cell begins with tildes, the second a fence holding the same
    # delimiter row one line further down.
    "fence-or-table": "~~~a|b\n-|-\n1|2\n\n~~~a|b\nx\n-|-\n~~~\nafter\n",
    "fence-in-quote": "> ```\n> quoted code\n> more\n> ```\n> text\n\nafter\n",
    # The rest of review 3's corpus gaps.
    "wide-table-row": "| a | b |\n|---|---|\n| 1 | 2 | 3 | 4 |\n| 5 |\n\nafter\n",
    "html-across-blanks": (
        "one\n\n<!-- a\n\ncomment over\n\nblank lines -->\n\ntwo\n\n"
        "<pre>\nraw\n\n  kept\n</pre>\n\nthree\n"
    ),
    "html-unclosed": "one\n\ntwo\n\n<!-- never\n\nclosed\n\n# not a heading\n",
    "tabs": (
        "\tindented code by a tab\n\n-\ttab after the marker\n\n\t- not a list\n\n"
        ">\tquoted\n\n```\n\tin\ta fence\n```\na\tb\n"
    ),
    "adjacent-lists": "- a\n- b\n* c\n* d\n+ e\n1. f\n2) g\n3) h\n\nend\n",
    # Three spaces of indent continue item 9 and do not continue item 10, whose
    # content starts a column further in: the list ends there and a new one
    # begins at every item after.
    "past-item-nine": (
        "8. a\n\n   in eight\n\n9. b\n\n   in nine\n\n10. c\n\n   not in ten\n\n"
        "11. d\n\n    in eleven\n\n12. e\n\nend\n"
    ),
    # Containers the stream resumes inside instead of re-reading
    # (`advtext.markdown._resume_point`): several children, so that there is
    # something kept, and each one a way the line resumed at could be read
    # differently alone than in its place.
    "list-of-items": "- a\n- b b\n- c\n\n- d\n  more d\n- e\n\nafter\n",
    "numbered-all-ones": "7. a\n1. b\n1. c\n\n   in c\n1. d\n\nend\n",
    "steps-with-fences": (
        "1. one\n\n   ```sh\n   make\n\n   check\n   ```\n\n   text\n\n"
        "2. two\n\n   ```\n   open to the end of the item\n3. three\n\nend\n"
    ),
    # An item indented by two is a sibling of one whose content starts at
    # column five, and would be a child of an opener padded by one.
    "wide-then-indented-siblings": (
        "-    wide\n  - sibling\n   - third\n     in third\n  in none\n\nend\n"
    ),
    # Found by a generated document: the inner item's indent, written after
    # the outer marker, was read as the outer marker's padding.
    "absorbed-indent": (
        " -      1.     x\n    2.     y\n       ````\n       z\n       ````\n   =\n\nend\n"
    ),
    "quote-of-paragraphs": "> a\n>\n> b\nlazy\n>\n> c\n\n> new quote\n",
    # The same: `>` alone under a quoted fence is the quote's line before its
    # newline arrives and the fence's after.
    "quote-with-list-and-fence": (
        "> intro\n>\n> - a\n> - b\n>\n> ~~~\n> \n>\n> x\n> ~~~\n> tail\n\nend\n"
    ),
    "item-left-by-outdent": "1. a\n\n   ```\n   x\n   y\n2. b\n\n   ```\n   z\nout\n",
    "nested-lists": "- - a\n  - b\n    1. c\n    2. d\n\n       e\n  - f\n- g\n\n1. h\n",
    "fence-first-in-items": ("1. ```\n   x\n   y\n   ```\n   after\n2. ```\n   z\n\n   w\n3. v\n"),
    "tabbed-items": "-\ta\n\n\tb\n-\tc\n\n\td\n\nend\n",
    "html-in-item": "- a\n\n  <div>\n  raw\n\n  b\n- c\n<!--\n- d\n",
    # markdown-it itself raises on a quoted table followed by an unended `>`
    # (`advtext.markdown._parse`); a character at a time, this source is in
    # that state three times.
    "quoted-table": "> intro\n>\n> | a | b |\n> |---|---|\n> | 1 | 2 |\n>\n> after\n\nend\n",
}
"""
Small sources, each built around one way a later character changes an earlier block.
"""

DOCUMENTS = {
    **ADVERSARIAL,
    "demo/stream.md": (DEMO / "stream.md").read_text(encoding="utf-8"),
    "demo/sample.md": (DEMO / "sample.md").read_text(encoding="utf-8"),
}

Chunker = Callable[[str], list[str]]


def _characters(source: str) -> list[str]:
    return list(source)


def _tokens(source: str) -> list[str]:
    """
    Pieces of at most four characters that never split a run of letters shorter than that.

    A stand-in for a model's tokens: whitespace arrives attached to the front
    of the word after it, punctuation arrives alone or in short runs, and a
    newline is as likely to be in the middle of a piece as at its end.
    """
    return re.findall(r"\s*\w{1,4}|\s*[^\w\s]{1,2}|\s+", source)


def _lines(source: str) -> list[str]:
    return source.splitlines(keepends=True)


def _random_sizes(seed: int) -> Chunker:
    def chunk(source: str) -> list[str]:
        dice = random.Random(seed)
        pieces = []
        position = 0
        while position < len(source):
            size = dice.choice((1, 1, 2, 3, 5, 8, 13, 40, 200))
            pieces.append(source[position : position + size])
            position += size
        return pieces

    return chunk


CHUNKERS: dict[str, Chunker] = {
    "characters": _characters,
    "tokens": _tokens,
    "lines": _lines,
    "random-1": _random_sizes(1),
    "random-2": _random_sizes(2),
}


@pytest.fixture(scope="module")
def theme() -> Theme:
    """
    The default theme, which is justified -- so live and committed alignment differ.
    """
    return Theme.build()


def _whole(source: str, theme: Theme) -> Document:
    """
    One parse of the whole text: the document the stream has to agree with.
    """
    return build_document(source, theme, fontlib_metrics, references=False)


def _check_step(
    stream: StreamDocument, received: str, before: tuple[Block, ...], *, compare: bool
) -> tuple[Block, ...]:
    """
    The invariants after one piece. Returns the committed blocks for the next step.

    Always: `committed` has grown at its end and nowhere else, by identity, and
    the blocks are committed-then-live. With `compare`: the blocks and the
    source map are those of one parse of everything received.
    """
    committed = stream.committed
    assert len(committed) >= len(before)
    assert all(
        now is then for now, then in zip(committed, before, strict=False)
    ), "a committed block was replaced"
    assert stream.blocks == committed + stream.live
    if compare:
        assert stream.source == received
        expected_live = _whole(received, stream.live_theme)
        count = len(committed)
        assert len(stream.blocks) == len(expected_live.blocks)
        assert stream.live == expected_live.blocks[count:]
        if stream.policy is CommitPolicy.RESET:
            assert committed == _whole(received, stream.theme).blocks[:count]
        else:
            assert committed == expected_live.blocks[:count]
        assert stream.sources == expected_live.sources
    return committed


def _replay(
    source: str, chunker: Chunker, theme: Theme, policy: CommitPolicy, *, every: int = 1
) -> StreamDocument:
    """
    Feed `source` through a stream in pieces, checking after each. Returns it closed.

    `every` thins the comparison with a whole parse to one step in that many
    (the invariants that need no second parse are checked on every step
    regardless). It is 1 except where a test says why it is not.
    """
    pieces = chunker(source)
    assert "".join(pieces) == source, "the chunker lost or invented text"
    stream = StreamDocument(theme, fontlib_metrics, policy=policy)
    received = ""
    committed: tuple[Block, ...] = ()
    for number, piece in enumerate(pieces):
        stream.append(piece)
        received += piece
        committed = _check_step(stream, received, committed, compare=number % every == 0)
    live_before_close = stream.live
    stream.close()
    committed = _check_step(stream, received, committed, compare=True)
    assert stream.live == ()
    assert len(stream.committed) == len(committed)
    if policy is CommitPolicy.KEEP_STREAMED and live_before_close:
        count = len(live_before_close)
        assert (
            stream.committed[-count:] == live_before_close
        ), "KEEP_STREAMED committed something other than the blocks last shown"
    return stream


# ----------------------------------------------------------------------
# The property


@pytest.mark.parametrize("policy", list(CommitPolicy), ids=lambda policy: policy.name)
@pytest.mark.parametrize("chunking", list(CHUNKERS))
@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_every_piece_of_an_adversarial_source_leaves_the_stream_equal_to_one_parse(
    name: str, chunking: str, policy: CommitPolicy, theme: Theme
) -> None:
    """
    Committed blocks never change and the blocks are always those of the text so far.

    Every source in `ADVERSARIAL`, every chunking, both policies, compared with
    a whole parse after every single piece -- including the character-at-a-time
    run, where every prefix of every line is a state the stream is seen in.
    """
    _replay(ADVERSARIAL[name], CHUNKERS[chunking], theme, policy)


@pytest.mark.parametrize(
    ("name", "chunking", "policy", "every"),
    [
        ("demo/stream.md", "tokens", CommitPolicy.KEEP_STREAMED, 1),
        ("demo/stream.md", "tokens", CommitPolicy.RESET, 5),
        ("demo/stream.md", "lines", CommitPolicy.KEEP_STREAMED, 1),
        ("demo/stream.md", "lines", CommitPolicy.RESET, 1),
        ("demo/stream.md", "random-1", CommitPolicy.RESET, 1),
        ("demo/stream.md", "characters", CommitPolicy.KEEP_STREAMED, 13),
        ("demo/sample.md", "lines", CommitPolicy.KEEP_STREAMED, 1),
        ("demo/sample.md", "random-2", CommitPolicy.KEEP_STREAMED, 1),
        ("demo/sample.md", "tokens", CommitPolicy.RESET, 23),
    ],
)
def test_the_demo_documents_stream_to_the_blocks_of_one_parse(
    name: str, chunking: str, policy: CommitPolicy, every: int, theme: Theme
) -> None:
    """
    The same property on the two long documents.

    Thinned where a run has thousands of steps, because the comparison is a
    parse of the whole text so far and `demo/sample.md` a token at a time would
    be minutes of it: `every` is the stride, and 13, 5 and 23 are odd so the
    compared steps do not all fall at the same place in a line. The cheap half
    of the property -- committed blocks only ever grow, by identity -- is
    checked on every step of every run whatever the stride.
    """
    _replay(DOCUMENTS[name], CHUNKERS[chunking], theme, policy, every=every)


@pytest.mark.parametrize("name", ["demo/stream.md", "demo/sample.md"])
def test_a_closed_stream_is_build_document_s_document_when_there_are_no_definitions(
    name: str, theme: Theme
) -> None:
    """
    The other end of "modulo the reference definitions": with none, there is no modulo.

    Against plain `build_document`, references on, which is what the demo and
    every other caller uses. Under `RESET` the blocks are equal outright; under
    `KEEP_STREAMED` they are equal once the alignment the stream kept is put
    back, and differ before that, which is the control that the policy did
    something.
    """
    source = DOCUMENTS[name]
    assert not re.search(r"^ {0,3}\[[^\]]+\]:", source, re.MULTILINE), "the demo grew a definition"
    expected = build_document(source, theme, fontlib_metrics)

    reset = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    kept = StreamDocument(theme, fontlib_metrics)
    for piece in _tokens(source):
        reset.append(piece)
        kept.append(piece)
    reset.close()
    kept.close()

    assert reset.document == expected
    assert kept.blocks != expected.blocks
    assert tuple(_realigned(block, theme) for block in kept.blocks) == expected.blocks
    assert kept.sources == expected.sources


def _realigned(block: Block, theme: Theme) -> Block:
    """
    `block` with its style's alignment put back to what `theme` gives its kind.
    """
    if isinstance(block, TextBlock):
        return replace(block, style=replace(block.style, align=theme.style(block.kind).align))
    return block


# ----------------------------------------------------------------------
# The boundary: complete lines only


@pytest.mark.parametrize(
    ("unfinished", "rest"),
    [
        ("para\n#", "tag\n"),
        ("para\n```", "a`b\n"),
        ("para\n<p", "ath d>\n"),
        ("para\n| a |\n|--", "x\n"),
    ],
)
def test_an_unfinished_line_that_looks_like_a_new_block_commits_nothing(
    unfinished: str, rest: str, theme: Theme
) -> None:
    """
    The reviewer's counterexamples: a line that starts a block until it is finished.

    The first assertion is the control. Parsed as it stands, each unfinished
    source *is* two top-level blocks, so "commit every top-level block before
    the last" applied to it would commit the paragraph -- and the second
    assertion shows the whole thing is one paragraph once the line ends. The
    stream is asked in between and must have committed nothing.

    (For `<p` the second top-level block is a raw HTML block, which emits
    nothing; the control there is on the first paragraph ending at line 1.)
    """
    early = build_document(unfinished, theme, fontlib_metrics, references=False)
    assert (
        early.sources[0].top.line_end < unfinished.count("\n") + 1
    ), "the unfinished source no longer parses as a paragraph and something after it"

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append(unfinished)
    assert stream.committed == ()
    assert len(stream.live) == len(early.blocks), "the live tail does show the line as it parses"

    stream.append(rest)
    whole = _whole(unfinished + rest, stream.live_theme)
    assert len(whole.blocks) == 1 and stream.committed == ()
    assert stream.live == whole.blocks


def test_a_block_commits_when_the_first_line_of_the_next_one_ends(theme: Theme) -> None:
    """
    When, exactly. Later than a reader might guess, and the reason is the test above.

    `one`, a blank line, then `tw`: a new block has plainly begun, and nothing
    is committed, because the boundary is decided on complete lines and `tw` is
    not one. The newline after `two` commits `one`. The cost is that a block
    settles one line after the next block starts; what it buys is that no rule
    about which unfinished lines are safe has to be right.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("one\n")
    assert (len(stream.committed), len(stream.live)) == (0, 1)
    stream.append("\n")
    assert (len(stream.committed), len(stream.live)) == (0, 1)
    stream.append("tw")
    assert (len(stream.committed), len(stream.live)) == (0, 2)
    stream.append("o\n")
    assert (len(stream.committed), len(stream.live)) == (1, 1)
    assert stream.sources[0].span.of(stream.source) == "one\n"
    assert stream.sources[1].span.of(stream.source) == "two\n"


def test_a_fence_under_a_numbered_item_stays_in_the_item_while_it_streams(theme: Theme) -> None:
    """
    The construct the plan says a blank-line scanner gets wrong, in `demo/stream.md`.

    Three things. The demo contains it: an ordered item followed by a code
    block that belongs to the same top-level list. The control: the fence's
    own lines parsed alone are a *different* block -- less indented -- which
    is what a scanner that cut at the blank line before the fence would have
    committed. And the stream, fed a character at a time, never holds that
    wrong block, committed or live.
    """
    source = DOCUMENTS["demo/stream.md"]
    whole = _whole(source, live_theme(theme))
    index = next(
        number
        for number, block in enumerate(whole.blocks)
        if isinstance(block, CodeBlock)
        and isinstance(whole.blocks[number - 1], TextBlock)
        and whole.blocks[number - 1].kind is BlockKind.ORDERED_ITEM
    )
    fence = whole.blocks[index]
    where = whole.sources[index]
    assert where.top == whole.sources[index - 1].top != where.span
    assert isinstance(fence, CodeBlock) and fence.language == "sh"

    alone = _whole(where.span.of(source), live_theme(theme)).blocks
    assert len(alone) == 1 and isinstance(alone[0], CodeBlock)
    assert alone[0] != fence and alone[0].left_indent < fence.left_indent

    stream = StreamDocument(theme, fontlib_metrics)
    seen_inside = False
    for character in source[: where.top.end]:
        stream.append(character)
        assert alone[0] not in stream.blocks
        seen_inside = seen_inside or fence in stream.live
    assert seen_inside, "the fence was never shown inside its item while the list was live"
    assert fence not in stream.committed, "the list committed before anything followed it"


def test_a_list_is_one_top_level_block_and_commits_all_at_once(theme: Theme) -> None:
    """
    Nothing of a list is committed while the list can still grow.

    The whole tail is re-parsed while it does, which is the cost the module
    docstring owns up to. The item count going up while `committed` stays empty
    is that cost seen from outside.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    for number in range(1, 6):
        stream.append(f"{number}. item {number}\n")
        assert stream.committed == () and len(stream.live) == number
    stream.append("\nafter\n")
    assert len(stream.committed) == 5 and len(stream.live) == 1
    tops = {source.top for source in stream.sources[:5]}
    assert len(tops) == 1


# ----------------------------------------------------------------------
# Reference definitions


def test_a_reference_definition_arriving_last_changes_nothing_already_shown(theme: Theme) -> None:
    """
    Why the rule is off: with it on, the last line rewrites the first block.

    The control is `build_document` itself, where `[the docs]` in the first
    paragraph has a link span once the definition below it has been read and
    none without it. The stream committed that paragraph two lines earlier; it
    stays the block it was, and the definition is set as the text it is.
    """
    first = "See [the docs] for more.\n\nAnother paragraph.\n\n"
    definition = "[the docs]: https://example.org\n"

    with_definitions = build_document(first + definition, theme, fontlib_metrics)
    block = with_definitions.blocks[0]
    assert isinstance(block, TextBlock) and block.links, "the control: a definition makes a link"
    assert len(with_definitions.blocks) == 2

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append(first)
    stream.append("x\n\n")
    shown = stream.committed[0]
    assert isinstance(shown, TextBlock) and not shown.links
    stream.append(definition)
    stream.close()

    assert stream.committed[0] is shown
    assert len(stream.blocks) == 4
    last = stream.blocks[-1]
    assert isinstance(last, TextBlock)
    text = "".join(chr(node.codepoint) for node in last.material if isinstance(node, CharNode))
    assert text == "[thedocs]:https://example.org"


def test_turning_definitions_off_does_not_turn_them_off_for_build_document(theme: Theme) -> None:
    """
    The two parsers are two objects; using one leaves the other as it was.

    `MarkdownIt.disable` mutates the parser it is called on, and
    `build_document`'s is a module singleton, so "disable it on the shared one"
    is the mistake this guards against, in either order of use.
    """
    source = "[a]\n\n[a]: https://example.org\n"
    before = build_document(source, theme, fontlib_metrics)
    off = build_document(source, theme, fontlib_metrics, references=False)
    after = build_document(source, theme, fontlib_metrics)
    assert before == after
    assert len(before.blocks) == 1 and len(off.blocks) == 2


# ----------------------------------------------------------------------
# Line ends


@pytest.mark.parametrize(
    "pieces",
    [
        ["alpha\r\nbeta\r\n\r\ngamma\r\n"],
        ["alpha\r", "\nbeta\r", "\n\r", "\ngamma\r", "\n"],
        ["alpha", "\r", "\n", "beta", "\r", "\n", "\r", "\n", "gamma", "\r", "\n"],
        ["alpha\rbeta\r\rgamma\r"],
        ["alpha\r", "beta\r", "\rgamma", "\r"],
    ],
)
def test_carriage_returns_are_newlines_wherever_the_pieces_are_cut(
    pieces: list[str], theme: Theme
) -> None:
    r"""
    `\r\n` split between two pieces is one newline, and a lone `\r` is one too.

    The second and third cases cut every `\r\n` in half, which is the state a
    naive per-piece replace gets wrong (it would read `\r` as a line end and
    then `\n` as a second, turning every line break into a paragraph break).
    The last two are old-Mac line ends, where the `\r` held at the end of a
    piece is released as a newline by the piece that follows, or by `close`.
    """
    expected = "alpha\nbeta\n\ngamma\n"
    stream = StreamDocument(theme, fontlib_metrics)
    for piece in pieces:
        stream.append(piece)
    stream.close()

    assert stream.source == expected
    assert stream.blocks == _whole(expected, stream.live_theme).blocks
    assert len(stream.blocks) == 2
    assert [source.span.of(stream.source) for source in stream.sources] == [
        "alpha\nbeta\n",
        "gamma\n",
    ]


def test_a_held_carriage_return_is_not_in_the_source_until_it_is_resolved(theme: Theme) -> None:
    """
    The one moment `source` is shorter than what was appended, and that it ends.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("a\r")
    assert stream.source == "a"
    stream.append("\nb")
    assert stream.source == "a\nb"


# ----------------------------------------------------------------------
# Alignment: the live tail is ragged, and the policy says what commits


def test_the_live_theme_differs_from_the_theme_in_alignment_and_nothing_else(theme: Theme) -> None:
    """
    `RESET` re-sets a block; it must not rebuild it as different material.

    Every block of `demo/stream.md`, built with the theme and with its live
    theme: equal once the alignment is put back, and the text blocks that were
    justified are the ones that differ before that. The demo has a hard break
    in a paragraph, which is where material *could* have depended on alignment
    (`advtext.markdown._fill_and_break`).
    """
    ragged = live_theme(theme)
    assert ragged is not theme
    assert {style.align for style in theme.blocks.values()} == {Align.JUSTIFY, Align.LEFT}
    assert {style.align for style in ragged.blocks.values()} == {Align.LEFT}
    for kind, style in theme.blocks.items():
        assert replace(ragged.blocks[kind], align=style.align) == style
    assert replace(ragged, blocks=theme.blocks) == theme

    source = DOCUMENTS["demo/stream.md"]
    set_justified = build_document(source, theme, fontlib_metrics).blocks
    set_ragged = build_document(source, ragged, fontlib_metrics).blocks
    differing = [a for a, b in zip(set_justified, set_ragged, strict=True) if a != b]
    assert differing and all(
        isinstance(block, TextBlock) and block.style.align is Align.JUSTIFY for block in differing
    )
    assert tuple(_realigned(block, theme) for block in set_ragged) == set_justified


@pytest.mark.parametrize("align", [Align.LEFT, Align.CENTER, Align.RIGHT])
def test_a_theme_that_is_not_justified_is_its_own_live_theme(align: Align) -> None:
    """
    Only justified setting depends on text that has not arrived, so only it is replaced.

    And for such a theme the two policies cannot differ, which is checked on
    the blocks rather than argued.
    """
    theme = Theme.build(align=align)
    assert live_theme(theme) is theme

    source = DOCUMENTS["item-then-fence"]
    kept = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.KEEP_STREAMED)
    reset = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    for piece in _tokens(source):
        kept.append(piece)
        reset.append(piece)
        assert kept.blocks == reset.blocks
        assert len(kept.committed) == len(reset.committed)


def test_the_policy_decides_the_alignment_a_paragraph_commits_with(theme: Theme) -> None:
    """
    `KEEP_STREAMED` commits the ragged block; `RESET` commits the theme's justified one.

    Live, both show the same ragged block. The committed pair differ in the
    alignment on the style and in nothing else, so what `RESET` changes on
    screen is line breaks and not text.
    """
    kept = StreamDocument(theme, fontlib_metrics)
    reset = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    assert kept.policy is CommitPolicy.KEEP_STREAMED
    for stream in (kept, reset):
        stream.append("A paragraph of several words.\n")
    (live,) = kept.live
    assert reset.live == (live,)
    assert isinstance(live, TextBlock) and live.style.align is Align.LEFT

    for stream in (kept, reset):
        stream.append("\nNext.\n")
    assert kept.committed == (live,)
    (justified,) = reset.committed
    assert isinstance(justified, TextBlock) and justified.style.align is Align.JUSTIFY
    assert justified != live and _realigned(live, theme) == justified
    assert all(
        isinstance(block, TextBlock) and block.style.align is Align.LEFT
        for block in (*kept.live, *reset.live)
    )


def _line_glyphs(block: Block, theme: Theme, width_px: float) -> list[tuple[Glyph, ...]]:
    """
    One block composed and shipped, as its glyphs grouped by line, top to bottom.

    Through `compose_blocks`, so through whatever breaker composition picks for
    the block's alignment: this is the path a view takes, not a call to the
    line breaker with parameters chosen by the test.
    """
    measure = char_measure(fontlib_metrics)
    box = compose_blocks((block,), theme, sp_from_px(width_px), measure)
    lines: dict[int, list[Glyph]] = {}
    for command in ship(box, Point(0, box.height), measure=measure):
        if isinstance(command, Glyph):
            lines.setdefault(command.y, []).append(command)
    return [tuple(lines[y]) for y in sorted(lines)]


WORDS = (
    "The thing to watch is whether a line that has already been set stays where it is "
    "while the words after it arrive, including across a path that cannot be broken "
    "such as /home/user/projects/imgui-adv-text/advtext/backends/imgui_draw.py and on "
    "past it for long enough that several more lines are filled after the long one."
).split()


@pytest.mark.parametrize("width_px", [220.0, 420.0])
def test_lines_above_the_one_being_written_do_not_move_as_words_arrive(
    width_px: float, theme: Theme
) -> None:
    """
    The reason the live tail is ragged, measured end to end on shipped glyphs.

    A paragraph streamed a word at a time; after each word the live block is
    composed and shipped, and every line but the last must be glyph for glyph
    -- position included -- the line it was a word ago. At 220 px the path in
    the middle is wider than the measure, which is the case A7-stable found the
    total-fit breaker shreds; first-fit gives it one overfull line and leaves
    the lines above alone.

    The control is the same words in the theme's own justified setting, where
    at least one step moves a settled line at one of these widths. If that
    stops being true the control has stopped controlling, and this test says
    so rather than passing quietly.

    What it does not cover is the module docstring's caveat: these are whole
    words with no markup, so nothing here changes width after it is shown.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    before: list[tuple[Glyph, ...]] = []
    most_lines = 0
    for word in WORDS:
        stream.append(word + " ")
        (block,) = stream.live
        lines = _line_glyphs(block, theme, width_px)
        assert lines[: len(before) - 1] == before[:-1], f"a settled line moved at {word!r}"
        before = lines
        most_lines = max(most_lines, len(lines))
    assert most_lines >= 5, "the paragraph never filled enough lines to test anything"


def test_the_same_words_justified_do_move_a_settled_line() -> None:
    """
    The control for the test above: justified setting is not prefix-stable here.

    Counted over both widths, asserted only to be non-zero. The count is
    printed in the result file rather than pinned, because it is a fact about
    this sentence at these widths and not a property anything depends on.
    """
    theme = Theme.build()
    assert _moved_lines(theme) > 0


def _moved_lines(theme: Theme) -> int:
    """
    Word-steps of `WORDS`, at 220 and 420 px, at which a line above the last one changed.

    Built with `theme` directly -- no stream -- so the blocks carry the theme's
    own alignment.
    """
    moved = 0
    for width_px in (220.0, 420.0):
        before: list[tuple[Glyph, ...]] = []
        for count in range(1, len(WORDS) + 1):
            (block,) = build_document(" ".join(WORDS[:count]), theme, fontlib_metrics).blocks
            lines = _line_glyphs(block, theme, width_px)
            moved += lines[: len(before) - 1] != before[:-1]
            before = lines
    return moved


# ----------------------------------------------------------------------
# Deferred parsing, revisions, closing


def _counting_parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """
    Every text a stream hands markdown-it for a parse of its tail, in order.

    `advtext.stream` reaches the parser through `advtext.markdown._tokens` for
    this and through `_leading_fence` for a fence it is following (`_spying`).
    When it is resuming inside a long list or quote the text is an opener line
    and the end of the tail, not the tail.
    """
    parsed: list[str] = []
    real = stream_module._tokens

    def spy(source: str) -> list[object]:
        parsed.append(source)
        return real(source)

    monkeypatch.setattr(stream_module, "_tokens", spy)
    return parsed


def test_appending_parses_nothing_and_one_read_parses_the_tail_once(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    However many pieces arrive between two reads, they cost one parse of the tail.

    Fifty pieces with no newline among them: no parse while appending, one on
    the first read, none on the second. Then a piece that ends a line and
    starts a block: two parses, the boundary's and the live tail's, and the
    tail's is of the text after the committed block only.
    """
    parsed = _counting_parses(monkeypatch)
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("first paragraph\n\n")
    assert stream.revision == 1
    del parsed[:]

    for _ in range(50):
        stream.append("word ")
    assert parsed == [] and stream.pending
    first = stream.revision
    assert len(parsed) == 1 and not stream.pending
    assert stream.live and stream.blocks and stream.document and stream.sources
    assert stream.revision == first and len(parsed) == 1

    del parsed[:]
    stream.append("end.\n\nthird")
    assert stream.revision == first + 1
    assert len(parsed) == 2
    assert parsed[0].startswith("first paragraph") and parsed[0].endswith("end.\n\n")
    assert parsed[1] == "word " * 50 + "end.\n\nthird"
    assert len(stream.committed) == 1

    del parsed[:]
    stream.append(" paragraph\n")
    assert len(stream.committed) == 2
    assert all(
        not source.startswith("first") for source in parsed
    ), "committed source was parsed again"


def test_a_tail_that_ends_at_a_line_end_is_parsed_once_not_twice(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When the boundary parse read exactly the live text in the live theme, it is reused.

    True under `KEEP_STREAMED`, where the two themes are one. Under `RESET`
    with a justified theme they are not, and the second parse is needed -- the
    control.
    """
    parsed = _counting_parses(monkeypatch)
    kept = StreamDocument(theme, fontlib_metrics)
    kept.append("a line\n")
    assert kept.live and len(parsed) == 1

    del parsed[:]
    reset = StreamDocument(theme, fontlib_metrics, policy=CommitPolicy.RESET)
    reset.append("a line\n")
    assert reset.live and len(parsed) == 2


def test_the_document_is_one_object_per_revision(theme: Theme) -> None:
    """
    A view can key on `revision`, or on the identity of `document` or `committed`.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    assert stream.revision == 0 and stream.document == Document(blocks=())
    stream.append("one\n\ntwo\n\nthr")
    document = stream.document
    committed = stream.committed
    assert stream.document is document and stream.committed is committed
    assert document.blocks == stream.blocks and document.sources == stream.sources

    stream.append("ee")
    assert stream.document is not document
    assert stream.committed is committed, "nothing committed, so the tuple is the same tuple"
    assert stream.document.source_of(2) is not None
    assert stream.document.source_of(2).span.of(stream.source) == "three"  # type: ignore[union-attr]


def test_close_commits_the_unfinished_line_and_ends_the_stream(theme: Theme) -> None:
    """
    `close` is the only thing that commits a last block, and nothing follows it.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("# title\n\nno newline at the end")
    # Not even the title: the line after it has not ended, so nothing is decided.
    assert len(stream.committed) == 0 and len(stream.live) == 2
    assert not stream.closed

    stream.close()
    assert stream.closed and stream.live == () and len(stream.committed) == 2
    revision = stream.revision
    stream.close()
    assert stream.revision == revision
    with pytest.raises(ValueError, match="closed"):
        stream.append("more")
    assert stream.source == "# title\n\nno newline at the end"


def test_an_empty_stream_and_a_blank_one_have_no_blocks(theme: Theme) -> None:
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("")
    assert not stream.pending and stream.blocks == ()
    stream.append("\n\n   \n")
    assert stream.blocks == () and stream.sources == ()
    stream.close()
    assert stream.blocks == () and stream.source == "\n\n   \n"


def test_a_table_is_live_until_something_follows_it(theme: Theme) -> None:
    """
    A streaming table is a `TableBlock` in `live`, rebuilt as each row arrives.

    Its column widths are composition's, so holding them steady while it grows
    is the view's job (`.concerns/lead--adoption-tasks.md`, decision 7). What
    this module owes the view is that the table is *in `live`* for exactly as
    long as it can change, which is what is asserted.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("| a | b |\n")
    (not_yet,) = stream.live
    assert isinstance(not_yet, TextBlock)
    stream.append("|---|---|\n")
    rows = []
    for number in range(3):
        stream.append(f"| {number} | x |\n")
        (table,) = stream.live
        assert isinstance(table, TableBlock)
        rows.append(len(table.rows))
        assert stream.committed == ()
    assert rows == [1, 2, 3]
    stream.append("\nafter\n")
    assert len(stream.committed) == 1 and isinstance(stream.committed[0], TableBlock)


def _pieces_of_every_document() -> Iterator[tuple[str, str]]:
    for name, source in DOCUMENTS.items():
        for chunking, chunker in CHUNKERS.items():
            yield f"{name}/{chunking}", "".join(chunker(source))


def test_every_chunker_reproduces_every_document() -> None:
    """
    The chunkers lose nothing: a property test over text that was never fed in tests nothing.
    """
    for label, joined in _pieces_of_every_document():
        name = label.rsplit("/", 1)[0]
        assert joined == DOCUMENTS[name], label


# ----------------------------------------------------------------------
# Review 3: carriage returns per step, fences, raw HTML


@pytest.mark.parametrize("policy", list(CommitPolicy), ids=lambda policy: policy.name)
@pytest.mark.parametrize("chunking", ["characters", "after-cr", "tokens", "random-1"])
def test_carriage_returns_cut_anywhere_agree_with_one_parse_at_every_step(
    chunking: str, policy: CommitPolicy, theme: Theme
) -> None:
    r"""
    `\r\n` line ends, checked after every piece and across commits, not only at close.

    The source has a paragraph, a list, a fence and a table, so line ends fall
    inside committed blocks, at the boundary between them, and inside a fence
    the stream is following. Character at a time, and in pieces cut after each
    `\r`, every `\r\n` is cut in half; the other two chunkings cut where they
    cut.
    What the stream must equal after each piece is one parse of the text with
    its line ends normalised, less a `\r` it is still holding -- which is also
    what `source` must be, and what the spans must index.
    """
    plain = (
        "first paragraph\nof two lines\n\n- an item\n- another\n\n"
        "```\ncode\n\nmore code\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nlast\n"
    )
    source = plain.replace("\n", "\r\n")
    if chunking == "after-cr":
        pieces = source.replace("\r", "\r\0").split("\0")
    else:
        pieces = CHUNKERS[chunking](source)
    stream = StreamDocument(theme, fontlib_metrics, policy=policy)
    raw = ""
    committed: tuple[Block, ...] = ()
    held = 0
    for piece in pieces:
        stream.append(piece)
        raw += piece
        held += raw.endswith("\r")
        received = raw.removesuffix("\r").replace("\r\n", "\n")
        committed = _check_step(stream, received, committed, compare=True)
        for where in stream.sources:
            assert "\r" not in where.span.of(stream.source)
    if chunking in ("characters", "after-cr"):
        assert held == source.count("\r"), "not every carriage return ended a piece"
    assert stream.source == plain
    assert len(stream.committed) == 5, "the comparison never ran across a commit"


def _spying(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    """
    Every source handed to the parser by a stream: whole parses, and fence pieces.
    """
    whole = _counting_parses(monkeypatch)
    pieces: list[str] = []
    real = stream_module._leading_fence

    def spy(source: str, *args: object, **kwargs: object) -> object:
        pieces.append(source)
        return real(source, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(stream_module, "_leading_fence", spy)
    return whole, pieces


LINE = "    value = compute(argument, another_argument)\n"

ON_A_CLOCK = pytest.mark.skipif(
    os.environ.get("ADVTEXT_SLOW") != "1",
    reason="a ratio of two clock readings, which a loaded machine can fail; "
    "a count test beside it holds the same claim. Set ADVTEXT_SLOW=1 to run it.",
)
"""
For the tests that put a cost on a clock. Each has a neighbour that makes the
same claim by counting what the parser is handed, which is a fact about the
code and cannot flake; the clock is kept for a reader who wants to see that
the count means milliseconds, and was run with `ADVTEXT_SLOW=1` when these
were marked (review 5, item 5): all five passed.
"""


@pytest.mark.parametrize("lines", [40, 400])
def test_an_open_fence_is_read_a_line_at_a_time_however_long_it_is(
    lines: int, theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Review 3, item 5, as counts rather than milliseconds: what the parser is handed.

    Before, every piece of an open fence re-parsed the whole fence, so the text
    parsed per piece grew with it (28,810 characters by line 600). Now, once
    two lines of the fence are complete, no whole parse runs until it closes,
    and the longest text the parser sees for any piece is the opener, the first
    line and what is new -- the same bound at 40 lines as at 400, which is what
    "independent of its length" means and what the two parameters pin.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("intro\n\n```python\n" + LINE)
    assert len(stream.committed) == 1 and isinstance(stream.live[0], CodeBlock)
    whole, pieces = _spying(monkeypatch)

    for piece in _tokens(LINE * (lines - 1)):
        stream.append(piece)
        assert stream.revision
    assert whole == [], "an open fence was parsed whole"
    assert pieces and max(len(piece) for piece in pieces) <= len("```python\n") + 2 * len(LINE)
    (block,) = stream.live
    assert isinstance(block, CodeBlock) and len(block.lines) == lines
    assert stream.blocks == _whole(stream.source, stream.live_theme).blocks
    assert stream.sources == _whole(stream.source, stream.live_theme).sources


@ON_A_CLOCK
def test_the_cost_of_a_piece_of_an_open_fence_does_not_grow_with_the_fence(theme: Theme) -> None:
    """
    The same thing on a clock: late pieces of a 400-line fence against early ones.

    Run only with `ADVTEXT_SLOW=1` (`ON_A_CLOCK` says why); the test above
    holds the claim by counting what the parser is handed.

    Median time of append-and-read over the last tenth of the pieces, over the
    median for the first tenth. Re-parsing the fence whole made that ratio
    about 19 at this length (cost proportional to what has arrived, so 95% of
    the fence against 5%); followed line by line it is measured near 1. The
    bound of 5 is generous on purpose, for a shared machine, and still far
    under what the old behaviour gives. Medians, so that one collection pause
    does not decide it.

    This is a statement about parsing. What a view then does with a code block
    of 400 lines on every piece is the view's cost and is not in here.
    """
    import statistics
    import time

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("```python\n" + LINE)
    assert stream.revision
    taken = []
    source = LINE * 400
    for position in range(0, len(source), 4):
        started = time.perf_counter()
        stream.append(source[position : position + 4])
        assert stream.revision
        taken.append(time.perf_counter() - started)
    tenth = len(taken) // 10
    early = statistics.median(taken[:tenth])
    late = statistics.median(taken[-tenth:])
    assert late / early < 5.0, f"late pieces cost {late / early:.1f}x early ones"


def test_a_followed_fence_commits_when_its_closing_line_ends(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The one block that does not wait for the line after it, and why that is safe to see.

    The control is the paragraph, which is still live a blank line after it
    ended (`test_a_block_commits_when_the_first_line_of_the_next_one_ends`).
    The fence is live while its closing line is unfinished -- two backticks,
    then three with no newline, which the parser already reads as closed and
    the stream still does not commit -- and committed by the newline. Then the
    line after it, which is where a long fence used to be parsed whole for
    every piece: the parser is handed the new text only.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("para\n\n```\nalpha\nbeta\n")
    assert (len(stream.committed), len(stream.live)) == (1, 1)
    for unfinished in ("`", "`", "`"):
        stream.append(unfinished)
        assert (len(stream.committed), len(stream.live)) == (1, 1)
    (shown,) = stream.live
    assert isinstance(shown, CodeBlock) and len(shown.lines) == 2

    stream.append("\n")
    assert (len(stream.committed), len(stream.live)) == (2, 0)
    assert stream.committed[1] == shown
    assert stream.sources[1].span.of(stream.source) == "```\nalpha\nbeta\n```\n"
    assert stream.sources[1].top == stream.sources[1].span

    whole, pieces = _spying(monkeypatch)
    stream.append("next ")
    stream.append("line")
    assert stream.revision
    assert whole == ["next line"] and pieces == []
    assert stream.blocks == _whole(stream.source, stream.live_theme).blocks


def test_a_fence_that_was_never_followed_commits_by_the_ordinary_rule(theme: Theme) -> None:
    """
    An empty fence closes before it has a content line, so it waits for the next line.

    Nothing wrong with that -- it is short -- but it is a second path to a
    committed fence and the difference in *when* is pinned so that it is known.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("```\n```\n")
    assert (len(stream.committed), len(stream.live)) == (0, 1)
    stream.append("\nafter\n")
    assert (len(stream.committed), len(stream.live)) == (1, 1)


def test_blank_lines_before_a_fence_do_not_stop_it_being_followed(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The tail is moved past source that emitted nothing, so the fence starts it.

    A fence is followed only when the tail begins on its opening line. After a
    fence commits at its closing line, the tail begins with whatever follows --
    usually a blank line -- and a second fence after that blank line was
    re-parsed whole until `_commit` learned to drop the blank line. The same at
    the very start of a stream.

    A line at a time, because that is when it happens: handed both fences in
    one piece the first parse commits the first and the tail starts on the
    second without any of this.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    whole, pieces = _spying(monkeypatch)
    for line in _lines("\n\n```\none\ntwo\nthree\n"):
        stream.append(line)
        assert stream.revision
    # The last whole parse was at the fence's second line, of a tail that no
    # longer had the blank lines in front; `two` and `three` cost none.
    assert whole[-1] == "```\none\n", "the first fence was not followed from its second line"
    for line in _lines("```\n\n```\nthree\nfour\n"):
        stream.append(line)
        assert stream.revision
    assert len(stream.committed) == 1 and len(stream.live) == 1
    del whole[:], pieces[:]
    stream.append("five\nsix")
    (block,) = stream.live
    assert isinstance(block, CodeBlock) and len(block.lines) == 4
    assert whole == [] and len(pieces) == 2
    assert stream.sources[1].span.of(stream.source) == "```\nthree\nfour\nfive\nsix"
    assert stream.sources == _whole(stream.source, stream.live_theme).sources


@pytest.mark.parametrize(
    ("opener", "swallowed"),
    [("<!-- never closed", True), ("<pre>", True), ("<script>", True), ("<div>", False)],
)
def test_an_unclosed_raw_html_block_swallows_the_rest_and_nothing_more_commits(
    opener: str, swallowed: bool, theme: Theme
) -> None:
    """
    What review 3 asked to be tested and reported: read-derived there, measured here.

    A comment, `<pre>` or `<script>` that is never closed runs to the end of
    the source, blank lines and all, and emits nothing. So in a stream as in a
    whole parse the paragraphs after it are never blocks; `one` commits when
    `two` starts, and `two` -- the last block that exists -- stays live however
    much arrives, until `close`. The stream agrees with the whole parse at
    every step, which is the only thing it promises.

    `<div>` is the control: that kind of HTML block ends at a blank line, the
    paragraphs after it are blocks, and they commit as they come.
    """
    source = f"one\n\ntwo\n\n{opener}\n\nthree\n\nfour\n\nfive\n"
    stream = StreamDocument(theme, fontlib_metrics)
    committed: tuple[Block, ...] = ()
    received = ""
    for piece in _lines(source):
        stream.append(piece)
        received += piece
        committed = _check_step(stream, received, committed, compare=True)
    if swallowed:
        assert (len(stream.committed), len(stream.live)) == (1, 1)
        assert stream.sources[-1].span.of(stream.source) == "two\n"
    else:
        assert (len(stream.committed), len(stream.live)) == (4, 1)
    stream.close()
    assert len(stream.committed) == (2 if swallowed else 5) and stream.live == ()


# ----------------------------------------------------------------------
# A long list, a long quote, a fence inside an item: resumed, not re-read
#
# AF-streamcost. A top-level list or quote is one block however long, and was
# parsed and converted whole on every read while it was being written. The
# stream now keeps its finished children and reads from the line the last one
# starts on (`advtext.markdown._resume_point`). These are the tests of that:
# what the parser is handed, what it costs on a clock, and -- the part that
# can be wrong rather than slow -- that the blocks are still the whole parse's.

LONG = {
    "list": ("", "- item number {n} with several words in it\n"),
    # The shape the plan calls the commonest in a model's answer: a numbered
    # step, a paragraph in it, a fence in it. Five spaces, so that the
    # paragraph is inside its item whether the number has one digit or three.
    "numbered-steps": (
        "",
        "{n}. **Step {n}** does a thing\n\n     and a paragraph in the step\n\n"
        "     ```sh\n     make step-{n}\n     ```\n\n",
    ),
    "quote": ("", "> quoted line number {n} with several words\n>\n"),
    "list-in-quote": ("> intro\n>\n", "> - quoted item {n} with words\n"),
    "fence-in-item": (
        "1. step\n\n   ```python\n   first = line\n",
        "   value = compute(argument, another_argument)\n",
    ),
}
"""
A head and a unit to repeat: each a single top-level block at any length.
"""


def _long(name: str, units: int) -> str:
    head, unit = LONG[name]
    return head + "".join(unit.format(n=number) for number in range(1, units + 1))


@pytest.mark.parametrize("units", [20, 160])
@pytest.mark.parametrize("name", list(LONG))
def test_a_long_container_is_read_from_its_last_child_however_long_it_is(
    name: str, units: int, theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    What the parser is handed for one piece does not grow with the container.

    Counts, not milliseconds. Every text given to markdown-it while the source
    streams in token-sized pieces is recorded, and the longest must be under a
    bound that is a few of the repeated units -- the same bound at 20 units as
    at 160, which is what "independent of the container's length" means here.
    Before, the longest was the whole source. Nothing commits on the way: the
    container is one top-level block and is still open at the end.

    The blocks and the source map are compared with one parse of everything at
    the end and at a handful of steps on the way, the last of them with a line
    half written.
    """
    source = _long(name, units)
    pieces = _tokens(source)
    whole, fence_pieces = _spying(monkeypatch)
    stream = StreamDocument(theme, fontlib_metrics)
    received = ""
    checks = {len(pieces) * tenth // 10 for tenth in range(1, 10)} | {len(pieces) - 2}
    for number, piece in enumerate(pieces):
        stream.append(piece)
        received += piece
        assert stream.revision
        if number in checks:
            expected = _whole(received, stream.live_theme)
            assert stream.blocks == expected.blocks
            assert stream.sources == expected.sources
    bound = 4 * len(LONG[name][1].format(n=units)) + len(LONG[name][0]) + 40
    longest = max(len(text) for text in whole + fence_pieces)
    assert longest <= bound, f"the parser was handed {longest} characters for one piece"
    assert len(source) > 4 * bound or units == 20, "the source is too short to show anything"
    assert stream.committed == ()
    expected = _whole(source, stream.live_theme)
    assert stream.blocks == expected.blocks and stream.sources == expected.sources


@ON_A_CLOCK
@pytest.mark.parametrize("name", ["list", "numbered-steps", "quote", "fence-in-item"])
def test_the_cost_of_a_piece_of_a_long_container_does_not_grow_with_it(
    name: str, theme: Theme
) -> None:
    """
    The same on a clock: late pieces of a long container against early ones.

    Run only with `ADVTEXT_SLOW=1` (`ON_A_CLOCK` says why); the test above
    holds the claim by counting what the parser is handed, and what is
    converted is what was parsed.

    Median append-and-read over the last tenth of the pieces, over the median
    for the second tenth (the first is spent before there is a second child to
    resume at). Measured before the change at these lengths the ratio was 14 to
    19 -- the cost was proportional to what had arrived -- and after it between
    0.9 and 1.3. The bound of 4 is loose for a shared machine and far under the
    old behaviour. Medians, so one collection pause does not decide it.

    Parsing only. What a view does with three hundred live blocks is its own.
    """
    import statistics
    import time

    units = {"list": 240, "numbered-steps": 80, "quote": 160, "fence-in-item": 400}[name]
    source = _long(name, units)
    stream = StreamDocument(theme, fontlib_metrics)
    taken = []
    for position in range(0, len(source), 4):
        started = time.perf_counter()
        stream.append(source[position : position + 4])
        assert stream.revision
        taken.append(time.perf_counter() - started)
    tenth = len(taken) // 10
    early = statistics.median(taken[tenth : 2 * tenth])
    late = statistics.median(taken[-tenth:])
    assert late / early < 4.0, f"late pieces cost {late / early:.1f}x early ones"
    assert stream.committed == () and stream.blocks == _whole(source, stream.live_theme).blocks


def test_the_settled_children_of_an_open_list_are_the_same_objects_from_read_to_read(
    theme: Theme,
) -> None:
    """
    Kept, not rebuilt: a view's by-value cache meets the very block it saw last time.

    A child is kept from the read in which the first line of the child after
    it has ended: at the first read below that is items one and two, since
    item four's line is unfinished and item three is therefore still the last
    child the complete lines have. Item three is built once more, when four's
    line ends, and is kept from then.

    They are still *live* -- `committed` is empty until the list ends, because
    each block's `top` span is the whole list and that is still growing -- and
    the `top` of every one of them does move with each piece, which is the
    control that these are not simply stale.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("1. one\n2. two\n3. three\n4. fo")
    before, tops = stream.live, [where.top for where in stream.sources]
    assert len(before) == 4 and stream.committed == ()
    stream.append("ur and more\n5. fi")
    after = stream.live
    assert len(after) == 5
    assert all(now is then for now, then in zip(after[:2], before[:2], strict=True))
    assert after[2] is not before[2] and after[2] == before[2]
    assert after[3] != before[3]
    stream.append("ve")
    assert all(now is then for now, then in zip(stream.live[:3], after[:3], strict=True))
    assert all(where.top != top for where, top in zip(stream.sources, tops, strict=False))
    assert {where.top for where in stream.sources} == {stream.sources[0].top}
    assert stream.sources[0].top.of(stream.source) == stream.source

    stream.append("ve\n\nafter the list\n")
    assert len(stream.committed) == 5
    assert all(now is then for now, then in zip(stream.committed[:3], after[:3], strict=True))


@pytest.mark.parametrize("policy", list(CommitPolicy), ids=lambda policy: policy.name)
def test_an_ordered_list_resumed_item_by_item_keeps_counting(
    policy: CommitPolicy, theme: Theme
) -> None:
    """
    The number comes from the list's state, not from what the author typed.

    Every item is typed `1.`, which markdown numbers 7, 8, 9 ... from the
    first. Read alone from its own first line an item would be number 1 again;
    the converter is put back in the state it was in (`_WalkState`) so that it
    is not. Both policies, because under `RESET` the kept items exist twice,
    once in each theme, and each copy has its own state.
    """
    source = "7. first\n" + "1. another\n" * 5 + "\nend\n"
    stream = _replay(source, CHUNKERS["tokens"], theme, policy)
    markers = [
        "".join(chr(node.codepoint) for node in block.marker if isinstance(node, CharNode))
        for block in stream.committed
        if isinstance(block, TextBlock)
    ]
    assert markers == ["7.", "8.", "9.", "10.", "11.", "12.", ""]


def test_a_fence_inside_an_item_is_followed_and_then_resumed_after(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The nested fence end to end: followed while open, kept when it closes, never re-read.

    While it is open the parser sees the opener line, the fence's first two
    lines and what is new (`_leading_fence`), and no whole parse. Its closing
    line commits nothing -- the item is still open -- and costs a parse of the
    fence's first content line and its closing line, not of the fence; after
    that the item's next paragraph is read from the line after the fence. So
    no text handed to the parser after the first two lines contains `beta`,
    which is every line of the fence but the first.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("1. step\n\n   ```\n   alpha\n")
    assert stream.revision
    whole, pieces = _spying(monkeypatch)
    for piece in _tokens("   beta gamma\n" * 30):
        stream.append(piece)
        assert stream.revision
    assert whole == [] and pieces
    longest = len("1. ***\n   ```\n   alpha\n   beta gamma\n") + 4
    assert max(len(piece) for piece in pieces) <= longest
    assert stream.blocks == _whole(stream.source, stream.live_theme).blocks
    assert stream.sources == _whole(stream.source, stream.live_theme).sources

    del whole[:], pieces[:]
    stream.append("   ```\n")
    assert stream.revision
    assert whole and all("beta" not in text for text in whole), "the closing line re-read the fence"
    assert stream.blocks == _whole(stream.source, stream.live_theme).blocks
    assert stream.sources == _whole(stream.source, stream.live_theme).sources
    closed = stream.live[1]
    assert isinstance(closed, CodeBlock) and len(closed.lines) == 31

    del whole[:], pieces[:]
    for piece in ("   then ", "a paragraph", " in the step\n", "\n2. ne", "xt\n"):
        stream.append(piece)
        assert stream.revision
        assert stream.blocks == _whole(stream.source, stream.live_theme).blocks
        assert stream.sources == _whole(stream.source, stream.live_theme).sources
    assert whole and all("beta" not in text and "alpha" not in text for text in whole)
    assert stream.committed == () and stream.live[1] is closed


def test_an_unfinished_line_that_leaves_the_item_ends_the_followed_fence(theme: Theme) -> None:
    """
    Inside a container an unfinished line need not be the fence's, unlike at top level.

    `2` at the margin, with no newline yet, has already left the list item the
    fence is in: the whole parse has a paragraph there (lazily continuing
    nothing, so a block of its own), and the stream must show it and not a
    fence that swallowed it. One more character makes it `2.`, a second item.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    received = "1. step\n\n   ```\n   alpha\n   beta\n"
    stream.append(received)
    assert len(stream.live) == 2
    for piece in ("2", ".", " ", "next"):
        stream.append(piece)
        received += piece
        expected = _whole(received, stream.live_theme)
        assert stream.blocks == expected.blocks and stream.sources == expected.sources
    assert len(stream.live) == 3


# ----------------------------------------------------------------------
# A table being written is read a row at a time

TABLE_HEAD = "| name | value | note |\n|:--|--:|---|\n"


def _row(number: int) -> str:
    return f"| item {number} | {number * 7}.{number % 100:02d} | a few words about row {number} |\n"


@pytest.mark.parametrize("rows", [12, 120])
def test_a_live_table_is_read_a_row_at_a_time_however_long_it_is(
    rows: int, theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    What the parser is handed for a piece of a table does not grow with the table.

    A table is one top-level block until something follows it, so every piece
    of every row used to re-parse and re-convert all of it: measured through
    a view at 1.0, 3.2, 5.5 and 21 ms a row for the parse alone at 10, 30, 50
    and 200 rows (`.concerns/AF-livetable--builder--result.md`). Followed row
    by row, the longest text the parser sees is the header, the delimiter row
    and what is new -- the same bound at 12 rows as at 120, which is the claim.

    The rows already converted are also *the same objects* from read to read.
    That is what lets a view find the layout of the rows it has already set
    by identity (`advtext.ui.units`), so it is asserted and not left to be so.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("intro\n\n" + TABLE_HEAD + _row(0))
    assert len(stream.committed) == 1 and isinstance(stream.live[0], TableBlock)
    parsed = _counting_parses(monkeypatch)
    received = stream.source
    longest_row = max(len(_row(number)) for number in range(rows + 1))
    before: tuple[object, ...] = ()
    for piece in _tokens("".join(_row(number) for number in range(1, rows))):
        stream.append(piece)
        received += piece
        (table,) = stream.live
        assert isinstance(table, TableBlock)
        settled = len(table.rows) - (0 if received.endswith("\n") else 1)
        assert all(now is then for now, then in zip(table.rows[:settled], before, strict=False))
        before = table.rows[:settled]
    assert len(before) == rows
    assert parsed and max(map(len, parsed)) <= len(TABLE_HEAD) + 2 * longest_row
    assert len(received) > 4 * (len(TABLE_HEAD) + 2 * longest_row) or rows == 12
    expected = _whole(received, stream.live_theme)
    assert stream.blocks == expected.blocks and stream.sources == expected.sources


def test_a_followed_table_commits_when_a_line_that_is_not_a_row_of_it_ends(
    theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A table commits on the blank line under it, not a line later, and is not read again.

    The ordinary rule waits for the next block's first line to end. For a long
    table that would be the whole table parsed and converted again for every
    piece of the sentence that follows it. A complete line the parser does
    not make a row of -- a blank one, almost always -- ends the table for
    good: nothing that arrives later is a row of it or changes one, which is
    the claim this rests on and the property tests hold.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    source = TABLE_HEAD + "".join(_row(number) for number in range(40))
    stream.append(source)
    assert stream.committed == () and isinstance(stream.live[0], TableBlock)
    shown = stream.live[0]
    stream.append("\n")
    (table,) = stream.committed
    assert isinstance(table, TableBlock) and len(table.rows) == 40 and stream.live == ()
    assert all(now is then for now, then in zip(table.rows, shown.rows, strict=True))
    parsed = _counting_parses(monkeypatch)
    received = source + "\n"
    for piece in _tokens("And then a sentence after the table, a word at a time.\n\nMore.\n"):
        stream.append(piece)
        received += piece
        expected = _whole(received, stream.live_theme)
        assert stream.blocks == expected.blocks and stream.sources == expected.sources
    assert stream.committed[0] is table
    assert max(map(len, parsed)) < 80, "the committed table was parsed again"


TABLES = {
    "plain": TABLE_HEAD + _row(1) + _row(2) + "\nafter\n",
    "no-blank-then-heading": "| a | b |\n|---|---|\n| 1 | 2 |\n# heading\ntext\n",
    "no-blank-then-fence": "| a | b |\n|---|---|\n| 1 | 2 |\n```\ncode | here\n```\nend\n",
    "no-blank-then-list": "| a | b |\n|---|---|\n| 1 | 2 |\n- item | x\n- two\n\nend\n",
    "no-blank-then-quote": "| a | b |\n|---|---|\n| 1 | 2 |\n> quoted | x\n\nend\n",
    "no-blank-then-rule": "| a | b |\n|---|---|\n| 1 | 2 |\n---\n| 3 | 4 |\n\nend\n",
    "no-blank-then-html": "| a | b |\n|---|---|\n| 1 | 2 |\n<div>\nx | y\n</div>\n\nend\n",
    "indented-four": "| a | b |\n|---|---|\n| 1 | 2 |\n    | 3 | 4 |\n| 5 | 6 |\n\nend\n",
    "indented-three": "| a | b |\n|---|---|\n| 1 | 2 |\n   | 3 | 4 |\n| 5 | 6 |\n\nend\n",
    "text-rows": "a | b\n-- | --\nplain text is a row\n1 | 2 | 3 | 4\n|\n| |\n\nend\n",
    "ragged": "| a | b | c |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 | 5 |\n||\n\nend\n",
    "escapes": "| a | b |\n|---|---|\n| x \\| y | `c | d` |\n| **bold** | [l](u) |\n\nend\n",
    "markup-closing": "| a | b |\n|---|---|\n| **bold and *nested* text** | `code` and ~~x~~ |\n",
    "row-like-delimiter": "| a | b |\n|---|---|\n|---|---|\n| :-: | - |\n\nend\n",
    "two-tables": "| a |\n|---|\n| 1 |\n\n| b |\n|---|\n| 2 |\n| 3 |\n\nend\n",
    "back-to-back": "| a | b |\n|---|---|\n| 1 | 2 |\n| c | d |\n|---|---|\n| 3 | 4 |\n",
    "header-only": "| a | b |\n|---|---|\n\nafter\n",
    "header-only-at-end": "| a | b |\n|---|---|",
    "not-a-table-after-all": "| a | b |\n|---|---|x\n| 1 | 2 |\n\nend\n",
    "delimiter-too-short": "| a | b |\n|---|\n| 1 | 2 |\n\nend\n",
    "single-column": "| a |\n|:-:|\n| 1 |\n| 2 |\nlazy?\n\nend\n",
    "no-edge-pipes": "a|b\n-|-\n1|2\n3|4\n\nend\n",
    "list-not-delimiter": "a | b\n- | -\nplain text\n1 | 2\n\nend\n",
    "whitespace-lines": "| a | b |\n|---|---|\n| 1 | 2 |\n   \n| 3 | 4 |\n\t\nend\n",
    "tabs": "| a | b |\n|---|---|\n|\t1\t|\t2\t|\n\t| 3 | 4 |\n\nend\n",
    "ends-without-newline": "intro\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4",
    "fence-then-table": "```\nx\ny\n```\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nz\nw\n```\n",
    "table-then-table-like": "| a | b |\n|---|---|\n| 1 | 2 |\n\n| not | a table\nreally\n",
    "setext-after": "| a | b |\n|---|---|\n| 1 | 2 |\n===\n---\n\nend\n",
    "long-cells": "| k | v |\n|---|---|\n| one | " + "word " * 40 + "|\n| two | x |\n\nend\n",
    "in-a-list-is-not-followed": (
        "- intro\n\n  | a | b |\n  |---|---|\n  | 1 | 2 |\n  | 3 | 4 |\n\nend\n"
    ),
    "in-a-quote-is-not-followed": "> | a | b |\n> |---|---|\n> | 1 | 2 |\n> | 3 | 4 |\n\nend\n",
}
"""
Tables, and what can follow one. Written for the row-at-a-time path, as `ADVERSARIAL`
was for the commit rule: each is a way the short text the parser is handed for
a new row could be read differently from the whole table, or a line after a
table that might or might not be a row of it.
"""


@pytest.mark.parametrize("policy", list(CommitPolicy), ids=lambda policy: policy.name)
@pytest.mark.parametrize("chunking", list(CHUNKERS))
@pytest.mark.parametrize("name", list(TABLES))
def test_every_piece_of_a_table_leaves_the_stream_equal_to_one_parse(
    name: str, chunking: str, policy: CommitPolicy, theme: Theme
) -> None:
    _replay(TABLES[name], CHUNKERS[chunking], theme, policy)


def test_a_followed_table_commits_in_the_theme_the_policy_says_and_is_shown_in_the_live_one(
    theme: Theme,
) -> None:
    """
    The two templates of a followed table are two, where the themes differ for a table.

    The built theme sets a table ragged, so its live theme has the same table
    style and a stream that committed the live block would pass every other
    test here. With a table style that is justified the two differ: the
    block shown is the live theme's and the block committed under `RESET` is
    the host's, with the same rows (the same objects) in both.
    """
    table_style = replace(theme.blocks[BlockKind.TABLE], align=Align.JUSTIFY)
    justified = replace(theme, blocks={**theme.blocks, BlockKind.TABLE: table_style})
    source = TABLE_HEAD + _row(1) + _row(2)
    for policy, committed_align in (
        (CommitPolicy.RESET, Align.JUSTIFY),
        (CommitPolicy.KEEP_STREAMED, Align.LEFT),
    ):
        stream = StreamDocument(justified, fontlib_metrics, policy=policy)
        stream.append(source)
        (shown,) = stream.live
        assert stream._table is not None and isinstance(shown, TableBlock)
        assert shown.style.align is Align.LEFT
        stream.append("\nafter\n")
        (table,) = stream.committed
        assert isinstance(table, TableBlock) and table.style.align is committed_align
        assert all(now is then for now, then in zip(table.rows, shown.rows, strict=True))
        _replay(source + "\nafter\n", _tokens, justified, policy)


@pytest.mark.parametrize("name", ["plain", "escapes", "ragged", "text-rows", "no-edge-pipes"])
def test_the_table_sources_really_are_followed(name: str, theme: Theme) -> None:
    """
    The battery above is only about the row-at-a-time path if that path runs.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    followed = 0
    for character in TABLES[name]:
        stream.append(character)
        assert stream.revision
        followed += stream._table is not None
    assert followed > 5


LEAVING = {
    "next-item": ("1. step\n\n   ```\n   alpha\n", "   beta\n", "2. next step"),
    "paragraph-at-the-margin": ("1. step\n\n   ```\n   alpha\n", "   beta\n", "para graph"),
    "one-space": ("1. step\n\n   ```\n   alpha\n", "   beta\n", " one space in"),
    "after-blank-lines": ("1. step\n\n   ```\n   alpha\n", "   beta\n\n\n", "2. next"),
    "heading": ("- step\n\n  ~~~py\n  alpha\n", "  beta\n", "# heading"),
    "rule-or-item": ("- step\n\n  ```\n  alpha\n", "  beta\n", "- - -"),
    "fence-at-the-margin": ("1. step\n\n   ```\n   alpha\n", "   beta\n", "```py"),
    "table-row": ("1. step\n\n   ```\n   alpha\n", "   beta\n", "a|b"),
    "quote": ("1. step\n\n   ```\n   alpha\n", "   beta\n", "> quoted"),
    "nested-to-outer-item": ("- a\n  - b\n\n    ```\n    alpha\n", "    beta\n", "  - c d"),
    "nested-to-outer-text": ("- a\n  - b\n\n    ```\n    alpha\n", "    beta\n", "  text of a"),
    "nested-to-margin": ("- a\n  - b\n\n    ```\n    alpha\n", "    beta\n", "1. other list"),
    "quoted-leaves-quote": ("> intro\n>\n> ```\n> alpha\n", "> beta\n", "lazy or not"),
    "quoted-item-next": ("> - a\n>\n>   ```\n>   alpha\n", ">   beta\n", "> - b c"),
    "quoted-item-leaves-item": ("> - a\n>\n>   ```\n>   alpha\n", ">   beta\n", "> text"),
    "quoted-item-leaves-quote": ("> - a\n>\n>   ```\n>   alpha\n", ">   beta\n", "- top"),
    "wide-number": ("10. step\n\n    ```\n    alpha\n", "    beta\n", "11. next"),
    "after-kept-children": ("1. one\n2. two\n\n   para\n\n   ```\n   alpha\n", "   beta\n", "3. x"),
}
"""
A followed fence inside a container, a line to repeat in it, and a line that leaves it.
"""


@pytest.mark.parametrize("repeats", [3, 120])
@pytest.mark.parametrize("name", list(LEAVING))
def test_a_line_being_typed_that_leaves_a_followed_fence_does_not_have_the_fence_re_read(
    name: str, repeats: int, theme: Theme, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Review 5, item 3, as counts: what the parser is handed while such a line is typed.

    The line under a fence in a list item that is not indented far enough has
    left the item and the fence with it. The stream used to answer that by
    forgetting the fence and reading its container from where reading resumes
    -- the fence's first line -- once for every piece of that line: measured
    with the review's snippet C, 7339 characters handed to the parser for one
    character under a fence of 3616, against 31 for a line that stays in.
    Now the fence's lines are kept and the parser is handed the opener, the
    fence's first two lines and the line being typed, so the longest text it
    sees for a piece is the same at 3 repeats of the fence's line as at 120.

    After every character the blocks and the source map are those of one
    parse of everything received, which is the half of this that matters:
    the blocks after the fence come from a parse that saw one line of it.

    When the line *ends* the fence is read whole once, by the read that
    decides what is settled; that is one parse per fence and is not counted.
    """
    head, line, leaving = LEAVING[name]
    received = head + line * repeats
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append(received)
    assert isinstance(stream.live[-1], CodeBlock) and stream._fence is not None
    assert stream._fence.base is not None, "fixture: the fence must be a nested, followed one"
    before = len(stream.live)
    whole, pieces = _spying(monkeypatch)
    for character in leaving:
        stream.append(character)
        received += character
        expected = _whole(received, stream.live_theme)
        assert stream.blocks == expected.blocks, received
        assert stream.sources == expected.sources, received
    assert len(stream.live) > before, "fixture: the line must leave the fence"
    longest = max(len(text) for text in whole + pieces)
    bound = len(head) + len(line) + len(leaving) + 40
    assert longest <= bound, f"the parser was handed {longest} characters for one character"
    assert len(received) > 3 * bound or repeats == 3, "the fence is too short to show anything"
    # And the line ending, and the stream ending, are what they always were.
    for piece in ("\n", "more\n"):
        stream.append(piece)
        received += piece
        expected = _whole(received, stream.live_theme)
        assert stream.blocks == expected.blocks and stream.sources == expected.sources
    stream.close()
    assert stream.committed == _whole(received, stream.live_theme).blocks


def test_an_unended_quote_marker_under_a_quoted_fence_is_the_quotes_line_not_the_fences(
    theme: Theme,
) -> None:
    r"""
    Found by a fuzz run, pinned here: the fence's span and its quote's end on different lines.

    `> ~~~`, `> `, then `>` with no newline. markdown-it gives the fence lines
    0 to 2 and the quote lines 0 to 3; with the newline both end at 3. The
    followed fence used to ask about the unfinished line with a newline added,
    as a top-level fence may, and reported the fence a line longer than the
    whole parse does.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    received = "> intro\n>\n> ~~~\n> \n"
    stream.append(received)
    for piece in (">", "\n", "> x", "\n>"):
        stream.append(piece)
        received += piece
        expected = _whole(received, stream.live_theme)
        assert stream.blocks == expected.blocks
        assert stream.sources == expected.sources, repr(received)


REVIEW_5 = {
    "star-second-child": "* a\n\n  b\n\n  c\n* d\n\n  e\n\nend\n",
    "plus-star": "+ a\n  * b\n\n    c\n  * d\n+ e\n\n  f\n\nend\n",
    "star-dash-star": "* a\n  - b\n    * c\n\n      d\n    * e\n  - f\n* g\n\nend\n",
    "hr-like-in-star": (
        "* a\n* * *\n* b\n\n  ---\n  c\n  - - -\n* d\n***\n- e\n\n  ***\n  f\n\nend\n"
    ),
    "paren-ordered": "1) a\n2) b\n\n   c\n3) d\n1. new list\n2. x\n\nend\n",
    "marker-change": "- a\n- b\n\n  b2\n* c\n* d\n\n  d2\n+ e\n\nend\n",
    "nine-to-ten": (
        "8. a\n9. b\n   in nine\n10. c\n   lazy in ten\n\n   out of ten\n11. d\n\n"
        "    in eleven\n\nend\n"
    ),
    "lazy-earlier": "- a\n- b\nlazy b\n- c\n  - d\nlazy d\n    lazy d2\n- e\n\nend\n",
    "outdent-pulls": "- a\n\n  - b\n\n    c\n\n   d\n\n  e\n\n f\n\nend\n",
    "three-deep-open": "- a\n  - b\n    - c\n\n      c2\n\n      ```\n      code\n      more\n",
    "quote-list-fence": (
        "> - a\n>\n>   ```py\n>   x = 1\n>\n>   y = 2\n>   ```\n>   after\n> - b\n"
        ">   ~~~\n>   open\n> - c\n\nend\n"
    ),
    "closer-longer": "1. a\n\n   ```\n   x\n   `````\n   after\n2. b\n\nend\n",
    "closer-shorter": "1. a\n\n   ````\n   x\n   ```\n   y\n   ````\n   after\n2. b\n\nend\n",
    "closer-indent3": "1. a\n\n   ```\n   x\n      ```\n   after\n2. b\n\nend\n",
    "closer-indent4": "1. a\n\n   ```\n   x\n       ```\n   y\n   ```\n2. b\n\nend\n",
    "closer-outdented": "1. a\n\n   ```\n   x\n```\nswallowed\n2. not an item\n",
    "closer-info-spaces": "1. a\n\n   ~~~\n   x\n   ~~~ no\n   y\n   ~~~   \n   z\n2. b\n",
    "tabs-1": "- a\n\n\tb\n\n\t\tcode?\n- c\n\t- d\n\n\t  e\n\nend\n",
    "tabs-2": "1.\ta\n\n\tb\n2.\tc\n\nend\n",
    "tabs-3": ">\t- a\n>\t  b\n>\n>\t- c\n\nend\n",
    "item-indented-code": "-     code1\n\n      code2\n\n  para\n-     x\n- \n      y\n\nend\n",
    "ordered-indented-code": "1.      code\n\n   text\n2.      more\n\nend\n",
    "setext-in-item": (
        "- a\n\n  title\n  ===\n\n  sub\n  ---\n\n  para\n===\n- b\n  ---\n- c\n\nend\n"
    ),
    "table-in-item": (
        "- intro\n\n  | a | b |\n  |---|---|\n  | 1 | 2 |\n  | 3 | 4 |\n\n  after\n"
        "- x | y\n  --|--\n  1 | 2\n- p|q\n-|-\n\nend\n"
    ),
    "lazy-table-split": "- para\na|b\n  -|-\n  1|2\n\nend\n",
    "list-or-table": "1. x\n2. a|b\n:-|-\nc|d\n\nend\n",
    "hard-breaks": "- a  \n  b\\\n  c  \n\n  d\\\n- e  \n\n  f\\\n\nend\n",
    "crlf": "- a\r\n- b\r\n\r\n  b2\r\n  ```\r\n  x\r\n  ```\r\n- c\r\n\r\nend\r\n",
    "lone-cr": "> a\r>\r> b\r\rend\r",
    "blank-then-loose": "- a\n- b\n\n\n- c\n\n\n  c2\n- d\n\nend\n",
    "quoted-tables": (
        "> x\n>\n> | a | b |\n> |---|---|\n> | 1 | 2 |\n>\n> | c | d |\n> |---|---|\n" ">\n\nend\n"
    ),
    "quoted-table-in-item": "- > a|b\n  > -|-\n  >\n  > 1|2\n- z\n\nend\n",
    "html": (
        "> a\n>\n> <div>\n> x\n>\n> y\n\n- a\n\n  <!--\n  c\n- still comment?\n  -->\n"
        "- b\n\nend\n"
    ),
    "empty-items": "-\n  a\n-\n\n  b\n- \n- c\n\n  d\n-   \n  e\n\nend\n",
    "heading-quote-in-item": "- # h\n\n  ## h2\n  text\n  > q\n  > r\n\n  > s\nlazy\n- t\n\nend\n",
    "odd-numbers": "0. a\n\n   b\n007. c\n\n     d\n123456789. e\n\n           f\n\nend\n",
    "tight-quotes": ">a\n>\n>b\n>> c\n>>\n>> d\n> > e\n>\n>f\n\nend\n",
    "sibling-indents": (
        "   - a\n\n     a2\n  - b\n\n    b2\n - c\n\n   c2\n- d\n\n  d2\n    - e?\n\n" "end\n"
    ),
    "wide-pad-nested": "-  a\n\n    1.  x\n\n        y\n   2. z\n\n      w\n\nend\n",
    "fence-opens-nested-item": (
        "- a\n  - ```\n    x\n    y\n    ```\n    z\n  - ~~~\n    open\n- b\n\nend\n"
    ),
    "fences-back-to-back": (
        "1. a\n   ```\n   x\n   ```\n   ```\n   y\n   z\n   ```\n   ~~~\n   ~~~\n   t\n"
        "2. b\n\nend\n"
    ),
    "fence-blank-lines": "- a\n\n  ```\n  x\n\n\n  y\n\n  ```\n\n\n  b\n\nend\n",
    "quote-fence-lazy": "> a\n>\n> ```\n> x\nlazy\n> y\n\nend\n",
    "list-in-quote-in-list": (
        "- a\n\n  > - b\n  >\n  >   c\n  > - d\n  >   ```\n  >   x\n  >   ```\n"
        "  >   e\n\n  f\n- g\n\nend\n"
    ),
    "numbering": "3. a\n\n   - x\n   - y\n\n   b\n5. c\n   1. p\n   1. q\n\n      r\n9. d\n\nend\n",
}
"""
Review 5's battery D: forty-five sources written to break resuming inside a container.

They were written by a reviewer reading `advtext.markdown._resume_point` and
the fence following in `advtext.stream` for what their author had not tried:
a `*` or `+` item with a second child, a `)` list resumed, a table, a setext
heading and a hard break inside an item, tabs, CRLF and a lone CR, closing
fences that are too short, too long, too far in or not far enough, lazy
continuation onto an earlier item, numbers that gain a digit. **It found
nothing** -- 0 mismatches in 180 runs, measured by the lead and again when it
was put here -- and that is the evidence the resume opener has beyond its
author's argument, so it is kept as a regression corpus and not as a list of
defects fixed.
"""


def _threes(source: str) -> list[str]:
    return [source[position : position + 3] for position in range(0, len(source), 3)]


@pytest.mark.parametrize(
    ("chunker", "policy"),
    [
        (_characters, CommitPolicy.KEEP_STREAMED),
        (_characters, CommitPolicy.RESET),
        (_threes, CommitPolicy.KEEP_STREAMED),
        (_lines, CommitPolicy.RESET),
    ],
    ids=["characters-KEEP_STREAMED", "characters-RESET", "threes-KEEP_STREAMED", "lines-RESET"],
)
@pytest.mark.parametrize("name", list(REVIEW_5))
def test_review_5_s_sources_stream_to_the_blocks_of_one_parse_after_every_piece(
    name: str, chunker: Chunker, policy: CommitPolicy, theme: Theme
) -> None:
    """
    After every piece: live, committed and the source map against a whole parse.

    `_replay` is the check the rest of this file uses, and it is the
    reviewer's: committed blocks only ever added to, by identity; live and
    committed equal to one parse of what has arrived, in the theme each is
    built with; sources equal; and the closed stream equal to the parse of
    everything. The carriage returns in two of the sources are normalised by
    `append`, so those two are compared with the parse of what the stream
    says it received.
    """
    source = REVIEW_5[name]
    if "\r" in source:
        pieces = chunker(source)
        stream = StreamDocument(theme, fontlib_metrics, policy=policy)
        committed: tuple[Block, ...] = ()
        for piece in pieces:
            stream.append(piece)
            committed = _check_step(stream, stream.source, committed, compare=True)
        stream.close()
        _check_step(stream, stream.source, committed, compare=True)
        assert stream.live == ()
        assert stream.source == source.replace("\r\n", "\n").replace("\r", "\n")
        return
    _replay(source, chunker, theme, policy)


def _generated(dice: random.Random, depth: int = 0) -> list[str]:
    """
    The lines of one random list or quote, with fences, paragraphs and more of itself inside.

    Markers of every width, padding from one space to five (five is "content
    starts after one, and the rest is indented code"), items indented up to
    three columns, quote markers with and without their space. Not a grammar
    of markdown: a way to reach nestings and column arithmetic nobody wrote
    down, which is where both mistakes in the first opener were.
    """

    def children() -> list[str]:
        out: list[str] = []
        for _ in range(dice.randint(1, 3)):
            roll = dice.random()
            if roll < 0.35:
                mark = dice.choice(["```", "~~~", "````"])
                out.append(mark)
                out += [dice.choice(["x = 1", "", "    in", "``", "- no", "> no"])] * 1
                out += [dice.choice(["y", "", "# no"]) for _ in range(dice.randint(0, 3))]
                if dice.random() < 0.7:
                    out.append(mark)
            elif roll < 0.5 and depth < 2:
                out += _generated(dice, depth + 1)
            else:
                texts = ["text", "**b** `c`", "===", "---", "# h", "1. in", "- in", "> q", "a|b"]
                out += [dice.choice(texts) for _ in range(dice.randint(1, 2))]
            if dice.random() < 0.6:
                out.append("")
        return out

    if dice.random() < 0.3:
        return [dice.choice(["> ", ">", " > "]) + line if line else ">" for line in children()]
    out = []
    ordered = dice.random() < 0.5
    first = dice.choice([1, 1, 7, 98])
    for number in range(dice.randint(1, 4)):
        marker = f"{first + number}." if ordered else "-"
        padding = dice.choice([1, 1, 1, 2, 4, 5])
        indent = dice.choice(["", "", " ", "   "])
        width = len(indent) + len(marker) + (padding if padding <= 4 else 1)
        body = children()
        out.append(indent + marker + (" " * padding + body[0] if body[0] else ""))
        out += [" " * width + line if line else "" for line in body[1:]]
    return out


GENERATED = int(os.environ.get("ADVTEXT_STREAM_FUZZ", "0"))
"""
How many generated documents the test below streams when asked for a long run; else twelve.
"""


@pytest.mark.parametrize("seed", range(GENERATED or 12))
def test_generated_nested_containers_stream_to_the_blocks_of_one_parse(
    seed: int, theme: Theme
) -> None:
    """
    The property on documents nobody wrote: three random containers, then damage.

    Each document is a few generated lists and quotes with one or two lines
    then outdented, indented or deleted, streamed in token-sized pieces and
    compared with a whole parse after every piece; every third seed under
    `RESET`.

    Twelve documents show little. They are here so that the generator and the
    comparison stay runnable: `ADVTEXT_STREAM_FUZZ=2000` in the environment
    runs that many, and then the odd seeds a character at a time, which is
    every prefix of every line and several seconds a document. The runs that
    were made, most of them with a larger generator kept outside the tree,
    are in `.concerns/AF-streamcost--builder--result.md`.
    """
    dice = random.Random(seed)
    lines: list[str] = []
    for _ in range(3):
        lines += [*_generated(dice), ""]
    for _ in range(dice.randint(0, 2)):
        index = dice.randrange(len(lines))
        roll = dice.random()
        if roll < 0.4:
            lines[index] = lines[index].removeprefix(" ").removeprefix(" ")
        elif roll < 0.7:
            lines[index] = " " * dice.randint(1, 4) + lines[index]
        else:
            del lines[index]
    source = "\n".join(lines) + dice.choice(["\n", ""])
    policy = CommitPolicy.RESET if seed % 3 == 0 else CommitPolicy.KEEP_STREAMED
    _replay(source, CHUNKERS["characters" if GENERATED and seed % 2 else "tokens"], theme, policy)


# ----------------------------------------------------------------------
# `append` from another thread (review 4, item 9)


def test_a_piece_appended_while_a_read_is_taking_the_buffer_is_not_lost(theme: Theme) -> None:
    """
    The interleaving that lost a piece, made to happen: an append the moment a read lets go.

    The read used to join the pending pieces and then clear the list, and a
    piece appended between the two was cleared unread. It now takes the list
    under the lock `append` holds. The lock here is a stand-in that appends a
    piece the instant the read releases it -- the earliest another thread
    could get in -- and the piece must be in the source, in order, and in the
    blocks of the next read.
    """
    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("kept one ")
    real = stream._lock
    releases = 0

    class Intruding:
        def __enter__(self) -> None:
            real.acquire()

        def __exit__(self, *exc: object) -> None:
            nonlocal releases
            real.release()
            releases += 1
            if releases == 1:
                stream._lock = real
                stream.append("INTRUDER ")
                stream._lock = self  # type: ignore[assignment]

    stream._lock = Intruding()  # type: ignore[assignment]
    assert stream.revision == 1
    assert releases == 1, "the read never took the lock, so nothing was tested"
    stream._lock = real
    assert stream.pending, "the intruding piece arrived after the read took its buffer"
    stream.append("kept two\n")
    assert stream.source == "kept one INTRUDER kept two\n"
    assert stream.blocks == _whole(stream.source, stream.live_theme).blocks


def test_pieces_appended_from_another_thread_all_arrive_in_order(theme: Theme) -> None:
    """
    The same with a real thread: a producer appending while this thread reads.

    Before the lock this lost a piece in 3 trials of 30 at 1,500 pieces each
    (scratch run, switch interval set to a microsecond so the threads
    interleave often). Eight trials here, which that rate would catch a
    little over half the time: the test above is the one that always would
    have failed, and this one is that the real thing works.
    """
    import sys
    import threading

    pieces = [f"w{number} " if number % 9 else f"w{number}\n\n" for number in range(1500)]
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for _ in range(8):
            stream = StreamDocument(theme, fontlib_metrics)

            def produce(target: StreamDocument = stream) -> None:
                for piece in pieces:
                    target.append(piece)

            producer = threading.Thread(target=produce)
            producer.start()
            while producer.is_alive():
                assert stream.revision >= 0
            producer.join()
            assert stream.source == "".join(pieces)
            assert stream.blocks == _whole(stream.source, stream.live_theme).blocks
    finally:
        sys.setswitchinterval(interval)


def test_a_late_piece_after_close_raises_in_the_thread_that_appended_it(theme: Theme) -> None:
    """
    What a cancelled producer meets: `ValueError`, where it appended, and nothing changed.
    """
    import threading

    stream = StreamDocument(theme, fontlib_metrics)
    stream.append("the reply so far")
    stream.close()
    committed = stream.committed
    raised: list[BaseException] = []

    def late() -> None:
        try:
            stream.append(" and one more token")
        except ValueError as error:
            raised.append(error)

    producer = threading.Thread(target=late)
    producer.start()
    producer.join()
    assert len(raised) == 1 and "closed" in str(raised[0])
    assert stream.source == "the reply so far" and stream.committed is committed

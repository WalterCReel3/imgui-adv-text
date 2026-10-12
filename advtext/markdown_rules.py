r"""
How markdown is READ here: the parser's configuration, its math rules, and the source map.

Everything in this module was in `advtext.markdown` and was moved out of it
whole, unchanged, so that something which reads markdown without making nodes
(`advtext.typeset_markdown`) can use the same parser, rule for rule, and not a
copy of it. `advtext.markdown` imports every name back and they are reachable
there exactly as before; `advtext.markdown`'s docstring is still where the
rules are described for a reader (`$...$`, `$$`, underscore emphasis, link
reference definitions).

**This module imports markdown-it and the standard library, and nothing of
advtext.** That is the point of it, and `tests/test_typeset_markdown.py` holds
it: a fresh interpreter that imports this module has no other `advtext` module
loaded.

What is here:

- the parser: `_build_parser`, the two singletons, `_parser(references, math)`
  and `_parse`, with the three custom rules (`_asterisk_only_emphasis`,
  `_math_inline`, `_math_block`) and the core rule that tells the inline math
  rule where the source ends (`_inline_knowing_the_end`);
- the parser a host's reader options choose (`_reader_parser`), and the one
  rules those add (`_written_stars`; `_written_backslashes` and
  `_written_cell_pipes`, pptmstr's P32). Added 2026-10-12 for
  `advtext.typeset_markdown.ReaderOptions`, which is where a host says them:
  these two names were never in `advtext.markdown` and are not imported back;
- the source map: `SourceSpan`, `BlockSource`, `_line_starts`, `_span`;
- three small things both readers need to agree on: `TAB_WIDTH`, `_BULLET`,
  and `ColumnAlign` with the table of style attributes it is read from.

The leading underscores are kept because the names are still private to the
package: two modules of it read them, and no host should.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from functools import cache
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_block.state_block import StateBlock
from markdown_it.rules_core.state_core import StateCore
from markdown_it.rules_inline.emphasis import tokenize as _emphasis_tokenize
from markdown_it.rules_inline.state_inline import StateInline

__all__ = [
    "BlockSource",
    "ColumnAlign",
    "SourceSpan",
    "TAB_WIDTH",
]

# A fenced block is not wrapped, so a tab has to become a definite number of
# columns somewhere. Four, because that is what the code in this project's own
# documents uses.
TAB_WIDTH = 4


_BULLET = "•"


class ColumnAlign(enum.Enum):
    """
    A table column's alignment, as the source's `:---:` markers set it.
    """

    LEFT = enum.auto()
    CENTER = enum.auto()
    RIGHT = enum.auto()


_COLUMN_ALIGNS = {
    "text-align:left": ColumnAlign.LEFT,
    "text-align:center": ColumnAlign.CENTER,
    "text-align:right": ColumnAlign.RIGHT,
}


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """
    A run of whole source lines: where in the markdown something came from.

    `line_start` and `line_end` are zero-based and half-open, as markdown-it's
    `token.map` is. `start` and `end` are the same range as character offsets
    into the source string, so `source[start:end]` is those lines **verbatim**
    -- list markers, quote prefixes, fence lines and the final newline included.
    Both are kept because a host wants both: lines to show a location, offsets
    to cut the text out without re-splitting it.

    Whole lines, never part of one. CommonMark's block structure is line-based
    and markdown-it reports nothing finer for a block, so a span cannot say
    where inside its line a list item's text begins. Verbatim source for a
    block is therefore the block *as the author typed it*, marker and all,
    which is what "copy as markdown" means.

    A span never ends in blank lines. markdown-it's range for a list runs on
    over the blank line that follows it; that line belongs to no block and is
    trimmed, so two adjacent spans never both claim it.
    """

    line_start: int
    line_end: int
    start: int
    end: int

    def of(self, source: str) -> str:
        """
        The lines this span covers, cut verbatim out of the source they index.
        """
        return source[self.start : self.end]

    def shifted(self, lines: int, characters: int) -> SourceSpan:
        """
        This span moved down a document, for a caller that parsed only the tail of one.

        A streaming segmenter re-parses from the start of the last top-level
        block, so the spans it gets back count from there. Adding the lines and
        the characters that came before puts them back in the whole source's
        coordinates.
        """
        return SourceSpan(
            line_start=self.line_start + lines,
            line_end=self.line_end + lines,
            start=self.start + characters,
            end=self.end + characters,
        )


@dataclass(frozen=True, slots=True)
class BlockSource:
    r"""
    Where one `Block` came from, at two grains.

    `span` is the block's own lines: one paragraph, one list item's paragraph,
    one fence, one table, one heading with its underline if it has one. `top`
    is the top-level markdown block those lines are part of -- the whole list,
    the whole block quote -- and equals `span` for a block that is top-level
    itself. A host copying "this paragraph" wants the
    first and one copying "this list" wants the second; a streaming segmenter
    commits by the second, because a top-level block is the unit that can no
    longer change once the next one has started.

    Blocks that came from one top-level block share an equal `top`, which is
    how to group them.

    **Which text the offsets index.** The string that was parsed, which is not
    always the string a host is holding:

    - From `build_document`, the `source` argument as given. A source with
      `\r\n` line ends slices correctly, carriage returns included. One with
      bare `\r` line ends does not (`_line_starts` says why).
    - From `advtext.stream.StreamDocument`, **`StreamDocument.source`**, in
      which every `\r\n` and lone `\r` has already become `\n`. A host that
      appended text with carriage returns and slices *its own copy* with these
      offsets gets the wrong text, off by one character for every `\r\n`
      above the block. Slice `stream.source`, or count by `line_start` and
      `line_end`, which are the same in both.
    """

    span: SourceSpan
    top: SourceSpan


def _asterisk_only_emphasis(state: StateInline, silent: bool) -> bool:
    """
    Suppress underscore emphasis, keeping `*`.

    pptmstr's reasoning at `pptmstr/ui/inline.py:50-74` applies unchanged:
    CommonMark's intraword rule already protects `foo_bar_baz`, and does not
    protect `__init__`, because each of its underscore runs sits at a word
    boundary and so may legally flank. The cost is that `_italic_` no longer
    italicises, which is the trade this document wants.
    """
    if state.src[state.pos] == "_":
        return False
    return _emphasis_tokenize(state, silent)


def _math_inline(state: StateInline, silent: bool) -> bool:
    r"""
    `$...$`, and `$$...$$` inside a line, with pandoc's guards.

    **The closer is the first unescaped marker after the opener, or there is
    none.** That is pandoc's reading and it is what keeps prices out: in
    `$5 and $10` the first dollar after the `5` has a space before it, so the
    `$5` opens nothing, and the search does *not* go on to a later dollar that
    would have passed. (The first version here did go on, and set
    `5 and $10, not math. But $e^{i\pi}+1=0` as one formula.) Pandoc's three
    guards: no white space after the opening marker, none before the closing
    one, and a closing `$` not followed by a digit.

    **Two more guards, which are this project's and a heuristic.** Pandoc's
    stop prices and nothing else, and the text this is read from is largely
    about code: `set $PATH=$HOME/bin` set `PATH=` in math italic and lost
    both dollars (review 2, item 4). So, as well:

    - the opening marker is **not preceded by a letter or a digit**
      (`US$5`, `a$b$`), and
    - the closing marker is **not followed by a letter, a digit, `{` or `(`**
      -- pandoc forbids only the digit. `$PATH=$HOME`, `$HOME/$USER` and
      `$a$b` are then text, and so are `${A}${B}` and `$(a)$(b)`, whose
      would-be closer is a shell expansion's opener. (The letter and the
      digit are the lead's decision; the brace and the parenthesis were
      added with them for those two shapes.)

    What that gives up, knowingly: a formula written hard against a word
    on either side. `$n$th` and `2$x$` are text now, and so is every part of
    `$x$y$`; `$n$-th`, `$n$ th`, `($x$)` and `$x$, $y$` are formulas as
    before. Nothing here knows a shell variable from a symbol -- `$PATH$`
    alone on a line is still a formula -- so a host whose text is known to be
    one or the other should leave math off or on accordingly.

    **A closer that is the last character of a text that may go on closes
    nothing yet** (review 3, item 3). The last guard reads the character
    *after* the closer, and at the very end of a text there is none: a
    stream cut at `set $PATH=$` showed `PATH=` as a set formula for the one
    piece before the `H` of `$HOME` arrived, and again at `$EDITOR=$`. A
    caller that knows more may follow says so (`build_document(...,
    more_may_follow=True)`; `advtext.stream` does, for its live tail, until
    it is closed), and then a marker that passes every guard but is the last
    character of the whole source is text, as an unclosed one is. With
    nothing said, the end of the input is a follower like a space: the text
    is complete, and `a $x$` has a formula in it. The same heuristic has
    limits this does not touch, listed so that nobody finds them again: in
    `$20/hr, or 15$/hr` the text between the dollars is a formula (the
    closer is followed by `/`), and in the regular expression `^a+$|^b+$`
    so is `|^b+` (a host showing that kind of text should leave math off, or
    the writer should put it in a code span, where a dollar is never looked
    at).

    A dollar that does not open a formula is consumed as text here rather
    than declined, as the backtick rule does with a run that has no closer, so
    that no other rule is offered it. Each opener reads only as far as the
    next dollar, so a paragraph is read at most twice however many it has.
    """
    source = state.src
    position = state.pos
    if source[position] != "$":
        return False
    maximum = state.posMax
    marker = "$$" if source.startswith("$$", position) else "$"
    start = position + len(marker)
    end = -1
    hard_against_a_word = position > 0 and source[position - 1].isalnum()
    if start < maximum and not source[start].isspace() and not hard_against_a_word:
        scan = start + 1
        while True:
            scan = source.find(marker, scan, maximum)
            if scan < 0:
                break
            backslashes = 0
            while source[scan - 1 - backslashes] == "\\":
                backslashes += 1
            if backslashes % 2:
                scan += 1
                continue
            follows = source[scan + len(marker) : scan + len(marker) + 1]
            if not source[scan - 1].isspace() and not (follows.isalnum() or follows in ("{", "(")):
                end = scan
            if end == len(source) - len(marker) and state.env.get(_END_IS_OPEN):
                # The last character of a text that may go on (see
                # `_inline_knowing_the_end`): what follows it is not known.
                end = -1
            break
    if end < 0:
        if not silent:
            state.pending += marker
        state.pos = start
        return True
    if not silent:
        token = state.push("math_inline", "math", 0)
        token.markup = marker
        token.content = source[start:end]
    state.pos = end + len(marker)
    return True


_MORE_MAY_FOLLOW = "advtext_more_may_follow"
_END_IS_OPEN = "advtext_end_is_open"


def _inline_knowing_the_end(state: StateCore) -> None:
    """
    markdown-it's core `inline` rule, telling `_math_inline` which inline
    content -- if any -- ends at the end of a source that may go on.

    The inline parser is handed one block's content at a time and cannot
    tell where in the source it is. This is the one place that can: when the
    caller said more may follow (`_parse`) and the source's last character
    is a dollar, the *last* inline token is the one that holds it provided
    its lines reach the source's last line (a source that ends inside a
    fence ends in a dollar that is code, and the paragraph before the fence
    is settled). The flag is in the parse's own `env`, set for that one
    token and cleared for every other.
    """
    env = state.env
    open_token = None
    if env.get(_MORE_MAY_FOLLOW) and state.src.endswith("$"):
        last_line = state.src.count("\n") + 1
        for token in reversed(state.tokens):
            if token.type == "inline":
                if token.map and token.map[1] >= last_line and token.content.endswith("$"):
                    open_token = token
                break
    for token in state.tokens:
        if token.type == "inline":
            if token.children is None:
                token.children = []
            env[_END_IS_OPEN] = token is open_token
            state.md.inline.parse(token.content, state.md, env, token.children)
    env[_END_IS_OPEN] = False


def _math_block(state: StateBlock, start_line: int, end_line: int, silent: bool) -> bool:
    """
    A display formula: a `$$` line to the next `$$` line, or one `$$ ... $$` line.

    A fence in every respect that matters to a caller reading a document a
    line at a time: it opens on a complete line, without looking for its
    closer, and an unclosed one runs to the end of its container.

    Known, and left (review 3): `$$ x = 1 $$` typed on ONE line changes kind
    twice while it is the line being written -- `$$` alone is an open block,
    `$$ x` is a paragraph (text after the marker is not a block's opening
    line), and the closing `$$` makes it a display formula. Nothing settled
    is touched; the live block is what flips.
    """
    if state.is_code_block(start_line):
        return False
    position = state.bMarks[start_line] + state.tShift[start_line]
    line = state.src[position : state.eMarks[start_line]].rstrip()
    if not line.startswith("$$"):
        return False
    if line != "$$":
        inside = line[2:-2]
        if len(line) < 5 or not line.endswith("$$") or "$$" in inside or not inside.strip():
            return False
        if silent:
            return True
        state.line = start_line + 1
        token = state.push("math_block", "math", 0)
        token.content = inside.strip()
        token.markup = "$$"
        token.map = [start_line, state.line]
        token.meta = {"closed": True}
        return True
    if silent:
        return True
    next_line = start_line
    closed = False
    while True:
        next_line += 1
        if next_line >= end_line:
            break
        position = state.bMarks[next_line] + state.tShift[next_line]
        maximum = state.eMarks[next_line]
        if position < maximum and state.sCount[next_line] < state.blkIndent:
            # As for a fence: a line indented less than its container ends it.
            break
        if state.src[position:maximum].rstrip() == "$$" and not state.is_code_block(next_line):
            closed = True
            break
    state.line = next_line + (1 if closed else 0)
    token = state.push("math_block", "math", 0)
    token.content = state.getLines(start_line + 1, next_line, state.sCount[start_line], False)
    token.markup = "$$"
    token.map = [start_line, state.line]
    # Whether the closing line was met: the converter does not typeset a block
    # that is still being written. A line that is `$$` counts whether or not
    # its newline has come, as the last line of a file must.
    token.meta = {"closed": closed}
    return True


def _written_stars(state: StateInline, silent: bool) -> bool:
    """
    A run of `*` read as the characters it is, where it was written as one and not as emphasis.

    Only in a parser built with `written_stars=True`
    (`advtext.typeset_markdown.ReaderOptions.keep_glob_stars`), where it runs
    before the emphasis rule and so decides first. pptmstr's rule, taken from
    its old seam (`_written_stars`, which that host added to this module's
    shared parser through `_parser`) with its three conditions unchanged.
    CommonMark pairs the stars of `delete **/*.py and tests/**/*.md` into a
    bold `/*.py and tests/` and draws none of the four: the reader sees
    another command than the one that was written.

    **What tells a written star from emphasis is the one character on each
    side of the whole run of stars** (and for the second condition, one
    more). A run is text when any of these holds:

    - a `/` is immediately before it or immediately after it (`**/*.py`,
      `src/*`, `/* note */`);
    - a `.` is immediately after it and the character after that `.` is not
      white space and not the end of the text (`*.py`, `**.tar.gz`; but not
      `*.` before a space, which nobody writes as a glob);
    - a letter or a digit is immediately before it AND immediately after it
      (`2*3*4`, `foo*bar`), which is how CommonMark itself reads `_`.

    The start and the end of the inline text count as a space. `**bold**`,
    `*emphasis*`, `**and/or**`, `**src/x.py**` and `**Ends in a stop.**` meet
    none of the three at either of their runs and are emphasis as before.

    **What it gets wrong, in both directions, and is left so.** A glob
    written exactly as emphasis is written still loses its stars:
    `rm *tmp and old* now` is `rm`, an italic `tmp and old`, and `now`. And
    emphasis written hard against a slash, or inside a word, is no longer
    emphasis: `**/usr/bin**` keeps its four stars and is not bold, and
    `foo*bar*baz`, in which CommonMark emphasises `bar`, keeps both. A star
    in a code span or a fenced block never reaches this rule.
    """
    source = state.src
    start = state.pos
    if source[start] != "*":
        return False
    stop = start
    while stop < state.posMax and source[stop] == "*":
        stop += 1
    before = source[start - 1] if start else " "
    after = source[stop] if stop < len(source) else " "
    more = source[stop + 1] if stop + 1 < len(source) else " "
    written = (
        before == "/"
        or after == "/"
        or (after == "." and not more.isspace())
        or (before.isalnum() and after.isalnum())
    )
    if not written:
        return False
    if not silent:
        state.pending += source[start:stop]
    state.pos = stop
    return True


# What a backslash escapes in CommonMark: the 32 ASCII punctuation characters.
_ESCAPABLE = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _written_backslashes(state: StateInline, silent: bool) -> bool:
    r"""
    A backslash escape read as CommonMark reads it, with the backslash set as well.

    Only in a parser built with `written_backslashes=True`
    (`advtext.typeset_markdown.ReaderOptions.backslashes_as_written`), where
    it stands in the escape rule's place and under its name. CommonMark
    draws the punctuation and not the backslash: `C:\_work\*.log` is set as
    `C:_work*.log`, `foo\.py` as `foo.py`, `\\server` as `\server` (pptmstr's
    P32, reproduced here 2026-10-12), and a reader approving a path or a
    pattern sees another one than was written.

    **Replaced, not switched off.** With no escape rule at all the backslash
    would be text and the character after it would be offered to every other
    rule, so `\*not emphasis\*` would be an italic `not emphasis\` after a
    backslash, and `\[x\](y)` a link: the writer's stars and brackets gone
    and their meaning changed as well. Here the escaped character still
    marks nothing, exactly as in CommonMark, and both characters are text.
    The rule is pptmstr's (`_written_escapes` in its seam, read there).

    - A backslash before one of the 32 ASCII punctuation characters: both
      are set. `\\` is two backslashes, and the second escapes nothing.
    - A backslash that ends a line: the backslash is set AND the line ends
      there (a hard break), and the next line's leading white space is not
      text, as in CommonMark. So `C:\dir\` at a line's end keeps its
      backslash, and a writer who ended a line with one to break it still
      gets the break, with a backslash before it.
    - A backslash before anything else, or the last character of the text:
      not this rule's. It is text already, as it is in CommonMark.

    What this does not reach, because another rule has read the backslash
    before any inline rule is asked: a link's destination and title
    (`[a](C:\_x)` goes to `C:_x`, and that is what `show_link_destinations`
    shows), and a link reference definition. `\|` in a table cell is put
    back by `_written_cell_pipes`. A backslash in a code span, a fenced or
    indented block, an autolink or a formula was never an escape and is
    unchanged; a fence's info string is kept as written by the reader with
    or without this.

    `\$` when math is on: the math rule runs after this one, so the dollar
    is taken here with its backslash and opens no formula, as an escaped
    dollar never did; what is set is `\$`. Inside a formula nothing is
    changed: `_math_inline` reads its source itself and skips an escaped
    closer as before.
    """
    source = state.src
    at = state.pos
    if source[at] != "\\" or at + 1 >= state.posMax:
        return False
    after = source[at + 1]
    if after == "\n":
        if not silent:
            state.pending += "\\"
            state.push("hardbreak", "br", 0)
        at += 2
        while at < state.posMax and source[at] in " \t":
            at += 1
        state.pos = at
        return True
    if after not in _ESCAPABLE:
        return False
    if not silent:
        state.pending += source[at : at + 2]
    state.pos = at + 2
    return True


def _written_cell_pipes(state: StateCore) -> None:
    r"""
    `\|` in a table cell given back its backslash, before the cell is read as a line.

    With `_written_backslashes`. markdown-it's table rule splits a row at
    each `|` that has no backslash before it and, where one has, drops the
    backslash and keeps the pipe (`escapedSplit`), so by the time a cell is
    read as inline text `a\|b` is `a|b` and no inline rule can know. But
    that makes the rule exact in reverse: **every `|` in a cell's content
    was written `\|`**, in a code span too (the split does not look for
    backticks). So each is written back as `\|`, and `_written_backslashes`
    sets the two. In a code span that is `\|` as well, where CommonMark's
    tables show `|`: as written.
    """
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type == "inline" and index and tokens[index - 1].type in ("th_open", "td_open"):
            token.content = token.content.replace("|", "\\|")


def _build_parser(
    *,
    references: bool = True,
    math: bool = False,
    html: bool = True,
    images: bool = True,
    written_stars: bool = False,
    written_backslashes: bool = False,
) -> MarkdownIt:
    """
    CommonMark, plus tables, minus underscore emphasis.

    Tables are not CommonMark and have to be enabled explicitly; the litmus test
    requires one (`docs/decisions.md`).

    `references=False` switches off the block rule that reads link reference
    definitions. It is a separate parser object and not a setting flipped on
    one: `MarkdownIt.disable` mutates, and `_PARSER` is a module singleton that
    every `build_document` call shares. `math=True` adds the two math rules,
    again to a parser of its own (`_parser`): four objects at most, each built
    when first asked for.

    The last three are a host's reader options (`_reader_parser`), and their
    defaults are the parser this function always built. `html=False`
    switches off the two rules that read raw HTML, block and inline: a tag,
    a comment opener and a generic's `<T>` are then ordinary text, which is
    CommonMark's own reading of them when HTML is not allowed. An autolink
    (`<https://...>`) is another rule and stays a link. `images=False`
    switches off the image rule, and `![alt](url)` is then what is left when
    nothing claims the `!`: an exclamation mark and a link. `written_stars`
    adds `_written_stars` in front of the emphasis rule.
    `written_backslashes` puts `_written_backslashes` in the escape rule's
    place, under its name (so the math rule is still placed after it), and
    `_written_cell_pipes` in front of the core's inline rule.
    """
    parser = MarkdownIt("commonmark").enable("table")
    parser.inline.ruler.at("emphasis", _asterisk_only_emphasis)
    if written_stars:
        parser.inline.ruler.before("emphasis", "written_stars", _written_stars)
    if written_backslashes:
        parser.inline.ruler.at("escape", _written_backslashes)
        parser.core.ruler.before("inline", "written_cell_pipes", _written_cell_pipes)
    if not html:
        parser.disable(["html_block", "html_inline"])
    if not images:
        parser.disable("image")
    if not references:
        parser.disable("reference")
    if math:
        # After the escape rule, so `\$` is a dollar before this sees it; the
        # block rule with a fence's `alt`, so it ends a paragraph, a quote and
        # a list exactly where a fence would.
        parser.inline.ruler.after("escape", "math_inline", _math_inline)
        parser.inline.add_terminator_char("$")
        parser.core.ruler.at("inline", _inline_knowing_the_end)
        parser.block.ruler.before(
            "fence",
            "math_block",
            _math_block,
            {"alt": ["paragraph", "reference", "blockquote", "list"]},
        )
    return parser


_PARSER = _build_parser()

_PARSER_WITHOUT_REFERENCES = _build_parser(references=False)
"""
The parser `build_document(..., references=False)` uses; see that function.
"""


@cache
def _parser(references: bool, math: bool) -> MarkdownIt:
    """
    The one parser for a combination of the two switches; the plain ones are the singletons.
    """
    if not math:
        return _PARSER if references else _PARSER_WITHOUT_REFERENCES
    return _build_parser(references=references, math=True)


@cache
def _reader_parser(
    references: bool,
    math: bool,
    html: bool,
    images: bool,
    written_stars: bool,
    written_backslashes: bool = False,
) -> MarkdownIt:
    """
    The one parser for a combination of the two switches and four reader options.

    With the options at their defaults (`html` and `images` true,
    `written_stars` and `written_backslashes` false) this IS `_parser(references, math)`, the same
    object, so a caller that states no option reads with the parser every
    caller read with before the options existed. Any other combination is a
    parser of its own, built once and kept: `MarkdownIt.disable` mutates, so
    an option cannot be a setting flipped on a shared object. A settled
    document and a stream that state equal options are handed the same
    parser, which is the point of going through here.
    """
    if html and images and not written_stars and not written_backslashes:
        return _parser(references, math)
    return _build_parser(
        references=references,
        math=math,
        html=html,
        images=images,
        written_stars=written_stars,
        written_backslashes=written_backslashes,
    )


def _parse(parser: MarkdownIt, source: str, more_may_follow: bool = False) -> list[Any]:
    r"""
    `parser.parse(source)`, surviving the one input markdown-it 4.2.0 is known to crash on.

    `more_may_follow` is the caller saying the source is not known to be
    complete, which one rule wants to know (`_math_inline`: a closing dollar
    that is the last character so far). It is handed over in the parse's
    `env`, and only when the source ends in a dollar, so every other parse is
    the call it always was.

    Measured: a table inside a block quote, followed by an unended line that
    is only the quote's marker -- `> a|b`, `>-|-`, `>` with no newline -- raises
    `IndexError` out of `MarkdownIt.parse` (the table rule asks the HTML-block
    rule about the last line, which indexes one past the end of the source).
    A file can end that way; a source arriving a character at a time passes
    through that state every time a quoted table gains a row, and
    `advtext.stream` parses the unfinished line. Found by the fuzz run for
    `.concerns/AF-streamcost--builder--result.md`, not by a report.

    The answer is to parse the same text with its last line ended, which is
    the text the next character but one would have made it anyway, and which
    does not crash. Line numbers are unchanged by a final newline, so the
    spans a caller computes from `source` still fit the tokens. Only
    `IndexError` is caught, and only once: anything else, or a second failure,
    is the caller's to see.
    """
    if more_may_follow and source.endswith("$"):
        return list(parser.parse(source, {_MORE_MAY_FOLLOW: True}))
    try:
        return list(parser.parse(source))
    except IndexError:
        if source.endswith("\n"):
            raise
        return list(parser.parse(source + "\n"))


def _line_starts(source: str) -> list[int]:
    """
    The character offset at which each line of `source` begins, plus the end.

    Lines are counted the way markdown-it counts them, by `\n`, so entry `k` is
    where the parser's line `k` starts. A `\r\n` source works because its
    lines still end in `\n`. A source with bare `\r` line ends does not:
    markdown-it normalises those to newlines before counting, and the offsets
    here would be into text it never saw. Nothing this project reads is in
    that form.
    """
    starts = [0]
    position = source.find("\n")
    while position != -1:
        starts.append(position + 1)
        position = source.find("\n", position + 1)
    if starts[-1] != len(source):
        starts.append(len(source))
    return starts


def _span(lines: Any, starts: list[int], source: str) -> SourceSpan:
    """
    markdown-it's `[begin, end)` line range as a `SourceSpan`, blank tail trimmed.
    """
    begin, end = int(lines[0]), int(lines[1])
    last = len(starts) - 1
    begin, end = min(begin, last), min(end, last)
    while end > begin + 1 and not source[starts[end - 1] : starts[end]].strip():
        end -= 1
    return SourceSpan(line_start=begin, line_end=end, start=starts[begin], end=starts[end])

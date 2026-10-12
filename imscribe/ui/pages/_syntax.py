r"""
The demo's syntax colouring: two small tokenisers and the shapes pages want them in.

**This is demo code, not library API.** `imscribe` ships no tokeniser and takes no
dependency to get one (`docs/decisions.md`); a view is handed *ranges with inks*
and never sees a token. What is here is the least that makes a code block, a diff
and a chat reply in the demo look coloured, so that the hand-off can be shown. A
host uses its own highlighter -- Pygments, tree-sitter, whatever its editor has --
and produces the same shapes. Nothing outside `imscribe.ui.pages` imports
this module, it is not in the facade, and its name starts with an underscore so
the page scan never mistakes it for a page.

`examples/theme_gallery.py` keeps its own twenty-line `highlight`, on purpose: an
example must run on the facade alone, and this module is not in it.

## The shapes

    tokens(text, language)        -> ((start, end, kind), ...)       offsets into `text`
    line_tokens(lines, language)  -> one such tuple per line         offsets into that line
    plain_spans(text, inks, lang) -> [(start, end, ink), ...]        for TypesetView.set_colours
    line_colours(inks)            -> the callable a diff view's `syntax=` takes

`tokens` is the tokeniser. The other three are it, cut to the coordinates a
consumer counts in. A code block (`imscribe.typeset_markdown.MarkdownCode`) is
coloured by plain offsets into its `text`, which is the text the typeset view
holds for it: `plain_spans`. A diff is coloured a line at a time in character
offsets of each line.

**What importing or calling this module loads: nothing of the layout core.**
It had a fourth shape, `colour_spans`, which coloured the old core's
`CodeBlock` by ranges of its node material through `imscribe.spans`; its last
caller went on 2026-10-11 and the function with it. What it inked is held as
literals in `tests/test_page_themes.py` (`OLD_SPANS`), against `plain_spans`.

**Lines are tokenised together and then cut apart**, never one at a time, because
a triple-quoted string or a block comment that opens on one line colours the lines
after it. `line_tokens` joins what it is given with newlines, tokenises once and
splits every token at the line ends. It can only know about the lines it was
handed: a chunk that starts inside a string someone opened earlier is coloured as
code, which is what any highlighter given a fragment does.

## What is recognised

Four kinds, because four inks is what the demo's schemes carry (`SyntaxInks`):
`"comment"`, `"string"`, `"number"`, `"keyword"`. Everything else is left in the
block's own ink and produces no token.

- **Python** (`python`, `py`, `python3`, `pycon`): `#` comments, single- and
  triple-quoted strings with any of the `rbfuRBFU` prefixes, numbers including
  hex, underscores and exponents, and the keywords plus `None`/`True`/`False`.
  No f-string interiors, no decorators as a kind, no soft keywords.
- **Everything else**, the generic fallback: `#` and `//` line comments (a `//`
  straight after a colon is a URL's and is left alone), `/* */` block comments,
  double- and single-quoted strings with backslash escapes, numbers, and no
  keywords at all -- a keyword list is what makes a tokeniser a language's, and
  guessing one colours `for` in a sentence. It is wrong about plenty: a `#` is a
  comment to it in C and in markdown alike, and an apostrophe opens a string.

An unterminated string runs to the end of its line (or of the text, for a
triple-quoted one), so a line being typed colours as it will when it is closed.

Not measured: speed. Both are one compiled alternation over the text, and the
demo's blocks are tens of lines.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "KINDS",
    "PYTHON_KEYWORDS",
    "SyntaxInks",
    "Token",
    "is_python",
    "line_colours",
    "line_tokens",
    "plain_spans",
    "tokens",
]

Token = tuple[int, int, str]
"""
`(start, end, kind)`: a half-open range of characters and which of `KINDS` it is.
"""

KINDS: Final = ("comment", "string", "number", "keyword")

PYTHON_KEYWORDS: Final = frozenset(
    "and as assert async await break class continue def del elif else except finally "
    "for from global if import in is lambda nonlocal not or pass raise return try while "
    "with yield None True False".split()
)

_PYTHON_NAMES: Final = frozenset({"python", "py", "python3", "pycon"})

_NUMBER: Final = (
    r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?[jJ]?)\b"
)

# Order is the tokeniser: a comment wins over the quote inside it, a string over
# the `#` inside it, and a triple quote is tried before the single one it starts
# with. Each string form has an unterminated tail so half a line still colours.
_PYTHON: Final = re.compile(
    r"(?P<comment>\#[^\n]*)"
    r"|(?P<string>(?:\b[rRbBfFuU]{1,2})?(?:"
    r'"""(?:[^\\]|\\.)*?(?:"""|\Z)'
    r"|'''(?:[^\\]|\\.)*?(?:'''|\Z)"
    r'|"(?:[^"\\\n]|\\.)*(?:"|(?=\n)|\Z)'
    r"|'(?:[^'\\\n]|\\.)*(?:'|(?=\n)|\Z)"
    r"))"
    rf"|(?P<number>{_NUMBER})"
    r"|(?P<word>\b[A-Za-z_]\w*\b)",
    re.DOTALL,
)

_GENERIC: Final = re.compile(
    r"(?P<comment>\#[^\n]*|(?<!:)//[^\n]*|/\*.*?(?:\*/|\Z))"
    r'|(?P<string>"(?:[^"\\\n]|\\.)*(?:"|(?=\n)|\Z)'
    r"|'(?:[^'\\\n]|\\.)*(?:'|(?=\n)|\Z))"
    rf"|(?P<number>{_NUMBER})"
    r"|(?P<word>\b[A-Za-z_]\w*\b)",
    re.DOTALL,
)


def is_python(language: str) -> bool:
    """
    Whether a fence's info string, or a diff's language, names Python.

    Only the first word is read, lower-cased: a fence may say `python title=x`.
    """
    words = language.strip().lower().split()
    return bool(words) and words[0] in _PYTHON_NAMES


def tokens(text: str, language: str = "") -> tuple[Token, ...]:
    """
    Every coloured range of `text`, in order, never overlapping.

    Python's rules for a Python `language`, the generic fallback for anything
    else including the empty string. Offsets are into `text` as given; nothing
    is stripped or expanded, so a caller that expanded tabs must tokenise the
    expanded text.
    """
    python = is_python(language)
    pattern = _PYTHON if python else _GENERIC
    found: list[Token] = []
    for match in pattern.finditer(text):
        kind = match.lastgroup
        if kind == "word":
            # Words are matched so that a keyword inside an identifier, and a
            # digit run inside a name, are consumed and not coloured.
            if not python or match.group() not in PYTHON_KEYWORDS:
                continue
            kind = "keyword"
        if kind is None or match.end() == match.start():
            continue
        found.append((match.start(), match.end(), kind))
    return tuple(found)


def line_tokens(lines: Sequence[str], language: str = "") -> tuple[tuple[Token, ...], ...]:
    """
    `tokens` over consecutive lines, as one tuple per line in that line's offsets.

    The lines are tokenised as one text, so a string opened on one of them
    colours the next; a token that crosses a line end is cut there and each
    piece keeps the kind. A line's own newline is never part of a piece.
    """
    starts: list[int] = []
    position = 0
    for line in lines:
        starts.append(position)
        position += len(line) + 1
    out: list[list[Token]] = [[] for _ in lines]
    row = 0
    for start, end, kind in tokens("\n".join(lines), language):
        while row + 1 < len(lines) and starts[row + 1] <= start:
            row += 1
        at = row
        while at < len(lines) and starts[at] < end:
            first = max(start, starts[at]) - starts[at]
            last = min(end, starts[at] + len(lines[at])) - starts[at]
            if last > first:
                out[at].append((first, last, kind))
            at += 1
    return tuple(tuple(line) for line in out)


@dataclass(frozen=True, slots=True)
class SyntaxInks:
    """
    One ink for each of `KINDS`, as ImGui packs a colour (`0xAABBGGRR`).

    Belongs to a colour scheme, beside its palette: the library's `Palette` has
    no syntax roles, because the library has no syntax.
    """

    keyword: int
    string: int
    comment: int
    number: int

    def ink(self, kind: str) -> int:
        """
        The ink for a token kind. `KeyError` for a kind that is not in `KINDS`.
        """
        if kind not in KINDS:
            raise KeyError(kind)
        return int(getattr(self, kind))


def plain_spans(text: str, inks: SyntaxInks, language: str = "") -> list[tuple[int, int, int]]:
    """
    `(start, end, ink)` for every token of `text`: plain offsets, in order, never overlapping.

    The shape `imscribe.ui.typeset_view.TypesetView.set_colours(block, spans)`
    takes for a code block of the direct path, whose text in the view IS the
    block's `text`:

        view.set_colours(number, plain_spans(block.text, inks, block.language))

    Nothing is converted and nothing of the layout core is asked: the offsets
    are `tokens`' own. `text` must be the text the view holds (tabs already
    expanded), since an offset into any other string is another place.
    """
    return [(start, end, inks.ink(kind)) for start, end, kind in tokens(text, language)]


def line_colours(
    inks: SyntaxInks,
) -> Callable[[Sequence[str], str], tuple[tuple[tuple[int, int, int], ...], ...]]:
    """
    A highlighter in the shape a diff view's `syntax=` takes.

    `(lines, language)` to, for each line, `(start, end, colour)` in character
    offsets of that line. Bound to one set of inks, so a page changing scheme
    makes a new one.
    """

    def colour(lines: Sequence[str], language: str) -> tuple[tuple[tuple[int, int, int], ...], ...]:
        return tuple(
            tuple((start, end, inks.ink(kind)) for start, end, kind in line)
            for line in line_tokens(lines, language)
        )

    return colour

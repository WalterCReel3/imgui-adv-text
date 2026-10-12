r"""
The Chat page: a canned conversation in the pane a host for a language model has.

**Nothing here talks to a model or to a network.** `demo/chat/script.md` holds
six exchanges. The page opens with the first one finished; pressing Enter in
the box at the bottom posts whatever was typed as a user turn and plays the
*next canned reply*, a few characters at a time, through an
`advtext.typeset_markdown.MarkdownStream` at the rate the slider sets. After
the sixth the script starts again. The footer says so in words, every frame.

## How it is put together

`examples/chat_transcript.py` is the precedent; this is the same pane with the
rest of a chat client around it.

- **A finished message is an `advtext.ui.typeset_view.TypesetView`** given the
  message's markdown as a string; the library holds one document for it and
  lays it out when the width changes and at no other time.
- **The message arriving is an
  `advtext.ui.typeset_stream_view.TypesetStreamView`** over a `MarkdownStream`,
  last in the pane, and it is the one that follows the end: it keeps the
  bottom in sight while the reader is there and lets go when they scroll up.
  When its reply is complete it stays a view of a closed stream and stops
  following.
- **Every message is read with the same settings**, arriving or finished:
  link reference definitions off (`references=False`, which a stream is
  always read with -- a `[1]: url` line could arrive last and turn earlier
  text into links) and math on. So a reply is the same blocks while it
  streams and after.
- **A fenced `diff` is drawn by an embedded diff view**
  (`advtext.ui.typeset_hosts.TypesetDiffFences` as each view's `host_for`),
  growing a line at a time while it streams. A fence of anything else is a
  code block with the demo's syntax colours, laid on with `set_colours` as
  plain offsets into the block's text (`advtext.ui.pages._syntax.plain_spans`;
  the library ships no tokeniser).
- **One selection for the whole transcript**, diffs included: every view takes
  its turn on one counter, and Ctrl+C copies from whichever was selected in
  last. A selection is `((block, offset), (block, offset))`.

## When the library is not drawing

There is no other renderer, and a message is a view: there is no
`Conversation` without the library (making one raises `TypesetUnavailable`).
So the page holds the script, the preset and the rate from the start and
makes its conversation on the first frame the library can draw. While
`advtext.typesetter.ready()` is false it draws ONE wrapped line and nothing
else (`advtext.ui.pages.typeset.say_why_not`).

A call that raises `TypesetUnavailable` ends that frame's drawing; the page
keeps the sentence and from the next frame on draws the one line, for good.
The exception does not leave `draw`, nor `send`. Any other exception is a bug
and is not caught. The page asks `ready()` and never `typesetter.module()`
(`advtext/ui/pages/typeset.py` has why).

## The controls on a block and on a message

Drawn over the top right corner of a block, after the view, so the view sees
them as items in front and leaves their clicks alone. A block's top is asked
of the library (`TypesetView.block_rect`), one call for each fenced block of
each message whose own rectangle meets the window:

- on a code block, `copy`: the block's source **without the fence**, cut from
  the message's markdown (tabs as typed), with the fence's own indentation
  removed;
- on a diff, `copy` (the fence's body: the patch) and a toggle between unified
  and side by side for that block.

Under each message, `copy as markdown`: the message's source, verbatim.

A user turn's bar is as tall as `TypesetView.height`, which is an estimate
until every block of the message has been in view once.

## The footer

One line naming the renderer, four figures and one statement. **None of them
is a measure of quality.**

- *page draw*: how long this page's `draw` took on the last frame, in
  milliseconds: the page's own work and the library's layout and draw of
  what is in view. Not the frame: ImGui's own render and the buffer swap are
  outside it.
- *per appended token*: on frames that appended pieces, the time to append
  them and take them in (`TypesetStreamView.sync`: the parse, the
  description, the one edit handed to the library), divided by the pieces
  appended. The last such frame and the mean over the reply. The library
  lays text out inside its draw, so layout is in *page draw* and cannot be
  told apart from it.
- messages; the arriving message's live and committed blocks.

There is no count of glyphs or of glyphs missing; `report` gives vertices and
how many messages the library did not set wholly as asked.

## Presets

*Mono, ragged* is one monospace face set ragged right at 15 px, which is what
pptmstr's transcript is and the first preset for that reason: its stream is
read in the one (ragged) theme throughout. *Roboto, justified* is the demo's
own theme: the tail is read ragged and a block again in the page's theme when
it commits (`MarkdownStream(theme, live_theme=...)`). Changing preset rebuilds
every message, and replays what has arrived of the unfinished one.

**The one thing here that can still reach the old core, and only before
the library has its fonts**: the mono preset sizes its theme with
`Theme.at_pixel_height(..., metrics=context.metrics)`. The page is built
before there is a window, so that first measurement of a face's ascent,
descent and em is `advtext.style.fontlib_metrics` over `advtext.fontlib`,
imported when the call is made and not with this module. A theme sized
after `typesetter.load_fonts()` is measured by the library and is the
same theme (`advtext.typeset_metrics`).

## What has been run

`tests/test_page_chat.py`: the script, the presets and the page's one line
with no library; the conversation's clock over a stand-in for the views; and,
in children that load the library, a whole conversation on a clock advanced
by hand, a streamed reply held to the document the same text gives whole, the
page in ImGui frames with no backend (a post, the wheel, the buttons), and
once in a real window at a rate that spans many edits. Nobody has looked at
it.

Options (`--tab chat:...`): `mono` or `roboto` picks the preset; `play` posts
the next canned turn as the page opens; `all` posts every turn and finishes
each at once; an integer is the tokens per second.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Final

from advtext import typesetter
from advtext.primitives import Face
from advtext.theme import Align, Faces, Theme
from advtext.typeset_markdown import MarkdownCode, MarkdownStream
from advtext.ui.ownership import MIN_WIDTH_PX, clipboard_text
from advtext.ui.pages import PageContext, PageSpec, caption, demo_text
from advtext.ui.pages._syntax import SyntaxInks, line_colours, plain_spans
from advtext.ui.pages.stream import ragged
from advtext.ui.pages.typeset import say_why_not, why_not
from advtext.ui.palette import DARK_PALETTE, Palette, rgba
from advtext.ui.typeset_hosts import TypesetDiffFences
from advtext.ui.typeset_stream_view import TypesetStreamView
from advtext.ui.typeset_view import TypesetUnavailable, TypesetView

__all__ = [
    "ASSISTANT",
    "DEFAULT_TOKENS_PER_SECOND",
    "FALLBACK",
    "MAX_TOKENS_PER_SECOND",
    "MONO",
    "PAGE",
    "PRESETS",
    "ROBOTO",
    "TEXT_WIDTH_PX",
    "USER",
    "USER_PALETTE",
    "ChatPage",
    "Conversation",
    "Exchange",
    "Message",
    "Preset",
    "fence_body",
    "parse_script",
    "readouts",
    "tokens",
]

USER: Final = "you"
ASSISTANT: Final = "assistant"

DEFAULT_TOKENS_PER_SECOND: Final = 60.0
MAX_TOKENS_PER_SECOND: Final = 2000.0

TEXT_WIDTH_PX: Final = 780.0
"""
The widest a message is set: the body is 1068 px, and a line that long is not a chat's.
"""

DIFF_CAP_PX: Final = 320.0
"""
The tallest an embedded diff grows before it scrolls inside itself.
"""

USER_INDENT_PX: Final = 28.0
USER_INK: Final = rgba(0xB9, 0xD3, 0xF0)
USER_BAR: Final = rgba(0x5B, 0x8D, 0xC9)
"""
A user turn is indented, set in `USER_INK`, and has a bar down its left edge.

This page's own chrome, like every colour here that is not a palette's: nobody
has judged any of them.
"""

USER_PALETTE: Final = replace(DARK_PALETTE, ink=USER_INK)
"""The palette a user turn is drawn with."""

SYNTAX: Final = SyntaxInks(
    keyword=rgba(0xC5, 0x86, 0xC0),
    string=rgba(0xCE, 0x91, 0x78),
    comment=rgba(0x6A, 0x99, 0x55),
    number=rgba(0xB5, 0xCE, 0xA8),
)


FALLBACK: Final = (
    "%% user\nIs there a script?\n"
    "%% assistant\nNo `demo/chat/script.md` was found, so this one canned reply is all "
    "there is. It still arrives through a `MarkdownStream`:\n\n"
    "```diff\n@@ -1 +1 @@\n-no script\n+one reply\n```\n"
)

_TURN: Final = re.compile(r"^%% (user|assistant)[ \t]*$", re.MULTILINE)


# ----------------------------------------------------------------------
# The script
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Exchange:
    """
    One canned exchange: what the user is taken to have asked, and the reply that plays.
    """

    prompt: str
    reply: str


def parse_script(text: str) -> tuple[Exchange, ...]:
    """
    The exchanges of a script: each `%% user` turn with the `%% assistant` turn after it.

    A turn runs from the line after its `%% role` line to the next such line.
    A user turn with no assistant turn after it, and an assistant turn with no
    user turn before it, are left out: the page plays whole exchanges.
    """
    marks = list(_TURN.finditer(text))
    if not marks:
        return ()
    ends = [mark.start() for mark in marks[1:]] + [len(text)]
    turns = [
        (mark.group(1), text[mark.end() : end].strip("\n") + "\n")
        for mark, end in zip(marks, ends, strict=True)
    ]
    exchanges = [
        Exchange(first[1], second[1])
        for first, second in zip(turns, turns[1:], strict=False)
        if first[0] == "user" and second[0] == "assistant"
    ]
    return tuple(exchanges)


def tokens(source: str) -> list[str]:
    """
    `source` in pieces of at most four visible characters, each with the white space before it.
    """
    return re.findall(r"\s*\S{1,4}|\s+", source)


def fence_body(source: str) -> str:
    """
    A fenced block's markdown without its fence: the lines between, less the fence's indentation.

    `source` is the block's own source lines (`TypesetView.block_source`). The
    closing fence is left out when there is one; a fence still open has none.
    Text that does not begin with a fence comes back unchanged -- an indented
    code block, or a fence that shares its first line with a list marker.
    """
    lines = source.splitlines(keepends=True)
    if not lines:
        return ""
    opener = lines[0].lstrip(" ")
    mark = opener[:1]
    if mark not in ("`", "~") or not opener.startswith(mark * 3):
        return source
    indent = len(lines[0]) - len(opener)
    run = len(opener) - len(opener.lstrip(mark))
    body = lines[1:]
    if body:
        closing = body[-1].strip()
        if closing and not closing.strip(mark) and len(closing) >= run:
            body = body[:-1]
    out = []
    for line in body:
        cut = 0
        while cut < indent and line[cut : cut + 1] == " ":
            cut += 1
        out.append(line[cut:])
    return "".join(out)


# ----------------------------------------------------------------------
# Presets
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Preset:
    """
    One way of setting the transcript: its option word, its label, and whether it is the mono one.
    """

    key: str
    label: str
    mono: bool

    def theme(self, context: PageContext) -> Theme:
        """
        Mono: one monospace face at 15 px, ragged. Otherwise the demo's own theme.

        The mono theme is sized through `context.metrics`, which measures the
        face when called: the module docstring says what that still reaches.
        """
        if not self.mono:
            return context.theme
        return Theme.at_pixel_height(
            15.0,
            context.px_per_inch,
            faces=Faces.mono(bold=Face.CODE),
            align=Align.LEFT,
            metrics=context.metrics,
        )


MONO: Final = Preset("mono", "Mono, ragged", True)
ROBOTO: Final = Preset("roboto", "Roboto, justified", False)
PRESETS: Final = (MONO, ROBOTO)


# ----------------------------------------------------------------------
# The conversation: no ImGui
# ----------------------------------------------------------------------


@dataclass
class Message:
    """
    One turn: who, the view that draws it, and what its blocks have been given.

    `stream` is set for a reply that arrived (or is arriving) through one;
    `markdown` is then the stream's text so far. `codes` are the numbers of
    its fenced blocks, diffs included, for the buttons the page draws on them.
    """

    role: str
    source: str
    view: Any
    """A `TypesetView`; a `TypesetStreamView` for a reply that arrived through a stream."""
    fences: TypesetDiffFences
    """The view's `host_for`."""
    stream: MarkdownStream | None = None
    """The stream of a reply; `None` for a message given whole."""
    codes: tuple[int, ...] = ()
    whole: bool = True
    """Whether the library's last draw set everything in view as asked."""
    vertices: int = 0
    """Vertices the view's last draw added to the pane's draw list."""
    _coloured: int = 0

    @property
    def blocks(self) -> tuple[Any, ...]:
        """
        The message's blocks, as its view has them (after its last `sync`, when arriving).
        """
        return tuple(self.view.blocks)

    @property
    def markdown(self) -> str:
        """
        The message's source, verbatim: what "copy as markdown" copies.
        """
        return self.source if self.stream is None else self.stream.source

    def diff(self, block: int) -> Any:
        """
        The embedded diff drawing block `block` (a `HostedDiff`), or `None` if it is not a diff.
        """
        if self.fences.view_of(self.view, block) is None:
            return None
        return self.view.hosted(block)

    def block_code(self, block: int) -> str:
        """
        What the `copy` button on a fenced block copies: its source without the fence.

        A diff's is the fence body its view read. A code block's is cut from
        the markdown; one with no source record gives its text as set.
        """
        hosted = self.diff(block)
        if hosted is not None:
            return str(hosted.text)
        source = self.view.block_source(block, self.markdown)
        if source is None:
            return str(self.view.block_text(block))
        return fence_body(source)


@dataclass
class Conversation:
    """
    The transcript, the reply arriving, and the clock that feeds it.

    `post` adds a user turn and starts the next canned reply; `advance` appends
    the pieces a span of time allows; `settle` takes them into the arriving
    message's view and times that. Nothing here needs a window.

    **It needs the library**: a message is a view, so making a conversation,
    posting to one and settling one are library calls and raise
    `TypesetUnavailable` when imtypeset is not in use.
    """

    context: PageContext
    exchanges: tuple[Exchange, ...]
    preset: Preset = MONO
    tokens_per_second: float = DEFAULT_TOKENS_PER_SECOND
    timer: Callable[[], float] = time.perf_counter

    messages: list[Message] = field(init=False)
    pieces: list[str] = field(default_factory=list, init=False)
    fed: int = field(default=0, init=False)
    posted: int = field(default=0, init=False)
    """How many exchanges have been played, the opening one included."""
    theme: Theme = field(init=False)
    token_ms: float = field(default=0.0, init=False)
    """Milliseconds per piece on the last frame that appended any."""
    token_total_ms: float = field(default=0.0, init=False)
    token_count: int = field(default=0, init=False)
    _owed: float = field(default=0.0, init=False)
    _pending: tuple[float, int] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.exchanges:
            self.exchanges = parse_script(FALLBACK)
        self.theme = self.preset.theme(self.context)
        first = self.exchanges[0]
        self.messages = [self._finished(USER, first.prompt), self._finished(ASSISTANT, first.reply)]
        self.posted = 1

    # -- building messages -------------------------------------------------

    def _fences(self, source: str | None) -> TypesetDiffFences:
        return TypesetDiffFences(source=source, height_cap=DIFF_CAP_PX, syntax=line_colours(SYNTAX))

    def _finished(self, role: str, source: str) -> Message:
        fences = self._fences(source)
        view = TypesetView(
            # Definitions off and math on, exactly as a stream reads.
            source,
            theme=self.theme,
            palette=USER_PALETTE if role == USER else DARK_PALETTE,
            math=True,
            references=False,
            host_for=fences,
        )
        message = Message(role, source, view, fences)
        self._colour(message)
        return message

    def _streaming(self, role: str) -> Message:
        fences = self._fences(None)
        # One theme, ragged, for the mono preset; for the other, the tail
        # ragged and a block again in the page's theme when it commits.
        live = ragged(self.theme)
        if self.preset.mono:
            stream = MarkdownStream(live, math=True)
        else:
            stream = MarkdownStream(self.theme, math=True, live_theme=live)
        view = TypesetStreamView(stream, palette=DARK_PALETTE, host_for=fences)
        return Message(role, "", view, fences, stream=stream)

    def _colour(self, message: Message) -> None:
        """
        Syntax colours for the code blocks not yet settled, and the list of fenced blocks.

        A committed block is coloured once. The blocks of a stream's unfinished
        tail are coloured again each time it changes, which for a code block
        still being written is a pass over the whole block.
        """
        blocks = message.blocks
        settled = len(blocks) if message.stream is None else len(message.stream.committed)
        codes = [number for number in message.codes if number < message._coloured]
        for number in range(message._coloured, len(blocks)):
            block: Any = blocks[number]
            if not isinstance(block, MarkdownCode):
                continue
            codes.append(number)
            # A fence is `di` and `dif` on its way to `diff`, and is a code
            # block until its info string says otherwise: what it was
            # coloured as then is taken off again. The spans are plain
            # offsets into the block's text, which is what the view's
            # `texts[number]` is for a code block.
            spans: Any = ()
            if not message.fences.accepts(block):
                spans = plain_spans(block.text, SYNTAX, block.language)
            message.view.set_colours(number, spans)
        message.codes = tuple(codes)
        message._coloured = settled

    # -- the clock ---------------------------------------------------------

    @property
    def live(self) -> Message | None:
        """
        The message arriving, or `None` when the last reply is complete.
        """
        last = self.messages[-1]
        if last.stream is not None and not last.stream.closed:
            return last
        return None

    @property
    def done(self) -> bool:
        return self.live is None

    @property
    def next(self) -> Exchange:
        """
        The exchange the next `post` plays. After the last, the first again.
        """
        return self.exchanges[self.posted % len(self.exchanges)]

    def post(self, text: str = "") -> Message:
        """
        Add a user turn -- `text`, or the script's own prompt if it is blank -- and start the reply.

        A reply still arriving is finished at once first: a host would cancel
        it, and a canned one has nothing to cancel.
        """
        self.finish()
        last = self.messages[-1]
        if last.stream is not None:
            # Finished without ever being drawn (`finish` straight after
            # `post`): its blocks have not been looked at yet.
            if last.view.sync():
                self._colour(last)
        exchange = self.next
        self.posted += 1
        asked = text if text.strip() else exchange.prompt
        self.messages.append(self._finished(USER, asked if asked.endswith("\n") else asked + "\n"))
        for message in self.messages:
            if message.stream is not None:
                # Only the message arriving scrolls the pane.
                message.view.follow = False
        reply = self._streaming(ASSISTANT)
        self.messages.append(reply)
        reply.view.follow_tail()
        self.pieces = tokens(exchange.reply)
        self.fed = 0
        self._owed = 0.0
        self.token_total_ms = 0.0
        self.token_count = 0
        return reply

    def _feed(self, count: int) -> int:
        live = self.live
        if live is None or live.stream is None:
            return 0
        count = max(0, min(count, len(self.pieces) - self.fed))
        began = self.timer()
        for piece in self.pieces[self.fed : self.fed + count]:
            live.stream.append(piece)
        self.fed += count
        if self.fed >= len(self.pieces):
            live.stream.close()
            self._owed = 0.0
        if count:
            spent, before = self._pending or (0.0, 0)
            self._pending = (spent + self.timer() - began, before + count)
        return count

    def advance(self, seconds: float) -> int:
        """
        Append the pieces `seconds` of the clock allow. Returns how many.
        """
        if self.done:
            return 0
        self._owed += max(0.0, seconds) * max(0.0, self.tokens_per_second)
        # A hair over, so sixty sixtieths of a second at forty a second is forty.
        count = int(self._owed + 1e-6)
        self._owed -= count
        return self._feed(count)

    def finish(self) -> int:
        """
        Append everything left of the reply arriving, and close it.
        """
        return self._feed(len(self.pieces) - self.fed)

    def settle(self) -> None:
        """
        Take what was appended into the last message's view, and time it.

        The page calls this just before it draws; a test calls it instead of
        drawing. With nothing appended since the last call it parses nothing
        and records nothing.

        There is no layout to ask for here: the library lays text out when it
        draws. What is timed is `sync` (the parse, the description and the
        one edit) and the colouring of what changed.
        """
        last = self.messages[-1]
        if last.stream is None:
            return
        began = self.timer()
        if last.view.sync():
            self._colour(last)
        if self._pending is not None:
            spent, count = self._pending
            self._pending = None
            spent += self.timer() - began
            self.token_ms = spent * 1000.0 / count
            self.token_total_ms += spent * 1000.0
            self.token_count += count

    @property
    def token_mean_ms(self) -> float:
        return self.token_total_ms / self.token_count if self.token_count else 0.0

    # -- presets -------------------------------------------------------------

    def set_preset(self, preset: Preset) -> None:
        """
        Set the whole transcript another way: new theme, every message built again.

        Each view there was gives its document back to the library. The reply
        arriving is replayed up to where it had got to, into a new stream, and
        goes on from there.
        """
        if preset is self.preset:
            return
        self.preset = preset
        self.theme = preset.theme(self.context)
        for message in self.messages:
            message.view.close()
        rebuilt: list[Message] = []
        for message in self.messages:
            if message.stream is None or message.stream.closed:
                rebuilt.append(self._finished(message.role, message.markdown))
                continue
            again = self._streaming(message.role)
            assert again.stream is not None
            again.stream.append(message.markdown)
            rebuilt.append(again)
        self.messages = rebuilt

    def counts(self) -> tuple[int, int, int]:
        """
        Messages, and the last message's live and committed blocks (zero and all, when finished).
        """
        last = self.messages[-1]
        if last.stream is None:
            return len(self.messages), 0, len(last.blocks)
        return len(self.messages), len(last.stream.live), len(last.stream.committed)


def readouts(conversation: Conversation, draw_ms: float) -> tuple[str, ...]:
    """
    The footer's two lines: what is canned, then the figures. Counts and costs, no judgement.
    """
    messages, live, committed = conversation.counts()
    state = (
        "reply complete"
        if conversation.done
        else f"reply arriving, piece {conversation.fed} of {len(conversation.pieces)}"
    )
    return (
        "Replies are canned: read from demo/chat/script.md and replayed through a "
        f"MarkdownStream. No model, no network.  ·  {state}",
        f"page draw {draw_ms:.1f} ms  ·  per appended token {conversation.token_ms:.2f} ms "
        f"(mean {conversation.token_mean_ms:.2f} over {conversation.token_count})  ·  "
        f"{messages} messages  ·  blocks: {live} live, {committed} committed",
    )


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------


RENDERER_LINE: Final = (
    "renderer: TypesetView / TypesetStreamView (imtypeset), diffs by TypesetDiffFences"
)
"""The first footer line while the library draws."""


class ChatPage:
    """
    The page: a `Conversation`, the pane that draws it, the box that posts to it.

    `conversation` is `None` until the first frame the library can draw
    (`open`): the script, the preset and the rate are the page's until then.
    """

    def __init__(self, context: PageContext) -> None:
        self.context = context
        words = context.options_for(PAGE.name)
        rate = context.count_for(PAGE.name)
        text = demo_text("chat/script.md")
        self.exchanges = parse_script(text if text is not None else FALLBACK) or parse_script(
            FALLBACK
        )
        """The script the conversation plays."""
        self.preset = ROBOTO if "roboto" in words else MONO
        """The preset the conversation opens in; the conversation's own once there is one."""
        self.tokens_per_second = DEFAULT_TOKENS_PER_SECOND if rate is None else float(rate)
        self.opening = "all" if "all" in words else "play" if "play" in words else ""
        """What the launch asked played as the conversation opens: `all`, `play` or nothing."""
        self.conversation: Conversation | None = None
        self.typed = ""
        self.frames = 0
        self.draw_ms = 0.0
        self.copied = 0
        """How many times a button of this page has written the clipboard."""
        self.failed = ""
        """What a `TypesetUnavailable` out of a frame or a post said; empty until one was raised."""
        self._refocus = False
        self._released = False

    @property
    def reason(self) -> str:
        """
        Why imtypeset is not drawing this page; empty while it is.

        What a frame raised, for good once one has; otherwise `why_not()`, read
        at each asking.
        """
        return self.failed or why_not()

    @property
    def renderer(self) -> str:
        """`"typeset"` while imtypeset draws the messages, `"none"` when nothing does."""
        return "none" if self.reason else "typeset"

    def open(self) -> Conversation:
        """
        The conversation, made if there is none yet, with what the launch asked played.

        Raises `TypesetUnavailable` when the library is not in use: every
        message is a view. The page calls this at the top of a frame it is
        about to draw, and nowhere else.
        """
        if self.conversation is None:
            made = Conversation(
                self.context,
                self.exchanges,
                preset=self.preset,
                tokens_per_second=self.tokens_per_second,
            )
            if self.opening == "all":
                for _ in range(len(made.exchanges) - 1):
                    made.post()
                    made.finish()
            elif self.opening == "play":
                made.post()
            self.conversation = made
        return self.conversation

    # -- what the controls do --------------------------------------------

    def send(self) -> None:
        """
        What Enter in the box does: post what was typed, play the next canned reply.

        Nothing while there is no conversation. A post takes in the reply that
        was arriving, which is an edit in the library: `TypesetUnavailable`
        from it is kept as the page's reason, as one out of a frame is, and
        what was typed stays in the box.
        """
        if self.conversation is None or self.reason:
            return
        try:
            self.conversation.post(self.typed)
        except TypesetUnavailable as exc:
            self._fail(exc)
            return
        self.typed = ""
        self._refocus = True

    def _fail(self, exc: TypesetUnavailable) -> None:
        self.failed = str(exc) or typesetter.reason() or "imtypeset raised TypesetUnavailable"
        self._release()

    def _release(self) -> None:
        """
        Give back what the page's views hold in the library, once, when the page gives up.

        Called when a frame or a call raised `TypesetUnavailable` and on the
        first frame that finds the library not drawing. The views are closed
        and KEPT, with everything else the page knows: `report()` reads them,
        and a closed view makes its document again if it is ever drawn. Until
        2026-10-11 only the Diff page let go of anything.
        """
        if self._released:
            return
        self._released = True
        if self.conversation is not None:
            for message in self.conversation.messages:
                # A fenced diff is a view of its own with documents of its own.
                for block in getattr(message.view, "hosts", ()):
                    diff = message.fences.view_of(message.view, block)
                    if diff is not None:
                        diff.close()
                message.view.close()

    def _message_at(self, index: int) -> Message:
        if self.conversation is None:
            raise LookupError("the page has no conversation: imtypeset is not drawing")
        return self.conversation.messages[index]

    def copy_markdown(self, index: int) -> str:
        """
        What "copy as markdown" under message `index` does. Returns what it copied.
        """
        return self._copy(self._message_at(index).markdown)

    def copy_block(self, index: int, block: int) -> str:
        """
        What `copy` on a fenced block does: its source without the fence.
        """
        return self._copy(self._message_at(index).block_code(block))

    def toggle_diff(self, index: int, block: int) -> Any:
        """
        What the toggle on a diff does: unified to side by side and back. The layout it is now in.

        A member of `advtext.ui.typeset_diff_view.DiffLayout`, or `None` if
        the block is not a diff.
        """
        hosted = self._message_at(index).diff(block)
        if hosted is None:
            return None
        layouts = type(hosted.view.layout)
        unified = hosted.view.layout is layouts.UNIFIED
        hosted.view.set_layout(layouts.SIDE_BY_SIDE if unified else layouts.UNIFIED)
        return hosted.view.layout

    def _copy(self, text: str) -> str:
        """
        Put `text` on the clipboard and return it as it was given.

        Through `advtext.ui.ownership.clipboard_text`, as every copy of the
        views goes: a NUL reaches the clipboard as U+2400 instead of ending
        the text there (review 3, item 9). What is returned is the source,
        NUL and all.
        """
        from imgui_bundle import imgui

        imgui.set_clipboard_text(clipboard_text(text))
        self.copied += 1
        return text

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts. All zero while there is no conversation.
        """
        conversation = self.conversation
        if conversation is None:
            return [
                f"frames={self.frames} messages=0 posted=0 fed=0 pieces=0 done=0 live=0 "
                f"committed=0 tokens_timed=0 diffs=0 diff_lines=0 codes=0 following=0 "
                f"edits=0 vertices=0 not_whole=0 preset={self.preset.key} "
                f"renderer={self.renderer}"
            ]
        messages, live, committed = conversation.counts()
        last = conversation.messages[-1]
        return [
            f"frames={self.frames} messages={messages} posted={conversation.posted} "
            f"fed={conversation.fed} pieces={len(conversation.pieces)} "
            f"done={int(conversation.done)} live={live} committed={committed} "
            f"tokens_timed={conversation.token_count} "
            f"diffs={sum(1 for m in conversation.messages for n in m.codes if m.diff(n))} "
            f"diff_lines={sum(m.fences.fed_lines for m in conversation.messages)} "
            f"codes={sum(len(m.codes) for m in conversation.messages)} "
            f"following={int(last.stream is not None and last.view.following)} "
            f"edits={sum(last.view.edits.values()) if last.stream is not None else 0} "
            f"vertices={sum(m.vertices for m in conversation.messages)} "
            f"not_whole={sum(1 for m in conversation.messages if not m.whole)} "
            f"preset={conversation.preset.key} renderer={self.renderer}"
        ]

    # -- the frame ---------------------------------------------------------

    def draw(self) -> None:
        from imgui_bundle import imgui

        began = time.perf_counter()
        self.frames += 1
        reason = self.reason
        if reason:
            self._release()
            say_why_not(reason)
            return
        self._released = False
        try:
            self._frame(imgui)
        except TypesetUnavailable as exc:
            # The library was switched off under this frame. What it had drawn
            # of the frame stays; from the next one on the page is the one line.
            self._fail(exc)
        self.draw_ms = (time.perf_counter() - began) * 1000.0

    def _frame(self, imgui: Any) -> None:
        """
        The header, the transcript, the box and the footer. `TypesetUnavailable` may leave it.

        The child window is ended on the way out, so the exception leaves
        ImGui's stack as it found it.
        """
        conversation = self.open()
        self._header(imgui, conversation)
        conversation.advance(imgui.get_io().delta_time)

        style = imgui.get_style()
        footer = (
            imgui.get_frame_height_with_spacing()
            + 3 * imgui.get_text_line_height_with_spacing()
            + style.item_spacing.y
        )
        # The scrollbar is always there, so the width the messages are broken
        # to does not change when the conversation first outgrows the pane;
        # the padding is asked for by name because the demo's style gives a
        # borderless child none.
        imgui.begin_child(
            "##advtext-chat-transcript",
            imgui.ImVec2(0.0, -footer),
            imgui.ChildFlags_.borders.value | imgui.ChildFlags_.always_use_window_padding.value,
            imgui.WindowFlags_.always_vertical_scrollbar.value,
        )
        try:
            for index in range(len(conversation.messages)):
                self._message(imgui, conversation, index)
        finally:
            imgui.end_child()

        self._input(imgui, conversation)
        caption(RENDERER_LINE)
        for line in readouts(conversation, self.draw_ms):
            caption(line)

    def _header(self, imgui: Any, conversation: Conversation) -> None:
        imgui.set_next_item_width(180.0)
        if imgui.begin_combo("##advtext-chat-preset", conversation.preset.label):
            try:
                for preset in PRESETS:
                    if imgui.selectable(preset.label, preset is conversation.preset)[0]:
                        conversation.set_preset(preset)
            finally:
                imgui.end_combo()
        imgui.same_line()
        imgui.set_next_item_width(220.0)
        changed, rate = imgui.slider_float(
            "tokens/s", conversation.tokens_per_second, 0.0, MAX_TOKENS_PER_SECOND
        )
        if changed:
            conversation.tokens_per_second = rate
        imgui.same_line()
        if imgui.button("Finish reply"):
            conversation.finish()
        imgui.same_line()
        _, self.context.debug = imgui.checkbox("debug overlay", self.context.debug)

    def _message(self, imgui: Any, conversation: Conversation, index: int) -> None:
        message = conversation.messages[index]
        user = message.role == USER
        palette: Palette = USER_PALETTE if user else DARK_PALETTE
        if user:
            imgui.indent(USER_INDENT_PX)
        try:
            imgui.text_disabled(message.role)
            width_px = max(min(imgui.get_content_region_avail().x, TEXT_WIDTH_PX), MIN_WIDTH_PX)
            if index == len(conversation.messages) - 1:
                conversation.settle()
            message.view.debug = self.context.debug
            buffer = imgui.get_window_draw_list().vtx_buffer
            before = buffer.size()
            message.whole = message.view.draw(palette=palette, width_px=width_px)
            message.vertices = buffer.size() - before
            height = float(message.view.height)
            origin = message.view.origin
            if origin is not None:
                if user:
                    imgui.get_window_draw_list().add_rect_filled(
                        imgui.ImVec2(origin[0] - 12.0, origin[1]),
                        imgui.ImVec2(origin[0] - 9.0, origin[1] + height),
                        USER_BAR,
                    )
                self._block_buttons(imgui, index, message, origin, width_px, height)
            if imgui.small_button(f"copy as markdown##advtext-chat-md-{index}"):
                self.copy_markdown(index)
        finally:
            if user:
                imgui.unindent(USER_INDENT_PX)
        imgui.spacing()

    def _block_tops(
        self,
        message: Message,
        origin: tuple[float, float],
        height: float,
        window: tuple[float, float],
    ) -> list[tuple[int, float]]:
        """
        Each fenced block of `message` with the screen y of its top, top to bottom.

        One library call a block (`TypesetView.block_rect`), made only when
        the message's own rectangle meets the window.
        """
        if not message.codes:
            return []
        if origin[1] + height <= window[0] or origin[1] >= window[1]:
            return []
        tops = []
        for block in message.codes:
            rect = message.view.block_rect(block)
            if rect is not None:
                tops.append((block, float(rect[1])))
        return tops

    def _block_buttons(
        self,
        imgui: Any,
        index: int,
        message: Message,
        origin: tuple[float, float],
        width_px: float,
        height: float,
    ) -> None:
        """
        `copy` on each fenced block on screen, and the layout toggle on each diff.

        Submitted after the view, at the block's top right corner, with the
        cursor put back afterwards: the view has already claimed its height
        and what follows it must not move.
        """
        window_top = imgui.get_window_pos().y
        window_bottom = window_top + imgui.get_window_size().y
        tops = self._block_tops(message, origin, height, (window_top, window_bottom))
        if not tops:
            return
        cursor = imgui.get_cursor_screen_pos()
        spacing = imgui.get_style().item_spacing.x
        for block, top in tops:
            if top + imgui.get_frame_height() <= window_top or top >= window_bottom:
                continue
            hosted = message.diff(block)
            labels = ["copy"]
            if hosted is not None:
                unified = hosted.view.layout.name == "UNIFIED"
                labels.insert(0, "side by side" if unified else "unified")
            x = origin[0] + width_px
            for label in reversed(labels):
                x -= imgui.calc_text_size(label).x + 2 * imgui.get_style().frame_padding.x
                imgui.set_cursor_screen_pos(imgui.ImVec2(x, top))
                if imgui.small_button(f"{label}##advtext-chat-{index}-{block}"):
                    if label == "copy":
                        self.copy_block(index, block)
                    else:
                        self.toggle_diff(index, block)
                x -= spacing
        imgui.set_cursor_screen_pos(cursor)

    def _input(self, imgui: Any, conversation: Conversation) -> None:
        send_width = imgui.calc_text_size("Send").x + 2 * imgui.get_style().frame_padding.x
        imgui.set_next_item_width(
            max(
                imgui.get_content_region_avail().x - send_width - imgui.get_style().item_spacing.x,
                80.0,
            )
        )
        if self._refocus:
            self._refocus = False
            imgui.set_keyboard_focus_here()
        hint = "Enter plays the next canned reply: " + conversation.next.prompt.strip()
        _, self.typed = imgui.input_text_with_hint("##advtext-chat-input", hint, self.typed)
        # Enter ends the edit; it is read on the frame the box lets go of the
        # keyboard, and the box is given the keyboard back. Only while it was
        # being typed in: ImGui's navigation rests on an item nobody chose.
        entered = imgui.is_item_deactivated() and (
            imgui.is_key_pressed(imgui.Key.enter, False)
            or imgui.is_key_pressed(imgui.Key.keypad_enter, False)
        )
        imgui.same_line()
        if imgui.button("Send") or entered:
            self.send()


PAGE = PageSpec(
    name="Chat",
    order=220,
    factory=ChatPage,
    group="Streaming",
    caption="a canned conversation: streaming replies, code, diffs, math, one selection",
    options=("mono", "roboto", "play", "all"),
    shots=("all", "roboto,all"),
)

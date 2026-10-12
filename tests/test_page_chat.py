"""
The Chat page: the script and the presets, the conversation's clock, the one
line the page draws without the library, the page in frames, and once in a
real window.

**Where each thing runs.** A message is a view and a view needs the imtypeset
library, which the pytest process never has ready (also under
`make test TYPESET=1`). So:

1. with no library, in the pytest process: the script's content, read off the
   blocks the direct markdown path makes of it; the presets; what the launch
   options set; the conversation's clock, its posting and its colouring over
   `_View` / `_StreamView`, stand-ins that read the markdown as the real views
   do and draw nothing; and the page itself, which is one line saying why not;
2. with the library, in a child of real ImGui frames with no window
   (`_HEADLESS`): a whole conversation on a clock advanced by hand, a streamed
   reply held to the document the same text gives whole, the hosted diff, the
   presets, and the page through `App.gui` -- a turn typed into the real
   `InputText` and entered, the wheel, the buttons, one selection; then a
   draw and a post made to raise, and the library switched off;
3. with the library, the real app in a real window, at a rate that spans many
   edits.

The children say THERE whether `typesetter.module()` and `ready()` held,
before the body and after it. Levels 2 and 3 are skipped, with the reason,
when `IMTYPESET_LIBRARY` is not set.

**Nothing here judges how a conversation looks.** The script's content is held
to what the task says it must exercise, and the counters to what can be counted.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from imscribe import typesetter
from imscribe.description import FACE_ROLES
from imscribe.fontmetrics import Face
from imscribe.theme import Align, BlockKind
from imscribe.typeset_markdown import (
    MarkdownCode,
    MarkdownStream,
    MarkdownTable,
    MarkdownText,
    parse_markdown,
)
from imscribe.ui import pages
from imscribe.ui.pages import PageContext
from imscribe.ui.pages import chat as page
from imscribe.ui.pages.chat import ASSISTANT, MONO, ROBOTO, USER, Conversation, Exchange
from imscribe.ui.pages.typeset import why_not

if TYPE_CHECKING:
    from conftest import Window

FRAME = 1.0 / 60.0

_ROOT = Path(__file__).resolve().parent.parent
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)
_SKIP = (
    "IMTYPESET_LIBRARY is not set: run `make test TYPESET=1` (after `make typeset-lib`) "
    "for the tests that need the imtypeset library"
)


@pytest.fixture(scope="module")
def script() -> tuple[Exchange, ...]:
    text = pages.demo_text("chat/script.md")
    assert text is not None, "demo/chat/script.md is missing"
    return page.parse_script(text)


@pytest.fixture(scope="module")
def context() -> PageContext:
    return PageContext.build()


class _View:
    """
    What stands where `TypesetView` does in the tests of what `Conversation` does with it.

    It reads the markdown it is given with the settings it is given, as the
    real view does, so `blocks` are the blocks the real view would hold; it
    keeps the colours it is handed and whether it was closed. It holds no
    document in any library, hosts nothing and draws nothing: no test that
    uses it asserts anything about a view.
    """

    made: list[_View] = []

    def __init__(self, source: str, *, theme: Any, **settings: Any) -> None:
        self.settings = {"theme": theme, **settings}
        self._parsed = tuple(
            parse_markdown(
                source,
                theme,
                math=bool(settings.get("math")),
                references=bool(settings.get("references", True)),
            ).blocks
        )
        self.colours: dict[int, int] = {}
        self.closed = False
        _View.made.append(self)

    @property
    def blocks(self) -> tuple[Any, ...]:
        return self._parsed

    def set_colours(self, block: int, spans: Any) -> None:
        self.colours[block] = len(list(spans))

    def close(self) -> None:
        self.closed = True


class _StreamView(_View):
    """
    The same, where `TypesetStreamView` stands: the blocks are the stream's, as of the last `sync`.
    """

    def __init__(self, stream: MarkdownStream, **settings: Any) -> None:
        self.stream = stream
        self.settings = settings
        self.colours = {}
        self.closed = False
        self.follow = True
        self.tailed = 0
        self.edits = {"set": 0, "replace": 0, "append": 0}
        self.following = True
        self._revision: int | None = None
        self._parsed = ()
        self.sync()
        _View.made.append(self)

    def sync(self) -> bool:
        revision = self.stream.revision
        if revision == self._revision:
            return False
        self._revision = revision
        self._parsed = tuple(self.stream.blocks)
        return True

    def follow_tail(self) -> None:
        self.tailed += 1


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch) -> type[_View]:
    """
    The two stand-ins under the page module's names for the views, for one test.
    """
    monkeypatch.setattr(page, "TypesetView", _View)
    monkeypatch.setattr(page, "TypesetStreamView", _StreamView)
    monkeypatch.setattr(_View, "made", [])
    return _View


def _talk(context: PageContext, script: tuple[Exchange, ...], **fields: Any) -> Conversation:
    return Conversation(context, script, **fields)


def _play(conversation: Conversation, seconds: float = FRAME) -> int:
    """
    Tick and settle until the reply is complete. Returns the ticks; fails if it never ends.
    """
    ticks = 0
    while not conversation.done:
        conversation.advance(seconds)
        conversation.settle()
        ticks += 1
        assert ticks < 100_000, "the reply never finished"
    conversation.settle()
    return ticks


# ----------------------------------------------------------------------
# The script
# ----------------------------------------------------------------------


def test_the_script_exercises_what_the_page_is_for(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    """
    Read off the blocks each reply becomes -- the direct path's, read as the
    page's views read a message: definitions off, math on -- and not off the
    markdown's spelling.
    """
    assert len(script) == 6
    seen: set[str] = set()
    code_faces = {FACE_ROLES["CODE"], FACE_ROLES["CODE_BOLD"]}
    for exchange in script:
        assert exchange.prompt.strip() and exchange.reply.strip()
        blocks = parse_markdown(exchange.reply, context.theme, references=False, math=True).blocks
        for block in blocks:
            match block:
                case MarkdownCode():
                    seen.add("diff" if block.language == "diff" else "code")
                    if block.left_indent > block.style.left_indent:
                        seen.add("fence in a list item")
                case MarkdownTable():
                    seen.add("table")
                case MarkdownText():
                    if block.links:
                        seen.add("link")
                    if block.marker and block.kind is BlockKind.ORDERED_ITEM:
                        seen.add("numbered item")
                    elif block.kind is BlockKind.ORDERED_ITEM:
                        seen.add("indented paragraph of an item")
                    if any(run.face in code_faces for run in block.runs):
                        seen.add("inline code")
                    for formula in block.formulas:
                        assert formula.state == "set", (formula.source, formula.state)
                        seen.add("display formula" if formula.display else "inline formula")
        if len(blocks) >= 30:
            seen.add("a long reply")
    assert seen >= {
        "code",
        "diff",
        "fence in a list item",
        "table",
        "link",
        "numbered item",
        "inline code",
        "inline formula",
        "display formula",
        "a long reply",
    }, sorted(seen)


def test_the_diff_reply_ends_in_its_fence_and_keeps_a_shells_dollars(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    """
    Two shapes review 2 asked the demo to show. A reply that *ends* with a
    diff fence -- the common shape of a patch, and the one whose copy was
    measured wrong at a document's edge. And a shell line outside code, whose
    dollar signs are not math: `PATH=$HOME/bin:$PATH` stays as typed while
    `$x^2$` in the same paragraph is the one formula.
    """
    (reply,) = [exchange.reply for exchange in script if "```diff" in exchange.reply]
    assert reply.rstrip("\n").endswith("```")
    blocks = parse_markdown(reply, context.theme, references=False, math=True).blocks
    last = blocks[-1]
    assert isinstance(last, MarkdownCode) and last.language == "diff"
    first = blocks[0]
    assert isinstance(first, MarkdownText)
    assert [(formula.source, formula.state) for formula in first.formulas] == [("x^2", "set")]
    assert "PATH=$HOME/bin:$PATH" in first.text


def test_a_script_is_whole_exchanges_and_tokens_join_back() -> None:
    text = "junk\n%% assistant\norphan\n%% user\nq1\n%% assistant\na1\n\nmore\n%% user\nq2\n"
    assert page.parse_script(text) == (Exchange("q1\n", "a1\n\nmore\n"),)
    assert page.parse_script("no turns") == ()
    (fallback,) = page.parse_script(page.FALLBACK)
    assert "```diff" in fallback.reply and "StreamDocument" not in fallback.reply
    pieces = page.tokens(fallback.reply)
    assert "".join(pieces) == fallback.reply and max(len(p.strip()) for p in pieces) <= 4


@pytest.mark.parametrize(
    ("source", "body"),
    [
        ("```python\na\n\tb\n```\n", "a\n\tb\n"),
        ("```python\na\n", "a\n"),
        ("   ```\n   a\n     b\n   ```\n", "a\n  b\n"),
        ("~~~~\n```\n~~~~\n", "```\n"),
        ("    indented\n", "    indented\n"),
        ("", ""),
    ],
)
def test_a_fence_body_is_the_lines_between_less_the_fences_indent(source: str, body: str) -> None:
    assert page.fence_body(source) == body


# ----------------------------------------------------------------------
# The presets: no library
# ----------------------------------------------------------------------


def test_the_presets_are_what_they_say(context: PageContext) -> None:
    """
    Mono: one monospace face, ragged, sized to 15 px through the context's
    metrics resolver (the one thing here that still measures a face through
    the old core, when called). Roboto: the demo's own theme, justified. A
    preset no longer names a commit policy of the old stream: `mono` is what
    the conversation reads.
    """
    theme = MONO.theme(context)
    faces = theme.faces
    assert faces.regular is faces.code is Face.CODE
    assert theme.style(BlockKind.PARAGRAPH).align is Align.LEFT
    assert page.ragged(theme) is theme, "the mono theme is ragged already"
    assert ROBOTO.theme(context) is context.theme
    assert context.theme.style(BlockKind.PARAGRAPH).align is Align.JUSTIFY
    assert (MONO.mono, ROBOTO.mono) == (True, False)
    assert not hasattr(MONO, "policy")
    asked: list[str] = []

    def resolver(key: str) -> Any:
        asked.append(key)
        return context.metrics(key)

    measured = PageContext.build(metrics=resolver)
    MONO.theme(measured)
    assert len(asked) == 1 and asked[0].startswith("code@"), asked


# ----------------------------------------------------------------------
# The conversation's clock, over the stand-in views
# ----------------------------------------------------------------------


def test_it_opens_on_one_finished_exchange_and_a_post_plays_the_next(
    context: PageContext, script: tuple[Exchange, ...], stand_in: type[_View]
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    assert [m.role for m in talk.messages] == [USER, ASSISTANT]
    assert talk.done and talk.posted == 1 and talk.next is script[1]
    assert all(type(m.view) is _View and m.stream is None for m in talk.messages)
    # Every finished message is read as a stream reads: definitions off, math on.
    for message in talk.messages:
        settings = message.view.settings
        assert (settings["math"], settings["references"]) == (True, False)
        assert settings["host_for"] is message.fences and settings["theme"] is talk.theme
    assert talk.messages[0].view.settings["palette"] is page.USER_PALETTE
    assert talk.messages[1].view.settings["palette"] is page.DARK_PALETTE

    reply = talk.post("my own words")
    assert [m.role for m in talk.messages] == [USER, ASSISTANT, USER, ASSISTANT]
    assert talk.messages[2].markdown == "my own words\n"
    assert type(reply.view) is _StreamView and type(reply.stream) is MarkdownStream
    assert reply.view.tailed == 1 and reply.view.settings["host_for"] is reply.fences
    assert not talk.done and talk.fed == 0
    assert talk.advance(FRAME) == 1 and talk.fed == 1
    assert talk.advance(0.5) == 30
    ticks = _play(talk)
    assert ticks > 1 and talk.done and talk.fed == len(talk.pieces)
    assert reply.markdown == script[1].reply
    assert talk.token_count == len(talk.pieces) and talk.token_mean_ms > 0.0
    messages, live, committed = talk.counts()
    assert (messages, live) == (4, 0) and committed == len(reply.blocks) >= 3

    # Blank: the script's own prompt. And the last exchange wraps to the first.
    talk.post("   ")
    assert talk.messages[-2].markdown == script[2].prompt
    for _ in range(4):
        talk.post()
    assert talk.posted == 7 and talk.messages[-2].markdown == script[0].prompt
    # Posting over a reply still arriving finishes it first, and only the
    # message arriving is left following the end.
    assert all(m.stream is None or m.stream.closed for m in talk.messages[:-1])
    earlier = [m.view for m in talk.messages[:-1] if m.stream is not None]
    assert len(earlier) == 5 and not any(view.follow for view in earlier)
    assert talk.messages[-1].view.follow is True


def test_a_conversation_with_no_script_plays_the_built_in_exchange(
    context: PageContext, stand_in: type[_View]
) -> None:
    talk = _talk(context, ())
    assert talk.exchanges == page.parse_script(page.FALLBACK)
    talk.post()
    assert talk.next is talk.exchanges[0] and len(talk.messages) == 4


def test_code_is_coloured_and_a_fence_that_becomes_a_diff_is_not(
    context: PageContext, script: tuple[Exchange, ...], stand_in: type[_View]
) -> None:
    """
    What the conversation hands `set_colours`, over the stand-in: more than
    five spans for the python fence, every one inside the block's text; and
    for the diff fence none once its info string says `diff` -- while it was
    still `di` and `dif` it was a code block and was coloured as one, and
    what it was coloured as then is taken off again. That the view then hosts
    a diff that grows is the real view's, in the child.
    """
    talk = _talk(context, script, tokens_per_second=60.0)
    talk.post()  # the python fence
    _play(talk)
    code = talk.messages[-1]
    (fence,) = code.codes
    block = code.blocks[fence]
    assert isinstance(block, MarkdownCode) and block.language == "python"
    assert code.view.colours[fence] > 5
    spans = page.plain_spans(block.text, page.SYNTAX, block.language)
    assert all(0 <= start < end <= len(block.text) for start, end, _ in spans)

    reply = talk.post()  # the diff
    seen: list[int] = []
    while not talk.done:
        talk.advance(FRAME)
        talk.settle()
        for number in reply.codes:
            seen.append(reply.view.colours[number])
    talk.settle()
    (fence,) = reply.codes
    assert reply.fences.accepts(reply.blocks[fence])
    assert reply.view.colours[fence] == 0
    assert seen[-1] == 0 and len(seen) > 20


def test_switching_preset_keeps_the_conversation_and_lets_go_of_every_view(
    context: PageContext, script: tuple[Exchange, ...], stand_in: type[_View]
) -> None:
    """
    Mono reads the arriving reply in one ragged theme; Roboto reads its tail
    ragged and its commits in the page's theme. Switching builds every message
    again from its markdown, the unfinished reply replayed up to where it had
    got to, and closes each view there was.
    """
    talk = _talk(context, script, tokens_per_second=60.0)
    assert talk.preset is MONO
    reply = talk.post()
    assert reply.stream is not None
    assert reply.stream.theme == talk.theme and reply.stream.live_theme == talk.theme
    for _ in range(40):
        talk.advance(FRAME)
    talk.settle()
    arrived = reply.markdown
    assert 0 < talk.fed < len(talk.pieces)
    before = [m.view for m in talk.messages]

    talk.set_preset(ROBOTO)
    assert talk.theme is context.theme and len(talk.messages) == 4
    assert [m.role for m in talk.messages] == [USER, ASSISTANT, USER, ASSISTANT]
    assert all(view.closed for view in before)
    assert not any(m.view.closed for m in talk.messages)
    again = talk.messages[-1]
    assert again is not reply and again.markdown == arrived and not talk.done
    assert again.stream is not None and again.stream.theme is context.theme
    assert again.stream.live_theme == page.ragged(context.theme) != context.theme
    assert all(m.view.settings["theme"] is context.theme for m in talk.messages[:-1])
    _play(talk)
    assert again.markdown == script[1].reply
    talk.set_preset(ROBOTO)
    assert talk.messages[-1] is again, "setting the preset it already has rebuilt everything"


def test_the_readouts_say_the_replies_are_canned_and_report_counts(
    context: PageContext, script: tuple[Exchange, ...], stand_in: type[_View]
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    talk.post()
    talk.advance(0.25)
    talk.settle()
    first, second = page.readouts(talk, 3.21)
    assert "canned" in first and "No model, no network" in first
    assert "replayed through a MarkdownStream" in first
    assert f"piece 15 of {len(talk.pieces)}" in first
    assert "page draw 3.2 ms" in second and "over 15)" in second and "4 messages" in second
    messages, live, committed = talk.counts()
    assert f"blocks: {live} live, {committed} committed" in second and live >= 1
    for word in ("better", "worse", "good", "bad", "smooth", "fast", "slow", "crisp"):
        assert word not in f"{first} {second} {page.RENDERER_LINE}".lower().split()
    _play(talk)
    assert "reply complete" in page.readouts(talk, 0.0)[0]


# ----------------------------------------------------------------------
# The page with no library: one line, and nothing else
# ----------------------------------------------------------------------


def _context(name: str, *options: str, count: int | None = None) -> PageContext:
    """
    A context as `--tab NAME:options,count` gives one, without the app's parser.
    """
    return PageContext.build(request_page=name, request_options=options, request_count=count)


def test_the_page_is_listed_where_the_lead_put_it_and_reads_its_options(
    script: tuple[Exchange, ...],
) -> None:
    """
    Without the library there is no conversation; what the launch asked for
    is the page's own until there is one.
    """
    spec = page.PAGE
    assert (spec.name, spec.group, spec.order) == ("Chat", "Streaming", 220)
    plain = page.ChatPage(_context("chat"))
    assert plain.conversation is None and plain.exchanges == script
    assert (plain.preset, plain.opening) == (MONO, "")
    assert plain.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND
    played = page.ChatPage(_context("chat", "roboto", "play", count=250))
    assert (played.preset, played.opening, played.tokens_per_second) == (ROBOTO, "play", 250.0)
    assert page.ChatPage(_context("chat", "all", "play")).opening == "all"
    other = page.ChatPage(_context("document", "roboto", "all", count=9))
    assert (other.preset, other.opening) == (MONO, "")
    assert other.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND


def test_the_page_does_not_raise_for_a_missing_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = page.ChatPage(_context("chat", "play"))
    assert made.exchanges == page.parse_script(page.FALLBACK) and len(made.exchanges) == 1


def test_what_the_launch_asked_played_is_played_as_the_conversation_opens(
    script: tuple[Exchange, ...], stand_in: type[_View]
) -> None:
    """
    `open`, over the stand-in views: `play` posts the next canned turn, `all`
    posts every turn and finishes each, and a second call makes nothing.
    """
    plain = page.ChatPage(_context("chat"))
    talk = plain.open()
    assert plain.conversation is talk and plain.open() is talk
    assert (talk.preset, len(talk.messages), talk.done) == (MONO, 2, True)

    played = page.ChatPage(_context("chat", "roboto", "play", count=250)).open()
    assert played.preset is ROBOTO and played.tokens_per_second == 250.0
    assert len(played.messages) == 4 and not played.done

    everything = page.ChatPage(_context("chat", "all")).open()
    assert len(everything.messages) == 12 and everything.done
    assert [m.markdown for m in everything.messages[1::2]] == [e.reply for e in script]


def _frames(draw: Any, count: int, seconds: float = FRAME) -> Any:
    """
    `count` real frames of `draw` in a window that fills the display. Returns ImGui.
    """
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1300.0, 800.0)
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    for _ in range(count):
        io.delta_time = seconds
        imgui.new_frame()
        try:
            imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
            imgui.set_next_window_size(imgui.ImVec2(1300.0, 800.0))
            imgui.begin("##imscribe-chat-page-test", None, imgui.WindowFlags_.no_title_bar.value)
            try:
                draw()
            finally:
                imgui.end()
        finally:
            imgui.render()
    return imgui


def test_without_the_library_the_page_draws_one_line_saying_why_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Real ImGui frames in the pytest process, where `ready()` is false. Each
    frame is one call of `say_why_not` with `why_not()`'s sentence and no call
    of anything else the page draws with; no conversation is made, and `send`
    does nothing and keeps what was typed. Then the same frames with nothing
    patched, so the line itself reaches ImGui.
    """
    assert not typesetter.ready()
    made = page.ChatPage(_context("chat", "all", count=400))
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the page drew, or built, more than the one line")

    monkeypatch.setattr(page, "caption", never)
    monkeypatch.setattr(page, "Conversation", never)
    monkeypatch.setattr(page.ChatPage, "_header", never)
    monkeypatch.setattr(page.ChatPage, "_input", never)
    _frames(made.draw, 4)
    assert said == [why_not()] * 4 and said[0]
    assert made.frames == 4 and made.failed == "" and made.reason == why_not()
    assert made.renderer == "none" and made.conversation is None
    made.typed = "hello"
    made.send()
    assert made.typed == "hello" and made.conversation is None and made.failed == ""
    (report,) = made.report()
    assert report.startswith("frames=4 messages=0 posted=0 fed=0 ")
    assert report.endswith(" preset=mono renderer=none") and "glyphs" not in report
    with pytest.raises(LookupError, match="no conversation"):
        made.copy_markdown(0)

    monkeypatch.undo()
    imgui = _frames(made.draw, 2)
    assert made.frames == 6 and imgui.get_current_context() is not None


@pytest.mark.parametrize("how", ["raised in a frame", "not ready any more", "raised in a post"])
def test_a_page_that_gives_up_closes_its_views_and_keeps_its_conversation(
    how: str, monkeypatch: pytest.MonkeyPatch, stand_in: type[_View]
) -> None:
    """
    B3 (T5-R #3). Until T5-FINAL only the Diff page closed its views when it
    gave up; this page kept every view, and with it the document each holds
    in the library, for as long as the page object lived. Both ways of giving
    up are held here: `TypesetUnavailable` out of a frame, and a library that
    stopped being ready between frames (another page's view switched it off).
    The page's own state is kept either way: it is what `report()` prints.
    """
    ready = {"reason": ""}
    monkeypatch.setattr(page, "why_not", lambda: ready["reason"])
    monkeypatch.setattr(page, "say_why_not", lambda reason: None)
    made = page.ChatPage(_context("chat", "play"))
    talk = made.open()
    views = [message.view for message in talk.messages]
    assert len(views) == 4 and not any(view.closed for view in views)

    if how == "raised in a frame":

        def unavailable(self: page.ChatPage, imgui: Any, conversation: Any, index: int) -> None:
            raise page.TypesetUnavailable("switched off under the frame")

        monkeypatch.setattr(page.ChatPage, "_message", unavailable)
        _frames(made.draw, 1)
    elif how == "raised in a post":

        def refusing(self: Conversation, text: str = "") -> Any:
            raise page.TypesetUnavailable("switched off under the post")

        monkeypatch.setattr(Conversation, "post", refusing)
        made.send()
    else:
        ready["reason"] = "switched off by another page"
        _frames(made.draw, 1)

    assert made.renderer == "none"
    assert [view.closed for view in views] == [True] * 4
    assert made.conversation is talk and [m.view for m in talk.messages] == views
    assert made.report()[0].startswith("frames=")


def test_a_typeset_unavailable_out_of_a_frame_or_a_post_stays_in_the_page(
    monkeypatch: pytest.MonkeyPatch, stand_in: type[_View]
) -> None:
    """
    The page's two handlers, with the library's readiness and the views stood
    in for. `TypesetUnavailable` from a message's draw: the transcript's child
    window is ended (ImGui accepts the frame), the reason is kept, and the
    frames after it are the one line. From a post: `send` returns, the reason
    is kept and what was typed stays in the box. Any other exception is a bug
    and is not caught.
    """
    monkeypatch.setattr(page, "why_not", lambda: "")
    said: list[str] = []
    monkeypatch.setattr(page, "say_why_not", said.append)
    made = page.ChatPage(_context("chat", "play"))
    tried: list[int] = []

    def unavailable(self: page.ChatPage, imgui: Any, conversation: Any, index: int) -> None:
        tried.append(index)
        raise page.TypesetUnavailable("switched off under the frame")

    monkeypatch.setattr(page.ChatPage, "_message", unavailable)
    _frames(made.draw, 3)
    assert tried == [0], "messages were tried after the library had failed"
    assert made.failed == "switched off under the frame" and said == [made.failed] * 2
    assert made.frames == 3 and made.renderer == "none"
    assert made.conversation is not None and len(made.conversation.messages) == 4

    posting = page.ChatPage(_context("chat", "play"))
    talk = posting.open()

    def refusing(self: Conversation, text: str = "") -> Any:
        raise page.TypesetUnavailable("switched off under the post")

    monkeypatch.setattr(Conversation, "post", refusing)
    posting.typed = "again"
    posting.send()
    assert posting.failed == "switched off under the post" and posting.typed == "again"
    assert posting.renderer == "none" and len(talk.messages) == 4
    posting.send()  # and nothing more is asked of the conversation once it has failed

    def broken(self: page.ChatPage, imgui: Any, conversation: Any, index: int) -> None:
        raise ZeroDivisionError("a bug")

    other = page.ChatPage(_context("chat"))
    monkeypatch.setattr(page.ChatPage, "_message", broken)
    imgui = pytest.importorskip("imgui_bundle").imgui
    imgui.get_io().delta_time = FRAME
    imgui.new_frame()
    try:
        imgui.begin("##imscribe-chat-page-bug", None, 0)
        try:
            with pytest.raises(ZeroDivisionError):
                other.draw()
        finally:
            imgui.end()
    finally:
        imgui.render()
    assert other.failed == ""


# ----------------------------------------------------------------------
# What the module imports, at import and ever
# ----------------------------------------------------------------------


def test_the_page_imports_nothing_of_the_old_core_or_the_old_views_even_lazily() -> None:
    """
    Read from the source, so an import inside a function counts. The one way
    this page still reaches the old core is not an import of its own: the mono
    preset's `Theme.at_pixel_height(metrics=context.metrics)`
    (`test_the_presets_are_what_they_say` holds that it is asked once).
    """
    from test_page_stream import OLD_MODULES, imports_of

    found = imports_of(_ROOT / "imscribe" / "ui" / "pages" / "chat.py")
    assert "imscribe.ui.typeset_hosts" in found and "imscribe.typeset_markdown" in found
    for name in found:
        for old in OLD_MODULES:
            assert name != old and not name.startswith(old + "."), name
    assert "imscribe.ui.pages._syntax.colour_spans" not in found


_CLOSURE = r"""
import json, sys
import imscribe.ui.pages.chat
print("REPORT " + json.dumps(sorted(name for name in sys.modules if name.startswith("imscribe"))))
"""


def test_importing_the_page_loads_none_of_the_old_core() -> None:
    """
    `imscribe.ui.typeset_diff_view` is imported when a fenced diff is first
    met. `imscribe.ui.pages._syntax` is imported with the page and loads
    nothing of the core itself.
    """
    from test_typeset_closure import OLD_CORE, THEME

    env = {name: value for name, value in os.environ.items() if name not in _VARIABLES}
    done = subprocess.run(
        [sys.executable, "-B", "-c", _CLOSURE],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    loaded = set(json.loads(done.stdout.split("REPORT ", 1)[1]))
    assert "imscribe.ui.pages.chat" in loaded and "imscribe.ui.typeset_hosts" in loaded
    assert loaded & OLD_CORE == THEME, sorted(loaded & OLD_CORE)
    assert "imscribe.ui.pages._syntax" in loaded
    for name in (
        "imscribe.stream",
        "imscribe.markdown",
        "imscribe.mathtext",
        "imscribe.style",
        "imscribe.spans",
        "imscribe.ui.typeset_diff_view",
    ):
        assert name not in loaded, name


# ----------------------------------------------------------------------
# A real window
# ----------------------------------------------------------------------

WINDOW_RATE = 400
"""Pieces a second of the page's clock in the windowed run (`--tab chat:play,400`)."""

WINDOW_FRAME = 1.0 / 60.0
"""
What the windowed run tells the page every frame took, whatever it really took.

The page feeds `delta_time * rate` pieces a frame. Left to the real clock, how
many edits a reply spans is a fact about the machine (a loaded machine whose
frames ran long fed a whole reply in few). With the frame's length stated, a
frame is worth `WINDOW_RATE * WINDOW_FRAME` pieces -- six or seven -- on any
machine, and a slow one only takes longer to get through them.
"""

WINDOWED = """
import sys
import time

from imgui_bundle import hello_imgui, imgui

from imscribe import typesetter
from imscribe.ui import app as imscribe_app

WANT_LIBRARY = sys.argv[1] == "with"
state = {"frames": 0, "turn": 0, "streaming": 0, "spent": 0.0}
real_gui = imscribe_app.App.gui


def last_line(made):
    # After the body: what was true when the last frame had been drawn.
    print(
        "child imported=%d module=%d ready=%d page_frames=%d conversation=%d"
        % (
            "imtypeset" in sys.modules,
            WANT_LIBRARY and typesetter.module() is not None,
            typesetter.ready(),
            made.frames,
            made.conversation is not None,
        )
    )
    print("why " + made.reason)
    hello_imgui.get_runner_params().app_shall_exit = True


def watched_gui(self):
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    # The page reads how long the frame took from here; the test says why.
    imgui.get_io().delta_time = FRAME
    began = time.perf_counter()
    real_gui(self)
    spent = time.perf_counter() - began
    state["frames"] += 1
    made = self.page("chat")
    if not WANT_LIBRARY:
        if state["frames"] >= 8:
            print(made.report()[0])
            last_line(made)
        return
    if state["frames"] == 2:
        # In the child, so that this cannot pass with nothing drawn.
        assert typesetter.module() is not None, "not in use: " + typesetter.reason()
        assert typesetter.ready(), "imtypeset has no fonts: " + typesetter.trouble()
    talk = made.conversation
    if not talk.done:
        state["streaming"] += 1
        state["spent"] += spent
    if talk.done and state["frames"] > 3:
        print(made.report()[0])
        print(
            "cost streaming_frames=%d gui_ms=%.3f"
            % (state["streaming"], 1000.0 * state["spent"] / max(1, state["streaming"]))
        )
        state["turn"] += 1
        if state["turn"] >= 3 or state["frames"] >= 20000:
            last_line(made)
        else:
            made.send()


imscribe_app.App.gui = watched_gui
imscribe_app.run(tab="chat:play,RATE")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def _windowed(
    window: Window, how: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[dict[str, str]], dict[str, str], str, str]:
    """
    The window run with or without the library.

    Each report line's fields, the child's last line, the page's reason, stdout.
    """
    script = window.out / "chat_page.py"
    source = WINDOWED.replace("FRAME", repr(WINDOW_FRAME)).replace("RATE", str(WINDOW_RATE))
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    with monkeypatch.context() as patch:
        if how == "without":
            for name in _VARIABLES:
                patch.delenv(name, raising=False)
        done = window.run([str(script), how])
    assert done.returncode == 0, f"{how}, on {window.where}:\n{done.stdout}\n{done.stderr}"
    print(how, window.where, done.stdout)  # shown by pytest -s, and when the test fails
    printed = done.stdout.splitlines()
    lines = [_fields(line) for line in printed if line.startswith("frames=")]
    child = [line for line in printed if line.startswith("child ")]
    why = [line[4:] for line in printed if line.startswith("why ")]
    assert len(child) == 1 and len(why) == 1, done.stdout
    return lines, _fields(child[0]), why[0], done.stdout


def test_without_the_library_the_page_says_why_not_in_a_real_window(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The real app on `--tab chat:play,400` with the library's variables removed
    for the child: eight frames, in each of which the page drew (the app did
    not replace it by its traceback page), no conversation was made, nothing
    of imtypeset was imported, and the page's reason is the sentence about
    the variable.
    """
    lines, child, why, stdout = _windowed(window, "without", monkeypatch)
    assert child["imported"] == "0" and child["ready"] == "0" and child["conversation"] == "0"
    (line,) = lines
    assert line["renderer"] == "none" and line["messages"] == "0" and line["preset"] == "mono"
    assert int(child["page_frames"]) >= 8 and line["frames"] == child["page_frames"], stdout
    assert typesetter.LIBRARY_VARIABLE in why, stdout


def test_with_the_library_three_replies_stream_through_imtypeset_in_a_real_window(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    `--tab chat:play,400` with the library: the code reply, the diff reply and
    the list-and-table reply, each until it is complete, on a clock that calls
    every frame a sixtieth of a second (`WINDOW_FRAME`). The child asserts
    `typesetter.module()` and `ready()` itself on its second frame and reports
    both again after its last, and each report says the typeset path drew.

    Counts. **That a reply streams across many edits** is arithmetic and not
    timing: a frame is worth `400 / 60` pieces, so a reply of `pieces` pieces
    cannot arrive in fewer than `ceil(pieces * 60 / 400)` frames, and the view
    makes at most one edit in each frame that brought something, so the edits
    are at most that many and two over, and "many" is more than half of them:
    an edit is skipped on a frame whose pieces changed no block's description
    (white space, or a fence's unfinished closing line). Every reply is over
    a hundred pieces. Vertices drawn, every message set as asked, the diff
    reply drawn by a hosted diff that read all fifteen of its lines.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    lines, child, why, stdout = _windowed(window, "with", monkeypatch)
    assert child["imported"] == "1" and child["module"] == "1" and child["ready"] == "1", stdout
    assert why == "" and child["conversation"] == "1"
    assert [line["messages"] for line in lines] == ["4", "6", "8"]
    for line in lines:
        assert line["renderer"] == "typeset" and "glyphs" not in line
        assert line["done"] == "1" and line["fed"] == line["pieces"] and line["live"] == "0"
        pieces = int(line["pieces"])
        assert pieces > 100, stdout
        frames_needed = math.ceil(pieces / (WINDOW_RATE * WINDOW_FRAME) - 1e-6)
        assert frames_needed > 15
        assert frames_needed // 2 < int(line["edits"]) <= frames_needed + 2, stdout
        assert int(line["vertices"]) > 1000 and line["not_whole"] == "0"
        assert line["tokens_timed"] == line["pieces"] and line["preset"] == "mono"
    assert [line["diffs"] for line in lines] == ["0", "1", "1"]
    assert [line["diff_lines"] for line in lines] == ["0", "15", "15"]
    assert lines[2]["codes"] == "5"


# ----------------------------------------------------------------------
# Through imtypeset: real frames, no window, in a child that has the library
# ----------------------------------------------------------------------

_HEADLESS = r"""
import json, sys
from imgui_bundle import imgui
from imscribe import typesetter
from imscribe.theme import Align, Theme
from imscribe.ui.pages import PageContext, demo_text
from imscribe.ui.pages import chat as page

OLD = json.loads(sys.argv[1])
SIZE = (1300.0, 800.0)
FRAME = 1.0 / 60.0
ts = typesetter.module()
report = {"module": ts is not None, "reason": typesetter.reason()}
if ts is None:
    print("REPORT " + json.dumps(report))
    raise SystemExit(0)
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(*SIZE)
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["load_fonts"] = typesetter.load_fonts()
report["ready"] = typesetter.ready()

def frame(app, seconds=FRAME, **events):
    io.delta_time = seconds
    if "mouse" in events:
        io.add_mouse_pos_event(*events["mouse"])
    if "wheel" in events:
        io.add_mouse_wheel_event(0.0, events["wheel"])
    for key, down in events.get("keys", ()):
        io.add_key_event(key, down)
    for character in events.get("text", ""):
        io.add_input_character(ord(character))
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##imscribe-chat-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            app.gui()
        finally:
            imgui.end()
    finally:
        imgui.render()

def opened(spec="chat"):
    from imscribe.ui.app import App
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    made = app.page("chat")
    before = made.conversation is None
    frame(app)
    frame(app)
    opened.unmade.append(before)
    return app, made
opened.unmade = []

def kinds(message):
    return [type(block).__name__ for block in message.blocks]

def shape(message):
    return {"view": type(message.view).__name__, "stream": type(message.stream).__name__,
            "fences": type(message.fences).__name__, "role": message.role}

script = page.parse_script(demo_text("chat/script.md"))
context = PageContext.build()

# 1. The conversation with no frame at all: a clock advanced by hand.
talk = page.Conversation(context, script, tokens_per_second=60.0)
opening = [shape(m) for m in talk.messages]
reply = talk.post("my own words")
arriving = shape(reply)
ticks = 0
while not talk.done:
    talk.advance(FRAME)
    talk.settle()
    ticks += 1
report["conversation"] = {
    "opening": opening, "arriving": arriving, "ticks": ticks, "posted": talk.posted,
    "asked": talk.messages[2].markdown, "whole": reply.markdown == script[1].reply,
    "timed": [talk.token_count, len(talk.pieces), talk.token_mean_ms > 0.0],
    "counts": list(talk.counts()), "readouts": list(page.readouts(talk, 3.21)),
}

# 2. Every reply streamed is the document the same text gives whole.
same = []
for number in range(1, len(script)):
    talk = page.Conversation(context, script, tokens_per_second=600.0)
    talk.posted = number
    streamed = talk.post()
    while not talk.done:
        talk.advance(FRAME)
        talk.settle()
    whole = talk._finished(page.ASSISTANT, script[number].reply)
    same.append({
        "blocks": len(streamed.blocks), "kinds": kinds(streamed) == kinds(whole),
        "texts": [a == b for a, b in zip(streamed.view.texts, whole.view.texts)],
        "hosts": list(whole.view.hosts),
        "values": streamed.blocks == whole.blocks,
        "codes": [list(streamed.codes), list(whole.codes)],
        "code": [streamed.block_code(b) == whole.block_code(b) for b in streamed.codes],
        "links": len(streamed.view.links),
    })
report["same"] = same

# 3. Reference definitions are text, finished and arriving.
text = "See [the paper][1] for why.\n\n[1]: https://example.org/paper\n"
talk = page.Conversation(context, (page.Exchange("q\n", text), page.Exchange("again\n", text)))
talk.post()
talk.finish()
talk.settle()
both = (talk.messages[1], talk.messages[3])
report["references"] = [[len(m.blocks), len(m.view.links)] for m in both]

# 4. The code reply is coloured; the diff reply is a hosted diff that grows.
from imscribe.ui.typeset_view import TypesetView
coloured = {}
real = TypesetView.set_colours
def recording(view, block, spans):
    spans = list(spans)
    coloured[(id(view), block)] = len(spans)
    real(view, block, spans)
TypesetView.set_colours = recording
talk = page.Conversation(context, script, tokens_per_second=60.0)
code = talk.post()
while not talk.done:
    talk.advance(FRAME)
    talk.settle()
(fence,) = code.codes
report["code"] = {"diff": code.diff(fence) is None, "spans": coloured[(id(code.view), fence)],
                  "body": code.block_code(fence)[:24], "fenced": "```" in code.block_code(fence),
                  "inside": all(0 <= s < e <= len(code.view.texts[fence])
                                for s, e, _ in code.view._colours.get(fence, ()))}
reply = talk.post()
fed = []
while not talk.done:
    talk.advance(FRAME)
    talk.settle()
    fed.append(reply.fences.fed_lines)
(fence,) = reply.codes
hosted = reply.diff(fence)
report["diff"] = {
    "hosted": type(hosted).__name__, "spans": coloured[(id(reply.view), fence)],
    "steps": sorted({b - a for a, b in zip(fed, fed[1:])}), "distinct": len(set(fed)),
    "fed": fed[-1], "restarts": reply.fences.restarts,
    "changed": [hosted.view.diff.added, hosted.view.diff.removed],
    "copy": reply.block_code(fence) == hosted.text, "head": hosted.text[:16],
    "tail": hosted.text[-13:], "host": fence in list(reply.view.hosts),
}
TypesetView.set_colours = real

# 5. The presets: the mono stream has one theme, the other two. With a diff arriving, too.
talk = page.Conversation(context, script, tokens_per_second=60.0)
reply = talk.post()
for _ in range(40):
    talk.advance(FRAME)
talk.settle()
arrived = reply.markdown
mono = [block.style.align.name for block in reply.stream.blocks if hasattr(block, "runs")]
before = [m.view for m in talk.messages]
talk.set_preset(page.ROBOTO)
again = talk.messages[-1]
talk.settle()
report["preset"] = {
    "mono": sorted(set(mono)), "same_theme": talk.theme is context.theme,
    "roles": [m.role for m in talk.messages], "kept": again.markdown == arrived,
    "fresh": again is not reply, "done": talk.done,
    "old_closed": [view.native_document is None for view in before],
    "live": sorted({b.style.align.name for b in again.stream.live if hasattr(b, "runs")}),
    "finished": Align.JUSTIFY.name in {
        b.style.align.name for b in talk.messages[1].blocks if hasattr(b, "runs")},
}
while not talk.done:
    talk.advance(FRAME)
    talk.settle()
report["preset"]["committed"] = Align.JUSTIFY.name in {
    b.style.align.name for b in again.stream.committed if hasattr(b, "runs")}
report["preset"]["whole"] = again.markdown == script[1].reply
# The preset changed while the diff reply is part way through its fence: the reply is
# replayed into a new stream and its diff is hosted again and read to its end.
talk = page.Conversation(context, script, tokens_per_second=60.0)
talk.posted = 2
reply = talk.post()
while reply.fences.fed_lines < 6 and not talk.done:
    talk.advance(FRAME)
    talk.settle()
part_way = [reply.fences.fed_lines, talk.done]
talk.set_preset(page.ROBOTO)
again = talk.messages[-1]
while not talk.done:
    talk.advance(FRAME)
    talk.settle()
talk.settle()
(fence,) = again.codes
report["preset_diff"] = {
    "part_way": part_way, "fresh": again is not reply, "fed": again.fences.fed_lines,
    "hosted": type(again.diff(fence)).__name__, "whole": again.markdown == script[2].reply,
    "copy": again.block_code(fence) == again.diff(fence).text,
}
report["old_before_app"] = sorted(name for name in sys.modules if name in OLD)
report["imscribe_before_app"] = sorted(n for n in sys.modules if n.startswith("imscribe"))

# 6. The page in frames: a turn typed into the box and entered, the reply followed to its
# end while the finished messages are left alone; the wheel lets go.
app, made = opened("chat:120")
talk = made.conversation
made._refocus = True
frame(app)
frame(app)
frame(app, text="hello there")
typed = [made.typed, len(talk.messages)]
frame(app, keys=((imgui.Key.enter, True),))
frame(app, keys=((imgui.Key.enter, False),))
reply = talk.messages[-1]
finished_before = [dict(m.view.edits) for m in talk.messages[:-1]]
# B5: `edits` counts what was HANDED to the library, and a view that laid its
# document out again on every frame would hand it nothing. The library's own
# counter (`DocumentStats.BlocksLaidOut`, which only goes up) is what moves then.
def laid_out():
    return [m.view.stats.blocks_laid_out for m in talk.messages[:-1]]
laid_before = laid_out()
frames = 0
while not talk.done and frames < 2000:
    frame(app)
    frames += 1
frame(app)
laid_after = laid_out()
report["page"] = {
    "renderer": made.renderer, "reason": made.reason, "typed": typed,
    "roles": [m.role for m in talk.messages], "asked": talk.messages[2].markdown,
    "box": made.typed, "shapes": [shape(m) for m in talk.messages],
    "frames": frames, "edits": dict(reply.view.edits), "following": reply.view.following,
    "finished_edits": [finished_before, [dict(m.view.edits) for m in talk.messages[:-1]]],
    "vertices": [m.vertices for m in talk.messages], "whole": [m.whole for m in talk.messages],
    "draw_ms": made.draw_ms > 0.0, "timed": talk.token_count == len(talk.pieces),
    "report": made.report()[0],
    "bar": [m.view.height > 0.0 and m.view.origin is not None for m in talk.messages],
    "finished_laid_out": [laid_before, laid_after],
}
# The box kept the keyboard: more typing goes into it.
frame(app, text="x")
report["page"]["kept_keyboard"] = made.typed
# And the counter is one that WOULD have moved: the same page in a narrower
# window is every message in view laid out again.
wide, SIZE = SIZE, (SIZE[0] - 300.0, SIZE[1])
frame(app)
frame(app)
report["page"]["laid_out_narrower"] = [laid_out(), [m.vertices > 0 for m in talk.messages[:-1]]]
SIZE = wide
app, made = opened("chat:all")
talk = made.conversation
report["all"] = [len(talk.messages), talk.done]
talk.tokens_per_second = 60.0
made.send()
reply = talk.messages[-1]
for _ in range(6):
    frame(app)
followed = reply.view.following
frame(app, mouse=(700.0, 400.0))
frame(app, wheel=5.0)
for _ in range(4):
    frame(app)
report["wheel"] = [followed, reply.view.following, talk.done,
                   all(not m.view.follow for m in talk.messages[:-1] if m.stream is not None)]

# 7. The buttons, and one selection across messages and their diffs.
app, made = opened("chat:all")
talk = made.conversation
copied = made.copy_markdown(1)
buttons = {"markdown": copied == talk.exchanges[0].reply == imgui.get_clipboard_text()}
code = next(i for i, m in enumerate(talk.messages) if m.codes and m.diff(m.codes[0]) is None)
buttons["code"] = made.copy_block(code, talk.messages[code].codes[0])[:10]
diff = next(i for i, m in enumerate(talk.messages) if m.codes and m.diff(m.codes[0]))
block = talk.messages[diff].codes[0]
buttons["diff"] = made.copy_block(diff, block)[:16]
buttons["clipboard"] = imgui.get_clipboard_text()[:16]
buttons["copied"] = made.copied
flipped = [made.toggle_diff(diff, block).name]
frame(app)
frame(app)
flipped.append(made.toggle_diff(diff, block).name)
flipped.append(made.toggle_diff(code, talk.messages[code].codes[0]))
buttons["flipped"] = flipped
listed = next(
    i for i, m in enumerate(talk.messages) if len(m.codes) == 3 and m.role == page.ASSISTANT
)
buttons["listed"] = made.copy_block(listed, talk.messages[listed].codes[0])
report["buttons"] = buttons
# Where the buttons are put: a fenced block's top, asked of the library.
message = talk.messages[code]
tops = made._block_tops(message, message.view.origin, message.view.height, (-1.0e9, 1.0e9))
report["tops"] = [[b, t == message.view.block_rect(b)[1]] for b, t in tops]
report["tops_out_of_view"] = made._block_tops(
    message, message.view.origin, message.view.height, (1.0e8, 1.0e9))
first, second = talk.messages[1].view, talk.messages[3].view
first.select(((0, 0), (0, 12)))
frame(app)
one = [first.owns_selection, first.selected_text()]
second.select(((0, 3), (0, 9)))
frame(app)
two = [second.owns_selection, first.selection]
hosted = talk.messages[diff].diff(block)
hosted.view.select_all()
for _ in range(3):
    frame(app)
report["selection"] = {"one": one, "two": two,
                       "three": [hosted.view.owns_selection, second.owns_selection]}
# A NUL in a message does not cut what the buttons put on the clipboard.
typed = "key = 'ab\0cd'\nnext line\n"
talk.post(typed)
talk.finish()
asked = len(talk.messages) - 2
copied = made.copy_markdown(asked)
report["nul"] = [talk.messages[asked].role, talk.messages[asked].markdown == typed,
                 copied == typed, imgui.get_clipboard_text()]

# 8. Open items, observed and not asserted on: a selection in the block being written.
app, made = opened("chat")
talk = made.conversation
talk.tokens_per_second = 120.0
talk.posted = 5
made.send()
reply = talk.messages[-1]
for _ in range(12):
    frame(app)
last = len(reply.view.blocks) - 1
taken = min(5, len(reply.view.texts[last]))
reply.view.select(((last, 0), (last, taken)))
held = []
for _ in range(40):
    frame(app)
    held.append(reply.view.selection is not None)
report["observed"] = {"selection_frames_held": sum(held), "of": len(held),
                      "blocks_then": last + 1, "blocks_now": len(reply.view.blocks),
                      "on_link": reply.view.on_link is not None}
report["unmade"] = opened.unmade

# After the body that needs the library, and before the sections that take it away.
report["after"] = {"module": typesetter.module() is not None, "ready": typesetter.ready(),
                   "reason": typesetter.reason(), "failed": made.failed}

# 9. A draw that raises with the library still ready: the page keeps the sentence, finishes
# the frame without an error, and is the one line from the next frame on.
from imscribe.ui.typeset_view import TypesetUnavailable, TypesetView
real_draw = TypesetView.draw
def failing(self, **kwargs):
    raise TypesetUnavailable("raised by the test")
app, made = opened("chat:all")
talk = made.conversation
count = len(talk.messages)
drawn = made.frames
TypesetView.draw = failing
frame(app)
TypesetView.draw = real_draw
at_once = {"failed": made.failed, "reason": made.reason, "renderer": made.renderer,
           "frames": made.frames - drawn}
shown = []
real_say = page.say_why_not
def saying(reason):
    shown.append(reason)
    real_say(reason)
page.say_why_not = saying
for _ in range(4):
    frame(app)
page.say_why_not = real_say
report["middraw"] = {"ready": typesetter.ready(), "at_once": at_once, "shown": shown,
                     "count": [count, len(talk.messages)], "report": made.report()[0],
                     "current": type(app.page("chat")).__name__}

# A post under which the library fails: nothing is posted, the page keeps the sentence
# and what was typed, and is the one line from the next frame on.
from imscribe.ui.typeset_stream_view import TypesetStreamView
app, made = opened("chat:play")
talk = made.conversation
for _ in range(5):
    frame(app)
real_sync = TypesetStreamView.sync
def failing_sync(self):
    raise TypesetUnavailable("raised by the test")
TypesetStreamView.sync = failing_sync
made.typed = "again"
made.send()
TypesetStreamView.sync = real_sync
shown = []
page.say_why_not = saying
frame(app)
page.say_why_not = real_say
report["send"] = {"failed": made.failed, "renderer": made.renderer, "posted": talk.posted,
                  "roles": [m.role for m in talk.messages], "typed": made.typed,
                  "shown": shown, "ready": typesetter.ready()}

# 10. Last, because it is for the rest of the process: the library switched off mid-reply.
app, made = opened("chat")
talk = made.conversation
talk.tokens_per_second = 120.0
made.send()
for _ in range(20):
    frame(app)
before = {"renderer": made.renderer, "fed": talk.fed, "frames": made.frames}
typesetter.disable("switched off by the test")
frame(app)
after = {"renderer": made.renderer, "fed": talk.fed, "reason": made.reason,
         "failed": made.failed}
made.typed = "more"
made.send()
for _ in range(5):
    frame(app)
report["off"] = {"before": before, "after": after, "fed": talk.fed, "typed": made.typed,
                 "messages": len(talk.messages), "frames": made.frames,
                 "report": made.report()[0], "ready": typesetter.ready()}
print("REPORT " + json.dumps(report))
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    """
    `_HEADLESS` run once in a child that has the library; skipped without the variable.

    The child says whether the library was in use and ready before its body
    and again after the part of it that draws, and that no page of that part
    had failed.
    """
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(_SKIP)
    from test_typeset_closure import OLD_CORE

    done = subprocess.run(
        [sys.executable, "-B", "-c", _HEADLESS, json.dumps(sorted(OLD_CORE))],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = [line for line in done.stdout.splitlines() if line.startswith("REPORT ")]
    assert len(lines) == 1, done.stdout + done.stderr
    report: dict[str, Any] = json.loads(lines[0][len("REPORT ") :])
    assert report["module"], f"imtypeset is not in use in the child: {report['reason']}"
    assert report["load_fonts"] and report["ready"], report
    after = report["after"]
    assert after["module"] and after["ready"], f"the library was lost under the body: {after}"
    assert after["failed"] == "", after
    print("observed (not asserted):", json.dumps(report["observed"]))
    return report


_FINISHED = {"view": "TypesetView", "stream": "NoneType", "fences": "TypesetDiffFences"}
_ARRIVING = {
    "view": "TypesetStreamView",
    "stream": "MarkdownStream",
    "fences": "TypesetDiffFences",
}


def test_it_opens_on_one_exchange_and_a_post_plays_the_next(
    typeset: dict[str, Any], script: tuple[Exchange, ...]
) -> None:
    told = typeset["conversation"]
    assert told["opening"] == [
        {**_FINISHED, "role": USER},
        {**_FINISHED, "role": ASSISTANT},
    ]
    assert told["arriving"] == {**_ARRIVING, "role": ASSISTANT}
    assert told["ticks"] > 1 and told["posted"] == 2 and told["asked"] == "my own words\n"
    assert told["whole"] is True
    pieces = len(page.tokens(script[1].reply))
    assert told["timed"] == [pieces, pieces, True]
    messages, live, committed = told["counts"]
    assert (messages, live) == (4, 0) and committed >= 3
    first, second = told["readouts"]
    assert "replayed through a MarkdownStream" in first and "reply complete" in first
    assert "page draw 3.2 ms" in second and f"over {pieces})" in second


def test_a_streamed_reply_is_the_document_the_text_gives_whole(
    typeset: dict[str, Any], script: tuple[Exchange, ...]
) -> None:
    """
    Every exchange of the script, hosted diffs and formulas included: the same
    blocks by value, the same described texts, the same fenced blocks with the
    same source, and no link made of a reference definition. Arriving and
    finished messages are read alike, so a change of preset -- which rebuilds
    a finished reply from its markdown -- changes nothing about it.
    """
    same = typeset["same"]
    assert len(same) == len(script) - 1
    for number, told in enumerate(same, start=1):
        assert told["blocks"] > 0 and told["kinds"] and told["values"], number
        assert told["codes"][0] == told["codes"][1] and all(told["code"]), number
        # The described texts are equal too, block for block, a hosted diff's
        # included: the text the library holds for a diff at the end of a
        # streamed reply was one line short until 2026-10-11, when the view
        # began asking again about a hosted block whose source had moved
        # (`tests/test_typeset_hosts.py`).
        assert len(told["texts"]) == told["blocks"]
        assert all(told["texts"]), number
    assert sum(len(told["codes"][0]) for told in same) >= 5
    assert sum(len(told["hosts"]) for told in same) == 1
    assert typeset["references"] == [[2, 0], [2, 0]]


def test_code_is_coloured_and_the_diff_is_a_hosted_view_that_grows(
    typeset: dict[str, Any],
) -> None:
    code, diff = typeset["code"], typeset["diff"]
    assert code["diff"] is True and code["spans"] > 5 and code["inside"] is True
    assert code["body"].startswith("import re\n\ndef tokens(") and code["fenced"] is False
    # While its info string was still `di` and `dif` the fence was a code
    # block and was coloured as one; as a diff it has no spans left.
    assert diff["hosted"] == "HostedDiff" and diff["spans"] == 0 and diff["host"] is True
    # A line or so at a time over many ticks, never the lot at once: one piece
    # a tick, and a piece carries the white space before it, so a blank
    # context line and the line after it can arrive together.
    assert set(diff["steps"]) <= {0, 1, 2} and diff["distinct"] >= 12
    assert diff["fed"] == 15 and diff["restarts"] == 0
    assert diff["changed"] == [4, 3] and diff["copy"] is True
    assert diff["head"] == "--- a/replay.py\n" and diff["tail"] == '== "a  bc\\n"\n'


def test_the_presets_are_one_theme_or_two_and_a_switch_lets_go_of_every_view(
    typeset: dict[str, Any],
) -> None:
    """
    Mono: every block ragged, arriving or not. Roboto: the tail ragged, and a
    block justified once it has committed, as a finished message is. Every
    view the switch replaced gave its document back. And with the diff reply
    part way through its fence when the preset changes, the new stream's diff
    is hosted and read to its fifteenth line.
    """
    preset = typeset["preset"]
    assert preset["mono"] == ["LEFT"] and preset["same_theme"] is True
    assert preset["roles"] == [USER, ASSISTANT, USER, ASSISTANT]
    assert preset["kept"] and preset["fresh"] and preset["done"] is False
    assert preset["old_closed"] == [True] * 4, "a view that was replaced kept its document"
    assert "JUSTIFY" not in preset["live"] and preset["finished"] is True
    assert preset["committed"] is True and preset["whole"] is True
    arriving = typeset["preset_diff"]
    assert arriving["part_way"][0] >= 6 and arriving["part_way"][1] is False
    assert arriving["fresh"] is True and arriving["hosted"] == "HostedDiff"
    assert arriving["fed"] == 15 and arriving["whole"] is True and arriving["copy"] is True


def test_a_conversation_loads_no_old_view_and_no_old_stream(typeset: dict[str, Any]) -> None:
    """
    Six conversations, every reply of the script, code coloured and a diff
    hosted, before the demo app was imported: NOTHING is loaded of the old
    core. Until 2026-10-12 it was what measuring a face loads (`MEASURING`
    of `tests/test_typeset_closure.py`): `typesetter.load_fonts` asked
    `imscribe.fontlib` where the font files are, and the mono preset's
    `Theme.at_pixel_height` measured one through
    `imscribe.style.fontlib_metrics`. The files are `imscribe.fontfiles`'
    now, and the child has loaded the library's fonts before the preset
    sizes its theme, so the library measures (`imscribe.typeset_metrics`).
    """
    loaded = set(typeset["old_before_app"])
    assert loaded == set(), sorted(loaded)
    everything = set(typeset["imscribe_before_app"])
    for name in ("imscribe.stream", "imscribe.markdown", "imscribe.mathtext", "imscribe.spans"):
        assert name not in everything, name
    assert not {n for n in everything if n.startswith(("imscribe.backends", "imscribe.ui.bare"))}
    # The mono preset was sized all the same, and by the library.
    assert "imscribe.style" not in everything and "imscribe.typeset_metrics" in everything


def test_the_page_takes_a_typed_turn_follows_the_end_and_lets_go(
    typeset: dict[str, Any],
) -> None:
    """
    A turn typed into the real `InputText` and entered posts it and plays the
    next reply, the box is emptied and keeps the keyboard, the reply is
    followed to its end over many edits, and the finished messages are not
    handed to the library again while it arrives. No page had a conversation
    before its first frame.
    """
    told = typeset["page"]
    assert typeset["unmade"] and all(typeset["unmade"])
    assert told["renderer"] == "typeset" and told["reason"] == ""
    assert told["typed"] == ["hello there", 2]
    assert told["roles"] == [USER, ASSISTANT, USER, ASSISTANT]
    assert told["asked"] == "hello there\n" and told["box"] == ""
    assert told["kept_keyboard"] == "x"
    assert [shape["view"] for shape in told["shapes"]] == ["TypesetView"] * 3 + [
        "TypesetStreamView"
    ]
    assert told["edits"]["set"] == 1 and sum(told["edits"].values()) > 40
    before, after = told["finished_edits"]
    assert before == after == [{"set": 1, "replace": 0, "append": 0}] * 3
    # B5 (T5-R #4): the assertion above cannot see a layout that is repeated
    # with nothing handed over. The library's own count of blocks laid out
    # can: over the whole reply it did not move for any finished message...
    laid_before, laid_after = told["finished_laid_out"]
    assert laid_before == laid_after and len(laid_before) == 3
    assert all(count > 0 for count in laid_before), "a finished message was never laid out"
    # ...and it is a count that moves when they ARE laid out again: at another
    # width, for each finished message the narrower window shows.
    narrower, in_view = told["laid_out_narrower"]
    assert any(in_view)
    for was, now, seen in zip(laid_after, narrower, in_view, strict=True):
        assert (now > was) if seen else (now >= was)
    assert told["following"] is True and told["draw_ms"] is True and told["timed"] is True
    # The pane followed the reply down: the last message is in view, and what
    # has scrolled out above it submits nothing.
    assert told["vertices"][-1] > 500 and all(told["whole"])
    assert all(told["bar"])
    assert " renderer=typeset" in told["report"] and "glyphs=" not in told["report"]
    assert typeset["all"] == [12, True]
    followed, after_wheel, done, others = typeset["wheel"]
    assert followed is True and after_wheel is False and done is False and others is True


def test_the_buttons_copy_and_flip_and_one_selection_is_current(
    typeset: dict[str, Any],
) -> None:
    buttons = typeset["buttons"]
    assert buttons["markdown"] is True and buttons["code"] == "import re\n"
    assert buttons["diff"] == buttons["clipboard"] == "--- a/replay.py\n" and buttons["copied"] == 3
    assert buttons["flipped"] == ["SIDE_BY_SIDE", "UNIFIED", None]
    # The indented fence of a list item comes back without its indentation.
    assert buttons["listed"] == "fonts = load_faces()\n"
    assert typeset["tops"] and all(same for _, same in typeset["tops"])
    assert typeset["tops_out_of_view"] == []
    selection = typeset["selection"]
    assert selection["one"][0] is True and len(selection["one"][1]) == 12
    assert selection["two"] == [True, None]
    assert selection["three"] == [True, False]


def test_a_nul_in_a_message_does_not_cut_what_the_buttons_put_on_the_clipboard(
    typeset: dict[str, Any],
) -> None:
    """
    Review 3, item 9. The clipboard is a C string: handed `key = 'ab\\0cd'`
    and a line after it, it kept `key = 'ab` and nothing else. The page's
    buttons send a NUL as U+2400 (`imscribe.ui.ownership.clipboard_text`).
    What the method returns is still the message's source, NUL and all.
    """
    role, kept, returned, clipboard = typeset["nul"]
    assert role == USER and kept is True and returned is True
    assert clipboard == "key = 'ab␀cd'\nnext line\n"


def test_when_a_draw_raises_the_page_is_the_one_line_from_the_next_frame_on(
    typeset: dict[str, Any],
) -> None:
    """
    `TypesetView.draw` made to raise `TypesetUnavailable` for one frame, with
    the library ready throughout, on the whole script. That frame ended
    without an error and the page holds what was said; the four frames after
    it are `say_why_not` with that sentence, although the library could draw
    again. The conversation is as it was and the page is still the page.
    """
    told = typeset["middraw"]
    assert told["ready"] is True and told["current"] == "ChatPage"
    at_once = told["at_once"]
    assert at_once["failed"] == "raised by the test" == at_once["reason"]
    assert at_once["renderer"] == "none" and at_once["frames"] == 1
    assert told["shown"] == ["raised by the test"] * 4
    assert told["count"] == [12, 12] and told["report"].endswith(" renderer=none")


def test_a_post_the_library_fails_under_posts_nothing_and_the_page_says_why(
    typeset: dict[str, Any],
) -> None:
    """
    `TypesetStreamView.sync` made to raise `TypesetUnavailable` under `send`,
    with a reply arriving: `send` returns, no turn is added, the script does
    not move on, what was typed stays in the box, and the next frame is the
    one line.
    """
    told = typeset["send"]
    assert told["ready"] is True
    assert told["failed"] == "raised by the test" and told["renderer"] == "none"
    assert told["roles"] == [USER, ASSISTANT, USER, ASSISTANT] and told["posted"] == 2
    assert told["typed"] == "again" and told["shown"] == ["raised by the test"]


def test_when_the_library_is_switched_off_the_page_is_the_one_line(
    typeset: dict[str, Any],
) -> None:
    """
    `typesetter.disable` between two frames of a reply. The next frame is the
    line with the reason; nothing more is fed, a `send` posts nothing and
    keeps what was typed, and the page raised nothing.
    """
    off = typeset["off"]
    before, after = off["before"], off["after"]
    assert off["ready"] is False and before["renderer"] == "typeset"
    assert after["renderer"] == "none" and "switched off by the test" in after["reason"]
    assert after["failed"] == "", "nothing was raised: the page asked `ready()` first"
    assert after["fed"] == before["fed"] == off["fed"]
    assert off["typed"] == "more" and off["messages"] == 4
    assert off["frames"] == before["frames"] + 6 and off["report"].endswith(" renderer=none")

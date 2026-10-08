"""
The Chat page: a whole canned conversation on a clock advanced by hand, the page
in frames, and once in a real window.

**Three levels.**

1. `Conversation` with no ImGui: posting, feeding, settling, the presets, and
   a streamed reply held to the document the same text gives whole.
2. The page through `App.gui` in frames of a context with no backend: a real
   `InputText` typed into, Enter, the wheel, the buttons' actions.
3. The real app in a real window, at a rate that spans many layouts.

**Nothing here judges how a conversation looks.** The script's content is held
to what the task says it must exercise, and the counters to what can be counted.
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

import advtext.ui.units
from advtext.markdown import CodeBlock, TableBlock, TextBlock, build_document, formula_spans
from advtext.selection import Selection
from advtext.stream import CommitPolicy
from advtext.style import Align, BlockKind
from advtext.ui import HostBlock, pages
from advtext.ui.app import App, parse_tab_request
from advtext.ui.bare_view import BareView
from advtext.ui.diff_view import DiffLayout
from advtext.ui.pages import PageContext
from advtext.ui.pages import chat as page
from advtext.ui.pages.chat import ASSISTANT, MONO, ROBOTO, USER, Conversation, Exchange
from advtext.ui.stream_view import StreamView

if TYPE_CHECKING:
    from conftest import Window

WIDTH_PX = 700.0
FRAME = 1.0 / 60.0


@pytest.fixture(scope="module")
def script() -> tuple[Exchange, ...]:
    text = pages.demo_text("chat/script.md")
    assert text is not None, "demo/chat/script.md is missing"
    return page.parse_script(text)


@pytest.fixture(scope="module")
def context() -> PageContext:
    return PageContext.build()


def _talk(context: PageContext, script: tuple[Exchange, ...], **fields: Any) -> Conversation:
    return Conversation(context, script, **fields)


def _play(conversation: Conversation, seconds: float = FRAME) -> int:
    """
    Tick and settle until the reply is complete. Returns the ticks; fails if it never ends.
    """
    ticks = 0
    while not conversation.done:
        conversation.advance(seconds)
        conversation.settle(WIDTH_PX)
        ticks += 1
        assert ticks < 100_000, "the reply never finished"
    conversation.settle(WIDTH_PX)
    return ticks


# ----------------------------------------------------------------------
# The script
# ----------------------------------------------------------------------


def test_the_script_exercises_what_the_page_is_for(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    """
    Read off the blocks each reply becomes, not off the markdown's spelling.
    """
    assert len(script) == 6
    math = page.markdown_math()
    seen: set[str] = set()
    for exchange in script:
        assert exchange.prompt.strip() and exchange.reply.strip()
        document = build_document(
            exchange.reply, context.theme, context.metrics, references=False, math=math
        )
        code = context.theme.style(BlockKind.CODE).font.key
        prose = context.theme.style(BlockKind.PARAGRAPH).font.key
        for block in document.blocks:
            match block:
                case CodeBlock():
                    seen.add("diff" if block.language == "diff" else "code")
                    if block.left_indent > block.style.left_indent:
                        seen.add("fence in a list item")
                case TableBlock():
                    seen.add("table")
                case TextBlock():
                    if block.links:
                        seen.add("link")
                    if block.marker and block.kind is BlockKind.ORDERED_ITEM:
                        seen.add("numbered item")
                    elif block.kind is BlockKind.ORDERED_ITEM:
                        seen.add("indented paragraph of an item")
                    fonts = {getattr(node, "font", prose) for node in block.material}
                    if code in fonts and len(fonts) > 1:
                        seen.add("inline code")
            for span in formula_spans(block):
                assert not span.refusal, (span.source, span.refusal)
                seen.add("display formula" if span.display else "inline formula")
        if len(document.blocks) >= 30:
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
    document = build_document(
        reply, context.theme, context.metrics, references=False, math=page.markdown_math()
    )
    last = document.blocks[-1]
    assert isinstance(last, CodeBlock) and last.language == "diff"
    first = document.blocks[0]
    assert isinstance(first, TextBlock)
    spans = formula_spans(first)
    assert [span.source for span in spans] == ["x^2"] and not spans[0].refusal
    text = "".join(chr(node.codepoint) for node in first.material if hasattr(node, "codepoint"))
    assert "PATH=$HOME/bin:$PATH" in text


def test_a_script_is_whole_exchanges_and_tokens_join_back() -> None:
    text = "junk\n%% assistant\norphan\n%% user\nq1\n%% assistant\na1\n\nmore\n%% user\nq2\n"
    assert page.parse_script(text) == (Exchange("q1\n", "a1\n\nmore\n"),)
    assert page.parse_script("no turns") == ()
    (fallback,) = page.parse_script(page.FALLBACK)
    assert "```diff" in fallback.reply
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
# The conversation
# ----------------------------------------------------------------------


def test_it_opens_on_one_finished_exchange_and_enter_plays_the_next(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    assert [m.role for m in talk.messages] == [USER, ASSISTANT]
    assert talk.done and talk.posted == 1 and talk.next is script[1]
    assert all(type(m.view) is BareView for m in talk.messages)

    reply = talk.post("my own words")
    assert [m.role for m in talk.messages] == [USER, ASSISTANT, USER, ASSISTANT]
    assert talk.messages[2].markdown == "my own words\n"
    assert isinstance(reply.view, StreamView) and not talk.done and talk.fed == 0
    assert talk.advance(FRAME) == 1 and talk.fed == 1
    assert talk.advance(0.5) == 30
    ticks = _play(talk)
    assert ticks > 1 and talk.done and talk.fed == len(talk.pieces)
    assert reply.markdown == script[1].reply
    assert talk.token_count == len(talk.pieces) and talk.token_mean_ms > 0.0

    # Blank: the script's own prompt. And the last exchange wraps to the first.
    talk.post("   ")
    assert talk.messages[-2].markdown == script[2].prompt
    for _ in range(4):
        talk.post()
    assert talk.posted == 7 and talk.messages[-2].markdown == script[0].prompt
    # Posting over a reply still arriving finishes it first.
    assert all(m.stream is None or m.stream.closed for m in talk.messages[:-1])


def test_a_streamed_reply_is_the_document_the_same_text_gives_whole(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    """
    Arriving and finished messages are read alike, so `set_preset` -- which
    rebuilds a finished reply from its markdown -- changes nothing about it.
    Every exchange of the script, hosted diffs and formulas included.
    """
    for number in range(1, len(script)):
        talk = _talk(context, script, tokens_per_second=600.0)
        talk.posted = number
        streamed = talk.post()
        _play(talk)
        whole = talk._finished(ASSISTANT, script[number].reply)
        a, b = streamed.view, whole.view
        la, lb = a.layout_for(advtext.units.sp_from_px(WIDTH_PX)), b.layout_for(
            advtext.units.sp_from_px(WIDTH_PX)
        )
        assert len(a.document.blocks) == len(b.document.blocks), number
        assert [type(x) for x in a.document.blocks] == [type(x) for x in b.document.blocks]
        assert la.model.copy_text(Selection(0, la.length)) == lb.model.copy_text(
            Selection(0, lb.length)
        ), number
        assert streamed.codes == whole.codes, number
        for block in streamed.codes:
            assert streamed.block_code(block) == whole.block_code(block), (number, block)


def test_reference_definitions_are_text_in_a_finished_message_and_in_one_arriving(
    context: PageContext,
) -> None:
    """
    Review 4: built with the default, the finished copy of a reply made links
    the arriving copy had shown as text.
    """
    reply = "See [the paper][1] for why.\n\n[1]: https://example.org/paper\n"
    talk = _talk(context, (Exchange("q\n", reply), Exchange("again\n", reply)))
    talk.post()
    _play(talk)
    finished, streamed = talk.messages[1], talk.messages[3]
    for message in (finished, streamed):
        blocks = message.view.document.blocks
        assert len(blocks) == 2
        assert all(isinstance(b, TextBlock) and not b.links for b in blocks)


def test_the_diff_reply_is_drawn_by_a_diff_view_that_grows_and_code_is_coloured(
    context: PageContext, script: tuple[Exchange, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    coloured: dict[tuple[int, int], int] = {}
    original = BareView.set_colours

    def recording(view: BareView, block: int, spans: Any) -> None:
        coloured[(id(view), block)] = len(spans)
        original(view, block, spans)

    monkeypatch.setattr(BareView, "set_colours", recording)
    talk = _talk(context, script, tokens_per_second=60.0)

    talk.post()  # the python fence
    _play(talk)
    code = talk.messages[-1]
    (fence,) = code.codes
    assert code.diff(fence) is None and coloured[(id(code.view), fence)] > 5
    assert code.block_code(fence).startswith("import re\n\ndef tokens(")
    assert "```" not in code.block_code(fence)

    reply = talk.post()  # the diff
    fed: list[int] = []
    while not talk.done:
        talk.advance(FRAME)
        talk.settle(WIDTH_PX)
        fed.append(reply.fences.fed_lines)
    (fence,) = reply.codes
    hosted = reply.diff(fence)
    # While its info string was still `di` and `dif` the fence was a code
    # block and was coloured as one; as a diff it has no spans left.
    assert hosted is not None and coloured[(id(reply.view), fence)] == 0
    assert isinstance(
        reply.view.layout_for(advtext.units.sp_from_px(WIDTH_PX)).placed[fence].blocks[0], HostBlock
    )
    # A line or so at a time over many ticks, never the lot at once: one piece
    # a tick, and a piece carries the white space before it, so a blank
    # context line and the line after it can arrive together.
    steps = {b - a for a, b in zip(fed, fed[1:], strict=False)}
    assert steps <= {0, 1, 2} and len(set(fed)) >= 12
    assert fed[-1] == 15 and reply.fences.restarts == 0
    assert (hosted.view.diff.added, hosted.view.diff.removed) == (4, 3)
    assert reply.block_code(fence) == hosted.text
    assert hosted.text.startswith("--- a/replay.py\n") and hosted.text.endswith('== "a  bc\\n"\n')


def test_finished_messages_are_not_laid_out_again_while_a_reply_arrives(
    context: PageContext, script: tuple[Exchange, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    talk.posted = 5  # the long reply
    width = advtext.units.sp_from_px(WIDTH_PX)
    reply = talk.post()
    before = [m.view.layout_for(width) for m in talk.messages[:-1]]

    shipped = 0
    ship = advtext.ui.units.ship_unit

    def counted(composed: Any, measure: Any) -> Any:
        nonlocal shipped
        shipped += 1
        return ship(composed, measure)

    monkeypatch.setattr(advtext.ui.units, "ship_unit", counted)
    per_token: list[int] = []
    while not talk.done:
        shipped = 0
        assert talk.advance(FRAME) == 1
        talk.settle(WIDTH_PX)
        per_token.append(shipped)
    assert [m.view.layout_for(width) for m in talk.messages[:-1]] == before
    assert all(
        a is b for a, b in zip([m.view.layout for m in talk.messages[:-1]], before, strict=True)
    )
    assert isinstance(reply.view, StreamView) and reply.view.relayouts <= len(talk.pieces) + 1
    # What a token costs in units shipped does not grow along a long reply.
    third = len(per_token) // 3
    assert len(per_token) > 1500
    assert max(per_token[-third:]) <= max(per_token[:third]) <= 4, (
        max(per_token[:third]),
        max(per_token[-third:]),
    )
    assert len(reply.view.document.blocks) >= 30


def test_the_presets_are_what_they_say_and_switching_keeps_the_conversation(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    assert talk.preset is MONO and MONO.policy is CommitPolicy.KEEP_STREAMED
    faces = talk.theme.faces
    assert faces.regular is faces.code and talk.theme.style(BlockKind.PARAGRAPH).align is Align.LEFT
    assert ROBOTO.theme(context) is context.theme and ROBOTO.policy is CommitPolicy.RESET
    assert context.theme.style(BlockKind.PARAGRAPH).align is Align.JUSTIFY

    reply = talk.post()
    for _ in range(40):
        talk.advance(FRAME)
    talk.settle(WIDTH_PX)
    arrived = reply.markdown
    assert 0 < talk.fed < len(talk.pieces)
    talk.set_preset(ROBOTO)
    assert talk.theme is context.theme and len(talk.messages) == 4
    assert [m.role for m in talk.messages] == [USER, ASSISTANT, USER, ASSISTANT]
    again = talk.messages[-1]
    assert again is not reply and again.markdown == arrived and not talk.done
    assert again.stream is not None and again.stream.policy is CommitPolicy.RESET
    _play(talk)
    assert again.markdown == script[1].reply
    talk.set_preset(ROBOTO)
    assert talk.messages[-1] is again, "setting the preset it already has rebuilt everything"


def test_the_readouts_say_the_replies_are_canned_and_report_counts(
    context: PageContext, script: tuple[Exchange, ...]
) -> None:
    talk = _talk(context, script, tokens_per_second=60.0)
    talk.post()
    talk.advance(0.25)
    talk.settle(WIDTH_PX)
    first, second = page.readouts(talk, 3.21)
    assert "canned" in first and "No model, no network" in first
    assert f"piece 15 of {len(talk.pieces)}" in first
    assert "page draw 3.2 ms" in second and "over 15)" in second and "4 messages" in second
    messages, live, committed = talk.counts()
    assert f"blocks: {live} live, {committed} committed" in second and live >= 1
    for word in ("better", "worse", "good", "bad", "smooth", "fast", "slow", "crisp"):
        assert word not in f"{first} {second}".lower().split()
    assert _talk(context, ()).exchanges == page.parse_script(page.FALLBACK)


# ----------------------------------------------------------------------
# The page, in frames
# ----------------------------------------------------------------------

SIZE = (1300.0, 800.0)


@pytest.fixture
def imgui() -> Iterator[Any]:
    """
    ImGui with a context of this test's own: the input box's state is per context.
    """
    module = pytest.importorskip("imgui_bundle").imgui
    before = module.get_current_context()
    made = module.create_context()
    module.set_current_context(made)
    try:
        yield module
    finally:
        module.destroy_context(made)
        if before is not None:
            module.set_current_context(before)


def _frame(imgui: Any, app: App, seconds: float = FRAME, **events: Any) -> None:
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = seconds
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
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
        imgui.begin("##advtext-chat-page-test", None, imgui.WindowFlags_.no_title_bar.value)
        app.gui()
        imgui.end()
    finally:
        imgui.render()


def _open(imgui: Any, spec: str = "chat") -> tuple[App, page.ChatPage]:
    app = App(source="# t\n\nx\n", columns_source="x\n", open_tab=spec)
    _frame(imgui, app)
    _frame(imgui, app)
    made = app.page("chat")
    assert isinstance(made, page.ChatPage)
    return app, made


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


def test_the_page_is_listed_where_the_lead_put_it_and_reads_its_options() -> None:
    spec = page.PAGE
    assert (spec.name, spec.group, spec.order) == ("Chat", "Streaming", 220)
    plain = page.ChatPage(_context("chat"))
    assert plain.conversation.preset is MONO and len(plain.conversation.messages) == 2
    assert plain.conversation.tokens_per_second == page.DEFAULT_TOKENS_PER_SECOND
    played = page.ChatPage(_context("chat:roboto,play,250"))
    assert played.conversation.preset is ROBOTO and played.conversation.tokens_per_second == 250.0
    assert len(played.conversation.messages) == 4 and not played.conversation.done
    everything = page.ChatPage(_context("chat:all"))
    assert len(everything.conversation.messages) == 12 and everything.conversation.done


def test_the_page_does_not_raise_for_a_missing_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = page.ChatPage(_context("chat:play"))
    assert len(made.conversation.exchanges) == 1 and len(made.conversation.messages) == 4


def test_typing_and_enter_posts_a_turn_and_the_reply_streams_following_the_end(
    imgui: Any,
) -> None:
    app, made = _open(imgui, "chat:120")
    talk = made.conversation
    made._refocus = True
    _frame(imgui, app)
    _frame(imgui, app)
    _frame(imgui, app, text="hello there")
    assert made.typed == "hello there" and len(talk.messages) == 2
    _frame(imgui, app, keys=((imgui.Key.enter, True),))
    _frame(imgui, app, keys=((imgui.Key.enter, False),))
    assert [m.role for m in talk.messages] == [USER, ASSISTANT, USER, ASSISTANT]
    assert talk.messages[2].markdown == "hello there\n" and made.typed == ""
    reply = talk.messages[-1]
    assert isinstance(reply.view, StreamView)
    frames = 0
    while not talk.done:
        _frame(imgui, app)
        frames += 1
        assert frames < 2000
    _frame(imgui, app)
    # Two pieces a frame: a layout for most frames, and the pane kept at its end.
    assert reply.view.relayouts > 40 and reply.view.following
    assert reply.stats is not None and reply.stats.glyphs > 0
    assert made.draw_ms > 0.0 and talk.token_count == len(talk.pieces)
    # The box kept the keyboard: more typing goes into it.
    _frame(imgui, app, text="x")
    assert made.typed == "x"


def test_scrolling_up_lets_go_of_the_end_while_a_reply_arrives(imgui: Any) -> None:
    app, made = _open(imgui, "chat:all")
    talk = made.conversation
    talk.tokens_per_second = 60.0
    made.send()
    reply = talk.messages[-1]
    assert isinstance(reply.view, StreamView)
    for _ in range(6):
        _frame(imgui, app)
    assert reply.view.following
    _frame(imgui, app, mouse=(700.0, 400.0))
    _frame(imgui, app, wheel=5.0)
    for _ in range(4):
        _frame(imgui, app)
    assert not reply.view.following and not talk.done
    # Every earlier stream view has stopped following for good.
    assert all(not m.view.follow for m in talk.messages[:-1] if isinstance(m.view, StreamView))


def test_the_buttons_copy_a_message_a_block_and_a_diff_and_flip_its_layout(imgui: Any) -> None:
    app, made = _open(imgui, "chat:all")
    talk = made.conversation
    assert made.copy_markdown(1) == talk.exchanges[0].reply == imgui.get_clipboard_text()
    code = next(i for i, m in enumerate(talk.messages) if m.codes and m.diff(m.codes[0]) is None)
    assert made.copy_block(code, talk.messages[code].codes[0]).startswith("import re\n")
    diff = next(i for i, m in enumerate(talk.messages) if m.codes and m.diff(m.codes[0]))
    block = talk.messages[diff].codes[0]
    assert made.copy_block(diff, block).startswith("--- a/replay.py\n")
    assert imgui.get_clipboard_text().startswith("--- a/replay.py\n") and made.copied == 3
    assert made.toggle_diff(diff, block) is DiffLayout.SIDE_BY_SIDE
    _frame(imgui, app)
    _frame(imgui, app)
    assert made.toggle_diff(diff, block) is DiffLayout.UNIFIED
    assert made.toggle_diff(code, talk.messages[code].codes[0]) is None
    # The indented fence of a list item comes back without its indentation.
    listed = next(
        i for i, m in enumerate(talk.messages) if len(m.codes) == 3 and m.role == ASSISTANT
    )
    first = talk.messages[listed].codes[0]
    assert made.copy_block(listed, first) == "fonts = load_faces()\n"


def test_a_nul_in_a_message_does_not_cut_what_the_buttons_put_on_the_clipboard(
    imgui: Any,
) -> None:
    """
    Review 3, item 9, for the one clipboard write C-fix3 could not reach.

    The clipboard is a C string: handed `key = 'ab\\0cd'` and a line after it,
    it kept `key = 'ab` and nothing else. `BareView` and `DiffView` send a NUL
    as U+2400 (`advtext.ui.bare_view.clipboard_text`); the page's own buttons
    wrote to the clipboard themselves and did not. What the method returns is
    still the message's source, NUL and all, as `selected_text()` is for a view.
    """
    app, made = _open(imgui, "chat:all")
    talk = made.conversation
    typed = "key = 'ab\0cd'\nnext line\n"
    talk.post(typed)
    talk.finish()
    asked = len(talk.messages) - 2
    assert talk.messages[asked].role == USER and talk.messages[asked].markdown == typed
    assert made.copy_markdown(asked) == typed
    assert imgui.get_clipboard_text() == "key = 'ab␀cd'\nnext line\n"
    # A text with no NUL goes as it is.
    assert made.copy_markdown(1) == talk.exchanges[0].reply == imgui.get_clipboard_text()


def test_one_selection_at_a_time_across_messages_and_their_diffs(imgui: Any) -> None:
    app, made = _open(imgui, "chat:all")
    talk = made.conversation
    first, second = talk.messages[1].view, talk.messages[3].view
    first.select(Selection(0, 12))
    _frame(imgui, app)
    assert first.owns_selection and not first.selection.is_empty
    second.select(Selection(3, 9))
    _frame(imgui, app)
    assert second.owns_selection and first.selection.is_empty
    diff = next(m for m in talk.messages if m.codes and m.diff(m.codes[0]))
    hosted = diff.diff(diff.codes[0])
    assert hosted is not None
    hosted.view.select_all()
    # Drawn or not, a view drops its selection on its next frame; scroll to the diff's message.
    for _ in range(3):
        _frame(imgui, app)
    assert hosted.view.owns_selection and not second.owns_selection


# ----------------------------------------------------------------------
# A real window
# ----------------------------------------------------------------------

WINDOW_RATE = 400
"""Pieces a second of the page's clock in the windowed run (`--tab chat:play,400`)."""

WINDOW_FRAME = 1.0 / 60.0
"""
What the windowed run tells the page every frame took, whatever it really took.

The page feeds `delta_time * rate` pieces a frame. Left to the real clock, how
many layouts a reply spans is a fact about the machine: this test used to
assert `layouts > 10`, and a loaded machine whose frames ran long fed a whole
reply in fewer (the one known flaky test of the suite). With the frame's
length stated, a frame is worth `WINDOW_RATE * WINDOW_FRAME` pieces -- six or
seven -- on any machine, and a slow one only takes longer to get through them.
"""

WINDOWED = """
from imgui_bundle import hello_imgui, imgui

from advtext.ui import app as advtext_app

state = {"frames": 0, "turn": 0}
real_gui = advtext_app.App.gui


def watched_gui(self):
    if state["frames"] == 0:
        hello_imgui.get_runner_params().fps_idling.enable_idling = False
    # The page reads how long the frame took from here; the test says why.
    imgui.get_io().delta_time = FRAME
    real_gui(self)
    state["frames"] += 1
    made = self.page("chat")
    if made.conversation.done and state["frames"] > 3:
        print(made.report()[0])
        state["turn"] += 1
        if state["turn"] >= 3 or state["frames"] >= 20000:
            hello_imgui.get_runner_params().app_shall_exit = True
        else:
            made.send()


advtext_app.App.gui = watched_gui
advtext_app.run(tab="chat:play,RATE")
"""


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


def test_three_replies_stream_in_a_real_window(window: Window) -> None:
    """
    `--tab chat:play,400`: the code reply, the diff reply and the list-and-table
    reply, each until it is complete, on a clock that calls every frame a
    sixtieth of a second (`WINDOW_FRAME`). Counts only.

    **That a reply streams across many layouts** is the assertion on
    `layouts`, and it is arithmetic and not timing: a frame is worth
    `400 / 60` pieces, so a reply of `pieces` pieces cannot arrive in fewer
    than `ceil(pieces * 60 / 400)` frames, and the view lays out once in each
    frame that brought something. The count must be at least that (a smaller
    one would mean a layout took in more than a frame's worth: pieces fed and
    not shown) and at most two over (a layout nothing arrived for). Measured
    here, twice: 24, 37 and 57 layouts for 157, 242 and 374 pieces, which is
    the lower bound exactly. Every reply is over a hundred pieces, so "many"
    is more than fifteen.
    """
    script = window.out / "chat_page.py"
    source = WINDOWED.replace("FRAME", repr(WINDOW_FRAME)).replace("RATE", str(WINDOW_RATE))
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    done = window.run([str(script)])
    assert done.returncode == 0, f"on {window.where}:\n{done.stdout}\n{done.stderr}"
    lines = [_fields(line) for line in done.stdout.splitlines() if line.startswith("frames=")]
    assert len(lines) == 3, done.stdout
    assert [line["messages"] for line in lines] == ["4", "6", "8"]
    for line in lines:
        assert line["done"] == "1" and line["fed"] == line["pieces"] and line["live"] == "0"
        pieces = int(line["pieces"])
        assert pieces > 100, done.stdout
        frames_needed = math.ceil(pieces / (WINDOW_RATE * WINDOW_FRAME) - 1e-6)
        assert frames_needed > 15
        assert (
            frames_needed <= int(line["layouts"]) <= frames_needed + 2
        ), f"{pieces} pieces need {frames_needed} frames at {WINDOW_RATE} a second: {done.stdout}"
        assert int(line["glyphs"]) > 0 and line["missing"] == "0"
        assert line["tokens_timed"] == line["pieces"] and line["preset"] == "mono"
    assert [line["diffs"] for line in lines] == ["0", "1", "1"]
    assert lines[1]["diff_lines"] == "15" and lines[2]["codes"] == "5"

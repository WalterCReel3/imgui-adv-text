"""
The Find page: its search held to the totals the old page's index found, its
marks held to what the view is handed, and the page in frames and in a window.

**Four levels, so nobody reads more into a green run than is there.**

1. No ImGui and no library: the search, its steps, its label and its cost.
   The index is built from block descriptions, which need no library, so the
   page has all of that whether or not anything is drawn.
2. Frames of a real `ImGuiContext` with no backend, in this process. The
   library is never ready here, so the page is ONE LINE saying why. A fake
   view shows what this process can see of the rest: marks handed over once
   per change as plain tuples, real characters typed into the real
   `InputText`, real Enter and Shift+Enter, and a view that fails mid-run
   leaving the page alive.
3. With the library, real frames, no window (`test_page_document.typeset_child`;
   skipped with the reason when `IMTYPESET_LIBRARY` is not set).
4. The real app in a real window: with the library on the sample twenty times
   over (asserting in the child that it is imported and ready), and without
   it (the one line, and no traceback page).

**Nothing here judges how a mark looks.** A test says which ranges were handed
to the view, where their rectangles are, and that the document was not edited.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import pytest
from test_page_document import (
    VARIABLES,
    WATCH_WITHOUT,
    says_only_why_not,
    typeset_child,
    unasked,
    windowed_typeset,
)

from advtext.typeset_find import FindIndex
from advtext.typeset_markdown import MarkdownConverter, parse_markdown
from advtext.ui.app import parse_tab_request
from advtext.ui.pages import PageContext
from advtext.ui.pages import find as page
from advtext.ui.pages.find import CURRENT_MARK, HIT_MARK
from advtext.ui.typeset_view import TypesetUnavailable

if TYPE_CHECKING:
    from conftest import Window

assert unasked  # the fixture, imported: `typesetter.module()` fails the test if asked

SIZE = (1300.0, 800.0)

# What the OLD page's index (`advtext.spans.FindIndex` over `build_document`'s
# blocks) found in this page's document -- `demo/sample.md` five times over --
# for nine needles: `(case ignored, case matched)`, matches outside table
# cells plus matches in them. Frozen on 2026-10-11, before that page body was
# removed (`.concerns/T5-FB-A-scripts/find_totals.py` printed them; of
# "glue"'s 55, 15 were in cells, which the old page counted and could not
# mark). The index this page uses now must find as many: that the swap lost
# no match is otherwise nowhere held.
OLD_TOTALS = {
    "glue": (55, 50),
    "the": (340, 295),
    "e": (2690, 2675),
    "Knuth": (5, 5),
    "hpack": (10, 10),
    "|": (0, 0),
    "zzqq": (0, 0),
    "The model": (5, 5),
    "a b": (30, 20),
}

GLUE = (
    "# A heading\n\nSome glue, then [a link](https://example.org) and more Glue.\n\n"
    "```\nglue = 1\n```\n\nA last paragraph with glue in it.\n"
)


def _context(spec: str) -> PageContext:
    request = parse_tab_request(spec)
    return PageContext.build(
        request_page=request.tab, request_options=request.options, request_count=request.columns
    )


# ----------------------------------------------------------------------
# 1. No ImGui, no library: the search
# ----------------------------------------------------------------------


def test_the_page_is_listed_where_the_lead_put_it() -> None:
    spec = page.PAGE
    assert (spec.name, spec.group, spec.order) == ("Find", "Embedding", 130)
    assert spec.shot_specs() == ("find",)
    assert spec.accepts("case") and not spec.accepts("nonsense")


def test_the_page_opens_with_a_needle_already_found(unasked: None) -> None:
    made = page.FindPage(_context("find"))
    assert made.copies == page.DEFAULT_COPIES
    finder = made.finder
    assert finder.needle == page.DEFAULT_NEEDLE and finder.ignore_case
    assert len(finder.matches) == OLD_TOTALS["glue"][0]
    assert finder.label == f"1 of {len(finder.matches)}"
    assert finder.keystrokes == 0, "the opening search is not something anybody typed"
    one = page.FindPage(_context("find:1"))
    assert made.blocks == page.DEFAULT_COPIES * one.blocks > 100
    # No view in this process: found, and handed to nobody.
    assert made.typeset is None and finder.view is None and finder.marked == 0
    assert finder.rects() == [] and finder.span_px() is None and not made.shown()


def test_the_launch_options_set_the_copies_and_case_matching(unasked: None) -> None:
    two = page.FindPage(_context("find:2,case"))
    one = page.FindPage(_context("find:1"))
    assert (two.copies, one.copies) == (2, 1)
    assert not two.finder.ignore_case and one.finder.ignore_case
    assert two.blocks == 2 * one.blocks
    other = page.FindPage(_context("document:3"))
    assert other.copies == page.DEFAULT_COPIES


def test_the_page_does_not_raise_for_a_missing_demo_file(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    monkeypatch.setattr(page, "demo_text", lambda name: None)
    made = page.FindPage(_context("find:1"))
    assert made.source == page.FALLBACK and made.blocks == 1
    assert len(made.finder.matches) == 2


def test_the_search_finds_what_the_old_pages_index_found(unasked: None) -> None:
    """
    Nine needles, case ignored and matched, against `OLD_TOTALS`.

    The needles are not all misses, a space finds what a space found, and a
    `|` (the table's own syntax, in no cell's text) finds nothing.
    """
    made = page.FindPage(_context("find"))
    finder = made.finder
    for needle, (insensitive, sensitive) in OLD_TOTALS.items():
        assert len(finder.search(needle, ignore_case=True)) == insensitive, needle
        assert len(finder.search(needle, ignore_case=False)) == sensitive, needle
    assert finder.keystrokes == 2 * len(OLD_TOTALS)
    assert sum(1 for total, _ in OLD_TOTALS.values() if total) == 7


def test_the_search_its_steps_and_its_label_need_no_view(unasked: None) -> None:
    """
    What a keystroke and next/previous do to the page's state, with nothing drawn.
    """
    made = page.FindPage(_context("find:1"))
    finder = made.finder
    count = len(finder.matches)
    assert count == 11 and finder.label == "1 of 11"
    made.step(1)
    made.step(1)
    assert finder.current == 2 and finder.label == "3 of 11"
    made.step(-3)
    assert finder.label == f"{count} of {count}", "previous wraps from the first to the last"
    made.step(1)
    assert finder.label == f"1 of {count}", "and next from the last to the first"

    # Typing another letter keeps the current match where the reader is.
    made.type("th")
    for _ in range(40):
        made.step(1)
    before = finder.match
    assert before is not None and before.block > 0
    made.type("the")
    after = finder.match
    assert after is not None
    assert (after.block, after.start) >= (before.block, before.start)
    earlier = finder.matches[: finder.current]
    assert all((m.block, m.start) < (before.block, before.start) for m in earlier)

    made.type("zzqq")
    assert finder.label == "no matches" and finder.match is None
    made.step(1)
    assert finder.match is None
    made.type("")
    assert finder.label == ""
    made.type("knuth")
    assert len(finder.matches) == 1
    made.match_case(True)
    assert not finder.ignore_case and finder.matches == ()
    made.match_case(False)
    assert len(finder.matches) == 1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.001
        return self.now


class _FakeTypeset:
    """
    What the page reads of a `TypesetView`, failing where and when it is told to.

    `fail` names the call that raises (`"draw"`, `"set_marks"`, `"scroll_to"`
    or `"stats"`) and `fail_at` the draw from which it does.
    """

    scrolled = False
    revision = 0  # what the page saw when it was built with no view: nothing edits it
    origin = (0.0, 0.0)

    def __init__(
        self,
        texts: Sequence[str],
        fail_at: int = 99,
        fail: str = "draw",
        error: Exception | None = None,
    ) -> None:
        self.texts = tuple(texts)
        self.fail_at = fail_at
        self.fail = fail
        self.error = error or TypesetUnavailable("imtypeset failed and is switched off: Error: no")
        self.draws = 0
        self.marks: list[Any] = []
        self.scrolls: list[tuple[Any, ...]] = []
        self.debug = False

    def _maybe(self, call: str, ahead: int = 0) -> None:
        if self.fail == call and self.draws + ahead >= self.fail_at:
            raise self.error

    def set_marks(self, marks: Any = None) -> None:
        self._maybe("set_marks", 1)
        self.marks.append(marks)

    def scroll_to(self, *args: Any, **kwargs: Any) -> None:
        self._maybe("scroll_to", 1)
        self.scrolls.append((*args, kwargs))

    @property
    def stats(self) -> Any:
        self._maybe("stats")
        return None

    def draw(self, **kwargs: Any) -> bool:
        imgui = _imgui()
        self.draws += 1
        self._maybe("draw")
        imgui.dummy(imgui.ImVec2(kwargs["width_px"], 10.0))
        return True


def _on_a_fake_typeset_view(
    fail_at: int = 99, fail: str = "draw", error: Exception | None = None, timer: Any = None
) -> tuple[page.FindPage, _FakeTypeset]:
    """
    The page as it is built with the library, over a view that draws nothing.

    The index is the real one: `MarkdownConverter.describe` needs no library.
    """
    made = page.FindPage(_context("find:1"), GLUE)
    theme = made.context.theme
    described = MarkdownConverter(theme).describe(parse_markdown(GLUE, theme).blocks)
    fake = _FakeTypeset(described.texts, fail_at, fail, error)
    made.typeset, made.reason = fake, ""  # type: ignore[assignment]
    extra = {} if timer is None else {"timer": timer}
    made.finder = page.TypesetFinder(fake, FindIndex.of(described.blocks), **extra)
    made.finder.search(page.DEFAULT_NEEDLE)
    made.finder.keystrokes = 0
    return made, fake


def test_the_cost_of_a_search_is_split_into_finding_and_handing_over(unasked: None) -> None:
    made, fake = _on_a_fake_typeset_view(timer=_Clock())
    finder = made.finder
    finder.search("glue")
    finder.search("glu")
    assert finder.keystrokes == 2
    assert finder.search_ms == pytest.approx(1.0) and finder.mark_ms == pytest.approx(1.0)
    lines = page.typeset_readouts(finder, 0, None)
    assert lines[0].startswith(f"marked 4 of {len(finder.matches)} found")
    assert "table cells are searched and marked" in lines[0]
    assert "search 1.00 ms, marks 1.00 ms" in lines[1]
    assert "2 keystrokes: 0 edits of the document" in lines[1] and "nothing drawn yet" in lines[1]


def test_the_readouts_report_counts_and_judge_nothing(unasked: None) -> None:
    made, _ = _on_a_fake_typeset_view()
    text = " ".join(made.lines()).lower()
    for word in ("better", "worse", "good", "bad", "clean", "crisp", "smooth", "fast", "slow"):
        assert word not in text.split(), word


# ----------------------------------------------------------------------
# 2. Frames with no backend: one line saying why; the rest over a fake view
# ----------------------------------------------------------------------

_OWN: list[Any] = []


def _imgui() -> Any:
    imgui = pytest.importorskip("imgui_bundle").imgui
    if imgui.get_current_context() is None:
        imgui.create_context()
    return imgui


def _own_context() -> None:
    """
    An ImGui context of this test's own, left current for whoever runs next.

    Every other frame test in the suite shares whichever context is current,
    and that is not good enough here: the search box has the same id in every
    page, and ImGui keeps one text-edit state per context. Measured: a second
    page's box, focused after a first page's had been typed into, appended to
    the first's text instead of replacing its own. The contexts this module
    made earlier are destroyed, and nobody else's is touched.
    """
    imgui = _imgui()
    fresh = imgui.create_context()
    imgui.set_current_context(fresh)
    while _OWN:
        imgui.destroy_context(_OWN.pop())
    _OWN.append(fresh)


def _frame_of(made: page.FindPage, draw: Any = None) -> int:
    imgui = _imgui()
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(*SIZE)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(*SIZE))
        imgui.begin("##advtext-find-page-fake", None, imgui.WindowFlags_.no_title_bar.value)
        try:
            (made.draw if draw is None else draw)()
        finally:
            imgui.end()
    finally:
        imgui.render()
    return int(imgui.get_draw_data().total_vtx_count)


def _key(made: page.FindPage, key: Any, *, shift: bool = False) -> None:
    """
    Press and release one key, a frame each, with Shift held around it if asked.
    """
    imgui = _imgui()
    io = imgui.get_io()
    if shift:
        io.add_key_event(imgui.Key.mod_shift, True)
    io.add_key_event(key, True)
    _frame_of(made)
    io.add_key_event(key, False)
    if shift:
        io.add_key_event(imgui.Key.mod_shift, False)
    _frame_of(made)


def _type(made: page.FindPage, text: str) -> None:
    io = _imgui().get_io()
    for character in text:
        io.add_input_character(ord(character))
        _frame_of(made)


def test_without_the_library_the_page_is_one_line_saying_why(
    monkeypatch: pytest.MonkeyPatch, unasked: None
) -> None:
    """
    `set` is `make test TYPESET=1`'s case in this process: the variable is
    there, no fonts were loaded, and the page must not import the library to
    find that out. No box, no pane: the line and nothing else.
    """
    for variable in ("unset", "set"):
        for name in VARIABLES:
            monkeypatch.delenv(name, raising=False)
        if variable == "set":
            monkeypatch.setenv(VARIABLES[0], "/somewhere/lib.so")
        made = page.FindPage(_context("find:1"), GLUE)
        assert made.typeset is None and made.renderer == "none" and made.reason
        assert made.lines() == (f"imtypeset is not drawing: {made.reason}",)
        assert made.edits == 0 and len(made.finder.matches) == 4
        says_only_why_not(made.draw, made.reason)
        assert made.pane is None and made.vertices == 0 and not made.shown()
        (line,) = made.report()
        assert line.startswith("frames=1 renderer=none copies=1 blocks=4 needle='glue' marked=0 ")
        assert "found=4" in line


def test_the_typeset_finder_hands_plain_marks_over_once_per_change(unasked: None) -> None:
    made, fake = _on_a_fake_typeset_view()
    finder = made.finder
    # In prose twice (case ignored), in the code block, and in the last paragraph.
    assert [(m.block, fake.texts[m.block][m.start : m.end]) for m in finder.matches] == [
        (1, "glue"),
        (1, "Glue"),
        (2, "glue"),
        (3, "glue"),
    ]
    assert finder.label == "1 of 4" and finder.marked == 4 and finder.aligned
    assert len(fake.marks) == 1 and all(isinstance(mark, tuple) for mark in fake.marks[0])
    # The current match's mark is the stronger one, and the last (drawn over a neighbour's).
    assert [mark[1] for mark in fake.marks[0]] == [HIT_MARK, HIT_MARK, HIT_MARK, CURRENT_MARK]
    assert CURRENT_MARK != HIT_MARK

    _frame_of(made)
    _frame_of(made)
    assert len(fake.marks) == 1, "a frame hands nothing over"
    assert made.renderer == "TypesetView" and fake.draws == 2 and fake.scrolls == []

    made.step(1)
    assert len(fake.marks) == 2 and finder.label == "2 of 4"
    _frame_of(made)
    # The line holding the match's first character, a third of the way down.
    assert fake.scrolls == [(1, finder.match.start, {"align": page.SHOW_AT})]
    made.match_case(True)
    # The current match stays the first at or after where it was: the code block's.
    assert finder.label == "2 of 3" and not finder.ignore_case and finder.keystrokes == 1
    made.type("zzqq")
    assert finder.label == "no matches" and fake.marks[-1] == () and finder.keystrokes == 2
    made.type("")
    assert finder.label == "" and made.lines()[0].startswith("marked 0 of 0 found")
    assert len(made.lines()) == 2, "no line naming the renderer: there is one"


def test_an_index_that_is_not_the_views_marks_nothing_and_says_so(unasked: None) -> None:
    made, fake = _on_a_fake_typeset_view()
    made.finder = page.TypesetFinder(fake, made.finder.finder.index, aligned=False)
    made.finder.search("glue")
    assert made.finder.marked == 0 and fake.marks[-1] is None
    assert "not marked: the view's texts differ" in made.lines()[0]
    assert "aligned=0" in made.report()[0]


def test_typing_in_the_box_searches_and_hands_the_marks_over(unasked: None) -> None:
    """
    Real characters into the real `InputText`, a frame each.
    """
    _own_context()
    made, fake = _on_a_fake_typeset_view()
    _frame_of(made)
    _frame_of(made)
    handed = len(fake.marks)
    made.focus()
    _frame_of(made)
    _frame_of(made)
    # The box takes the keyboard with its text selected, so typing replaces it.
    _type(made, "last")
    finder = made.finder
    assert finder.needle == "last" and finder.keystrokes == 4
    assert len(finder.matches) == 1 and finder.label == "1 of 1"
    _key(made, _imgui().Key.backspace)
    assert finder.needle == "las" and finder.keystrokes == 5
    assert len(fake.marks) == handed + 5, "one handing over for each keystroke, none for a frame"
    assert made.edits == 0 and made.renderer == "TypesetView"


def test_enter_and_shift_enter_step_and_the_box_keeps_the_keyboard(unasked: None) -> None:
    _own_context()
    made, fake = _on_a_fake_typeset_view()
    imgui = _imgui()
    _frame_of(made)
    _frame_of(made)
    made.focus()
    _frame_of(made)
    _frame_of(made)
    _type(made, "glu")
    finder = made.finder
    count = len(finder.matches)
    assert count == 4 and finder.label == "1 of 4"
    _key(made, imgui.Key.enter)
    assert finder.label == "2 of 4"
    _key(made, imgui.Key.enter)
    _key(made, imgui.Key.keypad_enter)
    assert finder.label == "4 of 4"
    _key(made, imgui.Key.enter, shift=True)
    assert finder.label == "3 of 4"
    # Each step asked the view for the line of the match it went to.
    assert [scroll[:2] for scroll in fake.scrolls][-1] == (finder.match.block, finder.match.start)
    # Still typing into the box, and appending: Enter did not take the keyboard away.
    _frame_of(made)
    _type(made, "e")
    assert finder.needle == "glue"


def test_enter_does_nothing_while_the_box_does_not_have_the_keyboard(unasked: None) -> None:
    _own_context()
    made, _ = _on_a_fake_typeset_view()
    _frame_of(made)
    _frame_of(made)
    before = made.finder.label
    _key(made, _imgui().Key.enter)
    assert made.finder.label == before


@pytest.mark.parametrize("call", ["draw", "set_marks", "scroll_to", "stats"])
def test_a_typeset_view_that_fails_mid_run_leaves_the_page_alive_and_saying_why(
    call: str, unasked: None
) -> None:
    """
    `TypesetUnavailable` out of ANY view call of a frame does not leave `draw`
    (so it cannot reach the app's traceback page), and from the next frame on
    the page is the one line. The finder keeps the needle, the case rule, the
    matches and the count of keystrokes; it has no view to hand marks to.
    """
    _own_context()
    made, fake = _on_a_fake_typeset_view(fail_at=2, fail=call)
    made.match_case(True)
    made.type("Glue")
    _frame_of(made)
    assert (made.renderer, made.vertices) == ("TypesetView", 0)

    made.step(1)  # one match: the same one, and a scroll asked for in the frame that fails
    made.finder.finder.search("glue")  # and marks to hand over in it
    _frame_of(made)
    assert made.typeset is None and made.renderer == "none" and made.finder.view is None
    assert made.reason == "imtypeset failed and is switched off: Error: no"
    assert made.view_stats is None and not made.shown()
    finder = made.finder
    assert (finder.needle, finder.ignore_case, len(finder.matches)) == ("glue", False, 3)
    assert finder.keystrokes == 2 and finder.marked == 0
    draws = fake.draws
    says_only_why_not(made.draw, made.reason)
    assert fake.draws == draws and made.lines() == (f"imtypeset is not drawing: {made.reason}",)
    assert "renderer=none" in made.report()[0]
    # The state is still the page's: a search with no view raises nothing.
    made.type("glu")
    assert len(made.finder.matches) == 3


def test_an_exception_that_is_not_the_librarys_is_a_bug_and_propagates(unasked: None) -> None:
    _own_context()
    made, fake = _on_a_fake_typeset_view(fail_at=2, error=ZeroDivisionError("a bug in the page"))
    _frame_of(made)
    raised: list[BaseException] = []

    def draw() -> None:
        try:
            made.draw()
        except ZeroDivisionError as exc:
            raised.append(exc)

    _frame_of(made, draw)  # the frame still closes: the pane was ended on the way out
    assert len(raised) == 1 and made.typeset is fake and made.renderer == "TypesetView"


# ----------------------------------------------------------------------
# 3. With the library, real frames, no window
# ----------------------------------------------------------------------

_TYPESET = r"""
from advtext.ui.pages import find as page

app = App(source="# t\n\nx\n", columns_source="x\n", open_tab="find")
frame(app.gui, 2)
made = app._views["Find"]
view, finder = made.typeset, made.finder
report["renderer"] = made.renderer
report["open"] = fields(made.report()[0].replace(repr("glue"), "_"))
report["lines"] = list(made.lines())
report["finder"] = type(finder).__name__
report["matches_read_glue"] = all(
    view.texts[m.block][m.start:m.end].casefold() == "glue" for m in finder.matches
)
report["source_blocks"] = len(view.blocks)
with_needle = made.vertices

# What the index built from the VIEW's blocks finds, per needle (the test has the old totals).
report["copies"] = made.copies
report["totals"] = {
    needle: len(finder.finder.index.find(needle, ignore_case=True))
    for needle in ("glue", "the", "e", "Knuth", "hpack", "|", "zzqq", "The model", "a b")
}
report["tables"] = len(view.tables)

# The same frame at the same scroll with no needle has fewer vertices: marks are drawn.
finder.search("")
frame(app.gui, 2)
report["empty"] = [made.vertices, finder.marked, len(finder.matches)]
finder.search("glue")
frame(app.gui, 2)
report["needle_vertices"] = [with_needle, made.vertices]

# A match 400 lines into ONE code block: the line is what is brought into view.
# (Before anything is typed: the two pages' boxes have one id, and ImGui keeps
# one text-edit state per context, so a box that has the keyboard would type
# its text into this page's.)
long_text = "# Long\n\n```\n" + "\n".join(
    f"line {n} of the block" + (" needle" if n == 400 else "") for n in range(600)
) + "\n```\n\nafter\n"
deep = page.FindPage(context("find:1"), long_text)
frame(deep.draw, 2)
deep.type("needle")
frames_to_show = 0
while not deep.shown() and frames_to_show < 12:
    frame(deep.draw)
    frames_to_show += 1
frame(deep.draw, 6)
match = deep.finder.match
span = deep.finder.span_px()
block = deep.typeset.block_rect(match.block)
report["deep"] = {
    "renderer": deep.renderer, "found": len(deep.finder.matches), "block": match.block,
    "line_of_match": deep.typeset.texts[match.block][:match.start].count("\n"),
    "shown": deep.shown(), "frames": frames_to_show, "scrolls": deep.scrolls,
    "span": list(span), "pane": list(deep.pane), "origin": list(deep.typeset.origin),
    "block_height": block[3] - block[1],
}

# To the last match, several screens down, and back.
made.type("glue")
frame(app.gui, 6)
resting = list(view.origin)
report["first_shown"] = [made.shown(), made.scrolls]
made.step(-1)
report["last_is_current"] = finder.current == len(finder.matches) - 1
frames_to_show = 0
while not made.shown() and frames_to_show < 12:
    frame(app.gui)
    frames_to_show += 1
frame(app.gui, 6)   # the view looks again for a few frames; it must stay shown
report["last"] = {"shown": made.shown(), "frames": frames_to_show, "scrolls": made.scrolls,
                  "moved": resting[1] - view.origin[1], "span": list(finder.span_px()),
                  "rects": len(finder.rects())}
made.step(1)
frame(app.gui, 8)
report["first_again"] = [finder.current, made.shown(), list(view.origin) == resting]
report["edits"] = [made.edits, dict(view.edits)]
report["stats"] = list(made.view_stats)

made.type("knuth")
insensitive = len(finder.matches)
made.match_case(True)
report["case"] = [insensitive, len(finder.matches), finder.ignore_case]
made.match_case(False)
report["case_back"] = len(finder.matches) == insensitive

# The debug overlay is the shared flag.
plain = made.vertices
made.context.debug = True
frame(app.gui, 2)
report["debug"] = [view.debug, made.vertices > plain]
made.context.debug = False

# Real characters into the real InputText, a frame each. Last, because a box
# that has the keyboard answers with its own text whatever the page holds.
before = finder.keystrokes
made.focus()
frame(app.gui, 2)
for character in "hpack":
    io.add_input_character(ord(character))
    frame(app.gui)
report["typed"] = [finder.needle, finder.keystrokes - before, len(finder.matches), finder.label,
                   made.edits]
def key(which, shift=False):
    if shift:
        io.add_key_event(imgui.Key.mod_shift, True)
    io.add_key_event(which, True)
    frame(app.gui)
    io.add_key_event(which, False)
    if shift:
        io.add_key_event(imgui.Key.mod_shift, False)
    frame(app.gui)
key(imgui.Key.enter)
key(imgui.Key.enter)
key(imgui.Key.enter, shift=True)
report["entered"] = finder.label

# The library switched off under the page: it stays alive, is one line saying
# why, and the finder keeps what it held.
held = [finder.needle, finder.ignore_case, finder.keystrokes, len(finder.matches)]
switch_off("switched off by the test")
frame(app.gui)
report["after"] = [made.renderer, made.reason, made.typeset is None, made.finder is finder,
                   finder.view is None, dict(app.page_errors),
                   [finder.needle, finder.ignore_case, finder.keystrokes, len(finder.matches)]
                   == held]
frame(app.gui, 2)
report["later"] = [made.renderer, dict(app.page_errors), list(made.lines()),
                   only_the_line(made.draw, made.reason), made.reason]
"""


@pytest.fixture(scope="module")
def typeset() -> dict[str, Any]:
    return typeset_child(_TYPESET)


def test_with_the_library_every_match_is_a_mark_the_typeset_view_draws(
    typeset: dict[str, Any],
) -> None:
    opened = typeset["open"]
    assert typeset["renderer"] == "TypesetView" and typeset["finder"] == "TypesetFinder"
    # No line names the renderer any more: there is one. The first is the count.
    assert len(typeset["lines"]) == 2
    assert typeset["lines"][0] == (
        f"marked {opened['found']} of {opened['found']} found  ·  "
        "table cells are searched and marked  ·  formula source is not searched"
    )
    assert opened["aligned"] == "1" and int(opened["found"]) > 0
    # The old page's index found as many and could mark only those outside
    # table cells; its totals are `OLD_TOTALS`, frozen. Here every one is a mark.
    assert typeset["tables"] > 0 and typeset["copies"] == page.DEFAULT_COPIES
    assert typeset["totals"] == {needle: old for needle, (old, _) in OLD_TOTALS.items()}
    assert int(opened["found"]) == typeset["totals"]["glue"] == 55
    assert opened["marked"] == opened["found"] and opened["current"] == "1"
    assert opened["keystrokes"] == "0" and opened["edits"] == "0" and opened["whole"] == "1"
    assert typeset["matches_read_glue"] is True
    assert int(opened["blocks"]) == typeset["source_blocks"]
    # Marks are vertices: no needle draws fewer, the needle again draws what it drew.
    vertices, marked, found = typeset["empty"]
    assert (marked, found) == (0, 0)
    assert typeset["needle_vertices"][0] == typeset["needle_vertices"][1] > vertices


def test_with_the_library_the_box_enter_and_the_case_checkbox_work_as_before(
    typeset: dict[str, Any],
) -> None:
    needle, keystrokes, found, label, edits = typeset["typed"]
    assert (needle, keystrokes, edits) == ("hpack", 5, 0) and found > 0
    assert label == f"1 of {found}"
    assert typeset["entered"] == f"2 of {found}", "Enter, Enter, Shift+Enter"
    insensitive, sensitive, ignore_case = typeset["case"]
    assert insensitive > 0 and sensitive == 0 and ignore_case is False
    assert typeset["case_back"] is True
    assert typeset["debug"] == [True, True]


def test_with_the_library_a_step_brings_the_line_of_the_match_into_the_pane(
    typeset: dict[str, Any],
) -> None:
    """
    `scroll_to(block, offset)` is asked for the match's first character, and the
    view keeps correcting for a few frames while blocks are laid out for the
    first time: `scrolls` counts frames that moved the pane, not requests.
    """
    shown, scrolls = typeset["first_shown"]
    assert shown is True
    last = typeset["last"]
    assert typeset["last_is_current"] is True
    assert last["shown"] is True and 1 <= last["frames"] <= 12, last
    assert last["moved"] > 2 * 800.0 and last["scrolls"] > scrolls and last["rects"] >= 1
    current, shown, at_rest = typeset["first_again"]
    assert (current, shown, at_rest) == (0, True, True)
    # Nothing a search or a step does edits the document.
    edits, by_kind = typeset["edits"]
    assert edits == 0 and by_kind == {"set": 1, "replace": 0, "append": 0}


def test_with_the_library_a_match_deep_in_one_long_block_is_shown(
    typeset: dict[str, Any],
) -> None:
    """
    600 lines in one code block, the needle on line 400: the block is many
    panes tall, so bringing "the block" into view would show its top and not
    the match. What is shown is the match's own line.
    """
    deep = typeset["deep"]
    assert deep["renderer"] == "TypesetView" and deep["found"] == 1
    assert deep["line_of_match"] == 400
    pane_height = deep["pane"][1] - deep["pane"][0]
    assert deep["block_height"] > 5 * pane_height, deep
    assert deep["shown"] is True and deep["scrolls"] >= 1, deep
    top = deep["origin"][1] + deep["span"][0]
    assert deep["pane"][0] <= top <= deep["pane"][1]


def test_with_the_library_switched_off_mid_run_the_page_is_one_line_and_no_traceback(
    typeset: dict[str, Any],
) -> None:
    renderer, reason, dropped, same_finder, no_view, errors, kept = typeset["after"]
    assert (renderer, dropped, same_finder, no_view, errors) == ("none", True, True, True, {})
    assert "switched off by the test" in reason
    assert kept is True, "the needle, the case rule, the keystrokes and the matches stay"
    renderer, errors, lines, (drawn, line), reason = typeset["later"]
    assert (renderer, errors) == ("none", {})
    assert lines == [f"imtypeset is not drawing: {reason}"]
    assert drawn == line > 0, "the page is the one line and nothing else"


# ----------------------------------------------------------------------
# 4. The real app in a real window, with the library and without it
# ----------------------------------------------------------------------


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split() if "=" in part)


_WATCH = r"""
def watch(app, made, frame):
    if frame == 6:
        report["needle"] = made.report()[0]
        report["lines"] = list(made.lines())
        made.finder.search("")        # not `type`: nothing may scroll between the two counts
    elif frame == 10:
        report["empty"] = made.report()[0]
        made.type("glue")
        made.step(-1)                 # the last match, twenty samples down
    elif frame == 26:
        report["stepped"] = made.report()[0]
        finish()
"""


def test_in_a_real_window_with_the_library_the_typeset_path_marks_and_scrolls(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = windowed_typeset(window, monkeypatch, "find:20", _WATCH)
    assert report["current"] == "Find" and report["reason"] == "" and report["trouble"] == ""
    assert len(report["lines"]) == 2 and report["lines"][0].startswith("marked ")
    needle, empty, stepped = (
        _fields(report[moment].replace(repr("glue"), "_").replace(repr(""), "_"))
        for moment in ("needle", "empty", "stepped")
    )
    for moment in (needle, empty, stepped):
        assert moment["renderer"] == "TypesetView" and moment["copies"] == "20", moment
        assert moment["aligned"] == "1" and moment["edits"] == "0" and moment["whole"] == "1"
        assert int(moment["vertices"]) > 1000
    assert int(needle["found"]) > 100 and needle["marked"] == needle["found"]
    assert (empty["found"], empty["marked"]) == ("0", "0")
    assert needle["scrolls"] == empty["scrolls"] == "0"
    assert int(needle["vertices"]) > int(empty["vertices"])
    assert stepped["current"] == stepped["found"] == needle["found"]
    assert int(stepped["scrolls"]) >= 1 and stepped["shown"] == "1", report["stepped"]


def test_in_a_real_window_without_the_library_the_page_says_why_and_stays_up(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The plain gate's window: no view and a reason, the library never imported,
    nothing on the traceback page, and the search still found what it finds.
    """
    report = windowed_typeset(window, monkeypatch, "find:2", WATCH_WITHOUT, how="without")
    assert report["current"] == "Find" and report["reason"]
    assert report["renderer"] == "none" and report["typeset"] is True
    got = _fields(report["text"][0].replace(repr("glue"), "_"))
    assert got["renderer"] == "none" and got["copies"] == "2" and got["vertices"] == "0"
    assert got["found"] == "22" and got["marked"] == "0"

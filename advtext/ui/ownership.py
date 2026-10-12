r"""
What the views share that is not layout: whose selection is current, and four small things.

`SelectionOwnership` and the one `SELECTION_OWNERSHIP` counter of the process;
`MIN_WIDTH_PX`; `clipboard_text` and `CLIPBOARD_NUL`; `scroll_for`; and the two
numbers a pane follows a growing document's tail by, `FAR_PX` and
`AT_BOTTOM_PX`. **This module imports nothing of advtext**, so a view that
sets its text some other way (`advtext.ui.typeset_view`) takes its turns on
the same counter as `BareView` and `DiffView` without importing `BareView`.
`tests/test_typeset_closure.py` holds that.

All but the last two were defined in `advtext.ui.bare_view` until 2026-10-10
and are still importable from there: that module imports them from here, so
`advtext.ui.bare_view.SELECTION_OWNERSHIP is advtext.ui.ownership.SELECTION_OWNERSHIP`
-- one counter, which is the point of it. `FAR_PX` and `AT_BOTTOM_PX` are
stated in `advtext.ui.stream_view` too, with the reasons for their values;
the two statements are held equal by the test named above until that module
takes them from here.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AT_BOTTOM_PX",
    "CLIPBOARD_NUL",
    "FAR_PX",
    "MIN_WIDTH_PX",
    "SELECTION_OWNERSHIP",
    "SelectionOwnership",
    "clipboard_text",
    "scroll_for",
]

FAR_PX = 1.0e7
"""
A scroll position past the end of any pane: asking for it is asking for the end.
`advtext.ui.stream_view.FAR_PX` has the reasoning.
"""

AT_BOTTOM_PX = 1.0
"""
How close to the end of its scroll range a pane must be to count as "at the bottom".
`advtext.ui.stream_view.AT_BOTTOM_PX` has the reasoning.
"""

# Below this the line breaker has nothing to work with and every line is
# overfull. A window narrower than this is a window being resized through zero.
MIN_WIDTH_PX = 80.0


@dataclass(slots=True)
class SelectionOwnership:
    """
    Whose selection is current: a counter, bumped each time a view takes its turn.

    **Public for a widget of a host's own that has a selection** and wants to
    take turns with the views here, as `advtext.ui.diff_view.DiffView` does:
    call `take()` on `SELECTION_OWNERSHIP` when the widget's selection
    becomes the current one, keep the number, and answer Ctrl+C only while
    `holds(number)`. A second counter is the defect this exists to prevent --
    two panes both copying on one Ctrl+C.

    Module state, deliberately, and the only such state here. "Which view
    does Ctrl+C belong to" is a fact about the whole application and no one
    view can hold it; ImGui's own answer (keyboard focus) is not usable,
    because a view that submits no item cannot have it. A counter rather than
    a reference to the owning view, so that a view that has been dropped is
    not kept alive by having been the last one clicked in.

    One process, one current selection. Two ImGui contexts in one process
    share it, which is wrong for them and has not come up.
    """

    turn: int = 0

    def take(self) -> int:
        """
        Take the next turn: the number to keep, which is the current one until someone else takes.
        """
        self.turn += 1
        return self.turn

    def holds(self, taken: int) -> bool:
        """
        Whether the turn `taken` (from `take`) is still the current one. Zero never is.
        """
        return taken != 0 and taken == self.turn


SELECTION_OWNERSHIP = SelectionOwnership()
"""The one counter of this process. Every view here takes its turns on it."""

CLIPBOARD_NUL = "\u2400"
"""
What a NUL becomes on its way to the clipboard: U+2400, the picture of one.
"""


def clipboard_text(text: str) -> str:
    """
    `text` as it is handed to the clipboard: each NUL as `CLIPBOARD_NUL`.

    The clipboard is a C string, and a NUL ends one: a copy of
    `key = 'ab\\0cd'` and the line after it put `key = 'ab` on the clipboard
    and nothing else -- text that was never in the document, with no sign
    that anything was missing (review 3, item 9). So every text this module
    and `advtext.ui.diff_view` hand to `imgui.set_clipboard_text` goes
    through here, a host's own `copy(text)` and `copy_as` included.
    `selected_text()` is not changed: it returns the characters that are
    there, NUL and all, for a host that does something else with them.
    """
    return text.replace("\0", CLIPBOARD_NUL) if "\0" in text else text


def scroll_for(
    top: float,
    bottom: float,
    scroll: float,
    height: float,
    *,
    margin: float = 24.0,
    align: float | None = None,
    always: bool = False,
) -> float | None:
    """
    The scroll offset that brings `[top, bottom)` into a window, or `None` to stay put.

    All in pixels of the scrolled content: where the span is, how far the
    window is scrolled, and how tall the window is. The arithmetic behind
    `BareView.scroll_to`, separate because it is arithmetic.

    `None` when the span is already inside the window with `margin` to spare
    above and below, so stepping through places that are on screen moves
    nothing. Otherwise, with no `align`, the nearer edge: a span above comes
    to the top and a span below to the bottom, each `margin` in; a span
    taller than the window shows its top. With `align`, the span's top is put
    that fraction of the window's height down. Never above the start;
    whoever applies it clamps to the end.

    `always` moves a span that is already in view, to where `align` says.
    Without an `align` it changes nothing: the nearest place from which a
    visible span is visible is here.
    """
    if top - margin >= scroll and bottom + margin <= scroll + height:
        if not always or align is None:
            return None
    if align is not None:
        return max(top - align * height, 0.0)
    if top - margin < scroll or bottom - top + 2.0 * margin > height:
        return max(top - margin, 0.0)
    return max(bottom + margin - height, 0.0)

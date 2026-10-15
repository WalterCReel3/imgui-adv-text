r"""
Widgets a host draws inside a `TypesetView`: the protocol, and fenced diffs as one user of it.

**Experimental** (branch `experimental/imtypeset-adoption`). Nothing in imscribe
imports this module: a host asks for it by name.

`imscribe.ui.typeset_view.TypesetView` (and `TypesetStreamView`) take a
`host_for`: a callable `(view, number, block) -> Hosted | None`. A block it
answers for is not set as text. To the library it is a Host block, a rectangle
as tall as the widget says it is, holding the widget's `text` so that a copy
through it has it; the view hands the widget that rectangle at each draw.
`Hosted` and `HostFor` are defined beside the view (they are part of its
signature) and are re-exported here.

`TypesetDiffFences` is the `host_for` the Chat page needs: a fenced `diff` or
`patch` block drawn by an `imscribe.ui.typeset_diff_view.TypesetDiffView`,
growing a line at a time while its fence is still being written. It is
`imscribe.ui.diff_view.DiffFences` again, reading the same source spans by the
same rules (`_read` is that class's, statement for statement), over the typeset
views. **`imscribe.ui.typeset_diff_view` is imported when the first fence is
met**, not with this module, so a document with no diff never loads it. It is
the ONE reader of fenced diffs for the typeset views: a second, which
`imscribe.ui.typeset_diff_view` carried for a tranche (`FencedDiffs`), was
removed at T4-DIFF, and `HostedDiff` took the one thing of its that this
lacked, `handle_keys`. (What that one had and this does not: a `host(...)`
entry for a caller that is not a view, an info string accepted by `accepts`,
and `px_per_inch` passed on. Nothing in the tree called them.)

## What a hosted block is and is not, in a `TypesetView`

- **Its height is asked at every draw** (`height_for`), with the width of its
  rectangle, and given to the library when it changed (one call).
- **It is drawn only while its rectangle meets the window**; out of the window
  a widget with a `handle_keys()` is called through that instead. `HostedDiff`
  has one, so Ctrl+C still copies a selection made in a diff that has since
  been scrolled out of view (run in a real window: `tests/test_typeset_hosts.py`).
- **The mouse over it is its own**: the view makes no hit test there and begins
  no selection. A drag begun in the text goes on across it.
- **To selection and copy it is one atom**, as a table is: a drag takes none of
  it above its vertical middle and all of it below, and a copy that takes it
  has its `text`, a blank line apart from the text either side.
- `view.hosted(n)` is the widget for block `n`; `view.source_of(n)` and
  `view.block_source(n)` still name the fence, verbatim.

**Not here, and in `BareView`:** text in the window is not held in place when a
widget above the window changes height (the library estimates what it has not
laid out; its team has that as request C2). A fence in a list item or a quote
is read from the code block's own lines, not from the source, as there.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from imscribe.diff import Diff, UnifiedDiffStream
from imscribe.ui.palette import Palette
from imscribe.ui.typeset_view import Hosted, HostFor

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from imscribe.ui.typeset_view import TypesetView

__all__ = ["FENCE_LANGUAGES", "HostFor", "Hosted", "HostedDiff", "TypesetDiffFences"]

FENCE_LANGUAGES = ("diff", "patch")
"""
The first words of a fence's info string that `TypesetDiffFences` takes for a diff.
"""


class HostedDiff:
    """
    One fenced diff as a typeset view holds it: a `Hosted` around a `TypesetDiffView`.

    `view` is the `TypesetDiffView`, for a host that wants to drive it. `text`
    is the fence's body as read so far.
    """

    __slots__ = ("__weakref__", "fence", "stream", "view")

    def __init__(self, view: Any) -> None:
        self.view = view
        self.stream = UnifiedDiffStream()
        # How far `TypesetDiffFences` has read this fence. Kept here, on the
        # object the document view holds for the block: it then lives exactly
        # as long as the view shows it.
        self.fence: _Fence | None = None

    def height_for(self, width_px: float) -> float:
        return float(self.view.height_for(width_px))

    def draw(self, *, palette: Palette | None = None, width_px: float | None = None) -> object:
        return self.view.draw(palette=palette, width_px=width_px)

    def handle_keys(self) -> None:
        """
        What the document view calls on a frame the diff is out of its window
        (`Hosted`): Ctrl+C and Ctrl+A for a selection made in the diff, which
        `TypesetDiffView.draw` would otherwise have answered.
        """
        self.view.handle_keys()

    def headers(self, width_px: float | None = None) -> tuple[Any, ...]:
        """
        `TypesetDiffView.headers` of the view: each file's header as a
        `DiffHeader`, with whether it fit the width this fence was last drawn
        at (or `width_px`). A fenced diff carries no `will_not_apply`; its
        warnings are the reader's own (lines not read, control characters).
        """
        return tuple(self.view.headers(width_px))

    @property
    def text(self) -> str:
        return self.stream.text


class _Fence:
    """
    How far into one fence's source `TypesetDiffFences` has read.

    `start` is where the fence's first line begins in the source and `opener`
    is that line. `fed` is the offset of the first character not yet read, or
    -1 while the opening line has not ended, and `read` is the source from
    `start` to `fed` as it was read: a source that still holds it there is the
    same fence, read on from `fed`; one that does not (an edit inside the
    fence, a closed one included) is read again from its first line. `plain`
    marks a fence read from its code block because its source could not be.
    `theme` is the view's theme the widget was made with: the diff view fixes
    its sizes from it, so another theme is another widget.
    """

    __slots__ = (
        "closed",
        "fed",
        "hosted",
        "indent",
        "mark",
        "opener",
        "plain",
        "read",
        "start",
        "theme",
    )

    def __init__(
        self, hosted: HostedDiff, *, theme: object, start: int = -1, plain: bool = False
    ) -> None:
        self.hosted = hosted
        self.theme = theme
        self.start = start
        self.opener = ""
        self.read = ""
        self.fed = -1
        self.indent = 0
        self.mark = ""
        self.closed = False
        self.plain = plain


class TypesetDiffFences:
    """
    A `TypesetView.host_for` that draws fenced `diff` and `patch` blocks as diffs.

    The keyword arguments are `TypesetDiffView`'s and are given to each view
    as it is made; `layout`, `height_cap` and `syntax` may be changed
    afterwards and apply to the fences met from then on (`set_layout` also
    switches the ones already made). **`cell=` is deprecated, accepted and
    ignored** (a `DeprecationWarning`; a name that is neither `"font"` nor
    `"pixel"` is still a `ValueError`): since imtypeset 0.4 every diff is on
    the device's whole-pixel cell by default (`imscribe.ui.typeset_diff_view`,
    "The cell is the device's"), and the attribute `cell` is always
    `"pixel"`. `source` is the markdown the blocks were
    read from, or a callable giving it, for a view that does not hold it
    (one given blocks); a view given a string, and a stream view, are asked
    for their own.

    One instance serves any number of views: what it keeps is on each view's
    own hosted widgets.
    """

    def __init__(
        self,
        *,
        source: str | Callable[[], str] | None = None,
        languages: Sequence[str] = FENCE_LANGUAGES,
        layout: Any = None,
        height_cap: float | None = None,
        syntax: Any = None,
        pixel_height: float | None = None,
        expand_step: int = 20,
        cell: str | None = None,
    ) -> None:
        if cell is not None:
            # Here and not at the top: see `_hosted`. The check is the view's.
            from imscribe.ui.typeset_diff_view import cell_given

            cell_given(cell, "TypesetDiffFences")
        #: Deprecated: what `cell=` used to choose. Always the device's cell now.
        self.cell = "pixel"
        self.source = source
        self.languages = tuple(word.lower() for word in languages)
        self.layout = layout
        self.height_cap = height_cap
        self.syntax = syntax
        self.pixel_height = pixel_height
        self.expand_step = expand_step
        #: Diff lines read from fences, ever: one per line of a fence's body.
        self.fed_lines = 0
        #: Times a fence was read again from its first line.
        self.restarts = 0
        # Every hosted diff made and still held by some view. Weak: a view
        # that is gone takes its diffs with it.
        self._made: weakref.WeakSet[HostedDiff] = weakref.WeakSet()

    # -- what a host reaches for ------------------------------------------

    def view_of(self, view: TypesetView, number: int) -> Any:
        """
        The `TypesetDiffView` drawing block `number` of `view`, or `None` if it is not a diff.
        """
        hosted = view.hosted(number)
        if isinstance(hosted, HostedDiff) and hosted in self._made:
            return hosted.view
        return None

    @property
    def live(self) -> int:
        """How many hosted diffs this has made that some view still holds."""
        return len(self._made)

    def set_layout(self, layout: Any) -> None:
        """
        Unified or side by side, for every diff made so far and every one made later.
        """
        self.layout = layout
        for hosted in list(self._made):
            hosted.view.set_layout(layout)

    def accepts(self, block: object) -> bool:
        """
        Whether `block` is a fence this draws: a code block whose info string begins with one
        of `languages`.

        A code block of either vocabulary (`MarkdownCode`, or the old core's
        `CodeBlock`): anything that names a `language`.
        """
        language = getattr(block, "language", None)
        if not isinstance(language, str):
            return False
        words = language.split(None, 1)
        return bool(words) and words[0].lower() in self.languages

    # -- the hook ------------------------------------------------------------

    def __call__(self, view: TypesetView, number: int, block: object) -> HostedDiff | None:
        if not self.accepts(block):
            return None
        stream = getattr(view, "stream", None)
        source = self._source_of(view)
        where = view.source_of(number) if source is not None else None
        known = view.hosted(number)
        fence = known.fence if isinstance(known, HostedDiff) and known in self._made else None
        theme = getattr(view, "theme", None)
        if fence is not None and fence.theme is not theme and fence.theme != theme:
            # `set_theme`: the diff view took its sizes from the old one.
            self.restarts += 1
            fence = None

        if source is not None and where is not None:
            span = where.span
            if (
                fence is None
                or fence.plain
                or fence.start != span.start
                or fence.fed > span.end
                # A closed fence read to its end: one that reaches further now
                # is not the fence that closed (its last line was added to).
                or (fence.closed and fence.fed != span.end)
                # What was read, its opening line first, is still there: an
                # edit inside the fence, closed or not, is read again. (A
                # stream only grows, and keeps its widget.)
                or not source.startswith(fence.read, span.start)
            ):
                if fence is not None:
                    self.restarts += 1
                fence = _Fence(self._hosted(view), theme=theme, start=span.start)
            # Whether this is all the fence will ever be: then a last line
            # with no newline is a line, and not one still being typed.
            final = stream is None or stream.closed or number < len(stream.committed)
            self._read(fence, source, span.end, final)
            if fence.fed >= 0:
                fence.read = source[fence.start : fence.fed]
            if final or fence.closed:
                # Nothing more will come: a last line the parser was holding
                # for the line after it (`UnifiedDiffStream.close`) is settled.
                fence.hosted.stream.close()
        if fence is None or fence.plain or source is None or where is None:
            # No source to cut from: the code block's own lines as the view
            # described them, whole, every time. (A tab in these is a tab, as
            # in the source the other path cuts from, since 2026-10-12; until
            # then the reader had expanded it, counting the sign's column.)
            if fence is None or not fence.plain:
                fence = _Fence(self._hosted(view), theme=theme, plain=True)
            text = view.block_text(number)
            text = text + "\n" if text else ""
            before = fence.hosted.stream.text
            fence.hosted.stream.set_text(text)
            self.fed_lines += text.count("\n") - (
                before.count("\n") if text.startswith(before) else 0
            )
        fence.hosted.fence = fence
        self._made.add(fence.hosted)
        fence.hosted.view.set_diff(fence.hosted.stream.diff)
        return fence.hosted

    def _source_of(self, view: TypesetView) -> str | None:
        held = view.source
        if held is not None:
            return held
        if callable(self.source):
            return self.source()
        return self.source

    def _hosted(self, view: TypesetView) -> HostedDiff:
        # Here and not at the top: a document with no fenced diff never loads
        # the diff view.
        from imscribe.ui.typeset_diff_view import DiffLayout, TypesetDiffView

        return HostedDiff(
            TypesetDiffView(
                Diff(),
                view.theme,
                layout=DiffLayout.UNIFIED if self.layout is None else self.layout,
                pixel_height=self.pixel_height,
                syntax=self.syntax,
                height_cap=self.height_cap,
                expand_step=self.expand_step,
                palette=view.palette,
            )
        )

    def _read(self, fence: _Fence, source: str, end: int, final: bool) -> None:
        """
        Feed the fence's lines in `source[fence.fed:end]` to its diff, whole lines only.

        The opening line is read first, once it has ended: its indentation is
        what every later line loses (CommonMark's rule for an indented fence),
        and its run of backticks or tildes is what a closing line must match.
        A line is fed when its newline is in the source -- or, if `final`,
        when it is the last thing there.
        """
        if fence.fed < 0:
            stop = source.find("\n", fence.start, end)
            if stop < 0:
                return
            opener = source[fence.start : stop]
            bare = opener.lstrip(" ")
            mark = bare[:1]
            if mark not in ("`", "~") or not bare.startswith(mark * 3):
                # Not a fence on a line of its own: a list marker or a quote
                # mark comes first, and stripping those is markdown's job.
                fence.plain = True
                return
            fence.opener = opener
            fence.indent = len(opener) - len(bare)
            fence.mark = mark * (len(bare) - len(bare.lstrip(mark)))
            fence.fed = stop + 1
        if fence.closed or fence.fed >= end:
            return
        chunk = source[fence.fed : end]
        if not final:
            chunk = chunk[: chunk.rfind("\n") + 1]
        if not chunk:
            return
        fence.fed += len(chunk)
        lines: list[str] = []
        # Cut at "\n" and nowhere else, as `imscribe.diff` cuts: `splitlines`
        # also cuts at a form feed, U+2028 and five more.
        pieces = chunk.split("\n")
        tail = pieces.pop()
        cut = [piece + "\n" for piece in pieces] + ([tail] if tail else [])
        for at, line in enumerate(cut):
            body = line
            for _ in range(fence.indent):
                if not body.startswith(" "):
                    break
                body = body[1:]
            closing = body.strip()
            if (
                closing.startswith(fence.mark)
                and not closing.strip(fence.mark[0])
                and len(line) - len(line.lstrip(" ")) < fence.indent + 4
                and at == len(cut) - 1
                and fence.fed >= end
            ):
                # It looks like the closing fence, and it is the last line of
                # the block's source: markdown, which has already decided
                # where the block ends, is the judge of whether it *is*.
                # While the block is still being written the line is neither:
                # it is read again when more has arrived.
                if final:
                    fence.closed = True
                else:
                    fence.fed -= len(line)
                break
            lines.append(body)
        if lines:
            self.fed_lines += len(lines)
            fence.hosted.stream.feed("".join(lines))

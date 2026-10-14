r"""
A diff in a plain ImGui window, from the text before and the text after.

The smallest host use of the diff view, written to be read by someone
embedding it -- in particular by an application that approves edits before they
are made and has, at that moment, the file as it is and the file as it would
be.

**One view, drawn by the imtypeset library** (branch
`experimental/imtypeset-adoption`). The diff is drawn by
`imscribe.ui.typeset_diff_view.TypesetDiffView`, whose text is set and drawn by
the imtypeset library, and by nothing else: without the library this prints
one line to standard error, `imtypeset is not drawing: <the reason>`, and
exits with status 1, before any window opens. Everything is imported from the
package root, the module `typesetter` included. Run it with:

    pip install --pre imscribe                       # brings imtypeset where it has a wheel
    python examples/diff_minimal.py                  # one file, unified

    python examples/diff_minimal.py --side-by-side
    python examples/diff_minimal.py --edits          # several edits, one diff
    IMSCRIBE_NO_TYPESET=1 python examples/diff_minimal.py   # no library: says why and exits 1

(Nothing is set in the environment: since 2026-10-13 the installed imtypeset
wheel is found by itself. `examples/typeset_minimal.py` says what a developer
building imtypeset from source does instead.)

## The three steps

1. **Make the model.** `Diff.from_texts(before, after, label)` when the host
   holds both whole texts (`None` for a side that does not exist: a new file,
   a deleted one). `Diff.from_edits([(old, new, label), ...])` when it holds
   several replacements, each of which becomes a file of the diff -- a
   multi-part edit. Both are pure: no window, no font, and they can be made on
   another thread or cached beside the request they describe.
2. **Make the view, once the fonts are loaded.** `make_view` below:
   `TypesetDiffView(diff, theme)`. It keeps the scroll offsets, the selection
   and what it has handed the library, so it is made once and kept, not
   rebuilt each frame. `view.set_diff(other)` replaces what it shows;
   `view.set_layout(DiffLayout.SIDE_BY_SIDE)` switches form. `make_view`
   raises `TypesetUnavailable` until the fonts are loaded.
3. **Draw it, every frame.** `view.draw(palette=palette)` at the cursor of
   whatever window is current. It claims its own space, handles the mouse
   (drag to select, Ctrl+C to copy, click a collapsed region to expand it)
   and draws only the rows on screen. It answers a `bool`: whether everything
   in view was set as asked (the library counts no glyphs). It raises
   `TypesetUnavailable` when the library cannot draw (its fonts were never
   loaded, or it failed and was switched off) and has then drawn nothing:
   this example says why and closes (`main`, below). Nothing else is caught.

## Why the texts and not a unified diff

A host that has the texts should hand them over and not a unified string made
from them (`Diff.from_unified` exists for text that only ever was a diff: a
fenced block in a chat, `git` output). From the texts the view can expand
collapsed context, and a text with no final newline is described correctly;
`difflib.unified_diff` over lines kept with their ends runs such a last line
into the next one, and nothing reading the result can undo that
(`imscribe.diff`, `Diff.from_unified`, has the example).

## Two things a host has to get right

**The palette.** A plain ImGui window is dark, and `DEFAULT_PALETTE` is ink
for a light page. `DARK_PALETTE` carries a dark `DiffPalette` as its `.diff`;
a host with colours of its own builds a `DiffPalette` and puts it in a
`Palette`. The `+` and `-` in the gutter are drawn whatever the colours are --
they are the channel that does not depend on hue -- and are never selected or
copied.

**Fonts are loaded once, when the atlas is built.** `typesetter.load_fonts()`
at the end of the host's `load_additional_fonts` gives the library its faces;
it answers False, and `typesetter.reason()` or `trouble()` says why, when it
could not.

## What has been run, and what has not

`tests/test_examples.py` builds both diffs and runs `main` in a real window
where one can be opened (an Xvfb in a user namespace, where this was written):
with the library when the suite is run with it, and without, where it must
exit 1 with the reason. **Nobody has looked at it**: the tests say rows were
drawn and that the library set everything in view as asked, and say nothing
about how the result reads.
"""

from __future__ import annotations

import argparse
import sys

from imscribe import (
    DARK_PALETTE,
    Diff,
    DiffLayout,
    Palette,
    Theme,
    TypesetDiffView,
    TypesetUnavailable,
    typesetter,
)

WINDOW_TITLE = "imscribe: a diff"
NOT_DRAWING = "imtypeset is not drawing"

LABEL = "greet.py"

BEFORE = '''\
"""Greet people."""

import sys


def greet(name):
    print("Hello, " + name)


def main():
    for name in sys.argv[1:]:
        greet(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

AFTER = '''\
"""Greet people."""

import sys


def greet(name, greeting="Hello"):
    print(f"{greeting}, {name}!")


def main():
    for name in sys.argv[1:]:
        greet(name)
    if len(sys.argv) < 2:
        greet("world")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

EDITS: tuple[tuple[str, str, str], ...] = (
    ("def greet(name):\n", 'def greet(name, greeting="Hello"):\n', "edit 1"),
    ('    print("Hello, " + name)\n', '    print(f"{greeting}, {name}!")\n', "edit 2"),
    ("    return 0", "    return 0  # always", "edit 3"),
)
"""
Three replacements as an editing tool states them: old string, new string, a
label. The last has no final newline on either side, which is the case a
unified string made by `difflib` gets wrong and `Diff.from_edits` does not.
"""


def text_diff(before: str | None = BEFORE, after: str | None = AFTER, label: str = LABEL) -> Diff:
    """
    The diff a host makes when it holds the whole file before and after.

    `before=None` is a file that does not exist yet and `after=None` one that
    is being deleted; the diff says so in the file's status.
    """
    return Diff.from_texts(before, after, label)


def edits_diff(edits: tuple[tuple[str | None, str | None, str], ...] = EDITS) -> Diff:
    """
    One diff from several `(old, new, label)` replacements, a file of the diff each.
    """
    return Diff.from_edits(edits)


def make_view(
    diff: Diff, *, side_by_side: bool = False, theme: Theme | None = None
) -> TypesetDiffView:
    """
    The view for `diff`. Made once and kept: it holds the scroll and the selection.

    Made once the fonts are loaded: it raises `TypesetUnavailable` until
    `typesetter.load_fonts()` has succeeded (`typesetter.ready()`), and does
    not ask for the library itself before that -- so calling it in a process
    that never loaded the fonts imports nothing.
    """
    if not typesetter.ready():
        why = typesetter.reason() or typesetter.trouble() or "its fonts were not loaded"
        raise TypesetUnavailable(f"{NOT_DRAWING}: {why}")
    theme = theme or Theme.build()
    layout = DiffLayout.SIDE_BY_SIDE if side_by_side else DiffLayout.UNIFIED
    return TypesetDiffView(diff, theme, layout=layout)


def show(view: TypesetDiffView, palette: Palette = DARK_PALETTE) -> bool:
    """
    Draw the diff in the current window, between its `begin` and `end`.

    One call: the view takes the width the window has left, claims the height
    it needs and handles its own mouse and keys. True when everything in view
    was set as asked. Raises `TypesetUnavailable` when the library cannot
    draw, having drawn nothing.
    """
    return view.draw(palette=palette)


def refuse(reason: str) -> int:
    """
    Say on standard error why nothing is drawn; the exit status of a run that drew nothing.
    """
    print(f"{NOT_DRAWING}: {reason}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the diff in it. Needs a display and the imtypeset library.

    `--frames N` closes the window after N frames and prints what the last one
    drew; it is how this is run unattended. Returns 0 after drawing, and 1
    (with the reason on standard error) when the library is not in use, has
    no fonts, or stopped drawing.
    """
    parser = argparse.ArgumentParser(description="A diff in a plain ImGui window.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--side-by-side", action="store_true", help="two columns, not one")
    parser.add_argument("--edits", action="store_true", help="several edits as one diff")
    args = parser.parse_args(argv)

    # Before any window: is the library in use at all?
    if typesetter.module() is None:
        return refuse(typesetter.reason())

    from imgui_bundle import hello_imgui, imgui, immapp

    diff = edits_diff() if args.edits else text_diff()
    theme = Theme.build()
    views: list[TypesetDiffView] = []  # made on the first frame: the fonts are loaded by then
    drawn: list[bool] = []
    failed: list[str] = []
    rows = [0]

    def stop(reason: str) -> None:
        failed.append(reason)
        hello_imgui.get_runner_params().app_shall_exit = True

    def load_fonts() -> None:
        # The runner's own default first, so the window's widgets keep it.
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        # Then the library's faces. False, and `reason()` says why, when it could not.
        typesetter.load_fonts()

    def gui() -> None:
        if failed:
            return
        if not typesetter.ready():
            stop(typesetter.reason() or typesetter.trouble() or "its fonts were not loaded")
            return
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size(imgui.ImVec2(860.0, 560.0), imgui.Cond_.first_use_ever)
        if imgui.begin(WINDOW_TITLE):
            imgui.text(f"{len(diff.files)} file(s)  +{diff.added} -{diff.removed}")
            try:
                if not views:
                    views.append(make_view(diff, side_by_side=args.side_by_side, theme=theme))
                drawn.append(show(views[-1]))
            except TypesetUnavailable as exc:
                # The library cannot draw (any more), and that call drew nothing.
                stop(str(exc).removeprefix(f"{NOT_DRAWING}: "))
        imgui.end()
        if args.frames and len(drawn) >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    def before_exit() -> None:
        if views:
            rows[0] = views[-1].row_count
        # imtypeset's context goes before the Dear ImGui context does.
        typesetter.unload()

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (900, 600)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    # An example should not leave an .ini beside wherever it was launched from.
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    params.callbacks.before_exit = before_exit
    immapp.run(params)

    if failed:
        return refuse(failed[0])
    if drawn:
        view = views[-1]
        print(
            f"frames={len(drawn)} layout={view.layout.name} files={len(diff.files)} "
            f"added={diff.added} removed={diff.removed} rows={rows[0]} "
            f"renderer={type(view).__name__} answered={int(drawn[-1])}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

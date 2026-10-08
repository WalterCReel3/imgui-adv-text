r"""
A diff in a plain ImGui window, from the text before and the text after.

The smallest host use of `advtext.DiffView`, written to be read by someone
embedding it -- in particular by an application that approves edits before they
are made and has, at that moment, the file as it is and the file as it would
be. Everything used is importable from the package root:

    from advtext import Diff, DiffView, Theme, DARK_PALETTE, load_faces

**It imports no `advtext` submodule**, and `tests/test_examples.py` reads this
file's imports to hold it to that. Run it with:

    python examples/diff_minimal.py                  # one file, unified
    python examples/diff_minimal.py --side-by-side
    python examples/diff_minimal.py --edits          # several edits, one diff

## The three steps

1. **Make the model.** `Diff.from_texts(before, after, label)` when the host
   holds both whole texts (`None` for a side that does not exist: a new file,
   a deleted one). `Diff.from_edits([(old, new, label), ...])` when it holds
   several replacements, each of which becomes a file of the diff -- a
   multi-part edit. Both are pure: no window, no font, and they can be made on
   another thread or cached beside the request they describe.
2. **Make the view, once.** `DiffView(diff, theme)`. It keeps the scroll
   offsets, the selection and what it has measured, so it is made when the
   diff is and kept, not rebuilt each frame. `view.set_diff(other)` replaces
   what it shows; `view.set_layout(DiffLayout.SIDE_BY_SIDE)` switches form.
3. **Draw it, every frame.** `view.draw(fonts=fonts, palette=palette)` at the
   cursor of whatever window is current. It claims its own space, handles the
   mouse (drag to select, Ctrl+C to copy, click a collapsed region to expand
   it) and draws only the rows on screen.

## Why the texts and not a unified diff

A host that has the texts should hand them over and not a unified string made
from them (`Diff.from_unified` exists for text that only ever was a diff: a
fenced block in a chat, `git` output). From the texts the view can expand
collapsed context, and a text with no final newline is described correctly;
`difflib.unified_diff` over lines kept with their ends runs such a last line
into the next one, and nothing reading the result can undo that
(`advtext.diff`, `Diff.from_unified`, has the example).

## Two things a host has to get right

**The palette.** A plain ImGui window is dark, and `DEFAULT_PALETTE` is ink
for a light page. `DARK_PALETTE` carries a dark `DiffPalette` as its `.diff`;
a host with colours of its own builds a `DiffPalette` and puts it in a
`Palette`. The `+` and `-` in the gutter are drawn whatever the colours are --
they are the channel that does not depend on hue -- and are never selected or
copied.

**Fonts are loaded once, when the atlas is built.** A diff is set in the
theme's code face; `load_faces()` with no arguments loads it.

## What has been run, and what has not

`tests/test_examples.py` builds both diffs, draws the view in a real ImGui
frame with the real fonts, and runs `main` in a real window where one can be
opened (an Xvfb in a user namespace, where this was written). **Nobody has
looked at it**: the tests say rows were drawn and none of their glyphs was
missing, and say nothing about how the result reads.
"""

from __future__ import annotations

import argparse

from advtext import (
    DARK_PALETTE,
    Diff,
    DiffLayout,
    DiffView,
    DrawStats,
    LoadedFaces,
    Palette,
    Theme,
    load_faces,
)

WINDOW_TITLE = "advtext: a diff"

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


def make_view(diff: Diff, *, side_by_side: bool = False, theme: Theme | None = None) -> DiffView:
    """
    The view for `diff`. Made once and kept: it holds the scroll and the selection.
    """
    layout = DiffLayout.SIDE_BY_SIDE if side_by_side else DiffLayout.UNIFIED
    return DiffView(diff, theme or Theme.build(), layout=layout)


def show(view: DiffView, fonts: LoadedFaces, palette: Palette = DARK_PALETTE) -> DrawStats:
    """
    Draw the diff in the current window, between its `begin` and `end`.

    One call: the view takes the width the window has left, claims the height
    it needs and handles its own mouse and keys.
    """
    return view.draw(fonts=fonts, palette=palette)


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the diff in it. Needs a display.

    `--frames N` closes the window after N frames and prints what the last one
    drew; it is how this is run unattended.
    """
    parser = argparse.ArgumentParser(description="A diff in a plain ImGui window.")
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--side-by-side", action="store_true", help="two columns, not one")
    parser.add_argument("--edits", action="store_true", help="several edits as one diff")
    args = parser.parse_args(argv)

    from imgui_bundle import hello_imgui, imgui, immapp

    diff = edits_diff() if args.edits else text_diff()
    view = make_view(diff, side_by_side=args.side_by_side)
    loaded: list[LoadedFaces] = []
    drawn: list[DrawStats] = []

    def load_fonts() -> None:
        # The runner's own default first, so the window's widgets keep it.
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        loaded.append(load_faces())

    def gui() -> None:
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size(imgui.ImVec2(860.0, 560.0), imgui.Cond_.first_use_ever)
        if imgui.begin(WINDOW_TITLE):
            imgui.text(f"{len(diff.files)} file(s)  +{diff.added} -{diff.removed}")
            drawn.append(show(view, loaded[-1]))
        imgui.end()
        if args.frames and len(drawn) >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

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
    immapp.run(params)

    if drawn:
        last = drawn[-1]
        print(
            f"frames={len(drawn)} layout={view.layout.name} files={len(diff.files)} "
            f"added={diff.added} removed={diff.removed} rows={view.row_count} "
            f"glyphs={last.glyphs} missing={last.missing}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

r"""
`demo/sample.md` in a `TypesetView`: markdown source in, drawn by the imtypeset library.

**Experimental**, with `imscribe/ui/typeset_view.py` and `imscribe/typesetter.py`
(branch `experimental/imtypeset-adoption`). It is the smallest program that
shows what a host does to draw through the imtypeset library:

    make typeset-lib                       # once: builds the sidecar library
    IMTYPESET_LIBRARY=<the library it built, in $PWD/build/imtypeset-bundle> \
    IMTYPESET_PYTHON=$PWD/build/imtypeset-bundle/pysnap \
    python examples/typeset_minimal.py

(The library's file name is the build's and differs by platform; `make
typeset-lib` says where it installed the pair.)

    python examples/typeset_minimal.py     # no library: says why, exits 1, opens no window

**There is no other renderer.** Without the library the example prints one
line to standard error, `imtypeset is not drawing: <the reason>`, and exits
with status 1.

Everything is imported from the package root, the module `typesetter`
included.

## The three things a host does

1. **Ask for the library, before any window.** `typesetter.module()` is the
   import; `None` means it is not in use and `typesetter.reason()` says why.
2. **Fonts.** At the end of its `load_additional_fonts`, after its own faces:
   `typesetter.load_fonts()`. True when the library has a context and its
   faces; `typesetter.ready()` says the same afterwards.
3. **Make the view and draw it.** `TypesetView(markdown, theme=..., palette=...)`
   takes the markdown SOURCE: the view reads it
   (`imscribe.typeset_markdown`), nothing is converted by the host. `math=True`
   turns `$...$` on. `view.draw(...)` at the cursor of the current window,
   every frame. Both raise `TypesetUnavailable` when the library cannot draw
   (it failed and was switched off); a draw that raised has drawn nothing.
   This example then says why and closes.

Before exit, and before the Dear ImGui context goes, `typesetter.unload()`.

`--frames N` closes the window after N frames and prints one line of counts;
`tests/test_typeset_view.py` runs it with the library and without. Nobody has
looked at what it draws.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from imscribe import DARK_PALETTE, Theme, TypesetUnavailable, TypesetView, typesetter

WINDOW_TITLE = "imscribe: typeset, minimal"
SAMPLE = Path(__file__).resolve().parent.parent / "demo" / "sample.md"
NOT_DRAWING = "imtypeset is not drawing"


def refuse(reason: str) -> int:
    """
    Say on standard error why nothing is drawn; the exit status of a run that drew nothing.
    """
    print(f"{NOT_DRAWING}: {reason}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """
    Open a window with the document in it. Needs a display and the imtypeset library.

    Returns 0 after drawing, and 1 (with the reason on standard error) when
    the library is not in use, has no fonts, or stopped drawing.
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--frames", type=int, default=0, help="exit after this many frames")
    parser.add_argument("--file", type=Path, default=SAMPLE, help="the markdown file to show")
    args = parser.parse_args(argv)

    # Step 1, before any window: is the library in use at all?
    if typesetter.module() is None:
        return refuse(typesetter.reason())

    from imgui_bundle import hello_imgui, imgui, immapp

    source = args.file.read_text(encoding="utf-8")
    theme = Theme.build()
    views: list[TypesetView] = []  # one view, made on the first frame: the fonts are loaded by then
    frames = [0]
    failed: list[str] = []

    def stop(reason: str) -> None:
        failed.append(reason)
        hello_imgui.get_runner_params().app_shall_exit = True

    def load_fonts() -> None:
        hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
        # Step 2. Last, so `Fonts[0]` stays the window's own.
        typesetter.load_fonts()

    def gui() -> None:
        if failed:
            return
        if not typesetter.ready():
            stop(typesetter.reason() or typesetter.trouble() or "its fonts were not loaded")
            return
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size(imgui.ImVec2(720.0, 820.0), imgui.Cond_.first_use_ever)
        if imgui.begin(WINDOW_TITLE):
            # The scrollbar is always there, so the measure does not change
            # (and every block re-break) on the frame it would first appear.
            imgui.begin_child(
                "##text",
                imgui.ImVec2(0.0, 0.0),
                imgui.ChildFlags_.always_use_window_padding.value,
                imgui.WindowFlags_.always_vertical_scrollbar.value,
            )
            try:
                # Step 3: the markdown source goes to the view as it is.
                if not views:
                    views.append(TypesetView(source, theme=theme, palette=DARK_PALETTE, math=True))
                views[-1].draw(palette=DARK_PALETTE)
                frames[0] += 1
            except TypesetUnavailable as exc:
                # Nothing was drawn or claimed by that call.
                stop(str(exc))
            finally:
                imgui.end_child()
        imgui.end()
        if args.frames and frames[0] >= args.frames:
            hello_imgui.get_runner_params().app_shall_exit = True

    params = hello_imgui.RunnerParams()
    params.app_window_params.window_title = WINDOW_TITLE
    params.app_window_params.window_geometry.size = (760, 860)
    params.imgui_window_params.default_imgui_window_type = (
        hello_imgui.DefaultImGuiWindowType.no_default_window
    )
    params.ini_disable = True
    params.callbacks.load_additional_fonts = load_fonts
    params.callbacks.show_gui = gui
    blocks = [0]

    def before_exit() -> None:
        if views:
            blocks[0] = len(views[-1].texts)
        # imtypeset's context goes before the Dear ImGui context does.
        typesetter.unload()

    params.callbacks.before_exit = before_exit
    immapp.run(params)

    if failed:
        return refuse(failed[0])
    print(f"frames={frames[0]} renderer=TypesetView blocks={blocks[0]}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

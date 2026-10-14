# imscribe

Markdown, streaming and diff views for [Dear ImGui](https://github.com/ocornut/imgui)
in Python: paragraphs justified and broken into lines the way TeX breaks
them, headings, lists, tables, fenced code, formulas written as `$...$`,
text that arrives a piece at a time, side-by-side and unified diffs,
selection and copying. You hand a view markdown source and call `draw` each
frame, inside your own window.

The text is set and drawn by [imtypeset](https://pypi.org/project/imtypeset/),
a C++ library that binds to the Dear ImGui inside the
[`imgui-bundle`](https://pypi.org/project/imgui-bundle/) wheel. imscribe is the
Python layer over it: it reads the markdown, describes it to the library, and
is the views. There is no other renderer in it: where imtypeset is not
installed a view draws nothing and says why.

**This is a beta** (`0.2.0b1`), installed only when asked for:

```
pip install --pre imscribe
```

## Two pins, held together

imscribe requires both of these exactly, and they move together:

```
imgui-bundle==1.92.900
imtypeset==0.4.1.192900
```

An imtypeset wheel is built for one `imgui-bundle` version and its fourth
number says which (`192900` is `1.92.900`). So imscribe cannot be installed
beside anything that needs another `imgui-bundle`. An application that pins
its own dependencies pins these two with it.

## Where it runs

Anywhere `imgui-bundle` 1.92.900 does, as far as installing goes. It DRAWS
where imtypeset has a wheel:

| | CPython |
|---|---|
| Linux x86-64, glibc 2.28 or later | 3.11, 3.12, 3.13, 3.14 |
| macOS 14 or later on Apple Silicon | 3.11, 3.12, 3.13, 3.14 |

Not Windows, not Linux on arm64, not macOS on Intel: there `pip install
imscribe` succeeds without imtypeset, `imscribe.typesetter.kind()` answers
`Kind.NOT_INSTALLED`, and nothing is drawn. On Linux with musl (Alpine), with
a glibc older than 2.28, and on macOS older than 14, the install fails at
imtypeset, which has no wheel that fits; `imgui-bundle` has none for an old
glibc or an old macOS either.

On Linux, `imgui-bundle`'s extension module loads `libX11.so.6` and
`libXext.so.6` from the system when it is imported (read from the 1.92.900
wheel's binaries); neither is in a wheel. On Debian and Ubuntu they are the
packages `libx11-6` and `libxext6`. imtypeset's library asks the system for
nothing beyond the C and C++ runtimes.

## Using it

```python
from imgui_bundle import hello_imgui, immapp
from imscribe import DARK_PALETTE, Theme, TypesetView, typesetter

SOURCE = "# Hello\n\nSome *markdown*, set in lines of even colour, and $e^{i\\pi} + 1 = 0$."
assert typesetter.module() is not None, typesetter.reason()  # before any window
views = []

def fonts():
    hello_imgui.imgui_default_settings.load_default_font_with_font_awesome_icons()
    typesetter.load_fonts()  # last, after the application's own fonts

def gui():
    if not views:  # on the first frame: the fonts are loaded by then
        views.append(TypesetView(SOURCE, theme=Theme.build(), palette=DARK_PALETTE, math=True))
    views[0].draw(palette=DARK_PALETTE)

params = hello_imgui.RunnerParams()
params.callbacks.load_additional_fonts = fonts
params.callbacks.show_gui = gui
params.callbacks.before_exit = typesetter.unload  # before Dear ImGui's context goes
immapp.run(params)
```

Where no imtypeset was found, the `assert` stops with `IMTYPESET_LIBRARY is
not set`. That is the sentence for "there is no imtypeset here": on a platform
outside the table above there is nothing to set, and the variable is only how
a developer names a library built from source.

`TypesetStreamView` takes text as it arrives (`append`), and `TypesetDiffView`
two texts or a unified diff. `python -m imscribe.typesetter` prints, with no
window, which imtypeset was found and whether it was accepted.

## What is not known

- **Nobody but its author has looked at what it draws.** The tests measure
  where text is placed and that frames are drawn; none of them judges how it
  looks.
- **macOS has not been run.** imtypeset's wheels pass their own installed
  checks on GitHub's macOS arm64 runners (three of that project's 55 tests
  fail there, by its own notes); imscribe itself has never run on a Mac.
- Everything was measured on Linux x86-64, CPython 3.11, with a software
  renderer and a display scale of 1.

## More

The repository has the examples, the demo application, the tests and the
notes on every decision: <https://github.com/WalterCReel3/imscribe>

MIT licence. The fonts the views set text in are not in this package: they
ship in the `imgui-bundle` wheel under their own licences.

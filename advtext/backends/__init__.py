"""
The two things that draw. Nothing in here is imported by anything in the layout core.

`advtext.shipout` produces a flat list of absolute-positioned `DrawCmd`s, and a
backend's whole job is to blit them. Neither backend knows what a box, a glue
node or a breakpoint is, and neither imports the other.

- `svg` emits real glyph outlines through fontTools. It needs no GPU, no display
  and no ImGui, which is why it is the backend the litmus tests are *shown* with
  in an environment that cannot open a window. It is not a fallback.
- `imgui_draw` issues `ImDrawList` calls and is the real target. It cannot be run
  here at all -- see `docs/decisions.md`.

There is no barrel: import the backend you want. A package that imported both
would pull ImGui into every SVG render and defeat the separation the two
backends exist to demonstrate.
"""

from __future__ import annotations

"""
advtext -- TeX's box-and-glue layout model, rendered by Dear ImGui.

A document is a tree of boxes, glue, kerns and penalties. `hpack` and `vpack`
measure it, a total-fit line breaker over badness and demerits cuts it into
lines, and ship-out flattens the result to absolute glyph positions. Because we
own every position, hit testing is arithmetic rather than a missing widget
feature -- selectable text is the return on doing layout from scratch.

The layout core imports neither ImGui nor fontTools. It consumes a metrics
interface and emits draw commands; an SVG backend and an ImDrawList backend
consume those. A layout two unrelated backends can render has had its geometry
separated from its drawing, which is the property selection depends on.

Deliberately out of scope, so nobody looks for them: hyphenation, `ext_tag`
extensible glyph assembly, delta nodes in `try_break`, `\\mathchoice`, `\\halign`,
ligature reconstruction, page breaking, bidi, complex shaping and CJK line
breaking. `docs/decisions.md` gives the reason for each, along with the
environment constraints that forced the two-backend split, and it is the
document every module here is written against.

No re-export barrel: import from the module that defines the thing.
"""

from __future__ import annotations

__all__: list[str] = []

r"""
The colours a view draws in, and the count of what a draw call managed.

`Palette`, `DiffPalette`, their four shipped values, `rgba` and `DrawStats`.
They are data: nothing here draws, measures or lays out, and **this module
imports nothing of advtext when it is imported**, so a view that sets its text
some other way (`advtext.ui.typeset_view`) can state its colours without
loading the Python draw backend and what that stands on.
`tests/test_typeset_closure.py` holds that.

They were defined in `advtext.backends.imgui_draw` until 2026-10-10 and are
still importable from there: that module imports them from here, so
`advtext.backends.imgui_draw.Palette is advtext.ui.palette.Palette`. The
docstrings below still say "this backend" where they describe what
`advtext.backends.imgui_draw` does with a colour; that is the backend meant.

One import is deferred: `Palette.with_roles` needs `advtext.theme.BlockKind`
to refuse a role for a rule, and takes it when called. A caller that has a
`BlockKind` to pass has loaded `advtext.theme` already, so calling it loads
nothing. (It read the enum from `advtext.style` until 2026-10-11: the same
object, behind the measuring half of that module and what that stands on.)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    from advtext.theme import BlockKind

__all__ = [
    "DARK_DIFF_PALETTE",
    "DARK_PALETTE",
    "DEFAULT_DIFF_PALETTE",
    "DEFAULT_PALETTE",
    "DiffPalette",
    "DrawStats",
    "Palette",
    "rgba",
]


def rgba(red: int, green: int, blue: int, alpha: int = 255) -> int:
    """
    Pack a colour the way `IM_COL32` does: alpha, blue, green, red, low byte first.

    Written out rather than taken from ImGui so this module's colours can be
    stated at import time without a live context, and so a test could check them.
    The byte order is ImGui's and is not RGBA despite the name of the macro.
    """
    return (alpha << 24) | (blue << 16) | (green << 8) | red


@dataclass(frozen=True, slots=True)
class DiffPalette:
    """
    The colours of a diff: what `advtext.ui.diff_view.DiffView` draws in.

    Here, beside `Palette` and reached through `Palette.diff`, so that a host
    still states its whole theme in one object and a view still reads no colour
    from anywhere else. Nothing in this module draws a diff; the roles are data.

    **Colour is never the only channel.** An added and a removed line differ in
    ink and in fill, and both of those are hue. What tells them apart without
    it is the `+` or `-` the view always draws in the gutter, in `gutter` ink,
    which is the same in both: pptmstr keeps the marker for exactly this reason
    (its design section 6.1). So nothing here has to survive a greyscale
    conversion, and no claim is made that it does.

    - `add`, `remove`, `context`, `meta`: ink for the text of a line of that
      kind. `meta` is the "no newline at end of file" marker line.
    - `add_fill`, `remove_fill`: the band behind a whole added or removed
      line. Translucent in the defaults, so they tint whatever the host's
      background is rather than replacing it.
    - `add_emphasis`, `remove_emphasis`: the mark behind the part of a line
      that changed, drawn over the fill.
    - `gutter`: line numbers and the `+`/`-` marker.
    - `header`, `header_fill`: a file's or a hunk's header line and the band
      behind it; a collapsed-context line uses them too.
    - `warning`: the "will not apply" label and the other warnings on a file
      header, and the placeholder drawn for a character that cannot be drawn
      as itself -- which can stand anywhere a character can, an emphasis mark
      included.
    - `current`: the bar beside the hunk `next_hunk`/`previous_hunk` is on.

    The defaults are for the light page `Palette()` assumes. The values are
    stated, not recommended: nobody has judged how they look. **One thing
    about them is measured**: in both shipped palettes every ink is at least
    4.5 to 1 (WCAG 2's ratio) against every ground the view draws it on --
    the page, a band over the page, an emphasis mark over its band
    (`tests/test_imgui_draw.py` computes it from the palette; the table of
    which ink meets which ground is there). Until review 3 the gutter's
    marker was 3.91 on the light removed band and the warning ink 2.24 on a
    light emphasis mark. A host that changes a fill should run the same
    arithmetic. Added and removed lines are still nearly the same grey as
    each other, which is the first paragraph's point and is unchanged.
    """

    add: int = rgba(0x11, 0x4B, 0x1F)
    remove: int = rgba(0x7A, 0x12, 0x12)
    context: int = rgba(0x11, 0x11, 0x11)
    meta: int = rgba(0x5E, 0x5E, 0x5E)
    add_fill: int = rgba(0x2E, 0xA0, 0x43, 0x30)
    remove_fill: int = rgba(0xD7, 0x3A, 0x49, 0x30)
    add_emphasis: int = rgba(0x2E, 0xA0, 0x43, 0x66)
    remove_emphasis: int = rgba(0xD7, 0x3A, 0x49, 0x66)
    gutter: int = rgba(0x5E, 0x5E, 0x5E)
    header: int = rgba(0x1D, 0x4E, 0xD8)
    header_fill: int = rgba(0x3B, 0x82, 0xF6, 0x1F)
    warning: int = rgba(0x66, 0x2E, 0x05)
    current: int = rgba(0x3B, 0x82, 0xF6)


DEFAULT_DIFF_PALETTE = DiffPalette()
"""
The diff colours for a light page. A named constant for the reason
`DEFAULT_PALETTE` is one.
"""


DARK_DIFF_PALETTE = DiffPalette(
    add=rgba(0xAF, 0xF5, 0xB4),
    remove=rgba(0xFF, 0xD3, 0xCE),
    context=rgba(0xE6, 0xE6, 0xE6),
    meta=rgba(0xA2, 0xA2, 0xA2),
    add_fill=rgba(0x2E, 0xA0, 0x43, 0x38),
    remove_fill=rgba(0xF8, 0x51, 0x49, 0x38),
    add_emphasis=rgba(0x2E, 0xA0, 0x43, 0x80),
    remove_emphasis=rgba(0xF8, 0x51, 0x49, 0x80),
    gutter=rgba(0xA2, 0xA2, 0xA2),
    header=rgba(0x8A, 0xB4, 0xF8),
    header_fill=rgba(0x3B, 0x82, 0xF6, 0x2E),
    warning=rgba(0xFA, 0xDA, 0xAA),
    current=rgba(0x8A, 0xB4, 0xF8),
)
"""
The diff colours for a dark background: light inks, the same translucent fills
a little stronger. `DARK_PALETTE.diff` is this.
"""


@dataclass(frozen=True, slots=True)
class Palette:
    """
    Every colour this backend can emit, so none of them is buried in a call.

    **`ink` is dark because `page` is light, and a caller that draws the glyphs
    without also drawing the page gets black text on whatever was behind it.**
    ImGui's default theme is dark, so that failure is invisible text rather than
    an error. The pair is the unit; overriding one without the other is the bug
    it is easiest to write here. `advtext.ui.bare_view.BareView` paints no page
    at all, so a host using it supplies ink for *its* background: `DARK_PALETTE`
    is one such, and `Palette(ink=..., rule=..., highlight=...)` is the general
    form.

    The defaults are paper rather than the surrounding chrome being made light.
    That keeps the demo matching the SVG artifacts exactly -- the same ink on
    the same white, so a screenshot and an artifact can be compared -- and it
    is what a document viewer looks like: dark chrome around a light page.

    ## Ink per block role

    `ink` is what every glyph is drawn in unless its block's role says
    otherwise. `roles` holds the otherwise: one colour per `BlockKind` -- each
    heading level, a quote, code, a table, a list item -- for the kinds a host
    wants to differ. Build it with `with_roles`; read it with `ink_for`.

    **The role is the block's, and the colour is applied by the caller of
    `draw_runs`, not carried on a glyph.** `advtext.shipout.Glyph` has no colour
    and gains none: a view that lays a document out as per-block units
    (`advtext.ui.units`) already knows which commands are which block's, and
    hands each run of them over with its ink. So a role's ink covers a whole
    unit. A block quote is one unit however many paragraphs it holds, and takes
    the ink of its first block.

    `rule` colours every rule: a thematic break, the bar down a quote, the line
    under a table's header. `highlight` is the selection. `link` is the ink for
    link text, which nothing in this module draws yet -- it is here so that a
    host states its whole theme in one place and the view that draws links
    reads it from the same one.

    Stored as a tuple of pairs rather than a dict so that a `Palette` stays
    hashable and cannot be edited behind a view that holds it.

    The debug colours carry the same association the SVG backend uses: stretched
    glue reads cool and shrunk glue reads warm, so an overfull line is spottable
    across a page rather than only in a number.
    """

    page: int = rgba(0xFA, 0xFA, 0xF8)
    ink: int = rgba(0x11, 0x11, 0x11)
    rule: int = rgba(0x11, 0x11, 0x11)
    highlight: int = rgba(0x3B, 0x82, 0xF6, 0x4D)
    debug_box: int = rgba(0x22, 0xC5, 0x5E, 0x80)
    debug_baseline: int = rgba(0xEF, 0x44, 0x44, 0x80)
    debug_stretched: int = rgba(0x3B, 0x82, 0xF6, 0x66)
    debug_shrunk: int = rgba(0xF9, 0x73, 0x16, 0x66)
    link: int = rgba(0x1D, 0x4E, 0xD8)
    roles: tuple[tuple[BlockKind, int], ...] = ()
    # The colours of a diff, for `advtext.ui.diff_view.DiffView`; see
    # `DiffPalette`. Like `ink` it is one half of a pair with the background,
    # so a palette for a dark pane names `DARK_DIFF_PALETTE` (or its own).
    diff: DiffPalette = DEFAULT_DIFF_PALETTE

    def ink_for(self, kind: BlockKind) -> int:
        """
        The ink for a block of this kind: its role's if one was given, else `ink`.
        """
        for role, colour in self.roles:
            if role is kind:
                return colour
        return self.ink

    def with_roles(self, roles: Mapping[BlockKind, int]) -> Palette:
        """
        This palette with the given kinds drawn in the given inks.

        Added to whatever roles it already has, the new ones winning. A kind
        not named keeps `ink`. `BlockKind.RULE` is refused rather than ignored:
        a thematic break has no glyphs, its colour is `rule`, and a role that
        silently did nothing is how a host ends up with a black line on a dark
        pane.
        """
        from advtext.theme import BlockKind  # deferred: see the module docstring

        if BlockKind.RULE in roles:
            raise ValueError("a rule has no ink; set `rule` to colour thematic breaks and bars")
        merged = dict(self.roles)
        merged.update(roles)
        ordered = tuple(sorted(merged.items(), key=lambda item: item[0].value))
        return replace(self, roles=ordered)


DEFAULT_PALETTE = Palette()
"""
The palette a caller gets by omitting one.

A module constant rather than a default argument of `Palette()`: an instance
built in a signature is built once at import and shared, which is harmless for a
frozen value and is exactly the pattern `B008` exists to stop people relying on.
Naming it says the sharing is deliberate.
"""


DARK_PALETTE = Palette(
    page=rgba(0x1E, 0x1E, 0x1E),
    ink=rgba(0xE6, 0xE6, 0xE6),
    rule=rgba(0x8A, 0x8A, 0x8A),
    highlight=rgba(0x3B, 0x82, 0xF6, 0x66),
    link=rgba(0x8A, 0xB4, 0xF8),
    diff=DARK_DIFF_PALETTE,
)
"""
Light ink for a dark background, with no role inks.

The counterpart of `DEFAULT_PALETTE` for a host whose pane is dark, and the
palette the tests draw with to show that nothing in the draw path assumes a
light page: every colour `draw_runs` emits is read from the palette it is given.
`page` is what `DocumentView` would fill its sheet with; `BareView` never reads
it. The values are stated, not recommended -- which dark theme a host wants is
the host's to say, and it says it by building its own `Palette`.
"""


@dataclass(frozen=True, slots=True)
class DrawStats:
    """
    What one `draw` call managed, so a caller can say what it could not do.

    `missing` counts glyphs the bound face has no raster for, which in this
    project means the synthetic codepoints from a `MATH` variant chain. Counting
    them is the difference between a demo that admits the display sigma is absent
    and one that quietly shows a gap.
    """

    glyphs: int = 0
    missing: int = 0
    rules: int = 0

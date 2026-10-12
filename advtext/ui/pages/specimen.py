"""
The Specimen page: imtypeset's own specimen, shown as a page of this demo.

**Experimental** (branch `experimental/imtypeset-adoption`, tranche 4). The
specimen, the formula gallery and the math page are the typesetting library's
to show (`.concerns/lead--tranche-4.md`, decision 2), so the three pages
`specimen.py`, `formula.py` and `mathtext.py` build nothing: each draws one
section of the library's demo,
`imtypeset.demo.show_demo_section(DemoSection.<name>)`, into a child window.
`SectionPage` below is what the three share; it is in this module because the
three page modules are the only files of the pages package that change held.

## When the library is not drawing

There is no other body (the pages' old bodies, `_old_specimen.py`,
`_old_formula.py` and `_old_mathtext.py`, were deleted in tranche 5). Decided
when the page is built, as `advtext/ui/pages/typeset.py` does:

- `advtext.typesetter.ready()` true (the app's font callback loaded the
  library's fonts) and the loaded library has the section: the section.
- Otherwise the page draws ONE wrapped line of text and nothing else
  (`advtext.ui.pages.typeset.say_why_not`): that imtypeset is not drawing, and
  `reason`.

The page asks `ready()` first and `module()` only when that was true, so
building it never imports the library (`advtext/ui/pages/typeset.py` has the
reason: the library is kept out of the pytest process).

`ready()` going false later (a view switched the library off, or the context
was unloaded) makes the page that one line from that frame on, for good: the
section is not looked up again. So does a `TypesetUnavailable` out of the
frame, from the next frame. **Any other exception out of the section is not
caught here**: it reaches `advtext.ui.app.App._draw_page`, which puts ImGui's
stacks back, shows the traceback in the page's place and fails an unattended
run. A section that raised may have left a child or a font pushed, and the
app's recovery is the one that is measured.

## The size

A section sets its running text at the size ImGui's text has where it is
called, so the call is wrapped in `imgui.push_font(None, size_px)`. The size
is the theme's body size in pixels, which is the size the other pages set
prose at. ImGui's own labels inside the section grow with it; that is the
section's contract (`../imtypeset/docs/advtext-swap-status.md`, "Galleries").
The faces are the ones `advtext.typesetter.load_fonts` gave the library: the
section adds none.

## What the header row does not have

A *debug overlay* checkbox: the specimen is paragraphs and widgets of the
library, which have no overlay. `--tab specimen:debug` is still accepted (the
option is every page's) and changes nothing here.

## What the readout is

Counts of the last frame, from `imtypeset.stats()` read before and after the
section: paragraphs the library drew, vertices it emitted, layouts it made.
Nothing here says how the section looks, and nobody has looked at it.
"""

from __future__ import annotations

import importlib
from typing import Any, ClassVar, Final

from advtext import typesetter
from advtext.primitives import px_from_sp
from advtext.theme import BlockKind
from advtext.ui.pages import PageContext, PageSpec, caption
from advtext.ui.pages.typeset import FONTS_NOT_LOADED, not_drawing, say_why_not, why_not
from advtext.ui.typeset_view import TypesetUnavailable

__all__ = [
    "FONTS_NOT_LOADED",
    "PAGE",
    "STAT_NAMES",
    "SectionPage",
    "SpecimenPage",
    "why_not",
]

STAT_NAMES: Final = (
    ("paragraphs", "DrawCalls"),
    ("vertices", "VerticesEmitted"),
    ("layouts", "Layouts"),
)
"""
`(what the readout calls it, the field of imtypeset.stats())`, in the order shown.
"""


class SectionPage:
    """
    One section of imtypeset's demo as a page.

    A subclass names the section (`SECTION`, a member of
    `imtypeset.demo.DemoSection` by name) and the child window's id (`CHILD`).

    `renderer` is `"section"` while the library draws it and `"none"` when
    nothing does; `reason` is then why, and the one line the page draws.
    `counts` holds the last frame's figures by the names of `STAT_NAMES`, all
    zero when there is no section.
    """

    SECTION: ClassVar[str]
    CHILD: ClassVar[str]

    def __init__(self, context: PageContext) -> None:
        self.context = context
        # Scaled points are whole, so the stock 16 px comes back as 15.9999976;
        # rounded, so that the size pushed is the size the readout names.
        self.size_px: float = round(
            px_from_sp(context.theme.style(BlockKind.PARAGRAPH).font.size, context.px_per_inch), 3
        )
        self.frames = 0
        self.counts: dict[str, int] = {name: 0 for name, _ in STAT_NAMES}
        self.title = ""
        """The section's title as the library gives it; empty when there is no section."""
        self._demo: Any = None
        self._section = 0
        self.reason = why_not()
        if not self.reason:
            self.reason = self._find_section()

    @property
    def renderer(self) -> str:
        return "section" if self._demo is not None else "none"

    def _find_section(self) -> str:
        """
        Look the section up in the loaded library; the reason it cannot be shown, or empty.
        """
        ts = typesetter.module()
        if ts is None:
            return typesetter.reason() or FONTS_NOT_LOADED
        try:
            demo = importlib.import_module(f"{ts.__name__}.demo")
            section = int(getattr(demo.DemoSection, self.SECTION))
            title = str(demo.section_name(section))
        except Exception as exc:  # noqa: BLE001 -- any failure here means "no section"
            return f"imtypeset's demo is not usable: {type(exc).__name__}: {exc}"
        if not title:
            return f"the loaded imtypeset library has no demo section {self.SECTION}"
        self._demo, self._section, self.title = demo, section, title
        return ""

    def _give_up(self, reason: str) -> None:
        """
        The library is not drawing any more: no section from here on, and why.
        """
        self._demo = None
        self.title = ""
        self.counts = {key: 0 for key, _ in STAT_NAMES}
        self.reason = reason or "imtypeset is not ready"

    def report(self) -> list[str]:
        """
        What an unattended run prints: counts, and the reason when nothing draws.
        """
        counts = " ".join(f"{name}={self.counts[name]}" for name, _ in STAT_NAMES)
        line = (
            f"frames={self.frames} renderer={self.renderer} section={self.SECTION} "
            f"size={self.size_px:.2f} {counts}"
        )
        if self._demo is None:
            line += f" reason={self.reason!r}"
        return [line]

    def line(self) -> str:
        """
        The caption over the section: what draws it, at what size, and the last frame's counts.

        The one "why not" line when there is no section.
        """
        if self._demo is None:
            return not_drawing(self.reason)
        counts = ", ".join(f"{self.counts[name]} {name}" for name, _ in STAT_NAMES)
        return (
            f"imtypeset.demo section {self.title!r} at {self.size_px:.0f} px  ·  "
            f"last frame: {counts}"
        )

    def draw(self) -> None:
        self.frames += 1
        if self._demo is not None and not typesetter.ready():
            self._give_up(why_not())
        if self._demo is None:
            say_why_not(self.reason)
            return
        try:
            self._draw_section()
        except TypesetUnavailable as exc:
            self._give_up(str(exc))

    def _draw_section(self) -> None:
        from imgui_bundle import imgui

        ts = typesetter.module()
        caption(self.line())
        imgui.separator()
        visible = imgui.begin_child(self.CHILD, imgui.ImVec2(0.0, 0.0), imgui.ChildFlags_.borders)
        try:
            if visible:
                before = ts.stats()
                # The section sets its text at the size ImGui's own text has here.
                imgui.push_font(None, self.size_px)
                try:
                    self._demo.show_demo_section(self._section)
                finally:
                    imgui.pop_font()
                after = ts.stats()
                self.counts = {
                    name: int(getattr(after, field) - getattr(before, field))
                    for name, field in STAT_NAMES
                }
        finally:
            imgui.end_child()


class SpecimenPage(SectionPage):
    """
    The Specimen page: `DemoSection.Specimen`.
    """

    SECTION = "Specimen"
    CHILD = "##advtext-specimen"


PAGE = PageSpec(
    name="Specimen",
    order=30,
    factory=SpecimenPage,
    group="Typesetting",
    caption="every face at one size, one face at every size, and the kerning",
)

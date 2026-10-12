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
when the page is built, as `imscribe/ui/pages/typeset.py` does:

- `imscribe.typesetter.ready()` true (the app's font callback loaded the
  library's fonts) and the loaded library has the section: the section.
- Otherwise the page draws ONE wrapped line of text and nothing else
  (`imscribe.ui.pages.typeset.say_why_not`): that imtypeset is not drawing, and
  `reason`.

The page asks `ready()` first and `module()` only when that was true, so
building it never imports the library (`imscribe/ui/pages/typeset.py` has the
reason: the library is kept out of the pytest process).

`ready()` going false later (a view switched the library off, or the context
was unloaded) makes the page that one line from that frame on, for good: the
section is not looked up again. So does a `TypesetUnavailable` out of the
frame, from the next frame. **Any other exception out of the section is not
caught here**: it reaches `imscribe.ui.app.App._draw_page`, which puts ImGui's
stacks back, shows the traceback in the page's place and fails an unattended
run. A section that raised may have left a child or a font pushed, and the
app's recovery is the one that is measured.

## The size

A section sets its running text at the size ImGui's text has where it is
called, so the call is wrapped in `imgui.push_font(None, size_px)`. ImGui's
own labels inside the section grow with it; that is the section's contract
(`../imtypeset/docs/advtext-swap-status.md`, "Galleries"). The faces are the
ones `imscribe.typesetter.load_fonts` gave the library: the section adds none.

**The reader picks the size**: a combo over the section, *text size*, of
`SIZES` (14, 16, 19, 23, 28 px), opening at `DEFAULT_SIZE`, 23. It is the
page's state: it lasts as long as the page object does, `report()` and the
caption name it, and `set_size` is what the combo calls. `--tab math:19`
opens the page at 19 (the integer every page accepts; one that is not in
`SIZES` is the nearest that is, the larger on a tie, and one above the
largest is refused by `PageSpec.max_count` before a window opens). `SIZES`
are pixels at 96 to the inch; `size_px`, what is pushed, is the choice times
the context's density over 96.

**Two lengths are called a size, and the numbers below are why 23.** The
size pushed is ImGui's: the height of a line of the Regular face. The library
makes an em of it through that face (`resolve_style` in the library's
`imtypeset.cpp`): em = size x 2048 / 2400 for Roboto. The Document page sets
its body at an EmSize of 16 px instead. A formula is set at the paragraph's em
in Latin Modern Math, whose x-height is 0.431 em where Roboto's is 0.528. So,
from the font files (`.concerns/T6-SIZE-scripts/xheights.py`):

| pushed | em | text x-height | formula x-height |
|---|---|---|---|
| Document page (em 16) | 16.00 | 8.45 px | 6.90 px |
| 16 (until T6-SIZE) | 13.65 | 7.21 px | 5.89 px |
| 19 (18.75 is em 16) | 16.21 | 8.57 px | 6.99 px |
| 23 (22.98 is the crossing) | 19.63 | 10.37 px | 8.46 px |

23 is the smallest whole size at which a formula's x-height is not below the
x-height of the Document page's running text; 19 is where the section's text
is the Document's size of type. The other three are a step of about 1.2 down
and up from those.

**A combo and not a slider**, because every size on the way costs a layout of
every paragraph of the section and a raster of every glyph in it, and a
dragged slider visits them all; a combo visits one.

**What does not follow it.** The section's own sliders are the section's:
*Width* (Math; pixels, so a larger size is fewer characters to the line),
the Specimen's two *EmSize* sliders (faces, kerning rows) and the Formula
gallery's *EmSize*. What they set is unchanged by this control; their labels
and the running text and notes around them are what grow.

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

from imscribe import typesetter
from imscribe.primitives import DEFAULT_PX_PER_INCH
from imscribe.ui.pages import PageContext, PageSpec, caption
from imscribe.ui.pages.typeset import FONTS_NOT_LOADED, not_drawing, say_why_not, why_not
from imscribe.ui.typeset_view import TypesetUnavailable

__all__ = [
    "DEFAULT_SIZE",
    "FONTS_NOT_LOADED",
    "PAGE",
    "SIZES",
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

SIZES: Final = (14.0, 16.0, 19.0, 23.0, 28.0)
"""
The sizes the reader picks from, in pixels at 96 to the inch. The module docstring has why these.
"""

DEFAULT_SIZE: Final = 23.0
"""
The size a page opens at: the smallest at which a formula's x-height is the Document text's.
"""


def nearest_size(wanted: float) -> float:
    """
    The member of `SIZES` closest to `wanted`; the larger of two equally close.
    """
    return min(reversed(SIZES), key=lambda size: abs(size - wanted))


class SectionPage:
    """
    One section of imtypeset's demo as a page.

    A subclass names the section (`SECTION`, a member of
    `imtypeset.demo.DemoSection` by name), the child window's id (`CHILD`) and
    the page it is (`NAME`, its `PageSpec.name`: whose launch integer it reads).

    `size` is the member of `SIZES` the section's text is set at and `size_px`
    what is pushed for it; `set_size` changes both.

    `renderer` is `"section"` while the library draws it and `"none"` when
    nothing does; `reason` is then why, and the one line the page draws.
    `counts` holds the last frame's figures by the names of `STAT_NAMES`, all
    zero when there is no section.
    """

    SECTION: ClassVar[str]
    CHILD: ClassVar[str]
    NAME: ClassVar[str]

    def __init__(self, context: PageContext) -> None:
        self.context = context
        self.size: float = DEFAULT_SIZE
        self.size_px: float = 0.0
        asked = context.count_for(self.NAME)
        self.set_size(DEFAULT_SIZE if asked is None else nearest_size(float(asked)))
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

    def set_size(self, size: float) -> None:
        """
        Set the section's text at `size`, one of `SIZES`, from the next call of the section.
        """
        if size not in SIZES:
            raise ValueError(f"{size!r} is not one of the sizes {SIZES}")
        self.size = float(size)
        self.size_px = round(self.size * self.context.px_per_inch / DEFAULT_PX_PER_INCH, 3)

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
        self._size_control()
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

    def _size_control(self) -> None:
        """
        The combo of `SIZES`. Opened and closed here, before the section's child is begun.
        """
        from imgui_bundle import imgui

        picked: float | None = None
        imgui.set_next_item_width(imgui.get_font_size() * 6.0)
        if imgui.begin_combo("text size", f"{self.size:.0f} px"):
            try:
                for size in SIZES:
                    if imgui.selectable(f"{size:.0f} px", size == self.size)[0]:
                        picked = size
            finally:
                imgui.end_combo()
        if picked is not None:
            self.set_size(picked)


class SpecimenPage(SectionPage):
    """
    The Specimen page: `DemoSection.Specimen`.
    """

    SECTION = "Specimen"
    CHILD = "##imscribe-specimen"
    NAME = "Specimen"


PAGE = PageSpec(
    name="Specimen",
    order=30,
    factory=SpecimenPage,
    group="Typesetting",
    max_count=int(SIZES[-1]),
    caption="every face at one size, one face at every size, and the kerning",
)

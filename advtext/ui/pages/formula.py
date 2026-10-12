"""
The Formula page: imtypeset's formula gallery, shown as a page of this demo.

**Experimental** (branch `experimental/imtypeset-adoption`, tranche 4). The
eleven plates are the library's now: `imtypeset.demo.DemoSection.Formulas`,
drawn by `advtext.ui.pages.specimen.SectionPage`, whose module docstring says
which body draws, at what size, and what the readout is.

While `advtext.typesetter.ready()` is false the page is one line saying why
(`SectionPage`).

## What the header row does not have

A *debug overlay* checkbox (the gallery's panels are the library's
paragraphs, which have no overlay), and warnings about a codepoint the math
face lacks or a glyph missing from ImGui's atlas: the library's public
interface answers neither question for a gallery it draws itself.
"""

from __future__ import annotations

from advtext.ui.pages import PageSpec
from advtext.ui.pages.specimen import SIZES, SectionPage

__all__ = ["PAGE", "FormulaPage"]


class FormulaPage(SectionPage):
    """
    The Formula page: `DemoSection.Formulas`.
    """

    SECTION = "Formulas"
    CHILD = "##advtext-formula"
    NAME = "Formula"


PAGE = PageSpec(
    name="Formula",
    order=40,
    factory=FormulaPage,
    group="Typesetting",
    max_count=int(SIZES[-1]),
    caption="imtypeset's gallery of TeX math-mode rules",
)

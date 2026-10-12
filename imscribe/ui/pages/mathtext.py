r"""
The Math page: imtypeset's math section, shown as a page of this demo.

**Experimental** (branch `experimental/imtypeset-adoption`, tranche 4).
Formulas in running text, in a heading, a list and a quotation, a stream fed
three bytes at a time, the table of the subset and the list of refusals are
the library's now: `imtypeset.demo.DemoSection.Math`, drawn by
`imscribe.ui.pages.specimen.SectionPage`, whose module docstring says which
body draws, at what size, and what the readout is.

While `imscribe.typesetter.ready()` is false the page is one line saying why
(`SectionPage`).

## What the page does not have

- A *debug overlay* checkbox and a *measure* slider in the header row. The
  section has a Width slider of its own, and a debug checkbox for the one
  part of it that is a document. The header row's one control is the *text
  size* combo every section page has (`SectionPage`, "The size"): the section
  has no size control of its own, and everything in it follows the size
  pushed around it.
- **A `done` option.** `--tab math:done` used to open the page's old body
  with its stream fed to the end. The section keeps its stream's state inside
  the library and offers no way to set it from outside, so the option and the
  second photograph it made were dropped with the old body (tranche 5):
  `math:done` is now refused as an unknown option, and the page has one shot.
"""

from __future__ import annotations

from imscribe.ui.pages import PageSpec
from imscribe.ui.pages.specimen import SIZES, SectionPage

__all__ = ["PAGE", "MathPage"]


class MathPage(SectionPage):
    """
    The Math page: `DemoSection.Math`.
    """

    SECTION = "Math"
    CHILD = "##imscribe-math"
    NAME = "Math"


PAGE = PageSpec(
    name="Math",
    order=60,
    factory=MathPage,
    group="Typesetting",
    max_count=int(SIZES[-1]),
    title="Math in text",
    caption="inline and display formulas from a $...$ subset, in running text and in a stream",
)

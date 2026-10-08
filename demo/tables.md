# Tables you can pull about

Every table on this page has a handle on the right edge of each column. Put the
mouse on one, press, and drag: the column is set to the width you give it and
its cells are broken again as paragraphs of that width. A handle between two
columns moves the boundary and leaves the table as wide as it was; the handle
on the table's right edge makes the last column, and so the table, wider or
narrower. No column goes below its longest word.

## Short cells

Nothing here needs to wrap at any width a pane is likely to have. Left alone,
a table that fits is scaled up to fill the measure.

| Delimiter row | The column is set |
| --- | --- |
| `---` | flush left |
| `:---` | flush left |
| `:---:` | centred |
| `---:` | flush right |

## Prose in cells

A cell is horizontal material like a paragraph's, and when its column is
narrower than the cell it is broken first-fit at natural spacing, ragged on the
side its alignment leaves free.

| Term | What it means here | Why it matters to a host |
| --- | --- | --- |
| Measure | The width a paragraph is broken to, which for a pane is the width of the pane and for a cell is the width of its column less the padding. | A pane that changes width re-breaks every block, so a host that can hold the measure steady should. |
| Unit | One independent run of blocks, shipped and indexed on its own and stacked by offset. | Changing one table costs that table and nothing else, which is what the counter above the pane reports. |
| Floor | The widest stretch of a cell that no line break can divide: its longest word. | Below it the word would run into the next column, so nothing sets a column narrower. |

## Alignment by column

The second column is centred and the third and fourth are set flush right, as
the markdown asks with colons in its delimiter row. Wrapped lines keep their
column's alignment.

| Unit | Name | In points | Scaled points |
| :--- | :---: | ---: | ---: |
| pt | point | 1 | 65536 |
| pc | pica | 12 | 786432 |
| in | inch | 72.27 | 4736286 |
| bp | big point, the PostScript point | 1.00375 | 65781 |
| cm | centimetre | 28.45275 | 1864679 |

## A table too wide for the pane

Its cells set on one line are wider than the measure, so the columns are
squeezed: each keeps at least its longest word and what is left is shared by
how much each could use. Drag a column down to its floor and watch the row
grow.

| Stage | What it takes in | What it hands on | Where it can go wrong | What it costs |
| --- | --- | --- | --- | --- |
| Convert | Markdown source, a theme and a metrics resolver | Blocks of horizontal material, one for each paragraph, code block, rule and table | Markdown the converter does not know is not set as anything | Paid once for each edit of the source |
| Compose | Blocks, a measure and the line breaking parameters | A vertical list of boxes with the glue between them | A word wider than its line leaves that line overfull | The line breaker, which is most of what a relayout spends |
| Ship | A box and the point its reference sits at | Glyph, rule and line commands at absolute positions | Nothing a reader would see: it is arithmetic over the box | One pass over the box |
| Draw | The commands the window can see | Vertices in the draw list of whatever window is current | A face that is not in the atlas is drawn in the bound font | The glyphs on screen and not the document |

## Links in cells

A link in a cell is live like any other: the pointer changes over it and a
click is reported in the line above the pane. A press on a link is the link's
and a press on a handle is the handle's; neither begins a selection.

| Document | What it is | Where |
| --- | --- | --- |
| The TeXbook | The model every box and every glue here follows | [ctan.org](https://ctan.org/pkg/texbook) |
| Dear ImGui | The immediate mode library this draws through | [github.com/ocornut/imgui](https://github.com/ocornut/imgui) |
| markdown-it-py | The parser that turns the source into tokens, with its own [documentation](https://markdown-it-py.readthedocs.io/) | [github.com/executablebooks](https://github.com/executablebooks/markdown-it-py) |

Text outside a table selects as it does anywhere, and stays selected while a
column is dragged.

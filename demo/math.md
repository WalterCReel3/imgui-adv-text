# Math in text

A formula written between dollar signs, such as $e^{i\pi} + 1 = 0$, is set by the math engine and sits in its line as one box. The subset is small on purpose: enough for everyday output, with no macro processor behind it. Everything on this page is ordinary markdown, converted with math switched on, which is off unless a host asks for it.

## What a formula does to its line

A formula of plain letters, such as $x$ or $a + b = c$, is no taller than the words around it, and the lines keep their leading. Scripts hang from the same baseline as the text: the letter in $x^2$ and in $x_i$ stands where a letter of the sentence would, and $x_i^2$ carries both at once. A fraction is another matter. The fraction $\frac{a}{b}$ needs more room than a line of words has, so its line is set further from its neighbours, and a fraction of fractions, $\frac{\frac{a}{b}}{\frac{c}{d}}$, pushes them further again. Only the gaps touching the formula's own line change. The lines above and below this sentence are spaced as they would have been with no formula anywhere in the paragraph, which is what lets a reader's eye keep its place.

## Inline and display

One source, two settings. Inline, a sum keeps its limits beside it, as in $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$, so the line is disturbed as little as possible. Between two lines of `$$` the same source is set in display style, centred, with the limits stacked and the fraction at full size:

$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

An integral keeps its bounds beside it in both styles, inline $\int_0^1 x^2 dx = \frac{1}{3}$ and displayed:

$$\int_0^1 x^2 dx = \frac{1}{3}$$

## A formula at a line break

A formula is never broken across lines. Drag the measure slider above and watch this one: the sum of an arithmetic progression, $a_1 + a_2 + a_3 + \cdots + a_n = \frac{n(a_1 + a_n)}{2}$, moves to the next line whole when it no longer fits, and the line it left is stretched to the margin like any other. At a measure narrower than the formula itself it overhangs; it is not scaled and not split.

## Roots, fitted delimiters, spaces and words

Parentheses typed as themselves stay the size of the type, as in $(\frac{a}{b})$. Written with `\left` and `\right` they are fitted to what stands between them, as in $\left(\frac{a}{b}\right)$: the font carries eight parentheses of rising height and the smallest that covers the content is the one set; when none does, the largest is used as long as it covers three quarters of it. Nothing is stretched. A root sign is chosen the same way, so the sign in $\sqrt{x}$ and the sign in $\sqrt{\frac{a}{b}}$ are two different outlines out of five.

A space can be asked for by name. The differential in $\int f(x) dx$ sits against the bracket, and in $\int f(x) \, dx$ it stands a thin space off. Words inside a formula are set in the face of the text around it and not in math italic: $x = 1 \text{ if } y > 0$.

$$
\left( \sum_{i=1}^{n} \frac{a_i}{b_i} \right)^2 \le \sqrt{n} \quad \text{for every } n
$$

## Where a formula can go

### In a heading: $E = mc^2$

- In a list item, $\alpha + \beta = \gamma$, with words after it.
- In a second item with a taller one, $\frac{1}{1 - x}$, which opens its own gap.

> In a quotation: $\lim_{n \to \infty} \frac{1}{n} = 0$.

| name | formula |
|---|---|
| Euler | $e^{i\pi} + 1 = 0$ |
| Basel | $\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}$ |

A link straight after a formula keeps its own colour and its own hit area: $a^2 + b^2 = c^2$ [is the theorem of Pythagoras](https://en.wikipedia.org/wiki/Pythagorean_theorem), and the formula before it is not part of the link.

## Prices are not math

It cost $5 and $10, and neither is a formula. An opening dollar sign must be followed at once by the formula and must not come straight after a letter or a digit, and a closing one must follow the formula at once and must not be followed by a letter or a digit; so $5 and $10 stay text, with their dollar signs, and so does the dollar sign of a shell variable written in the middle of a word. It is a rule of thumb, and what it gives up is two formulas written with nothing between them. A dollar sign can also be escaped, \$ like this.

## Selecting and copying

Select across a formula and it is taken or left as a whole: there is no caret position inside one, and a double click takes it alone. Copying gives back the source between its dollar signs, so a copied paragraph can be pasted into markdown and set again. The line under the page header shows what the current selection would copy.

Find does not look inside formulas: a search matches the words of a paragraph and steps over its boxes.

## The subset, one construct at a time

Each row is the source as typed and the result of setting that same source.

{{reference}}

## Refused, and why

Whatever cannot be set whole is never set as a damaged formula. Its source is shown as it was typed, in the code face with its dollar signs, and the reason is kept with the block for a host to read. Three things are still out. **Matrices are left out for now**: that was decided for this build and is a known gap, not an oversight, and everything else that needs alignment is out with them. Accents are not built. And a delimiter or a root sign is chosen from the sizes the font carries, the largest about three times the height of the type, and never assembled from pieces; so content taller than that is refused, where a sign that does not reach would be a damaged formula. The first two items below are of that kind. Environments and macros are out for good, since both need state that a table of commands does not have.

{{refusals}}

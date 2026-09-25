# The Measure

A column is not a decoration. It is a decision about how far the eye must
travel before it turns around, and almost everything else about a page follows
from that one number.

Reading is not a smooth glide along a line of type. The eye moves in jumps,
called *saccades*, and takes in a few characters at each brief stop between
them. The jumps along a line are cheap. The expensive one is the return sweep:
the long backward flick at the end of a line, which has to land on the first
word of the next line and not on the line above it or the line below. Miss that
landing and a reader loses a fraction of a second, and something worse than a
fraction of a second, which is the sense that the page is on their side. A page
that costs them that twice a paragraph is a tiring page however handsome its
type.

So a line has a comfortable length, and it is shorter than most people guess.
Robert Bringhurst gives **sixty-six characters**, counting the spaces, as the
ideal for a single column of text, and forty-five to seventy-five as the range
within which a reader is unlikely to complain. At a normal book size that is
something near four inches of line. Set the same text across a ten inch page
and every return sweep turns into a small act of navigation, performed forty
times a page, by a reader who did not ask to navigate anything.

A page wider than the line it wants is the ordinary case and not the exception.
Paper arrives in sheets and screens arrive in windows, and neither was sized by
a typographer. The column is the old answer: cut the page into strips each
about as wide as a line ought to be, fill the first one, and carry on at the
head of the second.

## An old answer, and a cheap one

Gutenberg set the forty-two line Bible in two columns, because the manuscripts
he was imitating were in two columns, and they were in two columns because a
lectern Bible is a large book and a line running the full width of one could
not be read standing up. The reason was ergonomic before it was ever
aesthetic. It still is.

The newspaper pushed the idea as far as it will go. A broadsheet page is
enormous, the material on it is heterogeneous, and none of it is meant to be
read in order from the top left corner. Narrow columns solve all three problems
at once. They bring the measure back under control; they let an editor move a
story without resetting it, because a column of type is a rectangle and
rectangles can be shuffled; and they let a reader enter the page anywhere,
since a column is short enough to be sampled without commitment.

The price is paid in the spaces. A narrow measure runs nearer thirty characters
than sixty, and thirty characters is about five words, which is about four
interword spaces. Justify such a line and those four spaces have to absorb the
whole of whatever the line was short by. They stretch, visibly, and when two or
three consecutive lines stretch in nearly the same places the reader sees a
*river* of white running down the column.

> The rivers are not imaginary. They are the eye finding an alignment nobody
> offered it on purpose.
>
> > And no typesetter can talk a reader out of seeing one.

Hyphenation is what makes a narrow justified column possible. It gives the
breaker somewhere else to cut, which means the line arrives closer to full,
which means the spaces have less work to do. A newspaper without hyphenation
is a newspaper set ragged right, and most of them now are. This document is set
justified and is not hyphenated, so it is quietly making the argument against
itself: watch the interword spacing as you narrow the columns and you will see
exactly the effect the paragraph above describes.

---

## Where one column ends

The interesting part of a column is not its width. It is its foot.

A vertical list is a sequence of boxes, glue and penalties, in the same way a
paragraph is a sequence of boxes, glue and penalties turned on its side. To cut
a document into columns is to break that vertical list in the same way the line
breaker breaks a horizontal one, and the arithmetic rhymes. Not every position
is a legal place to cut. A break may be taken at glue, and only when the thing
before that glue is something a reader can see, so that the discarded space
falls off the foot of the column rather than reappearing at the head of the
next one.

That rule has a consequence here which is worth stating plainly, because it is
not obvious and it shaped this page. Between two *lines of one paragraph* this
engine puts interline glue, so a paragraph may be cut between any two of its
lines. Between two *blocks* — two paragraphs, two items of a list, a heading
and the text beneath it — it puts a rigid kern instead, and a kern is not a
legal breakpoint. So every column break in this document falls inside some
paragraph, never between two of them, and any run of short blocks is one
indivisible slab however tall it grows. A quoted passage is a single box for
the same reason: the bar down its margin has to be exactly as tall as the
quote, so the quote is packed whole before anything can ask where it might be
cut. Keep the quotations short in a document meant for columns. That is why
the one above is.

Three decisions have to be made and none of them is obvious.

1. Where the cut may fall, which is the question above, and which the document
   answers rather than the layout engine.
2. What becomes of the glue that straddles the cut. TeX discards it and then
   inserts a fresh amount of its own at the top of the fragment, so that the
   first baseline of every column sits the same distance below the top of the
   column and the tops line up across the page. The name of that fresh glue is
   `\splittopskip`, and a splitter that forgets it produces columns whose first
   lines are each a little lower or higher than their neighbours, for reasons
   nobody will be able to see and everybody will be able to feel.
3. Whether the columns should be *balanced*. Filling each column to the full
   height and letting the last one end wherever it ends is honest, cheap, and
   correct. Balancing, so that the final column of an article is roughly as
   deep as the others, is what a designer usually wants and what a magazine
   always wants. It is not free: the usual method is to guess a height, set the
   whole thing, look at the result, and guess again.

TeX spells the cut `\vsplit` and it is one of the few primitives with an
opinion about the future, since the material it declines to take is handed back
for the next column to think about. Balancing is not a primitive at all. In
LaTeX it lives in the `multicol` package, which does exactly the guess, set and
guess again described above, and does it well enough that most of its users
have never had to find out.

## Small ugly things with names

The trade has never agreed on what to call the two commonest faults at a
column break, and the disagreement is older than any of us. A single line of a
paragraph left stranded at the foot of a column, with the rest of the paragraph
moving on to the next one, is bad because it promises a paragraph and does not
deliver it. A single line arriving alone at the head of a column, with the rest
of its paragraph behind it on the previous one, is worse, because it is a
fragment presented as a beginning. One of these is a widow and the other is an
orphan; which is which depends entirely on whom you ask, and British printers
have long called the second a **club line**, which at least has the merit of
being unambiguous.

The fix for both is the same and it is not a fix at all. It is a *penalty* — a
number attached to a position saying what it would cost to break there — large
enough that the breaker will pay for a slightly worse column elsewhere in order
to avoid it, and small enough that it will accept the fault rather than fail
outright when there is nowhere else to go. ***That is the whole of the
technique***, and it is the same technique the line breaker uses, and the same
one that keeps a heading from being the last thing on a page.

A heading at the foot of a column is the third fault and the least forgivable,
because a heading is a promise about what comes next and there is no next. It
is also the easiest to prevent, since a heading and the first lines of the
paragraph under it can simply be declared inseparable and moved together.

## What you are looking at

Every glyph on this page was placed by arithmetic in this repository, including
the ones that ended up in the wrong place. The columns were filled by walking
the vertical list until the next box would overflow the column height and
cutting at the last legal break before it. Nothing was balanced, nothing was
hyphenated, and no line was moved by hand to make a screenshot look better.

Change the column count and watch the last line of one column and the first
line of the next. If they read on from each other, the flow is real. If they do
not, something in the paragraph above is a lie, and the person who wrote it
would like to know.

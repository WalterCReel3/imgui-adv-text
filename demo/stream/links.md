# Links, and a word wider than the pane

A paragraph with an address in the middle of it that no pane is wide enough to
hold on one line:
https://example.org/a/very/long/path/that/keeps/going/through/several/directories/and/then/a/file-name-with-hyphens-in-it.html?first=1&second=two&third=the-third-parameter#and-a-fragment
and then the sentence carries on after it, as a sentence does. The address has
no space in it, so there is nowhere to break it, and the line it is on is wider
than the measure.

An inline link is a link as soon as its closing parenthesis arrives:
[the project page](https://example.org/project). Until then it is a square
bracket and some words.

A reference-style link is different. The words [the changelog][changes] and
[the issue tracker][issues] name their targets by label, and the labels are
defined at the foot of the answer, after everything else has been written.

A streaming renderer cannot wait for the foot of the answer, so while a
document streams the definitions are not read and those two links are shown as
the text that was typed, brackets and all. That is by design: a paragraph that
changed its meaning when a line arrived twenty lines later could never be
settled.

[changes]: https://example.org/project/changelog
[issues]: https://example.org/project/issues

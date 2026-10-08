Plain prose, and nothing else: no emphasis, no code, no list and no link. It is
the case a streaming view can hold still. Each line of the paragraph being
written is filled until the next word will not fit, and a line filled that way
depends only on the words up to its own end, so the words that arrive after it
have no way to reach back and change it.

That is the claim this source is here to let the counter check. Under the
policy that keeps a paragraph as it streamed, the count of settled lines that
moved should stay at zero from the first token to the last, at any rate and at
any width the pane is given. Under the policy that sets a finished paragraph
again, the count should rise once for each paragraph, at the moment the blank
line after it arrives, and at no other time.

A third paragraph is here so that there are three such moments and not two. It
runs a little longer than the others, long enough to fill several lines in a
narrow pane and a few in a wide one, because a paragraph of one line has no
settled line in it to move and would show nothing either way. It ends, like the
others, with a full stop and a blank line.

The last paragraph has no blank line after it. It stays live until the stream
is closed, which is the only thing that can tell a renderer that the final
sentence of an answer is finished and not merely paused.

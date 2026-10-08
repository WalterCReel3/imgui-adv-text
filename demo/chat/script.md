%% user
What is this pane, and what can I do in it?

%% assistant
This is a **canned conversation**: nothing here talks to a model or to the network. Each reply is a file read back a few characters at a time through `StreamDocument`, the way a host would feed it tokens.

Press Enter in the box below (typed text or none) and the next reply plays. The rate slider changes how fast. Things to try while one arrives:

- drag across text in any message, then Ctrl+C: one selection for the whole transcript;
- scroll up: the pane stops following the end, and takes it up again at the bottom;
- the `copy` button on a code block, and `copy as markdown` under a message.

The library is at [imgui-adv-text](https://example.org/imgui-adv-text) and its line breaker is Knuth and Plass's, from [*Breaking Paragraphs into Lines*](https://example.org/knuth-plass).

%% user
Show me a function, and how you would call it.

%% assistant
Here is `tokens`, which cuts a reply into the pieces this page feeds. The pattern is `\s*\S{1,4}|\s+`: up to four visible characters with the white space before them.

```python
import re

def tokens(source: str) -> list[str]:
    """Pieces of at most four visible characters."""
    # white space travels with the word after it
    return re.findall(r"\s*\S{1,4}|\s+", source)

assert "".join(tokens("a  bc\n")) == "a  bc\n"
```

Joined back together the pieces are the source, which is the only property the replay needs. Call it once per reply, not once per frame: `pieces = tokens(text)`.

%% user
Now change it so a piece can be longer.

%% assistant
One argument and one changed line. Every existing call keeps working, because `most` defaults to what was written in the pattern before. Run it with the directory on your path, PATH=$HOME/bin:$PATH (those dollar signs are a shell's and stay text; math is on in this pane, and $x^2$ is a formula). The diff arrives a line at a time, the block has a toggle for side by side, and this reply ends with it:

```diff
--- a/replay.py
+++ b/replay.py
@@ -1,8 +1,9 @@
 import re
 
-def tokens(source: str) -> list[str]:
-    """Pieces of at most four visible characters."""
+def tokens(source: str, most: int = 4) -> list[str]:
+    """Pieces of at most `most` visible characters."""
     # white space travels with the word after it
-    return re.findall(r"\s*\S{1,4}|\s+", source)
+    pattern = r"\s*\S{1,%d}|\s+" % most
+    return re.findall(pattern, source)
 
 assert "".join(tokens("a  bc\n")) == "a  bc\n"
```

%% user
Walk me through adopting this in my own app.

%% assistant
Four steps, in the order they stop being optional:

1. Load the faces once, when the font atlas is built.

   A host that already has a font keeps it; these are added beside it.

   ```python
   fonts = load_faces()
   ```

2. Build a theme at the pixel height your UI font uses.

   ```python
   theme = Theme.at_pixel_height(15.0, faces=Faces.mono(), align=Align.LEFT)
   ```

   Ragged right in one face is what a terminal-like transcript sets. Leave the arguments out for justified Roboto.

3. Keep one view per message.

   A finished message is a `BareView` and lays out only when the pane's width changes. The message still arriving is a `StreamView`:

   ```python
   stream = StreamDocument(theme, fontlib_metrics)
   view = StreamView(stream, measure)
   stream.append(piece)        # as tokens arrive
   view.draw(fonts=fonts)      # once a frame
   ```

4. Draw them all into one scrolling child, one after the other.

   The views paint no background and claim only their own height, so stacking them is just drawing them.

That is the whole of it. What each step costs:

| step | when it runs | what it costs |
| --- | --- | --- |
| load faces | once | reading four font files |
| build theme | once, and on a size change | metrics lookups |
| finished view | on a width change | one layout of that message |
| streaming view | each frame something arrived | the unfinished tail only |

%% user
How wide should a line be, and is there a formula for badness?

%% assistant
Bringhurst's band is 45 to 75 characters, with 66 the figure usually quoted; this demo's page is 2.25 alphabets, about 65.

Badness is how far a line's glue had to stretch or shrink. With $r$ the ratio of the adjustment to what the line can give, TeX takes it as $100 r^3$, so a line stretched to exactly its limit has badness $100$ and one at half of it only $12.5$. The demerits of a line then add the line penalty $l$ and square the sum:

$$
d = (l + b)^2 + p^2
$$

where $b$ is the badness and $p$ the penalty at the break. The breaker minimises $\sum_{i=1}^{n} d_i$ over the whole paragraph, which is what "total fit" means. A price like $5 or $10 is not a formula, and stays text.

%% user
Give me a long answer.

%% assistant
Here is the long one: thirty numbered notes, so that there is something to scroll while more of it arrives. The footer's cost per token should read about the same at the thirtieth as at the third.

1. **Note 1, on boxes.** A box has a width, a height and a depth, and nothing inside it is looked at again once it has been packed. This is note 1 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

2. **Note 2, on glue.** Glue has a natural width, a stretch and a shrink; a line is set by sharing its shortfall among its glue in proportion. This is note 2 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

3. **Note 3, on kerns.** A kern is a fixed space that is never a place to break, which is what keeps a pair like `AV` together. This is note 3 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

4. **Note 4, on penalties.** A penalty says how bad a break here would be; minus ten thousand forces one and ten thousand forbids it. This is note 4 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

5. **Note 5, on lines.** A line is an hbox packed to the measure, and the paragraph is those boxes stacked with interline glue between them. This is note 5 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.


   ```python
   note = 5  # a fence inside an item, every tenth note
   ```

6. **Note 6, on the strut.** Every line of text is set on its block's strut, so that a line of small letters is as tall as one with an ascender. This is note 6 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

7. **Note 7, on boxes.** A box has a width, a height and a depth, and nothing inside it is looked at again once it has been packed. This is note 7 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

8. **Note 8, on glue.** Glue has a natural width, a stretch and a shrink; a line is set by sharing its shortfall among its glue in proportion. This is note 8 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

9. **Note 9, on kerns.** A kern is a fixed space that is never a place to break, which is what keeps a pair like `AV` together. This is note 9 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

10. **Note 10, on penalties.** A penalty says how bad a break here would be; minus ten thousand forces one and ten thousand forbids it. This is note 10 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

11. **Note 11, on lines.** A line is an hbox packed to the measure, and the paragraph is those boxes stacked with interline glue between them. This is note 11 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

12. **Note 12, on the strut.** Every line of text is set on its block's strut, so that a line of small letters is as tall as one with an ascender. This is note 12 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

13. **Note 13, on boxes.** A box has a width, a height and a depth, and nothing inside it is looked at again once it has been packed. This is note 13 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

14. **Note 14, on glue.** Glue has a natural width, a stretch and a shrink; a line is set by sharing its shortfall among its glue in proportion. This is note 14 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

15. **Note 15, on kerns.** A kern is a fixed space that is never a place to break, which is what keeps a pair like `AV` together. This is note 15 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.


   ```python
   note = 15  # a fence inside an item, every tenth note
   ```

16. **Note 16, on penalties.** A penalty says how bad a break here would be; minus ten thousand forces one and ten thousand forbids it. This is note 16 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

17. **Note 17, on lines.** A line is an hbox packed to the measure, and the paragraph is those boxes stacked with interline glue between them. This is note 17 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

18. **Note 18, on the strut.** Every line of text is set on its block's strut, so that a line of small letters is as tall as one with an ascender. This is note 18 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

19. **Note 19, on boxes.** A box has a width, a height and a depth, and nothing inside it is looked at again once it has been packed. This is note 19 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

20. **Note 20, on glue.** Glue has a natural width, a stretch and a shrink; a line is set by sharing its shortfall among its glue in proportion. This is note 20 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

21. **Note 21, on kerns.** A kern is a fixed space that is never a place to break, which is what keeps a pair like `AV` together. This is note 21 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

22. **Note 22, on penalties.** A penalty says how bad a break here would be; minus ten thousand forces one and ten thousand forbids it. This is note 22 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

23. **Note 23, on lines.** A line is an hbox packed to the measure, and the paragraph is those boxes stacked with interline glue between them. This is note 23 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

24. **Note 24, on the strut.** Every line of text is set on its block's strut, so that a line of small letters is as tall as one with an ascender. This is note 24 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

25. **Note 25, on boxes.** A box has a width, a height and a depth, and nothing inside it is looked at again once it has been packed. This is note 25 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.


   ```python
   note = 25  # a fence inside an item, every tenth note
   ```

26. **Note 26, on glue.** Glue has a natural width, a stretch and a shrink; a line is set by sharing its shortfall among its glue in proportion. This is note 26 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

27. **Note 27, on kerns.** A kern is a fixed space that is never a place to break, which is what keeps a pair like `AV` together. This is note 27 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

28. **Note 28, on penalties.** A penalty says how bad a break here would be; minus ten thousand forces one and ten thousand forbids it. This is note 28 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

29. **Note 29, on lines.** A line is an hbox packed to the measure, and the paragraph is those boxes stacked with interline glue between them. This is note 29 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.

30. **Note 30, on the strut.** Every line of text is set on its block's strut, so that a line of small letters is as tall as one with an ascender. This is note 30 of thirty and it says so, so that a selection copied from the middle can be told from one copied from the end.


That was all thirty. Nothing above this line was laid out again while the lines below it arrived.

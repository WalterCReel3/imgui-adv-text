# One document, any scheme

This page holds **one piece of markdown**. The pickers above it change the
*palette*, which is nothing but colours, and the *theme*: which face plays which
role, how large the running text is, justified or ragged. The library paints no
background -- the colour behind this text belongs to
[the window](https://example.org/window) that drew it.

## What a host supplies

1. A theme, built once for a size the host states in its own pixels.
2. A palette, with an ink for any role that should differ.
3. Its own background, and a callback for [links](https://example.org/links).

> A quotation takes the ink of its role, and so does each level of heading.
> Change the palette and nothing is broken into lines again.

## Code is coloured by ranges

The view is handed ranges of a block's characters, each with an ink. It never
sees a token, so any highlighter will do. This one is the demo's:

```python
def spans(block, inks):
    """Ranges of characters, each with an ink."""
    for start, end, kind in tokens(text_of(block)):  # comment, string, ...
        if kind == "keyword":
            yield start, end, inks.keyword
    return 0x2A, 1_000.5, 'done'
```

A fence that names no language it knows gets the fallback: comments, strings
and numbers, and no keywords, since guessing a keyword list is guessing a language.

```sh
# build once, then run the page
make bootstrap && make run ARGS="--tab themes"   # 2 steps
echo "http://example.org/not//a-comment" 'single quoted'
```

| role | where its colour comes from |
|---|---|
| body | `Palette.ink` |
| heading, quote, code, table | `Palette.with_roles` |
| link | `Palette.link`, see [the palette](https://example.org/palette) |
| syntax | the host's own inks, as `ColourSpan`s |

---

Select across any of it and copy. With the split on, the same text is set
twice, in two palettes, and the two panes scroll together.

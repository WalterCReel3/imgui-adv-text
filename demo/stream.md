# Replaying an answer

This document is written the way a model writes: a heading, a few paragraphs,
a numbered procedure with code inside its steps, a table, and a closing remark.
It is meant to be fed to the renderer **a few characters at a time**, so every
block in it is, for a while, the block still being written.

The first paragraph has to be long enough to break onto several lines at any
width a pane is likely to have, because the thing to watch is whether a line
that has already been set stays where it is while the words after it arrive.
It also carries *emphasis that opens long before it closes, so that for a
dozen tokens the asterisk is only an asterisk*, and a `code span` that does the
same on a smaller scale.

## A procedure, with code inside the steps

1. Create the environment and install the package into it.

   ```sh
   python -m venv .venv
   .venv/bin/pip install -e .
   ```

2. Run the checks. The fence above is indented under its item, which is what
   makes this the construct a blank-line scanner gets wrong: read from its own
   first line it is not a fence inside a step but a code block on its own.

   A second paragraph inside the same step has the same property. Cut loose
   from the `2.` above it, it would be an ordinary paragraph at the margin.

3. Read the output:

   ```
   12 passed in 0.31s
   ```

Between the steps nothing may be committed early, and after the last one the
whole list is one settled block.

## Things that change their mind

A line can look like one thing and become another. This one mentions #tags and
ends before a line that starts with a number sign:
#not-a-heading, because no space follows the sign.

Some lines turn into a table only when the row of dashes arrives:

| setting        | breaks chosen | moves a settled line |
|----------------|:-------------:|---------------------:|
| justified      | all together  | sometimes            |
| ragged         | line by line  | never, for new words |

> A quotation is one block however many paragraphs it has.
>
> So its first paragraph is not settled until the quotation is over.

- A short list
- of three items
- the last of which contains a path that cannot be broken:
  `/home/user/projects/imgui-adv-text/advtext/backends/imgui_draw.py`

A heading with an underline
---------------------------

The heading above was a paragraph until its second line arrived.\
This line follows a hard break.

```python
def greet(name: str) -> str:
    return f"hello, {name}"
```

***

That is the whole of it.

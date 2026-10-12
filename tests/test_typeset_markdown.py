r"""
`advtext.typeset_markdown`: markdown to a block description with no node made.

Five groups.

1.  **What is loaded.** In fresh interpreters: `advtext.markdown_rules` loads
    nothing else of advtext; `advtext.typeset_markdown` loads
    `advtext.description`, `advtext.theme` and the one leaf THAT loads, and
    not the modules that make or measure nodes for a document. The names
    moved out of `advtext.markdown` are the same objects in both places, and
    the description types are `advtext.description`'s, the very objects
    `advtext.typesetter` has (`tests/test_description.py` holds the identity).
2.  **The oracle, frozen.** The direct description against what
    `Converter(theme).describe(build_document(source, ...).blocks)` answered,
    all seven fields, for every markdown file under `demo/`, a corpus of
    awkward sources in four themes, and generated sources. That converter
    and the math core that decided its refusals were deleted in tranche 5;
    what they answered on 2026-10-11 is `tests/data/material_descriptions.json`
    (2091 cases, every one this file ever asked), read through
    `tests/material_frozen.py`, where a case nobody froze is a `KeyError`
    and never a pass. `_differences` is the one
    comparison and it leaves out one thing, by name: the count of kerns the
    old path dropped. The other differences the module documents each have
    a test that says exactly what differs: a character a face lacks, a
    formula the old math core refuses, and -- the module's default, switched
    off for the comparison with `converter_spaces=True` -- which face the
    space beside a run is set in.
3.  **Tables and the source map.**
4.  **The stream**, held after every piece to one parse of everything
    received so far.
5.  **The library** (skipped without `IMTYPESET_LIBRARY`; a failure, not a
    skip, when it is set and `module()` is `None`): a `Document` takes every
    demo's direct description, a refused formula is reported per block, and
    `TypesetStreamView` runs over a `MarkdownStream` when it is handed this
    module's converter.
"""

from __future__ import annotations

import collections
import json
import os
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import material_frozen
import pytest
import test_markdown as markdown_tests

from advtext import markdown as markdown_module
from advtext import markdown_rules, typesetter
from advtext import typeset_markdown as direct
from advtext.description import RunDescription
from advtext.style import fontlib_metrics
from advtext.theme import Align, BlockKind, Theme
from advtext.typeset_markdown import (
    BLOCK_TABLE_HEADER,
    KIND_HOST,
    KIND_TABLE,
    RUN_DISPLAY_FORMULA,
    RUN_FORMULA,
    CellDescription,
    MarkdownCode,
    MarkdownConverter,
    MarkdownStream,
    MarkdownTable,
    MarkdownText,
    describe_markdown,
    parse_markdown,
)
from advtext.units import sp_from_px

_ROOT = Path(__file__).resolve().parent.parent
_DEMOS = sorted((_ROOT / "demo").rglob("*.md"))
_VARIABLES = (typesetter.LIBRARY_VARIABLE, typesetter.PACKAGE_VARIABLE)

KERNS = "kerns dropped (imtypeset kerns for itself)"
STOOD_IN = "characters no face has (advtext sets U+FFFD on the node; imtypeset stands in itself)"


def _refuses(source: str, display: bool, size: int) -> bool:
    """
    The old math core's decision, for the runs that show everything else equal.

    Frozen: `advtext.mathtext` is gone. A formula it was never asked about
    raises, so a new source cannot pass by being refused nothing.
    """
    return material_frozen.refuses(source, display, size)


def _aligned(theme: Theme, align: Align, indent: int = 0) -> Theme:
    return replace(
        theme,
        blocks={
            kind: replace(style, align=align, first_line_indent=indent)
            for kind, style in theme.blocks.items()
        },
    )


_DEFAULT = Theme.build()
THEMES: dict[str, Theme] = {
    "default": _DEFAULT,
    # A hard break in these two is a forced break with no fill before it.
    "centre": _aligned(_DEFAULT, Align.CENTER),
    "right": _aligned(_DEFAULT, Align.RIGHT),
    # Every text block begins with an indent box in the material.
    "indent": _aligned(_DEFAULT, Align.JUSTIFY, 12 * 65536),
}


_THEME_NAMES = {id(theme): name for name, theme in THEMES.items()}


def _material(
    source: str,
    theme: Theme,
    *,
    references: bool = True,
    math: bool = True,
    more_may_follow: bool = False,
    link_color: int = 0,
) -> typesetter.Description:
    """
    What the material path answered for this case: read from the frozen file.

    Until tranche 5 this WAS the material path
    (`typesetter.Converter(theme, link_color=...).describe(build_document(source,
    theme, fontlib_metrics, math=markdown_math() if math else None, ...).blocks)`).
    `theme` is one of `THEMES`.
    """
    return material_frozen.description(
        source,
        _THEME_NAMES[id(theme)],
        references=references,
        math=math,
        more_may_follow=more_may_follow,
        link_color=link_color,
    )


def _direct(source: str, theme: Theme, **more: Any) -> Any:
    """
    The direct description with `Converter`'s runs: what the old path's answer is compared with.
    """
    return describe_markdown(source, theme, converter_spaces=True, **more)


def _differences(old: Any, new: Any) -> list[str]:
    """
    Every field of the two descriptions that is not equal, one line each.

    All seven fields, compared whole. The one thing left out is `KERNS` in
    `kinds`: the old path counts the kern nodes it made and dropped, and the
    direct path makes none.

    And one thing is written the old way first, on both sides: a tab in a
    code block, which is a tab in a description made since 2026-10-12 and
    was spaces to its stop in what was frozen
    (`material_frozen.with_the_old_tabs` says exactly what it changes, and
    what holds it honest). A frozen description has no tab there to change.
    """
    old, new = material_frozen.with_the_old_tabs(old), material_frozen.with_the_old_tabs(new)
    found: list[str] = []
    for name in typesetter.Description._fields:
        a, b = getattr(old, name), getattr(new, name)
        if name == "kinds":
            a = collections.Counter({key: count for key, count in a.items() if key != KERNS})
            assert KERNS not in b
        if a == b:
            continue
        if isinstance(a, list):
            if len(a) != len(b):
                found.append(f"{name}: {len(a)} against {len(b)}")
            for index, (x, y) in enumerate(zip(a, b, strict=False)):
                if x != y:
                    found.append(f"{name}[{index}]: {x!r} against {y!r}")
        else:
            found.append(f"{name}: {dict(a)!r} against {dict(b)!r}")
    return found


def _child(code: str, env: dict[str, str], *args: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env={**env, "PYTHONPATH": str(_ROOT)},
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, f"the child failed:\n{result.stdout}\n{result.stderr}"
    report: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return report


def _without() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name not in _VARIABLES}


# ---------------------------------------------------------------------------
# 1. What is loaded
# ---------------------------------------------------------------------------

_LOADED = """
import json, sys
import importlib
importlib.import_module(sys.argv[1])
def loaded():
    return sorted(name for name in sys.modules if name == "advtext" or name.startswith("advtext."))
before = loaded()
themed = []
used = []
if sys.argv[1] == "advtext.typeset_markdown":
    from pathlib import Path
    from advtext.theme import Theme
    from advtext import typeset_markdown as direct
    theme = Theme.build()
    themed = loaded()
    for path in sorted(Path("demo").rglob("*.md")):
        source = path.read_text(encoding="utf-8")
        described = direct.describe_markdown(source, theme, references=False, math=True)
        stream = direct.MarkdownStream(theme, math=True)
        for at in range(0, len(source), 97):
            stream.append(source[at:at + 97])
            stream.revision
        stream.close()
        used.append(len(described.blocks) == len(stream.blocks) > 0)
print(json.dumps({
    "before": before,
    "themed": themed,
    "after": loaded(),
    "used": used,
    "heavy": [name for name in ("imgui_bundle", "fontTools", "imtypeset") if name in sys.modules],
    "markdown_it": "markdown_it" in sys.modules,
}))
"""

# What `import advtext.theme` loads: itself and one leaf that imports nothing
# of advtext. Until tranche 3 `Theme` was in `advtext.style`, whose measuring
# half brought `nodes`, `pack` and `badness` with it; until T5-B2 the leaves
# were two modules of the reference core, `advtext.units` and
# `advtext.fontmetrics`.
_THEME_LOADS = {"advtext.primitives", "advtext.theme"}

# What a document's nodes are made, measured, shipped or set with. None of it
# may be loaded by reading markdown directly.
_NOT_LOADED = (
    "advtext.markdown",
    "advtext.style",
    "advtext.shipout",
    "advtext.fontlib",
    "advtext.mathtext",
    "advtext.math",
    "advtext.linebreak",
    "advtext.selection",
    "advtext.spans",
    "advtext.stream",
    "advtext.typesetter",
    "advtext.ui",
    "advtext.backends",
)


def test_the_parser_rules_load_nothing_else_of_advtext() -> None:
    report = _child(_LOADED, _without(), "advtext.markdown_rules")
    assert report["before"] == ["advtext", "advtext.markdown_rules"]
    assert report["markdown_it"] and report["heavy"] == []


def test_reading_markdown_directly_loads_the_theme_the_description_and_no_more() -> None:
    report = _child(_LOADED, _without(), "advtext.typeset_markdown")
    expected = sorted(
        {"advtext", "advtext.description", "advtext.markdown_rules", "advtext.typeset_markdown"}
        | _THEME_LOADS
    )
    assert report["before"] == expected
    # Describing every demo, whole and as a stream, imported nothing lazily,
    # and neither did building the theme (it made an `InterlineSkip` of the
    # layout core's until T5-B2): what is loaded afterwards is what the import
    # loaded.
    assert report["used"] and all(report["used"])
    assert report["after"] == report["themed"] == report["before"]
    assert report["heavy"] == []
    for name in _NOT_LOADED:
        inside = name + "."
        assert not [
            found for found in report["after"] if found == name or found.startswith(inside)
        ], name


def test_the_theme_alone_loads_exactly_what_the_test_above_blames_on_it() -> None:
    report = _child(_LOADED, _without(), "advtext.theme")
    assert set(report["before"]) == {"advtext"} | _THEME_LOADS


def test_every_name_moved_out_of_markdown_is_the_same_object_there() -> None:
    moved = [
        name
        for name, value in vars(markdown_rules).items()
        if getattr(value, "__module__", None) == "advtext.markdown_rules"
    ]
    # Four names were ADDED to the rules module after the move (2026-10-12, a
    # host's reader options; the last two are pptmstr's P32) and were never in
    # `advtext.markdown`. Named, so that a fifth arriving unannounced still
    # fails here.
    added = {"_written_stars", "_reader_parser", "_written_backslashes", "_written_cell_pipes"}
    assert added <= set(moved) and not any(hasattr(markdown_module, name) for name in added)
    moved = [name for name in moved if name not in added]
    moved += ["TAB_WIDTH", "_BULLET", "_COLUMN_ALIGNS", "_PARSER", "_PARSER_WITHOUT_REFERENCES"]
    moved += ["_MORE_MAY_FOLLOW", "_END_IS_OPEN"]
    assert {"SourceSpan", "BlockSource", "ColumnAlign", "_math_inline", "_math_block"} <= set(moved)
    assert {"_parse", "_parser", "_build_parser", "_line_starts", "_span"} <= set(moved)
    for name in moved:
        assert getattr(markdown_module, name) is getattr(markdown_rules, name), name
    assert markdown_module.build_document.__module__ == "advtext.markdown"


def test_the_description_types_here_are_the_typesetters_own() -> None:
    """
    They were copies, equal field for field (SW-R1's finding R8). Both
    modules take them from `advtext.description` now;
    `tests/test_description.py` holds every name. Here, the two that the
    oracle below leans on.
    """
    assert direct.RunDescription is typesetter.RunDescription
    assert direct.BlockDescription is typesetter.BlockDescription
    assert direct.Description is typesetter.Description
    assert direct._with_tags is typesetter._with_tags


# ---------------------------------------------------------------------------
# 2. The oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_a_demo_is_described_directly_as_the_material_path_describes_it(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    old = _material(source, _DEFAULT)
    assert old.kinds[KERNS] > 0
    assert _differences(old, _direct(source, _DEFAULT, math=True, refuses=_refuses)) == []
    # No demo holds, outside a table, a formula the old math core refuses:
    # with the library left to decide, the description is the same again.
    assert _differences(old, _direct(source, _DEFAULT, math=True)) == []
    # And with math off, where a dollar is a dollar.
    plain = _material(source, _DEFAULT, math=False)
    assert _differences(plain, _direct(source, _DEFAULT)) == []


def test_the_demos_hold_enough_for_that_equality_to_mean_something() -> None:
    kinds: collections.Counter[str] = collections.Counter()
    faces: collections.Counter[int] = collections.Counter()
    hard = formulas = tagged = 0
    for path in _DEMOS:
        described = describe_markdown(path.read_text(encoding="utf-8"), _DEFAULT, math=True)
        kinds += described.kinds
        for block in described.blocks:
            hard += block.flags & direct.BLOCK_HARD_BREAKS
            for run in block.runs:
                faces[run.face] += 1
                formulas += bool(run.flags & (RUN_FORMULA | RUN_DISPLAY_FORMULA))
                tagged += bool(run.tag)
    assert len(_DEMOS) >= 13
    assert sum(count for key, count in kinds.items() if key.startswith("TextBlock")) > 200
    assert kinds["CodeBlock"] > 10 and kinds["RuleBlock"] > 0 and kinds["list markers"] > 50
    assert kinds["blocks quoted more than one deep"] > 0
    assert kinds["display formulas not closed yet (source so far)"] == 0
    # Bold, italic, bold italic and code runs; formulas; links; a hard break.
    assert all(faces[role] > 0 for role in (2, 3, 4, 5))
    assert formulas > 20 and tagged > 5 and hard > 0


# Sources chosen for where the two paths could part: white space at every
# edge, hard breaks of both spellings in every position, links over styled
# text and across breaks, formulas set, refused and unclosed, the block kinds
# nested in each other.
CORPUS: dict[str, str] = {
    "empty": "",
    "blank": "\n\n  \n",
    "plain": "One paragraph of plain words.\n",
    "spaces": "  leading,   doubled    and trailing   \n\twith\ta tab and a no-break space\n",
    "emphasis": "a *b* **c** ***d*** *e **f** g* **h *i* j** __init__ foo_bar_baz _no_\n",
    "code-span": "a `b  c` d ` e` f `` g`h `` `i ` j`k`l\n",
    "code-span-edges": "` x` and `y ` and `  z  ` and ` ` end\n",
    "styled-space": "**bold ** then *it* then ** x** `c` *i*`c`**b**\n",
    "softbreak": "one\ntwo  \nthree\\\nfour\n   five\n",
    "hard-break-space": "aaa bbb \\\nccc\n",
    "hard-break-twice": "a\\\n\\\nb  \n  \nc\n",
    "hard-break-first": "\\\na\n",
    "hard-break-in-bold": "**a\\\nb** c *d  \ne*\n",
    "hard-break-in-link": "[a\\\nb](u) [c  \n](v) [d](w)\\\ne\n",
    "hard-break-before-close": "*a\\\n*\n\n**b  \n**\n\n[c\\\n](u)\n",
    "hard-break-in-code": "`a b  \nc`\\\nd\n",
    "hard-break-in-heading": "# a\\\nb\n\nSetext  \ntitle\n===\n",
    "links": "[a](u) and [**b** c](v) and [d](u) and [`e`](w) and <https://x.org> end\n",
    "link-over-edges": "**a [b** c](u) d *e [f](v) g* [h *i*](w)\n",
    "link-empty": "[](u) and [ ](v) and [![i](p)](w) x\n",
    "references": "[a][r] and [r] and [none]\n\n[r]: https://example.org/r\n",
    "images-and-html": (
        "a ![alt *text*](p.png) b <b>c</b> d <!-- e --> f &amp; g &copy; h\n"
        "\n<div>\nraw\n</div>\n"
    ),
    "escapes": "\\*a\\* \\$b\\$ \\\\ c\\d &#35; \\`e\\`\n",
    "headings": (
        "# one\n## two *x*\n### three `y`\n#### four\n"
        "##### five **z**\n###### six\n\nSetext\n---\n"
    ),
    "lists": "- a\n- b\n  - c\n    - d\n  - e\n\n1. f\n2. g\n   1. h\n10. i\n\n7) j\n8) k\n",
    "loose-list": "- a\n\n  second paragraph\n\n- b\n\n      code in an item\n\n- c\n",
    "empty-items": "- a\n-\n\npara\n\n1.\n2. b\n\n- ```\n  code\n  ```\n\nend\n",
    "quotes": "> a\n> b\n>\n> > c\n> > > d\n>\n> - e\n>   f\n\n- > g\n  > h\n",
    "quote-code-rule": (
        "> ```py\n> x = 1\n> ```\n>\n> ---\n>\n" "> | a | b |\n> |---|---|\n> | 1 | 2 |\n"
    ),
    "code": (
        "```python\ndef f():\n\treturn 1\n\n\n```\n\n"
        "    indented\n      more\n\n~~~\n\n~~~\n\n```\n   \n```\n"
    ),
    "code-unclosed": "text\n\n```\ncode with **stars** and $x$\n\n\n",
    "rules": "a\n\n---\n\n- b\n\n  ***\n\n> ___\n",
    "table": "| a | *b* | `c` |\n|:--|:-:|--:|\n| 1 | [2](u) | $x$ |\n| **4** | 5\\|6 |\n\nafter\n",
    "table-in-list": "- item\n\n  | a | b |\n  |---|---|\n  | 1 | 2 |\n\n- next\n",
    "math-inline": "Euler: $e^{i\\pi}+1=0$ and $$x^2$$ and $5 and $10, not math; US$5; $n$th.\n",
    "math-refused": "ok $x^2$ then $\\hat x$ then $\\frac{1$ and **$\\nosuch$** end\n",
    "math-display": (
        "before\n\n$$\n\\sum_{k=0}^{n} k\n$$\n\n"
        "$$ a + b $$\n\n$$\n\\hat x\n$$\n\n$$\n$$\n\nafter\n"
    ),
    "math-display-nested": "- item\n\n  $$\n  x^2\n  $$\n\n> $$\n> y\n> $$\n\n1. $$ z $$\n",
    "math-unclosed": "text\n\n$$\n\\sum_{k=0}\n",
    "math-unclosed-empty": "text\n\n$$",
    "math-in-links": "[$x$ a](u) and **$y$ b** and [c $z$](v) and $a$$b$ $c$ $d$\n",
    "math-at-the-end": "set $PATH=$",
    "math-in-heading": "# The $x^2$ of it\n\n- $a$\n- b $c$\n",
    "dollars-off": "a $x$ b $$ c\n\n$$\ny\n$$\n",
    "crlf": "one\r\ntwo\r\n\r\n- a\r\n- b\r\n\r\n```\r\ncode\r\n```\r\n",
    "tabs": "\tcode by a tab\n\n-\ttab after the marker\n\n>\tquoted\n\na\tb\n",
    "unicode": "café naïve — “quoted” … and a​zero width\n",
    "everything": (
        "# T\n\nP *i* **b** `c` [l](u) $m$\\\nnext\n\n- a\n  1. b\n\n> q\n\n```\nx\n```\n\n---\n\n"
        "| h |\n|---|\n| c |\n\n$$\nd\n$$\n"
    ),
}


@pytest.mark.parametrize("name", sorted(CORPUS))
@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_an_awkward_source_is_described_directly_as_the_material_path_describes_it(
    name: str, theme_name: str
) -> None:
    source, theme = CORPUS[name], THEMES[theme_name]
    for references in (True, False):
        for math in (True, False):
            for more in (False, True):
                old = _material(
                    source, theme, references=references, math=math, more_may_follow=more
                )
                new = _direct(
                    source,
                    theme,
                    references=references,
                    math=math,
                    more_may_follow=more,
                    refuses=_refuses,
                )
                assert _differences(old, new) == [], (references, math, more)


def test_the_corpus_reaches_the_rules_it_was_written_for() -> None:
    def blocks(name: str, theme: str = "default", **more: Any) -> tuple[Any, ...]:
        return parse_markdown(CORPUS[name], THEMES[theme], **more).blocks

    # Two hard breaks one after the other are ONE newline: the old converter
    # writes a newline for a break only where the text does not already end
    # in one, and this is held to it.
    twice, after = blocks("hard-break-twice")
    assert (twice.text, twice.hard_breaks) == ("a\nb", True) and after.text == "c"
    # Justified, a break that is the last thing in a block is still a newline
    # (its fill glue is read as one) and the link over it covers it. Centred,
    # the break is a penalty that nothing follows, and it is nothing.
    last = blocks("hard-break-before-close")[-1]
    assert (last.text, last.hard_breaks, last.links[0][:2]) == ("c\n", True, (0, 2))
    last = blocks("hard-break-before-close", "centre")[-1]
    assert (last.text, last.hard_breaks, last.links[0][:2]) == ("c", False, (0, 1))
    # The space before a backslash break is unskipped.
    (spaced,) = blocks("hard-break-space")
    assert spaced.text == "aaa bbb\nccc"
    # A link closed straight after a break, centred: the break becomes a
    # newline when the next word arrives, and the link's end moves past it.
    for theme in ("default", "centre"):
        (linked,) = blocks("hard-break-in-link", theme)
        assert linked.text == "a\nb c\n d\ne"
        assert [link[:2] for link in linked.links] == [(0, 3), (4, 6), (7, 8)]
    # A formula at the end of a text that may go on is not one yet.
    (open_end,) = blocks("math-at-the-end", math=True, more_may_follow=True)
    assert open_end.formulas == () and open_end.text == "set $PATH=$"
    (closed_end,) = blocks("math-at-the-end", math=True)
    assert [formula.source for formula in closed_end.formulas] == ["PATH="]
    # An unclosed display block is its source so far, and says so.
    unclosed = blocks("math-unclosed", math=True)[-1]
    assert unclosed.text == "$$\\sum_{k=0}" and unclosed.formulas[0].state == "unclosed"
    assert unclosed.style.align is Align.CENTER and not unclosed.runs[0].flags
    # A tab in code is a tab (since 2026-10-12, pptmstr's P29: until then it
    # was spaces to its stop; `tests/test_host_requests_2.py` measures that
    # the library sets the two alike) and the blank end of a fence is dropped.
    code = [block for block in blocks("code") if isinstance(block, MarkdownCode)]
    assert code[0].text == "def f():\n\treturn 1" and code[0].language == "python"
    assert [block.text for block in code[1:]] == ["indented\n  more", "", "   "]


def test_generated_sources_are_described_directly_as_the_material_path_describes_them() -> None:
    atoms = [
        *("a", "bb", "ccc", " ", " ", "  ", "\n", "\n", "\n\n", "*", "**", "`", "``", "_"),
        *("[", "]", "(", ")", "(u)", "[x](u)", "[y](v)", "\\\n", "  \n", "\\", "$", "$$"),
        *("$x$", "$\\frac{1}{2}$", "$\\hat x$", "$$\n", "\n$$\n", "- ", "1. ", "3) ", "> "),
        *("    ", "\t", "# ", "## ", "---", "===", "```", "~~~", "|", "a|b", "\n-|-\n"),
        *("\n:-:|-:\n", "<b>", "<!--", "![i](p)", "&amp;", " ", "!", ".", "\r\n"),
        *("<br>", "[r]", "\n[r]: u\n", "\n---\n", "\n***\n"),
    ]
    rng = random.Random(20261010)
    names = sorted(THEMES)
    seen: collections.Counter[str] = collections.Counter()
    frozen = material_frozen.generated()
    assert len(frozen) == 500
    for number in range(500):
        source = "".join(rng.choice(atoms) for _ in range(rng.randint(1, 24)))
        theme_name = rng.choice(names)
        theme = THEMES[theme_name]
        references, math, more = (rng.random() < 0.5 for _ in range(3))
        # The sequence is the one the old path was asked about, draw for draw: a change to
        # `atoms` or to the seed is said here and not as 500 cases nobody froze.
        assert frozen[number] == (source, theme_name, references, math, more), number
        old = _material(source, theme, references=references, math=math, more_may_follow=more)
        new = _direct(
            source,
            theme,
            references=references,
            math=math,
            more_may_follow=more,
            refuses=_refuses,
        )
        assert _differences(old, new) == [], (source, references, math, more)
        seen += new.kinds
        seen["hard"] += sum(block.flags & 1 for block in new.blocks)
        seen["tables"] += len(new.tables)
        seen["runs"] += sum(len(block.runs) for block in new.blocks)
    # The generator is not allowed to pass by producing nothing of interest.
    for key in (
        "hard",
        "tables",
        "list markers",
        "links (Run.tag into a host table)",
        "formulas set (an explicit Formula run)",
        "formulas refused by advtext's builder (their source, in the code face)",
        "display formulas not closed yet (source so far)",
        "CodeBlock",
        "RuleBlock",
        "TextBlock QUOTE",
        "TextBlock HEADING_1",
    ):
        assert seen[key] >= 5, (key, seen[key])
    assert seen["runs"] > 300


def test_a_character_its_face_lacks_is_left_in_the_face_it_was_written_in() -> None:
    # U+03C0 is not in the code face and is in the prose face; U+4E2D is in none.
    source = "`aπb` and `c中d`\n"
    code = _DEFAULT.font_for(BlockKind.PARAGRAPH, direct._CODE)
    prose = _DEFAULT.style(BlockKind.PARAGRAPH).font
    assert not fontlib_metrics(code.key).has(0x03C0) and fontlib_metrics(prose.key).has(0x03C0)
    assert not fontlib_metrics(prose.key).has(0x4E2D)

    old = _material(source, _DEFAULT)
    new = _direct(source, _DEFAULT, math=True)
    # The same text either way: what was written.
    assert old.texts == new.texts == ["aπb and c中d"]
    code_role = typesetter.FACE_ROLE[code.face]
    # Directly, each code span is one run in the code face ...
    # (a run goes on over the space after it, as the old converter's does)
    assert [tuple(run)[:3] for run in new.blocks[0].runs] == [(0, 4, code_role), (8, 11, code_role)]
    # ... and through the material the two characters fall out of it: the
    # first was set from the prose face, the second replaced in it.
    assert [tuple(run)[:3] for run in old.blocks[0].runs] == [
        (0, 1, code_role),
        (2, 4, code_role),
        (8, 9, code_role),
        (10, 11, code_role),
    ]
    assert old.misfits[STOOD_IN] == 1 and STOOD_IN not in new.misfits
    # Nothing else differs.
    differing = _differences(old, new)
    assert len(differing) == 2
    assert differing[0].startswith("blocks[0]:") and differing[1].startswith("misfits:")
    assert old.blocks[0]._replace(runs=()) == new.blocks[0]._replace(runs=())


def test_a_formula_the_old_core_refuses_is_a_formula_run_unless_the_caller_refuses_it() -> None:
    source = "ok $x^2$ then $\\hat x$ end\n\n$$\n\\hat y\n$$\n"
    old = _material(source, _DEFAULT)
    assert old.texts == ["ok x^2 then $\\hat x$ end", "$$\\hat y$$"]

    new = describe_markdown(source, _DEFAULT, math=True)
    assert new.texts == ["ok x^2 then \\hat x end", "\\hat y"]
    assert [(run.start, run.end, run.flags) for run in new.blocks[0].runs] == [
        (3, 6, RUN_FORMULA),
        (12, 18, RUN_FORMULA),
    ]
    assert [(run.start, run.end, run.flags) for run in new.blocks[1].runs] == [
        (0, 6, RUN_DISPLAY_FORMULA)
    ]
    assert new.kinds["formulas set (an explicit Formula run)"] == 3

    # With the old decision handed in, the same description as the old path.
    asked: list[tuple[str, bool]] = []

    def refuses(formula: str, display: bool, size: int) -> bool:
        asked.append((formula, display))
        assert size == _DEFAULT.style(BlockKind.PARAGRAPH).font.size
        return _refuses(formula, display, size)

    assert _differences(old, _direct(source, _DEFAULT, math=True, refuses=refuses)) == []
    assert asked == [("x^2", False), ("\\hat x", False), ("\\hat y", True)]


@pytest.mark.parametrize("theme", ["default", "centre", "right"])
@pytest.mark.parametrize(
    "source",
    [
        "before\\\n$\\hat x$ after\n",
        "before  \n$\\hat x$\n",
        "a\\\n\\\n$$\\hat x$$ b\n",
        "*a*\\\n$\\hat x$\\\n$\\hat y$\n",
        "| h |\n|---|\n| a\\\n$\\hat x$ |\n",
    ],
)
def test_a_refused_formula_after_a_hard_break_starts_at_its_dollar(theme: str, source: str) -> None:
    """
    SW-R1's finding R5, reproduced before it was fixed: in a block set centred
    or ragged left a hard break's newline is written when the next node
    arrives, the range's start was read before that, and so a refused formula
    straight after a hard break began one character early, on the newline.
    """
    document = parse_markdown(source, THEMES[theme], math=True, refuses=lambda *_: True)
    found = 0
    for block in document.blocks:
        holders = (
            [cell for row in (block.header, *block.rows) for cell in row]
            if isinstance(block, MarkdownTable)
            else [block]
        )
        for holder in holders:
            assert isinstance(holder, direct.MarkdownCell | MarkdownText)
            for formula in holder.formulas:
                assert formula.state == "refused"
                marker = "$$" if formula.display else "$"
                shown = holder.text[formula.start : formula.end]
                assert shown == f"{marker}{formula.source}{marker}", (holder.text, formula)
                found += 1
    assert found >= 1


def test_an_empty_or_unclosed_formula_is_never_a_run_and_never_offered() -> None:
    def never(formula: str, display: bool, size: int) -> bool:
        raise AssertionError(f"asked about {formula!r}")

    document = parse_markdown("$$\n$$\n\n$$\nx^2\n", _DEFAULT, math=True, refuses=never)
    empty, unclosed = document.blocks
    assert isinstance(empty, MarkdownText) and isinstance(unclosed, MarkdownText)
    assert (empty.text, empty.formulas[0].state) == ("$$$$", "refused")
    assert (unclosed.text, unclosed.formulas[0].state) == ("$$x^2", "unclosed")
    for block in (empty, unclosed):
        assert not any(run.flags for run in block.runs)
    # With math off the hook is not called and a dollar is text.
    (plain,) = parse_markdown("a $x$ b", _DEFAULT, refuses=never).blocks
    assert isinstance(plain, MarkdownText) and plain.text == "a $x$ b" and not plain.formulas


def test_a_tail_described_again_keeps_its_style_indices_and_its_tags() -> None:
    document = parse_markdown(
        "# T\n\nA [one](https://a.example) link.\n\n> [two](https://b.example)\n", _DEFAULT
    )
    converter = MarkdownConverter(_DEFAULT, link_color=0xFF112233)
    whole = converter.describe(document.blocks)
    styles, targets = list(converter.styles), list(converter.targets)
    tail = converter.describe(document.blocks[1:], base=1)
    assert tail.blocks == whole.blocks[1:] and tail.links == whole.links
    assert converter.styles == styles and converter.targets == targets
    assert [converter.link_target(row.tag) for row in whole.links] == [
        "https://a.example",
        "https://b.example",
    ]
    assert converter.link_target(0) is None and converter.link_target(3) is None
    assert all(run.color == 0xFF112233 for block in whole.blocks for run in block.runs if run.tag)
    # Something that is no block is a Host block and a misfit, as there.
    odd = converter.describe([object()])
    assert odd.blocks[0].kind == KIND_HOST and odd.misfits["block type object"] == 1


def _faces(block: Any, base: int) -> list[tuple[int, int, int]]:
    """(face, flags, tag) of every character of a described block, runs laid out flat."""
    out = [(base, 0, 0)] * len(block.text)
    for run in block.runs:
        for at in range(run.start, run.end):
            out[at] = (run.face or base, run.flags, run.tag)
    return out


def _cells_of(block: Any) -> list[Any]:
    """Every cell of a described table in reading order; none for any other block."""
    return [cell for row in block.rows for cell in row]


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_the_default_differs_from_the_converters_runs_only_at_white_space(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    sources = (
        [source, *(CORPUS[name] for name in sorted(CORPUS))] if path == _DEMOS[0] else [source]
    )
    moved = 0
    for one in sources:
        ours = describe_markdown(one, _DEFAULT, math=True, refuses=_refuses)
        theirs = _direct(one, _DEFAULT, math=True, refuses=_refuses)
        for name in ("styles", "links", "tables", "texts", "misfits", "kinds"):
            assert getattr(ours, name) == getattr(theirs, name), name
        assert len(ours.blocks) == len(theirs.blocks)
        for a, b in zip(ours.blocks, theirs.blocks, strict=True):
            assert a._replace(runs=(), rows=()) == b._replace(runs=(), rows=())
            base = ours.styles[a.style].Face
            # A block's own text, or each cell of a table: a cell is text and
            # runs as a block is.
            held = [(a, b), *zip(_cells_of(a), _cells_of(b), strict=True)]
            for one, other in held:
                assert one.text == other.text
                faces = zip(_faces(one, base), _faces(other, base), strict=True)
                for at, (x, y) in enumerate(faces):
                    if one.text[at].isspace():
                        moved += x != y
                    else:
                        assert x == y, (one.text, at)
    if path.name in ("sample.md", "math.md", "script.md"):
        assert moved > 0


def _space_widths(face_role: int, size: int) -> set[int]:
    """The widths the old core gave an interword glue in a face: plain, and after a sentence."""
    return material_frozen.space_widths(face_role, size)


def _spaces_set_in_another_face(path: Path, converter_spaces: bool) -> tuple[int, int]:
    """
    (spaces, spaces whose face is not the one the old core measured its glue in).

    For every text block and table cell of the demo at `path`: the natural
    widths of the material's interword glue, in order (frozen: one list a
    text block or cell, as `build_document` made them), against the spaces
    of the direct text that are not inside a formula's source, each in the
    face the direct runs give it.
    """
    source = path.read_text(encoding="utf-8")
    widths = material_frozen.demo(str(path.relative_to(_ROOT / "demo")))["glue"]
    parsed = parse_markdown(
        source, _DEFAULT, math=True, refuses=_refuses, converter_spaces=converter_spaces
    ).blocks
    pairs: list[tuple[Any, Any]] = []
    for new in parsed:
        if isinstance(new, MarkdownText):
            pairs.append((new, new.style))
        elif isinstance(new, MarkdownTable):
            for now in (new.header, *new.rows):
                pairs.extend((cell, new.style) for cell in now)
    # One list of glue for each text block and each cell the old core made, in order.
    assert len(pairs) == len(widths)
    spaces = wrong = 0
    for (block, style), glue in zip(pairs, widths, strict=True):
        base = typesetter.FACE_ROLE[style.font.face]
        faces = [base] * len(block.text)
        inside = [False] * len(block.text)
        for run in block.runs:
            for at in range(run.start, run.end):
                faces[at] = run.face or base
                inside[at] = bool(run.flags)
        written = [
            at for at, character in enumerate(block.text) if character == " " and not inside[at]
        ]
        assert len(written) == len(glue), block.text
        for at, width in zip(written, glue, strict=True):
            spaces += 1
            wrong += width not in _space_widths(faces[at], style.font.size)
    return spaces, wrong


def test_every_space_is_in_the_face_the_old_core_measured_its_glue_in() -> None:
    spaces = wrong = converter_wrong = 0
    for path in _DEMOS:
        counted, missed = _spaces_set_in_another_face(path, False)
        spaces += counted
        wrong += missed
        converter_wrong += _spaces_set_in_another_face(path, True)[1]
    assert spaces > 5000 and wrong == 0
    # The same count over `Converter`'s runs: the spaces it sets in the face
    # of the run before them. If this ever reads 0 the check above has
    # stopped telling the two apart.
    assert converter_wrong > 50


@pytest.mark.parametrize(
    ("source", "text", "runs"),
    [
        # The space after a run is the paragraph's; a space inside one is the run's.
        ("`ab` cd", "ab cd", [(0, 2, 5)]),
        ("`a b` cd", "a b cd", [(0, 3, 5)]),
        ("**ab** cd *ef* gh", "ab cd ef gh", [(0, 2, 2), (6, 8, 3)]),
        ("**ab cd** ef", "ab cd ef", [(0, 5, 2)]),
        # A space written inside the marks is set with them, at either end.
        ("x ` a` y", "x  a y", [(2, 4, 5)]),
        ("x **a **y", "x **a **y", []),
        ("x *a\nb* y", "x a b y", [(2, 5, 3)]),
        # A hard break's newline is in no run: the run ends and begins again.
        ("**a\\\nb** c", "a\nb c", [(0, 1, 2), (2, 3, 2)]),
        # Two runs with the paragraph's space between them stay two.
        ("**a** **b**", "a b", [(0, 1, 2), (2, 3, 2)]),
        ("**a** `b` *c*", "a b c", [(0, 1, 2), (2, 3, 5), (4, 5, 3)]),
        # A code span that is one space is a space in the code face.
        ("a` `b", "a b", [(1, 2, 5)]),
        # A formula's run is its source and never a space beside it.
        ("a $x$ b", "a x b", [(2, 3, 0)]),
        # A hard break unskips a space whatever face it was in.
        ("a `b `\\\nc", "a b\nc", [(2, 3, 5)]),
        ("**a** \\\nb", "a\nb", [(0, 1, 2)]),
    ],
)
def test_a_space_is_set_in_the_face_of_the_text_it_was_written_in(
    source: str, text: str, runs: list[tuple[int, int, int]]
) -> None:
    (block,) = parse_markdown(source, _DEFAULT, math=True).blocks
    assert isinstance(block, MarkdownText)
    assert block.text == text
    assert [(run.start, run.end, run.face) for run in block.runs] == runs


# ---------------------------------------------------------------------------
# 3. Tables and the source map
# ---------------------------------------------------------------------------


def test_every_table_cell_is_the_text_and_runs_the_material_path_gave_it() -> None:
    """
    Cell by cell against what `Converter._text_of` read out of the old core's
    `TableBlock`s (frozen: text, runs before any link tag, whether a hard
    break, the link ranges, whether a header cell), and each table's
    alignments, indent and shape against the block's own.
    """
    cells = 0
    for path in _DEMOS:
        source = path.read_text(encoding="utf-8")
        frozen = material_frozen.demo(str(path.relative_to(_ROOT / "demo")))
        parsed = parse_markdown(
            source, _DEFAULT, math=True, refuses=_refuses, converter_spaces=True
        ).blocks
        old_description = _material(source, _DEFAULT)
        assert len(old_description.blocks) == len(parsed)
        tables = [at for at, block in enumerate(parsed) if isinstance(block, MarkdownTable)]
        # A table there is a table here, block for block.
        assert tables == old_description.tables and len(tables) == len(frozen["tables"])
        for at, old in zip(tables, frozen["tables"], strict=True):
            new = parsed[at]
            assert isinstance(new, MarkdownTable)
            assert [align.name for align in new.aligns] == old["aligns"]
            assert new.style == _DEFAULT.style(BlockKind.TABLE)
            assert new.left_indent == old["left_indent"]
            assert len(new.header) == old["header"] and len(new.rows) == old["rows"]
            for before, after in zip(old["cells"], (new.header, *new.rows), strict=True):
                assert len(before) == len(after)
                for was, now in zip(before, after, strict=True):
                    text, runs, hard, ranges, header = was
                    assert (now.text, list(now.runs), now.hard_breaks) == (
                        text,
                        [RunDescription(*run) for run in runs],
                        hard,
                    )
                    assert [list(link) for link in now.links] == ranges
                    assert now.header == header
                    cells += 1
    assert cells >= 129


def test_a_table_is_one_block_whose_cells_carry_the_converters_tags() -> None:
    source = (
        "See [first](https://a.example).\n\n"
        "| left | mid | right |\n|:--|:-:|--:|\n"
        "| [**b** c](https://b.example) | $x^2$ | `d` |\n| [e](https://a.example) | f |\n"
    )
    document = parse_markdown(source, _DEFAULT, math=True, converter_spaces=True)
    converter = MarkdownConverter(_DEFAULT, link_color=0xFF00FF00)
    described = converter.describe(document.blocks)
    # The whole description is what the old converter made of the same source.
    old = _material(source, _DEFAULT, link_color=0xFF00FF00)
    assert _differences(old, described) == []
    table = described.blocks[1]
    assert described.tables == [1] and table.kind == KIND_TABLE and not described.misfits
    assert table.text == "left\tmid\tright\nb c\tx^2\td\ne\tf\t" == described.texts[1]
    assert table.runs == () and table.flags == BLOCK_TABLE_HEADER and table.extent == 0.0
    assert [column.align for column in table.columns] == [1, 2, 3]
    assert all(column.width == 0.0 == column.share for column in table.columns)
    # Tags in reading order, a table's cells included; a URL seen twice has one.
    assert converter.targets == ["https://a.example", "https://b.example"]
    assert [
        (row.block, table.text[row.start : row.end], row.tag) for row in described.links[1:]
    ] == [
        (1, "b c", 2),
        (1, "e", 1),
    ]

    header, (first, formula, code), (again, last, filled) = table.rows
    assert [cell.text for cell in header] == ["left", "mid", "right"]
    assert first.text == "b c" and [converter.link_target(run.tag) for run in first.runs] == [
        "https://b.example",
        "https://b.example",
    ]
    assert first.runs[0].face == 2 and first.runs[1].face == 0
    assert all(run.color == 0xFF00FF00 for run in first.runs)
    assert formula.text == "x^2" and formula.runs[0].flags == RUN_FORMULA
    assert code.text == "d" and code.runs[0].face == 5
    # A short row is filled out by the parser.
    assert again.runs[0].tag == 1 and converter.link_target(1) == "https://a.example"
    assert last.text == "f" and filled == CellDescription("")


def test_a_table_may_state_its_columns_as_widths_or_as_shares() -> None:
    """
    What a host that lets a column be dragged hands over: `widths` in scaled
    points become pixels, `shares` are passed on, and either is ignored
    unless there is one a column.
    """
    document = parse_markdown("| a | b |\n|--:|:-:|\n| 1 | 2 |\n", _DEFAULT)
    (table,) = document.blocks
    assert isinstance(table, MarkdownTable) and table.widths == () == table.shares
    converter = MarkdownConverter(_DEFAULT)
    (plain,) = converter.describe([table]).blocks
    assert [(c.align, c.width, c.share) for c in plain.columns] == [(3, 0.0, 0.0), (2, 0.0, 0.0)]
    widths = (sp_from_px(120.0, _DEFAULT.px_per_inch), sp_from_px(80.5, _DEFAULT.px_per_inch))
    (sized,) = converter.describe([replace(table, widths=widths)]).blocks
    assert [column.width for column in sized.columns] == [converter.px(w) for w in widths]
    assert sized._replace(columns=plain.columns) == plain
    (shared,) = converter.describe([replace(table, shares=(1.0, 3.0))]).blocks
    assert [(c.width, c.share) for c in shared.columns] == [(0.0, 1.0), (0.0, 3.0)]
    (short,) = converter.describe([replace(table, widths=widths[:1])]).blocks
    assert short == plain
    # A table that states its columns is another value: a view sees it changed.
    assert replace(table, widths=widths) != table


def test_the_two_converters_give_a_table_the_same_block() -> None:
    """The old converter's half is frozen: its description, and its table of link targets."""
    tables = 0
    for path in _DEMOS:
        source = path.read_text(encoding="utf-8")
        parsed = parse_markdown(
            source, _DEFAULT, math=True, refuses=_refuses, converter_spaces=True
        ).blocks
        ours = MarkdownConverter(_DEFAULT, link_color=0xFF00FF00)
        old, new = _material(source, _DEFAULT, link_color=0xFF00FF00), ours.describe(parsed)
        # Cells, runs, tags, columns and the header flag: the same block.
        assert _differences(old, new) == []
        for at in new.tables:
            block = parsed[at]
            assert isinstance(block, MarkdownTable)
            rows = [block.header, *block.rows] if block.header else list(block.rows)
            assert new.blocks[at].kind == KIND_TABLE
            assert new.texts[at] == direct.table_text([cell.text for cell in row] for row in rows)
            assert new.texts[at].count("\n") == len(rows) - 1 and "\t" in new.texts[at]
            assert [[cell.text for cell in row] for row in new.blocks[at].rows] == [
                [cell.text for cell in row] for row in rows
            ]
            tables += 1
        assert ours.targets == material_frozen.targets(source, link_color=0xFF00FF00)
    assert tables >= 9
    assert direct.table_text([["a", "b"], ["c"]]) == typesetter.table_text([["a", "b"], ["c"]])
    assert direct.table_text([]) == "" and direct.table_text([["a", "b"], ["c"]]) == "a\tb\nc"


@pytest.mark.parametrize("path", _DEMOS, ids=lambda p: str(p.relative_to(_ROOT / "demo")))
def test_the_source_map_is_build_documents(path: Path) -> None:
    """
    Against the source map `advtext.markdown.build_document` answered
    (frozen: each block's span and top, lines and offsets).
    """
    source = path.read_text(encoding="utf-8")
    built = material_frozen.demo(str(path.relative_to(_ROOT / "demo")))["sources"]
    parsed = parse_markdown(source, _DEFAULT, math=True)
    assert [material_frozen.source_row(where) for where in parsed.sources] == built
    assert len(parsed.sources) == len(parsed.blocks)
    for name in sorted(CORPUS):
        mapped = parse_markdown(CORPUS[name], _DEFAULT, math=True).sources
        frozen = material_frozen.corpus_sources(name)
        assert [material_frozen.source_row(where) for where in mapped] == frozen, name


# ---------------------------------------------------------------------------
# 4. The stream
# ---------------------------------------------------------------------------


def _pieces(source: str, chunk: int) -> list[str]:
    if chunk == 0:
        return source.splitlines(keepends=True)
    return [source[at : at + chunk] for at in range(0, len(source), chunk)]


def _replay(
    source: str, chunk: int, theme: Theme = _DEFAULT, converter_spaces: bool = False
) -> MarkdownStream:
    """
    Feed `source` in pieces, holding the stream to one parse of what it has after each.
    """
    spaces = converter_spaces
    stream = MarkdownStream(theme, math=True, refuses=_refuses, converter_spaces=spaces)
    raw = seen = ""
    committed: tuple[Any, ...] = ()
    revision = stream.revision
    for piece in _pieces(source, chunk):
        stream.append(piece)
        raw += piece
        # A carriage return that ends a piece is held until the next one.
        told = raw[:-1] if raw.endswith("\r") else raw
        told = told.replace("\r\n", "\n").replace("\r", "\n")
        changed = told != seen
        seen = told
        assert stream.pending == changed
        blocks = stream.blocks
        assert stream.revision == revision + changed and not stream.pending
        revision += changed
        whole = parse_markdown(
            seen,
            theme,
            references=False,
            math=True,
            more_may_follow=True,
            refuses=_refuses,
            converter_spaces=spaces,
        )
        assert blocks == whole.blocks, (chunk, len(seen), seen[-40:])
        assert stream.sources == whole.sources, (chunk, len(seen))
        assert stream.source == seen
        # Committed blocks only ever grow at the end, and stay the same objects.
        now = stream.committed
        assert len(now) >= len(committed)
        assert all(a is b for a, b in zip(committed, now, strict=False))
        committed = now
        assert stream.committed + stream.live == blocks
    stream.close()
    seen = raw.replace("\r\n", "\n").replace("\r", "\n")
    assert stream.source == seen
    whole = parse_markdown(
        seen, theme, references=False, math=True, refuses=_refuses, converter_spaces=spaces
    )
    assert stream.blocks == whole.blocks and stream.live == () and stream.closed
    assert stream.sources == whole.sources
    assert all(a is b for a, b in zip(committed, stream.committed, strict=False))
    return stream


# The four replays `tests/test_typeset_stream_view.py` runs, and each demo by
# the line as well.
_REPLAYS = [("sample.md", 24), ("sample.md", 5), ("tables.md", 24), ("math.md", 24)]
_REPLAYS += [(str(path.relative_to(_ROOT / "demo")), 0) for path in _DEMOS]
_REPLAYS += [(str(path.relative_to(_ROOT / "demo")), 61) for path in _DEMOS]


@pytest.mark.parametrize(("name", "chunk"), _REPLAYS, ids=lambda value: str(value))
def test_a_stream_is_one_parse_of_what_it_has_after_every_piece(name: str, chunk: int) -> None:
    source = (_ROOT / "demo" / name).read_text(encoding="utf-8")
    stream = _replay(source, chunk)
    # The description at the end is the whole source's, field for field.
    final = MarkdownConverter(_DEFAULT).describe(stream.blocks)
    whole = describe_markdown(source, _DEFAULT, references=False, math=True, refuses=_refuses)
    assert _differences(whole, final) == []
    assert len(stream.committed) == len(final.blocks) > 0
    # And with the old converter's runs, it is the material path's for the same source.
    stream = _replay(source, chunk, converter_spaces=True)
    final = MarkdownConverter(_DEFAULT).describe(stream.blocks)
    assert _differences(_material(source, _DEFAULT, references=False), final) == []


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_an_awkward_source_streams_a_character_at_a_time(name: str) -> None:
    _replay(CORPUS[name], 1)
    _replay(CORPUS[name], 3, THEMES["centre"])


@pytest.mark.parametrize("name", ["ADVERSARIAL", "DOCUMENTS", "REVIEW_5", "TABLES"])
def test_the_sources_the_old_stream_is_held_to_stream_here_too(name: str) -> None:
    # The corpora of the old stream's own tests (`tests/test_stream.py`, deleted with
    # `advtext.stream` in tranche 5; the sources are kept in
    # `tests/data/stream_corpora.json`): what `StreamDocument`'s commit rule was argued
    # from and tested on. The same rule is here, so the same sources.
    corpus = material_frozen.corpora()[name]
    assert len(corpus) > 30 and all(isinstance(source, str) for source in corpus.values())
    for source in corpus.values():
        _replay(source, 1)
        _replay(source, 3, THEMES["centre"])
        _replay(source, 0)


def test_what_the_commit_rule_must_not_commit_early() -> None:
    # `advtext.stream`'s four: an unfinished line can still become anything.
    for source in (
        "para\n#tag\n\nend\n",
        "para\n```py`x\n\nend\n",
        "para\n\n<path> more\n\nend\n",
        "a|b\n-|-x\n\nend\n",
        "para\n-\n\nend\n",
        "- a\n\n  still a\n\n  ```\n  code\n  ```\n\n1. new list\n",
    ):
        for chunk in (1, 2, 5):
            _replay(source, chunk)
    stream = MarkdownStream(_DEFAULT)
    stream.append("para\n#")
    assert stream.committed == () and len(stream.live) == 2
    stream.append("tag\n")
    assert stream.committed == () and [block.text for block in stream.live] == ["para #tag"]
    stream.append("\nnext")
    # Not yet: `next` is an unfinished line, and the boundary is decided on whole ones.
    assert stream.committed == () and len(stream.live) == 2
    stream.append("\n")
    assert [block.text for block in stream.committed] == ["para #tag"]
    assert [block.text for block in stream.live] == ["next"]


def test_a_live_block_that_did_not_change_is_the_same_object() -> None:
    stream = MarkdownStream(_DEFAULT)
    stream.append("- one\n- two\n- thr")
    first = stream.blocks
    assert stream.committed == () and len(first) == 3
    stream.append("ee")
    second = stream.blocks
    assert second[0] is first[0] and second[1] is first[1] and second[2] is not first[2]
    # White space at the end changes no block: all three are the objects they were.
    stream.append("  ")
    third = stream.blocks
    assert all(a is b for a, b in zip(second, third, strict=True))
    # And a block keeps its identity through its commit.
    stream.append("\n\nafter\n")
    fourth = stream.blocks
    assert stream.committed == fourth[:3] and all(
        a is b for a, b in zip(third, fourth[:3], strict=True)
    )
    # So "the first block that is not the object it was" is the first that changed.
    stream.append(" more")
    fifth = stream.blocks
    assert [a is b for a, b in zip(fourth, fifth, strict=True)] == [True, True, True, False]


# -- the shortcuts: a long list, quote, fence or table is not read from its top --


def _long(name: str, units: int) -> str:
    head, unit = _LONG[name]
    return head + "".join(unit.format(n=number) for number in range(1, units + 1))


_LONG: dict[str, list[str]] = material_frozen.corpora()["LONG"]
_LEAVING: dict[str, list[str]] = material_frozen.corpora()["LEAVING"]
_STREAMED_TABLES: dict[str, str] = material_frozen.corpora()["TABLES"]
"""
The old stream tests' long containers, fences left by a line, and tables: sources only.
"""

_LONG_TOP = {
    "fence": ("```python\n", "value_{n} = compute(n={n}, scale=1.5)\n"),
    "tilde-fence": ("~~~\n", "\tline {n} with a tab\n\n"),
    "table": (
        "| a | b | c |\n|:--|:-:|--:|\n",
        "| row {n} | **v** {n} | [l](https://e.example/{n}) |\n",
    ),
}
"""
A head and a unit to repeat, for the two blocks followed at top level.
"""


def _long_top(name: str, units: int) -> str:
    head, unit = _LONG_TOP[name]
    return head + "".join(unit.format(n=number) for number in range(1, units + 1))


def _replay_two_themes(source: str, pieces: list[str]) -> MarkdownStream:
    """
    `_replay` for a stream whose tail is built with another theme than it commits with.

    What is committed is the head of one parse of everything so far in the
    host's theme, what is live is the rest of one parse in the live theme,
    and the sources are one parse's. This is the only place the kept
    children of a long list are held in two themes at once.
    """
    ragged = _aligned(_DEFAULT, Align.CENTER)
    stream = MarkdownStream(_DEFAULT, math=True, refuses=_refuses, live_theme=ragged)
    seen = ""
    for piece in pieces:
        stream.append(piece)
        seen += piece
        blocks = stream.blocks
        more: dict[str, Any] = {"references": False, "math": True, "refuses": _refuses}
        hosts = parse_markdown(seen, _DEFAULT, more_may_follow=True, **more)
        lives = parse_markdown(seen, ragged, more_may_follow=True, **more)
        cut = len(stream.committed)
        assert stream.committed == hosts.blocks[:cut], (len(seen), seen[-40:])
        assert stream.live == lives.blocks[cut:], (len(seen), seen[-40:])
        assert blocks == stream.committed + stream.live
        assert stream.sources == hosts.sources, (len(seen), seen[-40:])
    stream.close()
    assert stream.blocks == parse_markdown(seen, _DEFAULT, **more).blocks
    return stream


@pytest.mark.parametrize("source", markdown_tests.NESTED_SOURCES)
def test_a_nested_source_streams_as_one_parse_from_wherever_reading_resumes(source: str) -> None:
    """
    `tests/test_markdown.py`'s sixteen sources for `_resume_point`: lists in
    lists, quotes in items, fences and tables inside both, lazy lines. Read a
    character at a time, three at a time, by the line, and with two themes.
    """
    for chunk in (1, 3, 0):
        _replay(source, chunk)
    _replay(source, 2, THEMES["centre"])
    _replay_two_themes(source, _pieces(source, 1))
    _replay_two_themes(source, _pieces(source, 0))


@pytest.mark.parametrize("name", sorted(_LONG))
def test_a_long_container_streams_as_one_parse_after_every_piece(name: str) -> None:
    source = _long(name, 12)
    _replay(source, 0)
    _replay(source, 7)
    _replay(source, 1)
    _replay_two_themes(source, material_frozen.tokens(source))


@pytest.mark.parametrize("name", sorted(_LEAVING))
def test_a_fence_in_a_container_and_the_line_that_leaves_it_stream_as_one_parse(name: str) -> None:
    head, unit, after = _LEAVING[name]
    source = head + unit * 4 + after
    _replay(source, 1)
    _replay(source, 0)
    _replay_two_themes(source, _pieces(source, 1))
    _replay(source + "\n\nand a paragraph after\n", 3)


@pytest.mark.parametrize("name", sorted(_LONG_TOP))
def test_a_long_fence_or_table_streams_as_one_parse_after_every_piece(name: str) -> None:
    source = _long_top(name, 9) + "\nA paragraph after it.\n\n" + _long_top(name, 3)
    _replay(source, 0)
    _replay(source, 1)
    _replay(source, 5, THEMES["centre"])
    _replay_two_themes(source, _pieces(source, 1))
    _replay_two_themes(source, material_frozen.tokens(source))


@pytest.mark.parametrize("name", sorted(_STREAMED_TABLES))
def test_a_table_streams_as_one_parse_in_two_themes(name: str) -> None:
    source = _STREAMED_TABLES[name]
    _replay_two_themes(source, _pieces(source, 1))
    _replay_two_themes(source, _pieces(source, 0))


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """
    The length of every text handed to markdown-it from now on.
    """
    handed: list[int] = []
    real = direct._parse

    def parse(parser: Any, source: str, *more: Any) -> Any:
        handed.append(len(source))
        return real(parser, source, *more)

    monkeypatch.setattr(direct, "_parse", parse)
    return handed


@pytest.mark.parametrize("units", [20, 160])
@pytest.mark.parametrize(
    "name", ["list", "numbered-steps", "quote", "list-in-quote", "fence", "tilde-fence", "table"]
)
def test_what_the_parser_is_handed_for_a_piece_does_not_grow_with_the_block(
    name: str, units: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Counts, not milliseconds, as `tests/test_stream.py` held `StreamDocument`
    to it: every text given to markdown-it while the source streams in
    token-sized pieces is recorded, and the longest must be under a bound of
    a few repeated units -- the same bound at 20 units as at 160. Before
    tranche 3 the longest was the whole source (SW-2 measured 17.5 ms a read
    by the 300th list item).

    `fence-in-item` of that file's `LONG` is not here: a fence INSIDE a list
    item is not followed a line at a time by this class, and the test below
    says so.
    """
    if name in _LONG_TOP:
        source, (head, unit) = _long_top(name, units), _LONG_TOP[name]
    else:
        source, (head, unit) = _long(name, units), _LONG[name]
    handed = _spy(monkeypatch)
    stream = MarkdownStream(_DEFAULT)
    received = ""
    pieces = material_frozen.tokens(source)
    checks = {len(pieces) * tenth // 10 for tenth in range(1, 10)} | {len(pieces) - 2}
    for number, piece in enumerate(pieces):
        stream.append(piece)
        received += piece
        assert stream.revision
        if number in checks:
            parses = len(handed)
            expected = parse_markdown(received, _DEFAULT, references=False)
            del handed[parses:]  # the comparison's own parse is not the stream's
            assert stream.blocks == expected.blocks
            assert stream.sources == expected.sources
    bound = 4 * len(unit.format(n=units)) + len(head) + 40
    assert max(handed) <= bound, f"the parser was handed {max(handed)} characters for one piece"
    assert len(source) > 4 * bound or units == 20, "the source is too short to show anything"
    assert stream.committed == ()


def test_a_fence_inside_a_list_item_is_still_read_whole_while_it_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The one shortcut of `StreamDocument`'s not carried over, stated as a test
    so that it is a known cost and not a surprise: an open fence inside an
    item is its container's last child, and every read hands the parser all
    of it. When this starts failing because someone followed it, delete it
    and add `fence-in-item` to the test above.
    """
    source = _long("fence-in-item", 160)
    handed = _spy(monkeypatch)
    stream = MarkdownStream(_DEFAULT)
    for piece in source.splitlines(keepends=True):
        stream.append(piece)
        assert stream.revision
    assert max(handed) > len(source) * 0.9
    assert stream.blocks == parse_markdown(source, _DEFAULT, references=False).blocks


def test_a_followed_fence_commits_when_its_closing_line_ends_and_a_table_at_its_blank_line() -> (
    None
):
    """
    One line earlier than the rule for every other block, as in
    `advtext.stream`: the alternative is the whole block read again for
    every piece of the line that follows it.
    """
    stream = MarkdownStream(_DEFAULT)
    stream.append("```py\nx = 1\ny = 2\n")
    assert stream.committed == () and [type(block) for block in stream.live] == [MarkdownCode]
    stream.append("```")
    assert stream.committed == (), "an unfinished closing line can still become content"
    stream.append("\n")
    (code,) = stream.committed
    assert isinstance(code, MarkdownCode) and code.text == "x = 1\ny = 2" and stream.live == ()
    stream.append("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 ")
    (table,) = stream.live
    assert isinstance(table, MarkdownTable) and len(table.rows) == 2
    first_row = table.rows[0]
    stream.append("| 4 |\n")
    (table,) = stream.live
    assert len(table.rows) == 2 and table.rows[0] is first_row, "a row read once is kept"
    assert len(stream.committed) == 1
    stream.append("\n")
    assert len(stream.committed) == 2 and stream.live == ()
    assert stream.committed[1] == table
    stream.close()
    whole = parse_markdown(stream.source, _DEFAULT, references=False)
    assert stream.blocks == whole.blocks and stream.sources == whole.sources


def test_the_kept_children_of_a_long_list_are_the_same_objects_read_after_read() -> None:
    """
    A view finds the first block that `is not` the one it had. In a list
    being written that must be the item being written (or the one before
    it, which is read again with it), not the top of the list.
    """
    source = _long("list", 40)
    stream = MarkdownStream(_DEFAULT, live_theme=_aligned(_DEFAULT, Align.LEFT))
    before: tuple[Any, ...] = ()
    for piece in material_frozen.tokens(source):
        stream.append(piece)
        now = stream.blocks
        changed = next(
            (index for index, (a, b) in enumerate(zip(before, now, strict=False)) if a is not b),
            min(len(before), len(now)),
        )
        assert changed >= len(before) - 2, (changed, len(before))
        before = now
    assert len(before) == 40 and stream.committed == ()


def test_the_resume_helpers_copied_from_markdown_have_not_drifted() -> None:
    """
    `_resume_point` and what it calls are `advtext.markdown`'s, copied here
    because that module imports the layout core (the module says so where
    they stand). For as long as both exist, their source is the same text.
    The two patterns that were `advtext.stream`'s are held to what they were
    when that module was deleted (frozen).
    """
    import inspect

    for name in ("_Resume", "_opens", "_resume_point", "_opener", "_step_over"):
        ours = inspect.getsource(getattr(direct, name))
        assert ours == inspect.getsource(getattr(markdown_module, name)), name
    for name in ("_CONTAINER_OPENS", "_CONTAINER_CLOSES"):
        assert getattr(direct, name) == getattr(markdown_module, name), name
    for name in ("_ITEM_OPENER", "_QUOTE_OPENER"):
        assert getattr(direct, name).pattern == getattr(markdown_module, name).pattern, name
    for name in ("_FENCE_OPENER", "_TABLE_DELIMITER"):
        assert getattr(direct, name).pattern == material_frozen.stream_pattern(name), name


def test_line_ends_closing_and_appending_after_the_close() -> None:
    stream = MarkdownStream(_DEFAULT)
    stream.append("one\r")
    assert stream.source == "one"
    stream.append("\ntwo\r\n\rthree")
    assert stream.source == "one\ntwo\n\nthree"
    stream.append("")
    assert not stream.pending or stream.revision
    revision = stream.revision
    assert stream.revision == revision
    stream.append("\r")
    stream.close()
    stream.close()
    assert stream.source == "one\ntwo\n\nthree\n" and stream.live == ()
    assert [block.text for block in stream.committed] == ["one two", "three"]
    with pytest.raises(ValueError, match="closed"):
        stream.append("more")
    empty = MarkdownStream(_DEFAULT)
    assert empty.blocks == () and empty.revision == 0 and empty.theme is _DEFAULT
    empty.close()
    assert empty.blocks == () and empty.revision == 1


def test_a_live_theme_sets_the_tail_and_a_block_commits_in_the_hosts() -> None:
    ragged = _aligned(_DEFAULT, Align.LEFT)
    stream = MarkdownStream(_DEFAULT, live_theme=ragged)
    stream.append("first paragraph\n\nsecond\n")
    (committed,) = stream.committed
    (live,) = stream.live
    assert committed.style.align is Align.JUSTIFY and live.style.align is Align.LEFT
    stream.append("paragraph")
    (live,) = stream.live
    assert live.style.align is Align.LEFT and live.text == "second paragraph"
    stream.close()
    assert [block.style.align for block in stream.committed] == [Align.JUSTIFY, Align.JUSTIFY]


def test_a_math_closer_at_the_end_of_a_stream_waits_for_what_follows() -> None:
    stream = MarkdownStream(_DEFAULT, math=True)
    stream.append("set $PATH=$")
    (block,) = stream.live
    assert block.text == "set $PATH=$" and not block.formulas
    stream.append("HOME")
    (block,) = stream.live
    assert block.text == "set $PATH=$HOME" and not block.formulas
    other = MarkdownStream(_DEFAULT, math=True)
    other.append("so $x$")
    other.close()
    (block,) = other.committed
    assert block.text == "so x" and [formula.source for formula in block.formulas] == ["x"]


# ---------------------------------------------------------------------------
# 5. The library
# ---------------------------------------------------------------------------

_LIBRARY = r"""
import json, re, sys
from pathlib import Path
from advtext import typesetter

ts = typesetter.module()
if ts is None:
    print(json.dumps({"module": False, "reason": typesetter.reason()}))
    sys.exit(0)

from imgui_bundle import imgui
from advtext import typeset_markdown as direct
from advtext.theme import Theme
from advtext.ui.typeset_stream_view import TypesetStreamView
from advtext.ui.typeset_view import TypesetView

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "tests"))
import material_frozen
report = {"module": True, "files": {}}
imgui.create_context()
io = imgui.get_io()
io.display_size = imgui.ImVec2(1200.0, 800.0)
io.delta_time = 1.0 / 60.0
io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
report["ready"] = typesetter.load_fonts() and typesetter.ready()
theme = Theme.build()
style = typesetter.base_style(theme, 0xFFFFFFFF)

def laid(described, width=600.0):
    doc = ts.Document()
    whole = doc.set_blocks(described.blocks, typesetter.block_styles(described.styles))
    edit = doc.edit_error.code
    doc.layout(width, style)
    doc.layout_window(0.0, 1.0e9)
    return doc, whole, edit

# 1. A Document takes every demo's direct description, and sets it as it sets
#    the material path's (frozen: what the old converter described, laid out here).
for path in sorted((ROOT / "demo").rglob("*.md")):
    source = path.read_text(encoding="utf-8")
    described = direct.describe_markdown(source, theme, math=True)
    material = material_frozen.description(source)
    doc, whole, edit = laid(described)
    other, _, _ = laid(material)
    same, _, _ = laid(direct.describe_markdown(source, theme, math=True, converter_spaces=True))
    same_height = same.size()[1]
    same.close()
    vertices, _ = doc.draw_to_buffers((0.0, 0.0), (0.0, 0.0, 600.0, 1.0e9))
    # A block copies back as its text, but for one thing measured here and not
    # this module's doing (the material path's description is the same): two
    # spaces in a row in a paragraph -- a code span ending in one, then a
    # space -- are set and copied by the library as one. Offsets after them
    # still fit. `collapsed` counts the blocks where that happened.
    copied = [doc.range_text(((i, 0), (i, len(text)))) for i, text in enumerate(described.texts)]
    collapsed = [
        i for i, text in enumerate(described.texts)
        if copied[i] != text and described.blocks[i].kind != direct.KIND_CODE
        and copied[i] == re.sub(" {2,}", " ", text)
    ]
    report["files"][str(path.relative_to(ROOT / "demo"))] = {
        "blocks": [len(described.blocks), len(doc)],
        "set_blocks": whole,
        "edit_error": edit,
        "block_errors": [i for i in range(len(doc)) if doc.block_error(i).code],
        "vertex_bytes": len(vertices),
        "heights": [same_height, other.size()[1]],
        "height": doc.size()[1],
        "texts": all(
            copied[i] == text or i in collapsed for i, text in enumerate(described.texts)
        ),
        "collapsed": len(collapsed),
        "same_copy": copied == [
            other.range_text(((i, 0), (i, len(text)))) for i, text in enumerate(material.texts)
        ],
    }
    doc.close()
    other.close()

# 2. A formula the library will not set: where a caller learns of it.
described = direct.describe_markdown(
    "fine $x^2$ here\n\nnot $\\hat x$ here\n\n$$\n\\frac{1\n$$\n", theme, math=True
)
doc, whole, edit = laid(described)
report["refused"] = {
    "set_blocks": whole,
    "edit_error": edit,
    "errors": [
        [doc.block_error(i).code, doc.block_error(i).message, doc.block_error(i).codepoint_pos]
        for i in range(len(doc))
    ],
    "math_refused": int(ts.ErrorCode.MathRefused),
    "copies": [
        doc.range_text(((i, 0), (i, len(text)))) for i, text in enumerate(described.texts)
    ],
    "texts": described.texts,
}
doc.close()

# 3. A character the code face lacks, left in the code face (directly) and
#    moved to the prose face (through the material): the same carets.
source = "`aπb` and → and `c中d`"
carets = []
for described in (
    direct.describe_markdown(source, theme),
    material_frozen.description(source, math=False),
):
    doc, _, _ = laid(described, 2000.0)
    carets.append([doc.caret_rect((0, at))[0] for at in range(len(described.texts[0]) + 1)])
    doc.close()
report["carets"] = carets

# 4. TypesetStreamView over a MarkdownStream.
def frame(view):
    imgui.new_frame()
    try:
        imgui.set_next_window_pos(imgui.ImVec2(20.0, 20.0))
        imgui.set_next_window_size(imgui.ImVec2(700.0, 400.0))
        imgui.begin("host", None, imgui.WindowFlags_.no_move.value)
        imgui.begin_child("##text")
        try:
            draw_list = imgui.get_window_draw_list()
            before = draw_list.vtx_buffer.size()
            view.draw()
            return draw_list.vtx_buffer.size() - before
        finally:
            imgui.end_child()
            imgui.end()
    finally:
        imgui.render()

def everything(view):
    doc = view.native_document
    last = len(view.texts) - 1
    return doc.range_text(((0, 0), (last, len(view.texts[last]))), "\n\n")

report["streams"] = {}
for name, chunk in (("sample.md", 24), ("sample.md", 5), ("tables.md", 24), ("math.md", 24)):
    source = (ROOT / "demo" / name).read_text(encoding="utf-8")
    whole = TypesetView(source, theme=theme, math=True)
    frame(whole)
    stream = direct.MarkdownStream(theme, math=True)
    view = TypesetStreamView(stream)
    frame(view)
    most = drawn = frames = 0
    for at in range(0, len(source), chunk):
        stream.append(source[at:at + chunk])
        edits = sum(view.edits.values())
        drawn += frame(view) > 0
        frames += 1
        most = max(most, sum(view.edits.values()) - edits)
    stream.close()
    frame(view)
    idle = sum(view.edits.values())
    frame(view)
    report["streams"][f"{name} {chunk}"] = {
        "converter": type(view.converter).__name__,
        "frames": frames,
        "frames_drawn": drawn,
        "most_edits_in_a_frame": most,
        "edits_in_an_idle_frame": sum(view.edits.values()) - idle,
        "edits": dict(view.edits),
        "edit_error": view.native_document.edit_error.code,
        "library_blocks": [view.native_document.block_count, len(stream.blocks)],
        "same_texts": list(view.texts) == list(whole.texts),
        "same_copy": everything(view) == everything(whole),
        "copy_length": len(everything(view)),
        "trouble": typesetter.trouble(),
    }
    view.close()
    whole.close()
report["still_in_use"] = typesetter.module() is not None
typesetter.unload()
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def library() -> dict[str, Any]:
    if not os.environ.get(typesetter.LIBRARY_VARIABLE):
        pytest.skip(f"{typesetter.LIBRARY_VARIABLE} is not set: imtypeset is not in use")
    report = _child(_LIBRARY, dict(os.environ), str(_ROOT))
    assert report["module"], f"the library was asked for and not loaded: {report.get('reason')}"
    assert report["ready"]
    return report


def test_a_document_takes_every_demos_direct_description_whole(library: dict[str, Any]) -> None:
    files = library["files"]
    assert len(files) == len(_DEMOS)
    for name, told in files.items():
        assert told["blocks"][0] == told["blocks"][1] > 0, name
        assert told["set_blocks"] is True and told["edit_error"] == 0, name
        assert told["block_errors"] == [], name
        assert told["vertex_bytes"] > 0 and told["texts"] and told["same_copy"], name
        # With the old converter's runs it is the same description but for the
        # kern count, and the same height. With its own, spaces beside runs are
        # other widths and lines may break elsewhere: that height is only reported.
        assert told["heights"][0] == told["heights"][1] > 0, name
        assert told["height"] > 0, name
    # One block in all the demos holds two spaces in a row (the child says what
    # the library does with them); every other copies back character for character.
    assert {name: told["collapsed"] for name, told in files.items() if told["collapsed"]} == {
        "diff/README.md": 1
    }


def test_the_library_says_which_block_holds_a_formula_it_will_not_set(
    library: dict[str, Any],
) -> None:
    told = library["refused"]
    assert told["set_blocks"] is True and told["edit_error"] == 0
    fine, inline, display = told["errors"]
    assert fine[0] == 0
    assert inline[0] == display[0] == told["math_refused"]
    assert inline[1] and display[1]
    # The place is an index into the block's text, inside the formula's source.
    assert told["texts"][1] == "not \\hat x here" and 4 <= inline[2] < 10
    assert told["texts"][2] == "\\frac{1" and 0 <= display[2] <= 7
    # A refused formula copies as its source, as a set one does.
    assert told["copies"] == told["texts"]


def test_a_character_left_in_the_face_that_lacks_it_is_set_where_the_borrowed_one_was(
    library: dict[str, Any],
) -> None:
    directly, through_material = library["carets"]
    text = "a\u03c0b and \u2192 and c\u4e2dd"
    assert len(directly) == len(through_material) == len(text) + 1

    def advances(carets: list[float]) -> list[float]:
        return [round(b - a, 3) for a, b in zip(carets, carets[1:], strict=False)]

    ours, theirs = advances(directly), advances(through_material)
    # Every character is as wide either way: the library borrows for itself
    # what the old core borrowed for it.
    for at, character in enumerate(text):
        if character != " ":
            assert ours[at] == theirs[at] > 0, (at, character)
    # And directly every space is the paragraph's own. (Through the material
    # the space after the arrow is the math face's: the run that borrowed
    # the arrow goes on over it. That is not asserted; it is `Converter`'s.)
    assert len({ours[at] for at, character in enumerate(text) if character == " "}) == 1


def test_typeset_stream_view_runs_over_a_markdown_stream_with_this_converter(
    library: dict[str, Any],
) -> None:
    assert set(library["streams"]) == {"sample.md 24", "sample.md 5", "tables.md 24", "math.md 24"}
    for name, told in library["streams"].items():
        assert told["converter"] == "MarkdownConverter", name
        assert told["frames_drawn"] == told["frames"] > 20, name
        assert told["most_edits_in_a_frame"] == 1 and told["edits_in_an_idle_frame"] == 0, name
        assert told["edits"]["set"] == 1 and told["edits"]["append"] > 0, name
        assert told["edit_error"] == 0 and told["trouble"] == "", name
        assert told["library_blocks"][0] == told["library_blocks"][1] > 0, name
        # What it ends as is what a TypesetView given the whole source shows:
        # the same texts, the same copy.
        assert told["same_texts"] and told["same_copy"] and told["copy_length"] > 1000, name
    assert library["still_in_use"]

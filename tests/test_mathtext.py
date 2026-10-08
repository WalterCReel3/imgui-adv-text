r"""
`advtext.mathtext`: a `$...$` subset against the atoms a person would have written.

Four claims, each with its own section:

1. **A source is the formula it says it is.** Every construct is compared with a
   hand-built atom list, and each of the eleven gallery entries in
   `advtext.ui.formulas` is written as a source and must set to the *same box*
   the hand-built entry sets to. Box equality rather than atom equality for the
   gallery because two of its entries group atoms a way no source would
   (`var("∂ψ")` is one atom holding two); the entries where the atoms coincide
   are compared as atoms as well.
2. **Everything outside the subset is a refusal with a kind, a reason and a
   position**, and `parse` is total: seeded fuzz, and inputs sized so that a
   quadratic pass would not finish.
3. **A font that cannot be used is a refusal too**, through `typeset`, and so
   is a formula the engine will not set: content taller than the largest
   delimiter the face has.
4. **Every glyph a supported command can name is in the math face**, checked
   against the font file through `advtext.ui.formulas.missing_codepoints`.

5. **The second pass** (section 5): `\sqrt`, `\left`...`\right`, the explicit
   spaces and `\text{}`, each against the engine's own constructors
   (`radical`, `delimited`, `THIN_SPACE`..., `prose_text`), which decision D1
   had the engine grow after the first version of the subset refused them.

Everything here runs against the real Latin Modern Math: the claims are about
what sets, and a fake face would not know which codepoints exist.
"""

from __future__ import annotations

import ast
import random
from dataclasses import replace
from pathlib import Path

import pytest

import advtext.math
from advtext import fontlib
from advtext.fontlib import MissingFontError
from advtext.fontmetrics import Face, MathFontMetrics
from advtext.math import (
    MED_SPACE,
    NEGATIVE_THIN_SPACE,
    QQUAD,
    QUAD,
    THICK_SPACE,
    THIN_SPACE,
    Atom,
    AtomType,
    Fraction,
    Limits,
    MathChar,
    MathItem,
    Style,
    SubList,
    bin_,
    close_,
    delimited,
    frac,
    group,
    inner,
    math_fonts,
    mlist_to_hlist,
    op,
    open_,
    ord_,
    prose_text,
    punct,
    radical,
    rel,
    space,
)
from advtext.math.mlist import (
    DelimiterTooSmallError,
    MathLayoutError,
    MissingGlyphError,
    TextFaceUnavailableError,
)
from advtext.mathtext import (
    MAX_DEPTH,
    Formula,
    Refusal,
    RefusalKind,
    Typeset,
    formula_fonts,
    parse,
    refused_commands,
    set_formula,
    sized_delimiters,
    supported_commands,
    typeset,
)
from advtext.nodes import Box, CharNode, Rule
from advtext.pack import hpack
from advtext.style import parse_font_key
from advtext.ui import formulas
from advtext.ui.formulas import ENTRIES, italic, missing_codepoints, var
from advtext.units import Scaled, sp_from_px

FONTS = formula_fonts(sp_from_px(formulas.FORMULA_PX, 96.0))


def atoms(source: str) -> tuple[MathItem, ...]:
    result = parse(source)
    assert isinstance(result, Formula), result
    return result.items


def refusal(source: str) -> Refusal:
    result = parse(source)
    assert isinstance(result, Refusal), result
    return result


def box_of(items: tuple[MathItem, ...], style: Style) -> Box:
    return hpack(mlist_to_hlist(list(items), style, FONTS), measure=FONTS.measure).box


def box_of_source(source: str, *, display: bool = False) -> Box:
    result = parse(source, display=display)
    assert isinstance(result, Formula), result
    return set_formula(result, FONTS)


def width(source: str, style: Style = Style.TEXT) -> int:
    return box_of(atoms(source), style).width


# --------------------------------------------------------------------------------
# 1. The gallery, as sources
# --------------------------------------------------------------------------------

GALLERY: dict[str, tuple[str, ...]] = {
    "operator-style": (r"\sum_{i=1}^n", r"\sum_{i=1}^n"),
    "euler": (r"e^{i\pi} + 1 = 0",),
    "schrodinger": (
        r"i\hbar\frac{\partial\psi}{\partial t} = " r"-\frac{\hbar^2}{2m}\nabla^2\psi + V\psi",
    ),
    "basel": (r"\sum_{n=1}^\infty \frac{1}{n^2} = \frac{\pi^2}{6}",),
    "cauchy": (r"f(a) = \frac{1}{2\pi i} \oint_\gamma \frac{f(z)}{z-a} dz",),
    "continued-fraction": (r"\varphi = 1 + \frac{1}{1+\frac{1}{1+\frac{1}{1+\frac{1}{1+1}}}}",),
    "script-towers": (r"x^{y^{z^w}}", r"x_{y_{z_w}}"),
    "atom-classes": (r"a+b=c", r"a{+}b{=}c"),
    "binary-or-not": (r"-x", r"a-x"),
    "radical": (r"\sqrt{a^2+b^2}", r"\sqrt{\frac{a^2+b^2}{c^2}}"),
    "sized-delimiters": (r"(\frac{a^2+b^2}{c^2})", r"\left(\frac{a^2+b^2}{c^2}\right)"),
}
"""
One source per panel of each gallery entry, in the entry's panel order.
"""

SAME_ATOMS = ("operator-style", "euler", "basel", "cauchy", "script-towers", "binary-or-not")
"""
The entries a source reproduces atom for atom. The other three set identically
and are grouped differently: `schrodinger` holds `∂ψ` as one atom of two,
`continued-fraction` wraps its innermost `1` in an Inner, and `atom-classes`
writes `ord_("+")` where a source can only say `{+}`. The two sized entries
hold a bare `Fraction` under the radical and between the delimiters, where a
source's `\frac` is that fraction in an Inner atom.
"""


def test_the_gallery_table_names_every_entry() -> None:
    assert set(GALLERY) == {entry.key for entry in ENTRIES}
    assert len(GALLERY) == 11


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry.key)
def test_a_source_sets_the_box_the_hand_built_entry_sets(entry: formulas.EntryDef) -> None:
    sources = GALLERY[entry.key]
    assert len(sources) == len(entry.panels)
    for source, panel in zip(sources, entry.panels, strict=True):
        result = parse(source, display=panel.style is Style.DISPLAY)
        assert isinstance(result, Formula), result
        assert result.style is panel.style
        built = set_formula(result, FONTS)
        assert built.width > 0
        assert built == box_of(panel.items, panel.style)
        if entry.key in SAME_ATOMS:
            assert result.items == panel.items


def test_the_two_all_ordinary_panels_differ_from_the_classified_ones() -> None:
    # Guards the gallery test against a `box_of` that ignores classes: if it
    # did, these would be equal and the test above would prove nothing.
    assert width("a+b=c") > width("a{+}b{=}c")
    assert width("a-x") > width("-x") + width("a")


# --------------------------------------------------------------------------------
# 1b. Each construct against hand-built atoms
# --------------------------------------------------------------------------------


def test_letters_are_italic_digits_and_capital_greek_upright() -> None:
    assert atoms("x") == (var("x"),)
    assert atoms("h") == (ord_(chr(0x210E)),)
    assert atoms("7") == (ord_("7"),)
    assert atoms(r"\Sigma") == (ord_("Σ"),)
    assert atoms(r"\sigma") == (var("σ"),)
    assert atoms("xy2") == (var("x"), var("y"), ord_("2"))


def test_the_italic_table_is_the_gallerys() -> None:
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert atoms(letters) == tuple(ord_(italic(letter)) for letter in letters)
    # Omicron has no command in LaTeX (it is the Latin o), so it is not typed either.
    for codepoint in sorted(set(range(0x03B1, 0x03CA)) - {0x03BF}):
        assert atoms(chr(codepoint)) == (ord_(italic(chr(codepoint))),)


def test_variant_greek_follows_unicode_math() -> None:
    assert atoms(r"\epsilon\varepsilon\phi\varphi") == (
        ord_(chr(0x1D716)),
        ord_(italic("ε")),
        ord_(chr(0x1D719)),
        ord_(italic("φ")),
    )


def test_scripts_take_one_token_or_a_group_in_either_order() -> None:
    both = var("x", sup="2", sub=group(var("i")))
    assert atoms("x^2_i") == (both,)
    assert atoms("x_i^2") == (both,)
    assert atoms("x^{2}_{i}") == (both,)
    assert atoms(r"x^\alpha") == (var("x", sup=group(var("α"))),)
    assert atoms("x^{ab}") == (var("x", sup=group(var("a"), var("b"))),)
    assert atoms("x ^ 2") == atoms("x^2")


def test_one_token_means_one_token() -> None:
    # TeX's rule, and the reason `x^10` is a classic slip: the 0 is not raised.
    assert atoms("x^10") == (var("x", sup="1"), ord_("0"))
    assert atoms("x^-1") == (var("x", sup=group(bin_("−"))), ord_("1"))


def test_a_script_with_nothing_before_it_hangs_on_an_empty_atom() -> None:
    assert atoms("^2") == (Atom(AtomType.ORD, None, SubList((ord_("2"),))),)
    assert atoms("{}_a") == (ord_(SubList(()), sub=group(var("a"))),)


def test_primes_are_a_superscript_and_a_caret_may_follow_them() -> None:
    prime = ord_(chr(0x2032))
    assert atoms("f'") == (var("f", sup=group(prime)),)
    assert atoms("f''") == (var("f", sup=group(prime, prime)),)
    assert atoms("f'^2") == (var("f", sup=group(prime, ord_("2"))),)
    assert atoms("f'_n") == (var("f", sup=group(prime), sub=group(var("n"))),)


def test_a_group_is_an_ordinary_atom_and_a_lone_ordinary_atom_is_itself() -> None:
    assert atoms("{x}") == (var("x"),)
    assert atoms("{{x}}^2") == atoms("x^2")
    assert atoms("{ab}") == (ord_(group(var("a"), var("b"))),)
    assert atoms("{x^2}^3") == (ord_(group(var("x", sup="2")), sup="3"),)
    assert atoms("{+}") == (ord_(group(bin_("+"))),)


def test_a_fraction_is_an_inner_atom_and_can_carry_scripts() -> None:
    half = frac("1", "2")
    assert atoms(r"\frac{1}{2}") == (inner(half),)
    assert atoms(r"\frac12") == (inner(half),)
    assert atoms(r"\frac{a+b}{c}") == (
        inner(frac(group(var("a"), bin_("+"), var("b")), group(var("c")))),
    )
    assert atoms(r"\frac12^n") == (inner(half, sup=group(var("n"))),)
    assert isinstance(half, Fraction)


def test_ascii_characters_carry_tex_classes() -> None:
    assert atoms("a+b-c*d") == (
        var("a"),
        bin_("+"),
        var("b"),
        bin_("−"),
        var("c"),
        bin_("∗"),
        var("d"),
    )
    assert atoms("=<>:") == (rel("="), rel("<"), rel(">"), rel(":"))
    assert atoms("([])") == (open_("("), open_("["), close_("]"), close_(")"))
    assert atoms(",;") == (punct(","), punct(";"))
    assert atoms("./|") == (ord_("."), ord_("/"), ord_("|"))
    assert atoms("n!") == (var("n"), close_("!"))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\times", bin_("×")),
        (r"\cdot", bin_("⋅")),
        (r"\pm", bin_("±")),
        (r"\le", rel("≤")),
        (r"\leq", rel("≤")),
        (r"\neq", rel("≠")),
        (r"\in", rel("∈")),
        (r"\to", rel("→")),
        (r"\Rightarrow", rel("⇒")),
        (r"\approx", rel("≈")),
        (r"\langle", open_("⟨")),
        (r"\rangle", close_("⟩")),
        (r"\{", open_("{")),
        (r"\}", close_("}")),
        (r"\colon", punct(":")),
        (r"\infty", ord_("∞")),
        (r"\partial", ord_(chr(0x1D715))),
        (r"\ldots", inner(MathChar(0x2026))),
        (r"\cdots", inner(MathChar(0x22EF))),
        (r"\%", ord_("%")),
    ],
)
def test_a_named_symbol_is_one_atom_of_its_class(source: str, expected: Atom) -> None:
    assert atoms(source) == (expected,)


def test_a_symbol_typed_as_itself_is_the_command() -> None:
    assert atoms("π") == atoms(r"\pi")
    assert atoms("∑_i") == atoms(r"\sum_i")
    assert atoms("a ≤ b") == atoms(r"a \le b")
    assert atoms("a − b") == atoms("a - b")
    assert atoms("∂") == atoms(r"\partial")


def test_sums_take_the_default_and_integrals_stay_beside() -> None:
    assert atoms(r"\sum_i") == (op("∑", sub=group(var("i"))),)
    assert atoms(r"\int_0^1") == (op("∫", sup="1", sub="0", limits=Limits.NO_LIMITS),)
    assert atoms(r"\sum\nolimits_i") == (op("∑", sub=group(var("i")), limits=Limits.NO_LIMITS),)
    assert atoms(r"\int\limits_0") == (op("∫", sub="0", limits=Limits.LIMITS),)
    assert atoms(r"\sum_i\limits") == (op("∑", sub=group(var("i")), limits=Limits.LIMITS),)


def test_limits_placement_comes_from_the_engine() -> None:
    # Stacked limits make the display sum narrower and deeper than the inline
    # one; an integral's stay beside it in both.
    inline = box_of_source(r"\sum_{i=1}^{n}")
    display = box_of_source(r"\sum_{i=1}^{n}", display=True)
    assert display.depth > inline.depth
    assert display.height > inline.height
    stacked = box_of_source(r"\int\limits_{i=1}^{n}", display=True)
    beside = box_of_source(r"\int_{i=1}^{n}", display=True)
    assert stacked.depth > beside.depth


def test_function_names_are_upright_operators() -> None:
    sin = atoms(r"\sin")[0]
    assert sin == Atom(
        AtomType.OP, SubList(tuple(ord_(letter) for letter in "sin")), limits=Limits.NO_LIMITS
    )
    lim = atoms(r"\lim_{x\to0}")[0]
    assert isinstance(lim, Atom)
    assert lim.kind is AtomType.OP and lim.limits is Limits.DEFAULT
    assert lim.nucleus == SubList(tuple(ord_(letter) for letter in "lim"))
    assert atoms(r"\operatorname{rank}")[0] == Atom(
        AtomType.OP, SubList(tuple(ord_(letter) for letter in "rank")), limits=Limits.NO_LIMITS
    )
    # An operator name is spaced from its argument; the same letters as
    # variables are not, and are a different (italic) set of glyphs.
    assert width(r"\sin x") > width(r"\mathrm{sin}x")


def test_mathrm_is_upright_letters_and_blanks_in_it_mean_nothing() -> None:
    assert atoms(r"\mathrm{d x}") == (ord_(SubList((ord_("d"), ord_("x")))),)
    assert atoms(r"\mathrm{}") == (ord_(SubList(())),)
    assert atoms(r"\mathrm{d}") != atoms("d")
    assert width(r"\mathrm{a b}") == width(r"\mathrm{ab}")


def test_overline_and_underline_are_the_engines_atoms() -> None:
    assert atoms(r"\overline{z}") == (Atom(AtomType.OVER, SubList((var("z"),))),)
    assert atoms(r"\underline{ab}") == (Atom(AtomType.UNDER, group(var("a"), var("b"))),)
    plain = box_of(atoms("z"), Style.TEXT)
    barred = box_of(atoms(r"\overline{z}"), Style.TEXT)
    assert barred.height > plain.height


def test_alphabets_map_to_unicode_and_know_their_holes() -> None:
    assert atoms(r"\mathbb{R}") == (ord_(chr(0x211D)),)
    assert atoms(r"\mathbb{A}") == (ord_(chr(0x1D538)),)
    assert atoms(r"\mathbf{v}") == (ord_(chr(0x1D42F)),)
    assert atoms(r"\mathcal{L}") == (ord_(chr(0x2112)),)
    assert atoms(r"\mathbf{Ax}") == (ord_(SubList((ord_(chr(0x1D400)), ord_(chr(0x1D431))))),)
    assert refusal(r"\mathbb{r}").kind is RefusalKind.CHARACTER
    assert refusal(r"\mathcal{1}").kind is RefusalKind.CHARACTER


def test_display_changes_the_style_and_not_the_atoms() -> None:
    inline, display = parse(r"\sum_i x_i"), parse(r"\sum_i x_i", display=True)
    assert isinstance(inline, Formula) and isinstance(display, Formula)
    assert inline.items == display.items
    assert (inline.style, display.style) == (Style.TEXT, Style.DISPLAY)
    assert inline.source == r"\sum_i x_i"


# --------------------------------------------------------------------------------
# 2. Refusals, and totality
# --------------------------------------------------------------------------------

REFUSALS: tuple[tuple[str, RefusalKind, int], ...] = (
    ("", RefusalKind.EMPTY, 0),
    ("   ", RefusalKind.EMPTY, 0),
    ("x^", RefusalKind.SYNTAX, 1),
    ("x_}", RefusalKind.SYNTAX, 1),
    ("x^2^3", RefusalKind.SYNTAX, 3),
    ("x_2_3", RefusalKind.SYNTAX, 3),
    ("x^2'", RefusalKind.SYNTAX, 3),
    ("a{b", RefusalKind.SYNTAX, 1),
    ("a}b", RefusalKind.SYNTAX, 1),
    ("ab\\", RefusalKind.SYNTAX, 2),
    (r"\frac{1}", RefusalKind.SYNTAX, 0),
    (r"x\limits", RefusalKind.SYNTAX, 1),
    (r"\nolimits", RefusalKind.SYNTAX, 0),
    ("a $ b", RefusalKind.SYNTAX, 2),
    ("50% off", RefusalKind.SYNTAX, 2),
    (r"\mathrm x", RefusalKind.SYNTAX, 0),
    (r"\mathrm{abc", RefusalKind.SYNTAX, 7),
    ("{" * (MAX_DEPTH + 1), RefusalKind.NESTING, MAX_DEPTH),
    (r"a + \foo", RefusalKind.UNKNOWN_COMMAND, 4),
    (r"\sumx", RefusalKind.UNKNOWN_COMMAND, 0),
    ("a € b", RefusalKind.CHARACTER, 2),
    ('"', RefusalKind.CHARACTER, 0),
    (r"\mathrm{naïve}", RefusalKind.CHARACTER, 10),
    (r"\operatorname{a\,b}", RefusalKind.CHARACTER, 15),
    (r"\newcommand{\R}{x}", RefusalKind.MACRO, 0),
    (r"\def\x{1}", RefusalKind.MACRO, 0),
    ("#1", RefusalKind.MACRO, 0),
    (r"\begin{aligned}a\end{aligned}", RefusalKind.ENVIRONMENT, 0),
    (r"a \end{x}", RefusalKind.ENVIRONMENT, 2),
    (r"\begin", RefusalKind.ENVIRONMENT, 0),
    (r"\begin{pmatrix}a&b\end{pmatrix}", RefusalKind.MATRIX, 0),
    (r"\begin{bmatrix}", RefusalKind.MATRIX, 0),
    (r"\begin {matrix}", RefusalKind.MATRIX, 0),
    (r"\begin{cases}", RefusalKind.MATRIX, 0),
    (r"\pmatrix{a}", RefusalKind.MATRIX, 0),
    ("a & b", RefusalKind.ALIGNMENT, 2),
    (r"a \\ b", RefusalKind.ALIGNMENT, 2),
    (r"a \over b", RefusalKind.INFIX, 2),
    (r"n \choose k", RefusalKind.INFIX, 2),
    (r"\hat{x}", RefusalKind.ACCENT, 0),
    (r"\vec v", RefusalKind.ACCENT, 0),
    (r"\displaystyle\sum", RefusalKind.STYLE, 0),
    (r"\dfrac12", RefusalKind.STYLE, 0),
    (r"\mathit{x}", RefusalKind.STYLE, 0),
    # What is still refused in the four families the second pass opened.
    (r"\big(", RefusalKind.DELIMITER, 0),
    (r"a \Bigl[ b", RefusalKind.DELIMITER, 2),
    (r"\dbinom{n}{k}", RefusalKind.STYLE, 0),
    (r"a \tbinom{n}{k}", RefusalKind.STYLE, 2),
    (r"\binom{n}", RefusalKind.SYNTAX, 0),
    (r"\left( a \middle| b \right)", RefusalKind.DELIMITER, 9),
    (r"\left\uparrow x \right)", RefusalKind.DELIMITER, 5),
    (r"\left x \right)", RefusalKind.DELIMITER, 6),
    (r"\left( x \right\rightarrow", RefusalKind.DELIMITER, 15),
    (r"\left( x \right x", RefusalKind.DELIMITER, 16),
    (r"\overbrace{a+b}", RefusalKind.DELIMITER, 0),
    (r"1 + \sqrt[3]{x}", RefusalKind.RADICAL, 4),
    (r"\sqrt [n] x", RefusalKind.RADICAL, 0),
    (r"\root 3 \of x", RefusalKind.RADICAL, 0),
    (r"\hspace{1em}", RefusalKind.SPACING, 0),
    (r"a\space b", RefusalKind.SPACING, 1),
    (r"\phantom{x}", RefusalKind.SPACING, 0),
    (r"\mbox{a}", RefusalKind.TEXT, 0),
    (r"\text{a {b} c}", RefusalKind.TEXT, 8),
    (r"x \text{if $y$}", RefusalKind.TEXT, 11),
    (r"\text{a\,b}", RefusalKind.TEXT, 7),
    # ... and the ways a `\left`...`\right`, a `\sqrt` or a `\text` can be malformed.
    (r"\left( x", RefusalKind.SYNTAX, 0),
    (r"a + \left[ x", RefusalKind.SYNTAX, 4),
    (r"x \right)", RefusalKind.SYNTAX, 2),
    (r"\left( {a \right)}", RefusalKind.SYNTAX, 10),
    (r"{\left( a } \right)", RefusalKind.SYNTAX, 10),
    (r"\left", RefusalKind.SYNTAX, 0),
    (r"\left( x \right", RefusalKind.SYNTAX, 9),
    (r"x^\right)", RefusalKind.SYNTAX, 2),
    (r"\sqrt", RefusalKind.SYNTAX, 0),
    (r"\sqrt}", RefusalKind.SYNTAX, 0),
    (r"\text x", RefusalKind.SYNTAX, 0),
    (r"\text{abc", RefusalKind.SYNTAX, 5),
    ("\\text{a\x07b}", RefusalKind.CHARACTER, 7),
    ("\\left(" * (MAX_DEPTH + 1), RefusalKind.NESTING, 6 * MAX_DEPTH),
)


@pytest.mark.parametrize(("source", "kind", "position"), REFUSALS)
def test_a_source_outside_the_subset_is_refused(
    source: str, kind: RefusalKind, position: int
) -> None:
    for display in (False, True):
        refused = parse(source, display=display)
        assert isinstance(refused, Refusal), refused
        assert (refused.kind, refused.position) == (kind, position), refused
        assert refused.source == source and refused.display is display
        assert refused.reason and "\n" not in refused.reason


def test_every_refusal_kind_has_a_case() -> None:
    # `FONT` and `LAYOUT` are the kinds `parse` cannot give: it has no font, and
    # whether a delimiter can cover its content is the engine's to say. Section 3.
    assert {kind for _, kind, _ in REFUSALS} == set(RefusalKind) - {
        RefusalKind.FONT,
        RefusalKind.LAYOUT,
    }


def test_a_refusal_names_the_command_it_refused() -> None:
    assert refusal(r"\hat{2}").reason.startswith(r"\hat ")
    # Nothing is "not yet" any more: the four families that were are parsed.
    for command, _kind in sorted(refused_commands().items()):
        assert "yet" not in refusal(f"\\{command}").reason.split(), command
    assert r"\text{...}" in refusal(r"\mbox{a}").reason
    assert r"\sqrt[n] " in refusal(r"\sqrt[3]{x}").reason
    assert r"\left and \right" in refusal(r"\big(").reason
    assert "'x' is not a delimiter \\left can size" == refusal(r"\left x \right)").reason
    assert r"\uparrow is not a delimiter \right" in refusal(r"\left( a \right\uparrow").reason
    # A brace closing across a pair says so, rather than "no { before it".
    assert refusal(r"{\left( a } \right)").reason == r"a } between a \left and its \right"
    assert refusal(r"\left( a").reason == r"a \left with no \right after it"
    assert refusal(r"a \right)").reason == r"a \right with no \left before it"
    assert "matrices are left out for now" in refusal(r"\begin{pmatrix}").reason
    assert r"\zzz" in refusal(r"\zzz").reason
    assert "U+20AC" in refusal("€").reason


def test_every_command_listed_as_refused_is_refused_with_its_kind() -> None:
    listed = refused_commands()
    assert len(listed) > 60
    for name, kind in listed.items():
        refused = refusal(f"a \\{name}{{b}}")
        assert refused.kind is kind, name
        assert refused.position == 2
    assert not set(listed) & set(supported_commands())


def test_every_supported_command_parses_and_sets() -> None:
    names = supported_commands()
    assert len(names) > 200
    assert {"text", ",", "quad", "sqrt", "left", "right", "!", "textbf"} <= set(names)
    takes_argument = {"frac": "{a}{b}", "binom": "{a}{b}", "limits": "", "nolimits": ""}
    for name in names:
        if name in ("limits", "nolimits"):
            source = f"\\sum\\{name}_i"
        elif name in ("mathrm", "operatorname", "mathbb", "mathbf", "mathcal"):
            source = f"\\{name}{{A}}"
        elif name in ("overline", "underline", "sqrt", "text", "textrm", "textnormal"):
            source = f"\\{name}{{a}}"
        elif name in ("textit", "textbf"):
            source = f"x \\{name}{{a b}} y"
        elif name in ("left", "right"):
            source = r"a \left( b \right) c"
        else:
            source = f"a \\{name}{takes_argument.get(name, '')} b"
        for display in (False, True):
            result = parse(source, display=display)
            assert isinstance(result, Formula), (name, result)
            assert set_formula(result, FONTS).width > 0


FUZZ_PIECES = (
    *("a", "x", "1", "+", "-", "=", ",", "(", ")", "[", "]", "|", " ", "  "),
    *("{", "}", "{", "}", "^", "_", "'", "\\", "$", "&", "#", "%", "~", "\n"),
    *(r"\frac", r"\sum", r"\int", r"\alpha", r"\,", r"\pi", r"\text", r"\mathbb"),
    *(r"\limits", r"\nolimits", r"\left", r"\sqrt", r"\begin", r"\\", r"\{", r"\}"),
    *(r"\overline", r"\operatorname", r"\lim", r"\ldots", r"\le", "π", "∑", "€", "\x00"),
    *(r"\right", r"\right", r"\left(", r"\right)", r"\left(", r"\right)", ".", "<"),
    *(r"\quad", r"\!", r"\;", r"\text{a b}", r"\sqrt{x}", r"\frac{a}{b}", r"\sum\limits_a^b"),
)


def test_parse_is_total_and_every_formula_it_returns_sets_or_is_refused_by_the_engine() -> None:
    """
    Token soup. `parse` never raises; a `Formula` it returns either sets or is
    refused by the engine with `MathLayoutError` and nothing else; and
    `typeset`, which is the route a document takes, never raises at all and
    agrees with the two-step route about which it was.
    """
    rng = random.Random(20261007)
    formulas_seen = 0
    too_tall = 0
    families = {AtomType.RADICAL: 0, AtomType.LEFT: 0, AtomType.SPACE: 0}
    prose = 0
    kinds: set[RefusalKind] = set()
    for _ in range(6000):
        source = "".join(rng.choice(FUZZ_PIECES) for _ in range(rng.randrange(0, 14)))
        display = rng.random() < 0.5
        result = parse(source, display=display)
        whole = typeset(source, SIZE, display=display, fonts=FONTS)
        if isinstance(result, Formula):
            formulas_seen += 1
            assert result.items
            for kind in families:
                families[kind] += kind.name in repr(result.items)
            prose += "MathText" in repr(result.items)
            try:
                box = set_formula(result, FONTS)
            except MathLayoutError:
                too_tall += 1
                assert isinstance(whole, Refusal) and whole.kind is RefusalKind.LAYOUT
                assert whole.reason and whole.position == 0
            else:
                # Not `width >= 0`: `\!` alone is a formula three mu narrower
                # than nothing, which is what it is in TeX too.
                assert isinstance(whole, Typeset) and whole.box == box
        else:
            assert isinstance(result, Refusal)
            assert whole == result
            kinds.add(result.kind)
            assert 0 <= result.position <= len(source)
            assert result.reason
    # The fuzz is only evidence if it reaches both outcomes in number, and
    # reaches the constructs of the second pass among the formulas. A balanced
    # `\left`...`\right` is rare in soup (2 of 6000 with this seed), which is
    # what the grown formulas of the next test are for.
    assert formulas_seen > 400
    assert len(kinds) >= 8
    assert families[AtomType.RADICAL] > 20 and families[AtomType.SPACE] > 20, families
    assert prose > 20


def _grown(rng: random.Random, depth: int) -> str:
    """
    A well-formed source grown from the constructs of the second pass and the
    tall things of the first, `depth` levels deep at most.
    """
    if depth <= 0:
        return rng.choice(["x", "a", "1", r"\alpha", r"\,", r"\text{a b}", r"\quad"])

    def part() -> str:
        return _grown(rng, depth - rng.randrange(1, 3))

    written = sorted(sized_delimiters())
    match rng.randrange(8):
        case 0:
            return f"\\left{rng.choice(written)} {part()} \\right{rng.choice(written)}"
        case 1:
            return f"\\sqrt{{{part()}}}"
        case 2:
            return f"\\frac{{{part()}}}{{{part()}}}"
        case 3:
            return f"{{{part()}}}^{{{part()}}}_{{{part()}}}"
        case 4:
            return f"\\sum\\limits_{{{part()}}}^{{{part()}}}"
        case 5:
            return f"{part()} \\{rng.choice([',', ':', ';', '!'])} {part()}"
        case 6:
            return f"{part()} + {part()}"
        case _:
            return f"\\text{{ if }} {part()}"


def test_grown_formulas_all_parse_and_each_sets_or_is_refused_as_too_tall() -> None:
    r"""
    Two thousand well-formed sources built from `\left`...`\right`, `\sqrt`,
    `\frac`, scripts, stacked limits, spaces and `\text`, in both styles.

    Every one parses. Every one then either sets -- with a sized delimiter in
    hundreds of them -- or comes back from `typeset` as a `LAYOUT` refusal,
    and both happen in number. None is a `FONT` refusal and nothing raises:
    that is the "never a broken formula" contract for the constructs whose
    setting can fail.
    """
    rng = random.Random(1762)
    sets = too_tall = paired = 0
    for _ in range(2000):
        source = _grown(rng, rng.randrange(1, 7))
        display = rng.random() < 0.5
        parsed = parse(source, display=display)
        assert isinstance(parsed, Formula), (source, parsed)
        done = typeset(source, SIZE, display=display, fonts=FONTS)
        if isinstance(done, Typeset):
            sets += 1
            paired += r"\left" in source
            assert done.box == set_formula(parsed, FONTS)
        else:
            assert done.kind is RefusalKind.LAYOUT, (source, done)
            assert "as tall as the largest the math face has" in done.reason
            too_tall += 1
            with pytest.raises(MathLayoutError):
                set_formula(parsed, FONTS)
    # 97 refusals with this seed since the largest delimiter became acceptable
    # down to three quarters of the content (review 2, item 9); 1903 set.
    assert sets > 500 and too_tall > 60 and paired > 200, (sets, too_tall, paired)


def test_parse_is_total_over_arbitrary_characters() -> None:
    rng = random.Random(7)
    for _ in range(3000):
        source = "".join(chr(rng.randrange(0, 0x3000)) for _ in range(rng.randrange(0, 12)))
        result = parse(source)
        assert isinstance(result, Formula | Refusal)
        if isinstance(result, Formula):
            set_formula(result, FONTS)
        # Arbitrary characters as the words of a `\text{}`: printable ones are
        # taken, the rest refused, and `typeset` returns for all of them.
        worded = typeset("\\text{" + source.replace("}", "") + "}", SIZE, fonts=FONTS)
        assert isinstance(worded, Typeset | Refusal)
    for codepoint in (0xD800, 0xDFFF, 0x10FFFF, 0xFFFD, 0x1D455):
        assert isinstance(parse(chr(codepoint)), Formula | Refusal)
        assert isinstance(parse("\\" + chr(codepoint)), Formula | Refusal)


@pytest.mark.parametrize(
    "source",
    [
        "{" * 50_000,
        "}" * 50_000,
        "x^" * 50_000,
        "{x^" * 50_000,
        r"\frac" * 50_000,
        r"\overline" * 50_000,
        "_{" * 50_000,
        "x" + "'" * 200_000,
        "x" + r"\," * 200_000,
        r"\," * 200_000,
        "x" * 200_000,
        "{}" * 100_000,
        "{x}" * 60_000 + "^",
        "\\" * 200_000,
        r"\mathrm{" + "a" * 200_000,
        r"\mathrm{" + "a" * 200_000 + "}",
        " " * 200_000 + "x",
        r"\begin" + " " * 200_000,
        r"\sum" + r"\limits" * 60_000,
        r"\left(" * 50_000,
        r"\right)" * 50_000,
        r"\left( x \right)" * 30_000,
        r"\left" + " " * 200_000 + "(",
        r"\sqrt" * 50_000,
        r"\sqrt{" * 50_000,
        r"\text{" + "a " * 100_000,
        r"\text{" + "a " * 100_000 + "}",
        r"\quad" * 60_000,
    ],
    ids=lambda source: repr(source[:12]),
)
def test_hostile_sizes_return_and_do_not_recurse(source: str) -> None:
    # Each is sized so that a quadratic pass (tens of billions of steps) would
    # not come back, and each nests or repeats the one construct most likely to
    # recurse. A RecursionError here is the failure being guarded against.
    result = parse(source)
    assert isinstance(result, Formula | Refusal)


def test_nesting_is_allowed_up_to_the_cap_and_sets() -> None:
    deepest = "{" * MAX_DEPTH + "x" + "}" * MAX_DEPTH
    assert atoms(deepest) == (var("x"),)
    tower = "x" + "^{x" * (MAX_DEPTH - 1) + "}" * (MAX_DEPTH - 1)
    result = parse(tower)
    assert isinstance(result, Formula)
    assert set_formula(result, FONTS).height > 0
    assert refusal("x" + "^{x" * (MAX_DEPTH + 1)).kind is RefusalKind.NESTING


# --------------------------------------------------------------------------------
# 3. `typeset`: one call, and a font failure is a refusal
# --------------------------------------------------------------------------------

SIZE = sp_from_px(16.0, 96.0)


def test_typeset_is_parse_then_set() -> None:
    done = typeset(r"\sum_{i=1}^n i", SIZE, display=True)
    assert isinstance(done, Typeset)
    assert done.formula == parse(r"\sum_{i=1}^n i", display=True)
    assert done.box == set_formula(done.formula, formula_fonts(SIZE))
    assert done.box.width > 0 and done.box.depth > 0


def test_typeset_reuses_the_fonts_it_is_handed() -> None:
    done = typeset("x^2", SIZE, fonts=FONTS)
    assert isinstance(done, Typeset)
    assert done.fonts is FONTS
    assert done.box == box_of(atoms("x^2"), Style.TEXT)


def test_typeset_passes_a_parse_refusal_through_untouched() -> None:
    assert typeset(r"\hat2", SIZE) == parse(r"\hat2")
    assert isinstance(parse(r"\hat2"), Refusal)
    assert typeset("", SIZE, display=True) == parse("", display=True)


def test_a_missing_math_face_is_a_refusal_and_not_an_exception() -> None:
    def no_file(size: Scaled) -> MathFontMetrics:
        raise MissingFontError("math has no bundled file and none is registered")

    refused = typeset("x^2", SIZE, resolve=no_file)
    assert isinstance(refused, Refusal)
    assert (refused.kind, refused.position, refused.source) == (RefusalKind.FONT, 0, "x^2")
    assert "MissingFontError" in refused.reason and "none is registered" in refused.reason


def test_a_face_with_no_math_table_is_a_refusal_and_not_an_exception() -> None:
    from advtext import fontlib
    from advtext.fontmetrics import Face

    def prose_face(size: Scaled) -> MathFontMetrics:
        # Roboto: a real face, and no `MATH` table. The cast is the lie a host
        # registering the wrong file for the math role would be telling.
        return fontlib.metrics(Face.PROSE, float(size))  # type: ignore[return-value]

    refused = typeset(r"\frac12", SIZE, display=True, resolve=prose_face)
    assert isinstance(refused, Refusal)
    assert refused.kind is RefusalKind.FONT and refused.display is True
    assert "\n" not in refused.reason
    # The failure named is the missing table, not a slip in this test's fake.
    assert "'math'" in refused.reason, refused.reason
    assert not hasattr(prose_face(SIZE), "math")


def test_the_two_step_route_does_raise_which_is_why_typeset_exists() -> None:
    def no_file(size: Scaled) -> MathFontMetrics:
        raise MissingFontError("gone")

    with pytest.raises(MissingFontError):
        formula_fonts(SIZE, no_file)


# --------------------------------------------------------------------------------
# 4. Coverage, and the direction of the dependency
# --------------------------------------------------------------------------------


def test_every_glyph_a_supported_command_names_is_in_the_math_face() -> None:
    items: list[MathItem] = []
    for name in supported_commands():
        if name in ("frac", "limits", "nolimits", "overline", "underline"):
            continue
        if name in ("mathbb", "mathcal"):
            source = f"\\{name}{{ABCDEFGHIJKLMNOPQRSTUVWXYZ}}"
        elif name == "mathbf":
            source = r"\mathbf{ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789}"
        elif name in ("mathrm", "operatorname"):
            printable = "".join(chr(c) for c in range(0x20, 0x7F) if chr(c) not in "{}\\$")
            source = f"\\{name}{{{printable}}}"
        elif name in ("left", "right"):
            # The delimiters themselves; their sized variants are section 5's.
            source = "".join(f"\\left{d} a \\right{d}" for d in sized_delimiters())
        elif name == "sqrt":
            source = r"\sqrt{a}"
        elif name == "binom":
            source = r"\binom{a}{b}"
        elif name.startswith("text"):
            # Prose is set in a prose face; the math face is not asked for it.
            continue
        else:
            source = f"a \\{name} b"
        items.extend(atoms(source))
    items.extend(atoms("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
    items.extend(atoms("+-*=<>:()[]!?,;./|@ x'"))
    items.extend(atoms("−"))
    named = formulas.codepoints(items)
    assert len(set(named)) > 380
    assert missing_codepoints(items) == ()


def test_the_coverage_check_can_fail() -> None:
    # U+1D455 is the hole the italic `h` would fall in. If the check above
    # could not see it, it could not see anything.
    assert missing_codepoints((ord_(chr(0x1D455)),)) == (0x1D455,)


def test_the_engine_does_not_import_this_module() -> None:
    # By import, not by mention: a docstring in the engine may well name the
    # extension. What it may not do is depend on it.
    package = Path(advtext.math.__file__).parent
    checked = 0
    for path in sorted(package.glob("*.py")):
        for name in imports_of(path):
            checked += 1
            assert "mathtext" not in name, (path.name, name)
    assert checked > 5


def test_this_module_does_not_import_the_ui() -> None:
    # `advtext.ui.formulas` imports `advtext.markdown` and `advtext.ui`, which
    # is most of the tree, to reach one italic table; this module repeats the
    # table instead. (It may import `advtext.markdown` itself, and does, for
    # `markdown_math`: markdown does not import it back, which
    # `tests/test_mathinline.py` pins from the other side.)
    import advtext.mathtext as module

    imported = imports_of(Path(module.__file__))
    assert any(name.startswith("advtext.math") for name in imported)
    assert not [name for name in imported if name.startswith("advtext.ui")]


def imports_of(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


# --------------------------------------------------------------------------------
# 5. The second pass: radicals, sized delimiters, spaces, words
# --------------------------------------------------------------------------------


def chars(box: Box) -> list[CharNode]:
    """
    Every character node of a box, depth first, in the order it is set.
    """
    found: list[CharNode] = []
    for node in box.contents:
        if isinstance(node, CharNode):
            found.append(node)
        elif isinstance(node, Box):
            found.extend(chars(node))
    return found


def rules(box: Box) -> int:
    return sum(
        rules(node) if isinstance(node, Box) else isinstance(node, Rule) for node in box.contents
    )


def scripted(atom: Atom, *, sup: str = "", sub: str = "") -> Atom:
    """
    `atom` with one-character scripts, in the form the parser gives a script.
    """
    return replace(
        atom,
        sup=SubList((ord_(sup),)) if sup else atom.sup,
        sub=SubList((ord_(sub),)) if sub else atom.sub,
    )


def test_a_square_root_is_the_engines_radical() -> None:
    assert atoms(r"\sqrt{x+1}") == (radical(group(var("x"), bin_("+"), ord_("1"))),)
    # One token, by TeX's rule, when there is no brace.
    assert atoms(r"\sqrt x y") == (radical(group(var("x"))), var("y"))
    assert atoms(r"\sqrt 12") == (radical(group(ord_("1"))), ord_("2"))
    assert atoms(r"\sqrt{x}^2") == (scripted(radical(group(var("x"))), sup="2"),)
    assert atoms(r"\sqrt{\sqrt{x}}") == (radical(group(radical(group(var("x"))))),)
    assert atoms(r"\sqrt{}") == (radical(group()),)


def test_a_radical_sets_a_sign_and_a_rule_over_its_radicand() -> None:
    plain = box_of_source("x")
    rooted = box_of_source(r"\sqrt{x}")
    assert rooted.height > plain.height and rooted.width > plain.width
    assert rules(rooted) == 1 and rules(plain) == 0
    assert fontlib_glyph(chars(rooted)[0]).startswith("radical")
    # The sign is chosen to cover: over a fraction it is another outline.
    over_fraction = box_of_source(r"\sqrt{\frac{a}{b}}", display=True)
    assert chars(over_fraction)[0].codepoint != chars(rooted)[0].codepoint


DELIMITERS = sized_delimiters()


def test_the_delimiter_table_is_what_the_task_names_and_a_little_more() -> None:
    asked_for = {"(", ")", "[", "]", "\\{", "\\}", "|", "\\|", "\\langle", "\\rangle", "."}
    assert asked_for <= set(DELIMITERS)
    assert DELIMITERS["."] is None
    assert [written for written, codepoint in DELIMITERS.items() if codepoint is None] == ["."]
    assert DELIMITERS["<"] == DELIMITERS["\\langle"] == 0x27E8
    assert DELIMITERS["\\|"] == DELIMITERS["\\Vert"] == 0x2016
    assert DELIMITERS["|"] == DELIMITERS["\\vert"] == 0x7C


@pytest.mark.parametrize("written", sorted(DELIMITERS))
def test_each_delimiter_is_the_engines_left_right_pair_and_has_sizes_to_choose_from(
    written: str,
) -> None:
    r"""
    For every delimiter `\left` accepts: the atoms are `delimited(...)`'s, the
    font has a chain of variants for it reaching about three em, and a tall
    body is set with a different outline from a short one -- which is the
    whole of what `\left` is for. The null delimiter sets no glyph at all.
    """
    codepoint = DELIMITERS[written]
    character = None if codepoint is None else chr(codepoint)
    short = f"\\left{written} x \\right{written}"
    tall = f"\\left{written} \\frac{{a}}{{b}} \\right{written}"
    assert atoms(short) == (delimited(character, group(var("x")), character),)

    short_box = box_of_source(short)
    tall_box = box_of_source(tall, display=True)
    if codepoint is None:
        assert [chr(node.codepoint) for node in chars(short_box)] == [italic("x")]
        return
    face = FONTS.faces[min(FONTS.faces)]
    chain = face.vertical_variants(codepoint)
    assert len(chain) >= 8, (written, len(chain))
    assert chain[-1].extent >= 2.9 * face.em, (written, chain[-1].extent / face.em)
    variants = {variant.codepoint for variant in chain}
    first, last = chars(tall_box)[0].codepoint, chars(tall_box)[-1].codepoint
    assert first in variants and last in variants
    assert first == last, "one delimiter on both sides is one outline on both sides"
    assert first != chars(short_box)[0].codepoint
    assert tall_box.height + tall_box.depth > short_box.height + short_box.depth


def test_a_delimiter_with_no_chain_of_sizes_is_not_in_the_table() -> None:
    # The control for the chain check above: the arrows have two sizes, `<`
    # as itself has none, and neither is offered.
    face = FONTS.faces[min(FONTS.faces)]
    assert len(face.vertical_variants(0x2191)) < 8
    assert face.vertical_variants(ord("<")) == ()
    assert 0x2191 not in DELIMITERS.values() and ord("<") not in DELIMITERS.values()


def test_left_and_right_pair_nest_take_scripts_and_need_not_match() -> None:
    inner_pair = delimited("[", group(var("a")), "]")
    assert atoms(r"\left( \left[ a \right] \right)^2") == (
        scripted(delimited("(", group(inner_pair), ")"), sup="2"),
    )
    assert atoms(r"\left( x \right]") == (delimited("(", group(var("x")), "]"),)
    assert atoms(r"\left. x \right|_0") == (
        scripted(delimited(None, group(var("x")), "|"), sub="0"),
    )
    assert atoms(r"\left\{x\right\}") == (delimited("{", group(var("x")), "}"),)
    assert atoms(r"\left(\right)") == (delimited("(", group(), ")"),)
    # A group inside a pair, and a pair inside a group, close in their own order.
    assert atoms(r"\left( {a} \right)") == (delimited("(", group(var("a")), ")"),)
    assert atoms(r"{\left( a \right)}") == (
        Atom(AtomType.ORD, SubList((delimited("(", group(var("a")), ")"),))),
    )
    # ... and the commands that only begin with `\right` are still themselves.
    assert atoms(r"a \rightarrow b")[1] == rel("→")
    assert atoms(r"\left( a \rightarrow b \right)") == (
        delimited("(", group(var("a"), rel("→"), var("b")), ")"),
    )


def test_a_fitted_pair_is_larger_than_the_fixed_one_round_the_same_fraction() -> None:
    fixed = box_of_source(r"(\frac{a}{b})", display=True)
    fitted = box_of_source(r"\left(\frac{a}{b}\right)", display=True)
    assert fontlib_glyph(chars(fixed)[0]) == "parenleft"
    assert fontlib_glyph(chars(fitted)[0]).startswith("parenleft.v")
    assert fitted.height + fitted.depth > fixed.height + fixed.depth


def fontlib_glyph(node: CharNode) -> str:
    return str(fontlib.glyph_name(Face.MATH, node.codepoint))


SPACES = {
    r"\,": THIN_SPACE,
    r"\thinspace": THIN_SPACE,
    r"\:": MED_SPACE,
    r"\>": MED_SPACE,
    r"\medspace": MED_SPACE,
    r"\;": THICK_SPACE,
    r"\thickspace": THICK_SPACE,
    r"\!": NEGATIVE_THIN_SPACE,
    r"\negthinspace": NEGATIVE_THIN_SPACE,
    r"\quad": QUAD,
    r"\qquad": QQUAD,
}
MU = {r"\,": 3, r"\:": 4, r"\;": 5, r"\!": -3, r"\quad": 18, r"\qquad": 36}


@pytest.mark.parametrize("command", SPACES)
def test_each_space_command_is_the_engines_space_atom(command: str) -> None:
    assert atoms(f"a{command} b") == (var("a"), SPACES[command], var("b"))
    assert SPACES[command].kind is AtomType.SPACE


@pytest.mark.parametrize("command", MU)
def test_each_space_is_its_math_units_wide(command: str) -> None:
    quad = round(FONTS.params(Style.TEXT).math_quad)
    added = width(f"a{command} b") - width("ab")
    # A mu is a whole number of scaled points, so the error grows with the count.
    assert abs(added - quad * MU[command] / 18) <= abs(MU[command]), (command, added, quad)
    assert (added < 0) == (MU[command] < 0)


def test_a_script_after_a_space_hangs_on_nothing_and_a_space_can_be_a_script() -> None:
    # A space is glue, not something a script attaches to (TeX: a new empty noad).
    assert atoms(r"x\,^2") == (var("x"), THIN_SPACE, scripted(Atom(AtomType.ORD), sup="2"))
    assert atoms(r"x^\,") == (replace(var("x"), sup=SubList((THIN_SPACE,))),)
    assert atoms(r"\frac\,\quad") == (inner(Fraction(SubList((THIN_SPACE,)), SubList((QUAD,)))),)
    assert atoms(r"\,") == (THIN_SPACE,)
    assert box_of_source(r"\,").width == width("a\\, b") - width("ab")


CLASS_SOURCES = {
    AtomType.ORD: "x",
    AtomType.OP: r"\sum",
    AtomType.BIN: "+",
    AtomType.REL: "=",
    AtomType.OPEN: "(",
    AtomType.CLOSE: ")",
    AtomType.PUNCT: ",",
    AtomType.INNER: r"\ldots",
}


def test_the_class_sources_are_of_their_classes() -> None:
    for kind, source in CLASS_SOURCES.items():
        (atom,) = atoms(source)
        assert isinstance(atom, Atom) and atom.kind is kind
    assert len(CLASS_SOURCES) == 8


@pytest.mark.parametrize("left", CLASS_SOURCES, ids=lambda kind: kind.name)
@pytest.mark.parametrize("right", CLASS_SOURCES, ids=lambda kind: kind.name)
def test_a_space_adds_its_own_width_and_nothing_else(left: AtomType, right: AtomType) -> None:
    r"""
    The acceptance test the first draft of the subset left for the engine's space.

    Width is the observable for "the class rules saw the same thing": a Bin
    that flipped to or from Ord, or a table entry that changed, moves a line by
    a whole mu-skip. So for every pair of classes, with something either side
    in some cases and nothing in others, `L \, R` is exactly `L R` and three
    mu, in three styles. Written against a space folded into its neighbour
    (`.concerns/C-mathtext-scripts/`); it passes unchanged against the
    engine's `SPACE` atom, which is glue and is stepped over by both passes.
    """
    for style in (Style.TEXT, Style.DISPLAY, Style.SCRIPT):
        thin = box_of((THIN_SPACE,), style).width
        assert thin > 0
        for before in ("", "a", "="):
            for after in ("", "b", ")"):
                plain = f"{before} {CLASS_SOURCES[left]} {CLASS_SOURCES[right]} {after}"
                spaced = f"{before} {CLASS_SOURCES[left]} \\, {CLASS_SOURCES[right]} {after}"
                assert width(spaced, style) == width(plain, style) + thin, (spaced, style)


def test_a_naive_ordinary_space_would_not_be_transparent() -> None:
    # The control for the test above: the same check fails for the obvious
    # construction -- an ordinary atom holding a space glyph -- so passing it
    # is a property of the engine's space and not of the pairs chosen.
    naive = (rel("="), ord_(chr(0x2006)), bin_("−"), var("x"))
    spaced = atoms(r"= \, -x")
    plain = atoms(r"= -x")
    thin = box_of((THIN_SPACE,), Style.TEXT).width
    assert box_of(spaced, Style.TEXT).width == box_of(plain, Style.TEXT).width + thin
    assert box_of(naive, Style.TEXT).width > box_of(spaced, Style.TEXT).width


def test_text_is_the_engines_prose_atom() -> None:
    assert atoms(r"x \text{ if } y") == (var("x"), prose_text(" if "), var("y"))
    assert atoms(r"\textrm{a b}") == atoms(r"\textnormal{a b}") == (prose_text("a b"),)
    assert atoms(r"\textit{a b}") == (prose_text("a b", face=Face.PROSE_ITALIC),)
    assert atoms(r"\textbf{a b}") == (prose_text("a b", face=Face.PROSE_BOLD),)
    # Blanks are kept, a run of them as one; nothing else is touched.
    assert atoms("\\text{a  \n\t b }") == (prose_text("a b "),)
    assert atoms(r"\text{naïve — x^2_3 & 50%}") == (prose_text("naïve — x^2_3 & 50%"),)
    assert atoms(r"\text{}") == (prose_text(""),)
    assert atoms(r"\text {max}_i") == (replace(prose_text("max"), sub=SubList((var("i"),))),)
    # `\mathrm` is not this: it is the math face's upright letters, blanks dropped.
    assert atoms(r"\mathrm{a b}") != atoms(r"\text{a b}")


def test_text_is_set_in_a_prose_face_at_the_size_of_the_style_it_lands_in() -> None:
    text_size, script_size = sorted(FONTS.sizes.values(), reverse=True)[:2]
    upright = chars(box_of_source(r"\text{if}"))
    assert [chr(node.codepoint) for node in upright] == ["i", "f"]
    assert {parse_font_key(node.font).face for node in upright} == {Face.PROSE}
    assert {parse_font_key(node.font).size for node in upright} == {text_size}

    x, i, f = chars(box_of_source(r"x_{\text{if}}"))
    assert parse_font_key(x.font).face is Face.MATH
    assert {parse_font_key(node.font).face for node in (i, f)} == {Face.PROSE}
    assert {parse_font_key(node.font).size for node in (i, f)} == {script_size}

    bold = chars(box_of_source(r"\textbf{b}"))
    assert parse_font_key(bold[0].font).face is Face.PROSE_BOLD
    # Its blanks are the prose face's interword space, each one kept.
    assert width(r"\text{a b}") > width(r"\text{ab}")
    assert width(r"\text{ a }") > width(r"\text{a}")


SHORT_BY_A_LITTLE = r"\left( \frac{\sum\limits_{i=1}^{n} a_i}{\prod\limits_{k=1}^{n} b_k} \right)"
r"""
What C-mathtext2 measured refused for being 1.05 times too tall, and what the
rule was amended for: it sets now, between the largest parentheses there are.
"""

TOO_TALL = r"\left( 1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{1 + \frac{1}{x}}}}} \right)"
r"""
A continued fraction five deep: the largest parenthesis covers under three
quarters of it, in text style and in display, and it is still refused.
"""


def test_content_a_little_taller_than_the_largest_delimiter_takes_the_largest() -> None:
    r"""
    Review 2, item 9. TeX's rule (factor 901, shortfall 5pt) is satisfied by no
    parenthesis of the font for this formula; the largest is used, as TeX uses
    it, because it covers at least three quarters of the content.
    """
    done = typeset(SHORT_BY_A_LITTLE, SIZE)
    assert isinstance(done, Typeset)
    face = done.fonts.face(Style.TEXT)
    largest = face.vertical_variants(ord("("))[-1].codepoint
    found = [node.codepoint for node in chars_of(done.box)]
    assert found[0] == largest
    assert found[-1] == face.vertical_variants(ord(")"))[-1].codepoint
    # ... and it does fall short of what it stands beside, which is the point.
    paren = done.fonts.measure(CharNode(done.fonts.key(Style.TEXT), largest))
    assert paren.height + paren.depth < done.box.height + done.box.depth
    assert 4 * (paren.height + paren.depth) >= 3 * (done.box.height + done.box.depth)
    # In display style the same source is taller, and under the three quarters.
    refused = typeset(SHORT_BY_A_LITTLE, SIZE, display=True)
    assert isinstance(refused, Refusal) and refused.kind is RefusalKind.LAYOUT


def chars_of(box: Box) -> list[CharNode]:
    found: list[CharNode] = []
    for node in box.contents:
        if isinstance(node, CharNode):
            found.append(node)
        elif isinstance(node, Box):
            found.extend(chars_of(node))
    return found


def test_a_script_on_a_group_with_a_script_clears_the_inner_script() -> None:
    r"""
    Review 2, item 1, on the real font: `{x^2}^3` set its 3 where `x^3` sets
    it, so the two scripts ran together as 23. TeX places a script on a group
    from the group's box (`tex.web:14889`-14895).
    """
    inner, outer, plain = (typeset(source, SIZE) for source in ("x^2", "{x^2}^3", "x^3"))
    assert isinstance(inner, Typeset) and isinstance(outer, Typeset) and isinstance(plain, Typeset)

    def raised(done: Typeset) -> int:
        return -[node for node in done.box.contents if isinstance(node, Box)][-1].shift_amount

    from_the_box = inner.box.height - round(outer.fonts.params(Style.SCRIPT).sup_drop)
    assert raised(outer) >= from_the_box > raised(plain)
    assert raised(inner) == raised(plain)
    # The three other shapes the review names all set, and a subscript drops.
    for source in (r"{a_i}_j", r"{(a+b)}^2", r"\mathrm{ab}^2"):
        assert isinstance(typeset(source, SIZE), Typeset), source
    lower = typeset(r"{a_i}_j", SIZE)
    bare = typeset(r"a_j", SIZE)
    assert isinstance(lower, Typeset) and isinstance(bare, Typeset)
    assert -raised(lower) > -raised(bare)


def test_a_word_with_a_character_the_prose_face_lacks_is_refused_by_name() -> None:
    r"""
    Review 2, item 5: `v = \text{...}` with CJK inside set a formula with a
    hole after the equals sign.
    """
    source = r"v = \text{速度}"
    assert not fontlib.metrics(Face.PROSE, 16.0).has(ord("速"))
    refused = typeset(source, SIZE)
    assert isinstance(refused, Refusal)
    assert refused.kind is RefusalKind.FONT
    assert refused.position == source.index("速")
    assert "'速'" in refused.reason and "U+901F" in refused.reason and "prose" in refused.reason
    with pytest.raises(MissingGlyphError):
        set_formula(parse_formula(source), formula_fonts(SIZE))
    # Controls: words the face has still set; so does the italic face's own check.
    assert isinstance(typeset(r"v = \text{speed}", SIZE), Typeset)
    assert isinstance(typeset(r"v = \textit{café}", SIZE), Typeset)


def test_backslash_space_and_tilde_are_six_math_units() -> None:
    r"""
    Review 2, item 10: `a\ b` and `x~y` were refused. They are the engine's
    own `SPACE` item at six mu -- plain TeX's interword space in its own text
    font -- transparent to the classes either side like every other space.
    """
    six = (space(6, stretch=3, shrink=2),)
    assert atoms("a\\ b") == atoms("a~b") == atoms("a\\\nb") == (var("a"), *six, var("b"))
    for style in (Style.TEXT, Style.DISPLAY, Style.SCRIPT):
        mu = FONTS.mu(style)
        for spaced in ("a\\ b", "a~b", "= ~ -x"):
            plain = spaced.replace("\\ ", " ").replace("~", " ")
            assert width(spaced, style) == width(plain, style) + 6 * mu, (spaced, style)
    assert width(r"a\ b") == 2 * (width(r"a\,b") - width("ab")) + width("ab")
    # A script after one hangs on nothing, as after any space.
    assert atoms(r"a~^2")[-1] == Atom(AtomType.ORD, sup=atoms("2") and SubList(atoms("2")))
    assert {" "} <= set(supported_commands())
    assert " " not in refused_commands()


def test_binom_is_a_barless_fraction_between_fitted_parentheses() -> None:
    r"""
    Review 2, item 10: both halves were in the engine. The box is the box the
    hand-built atoms set, there is no rule in it, and the parentheses grow
    with the style.
    """
    built = (ord_(delimited("(", frac(var("n"), var("k"), thickness=0), ")").nucleus),)
    assert atoms(r"\binom{n}{k}") == atoms(r"\binom nk") == built
    for style in (Style.TEXT, Style.DISPLAY):
        box = box_of(atoms(r"\binom{n}{k}"), style)
        assert box == box_of(built, style)
        assert not rules_in(box)
        assert [chr(node.codepoint) for node in chars_of(box)][1:3] == [
            italic("n"),
            italic("k"),
        ]
    text = chars_of(box_of(built, Style.TEXT))
    display = chars_of(box_of(built, Style.DISPLAY))
    chain = [v.codepoint for v in FONTS.face(Style.TEXT).vertical_variants(ord("("))]
    assert chain.index(display[0].codepoint) > chain.index(text[0].codepoint) > 0
    # It is an Ord, as amsmath's is, and takes scripts as one box.
    assert width(r"a \binom{n}{k} b") == width("a") + width(r"\binom{n}{k}") + width("b")
    assert isinstance(typeset(r"\binom{n}{k}^2 + \binom{n+1}{k}", SIZE), Typeset)
    assert "binom" in supported_commands() and "dbinom" in refused_commands()


def rules_in(box: Box) -> list[Rule]:
    found: list[Rule] = []
    for node in box.contents:
        if isinstance(node, Rule):
            found.append(node)
        elif isinstance(node, Box):
            found.extend(rules_in(node))
    return found


def test_content_taller_than_the_largest_delimiter_is_a_layout_refusal() -> None:
    r"""
    The engine's refusal, as the extension's: `parse` takes it, `set_formula`
    raises the engine's error, `typeset` returns a `LAYOUT` refusal whose
    reason names the delimiter and a proportion and no scaled points.

    Two controls: the same content between fixed parentheses sets, and a
    shorter body between `\left(` and `\right)` sets.
    """
    formula = parse(TOO_TALL)
    assert isinstance(formula, Formula)
    fonts = formula_fonts(SIZE)
    with pytest.raises(DelimiterTooSmallError) as caught:
        set_formula(formula, fonts)
    error = caught.value
    assert isinstance(error, MathLayoutError) and error.codepoint == ord("(")
    assert error.needed > error.largest > 0

    refused = typeset(TOO_TALL, SIZE)
    assert isinstance(refused, Refusal)
    assert (refused.kind, refused.position, refused.source) == (RefusalKind.LAYOUT, 0, TOO_TALL)
    assert refused.reason == (
        f"what is between the delimiters needs a ( {error.needed / error.largest:.2f} times "
        "as tall as the largest the math face has, and one is not assembled from pieces here"
    )
    assert typeset(TOO_TALL, SIZE, fonts=fonts) == refused

    fixed = TOO_TALL.replace(r"\left(", "(").replace(r"\right)", ")")
    assert isinstance(typeset(fixed, SIZE), Typeset)
    assert isinstance(typeset(r"\left( \frac{a}{b} \right)", SIZE), Typeset)


def test_a_radicand_taller_than_the_largest_radical_sign_is_a_layout_refusal() -> None:
    def roots(depth: int) -> str:
        return r"\sqrt{" * depth + "x" + "}" * depth

    assert isinstance(typeset(roots(5), SIZE), Typeset)
    refused = typeset(roots(6), SIZE)
    assert isinstance(refused, Refusal) and refused.kind is RefusalKind.LAYOUT
    assert refused.reason.startswith("what is under the root needs a radical sign 1.")
    assert "(" not in refused.reason and "U+" not in refused.reason


def test_words_with_no_prose_face_to_set_them_in_are_a_font_refusal() -> None:
    math_only = math_fonts(SIZE, formulas.fontlib_math_metrics)
    assert math_only.text is None
    refused = typeset(r"x \text{ if } y", SIZE, fonts=math_only)
    assert isinstance(refused, Refusal)
    assert refused.kind is RefusalKind.FONT
    assert refused.reason.startswith("there is no prose face to set its words in")
    with pytest.raises(TextFaceUnavailableError):
        set_formula(parse_formula(r"\text{a}"), math_only)
    # The control: the same fonts set a formula with no words in it.
    assert isinstance(typeset("x + y", SIZE, fonts=math_only), Typeset)
    # ... and `formula_fonts` brings the prose faces unless told otherwise.
    assert formula_fonts(SIZE).text is not None


def parse_formula(source: str) -> Formula:
    result = parse(source)
    assert isinstance(result, Formula), result
    return result


def test_the_markdown_builder_sets_the_new_constructs_and_refuses_what_is_too_tall() -> None:
    from advtext.markdown import MathRefused
    from advtext.mathtext import markdown_math

    build = markdown_math()
    for source in (r"\sqrt{x^2+y^2}", r"\left( \frac{a}{b} \right)", r"a \, b", r"x \text{ if } y"):
        for display in (False, True):
            built = build(source, display, SIZE)
            assert isinstance(built, Box) and built.width > 0, source
    refused = build(TOO_TALL, False, SIZE)
    assert isinstance(refused, MathRefused)
    assert "as tall as the largest the math face has" in refused.reason
    assert build(TOO_TALL, False, SIZE) is refused, "a refusal is remembered like a box"

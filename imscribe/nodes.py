r"""
The node vocabulary: boxes, glue, kerns, penalties and the rest of TeX's list items.

A document here is a list of nodes. `hpack` and `vpack` measure a list into a
`Box`; the line breaker cuts a list at legal points; ship-out walks the result
and emits positions. Everything downstream is written against the types in this
module, and nothing in this module knows how to lay anything out -- the
algorithms live elsewhere so that they can be tested against hand-built lists.

**Height and depth are measured from the baseline, not from a bounding box.**
This is the single most common porting error and it is worth reading twice. A
box's reference point sits *on the baseline at its left edge*. `height` extends
upward from there and `depth` extends downward, so a box sitting at baseline `y`
in a downward-growing coordinate system occupies `y - height` to `y + depth`
(`docs/tex-notes.md` §1.3). A parenthesis has height and depth; a lowercase "x"
has height and no depth. Treating `height` as "how tall the thing is" silently
puts every descender-bearing line a few points wrong and the result looks like a
leading bug rather than a sign error. `shift_amount` uses the same convention:
**positive shifts down** in an hlist (§653), and right in a vlist.

**Infinite glue orders do not add to finite ones.** `GlueTotal` exists to make
that unexpressible rather than merely documented; see its docstring for why
pairwise "highest order wins" is the wrong shape and loses information.

Deliberately absent:

- **`Ligature`.** Ligature reconstruction after a break is out of scope
  (`docs/decisions.md`), and a ligature node that nothing reconstructs is a
  `CharNode` with extra fields to keep consistent.
- **`Ins`, `Mark`, `Adjust`, `Whatsit`, `Unset`.** Inserts, marks and `\vadjust`
  belong to page breaking; `unset_node` belongs to `\halign`. Both are out.
- **Leaders and `\nonscript`**, which are glue subtypes we do not use.
- **Resolved metrics on `CharNode`.** A `CharNode` names a face and a codepoint
  and nothing else, exactly as TeX's does. Its advance comes from the metrics
  interface at pack time. Caching the advance in the node would create a second
  source of truth that goes stale the moment a face is re-resolved at a
  different size.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final, TypeAlias

from imscribe.badness import INF_BAD
from imscribe.units import RUNNING, GlueOrder, Scaled

__all__ = [
    "EJECT_PENALTY",
    "INF_PENALTY",
    "Box",
    "BoxKind",
    "CharNode",
    "Disc",
    "FontKey",
    "Glue",
    "GlueSign",
    "GlueSpec",
    "GlueTotal",
    "Kern",
    "KernKind",
    "MathOff",
    "MathOn",
    "Node",
    "Penalty",
    "Rule",
    "is_discardable",
    "permits_break_at_following_glue",
]

FontKey: TypeAlias = str
"""
An opaque name for a resolved face at a size, e.g. "roboto-regular-16".

A `str` because the layout core must not know what a font *is* -- it hands the
key back to the metrics interface and gets numbers. `imscribe.fontmetrics` owns
what keys exist and what they mean; this module only carries them.
"""

INF_PENALTY: Final = INF_BAD
"""
A penalty that forbids a break. TeX's `@d inf_penalty = inf_bad` (§157).

The identity with `INF_BAD` is the source's, not a coincidence to be tidied
away: penalties and badness are compared against each other in the demerits
formula, so they share a magnitude on purpose.
"""

EJECT_PENALTY: Final = -INF_PENALTY
"""
A penalty that forces a break. TeX's `@d eject_penalty = -inf_penalty` (§157).
"""


class BoxKind(enum.Enum):
    """
    Whether a box's contents run horizontally or vertically.

    One `Box` type with a kind rather than separate `HBox` and `VBox` classes.
    The source makes the same call -- `hlist_node` and `vlist_node` are
    different `type` codes over a byte-identical seven-word layout (§135, §137)
    -- and every field, plus `shift_amount`, `glue_set` and the whole of
    ship-out, is shared. Two classes would duplicate nine fields and force an
    `HBox | VBox` union at every site, and they would buy no exhaustiveness that
    `match box.kind` with `assert_never` does not already give.

    What the kind *does* change is which dimension the glue is set along and
    which way `shift_amount` moves the box, and those are branches either way.
    """

    HLIST = enum.auto()
    VLIST = enum.auto()


class GlueSign(enum.Enum):
    """
    Which direction a packed box's glue was set in (§135: `normal/stretching/shrinking`).

    `NORMAL` means the glue sits at its natural width and `glue_set` is not
    consulted. Note that `glue_set` is stored as a *positive* ratio for shrink
    as well as stretch (§664), so the sign lives here and nowhere else.
    """

    NORMAL = enum.auto()
    STRETCHING = enum.auto()
    SHRINKING = enum.auto()


class KernKind(enum.Enum):
    """
    Where a kern came from (§155).

    It matters for breaking, and in two opposite directions, which is why the
    distinction cannot be dropped:

    - A break *at* the kern -- before it -- is legal only when the kind is
      `EXPLICIT` and a glue node follows (§866's `kern_break`, reached from the
      `kern_node` arm only `if subtype(cur_p)=explicit`).
    - A break at a glue node *after* the kern is legal only when the kind is
      **not** `EXPLICIT` (§868's third branch). See
      `permits_break_at_following_glue`.

    The two rules concern different positions -- one before the kern and one
    after it -- so they are not in tension, and a `NORMAL` font or math kern
    genuinely enables a breakpoint that an `EXPLICIT` one suppresses.
    """

    NORMAL = enum.auto()
    EXPLICIT = enum.auto()
    ACCENT = enum.auto()


@dataclass(frozen=True, slots=True)
class GlueSpec:
    """
    The stretchability of a piece of glue (§150).

    Separate from `Glue` because a spec is a shareable value -- `\\baselineskip`
    is one spec referenced by every interline glue node -- while a `Glue` is a
    position in a list. TeX expresses the same split with a reference-counted
    `glue_spec` record; frozen dataclasses give us the sharing for free.

    `stretch` and `shrink` are magnitudes and are not negative: shrinking is
    expressed by `shrink` plus a `SHRINKING` glue sign, not by a negative
    `stretch`.
    """

    width: Scaled = 0
    stretch: Scaled = 0
    stretch_order: GlueOrder = GlueOrder.NORMAL
    shrink: Scaled = 0
    shrink_order: GlueOrder = GlueOrder.NORMAL


@dataclass(frozen=True, slots=True)
class GlueTotal:
    """
    Stretch or shrink accumulated across a list, kept separately per order of infinity.

    This is the type that makes "infinite orders do not add to finite ones"
    structural. The tempting shape -- an `(amount, order)` pair whose `__add__`
    returns whichever operand has the higher order -- is *wrong*, and §646's own
    worked example is the counterexample. Adding 3pt, 8fill, 5fil, 6pt, -3fil
    and -8fill must come to "essentially 2fil". Pairwise highest-order-wins
    collapses `8fill + 5fil` to `8fill`, then `8fill + (-8fill)` to zero at
    order `fill`, and the 5fil that decides the answer has been thrown away.

    So every order is accumulated independently and the winner is chosen only at
    the end, which is exactly what `hpack` does with its
    `total_stretch: array[glue_ord] of scaled` (§646). Addition here is total,
    associative and lossless, and `dominant_order` is the query that applies the
    rule once.
    """

    amounts: tuple[Scaled, Scaled, Scaled, Scaled] = (0, 0, 0, 0)

    @classmethod
    def of(cls, amount: Scaled, order: GlueOrder = GlueOrder.NORMAL) -> GlueTotal:
        """
        A total holding a single contribution at one order.
        """
        slots: list[Scaled] = [0, 0, 0, 0]
        slots[order] = amount
        return cls((slots[0], slots[1], slots[2], slots[3]))

    def __add__(self, other: GlueTotal) -> GlueTotal:
        """
        Add componentwise. No order is ever folded into another.
        """
        a, b = self.amounts, other.amounts
        return GlueTotal((a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3]))

    def __getitem__(self, order: GlueOrder) -> Scaled:
        """
        The accumulated amount at one order.
        """
        return self.amounts[order]

    @property
    def dominant_order(self) -> GlueOrder:
        """
        The highest order with a nonzero amount, or `NORMAL` if every order is zero.

        §646: "The highest order of infinity that has a nonzero coefficient is
        then used as if no other orders were present." A total that cancels to
        zero at every order reports `NORMAL`, which pairs with a `dominant` of
        zero and makes the box unsettable in that direction -- the correct
        reading, and the reason the fallback is not an error.
        """
        for order in (GlueOrder.FILLL, GlueOrder.FILL, GlueOrder.FIL):
            if self.amounts[order] != 0:
                return order
        return GlueOrder.NORMAL

    @property
    def dominant(self) -> Scaled:
        """
        The amount at `dominant_order`: the only stretchability that counts.
        """
        return self.amounts[self.dominant_order]


@dataclass(frozen=True, slots=True)
class CharNode:
    """
    One glyph, named rather than measured (§134).

    Carries no dimensions on purpose -- see the module docstring. In TeX a char
    node is a single word holding a font and a character precisely because the
    metrics are a property of the font, not of the occurrence.
    """

    font: FontKey
    codepoint: int


@dataclass(frozen=True, slots=True)
class Box:
    """
    A packed list with settled dimensions (§135, §137).

    `height` is the extent above the baseline and `depth` the extent below it;
    the module docstring says why that matters more than it looks like it
    should. `shift_amount` moves the box down in an hlist and right in a vlist,
    positive in both cases (§653).

    `glue_set` is the one deliberate float in a scaled-integer system
    (`imscribe.units`): it is a ratio, TeX stores it as a `real` too (§109), and
    it is stored positive for shrink as well as stretch, with the direction in
    `glue_sign`. Rendering multiplies an accumulated stretch by it and rounds
    *once* per glue node against a running total (`docs/tex-notes.md` §2.5),
    which is what keeps the error from walking along the line.

    `glue_order` records which order of infinity the setting applies to. Glue in
    the contents whose order differs from it renders at its natural width.
    """

    kind: BoxKind
    contents: tuple[Node, ...] = ()
    width: Scaled = 0
    height: Scaled = 0
    depth: Scaled = 0
    shift_amount: Scaled = 0
    glue_set: float = 0.0
    glue_sign: GlueSign = GlueSign.NORMAL
    glue_order: GlueOrder = GlueOrder.NORMAL


@dataclass(frozen=True, slots=True)
class Rule:
    """
    A solid black rectangle (§138).

    Any of the three dimensions may be `RUNNING`, meaning "resolve me against
    whatever box encloses me at ship-out". That is how a full-width horizontal
    rule works without anyone measuring the column. A running dimension is a
    sentinel, not a length: it must be replaced before anything adds it to
    anything.

    The source's invariant is worth keeping: the `width` is never running in an
    hlist, and the `height` and `depth` are never running in a vlist.
    """

    width: Scaled = RUNNING
    height: Scaled = RUNNING
    depth: Scaled = RUNNING

    @property
    def is_running(self) -> bool:
        """
        Whether any dimension still has to be resolved against an enclosing box.
        """
        return RUNNING in (self.width, self.height, self.depth)


@dataclass(frozen=True, slots=True)
class Glue:
    """
    Stretchable, shrinkable, discardable space (§149).

    A legal breakpoint sits *before* a glue node, and only when the preceding
    node permits it -- `permits_break_at_following_glue`, which is **not** the
    negation of `is_discardable`. Glue after a chosen break is discarded, which
    is why a line does not start with the space that ended the previous one.
    """

    spec: GlueSpec


@dataclass(frozen=True, slots=True)
class Kern:
    """
    Fixed space that does not stretch (§155).

    Discardable like glue, but a legal breakpoint only when `kind` is `EXPLICIT`
    and a glue node follows.
    """

    width: Scaled = 0
    kind: KernKind = KernKind.NORMAL


@dataclass(frozen=True, slots=True)
class Penalty:
    """
    The cost, in demerits, of breaking here (§157).

    Negative values encourage a break and positive values discourage one.
    `INF_PENALTY` or more forbids it outright; `EJECT_PENALTY` or less forces
    it. Both are named constants in this module because a bare `10000` at a call
    site is indistinguishable from an arbitrary large number, and the identity
    with `INF_BAD` is the reason the value is what it is.
    """

    value: int = 0

    @property
    def forbids_break(self) -> bool:
        """
        Whether this penalty makes a break here illegal rather than merely costly.
        """
        return self.value >= INF_PENALTY

    @property
    def forces_break(self) -> bool:
        """
        Whether this penalty compels a break here.
        """
        return self.value <= EJECT_PENALTY


@dataclass(frozen=True, slots=True)
class Disc:
    """
    A discretionary break: what to insert if broken here, and what to drop (§145).

    `pre_break` ends the line, `post_break` starts the next one, and
    `replace_count` nodes following this one are the text those two replace when
    the break is taken. All three lists must contain only characters, kerns,
    boxes and rules.

    An empty `pre_break` marks an explicit `\\-`-style opportunity rather than a
    hyphenation point, and is charged the explicit-hyphen penalty instead of the
    ordinary one. Nothing in this project *generates* discretionaries --
    hyphenation is out of scope (`docs/decisions.md`) -- but the line breaker
    must still handle them correctly, because a caller can build them by hand
    and a compound word's existing hyphen is one.
    """

    pre_break: tuple[Node, ...] = ()
    post_break: tuple[Node, ...] = ()
    replace_count: int = 0


@dataclass(frozen=True, slots=True)
class MathOn:
    """
    The start of an inline math formula (§147).

    `width` is the `\\mathsurround` space put either side of the formula. The
    node is discardable and a break is *not* legal here -- only at the matching
    `MathOff`, and then only when glue follows.
    """

    width: Scaled = 0


@dataclass(frozen=True, slots=True)
class MathOff:
    """
    The end of an inline math formula (§147). See `MathOn`.
    """

    width: Scaled = 0


Node: TypeAlias = CharNode | Box | Rule | Glue | Kern | Penalty | Disc | MathOn | MathOff
"""
Anything that can appear in a horizontal or vertical list.

A union of frozen dataclasses rather than a base class, so that `match` over it
plus `assert_never` in the default arm turns a forgotten variant into a type
error at a named line instead of a silently skipped node.
"""

_DISCARDABLE: Final = (MathOn, MathOff, Glue, Kern, Penalty)
"""
The discardable node types, in the source's partition (§148).

§148 defines `non_discardable(p) == (type(p) < math_node)`, and TeX's node type
codes are *ordered* to make that a single comparison. We have an unordered union
instead, so the partition is written out here.

§148 spells `precedes_break` with the same comparison, but the two are not
interchangeable at the one call site that matters: §868 tests `precedes_break`
as the *second* of three branches, and the third admits a kern that this tuple
calls discardable. Use `permits_break_at_following_glue` for that question and
this predicate only for §879's pruning after a chosen break.
"""

_PRECEDES_BREAK: Final = (CharNode, Box, Rule, Disc)
"""
The node types §868 accepts before a glue breakpoint without consulting subtype.

Folds its first two branches together: `is_char_node(prev_p)` gives `CharNode`,
and `precedes_break(prev_p)` -- `type(p) < math_node` -- gives `Box`, `Rule` and
`Disc` out of the types this project keeps. The kern branch is separate because
it reads a subtype.
"""


def is_discardable(node: Node) -> bool:
    """
    Whether this node is dropped when it follows a chosen breakpoint (§148, §879).

    This answers one question only: what §879 prunes from the start of the next
    line, which is what stops a line from beginning with the space that ended the
    previous one. It is *not* the breakpoint rule -- see
    `permits_break_at_following_glue`, which admits a node this returns `True`
    for.
    """
    return isinstance(node, _DISCARDABLE)


def permits_break_at_following_glue(node: Node) -> bool:
    """
    Whether a glue node immediately after `node` is a legal breakpoint (§868).

    §868 has three branches, and all three call `try_break(0, unhyphenated)`:

    1. `is_char_node(prev_p)` -- the glue follows a character.
    2. `precedes_break(prev_p)`, i.e. `type(prev_p) < math_node` -- here `Box`,
       `Rule` and `Disc`.
    3. `(type(prev_p) = kern_node) and (subtype(prev_p) <> explicit)` -- a font
       kern or a math kern. A kern is discardable, so this branch is exactly
       what makes the rule wider than `not is_discardable(node)`.

    Dropping the third branch is not academic. `imscribe.fontlib` extracts real
    pair kerns from `GPOS` and math spacing emits kerns, so a line breaker built
    on the narrower rule refuses to break at the space after every kerned pair
    and after every formula-adjacent kern. The symptom is "this paragraph breaks
    oddly around formulas and after certain letter pairs", which reads as a
    line-breaker bug and is a missing predicate branch.

    `MathOn`/`MathOff` are excluded deliberately: a math node has
    `type = math_node`, so it fails all three branches. The break a math node
    offers is taken *at* the node by §866's `kern_break`, and only when its
    subtype is `after` (correction C1 in `docs/tex-notes.md`).

    §868 wraps all three branches in `if auto_breaking then`. `auto_breaking` is
    a running flag the line breaker carries -- it goes false at a `before` math
    node and true again at an `after` one -- and not a property of any single
    node, so the caller owns it and this predicate does not see it.
    """
    if isinstance(node, Kern):
        return node.kind is not KernKind.EXPLICIT
    return isinstance(node, _PRECEDES_BREAK)

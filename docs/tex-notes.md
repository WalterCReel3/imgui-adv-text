# TeX layout algorithms — implementation reference

> **2026-10-12:** the package this document calls `advtext` was renamed `imscribe` (`advtext/…` is `imscribe/…`, `import advtext` is `import imscribe`). Nothing below was changed for it.

Source: `/home/wreel/Downloads/tex.web` (Knuth, TeX82, WEB format, 25010 lines).

All section numbers (`§n`) below are WEB section numbers, computed by counting `@*` / `@ ` /
bare `@` section starts from the top of the file. Spot-checked: §108 = `badness`,
§749/§750 = `make_op`, §851 = demerits part of `try_break` — these match the published
*TeX: The Program* numbering.

Anything I could not find in the file is marked **NOT FOUND in tex.web search**.
Anything that is my own engineering suggestion rather than a transcription is marked
**[my proposal, not in tex.web]**.

Units: all dimensions are `scaled` = 32-bit integer in units of $2^{-16}$ pt (`@d unity == @'200000`,
i.e. 65536, §101). `@d max_dimen == @'7777777777` = $2^{30}-1$ (§247 area, line 8495).
`half(x)` rounds odd numbers up: `if odd(x) then half:=(x+1) div 2 else half:=x div 2` (§100).

---

# CORRECTIONS — read this before implementing from any section below

This document was audited line by line against `tex.web` after it was written. **The audit
found the transcriptions exact**, including the ones most likely to be garbled: §3's badness
constants, §7's 64-character spacing string (byte-identical), §8's one-step `make_op`
successor chain, §4's `b>12`/`b>99` thresholds and §859 demerits, §6's `append_to_vlist`,
and §2.5's unusual accumulate-and-difference glue rounding. Those can be implemented as
written.

Five things below are **wrong or misleading** and are corrected here. The body text has not
been rewritten, so where the body and this section disagree, **this section wins**.

### C1. §5.7 — a `before` math node is NEVER a legal breakpoint

The §5.7 summary table row "math node (`before` or `after`) followed by glue | yes | 0" is
wrong. §866 (tex.web 17061-17064, 17084-17085) assigns `auto_breaking:=(subtype(cur_p)=after)`
**before** `kern_break` expands, and `kern_break`'s guard is `and auto_breaking`. With
`before=0`/`after=1`:

- math node subtype `after`, followed by glue → legal break, penalty 0.
- math node subtype `before` → **never** a break.

§5.4's prose has this right; only the lookup table is wrong, and the table is what gets copied.

### C2. §6.1 — a rule in vertical mode DOES set `prev_depth`, and this hits the markdown `---`

§6.1's claim that rules "do not update `prev_depth`" is wrong. tex.web 20515-20522:

```
vmode+hrule,hmode+vrule,mmode+vrule: begin tail_append(scan_rule_spec);
  if abs(mode)=vmode then prev_depth:=ignore_depth
```

A rule sets `prev_depth := ignore_depth` (−65536000 sp = −1000pt exactly), which makes
`append_to_vlist`'s `prev_depth > ignore_depth` guard fail for the *next* box. **A rule
therefore suppresses interline glue on both sides of itself**, and the document is expected
to supply explicit vertical skips around it.

This is not academic: it is the `---` thematic break between two paragraphs, named in
`docs/decisions.md` as part of litmus test 1. Implementing §6.1 as written gives every rule a
full `\baselineskip`-derived gap below it that TeX does not emit, the rule sits too close to
the paragraph above and too far from the one below, and it reads as "my rules have
inconsistent spacing" rather than as a bug.

**Whoever assembles vertical lists needs an explicit `prev_depth = IGNORE_DEPTH` on rule
append, and a test pinning "no interline glue is emitted after a rule".**

### C3. §2.5 — `round()` in the restated pseudocode is Pascal's, not Python's

The §625/§634 transcription is exact. The *restatement* `cur_g = round(clamp(...))` is a trap:
Pascal's `round` is half-away-from-zero, Python's builtin is half-to-even. They disagree on
every exact `.5`, and `glue_set * cur_glue` lands on exact halves routinely because `glue_set`
is a ratio of integers and `cur_glue` is an integer sum of scaled points.

`round(2.5)` is 3 in TeX and 2 in Python; `round(-0.5)` is −1 in TeX and 0 in Python. Because
the algorithm takes *differences* of successive rounded values, a 1sp divergence at glue node
k shifts everything from k onward.

Write an explicit helper — `floor(x + 0.5)` for x ≥ 0, `ceil(x - 0.5)` for x < 0 — document it
as "Pascal `round`, half away from zero, per §625", and pin it with a test at an exact half.

**Do not reach for `advtext.units.round_to_px` for this.** That is a different rounding
(sp→device pixels, once, on a final absolute coordinate) and it uses Python's `round`. The
§625 rounding is sp→sp inside the layout core.

Related, lower stakes: `x_over_n` (tex.web 2274-2290) truncates toward zero for negative `x`,
whereas Python `//` and `%` floor. Only bites for negative arguments; `cur_mu` is positive in
practice.

### C4. §3 — the reachable range of `badness` is not `[0, 10000]`

True as an interval, misleading as a spec. The largest *finite* value the function can return
is **8189**, at `r = 1290`. Everything from 8190 to 9999 is unreachable, so the reachable set
is `{0..8189} ∪ {10000}`. Knuth's "any badness of 2^13 or more is treated as infinitely bad"
is an approximation — the real cutover is above 8189, not at 8192.

A test asserting a value in the 8190-9999 band, or named for saturation "at 8192", will fail
against a *correct* implementation and look like the implementation is wrong.

### C5. Two blocks presented as verbatim are abridged

- **§7.5 `math_glue` (§716)** drops the negative-fraction correction that follows
  `n:=x_over_n(m,@'200000); f:=remainder;` — namely `if f<0 then begin decr(n);
  f:=f+@'200000; end` (tex.web 14102-14107). Dead code for us, since `cur_mu` is positive.
- **§2.3's "Key facts" bullet** overstates the overfull clamp. The code block above it is
  correct; the bullet drops the guard. tex.web 13112-13114 requires **three** conditions
  together: `(total_shrink[o] < -x)` **and** `(o = normal)` **and** `(list_ptr(r) <> null)`.
  An overfull box whose winning shrink order is infinite keeps its computed ratio, and an
  empty box is left alone.

### Known-unreliable: the section *numbers* themselves

The auditor verified **content at each citation**, not that a given hit is section *n*. The
WEB numbering was computed by counting section starts and was only spot-checked. So "§679"
means "this text is in tex.web and says what the notes say it says" — if a number is off by
one, the code is still right and only the cross-reference is wrong. One known inconsistency:
`max_dimen` is cited as "§247 area" here and as §421 in `advtext/units.py`; both point at
tex.web line 8495, so one is wrong and neither is load-bearing.

---

## 1. The node / box model

`type` and `subtype` live in the first word of every non-char node (§133):

```
@d type(#)    == mem[#].hh.b0
@d subtype(#) == mem[#].hh.b1
```

### 1.1 Type codes (§134–§159)

| code | name | §  | notes |
|---|---|---|---|
| — | `char_node` | §134 | 1 word; identified by address: `@d is_char_node(#) == (#>=hi_mem_min)`. `@d font == type`, `@d character == subtype`. hlists only. |
| 0 | `hlist_node` | §135 | 7 words |
| 1 | `vlist_node` | §137 | same layout as hlist |
| 2 | `rule_node` | §138 | 4 words |
| 3 | `ins_node` | §140 | 5 words |
| 4 | `mark_node` | §141 | 2 words |
| 5 | `adjust_node` | §142 | 2 words, hlists only (`\vadjust`) |
| 6 | `ligature_node` | §143 | 2 words, hlists only |
| 7 | `disc_node` | §145 | 2 words, hlists only |
| 8 | `whatsit_node` | §146 | ≥2 words |
| 9 | `math_node` | §147 | 2 words, hlists only |
| 10 | `glue_node` | §149 | 2 words |
| 11 | `kern_node` | §155 | 2 words |
| 12 | `penalty_node` | §157 | 2 words |
| 13 | `unset_node` | §159 | alignment scratch |
| 14 | `style_node` | §688 | math only |
| 15 | `choice_node` | §688/§689 | math only |
| 16.. | noads | §682 | `ord_noad = unset_node+3 = 16`, etc. |

### 1.2 Box node layout (§135)

```
@d hlist_node=0            {|type| of hlist nodes}
@d box_node_size=7         {number of words to allocate for a box node}
@d width_offset=1          {position of |width| field in a box node}
@d depth_offset=2          {position of |depth| field in a box node}
@d height_offset=3         {position of |height| field in a box node}
@d width(#)  == mem[#+width_offset].sc  {width of the box, in sp}
@d depth(#)  == mem[#+depth_offset].sc  {depth of the box, in sp}
@d height(#) == mem[#+height_offset].sc {height of the box, in sp}
@d shift_amount(#) == mem[#+4].sc  {repositioning distance, in sp}
@d list_offset=5
@d list_ptr(#)   == link(#+list_offset)
@d glue_order(#) == subtype(#+list_offset) {applicable order of infinity}
@d glue_sign(#)  == type(#+list_offset)    {stretching or shrinking}
@d normal=0
@d stretching = 1
@d shrinking  = 2
@d glue_offset = 6
@d glue_set(#) == mem[#+glue_offset].gr   {a word of type |glue_ratio|}
```

`glue_ratio = real` (§7/§109, line 2373) — a float, *not* a scaled integer.

`shift_amount` semantics (§135, verbatim): "a scaled integer indicating how much this box
should be lowered (if it appears in a horizontal list), or how much it should be moved to
the right (if it appears in a vertical list)."

`new_null_box` (§136) zeroes width/depth/height/shift_amount, `list_ptr:=null`,
`glue_sign:=normal`, `glue_order:=normal`, `glue_set:=0.0`.

### 1.3 **height vs. depth relative to the baseline**

TeX's box reference point is *on the baseline at the left edge*. `height` extends **upward**
from the reference point; `depth` extends **downward**. The DVI coordinate system has
`v` increasing downward (`down1 157 a[1]. Set v:=v+a, i.e., move down a units`, §586 area,
line 11534), so:

- top edge of a box at baseline `v` is `v - height`
- bottom edge is `v + depth`

The code that proves this:

- `ship_out` (§640): `cur_v := height(p)+v_offset;` — the page box is placed so its
  *top* is at `v_offset`, i.e. `cur_v` is set to the baseline.
- `vlist_out` (§629): `cur_v := cur_v - height(this_box); top_edge := cur_v;` — on entry
  `cur_v` is the box's baseline; subtracting height gives the top edge.
- `vlist_out`, "Output a box in a vlist" (§632):
  ```
  if list_ptr(p)=null then cur_v:=cur_v+height(p)+depth(p)
  else begin cur_v:=cur_v+height(p); synch_v;     {advance to this box's baseline}
    ...
    cur_v:=save_v+depth(p); cur_h:=left_edge;     {advance past its depth}
    end
  ```
- `hlist_out`, "Output a box in an hlist" (§623):
  `cur_v := base_line + shift_amount(p);` — positive shift lowers the box.

`hpack` accumulation (§653): a box `p` in an hlist contributes
```
x:=x+width(p);
if type(p)>=rule_node then s:=0 else s:=shift_amount(p);
if height(p)-s>h then h:=height(p)-s;
if depth(p)+s>d then d:=depth(p)+s;
```
i.e. shifting a box *down* by `s` reduces its contribution to the enclosing height and
increases its contribution to the enclosing depth. That is the only place the sign
convention matters, and it is unambiguous: **+shift = down**.

`vpack` accumulation (§670): `x:=x+d+height(p); d:=depth(p);` — heights and depths chain,
and the running `d` is the depth of the *last* item, which becomes the box's depth.

### 1.4 rule_node (§138)

Has `width`, `depth`, `height` at the same offsets. `rule_node_size=4`.
```
@d null_flag == -@'10000000000  {$-2^{30}$, signifies a missing item}
@d is_running(#) == (#=null_flag)
```
`new_rule` (§139) sets all three to `null_flag`. A "running" dimension is resolved at
ship-out against the enclosing box (§624: `if is_running(rule_ht) then rule_ht:=height(this_box)`).
"The `width` is never running in an hlist; the `height` and `depth` are never running in a vlist."
Rendering: `rule_ht := rule_ht + rule_dp;` — the DVI rule primitive takes a *thickness*,
and the rule's reference point is at its bottom-left (§624: `cur_v := base_line + rule_dp`).

### 1.5 ligature_node (§143)

```
@d ligature_node=6
@d lig_char(#) == #+1       {the word where the ligature is to be found}
@d lig_ptr(#)  == link(lig_char(#))  {the list of original characters}
```
`lig_char(p)` has `font`/`character` fields exactly like a char_node. `subtype` is
`0 + 2 (implicit left boundary) + 1 (implicit right boundary)`. In `hpack` (§652) a ligature
node is handled by copying `mem[lig_char(p)]` into a scratch word `lig_trick` and
re-dispatching as a char_node.

### 1.6 disc_node (§145)

```
@d disc_node=7
@d replace_count == subtype  {how many subsequent nodes to replace}
@d pre_break  == llink
@d post_break == rlink
```
"All three of the discretionary texts must be lists that consist entirely of character,
kern, box, rule, and ligature nodes." If `pre_break(p)=null`, `ex_hyphen_penalty` is
charged; otherwise `hyphen_penalty`.

### 1.7 math_node (§147)

```
@d math_node=9
@d before=0   @d after=1
```
`width` = the `\mathsurround` space. `new_math(w,s)`.

### 1.8 glue_node (§149) and kern_node (§155), penalty_node (§157)

```
@d glue_node=10
@d cond_math_glue=98   {\nonscript}
@d mu_glue=99
@d a_leaders=100  @d c_leaders=101  @d x_leaders=102
@d glue_ptr   == llink
@d leader_ptr == rlink
```
`subtype` of parametric glue = parameter number + 1.

```
@d kern_node=11
@d explicit=1   {subtype of kerns from \kern and \/}
@d acc_kern=2   {subtype of kerns from accents}
```
(`normal=0` for font/math kerns; `mu_glue=99` for `\mkern`.)

```
@d penalty_node=12
@d inf_penalty=inf_bad            {= 10000}
@d eject_penalty=-inf_penalty     {= -10000}
@d penalty(#) == mem[#+1].int
```

### 1.9 The discardability ordering (§148) — load-bearing

```
@d precedes_break(#)  == (type(#)<math_node)
@d non_discardable(#) == (type(#)<math_node)
```
i.e. types 0..8 (hlist, vlist, rule, ins, mark, adjust, ligature, disc, whatsit) are
non-discardable; types ≥ 9 (math, glue, kern, penalty) are discarded after a break.
This is *why* the type codes are in that order — §148 says so explicitly. If you renumber
node types in a reimplementation, keep this partition.

---

## 2. Glue

### 2.1 glue_spec (§150)

```
@d glue_spec_size=4
@d glue_ref_count(#) == link(#)
@d stretch(#) == mem[#+2].sc
@d shrink(#)  == mem[#+3].sc
@d stretch_order == type      {order of infinity for stretching}
@d shrink_order  == subtype
@d fil=1    {first-order infinity}
@d fill=2   {second-order infinity}
@d filll=3  {third-order infinity}
```
(`width(#)` at offset 1, shared with the box macro.) `normal = 0` is the finite order.
Types: `@!glue_ord = normal..filll`.

### 2.2 The "highest order wins" rule (§646)

Verbatim: "To figure out the glue setting, `hpack` and `vpack` determine how much
stretchability and shrinkability are present, considering all four orders of infinity.
The highest order of infinity that has a nonzero coefficient is then used as if no other
orders were present."

Worked example from §646: stretches 3pt, 8fill, 5fil, 6pt, −3fil, −8fill total to
"essentially 2fil"; to make up 6pt the actual stretches are 0pt, 0pt, 15pt, 0pt, −9pt, 0pt.

Accumulators (§646):
```
@!total_stretch, @!total_shrink: array[glue_ord] of scaled;
@!last_badness:integer;
```

### 2.3 `hpack` (§649–§667)

Signature: `function hpack(p:pointer; w:scaled; m:small_number):pointer;`
with `@d exactly=0`, `@d additional=1`, `@d natural == 0,additional` (§644).

Accumulation of glue (§656):
```
begin g:=glue_ptr(p); x:=x+width(g);
o:=stretch_order(g); total_stretch[o]:=total_stretch[o]+stretch(g);
o:=shrink_order(g);  total_shrink[o] :=total_shrink[o] +shrink(g);
if subtype(p)>=a_leaders then
  begin g:=leader_ptr(p);
  if height(g)>h then h:=height(g);
  if depth(g)>d then d:=depth(g);
  end;
end
```
Characters (§654): `x := x + char_width`, `h := max(h, char_height)`, `d := max(d, char_depth)`.
Kern and math nodes (§651): `x := x + width(p)` (no effect on h/d).

The decision (§657):
```
if m=additional then w:=x+w;
width(r):=w; x:=w-x;   {now |x| is the excess to be made up}
if x=0 then
  begin glue_sign(r):=normal; glue_order(r):=normal;
  set_glue_ratio_zero(glue_set(r));
  return;
  end
else if x>0 then <Determine horizontal glue stretch setting...>
else <Determine horizontal glue shrink setting...>
```

Stretch branch (§658 + §659):
```
<Determine the stretch order>:
if total_stretch[filll]<>0 then o:=filll
else if total_stretch[fill]<>0 then o:=fill
else if total_stretch[fil]<>0 then o:=fil
else o:=normal

glue_order(r):=o; glue_sign(r):=stretching;
if total_stretch[o]<>0 then glue_set(r):=unfloat(x/total_stretch[o])
else begin glue_sign(r):=normal;
  set_glue_ratio_zero(glue_set(r)); {there's nothing to stretch}
  end;
if o=normal then if list_ptr(r)<>null then
  <Report an underfull hbox and goto common_ending, if this box is sufficiently bad>;
return;
```

Underfull/Loose report (§660):
```
last_badness:=badness(x,total_stretch[normal]);
if last_badness>hbadness then
  begin print_ln;
  if last_badness>100 then print_nl("Underfull") else print_nl("Loose");
  print(" \hbox (badness "); print_int(last_badness);
  goto common_ending;
  end;
```
So: **badness > 100 ⇒ "Underfull"; 1..100 ⇒ "Loose"**; reported only when > `\hbadness`,
and only when the applicable order is `normal` and the box is non-empty.

Shrink branch (§664 + §665 + §666 + §667):
```
<Determine the shrink order>  {same cascade on total_shrink}
glue_order(r):=o; glue_sign(r):=shrinking;
if total_shrink[o]<>0 then glue_set(r):=unfloat((-x)/total_shrink[o])
else begin glue_sign(r):=normal; set_glue_ratio_zero(glue_set(r)); end;
if (total_shrink[o]<-x)and(o=normal)and(list_ptr(r)<>null) then
  begin last_badness:=1000000;
  set_glue_ratio_one(glue_set(r));   {use the maximum shrinkage}
  <Report an overfull hbox ...>
  end
else if o=normal then if list_ptr(r)<>null then
  <Report a tight hbox ...>;
return;
```
Overfull test (§666):
```
if (-x-total_shrink[normal]>hfuzz)or(hbadness<100) then
  begin if (overfull_rule>0)and(-x-total_shrink[normal]>hfuzz) then
    <append a rule of width overfull_rule>;
  print_ln; print_nl("Overfull \hbox (");
  print_scaled(-x-total_shrink[normal]); print("pt too wide");
  goto common_ending;
  end
```
Tight test (§667): `last_badness:=badness(-x,total_shrink[normal]); if last_badness>hbadness then ... "Tight \hbox (badness ...`

**Key facts for a reimplementation:**
- On overfull, `glue_set` is clamped to exactly `1.0` and `last_badness := 1000000`.
  Overflow is *not* distributed; the box just sticks out.
- `glue_set` is only meaningful together with `glue_sign` and `glue_order`.
- When there is nothing to stretch/shrink at the winning order, `glue_sign` reverts to
  `normal` and `glue_set` to 0 — the content simply won't fill the box.

### 2.4 `vpack` / `vpackage` (§668–§678)

```
@d vpack(#) == vpackage(#,max_dimen)   {special case of unconstrained depth}
function vpackage(p:pointer; h:scaled; m:small_number; l:scaled):pointer;
```
`l` is the maximum allowed depth. Body (§668):
```
w:=0; <Clear dimensions to zero>;
while p<>null do <Examine node p in the vlist ...>;
width(r):=w;
if d>l then begin x:=x+d-l; depth(r):=l; end
else depth(r):=d;
<Determine the value of height(r) and the appropriate glue setting; ...>
```
Note the depth clamp: excess depth is *converted into height*, i.e. the reference point
moves down.

Accumulation (§669–§671):
```
box/rule/unset (§670):  x:=x+d+height(p); d:=depth(p);
                        if type(p)>=rule_node then s:=0 else s:=shift_amount(p);
                        if width(p)+s>w then w:=width(p)+s;
glue (§671):            x:=x+d; d:=0;
                        g:=glue_ptr(p); x:=x+width(g);
                        o:=stretch_order(g); total_stretch[o]+=stretch(g);
                        o:=shrink_order(g);  total_shrink[o] +=shrink(g);
                        if subtype(p)>=a_leaders then
                          begin g:=leader_ptr(p); if width(g)>w then w:=width(g); end;
kern (§669):            x:=x+d+width(p); d:=0;
char node:              confusion("vpack")   {illegal}
```

Decision (§672) is identical in shape to §657 with `h`/`x` in place of `w`/`x`.
Stretch (§673) / underfull (§674) / shrink (§676) / overfull (§677) / tight (§678) are
character-for-character the horizontal versions with `vbadness` and `vfuzz` substituted
and messages `"Underfull \vbox"`, `"pt too high"`, `"Tight \vbox"`.

### 2.5 Rendering set glue at ship-out (§625 for hlists, §634 for vlists)

This is the part people get wrong. TeX does **not** compute each glue node's width
independently; it accumulates the *total* natural stretch/shrink seen so far, multiplies
once, rounds once, and takes a difference. This keeps rounding error from accumulating
across a line.

```
@d billion == float_constant(1000000000)
@d vet_glue(#) == glue_temp:=#;
  if glue_temp>billion then glue_temp:=billion
  else if glue_temp<-billion then glue_temp:=-billion

<Move right or output leaders> =            {§625, inside hlist_out}
begin g:=glue_ptr(p); rule_wd:=width(g)-cur_g;
if g_sign<>normal then
  begin if g_sign=stretching then
    begin if stretch_order(g)=g_order then
      begin cur_glue:=cur_glue+stretch(g);
      vet_glue(float(glue_set(this_box))*cur_glue);
      cur_g:=round(glue_temp);
      end;
    end
  else if shrink_order(g)=g_order then
      begin cur_glue:=cur_glue-shrink(g);
      vet_glue(float(glue_set(this_box))*cur_glue);
      cur_g:=round(glue_temp);
      end;
  end;
rule_wd:=rule_wd+cur_g;
if subtype(p)>=a_leaders then <Output leaders ...>;
goto move_past;
end
```
Locals, declared in `hlist_out` (§619):
```
@!g_order: glue_ord;         {applicable order of infinity for glue}
@!g_sign: normal..shrinking;
@!glue_temp:real;            {glue value before rounding}
@!cur_glue:real;             {glue seen so far}
@!cur_g:scaled;              {rounded equivalent of |cur_glue| times the glue ratio}
```
initialised `cur_g:=0; cur_glue:=float_constant(0);` and
`g_order:=glue_order(this_box); g_sign:=glue_sign(this_box);`.
`move_past: cur_h:=cur_h+rule_wd;`.

The vertical version (§634) is identical with `rule_ht` for `rule_wd` and
`move_past: cur_v:=cur_v+rule_ht;` (§631).

**Restated as an algorithm:**
```
cur_glue = 0.0; cur_g = 0
for each glue node g in box.children:
    w = g.width - cur_g
    if box.glue_sign == STRETCH and g.stretch_order == box.glue_order:
        cur_glue += g.stretch
        cur_g = round(clamp(box.glue_set * cur_glue, -1e9, +1e9))
    elif box.glue_sign == SHRINK and g.shrink_order == box.glue_order:
        cur_glue -= g.shrink
        cur_g = round(clamp(box.glue_set * cur_glue, -1e9, +1e9))
    w += cur_g
    advance by w
```
Note the asymmetry: `cur_glue` *decreases* on shrink, and `glue_set` is stored as a
positive ratio in both cases (§664 stores `(-x)/total_shrink[o]`), so the product is
negative for shrink. Glue whose order does not match `box.glue_order` renders at exactly
its natural width.

---

## 3. Badness (§108)

Verbatim:

```
@d inf_bad = 10000 {infinitely bad value}

@p function badness(@!t,@!s:scaled):halfword; {compute badness, given |t>=0|}
var r:integer; {approximation to $\alpha t/s$, where $\alpha^3\approx 100\cdot2^{18}$}
begin if t=0 then badness:=0
else if s<=0 then badness:=inf_bad
else  begin if t<=7230584 then  r:=(t*297) div s {$297^3=99.94\times2^{18}$}
  else if s>=1663497 then r:=t div (s div 297)
  else r:=t;
  if r>1290 then badness:=inf_bad {$1290^3<2^{31}<1291^3$}
  else badness:=(r*r*r+@'400000) div @'1000000;
  end; {that was $r^3/2^{18}$, rounded to the nearest integer}
end;
```

Octal constants: `@'400000` = 131072 = $2^{17}$, `@'1000000` = 262144 = $2^{18}$.

So the final line is `badness := (r³ + 2¹⁷) div 2¹⁸` — i.e. `r³ / 2¹⁸` rounded to nearest.

Documentation from §108, verbatim:
- "the badness of this situation is $100(t/s)^3$; however, badness is simply a heuristic,
  so we need not squeeze out the last drop of accuracy when computing it."
- "It produces an integer value that is a reasonably close approximation to $100(t/s)^3$,
  and **all implementations of TeX should use precisely this method**."
- "Any badness of $2^{13}$ or more is treated as infinitely bad, and represented by 10000."
- "It is not difficult to prove that `badness(t+1,s) >= badness(t,s) >= badness(t,s+1)`."
- "The badness function defined here is capable of computing at most 1095 distinct values."

**Constants explained:**

| constant | meaning |
|---|---|
| `297` | $\alpha$ such that $\alpha^3 \approx 100\cdot 2^{18}$; $297^3 = 26198073 = 99.94 \times 2^{18}$ |
| `7230584` | largest `t` for which `t*297` cannot overflow 31 bits ($7230584 \times 297 = 2147483448 < 2^{31}$) |
| `1663497` | if `t` is too big to multiply, and `s >= 1663497`, use `t div (s div 297)`; below that threshold, the fallback is just `r := t` (which will exceed 1290 and yield `inf_bad`) |
| `1290` | $1290^3 < 2^{31} < 1291^3$; guards the `r*r*r` multiply |
| `@'400000` = $2^{17}$ | rounding addend |
| `@'1000000` = $2^{18}$ | divisor |
| `inf_bad` = 10000 | returned value for $r > 1290$, i.e. badness $\ge 2^{13}$ = 8192 |

**Range:** `badness` returns an integer in `[0, 10000]`. It is `halfword`-typed. It is
never greater than 10000 (§828 relies on this: "If `threshold` is 10000 or more, all legal
breaks are considered feasible, since the `badness` function specified above never returns
a value greater than 10000").

Callers that need to express "worse than infinitely bad" use separate sentinels:
- `@d awful_bad == @'7777777777` = $2^{30}-1$ (§833), "more than a billion demerits"
- `@d deplorable == 100000` (§974), "more than `inf_bad`, but less than `awful_bad`"
- `try_break` uses `inf_bad+1` = 10001 for a line that cannot shrink enough (§853)
- `hpack`/`vpack` set `last_badness := 1000000` on overfull (§664/§676)

Also: `@d inf_penalty = inf_bad` and `@d eject_penalty = -inf_penalty` (§157). Penalty and
badness share the 10000 magnitude.

---

## 4. Line breaking

Entry point: `procedure line_break(final_widow_penalty:integer)` (§815), callable only from
horizontal mode. Structure (§815):
```
pack_begin_line:=mode_line;
<Get ready to start line breaking>;
<Find optimal breakpoints>;
<Break the paragraph at the chosen breakpoints, justify ... and append them to the
 current vertical list>;
<Clean up the memory by removing the break nodes>;
pack_begin_line:=0;
```

### 4.1 Paragraph preamble (§816)

The list is moved from `head` to `temp_head`; then, verbatim:
```
if is_char_node(tail) then tail_append(new_penalty(inf_penalty))
else if type(tail)<>glue_node then tail_append(new_penalty(inf_penalty))
else begin type(tail):=penalty_node; delete_glue_ref(glue_ptr(tail));
  flush_node_list(leader_ptr(tail)); penalty(tail):=inf_penalty;
  end;
link(tail):=new_param_glue(par_fill_skip_code);
```
i.e. a trailing space is *replaced* by `\penalty10000`, then `\parfillskip` is appended.
The infinite penalty makes the `\parfillskip` glue never a legal breakpoint.

### 4.2 Background (§827)

```
no_shrink_error_yet:=true;
check_shrinkage(left_skip); check_shrinkage(right_skip);
q:=left_skip; r:=right_skip; background[1]:=width(q)+width(r);
background[2]:=0; background[3]:=0; background[4]:=0; background[5]:=0;
background[2+stretch_order(q)]:=stretch(q);
background[2+stretch_order(r)]:=background[2+stretch_order(r)]+stretch(r);
background[6]:=shrink(q)+shrink(r);
```
Index layout of the six-element width arrays (`background`, `active_width`,
`cur_active_width`, `break_width`): `[1]`=natural width, `[2]`=stretch order normal,
`[3]`=fil, `[4]`=fill, `[5]`=filll, `[6]`=shrink (finite only).

Infinite shrink in a paragraph is an error and is silently made finite (§825/§826,
`finite_shrink`): "that is why the algorithm maintains four registers for stretching but
only one for shrinking."

### 4.3 Fitness classes (§817)

```
@d tight_fit=3       {fitness classification for lines shrinking 0.5 to 1.0 of their shrinkability}
@d loose_fit=1       {fitness classification for lines stretching 0.5 to 1.0 of their stretchability}
@d very_loose_fit=0  {fitness classification for lines stretching more than their stretchability}
@d decent_fit=2      {fitness classification for all other lines}
```

Assignment for a **stretching** line (§852):
```
if (cur_active_width[3]<>0)or(cur_active_width[4]<>0)or(cur_active_width[5]<>0) then
  begin b:=0; fit_class:=decent_fit; {infinite stretch}
  end
else begin if shortfall>7230584 then if cur_active_width[2]<1663497 then
    begin b:=inf_bad; fit_class:=very_loose_fit; goto done1;
    end;
  b:=badness(shortfall,cur_active_width[2]);
  if b>12 then
    if b>99 then fit_class:=very_loose_fit
    else fit_class:=loose_fit
  else fit_class:=decent_fit;
  done1:
  end
```
Assignment for a **shrinking** line (§853):
```
begin if -shortfall>cur_active_width[6] then b:=inf_bad+1
else b:=badness(-shortfall,cur_active_width[6]);
if b>12 then fit_class:=tight_fit else fit_class:=decent_fit;
end
```
with `shortfall := line_width - cur_active_width[1]` (§851).

**Thresholds:** `b <= 12` ⇒ decent (both directions). `13..99` stretching ⇒ loose.
`>= 100` stretching ⇒ very loose. `b > 12` shrinking ⇒ tight. There is no "very tight":
shrink is bounded, and once `-shortfall > total shrink` the badness is `inf_bad+1` = 10001,
which forces deactivation.

(Note `b=12` corresponds to $100(t/s)^3 \approx 12$, i.e. $t/s \approx 0.5$; `b=100`
corresponds to $t/s = 1$. Hence the "0.5 to 1.0 of their stretchability" prose above.)

### 4.4 `try_break` (§829)

```
procedure try_break(pi:integer; break_type:small_number);
```
`pi` = penalty at `cur_p`; `pi = eject_penalty` if forced, `inf_penalty` if illegal.
`break_type` ∈ {`unhyphenated`=0, `hyphenated`=1} (§819).

Range clamp (§831):
```
if abs(pi)>=inf_penalty then
  if pi>0 then return          {this breakpoint is inhibited by infinite penalty}
  else pi:=eject_penalty       {this breakpoint will be forced}
```

Active node layout (§819):
```
@d active_node_size=3
@d fitness == subtype              {very_loose_fit..tight_fit on final line for this break}
@d break_node == rlink             {pointer to the corresponding passive node}
@d line_number == llink            {line that begins at this breakpoint}
@d total_demerits(#) == mem[#+2].int
@d unhyphenated=0
@d hyphenated=1
```

Feasibility gate (§851):
```
shortfall:=line_width-cur_active_width[1];
if shortfall>0 then <badness for stretching ...>
else <badness for shrinking ...>;
if (b>inf_bad)or(pi=eject_penalty) then
  <Prepare to deactivate node r, and goto deactivate unless there is a reason
   to consider lines of text from r to cur_p>
else begin prev_r:=r;
  if b>threshold then goto continue;
  node_r_stays_active:=true;
  end;
```

Emergency escape (§854) — the "last resort" that permits overfull boxes:
```
begin if final_pass and (minimum_demerits=awful_bad) and
   (link(r)=last_active) and (prev_r=active) then
  artificial_demerits:=true {set demerits zero, this break is forced}
else if b>threshold then goto deactivate;
node_r_stays_active:=false;
end
```

### 4.5 **The demerits formula** (§859) — verbatim

```
@ @<Compute the demerits, |d|, from |r| to |cur_p|@>=
begin d:=line_penalty+b;
if abs(d)>=10000 then d:=100000000 else d:=d*d;
if pi<>0 then
  if pi>0 then d:=d+pi*pi
  else if pi>eject_penalty then d:=d-pi*pi;
if (break_type=hyphenated)and(type(r)=hyphenated) then
  if cur_p<>null then d:=d+double_hyphen_demerits
  else d:=d+final_hyphen_demerits;
if abs(fit_class-fitness(r))>1 then d:=d+adj_demerits;
end
```

Read carefully:

1. `d := (line_penalty + b)²`, with **saturation at 10⁸** when `|line_penalty + b| >= 10000`.
   Not clamped — *replaced* by 100000000.
2. **Sign convention on the penalty term:**
   - `pi > 0` ⇒ `d += pi²` (penalizes)
   - `eject_penalty < pi < 0` ⇒ `d -= pi²` (rewards — a negative penalty *reduces* demerits
     by the square of its magnitude)
   - `pi == 0` ⇒ no term
   - `pi == eject_penalty` (−10000) ⇒ **no term at all**. A forced break contributes nothing.
     This is important: the `else if pi>eject_penalty` guard excludes exactly −10000.
     (Penalties < −10000 were already clamped to `eject_penalty` in §831.)
3. `double_hyphen_demerits` when this break *and* the previous break were both `hyphenated`
   and this is not the end of the paragraph; `final_hyphen_demerits` when `cur_p=null`
   (paragraph end) and the previous break was hyphenated. Note "the end of a paragraph is
   also regarded as `hyphenated`" (§829).
4. `adj_demerits` when the two adjacent lines' fitness classes differ by more than 1
   (e.g. tight(3) next to loose(1), or very_loose(0) next to decent(2)).

Accumulation (§855):
```
if artificial_demerits then d:=0 else <Compute the demerits, d, from r to cur_p>;
d:=d+total_demerits(r);
if d<=minimal_demerits[fit_class] then
  begin minimal_demerits[fit_class]:=d;
  best_place[fit_class]:=break_node(r); best_pl_line[fit_class]:=l;
  if d<minimum_demerits then minimum_demerits:=d;
  end
```
Note `<=`: later breaks with equal demerits win.

Pruning (§836):
```
if abs(adj_demerits)>=awful_bad-minimum_demerits then minimum_demerits:=awful_bad-1
else minimum_demerits:=minimum_demerits+abs(adj_demerits);
for fit_class:=very_loose_fit to tight_fit do
  begin if minimal_demerits[fit_class]<=minimum_demerits then
    <Insert a new active node from best_place[fit_class] to cur_p>;
  minimal_demerits[fit_class]:=awful_bad;
  end;
minimum_demerits:=awful_bad;
```
"It is not necessary to create new active nodes having `minimal_demerits` greater than
`minimum_demerits+abs(adj_demerits)`, since such active nodes will never be chosen."

### 4.6 The three passes (§863) — verbatim

```
@<Find optimal breakpoints@>=
threshold:=pretolerance;
if threshold>=0 then
  begin ... second_pass:=false; final_pass:=false;
  end
else begin threshold:=tolerance; second_pass:=true;
  final_pass:=(emergency_stretch<=0);
  end;
loop@+ begin if threshold>inf_bad then threshold:=inf_bad;
  if second_pass then <Initialize for hyphenating a paragraph>;
  <Create an active breakpoint representing the beginning of the paragraph>;
  cur_p:=link(temp_head); auto_breaking:=true;
  prev_p:=cur_p; {glue at beginning is not a legal breakpoint}
  while (cur_p<>null)and(link(active)<>last_active) do
    <Call try_break if cur_p is a legal breakpoint; on the second pass, also try to
     hyphenate the next word, if cur_p is a glue node; then advance cur_p ...>;
  if cur_p=null then
    <Try the final line break at the end of the paragraph, and goto done if the
     desired breakpoints have been found>;
  <Clean up the memory by removing the break nodes>;
  if not second_pass then
    begin threshold:=tolerance; second_pass:=true; final_pass:=(emergency_stretch<=0);
    end {if at first you don't succeed, \dots}
  else begin background[2]:=background[2]+emergency_stretch; final_pass:=true;
    end;
  end;
done:
```

So:
- **Pass 1**: `threshold = pretolerance`, no hyphenation. **Skipped entirely** if
  `pretolerance < 0`.
- **Pass 2**: `threshold = tolerance`, hyphenation enabled. `final_pass` is already true
  if `emergency_stretch <= 0` (so there is no third pass in that case).
- **Pass 3 ("emergency pass")**: `background[2] += emergency_stretch` — finite stretch is
  added to the *background*, which lowers every line's badness, plus `final_pass := true`
  which enables the `artificial_demerits` escape in §854.

`threshold` is clamped to `inf_bad` at the top of each pass.

Initial active node (§864):
```
q:=get_node(active_node_size);
type(q):=unhyphenated; fitness(q):=decent_fit;
link(q):=last_active; break_node(q):=null;
line_number(q):=prev_graf+1; total_demerits(q):=0; link(active):=q;
do_all_six(store_background);
```

Final break and looseness (§873, §874, §875):
```
begin try_break(eject_penalty,hyphenated);
if link(active)<>last_active then
  begin <Find an active node with fewest demerits>;
  if looseness=0 then goto done;
  <Find the best active node for the desired looseness>;
  if (actual_looseness=looseness)or final_pass then goto done;
  end;
end
```
`<Find an active node...>` (§874) scans the active list for minimum `total_demerits`,
setting `best_bet` and `best_line := line_number(best_bet)`. The looseness variant (§875)
prefers the active node whose `line_number - best_line` moves `actual_looseness` toward
`looseness`, tie-broken by demerits.

### 4.7 Parameter codes

Integer parameters (§236):
```
@d pretolerance_code=0            @d tolerance_code=1
@d line_penalty_code=2            @d hyphen_penalty_code=3
@d ex_hyphen_penalty_code=4       @d club_penalty_code=5
@d widow_penalty_code=6           @d broken_penalty_code=8
@d bin_op_penalty_code=9          @d rel_penalty_code=10
@d inter_line_penalty_code=13     @d double_hyphen_demerits_code=14
@d final_hyphen_demerits_code=15  @d adj_demerits_code=16
@d delimiter_factor_code=18       @d looseness_code=19
@d hbadness_code=26               @d vbadness_code=27
```
Dimension parameters (§247):
```
@d math_surround_code=1    @d line_skip_limit_code=2
@d max_depth_code=5        @d split_max_depth_code=6   @d box_max_depth_code=7
@d hfuzz_code=8            @d vfuzz_code=9
@d delimiter_shortfall_code=10  @d null_delimiter_space_code=11
@d script_space_code=12    @d emergency_stretch_code=20
```
Glue parameters (§224):
```
@d line_skip_code=0        @d baseline_skip_code=1     @d par_skip_code=2
@d top_skip_code=9         @d split_top_skip_code=10
@d thin_mu_skip_code=15    @d med_mu_skip_code=16      @d thick_mu_skip_code=17
```

**IniTeX defaults** (§240): every integer parameter is 0 except
```
mag:=1000; tolerance:=10000; hang_after:=1; max_dead_cycles:=25;
escape_char:="\"; end_line_char:=carriage_return;
```
So raw TeX has `pretolerance = 0` (pass 1 runs with threshold 0 — essentially only perfect
lines), `tolerance = 10000` (pass 2 accepts everything), and all demerits/penalties zero.
The familiar values (`\tolerance=200`, `\adjdemerits=10000`, `\linepenalty=10`,
`\doublehyphendemerits=10000`, `\finalhyphendemerits=5000`, `\hyphenpenalty=50`) come from
`plain.tex`, which is **NOT FOUND in tex.web search** — it is a separate file.

### 4.8 `\parshape` / `\hangindent` — line width for line *n* (§847–§850, §889)

§847, verbatim: "If `par_shape_ptr` is not null, it points to a $(2n+1)$-word record in
`mem`, where the `info` in the first word contains the value of `n`, and the other $2n$
words contain the left margins and line lengths for the first `n` lines of the paragraph;
the specifications for line `n` apply to all subsequent lines. If `par_shape_ptr=null`, the
shape of the paragraph depends on the value of `n=hang_after`; if `n>=0`, hanging
indentation takes place on lines `n+1`, `n+2`, …, otherwise it takes place on lines
1, …, |n|. When hanging indentation is active, the left margin is `hang_indent`, if
`hang_indent>=0`, else it is 0; the line length is `hsize - |hang_indent|`. The normal
setting is `par_shape_ptr=null`, `hang_after=1`, and `hang_indent=0`."

Setup (§848):
```
if par_shape_ptr=null then
  if hang_indent=0 then
    begin last_special_line:=0; second_width:=hsize; second_indent:=0;
    end
  else <Set line length parameters in preparation for hanging indentation>
else begin last_special_line:=info(par_shape_ptr)-1;
  second_width:=mem[par_shape_ptr+2*(last_special_line+1)].sc;
  second_indent:=mem[par_shape_ptr+2*last_special_line+1].sc;
  end;
if looseness=0 then easy_line:=last_special_line
else easy_line:=max_halfword
```
Hanging indentation (§849):
```
begin last_special_line:=abs(hang_after);
if hang_after<0 then
  begin first_width:=hsize-abs(hang_indent);
  if hang_indent>=0 then first_indent:=hang_indent else first_indent:=0;
  second_width:=hsize; second_indent:=0;
  end
else begin first_width:=hsize; first_indent:=0;
  second_width:=hsize-abs(hang_indent);
  if hang_indent>=0 then second_indent:=hang_indent else second_indent:=0;
  end;
end
```
Lookup during breaking (§850):
```
if l>easy_line then begin line_width:=second_width; old_l:=max_halfword-1; end
else begin old_l:=l;
  if l>last_special_line then line_width:=second_width
  else if par_shape_ptr=null then line_width:=first_width
  else line_width:=mem[par_shape_ptr+2*l].sc;
  end
```
Lookup at packaging time (§889):
```
if cur_line>last_special_line then
  begin cur_width:=second_width; cur_indent:=second_indent; end
else if par_shape_ptr=null then
  begin cur_width:=first_width; cur_indent:=first_indent; end
else begin cur_width :=mem[par_shape_ptr+2*cur_line].sc;
  cur_indent:=mem[par_shape_ptr+2*cur_line-1].sc;
  end;
adjust_tail:=adjust_head; just_box:=hpack(q,cur_width,exactly);
shift_amount(just_box):=cur_indent
```
So: **line `n` (1-based) gets width `parshape[2n]` and left margin `parshape[2n-1]`**;
for `n > last_special_line` it gets `second_width`/`second_indent`. The indent is applied
as the box's `shift_amount` in the enclosing vlist (= move right), not as glue.

`easy_line` is the optimisation that lets all sufficiently large line numbers be treated as
one equivalence class — disabled (set to `max_halfword`) when `\looseness ≠ 0`.

### 4.9 Line assembly (`post_line_break`, §876–§890)

Per line: append `\rightskip` at the end (§886: replacing the break glue if the break was
at glue), prepend `\leftskip` unless zero (§887), `hpack(q, cur_width, exactly)` (§889),
`append_to_vlist(just_box)` (§888), then penalties (§890):
```
if cur_line+1<>best_line then
  begin pen:=inter_line_penalty;
  if cur_line=prev_graf+1 then pen:=pen+club_penalty;
  if cur_line+2=best_line then pen:=pen+final_widow_penalty;
  if disc_break then pen:=pen+broken_penalty;
  if pen<>0 then begin r:=new_penalty(pen); link(tail):=r; tail:=r; end;
  end
```
The final line is never penalized. A two-line paragraph gets both club and widow penalties.

Pruning at the start of the next line (§879):
```
begin r:=temp_head;
loop@+ begin q:=link(r);
  if q=cur_break(cur_p) then goto done1;
  if is_char_node(q) then goto done1;
  if non_discardable(q) then goto done1;
  if type(q)=kern_node then if subtype(q)<>explicit then goto done1;
  r:=q; {now type(q)=glue_node, kern_node, math_node, or penalty_node}
  end;
done1: ...
```
i.e. **glue, penalty, math, and *explicit* kerns are discarded after a break; font kerns
are not.** This must match the `break_width` lookahead in `try_break` (§837, "Kern nodes do
not disappear at a line break unless they are `explicit`").

---

## 5. Breakpoint legality

### 5.1 The main switch (§866) — verbatim

```
@d act_width == active_width[1]
@d kern_break == begin if not is_char_node(link(cur_p)) and auto_breaking then
    if type(link(cur_p))=glue_node then try_break(0,unhyphenated);
  act_width:=act_width+width(cur_p);
  end

@<Call try_break if cur_p is a legal breakpoint...@>=
begin if is_char_node(cur_p) then <Advance cur_p to the node following the present
    string of characters>;
case type(cur_p) of
hlist_node,vlist_node,rule_node: act_width:=act_width+width(cur_p);
whatsit_node: <Advance past a whatsit node in the line_break loop>;
glue_node: begin <If node cur_p is a legal breakpoint, call try_break; then update the
  active widths by including the glue in glue_ptr(cur_p)>;
  if second_pass and auto_breaking then <Try to hyphenate the following word>;
  end;
kern_node: if subtype(cur_p)=explicit then kern_break
  else act_width:=act_width+width(cur_p);
ligature_node: begin f:=font(lig_char(cur_p));
  act_width:=act_width+char_width(f)(char_info(f)(character(lig_char(cur_p))));
  end;
disc_node: <Try to break after a discretionary fragment, then goto done5>;
math_node: begin auto_breaking:=(subtype(cur_p)=after); kern_break;
  end;
penalty_node: try_break(penalty(cur_p),unhyphenated);
mark_node,ins_node,adjust_node: do_nothing;
othercases confusion("paragraph")
endcases;
prev_p:=cur_p; cur_p:=link(cur_p);
done5:end
```

### 5.2 Break at glue (§868) — verbatim

```
if auto_breaking then
  begin if is_char_node(prev_p) then try_break(0,unhyphenated)
  else if precedes_break(prev_p) then try_break(0,unhyphenated)
  else if (type(prev_p)=kern_node)and(subtype(prev_p)<>explicit) then
    try_break(0,unhyphenated);
  end;
check_shrinkage(glue_ptr(cur_p)); q:=glue_ptr(cur_p);
act_width:=act_width+width(q);
active_width[2+stretch_order(q)]:=active_width[2+stretch_order(q)]+stretch(q);
active_width[6]:=active_width[6]+shrink(q)
```

The rule stated in prose (§862): "If `type(cur_p)=glue_node` then `cur_p` is a legal
breakpoint if and only if `auto_breaking` is true **and** `prev_p` does not point to a
glue node, penalty node, explicit kern node, or math node."

Equivalently: a break is allowed at glue iff the preceding item is a char node, or a
non-discardable node (`precedes_break`, types < `math_node`), or an implicit (font) kern.
The penalty for such a break is `0`.

`prev_p` is initialised to `cur_p` at the start (§863: `prev_p:=cur_p; {glue at beginning
is not a legal breakpoint}`).

### 5.3 Break at kern (§866)

Only `explicit` kerns (from `\kern` and `\/`) are breakpoints, and only when the *next*
node is a glue node:
```
@d kern_break == begin if not is_char_node(link(cur_p)) and auto_breaking then
    if type(link(cur_p))=glue_node then try_break(0,unhyphenated);
  act_width:=act_width+width(cur_p);
  end
```
Penalty 0. A font kern (`subtype = normal`) is never a breakpoint and just adds width.

### 5.4 Break at math-off (§866)

```
math_node: begin auto_breaking:=(subtype(cur_p)=after); kern_break; end;
```
The math node uses `kern_break` too, so a break is allowed at a math node iff it is
followed by glue. And `auto_breaking` is set to `true` only at the `after` node
(`@d before=0 @d after=1`, §147) — so **glue inside a formula is never a breakpoint**
(§862: "A variable called `auto_breaking` is set to true except within math formulas,
since glue nodes are not legal breakpoints when they appear in formulas").

### 5.5 Break at penalty (§866)

```
penalty_node: try_break(penalty(cur_p),unhyphenated);
```
Unconditional. `try_break` then rejects it if `penalty >= inf_penalty` and forces it if
`penalty <= eject_penalty` (§831).

### 5.6 Break at discretionary (§869) — verbatim

```
begin s:=pre_break(cur_p); disc_width:=0;
if s=null then try_break(ex_hyphen_penalty,hyphenated)
else begin repeat <Add the width of node s to disc_width>; s:=link(s);
  until s=null;
  act_width:=act_width+disc_width;
  try_break(hyphen_penalty,hyphenated);
  act_width:=act_width-disc_width;
  end;
r:=replace_count(cur_p); s:=link(cur_p);
while r>0 do
  begin <Add the width of node s to act_width>;
  decr(r); s:=link(s);
  end;
prev_p:=cur_p; cur_p:=s; goto done5;
end
```
So: an empty-pre-break discretionary (`\-` with no text, or `\discretionary{}{}{}`) is
charged `ex_hyphen_penalty`; one with pre-break text is charged `hyphen_penalty`. The
pre-break width is added to the running width *only for the duration of the `try_break`
call* — a break there ends the line with the pre-break material present; if not broken,
the `replace_count` following nodes are what contribute width instead.

Width accumulation for disc texts (§870/§871) handles only char nodes, ligature nodes,
hlist/vlist/rule/kern — anything else is `confusion("disc3")`/`confusion("disc4")`.

### 5.7 Summary table

| Position | Legal? | Penalty charged |
|---|---|---|
| glue, preceded by char / non-discardable node / implicit kern, outside math | yes | 0 |
| glue, preceded by glue / penalty / explicit kern / math node | **no** | — |
| glue inside `$...$` (`auto_breaking` false) | **no** | — |
| explicit kern followed by glue | yes | 0 |
| explicit kern not followed by glue | **no** | — |
| implicit (font) kern | **no** | — |
| math node (`before` or `after`) followed by glue | yes | 0 |
| penalty node | yes (unless ≥ 10000) | `penalty(p)` |
| disc node with non-empty `pre_break` | yes | `hyphen_penalty` |
| disc node with empty `pre_break` | yes | `ex_hyphen_penalty` |
| end of paragraph | forced | `eject_penalty`, `break_type=hyphenated` |

---

## 6. Page breaking / vertical lists

### 6.1 Interline glue — `append_to_vlist` (§679) — **verbatim, and this is the whole thing**

```
@ When a box is being appended to the current vertical list, the
baselineskip calculation is handled by the |append_to_vlist| routine.

@p procedure append_to_vlist(@!b:pointer);
var d:scaled; {deficiency of space between baselines}
@!p:pointer; {a new glue node}
begin if prev_depth>ignore_depth then
  begin d:=width(baseline_skip)-prev_depth-height(b);
  if d<line_skip_limit then p:=new_param_glue(line_skip_code)
  else  begin p:=new_skip_param(baseline_skip_code);
    width(temp_ptr):=d; {|temp_ptr=glue_ptr(p)|}
    end;
  link(tail):=p; tail:=p;
  end;
link(tail):=b; tail:=b; prev_depth:=depth(b);
end;
```

Supporting definitions:
- `@d ignore_depth == -65536000` (§212) — that is −1000 pt exactly (65536000 / 65536 = 1000).
  Set at the start of a vertical list / after `\nointerlineskip`-like conditions
  (e.g. §1025: `push_nest; mode:=-vmode; prev_depth:=ignore_depth;`).
- `@d prev_depth == aux.sc` (§212) — the vertical-mode auxiliary field.
- `@d line_skip_limit == dimen_par(line_skip_limit_code)` (`\lineskiplimit`, §247).
- `new_param_glue(line_skip_code)` shares the `\lineskip` spec (stretch/shrink included).
- `new_skip_param(baseline_skip_code)` makes a **fresh copy** of `\baselineskip` and
  overwrites only its `width`, preserving `\baselineskip`'s stretch and shrink components.

**Algorithm, restated:**
```
def append_box(vlist, b, prev_depth, baselineskip, lineskip, lineskiplimit):
    if prev_depth > IGNORE_DEPTH:            # -1000pt
        d = baselineskip.width - prev_depth - b.height
        if d < lineskiplimit:
            glue = copy_of(lineskip)         # full spec, as-is
        else:
            glue = copy_of(baselineskip)
            glue.width = d                   # stretch/shrink kept
        vlist.append(glue)
    vlist.append(b)
    prev_depth = b.depth
```
Interpretation: TeX tries to make the *baseline-to-baseline* distance equal to
`\baselineskip`. The glue it needs is `\baselineskip − (depth of previous box) − (height of
next box)`. If that number is smaller than `\lineskiplimit` (including negative — boxes
that would collide), it gives up on constant baselines and inserts `\lineskip` instead,
which guarantees a minimum *visual* gap between the previous box's bottom and the next
box's top.

**This only fires from `append_to_vlist`.** Glue, kerns, rules and penalties appended to a
vlist by other routes do *not* get interline glue, and they do not update `prev_depth`
(except boxes appended via `append_to_vlist`, and explicit `\prevdepth` assignments).
`prev_depth` is reset to `ignore_depth` at the start of an internal vertical list (§775,
§1025, §1070 area) so the first box never gets leading glue.

### 6.2 `prune_page_top` (§968, §969)

Removes all glue/kern/penalty nodes *before* the first box or rule, and inserts
`\splittopskip` glue sized so the topmost baseline sits `\splittopskip` from the top:
```
@<Insert glue for |split_top_skip|...@>=
begin q:=new_skip_param(split_top_skip_code); link(prev_p):=q; link(q):=p;
if width(temp_ptr)>height(p) then width(temp_ptr):=width(temp_ptr)-height(p)
else width(temp_ptr):=0;
p:=null;
end
```
Whatsit/mark/ins nodes are kept and skipped over.

### 6.3 `vert_break` (§970–§976) — the vsplit cost function

```
function vert_break(p:pointer; h,d:scaled):pointer;  {finds optimum page break}
@d active_height == active_width   {new name for the six distance variables}
@d cur_height == active_height[1]
```
State: `cur_height` (natural height so far), `prev_dp` (depth of previous box),
`least_cost`, `best_place`, `best_height_plus_depth`.

Legality of a break in a vlist (§973) — **same shape as horizontal, different details**:
```
case type(p) of
hlist_node,vlist_node,rule_node: begin
  cur_height:=cur_height+prev_dp+height(p); prev_dp:=depth(p);
  goto not_found;
  end;
whatsit_node: <Process whatsit p in vert_break loop, goto not_found>;
glue_node: if precedes_break(prev_p) then pi:=0
  else goto update_heights;
kern_node: begin if link(p)=null then t:=penalty_node
  else t:=type(link(p));
  if t=glue_node then pi:=0 else goto update_heights;
  end;
penalty_node: pi:=penalty(p);
mark_node,ins_node: goto not_found;
othercases confusion("vertbreak")
endcases
```
Note: **all** kerns (not just `explicit`) are legal breakpoints in a vlist provided the
next node is glue; and a kern at the very end of the list counts as followed by a
penalty node, i.e. not a breakpoint.

Depth clamping during the scan (§972):
```
not_found: if prev_dp>d then
    begin cur_height:=cur_height+prev_dp-d;
    prev_dp:=d;
    end;
```
"the maximum depth `d` might be negative, so `cur_height` and `prev_dp` might need to be
corrected even after a glue or kern node."

Badness (§975) — verbatim:
```
if cur_height<h then
  if (active_height[3]<>0) or (active_height[4]<>0) or (active_height[5]<>0) then b:=0
  else b:=badness(h-cur_height,active_height[2])
else if cur_height-h>active_height[6] then b:=awful_bad
else b:=badness(cur_height-h,active_height[6])
```

Cost (§974) — verbatim:
```
@d deplorable == 100000 {more than |inf_bad|, but less than |awful_bad|}

if pi<inf_penalty then
  begin <Compute the badness, b, using awful_bad if the box is too full>;
  if b<awful_bad then
    if pi<=eject_penalty then b:=pi
    else if b<inf_bad then b:=b+pi
      else b:=deplorable;
  if b<=least_cost then
    begin best_place:=p; least_cost:=b;
    best_height_plus_depth:=cur_height+prev_dp;
    end;
  if (b=awful_bad)or(pi<=eject_penalty) then goto done;
  end
```
Glue accumulation (§976): `active_height[2+stretch_order(q)] += stretch(q)`,
`active_height[6] += shrink(q)`; infinite shrink is an error and is made finite.
Then (§976, tail): `cur_height := cur_height + prev_dp + width(q); prev_dp := 0`.

### 6.4 `vsplit` (§977)

```
function vsplit(n:eight_bits; h:scaled):pointer;
begin v:=box(n);
... clear split_first_mark / split_bot_mark ...
<Dispense with trivial cases of void or bad boxes>;     {void -> null; hbox -> error}
q:=vert_break(list_ptr(v),h,split_max_depth);
<Look at all the marks in nodes before the break, and set the final link to null at the break>;
q:=prune_page_top(q); p:=list_ptr(v); free_node(v,box_node_size);
if q=null then box(n):=null
else box(n):=vpack(q,natural);
vsplit:=vpackage(p,h,exactly,split_max_depth);
exit: end;
```

### 6.5 The page builder (§980–§1007)

Page state (§982):
```
@d page_goal   == page_so_far[0]  {desired height of information on page being built}
@d page_total  == page_so_far[1]  {height of the current page}
@d page_shrink == page_so_far[6]  {shrinkability of the current page}
@d page_depth  == page_so_far[7]  {depth of the current page}
@!page_so_far: array [0..7] of scaled;
```
`page_so_far[2..5]` are the four stretch orders. Frozen at first box/insert (§987):
```
procedure freeze_page_specs(s:small_number);
begin page_contents:=s;
page_goal:=vsize; page_max_depth:=max_depth;
page_depth:=0; do_all_six(set_page_so_far_zero);
least_page_cost:=awful_bad;
...
```

Breakpoint legality on the page (§1000):
```
glue_node: if page_contents<box_there then goto done1
  else if precedes_break(page_tail) then pi:=0
  else goto update_heights;
kern_node: if page_contents<box_there then goto done1
  else if link(p)=null then return
  else if type(link(p))=glue_node then pi:=0
  else goto update_heights;
penalty_node: if page_contents<box_there then goto done1 else pi:=penalty(p);
```
`type(page_head) := glue_node` (§988) "so that an initial glue node on the current page
will not be considered a valid breakpoint."

`\topskip` insertion (§1001) — mirrors `prune_page_top`:
```
q:=new_skip_param(top_skip_code);
if width(temp_ptr)>height(p) then width(temp_ptr):=width(temp_ptr)-height(p)
else width(temp_ptr):=0;
link(q):=p; link(contrib_head):=q; goto continue;
```

Height accumulation:
```
box/rule (§1002):  page_total:=page_total+page_depth+height(p); page_depth:=depth(p);
glue/kern (§1004): ... page_total:=page_total+page_depth+width(q); page_depth:=0
depth clamp (§1003):
  if page_depth>page_max_depth then
    begin page_total:=page_total+page_depth-page_max_depth;
    page_depth:=page_max_depth;
    end;
```

Page badness (§1007) — verbatim:
```
if page_total<page_goal then
  if (page_so_far[3]<>0) or (page_so_far[4]<>0) or (page_so_far[5]<>0) then b:=0
  else b:=badness(page_goal-page_total,page_so_far[2])
else if page_total-page_goal>page_shrink then b:=awful_bad
else b:=badness(page_total-page_goal,page_shrink)
```

Page cost (§1005) — verbatim:
```
if pi<inf_penalty then
  begin <Compute the badness, b, of the current page, using awful_bad if the box is too full>;
  if b<awful_bad then
    if pi<=eject_penalty then c:=pi
    else if b<inf_bad then c:=b+pi+insert_penalties
      else c:=deplorable
  else c:=b;
  if insert_penalties>=10000 then c:=awful_bad;
  if c<=least_page_cost then
    begin best_page_break:=p; best_size:=page_goal;
    least_page_cost:=c;
    ... record best_ins_ptr for each insertion class ...
    end;
  if (c=awful_bad)or(pi<=eject_penalty) then
    begin fire_up(p);   {output the current page at the best place}
    if output_active then return;
    goto done;
    end;
  end
```

**Difference from `vert_break`:** the page builder's cost adds `insert_penalties`, and
forces `c := awful_bad` if `insert_penalties >= 10000`. Otherwise the shape is identical:

```
c = pi                            if b < awful_bad and pi <= -10000    (forced break)
c = b + pi + insert_penalties     if b < awful_bad and b < inf_bad
c = deplorable (100000)           if b < awful_bad and b >= inf_bad
c = awful_bad                     if b == awful_bad  (page cannot shrink enough)
```
and the page is fired up as soon as `c == awful_bad` or `pi <= eject_penalty`.
Ties go to the *later* break (`c <= least_page_cost`).

`\vbadness` (§247, `vbadness_code=27`) does **not** participate in the cost function at
all — it only controls diagnostic reporting in `vpack` (§674, §677, §678). The page
builder's quality is governed purely by `badness(page_goal − page_total, page_stretch)`
compared across candidate breaks.

Tracing hook (§1006) prints `% t=<totals> g=<goal> b=<badness> p=<penalty> c=<cost>` with
`#` marking a new champion — extremely useful to replicate when debugging a port.

---

## 7. Math typesetting (`mlist_to_hlist`)

### 7.1 Noad structure (§681)

```
@d noad_size=4
@d nucleus(#) == #+1
@d supscr(#)  == #+2
@d subscr(#)  == #+3
@d math_type == link           {a halfword in mem}
@d fam       == font           {a quarterword in mem}
@d math_char=1      {simple: fam + character}
@d sub_box=2        {info(q) points to a box; its shift_amount is a downward shift}
@d sub_mlist=3      {info(q) points to an mlist}
@d math_text_char=4 {italic correction is dubious}
{ math_type = empty (=0) means the field is absent }
```

### 7.2 Atom types (§682, §683, §687)

```
@d ord_noad   = unset_node+3   {= 16}
@d op_noad    = ord_noad+1     {17}
@d bin_noad   = ord_noad+2     {18}
@d rel_noad   = ord_noad+3     {19}
@d open_noad  = ord_noad+4     {20}
@d close_noad = ord_noad+5     {21}
@d punct_noad = ord_noad+6     {22}
@d inner_noad = ord_noad+7     {23}
@d limits=1     {subtype of op_noad whose scripts are to be above, below}
@d no_limits=2  {subtype of op_noad whose scripts are to be normal}

@d radical_noad = inner_noad+1   {24}  @d radical_noad_size=5
@d fraction_noad = radical_noad+1 {25} @d fraction_noad_size=6
@d under_noad   = fraction_noad+1 {26}
@d over_noad    = under_noad+1    {27}
@d accent_noad  = over_noad+1     {28}  @d accent_noad_size=5  @d accent_chr(#)==#+4
@d vcenter_noad = accent_noad+1   {29}
@d left_noad    = vcenter_noad+1  {30}
@d right_noad   = left_noad+1     {31}
@d delimiter == nucleus
@d scripts_allowed(#) == (type(#)>=ord_noad)and(type(#)<left_noad)
```
Fraction noads reuse fields: `@d thickness == width`, `@d numerator == supscr`,
`@d denominator == subscr`, `@d default_code == @'10000000000` (= $2^{30}$, "denotes
`default_rule_thickness`"). Delimiter fields:
`@d left_delimiter(#)==#+4`, `@d right_delimiter(#)==#+5`, with subfields
`small_fam/.b0`, `small_char/.b1`, `large_fam/.b2`, `large_char/.b3` (§683).

**Note the ordering trap:** the eight *spacing* atom types Ord..Inner are contiguous
(16..23), and everything else (Over, Under, Vcent, Rad, Acc, Left, Right) maps into one of
those eight for spacing purposes during the second pass (§761 — see below). Over, Under,
Vcenter map to `ord_noad`; Radical maps to `ord_noad`; Accent maps to `ord_noad`; Left/Right
map to `open_noad`/`close_noad`.

### 7.3 Styles (§688)

```
@d style_node = unset_node+1   {= 14}      @d style_node_size=3
@d display_style=0
@d text_style=2
@d script_style=4
@d script_script_style=6
@d cramped=1   {add this to an uncramped style if you want to cramp it}
```
§688, verbatim: "TeX uses even numbers 0, 2, 4, 6 to encode the basic styles
`display_style`, …, `script_script_style`, and adds 1 to get the 'cramped' versions of
these styles. This gives a numerical order that is **backwards** from the convention of
Appendix G in *The TeXbook*; i.e., a smaller style has a larger numerical value."

So the eight style codes are: 0 D, 1 D′, 2 T, 3 T′, 4 S, 5 S′, 6 SS, 7 SS′.
Test `cur_style < text_style` means "display style (D or D′)".
Test `cur_style < script_style` means "display or text" (used for conditional math spacing).
Test `odd(cur_style)` means "cramped".

### 7.4 Style transitions (§702) — verbatim

```
@d cramped_style(#) == 2*(# div 2)+cramped              {cramp the style}
@d sub_style(#)     == 2*(# div 4)+script_style+cramped {smaller and cramped}
@d sup_style(#)     == 2*(# div 4)+script_style+(# mod 2) {smaller}
@d num_style(#)     == #+2-2*(# div 6)                  {smaller unless already script-script}
@d denom_style(#)   == 2*(# div 2)+cramped+2-2*(# div 6) {smaller, cramped}
```

Expanded tables:

| cur_style | cramped | sup_style | sub_style | num_style | denom_style |
|---|---|---|---|---|---|
| 0 D   | 1 D′  | 4 S   | 5 S′  | 2 T   | 3 T′  |
| 1 D′  | 1 D′  | 5 S′  | 5 S′  | 3 T′  | 3 T′  |
| 2 T   | 3 T′  | 4 S   | 5 S′  | 4 S   | 5 S′  |
| 3 T′  | 3 T′  | 5 S′  | 5 S′  | 5 S′  | 5 S′  |
| 4 S   | 5 S′  | 6 SS  | 7 SS′ | 6 SS  | 7 SS′ |
| 5 S′  | 5 S′  | 7 SS′ | 7 SS′ | 7 SS′ | 7 SS′ |
| 6 SS  | 7 SS′ | 6 SS  | 7 SS′ | 6 SS  | 7 SS′ |
| 7 SS′ | 7 SS′ | 7 SS′ | 7 SS′ | 7 SS′ | 7 SS′ |

Verify `num_style(6) = 6+2-2*(6 div 6) = 6`; `denom_style(6) = 2*3+1+2-2 = 7`. Correct:
script-script does not shrink further.

Size code from style (§703):
```
@<Set up the values of |cur_size| and |cur_mu|, based on |cur_style|@>=
begin if cur_style<script_style then cur_size:=text_size
else cur_size:=16*((cur_style-text_style) div 2);
cur_mu:=x_over_n(math_quad(cur_size),18);
end
```
with `@d text_size=0`, `@d script_size=16`, `@d script_script_size=32` (§699).
Check: style 4 (S) ⇒ `16*((4-2) div 2)` = 16 = script_size. Style 6 ⇒ `16*2` = 32. Style 7
⇒ `16*((7-2) div 2)` = `16*2` = 32. Styles 0..3 ⇒ text_size. Correct.

**`cur_mu` = math_quad / 18.** `1 mu = 1/18 em` measured in the *math symbol font of the
current size*.

### 7.5 The inter-atom spacing table (§764) — verbatim

```
@d math_spacing=@;@/
"0234000122*4000133**3**344*0400400*000000234000111*1111112341011"
```
(64 characters; I counted them.)

Legend (§764, verbatim):
```
0 means no space;
1 means a conditional thin space (\nonscript\mskip\thinmuskip);
2 means a thin space (\mskip\thinmuskip);
3 means a conditional medium space (\nonscript\mskip\medmuskip);
4 means a conditional thick space (\nonscript\mskip\thickmuskip);
* means an impossible case.
```

Indexing (§765, §766):
```
@<Compute the magic offset@>=
magic_offset:=str_start[math_spacing]-9*ord_noad

@<Append inter-element spacing based on |r_type| and |t|@>=
if r_type>0 then {not the first noad}
  begin case so(str_pool[r_type*8+t+magic_offset]) of
  "0": x:=0;
  "1": if cur_style<script_style then x:=thin_mu_skip_code else x:=0;
  "2": x:=thin_mu_skip_code;
  "3": if cur_style<script_style then x:=med_mu_skip_code else x:=0;
  "4": if cur_style<script_style then x:=thick_mu_skip_code else x:=0;
  othercases confusion("mlist4")
  endcases;
  if x<>0 then
    begin y:=math_glue(glue_par(x),cur_mu);
    z:=new_glue(y); glue_ref_count(y):=null; link(p):=z; p:=z;
    subtype(z):=x+1; {store a symbolic subtype}
    end;
  end
```
Since `r_type*8 + t - 9*ord_noad = 8*(r_type - ord_noad) + (t - ord_noad)`, the index is
`8*row + col` with `row = previous atom class − Ord` and `col = current atom class − Ord`,
both in 0..7 for Ord, Op, Bin, Rel, Open, Close, Punct, Inner.

**Decoded table** (rows = left/previous atom, columns = right/current atom):

|  | Ord | Op | Bin | Rel | Open | Close | Punct | Inner |
|---|---|---|---|---|---|---|---|---|
| **Ord**   | 0 | 2 | 3 | 4 | 0 | 0 | 0 | 1 |
| **Op**    | 2 | 2 | * | 4 | 0 | 0 | 0 | 1 |
| **Bin**   | 3 | 3 | * | * | 3 | * | * | 3 |
| **Rel**   | 4 | 4 | * | 0 | 4 | 0 | 0 | 4 |
| **Open**  | 0 | 0 | * | 0 | 0 | 0 | 0 | 0 |
| **Close** | 0 | 2 | 3 | 4 | 0 | 0 | 0 | 1 |
| **Punct** | 1 | 1 | * | 1 | 1 | 1 | 1 | 1 |
| **Inner** | 1 | 2 | 3 | 4 | 1 | 0 | 1 | 1 |

In glue terms:

|  | Ord | Op | Bin | Rel | Open | Close | Punct | Inner |
|---|---|---|---|---|---|---|---|---|
| **Ord**   | — | thin | (med) | (thick) | — | — | — | (thin) |
| **Op**    | thin | thin | * | (thick) | — | — | — | (thin) |
| **Bin**   | (med) | (med) | * | * | (med) | * | * | (med) |
| **Rel**   | (thick) | (thick) | * | — | (thick) | — | — | (thick) |
| **Open**  | — | — | * | — | — | — | — | — |
| **Close** | — | thin | (med) | (thick) | — | — | — | (thin) |
| **Punct** | (thin) | (thin) | * | (thin) | (thin) | (thin) | (thin) | (thin) |
| **Inner** | (thin) | thin | (med) | (thick) | (thin) | — | (thin) | (thin) |

Parentheses = **suppressed in script and scriptscript styles** (codes 1, 3, 4: the test is
`cur_style < script_style`, i.e. inserted only in display/text styles, cramped or not).
Only code `2` (Ord–Op, Op–Ord, Op–Op, Close–Op, Inner–Op) is unconditional.

`*` cases are unreachable because a `bin_noad` is demoted to `ord_noad` whenever it is not
in binary position (§728, §729):
```
bin_noad: case r_type of
  bin_noad,op_noad,rel_noad,open_noad,punct_noad,left_noad:
    begin type(q):=ord_noad; goto reswitch;
    end;
  othercases do_nothing
  endcases;
rel_noad,close_noad,punct_noad,right_noad: begin
  <Convert a final bin_noad to an ord_noad>;   {= if r_type=bin_noad then type(r):=ord_noad}
  if type(q)=right_noad then goto done_with_noad;
  end;
```

The glue itself: `math_glue(glue_par(x), cur_mu)` (§716) converts a `mu`-valued spec to
scaled points:
```
@d mu_mult(#) == nx_plus_y(n,#,xn_over_d(#,f,@'200000))
n:=x_over_n(m,@'200000); f:=remainder;   {m = cur_mu, split into integer+fraction}
width(p):=mu_mult(width(g));
stretch_order(p):=stretch_order(g);
if stretch_order(p)=normal then stretch(p):=mu_mult(stretch(g)) else stretch(p):=stretch(g);
shrink_order(p):=shrink_order(g);
if shrink_order(p)=normal then shrink(p):=mu_mult(shrink(g)) else shrink(p):=shrink(g);
```
i.e. finite components scale by `cur_mu`; infinite (fil/fill/filll) components pass through.

Plain TeX's actual values for `\thinmuskip`/`\medmuskip`/`\thickmuskip` are **NOT FOUND in
tex.web search** (they live in `plain.tex`). IniTeX leaves all glue parameters zero (§228
area: all `glue_par` initialized to `zero_glue`).

### 7.6 Penalties between atoms (§761, §767)

```
t:=ord_noad; s:=noad_size; pen:=inf_penalty;
case type(q) of
op_noad,open_noad,close_noad,punct_noad,inner_noad: t:=type(q);
bin_noad: begin t:=bin_noad; pen:=bin_op_penalty; end;
rel_noad: begin t:=rel_noad; pen:=rel_penalty; end;
ord_noad,vcenter_noad,over_noad,under_noad: do_nothing;
radical_noad: s:=radical_noad_size;
accent_noad:  s:=accent_noad_size;
fraction_noad: s:=fraction_noad_size;
left_noad,right_noad: t:=make_left_right(q,style,max_d,max_h);
style_node: <Change the current style and goto delete_q>;
whatsit_node,penalty_node,rule_node,disc_node,adjust_node,ins_node,mark_node,
 glue_node,kern_node:
  begin link(p):=q; p:=q; q:=link(q); link(p):=null; goto done; end;
othercases confusion("mlist3")
endcases
```
So Vcenter/Over/Under/Radical/Accent/Fraction all space as **Ord**. Penalty insertion
(§767): after a `bin_noad` insert `\binoppenalty`, after a `rel_noad` insert `\relpenalty`,
but only if `mlist_penalties` is true, there is a following node, and that node is neither a
penalty node nor a `rel_noad`.

### 7.7 `clean_box` (§720)

```
function clean_box(p:pointer; s:small_number):pointer;
```
Converts a noad field to a box with `shift_amount = 0`, recursing into `mlist_to_hlist` for
`sub_mlist`. If the result is a single already-clean hbox/vbox it is reused; otherwise
`hpack(q, natural)`. §721 then strips a trailing italic-correction kern
("Simplify a trivial box").

---

## 8. Big operators — `make_op` (§749, §750, §751)

This is the sigma path. Verbatim, §749:

```
@ If the nucleus of an |op_noad| is a single character, it is to be
centered vertically with respect to the axis, after first being enlarged
(via a character list in the font) if we are in display style.  The normal
convention for placing displayed limits is to put them above and below the
operator in display style.

The italic correction is removed from the character if there is a subscript
and the limits are not being displayed. The |make_op|
routine returns the value that should be used as an offset between
subscript and superscript.

After |make_op| has acted, |subtype(q)| will be |limits| if and only if
the limits have been set above and below the operator. In that case,
|new_hlist(q)| will already contain the desired final box.

@<Declare math...@>=
function make_op(@!q:pointer):scaled;
var delta:scaled; {offset between subscript and superscript}
@!p,@!v,@!x,@!y,@!z:pointer; {temporary registers for box construction}
@!c:quarterword;@+@!i:four_quarters; {registers for character examination}
@!shift_up,@!shift_down:scaled; {dimensions for box calculation}
begin if (subtype(q)=normal)and(cur_style<text_style) then
  subtype(q):=limits;
if math_type(nucleus(q))=math_char then
  begin fetch(nucleus(q));
  if (cur_style<text_style)and(char_tag(cur_i)=list_tag) then {make it larger}
    begin c:=rem_byte(cur_i); i:=char_info(cur_f)(c);
    if char_exists(i) then
      begin cur_c:=c; cur_i:=i; character(nucleus(q)):=c;
      end;
    end;
  delta:=char_italic(cur_f)(cur_i); x:=clean_box(nucleus(q),cur_style);
  if (math_type(subscr(q))<>empty)and(subtype(q)<>limits) then
    width(x):=width(x)-delta; {remove italic correction}
  shift_amount(x):=half(height(x)-depth(x)) - axis_height(cur_size);
    {center vertically}
  math_type(nucleus(q)):=sub_box; info(nucleus(q)):=x;
  end
else delta:=0;
if subtype(q)=limits then
  @<Construct a box with limits above and below it, skewed by |delta|@>;
make_op:=delta;
end;
```

### 8.1 `\limits` vs `\nolimits`

- `@d limits=1`, `@d no_limits=2` are `op_noad` subtypes (§682); `normal=0` means "default".
- First line of `make_op`: **if the subtype is still `normal` and we are in display style,
  it becomes `limits`.** So in display style, limits are stacked by default; in text/script
  style they are not.
- `\limits` / `\nolimits` set the subtype explicitly and thereby override the style default
  in both directions.
- After `make_op`, `subtype(q)=limits` iff the limits were actually stacked, and in that
  case `new_hlist(q)` is already the finished box — the caller (§733) does
  `op_noad: begin delta:=make_op(q); if subtype(q)=limits then goto check_dimensions; end;`
  so `make_scripts` is *not* called.

### 8.2 Selecting the larger glyph

```
if (cur_style<text_style)and(char_tag(cur_i)=list_tag) then {make it larger}
  begin c:=rem_byte(cur_i); i:=char_info(cur_f)(c);
  if char_exists(i) then
    begin cur_c:=c; cur_i:=i; character(nucleus(q)):=c;
    end;
  end;
```
- `@d char_tag(#) == ((qo(#.b2)) mod 4)` (§554); `@d rem_byte(#) == #.b3` (§545).
- `@d no_tag=0`, `@d lig_tag=1`, `@d list_tag=2`, `@d ext_tag=3` (§544).
- §544, verbatim: "`tag=2` (`list_tag`) means that this character is part of a chain of
  characters of ascending sizes, and not the largest in the chain. The `remainder` field
  gives the character code of the next larger character." … "Characters with `tag=2` and
  `tag=3` are treated as characters with `tag=0` unless they are used in special
  circumstances in math formulas. For example, the `\sum` operation looks for a `list_tag`,
  and the `\left` operation looks for both `list_tag` and `ext_tag`."

**Critical detail:** `make_op` follows the successor chain **exactly one step**, and only in
display style. It does not loop. `cmsy` supplies the text-size `\sum` at `cmex10` position
and its `list_tag` successor is the display-size `\sum`. There is no size-fitting search
here — unlike `var_delimiter`.

`var_delimiter` (§706, §707, §708) is the one that *does* walk the chain, and it also
handles `ext_tag`:
```
@<Look at the list of characters starting with |x|...@>=      {§708}
begin y:=x;
if (qo(y)>=font_bc[g])and(qo(y)<=font_ec[g]) then
  begin continue: q:=char_info(g)(y);
  if char_exists(q) then
    begin if char_tag(q)=ext_tag then
      begin f:=g; c:=y; goto found;
      end;
    hd:=height_depth(q);
    u:=char_height(g)(hd)+char_depth(g)(hd);
    if u>w then
      begin f:=g; c:=y; w:=u;
      if u>=v then goto found;
      end;
    if char_tag(q)=list_tag then
      begin y:=rem_byte(q); goto continue;
      end;
    end;
  end;
end
```
and §707 first tries the "small" variant across all three sizes (`z:=z+s+16; repeat z:=z-16;
… until z<16`), then the "large" variant.

Extensible assembly (§713, §714), for completeness:
```
@d ext_top(#)==#.b0   @d ext_mid(#)==#.b1   @d ext_bot(#)==#.b2   @d ext_rep(#)==#.b3   {§546}

b:=new_null_box; type(b):=vlist_node;
r:=font_info[exten_base[f]+rem_byte(q)].qqqq;
<Compute the minimum suitable height, w, and the number of extension steps, n; set width(b)>;
c:=ext_bot(r); if c<>min_quarterword then stack_into_box(b,f,c);
c:=ext_rep(r); for m:=1 to n do stack_into_box(b,f,c);
c:=ext_mid(r);
if c<>min_quarterword then
  begin stack_into_box(b,f,c); c:=ext_rep(r);
  for m:=1 to n do stack_into_box(b,f,c);
  end;
c:=ext_top(r); if c<>min_quarterword then stack_into_box(b,f,c);
depth(b):=w-height(b);
```
§546: "the extensible characters have the form $TR^kMR^kB$ from top to bottom, for some
$k\ge0$, unless $M$ is absent; in the latter case we can have $TR^kB$ for both even and odd
values of $k$. The width of the extensible character is the width of $R$; and the
height-plus-depth is the sum of the individual height-plus-depths of the components used."
Sizing loop (§714): `n:=0; if u>0 then while w<v do begin w:=w+u; incr(n); if ext_mid(r)<>0
then w:=w+u; end` where `u = height_plus_depth(rep)`.

### 8.3 Vertical centering on the math axis

```
shift_amount(x) := half(height(x) - depth(x)) - axis_height(cur_size);
```
`x` is `clean_box(nucleus(q), cur_style)` — a box whose baseline is the glyph's baseline.
Recall `shift_amount` in an hlist means **move down**.

Derivation: after shifting by `s`, the box's top is at `-(height − s)` and its bottom at
`depth + s` relative to the enclosing baseline (with +y down). The midpoint is at
`s + (depth − height)/2`. Setting that equal to `−axis_height` (the axis is *above* the
baseline, so at `−axis_height` in +y-down coordinates) gives
`s = (height − depth)/2 − axis_height`. That is exactly the code.

**In words: the vertical centre of the operator glyph is placed on the math axis.**

The same formula appears in `var_delimiter` (§706):
`shift_amount(b):=half(height(b)-depth(b)) - axis_height(s);`
and, in the complementary form, in `make_vcenter` (§736):
```
delta:=height(v)+depth(v);
height(v):=axis_height(cur_size)+half(delta);
depth(v):=delta-height(v);
```

### 8.4 Italic correction and the sub/sup offset

```
delta := char_italic(cur_f)(cur_i);
...
if (math_type(subscr(q))<>empty) and (subtype(q)<>limits) then
  width(x) := width(x) - delta;   {remove italic correction}
...
make_op := delta;
```
`clean_box` on a `math_char` nucleus produces a box whose width *includes* the italic
correction (via the kern appended in §755, unless stripped by §721). When there is a
subscript and limits are inline, the correction is removed from the width, and `delta` is
returned to `make_scripts` as the horizontal offset of the superscript relative to the
subscript — that is what makes $\int_a^b$ lean.

### 8.5 Stacking limits (§750, §751) — verbatim

```
@<Construct a box with limits above and below it...@>=          {§750}
begin x:=clean_box(supscr(q),sup_style(cur_style));
y:=clean_box(nucleus(q),cur_style);
z:=clean_box(subscr(q),sub_style(cur_style));
v:=new_null_box; type(v):=vlist_node; width(v):=width(y);
if width(x)>width(v) then width(v):=width(x);
if width(z)>width(v) then width(v):=width(z);
x:=rebox(x,width(v)); y:=rebox(y,width(v)); z:=rebox(z,width(v));
shift_amount(x):=half(delta); shift_amount(z):=-shift_amount(x);
height(v):=height(y); depth(v):=depth(y);
@<Attach the limits to |y| and adjust |height(v)|, |depth(v)| to
  account for their presence@>;
new_hlist(q):=v;
end
```
```
@<Attach the limits to |y| and adjust |height(v)|, |depth(v)|...@>=    {§751}
if math_type(supscr(q))=empty then
  begin free_node(x,box_node_size); list_ptr(v):=y;
  end
else  begin shift_up:=big_op_spacing3-depth(x);
  if shift_up<big_op_spacing1 then shift_up:=big_op_spacing1;
  p:=new_kern(shift_up); link(p):=y; link(x):=p;
  p:=new_kern(big_op_spacing5); link(p):=x; list_ptr(v):=p;
  height(v):=height(v)+big_op_spacing5+height(x)+depth(x)+shift_up;
  end;
if math_type(subscr(q))=empty then free_node(z,box_node_size)
else  begin shift_down:=big_op_spacing4-height(z);
  if shift_down<big_op_spacing2 then shift_down:=big_op_spacing2;
  p:=new_kern(shift_down); link(y):=p; link(p):=z;
  p:=new_kern(big_op_spacing5); link(z):=p;
  depth(v):=depth(v)+big_op_spacing5+height(z)+depth(z)+shift_down;
  end
```

**Resulting vlist inside `v`, top to bottom:**
```
kern big_op_spacing5
box  x                (upper limit, reboxed to width(v), shifted right by half(delta))
kern shift_up         = max(big_op_spacing3 - depth(x), big_op_spacing1)
box  y                (the operator, reboxed to width(v))
kern shift_down       = max(big_op_spacing4 - height(z), big_op_spacing2)
box  z                (lower limit, shifted right by -half(delta))
kern big_op_spacing5
```
and
```
width(v)  = max(width(x), width(y), width(z))
height(v) = height(y) + [big_op_spacing5 + height(x) + depth(x) + shift_up]   if sup present
depth(v)  = depth(y)  + [big_op_spacing5 + height(z) + depth(z) + shift_down] if sub present
```
Note `v` is a **vlist node built by hand, not by `vpack`** — the height/depth are computed
explicitly, and `list_ptr(v)` is assigned directly. Its baseline therefore coincides with
`y`'s baseline, i.e. with the operator's own (already axis-centred) baseline. The
`big_op_spacing5` kerns are *padding* that is included in height/depth, so the surrounding
`baselineskip`/interline logic sees the full extent.

`rebox(b, w)` (§715) centres `b` in width `w` by wrapping the contents in `\hss` glue:
```
if (width(b)<>w)and(list_ptr(b)<>null) then
  begin if type(b)=vlist_node then b:=hpack(b,natural);
  p:=list_ptr(b);
  if (is_char_node(p))and(link(p)=null) then
    begin f:=font(p); v:=char_width(f)(char_info(f)(character(p)));
    if v<>width(b) then link(p):=new_kern(width(b)-v);
    end;
  free_node(b,box_node_size);
  b:=new_glue(ss_glue); link(b):=p;
  while link(p)<>null do p:=link(p);
  link(p):=new_glue(ss_glue);
  rebox:=hpack(b,w,exactly);
  end
else begin width(b):=w; rebox:=b; end;
```
(The single-char special case compensates for the italic correction that `clean_box`
folded into the width.)

### 8.6 `big_op_spacing` semantics (§701)

```
@d default_rule_thickness == mathex(8)  {thickness of \over bars}
@d big_op_spacing1 == mathex(9)   {minimum clearance above a displayed op}
@d big_op_spacing2 == mathex(10)  {minimum clearance below a displayed op}
@d big_op_spacing3 == mathex(11)  {minimum baselineskip above displayed op}
@d big_op_spacing4 == mathex(12)  {minimum baselineskip below displayed op}
@d big_op_spacing5 == mathex(13)  {padding above and below displayed limits}
```
So 1/2 are *gap* minima (kern between the boxes), 3/4 are *baseline-distance* minima
(the kern is reduced by the limit box's depth/height), and 5 is unconditional padding.

---

## 9. Fractions, radicals, scripts

### 9.1 `make_fraction` (§743–§748)

```
procedure make_fraction(q:pointer);                       {§743}
begin if thickness(q)=default_code then thickness(q):=default_rule_thickness;
<Create equal-width boxes x and z for the numerator and denominator, and compute the
 default amounts shift_up and shift_down by which they are displaced from the baseline>;
if thickness(q)=0 then <Adjust shift_up and shift_down for the case of no fraction line>
else <Adjust shift_up and shift_down for the case of a fraction line>;
<Construct a vlist box for the fraction, according to shift_up and shift_down>;
<Put the fraction into a box with its delimiters, and make new_hlist(q) point to it>;
end;
```

Defaults (§744):
```
x:=clean_box(numerator(q),num_style(cur_style));
z:=clean_box(denominator(q),denom_style(cur_style));
if width(x)<width(z) then x:=rebox(x,width(z))
else z:=rebox(z,width(x));
if cur_style<text_style then {display style}
  begin shift_up:=num1(cur_size); shift_down:=denom1(cur_size);
  end
else begin shift_down:=denom2(cur_size);
  if thickness(q)<>0 then shift_up:=num2(cur_size)
  else shift_up:=num3(cur_size);
  end
```
So: **display ⇒ `num1`/`denom1`; non-display with a rule ⇒ `num2`/`denom2`; non-display
`\atop` (thickness 0) ⇒ `num3`/`denom2`.** `num3` is never used in display style.

No fraction line (§745):
```
begin if cur_style<text_style then clr:=7*default_rule_thickness
else clr:=3*default_rule_thickness;
delta:=half(clr-((shift_up-depth(x))-(height(z)-shift_down)));
if delta>0 then
  begin shift_up:=shift_up+delta;
  shift_down:=shift_down+delta;
  end;
end
```
(`(shift_up − depth(x))` is the bottom of the numerator above the baseline;
`(height(z) − shift_down)` is the top of the denominator above the baseline; the difference
is the actual gap. `clr` is the minimum gap: 7× rule thickness in display, 3× otherwise.
The deficiency is split evenly between the two.)

With a fraction line (§746):
```
begin if cur_style<text_style then clr:=3*thickness(q)
else clr:=thickness(q);
delta:=half(thickness(q));
delta1:=clr-((shift_up-depth(x))-(axis_height(cur_size)+delta));
delta2:=clr-((axis_height(cur_size)-delta)-(height(z)-shift_down));
if delta1>0 then shift_up:=shift_up+delta1;
if delta2>0 then shift_down:=shift_down+delta2;
end
```
`delta = half(thickness)`: the rule is centred on the axis, so its top is at
`axis_height + delta` and its bottom at `axis_height − delta`. `clr` is the minimum
clearance between numerator-bottom and rule-top (and rule-bottom and denominator-top):
3× the thickness in display, 1× otherwise.

vlist assembly (§747):
```
v:=new_null_box; type(v):=vlist_node;
height(v):=shift_up+height(x); depth(v):=depth(z)+shift_down;
width(v):=width(x); {this also equals width(z)}
if thickness(q)=0 then
  begin p:=new_kern((shift_up-depth(x))-(height(z)-shift_down));
  link(p):=z;
  end
else begin y:=fraction_rule(thickness(q));
  p:=new_kern((axis_height(cur_size)-delta)-(height(z)-shift_down));
  link(y):=p; link(p):=z;
  p:=new_kern((shift_up-depth(x))-(axis_height(cur_size)+delta));
  link(p):=y;
  end;
link(x):=p; list_ptr(v):=x
```
`fraction_rule(t)` (§704) is a rule node with `height(p):=t; depth(p):=0;` and running width.

Delimiters (§748):
```
if cur_style<text_style then delta:=delim1(cur_size)
else delta:=delim2(cur_size);
x:=var_delimiter(left_delimiter(q), cur_size, delta); link(x):=v;
z:=var_delimiter(right_delimiter(q), cur_size, delta); link(v):=z;
new_hlist(q):=hpack(x,natural)
```
`delim1`/`delim2` are the *requested height-plus-depth* of the delimiters — display vs.
non-display. With `null_delimiter` (fam 0, char 0) `var_delimiter` returns an empty box of
width `\nulldelimiterspace` (§706).

### 9.2 `make_radical` (§737) — verbatim

```
procedure make_radical(@!q:pointer);
var x,@!y:pointer;
@!delta,@!clr:scaled;
begin x:=clean_box(nucleus(q),cramped_style(cur_style));
if cur_style<text_style then {display style}
  clr:=default_rule_thickness+(abs(math_x_height(cur_size)) div 4)
else  begin clr:=default_rule_thickness; clr:=clr + (abs(clr) div 4);
  end;
y:=var_delimiter(left_delimiter(q),cur_size,height(x)+depth(x)+clr+
  default_rule_thickness);
delta:=depth(y)-(height(x)+depth(x)+clr);
if delta>0 then clr:=clr+half(delta); {increase the actual clearance}
shift_amount(y):=-(height(x)+clr);
link(y):=overbar(x,clr,height(y));
info(nucleus(q)):=hpack(y,natural); math_type(nucleus(q)):=sub_box;
end;
```
Clearance: display ⇒ `default_rule_thickness + |math_x_height|/4`;
otherwise ⇒ `default_rule_thickness * 5/4` (written as `t + t/4`).

§737 prose: "we ensure alignment between a square root sign and the rule above its nucleus
by assuming that the baseline of the square-root symbol is the same as the bottom of the
rule. The height of the square-root symbol will be the thickness of the rule, and the depth
of the square-root symbol should exceed or equal the height-plus-depth of the nucleus plus a
certain minimum clearance `clr`. The symbol will be placed so that the actual clearance is
`clr` plus half the excess."

`overbar(b,k,t)` (§705):
```
function overbar(b:pointer; k,t:scaled):pointer;
begin p:=new_kern(k); link(p):=b; q:=fraction_rule(t); link(q):=p;
p:=new_kern(t); link(p):=q; overbar:=vpack(p,natural);
end;
```
= vlist of [kern t, rule of thickness t, kern k, box b].

Related: `make_over` (§734) is `overbar(clean_box(nucleus, cramped_style(cur_style)),
3*default_rule_thickness, default_rule_thickness)`. `make_under` (§735) puts
`new_kern(3*default_rule_thickness)` then `fraction_rule(default_rule_thickness)` below, and
then fixes the height/depth so the original baseline is preserved.

### 9.3 `make_scripts` (§756–§759) — verbatim

```
procedure make_scripts(@!q:pointer;@!delta:scaled);                 {§756}
var p,@!x,@!y,@!z:pointer;
@!shift_up,@!shift_down,@!clr:scaled;
@!t:small_number;
begin p:=new_hlist(q);
if is_char_node(p) then
  begin shift_up:=0; shift_down:=0;
  end
else  begin z:=hpack(p,natural);
  if cur_style<script_style then t:=script_size@+else t:=script_script_size;
  shift_up:=height(z)-sup_drop(t);
  shift_down:=depth(z)+sub_drop(t);
  free_node(z,box_node_size);
  end;
if math_type(supscr(q))=empty then
  <Construct a subscript box x when there is no superscript>
else  begin <Construct a superscript box x>;
  if math_type(subscr(q))=empty then shift_amount(x):=-shift_up
  else <Construct a sub/superscript combination box x, with the
    superscript offset by delta>;
  end;
if new_hlist(q)=null then new_hlist(q):=x
else  begin p:=new_hlist(q);
  while link(p)<>null do p:=link(p);
  link(p):=x;
  end;
end;
```
**Note `t`:** `sup_drop`/`sub_drop` are looked up at the size of the *scripts*, not the
nucleus: `script_size` when the current style is display or text, `script_script_size`
otherwise. Everything else uses `cur_size`.

A bare character nucleus gets `shift_up = shift_down = 0` (no drop). A composite nucleus
drops the superscript baseline `sup_drop` below its top and the subscript baseline
`sub_drop` below its bottom.

Subscript only (§757):
```
begin x:=clean_box(subscr(q),sub_style(cur_style));
width(x):=width(x)+script_space;
if shift_down<sub1(cur_size) then shift_down:=sub1(cur_size);
clr:=height(x)-(abs(math_x_height(cur_size)*4) div 5);
if shift_down<clr then shift_down:=clr;
shift_amount(x):=shift_down;
end
```
Clamps: `shift_down >= sub1` and `shift_down >= height(x) − (4/5)·|math_x_height|`,
i.e. **the top of the subscript must not rise above baseline + 4/5 x-height** (§757 prose:
"the top of the subscript should not exceed the baseline plus four-fifths of the x-height").

Superscript (§758):
```
begin x:=clean_box(supscr(q),sup_style(cur_style));
width(x):=width(x)+script_space;
if odd(cur_style) then clr:=sup3(cur_size)
else if cur_style<text_style then clr:=sup1(cur_size)
else clr:=sup2(cur_size);
if shift_up<clr then shift_up:=clr;
clr:=depth(x)+(abs(math_x_height(cur_size)) div 4);
if shift_up<clr then shift_up:=clr;
end
```
`sup3` if cramped, `sup1` if uncramped display, `sup2` otherwise. Then
`shift_up >= depth(x) + (1/4)·|math_x_height|`, i.e. **the bottom of the superscript must
not descend below baseline + 1/4 x-height**.

> **Correction to the brief:** you wrote "the 4/5 and 1/5 x-height clamps". The code has
> **4/5** (subscript top, §757 and again in §759) and **1/4** (superscript bottom, §758) —
> `abs(math_x_height(cur_size)*4) div 5` and `abs(math_x_height(cur_size)) div 4`.
> There is no 1/5 anywhere in these sections.

Both together (§759):
```
begin y:=clean_box(subscr(q),sub_style(cur_style));
width(y):=width(y)+script_space;
if shift_down<sub2(cur_size) then shift_down:=sub2(cur_size);
clr:=4*default_rule_thickness-((shift_up-depth(x))-(height(y)-shift_down));
if clr>0 then
  begin shift_down:=shift_down+clr;
  clr:=(abs(math_x_height(cur_size)*4) div 5)-(shift_up-depth(x));
  if clr>0 then
    begin shift_up:=shift_up+clr;
    shift_down:=shift_down-clr;
    end;
  end;
shift_amount(x):=delta; {superscript is delta to the right of the subscript}
p:=new_kern((shift_up-depth(x))-(height(y)-shift_down)); link(x):=p; link(p):=y;
x:=vpack(x,natural); shift_amount(x):=shift_down;
end
```
§759 prose: "the subscript must be separated from the superscript by at least four times
`default_rule_thickness`. If this condition would be violated, the subscript moves down,
after which both subscript and superscript move up so that the bottom of the superscript
is at least as high as the baseline plus four-fifths of the x-height."

Note the assembly: a **vlist** of [sup box (shifted right by `delta`), kern, sub box],
`vpack`ed naturally, and then the *whole vlist* is shifted down by `shift_down` — which is
why the sub/sup pair rides together. `sub2` (not `sub1`) is the floor when both are present.

`script_space` (`\scriptspace`, dimen param 12, §247) is added to the *width* of every
script box.

---

## 10. Font metric parameters

### 10.1 TFM accessors (§554, §557, §558)

```
@d char_info_end(#)==#].qqqq
@d char_info(#)==font_info[char_base[#]+char_info_end
@d char_width_end(#)==#.b0].sc
@d char_width(#)==font_info[width_base[#]+char_width_end
@d char_exists(#)==(#.b0>min_quarterword)
@d char_italic_end(#)==(qo(#.b2)) div 4].sc
@d char_italic(#)==font_info[italic_base[#]+char_italic_end
@d height_depth(#)==qo(#.b1)
@d char_height_end(#)==(#) div 16].sc
@d char_height(#)==font_info[height_base[#]+char_height_end
@d char_depth_end(#)==(#) mod 16].sc
@d char_depth(#)==font_info[depth_base[#]+char_depth_end
@d char_tag(#)==((qo(#.b2)) mod 4)
...
@d char_kern_end(#)==256*op_byte(#)+rem_byte(#)].sc
@d char_kern(#)==font_info[kern_base[#]+char_kern_end
@d kern_base_offset==256*(128+min_quarterword)
...
@d param(#)==font_info[#+param_end
```
A `char_info_word` packs: `b0` = width index (0 ⇒ character does not exist),
`b1` = (height index)·16 + (depth index), `b2` = (italic index)·4 + tag, `b3` = remainder.
TFM allows at most 16 heights, 16 depths, 64 italic corrections (§543).

### 10.2 Text-font `\fontdimen` (§547, §558)

| index | name | §547 description |
|---|---|---|
| 1 | `slant` | "the amount of italic slant, which is used to help position accents. For example, `slant=.25` means that when you go up one unit, you also go .25 units to the right. The `slant` is a pure number; it's the only `fix_word` other than the design size itself that is not scaled by the design size." |
| 2 | `space` | "the normal spacing between words in text. Note that character `" "` in the font need not have anything to do with blank spaces." |
| 3 | `space_stretch` | "the amount of glue stretching between words" |
| 4 | `space_shrink` | "the amount of glue shrinking between words" |
| 5 | `x_height` | "the size of one ex in the font; it is also the height of letters for which accents don't have to be raised or lowered" |
| 6 | `quad` | "the size of one em in the font" |
| 7 | `extra_space` | "the amount added to `param[2]` at the ends of sentences" |

"If fewer than seven parameters are present, TeX sets the missing parameters to zero."

Macro names (§558):
```
@d slant==param(slant_code)      @d space==param(space_code)
@d space_stretch==param(space_stretch_code)  @d space_shrink==param(space_shrink_code)
@d x_height==param(x_height_code) @d quad==param(quad_code)
@d extra_space==param(extra_space_code)
```
Codes (§547): `slant_code=1 … extra_space_code=7`.

Note: `space(f) = 0` is TeX's test for "this is a math font" (§752:
"The `math_type` is converted to `math_text_char` here if we would not want to apply an
italic correction to the current character unless it belongs to a math font (i.e., a font
with `space=0`)"; also §755).

### 10.3 MathSymbol (family 2, "sigma") parameters 1–22 (§700)

```
@d mathsy_end(#)==fam_fnt(2+#)]].sc
@d mathsy(#)==font_info[#+param_base[mathsy_end
@d math_x_height==mathsy(5)  {height of `x'}
@d math_quad==mathsy(6)      {18mu}
@d num1==mathsy(8)   {numerator shift-up in display styles}
@d num2==mathsy(9)   {numerator shift-up in non-display, non-\atop}
@d num3==mathsy(10)  {numerator shift-up in non-display \atop}
@d denom1==mathsy(11) {denominator shift-down in display styles}
@d denom2==mathsy(12) {denominator shift-down in non-display styles}
@d sup1==mathsy(13)  {superscript shift-up in uncramped display style}
@d sup2==mathsy(14)  {superscript shift-up in uncramped non-display}
@d sup3==mathsy(15)  {superscript shift-up in cramped styles}
@d sub1==mathsy(16)  {subscript shift-down if superscript is absent}
@d sub2==mathsy(17)  {subscript shift-down if superscript is present}
@d sup_drop==mathsy(18) {superscript baseline below top of large box}
@d sub_drop==mathsy(19) {subscript baseline below bottom of large box}
@d delim1==mathsy(20) {size of \atopwithdelims delimiters in display styles}
@d delim2==mathsy(21) {size of \atopwithdelims delimiters in non-displays}
@d axis_height==mathsy(22) {height of fraction lines above the baseline}
@d total_mathsy_params=22
```
Parameters 1–7 are the ordinary text parameters (slant, space, …, extra_space);
**parameters 8–22 are the math-specific ones**, and parameters 5 and 6 are reused under
the names `math_x_height` and `math_quad`. All of `mathsy(n)` take a *size code*
argument (`text_size`=0 / `script_size`=16 / `script_script_size`=32), so each is really
three numbers.

### 10.4 MathExtension (family 3, "xi") parameters 1–13 (§701)

```
@d mathex(#)==font_info[#+param_base[fam_fnt(3+cur_size)]].sc
@d default_rule_thickness==mathex(8)  {thickness of \over bars}
@d big_op_spacing1==mathex(9)   {minimum clearance above a displayed op}
@d big_op_spacing2==mathex(10)  {minimum clearance below a displayed op}
@d big_op_spacing3==mathex(11)  {minimum baselineskip above displayed op}
@d big_op_spacing4==mathex(12)  {minimum baselineskip below displayed op}
@d big_op_spacing5==mathex(13)  {padding above and below displayed limits}
@d total_mathex_params=13
```
Parameters 1–7 are again the text parameters. `mathex` does **not** take a size argument —
"the size code is omitted (since it is always `cur_size` when we refer to such parameters)"
(§701).

### 10.5 The enforcement check (§1195)

```
if (font_params[fam_fnt(2+text_size)]<total_mathsy_params)or
   (font_params[fam_fnt(2+script_size)]<total_mathsy_params)or
   (font_params[fam_fnt(2+script_script_size)]<total_mathsy_params) then
  begin print_err("Math formula deleted: Insufficient symbol fonts"); ... end
else if (font_params[fam_fnt(3+text_size)]<total_mathex_params)or ... then
  begin print_err("Math formula deleted: Insufficient extension fonts"); ... end
```
TeX refuses to typeset math at all unless all three sizes of family 2 have ≥22 params and
all three sizes of family 3 have ≥13.

### 10.6 Synthesising these from a plain TrueType/OpenType font

**None of the numeric values of `cmsy10`/`cmex10` appear in tex.web** — they live in TFM
files. **NOT FOUND in tex.web search.**

What a TrueType font *does* give you:
- `unitsPerEm`, `hhea.ascender`/`descender`, `OS/2.sxHeight`, `OS/2.sCapHeight`,
  `post.italicAngle`, `OS/2.yStrikeoutPosition`/`yStrikeoutSize`,
  `post.underlinePosition`/`underlineThickness`
- per-glyph advance, bounding box (which gives height/depth), and (with `GPOS`) kerning
- an OpenType `MATH` table **if** the font has one (STIX Two, Latin Modern Math, Cambria
  Math, Libertinus Math). If it does, use it — its `MathConstants` map almost 1:1 onto
  the sigma/xi parameters, and `MathVariants`/`MathGlyphConstruction` replace
  `list_tag`/`ext_tag`.

If there is no `MATH` table, you must synthesise. Below, `em` = font size in px,
`xh` = x-height (fall back to `0.45 em` if `sxHeight` is absent or zero),
`rt` = a rule thickness (use `underlineThickness` scaled to the current size, or
`0.04 em`).

**[All of the following fractions are my proposals, not in tex.web.]** They are chosen to
reproduce the *qualitative* behaviour of the cm fonts, not their exact numbers.

| param | proposal | rationale |
|---|---|---|
| `slant` (1) | `tan(-post.italicAngle)` | exactly what TFM param 1 means (§547) |
| `space` (2) | advance of U+0020 | direct |
| `space_stretch` (3) | `0.5 * space` | — |
| `space_shrink` (4) | `0.33 * space` | — |
| `x_height` / `math_x_height` (5) | `OS/2.sxHeight`, else `0.45 em` | direct |
| `quad` / `math_quad` (6) | `1.0 em` | §547 "the size of one em in the font"; drives `cur_mu = quad/18` (§703) |
| `extra_space` (7) | `0.33 * space` | — |
| `axis_height` (22) | `OS/2.yStrikeoutPosition`, else `0.25 em` (≈ `0.55 * xh`) | the axis is where `−` and `=` sit; the strikeout position is the same idea. Used by `make_op` centring, `make_fraction`, `make_vcenter`, `var_delimiter`. **Get this one right — it is what makes a Σ look centred.** |
| `default_rule_thickness` (xi 8) | `underlineThickness`, else `0.04 em` | fraction bars, `\overline`, and the `4*default_rule_thickness` sub/sup separation in §759 |
| `num1` (8) | `axis_height + 0.5*rt + 3*rt + <numerator depth>` is what the code computes anyway; a flat `0.68 em` works | display numerator shift-up |
| `num2` (9) | `0.39 em` | non-display, with rule |
| `num3` (10) | `0.44 em` | non-display `\atop` (slightly higher, since there's no rule) |
| `denom1` (11) | `0.69 em` | display denominator shift-down |
| `denom2` (12) | `0.34 em` | non-display |
| `sup1` (13) | `0.41 em` | uncramped display |
| `sup2` (14) | `0.36 em` | uncramped non-display |
| `sup3` (15) | `0.29 em` | cramped (lower, because something sits above) |
| `sub1` (16) | `0.15 em` | subscript alone |
| `sub2` (17) | `0.24 em` | subscript with superscript |
| `sup_drop` (18) | `0.39 em` | superscript baseline below top of nucleus box |
| `sub_drop` (19) | `0.05 em` | subscript baseline below bottom of nucleus box |
| `delim1` (20) | `2.4 em` | requested h+d for `\atopwithdelims` in display |
| `delim2` (21) | `1.0 em` | non-display |
| `big_op_spacing1` (xi 9) | `0.11 em` | min gap above op |
| `big_op_spacing2` (xi 10) | `0.17 em` | min gap below op |
| `big_op_spacing3` (xi 11) | `0.20 em` | min baseline distance above |
| `big_op_spacing4` (xi 12) | `0.61 em` | min baseline distance below |
| `big_op_spacing5` (xi 13) | `0.10 em` | padding above/below limits |

Additional synthesis notes:

- **Per-size values.** `mathsy(n)` is indexed by size code. If you only have one font,
  compute the script sizes by scaling: script = 0.7× text, scriptscript = 0.5× text
  (these are plain TeX's `\scriptfont`/`\scriptscriptfont` magnifications and are
  **NOT FOUND in tex.web search** — tex.web only provides the mechanism, `fam_fnt(f+size)`).
  Then all the `em`-relative fractions above scale automatically.
- **`list_tag` / `rem_byte` successor chain has no TrueType equivalent** without a `MATH`
  table. Substitute: keep a hand-written map from text-size codepoint to display-size
  codepoint (e.g. U+2211 Σ at 1.0× for text, and the same glyph scaled 1.4–1.6× for
  display), or use `MathVariants` if present. The `make_op` code only needs *one* step, so
  a single alternate per operator suffices.
- **`ext_tag` is a trap** — see §11 below.
- **`char_italic`** has no direct TrueType equivalent. Approximate with
  `max(0, glyph_bbox.xMax − advance)` for upright fonts, or
  `advance * tan(italicAngle) * something` for italics. A value of 0 is safe but makes
  $\int_a^b$ look slightly wrong.
- Do **not** try to derive `axis_height` from `(ascender + descender)/2`. Use the strikeout
  position; the math axis is a typographic feature, not a geometric midpoint.

---

## 11. Ligature / kerning and the character list (brief)

**Data** (§545): the `lig_kern` array is a list of 4-byte instructions:
```
@d stop_flag == qi(128)   @d kern_flag == qi(128)
@d skip_byte(#)==#.b0     @d next_char(#)==#.b1
@d op_byte(#)==#.b2       @d rem_byte(#)==#.b3
```
- `skip_byte >= 128` ⇒ last step of this program; otherwise skip that many intervening steps.
- `next_char` ⇒ the character that must follow for the instruction to fire.
- `op_byte >= 128` ⇒ kern step, inserting `kern[256*(op_byte-128)+remainder]`
  (`char_kern`, §557). `op_byte < 128` ⇒ ligature step.
- Eight ligature ops, `op_byte = 4a+2b+c` with $0 \le a \le b+c$, $0 \le b,c \le 1$:
  insert `remainder` between the two characters; delete the left one if `b=0`, the right one
  if `c=0`; then pass over `a` characters.
- `skip_byte=255` on the *first* instruction ⇒ `next_char` is the font's boundary character.
  On the *last* ⇒ there is a left-boundary program at `256*op_byte+remainder`.
- `skip_byte > 128` on a character's first instruction ⇒ the real program starts at
  `256*op_byte+remainder` (indirection, so programs can live past index 255).

**Text-mode execution** is the `main_control` inner loop (§1039, §1040). It maintains
`cur_l` (current char), `cur_r` (lookahead), `lig_stack`, `ligature_present`,
`lft_hit`/`rt_hit`, and builds `ligature_node`s that retain the original characters in
`lig_ptr` for later hyphenation. §1039 notes: "tests with Computer Modern Roman showed that
about 40 per cent of all characters actually encountered in practice had a lig/kern
program, and that about four lig/kern commands were investigated for every such character."

**Math-mode execution** is `make_ord` (§752, §753) — a much simpler version with no
boundary characters and no `ligature_node` (the ligature is stored directly in a char node
inside an `ord_noad`). It fires only when the noad has no scripts, the next noad is
Ord..Punct, and both nuclei are `math_char` in the same family.

**Character list** (`list_tag`, §544): a chain of ascending-size variants of one glyph,
followed one step at a time by `rem_byte`. Consumers: `make_op` (one step, §749),
`var_delimiter` (walks the whole chain, §708), `make_math_accent` (walks until the accent is
wider than the accentee, §740).

For a reimplementation on TrueType: use HarfBuzz (or the raw `GSUB`/`GPOS` tables) for
ligatures and kerning. Do not attempt to reimplement the TFM lig/kern VM — it is only
useful if you are consuming TFM/PK fonts.

---

## What a from-scratch reimplementation actually needs

Target: markdown + one display sigma formula, laid out in an immediate-mode GUI.

Ranked by value ÷ complexity. "LOC" is my rough estimate of non-trivial code in C++.

### Tier 1 — do these first, they are the whole system

1. **The box/glue/kern/penalty node model** (§133–§159). ~150 LOC.
   Everything else is a function on this. You do not need all 14 node types: start with
   `hlist`, `vlist`, `rule`, `glue`, `kern`, `penalty`, `char`(or a text-run node), `disc`.
   Skip `ins`, `mark`, `adjust`, `whatsit`, `unset` entirely. **Keep the
   `non_discardable` type ordering** (§148) or invent an explicit predicate.

2. **`hpack`/`vpack` with the four glue orders** (§649–§678) + **the ship-out
   accumulate-and-round glue renderer** (§625/§634). ~200 LOC.
   This is the single highest-value thing in TeX. `\hss`-centring, `\hfil`-justification,
   filling a box to an exact width, and the entire math box assembly all fall out of it for
   free. Implementing `fil/fill/filll` costs you 10 extra lines over finite-only glue and
   buys you `rebox`, `\hss`, and centred limits. **Do not simplify the ship-out path** —
   the `cur_glue`/`cur_g` difference trick is what keeps a justified line from drifting.

3. **`badness`** (§108). 10 LOC. Copy it verbatim. Integer-only, no FP, deterministic
   across platforms. You need it for both line and page breaking.

4. **Interline glue / `append_to_vlist`** (§679). 15 LOC.
   `d = baselineskip − prev_depth − height(b); if d < lineskiplimit use lineskip else use
   baselineskip with width d`. This is what makes multi-line text with mixed font sizes and
   an inline formula not look broken. You explicitly flagged this as important; it really is
   ~15 lines and it is the highest value-per-line item in the whole document.

5. **Breakpoint legality rules** (§866, §868, §869). ~40 LOC.
   You need these regardless of which breaking algorithm you use.

### Tier 2 — high value, moderate cost

6. **Knuth–Plass line breaking: `try_break` + demerits** (§829–§859, §863). ~400 LOC.
   The dynamic program itself is not hard; the delta-node bookkeeping (§822–§824) that makes
   it O(n) *is*. **Simplification that preserves ~95% of the quality:** drop delta nodes and
   just recompute `active_width` by re-walking from each active node's break to `cur_p`.
   That is O(n·k) where k is the active-list size (typically < 20), which for markdown-sized
   paragraphs is free. Keep: fitness classes, `adj_demerits`, the squared
   `(line_penalty + badness)` term, `eject_penalty` forcing. Keep the three-pass structure
   but with **pass 2 = pass 1 without hyphenation** and pass 3 = emergency stretch.
   For a proof-of-concept, even first-fit greedy + `hpack(line, width, exactly)` produces
   correct-looking justified text; the Knuth–Plass upgrade is a drop-in replacement later
   because it consumes exactly the same node list.

7. **`mlist_to_hlist` skeleton + the 8×8 spacing table** (§726, §764–§766). ~200 LOC.
   The spacing table is a 64-byte string and a 12-line switch. Enormous visual payoff for
   almost nothing. Implement the four styles + cramped and the five style-transition macros
   (§702) — they are five one-line expressions and they are what makes nested scripts shrink
   correctly.

8. **`make_op` + limit stacking** (§749–§751). ~90 LOC. Your litmus test.
   The essential pieces, in order of importance:
   a. `shift_amount = half(height − depth) − axis_height` — centre on the axis.
   b. Pick the display-size glyph when `cur_style < text_style`.
   c. `subtype = limits` by default in display style.
   d. The §750/§751 vlist assembly with `big_op_spacing1..5`.
   Even with (a) alone and everything else crude, a Σ will look right.

9. **`make_scripts`** (§756–§759). ~80 LOC. Needed for the limits on the sigma
   (they go through `clean_box(supscr, sup_style(cur_style))` in §750, but any inline
   `x_i^2` in the surrounding text needs the full §756–§759 path).

10. **`make_fraction`** (§743–§748). ~80 LOC. Cheap, and markdown math almost always has
    a fraction somewhere.

### Tier 3 — worth it eventually

11. **Page breaking** (§1000–§1007). ~150 LOC. In an immediate-mode GUI with a scrolling
    viewport you probably do not paginate at all. If you do, the page-builder cost function
    (§1005) is 12 lines and is strictly simpler than line breaking because it commits
    greedily to the best-so-far break rather than doing a full DP.

12. **`\parshape` / `\hangindent`** (§847–§850). ~40 LOC. Only worth it if you want
    blockquote indentation or text wrap around a float. The `easy_line` optimisation is
    pure performance — skip it.

13. **`make_radical`** (§737) + **`var_delimiter`** (§706–§708). ~120 LOC.
    `var_delimiter` without `ext_tag` (i.e. only the size-chain walk) is easy and covers
    `\left(`…`\right)` up to the largest available variant.

### Traps — things that look necessary and are not

- **Full hyphenation** (Chapters 40–43, §891–§966, ~1000 LOC). This is `reconstitute`
  (§905–§918), the packed-trie pattern table (§920–§924), the exception table (§925), and
  the interaction between hyphenation and ligature reconstruction — which is genuinely the
  hairiest code in TeX, because inserting a hyphen can destroy and re-form ligatures across
  the break (§915, §916). **Do not.** For a PoC, either disable hyphenation entirely
  (set `pretolerance` high, run one pass) or insert `disc_node`s from a small list of
  explicit hyphenation points. If you later want real hyphenation, use `libhyphen`/`hunspell`
  patterns through an external call and just emit `disc_node`s — you never need TeX's trie.

- **`ext_tag` extensible-glyph assembly** (§546, §713, §714). Only cmex-style TFM fonts and
  OpenType `MATH`-table fonts have the recipes. A normal TrueType font has **no** data to
  drive this, and synthesising it (guessing which glyphs are the top/mid/bot/rep pieces of a
  brace) is not possible. **Skip it.** For oversized delimiters either (a) use the largest
  available `MathVariants` glyph and accept it, or (b) draw the delimiter as vector geometry
  yourself. TeX's own fallback when no variant is large enough is exactly "return the largest
  available variant" (§706: "And if no variant is large enough, it returns the largest
  available variant") — so degrading gracefully is sanctioned by the original.

- **The delta-node incremental width machinery in `try_break`** (§822–§824, §837, §843,
  §860, §861). It exists to make line breaking O(n) on a 1982 machine. It is where all the
  subtle bugs live. Recompute widths naively.

- **`\mathchoice` / `choice_node`** (§689, §731). Almost nothing uses it. Skip.

- **Insertions, marks, `\vadjust`, output routines, alignment (`\halign`)**
  (§140–§142, §980–§1028, Chapter 37). Each is a large subsystem serving a feature you
  almost certainly do not need for markdown. Markdown tables are better done as a
  purpose-built grid over `hpack`ed cells than via `\halign`'s unset-node machinery.

- **DVI output** (Chapters 31–32, except the glue-rendering logic in §625/§634). You are
  drawing to a GUI. Steal §625/§634 and §623/§632 (the coordinate walk) and throw away
  everything about `movement`, `push`/`pop`, and the byte encoding.

- **`glue_ratio` as `float`.** tex.web uses a `real` (§109) and explicitly says "the precise
  details of rounding, etc., in the glue calculation are not of critical importance for the
  consistency of results on different computers" — unlike `badness`, which it says *must* be
  bit-exact. So `double` is fine for `glue_set`, and you do not need TeX's fixed-point
  glue-ratio alternative.

### Minimal viable path, in build order

1. Node types + `hpack`/`vpack` + glue orders + the ship-out glue walk.
2. `badness` (verbatim).
3. `append_to_vlist` interline glue.
4. Greedy line breaking honouring §866/§868 legality, `hpack(line, width, exactly)`.
5. Synthesised sigma/xi font params from `OS/2` + `post` (§10.6 table).
6. `mlist_to_hlist` second pass + the 64-char spacing table + styles.
7. `make_op` (axis centring first, then display-size glyph, then §750/§751 limits).
8. `make_scripts`, `make_fraction`.
9. *Then*, if the greedy breaks bother you: swap in Knuth–Plass.

Items 1–4 are ~400 LOC and give you correct justified multi-line text. Items 5–8 are
~450 LOC and give you a correctly-typeset $\sum_{i=1}^{n}$.

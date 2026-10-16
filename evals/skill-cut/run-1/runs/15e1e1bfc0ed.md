### Intent
> Rewrite `principles/depth-over-breadth.md` in #633's reasoning-not-rules style. It should explain why depth beats extra scope and how to tell the two apart, keep its boundary and pairs, and keep jstack's form (first paragraph, relative links, card footer). The change is limited to the principle, its card and lines that quote it, and leaves `/deeper` untouched. `make check` and `jgauge test-slot -- make check` must pass, and the Result must hold a side by side with one #633 principle.

### Reviewers
- Reviewer A: 5 findings (1 warning, 4 nits)
- Reviewer B: 5 findings (2 warnings, 3 nits)
- Both independently raised the depth/breadth test contradiction, the duplicated instruments sentence and the hard-to-parse `/deeper` sentence. Each also raised points the other did not.

### Act On
- **The "how to tell" test contradicts the third question** (A1, B2). Line 15 says wider work "changes the outcome" measured against the "Done when". Line 13's third question ("What says it is done?") is itself a rewrite of the "Done when", since it adds a fail-then-pass test, a measured target or an outside judge. Applied literally, the test sends the principle's main move to "Noticed" as breadth, which is the opposite of what `/deeper` asks for.
  - This is the one new decision rule the rewrite adds, and it is the "how to tell" the Done-when line asks for.
  - Both reviewers found it, and both proposed the same fix: base the test on deliverables. Deeper work keeps what is delivered and changes where it starts, what it measures with and what judges it. Wider work adds a deliverable.
  - B2's side note belongs in the same fix. "Depth changes those three answers and nothing else. A plan that answers them by adding a deliverable…" reads as though adding a deliverable is a way to answer the questions.
- **"say why it is reasonable" changes the rule** (B1). The old rule was "say it is reasonable", a prompting move taken from Rieseberg's Depth move. `skills/deeper/SKILL.md` question 4 and `THIRD_PARTY.md:260` still state it that way.
  - The task was a change of style, not of rule, and `/deeper` is off limits, so the principle now disagrees with the skill it backs and the source it credits.
  - Only one reviewer raised it, but it names a concrete wording change and two places it now contradicts.
  - Fix: restore "say it is reasonable". If the reasoning style wants a reason, add a clause on why rather than turning the move into a duty to justify.

### Consider
- **Repeated points** (A2, B3). "Naming a method without the command… is still words" (line 7) repeats line 12, and B3 notes it also breaks the raw-data paragraph's chain of argument. A also flags overlap between lines 5 and 7.
  - At 710 words, the file is now the longest principle, against a #633 ceiling of about 475. Matching #633's style is the task.
  - Dropping the line-7 sentence is cheap and both reviewers want it. The line 5/7 trim is more a judgment call.
- **The `/deeper` sentence at line 17 is hard to parse** (A3, B4). Both reviewers flagged it. The real issue under the grammar is B4's point: the principle names three questions, the skill has four, and the sentence papers over the gap.
  - Either suggested rewording works. This is a one-line fix to the only sentence linking the principle to the skill.
- **The `**Why:**` label was dropped** (A5). The reviewer says all four #633 principles in this repo keep `**Why:**`, and some keep `**Pattern:**` or `**The test:**`.
  - The task's named form (first paragraph, relative links, card footer) doesn't list labels, so this isn't a clear Done-when miss.
  - Still, "reads like the four principles" is the bar, and the siblings visibly share this structure. Check against one sibling, then either restore the label or say in the Result why it was left out.

### Noted
- **The card was left unchanged** (A4). "Where" permits touching the card; it doesn't require it. The card's meaning still matches the body.
  - If it is kept, say in the Result that this was deliberate.
  - If it is reworded, regenerate `docs/jstack-explained.html` in the same change.
- **The side by side cannot be checked from the diff** (B5). This is correct and expected, because "Proves it" puts it in the Result. The Result must include it, since no test can check the style match.

### Dismissed
- None. Every finding names a concrete line and a concrete effect.

### Agreement Map
The two reviewers converged on the same three issues. The test contradiction is the one that matters, and they described it the same way and proposed the same fix. Their nits overlap almost exactly too, which suggests the prose problems are real rather than padding.

They diverged on rule fidelity and form:
- B alone caught the "say why" wording drift, which is the more serious of the unshared findings, because the task promised a change of style, not of rule.
- A alone compared form against the siblings (labels, word counts, card).

Taken together: the rewrite gets the reasoning tone right. However, its one new rule is wrong and one old rule drifted, and both are small textual fixes.

BUCKETS
A1: Act on
A2: Consider
A3: Consider
A4: Noted
A5: Consider
B1: Act on
B2: Act on
B3: Consider
B4: Consider
B5: Noted

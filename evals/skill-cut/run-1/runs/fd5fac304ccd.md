### Intent
> Rewrite `principles/depth-over-breadth.md` in #633's reasoning-not-rules style. It should explain why depth beats extra scope and how to tell the two apart, keep its boundary and its pairs, and stay in jstack's form (first paragraph, relative links, card footer). `make check` and `jgauge test-slot -- make check` must pass. The Result must include a side by side with one #633 principle. Where: the principle, its card, and any line that quotes it. Do not touch `/deeper`.

### Reviewers
- Reviewer A: 5 findings
- Reviewer B: 5 findings
- The reviewers converged on three issues (the depth test, the repeated instruments sentence, the `/deeper` sentence). Each also raised findings the other did not.

### Act On

1. **The depth/breadth test contradicts the principle's own third question** (A1, B2, merged). Line 15 says wider work "changes the outcome" as measured against the "Done when." Line 13's third question ("What says it is done?") tells the reader to rewrite the "Done when" with a failing-then-passing test, a measured target, or an outside judge. Read literally, the test files the principle's main depth move under breadth and sends it to "Noticed."
   - Why it matters: this is the one new decision rule the rewrite adds, and it is the "how to tell" the Done-when line asked for. A wrong rule here misroutes real work.
   - Both reviewers found it independently and proposed the same fix: base the test on deliverables. Deeper work keeps what is delivered and changes where it starts, what it measures with, and what judges it. Wider work adds a deliverable.
   - While fixing it, also reword "a plan that answers them by adding a deliverable" (B2). It currently reads as though adding a deliverable is a valid way to answer the three questions.

2. **"say why it is reasonable" changes the rule, not just the style** (B1). The source move is to state that an ambitious target is reasonable, which is a prompting technique. Adding "why" turns it into a duty to justify the target.
   - Why it matters: the principle now disagrees with `skills/deeper/SKILL.md` question 4, which this task may not touch, and with the credit at `THIRD_PARTY.md:260`. The task asked for a change of style, not of rule.
   - It was raised by one reviewer only, but the evidence is concrete and cross-referenced.
   - Fix: restore "and say it is reasonable". If the reasoning style needs a reason, add a clause explaining why the move works, rather than requiring the worker to justify the target.

### Consider

- **The instruments point is made twice, and line 7 breaks the raw-data paragraph** (A2, B3, merged). Line 7's "Naming a method without the command… is still words" repeats line 12, and it interrupts line 7's chain from digested input to self-judging.
  - The file grew from 544 to 710 words, the longest of the 25 principles. The #633 principles are at most 475 words, and the Done-when asks for this one to read like them.
  - Tradeoff: cutting the sentence costs one line and fixes both problems.
  - A's further cut at line 5 is less clear-cut. That sentence states the thesis and line 7 states its consequence, so leave line 5 to the author.
- **The `/deeper` sentence at line 17 is hard to parse** (A3, B4, merged). It hides the reconciliation of three questions with `/deeper`'s four inside a mid-sentence clause.
  - Both reviewers flagged it, and both suggested rewrites that work. B's version also explains why the first question stays a depth question.
  - Tradeoff: a cheap fix, but it is readability rather than correctness.
- **The card no longer echoes the body's wording** (A4). The card still lists the "X over Y" pairs, while the body now uses three questions. The meaning is the same.
  - Tradeoff: rewording the card also means regenerating `docs/jstack-explained.html:735`. Both are inside **Where**, so either is legitimate.
  - At minimum, the Result should say the card was kept on purpose.
- **The `**Why:**` label was dropped** (A5). A says the four #633 principles in this repo keep a `**Why:**` label, and most add `**Pattern:**` or `**The test:**`.
  - If that is true, "reads like the four principles of #633" points toward keeping the labels. Unlabelled prose is not obviously the form the siblings use.
  - Tradeoff: the side by side in the Result should settle this. Match whatever the sibling there actually shows.

### Noted
- **The side by side cannot be seen in the diff** (B5). Correct, and by design: the Proves-it line puts it in the Result, not the diff. It is a reminder that the Result must include it, not a defect in the change.

### Dismissed
- None. Every finding was either substantive or a fair, cheap readability point. Neither reviewer drifted into "I would have done it differently."

### Agreement Map
- **Agreement:** the reviewers independently converged on the depth-test contradiction, the duplicated instruments sentence, and the `/deeper` sentence. The contradiction is the strongest signal in this review, because it is the one new rule the task asked for.
- **Divergence:**
  - B alone caught the semantic drift in "say why it is reasonable." It is the subtler finding, since it needs knowledge of the source and of the skill.
  - A alone looked at form against the siblings: the card and the labels.
- **Pattern:** the prose is close. The two real problems both come from the rewrite changing meaning while it changed style. One is a new rule that contradicts the body, the other a rule silently altered. Fix those two, tighten the duplicates, and the change is shippable.

BUCKETS
A1: Act on
A2: Consider
A3: Consider
A4: Consider
A5: Consider
B1: Act on
B2: Act on
B3: Consider
B4: Consider
B5: Noted

### Intent
> Rewrite `principles/depth-over-breadth.md` in #633's reasoning-not-rules style: explain why depth beats extra scope and how to tell the two apart, rather than list rules. Keep its boundary and pairs, and keep jstack's form (first paragraph, relative links, card footer). The card and any line quoting the principle are in scope. `/deeper` is not. `make check` and `jgauge test-slot -- make check` must pass, and the Result must show a side by side with one #633 principle.

### Reviewers
- Reviewer A: 5 findings (1 warning, 4 nits)
- Reviewer B: 5 findings (2 warnings, 3 nits)
- They agreed on three points: the depth-or-breadth test, the repeated instruments sentence, and the `/deeper` sentence. Neither ran `make check`, so that "Done when" line is unconfirmed by this review.

### Act On
- **The depth-or-breadth test contradicts the third question** (A1, B2; line 15 against line 13). The test says wider work "changes the outcome" measured against "Done when". But question 3 tells the reader to rewrite "Done when": swap self-report for a failing-then-passing test, a measured target or an outside judge. Applied literally, the test files the main gain of depth under "Noticed" as breadth. It also contradicts `/deeper` answer 4. This is the one new decision rule the rewrite adds, and the task's "how to tell" depends on it. Both reviewers found it independently, with a concrete path. The fix: base the test on deliverables. Deeper work keeps the deliverables and changes where it starts, what it measures with, and what proves it. Wider work adds a deliverable. Also fix "A plan that answers them by adding a deliverable", which reads as though adding a deliverable is one way to answer the questions.
- **"say why it is reasonable" changes the rule** (B1; line 13). The task asked for a change of style, not of rule. The source move is to state an ambitious target as reasonable, not to justify it. `skills/deeper/SKILL.md` question 4 and the `THIRD_PARTY.md:260` credit both still describe the original rule. The principle now disagrees with the skill it backs and with the source it credits, and `/deeper` is off limits, so the principle is the side that has to move. Restore "and say it is reasonable". If the reasoning style needs a "why", add a clause that explains the effect: a target stated as reasonable sends the worker to the expert's tools instead of trimming the goal.

### Consider
- **The instruments point is made twice** (A2, B3; lines 7 and 12). Line 7's "Naming a method without the command… is still words" interrupts the raw-data argument, and line 12 says the same thing. A also points out the 5/7 overlap. The file is now the longest of the 25 principles (710 words against at most 475 for the #633 rewrites). The task is about style, so matching #633's economy is part of "reads like". The fix is cheap: drop the sentence at line 7. I recommend doing it.
- **The `/deeper` sentence at line 17 is hard to parse** (A3, B4). Its job is to reconcile three questions with four, and it does that badly. B's underlying point also stands: the first `/deeper` question is the one most open to breadth, and the sentence does not say how it stays deep. Either suggested rewording works. It is cheap, and it is the line that ties the principle to its skill.
- **The card no longer echoes the body** (A4; line 23 and `docs/jstack-explained.html:735`). The card's three "X over Y" phrases are still accurate but no longer appear in the body. The card and its quoted copy are both inside **Where**, so either fix is in scope:
  - reword the card around the three questions and regenerate the explained page, or
  - keep the card on purpose and say so in the Result.

  Leaving it silently unaddressed is the only wrong option.
- **The labels dropped** (A5; lines 7 and 19). A compared the rewrite against jstack's current copies of the four #633 principles. Those copies have not been caught up yet, so they may not be the right model. The target is upstream `pstack/` at e5136d8. Check the four #633 principles in the fresh clone. If they keep `**Why:**` or `**The test:**`, restore the labels. If they dropped them, this finding goes away.

### Noted
- **The side by side cannot be checked from the diff** (B5). This is correct, and the diff cannot show it by nature. The Result has to carry it, along with `make check` and the `jgauge test-slot` output. Prose with structural tests only is acceptable here.

### Dismissed
- None. Every finding is about a changed line or something in **Where**, and none amounts to "I'd have done it differently."

### Agreement Map
Both reviewers found the same warning, the line-15 test against line 13, on their own. That makes it the most reliable signal in the review, and it lands on the one new rule the rewrite introduces. They also agreed on the duplicate sentence and the `/deeper` sentence, which are both readability costs of the same kind. They diverged in what else they caught:
- B alone caught the change of meaning in "say why it is reasonable", by checking the principle against the skill and the credit. That is the most consequential single catch.
- A alone covered form: the card and the labels. The labels finding depends on comparing against upstream rather than jstack's stale copies.

The pattern is that the style rewrite reads well overall, but where it rephrased rules into reasoning it changed two rules by accident. Those two are the fixes. The rest is tightening.

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

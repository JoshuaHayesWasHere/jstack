### Intent
> Section 3 of the /deeper design: a step inside the home skill's brief writing, not a separate file. It runs on its own for research, perf, analysis and outcome briefs, and carries its own copy of the four questions. Answer 2 goes to the scout's `Read:` or the request's sources, answer 3 to the brief for the crew, and answer 4 to `Proves it:`. Mechanical fixes, docs changes and bug fixes with a known cause skip it. `/deeper` stays manual. `skills/deeper/`, the principle, `templates/brief.md` and the parser are untouched.

### Reviewers
- Reviewer A: 6 findings (4 warnings, 2 nits)
- Reviewer B: 7 findings (4 warnings, 3 nits)
- The two agreed independently on the three main defects: the template contradiction, the classification keyed on playbook names, and answers 3 and 4 being lost for a request. They differ on severity and on a few smaller points. Both answered the review skill's questions.

### Act On

**1. The step names brief lines that the template forbids or that nothing defines** (A1, B1)
- The step tells the home to write `Read:` and `Instruments:` on its own briefs.
- `templates/brief.md` says a home brief "leaves all five out", and `Read:` is one of the five.
- `Instruments:` exists nowhere else: not in the template, the scout skill, the crew skill or the parser.
- A scout following its own skill will drop answer 3. A home following the template will drop answer 2.
- The phrase "though the home wrote it" admits the clash rather than resolving it.
- Why it matters: the step's main output, putting the answers in the right lines, does not reliably happen. This fails the first "Done when" line in practice.
- Remedy within "Where": map answer 3 to a line the template already has (`Change:`, a Done-when item, or a plain sentence in the task body). If `Read:` and `Instruments:` really belong on home briefs, record in the Result that `templates/brief.md` and `skills/scout/SKILL.md` need a follow-up. Do not ship the contradiction silently.

**2. The step is decided by the playbook's name, not by the kind of work** (A2, B2, A3, A4, B3, merged)
- The case statement only looks at the kind of work when no playbook is picked. Otherwise the playbook's name decides.
- Concrete paths that go wrong:
  - `bug-fix` always skips, though that playbook is for reproducing and root-causing bugs whose cause is unknown. The principle exempts only a cause already proven.
  - Outcome work carrying `feature` or `autonomous-run` always skips, and research run under `swarm` or `arena` does too. The intent names outcome briefs explicitly.
  - On the scout-request path, both scout playbooks are in the run arm. Every request therefore gets the questions, even when it delivers a brief for a docs change or a known-cause fix. That breaks the second "Done when" line.
  - The ten names are a hand-kept copy. The test only checks one direction (each listed name is a file), so a new research playbook would skip silently and the tests would stay green.
- The test labels `bug-fix` as a "known bug" skip, which locks the mismatch in.
- Why it matters: this is the step's trigger, and it misfires both ways on real inputs.
- Remedy: key the case on the kind of work of the task being briefed, which the home can always state, for example `research|perf|analysis|outcome|known-cause-fix|mechanical|docs`. Let the playbook at most suggest a default.
- This one change fixes A2, A3 and B2, and removes the list that A4 and B3 worry about. The marker in the playbooks' front matter becomes unnecessary, and it was outside "Where" anyway.

### Consider

**3. A request that asks for no brief has nowhere to put answers 3 and 4** (A5, B4)
- The current text only covers a Deliver line that asks for the crewmate's brief, and packs the methods and the outside judge into a path bullet.
- The tradeoff is small. B's remedy fits the existing template: write 3 and 4 as `Questions:` items. That is one sentence, it also handles the report-only case, and it avoids overloading Deliver.
- Not a "Done when" failure, but cheap enough to do while rewording the step for item 1.

**4. No test checks that the lines the step names exist in the templates** (A6)
- The tests do execute the block, so they are not wording-only. But a test asserting that each destination line named in the echo appears in `templates/brief.md` or `templates/scout-request.md` would have caught item 1, and it will keep the fix honest.
- Low cost, high value once item 1 is fixed. The remaining question is whether you want that cross-file coupling in the tests.

**5. The extra skip condition lives in prose after the block** (B6)
- "Skip it too for a task whose Done when already names its data…" overrides the block's output after the fact.
- If item 2 turns the input into a kind of work, this condition can become one more kind, and the block prints the skip itself. Do it if it falls out of item 2 naturally. Otherwise it is acceptable as is.

**6. "The block under it" points about 90 lines away into another section** (B5)
- The home executes this text, so an ambiguous pointer is a real (small) risk.
- Naming the section costs one phrase.

### Noted
- B7: whether `make check` and `jgauge test-slot -- make check` passed is not shown by the diff, and the reviewer ran nothing. The Result must state both outcomes. The reviewers could not judge this.

### Dismissed
- None. Neither reviewer padded with style preferences. Even the nits point at concrete gaps in instructions the home has to execute.

### Agreement Map
- **Strong consensus on the two blockers.** Both reviewers traced the template contradiction (item 1) and the playbook-keyed trigger (item 2) to concrete paths: the grep for `Instruments`, and `picked='bug-fix'` printing the known-cause skip. Independent agreement on concrete paths is the strongest signal this review offers.
- **They converged on the same remedy for item 2.** Both proposed keying on the kind of work, so the fix is well understood and deletes code (the name list) rather than adding any.
- **They diverged on severity for the no-brief request** (A: nit, B: warning). It is a real gap but a one-sentence fix, so it sits in Consider.
- **Each saw something the other missed.**
  - A alone saw that the scout-request path inherits the wrong trigger (A3) and that a destination-check test would have caught item 1 (A6).
  - B alone flagged the prose-only skip, the dangling reference and the unverified checks.
- **The overall pattern:** the step's idea is sound and well scoped, but its two connection points are both wrong. Its input reads playbook names instead of the kind of work, and its output names lines the templates do not accept. Fix those two and the rest is polish.

```
BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Act on
A5: Consider
A6: Consider
B1: Act on
B2: Act on
B3: Act on
B4: Consider
B5: Consider
B6: Consider
B7: Noted
```

### Intent
> Task: "run the Size/Playbook/Proves-it and required-field checks before a brief is queued for the user, not after; and bind approval to the brief's content so cosmetic or wording-only edits keep the approval, while scope/risk changes still re-ask. Done when: an approved brief with a wording-only edit stays approved in a test, and an incomplete brief can't be queued." Merged in: topic #3 of [their] 13:06 list, "Verifiable approvals: an approval record holding the user's message id plus the brief's content hash, so other bots can check it and the user isn't asked again." Refined: "tie the user's approval to what a brief says, not its exact wording … Approval should survive harmless edits (typos, formatting, reordering) while still catching real changes to intent or scope." Today the checks run at launch in `src/jbus/dispatch.py`, so a bad brief is queued, approved, then gated. An approval is bound to the full-body `brief_sha`, so any edit voids it.

### Reviewers
- Reviewer A: 9 findings
- Reviewer B: 8 findings
- They agreed independently on four issues: template text passing `_filled`, negation slipping through the typo allowance, the check lists that can drift apart, and the string-suffix match in the CLI. Both answered the review's scope questions and tagged a principle on every finding.

### Act On

**1. `queue add` accepts the template's unedited Task, Done when, Pull request and Review** (A1, B1)
`_filled` only treats a value as template text when it starts with `<`. The template's own lines for these four fields start with `"` or `- `, or hold no `<` at all and use `|` alternatives. So an unedited copy of `templates/brief.md` passes those fields and reaches the user for a go.

This misses the Done-when line "refuses an incomplete brief". It also makes the new docs and the home skill's "not the template's own text" claim false. Both reviewers found it, and it rests on a concrete input: the shipped template itself.

Fix: strip quotes and list markers, then reuse `parse._template`. Add a test that runs `queue add` on the raw template and expects a fault for every required field.

**2. A contraction turns a negation into a "typo" that keeps the go** (A3, B2)
`meaning.py:94` deletes apostrophes, so `shouldn't` becomes `shouldnt`. That is within two edits of `should`, so "the gate should fire" and "the gate shouldn't fire" fingerprint as the same line. This is a concrete path that flips a Done-when line's meaning and keeps the user's approval, which is exactly the "real changes to intent" the task said must re-ask.

The two-edit rule is the spec's. Joining contractions is the author's own choice, and that choice is what puts negation inside the allowance.

Fix:
- Split `n't` into a `not` token, and make sure `not` is not in `FILLER`.
- Add a test that `should` changed to `shouldn't` re-asks.
- Extend the stated limit in `docs/jbus.md` and the PR body. Near antonyms (`include`/`exclude`, `import`/`export`) and swapped direction (fillers dropped and words sorted, so "move `a` to `b`" equals "move `b` to `a`") still keep the go under the spec's own rules. The task requires the limit to be stated, and these cases are not.

**3. The add check and the launch check are two lists kept in step only by convention** (A4, B3; A7's redundancies fold in here)
`faults` re-lists `designed`/`proof`/`sized`/`playbook` by hand beside dispatch's `CHECKS` and `ASKED`. The Done-when line "runs every check a launch runs" therefore holds only until someone adds a check to one list and not the other. The only parity test covers Design alone. This is the "rule in prose" pattern the review asks about, and it recreates the bug the task fixes.

Fix: keep one tuple of `(kind, check)` in `jbriefs.parse`. `faults` loops over it, and dispatch builds from it, keeping only the grandfathering (no `Proves it:` line, `shaped_since`). Both files are in Where. Doing this also removes the double `designed()` call and the discarded `_filled` result.

### Consider

**4. The home skill drops the new "its go does not hold" line** (A2)
On a successful add, the skill prints only `added: the row <slug>`, so the new go-void signal never reaches the home. The user is still re-asked later through the launch gate, so the outcome is correct but delayed. The fix is a few lines in a file already in Where, and without it the PR's new output has no consumer.

**5. `scope` is printed for other bots but its meaning differs from `holds`** (A5)
After a typo fix, `verify` shows a changed `scope` with `holds: true`. A bot that compares `scope` hashes, which is the use the docs suggest, would refuse a brief jbus launches. That cuts against the "other bots can check it" goal.

Tradeoff: the cheap fix is a docs sentence that `scope` equality is stricter than `holds`, and that bots should call `verify`. A fingerprint `method`/version field is cheap insurance against later `FILLER` changes, though it is not strictly needed yet. The case of a hand-edited `queue.json` tampering with `meaning` is weak, since anyone who can edit that file can edit anything in it.

**6. The CLI picks what to print by `endswith` on message constants** (A6, B5)
Both reviewers flagged it, and it breaks silently if the wording changes. Always printing the returned line is simpler and removes the branch. It is cheap, but it is not a correctness bug today.

**7. The PR says launch checks are unchanged, but `playbook` is now stricter** (A8)
Non-crewmate playbooks are now gated at launch, including on rows already approved. The task intends this, but the PR description should say so, given the Done-when line about older rows keeping working.

### Noted
- **A7:** `designed()` is called twice, a `_filled` result is discarded, and `ROUTING` is stripped twice. These are absorbed by Act On #3.
- **A9:** re-adding to change priority now requires a complete brief, which would void an old row's go. It is theoretical, since every row queued today is complete.
- **B4:** `approve` does not run `faults`, so an incomplete row queued before this change could still be put to the user. The launch backstop catches it and no such rows exist today. It is a one-line hardening if wanted.
- **B6:** greedy pairing in `_pairs` can re-ask when a valid pairing exists. It errs only toward asking again, so it is safe. The docstring slightly overstates the behaviour.
- **B7:** `src/jbus/asks.py` is outside the Where line. The queue verbs actually live there and `cli.py` is untouched, so the brief's Where line was imprecise, not the change.

### Dismissed
- **B8** (the PR description is unverifiable): Reviewer A did see the PR body and checked its limit section. That section's real gap is covered by Act On #2.

### Agreement Map
The two reviewers converged on the three substantive issues: template text passing, negation slipping through, and the duplicated check lists. Each of those has a concrete execution path, which makes them high-confidence. They also converged on one small fragility, the `endswith` match.

Reviewer A went further into how the change is used: the home skill dropping the line, `verify`'s semantics for other bots, and the PR text's accuracy. Reviewer B went further into edges of the mechanism: `approve`, pairing, and the Where line. Neither set of single-reviewer findings changes correctness.

The pattern suggests the core design (a fingerprint plus the full sha, with checks run at `add`) is sound. The three Act On items are all cases where the implementation narrowly misses its own stated guarantee, and each has a contained fix inside the Where line.

```
BUCKETS
A1: Act on
A2: Consider
A3: Act on
A4: Act on
A5: Consider
A6: Consider
A7: Noted
A8: Consider
A9: Noted
B1: Act on
B2: Act on
B3: Act on
B4: Noted
B5: Consider
B6: Noted
B7: Noted
B8: Dismissed
```

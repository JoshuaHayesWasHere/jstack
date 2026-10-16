### Intent
> Run the Proves it / Size / Playbook checks and the required-field checks of `templates/brief.md` at `jbus queue add`, so an incomplete brief is never queued; the launch keeps them as a backstop. Bind an approval to a deterministic meaning fingerprint over the scope-and-risk fields, so typos, formatting, reordering and edits to non-scope fields keep the go, while an added, removed or changed Done-when line, path, number or value re-asks. Store the fingerprint, the full `brief_sha` and the basis in the approval record and print them for other bots to verify. Old full-text-sha approvals keep working. Docs, the home skill and the PR description state the method and its known limit, and `make check` exits 0.

### Reviewers
- Reviewer A: 9 findings
- Reviewer B: 8 findings
- They independently agreed on the three most important issues: template text passing `_filled`, negation slipping through the typo allowance, and the two check lists. They also agreed on the `endswith` nit. Both answered the review skill's questions.

### Act On

1. **`queue add` accepts the template's unedited text for Task, Done when, Pull request and Review** (A1, B1)
   - `_filled` only rejects values that start with `<`. The template's quoted `Task`, its `- <a check>` list item, and the `x | y` choices for Pull request and Review all pass.
   - This breaks the main Done-when line ("an incomplete brief can't be queued"). It also makes the new docs and home-skill text untrue.
   - Fix:
     - Strip quotes and list markers before the check.
     - Reuse `parse._template`.
     - Add a test that runs `queue add` on the raw `templates/brief.md` and expects a fault per required field.

2. **A contraction turns a negation into a typo, so the go survives "should" → "shouldn't"** (A3, B2)
   - Deleting the apostrophe was the author's choice, not the spec's. It puts `shouldn't` within two edits of `should`.
   - Separately, real antonym pairs within two edits keep the go: `include`/`exclude`, `import`/`export`. So do direction swaps hidden by filler-dropping plus sorting ("move a to b").
   - The task requires the docs and the PR to state the known limit, and those cases are absent.
   - Fix:
     - Emit `n't` as a separate `not` token.
     - Add a test that `should` → `shouldn't` re-asks.
     - Add antonyms-within-two-edits and direction swaps to the limit section in `docs/jbus.md`, the PR body and the module docstring.

3. **The add-time and launch-time checks are two hand-kept lists** (A4, B3)
   - The task is "`queue add` runs every check a launch runs". Today that holds only by convention. A check added to `CHECKS`/`ASKED` later would gate at launch and never at add, which is the exact bug this PR fixes.
   - The only parity test covers Design alone.
   - Fix:
     - Keep one `(kind, check)` tuple in `jbriefs.parse`.
     - Have `faults` iterate it after the required-field pass.
     - Have `dispatch` derive `CHECKS`/`ASKED` from it, keeping only its grandfathering (no `Proves it:`, `shaped_since`).
   - This also removes the duplicate `designed` call and the discarded `_filled` result (A7).

4. **The home skill drops the "its go does not hold" line on a successful add** (A2)
   - The home captures `$said` but prints it only on failure. A scope change therefore looks like a plain success, and the user is re-asked only later, when a launch gates "brief changed after approval".
   - The re-ask is the user-facing half of this task, and the skill is in Where.
   - Fix: on success, surface `$said` when the go is void, and say the home then puts the brief to the user again.
   - This pairs naturally with the fix in Consider #1.

### Consider

1. **`asks.py` decides what to print by matching the end of the returned string** (A6, B5)
   - Reworded constants would silently break both this check and the home's detection in Act On #4.
   - Returning the go state as data, or always printing the line, costs little. It is fragile rather than broken today, but cheap to fix while touching Act On #4.

2. **`scope` and `holds` can disagree, and `scope` is never checked against `meaning`** (A5)
   - After a typo fix, `verify` shows a different `scope` with `holds: true`. A bot comparing hashes, the use the docs give, would refuse a brief jbus would launch. That undercuts "other bots can check it".
   - Possible fixes:
     - State in the docs that `scope` equality is stricter than `holds`.
     - Better, have `verify` expose `holds` as the answer.
   - A fingerprint method/version field is cheap insurance against future `FILLER` changes.
   - The tamper check (`scope == fingerprint(meaning)`) is lower value, since anyone editing `queue.json` can edit both.

3. **The PR description says the launch checks are unchanged, but `playbook` now rejects non-crewmate playbooks at launch too** (A8)
   - The behavior is intended. The description should say so, since a row approved since `shaped_since` with such a playbook would newly gate.
   - This is a one-line text fix.

### Noted
- **Redundancies in `faults` and `queue.fingerprint`** (A7): the `faults` ones disappear with Act On #3. The double routing strip is harmless.
- **Re-prioritising an old, incomplete row now needs a full brief, which voids its go** (A9): all four rows queued today are complete, so this is theoretical.
- **`approve` doesn't run `faults`** (B4): only rows queued before this change could hit it, the launch backstop still catches them, and today's rows are complete.
- **Greedy pairing in `_pairs`** (B6): it errs only toward re-asking, so it is safe. Worth a docstring tweak at most.

### Dismissed
- **`src/jbus/asks.py` is outside Where** (B7): the queue verbs live in `asks.py`, and `cli.py` doesn't hold them. The Where line named the wrong module, and the change put the code where it belongs.
- **The PR description couldn't be checked** (B8): Reviewer A did read the PR body (see A3, A8). Its real gaps are captured under Act On #2 and Consider #3.

### Agreement Map
- **Agreed:** both reviewers independently found the same three substantive issues: template text passing `_filled`, contraction negation, and dual check lists. They also shared the `endswith` nit. That consensus on concrete execution paths is why those items lead the verdict.
- **Diverged on lifecycle:**
  - A looked further along the user-facing flow and caught the home skill discarding the void-go line and the stricter-than-`holds` `scope` hash. Both bear directly on "scope changes still re-ask" and "other bots can verify".
  - B looked at edges of old rows (`approve`, greedy pairing) and the Where line. These are real but low-impact.
- **Overall:** neither reviewer padded with style nits. The fingerprint design is sound. The fixes are a tightened `_filled`, one tokenizer change plus docs, a single shared check tuple, and surfacing the void-go line. After those, this ships.

BUCKETS
A1: Act on
A2: Act on
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
B7: Dismissed
B8: Dismissed

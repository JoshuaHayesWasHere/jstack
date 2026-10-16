### Intent
> (Condensed from the brief; the user's quoted words are under Task there.) `jbus queue add` must run every check a launch runs: Proves it, Size, a real crewmate Playbook, and the required fields of `templates/brief.md`. It must refuse an incomplete brief with one line per fault and queue nothing, and the launch keeps its checks as a backstop. An approval binds to a deterministic, model-free meaning fingerprint over the scope and risk fields, with typo tolerance (words of five or more letters, within two edits). Paths, numbers, URLs and key values are kept exact. Typos, formatting, reordering and edits to non-scope fields keep the go, and real scope changes re-ask. The method and its known limit are stated in the PR and `docs/jbus.md`. The record holds the scope fingerprint, the full `brief_sha` and the basis, and `show --json`/`verify` prints them for other bots. Old full-sha rows keep working. Tests cover each case, and `make check` exits 0.

### Reviewers
- Reviewer A: 9 findings
- Reviewer B: 8 findings
- They agreed independently on the three main issues: template text passes `_filled`, negation slips through the typo allowance, and the add and launch check lists are kept apart. The review skill's questions were asked.

### Act On
1. **`queue add` accepts the template's own text for Task, Done when, Pull request and Review** (A1, B1). `_filled` (`src/jbriefs/parse.py:355`) only treats a value as template text when it starts with `<`. The template's own `"<…>"`, `- <a check>`, and `a | b` lines all pass. A brief copied straight from the template therefore reaches the user for a go. That fails the core Done-when line "refuses an incomplete brief". The docs and the home skill also claim more than the code does.
   - Fix: strip quotes and list markers, then reuse `_template`.
   - Test: run `queue add` on the unedited `templates/brief.md` and expect a fault for every required field.
   - Both reviewers found this on a concrete path, so it is the clearest blocker.

2. **A negation keeps the go** (A3, B2). The two-edit rule is the spec's. Deleting the apostrophe (`meaning.py:94`) is the author's own choice, and it puts `shouldn't` within two edits of `should`. So "should fire" changed to "shouldn't fire" in Done when keeps the approval. That flips intent in a field that carries scope.
   - Fix: tokenise `n't` as `not`.
   - Test: `should` changed to `shouldn't` re-asks.
   - Docs: the spec's own rules produce other cases (`include`/`exclude`, swapped direction once fillers are dropped and words sorted). These are not code changes, but the Done-when line requires the known limit to be stated, and today it names only `must`/`may` and `files`/`fixes`. Add them to `docs/jbus.md` and the PR.

3. **The add checks and the launch checks are two hand-kept lists** (A4, B3). The task exists because checks ran in the wrong place. `faults` re-lists `CHECKS` and `ASKED` by hand, and only a docstring keeps them in step. A check added to dispatch later would silently gate only at launch, and the parity test covers only Design.
   - Fix: one tuple of checks in `jbriefs.parse`. `faults` loops over it after the required-field pass, and dispatch builds from it, keeping only the grandfathering.
   - This also removes the redundancies in A7.

4. **The home skill drops the "its go does not hold" line** (A2). `skills/home/SKILL.md:632` prints `$said` only when the command fails. A scope change at re-add therefore looks like a plain success to the home, and the user is only re-asked later, through a launch gate. That undercuts the "check before queued for the user" goal. The file is in Where.
   - Fix: on success, surface the GO line and say that the home re-puts the brief.

5. **The PR description says the launch checks are unchanged, but they are not** (A8). `parse.playbook` now refuses non-crewmate playbooks, and `dispatch.ASKED` calls it. So rows approved since `shaped_since` with e.g. `autopilot-full` now gate at launch. The change is intended, but the PR must state it, because it changes behaviour for existing approved rows.
   - Fix: a one-paragraph edit to the PR description.

### Consider
- **`scope` versus `holds`** (A5). `verify` can print a different `scope` with `holds: true` after a typo fix, so a bot comparing hashes, as the docs suggest, would refuse a brief jbus launches. That bears directly on "another bot can check".
  - At minimum, document that `scope` equality is stricter than `holds`.
  - A method or version field is cheap now and costly later.
  - Checking `scope` against the stored `meaning` in `approved_text` guards against hand-edits only, so it is low value.
- **The CLI matches the end of a string** (A6, B5). `asks.py:107` decides whether to print by matching the tail of the returned message. It is brittle but works today. If the fix for item 4 has the CLI always print the returned line, this goes away for free.

### Noted
- Redundant `designed()` call, discarded `_filled` result for Size, and `ROUTING` dropped twice (A7). These are covered by the fix for item 3.
- Re-prioritising an old, incomplete row requires a full brief, which costs its go (A9). This is theoretical: every row queued today has all the fields.
- `approve` does not run `faults` (B4). The task scopes the check to `queue add`, and the launch backstop catches pre-change rows.
- Greedy pairing in `_pairs` can re-ask when a valid matching exists (B6). It only errs toward re-asking, which is safe. The docstring could say so.

### Dismissed
- **`src/jbus/asks.py` is outside Where** (B7). The queue verbs live in `asks.py`, and `cli.py` is untouched. The Where line named the CLI layer imprecisely, and the change put the code in its canonical place.
- **The PR description cannot be checked** (B8). Reviewer A read the PR body (A3, A8) and confirmed it states the method. Its remaining gaps are covered by items 2 and 5 above.

### Agreement Map
- **Agreed:** both reviewers converged independently on the three substantive issues: the template-text gap, negation passing the typo allowance, and the duplicated check lists. Each is a concrete path, not a hypothetical. That consensus is strong evidence the core design is sound and these are the real gaps.
- **A only:** Reviewer A alone traced the change past the Python, into the home skill's shell block (A2) and the PR body (A8). Both are integration seams a diff-only reading misses.
- **B only:** Reviewer B's unique findings were edges (B4, B6) or scope bookkeeping (B7, B8), and none of them holds up as a blocker.
- **Overall:** the fingerprint machinery is sound. The weak points are where it meets the template, the launch path and the home skill.

BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Act on
A5: Consider
A6: Consider
A7: Noted
A8: Act on
A9: Noted
B1: Act on
B2: Act on
B3: Act on
B4: Noted
B5: Consider
B6: Noted
B7: Dismissed
B8: Dismissed

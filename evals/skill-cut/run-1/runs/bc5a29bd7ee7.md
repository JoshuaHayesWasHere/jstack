### Intent
> P7 of the pstack-drift audit, the optional items under the user's approval of "every other upstream update." There are two parts.
>
> 1. **Merge result.** Answer from the code whether jmerge's "fails over today's main" check runs the checks on the merge result. If it does not, make it re-check when main has changed a caller or a dependency of the PR's files, or a lockfile. Add a test.
> 2. **Effort.** Read from T3's own tool schema whether a T3 launch takes an effort setting. Record the decision in THIRD_PARTY.md. Nothing may go above medium.
>
> Both `make check` and `jgauge test-slot -- make check` must pass.

### Reviewers
- Reviewer A: 7 findings
- Reviewer B: 5 findings
- The reviewers agreed independently on two findings: the effort shape is unproven (A1/B4), and bare-name imports between test files are missed (A4/B2). Both answered the review skill's questions.

### Act On

1. **The effort shape is asserted, not proven, so a wrong shape fails silently into `high`** (A1, B4). The repo's T3 fixture types `options` as `anyOf [{}, null]`, so the schema test accepts any shape. "Proves it" asks for the T3 schema to be quoted, and that schema does not contain this answer. If T3 ignores the shape, every Claude role launches at `high`, which breaks the user's hard rule with no signal.
   - Fix: cite the real source of the shape (T3's provider code or a captured accepted launch) and pin it in a fixture that fails on a different shape.
   - If no source can be found, record it as a `jbus gate`, as the Decisions line allows.

2. **The "never above medium" claim covers Codex and Grok without checking them** (A2). THIRD_PARTY.md and the docstring say the rule holds for every role the map names. Codex and Grok lines send no effort, and their T3 defaults were never read.
   - The PR's own reasoning for Claude (T3's default is above medium) shows the risk is real.
   - Cheapest fix inside Where: narrow the wording to Claude lines and gate the Codex/Grok question. Capping them is fine too if their schema shows an option.

3. **An unreadable head makes the dependency check pass** (A3). When `git show <head>:<path>` fails, `related` reads each of the PR's files as empty, so a dependency changed on main is never seen.
   - This check exists to block merges. Every other git failure in jmerge blocks; this one passes.
   - Fix: check `cat-file -e` and fetch `refs/pull/<n>/head` the way the existing code at ~cli.py:1078 does. If the head is still missing, return a stale reason. Add a test.

4. **Bare-name sibling imports in `tests/` are invisible** (A4, B2). `modules()` gives only dotted paths, but this repo's tests import each other by bare name, including the PR's own `test_jmerge_callers.py` (`from test_jmerge_fresh import Kitchen ...`).
   - Main changing `Kitchen` while a PR changes a test that uses it is exactly the "main changed a dependency" case, and it stays green.
   - Fix: also name files in a pytest import root by their bare module name, and add a test.

5. **A module renamed by the PR misses callers main added under the old name** (B1). `left` reaches `stale_paths` but not `related`. GitHub lists only the new path, so `modules(<old path>)` is never compared.
   - This is the core #613 scenario: the PR moves `core.py`, main adds `from pkg import core`, and the PR merges onto a broken import.
   - The fix is small: pass `left` into `related` with empty text. Add a Kitchen test that does a `git mv`.

### Consider

- **Path mentions in prose count as dependencies** (B3). This fails closed, but any PR touching THIRD_PARTY.md or `docs/jmerge.md` goes stale whenever main touches a path they mention. That forces a rebase for guarded PRs or a full `make check` rerun elsewhere.
  - Restricting path matching to files the check executes (code, Makefile, CI config) would cut the noise.
  - Tradeoff: it adds a file-kind rule, against wasted reruns. It is worth doing if this PR's own docs trip it in practice.
- **Three doc files are outside the Where line** (A7): `docs/configuration.md`, `docs/jmerge.md`, `docs/jroles.md`.
  - The edits describe the new behaviour, so keeping them is probably right. The brief still counts each one.
  - Either keep them and name them under "Noticed" in the Result, or revert them and leave the doc update for later. It is the home's call, not a bug.

### Noted

- **Path matching is too loose** (A5). The plain-substring match and the `endswith("conftest.py")` suffix rule can over-match. Both fail closed, and the cost is an occasional extra recheck. A basename check is a one-line fix if B3's change touches `uses` anyway.
- **Per-file subprocesses and pair-wise parses** (A6, B5). `related` starts one `git show` per file, and `ast.parse` runs once per pair of files. Nothing shows it nearing the 300 s jbus limit. It becomes worth fixing once a pass is measured as slow; `git cat-file --batch` and parse-once are the remedies.

### Dismissed

None. Every finding is about a changed line and points to something concrete. Neither reviewer padded with style nits.

### Agreement Map

The reviewers split cleanly by area and converged on the two findings that matter most.

- **Where they agreed:** the effort shape rests on a schema that permits anything, and the import heuristic is tuned to `src/`. Both are consensus findings, and both are cases where the PR's own artifacts disprove its claim (the fixture, and its own test imports).
- **Where they diverged:** each found a different fail-open path in `related`.
  - A traced the unreadable-head path (A3).
  - B traced the rename path (B1).
  - B also saw the opposite failure mode, over-matching on prose (B3).

Together these show that the check is a heuristic over text. It leaks in both directions, and the leaks that let a merge through are the ones to close now.

The effort half has the same shape: the decision is plausibly right but is not yet proven from T3's schema, and that proof is the one thing the user's rule depends on.

```
BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Act on
A5: Noted
A6: Noted
A7: Consider
B1: Act on
B2: Act on
B3: Consider
B4: Act on
B5: Noted
```

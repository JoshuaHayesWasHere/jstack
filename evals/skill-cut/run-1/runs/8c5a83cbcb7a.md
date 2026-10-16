### Intent
> Task: the audit's P6. Once a crewmate has written `fixed and green`, a third rebase forced by main is not made. The crewmate instead writes one stop line in its Result and pipes a gate, and jbus surfaces the pull request as waiting. The count is kept where jbus or jmerge can read it. A test drives three rebases and finds the stop on the third. `make check` and `jgauge test-slot -- make check` pass. Where: `skills/crew/SKILL.md` ("A conflict"), `src/jmerge/` or `src/jbus/`, the tests. Do not touch how a rebase is pushed.

### Reviewers
- Reviewer A: 6 findings (3 warnings, 3 nits)
- Reviewer B: 5 findings (4 warnings, 1 nit)
- Both agreed on the jbus mapping and on the `Fixed:` proxy. Each found correctness gaps the other missed. Both worked through the review skill's questions.

### Act On

**1. The held pull request shows as waiting on its crewmate instead of on the user.** (A1, B1)
- `held a third rebase` maps to the `rebase` step (`src/jbus/merge.py:97`), which `work.py:287` draws as "Rebase, its crewmate".
- The crewmate is forbidden to act until a `Rebase hold lifted:` line exists, so the row names the wrong party.
- Once the gate is answered or never parked, the row is wrong for good.
- The skill's own text (SKILL.md:118) promises "waiting on the user".
- Fix: map the reason to the `hold` step and change `tests/test_jbus_merge.py:288` to `"REBASE_HELD": "hold"`. This is a one-line change inside **Where**.

**2. The count reads the whole brief instead of the last Result.** (B2)
- The awk (SKILL.md:396-399) counts `Fixed:` and `Rebased after fixed:` lines across every round.
- SKILL.md:159 says every block reads the last result.
- Concrete path: two rebases in round one, then a follow-up round with a new `Fixed:`. The first conflict of the new round is held at once.
- Fix: reset the counters at each `/^## Result/`.
- Check that `ready.rebase_held` applies the same scope, so the block and jmerge agree.

**3. Running the block again on a held head parks another gate.** (A3)
- The block writes the hold line only once, but prints `hold:` on every run, and the prose says to park a gate on `hold`.
- `mainmoved.py` wakes red pull requests on each main commit, and a held pull request is often red, so the same question gets gated again and again.
- This is the "run twice" case from question 4.
- Fix: print a distinct word such as `held:` when the line was already there, and gate only on the first `hold:`.
- While making this change, de-dup against the last hold or lift line, as `rebase_held` does. That also resolves B5.

**4. The test skips the two paths that matter most.** (A5, B4)
- Every simulated move of main touches an unrelated file, so no rebase ever stops on a conflict. This is a section called "A conflict", so the `counted` call on the stopped path (SKILL.md:443) never runs.
- jmerge's `waits()` ordering in `cli.py:703` is never exercised. The test calls `ready.rebase_held` directly, so moving or dropping that line breaks nothing.
- Fix:
  - Add one run where main changes the branch's own file.
  - Add one assertion through `waits()` that a pull request at the held head reports `REBASE_HELD`.

### Consider

**5. The cap starts at `Fixed:`, not at "fixed and green".** (A2, B3)
- This is a real deviation from the first "Done when" line: `Fixed:` is written before any check is green, including `Fixed: none needed`.
- The tradeoff: the PR explains that `fixed and green` is only sent to the home, never written. Making the real state readable means adding a new marker to the brief, plus a writer for it. That is more than size S.
- The deviation errs toward holding early, which is safe but can stall a pull request that never went green.
- At minimum, state the deviation in the PR so the user can rule on it. Better, write a `Green:` line when the crewmate sends `fixed and green`, and count from that.

**6. The hold is recorded at the local HEAD, but jmerge reads the pushed head.** (A4)
- Concrete only if the push after the second rebase was refused and main then moved again.
- The fix is trivial: use the `pushed` head the block already has from `gh pr view`.
- It is cheap enough to take along with item 3.

### Noted
- **A6:** `run(about, home)` silently switches the slug to `"alpha"`. This is fragile test plumbing, but it is correct for the only caller today.
- **B5:** the de-dup checks for any hold line ever written at that head, not the current one. The scenario (lifted, then back at exactly the same head) is contrived, and it disappears if item 3 de-dups against the last hold or lift line.

### Dismissed
None. Every finding pointed at a concrete path or a real gap in the "Done when" lines. Neither reviewer padded with style nits.

### Agreement Map
- Both reviewers found the two issues that read straight off the task text: which step jbus maps the reason to, and `Fixed:` standing in for "fixed and green". Those are the safest calls.
- Each also found a different state-dependent bug: A found the repeat on rerun, B found the scope across rounds. Neither saw the other's.
- Both bugs come from the block reading brief history loosely: the whole file, any matching line, every run.
- That points to one structural fix: read only the last Result, and treat the last hold or lift line as the state. This covers items 2 and 3 and B5 together.
- On testing they converged: the block is executed for real, which is good, but the conflict path and jmerge's own path to the hold are not.

BUCKETS
A1: Act on
A2: Consider
A3: Act on
A4: Consider
A5: Act on
A6: Noted
B1: Act on
B2: Act on
B3: Consider
B4: Act on
B5: Noted

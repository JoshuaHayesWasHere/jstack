### Intent
> Task: the audit's P6. Once a crewmate has written `fixed and green`, a third rebase forced by main is not made. The crewmate writes one stop line in its Result and pipes a gate, and jbus surfaces the pull request as waiting. The count is kept where jbus or jmerge can read it. A test drives three rebases and finds the stop on the third. `make check` and `jgauge test-slot -- make check` pass. Where: `skills/crew/SKILL.md` ("A conflict"), `src/jmerge/` or `src/jbus/`, and the tests. Do not touch how a rebase is pushed.

### Reviewers
- Reviewer A: 6 findings
- Reviewer B: 5 findings
- Both reviewers answered the review skill's questions. They agreed on three issues: the jbus step mapping, the `Fixed:` proxy, and the test's coverage gaps. Each also found things the other missed.

### Act On

**1. jbus shows the held pull request as waiting on its crewmate, not on the user** (A1, B1)
`REBASE_HELD` maps to the `rebase` step (`src/jbus/merge.py:97`), which `work.py:287` draws as "Rebase, its crewmate". After the hold, the crewmate is not allowed to act; only the user's answer clears it. The PR's own text (SKILL.md:118) says jbus lists it as waiting on the user. A1 adds the decisive detail: once the gate is answered or never parked, the row reads "its crewmate" for good. The test table at `tests/test_jbus_merge.py:288` locks in the wrong mapping.
- Why it matters: it is the "jbus surfaces it as waiting" line of Done when, and as written it surfaces the wrong waiter.
- Fix: move `held a third rebase` to the `hold` rule, as with `NOT_UPHELD` and `UNRULED_DROPS`, and change the test to `"REBASE_HELD": "hold"`.

**2. Running the block again on a held head parks a duplicate gate** (A3)
The block writes the hold line only once, but it prints `hold:` on every run, and the prose says to park a gate on `hold`. `mainmoved.py` wakes red pull requests on every main commit, and a held pull request is often red. Each wake therefore asks the user the same question again.
- Why it matters: this is a concrete run-twice failure, and the fix is cheap.
- Fix: print a distinct word (e.g. `held:`) when the line already exists, and park the gate only on the first `hold:`.

**3. The count reads the whole brief, not the last Result** (B2)
SKILL.md:159 makes it a rule that every block reads the last result. This awk counts `Fixed:` and `Rebased after fixed:` lines anywhere in the file. After a follow-up round, the old rebases still count, so the first conflict of the new round is held at once.
- Why it matters: it breaks the skill's own stated convention, and the path to failure is concrete: a steer leads to a follow-up round.
- Fix: reset the counters on `/^## Result/`.

**4. The test skips the conflict path and jmerge's `waits()`** (A5, B4)
The proving test does run the shell block, which is right. But every move of main touches a file the branch does not change, so no rebase ever stops. That leaves two paths unexecuted:
- The `counted` call in the stopped-rebase `elif` branch. Conflicts are exactly what this section is about.
- The new `rebase_held` call placed in `waits()` (`cli.py:703`).

Deleting either one would pass the suite.
- Fix: add one run where main changes the branch's own file, and assert that the `Rebased after fixed:` line is written. Add one assertion through `waits()` (or jmerge's `wait` line) that returns `REBASE_HELD` at the held head.

### Consider

**5. `Fixed:` stands in for "fixed and green"** (A2, B3)
Both reviewers flag this, and they are right that it is a proxy. `Fixed:` is written before any check passes, and `Fixed: none needed` starts the count too.
- The tradeoff: `fixed and green` is sent to the home, never written to the brief, so the literal condition cannot be read as things stand. Making it readable means adding a new marker that a crewmate writes when the head turns green. That adds scope.
- The error runs in the safe direction: it holds earlier, and the hold raises a gate for the user rather than doing anything destructive.
- Recommendation: if the design doc's "#613 in detail" doesn't demand green specifically, keep the proxy and state the deviation from Done when explicitly in the PR and in the skill prose. Otherwise, add the marker.

**6. The hold is recorded at the local HEAD, but jmerge compares GitHub's head** (A4)
This only matters after a refused push followed by another move of main, which is narrow. The fix is a one-word change: use the `pushed` head the block already has. It's cheap enough to take.

**7. The de-dup check and `rebase_held` disagree on which hold is current** (B5)
The trigger path is convoluted: a hold is lifted, a rebase stops, and an abort lands back on exactly the held head. But this is the same lines as item 2. Aligning the de-dup with `rebase_held`'s "last hold-or-lift line" rule costs almost nothing while that code is open, so fold it into that fix rather than treating it separately.

### Noted
- **A6**: the `run(about, home)` test helper also switches the slug. This is test-helper coupling with a single caller today. It's fine for now and worth fixing only if a second brief name shows up.

### Dismissed
None. Every finding pointed at a real changed line and a real path, and neither reviewer padded with style nits.

### Agreement Map
**Where they agreed:**
- Both independently caught the jbus step mapping and pinned the same lines, a strong consensus signal for the top Act On item.
- Both caught the `Fixed:` proxy. That one is real, but it is a spec-versus-feasibility question rather than a bug.
- Both saw the test as executing, which is good, but partial. B identified the more important gap, the untested conflict path; A identified the `waits()` gap, which B also named.

**Where they diverged:**
- A's unique finds are about idempotency and pushed-versus-local state (A3, A4).
- B's unique finds are about reading the brief's history: the last Result (B2) and the last hold line (B5).

Those are complementary blind spots, not disagreements. The pattern says the core mechanism is sound, and the weaknesses sit at the edges of state that persists across runs and rounds. Fix items 1–4, fold in 6 and 7 cheaply, and decide on 5 explicitly.

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
B5: Consider

### Intent
> Task: sections 1, 2, 5 and 6 of the /deeper design (Felix Rieseberg's "four types of ambition"). It covers four parts:
> - a manual-only `skills/deeper/` that answers the four questions and gives a rewritten prompt, with a non-blocking `jbus gate` when a home runs it;
> - the 25th principle, `depth-over-breadth`, which jdrift lists as a jstack source, with every count saying 25;
> - the `THIRD_PARTY.md` credit;
> - a blind, rerunnable eval in `evals/deeper/` over about 10 past briefs. It scores raw sources, instruments and outside proof, and its Result says plainly whether /deeper won. "If it did not, say so: that is a finding, not a reason to tune the eval."
>
> It is done when `make check` and `jgauge test-slot -- make check` pass.

### Reviewers
- Reviewer A: 5 findings
- Reviewer B: 8 findings
- Neither reviewer reported an unmet "Done when" line in the skill, the principle, jdrift, `install.sh` or the credit. Every finding of substance is about the eval and what its README claims.

### Act On

**1. The eval's "won" verdict is not supported by its own measures** (A1, B1, merged)
- **What A found:** A rescored the committed run-2 briefs without the backtick branch of `OUTSIDE` (`evals/deeper/score.py`). The whole rise in "outside", from 0.57 to 0.75, disappears: plain scores 0.34 and deeper 0.33.
- **What B found:** B shows that eight of ten cases flipped sign on "outside" between run 1 and run 2. The only change between the runs was the skill's output format, a fence that became a block quote. So "lost on none" (the 8/2 split) is noise from a proxy that rewards inline code. The skill itself tells writers to use inline code, since it asks them to name things by path and command.
- **Why it matters:** The intent asks for exactly one honest sentence here: did /deeper win. The README states "won" from run 2 alone, when its own rule says only what both runs agree on counts. That is the outcome the task warned against, even though the skill changed and not the eval.
- **The fix needs no new model calls:**
  - In `OUTSIDE`, make a backtick span count only when it holds a command that is run, or drop that branch.
  - Rescore both committed runs.
  - Restate the Result: won on raw and instruments in both runs; proof outside not shown. If that means the rule says /deeper did not win, say so.
- **A caution:** Changing a measure after seeing results is itself a form of tuning. The README should therefore say what changed and why, and show the old and new numbers side by side.

**2. The "raw sources" measure counts the skill's own example list, and the README claims it doesn't** (A2, B2)
- Seven of the twelve `RAW` kinds match answer 2 of `skills/deeper/SKILL.md` almost word for word.
- Instruments have a `beyond` control. Raw has none.
- Despite that, `evals/deeper/README.md` ("What holds") says the raw effect holds "not only by copying the skill's own examples".
- Both reviewers found this independently, and it bears on the one result the eval still claims.
- **Fix:** Add a raw `beyond` that leaves out the skill's listed kinds, then rescore the committed briefs. Or narrow the sentence to instruments.

**3. The one documented command deletes the committed results before it can fail** (A3, B3)
- `write()` in `evals/deeper/eval.py` runs `rmtree` on `runs/` and `deeper/` before any of the 60 `claude -p` calls. `key.json` is written only at the end.
- Any of these leaves a partial `runs/`, a stale key, and a `report` that refuses to run:
  - a missing `claude`,
  - a non-zero exit,
  - an empty output,
  - a missing block quote,
  - a 900 s timeout.
- Nothing can resume. This is the "crashed halfway" case, and it sits on the path the intent calls "rerunnable by one command".
- **Fix:** Write into a temporary directory and swap it in once the key is written. At minimum, check `shutil.which("claude")` before deleting anything.

**4. Redaction fails open** (B4)
- `_private` reads jleak patterns from `~/.config` only, while `jleak.cli` respects `XDG_CONFIG_HOME`.
- On `jleak.Missing` it quietly returns `()`. Cases, briefs and model outputs built from private task history are then written, unredacted, into a repo meant to be public.
- Only one reviewer raised it, but it is a security finding with a concrete path. A silent fallback to "no patterns" is wrong whatever the user's environment is.
- **Fix:** Resolve the path as `jleak.cli` does, and make `cases` and `write` fail when the patterns don't load.

### Consider

- **The "Not held" column counts a phrase** (A4). It counts every "does not hold" anywhere in a brief and misses "did not hold" and "doesn't hold". The README's "seven of the ten" claim about outcomes is read off it.
  - Limiting the search to the Result section and matching the tense variants is cheap, and this is the "how it turned out" part of the intent.
  - The tradeoff is small. Fix it, or relabel the column as a phrase count.
- **`SELF` disqualifies any proof line containing "review"** (B5). This skews `rs-parallel-reviews`, whose subject is reviews.
  - It affects one case of ten. But if the outside measure is being reworked for item 1 anyway, fix it in the same pass.
- **The principle card's leans list `perf-issue` and `investigation`** (B6), and neither playbook references the principle. The card is rendered on `docs/jstack-explained.html`, so this is a false statement in shipped docs.
  - The one-line fix (list only `deeper`) is in scope. Linking the playbooks is outside the "Where" line and is for later.
- **The gate placeholder `Context: <the four answers…, in one line each>`** (B7) invites four lines, and `mirror.field` keeps only the first.
  - The home step belongs to another brief, but this skill's wording is what it will copy. A one-line rewording ("on this one line, separated by semicolons") removes a real data-loss path.

### Noted

- **A5:** `eval.py` puts `evals/deeper` and `src` on `sys.path`, and registers a top-level `score` module, for the rest of the test session. This is real but has had no observed effect. Fix it if a test-ordering problem ever appears.
- **B8:** `Pinned.own = ()` is a default no caller uses. It is harmless; making the field required is a matter of taste.

### Dismissed

None. Every finding was concrete and about changed lines.

### Agreement Map

**Where they agreed.** The reviewers converged independently on two things: the raw measure echoes the skill's list (A2/B2), and `write()` is destructive and non-resumable (A3/B3). Those are the consensus items.

**Where they arrived from opposite ends.** On the verdict they reached the same conclusion by different routes:
- A took apart the scorer, showing that backticks produce the whole outside gain.
- B took apart the process, showing that a format-only re-run flipped the outcome.

Together they make the strongest finding in the review. The eval's "won" rests on a proxy measured in a run its own rule says not to trust alone.

**What only B raised.** B alone raised redaction (B4) and the skill and principle details (B6, B7). B read wider than A, into how the eval touches private data and how the skill's text is consumed.

**What the pattern tells us.** The plumbing drew almost nothing:
- the skill,
- the principle,
- the jdrift source map,
- the install,
- the counts.

The eval drew everything, and mostly about what it claims rather than whether it runs. The work is close. Rescore the committed briefs with honest measures, state whatever verdict comes out, and make the rerun and the redaction safe.

```
BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Consider
A5: Noted
B1: Act on
B2: Act on
B3: Act on
B4: Act on
B5: Consider
B6: Consider
B7: Consider
B8: Noted
```

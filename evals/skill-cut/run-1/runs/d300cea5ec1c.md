### Intent
> Add `/deeper`, a manual skill that answers Felix Rieseberg's four questions and returns a rewritten prompt, with a non-blocking `jbus gate` when a home runs it. Add the 25th principle, `depth-over-breadth`, listed by jdrift as a jstack source, with every count updated to 25. Credit Rieseberg in `THIRD_PARTY.md`. Commit a rerunnable blind eval over about 10 past briefs, scored by something other than the writing agent, whose Result says plainly whether `/deeper` won. If it did not, that is the finding, not a reason to tune.

### Reviewers
- Reviewer A: 5 findings
- Reviewer B: 8 findings
- They agreed independently on two issues: raw sources copied from the skill's list, and the wipe-before-write in `write()`. Each also attacked the eval's verdict from a different side. All the review skill's questions were addressed.

### Act On

**1. The "won" verdict is not supported by the eval as committed.** (A1, B1, merged)
The rule requires `/deeper` to lose on no measure, so "outside" decides the verdict. Both reviewers show that measure cannot carry it:
- **A1:** the backtick branch of `OUTSIDE` (`evals/deeper/score.py`) counts inline code as an outside judge. A rescore of the committed run-2 briefs without that branch leaves the arms level (0.34 vs 0.33). The whole 0.57 → 0.75 rise is formatting, and the skill tells deeper briefs to name things by path, so they use more of it.
- **B1:** run 1 lost on outside (4 up, 6 down). The only change before run 2 was the rewrite's output format (fence → block quote). Run 2 then won 8–2, and eight cases flipped sign. The README says only what the two runs agree on is a finding, then declares "won" on the one run where they disagree.

The task said a non-win "is a finding, not a reason to tune the eval". Here the eval itself is the PR's proof.
- **Fix:** drop the bare-backtick branch, or limit it to commands actually run. Rescore both runs, which needs no model calls. Restate the Result as what both runs show: won on instruments, raw pending item 2, outside not shown. Take the planned `Proves it:` line out of the README until outside is shown.

**2. "Raw sources" may only count the skill's own example list, yet the README claims otherwise.** (A2, B2, consensus)
- Seven of the twelve `RAW` kinds match `SKILL.md` question 2 almost word for word. Instruments got a `beyond` control for this; raw got none.
- The README's "not only by copying the skill's own examples" is therefore unsupported for raw.
- **Fix:** add a raw `beyond` that excludes the skill's listed kinds and rescore the committed briefs. Report whatever comes out, or narrow the sentence to instruments.

**3. The one documented command deletes the committed results before it can fail.** (A3, B3, consensus)
- `write()` runs `rmtree` on `runs/` and `deeper/` before any of the 60 `claude -p` calls, and `key.json` is written only at the end.
- Any of these leaves a partial `runs/`, a stale key, and a `report` that refuses to run:
  - a missing `claude`
  - one bad exit
  - a missing block quote
  - a timeout
- This is the "crashed halfway" case the review asks about. "Rerunnable by one command" is a Done-when line.
- **Fix:** write into a temp directory and swap it in after the key is written. Also check `shutil.which("claude")` before touching anything.

**4. Redaction fails open.** (B4, single reviewer, but a security finding with a concrete path)
- `_private` reads patterns from `~/.config` and ignores `XDG_CONFIG_HOME`, which `jleak`'s own CLI honours.
- It also swallows `jleak.Missing` and returns no patterns. Briefs and model output from private task history are then written, unredacted, into a repo meant to be public.
- **Fix:** resolve the path as `jleak.cli` does, and fail when the patterns are missing.

**5. The gate's `Context:` placeholder loses three of the four answers.** (B7)
- `skills/deeper/SKILL.md:67` invites "one line each", but `mirror.field` keeps only the `Context:` line.
- A home that follows the wording silently records only answer 1, and the test fills in the semicolon form, so it never catches this.
- **Fix:** a one-line wording change, plus a test case for a home that writes one line per answer.

### Consider

- **The "Not held" column is a phrase count.** (A4) It counts "does not hold" anywhere in the brief and misses tense variants, yet the README turns it into "seven of the ten had a Done when line … did not hold". Limiting the search to the Result section and matching the variants is cheap. The tradeoff is small effort against a factual-sounding sentence that rests on a loose count.
- **`SELF` treats any "review" as self-assessment.** (B5) It penalises `rs-parallel-reviews` for its subject rather than its judge. That makes the outside measure, already the weak one, noisier on one of the ten cases. Worth fixing in the same rescore as Act On 1, if it is cheap.
- **The principle card claims usage that does not exist.** (B6) The card says `perf-issue` and `investigation` lean on the principle, but neither links to it, and the card is shown on the explained page. Listing only `deeper` now is a one-word fix. Linking the playbooks is outside **Where** and is for later.

### Noted
- **Test import leaks into `sys.path`.** (A5) Importing `eval.py` in tests leaves `evals/deeper` and `src` on `sys.path`, plus a top-level `score` module, for the rest of the worker. This is real hygiene, but nothing collides today.
- **`Pinned.own` has an unused default.** (B8) Harmless, and this is a style choice.

### Dismissed
- None. Every finding is accurate. Only the two nits above are not worth acting on in this PR.

### Agreement Map
- **Consensus:** both reviewers found the same two problems independently, raw copying (A2/B2) and the wipe-before-write (A3/B3). That is a strong signal.
- **Complementary:** on the verdict they diverged in method but converged in conclusion. A showed the outside measure reads formatting (A1). B showed the outside result is not stable across runs (B1). Together they mean the eval's "won" rests on its weakest measure, read from one run.
- **Coverage:** A stayed inside the eval's mechanics. B covered the whole surface (skill, principle card, jdrift, privacy) and found the one security issue.

Neither reviewer's findings were padded with nits.

The skill, principle, credit and jdrift parts look sound. The work left is mostly to make the eval honest:
- rescore with no model calls,
- make the write step crash-safe,
- make redaction fail closed,
- report whatever the rescored numbers say, including "did not win on outside" if that is the result.

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
B7: Act on
B8: Noted

### Intent
> Replace the two pr-review reviewer subagents (A/B) per PR with one scoped review thread. That thread reads the PR's diff itself, sends one combined review, writes one `## Review` section that jmerge's ready rule still accepts, and is archived by jbus on the next pass after the PR merges or closes. A review thread of an open PR is never archived. Skills and docs that say "two reviewers" now say one. Tests cover the skill text, the archive on merge and its absence for an open PR, and jmerge reading the new section as ready. `make check` exits 0.

### Reviewers
- Reviewer A: 8 findings
- Reviewer B: 4 findings
- They agreed independently on two things: the false Step 4 sentence and the files outside `Where`. They raised the "closed" inference from two angles that land on the same function.

### Act On

**1. `shut()` decides "closed" from absence, and the result is an archive** (A2, B1)
- `shut()` treats a slug as closed when its Result URL is missing from `world.open`.
- `world.open` is a 100-item list compared by raw URL string.
- So the review thread of the 101st open PR, or of a PR whose URL differs in form, gets settled and archived. That breaks the Done when line "a review thread of an open pull request is never archived".
- B1 adds that this is a second definition of "closed" beside `watch.pull`, and the new test already shows them disagreeing (`eta`).
- Both reviewers reached the same function from different angles. This is the strongest signal in the review.
- **Remedy:** define "merged or closed" in one place, and confirm "closed" from GitHub's reported state before archiving. For example, `world.merged`, plus `gh pr view --json state` == `CLOSED`, cached the way `merged.json` caches merges.
- B1's suggestion alone, reusing `watch.pull`, would unify the two rules. But `watch.pull` is also absence-based, so it does not fully answer A2.

**2. The jmerge "new shape" test never lists a finding** (A1)
- The template's `Findings:` line has no `": "`, so the fill never lands.
- The section jmerge reads therefore has zero `- ` findings, and the findings/answers match in `ready.py` is never exercised.
- This Done when test is meant to prove "its findings answered", and right now it would pass even if that matching broke.
- **Remedy:**
  - Write the `Findings:` list explicitly, or fix the fill to split on `:`.
  - Add the negative case: the same section with the `Finding:` line removed is not ready.

**3. `docs/flow.html` still says "Two reviewers ... then settles itself"** (A3)
- This misses the Done when line directly: "any other skill or doc that tells pr-review to start two reviewers says one".
- The change updated `flow.md`, README and `jgauge.md` but missed this hand-written page, and no test catches it.
- It is a one-line fix.

**4. Step 4 of `skills/pr-review/SKILL.md:232` claims an independent check that no longer exists** (A6, B2)
- "Judge it against what the reading was not given: the brief's decisions" was true with two Explore subagents. In one thread it is false: the same thread read the whole brief.
- This is skill text an agent acts on. Telling it there is a cross-check when there is none weakens the judgment step.
- **Remedy:** reword it to say that reading and judgment are the same thread, and that the lead step re-checks each claim against the repo and the brief.

### Consider

**`finished()` carries a non-prefix `"archive"` key in a prefix-keyed map** (A4)
- This forces three extra pieces in `settle`:
  - the special case,
  - the second `shelve` set copied down to subagents,
  - the nested loop with `break`.
- Computing `ended` once and deriving `("settle", "archive")` per thread from `role_of` and `slug_of` would delete those pieces.
- **Tradeoff:** it is a real simplification in a file this PR owns. It is maintainability, not correctness, and it touches the same code as Act On #1, so it is cheapest done alongside that fix.

**A merged PR's review threads stay unarchived when the last Review is `not run`** (A5)
- After a merge, the thread waits on nothing, and the Done when line says the thread is archived on the next pass.
- The path is concrete but uncommon.
- **Tradeoff:** archive non-busy review threads of ended slugs regardless of verdict, or document in `docs/jbus.md` that they are kept on purpose. Either is fine. Choose one.

### Noted
- **A7, B4: files outside `Where`.** These are `README.md`, `docs/flow.md`, `docs/jgauge.md` and `src/jbus/t3.py`.
  - Each traces to the task: the docs follow the "any other doc" Done when line, and `t3.py` was needed because `_held` refused `archive`.
  - The brief's `Where` was too narrow. No change is needed.
- **A8: the `docs/jbus.md:108` sentence is hard to parse.** It is worth fixing in the same doc pass, but it is a nit.
- **B3: the fake keeps archived threads listed, and already-settled A/B subagents are not archived.**
  - The first part is a hypothesis about T3's listing behaviour.
  - The second only affects reviews started under the old skill, which this task leaves alone ("reviews already written").
  - It is transitional and low-impact.

### Dismissed
None. Every finding was grounded in changed lines or a Done when gap. The weaker ones are filed under Noted rather than rejected.

### Agreement Map
- **Agreement:** both reviewers caught the stale Step 4 sentence and the out-of-`Where` files, and both went after `shut()`. A argued from the Done when guarantee (open PRs never archived). B argued from duplication with `watch.pull`. Two independent routes to one function make it the clear top item.
- **A only:**
  - the hollow jmerge test,
  - the missed `flow.html`,
  - the structure of `finished()`,
  - the `not run` edge.

  A read the tests and the Done when list more literally.
- **B only:** the fake T3 behaviour. B leaned toward how the tests model the outside world.
- **Severity:** neither reviewer inflated nits. The single nit (A8) was labelled as one.
- **Overall:** the core change, one thread with one section, looks sound. The risk sits in the new archive rule and in one test that does not exercise what it claims.

BUCKETS
A1: Act on
A2: Act on
A3: Act on
A4: Consider
A5: Consider
A6: Act on
A7: Noted
A8: Noted
B1: Act on
B2: Act on
B3: Noted
B4: Noted

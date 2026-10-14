# Hillclimb

Run by: a crewmate, for moving one measurable thing toward a target over many attempts, where the brief's "Done when" has the target as a number.

Source: pstack, `pstack/skills/poteto-mode/playbooks/hillclimb.md`

<!-- card: Long or wide runs | 2 | Moving one measurable thing toward a target over many attempts. The brief's "Done when" has the target as a number. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the metric and the honesty of the experiment.** One change, one measurement, keep or revert. Never two untested changes at once, never a win claimed from reading code (`principles/prove-it-works.md`).

1. Fix the metric before anything is built: read the code path, name what can move the result (the size of the data, history, state, concurrency), and pick the case that shows the complaint. If none does, fix the case and do not climb. Then write three things: the one metric, which direction is better, and a stop predicate that pairs the brief's target with a floor on attempts, so a lucky early win cannot end the run ("30% under the baseline, and at least 6 attempts"). A brief with no number: set one, say it here, and carry on (`principles/never-block-on-the-human.md`).
2. Build the harness, show that it can tell cases apart, then freeze it (`principles/build-the-lever.md`). It is one command, run by the block under "Taking the runs" in `skills/benchmark-checklist/SKILL.md`, read in full now. It prints its count of errors and of work done. Run it on a harder and an easier case and see them apart: if they are not, change the case or the metric. Vet it with that skill's seven questions (`principles/explain-the-number.md`). Commit it, then do not touch it. Write down the baseline commit, median and range, and a passing run of the repo's check command, the gate every attempt must keep.
3. Open the log: read `skills/show-me-your-work/SKILL.md` in full and write the first row with its block, the frozen harness and the baseline. One row per attempt after that, kept or reverted: the phase is the attempt (`a1`, `a2`), the decision the change, the why the mechanism, the evidence the commit or `reverted`, the result the verdict with before and after. Read it before each attempt.
4. Write the hypotheses down, each as a mechanism from the code path of step 1 ("defer X off the start path, since it blocks the first paint"). For a speed metric, order them as step 4 of `playbooks/perf-issue.md` does, cheapest first. Take only its order: this playbook's stop is step 6.
5. Loop, one hypothesis per attempt. Make the change. Measure it with the frozen harness, both sides in turn, and run the gate. The other side is one second worktree, made once at the baseline, `git worktree add --detach <path> <commit>`, and run once unreported so both are warm. After each kept change move it to the commit before the next attempt, `git -C <path> checkout --detach <commit>`. Keep it only when the metric moves by more than the spread between runs and the gate passes: commit it by itself, with `git add <files>` and never `-A`. Otherwise revert it in full: `git checkout -- <files>`, and `git clean -f -- <the files it added>`. Log the row either way, then start the next (`principles/sequence-verifiable-units.md`). Wait for each measurement inside this turn: nothing wakes a thread that ends its turn on a background command.
6. Push past the first plateau. After three reverts in a row: change the kind of idea, combine two near misses, read the profile again, or try something radical. Stop when the predicate holds, or when what is left costs more than it gives. Do not relax the predicate, and do not stop while a cheap hypothesis is untried. Right and simple outrank the number: revert a win that breaks behaviour, and keep a simplification that holds the number (`principles/laziness-protocol.md`).
7. Check the log as "Check the log before handing over" in the log skill says. Move the second worktree back, `git -C <path> checkout --detach <baseline commit>`, take the final number against it and vet it once more. Then `git worktree remove <path>`, also after a run that stopped early.
8. Run `playbooks/opening-a-pr.md`: one pull request, the kept commits in the order they landed, the harness's commit first.

Never done here, and who does it:

- **A change to the frozen harness.** Nobody does, in this task. A harness found wrong ends the run: say so in the Result, and the home plans the new one.
- **A pull request per kept change.** Nobody does: one pull request.
- **Attempts typed or measured by subagents side by side.** Nobody does: the measurement is the slow part and runs one at a time, under the heavy-suite lock when the harness starts several workers, as the benchmark skill says.
- **Committing the log.** Nobody does, unless the brief says so: the Result carries it.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the metric and the target, baseline to final with the percent, the attempts (kept and reverted), each kept change on one line, the log's path and rows, and the best idea not yet tried.

# Perf issue

Run by: a crewmate, for one thing that is too slow, fixed once and proved with a number before and after.

Source: pstack, `pstack/skills/poteto-mode/playbooks/perf-issue.md`

<!-- card: Build and change | 4 | One thing that is too slow, fixed once and proved with a number before and after. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

Verify skill: `.claude/skills/verify-*/`, else a `verify-*` item of `skills.json`'s `projectSkills` (jstack: `features/verify-jstack/project-skill/`).

**You own the measurement story.** Every fix is tied to a number you took, and a number is believed only after it is vetted. Reading the source is not measuring: no claim of a ceiling, a cause or a win without a run behind it.

1. Write the claim you expect to ship, in one sentence with its unit ("the export is 30% faster at the median on the 60k-row file"), and the one command that measures it: the repo's verify skill or harness where it has one, otherwise the command the brief names.
   Set a target the field would call ambitious, proved by the measurement and not by your own word (`principles/principle-depth-over-breadth.md`).
   Read `features/benchmark-checklist/SKILL.md` in full now.
2. Take the baseline with the block under "Taking the runs" in that skill, at least 5 rounds, on the untouched code, and vet it with the skill's seven questions before anything is planned from it (`principles/principle-explain-the-number.md`). Write down the median, the range, the failed runs and the commit, `git rev-parse HEAD`. A baseline that does not show the complaint is the wrong case: fix the case, not the code.
3. Name the limiter from a profile, taken in a run you do not report, and read the code path it points at. Write each hypothesis as a mechanism ("the header is parsed once per row"), not as a place to look. Do not explain a cost you have not seen in a profile (`principles/principle-fix-root-causes.md`).
4. Order the hypotheses by these, cheapest first, and stop at the first that meets the claim: do not do it, so that work whose result nothing uses is stopped and not made cheaper (`principles/principle-subtract-before-you-add.md`); do it, but not again; do it less; do it later; do it when nobody is waiting; do it concurrently; do it cheaper.
5. Make one change, then measure it against the baseline with the same block, both sides in turn, and run the repo's check command. Keep it only when the gap is wider than the spread between runs and the check passes. Otherwise revert it in full, `git checkout -- <files>` and `git clean -f -- <the files it added>`, and take the next hypothesis (`principles/principle-sequence-verifiable-units.md`). Never two untested changes at once. A fix that crosses a module boundary gets its two or three shapes written down and one picked before code (`principles/principle-exhaust-the-design-space.md`). One commit per kept change.
6. Take the final number on the committed fix against the baseline commit, in a second worktree of that commit, `git worktree add --detach <path> <baseline commit>`, removed after. Vet it with the seven questions. "Inconclusive", or a win on a surface other than the one in the claim, is not a pass: say so, and say which question it failed (`principles/principle-prove-it-works.md`).
7. Put one primary number under Verification in the pull request's body: the verdict, median to median with the unit, the runs a side, the range, the limiter. The rows the block printed go on the Result's `Proof:` line.
8. Run `features/writing/playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **A loop of fixes toward a target.**
  A crewmate does, from a brief with `playbooks/hillclimb.md`.
  This playbook is one fix: what else the profile showed is a queued row or nothing (`templates/a-fault-outside.md`).
- **Handing the fix to a subagent.** Nobody does: the one who measured types the change, on this session's own model and effort.
- **A measurement outside the heavy-suite lock, when its command starts several workers.** Nobody does: the benchmark skill says how the lock goes around the runs.
- **Relaxing the claim to fit the number.** Nobody does. A claim that was not met is reported as not met.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the claim, the baseline and the final number with their runs and range, the delta, the limiter, each change kept or reverted, and the command that takes the number again.

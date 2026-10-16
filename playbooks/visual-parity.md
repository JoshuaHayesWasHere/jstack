# Visual parity

Run by: a crewmate, for one component moved to a new implementation (a migration, a restyle, a port) that has to look exactly as it did, one component to a brief.

Source: pstack, `pstack/skills/poteto-mode/playbooks/visual-parity.md`

<!-- card: Build and change | 5 | One component moved to a new implementation that has to look exactly as it did. One component to a brief. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own pixel-exact equivalence of one component.** The baseline is the spec, and you do not touch it. Equivalence is shown by an image diff, not by eye. Three things are held from the first step to the last: the harness is not changed, the baseline is not changed, and the component is not restructured so that a diff passes.

1. Establish the baseline first, before any migration: the harness that screenshots the current component across its states, and its images, plus the target's when two implementations are matched. No baseline, no parity claim. Where the repo has none and the brief's **Where** covers a harness, build it now, take its images under the lock of step 2, and commit it by itself, before the component is touched (`principles/principle-sequence-verifiable-units.md`). Where it does not, stop and say so.
2. Run the harness on the untouched component, for this component's spec only, under the machine-wide lock: `flock ~/.local/state/locks/heavy-suite.lock <the harness's command>`. It queues behind other threads, so give it a long timeout and wait. See a diff of zero. Write down the commit, `git rev-parse HEAD`, as the baseline commit, and the paths of the baseline images and the harness.
3. Check that the component is yours alone to move. A shared primitive that it leans on and that has to change is migrated first, as a task of its own: stop and say so, and the home splits it (`principles/principle-separate-before-serializing-shared-state.md`). One component, one worktree, one owner.
4. Migrate the component, in small units, each one run against the baseline before the next is started.
5. Verify against the baseline by image diff, with the harness of step 1 and no other instrument, under the same lock. The repo's verify skill, where it has one, is how the component is reached, not what measures it. A nonzero diff is a fail (`principles/principle-prove-it-works.md`). Open the diff image, name what moved (a font, a spacing, an edge, a state) and fix the component where that comes from (`principles/principle-fix-root-causes.md`). Run it again, in this thread, until the diff is zero. A threshold is not raised and a state is not dropped.
6. Show the baseline untouched: `git diff --stat <the baseline commit> -- <the baseline images and the harness>` prints nothing. Where the baseline itself looks wrong, do not edit it: carry on against it, and park the question as a gate, as `skills/crew/SKILL.md` "Do the task" says, with "the baseline stands" as its default.
7. Run `playbooks/opening-a-pr.md`. The full run of the heavy suite is whoever's the block in `skills/crew/SKILL.md` "Do the task" prints.

Never done here, and who does it:

- **An edit to the baseline, the harness or its threshold.** Only the user's word changes the spec: the gate of step 6 asks.
- **A second component in this pull request.** The home splits several components into one brief each, shared primitives first. A second one goes in the Result under "Noticed".
- **Components moved side by side in worktrees you start.** The home launches them, one crewmate each.
- **Parity claimed by eye, or from a diff that is "close".** Nobody claims it: zero, or the Result says does not hold.
- **The screenshot run outside the lock, or a second way round it.** Nobody does: it waits its turn.

**Hand over:** in the pull request's Verification and on the Result's `Proof:` line, to the reviewer and the home: the component, the diff result for each state as printed, where the baseline and the harness are, the output of step 6, and what is left.

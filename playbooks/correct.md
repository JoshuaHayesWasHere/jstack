# Correction

Run by: a crewmate, for one class of repeated mistake that the brief names, to be made impossible or at least caught.

Source: pstack, `pstack/skills/correct/SKILL.md`

<!-- card: Work on jstack itself | 3 | One class of repeated mistake that the brief names, to be made impossible or at least caught. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the correction: the level, the check and the proof.**
A correction is done when the mistake cannot be made again, or fails loudly when it is.
A paragraph asking the next agent to be careful is not one.
The smallest check that catches the class ships, and nothing more (`principles/principle-laziness-protocol.md`).

1. Read the evidence the brief gives for the class: the commits, steers or review findings, at least two. Open each and write down the one thing they share, as a sentence a check could test. If they share nothing, it is not a class: stop and say so.
2. Reproduce one past mistake. In your worktree, put it back as it was made (the reverted commit's change, the line the reviewer flagged), and see that the repo's check command passes with it there. That pass is the gap you are closing (`principles/principle-fix-root-causes.md`). Undo it.
3. Pick the level, the highest that works, in the order of `skills/correct/SKILL.md`: structure, then types, then a test, then a written rule (`principles/principle-encode-lessons-in-structure.md`). Write down why each level above the one you picked does not work. If the brief picked a level and a higher one works, take the higher one and say so in the Result.
4. Make the change. Structure: one owner, one supported way, the old way and its dead code deleted with every caller moved (`principles/principle-subtract-before-you-add.md`, `principles/principle-migrate-callers-then-delete-legacy-apis.md`). Types: the bad state cannot be written, or a check in the repo's check command fails with an error that names what to use in its place (`principles/principle-type-system-discipline.md`). A test: it executes something and asserts the behaviour (`principles/principle-test-behavior-not-implementation.md`). A change that cannot be made inside the brief's **Where** is not made: stop and say so.
5. Prove it on the real mistake (`principles/principle-prove-it-works.md`). Put the mistake from step 2 back, run the check command, and see it fail with the new error. Undo it and see it pass. A check that was never seen red is not kept.
6. Write the rule's line for `notes.md`, word for word, with what enforces it: `<the rule> (enforced by <the test, check or block>)`. For a written rule with no check: `(nothing enforces it: <why>)`. You do not edit `notes.md`: the line goes in the Result under "Noticed", and the home adds it. If a line for this rule is already there, say which one it replaces.
7. Commit the check before the change that satisfies it where the two can be told apart, so the branch and the pull request read red, then green (`principles/principle-sequence-verifiable-units.md`).
8. Run `playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **A second class in the same pull request.**
  It goes under "Noticed", for the home to plan.
- **An edit to `notes.md`, the plan or `~/.claude/CLAUDE.md`.**
  The home adds the line from step 6, and the rest is not this task's.
- **An exception to the new check.**
  Only the user's word makes one.

**Hand over:** in the pull request's Verification and on the Result's `Proof:` line, to the reviewer and the home: the class and its evidence, the level picked and why no higher one works,
the break used to show the check red with its output failing and then passing, and the `notes.md` line.

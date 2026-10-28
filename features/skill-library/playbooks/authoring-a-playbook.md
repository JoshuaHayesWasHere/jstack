# Authoring a playbook

Run by: a crewmate, for writing a new file in `playbooks/`, when a kind of task comes back and no playbook there covers it.

Source: pstack, `pstack/skills/figure-it-out/SKILL.md`

<!-- card: Work on jstack itself | 1 | Writing a new file in `playbooks/`, when a kind of task comes back and no playbook covers it. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the playbook's steps**: its reader is an agent that copies them in as todos and works them to the letter, in a thread that has read nothing else.
The frame around the steps is not yours: `features/skill-library/templates/playbook.md` is its one copy, and the shape test holds every file in `playbooks/` to it.

1. Show that no playbook fits. Run the block under step 1 of "Handing a task to a crewmate" in `skills/home/SKILL.md`, with `$T` as your skill's top block sets it: it prints a row for each playbook, its name and who runs it for what. Write down the two closest rows and, for each, the step that does not fit this kind of task. When a changed step in one of them is enough, change that playbook and write no new one (`principles/principle-subtract-before-you-add.md`): steps 2 to 5 are then `skip: <the playbook> changed`.
2. Frame it in four lines, before any step is written: the one role that runs it (a crewmate, a scout or the home); the trigger, in one line, as it will stand on the `Run by:` line; done, as a check that can fail (`principles/principle-prove-it-works.md`); and what is handed over, to whom.
3. Take the steps from evidence, not from what the work ought to be: two past tasks of the kind, from their briefs and Results in `$H/tasks/`, or the source playbook when it is drawn from one. List what each did and what its Result says got in the way or was left, and keep what they share. A Result does not hold the order the work went in: take the order from the source, or from the next sentence. Put the riskiest unknown first, and the building of a check before the work it checks (`principles/principle-sequence-verifiable-units.md`). With fewer than two past tasks and no source, say so in the Result: the steps are a guess until step 7.
4. Write four to nine steps.
   Each is an action that ends in something seen: an output read, a test red or green, a file on disk.
   Each names the principle it leans on, by its path, where one in `principles/` fits, and none where none does.
   A step that is the same every time is a shell block or a script that the step runs, not prose to follow (`principles/principle-encode-lessons-in-structure.md`).
   A crewmate's last step runs `features/writing/playbooks/opening-a-pr.md`.
5. Write the `Never done` list: what this reader will be tempted to do and must not, each with who does it (the home, the reviewer, a scout, the user, or nobody) and where the reader leaves it for them.
6. Copy the frame from `features/skill-library/templates/playbook.md` to `playbooks/<name>.md` and fill it in with the steps and the list; run the shape test until it passes, `uv run pytest features/repo-guards/tests/test_playbooks.py`, which reads the directory, so the new file needs no edit to a test or to a skill; run the block from step 1 again and see the new row; a playbook drawn from another project gets its line in `THIRD_PARTY.md`, as the test says.
7. Follow the new playbook by hand on one real or past task, step by step, as its reader would (`principles/principle-prove-it-works.md`). Write down three things for the Result: what helped, what got in the way, and what was skipped and why. Change the steps that got in the way and run the shape test again.
8. Run `features/writing/playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **A change to the frame**: `features/skill-library/templates/playbook.md` and the shape test are a task of their own: a row, queued as `templates/a-fault-outside.md` says.
- **A change to a skill so that the playbook is found.**
  Nobody does: the home's block reads the directory.
  A playbook that needs a skill to do something new is a row, queued as `templates/a-fault-outside.md` says, and the home plans it.
- **A second playbook in the same pull request.**
  One kind of task, one file, one trial.
  The next is a row, queued as `templates/a-fault-outside.md` says.
- **Reaching running threads.** Nobody does: a home picks the playbook after the merge and a `git pull` in the main checkout.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the two closest playbooks and why neither fits, the four lines of step 2, the evidence the steps came from, and the trial of step 7 (what helped, what got in the way, what was skipped).

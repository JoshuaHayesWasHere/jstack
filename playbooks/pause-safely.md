# Pause safely

Run by: a crewmate, for an explicit word to pause, from the user or the home, in the middle of a task: stop here, pause this, pick it up later.

Source: pstack, `pstack/skills/poteto-mode/playbooks/pause-safely.md`

<!-- card: In every task | 2 | An explicit word to pause in the middle of a task, from the operator or the home: stop here, pick it up later. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own a clean stop.** You leave a checkpoint that a thread which has read nothing else can resume from. This is for an explicit pause only. On "keep going", "going to bed, keep going" or "don't stop", you do not pause: the task goes on as `skills/crew/SKILL.md` "Carry on" says. A full context, a hard step or a question for the user is not a pause either.

1. Stop at a safe boundary. Finish the step you are in, or back out of it, whichever is shorter. Start nothing new, and stop every subagent and background command you started. Run `git status -sb` and read it: it is what the pause has to make durable.
2. Take no irreversible action in order to pause. No pull request is opened, nothing is merged, rebased or deleted, and nothing is pushed, so no check runs on a `wip:` head. Whatever you would undo to "tidy up" stays as it is.
3. Make the work durable: commit every uncommitted edit as one commit on the current branch, with the subject `wip: <what was in progress>`. If the check command fails at that commit, say so in the commit body in one line. A second pause after this one makes a second `wip:` commit and loses nothing (`principles/principle-make-operations-idempotent.md`). Run `git status --porcelain` and see it print nothing.
4. Write the resume note where the next thread reads first: the brief's Result, as `templates/result.md` has it, with `Status: paused`. Each "Done when" line says holds or does not hold, and the `Proof:` line has what was run so far. The `Left:` line carries the rest, in this order: what you were doing when you stopped, the first action on resume, the files that matter (with how to get back any that sit in `/tmp`), and what would trip up a thread that has not seen this one. Write paths and commit ids, not diffs.
5. Read the note back from disk as the thread that resumes would, with the brief and the branch and nothing else (`principles/principle-prove-it-works.md`). Whatever it could not act on is still in your head: put it in the `Left:` line.
6. End as `skills/crew/SKILL.md` "End" says, from its step 2 on: its blocks read `Status: paused`. What you send the home, and say in this thread, also has the first action on resume. A wake that comes while you are paused is that skill's "When the watch wakes you": one line in the Result, and the turn ends.

Never done here, and who does it:

- **Pausing unasked.** Nobody does: with no word to pause, the task goes on.
- **Opening a pull request to park the work.**
  Nobody does: the `wip:` commit and the Result are the checkpoint.
  `features/writing/playbooks/opening-a-pr.md` is run on resume, when "Done when" holds.
- **A resume file of your own, in `/tmp` or the repo.** Nobody writes one: the brief is the one place the next thread reads.
- **Squashing or rewording the `wip:` commit.** The home squash-merges, so it never reaches the default branch.
- **Resuming.** The user or the home says when, in this thread or with a new one on the same worktree. The round that follows appends `## Result, follow-up`, as `skills/crew/SKILL.md` "End" says.

**Hand over:** in the Result, to the home and to the thread that resumes: which "Done when" lines hold, what is on disk and at which commit, whether the check command passes there, and the first action on resume. This is a pause, not a final report.

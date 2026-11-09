# Operations

Run by: a crewmate, for an operation on the machine that changes no tracked file and opens no pull request (a cleanup, a tag, a setting), in a brief with `Pull request: none`.

Source: this repo

<!-- card: Build and change | 6 | An operation on the machine that changes no tracked file and opens no pull request: a cleanup, a tag, a setting. -->

Work the numbered steps below in order.
Report a step you do not do as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo.
Read a principle in full when a step you are doing names it.

**You own the state of the machine before and after.** The brief says what to change, and the machine says what is there now. Act on what the machine says, change only what the brief asks, and record how to put each change back.

1. Check the state the brief names, by a command, before anything is done (`principles/principle-make-operations-idempotent.md`).
   Run the brief's `Proves it:` command, and one command for each thing the operation needs: the target is there, the build is installed, the merge is on the green main.
   Keep what each prints as the before.
   Where the brief's command picks the wrong item, run one that matches its intent, and record a `Decision:` line.
   If the work is already done, change nothing, and go to step 6: the Result says `Status: done` and `Changed: nothing`.
   If something the operation needs is missing, change nothing, and go to step 7: the Result says `Status: paused`, what is missing, and the command that will show it is there.
2. Write the list of exactly what will change, from what step 1 printed and not from the brief's count: each path, branch, tag or setting, with its size, tip or value now.
   Apply each keep rule of the brief (a process uses it, its row has not ended, a file names it), and move each item a rule keeps to a second list, with why.
3. Find the door of `templates/gates.md` the operation walks through: removing a file, a branch or a worktree is `deletes data`, and a tag or a package is `publishes`.
   Make its fail-safe first, and check it by a command: a `git bundle` of each branch, read back with `git bundle verify`; a copy of each file or setting; the exact artifact and where it goes.
   The user's yes to that door is quoted on the brief's `Task:`, `Decisions:` or `Builds on:` line, or is a gate the user answered.
   With no yes, park a gate as `skills/crew/a-gate.md` says, and go to step 7 with `Status: paused`.
   With no door, write `no door` on the `Proof:` line.
4. Do the operation, one item at a time, and read each command's exit.
   Run the keep checks again right before you act: a process can start using a path after step 2.
   Name each target in full, never by a glob or a variable, and use the form that prints what it did, such as `rm -v` or `git worktree prune -v`.
   A run that stopped halfway is finished by steps 1 to 4 again, which leave what is done.
5. Run the command from step 1 again, after any wait the brief names (such as two jbus passes), and put its output beside the before (`principles/principle-prove-it-works.md`).
   Each item of the first list is changed, and each item of the second is as it was.
   Where the after does not show the change, the Result says `Status: not done`, the item, and both outputs.
6. Run `git status --porcelain` and `git log --oneline origin/main..HEAD` in the worktree, and see both print nothing: no file and no commit is left behind.
   Put a changed tracked file back with `git checkout -- <file>`; what changed it is a row, as `templates/a-fault-outside.md` says.
7. Write the Result as `templates/result.md` has it, and end as `skills/crew/SKILL.md` "End" says.
   `Changed:` says what changed on the machine, with its size, tip or value, and the command that puts it back: `git fetch <bundle> HEAD:<branch>`, the copy to restore, the tag to delete.
   A change that reached someone outside the machine says that no command takes it back.
   `Left:` says what the brief named that is still there, from the second list, each with why, or `none`.

Never done here, and who does it:

- **A commit, a push of the branch, or a pull request.**
  Nobody does: the brief says `Pull request: none`.
  A file that has to change is a row, queued as `templates/a-fault-outside.md` says.
- **An item past the list of step 2.**
  The home decides on it, from the `Left:` line: a worktree or a file you saw and the brief did not name stays as it is.
- **Walking a door with no yes.**
  The user does, through the gate of step 3.
- **A timer, a `sleep` or a watcher that waits for what step 1 found missing.**
  Nobody arms one: the row ends `Status: paused`, and the home launches it again.
- **Loosening a keep rule because a match looks harmless.**
  The home does, with a later brief: the Result says why it looked harmless.

**Hand over:** in the Result, to the home: the before and after of the same command, each item changed with the command that puts it back, each item kept with why, the fail-safe's path, and each gate parked.

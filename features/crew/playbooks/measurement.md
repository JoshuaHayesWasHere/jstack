# Measurement

Run by: a crewmate, for a measurement row: a probe, a shot or a count whose product is a number, a shot or an answer, with no fix, no target to drive toward and no change to the code.

Source: this repo

<!-- card: Diagnose, fix nothing | 2 | A probe, a shot or a count whose product is a number or an answer: no fix, no target, no change to the code. -->

Work the numbered steps below in order.
Report a step you do not do as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo.
Read a principle in full when a step you are doing names it.

**You own the record of the measurement.**
Each number comes from a file the machine wrote and that the home can open after you, never from your own account of the run.
Each thing the probe made is closed, or named for the home.

1. Check that there is something to measure before anything runs (`principles/principle-prove-it-works.md`).
   Read what the run needs from the machine itself: the commit green holds (`readlink -f ~/.local/share/jstack/harness/claude-code/source`, then `git merge-base --is-ancestor <commit> <that sha>`), the build that runs (`yay -Q <package>`, and its process's start, `ps -o lstart= -p <pid>`, after the install), or the traffic the probe reads.
   Where it is not there, take nothing: a shot of the old build proves nothing.
   Write the Result with `Status: paused`, a `Proof:` line of what each command printed, and a `Left:` line of what it waits on and who gives it, then go to the last step.
2. Open the row's folder and write down today's number before the run (`principles/principle-explain-the-number.md`).
   Run the block below with the slug in place of `<slug>`: each file goes there under this round's stamp `$r`, so no round overwrites another.

   ```sh
   R=~/.local/state/home/$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")/reports/<slug>
   r=$(date -u +%Y%m%dT%H%M%SZ)
   mkdir -p "$R" && ls -la "$R" && echo "$r" | tee "$R/$r-run-start.log"
   ```

   Then run each command on the brief's `Instruments:` line once, as it is worded, into `"$R/$r-before-<name>.log"`, and read the number off that file.
   An instrument that reads only after the event has as its before the brief's dated baseline: copy it, with its date, into `"$R/$r-baseline.log"`.
   A command that picks the wrong item keeps its worded output beside a fixed one, with a `Decision:` line for the Result.
3. Take the measurement, one round at a time, each into its own file under `$R`, and wait for each inside this turn.
   A shot is taken with the state it shows, at the same second, under one stamp: `s=$(date -u +%Y%m%dT%H%M%S)`, then `"$R/$s-<what>.png"` beside `"$R/$s-<what>.<state file>"` (a `jq` of `work.json`, a `t3_thread_read`).
   A probe left running starts from the main checkout, as its docstring says, or jbus's sweep stops it as an orphan of a worktree.
   Write each throwaway thing the run makes (a branch, a pull request, a thread, a process) to `"$R/made.log"` as you make it, one line each.
   A loop of more than ten `gh` calls reads `skills/crew/gh-budget.md` first.
4. Read every number from the machine's record and vet it (`principles/principle-explain-the-number.md`).
   The record is a transcript's `usage` lines (`jq 'select(.type=="assistant")|.message.usage' <transcript>`), the telemetry store (`sqlite3 -readonly`, and on `malformed` a copy taken with `.backup` first), the probe's own lines, or a shot read beside its state file.
   Answer questions 4 and 7 of `skills/benchmark-checklist/SKILL.md` for each number, and give its run count, its range and the path it was read from.
   A number reasoned from the code is not a result.
5. Close each line of `"$R/made.log"` and see it closed (`principles/principle-prove-it-works.md`).
   Stop the processes, and `gh pr close <n>` each throwaway pull request unmerged, then `gh pr view <n> --json state,mergedAt` shows `CLOSED`.
   A branch on origin is left there: its deletion deletes data, a gate parked by `skills/crew/a-gate.md`, with a bundle of it under `$R` (`git bundle create "$R/<branch>.bundle" <branch>`).
   Each line goes on the Result's `Left:` line with its state, so the home leaves a probe's red checks out of the week's counts.
6. Write the Result.
   Answer each question of **Done when** in one line: the answer, then the number with its unit and its record's path.
   On `Left:`, write what the next row must do: the next round to take, an instrument to fix, or a case this run did not see.
7. Do "End" of `skills/crew/SKILL.md`: this playbook opens no pull request, and nothing it measured merges.

Never done here, and who does it:

- **A fix to what the run measured.**
  A crewmate does, from a brief the home writes: the finding goes on `Left:`, or is a queued row as `templates/a-fault-outside.md` says.
- **Installing a build, restarting a service, or changing a setting so that there is something to measure.**
  The user does: step 1 pauses the row and names the wait on `Left:`.
- **A change to the instrument in the middle of a run.**
  Nobody does, in this row: an instrument found wrong is a `Left:` line, and the next row runs the fixed one.
- **Deleting a branch, a pull request or a report file.**
  The user does, on the gate step 5 parks.
- **Merging the throwaway pull request.**
  Nobody does.

**Hand over:** in the Result, to the home and the next row: the one-line answers with their numbers and paths, the folder `reports/<slug>/`, each throwaway thing and its state, and what the next row must do.

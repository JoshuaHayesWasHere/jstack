# State

A repo has one root home, and may have scoped homes beside it, each for one goal. `/home <scope>` starts one.

`~/.local/state/home/<repo>/` is shared by every home of the repo:

| File | Holds |
|---|---|
| `standing.md` | Your standing rules for the repo's homes. A home reads it whole at its start. |
| `tasks/<slug>.md` | A crewmate's brief, then its Result, then its Review. |
| `scouts/<slug>.md` | A scout's request, then its report. |
| `reports/<slug>.html` | A scout's visual page, when the request asked for one. |
| `merge.log` | The lines `jmerge` printed, each after the time it was printed. |
| `off` | Present when the automatic home is switched off for the repo. |
| `merge-off` | Present when the automatic merge is switched off for the repo. |
| `fresh-check` | The repo's check command, one line, which a crewmate runs once and `jbus queue add` holds a brief's check line to. Present, it also has a pull request whose check started before main moved proven over today's main on GitHub: `jmerge` asks GitHub to merge main into its branch, and the check at that head decides. No suite runs on this machine for a merge. Optional. |
| `home-thread` | The sweep switch. With a thread id in it, the home runs `jmerge --sweep` at its start; empty or missing, nobody sweeps. It decides nothing of the merge: `jbus` runs `jmerge` on each pass whatever it holds. You write it by hand. |

A home's own directory is the repo's directory for the root home, and `~/.local/state/home/<repo>/<scope>/` for a scoped one:

| File | Holds |
|---|---|
| `handoff.md` | A note a home left when the `handoff` skill still started the next home, where one is left. A start reads it, and the next archive moves it to `log/`. |
| `plan.md` | One entry per open task, each with a "Done when" list and your decisions. It holds no status: `jbus plan` counts one from the entry's queue rows. |
| `plan-done.md` | The sections of the entries that are finished, moved there by `jbus plan close <entry>`. |
| `gates.md` | Each question only you can answer, with the default taken. |
| `blockers.json` | Each blocker this home briefed a fix of, by its key, with each fix queued for it: `jbus queue add` counts them against `retry_cap` ([Decisions](../../jbus/docs/jbus/decisions.md)). |
| `home-id` | The home's thread id. The home's start writes it. |
| `prefix` | A scoped home's slug prefix, such as `ux-`, which starts each of its briefs and requests. The root home writes it when it makes the scope. |
| `log/` | The note of each home archived here, dated: what it had out that jbus did not hold, what was uncommitted, what it handed to the root home, and its `Was home:` line. Older notes too. |
| `plan-archived.md` | An archived scope's plan, moved out of `plan.md` so that nothing counts the scope as a home. `/home <scope>` moves it back. |

A thread messages its home only when the home has something to do.
A crewmate tells it only that its task ended with no pull request, or that its task is paused.
A scout tells it that its report is written.
A gate goes to `jbus gate`, and to the home only on a machine with no jbus.
A crewmate sends nothing when its pull request opens or when the findings are handled.
A reviewer sends nothing: jbus tells the crewmate of its review when the crewmate owes a line, and the home only when the brief has no `Thread:` line.
"Telling the home" in `features/crew/SKILL.md` has every case.
The message goes to the id in a `home-id`, read when it is sent: the root home's, or the one in `<scope>/` when the `Home:` line of the brief or request names that scope.
No brief names a thread, so a home that starts rewrites none.
Once a scoped home is archived, its briefs are the root home's, and their reports go to the root.
Once the root home is archived there is no `home-id`, nothing is sent, and the report waits on disk until someone types `/home`.

## Undo an edit to standing.md

A home runs `jbus snapshot --why "<what changed>"` right after each edit to a `standing.md`, so each edit is a commit of its own in `~/.local/state/home`, pushed with the tree ("Back up the homes' state" in `features/jbus/docs/jbus.md`).
To undo one, find its commit, write back the file as it was before it, and snapshot again:

```sh
git -C ~/.local/state/home log -p -- <repo>/standing.md
git -C ~/.local/state/home restore --source=<commit>^ -- <repo>/standing.md
jbus snapshot --why "<repo> standing.md, <commit> undone"
```

The first line lists every edit with its diff, the newest first, and `<commit>` is the one to undo. The second writes the file as it stood in the commit before it, which undoes that edit and every later one. Undoing the commit that made the file removes it. A commit that is not there, or the tree's first commit, makes it fail, and it writes nothing. The undo is itself a commit, so it can be undone the same way.

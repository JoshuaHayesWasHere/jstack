# State

A repo has one root home, and may have scoped homes beside it, each for one goal. `/home <scope>` starts one.

`~/.local/state/home/<repo>/` is shared by every home of the repo:

| File | Holds |
|---|---|
| `notes.md` | Facts about the repo that a new thread would otherwise relearn. A home reads it when a step needs one. No context pack text is copied here: a repo's pack is in its own checkout, at `<repo>/docs/context/` ([context.md](../features/jpack/docs/context.md)). |
| `standing.md` | Your standing rules for the repo's homes. A home reads it whole at its start. |
| `tasks/<slug>.md` | A crewmate's brief, then its Result, then its Review. |
| `scouts/<slug>.md` | A scout's request, then its report. |
| `reports/<slug>.html` | A scout's visual page, when the request asked for one. |
| `merge.log` | The lines `jmerge` printed, each after the time it was printed. |
| `off` | Present when the automatic home is switched off for the repo. |
| `merge-off` | Present when the automatic merge is switched off for the repo. |
| `fresh-check` | One line, the command `jmerge` runs as the repo's local check. Optional. |
| `home-thread` | The merge switch. Empty or missing, `jbus` runs `jmerge`. With a thread id in it, that home runs `jmerge` and `jbus` does not. You write it by hand. |

A home's own directory is the repo's directory for the root home, and `~/.local/state/home/<repo>/<scope>/` for a scoped one:

| File | Holds |
|---|---|
| `handoff.md` | The note the last home left, at most ten lines: what is next, what it has out that jbus does not hold, what not to redo, what is uncommitted, and any gate jbus could not take. The `handoff` skill rewrites it. Where things stand is read from jbus at the next start. |
| `plan.md` | One entry per open task, each with a "Done when" list and your decisions. It holds no status: `jbus plan` counts one from the entry's queue rows. |
| `plan-done.md` | The sections of the entries that are finished, moved there by `jbus plan close <entry>`. |
| `gates.md` | Each question only you can answer, with the default taken. |
| `home-id` | The home's thread id. The home's start writes it. |
| `log/` | Old handoffs, dated. |

A thread messages its home only when the home has something to do. A crewmate tells it that its pull request is fixed and green, that it is green with no review to come, that its task ended with no pull request, or that its task is paused. A scout tells it that its report is written. Either sends a gate. A crewmate sends nothing when its pull request opens or when the findings are handled. A reviewer sends its findings to the crewmate's thread, and to the home only when the brief has no `Thread:` line. "Telling the home" in `skills/crew/SKILL.md` has every case. The message goes to the id in a `home-id`, read when it is sent: the root home's, or the one in `<scope>/` when the `Home:` line of the brief or request names that scope. No brief names a thread, so a home that starts rewrites none. Between a handoff and the next start there is no `home-id`, nothing is sent, and the report waits on disk.

## Undo an edit to standing.md

A home runs `jbus snapshot --why "<what changed>"` right after each edit to a `standing.md`, so each edit is a commit of its own in `~/.local/state/home`, pushed with the tree ("Back up the homes' state" in `docs/jbus.md`). To undo one, find its commit, write back the file as it was before it, and snapshot again:

```sh
git -C ~/.local/state/home log -p -- <repo>/standing.md
git -C ~/.local/state/home restore --source=<commit>^ -- <repo>/standing.md
jbus snapshot --why "<repo> standing.md, <commit> undone"
```

The first line lists every edit with its diff, the newest first, and `<commit>` is the one to undo. The second writes the file as it stood in the commit before it, which undoes that edit and every later one. Undoing the commit that made the file removes it. A commit that is not there, or the tree's first commit, makes it fail, and it writes nothing. The undo is itself a commit, so it can be undone the same way.

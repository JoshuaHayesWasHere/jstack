# What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](the-queue.md#what-an-approval-is-bound-to));
- every slug in `depends` is merged;
- no branch of its name exists, and no settled thread has its slug;
- fewer than `max_running` crewmates (derived from the machine unless the config sets it, `jgauge sizes` prints it) are out across every project in the config;
- `jgauge room` prints `go`.

Rows launch lowest `priority` first. A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there. jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch.

- **A brief whose scope changed after the go** is `condition <slug>: brief changed after approval`.
  Approve it again.
  An edit that keeps its meaning fingerprint is no change.
- **A brief is not checked again.**
  The checks of `add` (`Design:`, `Proves it:`, `Skills:`, `Size:`, `Where:`, `Playbook:`) are made when a row is first queued, and a launch makes none of them.
  A row with a go is grandfathered, whatever a check added since says of its brief.
- **No room** prints `wait <slug>: no room: <why>` and launches neither that row nor any after it in the pass.
  After `room_passes` passes in a row with no room, jbus records `condition <slug>: no room for <n> passes: <why>` once.
- **A lost reply is never launched twice.** jbus writes a file keyed `<project>/<slug>/<brief_sha 12>` under `~/.local/state/jbus/launches/` before the call, and looks a lost reply's thread up.
- **Overlap stops no launch.** Each crewmate has its own worktree and branch. A launch that shares a path with a brief that is out sends `overlap <slug>: shares <paths> with <holder>; whichever merges second rebases`, once per pair.

`max_running` is one count for the machine. Each pass adds up the crewmates that are out in every project before it launches anything. The free slots go to the projects in turns, in the order of the config, one row a turn. `~/.local/state/jbus/rotation.json` names the project whose turn is first. If T3 Code does not answer for one project, that pass launches nothing in any project. Once the count is reached, each pass prints one line for every row it holds, `max_running is <n> across all projects: <slug> waits, since <time>`, where the time is when the row began to wait for a slot.

## A scout

A scout's request goes out on a path of its own, so research someone asks for, an expert bot included, never becomes a crewmate that branches and opens a pull request.

```
jbus scout add <slug> < request.md
jbus scout approve <slug> --sha <sha12> --word <id>
jbus scout approve <slug> --sha <sha12> --answer <number>
jbus scout approve <slug> --sha <sha12> --message <thread id>/<message id>
jbus scout approve <slug> --sha <sha12> --page <session key>/<entry id>
jbus scout show
```

- **`add`** checks the request against `features/scout/templates/scout-request.md` and stores it as `scouts/<slug>.md` in the home's state directory.
  It refuses a line only a crewmate's brief has (`Task:`, `Size:`, `Pull request:`), naming it, and a request out of the template's shape.
  It never takes over a request a home wrote itself, and never changes one whose scout is out.
- **`approve`** takes the same bases as `jbus queue approve`, `--rule` aside, and the first 12 of the request's sha, which `add` prints.
  The go holds for that request alone: an edit after it, `Home:` and `Thread:` lines aside, holds the launch until you approve it again.
- **A pass** launches each approved request once, as a thread titled `scout: <slug>` told `/scout <slug>`.
  The thread works in the project's own checkout as it stands, with no worktree and no branch, so it has nothing to commit and no pull request to open.
  Its model is the role map's `scout` line, it waits for `jgauge room --light`, and it takes no slot of `max_running`.
  jbus writes `Thread: <id>` into the request, and a lost reply is adopted on the next pass, never launched twice.
- **`show`** prints each request's state (`requested`, `approved`, `changed`, `launching` or `launched`), its thread, what its last Report says (`none`, `reported`, `blocked` or `not done`) and its go.

`jbus queue add` and `jbus scout add` refuse a `Task:` or a `Request:` line longer than 2,000 characters, the text of the line and the lines under it.
A transcript or a long text goes in a file the line names.

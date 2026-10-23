# What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](the-queue.md#what-an-approval-is-bound-to));
- every slug in `depends` is merged;
- no branch of its name exists, and no settled thread has its slug;
- fewer than `max_running` crewmates are out across every project in the config (`jgauge sizes` prints `max_running`, which jbus derives from the machine unless the config sets it);
- `jgauge room` prints `go`.

Rows launch lowest `priority` first. A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there. jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch.

- **A brief whose scope changed after the go** gets `condition <slug>: brief changed after approval`.
  Approve it again.
  An edit that keeps its meaning fingerprint is no change.
- **A brief is not checked again.**
  `add` runs its checks (`Design:`, `Proves it:`, `Skills:`, `Size:`, `Where:`, `Playbook:`) when it first queues a row, and a launch runs none of them.
  A row with a go is grandfathered, whatever a check added since says of its brief.
- **No room** prints `wait <slug>: no room: <why>` and launches neither that row nor any after it in the pass.
  After `room_passes` passes in a row with no room, jbus records `condition <slug>: no room for <n> passes: <why>` once.
- **A lost reply never leads to a second launch.**
  jbus writes a file keyed `<project>/<slug>/<brief_sha 12>` under `~/.local/state/jbus/launches/` before the call, and looks up the thread of a lost reply.
- **Overlap does not stop a launch.**
  Each crewmate has its own worktree and branch.
  When a launch shares a path with a brief that is still out, jbus sends `overlap <slug>: shares <paths> with <holder>; whichever merges second rebases`, once per pair.

`max_running` is one limit for the whole machine, not one for each project.
Before it launches anything, each pass adds up the crewmates that are out in every project.
The free slots go to the projects in turns, in the order of the config, one row a turn.
`~/.local/state/jbus/rotation.json` names the project whose turn is first.
If T3 Code does not answer for one project, that pass launches nothing in any project.
Once the count is reached, each pass prints one line for every row that waits, `max_running is <n> across all projects: <slug> waits, since <time>`.
The time is when the row began to wait for a slot.

## A scout

jbus launches a scout's request as a scout thread, never as a crewmate.
So research that anyone asks for, an expert bot included, never branches or opens a pull request.

```
jbus scout add <slug> < request.md
jbus scout approve <slug> --sha <sha12> --word <id>
jbus scout approve <slug> --sha <sha12> --answer <number>
jbus scout approve <slug> --sha <sha12> --message <thread id>/<message id>
jbus scout approve <slug> --sha <sha12> --page <session key>/<entry id>
jbus scout show
```

- **`add`** checks the request against `features/scout/templates/scout-request.md` and stores it as `scouts/<slug>.md` in the home's state directory.
  It refuses a request with a line that only a crewmate's brief has (`Task:`, `Size:`, `Pull request:`), and names the line.
  It also refuses a request out of the template's shape.
  It never takes over a request a home wrote itself, and never changes one whose scout is out.
- **`approve`** takes the same bases as `jbus queue approve`, except `--rule`.
  It also takes the first 12 characters of the request's sha, which `add` prints.
  The go holds for that request alone.
  An edit after the go, other than to the `Home:` and `Thread:` lines, holds the launch until you approve it again.
- **A pass** launches each approved request once, as a thread titled `scout: <slug>` whose message is `/scout <slug>`.
  The thread works in the project's own checkout as it stands, with no worktree and no branch, so it has nothing to commit and no pull request to open.
  Its model is the role map's `scout` line, it waits for `jgauge room --light`, and it takes no slot of `max_running`.
  jbus writes `Thread: <id>` into the request.
  The next pass adopts the thread of a lost reply, so no request launches twice.
- **`show`** prints each request's state (`requested`, `approved`, `changed`, `launching` or `launched`), its thread, what its last Report says (`none`, `reported`, `blocked` or `not done`) and its go.

`jbus queue add` and `jbus scout add` refuse a `Task:` or a `Request:` line longer than 2,000 characters, counting the text of the line and the lines under it.
A transcript or a long text goes in a file the line names.

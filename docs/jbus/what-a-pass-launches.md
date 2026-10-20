# What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](the-queue.md#what-an-approval-is-bound-to));
- every slug in `depends` is merged;
- no branch of its name exists, and no settled thread has its slug;
- fewer than `max_running` crewmates (24 unless the config sets it) are out across every project in the config;
- `jgauge room` prints `go`.

Rows launch lowest `priority` first. A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there. jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch.

- **A brief whose scope changed after the go** is `gate <slug>: brief changed after approval`. Approve it again. An edit that keeps its meaning fingerprint is no change.
- **A brief is not checked again.**
  The checks of `add` (`Design:`, `Proves it:`, `Skills:`, `Size:`, `Where:`, `Playbook:`) are made when a row is first queued, and a launch makes none of them.
  A row with a go is grandfathered, whatever a check added since says of its brief.
- **No room** prints `wait <slug>: no room: <why>` and launches neither that row nor any after it in the pass. After `room_passes` passes in a row with no room, jbus sends `gate <slug>: no room for <n> passes: <why>` once.
- **A lost reply is never launched twice.** jbus writes a file keyed `<project>/<slug>/<brief_sha 12>` under `~/.local/state/jbus/launches/` before the call, and looks a lost reply's thread up.
- **Overlap stops no launch.** Each crewmate has its own worktree and branch. A launch that shares a path with a brief that is out sends `overlap <slug>: shares <paths> with <holder>; whichever merges second rebases`, once per pair.

`max_running` is one count for the machine. Each pass adds up the crewmates that are out in every project before it launches anything. The free slots go to the projects in turns, in the order of the config, one row a turn. `~/.local/state/jbus/rotation.json` names the project whose turn is first. If T3 Code does not answer for one project, that pass launches nothing in any project. Once the count is reached, each pass prints one line for every row it holds, `max_running is <n> across all projects: <slug> waits, since <time>`, where the time is when the row began to wait for a slot.

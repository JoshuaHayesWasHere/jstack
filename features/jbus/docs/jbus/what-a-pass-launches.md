# What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](the-queue.md#what-an-approval-is-bound-to));
- every slug in `depends` is merged, or every one but one, whose pull request is open: the row then launches stacked on that pull request's branch;
- no branch of its name exists, and no settled thread has its slug;
- fewer than `max_running` crewmates are out across every project in the config (`jgauge sizes` prints `max_running`, which jbus derives from the machine unless the config sets it);
- fewer than `max_per_project` crewmates are out in the row's project, 24 unless the config sets it;
- fewer than `max_per_home` crewmates are out for the row's home, 6 unless the config sets it;
- `jgauge room` prints `go`.

Rows launch lowest `priority` first.
A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there.
jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch, but for a stacked link's line below.

A row launched stacked starts its worktree from its base's branch, and its brief has `Stacked on: <slug> <branch>` in its head in place of `Green main:`.
Its crew opens its pull request on that branch, and `jmerge` waits on it as `it is stacked on <branch>, and merges after <slug> merged and jbus moved it onto <default>`.
Each pass after that tells its crew once for each move of its base's head, to rebase onto the base's branch.
Once its base merged, jbus bases its pull request on the default branch, where GitHub has not done so itself on deleting the base's branch, and moves the link's own commits onto it itself in the same pass, with no message to its crew.
It rebases them in a scratch worktree of its own, pushes them with a lease at the head it read, and moves the crew's worktree, where it is clean, to the pushed head.
A crew whose thread is at work is left until a later pass.
A rebase that conflicts, a push the lease refuses, a crew's worktree with work in it, or a reviewer still out leaves the branch as it was, and the crew is told to move its own commits instead.
Once the link moved or that message went, the line says `Stacked on: <slug> <default> at <the commit that merged it>`, and `jmerge` waits until the link's head holds that commit.
A link still on its base's branch gets no message to rebase onto main: its branch holds its base's commits too.

- **A brief whose scope changed after the go** gets `condition <slug>: brief changed after approval: <lines>`.
  `<lines>` names each line the go no longer covers, as `<field>: <the line>`, or `<field>: a line taken out`, joined by `; `.
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
  Each pass compares every two briefs that are out, by their `Where:` lines and by the files each open pull request changes beyond its `Where:` (the `Diff:` of `jmerge --claims`).
  When two of them share a path, jbus sends `overlap <slug>: shares <paths> with <other>; whichever merges second rebases`, once per pair, keyed by the two slugs.
  When the two `Where:` lines do not meet and a diff made them meet, the line says so after the other slug: `, by <slug>'s diff` or `, by both diffs`.
  A pair that is told once is not told again when its shared files grow.
  No launch and no merge waits on it.

`max_running` is one limit for the whole machine, not one for each project.
Before it launches anything, each pass adds up the crewmates that are out in every project.
The free slots go to the projects in turns, in the order of the config, one row a turn.
`~/.local/state/jbus/rotation.json` names the project whose turn is first.
If T3 Code does not answer for one project, that pass launches nothing in any project.
Once the count is reached, each pass prints one line for every row that waits, `max_running is <n> across all projects: <slug> waits, since <time>`.
The time is when the row began to wait for a slot.

Two more caps hold inside each project, and both are top-level keys of `~/.config/jbus/config.toml`, beside `max_running`.
`max_per_project` caps the crewmates out in one project, 24 when the config does not set it.
`max_per_home` caps the crewmates out for one home of a project, the root home or one scope, 6 when the config does not set it.
A config that sets either to anything but a whole number of 1 or more is refused.
A crewmate out counts toward the home its queued brief names on its `Home:` line (`jbriefs.home.home_of`), and toward the root home when that brief is gone.
A row whose home is full waits, and the rows of the project's other homes still take its turns.
A project at its cap takes no more turns in the pass.
A scout and a reviewer are not crewmates, and count toward no cap.
Each pass prints one line for every row a cap holds, with the first cap that holds it, its home's, its project's or the machine's:

```
max_per_home is 6 in the root home: <slug> waits, since <time>
max_per_home is 6 in the flow home: <slug> waits, since <time>
max_per_project is 24 in jstack: <slug> waits, since <time>
max_running is 24 across all projects: <slug> waits, since <time>
```

## What a rebase asks of its crew

`rebase.tell` reads three kinds of `wait` line `jmerge` prints about a rebase, and sends the crew one message for each head, keyed `<kind>|<slug>|<head 12>`.

| `jmerge` waits on | jbus sends | Key |
|---|---|---|
| main moving under the pull request, or a conflict with its base | an ask to rebase, with a backup ref and a lease | `rebase` |
| a rebase that changed the content after its review (`scoped review of <range-diff>`) | an ask for one scoped review of that range-diff | `rereview` |
| lines the rebase dropped with no `Dropped on rebase:` line at the head | an ask to put the lines back or explain each file | `drops` |

The third kind ends in a scoped-review ask too.
Once the Result explains each drop, `jmerge` waits with `the scoped review has not ruled on the drops in <files>; scoped review of <range-diff>`, and jbus asks the crew for that scoped review under the `rereview` key.
A head with a `rereview` mark already, or whose Result has a `Scoped reviewer:` line of it, is asked nothing more.

## A scout

jbus launches a scout's request as a scout thread, never as a crewmate.
So research that anyone asks for, an expert bot included, never branches or opens a pull request.
A request is a row of the queue, queued, approved and ordered as any row is:

```
jbus queue add <slug> --priority <n> [--entry <entry>] [--depends <slugs>] < scouts/<slug>.md
jbus queue approve <slug> --sha <sha12> --word <id>
```

- **`add`** takes a text whose head has a `Request:` line and no `Task:` line as a scout's request, and keeps it as a row whose `role` is `scout`.
  It checks the request against `features/scout/templates/scout-request.md` in place of a brief's lints.
  It refuses a request with a line that only a crewmate's brief has (`Size:`, `Pull request:`), and names the line, and a request out of the template's shape.
  A row keeps the role it was first queued with, until its Report says done.
  Then the crewmate's brief the scout delivered at its slug takes the row over, with no go, and the pass launches it as any crewmate's once it has one.
  `--depends` needs the request's `Builds on:` line to name the row, as a brief's does.
- **The go** is a row's go: your word with `jbus queue approve`, or the go of the row's plan entry under `go = "entry"`.
  The follow-up rule approves no request.
- **A pass** launches each request whose go holds and whose depends are over (merged, a crewmate's row ended `done`, or a scout's row whose Report says `Status: done`), once, as a thread titled `scout: <slug>` whose message is `/scout <slug>`.
  The thread works in the project's own checkout as it stands, with no worktree and no branch, so it has nothing to commit and no pull request to open.
  Its model is the role map's `scout` line, it waits for `jgauge room --light`, and it takes no slot of `max_running`.
  jbus writes the queued request to `scouts/<slug>.md` in the home's state directory, or holds the launch with a condition where the file there is another request, and writes `Thread: <id>` into it.
  The next pass adopts the thread of a lost reply, so no request launches twice.
- **`jbus queue show`** lists the row with `scout` in its `role` column.
  It is `queued` until it launches, then `launched` or `running`, `done` once its last Report says `Status: done`, and `left` for a Report that says anything else.

`jbus queue add` refuses a `Task:` or a `Request:` line longer than 2,000 characters, counting the text of the line and the lines under it.
A transcript or a long text goes in a file the line names.

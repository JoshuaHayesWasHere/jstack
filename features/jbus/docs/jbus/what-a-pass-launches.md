# What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](the-queue.md#what-an-approval-is-bound-to));
- every slug in `depends` is merged, or every one but one, whose pull request is open: the row then launches stacked on that pull request's branch, unless its brief opens no pull request (a measure or a proof row), which is never stacked and waits for that slug's merge;
- no branch of its name exists, save the one jbus made for a launch whose connection dropped (below), and no settled thread has its slug;
- main is not red, as `main.json` reads it, or the row fixes main (jbus filed it for the red, or its heading says it fixes main), or it launches stacked on an open row it depends on; any other row waits as `main is red: waits for green`, and launches on the first pass that reads main as green ([A red main](a-red-main.md));
- fewer than `max_running` crewmates are out across every project in the config (`jgauge sizes` prints `max_running`, which jbus derives from the machine unless the config sets it);
- fewer than `max_per_project` crewmates are out in the row's project, 24 unless the config sets it;
- fewer than `max_per_home` crewmates are out for the row's home, 6 unless the config sets it;
- `jgauge room` prints `go`.

Rows launch in this order (`queue.order`):

1. The lowest priority first, counting the priority a row inherits: a row named by the `Waits on:` line of a row's last Result, or by the `depends` of a row already launched, takes the lowest priority of the rows waiting on it, down any chain of such waits.
   A row that is over, or whose thread is archived, lifts nothing.
2. Among rows of one priority, the one that has waited longest: the oldest `since`, the time its present `why` first held.
   A row with no `why` yet comes last.
3. Then by slug.

So a row that a paused crew waits on launches ahead of the rows that crew would launch ahead of, and a newer row never passes an older one of the same priority.

A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there.
jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch, but for a stacked link's line below.

A row launched stacked starts its worktree from its base's branch, and its brief has `Stacked on: <slug> <branch>` in its head in place of `Green main:`.
Its crew opens its pull request on that branch, and `jmerge` waits on it as `it is stacked on <branch>, and merges after <slug> merged and jbus moved it onto <default>`.
Its line of `work.json` is `stacked`: its `who` is `<slug>`, the row it is stacked on, its `waits` is `<slug> to merge`, and its `why` is the queue row's, as each row's line carries it.
The view draws it in Check, on the Stacked stage.

A stack is made by a depends only.
`jbus queue add` refuses a brief whose own `Stacked on:` line names a row its depends does not, with `refused: <slug> cannot be stacked on <row>: its depends does not name <row>`, and says to add `--depends <row>`.
While the base is open, the link stays on its stack, and jbus tells its crew nothing, whatever the base's head does (`jbus.stack`).

Once its base merged, jbus moves the link once.
It bases the link's pull request on the branch the base merged into, where GitHub has not done so itself on deleting the base's branch.
A base merged into another branch than the default leaves its link on that branch.
jbus moves the link's own commits onto that branch itself in the same pass, with no message to its crew.
It rebases them in a scratch worktree of its own, pushes them with a lease at the head it read, and moves the crew's worktree, where it is clean, to the pushed head.
A crew whose thread is at work is left until a later pass.
A rebase that conflicts, a push the lease refuses, a crew's worktree with work in it, or a reviewer still out leaves the branch as it was, and the crew is told to move its own commits instead.
Once the link moved or that message went, the line says `Stacked on: <slug> <branch> at <the commit that merged it>`, and `jmerge` waits until the link's head holds that commit.
A link still on its base's branch gets no message to rebase onto main: its branch holds its base's commits too.
A link with no pull request yet, its crew at its desk proof or waiting on its review, has only its line moved, in the brief's head and on its Result's `Stacked on:` line, before jbus launches its reviewer, so the reviewer fetches a base origin still has.

- **A brief whose scope changed after the go** gets `condition <slug>: brief changed after approval: <lines>`.
  `<lines>` names each line the go no longer covers, as `<field>: <the line>`, or `<field>: a line taken out`, joined by `; `.
  Approve it again.
  An edit that keeps its meaning fingerprint is no change.
- **A brief is not checked again.**
  `add` runs its checks when it first queues a row: the eight lines a brief must have, the checks of `Task:`, `Design:`, `Proves it:`, `Skills:`, `Size:`, `Review:`, `Playbook:`, `Where:`, `Instruments:` and `Builds on:`, the load check and the brief's conduct ([The table](the-queue.md#the-table)).
  A launch runs none of them.
  A row with a go is grandfathered, whatever a check added since says of its brief.
- **No room** prints `wait <slug>: no room: <why>` and launches neither that row nor any after it in the pass.
  After `room_passes` passes in a row with no room, jbus records `condition <slug>: no room for <n> passes: <why>` once.
- **A full /tmp is swept before the row waits on it**, with no word of yours (`jbus.cleanup.sweep`).
  When `jgauge room` says /tmp is full (its quota, its size or its file slots), jbus removes, and then asks room again:
  - the Claude scratch folder of each T3 Code worktree that is gone and is no live row's;
  - each session folder in the Claude scratch folder of a configured project's main checkout (`/tmp/claude-<uid>/-home-<user>-repos-<repo>/<session>/`, a home's, a scout's or your own session's) that nothing wrote in for `IDLE`, 12 hours, and that no running process resumes;
  - each copy of the base that a `proved.sh` killed before its EXIT trap left.

  It leaves every folder a process works in or names, every session folder written in within those 12 hours, every session folder a running process resumes however long it sat idle (its name is the session id a Claude process names, as in `claude --resume=<id>`, `claude --resume <id>` or `claude --session-id <id>`, as T3 Code runs a session with its working directory at the checkout; a session started fresh, with neither, is kept by those 12 hours alone), every copy of the base in a folder where a `proved.sh` still runs, and everything else in /tmp: a crew's own clone under a name of its choosing, such as `/tmp/t3s-stable`, stays until you clear it.
  It says `cleared /tmp: <n> folders finished crews left, <m> of sessions ended in a main checkout, <the first three>`.
  Where no process can be read, it removes nothing and the row waits.
- **A lost reply leads to a second launch only when the connection dropped and no thread was made.**
  jbus writes a file keyed `<project>/<slug>/<brief_sha 12>` under `~/.local/state/jbus/launches/` before the call, and looks up the thread of a lost reply.
  A launch whose connection dropped (ECONNRESET) and whose lookup finds no thread of its title and branch is launched once more, under the same file.
  A second drop, a server error or any other lost reply is `condition <slug>: launch reply lost, <n> matching threads`.
- **A file another brief names does not stop a launch.**
  Each crewmate has its own worktree and branch.
  The crew of the pull request that merges second rebases it, and jbus tells that crew to.

`max_running` is one limit for the whole machine, not one for each project.
Before it launches anything, each pass adds up the crewmates that are out in every project.
The free slots go to the projects in turns, in the order of the config, one row a turn.
`~/.local/state/jbus/rotation.json` names the project whose turn is first.
If T3 Code does not answer for one project, that pass launches nothing in any project.
Once the count is reached, each pass prints one line for every row that waits, `max_running is <n> across all projects: <slug> waits, since <time>`.
The time is when the row began to wait for a slot.

`max_per_project` and `max_per_home` hold inside each project, and both are top-level keys of `~/.config/jbus/config.toml`, beside `max_running`.
A home is the root home or one scope of the project.
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

## A crew's worktree

jbus makes the crew's worktree itself, before the launch, and launches the crew into it with `existing_worktree` (`jbus.crewtree`).
It fetches the row's base from origin (the default branch, the branch its `Pull request:` line names, or the branch of the pull request it is stacked on) and runs `git worktree add --no-track -b <slug>` at that commit, at the path T3 Code would have used: `$T3CODE_HOME/worktrees/<checkout>/<slug>`, `~/.t3` when `T3CODE_HOME` is not set.
In the worktree it writes two files that are in no commit:

- `.claude/settings.json`, from `jroles.mirror.worktree_settings`: `permissions.deny` of `Artifact` and `AskUserQuestion`, and `skillOverrides` that lists by name only each skill of `~/.claude/skills` other than `crew` and `pr-review`, the two a crew and its reviewer invoke.
  Claude Code reads it from the session's folder before the first request and merges it key by key over the instance's own settings, so a crew's first request carries neither tool's schema (about 14,000 tokens on 2026-11-09) and no description of a skill it does not use.
- `.claude/.gitignore`, holding `*`, so neither file shows in `git status` and neither can be committed.
  The repo's `.gitignore` and the shared `info/exclude` stay as they are.

The reviewer launches into the crew's worktree, so it reads the same file.
A scout has a worktree of its own with the same two files ([A scout](#a-scout)).
A home has none: it works in the project's own checkout, which has no such file, so it keeps both tools, since a home publishes pages and asks the user in a question box.

The launch record keeps the commit the branch was made at.
A launch whose reply is lost is looked up and adopted as before, since the thread is on the branch `<slug>`.
A launch whose connection dropped and that made no thread is tried once more into the same worktree, where the branch is still at that commit and nothing in it changed, so no second worktree or branch is made.
A worktree jbus cannot make (origin lacks the base, or the worktree is not clean once its files are written) is a condition, `the crew's worktree could not be made`, and the row does not launch.
A launch T3 Code refuses removes the worktree and the branch with it.
T3 Code's storage cleanup removes a finished crew's worktree by its thread's path under its worktrees folder, whoever made it, as it did when T3 Code made it.

## What a rebase asks of its crew

`rebase.tell` reads three kinds of `wait` line `jmerge` prints about a rebase, and acts once for each head, keyed `<kind>|<slug>|<head 12>`.

| `jmerge` waits on | jbus does | Key |
|---|---|---|
| main moving under the pull request, or a conflict with its base | sends an ask to rebase, with a backup ref and a lease | `rebase` |
| a rebase that changed the content after its review (`scoped review of <range-diff>`) | launches one scoped reviewer of that range-diff in the crew's worktree, and writes its `Scoped reviewer:` line; the crew is sent nothing | `rereview` |
| lines the rebase dropped with no `Dropped on rebase:` line at the head | sends an ask to put the lines back or explain each file | `drops` |

The third kind ends in a scoped review too.
Once the Result explains each drop, `jmerge` waits with `the scoped review has not ruled on the drops in <files>; scoped review of <range-diff>`, and jbus launches that scoped reviewer under the `rereview` key.
A head with a `rereview` mark already, or whose Result has a `Scoped reviewer:` line of it, gets no other reviewer.
The key is marked before the launch, so a pass that crashes launches no second one; a capped review pool, no worktree for the crew, or T3 Code refusing the launch marks nothing and is a gate once for the head.
The crew hears of the scoped review from `jbus.reviewed` once it is written, with its findings by id, and of a clean one not at all.

## A crew is compacted at its pull request

Once a crew's pull request is open, `compact.tell` sends its thread one message, a slash and the word `compact`, which is Claude Code's command to compact a session; its template is `compact` and its key `compact|<slug>`, and it goes once for the row.
T3 Code runs a compaction for a user message that is that command, so the crew waits on its checks with a summary of its work, and not the whole context it built up.

Why: a crew is at about 160k tokens when its pull request opens, under T3 Code's 200k floor for an idle compaction, so it was never compacted there.
Each call it then made for a failed check, a conflict or a comment sent 208.7k tokens on average (2026-11-09).
A probe compacted a finished crew at 137k: its next call sent 38.9k, and it still knew its brief.

It goes on the first pass where all of these hold:

- the row's pull request is open: a merged or closed one gets none;
- the brief's last Result that names a pull request names its URL;
- the thread is the row's crew, as its title says: a home, a scout or a reviewer gets none;
- T3 Code says the thread has no turn running or queued: a crew still at work is compacted on the first pass after its turn ends;
- the thread's last call, in [the telemetry store](the-telemetry-store.md), sent 100k tokens or more: a thread the store holds no call of yet waits for a pass whose build read one;
- the outbox holds it under none of its rules: a thread this pass already told something waits for the next pass.

A pass where one of these does not hold sends nothing and writes no key, so a later pass asks again.
`outbox.jsonl` keeps one `compact` line for each send.

## A home, a crew or a scout is compacted at its ceiling

`compact.tell_at_ceiling` sends the same message to a thread of a role once its last call has sent the role's ceiling or more (`compact.CEILINGS`): 430k tokens for a home, 180k for a crew and 330k for a scout, the user's ceilings of 2026-11-12.
A crew is still compacted at its pull request too, at 100k, as above.
Its key is `compact|<role>|<thread>|<at>`, where `<at>` is the time of that last call, so a thread is compacted once for each climb, and again each time it climbs back to the ceiling.

The threads of a role are:

- for a home, each home thread of the project, the root home's and each scope's;
- for a crew or a scout, each thread of the project T3 Code lists whose title gives that role: T3 Code lists no archived thread, and a finished task's or scout's thread is archived, so a thread that is woken no more gets none.

A row's status cannot say which threads are woken no more: an idle scout has written its Report, so its row is `done`.

Why: T3 Code compacts only a thread whose last run has completed, two minutes before its cache expires, and a home woken every few minutes never gets there.
On 2026-11-09 the polish home made 751 calls in eight hours with no gap over 21.5 minutes, and climbed from 57k to 630k.
A crew or a scout that waits between turns, on a review, a check or an answer, replays its whole context on each call it is woken for.

Replayed over the main calls of 2026-11-08 to 2026-11-12 in the telemetry store, a pass compacting a thread idle for 2 minutes or more, and its next call sending the median size of a call after a compaction:

- crews: 217 of 707 threads compacted 246 times, and the mean crew call goes from 130.4k to 103.7k;
- scouts: none, since no scout call went over 298.9k that week;
- homes, over their calls before the 150k ceiling began (2026-11-10 13:34): 4 compactions of 2 threads in place of 50 of 16, and the mean home call goes from 102.4k under the 150k ceiling to 185.7k.

It goes on the first pass where all of these hold:

- the thread's last call, in [the telemetry store](the-telemetry-store.md), sent its role's ceiling or more: a thread the store holds no call of gets none;
- no compact message went for that call yet: the store keeps no call for a compaction itself, so a thread stays at its last big call until it speaks again, and a key of the thread alone would compact a thread once and never again;
- the call is newer than the last compact message the thread was sent, by either rule: the store is built by a chore that can trail a pass, and a call it reads late from before the compaction is not a new climb, and a crew compacted at its pull request is not compacted again for that call;
- T3 Code says the thread has no turn running or queued: a thread is compacted between turns, never in the middle of one;
- the outbox holds it under none of its rules: a thread this pass already told something waits for the next pass.

The step runs before `wakes.tell`, so a home sent the compact message hears its wake on the next pass, when its compaction has ended, with nothing of the wake lost: the outbox holds a second message that needs `act` to a thread this pass told, and the items stay new to the home until a wake goes.
A send T3 Code did not take writes no key, so the next pass sends it again; one T3 Code refused is marked and not sent again for that call.

## A scout

jbus launches a scout's request as a scout thread, never as a crewmate.
So research that anyone asks for, an expert bot included, never branches or opens a pull request.
A request is a row of the queue, queued, approved and ordered as any row is:

```
jbus queue add <slug> --priority <n> [--entry <entry>] [--depends <slugs>] < scouts/<slug>.md
jbus queue approve <slug> --word <id>
```

- **`add`** takes a text whose head has a `Request:` line and no `Task:` line as a scout's request, and keeps it as a row whose `role` is `scout`.
  It checks the request against `features/scout/templates/scout-request.md` in place of a brief's lints.
  It refuses a request with a line that only a crewmate's brief has (`Size:`, `Pull request:`), and names the line, and a request out of the template's shape.
  A row keeps the role it was first queued with, until its Report says done.
  Then the crewmate's brief the scout delivered at its slug takes the row over, with no go, and the pass launches it as any crewmate's once it has one.
  `--depends` needs the request's `Builds on:` line to name the row, as a brief's does.
- **The go** is a row's go: your word with `jbus queue approve`, or the go of the row's plan entry under `go = "entry"`.
  The follow-up rule approves no request.
- **A pass** launches each request whose go holds and whose depends are over (merged, a crewmate's row that a pass wrote `done` (`work.over`), or a scout's row whose Report says `Status: done`), once, as a thread titled `scout: <slug>` whose message is `/scout <slug>`.
  Before the launch jbus makes the scout a worktree of its own (`jbus.crewtree.make_scout`): `git worktree add --detach` at origin's default branch, just fetched, at `$T3CODE_HOME/worktrees/<checkout>/scout+<slug>`, a name no slug can take, so it never meets a crew's worktree of the same slug.
  It has no branch, so the scout has nothing to commit and no pull request to open.
  jbus writes the two files of [A crew's worktree](#a-crews-worktree) in it, the skill listed in full being `scout`, and launches the thread into it with `existing_worktree`, so the scout's first request carries neither `Artifact` nor `AskUserQuestion`.
  The scout still reads and writes the home's state directory, which it finds from the repo's shared git folder.
  Any folder an earlier pass left at that path, before it wrote a launch record, is removed and made again; a worktree jbus cannot make is the condition `the scout's worktree could not be made`, and a launch T3 Code refuses removes the worktree.
  Once the scout's last Report says `Status: done`, or its row is removed, the first pass on which no thread of the scout is at work removes the worktree (`scouts.clear`) and says `removed scout <slug>'s worktree`.
  Its model is the one the request's `Model:` line names (`jbus.queue.model`), on the provider, pool and options of the role map's `scout` line.
  A request with no `Model:` line launches on the model of the role map's `scout` line.
  A request that names a model while the role map has no `scout` line launches nothing: the pass records the condition `the request names a model and the role map has no scout line`.
  The scout waits for `jgauge room --light`, and it takes no slot of `max_running`.
  jbus writes the queued request to `scouts/<slug>.md` in the home's state directory, or holds the launch with a condition where the file there is another request, and writes `Thread: <id>` into it.
  The next pass adopts the thread of a lost reply, so no request launches twice.
- **`jbus queue show`** lists the row with `scout` in its `role` column.
  It is `queued` until it launches, then `launched` or `running`, `done` once its last Report says `Status: done`, and `left` for a Report that says anything else.

`jbus queue add` refuses a `Task:` or a `Request:` line longer than 2,000 characters, counting the text of the line and the lines under it.
A transcript or a long text goes in a file the line names.

## A home

A pass keeps the catch-all's home, `uncategorized`, running once the project's home has started (a root `plan.md`).
When the catch-all's `home-id` names no thread, or one T3 Code has archived or does not know, and the thread jbus last launched for it is not at work, the pass makes `uncategorized/` with an empty `plan.md` where there is none and launches a thread titled `home: <project> uncategorized` whose message is `/home uncategorized`.
The thread works in the project's own checkout, with no worktree and no branch, and its model is the role map's `home` line.
Its start writes its own `home-id`.
A launched thread holds off the next launch only while its start may still write its `home-id`: one whose start failed or went idle with no `home-id` written is launched again on the next pass.

A home that stalls is launched again too: a home quiet with work out is nudged twice, a patience apart, and a patience after the second nudge jbus launches `/home <scope>` on a fresh thread ([What waits on you](what-waits-on-you.md#a-home-that-stalls)).

`~/.local/state/jbus/<project>/relaunches.json` keeps the last launch of each home: its thread, when, and why, and the `stage` of its start: `intent` before T3 Code names its thread, `launched` once it does, `started` once the home's `home-id` names that thread, and `failed` when its run ended with no `home-id` and no launch has followed.
jbus holds a home's next launch for `PATIENCE` (60 minutes), the time its start has to write its `home-id`, only while that start may still write it: its thread is at work, T3 Code does not list it yet, or the reply that names it was lost.
A start whose run ended is over at once, and the next pass launches the home again.
jbus reads what the run failed on: `not signed in` for a login lapse, a usage limit, which it writes to the ledger so the next launch goes to another instance or waits for the reset, or else the run's end.
A second start in a row that fails on the cause the first failed on waits for that cause to clear (the instance it ran on signed in again, the limit's reset, or `PATIENCE` for any other cause) and says so once, a quiet `home-start` event in the digest.
The home's entry keeps the failure and `says`, why a home has no `home-id` yet, such as `start failed: not signed in`, through the next launch, and drops both once the home starts, a scoped home as the catch-all.
The T3 Code fork's sidebar shows such a home's `says` in place of `starting...`.
No home launches while the dispatch is off or stopped.
